# -*- coding: utf-8 -*-
r"""extract_event_time.py —— 定向时间补抽（T3.5，两级抽取的第二级）。

**为什么有这一级**：T3（`extract.py`）的固定口径是「正文不能确定到日时写 null，绝不猜测」，
全量 709 篇实测 1649 条事件里 989 条 `event_time` 为 null。主抽取缓存与 `extract.py`
**不动**（重放逐字节不变），补抽在**另一份独立缓存**上做第二级：只对 `event_time` 为 null 的
事件，把「事件类型／事件名称／证据引文／引文周围的有界窗口／文档发布时间」拼成一个小提示词，
只问模型两件事——这个事件的日期、这个日期凭什么（依据标记）。

| 产物 | 落点 | 内容 |
| --- | --- | --- |
| 补抽缓存 | `阶段05-数据准备\数据集\_抽取缓存\v2.1\时间补抽\{event_id}.json` | 逐条原始返回、模型、prompt 版本、输入 sha256、窗口 sha256（**只有这些**，解析与复核每次重算） |
| 覆盖层 | `代码\抽取与图谱\_全量\v2.1\event_time_backfill.json`（pilot 落 `_试跑\`） | 逐条结果（日期＋`event_time_basis`＋证据引文＋复核读数），**无时间戳、逐字节可重放**；`dedup_events.py` 只读它 |
| 报告 | 同目录 `event_time_backfill_report.json` | 运行读数（调用次数／token／墙钟）、依据分布、复核统计、10 条抽样 |
| 度量 | 同目录 `时间覆盖_度量.json`（`--measure`） | 时间覆盖与可过滤性指标（补抽前／后） |

口径（逐条对应《15》第五节 硬约束与本次任务的两条修复要求）：

1. **只处理 null 事件**：`event_time` 非空的事件一个字节都不改（T3 已核验过正文渲染）。
2. **日期书写形式**：`2026 年8 月27 日`（数字与 CJK 之间夹空格）与 `2026年8月27日`／
   `2026-08-27`／`2026/8/27`／`2026.8.27` 等价——提示词里写明，复核在**去掉全部空白**的
   窗口副本上比对（与 T3 的 `date_rendering_in_document` 同一口径，多一项「空格外写法」）。
3. **日期可以出现在窗口的任何位置**：只要窗口里写出的日期是在描述本事件（不必落在证据引文
   之内），就可以采用；模型必须在 `evidence_quote` 里逐字抄出承载该日期的那一句。
4. **年份锚定规则（确定性、不猜）**：窗口只给「月日」时，年份由文档的 `publish_time` 锚定——
   月 ≤ 发布月 → 发布年；否则 发布年 − 1。该结果记 `event_time_basis="year_from_publish"`，
   **绝不记成 stated**；且月日必须在窗口里**独立出现**（前面不带年份、后面不带数字）才认定。
5. **`event_time_basis` 三值**：`stated`（正文明确写出年月日）／`year_from_publish`（月日＋锚定
   年份）／`null`（窗口里确实没有可归属的日期）。复核不过的一律回到 `null` 并在结果里写明原因。
6. **绝不编日期**：模型给的日期必须在窗口里复核得到；复核规则不用模糊匹配、不做编辑距离。
7. **确定性重放**：缓存命中即不调用模型（不需要密钥、不需要网络），覆盖层逐字节一致；
   缓存缺失或输入不一致时按《15》第十一节 阻断，不静默降级。
8. **不新增本体、不改主缓存、不调数据库**：产品侧只多一个覆盖层与两份审计文件。

用法：

    python 代码\抽取与图谱\extract_event_time.py --profile v21            # 全量补抽（未命中的才调模型）
    python 代码\抽取与图谱\extract_event_time.py --profile v21 --limit 3   # 先跑前 3 条（联机自检）
    python 代码\抽取与图谱\extract_event_time.py --profile v21 --docs 1373,2011
    python 代码\抽取与图谱\extract_event_time.py --profile v21 --verify     # 只重算复核、写零字节、零调用
    python 代码\抽取与图谱\extract_event_time.py --profile v21 --measure    # 只算时间覆盖／可过滤性指标
    python 代码\抽取与图谱\extract_event_time.py --profile v21 --force      # 忽略缓存重调（会花钱）

退出码：`0` 成功；`1` 阻断（缓存与当前输入不一致且未 `--force`／需要密钥但未就位）；
`2` 复核不通过（`--verify` 与磁盘产物不一致，或缓存缺条）。
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

SPEC = config.EVENT_TIME_BACKFILL


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def now_iso() -> str:
    tz = _dt.timezone(_dt.timedelta(hours=8))
    return _dt.datetime.now(tz).isoformat(timespec="seconds")


def read_jsonl(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def dump_json(path, obj, indent=2):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def sha256_text(text) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    if not path or not os.path.isfile(path):
        return ""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def rel(path) -> str:
    return os.path.relpath(path, config.ROOT).replace("\\", "/")


_WS_RE = re.compile(r"[\s\u3000]+")


def strip_ws(text) -> str:
    """去掉全部空白（含全角空格）：与 config.EVIDENCE["normalize"] 同一口径。"""
    return _WS_RE.sub("", str(text or ""))


def compact_map(text):
    """返回 (去空白副本, 去空白副本每个字符在原串中的下标)。"""
    chars, index = [], []
    for position, char in enumerate(str(text or "")):
        if char.isspace() or char == "\u3000":
            continue
        chars.append(char)
        index.append(position)
    return "".join(chars), index


def find_in_text(haystack, needle):
    """折空白后的精确子串查找；返回 (原串起始下标, 原串结束下标) 或 None。"""
    compact, index = compact_map(haystack)
    target = strip_ws(needle)
    if not target or not compact:
        return None
    position = compact.find(target)
    if position < 0:
        return None
    return index[position], index[position + len(target) - 1] + 1


# --------------------------------------------------------------------------
# 日期书写形式与复核（含「数字与 CJK 之间夹空格」的语料写法）
# --------------------------------------------------------------------------
def date_renderings(iso_date):
    """`YYYY-MM-DD` 的等价书写形式（去掉全部空白后再比对，故空格外写法自动覆盖）。"""
    year, month, day = (int(x) for x in str(iso_date).split("-"))
    y = "%04d" % year
    return [
        "%s-%02d-%02d" % (y, month, day), "%s-%d-%d" % (y, month, day),
        "%s/%d/%d" % (y, month, day), "%s/%02d/%02d" % (y, month, day),
        "%s.%d.%d" % (y, month, day), "%s.%02d.%02d" % (y, month, day),
        "%s年%d月%d日" % (y, month, day), "%s年%02d月%02d日" % (y, month, day),
    ]


def date_in_text(iso_date, text) -> bool:
    """日期是否在文本里真实出现（文本先去掉全部空白）。"""
    text_ns = strip_ws(text)
    return any(rendering in text_ns for rendering in date_renderings(iso_date))


def month_day_renderings(month, day):
    return ["%d月%d日" % (month, day), "%02d月%02d日" % (month, day)]


def month_day_standalone_in_text(month, day, text) -> bool:
    """月日是否在文本里**独立出现**（前面不带年份、后面不带数字）。

    「独立」是 year_from_publish 的认定条件：若窗口写的是 `2025年8月27日`，那不是「只给月日」，
    不能拿发布年去替换正文里已经写出的年份。
    """
    text_ns = strip_ws(text)
    for rendering in month_day_renderings(month, day):
        start = 0
        while True:
            position = text_ns.find(rendering, start)
            if position < 0:
                break
            before = text_ns[max(0, position - 6):position]
            after = text_ns[position + len(rendering):position + len(rendering) + 1]
            bad_prefix = re.search(r"(\d{4}[-/.]|\d{1,4}年)$", before)
            if not bad_prefix and not after.isdigit():
                return True
            start = position + 1
    return False


def normalize_date(value):
    """把模型返回的日期折成 `YYYY-MM-DD`；返回 (iso 或 None, 是否给了值但不可解析)。"""
    if value is None:
        return None, False
    text = strip_ws(value)
    if not text or text.lower() in ("null", "none", "无", "未知"):
        return None, False
    for pattern in config.TIME["accepted_income_forms"]:
        if re.match(pattern, text):
            parts = re.findall(r"\d+", text)
            try:
                return _dt.date(int(parts[0]), int(parts[1]), int(parts[2])).isoformat(), False
            except (ValueError, IndexError):
                return None, True
    return None, True


def parse_publish_date(value):
    if not value:
        return None
    text = strip_ws(value)
    match = re.match(r"^(\d{4})\D{0,2}(\d{1,2})\D{0,2}(\d{1,2})", text)
    if not match:
        return None
    try:
        return _dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def anchor_year(publish_date, month):
    """确定性年份锚定：月 ≤ 发布月 → 发布年；否则 发布年 − 1。"""
    if publish_date is None:
        return None
    if month <= publish_date.month:
        return publish_date.year
    return publish_date.year - 1


# --------------------------------------------------------------------------
# 窗口：以证据引文为中心的有界窗口（必要时向同文档相邻块扩展）
# --------------------------------------------------------------------------
def build_window(doc_chunks, source_chunk_id, quote):
    """返回窗口字典：{text, chunk_id, chunk_index, quote_start, expanded_prev, expanded_next,
    quote_found_in_chunk, quote_found_in_document, window_source}。"""
    chunks = sorted(doc_chunks, key=lambda c: int(c.get("chunk_index") or 0))
    window_chars = int(SPEC["window_chars"])
    neighbor_chars = int(SPEC["neighbor_chars"])
    quote = str(quote or "")

    position_in_doc = next((i for i, c in enumerate(chunks)
                            if str(c.get("chunk_id")) == str(source_chunk_id)), None)
    chunk = chunks[position_in_doc] if position_in_doc is not None else None
    located = find_in_text(chunk.get("content") or "", quote) if chunk is not None else None
    quote_found_in_chunk = located is not None
    quote_found_in_document = quote_found_in_chunk

    if not quote_found_in_chunk:
        # 证据块对不上时按 chunk_index 升序在整篇里找引文（确定性），并如实记账。
        for index, candidate in enumerate(chunks):
            hit = find_in_text(candidate.get("content") or "", quote)
            if hit is not None:
                chunk, position_in_doc, located = candidate, index, hit
                quote_found_in_chunk = True
                quote_found_in_document = True
                break

    if chunk is None or not quote_found_in_chunk:
        # 兜底（不应出现）：窗口取该文档前若干字符，标记引文未定位，复核仍按真实窗口做。
        text = "\n".join(str(c.get("content") or "") for c in chunks)[: 2 * window_chars]
        return {"text": text, "chunk_id": str(source_chunk_id), "chunk_index": None,
                "quote_start": None, "expanded_prev": False, "expanded_next": False,
                "quote_found_in_chunk": False, "quote_found_in_document": False,
                "window_source": "fallback_document_head"}

    content = str(chunk.get("content") or "")
    start, end = located
    left = max(0, start - window_chars)
    right = min(len(content), end + window_chars)
    expanded_prev = expanded_next = False
    if left == 0 and position_in_doc > 0:
        previous = str(chunks[position_in_doc - 1].get("content") or "")
        if previous:
            prefix = previous[-neighbor_chars:]
            content = prefix + content
            start, end, right = start + len(prefix), end + len(prefix), right + len(prefix)
            left = max(0, start - window_chars)
            expanded_prev = True
    text = content[left:right]
    if right >= len(content) and position_in_doc + 1 < len(chunks):
        following = str(chunks[position_in_doc + 1].get("content") or "")
        if following:
            text = text + following[:neighbor_chars]
            expanded_next = True
    return {"text": text, "chunk_id": str(chunk.get("chunk_id")),
            "chunk_index": int(chunk.get("chunk_index") or 0),
            "quote_start": start, "expanded_prev": expanded_prev,
            "expanded_next": expanded_next, "quote_found_in_chunk": quote_found_in_chunk,
            "quote_found_in_document": quote_found_in_document,
            "window_source": "quote_centered"}


# --------------------------------------------------------------------------
# 提示词与调用参数
# --------------------------------------------------------------------------
def build_messages(case):
    """小提示词：只问「日期 ＋ 依据标记 ＋ 承载日期的引文」。"""
    window = case["window"]["text"]
    system = ("你是财经公告的时间归一化工具。只输出一个 JSON 对象，不输出解释、不输出"
              "Markdown 代码围栏、不输出多余字段。")
    user = "\n".join([
        "任务：判断下面这个**事件**的发生日期。",
        "",
        "事件类型：%s" % case["event_type"],
        "事件名称：%s" % case["event_name"],
        "抽取时给出的证据引文：%s" % (case["quote"] or "（无）"),
        "该文档的发布时间（publish_time）：%s" % (case["publish_time"] or "（未知）"),
        "",
        "证据引文所在的正文窗口（同一篇文档，窗口以引文为中心、前后各 %d 字；"
        "引文可能跨块，窗口最多再向相邻块各扩 %d 字）："
        % (int(SPEC["window_chars"]), int(SPEC["neighbor_chars"])),
        "<<<窗口开始>>>",
        window,
        "<<<窗口结束>>>",
        "",
        "规则（逐条遵守）：",
        "1. 只回答**能确定到日**的日期；窗口里确实没有可归属到这个事件的日期时，"
        "`event_time` 返回 null、`event_time_basis` 返回 \"null\"。",
        "2. 日期的各种写法等价：`2026 年8 月27 日`（数字与汉字之间可能有空格）、"
        "`2026年8月27日`、`2026-08-27`、`2026/8/27`、`2026.8.27` 都按 `YYYY-MM-DD` 返回，"
        "例如 `2026 年8 月27 日` → `2026-08-27`。",
        "3. **窗口里任何位置**写出的日期，只要它是在描述这个事件，就可以采用（不必出现在"
        "上面的证据引文里）；采用了哪一句，就把那一句**逐字**抄进 `evidence_quote`（≤%d 字，"
        "必须来自窗口原文）。" % int(SPEC["quote_max_chars"]),
        "4. 窗口只给「月日」（例如 `8 月27 日`）而没有年份时：按发布时间锚定年份——"
        "月 ≤ 发布月 → 用发布年；否则用 发布年 − 1；这时 `event_time_basis` 必须写 "
        "\"year_from_publish\"（年份是锚定值，不是正文写的）。",
        "5. 窗口里若同时出现多个可能属于**不同事件**的日期、无法确定哪一个描述本事件，"
        "就返回 null（`event_time_basis` 写 \"null\"），不要挑一个「看起来最像」的。",
        "6. `event_time_basis` 只能是 \"stated\"（正文明确写出年月日）／"
        "\"year_from_publish\"（月日＋锚定年份）／\"null\"（没有可归属的日期）三者之一。",
        "",
        "只输出 JSON：{\"event_time\": \"YYYY-MM-DD\" 或 null, "
        "\"event_time_basis\": \"stated\" 或 \"year_from_publish\" 或 \"null\", "
        "\"evidence_quote\": \"承载该日期的窗口原文\"}",
    ])
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def model_params() -> dict:
    return {
        "model": config.time_backfill_model(),
        "temperature": SPEC["temperature"],
        "max_tokens": int(SPEC["max_tokens"]),
        "response_format": SPEC["response_format"],
    }


def input_sha256(case) -> str:
    """输入指纹：覆盖提示词全文、调用参数与窗口（窗口由块与引文确定性算出）。"""
    return sha256_text(config.stable_json({
        "prompt_version": SPEC["prompt_version"],
        "params": model_params(),
        "messages": case["messages"],
        "doc_id": case["doc_id"],
        "event_id": case["event_id"],
        "source_chunk_id": case["source_chunk_id"],
        "window_sha256": sha256_text(case["window"]["text"]),
    }))


def cache_path(event_id) -> str:
    return os.path.join(SPEC["cache_dir"], SPEC["cache_file_pattern"].format(event_id=event_id))


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


def _invoke(client, openai_mod, case, stats, kwargs):
    """发一次请求（含传输层退避重试），返回该次尝试的明细。"""
    pacing = SPEC["pacing"]
    wait = max(0.0, float(pacing["min_interval_seconds"]) - (time.time() - _LAST_CALL_TS[0]))
    if wait:
        time.sleep(wait)
    for attempt in range(1, int(pacing["max_retries"]) + 2):
        started = time.time()
        _LAST_CALL_TS[0] = started
        stats["api_calls"] += 1
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            if not _retryable(exc, openai_mod) or attempt > int(pacing["max_retries"]):
                raise
            backoff = min(float(pacing["backoff_base_seconds"]) * (2 ** (attempt - 1)),
                          float(pacing["backoff_max_seconds"]))
            stats["retries"] += 1
            print("[重试] %s 第 %d 次失败（%s），%.1f 秒后重试"
                  % (case["event_id"], attempt, type(exc).__name__, backoff))
            time.sleep(backoff)
            continue
        usage = response.usage.model_dump() if response.usage else {}
        usage = {k: v for k, v in usage.items()
                 if v is None or isinstance(v, (int, float, str, dict))}
        return {
            "elapsed_ms": int((time.time() - started) * 1000),
            "transport_attempts": attempt,
            "usage": usage,
            "finish_reason": (response.choices[0].finish_reason if response.choices else None),
            "model_resolved": str(getattr(response, "model", "") or ""),
            "response_text": (response.choices[0].message.content if response.choices else ""),
        }
    raise RuntimeError("模型调用失败且未抛出异常（不应到达）")


def call_model(client, openai_mod, case, stats, skip_primary=False):
    """主尝试 ＋（被输出上限截断时）一次压缩重试；两次原始返回都进缓存。

    主尝试的调用参数就是 `model_params()`（＝ config 第 10 节登记的 base_url／model／
    temperature／max_tokens／response_format），因此 `input_sha256` 只由主尝试参数决定；
    压缩重试是**恢复路径**，与 `extract.py` 的 `LLM["fallback"]` 同一套约定。
    `skip_primary=True`（上一次缓存条目已被截断时用）直接走压缩重试，省掉一次注定被截断的调用。
    """
    fallback = SPEC["fallback"]
    details = []
    plans = [True] if skip_primary else [False, True]
    for compact in plans:
        kwargs = dict(model_params())
        kwargs["messages"] = case["messages"]
        kwargs["response_format"] = {"type": kwargs["response_format"]}
        if compact:
            kwargs["max_tokens"] = int(fallback["max_tokens"])
            if fallback.get("reasoning_effort"):
                kwargs["reasoning_effort"] = fallback["reasoning_effort"]
        detail = _invoke(client, openai_mod, case, stats, kwargs)
        detail["compact"] = bool(compact)
        detail["max_tokens"] = kwargs["max_tokens"]
        detail["reasoning_effort"] = kwargs.get("reasoning_effort")
        details.append(detail)
        if detail["finish_reason"] != fallback["trigger_reason"]:
            break
        if compact or len(details) >= int(fallback["max_attempts"]) or skip_primary:
            break
        stats["fallback_calls"] = stats.get("fallback_calls", 0) + 1
        print("[压缩重试] %s 主尝试被输出上限截断，关闭思考重问一次" % case["event_id"])
    final = details[-1]
    usage_total = {key: sum(int((d["usage"] or {}).get(key) or 0) for d in details)
                   for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    return {
        "attempts": len(details),
        "attempts_detail": details,
        "usage": final["usage"],
        "usage_total": usage_total,
        "elapsed_ms": sum(d["elapsed_ms"] for d in details),
        "transport_attempts": sum(d["transport_attempts"] for d in details),
        "finish_reason": final["finish_reason"],
        "model_resolved": final["model_resolved"],
        "response_text": final["response_text"],
    }


def write_cache(case, detail, stats):
    record = {
        "cache_schema": SPEC["cache_schema"],
        "dataset_version": config.DATASET_VERSION,
        "doc_id": case["doc_id"],
        "event_id": case["event_id"],
        "source_chunk_id": case["source_chunk_id"],
        "model_requested": model_params()["model"],
        "model_resolved": detail["model_resolved"],
        "model_pinned": SPEC["model_pinned"],
        "model_pinning_state": config.model_pinning_state(detail["model_resolved"]),
        "temperature": SPEC["temperature"],
        "max_tokens": int(SPEC["max_tokens"]),
        "response_format": SPEC["response_format"],
        "prompt_version": SPEC["prompt_version"],
        "window_chars": int(SPEC["window_chars"]),
        "neighbor_chars": int(SPEC["neighbor_chars"]),
        "window_sha256": sha256_text(case["window"]["text"]),
        "input_sha256": input_sha256(case),
        "created_at": now_iso(),
        "elapsed_ms": detail["elapsed_ms"],
        "transport_attempts": detail["transport_attempts"],
        "attempts": detail["attempts"],
        "attempts_detail": detail["attempts_detail"],
        "usage": detail["usage"],
        "usage_total": detail["usage_total"],
        "finish_reason": detail["finish_reason"],
        "response_text": detail["response_text"],
    }
    target = cache_path(case["event_id"])
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(record, fh, ensure_ascii=False, sort_keys=True, indent=2)
        fh.write("\n")
    stats["cache_written"].append(case["event_id"])
    return record


def load_or_call(case, client, openai_mod, stats, force):
    """缓存命中则只读缓存（不调模型、不需要密钥）；缺失或 --force 才调用并写缓存。"""
    path = cache_path(case["event_id"])
    want = input_sha256(case)
    if os.path.isfile(path) and not force:
        try:
            with open(path, encoding="utf-8") as fh:
                record = json.load(fh)
        except (OSError, ValueError):
            record = None                    # 半截写入的缓存条目不算缓存（重问一次并重写）
        if record is None:
            if client is None:
                raise RuntimeError("补抽缓存读不出来且不允许调用模型：%s" % rel(path))
            print("[重写] %s 的缓存条目不可读，重问一次" % case["event_id"])
            return write_cache(case, call_model(client, openai_mod, case, stats), stats), False
        if str(record.get("doc_id")) != str(case["doc_id"]):
            raise RuntimeError("补抽缓存与事件不是同一篇文档：%s 记的是 doc_id=%s，当前是 %s"
                               % (rel(path), record.get("doc_id"), case["doc_id"]))
        if record.get("input_sha256") != want:
            raise RuntimeError(
                "补抽缓存与当前输入不一致：%s 的 input_sha256=%s，当前=%s。"
                "这通常意味着提示词、窗口、模型或调用参数变过；确认后加 --force 重跑并重写缓存。"
                % (rel(path), record.get("input_sha256"), want))
        if record_unstable(record):
            # 未收敛的缓存条目（上一次返回被输出上限截断、且不可解析）不算有效缓存：本次补齐。
            if client is None:
                raise RuntimeError("补抽缓存条目未收敛（finish_reason=length）且不允许调用模型：%s"
                                   % rel(path))
            print("[缓存] %s 上一次返回被截断，本次按压缩重试补齐（跳过注定被截断的主尝试）"
                  % case["event_id"])
            detail = call_model(client, openai_mod, case, stats, skip_primary=True)
            return write_cache(case, detail, stats), False
        stats["cache_hits"] += 1
        return record, True
    if client is None:
        raise RuntimeError("需要调用模型但客户端未构造（--verify 模式下不允许调用）：%s"
                           % rel(path))
    detail = call_model(client, openai_mod, case, stats)
    record = write_cache(case, detail, stats)
    stats["fetched"] += 1
    return record, False


def get_client(stats):
    """惰性构造客户端：只有真的缺缓存时才需要密钥与网络。"""
    import openai  # 只有真正要调用时才 import
    stats["base_url"] = config.time_backfill_base_url()
    client = openai.OpenAI(api_key=config.time_backfill_api_key(),
                           base_url=stats["base_url"],
                           timeout=float(SPEC["timeout_seconds"]), max_retries=0)
    return client, openai


# --------------------------------------------------------------------------
# 解析与复核
# --------------------------------------------------------------------------
def parse_json_object(text):
    """容错只做「剥 Markdown 代码围栏」与「取第一个花括号块」，不改写内容。"""
    raw = str(text or "").strip()
    if not raw:
        return None, "empty_response"
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw).strip()
    try:
        payload = json.loads(raw)
    except ValueError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None, "not_json"
        try:
            payload = json.loads(raw[start:end + 1])
        except ValueError:
            return None, "not_json"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, ""


def normalize_basis(value):
    text = strip_ws(value).lower()
    if text in ("stated", "explicit", "explicit_date", "正文", "明确"):
        return "stated"
    if text in ("year_from_publish", "from_publish", "anchored",
                "year_from_publish_time", "锚定", "yearfrompublish"):
        return "year_from_publish"
    if text in ("", "null", "none", "无", "没有", "unknown"):
        return "null"
    return None


def record_unstable(record):
    """缓存条目是否**未收敛**：被输出上限截断（finish_reason=length）**且**返回不可解析。

    与 `extract.py` 的同一口径（截断的条目下次自动补齐）；但若截断的返回恰好已是完整 JSON
    （常见于「正文写完、只差收尾」），就按可用条目处理——这样复跑仍然是零模型调用。
    """
    if not record:
        return True
    if record.get("finish_reason") != SPEC["fallback"]["trigger_reason"]:
        return False
    payload, _reason = parse_json_object(record.get("response_text"))
    return payload is None


def verify_result(case, payload):
    """对一条模型返回做确定性复核，返回结果字典（含 event_time／event_time_basis）。"""
    publish_date = parse_publish_date(case["publish_time"])
    window_text = case["window"]["text"]
    window_ns = strip_ws(window_text)
    model_time, bad_time = normalize_date((payload or {}).get("event_time"))
    basis_raw = (payload or {}).get("event_time_basis")
    if basis_raw is None:
        basis_raw = (payload or {}).get("basis")
    basis = normalize_basis(basis_raw)
    evidence = str((payload or {}).get("evidence_quote") or "").strip()
    if len(evidence) > int(SPEC["quote_max_chars"]):
        evidence = evidence[:int(SPEC["quote_max_chars"])]

    result = {
        "doc_id": case["doc_id"], "event_id": case["event_id"],
        "event_type": case["event_type"], "event_name": case["event_name"],
        "publish_time": case["publish_time"], "source_chunk_id": case["source_chunk_id"],
        "quote": case["quote"][:int(SPEC["quote_max_chars"])],
        "window_chars": int(SPEC["window_chars"]), "neighbor_chars": int(SPEC["neighbor_chars"]),
        "window_sha256": sha256_text(window_text),
        "quote_found_in_chunk": case["window"]["quote_found_in_chunk"],
        "quote_found_in_document": case["window"]["quote_found_in_document"],
        "model_event_time": model_time, "model_event_time_basis": basis,
        "evidence_quote": evidence,
        "event_time": None, "event_time_basis": "null",
        "date_in_window": False, "date_in_evidence_quote": False,
        "evidence_in_window": False, "evidence_quality": "quote_missing",
        "year_anchor": None, "verdict": "rejected", "reject_reason": "",
    }
    if evidence:
        result["evidence_in_window"] = find_in_text(window_text, evidence) is not None
    if model_time:
        result["date_in_window"] = date_in_text(model_time, window_ns)
        result["date_in_evidence_quote"] = date_in_text(model_time, evidence) if evidence else False
    if evidence:
        result["evidence_quality"] = ("quote_carries_date" if result["date_in_evidence_quote"]
                                      else ("quote_in_window" if result["evidence_in_window"]
                                            else "quote_not_in_window"))

    if model_time is None:
        result["reject_reason"] = "model_unparsable_date" if bad_time else "model_says_null"
        return result
    if basis is None:
        result["reject_reason"] = "basis_missing_or_invalid"
        return result
    if basis == "null":
        result["reject_reason"] = "basis_null_with_date"
        return result
    if basis == "stated":
        if result["date_in_window"]:
            result["event_time"], result["event_time_basis"] = model_time, "stated"
            result["verdict"], result["reject_reason"] = "accepted", ""
        else:
            result["reject_reason"] = "stated_date_not_in_window"
        return result
    # year_from_publish：月日必须在窗口里独立出现，年份必须等于锚定值。
    month, day = int(model_time[5:7]), int(model_time[8:10])
    anchored = anchor_year(publish_date, month)
    result["year_anchor"] = {
        "rule": SPEC["year_from_publish_rule"],
        "publish_date": publish_date.isoformat() if publish_date else None,
        "publish_year": publish_date.year if publish_date else None,
        "publish_month": publish_date.month if publish_date else None,
        "month_day": "%d-%d" % (month, day),
        "anchored_year": anchored,
        "month_day_standalone_in_window": month_day_standalone_in_text(month, day, window_ns),
    }
    if publish_date is None:
        result["reject_reason"] = "publish_time_unparsable"
    elif anchored != int(model_time[:4]):
        result["reject_reason"] = "anchored_year_mismatch"
    elif not result["year_anchor"]["month_day_standalone_in_window"]:
        result["reject_reason"] = "month_day_not_standalone_in_window"
    else:
        result["event_time"], result["event_time_basis"] = model_time, "year_from_publish"
        result["verdict"], result["reject_reason"] = "accepted", ""
    return result


def build_case(record, event, doc_chunks):
    window = build_window(doc_chunks, event.get("source_chunk_id"), event.get("quote"))
    case = {
        "doc_id": int(record["doc_id"]),
        "event_id": str(event["event_id"]),
        "event_type": str(event.get("event_type") or ""),
        "event_name": str(event.get("event_name") or ""),
        "quote": str(event.get("quote") or "")[:int(SPEC["quote_max_chars"])],
        "publish_time": str(record.get("publish_time") or ""),
        "source_chunk_id": event.get("source_chunk_id"),
        "window": window,
    }
    case["messages"] = build_messages(case)
    return case


# --------------------------------------------------------------------------
# 度量：时间覆盖与「可过滤性」（补抽前／后）
# --------------------------------------------------------------------------
def _doc_time_metrics(doc_dates):
    """doc_dates: {doc_id: [date, ...]} → 可过滤性读数（确定性、无阈值猜测）。"""
    both, months, span31 = [], [], []
    for doc_id in sorted(doc_dates):
        dates = sorted({d for d in doc_dates[doc_id] if d})
        if len(dates) >= 2:
            both.append(doc_id)
            if len({(d.year, d.month) for d in dates}) >= 2:
                months.append(doc_id)
            if (dates[-1] - dates[0]).days >= 31:
                span31.append(doc_id)
    return {"docs_with_ge2_dated_events": len(both),
            "docs_times_span_more_than_one_month": len(months),
            "docs_times_span_ge_31_days": len(span31),
            "doc_ids_ge2": both, "doc_ids_multi_month": months}


def measure(records, chunks_by_doc, overlay, merged_rows):
    """补抽前／后的时间覆盖与可过滤性（抽取层 ＋ 图谱层，两个口径都算，不猜）。"""
    overlay_rows = {(int(r["doc_id"]), str(r["event_id"])): r
                    for r in (overlay or {}).get("results", [])}

    def layer_from_extraction(patch_rows):
        events = dated = 0
        per_doc = {}
        for record in records:
            doc_id = int(record["doc_id"])
            for event in sorted(record.get("events") or [], key=lambda e: str(e["event_id"])):
                events += 1
                time_value = event.get("event_time")
                if not time_value:
                    patch = patch_rows.get((doc_id, str(event["event_id"]))) or {}
                    time_value = patch.get("event_time")
                date = parse_publish_date(time_value) if time_value else None
                if date:
                    dated += 1
                    per_doc.setdefault(doc_id, []).append(date)
        return {"events": events, "events_with_time": dated,
                "events_without_time": events - dated, "metrics": _doc_time_metrics(per_doc)}

    def layer_from_graph():
        per_doc, dated = {}, 0
        for row in merged_rows:
            time_value = row.get("event_time")
            date = parse_publish_date(time_value) if time_value else None
            if date:
                dated += 1
            for doc_id in row.get("evidence_doc_ids") or []:
                if date:
                    per_doc.setdefault(int(doc_id), []).append(date)
        return {"events": len(merged_rows), "events_with_time": dated,
                "events_without_time": len(merged_rows) - dated,
                "metrics": _doc_time_metrics(per_doc)}

    return {
        "schema": SPEC["schema"] + "-measure",
        "definition": {
            "docs_with_ge2_dated_events": "该文档的事件里有 ≥2 条 event_time 非空",
            "docs_times_span_more_than_one_month": "同上的日期落在 ≥2 个不同自然月（主口径）",
            "docs_times_span_ge_31_days": "同上最早与最晚日期相差 ≥31 天（次要口径，一并给出）",
            "layer_note": "抽取层＝每篇的 events[]（补抽覆盖层已应用）；"
                          "图谱层＝去重合并后事件按其证据文档展开（dedup_events.py 产物）",
        },
        "extraction_layer_before_backfill": layer_from_extraction({}),
        "extraction_layer_after_backfill": layer_from_extraction(overlay_rows),
        "graph_layer_after_backfill": layer_from_graph(),
        "backfill": {"null_events": len(overlay_rows),
                     "accepted": sum(1 for r in overlay_rows.values() if r.get("event_time")),
                     "by_basis": _histogram([r.get("event_time_basis") or "null"
                                             for r in overlay_rows.values()])},
    }


def _histogram(values):
    out = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return {k: out[k] for k in sorted(out)}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def collect_cases(records, chunks_by_doc, only_docs=None, limit=None):
    """按（doc_id, event_id）确定性顺序收集 null 事件的小提示词输入。"""
    cases, notes = [], []
    for record in sorted(records, key=lambda r: int(r["doc_id"])):
        doc_id = int(record["doc_id"])
        if only_docs and doc_id not in only_docs:
            continue
        for event in sorted(record.get("events") or [], key=lambda e: str(e["event_id"])):
            if event.get("event_time"):
                continue                      # 非空事件一个字节都不改（T3 已核验正文渲染）
            case = build_case(record, event, chunks_by_doc.get(doc_id) or [])
            if not case["window"]["quote_found_in_document"]:
                notes.append({"doc_id": doc_id, "event_id": case["event_id"],
                              "reason": "quote_not_found_in_document",
                              "note": "窗口退化为该文档前若干字符；仍会提问，但如实记账"})
            cases.append(case)
    if limit is not None:
        cases = cases[:int(limit)]
    return cases, notes


def build_overlay(paths, records_path, extract_sha, docs_total, events_total,
                  cases, results, notes, cache_records):
    """覆盖层：**无时间戳**，逐字节可重放；见模块头「确定性重放」。"""
    by_basis = _histogram([r["event_time_basis"] for r in results])
    accepted = [r for r in results if r["event_time"]]
    stated_before = events_total - len(cases)          # T3 已给出的非空事件（口径为 stated）
    by_basis_after = {
        "stated": stated_before + sum(1 for r in accepted if r["event_time_basis"] == "stated"),
        "year_from_publish": sum(1 for r in accepted
                                 if r["event_time_basis"] == "year_from_publish"),
        "null": len(cases) - len(accepted),
    }
    return {
        "schema": SPEC["schema"],
        "dataset_version": config.DATASET_VERSION,
        "profile": paths["profile"],
        "prompt_version": SPEC["prompt_version"],
        "window": {"window_chars": int(SPEC["window_chars"]),
                   "neighbor_chars": int(SPEC["neighbor_chars"]),
                   "rule": SPEC["window_rule_note"]},
        "basis_values": list(SPEC["basis_values"]),
        "basis_definitions": SPEC["basis_definitions"],
        "year_from_publish_rule": SPEC["year_from_publish_rule"],
        "source": {
            "extract_records": rel(records_path),
            "extract_records_sha256": extract_sha,
            "chunks": rel(config.CHUNKS_PATH),
            "chunks_sha256": sha256_file(config.CHUNKS_PATH),
            "documents": docs_total,
            "events_total": events_total,
            "null_events_in_scope": len(cases),
        },
        "cache": {
            "dir": rel(SPEC["cache_dir"]),
            "schema": SPEC["cache_schema"],
            "entries_used": len(cache_records),
            "results": [{"event_id": r["event_id"], "cache_input_sha256": r["cache_input_sha256"],
                         "cache_path": r["cache_path"]}
                        for r in sorted(results, key=lambda x: str(x["event_id"]))],
        },
        "counts": {
            "events_total": events_total,
            "events_null_in_scope": len(cases),
            "accepted": len(accepted),
            "rejected": len(cases) - len(accepted),
            "by_basis": by_basis,
            "events_by_basis_after": by_basis_after,
            "event_time_nonnull_after": (events_total - len(cases)) + len(accepted),
            "event_time_null_after": len(cases) - len(accepted),
            "quote_not_found_in_document": len(notes),
        },
        "notes": sorted(notes, key=lambda n: (n["doc_id"], n["event_id"])),
        "results": sorted(results, key=lambda r: (int(r["doc_id"]), str(r["event_id"]))),
    }


def _samples(results):
    """10 条抽样：≥3 条 year_from_publish ＋ stated／null 各若干（确定性取法）。"""
    ordered = sorted(results, key=lambda r: (int(r["doc_id"]), str(r["event_id"])))
    picked = [r for r in ordered if r["event_time_basis"] == "year_from_publish"][:3]
    for basis, wanted in (("stated", 4), ("null", 3)):
        pool = [r for r in ordered if r["event_time_basis"] == basis]
        if pool:
            step = max(1, (len(pool) + wanted - 1) // wanted)
            picked.extend(pool[::step][:wanted])
    seen, unique = set(), []
    for row in picked:
        if row["event_id"] in seen:
            continue
        seen.add(row["event_id"])
        unique.append(row)
    return unique[:10]


def build_report(paths, overlay, results, notes, stats, started, args, cases):
    usage_totals = {key: 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    resolved = {}
    for result in results:
        record_path = os.path.join(config.ROOT, result["cache_path"])
        record = load_json(record_path) or {}
        usage = record.get("usage_total") or record.get("usage") or {}
        for key in usage_totals:
            usage_totals[key] += int(usage.get(key) or 0)
        name = record.get("model_resolved") or "?"
        resolved[name] = resolved.get(name, 0) + 1
    return {
        "schema": SPEC["schema"] + "-report",
        "generated_at": now_iso(),
        "profile": paths["profile"],
        "overlay": rel(paths["overlay"]),
        "overlay_note": "覆盖层不含时间戳，逐字节可重放；本报告含运行读数，允许每次不同。",
        "run": {
            "mode": ("verify" if args.verify else ("measure" if args.measure else "backfill")),
            "force": bool(args.force), "limit": args.limit, "docs": args.docs or "",
            "base_url": stats.get("base_url"),
            "model_requested": config.time_backfill_model(),
            "model_pinned": SPEC["model_pinned"],
            "model_resolved_counts": {k: resolved[k] for k in sorted(resolved)},
            "api_calls": stats["api_calls"], "cache_hits": stats["cache_hits"],
            "fetched": stats["fetched"], "retries": stats["retries"],
            "fallback_calls": stats.get("fallback_calls", 0),
            # 「复用缓存」与「新写／补齐缓存」的条数只写进报告（运行读数），**不写进覆盖层**：
            # 覆盖层必须逐字节可重放，不能带这类随运行变化的状态。
            "cache_reused": stats["cache_hits"], "cache_written_count": stats["fetched"],
            "cache_entries_written": sorted(stats["cache_written"]),
            "wall_clock_seconds": round(time.time() - started, 3),
            "usage_total": usage_totals,
            "note": "token 合计直接读缓存条目的 usage（逐条原始返回的用量），不是估算",
        },
        "counts": overlay["counts"],
        "verification": {
            "by_basis": overlay["counts"]["by_basis"],
            "evidence_quality": _histogram([r["evidence_quality"] for r in results]),
            "reject_reasons": _histogram([r["reject_reason"] for r in results
                                          if r["reject_reason"]]),
            "quote_found_in_chunk": sum(1 for r in results if r["quote_found_in_chunk"]),
            "quote_found_in_document": sum(1 for r in results if r["quote_found_in_document"]),
            "anchored_year_matches": sum(
                1 for r in results
                if (r.get("year_anchor") or {}).get("anchored_year")
                == int(str(r.get("model_event_time") or "0")[:4] or 0)),
            "rejected_samples": [{"event_id": r["event_id"], "doc_id": r["doc_id"],
                                  "model_event_time": r["model_event_time"],
                                  "model_basis": r["model_event_time_basis"],
                                  "reason": r["reject_reason"]}
                                 for r in sorted(results,
                                                 key=lambda x: (int(x["doc_id"]),
                                                                str(x["event_id"])))
                                 if r["reject_reason"]][:20],
        },
        "notes": overlay["notes"],
        "samples": _samples(results),
    }


def finish(args, paths, overlay, report, results, stats, cases):
    overlay_text = dump_json(paths["overlay"], overlay)
    report["run"]["overlay_sha256"] = sha256_text(overlay_text)
    dump_json(paths["report"], report)
    accepted = [r for r in results if r["event_time"]]
    print("")
    print("输入（只读）：%s（%d 篇、%d 条事件）"
          % (rel(paths["extract_records"]),
             overlay["source"]["documents"], overlay["source"]["events_total"]))
    print("补抽范围：%d 条 null 事件；接受 %d 条、保持 null %d 条；依据分布 %s"
          % (len(cases), len(accepted), len(cases) - len(accepted),
             overlay["counts"]["by_basis"]))
    print("模型调用：%d 次（缓存命中 %d 条、重试 %d 次）；token %s；墙钟 %.1f 秒"
          % (stats["api_calls"], stats["cache_hits"], stats["retries"],
             report["run"]["usage_total"], report["run"]["wall_clock_seconds"]))
    print("端点：%s；模型：%s（解析到 %s）"
          % (stats.get("base_url"), config.time_backfill_model(),
             report["run"]["model_resolved_counts"]))
    print("产物：%s" % rel(paths["overlay"]))
    print("      %s" % rel(paths["report"]))
    return 0


def run_backfill(args) -> int:
    paths = config.time_backfill_paths(args.profile)
    records_path = paths["extract_records"]
    if not os.path.isfile(records_path):
        raise SystemExit("输入不存在：%s（请先跑 extract.py --profile %s）"
                         % (records_path, args.profile))
    records = read_jsonl(records_path)
    extract_sha = sha256_file(records_path)
    chunks_by_doc = {}
    for chunk in read_jsonl(config.CHUNKS_PATH):
        chunks_by_doc.setdefault(int(chunk["doc_id"]), []).append(chunk)
    events_total = sum(len(r.get("events") or []) for r in records)
    only_docs = {int(x) for x in re.split(r"[,\s]+", args.docs or "") if x.strip()} or None
    cases, notes = collect_cases(records, chunks_by_doc, only_docs, args.limit)

    stats = {"api_calls": 0, "cache_hits": 0, "fetched": 0, "retries": 0,
             "fallback_calls": 0, "cache_written": [],
             "base_url": config.time_backfill_base_url()}
    started = time.time()
    client, openai_mod = (None, None)
    force = bool(args.force)
    results, cache_records = [], {}
    for index, case in enumerate(cases, start=1):
        need_call = force or not os.path.isfile(cache_path(case["event_id"]))
        if not need_call:
            cached = load_json(cache_path(case["event_id"]))
            if record_unstable(cached):
                need_call = True        # 半截写入／截断且不可解析：本次补齐（要客户端）
        if need_call and client is None:
            client, openai_mod = get_client(stats)
        record, _from_cache = load_or_call(case, client, openai_mod, stats, force)
        cache_records[case["event_id"]] = record
        payload, parse_reason = parse_json_object(record.get("response_text"))
        result = verify_result(case, payload or {})
        result["cache_path"] = rel(cache_path(case["event_id"]))
        result["cache_input_sha256"] = record.get("input_sha256")
        result["parse_reason"] = parse_reason
        result["model_resolved"] = record.get("model_resolved")
        results.append(result)
        if index % 50 == 0 or index == len(cases):
            print("  … %d/%d（调用 %d、命中 %d、通过 %d）"
                  % (index, len(cases), stats["api_calls"], stats["cache_hits"],
                     sum(1 for r in results if r["event_time"])), flush=True)

    overlay = build_overlay(paths, records_path, extract_sha, len(records), events_total,
                            cases, results, notes, cache_records)
    baseline = sha256_file(paths["overlay"])
    report = build_report(paths, overlay, results, notes, stats, started, args, cases)
    code = finish(args, paths, overlay, report, results, stats, cases)
    if baseline:
        print("重放比对：本次重算的覆盖层 sha256=%s；上一版磁盘覆盖层 sha256=%s → %s"
              % (sha256_file(paths["overlay"])[:16], baseline[:16],
                 "逐字节一致 ✓" if sha256_file(paths["overlay"]) == baseline else "不一致"))
    return code


def run_verify(args) -> int:
    """只重算复核：零写入、零调用；与磁盘覆盖层逐字节比对（要求完全一致）。"""
    paths = config.time_backfill_paths(args.profile)
    if not os.path.isfile(paths["overlay"]):
        print("[阻断] 覆盖层不存在：%s" % rel(paths["overlay"]))
        return 1
    before = sha256_file(paths["overlay"])
    records = read_jsonl(paths["extract_records"])
    chunks_by_doc = {}
    for chunk in read_jsonl(config.CHUNKS_PATH):
        chunks_by_doc.setdefault(int(chunk["doc_id"]), []).append(chunk)
    only_docs = {int(x) for x in re.split(r"[,\s]+", args.docs or "") if x.strip()} or None
    cases, notes = collect_cases(records, chunks_by_doc, only_docs, args.limit)
    stats = {"api_calls": 0, "cache_hits": 0, "fetched": 0, "retries": 0,
             "fallback_calls": 0, "cache_written": [],
             "base_url": config.time_backfill_base_url()}
    results, cache_records, missing = [], {}, []
    for case in cases:
        path = cache_path(case["event_id"])
        if not os.path.isfile(path):
            missing.append(rel(path))
            continue
        record = load_json(path)
        if record is None:
            missing.append(rel(path))
            continue
        if record.get("input_sha256") != input_sha256(case):
            print("[阻断] 补抽缓存与当前输入不一致：%s" % rel(path))
            return 1
        stats["cache_hits"] += 1
        cache_records[case["event_id"]] = record
        payload, parse_reason = parse_json_object(record.get("response_text"))
        result = verify_result(case, payload or {})
        result["cache_path"] = rel(path)
        result["cache_input_sha256"] = record.get("input_sha256")
        result["parse_reason"] = parse_reason
        result["model_resolved"] = record.get("model_resolved")
        results.append(result)
    if missing:
        print("[不通过] 缺 %d 条补抽缓存：%s" % (len(missing), missing[:5]))
        return 2
    events_total = sum(len(r.get("events") or []) for r in records)
    overlay = build_overlay(paths, paths["extract_records"], sha256_file(paths["extract_records"]),
                            len(records), events_total, cases, results, notes, cache_records)
    text = json.dumps(overlay, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    after = sha256_text(text)
    print("重放核对：磁盘覆盖层 sha256=%s；按缓存重算 sha256=%s" % (before[:16], after[:16]))
    print("模型调用 %d 次（缓存命中 %d 条）；逐字节%s"
          % (stats["api_calls"], stats["cache_hits"], "一致 ✓" if after == before else "不一致 ✗"))
    if after != before:
        old = load_json(paths["overlay"]) or {}
        for key in sorted(set(old) | set(overlay)):
            if old.get(key) != overlay.get(key):
                print("  差异字段：%s" % key)
        return 2
    return 0


def run_measure(args) -> int:
    paths = config.time_backfill_paths(args.profile)
    records = read_jsonl(paths["extract_records"])
    chunks_by_doc = {}
    for chunk in read_jsonl(config.CHUNKS_PATH):
        chunks_by_doc.setdefault(int(chunk["doc_id"]), []).append(chunk)
    overlay = load_json(paths["overlay"]) or {}
    merged_path = config.pipeline_paths(args.profile)["events_merged"]
    merged_rows = read_jsonl(merged_path)
    payload = measure(records, chunks_by_doc, overlay, merged_rows)
    payload["generated_at"] = now_iso()
    payload["sources"] = {"extract_records": rel(paths["extract_records"]),
                          "extract_records_sha256": sha256_file(paths["extract_records"]),
                          "overlay": rel(paths["overlay"]),
                          "overlay_sha256": sha256_file(paths["overlay"]),
                          "events_merged": rel(merged_path),
                          "events_merged_sha256": sha256_file(merged_path)}
    target = args.measure_output or paths["measure"]
    dump_json(target, payload)
    print("时间覆盖／可过滤性度量：")
    for key in ("extraction_layer_before_backfill", "extraction_layer_after_backfill",
                "graph_layer_after_backfill"):
        block = payload[key]
        print("  %s：事件 %d 条、有时间 %d 条、无时间 %d 条；%s"
              % (key, block["events"], block["events_with_time"], block["events_without_time"],
                 {k: v for k, v in block["metrics"].items() if not k.startswith("doc_ids")}))
    print("  补抽：%s" % payload["backfill"])
    print("产物：%s" % rel(target))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 6 阶段 定向时间补抽（T3.5；只处理 event_time 为 null 的事件；"
                    "参数取自 config.EVENT_TIME_BACKFILL；缓存命中零调用）")
    parser.add_argument("--profile", default="v21", choices=["pilot", "v21"])
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条 null 事件（联机自检）")
    parser.add_argument("--docs", default=None, help="只处理指定 doc_id（逗号或空格分隔）")
    parser.add_argument("--force", action="store_true", help="忽略已有缓存，重新调用并重写缓存")
    parser.add_argument("--verify", action="store_true",
                        help="只按缓存重算复核并与磁盘覆盖层逐字节比对（零写入、零调用）")
    parser.add_argument("--measure", action="store_true",
                        help="只算时间覆盖／可过滤性指标（零调用）")
    parser.add_argument("--measure-output", default=None, help="度量产物落点（默认 config 登记值）")
    args = parser.parse_args(argv)
    try:
        if args.measure:
            return run_measure(args)
        if args.verify:
            return run_verify(args)
        return run_backfill(args)
    except SystemExit as exc:
        print("[阻断] %s" % exc)
        return 1
    except RuntimeError as exc:
        print("[阻断] %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
