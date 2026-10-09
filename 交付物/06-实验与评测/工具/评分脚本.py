#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""阶段10 · 问答质量评分（跨厂商模型评审 / LLM-as-judge）—— 只评已跑好的答案，不生成任何答案。

============================================================================
这份脚本做什么（以及严格不做什么）
============================================================================
做：
  读 `交付物/06-实验与评测/对照产出_v13/{A..E}/qa_records.jsonl`（与同目录
  `answer_trace.jsonl`）里**已经跑好**的 30 题 × A～E 五组 ＝ 150 条答案，
  按《02-项目执行总控文档》第12.7节 的 0／1／2 量表**逐字**调用**跨厂商**大模型打分，
  把逐条评分、汇总读数、跨模型一致率与调用台账落盘。

不做（硬边界，本脚本没有任何一条代码路径会碰）：
  · 不生成任何答案、不跑题、不调生成侧模型；
  · 不修改 `对照产出_v13/`（只读打开）、不改 `交付物/03-代码/` 与 `工具/` 下任何既有文件；
  · 不做任何 git 写操作。

============================================================================
judge 选型（跨厂商，不得用生成侧同款）
============================================================================
生成侧模型是 `deepseek-flash`，因此两个 judge 都**不是**它：
  · 主 judge ＝ Moonshot `kimi-k3`（对全部 150 条 × 3 维度评分）；
  · 副 judge ＝ 智谱 `glm-5.3-flash`（对 6 题 × 5 组 ＝ 30 条 × 3 维度评分，做跨模型交叉核对）。
凭据只从环境变量（`KIMI_API_KEY` / `ZHIPU_API_KEY`，端点可经 `KIMI_BASE_URL` 等覆盖）读，
缺失再回退到 `交付物/03-代码/抽取与图谱/config.local.json`（`.gitignore` 已覆盖 `config.local.*`）。
**凭据不进任何产物、日志或标准输出**：本脚本只打印 key 的来源（env / config.local）。

============================================================================
可重跑与续跑
============================================================================
每一次调用的**原始返回**（含 usage、解析结果、实际解析到的 model id）落在
`问答评分/_judge原始返回/<judge>/<prompt_version>/<key>.json`。重跑时：
  · 缓存命中且输入 sha256 一致 ⇒ **直接复用，不重复烧调用**；
  · 输入变了（换 prompt 版本、换答案）⇒ 输入 sha256 不一致，重算该条；
  · 调用失败 ⇒ 该条不写 ok 缓存，下次重跑只补这一条。
因此「冒烟」的 10 条会被全量运行直接复用（同一 judge／同一 prompt 版本／同一输入）。

============================================================================
预算护栏
============================================================================
`--max-calls`（默认 900）是**含重试**的调用上限。台账里已有的尝试次数 + 本轮已发次数
一旦触到上限，脚本抛错停下，不静默超支。

用法：
  python 工具/评分脚本.py --probe        # 只探两个 judge 的连通性与实测 model id（2 次调用）
  python 工具/评分脚本.py --selftest     # 零调用：装配 150 条输入并自检完整性
  python 工具/评分脚本.py --smoke        # 冒烟 10 条（2 题 × 5 组）× 3 维（主 judge）
  python 工具/评分脚本.py --run --judge kimi     # 主 judge 全量 150 条 × 3 维
  python 工具/评分脚本.py --run --judge zhipu    # 副 judge 30 条 × 3 维
  python 工具/评分脚本.py --adjudicate  # 两家不一致的维度由副 judge 复核证据给出最终分
  python 工具/评分脚本.py --report       # 零调用：重出评分记录／汇总／报告
  python 工具/评分脚本.py --all          # probe → smoke → kimi 全量 → zhipu 交叉 → 复核 → report
  python 工具/评分脚本.py --status       # 零调用：看缓存与台账现状
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from collections import OrderedDict
from datetime import datetime

# ---------------------------------------------------------------------------
# 0. 路径与常量
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
STAGE10 = os.path.dirname(HERE)
# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\工具\` 整体移到
# `交付物/06-实验与评测\工具\`（**下移一层**）：STAGE10 仍是"工具"的上一级（不变），
# 但工作区根还要再上一层，故在 STAGE10 之上多取一次 dirname。
ROOT = os.path.dirname(os.path.dirname(STAGE10))

V13 = os.path.join(STAGE10, "对照产出_v13")
OUT_DIR = os.path.join(STAGE10, "问答评分")
CACHE_DIR = os.path.join(OUT_DIR, "_judge原始返回")
RECORDS_PATH = os.path.join(OUT_DIR, "评分记录.jsonl")
SUMMARY_PATH = os.path.join(OUT_DIR, "评分汇总.json")
REPORT_PATH = os.path.join(OUT_DIR, "问答评分报告.md")
LEDGER_PATH = os.path.join(OUT_DIR, "调用台账.json")
JUDGE_CFG_PATH = os.path.join(OUT_DIR, "_judge配置.json")

QUESTIONS_PATH = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集", "questions.jsonl")
CHUNKS_PATH = os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")
LOCAL_CONFIG_PATH = os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "config.local.json")
AC_COMPARE_PATH = os.path.join(V13, "A_vs_C_对照.json")

GROUPS = ("A", "B", "C", "D", "E")
GROUP_LABEL = {
    "A": "A 组 · Vector RAG（基线）",
    "B": "B 组 · Vector RAG + 1-hop 图谱",
    "C": "C 组 · Vector RAG + 2-hop 图谱（Method）",
    "D": "D 组 · C + 时间过滤",
    "E": "E 组 · D + 证据排序",
}

PROMPT_VERSION = "stage10-qa-judge-v1.0"
# 不一致样本的最终分复核用独立版本号（《02》第12.7节 2026-10-04 口径变更段：
# 「跨模型核对不一致的样本，由副 judge 复核证据后给出最终分，并在实验记录中保留两次评分与不一致原因」）
PROMPT_VERSION_ADJ = "stage10-qa-judge-v1.0-adj"
CACHE_SCHEMA = "stage10-qa-judge-cache-v1"
LEDGER_SCHEMA = "stage10-qa-judge-ledger-v1"
RECORD_SCHEMA = "stage10-qa-judge-record-v1"

# 《02-项目执行总控文档》第12.7节 的量表**原文**（逐字照抄，不得自创、不得改写）
SCALE_SOURCE = "《02-项目执行总控文档》第12.7节「评价指标与定义」"
SCALE_VERBATIM = "Answer Accuracy：0 = 错误，1 = 部分正确，2 = 完全正确。Completeness：0 = 关键信息大量遗漏，1 = 基本覆盖，2 = 信息完整。Faithfulness：0 = 存在明显无依据事实，1 = 少量不严谨，2 = 完全基于证据。"
DOC02_PATH = os.path.join(ROOT, "02-项目执行总控文档.md")

# 《02》第12.8节 判定规则与判定范围的**原文**（逐字引用、一字未改）。
# 只在非 pr 档的报告正文里引用（为的是让预实验集那份报告逐字节不变）；
# 改造后用逐字包含性检查核对过与 `02-项目执行总控文档.md` 第12.8节 的原文一致。
RULE_128_VERBATIM = (
    "对**关系型子集**（任务类型为\"关系型\"的题目）、**多跳型子集**（路径深度为 1-hop 或 2-hop 的题目，"
    "即 gold_hop_depth ≥ 1）、**时序型子集**（时间约束为\"有\"的题目）各自独立应用同一条规则——"
    "若 KG-RAG 在该子集上的 Complete Evidence Recall@K 高于 Vector RAG，且该子集的 Answer Accuracy "
    "不下降（持平或提升），则判定知识图谱在该类问题上提供了额外检索价值。"
)
RULE_128_SCOPE_VERBATIM = (
    "该判定以核心测试集的 108 题为依据，压力测试子集仅作为附加观察参与讨论，不作为本节主体判定的依据。"
)


def current_02_version() -> str:
    """从《02》修订记录表里取最后一条 `| vX.Y |` 作为现行基线版本号（只读）。"""
    import re
    try:
        with open(DOC02_PATH, "r", encoding="utf-8") as fh:
            found = re.findall(r"^\|\s*(v\d+\.\d+)\s*\|", fh.read(), re.M)
    except OSError:
        return ""
    return found[-1] if found else ""

DIMENSIONS = (
    ("answer_accuracy", "Answer Accuracy", "0 = 错误，1 = 部分正确，2 = 完全正确",
     "答案与【参考答案】对照后的正确程度。判的是「答对没有」，不是「写得好不好」。"),
    ("completeness", "Completeness", "0 = 关键信息大量遗漏，1 = 基本覆盖，2 = 信息完整",
     "答案对【参考答案】所含关键信息的覆盖程度。判的是「漏没漏」；答非所问按大量遗漏处理。"),
    ("faithfulness", "Faithfulness", "0 = 存在明显无依据事实，1 = 少量不严谨，2 = 完全基于证据",
     "答案里的**事实性说法**是否能被【被评答案可用证据】支撑。判的是「有没有编」；"
     "只认【被评答案可用证据】，不得把【该题 gold 证据】当作支撑来源。"),
)

# 《02》第12.8节 的三个子集（口径照既有 `交付物/06-实验与评测/工具/跑AC对照.py` 第 63～68 行）
SUBSETS = (
    ("关系型", lambda q: q.get("task_type") == "关系型"),
    ("多跳型", lambda q: int(q.get("gold_hop_depth") or 0) >= 1),
    ("时序型", lambda q: q.get("time_constraint") == "有"),
)

# 冒烟样本：2 题 × 5 组 ＝ 10 条。两题取在标签谱的两端，覆盖面最宽。
SMOKE_QIDS = ("PE-01", "PE-27")

# 副 judge 交叉核对样本：6 题 × 5 组 ＝ 30 条（＝ 150 条的 20%）。
# 选取规则（确定性、按 qid 分层）：每个 (task_type × gold_hop_depth) 单元格优先取小组内
# 时间约束＝「有」的题，使三个子集（关系型／多跳型／时序型）与三种任务类型、三档跳数都被覆盖。
CROSS_CHECK_QIDS = ("PE-03", "PE-04", "PE-12", "PE-18", "PE-24", "PE-25")

# ---------------------------------------------------------------------------
# 0.1 数据集档案（**最小参数化改造**：只换「评谁／在哪读／在哪写／怎么抽样」，
#     量表、prompt、prompt 版本、评分与重试逻辑、缓存键构造**一字未改**）
# ---------------------------------------------------------------------------
# `pr`（默认档）的全部取值与改造前**逐字相同** ⇒ 预实验集那 5 件产物逐字节不变。
# `formal` ＝ 正式集：`对照产出_正式/{A..E}/qa_records.jsonl` 下**已经跑好的 582 条有效答案**
# （A 113／B 118／C 117／D 117／E 117；B1 组＝闭卷 LLM 辅助基线，**不在本次评分范围内**），
# 题集＝`交付物/06-实验与评测/测试集/questions.jsonl`（120 题：核心 108 ＋ 压力 12），
# 检索侧 ① 的读数直接取既有 `对照产出_正式/A_vs_C_对照.json` 的 `subsets_named_core`
# （核心集 108 题内的三子集 Complete Evidence Recall@K；**不重算、不改读数**）。
DATASET_PROFILES = {
    "pr": {
        "label": "预实验集（30 题 × A～E 五组 ＝ 150 条答案）",
        "sample_desc": "30 题 × 5 组",
        "answers_root": os.path.join(STAGE10, "对照产出_v13"),
        "out_dir": os.path.join(STAGE10, "问答评分"),
        "questions": os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集", "questions.jsonl"),
        "ac_compare": os.path.join(STAGE10, "对照产出_v13", "A_vs_C_对照.json"),
        "cer_source": "subsets",
        "per_group_expected": 30,
        "smoke_mode": ("qids", SMOKE_QIDS),
        "cross_mode": ("qids", CROSS_CHECK_QIDS),
        "core_only_128": False,
    },
    "formal": {
        "label": "正式集（120 题题集的 582 条有效答案：A 113／B 118／C 117／D 117／E 117）",
        "sample_desc": "120 题题集（有效答案 582 条；FQ-022 在 A～E 五组均未成功产出，故五组合计 582 而非 600）",
        "answers_root": os.path.join(STAGE10, "对照产出_正式"),
        "out_dir": os.path.join(STAGE10, "问答评分_正式"),
        "questions": os.path.join(STAGE10, "测试集", "questions.jsonl"),
        "ac_compare": os.path.join(STAGE10, "对照产出_正式", "A_vs_C_对照.json"),
        "cer_source": "subsets_named_core",
        "per_group_expected": None,
        "smoke_mode": ("per_group_stratified", 2),
        "cross_mode": ("per_group_systematic", 0.2),
        # 《02》第12.8节 明文「该判定以核心测试集的 108 题为依据，压力测试子集仅作为附加观察」，
        # 故正式档的 12.8 ② 只在核心集题目上计算；pr 档无核心／压力标签，维持改造前口径。
        "core_only_128": True,
    },
}

DATASET = "pr"
DATASET_LABEL = DATASET_PROFILES["pr"]["label"]
SAMPLE_DESC = DATASET_PROFILES["pr"]["sample_desc"]
CER_SOURCE = DATASET_PROFILES["pr"]["cer_source"]
PER_GROUP_EXPECTED = DATASET_PROFILES["pr"]["per_group_expected"]
SMOKE_MODE = DATASET_PROFILES["pr"]["smoke_mode"]
CROSS_MODE = DATASET_PROFILES["pr"]["cross_mode"]
CORE_ONLY_128 = DATASET_PROFILES["pr"]["core_only_128"]


def apply_dataset(name: str) -> None:
    """把模块级路径与抽样方式切到指定数据集档案；默认档 `pr` ＝ 改造前取值。"""
    global DATASET, DATASET_LABEL, SAMPLE_DESC, CER_SOURCE, PER_GROUP_EXPECTED
    global SMOKE_MODE, CROSS_MODE, CORE_ONLY_128
    global V13, OUT_DIR, CACHE_DIR, RECORDS_PATH, SUMMARY_PATH, REPORT_PATH
    global LEDGER_PATH, JUDGE_CFG_PATH, QUESTIONS_PATH, AC_COMPARE_PATH
    prof = DATASET_PROFILES[name]
    DATASET = name
    DATASET_LABEL = prof["label"]
    SAMPLE_DESC = prof["sample_desc"]
    CER_SOURCE = prof["cer_source"]
    PER_GROUP_EXPECTED = prof["per_group_expected"]
    SMOKE_MODE = prof["smoke_mode"]
    CROSS_MODE = prof["cross_mode"]
    CORE_ONLY_128 = prof["core_only_128"]
    V13 = prof["answers_root"]
    OUT_DIR = prof["out_dir"]
    CACHE_DIR = os.path.join(OUT_DIR, "_judge原始返回")
    RECORDS_PATH = os.path.join(OUT_DIR, "评分记录.jsonl")
    SUMMARY_PATH = os.path.join(OUT_DIR, "评分汇总.json")
    REPORT_PATH = os.path.join(OUT_DIR, "问答评分报告.md")
    LEDGER_PATH = os.path.join(OUT_DIR, "调用台账.json")
    JUDGE_CFG_PATH = os.path.join(OUT_DIR, "_judge配置.json")
    QUESTIONS_PATH = prof["questions"]
    AC_COMPARE_PATH = prof["ac_compare"]


MAX_CALLS_DEFAULT = 900            # 含重试的调用上限（作者授权上限）
MAX_ATTEMPTS = 3                   # 首次 + 最多 2 次重试
PACE_SECONDS = 1.2                 # 串行节奏（≈50 次/分钟，照 `工具/跑系统指标.py` 的 paced 档）
COOLDOWN_ON_RATE_LIMIT = 30.0      # 触发限流后的冷却（串行 + 冷却，不并发）
TIMEOUT_SECONDS = 180.0
# 输出上限：两家都给足。**2026-10-07 实测修正**：zhipu 原设 1600 时，Faithfulness 维度的少数
# 回答（要求逐条列举证据支撑）会被截断在 1600 token 上、返回的 JSON 不完整而不可用（4 格），
# 故与 kimi 同为 4000；截断仍按失败处理（`finish_reason == "length"` 不接受）。
MAX_TOKENS = {"kimi": 4000, "zhipu": 4000}
EVIDENCE_CHAR_CAP = 1600           # 单条证据正文进 prompt 的字符上限（只截断极长块，截断处有标记）
GOLD_CHAR_CAP = 1200

VENDORS = {
    "kimi": {
        "key": "kimi",
        "label": "Moonshot Kimi",
        "model": "kimi-k3",
        "base_field": "kimi_base_url",
        "key_field": "kimi_api_key",
        "env_key": "KIMI_API_KEY",
        "env_base": "KIMI_BASE_URL",
        "temperature_fallback": 1.0,
        "model_source": "config.local.json 的 kimi_model_hint（Moonshot 直连）",
    },
    "zhipu": {
        "key": "zhipu",
        "label": "智谱 Zhipu",
        "model": "glm-5.3-flash",
        "base_field": "zhipu_base_url",
        "key_field": "zhipu_api_key",
        "env_key": "ZHIPU_API_KEY",
        "env_base": "ZHIPU_BASE_URL",
        "temperature_fallback": 0.0,
        "model_source": "config.local.json 的 zhipu_base_url（智谱直连）",
    },
}

TEMPERATURE_REQ = 0.0              # 口径：temperature 0（若端点拒收，按实测回退并把实际值记进记录）


def log(msg: str) -> None:
    print(msg, flush=True)


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: str, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_jsonl(path: str, rows) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def iter_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


# ---------------------------------------------------------------------------
# 1. 凭据（只读来源，绝不落盘／绝不打印取值）
# ---------------------------------------------------------------------------
def read_local_config() -> dict:
    return read_json(LOCAL_CONFIG_PATH, {}) or {}


def credential(local_key: str, env_name: str, local: dict):
    """环境变量优先，缺失回退 config.local.json；返回 (取值, 来源标签)。"""
    value = os.environ.get(env_name, "").strip()
    if value:
        return value, "env:" + env_name
    value = str(local.get(local_key, "") or "").strip()
    if value:
        return value, "config.local:" + local_key
    return "", "missing"


def resolve_vendor(vj: dict, local: dict, temp_override=None) -> dict:
    out = dict(vj)
    key, key_src = credential(vj["key_field"], vj["env_key"], local)
    base, base_src = credential(vj["base_field"], vj["env_base"], local)
    out["_key"] = key
    out["_base_url"] = base
    out["key_source"] = key_src
    out["base_source"] = base_src
    out["has_key"] = bool(key)
    out["has_base"] = bool(base)
    if temp_override is not None:
        out["temperature"] = float(temp_override)
    else:
        out["temperature"] = float(TEMPERATURE_REQ)
    return out


def save_judge_cfg(cfg: dict) -> None:
    """把「实际可用的 temperature 与实际解析到的 model id」记在输出目录（不含凭据）。"""
    write_json(JUDGE_CFG_PATH, cfg)


def load_judge_cfg() -> dict:
    return read_json(JUDGE_CFG_PATH, {}) or {}


# ---------------------------------------------------------------------------
# 2. 输入装配：题集 / 文本块 / 五组答案
# ---------------------------------------------------------------------------
def load_questions() -> dict:
    out = {}
    for row in iter_jsonl(QUESTIONS_PATH):
        out[row["qid"]] = row
    return out


def load_chunks() -> dict:
    out = {}
    for row in iter_jsonl(CHUNKS_PATH):
        out[int(row["chunk_id"])] = {
            "doc_id": row.get("doc_id"),
            "content": row.get("content") or "",
            "token_count": row.get("token_count"),
        }
    return out


def load_group(group: str, questions: dict) -> list:
    """把一组 30 条答案装配成评分输入。

    `qa_records.jsonl` 是答案正文的落点；`answer_trace.jsonl` 提供证据列表与图谱路径。
    两份逐条对齐（顺位 + 正文逐字比对），不一致即报错，不静默取其一。
    注意数据实况：五组的 `answer.answer_id` 都是 `A-001`…（跨组重名），
    故主键用 `answer_key = <group>__<answer_id>`。
    """
    qa_path = os.path.join(V13, group, "qa_records.jsonl")
    tr_path = os.path.join(V13, group, "answer_trace.jsonl")
    if not (os.path.exists(qa_path) and os.path.exists(tr_path)):
        raise RuntimeError("缺输入：%s 或 %s" % (qa_path, tr_path))
    qa_rows = list(iter_jsonl(qa_path))
    tr_rows = list(iter_jsonl(tr_path))
    if len(qa_rows) != len(tr_rows):
        raise RuntimeError("%s：qa_records %d 条 ≠ answer_trace %d 条" % (group, len(qa_rows), len(tr_rows)))

    items = []
    for i, (qa, tr) in enumerate(zip(qa_rows, tr_rows)):
        ans = qa["answer"]
        if str(tr.get("group")) != group:
            raise RuntimeError("%s 第 %d 条 trace 的 group=%r 不符" % (group, i, tr.get("group")))
        if (ans.get("answer_text") or "") != (tr.get("answer_text") or ""):
            raise RuntimeError("%s 第 %d 条：qa_records 与 answer_trace 的正文不一致" % (group, i))
        qid = tr.get("qid")
        if qid not in questions:
            raise RuntimeError("%s 第 %d 条：qid=%r 不在 questions.jsonl" % (group, i, qid))
        q = questions[qid]
        # 说明：qa_records 的 question_id（Q-0xx）与题集的 qid（PE-xx）是两套编号，
        # 二者靠 `answer_trace.jsonl` 的 qid 字段对齐（上面已逐条校验），此处不作等值断言。
        items.append({
            "group": group,
            "answer_key": "%s__%s" % (group, ans.get("answer_id")),
            "answer_id": ans.get("answer_id"),
            "question_id": ans.get("question_id"),
            "qid": qid,
            "answer_text": ans.get("answer_text") or "",
            "is_graph_extended": bool(ans.get("is_graph_extended")),
            "graph_payload": tr.get("graph_payload") or {},
            "evidence": tr.get("evidence") or [],
            "answer_evidence": qa.get("answer_evidence") or [],
            "model_name": ans.get("model_name"),
            "gen_prompt_version": ans.get("prompt_version"),
            "question": q.get("question") or tr.get("question") or "",
            "reference_answer": q.get("reference_answer") or "",
            "gold_evidence_chunk_ids": [int(x) for x in (q.get("gold_evidence_chunk_ids") or [])],
            "task_type": q.get("task_type"),
            "gold_hop_depth": q.get("gold_hop_depth"),
            "time_constraint": q.get("time_constraint"),
        })
    return items


def load_all_answers(questions: dict) -> list:
    items = []
    for g in GROUPS:
        items.extend(load_group(g, questions))
    return items


def clip(text: str, cap: int) -> str:
    text = text or ""
    if len(text) <= cap:
        return text
    return text[:cap] + "…（此块过长，已按 %d 字截断留痕）" % cap


# ---------------------------------------------------------------------------
# 3. Prompt（固定版本号 stage10-qa-judge-v1.0）
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "你是一次毕业论文实验里的**独立评分模型**，按作者预先给定的 0／1／2 统一量表给一条问答答案打分。\n"
    "纪律（必须遵守）：\n"
    "1. 只按给定量表打分，不得引入量表之外的任何标准；量表取值只有 0、1、2 三个整数。\n"
    "2. 不得因为答案写得长、写得流畅、格式好看就抬高分数；也不得因为答案短就压低分数。\n"
    "3. 判 Faithfulness 时，只能以【被评答案可用证据】为支撑来源；证据里没有的说法就是没有支撑。\n"
    "4. 你只输出一个 JSON 对象，不输出任何解释性文字、不加代码块围栏。\n"
    "5. 即使材料不完整，也必须给出 0／1／2 中的一个整数，不得拒答、不得输出空值。\n"
)


def build_user_prompt(item: dict, dim: tuple, chunks: dict) -> str:
    dim_key, dim_label, dim_scale, dim_focus = dim
    L = []
    L.append("【评分任务】只评一个维度：%s" % dim_label)
    L.append("【量表（第12.7节原文，逐字）】%s" % dim_scale)
    L.append("【本维度判什么】%s" % dim_focus)
    L.append("")
    L.append("【题目】%s" % item["question"])
    L.append("【参考答案（金标准）】%s" % (item["reference_answer"] or "（本题集未提供参考答案）"))
    L.append("")

    gold_ids = item["gold_evidence_chunk_ids"]
    if gold_ids:
        L.append("【该题 gold 证据（只作 Accuracy／Completeness 的对照锚点，**不得**当作 Faithfulness 的支撑来源）】")
        for cid in gold_ids:
            c = chunks.get(int(cid)) or {}
            L.append("  · chunk_id=%s doc_id=%s：%s" % (cid, c.get("doc_id"), clip(c.get("content"), GOLD_CHAR_CAP)))
    else:
        L.append("【该题 gold 证据】无登记")
    L.append("")
    L.append("【被评答案（被评对象；其中的「【证据来源】」「【知识图谱路径】」等段落是系统拼装的固定结构）】")
    L.append(item["answer_text"] or "（空正文）")
    L.append("")
    L.append("【被评答案可用证据（本次问答实际检索到的证据全文）】")
    if not item["evidence"]:
        L.append("  （无证据）")
    for e in item["evidence"]:
        cid = e.get("chunk_id")
        c = chunks.get(int(cid)) if cid is not None else None
        c = c or {}
        L.append("  ── [证据%s] chunk_id=%s doc_id=%s 图谱来源=%s 标题=%s"
                 % (e.get("rank"), cid, e.get("doc_id"),
                    "是" if e.get("from_graph") else "否", (e.get("title") or "")[:80]))
        L.append("     %s" % clip(c.get("content"), EVIDENCE_CHAR_CAP))
    gp = item.get("graph_payload") or {}
    paths = gp.get("graph_path") or []
    L.append("")
    if paths:
        L.append("【知识图谱路径（本次回答实际带出的路径，条数 %d）】" % len(paths))
        for p in paths[:12]:
            L.append("  · depth=%s %s --%s--> %s" % (p.get("depth"), p.get("start"),
                                                    p.get("relations") or "（无关系标签）", p.get("end")))
    else:
        L.append("【知识图谱路径】未使用图谱扩展（本次回答无图谱路径）")
    L.append("")
    L.append("【输出格式】只输出如下 JSON（不要代码块围栏、不要任何额外文字）：")
    L.append('{"score": 0 或 1 或 2, "reason": "一句话中文理由，不超过 60 字，必须点出判这个分的依据"}')
    return "\n".join(L)


ADJ_SYSTEM_PROMPT = (
    "你是本次毕业论文实验里的**副 judge**（跨厂商模型评审的复核方）。现在要处理的是一条"
    "**两家 judge 打分不一致**的样本：请**重新对照证据**复核，给出该维度的**最终分**。\n"
    "纪律（必须遵守）：\n"
    "1. 只按给定 0／1／2 量表打分，不得引入量表之外的标准；取值只有 0、1、2 三个整数。\n"
    "2. 必须先看证据再下判断；不得因为「另一家给了某个分」就顺着它给分，也不得为求一致而折中。\n"
    "3. 判 Faithfulness 时只认【被评答案可用证据】。\n"
    "4. 你只输出一个 JSON 对象，不输出任何解释性文字、不加代码块围栏；不得拒答。\n"
)


def build_adjudication_prompt(item: dict, dim: tuple, chunks: dict,
                              a_score, a_reason, b_score, b_reason) -> str:
    """不一致样本的最终分复核 prompt：同一量表 + 完整证据上下文 + 两家分歧的两次评分与理由。"""
    base = build_user_prompt(item, dim, chunks)
    tail = [
        "",
        "【本条的两次评分（不一致，需要你复核后给最终分）】",
        "  · 主 judge（%s）给的 %s 分＝%s；理由：%s" % ("主 judge", dim[1], a_score, a_reason or "（无）"),
        "  · 副 judge（你上一次）给的 %s 分＝%s；理由：%s" % (dim[1], b_score, b_reason or "（无）"),
        "",
        "【请你做的事】重新对照上面的题目、参考答案与该答案可用证据，独立给出该维度的**最终分**，"
        "并说明两家不一致的原因出在哪里（是答案本身处在量表边界，还是某一方看漏/看多了证据）。",
        "【输出格式】只输出如下 JSON（不要代码块围栏、不要任何额外文字）：",
        '{"final_score": 0 或 1 或 2, "reason": "一句话中文理由（不超过 60 字）", '
        '"disagreement_note": "一句话说明两家不一致的原因（不超过 60 字）"}',
    ]
    return base + "\n" + "\n".join(tail)


# ---------------------------------------------------------------------------
# 4. 调用与缓存（串行 + 冷却 + 最多 2 次重试）
# ---------------------------------------------------------------------------
class BudgetExceeded(RuntimeError):
    pass


class Ledger:
    """逐次调用台账（不含凭据）。每次尝试后立即落盘，进程被杀也不丢账。

    口径（与「调用次数」的成本账严格对齐）：
      · `calls` 只记**真实发出的 HTTP 尝试**（含重试；重试的第 2／3 次都各占一行）；
      · **缓存命中不算调用**，另记在 `cache_hits` 段里（只是复用，不烧调用）。
    """

    def __init__(self, path: str, max_calls: int):
        self.path = path
        self.max_calls = int(max_calls)
        obj = read_json(path, None) or {}
        raw = list(obj.get("calls") or [])
        # 自迁移：早期版本把缓存命中混在 calls 里，这里按 from_cache 分流，不丢账也不虚增调用数。
        self.calls = [c for c in raw if not c.get("from_cache")]
        self.cache_hits = list(obj.get("cache_hits") or []) + [c for c in raw if c.get("from_cache")]
        self.seq = max([int(c.get("seq") or 0) for c in self.calls] + [0])

    def attempts_total(self) -> int:
        """真实 HTTP 尝试次数（不含缓存命中）。"""
        return len(self.calls)

    def _totals(self) -> dict:
        tot = {"attempts": 0, "ok": 0, "failed": 0, "retries": 0, "cache_hits": len(self.cache_hits),
               "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        for c in self.calls:
            tot["attempts"] += 1
            tot["ok" if c.get("ok") else "failed"] += 1
            if int(c.get("attempt") or 1) > 1:
                tot["retries"] += 1
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                tot[k] += int(c.get(k) or 0)
        return tot

    def flush(self) -> None:
        write_json(self.path, {
            "schema": LEDGER_SCHEMA,
            "generated_by": "交付物/06-实验与评测/工具/评分脚本.py",
            "generated_at": now_iso(),
            "prompt_version": PROMPT_VERSION,
            "scale_source": SCALE_SOURCE,
            "caliber": "attempts ＝ 真实发出的 HTTP 尝试次数（含重试）；缓存命中不计入调用次数，单列 cache_hits。",
            "budget": {"max_calls_including_retries": self.max_calls, "used": self.attempts_total()},
            "note": "本条台账逐次记录每一次 HTTP 尝试（含重试与冷却）；**不含任何凭据**，只记 key 的来源标签。",
            "totals": self._totals(),
            "calls": self.calls,
            "cache_hits": self.cache_hits,
        })

    def reserve(self) -> None:
        if self.attempts_total() >= self.max_calls:
            raise BudgetExceeded(
                "调用上限 %d 已达（含重试），按授权边界停下，不静默超支。" % self.max_calls)

    def append(self, row: dict) -> None:
        self.seq += 1
        row = dict(row)
        row["seq"] = self.seq
        self.calls.append(row)
        self.flush()

    def mark_cache_hit(self, row: dict) -> None:
        """缓存命中只是复用，不进 calls（不占预算、不计入调用次数）。"""
        self.cache_hits.append(dict(row))
        self.flush()


def _is_rate_limit(err_text: str, status) -> bool:
    return status == 429 or "rate" in (err_text or "").lower() or "限流" in (err_text or "")


def call_model(vendor: dict, system: str, user: str, cache_meta: dict, ledger: Ledger,
               max_calls: int) -> dict:
    """调一次 judge；结果（含每次尝试）写缓存。缓存命中直接返回，不再调用。"""
    path = cache_meta["path"]
    input_sha = cache_meta["input_sha256"]

    if os.path.exists(path):
        entry = read_json(path, None) or {}
        if entry.get("input_sha256") == input_sha and entry.get("ok"):
            ledger.mark_cache_hit({
                "timestamp": now_iso(), "judge": vendor["key"], "model": vendor["model"],
                "model_resolved": entry.get("model_resolved"),
                "answer_key": cache_meta["answer_key"], "qid": cache_meta["qid"],
                "group": cache_meta["group"], "dimension": cache_meta["dimension"],
                "status": "cache_hit", "note": "复用已有原始返回，不烧调用",
            })
            entry["_from_cache"] = True
            return entry

    from openai import OpenAI  # 延迟导入：零调用档（--selftest/--report）不依赖该包

    client = OpenAI(api_key=vendor["_key"], base_url=vendor["_base_url"], timeout=TIMEOUT_SECONDS)
    attempts = []
    temperature = float(vendor.get("temperature", TEMPERATURE_REQ))
    parsed = None
    last_text = ""
    resolved = None
    ok = False
    rate_limited = False
    max_tokens = MAX_TOKENS.get(vendor["key"], 2000)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if ledger.attempts_total() >= max_calls:
            raise BudgetExceeded("调用上限 %d 已达（含重试），按授权边界停下。" % max_calls)
        t0 = time.time()
        row = {"timestamp": now_iso(), "judge": vendor["key"], "model": vendor["model"],
               "answer_key": cache_meta["answer_key"], "qid": cache_meta["qid"],
               "group": cache_meta["group"], "dimension": cache_meta["dimension"],
               "attempt": attempt, "temperature": temperature, "max_tokens": max_tokens,
               "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
               "status": None, "error": None, "ok": False, "finish_reason": None,
               "latency_seconds": 0.0}
        try:
            resp = client.chat.completions.create(
                model=vendor["model"],
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user}],
            )
            dt = time.time() - t0
            choice = resp.choices[0]
            text = choice.message.content or ""
            u = getattr(resp, "usage", None)
            row["prompt_tokens"] = int(getattr(u, "prompt_tokens", 0) or 0)
            row["completion_tokens"] = int(getattr(u, "completion_tokens", 0) or 0)
            row["total_tokens"] = int(getattr(u, "total_tokens", 0) or 0)
            row["latency_seconds"] = round(dt, 3)
            row["finish_reason"] = choice.finish_reason
            row["status"] = "http_ok"
            resolved = getattr(resp, "model", None) or resolved
            row["model_resolved"] = resolved
            last_text = text
            parsed = extract_json(text)
            if parsed is None:
                parsed = extract_json_lenient(text)
                if parsed is not None:
                    row["json_recovered"] = True
            if parsed is None:
                row["error"] = "返回不是合法 JSON"
                row["raw_excerpt"] = text[:300]
                row["ok"] = False
            elif choice.finish_reason == "length":
                row["error"] = "被输出上限截断"
                row["raw_excerpt"] = text[:300]
                row["ok"] = False
            else:
                row["ok"] = True
                ok = True
        except Exception as exc:  # noqa: BLE001 —— 逐类判定在下方
            dt = time.time() - t0
            row["latency_seconds"] = round(dt, 3)
            msg = str(exc)
            status = getattr(exc, "status_code", None)
            row["status"] = "error"
            row["http_status"] = status
            row["error"] = msg[:400]
            # 端点拒收 temperature：换该家的回退值再试一次（记为一次带标记的重试）
            if status == 400 and "temperature" in msg.lower() and temperature != vendor.get("temperature_fallback"):
                row["note"] = "端点拒收 temperature=%s，按实测回退到 %s" % (temperature, vendor["temperature_fallback"])
                temperature = float(vendor["temperature_fallback"])
                row["ok"] = False
            if _is_rate_limit(msg, status):
                rate_limited = True
                row["rate_limited"] = True
            ok = False

        attempts.append(row)
        ledger.append(row)
        if row["ok"]:
            break
        if attempt < MAX_ATTEMPTS:
            if rate_limited:
                time.sleep(COOLDOWN_ON_RATE_LIMIT)   # 串行 + 冷却，不并发
            else:
                time.sleep(PACE_SECONDS * 2)
        else:
            break

    entry = {
        "cache_schema": CACHE_SCHEMA,
        "judge": vendor["key"],
        "model_requested": vendor["model"],
        "model_resolved": resolved,
        "temperature_used": temperature,
        "temperature_requested": TEMPERATURE_REQ,
        "max_tokens": max_tokens,
        "prompt_version": PROMPT_VERSION,
        "input_sha256": input_sha,
        "answer_key": cache_meta["answer_key"],
        "qid": cache_meta["qid"],
        "group": cache_meta["group"],
        "dimension": cache_meta["dimension"],
        "attempts": attempts,
        "ok": ok,
        "parsed": parsed,
        "raw_text": last_text,
        "finished_at": now_iso(),
    }
    if ok:
        write_json(path, entry)
    entry["_from_cache"] = False
    time.sleep(PACE_SECONDS)
    return entry


def extract_json(text: str):
    """从返回正文里取出第一个 JSON 对象；失败返回 None。"""
    if not text:
        return None
    fence = re.compile(r"```(?:json)?\s*(.*?)```", re.S)
    m = fence.search(text)
    if m:
        text = m.group(1)
    s = text.find("{")
    while s != -1:
        e = text.rfind("}")
        while e > s:
            try:
                obj = json.loads(text[s:e + 1])
                if isinstance(obj, dict):
                    return obj
            except Exception:  # noqa: BLE001
                pass
            e = text.rfind("}", s, e)
        s = text.find("{", s + 1)
    return None


# 兜底解析（**窄口径**）：judge 偶尔会漏掉 reason 值的开引号，例如
#   {"score": 2, "reason": 答案与参考答案完全一致。"}
# —— 整串不是合法 JSON，但 `"score": 2` 是**模型明确给出**的分值，直接丢弃等于把模型已经给出的判断
# 当成失败。这里只在**严格解析失败之后**尝试，且要求同时命中「唯一的 score 值」与「非空 reason」，
# 不做任何推断、不给默认分；解析成功时在记录里打 `json_recovered=true` 留痕。
_SCORE_RE = re.compile(r'"(?:final_)?score"\s*:\s*([012])\s*(?=[,}\]])')
_REASON_RE = re.compile(r'"reason"\s*:\s*"?([^"}\n]{2,300})')


def extract_json_lenient(text: str):
    if not text:
        return None
    hits = _SCORE_RE.findall(text)
    if len(hits) != 1:
        return None
    m = _REASON_RE.search(text)
    if not m:
        return None
    reason = m.group(1).strip().strip('。').strip()
    if len(reason) < 4:
        return None
    return {"score": int(hits[0]), "reason": reason, "_recovered_from_malformed_json": True}


# ---------------------------------------------------------------------------
# 5. 单条评分（一条答案 × 三个维度 = 三次调用）
# ---------------------------------------------------------------------------
REFUSAL_MARKS = ("无法评分", "不能评分", "抱歉", "无法完成", "无法判断", "拒绝", "我不能")
# 拒答识别要**窄**：只看理由**开头**是不是判定方自己不肯打分（第一人称拒答）。
# 反面教材（2026-10-07 实测一次误判）：理由「被评答案拒绝作答，未给出参考答案中…，判错误」——
# 分值是合法 0 分，「拒绝」是在描述**被评答案**，不是在说判定方拒答；按旧的全串匹配会被误判成拒答并丢掉这个 0 分。
_REFUSAL_RE = re.compile(
    r"^\s*(?:很?抱歉|我无法|我不能|我不会|无法评分|不能评分|无法完成评分|无法给出评分|拒绝评分)")


def _looks_like_refusal(reason: str) -> bool:
    return bool(_REFUSAL_RE.match(reason or ""))


def normalize_score(parsed) -> tuple:
    """把 judge 返回归一成 (score|None, reason, problem)。"""
    if not isinstance(parsed, dict):
        return None, "", "返回不是对象"
    raw = parsed.get("score")
    reason = str(parsed.get("reason") or "").strip()
    score = None
    if isinstance(raw, bool):
        score = int(raw)
    elif isinstance(raw, int):
        score = raw
    elif isinstance(raw, float) and raw == int(raw):
        score = int(raw)
    elif isinstance(raw, str) and raw.strip() in ("0", "1", "2"):
        score = int(raw.strip())
    problems = []
    if score is None or score not in (0, 1, 2):
        problems.append("分值不在 {0,1,2}")
    if not reason:
        problems.append("reason 为空")
    elif len(reason) < 4:
        problems.append("reason 过短")
    elif _looks_like_refusal(reason):
        problems.append("疑似拒答")
    return score, reason, "；".join(problems)


def normalize_adjudication(parsed) -> tuple:
    """把复核返回（final_score）归一成 (score|None, reason, problem)。"""
    if not isinstance(parsed, dict):
        return None, "", "返回不是对象"
    flat = dict(parsed)
    if "final_score" in flat and "score" not in flat:
        flat["score"] = flat.get("final_score")
    return normalize_score(flat)


def adjudication_cache_path(judge: str, answer_key: str, dim_key: str) -> str:
    return os.path.join(CACHE_DIR, judge, PROMPT_VERSION_ADJ, "%s__%s.json" % (answer_key, dim_key))


def run_adjudication(max_calls: int) -> int:
    """《02》第12.7节（2026-10-04 口径变更段）：跨模型核对**不一致**的样本由副 judge 复核证据后给出最终分。

    只对已有两家评分的 30 条交叉核对样本执行；两家一致的维度**不调用**（那一半没有争议）。
    """
    questions = load_questions()
    items = select_cross(load_all_answers(questions))
    kimi_map = {r["answer_key"]: r for r in build_records_from_cache("kimi", items)}
    zhipu_map = {r["answer_key"]: r for r in build_records_from_cache("zhipu", items)}
    local = read_local_config()
    judge_cfg = (load_judge_cfg().get("judges") or {}).get("zhipu") or {}
    v = resolve_vendor(VENDORS["zhipu"], local, judge_cfg.get("temperature_used"))
    if not (v["has_key"] and v["has_base"]):
        raise RuntimeError("副 judge 凭据／端点缺失")
    ledger = Ledger(LEDGER_PATH, max_calls)

    todo = []
    for it in items:
        ra, rz = kimi_map.get(it["answer_key"]), zhipu_map.get(it["answer_key"])
        for dim in DIMENSIONS:
            k = dim[0]
            a = (ra or {}).get("scores", {}).get(k)
            b = (rz or {}).get("scores", {}).get(k)
            if a is None or b is None or a == b:
                continue
            todo.append((it, dim, a, (ra or {}).get("reasons", {}).get(k, ""),
                         b, (rz or {}).get("reasons", {}).get(k, "")))
    log("== 不一致复核（副 judge）：需复核 %d 格（%d 条 × 3 维中两家分歧的那些）==" % (len(todo), len(items)))
    if not todo:
        log("   两家在全部交叉核对样本上逐维一致，无需复核。")
        ledger.flush()
        return 0
    for n, (it, dim, a, ar, b, br) in enumerate(todo, 1):
        user = build_adjudication_prompt(it, dim, load_chunks_cached(), a, ar, b, br)
        meta = {"path": adjudication_cache_path("zhipu", it["answer_key"], dim[0]),
                "answer_key": it["answer_key"], "qid": it["qid"], "group": it["group"],
                "dimension": dim[0],
                "input_sha256": sha256_text(ADJ_SYSTEM_PROMPT + "\x00" + user + "\x00" + PROMPT_VERSION_ADJ)}
        entry = call_model(v, ADJ_SYSTEM_PROMPT, user, meta, ledger, max_calls)
        score, reason, problem = normalize_adjudication(entry.get("parsed"))
        log("   %d／%d %s %s：主 %s / 副 %s → 最终 %s（%s）"
            % (n, len(todo), it["answer_key"], dim[0], a, b,
               score if score is not None else "失败", (reason or problem or "")[:36]))
    ledger.flush()
    return 0


def score_answer(vendor: dict, item: dict, chunks: dict, ledger: Ledger, max_calls: int,
                 dims=DIMENSIONS) -> dict:
    q = {"question": item["question"], "reference_answer": item["reference_answer"],
         "gold_evidence_chunk_ids": item["gold_evidence_chunk_ids"]}
    rec = {
        "schema": RECORD_SCHEMA,
        "answer_key": item["answer_key"],
        "answer_id": item["answer_id"],
        "question_id": item["question_id"],
        "qid": item["qid"],
        "group": item["group"],
        "judge_vendor": vendor["key"],
        "judge_model": vendor["model"],
        "prompt_version": PROMPT_VERSION,
        "scale_source": SCALE_SOURCE,
        "scores": {}, "reasons": {}, "tokens": {}, "latency_seconds": {}, "judge_failed": [],
        "temperature": None, "model_resolved": None,
        "answer_chars": len(item["answer_text"] or ""),
        "evidence_count": len(item["evidence"]),
    }
    tok_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    lat_total = 0.0
    for dim in dims:
        dim_key = dim[0]
        user = build_user_prompt(item, dim, chunks)
        cache_path = os.path.join(CACHE_DIR, vendor["key"], PROMPT_VERSION,
                                  "%s__%s.json" % (item["answer_key"], dim_key))
        meta = {"path": cache_path, "answer_key": item["answer_key"], "qid": item["qid"],
                "group": item["group"], "dimension": dim_key,
                "input_sha256": sha256_text(SYSTEM_PROMPT + "\x00" + user + "\x00" + PROMPT_VERSION)}
        entry = call_model(vendor, SYSTEM_PROMPT, user, meta, ledger, max_calls)
        rec["temperature"] = entry.get("temperature_used")
        rec["model_resolved"] = entry.get("model_resolved") or rec["model_resolved"]
        score, reason, problem = normalize_score(entry.get("parsed"))
        toks = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        lat = 0.0
        for a in entry.get("attempts") or []:
            for k in toks:
                toks[k] += int(a.get(k) or 0)
            lat += float(a.get("latency_seconds") or 0.0)
        if not entry.get("ok") or problem:
            rec["judge_failed"].append({
                "dimension": dim_key, "attempts": len(entry.get("attempts") or []),
                "problem": problem or (entry.get("attempts") or [{}])[-1].get("error") or "调用失败",
            })
            rec["scores"][dim_key] = None
            rec["reasons"][dim_key] = reason
        else:
            rec["scores"][dim_key] = score
            rec["reasons"][dim_key] = reason
        rec["tokens"][dim_key] = toks
        rec["latency_seconds"][dim_key] = round(lat, 3)
        for k in tok_total:
            tok_total[k] += toks[k]
        lat_total += lat
    rec["tokens"]["total"] = tok_total
    rec["latency_seconds"]["total"] = round(lat_total, 3)
    done = sum(1 for d in rec["scores"].values() if d is not None)
    rec["status"] = "ok" if done == len(dims) else ("judge_failed" if done == 0 else "partial")
    return rec


# ---------------------------------------------------------------------------
# 6. 档位：probe / selftest / smoke / run / report
# ---------------------------------------------------------------------------
def persist_vendor_identity(vendor: dict, entry: dict) -> None:
    cfg = load_judge_cfg()
    cfg.setdefault("prompt_version", PROMPT_VERSION)
    cfg.setdefault("temperature_requested", TEMPERATURE_REQ)
    per = cfg.setdefault("judges", {})
    per[vendor["key"]] = {
        "label": vendor["label"],
        "model_requested": vendor["model"],
        "model_resolved": entry.get("model_resolved"),
        "temperature_used": entry.get("temperature_used"),
        "key_source": vendor["key_source"],
        "base_source": vendor["base_source"],
        "has_key": vendor["has_key"],
        "model_source": vendor["model_source"],
        "checked_at": now_iso(),
        "note": "此处只登记 key 的**来源标签**，不含凭据取值。",
    }
    save_judge_cfg(cfg)


def probe(only=None, max_calls=MAX_CALLS_DEFAULT) -> int:
    """各发一次最小请求，确认 model id 可用并登记实测解析到的 id 与可用 temperature。"""
    local = read_local_config()
    ledger = Ledger(LEDGER_PATH, max_calls)
    rc = 0
    for key in (only or ("kimi", "zhipu")):
        judge_cfg = (load_judge_cfg().get("judges") or {}).get(key) or {}
        temp_override = judge_cfg.get("temperature_used")
        v = resolve_vendor(VENDORS[key], local, temp_override)
        log("── probe %s：model=%s key=%s base=%s temperature=%s"
            % (v["label"], v["model"], v["key_source"], v["base_source"], v["temperature"]))
        if not (v["has_key"] and v["has_base"]):
            log("   [FAIL] 凭据或端点缺失，跳过")
            rc = 1
            continue
        user = '只输出如下 JSON：{"score": 1, "reason": "连通性自检"}'
        meta = {"path": os.path.join(CACHE_DIR, v["key"], PROMPT_VERSION, "_probe.json"),
                "answer_key": "_probe", "qid": "_probe", "group": "_probe", "dimension": "_probe",
                "input_sha256": sha256_text("PROBE\x00" + v["model"] + "\x00" + PROMPT_VERSION)}
        try:
            entry = call_model(v, "你是连通性自检，只输出 JSON。", user, meta, ledger, max_calls)
        except BudgetExceeded as exc:
            log("   [FAIL] %s" % exc)
            return 1
        ok = bool(entry.get("ok"))
        log("   model_resolved=%s temperature_used=%s ok=%s"
            % (entry.get("model_resolved"), entry.get("temperature_used"), ok))
        persist_vendor_identity(v, entry)
        if not ok:
            log("   [FAIL] 最后一次尝试：%s" % ((entry.get("attempts") or [{}])[-1].get("error")))
            rc = 1
    ledger.flush()
    log("probe 完成；台账累计尝试 %d 次" % ledger.attempts_total())
    return rc


def selftest(max_calls=MAX_CALLS_DEFAULT) -> int:
    """零调用自检：装配 150 条输入，检查字段完整性与 prompt 可构建。"""
    questions = load_questions()
    chunks = load_chunks()
    items = load_all_answers(questions)
    log("装配：题集 %d 题、文本块 %d 块、答案 %d 条" % (len(questions), len(chunks), len(items)))
    bad = []
    empty = 0
    for it in items:
        if not it["question"]:
            bad.append("%s 缺题干" % it["answer_key"])
        if not it["reference_answer"]:
            bad.append("%s 缺参考答案" % it["answer_key"])
        if not it["answer_text"].strip():
            empty += 1
        missing = [e.get("chunk_id") for e in it["evidence"] if int(e.get("chunk_id") or -1) not in chunks]
        if missing:
            bad.append("%s 证据块不在 chunks.jsonl：%s" % (it["answer_key"], missing[:3]))
        for dim in DIMENSIONS:
            p = build_user_prompt(it, dim, chunks)
            if len(p) < 200:
                bad.append("%s/%s prompt 过短" % (it["answer_key"], dim[0]))
    for g in GROUPS:
        n = sum(1 for it in items if it["group"] == g)
        if PER_GROUP_EXPECTED is not None and n != PER_GROUP_EXPECTED:
            bad.append("%s 组答案数 %d ≠ %d" % (g, n, PER_GROUP_EXPECTED))
    smoke = select_smoke(items)
    cross = select_cross(items)
    if DATASET == "pr":
        cross_desc = "%d 题 × 5 组" % len(CROSS_CHECK_QIDS)
    else:
        cross_desc = "每组 ⌈20%%⌉ 系统抽样：%s" % "／".join(
            "%s %d" % (g, sum(1 for it in cross if it["group"] == g)) for g in GROUPS)
    log("空正文 %d 条；冒烟样本 %d 条；交叉核对样本 %d 条（%s）"
        % (empty, len(smoke), len(cross), cross_desc))
    if bad:
        log("自检 FAIL %d 项：" % len(bad))
        for b in bad[:20]:
            log("  · %s" % b)
        return 1
    log("自检 OK：%d 条输入齐备、三档 prompt 均可构建" % len(items))
    return 0


def select_items(items: list, qids) -> list:
    want = set(qids)
    return [it for it in items if it["qid"] in want]


def select_smoke(items: list) -> list:
    """冒烟样本。

    pr     ＝ 2 题（SMOKE_QIDS）× 5 组 ＝ 10 条（改造前口径，不变）；
    formal ＝ **每组各 2 条**，且**跨层取**：先取该组内第一道「关系型 ＋ ≥2 跳」
             （图谱扩展 ＋ 证据上下文最重的一档，也是 judge 出格式错的高发档），
             再取第一道「事实型 ＋ 0 跳」（最轻的一档）——既满足「A～E 各 2 条」，
             又让冒烟真的压到最重的那一档，而不是 10 条都落在最容易的一格。
    """
    mode, arg = SMOKE_MODE
    if mode == "qids":
        return select_items(items, arg)
    # 分层档的判据要用题目侧的 `task_type` 与 `gold_hop_depth`。**评分记录不带这两项**
    # （它们在 `load_group()` 装配的条目上），故此处按 `answer_key` 就近补齐；补不到就
    # 退回「该组按 qid 升序取前 arg 条」。纯本地装配、零调用——报告档不应因为抽样元数据
    # 缺失而崩，也不应因此改变 pr 档的任何取值。
    if any(it.get("task_type") is None or it.get("gold_hop_depth") is None for it in items):
        meta = {}
        try:
            meta = {x["answer_key"]: x for x in load_all_answers(load_questions())}
        except Exception:                                        # noqa: BLE001
            meta = {}
        fixed = []
        for it in items:
            if it.get("task_type") is None or it.get("gold_hop_depth") is None:
                m = meta.get(it.get("answer_key"))
                if m:
                    d = dict(it)
                    if d.get("task_type") is None:
                        d["task_type"] = m.get("task_type")
                    if d.get("gold_hop_depth") is None:
                        d["gold_hop_depth"] = m.get("gold_hop_depth")
                    fixed.append(d)
                    continue
            fixed.append(it)
        items = fixed
    out = []
    for g in GROUPS:
        rows = sorted([it for it in items if it["group"] == g], key=lambda x: x["qid"])
        picked = []
        preds = (lambda it: it.get("task_type") == "关系型" and int(it.get("gold_hop_depth") or 0) >= 2,
                 lambda it: it.get("task_type") == "事实型" and int(it.get("gold_hop_depth") or 0) == 0)
        for pred in preds:
            hit = next((it for it in rows if pred(it) and it not in picked), None)
            if hit is not None:
                picked.append(hit)
        if len(picked) < int(arg):          # 兜底：该组缺档时按 qid 升序补齐
            for it in rows:
                if it not in picked:
                    picked.append(it)
                if len(picked) >= int(arg):
                    break
        out.extend(picked[:int(arg)])
    return out


def select_cross(items: list) -> list:
    """副 judge 交叉核对样本（《02》第12.7节：副 judge 对 **≥20%** 的样本做跨模型交叉核对）。

    pr     ＝ 6 题（CROSS_CHECK_QIDS）× 5 组 ＝ 30 条（＝150 条的 20%，改造前口径，不变）；
    formal ＝ 每组内按 qid 升序做**系统抽样**（每 5 条取 1 条、自组内第 1 条起），
             取到该组答案数的 ⌈20%⌉ —— 确定性、可复算，且**每组都不低于 20%**。
    """
    mode, arg = CROSS_MODE
    if mode == "qids":
        return select_items(items, arg)
    out = []
    for g in GROUPS:
        rows = sorted([it for it in items if it["group"] == g], key=lambda x: x["qid"])
        if not rows:
            continue
        want = int(math.ceil(len(rows) * float(arg)))
        picked = rows[::5]
        if len(picked) < want:      # 兜底：系统抽样的步长不足时按 qid 升序补齐（不改抽样口径）
            rest = [r for r in rows if r not in picked]
            picked = picked + rest[:want - len(picked)]
        out.extend(picked[:want])
    return out


def run_judge(judge: str, items: list, max_calls: int, label: str) -> list:
    local = read_local_config()
    judge_cfg = (load_judge_cfg().get("judges") or {}).get(judge) or {}
    v = resolve_vendor(VENDORS[judge], local, judge_cfg.get("temperature_used"))
    if not (v["has_key"] and v["has_base"]):
        raise RuntimeError("%s 凭据／端点缺失" % v["label"])
    ledger = Ledger(LEDGER_PATH, max_calls)
    log("== %s：%s 条答案 × %d 维度 ＝ 最多 %d 次调用（缓存命中不烧调用）=="
        % (label, len(items), len(DIMENSIONS), len(items) * len(DIMENSIONS)))
    log("   model=%s temperature=%s key=%s" % (v["model"], v["temperature"], v["key_source"]))
    out = []
    done = calls = 0
    before = ledger.attempts_total()
    for it in items:
        rec = score_answer(v, it, load_chunks_cached(), ledger, max_calls)
        out.append(rec)
        done += 1
        if done % 10 == 0 or done == len(items):
            used = ledger.attempts_total() - before
            log("   进度 %d／%d（本轮已发尝试 %d 次，累计台账 %d 次）%s"
                % (done, len(items), used, ledger.attempts_total(),
                   "" if rec["status"] == "ok" else "  末条状态=%s" % rec["status"]))
    ledger.flush()
    return out


_CHUNK_CACHE = {}


def load_chunks_cached() -> dict:
    if not _CHUNK_CACHE:
        _CHUNK_CACHE.update(load_chunks())
    return _CHUNK_CACHE


def smoke(max_calls: int) -> int:
    """冒烟 10 条（2 题 × 5 组）× 3 维：查 JSON 可解析、分值 ∈ {0,1,2}、reason 非空、无拒答。"""
    questions = load_questions()
    items = select_smoke(load_all_answers(questions))
    recs = run_judge("kimi", items, max_calls, "冒烟（主 judge kimi）")
    write_jsonl(os.path.join(OUT_DIR, "_冒烟记录.jsonl"), recs)
    bad = []
    rows = []
    for rec in recs:
        for dim_key, _lbl, _s, _f in DIMENSIONS:
            s = rec["scores"].get(dim_key)
            r = (rec["reasons"].get(dim_key) or "").strip()
            if s not in (0, 1, 2):
                bad.append("%s/%s 分值=%r" % (rec["answer_key"], dim_key, s))
            if not r:
                bad.append("%s/%s reason 为空" % (rec["answer_key"], dim_key))
            rows.append((rec["answer_key"], rec["qid"], dim_key, s, r[:40]))
    log("── 冒烟读数（%d 条 × 3 维）──" % len(recs))
    for ab, qid, dim_key, s, r in rows:
        log("   %-10s %-6s %-16s score=%s  %s" % (ab, qid, dim_key, s, r))
    n_ok = sum(1 for rec in recs if rec["status"] == "ok")
    log("冒烟结果：%d／%d 条三维齐全；异常 %d 项" % (n_ok, len(recs), len(bad)))
    for b in bad[:10]:
        log("   · %s" % b)
    return 1 if bad else 0


# ---------------------------------------------------------------------------
# 7. 汇总：五组 × 三维度、三子集、跨模型一致率、调用账
# ---------------------------------------------------------------------------
DIM_KEYS = [d[0] for d in DIMENSIONS]
DIM_LABEL = {d[0]: d[1] for d in DIMENSIONS}


def mean_of(rows, dim_key):
    vals = [r["scores"].get(dim_key) for r in rows if r["scores"].get(dim_key) is not None]
    if not vals:
        return None, 0, {}
    dist = {str(i): sum(1 for v in vals if v == i) for i in (0, 1, 2)}
    return round(sum(vals) / len(vals), 4), len(vals), dist


def summarize_group(rows, dim_key):
    m, n, dist = mean_of(rows, dim_key)
    return {"mean": m, "n_scored": n, "distribution_0_1_2": [dist.get("0", 0), dist.get("1", 0), dist.get("2", 0)]}


def linear_weighted_kappa(pairs):
    """线性加权 kappa（0／1／2 视作序数尺度）；pairs = [(a, b), ...]。"""
    pairs = [(int(a), int(b)) for a, b in pairs]
    if not pairs:
        return None
    n = len(pairs)
    obs = [[0] * 3 for _ in range(3)]
    for a, b in pairs:
        obs[a][b] += 1
    row = [sum(obs[i]) / n for i in range(3)]
    col = [sum(obs[i][j] for i in range(3)) / n for j in range(3)]
    num = den = 0.0
    for i in range(3):
        for j in range(3):
            w = 1.0 - abs(i - j) / 2.0
            num += w * (obs[i][j] / n)
            den += w * (row[i] * col[j])
    if den == 0 or den >= 1.0 - 1e-12:
        # 期望不一致度＝0（两家的边际分布完全相同且退化，例如全部判 2 分）时 kappa 在数学上无定义，
        # 返回 None 并在报告里写明「无定义」，**不得**用 1.0 假装算出来了。
        return None
    return round((num - den) / (1.0 - den), 4)


def agreement(kimi_recs, zhipu_recs):
    by_key_a = {r["answer_key"]: r for r in kimi_recs}
    pairs_all = {k: [] for k in DIM_KEYS}
    per_group = {g: {k: [] for k in DIM_KEYS} for g in GROUPS}
    n_used = 0
    for rz in zhipu_recs:
        ra = by_key_a.get(rz["answer_key"])
        if not ra:
            continue
        used = False
        for k in DIM_KEYS:
            a, b = ra["scores"].get(k), rz["scores"].get(k)
            if a is None or b is None:
                continue
            pairs_all[k].append((a, b))
            per_group[rz["group"]][k].append((a, b))
            used = True
        if used:
            n_used += 1
    out = {"n_answers_compared": n_used, "per_dimension": {}, "per_group": {}}
    for k in DIM_KEYS:
        ps = pairs_all[k]
        agree = sum(1 for a, b in ps if a == b)
        exact2 = sum(1 for a, b in ps if a == b == 2)
        out["per_dimension"][k] = {
            "n": len(ps),
            "simple_agreement": round(agree / len(ps), 4) if ps else None,
            "linear_weighted_kappa": linear_weighted_kappa(ps),
            "mean_abs_diff": round(sum(abs(a - b) for a, b in ps) / len(ps), 4) if ps else None,
            "both_full_marks": exact2,
            "both_full_marks_rate": round(exact2 / len(ps), 4) if ps else None,
        }
    for g in GROUPS:
        out["per_group"][g] = {}
        for k in DIM_KEYS:
            ps = per_group[g][k]
            agree = sum(1 for a, b in ps if a == b)
            out["per_group"][g][k] = {
                "n": len(ps),
                "simple_agreement": round(agree / len(ps), 4) if ps else None,
                "linear_weighted_kappa": linear_weighted_kappa(ps),
            }
    return out


def build_records_from_cache(judge: str, items: list) -> list:
    """零调用：从原始返回重建逐条评分记录（重跑安全）。"""
    chunks = load_chunks_cached()
    out = []
    for it in items:
        rec = {
            "schema": RECORD_SCHEMA, "answer_key": it["answer_key"], "answer_id": it["answer_id"],
            "question_id": it["question_id"], "qid": it["qid"], "group": it["group"],
            "judge_vendor": judge, "judge_model": VENDORS[judge]["model"],
            "prompt_version": PROMPT_VERSION, "scale_source": SCALE_SOURCE,
            "scores": {}, "reasons": {}, "tokens": {}, "latency_seconds": {}, "judge_failed": [],
            "temperature": None, "model_resolved": None,
            "answer_chars": len(it["answer_text"] or ""), "evidence_count": len(it["evidence"]),
        }
        tok_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        lat_total = 0.0
        for dim in DIMENSIONS:
            dim_key = dim[0]
            path = os.path.join(CACHE_DIR, judge, PROMPT_VERSION,
                                "%s__%s.json" % (it["answer_key"], dim_key))
            entry = read_json(path, None)
            toks = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            lat = 0.0
            if entry:
                rec["temperature"] = entry.get("temperature_used")
                rec["model_resolved"] = entry.get("model_resolved") or rec["model_resolved"]
                for a in entry.get("attempts") or []:
                    for k in toks:
                        toks[k] += int(a.get(k) or 0)
                    lat += float(a.get("latency_seconds") or 0.0)
                score, reason, problem = normalize_score(entry.get("parsed"))
                if entry.get("ok") and not problem:
                    rec["scores"][dim_key] = score
                    rec["reasons"][dim_key] = reason
                else:
                    rec["scores"][dim_key] = None
                    rec["reasons"][dim_key] = reason
                    rec["judge_failed"].append({
                        "dimension": dim_key, "attempts": len(entry.get("attempts") or []),
                        "problem": problem or "调用失败",
                    })
            else:
                rec["scores"][dim_key] = None
                rec["reasons"][dim_key] = ""
                rec["judge_failed"].append({"dimension": dim_key, "attempts": 0, "problem": "未运行（无缓存）"})
            rec["tokens"][dim_key] = toks
            rec["latency_seconds"][dim_key] = round(lat, 3)
            for k in tok_total:
                tok_total[k] += toks[k]
            lat_total += lat
        rec["tokens"]["total"] = tok_total
        rec["latency_seconds"]["total"] = round(lat_total, 3)
        done = sum(1 for d in rec["scores"].values() if d is not None)
        rec["status"] = "ok" if done == len(DIMENSIONS) else ("judge_failed" if done == 0 else "partial")
        out.append(rec)
    return out


def build_report(max_calls: int) -> int:
    questions = load_questions()
    items = load_all_answers(questions)
    kimi_items = items
    # 副 judge 要读的样本**必须与发调用时用的同一套选择逻辑**（`select_cross` 按 CROSS_MODE 分档：
    # pr ＝ 6 题 × 5 组，formal ＝ 每组按 qid 升序系统抽样 ⌈20%⌉）。原先此处写死
    # `select_items(items, CROSS_CHECK_QIDS)`——那是**预实验集**的题号清单，正式档拿它会选出空集，
    # 于是 `评分记录.jsonl` 只剩主 judge 的 582 条、交叉核对与跨模型一致率全部落空。
    zhipu_items = select_cross(items)

    kimi_recs = build_records_from_cache("kimi", kimi_items)
    zhipu_recs = build_records_from_cache("zhipu", zhipu_items)
    judge_cfg = load_judge_cfg()

    # 不一致复核（《02》第12.7节 2026-10-04 口径变更段）：把两次评分、是否一致、最终分与不一致原因
    # 一并挂到副 judge 的记录上；两家一致的维度最终分就是该分（不额外调用）。
    kimi_map = {r["answer_key"]: r for r in kimi_recs}
    adj_summary = {"n_answers_cross_checked": len(zhipu_recs), "n_cells": 0, "n_agree": 0,
                   "n_disagree": 0, "n_adjudicated": 0, "n_adjudication_failed": 0,
                   "by_dimension": {k: {"n": 0, "agree": 0, "disagree": 0, "adjudicated": 0}
                                    for k in DIM_KEYS},
                   "disagreement_notes": []}
    for rz in zhipu_recs:
        ra = kimi_map.get(rz["answer_key"]) or {"scores": {}, "reasons": {}}
        adj = {}
        for k in DIM_KEYS:
            a, b = ra["scores"].get(k), rz["scores"].get(k)
            cell = {"kimi_score": a, "zhipu_score": b, "kimi_reason": ra["reasons"].get(k, ""),
                    "zhipu_reason": rz["reasons"].get(k, ""), "agree": None,
                    "final_score": None, "final_source": "未比对（缺一方分值）",
                    "disagreement_note": ""}
            if a is not None and b is not None:
                adj_summary["n_cells"] += 1
                adj_summary["by_dimension"][k]["n"] += 1
                cell["agree"] = (a == b)
                if a == b:
                    adj_summary["n_agree"] += 1
                    adj_summary["by_dimension"][k]["agree"] += 1
                    cell["final_score"] = a
                    cell["final_source"] = "两家一致"
                else:
                    adj_summary["n_disagree"] += 1
                    adj_summary["by_dimension"][k]["disagree"] += 1
                    entry = read_json(adjudication_cache_path("zhipu", rz["answer_key"], k), None) or {}
                    sc, rs, pb = normalize_adjudication(entry.get("parsed"))
                    if entry.get("ok") and sc is not None and not pb:
                        adj_summary["n_adjudicated"] += 1
                        adj_summary["by_dimension"][k]["adjudicated"] += 1
                        cell["final_score"] = sc
                        cell["final_source"] = "副 judge 复核证据后给出最终分"
                        cell["final_reason"] = rs
                        cell["disagreement_note"] = str((entry.get("parsed") or {}).get("disagreement_note") or "")
                    else:
                        adj_summary["n_adjudication_failed"] += 1
                        cell["final_source"] = "复核未完成（如实登记，不补分）"
                    adj_summary["disagreement_notes"].append({
                        "answer_key": rz["answer_key"], "qid": rz["qid"], "group": rz["group"],
                        "dimension": k, "kimi_score": a, "zhipu_score": b,
                        "final_score": cell["final_score"], "note": cell["disagreement_note"],
                    })
            else:
                cell["final_score"] = a if a is not None else b
                cell["final_source"] = "仅一方有分" if cell["final_score"] is not None else "无分"
            adj[k] = cell
        rz["adjudication"] = adj

    # 终值口径：未做交叉核对的 120 条＝主 judge 的分；做了的 30 条＝该维最终分（一致即同分，不一致取复核分）
    adj_by_key = {r["answer_key"]: r.get("adjudication") or {} for r in zhipu_recs}
    final_recs = []
    for r in kimi_recs:
        f = dict(r)
        adj = adj_by_key.get(r["answer_key"])
        if adj:
            f["scores"] = {k: (adj.get(k, {}) or {}).get("final_score") for k in DIM_KEYS}
            f["final_score_source"] = "交叉核对样本：一致取同分／不一致取副 judge 复核分"
        else:
            f["final_score_source"] = "主 judge 分（未做交叉核对）"
        final_recs.append(f)
    adj_summary["final_scores_by_group"] = {
        g: {k: summarize_group([f for f in final_recs if f["group"] == g], k) for k in DIM_KEYS}
        for g in GROUPS
    }

    # 逐条记录落盘：主 judge 全量 + 副 judge 子集（副 judge 记录带 judge_vendor 区分）
    all_recs = kimi_recs + zhipu_recs
    write_jsonl(RECORDS_PATH, all_recs)
    write_jsonl(os.path.join(OUT_DIR, "_冒烟记录.jsonl"), select_smoke(kimi_recs))

    ledger = Ledger(LEDGER_PATH, max_calls)
    totals = ledger._totals()   # 只读：报告档**不写**台账（台账由发调用的进程独占写，避免并发覆盖）

    # 五组 × 三维度
    by_group = OrderedDict()
    for g in GROUPS:
        rows = [r for r in kimi_recs if r["group"] == g]
        by_group[g] = {
            "label": GROUP_LABEL[g],
            "n_answers": len(rows),
            "n_scored_full": sum(1 for r in rows if r["status"] == "ok"),
            "dimensions": {k: summarize_group(rows, k) for k in DIM_KEYS},
        }

    # 三子集 × 五组 × 三维度
    qmeta = {it["qid"]: it for it in items}
    subsets = []
    for name, pred in SUBSETS:
        qids = [qid for qid, q in questions.items() if pred(q)]
        per_group = OrderedDict()
        for g in GROUPS:
            rows = [r for r in kimi_recs if r["group"] == g and r["qid"] in qids]
            per_group[g] = {"n_questions": len({r["qid"] for r in rows}),
                            "dimensions": {k: summarize_group(rows, k) for k in DIM_KEYS}}
        subsets.append({"name": name, "qids": sorted(qids), "per_group": per_group})

    # 《02》第12.8节 判定的机检口径（Method ＝ C 组 vs Baseline 2 ＝ A 组）
    # ① Complete Evidence Recall@K（检索侧读数）**直接取既有对照产物的读数，不重算、不改**：
    #    pr 档取 `subsets`；formal 档取 `subsets_named_core`（＝核心集 108 题内按
    #    关系型／多跳型／时序型分组的既有读数，对应 `A_vs_C_对照报告.md` 第 4.1 节）。
    # ② Answer Accuracy（模型评分口径）由本次评分给出；formal 档按第12.8节 明文
    #    「该判定以核心测试集的 108 题为依据，压力测试子集仅作为附加观察」限定在核心集内。
    ac = read_json(AC_COMPARE_PATH, {}) or {}
    if CER_SOURCE == "subsets":
        ac_subsets = {s["name"]: s["per_group"] for s in (ac.get("subsets") or [])}
    else:
        ac_subsets = ac.get("subsets_named_core") or {}
    aa_scope_qids = None
    if CORE_ONLY_128:
        aa_scope_qids = {qid for qid, q in questions.items() if (q.get("subset") or "") == "核心"}
    judge_128 = []
    for s in subsets:
        name = s["name"]
        subset_qids = set(s["qids"])
        per_aa, per_n = {}, {}
        for g in GROUPS:
            rows = [r for r in kimi_recs if r["group"] == g and r["qid"] in subset_qids]
            if aa_scope_qids is not None:
                rows = [r for r in rows if r["qid"] in aa_scope_qids]
            per_aa[g] = summarize_group(rows, "answer_accuracy")
            per_n[g] = len({r["qid"] for r in rows})
        aa = per_aa
        cer = {g: ((ac_subsets.get(name) or {}).get(g) or {}).get("complete_evidence_recall_at_k")
               for g in ("A", "C")}
        cer_a, cer_c = cer.get("A"), cer.get("C")
        cer_half = (cer_c is not None and cer_a is not None and cer_c > cer_a)
        aa_c, aa_a = aa["C"]["mean"], aa["A"]["mean"]
        if aa_c is None or aa_a is None:
            aa_half = None
            aa_verdict = "无法判定（存在未评到分的条目）"
        else:
            aa_half = aa_c >= aa_a
            aa_verdict = "不下降成立（持平）" if aa_c == aa_a else ("不下降成立（提升 %+.4f）" % (aa_c - aa_a)
                                                              if aa_c > aa_a else "不下降不成立（下降 %.4f）" % (aa_c - aa_a))
        row = {
            "subset": name,
            "n_questions": s["per_group"]["A"]["n_questions"] if aa_scope_qids is None
                           else len(subset_qids & aa_scope_qids),
            "cer_A": cer_a, "cer_C": cer_c, "cer_half_holds": cer_half,
            "answer_accuracy_A": aa_a, "answer_accuracy_C": aa_c,
            "answer_accuracy_gap_C_minus_A": None if (aa_a is None or aa_c is None) else round(aa_c - aa_a, 4),
            "answer_accuracy_half_holds": aa_half, "answer_accuracy_verdict": aa_verdict,
            "combined_holds": bool(cer_half and aa_half) if aa_half is not None else False,
        }
        if aa_scope_qids is not None:
            # 只在非 pr 档写入（保持预实验集那份 `评分汇总.json` 的键集合与取值一字不变）
            row["aa_scope"] = "核心测试集 108 题内"
            row["n_questions_answered_A"] = per_n["A"]
            row["n_questions_answered_C"] = per_n["C"]
        judge_128.append(row)

    sample_block = {
        "answers_total": len(items),
        "groups": list(GROUPS),
        "qids_per_group": PER_GROUP_EXPECTED,
        "primary_judge_answers": len(kimi_items),
        "primary_judge_calls_planned": len(kimi_items) * len(DIMENSIONS),
        "cross_judge_answers": len(zhipu_items),
        "cross_judge_qids": sorted({it["qid"] for it in zhipu_items}),
        "cross_judge_calls_planned": len(zhipu_items) * len(DIMENSIONS),
        "empty_answer_bodies": sum(1 for it in items if not it["answer_text"].strip()),
        "answer_chars_mean": round(sum(len(it["answer_text"]) for it in items) / len(items), 1),
    }
    if DATASET != "pr":
        # 新增键只在非 pr 档写入（保持预实验集那份 `评分汇总.json` 的键集合与取值一字不变）
        sample_block.update({
            "dataset": DATASET,
            "dataset_label": DATASET_LABEL,
            "sample_desc": SAMPLE_DESC,
            "answers_by_group": {g: sum(1 for it in items if it["group"] == g) for g in GROUPS},
            "qids_answered_unique": len({it["qid"] for it in items}),
            "cross_judge_by_group": {g: sum(1 for it in zhipu_items if it["group"] == g) for g in GROUPS},
            "cross_judge_share": round(len(zhipu_items) / len(items), 4),
        })

    summary = {
        "schema": "stage10-qa-judge-summary-v1",
        "generated_by": "交付物/06-实验与评测/工具/评分脚本.py",
        "generated_at": now_iso(),
        "caliber_statement": (
            "本汇总的问答质量分由**跨厂商大模型**按《02》第12.7节 的 0／1／2 统一量表给出，"
            "**不是人工评分**，只反映模型判断；任何人读这些读数时不得把它们当作人工金标准。"
        ),
        "prompt_version": PROMPT_VERSION,
        "scale_source": SCALE_SOURCE,
        "scale_verbatim": SCALE_VERBATIM,
        "doc02_version": current_02_version(),
        "judges": judge_cfg.get("judges") or {},
        "temperature_requested": TEMPERATURE_REQ,
        "sample": sample_block,
        "by_group": by_group,
        "subsets": subsets,
        "judgement_12_8_answer_accuracy_half": judge_128,
        "cross_model_agreement": agreement(kimi_recs, zhipu_recs),
        "cross_model_adjudication": adj_summary,
        "call_account": {
            "max_calls_including_retries": max_calls,
            "attempts_total": totals["attempts"],
            "ok": totals["ok"],
            "failed": totals["failed"],
            "retries": totals["retries"],
            "cache_hits_reused_not_billed": totals["cache_hits"],
            "prompt_tokens": totals["prompt_tokens"],
            "completion_tokens": totals["completion_tokens"],
            "total_tokens": totals["total_tokens"],
            "failed_records": sum(1 for r in all_recs if r["status"] != "ok"),
            "failed_dimension_cells": sum(len(r["judge_failed"]) for r in all_recs),
        },
    }
    write_json(SUMMARY_PATH, summary)
    write_report_md(summary, kimi_recs, zhipu_recs, ledger)
    log("已落盘：%s" % RECORDS_PATH)
    log("已落盘：%s" % SUMMARY_PATH)
    log("已落盘：%s" % REPORT_PATH)
    log("已落盘：%s" % LEDGER_PATH)
    return 0


def fmt_cell(v):
    return "—" if v is None else ("%.4f" % v if isinstance(v, float) else str(v))


def write_report_md(summary: dict, kimi_recs, zhipu_recs, ledger) -> None:
    S = summary
    L = []
    A = L.append
    # 数据集相关的取值集中在这里；`pr` 档下每个变量的取值都与改造前的字面量逐字相同，
    # 因此预实验集那份报告逐字节不变（已验证）。
    IS_PR = (DATASET == "pr")
    ANSWERS_REL = os.path.relpath(V13, ROOT).replace("\\", "/")
    QUESTIONS_REL = os.path.relpath(QUESTIONS_PATH, ROOT).replace("\\", "/")
    N_BY_GROUP = {g: sum(1 for r in kimi_recs if r["group"] == g) for g in GROUPS}
    GROUP_N_TXT = "／".join("%s %d" % (g, N_BY_GROUP[g]) for g in GROUPS)
    SUBSET_RULE_SRC = ("交付物/06-实验与评测/工具/跑AC对照.py" if IS_PR
                       else "交付物/06-实验与评测/工具/跑正式对照.py 第 143～145 行")
    A("# 阶段10 · 问答质量评分报告（跨厂商模型评审）")
    A("")
    A("> **口径声明（请先读这一段）**：本报告的问答质量分由**跨厂商大模型**（主评 Moonshot Kimi，"
      "交叉核对 智谱 GLM）按《02-项目执行总控文档》第12.7节 的 0／1／2 统一量表逐条给出，"
      "**是模型评分、不是人工评分**。报告中的一切「一致率」都是**跨模型一致率**，"
      "用于说明两家模型在这批答案上的判断是否相同，**不构成任何评分者一致性证据、也不构成评分信度**；"
      "本课题**没有**人工逐题评分，也**没有**人工金标准。读这些数字时，请把它们读成"
      "「在这一固定量表与这一固定 prompt 下，两个第三方模型对同一批已生成答案的判断」，"
      "而不是「这批答案的客观质量」。")
    A("")
    A("| 项 | 值 |")
    A("| --- | --- |")
    _obj = ("已跑好的 30 题 × A～E 五组 ＝ " if IS_PR
            else "已跑好的 A～E 五组共 %d 条有效答案（%s）＝ " % (S["sample"]["answers_total"], GROUP_N_TXT))
    A("| 被评对象 | %s**%d 条答案**（`%s/{A..E}/qa_records.jsonl`，只读） |"
      % (_obj, S["sample"]["answers_total"], ANSWERS_REL))
    A("| 生成侧模型 | `deepseek-flash`（**判分不使用它**） |")
    kimi = (S["judges"] or {}).get("kimi") or {}
    zhipu = (S["judges"] or {}).get("zhipu") or {}
    A("| 主 judge | %s：请求 `%s`，实测解析到 `%s` |"
      % (kimi.get("label") or "Moonshot Kimi", kimi.get("model_requested"), kimi.get("model_resolved")))
    A("| 副 judge（交叉核对） | %s：请求 `%s`，实测解析到 `%s` |"
      % (zhipu.get("label") or "智谱 Zhipu", zhipu.get("model_requested"), zhipu.get("model_resolved")))
    A("| prompt 版本 | `%s` |" % S["prompt_version"])
    A("| 温度 | 请求 temperature=%s；实测可用值见各条记录的 `temperature` 字段 |" % S["temperature_requested"])
    A("| 量表来源 | %s（**逐字照抄，未自创**；报告生成时《02》基线版本 %s） |" % (S["scale_source"], S.get("doc02_version") or "未解析"))
    A("| 评分主体口径 | 《02》第12.7节「评分主体口径变更（2026-10-04，作者裁定）」段：跨厂商模型评审（主 judge＝kimi、副 judge＝智谱，副 judge 对 ≥20% 样本交叉核对） |")
    A("| 本报告不含 | 任何人工评分、任何「评分者一致性／信度」表述、任何凭据 |")
    A("| 口径的最终性 | **作者裁定（2026-10-07）：「以后都不做人工」。** 三项 0／1／2 与「≥20% 二次复评」一律由跨厂商模型给出，**本报告的模型评分口径就是最终口径**——不存在「待人工评分」这一后续步骤，下游文本不得再把它写成待办 |")
    A("")

    A("## 一、量表原文（逐字引用）")
    A("")
    A("> " + S["scale_verbatim"])
    A("")
    A("三维度与量表取值的对应（本脚本 prompt 中逐字沿用）：")
    A("")
    A("| 维度 | 0 | 1 | 2 |")
    A("| --- | --- | --- | --- |")
    for key, label, scale, focus in DIMENSIONS:
        parts = [p.strip().split("=", 1) for p in scale.split("，")]
        vals = {}
        for p in parts:
            if len(p) == 2 and p[0].strip() in ("0", "1", "2"):
                vals[p[0].strip()] = p[1].strip()
        A("| %s | %s | %s | %s |" % (label, vals.get("0", ""), vals.get("1", ""), vals.get("2", "")))
    A("")
    A("判分口径要点：**Answer Accuracy** 与**参考答案**对照；**Completeness** 看对参考答案关键信息的覆盖；"
      "**Faithfulness** 只认**被评答案可用证据**（本次问答实际检索到的证据全文随 prompt 一同送入 judge），"
      "该题的 gold 证据只作 Accuracy／Completeness 的对照锚点、**不得**当作 Faithfulness 的支撑来源。")
    A("")

    A("## 二、样本与规模")
    A("")
    sm = S["sample"]
    if IS_PR:
        _sample_desc = "30 题 × 5 组"
        _cross_desc = "、".join(sm["cross_judge_qids"])
    else:
        _sample_desc = sm.get("sample_desc") or SAMPLE_DESC
        _cross_desc = ("每组 ⌈20%⌉ 系统抽样（"
                       + "／".join("%s %d" % (g, sm["cross_judge_by_group"][g]) for g in GROUPS)
                       + "），占 %d 条的 %.2f%%" % (sm["answers_total"], sm["cross_judge_share"] * 100))
    A("| 项 | 值 |")
    A("| --- | --- |")
    A("| 答案总数 | %s（%s） |" % (sm["answers_total"], _sample_desc))
    A("| 空正文条数 | **%s** |" % sm["empty_answer_bodies"])
    A("| 正文平均字数 | %s |" % sm["answer_chars_mean"])
    A("| 主 judge 评分条数 | %s 条 × 3 维度 ＝ %s 次计划调用 |" % (sm["primary_judge_answers"], sm["primary_judge_calls_planned"]))
    A("| 副 judge 评分条数 | %s 条（%s）× 3 维度 ＝ %s 次计划调用 |"
      % (sm["cross_judge_answers"], _cross_desc, sm["cross_judge_calls_planned"]))
    A("| 不一致复核 | 只在两家分歧的维度上调用副 judge，最多 %s 次（%s 条 × 3 维；一致的维度不调用） |"
      % (sm["cross_judge_answers"] * 3, sm["cross_judge_answers"]))
    A("| 计划调用合计（含重试前） | %s 次，授权上限 %s 次 |"
      % (sm["primary_judge_calls_planned"] + sm["cross_judge_calls_planned"],
         S["call_account"]["max_calls_including_retries"]))
    A("")

    A("## 三、五组 × 三维度读数（主 judge）")
    A("")
    for dim_key in DIM_KEYS:
        A("### 3.%d %s" % (DIM_KEYS.index(dim_key) + 1, DIM_LABEL[dim_key]))
        A("")
        A("| 组 | 均值 | 0 分 | 1 分 | 2 分 | 已评条数 | 未评条数 |")
        A("| --- | --- | --- | --- | --- | --- | --- |")
        for g in GROUPS:
            d = S["by_group"][g]["dimensions"][dim_key]
            dist = d["distribution_0_1_2"]
            A("| %s | %s | %d | %d | %d | %d | %d |"
              % (GROUP_LABEL[g], fmt_cell(d["mean"]), dist[0], dist[1], dist[2],
                 d["n_scored"], N_BY_GROUP[g] - d["n_scored"]))
        A("")
    A("三维度总览（均值）：")
    A("")
    A("| 组 | Answer Accuracy | Completeness | Faithfulness |")
    A("| --- | --- | --- | --- |")
    for g in GROUPS:
        A("| %s | %s | %s | %s |" % (
            GROUP_LABEL[g],
            fmt_cell(S["by_group"][g]["dimensions"]["answer_accuracy"]["mean"]),
            fmt_cell(S["by_group"][g]["dimensions"]["completeness"]["mean"]),
            fmt_cell(S["by_group"][g]["dimensions"]["faithfulness"]["mean"])))
    A("")

    A("## 四、三个子集读数（《02》第12.8节 的分组口径：关系型／多跳型／时序型，允许重叠）")
    A("")
    A("子集标签取自 `%s` 的 `task_type`／`gold_hop_depth`／`time_constraint`，"
      "口径与既有 `%s` 一致：关系型＝`task_type == 关系型`；"
      "多跳型＝`gold_hop_depth ≥ 1`；时序型＝`time_constraint == 有`。"
      % (QUESTIONS_REL, SUBSET_RULE_SRC))
    A("")
    for s in S["subsets"]:
        A("### 4.%d %s子集（%d 题）" % (S["subsets"].index(s) + 1, s["name"], s["per_group"]["A"]["n_questions"]))
        A("")
        A("| 组 | Answer Accuracy | Completeness | Faithfulness |")
        A("| --- | --- | --- | --- |")
        for g in GROUPS:
            d = s["per_group"][g]["dimensions"]
            A("| %s | %s | %s | %s |" % (GROUP_LABEL[g], fmt_cell(d["answer_accuracy"]["mean"]),
                                        fmt_cell(d["completeness"]["mean"]), fmt_cell(d["faithfulness"]["mean"])))
        A("")
    A("> 子集内题目数少于 30，读数比组级读数更容易受单条答案影响；本报告不据此作强度更高的结论。"
      if IS_PR else
      "> 本节的三个子集按上面同一条判据在**全部已评答案**上分组（子集允许重叠、题数见各小节标题）；"
      "正式集下 §五 的判定另按《02》第12.8节 明文限定在核心测试集 108 题内，两者范围不同、不得混读。")
    A("")

    A("## 五、《02》第12.8节 判定的机检口径结论（A 组＝Baseline 2 vs C 组＝Method）")
    A("")
    if not IS_PR:
        A("> **判定规则与判定范围的原文（《02-项目执行总控文档》第12.8节，逐字引用、一字未改）**：")
        A("> ")
        A("> " + RULE_128_VERBATIM)
        A("> ")
        A("> " + RULE_128_SCOPE_VERBATIM)
        A("")
    A("第12.8节 的判定要求**两个条件同时成立**：① KG-RAG 在该子集上的 Complete Evidence Recall@K **高于** "
      "Vector RAG；② 该子集的 Answer Accuracy **不下降**。下表给出这两个条件在三个子集上的机检读数。")
    A("")
    if not IS_PR:
        A("① 的读数取自既有 `%s` 的 `subsets_named_core`（＝核心集 108 题内按三子集分组的 "
          "Complete Evidence Recall@K，逐字对应 `对照产出_正式/A_vs_C_对照报告.md` 第 4.1 节），"
          "**本次评分不重算、不改动它**；② 的读数＝本次跨厂商模型评分给出的 Answer Accuracy 均值。"
          % os.path.relpath(AC_COMPARE_PATH, ROOT).replace("\\", "/"))
        A("")
    A("| 子集 | 题数 | CER@K（A） | CER@K（C） | ① CER 提高 | Answer Accuracy（A） | Answer Accuracy（C） | ② 不下降 | 合取判定 |")
    A("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in S["judgement_12_8_answer_accuracy_half"]:
        A("| %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            row["subset"], row["n_questions"], fmt_cell(row["cer_A"]), fmt_cell(row["cer_C"]),
            "成立" if row["cer_half_holds"] else "**不成立**",
            fmt_cell(row["answer_accuracy_A"]), fmt_cell(row["answer_accuracy_C"]),
            row["answer_accuracy_verdict"], "成立" if row["combined_holds"] else "**不成立**"))
    A("")
    cer_all_fail = all(not r["cer_half_holds"] for r in S["judgement_12_8_answer_accuracy_half"])
    aa_rows = S["judgement_12_8_answer_accuracy_half"]
    if IS_PR:
        A("**读法（照实写）**：")
        A("")
        if cer_all_fail:
            A("- ① 那一半（Complete Evidence Recall@K 提高）在**三个子集上都不成立**——A 组与 C 组的 CER@K 逐子集相同"
              "（见上表两列读数字面相等），这是既有 `对照产出_v13/A_vs_C_对照.json` 的读数，本次评分不改变它。")
        for row in aa_rows:
            A("- ② 那一半（该子集 Answer Accuracy 不下降）：%s 子集上 **%s**（C 组 %s vs A 组 %s，差 %s）。"
              % (row["subset"], row["answer_accuracy_verdict"], fmt_cell(row["answer_accuracy_C"]),
                 fmt_cell(row["answer_accuracy_A"]), fmt_cell(row["answer_accuracy_gap_C_minus_A"])))
        A("")
        A("**合成结论**：既然 ①（CER 提高）在三个子集上都不成立，按第12.8节 的合取条件，"
          "**知识图谱在本数据集与本次配置下、在这三个子集上都没有满足判定的「额外检索价值」**；"
          "本节的 ② 只是把「Answer Accuracy 不下降」这一半单独算清楚（上表最后一列），"
          "它成立与否都**不能**单独翻转合取判定。三种结果都是第12.8节 认可的有效实验结论，"
          "这里如实报第三种（没有任何子集满足判定条件）并提示按归因方法分析原因。")
        A("")
        A("> **范围限定**：本次评分覆盖的是**30 题预实验集**，而第12.8节 的主体判定依据是核心测试集的 **108 题**；"
          "本节的机检结论只能在「30 题预实验集 + 本次固定配置」这一范围内读，不得搬到 108 题的口径上使用。")
    else:
        A("**逐子集判定（照实写，不合并）**：")
        A("")
        for row in aa_rows:
            A("- **%s子集**（题数 %s；参与 ② 计分的条数：A 组 %s 条／C 组 %s 条，范围＝%s）："
              "① Complete Evidence Recall@K %s（A %s → C %s）；② Answer Accuracy **%s**（C 组 %s vs A 组 %s，差 %s）；"
              "**①且② 的合取判定：%s**。"
              % (row["subset"], row["n_questions"],
                 row.get("n_questions_answered_A"), row.get("n_questions_answered_C"),
                 row.get("aa_scope") or "全部已评答案",
                 "成立（C 高于 A）" if row["cer_half_holds"] else "**不成立**",
                 fmt_cell(row["cer_A"]), fmt_cell(row["cer_C"]),
                 row["answer_accuracy_verdict"], fmt_cell(row["answer_accuracy_C"]),
                 fmt_cell(row["answer_accuracy_A"]), fmt_cell(row["answer_accuracy_gap_C_minus_A"]),
                 "**成立**" if row["combined_holds"] else "**不成立**"))
        A("")
        n_ok = sum(1 for r in aa_rows if r["combined_holds"])
        A("**合成结论**：按第12.8节 的合取条件（① CER@K 高于 Vector RAG **且** ② Answer Accuracy 不下降）逐子集判定，"
          "三个子集中 **%d 个**满足合取条件——%s。判定按子集分别进行、互不牵连，"
          "本报告不把三个子集合并成一个整体结论；三种结果（多子集满足／部分满足／都不满足）都是第12.8节 认可的有效实验结论，"
          "此处如实报告机检读数给出的那一种。"
          % (n_ok, "、".join("%s%s" % (r["subset"], "满足" if r["combined_holds"] else "不满足") for r in aa_rows)))
        A("")
        A("> **范围限定**：本节 ①② 的判定范围＝**核心测试集 108 题**（第12.8节 明文），"
          "压力测试子集（12 题：FQ-073～FQ-084）只作附加观察、**未进入本节判定**；"
          "本节读数只在「本次题集 ＋ 冻结配置（K=10／N=20／Context Token Budget=3600／g=2，model=deepseek-flash）"
          "＋ 模型评分口径」这一范围内读，不得外推。")
    A("")
    A("> **口径限定（《02》第12.7节 2026-10-04 口径变更段 ③）**：上表的『Answer Accuracy』必须读成"
      "**模型评分口径下的准确率**（由跨厂商模型按第12.7节 原量表逐字给出），"
      "**不是人工评分口径下的准确率**；论文引用该结论时须一并写明评分者身份为跨厂商模型、非人工。")
    A("")

    A("## 六、跨模型一致率（kimi vs 智谱）")
    A("")
    cm = S["cross_model_agreement"]
    A("口径：副 judge 在同一样本上跑**同一量表、同一 prompt 版本**，与主 judge 逐条比对。"
      "**上报口径＝简单一致率（逐维、逐组）**，并附**线性加权 kappa**（0／1／2 视作序数尺度）作参考。"
      "选简单一致率为上报口径的理由：样本仅 %d 条，序数分布高度偏斜（大量答案被两家同时判 2 分），"
      "kappa 在这种边际分布下对少量不一致反应过度、数值不稳定，容易把「两家基本一致」读成「两家不一致」；"
      "而且当两家的边际分布完全相同且退化（例如某维度全部判 2 分）时，**kappa 在数学上无定义**"
      "（期望不一致度＝0），本报告对该情形记「无定义」而不拿 1.0 冒名顶替。"
      "简单一致率不受边际分布影响，更适合本样本规模。**两者都只说明模型之间是否一致，不说明评分是否可信。**"
      % cm["n_answers_compared"])
    A("")
    A("| 维度 | 比对条数 | 简单一致率 | 线性加权 kappa | 平均绝对差 | 两家同判 2 分 |")
    A("| --- | --- | --- | --- | --- | --- |")
    for k in DIM_KEYS:
        d = cm["per_dimension"][k]
        A("| %s | %d | %s | %s | %s | %d（%s） |" % (
            DIM_LABEL[k], d["n"], fmt_cell(d["simple_agreement"]), fmt_cell(d["linear_weighted_kappa"]),
            fmt_cell(d["mean_abs_diff"]), d["both_full_marks"], fmt_cell(d["both_full_marks_rate"])))
    A("")
    A("逐组（A～E）：")
    A("")
    A("| 组 | 比对条数 | Answer Accuracy | Completeness | Faithfulness |")
    A("| --- | --- | --- | --- | --- |")
    for g in GROUPS:
        n = (cm["per_group"][g]["answer_accuracy"] or {}).get("n")
        cells = []
        for k in DIM_KEYS:
            d = cm["per_group"][g][k]
            cells.append("%s（κ=%s）" % (fmt_cell(d["simple_agreement"]), fmt_cell(d["linear_weighted_kappa"])))
        A("| %s | %s | %s |" % (GROUP_LABEL[g], n, " | ".join(cells)))
    A("")

    A("## 七、不一致样本的最终分复核（《02》第12.7节 2026-10-04 口径变更段）")
    A("")
    ad = S["cross_model_adjudication"]
    A("口径原文（《02》第12.7节）：「跨模型核对不一致的样本，按上一段对『两次评分不一致』的同一处置方式"
      "——由副 judge 复核证据后给出最终分，并在实验记录中保留两次评分与不一致原因，只是执行者由单人改为两个厂商的模型。」"
      "本节即该条的落点：**两家一致的维度不额外调用**（没有争议，最终分就是该分）；"
      "**不一致的维度**由副 judge（智谱）带完整证据上下文复核一次，给出最终分与不一致原因。")
    A("")
    A("| 项 | 值 |")
    A("| --- | --- |")
    A("| 交叉核对样本 | %d 条 × 3 维 ＝ %d 格 |" % (ad["n_answers_cross_checked"], ad["n_cells"]))
    A("| 两家一致 | %d 格（%s） |" % (ad["n_agree"],
                                     fmt_cell(ad["n_agree"] / ad["n_cells"]) if ad["n_cells"] else "—"))
    A("| 两家不一致 | %d 格 |" % ad["n_disagree"])
    A("| 已给出最终分（副 judge 复核） | %d 格 |" % ad["n_adjudicated"])
    A("| 复核未完成（如实登记，不补分） | %d 格 |" % ad["n_adjudication_failed"])
    A("")
    A("逐维：")
    A("")
    A("| 维度 | 比对格数 | 一致 | 不一致 | 已复核给最终分 |")
    A("| --- | --- | --- | --- | --- |")
    for k in DIM_KEYS:
        d = ad["by_dimension"][k]
        A("| %s | %d | %d | %d | %d |" % (DIM_LABEL[k], d["n"], d["agree"], d["disagree"], d["adjudicated"]))
    A("")
    if ad["disagreement_notes"]:
        A("不一致清单（逐格保留两次评分、最终分与不一致原因）：")
        A("")
        A("| 样本 | 组 | 维度 | 主 judge | 副 judge | 最终分 | 不一致原因 |")
        A("| --- | --- | --- | --- | --- | --- | --- |")
        for n in ad["disagreement_notes"]:
            A("| %s | %s | %s | %s | %s | %s | %s |" % (
                n["qid"], n["group"], DIM_LABEL[n["dimension"]], n["kimi_score"], n["zhipu_score"],
                fmt_cell(n["final_score"]), (n["note"] or "（未登记）").replace("|", "／")[:60]))
        A("")
    A("**终值口径**：未做交叉核对的 %d 条用主 judge 的分；做了交叉核对的 %d 条用上表的最终分"
      "（一致即同分，不一致取副 judge 复核分）。终值在各组上的均值与分布："
      % (sm["answers_total"] - ad["n_answers_cross_checked"], ad["n_answers_cross_checked"]))
    A("")
    A("| 组 | Answer Accuracy | Completeness | Faithfulness |")
    A("| --- | --- | --- | --- |")
    for g in GROUPS:
        d = ad["final_scores_by_group"][g]
        A("| %s | %s | %s | %s |" % (GROUP_LABEL[g], fmt_cell(d["answer_accuracy"]["mean"]),
                                    fmt_cell(d["completeness"]["mean"]), fmt_cell(d["faithfulness"]["mean"])))
    A("")
    A("> 注意：上表的终值只在 20% 样本上受过副 judge 影响，其余 80% 仍是主 judge 单方判断；"
      "因此终值**不比第三节的主 judge 读数更接近「真值」**，它只是按第12.7节 规定的分歧处置流程算出来的口径值。")
    A("")

    A("## 八、调用账与失败／重试")
    A("")
    ca = S["call_account"]
    A("| 项 | 值 |")
    A("| --- | --- |")
    A("| 授权上限（含重试） | %d 次 |" % ca["max_calls_including_retries"])
    A("| **累计调用次数（真实 HTTP 尝试，含重试）** | **%d 次** |" % ca["attempts_total"])
    A("| 其中成功 | %d 次 |" % ca["ok"])
    A("| 其中失败（该次尝试没拿到可用结果；**均已在重试或续跑中补回**） | %d 次 |" % ca["failed"])
    A("| 其中为重试（第 2／3 次尝试） | %d 次 |" % ca["retries"])
    A("| 缓存命中复用（**不算调用**、不占预算） | %d 次 |" % ca["cache_hits_reused_not_billed"])
    A("| prompt token | %d |" % ca["prompt_tokens"])
    A("| completion token | %d |" % ca["completion_tokens"])
    A("| **token 合计** | **%d** |" % ca["total_tokens"])
    A("| 三维未评齐的条数 | %d |" % ca["failed_records"])
    A("| 未评到分的维度格数 | %d |" % ca["failed_dimension_cells"])
    A("")
    A("逐次调用（时间／模型／token／成功与否，不含凭据）见 `调用台账.json`；"
      "每个 judge 每次调用的原始返回见 `_judge原始返回/<judge>/<prompt_version>/`。")
    A("")
    planned = S["sample"]["primary_judge_calls_planned"] + S["sample"]["cross_judge_calls_planned"]
    _plan_txt = ("450 ＋ 90 ＝ %d" % planned) if IS_PR else (
        "%d ＋ %d ＝ %d" % (S["sample"]["primary_judge_calls_planned"],
                           S["sample"]["cross_judge_calls_planned"], planned))
    _trunc_txt = "副 judge 输出被 max_tokens 截断" if IS_PR else "judge 输出被 max_tokens 截断（两家都发生过）"
    A("**为什么实际次数高于计划数**：计划的唯一评分格数是 %s 格，"
      "实际发出 %d 次尝试，多出的 %d 次全部用于把失败补回来——其中重试（第 2／3 次尝试）%d 次，"
      "其余 %d 次是脚本续跑时对上一轮没拿到可用结果的格子的补跑。失败本身按三类如实登记："
      "① 首跑时判定端点拒收 `temperature=0`（1 次，随即按实测回退）；"
      "② judge 返回不是合法 JSON（含极少数漏写 JSON 引号、以及%s）；"
      "③ 其余为偶发失败。**这些失败没有被静默丢弃、也没有补 0 分**：补不回来的格子会以 `judge_failed` "
      "原样进 `评分记录.jsonl` 并计入上表；本次最终**未评到分的维度格数为 %d**。"
      % (_plan_txt, ca["attempts_total"], ca["attempts_total"] - planned, ca["retries"],
         ca["attempts_total"] - planned - ca["retries"], _trunc_txt, ca["failed_dimension_cells"]))
    A("")

    A("## 九、已知限制（如实登记，不粉饰）")
    A("")
    A("1. **judge 与生成侧可能同源偏见**：生成侧是 `deepseek-flash`，两个 judge 是 Moonshot Kimi 与智谱 GLM，"
      "厂商不同但都是中文大模型、都以相似的中文财经公告语料预训练；同一批答案上出现系统性同向偏差是可能的，"
      "本报告无法排除，只能靠跨厂商这一设计减轻。")
    A("2. **单次评分、无人工锚点**：每条只由一个 judge 评一次（副 judge 只覆盖 20% 样本），"
      "**没有任何人工逐题评分可比对**，因此本报告**不能**给出评分准确度、也不能给出任何"
      "「评分者一致性／信度」类结论；能给的只有跨模型一致率。")
    A("3. **量表是简表**：第12.7节 的 0／1／2 描述只有一句话（如「1 = 部分正确」），"
      "「部分」的边界本身有解释空间，不同 judge、不同题上的边界把握可能不同；"
      "本报告用固定 prompt 版本 + 尽可能低的温度（实际可用值见第 6 条）尽量压低这一自由度，但不能消除。")
    A("4. **Faithfulness 判定的边界**：judge 拿到的是**本次问答实际检索到的证据全文**，"
      "因此「答案与证据一致」并不等于「答案与公开事实一致」——"
      "如果证据本身被抽错，答案忠实于错误证据时仍会得高分；反之，"
      "答案里正确但证据里没出现的信息会被判为无依据。这两类误判本报告无法从读数中分离。")
    A("5. **judge 只看被评答案的字面**：答案里「【证据来源】」等段落是系统拼装的固定结构，"
      "judge 可能受其格式与引用标记影响（例如把带 [证据n] 标记的句子当作更有依据），该影响未做消融。")
    A("6. **temperature 的实测偏差（本次真的发生了）**：口径是 temperature 0。实测 "
      "**主 judge 的 `kimi-k3` 端点拒收 0**（HTTP 400：`invalid temperature: only 1 is allowed for this model`），"
      "按端点唯一允许值回退到 **1.0**；副 judge 的 `glm-5.3-flash` 接受 **0.0**。"
      "因此**主 judge 的逐条判断带有采样随机性**，同一输入重跑未必逐字复现（副 judge 侧无此问题）。"
      "实际用到的值逐条记在 `评分记录.jsonl` 的 `temperature` 字段、`调用台账.json` 的每次尝试行"
      "与 `_judge配置.json` 里，未隐藏。")
    A("7. **样本规模**：%s单条答案的分差就能改变子集均值，"
      "故本报告只用「成立／不成立」这类方向性表述，不报显著性。"
      % ("150 条答案、30 题；子集内题数最少 12 题（时序型）／21 题（多跳型），" if IS_PR else
         ("%d 条答案、120 题题集（核心 108 ＋ 压力 12）；三个子集按全部已评答案分组，条数 %s；"
          % (sm["answers_total"],
             "／".join("%s %d 条" % (s["name"], sum(1 for r in kimi_recs if r["qid"] in set(s["qids"])))
                       for s in S["subsets"])))))
    A("8. **只评不生成**：本次评分不改变任何一条答案，也不重跑任何问答；"
      "被评答案本身的门禁状态、空正文与拼装结构都沿用 `%s` 的原始留痕。" % ANSWERS_REL)
    A("")

    A("## 十、产物清单")
    A("")
    A("| 文件 | 内容 |")
    A("| --- | --- |")
    A("| `评分记录.jsonl` | 逐条评分：主 judge %d 条 + 副 judge %d 条；每条含三维分值、每维一句 reason、judge 模型、prompt 版本、tokens、latency；副 judge 的记录另带 `adjudication`（两次评分、是否一致、最终分、不一致原因） |"
      % (len(kimi_recs), len(zhipu_recs)))
    A("| `评分汇总.json` | 五组 × 三维度均值与 0／1／2 分布、三子集读数、12.8 机检结论、跨模型一致率、不一致复核与终值、调用与 token 账 |")
    A("| `问答评分报告.md` | 本文件 |")
    A("| `调用台账.json` | 逐次调用的时间／模型／token／成功与否（不含凭据） |")
    A("| `_judge原始返回/` | 每个 judge 每次调用的原始返回与 usage（重跑续跑与审计用） |")
    A("| `_judge配置.json` | 两家实测解析到的 model id、实际可用 temperature、凭据来源标签（不含取值） |")
    A("| `_冒烟记录.jsonl` | 冒烟 %d 条的评分记录 |" % len(select_smoke(kimi_recs)))
    A("")
    A("评分脚本：`交付物/06-实验与评测/工具/评分脚本.py`（可重跑；缓存命中即复用，不重复烧调用）。")
    A("")

    # ---- 附录：未满分逐条清单（供失败案例分析按模型评分口径登记）----
    def _list_of(dim_key, pred):
        out = []
        for r in sorted(kimi_recs, key=lambda x: (x["group"], x["answer_key"])):
            v = r["scores"].get(dim_key)
            if v is not None and pred(v):
                out.append((r["group"], r["qid"], r["answer_key"], v, (r["reasons"].get(dim_key) or "").strip()))
        return out

    A("## 十一、附：未满分逐条清单（供《失败案例分析》按模型评分口径登记）")
    A("")
    A("这一节是给下游用的：此前《失败案例分析》第 ⑤ 类「生成不忠实」的登记是「**无判据——需人工 0／1／2 评分中的 "
      "Faithfulness 一项；未评分前只能记『无法判定』**」。按《02》第12.7节 的模型评分口径与本次作者裁定"
      "（以后都不做人工），**Faithfulness 现在有判据了**：下面就是全部未满分的逐条清单，"
      "《失败案例分析》可直接据此把第 ⑤ 类从「无法判定」改登记为「模型评分口径下的实例清单」"
      "（**须带口径限定**：这是模型评分，不是人工判定）。")
    A("")
    tot = {k: {"0": 0, "1": 0, "2": 0} for k in DIM_KEYS}
    for r in kimi_recs:
        for k in DIM_KEYS:
            v = r["scores"].get(k)
            if v is not None:
                tot[k][str(v)] += 1
    A("三维度全量分布（%d 条）：" % len(kimi_recs))
    A("")
    A("| 维度 | 0 分 | 1 分 | 2 分 |")
    A("| --- | --- | --- | --- |")
    for k in DIM_KEYS:
        A("| %s | %d | %d | %d |" % (DIM_LABEL[k], tot[k]["0"], tot[k]["1"], tot[k]["2"]))
    A("")
    f1 = _list_of("faithfulness", lambda v: v < 2)
    A("### 11.1 Faithfulness 未满分（**%d 条**；其中 0 分 **%d** 条、1 分 **%d** 条）"
      % (len(f1), tot["faithfulness"]["0"], tot["faithfulness"]["1"]))
    A("")
    if f1:
        A("| 组 | 题号 | 被评答案 | 分 | judge 给的理由 |")
        A("| --- | --- | --- | --- | --- |")
        for g, qid, ak, v, rs in f1:
            A("| %s | %s | `%s` | %d | %s |" % (g, qid, ak, v, rs.replace("|", "／")))
    else:
        A("无（%d 条全部判 2 分）。" % len(kimi_recs))
    A("")
    if IS_PR:
        A("**读法**：Faithfulness 判 0 分（「存在明显无依据事实」）的条数为 **%d**，"
          "即在本批 150 条答案里，judge **没有**发现「明显编造」的实例；判 1 分的 %d 条都是"
          "「个别措辞/归属与证据有出入」这类少量不严谨（逐条见上表）。"
          "这不等于「答案全都没问题」——Faithfulness 只对照**本次检索到的证据**，"
          "证据本身抽错时答案仍会得高分（见第九节已知限制第 4 条）。"
          % (tot["faithfulness"]["0"], tot["faithfulness"]["1"]))
    else:
        A("**读法**：Faithfulness 判 0 分（「存在明显无依据事实」）的条数为 **%d**、判 1 分（「少量不严谨」）"
          "的条数为 **%d**，逐条的分值与 judge 一句话理由都在上表（这两类就是《失败案例分析》第 ⑤ 类"
          "「生成不忠实」在**模型评分口径**下的实例清单）。这不等于「答案全都没问题」——"
          "Faithfulness 只对照**本次检索到的证据**：证据本身抽错时答案仍会得高分，"
          "而答案里正确但证据里没出现的信息会被判为无依据（见第九节已知限制第 4 条）；"
          "并且这 %d／%d 条的判定本身是**模型评分**，不是人工判定。"
          % (tot["faithfulness"]["0"], tot["faithfulness"]["1"],
             tot["faithfulness"]["0"], tot["faithfulness"]["1"]))
    A("")
    a0 = _list_of("answer_accuracy", lambda v: v == 0)
    A("### 11.2 Answer Accuracy 判 0 分（**%d 条**）" % len(a0))
    A("")
    A("| 组 | 题号 | 被评答案 | judge 给的理由 |")
    A("| --- | --- | --- | --- |")
    for g, qid, ak, v, rs in a0:
        A("| %s | %s | `%s` | %s |" % (g, qid, ak, rs.replace("|", "／")))
    A("")
    if IS_PR:
        A("**读法（照实说）**：0 分集中在 **PE-16 与 PE-23** 两道题的五组答案上——这两题的系统回答"
          "要么**否认存在共同事件**、要么**以证据不足拒答**，而参考答案都给出了明确主体；"
          "judge 据此判「错误」而非「部分正确」。这属于**答案侧的系统性失败模式**（该答不答／答反），"
          "不是评分噪声，可直接进《失败案例分析》的「检索漏召回」或「生成不忠实」归因链上游。")
    else:
        _byq = {}
        for g, qid, ak, v, rs in a0:
            _byq.setdefault(qid, []).append(g)
        _top = sorted(_byq.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        A("**读法（照实说）**：Answer Accuracy 判 0 分的 %d 条分布在 **%d 道题**上，最集中的是 %s。"
          "0 分的含义按第12.7节 量表原文＝「答案与(参考)答案对照后错误」；逐条的 judge 理由见上表，"
          "可直接与《失败案例分析》的六类归因逐条对照。**这是模型评分口径下的读数，不是人工判定。**"
          % (len(a0), len(_byq), "、".join("%s（%d 条）" % (q, len(gs)) for q, gs in _top[:6])))
    A("")
    c0 = _list_of("completeness", lambda v: v == 0)
    A("### 11.3 Completeness 判 0 分（**%d 条**，为三维度中最弱的一项）" % len(c0))
    A("")
    A("| 组 | 题号 | 被评答案 | judge 给的理由 |")
    A("| --- | --- | --- | --- |")
    for g, qid, ak, v, rs in c0:
        A("| %s | %s | `%s` | %s |" % (g, qid, ak, rs.replace("|", "／")))
    A("")
    A("**读法**：Completeness 是三项里最弱的一项（0 分 %d 条、1 分 %d 条），"
      "与 Accuracy 的 0 分清单有重叠但更宽——**「答得不全」比「答得不对」更普遍**。"
      % (tot["completeness"]["0"], tot["completeness"]["1"]))
    A("")
    A("> 上述清单全部为**模型评分**结果，**不是人工判定**；引用时须一并写明评分者身份与 prompt 版本 `%s`。"
      % S["prompt_version"])
    A("")
    text = "\n".join(L) + "\n"
    with open(REPORT_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def status(max_calls: int) -> int:
    questions = load_questions()
    items = load_all_answers(questions)
    zhipu_items = select_cross(items)
    for judge, sub in (("kimi", items), ("zhipu", zhipu_items)):
        n = 0
        for it in sub:
            for dim in DIMENSIONS:
                p = os.path.join(CACHE_DIR, judge, PROMPT_VERSION,
                                 "%s__%s.json" % (it["answer_key"], dim[0]))
                if os.path.exists(p) and (read_json(p, {}) or {}).get("ok"):
                    n += 1
        log("%-6s 目标 %d 条（%d 格），缓存已完成 %d 格" % (judge, len(sub), len(sub) * len(DIMENSIONS), n))
    ledger = Ledger(LEDGER_PATH, max_calls)
    t = ledger._totals()
    log("台账：尝试 %d 次（成功 %d／失败 %d／重试 %d），token 合计 %d，上限 %d"
        % (t["attempts"], t["ok"], t["failed"], t["retries"], t["total_tokens"], max_calls))
    return 0


# ---------------------------------------------------------------------------
# 8. main
def rebase_out_dir(path: str) -> None:
    """把输出类路径整体重挂到指定目录（`--out-dir`）。

    只在 `apply_dataset()` 之后调用；各函数都是在调用时读这些模块级全局量，
    因此重挂即生效。用途是**并行分片**：两个进程各自的缓存与台账必须落在各自目录，
    否则「每次尝试后立即落盘」的台账会互相覆盖。
    """
    global OUT_DIR, CACHE_DIR, RECORDS_PATH, SUMMARY_PATH, REPORT_PATH
    global LEDGER_PATH, JUDGE_CFG_PATH
    OUT_DIR = os.path.abspath(path)
    CACHE_DIR = os.path.join(OUT_DIR, "_judge原始返回")
    RECORDS_PATH = os.path.join(OUT_DIR, "评分记录.jsonl")
    SUMMARY_PATH = os.path.join(OUT_DIR, "评分汇总.json")
    REPORT_PATH = os.path.join(OUT_DIR, "问答评分报告.md")
    LEDGER_PATH = os.path.join(OUT_DIR, "调用台账.json")
    JUDGE_CFG_PATH = os.path.join(OUT_DIR, "_judge配置.json")


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="阶段10 问答质量评分（跨厂商模型评审；只评已跑好的答案）")
    ap.add_argument("--probe", action="store_true", help="只探两个 judge 的连通性与实测 model id")
    ap.add_argument("--selftest", action="store_true", help="零调用：装配 150 条输入并自检")
    ap.add_argument("--smoke", action="store_true", help="冒烟 10 条 × 3 维（主 judge）")
    ap.add_argument("--run", action="store_true", help="按 --judge 跑评分（缓存命中即复用）")
    ap.add_argument("--adjudicate", action="store_true",
                    help="对两家评分不一致的维度由副 judge 复核证据给出最终分（《02》第12.7节 口径变更段）")
    ap.add_argument("--judge", default="kimi", choices=("kimi", "zhipu", "both"))
    ap.add_argument("--report", action="store_true", help="零调用：重出记录／汇总／报告")
    ap.add_argument("--status", action="store_true", help="零调用：看缓存与台账现状")
    ap.add_argument("--all", action="store_true",
                    help="probe → smoke → kimi 全量 → zhipu 交叉 → 不一致复核 → report")
    ap.add_argument("--max-calls", type=int, default=MAX_CALLS_DEFAULT,
                    help="含重试的调用上限（默认 %d，授权上限）" % MAX_CALLS_DEFAULT)
    ap.add_argument("--dataset", default="pr", choices=tuple(DATASET_PROFILES),
                    help="数据集档案：pr＝预实验集（默认，取值与改造前逐字相同）／"
                         "formal＝正式集（120 题题集的 582 条有效答案）")
    ap.add_argument("--judge-filter", default="", help="仅对指定 qid 列表（逗号分隔）评分，调试用")
    ap.add_argument("--out-dir", default=None,
                    help="覆盖输出目录（缓存／记录／汇总／报告／台账／judge 配置一并重挂）。"
                         "**并行分片用**：台账「每次尝试后立即落盘」，两个进程共享同一目录会互相覆盖，"
                         "故并行时必须各写各的目录，跑完再合并缓存与台账。默认取数据集档案的 out_dir。")
    args = ap.parse_args(argv)
    apply_dataset(args.dataset)
    if args.out_dir:
        rebase_out_dir(args.out_dir)
    max_calls = int(args.max_calls)

    if not (args.probe or args.selftest or args.smoke or args.run or args.report
            or args.status or args.all or args.adjudicate):
        ap.print_help()
        return 2

    if args.selftest:
        return selftest(max_calls)
    if args.status:
        return status(max_calls)
    if args.report:
        return build_report(max_calls)
    if args.adjudicate:
        return run_adjudication(max_calls)
    if args.all:
        rc = probe(None, max_calls)
        if rc != 0:
            log("probe 未通过，按纪律停下（不硬跑）。")
            return rc
        rc = smoke(max_calls)
        if rc != 0:
            log("冒烟未通过，按纪律停下（不硬跑全量）。")
            return rc
        questions = load_questions()
        items = load_all_answers(questions)
        run_judge("kimi", items, max_calls, "主 judge 全量")
        run_judge("zhipu", select_cross(items), max_calls, "副 judge 交叉核对")
        run_adjudication(max_calls)
        return build_report(max_calls)
    if args.probe:
        return probe(None, max_calls)
    if args.smoke:
        return smoke(max_calls)

    # --run
    questions = load_questions()
    items = load_all_answers(questions)
    if args.judge_filter:
        want = {q.strip() for q in args.judge_filter.split(",") if q.strip()}
        items = [it for it in items if it["qid"] in want or it["answer_key"] in want]
        log("过滤后 %d 条答案" % len(items))
    if args.judge in ("kimi", "both"):
        run_judge("kimi", items, max_calls, "主 judge")
    if args.judge in ("zhipu", "both"):
        run_judge("zhipu", select_cross(items), max_calls, "副 judge 交叉核对")
    return 0


if __name__ == "__main__":
    sys.exit(main())
