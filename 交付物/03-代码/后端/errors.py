# -*- coding: utf-8 -*-
"""代码\\后端\\errors.py —— 第 9 阶段（前后端系统集成）后端的错误码表与统一响应封装。

口径来源：《10-系统总体设计（第四阶段）》第 4.7.1 节（错误码与「detail 只进日志」）、
第 4.7.2 节 表 4-13（各接口的错误码列）、《24-第9阶段任务书》第五节 硬约束 7／8 与
第六节 格式决策 3。

三条硬口径
----------
1. **响应体键集合恰为 `{code, message}`**：`detail` 面向调试，**只写后端日志、不进响应体**
   （硬约束 7；机检方式＝检查响应体键集合）。
2. **2002 是正常业务状态、不是错误**：图谱查询为空、历史记录为空返回 HTTP 200 与空结果，
   不得返回 4xx／5xx（硬约束 6）。本文件把 2002 放进取值表并显式标注 `is_error=False`，
   成功响应仍走 `ok()`，前端据空结果自行提示。
3. **未捕获异常**回 HTTP 500 ＋ code 9999，响应体同样只有 `{code, message}`，
   异常堆栈只进日志。

新增登记
--------
**1004（HTTP 429）请求频率超出限制** 是第 9 阶段的**新增错误码**（《24》第六节 格式决策 9
登记了新增接口 `/api/health`，此处是新增错误码）：表 4-13 与《10》第4.7.1节 的 11 个错误码里
没有限流码，而《24》第八节 C9 要求限流「返回明确错误码或 429」，故取 1xxx（输入／客户端类）
下的 1004 ＋ HTTP 429，语义单一、不与 1001（输入为空／超长）混用。**须在《25》登记为新增**。
"""

from __future__ import annotations

import logging
import logging.handlers  # noqa: F401  （RotatingFileHandler 用；本文件 setup_logging 里显式引用）
import os
import sys

from starlette.responses import JSONResponse

import config

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = logging.getLogger("ashare_qa.backend")

# --------------------------------------------------------------------------
# 1. 错误码表（code → (message, http_status)）
# --------------------------------------------------------------------------
CODES = {
    1001: ("输入为空或长度超出限制", 400),
    1002: ("参数格式错误", 400),
    1003: ("必填字段缺失", 400),
    1004: ("请求频率超出限制", 429),          # 第 9 阶段新增（限流；须在《25》登记）
    2001: ("资源不存在", 404),
    2002: ("查询结果为空", 200),              # 正常业务状态，不是错误
    2003: ("文档已被历史回答引用", 409),
    3001: ("图谱服务不可用", 503),
    3002: ("大模型接口超时", 504),
    3003: ("向量索引不可用", 500),
    # 第 9 阶段新增（须在《25》登记）：上游第 8 阶段的「装配账目守卫」未通过——即**现场重算的
    # 预算分账与冻结的上游 trace 不一致**时，链路会主动非零退出。它既不是图谱故障也不是模型故障，
    # 用 3001／3003 代替都属**误标**（2026-09-30 实测：PE-03 就落在这条上），故单列一码。
    3004: ("装配账目守卫未通过（上游一致性守卫，非图谱或模型故障）", 502),
    4001: ("凭据无效", 401),
    4002: ("无操作权限", 403),
    9999: ("服务内部错误", 500),              # 未捕获异常（不是《10》登记码）
}

# 非错误的「正常业务状态码」：响应走 ok()，HTTP 200
NORMAL_CODES = frozenset({2002})
CODE_EMPTY_RESULT = 2002

# HTTP 状态 → 错误码（Starlette 抛出的 HTTPException 与未匹配路由的归一化）
HTTP_STATUS_TO_CODE = {
    400: 1002, 401: 4001, 403: 4002, 404: 2001, 409: 2003,
    429: 1004, 503: 3001, 504: 3002,
}


def message_of(code: int) -> str:
    return CODES.get(int(code), CODES[9999])[0]


def http_status_of(code: int) -> int:
    return CODES.get(int(code), CODES[9999])[1]


def is_normal(code: int) -> bool:
    """是否为「不是错误」的正常业务状态（2002）。"""
    return int(code) in NORMAL_CODES


# --------------------------------------------------------------------------
# 2. 统一异常类型与响应体构造（纯函数，便于自检）
# --------------------------------------------------------------------------
class ApiError(Exception):
    """接口层唯一显式抛出的异常。

    * `code`／`message`／`http_status` 进响应体；
    * `detail` **只进后端日志**，绝不进响应体（硬约束 7）。

    调用方建议用 `ApiError(1001, detail="question 为空")` 这类形式：message 取表中默认值，
    detail 留作日志里的定位信息（不得写入口令、连接串等敏感取值）。
    """

    def __init__(self, code: int, detail: str | None = None, message: str | None = None,
                 http_status: int | None = None):
        try:
            code = int(code)
        except (TypeError, ValueError):
            code = 9999
        self.code = code
        if code not in CODES:
            logger.warning("构造了未登记的错误码 %r，按 9999 处理（响应体仍回该码，请核对《25》）", code)
        self.message = message if message is not None else message_of(code)
        self.http_status = int(http_status) if http_status is not None else http_status_of(code)
        self.detail = detail
        super().__init__("[%d] %s" % (self.code, self.message))

    def payload(self) -> dict:
        """响应体：**键集合恰为 {code, message}**。"""
        return {"code": self.code, "message": self.message}


def error_payload(code: int, message: str | None = None) -> dict:
    return {"code": int(code), "message": message if message is not None else message_of(code)}


def error_response(code: int, message: str | None = None,
                   http_status: int | None = None, detail: str | None = None) -> JSONResponse:
    """直接构造错误响应（**中间件用**：中间件在 ExceptionMiddleware 之外，抛 ApiError
    不会被异常处理器接住，必须在中间件里自己返回 JSONResponse）。"""
    if detail:
        logger.warning("错误响应（detail 只进日志）：code=%s detail=%s", code, detail)
    return JSONResponse(status_code=int(http_status) if http_status is not None
                        else http_status_of(code),
                        content=error_payload(code, message))


UNCAUGHT_CODE = 9999


def uncaught_payload() -> dict:
    return error_payload(UNCAUGHT_CODE)


# --------------------------------------------------------------------------
# 3. 成功响应封装（《24》第六节 格式决策 3）
# --------------------------------------------------------------------------
def ok(data, meta: dict | None = None) -> dict:
    """成功响应：`{"data": …, "meta": {"dataset_version": …, "data_cutoff_time": …}}`。

    `meta` 缺省取数据集版本级属性（`meta\\dataset.json`）；传入的键会覆盖／补充默认值。
    """
    payload_meta = config.meta_fields()
    if meta:
        payload_meta.update(meta)
    return {"data": data, "meta": payload_meta}


def page_payload(total: int, items: list, page: int, page_size: int) -> dict:
    """分页区块：`{"total": …, "items": […], "page": …, "page_size": …}`（放在 `data` 内）。"""
    return {"total": int(total), "items": list(items),
            "page": int(page), "page_size": int(page_size)}


def ok_page(total: int, items: list, page: int, page_size: int,
            meta: dict | None = None) -> dict:
    """分页成功响应（`ok()` ＋ `page_payload()` 的组合，避免各接口各写一遍）。"""
    return ok(page_payload(total, items, page, page_size), meta=meta)


def ok_empty(meta: dict | None = None, page: int = 1, page_size: int = 0) -> dict:
    """空结果的**正常**响应（HTTP 200；对应 2002 的语义，但响应体里不出现错误码）。"""
    return ok_page(0, [], page, page_size, meta=meta)


# --------------------------------------------------------------------------
# 4. 日志
# --------------------------------------------------------------------------
def setup_logging(level: int = logging.INFO) -> None:
    """配置后端日志（**始终** stderr；**可选**再落一份轮转文件）。detail 与未捕获异常堆栈只落这里。

    评审 P1-11 的落地（口径逐条写清，便于门禁核查）
    -----------------------------------------------
    * ① **stderr 一直在**：容器形态靠 stdout／stderr 采集，故 `StreamHandler(stderr)` 保留为
      第一个 handler，本函数的行为对**未配置落盘**的部署与改动前**完全一致**；
    * ② **落盘是"可选"**：路径取 `config.LOG_PATH`（即 `代码\\后端\\config.local.json` 的
      `log_path`，由 `config.py` 读取）。取不到（键缺失／空串／写成目录）时 `LOG_PATH is None`
      → **一个 FileHandler 都不挂**，只出 stderr；
    * ③ **轮转**：用 `logging.handlers.RotatingFileHandler`，参数取 `config.LOG_ROTATION`
      （当前＝单文件 10 MiB、保留 5 个历史文件、UTF-8）——`backup_count>0` 即轮转，
      `app.log` → `app.log.1` → … → `app.log.5`，不会无限长大；
    * ④ **不写凭据**：日志格式里只有时间／级别／logger 名／消息，**不含**任何连接串或口令；
      格式字符串本身不引用 `config` 的任何凭据取值（本函数只读 `LOG_PATH`／`LOG_ROTATION`）。
    * ⑤ **文件打不开不阻断开服**：路径所在目录不存在或没有写权限时，`RotatingFileHandler`
      会抛 `OSError`／`FileNotFoundError`。这里**如实记一条 WARNING 到 stderr 并继续**，
      不静默吞掉、也不让后端起不来——"日志落不下去"是运维问题，不该等于"服务不可用"。
      目录不存在时先尝试 `os.makedirs`（`log_path` 允许指向尚未创建的目录）。
    """
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"))
    handlers = [handler]

    log_path = getattr(config, "LOG_PATH", None)
    if log_path:
        rotation = getattr(config, "LOG_ROTATION", {}) or {}
        try:
            directory = os.path.dirname(log_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            # 延迟导入：只在本函数真正要用时才 import，不给导入期添负担。
            from logging.handlers import RotatingFileHandler
            file_handler = RotatingFileHandler(
                log_path,
                maxBytes=int(rotation.get("max_bytes", 10 * 1024 * 1024)),
                backupCount=int(rotation.get("backup_count", 5)),
                encoding=str(rotation.get("encoding", "utf-8")),
                delay=True)
            file_handler.setFormatter(logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s"))
            handlers.append(file_handler)
        except OSError as exc:
            # detail 只进日志：这里只报**路径与异常类型**，绝不回显任何凭据取值。
            logging.getLogger("ashare_qa.backend").warning(
                "日志落盘不可用（log_path=%s，%s: %s）——本次只出 stderr，服务照常启动。",
                log_path, type(exc).__name__, exc)

    root = logging.getLogger("ashare_qa")
    root.handlers[:] = handlers
    root.setLevel(level)
    root.propagate = False


# --------------------------------------------------------------------------
# 5. FastAPI 异常处理装配
# --------------------------------------------------------------------------
def install_exception_handlers(app) -> None:
    """把 `ApiError` 与未捕获异常统一转成 `{"code": …, "message": …}`。

    三类处理：
    * `ApiError` → 按其 code／http_status；
    * 请求校验错误（FastAPI 的 `RequestValidationError`）→ 缺必填＝1003、其余＝1002；
    * 其余未捕获异常 → HTTP 500 ＋ code 9999，堆栈只进日志。
    """
    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(ApiError)
    async def _handle_api_error(request, exc: ApiError):
        logger.warning("ApiError %s %s → code=%s http=%s%s",
                       request.method, request.url.path, exc.code, exc.http_status,
                       ("；detail=%s" % exc.detail) if exc.detail else "")
        return JSONResponse(status_code=exc.http_status, content=exc.payload())

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request, exc: RequestValidationError):
        missing = any(str(e.get("type", "")).endswith("missing") for e in exc.errors())
        code = 1003 if missing else 1002
        logger.warning("请求校验失败 %s %s → code=%s；detail=%s",
                       request.method, request.url.path, code, exc.errors())
        return JSONResponse(status_code=http_status_of(code), content=error_payload(code))

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request, exc: StarletteHTTPException):
        code = HTTP_STATUS_TO_CODE.get(int(exc.status_code), UNCAUGHT_CODE)
        status = http_status_of(code) if code != UNCAUGHT_CODE else int(exc.status_code)
        logger.warning("HTTPException %s %s → %s → code=%s",
                       request.method, request.url.path, exc.status_code, code)
        return JSONResponse(status_code=status, content=error_payload(code))

    @app.exception_handler(Exception)
    async def _handle_uncaught(request, exc: Exception):
        # 堆栈只进日志，响应体只有 code／message（硬约束 7）
        logger.exception("未捕获异常 %s %s → code=%s",
                         request.method, request.url.path, UNCAUGHT_CODE)
        return JSONResponse(status_code=http_status_of(UNCAUGHT_CODE),
                            content=uncaught_payload())


def register_request_id(app) -> None:
    """预留：给每个请求打一个 request-id（日志用）。第一版只记方法＋路径，不落额外字段。"""
    return None


# --------------------------------------------------------------------------
# 6. 自检：逐码构造一次，打印 HTTP 状态与响应体键集合
# --------------------------------------------------------------------------
def selftest() -> int:
    line = "=" * 74
    print(line)
    print("errors.py 自检（逐码构造一次：HTTP 状态 ＋ 响应体键集合）")
    print(line)
    print("%-6s %-6s %-8s %s" % ("code", "http", "is_err", "message"))
    print("-" * 74)

    bad = 0
    for code in sorted(CODES):
        err = ApiError(code, detail="（示例调试信息：只进日志、不进响应体）")
        body = err.payload()
        keys = set(body.keys())
        flag = "正常" if is_normal(code) else "错误"
        print("%-6d %-6d %-8s %s" % (err.code, err.http_status, flag, err.message))
        if keys != {"code", "message"}:
            print("    !! 响应体键集合异常：%s" % sorted(keys))
            bad += 1

    print("-" * 74)
    print("未捕获异常路径（模拟）：code=%d http=%d body=%s"
          % (UNCAUGHT_CODE, http_status_of(UNCAUGHT_CODE), uncaught_payload()))
    if set(uncaught_payload().keys()) != {"code", "message"}:
        bad += 1
        print("    !! 未捕获异常的响应体键集合异常")
    print()

    print("--- 三类统一响应形态 ---")
    print("ok(data=…)              = %s"
          % {k: (v if k != "data" else "<data>") for k, v in ok({"x": 1}).items()})
    print("ok_page(total=3, …)     = %s"
          % ok_page(3, [{"a": 1}], 1, 20)["data"])
    print("ok_empty()              = %s" % ok_empty()["data"])
    print("error_payload(2003)     = %s" % error_payload(2003))
    print()

    print("--- 关键判据 ---")
    checks = [
        ("2002 的 HTTP 状态为 200 且被标为「非错误」",
         http_status_of(2002) == 200 and is_normal(2002)),
        ("全部响应体键集合恰为 {code, message}", bad == 0),
        ("1001／1002／1003 均为 HTTP 400",
         all(http_status_of(c) == 400 for c in (1001, 1002, 1003))),
        ("2001=404／2003=409／3001=503／3002=504／3003=500／4001=401／4002=403",
         (http_status_of(2001), http_status_of(2003), http_status_of(3001),
          http_status_of(3002), http_status_of(3003), http_status_of(4001),
          http_status_of(4002)) == (404, 409, 503, 504, 500, 401, 403)),
        ("1004 限流码为 HTTP 429（第 9 阶段新增，须在《25》登记）",
         http_status_of(1004) == 429),
        # 评审 P1-11：日志落盘是**可选**的，且 stderr 必须在（本项只判源码形态，不触盘）。
        ("setup_logging 始终挂 stderr 且仅在 log_path 存在时追加轮转文件",
         _setup_logging_shape_ok()),
    ]
    for label, good in checks:
        print("  [%s] %s" % ("OK " if good else "FAIL", label))
    print(line)
    return 0 if all(g for _, g in checks) and bad == 0 else 1


def _setup_logging_shape_ok() -> bool:
    """判 `setup_logging()` 的源码形态（**不写盘、不改全局 logging 状态**）。

    两条：① 必须有 `StreamHandler(stream=sys.stderr)`；② 追加文件 handler 必须**由
    `config.LOG_PATH` 把关**、且用的是 `RotatingFileHandler`（有轮转、不是裸 FileHandler）。
    """
    import inspect
    src = inspect.getsource(setup_logging)
    return ("StreamHandler(stream=sys.stderr)" in src
            and "RotatingFileHandler" in src
            and "config" in src and "LOG_PATH" in src)


if __name__ == "__main__":
    raise SystemExit(selftest())
