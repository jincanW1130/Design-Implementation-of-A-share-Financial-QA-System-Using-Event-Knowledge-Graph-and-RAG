# -*- coding: utf-8 -*-
"""U 组 · 关键词召回（工程增强）—— 后端服务与只读接口。

被测文件
--------
* `交付物/03-代码/后端/services/hybrid_search.py`（惰性 BM25 索引／片段／降级）
* `交付物/03-代码/后端/api/search.py`（`GET /api/search/keywords`）
* `交付物/03-代码/后端/services/qa_service.py` 的空结果分支（`related_chunks`）

口径
----
关键词召回属于**工程增强**，不在论文 A～E 实验口径内；本组测试只钉住：
① 题库里的精确问题能命中预期 chunk（BM25 分数 > 0）；
② 空查询返回空列表、不触发构建；
③ `k` 越界／非法参数与缺失 `q` 的错误码（1002／1001／1003）；
④ 构建失败时降级为空结果（接口不 500）；
⑤ `POST /api/qa/ask` 空结果时附 `related_chunks`（≤3 条）与 `engineering_enhancement=true`。

离线纪律：TestClient 走 ASGI 内存传输；索引只读本地 `chunks.jsonl`；不联网、不调模型。
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
qa_service = _bootstrap.load_backend("services.qa_service")
hybrid_search = _bootstrap.load_backend("services.hybrid_search")

PE01 = ("长城汽车《2023年股票期权激励计划》首次授予股票期权第二个行权期的"
        "行权期有效期是什么时间段？")


@pytest.fixture()
def client(monkeypatch):
    """TestClient（内存传输）＋ 停用限流判定（与 G 组同一做法）。"""
    with TestClient(main_mod.app) as c:
        monkeypatch.setattr(main_mod.RateLimitMiddleware, "_over_limit",
                            lambda self, ip: False)
        yield c


# ---------------------------------------------------------------------------
# 1. 服务层：命中、空查询、降级
# ---------------------------------------------------------------------------
def test_service_hits_expected_chunk_with_positive_score():
    rows = hybrid_search.search(PE01, 5)

    assert rows, "题库中的精确问题应有关键词命中"
    ids = [row["chunk_id"] for row in rows]
    assert 1001001 in ids, "PE-01 的 gold chunk（1001001）应进入 Top-5：%s" % ids
    assert all(row["score"] > 0 for row in rows), "命中项的 BM25 分数必须为正"
    first = rows[0]
    assert set(first) == {"chunk_id", "doc_id", "title", "snippet", "score"}
    assert isinstance(first["title"], str) and first["title"]
    assert 0 < len(first["snippet"]) <= 201, "snippet 应截断到约 200 字（含省略号）"
    assert hybrid_search.index_ready() is True


def test_service_empty_question_returns_empty_without_building():
    hybrid_search.reset()

    assert hybrid_search.search("", 5) == []
    assert hybrid_search.search("   ", 5) == []
    assert hybrid_search.index_ready() is False, "空查询不应触发惰性构建"


def test_service_build_failure_degrades_to_unavailable(monkeypatch):
    """构建失败只降级为不可用：返回 []、不抛异常、状态带 error。"""
    hybrid_search.reset()

    def _boom():
        raise RuntimeError("模拟索引构建失败")

    monkeypatch.setattr(hybrid_search, "_load_lexical_module", _boom)
    try:
        assert hybrid_search.search(PE01, 3) == []
        status = hybrid_search.status()
        assert status["index_ready"] is False
        assert "模拟索引构建失败" in (status["error"] or "")
        # 构建只尝试一次：第二次调用直接返回 []，不再重复抛错／重试
        assert hybrid_search.search(PE01, 3) == []
    finally:
        hybrid_search.reset()


# ---------------------------------------------------------------------------
# 2. 接口层：成功信封与参数错误码
# ---------------------------------------------------------------------------
def test_api_success_envelope_and_payload(client):
    r = client.get("/api/search/keywords", params={"q": PE01, "k": 3})

    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"data", "meta"}
    data = body["data"]
    assert set(data) == {"items", "total", "took_ms", "index_ready"}
    assert data["total"] == len(data["items"]) == 3
    assert data["index_ready"] is True
    assert data["took_ms"] >= 0
    assert body["meta"]["dataset_version"] == "v2.1"
    assert body["meta"]["data_cutoff_time"]


def test_api_default_k_is_five(client):
    r = client.get("/api/search/keywords", params={"q": "长城汽车 股票期权"})

    assert r.status_code == 200
    data = r.json()["data"]
    assert 0 < data["total"] <= 5


def test_api_missing_q_is_1003(client):
    r = client.get("/api/search/keywords", params={"k": 5})

    assert r.status_code == 400
    assert r.json()["code"] == 1003
    assert set(r.json()) == {"code", "message"}


def test_api_blank_or_control_question_is_1001(client):
    for q in ("", "   ", "abc\x00def"):
        r = client.get("/api/search/keywords", params={"q": q})
        assert r.status_code == 400, q
        assert r.json()["code"] == 1001, q


@pytest.mark.parametrize("k", ["0", "21", "-1", "abc"])
def test_api_invalid_k_is_1002(client, k):
    r = client.get("/api/search/keywords", params={"q": "长城汽车", "k": k})

    assert r.status_code == 400
    assert r.json()["code"] == 1002
    assert set(r.json()) == {"code", "message"}


def test_api_empty_result_is_http_200_with_empty_list(client, monkeypatch):
    """2002 语义：没有关键词命中时是 HTTP 200＋空列表，不是错误。"""
    monkeypatch.setattr(hybrid_search, "search", lambda question, k: [])

    r = client.get("/api/search/keywords", params={"q": "完全不存在的词元组合"})

    assert r.status_code == 200
    data = r.json()["data"]
    assert data["items"] == [] and data["total"] == 0


# ---------------------------------------------------------------------------
# 3. 空结果附 related_chunks（qa_service）
# ---------------------------------------------------------------------------
def test_ask_empty_payload_carries_related_chunks(monkeypatch):
    calls = []

    def _related(question, k):
        calls.append((question, k))
        return [{"chunk_id": 1001001, "doc_id": 1001, "title": "示例标题",
                 "snippet": "示例摘要", "score": 1.5}]

    monkeypatch.setattr(qa_service, "_run_chain",
                        lambda *a, **k: {"empty": True, "empty_reason": "no_citable_evidence",
                                         "out_dir": "-", "elapsed_seconds": 0.1, "now": "-"})
    monkeypatch.setattr(qa_service.hybrid_search, "search", _related)

    payload = qa_service.ask("一个没有可引用证据的问题", "S-U-TEST-0001")

    assert payload["empty"] is True
    assert payload["engineering_enhancement"] is True
    assert payload["related_chunks"] == [{
        "chunk_id": 1001001, "doc_id": 1001, "title": "示例标题",
        "snippet": "示例摘要", "score": 1.5}]
    assert calls == [("一个没有可引用证据的问题", 3)], \
        "空结果只取 3 条关键词相关原文"


def test_ask_empty_payload_keeps_empty_related_when_unavailable(monkeypatch):
    monkeypatch.setattr(qa_service, "_run_chain",
                        lambda *a, **k: {"empty": True, "empty_reason": "no_citable_evidence",
                                         "out_dir": "-", "elapsed_seconds": 0.1, "now": "-"})
    monkeypatch.setattr(qa_service.hybrid_search, "search", lambda question, k: [])

    payload = qa_service.ask("另一个空结果问题", "S-U-TEST-0002")

    assert payload["related_chunks"] == [], "关键词不可用／无命中时保持空列表"
    assert "未检索到可引用的证据" in payload["notice"], "原文案不变"
