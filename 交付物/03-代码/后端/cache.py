# -*- coding: utf-8 -*-
"""代码\\后端\\cache.py —— 只读热点接口的**进程内 TTL＋LRU 缓存**（第 6 轮）。

设计口径
--------
* **不引入 Redis／外部服务**：缓存只活在当前后端进程里，进程退出即消失；
  多 worker 部署时各 worker 各有一份（本项目本机固定单进程，见 `run.py`）。
* **可关闭**：`config.CACHE["enabled"]`（`config.local.json` 的 `cache_enabled`，或环境变量
  `ASHARE_CACHE_ENABLED=0`）。关闭后 `get()` 恒为未命中、`set()` 不落数据，接口行为与
  未接缓存完全一致（只多一次字典开关判断）。
* **TTL＋LRU**：`ttl_seconds` 到期即失效（惰性删除，读取时判断）；`max_entries` 满后按
  最近最少使用淘汰。
* **不改变响应内容**：缓存的是接口的 `data` 区块（不是整个信封）；`errors.ok()` 每次
  重新生成 `{data, meta}`，`meta` 仍取当前配置。读写均做深拷贝，调用方改不到缓存里的对象。
* **只缓存成功结果**：加载函数抛异常时异常原样上抛且不落缓存（400／404 等错误不缓存）。
* **统计**：`hits／misses／hit_rate／sets／evictions／expired／size` 随
  `GET /api/health` 的 `cache` 区块返回（不新增路由）。

线程安全：所有读写都在同一把 `RLock` 内完成；加载函数也在锁内执行，天然避免
缓存击穿（同一 key 的并发请求只会真正加载一次）。
"""

from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

import config

_MISS = object()


class TTLCache:
    """线程安全的 TTL＋LRU 缓存；`clock` 可注入，便于单测直接拨表。"""

    def __init__(self, name: str, ttl_seconds: float, max_entries: int,
                 enabled: bool = True, clock: Callable[[], float] = time.monotonic):
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds 必须为正数")
        if max_entries <= 0:
            raise ValueError("max_entries 必须为正数")
        self.name = name
        self.ttl_seconds = float(ttl_seconds)
        self.max_entries = int(max_entries)
        self.enabled = bool(enabled)
        self._clock = clock
        self._lock = threading.RLock()
        self._data: OrderedDict[Any, tuple[float, Any]] = OrderedDict()
        self._hits = 0
        self._misses = 0
        self._sets = 0
        self._evictions = 0
        self._expired = 0

    # ------------------------------------------------------------ 读写
    def get(self, key: Any) -> Any:
        """命中返回值（深拷贝）；未命中／已过期／缓存关闭返回 `_MISS`。"""
        with self._lock:
            if not self.enabled:
                self._misses += 1
                return _MISS
            item = self._data.get(key)
            if item is None:
                self._misses += 1
                return _MISS
            expires_at, value = item
            if expires_at <= self._clock():
                del self._data[key]
                self._expired += 1
                self._misses += 1
                return _MISS
            self._data.move_to_end(key)                # LRU：命中即移到队尾
            self._hits += 1
            return copy.deepcopy(value)

    def set(self, key: Any, value: Any) -> bool:
        """写入（深拷贝）；缓存关闭时返回 False 且不保存。"""
        with self._lock:
            if not self.enabled:
                return False
            self._data[key] = (self._clock() + self.ttl_seconds, copy.deepcopy(value))
            self._data.move_to_end(key)
            self._sets += 1
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)
                self._evictions += 1
            return True

    def get_or_load(self, key: Any, loader: Callable[[], Any]) -> Any:
        """命中直接返回；未命中则调用 `loader()` 并缓存其结果。

        异常不吞、不缓存。加载在锁内执行：同一 key 的并发请求只加载一次。
        """
        with self._lock:                              # 与 get／set 同一把可重入锁
            hit = self.get(key)
            if hit is not _MISS:
                return hit
            value = loader()
            if value is not None:
                self.set(key, value)
            return copy.deepcopy(value)

    def invalidate(self, key: Any) -> bool:
        """删除单个 key；返回是否原本存在。"""
        with self._lock:
            return self._data.pop(key, None) is not None

    def clear(self) -> None:
        """清空数据（统计计数**保留**，便于观察「清空后重建」）。"""
        with self._lock:
            self._data.clear()

    def reset(self) -> None:
        """清空数据**并**把统计计数归零（测试隔离用；接口行为不受影响）。"""
        with self._lock:
            self._data.clear()
            self._hits = self._misses = self._sets = 0
            self._evictions = self._expired = 0

    # ------------------------------------------------------------ 观测
    def snapshot(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "name": self.name,
                "enabled": self.enabled,
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
                "size": len(self._data),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
                "sets": self._sets,
                "evictions": self._evictions,
                "expired": self._expired,
            }


_CFG = config.CACHE
CONFIG_META_CACHE = TTLCache("config_meta", _CFG["ttl_seconds"], _CFG["max_entries"],
                             enabled=_CFG["enabled"])
ENTITY_DETAIL_CACHE = TTLCache("entity_detail", _CFG["ttl_seconds"], _CFG["max_entries"],
                               enabled=_CFG["enabled"])
_CACHES = (CONFIG_META_CACHE, ENTITY_DETAIL_CACHE)


def snapshot() -> dict:
    """所有缓存的名细＋汇总（挂到 `/api/health` 的 `cache` 区块）。"""
    items = {c.name: c.snapshot() for c in _CACHES}
    hits = sum(c.snapshot()["hits"] for c in _CACHES)
    misses = sum(c.snapshot()["misses"] for c in _CACHES)
    total = hits + misses
    return {
        "enabled": bool(_CFG["enabled"]),
        "ttl_seconds": _CFG["ttl_seconds"],
        "max_entries": _CFG["max_entries"],
        "hits": hits,
        "misses": misses,
        "hit_rate": round(hits / total, 4) if total else 0.0,
        "caches": items,
    }


def clear_all() -> None:
    """清空所有缓存（测试／运维用；响应内容不变，仅让下一次请求重新加载）。"""
    for cache in _CACHES:
        cache.clear()


def reset_all() -> None:
    """清空数据并归零统计（仅测试隔离用）。"""
    for cache in _CACHES:
        cache.reset()
