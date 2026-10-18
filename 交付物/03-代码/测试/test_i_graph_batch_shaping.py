# -*- coding: utf-8 -*-
r"""I 组 · 图谱批量取块与路径整形（第 5 轮 9.1 补强，**只增不改**）。

被测对象（第 1 轮性能优化的核心改动，此前只有端到端读数、没有函数级用例）：

* `交付物/03-代码\后端\services\graph_service.py`
    - `Neo4jGraphQuery.event_chunk_ids_batch()`：一条 Cypher 批量取块，语义与逐个
      `event_chunk_ids()` 逐项一致（排除 `EVIDENCED_BY`、忽略空 `source_chunk_id`、
      每个事件的集合按 `(长度, 值)` 升序）；
    - `Neo4jGraphQuery.g6_time_filter()`：时间过滤后的「存活／移除」与块级差集；
    - `Neo4jGraphQuery.graph_path_payload()`：路径项整形；
    - `BACKEND_FACTORIES` / `register_backend()` / `resolve_backend_name()`。
* `交付物/03-代码\后端\api\graph.py`
    - `_path_payload()`：用 `brief_map` 批量取节点简述，**不再逐节点 `brief()`**（消 N+1）；
    - `_sort_paths()` / `_dedup_paths()`：确定性与去重。

**不连 Neo4j**：`Neo4jGraphQuery` 用 `_run` 的进程内替身构造（不触发驱动），
`_path_payload` 用只记录调用次数的假 reader。离线、零外部依赖。
"""

from __future__ import annotations

import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

gs = _bootstrap.load_backend("services.graph_service")
graph_api = _bootstrap.load_backend("api.graph")


# ---------------------------------------------------------------------------
# 探针后端：不发 Cypher，只按查询特征回确定性行
# ---------------------------------------------------------------------------
EVENT_TIME = {"E1": "2026-03-01", "E2": "", "E3": "2024-01-01"}
EVENT_CHUNKS = {"E1": ["102", "101", "101", "9"], "E2": ["105"], "E3": ["103"]}


class ProbeNeo4j(gs.Neo4jGraphQuery):
    """`Neo4jGraphQuery` 的进程内替身：不建驱动、不连库，`_run` 按查询特征回行。"""

    def __init__(self):
        self._driver = None
        self._session = None
        self._last_cypher = []
        self.queries = []

    def _run(self, query: str, **params):
        self.queries.append((query, params))
        ids = [str(x) for x in (params.get("ids") or [])]

        if "labels(n)[0] AS label" in query and "$id" in query:
            return [{"label": "Event"}]

        if "AS event_id" in query:                        # _BATCH_EVENT_CHUNK_IDS
            rows = []
            for eid in ids:
                for cid in EVENT_CHUNKS.get(eid, []):
                    rows.append({"event_id": eid, "source_chunk_id": cid})
                rows.append({"event_id": eid, "source_chunk_id": ""})
                rows.append({"event_id": eid, "source_chunk_id": None})
            rows.append({"event_id": "NOT-REQUESTED", "source_chunk_id": "777"})
            return rows

        if "AS counterpart" in query:                      # G5
            eid = str(params.get("id"))
            rows = []
            for idx, cid in enumerate(EVENT_CHUNKS.get(eid, [])):
                rows.append({
                    "relation": "PARTICIPATES_IN", "edge_id": "e%d" % idx,
                    "direction": "in", "neighbor": "N%d" % idx, "role": "主体",
                    "source_doc_id": "11", "source_chunk_id": cid,
                    "confidence": "0.9",
                    "counterpart": {"node_id": "N%d" % idx, "label": "Company",
                                    "name": "公司%d" % idx},
                })
            rows.append({"relation": "EVIDENCED_BY", "edge_id": "ev",
                         "direction": "out", "neighbor": "DOC1", "role": "",
                         "source_doc_id": None, "source_chunk_id": None,
                         "confidence": None, "counterpart": {"node_id": "DOC1"}})
            return rows

        if query == gs.NEO4J_CYPHER["G6"]:                 # G6
            # 与真实 Cypher 一致：只回实际存在的节点；未知 id 让调用方走 1002 分支
            return [{"ev": {"node_id": eid, "event_time": EVENT_TIME[eid],
                            "event_id": eid, "event_type": "业绩"}}
                    for eid in ids if eid in EVENT_TIME]

        raise AssertionError("未预期的查询：%s" % query[:80])


@pytest.fixture()
def probe():
    return ProbeNeo4j()


# ==========================================================================
# I1 · event_chunk_ids_batch
# ==========================================================================
def test_batch_empty_input_makes_no_query(probe):
    assert probe.event_chunk_ids_batch([]) == {}
    assert probe.queries == []


def test_batch_dedups_sorts_and_drops_blank_chunk_ids(probe):
    got = probe.event_chunk_ids_batch(["E1", "E2"])
    assert got["E1"] == ["9", "101", "102"]          # (长度, 值) 升序 ＋ 去重
    assert got["E2"] == ["105"]                      # 空串／None 被忽略
    assert len(probe.queries) == 1                   # 批量：一条 Cypher


def test_batch_keeps_unknown_event_ids_as_empty_lists(probe):
    got = probe.event_chunk_ids_batch(["MISSING"])
    assert got == {"MISSING": []}


def test_batch_ignores_rows_for_events_not_requested(probe):
    got = probe.event_chunk_ids_batch(["E1"])
    assert "NOT-REQUESTED" not in got
    assert all(cid != "777" for cid in got["E1"])


def test_batch_passes_the_evidenced_relation_name_to_cypher(probe):
    probe.event_chunk_ids_batch(["E1"])
    query, params = probe.queries[0]
    assert "type(r) <> $evidenced" in query
    assert params["evidenced"] == gs.EVIDENCED_BY


def test_batch_is_semantically_identical_to_single_event_chunk_ids(probe):
    """批量版与逐个 `event_chunk_ids()`（走 G5）逐事件相等——这是性能优化不改语义的证据。"""
    ids = ["E1", "E2", "E3"]
    batch = probe.event_chunk_ids_batch(ids)
    single = {eid: probe.event_chunk_ids(eid) for eid in ids}
    assert batch == single


# ==========================================================================
# I2 · G6 时间过滤与块级差集
# ==========================================================================
def test_g6_exclude_policy_splits_passed_null_and_out_of_range(probe):
    env = probe.g6_time_filter(["E1", "E2", "E3"], "2025-01-01", "2026-12-31",
                               null_policy="exclude")
    assert env["code"] == gs.RC_OK
    assert env["passed_ids"] == ["E1"]
    assert env["removed_null_ids"] == ["E2"]
    assert env["removed_out_of_range_ids"] == ["E3"]
    assert env["removed_ids"] == ["E2", "E3"]


def test_g6_chunk_diff_is_set_difference_not_concatenation(probe):
    env = probe.g6_time_filter(["E1", "E2", "E3"], "2025-01-01", "2026-12-31",
                               null_policy="exclude")
    assert env["chunk_ids_survived"] == ["9", "101", "102"]
    assert env["chunk_ids_removed"] == ["103", "105"]
    assert env["chunk_id_diff"] == ["103", "105"]       # 移除集 − 存活集
    assert env["chunk_id_diff_reverse"] == ["9", "101", "102"]   # 存活集 − 移除集
    assert env["chunk_ids_in_scope"] == ["9", "101", "102", "103", "105"]


def test_g6_keep_policy_keeps_null_event_time(probe):
    """空 `event_time` 在 `keep` 策略下按存活处理；合法策略只有 exclude／keep。"""
    env = probe.g6_time_filter(["E1", "E2", "E3"], "2025-01-01", "2026-12-31",
                               null_policy="keep")
    assert env["passed_ids"] == ["E1", "E2"]
    assert env["removed_ids"] == ["E3"]
    assert env["removed_null_ids"] == []


def test_g6_all_removed_is_empty_code_not_an_error(probe):
    env = probe.g6_time_filter(["E3"], "2020-01-01", "2020-12-31", null_policy="exclude")
    assert env["code"] == gs.RC_EMPTY
    assert env["passed_ids"] == []


def test_g6_rejects_unknown_policy_before_querying(probe):
    env = probe.g6_time_filter(["E1"], "2020-01-01", "2030-12-31", null_policy="skip")
    assert env["code"] == gs.RC_INVALID_INPUT
    assert probe.queries == []


def test_g6_rejects_reversed_window(probe):
    env = probe.g6_time_filter(["E1"], "2026-12-31", "2025-01-01")
    assert env["code"] == gs.RC_INVALID_INPUT
    assert probe.queries == []


def test_g6_rejects_unknown_event_id(probe):
    env = probe.g6_time_filter(["NOPE"], "2020-01-01", "2030-12-31")
    assert env["code"] == gs.RC_INVALID_INPUT
    assert "NOPE" in env.get("detail", "")


# ==========================================================================
# I3 · 路径整形（api.graph._path_payload）
# ==========================================================================
class FakeReader:
    """只记录 `brief()` 调用次数的假 reader（路径整形不应逐节点调用它）。"""

    def __init__(self):
        self.brief_calls = []

    def brief(self, node_id):
        self.brief_calls.append(str(node_id))
        return {"node_id": str(node_id), "label": "Company",
                "name": "NAME-%s" % node_id, "stock_code": ""}


def _path():
    return {
        "start": "A", "end": "B", "depth": 2, "nodes": ["A", "X", "B"],
        "relations": [
            {"relation": "RELATED_TO", "direction": "out", "neighbor": "X",
             "role": "涉及方", "edge_id": 0,
             "evidence": {"source_doc_id": "11", "source_chunk_id": "101",
                          "confidence": "0.9"}},
            {"relation": "EVIDENCED_BY", "direction": "out", "neighbor": "B",
             "role": "", "edge_id": 1, "evidence": None},
        ],
    }


BRIEF_MAP = {
    "A": {"node_id": "A", "label": "Company", "name": "甲", "stock_code": "000001"},
    "X": {"node_id": "X", "label": "Company", "name": "乙", "stock_code": "000002"},
    "B": {"node_id": "B", "label": "Document", "name": "", "stock_code": ""},
}


def test_path_payload_uses_brief_map_without_any_brief_call():
    reader = FakeReader()
    out = graph_api._path_payload(reader, _path(), brief_map=BRIEF_MAP)
    assert reader.brief_calls == []                      # 批量：零次逐节点查询
    assert [n["node_id"] for n in out["nodes"]] == ["A", "X", "B"]
    assert out["node_ids"] == ["A", "X", "B"]
    assert out["start"] == "A" and out["end"] == "B" and out["depth"] == 2


def test_path_payload_falls_back_to_brief_only_for_missing_nodes():
    reader = FakeReader()
    partial = dict(BRIEF_MAP)
    partial.pop("X")
    out = graph_api._path_payload(reader, _path(), brief_map=partial)
    assert reader.brief_calls == ["X"]
    assert out["nodes"][1]["node_id"] == "X"


def test_path_payload_edge_fields_and_numeric_normalization():
    out = graph_api._path_payload(FakeReader(), _path(), brief_map=BRIEF_MAP)
    first, second = out["edges"]
    assert first["relation"] == "RELATED_TO"
    assert first["direction"] == "out" and first["neighbor"] == "X"
    assert first["source_doc_id"] == 11                 # 数字串 → int
    assert first["source_chunk_id"] == 101
    assert first["confidence"] == 0.9                   # 数字串 → float
    assert first["evidence_doc_id"] is None
    assert first["neighbor_label"] == "Company"         # 标签取自 brief_map
    assert second["relation"] == "EVIDENCED_BY"
    assert second["evidence_doc_id"] == "B"
    assert second["source_doc_id"] is None


def test_path_payload_with_evidence_attaches_metadata_and_marks_missing():
    doc_meta = {11: {"title": "公告", "source": "cninfo",
                     "publish_time": "2026-03-02", "url": "https://example.invalid/1"}}
    chunk_meta = {101: 3}
    out = graph_api._path_payload(FakeReader(), _path(), with_evidence=True,
                                  doc_meta=doc_meta, chunk_meta=chunk_meta,
                                  brief_map=BRIEF_MAP)
    ev0 = out["edges"][0]["evidence"]
    assert ev0 == {"doc_id": 11, "chunk_id": 101, "title": "公告", "source": "cninfo",
                   "publish_time": "2026-03-02", "url": "https://example.invalid/1",
                   "chunk_index": 3, "missing": False}
    assert out["edges"][1]["evidence"] is None
    assert out["edges"][1]["note"] == graph_api.NO_EVIDENCE_NOTE


def test_path_payload_with_evidence_marks_missing_document_honestly():
    out = graph_api._path_payload(FakeReader(), _path(), with_evidence=True,
                                  doc_meta={}, chunk_meta={}, brief_map=BRIEF_MAP)
    ev = out["edges"][0]["evidence"]
    assert ev["missing"] is True
    assert ev["title"] is None and ev["chunk_index"] is None


def test_path_payload_does_not_mutate_the_internal_path():
    path = _path()
    snapshot = copy.deepcopy(path)
    graph_api._path_payload(FakeReader(), path, brief_map=BRIEF_MAP)
    assert path == snapshot


# ==========================================================================
# I4 · 排序 / 去重 / graph_path_payload
# ==========================================================================
def test_sort_paths_is_depth_then_node_sequence():
    paths = [
        {"depth": 2, "node_ids": ["A", "B"], "edges": []},
        {"depth": 1, "node_ids": ["B"], "edges": []},
        {"depth": 2, "node_ids": ["A", "A2"], "edges": []},
    ]
    got = graph_api._sort_paths(paths)
    assert [p["depth"] for p in got] == [1, 2, 2]
    assert got[1]["node_ids"] == ["A", "A2"]
    assert got[2]["node_ids"] == ["A", "B"]


def test_dedup_paths_uses_node_and_edge_sequence():
    first = {"nodes": ["A", "B"], "relations": [{"edge_id": 0}]}
    same = {"nodes": ["A", "B"], "relations": [{"edge_id": 0}]}
    other = {"nodes": ["A", "B"], "relations": [{"edge_id": 1}]}
    assert graph_api._dedup_paths([first, same, other]) == [first, other]


def test_graph_path_payload_copies_evidence_instead_of_aliasing():
    path = {"start": "A", "end": "B", "depth": 1, "nodes": ["A", "B"],
            "relations": [{"relation": "RELATED_TO", "direction": "out",
                           "neighbor": "B", "role": "涉及方",
                           "evidence": {"source_doc_id": "11"}}]}
    out = gs.Neo4jGraphQuery.graph_path_payload(None, path)
    assert out["relations"][0]["evidence"] == {"source_doc_id": "11"}
    out["relations"][0]["evidence"]["source_doc_id"] = "99"
    assert path["relations"][0]["evidence"]["source_doc_id"] == "11"


# ==========================================================================
# I5 · 后端注册表
# ==========================================================================
def test_builtin_backends_are_registered():
    assert gs.MEMORY_BACKEND in gs.BACKEND_FACTORIES
    assert gs.NEO4J_BACKEND in gs.BACKEND_FACTORIES


def test_resolve_backend_name_is_case_and_whitespace_insensitive():
    assert gs.resolve_backend_name("  MEMORY ") == gs.MEMORY_BACKEND
    assert gs.resolve_backend_name("Neo4J") == gs.NEO4J_BACKEND


def test_resolve_backend_name_unknown_exits():
    with pytest.raises(SystemExit):
        gs.resolve_backend_name("not-a-backend")


@pytest.mark.parametrize("name,factory", [("", lambda: None), ("x", None)])
def test_register_backend_rejects_blank_name_or_non_callable(name, factory):
    with pytest.raises(ValueError):
        gs.register_backend(name, factory)
