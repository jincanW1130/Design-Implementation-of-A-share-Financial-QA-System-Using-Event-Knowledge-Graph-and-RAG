# -*- coding: utf-8 -*-
"""V 组 · BM25 理论除零边界（独立审查 2026-10-19 P3）。

`LexicalIndex.avgdl` 只有在所有块内容都为空时才为 0；正常 build 产物此时也没有任何
posting，`search()` 会提前返回。但直接构造的索引（或未来数据形态变化）仍可能走到
长度归一化，故用 `avgdl or 1.0` 兜底；本文件钉住该边界不抛 ZeroDivisionError。
"""

from __future__ import annotations

import os
import sys
from array import array

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

lexical = _bootstrap.load_module("增强", "lexical_search.py")


def test_all_empty_chunks_have_zero_avgdl_and_search_empty():
    index = lexical.LexicalIndex.build([
        {"chunk_id": 1, "doc_id": 1, "content": ""},
        {"chunk_id": 2, "doc_id": 1, "content": None},
    ])
    assert index.avgdl == 0.0
    assert index.posting_count == 0
    assert index.search("任何问题", n=5) == []


def test_direct_index_with_zero_avgdl_does_not_divide_by_zero():
    """手工构造 avgdl=0 但存在 posting 的极端索引：必须返回有限分数而不是抛错。"""
    index = lexical.LexicalIndex(
        postings={"甲": array("I", [1])},      # index=0, tf=1
        chunk_ids=[1], doc_ids=[1], lengths=[0])
    assert index.avgdl == 0.0
    rows = index.search("甲", n=1)
    assert len(rows) == 1
    assert rows[0]["chunk_id"] == 1
    assert rows[0]["lexical_score"] > 0.0
