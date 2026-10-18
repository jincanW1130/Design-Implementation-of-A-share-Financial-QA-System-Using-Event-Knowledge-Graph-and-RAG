# -*- coding: utf-8 -*-
"""代码\\后端\\main.py —— 第 9 阶段（前后端系统集成）后端的 **FastAPI 应用装配**。

第 2 轮重构说明
---------------
原文件近 500 行，同时承担「装配 ＋ 中间件 ＋ 探针 ＋ 参数校验」。本轮按单一职责拆成
四个模块，本文件只保留**装配**：

* `params.py` —— 参数解析／校验（`validate_question`、分页、整数、布尔开关）；
* `middleware.py` —— 限流、请求体／问题长度校验、安全响应头、裸 OPTIONS 兜底；
* `probes.py` —— `/api/health` 的四项探针；
* `main.py`（本文件）—— CORS、异常处理装配、可选路由注册、健康路由、启动清理。

为兼容既有调用方与测试，`main.validate_question`、`main.RateLimitMiddleware`、
`main.GuardMiddleware`、`main.probe_*`、`main.health_payload` 等名字**全部原样重导出**
（指向同一对象，monkeypatch 类属性仍然生效）。

装配内容
--------
  1. **CORS**：允许来源取自 `config.CORS_ORIGINS`（端口一律读 `config.local.json`）。
  2. **统一异常处理**：委派 `errors.install_exception_handlers(app)`——响应体键集合
     恰为 `{code, message}`（硬约束 7）。
  3. **请求 ID**：委派 `errors.register_request_id(app)`——进日志与 `X-Request-Id`
     响应头，**不进响应体**。
  4. **中间件**：限流（1004／429；`/api/health` 豁免）＋请求体大小／问题长度
     （1001／1002）＋基础安全头＋裸 OPTIONS 兜底。
  5. **`GET /api/health`**：`{status, mysql, neo4j, vector_index, model_config}`。
  6. **可选路由**：`api/*.py` 存在就注册，不存在就打印说明，后端可独立启动。
"""

from __future__ import annotations

import importlib
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

import config
import errors
import middleware
import observability
import probes
from params import validate_question       # noqa: F401（重导出：测试与既有调用方直接取用）

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger

# 重导出中间件与探针（保持 `main.<name>` 可用；对象身份不变）
RateLimitMiddleware = middleware.RateLimitMiddleware
GuardMiddleware = middleware.GuardMiddleware
probe_mysql = probes.probe_mysql
probe_neo4j = probes.probe_neo4j
probe_vector_index = probes.probe_vector_index
model_config_block = probes.model_config_block
health_payload = probes.health_payload

APP_TITLE = "A 股财经文本问答系统 · 第 9 阶段后端"
APP_VERSION = "stage9-t4-skeleton"

# 可选注册的接口模块 → 路由前缀
# （表 4-13 共 28 行＝业务 25 个接口 ＋ 条件性登录 3 个，后者不注册）
OPTIONAL_ROUTERS = [
    ("qa", "/api/qa"),
    ("evidence", "/api/evidence"),
    ("history", "/api/history"),
    ("graph", "/api/graph"),
    ("admin", "/api/admin"),
    ("market", "/api/market"),
    # 2026-10-18 工程增强：BM25 关键词召回（只读；不进入论文 A～E 实验口径）
    ("search", "/api/search"),
]


# ==========================================================================
# 1. 可选接口模块的注册
# ==========================================================================
def register_optional_routers(app: FastAPI) -> dict:
    """`api\\<name>.py` 存在且有 `router` 就挂上；不存在就记一行说明（不中断启动）。

    模块可**另带**一个可选的 `extra_routers`，形如 `[(router, 绝对前缀), …]`——用于挂载
    **不属于本前缀**但同属该模块的接口：`api\\qa.py` 的 `GET /api/config/meta`、
    `api\\evidence.py` 的 `GET /api/documents/{doc_id}/chunks/{chunk_id}`。挂载时
    **按绝对前缀原样落位**（不拼接），路径与表 4-13 逐字一致。
    """
    status = {}
    for name, prefix in OPTIONAL_ROUTERS:
        try:
            module = importlib.import_module("api.%s" % name)
        except ImportError:
            status[name] = False
            continue
        router = getattr(module, "router", None)
        if router is None:
            logger.warning("api.%s 已存在但没有 router，跳过注册", name)
            status[name] = False
            continue
        app.include_router(router, prefix=prefix)
        for extra_router, extra_prefix in getattr(module, "extra_routers", ()) or ():
            app.include_router(extra_router, prefix=extra_prefix)
        status[name] = True
    return status


def api_routes(app: FastAPI) -> list:
    """已注册的 `/api/*` 路由清单（`路径 方法`；供启动打印与门禁 C1 自查）。"""
    out = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith("/api/"):
            methods = sorted(getattr(route, "methods", []) or [])
            out.append(("%s %s" % (path, "/".join(methods))).strip())
    return sorted(out)


# ==========================================================================
# 2. 应用装配
# ==========================================================================
def create_app() -> FastAPI:
    errors.setup_logging()
    app = FastAPI(title=APP_TITLE, version=APP_VERSION)

    # 统一异常处理（errors.py 负责三类：ApiError／请求校验／未捕获）
    errors.install_exception_handlers(app)

    # 中间件：先加的在**内层**，后加的在**外层**。CORS 放在限流与校验之外，
    # 这样它们生成的错误响应也带 CORS 头（否则前端只能看到「网络错误」）。
    app.add_middleware(RateLimitMiddleware,
                       window_seconds=config.RATE_LIMIT["window_seconds"],
                       max_requests=config.RATE_LIMIT["max_requests"],
                       exempt_paths={"/api/health"},
                       trust_proxy_headers=bool(getattr(config, "TRUST_PROXY_HEADERS", False)))
    app.add_middleware(GuardMiddleware, max_body_bytes=config.LIMITS["max_body_bytes"])
    app.add_middleware(CORSMiddleware,
                       allow_origins=list(config.CORS_ORIGINS),
                       allow_credentials=True,
                       allow_methods=["*"],
                       allow_headers=["*"])

    # 基础安全响应头 ＋ 裸 OPTIONS 兜底（顺序与拆分前一致）
    middleware.install_response_middlewares(app)

    # 访问日志／进程内指标（第 4 轮 8.1／8.2）：挂在请求 ID 内层、限流与校验外层，
    # 这样被拒请求也计数，且日志自动带同一个 request_id。指标摘要随 /api/health 返回，
    # **不新增路由**（OpenAPI 操作数不变）。
    observability.install_metrics(app)

    # 请求 ID 最后挂 → 位于最外层，限流／校验拒绝的响应同样带 X-Request-Id，
    # 且相关日志都能取到同一个 ID。它只写响应头与日志上下文，不改响应体。
    errors.register_request_id(app)

    # 健康探针（GET／HEAD）。不加统一响应信封：表 4-13 未收录，响应体在
    # 《24》第 3.5 节被逐字规定；HTTP 状态恒为 200。
    @app.api_route("/api/health", methods=["GET", "HEAD"], tags=["health"])
    def health():
        """就绪探针（门禁 A5）：四项依赖的可用状态 ＋ 总体 status。

        同步 `def`：FastAPI 把它放进线程池执行，慢依赖不再阻塞事件循环。
        """
        return JSONResponse(content=health_payload())

    # 可选注册
    status = register_optional_routers(app)

    # M5（2026-10-11 审查）：启动时清理一次过期的 qa_runs 运行目录（此后每 24h 由
    # 问答链路的节流触发；清理失败只记日志，不阻断启动）。
    try:
        from services import qa_service as _qa_service
        _qa_service.cleanup_qa_runs()
    except Exception as _cleanup_exc:                          # noqa: BLE001
        logger.warning("qa_runs 启动清理跳过：%s: %s",
                       type(_cleanup_exc).__name__, _cleanup_exc)

    logger.info("后端骨架已装配：允许来源=%s；限流=%s；请求体上限=%d 字节；问题长度=%d～%d 字",
                "、".join(config.CORS_ORIGINS), config.RATE_LIMIT,
                config.LIMITS["max_body_bytes"], config.LIMITS["question_min_chars"],
                config.LIMITS["question_max_chars"])
    logger.info("已注册的 /api 路由（本批应为 1 条）：%s", "；".join(api_routes(app)))
    for name, _prefix in OPTIONAL_ROUTERS:
        if not status.get(name):
            logger.info("可选接口模块 api\\%s.py 尚未落位——本批不注册该前缀（骨架可独立启动）", name)
    return app


app = create_app()


if __name__ == "__main__":
    # 便于 `python 交付物/03-代码\后端/main.py` 直接起服务（与 run.py 等价，但固定 reload 关）
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.BACKEND_PORT, log_level="info")
