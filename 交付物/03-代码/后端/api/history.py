# -*- coding: utf-8 -*-
"""代码\\后端\\api\\history.py —— 第 9 阶段历史记录接口（表 4-13 的两条）。

| 方法 | 路径 | 处理 | 错误码 |
| --- | --- | --- | --- |
| GET | `/api/history` | `qa_service.history_list` | 1002 |
| GET | `/api/history/{question_id}` | `qa_service.history_detail` | 1002／2001 |

会话隔离（FR-06）
-----------------
* 列表**强制**带 `session_id`：缺失即 `ApiError(1002)`（不是 1003——查询参数缺失按格式错误拒）。
* 回看**必须**带 `session_id` 且与记录一致：跨会话访问按 `ApiError(2001)` 拒
  （不用 4002 无权限：这里连「这条记录存在」都不该透露给对方会话）。

其它
----
* 分页 `page`／`page_size` 非法（非整数、小于 1、`page_size` 超过上限）→ 1002；
  查询参数一律按字符串收下再自行解析，以便把「缺失」与「非法」都归到 1002。
* **空列表不是错误**（硬约束 6）：无记录时回 HTTP 200 的空结果（`total=0`、`items=[]`）。
* 回看**不返回渲染后的图谱路径**，只回 `graph_path_available` 布尔值
  （【回顾只还原三表内容，不重新渲染图谱路径】）。
"""

from __future__ import annotations

import sys

from fastapi import APIRouter, Header

import config
import errors
import params
import services.qa_service as qa_service

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

router = APIRouter(tags=["history"])

PAGE_SIZE_MAX = int(config.API_LIMITS["page_size_max"])
"""`page_size` 上限（防止一次拉全表；取值登记在《25-文档更新登记》，第 2 轮收敛到 config）。"""

PAGE_MAX = int(config.API_LIMITS["page_max"])

SESSION_ID_MAX_CHARS = int(config.API_LIMITS["session_id_max_chars"])
"""`session_id` 上限：与 `question.session_id` 的 CHAR(36) 一致（取自 `config`）。"""
"""`page` 上限（2026-10-18 全面审查 A3 新增）。

审查实测：`page=999999999999999999999` 时 `(page-1)*page_size` 溢出成 10^21 量级，
拼进 `LIMIT` 变成非法 SQL（`near '19999999999999999999960'`），pymysql 抛
`ProgrammingError` → 未捕获 → **HTTP 500 ＋ 9999**。分页参数属「格式非法」，
按 **1002** 拒绝；同时给上界，避免任何超大偏移打到数据库。
"""


_parse_int = params.parse_int
"""查询参数取整数；空串／缺失取默认值，非法值抛 `ApiError(1002)`（实现见 `params`）。"""


def _page_args(page, page_size) -> tuple:
    """历史列表的分页口径：`page ≤ PAGE_MAX`、`1 ≤ page_size ≤ PAGE_SIZE_MAX`。"""
    return params.page_args(page, page_size, page_size_max=PAGE_SIZE_MAX,
                            default_page_size=int(config.API_LIMITS["default_page_size"]),
                            page_max=PAGE_MAX)


def _require_session_id(session_id: str | None) -> str:
    """`session_id` 是强制过滤条件；缺失／过长／非法一律 1002。"""
    if not isinstance(session_id, str) or not session_id.strip():
        raise errors.ApiError(1002, detail="缺少 session_id —— 历史记录按会话隔离（FR-06），"
                              "该参数为强制项")
    text = session_id.strip()
    if len(text) > SESSION_ID_MAX_CHARS:
        raise errors.ApiError(1002, detail="session_id 长度 %d 超过 %d（应为 UUID）"
                              % (len(text), SESSION_ID_MAX_CHARS))
    return text


@router.get("", responses=errors.error_responses(1002, 9999))
async def list_history(session_id: str | None = None, page: str | None = None,
                       page_size: str | None = None,
                       x_session_id: str | None = Header(default=None, alias="X-Session-Id")):
    """按会话分页列出历史问答（`ask_time` 倒序）；无记录 → HTTP 200 空结果。

    P3-6：会话标识同时接受 query 参数 `session_id` 与请求头 `X-Session-Id`（query 优先），
    与其它接口的鉴权头用法对齐；此前只认 query，带头会被误判为「缺少 session_id」返 1002。
    """
    sid = _require_session_id(session_id or x_session_id)
    page_no, size = _page_args(page, page_size)
    data = qa_service.history_list(sid, page_no, size)
    return errors.ok(data)


@router.get("/{question_id}", responses=errors.error_responses(1002, 2001, 9999))
async def history_detail(question_id: int, session_id: str | None = None,
                         x_session_id: str | None = Header(default=None, alias="X-Session-Id")):
    """回看一条历史问答（只还原三表内容，不重新渲染图谱路径）；跨会话／不存在 → 2001。

    P3-6：同列表接口，会话标识也接受 `X-Session-Id` 请求头（query 优先）。
    """
    sid = _require_session_id(session_id or x_session_id)
    return errors.ok(qa_service.history_detail(question_id, sid))
