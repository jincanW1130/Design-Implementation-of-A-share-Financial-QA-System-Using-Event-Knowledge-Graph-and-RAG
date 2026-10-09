# -*- coding: utf-8 -*-
"""第 7 阶段预实验问题集（30 题）的**第三方模型盲标复核**脚本。

依据与先例：

* `交付物/04-数据与知识图谱/事件抽取与知识图谱\\16-事件抽取与知识图谱（第六阶段）.md` 第 8.10 节
  「三个第三方模型的独立复核」——Prompt 版本 `stage6-thirdparty-review-v1.0`、**盲标**、
  三家厂商各跑一遍、原始返回进缓存、纯文档登记；本脚本照搬其方法学与性质声明口径。
* `交付物/05-系统实现/RAG检索系统\\预实验问题集\\说明.md` 第四节（gold 由决策者 AI 用确定性脚本
  构造并逐条回原文核验）与《18-第7阶段任务书》「检索 gold 必须由人工构造」的要求：
  作者已裁定「让第三方模型确认」，本脚本即该裁定的执行工具。

本脚本做什么（**只此一个新脚本**）：

1. `--profile run`（默认）：对 30 道题，用**同一套盲标提示词**
   （Prompt 版本 `stage7-thirdparty-review-v1.0`、输出 schema `stage7-thirdparty-review-1.0`）
   让**参与本次确认的两家**（`kimi`＋`zhipu`）各跑一遍；每题问三件事（A 这组 gold 是否足以
   支撑题目与参考答案；B 哪些块必需、哪些可有可无；C 参考答案是否被这些块支撑、有没有块里
   出现而答案漏掉的要点），要求**严格 JSON 输出**。原始返回（含 usage）进缓存。
   另有一条**已按作者指示剥离的第三方线**（见下方 `EXCLUDED_TRACE_VENDORS`）：它不参与
   本次确认、本脚本也不持有它的端点与配置字段名，只从留痕目录读取历史结果登记为留痕口径。
2. `--profile replay`：只读缓存重放，**禁止调用模型**（缓存未命中即失败），
   产出与首跑**逐字节一致**（不写时间戳、键排序、按 qid 升序）。
3. `--profile selftest`：不调用模型，只做**盲标自检**——逐题断言提示词里不出现
   `gold_verify_note`／`gold_verify_anchors`／`gold_evidence_rule`／`graph_path`／
   「图谱」等会泄露「哪些块是图谱侧找到的、本题是否已判过」的字段或字样。

**盲标**（硬要求）：提示词只含【题干】【三个标签】【参考答案】【gold 证据块的原文】四项。
不透露核验结论、不透露哪些块来自图谱侧、不透露本题是否已被判过。

**成本闸门**：单家累计 token 超过 2,000,000 即停下并报告（参与确认的两家合计 ≤ 5,000,000）。

**密钥纪律**：密钥只从环境变量读（`KIMI_API_KEY`／`ZHIPU_API_KEY`，
端点可经 `KIMI_BASE_URL` 等覆盖），缺失再回退到 `代码\\抽取与图谱\\config.local.json`
（该文件已被 `.gitignore` 的 `config.local.*` 覆盖，不入公开仓库）。
**脚本不打印、不记录、不回显任何密钥**（含前缀、含长度）。本文件不含任何密钥字面量。

**术语纪律**：全文不写出被禁用的四字连写术语。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# 2026-10-09 目录重组修正：本脚本随 `代码\检索\` 整体移到 `交付物/03-代码\检索\`
# （**下移一层**），求 ROOT 的上溯次数 2 → 3。
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# ---------------------------------------------------------------------------
# 0. 路径与常量（自足计算；不依赖任何会被并发修改的模块）
# ---------------------------------------------------------------------------
STAGE7_DIR = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统")
WORK_DIR = os.path.join(STAGE7_DIR, "_工作底稿", "第三方复核")     # 本次复核的落点
Q_DIR = os.path.join(STAGE7_DIR, "预实验问题集")
QUESTIONS_PATH = os.path.join(Q_DIR, "questions.jsonl")
LEDGER_PATH = os.path.join(Q_DIR, "第三方复核台账.json")
CHUNKS_PATH = os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")
LOCAL_CONFIG_PATH = os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "config.local.json")

PROMPT_VERSION = "stage7-thirdparty-review-v1.0"
OUTPUT_SCHEMA = "stage7-thirdparty-review-1.0"
CACHE_SCHEMA = "stage7-thirdparty-review-cache-1.0"

TOKEN_GATE_PER_VENDOR = 2_000_000
TOKEN_GATE_TOTAL = 5_000_000

# 复核之后由**决策者（AI）回原文逐条裁定**的结论（裁定台账，随复核结果一并登记）。
# 只有原文明确支持的修正才动 gold／参考答案；其余一律只登记不改。
GOLD_CHANGED_QIDS = ["PE-26", "PE-29"]
ADJUDICATIONS = {
    "PE-06": "只登记不改：参与确认的两家（kimi、zhipu）均判“成立”，维持现行 gold 与参考答案；"
             "已按作者指示剥离的一条第三方线（不参与确认、只作留痕）判“部分成立”系误读——把“品种一”的单只发行金额当成合计发行总额；"
             "原文 1021001 已写明“发行总额为人民币45亿元”，1021002 写明“品种二 5亿元”，40亿＋5亿＝45亿，两处一致。",
    "PE-26": "改 gold：参与确认的两家（kimi、zhipu）一致判“部分成立／参考答案未被 gold 支撑”（已剥离的一条线同向，只作留痕）。"
             "回原文 1502001、1533001 逐字给出两份框架协议全称，原 gold（1502005、1533005）只含协议正文不含协议名称，"
             "属 gold 证据不足；故补入该两块（2 块→4 块），候选规则相应改为“文档内全部文本块”。",
    "PE-29": "改参考答案：参与确认的两家为 1:1 分歧（kimi“成立”、zhipu“部分成立”）；zhipu 指出原文 1001001 同一块内并列"
             "“首次授予第二个行权期”与“预留授予第一个行权期”两条均自 2026-09-11 起行权的事件，原参考答案漏了后者"
             "（kimi 也把该点记入 missing_from_answer），回原文确认属实，属参考答案不完整；gold 证据块不变（1001000、1001001）。",
    "_class": "其余“必要块是 gold 真子集”“块内含答案未写的点”等分歧一律判为**标注粒度／详略差异**，只登记不改。",
}

# 参与本次确认的两家厂商（端点／模型名来自 config.local.json 的 `*_base_url`／`*_model_hint`
# 与 2026-09-27 的 `/models` 实测；见交付报告的「验证 1」）。
# temperature 逐家不同：`kimi-k3` 端点只接受 temperature=1（实测 400），`zhipu` 取 0。
VENDORS = [
    {
        "key": "kimi",
        "label": "Moonshot Kimi",
        "base_field": "kimi_base_url",
        "key_field": "kimi_api_key",
        "env_key": "KIMI_API_KEY",
        "env_base": "KIMI_BASE_URL",
        "model": "kimi-k3",
        "temperature": 1.0,
        "model_source": "config.local.json 的 kimi_model_hint＝「kimi k3」；2026-09-27 `/models` 实测确认 id＝kimi-k3",
    },
    {
        "key": "zhipu",
        "label": "智谱 Zhipu",
        "base_field": "zhipu_base_url",
        "key_field": "zhipu_api_key",
        "env_key": "ZHIPU_API_KEY",
        "env_base": "ZHIPU_BASE_URL",
        "model": "glm-5.3-flash",
        "temperature": 0.0,
        "model_source": "zhipu_note＝「智谱直连」；模型取 glm-5.3-flash，与《16》8.10 的第三方线保持一致",
    },
]

# 已按作者指示剥离的第三方线（**留痕口径：不参与本次确认、不得调用**）：
# 百度千帆 `ernie-5.1` 一条**原已完整跑通**（30 题 0 失败、60,073 token、模型 id 可解析），
# 但作者裁定该通道不可用，其凭据已从 `交付物/03-代码\抽取与图谱\config.local.json` 删除；本脚本因此
# **不再持有它的端点与配置字段名、也不调用它**（`VENDORS` 里没有这一条），只保留下面这条说明。
# 该线的 30 条原始返回与结果**不删不改**，留痕在
# `交付物/05-系统实现/RAG检索系统\_工作底稿\第三方复核\qianfan\`；`--profile replay`（以及 `run`）只**读取**
# 该留痕目录，把它登记为 `excluded_per_author=true` 的留痕口径，不并入“参与确认的两家”的一致率与用量。
EXCLUDED_TRACE_VENDORS = [
    {
        "key": "qianfan",
        "label": "百度千帆",
        "model": "ernie-5.1",
        "excluded_per_author": True,
        "exclusion_reason": "作者指示该通道不可用，凭据已从 config.local.json 删除；按裁定不参与本次确认。"
                            "该线实测曾完整跑通（30/30、0 失败、60,073 token），30 条原始返回与结果不删，"
                            "保留在 _工作底稿/第三方复核/qianfan/ 作为留痕。",
        "trace_dir": os.path.join(WORK_DIR, "qianfan"),
    },
]

MAX_TOKENS = 8000
TIMEOUT_SECONDS = 180.0
MAX_ATTEMPTS = 2          # 只在「返回不是合法 JSON」或「被输出上限截断」时再试一次

# 盲标自检的禁止字样（出现即判泄露）。这些字段/字样会暴露「哪些块是图谱侧找到的」、
# 「本题此前是否已被判过」或本项目的内部标签，一律不得进入提示词。
# 注意：提示词里合法出现的「gold 证据块」「gold_hop_depth」「chunk_id」不在表内——
# 它们只是命名这组块与标签本身，不泄露来源与判过与否。
FORBIDDEN_IN_PROMPT = [
    "gold_verify_note", "gold_verify_anchors", "gold_evidence_rule", "graph_path",
    "gold_verified_by", "gold_review_status", "gold_evidence_doc_ids",
    "回原文核验", "图谱", "向量", "HAS_EXECUTIVE", "PARTICIPATES_IN", "ISSUED_BY",
    "RELATED_TO", "EVIDENCED_BY", "BELONGS_TO", "共同参与事件", "人工确认",
    "参考集", "已判", "决策者", "source_chunk_id", "source_doc_id",
]

VERDICTS = ("成立", "部分成立", "不成立")


# ---------------------------------------------------------------------------
# 1. 小工具（确定性序列化／读写）
# ---------------------------------------------------------------------------
def stable_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def write_jsonl(path: str, rows) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def iter_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# ---------------------------------------------------------------------------
# 2. 凭据读取（只写读取方式；取值不入仓库、不落盘、不进日志、不回显）
# ---------------------------------------------------------------------------
def read_local_config() -> dict:
    try:
        with open(LOCAL_CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (OSError, ValueError):
        return {}


def credential(local_key: str, env_name: str, local: dict) -> tuple:
    """按「环境变量优先、缺失再回退 config.local.json」取凭据，返回 (取值, 来源)。

    绝不回显取值：调用方只允许使用布尔值与来源名。
    """
    value = (os.environ.get(env_name) or "").strip()
    if value:
        return value, "env"
    value = str(local.get(local_key) or "").strip()
    return value, ("config.local" if value else "missing")


def resolve_vendor(vendor: dict, local: dict) -> dict:
    """解析一家的端点／模型／凭据是否存在（不含取值输出）。"""
    base = (os.environ.get(vendor["env_base"]) or "").strip() or str(local.get(vendor["base_field"]) or "").strip()
    key, src = credential(vendor["key_field"], vendor["env_key"], local)
    out = dict(vendor)
    out["_base_url"] = base
    out["_key"] = key
    out["key_source"] = src
    out["base_url"] = base
    return out


# ---------------------------------------------------------------------------
# 3. 只读输入（题目与文本块原文）
# ---------------------------------------------------------------------------
LABELS = ("task_type", "gold_hop_depth", "time_constraint")


def load_questions() -> list:
    rows = list(iter_jsonl(QUESTIONS_PATH))
    rows.sort(key=lambda r: r["qid"])
    return rows


def load_chunks() -> dict:
    chunks = {}
    for row in iter_jsonl(CHUNKS_PATH):
        chunks[int(row["chunk_id"])] = row
    return chunks


# ---------------------------------------------------------------------------
# 4. 盲标提示词（只含【题干】【三个标签】【参考答案】【gold 证据块的原文】）
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "你是一名独立的第三方复核者，对一套「检索题目的 gold 证据」做盲标复核。"
    "你只看到题目、三个标签、参考答案与一组候选证据块的原文；"
    "你不知道这些块是怎么被挑出来的，也不知道它们此前是否被任何人判过。"
    "请只依据所给原文判断，不要臆测外部信息。"
    "严格按用户给出的 JSON 结构输出，只输出这一个 JSON 对象，不要输出任何解释性文字或代码块围栏。"
)


def build_user_prompt(q: dict, chunks: dict) -> str:
    """构造盲标用户提示词。**不含**任何核验结论／锚点／图谱字段。

    块按 chunk_id 升序给出，编号 <i> 仅用于阅读，模型回答时用 chunk_id 引用。
    """
    gold_ids = sorted(int(c) for c in q["gold_evidence_chunk_ids"])
    lines = []
    lines.append("【题干】")
    lines.append(q["question"])
    lines.append("")
    lines.append("【三个标签】")
    lines.append("任务类型：%s" % q["task_type"])
    lines.append("gold_hop_depth：%d" % int(q["gold_hop_depth"]))
    lines.append("时间约束：%s" % q["time_constraint"])
    lines.append("")
    lines.append("【参考答案】")
    lines.append(q["reference_answer"])
    lines.append("")
    lines.append("【gold 证据块的原文】（共 %d 块）" % len(gold_ids))
    for i, cid in enumerate(gold_ids, 1):
        content = str((chunks.get(cid) or {}).get("content") or "")
        lines.append("--- 块 %d | chunk_id=%d ---" % (i, cid))
        lines.append(content)
    lines.append("")
    lines.append("【要回答的三个问题】")
    lines.append("A. 这组 gold 证据是否**足以**支撑题目与参考答案？")
    lines.append("B. 这些块里，哪些是回答本题**必需**的，哪些**可有可无**？")
    lines.append("C. 参考答案是否被这些块支撑？有没有块里出现、而参考答案**漏掉**的要点？")
    lines.append("")
    lines.append("【输出格式】只输出如下 JSON（不要代码块围栏、不要额外文字）：")
    lines.append("{")
    lines.append('  "verdict": "成立|部分成立|不成立",')
    lines.append('  "necessary_chunks": [chunk_id, ...],')
    lines.append('  "optional_chunks": [chunk_id, ...],')
    lines.append('  "answer_supported": true 或 false,')
    lines.append('  "missing_from_answer": ["块里出现但参考答案漏掉的要点", ...],')
    lines.append('  "insufficient_reason": "当 verdict 不是「成立」或 answer_supported 为 false 时，说明为什么；否则填空字符串"')
    lines.append("}")
    lines.append("")
    lines.append("约束：`necessary_chunks` 与 `optional_chunks` 的取值必须来自上面出现过的 chunk_id；"
                 "两块集合不得有交集；若某块不需要，可只放进 optional_chunks。"
                 "`verdict` 只能取 成立／部分成立／不成立 三者之一。")
    return "\n".join(lines)


def prompt_blindness_violations(prompt: str) -> list:
    return [w for w in FORBIDDEN_IN_PROMPT if w in prompt]


# ---------------------------------------------------------------------------
# 5. 返回解析
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str):
    """从返回正文里取出第一个 JSON 对象；失败返回 None。"""
    if not text:
        return None
    candidates = []
    m = _FENCE.search(text)
    if m:
        candidates.append(m.group(1))
    candidates.append(text)
    for cand in candidates:
        s = cand.find("{")
        e = cand.rfind("}")
        if s == -1 or e == -1 or e < s:
            continue
        try:
            return json.loads(cand[s:e + 1])
        except ValueError:
            continue
    return None


def normalize_review(obj, gold_ids: set) -> dict:
    """把模型返回规范化成固定形状；越界/缺失一律记异常，不伪造。"""
    problems = []
    verdict = obj.get("verdict")
    if verdict not in VERDICTS:
        problems.append("verdict 非法或缺失：%r" % (verdict,))
        verdict = None
    ans = obj.get("answer_supported")
    if not isinstance(ans, bool):
        problems.append("answer_supported 非布尔：%r" % (ans,))
        ans = None

    def _id_list(name):
        raw = obj.get(name)
        if not isinstance(raw, list):
            problems.append("%s 非数组：%r" % (name, raw))
            return []
        out = []
        for v in raw:
            try:
                iv = int(v)
            except (TypeError, ValueError):
                problems.append("%s 含非整数项：%r" % (name, v))
                continue
            if iv not in gold_ids:
                problems.append("%s 含越界 chunk_id：%d" % (name, iv))
                continue
            out.append(iv)
        return sorted(set(out))

    nec = _id_list("necessary_chunks")
    opt = _id_list("optional_chunks")
    both = sorted(set(nec) & set(opt))
    if both:
        problems.append("necessary 与 optional 交集非空：%s" % both)

    miss = obj.get("missing_from_answer")
    if not isinstance(miss, list):
        problems.append("missing_from_answer 非数组：%r" % (miss,))
        miss = []
    miss = [str(x) for x in miss]

    reason = obj.get("insufficient_reason")
    if not isinstance(reason, str):
        problems.append("insufficient_reason 非字符串：%r" % (reason,))
        reason = ""

    return {
        "verdict": verdict,
        "necessary_chunks": nec,
        "optional_chunks": opt,
        "answer_supported": ans,
        "missing_from_answer": miss,
        "insufficient_reason": reason,
        "normalize_problems": problems,
    }


# ---------------------------------------------------------------------------
# 6. 调用与缓存
# ---------------------------------------------------------------------------
def cache_path(vendor_key: str, qid: str) -> str:
    return os.path.join(WORK_DIR, vendor_key, "cache", "%s.json" % qid)


def call_model(vendor: dict, system: str, user: str, cache_key_obj: dict, replay: bool) -> dict:
    """调用一次模型；原始返回（含 usage）进缓存。replay 时命中缓存不再调用。

    缓存条目**不含墙钟**，因此同一输入重放时缓存与产出逐字节一致。
    """
    path = cache_key_obj["path"]
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            entry = json.load(fh)
        entry["_from_cache"] = True
        return entry
    if replay:
        raise RuntimeError("replay 模式下缓存未命中：%s（不得回退到接口）" % path)

    from openai import OpenAI
    client = OpenAI(api_key=vendor["_key"], base_url=vendor["_base_url"], timeout=TIMEOUT_SECONDS)

    attempts = []
    last_text = ""
    last_usage = None
    resolved = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        t0 = time.time()
        resp = client.chat.completions.create(
            model=vendor["model"],
            temperature=vendor["temperature"],
            max_tokens=MAX_TOKENS,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        dt = time.time() - t0
        choice = resp.choices[0]
        text = choice.message.content or ""
        u = resp.usage
        details = getattr(u, "completion_tokens_details", None)
        usage = {
            "prompt_tokens": int(getattr(u, "prompt_tokens", 0) or 0),
            "completion_tokens": int(getattr(u, "completion_tokens", 0) or 0),
            "total_tokens": int(getattr(u, "total_tokens", 0) or 0),
            "reasoning_tokens": int(getattr(details, "reasoning_tokens", 0) or 0) if details else 0,
        }
        attempts.append({
            "attempt": attempt,
            "elapsed_seconds": round(dt, 3),
            "finish_reason": choice.finish_reason,
            "raw_text": text,
            "usage": usage,
        })
        last_text, last_usage, resolved = text, usage, getattr(resp, "model", None)

        parsed_ok = extract_json(text) is not None
        truncated = choice.finish_reason == "length"
        if parsed_ok and not truncated:
            break

    entry = {
        "cache_schema": CACHE_SCHEMA,
        "vendor": vendor["key"],
        "model": vendor["model"],
        "model_resolved": resolved,
        "prompt_version": PROMPT_VERSION,
        "output_schema": OUTPUT_SCHEMA,
        "input_sha256": cache_key_obj["input_sha256"],
        "attempts": attempts,
        "usage": last_usage,
        "raw_text": last_text,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_json(path, entry)
    entry["_from_cache"] = False
    return entry


# ---------------------------------------------------------------------------
# 7. 单家跑一遍
# ---------------------------------------------------------------------------
def run_vendor(vendor: dict, questions: list, chunks: dict, replay: bool, log) -> dict:
    """对一家厂商跑全部 30 题，返回该家的结果（含逐题记录与汇总）。"""
    vkey = vendor["key"]
    results = []
    token_total = 0
    gate_hit = False
    for q in questions:
        qid = q["qid"]
        gold_ids = set(int(c) for c in q["gold_evidence_chunk_ids"])
        user = build_user_prompt(q, chunks)
        violations = prompt_blindness_violations(user)
        if violations:
            raise SystemExit("盲标自检失败（提示词含禁止字样 %s）：%s" % (violations, qid))
        path = cache_path(vkey, qid)
        key_obj = {"path": path, "input_sha256": sha256_text(SYSTEM_PROMPT + "\x00" + user)}

        if not replay and token_total > TOKEN_GATE_PER_VENDOR:
            gate_hit = True
            raise SystemExit("成本闸门：%s 累计 token 已超过 %d，按约定停下并报告。"
                             % (vkey, TOKEN_GATE_PER_VENDOR))
        try:
            entry = call_model(vendor, SYSTEM_PROMPT, user, key_obj, replay)
        except Exception as exc:                       # 传输层／鉴权失败：如实登记
            if replay and "缓存未命中" in str(exc):
                raise                                   # 重放缺缓存：直接失败，不得降级成「调用失败」
            log("  [%s] %s 调用失败：%s" % (vkey, qid, type(exc).__name__))
            results.append({
                "qid": qid, "ok": False,
                "error": "%s: %s" % (type(exc).__name__, str(exc)[:200]),
            })
            continue

        parsed = extract_json(entry["raw_text"])
        if parsed is None:
            review = {"verdict": None, "necessary_chunks": [], "optional_chunks": [],
                      "answer_supported": None, "missing_from_answer": [],
                      "insufficient_reason": "", "normalize_problems": ["返回不是合法 JSON"]}
        else:
            review = normalize_review(parsed, gold_ids)

        usage = entry.get("usage") or {}
        token_total += int(usage.get("total_tokens", 0) or 0)
        results.append({
            "qid": qid,
            "ok": True,
            "model": entry.get("model"),
            "model_resolved": entry.get("model_resolved"),
            "prompt_version": PROMPT_VERSION,
            "output_schema": OUTPUT_SCHEMA,
            "attempts": len(entry.get("attempts") or []),
            # 不登记 used_cache：那是「本次是不是重放」的运行态标志，写进产物会让
            # 首跑与重放的输出不再逐字节一致；「原始返回在缓存里」由 cache/<qid>.json 自证。
            "usage": usage,
            "verdict": review["verdict"],
            "necessary_chunks": review["necessary_chunks"],
            "optional_chunks": review["optional_chunks"],
            "answer_supported": review["answer_supported"],
            "missing_from_answer": review["missing_from_answer"],
            "insufficient_reason": review["insufficient_reason"],
            "normalize_problems": review["normalize_problems"],
            "raw_sha256": sha256_text(entry["raw_text"]),
        })
        log("  [%s] %s verdict=%s needed=%d optional=%d supported=%s tokens=%s"
            % (vkey, qid, review["verdict"], len(review["necessary_chunks"]),
               len(review["optional_chunks"]), review["answer_supported"],
               usage.get("total_tokens")))

    ok_rows = [r for r in results if r["ok"]]
    verdict_counts = {v: 0 for v in VERDICTS}
    for r in ok_rows:
        if r["verdict"] in verdict_counts:
            verdict_counts[r["verdict"]] += 1
    usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0,
                    "total_tokens": 0}
    for r in ok_rows:
        for k in usage_totals:
            usage_totals[k] += int((r["usage"] or {}).get(k, 0) or 0)

    out_dir = os.path.join(WORK_DIR, vkey)
    write_jsonl(os.path.join(out_dir, "review.jsonl"), ok_rows)
    summary = {
        "vendor": vkey,
        "vendor_label": vendor["label"],
        "model": vendor["model"],
        "base_url": vendor["base_url"],
        "key_source": vendor["key_source"],
        "prompt_version": PROMPT_VERSION,
        "output_schema": OUTPUT_SCHEMA,
        "questions_total": len(questions),
        "answered": len(ok_rows),
        "failed": len(results) - len(ok_rows),
        "verdict_counts": verdict_counts,
        "usage_totals": usage_totals,
        "token_gate_per_vendor": TOKEN_GATE_PER_VENDOR,
        "token_gate_hit": gate_hit,
        "model_source": vendor["model_source"],
    }
    write_json(os.path.join(out_dir, "summary.json"), summary)
    return {"summary": summary, "results": results, "ok_rows": ok_rows}


# ---------------------------------------------------------------------------
# 8. 跨厂商一致率与台账
# ---------------------------------------------------------------------------
def cross_vendor(per_vendor_results: dict, questions: list, scope_keys: list) -> dict:
    """在给定线集合内逐题比对 verdict；两家以上作答才算一次可比较，全同记为一致。

    `scope_keys` 决定口径：确认口径只传 kimi／zhipu 两家；留痕口径才把已剥离的那条线算进来。
    """
    scope_keys = [k for k in scope_keys if k in per_vendor_results]
    rows = []
    for q in questions:
        qid = q["qid"]
        vs = {}
        for vkey in scope_keys:
            res = per_vendor_results[vkey]
            hit = next((r for r in res["ok_rows"] if r["qid"] == qid), None)
            if hit is not None:
                vs[vkey] = hit["verdict"]
        values = [x for x in vs.values() if x is not None]
        comparable = len(values) >= 2
        consistent = comparable and len(set(values)) == 1
        rows.append({
            "qid": qid,
            "verdicts": vs,
            "comparable": comparable,
            "consistent": consistent,
        })
    comparable_rows = [r for r in rows if r["comparable"]]
    consistent_rows = [r for r in rows if r["consistent"]]
    rate = (len(consistent_rows) / len(comparable_rows)) if comparable_rows else None
    return {
        "per_question": rows,
        "comparable_questions": len(comparable_rows),
        "consistent_questions": len(consistent_rows),
        "consistency_rate": (round(rate, 4) if rate is not None else None),
        "scope": list(scope_keys),
        "note": "一致率＝该口径内跨厂商 verdict 完全相同的题数／各线都作答的题数；"
                "它是**模型间一致率**，不是人工一致率、不是金标准。",
    }


def load_excluded_trace(questions: list, log=None) -> dict:
    """只读**已剥离线**的留痕目录（不调接口、不需要凭据）；留痕缺失时跳过、不报错。

    这是 `--profile replay` 能“不因该线缺失而报错”的关键：历史结果只按留痕口径登记，
    永远不参与“参与确认的两家”的汇总。
    """
    out = {}
    for spec in EXCLUDED_TRACE_VENDORS:
        d = spec["trace_dir"]
        summary_path = os.path.join(d, "summary.json")
        review_path = os.path.join(d, "review.jsonl")
        if not (os.path.exists(summary_path) and os.path.exists(review_path)):
            if log:
                log("== 留痕线 %s：未找到历史留痕目录，跳过（不影响本次确认）==" % spec["key"])
            continue
        try:
            with open(summary_path, encoding="utf-8") as fh:
                summary = json.load(fh)
            ok_rows = list(iter_jsonl(review_path))
        except (OSError, ValueError) as exc:
            if log:
                log("== 留痕线 %s：历史留痕读取失败（%s），跳过（不影响本次确认）=="
                    % (spec["key"], type(exc).__name__))
            continue
        summary = dict(summary)
        summary["excluded_per_author"] = True
        summary["exclusion_reason"] = spec["exclusion_reason"]
        summary["trace_dir"] = os.path.relpath(d, ROOT).replace("\\", "/")
        summary["summary_source"] = "历史留痕 summary.json 与 review.jsonl（只读；该线不调用、不参与本次确认）"
        out[spec["key"]] = {"summary": summary, "results": ok_rows, "ok_rows": ok_rows,
                            "trace_only": True}
    return out


def _usage_sum(per_vendor_results: dict) -> dict:
    tot = {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
    for res in per_vendor_results.values():
        for k in tot:
            tot[k] += int((res["summary"].get("usage_totals") or {}).get(k, 0) or 0)
    return tot


def build_ledger(confirmed_results: dict, trace_results: dict, cross_confirmed: dict,
                 cross_all_lines: dict, questions: list, changed_qids: list) -> dict:
    lines = []
    for scope_map, excluded in ((confirmed_results, False), (trace_results, True)):
        for vkey, res in scope_map.items():
            s = res["summary"]
            lines.append({
                "vendor": vkey,
                "vendor_label": s["vendor_label"],
                "model": s["model"],
                "base_url": s["base_url"],
                "key_source": s["key_source"],
                "prompt_version": s["prompt_version"],
                "output_schema": s["output_schema"],
                "questions_total": s["questions_total"],
                "answered": s["answered"],
                "failed": s["failed"],
                "verdict_counts": s["verdict_counts"],
                "usage_totals": s["usage_totals"],
                "token_gate_per_vendor": s["token_gate_per_vendor"],
                "token_gate_hit": s["token_gate_hit"],
                "excluded_per_author": bool(excluded or s.get("excluded_per_author")),
                "exclusion_reason": s.get("exclusion_reason"),
                "trace_dir": s.get("trace_dir"),
                "summary_source": s.get("summary_source", "本次运行（该线参与本次确认）"),
                "per_question_attempts": {r["qid"]: r["attempts"] for r in res["ok_rows"]},
                "per_question_usage": {r["qid"]: r["usage"] for r in res["ok_rows"]},
            })
    confirmed_usage = _usage_sum(confirmed_results)
    all_usage = _usage_sum(confirmed_results)
    for k, v in _usage_sum(trace_results).items():
        all_usage[k] = all_usage[k] + v
    return {
        "ledger_schema": "stage7-thirdparty-review-ledger-1.1",
        "prompt_version": PROMPT_VERSION,
        "output_schema": OUTPUT_SCHEMA,
        "questions_total": len(questions),
        "vendors": lines,
        "token_gate_total": TOKEN_GATE_TOTAL,
        "confirmed_lines": list(confirmed_results.keys()),
        "excluded_lines": list(trace_results.keys()),
        "usage_totals": confirmed_usage,
        "usage_totals_confirmation": confirmed_usage,
        "usage_totals_all_lines_trace": all_usage,
        "token_grand_total": all_usage,
        "token_grand_total_confirmation": confirmed_usage,
        "cross_vendor": {
            "scope": cross_confirmed["scope"],
            "comparable_questions": cross_confirmed["comparable_questions"],
            "consistent_questions": cross_confirmed["consistent_questions"],
            "consistency_rate": cross_confirmed["consistency_rate"],
            "per_question_verdicts": {r["qid"]: r["verdicts"] for r in cross_confirmed["per_question"]},
        },
        "cross_vendor_all_lines_trace": {
            "scope": cross_all_lines["scope"],
            "comparable_questions": cross_all_lines["comparable_questions"],
            "consistent_questions": cross_all_lines["consistent_questions"],
            "consistency_rate": cross_all_lines["consistency_rate"],
            "per_question_verdicts": {r["qid"]: r["verdicts"] for r in cross_all_lines["per_question"]},
        },
        "gold_changed_qids": sorted(changed_qids),
        "adjudications": dict(ADJUDICATIONS),
        "line_scope_note": "本次确认采用两家（Moonshot `kimi-k3`、智谱 `glm-5.3-flash`）。"
                           "百度千帆 `ernie-5.1` 一条**原已完整跑通（30/30、0 失败、60,073 token）**，"
                           "但作者指示该通道不可用、其凭据已从 `交付物/03-代码/抽取与图谱/config.local.json` 删除，"
                           "故**不参与本次确认**（vendors[] 里保留该条并标 `excluded_per_author: true`）；"
                           "其 30 条原始返回与结果保留在 `交付物/05-系统实现/RAG检索系统/_工作底稿/第三方复核/qianfan/` 作为留痕。"
                           "为此 usage_totals 与一致率并列给出两个口径：`*_confirmation`（两家，确认口径）与 "
                           "`*_all_lines_trace`（三家，留痕口径）；留痕口径只作历史记录，不代表确认结论。",
        "note": "本台账是**第三方模型盲标复核**的记录；参与确认的两家厂商不同 ⇒ 具备跨厂商证据性，"
                "但**仍不等于事实**，也**不是人工确认、不是金标准**。人工抽检未做。",
    }


# ---------------------------------------------------------------------------
# 9. profile
# ---------------------------------------------------------------------------
def _prev_summary(vkey: str):
    p = os.path.join(WORK_DIR, vkey, "summary.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _cache_complete(vkey: str, qids) -> bool:
    return all(os.path.exists(cache_path(vkey, q)) for q in qids)


def select_vendors(local: dict, only: list, replay: bool = False, qids=()) -> list:
    """挑出可用厂商。

    `replay` 只用缓存，**不需要凭据**：若凭据已不可得（例如凭据文件被别的任务改动），
    只要首跑的 `summary.json` 与 30 题缓存都在，就从它们复原厂商身份（模型名／端点／来源），
    保证重放与首跑逐字节一致；否则才判为不可用。
    """
    out = []
    for v in VENDORS:
        if only and v["key"] not in only:
            continue
        rv = resolve_vendor(v, local)
        if not rv["_key"] or not rv["_base_url"]:
            prev = _prev_summary(v["key"]) if replay else None
            if prev and _cache_complete(v["key"], qids):
                rv["base_url"] = prev["base_url"]
                rv["model"] = prev["model"]
                rv["key_source"] = prev["key_source"]
                rv["model_source"] = prev.get("model_source", rv["model_source"])
                rv["_key"] = ""
                rv["unavailable"] = None
                rv["replay_meta"] = "由首跑 summary.json 复原（replay 只读缓存，不取凭据）"
            else:
                rv["unavailable"] = "无凭据或端点缺失"
        else:
            rv["unavailable"] = None
        out.append(rv)
    return out


def profile_selftest(questions: list, chunks: dict) -> int:
    bad = 0
    for q in questions:
        user = build_user_prompt(q, chunks)
        vio = prompt_blindness_violations(user)
        if vio:
            bad += 1
            print("  !! %s 提示词含禁止字样：%s" % (q["qid"], vio))
    print("[T9-3rd] 盲标自检：%d 题，违规 %d 题" % (len(questions), bad))
    return 2 if bad else 0


def profile_run(questions: list, chunks: dict, only: list, replay: bool) -> int:
    local = read_local_config()
    vendors = select_vendors(local, only, replay, [q["qid"] for q in questions])

    def log(msg):
        print(msg, flush=True)

    excluded_requested = [k for k in only if k in {s["key"] for s in EXCLUDED_TRACE_VENDORS}]
    if excluded_requested:
        log("== 已按作者指示剥离的线 %s：不参与确认、没有可调用端点，只作留痕，跳过 =="
            % ",".join(excluded_requested))

    per_vendor = {}
    for v in vendors:
        if v["unavailable"]:
            log("== 跳过 %s：%s ==" % (v["key"], v["unavailable"]))
            continue
        log("== 开始 %s（%s，model=%s，key_source=%s）==" % (v["key"], v["label"], v["model"], v["key_source"]))
        if v.get("replay_meta"):
            log("   （%s）" % v["replay_meta"])
        per_vendor[v["key"]] = run_vendor(v, questions, chunks, replay, log)

    if not per_vendor:
        if only and all(k in {s["key"] for s in EXCLUDED_TRACE_VENDORS} for k in only):
            print("[T9-3rd] 请求的线都已按作者指示剥离（只作留痕、不参与确认）；无需运行，0 次调用。")
            return 0
        print("[T9-3rd] 没有任何可用厂商，未产生复核结果。")
        return 1

    # 留痕口径：只读已按作者指示剥离那条线的历史缓存/结果（不调用、不需要凭据；缺失即跳过）
    trace = load_excluded_trace(questions, log)
    confirmed_keys = list(per_vendor.keys())
    all_keys = confirmed_keys + list(trace.keys())
    cross_confirmed = cross_vendor(per_vendor, questions, confirmed_keys)
    cross_all_lines = cross_vendor({**per_vendor, **trace}, questions, all_keys)
    changed = list(GOLD_CHANGED_QIDS)
    ledger = build_ledger(per_vendor, trace, cross_confirmed, cross_all_lines, questions, changed)
    write_json(LEDGER_PATH, ledger)

    # 跨厂商一致率的产品（确定性）
    write_json(os.path.join(WORK_DIR, "cross_vendor.json"), cross_confirmed)
    write_json(os.path.join(WORK_DIR, "cross_vendor_all_lines_trace.json"), cross_all_lines)

    total = ledger["token_grand_total"]["total_tokens"]
    confirm_total = ledger["token_grand_total_confirmation"]["total_tokens"]
    print("[T9-3rd] 完成：参与确认 %d 家%s"
          % (len(per_vendor),
             ("；留痕线 %s（不参与确认）" % ",".join(trace.keys())) if trace else "；留痕线 0 条"))
    print("[T9-3rd] 确认口径（%s）跨厂商一致率 %s（%d/%d 题）、token 合计 %d"
          % ("+".join(confirmed_keys), cross_confirmed["consistency_rate"],
             cross_confirmed["consistent_questions"], cross_confirmed["comparable_questions"],
             confirm_total))
    print("[T9-3rd] 留痕口径（%s）跨厂商一致率 %s（%d/%d 题）、token 合计 %d"
          % ("+".join(all_keys), cross_all_lines["consistency_rate"],
             cross_all_lines["consistent_questions"], cross_all_lines["comparable_questions"],
             total))
    if total > TOKEN_GATE_TOTAL:
        print("[T9-3rd] 留痕口径 token 合计超过闸门 %d，停下并报告。" % TOKEN_GATE_TOTAL)
        return 3
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="第 7 阶段预实验问题集的第三方模型盲标复核")
    parser.add_argument("--profile", choices=["run", "replay", "selftest"], default="run")
    parser.add_argument("--replay", action="store_true", help="等价于 --profile replay（只读缓存、0 次调用）")
    parser.add_argument("--selftest", action="store_true", help="等价于 --profile selftest")
    parser.add_argument("--vendors", default="", help="逗号分隔的厂商子集（kimi,zhipu）；默认全部（参与确认的两家）")
    args = parser.parse_args(argv)

    if args.selftest:
        args.profile = "selftest"
    elif args.replay:
        args.profile = "replay"
    only = [x.strip() for x in args.vendors.split(",") if x.strip()]
    questions = load_questions()
    chunks = load_chunks()

    if args.profile == "selftest":
        return profile_selftest(questions, chunks)
    return profile_run(questions, chunks, only, replay=(args.profile == "replay"))


if __name__ == "__main__":
    raise SystemExit(main())
