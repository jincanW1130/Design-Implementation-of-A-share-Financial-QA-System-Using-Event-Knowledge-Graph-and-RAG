# -*- coding: utf-8 -*-
"""N 组 · 低覆盖模块的**纯函数**补测（第 10 轮新增）。

只挑"输入 → 输出"完全确定、无网络／无数据库的纯函数，不连接任何外部依赖：

* `后端\\services\\market_service.py`：`_num`／`_strip_jsonp`／`_clean`／`_quote_item`／
  `_short_reason`／`_secid_args`／`_envelope`。重点是两条硬口径——**不编造数字**、
  **未接入原因不泄漏 URL**。
* `后端\\db.py`：`split_sql`（DDL 切分）与 `describe_target`（**绝不含口令**）。

这些断言验证行为契约，不是为覆盖率凑行数。
"""

from __future__ import annotations

import os
import socket
import sys
import urllib.error

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

market = _bootstrap.load_backend("services.market_service")
db = _bootstrap.load_backend("db")
backend_cfg = _bootstrap.component_config("后端")


# ---------------------------------------------------------------------------
# market_service：数值解析不编造 0
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value, expected", [
    (None, None), (True, None), (False, None),
    ("", None), ("-", None), ("--", None), ("null", None), ("None", None),
    ("  ", None), ("abc", None),
    (0, 0), (3, 3), (1.25, 1.25), ("2.5", 2.5), (" -3.75 ", -3.75),
])
def test_market_num_never_invents_zero(value, expected):
    assert market._num(value) == expected


# ---------------------------------------------------------------------------
# market_service：JSONP 外壳与高亮清洗
# ---------------------------------------------------------------------------
def test_market_strip_jsonp_accepts_plain_and_wrapped_objects():
    assert market._strip_jsonp('{"a": 1}') == {"a": 1}
    assert market._strip_jsonp('cb({"a": 2});') == {"a": 2}
    assert market._strip_jsonp('  callback ( {"a": 3} ) ;  ') == {"a": 3}


@pytest.mark.parametrize("text", ["", "not json", "[]", "null", "cb()"])
def test_market_strip_jsonp_rejects_non_object_bodies(text):
    with pytest.raises(ValueError):
        market._strip_jsonp(text)


def test_market_clean_removes_em_tags_only():
    assert market._clean("<em>贵州</em>茅台 <EM>公告</EM>") == "贵州茅台 公告"
    assert market._clean(None) == ""
    assert market._clean("  原文  ") == "原文"


# ---------------------------------------------------------------------------
# market_service：行情行映射与 secid 归一化（非法项不猜）
# ---------------------------------------------------------------------------
def test_market_quote_item_maps_fields_and_keeps_missing_as_none():
    row = {"f12": "600519", "f14": "贵州茅台", "f2": "1680.5",
           "f3": "-0.42", "f4": "-7.1", "f6": "-"}
    assert market._quote_item(row) == {
        "code": "600519", "name": "贵州茅台", "price": 1680.5,
        "change_pct": -0.42, "change": -7.1, "amount": None}
    assert market._quote_item({"f14": "缺代码"}) is None
    assert market._quote_item(["not", "a", "dict"]) is None


def test_market_secid_args_normalizes_and_reports_bad_without_guessing():
    secids, bad = market._secid_args(["600519", "sz000001", "sh600000", "bad", "12345"])
    assert secids == "1.600519,0.000001,1.600000"
    assert bad == ["bad", "12345"], "非法项必须原样报告，不得猜测市场"


# ---------------------------------------------------------------------------
# market_service：未接入原因简短、不含 URL；响应 scope 恒为 display_only
# ---------------------------------------------------------------------------
def test_market_short_reason_is_short_and_never_leaks_url():
    url = "http://10.0.0.8:8080/secret?token=abc"
    cases = [
        (urllib.error.HTTPError(url, 503, "boom", None, None), "HTTP 503"),
        (socket.timeout("timed out"), "超时"),
        (urllib.error.URLError("unreachable"), "不可达"),
        (ValueError("bad json"), "无法解析"),
        (KeyError("missing"), "无法解析"),
        (RuntimeError("boom"), "RuntimeError"),
    ]
    for exc, expected in cases:
        reason = market._short_reason(exc)
        assert expected in reason
        assert "10.0.0.8" not in reason and "token=abc" not in reason


def test_market_envelope_marks_display_only_and_failure_has_no_items():
    ok = market._envelope([{"code": "600519"}], True)
    failed = market._envelope([], False, reason="外部数据源不可达")

    assert ok["scope"] == failed["scope"] == "display_only"
    assert ok["connected"] is True and ok["items"] == [{"code": "600519"}]
    assert failed["connected"] is False and failed["items"] == []
    assert failed["reason"] == "外部数据源不可达"


# ---------------------------------------------------------------------------
# db：DDL 切分与连接目标描述（绝不泄漏口令）
# ---------------------------------------------------------------------------
def test_db_split_sql_drops_comments_and_splits_statements():
    text = """
-- 建表脚本（整行注释）
CREATE TABLE a (id INT);

-- 中间注释
CREATE TABLE b (
  id INT
);

"""
    statements = db.split_sql(text)
    assert len(statements) == 2
    assert statements[0].startswith("CREATE TABLE a")
    assert statements[1].startswith("CREATE TABLE b")
    assert all("--" not in stmt for stmt in statements)
    assert db.split_sql("-- only a comment\n\n") == []


def test_db_describe_target_never_contains_password():
    params = backend_cfg.db_params(with_database=True)
    described = db.describe_target()
    without_db = db.describe_target(with_database=False)

    assert str(params["host"]) in described
    assert str(params["port"]) in described
    assert str(params["user"]) in described
    if str(params.get("password") or ""):
        assert str(params["password"]) not in described
        assert str(params["password"]) not in without_db
    assert "(未指定库)" in without_db
