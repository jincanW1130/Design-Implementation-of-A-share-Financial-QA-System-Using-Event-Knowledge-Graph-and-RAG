# -*- coding: utf-8 -*-
"""R 组 · 检索侧进程内指标（第三轮 8.2）。

只测 `observability.MetricsRegistry` 的计数口径，不启动服务、不连 MySQL／Neo4j：
* 默认快照含 `retrieval` 五个零值键与 `evidence_avg`；
* 非复用链路：vector_searches／graph_queries／evidence_total／empty_results 累加；
* 复用链路：只累加 reused_answers，不重复计一次向量检索；
* 并发写入不丢计数（锁内累加）。
"""

from __future__ import annotations

import os
import sys
import threading

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

obs = _bootstrap.load_backend("observability")


def test_retrieval_defaults_are_zero():
    snap = obs.MetricsRegistry().snapshot()
    assert snap["retrieval"] == {
        "vector_searches": 0,
        "graph_queries": 0,
        "evidence_total": 0,
        "empty_results": 0,
        "reused_answers": 0,
        "evidence_avg": 0.0,
    }


def test_retrieval_counts_normal_and_empty_runs():
    reg = obs.MetricsRegistry()
    reg.record_qa_retrieval(evidence_count=10, graph_used=True)
    reg.record_qa_retrieval(evidence_count=8, graph_used=False)
    reg.record_qa_retrieval(evidence_count=0, graph_used=False, empty=True)
    snap = reg.snapshot()["retrieval"]
    assert snap["vector_searches"] == 3
    assert snap["graph_queries"] == 1
    assert snap["evidence_total"] == 18
    assert snap["empty_results"] == 1
    assert snap["reused_answers"] == 0
    assert snap["evidence_avg"] == 6.0


def test_retrieval_reuse_does_not_count_as_new_search():
    reg = obs.MetricsRegistry()
    reg.record_qa_retrieval(reused=True)
    reg.record_qa_retrieval(reused=True)
    reg.record_qa_retrieval(evidence_count=10, graph_used=True)
    snap = reg.snapshot()["retrieval"]
    assert snap["reused_answers"] == 2
    assert snap["vector_searches"] == 1
    assert snap["graph_queries"] == 1
    assert snap["evidence_total"] == 10


def test_retrieval_thread_safe():
    reg = obs.MetricsRegistry()
    threads = []
    for _ in range(8):
        t = threading.Thread(target=lambda: [
            reg.record_qa_retrieval(evidence_count=1, graph_used=True) for _ in range(250)])
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    snap = reg.snapshot()["retrieval"]
    assert snap["vector_searches"] == 2000
    assert snap["graph_queries"] == 2000
    assert snap["evidence_total"] == 2000
