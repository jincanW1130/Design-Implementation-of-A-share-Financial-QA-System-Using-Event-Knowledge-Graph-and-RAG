# -*- coding: utf-8 -*-
"""代码\\后端\\observability.py —— 轻量结构化日志与**进程内**指标（第 4 轮：8.1／8.2）。

为什么单独成模块
----------------
第 2 轮已把 `main.py` 收敛为装配层；访问日志与指标属于「横切观测」，与限流／校验
（`middleware.py`）职责不同，故独立成文件，`main.py` 只调用 `install_metrics(app)`。

两条边界（本机没有 Prometheus／OpenTelemetry／APM，**不引入新服务与新依赖**）
--------------------------------------------------------------------------------
* **指标只在进程内**：滑动窗口样本保存在内存里，重启即清零；单进程单实例口径，
  多 worker／多实例不聚合（与现有单进程限流同一登记方式）。
* **指标摘要不新增路由**：挂在既有 `GET /api/health` 的 `metrics` 键上。这样 OpenAPI
  的路径／操作数不变，`验收第9阶段.py` 的 C1「未登记新增接口」不会因本轮变红；
  代价是健康探测会顺带做一次内存快照（微秒级，见方案文档的取舍说明）。

结构化日志
----------
`AccessLogMiddleware` 为每个 `/api/*` 请求写一行：
`access method=… path=… status=… duration_ms=… route=…`
* 级别固定 INFO（错误仍由 `errors.py` 的异常处理器按 WARNING／ERROR 记录）；
* 请求 ID 由 `errors.py` 的 `RequestIdFilter` 自动补在行首，**不重复打印**；
* 只记方法、路径模板、状态码、耗时，**不记请求体、不记 question 原文、不记任何口令**；
* 支持采样：`ASHARE_ACCESS_LOG=0` 关闭；`ASHARE_ACCESS_LOG_SAMPLE_RATE=0～1` 按比例采样
  （缺省 1.0，即全量）。采样只影响日志行，不影响指标计数。

指标口径（`/api/health` 的 `metrics`）
--------------------------------------
* `requests`：全局总请求数、最近 60 s 的请求数／QPS／错误率（HTTP ≥ 400 计错误）；
* `routes`：按「方法 + 路由模板」分组（模板不含具体 id，避免高基数），
  `avg_ms`／`p50_ms`／`p95_ms`／`p99_ms` 取最近 300 s 样本，`qps` 与 `error_rate` 取最近 60 s；
* `qa`：`/api/qa/ask` 的成功／失败计数（按 HTTP 状态；200＝成功，≥400＝失败）；
* `retrieval`：问答链路的**检索侧计数**（第三轮 8.2）——实际跑链路的次数、图谱查询
  次数、证据总数、空结果数、复用次数，以及**知识库命中率**（有可引用证据的链路占比）。
  由 `services/qa_service.py` 在链路返回后写入；不记录问题原文，不增加路由，仍是进程内口径。
* `llm`：`answer_trace.jsonl` 的 **attempts** 聚合（第八轮 8.2）——调用次数、失败次数、
  失败率、累计／平均秒数。失败定义为「尝试请求失败或返回空正文」；重试按实际尝试逐次计数。
* `rate_limit`：限流中间件实际拒绝的次数（1004／429）。
* 每个路由最多保留 2000 个样本、最多 128 个路由键；超出后旧样本自然淘汰或归入
  `__other__`，防止探测工具制造高基数把内存打满。
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
import time
from collections import deque

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("ashare_qa.backend")

WINDOW_SECONDS = 60.0          # QPS／错误率的统计窗口
HISTORY_SECONDS = 300.0        # P50／P95／P99 的样本窗口
MAX_SAMPLES_PER_ROUTE = 2000
MAX_ROUTE_KEYS = 128
OTHER_ROUTE_KEY = "__other__"

ACCESS_LOG_ENABLED = os.environ.get("ASHARE_ACCESS_LOG", "1").strip().lower() not in (
    "0", "false", "off", "no")

# 路由模板归一：数字段、UUID、`EVT-0006` / `PER-0001` / `HCONF-…` 这类标识段替换成 `{id}`。
# 目的：按「接口」聚合指标，同时避免具体 id 制造无限多的键。
_ID_SEGMENT_RE = re.compile(
    r"^(?:\d+|[0-9a-fA-F]{16,}|[A-Za-z]{1,12}[-_][A-Za-z0-9_-]*\d[A-Za-z0-9_-]*)$")


def normalize_path(path: str) -> str:
    """把请求路径归一成低基数模板（只用于指标／日志的 route 字段）。"""
    parts = [p for p in str(path or "").split("/") if p]
    out = []
    for part in parts:
        out.append("{id}" if _ID_SEGMENT_RE.match(part) else part)
    return "/" + "/".join(out)


def request_route(request) -> str:
    """优先用框架登记的路由模板；新版 FastAPI 的 include_router 模板可能不含前缀，
    此时用归一化后的实际路径（例如 `/api/graph/events/{id}`）。"""
    route = getattr(request.scope.get("route"), "path", None)
    if route and str(route).startswith("/api/"):
        return str(route)
    return normalize_path(request.url.path)


def _sample_rate() -> float:
    raw = os.environ.get("ASHARE_ACCESS_LOG_SAMPLE_RATE", "").strip()
    if not raw:
        return 1.0
    try:
        value = float(raw)
    except ValueError:
        return 1.0
    return min(1.0, max(0.0, value))


ACCESS_LOG_SAMPLE_RATE = _sample_rate()


class MetricsRegistry:
    """进程内滑动窗口指标（线程安全；只依赖标准库）。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._started = time.monotonic()
        self._routes = {}                  # key -> deque[(monotonic_ts, duration_ms, status)]
        self._total_requests = 0
        self._qa_success = 0
        self._qa_failure = 0
        self._rate_limit_hits = 0
        # 检索侧计数（第三轮 8.2）：只累计，不做滑动窗口；重启清零。
        self._retrieval = {
            "vector_searches": 0,
            "graph_queries": 0,
            "evidence_total": 0,
            "empty_results": 0,
            "reused_answers": 0,
        }
        # LLM 尝试聚合（第八轮 8.2）：按 answer_trace 的 attempts 逐次计数。
        self._llm_calls = 0
        self._llm_failures = 0
        self._llm_seconds_total = 0.0

    # ---- 写入 ----
    def record_request(self, method: str, route: str, status: int,
                       duration_ms: float) -> None:
        now = time.monotonic()
        key = "%s %s" % (str(method or "?").upper(), route or "?")
        with self._lock:
            self._total_requests += 1
            if key not in self._routes and len(self._routes) >= MAX_ROUTE_KEYS:
                key = OTHER_ROUTE_KEY
            queue = self._routes.get(key)
            if queue is None:
                queue = deque(maxlen=MAX_SAMPLES_PER_ROUTE)
                self._routes[key] = queue
            queue.append((now, float(duration_ms), int(status)))
            cutoff = now - HISTORY_SECONDS
            while queue and queue[0][0] < cutoff:
                queue.popleft()
            if route == "/api/qa/ask":
                if int(status) < 400:
                    self._qa_success += 1
                else:
                    self._qa_failure += 1

    def record_rate_limit_hit(self) -> None:
        with self._lock:
            self._rate_limit_hits += 1

    def record_qa_retrieval(self, *, evidence_count: int = 0, graph_used: bool = False,
                            empty: bool = False, reused: bool = False) -> None:
        """记录一次问答的检索侧结果（第三轮 8.2）。

        * `reused=True`：命中同会话已有回答，**没有**发生新的向量检索；
        * 其余情况：`vector_searches` +1；`graph_used` 为真时 `graph_queries` +1；
        * `evidence_count` 累加进 `evidence_total`（空结果为 0）；
        * `empty=True` 时 `empty_results` +1。

        全部为整数计数，不保存问题/答案文本，不引入高基数标签。
        """
        with self._lock:
            if reused:
                self._retrieval["reused_answers"] += 1
                return
            self._retrieval["vector_searches"] += 1
            if graph_used:
                self._retrieval["graph_queries"] += 1
            if empty:
                self._retrieval["empty_results"] += 1
            try:
                count = int(evidence_count)
            except (TypeError, ValueError):
                count = 0
            self._retrieval["evidence_total"] += max(count, 0)

    def record_llm_attempts(self, attempts) -> None:
        """记录一次问答链路里的 LLM 尝试（`answer_trace.jsonl` 的 `attempts`）。

        * 每次尝试计一次 `calls`（重试不合并）；
        * `ok=false`（请求失败）或 `empty_body=true`（请求成功但正文为空）计一次 failure；
        * `seconds` 累加为总耗时；非法数值按 0 处理。

        只保存整数／浮点计数，不保存 Prompt、问题或答案正文。
        """
        rows = attempts if isinstance(attempts, list) else []
        calls = 0
        failures = 0
        seconds = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            calls += 1
            if not row.get("ok") or row.get("empty_body"):
                failures += 1
            try:
                seconds += max(float(row.get("seconds") or 0.0), 0.0)
            except (TypeError, ValueError):
                pass
        if not calls:
            return
        with self._lock:
            self._llm_calls += calls
            self._llm_failures += failures
            self._llm_seconds_total += seconds

    # ---- 读取 ----
    def snapshot(self) -> dict:
        now = time.monotonic()
        window_cutoff = now - WINDOW_SECONDS
        with self._lock:
            routes = {key: list(queue) for key, queue in self._routes.items()}
            total = self._total_requests
            qa_success = self._qa_success
            qa_failure = self._qa_failure
            hits = self._rate_limit_hits
            retrieval = dict(self._retrieval)
            llm_calls = self._llm_calls
            llm_failures = self._llm_failures
            llm_seconds_total = self._llm_seconds_total
            uptime = now - self._started

        # P2（独立审查 2026-10-19）：历史窗口必须与 HISTORY_SECONDS 一致。旧实现按
        # `window_cutoff - HISTORY_SECONDS`（即 now-360）过滤；record_request() 虽在写入时
        # 裁剪 300 s，但空闲后的首次 snapshot 不会重新裁剪，于是 300～360 s 的样本被算进
        # avg/p50/p95/p99。这里直接以 now-HISTORY_SECONDS 为下界，写入与读取同一口径。
        history_cutoff = now - HISTORY_SECONDS
        all_samples = []
        route_items = {}
        for key in sorted(routes):
            samples = [s for s in routes[key] if s[0] >= history_cutoff]
            if not samples:
                continue
            all_samples.extend(samples)
            window = [s for s in samples if s[0] >= window_cutoff]
            durations = [s[1] for s in samples]
            errors = [s for s in window if s[2] >= 400]
            route_items[key] = {
                "count_window": len(window),
                "qps": round(len(window) / WINDOW_SECONDS, 2),
                "errors_window": len(errors),
                "error_rate": round(len(errors) / len(window), 4) if window else 0.0,
                "avg_ms": round(sum(durations) / len(durations), 1) if durations else None,
                "p50_ms": _percentile(durations, 50),
                "p95_ms": _percentile(durations, 95),
                "p99_ms": _percentile(durations, 99),
            }

        window_all = [s for s in all_samples if s[0] >= window_cutoff]
        window_errors = [s for s in window_all if s[2] >= 400]
        qa_total = qa_success + qa_failure
        return {
            "window_seconds": int(WINDOW_SECONDS),
            "history_seconds": int(HISTORY_SECONDS),
            "uptime_seconds": round(uptime, 1),
            "requests": {
                "total": total,
                "window": len(window_all),
                "qps": round(len(window_all) / WINDOW_SECONDS, 2),
                "errors_window": len(window_errors),
                "error_rate": round(len(window_errors) / len(window_all), 4)
                if window_all else 0.0,
            },
            "routes": route_items,
            "qa": {
                "success": qa_success,
                "failure": qa_failure,
                "success_rate": round(qa_success / qa_total, 4) if qa_total else 0.0,
            },
            "retrieval": {
                **retrieval,
                "evidence_avg": (round(retrieval["evidence_total"]
                                       / retrieval["vector_searches"], 2)
                                 if retrieval["vector_searches"] else 0.0),
                "kb_hit_rate": (round((retrieval["vector_searches"]
                                       - retrieval["empty_results"])
                                      / retrieval["vector_searches"], 4)
                                if retrieval["vector_searches"] else 0.0),
            },
            "llm": {
                "calls": llm_calls,
                "failures": llm_failures,
                "failure_rate": (round(llm_failures / llm_calls, 4)
                                 if llm_calls else 0.0),
                "total_seconds": round(llm_seconds_total, 3),
                "avg_seconds": (round(llm_seconds_total / llm_calls, 3)
                                if llm_calls else 0.0),
            },
            "rate_limit": {"hits": hits},
        }


def _percentile(values: list, pct: int):
    """最近邻百分位（不引入 numpy 依赖）；样本为空返回 None。"""
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((pct / 100.0) * (len(ordered) - 1)))
    index = min(max(index, 0), len(ordered) - 1)
    return round(ordered[index], 1)


METRICS = MetricsRegistry()


def record_rate_limit_hit() -> None:
    METRICS.record_rate_limit_hit()


def record_qa_retrieval(**kwargs) -> None:
    METRICS.record_qa_retrieval(**kwargs)


def record_llm_attempts(attempts) -> None:
    METRICS.record_llm_attempts(attempts)


def snapshot() -> dict:
    return METRICS.snapshot()


class AccessLogMiddleware(BaseHTTPMiddleware):
    """记录 `/api/*` 的访问日志并写入进程内指标（不读请求体、不记问题原文）。"""

    def __init__(self, app, scope_prefix: str = "/api/"):
        super().__init__(app)
        self.scope_prefix = scope_prefix

    async def dispatch(self, request, call_next):
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            if request.url.path.startswith(self.scope_prefix):
                duration_ms = (time.perf_counter() - started) * 1000.0
                route = request_route(request)
                METRICS.record_request(request.method, route, status, duration_ms)
                if ACCESS_LOG_ENABLED and random.random() < ACCESS_LOG_SAMPLE_RATE:
                    logger.info("access method=%s path=%s status=%d duration_ms=%.1f route=%s",
                                request.method, _short(request.url.path), status,
                                duration_ms, _short(route))


def _short(text: str, limit: int = 200) -> str:
    """路径长度兜底：异常长的探测路径不把日志撑爆。"""
    text = str(text or "")
    return text if len(text) <= limit else text[:limit] + "…"


def install_metrics(app) -> None:
    """挂载访问日志／指标中间件。调用位置在 `errors.register_request_id()` 之前：
    这样它位于限流／校验／CORS 外层（能统计到被拒请求），又位于请求 ID 内层
    （日志自动带同一个 request_id）。"""
    app.add_middleware(AccessLogMiddleware)
