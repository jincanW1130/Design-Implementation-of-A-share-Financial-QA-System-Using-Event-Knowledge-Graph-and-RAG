# -*- coding: utf-8 -*-
"""代码\\后端\\params.py —— 接口层的**公共参数校验与解析工具**。

为什么单独成模块
----------------
第 2 轮重构前，同一套参数口径散在四个地方：

* `api\\graph.py` 与 `api\\history.py` 各写了一份 `_parse_int`；
* `api\\graph.py`／`api\\history.py`／`api\\admin.py`／`api\\market.py` 各自解析分页；
* `main.py` 的 `validate_question()` 被 `api\\qa.py`、`api\\admin.py` 用**延迟导入 main**
  的方式复用——路由层因此反过来依赖「应用装配模块」，既绕又容易循环导入。

本模块把这些**纯函数**收拢到一处：只依赖 `config` 与 `errors`，不依赖 FastAPI 的装配、
不依赖任何 service。`main.validate_question` 仍作为兼容别名保留（测试与既有调用方照旧），
但路由模块改为直接 `import params`，不再反向依赖 `main`。

口径约定
--------
* `text()`：`None → ""`，**不 strip**（与 `api\\graph.py` 原 `_s` 逐字一致；
  注意 `graph_service._s` 是 strip 版本，两者不可混用）。
* `parse_int()`：空串／缺失取默认值，非法值 → `ApiError(1002)`。
* `page_args()`：`page ≥ 1`、`page_size` 在区间内；可选 `page_max` 上界。
* `truthy()`：`1／true／yes／on`（大小写不敏感）为真，其余为假。
"""

from __future__ import annotations

import errors
import config


def text(value: object) -> str:
    """统一成字符串（`None → ""`），**不改变其余取值**（不 strip、不转大小写）。"""
    return "" if value is None else str(value)


def is_blank(raw: object) -> bool:
    """查询参数是否「缺失或只有空白」——用于「空串按缺省处理」的统一判断。"""
    return raw is None or text(raw).strip() == ""


def parse_int(raw: object, name: str, default: int | None = None) -> int | None:
    """查询参数取整数；空串／缺失取默认值，非法值抛 `ApiError(1002)`。"""
    if is_blank(raw):
        return default
    try:
        return int(text(raw).strip())
    except (TypeError, ValueError):
        raise errors.ApiError(1002, detail="%s 不是整数：%r" % (name, raw))


def page_args(page: object, page_size: object, *, page_size_max: int | None = None,
              default_page_size: int | None = None,
              page_max: int | None = None) -> tuple[int, int]:
    """分页参数统一校验，返回 `(page, page_size)`；非法 → `ApiError(1002)`。

    边界值缺省取 `config.API_LIMITS`（`page_size_max=200`、`default_page_size=20`），
    只在**取值来源不同**时才由调用方显式传入（例如历史接口另有 `page_max`）。
    """
    limits = config.API_LIMITS
    size_max = int(limits["page_size_max"] if page_size_max is None else page_size_max)
    default_size = int(limits["default_page_size"]
                       if default_page_size is None else default_page_size)

    page_no = parse_int(page, "page", default=1)
    if page_no is None or page_no < 1:
        raise errors.ApiError(1002, detail="page 必须是不小于 1 的整数：%r" % (page,))
    if page_max is not None and page_no > int(page_max):
        raise errors.ApiError(1002, detail="page 超过上限 %d：%r" % (int(page_max), page))

    size = parse_int(page_size, "page_size", default=default_size)
    if size is None or size < 1 or size > size_max:
        raise errors.ApiError(1002, detail="page_size 必须是 1～%d 的整数：%r"
                              % (size_max, page_size))
    return page_no, size


def truthy(raw: object) -> bool:
    """布尔开关：`1／true／yes／on`（大小写不敏感）为真，其余（含缺省）为假。"""
    return text(raw).strip().lower() in ("1", "true", "yes", "on")


def validate_question(raw: object) -> str:
    """校验问题文本，返回规范化后的字符串；不合规抛 `ApiError(1001)`。

    规则取自 `config.LIMITS`：去首尾空白后长度必须落在
    `[question_min_chars, question_max_chars]`（1～500）内。`detail` 只进日志。

    控制字符在入口拒绝：它们会落到文件路径／子进程参数上，曾触发
    `ValueError: embedded null character` → HTTP 500；保留 `\\t\\r\\n` 并折成单空格。
    """
    if raw is None or not isinstance(raw, str):
        raise errors.ApiError(1001, detail="question 缺失或不是字符串（type=%s）"
                              % type(raw).__name__)
    value = raw.strip()
    if any(ch < " " for ch in value if ch not in "\t\r\n") or "\x7f" in value:
        bad = next(ch for ch in value if (ch < " " and ch not in "\t\r\n") or ch == "\x7f")
        raise errors.ApiError(1001, detail="question 含控制字符（U+%04X）" % ord(bad))
    if any(ch in "\t\r\n" for ch in value):
        value = " ".join(value.split())
    lo = int(config.LIMITS["question_min_chars"])
    hi = int(config.LIMITS["question_max_chars"])
    if len(value) < lo:
        raise errors.ApiError(1001, detail="question 去空白后为空（长度 0 < %d）" % lo)
    if len(value) > hi:
        raise errors.ApiError(1001, detail="question 长度 %d 超出上限 %d" % (len(value), hi))
    return value
