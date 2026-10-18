# -*- coding: utf-8 -*-
r"""J 组 · 集成测试：读接口 → 真实图谱查询（内存后端）→ 响应整形（第 5 轮 9.2）。

与 G 组的区别
-------------
G 组把业务层全部换成替身，验证的是**路由契约**；本组只替换「后端选择」这一步：

    HTTP 请求 → FastAPI 路由 → GraphReader（真实实现）
              → 内存图谱后端（真实 `检索/graph_query.py`，读 04 的 nodes.csv／edges.csv）
              → 响应整形（真实 `_path_payload`／`_sort_paths`／`_entity_item`）→ JSON

即「接口 → 图谱 → 整形」整条读链**真跑**，但不连 Neo4j、不连 MySQL、不调模型、不联网。
数据集缺失时整组 `pytest.skip`（与既有 E 组对真实语料的处理一致）。

覆盖：
* `/api/graph/entities`：字段齐全（node_id／label／name／stock_code／properties）与空结果；
* `/api/graph/entities/{id}/neighbors`：内存后端的一跳、边字段齐全、不存在节点 → 2001；
* `/api/graph/paths`：真实多跳路径（节点 600519 → 事件 EVT-0288）、路径与边字段齐全、
  参数缺失 → 1002；
* `/api/graph/events`：真实事件列表分页与类型过滤。
"""

from __future__ import annotations

import contextlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

main_mod = _bootstrap.load_backend("main")
gs = _bootstrap.load_backend("services.graph_service")
graph_api = _bootstrap.load_backend("api.graph")
retrieval_cfg = _bootstrap.component_config("检索")


@pytest.fixture(scope="module")
def memory_backend():
    """真实内存图谱后端（只读 04 的图谱导出物）；缺失则整组跳过。"""
    nodes = getattr(retrieval_cfg, "NODES_CSV", "")
    edges = getattr(retrieval_cfg, "EDGES_CSV", "")
    if not (nodes and edges and os.path.isfile(nodes) and os.path.isfile(edges)):
        pytest.skip("图谱导出物不存在：%s / %s" % (nodes, edges))
    graph, backend = gs.open_backend("memory")
    assert backend == gs.MEMORY_BACKEND
    yield graph
    gs.close_backend(graph)


@pytest.fixture()
def client(memory_backend, monkeypatch):
    """用真实 GraphReader 替换 `api.graph.reader()`，并临时停用限流判定。"""
    real_reader = graph_api.GraphReader(memory_backend, gs.MEMORY_BACKEND)

    @contextlib.contextmanager
    def _reader():
        yield real_reader

    monkeypatch.setattr(graph_api, "reader", _reader)
    monkeypatch.setattr(main_mod.RateLimitMiddleware, "_over_limit",
                        lambda self, ip: False)
    with TestClient(main_mod.app) as c:
        yield c


def _meta(body):
    assert set(body.keys()) == {"data", "meta"}
    assert body["meta"]["dataset_version"] == "v2.1"
    assert body["meta"]["data_cutoff_time"]


# ---------------------------------------------------------------------------
# J1 实体检索：图谱 → 整形
# ---------------------------------------------------------------------------
def test_entities_reads_real_graph_and_shapes_fields(client):
    r = client.get("/api/graph/entities", params={"keyword": "贵州茅台"})
    assert r.status_code == 200
    body = r.json()
    _meta(body)
    data = body["data"]
    assert set(data.keys()) == {"total", "items", "page", "page_size"}
    assert data["total"] >= 1
    item = data["items"][0]
    assert set(item.keys()) == {"node_id", "label", "name", "stock_code", "properties"}
    assert item["node_id"] == "600519"
    assert item["label"] == "Company"
    assert item["name"] == "贵州茅台"
    assert item["stock_code"] == "600519"
    assert isinstance(item["properties"], dict)


def test_entities_unknown_keyword_is_http_200_empty(client):
    r = client.get("/api/graph/entities", params={"keyword": "不存在的公司XYZ"})
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0
    assert r.json()["data"]["items"] == []


def test_entities_invalid_type_is_1002_before_touching_graph(client):
    r = client.get("/api/graph/entities", params={"keyword": "茅台", "type": "NotALabel"})
    assert r.status_code == 400
    assert r.json()["code"] == 1002
    assert set(r.json().keys()) == {"code", "message"}


# ---------------------------------------------------------------------------
# J2 一跳邻居：真实 G1 → 边整形
# ---------------------------------------------------------------------------
def test_neighbors_returns_real_edges_with_complete_fields(client):
    r = client.get("/api/graph/entities/600519/neighbors")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"node", "nodes", "edges", "total"}
    assert data["node"]["node_id"] == "600519"
    assert data["total"] == len(data["edges"]) > 0
    edge = data["edges"][0]
    assert set(edge.keys()) == {"relation", "direction", "neighbor", "role",
                                "source_doc_id", "source_chunk_id", "confidence",
                                "evidence_doc_id", "neighbor_label"}
    assert edge["neighbor"] in {n["node_id"] for n in data["nodes"]}


def test_neighbors_unknown_node_is_2001(client):
    r = client.get("/api/graph/entities/GHOST-NODE/neighbors")
    assert r.status_code == 404
    assert r.json()["code"] == 2001
    assert set(r.json().keys()) == {"code", "message"}


# ---------------------------------------------------------------------------
# J3 多跳路径：真实 G7 → 路径整形（含批量节点简述）
# ---------------------------------------------------------------------------
def test_paths_returns_real_path_with_complete_fields(client):
    r = client.get("/api/graph/paths", params={
        "from_node": "600519", "to_node": "EVT-0288", "hop": "2"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"paths", "hop", "is_graph_extended",
                                "from_node", "to_node", "relation",
                                "start_time", "end_time"}
    assert data["hop"] == 2
    assert data["is_graph_extended"] is True
    assert data["paths"]
    path = data["paths"][0]
    assert set(path.keys()) == {"start", "end", "depth", "nodes", "edges", "node_ids"}
    assert path["start"] == "600519"
    assert path["end"] == "EVT-0288"
    assert [n["node_id"] for n in path["nodes"]] == path["node_ids"]
    for node in path["nodes"]:
        assert set(node.keys()) == {"node_id", "label", "name", "stock_code"}
    assert path["edges"]
    for edge in path["edges"]:
        assert edge["neighbor"] in path["node_ids"]


def test_paths_missing_target_and_relation_is_1002(client):
    r = client.get("/api/graph/paths", params={"from_node": "600519"})
    assert r.status_code == 400
    assert r.json()["code"] == 1002


def test_paths_unknown_target_is_http_200_empty_not_error(client):
    r = client.get("/api/graph/paths", params={
        "from_node": "600519", "to_node": "NO-SUCH-NODE", "hop": "2"})
    assert r.status_code == 200
    assert r.json()["data"]["paths"] == []
    assert r.json()["data"]["is_graph_extended"] is False


# ---------------------------------------------------------------------------
# J4 事件列表：真实 G3／G4 → 分页整形
# ---------------------------------------------------------------------------
def test_events_reads_real_events_and_paginates(client):
    r = client.get("/api/graph/events", params={"event_type": "业绩",
                                                "page": "1", "page_size": "3"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"total", "items", "page", "page_size"}
    assert data["total"] > 3
    assert data["page"] == 1 and data["page_size"] == 3
    assert len(data["items"]) == 3
    for item in data["items"]:
        assert set(item.keys()) == {"event_id", "node_id", "event_type",
                                    "event_name", "event_time",
                                    "description", "confidence"}
        assert item["event_type"] == "业绩"


def test_events_by_stock_code_is_http_200_even_when_empty(client):
    r = client.get("/api/graph/events", params={"stock_code": "999999"})
    assert r.status_code == 200
    assert r.json()["data"]["total"] == 0
