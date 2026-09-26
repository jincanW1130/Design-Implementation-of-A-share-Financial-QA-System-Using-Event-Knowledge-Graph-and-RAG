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
#   `deepseek-v4-pro`；环境变量 `STAGE6_EXTRACT_MODEL` 的取值 `deepseek-v4-flash` **不在列表里**，
#   但可作为对话补全的请求模型使用，**响应体的 `model` 字段解析为 `deepseek-flash`**
#   ——即端点把别名静默解析到了 `deepseek-flash`。这一条必须如实登记：
#   `model_default` 是请求值，`model_pinned` 是实测被解析到的模型 id，
#   每次调用的 `model_resolved` 逐篇写进缓存，与 `model_pinned` 不一致时记
#   `model_pinning_warning`（见 extract.py），不静默放过。
LLM = {
    "provider": "OpenAI 兼容的对话补全端点（openai 2.44.0 客户端）",
    "base_url_env": "LLM_BASE_URL",
    "base_url_default": "https://api.deepseek.com/v1",
    # 只认项目自己的变量名，**不回退到通用名 `LLM_MODEL`**：运行环境（DSH）会用
    # `LLM_MODEL` 做自己的模型路由，一旦撞名就让 709 篇主抽取缓存的键全部失配
    # （2026-09-26 实测过一次：镜像重跑抽出空集、12 项验收连锁变红）。
    "model_env": "STAGE6_EXTRACT_MODEL",
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
    """只写**读取方式**：密钥按以下顺序取，取值不进仓库、不写日志、不进导出物。

    1. 环境变量 `LLM_API_KEY`；
    2. 与 config.py 同目录的 `config.local.json` 的 `api_key` 字段
       —— 该文件名已被 `.gitignore` 的 `config.local.*` 覆盖，不入公开仓库。

    之所以要有第二条：运行环境（DSH）自带一份 Process 级环境，**它启动的子进程继承的是
    那份环境而不是用户级环境**，因此只设用户级变量时脚本侧读不到（2026-09-26 实测）。
    两条都不就位时按《15》第十一节 阻断（抛异常并非零退出），
    绝不用占位文本或模型编造的文本冒充实测抽取结果。
    """
    # 哨兵：验收脚本的镜像重跑会设它，**先于任何密钥来源**拒绝——
    # 否则「有本地配置文件」时摘掉环境变量也拦不住调用，重放可能偷偷打接口。
    if (os.environ.get("STAGE6_FORBID_MODEL_CALLS") or "").strip() == "1":
        raise RuntimeError(
            "STAGE6_FORBID_MODEL_CALLS=1：本次为**重放**，禁止调用模型。"
            "缓存未命中即视为失败，不得回退到接口。"
        )
    name = LLM["api_key_env"]
    value = (os.environ.get(name) or "").strip()
    if not value:
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.json")
        try:
            with open(local, encoding="utf-8") as fh:
                value = str((json.load(fh) or {}).get("api_key") or "").strip()
        except (OSError, ValueError):
            value = ""
    if not value:
        raise RuntimeError(
            "密钥未就位（环境变量 %s 与同目录 config.local.json 都没有）：抽取必须调用模型接口，"
            "按《15》第十一节 阻断，不得用占位文本或编造文本充数。" % name
        )
    return value


def base_url() -> str:
    """端点：优先环境变量，缺省用本文件固化的取值（端点不是密钥，可以写进配置）。"""
    return (os.environ.get(LLM["base_url_env"]) or LLM["base_url_default"]).strip()


def model_requested() -> str:
    """请求用的模型 id：只认项目自己的环境变量 `STAGE6_EXTRACT_MODEL`，缺省用本文件固化的取值。

    刻意**不**回退到通用名 `LLM_MODEL`——运行环境会设置同名变量做自己的模型路由，
    回退等于把缓存键交给外部环境，撞名就全库失配。
    """
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


# ==========================================================================
# 9. T4～T7：实体消歧／事件去重／图谱写入与导出（2026-09-25 追加）
# ==========================================================================
# 本节编号为 **9**（第 8 节是同日在文件末尾追加的「T3 全量运行的产物落点」，
# 由并行会话追加；两节都只是**追加**，第 1～7 节的既有键一个都没有改动
# ——另有进程在读它们）。写作顺序不影响 Python 的求值，但读的时候按编号找。
# 本节只放 T4～T7 的参数与 schema 常量，取值依据如下，不新增本体、不新增字段：
#
# * 消歧规则与事件去重四条件：《10-系统总体设计（第四阶段）》第4.5.4节（＝《02》第9.2节）。
#   实体对齐**以 stock_code 为锚**：先与别名表匹配，匹配成功归并到对应的 stock_code 节点，
#   匹配失败进入待消歧列表；事件去重按 event_type＋参与主体＋时间窗口＋触发词相似度四条件
#   同时满足时合并，合并后保留全部证据文档。
# * 证据属性口径与 9 条关系的端点／额外属性：第4.5.2节 的表 4-9（已在第 3 节 RELATION_SCHEMA）。
# * 导出物四件套的落点与排序：《15》第4.3节；逐字节一致与「不含正文」：《15》第五节 硬约束 8、11。
# * 编号显式分配：《15》第五节 硬约束 9（event_id／policy_id／institution_id／person_id 由本阶段
#   一次性分配并固化，不依赖数据库自增）——按 `代码\\抽取与图谱\\README.md` 第七节，由
#   `write_graph.py`（T6）分配。
#
# 目录口径：《15》第4.2节 要求 T4／T5 的产物「落缓存目录」、第4.3节 要求 T6 的导出物落
# `阶段06-事件抽取与知识图谱\\图谱导出\\v2.1\\`。试跑（pilot）不改交付物目录，全部产物落
# `阶段06-事件抽取与知识图谱\\_试跑_图谱管线\\`（与 `代码\\抽取与图谱\\_试跑\\` 那份 T1 记录分开）。

GRAPH_PIPELINE = {
    "profile_roots": {
        # pilot：试跑专用目录，不是交付物；v21：按《15》第4.2／4.3节 落缓存目录与导出目录。
        "pilot": os.path.join(STAGE_DIR, "_试跑_图谱管线"),
        "v21": os.path.join(CACHE_DIR, "图谱管线"),
    },
    "export_roots": {
        "pilot": os.path.join(STAGE_DIR, "_试跑_图谱管线", "图谱导出"),
        "v21": GRAPH_EXPORT_DIR,
    },
    # T4～T7 的**唯一输入**是 extract.py（T3）解析后的抽取结果（一行一篇）；
    # pilot 落 `OUTPUT_FILES["extracted"]`、v21 落 `FULL_OUTPUT_FILES["extracted"]`
    # （第 8 节，T3 全量产物与试跑留痕物理隔离）。用函数取值而不是在定义处取，
    # 这样本节的求值顺序与第 8 节的先后无关。
    "extract_records_profiles": {"pilot": "OUTPUT_FILES", "v21": "FULL_OUTPUT_FILES"},
    "extract_records_key": "extracted",
    "subdirs": {"disambig": "消歧", "dedup": "去重"},
    # 文件名（机器可读产物一律 ASCII 名，与第 7 节 OUTPUT_FILES 同风格）。
    "files": {
        "alias_table": "alias_table.json",
        "disambiguation": "disambiguation.json",
        "unresolved": "unresolved.jsonl",
        "merge_log": "merge_log.jsonl",
        "events_merged": "events_merged.jsonl",
        "merge_summary": "merge_summary.json",
        "dedup_self_test": "dedup_self_test.json",
        "nodes": "nodes.csv",
        "edges": "edges.csv",
        "graph_stats": "graph_stats.json",
        "replay_cypher": "replay.cypher",
        "graph_check": "graph_check.json",
        "manifest": "manifest.sha256",
    },
    # 逐字节比对时**排除**的字段（《15》第八节：`generated_at` 与缓存指纹字段单独成行）。
    "excluded_from_byte_compare": ["generated_at", "cache_fingerprint"],
}

# 三个产物 schema 版本（改字段名必须同步改这里，否则复跑对不上）。
DISAMBIG_SCHEMA = "stage6-disambiguation-1.0"
DEDUP_SCHEMA = "stage6-dedup-1.0"
GRAPH_SCHEMA = "stage6-graph-1.0"

# --------------------------------------------------------------------------
# 9.1 T4 实体消歧
# --------------------------------------------------------------------------
DISAMBIG = {
    # 别名表（＝本阶段固化的 105 家配置公司集）的**只读**来源：第 5 阶段已冻结的配置，
    # 只读它的 COMPANIES（code／name／industry／board）。不复制、不改动该文件。
    "alias_source_path": os.path.join(ROOT, "代码", "数据准备", "config.py"),
    "alias_source_attr": "COMPANIES",
    # 「公司注册全称」别名补充（**数据**，不是规则）：2026-09-26 全量实测发现，语料写的是工商
    # 登记全称（万科企业股份有限公司／宝山钢铁股份有限公司／牧原食品集团股份有限公司），而
    # 上面的配置公司集只有**市场简称**（万科A／宝钢股份／牧原股份）；简称不是全称的子串，
    # R2 永远不触发 → 1888 条公司提及只消歧 618 条、105 家里 15 家一条身份都没有。
    # 补充表由 `代码\抽取与图谱\build_company_aliases.py` 建档（巨潮公司概况接口优先、
    # 语料标题 ≥2 篇印证兜底，逐家记录来源与证据；绝不手打），本文件只登记读取方式。
    "registered_names_path": os.path.join(_THIS_DIR, "company_registered_names.py"),
    "registered_names_attr": "REGISTERED_NAMES",
    "registered_names_schema": "stage6-company-registered-names-1.0",
    # 匹配规则（按序求值；规则本身照《10》第4.5.4节「先与别名表匹配…匹配失败进入待消歧列表」）：
    #   R1 精确：归一后的名称 == 别名表里该 code 的任一书写面（简称或注册全称），
    #      或 == 6 位股票代码；
    #   R2 全称展开：归一后的名称**包含**别名表里该 code 的任一书写面，且残余串（去掉该次出现后的前后缀）
    #      不含任何一个「不同主体限定词」——「上海电气集团股份有限公司」命中 601727，
    #      而「上海电气控股集团有限公司」因残余含「控股」判为**另一个主体**，进待消歧清单。
    #   命中多个不同代码 → 待消歧（ambiguous_alias）。
    #   归一化只动空白与最外层包裹字符，不做大小写折叠、不做模糊匹配、不做编辑距离。
    #   ⚠ 规则本身（两条、判定顺序、限定词清单、归一化口径）**未改**：注册全称只是往别名表里
    #     多加书写面，即《15》「待消歧清单」要喂回别名表的那一类数据。
    "match_rules": ["R1_exact_name_or_code", "R2_full_name_contains_short_name"],
    "distinct_entity_markers": ["控股", "投资", "实业", "资本", "集团控股"],
    "min_short_name_chars": 2,          # 防止过短简称把无关名称吞进来
    "strip_outer_chars": "《》〈〉<>【】〔〕“”‘’\"'（）()",
    # Company 节点的 exchange 属性：表 4-8 要求，配置里只有 board（板块），按板块映射（可复核）。
    "exchange_by_board": {
        "沪市主板": "上交所", "科创板": "上交所",
        "深市主板": "深交所", "创业板": "深交所",
        "北交所": "北交所",
    },
    # 未命中的公司（不在这 105 家里）按《10》第4.5.4节 进待消歧清单，**暂不写入图谱**；
    # 引用它们的关系边一并跳过并计数（本键只登记口径，不改本体）。
    "unresolved_company_policy": "pending_confirmation_exclude_from_graph",
    # Company 之外的四类实体没有 stock_code 锚点：《10》第4.5.1节 只给了 stock_code 的锚法，
    # 这里取**同类型 + 同名（归一化后）即同一实体**的最小规则，不做跨写法归并（不猜）。
    "non_company_rule": "same_type_same_normalized_name",
    "identity_key_separator": ":",
}

# --------------------------------------------------------------------------
# 9.2 T5 事件去重（四项条件同时满足才合并）
# --------------------------------------------------------------------------
DEDUP = {
    "conditions": ["event_type", "participants", "time_window", "trigger_similarity"],
    # 条件 2 参与主体：按《10》第4.5.2节「事件参与主体统一由 PARTICIPATES_IN 关系与 ISSUED_BY
    # 关系表达」，参与主体集合 = PARTICIPATES_IN 的起点 ∪ ISSUED_BY 的终点（规范化后的身份键）。
    # 取**集合相等**（最保守）；任一端点的身份未消歧 → 本条件不成立（不在未消歧的实体上做去重）。
    "participants_rule": "set_equality_of_participates_in_heads_and_issued_by_tails",
    "participants_relations": ["PARTICIPATES_IN", "ISSUED_BY"],
    # 条件 3 时间窗口：|event_time 差| ≤ 本值（天）。两侧都必须有日期；缺失即不成立——
    # T3 的固定口径是「不能确定到日时写 null，绝不猜测」，故不用发布时间顶替。
    "time_window_days": 7,
    "time_window_requires_both_dates": True,
    # 条件 4 触发词相似度：T3 未产出 trigger（README 第 5 节：trigger 只作调试字段），
    # 故取 event_name 的**字符二元组 Jaccard**（确定性、无随机、无外部依赖），阈值见下。
    "similarity_field": "event_name",
    "similarity_metric": "char_bigram_jaccard",
    "similarity_min": 0.5,
    "similarity_round": 3,
    # 合并后：代表成员取**发布时间最早的证据文档**所在成员（并列按 doc_id、再按局部 event_id），
    # event_time 取成员中最早的非空日期（全空则 null），confidence 取成员最大值，
    # 证据文档取全部成员证据文档的**并集**（《10》第4.5.4节：合并后保留全部证据文档）。
    "representative_rule": "earliest_publish_time_then_doc_id_then_local_event_id",
    "event_time_rule": "earliest_non_null_among_members",
    "confidence_rule": "max_rounded_3",
    "evidence_rule": "union_of_member_evidence_docs",
    "linkage": "union_find_single_linkage",
    # 自检（不是交付物）：用真实缓存里的一条事件复制成第二篇文档，验证「合并后保留全部证据文档」。
    "self_test": {
        "enabled": True,
        "doc_id_offset": 900000,        # 合成文档的 doc_id（偏移量确定性、不与真实 doc_id 冲突）
        "note": "合成夹具只用于自检；不进导出物、不进合并日志，只写 dedup_self_test.json。",
    },
}

# --------------------------------------------------------------------------
# 9.3 T6 图谱写入与导出
# --------------------------------------------------------------------------
GRAPH = {
    # 编号显式分配（硬约束 9）：Company／Document 直接用本体标识，其余四类按确定性顺序编号。
    "id_rule": ("Company=stock_code；Document=doc_id；Person／Institution／Policy／Industry／Event "
                "按（类型, 归一化名称）或事件的确定性排序一次性分配 PER／INST／POL／IND／EVT 编号"),
    "id_prefixes": {
        "Person": "PER", "Institution": "INST", "Policy": "POL",
        "Industry": "IND", "Event": "EVT",
    },
    "id_width": 4,                      # PER-0001、EVT-0001（《10》第4.5.1节 的示例即 EVT-0001）
    "list_separator": "|",              # aliases 这类数组属性在 CSV 里的连接符
    # 表 4-8／表 4-9 的属性名，逐字取自《10》第4.5.1／4.5.2节（不新增字段、不改名）。
    "node_columns": [
        "node_id", "label", "name",
        # Company（表 4-8 实体类型 1）
        "stock_code", "company_name", "short_name", "aliases", "exchange",
        # Person（实体类型 2）
        "person_id", "person_name", "role_title",
        # Industry（实体类型 3）
        "industry_code", "industry_name", "level",
        # Institution（实体类型 4）
        "institution_id", "institution_name", "institution_type",
        # Event（实体类型 5：六项核心属性）
        "event_id", "event_type", "event_name", "event_time", "description", "confidence",
        # Policy（实体类型 6）
        "policy_id", "policy_name", "issuer", "publish_date",
        # Document（证据文档标签，不是第七类实体）
        "doc_id", "title", "source", "url", "publish_time", "category",
    ],
    "edge_columns": [
        "head_id", "relation", "tail_id",
        "source_doc_id", "source_chunk_id", "confidence",
        "role", "valid_from", "valid_to",
    ],
    # BELONGS_TO 的 valid_from／valid_to：正文没给日期时留空。**不用发布时间兜底**
    # （兜底等于替正文编一个有效期起点，与 T3「绝不猜测」同源）。
    "belongs_to_validity_fallback": None,
    # 未消歧的公司不写进图谱（《10》第4.5.4节：人工确认后再写入图谱）。
    "include_unresolved_entities": False,
    # 导出物**只含编号、类型、名称、证据编号与置信度，不复制正文**（《15》第4.3节）：
    # 本清单里的字段一律不写进导出物；`quote`／`note` 是正文或调试信息，明确排除。
    "forbidden_export_fields": ["quote", "quote_match_count", "note", "content", "response_text"],
    # 正文不外泄的机器核验口径：任取 v2.1 文本块 content 的一个该长度的子串，
    # 都不得出现在导出物文件里（《15》第八节「导出物不复制正文」）。
    "body_text_check": {"probe_substring_chars": 100, "probe_chunks": 200, "seed": 20260925},
    # SELECT/约束与索引照抄《10》第4.5.3节（7 条唯一性约束 ＋ 3 条索引），逐条写进 replay.cypher。
    "constraints": [
        "CREATE CONSTRAINT uk_company_stock FOR (c:Company) REQUIRE c.stock_code IS UNIQUE",
        "CREATE CONSTRAINT uk_person FOR (p:Person) REQUIRE p.person_id IS UNIQUE",
        "CREATE CONSTRAINT uk_industry FOR (i:Industry) REQUIRE i.industry_code IS UNIQUE",
        "CREATE CONSTRAINT uk_institution FOR (n:Institution) REQUIRE n.institution_id IS UNIQUE",
        "CREATE CONSTRAINT uk_event FOR (e:Event) REQUIRE e.event_id IS UNIQUE",
        "CREATE CONSTRAINT uk_policy FOR (p:Policy) REQUIRE p.policy_id IS UNIQUE",
        "CREATE CONSTRAINT uk_document FOR (d:Document) REQUIRE d.doc_id IS UNIQUE",
        "CREATE INDEX idx_event_time FOR (e:Event) ON (e.event_time)",
        "CREATE INDEX idx_event_type FOR (e:Event) ON (e.event_type)",
        "CREATE INDEX idx_doc_publish FOR (d:Document) ON (d.publish_time)",
    ],
}

# --------------------------------------------------------------------------
# 9.4 T7 入口
# --------------------------------------------------------------------------
RUN_ALL = {
    # 阶段顺序照《15》第4.2节：extract → disambiguate → dedup_events → write_graph。
    "stages": [
        {"name": "extract", "script": "extract.py", "label": "实体与事件抽取（T3）"},
        {"name": "disambiguate", "script": "disambiguate.py", "label": "实体消歧（T4）"},
        {"name": "dedup_events", "script": "dedup_events.py", "label": "事件去重（T5）"},
        {"name": "write_graph", "script": "write_graph.py", "label": "图谱写入与导出（T6）"},
    ],
    # 缓存齐全时入口脚本**不得**调用模型：extract 全命中缓存时 api_calls_total 必须为 0。
    "max_api_calls_on_replay": 0,
    "log_first": "运行日志_首跑.txt",
    "log_second": "运行日志_复跑.txt",
}

# --------------------------------------------------------------------------
# 9.5 T4～T7 共用的取值函数（只做路径解析与归一化，不放参数逻辑）
# --------------------------------------------------------------------------
def extract_records_path(profile: str) -> str:
    """T4～T7 的唯一输入：extract.py 解析后的抽取结果（一行一篇）。

    pilot 取 `OUTPUT_FILES["extracted"]`，v21 取 `FULL_OUTPUT_FILES["extracted"]`
    （第 8 节：T3 的全量产物与 T1 的试跑留痕物理隔离）。
    """
    table_name = GRAPH_PIPELINE["extract_records_profiles"].get(profile)
    table = globals().get(table_name) if table_name else None
    if not isinstance(table, dict) or GRAPH_PIPELINE["extract_records_key"] not in table:
        raise KeyError("profile=%s 的抽取结果落点未在 config 中登记" % profile)
    return table[GRAPH_PIPELINE["extract_records_key"]]


def pipeline_paths(profile: str) -> dict:
    """按 profile 解析 T4～T7 的目录与文件落点（不建目录，只给路径）。"""
    work_root = GRAPH_PIPELINE["profile_roots"][profile]
    export_dir = GRAPH_PIPELINE["export_roots"][profile]
    names = GRAPH_PIPELINE["files"]
    disambig_dir = os.path.join(work_root, GRAPH_PIPELINE["subdirs"]["disambig"])
    dedup_dir = os.path.join(work_root, GRAPH_PIPELINE["subdirs"]["dedup"])
    return {
        "profile": profile,
        "work_root": work_root,
        "disambig_dir": disambig_dir,
        "dedup_dir": dedup_dir,
        "export_dir": export_dir,
        "extract_records": extract_records_path(profile),
        "alias_table": os.path.join(disambig_dir, names["alias_table"]),
        "disambiguation": os.path.join(disambig_dir, names["disambiguation"]),
        "unresolved": os.path.join(disambig_dir, names["unresolved"]),
        "merge_log": os.path.join(dedup_dir, names["merge_log"]),
        "events_merged": os.path.join(dedup_dir, names["events_merged"]),
        "merge_summary": os.path.join(dedup_dir, names["merge_summary"]),
        "dedup_self_test": os.path.join(dedup_dir, names["dedup_self_test"]),
        "nodes": os.path.join(export_dir, names["nodes"]),
        "edges": os.path.join(export_dir, names["edges"]),
        "graph_stats": os.path.join(export_dir, names["graph_stats"]),
        "replay_cypher": os.path.join(export_dir, names["replay_cypher"]),
        "graph_check": os.path.join(work_root, names["graph_check"]),
        "manifest": os.path.join(work_root, names["manifest"]),
        "log_first": os.path.join(work_root, RUN_ALL["log_first"]),
        "log_second": os.path.join(work_root, RUN_ALL["log_second"]),
    }


def normalize_entity_name(name) -> str:
    """实体身份比对用的归一化：只动空白与**最外层包裹字符**。

    去掉全部空白（含全角空格）后，反复剥掉最外层的书名号／引号／括号，
    其余字符一律照原样（不做大小写折叠、不做标点归一、不做模糊匹配）。
    比 T3 的证据定位（`evidence_key`，只去空白）多一步剥壳，是为了让
    「《证券法》」与「证券法」这类**同一条政策的两种书写**在身份层对齐。
    """
    import re as _re
    text = _re.sub(r"[\s　]+", "", str(name or ""))
    outer = DISAMBIG["strip_outer_chars"]
    pairs = [(outer[i], outer[i + 1]) for i in range(0, len(outer) - 1, 2)]
    changed = True
    while changed and len(text) >= 2:
        changed = False
        for left, right in pairs:
            if text.startswith(left) and text.endswith(right):
                text = text[1:-1]
                changed = True
                break
    return text


def round_confidence(value):
    """置信度统一四舍五入到 3 位小数（与 T3 的可重放口径一致）。"""
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# 8. T3 全量运行的产物落点（2026-09-25 追加，仅新增键；上面任何既有取值未改动）
# --------------------------------------------------------------------------
# 依据：《15-第6阶段任务书》第4.2节 的「小规模先行」纪律——`PILOT_DIR`（`_试跑\`）是
# T1 小规模验证的**留痕**，T3 的全量产物必须与它物理隔离，否则一次全量运行就会覆盖掉
# 试跑记录。故 `--profile pilot` 仍落 `OUTPUT_FILES`（取值与行为不变），
# `--profile v21` 落 `FULL_OUTPUT_FILES`（`_全量\<dataset_version>\`）。
# 两处与缓存一样**都不是交付物、不入仓库**（`.gitignore` 应覆盖 `代码/抽取与图谱/_全量/`）。
FULL_RUN_DIR = os.path.join(_THIS_DIR, "_全量", DATASET_VERSION)
FULL_OUTPUT_FILES = {
    "selection": os.path.join(FULL_RUN_DIR, "selection.json"),
    "coverage": os.path.join(FULL_RUN_DIR, "coverage.json"),
    "extracted": os.path.join(FULL_RUN_DIR, "extracted.jsonl"),
    "rejected": os.path.join(FULL_RUN_DIR, "rejected.jsonl"),
    "run_history": os.path.join(FULL_RUN_DIR, "run_history.jsonl"),
    "verify": os.path.join(FULL_RUN_DIR, "verify.json"),
    "manifest": os.path.join(FULL_RUN_DIR, "manifest.sha256"),
}
# 全量运行的完整控制台输出**不由脚本写**，而是由启动命令把 stdout／stderr 重定向到这里
# （脚本内不写日志文件，避免与「产物确定性」混在一起）；此键只登记落点。
FULL_RUN_LOG = os.path.join(FULL_RUN_DIR, "运行日志_全量.txt")

# ==========================================================================
# 10. 定向时间补抽（2026-09-26 追加；**只新增键**，第 1～9 节的既有取值一个都没有改动）
# ==========================================================================
# 依据与口径（两级抽取的第二级）：
# * 第一级（T3，`extract.py`）的固定口径是「正文不能确定到日时写 null，绝不猜测」；全量实测
#   989／1649 条事件的 `event_time` 为 null。主抽取缓存（`_抽取缓存\<version>\<doc_id>.json`）
#   与 `extract.py` 因此**一字不动**（重放逐字节不变）。
# * 第二级只对 `event_time` 为 null 的事件做一次**定向补抽**：把事件类型／名称／证据引文／
#   引文周围的**有界窗口**／文档发布时间给模型，只问「这个事件的日期 ＋ 依据标记」。
# * 结果一律带 `event_time_basis`，取值只能是 `stated`（正文明确写出年月日）／
#   `year_from_publish`（只给月日，按发布时间锚定年份）／`null`（窗口里确实没有可归属的日期）。
#   日期先在**窗口原文**上复核（含「数字与汉字之间被空格切开」的写法），复核不过一律记 `null`，
#   绝不猜测、绝不编日期。
# * 缓存独立：`_抽取缓存\<version>\时间补抽\{event_id}.json`（存原始返回、模型、prompt 版本与
#   输入 sha256）；复跑全部命中缓存时**零模型调用**，不需要密钥也不需要网络。
EVENT_TIME_BACKFILL = {
    "schema": "stage6-time-backfill-1.0",
    "cache_schema": "stage6-time-backfill-cache-1.0",
    # 端点与模型：与第 2 节 `LLM` 同一套环境变量与缺省值（这里只登记读取方式，不含密钥）。
    "provider_note": "与 config.LLM 同端点、同模型（OpenAI 兼容对话补全）",
    "base_url_env": LLM["base_url_env"],
    "base_url_default": LLM["base_url_default"],
    "model_env": LLM["model_env"],
    "model_default": LLM["model_default"],
    "model_pinned": LLM["model_pinned"],
    "api_key_env": LLM["api_key_env"],
    "temperature": 0,
    "max_tokens": 512,
    "response_format": "json_object",
    "timeout_seconds": 180.0,
    "prompt_version": "stage6-time-backfill-v1.0",
    # 压缩重试：**只在主尝试被输出上限截断（finish_reason == "length"）时**触发一次。
    # 2026-09-26 实测：本端点把 `deepseek-v4-flash` 解析为推理型模型，max_tokens=512 时
    # 部分请求把 512 个完成 token 全用在思考上、正文为空（finish_reason="length"）；
    # 与 2.2 节 `LLM["fallback"]` 同一套路：关掉思考（reasoning_effort="none"）再问一次，
    # 两次原始返回都进缓存；被截断的缓存条目视为**未收敛**，下次运行自动补齐。
    "fallback": {
        "trigger_reason": "length",
        "max_attempts": 2,
        "max_tokens": 1024,
        "reasoning_effort": "none",
    },
    # 窗口定义（README 第十一节 同步登记）：以证据引文在**证据块**里的匹配位置为中心，左右
    # 各取 window_chars 个字符；窗口贴到该证据块边界时，允许向同文档的相邻块扩展，每侧最多
    # neighbor_chars 个字符。窗口因此是**有界**的（≤ 2×window_chars ＋ 引文长度 ＋ 2×neighbor_chars）。
    "window_chars": 500,
    "neighbor_chars": 300,
    "quote_max_chars": 200,
    "window_rule_note": (
        "窗口＝证据块内以引文为中心的前后各 window_chars 个字符；贴边时同文档前／后各一块最多 "
        "neighbor_chars 个字符补进来。窗口写进缓存条目的 window_sha256，便于逐条复核。"
    ),
    # 日期书写形式：接受 4 种（与 TIME.accepted_income_forms 同一套），并额外接受
    # 「数字与汉字之间被空格切开」的语料写法（实测 `司2026 年8 月27 日至28 日召开的…`）。
    "spaced_form_note": (
        "`2026 年8 月27 日`（数字与 CJK 之间夹空格）与 `2026年8月27日`／`2026-08-27`／"
        "`2026/8/27`／`2026.8.27` 等价；复核在**去掉全部空白**的窗口副本上比对，"
        "但**不做**大小写折叠、标点归一、模糊匹配或编辑距离。"
    ),
    # 年份锚定规则（确定性、文档化、不猜）：窗口只给月日时，年份取发布时间锚定值。
    "year_from_publish_rule": "月日 ＋ 发布时间锚定：月 ≤ 发布月 → 发布年；否则 发布年 − 1",
    "year_from_publish_note": (
        "锚定年份是**推断值**，因此 `event_time_basis` 记 `year_from_publish` 而不是 `stated`；"
        "月日必须在窗口里**独立出现**（前面不带 4 位年份、后面不带数字），否则不认定。"
    ),
    "basis_values": ["stated", "year_from_publish", "null"],
    "basis_definitions": {
        "stated": "正文（窗口）明确写出年月日，且日期在窗口里复核得到",
        "year_from_publish": "窗口只给月日，年份按第 10 节的锚定规则从 publish_time 推出",
        "null": "窗口内确实没有可归属到该事件的日期；事件保持 event_time=null",
    },
    # 缓存：与主抽取缓存同一个 work root（`_抽取缓存\<version>\`）下的**独立子目录**。
    "cache_dir": os.path.join(CACHE_DIR, "时间补抽"),
    "cache_file_pattern": "{event_id}.json",
    "pacing": {
        "min_interval_seconds": PACING["min_interval_seconds"],
        "max_retries": PACING["max_retries"],
        "backoff_base_seconds": PACING["backoff_base_seconds"],
        "backoff_max_seconds": PACING["backoff_max_seconds"],
    },
    # 产物落点：与 T3 的全量产物同层（不是交付物、不入仓库），逐字节可重放。
    "outputs": {
        "pilot": {
            "overlay": os.path.join(PILOT_DIR, "event_time_backfill.json"),
            "report": os.path.join(PILOT_DIR, "event_time_backfill_report.json"),
            "measure": os.path.join(PILOT_DIR, "时间覆盖_度量.json"),
        },
        "v21": {
            "overlay": os.path.join(FULL_RUN_DIR, "event_time_backfill.json"),
            "report": os.path.join(FULL_RUN_DIR, "event_time_backfill_report.json"),
            "measure": os.path.join(FULL_RUN_DIR, "时间覆盖_度量.json"),
        },
    },
}


def time_backfill_paths(profile: str) -> dict:
    r"""定向时间补抽（T3.5）的落点：pilot 落 `_试跑\`、v21 落 `_全量\<version>\`（与 T3 同层）。"""
    table = EVENT_TIME_BACKFILL["outputs"].get(profile)
    if not table:
        raise KeyError("profile=%s 的时间补抽落点未在 config 中登记" % profile)
    return {
        "profile": profile,
        "cache_dir": EVENT_TIME_BACKFILL["cache_dir"],
        "overlay": table["overlay"],
        "report": table["report"],
        "measure": table["measure"],
        "extract_records": extract_records_path(profile),
    }


def time_backfill_base_url() -> str:
    """补抽端点：优先环境变量，缺省用本节固化的取值（端点不是密钥，可以写进配置）。"""
    return (os.environ.get(EVENT_TIME_BACKFILL["base_url_env"])
            or EVENT_TIME_BACKFILL["base_url_default"]).strip()


def time_backfill_model() -> str:
    """补抽请求的模型 id：只认项目自己的环境变量 `STAGE6_EXTRACT_MODEL`，缺省用本节固化的取值。"""
    return (os.environ.get(EVENT_TIME_BACKFILL["model_env"])
            or EVENT_TIME_BACKFILL["model_default"]).strip()


def time_backfill_api_key() -> str:
    """只写**读取方式**：密钥只来自环境变量，不入仓库、不落盘、不进日志。"""
    name = EVENT_TIME_BACKFILL["api_key_env"]
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(
            "环境变量 %s 未就位：定向时间补抽需要调用模型接口，按《15》第十一节 阻断，"
            "不得用占位文本或编造日期充数（缓存全部命中时本函数不会被调用）。" % name
        )
    return value


# ==========================================================================
# 11. 人工确认的实体写入图谱（2026-09-26 追加；**只新增键**，第 1～10 节取值未改）
# ==========================================================================
# 依据：《10-系统总体设计（第四阶段）》第4.5.4节「匹配失败进入待消歧列表，**人工确认后再写入
# 图谱**」。确认结果是**数据，不是代码**：人可编辑的确认文件由 `待人工确认清单.md` 播种，
# `write_graph.py` 只读它，把 `confirmed: true` 的条目写成**自己的节点**（节点名＝书写面；
# 因为没有解析出 stock_code，所以不填 stock_code），从而让以它们为端点的边得以写入。
# * 未确认条目（`confirmed: false` 或缺少该字段）一律继续排除，与
#   `DISAMBIG["unresolved_company_policy"]` 的既有口径一致。
# * 同一个确认名称只产生一个节点（按归一化名称去重）；确认名称**不得**并进配置公司
#   （命中别名表书写面时拒绝写入并计数上报，绝不做「名字合并」）。
# * 落点与命名：确认文件放交付物导出目录（与四件套同目录）；`write_graph.py` 在
#   `graph_stats.json` 里登记「人工确认贡献」的节点数／边数与文件 sha256，效果可审计。
HUMAN_CONFIRMATION = {
    "schema": "stage6-human-confirmation-1.0",
    "filename": "人工确认清单.json",
    "field": "confirmed",
    "node_id_prefix": "HCONF",
    "seeded_from": "阶段06-事件抽取与知识图谱\\图谱导出\\v2.1\\待人工确认清单.md",
    "identity_key_prefix": "human_confirmed",
    "note": (
        "确认条目＝《10》第4.5.4节 的待消歧主体经人工确认后的最终判定；节点编号按归一化名称"
        "确定性排序分配 HCONF-####，不依赖数据库自增，也不与 Company（stock_code）编号冲突。"
    ),
}


def human_confirmation_path(profile: str) -> str:
    """确认文件的落点：与图谱导出物同目录（pilot 落试跑导出目录，v21 落交付物导出目录）。"""
    export_dir = GRAPH_PIPELINE["export_roots"][profile]
    return os.path.join(export_dir, HUMAN_CONFIRMATION["filename"])
