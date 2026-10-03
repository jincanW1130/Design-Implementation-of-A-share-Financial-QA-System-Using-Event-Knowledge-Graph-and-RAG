# -*- coding: utf-8 -*-
"""代码\\问答\\config.py —— 第 8 阶段（智能问答系统）答案生成层组件的**唯一参数来源**。

本文件只放参数与读取方式，**不放任何密钥取值**。脚本内不得写死模型名、端点、路径、
温度、Prompt 版本、日期或阈值，一律经本文件读取（沿用 `代码\\数据准备\\config.py`、
`代码\\抽取与图谱\\config.py`、`代码\\检索\\config.py` 已确立的做法）。

参数来源（只引用、不新增、不改名）：

* 答案生成口径（模型、版本、端点、temperature、Prompt 版本）：《21-第8阶段任务书
  （智能问答系统）》第2.4节 作者裁定、第五节 硬约束 2／3；《10-系统总体设计（第四阶段）》
  第4.6.8节 表 4-12（Prompt 七区块，v1.0）。
* `max_tokens`（答案侧生成配置，非实验变量）：**《21》v1.3 第五节 硬约束 2** 的扩写段
  （推理型模型、推理与正文共用该上限、2048／4096 的实测截断、16384 的实测余量、端点接受
  16384／32768），以及 v1.3 修订记录与配套的**空正文重试规则**；证据文件见下方
  `ANSWER["max_tokens"]` 旁的旁注。
* 四项定值 K／N／Context Token Budget／g：**从 `代码\\检索\\config.py` 导入**，不在本文件
  复制字面量（《21》第五节 硬约束 1、验收 B2）。目录名「检索」与模块名冲突，故用
  `importlib` 以**文件路径**加载，不走 `sys.path`。
* 输入八项与只读纪律：《21》第三节；产出落点：《21》第4.3节。
* 密钥读取方式：沿用第 6 阶段（环境变量优先、其次与 `代码\\抽取与图谱\\config.py` 同目录的
  `config.local.json`）；《21》第五节 硬约束 19、第2.5节 第 2 条。
* 镜像重跑守卫：照第 7 阶段 `STAGE7_FORBID_MODEL_CALLS` 做成
  `STAGE8_FORBID_MODEL_CALLS`（《21》第2.5节 第 3 条、验收 G1）。

**模型 id 只认自定义环境变量**（`STAGE8_ANSWER_MODEL`／`STAGE8_SELECTION_MODEL`）：
运行环境的通用变量 `LLM_MODEL`／`LLM_BASE_URL` 是**别处**的路由变量，本文件**刻意不读**——
第 6 阶段曾因撞名 `LLM_MODEL` 让 709 篇抽取缓存全部失配。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys

# 控制台默认 GBK：本组件的所有脚本在导入时即把 stdout／stderr 切到 UTF-8，
# 否则中文输出会被按 GBK 解码（第 5 阶段踩过的坑）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

# --------------------------------------------------------------------------
# 1. 路径
# --------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

STAGE_DIR = os.path.join(ROOT, "阶段08-智能问答系统")
OUTPUT_DIR = os.path.join(STAGE_DIR, "问答产出")      # 《21》第4.3节 的结构化产出
WORK_DIR = os.path.join(STAGE_DIR, "_工作底稿")        # 勘察与试跑留痕（不入库）

# --- 输入（《21》第三节 的八项；一律只读）---
TRACE_PATH = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "per_question_trace.jsonl")
INPUT_MANIFEST_PATH = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "input_manifest.json")
STAGE7_RUN_MANIFEST_PATH = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "run_manifest.json")
QUESTIONS_PATH = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集", "questions.jsonl")

DATASET_VERSION = "v2.1"
DATASET_DIR = os.path.join(ROOT, "阶段05-数据准备", "数据集", DATASET_VERSION)
CHUNKS_PATH = os.path.join(DATASET_DIR, "chunks", "chunks.jsonl")
DOCUMENTS_PATH = os.path.join(DATASET_DIR, "clean", "documents.jsonl")
DATASET_META_PATH = os.path.join(DATASET_DIR, "meta", "dataset.json")

# **2026-10-02 作者裁定：交付口径由 v1.2 切换为 v1.3**（原候选口径转正；理由与代价见
# 《16》第 9.5 节、《10》第4.5.4节 与《02》修订记录）。v1.2 归档保留、可原样复现
# （抽取侧用 --profile v21_v1_2，产物仍在 图谱导出\v2.1_v1_2\、一个字节未动）。
GRAPH_VERSION = "v2.1_v1_3"
GRAPH_DIR = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", GRAPH_VERSION)
NODES_CSV = os.path.join(GRAPH_DIR, "nodes.csv")
EDGES_CSV = os.path.join(GRAPH_DIR, "edges.csv")
GRAPH_STATS_PATH = os.path.join(GRAPH_DIR, "graph_stats.json")

# T1 的输入清单（简称 → 路径），顺序即清单顺序，不得随运行环境变化
INPUT_FILES = [
    ("per_question_trace", TRACE_PATH),
    ("stage7_input_manifest", INPUT_MANIFEST_PATH),
    ("stage7_run_manifest", STAGE7_RUN_MANIFEST_PATH),
    ("documents", DOCUMENTS_PATH),
    ("chunks", CHUNKS_PATH),
    ("dataset_meta", DATASET_META_PATH),
    ("nodes_csv", NODES_CSV),
    ("edges_csv", EDGES_CSV),
    ("graph_stats", GRAPH_STATS_PATH),
    ("questions", QUESTIONS_PATH),
]

# --- 产出（《21》第4.3节）---
INPUT_MANIFEST_OUT_PATH = os.path.join(OUTPUT_DIR, "input_manifest.json")     # T1
SELECTION_MATRIX_PATH = os.path.join(OUTPUT_DIR, "selection_matrix.jsonl")    # T2
SELECTION_DECISION_PATH = os.path.join(OUTPUT_DIR, "selection_decision.json")  # T2
PROMPT_SNAPSHOT_PATH = os.path.join(OUTPUT_DIR, "prompt_snapshot.json")       # T3
ANSWER_TRACE_PATH = os.path.join(OUTPUT_DIR, "answer_trace.jsonl")            # T8（后续子任务）
QA_RECORDS_PATH = os.path.join(OUTPUT_DIR, "qa_records.jsonl")                # T8（后续子任务）
RUN_MANIFEST_PATH = os.path.join(OUTPUT_DIR, "run_manifest.json")             # T9（后续子任务）

# --------------------------------------------------------------------------
# 2. 答案生成侧冻结口径（《21》第2.4节 作者裁定；第五节 硬约束 2／3）
# --------------------------------------------------------------------------
# model_version 的取值口径 ＝ 端点 /models 实测列出的 id（《21》第五节 硬约束 2），
# 不是发行版本号；三值与《02》v3.3 登记逐字一致。
ANSWER = {
    "model_name": "deepseek-flash",
    "model_version": "deepseek-flash",
    "endpoint": "https://api.deepseek.com/v1",
    "temperature": 0,
    # --- max_tokens 的定值依据（《21》v1.3 第五节 硬约束 2，决策者 2026-09-29 实测）---
    # 本端点上的模型是**推理型**（响应带 reasoning_content），**推理 token 与正文 token 共用**
    # 这一个上限：上限给小了，推理载荷会把正文预算吃光，模型返回空正文（不是模型不会答，
    # 是配置不够）。故该值是**答案侧生成配置**（《02》第12.4节 只冻结模型、版本、temperature、
    # Prompt 版本与四项检索定值，不冻结输出上限），**A～E 五组同值**，不随组变化。
    # 实测（证据：_工作底稿\决策者核验\max_tokens_复测.json 与 max_tokens_上限复测.json）：
    #   * max_tokens=2048 → 必空（如 PE-14 推理 2367 字吃满 2048、finish_reason=length）；
    #   * max_tokens=4096 → 仍截断（PE-14 reasoning 6896 字、content 为空、finish_reason=length）；
    #   * max_tokens=16384 → 最吃推理的 PE-14 也稳定 finish_reason=stop 且正文非空
    #     （completion 2041；PE-04 completion 2888），余量充足；
    #   * 端点亦接受 16384／32768（32768 实测通过，但不取更大值以免无谓拉长生成）。
    # 故取 16384。T2 小样本试跑（--limit 2）曾把 1024 提到 2048（《21》v1.2 修订记录 ③），
    # v1.3 按其修订记录由 2048 升到 16384；**三候选同值**（仍满足「只换模型」的单变量口径）。
    "max_tokens": 16384,
    "timeout_seconds": 300,
    "prompt_version": "v1.0",
}

# 三模型对照候选（《21》第2.5节 实测勘察；T2 只换模型、其余全同）
MODEL_CANDIDATES = [
    {
        "key": "deepseek-flash",
        "provider": "deepseek",
        "model": "deepseek-flash",
        "endpoint": ANSWER["endpoint"],           # 同一端点，不复制字面量
        "role": "作者裁定候选（冻结值）",
        "key_source": "环境变量 LLM_API_KEY 优先；其次 代码\\抽取与图谱\\config.local.json 的 api_key 字段",
    },
    {
        "key": "deepseek-v4-pro",
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "endpoint": ANSWER["endpoint"],
        "role": "同端点对照",
        "key_source": "同上（DeepSeek 同端点，同一密钥来源）",
    },
    {
        "key": "glm-5.3-flash",
        "provider": "zhipu",
        "model": "glm-5.3-flash",
        "endpoint": "https://open.bigmodel.cn/api/paas/v4",
        "role": "第三方对照",
        "key_source": "环境变量 ZHIPU_API_KEY 优先；其次 代码\\抽取与图谱\\config.local.json 的 zhipu_api_key 字段",
    },
]

# 模型 id 只认这两个自定义环境变量；LLM_MODEL／LLM_BASE_URL 是运行环境自身的路由变量，
# **刻意不读**（第 6 阶段的撞名事故）。
ANSWER_MODEL_ENV = "STAGE8_ANSWER_MODEL"
SELECTION_MODEL_ENV = "STAGE8_SELECTION_MODEL"

# T2 选型判定的阈值与规则（**事先写明**，避免看到结果再定；《21》第2.5节 第 4 条改判规则）
SELECTION = {
    "frozen_candidate": "deepseek-flash",          # 作者裁定候选（对照基准）
    "consecutive_failures_threshold": 3,           # 规则①：连续 3 次请求失败
    # 规则②：机检读数「显著劣于」对照的阈值——按百分点的绝对差判定，
    #   劣化量 ≥ 该阈值即触发；四项读数＝引用越界率／日期越界率／空答案率（越低越好）
    #   与图谱标记一致率（越高越好）。
    "machine_check_margin": 0.10,
    "mean_latency_limit_seconds": 30.0,            # 规则③：30 题平均时延上限
}

# Moonshot／kimi-k3 的排除证据（《21》第2.5节 第 1 条表；决策者的勘察原始输出）
MOONSHOT_EXCLUSION = {
    "provider": "moonshot",
    "model": "kimi-k3",
    "endpoint": "https://api.moonshot.cn/v1",
    "reason": "该模型只接受 temperature=1，与《02》第12.4节 冻结的 temperature=0 直接冲突",
    "evidence_path": os.path.join(WORK_DIR, "勘察_答案生成模型_真实载荷.json"),
}

# --------------------------------------------------------------------------
# 2.1 生成与记录层的固定口径（《21》第六节 格式决策 4／5；第五节 硬约束 12／13）
# --------------------------------------------------------------------------
# 标识生成规则（格式决策 4）：`question_id`／`answer_id` 由**确定性规则**生成，
# 与题集 `PE-nn` 一一对应（`PE-07` → `Q-007`／`A-007`）；**不使用随机数或时间戳**。
QUESTION_ID_PREFIX = "Q-"
ANSWER_ID_PREFIX = "A-"
ID_DIGITS = 3                       # `Q-001`… 的位宽
# 题集里没有的题（`--question` 自定义问题，不属于 30 题预实验集）用的确定性标识
CUSTOM_QUESTION_ID = "Q-CUSTOM"
CUSTOM_ANSWER_ID = "A-CUSTOM"

# `session_id` 由命令行给定、缺省为固定值（格式决策 4；《21》第五节 硬约束 16 第一版不启用登录）
DEFAULT_SESSION_ID = "S-001"

# 开放式分析问题的识别判据（《21》第五节 硬约束 12）：**按题集的标注字段 `task_type` 判**，
# 不得靠关键词猜。30 题预实验集的 `task_type` 实测取值为 事实型／关系型／事件型，**无开放式题**，
# 故 D6 在本阶段按「不适用」通过（依据由程序从题集现算并打印，不写死结论）。
OPEN_ENDED_TASK_TYPES = ("开放式", "开放型", "分析型", "开放式分析")


def identifiers_for(qid: str) -> tuple:
    """按格式决策 4 的**确定性规则**由题集 `qid` 推出 `(question_id, answer_id)`。

    `PE-nn` → `Q-0nn`／`A-0nn`（与题集一一对应）；题集之外的题（`--question` 自定义问题）
    → `Q-CUSTOM`／`A-CUSTOM`。**不参与随机数或时间戳**。
    """
    import re
    m = re.fullmatch(r"PE-(\d+)", str(qid or "").strip())
    if not m:
        return CUSTOM_QUESTION_ID, CUSTOM_ANSWER_ID
    n = int(m.group(1))
    return ("%s%0*d" % (QUESTION_ID_PREFIX, ID_DIGITS, n),
            "%s%0*d" % (ANSWER_ID_PREFIX, ID_DIGITS, n))

# --------------------------------------------------------------------------
# 3. 检索侧四项定值：从 代码\\检索\\config.py **导入**（不复制字面量）
# --------------------------------------------------------------------------
_RETRIEVAL_CONFIG_PATH = os.path.join(ROOT, "代码", "检索", "config.py")


def _load_retrieval_config():
    """以文件路径加载 `代码\\检索\\config.py`。

    目录名「检索」不是合法模块名，且与「检索」在 `sys.path` 上可能的重名冲突，故用
    `importlib.util.spec_from_file_location` 加载，**不动 `sys.path`**（《21》第五节 硬约束 1）。
    """
    if not os.path.isfile(_RETRIEVAL_CONFIG_PATH):
        raise SystemExit("检索侧参数来源不存在：%s" % _RETRIEVAL_CONFIG_PATH)
    spec = importlib.util.spec_from_file_location("_stage8_retrieval_config",
                                                  _RETRIEVAL_CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RET = _load_retrieval_config()
RETRIEVAL = getattr(_RET, "RETRIEVAL", None)
if not isinstance(RETRIEVAL, dict):
    raise SystemExit("检索侧 config 里没有可用的 RETRIEVAL 常量：%s" % _RETRIEVAL_CONFIG_PATH)


def _need(key: str):
    """从检索侧 RETRIEVAL 取一项定值；读到 None／缺失即报错退出，**不得兜底**。"""
    value = RETRIEVAL.get(key)
    if value is None:
        raise SystemExit(
            "检索侧 config.RETRIEVAL[%r] 为 None／缺失（TBD）——第 8 阶段直接从第 7 阶段"
            "导入，不得用默认值兜底；请先在第 7 阶段固化并回《02》登记。" % key)
    return value


# 四项定值（《02》第12.4节／第12.7节 第一步）
K = _need("K")                                   # 最终证据集合的文本块上限
N = _need("N")                                   # 向量检索候选数量
CONTEXT_TOKEN_BUDGET = _need("context_token_budget")
G = _need("graph_retention_share")

# 判定数据集版本级属性（Prompt 第 2 区块注入）与相对时间基准
DATA_CUTOFF_TIME = getattr(_RET, "DATA_CUTOFF_TIME", None)
if not DATA_CUTOFF_TIME:
    raise SystemExit("检索侧 config.DATA_CUTOFF_TIME 缺失——不得兜底。")

# --------------------------------------------------------------------------
# 3.1 相对时间窗口规则（《21》第五节 硬约束 10 第③条／硬约束 11；《02》第10.3节）
# --------------------------------------------------------------------------
# 「最新／最近／近期」一律按 event_time 判定、基准是 data_cutoff_time：「最近」＝截止前 30 天、
# 「近期」＝前 90 天。窗口表与检索侧同源，**从 代码\检索\config.py 导入**，本文件不复制字面量
# （硬约束 1／11；「最新」的天数为 None 表示「基准日当天」）。
RELATIVE_TIME_WINDOWS = getattr(_RET, "RELATIVE_TIME_WINDOWS", None)
if not isinstance(RELATIVE_TIME_WINDOWS, dict) or not RELATIVE_TIME_WINDOWS:
    raise SystemExit("检索侧 config.RELATIVE_TIME_WINDOWS 缺失——不得兜底。")


def cutoff_date():
    """`data_cutoff_time` 的日期部分（`datetime.date`）；不写死日期。"""
    from datetime import date
    return date.fromisoformat(DATA_CUTOFF_TIME[:10])


def window_endpoint_dates():
    """由 `data_cutoff_time` 按窗口规则**确定性推出**的判定区间端点日期集合。

    用于《21》第五节 硬约束 10 的第③条来源（日期来源可核）：对每条窗口规则
    （「最近」＝前 30 天、「近期」＝前 90 天；天数为 None 表示基准日当天）给出端点。
    """
    from datetime import timedelta
    base = cutoff_date()
    out = set()
    for days in RELATIVE_TIME_WINDOWS.values():
        out.add(base if days is None else base - timedelta(days=int(days)))
    return out

# 实测规模的权威来源（T1 复核用）——仍从检索侧 config 导入，不复制字面量
CORPUS = getattr(_RET, "CORPUS", None)
GRAPH_SIZE = getattr(_RET, "GRAPH_SIZE", None)
EXPECTED_SCALE = {
    "documents": (CORPUS or {}).get("documents"),
    "chunks": (CORPUS or {}).get("chunks"),
    # 图谱 CSV 的规模口径＝**不含表头**的数据行数（检索侧 GRAPH_SIZE 的登记口径）
    "nodes_excl_header": (GRAPH_SIZE or {}).get("nodes"),
    "edges_excl_header": (GRAPH_SIZE or {}).get("edges"),
}
for _k, _v in EXPECTED_SCALE.items():
    if _v is None:
        raise SystemExit("检索侧 config 缺 %s 的登记规模——不得兜底。" % _k)
del _k, _v

# --------------------------------------------------------------------------
# 4. 固定表守卫：读到 TBD／None 即报错退出
# --------------------------------------------------------------------------
FIXED = {
    "model_name": ANSWER["model_name"],
    "model_version": ANSWER["model_version"],
    "endpoint": ANSWER["endpoint"],
    "temperature": ANSWER["temperature"],
    "max_tokens": ANSWER["max_tokens"],
    "timeout_seconds": ANSWER["timeout_seconds"],
    "prompt_version": ANSWER["prompt_version"],
    "K": K,
    "N": N,
    "context_token_budget": CONTEXT_TOKEN_BUDGET,
    "graph_retention_share": G,
    "dataset_version": DATASET_VERSION,
    "data_cutoff_time": DATA_CUTOFF_TIME,
}


def require_fixed(name: str):
    """读取固定表里的一项；值为 None／空串／"TBD" 即报错退出，不用默认值兜底。"""
    if name not in FIXED:
        raise SystemExit("固定表里没有 %r（合法名：%s）" % (name, "、".join(sorted(FIXED))))
    value = FIXED[name]
    if value is None or (isinstance(value, str) and value.strip() in ("", "TBD")):
        raise SystemExit(
            "固定项 %r 仍为 TBD（《02》第12.4节 固定表）；冻结后方可使用，不得用默认值兜底。" % name)
    return value


# --------------------------------------------------------------------------
# 5. 镜像重跑守卫（《21》第2.5节 第 3 条；验收 G1）
# --------------------------------------------------------------------------
FORBID_MODEL_CALLS_ENV = "STAGE8_FORBID_MODEL_CALLS"


def model_calls_forbidden() -> bool:
    """`STAGE8_FORBID_MODEL_CALLS=1` 时为真；调用方在发请求前必须检查并抛错。"""
    return (os.environ.get(FORBID_MODEL_CALLS_ENV) or "").strip() == "1"


def assert_model_calls_allowed(where: str = "") -> None:
    """发请求前的硬守卫：哨兵置位时禁止任何模型调用（装配层仍须跑通并落 Prompt 文本）。"""
    if model_calls_forbidden():
        raise SystemExit(
            "%s%s=1：镜像重跑期间禁止任何答案生成模型调用（装配层仍须跑通）。"
            % ((where + "：") if where else "", FORBID_MODEL_CALLS_ENV))


# --------------------------------------------------------------------------
# 6. 密钥读取（不写死、不回显、不入库、不进日志；《21》第五节 硬约束 19）
# --------------------------------------------------------------------------
# 与 代码\抽取与图谱\config.py 同目录的本地配置（已在 .gitignore 里）
LOCAL_CONFIG_PATH = os.path.join(ROOT, "代码", "抽取与图谱", "config.local.json")

# provider → 环境变量名（按顺序取第一个非空者）
KEY_ENV_NAMES = {
    "deepseek": ("LLM_API_KEY", "DEEPSEEK_API_KEY"),
    "zhipu": ("ZHIPU_API_KEY", "GLM_API_KEY"),
    "moonshot": ("MOONSHOT_API_KEY", "KIMI_API_KEY"),
}
# provider → config.local.json 的字段名
KEY_LOCAL_FIELDS = {
    "deepseek": ("api_key",),
    "zhipu": ("zhipu_api_key",),
    "moonshot": ("kimi_api_key",),
}


def _read_local_config() -> dict:
    if not os.path.isfile(LOCAL_CONFIG_PATH):
        return {}
    try:
        with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def api_key(provider: str, local: dict | None = None) -> str:
    """取指定供应商的密钥：环境变量优先，其次本地 config.local.json。

    返回值**只允许**用于请求头，**不得**打印、写盘或写日志（打印只允许「可用／不可用」）。
    缺失即抛错退出。供应商不在表里也抛错（不猜、不回退到别的 provider 的密钥）。
    """
    provider = (provider or "").strip().lower()
    if provider not in KEY_ENV_NAMES:
        raise SystemExit("未知的密钥供应商 %r；已知：%s"
                         % (provider, "、".join(sorted(KEY_ENV_NAMES))))
    for name in KEY_ENV_NAMES[provider]:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    cfg = _read_local_config() if local is None else local
    for field in KEY_LOCAL_FIELDS[provider]:
        value = cfg.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise SystemExit(
        "供应商 %r 的密钥不可用：环境变量 %s 均未置位，且 %s 里 %s 字段为空。"
        "密钥不写死、不回显；请先配置后重跑。"
        % (provider, "／".join(KEY_ENV_NAMES[provider]), LOCAL_CONFIG_PATH,
           "／".join(KEY_LOCAL_FIELDS[provider])))


def api_key_available(provider: str) -> bool:
    """只回答「可不可用」，**不返回也不打印**密钥取值。"""
    try:
        return bool(api_key(provider))
    except SystemExit:
        return False


def resolve_model(kind: str) -> str:
    """模型 id 解析：`kind ∈ {"answer", "selection"}`。

    只认 `STAGE8_ANSWER_MODEL`／`STAGE8_SELECTION_MODEL`；**刻意不读** `LLM_MODEL`
    （运行环境自身的路由变量，撞名会让缓存与实验口径一起失配）。
    """
    env_name = {"answer": ANSWER_MODEL_ENV, "selection": SELECTION_MODEL_ENV}.get(kind)
    if env_name is None:
        raise SystemExit("resolve_model 的 kind 只能是 'answer' 或 'selection'，收到 %r" % kind)
    override = (os.environ.get(env_name) or "").strip()
    if override:
        return override
    if kind == "answer":
        return require_fixed("model_name")
    # 选型实验的缺省「本题候选」＝作者裁定候选
    return require_fixed("model_name")


# --------------------------------------------------------------------------
# 7. 通用工具（与检索侧同一套写法，避免脚本各写一份）
# --------------------------------------------------------------------------
def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: str, obj) -> None:
    """按固定键序写 JSON（缩进 2、结尾换行、sort_keys），供逐字节比对。"""
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
    """一行一条；调用方负责行的顺序（必须确定性），JSON 键排序、无多余空格。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")) + "\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
# 8. 自检
# --------------------------------------------------------------------------
def selftest() -> int:
    print("=" * 72)
    print("config.py 自检（第 8 阶段：智能问答系统）")
    print("=" * 72)
    print("ROOT         = %s" % ROOT)
    print("STAGE_DIR    = %s" % STAGE_DIR)
    print("OUTPUT_DIR   = %s" % OUTPUT_DIR)
    print("WORK_DIR     = %s" % WORK_DIR)
    print("检索侧参数来源 = %s" % _RETRIEVAL_CONFIG_PATH)
    print()
    print("--- 四项定值（从 代码\\检索\\config.py 导入，不是本文件的字面量）---")
    for name, value in (("K", K), ("N", N),
                        ("CONTEXT_TOKEN_BUDGET", CONTEXT_TOKEN_BUDGET), ("G", G)):
        print("  %-22s = %s" % (name, value))
    print("  DATA_CUTOFF_TIME       = %s" % DATA_CUTOFF_TIME)
    print("  DATASET_VERSION        = %s" % DATASET_VERSION)
    print("  相对时间窗口表（导入自检索侧） = %s" % RELATIVE_TIME_WINDOWS)
    print("  由窗口规则推出的判定区间端点   = %s"
          % "、".join(sorted(d.isoformat() for d in window_endpoint_dates())))
    print()
    print("--- 答案侧三值（《02》v3.3 登记口径）---")
    print("  model_name    = %s" % ANSWER["model_name"])
    print("  model_version = %s" % ANSWER["model_version"])
    print("  temperature   = %s" % ANSWER["temperature"])
    print("  max_tokens    = %s（《21》v1.3 硬约束 2：推理型模型推理与正文共用预算，"
          "2048 必空／4096 仍截断／16384 实测 stop 且正文非空；三候选同值）"
          % ANSWER["max_tokens"])
    print("  endpoint      = %s" % ANSWER["endpoint"])
    print("  prompt_version= %s" % ANSWER["prompt_version"])
    print()
    print("--- 模型 id 环境变量（只认自定义名，不读 LLM_MODEL）---")
    for env_name in (ANSWER_MODEL_ENV, SELECTION_MODEL_ENV):
        raw = os.environ.get(env_name)
        print("  %-24s 置位=%s" % (env_name, "是" if (raw or "").strip() else "否（用冻结值）"))
    print("  LLM_MODEL 在本组件里被读取 = 否（运行环境自身的路由变量，刻意不读）")
    print()
    print("--- 密钥可用性（只打印真／假，不回显取值）---")
    for cand in MODEL_CANDIDATES:
        print("  %-16s provider=%-9s 可用=%s"
              % (cand["model"], cand["provider"],
                 "真" if api_key_available(cand["provider"]) else "假"))
    print()
    print("--- 输入文件是否存在（《21》第三节 八项）---")
    for name, path in INPUT_FILES:
        print("  %-22s 存在=%-5s %s" % (name, "真" if os.path.isfile(path) else "假", path))
    print()
    print("--- 镜像重跑守卫 ---")
    print("  %s = %s → model_calls_forbidden() = %s"
          % (FORBID_MODEL_CALLS_ENV, os.environ.get(FORBID_MODEL_CALLS_ENV) or "(未置位)",
             model_calls_forbidden()))
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
