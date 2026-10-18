# -*- coding: utf-8 -*-
"""工具\\告警检查.py —— 第二轮第 9 轮（8.4 告警落地）：按阈值检查 `/api/health`。

做什么
------
读取运行中后端 `GET /api/health` 的**四项依赖状态**与 **`metrics` 摘要**，按阈值判定；
任一项超阈值就**非零退出（1）并逐条打印原因**；全部在阈值内退出 0。可直接挂到
Windows 任务计划程序／cron，作为「无外部告警通道」时的最小可用告警。

默认阈值（脚本顶部常量；全部可用命令行参数覆盖）
------------------------------------------------
| 参数 | 默认 | 含义 |
| --- | --- | --- |
| `--error-rate` | **0.05（5%）** | 最近 60 s 全站错误率（HTTP ≥ 400 计错误），比例 0～1 |
| `--p95-ms` | **2000** | 非问答路由的 P95 上限（毫秒） |
| `--qa-p95-ms` | **320000** | `POST /api/qa/ask` 的 P95 上限（毫秒；前端等待上限 320 s，LLM 链路天然慢，故单列） |
| `--rate-limit-hits` | **20** | 进程启动以来累计限流命中数上限（1004／429） |
| `--timeout` | **8** | 请求健康接口的超时（秒） |

**依赖判定**：`mysql`／`neo4j`／`vector_index`／`model_config` 任一 `ok=false`，
或 `metrics` 不可用，均视为超阈值（`metrics` 不可用时无法评估后三条，直接失败而不是猜）。

指标口径提醒
------------
指标是**进程内**的：重启清零、多 worker 不聚合（与既有单进程限流同一登记方式）；
`rate_limit.hits` 是**累计值**，不是 60 s 窗口值——阈值选 20 是「自启动以来明显异常」
的粗粒度判据，重启会复位。

用法
----
    python 工具\\告警检查.py
    python 工具\\告警检查.py --error-rate 0.02 --p95-ms 1500 --rate-limit-hits 5
    python 工具\\告警检查.py --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# ---- 默认阈值（命令行可覆盖；改这里即改全局默认） -------------------------
DEFAULT_ERROR_RATE = 0.05          # 最近 60 s 错误率上限（5%）
DEFAULT_P95_MS = 2000.0            # 非问答路由 P95 上限（2 s）
DEFAULT_QA_P95_MS = 320000.0       # 问答路由 P95 上限（320 s，与前端等待上限一致）
DEFAULT_RATE_LIMIT_HITS = 20       # 进程启动以来累计限流命中上限
DEFAULT_TIMEOUT = 8.0

QA_ROUTE = "POST /api/qa/ask"
DEPENDENCIES = ("mysql", "neo4j", "vector_index", "model_config")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def fetch_health(base_url: str, timeout: float) -> dict:
    """读取 `/api/health`（只读；不发送任何凭据）。"""
    url = base_url.rstrip("/") + "/api/health"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _short(text, limit: int = 160) -> str:
    text = str(text or "").replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def _p95_of(route_item) -> float | None:
    if not isinstance(route_item, dict):
        return None
    value = route_item.get("p95_ms")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def evaluate(health: dict, args) -> tuple[list[str], list[str]]:
    """返回 `(超阈值原因列表, 读数行列表)`；原因列表为空即通过。"""
    breaches: list[str] = []
    readings: list[str] = []

    # 1) 四项依赖
    for name in DEPENDENCIES:
        block = health.get(name)
        if not isinstance(block, dict):
            breaches.append("依赖 %s：探针缺失（响应里没有该键）" % name)
            continue
        if block.get("ok"):
            readings.append("依赖 %-12s ok=true  %s"
                            % (name, _short(block.get("info"))))
        else:
            breaches.append("依赖 %s ok=false：%s"
                            % (name, _short(block.get("info"))))
    status = health.get("status")
    readings.append("总体 status     = %r" % status)
    if status != "ok" and not breaches:
        breaches.append("status=%r（不是 ok），但四项探针均报 ok——请核对探针实现" % status)

    # 2) metrics 可用性
    metrics = health.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("available") is False:
        breaches.append("metrics 不可用，无法评估错误率／P95／限流阈值")
        return breaches, readings

    requests = metrics.get("requests") or {}
    error_rate = float(requests.get("error_rate") or 0.0)
    line = ("错误率(60s)    = %.2f%%（%d/%d）阈值 %.2f%%"
            % (error_rate * 100.0, int(requests.get("errors_window") or 0),
               int(requests.get("window") or 0), args.error_rate * 100.0))
    readings.append(line)
    if error_rate > args.error_rate:
        breaches.append("最近 60 s 错误率 %.2f%% > 阈值 %.2f%%"
                        % (error_rate * 100.0, args.error_rate * 100.0))

    routes = metrics.get("routes") or {}
    worst_route, worst_p95 = None, None
    qa_p95 = None
    for key, item in routes.items():
        p95 = _p95_of(item)
        if p95 is None:
            continue
        if key == QA_ROUTE:
            qa_p95 = p95
            continue
        if worst_p95 is None or p95 > worst_p95:
            worst_route, worst_p95 = key, p95

    if worst_p95 is None:
        readings.append("P95(非问答)    = 无样本（阈值 %.0f ms）" % args.p95_ms)
    else:
        readings.append("P95(非问答)    = %.1f ms（%s）阈值 %.0f ms"
                        % (worst_p95, worst_route, args.p95_ms))
        if worst_p95 > args.p95_ms:
            breaches.append("路由 %s 的 P95 %.1f ms > 阈值 %.0f ms"
                            % (worst_route, worst_p95, args.p95_ms))

    if qa_p95 is None:
        readings.append("P95(问答)      = 无样本（阈值 %.0f ms）" % args.qa_p95_ms)
    else:
        readings.append("P95(问答)      = %.1f ms 阈值 %.0f ms"
                        % (qa_p95, args.qa_p95_ms))
        if qa_p95 > args.qa_p95_ms:
            breaches.append("问答路由 P95 %.1f ms > 阈值 %.0f ms"
                            % (qa_p95, args.qa_p95_ms))

    hits = int((metrics.get("rate_limit") or {}).get("hits") or 0)
    readings.append("限流命中(累计) = %d 阈值 %d" % (hits, args.rate_limit_hits))
    if hits > args.rate_limit_hits:
        breaches.append("限流累计命中 %d > 阈值 %d（检查是否有来源被 429／1004）"
                        % (hits, args.rate_limit_hits))

    qa = metrics.get("qa") or {}
    readings.append("问答成败       = 成功 %s／失败 %s（成功率 %s）"
                    % (qa.get("success"), qa.get("failure"), qa.get("success_rate")))
    return breaches, readings


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="按阈值检查 /api/health 的依赖与 metrics，超阈值非零退出")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="后端地址（默认 %s）" % DEFAULT_BASE_URL)
    parser.add_argument("--error-rate", type=float, default=DEFAULT_ERROR_RATE,
                        help="最近 60 s 错误率上限，比例 0～1（默认 %.2f）" % DEFAULT_ERROR_RATE)
    parser.add_argument("--p95-ms", type=float, default=DEFAULT_P95_MS,
                        help="非问答路由 P95 上限，毫秒（默认 %.0f）" % DEFAULT_P95_MS)
    parser.add_argument("--qa-p95-ms", type=float, default=DEFAULT_QA_P95_MS,
                        help="问答路由 P95 上限，毫秒（默认 %.0f）" % DEFAULT_QA_P95_MS)
    parser.add_argument("--rate-limit-hits", type=int, default=DEFAULT_RATE_LIMIT_HITS,
                        help="进程启动以来累计限流命中上限（默认 %d）" % DEFAULT_RATE_LIMIT_HITS)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="健康接口超时，秒（默认 %.0f）" % DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)

    if not (0.0 <= args.error_rate <= 1.0):
        parser.error("--error-rate 必须在 0～1 之间")
    for name in ("p95_ms", "qa_p95_ms", "timeout"):
        if getattr(args, name) <= 0:
            parser.error("--%s 必须为正数" % name.replace("_", "-"))
    if args.rate_limit_hits < 0:
        parser.error("--rate-limit-hits 不得为负数")

    url = args.base_url.rstrip("/") + "/api/health"
    print("=" * 78)
    print("告警检查：%s" % url)
    print("=" * 78)
    print("阈值：错误率 %.2f%% ｜ 非问答 P95 %.0f ms ｜ 问答 P95 %.0f ms ｜ 累计限流 %d"
          % (args.error_rate * 100.0, args.p95_ms, args.qa_p95_ms, args.rate_limit_hits))
    print()

    try:
        health = fetch_health(args.base_url, args.timeout)
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print("[FAIL] 无法读取健康接口：%s: %s" % (type(exc).__name__, first))
        print("结论：告警检查失败（后端不可达或响应不是合法 JSON）。退出码 1。")
        return 1
    if not isinstance(health, dict):
        print("[FAIL] 健康接口响应不是 JSON 对象。")
        print("结论：告警检查失败。退出码 1。")
        return 1

    breaches, readings = evaluate(health, args)
    for line in readings:
        print("  %s" % line)
    print()

    if breaches:
        print("超阈值 %d 项：" % len(breaches))
        for reason in breaches:
            print("  [BREACH] %s" % reason)
        print("\n结论：告警（超阈值）。退出码 1。")
        return 1

    print("结论：四项依赖均 ok，metrics 各项在阈值内。退出码 0。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
