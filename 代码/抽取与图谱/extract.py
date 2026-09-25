# -*- coding: utf-8 -*-
r"""extract.py —— 第 6 阶段「实体与事件抽取」的可执行脚本（T1 小规模试跑入口）。

口径（照《15-第6阶段任务书》第五节 硬约束 3、4、7、8、10、18 与 第六节 的格式决策）：

* **以文档为上下文、以文本块为证据单位**：一篇文档一次调用，事件不被块边界切断；
  每条事实的 `source_chunk_id` 由代码在该文档的文本块序列里定位得到。
* **证据由代码解析，不由模型给编号**：模型对每一条实体／事件／关系必须给逐字引用
  `quote`，代码只做「折空白 + 精确子串」匹配；定位不到就整条丢弃并登记原因。
* **缓存可重放**：原始返回按 `doc_id` 一篇一个文件落在 `config.CACHE_DIR`
  （与数据集版本目录同级、不入仓库）；缓存命中时**不调用模型**，产物由缓存确定性重算，
  因此能逐字节复现。
* **密钥只从环境变量读**（`config.api_key()`），不入仓库、不落盘、不进日志。

用法（全部参数取自 `代码\抽取与图谱\config.py`）：

    python 代码\抽取与图谱\extract.py --select-only     # 只算选样与覆盖性重算，不调模型
    python 代码\抽取与图谱\extract.py                   # T1：试跑 12 篇（默认 --profile pilot）
    python 代码\抽取与图谱\extract.py --limit 3         # 只跑选样结果的前 3 篇
    python 代码\抽取与图谱\extract.py --docs 1026,1018  # 只跑指定 doc_id
    python 代码\抽取与图谱\extract.py --force           # 忽略已有缓存，重新调用并重写缓存
    python 代码\抽取与图谱\extract.py --verify          # 独立核对既有产物（不调用模型）
    python 代码\抽取与图谱\extract.py --profile v21     # 全量 709 篇（T3 的口径，T1 不执行）

退出码 0 表示成功；密钥未就位、选样断言不成立、缓存与当前输入不一致（且未 `--force`）
等情形一律非零退出（《15》第十一节 的阻断项不得静默降级）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402

# --------------------------------------------------------------------------
# 提示词（与 `LLM.prompt_version` 绑定：改这里的任何一个字，必须同步升版本号）
# --------------------------------------------------------------------------
# `<<...>>` 占位符在 `render_user_prompt()` 里替换；枚举一律从 config 注入，
# 脚本内不重复写字面量（硬约束 18）。
SYSTEM_PROMPT = (
    "你是 A 股财经信息的事件抽取器。你只输出一个 JSON 对象，不输出解释、"
    "不输出 Markdown 代码块、不输出多余字段。\n"
    "你必须严格遵守给定的字段名与枚举，枚举之外的取值一律不要输出。\n"
    "每一条实体、事件、关系都必须给出【原文逐字引用】quote：quote 必须是从【正文】里"
    "连续复制的一段文字，不得改写、不得拼接、不得省略中间字符、不得引用标题。\n"
    "quote 要连标点一起照抄（书名号、引号、括号、% 都照抄），不要补字也不要删字；"
    "如果一段话跨行，就改选一段更完整的短句——凭记忆重写一定会被程序判为无法定位。\n"
    "实体 name 同样必须是正文里连续出现的写法：正文只写简称就写简称，"
    "不要补全成公司全称、不要缩写、不要改标点。\n"
    "时间只写正文能确定到「日」的日期；不能确定到日时写 null，绝不猜测、绝不用发布时间顶替。\n"
    "只抽正文明确写出的事实：不得用常识补全，不得把行业通稿里顺带提到的公司当成事件主体。"
)

USER_TEMPLATE = """【文档元信息】
doc_id: <<DOC_ID>>
category: <<CATEGORY>>
source: <<SOURCE>>
publish_time: <<PUBLISH_TIME>>
title: <<TITLE>>

【正文】
<<CONTENT>>

【只输出下面这一个 JSON 对象，字段名照抄】
{
  "entities": [
    {"name": "实体在正文里的写法", "type": "<<ENTITY_TYPES>>",
     "quote": "正文逐字引用，必须包含 name"}
  ],
  "events": [
    {"event_type": "<<EVENT_TYPES>>", "event_name": "一句话事件名",
     "event_time": "YYYY-MM-DD 或 null", "description": "一句话事件经过",
     "confidence": 0.9, "quote": "正文逐字引用"}
  ],
  "relations": [
    {"relation": "<<MODEL_RELATIONS>>",
     "head": "entities 里的 name，或事件引用 E1", "head_type": "<<HEAD_TAIL_TYPES>>",
     "tail": "entities 里的 name，或事件引用 E1", "tail_type": "<<HEAD_TAIL_TYPES>>",
     "role": "<<ROLES>>（只有 PARTICIPATES_IN 写这个字段）",
     "valid_from": "YYYY-MM-DD 或 null（只有 BELONGS_TO 写这个字段）",
     "valid_to": "YYYY-MM-DD 或 null（只有 BELONGS_TO 写这个字段）",
     "confidence": 0.9, "quote": "正文逐字引用"}
  ]
}

【规则】
1. entities 只输出这 5 类：<<ENTITY_TYPES>>。Event 不在这里输出——事件由 events 数组给出；
   Policy（政策）在这里输出。同一实体只输出一次，name 用正文里的写法；最多 <<MAX_ENTITIES>> 条。
2. events 按正文出现顺序排列，依次记作 E1、E2……relations 里用 E1 这样的引用指事件；
   最多 <<MAX_EVENTS>> 条。event_type 只能取 <<EVENT_TYPES>>。
3. relations 只输出这 8 类：<<MODEL_RELATIONS>>。EVIDENCED_BY 不要输出（由程序按 doc_id 生成）。
   端点类型必须符合：<<RELATION_SCHEMA_NOTE>>
   - head／tail 写 entities 里的 name，或写事件引用 E1；不得出现其他取值。
   - 每条事件至少要有 1 条 PARTICIPATES_IN；事件主体（公司／人物／机构）用 role=主体。
   - ISSUED_BY 只用于 event_type 为「政策」或「监管」的事件，终点必须是 Institution；
     同一机构既是发布／作出方又参与该事件时只写 ISSUED_BY，不要再写 PARTICIPATES_IN。
   - role 只取 <<ROLES>>；「监管方」只用于参与事件但不是发布／作出方的机构。
   - 只有正文明确写出时才输出 SUPPLIES／CUSTOMER_OF／COMPETES_WITH／HAS_EXECUTIVE／BELONGS_TO；
     没有就留空数组。最多 <<MAX_RELATIONS>> 条。
4. quote 必须来自【正文】、逐字连续、长度 12～200 字；引用标题或改写过的文字会被程序
   判为无法定位并整条丢弃。建议 20～80 字、选一句完整的话；照抄时连标点一起抄。
5. event_time 只在正文写明到「日」时填写（「2026年8月15日」或「2026-08-15」都可以）；
   只写到月、或需要靠推断的，一律写 null。valid_from／valid_to 只在正文给出明确日期时填写。
6. 没有把握的条目一律不要输出——本任务宁可少抽，不可编造。
7. 输出要紧凑：事件描述限一句话，不要复述本提示词，不要输出解释或推理过程。"""

# 压缩重试专用指令：**只在主尝试被输出上限截断时**追加一次，两次原始返回都进缓存。
COMPACT_INSTRUCTION = """

【本次为压缩重试；上一次返回被输出上限截断】
请大幅压缩输出：只保留最重要的事件（最多 <<COMPACT_EVENTS>> 条）、直接参与这些事件的实体
（最多 <<COMPACT_ENTITIES>> 条）与关系（最多 <<COMPACT_RELATIONS>> 条）；每条 quote 控制在
12～<<COMPACT_QUOTE_MAX>> 字以内；不确定的一律不输出。字段名与枚举同上，仍然只输出一个 JSON 对象。"""

PROMPT_TEMPLATE_SHA256 = config.sha256_hex(SYSTEM_PROMPT + "\n===USER===\n" + USER_TEMPLATE)


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def normalize_ws(text) -> str:
    """只折空白：把连续空白（含换行、全角空格）折成单个半角空格并去首尾空白。"""
    return re.sub(r"[\s\u3000]+", " ", str(text or "")).strip()


def evidence_key(text) -> str:
    """证据比对用的键：**去掉全部空白**（含全角空格），其余字符一律照原样。

    只归一空白，不做大小写、标点或模糊匹配——来源 PDF 里存在词内空格
    （doc_id 1018 的正文写作「公 司将」），折成单空格会把合法引用误判为无法定位，
    故比对键去掉所有空白。见 `config.EVIDENCE["normalize"]`。
    """
    return re.sub(r"[\s\u3000]+", "", str(text or ""))


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dump_json(path, obj, indent=2):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def dump_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
             for r in rows]
    text = ("\n".join(lines) + "\n") if lines else ""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


# --------------------------------------------------------------------------
# 选样（确定性；覆盖 8 种事件类型与 4 个类目）
# --------------------------------------------------------------------------
def event_type_hits(doc, event_type):
    """返回 None（未命中）／"title"／"title+body"（冻结代理指标，见 config）。"""
    title = str(doc.get("title") or "")
    body = str(doc.get("content") or "")
    pattern = config.EVENT_TYPE_TITLE_PATTERNS[event_type]
    if not re.search(pattern, title):
        return None
    if event_type == "产品" and re.search(config.PRODUCT_EXCLUDE_PATTERN, title):
        return None
    return "title+body" if re.search(pattern, body) else "title"


def select_pilot_docs(docs):
    """按 config.PILOT 的确定性规则选出试跑文档，返回 [(doc, reason), ...]。

    规则（三阶段，全部按 doc_id 升序确定次序）：
      A 事件类型覆盖：本体固定顺序逐个事件类型取候选，优先其「沉淀类目」，
        同一事件类型内「正文也命中」优先、再按 doc_id；类目配额用尽则跨类目回退。
      B 类目补齐：按类目顺序把配额补满，优先「标题命中某事件类型且正文 ≥ min_doc_chars」
        的候选（避免只抽到一行快讯），其次命中事件类型的，最后该类目里最小的 doc_id。
      C 兜底：不足 doc_count 时按 doc_id 升序补足（会在断言里暴露是否发生）。
    """
    spec = config.PILOT
    candidates = {et: [d for d in docs if event_type_hits(d, et)]
                  for et in spec["event_type_order"]}
    quota = dict(spec["category_quota"])
    chosen, reasons = [], {}

    for et in spec["event_type_order"]:
        pool = candidates[et]
        preferred = spec["preferred_category"][et]
        pref_pool = [d for d in pool if d["category"] == preferred and d["doc_id"] not in reasons]
        other_pool = [d for d in pool if d["category"] != preferred and d["doc_id"] not in reasons]
        picked = None
        for candidate_pool, tag in ((pref_pool, "首选类目"), (other_pool, "跨类目回退")):
            usable = [d for d in candidate_pool if quota.get(d["category"], 0) > 0]
            if usable:
                usable.sort(key=lambda d: (0 if event_type_hits(d, et) == "title+body" else 1,
                                           d["doc_id"]))
                picked = (usable[0], tag)
                break
        if picked is None:
            continue
        doc, tag = picked
        quota[doc["category"]] -= 1
        chosen.append(doc)
        reasons[doc["doc_id"]] = "覆盖事件类型 %s（%s；标题级冻结代理命中）" % (et, tag)

    for cat in spec["category_order"]:
        while quota.get(cat, 0) > 0:
            pool = [d for d in docs if d["category"] == cat and d["doc_id"] not in reasons]
            rich = [d for d in pool
                    if len(str(d.get("content") or "")) >= spec["min_doc_chars"]
                    and any(event_type_hits(d, et) for et in spec["event_type_order"])]
            hit = [d for d in pool if any(event_type_hits(d, et) for et in spec["event_type_order"])]
            pick_from = rich or hit or pool
            if not pick_from:
                print("[选样] 类目 %s 的候选耗尽，配额未满" % cat)
                break
            doc = sorted(pick_from, key=lambda d: d["doc_id"])[0]
            quota[cat] -= 1
            chosen.append(doc)
            ets = [et for et in spec["event_type_order"] if event_type_hits(doc, et)]
            tier = "命中事件类型且正文充足" if doc in rich else (
                "命中事件类型" if doc in hit else "类目内兜底")
            reasons[doc["doc_id"]] = "补足类目 %s（%s%s）" % (
                cat, tier, ("；标题命中 " + "/".join(ets)) if ets else "")

    while len(chosen) < spec["doc_count"]:
        pool = sorted([d for d in docs if d["doc_id"] not in reasons], key=lambda d: d["doc_id"])
        if not pool:
            break
        doc = pool[0]
        chosen.append(doc)
        reasons[doc["doc_id"]] = "兜底补足篇数（前两阶段不足 doc_count）"

    chosen.sort(key=lambda d: d["doc_id"])
    return [(d, reasons[d["doc_id"]]) for d in chosen]


def check_selection(selection):
    """选样断言：篇数、doc_id 唯一、4 个类目、8 种事件类型。返回问题清单。"""
    spec = config.PILOT
    problems = []
    if len(selection) != spec["doc_count"]:
        problems.append("选出 %d 篇，应为 %d 篇" % (len(selection), spec["doc_count"]))
    ids = [d["doc_id"] for d, _ in selection]
    if len(set(ids)) != len(ids):
        problems.append("doc_id 有重复：%s" % ids)
    cats = {d["category"] for d, _ in selection}
    for cat in spec["category_order"]:
        if cat not in cats:
            problems.append("类目缺失：%s" % cat)
    for et in spec["event_type_order"]:
        if not any(event_type_hits(d, et) for d, _ in selection):
            problems.append("事件类型缺失（标题级代理）：%s" % et)
    return problems


def compute_coverage(docs, chunks):
    """重算《15》表 15-C／15-D／15-E（T1 的「覆盖性重算」），并与声明值比对。"""
    per_doc_chunks = {}
    for chunk in chunks:
        per_doc_chunks[chunk["doc_id"]] = per_doc_chunks.get(chunk["doc_id"], 0) + 1
    table_c = {
        "company_list_ge2": sum(1 for d in docs if len(d.get("company_list") or []) >= 2),
        "subject_companies_ge2": sum(1 for d in docs if len(d.get("subject_companies") or []) >= 2),
    }
    doc_title_hits = {et: [d for d in docs if event_type_hits(d, et)] for et in config.EVENT_TYPES}
    table_d = {
        "公告标题级": {et: sum(1 for d in doc_title_hits[et] if d["category"] == "公告")
                   for et in config.EVENT_TYPES},
        "公告外监管标题级": sum(1 for d in doc_title_hits["监管"] if d["category"] != "公告"),
        "正文级": {},
    }
    for rel in config.RELATIONS:
        pattern = config.RELATION_BODY_PATTERNS.get(rel)
        if not pattern:
            continue
        table_d["正文级"][rel] = sum(
            1 for d in docs if re.search(pattern, str(d.get("content") or "")))
    total_chunks = len(chunks)
    table_e = {}
    for cat in config.PILOT["category_order"]:
        n_docs = sum(1 for d in docs if d["category"] == cat)
        n_chunks = sum(per_doc_chunks.get(d["doc_id"], 0) for d in docs if d["category"] == cat)
        table_e[cat] = {
            "docs": n_docs,
            "chunks": n_chunks,
            "chunk_share": round(n_chunks / total_chunks, 4) if total_chunks else 0.0,
            "chunks_per_doc": round(n_chunks / n_docs, 2) if n_docs else 0.0,
        }
    table_e["合计"] = {
        "docs": len(docs), "chunks": total_chunks, "chunk_share": 1.0,
        "chunks_per_doc": round(total_chunks / len(docs), 2) if docs else 0.0,
    }
    declared = config.TASK_BOOK_TABLES
    diffs, rounding_notes = [], []
    for key, value in declared["table_15C"].items():
        if table_c.get(key) != value:
            diffs.append("表15-C %s：重算 %s ≠ 声明 %s" % (key, table_c.get(key), value))
    for et, value in declared["table_15D"]["公告标题级"].items():
        if table_d["公告标题级"].get(et) != value:
            diffs.append("表15-D 公告标题级 %s：重算 %s ≠ 声明 %s"
                         % (et, table_d["公告标题级"].get(et), value))
    if table_d["公告外监管标题级"] != declared["table_15D"]["公告外监管标题级"]:
        diffs.append("表15-D 公告外监管：重算 %s ≠ 声明 %s"
                     % (table_d["公告外监管标题级"], declared["table_15D"]["公告外监管标题级"]))
    for rel, value in declared["table_15D"]["正文级"].items():
        if table_d["正文级"].get(rel) != value:
            diffs.append("表15-D 正文级 %s：重算 %s ≠ 声明 %s"
                         % (rel, table_d["正文级"].get(rel), value))
    for cat, value in declared["table_15E"].items():
        got = table_e.get(cat, {})
        for field in ("docs", "chunks"):
            if got.get(field) != value[field]:
                diffs.append("表15-E %s.%s：重算 %s ≠ 声明 %s"
                             % (cat, field, got.get(field), value[field]))
        share_gap = abs(float(got.get("chunk_share", 0)) - float(value["chunk_share"]))
        if share_gap > 0.0011:      # 声明值只保留到 3 位小数，容差按 0.001 量级取
            diffs.append("表15-E %s.chunk_share：重算 %s ≠ 声明 %s"
                         % (cat, got.get("chunk_share"), value["chunk_share"]))
        elif share_gap > 0:
            rounding_notes.append("表15-E %s.chunk_share：重算 %s（%s/%s）与声明 %s 相差 %.4f，"
                                  "属声明侧保留位数造成的舍入差，篇数与块数完全一致"
                                  % (cat, got.get("chunk_share"), got.get("chunks"),
                                     table_e["合计"]["chunks"], value["chunk_share"], share_gap))
        if abs(float(got.get("chunks_per_doc", 0)) - float(value["chunks_per_doc"])) > 0.005:
            diffs.append("表15-E %s.chunks_per_doc：重算 %s ≠ 声明 %s"
                         % (cat, got.get("chunks_per_doc"), value["chunks_per_doc"]))
    return {
        "dataset_version": config.DATASET_VERSION,
        "doc_count": len(docs),
        "chunk_count": len(chunks),
        "table_15C": table_c,
        "table_15D": table_d,
        "table_15E": table_e,
        "declared_values": declared,
        "differs_from_declared": diffs,
        "rounding_notes": rounding_notes,
        "matches_declared": not diffs,
        "note": "代理指标（标题级／正文级关键词命中），不是抽取结果；一篇可命中多类。",
    }


# --------------------------------------------------------------------------
# 提示词渲染与输入指纹
# --------------------------------------------------------------------------
def relation_schema_note() -> str:
    parts = []
    for rel in config.RELATIONS:
        schema = config.RELATION_SCHEMA[rel]
        if not schema["from_model"]:
            continue
        extra = ("，另带 " + "、".join(schema["extra_attrs"])) if schema["extra_attrs"] else ""
        parts.append("%s %s→%s%s" % (rel, "|".join(schema["domain"]),
                                     "|".join(schema["range"]), extra))
    return "；".join(parts)


def render_user_prompt(doc, compact=False) -> str:
    limits = config.LLM["fallback"]["compact_limits"] if compact else config.EXTRACT_LIMITS
    text = USER_TEMPLATE
    for key, value in (
        ("<<DOC_ID>>", str(doc.get("doc_id"))),
        ("<<CATEGORY>>", str(doc.get("category") or "")),
        ("<<SOURCE>>", str(doc.get("source") or "")),
        ("<<PUBLISH_TIME>>", str(doc.get("publish_time") or "")),
        ("<<TITLE>>", str(doc.get("title") or "")),
        ("<<CONTENT>>", str(doc.get("content") or "")),
        ("<<ENTITY_TYPES>>", "|".join(config.ENTITY_TYPES_FROM_MODEL)),
        ("<<EVENT_TYPES>>", "|".join(config.EVENT_TYPES)),
        ("<<MODEL_RELATIONS>>", "|".join(config.RELATIONS_FROM_MODEL)),
        ("<<HEAD_TAIL_TYPES>>", "|".join(config.ENTITY_TYPES)),
        ("<<ROLES>>", "|".join(config.ROLES)),
        ("<<RELATION_SCHEMA_NOTE>>", relation_schema_note()),
        ("<<MAX_ENTITIES>>", str(limits["entities"])),
        ("<<MAX_EVENTS>>", str(limits["events"])),
        ("<<MAX_RELATIONS>>", str(limits["relations"])),
    ):
        text = text.replace(key, value)
    if compact:
        compact_limits = config.LLM["fallback"]["compact_limits"]
        text += (COMPACT_INSTRUCTION
                 .replace("<<COMPACT_EVENTS>>", str(compact_limits["events"]))
                 .replace("<<COMPACT_ENTITIES>>", str(compact_limits["entities"]))
                 .replace("<<COMPACT_RELATIONS>>", str(compact_limits["relations"]))
                 .replace("<<COMPACT_QUOTE_MAX>>", str(compact_limits["quote_max_chars"])))
    return text


def build_messages(doc, compact=False):
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": render_user_prompt(doc, compact=compact)}]


def input_sha256(doc, compact=False) -> str:
    """输入指纹：文档字段 + 提示词 + 模型与调用参数 + Prompt 版本，全部进哈希。"""
    limits = config.LLM["fallback"]["compact_limits"] if compact else config.EXTRACT_LIMITS
    payload = {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "content": doc.get("content"),
        "content_sha256_16": doc.get("content_sha256_16"),
        "publish_time": doc.get("publish_time"),
        "category": doc.get("category"),
        "source": doc.get("source"),
        "prompt_version": config.LLM["prompt_version"],
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
        "model_requested": config.model_requested(),
        "temperature": config.LLM["temperature"],
        "max_tokens": (config.LLM["fallback"]["max_tokens"] if compact
                       else config.LLM["max_tokens"]),
        "response_format": config.LLM["response_format"],
        "compact_retry": bool(compact),
        "reasoning_effort": (config.LLM["fallback"]["reasoning_effort"] if compact else None),
        "entity_types": config.ENTITY_TYPES_FROM_MODEL,
        "event_types": config.EVENT_TYPES,
        "roles": config.ROLES,
        "relations_from_model": config.RELATIONS_FROM_MODEL,
        "extract_limits": limits,
    }
    return config.sha256_hex(config.stable_json(payload))


def cache_path(doc_id) -> str:
    return os.path.join(config.CACHE_DIR, "%s.json" % doc_id)


# --------------------------------------------------------------------------
# 模型调用（带限流与退避；客户端惰性构造，缓存全命中时不需要密钥也不需要网络）
# --------------------------------------------------------------------------
_LAST_CALL_TS = [0.0]


def _retryable(exc, openai_mod):
    if isinstance(exc, (openai_mod.APIConnectionError, openai_mod.APITimeoutError,
                        openai_mod.RateLimitError)):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def _invoke(client, openai_mod, doc, stats, compact):
    """发一次请求（含传输层退避重试），返回该次尝试的明细。"""
    limits = config.LLM["fallback"]["compact_limits"] if compact else config.EXTRACT_LIMITS
    kwargs = {
        "model": config.model_requested(),
        "messages": build_messages(doc, compact=compact),
        "temperature": config.LLM["temperature"],
        "max_tokens": (config.LLM["fallback"]["max_tokens"] if compact
                       else config.LLM["max_tokens"]),
        "response_format": {"type": config.LLM["response_format"]},
    }
    if compact:
        kwargs["reasoning_effort"] = config.LLM["fallback"]["reasoning_effort"]
    wait = max(0.0, config.PACING["min_interval_seconds"] - (time.time() - _LAST_CALL_TS[0]))
    if wait:
        time.sleep(wait)
    for attempt in range(1, config.PACING["max_retries"] + 2):
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
            stats["retries"] += 1
            print("[重试] doc_id=%s 第 %d 次失败（%s），%.1f 秒后重试"
                  % (doc["doc_id"], attempt, type(exc).__name__, backoff))
            time.sleep(backoff)
            continue
        usage = response.usage.model_dump() if response.usage else {}
        usage = {k: v for k, v in usage.items()
                 if v is None or isinstance(v, (int, float, str, dict))}
        return {
            "compact": bool(compact),
            "max_tokens": kwargs["max_tokens"],
            "reasoning_effort": kwargs.get("reasoning_effort"),
            "input_sha256": input_sha256(doc, compact=compact),
            "elapsed_ms": int((time.time() - started) * 1000),
            "transport_attempts": attempt,
            "usage": usage,
            "finish_reason": (response.choices[0].finish_reason if response.choices else None),
            "model_resolved": str(getattr(response, "model", "") or ""),
            "response_text": (response.choices[0].message.content if response.choices else ""),
        }
    raise RuntimeError("模型调用失败且未抛出异常（不应到达）")


def call_model(doc, stats):
    """调用模型并返回缓存记录；主尝试被截断时按 config 的规则做一次压缩重试。

    两次原始返回都写进同一份缓存（`attempts_detail`），顶层 `response_text` 是
    **最终采用**的那一次；`usage_total` 是两次尝试的合计（成本要算全）。
    """
    import openai  # 只有真正要调用时才 import，避免复跑路径依赖它

    client = openai.OpenAI(api_key=config.api_key(), base_url=config.base_url(),
                           timeout=config.LLM["timeout_seconds"], max_retries=0)
    details = []
    for compact in (False, True):
        detail = _invoke(client, openai, doc, stats, compact)
        details.append(detail)
        if detail["finish_reason"] != config.LLM["fallback"]["trigger_reason"]:
            break
        if compact or len(details) >= config.LLM["fallback"]["max_attempts"]:
            break
        stats["fallback_calls"] = stats.get("fallback_calls", 0) + 1
        print("[压缩重试] doc_id=%s 主尝试被输出上限截断，改用压缩契约重试一次" % doc["doc_id"])
    final = details[-1]
    usage_total = {key: sum(int((d["usage"] or {}).get(key) or 0) for d in details)
                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    record = {
        "cache_schema": config.CACHE_SCHEMA,
        "doc_id": doc["doc_id"],
        "dataset_version": config.DATASET_VERSION,
        "model_requested": config.model_requested(),
        "model_resolved": final["model_resolved"],
        "model_pinned": config.LLM["model_pinned"],
        "model_pinning_state": config.model_pinning_state(final["model_resolved"]),
        "model_version": config.LLM["model_version"],
        "model_version_note": config.LLM["model_version_note"],
        "prompt_version": config.LLM["prompt_version"],
        "prompt_template_sha256": PROMPT_TEMPLATE_SHA256,
        "input_sha256": input_sha256(doc),
        "temperature": config.LLM["temperature"],
        "max_tokens": config.LLM["max_tokens"],
        "response_format": config.LLM["response_format"],
        "created_at": now_iso(),
        "elapsed_ms": sum(d["elapsed_ms"] for d in details),
        "attempts": len(details),
        "attempts_detail": details,
        "usage": final["usage"],
        "usage_total": usage_total,
        "finish_reason": final["finish_reason"],
        "response_text": final["response_text"],
    }
    target = cache_path(doc["doc_id"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    return record, False


def load_or_call(doc, force, stats):
    """缓存命中则只读缓存（不调模型）；缺失或 --force 才调用。"""
    path = cache_path(doc["doc_id"])
    if os.path.isfile(path) and not force:
        with open(path, encoding="utf-8") as fh:
            record = json.load(fh)
        want = input_sha256(doc)
        if record.get("input_sha256") != want:
            raise RuntimeError(
                "缓存与当前输入不一致：doc_id=%s 的缓存 input_sha256=%s，当前输入=%s。"
                "这通常意味着文档、提示词、模型或调用参数变过；确认后加 --force 重跑并重写缓存。"
                % (doc["doc_id"], record.get("input_sha256"), want))
        if record.get("finish_reason") == config.LLM["fallback"]["trigger_reason"]:
            # 未收敛的缓存条目（上一次返回被输出上限截断）不算有效缓存：本次补齐后才是稳态。
            print("[缓存] doc_id=%s 的缓存条目上一次返回被截断，本次做压缩重试补齐" % doc["doc_id"])
            record, _ = call_model(doc, stats)
            stats["fetched"] += 1
            return record, False
        stats["cache_hits"] += 1
        return record, True
    record, _ = call_model(doc, stats)
    stats["fetched"] += 1
    return record, False


# --------------------------------------------------------------------------
# 解析与证据定位
# --------------------------------------------------------------------------
def parse_json_object(text):
    """把模型返回文本解析成 JSON 对象；容错只做「剥 Markdown 代码围栏」，不做改写。"""
    raw = (text or "").strip()
    fence_stripped = False
    if raw.startswith("```"):
        fence_stripped = True
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        obj = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        return None, "bad_json:%s" % type(exc).__name__, fence_stripped
    if not isinstance(obj, dict):
        return None, "json_not_object", fence_stripped
    return obj, None, fence_stripped


def resolve_quote(quote, chunks_sorted, content_norm):
    """在文档的文本块序列里定位逐字引用。

    返回 (chunk_id, reason, match_count)：定位成功时 reason 为 None；
    失败时区分「正文里有、但跨了文本块边界」与「正文里根本没有」——
    前者是机械边界问题，后者才是改写或编造，两者必须分开登记。
    """
    q = evidence_key(quote)
    if not q:
        return None, "quote_missing", 0
    matched = [c for c in chunks_sorted if q in evidence_key(c.get("content"))]
    if matched:
        matched.sort(key=lambda c: c["chunk_index"])
        return matched[0]["chunk_id"], None, len(matched)
    if q in evidence_key(content_norm):
        return None, "quote_spans_chunk_boundary", 0
    return None, "quote_not_in_document", 0


def normalize_confidence(value):
    """confidence 只接受 0.0～1.0；写成百分数（1<x≤100）按 /100 归一并记警告。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None, None
    value = float(value)
    if config.CONFIDENCE_MIN <= value <= config.CONFIDENCE_MAX:
        return round(value, 3), None
    if config.CONFIDENCE_MAX < value <= 100.0:
        return round(value / 100.0, 3), "confidence_scaled"
    return None, None


def normalize_date(value):
    """把 YYYY-MM-DD／YYYY/M/D／YYYY.M.D／YYYY年M月D日 折成 YYYY-MM-DD；其余返回 None。"""
    if value is None:
        return None, False
    text = str(value).strip()
    if not text or text.lower() in ("null", "none"):
        return None, False
    for pattern in config.TIME["accepted_income_forms"]:
        if re.match(pattern, text):
            parts = re.findall(r"\d+", text)
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            try:
                return _dt.date(year, month, day).isoformat(), False
            except ValueError:
                return None, True
    return None, True


def date_rendering_in_document(iso_date, content_norm) -> bool:
    """日期是否在正文里真实出现。

    日期内部的空白（例如「2020 年9 月23 日」）是来源文本自带的排版空格，因此这一步
    在**去掉全部空白**的正文副本上比对；这不是对 quote 的模糊匹配，quote 仍走
    `resolve_quote()` 的折空白 + 精确子串。
    """
    year, month, day = iso_date.split("-")
    content_nospace = evidence_key(content_norm)
    renderings = ["%s-%s-%s" % (year, month, day),
                  "%s-%d-%d" % (year, int(month), int(day)),
                  "%s/%d/%d" % (year, int(month), int(day)),
                  "%s.%d.%d" % (year, int(month), int(day)),
                  "%s年%d月%d日" % (year, int(month), int(day))]
    return any(r in content_nospace for r in renderings)


def resolve_endpoint(ref, ref_type, entities_by_name_and_type, entities_by_name, ref_map):
    """把 head／tail 解析成实体或事件。返回 (resolved, reason)。"""
    text = str(ref or "").strip()
    if not text:
        return None, "endpoint_missing"
    if ref_type == "Event" or re.match(r"^E\d+$", text):
        event = ref_map.get(text)
        if event is None:
            return None, "event_ref_unresolved"
        if ref_type and ref_type != "Event":
            return None, "endpoint_type_mismatch"
        return {"kind": "event", "type": "Event", "id": event["event_id"],
                "name": event["event_name"], "obj": event}, None
    hit = entities_by_name_and_type.get((text, ref_type))
    if hit is None:
        same_name = entities_by_name.get(text, [])
        if len(same_name) == 1:
            hit = same_name[0]
        elif len(same_name) > 1:
            return None, "endpoint_ambiguous"
        else:
            return None, "entity_ref_unresolved"
    if ref_type and ref_type != hit["type"]:
        return None, "endpoint_type_mismatch"
    return {"kind": "entity", "type": hit["type"], "id": hit["entity_id"],
            "name": hit["name"], "obj": hit}, None


def parse_and_validate(doc, record, chunks_for_doc):
    """把一份缓存记录解析成（记录, 拒绝清单, 警告清单）。"""
    doc_id = doc["doc_id"]
    content_norm = normalize_ws(doc.get("content"))
    content_key = evidence_key(doc.get("content"))
    chunks_sorted = sorted(chunks_for_doc, key=lambda c: c["chunk_index"])
    rejects, warnings = [], []
    text = record.get("response_text") or ""
    parsed, err, fence = parse_json_object(text)
    if fence:
        warnings.append({"kind": "fences_stripped", "detail": "返回文本带 Markdown 代码围栏"})
    if parsed is None:
        reason = err
        if record.get("finish_reason") == "length":
            reason = "truncated_by_max_tokens"
        elif not text.strip():
            reason = "empty_response"
        rejects.append({"doc_id": doc_id, "kind": "document", "item_index": None,
                        "reason": reason, "payload": text[:200]})
        return None, rejects, warnings

    # ---- entities ----
    entities, seen_entities = [], {}
    raw_entities = parsed.get("entities")
    if not isinstance(raw_entities, list):
        rejects.append({"doc_id": doc_id, "kind": "entities", "item_index": None,
                        "reason": "entities_not_list", "payload": str(raw_entities)[:200]})
        raw_entities = []
    for index, item in enumerate(raw_entities):
        if not isinstance(item, dict):
            rejects.append({"doc_id": doc_id, "kind": "entity", "item_index": index,
                            "reason": "item_not_object", "payload": str(item)[:200]})
            continue
        name = str(item.get("name") or "").strip()
        etype = item.get("type")
        quote = item.get("quote")
        reason = None
        chunk_id = None
        match_count = 0
        if not name:
            reason = "entity_name_missing"
        elif etype not in config.ENTITY_TYPES_FROM_MODEL:
            reason = "entity_type_illegal"
        elif evidence_key(name) not in content_key:
            reason = "entity_name_not_in_document"
        else:
            chunk_id, reason, match_count = resolve_quote(quote, chunks_sorted, content_norm)
        if reason:
            rejects.append({"doc_id": doc_id, "kind": "entity", "item_index": index,
                            "reason": reason, "payload": item})
            continue
        key = (name, etype)
        if key in seen_entities:
            warnings.append({"kind": "entity_duplicate", "detail": "%s（%s）" % key})
            continue
        entity = {
            "entity_id": "ENT-%d-%03d" % (doc_id, len(entities) + 1),
            "name": name, "type": etype,
            "source_doc_id": doc_id, "source_chunk_id": chunk_id,
            "quote": str(quote).strip(), "quote_match_count": match_count,
        }
        if match_count > 1:
            warnings.append({"kind": "quote_ambiguous",
                             "detail": "entity %s 命中 %d 块，取最小块" % (name, match_count)})
        entities.append(entity)
        seen_entities[key] = entity

    entities_by_name, entities_by_name_and_type = {}, {}
    for entity in entities:
        entities_by_name.setdefault(entity["name"], []).append(entity)
        entities_by_name_and_type[(entity["name"], entity["type"])] = entity

    # ---- events ----
    events, ref_map = [], {}
    raw_events = parsed.get("events")
    if not isinstance(raw_events, list):
        rejects.append({"doc_id": doc_id, "kind": "events", "item_index": None,
                        "reason": "events_not_list", "payload": str(raw_events)[:200]})
        raw_events = []
    if len(raw_events) > config.EXTRACT_LIMITS["events"]:
        warnings.append({"kind": "events_over_limit",
                         "detail": "返回 %d 条，超过上限 %d，按序截断"
                                   % (len(raw_events), config.EXTRACT_LIMITS["events"])})
        raw_events = raw_events[:config.EXTRACT_LIMITS["events"]]
    for index, item in enumerate(raw_events):
        ref = "E%d" % (index + 1)
        if not isinstance(item, dict):
            rejects.append({"doc_id": doc_id, "kind": "event", "item_index": index,
                            "reason": "item_not_object", "payload": str(item)[:200]})
            continue
        event_type = item.get("event_type")
        name = str(item.get("event_name") or "").strip()
        description = str(item.get("description") or "").strip()
        quote = item.get("quote")
        reason = None
        chunk_id = None
        match_count = 0
        if event_type not in config.EVENT_TYPES:
            reason = "event_type_illegal"
        elif not name:
            reason = "event_name_missing"
        elif not description:
            reason = "event_description_missing"
        else:
            chunk_id, reason, match_count = resolve_quote(quote, chunks_sorted, content_norm)
        if reason is None and normalize_confidence(item.get("confidence"))[0] is None:
            reason = "event_confidence_missing_or_illegal"
        if reason:
            rejects.append({"doc_id": doc_id, "kind": "event", "item_index": index,
                            "reason": reason, "payload": item})
            continue
        confidence, conf_warn = normalize_confidence(item.get("confidence"))
        if conf_warn:
            warnings.append({"kind": conf_warn,
                             "detail": "%s confidence=%s" % (ref, item.get("confidence"))})
        event_time, unparsable = normalize_date(item.get("event_time"))
        if unparsable:
            warnings.append({"kind": "event_time_unparsable",
                             "detail": "%s 原值=%r → null" % (ref, item.get("event_time"))})
        elif event_time and config.TIME["verify_rendering_in_document"] \
                and not date_rendering_in_document(event_time, content_norm):
            warnings.append({"kind": "event_time_unverified",
                             "detail": "%s %s 未在正文找到该日期的任何写法 → null"
                                       % (ref, event_time)})
            event_time = None
        event = {
            "event_id": "EVT-%d-%02d" % (doc_id, len(events) + 1),
            "event_type": event_type, "event_name": name, "event_time": event_time,
            "description": description, "confidence": confidence,
            "source_doc_id": doc_id, "source_chunk_id": chunk_id,
            "quote": str(quote).strip(), "quote_match_count": match_count,
            "local_ref": ref,
        }
        events.append(event)
        ref_map[ref] = event

    # ---- relations ----
    relations = []
    raw_relations = parsed.get("relations")
    if not isinstance(raw_relations, list):
        rejects.append({"doc_id": doc_id, "kind": "relations", "item_index": None,
                        "reason": "relations_not_list", "payload": str(raw_relations)[:200]})
        raw_relations = []
    if len(raw_relations) > config.EXTRACT_LIMITS["relations"]:
        warnings.append({"kind": "relations_over_limit",
                         "detail": "返回 %d 条，超过上限 %d，按序截断"
                                   % (len(raw_relations), config.EXTRACT_LIMITS["relations"])})
        raw_relations = raw_relations[:config.EXTRACT_LIMITS["relations"]]
    for index, item in enumerate(raw_relations):
        if not isinstance(item, dict):
            rejects.append({"doc_id": doc_id, "kind": "relation", "item_index": index,
                            "reason": "item_not_object", "payload": str(item)[:200]})
            continue
        relation = item.get("relation")
        reason = None
        chunk_id, match_count = None, 0
        head = tail = None
        confidence = None
        if relation not in config.RELATIONS_FROM_MODEL:
            reason = "relation_not_allowed"
        if reason is None:
            head, reason = resolve_endpoint(item.get("head"), item.get("head_type"),
                                            entities_by_name_and_type, entities_by_name, ref_map)
        if reason is None:
            tail, reason = resolve_endpoint(item.get("tail"), item.get("tail_type"),
                                            entities_by_name_and_type, entities_by_name, ref_map)
        schema = config.RELATION_SCHEMA.get(relation, {})
        if reason is None and (head["type"] not in schema.get("domain", [])
                               or tail["type"] not in schema.get("range", [])):
            reason = "relation_domain_range_illegal"
        role = item.get("role")
        if reason is None and relation == "PARTICIPATES_IN" and role not in config.ROLES:
            reason = "role_missing_or_illegal"
        if reason is None and relation == "ISSUED_BY":
            if head["kind"] != "event":
                reason = "issued_by_head_not_event"
            elif head["obj"]["event_type"] not in config.ISSUED_BY_EVENT_TYPES:
                reason = "issued_by_event_type_illegal"
            elif tail["type"] != "Institution":
                reason = "issued_by_tail_not_institution"
        if reason is None:
            confidence, conf_warn = normalize_confidence(item.get("confidence"))
            if confidence is None:
                reason = "relation_confidence_missing_or_illegal"
            elif conf_warn:
                warnings.append({"kind": conf_warn, "detail": "relation#%d" % index})
        if reason is None:
            chunk_id, reason, match_count = resolve_quote(
                item.get("quote"), chunks_sorted, content_norm)
        if reason:
            rejects.append({"doc_id": doc_id, "kind": "relation", "item_index": index,
                            "reason": reason, "payload": item})
            continue
        relation_record = {
            "relation_id": "REL-%d-%03d" % (doc_id, len(relations) + 1),
            "relation": relation,
            "head_id": head["id"], "head_name": head["name"], "head_type": head["type"],
            "tail_id": tail["id"], "tail_name": tail["name"], "tail_type": tail["type"],
            "source_doc_id": doc_id, "source_chunk_id": chunk_id, "confidence": confidence,
            "quote": str(item.get("quote")).strip(), "quote_match_count": match_count,
        }
        if relation == "PARTICIPATES_IN":
            relation_record["role"] = role
        elif role is not None:
            warnings.append({"kind": "role_ignored",
                             "detail": "%s 不携带 role，已忽略" % relation})
        if relation == "BELONGS_TO":
            valid_from, bad_from = normalize_date(item.get("valid_from"))
            valid_to, bad_to = normalize_date(item.get("valid_to"))
            for label, raw_value, bad in (("valid_from", item.get("valid_from"), bad_from),
                                          ("valid_to", item.get("valid_to"), bad_to)):
                if bad:
                    warnings.append({"kind": "%s_unparsable" % label,
                                     "detail": "原值=%r → null" % raw_value})
            relation_record["valid_from"] = valid_from if not bad_from else None
            relation_record["valid_to"] = valid_to if not bad_to else None
        relations.append(relation_record)

    # ---- 去重规则：同一机构既是发布／作出方又参与该事件时只写 ISSUED_BY ----
    issued = {(r["head_id"], r["tail_id"]) for r in relations if r["relation"] == "ISSUED_BY"}
    kept = []
    for relation_record in relations:
        if relation_record["relation"] == "PARTICIPATES_IN" \
                and relation_record.get("role") == "监管方" \
                and (relation_record["tail_id"], relation_record["head_id"]) in issued:
            rejects.append({
                "doc_id": doc_id, "kind": "relation", "item_index": None,
                "reason": "issued_by_duplicate",
                "payload": {"dropped_relation_id": relation_record["relation_id"],
                            "relation": "PARTICIPATES_IN",
                            "head": relation_record["head_name"],
                            "tail": relation_record["tail_name"],
                            "note": "同一机构既是发布／作出方又参与该事件，"
                                    "按《10》第4.5.2节 只保留 ISSUED_BY"}})
        else:
            kept.append(relation_record)
    relations = kept

    # ---- EVIDENCED_BY：由程序生成，不带三项证据属性 ----
    evidenced_by = [{
        "relation_id": "EVD-%d-%02d" % (doc_id, i + 1),
        "relation": "EVIDENCED_BY",
        "head_id": event["event_id"], "head_name": event["event_name"], "head_type": "Event",
        "tail_id": "DOC-%d" % doc_id, "tail_name": doc["title"],
        "tail_type": config.DOCUMENT_LABEL,
        "note": "结构性关系：终点即证据文档，不携带 source_doc_id／source_chunk_id／confidence",
    } for i, event in enumerate(events)]

    for event in events:
        involved = [r for r in relations
                    if r["tail_id"] == event["event_id"]
                    or (r["relation"] == "ISSUED_BY" and r["head_id"] == event["event_id"])]
        if not involved:
            warnings.append({"kind": "event_without_participant",
                             "detail": "%s（%s）没有 PARTICIPATES_IN／ISSUED_BY"
                                       % (event["event_id"], event["event_type"])})

    record_out = {
        "record_schema": config.RECORD_SCHEMA,
        "doc_id": doc_id,
        "category": doc.get("category"),
        "title": doc.get("title"),
        "source": doc.get("source"),
        "publish_time": doc.get("publish_time"),
        "content_sha256_16": doc.get("content_sha256_16"),
        "model_requested": record.get("model_requested"),
        "model_resolved": record.get("model_resolved"),
        "model_pinning_state": record.get("model_pinning_state"),
        "prompt_version": record.get("prompt_version"),
        "prompt_template_sha256": record.get("prompt_template_sha256"),
        "input_sha256": record.get("input_sha256"),
        "temperature": record.get("temperature"),
        "finish_reason": record.get("finish_reason"),
        "entities": entities,
        "events": events,
        "relations": relations,
        "evidenced_by": evidenced_by,
        "counts": {"entities": len(entities), "events": len(events),
                   "relations": len(relations), "evidenced_by": len(evidenced_by),
                   "rejected": len(rejects), "warnings": len(warnings)},
        "warnings": warnings,
    }
    return record_out, rejects, warnings


# --------------------------------------------------------------------------
# 运行与产物
# --------------------------------------------------------------------------
def load_docs_and_chunks():
    docs = read_jsonl(config.DOCS_PATH)
    chunks = read_jsonl(config.CHUNKS_PATH)
    by_doc = {}
    for chunk in chunks:
        by_doc.setdefault(chunk["doc_id"], []).append(chunk)
    return docs, chunks, by_doc


def pick_docs(args, docs):
    """按 profile／--docs／--limit 决定本次跑哪些文档，返回 [(doc, reason), ...]。"""
    if args.profile == "pilot":
        selection = select_pilot_docs(docs)
    else:
        selection = [(d, "profile=v21 全量（T3 的口径）")
                     for d in sorted(docs, key=lambda x: x["doc_id"])]
    if args.docs:
        wanted = [int(x) for x in re.split(r"[,\s]+", args.docs.strip()) if x]
        by_id = {d["doc_id"]: (d, reason) for d, reason in selection}
        all_by_id = {d["doc_id"]: d for d in docs}
        picked = []
        for doc_id in wanted:
            if doc_id in by_id:
                picked.append(by_id[doc_id])
            elif doc_id in all_by_id:
                picked.append((all_by_id[doc_id], "由 --docs 显式指定（不在选样结果内）"))
            else:
                raise SystemExit("--docs 里的 doc_id=%s 不在 v2.1 的 documents.jsonl 中" % doc_id)
        selection = picked
    if args.limit is not None:
        selection = selection[:args.limit]
    return selection


def build_selection_payload(selection, problems):
    spec = config.PILOT
    return {
        "dataset_version": config.DATASET_VERSION,
        "rule": {
            "doc_count": spec["doc_count"],
            "category_quota": spec["category_quota"],
            "preferred_category": spec["preferred_category"],
            "min_doc_chars": spec["min_doc_chars"],
            "event_type_order": spec["event_type_order"],
            "stages": ["A 事件类型覆盖", "B 类目补齐", "C 兜底补足篇数"],
            "note": "事件类型命中是《13》第9.1.1节 的标题级冻结代理正则（不是抽取结果）；"
                    "同一事件类型内「正文也命中」优先，再按 doc_id 升序。",
        },
        "documents": [{
            "doc_id": d["doc_id"], "category": d["category"], "title": d["title"],
            "publish_time": d["publish_time"], "chars": len(str(d.get("content") or "")),
            "reason": reason,
            "title_level_event_types": [et for et in spec["event_type_order"]
                                        if event_type_hits(d, et)],
        } for d, reason in selection],
        "category_counts": {cat: sum(1 for d, _ in selection if d["category"] == cat)
                            for cat in spec["category_order"]},
        "event_type_coverage": {et: [d["doc_id"] for d, _ in selection if event_type_hits(d, et)]
                                for et in spec["event_type_order"]},
        "assertions_ok": not problems,
        "assertion_problems": problems,
    }


def write_manifest(selection):
    """把确定性产物写成 `sha256  <路径>` 的清单（缓存 + 解析输出 + 选样 + 覆盖性）。"""
    paths = [os.path.join(config.CACHE_DIR, "%s.json" % d["doc_id"]) for d, _ in selection]
    paths += [config.OUTPUT_FILES["selection"], config.OUTPUT_FILES["coverage"],
              config.OUTPUT_FILES["extracted"], config.OUTPUT_FILES["rejected"]]
    entries = []
    for path in sorted(paths):
        if not os.path.isfile(path):
            continue
        rel = os.path.relpath(path, config.ROOT).replace("\\", "/")
        entries.append("%s  %s" % (sha256_file(path), rel))
    text = "\n".join(entries) + "\n"
    with open(config.OUTPUT_FILES["manifest"], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return {"manifest_sha256": config.sha256_hex(text), "file_count": len(entries),
            "text": text}


def append_run_history(stats):
    path = config.OUTPUT_FILES["run_history"]
    index = len(read_jsonl(path)) if os.path.isfile(path) else 0
    line = dict(stats)
    line["run_index"] = index + 1
    with open(path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(line, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")) + "\n")


def run_extraction(args, docs, chunks, by_doc, selection, stats):
    os.makedirs(config.PILOT_DIR, exist_ok=True)
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    problems = check_selection(selection) if (args.profile == "pilot"
                                              and not args.docs) else []
    selection_payload = build_selection_payload(selection, problems)
    dump_json(config.OUTPUT_FILES["selection"], selection_payload)
    coverage = compute_coverage(docs, chunks)
    dump_json(config.OUTPUT_FILES["coverage"], coverage)

    records, rejects_all, failures = [], [], []
    for index, (doc, _) in enumerate(selection, 1):
        doc_id = doc["doc_id"]
        started = time.time()
        try:
            record, from_cache = load_or_call(doc, args.force, stats)
        except Exception as exc:  # noqa: BLE001
            failures.append({"doc_id": doc_id, "stage": "call_or_cache",
                             "error": "%s: %s" % (type(exc).__name__, exc)})
            print("[失败] doc_id=%s 调用／缓存阶段失败：%s: %s"
                  % (doc_id, type(exc).__name__, exc))
            continue
        record_out, rejects, warnings = parse_and_validate(doc, record, by_doc.get(doc_id, []))
        rejects_all.extend(rejects)
        if record_out is None:
            failures.append({"doc_id": doc_id, "stage": "parse", "error": rejects[0]["reason"]})
            print("[失败] doc_id=%s 解析失败：%s" % (doc_id, rejects[0]["reason"]))
        else:
            records.append(record_out)
        usage = record.get("usage_total") or record.get("usage") or {}
        stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        stats["total_tokens"] += int(usage.get("total_tokens") or 0)
        stats["model_latency_ms_sum"] = stats.get("model_latency_ms_sum", 0) \
            + int(record.get("elapsed_ms") or 0)
        if record.get("model_pinning_state") == "warning":
            stats["model_pinning_warnings"].append(doc_id)
        stats["per_doc"].append({
            "doc_id": doc_id, "from_cache": from_cache,
            "elapsed_ms": int((time.time() - started) * 1000),
            "cache_elapsed_ms": record.get("elapsed_ms"),
            "finish_reason": record.get("finish_reason"),
            "usage": usage,
            "counts": (record_out or {}).get("counts", {}),
            "reject_reasons": sorted({r["reason"].split(":")[0] for r in rejects}),
            "warning_kinds": sorted({w["kind"] for w in warnings}),
        })
        print("[%2d/%2d] doc_id=%-5s %-6s 缓存=%-5s 实体=%-2s 事件=%-2s 关系=%-2s 拒绝=%-2s %s"
              % (index, len(selection), doc_id, doc["category"],
                 "命中" if from_cache else "新调",
                 (record_out or {}).get("counts", {}).get("entities", "-"),
                 (record_out or {}).get("counts", {}).get("events", "-"),
                 (record_out or {}).get("counts", {}).get("relations", "-"),
                 len(rejects), str(doc["title"])[:34]))

    records.sort(key=lambda r: r["doc_id"])
    rejects_all.sort(key=lambda r: (r["doc_id"], r["kind"], r.get("item_index") or 0, r["reason"]))
    dump_jsonl(config.OUTPUT_FILES["extracted"], records)
    dump_jsonl(config.OUTPUT_FILES["rejected"], rejects_all)
    dump_json(config.OUTPUT_FILES["verify"],
              build_verify_payload(docs, chunks, records, rejects_all, selection))
    manifest = write_manifest(selection)
    stats["manifest_sha256"] = manifest["manifest_sha256"]
    stats["manifest_files"] = manifest["file_count"]
    stats["finished_at"] = now_iso()
    stats["wall_clock_seconds"] = round(
        time.time() - float(stats.pop("_started_monotonic", time.time())), 2)
    stats["api_calls_total"] = stats["api_calls"]
    stats["failures"] = failures
    stats["reject_total"] = len(rejects_all)
    append_run_history(stats)
    return records, rejects_all, failures, selection_payload, coverage, manifest


# --------------------------------------------------------------------------
# 独立核对：证据可回溯 + 本体一致性 + 证据属性完整性（全部对 v2.1 重算）
# --------------------------------------------------------------------------
def check_chunk_evidence(item, doc_id, chunk_by_id, chunk_ids_by_doc):
    """核对一条事实的 source_chunk_id 与 quote（对 chunks.jsonl 重算，不读产物自述）。"""
    chunk_id = item.get("source_chunk_id")
    if chunk_id is None:
        return False, "source_chunk_id_missing"
    if chunk_id not in chunk_by_id:
        return False, "source_chunk_id_not_in_chunks_jsonl"
    if chunk_id not in chunk_ids_by_doc.get(doc_id, set()):
        return False, "source_chunk_id_belongs_to_other_doc"
    if item.get("source_doc_id") != doc_id:
        return False, "source_doc_id_mismatch"
    quote = evidence_key(item.get("quote"))
    if not quote:
        return False, "quote_empty"
    if quote not in evidence_key(chunk_by_id[chunk_id].get("content")):
        return False, "quote_not_in_that_chunk"
    return True, None


def build_verify_payload(docs, chunks, records, rejects_all, selection):
    """对已落盘的结果做独立核对；本文件不写时间，参与逐字节比对。"""
    doc_by_id = {d["doc_id"]: d for d in docs}
    chunk_by_id = {c["chunk_id"]: c for c in chunks}
    chunk_ids_by_doc = {}
    for chunk in chunks:
        chunk_ids_by_doc.setdefault(chunk["doc_id"], set()).add(chunk["chunk_id"])

    entity_types, event_types, relation_types = {}, {}, {}
    evidence_ok, evidence_bad = 0, []
    attr_ok, attr_bad = 0, []
    role_counts, illegal, examples = {}, [], []
    for record in records:
        doc_id = record["doc_id"]
        for entity in record["entities"]:
            entity_types[entity["type"]] = entity_types.get(entity["type"], 0) + 1
            if entity["type"] not in config.ENTITY_TYPES:
                illegal.append({"kind": "entity_type_illegal", "doc_id": doc_id,
                                "item": entity["entity_id"]})
            ok, why = check_chunk_evidence(entity, doc_id, chunk_by_id, chunk_ids_by_doc)
            evidence_ok, evidence_bad = _tally(ok, why, entity, "entity",
                                               evidence_ok, evidence_bad)
            if ok and len(examples) < 6:
                examples.append({"kind": "entity", "doc_id": doc_id, "item": entity["name"],
                                 "source_chunk_id": entity["source_chunk_id"],
                                 "chunk_doc_id": chunk_by_id[entity["source_chunk_id"]]["doc_id"],
                                 "quote_head": normalize_ws(entity["quote"])[:30]})
        for event in record["events"]:
            event_types[event["event_type"]] = event_types.get(event["event_type"], 0) + 1
            missing = [a for a in config.EVENT_CORE_ATTRS
                       if a not in event or (event.get(a) in (None, "") and a != "event_time")]
            if missing:
                illegal.append({"kind": "event_core_attrs_missing", "doc_id": doc_id,
                                "item": event["event_id"], "detail": missing})
            if event["event_type"] not in config.EVENT_TYPES:
                illegal.append({"kind": "event_type_illegal", "doc_id": doc_id,
                                "item": event["event_id"]})
            ok, why = check_chunk_evidence(event, doc_id, chunk_by_id, chunk_ids_by_doc)
            evidence_ok, evidence_bad = _tally(ok, why, event, "event",
                                               evidence_ok, evidence_bad)
        for relation in record["relations"] + record["evidenced_by"]:
            relation_types[relation["relation"]] = relation_types.get(relation["relation"], 0) + 1
            if relation["relation"] == "EVIDENCED_BY":
                if any(a in relation for a in config.EVIDENCE_ATTRS):
                    illegal.append({"kind": "evidenced_by_has_evidence_attrs",
                                    "doc_id": doc_id, "item": relation["relation_id"]})
                if relation["tail_type"] != config.DOCUMENT_LABEL:
                    illegal.append({"kind": "evidenced_by_tail_not_document",
                                    "doc_id": doc_id, "item": relation["relation_id"]})
                continue
            if relation["relation"] not in config.RELATIONS:
                illegal.append({"kind": "relation_type_illegal", "doc_id": doc_id,
                                "item": relation["relation_id"]})
            ok, why = check_chunk_evidence(relation, doc_id, chunk_by_id, chunk_ids_by_doc)
            evidence_ok, evidence_bad = _tally(ok, why, relation, "relation",
                                               evidence_ok, evidence_bad)
            if ok:
                missing = [a for a in config.EVIDENCE_ATTRS if relation.get(a) in (None, "")]
                if missing:
                    attr_bad.append({"kind": "relation", "doc_id": doc_id,
                                     "id": relation["relation_id"], "missing": missing})
                else:
                    attr_ok += 1
            if relation["relation"] == "PARTICIPATES_IN":
                role = relation.get("role")
                role_counts[role] = role_counts.get(role, 0) + 1
                if role not in config.ROLES:
                    illegal.append({"kind": "role_illegal", "doc_id": doc_id,
                                    "item": relation["relation_id"], "detail": role})
            if relation["relation"] == "ISSUED_BY":
                heads = [e for e in record["events"] if e["event_id"] == relation["head_id"]]
                if not heads or heads[0]["event_type"] not in config.ISSUED_BY_EVENT_TYPES:
                    illegal.append({"kind": "issued_by_event_type_illegal", "doc_id": doc_id,
                                    "item": relation["relation_id"]})
    reject_reasons = {}
    for reject in rejects_all:
        key = reject["reason"].split(":")[0]
        reject_reasons[key] = reject_reasons.get(key, 0) + 1
    selected_ids = [d["doc_id"] for d, _ in selection]
    present_ids = [r["doc_id"] for r in records]
    missing_ids = [doc_id for doc_id in selected_ids if doc_id not in set(present_ids)]
    return {
        "verified_at": None,      # 不写时间：本文件参与逐字节比对
        "dataset_version": config.DATASET_VERSION,
        "documents": len(records),
        "selected_doc_ids": selected_ids,
        "documents_missing": missing_ids,
        "scope_note": ("本次核对覆盖 %d／%d 篇；缺失的 doc_id 见 documents_missing"
                       "（部分运行或解析失败都会落在这里）"
                       % (len(present_ids), len(selected_ids))),
        "ontology": {
            "entity_types": entity_types,
            "event_types": event_types,
            "relation_types": relation_types,
            "entity_types_expected": config.ENTITY_TYPES,
            "event_types_expected": config.EVENT_TYPES,
            "relations_expected": config.RELATIONS,
            "enumeration_violations": illegal,
        },
        "evidence": {
            "items_checked": evidence_ok + len(evidence_bad),
            "items_ok": evidence_ok,
            "items_bad": len(evidence_bad),
            "bad_examples": evidence_bad[:10],
            "examples": examples,
            "rule": "source_chunk_id 必须在 v2.1 的 chunks.jsonl 中存在、其 doc_id 等于同一条事实的 "
                    "source_doc_id，且该条的 quote 折空白后必须出现在该文本块的 content 里",
            "note": "EVIDENCED_BY 不参与本项核对（它不携带三项证据属性，终点即文档）",
        },
        "evidence_attrs": {
            "relations_with_three_attrs_ok": attr_ok,
            "relations_missing_attrs": attr_bad[:10],
        },
        "roles": role_counts,
        "rejected": {"total": len(rejects_all), "by_reason": reject_reasons},
        "negative_controls": negative_controls(records, chunks, doc_by_id),
        "reproducibility": reproducibility_check(),
    }


def negative_controls(records, chunks, doc_by_id, marker="【负对照标记不会出现在正文】"):
    """负对照：证明「引用定位门」与「枚举门」不是摆设（全部离线、确定性）。

    做法：拿一条**已通过**的实体引用来做三件事——① 在原引用后追加一个正文里不存在的
    标记；② 在引用前追加同一标记；③ 用一条编造的关系（INVOLVES）与一个本体外实体类型
    （Product）跑一遍 `parse_and_validate`。期望全部被拒。
    """
    chunks_by_doc = {}
    for chunk in chunks:
        chunks_by_doc.setdefault(chunk["doc_id"], []).append(chunk)
    results = []
    sample = None
    for record in records:
        if record["entities"]:
            sample = (record, record["entities"][0])
            break
    if sample is None:
        return {"executed": False, "reason": "没有可用于负对照的已通过实体", "cases": []}
    record, entity = sample
    doc = doc_by_id.get(record["doc_id"], {})
    content_norm = evidence_key(doc.get("content"))
    ordered = sorted(chunks_by_doc.get(record["doc_id"], []), key=lambda c: c["chunk_index"])
    cases = []
    original = evidence_key(entity["quote"])
    middle = len(original) // 2
    for label, mutated in (("引用后追加正文不存在的标记", original + marker),
                           ("引用前追加正文不存在的标记", marker + original),
                           ("引用中间插入正文不存在的标记",
                            original[:middle] + marker + original[middle:])):
        chunk_id, reason, _ = resolve_quote(mutated, ordered, content_norm)
        cases.append({"case": label, "malformed_quote": mutated[:60],
                      "expected": "reject", "got_chunk_id": chunk_id,
                      "got_reason": reason, "passed": chunk_id is None})
    synthetic = {
        "entities": [{"name": entity["name"], "type": "Product", "quote": entity["quote"]}],
        "events": [{"event_type": "不存在的类型", "event_name": "x", "event_time": None,
                    "description": "x", "confidence": 0.5, "quote": entity["quote"]}],
        "relations": [
            {"relation": "INVOLVES", "head": entity["name"], "head_type": "Company",
             "tail": "E1", "tail_type": "Event", "confidence": 0.5, "quote": entity["quote"]},
            {"relation": "EVIDENCED_BY", "head": "E1", "head_type": "Event",
             "tail": entity["name"], "tail_type": "Company", "confidence": 0.5,
             "quote": entity["quote"]},
        ],
    }
    _, rejects, _ = parse_and_validate(doc, {"response_text": json.dumps(
        synthetic, ensure_ascii=False)}, ordered)
    got = sorted({r["reason"] for r in rejects})
    cases.append({
        "case": "本体外类型／关系（Product、INVOLVES、模型输出 EVIDENCED_BY）",
        "expected": ["entity_type_illegal", "event_type_illegal", "relation_not_allowed"],
        "got_reasons": got,
        "passed": {"entity_type_illegal", "event_type_illegal",
                   "relation_not_allowed"}.issubset(set(got)),
    })
    return {"executed": True, "doc_id": record["doc_id"],
            "cases": cases, "all_passed": all(c["passed"] for c in cases)}


def _tally(ok, why, item, kind, evidence_ok, evidence_bad):
    if ok:
        return evidence_ok + 1, evidence_bad
    evidence_bad.append({"kind": kind,
                         "doc_id": item.get("source_doc_id"),
                         "id": item.get("entity_id") or item.get("event_id")
                               or item.get("relation_id"),
                         "reason": why})
    return evidence_ok, evidence_bad


def reproducibility_check():
    """读 run_history.jsonl：产物清单哈希在两次运行间一致即成可重放证据。"""
    path = config.OUTPUT_FILES["run_history"]
    if not os.path.isfile(path):
        return {"runs": 0}
    runs = read_jsonl(path)
    out = {"runs": len(runs),
           "manifest_sha256": [r.get("manifest_sha256") for r in runs],
           "api_calls": [r.get("api_calls_total", r.get("api_calls")) for r in runs],
           "cache_hits": [r.get("cache_hits") for r in runs],
           "fetched": [r.get("fetched") for r in runs],
           "documents": [r.get("documents") for r in runs],
           "wall_clock_seconds": [r.get("wall_clock_seconds") for r in runs]}
    # 只看**最后两次文档集合相同**的运行：前面的单篇冒烟不作为可重放证据。
    same_scope = [r for r in runs
                  if r.get("documents") == (runs[-1].get("documents") if runs else None)]
    tail = same_scope[-2:]
    out["compared_runs"] = [r.get("run_index") for r in tail]
    out["compared_manifest_sha256"] = [r.get("manifest_sha256") for r in tail]
    out["identical_across_runs"] = (len(tail) >= 2
                                    and len({r.get("manifest_sha256") for r in tail}) == 1
                                    and bool(tail[0].get("manifest_sha256")))
    return out


def print_verify_summary(payload):
    print("核对：文档 %d 篇；实体 %d／事件 %d／关系 %d（含 EVIDENCED_BY %d）"
          % (payload["documents"],
             sum(payload["ontology"]["entity_types"].values()),
             sum(payload["ontology"]["event_types"].values()),
             sum(payload["ontology"]["relation_types"].values()),
             payload["ontology"]["relation_types"].get("EVIDENCED_BY", 0)))
    print("  实体类型：%s" % payload["ontology"]["entity_types"])
    print("  事件类型：%s" % payload["ontology"]["event_types"])
    print("  关系类型：%s" % payload["ontology"]["relation_types"])
    print("  枚举违规：%d 条" % len(payload["ontology"]["enumeration_violations"]))
    evidence = payload["evidence"]
    print("  证据：核对 %d 条，通过 %d，未通过 %d"
          % (evidence["items_checked"], evidence["items_ok"], evidence["items_bad"]))
    print("  证据属性：带齐三项 %d 条，缺项 %d 条"
          % (payload["evidence_attrs"]["relations_with_three_attrs_ok"],
             len(payload["evidence_attrs"]["relations_missing_attrs"])))
    print("  拒绝：合计 %d 条；原因分布 %s"
          % (payload["rejected"]["total"], payload["rejected"]["by_reason"]))
    repro = payload["reproducibility"]
    print("  可重放：运行 %s 次；清单哈希 %s；两次一致=%s；API 调用 %s；缓存命中 %s"
          % (repro.get("runs"),
             [h[:12] if h else None for h in repro.get("manifest_sha256", [])],
             repro.get("identical_across_runs"), repro.get("api_calls"),
             repro.get("cache_hits")))
    controls = payload.get("negative_controls") or {}
    print("  负对照：执行=%s；全部通过=%s" % (controls.get("executed"), controls.get("all_passed")))


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 6 阶段实体与事件抽取（T1 小规模试跑；参数一律取自 config.py）")
    parser.add_argument("--profile", default="pilot", choices=["pilot", "v21"],
                        help="pilot＝T1 的 12 篇确定性选样（默认）；v21＝全量 709 篇（T3 口径）")
    parser.add_argument("--limit", type=int, default=None, help="只跑选样结果的前 N 篇")
    parser.add_argument("--docs", default=None, help="只跑指定 doc_id，逗号或空格分隔")
    parser.add_argument("--force", action="store_true", help="忽略已有缓存，重新调用并重写缓存")
    parser.add_argument("--select-only", action="store_true",
                        help="只算选样与覆盖性重算，不调模型")
    parser.add_argument("--verify", action="store_true", help="只核对既有产物，不调模型")
    args = parser.parse_args(argv)

    docs, chunks, by_doc = load_docs_and_chunks()
    print("输入：%s（%d 篇文档／%d 个文本块）" % (config.DOCS_PATH, len(docs), len(chunks)))

    if args.select_only or args.verify:
        selection = pick_docs(args, docs)
        problems = check_selection(selection) if args.profile == "pilot" else []
        if args.select_only:
            os.makedirs(config.PILOT_DIR, exist_ok=True)
            payload = build_selection_payload(selection, problems)
            dump_json(config.OUTPUT_FILES["selection"], payload)
            coverage = compute_coverage(docs, chunks)
            dump_json(config.OUTPUT_FILES["coverage"], coverage)
            print("选样 %d 篇；类目=%s" % (len(selection), payload["category_counts"]))
            print("覆盖性重算与《15》声明值一致：%s" % coverage["matches_declared"])
            for diff in coverage["differs_from_declared"]:
                print("  [差异] %s" % diff)
            for problem in problems:
                print("  [选样断言未通过] %s" % problem)
            return 0 if not problems else 1
        records = read_jsonl(config.OUTPUT_FILES["extracted"]) \
            if os.path.isfile(config.OUTPUT_FILES["extracted"]) else []
        rejects = read_jsonl(config.OUTPUT_FILES["rejected"]) \
            if os.path.isfile(config.OUTPUT_FILES["rejected"]) else []
        payload = build_verify_payload(docs, chunks, records, rejects, selection)
        dump_json(config.OUTPUT_FILES["verify"], payload)
        print_verify_summary(payload)
        return 0

    selection = pick_docs(args, docs)
    problems = check_selection(selection) if (args.profile == "pilot"
                                              and not args.docs) else []
    if problems:
        for problem in problems:
            print("[选样断言未通过] %s" % problem)
        return 1
    started_at = time.time()
    stats = {"started_at": now_iso(), "profile": args.profile, "documents": len(selection),
             "api_calls": 0, "retries": 0, "cache_hits": 0, "fetched": 0,
             "fallback_calls": 0,
             "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
             "model_latency_ms_sum": 0,
             "model_pinning_warnings": [], "per_doc": [], "force": bool(args.force),
             "_started_monotonic": started_at}
    records, rejects, failures, _, coverage, manifest = run_extraction(
        args, docs, chunks, by_doc, selection, stats)
    print("\n汇总：文档 %d／实体 %d／事件 %d／关系 %d（另有 EVIDENCED_BY %d）；拒绝 %d 条；失败 %d 篇"
          % (len(records),
             sum(r["counts"]["entities"] for r in records),
             sum(r["counts"]["events"] for r in records),
             sum(r["counts"]["relations"] for r in records),
             sum(r["counts"]["evidenced_by"] for r in records),
             len(rejects), len(failures)))
    print("本跑：API 调用 %d 次（重试 %d）、缓存命中 %d 篇、本次新调 %d 篇；"
          "tokens 合计 %d（prompt %d ＋ completion %d）"
          % (stats["api_calls"], stats["retries"], stats["cache_hits"], stats["fetched"],
             stats["total_tokens"], stats["prompt_tokens"], stats["completion_tokens"]))
    print("压缩重试触发 %d 次（仅当主尝试 finish_reason=length）" % stats.get("fallback_calls", 0))
    print("耗时：%.1f 秒；产物清单 %d 个文件，清单哈希 %s"
          % (stats["wall_clock_seconds"], manifest["file_count"],
             manifest["manifest_sha256"][:16]))
    print("覆盖性重算与《15》声明值一致：%s" % coverage["matches_declared"])
    print("证据与本体核对见 %s" % config.OUTPUT_FILES["verify"])
    return 0 if not failures else 2


if __name__ == "__main__":
    sys.exit(main())
