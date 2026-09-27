# -*- coding: utf-8 -*-
"""代码\\检索\\config.py —— 第 7 阶段（RAG 检索系统）检索组件的**唯一参数来源**。

本文件只放参数与读取方式，不放任何密钥（第 7 阶段的链路上没有大语言模型调用，
也不需要密钥；`api_key` 一类读取方式**刻意不提供**，以免第 8 阶段之前被误用）。
脚本内不得写死模型名、路径、阈值、K／N／预算或日期，一律经本文件读取
（沿用 `代码\\数据准备\\config.py` 与 `代码\\抽取与图谱\\config.py` 已确立的做法）。

参数来源（本文件只引用、不新增、不改名）：

* 检索管线的三段划分、四级策略、**Top-K 五步契约**、A～E 五组开关、裁剪规则与
  证据排序口径：《10-系统总体设计（第四阶段）》第4.6节（＝《02》第12.7节）。
* 输入资产与只读纪律：《13-数据准备（第五阶段）》第9.2节、第9.4节；数据集 `v2.1`。
* 图谱侧输入与已知边界：《16-事件抽取与知识图谱（第六阶段）》第八节、第九节；
  现行导出物 `阶段06-事件抽取与知识图谱\\图谱导出\\v2.1_v1_2\\`。
* 三项 TBD（K／N／Context Token Budget）由本阶段预实验固化并回《02》登记：
  《18-第7阶段任务书（RAG检索系统）》第2.4节、硬约束 10、T8。
* 空值语义与相对时间基准：《02》第11.3节、第10.3节，v2.9 裁定 ① 与 ②。

**K／N／Context Token Budget 在 T8 之前一律为 `None`（TBD）**：脚本读到 `None`
必须报错退出，不得用默认值兜底——否则预实验的"饱和"会在不同输入之间漂移。
"""

from __future__ import annotations

import hashlib
import json
import os

# --------------------------------------------------------------------------
# 1. 路径
# --------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

STAGE_DIR = os.path.join(ROOT, "阶段07-RAG检索系统")
OUTPUT_DIR = os.path.join(STAGE_DIR, "检索产出")          # T4.3 的结构化产出
QUESTIONS_DIR = os.path.join(STAGE_DIR, "预实验问题集")     # T4.4 的题集四件
DOCS_DIR = os.path.join(STAGE_DIR, "_工作底稿")            # 只读验证与临时产物（不入《19》）

# --- 向量侧输入（只读）---
DATASET_VERSION = "v2.1"
DATASET_ROOT = os.path.join(ROOT, "阶段05-数据准备", "数据集")
DATASET_DIR = os.path.join(DATASET_ROOT, DATASET_VERSION)
DOCS_PATH = os.path.join(DATASET_DIR, "clean", "documents.jsonl")
CHUNKS_PATH = os.path.join(DATASET_DIR, "chunks", "chunks.jsonl")
INDEX_PATH = os.path.join(DATASET_DIR, "index", "faiss.index")
VECTOR_MAP_PATH = os.path.join(DATASET_DIR, "index", "vector_map.jsonl")
BUILD_META_PATH = os.path.join(DATASET_DIR, "index", "build_meta.json")
DATASET_META_PATH = os.path.join(DATASET_DIR, "meta", "dataset.json")

# --- 图谱侧输入（只读）---
GRAPH_VERSION = "v2.1_v1_2"
GRAPH_DIR = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", GRAPH_VERSION)
NODES_CSV = os.path.join(GRAPH_DIR, "nodes.csv")
EDGES_CSV = os.path.join(GRAPH_DIR, "edges.csv")
REPLAY_CYPHER = os.path.join(GRAPH_DIR, "replay.cypher")
GRAPH_STATS_PATH = os.path.join(GRAPH_DIR, "graph_stats.json")
HUMAN_CONFIRM_PATH = os.path.join(GRAPH_DIR, "人工确认清单.json")

# T1 的输入指纹清单（T11 用它比对"输入只读"）
INPUT_MANIFEST_PATH = os.path.join(OUTPUT_DIR, "input_manifest.json")

# T1 的输入清单（路径 → 简称），顺序即清单顺序，不得随运行环境变化
INPUT_FILES = [
    ("documents", DOCS_PATH),
    ("chunks", CHUNKS_PATH),
    ("faiss_index", INDEX_PATH),
    ("vector_map", VECTOR_MAP_PATH),
    ("build_meta", BUILD_META_PATH),
    ("dataset_meta", DATASET_META_PATH),
    ("nodes_csv", NODES_CSV),
    ("edges_csv", EDGES_CSV),
    ("replay_cypher", REPLAY_CYPHER),
    ("graph_stats", GRAPH_STATS_PATH),
    ("human_confirmation", HUMAN_CONFIRM_PATH),
]

# 结构化产出的落点（一行一条的 JSONL／CSV，UTF-8 不带 BOM）
OUTPUT_FILES = {
    "input_manifest": INPUT_MANIFEST_PATH,
    "pre_experiment_matrix": os.path.join(OUTPUT_DIR, "pre_experiment_matrix.jsonl"),
    "k_selection": os.path.join(OUTPUT_DIR, "k_selection.json"),
    "per_question_trace": os.path.join(OUTPUT_DIR, "per_question_trace.jsonl"),
    "metrics_pre": os.path.join(OUTPUT_DIR, "metrics_pre.jsonl"),
    "run_manifest": os.path.join(OUTPUT_DIR, "run_manifest.json"),
}

# 题集四件的落点
QUESTION_FILES = {
    "questions": os.path.join(QUESTIONS_DIR, "questions.jsonl"),
    "template": os.path.join(QUESTIONS_DIR, "题目模板.md"),
    "build_script": os.path.join(_THIS_DIR, "build_questions.py"),
    "readme": os.path.join(QUESTIONS_DIR, "说明.md"),
}

# --------------------------------------------------------------------------
# 2. 向量侧口径（第 5 阶段已固化，本阶段只引用、不得更换）
# --------------------------------------------------------------------------
EMBEDDING = {
    "model_name": "BAAI/bge-small-zh-v1.5",
    "revision": "7999e1d3359715c523056ef9478215996d62a620",
    "dim": 512,
    "normalize": True,                 # L2 归一化 + 内积 ＝ 余弦相似度
    "metric": "inner_product",
    # 查询侧不加指令前缀：文档与查询同向编码（《02》第12.4节；硬约束 12）
    "query_instruction": "",
    "max_length": 512,
}

# 语料规模（实测读数；T1 会逐项复核，不一致即失败）
CORPUS = {
    "documents": 709,
    "chunks": 5018,
    "vectors": 5018,
    "token_count_min": 64,
    "token_count_max": 500,
    "token_count_total": 1593125,
}

# --------------------------------------------------------------------------
# 3. 图谱侧口径
# --------------------------------------------------------------------------
# 边表列（9 列，顺序即 CSV 表头）
EDGE_COLUMNS = ["head_id", "relation", "tail_id", "source_doc_id", "source_chunk_id",
                "confidence", "role", "valid_from", "valid_to"]

# 9 条核心关系；EVIDENCED_BY 由程序按 doc_id 生成、**不携带** evidence 三项，
# 也**不产生文本块级候选**（硬约束 14；表 18-F 的 G5 边界）
RELATIONS = [
    "BELONGS_TO", "SUPPLIES", "CUSTOMER_OF", "COMPETES_WITH", "HAS_EXECUTIVE",
    "PARTICIPATES_IN", "ISSUED_BY", "RELATED_TO", "EVIDENCED_BY",
]
EVIDENCED_BY = "EVIDENCED_BY"
SEMANTIC_RELATIONS = [r for r in RELATIONS if r != EVIDENCED_BY]   # 8 条
EVIDENCE_ATTRS = ["source_doc_id", "source_chunk_id", "confidence"]

NODE_LABELS = ["Company", "Person", "Industry", "Institution", "Event", "Policy", "Document"]
EVENT_TYPES = ["业绩", "监管", "股权", "投资并购", "重大合同", "产品", "政策", "重大经营"]
ROLES = ["主体", "合作方", "涉及方", "监管方", "受影响方"]

# "事件三元组"的字段形态（《18》第六节 的格式决策 3：本次定义）
EVENT_TRIPLE_FIELDS = ["event_id", "event_type", "event_time"]

# 图谱规模（实测读数；T1 会逐项复核）
GRAPH_SIZE = {
    "nodes": 2802,
    "edges": 2736,
    "events": 1100,
    "events_without_time": 544,       # 49.5%：D／E 组时间过滤要剔除的规模（硬约束 3）
    "semantic_edges": 1625,
    "replay_cypher_lines": 5561,
    "checks": 20,
    "checks_passed": 18,
}

# --------------------------------------------------------------------------
# 4. 检索参数（K／N／预算：T8 之前为 TBD，读到 None 必须报错退出）
# --------------------------------------------------------------------------
RETRIEVAL = {
    # —— 三项必固化，T8 由预实验落定并回《02》登记 ——
    "N": None,                        # 向量检索候选数量（TBD）
    "K": None,                        # 最终证据集合的文本块上限（TBD）
    "context_token_budget": None,     # Context Token Budget（TBD）
    # —— 预实验网格（硬约束 10）——
    "k_grid": [5, 10, 15],
    "n_grid": [20, 50, 100],
    "selection_rule": "在满足 Context Token Budget 的前提下，取 Complete Evidence Recall@K 饱和的最小 K",
    # —— 时间过滤的空值语义（v2.9 裁定 ①）——
    "time_filter_null_policy": "exclude",     # 显式配置项：exclude／keep，默认 exclude
    # —— 指标分母（硬约束 8）——
    "precision_denominator": "K",             # 恒为 K，候选不足时空缺记未命中
}

# A～E 五组的三个开关取值（《02》第12.6节；硬约束 9：三个开关必须独立）
GROUPS = {
    "A": {"graph_depth": 0, "time_filter": False, "evidence_sort": False},
    "B": {"graph_depth": 1, "time_filter": False, "evidence_sort": False},
    "C": {"graph_depth": 2, "time_filter": False, "evidence_sort": False},
    "D": {"graph_depth": 2, "time_filter": True, "evidence_sort": False},
    "E": {"graph_depth": 2, "time_filter": True, "evidence_sort": True},
}
DEFAULT_GROUP = "C"                    # Method ＝ C 组（《02》第12.5节）

# 三个开关的合法取值域（防止引入第四个可变参数，硬约束 9）
SWITCH_DOMAINS = {
    "graph_depth": [0, 1, 2],
    "time_filter": [False, True],
    "evidence_sort": [False, True],
}

# 证据排序（E 组单变量：只读集合、只改顺序）允许使用的可解释因素（非目标 9）
EVIDENCE_SORT_KEYS = ["entity_match", "evidence_type", "source_publish_time", "graph_relation_type"]

# 相对时间的窗口（天），基准是 data_cutoff_time（《02》第10.3节；硬约束 21）
RELATIVE_TIME_WINDOWS = {"最新": None, "最近": 30, "近期": 90}

# --------------------------------------------------------------------------
# 5. 版本级属性与工具函数
# --------------------------------------------------------------------------
DATA_CUTOFF_TIME = "2026-09-25T23:59:59+08:00"

# 第 7 阶段不做任何大语言模型调用（硬约束 16）；此开关供 T11 在摘除密钥的环境下自证
MODEL_CALLS_ALLOWED = 0


def sha256_file(path: str) -> str:
    """文件的 SHA-256（分块读，避免把大索引一次性读进内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json(obj) -> str:
    """确定性 JSON 序列化：键排序、不留空格差异，供逐字节比对。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """按固定键序写 JSON（缩进 2、结尾换行），供逐字节比对。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def iter_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: str, rows) -> None:
    """一行一条；调用方负责行的顺序（必须确定性）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def read_faiss_index(path: str):
    """按字节流反序列化读 FAISS 索引。

    **不得**用 `faiss.read_index`／`write_index`：它们走 C++ 的 `fopen`，在含中文的
    路径（本项目数据集路径就含中文）下会因 ANSI 代码页失败。本函数沿用
    `代码\\数据准备\\embed.py` 第 127～155 行的同一封装，序列化格式逐字节一致
    （《18》硬约束 13；《17》第6.3节）。
    """
    import faiss
    import numpy as np

    with open(path, "rb") as f:
        raw = f.read()
    arr = np.frombuffer(bytearray(raw), dtype=np.uint8)
    return faiss.deserialize_index(arr)


def require_fixed(name: str):
    """读取 T8 之前仍为 TBD 的三项参数；为 None 即报错退出，不用默认值兜底。"""
    value = RETRIEVAL.get(name)
    if value is None:
        raise SystemExit(
            "参数 %s 仍为 TBD（第 7 阶段预实验 T8 固化后回填 config.RETRIEVAL，"
            "并回《02》第12.7节 第一步与 第12.4节 登记）；不得用默认值兜底。" % name)
    return value
