# -*- coding: utf-8 -*-
r"""压测.py —— 轻量 HTTP 压测（第 5 轮 9.4）。

只依赖标准库（urllib ＋ threading），不改产品代码、不写数据库。

默认参数刻意很小：**20 个请求 / 并发 5 / 端点 `/api/health`**。原因是后端有
「60 次／60 秒」的滑动窗口限流（`/api/health` 豁免），而问答接口每条要 10 s 以上。
要压问答接口时请显式指定，并在启动后端时临时放宽 `ASHARE_RATE_LIMIT_MAX`，
压测完恢复默认。

用法::

    python 工具\压测.py                                  # 20 请求、并发 5、/api/health
    python 工具\压测.py --requests 60 --concurrency 10   # 更大一点
    python 工具\压测.py --endpoint /api/graph/entities?keyword=茅台
    python 工具\压测.py --json 交付物\06-实验与评测\系统指标\压测读数.json

输出：总请求数、成功/失败、QPS、P50/P95/P99、最小/最大/平均延迟。
失败＝超时、连接错误或 HTTP 状态码不在 200～299。
退出码：0＝全部成功；1＝存在失败（读数仍会打印，便于留痕）。
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass


def _percentile(values, pct):
    """最近秩法（nearest-rank）：返回第 ceil(n*pct/100) 个值；空列表返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    import math
    rank = max(1, math.ceil(len(ordered) * pct / 100.0))
    return ordered[min(rank, len(ordered)) - 1]


def _one(url, timeout, counter, lock, latencies, failures):
    with counter["lock"]:
        counter["index"] += 1
        index = counter["index"]
    request = urllib.request.Request(url, method="GET", headers={
        "User-Agent": "ashare-stress/1.0 (+local)",
        "X-Request-Id": "stress-%04d" % index,
    })
    start = time.perf_counter()
    status = None
    error = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        error = "HTTP %s" % exc.code
    except Exception as exc:                                  # noqa: BLE001
        error = "%s: %s" % (type(exc).__name__, exc)
    elapsed = (time.perf_counter() - start) * 1000.0
    with lock:
        latencies.append(elapsed)
        if error is not None or status is None or not (200 <= status < 300):
            failures.append({"index": index, "status": status, "error": error})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="轻量 HTTP 压测（默认 20 请求／并发 5／/api/health）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="后端根地址（默认 http://127.0.0.1:8000）")
    parser.add_argument("--endpoint", default="/api/health",
                        help="请求路径（默认 /api/health；它不受限流约束）")
    parser.add_argument("--requests", type=int, default=20,
                        help="总请求数（默认 20；限流 60 次/60 秒，别默认打满）")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="并发线程数（默认 5）")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="单请求超时秒数（默认 10）")
    parser.add_argument("--json", default=None,
                        help="可选：把读数另存为 JSON（目录不存在会自动创建）")
    args = parser.parse_args(argv)

    if args.requests < 1 or args.concurrency < 1:
        print("[压测] requests 与 concurrency 必须为正整数", file=sys.stderr)
        return 2
    if args.endpoint.startswith("/api/qa"):
        print("[压测] 提示：问答接口每条可能 10 s 以上，且受 60 次/60 秒限流；"
              "请确认已按需放宽 ASHARE_RATE_LIMIT_MAX。", file=sys.stderr)

    url = args.base_url.rstrip("/") + "/" + args.endpoint.lstrip("/")
    latencies, failures = [], []
    counter = {"index": 0, "lock": threading.Lock()}
    lock = threading.Lock()

    from concurrent.futures import ThreadPoolExecutor
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(_one, url, args.timeout, counter, lock, latencies, failures)
                   for _ in range(args.requests)]
        for future in futures:
            future.result()
    wall = time.perf_counter() - started

    ok = len(latencies) - len(failures)
    qps = (len(latencies) / wall) if wall > 0 else 0.0
    report = {
        "url": url,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "wall_seconds": round(wall, 4),
        "qps": round(qps, 3),
        "ok": ok,
        "failed": len(failures),
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else None,
            "p50": round(_percentile(latencies, 50), 3) if latencies else None,
            "p95": round(_percentile(latencies, 95), 3) if latencies else None,
            "p99": round(_percentile(latencies, 99), 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
            "mean": round(statistics.fmean(latencies), 3) if latencies else None,
        },
        "failures": failures[:20],
    }

    print("=" * 66)
    print("压测：%s" % url)
    print("请求 %d 次｜并发 %d｜墙钟 %.3f s｜QPS %.3f"
          % (args.requests, args.concurrency, wall, qps))
    lat = report["latency_ms"]
    print("成功 %d｜失败 %d" % (ok, len(failures)))
    print("延迟(ms)：min %s｜P50 %s｜P95 %s｜P99 %s｜max %s｜mean %s"
          % (lat["min"], lat["p50"], lat["p95"], lat["p99"], lat["max"], lat["mean"]))
    if failures:
        print("失败明细（最多 20 条）：")
        for item in report["failures"]:
            print("  #%04d status=%s error=%s"
                  % (item["index"], item["status"], item["error"]))
    print("=" * 66)

    if args.json:
        import os
        directory = os.path.dirname(os.path.abspath(args.json))
        os.makedirs(directory, exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        print("读数已写入：%s" % args.json)

    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
