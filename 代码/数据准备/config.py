# -*- coding: utf-8 -*-
"""第 5 阶段（数据准备）的唯一参数来源。

本文件是第 5 阶段全部**已冻结决策**的落点：来源、公司、时间窗、编号方案、切分参数、
Embedding 模型、配额、路径。按《12-第5阶段任务书（数据准备）》第2.3节 的 TBD 归属表，
本阶段必须固化的是 Embedding 模型与版本、切分参数、dataset_version／data_cutoff_time 三项。

纪律（《12》第5节 硬约束 5／7、第4.2节）：
  * 切分参数一经封版不得更改，改参数等于换数据集版本；
  * doc_id 与 chunk_id 由本文件显式分配，不依赖数据库自增；
  * 任何脚本都不得绕过本文件写死参数；需要改参数时改本文件并升 dataset_version。

用法：其余脚本一律 `from config import *`（或 `import config`），不得自带默认值。
"""

from __future__ import annotations

import os

# --------------------------------------------------------------------------
# 0. 路径
# --------------------------------------------------------------------------
# 本文件位于 <ROOT>\代码\数据准备\config.py，因此 ROOT 是上溯两级。
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", ".."))

STAGE_DIR = os.path.join(ROOT, "阶段05-数据准备")
DATASET_ROOT = os.path.join(STAGE_DIR, "数据集")
PILOT_ROOT = os.path.join(STAGE_DIR, "_试跑")          # 小规模试跑，不属于交付数据集
TOOL_DIR = os.path.join(ROOT, "工具")

# --------------------------------------------------------------------------
# 1. 数据集版本级元信息（《12》第2.3节：本阶段必须固化）
# --------------------------------------------------------------------------
# v1.1：v1.0 封版后只**新增**一个数据集内部字段 subject_companies（见 第8节），
# 规模、编号、切分、向量与 v1.0 完全一致；v1.0 目录保持不可变（《12》第4.2节）。
DATASET_VERSION = "v2.0"
PIPELINE_VERSION = "pipeline-1.0"

# 数据截止时间：数据集版本级属性，不属于任何表（《02》第10.1节、第10.3节；《12》第5节 硬约束 2）。
# 口径：收录 publish_time 的日期部分 ≤ DATA_CUTOFF_DATE 的文档。
DATA_CUTOFF_DATE = "2026-09-25"
DATA_CUTOFF_TIME = "2026-09-25T23:59:59+08:00"
TIMEZONE = "+08:00"

# 数据集的采集时间窗：下界 = cutoff − 100 天 = 2026-06-17。
# 为什么不是正好 90 天：《12》第5节 硬约束 13 要求覆盖"data_cutoff_time 前**至少** 90 天"。
# 若把下界定在正好 cutoff−90，验收就要求"最早一篇恰好落在 2026-06-27 当天"才算通过，
# 而各来源那一天有没有文完全取决于抓取运气，验收会退化成掷骰子（2026-09-25 实测：
# 分时段铺开后最早一篇落到 2026-07-01，cutoff−earliest＝86 天，卡在 90 天门槛外）。
# 把采集窗放宽到 100 天，既满足"至少 90 天"，又让完整的 [cutoff−90, cutoff] 落在
# 数据集**内部**而不是骑在边界上——相对时间问题因此有边界余量。
WINDOW_START = "2026-06-17"
WINDOW_END = DATA_CUTOFF_DATE
WINDOW_DAYS = 100

# 相对时间区间（《02》第10.3节；《12》第5节 硬约束 13 要求两段都非空）
BUCKET_RECENT = ("2026-08-27", "2026-09-25")   # [cutoff-30d, cutoff]
BUCKET_EARLIER = ("2026-06-17", "2026-08-26")  # [cutoff-100d, cutoff-30d)
# 《02》第10.3节 的"近期"区间 [cutoff-90d, cutoff]，用于回报覆盖情况与验收
ANALYSIS_90_RANGE = ("2026-06-27", "2026-09-25")

# --------------------------------------------------------------------------
# 2. 四类来源（《12》第5节 硬约束 12：只允许这四类，股吧不进入数据集）
# --------------------------------------------------------------------------
CATEGORIES = ["公告", "监管公开信息", "政策文件", "财经新闻"]

# company_list 必须非空的类别（《12》第八节 开工前修订后的口径）。
# 政策文件与监管公开信息多数不涉及特定上市公司，允许 company_list 为空数组，
# 但**不得为 null**，且必须在《13》说明。clean.py 与 check.py 都必须读这一项，
# 不得各自复制一份字面量。
CATEGORIES_REQUIRING_COMPANY = ("公告", "财经新闻")

# category -> 具体来源站点。source 字段存站点名，category 存四类之一。
SOURCES = {
    "公告": {
        "source": "巨潮资讯网",
        "home": "https://www.cninfo.com.cn",
        "access_note": "深交所指定的法定信息披露网站，公告原文为公开披露文件。",
        "rate_limit_seconds": 1.2,
    },
    "监管公开信息": {
        "source": "中国证监会",
        "home": "https://www.csrc.gov.cn",
        "access_note": "证监会官网信息公开栏目，行政处罚决定书等为依法公开的监管文件。",
        "rate_limit_seconds": 1.5,
    },
    "政策文件": {
        "source": "中国政府网",
        "home": "https://www.gov.cn",
        "access_note": "国务院政策文件库，国务院文件（gw）与部门文件（bm）均为公开发布。",
        "rate_limit_seconds": 1.5,
    },
    "财经新闻": {
        "source": "人民网财经/中证网/证券日报网",
        "home": "http://finance.people.com.cn ; https://www.cs.com.cn ; http://www.zqrb.cn",
        "access_note": "正规财经新闻媒体，仅用于学术研究，正文不进入公开仓库。",
        "rate_limit_seconds": 2.0,
    },
}

# 财经新闻的具体站点（source 字段按站点分别填写）
NEWS_SITES = {
    "人民网财经": {
        "entry": "http://finance.people.com.cn/",
        "article_pattern": r"finance\.people\.com\.cn/n1/\d{4}/\d{4}/[^\"']+\.html",
        "date_meta": "publishdate",
    },
    "中证网": {
        "entry": "https://www.cs.com.cn/",
        "article_pattern": r"cs\.com\.cn/[^\"']+\.html",
        "date_meta": "publishdate",
    },
    "证券日报网": {
        "entry": "http://www.zqrb.cn/",
        "article_pattern": r"zqrb\.cn/[^\"']+\.html",
        "date_meta": "publishdate",
    },
}

HTTP = {
    "user_agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "timeout_seconds": 30,
    "max_retries": 3,
    "backoff_seconds": 2.0,
    # 全局抓取上限：控制频率、遵守来源网站访问规范（《12》第5节 硬约束 12、第十节 风险 2）
    "min_interval_seconds": 1.2,
}

# 已实测可用的取数端点（2026-09-25 实测）。原先只写在 README 第四节，现收进 config，
# 避免脚本里散落常量。参数含义见 README 第四节。
ENDPOINTS = {
    "cninfo_topsearch": "https://www.cninfo.com.cn/new/information/topSearch/query",
    "cninfo_query": "https://www.cninfo.com.cn/new/hisAnnouncement/query",
    "cninfo_static": "https://static.cninfo.com.cn/",
    "gov_policy_search": "https://sousuo.www.gov.cn/search-gov/data",
    "gov_policy_types": ["zhengcelibrary_gw", "zhengcelibrary_bm"],
    "csrc_search": "https://www.csrc.gov.cn/searchList/{channel}",
    # 证监会栏目 channelGuid。主来源＝行政处罚；备用＝市场禁入
    #（实测该栏目最新发文早于窗口下界，窗口内 0 篇，仅作备用，不足时须登记）。
    "csrc_channels": {
        "行政处罚": "17d5ff2fe43e488dba825807ae40d63f",
        "市场禁入": "3795869930ca4b70bf55469270a6e641",
    },
}

# --------------------------------------------------------------------------
# 3. 第一版规模：10 家公司（《02》第17节"先小后大"，第一版 10 家／100 篇）
# --------------------------------------------------------------------------
# board 用于覆盖不同板块；cninfo_column 是巨潮公告查询接口的 column 取值。
# subs 是**预先批准的同行业替代公司**：仅当主选公司在时间窗内公告数不足时启用，
# 且必须登记到 reports\skipped.jsonl 与《13》。不得自行另选公司。
COMPANIES = [
    # —— 第一版已用的 10 家（保留，保证版本间连续性）——
    {"code": "000001", "name": "平安银行", "industry": "银行",        "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "000002", "name": "万科A",   "industry": "房地产",      "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "600519", "name": "贵州茅台", "industry": "食品饮料",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600028", "name": "中国石化", "industry": "石油化工",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600276", "name": "恒瑞医药", "industry": "医药生物",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "002594", "name": "比亚迪",   "industry": "汽车",        "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "300750", "name": "宁德时代", "industry": "电力设备",    "board": "创业板",   "cninfo_column": "szse", "subs": []},
    {"code": "002475", "name": "立讯精密", "industry": "电子制造",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "688981", "name": "中芯国际", "industry": "半导体",      "board": "科创板",   "cninfo_column": "sse",  "subs": []},
    {"code": "601012", "name": "隆基绿能", "industry": "光伏",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    # —— 第二版增补 40 家 ——
    # 建筑与工程（重大合同/中标类披露的主要来源，第一版全库 0 篇正缺这一类）
    {"code": "601668", "name": "中国建筑", "industry": "建筑工程",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601390", "name": "中国中铁", "industry": "建筑工程",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601186", "name": "中国铁建", "industry": "建筑工程",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600970", "name": "中材国际", "industry": "建筑工程",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "002051", "name": "中工国际", "industry": "建筑工程",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    # 电力设备与机械
    {"code": "600089", "name": "特变电工", "industry": "电力设备",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600875", "name": "东方电气", "industry": "电力设备",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601727", "name": "上海电气", "industry": "电力设备",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600406", "name": "国电南瑞", "industry": "电力设备",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600031", "name": "三一重工", "industry": "工程机械",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "000338", "name": "潍柴动力", "industry": "工程机械",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    # 通信设备与电子
    {"code": "000063", "name": "中兴通讯", "industry": "通信设备",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "600522", "name": "中天科技", "industry": "通信设备",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601138", "name": "工业富联", "industry": "电子制造",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "002241", "name": "歌尔股份", "industry": "电子制造",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "000725", "name": "京东方A",  "industry": "面板显示",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    # 半导体
    {"code": "603501", "name": "韦尔股份", "industry": "半导体",      "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "002371", "name": "北方华创", "industry": "半导体设备",  "board": "深市主板", "cninfo_column": "szse", "subs": []},
    # 金融
    {"code": "600036", "name": "招商银行", "industry": "银行",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601398", "name": "工商银行", "industry": "银行",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601318", "name": "中国平安", "industry": "保险",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600030", "name": "中信证券", "industry": "证券",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "300059", "name": "东方财富", "industry": "证券",        "board": "创业板",   "cninfo_column": "szse", "subs": []},
    # 房地产与消费
    {"code": "600048", "name": "保利发展", "industry": "房地产",      "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600887", "name": "伊利股份", "industry": "食品饮料",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "000858", "name": "五粮液",   "industry": "食品饮料",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "603288", "name": "海天味业", "industry": "食品饮料",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "002714", "name": "牧原股份", "industry": "农业养殖",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "000333", "name": "美的集团", "industry": "家用电器",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "000651", "name": "格力电器", "industry": "家用电器",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    # 汽车与新能源
    {"code": "601633", "name": "长城汽车", "industry": "汽车",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600104", "name": "上汽集团", "industry": "汽车",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "300274", "name": "阳光电源", "industry": "光伏",        "board": "创业板",   "cninfo_column": "szse", "subs": []},
    {"code": "600438", "name": "通威股份", "industry": "光伏",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    # 资源与材料
    {"code": "601088", "name": "中国神华", "industry": "煤炭",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "601899", "name": "紫金矿业", "industry": "有色金属",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600019", "name": "宝钢股份", "industry": "钢铁",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "600309", "name": "万华化学", "industry": "基础化工",    "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
    {"code": "000792", "name": "盐湖股份", "industry": "基础化工",    "board": "深市主板", "cninfo_column": "szse", "subs": []},
    {"code": "600900", "name": "长江电力", "industry": "电力",        "board": "沪市主板", "cninfo_column": "sse",  "subs": []},
]

# --------------------------------------------------------------------------
# 4. 配额（第一版 100 篇；试跑 20 篇）
# --------------------------------------------------------------------------
# 公告为按公司配额（每家公司 QUOTA_PER_COMPANY 篇）；
# 其余三类为全局配额。
QUOTA_V1 = {
    "公告": None,                # 由 ANNOUNCEMENT_PER_COMPANY × 公司数决定
    "财经新闻": 50,
    "政策文件": 30,
    "监管公开信息": 20,
}
ANNOUNCEMENT_PER_COMPANY = 8     # 8 × 50 家 = 400（第二版）
TARGET_DOC_COUNT_V1 = 500

# 公告的**时段分层抽取**（2026-09-25 增设，开工前修正）。
# 起因：若按 publish_time 降序取前 N 篇，公告会全部挤在窗口右端——实测 10 家公司的
# 近 30 天公告量远大于其余 60 天（如恒瑞医药 30/0、贵州茅台 0/7），数据集的
# [cutoff-90d, cutoff-30d) 一段会被抽空，而《02》第12.2节 的"时间约束＝有"题目
# 正需要这一段的 gold 证据。
# 规则：每家公司先从 BUCKET_RECENT 取 recent 篇、再从 BUCKET_EARLIER 取 earlier 篇；
# 某一时段不足时由另一时段补足，补足情况必须登记到 reports\ 与《13》。
ANNOUNCEMENT_STRATA_V1 = {"recent": 4, "earlier": 4}
ANNOUNCEMENT_STRATA_PILOT = {"recent": 2, "earlier": 1}

QUOTA_PILOT = {
    "公告": 9,                   # 3 家公司 × 3 篇
    "财经新闻": 5,
    "政策文件": 3,
    "监管公开信息": 3,
}
PILOT_COMPANY_COUNT = 3
PILOT_COMPANIES = ["000001", "000002", "600519"]
ANNOUNCEMENT_PER_COMPANY_PILOT = 3
TARGET_DOC_COUNT_PILOT = 20

# 每个相对时间桶的最低文档数（《12》第5节 硬约束 13：两段都必须非空）
MIN_DOCS_PER_TIME_BUCKET = 5

# --------------------------------------------------------------------------
# 5. 编号方案（《12》第5节 硬约束 7：显式分配、稳定、不依赖自增）
# --------------------------------------------------------------------------
# doc_id 按类别分块，便于人工识别与后续扩充：
#   公告 1001+ ／ 财经新闻 2001+ ／ 政策文件 3001+ ／ 监管公开信息 4001+
DOC_ID_BLOCK = {
    "公告": 1000,
    "财经新闻": 2000,
    "政策文件": 3000,
    "监管公开信息": 4000,
}
# 块内序号按 (publish_time 降序, url 升序) 排序后从 1 开始分配，保证可重复。
DOC_ID_STRIDE = 1000             # chunk_id = doc_id * 1000 + chunk_index


def doc_id_for(category: str, seq: int) -> int:
    """按类别与块内序号（1 起）分配 doc_id。"""
    if category not in DOC_ID_BLOCK:
        raise ValueError("未知 category: %r" % category)
    if seq < 1:
        raise ValueError("seq 必须从 1 开始")
    return DOC_ID_BLOCK[category] + seq


def chunk_id_for(doc_id: int, chunk_index: int) -> int:
    """chunk_id 由 doc_id 与块内序号唯一确定（双射，可反查）。"""
    if chunk_index < 0:
        raise ValueError("chunk_index 必须 >= 0")
    if chunk_index >= DOC_ID_STRIDE:
        raise ValueError("单文档文本块数超过 %d，需调整 DOC_ID_STRIDE" % DOC_ID_STRIDE)
    return doc_id * DOC_ID_STRIDE + chunk_index


def split_chunk_id(chunk_id: int):
    """反查：chunk_id -> (doc_id, chunk_index)。"""
    return chunk_id // DOC_ID_STRIDE, chunk_id % DOC_ID_STRIDE


# --------------------------------------------------------------------------
# 6. 切分参数（《12》第2.3节：本阶段必须固化；第5节 硬约束 5：封版后不得更改）
# --------------------------------------------------------------------------
# 单位一律为**字符数**（中文按字符计，不按词计）。
# 目标 400 ／ 上限 512 ／ 下限 128 ／ 重叠 50。
# 重叠 50/400 = 12.5%，只用于衔接上下文，不足以让同一段内容在两个文本块里
# 都构成完整证据（《12》第5节 硬约束 5、《02》第12.7节 第二步"一个文本块只算一个证据"）。
CHUNK = {
    "target_chars": 400,
    "max_chars": 512,
    "min_chars": 128,
    "overlap_chars": 50,
    # 边界优先级：段落 > 句末标点 > 逗号/分号 > 硬切
    "boundary_priority": ["\n\n", "\n", "。", "！", "？", "；", "…", ".", "!", "?", ";"],
    "strip_rules": True,
}

# 文档级过滤：清洗后正文短于该长度的文档整篇跳过（登记到 reports\skipped.jsonl）
MIN_DOC_CHARS = 80

# --------------------------------------------------------------------------
# 公告的**标题排除规则**：定期报告全文不收录（2026-09-25 实测后增设）
# --------------------------------------------------------------------------
# 起因：试跑数据集 521 个文本块里有 364 个来自**同一篇**《贵州茅台2026年半年度报告》
# （正文 11.8 万字符，占 70%）。这会让 Recall@K／Precision@K 退化成
# "有没有命中那篇定期报告"，检索指标失去区分度；而《02》第9.2节 的 8 种事件类型里
# 并没有"发布定期报告"这一类，业绩信息由**业绩预告／业绩快报**类公告承载。
# 处理口径：在**候选阶段排除标题命中下列模式的公告**，不是按长度截断——
# 截断等于改写证据，违反《10》第4.4.6节 的"证据按原文展示"。
EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_V1 = [
    r"年度报告", r"半年度报告", r"季度报告", r"[一二三四]季报",
    r"审计报告", r"内部控制(评价|自我评价|审计)报告",
    r"社会责任报告", r"ESG报告", r"环境、社会及管治报告",
    # 纯格式化的每日／每月披露表单：同一家公司逐日／逐月重复提交，标题相同、内容为模板，
    # 不含事件信息。它们既占掉公告配额，又会在去重环节把同一家公司的多篇压成一篇，
    # 使各公司公告数不均（v1 实测：中国石化入选 5 篇中 3 篇同题被压掉，最终只剩 2 篇）。
    r"翌日披露(报表|表格)", r"证券变动月报表", r"月报表$",
    # 长全文类报告。v1 实测漏网的两类：
    #   《2025年可持续发展报告（英文版）》39.7 万字符＝全库 51.7%；
    #   《港股公告：2026中期报告》《…2026年中期业绩公告》各 8.1 万字符。
    # 「中期报告」是港股对半年度报告的叫法，原来的「半年度报告」模式拦不住。
    r"可持续发展报告", r"中期报告", r"英文版",
]
EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_PILOT = EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_V1

# 单篇文档的长度上限（**采集候选阶段**过滤，不是截断）。
# 语料以"事件型披露"为主体；超过该长度的正文基本都是把整套财务报表或全文附件并进公告的
# 长文档——v1 实测一篇 39.7 万字符的可持续发展报告就占了全库 51.7% 的字符、并直接撑爆了
# 编号步长（单篇超过 1000 个文本块，chunk.py 报错中止）。超过上限的候选在**选入之前**丢弃，
# 由后续候选顶替，因此配额不会被抽空；丢弃明细登记在 raw\_fetch_log.jsonl。
# 一律**排除整篇**，绝不截断——截断等于改写证据（《10》第4.4.6节）。
MAX_DOC_CHARS_FOR_INCLUSION = 60000

# 巨潮公告查询接口**每页最多返回 30 条**（2026-09-25 实测：pageSize 传 50/100/200 均只回 30），
# 因此必须翻页才能看到整个时间窗。中国石化在 100 天窗口内有 85 篇公告，只取第 1 页时
# 最早的候选只到窗口末端（2026-08-24），earlier 时段根本没有候选，分时段抽取只能靠跨段回填。
CNINFO_MAX_PAGES = 4             # 每家最多翻 4 页 = 120 篇候选

# 单篇文档文本块数的**告警**阈值（只报告、不截断）：超过即写进 reports\chunk_stats.json
# 的异常清单，让"某一篇把索引吃掉"这类问题在报告里显形。
MAX_CHUNKS_PER_DOC_WARN = 120

# --------------------------------------------------------------------------
# 7. Embedding 模型（《12》第2.3节：本阶段必须固化并写入元信息）
# --------------------------------------------------------------------------
# 选型理由见《13》：中文检索的常用基线、CPU 可跑、维度小、索引可全量重建。
EMBEDDING = {
    "model_name": "BAAI/bge-small-zh-v1.5",
    "revision": "7999e1d3359715c523056ef9478215996d62a620",
    "dim": 512,
    "normalize": True,          # L2 归一化后内积等价于余弦相似度
    "device": "cpu",
    "batch_size": 32,
    "max_seq_length": 512,
    "query_instruction": "",    # bge-zh-v1.5 检索时不加指令前缀，文档与查询同向编码
    "pooling": "cls",
    "similarity": "cosine",
}

# FAISS 索引类型：归一化向量 + 内积 = 余弦相似度；第一版规模小，用精确检索
FAISS = {
    "index_type": "IndexFlatIP",
    "metric": "inner_product",
    "index_file": "faiss.index",
    "map_file": "vector_map.jsonl",
    "meta_file": "build_meta.json",
}

# --------------------------------------------------------------------------
# 8. 清洗口径
# --------------------------------------------------------------------------
CLEAN = {
    # 全角/半角统一：**只做定向归一，不做整段 NFKC**（2026-09-25 开工前修正）。
    # 原口径 normalize_unicode=True（NFKC）会把中文全角标点 ，；：！？（） 折成 ASCII 的
    # ",;:!?()"，而 。 、 属 CJK 标点不受影响，结果同一句话里出现 "," 与 "。" 混排；
    # 更关键的是《10》第4.4.6节 要求证据按原文展示、权威文本不被改写，折标点等于改写证据。
    # 因此只把**全角 ASCII 区**（ＦＦ１０–ＦＦ１９ 数字、ＦＦ２１–ＦＦ５Ａ 与 ＦＦ４１–ＦＦ５Ａ
    # 字母、Ｕ＋３０００ 表意空格）折成半角，中文标点一律保持原样。
    "normalize_fullwidth_ascii": True,
    "normalize_unicode_nfkc": False,
    "preserve_cjk_punctuation": True,
    "collapse_blank_lines": True,
    "strip_control_chars": True,
    # 去模板：公告页眉页脚、免责声明、导航面包屑按行匹配删除。
    # 注意：**不含** r"^\s*$"。原先把空行整行删掉会让 collapse_blank_lines 变成空操作，
    # 并使 CHUNK.boundary_priority 的首选段落边界 "\n\n" 永远不可能命中；空行交给
    # collapse_blank_lines 折叠成单个空行，段落边界由此得以保留。
    "drop_line_patterns": [
        r"^本公司及(董事会|监事会)全体成员保证.*$",
        r"^证券代码[:：].*$",
        r"^证券简称[:：].*$",
        r"^公告编号[:：].*$",
        r"^(特此公告|特此通知)[。．.]?$",
        r"^扫一扫.*$", r"^分享到.*$", r"^责任编辑[:：].*$",
        r"^上一篇[:：].*$", r"^下一篇[:：].*$",
    ],
    "keep_line_patterns_after_drop": [],
}

# --------------------------------------------------------------------------
# subject_companies 的阈值（数据集内部字段，只由 clean.py 使用；不入库、不对应任何列）
# --------------------------------------------------------------------------
# 判定规则（clean.py 实现）：公司在 company_list 内，且满足**其一**即计入 subject_companies——
#   ① 其名称或 6 位代码出现在文档 title 中；
#   ② 其名称出现次数 ＋ 代码出现次数在 content 中 ≥ 本值。
# 实测动机（《14-前五阶段审核报告》第3.4节，2026-09-25）：company_list 对财经新闻采用
# "正文提及即关联"，25 篇新闻里约 12 篇被标注了并非文章主题的公司（doc_id 2009 标比亚迪而
# 正文主角是山东朗进科技、2016 标平安银行而正文主角是民生银行、2021 标宁德时代＋中芯国际
# 而正文主角是招商证券）；第 6 阶段若直接按 company_list 建"公司参与事件"的边会张冠李戴。
# 本字段只做**收紧**：company_list 的口径（"文档涉及的公司"，检索仍用它）保持不变。
# v1.1 实测效果（本规则的直接后果）：25 篇财经新闻中 9 篇 subject_companies 非空、
# 16 篇 company_list 非空但收紧为空；全库 company_list 非空的 74 篇里 42 篇有 subject。
SUBJECT_MENTION_MIN = 3

# 去重口径（《12》第5节 硬约束 3、第八节 修订后的验收项）
DEDUP = {
    "url_unique": True,
    "title_normalize": ["去除首尾空白", "去除全角空格", "合并连续空白"],
    "title_unique_within_dataset": True,
    # 监管公开信息的同题文档按"原标题（当事人）"构造后再判重
    "regulator_title_disambiguation": True,
    "content_fingerprint": "sha256_16",
    "minhash_similarity_threshold": None,   # 第一版只做精确指纹去重，不做近似去重
}

# --------------------------------------------------------------------------
# 9. 数据集目录结构（《12》第4.2节）
# --------------------------------------------------------------------------
SUBDIRS = ["meta", "raw", "clean", "chunks", "index", "reports"]


def dataset_dir(profile: str = "v1") -> str:
    """返回当前 profile 的数据集根目录（试跑与正式版物理隔离）。"""
    if profile == "pilot":
        return PILOT_ROOT
    return os.path.join(DATASET_ROOT, DATASET_VERSION)


def profile_settings(profile: str) -> dict:
    """把 profile 归一成一组执行参数，供各脚本统一读取。"""
    if profile == "pilot":
        return {
            "profile": "pilot",
            "dir": PILOT_ROOT,
            "companies": [c for c in COMPANIES if c["code"] in PILOT_COMPANIES],
            "quota": dict(QUOTA_PILOT),
            "announcement_per_company": ANNOUNCEMENT_PER_COMPANY_PILOT,
            "announcement_strata": dict(ANNOUNCEMENT_STRATA_PILOT),
            "exclude_announcement_title_patterns": list(EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_PILOT),
            "target_docs": TARGET_DOC_COUNT_PILOT,
        }
    return {
        "profile": "v1",
        "dir": os.path.join(DATASET_ROOT, DATASET_VERSION),
        "companies": list(COMPANIES),
        "quota": dict(QUOTA_V1),
        "announcement_per_company": ANNOUNCEMENT_PER_COMPANY,
        "announcement_strata": dict(ANNOUNCEMENT_STRATA_V1),
        "exclude_announcement_title_patterns": list(EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_V1),
        "target_docs": TARGET_DOC_COUNT_V1,
    }


INGEST_TIME = None  # 由各脚本在运行时写入 UTC+8 的 ISO8601 时间戳
