# -*- coding: utf-8 -*-
r"""G 组 · API 路由层单测（2026-10-11 新增，对应《2026-10-11-全栈测试与代码审查报告》S4）。

被测面
------
`交付物/03-代码\后端\api\*.py` 六个路由模块（qa／evidence／history／graph／admin／market）
＋ `main.py` 的中间件与异常装配 ＋ `errors.py` 的统一信封——即审查报告中「实现层行覆盖为 0
且被排除在 coverage.json 分母外」的那一层。用例与表 4-13 的接口逐条对应（成功信封／参数
校验错误码／空结果语义／9999 兜底）。

离线纪律（与 A～F 组一致，`conftest.forbid_network` 审计钩子继续生效）
------------------------------------------------------------------
* TestClient 走 **ASGI 内存传输**（httpx ASGITransport），不建 socket、不起服务；
* 业务层一律 **monkeypatch 替身**：`qa_service`／`market_service` 的取数函数、
  `api.graph` 的 `reader()`（假 `GraphReader`）、`api.admin` 的 `db` 读写——
  不连 MySQL、不连 Neo4j、不跑问答链路、不调大模型；
* 限流中间件在夹具里把阈值临时放大，避免几十个用例互相触发 429 干扰判读。

钉住的契约（改动即红，防漂移）
----------------------------
1. 成功响应一律 `{data, meta}`（`meta` 含 `dataset_version`／`data_cutoff_time`）；
2. 错误响应键集合**恰为** `{code, message}`，任何响应体不出现 `detail` 键（硬约束 7）；
3. 空结果是 **HTTP 200 的空数据**（2002 语义），不是错误码；
4. 未捕获异常 → HTTP 500 ＋ 9999；路径参数类型错（422）→ 1002；
5. `/api/qa/ask` 缺 `question`／缺 `session_id` → **1003**（S6 修复后的契约）；
6. `/api/admin/*` 无共享密钥 → **401/4001（fail closed）**（S1 修复后的契约）。
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

main_mod = _bootstrap.load_backend("main")
errors_mod = _bootstrap.load_backend("errors")
qa_service = _bootstrap.load_backend("services.qa_service")
market_service = _bootstrap.load_backend("services.market_service")
graph_api = _bootstrap.load_backend("api.graph")
gs = graph_api.gs                      # api.graph 引用的同一份 graph_service 实例
admin_api = _bootstrap.load_backend("api.admin")

TEST_TOKEN = "g-group-test-admin-token"


# ---------------------------------------------------------------------------
# 替身：假 GraphReader（api.graph 的 reader() 上下文管理器被整体替掉）
# ---------------------------------------------------------------------------
class FakeGraph:
    """只回确定性读数的图谱后端替身（不连 Neo4j、不读导出物）。"""

    def __init__(self):
        self.adj = {}
        self.nodes = {}          # consistency-check 的内存后端统计会读 nodes／edges
        self.edges = {}

    def g1_one_hop(self, node_id):
        nid = str(node_id)
        if nid == "GHOST":
            return {"code": gs.RC_NOT_FOUND, "results": []}
        if nid == "BAD_ID":
            return {"code": gs.RC_INVALID_INPUT, "results": []}
        if nid == "E-A":
            return {"code": gs.RC_OK, "results": [{
                "edge_id": "e9", "relation": "PARTICIPATES_IN", "direction": "in",
                "neighbor": "N1", "role": "主体",
                "neighbor_node": {"node_id": "N1", "label": "Company", "name": "甲公司"},
            }]}
        return {"code": gs.RC_OK, "results": [{
            "edge_id": "e1", "relation": "RELATED_TO", "direction": "out",
            "neighbor": "N2", "role": "涉及方", "confidence": 0.5,
            "neighbor_node": {"node_id": "N2", "label": "Company", "name": "乙公司"},
        }]}

    def g2_two_hop(self, node_id):
        return self.g1_one_hop(node_id)

    def resolve_node(self, node_id):
        return {"code": gs.RC_OK, "node_ids": [str(node_id)]}

    def relation_paths(self, node_id, relation, hop):
        return []

    def g3_events_by_type(self, etype):
        return {"code": gs.RC_OK, "results": [{
            "node_id": "E-A", "event_id": "E-A", "event_type": str(etype),
            "event_name": "甲公司年度业绩", "event_time": "2026-03-01",
            "description": "年度业绩披露", "confidence": 0.9}]}

    def g4_company_events(self, code):
        return {"code": gs.RC_NOT_FOUND, "results": []}

    def g5_event_evidence(self, eid):
        return {"code": gs.RC_OK, "results": []}

    def g7_paths(self, source, target, max_depth=2):
        return {"code": gs.RC_NOT_FOUND, "results": []}


class FakeReader:
    """`api.graph.reader()` 的替身返回对象：只暴露路由函数用到的方法。"""

    def __init__(self):
        self.graph = FakeGraph()
        self.backend = "memory"

    def search(self, keyword, label):
        return [("Company", {"node_id": "N1", "name": "甲公司", "stock_code": "000001"})]

    def brief(self, node_id):
        return {"node_id": str(node_id), "label": "Company", "name": "甲公司"}

    def relation_paths(self, node_id, relation, hop):
        return []

    def _raw_node(self, node_id):
        nid = str(node_id)
        if nid == "GHOST":
            return None
        if nid == "E-A":
            return {"node_id": "E-A", "label": "Event", "event_id": "E-A",
                    "event_type": "业绩", "event_name": "甲公司年度业绩",
                    "event_time": "2026-03-01", "description": "年度业绩披露",
                    "confidence": 0.9}
        return {"node_id": nid, "label": "Company", "name": "甲公司",
                "stock_code": "000001", "aliases": "甲公司|JIA"}

    def label_of(self, node_id):
        return {"N1": "Company", "E-A": "Event"}.get(str(node_id))

    def all_events(self):
        return []

    def evidence_doc_counts(self, node_ids):
        return {str(k): 1 for k in (node_ids or [])}

    def relation(self, node_id):
        return None


def _fake_reader_ctx(monkeypatch):
    """把 `api.graph.reader()` 换成返回 FakeReader 的上下文管理器。"""
    import contextlib
    monkeypatch.setattr(graph_api, "reader",
                        contextlib.contextmanager(lambda: (yield FakeReader())))


# ---------------------------------------------------------------------------
# 夹具：TestClient（内存传输）＋ 放大限流阈值
# ---------------------------------------------------------------------------
def _find_middleware(app, cls):
    node = getattr(app, "middleware_stack", None)
    while node is not None:
        if isinstance(node, cls):
            return node
        node = getattr(node, "app", None)
    return None


@pytest.fixture()
def client(monkeypatch):
    # 本环境的 TestClient 把中间件栈的构建推迟到**首次请求**之后，夹具里拿不到真正
    # 处理请求的 RateLimitMiddleware 实例；几十个用例共享同一 app 时，60 次／60 秒的
    # 默认阈值会让后半程用例互相触发 429（1004）。故在**类级**停用限流判定——
    # 对任何栈／任何实例都生效；限流行为本身的真实性由 .workbuddy/test-audit 的
    # test_s1_s2_fixes.py 用真实实例直接驱动 _over_limit 验证（不经 HTTP）。
    with TestClient(main_mod.app) as c:
        monkeypatch.setattr(main_mod.RateLimitMiddleware, "_over_limit",
                            lambda self, ip: False)
        yield c


def _fake_ask(question, session_id, group):
    """`qa_service.ask` 的九键替身（表 4-13 的载荷形状）。"""
    return {"answer_id": 40, "question_id": 40, "answer_text": "【回答】替身答案",
            "answer_type": "未标注", "data_cutoff_time": "2026-06-30T00:00:00+08:00",
            "evidence": [{"chunk_id": 101, "doc_id": 1}], "graph_path": None,
            "is_graph_extended": False, "time_interpretation": "【数据截至与判定区间】替身"}


# ---------------------------------------------------------------------------
# G1 信封与统一兜底（以 qa/evidence 为载体）
# ---------------------------------------------------------------------------
def test_g1_success_envelope_is_data_meta(client, monkeypatch):
    """成功响应一律 {data, meta}；meta 带 dataset_version／data_cutoff_time。"""
    monkeypatch.setattr(qa_service, "get_answer", lambda answer_id: {"answer_id": answer_id})
    r = client.get("/api/qa/answers/40")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"data", "meta"}
    assert body["data"] == {"answer_id": 40}
    assert body["meta"]["dataset_version"] == "v2.1"
    assert body["meta"]["data_cutoff_time"]


def test_g1_uncaught_exception_becomes_9999(client_factory, monkeypatch):
    """业务层未捕获异常 → HTTP 500 ＋ 9999，堆栈只进日志。

    注：TestClient 默认 `raise_server_exceptions=True` 会把服务端异常上抛给测试端
    （便于断言异常本身）；这里用 False 档验证**客户端实际收到的 500 响应**。
    """
    def _boom(answer_id):
        raise RuntimeError("替身内部故障")
    monkeypatch.setattr(qa_service, "get_answer", _boom)
    with client_factory(raise_server_exceptions=False) as c:
        r = c.get("/api/qa/answers/40")
    assert r.status_code == 500
    assert r.json() == {"code": 9999, "message": "服务内部错误"}


@pytest.fixture()
def client_factory():
    """按需构造 TestClient（用于需要非默认参数的个别用例）。"""
    def _make(**kwargs):
        return TestClient(main_mod.app, **kwargs)
    return _make


def test_g1_path_type_mismatch_becomes_1002(client):
    """路径参数类型错（FastAPI 422）→ 统一转 1002/HTTP 400。"""
    r = client.get("/api/qa/answers/not-an-int")
    assert r.status_code == 400
    assert r.json()["code"] == 1002


def test_g1_resource_missing_becomes_2001(client, monkeypatch):
    """业务层抛 ApiError(2001) → HTTP 404 ＋ {code, message}，detail 不进响应体。"""
    def _missing(answer_id):
        raise errors_mod.ApiError(2001, detail="回答不存在：answer_id=40（只进日志）")
    monkeypatch.setattr(qa_service, "get_answer", _missing)
    r = client.get("/api/qa/answers/40")
    assert r.status_code == 404
    body = r.json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == 2001
    assert "answer_id=40" not in r.text, "detail 只进日志，不得出现在响应体"


# ---------------------------------------------------------------------------
# G2 /api/qa（表 4-13 三条）
# ---------------------------------------------------------------------------
def test_g2_ask_success_returns_nine_keys(client, monkeypatch):
    monkeypatch.setattr(qa_service, "ask", _fake_ask)
    r = client.post("/api/qa/ask",
                    json={"question": "甲公司2026年的业绩如何？", "session_id": "S-G-TEST-0001"})
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    for key in ("answer_id", "answer_text", "answer_type", "data_cutoff_time", "evidence",
                "graph_path", "is_graph_extended", "question_id", "time_interpretation"):
        assert key in data, "载荷缺 %s" % key


def test_g2_ask_missing_question_is_1003(client):
    """S6 契约：缺 question 键 → 1003（必填字段缺失），不再是 1001。"""
    r = client.post("/api/qa/ask", json={"session_id": "S-G-TEST-0001"})
    assert r.status_code == 400
    assert r.json()["code"] == 1003


def test_g2_ask_missing_session_id_is_1003(client):
    r = client.post("/api/qa/ask", json={"question": "甲公司2026年的业绩如何？"})
    assert r.status_code == 400
    assert r.json()["code"] == 1003


def test_g2_ask_question_too_long_is_1001(client):
    r = client.post("/api/qa/ask",
                    json={"question": "x" * 501, "session_id": "S-G-TEST-0001"})
    assert r.status_code == 400
    assert r.json()["code"] == 1001


def test_g2_ask_group_switch_field_is_1002(client):
    """硬约束 9：出现分组开关字段一律 1002。"""
    r = client.post("/api/qa/ask", json={"question": "q", "session_id": "S-G-TEST-0001",
                                         "experiment_group": "A"})
    assert r.status_code == 400
    assert r.json()["code"] == 1002


def test_g2_ask_session_id_too_long_is_1002(client):
    r = client.post("/api/qa/ask", json={"question": "q", "session_id": "S" * 37})
    assert r.status_code == 400
    assert r.json()["code"] == 1002


def test_g2_config_meta_success(client, monkeypatch):
    monkeypatch.setattr(qa_service, "config_meta",
                        lambda: {"dataset_version": "v2.1", "K": 6, "N": 12})
    r = client.get("/api/config/meta")
    assert r.status_code == 200
    assert r.json()["data"]["dataset_version"] == "v2.1"


# ---------------------------------------------------------------------------
# G3 /api/evidence（表 4-13 三条）
# ---------------------------------------------------------------------------
def test_g3_evidence_success_and_filter_validation(client, monkeypatch):
    seen = {}

    def _fake(answer_id, evidence_type=None, group_by=None):
        seen.update(evidence_type=evidence_type, group_by=group_by)
        return {"total": 1, "counts": {"回答来源": 1}, "items": []}

    monkeypatch.setattr(qa_service, "evidence_of_answer", _fake)
    r = client.get("/api/evidence/40", params={"evidence_type": "回答来源"})
    assert r.status_code == 200
    assert seen == {"evidence_type": "回答来源", "group_by": None}

    r2 = client.get("/api/evidence/40", params={"evidence_type": "不存在的类"})
    assert r2.status_code == 400 and r2.json()["code"] == 1002
    r3 = client.get("/api/evidence/40", params={"group_by": "doc_id"})
    assert r3.status_code == 400 and r3.json()["code"] == 1002


def test_g3_graph_path_success(client, monkeypatch):
    monkeypatch.setattr(qa_service, "graph_path_of_answer",
                        lambda answer_id: {"is_graph_extended": False, "paths": None,
                                           "display_mode": "not_used"})
    r = client.get("/api/evidence/40/graph-path")
    assert r.status_code == 200
    assert r.json()["data"]["is_graph_extended"] is False


def test_g3_chunk_detail_success(client, monkeypatch):
    monkeypatch.setattr(qa_service, "chunk_detail",
                        lambda doc_id, chunk_id: {"chunk": {"chunk_id": chunk_id,
                                                            "content": "原文照抄"}})
    r = client.get("/api/documents/1/chunks/101")
    assert r.status_code == 200
    assert r.json()["data"]["chunk"]["chunk_id"] == 101


# ---------------------------------------------------------------------------
# G4 /api/history（表 4-13 两条；M11 书面裁决＝维持实现口径「缺 session_id→1002」，
# 见《25》修订记录 v1.19 第 ⑦ 条：防御性拒绝优于静默空历史，安全内核一致）
# ---------------------------------------------------------------------------
def _fake_history_list(sid, page, size):
    return {"total": 0, "items": [], "page": page, "page_size": size}


def test_g4_history_empty_is_http200_not_error(client, monkeypatch):
    """空结果是 2002 语义：HTTP 200 空数据，响应体不出现错误码。"""
    monkeypatch.setattr(qa_service, "history_list", _fake_history_list)
    r = client.get("/api/history", params={"session_id": "S-G-TEST-0001"})
    assert r.status_code == 200
    body = r.json()
    assert "code" not in body
    assert body["data"]["total"] == 0 and body["data"]["items"] == []


def test_g4_history_missing_session_id_is_1002(client):
    r = client.get("/api/history")
    assert r.status_code == 400
    assert r.json()["code"] == 1002


def test_g4_history_pagination_validation(client, monkeypatch):
    monkeypatch.setattr(qa_service, "history_list", _fake_history_list)
    r1 = client.get("/api/history", params={"session_id": "S", "page": "0"})
    r2 = client.get("/api/history", params={"session_id": "S", "page_size": "999"})
    r3 = client.get("/api/history", params={"session_id": "S", "page": "abc"})
    assert all(r.status_code == 400 and r.json()["code"] == 1002 for r in (r1, r2, r3))


def test_g4_history_detail_success_and_2001(client, monkeypatch):
    monkeypatch.setattr(qa_service, "history_detail",
                        lambda qid, sid: {"question_id": qid, "answer_text": "【回答】x"})
    r = client.get("/api/history/40", params={"session_id": "S-G-TEST-0001"})
    assert r.status_code == 200 and r.json()["data"]["question_id"] == 40

    def _cross(qid, sid):
        raise errors_mod.ApiError(2001, detail="跨会话访问（只进日志）")
    monkeypatch.setattr(qa_service, "history_detail", _cross)
    r2 = client.get("/api/history/40", params={"session_id": "S-OTHER"})
    assert r2.status_code == 404 and r2.json()["code"] == 2001


# ---------------------------------------------------------------------------
# G5 /api/graph（表 4-13 五条 ＋ 实体详情/实体证据两条补充接口）
# ---------------------------------------------------------------------------
def test_g5_entities_success(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities", params={"keyword": "甲公司", "type": "Company"})
    assert r.status_code == 200, r.text[:300]
    body = r.json()["data"]
    items = body["items"]
    assert body["total"] == 1
    assert items[0]["node_id"] == "N1" and items[0]["label"] == "Company"
    assert items[0]["stock_code"] == "000001"


def test_g5_entities_type_and_page_validation(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r1 = client.get("/api/graph/entities", params={"type": "NotAType"})
    r2 = client.get("/api/graph/entities", params={"page_size": "0"})
    assert r1.status_code == 400 and r1.json()["code"] == 1002
    assert r2.status_code == 400 and r2.json()["code"] == 1002


def test_g5_neighbors_success(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/N1/neighbors")
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["total"] == 1
    assert data["edges"][0]["relation"] == "RELATED_TO"
    assert data["nodes"][0]["name"] == "乙公司"
    assert data["node"]["node_id"] == "N1"


def test_g5_neighbors_node_not_found_is_2001(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/GHOST/neighbors")
    assert r.status_code == 404
    assert r.json()["code"] == 2001


def test_g5_neighbors_relation_validation(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/N1/neighbors", params={"relation": "NOT_A_RELATION"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g5_paths_parameter_validation(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r1 = client.get("/api/graph/paths", params={"to_node": "N2"})          # 缺 from_node
    r2 = client.get("/api/graph/paths", params={"from_node": "N1", "to_node": "N2",
                                                "hop": "3"})                # hop 上限 2
    assert r1.status_code == 400 and r1.json()["code"] == 1002
    assert r2.status_code == 400 and r2.json()["code"] == 1002


def test_g5_paths_success_empty(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    relation = graph_api.RELATIONS[0]
    r = client.get("/api/graph/paths", params={"from_node": "N1", "relation": relation,
                                               "hop": "1"})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["is_graph_extended"] is False


def test_g5_events_type_validation_and_empty(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r1 = client.get("/api/graph/events", params={"event_type": "不属于任何类型"})
    assert r1.status_code == 400 and r1.json()["code"] == 1002
    r2 = client.get("/api/graph/events", params={"event_type": graph_api.EVENT_TYPES[0]})
    assert r2.status_code == 200, r2.text[:300]


def test_g5_event_detail_not_found_is_2001(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/events/GHOST")
    assert r.status_code == 404 and r.json()["code"] == 2001


def test_g5_backend_down_is_3001(client, monkeypatch):
    """图谱后端打不开（open_backend 以 SystemExit 报告）→ 收敛为 3001，不自动降级。"""
    def _broken(name=None):
        raise SystemExit("Neo4j 不可连接（替身）")
    monkeypatch.setattr(gs, "open_backend", _broken)
    r = client.get("/api/graph/entities/N1/neighbors")
    assert r.status_code == 503
    assert r.json()["code"] == 3001


# ---------------------------------------------------------------------------
# G5b /api/graph 补充：实体详情／实体证据／开关／事件成功路径（第 9 阶段新增接口）
# ---------------------------------------------------------------------------
def test_g5b_entity_detail_success(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/N1")
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["scope"] == "entity_detail"
    assert data["node"] == {"node_id": "N1", "label": "Company",
                            "name": "甲公司", "stock_code": "000001"}
    assert data["properties"].get("aliases") == "甲公司|JIA"
    assert data["property_keys"] == sorted(data["property_keys"])
    assert data["degree"] == {"out": 0, "in_": 0, "total": 0}   # 内存后端：adj 为空
    assert data["counts"]["relations"] == 1


def test_g5b_entity_detail_not_found_is_2001(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/GHOST")
    assert r.status_code == 404 and r.json()["code"] == 2001


def test_g5b_entity_evidence_success_empty_documents(client, monkeypatch):
    """边不带证据属性 → documents 空（2002 语义）＋ relations_without_evidence 如实列出。"""
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/N1/evidence")
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["scope"] == "entity_evidence"
    assert data["counts"]["relations"] == 1
    assert data["documents_total"] == 0
    assert len(data["relations_without_evidence"]) == 1


def test_g5b_entity_evidence_depth_validation(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/N1/evidence", params={"depth": "3"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g5b_neighbors_with_properties_switch(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/entities/N1/neighbors", params={"with_properties": "1"})
    assert r.status_code == 200
    # properties 省略 brief 顶层已有字段（PROP_SKIP），Company 的真实属性如 aliases 保留
    assert r.json()["data"]["node"].get("properties", {}).get("aliases") == "甲公司|JIA"


def test_g5b_paths_time_window_validation(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/paths", params={"from_node": "N1", "to_node": "N2",
                                               "start_time": "2026-12-31",
                                               "end_time": "2026-01-01"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g5b_paths_fixed_target_not_found_is_empty_200(client, monkeypatch):
    """定点模式：G7 未命中 → HTTP 200 ＋ paths=[]（空结果不是错误）。"""
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/paths", params={"from_node": "N1", "to_node": "N2",
                                               "hop": "2"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["paths"] == [] and data["is_graph_extended"] is False


def test_g5b_events_by_type_success_with_time_window(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r1 = client.get("/api/graph/events",
                    params={"event_type": graph_api.EVENT_TYPES[0],
                            "start_time": "2026-01-01", "end_time": "2026-12-31"})
    assert r1.status_code == 200, r1.text[:300]
    items = r1.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["event_id"] == "E-A" and items[0]["node_id"] == "E-A"
    # 窗口外：event_time=2026-03-01 不落在 2027 年 → 空结果
    r2 = client.get("/api/graph/events",
                    params={"event_type": graph_api.EVENT_TYPES[0],
                            "start_time": "2027-01-01", "end_time": "2027-12-31"})
    assert r2.status_code == 200 and r2.json()["data"]["items"] == []


def test_g5b_events_by_stock_code_empty(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/events", params={"stock_code": "000001"})
    assert r.status_code == 200 and r.json()["data"]["items"] == []


def test_g5b_event_detail_success(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/events/E-A")
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["event"]["event_id"] == "E-A"
    assert data["event"]["event_type"] == "业绩"
    assert data["participants"][0]["node_id"] == "N1"
    assert data["evidences"] == [] and data["evidence_total"] == 0


def test_g5b_event_detail_not_event_node_is_2001(client, monkeypatch):
    _fake_reader_ctx(monkeypatch)
    r = client.get("/api/graph/events/N1")          # Company 节点 → 2001
    assert r.status_code == 404 and r.json()["code"] == 2001


# ---------------------------------------------------------------------------
# G6 /api/market（作者新增四条，表 4-13 之外）
# ---------------------------------------------------------------------------
def test_g6_quote_success_with_default_codes(client, monkeypatch):
    seen = {}

    def _fake(codes):
        seen["codes"] = codes
        return {"connected": True, "scope": "display_only", "items": []}

    monkeypatch.setattr(market_service, "quotes", _fake)
    r = client.get("/api/market/quote")
    assert r.status_code == 200
    assert seen["codes"] == ["000001", "600519"]


def test_g6_quote_invalid_code_is_1002(client, monkeypatch):
    monkeypatch.setattr(market_service, "quotes", lambda codes: {})
    r = client.get("/api/market/quote", params={"codes": "abc"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g6_announcements_missing_code_is_1003(client, monkeypatch):
    monkeypatch.setattr(market_service, "announcements", lambda *a: {})
    r = client.get("/api/market/announcements")
    assert r.status_code == 400 and r.json()["code"] == 1003


def test_g6_days_out_of_range_is_1002(client, monkeypatch):
    monkeypatch.setattr(market_service, "corpus_reports", lambda *a: {})
    r = client.get("/api/market/reports", params={"days": "99"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g6_news_missing_keyword_is_1003(client, monkeypatch):
    monkeypatch.setattr(market_service, "news", lambda *a: {})
    r = client.get("/api/market/news")
    assert r.status_code == 400 and r.json()["code"] == 1003


def test_g6_page_size_validation(client, monkeypatch):
    monkeypatch.setattr(market_service, "news", lambda *a: {})
    r = client.get("/api/market/news", params={"keyword": "业绩", "page_size": "0"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g6_reports_success(client, monkeypatch):
    monkeypatch.setattr(market_service, "corpus_reports",
                        lambda days, size: {"connected": True, "scope": "display_only",
                                            "items": [], "days": days})
    r = client.get("/api/market/reports", params={"days": "7"})
    assert r.status_code == 200
    assert r.json()["data"]["days"] == 7


# ---------------------------------------------------------------------------
# G7 /api/admin（S1 修复后的三态 ＋ 带密钥的代表性成功路径）
# ---------------------------------------------------------------------------
def _admin_headers():
    return {"X-Admin-Token": TEST_TOKEN}


def test_g7_admin_without_credentials_fail_closed(client):
    """S1：无凭据写库请求 → 401/4001（fail closed；不再裸放行）。"""
    r = client.post("/api/admin/documents", json={"title": "t", "raw_text": "x"})
    assert r.status_code == 401
    assert r.json() == {"code": 4001, "message": errors_mod.message_of(4001)}


def test_g7_admin_frontend_origin_is_4002(client):
    origin = main_mod.config.CORS_ORIGINS[0]
    r = client.get("/api/admin/documents", headers={"Origin": origin})
    assert r.status_code == 403 and r.json()["code"] == 4002


def test_g7_admin_wrong_token_is_401(client):
    r = client.post("/api/admin/documents", json={"title": "t", "raw_text": "x"},
                    headers={"X-Admin-Token": "wrong-token"})
    assert r.status_code == 401 and r.json()["code"] == 4001


def test_g7_admin_list_documents_success(client, monkeypatch):
    """带正确共享密钥 ＋ db 替身 → 200 信封；items 六键与表 4-13 一致。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api.db, "scalar", lambda sql, args=None: 2)
    monkeypatch.setattr(admin_api.db, "query", lambda sql, args=None: [{
        "doc_id": 1, "title": "甲公司公告", "source": "cninfo",
        "publish_time": "2026-03-02 10:00:00", "ingest_time": "2026-03-02 11:00:00",
        "category": "公告", "chunk_count": 12}])
    r = client.get("/api/admin/documents", headers=_admin_headers())
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["total"] == 2
    item = data["items"][0]
    for key in ("doc_id", "title", "source", "publish_time", "ingest_time", "chunk_count"):
        assert key in item, "items 缺表 4-13 字段 %s" % key
    assert item["doc_id"] == 1 and item["chunk_count"] == 12


def test_g7_admin_update_missing_document_is_2001(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api, "_doc_row", lambda doc_id: None)
    r = client.put("/api/admin/documents/99999", headers=_admin_headers(),
                   json={"title": "新题名", "content": "正文", "source": "cninfo",
                         "publish_time": "2026-03-02 10:00:00"})
    assert r.status_code == 404 and r.json()["code"] == 2001


def test_g7_admin_experiment_ask_missing_question_is_1001(client, monkeypatch):
    """experiment/ask 的表 4-13 登记码含 1001（与 /api/qa/ask 的 1003 口径不同，按表钉住）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    r = client.post("/api/admin/experiment/ask", headers=_admin_headers(), json={})
    assert r.status_code == 400 and r.json()["code"] == 1001


def test_g7_admin_consistency_check_success(client, monkeypatch):
    """带密钥 ＋ db／图谱替身 → 200 信封（一致性检查的只读统计路径）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api.db, "scalar", lambda sql, args=None: 5)
    monkeypatch.setattr(admin_api.db, "query", lambda sql, args=None: [])
    monkeypatch.setattr(gs, "open_backend", lambda name=None: (FakeGraph(), "memory"))
    r = client.get("/api/admin/consistency-check", headers=_admin_headers())
    assert r.status_code == 200, r.text[:300]
    assert isinstance(r.json()["data"], dict) and r.json()["data"]


def test_g7_admin_fallback_route_gate(client, monkeypatch):
    """未登记的 /api/admin/* 兜底路由：无密钥 → 401（S1）；带密钥 → 2001（资源不存在）。"""
    r1 = client.post("/api/admin/__gate_probe__", json={})
    assert r1.status_code == 401 and r1.json()["code"] == 4001
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    r2 = client.post("/api/admin/__gate_probe__", json={}, headers=_admin_headers())
    assert r2.status_code == 404 and r2.json()["code"] == 2001


def _fake_record_task(monkeypatch):
    """替掉台账写盘（_record_task 会写 _工作底稿\\后台任务台账.jsonl；测试保持只读）。"""
    calls = []

    def _fake(kind, **kwargs):
        calls.append((kind, kwargs))
        return {"task_id": "T-G-0001", "kind": kind, "status": "accepted",
                "note": str(kwargs.get("note") or "")}

    monkeypatch.setattr(admin_api, "_record_task", _fake)
    return calls


def test_g7_admin_reprocess_success(client, monkeypatch):
    """scope=all 的重处理登记 → 200；台账只登记不执行（executed=False）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    calls = _fake_record_task(monkeypatch)
    r = client.post("/api/admin/reprocess", headers=_admin_headers(), json={"scope": "all"})
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["task_id"] == "T-G-0001" and data["executed"] is False
    assert data["scope"] == "all"
    assert calls and calls[0][0] == "reprocess"


def test_g7_admin_reprocess_validation(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    _fake_record_task(monkeypatch)
    r1 = client.post("/api/admin/reprocess", headers=_admin_headers(),
                     json={"scope": "all", "unknown_field": 1})
    r2 = client.post("/api/admin/reprocess", headers=_admin_headers(),
                     json={"scope": "chunk"})
    r3 = client.post("/api/admin/reprocess", headers=_admin_headers(),
                     json={"scope": "not-a-scope"})
    assert r1.status_code == 400 and r1.json()["code"] == 1002
    assert r2.status_code == 400 and r2.json()["code"] == 1002
    assert r3.status_code == 400 and r3.json()["code"] == 1002


def test_g7_admin_delete_missing_document_is_2001(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api, "_doc_row", lambda doc_id: None)
    r = client.delete("/api/admin/documents/99999", headers=_admin_headers())
    assert r.status_code == 404 and r.json()["code"] == 2001


def test_g7_admin_delete_referenced_document_is_2003(client, monkeypatch):
    """被历史回答引用的文档 → 409/2003，响应体含 retained_for_history（表 4-13 例外）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api, "_doc_row", lambda doc_id: {"doc_id": doc_id})
    monkeypatch.setattr(admin_api, "_doc_reference_count", lambda doc_id: 3)
    r = client.delete("/api/admin/documents/1", headers=_admin_headers())
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == 2003 and body.get("retained_for_history") is True


def test_g7_admin_create_document_missing_required_is_1003(client, monkeypatch):
    """导入接口缺必填字段 → 1003（表 4-13 对 POST 列了 1003）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    r = client.post("/api/admin/documents", headers=_admin_headers(),
                    json={"content": "只有正文，缺 title", "source": "cninfo"})
    assert r.status_code == 400 and r.json()["code"] == 1003


def test_g7_admin_list_documents_time_window_validation(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    r = client.get("/api/admin/documents", headers=_admin_headers(),
                   params={"start_time": "2026-12-31", "end_time": "2026-01-01"})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g7_admin_extraction_run_success(client, monkeypatch):
    """抽取任务登记 → 200；五项统计未真跑全为 0、executed=False（第一版只登记）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    _fake_record_task(monkeypatch)
    r = client.post("/api/admin/extraction/run", headers=_admin_headers(),
                    json={"scope": "all"})
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["executed"] is False and data["task_id"] == "T-G-0001"
    assert data["processed_chunks"] == 0 and data["event_count"] == 0


def test_g7_admin_extraction_run_validation(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    _fake_record_task(monkeypatch)
    r1 = client.post("/api/admin/extraction/run", headers=_admin_headers(), json={})
    r2 = client.post("/api/admin/extraction/run", headers=_admin_headers(),
                     json={"scope": "all", "unknown": 1})
    r3 = client.post("/api/admin/extraction/run", headers=_admin_headers(),
                     json={"scope": "all", "prompt_version": "x" * 65})
    assert r1.status_code == 400 and r1.json()["code"] == 1003
    assert r2.status_code == 400 and r2.json()["code"] == 1002
    assert r3.status_code == 400 and r3.json()["code"] == 1002


def test_g7_admin_extraction_task_found_and_missing(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api, "_read_ledger", lambda path: [{
        "task_id": "T-G-0001", "kind": "extraction", "status": "accepted",
        "created_at": "2026-10-11T00:00:00", "scope": "all", "doc_ids": []}])
    r = client.get("/api/admin/extraction/tasks/T-G-0001", headers=_admin_headers())
    assert r.status_code == 200 and r.json()["data"]["task_id"] == "T-G-0001"

    monkeypatch.setattr(admin_api, "_read_ledger", lambda path: [])
    r2 = client.get("/api/admin/extraction/tasks/T-NOPE", headers=_admin_headers())
    assert r2.status_code == 404 and r2.json()["code"] == 2001


def test_g7_admin_extraction_events_success_and_validation(client, monkeypatch):
    import contextlib
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api, "reader",
                        contextlib.contextmanager(lambda: (yield FakeReader())))
    r = client.get("/api/admin/extraction/events",
                   headers=_admin_headers(),
                   params={"event_type": graph_api.EVENT_TYPES[0], "confidence_min": "0.5"})
    assert r.status_code == 200, r.text[:300]
    items = r.json()["data"]["items"]
    assert items and items[0]["evidence_doc_count"] == 1

    r2 = client.get("/api/admin/extraction/events", headers=_admin_headers(),
                    params={"event_type": graph_api.EVENT_TYPES[0], "confidence_min": "abc"})
    r3 = client.get("/api/admin/extraction/events", headers=_admin_headers(),
                    params={"event_type": graph_api.EVENT_TYPES[0], "confidence_min": "2"})
    r4 = client.get("/api/admin/extraction/events", headers=_admin_headers(),
                    params={"event_type": graph_api.EVENT_TYPES[0],
                            "start_time": "2026-12-31", "end_time": "2026-01-01"})
    assert all(x.status_code == 400 and x.json()["code"] == 1002 for x in (r2, r3, r4))


def test_g7_admin_disambiguation_list_success(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    rows = [{"entity_id": "D-1", "name": "某子公司", "matched_codes": ["000009"],
             "label": "Company", "doc_id": 7, "reason": "多候选",
             "normalized_name": "某子公司"}]
    monkeypatch.setattr(admin_api, "_disambig_rows", lambda: (rows, "fake-unresolved.jsonl",
                                                              "0" * 64))
    monkeypatch.setattr(admin_api, "_confirmations", lambda: {})
    monkeypatch.setattr(admin_api, "_unresolved_source", lambda: {})
    r = client.get("/api/admin/extraction/disambiguation", headers=_admin_headers())
    assert r.status_code == 200, r.text[:300]
    data = r.json()["data"]
    assert data["items"][0]["item_id"] == "D-1"
    assert data["items"][0]["status"] == "pending"
    disambig = r.json()["meta"]["disambiguation"]
    assert disambig["source_lines"] == 1 and disambig["pending"] == 1


def test_g7_admin_disambiguation_confirm_unknown_item_is_2001(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api, "_disambig_rows", lambda: ([], "fake-unresolved.jsonl",
                                                              "0" * 64))
    r = client.post("/api/admin/extraction/disambiguation/GHOST", headers=_admin_headers(),
                    json={"stock_code": "000001"})
    assert r.status_code == 404 and r.json()["code"] == 2001


def test_g7_admin_list_documents_filtered_success(client, monkeypatch):
    """带 source／category／时间窗过滤的成功路径（WHERE 构造分支）。"""
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    monkeypatch.setattr(admin_api.db, "scalar", lambda sql, args=None: 1)
    monkeypatch.setattr(admin_api.db, "query", lambda sql, args=None: [{
        "doc_id": 2, "title": "乙公司公告", "source": "cninfo",
        "publish_time": "2026-02-01 09:00:00", "ingest_time": "2026-02-01 10:00:00",
        "category": "公告", "chunk_count": 8}])
    r = client.get("/api/admin/documents", headers=_admin_headers(),
                   params={"source": "cninfo", "category": "公告",
                           "start_time": "2026-01-01", "end_time": "2026-12-31"})
    assert r.status_code == 200, r.text[:300]
    assert r.json()["data"]["items"][0]["doc_id"] == 2


def test_g7_admin_create_document_unknown_field_is_1002(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    r = client.post("/api/admin/documents", headers=_admin_headers(),
                    json={"title": "t", "content": "c", "source": "cninfo",
                          "publish_time": "2026-03-02", "unknown_field": 1})
    assert r.status_code == 400 and r.json()["code"] == 1002


def test_g7_admin_disambiguation_page_validation(client, monkeypatch):
    monkeypatch.setattr(admin_api.config, "ADMIN_TOKEN", TEST_TOKEN)
    r = client.get("/api/admin/extraction/disambiguation", headers=_admin_headers(),
                   params={"page_size": "999"})
    assert r.status_code == 400 and r.json()["code"] == 1002


# ---------------------------------------------------------------------------
# G10 事务与并发（复评 N2＋M10，2026-10-11）
# ---------------------------------------------------------------------------
class _FakeCursor:
    """记录 execute／executemany 调用序；fail_on 里的 SQL 子串命中即注入异常。"""

    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = tuple(fail_on)

    def execute(self, sql, args=None):
        self.calls.append(("execute", str(sql)[:40]))
        for marker in self.fail_on:
            if marker in str(sql):
                raise RuntimeError("injected failure: %s" % marker)

    def executemany(self, sql, seq):
        self.calls.append(("executemany", str(sql)[:40]))
        for marker in self.fail_on:
            if marker in str(sql):
                raise RuntimeError("injected failure: %s" % marker)

    def close(self):
        self.calls.append(("close", ""))


class _FakeConn:
    """假连接：begin／commit／rollback 调用序可断言（M10 的判据载体）。"""

    def __init__(self, fail_on=()):
        self.log = []
        self.cur = _FakeCursor(fail_on)

    def begin(self):
        self.log.append("begin")

    def commit(self):
        self.log.append("commit")

    def rollback(self):
        self.log.append("rollback")

    def cursor(self):
        return self.cur


_RECORD = {
    "question": {"session_id": "S-G10", "question_text": "测试问题",
                 "task_type": None, "gold_hop_depth": None,
                 "time_constraint": None, "ask_time": "2026-10-11T00:00:00"},
    "answer": {"answer_text": "【回答】测试", "graph_path": "", "model_name": "m",
               "prompt_version": "p", "is_graph_extended": 0,
               "create_time": "2026-10-11T00:00:00"},
    "answer_evidence": [{"chunk_id": 101, "doc_id": 1, "rank": 1,
                         "evidence_type": "回答来源"}],
}


def _run_persist(monkeypatch, fail_on=()):
    """在假连接上跑一次 _persist，返回 (连接调用序, 游标调用序, 异常或 None)。"""
    conn = _FakeConn(fail_on)
    monkeypatch.setattr(qa_service, "_fresh_conn", lambda: conn)
    monkeypatch.setattr(qa_service, "_evidence_rows", lambda answer_id: [])
    err = None
    try:
        qa_service._persist(_RECORD, 900, 900)
    except Exception as exc:                               # noqa: BLE001
        err = exc
    return conn.log, conn.cur.calls, err


def test_g10_persist_commits_on_success(monkeypatch):
    """① 正常路径：begin → 三段写 → executemany → commit，且无 rollback。"""
    log, cur_calls, err = _run_persist(monkeypatch)
    assert err is None
    assert log == ["begin", "commit"], "正常路径应 begin→commit、无 rollback：%s" % log
    assert len([c for c in cur_calls if c[0] == "execute"]) == 3
    assert any(c[0] == "executemany" for c in cur_calls)


def test_g10_persist_rolls_back_on_question_upsert_failure(monkeypatch):
    """② question upsert 失败 → rollback 且不 commit，异常上抛。"""
    log, _, err = _run_persist(monkeypatch, fail_on=("INSERT INTO question",))
    assert isinstance(err, RuntimeError)
    assert log == ["begin", "rollback"], "异常路径应 begin→rollback、无 commit：%s" % log


def test_g10_persist_rolls_back_on_evidence_failure(monkeypatch):
    """③ executemany（证据批量插）失败 → rollback 且不 commit。"""
    log, cur_calls, err = _run_persist(monkeypatch, fail_on=("INSERT INTO answer_evidence",))
    assert isinstance(err, RuntimeError)
    assert log == ["begin", "rollback"]
    # 失败点在 executemany：此前 question／answer／DELETE 三段 execute 已按序发生
    # （close 来自 cursor 上下文的 finally，判序时排除）
    real = [c for c in cur_calls if c[0] != "close"]
    assert sum(1 for c in real if c[0] == "execute") == 3
    assert real[-1][0] == "executemany"


def test_g10_persist_rolls_back_on_commit_failure(monkeypatch):
    """④ commit 自身抛错 → 仍进入 rollback 分支（异常不上抛为静默）。"""
    conn = _FakeConn()

    def _bad_commit():
        conn.log.append("commit")
        raise RuntimeError("commit 注入失败")

    monkeypatch.setattr(qa_service, "_fresh_conn", lambda: conn)
    monkeypatch.setattr(qa_service, "_evidence_rows", lambda answer_id: [])
    monkeypatch.setattr(conn, "commit", _bad_commit)
    try:
        qa_service._persist(_RECORD, 900, 900)
    except RuntimeError:
        pass                                               # commit 的异常经 except 分支上抛
    assert "rollback" in conn.log, "commit 失败也必须 rollback（begin/commit/rollback 序）"
    assert conn.log[0] == "begin"


def test_g10_ask_alloc_and_persist_share_lock_shape():
    """N2 红测：ask() 的 ID 分配与落库必须在同一 _DB_LOCK 锁段内（防并发同号互覆）。"""
    import inspect
    src = inspect.getsource(qa_service.ask)
    lock_pos = src.find("with _DB_LOCK:")
    alloc_pos = src.find("_next_ids(")
    persist_pos = src.find("items = _persist(")
    assert -1 < lock_pos < alloc_pos < persist_pos, \
        "ask() 中 _next_ids 与 _persist 必须位于同一 with _DB_LOCK 段内（N2）"
    assert src.count("_persist(") == 1, "锁段外不得再有独立 _persist 调用"


# ---------------------------------------------------------------------------
# G8 全响应体纪律：任何响应不出现 detail 键（抽全部用例的响应复核）
# ---------------------------------------------------------------------------
def test_g8_no_detail_key_in_any_response(client, monkeypatch):
    """把本组典型响应再过一遍机检：成功＝{data,meta}，错误＝{code,message}，无 detail。"""
    monkeypatch.setattr(qa_service, "get_answer", lambda answer_id: {"answer_id": answer_id})
    checks = [
        client.get("/api/qa/answers/40"),
        client.get("/api/qa/answers/40", headers={"X-Admin-Token": "x"}),
        client.post("/api/qa/ask", json={"session_id": "S"}),
        client.get("/api/history"),
        client.get("/api/graph/paths", params={"to_node": "N2"}),
        client.get("/api/market/quote", params={"codes": "abc"}),
        client.post("/api/admin/documents", json={"title": "t", "raw_text": "x"}),
    ]
    for r in checks:
        assert "detail" not in r.json(), "响应体出现 detail 键：%s" % r.text[:200]
        if r.status_code == 200:
            assert set(r.json().keys()) == {"data", "meta"}
        else:
            assert set(r.json().keys()) == {"code", "message"}
