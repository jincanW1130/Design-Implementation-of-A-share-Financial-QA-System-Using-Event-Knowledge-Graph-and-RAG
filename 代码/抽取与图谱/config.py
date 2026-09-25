# -*- coding: utf-8 -*-
"""代码\\抽取与图谱\\config.py —— 抽取与图谱组件的**唯一参数来源**。

本文件只放参数与**读取方式**，不放任何取值型的密钥：密钥只从环境变量读取
（见 `api_key()`），不入仓库、不落盘、不进日志。脚本内不得写死模型名、路径、
阈值或日期，一律经本文件读取（沿用 `代码\\数据准备\\config.py` 已确立的做法）。

参数来源（本文件只引用、不新增、不改名）：

* 本体 schema（6 类实体／8 种事件类型／9 条核心关系、role 取值、证据属性口径、
  ISSUED_BY 只用于政策事件与监管事件、Document 不作为第七类实体）：
  《10-系统总体设计（第四阶段）》第4.5节（＝《02》第9.2节）。
* 冻结口径（以文档为上下文、以文本块为证据单位、缓存可重放、编号显式分配）：
  《15-第6阶段任务书（事件抽取与知识图谱）》第五节 硬约束 1～20。
* 事件类型与关系的**标题级／正文级代理关键词集**（只用于试跑选样与覆盖性重算，
  不是抽取结果）：《13-数据准备（第五阶段）》第9.1.1节 末尾代码块，
  以及 `代码\\数据准备\\config.py` 的 `EVENT_FIRST`（重大合同组与产品组的冻结正则）。
* 数据集路径、版本、切分重叠：`代码\\数据准备\\config.py`（v2.1 为现行版本）。

编号口径：试跑按 `doc_id` 局部编号（ENT-／EVT-／REL- 前缀）以便回溯；
全局编号（EVT-0001、policy_id、institution_id、person_id）由 T6 的
`write_graph.py` 统一一次性分配，本组件不固化全局编号。
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
STAGE_DIR = os.path.join(ROOT, "阶段06-事件抽取与知识图谱")

DATASET_VERSION = "v2.1"
DATASET_ROOT = os.path.join(ROOT, "阶段05-数据准备", "数据集")
DATASET_DIR = os.path.join(DATASET_ROOT, DATASET_VERSION)
DOCS_PATH = os.path.join(DATASET_DIR, "clean", "documents.jsonl")
CHUNKS_PATH = os.path.join(DATASET_DIR, "chunks", "chunks.jsonl")

# 原始返回缓存：与数据集版本目录同级，一版一个子目录；下划线前缀表示它不是数据集内容。
CACHE_ROOT = os.path.join(DATASET_ROOT, "_抽取缓存")
CACHE_DIR = os.path.join(CACHE_ROOT, DATASET_VERSION)

# 试跑产物目录：不是交付物、不入仓库（`.gitignore` 已含 `代码/抽取与图谱/_试跑/`）。
PILOT_DIR = os.path.join(_THIS_DIR, "_试跑")

# T6 的图谱导出物落点（本任务 T1 不产出，只登记，避免下游自行发明路径）。
GRAPH_EXPORT_DIR = os.path.join(STAGE_DIR, "图谱导出", DATASET_VERSION)

# 试跑产物文件名（机器可读产物一律 ASCII 名；运行日志用中文名，与第 5 阶段 勘察\\ 同风格）。
OUTPUT_FILES = {
    "selection": os.path.join(PILOT_DIR, "selection.json"),
    "coverage": os.path.join(PILOT_DIR, "coverage.json"),
    "extracted": os.path.join(PILOT_DIR, "extracted.jsonl"),
    "rejected": os.path.join(PILOT_DIR, "rejected.jsonl"),
    "run_history": os.path.join(PILOT_DIR, "run_history.jsonl"),
    "verify": os.path.join(PILOT_DIR, "verify.json"),
    "manifest": os.path.join(PILOT_DIR, "manifest.sha256"),
    "log_first": os.path.join(PILOT_DIR, "运行日志_首跑.txt"),
    "log_second": os.path.join(PILOT_DIR, "运行日志_复跑.txt"),
}

# --------------------------------------------------------------------------
# 2. 抽取模型与调用参数（第 6 阶段必须固化的一项：模型／模型版本／Prompt 版本／temperature）
# --------------------------------------------------------------------------
# 2026-09-25 实测（只写读取方式，不写任何密钥）：
#   端点 `https://api.deepseek.com/v1` 的 `/models` 只列出 `deepseek-flash` 与
#   `deepseek-v4-pro`；环境变量 `LLM_MODEL` 的取值 `deepseek-v4-flash` **不在列表里**，
#   但可作为对话补全的请求模型使用，**响应体的 `model` 字段解析为 `deepseek-flash`**
#   ——即端点把别名静默解析到了 `deepseek-flash`。这一条必须如实登记：
#   `model_default` 是请求值，`model_pinned` 是实测被解析到的模型 id，
#   每次调用的 `model_resolved` 逐篇写进缓存，与 `model_pinned` 不一致时记
#   `model_pinning_warning`（见 extract.py），不静默放过。
LLM = {
    "provider": "OpenAI 兼容的对话补全端点（openai 2.44.0 客户端）",
    "base_url_env": "LLM_BASE_URL",
    "base_url_default": "https://api.deepseek.com/v1",
    "model_env": "LLM_MODEL",
    "api_key_env": "LLM_API_KEY",
    "model_default": "deepseek-v4-flash",     # 环境变量缺省时的请求模型（别名）
    "model_pinned": "deepseek-flash",         # 2026-09-25 实测解析到的模型 id
    "model_version": None,                    # 端点未提供版本／修订号，如实记 None
    "model_version_note": (
        "端点 `/models` 只返回 id 与 owned_by，不返回版本或 revision；"
        "与 `config.EMBEDDING` 的「模型名 + revision」双钉不同，这里只能钉到模型 id，"
        "因此**可重放性由缓存承担**（同一 doc_id 的原始返回逐字节留档），"
        "不依赖「同一次请求一定得到同一段文本」这一假设。"
    ),
    "temperature": 0,
    # 2026-09-25 实测：4096 会把长文档的返回截断（完成 token 打满、JSON 不完整），
    # 端点接受 8192 与 16384；取 8192 兼顾「不截断」与「不失控」。
    "max_tokens": 8192,
    "response_format": "json_object",
    "timeout_seconds": 180.0,
    "prompt_version": "stage6-extract-v1.1",
    # 压缩重试：**只在主尝试被输出上限截断（finish_reason == "length"）时**触发一次。
    # 依据（2026-09-25 实测）：10,304 字符的 doc_id 1381 在主尝试下打满 8192 完成 token
    # 仍未输出完 JSON；同一端点 `reasoning_effort="none"` 可把完成 token 压到约 1/4
    # （探针实测 78 → 18），因此压缩重试同时收紧输出契约并关闭思考，两次原始返回都进缓存。
    "fallback": {
        "trigger_reason": "length",      # finish_reason 取该值时触发压缩重试
        "max_attempts": 2,
        "max_tokens": 8192,
        "reasoning_effort": "none",
        "compact_limits": {"entities": 8, "events": 2, "relations": 6, "quote_max_chars": 60},
    },
}


def api_key() -> str:
    """只写**读取方式**：密钥只来自环境变量，不入仓库、不落盘、不进日志。

    密钥未就位时按《15》第十一节 阻断（抛异常并非零退出），
    绝不用占位文本或模型编造的文本冒充实测抽取结果。
    """
    name = LLM["api_key_env"]
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(
            "环境变量 %s 未就位：抽取必须调用模型接口，按《15》第十一节 阻断，"
            "不得用占位文本或编造文本充数。" % name
        )
    return value


def base_url() -> str:
    """端点：优先环境变量，缺省用本文件固化的取值（端点不是密钥，可以写进配置）。"""
    return (os.environ.get(LLM["base_url_env"]) or LLM["base_url_default"]).strip()


def model_requested() -> str:
    """请求用的模型 id：优先环境变量 `LLM_MODEL`，缺省用本文件固化的取值。"""
    return (os.environ.get(LLM["model_env"]) or LLM["model_default"]).strip()


def model_pinning_state(resolved: str) -> str:
    """把「响应体解析到的模型」与钉住的模型比对，返回 `ok` 或 `warning`。"""
    return "ok" if str(resolved or "") == str(LLM["model_pinned"]) else "warning"


# --------------------------------------------------------------------------
# 3. 本体 schema（单一口径来源，不得新增、改名、合并）
# --------------------------------------------------------------------------
ENTITY_TYPES = ["Company", "Person", "Industry", "Institution", "Event", "Policy"]
# Event 由 `events[]` 物化为事件节点，不要求模型在 `entities[]` 里重复输出，
# 否则同一事件会被计两次（《10》第4.5.1节：participants 不作为事件属性存储）。
ENTITY_TYPES_FROM_MODEL = ["Company", "Person", "Industry", "Institution", "Policy"]

EVENT_TYPES = ["业绩", "监管", "股权", "投资并购", "重大合同", "产品", "政策", "重大经营"]
EVENT_CORE_ATTRS = ["event_id", "event_type", "event_name", "event_time", "description", "confidence"]

RELATIONS = [
    "BELONGS_TO", "SUPPLIES", "CUSTOMER_OF", "COMPETES_WITH", "HAS_EXECUTIVE",
    "PARTICIPATES_IN", "ISSUED_BY", "RELATED_TO", "EVIDENCED_BY",
]

# 关系的方向、端点类型与额外属性（照《10》第4.5.2节 的表 4-9）。
# `from_model=True` 的 8 条由模型给出；EVIDENCED_BY 由程序按 doc_id 直接生成，
# 不要求模型输出，也不携带 source_doc_id／source_chunk_id／confidence。
RELATION_SCHEMA = {
    "BELONGS_TO": {
        "domain": ["Company"], "range": ["Industry"], "from_model": True,
        "extra_attrs": ["valid_from", "valid_to"],
        "note": "公司所属行业，带有效时间区间",
    },
    "SUPPLIES": {
        "domain": ["Company"], "range": ["Company"], "from_model": True,
        "extra_attrs": [], "note": "供应商关系，A 向 B 供货，方向按信息来源",
    },
    "CUSTOMER_OF": {
        "domain": ["Company"], "range": ["Company"], "from_model": True,
        "extra_attrs": [], "note": "客户关系，按抽取结果确定方向",
    },
    "COMPETES_WITH": {
        "domain": ["Company"], "range": ["Company"], "from_model": True,
        "extra_attrs": [], "note": "竞争关系，第一版按抽取方向存一条",
    },
    "HAS_EXECUTIVE": {
        "domain": ["Company"], "range": ["Person"], "from_model": True,
        "extra_attrs": [], "note": "公司高管任职关系",
    },
    "PARTICIPATES_IN": {
        "domain": ["Company", "Person", "Institution"], "range": ["Event"], "from_model": True,
        "extra_attrs": ["role"],
        "note": "公司／人物／机构参与事件；发布或作出方只写 ISSUED_BY",
    },
    "ISSUED_BY": {
        "domain": ["Event"], "range": ["Institution"], "from_model": True,
        "extra_attrs": [], "note": "只出现在政策事件与监管事件上",
    },
    "RELATED_TO": {
        "domain": ["Event"], "range": ["Policy"], "from_model": True,
        "extra_attrs": [], "note": "事件与相关政策之间的关联",
    },
    "EVIDENCED_BY": {
        "domain": ["Event"], "range": ["Document"], "from_model": False,
        "extra_attrs": [],
        "note": "证据文档，由程序按 doc_id 生成；不携带三项证据属性",
    },
}
RELATIONS_FROM_MODEL = [r for r in RELATIONS if RELATION_SCHEMA[r]["from_model"]]
EVIDENCE_ATTRS = ["source_doc_id", "source_chunk_id", "confidence"]
ROLES = ["主体", "合作方", "涉及方", "监管方", "受影响方"]
ISSUED_BY_EVENT_TYPES = ["政策", "监管"]
DOCUMENT_LABEL = "Document"          # 证据文档标签：不作为第七类实体，不参与实体识别与消歧
CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0

# 抽取条数上限（控制单篇输出规模，防模型无节制罗列；不是本体约束）。
EXTRACT_LIMITS = {"entities": 12, "events": 4, "relations": 16}

# --------------------------------------------------------------------------
# 4. 证据定位规则（证据由代码解析，不由模型给编号）
# --------------------------------------------------------------------------
EVIDENCE = {
    # 2026-09-25 校准：来源 PDF 抽取出来的正文里存在词内空格（doc_id 1018 写作「公 司将」），
    # 若只把连续空白折成单空格，「公司将」这类引用会被误判为无法定位。故两侧一律**去掉
    # 全部空白（含全角空格）后比对**——仍然只归一空白，不做大小写、标点或模糊匹配，
    # 也不做编辑距离。
    "normalize": "whitespace_removed（去掉全部空白，含全角空格）",
    "match": "exact_substring",          # 精确子串匹配，不做模糊匹配、不做编辑距离
    "document_side": "按 chunk_index 升序在**该文档的文本块序列**里查",
    "multi_hit_policy": "命中多块时取 chunk_index 最小的一块，并记录 quote_match_count",
    "chunk_overlap_chars": 50,           # 来自第 5 阶段切分参数（重叠 50 字符）
    "quote_min_chars": 12,
    "quote_max_chars": 200,
    "title_is_not_evidence": True,       # 文本块由 content 切分而来，标题不进 quote
}

# event_time 归一化：只在正文能确定到日时填写，否则 null（绝不猜测）。
TIME = {
    "format": "YYYY-MM-DD",
    "accepted_income_forms": [           # 模型允许写这几种；代码统一折成 YYYY-MM-DD
        r"^\d{4}-\d{1,2}-\d{1,2}$",
        r"^\d{4}/\d{1,2}/\d{1,2}$",
        r"^\d{4}\.\d{1,2}\.\d{1,2}$",
        r"^\d{4}年\d{1,2}月\d{1,2}日$",
    ],
    # 代码侧复核：日期必须在正文里以某种写法真实出现，否则置 null 并记 event_time_unverified。
    "verify_rendering_in_document": True,
}

# --------------------------------------------------------------------------
# 5. 节奏与重试（沿用第 5 阶段数据管线的 HTTP 约定：最小间隔 + 指数退避）
# --------------------------------------------------------------------------
PACING = {
    "min_interval_seconds": 1.0,         # 两次调用之间至少间隔（礼貌限流）
    "max_retries": 4,                    # 传输层失败最多再试 4 次
    "backoff_base_seconds": 2.0,         # 退避：base * 2^(attempt-1)
    "backoff_max_seconds": 30.0,
    "retry_on": "连接错误／超时／HTTP 429／HTTP 5xx；4xx（除 429）不重试",
}

# --------------------------------------------------------------------------
# 6. 试跑选样规则（确定性；12 篇覆盖 8 种事件类型与 4 个类目）
# --------------------------------------------------------------------------
# 类目配额：刻意做成「覆盖优先」——12 篇无法同时按表 15-E 的文本块占比分配
# （公告 80.6%、财经新闻 11.2%、政策文件 5.7%、监管公开信息 2.6%）又保住每个类目
# 至少 1 篇，故非公告三类各留出 3／2／1 篇，公告占 6 篇。
PILOT = {
    "doc_count": 12,
    "category_quota": {"公告": 6, "财经新闻": 3, "政策文件": 2, "监管公开信息": 1},
    "category_order": ["公告", "财经新闻", "政策文件", "监管公开信息"],
    "event_type_order": EVENT_TYPES,      # 本体固定顺序，作为覆盖扫描顺序
    # 事件类型的「沉淀类目」：政策落在政策文件池、监管落在监管公开信息池，
    # 其余 6 类落在公司挂钩池（公告／财经新闻）；首选类目无候选时跨类目回退。
    "preferred_category": {
        "业绩": "公告", "监管": "监管公开信息", "股权": "公告", "投资并购": "公告",
        "重大合同": "公告", "产品": "公告", "政策": "政策文件", "重大经营": "公告",
    },
    # 类目补齐时的「材料充足度」门槛：优先选正文 ≥ 本值的候选，
    # 避免只抽到一行快讯（v2.1 里有 83 与 110 字符的业绩类快讯）。
    "min_doc_chars": 300,
    "assertions": [
        "恰好选出 doc_count 篇，且 doc_id 不重复",
        "4 个类目各至少 1 篇",
        "8 种事件类型各至少 1 篇（按冻结的标题级代理正则命中，见 EVENT_TYPE_TITLE_PATTERNS）",
    ],
}

# 事件类型的标题级／正文级代理关键词集（冻结；一篇可命中多类，故各列之和大于篇数）。
EVENT_TYPE_TITLE_PATTERNS = {
    "业绩": r"业绩预告|业绩快报|预增|预减|扭亏|净利润|年度业绩|半年度业绩|前三季度业绩",
    "监管": r"处罚|监管|警示|问询|立案|通报|纪律处分|监管函",
    "股权": (r"股权激励|限制性股票|回购|增持|减持|质押|权益变动|要约收购|股权转让|"
             r"定向增发|非公开发行|发行股票|可转换公司债券|配股"),
    "投资并购": r"收购|并购|重大资产重组|资产购买|对外投资|增资扩股|设立.*公司",
    "重大合同": r"中标|重大合同|订单|框架协议|供货|签约|签订.*合同",
    "产品": (r"临床试验|注册证|医疗器械注册|药品注册|上市许可|获批上市|新产品|首台|投产|量产|"
             r"取得.*批件|获得.*批准"),
    "政策": r"政策|办法|规划|指导意见|实施方案|通知|条例",
    "重大经营": r"重大经营|经营合同|中标|停产|复产|重大事项",
}
# 产品组的再融资污染排除（与第 5 阶段 EVENT_FIRST 的 exclude_pattern 同一口径）：
# 标题命中「发行／股票／债券／募集／上市公告书／可转换」即整条剔除。
PRODUCT_EXCLUDE_PATTERN = r"发行|股票|债券|募集|上市公告书|可转换"

# 9 条核心关系的正文级代理关键词（算「有没有证据」，不是抽取结果）。
RELATION_BODY_PATTERNS = {
    "HAS_EXECUTIVE": r"董事|高管|任职|辞职",
    "ISSUED_BY": r"证监会|交易所|政府|国务院|委员会|管理局",
    "RELATED_TO": r"依据|贯彻|落实",
    "BELONGS_TO": r"行业|产业",
    "CUSTOMER_OF": r"客户",
    "SUPPLIES": r"供应商|供货商",
    "COMPETES_WITH": r"竞争对手|同业竞争|经销商",
    "PARTICIPATES_IN": r"参与|出席",
    "EVIDENCED_BY": None,                 # 结构性关系，不依赖正文
}

# 覆盖性重算的对照值（抄自《15》表 15-C／15-D／15-E 的声明值，**只用于比对**，
# 不参与抽取。重算值与声明值不一致时以重算值为准并在报告中说明差异原因。
TASK_BOOK_TABLES = {
    "table_15C": {"company_list_ge2": 66, "subject_companies_ge2": 9},
    "table_15D": {
        "公告标题级": {"业绩": 21, "股权": 46, "投资并购": 1, "重大合同": 100,
                   "产品": 102, "重大经营": 60, "政策": 45, "监管": 1},
        "公告外监管标题级": 21,
        "正文级": {"SUPPLIES": 32, "CUSTOMER_OF": 88, "COMPETES_WITH": 9},
    },
    "table_15E": {
        "公告": {"docs": 556, "chunks": 4042, "chunk_share": 0.806, "chunks_per_doc": 7.27},
        "政策文件": {"docs": 30, "chunks": 284, "chunk_share": 0.057, "chunks_per_doc": 9.47},
        "财经新闻": {"docs": 103, "chunks": 563, "chunk_share": 0.112, "chunks_per_doc": 5.47},
        "监管公开信息": {"docs": 20, "chunks": 129, "chunk_share": 0.026, "chunks_per_doc": 6.45},
        "合计": {"docs": 709, "chunks": 5018, "chunk_share": 1.0, "chunks_per_doc": 7.08},
    },
}

# 缓存与产物的 schema 版本（改字段名必须同步改这里，否则复跑对不上）。
CACHE_SCHEMA = "stage6-extract-cache-1.0"
RECORD_SCHEMA = "stage6-pilot-record-1.0"


# --------------------------------------------------------------------------
# 7. 小工具（各脚本共用；参数逻辑不在这里）
# --------------------------------------------------------------------------
def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_json(obj) -> str:
    """确定性序列化：键排序、UTF-8、不转义中文，用于哈希与逐字节比对。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_dataset():
    """读 v2.1 的 `clean\\documents.jsonl` 与 `chunks\\chunks.jsonl`（只读）。"""
    docs, chunks = [], []
    with open(DOCS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                docs.append(json.loads(line))
    with open(CHUNKS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return docs, chunks
