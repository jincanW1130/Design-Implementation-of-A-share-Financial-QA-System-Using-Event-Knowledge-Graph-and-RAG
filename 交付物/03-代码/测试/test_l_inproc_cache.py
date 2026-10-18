# -*- coding: utf-8 -*-
"""L 组 · 进程内 TTL／LRU 缓存（第 6 轮）。

覆盖两件事：

1. `缓存\\cache.py` 的单元行为：命中／未命中、TTL 过期、LRU 淘汰、关闭开关、
   `get_or_load` 只加载一次、深拷贝隔离、统计口径；
2. 两个只读热点接口的集成行为：`/api/config/meta` 与 `/api/graph/entities/{id}`
   在缓存开启时**只真正查询一次**、响应内容与未缓存时一致；缓存关闭时每次都查询；
   节点不存在（404）不缓存；TTL 到期后重新查询。

离线纪律：TestClient 走 ASGI 内存传输；图谱侧用 `api.graph.reader()` 的假读者，
不连 Neo4j／MySQL；`/api/config/meta` 只读数据集元信息 JSON。
"""

from __future__ import annotations

import contextlib
import os
import sys

import pytest
from fastapi.testclient import TestClient

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

cache_mod = _bootstrap.load_backend("cache")
config_mod = _bootstrap.load_backend("config")
main_mod = _bootstrap.load_backend("main")
qa_service = _bootstrap.load_backend("services.qa_service")
graph_api = _bootstrap.load_backend("api.graph")


# ---------------------------------------------------------------------------
# 假图谱读者（只暴露实体详情用到的三件事）
# ---------------------------------------------------------------------------
class CountingReader:
    """记录 `_raw_node()` 调用次数；边集为空，避免碰 MySQL。"""

    def __init__(self):
        self.graph = _CountingGraph()
        self.backend = "memory"
        self.raw_calls = 0

    def _raw_node(self, node_id):
        self.raw_calls += 1
        nid = str(node_id)
        if nid == "GHOST":
            return None
        return {"node_id": nid, "label": "Company", "name": "甲公司",
                "stock_code": "000001", "aliases": "甲公司|JIA"}


class _CountingGraph:
    def __init__(self):
        self.adj = {}

    def g1_one_hop(self, node_id):
        return {"code": "OK", "results": []}


@pytest.fixture(autouse=True)
def _fresh_cache():
    """每个用例前后清空缓存并归零统计，避免用例之间互相影响。"""
    cache_mod.reset_all()
    yield
    cache_mod.reset_all()


@pytest.fixture()
def client(monkeypatch):
    """TestClient：停用限流判定（与 G 组同一做法），不影响被测接口。"""
    with TestClient(main_mod.app) as c:
        monkeypatch.setattr(main_mod.RateLimitMiddleware, "_over_limit",
                            lambda self, ip: False)
        yield c


@pytest.fixture()
def reader_factory(monkeypatch):
    """把 `api.graph.reader()` 换成可观察调用次数的假读者。"""
    state = {"reader": CountingReader()}

    @contextlib.contextmanager
    def _ctx():
        yield state["reader"]

    monkeypatch.setattr(graph_api, "reader", _ctx)
    return state


# ---------------------------------------------------------------------------
# 1. TTLCache 单元测试
# ---------------------------------------------------------------------------
def _new_cache(ttl=10, max_entries=8, enabled=True):
    clock = {"now": 1000.0}
    c = cache_mod.TTLCache("unit", ttl, max_entries, enabled=enabled,
                           clock=lambda: clock["now"])
    return c, clock


def test_l1_ttl_cache_hit_miss_and_stats():
    c, _ = _new_cache()
    assert c.get("a") is cache_mod._MISS
    c.set("a", {"v": 1})
    assert c.get("a") == {"v": 1}
    snap = c.snapshot()
    assert snap["hits"] == 1 and snap["misses"] == 1 and snap["sets"] == 1
    assert snap["hit_rate"] == 0.5
    assert snap["size"] == 1


def test_l1_ttl_cache_expires():
    c, clock = _new_cache(ttl=10)
    c.set("a", 1)
    clock["now"] += 9.9
    assert c.get("a") == 1
    clock["now"] += 0.2                                  # 超过 TTL
    assert c.get("a") is cache_mod._MISS
    assert c.snapshot()["expired"] == 1


def test_l1_ttl_cache_lru_eviction():
    c, _ = _new_cache(max_entries=2)
    c.set("a", 1)
    c.set("b", 2)
    assert c.get("a") == 1                                # a 变为最近使用
    c.set("c", 3)                                         # 淘汰最久未用的 b
    assert c.get("b") is cache_mod._MISS
    assert c.get("a") == 1 and c.get("c") == 3
    assert c.snapshot()["evictions"] == 1


def test_l1_ttl_cache_disabled():
    c, _ = _new_cache(enabled=False)
    assert c.set("a", 1) is False
    assert c.get("a") is cache_mod._MISS
    assert c.snapshot()["enabled"] is False
    assert c.snapshot()["size"] == 0


def test_l1_get_or_load_runs_loader_once():
    c, _ = _new_cache()
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return {"v": calls["n"]}

    assert c.get_or_load("k", loader) == {"v": 1}
    assert c.get_or_load("k", loader) == {"v": 1}
    assert calls["n"] == 1
    assert c.snapshot()["hits"] == 1


def test_l1_get_or_load_does_not_cache_exceptions():
    c, _ = _new_cache()
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        raise RuntimeError("boom")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            c.get_or_load("k", loader)
    assert calls["n"] == 2
    assert c.get("k") is cache_mod._MISS


def test_l1_cached_value_is_deepcopied():
    c, _ = _new_cache()
    original = {"items": [1]}
    c.set("k", original)
    original["items"].append(2)                           # 改写入参不影响缓存
    got = c.get("k")
    got["items"].append(3)                                # 改读出值不影响缓存
    assert c.get("k") == {"items": [1]}


# ---------------------------------------------------------------------------
# 2. /api/config/meta 集成测试
# ---------------------------------------------------------------------------
def test_l2_config_meta_cached_once(client, monkeypatch):
    calls = {"n": 0}
    real = qa_service.config_meta

    def counting():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(qa_service, "config_meta", counting)
    first = client.get("/api/config/meta")
    second = client.get("/api/config/meta")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()                  # 响应内容逐键一致
    assert calls["n"] == 1
    snap = cache_mod.CONFIG_META_CACHE.snapshot()
    assert snap["hits"] == 1 and snap["misses"] == 1


def test_l2_config_meta_cache_can_be_disabled(client, monkeypatch):
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return {"v": calls["n"]}

    monkeypatch.setattr(qa_service, "config_meta", counting)
    monkeypatch.setattr(cache_mod.CONFIG_META_CACHE, "enabled", False)
    client.get("/api/config/meta")
    client.get("/api/config/meta")
    assert calls["n"] == 2


def test_l2_config_meta_ttl_expiry_rereads(client, monkeypatch):
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return {"v": calls["n"]}

    monkeypatch.setattr(qa_service, "config_meta", counting)
    clock = {"now": 1000.0}
    monkeypatch.setattr(cache_mod.CONFIG_META_CACHE, "_clock", lambda: clock["now"])
    client.get("/api/config/meta")
    client.get("/api/config/meta")
    assert calls["n"] == 1
    clock["now"] += cache_mod.CONFIG_META_CACHE.ttl_seconds + 1
    r = client.get("/api/config/meta")
    assert calls["n"] == 2
    assert r.json()["data"] == {"v": 2}


# ---------------------------------------------------------------------------
# 3. /api/graph/entities/{id} 集成测试
# ---------------------------------------------------------------------------
def test_l3_entity_detail_cached_once(client, reader_factory):
    rd = reader_factory["reader"]
    first = client.get("/api/graph/entities/N1")
    second = client.get("/api/graph/entities/N1")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert rd.raw_calls == 1
    snap = cache_mod.ENTITY_DETAIL_CACHE.snapshot()
    assert snap["hits"] == 1 and snap["misses"] == 1


def test_l3_entity_detail_not_found_not_cached(client, reader_factory):
    rd = reader_factory["reader"]
    for _ in range(2):
        r = client.get("/api/graph/entities/GHOST")
        assert r.status_code == 404 and r.json()["code"] == 2001
    assert rd.raw_calls == 2                              # 错误不落缓存
    assert cache_mod.ENTITY_DETAIL_CACHE.snapshot()["size"] == 0


def test_l3_entity_detail_cache_can_be_disabled(client, reader_factory, monkeypatch):
    rd = reader_factory["reader"]
    monkeypatch.setattr(cache_mod.ENTITY_DETAIL_CACHE, "enabled", False)
    client.get("/api/graph/entities/N1")
    client.get("/api/graph/entities/N1")
    assert rd.raw_calls == 2


def test_l3_entity_detail_ttl_expiry_rereads(client, reader_factory, monkeypatch):
    rd = reader_factory["reader"]
    clock = {"now": 1000.0}
    monkeypatch.setattr(cache_mod.ENTITY_DETAIL_CACHE, "_clock", lambda: clock["now"])
    client.get("/api/graph/entities/N1")
    client.get("/api/graph/entities/N1")
    assert rd.raw_calls == 1
    clock["now"] += cache_mod.ENTITY_DETAIL_CACHE.ttl_seconds + 1
    client.get("/api/graph/entities/N1")
    assert rd.raw_calls == 2


def test_l3_cache_invalidation_clear(client, reader_factory):
    rd = reader_factory["reader"]
    client.get("/api/graph/entities/N1")
    assert rd.raw_calls == 1
    cache_mod.ENTITY_DETAIL_CACHE.clear()                 # 显式失效
    client.get("/api/graph/entities/N1")
    assert rd.raw_calls == 2


def test_l3_health_reports_cache_stats(client, reader_factory):
    client.get("/api/graph/entities/N1")
    client.get("/api/graph/entities/N1")
    body = client.get("/api/health").json()
    assert "cache" in body
    detail = body["cache"]["caches"]["entity_detail"]
    assert detail["hits"] >= 1
    assert body["cache"]["enabled"] == bool(config_mod.CACHE["enabled"])
