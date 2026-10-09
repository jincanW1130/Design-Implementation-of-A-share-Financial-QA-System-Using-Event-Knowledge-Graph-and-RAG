# -*- coding: utf-8 -*-
"""D 组 · 后端错误码映射 —— 被测文件：`代码\\后端\\errors.py` 与
`代码\\后端\\services\\qa_service.py` 的 `_classify_failure()`。

覆盖（评审 P1-12 点名的"错误码映射"）：

1. **14 个错误码的语义单一性**：码表逐码检查（message 非空且互不重复、HTTP 状态落在登记值上、
   2002 是"不是错误的正常业务状态"）；
2. **映射函数的纯逻辑**：`message_of`／`http_status_of`／`is_normal`／未知码兜底／
   `HTTP_STATUS_TO_CODE` 的往返一致性／响应体键集合**恰为** `{code, message}`（detail 只进日志）；
3. **`_classify_failure` 按中文措辞猜码**：用**参数化用例把已知的措辞逐条钉住**，
   并覆盖守卫 → 索引 → 图谱 → 模型四档的**判定优先级**与 2026-10-04 修掉的那处真缺陷
   （裸词「图谱」曾让**任何**模型侧失败都被误标成 3001）。

**已知技术债的显式标注（评审 P1-9）**：`_classify_failure` 的实现依赖**中文措辞子串**，
不是结构化判据；同义但换了措辞的日志会落到 9999 未归类。测试在这里的作用是
**防止静默漂移**（措辞或优先级被改动即红），**不是**证明归类正确。这一条由
`test_classify_failure_depends_on_chinese_wordings_a_known_debt` 落成可执行读数。

本文件不连 MySQL、不连 Neo4j、不起服务、不联网：`errors.py` 与 `qa_service.py` 的导入
只读本地配置常量，数据库连接是**懒加载**的（`db.connect()` 才会连）。
FastAPI 的异常处理器装配（`install_exception_handlers`）需要起应用／走 TestClient，
**不在本文件覆盖面内**——那部分由第 9 阶段门禁（`工具\\验收第9阶段.py`）覆盖。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

errors = _bootstrap.load_backend("errors")
qa_service = _bootstrap.load_backend("services.qa_service")

# 14 个错误码及其登记语义（逐条抄自 `errors.py` 的 CODES，作为**独立于实现的**期望表）
EXPECTED_CODES = {
    1001: ("输入为空或长度超出限制", 400),
    1002: ("参数格式错误", 400),
    1003: ("必填字段缺失", 400),
    1004: ("请求频率超出限制", 429),
    2001: ("资源不存在", 404),
    2002: ("查询结果为空", 200),
    2003: ("文档已被历史回答引用", 409),
    3001: ("图谱服务不可用", 503),
    3002: ("大模型接口超时", 504),
    3003: ("向量索引不可用", 500),
    3004: ("装配账目守卫未通过（上游一致性守卫，非图谱或模型故障）", 502),
    4001: ("凭据无效", 401),
    4002: ("无操作权限", 403),
    9999: ("服务内部错误", 500),
}


# ---------------------------------------------------------------------------
# D1 码表：14 个码、语义单一
# ---------------------------------------------------------------------------
def test_codes_table_has_fourteen_single_meaning_codes():
    assert len(errors.CODES) == len(EXPECTED_CODES) == 14
    assert set(errors.CODES) == set(EXPECTED_CODES)
    messages = [value[0] for value in errors.CODES.values()]
    assert len(set(messages)) == len(messages), "同一条 message 不得对应两个码（语义必须单一）"
    for code, (message, status) in EXPECTED_CODES.items():
        assert errors.CODES[code] == (message, status), "码 %d 的语义被改动" % code
        assert errors.message_of(code) == message
        assert errors.http_status_of(code) == status
        assert 400 <= status <= 599 or status == 200


def test_error_code_bands_and_http_statuses():
    """1xxx＝输入／客户端、2xxx＝资源、3xxx＝依赖与上游、4xxx＝凭据与权限。"""
    assert [errors.http_status_of(c) for c in (1001, 1002, 1003, 1004)] == [400, 400, 400, 429]
    assert [errors.http_status_of(c) for c in (2001, 2002, 2003)] == [404, 200, 409]
    assert [errors.http_status_of(c) for c in (3001, 3002, 3003, 3004)] == [503, 504, 500, 502]
    assert [errors.http_status_of(c) for c in (4001, 4002)] == [401, 403]
    assert errors.http_status_of(9999) == 500


def test_only_2002_is_a_normal_business_status():
    assert errors.is_normal(2002) is True
    assert errors.NORMAL_CODES == frozenset({2002})
    assert errors.CODE_EMPTY_RESULT == 2002
    assert errors.http_status_of(2002) == 200, "查询结果为空是 200，不是 4xx／5xx"
    for code in EXPECTED_CODES:
        if code != 2002:
            assert errors.is_normal(code) is False


# ---------------------------------------------------------------------------
# D2 响应体：键集合恰为 {code, message}，detail 只进日志
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("code", sorted(EXPECTED_CODES))
def test_response_body_keyset_is_exactly_code_and_message(code):
    exc = errors.ApiError(code, detail="只应进日志的调试信息：db_password=***")
    payload = exc.payload()
    assert set(payload) == {"code", "message"}
    assert payload["code"] == code
    assert payload["message"] == errors.message_of(code)
    assert "detail" not in payload
    assert "只应进日志的调试信息" not in str(payload)
    assert exc.detail is not None and "只应进日志的调试信息" in exc.detail
    assert str(exc) == "[%d] %s" % (code, errors.message_of(code)), \
        "异常字符串里也不得带 detail"


def test_error_payload_and_uncaught_payload():
    assert errors.error_payload(2003) == {"code": 2003, "message": "文档已被历史回答引用"}
    assert errors.error_payload(2003, message="自定义说明") == {"code": 2003, "message": "自定义说明"}
    assert set(errors.uncaught_payload()) == {"code", "message"}
    assert errors.uncaught_payload()["code"] == errors.UNCAUGHT_CODE == 9999


def test_success_envelope_shape():
    ok = errors.ok({"x": 1})
    assert set(ok) == {"data", "meta"}
    assert ok["data"] == {"x": 1}
    assert {"dataset_version", "data_cutoff_time"} <= set(ok["meta"])
    page = errors.page_payload(3, [{"a": 1}], 1, 20)
    assert set(page) == {"total", "items", "page", "page_size"}
    assert errors.ok_page(3, [{"a": 1}], 1, 20)["data"] == page
    assert errors.ok_empty()["data"] == {"total": 0, "items": [], "page": 1, "page_size": 0}


# ---------------------------------------------------------------------------
# D3 未登记码一律兜底到 9999（message／http），但响应体仍回原码
# ---------------------------------------------------------------------------
def test_unknown_code_falls_back_to_9999_semantics():
    assert errors.message_of(12345) == errors.message_of(9999)
    assert errors.http_status_of(12345) == errors.http_status_of(9999) == 500
    assert errors.is_normal(12345) is False
    exc = errors.ApiError(12345, detail="未登记的码")
    assert exc.code == 12345, "响应体仍回调用方给的那个码（便于核对《25》）"
    assert exc.message == errors.message_of(9999)
    assert exc.http_status == 500


def test_non_numeric_code_is_normalized_to_9999():
    assert errors.ApiError("not-a-code").code == 9999
    assert errors.ApiError(None).code == 9999


# ---------------------------------------------------------------------------
# D4 HTTP 状态 → 错误码：取值必须在码表内，且往返一致
# ---------------------------------------------------------------------------
def test_http_status_to_code_mapping_is_consistent():
    expected = {400: 1002, 401: 4001, 403: 4002, 404: 2001, 409: 2003, 429: 1004,
                503: 3001, 504: 3002}
    assert errors.HTTP_STATUS_TO_CODE == expected
    for status, code in errors.HTTP_STATUS_TO_CODE.items():
        assert code in errors.CODES, "映射目标必须是登记过的码"
        assert errors.http_status_of(code) == status, \
            "反向映射必须回到同一个 HTTP 状态（status=%d code=%d）" % (status, code)


# ---------------------------------------------------------------------------
# D5 _classify_failure：把已知的中文措辞逐条钉住（防止静默漂移）
# ---------------------------------------------------------------------------
GUARD_CASES = [
    ("…\ntoken 账现场重算与上游 trace 不一致——现场 text+path+event_triple=3177、"
     "trace total_tokens=3446\n", 3004),
    ("[装配] 预算守卫未通过，拒绝出答案", 3004),
    ("现场 text+path+event_triple=3177", 3004),
]
INDEX_CASES = [
    ("ImportError: No module named 'faiss'", 3003),
    ("向量索引不可用：index 文件缺失", 3003),
    ("索引文件损坏：faiss.index", 3003),
    ("vector_map.jsonl 行数与索引不一致", 3003),
    ("build_meta.json 缺失", 3003),
    ("vector index load failed", 3003),
    ("向量检索组件初始化失败", 3003),
]
GRAPH_CASES = [
    ("neo4j: connection refused", 3001),
    ("bolt://localhost:7687 不可达", 3001),
    ("GraphDatabase.driver 抛错", 3001),
    ("GraphService 未就绪", 3001),
    ("图谱服务不可用", 3001),
    ("图谱查询层 G1 执行失败", 3001),
    ("GraphReader 初始化失败", 3001),
]
MODEL_CASES = [
    ("URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING]>", 3002),
    ("HTTPSConnectionPool: Read timed out.", 3002),
    ("connection reset by peer", 3002),
    ("模型调用失败：返回体为空", 3002),
    ("大模型接口返回 500", 3002),
    ("api.deepseek.com 连接失败", 3002),
    ("deepseek-flash 两次尝试均空正文", 3002),
]
UNCLASSIFIED_CASES = [
    ("", 9999),
    ("Traceback (most recent call last): ValueError: 未知问题", 9999),
    ("子进程退出码 1（日志尾部：略）", 9999),
]


@pytest.mark.parametrize("text,expected", GUARD_CASES, ids=["guard-1", "guard-2", "guard-3"])
def test_classify_failure_guard_markings(text, expected):
    assert qa_service._classify_failure(text) == expected


@pytest.mark.parametrize("text,expected", INDEX_CASES,
                         ids=["faiss", "vector-index-zh", "index-file-zh", "vector-map",
                              "build-meta", "vector-index-en", "vector-search-zh"])
def test_classify_failure_index_markings(text, expected):
    assert qa_service._classify_failure(text) == expected


@pytest.mark.parametrize("text,expected", GRAPH_CASES,
                         ids=["neo4j", "bolt", "graphdatabase", "graphservice",
                              "graph-service-zh", "graph-layer-zh", "graphreader"])
def test_classify_failure_graph_markings(text, expected):
    assert qa_service._classify_failure(text) == expected


@pytest.mark.parametrize("text,expected", MODEL_CASES,
                         ids=["urlerror", "timed-out", "connection-reset", "call-failed-zh",
                              "llm-zh", "deepseek-endpoint", "deepseek-model"])
def test_classify_failure_model_markings(text, expected):
    assert qa_service._classify_failure(text) == expected


@pytest.mark.parametrize("text,expected", UNCLASSIFIED_CASES,
                         ids=["empty", "unrelated-traceback", "no-marks"])
def test_classify_failure_falls_back_to_9999(text, expected):
    assert qa_service._classify_failure(text) == expected


@pytest.mark.parametrize("text,expected", [
    # 四档同时出现时的优先级：守住 → 索引 → 图谱 → 模型
    ("预算守卫未通过；向量索引不可用；neo4j 不可达；SSL 失败", 3004),
    ("向量索引不可用；neo4j 不可达；SSL 失败", 3003),
    ("neo4j 不可达；SSL 失败", 3001),
    ("SSL 失败；timed out", 3002),
], ids=["guard-first", "index-before-graph", "graph-before-model", "model-only"])
def test_classify_failure_priority(text, expected):
    assert qa_service._classify_failure(text) == expected


def test_classify_failure_never_returns_an_unregistered_code():
    for text, _expected in GUARD_CASES + INDEX_CASES + GRAPH_CASES + MODEL_CASES \
            + UNCLASSIFIED_CASES:
        assert qa_service._classify_failure(text) in errors.CODES


# ---------------------------------------------------------------------------
# D6 2026-10-04 修掉的真缺陷：裸词「图谱」不得再当图谱故障的证据
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    # 第 8 阶段每次失败都会打印的装配状态行（含「图谱」二字），实测曾让全部模型侧失败被误标 3001
    "URLError: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING]>\n[生成] PE-02 … 图谱段BAD",
    "[生成] PE-03 … 图谱段BAD\n[生成] 两次尝试均空正文",
], ids=["ssl-failure-with-graph-status-line", "graph-status-line-only"])
def test_bare_graph_word_is_not_a_graph_service_marker(text):
    assert "图谱" in text, "本用例的材料必须含裸词「图谱」，否则它证明不了这处修复"
    code = qa_service._classify_failure(text)
    assert code != 3001, "裸词「图谱」不是图谱服务故障的证据（2026-10-04 修掉的误标）"
    assert code in (3002, 9999)


def test_graph_status_line_plus_real_graph_marks_still_maps_to_3001():
    assert qa_service._classify_failure("图谱段BAD\nneo4j 连接被拒绝") == 3001


# ---------------------------------------------------------------------------
# D7 已知技术债的显式读数（评审 P1-9）：措辞一换就归不了类
# ---------------------------------------------------------------------------
def test_classify_failure_depends_on_chinese_wordings_a_known_debt():
    """**已知技术债，如实登记**：同义但未含标记词的日志一律落到 9999 未归类。

    这不是"缺陷断言"（源码 docstring 明确写了兜底取 9999：「判不出类别时如实说不知道」），
    而是把 P1-9 那句"按字符串猜错误码"落成一条**可执行的读数**：
    归类能力只覆盖上面参数化用例列出的那批措辞，换一种写法就失效。
    """
    assert qa_service._classify_failure(
        "子进程退出码 1：模型服务返回 429，请稍后重试") == 9999
    assert qa_service._classify_failure("问答链路失败：原因见上") == 9999
    # 对照：同一类故障只要带上标记词就能归类
    assert qa_service._classify_failure("大模型接口返回 429，请稍后重试") == 3002
