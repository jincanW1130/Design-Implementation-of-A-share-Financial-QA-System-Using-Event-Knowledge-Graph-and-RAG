# -*- coding: utf-8 -*-
"""代码\\后端\\api\\evidence.py —— 第 9 阶段证据与原文接口（表 4-13 的三条）。

| 方法 | 路径 | 处理 | 错误码 |
| --- | --- | --- | --- |
| GET | `/api/evidence/{answer_id}` | `qa_service.evidence_of_answer` | 1002／2001 |
| GET | `/api/evidence/{answer_id}/graph-path` | `qa_service.graph_path_of_answer` | 2001 |
| GET | `/api/documents/{doc_id}/chunks/{chunk_id}` | `qa_service.chunk_detail` | 2001 |

三条纪律
--------
* **空证据不是错误**（硬约束 6／错误码表）：`answer_id` 存在但一条证据都没有时，
  照常返回 HTTP 200 的空结果（`items: []`、四类计数全 0），**不**回 2002 这样的错误码——
  2002 是**正常业务状态**，在响应体里以「空数据」表达，而非以错误码表达。
* **路径不重建**（硬约束 11／组 E）：`graph-path` 的 `paths` 直接解析
  `answer.graph_path` 的**落库原文**；未使用图谱扩展时 `display_mode = not_used`、`paths = null`。
* **原文不改写**：文本块内容照抄数据库（与上游 `chunks.jsonl` 一致），不截断、不摘要。

`/api/documents/...` 不在 `/api/evidence` 前缀下（表 4-13 如此），故本模块另外暴露
`extra_routers`，由 `main.register_optional_routers` 按绝对前缀挂载。
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

router = APIRouter(tags=["evidence"])
documents_router = APIRouter(tags=["documents"])

extra_routers = [(documents_router, "/api/documents")]

GROUP_BY_VALUES = ("evidence_type",)
"""`group_by` 的合法取值：按证据类型再分一次组（其余取值按 1002 拒）。"""


def _check_evidence_type(evidence_type: str | None) -> str | None:
    if evidence_type is None or evidence_type == "":
        return None
    if evidence_type not in qa_service.EVIDENCE_TYPES:
        raise errors.ApiError(1002, detail="evidence_type=%r 不在四类之内（%s）"
                              % (evidence_type, "、".join(qa_service.EVIDENCE_TYPES)))
    return evidence_type


def _check_group_by(group_by: str | None) -> str | None:
    if group_by is None or group_by == "":
        return None
    if group_by not in GROUP_BY_VALUES:
        raise errors.ApiError(1002, detail="group_by=%r 不是合法取值（%s）"
                              % (group_by, "、".join(GROUP_BY_VALUES)))
    return group_by


@router.get("/{answer_id}")
async def evidence_of_answer(answer_id: int, evidence_type: str | None = None,
                             group_by: str | None = None):
    """某条回答的证据：四类分组计数 ＋ 明细（含文档元数据）。不存在 → 2001；空 → 200。"""
    data = qa_service.evidence_of_answer(answer_id,
                                         evidence_type=_check_evidence_type(evidence_type),
                                         group_by=_check_group_by(group_by))
    return errors.ok(data)


@router.get("/{answer_id}/graph-path")
async def graph_path_of_answer(answer_id: int):
    """某条回答用的图谱路径：`is_graph_extended`／`paths`／`display_mode`。不存在 → 2001。"""
    return errors.ok(qa_service.graph_path_of_answer(answer_id))


@documents_router.get("/{doc_id}/chunks/{chunk_id}")
async def chunk_detail(doc_id: int, chunk_id: int):
    """文本块原文 ＋ 前后各两块 ＋ 所属文档元数据。不存在（或不属于该文档）→ 2001。"""
    return errors.ok(qa_service.chunk_detail(doc_id, chunk_id))
