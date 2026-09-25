# -*- coding: utf-8 -*-
r"""company_registered_names.py —— T4 消歧的「公司注册全称」别名补充（**冻结数据**）。

本文件由 `build_company_aliases.py` 生成，**不要手改**：全部名字都取自实据，
没有任何一条是手打或推测出来的。

来源与证据逐家写在条目里：
  * `source = cninfo_company_intro`：巨潮公司概况接口的 ORGNAME 字段（证据含请求参数、
    HTTP 状态与 ASECNAME／MARKET／F032V 三个互相印证的响应字段）；
  * `source = corpus_corroborated_titles`：接口给不出名字时从该代码的公告标题 harvest，
    且**至少 2 篇不同文档的标题相互印证**（证据含印证篇数与 doc_id 清单）；
  * `source = unknown`：两条路都拿不到，如实登记，等人工确认（**不猜**）。

`CORPUS_CORROBORATION_*` 是对接口来源也顺手做的语料复核（只作审计，不参与别名）；
`disambiguate.py` 只读本模块的 `REGISTERED_NAMES`。
"""

SUPPLEMENT_SCHEMA = "stage6-company-registered-names-1.0"
SOURCE_ENDPOINT = "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction"
SOURCE_ENDPOINT_FIELD = "data.records[0].basicInformation[0].ORGNAME"
SOURCE_ENDPOINT_PARAM = "scode"
CORPUS_MIN_CORROBORATION = 2
SOURCE_COUNTS = {"cninfo_company_intro": 105}

REGISTERED_NAMES = {
    "000001": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1037
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000001"
            },
            "response_industry": "货币金融服务",
            "response_market": "深交所主板",
            "response_short_name": "平安银行"
        },
        "registered_name": "平安银行股份有限公司",
        "short_name": "平安银行",
        "source": "cninfo_company_intro",
        "stock_code": "000001"
    },
    "000002": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1273
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000002"
            },
            "response_industry": "房地产业",
            "response_market": "深交所主板",
            "response_short_name": "万  科Ａ"
        },
        "registered_name": "万科企业股份有限公司",
        "short_name": "万科A",
        "source": "cninfo_company_intro",
        "stock_code": "000002"
    },
    "000034": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000034"
            },
            "response_industry": "批发业",
            "response_market": "深交所主板",
            "response_short_name": "神州数码"
        },
        "registered_name": "神州数码集团股份有限公司",
        "short_name": "神州数码",
        "source": "cninfo_company_intro",
        "stock_code": "000034"
    },
    "000063": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000063"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所主板",
            "response_short_name": "中兴通讯"
        },
        "registered_name": "中兴通讯股份有限公司",
        "short_name": "中兴通讯",
        "source": "cninfo_company_intro",
        "stock_code": "000063"
    },
    "000333": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000333"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所主板",
            "response_short_name": "美的集团"
        },
        "registered_name": "美的集团股份有限公司",
        "short_name": "美的集团",
        "source": "cninfo_company_intro",
        "stock_code": "000333"
    },
    "000338": {
        "corpus_corroboration_count": 8,
        "corpus_corroboration_doc_ids": [
            1055,
            1056,
            1057,
            1151,
            1180,
            1237,
            1302,
            1369
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000338"
            },
            "response_industry": "汽车制造业",
            "response_market": "深交所主板",
            "response_short_name": "潍柴动力"
        },
        "registered_name": "潍柴动力股份有限公司",
        "short_name": "潍柴动力",
        "source": "cninfo_company_intro",
        "stock_code": "000338"
    },
    "000651": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000651"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所主板",
            "response_short_name": "格力电器"
        },
        "registered_name": "珠海格力电器股份有限公司",
        "short_name": "格力电器",
        "source": "cninfo_company_intro",
        "stock_code": "000651"
    },
    "000661": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000661"
            },
            "response_industry": "医药制造业",
            "response_market": "深交所主板",
            "response_short_name": "长春高新"
        },
        "registered_name": "长春高新技术产业(集团)股份有限公司",
        "short_name": "长春高新",
        "source": "cninfo_company_intro",
        "stock_code": "000661"
    },
    "000725": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000725"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所主板",
            "response_short_name": "京东方Ａ"
        },
        "registered_name": "京东方科技集团股份有限公司",
        "short_name": "京东方A",
        "source": "cninfo_company_intro",
        "stock_code": "000725"
    },
    "000792": {
        "corpus_corroboration_count": 3,
        "corpus_corroboration_doc_ids": [
            1269,
            1270,
            1271
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000792"
            },
            "response_industry": "化学原料和化学制品制造业",
            "response_market": "深交所主板",
            "response_short_name": "盐湖股份"
        },
        "registered_name": "青海盐湖工业股份有限公司",
        "short_name": "盐湖股份",
        "source": "cninfo_company_intro",
        "stock_code": "000792"
    },
    "000858": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000858"
            },
            "response_industry": "酒、饮料和精制茶制造业",
            "response_market": "深交所主板",
            "response_short_name": "五 粮 液"
        },
        "registered_name": "宜宾五粮液股份有限公司",
        "short_name": "五粮液",
        "source": "cninfo_company_intro",
        "stock_code": "000858"
    },
    "000963": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "000963"
            },
            "response_industry": "零售业",
            "response_market": "深交所主板",
            "response_short_name": "华东医药"
        },
        "registered_name": "华东医药股份有限公司",
        "short_name": "华东医药",
        "source": "cninfo_company_intro",
        "stock_code": "000963"
    },
    "002022": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002022"
            },
            "response_industry": "医药制造业",
            "response_market": "深交所主板",
            "response_short_name": "科华生物"
        },
        "registered_name": "上海科华生物工程股份有限公司",
        "short_name": "科华生物",
        "source": "cninfo_company_intro",
        "stock_code": "002022"
    },
    "002051": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002051"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "深交所主板",
            "response_short_name": "中工国际"
        },
        "registered_name": "中工国际工程股份有限公司",
        "short_name": "中工国际",
        "source": "cninfo_company_intro",
        "stock_code": "002051"
    },
    "002090": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002090"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所主板",
            "response_short_name": "金智科技"
        },
        "registered_name": "江苏金智科技股份有限公司",
        "short_name": "金智科技",
        "source": "cninfo_company_intro",
        "stock_code": "002090"
    },
    "002128": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1471
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002128"
            },
            "response_industry": "煤炭开采和洗选业",
            "response_market": "深交所主板",
            "response_short_name": "电投能源"
        },
        "registered_name": "内蒙古电投能源股份有限公司",
        "short_name": "电投能源",
        "source": "cninfo_company_intro",
        "stock_code": "002128"
    },
    "002200": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002200"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "深交所主板",
            "response_short_name": "交投生态"
        },
        "registered_name": "云南交投生态科技股份有限公司",
        "short_name": "交投生态",
        "source": "cninfo_company_intro",
        "stock_code": "002200"
    },
    "002241": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1354
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002241"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所主板",
            "response_short_name": "歌尔股份"
        },
        "registered_name": "歌尔股份有限公司",
        "short_name": "歌尔股份",
        "source": "cninfo_company_intro",
        "stock_code": "002241"
    },
    "002307": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002307"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "深交所主板",
            "response_short_name": "北新路桥"
        },
        "registered_name": "新疆北新路桥集团股份有限公司",
        "short_name": "北新路桥",
        "source": "cninfo_company_intro",
        "stock_code": "002307"
    },
    "002323": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002323"
            },
            "response_industry": "建筑装饰、装修和其他建筑业",
            "response_market": "深交所主板",
            "response_short_name": "*ST雅博"
        },
        "registered_name": "山东雅博科技股份有限公司",
        "short_name": "*ST雅博",
        "source": "cninfo_company_intro",
        "stock_code": "002323"
    },
    "002350": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002350"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所主板",
            "response_short_name": "北京科锐"
        },
        "registered_name": "北京科锐集团股份有限公司",
        "short_name": "北京科锐",
        "source": "cninfo_company_intro",
        "stock_code": "002350"
    },
    "002371": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002371"
            },
            "response_industry": "专用设备制造业",
            "response_market": "深交所主板",
            "response_short_name": "北方华创"
        },
        "registered_name": "北方华创科技集团股份有限公司",
        "short_name": "北方华创",
        "source": "cninfo_company_intro",
        "stock_code": "002371"
    },
    "002376": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002376"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所主板",
            "response_short_name": "新北洋"
        },
        "registered_name": "山东新北洋信息技术股份有限公司",
        "short_name": "新北洋",
        "source": "cninfo_company_intro",
        "stock_code": "002376"
    },
    "002457": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002457"
            },
            "response_industry": "非金属矿物制品业",
            "response_market": "深交所主板",
            "response_short_name": "青龙管业"
        },
        "registered_name": "青龙管业集团股份有限公司",
        "short_name": "青龙管业",
        "source": "cninfo_company_intro",
        "stock_code": "002457"
    },
    "002475": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1036
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002475"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所主板",
            "response_short_name": "立讯精密"
        },
        "registered_name": "立讯精密工业股份有限公司",
        "short_name": "立讯精密",
        "source": "cninfo_company_intro",
        "stock_code": "002475"
    },
    "002531": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002531"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所主板",
            "response_short_name": "天顺风能"
        },
        "registered_name": "天顺风能(苏州)股份有限公司",
        "short_name": "天顺风能",
        "source": "cninfo_company_intro",
        "stock_code": "002531"
    },
    "002541": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002541"
            },
            "response_industry": "金属制品业",
            "response_market": "深交所主板",
            "response_short_name": "鸿路钢构"
        },
        "registered_name": "安徽鸿路钢结构(集团)股份有限公司",
        "short_name": "鸿路钢构",
        "source": "cninfo_company_intro",
        "stock_code": "002541"
    },
    "002586": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002586"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "深交所主板",
            "response_short_name": "围海股份"
        },
        "registered_name": "浙江省围海建设集团股份有限公司",
        "short_name": "ST围海",
        "source": "cninfo_company_intro",
        "stock_code": "002586"
    },
    "002594": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002594"
            },
            "response_industry": "汽车制造业",
            "response_market": "深交所主板",
            "response_short_name": "比亚迪"
        },
        "registered_name": "比亚迪股份有限公司",
        "short_name": "比亚迪",
        "source": "cninfo_company_intro",
        "stock_code": "002594"
    },
    "002714": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "002714"
            },
            "response_industry": "畜牧业",
            "response_market": "深交所主板",
            "response_short_name": "牧原股份"
        },
        "registered_name": "牧原食品集团股份有限公司",
        "short_name": "牧原股份",
        "source": "cninfo_company_intro",
        "stock_code": "002714"
    },
    "300021": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300021"
            },
            "response_industry": "水利管理业",
            "response_market": "深交所创业板",
            "response_short_name": "大禹节水"
        },
        "registered_name": "大禹节水集团股份有限公司",
        "short_name": "大禹节水",
        "source": "cninfo_company_intro",
        "stock_code": "300021"
    },
    "300022": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300022"
            },
            "response_industry": "批发业",
            "response_market": "深交所创业板",
            "response_short_name": "吉峰科技"
        },
        "registered_name": "吉峰三农科技服务股份有限公司",
        "short_name": "吉峰科技",
        "source": "cninfo_company_intro",
        "stock_code": "300022"
    },
    "300059": {
        "corpus_corroboration_count": 7,
        "corpus_corroboration_doc_ids": [
            1022,
            1164,
            1188,
            1211,
            1281,
            1332,
            1397
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300059"
            },
            "response_industry": "资本市场服务",
            "response_market": "深交所创业板",
            "response_short_name": "东方财富"
        },
        "registered_name": "东方财富信息股份有限公司",
        "short_name": "东方财富",
        "source": "cninfo_company_intro",
        "stock_code": "300059"
    },
    "300191": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300191"
            },
            "response_industry": "石油和天然气开采业",
            "response_market": "深交所创业板",
            "response_short_name": "潜能恒信"
        },
        "registered_name": "潜能恒信能源技术股份有限公司",
        "short_name": "潜能恒信",
        "source": "cninfo_company_intro",
        "stock_code": "300191"
    },
    "300209": {
        "corpus_corroboration_count": 2,
        "corpus_corroboration_doc_ids": [
            1506,
            1593
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300209"
            },
            "response_industry": "零售业",
            "response_market": "深交所创业板",
            "response_short_name": "行云科技"
        },
        "registered_name": "行云科技股份有限公司",
        "short_name": "行云科技",
        "source": "cninfo_company_intro",
        "stock_code": "300209"
    },
    "300265": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300265"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所创业板",
            "response_short_name": "通光线缆"
        },
        "registered_name": "江苏通光电子线缆股份有限公司",
        "short_name": "通光线缆",
        "source": "cninfo_company_intro",
        "stock_code": "300265"
    },
    "300274": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300274"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所创业板",
            "response_short_name": "阳光电源"
        },
        "registered_name": "阳光电源股份有限公司",
        "short_name": "阳光电源",
        "source": "cninfo_company_intro",
        "stock_code": "300274"
    },
    "300351": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300351"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "永贵电器"
        },
        "registered_name": "浙江永贵电器股份有限公司",
        "short_name": "永贵电器",
        "source": "cninfo_company_intro",
        "stock_code": "300351"
    },
    "300355": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300355"
            },
            "response_industry": "生态保护和环境治理业",
            "response_market": "深交所创业板",
            "response_short_name": "蒙草生态"
        },
        "registered_name": "蒙草生态环境(集团)股份有限公司",
        "short_name": "蒙草生态",
        "source": "cninfo_company_intro",
        "stock_code": "300355"
    },
    "300393": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300393"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所创业板",
            "response_short_name": "中来股份"
        },
        "registered_name": "苏州中来光伏新材股份有限公司",
        "short_name": "中来股份",
        "source": "cninfo_company_intro",
        "stock_code": "300393"
    },
    "300436": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300436"
            },
            "response_industry": "医药制造业",
            "response_market": "深交所创业板",
            "response_short_name": "广生堂"
        },
        "registered_name": "福建广生堂药业股份有限公司",
        "short_name": "广生堂",
        "source": "cninfo_company_intro",
        "stock_code": "300436"
    },
    "300504": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300504"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "天邑股份"
        },
        "registered_name": "四川天邑康和通信股份有限公司",
        "short_name": "天邑股份",
        "source": "cninfo_company_intro",
        "stock_code": "300504"
    },
    "300510": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300510"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所创业板",
            "response_short_name": "金冠股份"
        },
        "registered_name": "吉林省金冠电气股份有限公司",
        "short_name": "金冠股份",
        "source": "cninfo_company_intro",
        "stock_code": "300510"
    },
    "300562": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300562"
            },
            "response_industry": "专用设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "乐心股份"
        },
        "registered_name": "广东乐心医疗电子股份有限公司",
        "short_name": "乐心股份",
        "source": "cninfo_company_intro",
        "stock_code": "300562"
    },
    "300571": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300571"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "平治信息"
        },
        "registered_name": "杭州平治信息技术股份有限公司",
        "short_name": "平治信息",
        "source": "cninfo_company_intro",
        "stock_code": "300571"
    },
    "300642": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300642"
            },
            "response_industry": "医药制造业",
            "response_market": "深交所创业板",
            "response_short_name": "透景生命"
        },
        "registered_name": "上海透景生命科技股份有限公司",
        "short_name": "透景生命",
        "source": "cninfo_company_intro",
        "stock_code": "300642"
    },
    "300723": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300723"
            },
            "response_industry": "医药制造业",
            "response_market": "深交所创业板",
            "response_short_name": "一品红"
        },
        "registered_name": "一品红药业集团股份有限公司",
        "short_name": "一品红",
        "source": "cninfo_company_intro",
        "stock_code": "300723"
    },
    "300750": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1396
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300750"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "深交所创业板",
            "response_short_name": "宁德时代"
        },
        "registered_name": "宁德时代新能源科技股份有限公司",
        "short_name": "宁德时代",
        "source": "cninfo_company_intro",
        "stock_code": "300750"
    },
    "300757": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300757"
            },
            "response_industry": "专用设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "罗博特科"
        },
        "registered_name": "罗博特科智能科技股份有限公司",
        "short_name": "罗博特科",
        "source": "cninfo_company_intro",
        "stock_code": "300757"
    },
    "300765": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300765"
            },
            "response_industry": "食品制造业",
            "response_market": "深交所创业板",
            "response_short_name": "石药创新"
        },
        "registered_name": "石药创新制药股份有限公司",
        "short_name": "石药创新",
        "source": "cninfo_company_intro",
        "stock_code": "300765"
    },
    "300854": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300854"
            },
            "response_industry": "生态保护和环境治理业",
            "response_market": "深交所创业板",
            "response_short_name": "中兰环保"
        },
        "registered_name": "中兰环保科技股份有限公司",
        "short_name": "中兰环保",
        "source": "cninfo_company_intro",
        "stock_code": "300854"
    },
    "300869": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300869"
            },
            "response_industry": "专用设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "康泰医学"
        },
        "registered_name": "康泰医学系统(秦皇岛)股份有限公司",
        "short_name": "康泰医学",
        "source": "cninfo_company_intro",
        "stock_code": "300869"
    },
    "300900": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "300900"
            },
            "response_industry": "铁路、船舶、航空航天和其他运输设备制造业",
            "response_market": "深交所创业板",
            "response_short_name": "广联航空"
        },
        "registered_name": "广联航空工业股份有限公司",
        "short_name": "广联航空",
        "source": "cninfo_company_intro",
        "stock_code": "300900"
    },
    "301085": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "301085"
            },
            "response_industry": "软件和信息技术服务业",
            "response_market": "深交所创业板",
            "response_short_name": "亚康股份"
        },
        "registered_name": "北京亚康万玮信息技术股份有限公司",
        "short_name": "亚康股份",
        "source": "cninfo_company_intro",
        "stock_code": "301085"
    },
    "301235": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "301235"
            },
            "response_industry": "建筑安装业",
            "response_market": "深交所创业板",
            "response_short_name": "华康洁净"
        },
        "registered_name": "武汉华康世纪洁净科技股份有限公司",
        "short_name": "华康洁净",
        "source": "cninfo_company_intro",
        "stock_code": "301235"
    },
    "600019": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1072
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600019"
            },
            "response_industry": "黑色金属冶炼和压延加工业",
            "response_market": "上交所",
            "response_short_name": "宝钢股份"
        },
        "registered_name": "宝山钢铁股份有限公司",
        "short_name": "宝钢股份",
        "source": "cninfo_company_intro",
        "stock_code": "600019"
    },
    "600028": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600028"
            },
            "response_industry": "石油和天然气开采业",
            "response_market": "上交所",
            "response_short_name": "中国石化"
        },
        "registered_name": "中国石油化工股份有限公司",
        "short_name": "中国石化",
        "source": "cninfo_company_intro",
        "stock_code": "600028"
    },
    "600030": {
        "corpus_corroboration_count": 7,
        "corpus_corroboration_doc_ids": [
            1043,
            1081,
            1150,
            1177,
            1276,
            1309,
            1379
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600030"
            },
            "response_industry": "资本市场服务",
            "response_market": "上交所",
            "response_short_name": "中信证券"
        },
        "registered_name": "中信证券股份有限公司",
        "short_name": "中信证券",
        "source": "cninfo_company_intro",
        "stock_code": "600030"
    },
    "600031": {
        "corpus_corroboration_count": 8,
        "corpus_corroboration_doc_ids": [
            1008,
            1042,
            1114,
            1125,
            1176,
            1268,
            1316,
            1358
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600031"
            },
            "response_industry": "专用设备制造业",
            "response_market": "上交所",
            "response_short_name": "三一重工"
        },
        "registered_name": "三一重工股份有限公司",
        "short_name": "三一重工",
        "source": "cninfo_company_intro",
        "stock_code": "600031"
    },
    "600036": {
        "corpus_corroboration_count": 8,
        "corpus_corroboration_doc_ids": [
            1012,
            1076,
            1080,
            1162,
            1196,
            1278,
            1308,
            1395
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600036"
            },
            "response_industry": "货币金融服务",
            "response_market": "上交所",
            "response_short_name": "招商银行"
        },
        "registered_name": "招商银行股份有限公司",
        "short_name": "招商银行",
        "source": "cninfo_company_intro",
        "stock_code": "600036"
    },
    "600048": {
        "corpus_corroboration_count": 7,
        "corpus_corroboration_doc_ids": [
            1005,
            1070,
            1161,
            1226,
            1227,
            1307,
            1394
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600048"
            },
            "response_industry": "房地产业",
            "response_market": "上交所",
            "response_short_name": "保利发展"
        },
        "registered_name": "保利发展控股集团股份有限公司",
        "short_name": "保利发展",
        "source": "cninfo_company_intro",
        "stock_code": "600048"
    },
    "600062": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600062"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "华润双鹤"
        },
        "registered_name": "华润双鹤药业股份有限公司",
        "short_name": "华润双鹤",
        "source": "cninfo_company_intro",
        "stock_code": "600062"
    },
    "600079": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600079"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "ST人福"
        },
        "registered_name": "人福医药集团股份公司",
        "short_name": "ST人福",
        "source": "cninfo_company_intro",
        "stock_code": "600079"
    },
    "600089": {
        "corpus_corroboration_count": 6,
        "corpus_corroboration_doc_ids": [
            1209,
            1232,
            1233,
            1340,
            1342,
            1385
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600089"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "上交所",
            "response_short_name": "特变电工"
        },
        "registered_name": "特变电工股份有限公司",
        "short_name": "特变电工",
        "source": "cninfo_company_intro",
        "stock_code": "600089"
    },
    "600104": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600104"
            },
            "response_industry": "汽车制造业",
            "response_market": "上交所",
            "response_short_name": "上汽集团"
        },
        "registered_name": "上海汽车集团股份有限公司",
        "short_name": "上汽集团",
        "source": "cninfo_company_intro",
        "stock_code": "600104"
    },
    "600196": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600196"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "复星医药"
        },
        "registered_name": "上海复星医药(集团)股份有限公司",
        "short_name": "复星医药",
        "source": "cninfo_company_intro",
        "stock_code": "600196"
    },
    "600267": {
        "corpus_corroboration_count": 5,
        "corpus_corroboration_doc_ids": [
            1417,
            1438,
            1518,
            1538,
            1562
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600267"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "海正药业"
        },
        "registered_name": "浙江海正药业股份有限公司",
        "short_name": "海正药业",
        "source": "cninfo_company_intro",
        "stock_code": "600267"
    },
    "600276": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600276"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "恒瑞医药"
        },
        "registered_name": "江苏恒瑞医药股份有限公司",
        "short_name": "恒瑞医药",
        "source": "cninfo_company_intro",
        "stock_code": "600276"
    },
    "600309": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600309"
            },
            "response_industry": "化学原料和化学制品制造业",
            "response_market": "上交所",
            "response_short_name": "万华化学"
        },
        "registered_name": "万华化学集团股份有限公司",
        "short_name": "万华化学",
        "source": "cninfo_company_intro",
        "stock_code": "600309"
    },
    "600406": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1362
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600406"
            },
            "response_industry": "软件和信息技术服务业",
            "response_market": "上交所",
            "response_short_name": "国电南瑞"
        },
        "registered_name": "国电南瑞科技股份有限公司",
        "short_name": "国电南瑞",
        "source": "cninfo_company_intro",
        "stock_code": "600406"
    },
    "600420": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600420"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "国药现代"
        },
        "registered_name": "上海现代制药股份有限公司",
        "short_name": "国药现代",
        "source": "cninfo_company_intro",
        "stock_code": "600420"
    },
    "600438": {
        "corpus_corroboration_count": 6,
        "corpus_corroboration_doc_ids": [
            1069,
            1158,
            1195,
            1245,
            1321,
            1365
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600438"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "上交所",
            "response_short_name": "通威股份"
        },
        "registered_name": "通威股份有限公司",
        "short_name": "通威股份",
        "source": "cninfo_company_intro",
        "stock_code": "600438"
    },
    "600488": {
        "corpus_corroboration_count": 4,
        "corpus_corroboration_doc_ids": [
            1405,
            1487,
            1548,
            1559
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600488"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "津药药业"
        },
        "registered_name": "津药药业股份有限公司",
        "short_name": "津药药业",
        "source": "cninfo_company_intro",
        "stock_code": "600488"
    },
    "600519": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600519"
            },
            "response_industry": "酒、饮料和精制茶制造业",
            "response_market": "上交所",
            "response_short_name": "贵州茅台"
        },
        "registered_name": "贵州茅台酒股份有限公司",
        "short_name": "贵州茅台",
        "source": "cninfo_company_intro",
        "stock_code": "600519"
    },
    "600521": {
        "corpus_corroboration_count": 5,
        "corpus_corroboration_doc_ids": [
            1416,
            1460,
            1514,
            1517,
            1568
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600521"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "华海药业"
        },
        "registered_name": "浙江华海药业股份有限公司",
        "short_name": "华海药业",
        "source": "cninfo_company_intro",
        "stock_code": "600521"
    },
    "600522": {
        "corpus_corroboration_count": 7,
        "corpus_corroboration_doc_ids": [
            1112,
            1148,
            1149,
            1244,
            1294,
            1320,
            1364
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600522"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "上交所",
            "response_short_name": "中天科技"
        },
        "registered_name": "江苏中天科技股份有限公司",
        "short_name": "中天科技",
        "source": "cninfo_company_intro",
        "stock_code": "600522"
    },
    "600587": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600587"
            },
            "response_industry": "专用设备制造业",
            "response_market": "上交所",
            "response_short_name": "新华医疗"
        },
        "registered_name": "山东新华医疗器械股份有限公司",
        "short_name": "新华医疗",
        "source": "cninfo_company_intro",
        "stock_code": "600587"
    },
    "600789": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600789"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "鲁抗医药"
        },
        "registered_name": "山东鲁抗医药股份有限公司",
        "short_name": "鲁抗医药",
        "source": "cninfo_company_intro",
        "stock_code": "600789"
    },
    "600875": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600875"
            },
            "response_industry": "通用设备制造业",
            "response_market": "上交所",
            "response_short_name": "东方电气"
        },
        "registered_name": "东方电气股份有限公司",
        "short_name": "东方电气",
        "source": "cninfo_company_intro",
        "stock_code": "600875"
    },
    "600887": {
        "corpus_corroboration_count": 8,
        "corpus_corroboration_doc_ids": [
            1007,
            1035,
            1094,
            1157,
            1183,
            1282,
            1306,
            1392
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600887"
            },
            "response_industry": "食品制造业",
            "response_market": "上交所",
            "response_short_name": "伊利股份"
        },
        "registered_name": "内蒙古伊利实业集团股份有限公司",
        "short_name": "伊利股份",
        "source": "cninfo_company_intro",
        "stock_code": "600887"
    },
    "600900": {
        "corpus_corroboration_count": 1,
        "corpus_corroboration_doc_ids": [
            1182
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600900"
            },
            "response_industry": "电力、热力生产和供应业",
            "response_market": "上交所",
            "response_short_name": "长江电力"
        },
        "registered_name": "中国长江电力股份有限公司",
        "short_name": "长江电力",
        "source": "cninfo_company_intro",
        "stock_code": "600900"
    },
    "600970": {
        "corpus_corroboration_count": 6,
        "corpus_corroboration_doc_ids": [
            1131,
            1229,
            1255,
            1297,
            1319,
            1391
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "600970"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "上交所",
            "response_short_name": "中材国际"
        },
        "registered_name": "中国中材国际工程股份有限公司",
        "short_name": "中材国际",
        "source": "cninfo_company_intro",
        "stock_code": "600970"
    },
    "601012": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601012"
            },
            "response_industry": "电气机械和器材制造业",
            "response_market": "上交所",
            "response_short_name": "隆基绿能"
        },
        "registered_name": "隆基绿能科技股份有限公司",
        "short_name": "隆基绿能",
        "source": "cninfo_company_intro",
        "stock_code": "601012"
    },
    "601088": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601088"
            },
            "response_industry": "煤炭开采和洗选业",
            "response_market": "上交所",
            "response_short_name": "中国神华"
        },
        "registered_name": "中国神华能源股份有限公司",
        "short_name": "中国神华",
        "source": "cninfo_company_intro",
        "stock_code": "601088"
    },
    "601089": {
        "corpus_corroboration_count": 6,
        "corpus_corroboration_doc_ids": [
            1476,
            1496,
            1497,
            1516,
            1555,
            1591
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601089"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "福元医药"
        },
        "registered_name": "北京福元医药股份有限公司",
        "short_name": "福元医药",
        "source": "cninfo_company_intro",
        "stock_code": "601089"
    },
    "601138": {
        "corpus_corroboration_count": 8,
        "corpus_corroboration_doc_ids": [
            1025,
            1100,
            1207,
            1224,
            1279,
            1314,
            1339,
            1378
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601138"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "上交所",
            "response_short_name": "工业富联"
        },
        "registered_name": "富士康工业互联网股份有限公司",
        "short_name": "工业富联",
        "source": "cninfo_company_intro",
        "stock_code": "601138"
    },
    "601186": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601186"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "上交所",
            "response_short_name": "中国铁建"
        },
        "registered_name": "中国铁建股份有限公司",
        "short_name": "中国铁建",
        "source": "cninfo_company_intro",
        "stock_code": "601186"
    },
    "601318": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601318"
            },
            "response_industry": "保险业",
            "response_market": "上交所",
            "response_short_name": "中国平安"
        },
        "registered_name": "中国平安保险(集团)股份有限公司",
        "short_name": "中国平安",
        "source": "cninfo_company_intro",
        "stock_code": "601318"
    },
    "601390": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601390"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "上交所",
            "response_short_name": "中国中铁"
        },
        "registered_name": "中国中铁股份有限公司",
        "short_name": "中国中铁",
        "source": "cninfo_company_intro",
        "stock_code": "601390"
    },
    "601398": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601398"
            },
            "response_industry": "货币金融服务",
            "response_market": "上交所",
            "response_short_name": "工商银行"
        },
        "registered_name": "中国工商银行股份有限公司",
        "short_name": "工商银行",
        "source": "cninfo_company_intro",
        "stock_code": "601398"
    },
    "601567": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601567"
            },
            "response_industry": "仪器仪表制造业",
            "response_market": "上交所",
            "response_short_name": "三星电气"
        },
        "registered_name": "宁波三星医疗电气股份有限公司",
        "short_name": "三星电气",
        "source": "cninfo_company_intro",
        "stock_code": "601567"
    },
    "601633": {
        "corpus_corroboration_count": 7,
        "corpus_corroboration_doc_ids": [
            1001,
            1068,
            1109,
            1169,
            1261,
            1327,
            1375
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601633"
            },
            "response_industry": "汽车制造业",
            "response_market": "上交所",
            "response_short_name": "长城汽车"
        },
        "registered_name": "长城汽车股份有限公司",
        "short_name": "长城汽车",
        "source": "cninfo_company_intro",
        "stock_code": "601633"
    },
    "601668": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601668"
            },
            "response_industry": "土木工程建筑业",
            "response_market": "上交所",
            "response_short_name": "中国建筑"
        },
        "registered_name": "中国建筑股份有限公司",
        "short_name": "中国建筑",
        "source": "cninfo_company_intro",
        "stock_code": "601668"
    },
    "601727": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601727"
            },
            "response_industry": "通用设备制造业",
            "response_market": "上交所",
            "response_short_name": "上海电气"
        },
        "registered_name": "上海电气集团股份有限公司",
        "short_name": "上海电气",
        "source": "cninfo_company_intro",
        "stock_code": "601727"
    },
    "601899": {
        "corpus_corroboration_count": 7,
        "corpus_corroboration_doc_ids": [
            1033,
            1034,
            1092,
            1145,
            1192,
            1311,
            1370
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "601899"
            },
            "response_industry": "有色金属矿采选业",
            "response_market": "上交所",
            "response_short_name": "紫金矿业"
        },
        "registered_name": "紫金矿业集团股份有限公司",
        "short_name": "紫金矿业",
        "source": "cninfo_company_intro",
        "stock_code": "601899"
    },
    "603087": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "603087"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所",
            "response_short_name": "甘李药业"
        },
        "registered_name": "甘李药业股份有限公司",
        "short_name": "甘李药业",
        "source": "cninfo_company_intro",
        "stock_code": "603087"
    },
    "603163": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "603163"
            },
            "response_industry": "建筑安装业",
            "response_market": "上交所",
            "response_short_name": "圣晖集成"
        },
        "registered_name": "圣晖系统集成集团股份有限公司",
        "short_name": "圣晖集成",
        "source": "cninfo_company_intro",
        "stock_code": "603163"
    },
    "603288": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "603288"
            },
            "response_industry": "食品制造业",
            "response_market": "上交所",
            "response_short_name": "海天味业"
        },
        "registered_name": "佛山市海天调味食品股份有限公司",
        "short_name": "海天味业",
        "source": "cninfo_company_intro",
        "stock_code": "603288"
    },
    "603501": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "603501"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "上交所",
            "response_short_name": "豪威集团"
        },
        "registered_name": "豪威集成电路(集团)股份有限公司",
        "short_name": "韦尔股份",
        "source": "cninfo_company_intro",
        "stock_code": "603501"
    },
    "603856": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "603856"
            },
            "response_industry": "橡胶和塑料制品业",
            "response_market": "上交所",
            "response_short_name": "东宏股份"
        },
        "registered_name": "山东东宏管业股份有限公司",
        "short_name": "东宏股份",
        "source": "cninfo_company_intro",
        "stock_code": "603856"
    },
    "605287": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "605287"
            },
            "response_industry": "建筑装饰、装修和其他建筑业",
            "response_market": "上交所",
            "response_short_name": "德才股份"
        },
        "registered_name": "德才装饰股份有限公司",
        "short_name": "德才股份",
        "source": "cninfo_company_intro",
        "stock_code": "605287"
    },
    "688485": {
        "corpus_corroboration_count": 2,
        "corpus_corroboration_doc_ids": [
            1455,
            1572
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "688485"
            },
            "response_industry": "生态保护和环境治理业",
            "response_market": "上交所科创板",
            "response_short_name": "九州一轨"
        },
        "registered_name": "北京九州一轨环境科技股份有限公司",
        "short_name": "九州一轨",
        "source": "cninfo_company_intro",
        "stock_code": "688485"
    },
    "688506": {
        "corpus_corroboration_count": 4,
        "corpus_corroboration_doc_ids": [
            1422,
            1510,
            1530,
            1579
        ],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "688506"
            },
            "response_industry": "医药制造业",
            "response_market": "上交所科创板",
            "response_short_name": "百利天恒"
        },
        "registered_name": "四川百利天恒药业股份有限公司",
        "short_name": "百利天恒",
        "source": "cninfo_company_intro",
        "stock_code": "688506"
    },
    "688981": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "688981"
            },
            "response_industry": "计算机、通信和其他电子设备制造业",
            "response_market": "上交所科创板",
            "response_short_name": "中芯国际"
        },
        "registered_name": "中芯国际集成电路制造有限公司",
        "short_name": "中芯国际",
        "source": "cninfo_company_intro",
        "stock_code": "688981"
    },
    "920019": {
        "corpus_corroboration_count": 0,
        "corpus_corroboration_doc_ids": [],
        "evidence": {
            "endpoint": "https://www.cninfo.com.cn/data20/companyOverview/getCompanyIntroduction",
            "field": "data.records[0].basicInformation[0].ORGNAME",
            "http_status": 200,
            "method": "GET",
            "param": {
                "scode": "920019"
            },
            "response_industry": "开采专业及辅助性活动",
            "response_market": "北交所",
            "response_short_name": "铜冠矿建"
        },
        "registered_name": "铜陵有色金属集团铜冠矿山建设股份有限公司",
        "short_name": "铜冠矿建",
        "source": "cninfo_company_intro",
        "stock_code": "920019"
    }
}
