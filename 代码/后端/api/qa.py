# -*- coding: utf-8 -*-
"""代码\\后端\\api\\qa.py —— 第 9 阶段问答接口（表 4-13 的三条）。

| 方法 | 路径 | 处理 | 错误码 |
| --- | --- | --- | --- |
| POST | `/api/qa/ask` | `qa_service.ask` | 1001／1002／1003／3001／3002／3003 |
| GET | `/api/qa/answers/{answer_id}` | `qa_service.get_answer` | 2001 |
| GET | `/api/config/meta` | `qa_service.config_meta` | — |

三条纪律（《24》第五节）
------------------------
* **硬约束 9**：`/api/qa/ask` 的请求体**只接受** `question` 与 `session_id`。出现
  `experiment_group`／`group`／`experiment`／`ab_group` 等**任何分组开关字段**，或任何
  未登记字段，一律 `ApiError(1002)` 拒——接口层不提供 A～E 组的切换入口，实验分组只在
  离线实验运行器里定。
* **硬约束 7**：错误响应体键集合恰为 `{code, message}`（`detail` 只进日志）；
  成功响应一律 `errors.ok(...)` 信封 `{data, meta}`。
* **参数校验复用**：问题文本用 `main.validate_question`（空／超长 → 1001），
  不在此处另写一份规则。

`/api/config/meta` 不在 `/api/qa` 前缀下（表 4-13 如此），故本模块另外暴露一个
`extra_routers`，由 `main.register_optional_routers` 按绝对前缀挂载——
模块化装配的钩子，见 `main.py` 同名函数的注释。
"""

from __future__ import annotations

import asyncio
import sys

from fastapi import APIRouter, Body

import config
import errors
import services.qa_service as qa_service

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger

router = APIRouter(tags=["qa"])
config_router = APIRouter(tags=["config"])

# 不在本模块前缀下的接口：`(路由器, 绝对前缀)`，由 main.register_optional_routers 挂载
extra_routers = [(config_router, "/api/config")]

ALLOWED_BODY_KEYS = frozenset({"question", "session_id"})
"""`/api/qa/ask` 允许出现的**全部**请求体字段（硬约束 9 的机检口径）。"""

GROUP_SWITCH_KEYS = frozenset({
    "group", "groups", "experiment_group", "experimentgroup", "group_id", "groupid",
    "ab_group", "abgroup", "ab", "exp_group", "experiment", "variant", "arm",
    "graph_depth", "time_filter", "evidence_sort", "retention_share", "g",
})
"""分组／试验开关字段名（小写去下划线后比对）——出现即 1002。"""

SESSION_ID_MAX_CHARS = 36
"""`session_id` 的上限：浏览器生成的 UUID 是 36 字符（`question.session_id` 为 CHAR(36)）。"""


def _normalized(name) -> str:
    """字段名归一：小写、去下划线与连字符（`Experiment-Group` 也该被认出来）。"""
    return str(name).strip().lower().replace("-", "").replace("_", "")


GROUP_SWITCH_KEYS_NORMALIZED = frozenset(_normalized(k) for k in GROUP_SWITCH_KEYS)


def _reject_switches(payload: dict) -> None:
    """硬约束 9：请求体里出现任何分组开关字段或未登记字段，一律 1002。"""
    unknown = [key for key in payload if key not in ALLOWED_BODY_KEYS]
    if not unknown:
        return
    switches = sorted(k for k in unknown if _normalized(k) in GROUP_SWITCH_KEYS_NORMALIZED)
    if switches:
        detail = ("请求体含分组／开关字段 %s —— 提问固定 C 组，接口层不提供 A～E 组切换"
                  "（硬约束 9）" % "、".join(switches))
    else:
        detail = ("请求体含未登记字段 %s —— 本接口只接受 %s"
                  % ("、".join(sorted(unknown)), "、".join(sorted(ALLOWED_BODY_KEYS))))
    raise errors.ApiError(1002, detail=detail)


def _validate_question(raw) -> str:
    """复用 `main.validate_question`（延迟导入：`main` 在装配期才 import 本模块）。"""
    import main                                  # noqa: PLC0415（避免装配期循环导入）
    return main.validate_question(raw)


@router.post("/ask")
async def ask(payload: dict | None = Body(default=None)):
    """提问：跑一次问答链路并落库，返回表 4-13 规定的九项载荷。"""
    if not isinstance(payload, dict):
        raise errors.ApiError(1003, detail="请求体必须是 JSON 对象，收到 %s"
                              % type(payload).__name__)
    _reject_switches(payload)

    question = _validate_question(payload.get("question"))
    session_id = payload.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise errors.ApiError(1003, detail="session_id 缺失或不是非空字符串（第一版由前端生成 UUID）")
    session_id = session_id.strip()
    if len(session_id) > SESSION_ID_MAX_CHARS:
        raise errors.ApiError(1002, detail="session_id 长度 %d 超过 %d（应为 UUID）"
                              % (len(session_id), SESSION_ID_MAX_CHARS))

    # 固定 C 组：分组取自检索侧 config 的 DEFAULT_GROUP，不由请求体决定（硬约束 9）。
    # 链路是同步阻塞调用（10～30 s），放到工作线程，避免堵住事件循环。
    data = await asyncio.to_thread(qa_service.ask, question, session_id, config.DEFAULT_GROUP)
    return errors.ok(data)


@router.get("/answers/{answer_id}")
async def get_answer(answer_id: int):
    """按 `answer_id` 取回回答（含证据与图谱路径）；不存在 → 2001。"""
    return errors.ok(qa_service.get_answer(answer_id))


@config_router.get("/meta")
async def config_meta():
    """当前生效的只读口径（数据集版本／截止时间／Prompt 版本／K／N／预算／模型名）。"""
    return errors.ok(qa_service.config_meta())
