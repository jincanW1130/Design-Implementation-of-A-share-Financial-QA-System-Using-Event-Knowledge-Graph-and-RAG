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

from fastapi import APIRouter

import errors
import services.qa_service as qa_service

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

router = APIRouter(tags=["history"])

PAGE_SIZE_MAX = 200
"""`page_size` 上限（防止一次拉全表；取值登记在《25-文档更新登记》）。"""


def _parse_int(raw, name: str, default: int | None = None) -> int | None:
    """查询参数取整数；空串／缺失取默认值，非法值抛 `ApiError(1002)`。"""
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        raise errors.ApiError(1002, detail="%s 不是整数：%r" % (name, raw))


def _require_session_id(session_id: str | None) -> str:
    """`session_id` 是强制过滤条件；缺失／过长／非法一律 1002。"""
    if not isinstance(session_id, str) or not session_id.strip():
        raise errors.ApiError(1002, detail="缺少 session_id —— 历史记录按会话隔离（FR-06），"
                              "该参数为强制项")
    text = session_id.strip()
    if len(text) > 36:
        raise errors.ApiError(1002, detail="session_id 长度 %d 超过 36（应为 UUID）" % len(text))
    return text


@router.get("")
async def list_history(session_id: str | None = None, page: str | None = None,
                       page_size: str | None = None):
    """按会话分页列出历史问答（`ask_time` 倒序）；无记录 → HTTP 200 空结果。"""
    sid = _require_session_id(session_id)
    page_no = _parse_int(page, "page", default=1)
    if page_no is None or page_no < 1:
        raise errors.ApiError(1002, detail="page 必须是不小于 1 的整数：%r" % page)
    size = _parse_int(page_size, "page_size", default=20)
    if size is None or size < 1 or size > PAGE_SIZE_MAX:
        raise errors.ApiError(1002, detail="page_size 必须是 1～%d 的整数：%r"
                              % (PAGE_SIZE_MAX, page_size))
    data = qa_service.history_list(sid, page_no, size)
    return errors.ok(data)


@router.get("/{question_id}")
async def history_detail(question_id: int, session_id: str | None = None):
    """回看一条历史问答（只还原三表内容，不重新渲染图谱路径）；跨会话／不存在 → 2001。"""
    sid = _require_session_id(session_id)
    return errors.ok(qa_service.history_detail(question_id, sid))
