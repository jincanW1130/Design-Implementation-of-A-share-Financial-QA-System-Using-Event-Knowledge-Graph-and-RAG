# -*- coding: utf-8 -*-
"""R 组 · 检索侧进程内指标与日志采样（第三轮 8.2；第八轮 8.2 增量）。

只测计数口径，不启动真实服务、不连 MySQL／Neo4j：
* 默认快照含 `retrieval` 零值键、`evidence_avg`、`kb_hit_rate` 与 `llm` 零值键；
* 非复用链路：vector_searches／graph_queries／evidence_total／empty_results 累加；
* 复用链路：只累加 reused_answers，不重复计一次向量检索；
* 路由指标含 `avg_ms`（作者原文「平均」）；
* LLM 尝试按 attempts 聚合失败率（失败／空正文／重试）；
* 访问日志采样率解析与 0／1 两端行为；
* 并发写入不丢计数（锁内累加）。
"""

from __future__ import annotations

import logging
import os
import sys
import threading

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

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
        "kb_hit_rate": 0.0,
    }
    assert snap["llm"] == {
        "calls": 0,
        "failures": 0,
        "failure_rate": 0.0,
        "total_seconds": 0.0,
        "avg_seconds": 0.0,
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
    # 知识库命中率：3 次检索中 2 次有可引用证据。
    assert snap["kb_hit_rate"] == 0.6667


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


def test_route_metrics_include_average():
    """作者原文「平均」：路由指标同时给出 avg_ms 与 P50／P95／P99。"""
    reg = obs.MetricsRegistry()
    for duration in (10.0, 20.0, 30.0):
        reg.record_request("GET", "/api/x", 200, duration)
    item = reg.snapshot()["routes"]["GET /api/x"]
    assert item["avg_ms"] == 20.0
    assert item["p50_ms"] == 20.0
    assert item["p95_ms"] == 30.0
    assert item["p99_ms"] == 30.0


def test_llm_attempt_metrics_count_failures_and_retries():
    """LLM 失败率：请求失败与空正文都计失败；重试按实际尝试逐次计数。"""
    reg = obs.MetricsRegistry()
    reg.record_llm_attempts([
        {"ok": True, "empty_body": False, "seconds": 1.0},
        {"ok": False, "empty_body": None, "seconds": 0.5},
        {"ok": True, "empty_body": True, "seconds": 0.7},
        "not-a-dict",
    ])
    snap = reg.snapshot()["llm"]
    assert snap["calls"] == 3
    assert snap["failures"] == 2
    assert snap["failure_rate"] == 0.6667
    assert snap["total_seconds"] == 2.2
    assert snap["avg_seconds"] == 0.733
    # 空 attempts 不改变计数。
    reg.record_llm_attempts([])
    reg.record_llm_attempts(None)
    assert reg.snapshot()["llm"]["calls"] == 3


def test_sample_rate_parsing(monkeypatch):
    """采样率：缺省 1.0；0／1 边界；越界夹紧；非法值回落 1.0。"""
    cases = [(None, 1.0), ("0", 0.0), ("0.25", 0.25), ("2", 1.0),
             ("-1", 0.0), ("abc", 1.0)]
    for raw, expected in cases:
        if raw is None:
            monkeypatch.delenv("ASHARE_ACCESS_LOG_SAMPLE_RATE", raising=False)
        else:
            monkeypatch.setenv("ASHARE_ACCESS_LOG_SAMPLE_RATE", raw)
        assert obs._sample_rate() == expected


def _sample_client() -> TestClient:
    app = Starlette(routes=[Route("/api/x", lambda request: PlainTextResponse("ok"))])
    app.add_middleware(obs.AccessLogMiddleware)
    return TestClient(app)


def test_access_log_sampling_suppresses_and_emits(monkeypatch, caplog):
    """采样 0 不写 access 行；采样 1 写且字段齐全（不含请求体／问题原文）。"""
    monkeypatch.setattr(obs, "ACCESS_LOG_ENABLED", True)
    caplog.set_level(logging.INFO, logger="ashare_qa.backend")

    monkeypatch.setattr(obs, "ACCESS_LOG_SAMPLE_RATE", 0.0)
    _sample_client().get("/api/x")
    assert "access method=" not in caplog.text

    caplog.clear()
    monkeypatch.setattr(obs, "ACCESS_LOG_SAMPLE_RATE", 1.0)
    _sample_client().get("/api/x")
    assert "access method=GET path=/api/x status=200" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "route=/api/x" in caplog.text
