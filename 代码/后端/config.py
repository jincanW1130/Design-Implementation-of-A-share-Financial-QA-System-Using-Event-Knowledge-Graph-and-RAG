# -*- coding: utf-8 -*-
"""代码\\后端\\config.py —— 第 9 阶段（前后端系统集成）后端组件的**唯一参数来源**。

本文件只放参数与读取方式，**不放任何口令取值**。后端所有模块（db／errors／main／run／
api\\*／services\\*／tools\\*）一律经本文件读取参数；脚本内不得写死库名、连接串、端口、路径、
K／N／预算／g、模型名与版本、日期（《24-第9阶段任务书》第五节 硬约束 1）。

四类参数与来源
---------------
1. **检索侧四项定值**（K／N／Context Token Budget／g）：从 `代码\\检索\\config.py` 的
   `RETRIEVAL` **导入**（`importlib.util.spec_from_file_location` 按文件路径加载，不走
   `sys.path`——目录名「检索」不是合法模块名）——**不落第二份字面量**（硬约束 1）。
2. **生成侧配置**（模型／版本／Prompt 版本／temperature／max_tokens）：从
   `代码\\问答\\config.py` 的 `ANSWER` **导入**，同样不复制字面量。
3. **本机配置**（MySQL／Neo4j 连接参数、两个端口）：从同目录的 `config.local.json` 读。
   该文件被 `.gitignore` 的 `config.local.*`／`*.local.json` 覆盖，**不入公开仓库**。
4. **路径与输入清单**：本文件按工作区结构给出（§「2. 路径」），全部指向只读的上游产物。

口令纪律（硬约束 2／4）
-----------------------
口令**只从 `config.local.json` 读**，不写死、不回显、不入库、不进日志、不进前端构建产物。
本文件的打印只输出「已配置／未配置」，**任何情况下不打印口令取值**。

「缺失即报错退出、不得兜底」与「--dry-run 必须能跑通」的两条同时成立，本文件的做法
----------------------------------------------------------------------------------
《24》第五节 硬约束 1 要求「缺失或仍是占位串即 SystemExit」，而《24》的验证清单又要求
`tools\\import_data.py --dry-run` **在凭据未填时仍能跑通（不连库）**。两条在**导入期**不可能
同时成立，故本文件把校验分成两层，写清楚以免被当成「兜底」：

* **导入期硬校验（结构性错误，立即可判）**：配置文件不存在、必填键缺失、类型不对、
  `mysql_host`／`mysql_user`／`mysql_database` 为空或仍是占位串 —— 一律 `SystemExit`，
  因为这些值无论连不连库都用不了。
* **使用期硬校验（凭据类，延迟到真正需要用它的那一刻）**：`mysql_password` 为空或仍是
  占位串时，本文件在导入期**不退出**，只把 `MYSQL_PASSWORD_READY` 置为 `False`；
  真正要连库的代码必须调用 `db_params()`，由它 `SystemExit` 并给出
  「请检查 `代码\\后端\\config.local.json`」的提示。`--dry-run` 不调用 `db_params()`，
  因此能跑通；真写库的步骤必然在 `db_params()` 上以**明确的凭据错误**退出。

这**不是**兜底：没有任何默认口令、没有任何「localhost 猜一个」的回退，缺口令就是缺口令，
只是把「什么时候报错」放到唯一能报得准的地方（连接点）。`selftest()` 在凭据未配置时会
打印醒目的「凭据待填」告警行。
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys

# 控制台默认 GBK：导入时即把 stdout／stderr 切到 UTF-8，否则中文输出按 GBK 解码会炸
# （第 5／8 阶段踩过的坑）。文件读写一律显式 encoding="utf-8"。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# --------------------------------------------------------------------------
# 1. 工作区根与阶段目录
# --------------------------------------------------------------------------
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))            # 代码\后端
CODE_DIR = os.path.dirname(BACKEND_DIR)                            # 代码
ROOT = os.path.dirname(CODE_DIR)                                   # 工作区根

STAGE9 = os.path.join(ROOT, "阶段09-前后端系统集成")
OUTPUT_DIR = os.path.join(STAGE9, "集成产出")                       # 本阶段的集成产出落点
WORK_DIR = os.path.join(STAGE9, "_工作底稿")                        # 勘察与试跑留痕（不入库）
SCHEMA_DIR = os.path.join(BACKEND_DIR, "schema")
SCHEMA_SQL = os.path.join(SCHEMA_DIR, "六张表.sql")                 # 六张表的 DDL（唯一 schema 出处）

LOCAL_CONFIG_PATH = os.path.join(BACKEND_DIR, "config.local.json")
LOCAL_CONFIG_EXAMPLE = os.path.join(BACKEND_DIR, "config.local.json.example")

# --------------------------------------------------------------------------
# 2. 上游输入清单（**只读**；《24》第三节 八项）
# --------------------------------------------------------------------------
DATASET_VERSION = "v2.1"
DATASET_DIR = os.path.join(ROOT, "阶段05-数据准备", "数据集", DATASET_VERSION)
DOCUMENTS_JSONL = os.path.join(DATASET_DIR, "clean", "documents.jsonl")
CHUNKS_JSONL = os.path.join(DATASET_DIR, "chunks", "chunks.jsonl")
DATASET_META_PATH = os.path.join(DATASET_DIR, "meta", "dataset.json")
DATASET_INDEX_DIR = os.path.join(DATASET_DIR, "index")              # 向量索引三件（只读）
VECTOR_INDEX_PATH = os.path.join(DATASET_INDEX_DIR, "faiss.index")
VECTOR_MAP_PATH = os.path.join(DATASET_INDEX_DIR, "vector_map.jsonl")
BUILD_META_PATH = os.path.join(DATASET_INDEX_DIR, "build_meta.json")

# **2026-10-02 作者裁定：交付口径由 v1.2 切换为 v1.3**（原候选口径转正；理由与代价见
# 《16》第 9.5 节、《10》第4.5.4节 与《02》修订记录）。v1.2 归档保留、可原样复现
# （抽取侧用 --profile v21_v1_2，产物仍在 图谱导出\v2.1_v1_2\、一个字节未动）。
GRAPH_VERSION = "v2.1_v1_3"
GRAPH_DIR = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", GRAPH_VERSION)
NODES_CSV = os.path.join(GRAPH_DIR, "nodes.csv")
EDGES_CSV = os.path.join(GRAPH_DIR, "edges.csv")
GRAPH_STATS_PATH = os.path.join(GRAPH_DIR, "graph_stats.json")

QA_RECORDS_JSONL = os.path.join(ROOT, "阶段08-智能问答系统", "问答产出", "qa_records.jsonl")

# 第三节 八项输入（简称 → 路径），顺序即清单顺序，不得随运行环境变化
INPUT_FILES = [
    ("documents", DOCUMENTS_JSONL),
    ("chunks", CHUNKS_JSONL),
    ("dataset_meta", DATASET_META_PATH),
    ("vector_index", VECTOR_INDEX_PATH),
    ("vector_map", VECTOR_MAP_PATH),
    ("build_meta", BUILD_META_PATH),
    ("nodes_csv", NODES_CSV),
    ("edges_csv", EDGES_CSV),
    ("graph_stats", GRAPH_STATS_PATH),
    ("qa_records", QA_RECORDS_JSONL),
]

# 本批导入的**对拍基准**（上游产物的登记行数；《24》第八节 B3／B4）
EXPECTED_COUNTS = {
    "document": 709,
    "document_chunk": 5018,
    "question": 30,
    "answer": 30,
    "answer_evidence": 293,
}

# --------------------------------------------------------------------------
# 3. 六张表（**恒为六张**，供门禁逐项核对；《24》第五节 硬约束 3）
# --------------------------------------------------------------------------
TABLES = ["user", "document", "document_chunk", "question", "answer", "answer_evidence"]

# 导入顺序：与外键依赖一致（父表在前）
IMPORT_ORDER = ["document", "document_chunk", "question", "answer", "answer_evidence"]

# --------------------------------------------------------------------------
# 4. 上游参数：**导入**而非复制（硬约束 1）
# --------------------------------------------------------------------------
RETRIEVAL_CONFIG_PATH = os.path.join(ROOT, "代码", "检索", "config.py")
ANSWER_CONFIG_PATH = os.path.join(ROOT, "代码", "问答", "config.py")


def _load_module(mod_name: str, path: str):
    """按**文件路径**加载上游 config.py（不动 sys.path）。

    上游目录名「检索」「问答」不是合法模块名，且可能与 sys.path 上的同名模块冲突，
    故用 `importlib.util.spec_from_file_location`（第 8 阶段 `代码\\问答\\config.py`
    已确立的同一做法）。
    """
    if not os.path.isfile(path):
        raise SystemExit("上游参数来源不存在：%s（第 9 阶段一律 import 复用，不复制实现）" % path)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RET = _load_module("_stage9_retrieval_config", RETRIEVAL_CONFIG_PATH)
RETRIEVAL = getattr(_RET, "RETRIEVAL", None)
if not isinstance(RETRIEVAL, dict):
    raise SystemExit("检索侧 config 里没有可用的 RETRIEVAL 常量：%s" % RETRIEVAL_CONFIG_PATH)


def _need_retrieval(key: str):
    """从检索侧 RETRIEVAL 取一项定值；读到 None／缺失即报错退出，**不得兜底**。"""
    value = RETRIEVAL.get(key)
    if value is None:
        raise SystemExit(
            "检索侧 config.RETRIEVAL[%r] 为 None／缺失（TBD）——第 9 阶段直接从第 7 阶段导入，"
            "不得用默认值兜底；请先在第 7 阶段固化并回《02》登记。" % key)
    return value


K = _need_retrieval("K")                              # 最终证据集合的文本块上限
N = _need_retrieval("N")                              # 向量检索候选数量
CONTEXT_TOKEN_BUDGET = _need_retrieval("context_token_budget")
G = _need_retrieval("graph_retention_share")          # 分层保留份额 g（全局固化量）

# 第 7 阶段的版本级属性（作为**交叉核对**用；权威来源见 §5 的 dataset.json）
DATA_CUTOFF_TIME_UPSTREAM = getattr(_RET, "DATA_CUTOFF_TIME", None)
DEFAULT_GROUP = getattr(_RET, "DEFAULT_GROUP", None)
GROUPS = getattr(_RET, "GROUPS", None)

_ANS = _load_module("_stage9_answer_config", ANSWER_CONFIG_PATH)
ANSWER = getattr(_ANS, "ANSWER", None)
if not isinstance(ANSWER, dict):
    raise SystemExit("答案生成侧 config 里没有可用的 ANSWER 常量：%s" % ANSWER_CONFIG_PATH)

ANSWER_MODEL = ANSWER.get("model_name")               # 生成模型标识（写入 answer.model_name）
ANSWER_MODEL_VERSION = ANSWER.get("model_version")
PROMPT_VERSION = ANSWER.get("prompt_version")         # 写入 answer.prompt_version
ANSWER_TEMPERATURE = ANSWER.get("temperature")
ANSWER_MAX_TOKENS = ANSWER.get("max_tokens")
for _name, _value in (("model_name", ANSWER_MODEL), ("model_version", ANSWER_MODEL_VERSION),
                      ("prompt_version", PROMPT_VERSION)):
    if _value is None or not str(_value).strip():
        raise SystemExit("答案生成侧 ANSWER[%r] 缺失——不得兜底。" % _name)
del _name, _value

# --------------------------------------------------------------------------
# 5. 数据集版本级属性（`/api/config/meta` 的来源；**不属于任何表**）
# --------------------------------------------------------------------------
_dataset_meta_cache = None


def dataset_meta() -> dict:
    """读数据集元信息 `meta\\dataset.json`（带缓存）。

    `dataset_version` 与 `data_cutoff_time` 是**数据集版本级属性**，与六张表无关
    （《10》第4.4.4节）；接口响应统一带上它们，页面固定显示「数据截至：YYYY-MM-DD」。
    """
    global _dataset_meta_cache
    if _dataset_meta_cache is None:
        if not os.path.isfile(DATASET_META_PATH):
            raise SystemExit("数据集元信息不存在：%s——不得兜底。" % DATASET_META_PATH)
        with open(DATASET_META_PATH, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict) or not obj.get("dataset_version") or not obj.get("data_cutoff_time"):
            raise SystemExit("数据集元信息缺 dataset_version／data_cutoff_time：%s" % DATASET_META_PATH)
        _dataset_meta_cache = obj
    return _dataset_meta_cache


def meta_fields() -> dict:
    """成功响应的 `meta` 区块（《24》第六节 格式决策 3）。"""
    meta = dataset_meta()
    return {"dataset_version": meta["dataset_version"],
            "data_cutoff_time": meta["data_cutoff_time"]}


def data_cutoff_date() -> str:
    """`data_cutoff_time` 的日期部分（YYYY-MM-DD；页面固定显示用）。不写死日期。"""
    return str(dataset_meta()["data_cutoff_time"])[:10]


# --------------------------------------------------------------------------
# 6. 本机配置（`config.local.json`）——口令只从这里读
# --------------------------------------------------------------------------
# 「占位串」的判定：模板里保留的提示语一律视为**未填**（不含任何真实口令）。
PLACEHOLDER_MARKERS = (
    "填在这里", "填在这", "请填", "填入", "占位", "your_", "YOUR_", "<", ">",
    "changeme", "CHANGEME", "TODO", "todo", "xxxx",
)

# 必填键 → 期望类型（`None` 表示「字符串，且不得为空或占位」）
_REQUIRED_KEYS = {
    "mysql_host": str,
    "mysql_port": int,
    "mysql_user": str,
    "mysql_password": str,        # 结构必填；**取值可为占位串**（延迟到 db_params() 报错）
    "mysql_database": str,
    "mysql_charset": str,
    "neo4j_uri": str,
    "neo4j_user": str,
    "neo4j_password": str,        # 允许为空串（本机 Neo4j 未设口令时）
    "backend_port": int,
    "frontend_port": int,
}
# 这些键**不得**为空或占位（无论是否连库都用得上）
_STRICT_STR_KEYS = ("mysql_host", "mysql_user", "mysql_database", "mysql_charset",
                    "neo4j_uri", "neo4j_user")


def _is_placeholder(value) -> bool:
    """只判「是不是模板里的提示语」，**不打印取值本身**。"""
    if value is None:
        return True
    text = str(value).strip()
    if not text:
        return True
    return any(mark in text for mark in PLACEHOLDER_MARKERS)


def _load_local_config() -> dict:
    if not os.path.isfile(LOCAL_CONFIG_PATH):
        raise SystemExit(
            "本机配置不存在：%s\n"
            "请先复制模板并填入本机取值：\n"
            "    copy \"%s\" \"%s\"\n"
            "后端只从它读连接参数，不写死、不兜底。"
            % (LOCAL_CONFIG_PATH, LOCAL_CONFIG_EXAMPLE, LOCAL_CONFIG_PATH))
    try:
        with open(LOCAL_CONFIG_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:
        raise SystemExit("本机配置无法解析（%s）：%s" % (type(exc).__name__, LOCAL_CONFIG_PATH))
    if not isinstance(raw, dict):
        raise SystemExit("本机配置的顶层必须是 JSON 对象：%s" % LOCAL_CONFIG_PATH)

    # 去掉 `_说明` 一类的注释键
    cfg = {k: v for k, v in raw.items() if not str(k).startswith("_")}

    # —— 导入期硬校验：键缺失／类型不对／关键字符串为空或占位 ——
    for key, typ in _REQUIRED_KEYS.items():
        if key not in cfg or cfg[key] is None:
            raise SystemExit("本机配置缺必填键 %r：%s" % (key, LOCAL_CONFIG_PATH))
        if typ is int:
            try:
                cfg[key] = int(cfg[key])
            except (TypeError, ValueError):
                raise SystemExit("本机配置 %r 必须是整数，收到 %r" % (key, type(cfg[key]).__name__))
        elif not isinstance(cfg[key], str):
            raise SystemExit("本机配置 %r 必须是字符串" % key)
    for key in _STRICT_STR_KEYS:
        if _is_placeholder(cfg[key]):
            raise SystemExit(
                "本机配置 %r 为空或仍是模板占位串——请填入真实取值后重跑：%s"
                % (key, LOCAL_CONFIG_PATH))
    return cfg


_LOCAL = _load_local_config()

# 导入期只报告、不回显
MYSQL_PASSWORD_READY = not _is_placeholder(_LOCAL["mysql_password"])
NEO4J_PASSWORD_READY = not _is_placeholder(_LOCAL["neo4j_password"])

BACKEND_PORT = _LOCAL["backend_port"]
FRONTEND_PORT = _LOCAL["frontend_port"]
CORS_ORIGINS = [
    "http://localhost:%d" % FRONTEND_PORT,
    "http://127.0.0.1:%d" % FRONTEND_PORT,
]


def db_params(with_database: bool = True) -> dict:
    """MySQL 连接参数（口令在此**使用期**校验，供 db.py 调用）。

    口令缺失／仍是占位串时 `SystemExit`，提示里含「请检查 代码\\后端\\config.local.json」。
    **返回值含口令，禁止打印、禁止写盘、禁止进日志。**
    """
    if not MYSQL_PASSWORD_READY:
        raise SystemExit(
            "MySQL 凭据不可用：代码\\后端\\config.local.json 的 mysql_password 为空或仍是模板占位串。\n"
            "请检查 代码\\后端\\config.local.json（参考同目录的 config.local.json.example）：\n"
            "    mysql_password = 本机 MySQL 的 root 口令\n"
            "本阶段**不提供默认口令、不提供兜底路径**；凭据由作者填入后重跑即可。\n"
            "（仅解析与统计的 --dry-run 不连库，不受此影响。）")
    params = {
        "host": _LOCAL["mysql_host"],
        "port": _LOCAL["mysql_port"],
        "user": _LOCAL["mysql_user"],
        "password": _LOCAL["mysql_password"],
        "charset": _LOCAL["mysql_charset"],
    }
    if with_database:
        params["database"] = _LOCAL["mysql_database"]
    return params


def db_database() -> str:
    return _LOCAL["mysql_database"]


def db_charset() -> str:
    return _LOCAL["mysql_charset"]


def neo4j_params() -> dict:
    """Neo4j 连接参数（口令允许为空：本机 Neo4j 首次启动前无口令）。"""
    return {"uri": _LOCAL["neo4j_uri"], "user": _LOCAL["neo4j_user"],
            "password": _LOCAL["neo4j_password"]}


def mysql_configured() -> bool:
    """只回答「口令填了没有」，**不返回也不打印口令**。"""
    return MYSQL_PASSWORD_READY


# --------------------------------------------------------------------------
# 7. 接口层门槛参数（输入校验与频率限制；《24》第八节 G2「在文档中登记限制参数」）
# --------------------------------------------------------------------------
RATE_LIMIT = {
    "window_seconds": 60,         # 滑动窗口长度
    "max_requests": 60,           # 同一来源 IP 在窗口内允许的请求数
}
LIMITS = {
    "max_body_bytes": 64 * 1024,  # 请求体上限（64 KiB）
    "question_min_chars": 1,      # question 最短长度（空串按 1001 拒）
    "question_max_chars": 500,    # question 最长长度（超长按 1001 拒）
}

# --------------------------------------------------------------------------
# 8. 固定项：读到 None／空串／"TBD" 即报错退出（不用默认值兜底）
# --------------------------------------------------------------------------
FIXED = {
    "K": K,
    "N": N,
    "context_token_budget": CONTEXT_TOKEN_BUDGET,
    "graph_retention_share": G,
    "model_name": ANSWER_MODEL,
    "model_version": ANSWER_MODEL_VERSION,
    "prompt_version": PROMPT_VERSION,
    "dataset_version": DATASET_VERSION,
}


def require_fixed(name: str):
    if name not in FIXED:
        raise SystemExit("固定表里没有 %r（合法名：%s）" % (name, "、".join(sorted(FIXED))))
    value = FIXED[name]
    if name == "data_cutoff_time":
        value = dataset_meta().get("data_cutoff_time")
    if value is None or (isinstance(value, str) and value.strip() in ("", "TBD")):
        raise SystemExit(
            "固定项 %r 仍为 TBD／空（《02》第12.4节 固定表）；冻结后方可使用，不得用默认值兜底。"
            % name)
    return value


# --------------------------------------------------------------------------
# 9. 通用工具（与第 7／8 阶段同一套写法，避免各脚本各写一份）
# --------------------------------------------------------------------------
def sha256_file(path: str) -> str:
    """文件的 SHA-256（分块读，避免把大文件／索引一次性读进内存）。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


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


def count_jsonl(path: str) -> int:
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def fields_of_jsonl(path: str, limit: int = 1) -> list:
    """读前 `limit` 行的键集合（**按真实数据取字段名，不凭猜**）。"""
    keys = set()
    for i, row in enumerate(iter_jsonl(path)):
        if isinstance(row, dict):
            keys |= set(row.keys())
        if i + 1 >= limit:
            break
    return sorted(keys)


# --------------------------------------------------------------------------
# 9.1 实时数据区（作者新增意见：实时数据再完善一些）
# --------------------------------------------------------------------------
# 口径（硬约束，写在这里供全后端引用）：
#   本系统的问答答案锚定**冻结语料**（DATASET_VERSION，数据截止 data_cutoff_time）。
#   本节参数只服务页面上的「实时数据区」——**实时数据只作展示，绝不进入检索／问答证据链**；
#   所有实时区响应体都带 `"scope": "display_only"`。数据源失败时如实返回「未接入」
#   （connected=false ＋ reason），**绝不返回任何编造数据**（假价格／假涨跌幅／假新闻）。
#
# 三个公开源（无需 key，参数为实测通过的原样）＋一个语料内源：
#   1) 实时行情：东方财富 push2（`secids` 前缀：沪市 1.、深市 0.）
#   2) 个股公告：东方财富 np-anotice（详情页模板见 notice_detail_url）
#   3) 个股新闻：东方财富搜索 JSONP（**必须带 Referer**，返回体需剥掉 cb(...) 外壳）
#   4) 语料内近一周：**不依赖外部源**，直接查库 `document` 表（降级形态）
MARKET_ZONE = {
    # 源 URL 模板：占位符在请求时填充（不得在 services\market_service.py 里写死）
    "quote_url": ("https://push2.eastmoney.com/api/qt/ulist.np/get"
                  "?fltt=2&secids={secids}&fields=f12,f14,f2,f3,f4,f6"),
    "announcement_url": ("https://np-anotice-stock.eastmoney.com/api/security/ann"
                         "?sr=-1&page_size={page_size}&page_index=1&ann_type=A"
                         "&client_source=web&stock_list={code}"),
    "notice_detail_url": "https://data.eastmoney.com/notices/detail/{code}/{art_code}.html",
    "news_url": "https://search-api-web.eastmoney.com/search/jsonp?cb=&param={param}",
    "news_referer": "https://so.eastmoney.com/",     # 新闻源**必须**带该 Referer
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "source_name": "eastmoney",                      # 实时区响应的 source 字段取值
    "corpus_source_name": "corpus",                  # 语料内源的 source 字段取值
    "timeout_seconds": 8,                            # 单次外部请求超时（秒）
    "cache_ttl_seconds": 60,                         # 进程内缓存 TTL（秒）
    "default_codes": ["000001", "600519"],           # 缺 codes 参数时的默认股列表
    "corpus_lookback_days": 7,                       # 语料内源默认回看天数（近一周）
    # 各接口的 page_size 合法区间（越界按 1002 拒）
    "page_size_min": 1,
    "page_size_max": 50,
    # days 参数的合法区间（越界按 1002 拒）
    "days_min": 1,
    "days_max": 30,
}
# secids 前缀规则：沪市 `1.`、深市 `0.`（北交所 4/8 归 `0.`）。
#   显式市场前缀（`sh`／`sz`）优先；否则按代码首位判定，认不出取默认值。
MARKET_MARKET_PREFIX = {"sh": "1", "sz": "0"}
MARKET_SECID_PREFIX_BY_HEAD = {"6": "1", "0": "0", "3": "0", "4": "0", "8": "0"}
MARKET_SECID_DEFAULT_PREFIX = "0"


def market_zone() -> dict:
    """实时数据区参数（返回**浅拷贝**，调用方不得就地改这份配置）。"""
    return dict(MARKET_ZONE)


def market_default_codes() -> list:
    return list(MARKET_ZONE["default_codes"])


def secid_of(code) -> str:
    """把证券代码归一化成东方财富的 `secid` 形式（`600519` → `1.600519`、`000001` → `0.000001`）。

    接受 `600519`／`000001`／`sh600519`／`sz000001`／`SH600519`／`1.600519` 等写法；
    格式不合法（非 6 位数字，或市场前缀不认识）抛 `ValueError`——**不猜**，由调用方按
    参数格式错误处理（接口层 → 1002）。前缀规则取自本文件的 `MARKET_*` 常量。
    """
    text = str(code).strip().lower()
    if "." in text:                                   # 已是 secid：`1.600519`
        head, _, digits = text.partition(".")
        if head in ("0", "1") and digits.isdigit():
            return "%s.%s" % (head, digits)
        raise ValueError("secid 形式不合法：%r" % code)
    market = None
    for prefix, market_id in MARKET_MARKET_PREFIX.items():
        if text.startswith(prefix):
            text, market = text[len(prefix):], market_id
            break
    if not (len(text) == 6 and text.isdigit()):
        raise ValueError("证券代码应为 6 位数字（可带 sh／sz 前缀）：%r" % code)
    if market is None:
        market = MARKET_SECID_PREFIX_BY_HEAD.get(text[0], MARKET_SECID_DEFAULT_PREFIX)
    return "%s.%s" % (market, text)


# --------------------------------------------------------------------------
# 10. 自检（`python 代码\\后端\\config.py`）
# --------------------------------------------------------------------------
def selftest() -> int:
    line = "=" * 74
    print(line)
    print("config.py 自检（第 9 阶段：前后端系统集成 / 后端唯一参数来源）")
    print(line)
    print("ROOT        = %s" % ROOT)
    print("BACKEND_DIR = %s" % BACKEND_DIR)
    print("STAGE9      = %s" % STAGE9)
    print("OUTPUT_DIR  = %s" % OUTPUT_DIR)
    print("SCHEMA_SQL  = %s" % SCHEMA_SQL)
    print()

    print("--- 检索侧四项定值（从 代码\\检索\\config.py 导入，不是本文件的字面量）---")
    print("  来源文件        = %s" % RETRIEVAL_CONFIG_PATH)
    print("  K               = %s" % K)
    print("  N               = %s" % N)
    print("  CONTEXT_TOKEN_BUDGET = %s" % CONTEXT_TOKEN_BUDGET)
    print("  G（graph_retention_share） = %s" % G)
    print()

    print("--- 生成侧配置（从 代码\\问答\\config.py 导入）---")
    print("  来源文件        = %s" % ANSWER_CONFIG_PATH)
    print("  ANSWER_MODEL    = %s" % ANSWER_MODEL)
    print("  model_version   = %s" % ANSWER_MODEL_VERSION)
    print("  PROMPT_VERSION  = %s" % PROMPT_VERSION)
    print("  temperature     = %s" % ANSWER_TEMPERATURE)
    print("  max_tokens      = %s" % ANSWER_MAX_TOKENS)
    print()

    print("--- 数据集版本级属性（meta\\dataset.json，不属于任何表）---")
    meta = dataset_meta()
    print("  dataset_version  = %s" % meta.get("dataset_version"))
    print("  data_cutoff_time = %s（页面固定显示 %s）"
          % (meta.get("data_cutoff_time"), data_cutoff_date()))
    print("  检索侧 config.DATA_CUTOFF_TIME = %s → 与上者一致 = %s"
          % (DATA_CUTOFF_TIME_UPSTREAM,
             str(DATA_CUTOFF_TIME_UPSTREAM) == str(meta.get("data_cutoff_time"))))
    print()

    print("--- 本机配置（只报「已配置／未配置」，不回显任何口令）---")
    print("  配置文件            = %s（存在=%s）"
          % (LOCAL_CONFIG_PATH, os.path.isfile(LOCAL_CONFIG_PATH)))
    print("  mysql_host:port     = %s:%s" % (_LOCAL["mysql_host"], _LOCAL["mysql_port"]))
    print("  mysql_user          = %s" % _LOCAL["mysql_user"])
    print("  mysql_database      = %s（charset=%s）"
          % (_LOCAL["mysql_database"], _LOCAL["mysql_charset"]))
    print("  mysql_password      = %s" % ("已配置" if MYSQL_PASSWORD_READY else "未配置（空或占位串）"))
    print("  neo4j_uri           = %s" % _LOCAL["neo4j_uri"])
    print("  neo4j_user          = %s" % _LOCAL["neo4j_user"])
    print("  neo4j_password      = %s" % ("已配置" if NEO4J_PASSWORD_READY else "未配置（空）"))
    print("  backend_port        = %s" % BACKEND_PORT)
    print("  frontend_port       = %s" % FRONTEND_PORT)
    print("  CORS 允许来源       = %s" % "、".join(CORS_ORIGINS))
    print()

    print("--- 六张表（恒为六张）---")
    print("  TABLES       = %s" % "、".join(TABLES))
    print("  数量         = %d" % len(TABLES))
    print("  导入顺序     = %s" % " → ".join(IMPORT_ORDER))
    print("  对拍基准     = %s" % json.dumps(EXPECTED_COUNTS, ensure_ascii=False, sort_keys=True))
    print()

    print("--- 输入文件是否存在（《24》第三节 八项，只读）---")
    for name, path in INPUT_FILES:
        print("  %-14s 存在=%-5s %s" % (name, "真" if os.path.isfile(path) else "假", path))
    print()

    print("--- 接口层门槛参数 ---")
    print("  RATE_LIMIT = %s" % json.dumps(RATE_LIMIT, ensure_ascii=False, sort_keys=True))
    print("  LIMITS     = %s" % json.dumps(LIMITS, ensure_ascii=False, sort_keys=True))
    print()

    print("--- 实时数据区（只作展示、不进问答证据链；scope=display_only）---")
    print("  超时／缓存 TTL = %ss／%ss" % (MARKET_ZONE["timeout_seconds"],
                                           MARKET_ZONE["cache_ttl_seconds"]))
    print("  默认股列表     = %s" % "、".join(MARKET_ZONE["default_codes"]))
    print("  secid 前缀规则 = 沪市 %s／深市 %s（6→1，0／3／4／8→0）"
          % (MARKET_MARKET_PREFIX["sh"] + ".", MARKET_MARKET_PREFIX["sz"] + "."))
    print("  secid 样例     = 600519→%s，000001→%s，sh600519→%s"
          % (secid_of("600519"), secid_of("000001"), secid_of("sh600519")))
    print("  行情源         = %s" % MARKET_ZONE["quote_url"].split("?")[0])
    print("  公告源         = %s" % MARKET_ZONE["announcement_url"].split("?")[0])
    print("  新闻源         = %s（Referer=%s）"
          % (MARKET_ZONE["news_url"].split("?")[0], MARKET_ZONE["news_referer"]))
    print("  语料内源       = 查库 document 表，近 %d 天（截止 %s）"
          % (MARKET_ZONE["corpus_lookback_days"], data_cutoff_date()))
    print()

    if not MYSQL_PASSWORD_READY:
        print("!! 阻断项：MySQL 凭据待填 —— 上面已打印「mysql_password = 未配置」。")
        print("   --dry-run（只解析与统计、不连库）可正常跑通；真写库会在 db_params() 处")
        print("   以明确的凭据错误退出。补齐方式：编辑 %s" % LOCAL_CONFIG_PATH)
        print()
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
