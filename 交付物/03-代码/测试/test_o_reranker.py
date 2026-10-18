# -*- coding: utf-8 -*-
"""O 组 · 可插拔 Rerank 接口（第 10 轮新增）—— 被测文件：`代码\\增强\\reranker.py`。

必须证明的两条性质：

1. **默认不改变结果**：`rerank_records(..., None)` 原样返回原列表；
   `rerank_record`／`rerank_result`／`RerankedRunner(..., None)` 原样返回**同一个对象**。
2. **注入自定义 reranker 会改变顺序**：倒序重排器只反转最终证据顺序，
   集合、计数与其他 trace 字段不变（第④步已冻结集合）。

实现说明：`pipeline.py` 是第 10 阶段 G4 登记的上游只读文件，本轮**未改动它**；
接口以包装器形式接在 pipeline 输出之后（见模块 docstring）。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402
from conftest import QUESTION  # noqa: E402

pipe = _bootstrap.load_module("检索", "pipeline.py")
reranker_mod = _bootstrap.load_module("增强", "reranker.py")
cfg = _bootstrap.component_config("检索")


def _records(*chunk_ids):
    return [{"chunk_id": int(cid), "similarity": 1.0 / (index + 1),
             "vector_rank": index + 1, "hit_by": ["vector"]}
            for index, cid in enumerate(chunk_ids)]


class _ReverseReranker:
    """带 `rerank()` 方法的自定义重排器（验证对象形态的接口）。"""

    def __init__(self):
        self.calls = []

    def rerank(self, question, records):
        self.calls.append((question, [rec["chunk_id"] for rec in records],
                           [dict(rec) for rec in records]))
        return list(reversed(records))


# ---------------------------------------------------------------------------
# 纯函数层
# ---------------------------------------------------------------------------
def test_default_reranker_returns_the_same_object_and_order():
    records = _records(11, 22, 33)
    out = reranker_mod.rerank_records(records, "问题", None)

    assert out is records, "默认 None 必须原样返回原列表（不复制、不排序）"
    assert [rec["chunk_id"] for rec in out] == [11, 22, 33]
    assert out[0] is records[0], "默认路径不得替换记录对象"


def test_injected_reranker_changes_order_but_not_fields_or_membership():
    records = _records(11, 22, 33)
    reranker = _ReverseReranker()

    out = reranker_mod.rerank_records(records, "贵州茅台", reranker)

    assert [rec["chunk_id"] for rec in out] == [33, 22, 11], "注入的 reranker 必须改变顺序"
    assert {rec["chunk_id"] for rec in out} == {11, 22, 33}, "只改顺序，不得增删记录"
    assert [rec["similarity"] for rec in out] == [1.0 / 3, 0.5, 1.0], "记录字段必须原样透传"
    assert reranker.calls[0][0] == "贵州茅台"
    assert reranker.calls[0][1] == [11, 22, 33]


def test_callable_reranker_is_supported():
    records = _records(1, 2, 3)
    out = reranker_mod.rerank_records(records, "q", lambda q, rows: rows[1:] + rows[:1])

    assert [rec["chunk_id"] for rec in out] == [2, 3, 1]


def test_reranker_must_return_a_permutation():
    records = _records(1, 2, 3)

    with pytest.raises(ValueError, match="条数"):
        reranker_mod.rerank_records(records, "q", lambda q, rows: rows[:2])
    with pytest.raises(ValueError, match="重复"):
        reranker_mod.rerank_records(records, "q", lambda q, rows: [rows[0]] * 3)
    with pytest.raises(ValueError, match="排列"):
        reranker_mod.rerank_records(
            records, "q", lambda q, rows: rows[:2] + [{"chunk_id": 999}])
    with pytest.raises(ValueError, match="None"):
        reranker_mod.rerank_records(records, "q", lambda q, rows: None)


# ---------------------------------------------------------------------------
# 包装器层：对真实 pipeline trace 的默认透明与注入重排
# ---------------------------------------------------------------------------
def _run(graph_case, searcher):
    switches = {"graph_depth": 2, "time_filter": True, "evidence_sort": False,
                "_group": "D"}
    return pipe.run_question(
        QUESTION, switches, graph_case.graph, searcher, graph_case.chunks,
        graph_case.documents, n=int(cfg.require_fixed("N")),
        k=int(cfg.require_fixed("K")),
        budget=int(cfg.require_fixed("context_token_budget")),
        g=int(cfg.require_fixed("graph_retention_share")),
        vector_cache={}, graph_cache={}, full_pool_cache={})


def test_rerank_record_default_is_the_same_object(synthetic_graph, fake_searcher):
    baseline = _run(synthetic_graph, fake_searcher())

    assert reranker_mod.rerank_record(
        baseline, QUESTION["question"], None, synthetic_graph.chunks) is baseline


def test_rerank_record_injected_changes_order_only(synthetic_graph, fake_searcher):
    baseline = _run(synthetic_graph, fake_searcher())
    reranker = _ReverseReranker()

    reranked = reranker_mod.rerank_record(
        baseline, QUESTION["question"], reranker, synthetic_graph.chunks)

    assert reranked is not baseline, "注入时必须返回新的 trace 对象，不改调用方对象"
    assert reranked["evidence"] == list(reversed(baseline["evidence"])), \
        "注入倒序重排器后最终证据顺序应反转"
    assert set(reranked["evidence"]) == set(baseline["evidence"]), "集合必须不变"
    assert reranked["evidence_size"] == baseline["evidence_size"]
    assert reranked["segments"]["⑤ 最终证据集合"]["order"] == reranked["evidence"]
    assert baseline["segments"]["⑤ 最终证据集合"]["order"] == baseline["evidence"], \
        "必须复制外层与⑤段，不得原地改写基线 trace"
    assert reranked.get("rerank_applied") is True
    assert "rerank_applied" not in baseline
    assert reranker.calls[0][1] == baseline["evidence"], \
        "重排器收到的顺序应是第⑤步的呈现顺序"
    assert all("content" in row for row in reranker.calls[0][2]), \
        "传入 chunks 时应给重排器附上正文"


class _StubRunner:
    """只验证 `RerankedRunner` 包装语义的最小 PipelineRunner 替身。"""

    def __init__(self, result):
        self.result = result
        self.chunks = {}
        self.calls = []

    def run(self, questions, switches, n, k, budget, g):
        self.calls.append((questions, switches, n, k, budget, g))
        return self.result


def _stub_result():
    return {"records": [{"qid": "T-01", "evidence": [11, 22, 33],
                         "final_evidence_chunk_ids": [11, 22, 33],
                         "evidence_size": 3,
                         "segments": {"⑤ 最终证据集合": {"order": [11, 22, 33],
                                                    "presentation_rule": "D 组"}}}]}


def test_reranked_runner_default_returns_original_result():
    result = _stub_result()
    runner = reranker_mod.RerankedRunner(_StubRunner(result), reranker=None)

    assert runner.run([], {}, 20, 10, 3600, 2) is result


def test_reranked_runner_injected_changes_evidence_order():
    result = _stub_result()
    stub = _StubRunner(result)
    questions = [{"qid": "T-01", "question": "测试问题"}]
    runner = reranker_mod.RerankedRunner(stub, reranker=_ReverseReranker())

    out = runner.run(questions, {"switches": {}}, 20, 10, 3600, 2)

    assert stub.calls and stub.calls[0][0] == questions, "包装器必须把参数原样传给 PipelineRunner"
    assert out["records"][0]["evidence"] == [33, 22, 11]
    assert result["records"][0]["evidence"] == [11, 22, 33], "原结果不得被原地修改"
