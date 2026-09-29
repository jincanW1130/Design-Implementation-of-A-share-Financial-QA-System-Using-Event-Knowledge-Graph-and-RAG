# -*- coding: utf-8 -*-
r"""auto_annotate_repair.py —— 对 **flash 版**自动标注（模型参照集）做「定向修复」（提准）。

## 边界（先写清楚，别漏）

* 只处理 **flash 版**（`自动标注_flash\`）里 **lint 有命中的条目**；没命中的条目**一个字节都不动**
  （`*.auto.repaired.jsonl` 的行＝原行里只换 `annotation` 的字节手术，非命中条目原行照搬）。
  第二轮（`--round 2`）输入改读**首轮提准产物**（`自动标注\提准\*.auto.repaired.jsonl`），
  命中清单改读规则 v1.2 的 `lint_命中_flash.repaired.json`，**就地**重写同名产物；
  首轮记录在台账 `items`／报告上半部分**原样保留**，第二轮追加在台账 `第二轮` 键与报告下半部分，
  首轮产物另存快照 `_首轮快照\`。
* **只修「有硬命中」的条目**（作者 2026-09-27 裁定）：软提示 `S1`～`S4` **只登记、不进修复提示词、
  不改标注**——它们是指示性的，改了会放大规则误报。软命中的条目在台账里逐条留档
  （`soft_hits_not_repaired`），行字节照搬。
* 模型仍是 `deepseek-flash`（**禁止调用 `deepseek-v4-pro`**），temperature=0、max_tokens 沿用标注器
  自己的 16384；Prompt 版本 `stage6-auto-annotate-flash-repair-v1.0`（与标注器、与 pro 版都不同）。
* 提示词里的**输出 schema 与 quote 规则复用 `auto_annotate.py` 的**（`SYSTEM_PROMPT`／
  `render_schema()`／`REPAIR_TEMPLATE`），本脚本**不另抄一份**口径文本；
  `config.ontology_definitions_text()`、校验内核 `工具\标注助手.validate_annotation` 同样复用。
* 允许模型判**误报**：返回 `disputed: [{"rule": …, "reason": …}]` 时该规则不再改，台账逐条记。
* 校验最多回喂 3 轮；仍不过则**保留原标注**并标 `repair_failed`（不许放宽校验）。
* **模型自我修正不构成独立验证**：修复后重跑 lint 只说明「按同一套规则，命中少了多少」，
  不能当成「标注质量被独立证明」；这一句要原样进报告与文档。

## 用法

```powershell
python 代码\抽取与图谱\auto_annotate_repair.py run --workers 4     # 只修有命中的条目
python 代码\抽取与图谱\auto_annotate_repair.py run --limit 5       # 试跑
python 代码\抽取与图谱\auto_annotate_repair.py replay              # 只从缓存重放，0 次调用
python 代码\抽取与图谱\auto_annotate_repair.py selftest            # 离线自测（假传输层，0 次调用）
python 代码\抽取与图谱\auto_annotate_repair.py run --round 2 --input-dir "…\v2.1\自动标注\提准" `
  --input-suffix .auto.repaired --out-suffix .auto.repaired --lint "…\lint_命中_flash.repaired.json"
```

产物（默认落 `…\v2.1\自动标注\提准\`）：`dev.auto.repaired.jsonl`／`test.auto.repaired.jsonl`、
`提准台账.json`、`提准报告.md`、`工作区\{dev,test}\*.md`（可直接用
`python 工具\标注助手.py check --workspace "…\自动标注\提准\工作区" --eval-dir "…\v2.1"` 复核）、
`_缓存\<ITEM_ID>.json`（每次尝试的原始返回，可重放）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import sys
import threading
import time
from collections import Counter, OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402

ROOT = config.ROOT
HANDANN_PATH = os.path.join(ROOT, "工具", "标注助手.py")
EVAL_SUBDIR = "抽取评测集"
FLASH_DIRNAME = "自动标注_flash"
OUT_DIRNAME = os.path.join("自动标注", "提准")
REPAIR_CACHE_DIRNAME = "_缓存"
LEDGER_NAME = "提准台账.json"
REPORT_NAME = "提准报告.md"
WORKSPACE_DIRNAME = "工作区"

REPAIR_PROMPT_VERSION = "stage6-auto-annotate-flash-repair-v1.0"
REPAIR_MODEL_DEFAULT = "deepseek-flash"
REPAIR_TEMPERATURE = 0
REPAIR_MAX_TOKENS = 16384
MAX_ROUNDS = 3
LEDGER_SCHEMA = "stage6-auto-annotate-repair-ledger-1.0"
CACHE_SCHEMA = "stage6-auto-annotate-repair-cache-1.0"

REPAIR_SYSTEM_SUFFIX = (
    "\n\n【本次是「定向修复」】你在修一份已经产出、且被离线 lint 判为有命中的自动标注："
    "只按下面给出的**命中规则与定位**改；规则没命中到的地方不要顺手改（不许扩大改动面）。"
    "若你判断某条命中是 lint 的**误报**，把它写进 `disputed` 并给理由，**该处标签保持不动**。"
    "输出仍是一个 JSON 对象，顶层就两个键：`annotation`（完整标注，结构与 quote 规则与上一轮一致）"
    "与 `disputed`（数组，每项 {\"rule\": …, \"reason\": …}，没有就写 []）。"
    "**不得**为了消掉命中而删除本可成立的事实；确实撑不住的条目宁可删掉并在 notes 里如实登记。"
)


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handann = _load_module(HANDANN_PATH, "stage6_handann_repair")
auto = _load_module(os.path.join(_HERE, "auto_annotate.py"), "stage6_auto_annotate_repair")


def eval_dir() -> str:
    return os.path.join(config.DATASET_ROOT, EVAL_SUBDIR, config.DATASET_VERSION)


def flash_dir() -> str:
    return os.path.join(eval_dir(), FLASH_DIRNAME)


def out_dir() -> str:
    return os.path.join(eval_dir(), OUT_DIRNAME)


def lint_path() -> str:
    return os.path.join(out_dir(), "lint_命中_flash.json")


def cache_dir() -> str:
    return os.path.join(out_dir(), REPAIR_CACHE_DIRNAME)


def resolve_path(path: str) -> str:
    """把命令行给的相对路径按项目根解析（绝对路径原样返回）。"""
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.join(ROOT, path)


def round_cache_dir(round_no: int) -> str:
    """第二轮用**独立缓存目录**，避免与首轮同 item_id 的缓存指纹相互污染。"""
    return cache_dir() if int(round_no) <= 1 else os.path.join(cache_dir(), "第%d轮" % int(round_no))


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def read_jsonl(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def read_jsonl_lines(path: str) -> list:
    """返回 [(rec, 原始行去掉换行), …]：用于「只换 annotation」的字节手术。"""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append((json.loads(line), line.rstrip("\n")))
    return rows


def write_text_atomic(path: str, text: str) -> None:
    handann.write_text_atomic(path, text)


# --------------------------------------------------------------------------
# 命中清单 → 每条命中的「规则＋定位」
# --------------------------------------------------------------------------
def split_hits(payload: dict) -> dict:
    """把命中清单拆成 {item_id: {"hard": [...], "soft": [...]}}（两类都留档）。"""
    out = OrderedDict()
    for iid, res in (payload.get("items") or {}).items():
        bucket_out = OrderedDict([("hard", []), ("soft", [])])
        for kind, bucket in (("hard", res.get("hard") or {}), ("soft", res.get("soft") or {})):
            for rule_id, items in (bucket or {}).items():
                for h in (items or []):
                    bucket_out[kind].append(OrderedDict([
                        ("rule", rule_id), ("kind", kind),
                        ("location", h.get("location")), ("detail", h.get("detail")),
                    ]))
        if bucket_out["hard"] or bucket_out["soft"]:
            out[iid] = bucket_out
    return out


def load_hits(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    return split_hits(payload)


def render_repair_prompt(rec, annotation, hits, problems=None) -> str:
    """定向修复的 user prompt：本块＋全文＋现行标签＋命中规则与定位＋本体定义＋schema（复用标注器的）。"""
    lines = [
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
        auto.render_schema(),
        "",
        "────────────────────────────────────────",
        "【本条文本块（`text`，**标注对象**；`quote` 只能取自本段）】",
        str(rec.get("text") or ""),
        "",
        "────────────────────────────────────────",
        "【文档全文（`doc_text`，**仅作上下文**，不是标注对象；其原文不许抄进 quote）】",
        str(rec.get("doc_text") or ""),
        "",
        "────────────────────────────────────────",
        "【现行标签（上一版自动标注的完整 annotation，原样给你；要改就整份重写）】",
        "```json",
        json.dumps(annotation, ensure_ascii=False, indent=1),
        "```",
        "",
        "────────────────────────────────────────",
        "【离线 lint 的命中规则与定位（**只改这些点**；判为误报就写进 disputed）】",
    ]
    for i, h in enumerate(hits, 1):
        lines.append("  %d) [%s] %s｜%s｜%s"
                     % (i, h.get("kind"), h.get("rule"), h.get("location"), h.get("detail")))
    if problems:
        lines.append(auto.REPAIR_TEMPLATE % (len(problems), "\n".join(
            "  %d) 字段 `%s`：%s" % (i, p["field"], p["message"])
            for i, p in enumerate(problems, 1))))
    return "\n".join(lines)


def build_messages(rec, annotation, hits, problems=None) -> list:
    return [{"role": "system", "content": auto.SYSTEM_PROMPT + REPAIR_SYSTEM_SUFFIX},
            {"role": "user", "content": render_repair_prompt(rec, annotation, hits, problems)}]


def input_fingerprint(rec, annotation, hits, problems, model, prompt_version) -> str:
    """缓存键：条目全部抽样字段＋现行标签＋命中清单＋提示词模板＋本体定义＋模型＋temperature。"""
    payload = OrderedDict([
        ("item_record_sha256", sha256_text(config.stable_json(rec))),
        ("base_annotation_sha256", sha256_text(json.dumps(annotation, ensure_ascii=False, sort_keys=True))),
        ("hits", [[h.get("rule"), h.get("location"), h.get("detail")] for h in hits]),
        ("problems", [p["field"] + "|" + p["kind"] for p in (problems or [])]),
        ("system_prompt_sha256", sha256_text(auto.SYSTEM_PROMPT + REPAIR_SYSTEM_SUFFIX)),
        ("schema_sha256", sha256_text(auto.render_schema())),
        ("user_prompt_sha256", sha256_text(render_repair_prompt(rec, annotation, hits, problems))),
        ("model_requested", model),
        ("temperature", REPAIR_TEMPERATURE),
        ("max_tokens", REPAIR_MAX_TOKENS),
        ("prompt_version", prompt_version),
        ("ontology_defs_digest", config.ontology_definitions_digest()),
    ])
    return config.sha256_hex(config.stable_json(payload))


# --------------------------------------------------------------------------
# 模型调用（复用 config 的密钥／端点／限流；**不许**在重放模式下打接口）
# --------------------------------------------------------------------------
_PACE_LOCK = threading.Lock()
_LAST_CALL_TS = [0.0]


def _retryable(exc, openai_mod) -> bool:
    if openai_mod is not None and isinstance(
            exc, (openai_mod.APIConnectionError, openai_mod.APITimeoutError, openai_mod.RateLimitError)):
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and (status == 429 or status >= 500)


def invoke(client, openai_mod, rec, annotation, hits, problems, stats, model, prompt_version) -> dict:
    kwargs = {
        "model": model,
        "messages": build_messages(rec, annotation, hits, problems),
        "temperature": REPAIR_TEMPERATURE,
        "max_tokens": REPAIR_MAX_TOKENS,
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
            time.sleep(backoff)
            continue
        usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
        usage = {k: v for k, v in usage.items() if v is None or isinstance(v, (int, float, str, dict))}
        return OrderedDict([
            ("input_sha256", input_fingerprint(rec, annotation, hits, problems, model, prompt_version)),
            ("elapsed_ms", int((time.time() - started) * 1000)),
            ("transport_attempts", attempt),
            ("usage", usage),
            ("finish_reason", (response.choices[0].finish_reason if response.choices else None)),
            ("model_resolved", str(getattr(response, "model", "") or "")),
            ("response_text", (response.choices[0].message.content if response.choices else "")),
            ("round_problems", [p["field"] + "|" + p["kind"] for p in (problems or [])]),
            ("created_at", now_iso()),
        ])
    raise RuntimeError("模型调用失败且未抛出异常（不应到达）")


# --------------------------------------------------------------------------
# 解析、校验、复验
# --------------------------------------------------------------------------
def parse_repair_object(text) -> tuple:
    """解析修复返回：返回 (annotation, disputed)。兼容「顶层就是 annotation」的返回。"""
    obj = auto.parse_json_object(text)
    if isinstance(obj.get("annotation"), dict):
        ann = obj["annotation"]
        disputed = obj.get("disputed") if isinstance(obj.get("disputed"), list) else []
    else:
        ann = obj
        disputed = []
    return ann, disputed


def program_owned_problems(problems) -> list:
    kinds = getattr(auto, "_PROGRAM_OWNED_KINDS", ())
    return [p for p in problems
            if p["kind"] in kinds or (p.get("field") or "").startswith("provenance")]


def model_owned_problems(problems) -> list:
    owned = {id(p) for p in program_owned_problems(problems)}
    return [p for p in problems if id(p) not in owned]


def attach_provenance(ann, attempts, hits, disputed, model, prompt_version) -> OrderedDict:
    last = attempts[-1] if attempts else {}
    out = OrderedDict()
    out["status"] = handann.AUTO_STATUS
    for slot in ("entities", "events", "relations", "times", "ontology_boundary_log"):
        out[slot] = ann.get(slot) if isinstance(ann.get(slot), list) else []
    out["notes"] = ann.get("notes") or ""
    out["provenance"] = OrderedDict([
        ("annotator", "llm"),
        ("model", model),
        ("model_resolved", last.get("model_resolved") or ""),
        ("prompt_version", prompt_version),
        ("temperature", REPAIR_TEMPERATURE),
        ("generated_at", last.get("created_at") or now_iso()),
        ("attempts", len(attempts)),
        ("usage", auto.summarize_usage(attempts)),
        ("repair", OrderedDict([
            ("tool", "代码\\抽取与图谱\\auto_annotate_repair.py"),
            ("base_dir", os.path.relpath(flash_dir(), ROOT)),
            ("rules", sorted({h.get("rule") for h in hits})),
            ("disputed", disputed),
            ("note", "定向修复的产物：**模型自我修正不构成独立验证**，修复后命中数只说明"
                     "「按同一套 lint 规则命中少了多少」，不是标注质量的独立证明。"),
        ])),
    ])
    return out


def validate(rec, ann, cfg):
    return handann.validate_annotation(
        {"item_id": rec.get("item_id"), "chunk_id": rec.get("chunk_id"),
         "doc_id": rec.get("doc_id"), "text": rec.get("text"), "annotation": ann}, cfg)


def repair_one(rec, base_annotation, hits, client, openai_mod, stats, cfg, model, prompt_version,
               cache_record=None) -> dict:
    """跑完整条修复链（多轮调用＋校验），返回缓存记录。"""
    attempts = []
    problems = None
    final_ann, final_problems, disputed_all = None, None, []
    for _rnd in range(1, MAX_ROUNDS + 1):
        if cache_record is not None and len(attempts) < len(cache_record.get("attempts_detail") or []):
            detail = cache_record["attempts_detail"][len(attempts)]
        else:
            detail = invoke(client, openai_mod, rec, base_annotation, hits, problems, stats,
                            model, prompt_version)
        attempts.append(detail)
        try:
            ann_raw, disputed = parse_repair_object(detail["response_text"])
            ann, dropped = auto.normalize_annotation(ann_raw, rec, cfg)
            ann, dropped = auto.mechanical_repair(ann, dropped, cfg, rec)
            after = model_owned_problems(validate(rec, ann, cfg))
            detail["parse_ok"] = True
            detail["dropped"] = dropped
        except (ValueError, TypeError) as exc:
            ann, after = None, [{"field": "JSON", "kind": "parse_error",
                                 "message": "返回不是合法 JSON 对象：%s" % exc}]
            disputed = []
            detail["parse_ok"] = False
        detail["problems_after"] = [p["field"] + "|" + p["kind"] for p in after]
        detail["disputed"] = disputed
        if disputed:
            disputed_all = disputed
        final_ann, final_problems = ann, after
        if not after:
            break
        problems = after
    status = "repaired"
    if final_ann is None or final_problems:
        status = "repair_failed"
        final_ann = base_annotation
    else:
        final_ann = attach_provenance(final_ann, attempts, hits, disputed_all, model, prompt_version)
        leftover = validate(rec, final_ann, cfg)
        if leftover:
            status = "repair_failed"
            final_problems = leftover
            final_ann = base_annotation
    return OrderedDict([
        ("cache_schema", CACHE_SCHEMA),
        ("item_id", rec.get("item_id")),
        ("split", rec.get("split")),
        ("status", status),
        ("model_requested", model),
        ("model_resolved", (attempts[-1].get("model_resolved") if attempts else "")),
        ("prompt_version", prompt_version),
        ("temperature", REPAIR_TEMPERATURE),
        ("max_tokens", REPAIR_MAX_TOKENS),
        ("rounds", len(attempts)),
        ("hits_before", hits),
        ("disputed", disputed_all),
        ("final_problems", [p["field"] + "|" + p["kind"] for p in (final_problems or [])]),
        ("final_annotation", final_ann),
        ("final_annotation_sha256", sha256_text(json.dumps(final_ann, ensure_ascii=False, sort_keys=True))),
        ("attempts_detail", attempts),
        ("created_at", now_iso()),
    ])


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def process_item(rec, orig_line, base_annotation, hits, client, openai_mod, stats, cfg,
                 force, replay, lock, cache_path_dir=None) -> tuple:
    """返回 (新行文本, 缓存记录)。非命中条目：原行照搬、不写缓存、0 次调用。"""
    if not hits:
        return _ensure_nl(orig_line), None
    item_id = rec.get("item_id")
    path = os.path.join(cache_path_dir or cache_dir(), "%s.json" % item_id)
    cached = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            cached = json.load(fh)
    if cached is not None and not force:
        want = input_fingerprint(rec, base_annotation, hits, None, cached.get("model_requested"),
                                 cached.get("prompt_version"))
        first = (cached.get("attempts_detail") or [{}])[0]
        stored = first.get("input_sha256")
        # L-9：缓存记录若缺 attempts_detail[0].input_sha256，原先 `first` 退化成 {}、`stored` 为
        # None，指纹校验被整体跳过 → 旧答案被静默复用。此类条目一律视为**不可用**：
        # 本工具写出的缓存恒有 attempts_detail（见上方记录构造），缺失即说明来源可疑。
        if not stored:
            raise RuntimeError("item_id=%s 的提准缓存缺 attempts_detail[0].input_sha256，"
                               "无法核对输入一致性（删去该缓存或加 --force 重跑）" % item_id)
        if stored != want:
            raise RuntimeError("item_id=%s 的提准缓存与当前输入不一致（加 --force 重跑）" % item_id)
        with lock:
            stats["cache_hits"] += 1
        record = cached
    else:
        if replay:
            raise RuntimeError("replay：item_id=%s 的提准缓存缺失（缓存未命中即失败）" % item_id)
        if (os.environ.get("STAGE6_FORBID_MODEL_CALLS") or "").strip() == "1":
            raise RuntimeError("STAGE6_FORBID_MODEL_CALLS=1：禁止调用模型；item_id=%s 缓存未命中" % item_id)
        record = repair_one(rec, base_annotation, hits, client, openai_mod, stats, cfg,
                            REPAIR_MODEL_DEFAULT, REPAIR_PROMPT_VERSION)
        os.makedirs(cache_dir(), exist_ok=True)
        write_text_atomic(path, json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        with lock:
            stats["repaired"] += 1
    ann = record["final_annotation"]
    marker = ', "annotation": '
    pos = orig_line.rindex(marker)
    head = orig_line[:pos + len(marker)]
    tail = orig_line[pos + len(marker):]
    if not tail.endswith("}"):
        raise RuntimeError("item_id=%s 的原始行不以 annotation 结尾，字节手术不适用" % item_id)
    return head + json.dumps(ann, ensure_ascii=False) + "}\n", record


def _ensure_nl(line: str) -> str:
    """拼接 jsonl 前保证**恰好一个行尾换行**（`read_jsonl_lines` 会去掉行尾换行）。"""
    return line if line.endswith("\n") else line + "\n"


def cmd_run(args) -> int:
    cfg = handann._load_config()
    os.makedirs(out_dir(), exist_ok=True)
    os.makedirs(os.path.join(out_dir(), WORKSPACE_DIRNAME), exist_ok=True)
    round_no = int(getattr(args, "round", 1) or 1)
    cache_path_dir = round_cache_dir(round_no)
    os.makedirs(cache_path_dir, exist_ok=True)
    # 第二轮：输入＝首轮提准产物（不是 flash 原版），命中清单＝规则修正后的提准后 lint
    src_dir = resolve_path(args.input_dir) if getattr(args, "input_dir", None) else flash_dir()
    src_suffix = getattr(args, "input_suffix", None) or ".auto"
    out_suffix = getattr(args, "out_suffix", None) or ".auto.repaired"
    lint_file = (resolve_path(args.lint) if getattr(args, "lint", None) else lint_path())
    if not os.path.isfile(lint_file):
        raise SystemExit("缺少 %s：先跑 `auto_annotate_lint.py lint --version flash`" % lint_file)
    hits_by_item = load_hits(lint_file)
    if round_no > 1:
        print("第 %d 轮：输入 %s（后缀 %s）｜命中清单 %s｜输出后缀 %s"
              % (round_no, src_dir, src_suffix, lint_file, out_suffix))
    splits = ["dev", "test"] if args.split == "all" else [args.split]

    truth = {}
    for split in ("dev", "test"):
        for r in read_jsonl(os.path.join(eval_dir(), "%s.jsonl" % split)):
            truth[r["item_id"]] = r

    todo = []
    for split in splits:
        src = os.path.join(src_dir, "%s%s.jsonl" % (split, src_suffix))
        if not os.path.isfile(src):
            print("跳过 %s：%s 不存在" % (split, src))
            continue
        for rec, line in read_jsonl_lines(src):
            todo.append((split, rec, line))
    if args.limit:
        todo = todo[:args.limit]
    # 只修**硬命中**条目；软提示（R3／S1～S4）只登记，不进提示词、不改标注（作者 2026-09-27 裁定）
    hard_by_item = OrderedDict((iid, e["hard"]) for iid, e in hits_by_item.items() if e["hard"])
    soft_by_item = OrderedDict((iid, e["soft"]) for iid, e in hits_by_item.items()
                               if e["soft"] and not e["hard"])
    hit_items = [t for t in todo if hard_by_item.get(t[1]["item_id"])]
    print("提准：待处理 %d 条（其中**硬命中** %d 条、软命中仅登记 %d 条、软＋硬重叠 %d 条）"
          "｜模型 %s｜Prompt %s｜workers %d"
          % (len(todo), len(hit_items), len(soft_by_item),
             sum(1 for iid, e in hits_by_item.items() if e["hard"] and e["soft"]),
             REPAIR_MODEL_DEFAULT, REPAIR_PROMPT_VERSION, args.workers))

    replay = bool(args.replay)
    force = bool(args.force)
    if replay:
        os.environ["STAGE6_FORBID_MODEL_CALLS"] = "1"
        force = False
    stats = {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "repaired": 0}
    lock = threading.Lock()
    client = openai_mod = None
    need_api = (not replay) and any(
        force or not os.path.isfile(os.path.join(cache_path_dir, "%s.json" % t[1]["item_id"]))
        for t in hit_items)
    if need_api:
        import openai
        openai_mod = openai
        client = openai.OpenAI(api_key=cfg.api_key(), base_url=cfg.base_url(),
                               timeout=cfg.LLM["timeout_seconds"], max_retries=0)

    started = time.time()
    results = OrderedDict()
    errors = []
    if args.workers <= 1 or replay:
        for split, rec, line in todo:
            try:
                new_line, record = process_item(rec, line, rec.get("annotation") or {},
                                                hard_by_item.get(rec["item_id"]), client, openai_mod,
                                                stats, cfg, force, replay, lock,
                                                cache_path_dir=cache_path_dir)
                results[rec["item_id"]] = (split, new_line, record)
            except Exception as exc:  # noqa: BLE001
                errors.append((rec["item_id"], "%s: %s" % (type(exc).__name__, exc)))
    else:
        import queue
        q = queue.Queue()
        for item in todo:
            q.put(item)
        out_lock = threading.Lock()

        def worker():
            while True:
                try:
                    split, rec, line = q.get_nowait()
                except queue.Empty:
                    return
                try:
                    new_line, record = process_item(rec, line, rec.get("annotation") or {},
                                                    hard_by_item.get(rec["item_id"]), client,
                                                    openai_mod, stats, cfg, force, replay, lock,
                                                    cache_path_dir=cache_path_dir)
                    with out_lock:
                        results[rec["item_id"]] = (split, new_line, record)
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
        print("有 %d 条失败（不写盘）：" % len(errors))
        for iid, msg in errors[:10]:
            print("  %s：%s" % (iid, msg))
        return 1

    # ---- 写 jsonl（字节手术：非命中条目原行照搬）----
    by_split = OrderedDict()
    ledger_rows = OrderedDict()
    for _split, rec, _line in todo:
        split, new_line, record = results[rec["item_id"]]
        by_split.setdefault(split, []).append(_ensure_nl(new_line))
        if record is not None:
            ledger_rows[rec["item_id"]] = record
    for split, lines in by_split.items():
        write_text_atomic(os.path.join(out_dir(), "%s%s.jsonl" % (split, out_suffix)), "".join(lines))

    # ---- 工作区物化：命中条目＝修复后标签；非命中条目＝输入集合的工作区原字节 ----
    eval_relpath = os.path.relpath(eval_dir(), ROOT)
    copied = 0
    for _split, rec, _line in todo:
        split, _new_line, record = results[rec["item_id"]]
        dst = os.path.join(out_dir(), WORKSPACE_DIRNAME, split, "%s.md" % rec["item_id"])
        if record is None:
            src = os.path.join(src_dir, WORKSPACE_DIRNAME, split, "%s.md" % rec["item_id"])
            with open(src, "rb") as fh:
                blob = fh.read()
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as fh:
                fh.write(blob)
            copied += 1
        else:
            content = handann.render_item(truth[rec["item_id"]], cfg, eval_relpath)
            i = content.find(handann.MARK_ANN_BEGIN) + len(handann.MARK_ANN_BEGIN)
            j = content.find(handann.MARK_ANN_END)
            body = "\n```json\n%s\n```\n" % json.dumps(record["final_annotation"],
                                                       ensure_ascii=False, indent=2)
            write_text_atomic(dst, content[:i] + body + content[j:])
    print("工作区物化：%d 条照搬输入集合工作区原字节｜%d 条按修复后标签重写"
          % (copied, len(ledger_rows)))

    write_ledger_and_report(args, cfg, results, stats, wall, hard_by_item,
                            hits_by_item=hits_by_item, src_dir=src_dir, src_suffix=src_suffix,
                            lint_file=lint_file, round_no=round_no)
    print("提准完成：处理 %d 条（硬命中 %d 条）｜API 调用 %d 次（传输层重试 %d）｜缓存命中 %d｜"
          "修复成功 %d｜墙钟 %.1f 秒"
          % (len(todo), len(hit_items), stats["api_calls"], stats["transport_retries"],
             stats["cache_hits"],
             sum(1 for r in ledger_rows.values() if r["status"] == "repaired"), wall))
    print("产物：%s" % out_dir())
    return 0


def write_ledger_and_report(args, cfg, results, stats, wall, hard_by_item, hits_by_item=None,
                            src_dir=None, src_suffix=".auto", lint_file=None, round_no=1) -> None:
    """写台账与报告。`round_no>1` 时**保留首轮记录**，把第二轮追加为 `第二轮` 一段。"""
    src_dir = src_dir or flash_dir()
    lint_file = lint_file or lint_path()
    round_no = int(round_no or 1)
    rows = OrderedDict()
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "reasoning_tokens": 0}
    status_counter = Counter()
    elapsed_ms = 0
    before_counts = {}
    for _split in ("dev", "test"):
        src = os.path.join(src_dir, "%s%s.jsonl" % (_split, src_suffix))
        if not os.path.isfile(src):
            continue
        for _rec in read_jsonl(src):
            _ann = _rec.get("annotation") or {}
            before_counts[_rec["item_id"]] = {
                k: len(_ann.get(k) or []) for k in ("entities", "events", "relations", "times")}
    hits_by_item = hits_by_item or OrderedDict((iid, {"hard": h, "soft": []})
                                               for iid, h in hard_by_item.items())
    soft_rows = OrderedDict()
    for iid, e in sorted(hits_by_item.items()):
        if e.get("soft") and not e.get("hard"):
            soft_rows[iid] = [OrderedDict([("rule", h.get("rule")), ("location", h.get("location")),
                                           ("detail", h.get("detail"))]) for h in e["soft"]]
    for iid, (_split, _line, record) in sorted(results.items()):
        if record is None:
            continue
        usage = auto.summarize_usage(record.get("attempts_detail") or [])
        for k in total:
            total[k] += usage[k]
        status_counter[record["status"]] += 1
        for a in (record.get("attempts_detail") or []):
            try:
                elapsed_ms += int(a.get("elapsed_ms") or 0)
            except (TypeError, ValueError):
                pass
        rows[iid] = OrderedDict([
            ("item_id", iid), ("split", record.get("split")), ("status", record.get("status")),
            ("rounds", record.get("rounds")), ("usage", usage),
            ("hits_before", record.get("hits_before")), ("disputed", record.get("disputed")),
            ("final_problems", record.get("final_problems")),
            ("model_resolved", record.get("model_resolved")),
            ("final_annotation_sha256", record.get("final_annotation_sha256")),
            ("created_at", record.get("created_at")),
        ])
    params = OrderedDict([("model", REPAIR_MODEL_DEFAULT),
                          ("temperature", REPAIR_TEMPERATURE),
                          ("max_tokens", REPAIR_MAX_TOKENS),
                          ("prompt_version", REPAIR_PROMPT_VERSION),
                          ("max_rounds", MAX_ROUNDS)])
    counts = OrderedDict([
        ("items_with_hard_hits", len(hard_by_item)),
        ("items_with_hits", len(hits_by_item)),
        ("items_soft_only_not_repaired", len(soft_rows)),
        ("items_processed", len(rows)),
        ("api_calls", stats["api_calls"]),
        ("transport_retries", stats["transport_retries"]),
        ("cache_hits", stats["cache_hits"]),
        ("usage_total", total),
        ("status", OrderedDict(status_counter)),
        ("wall_seconds", round(wall, 1)),
        ("model_elapsed_seconds_total", round(elapsed_ms / 1000.0, 1)),
    ])
    round_block = OrderedDict([("参数", params), ("lint_source", os.path.relpath(lint_file, ROOT)),
                               ("counts", counts), ("items", rows),
                               ("soft_hits_not_repaired", soft_rows)])
    dispo = ("**定向修复（提准）不是独立验证**：修复模型与标注模型同源（`%s`），"
             "修复只按离线 lint 的命中清单改；「修复后命中减少」只说明按同一套规则少命中，"
             "不能当成标注质量被独立证明。pro 版**不进本流程**，仍作对照。" % REPAIR_MODEL_DEFAULT)
    ledger_path = os.path.join(out_dir(), LEDGER_NAME)
    if round_no <= 1:
        ledger = OrderedDict([
            ("schema", LEDGER_SCHEMA), ("tool", "代码\\抽取与图谱\\auto_annotate_repair.py"),
            ("定位", dispo), ("参数", params),
            ("lint_source", os.path.relpath(lint_file, ROOT)),
            ("counts", counts), ("items", rows), ("soft_hits_not_repaired", soft_rows),
        ])
    else:
        existing = OrderedDict()
        if os.path.isfile(ledger_path):
            with open(ledger_path, encoding="utf-8") as fh:
                existing = OrderedDict(json.load(fh))
        if not existing.get("items"):
            raise RuntimeError("第二轮写入前没读到首轮台账（%s）——拒绝覆盖，先确认首轮产物在位" % ledger_path)
        ledger = existing
        ledger["schema"] = LEDGER_SCHEMA
        ledger["tool"] = "代码\\抽取与图谱\\auto_annotate_repair.py"
        ledger["定位"] = dispo
        ledger["第二轮"] = OrderedDict([
            ("说明", "规则 v1.2（R9 加 ISSUED_BY 豁免／R6 收窄／R3 降级为软提示）后，"
                     "对**仍有硬命中**的条目做的第二轮定向修复。输入＝首轮的 "
                     "`*.auto.repaired.jsonl`（首轮产物快照见 `_首轮快照\\`），"
                     "命中清单＝规则 v1.2 的 `lint_命中_flash.repaired.json`；"
                     "非命中条目字节照搬首轮产物；首轮的参数／lint_source／counts／items 原样保留。"),
            ("参数", params), ("lint_source", os.path.relpath(lint_file, ROOT)),
            ("counts", counts), ("items", rows), ("soft_hits_not_repaired", soft_rows),
        ])
    write_text_atomic(ledger_path, json.dumps(ledger, ensure_ascii=False, indent=2) + "\n")
    def _report_block(title, extra_lines=()):
        blk = [title, ""] + list(extra_lines) + [
            "> **这不是独立验证**：修复模型 `%s` 与标注模型同源，修复依据是离线 lint 的命中清单；"
            % REPAIR_MODEL_DEFAULT,
            "> 「修复后命中数下降」只说明按同一套规则命中变少，不构成标注质量的独立证明。",
            "> 命中清单：`%s`。" % os.path.relpath(lint_file, ROOT), "",
            "| 项 | 值 |", "| --- | --- |",
            "| 有硬命中的条目（**修复触发范围**） | %d |" % len(hard_by_item),
            "| lint 有命中（硬或软）的条目 | %d |" % len(hits_by_item),
            "| **软命中、只登记不改**的条目 | %d（R3／S1～S4；不进修复提示词） |" % len(soft_rows),
            "| 实际处理条目 | %d |" % len(rows),
            "| API 调用 | %d（传输层重试 %d） |" % (stats["api_calls"], stats["transport_retries"]),
            "| 缓存命中 | %d |" % stats["cache_hits"],
            "| token | prompt %d／completion %d／reasoning %d／total %d |"
            % (total["prompt_tokens"], total["completion_tokens"], total["reasoning_tokens"],
               total["total_tokens"]),
            "| 墙钟 | %.1f 秒 |" % wall,
            "| 状态 | %s |" % ("；".join("%s %d 条" % (k, v) for k, v in sorted(status_counter.items()))
                                or "无"),
            "| 模型／Prompt | `%s`／`%s` |" % (REPAIR_MODEL_DEFAULT, REPAIR_PROMPT_VERSION),
            "", "逐条明细见 `%s`。" % LEDGER_NAME]
        if rows:
            blk += ["", "## 改动明细（修复前后逐条：各槽位条数变化；负数＝删减，正数＝新增）", "",
                    "| item_id | split | 状态 | 轮数 | 命中规则（前） | 实体 | 事件 | 关系 | times | disputed |",
                    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
            for iid, row in rows.items():
                rec = results[iid][2]
                after = rec["final_annotation"]
                b = before_counts.get(iid) or {}
                a = {k: len(after.get(k) or []) for k in ("entities", "events", "relations", "times")}

                def _d(k):
                    return ("%d→%d（%+d）" % (b.get(k, 0), a[k], a[k] - b.get(k, 0))
                            if k in b else "%d" % a[k])
                rules = "、".join(sorted({h.get("rule") for h in (rec.get("hits_before") or [])}))
                dis = "；".join("%s：%s" % (d.get("rule"), (d.get("reason") or "")[:60])
                                for d in (rec.get("disputed") or []))
                blk.append("| `%s` | %s | %s | %d | `%s` | %s | %s | %s | %s | %s |"
                           % (iid, row["split"], row["status"], row["rounds"], rules,
                              _d("entities"), _d("events"), _d("relations"), _d("times"),
                              dis or "—"))
        if soft_rows:
            blk += ["", "## 软命中（只登记、未进修复）", "",
                    "| item_id | 规则 | 定位 | 提示 |", "| --- | --- | --- | --- |"]
            for iid, hs in soft_rows.items():
                for h in hs:
                    blk.append("| `%s` | `%s` | %s | %s |"
                               % (iid, h["rule"], h.get("location"), (h.get("detail") or "")[:160]))
        return blk

    report_path = os.path.join(out_dir(), REPORT_NAME)
    if round_no <= 1:
        L = _report_block("# 自动提准报告（flash 版定向修复）")
    else:
        prev = ""
        if os.path.isfile(report_path):
            # L-11：用 with 关闭句柄（原先 open(...).read() 依赖 CPython 引用计数回收）。
            with open(report_path, encoding="utf-8") as fh:
                prev = fh.read()
        # 首轮报告的 `%s` 未格式化（历史缺陷），第二轮顺手修正引用文本；其余内容原样保留
        prev = prev.replace("修复模型 `%s` 与标注模型同源",
                            "修复模型 `%s` 与标注模型同源" % REPAIR_MODEL_DEFAULT)
        L = [prev.rstrip("\n"), "", "---", ""]
        L += _report_block(
            "# 第二轮定向修复（规则 v1.2 修正后，2026-09-27）",
            ["", "> 本段之上的表格是**首轮**报告（原样保留）。第二轮只处理规则 v1.2 下**仍命中硬规则**的条目；",
             "> 输入＝首轮 `*.auto.repaired.jsonl`（快照见 `_首轮快照\\`），非命中条目**字节照搬**首轮产物。",
             "> 首轮记录在 `%s` 里原样保留，第二轮追加在 `第二轮` 键下。" % LEDGER_NAME])
    write_text_atomic(report_path, "\n".join(L) + "\n")


# --------------------------------------------------------------------------
# 离线自测（假传输层，0 次真实调用）
# --------------------------------------------------------------------------
class _FakeUsage:
    def __init__(self):
        self._data = {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150,
                      "completion_tokens_details": {"reasoning_tokens": 20}}

    def model_dump(self):
        return dict(self._data)


class _FakeResponse:
    def __init__(self, text, model="deepseek-flash"):
        choice = type("C", (), {"finish_reason": "stop",
                                "message": type("M", (), {"content": text})()})()
        self.choices = [choice]
        self.usage = _FakeUsage()
        self.model = model


class _FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.script:
            raise AssertionError("假传输层脚本用完了（自测用例设计有误）")
        return _FakeResponse(self.script.pop(0))


class _FakeClient:
    def __init__(self, script):
        self.completions = _FakeCompletions(script)
        self.chat = type("Chat", (), {"completions": self.completions})()


def _stub_rec_and_ann() -> tuple:
    rec = OrderedDict([
        ("item_id", "ST-REPAIR-1"), ("split", "dev"), ("category", "公告"),
        ("publish_time", "2026-09-01"), ("title", "自测"), ("chunk_id", 9990001),
        ("doc_id", 999), ("company_list", ["000001"]), ("subject_companies", ["000001"]),
        ("text", "平安银行与万科A于2026年3月5日签署重大合同，合同金额一亿元。"),
        ("doc_text", "平安银行与万科A于2026年3月5日签署重大合同，合同金额一亿元。"),
    ])
    base = OrderedDict([
        ("status", "auto_annotated"),
        ("entities", [OrderedDict([("entity_type", "Company"), ("entity_ref", "E1"),
                                   ("quote", "平安银行与万科A于2026年3月5日签署重大合同"),
                                   ("chunk_id", 9990001), ("stock_code", "000002"),
                                   ("company_name", "平安银行"), ("short_name", "平安银行"),
                                   ("aliases", []), ("exchange", "深圳证券交易所")])]),
        ("events", []), ("relations", []), ("times", []), ("ontology_boundary_log", []),
        ("notes", ""),
    ])
    return rec, base


def cmd_selftest(args) -> int:
    cfg = handann._load_config()
    rec, base_ann = _stub_rec_and_ann()
    hits = [OrderedDict([("rule", "R2_code_source"), ("kind", "hard"),
                         ("location", "entities[0]"), ("detail", "代码与名字核不到")])]
    fixed_ann = OrderedDict(base_ann)
    fixed_ann["entities"] = [OrderedDict(list(base_ann["entities"][0].items()))]
    fixed_ann["entities"][0]["stock_code"] = "000001"
    broken_ann = OrderedDict(base_ann)
    broken_ann["entities"] = [OrderedDict(list(base_ann["entities"][0].items()))]
    broken_ann["entities"][0]["quote"] = "这段文字不在本块里"
    checks = []
    os.environ.pop("STAGE6_FORBID_MODEL_CALLS", None)

    # ① 两轮收敛：第一轮 quote 不在本块 → 回喂；第二轮通过
    client = _FakeClient([json.dumps({"annotation": broken_ann, "disputed": []}, ensure_ascii=False),
                          json.dumps({"annotation": fixed_ann, "disputed": []}, ensure_ascii=False)])
    stats = {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "repaired": 0}
    record = repair_one(rec, base_ann, hits, client, None, stats, cfg,
                        "deepseek-flash", "selftest-prompt")
    checks.append(("修复成功（两轮收敛）", record["status"] == "repaired" and record["rounds"] == 2))
    checks.append(("修复后代码已改对",
                   record["final_annotation"]["entities"][0]["stock_code"] == "000001"))
    checks.append(("provenance 带修复块",
                   record["final_annotation"]["provenance"]["repair"]["base_dir"].endswith(FLASH_DIRNAME)))
    checks.append(("校验器接受修复结果", not validate(rec, record["final_annotation"], cfg)))
    checks.append(("假传输层确实被调了两次", len(client.completions.calls) == 2))

    # ② 三轮都不合格 → 保留原标注、标 repair_failed
    client = _FakeClient([json.dumps({"annotation": broken_ann, "disputed": []},
                                     ensure_ascii=False)] * 3)
    stats = {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "repaired": 0}
    record = repair_one(rec, base_ann, hits, client, None, stats, cfg,
                        "deepseek-flash", "selftest-prompt")
    checks.append(("三轮不收敛 → repair_failed", record["status"] == "repair_failed"))
    checks.append(("repair_failed 保留原标注", record["final_annotation"] == base_ann))

    # ③ disputed 记录
    client = _FakeClient([json.dumps({"annotation": base_ann,
                                      "disputed": [{"rule": "R2_code_source",
                                                    "reason": "自测：认为规则误报"}]},
                                     ensure_ascii=False)])
    stats = {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "repaired": 0}
    record = repair_one(rec, base_ann, hits, client, None, stats, cfg,
                        "deepseek-flash", "selftest-prompt")
    checks.append(("disputed 进台账",
                   record["status"] == "repaired" and bool(record["disputed"])
                   and record["disputed"][0]["rule"] == "R2_code_source"))

    # ④ 缓存键覆盖
    fp0 = input_fingerprint(rec, base_ann, hits, None, "deepseek-flash", "p1")
    fp1 = input_fingerprint(rec, fixed_ann, hits, None, "deepseek-flash", "p1")
    fp2 = input_fingerprint(rec, base_ann, [], None, "deepseek-flash", "p1")
    fp3 = input_fingerprint(rec, base_ann, hits, None, "deepseek-v4-pro", "p1")
    fp4 = input_fingerprint(rec, base_ann, hits, None, "deepseek-flash", "p2")
    checks.append(("现行标签变 → 缓存键变", fp1 != fp0))
    checks.append(("命中清单变 → 缓存键变", fp2 != fp0))
    checks.append(("模型变 → 缓存键变", fp3 != fp0))
    checks.append(("Prompt 版本变 → 缓存键变", fp4 != fp0))

    # ⑤ 提示词复用标注器的 schema 与 quote 规则、含本体定义
    prompt = render_repair_prompt(rec, base_ann, hits)
    checks.append(("提示词含现行标签", "现行标签" in prompt))
    checks.append(("提示词含命中清单", "R2_code_source" in prompt))
    checks.append(("提示词含本体定义", config.ontology_definitions_text()[:40] in prompt))
    checks.append(("提示词含 schema（复用标注器 render_schema）",
                   "ontology_boundary_log" in prompt and "participants" in prompt))
    checks.append(("系统提示词复用标注器（quote 逐字引用规则）",
                   "原文逐字引用" in (auto.SYSTEM_PROMPT + REPAIR_SYSTEM_SUFFIX)))
    checks.append(("system 与 user 两条消息", len(build_messages(rec, base_ann, hits)) == 2))

    # ⑥ 非命中条目一个字节都不动
    line = json.dumps(OrderedDict(list(rec.items()) + [("annotation", base_ann)]),
                      ensure_ascii=False)
    new_line, record = process_item(rec, line, base_ann, [], None, None,
                                    {"api_calls": 0, "transport_retries": 0,
                                     "cache_hits": 0, "repaired": 0}, cfg, False, False,
                                    threading.Lock())
    checks.append(("非命中条目原字节照搬＋补回行尾换行（0 调用、无缓存记录）",
                   new_line == line + "\n" and record is None))
    # ⑦ 拼接后每个物理行都是合法 JSON（2026-09-27 修：未命中行曾因缺换行与下一行粘连）
    line2 = json.dumps(OrderedDict(list(rec.items())[:1] + [("annotation", base_ann)]),
                       ensure_ascii=False)
    l1, _ = process_item(rec, line, base_ann, [], None, None,
                         {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "repaired": 0},
                         cfg, False, False, threading.Lock())
    l2, _ = process_item(rec, line2, base_ann, [], None, None,
                         {"api_calls": 0, "transport_retries": 0, "cache_hits": 0, "repaired": 0},
                         cfg, False, False, threading.Lock())
    joined = [x for x in (l1 + l2).splitlines() if x.strip()]
    ok_join = len(joined) == 2
    try:
        ok_join = ok_join and all(isinstance(json.loads(x), dict) for x in joined)
    except ValueError:
        ok_join = False
    checks.append(("非命中行拼接后每行都是合法 JSON（不粘连）", ok_join))
    checks.append(("_ensure_nl 不重复加换行", _ensure_nl("x\n") == "x\n" and _ensure_nl("x") == "x\n"))

    # ⑧ 硬／软命中分流（作者 2026-09-27 裁定：软命中只登记、不改）
    fake_payload = {"items": {
        "X-HARD": {"hard": {"R2_code_source": [{"location": "entities[0]",
                                                "detail": "硬命中"}]}, "soft": {}},
        "X-SOFT": {"hard": {}, "soft": {"S1_quote_not_supporting_name": [
            {"location": "entities[0]", "detail": "软提示"}]}},
        "X-BOTH": {"hard": {"R9_event_without_participant": [{"location": "events[0]",
                                                              "detail": "硬"}]},
                   "soft": {"S2_procedural_event_name": [{"location": "events[0]",
                                                          "detail": "软"}]}},
    }}
    split = split_hits(fake_payload)
    checks.append(("硬／软分流：三条都进清单",
                   set(split) == {"X-HARD", "X-SOFT", "X-BOTH"}))
    checks.append(("软命中不进硬清单（X-SOFT 不触发修复）", not split["X-SOFT"]["hard"]))
    checks.append(("硬＋软同条：硬清单只含 R9",
                   [h["rule"] for h in split["X-BOTH"]["hard"]] == ["R9_event_without_participant"]
                   and [h["rule"] for h in split["X-BOTH"]["soft"]] == ["S2_procedural_event_name"]))

    failed = 0
    print("提准脚本离线自测（假传输层，0 次真实调用）：")
    for name, ok in checks:
        failed += 0 if ok else 1
        print("  [%s] %s" % ("OK" if ok else "FAIL", name))
    print("提准自测：%s（退出码 %d）"
          % ("全部通过" if not failed else "%d 项失败" % failed, 1 if failed else 0))
    return 1 if failed else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="auto_annotate_repair.py",
        description="对 flash 版自动标注做定向修复（提准）：只改 lint 有命中的条目，模型仍是 deepseek-flash。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")
    pr = sub.add_parser("run", help="执行定向修复")
    pr.add_argument("--split", default="all", choices=["all", "dev", "test"])
    pr.add_argument("--limit", type=int, default=0)
    pr.add_argument("--workers", type=int, default=4)
    pr.add_argument("--force", action="store_true", help="忽略提准缓存，重新调用")
    pr.add_argument("--replay", action="store_true", help="只从提准缓存重放，0 次调用")
    pr.add_argument("--round", type=int, default=1, choices=[1, 2],
                    help="1＝首轮（输入 flash 原版）；2＝第二轮（输入首轮提准产物，台账保留首轮并追加「第二轮」）")
    pr.add_argument("--input-dir", default=None,
                    help="输入目录（相对项目根；第二轮＝ `…\\v2.1\\自动标注\\提准`）")
    pr.add_argument("--input-suffix", default=None,
                    help="输入 jsonl 后缀（默认 .auto；第二轮用 .auto.repaired）")
    pr.add_argument("--out-suffix", default=None,
                    help="输出 jsonl 后缀（默认 .auto.repaired；第二轮就地重写同名文件）")
    pr.add_argument("--lint", default=None,
                    help="命中清单路径（默认 lint_命中_flash.json；第二轮用 lint_命中_flash.repaired.json）")
    sub.add_parser("selftest", help="离线自测（假传输层，0 次调用）")
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
    cmd = args.command or "run"
    if cmd == "selftest":
        return cmd_selftest(args)
    if getattr(args, "replay", False) and getattr(args, "force", False):
        raise SystemExit("--replay 与 --force 互斥")
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
