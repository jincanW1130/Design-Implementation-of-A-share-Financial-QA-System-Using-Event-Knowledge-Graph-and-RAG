# -*- coding: utf-8 -*-
r"""P1-12 补测 · F 组 —— 抽取与图谱组件的**纯函数**（离线、只读）。

覆盖（对应测试 README 第五节「没覆盖什么」里如实登记的那一条：

    "**数据准备／抽取与图谱两个组件的纯函数** | 本次按评审 P1-12 点名的四组覆盖面做
     （检索／问答／后端）；数据库准备侧的 `chunk.py`／`dedup.py` 等尚未纳入"

本文件补齐「抽取与图谱」一侧）：

  * `交付物/03-代码\抽取与图谱\extract.py`
      `normalize_ws` / `evidence_key` / `parse_json_object` / `resolve_quote` /
      `normalize_confidence` / `normalize_date` / `date_rendering_in_document` /
      `event_type_hits` / `render_user_prompt` 的确定性判据
  * `交付物/03-代码\抽取与图谱\fold_variants.py`
      `fold_simp` 与简繁对照表的自检
  * `交付物/03-代码\抽取与图谱\write_graph.py`
      `cell` / `to_csv` / `cypher_literal` / `prop_map` / `label_rank` / `_isolated`

三条纪律与其余各组件一致：**离线**、**参数不写死**（阈值一律取自抽取与图谱自己的
`config`）、**关键断言都配负向标定**。

注：本组不触碰任何**联网路径**（`call_model`／`load_or_call`）与需要真实图谱导出物的路径
（`show_graph` 等），那些属阶段门禁的覆盖面（测试 README 第五节第 1／3 条）。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402


# --------------------------------------------------------------------------
# 夹具
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def ex_cfg():
    """`交付物/03-代码\\抽取与图谱\\config.py` —— 参数唯一来源。"""
    return _bootstrap.component_config("抽取与图谱")


@pytest.fixture(scope="session")
def extract_mod():
    return _bootstrap.load_module("抽取与图谱", "extract.py")


@pytest.fixture(scope="session")
def fold_mod():
    return _bootstrap.load_module("抽取与图谱", "fold_variants.py")


@pytest.fixture(scope="session")
def wg_mod():
    return _bootstrap.load_module("抽取与图谱", "write_graph.py")


# ==========================================================================
# F1 组 · 空白归一与证据键（normalize_ws / evidence_key）
# ==========================================================================
def test_normalize_ws_folds_runs_to_single_half_width_space(extract_mod):
    """连续空白（含换行、全角空格）→ 单个半角空格，首尾去净。"""
    got = extract_mod.normalize_ws("  甲\u3000公司\n\n2026 年\t业绩  ")
    assert got == "甲 公司 2026 年 业绩"


def test_normalize_ws_none_is_empty(extract_mod):
    assert extract_mod.normalize_ws(None) == ""
    assert extract_mod.normalize_ws("") == ""


def test_evidence_key_removes_all_whitespace_but_changes_nothing_else(extract_mod):
    """证据键**去掉全部空白**（含全角空格），其余字符（含大小写、标点）原样。

    为什么不去大小写／不做模糊匹配：来源 PDF 里存在词内空格（doc_id 1018 的
    「公 司将」），折成单空格会把合法引用误判为无法定位（config.EVIDENCE['normalize']）。
    """
    assert extract_mod.evidence_key("公 司将") == "公司将"
    assert extract_mod.evidence_key("甲\u3000公司\n2026 年") == "甲公司2026年"
    # 负向标定：不做大小写折叠
    assert extract_mod.evidence_key("ABC") != extract_mod.evidence_key("abc")
    assert extract_mod.evidence_key("ABC") == "ABC"
    # 负向标定：不做标点归一
    assert extract_mod.evidence_key("甲，乙") == "甲，乙"


def test_evidence_key_none_is_empty(extract_mod):
    assert extract_mod.evidence_key(None) == ""


# ==========================================================================
# F2 组 · 模型 JSON 解析（parse_json_object）
# ==========================================================================
def test_parse_json_object_accepts_plain_object(extract_mod):
    obj, reason, fence = extract_mod.parse_json_object('{"a": 1, "b": [2, 3]}')
    assert obj == {"a": 1, "b": [2, 3]}
    assert reason is None
    assert fence is False


def test_parse_json_object_strips_markdown_fence_and_flags_it(extract_mod):
    """只做"剥代码围栏"这一种容错，并如实报告剥过（fence_stripped=True）。"""
    obj, reason, fence = extract_mod.parse_json_object("```json\n{\"a\": 1}\n```")
    assert obj == {"a": 1}
    assert reason is None
    assert fence is True


def test_parse_json_object_rejects_non_object_json(extract_mod):
    """数组／标量不是合法抽取结果：返回 json_not_object，不改写。"""
    for text in ("[1, 2, 3]", "42", "\"a string\""):
        obj, reason, fence = extract_mod.parse_json_object(text)
        assert obj is None
        assert reason == "json_not_object"


def test_parse_json_object_reports_bad_json_reason(extract_mod):
    obj, reason, fence = extract_mod.parse_json_object("{not json}")
    assert obj is None
    assert reason is not None and reason.startswith("bad_json:")
    assert fence is False


def test_parse_json_object_empty_text(extract_mod):
    obj, reason, fence = extract_mod.parse_json_object("")
    assert obj is None
    assert reason is not None and reason.startswith("bad_json:")


# ==========================================================================
# F3 组 · 逐字引用定位（resolve_quote）—— 三种失败必须**分开**登记
# ==========================================================================
def _chunks():
    return [
        {"chunk_id": 11, "chunk_index": 0, "content": "甲公司2026年度业绩预告。"},
        {"chunk_id": 12, "chunk_index": 1, "content": "预计净利润同比增长。"},
    ]


def test_resolve_quote_finds_chunk_and_reports_match_count(extract_mod):
    cid, reason, count = extract_mod.resolve_quote("甲公司2026年度业绩预告。", _chunks(), "")
    assert cid == 11
    assert reason is None
    assert count == 1


def test_resolve_quote_tolerates_word_internal_spaces_via_evidence_key(extract_mod):
    """引用「将 同比」这种带词内空格的写法，仍能命中不带空格的正文（去空白比对）。"""
    chunks = [{"chunk_id": 11, "chunk_index": 0, "content": "预计净利润同比增长。"}]
    cid, reason, count = extract_mod.resolve_quote("净利润 同比", chunks, "")
    assert cid == 11
    assert reason is None


def test_resolve_quote_distinguishes_boundary_span_from_not_in_document(extract_mod):
    """跨块边界 与 正文根本没有 —— 两种失败必须分开（前者机械、后者才是编造）。"""
    chunks = _chunks()
    full = "甲公司2026年度业绩预告。预计净利润同比增长。"
    # 引用横跨两块：整篇正文里有，但任何单块里都没有
    cid, reason, count = extract_mod.resolve_quote("业绩预告。预计净利润", chunks, full)
    assert cid is None
    assert reason == "quote_spans_chunk_boundary"
    # 正文里根本没有 → 编造／改写
    cid, reason, count = extract_mod.resolve_quote("本公司将回购全部股份", chunks, full)
    assert cid is None
    assert reason == "quote_not_in_document"


def test_resolve_quote_empty_quote_is_quote_missing(extract_mod):
    for blank in ("", "   ", "\n", None):
        cid, reason, count = extract_mod.resolve_quote(blank, _chunks(), "随便")
        assert cid is None
        assert reason == "quote_missing"
        assert count == 0


def test_resolve_quote_returns_the_earliest_chunk_on_multiple_matches(extract_mod):
    """多处命中时取 chunk_index 最小者（确定性，不受输入顺序影响）。"""
    chunks = [
        {"chunk_id": 22, "chunk_index": 1, "content": "重复文本X"},
        {"chunk_id": 21, "chunk_index": 0, "content": "重复文本X"},
    ]
    cid, reason, count = extract_mod.resolve_quote("重复文本X", chunks, "")
    assert cid == 21          # chunk_index 0 的在前
    assert count == 2


# ==========================================================================
# F4 组 · confidence / date 归一（normalize_confidence / normalize_date）
# ==========================================================================
def test_normalize_confidence_accepts_range_and_rounds(extract_mod, ex_cfg):
    assert extract_mod.normalize_confidence(0.0) == (0.0, None)
    assert extract_mod.normalize_confidence(1.0) == (1.0, None)
    assert extract_mod.normalize_confidence(0.98765) == (0.988, None)
    assert ex_cfg.CONFIDENCE_MIN == 0.0 and ex_cfg.CONFIDENCE_MAX == 1.0


def test_normalize_confidence_scales_percentages_and_flags_it(extract_mod):
    """写成百分数（1 < value ≤ 100）按 /100 归一，并记 confidence_scaled。"""
    assert extract_mod.normalize_confidence(90) == (0.9, "confidence_scaled")
    assert extract_mod.normalize_confidence(100) == (1.0, "confidence_scaled")


def test_normalize_confidence_rejects_non_numbers_and_out_of_range(extract_mod):
    """布尔／字符串／None／越界（>100）一律返回 (None, None)——不猜、不夹取。"""
    for bad in (True, False, "0.5", None, [], {}, 101, -0.1):
        assert extract_mod.normalize_confidence(bad) == (None, None)


def test_normalize_date_accepts_every_configured_form(extract_mod, ex_cfg):
    """config.TIME['accepted_income_forms'] 里的每种写法都折成 YYYY-MM-DD。"""
    forms = {
        "2026-3-1": "2026-03-01",
        "2026/3/1": "2026-03-01",
        "2026.3.1": "2026-03-01",
        "2026年3月1日": "2026-03-01",
    }
    for raw, want in forms.items():
        got, invalid = extract_mod.normalize_date(raw)
        assert got == want, raw
        assert invalid is False


def test_normalize_date_returns_none_for_junk_and_marks_invalid(extract_mod):
    """无法识别 → (None, True)；空／None／'null' 除外（视为"没给"，invalid=False）。"""
    for junk in ("昨天", "2026-13-40", "三月一日", "abc"):
        got, invalid = extract_mod.normalize_date(junk)
        assert got is None
        assert invalid is True, junk
    for absent in (None, "", "  ", "null", "None"):
        got, invalid = extract_mod.normalize_date(absent)
        assert got is None
        assert invalid is False, absent


def test_normalize_date_rejects_impossible_calendar_dates(extract_mod):
    """格式对但日期不存在（2 月 30 日）→ (None, True)，不得静默归一。"""
    got, invalid = extract_mod.normalize_date("2026-2-30")
    assert got is None
    assert invalid is True


def test_date_rendering_in_document_matches_all_renderings(extract_mod):
    iso = "2026-03-01"
    for text in ("2026-03-01", "2026-3-1", "2026/3/1", "2026.3.1", "2026年3月1日"):
        assert extract_mod.date_rendering_in_document(iso, text) is True, text


def test_date_rendering_in_document_tolerates_layout_spaces(extract_mod):
    """来源文本自带的排版空格（「2020 年9 月23 日」）不算不匹配。"""
    assert extract_mod.date_rendering_in_document("2020-09-23", "2020 年9 月23 日") is True


def test_date_rendering_in_document_rejects_a_different_date(extract_mod):
    """负向标定：不同日期不得被判为出现。"""
    assert extract_mod.date_rendering_in_document("2026-03-01", "2026-03-02") is False


# ==========================================================================
# F5 组 · 选样代理指标（event_type_hits）
# ==========================================================================
def test_event_type_hits_returns_none_when_title_misses(extract_mod):
    doc = {"title": "某公司日常经营公告", "content": "无关键内容"}
    assert extract_mod.event_type_hits(doc, "业绩") is None


def test_event_type_hits_distinguishes_title_only_from_title_and_body(extract_mod):
    """命中层级冻结为 title / title+body 两档（是选样的确定性代理指标）。"""
    title_only = {"title": "2026年度业绩预告", "content": "与本指标无关的正文"}
    both = {"title": "2026年度业绩预告", "content": "本年度业绩大幅增长"}
    assert extract_mod.event_type_hits(title_only, "业绩") == "title"
    assert extract_mod.event_type_hits(both, "业绩") == "title+body"


def test_event_type_hits_product_excludes_refinancing_titles(extract_mod):
    """产品组排除再融资污染：标题命中「发行／股票／债券…」时整条剔除（返回 None）。"""
    polluted = {"title": "关于向特定对象发行股票募集说明书的公告", "content": "取得注册证"}
    assert extract_mod.event_type_hits(polluted, "产品") is None
    clean = {"title": "公司新产品获得注册证", "content": "产品获批"}
    assert extract_mod.event_type_hits(clean, "产品") is not None


def test_event_type_hits_none_title_is_safe(extract_mod):
    assert extract_mod.event_type_hits({}, "业绩") is None
    assert extract_mod.event_type_hits({"title": None}, "业绩") is None


# ==========================================================================
# F6 组 · 简繁／异体折叠（fold_variants）
# ==========================================================================
def test_fold_simp_folds_traditional_to_simplified(fold_mod):
    assert fold_mod.fold_simp("廣東") == "广东"
    assert fold_mod.fold_simp("數據庫") == "数据库"


def test_fold_simp_is_idempotent(fold_mod):
    once = fold_mod.fold_simp("臺灣證券交易所")
    assert fold_mod.fold_simp(once) == once


def test_fold_simp_leaves_digits_and_letters_intact_and_nfkc_normalizes_width(fold_mod):
    """数字、半角字母原样；全角括号／字母／数字先被 NFKC 折成半角（docstring 明写"NFKC"）。"""
    assert fold_mod.fold_simp("2026年ABC-123") == "2026年ABC-123"
    # NFKC：全角括号 → 半角，全角字母数字 → 半角；中文与简繁折叠互不影响
    assert fold_mod.fold_simp("（A股）") == "(A股)"
    assert fold_mod.fold_simp("ＡＢＣ１２３") == "ABC123"


def test_fold_simp_handles_none_and_empty(fold_mod):
    assert fold_mod.fold_simp(None) == ""
    assert fold_mod.fold_simp("") == ""


def test_s2t_map_has_no_conflicting_targets(fold_mod):
    """简繁对照表自检：每个繁体字只有一个简体目标，且无同字映射（构建期已断言）。"""
    table = fold_mod.S2T_MAP
    assert len(table) > 0
    for trad, simp in table.items():
        assert len(trad) == 1 and len(simp) == 1
        assert trad != simp


def test_fold_simp_does_not_touch_ascii_case(fold_mod):
    """负向标定：不做大小写折叠（那是别的环节的职责）。"""
    assert fold_mod.fold_simp("AbC") == "AbC"


# ==========================================================================
# F7 组 · 图谱落盘字面量（write_graph：cell / to_csv / cypher_literal / prop_map）
# ==========================================================================
def test_cell_none_is_empty_string(wg_mod):
    assert wg_mod.cell(None) == ""


def test_cell_joins_lists_with_config_separator(wg_mod, ex_cfg):
    sep = ex_cfg.GRAPH["list_separator"]
    assert wg_mod.cell(["a", "b", "c"]) == sep.join(["a", "b", "c"])
    assert wg_mod.cell(("a", "b")) == sep.join(["a", "b"])
    assert sep == "|"      # config 冻结值：CSV 里数组属性的连接符


def test_cell_renders_bool_as_lowercase_literal(wg_mod):
    assert wg_mod.cell(True) == "true"
    assert wg_mod.cell(False) == "false"


def test_cell_falls_back_to_str(wg_mod):
    assert wg_mod.cell(42) == "42"
    assert wg_mod.cell(3.5) == "3.5"


def test_to_csv_uses_given_column_order_and_lf_terminator(wg_mod):
    cols = ["node_id", "label", "name"]
    rows = [{"node_id": "N1", "label": "Company", "name": "甲公司", "extra": "ignored"}]
    text = wg_mod.to_csv(cols, rows)
    assert text.endswith("\n")
    assert "\r\n" not in text
    lines = text.split("\n")
    assert lines[0] == "node_id,label,name"        # 表头＝给定列序（extra 被忽略）
    assert lines[1].startswith("N1,Company,")


def test_cypher_literal_quotes_escapes_and_nulls(wg_mod):
    assert wg_mod.cypher_literal(None) == ""
    assert wg_mod.cypher_literal("") == ""
    assert wg_mod.cypher_literal(42) == "42"
    assert wg_mod.cypher_literal(1.5) == "1.5"
    assert wg_mod.cypher_literal(True) == "true"
    assert wg_mod.cypher_literal("甲公司") == "'甲公司'"


def test_cypher_literal_escapes_quotes_and_newlines(wg_mod):
    """单引号与反斜杠转义；换行折成 \\n、回车折成空格（Cypher 单行字面量）。"""
    assert wg_mod.cypher_literal("a'b") == "'a\\'b'"
    assert wg_mod.cypher_literal("a\\b") == "'a\\\\b'"
    got = wg_mod.cypher_literal("第一行\n第二行\r结束")
    assert "\\n" in got
    assert "\n" not in got and "\r" not in got


def test_prop_map_skips_empty_values(wg_mod):
    got = wg_mod.prop_map([("a", "1"), ("b", None), ("c", ""), ("d", 2)])
    assert got == "{a: '1', d: 2}"


def test_prop_map_all_empty_is_empty_string(wg_mod):
    assert wg_mod.prop_map([("a", None), ("b", "")]) == ""


def test_label_rank_follows_config_entity_type_order(wg_mod, ex_cfg):
    """标签排序键 = 实体类型表顺序，Document 永远排在最后（未知标签也排在最后）。"""
    order = list(ex_cfg.ENTITY_TYPES) + [ex_cfg.DOCUMENT_LABEL]
    ranks = [wg_mod.label_rank(t) for t in order]
    assert ranks == sorted(ranks)
    assert ranks == list(range(len(order)))
    assert wg_mod.label_rank("NO_SUCH_LABEL") == len(order)
    assert wg_mod.label_rank(ex_cfg.DOCUMENT_LABEL) == len(order) - 1


def test_isolated_extracts_nodes_with_no_edge(wg_mod):
    nodes = [{"node_id": "N1"}, {"node_id": "N2"}, {"node_id": "N3"}]
    edges = [{"head_id": "N1", "tail_id": "N2"}]
    assert wg_mod._isolated(nodes, edges) == ["N3"]


def test_isolated_compares_as_strings(wg_mod):
    """端点 id 可能是 int，节点 id 是 str：必须按字符串比，否则孤立判定会误报。"""
    nodes = [{"node_id": "1"}, {"node_id": "2"}]
    edges = [{"head_id": 1, "tail_id": "2"}]
    assert wg_mod._isolated(nodes, edges) == []


def test_isolated_empty_edges_means_all_isolated(wg_mod):
    nodes = [{"node_id": "A"}, {"node_id": "B"}]
    assert wg_mod._isolated(nodes, []) == ["A", "B"]
