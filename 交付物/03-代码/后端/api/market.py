# -*- coding: utf-8 -*-
"""代码\\后端\\api\\market.py —— 第 9 阶段「实时数据区」的四条只读接口。

| 方法 | 路径 | 处理 | 错误码 |
| --- | --- | --- | --- |
| GET | `/api/market/quote` | `market_service.quotes` | 1002 |
| GET | `/api/market/announcements` | `market_service.announcements` | 1002／1003 |
| GET | `/api/market/news` | `market_service.news` | 1002／1003 |
| GET | `/api/market/reports` | `market_service.corpus_reports`（**语料内近一周，无外部依赖**） | 1002 |

三条纪律
--------
* **只作展示、不进问答证据链**：四条接口全部只读、不写任何表，响应体带
  `"scope": "display_only"`；`data` 里的 `connected`／`reason` 供页面如实显示「未接入」。
  问答答案的口径仍是**冻结语料**（数据截止 `data_cutoff_time`），两者页面分开显示。
* **「未接入」不是错误**：外部源不可达时 `connected=false`，仍返回 **HTTP 200** ＋
  `errors.ok(...)` 信封——这与错误码 **2002**（查询结果为空是**正常业务状态**）同一语义，
  不用 4xx／5xx 表达。**绝不编造价格／涨跌幅／新闻**。
* **错误响应体键集合恰为 `{code, message}`**（`detail` 只进日志）：参数缺失＝1003、
  格式不合法＝1002，二者由本层在调服务前判掉（服务层对非法参数只会降级为「未接入」）。

接口**不在表 4-13 的 27 个之内**，属作者新增意见下的**新增接口**（连同 `/api/health`
一并**须在《25》登记为新增**）。
"""

from __future__ import annotations

import asyncio
import sys

from fastapi import APIRouter

import config
import errors
import services.market_service as market_service

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                                        # noqa: BLE001
            pass

logger = errors.logger

router = APIRouter(tags=["market"])

DEFAULT_PAGE_SIZE = 20
"""`page_size` 缺省值（各接口一致）。"""


def _check_codes(raw):
    """`codes` 逗号分隔；缺省取 `config` 的默认股列表；格式非法 → 1002。"""
    if raw is None or not str(raw).strip():
        return config.market_default_codes()
    parts = [p.strip() for p in str(raw).split(",") if p.strip()]
    if not parts:
        raise errors.ApiError(1002, detail="codes 为空（应为逗号分隔的证券代码）")
    for code in parts:
        try:
            config.secid_of(code)
        except ValueError:
            raise errors.ApiError(
                1002, detail="codes 里有非法证券代码 %r（应为 6 位数字，可带 sh／sz 前缀）" % code)
    return parts


def _check_code(raw):
    """`code` 必填（缺 → 1003）；格式非法 → 1002。"""
    if raw is None or not str(raw).strip():
        raise errors.ApiError(1003, detail="缺必填参数 code")
    code = str(raw).strip()
    try:
        config.secid_of(code)
    except ValueError:
        raise errors.ApiError(
            1002, detail="code=%r 非法（应为 6 位数字，可带 sh／sz 前缀）" % code)
    return code


def _check_days(raw):
    """`days` 只认 `config.MARKET_ZONE` 的 `days_min`～`days_max`（默认近一周），越界 → 1002。"""
    low = int(config.MARKET_ZONE["days_min"])
    high = int(config.MARKET_ZONE["days_max"])
    if raw is None or not str(raw).strip():
        return int(config.MARKET_ZONE["corpus_lookback_days"])
    try:
        days = int(str(raw).strip())
    except ValueError:
        raise errors.ApiError(1002, detail="days=%r 不是整数（合法区间 %d～%d）" % (raw, low, high))
    if days < low or days > high:
        raise errors.ApiError(1002, detail="days=%d 超出合法区间 %d～%d" % (days, low, high))
    return days


def _check_page_size(raw):
    """`page_size` 认 `config.MARKET_ZONE` 的 `page_size_min`～`page_size_max`；越界 → 1002。"""
    low = int(config.MARKET_ZONE["page_size_min"])
    high = int(config.MARKET_ZONE["page_size_max"])
    if raw is None or not str(raw).strip():
        return DEFAULT_PAGE_SIZE
    try:
        size = int(str(raw).strip())
    except ValueError:
        raise errors.ApiError(1002, detail="page_size=%r 不是整数（合法区间 %d～%d）"
                              % (raw, low, high))
    if size < low or size > high:
        raise errors.ApiError(1002, detail="page_size=%d 超出合法区间 %d～%d" % (size, low, high))
    return size


@router.get("/quote")
async def quote(codes: str | None = None):
    """实时行情（只作展示）。`codes` 缺省取 `config` 的默认股列表；格式非法 → 1002。"""
    return errors.ok(await asyncio.to_thread(market_service.quotes, _check_codes(codes)))


@router.get("/announcements")
async def announcements(code: str | None = None, days: str | None = None,
                        page_size: str | None = None):
    """个股公告（近 `days` 天；只作展示）。缺 `code` → 1003；`days` 只认 1～30，否则 1002。"""
    return errors.ok(await asyncio.to_thread(
        market_service.announcements, _check_code(code), _check_days(days),
        _check_page_size(page_size)))


@router.get("/news")
async def news(keyword: str | None = None, page_size: str | None = None):
    """个股新闻（只作展示）。缺 `keyword` → 1003。"""
    if keyword is None or not str(keyword).strip():
        raise errors.ApiError(1003, detail="缺必填参数 keyword")
    return errors.ok(await asyncio.to_thread(
        market_service.news, str(keyword).strip(), _check_page_size(page_size)))


@router.get("/reports")
async def reports(days: str | None = None, page_size: str | None = None):
    """**语料内**近一周文档（不依赖外部源；只作展示）。`days` 只认 1～30，否则 1002。"""
    return errors.ok(await asyncio.to_thread(
        market_service.corpus_reports, _check_days(days), _check_page_size(page_size)))
