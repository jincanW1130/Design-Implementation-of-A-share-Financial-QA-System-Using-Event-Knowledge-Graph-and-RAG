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
* 四项 TBD（K／N／Context Token Budget／g）由本阶段预实验固化并回《02》登记：
  《18-第7阶段任务书（RAG检索系统）》第2.4节、硬约束 10、T8。
* 空值语义与相对时间基准：《02》第11.3节、第10.3节，v2.9 裁定 ① 与 ②。

**K／N／Context Token Budget／g 在 T8 之前一律为 `None`（TBD）**：脚本读到 `None`
必须报错退出，不得用默认值兜底——否则预实验的"饱和"会在不同输入之间漂移。

*第 7 阶段的中途修订（2026-09-27，作者裁定「甲案」）*：`RETRIEVAL` 新增
`graph_retention_share`（＝分层保留顺序里的 `g`），依据《10-系统总体设计（第四阶段）》
第4.6.4节～第4.6.6节（＝《02》第12.7节）与《18》第2.3节、第2.4节、硬约束 10。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys

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
    # —— 三项必固化：2026-09-27 由 T8 预实验落定，回《02》v3.1 第12.4节 与 第12.7节 第一步 登记 ——
    # 定值记录（T8；30 题预实验问题集、C 组＝Method、网格 K ∈ {5,10,15} × N ∈ {20,50,100}）：
    #   K = 10：网格中满足 gold 约束（本题集逐题 gold 证据数最大 7，验收第 25 行）的最小 K；
    #     在同一 Context Token Budget=3600 下把 K 从 10 提到 15，Complete Evidence Recall@K
    #     不再提升（0.5667 → 0.5667，相邻档增量 Δ=0.0000），故 K=10 即「满足预算的前提下
    #     饱和的最小 K」；K=5 被 gold 约束排除。
    #   N = 20：K 固定后网格三档的 Complete Evidence Recall@K 相同（0.5667／0.5667／0.5667），
    #     按「取最小 N」定值；N ≥ K 成立（20 ≥ 10）。
    #   Context Token Budget = 3600：规则＝基准格（K=10／N=20）在第一轮非约束预算下逐题
    #     **文本块 token** 占用中位数 3191.5 × 1.10 固定余量、向上取整到整百；图谱路径与
    #     事件三元组不单独预留额度、与文本块共用同一上限（超限先裁与问题实体无关的远端图谱路径）。
    #   依据：《18》第九节 T8、第2.4节、第五节 硬约束 10、第八节 第 20／21／22 行；执行证据
    #     （9 格网格、两轮读数、饱和判定、预算规则的敏感性与 g 曲线）落盘在
    #     阶段07-RAG检索系统\检索产出\pre_experiment_matrix.jsonl 与 k_selection.json。
    "N": 20,                          # 向量检索候选数量（T8 定值）
    "K": 10,                          # 最终证据集合的文本块上限（T8 定值）
    "context_token_budget": 3600,     # Context Token Budget（T8 定值）
    # —— g：图谱侧新增块在最终证据集合中的「分层保留份额」（T8 预实验定值，回《02》登记）——
    # 定位：**全局固化量**——A～E 五组取**同一值**、**不进任何开关**（不在 GROUPS、不在
    #   SWITCH_DOMAINS）、不随组变化，因此不破坏"三开关只差一个变量"的单变量归因；它只决定
    #   第③／④步「分层保留顺序」的第二层名额（第一层＝向量侧候选按原始排名升序取前 K−g 个，
    #   第二层＝图谱侧新增块按对问题的向量相似度降序（**并列按 chunk_id 升序**）至多 g 个，
    #   第三层＝向量侧剩余候选回填）。并列规则是确定性（逐字节可复现）的必要条件：
    #   相似度打平时只有 `chunk_id` 升序能给出唯一顺序（《02》第12.4节 与 第12.7节 第三步／
    #   第四步；《10》第4.6.4节 与 第4.6.6节；《18》第2.3节 与 硬约束 10）。
    # 选择规则（2026-09-27 v3.2 加固：含下限 1）：取满足「四项指标均不劣于 g=0」的 g 中的最大值，
    #   **且不低于下限 1**（g ≥ 1）——四项指标 ＝ Recall@K／Precision@K／MRR／Complete Evidence Recall@K。
    #   下限 1 的意义：**保证图谱侧证据在每道题上至少有一个名额**，从而维持 H1／H2 的可检验性
    #   （g = 0 会使 C 组与 A 组在最终证据集合上**结构性相等**，H1／H2 在定义上不可检验——
    #   可检验性属设计约束，不是指标比较的副产品）。**若在数据上所有 g ≥ 1 都劣于 g = 0，
    #   仍取 g = 1**，并把「在该预算下图谱侧证据未能体现出不劣」如实登记为**已知限制**，
    #   而**不是**把 g 降到 0。
    # 口径：《10》第4.6.4节 第三步与第四步、第4.6.5节、第4.6.6节（2026-09-27 裁定「甲案」）；
    #   《02》第12.7节 第一步、第12.4节；《18》第2.3节、第2.4节、硬约束 10。
    # **g = 0 退化为原字面口径**（向量侧在前、图谱侧新增块追加在后），用于对照与回归。
    # 定值记录（2026-09-27，T8 预实验的 g 曲线，取值前为 None＝TBD）：在参考格
    #   K=10／N=20／Context Token Budget=3000 上，五项 g ∈ {0,1,2,3,5} 的实测为——
    #   g=0：Recall 0.6548／Precision 0.1333／MRR 0.6556／CER 0.5667，图谱侧新增块入集 0 个；
    #   g=1：四项与 g=0 相同（不劣），入集 3 个；**g=2：Recall 0.6614／Precision 0.1367／
    #   MRR 0.6556／CER 0.5667（四项均不劣于 g=0），入集 14 个**；g=3 起 CER 掉到 0.5333（劣化）；
    #   g=5 进一步劣化（Recall 0.6206、CER 0.5000）。按选择规则（2026-09-27 v3.2 加固后含下限 1）
    #   取"不劣于 g=0 的最大 g、且不低于 1"＝**2**。
    #   T8 若把 K／N／预算的选定值定在别的格上，按同一条规则在该格上复算并回《02》登记。
    # 复算记录（2026-09-27，T8 在**选定格** K=10／N=20／Context Token Budget=3600 上复算）：
    #   g=0：0.6614／0.1367／0.6556／0.5667、图谱侧新增块入集 0 个（0／30 题）；
    #   g=1：0.6773／0.1433／0.6556／0.5667、入集 23 个（23／30 题）——四项不劣于 g=0；
    #   **g=2：0.6840／0.1467／0.6556／0.5667、入集 53 个（29／30 题）——四项均不劣于 g=0**；
    #   g=3：CER@10 掉到 0.5333（劣化）；g=5：0.6206／0.1267／0.6500／0.5000（劣化）。
    #   按同一条规则（含下限 1）取「不劣于 g=0 的最大 g、且不低于 1」＝**2**，与暂定值一致，
    #   故本次不改写本行；
    #   执行证据见 检索产出\k_selection.json 的 evidence.g_curve。
    # 留痕（2026-09-28）：以上 g 曲线示例读数按**第三方复核扩增 PE-26 的 gold（2 块→4 块）之前**的题集记录；
    #   现行产物为 g=2 → 0.6923／0.1500／0.6593／0.5667（入集 53 个；见 k_selection.json 的
    #   evidence.g_curve 与 pre_experiment_matrix.jsonl）。
    # 复算的敏感性（同一份 k_selection.json 的 evidence.budget_sensitivity 亦已登记；v3.2 起按
    #   《02》第1.2节 v3.2 行登记为**已知限制**）：预算规则唯一自由量是余量比例。B-19 复核
    #   （2026-09-29，以**当前产物**为准）：五档余量（0%／5%／10%／15%／20%，对应预算
    #   3200／3400／3600／3700／3900）下 g=2 四项**全不劣于** g=0（budget_sensitivity 五行的
    #   g2_not_worse_than_g0 皆 True）——**当前题集五档全 True**，即本题集上不存在「余量 ≥15%
    #   时 g=2 劣化」；原文所引「g=2 的 MRR 被 1 道题的位次变化拉低（0.6556 < 0.6589，低 0.003）」
    #   是**重绑 gold 之前的旧读数**，已与现产物不符，故删去该条断言。
    #   保留其一般形式：**已知限制**——若在别的预算下所有 g ≥ 1 都劣于 g = 0，仍取 g = 1 并把
    #   「在该预算下图谱侧证据未能体现出不劣」如实登记为已知限制，而**不是**把 g 降到 0。
    #   该敏感性是预实验集规模下的**噪声量级**，不构成「图谱无贡献」的证据；
    #   **待 T12 一并登记进产出文档《19》的「已知限制」一节**。故预算规则与 g 的取值须一起读，
    #   不得只引其一。
    # 读到 None（TBD）即报错退出，不得用默认值兜底（`require_fixed`）。
    "graph_retention_share": 2,
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

# --------------------------------------------------------------------------
# 6. 验收硬守卫：镜像重跑期间拒绝任何网络路径与凭据路径（《18》硬约束 16）
# --------------------------------------------------------------------------
# 只摘环境变量不够：只要链上任何一处（含将来新加的脚本、第三方依赖的回退分支）去取密钥或
# 直接发请求，「0 次调用」就只是**声明**而不是**保证**。`工具\验收第7阶段.py` 的镜像重跑会置
# `STAGE7_FORBID_MODEL_CALLS=1`，本文件在 **import 时**就把它变成硬约束（照第 6 阶段
# `代码\抽取与图谱\config.py` 的 `STAGE6_FORBID_MODEL_CALLS` 哨兵做法）：
#   ① 凭据路径：环境里只要还残留任何凭据类变量名（只匹配名字、不读取取值）→ 直接抛错；
#   ② 网络路径：装一个审计钩子，任何 socket／HTTP 连接尝试 → 直接抛错。
# 哨兵未置位时（正常运行、第 8 阶段接答案生成模型之前）本守卫整体不生效。
FORBID_MODEL_CALLS_ENV = "STAGE7_FORBID_MODEL_CALLS"
_CRED_NAME_PAT = re.compile(
    r"(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|ZHIPU|OPENAI|"
    r"DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)", re.IGNORECASE)
_NET_AUDIT_EVENTS = ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
                     "urllib.Request", "http.client.connect", "ftplib.connect",
                     "smtplib.connect", "imaplib.open", "poplib.connect", "telnetlib.Telnet")


def _guard_forbidden_model_calls() -> None:
    """哨兵：镜像重跑期间把「0 次大语言模型／外部接口调用」从声明变成硬保证。"""
    if (os.environ.get(FORBID_MODEL_CALLS_ENV) or "").strip() != "1":
        return
    cred = sorted(name for name in os.environ if _CRED_NAME_PAT.search(name))
    if cred:
        raise RuntimeError(
            "%s=1：子进程环境里仍残留凭据类变量 %s（只报变量名、不读任何取值）——"
            "镜像重跑**拒绝凭据路径**，验收脚本必须先把它们摘掉。"
            % (FORBID_MODEL_CALLS_ENV, "、".join(cred)))

    def _audit_hook(event, _args):
        if event in _NET_AUDIT_EVENTS:
            raise RuntimeError(
                "%s=1：拦截到网络路径 %s —— 第 7 阶段检索链必须 0 次大语言模型／外部接口调用，"
                "镜像重跑**拒绝网络路径**。" % (FORBID_MODEL_CALLS_ENV, event))

    sys.addaudithook(_audit_hook)


_guard_forbidden_model_calls()


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


# --------------------------------------------------------------------------
# 7. g 的取值域与显式校验（2026-09-28 第二轮复审 B-16 整改）
# --------------------------------------------------------------------------
# g 是**全局固化量**（《02》第12.4节／第12.7节 第一步、《18》第2.3节、硬约束 10），
# 现行选择规则自 v3.2 起含**硬下限 1**：1 ≤ g ≤ K。第 8 阶段将**直接调用库函数**
# （`pipeline.PipelineRunner.run`），因此取值域必须在库里**显式校验**，越界即抛错——
# 不许再像修订前那样由 `max(0, int(g))` 静默夹取（g=-1 当作 0、g≥K 得"图谱侧优先"）。
# g = 0 是《02》第12.7节 与《19》「已知限制」登记的**原字面口径退化值**，只保留在
# **显式命名**的退化回归通道里（`pipeline.PipelineRunner.run_legacy_g0()` 与
# 低层的 `retention_key()`／`plan_graph_layer()`），不再能从运行入口或命令行直接传。
GRAPH_SHARE_FLOOR = 1


def check_graph_share(g, k, where: str = "") -> int:
    """g 的显式校验：合法域 `GRAPH_SHARE_FLOOR ≤ g ≤ K`（1 ≤ g ≤ K），越界即抛错。"""
    g, k = int(g), int(k)
    if not (GRAPH_SHARE_FLOOR <= g <= k):
        raise ValueError(
            "%sg 越界：收到 g=%d、K=%d；合法域为 %d ≤ g ≤ K（g 是全局固化量，"
            "由 T8 预实验定值并回《02》登记）。g=0 只是「原字面口径」的**退化回归值**，"
            "须走显式通道（pipeline.PipelineRunner.run_legacy_g0() 或命令行 "
            "--legacy-g0-degeneration），不得从运行入口／命令行直接传，也不得静默夹取。"
            % ((where + "：") if where else "", g, k, GRAPH_SHARE_FLOOR))
    return g
