# -*- coding: utf-8 -*-
"""代码\\后端\\api\\search.py —— 关键词召回接口（工程增强，**不在论文实验口径内**）。

| 方法 | 路径 | 处理 | 错误码 |
| --- | --- | --- | --- |
| GET | `/api/search/keywords` | `hybrid_search.search` | 1001／1002／1003 |

口径
----
* **工程增强**：BM25 关键词召回只作补充提示，不进入证据链、不改变 A～E 实验组读数；
* 空结果是 **HTTP 200 ＋ 空列表**（2002 语义），不是错误；
* `q` 必填（缺失 → 1003），长度／控制字符规则**复用** `params.validate_question`（→ 1001）；
* `k` 缺省 5、合法区间 1～20，越界或非整数 → 1002；
* 索引构建失败时 `data.items=[]` 且 `data.index_ready=false`（降级，不返回 500）。
"""

from __future__ import annotations

import sys
import time

from fastapi import APIRouter

import errors
import params
import services.hybrid_search as hybrid_search

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger

router = APIRouter(tags=["search"])

DEFAULT_K = 5
MIN_K = 1
MAX_K = 20


@router.get("/keywords", responses=errors.error_responses(1001, 1002, 1003))
def search_keywords(q: str | None = None, k: int = DEFAULT_K):
    """按关键词（BM25／字符 n-gram）召回原文块摘要。

    同步 `def`：FastAPI 放入线程池执行——首次请求会惰性构建索引（约 1～2 s），
    不阻塞事件循环。响应 `data` 为 `{items, total, took_ms, index_ready}`。
    """
    if q is None:
        raise errors.ApiError(1003, detail="必填查询参数 q 缺失（关键词召回应给出问题文本）")
    question = params.validate_question(q)

    if not isinstance(k, int) or isinstance(k, bool):
        raise errors.ApiError(1002, detail="k 必须是 1～%d 的整数：%r" % (MAX_K, k))
    if k < MIN_K or k > MAX_K:
        raise errors.ApiError(1002, detail="k 必须是 1～%d 的整数：%r" % (MAX_K, k))

    started = time.perf_counter()
    items = hybrid_search.search(question, k)
    took_ms = round((time.perf_counter() - started) * 1000.0, 2)
    return errors.ok({
        "items": items,
        "total": len(items),
        "took_ms": took_ms,
        "index_ready": hybrid_search.index_ready(),
    })
