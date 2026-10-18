# -*- coding: utf-8 -*-
"""工具\\实验_只读接口缓存.py —— 只读热点接口缓存的 HTTP 实测。

第 6 轮覆盖 `GET /api/config/meta` 与 `GET /api/graph/entities/000001`；
**第四轮扩展**再覆盖 `GET /api/graph/events?page_size=20` 与 `GET /api/evidence/30`。
每个端点各发 N 次请求，统计 p50／p95／p99、响应体哈希（应全程一致），并从
`/api/health` 读取缓存命中率；两次运行（缓存关／开）会逐端点比对响应体 SHA-256。

**对比方式**：先用 `ASHARE_CACHE_ENABLED=0` 启动后端跑一次 `--label before`，
再用默认配置（缓存开启）重启后端跑一次 `--label after`；两次结果合并进同一个 JSON。
本脚本只读接口，不写业务数据。

用法（仓库根目录）::

    python 工具\\实验_只读接口缓存.py --label before
    python 工具\\实验_只读接口缓存.py --label after
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import statistics
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
DEFAULT_OUT = os.path.join(ROOT, "交付物/05-系统实现/前后端系统集成/_工作底稿",
                           "只读接口缓存_第四轮.json")
PATHS = {
    "config_meta": "/api/config/meta",
    "entity_detail": "/api/graph/entities/000001",
    # 第四轮新增：缓存候选（只读热点）
    "graph_events": "/api/graph/events?page_size=20",
    "evidence_detail": "/api/evidence/30",
}

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _request(conn, path):
    t0 = time.perf_counter()
    conn.request("GET", path, headers={"Accept": "application/json"})
    resp = conn.getresponse()
    body = resp.read()
    ms = (time.perf_counter() - t0) * 1000.0
    if resp.status != 200:
        raise RuntimeError("%s -> HTTP %s: %s" % (path, resp.status, body[:200]))
    return ms, body


def _pct(times, p):
    return round(times[min(len(times) - 1, int(len(times) * p))], 3)


def bench(conn, path, n, warmup):
    for _ in range(warmup):
        _request(conn, path)
    times, digests = [], set()
    for _ in range(n):
        ms, body = _request(conn, path)
        times.append(ms)
        digests.add(hashlib.sha256(body).hexdigest())
    times.sort()
    return {
        "requests": n,
        "warmup": warmup,
        "p50_ms": _pct(times, 0.50),
        "p95_ms": _pct(times, 0.95),
        "p99_ms": _pct(times, 0.99),
        "mean_ms": round(statistics.fmean(times), 3),
        "min_ms": round(times[0], 3),
        "max_ms": round(times[-1], 3),
        "distinct_response_bodies": len(digests),
        "response_sha256": sorted(digests)[0] if len(digests) == 1 else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="只读热点接口缓存 HTTP 实测")
    ap.add_argument("--label", required=True, help="before / after 等标签")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--requests", type=int, default=500)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    conn = http.client.HTTPConnection(args.host, args.port, timeout=30)
    try:
        first = {}
        # 首次请求（未命中／含连接懒加载），单列记录
        for key, path in PATHS.items():
            first[key], _ = _request(conn, path)
        results = {key: bench(conn, path, args.requests, args.warmup)
                   for key, path in PATHS.items()}
        _, health_body = _request(conn, "/api/health")
        health = json.loads(health_body.decode("utf-8"))
    finally:
        conn.close()

    payload = {}
    if os.path.exists(args.out):
        with open(args.out, "r", encoding="utf-8") as f:
            payload = json.load(f)
    payload.setdefault("runs", {})
    payload["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    payload["endpoints"] = PATHS
    payload["runs"][args.label] = {
        "first_request_ms": {k: round(v, 3) for k, v in first.items()},
        "latency": results,
        "health_cache": health.get("cache"),
        "health_status": health.get("status"),
    }

    # 缓存关／开两次运行的响应体逐端点比对（来自各自 N 次请求的唯一 SHA-256）
    runs = payload["runs"]
    if {"before", "after"} <= set(runs):
        comparison = {}
        for key in PATHS:
            before = ((runs["before"].get("latency") or {}).get(key) or {})
            after = ((runs["after"].get("latency") or {}).get(key) or {})
            b_hash, a_hash = before.get("response_sha256"), after.get("response_sha256")
            comparison[key] = {
                "before_sha256": b_hash,
                "after_sha256": a_hash,
                "identical": bool(b_hash and a_hash and b_hash == a_hash),
                "before_distinct_bodies": before.get("distinct_response_bodies"),
                "after_distinct_bodies": after.get("distinct_response_bodies"),
            }
        payload["cache_on_off_identical"] = comparison

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    run = payload["runs"][args.label]
    cache = run["health_cache"] or {}
    print("[%s] cache.enabled=%s hit_rate=%s hits=%s misses=%s"
          % (args.label, cache.get("enabled"), cache.get("hit_rate"),
             cache.get("hits"), cache.get("misses")))
    print("  首请求：%s" % run["first_request_ms"])
    for key, r in results.items():
        print("  %-16s n=%d p50=%.3f p95=%.3f p99=%.3f ms；响应体种类=%d"
              % (key, r["requests"], r["p50_ms"], r["p95_ms"], r["p99_ms"],
                 r["distinct_response_bodies"]))
    if "cache_on_off_identical" in payload:
        print("缓存关／开响应体逐端点比对：")
        for key, item in payload["cache_on_off_identical"].items():
            print("  %-16s identical=%s" % (key, item["identical"]))
    print("结论 JSON：%s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
