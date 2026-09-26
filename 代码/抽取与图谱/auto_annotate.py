# -*- coding: utf-8 -*-
r"""auto_annotate.py —— 第 6 阶段抽取评测集 v2.1 的「**模型自动标注**」管线（模型参照集）。

## 它是什么、不是什么（硬约束，不是建议）

* 产出的是 **模型参照集，不是人工金标准**。`annotation.status` 一律写 `auto_annotated`，
  并带 `provenance` 块如实登记「谁产的、用什么产的」；全部文档里都必须如实这么写，
  **禁止**任何地方把它说成「人工标注」或「金标准」。
* **绝不就地写进第 6 阶段的交付文件**：`dev.jsonl`／`test.jsonl` **只读**，槽位必须保持为空
  （《15》第八节 的冻结契约；`工具\验收第6阶段.py` 与 `sample_eval_set.py --verify-only`
  都盯着这条）。全部产物落在独立目录 `…\抽取评测集\v2.1\自动标注\`（`.gitignore` 覆盖）。
* 用**与抽取器不同的模型**降低同源自证：抽取器是 `deepseek-v4-flash`（别名
  `deepseek-v4-pro` 之外的那个），这里用 `deepseek-v4-pro`。**降低不等于消除**，报告里如实写。

## 复用的东西（不另立一套）

* 密钥与端点：`config.api_key()`／`config.base_url()`；`response_format` 与超时取自 `config.LLM`，
  重试与限流照 `config.PACING`。**标注器的模型／temperature／max_tokens／Prompt 版本是本组件
  自己的固化参数**（见下方常量区），与《16》第1.1节 的**抽取链冻结四要素**是两组参数，不要混谈。
  环境变量 `STAGE6_FORBID_MODEL_CALLS=1` 时 `config.api_key()` 会直接抛错——本脚本另在
  `call_model()` 入口先拦一道，保证**缓存未命中即失败**，不许偷偷打接口。
* 校验：`工具\标注助手.py` 的公开入口 `validate_annotation(record, cfg, path)`
  ——与 `check` **共用同一个校验源**，因此不存在「自动标注另一套校验」。
* 字段清单与枚举：`工具\标注助手.py` 的 `ENTITY_PER_TYPE_FIELDS`／`CASE_TYPES` 与
  `代码\抽取与图谱\config.py` 的本体常量；本体定义文本直接调
  `config.ontology_definitions_text()`，脚本内不重抄一处枚举。

## 用法

```powershell
python 代码\抽取与图谱\auto_annotate.py --limit 4          # 试跑（dev 前 4 条）
python 代码\抽取与图谱\auto_annotate.py                    # 跑满 260 条（dev 60 ＋ test 200）
python 代码\抽取与图谱\auto_annotate.py --split dev         # 只跑 dev
python 代码\抽取与图谱\auto_annotate.py --replay            # 只从缓存重放，**0 次调用**
python 代码\抽取与图谱\auto_annotate.py --workers 4         # 并发度（默认 4；1 = 串行）
python 代码\抽取与图谱\auto_annotate.py --force             # 忽略已有缓存，重新调用
$env:STAGE6_FORBID_MODEL_CALLS=1; python 代码\抽取与图谱\auto_annotate.py   # 缓存未命中即失败
```

退出码：0 成功；密钥未就位、缓存与当前输入不一致（未 `--force`）、重放时缓存缺失、
模型不可用等一律非零退出，绝不静默降级。

## 产物

```text
阶段05-数据准备\数据集\抽取评测集\v2.1\自动标注\
    dev.auto.jsonl / test.auto.jsonl   ← 抽样字段与 dev.jsonl／test.jsonl **逐字节同源**，只有 annotation 不同
    自动标注台账.json                    ← 模型／Prompt 版本／逐条 attempts／usage／校验问题／输入摘要／汇总
    自动标注报告.md                      ← 统计分布、quote 定位率、重试率、成本、**被迫猜测的字段清单**
    _缓存\<ITEM_ID>.json                 ← 每条每次尝试的原始返回（可重放）
    工作区\dev\*.md / 工作区\test\*.md    ← 与人工工作区同格式，可直接用 `标注助手.py check` 复核
```
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import re
import sys
import threading
import time
from collections import Counter, OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402

ROOT = config.ROOT
TOOL_RELPATH = "工具\\标注助手.py"
HANDANN_PATH = os.path.join(ROOT, "工具", "标注助手.py")

# --------------------------------------------------------------------------
# 固化参数（模型与 Prompt；换任何一个都要同步升 PROMPT_VERSION 并写进文档）
# --------------------------------------------------------------------------
PROMPT_VERSION = "stage6-auto-annotate-v1.0"
ANNOTATE_MODEL = "deepseek-v4-pro"     # **与抽取器（deepseek-v4-flash）不同的模型**，降低同源自证
TEMPERATURE = 0
# 8192 是作者最初给本组件沿用的抽取器取值。dev 试点实测：5 条里 DEV-005 的第 1、2 轮
# `finish_reason=length`、reasoning 8191／8192、**返回正文长度 0**，白烧 token 再重试
# （试点 reasoning 占 completion 的 93.9%）。端点接受 16384，故本组件改为 16384，把上限
# 让给推理；这是**标注器自己的参数**，不动抽取链的四要素（《16》第1.1节）。
MAX_TOKENS = 16384
MAX_ROUNDS = 3                          # 校验不合格时把问题清单回喂模型重写，最多 3 轮
EVAL_SUBDIR = "抽取评测集"
OUT_DIRNAME = "自动标注"
CACHE_DIRNAME = "_缓存"
WORKSPACE_DIRNAME = "工作区"
CACHE_SCHEMA = "stage6-auto-annotate-cache-1.0"
LEDGER_SCHEMA = "stage6-auto-annotate-ledger-1.0"

TRUTH_SOURCE_NOTE = (
    "**模型参照集，不是人工金标准**：由 %s（Prompt 版本 %s，temperature=%d）在 260 条文本块上"
    "自动产出；未逐条人工复核。第 10 阶段引用这些指标时只能表述为「模型参照下的抽取表现」，"
    "不得写成「人工金标准下的准确率」。"
)

PARAMS_SCOPE_NOTE = (
    "**两组参数不要混谈**：本台账／本报告里的模型／temperature／max_tokens／Prompt 版本是"
    "**自动标注器（`auto_annotate.py` 这个新组件）自己的参数**；"
    "《16-事件抽取与知识图谱（第六阶段）》第1.1节 的**抽取链冻结四要素**"
    "（模型 `deepseek-v4-flash`／模型解析名／Prompt 版本 `stage6-extract-v1.1`／temperature=0）"
    "管的是 `extract.py` 的抽取链，是另一组参数。本次运行**没有改动抽取链的任何冻结值**；"
    "标注器侧唯一的参数改动是 `max_tokens` 8192 → 16384（理由见报告：dev 试点中推理占 completion "
    "的 93.9%，8192 被推理吃满导致返回正文为空、白烧 token 重试）。"
)


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handann = _load_module(HANDANN_PATH, "stage6_handann")   # 校验核心与字段清单的唯一来源


# --------------------------------------------------------------------------
# 路径（全部由 config 推出，不写死版本号）
# --------------------------------------------------------------------------
def eval_dir() -> str:
    return os.path.join(config.DATASET_ROOT, EVAL_SUBDIR, config.DATASET_VERSION)


def out_dir() -> str:
    return os.path.join(eval_dir(), OUT_DIRNAME)


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def norm_ws(text) -> str:
    return handann.norm_ws(text)


def read_jsonl_ordered(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip():
                rows.append((json.loads(line, object_pairs_hook=OrderedDict), line))
    return rows


def write_text_atomic(path: str, text: str) -> None:
    handann.write_text_atomic(path, text)


def sha256_str(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# 1. 提示词（`stage6-auto-annotate-v1.0`）
# --------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "你是 A 股财经信息的**标注员**。你只输出一个 JSON 对象，不输出解释、不输出 Markdown 代码块、"
    "不输出多余字段。你必须严格遵守给定的字段名与枚举，枚举之外的取值一律不要输出。\n"
    "每一条实体、事件、关系、时间都必须给出【原文逐字引用】quote：quote 必须是【本条文本块】里"
    "连续复制的一段文字，12～200 字符，不得改写、不得拼接、不得省略中间字符、不得引用标题、"
    "**不得把下面【文档全文】里别处的原文抄进来**。\n"
    "quote 要连标点一起照抄（书名号、引号、括号、% 都照抄），不要补字也不要删字。\n"
    "事实在**文档级**判定（可以读文档全文来判断参与主体、role、时间对不对），但**证据必须落在"
    "本条文本块上**：本块撑不起的事实不要写进 entities／events／relations／times。\n"
    "时间只写正文能确定到「日」的日期（YYYY-MM-DD）；不能确定到日时写 null，绝不猜测、"
    "绝不用发布时间顶替。\n"
    "只标正文明确写出的事实：不得用常识补全，不得把行业通稿里顺带提到的公司当成事件主体，"
    "**不得编造正文里没有的取值**。"
)

SCHEMA_TEMPLATE = """【输出 JSON 结构】顶层就这 6 个键，不要输出 status／provenance（由程序写）：

{
  "entities": [ ... ],
  "events": [ ... ],
  "relations": [ ... ],
  "times": [ ... ],
  "ontology_boundary_log": [ ... ],
  "notes": ""
}

一、entities[]（实体；`entity_type` 只能取 <<ENTITY_TYPES>>，共 5 类）
   —— **`Event` 不写进这里**，事件一律写 events[]；**不许新增 Product（产品）／Location（地点）**。
   每条必须写：`entity_type`、`entity_ref`（本条内编号 E1／E2…，从 1 开始）、`quote`、`chunk_id`（= <<CHUNK_ID>>）。
   另按类型补必填属性（键必须在，正文给不出取值时写空串 "" 或 []，**不要编**）：
<<ENTITY_FIELDS>>

二、events[]（事件；`event_type` 只能取 <<EVENT_TYPES>>，共 8 种，不多不少、不改名、不合并）
   每条必须写：`event_ref`（V1／V2…）、`event_type`、`event_name`（一句话名称）、
   `event_time`（YYYY-MM-DD，正文不能确定到日就写 null）、`description`（一句话经过）、
   `confidence`（0.0～1.0）、`participants`（数组，每项 {entity_ref, role}，`entity_ref` 必须指向本条
   entities[] 里出现过的编号；`role` 只能取 <<ROLES>>）、`quote`、`chunk_id`（= <<CHUNK_ID>>）。
   `event_id` 由程序填（EVT-<item_id>-<n>），你不用写。
   发布／作出方只写 ISSUED_BY 关系，不再写 PARTICIPATES_IN。

三、relations[]（关系；`relation` 只能取 <<RELATIONS>>，共 9 条，方向即语义、不得反向写）
   —— **`EVIDENCED_BY` 不标注**（由程序按 doc_id 生成）。
   每条必须写：`relation`、`from_label`／`from_ref`／`to_label`／`to_ref`、`quote`，以及三项证据属性
   `source_doc_id`（= <<DOC_ID>>）、`source_chunk_id`（= <<CHUNK_ID>>）、`confidence`（0.0～1.0）。
   端点类型必须与关系 schema 一致：<<RELATION_SCHEMA_NOTE>>。
   `from_ref`／`to_ref` 指向 events[] 时 `label` 写 `Event`，指向 entities[] 时写该实体的 `entity_type`
   （且必须等于该实体真实的 entity_type）。
   `BELONGS_TO` 另填 `valid_from`／`valid_to`（正文没有日期就写 null，**不许编日期**）；
   `PARTICIPATES_IN` 另填 `role`（<<ROLES>>）。`SUPPLIES`／`CUSTOMER_OF`／`COMPETES_WITH`
   只在文档全文**明确陈述**了两家公司的业务关系时才写，`company_list` 的提及不等于关系成立。

四、times[]（时间）每条写：`time_type`（`event_time`／`valid_from`／`valid_to`）、
   `value`（YYYY-MM-DD）、`quote`。`publish_time` 数据集已给、**不重复标注**；`data_cutoff_time`
   是版本级属性、**不得出现**。

五、ontology_boundary_log[]（归不进 8 类事件或 9 条关系时，**只登记、不新增本体**）
   每条写：`case_id`（OB-<item_id>-<n>）、`case_type`（建议取值：<<CASE_TYPES>>）、`summary`、
   `quote`、`chunk_id`（= <<CHUNK_ID>>）、`suggested_handling`。
   ⚠️ 只允许写**建议**（如「疑似需要第 10 条关系：X 与 Y 的委托关系」）。**不得**写「已新增……
   关系／实体类型」这类**已生效**口径，不得自造关系名或实体类型，不得复活 `INVOLVES`。

六、notes（字符串）本块确实没有任何可标事实时：四个列表槽位留空列表、`notes` 写
   `empty_but_checked: true` 加一句理由（**这是合法结果，不许为了填满而编造**）。
   若某事实成立但其最直接的支撑文本不在本块（而在文档全文的别处）：写
   `cross_chunk_evidence: <那一块的 chunk_id>` 并简述该事实，**不要**把它写进本条的槽位。
"""

REPAIR_TEMPLATE = """
────────────────────────────────────────
【上一轮的返回有 %d 处不合口径，请**只重写** JSON 对象，逐条修掉下面每一个问题】
%s
（提示：最常见的原因是 `quote` 不是【本条文本块】里逐字连续出现的一段——请回到上面的
【本条文本块（标注对象）】里复制原文，不要改写、不要拼接、不要引用文档全文里别处的句子。
若某个事实在本块里找不到逐字证据，就**不要写这一条**；整块都没有可标事实时，
四个列表槽位留空、`notes` 写 `empty_but_checked: true` 加理由。）
"""


def render_schema() -> str:
    """schema 说明：枚举来自 config，字段清单来自 `标注助手.py`（与校验器同源），不重抄字面量。"""
    per_type = []
    for et in config.ENTITY_TYPES_FROM_MODEL:
        per_type.append("     - `%s`：%s" % (et, "、".join(handann.ENTITY_PER_TYPE_FIELDS.get(et) or [])))
    schema_note = "；".join(
        "%s %s→%s%s" % (r, "|".join(config.RELATION_SCHEMA[r]["domain"]),
                        "|".join(config.RELATION_SCHEMA[r]["range"]),
                        ("，另带 " + "、".join(config.RELATION_SCHEMA[r]["extra_attrs"]))
                        if config.RELATION_SCHEMA[r]["extra_attrs"] else "")
        for r in config.RELATIONS_FROM_MODEL)
    return (SCHEMA_TEMPLATE
            .replace("<<ENTITY_TYPES>>", "／".join(config.ENTITY_TYPES_FROM_MODEL))
            .replace("<<ENTITY_FIELDS>>", "\n".join(per_type))
            .replace("<<EVENT_TYPES>>", "／".join(config.EVENT_TYPES))
            .replace("<<RELATIONS>>", "／".join(config.RELATIONS_FROM_MODEL))
            .replace("<<ROLES>>", "／".join(config.ROLES))
            .replace("<<RELATION_SCHEMA_NOTE>>", schema_note)
            .replace("<<CASE_TYPES>>", "／".join(handann.CASE_TYPES)))


def render_user_prompt(rec, problems=None) -> str:
    parts = [
        "【本条条目（抽样字段，标注时不要改）】",
        "item_id: %s" % rec.get("item_id"),
        "split: %s" % rec.get("split"),
        "category: %s" % rec.get("category"),
        "publish_time: %s" % rec.get("publish_time"),
        "title: %s" % rec.get("title"),
        "chunk_id: %s" % rec.get("chunk_id"),
        "doc_id: %s" % rec.get("doc_id"),
        "company_list: %s" % json.dumps(rec.get("company_list"), ensure_ascii=False),
        "subject_companies: %s" % json.dumps(rec.get("subject_companies"), ensure_ascii=False),
        "",
        "【本体口径：8 种事件类型的定义、判定优先级与边界（不得新增、改名、合并）】",
        config.ontology_definitions_text(),
        "",
        render_schema(),
        "",
        "────────────────────────────────────────",
        "【本条文本块（`text`，**标注对象**；`quote` 只能取自本段）】",
        str(rec.get("text") or ""),
        "",
        "────────────────────────────────────────",
        "【文档全文（`doc_text`，**仅作上下文**，不是标注对象；其原文不许抄进 quote）】",
        str(rec.get("doc_text") or ""),
    ]
    if problems:
        parts.append(REPAIR_TEMPLATE % (len(problems), "\n".join(
            "  %d) 字段 `%s`：%s" % (i, p["field"], p["message"]) for i, p in enumerate(problems, 1))))
    return "\n".join(parts)


def build_messages(rec, problems=None):
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": render_user_prompt(rec, problems)}]


def input_fingerprint(rec, problems) -> str:
    """输入指纹：缓存键的**唯一**来源。覆盖（缺一不可）：

    ① **条目全部抽样字段**——整条 `rec` 的确定性序列化摘要（不是只挑几个键：`title`／
       `category`／`publish_time`／`company_list`／`subject_companies`／`sampling` 等任何一项变了，
       键就必须变，否则会拿旧返回当新输入的答案）；
    ② **Prompt 模板**——系统提示词、schema 渲染、以及**渲染后的完整 user prompt** 三份摘要；
    ③ **`config.ontology_definitions_digest()`**——本体定义文本（8 类事件定义／判定优先级／边界规则）
       的去空白 sha256；改了定义就要换键，这是 v1.2 变体暴露出的同类缺陷，本组件显式防住；
    ④ **模型** 与 ⑤ **temperature**——另附 `max_tokens`／Prompt 版本。

    `problems` 也进指纹——回喂的问题清单不同，这一轮的输入就不是同一个输入。
    自检用例见 `python 代码\\抽取与图谱\\auto_annotate.py selftest`。
    """
    payload = OrderedDict([
        ("item_record_sha256", sha256_str(config.stable_json(rec))),   # ① 条目全部抽样字段
        ("system_prompt_sha256", sha256_str(SYSTEM_PROMPT)),           # ② Prompt 模板
        ("schema_sha256", sha256_str(render_schema())),
        ("user_prompt_sha256", sha256_str(render_user_prompt(rec, problems))),
        ("prompt_version", PROMPT_VERSION),
        ("repair_problems", [p["field"] + "|" + p["kind"] for p in (problems or [])]),
        ("model_requested", ANNOTATE_MODEL),                           # ④ 模型
        ("temperature", TEMPERATURE),                                  # ⑤ temperature
        ("max_tokens", MAX_TOKENS),
        ("ontology_defs_digest", config.ontology_definitions_digest()),  # ③ 本体定义
    ])
    return config.sha256_hex(config.stable_json(payload))


# --------------------------------------------------------------------------
# 2. 模型调用（复用 config 的密钥／端点／调用参数与限流口径）
# --------------------------------------------------------------------------
_PACE_LOCK = threading.Lock()
_LAST_CALL_TS = [0.0]


def _retryable(exc, openai_mod) -> bool:
    if isinstance(exc, (openai_mod.APIConnectionError, openai_mod.APITimeoutError,
                        openai_mod.RateLimitError)):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def _invoke(client, openai_mod, rec, problems, stats, item_id):
    """发一次请求（含传输层退避重试），返回该次尝试的明细。"""
    kwargs = {
        "model": ANNOTATE_MODEL,
        "messages": build_messages(rec, problems),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
        "response_format": {"type": config.LLM["response_format"]},
    }
    for attempt in range(1, config.PACING["max_retries"] + 2):
        with _PACE_LOCK:
            wait = max(0.0, config.PACING["min_interval_seconds"] - (time.time() - _LAST_CALL_TS[0]))
            if wait:
                time.sleep(wait)
            started = time.time()
            _LAST_CALL_TS[0] = started
        stats["api_calls"] += 1
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if not _retryable(exc, openai_mod) or attempt > config.PACING["max_retries"]:
                raise
            backoff = min(config.PACING["backoff_base_seconds"] * (2 ** (attempt - 1)),
                          config.PACING["backoff_max_seconds"])
            with _PACE_LOCK:
                stats["transport_retries"] += 1
            print("[重试] item_id=%s 第 %d 次失败（%s），%.1f 秒后重试"
                  % (item_id, attempt, type(exc).__name__, backoff))
            time.sleep(backoff)
            continue
        usage = response.usage.model_dump() if response.usage else {}
        usage = {k: v for k, v in usage.items() if v is None or isinstance(v, (int, float, str, dict))}
        return {
            "input_sha256": input_fingerprint(rec, problems),
            "elapsed_ms": int((time.time() - started) * 1000),
            "transport_attempts": attempt,
            "usage": usage,
            "finish_reason": (response.choices[0].finish_reason if response.choices else None),
            "model_resolved": str(getattr(response, "model", "") or ""),
            "response_text": (response.choices[0].message.content if response.choices else ""),
            "round_problems": [p["field"] + "|" + p["kind"] for p in (problems or [])],
            "created_at": now_iso(),
        }
    raise RuntimeError("模型调用失败且未抛出异常（不应到达）")


# --------------------------------------------------------------------------
# 3. 解析、归一化与「机械修复」
# --------------------------------------------------------------------------
def parse_json_object(text):
    """把模型返回文本解析成 JSON 对象；容错只做「剥 Markdown 代码围栏」，不做改写。"""
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            raise
        obj = json.loads(raw[start:end + 1])
    if not isinstance(obj, dict):
        raise ValueError("返回的 JSON 顶层不是对象（是 %s）" % type(obj).__name__)
    return obj


_SLOT_KEYS = ("entities", "events", "relations", "times", "ontology_boundary_log")

# **程序自有**的问题：`provenance` 是本脚本拿到模型返回后才补写的，模型看不见它。
# 因此「回喂重写」的判据里必须排除它——否则每条都会被判「缺 provenance」、白白重写三轮。
_PROGRAM_OWNED_KINDS = ("auto_provenance_missing",)


def _is_program_owned(p) -> bool:
    return p["kind"] in _PROGRAM_OWNED_KINDS or (p.get("field") or "").startswith("provenance")


def _problems_of(ann, rec, cfg) -> list:
    """跑校验器并**丢掉程序自有**的问题，剩下的才是「模型该修的」。"""
    raw = handann.validate_annotation(
        {"item_id": (rec or {}).get("item_id"), "chunk_id": (rec or {}).get("chunk_id"),
         "doc_id": (rec or {}).get("doc_id"), "text": (rec or {}).get("text"),
         "annotation": ann}, cfg)
    return [p for p in raw if not _is_program_owned(p)]


def attach_provenance(ann, attempts) -> OrderedDict:
    """补 `provenance` 块——**自动标注必须能自证是自动标注**（`标注助手.py` 的 `auto_provenance_missing` 守卫）。

    取值全部来自本轮的真实调用记录（模型解析值／时间戳／usage 都取自缓存里的 attempts），
    因此**重放时补出来的 provenance 与首跑逐字一致**。
    """
    last = attempts[-1] if attempts else {}
    out = OrderedDict()
    out["status"] = ann.get("status")
    for slot in _SLOT_KEYS:
        out[slot] = ann.get(slot) if isinstance(ann.get(slot), list) else []
    out["notes"] = ann.get("notes") or ""
    out["provenance"] = OrderedDict([
        ("annotator", "llm"),
        ("model", ANNOTATE_MODEL),
        ("model_resolved", last.get("model_resolved") or ""),
        ("prompt_version", PROMPT_VERSION),
        ("temperature", TEMPERATURE),
        ("generated_at", last.get("created_at") or now_iso()),
        ("attempts", len(attempts)),
        ("usage", summarize_usage(attempts)),
    ])
    return out


def normalize_annotation(obj, rec, cfg) -> dict:
    """把模型返回的原始对象**机械归一化**成合口径的形状（不改写任何内容性取值）。

    只做「按条目自带的抽样字段与本体枚举即可唯一确定」的那些事：
    `chunk_id`／`source_doc_id`／`source_chunk_id` 强制为本条的 `chunk_id`／`doc_id`、
    `event_id` 补 `EVT-<item_id>-<n>`、`EVIDENCED_BY` 与 `Event` 实体剔出去（协议禁止）、
    非法枚举与结构非法的条目剔出去、`data_cutoff_time` 键删掉。
    剔掉的每一样都记进 `notes` 与返回值，**不静默丢**。
    """
    dropped = OrderedDict()
    ann = OrderedDict()
    ann["status"] = handann.AUTO_STATUS
    for slot in _SLOT_KEYS:
        value = obj.get(slot)
        ann[slot] = value if isinstance(value, list) else []

    def _drop(slot, what):
        dropped.setdefault(slot, []).append(what)

    # entities：剔掉 Event（协议：Event 不写进 entities[]）与非法类型
    keep = []
    for ent in ann["entities"]:
        if not isinstance(ent, dict):
            _drop("entities", "非对象的条目")
            continue
        et = ent.get("entity_type")
        if et == "Event":
            _drop("entities", "entity_type=Event（事件一律写 events[]）")
            continue
        if et not in config.ENTITY_TYPES_FROM_MODEL:
            _drop("entities", "entity_type=%s 不在 5 类里" % json.dumps(et, ensure_ascii=False))
            continue
        ent["chunk_id"] = rec.get("chunk_id")
        if not ent.get("entity_ref"):
            ent["entity_ref"] = "E%d" % (len(keep) + 1)
            _drop("entities", "缺 entity_ref，按出现顺序补 E%d" % (len(keep) + 1))
        # 校验器对 per-type 属性只判**键在不在**（`标注助手.py` 的 `_check_entities`）；
        # 缺键就补「无法给出取值」的空值（原文没有的就是没有，**不许编**），并如实登记补了哪些。
        for name in handann.ENTITY_PER_TYPE_FIELDS.get(et) or []:
            if name not in ent:
                ent[name] = [] if name == "aliases" else ""
                _drop("entities", "缺必填键 `%s`（%s），补空值" % (name, et))
        keep.append(ent)
    ann["entities"] = keep
    entity_refs = {e.get("entity_ref") for e in keep if e.get("entity_ref")}

    # events：补 event_id、强制 chunk_id、剔非法类型
    keep_ev, ev_refs = [], set()
    for i, ev in enumerate(ann["events"], 1):
        if not isinstance(ev, dict):
            _drop("events", "非对象的条目")
            continue
        if ev.get("event_type") not in config.EVENT_TYPES:
            _drop("events", "event_type=%s 不在 8 种里" % json.dumps(ev.get("event_type"), ensure_ascii=False))
            continue
        ev["chunk_id"] = rec.get("chunk_id")
        ev["event_id"] = "EVT-%s-%d" % (rec.get("item_id"), len(keep_ev) + 1)
        if not ev.get("event_ref"):
            ev["event_ref"] = "V%d" % (len(keep_ev) + 1)
            _drop("events", "缺 event_ref，按出现顺序补 V%d" % (len(keep_ev) + 1))
        for name in ("event_name", "description"):
            if name not in ev:
                ev[name] = ""
                _drop("events", "缺必填键 `%s`，补空串" % name)
        parts = ev.get("participants")
        if not isinstance(parts, list):
            ev["participants"] = []
            if parts is not None:
                _drop("events", "participants 不是数组，已清空")
        else:
            bad = []
            for p in parts:
                if not isinstance(p, dict):
                    bad.append(p)
                    _drop("events", "participant 不是对象，已剔")
                elif p.get("entity_ref") not in entity_refs:
                    bad.append(p)
                    _drop("events", "participant 指向不存在的 entity_ref=%s，已剔"
                          % json.dumps(p.get("entity_ref"), ensure_ascii=False))
                elif p.get("role") not in config.ROLES:
                    bad.append(p)
                    _drop("events", "participant 的 role=%s 不在 5 个值里，已剔（该写进"
                          " ontology_boundary_log 的 case_type=role_boundary）"
                          % json.dumps(p.get("role"), ensure_ascii=False))
            ev["participants"] = [p for p in parts if not any(p is b for b in bad)]
        keep_ev.append(ev)
        if ev.get("event_ref"):
            ev_refs.add(ev["event_ref"])
    ann["events"] = keep_ev

    # relations：剔 EVIDENCED_BY／非法关系名，强制三项证据属性里的两个 id
    keep_rel = []
    for rel in ann["relations"]:
        if not isinstance(rel, dict):
            _drop("relations", "非对象的条目")
            continue
        name = rel.get("relation")
        if name == "EVIDENCED_BY":
            _drop("relations", "EVIDENCED_BY（协议：不标注，由程序按 doc_id 生成）")
            continue
        if name not in config.RELATION_SCHEMA:
            _drop("relations", "relation=%s 不在 9 条里" % json.dumps(name, ensure_ascii=False))
            continue
        rel["source_doc_id"] = rec.get("doc_id")
        rel["source_chunk_id"] = rec.get("chunk_id")
        keep_rel.append(rel)
    ann["relations"] = keep_rel

    # times：剔非法 time_type
    keep_t = []
    for t in ann["times"]:
        if not isinstance(t, dict):
            _drop("times", "非对象的条目")
            continue
        if t.get("time_type") not in ("event_time", "valid_from", "valid_to"):
            _drop("times", "time_type=%s 不在三选一里" % json.dumps(t.get("time_type"), ensure_ascii=False))
            continue
        keep_t.append(t)
    ann["times"] = keep_t

    # ontology_boundary_log：补 case_id／chunk_id，剔非对象
    keep_ob = []
    for i, e in enumerate(ann["ontology_boundary_log"], 1):
        if not isinstance(e, dict):
            _drop("ontology_boundary_log", "非对象的条目")
            continue
        e["chunk_id"] = rec.get("chunk_id")
        if not e.get("case_id"):
            e["case_id"] = "OB-%s-%d" % (rec.get("item_id"), i)
        keep_ob.append(e)
    ann["ontology_boundary_log"] = keep_ob

    # 版本级属性：不得出现在标注里
    blob = json.dumps(ann, ensure_ascii=False)
    if "data_cutoff_time" in blob:
        for slot in _SLOT_KEYS:
            for item in ann[slot]:
                if isinstance(item, dict):
                    item.pop("data_cutoff_time", None)
        _drop("annotation", "data_cutoff_time（版本级属性，不落任何节点与关系）")

    ann["notes"] = obj.get("notes") if isinstance(obj.get("notes"), str) else ""
    return ann, dropped


def _problems_to_drop(problems):
    """把校验问题映射成「该剔掉哪个条目」：返回 [(槽位, 下标), …]（下标 -1 表示整个槽位）。

    只认得出槽位与下标的问题才剔；认不出的（status／notes 一类）留在原处，由调用方处理。
    """
    out = []
    for p in problems:
        field = p.get("field") or ""
        m = re.match(r"^(%s)\[(\d+)\]" % "|".join(_SLOT_KEYS), field)
        if m:
            out.append((m.group(1), int(m.group(2))))
            continue
        if field in _SLOT_KEYS:
            out.append((field, -1))
    return out


def mechanical_repair(ann, dropped, cfg, rec) -> tuple:
    """把仍不合格的**具体条目**剔掉，直到通过校验或没得剔——每一步都记进 `dropped`。

    这是「校验与重试都不收敛」时的兜底：宁可少标一条并如实登记，也不留一条不合口径的标注
    去污染参照集，更不放宽校验规则。必须带**本条的 text／chunk_id／doc_id** 才跑——
    否则每一个 quote 都会被判「不在正文里」，把整条误剔干净。
    """
    for _ in range(64):
        targets = _problems_to_drop(_problems_of(ann, rec, cfg))
        if not targets:
            break
        wrote = False
        for slot, idx in sorted(set(targets), key=lambda t: -t[1]):
            if idx < 0:
                if ann.get(slot):
                    ann[slot] = []
                    dropped.setdefault(slot, []).append("整个槽位不合口径，已清空")
                    wrote = True
                continue
            items = ann.get(slot) or []
            if 0 <= idx < len(items):
                dropped.setdefault(slot, []).append(
                    "%s[%d] 不合口径，已剔除：%s" % (
                        slot, idx,
                        "；".join(p["field"] + " " + p["kind"] for p in _problems_of(ann, rec, cfg)
                                  if (p.get("field") or "").startswith("%s[%d]" % (slot, idx)))[:300]))
                del items[idx]
                wrote = True
        if not wrote:
            break
    return ann, dropped


def build_annotation(obj, rec, cfg) -> tuple:
    """归一化 → 机械修复 → 空块兜底 → 返回 (annotation, dropped, final_problems)。

    `final_problems` 里**不含 `provenance` 相关**的问题——那是本脚本补写的，模型看不见；
    产出物的最终校验（带 provenance）由 `cmd_run` 收口，`check` 也会再核一遍。
    """
    ann, dropped = normalize_annotation(obj, rec, cfg)
    ann, dropped = mechanical_repair(ann, dropped, cfg, rec)
    problems = _problems_of(ann, rec, cfg)
    if problems and all(p["kind"] == "status_completed_but_empty" for p in problems):
        # 三轮重写后这一块确实什么都标不出来：按协议登记为 `empty_but_checked` 空块
        # （`标注说明.md` 第3.6节 允许的合法结果），而不是硬凑出内容。
        existing = (ann.get("notes") or "").strip()
        ann["notes"] = ("empty_but_checked: true（三轮重写后本块仍无可标事实，登记为空块）"
                        + ("；" + existing if existing else ""))
        dropped.setdefault("annotation", []).append(
            "整块无可标事实，按 `empty_but_checked` 登记为空块（原 kind：status_completed_but_empty）")
        problems = _problems_of(ann, rec, cfg)
    return ann, dropped, problems


# --------------------------------------------------------------------------
# 4. 单条：调用 → 校验 → 回喂重写（最多 MAX_ROUNDS 轮）→ 机械修复兜底
# --------------------------------------------------------------------------
def cache_path(item_id: str) -> str:
    return os.path.join(out_dir(), CACHE_DIRNAME, "%s.json" % item_id)


def load_cache(item_id: str):
    path = cache_path(item_id)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_cache(record) -> None:
    path = cache_path(record["item_id"])
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def call_model(client, openai_mod, rec, stats) -> dict:
    """跑完整条链路（多轮调用 + 机械修复），返回该条的结果与缓存记录。"""
    item_id = rec.get("item_id")
    problems = None
    attempts = []
    final_ann = final_problems = None
    dropped = OrderedDict()
    for rnd in range(1, MAX_ROUNDS + 1):
        detail = _invoke(client, openai_mod, rec, problems, stats, item_id)
        attempts.append(detail)
        try:
            obj = parse_json_object(detail["response_text"])
            ann, dropped, after = build_annotation(obj, rec, cfg=CONFIG)
            detail["parse_ok"] = True
        except (ValueError, TypeError) as exc:
            ann, after, dropped = None, [{"field": "JSON", "kind": "parse_error",
                                          "message": "返回不是合法 JSON 对象：%s" % exc}], OrderedDict()
            detail["parse_ok"] = False
        detail["problems_after"] = [p["field"] + "|" + p["kind"] for p in after]
        final_ann, final_problems = ann, after
        if not after:
            break
        problems = after
    final = attach_provenance(final_ann, attempts) if final_ann is not None else None
    record = OrderedDict([
        ("cache_schema", CACHE_SCHEMA),
        ("item_id", item_id),
        ("split", rec.get("split")),
        ("dataset_version", config.DATASET_VERSION),
        ("model_requested", ANNOTATE_MODEL),
        ("model_resolved", attempts[-1]["model_resolved"]),
        ("prompt_version", PROMPT_VERSION),
        ("temperature", TEMPERATURE),
        ("max_tokens", MAX_TOKENS),
        ("rounds", len(attempts)),
        ("cache_hit", False),
        ("dropped", dropped),
        ("final_annotation", final),
        ("final_problems", [p["field"] + "|" + p["kind"] for p in final_problems]),
        ("final_annotation_sha256", sha256_str(json.dumps(final, ensure_ascii=False, sort_keys=True))
         if final is not None else None),
        ("attempts_detail", attempts),
        ("created_at", now_iso()),
    ])
    return record


def summarize_usage(attempts):
    """把多次尝试的 usage 折成一个合计（各轮的原始返回仍逐条留在缓存里）。"""
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
    for a in attempts:
        u = a.get("usage") or {}
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            total[k] += int(u.get(k) or 0)
        details = u.get("completion_tokens_details") or {}
        total["reasoning_tokens"] += int(details.get("reasoning_tokens") or 0)
    return total


def artifact_call_stats(results) -> tuple:
    """**产物对应**的调用合计（次数，各次 elapsed 秒之和）。

    与 `stats["api_calls"]` 的区别：缓存命中时本次运行一次调用都没发生，但产物仍是当初那些调用
    产出的——台账要能把这两件事分开如实登记（首跑读数与全量重放读数的差别就在这里）。
    """
    calls, elapsed_ms = 0, 0
    for r in results.values():
        for a in (r.get("attempts_detail") or []):
            calls += 1
            try:
                elapsed_ms += int(a.get("elapsed_ms") or 0)
            except (TypeError, ValueError):
                pass
    return calls, round(elapsed_ms / 1000.0, 1)


# --------------------------------------------------------------------------
# 5. 主流程
# --------------------------------------------------------------------------
CONFIG = None


def annotate_one(rec, client, openai_mod, stats, force, replay, lock, ledger_rows):
    item_id = rec.get("item_id")
    cached = load_cache(item_id)
    if replay or (cached is not None and not force):
        if cached is None:
            raise RuntimeError("replay/缓存模式：item_id=%s 的缓存缺失（缓存未命中即失败，不许打接口）"
                               % item_id)
        # 输入指纹不一致 = 缓存与当前输入对不上，必须失败而不是静默沿用。
        want = input_fingerprint(rec, None)
        if cached.get("attempts_detail"):
            first = cached["attempts_detail"][0]
            if first.get("input_sha256") != want:
                raise RuntimeError(
                    "缓存与当前输入不一致：item_id=%s 的缓存 input_sha256=%s，当前=%s。"
                    "这通常意味着条目、提示词、模型或调用参数变过；确认后加 --force 重跑。"
                    % (item_id, first.get("input_sha256"), want))
        record = cached
        record["cache_hit"] = True
        with lock:
            stats["cache_hits"] += 1
        # 重放：**从原始返回重算全链路**（归一化→机械修复→兜底→补 provenance），
        # 不是读一个存下来的答案——首跑与重放走的是同一段代码，因此产出必然一致。
        last = record["attempts_detail"][-1]
        obj = parse_json_object(last["response_text"])
        ann, dropped, problems = build_annotation(obj, rec, CONFIG)
        record = OrderedDict(record)
        record["final_annotation"] = attach_provenance(ann, record["attempts_detail"])
        record["dropped"] = dropped
        record["final_problems"] = [p["field"] + "|" + p["kind"] for p in problems]
        record["final_annotation_sha256"] = sha256_str(
            json.dumps(record["final_annotation"], ensure_ascii=False, sort_keys=True))
        record["rounds"] = len(record["attempts_detail"])
        _push_ledger(record, rec, stats, lock, ledger_rows)
        return record

    # —— 禁止调用模型时（STAGE6_FORBID_MODEL_CALLS=1）：缓存未命中即失败 ——
    if (os.environ.get("STAGE6_FORBID_MODEL_CALLS") or "").strip() == "1":
        raise RuntimeError(
            "STAGE6_FORBID_MODEL_CALLS=1：本次为**重放**，禁止调用模型；item_id=%s 缓存未命中，"
            "按纪律失败，不得回退到接口。" % item_id)

    record = call_model(client, openai_mod, rec, stats)
    save_cache(record)
    with lock:
        stats["fetched"] += 1
    _push_ledger(record, rec, stats, lock, ledger_rows)
    return record


def _push_ledger(record, rec, stats, lock, ledger_rows):
    attempts = record.get("attempts_detail") or []
    usage = summarize_usage(attempts)
    row = OrderedDict([
        ("item_id", record.get("item_id")),
        ("split", rec.get("split")),
        ("category", rec.get("category")),
        ("chunk_id", rec.get("chunk_id")),
        ("doc_id", rec.get("doc_id")),
        ("input_summary", OrderedDict([
            ("text_chars", len(rec.get("text") or "")),
            ("doc_text_chars", len(rec.get("doc_text") or "")),
            ("token_count", rec.get("token_count")),
            ("prompt_chars", len(render_user_prompt(rec)) if attempts else None),
        ])),
        ("rounds", record.get("rounds")),
        ("cache_hit", bool(record.get("cache_hit"))),
        ("usage", usage),
        ("problems_after_each_round", [a.get("problems_after") for a in attempts]),
        ("problems_final", record.get("final_problems")),
        ("dropped", record.get("dropped")),
        ("parse_ok", [a.get("parse_ok") for a in attempts]),
        ("finish_reason", [a.get("finish_reason") for a in attempts]),
        ("elapsed_ms", [a.get("elapsed_ms") for a in attempts]),
        ("model_resolved", record.get("model_resolved")),
        ("created_at", record.get("created_at") or now_iso()),
        ("final_annotation_sha256", record.get("final_annotation_sha256")),
    ])
    with lock:
        ledger_rows[record.get("item_id")] = row


def write_workspace_item(rec, annotation, eval_relpath: str, cfg) -> str:
    """把一条自动标注物化成**与人工工作区同格式**的 md（可直接用 `标注助手.py check` 复核）。"""
    content = handann.render_item(rec, cfg, eval_relpath)
    i = content.find(handann.MARK_ANN_BEGIN) + len(handann.MARK_ANN_BEGIN)
    j = content.find(handann.MARK_ANN_END)
    body = "\n```json\n%s\n```\n" % json.dumps(annotation, ensure_ascii=False, indent=2)
    path = os.path.join(out_dir(), WORKSPACE_DIRNAME, rec["split"], "%s.md" % rec["item_id"])
    write_text_atomic(path, content[:i] + body + content[j:])
    return path


def write_auto_jsonl(rows, out_path: str) -> str:
    """写 auto.jsonl：**在原始行的字节上做手术**，抽样字段逐字节不动，只换 annotation 的值。

    做法：拿 `dev.jsonl`／`test.jsonl` 的**原始行**，在最后一个 `, "annotation": ` 处切开——
    前半段（17 项抽样字段 + `sampling` 的序列化）**原样保留**，只把 annotation 换成新值。
    因此「除 annotation 外全部一致」不是靠 `json.dumps` 再序列化一遍碰巧相同，而是**同一个字节串**。
    """
    lines = []
    for rec, orig_line, annotation in rows:
        marker = ', "annotation": '
        pos = orig_line.rindex(marker)
        head = orig_line[:pos + len(marker)]
        tail = orig_line[pos + len(marker):]
        assert tail.endswith("}"), "原始行不以 annotation 结尾，手术式重写不适用"
        lines.append(head + json.dumps(annotation, ensure_ascii=False) + "}\n")
    text = "".join(lines)
    write_text_atomic(out_path, text)
    return text


def cmd_run(args) -> int:
    global CONFIG
    cfg = CONFIG = handann._load_config()
    splits = ["dev", "test"] if args.split == "all" else [args.split]
    ed = eval_dir()
    od = out_dir()
    os.makedirs(os.path.join(od, CACHE_DIRNAME), exist_ok=True)
    os.makedirs(os.path.join(od, WORKSPACE_DIRNAME), exist_ok=True)

    records = []            # (rec, orig_line, split)
    for split in splits:
        for rec, line in read_jsonl_ordered(os.path.join(ed, "%s.jsonl" % split)):
            records.append((rec, line, split))
    if args.limit:
        records = records[:args.limit]

    replay = bool(args.replay)
    if replay:
        os.environ["STAGE6_FORBID_MODEL_CALLS"] = "1"   # 双保险：任何调用路径都会被拦
        force = False
    else:
        force = bool(args.force)

    stats = {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "fetched": 0}
    lock = threading.Lock()
    ledger_rows = OrderedDict()
    client = openai_mod = None
    need_api = not replay and any(load_cache(r["item_id"]) is None or force for r, _, _ in records)
    if need_api:
        import openai
        openai_mod = openai
        client = openai.OpenAI(api_key=cfg.api_key(), base_url=cfg.base_url(),
                               timeout=cfg.LLM["timeout_seconds"], max_retries=0)

    started = time.time()
    results = {}
    errors = []
    if args.workers <= 1 or replay:
        for rec, _line, _s in records:
            try:
                results[rec["item_id"]] = annotate_one(rec, client, openai_mod, stats, force,
                                                       replay, lock, ledger_rows)
            except Exception as exc:  # noqa: BLE001
                errors.append((rec["item_id"], "%s: %s" % (type(exc).__name__, exc)))
    else:
        import queue
        q = queue.Queue()
        for item in records:
            q.put(item)
        out_lock = threading.Lock()

        def worker():
            while True:
                try:
                    rec, _line, _s = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    rec_out = annotate_one(rec, client, openai_mod, stats, force, replay, lock,
                                           ledger_rows)
                    with out_lock:
                        results[rec["item_id"]] = rec_out
                except Exception as exc:  # noqa: BLE001
                    with out_lock:
                        errors.append((rec["item_id"], "%s: %s" % (type(exc).__name__, exc)))
                finally:
                    q.task_done()

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(args.workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    wall = time.time() - started

    if errors:
        print("有 %d 条失败（不写盘，先修）：" % len(errors))
        for iid, msg in errors[:10]:
            print("  %s：%s" % (iid, msg))
        return 1

    # ---- 收口校验：在**带上 provenance 的成品**上再跑一遍校验器（与 `check` 同一内核）----
    # 这一步的意义是：不写盘之前就证明「`check` 会 260／260 全过」，而不是写完再去碰运气。
    bad = []
    for rec, _line, _s in records:
        ann = results[rec["item_id"]]["final_annotation"]
        for p in handann.validate_annotation(
                {"item_id": rec["item_id"], "chunk_id": rec.get("chunk_id"),
                 "doc_id": rec.get("doc_id"), "text": rec.get("text"), "annotation": ann}, cfg):
            bad.append((rec["item_id"], p["field"], p["kind"]))
    if bad:
        print("成品校验未通过 %d 处（**不写盘**，请先查）：" % len(bad))
        for iid, field, kind in bad[:20]:
            print("  %s | %s | %s" % (iid, field, kind))
        return 1

    # ---- 写产物：auto.jsonl（按输入顺序）、工作区 md ----
    eval_relpath = os.path.relpath(ed, ROOT)
    rows_for_jl = []
    for rec, line, split in records:
        record = results[rec["item_id"]]
        annotation = record["final_annotation"]
        assert annotation is not None, "item_id=%s 没有可用的标注（不应到达）" % rec["item_id"]
        rows_for_jl.append((rec, line, annotation))
        write_workspace_item(rec, annotation, eval_relpath, cfg)
    by_split = {}
    for rec, line, annotation in rows_for_jl:
        by_split.setdefault(rec["split"], []).append((rec, line, annotation))
    for split, rows in by_split.items():
        write_auto_jsonl(rows, os.path.join(od, "%s.auto.jsonl" % split))

    write_ledger(args, cfg, records, results, stats, wall, od)
    write_report(args, cfg, records, results, stats, wall, od)
    write_workspace_guide(cfg, ed, od)

    print("auto_annotate 完成：%d 条｜API 调用 %d 次（传输层重试 %d）｜缓存命中 %d｜墙钟 %.1f 秒"
          % (len(records), stats["api_calls"], stats["transport_retries"],
             stats["cache_hits"], wall))
    print("产物：%s" % od)
    return 0


def write_ledger(args, cfg, records, results, stats, wall, od) -> None:
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
    for r in results.values():
        u = summarize_usage(r.get("attempts_detail") or [])
        for k in total:
            total[k] += u[k]
    rounds_hist = Counter(len(r.get("attempts_detail") or []) for r in results.values())
    calls_in_artifacts, model_elapsed = artifact_call_stats(results)
    ledger = OrderedDict([
        ("schema", LEDGER_SCHEMA),
        ("tool", "代码\\抽取与图谱\\auto_annotate.py"),
        ("定位", TRUTH_SOURCE_NOTE % (ANNOTATE_MODEL, PROMPT_VERSION, TEMPERATURE)),
        ("参数边界", PARAMS_SCOPE_NOTE),
        ("标注器参数", OrderedDict([
            ("model", ANNOTATE_MODEL),
            ("temperature", TEMPERATURE),
            ("max_tokens", MAX_TOKENS),
            ("prompt_version", PROMPT_VERSION),
            ("max_rounds", MAX_ROUNDS),
        ])),
        ("model", ANNOTATE_MODEL),
        ("model_resolved", sorted({r.get("model_resolved") for r in results.values()})),
        ("model_extractor_for_contrast", config.LLM["model_default"]),
        ("prompt_version", PROMPT_VERSION),
        ("temperature", TEMPERATURE),
        ("max_tokens", MAX_TOKENS),
        ("max_rounds", MAX_ROUNDS),
        ("dataset_version", config.DATASET_VERSION),
        ("eval_dir", eval_dir()),
        ("out_dir", od),
        ("counts", OrderedDict([
            ("items", len(records)),
            ("api_calls", stats["api_calls"]),
            ("api_calls_note", "本次运行**新增**的调用次数；产物对应的调用合计见 api_calls_in_artifacts"),
            ("api_calls_in_artifacts", calls_in_artifacts),
            ("cache_hits", stats["cache_hits"]),
            ("transport_retries", stats["transport_retries"]),
            ("rounds_histogram", OrderedDict(("%d 轮" % k, v) for k, v in sorted(rounds_hist.items()))),
            ("usage_total", total),
            ("usage_total_note", "全部条目的 usage 合计（缓存命中时从缓存记录照算），含每次重试轮"),
            ("wall_seconds", round(wall, 1)),
            ("model_elapsed_seconds_total", model_elapsed),
        ])),
        ("items", list(ledger_rows_sorted(results).values())),
    ])
    write_text_atomic(os.path.join(od, "自动标注台账.json"),
                      json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")


def ledger_rows_sorted(results):
    out = OrderedDict()
    for iid in sorted(results.keys()):
        r = results[iid]
        attempts = r.get("attempts_detail") or []
        out[iid] = OrderedDict([
            ("item_id", iid),
            ("split", r.get("split")),
            ("rounds", r.get("rounds")),
            ("cache_hit", bool(r.get("cache_hit"))),
            ("usage", summarize_usage(attempts)),
            ("problems_final", r.get("final_problems")),
            ("dropped", r.get("dropped")),
            ("model_resolved", r.get("model_resolved")),
            ("finish_reason", [a.get("finish_reason") for a in attempts]),
            ("created_at", r.get("created_at")),
            ("final_annotation_sha256", r.get("final_annotation_sha256")),
        ])
    return out


def write_workspace_guide(cfg, ed, od) -> None:
    write_text_atomic(os.path.join(od, WORKSPACE_DIRNAME, "说明.md"), "\n".join([
        "# 自动标注工作区（由 `代码\\抽取与图谱\\auto_annotate.py` 生成）",
        "",
        "**这是模型自动标注（`status = auto_annotated`），不是人工标注，也不是金标准。**",
        "它落在独立产物里；第 6 阶段交付文件 `dev.jsonl`／`test.jsonl` 的槽位仍为空（冻结契约）。",
        "",
        "格式与 `工具\\标注助手.py export` 生成的人工工作区**完全一致**，因此可直接复核：",
        "",
        "```powershell",
        "python 工具\\标注助手.py check --workspace \"%s\" --eval-dir \"%s\""
        % (os.path.relpath(os.path.join(od, WORKSPACE_DIRNAME), ROOT), os.path.relpath(ed, ROOT)),
        "```",
        "",
        "模型：`%s`（抽取器是 `%s`，两者不同，用于降低同源自证）｜Prompt 版本：`%s`｜temperature：`%d`。"
        % (ANNOTATE_MODEL, cfg.LLM["model_default"], PROMPT_VERSION, TEMPERATURE),
        "",
    ]))


# --------------------------------------------------------------------------
# 6. 报告（含「被迫猜测的字段清单」）
# --------------------------------------------------------------------------
def _entity_field_support(ann, rec, field_name, value):
    """判断一个实体属性的取值在正文里的支撑程度：本块 / 只在全文 / 完全没有。"""
    if value in (None, "", [], {}):
        return "空值"
    text_ws = norm_ws(rec.get("text") or "")
    doc_ws = norm_ws(rec.get("doc_text") or "")
    if isinstance(value, (list, tuple)):
        vals = [str(v) for v in value]
    else:
        vals = [str(value)]
    vals_ws = [norm_ws(v) for v in vals if norm_ws(v)]
    if not vals_ws:
        return "空值"
    if all(v in text_ws for v in vals_ws):
        return "本块有"
    if all(v in doc_ws for v in vals_ws):
        return "只在文档全文里（本块无支撑）"
    return "正文里完全没有（纯推测）"


def collect_stats(cfg, records, results):
    S = {
        "entities": Counter(), "events": Counter(), "relations": Counter(),
        "times": 0, "oblog": 0, "empty_but_checked": 0,
        "quote_total": 0, "quote_located": 0,
        "items_with_rounds_gt1": 0, "items_with_drops": 0,
        "dropped_total": Counter(),
        "field_support": OrderedDict(),   # (entity_type, field) -> Counter(支撑程度)
        "notes_flags": Counter(),
    }
    for rec, _line, _s in records:
        ann = results[rec["item_id"]]["final_annotation"]
        text_ws = norm_ws(rec.get("text") or "")
        non_empty = any(ann.get(k) for k in _SLOT_KEYS)
        notes = ann.get("notes") or ""
        if not non_empty and "empty_but_checked" in notes:
            S["empty_but_checked"] += 1
        if len(results[rec["item_id"]].get("attempts_detail") or []) > 1:
            S["items_with_rounds_gt1"] += 1
        dr = results[rec["item_id"]].get("dropped") or {}
        if any(v for v in dr.values()):
            S["items_with_drops"] += 1
        for slot, items in dr.items():
            for _ in items:
                S["dropped_total"][slot] += 1
        for m in re.finditer(r"(cross_chunk_evidence|empty_but_checked)\s*[:：]", notes):
            S["notes_flags"][m.group(1)] += 1
        for ent in ann.get("entities") or []:
            et = ent.get("entity_type")
            S["entities"][et] += 1
            for fname in (handann.ENTITY_PER_TYPE_FIELDS.get(et) or []):
                key = (et, fname)
                bucket = _entity_field_support(ann, rec, fname, ent.get(fname))
                S["field_support"].setdefault(key, Counter())[bucket] += 1
            S["quote_total"] += 1
            S["quote_located"] += int(norm_ws(ent.get("quote")) in text_ws)
        for ev in ann.get("events") or []:
            S["events"][ev.get("event_type")] += 1
            S["quote_total"] += 1
            S["quote_located"] += int(norm_ws(ev.get("quote")) in text_ws)
        for rel in ann.get("relations") or []:
            S["relations"][rel.get("relation")] += 1
            S["quote_total"] += 1
            S["quote_located"] += int(norm_ws(rel.get("quote")) in text_ws)
        for t in ann.get("times") or []:
            S["quote_total"] += 1
            S["quote_located"] += int(norm_ws(t.get("quote")) in text_ws)
        for e in ann.get("ontology_boundary_log") or []:
            S["quote_total"] += 1
            S["quote_located"] += int(norm_ws(e.get("quote")) in text_ws)
        S["times"] += len(ann.get("times") or [])
        S["oblog"] += len(ann.get("ontology_boundary_log") or [])
    return S


def write_report(args, cfg, records, results, stats, wall, od) -> None:
    S = collect_stats(cfg, records, results)
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
    for r in results.values():
        u = summarize_usage(r.get("attempts_detail") or [])
        for k in total:
            total[k] += u[k]
    n = len(records)
    hist = Counter(len(r.get("attempts_detail") or []) for r in results.values())
    calls_in_artifacts, model_elapsed = artifact_call_stats(results)
    retry_items = S["items_with_rounds_gt1"]
    qrate = (S["quote_located"] / S["quote_total"] * 100) if S["quote_total"] else 0.0
    L = []
    add = L.append
    add("# 自动标注报告（第 6 阶段抽取评测集 v2.1）")
    add("")
    add("> %s" % (TRUTH_SOURCE_NOTE % (ANNOTATE_MODEL, PROMPT_VERSION, TEMPERATURE)))
    add(">")
    add("> 第 6 阶段交付文件 `dev.jsonl`／`test.jsonl` 的**槽位仍为空**（《15》第八节 的冻结契约）；")
    add("> 本报告与全部自动标注产物落在独立目录 `阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\自动标注\\`。")
    add("> 第 10 阶段引用下面任何指标时，只能写成「**模型参照下的抽取表现**」，")
    add("> **不得**写成「人工金标准下的准确率」。")
    add("")
    add("## 一、运行概况")
    add("")
    add("| 项 | 值 |")
    add("| --- | --- |")
    add("| 模型（请求） | `%s` |" % ANNOTATE_MODEL)
    add("| 模型（响应解析值） | %s |" % "、".join("`%s`" % m for m in sorted(
        {r.get("model_resolved") for r in results.values()})))
    add("| 抽取器模型（对照，两者不同以降低同源自证） | `%s` |" % cfg.LLM["model_default"])
    add("| Prompt 版本 | `%s` |" % PROMPT_VERSION)
    add("| temperature ／ max_tokens | %d ／ %d |" % (TEMPERATURE, MAX_TOKENS))
    add("| 校验重写轮数上限 max_rounds | %d |" % MAX_ROUNDS)
    add("| 条目数 | %d |" % n)
    add("| API 调用次数（本次运行**新增**） | %d（其中传输层重试 %d 次） |"
        % (stats["api_calls"], stats["transport_retries"]))
    add("| API 调用次数（**产物合计**，含历次首跑与重试轮） | %d |" % calls_in_artifacts)
    add("| 缓存命中 | %d |" % stats["cache_hits"])
    add("| 墙钟 | %.1f 秒（%.1f 分钟） |" % (wall, wall / 60.0))
    add("| 模型耗时合计（各次调用的 elapsed 之和） | %.1f 秒（%.1f 分钟） |"
        % (model_elapsed, model_elapsed / 60.0))
    add("| token 合计 | prompt %d ／ completion %d ／ reasoning %d ／ total %d |"
        % (total["prompt_tokens"], total["completion_tokens"], total["reasoning_tokens"],
           total["total_tokens"]))
    add("| 校验重试（用到 >1 轮的条目） | %d／%d（%.1f%%） |" % (retry_items, n, retry_items / n * 100))
    add("| 重试轮次分布 | %s |" % "｜".join("%d 轮 %d 条" % (k, v) for k, v in sorted(hist.items())))
    add("| 整块无事实（`empty_but_checked`） | %d 条 |" % S["empty_but_checked"])
    add("| 触发了「机械剔除」的条目 | %d／%d |" % (S["items_with_drops"], n))
    add("")
    add("> %s" % PARAMS_SCOPE_NOTE)
    add("")
    add("## 二、标注条目统计")
    add("")
    add("| 槽位 | 条数 |")
    add("| --- | --- |")
    add("| 实体 entities | %d |" % sum(S["entities"].values()))
    add("| 事件 events | %d |" % sum(S["events"].values()))
    add("| 关系 relations | %d |" % sum(S["relations"].values()))
    add("| 时间 times | %d |" % S["times"])
    add("| 本体边界登记 | %d |" % S["oblog"])
    add("")
    add("### 2.1 实体类型分布（5 类）")
    add("")
    add("| entity_type | 条数 |")
    add("| --- | --- |")
    for et in cfg.ENTITY_TYPES_FROM_MODEL:
        add("| %s | %d |" % (et, S["entities"].get(et, 0)))
    add("")
    add("### 2.2 事件类型分布（8 种）")
    add("")
    add("| event_type | 条数 |")
    add("| --- | --- |")
    for et in cfg.EVENT_TYPES:
        add("| %s | %d |" % (et, S["events"].get(et, 0)))
    add("")
    add("### 2.3 关系分布（9 条）")
    add("")
    add("| relation | 条数 |")
    add("| --- | --- |")
    for r in cfg.RELATIONS:
        add("| %s | %d |" % (r, S["relations"].get(r, 0)))
    add("")
    add("> `EVIDENCED_BY` 恒为 0 属正常（协议：不标注，由程序按 `doc_id` 生成）。")
    add("")
    add("### 2.4 `quote` 逐字可定位率")
    add("")
    add("去空白后是**本条 `text` 的精确子串**的 quote 比例（口径同 `config.EVIDENCE`）："
        "**%d／%d ＝ %.2f%%**。" % (S["quote_located"], S["quote_total"], qrate))
    add("")
    add("## 三、被迫猜测的字段清单")
    add("")
    add("**这一节是判断「要不要放宽自动标注 schema」的依据。**")
    add("口径：逐字段看**校验器要求必填**（`工具\\标注助手.py` 的 `ENTITY_PER_TYPE_FIELDS`，"
        "与 `标注说明.md` 第3.1节 同源）的实体属性，模型实际给出的取值在正文里的支撑程度：")
    add("")
    add("* `本块有`：取值（去空白后）在本条 `text` 里出现——**有本块证据**；")
    add("* `只在文档全文里（本块无支撑）`：只在本条 `doc_text` 里出现——事实可判定，但证据不在本块；")
    add("* `正文里完全没有（纯推测）`：本块与全文都找不到——**只能编**；")
    add("* `空值`：模型如实写了空串／空列表（**没有编**，但字段没填）。")
    add("")
    add("| entity_type | 必填字段 | 本块有 | 只在文档全文里 | 正文里完全没有（纯推测） | 空值 | 合计 |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for (et, fname), c in S["field_support"].items():
        tot = sum(c.values())
        add("| %s | `%s` | %d | %d | %d | %d | %d |" % (
            et, fname, c.get("本块有", 0), c.get("只在文档全文里（本块无支撑）", 0),
            c.get("正文里完全没有（纯推测）", 0), c.get("空值", 0), tot))
    add("")
    add("**逐字段的受影响条数（按「出现非空取值、但本块无支撑」＝ `只在文档全文里` ＋ `正文里完全没有` 统计）**：")
    add("")
    add("| entity_type | 必填字段 | 非空但本块无支撑的条数 | 其中正文里完全没有 |")
    add("| --- | --- | --- | --- |")
    for (et, fname), c in S["field_support"].items():
        affected = c.get("只在文档全文里（本块无支撑）", 0) + c.get("正文里完全没有（纯推测）", 0)
        add("| %s | `%s` | %d | %d |" % (et, fname, affected, c.get("正文里完全没有（纯推测）", 0)))
    add("")
    add("## 四、兜底动作（校验不收敛时做了什么）")
    add("")
    add("全部动作**只删不造**：三轮重写后仍不合口径的**具体条目**被剔除、必填的键缺失时补"
        "「无法给出取值」的空值（空串／空列表）；**没有放宽任何校验规则**，也没有编造取值。"
        "每一次动作都写进了该条的 `notes` 与 `自动标注台账.json` 的 `dropped` 字段。")
    add("")
    if S["dropped_total"]:
        add("| 槽位 | 兜底动作次数 |")
        add("| --- | --- |")
        for slot, cnt in S["dropped_total"].items():
            add("| %s | %d |" % (slot, cnt))
        add("")
        add("> 逐条明细见台账 `items[*].dropped`（每条记的是「做了什么、为什么」）。")
    else:
        add("**本次没有任何兜底动作。**")
    add("")
    add("## 五、限制（如实登记，不淡化）")
    add("")
    add("1. **这不是人工金标准**，是模型参照集：`status = auto_annotated`，带 `provenance` 块。")
    add("2. **同源偏差被降低但没有消除**：标注模型 `%s` 与抽取器 `%s` 不是同一个模型，"
        "但都来自同一端点、同一个模型家族；两者对「什么算一条事件」「哪些字段该怎么填」的偏好可能同向。"
        % (ANNOTATE_MODEL, cfg.LLM["model_default"]))
    add("3. **未逐条人工复核**：本次没有做任何人工抽检，所有数字都是模型的产出，不是核对过的结论。")
    add("4. **被迫猜测的字段**见第三节：校验器要求必填、而正文撑不住的属性，模型只能填或留空。")
    add("5. **第 6 阶段交付文件的槽位仍为空**（冻结契约）；自动标注不写回，`merge` 也拒绝写回"
        "（`merge_refuses_auto`）。")
    add("")
    add("---")
    add("")
    add("生成时间：%s｜脚本：`代码\\抽取与图谱\\auto_annotate.py`｜Prompt 版本：`%s`"
        % (now_iso(), PROMPT_VERSION))
    add("")
    write_text_atomic(os.path.join(od, "自动标注报告.md"), "\n".join(L))


# --------------------------------------------------------------------------
# 7. 缓存键自检（S1：改了输入 → 键必须变）
# --------------------------------------------------------------------------
def _fingerprint_with(rec, problems=None, **overrides) -> str:
    """临时覆盖模块级参数（模型／temperature／max_tokens／提示词）后算一次指纹，用完还原。"""
    saved = {k: globals()[k] for k in overrides}
    globals().update(overrides)
    try:
        return input_fingerprint(rec, problems)
    finally:
        globals().update(saved)


def cmd_selftest(args) -> int:
    """缓存键自检（不调模型）：逐项证明「输入变了，`input_sha256` 一定变」。

    覆盖：①条目全部抽样字段（逐字段试：text／doc_text／title／category／publish_time／
    company_list／subject_companies／sampling／chunk_id／item_id）②Prompt 模板（系统提示词、
    schema 渲染）③`config.ontology_definitions_digest()` ④模型 ⑤temperature，
    另含 max_tokens、Prompt 版本与回喂问题清单；另证「同输入两次 → 同键」。
    """
    cfg = handann._load_config()
    base_rec = OrderedDict([
        ("item_id", "SELFTEST-001"), ("split", "dev"), ("category", "公告"),
        ("publish_time", "2026-09-01 08:00:00"), ("month", "2026-09"),
        ("title", "自检用标题（不参与任何真实标注）"),
        ("chunk_id", "CHK-SELFTEST-1"), ("doc_id", "DOC-SELFTEST-1"),
        ("chunk_index", 0), ("chunk_count_in_doc", 1), ("token_count", 120),
        ("company_list", ["000001", "000002"]), ("subject_companies", ["000001"]),
        ("text", "甲公司于2026年9月1日与乙公司签署重大合同，合同金额一亿元。" * 2),
        ("doc_text", "甲公司与乙公司签署重大合同。公司代码 000001。"),
        ("sampling", {"layer": "selftest", "block": 1}),
    ])
    base = input_fingerprint(base_rec, None)
    checks = []
    checks.append(("同输入两次 → 键相同（确定性）", input_fingerprint(base_rec, None) == base))

    def _case(label, mutate, **overrides):
        rec = OrderedDict(base_rec)
        for key, value in mutate.items():
            rec[key] = value
        checks.append((label, _fingerprint_with(rec, None, **overrides) != base))

    _case("① text 改一处 → 键变", {"text": base_rec["text"] + "（补一句）"})
    _case("① doc_text 改一处 → 键变", {"doc_text": base_rec["doc_text"] + "（补一句）"})
    _case("① title 改一处 → 键变", {"title": "另一个标题"})
    _case("① category 改一处 → 键变", {"category": "财经新闻"})
    _case("① publish_time 改一处 → 键变", {"publish_time": "2026-09-02 08:00:00"})
    _case("① company_list 改一处 → 键变", {"company_list": ["000001", "000003"]})
    _case("① subject_companies 改一处 → 键变", {"subject_companies": []})
    _case("① sampling 改一处 → 键变", {"sampling": {"layer": "selftest", "block": 2}})
    _case("① chunk_id 改一处 → 键变", {"chunk_id": "CHK-SELFTEST-2"})
    _case("① item_id 改一处 → 键变", {"item_id": "SELFTEST-002"})
    _case("① 新增未知抽样字段 → 键变", {"extra_sampling_field": "x"})
    checks.append(("② 系统提示词改一处 → 键变",
                   _fingerprint_with(base_rec, None, SYSTEM_PROMPT=SYSTEM_PROMPT + "\n（自检改动）") != base))
    checks.append(("② schema 模板改一处 → 键变",
                   _fingerprint_with(base_rec, None,
                                     SCHEMA_TEMPLATE=SCHEMA_TEMPLATE + "\n（自检改动）") != base))
    checks.append(("② Prompt 版本改一处 → 键变",
                   _fingerprint_with(base_rec, None, PROMPT_VERSION=PROMPT_VERSION + ".selftest") != base))

    # ③ 本体定义：改一处定义文本 → digest 必须变、缓存键必须跟着变
    digest_before = config.ontology_definitions_digest()
    orig_defs_text = config.ontology_definitions_text
    config.ontology_definitions_text = lambda: orig_defs_text() + "\n【自检】边界规则：本条为自检新增。"
    try:
        digest_after = config.ontology_definitions_digest()
        fp_after = input_fingerprint(base_rec, None)
    finally:
        config.ontology_definitions_text = orig_defs_text
    checks.append(("③ 本体定义改一处 → ontology_definitions_digest() 变", digest_after != digest_before))
    checks.append(("③ 本体定义改一处 → 缓存键变", fp_after != base))
    checks.append(("③ 本体定义还原 → digest 复原", config.ontology_definitions_digest() == digest_before))

    checks.append(("④ 模型改一处 → 键变",
                   _fingerprint_with(base_rec, None, ANNOTATE_MODEL=ANNOTATE_MODEL + "-x") != base))
    checks.append(("⑤ temperature 改一处 → 键变",
                   _fingerprint_with(base_rec, None, TEMPERATURE=TEMPERATURE + 0.7) != base))
    checks.append(("max_tokens 改一处 → 键变",
                   _fingerprint_with(base_rec, None, MAX_TOKENS=MAX_TOKENS * 2) != base))
    checks.append(("回喂的问题清单改一处 → 键变",
                   input_fingerprint(base_rec, [{"field": "entities[0].quote",
                                                 "kind": "quote_not_in_text",
                                                 "message": "自检用例"}]) != base))

    print("缓存键自检（不调模型）：基准 input_sha256=%s" % base)
    print("  本体定义 digest：改前 %s｜改后 %s" % (digest_before[:16] + "…", digest_after[:16] + "…"))
    failed = 0
    for i, (label, ok) in enumerate(checks, 1):
        print("  [%s] %2d. %s" % ("OK" if ok else "FAIL", i, label))
        failed += 0 if ok else 1
    print("缓存键自检：%d／%d 通过%s"
          % (len(checks) - failed, len(checks), "（退出码 0）" if not failed else "（退出码 1）"))
    return 1 if failed else 0


# --------------------------------------------------------------------------
# 8. CLI
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="auto_annotate.py",
        description="第 6 阶段抽取评测集 v2.1 的**模型自动标注**管线（模型参照集，不是人工金标准）。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", nargs="?", default="run", choices=["run", "selftest"],
                   help="run（默认）：跑自动标注；selftest：缓存键自检（不调模型，退出码 0／1）")
    p.add_argument("--split", default="all", choices=["all", "dev", "test"], help="只跑某个 split")
    p.add_argument("--limit", type=int, default=0, help="只跑前 N 条（试跑用；0 = 全部）")
    p.add_argument("--workers", type=int, default=4, help="并发度（默认 4；1 = 串行）")
    p.add_argument("--force", action="store_true", help="忽略已有缓存，重新调用并重写缓存")
    p.add_argument("--replay", action="store_true", help="只从缓存重放，**0 次调用**")
    return p


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    if args.command == "selftest":
        return cmd_selftest(args)
    if args.replay and args.force:
        raise SystemExit("--replay 与 --force 互斥")
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
