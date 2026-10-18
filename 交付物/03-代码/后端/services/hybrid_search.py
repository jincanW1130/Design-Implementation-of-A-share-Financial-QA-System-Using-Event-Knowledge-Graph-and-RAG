# -*- coding: utf-8 -*-
"""代码\\后端\\services\\hybrid_search.py —— 关键词召回（工程增强，BM25）。

定位（先读）
------------
本服务把 `增强/lexical_search.py` 的纯标准库 BM25（中文 1～3 字符 n-gram）接到线上：

* **只读**加载 `数据集/v2.1/chunks/chunks.jsonl`（以及 `clean/documents.jsonl` 的标题），
  不写任何数据、不联网、不调用大模型；
* 索引**惰性构建一次**（进程内单例）：启动时不建，首次 `search()` 才建；构建耗时写日志；
* 构建／查询失败一律**降级为「不可用」**（返回空列表 + `index_ready=false`），
  不让接口层抛 500——关键词召回只是补充提示，不能影响主链路可用性。

口径
----
本服务属于**工程增强**，不在论文 A～E 实验口径内：不改变检索链路、不改实验读数。
`GET /api/search/keywords` 与 `POST /api/qa/ask` 空结果里的 `related_chunks` 都不是
证据链的一部分，前端须标注「工程增强，非正式证据」。

线程安全
--------
FastAPI 把同步路由放进线程池，首轮并发请求可能同时触发构建。`_LOCK` 保护构建与
状态切换；索引对象构建完成后只读，查询本身无锁。
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
import time

import config
import errors

logger = errors.logger

# --------------------------------------------------------------------------
# 常量（工程增强层的本地参数；不进入论文实验口径）
# --------------------------------------------------------------------------
SNIPPET_CHARS = 200
"""`snippet` 的最大字数（超出截断并加省略号；不回整块原文）。"""

LEXICAL_MODULE_PATH = os.path.join(config.CODE_DIR, "增强", "lexical_search.py")

# --------------------------------------------------------------------------
# 进程内单例状态
# --------------------------------------------------------------------------
_LOCK = threading.RLock()
_LEXICAL_MODULE = None

_INDEX = None
_INDEX_READY = False
_BUILD_ATTEMPTED = False
_BUILD_ERROR = None
_BUILD_SECONDS = None
_CHUNKS_BY_ID = {}          # chunk_id(int) -> content(str)，只用于生成 snippet
_TITLES = {}                # doc_id(int) -> title(str)
_STATS = {"chunks": 0, "postings": 0, "avgdl": 0.0}


def _load_lexical_module():
    """按文件路径加载增强层的 `lexical_search.py`（不占用裸名模块空间）。"""
    global _LEXICAL_MODULE
    with _LOCK:
        if _LEXICAL_MODULE is None:
            if not os.path.isfile(LEXICAL_MODULE_PATH):
                raise FileNotFoundError("关键词召回模块不存在：%s" % LEXICAL_MODULE_PATH)
            spec = importlib.util.spec_from_file_location(
                "_backend_enhancement_lexical_search", LEXICAL_MODULE_PATH)
            if spec is None or spec.loader is None:      # pragma: no cover - 极罕见
                raise ImportError("无法构造关键词召回模块规格：%s" % LEXICAL_MODULE_PATH)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _LEXICAL_MODULE = module
    return _LEXICAL_MODULE


def _iter_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def _load_titles() -> dict:
    """`doc_id -> title`（`documents.jsonl` 只读；缺文件时返回空表，不阻断召回）。"""
    titles = {}
    path = getattr(config, "DOCUMENTS_JSONL", "")
    if not path or not os.path.isfile(path):
        logger.warning("关键词召回：documents.jsonl 不存在，标题留空（%s）", path)
        return titles
    for row in _iter_jsonl(path):
        try:
            titles[int(row["doc_id"])] = str(row.get("title") or "")
        except (KeyError, TypeError, ValueError):
            continue
    return titles


def _build_index():
    """构建索引（调用方必须持有 `_LOCK`）。异常向上抛，由 `_ensure_index` 降级。"""
    global _INDEX, _INDEX_READY, _BUILD_ERROR, _BUILD_SECONDS
    global _CHUNKS_BY_ID, _TITLES, _STATS

    started = time.perf_counter()
    logger.info("关键词召回：开始构建 BM25 索引（%s）", config.CHUNKS_JSONL)
    lexical = _load_lexical_module()
    chunks = []
    contents = {}
    for row in _iter_jsonl(config.CHUNKS_JSONL):
        chunk_id = int(row["chunk_id"])
        chunks.append(row)
        contents[chunk_id] = str(row.get("content") or "")
    index = lexical.LexicalIndex.build(chunks)
    elapsed = time.perf_counter() - started

    _INDEX = index
    _CHUNKS_BY_ID = contents
    _TITLES = _load_titles()
    _STATS = {"chunks": index.total_chunks, "postings": index.posting_count,
              "avgdl": round(float(index.avgdl), 2)}
    _INDEX_READY = True
    _BUILD_ERROR = None
    _BUILD_SECONDS = round(elapsed, 3)
    logger.info("关键词召回：BM25 索引就绪｜块数=%d｜posting=%d｜avgdl=%.2f｜构建 %.3fs",
                _STATS["chunks"], _STATS["postings"], _STATS["avgdl"], _BUILD_SECONDS)


def _ensure_index():
    """惰性构建一次；成功返回索引，失败返回 `None`（此后不再重试，避免每次请求重试拖慢）。"""
    global _BUILD_ATTEMPTED, _BUILD_ERROR, _INDEX_READY
    if _INDEX_READY:
        return _INDEX
    with _LOCK:
        if _INDEX_READY:
            return _INDEX
        if _BUILD_ATTEMPTED:
            return None
        _BUILD_ATTEMPTED = True
        try:
            _build_index()
        except Exception as exc:                       # noqa: BLE001 - 失败即降级
            _INDEX_READY = False
            _BUILD_ERROR = "%s: %s" % (type(exc).__name__, exc)
            logger.warning("关键词召回不可用（构建失败，接口降级为空结果）：%s",
                           _BUILD_ERROR, exc_info=True)
            return None
        return _INDEX


def _snippet(text: str) -> str:
    """压缩空白并截断到约 `SNIPPET_CHARS` 字（不回整块原文）。"""
    flat = " ".join(str(text or "").split())
    if len(flat) <= SNIPPET_CHARS:
        return flat
    return flat[:SNIPPET_CHARS].rstrip() + "…"


def search(question: str, k: int = 5) -> list:
    """关键词召回：返回 `[{chunk_id, doc_id, title, snippet, score}]`。

    不可用（构建失败／参数异常／查询异常）一律返回 `[]`，**不抛异常**。
    结果按 BM25 分数降序（并列按 chunk_id 升序）。
    """
    try:
        limit = int(k)
    except (TypeError, ValueError):
        return []
    if limit < 1 or not str(question or "").strip():
        return []
    index = _ensure_index()
    if index is None:
        return []
    try:
        rows = index.search(question, limit)
    except Exception as exc:                           # noqa: BLE001 - 降级
        logger.warning("关键词召回查询失败（降级为空结果）：%s: %s",
                       type(exc).__name__, exc)
        return []
    items = []
    for row in rows:
        chunk_id = int(row["chunk_id"])
        doc_id = int(row["doc_id"])
        items.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "title": _TITLES.get(doc_id, ""),
            "snippet": _snippet(_CHUNKS_BY_ID.get(chunk_id, "")),
            "score": float(row.get("lexical_score") or 0.0),
        })
    return items


def index_ready() -> bool:
    """索引是否已就绪（未构建／构建失败均为 False；本函数不触发构建）。"""
    return bool(_INDEX_READY)


def status() -> dict:
    """可观测状态（供日志与测试；不进入响应体以外的任何存储）。"""
    return {
        "index_ready": bool(_INDEX_READY),
        "build_attempted": bool(_BUILD_ATTEMPTED),
        "build_seconds": _BUILD_SECONDS,
        "error": _BUILD_ERROR,
        **dict(_STATS),
    }


def reset() -> None:
    """清空进程内状态（**仅供测试**；线上不调用）。"""
    global _INDEX, _INDEX_READY, _BUILD_ATTEMPTED, _BUILD_ERROR, _BUILD_SECONDS
    global _CHUNKS_BY_ID, _TITLES, _STATS
    with _LOCK:
        _INDEX = None
        _INDEX_READY = False
        _BUILD_ATTEMPTED = False
        _BUILD_ERROR = None
        _BUILD_SECONDS = None
        _CHUNKS_BY_ID = {}
        _TITLES = {}
        _STATS = {"chunks": 0, "postings": 0, "avgdl": 0.0}
