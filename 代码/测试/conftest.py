# -*- coding: utf-8 -*-
"""代码\\测试\\conftest.py —— 夹具与导入引导（pytest 只读，不改任何产品文件）。

两件事：

1. **导入引导**：把 `代码\\测试` 自己插进 `sys.path`，使各测试文件都能 `import _bootstrap`
   （`_bootstrap` 才是真正管"四个同名 config 串味"的那一层，理由见它的模块 docstring）。
   注意：`代码\\测试` 下**没有**任何产品模块、更没有 `config.py`，插它不会改变
   `import config` 的解析结果——真正的隔离在 `_bootstrap._Isolated` 里做。
2. **夹具**：给 A／C 两组提供**可复算的合成输入**——
   `synthetic_graph`（真实 `GraphQuery` ＋ 临时目录里的两张小 CSV）与
   `fake_searcher`（替掉向量检索的进程内替身，只回确定性读数）。

为什么图谱用**真实** `GraphQuery`（而不是打桩）：G6 时间过滤与 `graph_path_payload`
都在这个类里，替身会把"被测代码"换成"我自己写的桩"，等于没测。合成图只有 7 个节点、
6 条边，写在 `tmp_path` 里，**离线、零外部依赖、不读真实图谱导出物**。
"""

from __future__ import annotations

import csv
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# 测试期不写 `.pyc`：产品代码是**按文件路径**加载的，默认会往 `代码\检索\__pycache__\` 之类
# 的位置落字节码。本套测试对产品目录**一个字节都不写**（连 `__pycache__` 也不写），
# 与《检索 README》第二条"对输入只读"的纪律保持一致。
sys.dont_write_bytecode = True

import _bootstrap  # noqa: E402

# 合成图的三张表：节点／边／文本块。字段名逐字取自 `代码\检索\config.py`
# （`EDGE_COLUMNS` 与图谱导出物的列名），不在这里另立一套。
_NODE_FIELDS = ["node_id", "label", "name", "short_name", "aliases", "stock_code",
                "event_id", "event_type", "event_time", "event_title"]

_NODES = [
    # 公司：三种标识（node_id／stock_code／名称）都要能匹配
    ["N_C1", "Company", "甲公司", "甲", "甲公司|JIA", "000001", "", "", "", ""],
    ["N_C2", "Company", "乙公司", "乙", "", "000002", "", "", "", ""],
    ["N_C3", "Company", "丙公司", "丙", "", "000003", "", "", "", ""],
    # 事件：一个在窗口内、一个 event_time 为空、一个在窗口外
    ["EV_A", "Event", "", "", "", "", "E-A", "业绩", "2026-03-01", "甲公司年度业绩"],
    ["EV_N", "Event", "", "", "", "", "E-N", "监管", "", "甲公司监管事项"],
    ["EV_O", "Event", "", "", "", "", "E-O", "股权", "2024-01-01", "甲公司股权变动"],
    ["DOC1", "Document", "", "", "", "", "", "", "", ""],
]

# 边（表头顺序＝`config.EDGE_COLUMNS`）：三条 PARTICIPATES_IN 各带一个块，
# 一条 EVIDENCED_BY（**不带** source_chunk_id，不产生文本块级候选），
# 一条 2 跳才可达的语义边，一条**路径上没有事件**的语义边（用于"无事件可判定"分支）。
_EDGE_ROWS = [
    ["N_C1", "PARTICIPATES_IN", "EV_A", "1", "101", "0.90", "主体", "", ""],
    ["N_C1", "PARTICIPATES_IN", "EV_N", "1", "102", "0.80", "主体", "", ""],
    ["N_C1", "PARTICIPATES_IN", "EV_O", "1", "103", "0.70", "主体", "", ""],
    ["EV_A", "EVIDENCED_BY", "DOC1", "", "", "", "", "", ""],
    ["N_C2", "RELATED_TO", "EV_A", "2", "104", "0.50", "涉及方", "", ""],
    # 这一条**刻意接在一个没有事件的孤立公司节点上**（N_C3 只此一条边）：它形成的路径上
    # 没有任何 Event 节点，候选因此没有"可判定是否落在时间窗口内"的事件——用于覆盖
    # "无事件可判定 → 按空值策略一并剔除"这一分支（v2.9 裁定 ①）。
    ["N_C1", "RELATED_TO", "N_C3", "3", "105", "0.40", "涉及方", "", ""],
]

# 文本块（token_count 是实测值字段，这里给固定小值，便于精确控制预算）
_CHUNKS = {
    101: {"chunk_id": 101, "doc_id": 1, "token_count": 10, "content": "甲公司2026年业绩公告正文"},
    102: {"chunk_id": 102, "doc_id": 1, "token_count": 10, "content": "甲公司监管事项正文"},
    103: {"chunk_id": 103, "doc_id": 1, "token_count": 10, "content": "甲公司2024年股权变动正文"},
    104: {"chunk_id": 104, "doc_id": 2, "token_count": 10, "content": "乙公司相关事项正文"},
    105: {"chunk_id": 105, "doc_id": 3, "token_count": 10, "content": "甲乙公司关联关系正文"},
    999: {"chunk_id": 999, "doc_id": 4, "token_count": 10, "content": "向量侧命中的无关正文"},
}

_DOCUMENTS = {
    1: {"doc_id": 1, "title": "甲公司公告", "source": "cninfo", "category": "公告",
        "publish_time": "2026-03-02", "url": "https://example.invalid/1",
        "company_list": "甲公司", "subject_companies": "甲公司"},
    2: {"doc_id": 2, "title": "乙公司公告", "source": "cninfo", "category": "公告",
        "publish_time": "2026-02-01", "url": "https://example.invalid/2",
        "company_list": "乙公司", "subject_companies": "乙公司"},
    3: {"doc_id": 3, "title": "财经新闻", "source": "news", "category": "财经新闻",
        "publish_time": "2026-01-05", "url": "https://example.invalid/3",
        "company_list": "甲公司", "subject_companies": "甲公司"},
    4: {"doc_id": 4, "title": "无关文档", "source": "news", "category": "财经新闻",
        "publish_time": "2025-12-01", "url": "https://example.invalid/4",
        "company_list": "", "subject_companies": ""},
}

# 向量侧 N 条候选（与图谱侧**刻意重叠**：101／105 两路同命中，999 只在向量侧）
_VECTOR_ROWS = [
    {"vector_id": 0, "similarity": 0.90, "chunk_id": 105, "doc_id": 3, "vector_rank": 1},
    {"vector_id": 1, "similarity": 0.80, "chunk_id": 101, "doc_id": 1, "vector_rank": 2},
    {"vector_id": 2, "similarity": 0.70, "chunk_id": 999, "doc_id": 4, "vector_rank": 3},
]

# 全池相似度（第二层排序用）：比 N 条候选多了图谱侧新增块的分数
_FULL_POOL_ROWS = _VECTOR_ROWS + [
    {"vector_id": 3, "similarity": 0.33, "chunk_id": 104, "doc_id": 2, "vector_rank": 4},
    {"vector_id": 4, "similarity": 0.20, "chunk_id": 102, "doc_id": 1, "vector_rank": 5},
    {"vector_id": 5, "similarity": 0.10, "chunk_id": 103, "doc_id": 1, "vector_rank": 6},
]

# 测试用题（时间窗口是**题集给的那一种**：闭区间 + label + basis，与真实题集同形）
QUESTION = {
    "qid": "T-01",
    "question": "甲公司2026年的业绩情况如何？",
    "time_window": {"lo": "2026-01-01", "hi": "2026-12-31", "label": "2026年",
                    "basis": "event_time", "empty_policy": "exclude", "source": "题集 time_window"},
    "gold_evidence_chunk_ids": [101],
    "task_type": "事实型",
    "gold_hop_depth": 2,
}


class SyntheticCase:
    """合成用例的容器（图谱 ＋ 三张表 ＋ 向量侧读数）。"""

    def __init__(self, graph):
        self.graph = graph
        self.chunks = _CHUNKS
        self.documents = _DOCUMENTS
        self.vector_rows = _VECTOR_ROWS
        self.full_pool_rows = _FULL_POOL_ROWS
        self.question = QUESTION


class FakeSearcher:
    """向量检索的**进程内替身**：只回确定性读数，不碰索引、不碰模型、不联网。

    `search(question, n)` 的返回形状与 `vector_search.VectorSearcher.search()` 一致
    （`(rows, timing)`）。当 `n > n_limit` 时回"全池"读数——对应
    `pipeline.full_pool_similarities()` 对第二层排序取全池分数的那一次调用。
    """

    def __init__(self, n_rows, full_pool_rows, n_limit):
        self.n_rows = [dict(row) for row in n_rows]
        self.full_pool_rows = [dict(row) for row in full_pool_rows]
        self.n_limit = int(n_limit)
        self.calls = []

    def search(self, question, n):
        self.calls.append((str(question), int(n)))
        rows = self.full_pool_rows if int(n) > self.n_limit else self.n_rows
        return [dict(row) for row in rows], {"seconds": 0.0}


@pytest.fixture(scope="session", autouse=True)
def forbid_network():
    """把"本套测试离线"从**声明**变成**硬保证**（照第 7 阶段 `STAGE7_FORBID_MODEL_CALLS` 的做法）。

    装一个审计钩子：任何 socket 连接／域名解析／HTTP 请求一律当场抛错，用例随即变红。
    没有这条守卫时，"不联网"只是我在 README 里的一句话；有了它，一旦将来有人给某条用例
    加上一次真实调用（哪怕是无意的），整轮会立刻失败而不是悄悄联网。
    """
    events = ("socket.connect", "socket.getaddrinfo", "socket.gethostbyname",
              "urllib.Request", "http.client.connect", "ftplib.connect", "smtplib.connect")

    def _hook(event, args):
        if event in events:
            raise RuntimeError(
                "单元测试必须离线：拦截到网络事件 %r（参数 %r）——本套测试不得联网、"
                "不得调大模型；需要联网的路径属阶段门禁的覆盖面。" % (event, args))

    sys.addaudithook(_hook)
    yield


@pytest.fixture(scope="session")
def retrieval_mod():
    """`代码\\检索\\pipeline.py`（按文件路径加载；加载期 `import config` 命中检索侧那一份）。"""
    return _bootstrap.load_module("检索", "pipeline.py")


@pytest.fixture(scope="session")
def retrieval_cfg():
    """`代码\\检索\\config.py`（参数一律取自它，测试里不写死 K／N／预算／g）。"""
    return _bootstrap.component_config("检索")


@pytest.fixture(scope="session")
def synthetic_graph(tmp_path_factory, retrieval_cfg):
    """真实 `GraphQuery` ＋ 临时目录里的合成 nodes.csv／edges.csv（离线、只读）。"""
    directory = tmp_path_factory.mktemp("synthetic_graph")
    nodes_csv = directory / "nodes.csv"
    edges_csv = directory / "edges.csv"
    with open(nodes_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(_NODE_FIELDS)
        writer.writerows(_NODES)
    with open(edges_csv, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(retrieval_cfg.EDGE_COLUMNS))     # 列名与顺序一律取自 config
        writer.writerows(_EDGE_ROWS)
    graph_query = _bootstrap.load_module("检索", "graph_query.py")
    graph = graph_query.GraphQuery(str(nodes_csv), str(edges_csv))
    return SyntheticCase(graph)


@pytest.fixture
def fake_searcher(retrieval_cfg):
    """向量检索替身的工厂（每次测试新建，避免跨用例串状态）。"""
    limit = int(retrieval_cfg.require_fixed("N"))

    def _make(n_rows=None, full_pool_rows=None):
        return FakeSearcher(_VECTOR_ROWS if n_rows is None else n_rows,
                            _FULL_POOL_ROWS if full_pool_rows is None else full_pool_rows,
                            limit)

    return _make
