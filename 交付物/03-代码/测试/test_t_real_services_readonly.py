# -*- coding: utf-8 -*-
r"""T 组 · 真实 MySQL／Neo4j **只读**集成测试（第四轮欠账）。

与 J 组的分工
-------------
J 组用真实内存图后端跑「接口 → 图谱 → 整形」，但**不连 MySQL、不连 Neo4j**；
本组只测服务层 DAO／Neo4j 后端的真实行为：

* `db.py`：真实 MySQL 8.4 上的连接、探针、版本、行数、查询助手、
  游标提交／回滚路径与自检；
* `services/graph_service.py`：真实 Neo4j 5.26 上 G1～G7、标识解析、
  批量证据块，并与内存后端对拍关键字段。

三条纪律
--------
1. **没有服务就 UNRUN（pytest.skip），不伪装通过**：MySQL 探针失败或 Neo4j
   `verify_connectivity()` 失败时整组跳过，原因写进 skip message。
2. **只读**：只执行 `SELECT`／`MATCH` 与只读事务；MySQL 会话在夹具里显式设为
   `SET SESSION TRANSACTION READ ONLY` 并断言生效，任何误写的语句会被服务端拒绝。
3. **不写凑数断言**：断言的都是服务真实返回值之间的结构关系（排序、分区、
   集合差、批量与单个一致、内存／Neo4j 两端对拍），不靠硬编码业务读数。
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

db = _bootstrap.load_backend("db")
gs = _bootstrap.load_backend("services.graph_service")
backend_cfg = _bootstrap.component_config("后端")
retrieval_cfg = _bootstrap.component_config("检索")


# ---------------------------------------------------------------------------
# 夹具：服务不可达 → 整组 skip
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def real_db():
    """真实 MySQL 单例连接；会话设为 **READ ONLY** 后交给用例。"""
    probe = db.probe()
    if not probe.get("ok"):
        pytest.skip("UNRUN：MySQL 不可达（%s）" % probe.get("detail", ""))
    db.execute("SET SESSION TRANSACTION READ ONLY")
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module")
def neo4j_graph():
    """真实 Neo4j 后端（`bolt://127.0.0.1:7687`）；连不上则整组 skip。"""
    try:
        graph, name = gs.open_backend("neo4j")
    except SystemExit as exc:                              # verify_connectivity 失败
        pytest.skip("UNRUN：Neo4j 不可达（%s）" % str(exc).splitlines()[0])
    assert name == gs.NEO4J_BACKEND
    try:
        yield graph
    finally:
        gs.close_backend(graph)


@pytest.fixture(scope="module")
def memory_graph():
    """真实内存图后端（读 04 的图谱导出物），用于与 Neo4j 对拍；缺失则跳过。"""
    nodes = getattr(retrieval_cfg, "NODES_CSV", "")
    edges = getattr(retrieval_cfg, "EDGES_CSV", "")
    if not (nodes and edges and os.path.isfile(nodes) and os.path.isfile(edges)):
        pytest.skip("UNRUN：图谱导出物不存在（%s / %s）" % (nodes, edges))
    graph, backend = gs.open_backend("memory")
    assert backend == gs.MEMORY_BACKEND
    try:
        yield graph
    finally:
        gs.close_backend(graph)


# ---------------------------------------------------------------------------
# MySQL：连接、探针、元数据
# ---------------------------------------------------------------------------
def test_mysql_probe_version_and_database(real_db):
    probe = real_db.probe()
    assert probe["ok"] is True
    assert probe["detail"].startswith("8.")                # MySQL 8.x
    assert real_db.ping() is True
    assert real_db.server_version() == probe["detail"]
    assert real_db.database_exists() is True


def test_mysql_session_is_actually_read_only(real_db):
    assert real_db.scalar("SELECT @@session.transaction_read_only") == 1


def test_mysql_describe_target_never_leaks_password(real_db):
    target = real_db.describe_target()
    assert ":%s/" % backend_cfg.db_params()["port"] in target
    password = backend_cfg.db_params().get("password") or ""
    if password:
        assert password not in target


def test_mysql_table_counts_cover_the_six_tables(real_db):
    counts = real_db.table_counts()
    assert list(counts) == list(db.config.TABLES)
    assert counts["document"] > 0
    assert counts["document_chunk"] > counts["document"]  # 每个文档至少一块
    assert counts["question"] > 0 and counts["answer"] > 0
    assert counts["answer_evidence"] >= counts["answer"]


def test_mysql_query_helpers_return_rows_and_none(real_db):
    rows = real_db.query(
        "SELECT doc_id, title FROM document ORDER BY doc_id LIMIT 5")
    assert len(rows) == 5
    assert set(rows[0]) == {"doc_id", "title"}
    assert real_db.query_one(
        "SELECT doc_id, title FROM document ORDER BY doc_id LIMIT 1") == rows[0]
    assert real_db.query_one("SELECT doc_id FROM document WHERE 1=0") is None
    assert real_db.scalar("SELECT 42 AS answer") == 42
    assert real_db.scalar("SELECT doc_id FROM document WHERE 1=0") is None


def test_mysql_transaction_commit_and_rollback_paths(real_db):
    # commit=True 的提交路径：只读事务，提交不改变任何数据
    with real_db.cursor(commit=True) as cur:
        cur.execute("SELECT 1 AS n")
        assert cur.fetchone()["n"] == 1
    # 显式 begin → 只读查询 → rollback
    conn = real_db.begin()
    try:
        assert real_db.scalar("SELECT 2 AS n", conn=conn) == 2
    finally:
        real_db.rollback(conn)
    # commit=True 的异常回滚路径
    with pytest.raises(RuntimeError):
        with real_db.cursor(commit=True) as cur:
            cur.execute("SELECT 3 AS n")
            raise RuntimeError("只读事务主动回滚")
    # commit()／rollback() 的无参路径
    real_db.commit()
    real_db.rollback()


def test_mysql_execute_helpers_work_for_readonly_statements(real_db):
    assert real_db.execute("SELECT %s AS n", (7,)) >= 1
    assert real_db.executemany("SELECT %s AS n", [(1,), (2,)]) >= 1


def test_mysql_selftest_runs_green(real_db):
    assert real_db.selftest() == 0


# ---------------------------------------------------------------------------
# Neo4j：连接与标识解析
# ---------------------------------------------------------------------------
def test_neo4j_server_info(neo4j_graph):
    info = neo4j_graph.server_info()
    assert info["uri"].startswith("bolt://127.0.0.1")
    assert info["kernel"] == "Neo4j Kernel"
    assert info["version"].startswith("5.")
    assert info["edition"] in {"community", "enterprise"}


def test_resolve_node_by_id_name_and_failures(neo4j_graph):
    by_id = neo4j_graph.resolve_node("600519")
    assert by_id["code"] == gs.RC_OK
    assert by_id["matched_by"] == "node_id"
    assert by_id["node_ids"] == ["600519"]

    by_name = neo4j_graph.resolve_node("贵州茅台")
    assert by_name["code"] == gs.RC_OK
    assert by_name["matched_by"] == "name"
    assert "600519" in by_name["node_ids"]

    assert neo4j_graph.resolve_node("   ")["code"] == gs.RC_INVALID_INPUT
    assert neo4j_graph.resolve_node("不存在的公司XYZ")["code"] == gs.RC_NOT_FOUND


def test_resolve_company_rejects_non_company(neo4j_graph):
    ok = neo4j_graph.resolve_company("600519")
    assert ok["code"] == gs.RC_OK
    assert ok["node_ids"] == ["600519"]

    bad = neo4j_graph.resolve_company("EVT-0001")
    assert bad["code"] == gs.RC_INVALID_INPUT
    assert "不是 Company" in bad["detail"]


# ---------------------------------------------------------------------------
# Neo4j：G1～G7
# ---------------------------------------------------------------------------
def test_g1_one_hop_is_sorted_and_complete(neo4j_graph):
    env = neo4j_graph.g1_one_hop("600519")
    assert env["code"] == gs.RC_OK
    assert env["count"] == len(env["results"]) > 0
    seq = [(it["relation"], it["direction"], it["neighbor"], it["edge_id"])
           for it in env["results"]]
    assert seq == sorted(seq)
    for item in env["results"]:
        assert set(item) == {"edge_id", "relation", "direction", "neighbor",
                             "role", "evidence", "neighbor_node"}
        assert item["neighbor_node"]["node_id"] == item["neighbor"]
        if item["relation"] == gs.EVIDENCED_BY:
            assert item["evidence"] is None
        else:
            assert set(item["evidence"]) == set(gs.EVIDENCE_ATTRS)


def test_last_cypher_keeps_evidence_and_can_clear(neo4j_graph):
    neo4j_graph.last_cypher()                             # 先清掉之前的记录
    neo4j_graph.g1_one_hop("600519")
    executed = neo4j_graph.last_cypher()
    assert executed and all("MATCH" in statement for statement in executed)
    assert neo4j_graph.last_cypher() == []


def test_g2_two_hop_paths_are_consistent(neo4j_graph):
    env = neo4j_graph.g2_two_hop("600519")
    assert env["code"] == gs.RC_OK
    assert env["count"] == len(env["results"]) > 0
    assert env["one_hop_count"] == sum(1 for p in env["results"] if p["depth"] == 1)
    for path in env["results"]:
        assert path["depth"] == len(path["relations"]) == len(path["nodes"]) - 1
        assert 1 <= path["depth"] <= 2
        assert path["start"] == path["nodes"][0]
        assert path["end"] == path["nodes"][-1]
        assert [r["neighbor"] for r in path["relations"]] == path["nodes"][1:]


def test_g3_events_by_type_filters_and_sorts(neo4j_graph):
    env = neo4j_graph.g3_events_by_type("业绩")
    assert env["code"] == gs.RC_OK
    assert env["count"] > 0
    assert all(e["event_type"] == "业绩" for e in env["results"])
    seq = [(e["event_time"], e["node_id"]) for e in env["results"]]
    assert seq == sorted(seq)
    assert neo4j_graph.g3_events_by_type("不存在的类型")["code"] == gs.RC_INVALID_INPUT


def test_g4_company_events_are_unique_and_sorted(neo4j_graph):
    env = neo4j_graph.g4_company_events("000001")
    assert env["code"] == gs.RC_OK
    ids = [e["node_id"] for e in env["results"]]
    assert ids and len(ids) == len(set(ids))
    seq = [(e["event_time"], e["node_id"]) for e in env["results"]]
    assert seq == sorted(seq)


def test_g5_event_evidence_rules(neo4j_graph):
    env = neo4j_graph.g5_event_evidence("EVT-0001")
    assert env["code"] == gs.RC_OK
    assert env["count"] == len(env["results"]) > 0
    for item in env["results"]:
        assert item["relation"] != gs.EVIDENCED_BY
        assert item["evidence"]["source_chunk_id"]
    assert env["chunk_ids"] == sorted(
        {it["evidence"]["source_chunk_id"] for it in env["results"]},
        key=lambda x: (len(x), x))                         # 块号 1～3 位与数值混合排序
    for ref in env["document_refs"]:
        assert set(ref) == {"relation", "direction", "document_id",
                            "edge_id", "document"}
        assert ref["relation"] == gs.EVIDENCED_BY
    assert neo4j_graph.g5_event_evidence("GHOST-EVT")["code"] == gs.RC_NOT_FOUND
    assert neo4j_graph.g5_event_evidence("600519")["code"] == gs.RC_INVALID_INPUT


def test_g6_time_filter_partitions_ids_and_chunks(neo4j_graph):
    lo, hi = "2026-06-26", "2026-09-22"
    events = neo4j_graph.g4_company_events("000001")["results"]
    ids = [e["node_id"] for e in events]
    env = neo4j_graph.g6_time_filter(ids, lo, hi)

    assert env["code"] == gs.RC_OK
    passed = set(env["passed_ids"])
    removed_null = set(env["removed_null_ids"])
    removed_range = set(env["removed_out_of_range_ids"])
    assert passed | removed_null | removed_range == set(ids)
    assert not (passed & removed_null)
    assert not (passed & removed_range)
    assert not (removed_null & removed_range)

    event_time = {e["node_id"]: e["event_time"] for e in events}
    assert all(lo <= event_time[eid] <= hi for eid in passed)
    assert all(not event_time[eid] for eid in removed_null)
    assert all(event_time[eid] < lo or event_time[eid] > hi for eid in removed_range)

    survived = set(env["chunk_ids_survived"])
    removed = set(env["chunk_ids_removed"])
    assert set(env["chunk_id_diff"]) == removed - survived
    assert set(env["chunk_id_diff_reverse"]) == survived - removed
    assert set(env["chunk_ids_in_scope"]) == survived | removed

    # null_policy=keep：空时间事件进入通过集合，不再报“空值剔除”
    keep = neo4j_graph.g6_time_filter(ids, lo, hi, null_policy="keep")
    assert keep["removed_null_ids"] == []
    assert set(keep["passed_ids"]) == passed | removed_null

    assert neo4j_graph.g6_time_filter(ids, hi, lo)["code"] == gs.RC_INVALID_INPUT
    assert neo4j_graph.g6_time_filter(ids, lo, hi, null_policy="skip")["code"] \
        == gs.RC_INVALID_INPUT
    assert neo4j_graph.g6_time_filter(["EVT-NOPE"], lo, hi)["code"] \
        == gs.RC_INVALID_INPUT


def test_g7_paths_and_payload(neo4j_graph):
    env = neo4j_graph.g7_paths("600519", "EVT-0288", max_depth=2)
    assert env["code"] == gs.RC_OK
    assert env["count"] == len(env["results"]) > 0
    assert len(env["graph_path"]) == env["count"]
    for path in env["results"]:
        assert path["start"] == "600519"
        assert path["end"] == "EVT-0288"
        assert path["depth"] == len(path["relations"])
    for payload in env["graph_path"]:
        assert set(payload) == {"start", "end", "depth", "nodes", "relations"}
    assert neo4j_graph.g7_paths("600519", "EVT-0288", max_depth=3)["code"] \
        == gs.RC_INVALID_INPUT
    assert neo4j_graph.g7_paths("600519", "NO-SUCH-NODE")["code"] == gs.RC_NOT_FOUND


def test_event_chunk_ids_batch_matches_single(neo4j_graph):
    ids = [e["node_id"]
           for e in neo4j_graph.g4_company_events("000001")["results"]][:3]
    batch = neo4j_graph.event_chunk_ids_batch(ids)
    assert set(batch) == set(ids)
    for eid in ids:
        assert batch[eid] == neo4j_graph.event_chunk_ids(eid)
    assert neo4j_graph.event_chunk_ids_batch([]) == {}


# ---------------------------------------------------------------------------
# 双后端对拍（内存图 vs Neo4j，关键字段逐项一致）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("interface,method,arg", [
    ("G1", "g1_one_hop", "600519"),
    ("G3", "g3_events_by_type", "业绩"),
    ("G5", "g5_event_evidence", "EVT-0001"),
])
def test_neo4j_matches_memory_backend(neo4j_graph, memory_graph,
                                      interface, method, arg):
    env_neo = getattr(neo4j_graph, method)(arg)
    env_mem = getattr(memory_graph, method)(arg)
    assert gs._fingerprint(interface, env_neo) == gs._fingerprint(interface, env_mem)
