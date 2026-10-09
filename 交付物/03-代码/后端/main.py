# -*- coding: utf-8 -*-
"""代码\\后端\\main.py —— 第 9 阶段（前后端系统集成）后端骨架的 FastAPI 应用装配。

本文件是**骨架**（《24》第七节 T4）：只装配「横切能力」与**一个**就绪探针，
业务接口留待后续批次按表 4-13 逐个落位。装配内容：

  1. **CORS**：允许来源取自 `config.CORS_ORIGINS`（`http://localhost:5173` 与
     `http://127.0.0.1:5173`，端口一律读 `config.local.json`，不写死）。
  2. **统一异常处理**：委派 `errors.install_exception_handlers(app)`——`ApiError`、
     请求校验错误、`HTTPException`、未捕获异常统一转成 `{"code": …, "message": …}`，
     响应体键集合恰为 `{code, message}`（硬约束 7）。
  3. **请求体大小限制**：`config.LIMITS["max_body_bytes"]`（64 KiB）。
  4. **问题长度校验**：`config.LIMITS["question_min_chars"]／["question_max_chars"]`
     （1／500），越界按错误码 **1001** 拒（HTTP 400）。
  5. **按来源 IP 的滑动窗口限流**：阈值取 `config.RATE_LIMIT`，超限按错误码 **1004**
     （HTTP 429）拒——`1004` 是第 9 阶段**新增错误码**，须在《25》登记为新增。
  6. **`GET /api/health`**：返回 `{status, mysql, neo4j, vector_index, model_config}`
     （《24》第 3.5 节 与 门禁 A5）。四项各自带 `ok`；四项的说明文字放在 **`info`** 键下，
     **刻意不用 `detail` 作键名**——`detail` 在本项目里是「只进日志、绝不进响应体」的
     调试字段（硬约束 7），任何响应体里都不出现该键，以免机检把探针说明误判为泄出的调试信息。

本批**只注册 `/api/health` 一条业务路由**；`/api/qa`／`/api/evidence`／`/api/history`／
`/api/graph`／`/api/admin` 走**可选注册**：模块存在就挂上，不存在就打印一行说明并继续，
因此本批的后端可以**独立启动**（《24》第七节 T4 的「可独立启动」要求）。

两条容易踩的坑（写在这里供后续批次参照）
----------------------------------------
* **中间件里抛 `ApiError` 不会被 `@app.exception_handler` 接住**：`ApiError` 的处理挂在
  `ExceptionMiddleware` 上，而用户中间件在它**之外**。故本文件的中间件一律**自己返回
  `JSONResponse`**（经 `errors.error_response`），不靠异常处理器。
* **`/api/health` 不参与限流**：一键启动脚本与门禁 A5 会频繁探活，若把探针也算进窗口，
  正常探活会被自己的限流挡掉。故限流只作用于 `/api/*` 里的**其余**路径（已登记限制参数，
  《24》第八节 G2）。
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import threading
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import config
import errors

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger

APP_TITLE = "A 股财经文本问答系统 · 第 9 阶段后端"
APP_VERSION = "stage9-t4-skeleton"

# 可选注册的接口模块 → 路由前缀（表 4-13 共 28 行＝业务 25 个接口 ＋ 条件性登录 3 个，后者不注册；25 个业务接口按模块归入下列前缀）
OPTIONAL_ROUTERS = [
    ("qa", "/api/qa"),
    ("evidence", "/api/evidence"),
    ("history", "/api/history"),
    ("graph", "/api/graph"),
    ("admin", "/api/admin"),
    ("market", "/api/market"),
]


# ==========================================================================
# 1. 接口层可复用的输入校验（后续批次 api\*.py 直接调用，避免各写一份）
# ==========================================================================
def validate_question(raw) -> str:
    """校验问题文本，返回规范化后的字符串；不合规抛 `ApiError(1001)`。

    规则取自 `config.LIMITS`：去首尾空白后长度必须落在
    `[question_min_chars, question_max_chars]`（1～500）内。`detail` 只进日志。
    """
    if raw is None or not isinstance(raw, str):
        raise errors.ApiError(1001, detail="question 缺失或不是字符串（type=%s）" % type(raw).__name__)
    text = raw.strip()
    lo = int(config.LIMITS["question_min_chars"])
    hi = int(config.LIMITS["question_max_chars"])
    if len(text) < lo:
        raise errors.ApiError(1001, detail="question 去空白后为空（长度 0 < %d）" % lo)
    if len(text) > hi:
        raise errors.ApiError(1001, detail="question 长度 %d 超出上限 %d" % (len(text), hi))
    return text


# ==========================================================================
# 2. 中间件
# ==========================================================================
class RateLimitMiddleware(BaseHTTPMiddleware):
    """按来源 IP 的**滑动窗口**限流（阈值与窗口长度取 `config.RATE_LIMIT`）。

    实现：每来源 IP 一个时间戳双端队列，惰性剔除窗口外的记录；窗口内计数达到上限即拒。
    超限返回 HTTP 429 ＋ 错误码 1004（**第 9 阶段新增，须在《25》登记**），并带
    `Retry-After` 头。只在 `/api/*` 上生效，`/api/health` 豁免（探活不受限）。

    这是**单进程内**限流（第一版为单机演示，不做多进程／多实例共享计数，登记为已知限制）。
    """

    def __init__(self, app, window_seconds: int, max_requests: int, exempt_paths=(),
                 scope_prefix="/api/"):
        super().__init__(app)
        self.window = float(window_seconds)
        self.max_requests = int(max_requests)
        self.exempt_paths = set(exempt_paths)
        self.scope_prefix = scope_prefix
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def _client_ip(self, request: Request) -> str:
        """来源 IP：优先 `X-Forwarded-For` 首段，取不到则用直连地址。"""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _over_limit(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            queue = self._hits[ip]
            while queue and now - queue[0] > self.window:
                queue.popleft()
            if len(queue) >= self.max_requests:
                return True
            queue.append(now)
            return False

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(self.scope_prefix) and path not in self.exempt_paths:
            ip = self._client_ip(request)
            if self._over_limit(ip):
                logger.warning("限流：ip=%s path=%s 在 %ss 窗口内超过 %d 次",
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
    * **问题长度**：正文是 JSON 且含 `question` 字段时，按 `validate_question()` 校验。
      该字段缺失时不在这里拦——是否必填由具体接口决定（缺必填按 1003）。

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
                    logger.warning("请求体过大：path=%s content-length=%d 上限=%d",
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
                            validate_question(payload["question"])
                        except errors.ApiError as exc:
                            return errors.error_response(
                                exc.code, message=exc.message, http_status=exc.http_status,
                                detail=exc.detail)
        return await call_next(request)


# ==========================================================================
# 3. `/api/health` 的四项探针
# ==========================================================================
def probe_mysql() -> dict:
    """MySQL 探针（委派 `db.probe()`；**只报状态，不含口令**）。"""
    try:
        import db
    except Exception as exc:                      # 依赖不可用也不该拖垮探针
        return {"ok": False, "info": "db 模块不可用：%s" % type(exc).__name__}
    info = db.probe()
    return {"ok": bool(info.get("ok")), "info": info.get("detail", "")}


def probe_neo4j() -> dict:
    """Neo4j 探针：连一次即断，连接超时 2 秒；**不打印口令**。"""
    try:
        from neo4j import GraphDatabase
    except Exception as exc:
        return {"ok": False, "info": "neo4j 驱动不可用：%s" % type(exc).__name__}
    params = config.neo4j_params()
    driver = None
    try:
        driver = GraphDatabase.driver(
            params["uri"], auth=(params["user"], params["password"] or None),
            connection_timeout=2.0)
        driver.verify_connectivity()
        return {"ok": True, "info": "%s 可连接" % params["uri"]}
    except Exception as exc:
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return {"ok": False, "info": "%s 不可连接：%s" % (params["uri"], first)}
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass


def probe_vector_index() -> dict:
    """向量索引探针：向量索引三件（索引／映射／构建元信息）齐备且与数据集版本一致。

    **不做向量检索**（那是 `/api/qa` 的事），只判「索引可用」。术语一律写「向量索引」。
    """
    triple = [("索引文件", config.VECTOR_INDEX_PATH),
              ("映射文件", config.VECTOR_MAP_PATH),
              ("构建元信息", config.BUILD_META_PATH)]
    missing = [name for name, path in triple if not os.path.isfile(path)]
    if missing:
        return {"ok": False, "info": "缺文件：%s" % "、".join(missing)}
    try:
        meta = config.read_json(config.BUILD_META_PATH)
    except Exception as exc:
        return {"ok": False, "info": "构建元信息不可解析：%s" % type(exc).__name__}
    version = meta.get("dataset_version")
    if version != config.DATASET_VERSION:
        return {"ok": False, "info": "构建元信息的数据集版本 %r ≠ %r"
                % (version, config.DATASET_VERSION)}
    return {"ok": True,
            "info": "向量 %s 条，维度 %s，%s／%s"
            % (meta.get("vector_count"), meta.get("dim"),
               meta.get("index_type"), meta.get("similarity"))}


def model_config_block() -> dict:
    """生成与检索侧的**定值**是否齐备（`config.FIXED` 逐项 `require_fixed()`）。"""
    try:
        values = {name: config.require_fixed(name) for name in sorted(config.FIXED)}
    except SystemExit as exc:
        return {"ok": False, "info": str(exc).splitlines()[0]}
    return {"ok": True,
            "info": "模型 %s／Prompt %s；K=%s N=%s 预算=%s g=%s"
            % (values["model_name"], values["prompt_version"], values["K"],
               values["N"], values["context_token_budget"], values["graph_retention_share"]),
            "model_name": values["model_name"],
            "prompt_version": values["prompt_version"],
            "K": values["K"], "N": values["N"],
            "context_token_budget": values["context_token_budget"],
            "graph_retention_share": values["graph_retention_share"]}


def health_payload() -> dict:
    """`/api/health` 的响应体：`{status, mysql, neo4j, vector_index, model_config}`。

    `status` = 四项全 `ok` 取 `"ok"`，否则 `"degraded"`。**HTTP 状态恒为 200**
    （服务本身活着；某一项不 ok 是依赖状态，不是接口失败）。
    """
    blocks = {"mysql": probe_mysql(), "neo4j": probe_neo4j(),
              "vector_index": probe_vector_index(), "model_config": model_config_block()}
    payload = {"status": "ok" if all(b["ok"] for b in blocks.values()) else "degraded"}
    payload.update(blocks)
    return payload


# ==========================================================================
# 4. 可选接口模块的注册
# ==========================================================================
def register_optional_routers(app: FastAPI) -> dict:
    """`api\\<name>.py` 存在且有 `router` 就挂上；不存在就记一行说明（不中断启动）。

    等价于《24》给的 `try: from api import qa, evidence, …` 写法，只是按模块逐个判定，
    粒度更细：某个模块没写好不会连带其余模块一起不注册。

    模块可**另带**一个可选的 `extra_routers`，形如 `[(router, 绝对前缀), …]`——用于挂载
    **不属于本前缀**但同属该模块的接口：`api\\qa.py` 的 `GET /api/config/meta`、
    `api\\evidence.py` 的 `GET /api/documents/{doc_id}/chunks/{chunk_id}` 都是表 4-13 里
    与该模块同批交付、却在另一个前缀下的路径。挂载时**按绝对前缀原样落位**（不拼接），
    这样路径与表 4-13 逐字一致。未提供该属性的模块不受影响。
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
# 5. 应用装配
# ==========================================================================
def create_app() -> FastAPI:
    errors.setup_logging()
    app = FastAPI(title=APP_TITLE, version=APP_VERSION)

    # 统一异常处理（errors.py 负责三类：ApiError／请求校验／未捕获）
    errors.install_exception_handlers(app)
    errors.register_request_id(app)

    # 中间件：先加的在**内层**，后加的在**外层**。CORS 放最外层，
    # 这样限流与校验生成的错误响应也带 CORS 头（否则前端只能看到「网络错误」）。
    app.add_middleware(RateLimitMiddleware,
                       window_seconds=config.RATE_LIMIT["window_seconds"],
                       max_requests=config.RATE_LIMIT["max_requests"],
                       exempt_paths={"/api/health"})
    app.add_middleware(GuardMiddleware, max_body_bytes=config.LIMITS["max_body_bytes"])
    app.add_middleware(CORSMiddleware,
                       allow_origins=list(config.CORS_ORIGINS),
                       allow_credentials=True,
                       allow_methods=["*"],
                       allow_headers=["*"])

    # 本批唯一注册的业务路由
    @app.get("/api/health", tags=["health"])
    async def health():
        """就绪探针（门禁 A5）：四项依赖的可用状态 ＋ 总体 status。

        本接口**不加统一响应信封**：表 4-13 未收录它，其响应体在《24》第 3.5 节被
        逐字规定为 `{status, mysql, neo4j, vector_index, model_config}`，故按字面返回，
        不套 `{data, meta}`。HTTP 状态恒为 200。
        """
        return JSONResponse(content=health_payload())

    # 可选注册（本批不存在这些模块，启动时打印说明）
    status = register_optional_routers(app)

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
    # 便于 `python 交付物/03-代码\后端\main.py` 直接起服务（与 run.py 等价，但固定 reload 关）
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=config.BACKEND_PORT, log_level="info")
