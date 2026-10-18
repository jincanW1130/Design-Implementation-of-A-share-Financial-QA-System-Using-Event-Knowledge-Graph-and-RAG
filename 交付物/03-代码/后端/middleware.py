# -*- coding: utf-8 -*-
"""代码\\后端\\middleware.py —— 后端的横切中间件（限流／请求体与问题校验／响应头）。

为什么从 `main.py` 拆出来
-------------------------
`main.py` 原先同时承担「应用装配」与「中间件实现」两件事（近 500 行）。第 2 轮按单一
职责拆开：本模块只放**与路由无关的请求处理策略**，`main.py` 只保留装配、探针与路由注册。
`main.RateLimitMiddleware`／`main.GuardMiddleware` 仍重导出同一类对象（测试对类属性打
monkeypatch 的行为不变）。

两条容易踩的坑（沿用原注释）
----------------------------
* **中间件里抛 `ApiError` 不会被 `@app.exception_handler` 接住**：`ApiError` 的处理挂在
  `ExceptionMiddleware` 上，而用户中间件在它**之外**。故这里的中间件一律**自己返回
  `JSONResponse`**（经 `errors.error_response`），不靠异常处理器。
* **`/api/health` 不参与限流**：探活与门禁会频繁请求，计入窗口会把自己的探活挡掉。
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

import errors
import observability
import params


class RateLimitMiddleware(BaseHTTPMiddleware):
    """按来源 IP 的**滑动窗口**限流（阈值与窗口长度取 `config.RATE_LIMIT`）。

    实现：每来源 IP 一个时间戳双端队列，惰性剔除窗口外的记录；窗口内计数达到上限即拒。
    超限返回 HTTP 429 ＋ 错误码 1004，并带 `Retry-After` 头。只在 `/api/*` 上生效，
    `/api/health` 豁免（探活不受限）。

    这是**单进程内**限流（第一版为单机演示，不做多进程／多实例共享计数，登记为已知限制）。

    2026-10-11 按 S2 加固三点：
    * **来源默认只信直连地址**：`X-Forwarded-For` 仅当 `trust_proxy_headers=True`
      （`config.local.json` 可选键，默认 False）时才读——直连形态信任 XFF 等于让
      伪造头绕过限流并污染日志；
    * **键数量有界**：跟踪的 IP 键超过 `MAX_TRACKED_IPS` 即清扫，仍超则按最近活动
      时间淘汰最旧的键——消除「伪造 IP 轮换打爆 `_hits` 内存」的攻击面；
    * **低频全量清扫**：每 `SWEEP_INTERVAL_SECONDS` 秒清一次全空窗口的键，
      空队列即删键，不残留空 deque。
    """

    MAX_TRACKED_IPS = 100_000
    """跟踪的来源 IP 键上限（S2 自保护）。单键是一小段 deque（窗口内 ≤ max_requests 个
    时间戳），10 万键约为数十 MB 量级；触顶先全量清扫，仍超则淘汰最旧键并告警。"""

    SWEEP_INTERVAL_SECONDS = 60.0
    """全量清扫的最小间隔（秒）：正常流量下每分钟扫一次；触顶时立即触发，不等间隔。"""

    def __init__(self, app, window_seconds: int, max_requests: int, exempt_paths=(),
                 scope_prefix="/api/", trust_proxy_headers: bool = False):
        super().__init__(app)
        self.window = float(window_seconds)
        self.max_requests = int(max_requests)
        self.exempt_paths = set(exempt_paths)
        self.scope_prefix = scope_prefix
        self.trust_proxy_headers = bool(trust_proxy_headers)
        self._hits = {}
        self._lock = threading.Lock()
        self._last_sweep = time.monotonic()

    def _client_ip(self, request: Request) -> str:
        """来源 IP：默认取直连地址；仅当部署在可信反代之后才读 `X-Forwarded-For` 首段。"""
        if self.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _sweep_locked(self, now: float) -> None:
        """清理过期键（持锁调用）：删全空窗口的键；仍超上限则淘汰最旧键（S2 自保护）。"""
        expired = [ip for ip, q in self._hits.items()
                   if not q or now - q[-1] > self.window]
        for ip in expired:
            del self._hits[ip]
        if len(self._hits) > self.MAX_TRACKED_IPS:
            overflow = len(self._hits) - self.MAX_TRACKED_IPS
            oldest = sorted(self._hits, key=lambda ip: self._hits[ip][-1])[:overflow]
            for ip in oldest:
                del self._hits[ip]
            errors.logger.warning("限流器跟踪键数超上限（%d），已淘汰 %d 个最久未活动的来源"
                                  "（S2 自保护：淘汰意味着这些来源的窗口计数清零）",
                                  self.MAX_TRACKED_IPS, overflow)

    def _over_limit(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if now - self._last_sweep >= self.SWEEP_INTERVAL_SECONDS:
                self._last_sweep = now
                self._sweep_locked(now)                     # 低频清扫（S2）
            queue = self._hits.get(ip)
            if queue is not None:
                while queue and now - queue[0] > self.window:
                    queue.popleft()
                if not queue:
                    del self._hits[ip]                      # 空队列即删键（S2）
                    queue = None
            if queue is not None and len(queue) >= self.max_requests:
                return True
            self._hits.setdefault(ip, deque()).append(now)
            if len(self._hits) > self.MAX_TRACKED_IPS:
                self._sweep_locked(now)                     # 触顶立即清扫（S2）
            return False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(self.scope_prefix) and path not in self.exempt_paths:
            ip = self._client_ip(request)
            if self._over_limit(ip):
                observability.record_rate_limit_hit()      # 第 4 轮 8.2：限流命中计数
                errors.logger.warning("限流：ip=%s path=%s 在 %ss 窗口内超过 %d 次",
                                      ip, path, self.window, self.max_requests)
                response = errors.error_response(
                    1004, detail="ip=%s path=%s window=%ss max=%d"
                    % (ip, path, self.window, self.max_requests))
                response.headers["Retry-After"] = str(int(self.window))
                return response
        return await call_next(request)


class GuardMiddleware(BaseHTTPMiddleware):
    """请求体大小 ＋ 问题长度两步校验（都按错误码 **1001**／HTTP 400 拒）。

    * **大小**：`Content-Length` 超过 `config.LIMITS["max_body_bytes"]`（64 KiB）即拒，
      不读正文（省内存）。分块传输（无 `Content-Length`）无法在中间件层预判，
      交由下游读取时自然受限，登记为已知限制。
    * **问题长度**：正文是 JSON 且含 `question` 字段时，按 `params.validate_question()`
      校验。该字段缺失时不在这里拦——是否必填由具体接口决定（缺必填按 1003）。

    在中间件层拦一道，是为了让「超长输入」在任何接口上都不会先落进业务逻辑；
    各接口仍应调用 `validate_question()` 复核（纵深防御，且便于单测）。
    """

    def __init__(self, app, max_body_bytes: int, scope_prefix="/api/"):
        super().__init__(app)
        self.max_body_bytes = int(max_body_bytes)
        self.scope_prefix = scope_prefix

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith(self.scope_prefix):
            declared = request.headers.get("content-length")
            if declared is not None:
                try:
                    size = int(declared)
                except ValueError:
                    return errors.error_response(
                        1002, detail="Content-Length 不是整数：%r" % declared)
                if size > self.max_body_bytes:
                    errors.logger.warning("请求体过大：path=%s content-length=%d 上限=%d",
                                          request.url.path, size, self.max_body_bytes)
                    return errors.error_response(
                        1001, detail="content-length=%d > max_body_bytes=%d"
                        % (size, self.max_body_bytes))
            ctype = (request.headers.get("content-type") or "").lower()
            if "application/json" in ctype:
                body = await request.body()          # Starlette 会缓存，下游可重复读
                if body:
                    try:
                        payload = json.loads(body.decode("utf-8"))
                    except Exception as exc:
                        return errors.error_response(
                            1002, detail="请求体不是合法 JSON：%s" % type(exc).__name__)
                    if isinstance(payload, dict) and "question" in payload:
                        try:
                            params.validate_question(payload["question"])
                        except errors.ApiError as exc:
                            return errors.error_response(
                                exc.code, message=exc.message, http_status=exc.http_status,
                                detail=exc.detail)
        return await call_next(request)


def install_response_middlewares(app) -> None:
    """安装基础安全响应头与「裸 OPTIONS」兜底（后加的在外层，调用顺序即原顺序）。

    2026-10-18 全面审查 B：后端只输出 JSON、不渲染 HTML，故 CSP 不在此设（应由静态
    服务器／反向代理统一设）；这里补三个零风险的头：禁 MIME 嗅探、禁被 iframe 嵌套、
    不外泄 Referer。
    """
    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        return response

    # 2026-10-18（第二轮）HTTP 语义：非 CORS 预检的 OPTIONS 也要可用。
    # Starlette 的 CORSMiddleware 只对「带 Origin ＋ Access-Control-Request-Method」的预检
    # 短路；裸 OPTIONS（探测工具常见）此前落到路由匹配 → 405 且无 Allow。这里兜一层：
    # 返回 204 ＋ Allow，且**不**覆盖预检响应（预检在更外层已被 CORS 处理）。
    @app.middleware("http")
    async def _options(request, call_next):
        if request.method == "OPTIONS" and not request.headers.get("access-control-request-method"):
            resp = Response(status_code=204)
            resp.headers["Allow"] = "GET, HEAD, POST, PUT, DELETE, OPTIONS"
            return resp
        return await call_next(request)
