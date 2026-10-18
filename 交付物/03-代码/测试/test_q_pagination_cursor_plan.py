# -*- coding: utf-8 -*-
"""Q 组 · 历史列表「游标分页方案」的语义单测（第三轮 9.x）。

现状（不粉饰）：`qa_service.history_list()` 仍用 `LIMIT %s OFFSET %s`，游标分页**尚未接入
接口**；方案见 `交付物/05-系统实现/性能与架构优化方案.md` 第 1.3 节第 5 条：
按 `(ask_time, question_id)` 做键集分页，游标是 base64 的 `ask_time|question_id`，
`WHERE (ask_time, question_id) < (上一页最后一行)`，`ORDER BY ask_time DESC, question_id DESC`。

本组不新增产品代码，只把该方案的**关键语义**钉住，供将来切换时回归：

* 游标编解码可往返，坏游标必须显式失败（不能静默退化成首页）；
* 在 `ask_time` 大量相同的合成数据上，键集分页与 OFFSET 分页给出**同一顺序、无重无漏**；
* 必须用 `(ask_time, question_id)` 复合键——只按 `ask_time` 会在同秒记录上重复/跳过。
"""

from __future__ import annotations

import base64
import binascii

import pytest


def encode_cursor(ask_time: str, question_id: int) -> str:
    raw = "%s|%d" % (ask_time, int(question_id))
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> tuple[str, int]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii") + b"=" * (-len(cursor) % 4))
        text = raw.decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("游标不是合法的 base64 文本") from exc
    parts = text.split("|")
    if len(parts) != 2:
        raise ValueError("游标必须恰为 ask_time|question_id 两段")
    ask_time, qid = parts
    if not ask_time.strip():
        raise ValueError("游标缺少 ask_time")
    try:
        question_id = int(qid)
    except ValueError as exc:
        raise ValueError("游标里的 question_id 不是整数") from exc
    if question_id <= 0:
        raise ValueError("游标里的 question_id 必须为正数")
    return ask_time, question_id


def keyset_page(rows: list, cursor: tuple[str, int] | None, limit: int) -> tuple[list, str | None]:
    """按方案 SQL 的语义取一页，返回 (本页行, 下一页游标或 None)。"""
    ordered = sorted(rows, key=lambda r: (r["ask_time"], r["question_id"]), reverse=True)
    if cursor is not None:
        ordered = [r for r in ordered if (r["ask_time"], r["question_id"]) < cursor]
    page = ordered[:limit]
    next_cursor = (encode_cursor(page[-1]["ask_time"], page[-1]["question_id"])
                   if len(ordered) > limit else None)
    return page, next_cursor


def _rows():
    # 刻意让 3 组记录共享同一 ask_time，验证复合键的稳定性
    return [
        {"question_id": 1, "ask_time": "2026-10-01 10:00:00"},
        {"question_id": 2, "ask_time": "2026-10-01 10:00:00"},
        {"question_id": 3, "ask_time": "2026-10-01 10:00:00"},
        {"question_id": 4, "ask_time": "2026-10-01 09:00:00"},
        {"question_id": 5, "ask_time": "2026-10-01 09:00:00"},
        {"question_id": 6, "ask_time": "2026-10-01 08:00:00"},
        {"question_id": 7, "ask_time": "2026-10-01 07:00:00"},
        {"question_id": 8, "ask_time": "2026-10-01 06:00:00"},
    ]


def test_cursor_roundtrip_and_rejects_bad_values():
    cursor = encode_cursor("2026-10-01 10:00:00", 31)
    assert decode_cursor(cursor) == ("2026-10-01 10:00:00", 31)
    for bad in ("", "not-base64!!", base64.urlsafe_b64encode(b"only-one").decode(),
                base64.urlsafe_b64encode(b"2026-10-01|abc").decode(),
                base64.urlsafe_b64encode(b"2026-10-01|0").decode()):
        with pytest.raises(ValueError):
            decode_cursor(bad)


def test_keyset_walk_matches_offset_pages_without_gaps_or_duplicates():
    rows = _rows()
    expected = [r["question_id"] for r in
                sorted(rows, key=lambda r: (r["ask_time"], r["question_id"]), reverse=True)]
    walked, cursor = [], None
    for _ in range(10):                       # 上限防止坏实现死循环
        page, cursor = keyset_page(rows, decode_cursor(cursor) if cursor else None, 3)
        walked.extend(r["question_id"] for r in page)
        if cursor is None:
            break
    assert walked == expected, "键集分页必须与 OFFSET 顺序一致"
    assert len(walked) == len(set(walked)) == len(rows), "不得重复、不得漏行"


def test_single_column_cursor_would_lose_rows_on_equal_timestamps():
    rows = _rows()
    same_time = [r for r in rows if r["ask_time"] == "2026-10-01 10:00:00"]
    assert len(same_time) == 3
    # 只按 ask_time 过滤：取完第一条后，余下两条会被 `< 10:00:00` 一并排除
    naive_after = [r["question_id"] for r in
                   sorted(rows, key=lambda r: r["ask_time"], reverse=True)
                   if r["ask_time"] < "2026-10-01 10:00:00"]
    assert 3 not in naive_after and 2 not in naive_after, \
        "这正是必须用 (ask_time, question_id) 复合键的原因"
    page, next_cursor = keyset_page(rows, decode_cursor(encode_cursor(
        "2026-10-01 10:00:00", 3)), 3)
    assert [r["question_id"] for r in page] == [2, 1, 5], \
        "复合键应严格接在 (10:00:00, 3) 之后，既不重复 3 也不跳过 2"
    assert next_cursor is not None
