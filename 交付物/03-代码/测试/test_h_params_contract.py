# -*- coding: utf-8 -*-
r"""H 组 · 接口层公共参数校验（第 5 轮 9.1/9.3 补强，**只增不改**）。

被测对象：`交付物/03-代码\后端\params.py` 的六个纯函数——
`text` / `is_blank` / `parse_int` / `page_args` / `truthy` / `validate_question`。

为什么单测这一层
----------------
第 2 轮把这些口径从四个路由模块收敛到一处，但它们的边界（默认值、空串、上下界、
控制字符）此前只通过 G 组的路由用例**间接**覆盖。本组直接钉住函数级契约：

* 缺省／空串 → 取默认值，不报错；
* 非法数值 → `ApiError(1002)`，响应键集合恰为 `{code, message}`；
* 分页上下界与 `config.API_LIMITS` 同源（不从测试里再抄一份字面量）；
* `validate_question` 的 1～500 字、去空白、`\t\r\n` 折单空格、控制字符拒绝。

离线纪律不变：不联网、不读数据集、不写产品目录。
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

errors_mod = _bootstrap.load_backend("errors")
backend_cfg = _bootstrap.component_config("后端")
params_mod = _bootstrap.load_module("后端", "params.py")

LIMITS = backend_cfg.LIMITS
API_LIMITS = backend_cfg.API_LIMITS


def _raise_code(func, *args, **kwargs) -> int:
    """调用 `func` 并断言其抛 `ApiError`；返回错误码（响应体口径同时校验）。"""
    with pytest.raises(errors_mod.ApiError) as excinfo:
        func(*args, **kwargs)
    err = excinfo.value
    assert set(err.payload().keys()) == {"code", "message"}
    assert "detail" not in err.payload()
    return err.code


# ---------------------------------------------------------------------------
# H1 · text / is_blank
# ---------------------------------------------------------------------------
def test_text_none_is_empty_string_not_the_literal_none():
    assert params_mod.text(None) == ""


def test_text_keeps_strings_verbatim_including_spaces():
    """`text()` 不 strip、不折叠——与 `api.graph._s` 的历史口径逐字一致。"""
    assert params_mod.text("  甲 公司  ") == "  甲 公司  "
    assert params_mod.text(0) == "0"
    assert params_mod.text(False) == "False"


def test_is_blank_treats_none_and_whitespace_as_missing():
    assert params_mod.is_blank(None) is True
    assert params_mod.is_blank("") is True
    assert params_mod.is_blank(" \t\r\n ") is True


def test_is_blank_does_not_swallow_zero_or_text():
    """只有「缺失或全空白」算空；`0` 与带内容字符串都不是。"""
    assert params_mod.is_blank(0) is False
    assert params_mod.is_blank("0") is False
    assert params_mod.is_blank(" a ") is False


# ---------------------------------------------------------------------------
# H2 · parse_int
# ---------------------------------------------------------------------------
def test_parse_int_missing_or_blank_returns_default():
    assert params_mod.parse_int(None, "page", default=7) == 7
    assert params_mod.parse_int("", "page", default=7) == 7
    assert params_mod.parse_int("   ", "page", default=7) == 7


def test_parse_int_accepts_signed_and_padded_integers():
    assert params_mod.parse_int("42", "n") == 42
    assert params_mod.parse_int("  -3 ", "n") == -3
    assert params_mod.parse_int("0", "n") == 0


@pytest.mark.parametrize("bad", ["3.5", "1e3", "abc", "12a", "--1"])
def test_parse_int_rejects_non_integers_with_1002(bad):
    assert _raise_code(params_mod.parse_int, bad, "n") == 1002


def test_parse_int_error_payload_is_exactly_code_and_message():
    with pytest.raises(errors_mod.ApiError) as excinfo:
        params_mod.parse_int("x", "page")
    err = excinfo.value
    assert err.payload() == {"code": 1002, "message": errors_mod.message_of(1002)}
    assert err.http_status == 400


# ---------------------------------------------------------------------------
# H3 · page_args
# ---------------------------------------------------------------------------
def test_page_args_defaults_come_from_config_not_from_the_test():
    page, size = params_mod.page_args(None, None)
    assert page == 1
    assert size == int(API_LIMITS["default_page_size"])


def test_page_args_accepts_in_range_values():
    assert params_mod.page_args("3", str(API_LIMITS["page_size_max"])) == (
        3, int(API_LIMITS["page_size_max"]))


@pytest.mark.parametrize("page", ["0", "-1", "x"])
def test_page_args_rejects_bad_page_number(page):
    assert _raise_code(params_mod.page_args, page, None) == 1002


@pytest.mark.parametrize("size", ["0", "-1", "x"])
def test_page_args_rejects_bad_page_size(size):
    assert _raise_code(params_mod.page_args, None, size) == 1002


def test_page_args_rejects_page_size_above_config_ceiling():
    above = int(API_LIMITS["page_size_max"]) + 1
    assert _raise_code(params_mod.page_args, None, str(above)) == 1002


def test_page_args_honours_explicit_page_max_boundary():
    assert params_mod.page_args("5", None, page_max=5) == (
        5, int(API_LIMITS["default_page_size"]))
    assert _raise_code(params_mod.page_args, "6", None, page_max=5) == 1002


def test_page_args_honours_explicit_size_override():
    """调用方显式给的上下界优先于 config 缺省（历史接口的另一套口径）。"""
    assert params_mod.page_args(None, None, page_size_max=5, default_page_size=2) == (1, 2)
    assert _raise_code(params_mod.page_args, None, "6", page_size_max=5) == 1002


# ---------------------------------------------------------------------------
# H4 · truthy
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "On", " on "])
def test_truthy_accepts_documented_true_spellings(value):
    assert params_mod.truthy(value) is True


@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "yes!", "2"])
def test_truthy_rejects_everything_else(value):
    assert params_mod.truthy(value) is False


# ---------------------------------------------------------------------------
# H5 · validate_question
# ---------------------------------------------------------------------------
def test_validate_question_rejects_missing_and_non_string():
    assert _raise_code(params_mod.validate_question, None) == 1001
    assert _raise_code(params_mod.validate_question, 123) == 1001
    assert _raise_code(params_mod.validate_question, ["q"]) == 1001


@pytest.mark.parametrize("blank", ["", "   ", "\t\r\n"])
def test_validate_question_rejects_blank_after_strip(blank):
    assert _raise_code(params_mod.validate_question, blank) == 1001


def test_validate_question_trims_outer_whitespace_but_keeps_content():
    assert params_mod.validate_question("  贵州茅台2026年业绩如何？ \n") == \
        "贵州茅台2026年业绩如何？"


def test_validate_question_folds_multiline_into_single_spaces():
    got = params_mod.validate_question("甲公司的\n\t业绩\r\n如何？")
    assert got == "甲公司的 业绩 如何？"
    assert "\n" not in got and "\t" not in got and "\r" not in got


def test_validate_question_accepts_the_configured_max_length():
    hi = int(LIMITS["question_max_chars"])
    assert len(params_mod.validate_question("问" * hi)) == hi


def test_validate_question_rejects_one_char_above_the_limit():
    hi = int(LIMITS["question_max_chars"])
    assert _raise_code(params_mod.validate_question, "问" * (hi + 1)) == 1001


@pytest.mark.parametrize("bad", ["第一行\x00第二行", "含\x07铃声", "删除\x7f字符"])
def test_validate_question_rejects_control_characters(bad):
    assert _raise_code(params_mod.validate_question, bad) == 1001


def test_validate_question_length_is_counted_after_trimming():
    """首尾空白不计入长度：`hi` 个字加两侧空白仍然合法。"""
    hi = int(LIMITS["question_max_chars"])
    assert params_mod.validate_question("  " + "问" * hi + "  ") == "问" * hi
