# -*- coding: utf-8 -*-
r"""K 组 · 实体消歧与检索指标纯函数（第 5 轮 9.1 补强，**只增不改**）。

两组此前只有整链产物（`disambiguation.json`／`metrics_pre.jsonl`）层面的核对，
函数级边界没有用例；本组把口径钉住：

* `抽取与图谱/disambiguate.py`
    - `match_company()` 的 R1 精确、R2 全称展开、限定词阻断、多命中歧义、无命中；
    - `disambiguate_records()` 的身份键、未消歧留痕、`include_unresolved`（name_only）
      开关的「留痕一条不少」语义。
* `检索/metrics.py`
    - 四项指标的空边界与 Precision@K 分母恒为 K；
    - `evaluate_question_chunk_level()` 对 `|final| > K` 的四项一致截断；
    - `aggregate_chunk_level()` / `aggregate_doc_level_diagnostic()` 的双向混算拦截；
    - `chunk_id` 字符串／整数按同一集合语义处理。

全部离线、不读真实产物、不写产品目录。
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

dis = _bootstrap.load_module("抽取与图谱", "disambiguate.py")
dis_cfg = _bootstrap.component_config("抽取与图谱")
metrics = _bootstrap.load_module("检索", "metrics.py")

SEP = dis_cfg.DISAMBIG["identity_key_separator"]


def _entry(code, short_name, surfaces):
    normal = [dis_cfg.normalize_entity_name(s) for s in surfaces]
    return {
        "stock_code": code,
        "short_name": short_name,
        "normalized_short_name": dis_cfg.normalize_entity_name(short_name),
        "normalized_alias_surfaces": sorted({s for s in normal if s}),
        "registered_name": "",
        "exchange": "",
        "industry": "",
    }


ALIASES = {
    "600309": _entry("600309", "万华化学", ["万华化学", "万华化学集团股份有限公司"]),
    "601727": _entry("601727", "上海电气", ["上海电气", "上海电气集团股份有限公司"]),
    "600519": _entry("600519", "贵州茅台", ["贵州茅台", "贵州茅台酒股份有限公司"]),
    "600000": _entry("600000", "同名公司", ["同名公司"]),
    "600001": _entry("600001", "同名公司", ["同名公司"]),
}


def _norm(name):
    return dis_cfg.normalize_entity_name(name)


# ==========================================================================
# K1 · match_company 两条规则
# ==========================================================================
def test_r1_matches_short_name_registered_name_and_code():
    assert dis.match_company(_norm("万华化学"), ALIASES)[:2] == (
        "600309", "R1_exact_name_or_code")
    assert dis.match_company(_norm("万华化学集团股份有限公司"), ALIASES)[:2] == (
        "600309", "R1_exact_name_or_code")
    assert dis.match_company("600519", ALIASES)[:2] == (
        "600519", "R1_exact_name_or_code")


def test_r2_matches_full_name_containing_short_name():
    code, rule, detail = dis.match_company(
        _norm("万华化学集团股份有限公司（烟台）"), ALIASES)
    assert (code, rule) == ("600309", "R2_full_name_contains_short_name")
    assert "600309" in detail["matched_codes"]
    assert detail["blocked_by_marker"] == []


def test_distinct_entity_marker_blocks_merge():
    """残余含「控股」→ 判为另一个主体，进待消歧，绝不并到 601727。"""
    code, rule, detail = dis.match_company(
        _norm("上海电气控股集团有限公司"), ALIASES)
    assert code is None
    assert rule == "distinct_entity_marker"
    assert detail["matched_codes"] == []
    assert detail["blocked_by_marker"][0]["code"] == "601727"
    assert detail["blocked_by_marker"][0]["marker"] in dis_cfg.DISAMBIG["distinct_entity_markers"]


def test_ambiguous_alias_is_not_guessed():
    code, rule, detail = dis.match_company(_norm("同名公司"), ALIASES)
    assert code is None
    assert rule == "ambiguous_alias"
    assert detail["matched_codes"] == ["600000", "600001"]


def test_no_alias_match_is_explicit():
    code, rule, detail = dis.match_company(_norm("完全没听过的公司"), ALIASES)
    assert (code, rule) == (None, "no_alias_match")
    assert detail == {"matched_codes": [], "blocked_by_marker": []}


def test_short_surface_below_min_chars_does_not_trigger_r2():
    short = _entry("600002", "A", ["A"])
    code, rule, _ = dis.match_company(_norm("A公司股份有限公司"), {"600002": short})
    assert code is None
    assert rule == "no_alias_match"


# ==========================================================================
# K2 · disambiguate_records
# ==========================================================================
def _records():
    return [
        {"doc_id": 2, "entities": [
            {"entity_id": "e2", "type": "Company", "name": "贵州茅台酒股份有限公司"},
            {"entity_id": "e1", "type": "Person", "name": " 张三 "},
        ]},
        {"doc_id": 1, "entities": [
            {"entity_id": "e3", "type": "Company", "name": "上海电气控股集团有限公司"},
        ]},
    ]


def test_resolved_company_uses_stock_code_identity_key():
    emap, unresolved, seen = dis.disambiguate_records(_records(), ALIASES)
    item = emap["e2"]
    assert item["status"] == "resolved"
    assert item["identity_key"] == "Company%s600519" % SEP
    assert item["rule"] == "R1_exact_name_or_code"
    assert "600519" in seen


def test_non_company_identity_uses_label_and_normalized_name():
    emap, _unresolved, _seen = dis.disambiguate_records(_records(), ALIASES)
    item = emap["e1"]
    assert item["status"] == "resolved"
    assert item["identity_key"] == "Person%s张三" % SEP
    assert item["rule"] == dis_cfg.DISAMBIG["non_company_rule"]


def test_unresolved_company_is_kept_with_reason_and_no_identity():
    emap, unresolved, _seen = dis.disambiguate_records(_records(), ALIASES)
    item = emap["e3"]
    assert item["status"] == "unresolved"
    assert item["identity_key"] is None
    assert len(unresolved) == 1
    row = unresolved[0]
    assert row["reason"] == "distinct_entity_marker"
    assert row["doc_id"] == 1 and row["entity_id"] == "e3"
    assert row["matched_codes"] == []
    assert row["blocked_by_marker"]


def test_records_are_processed_in_doc_id_order():
    emap, _u, _s = dis.disambiguate_records(_records(), ALIASES)
    assert list(emap) == ["e3", "e1", "e2"]          # doc 1 先于 doc 2；题内按 entity_id 升序


def test_include_unresolved_admits_name_only_but_keeps_audit_row():
    emap, unresolved, _seen = dis.disambiguate_records(
        _records(), ALIASES, include_unresolved=True)
    item = emap["e3"]
    assert item["status"] == "resolved"
    assert item["resolved_by"] == "name_only"
    assert item["rule"] == "name_only_admitted"
    assert item["identity_key"] == "Company%s%s" % (SEP, _norm("上海电气控股集团有限公司"))
    # 审计留痕一条不少：unresolved 列表仍有一条
    assert len(unresolved) == 1


def test_include_unresolved_does_not_change_resolved_company_rule():
    emap, _u, _s = dis.disambiguate_records(
        _records(), ALIASES, include_unresolved=True)
    assert emap["e2"]["resolved_by"] == "stock_code"
    assert emap["e2"]["identity_key"] == "Company%s600519" % SEP


# ==========================================================================
# K3 · 四项指标：口径与边界
# ==========================================================================
def test_precision_denominator_is_always_k():
    """M=2 < K=10，命中 1 → 0.1（分母是 10，不是实际候选数 2）。"""
    assert metrics.precision_at_k(["g1", "x"], ["g1"], 10) == 0.1


def test_recall_and_complete_evidence_recall_distinguish_partial_hit():
    final, gold = ["g1", "x"], ["g1", "g2"]
    assert metrics.recall_at_k(final, gold, 5) == 0.5
    assert metrics.complete_evidence_recall_at_k(final, gold, 5) == 0.0


def test_mrr_uses_first_hit_rank():
    assert metrics.mrr(["x", "y", "g1"], ["g1"]) == metrics._r(1.0 / 3)


@pytest.mark.parametrize("func,args", [
    (metrics.recall_at_k, (["a"], [], 10)),
    (metrics.precision_at_k, (["a"], [], 10)),
    (metrics.mrr, (["a"], [])),
    (metrics.complete_evidence_recall_at_k, (["a"], [], 10)),
])
def test_empty_gold_is_zero_not_an_exception(func, args):
    assert func(*args) == 0.0


def test_chunk_ids_are_compared_by_string_form():
    """整数 1001001 与字符串 "1001001" 是同一个文本块（集合语义）。"""
    assert metrics.recall_at_k([1001001], ["1001001"], 5) == 1.0
    assert metrics.precision_at_k([1001001, 1001001], ["1001001"], 5) == 0.2


def test_k_must_be_positive():
    with pytest.raises(ValueError):
        metrics.precision_at_k(["a"], ["a"], 0)
    with pytest.raises(ValueError):
        metrics.evaluate_question_chunk_level(["a"], ["a"], -1)


# ==========================================================================
# K4 · 逐题行截断与聚合混算拦截
# ==========================================================================
def test_question_row_truncates_all_four_metrics_to_k():
    final = ["c%02d" % i for i in range(1, 13)]       # 12 条，K=10
    gold_out = ["c11"]                                # 落在 K 之外
    row = metrics.evaluate_question_chunk_level(final, gold_out, 10, qid="PE-B15")
    assert row["n_final"] == 10 and row["n_hit"] == 0
    assert row["mrr"] == 0.0
    assert row["final_ids"] == final[:10]


def test_question_row_keeps_question_level_tags_verbatim():
    row = metrics.evaluate_question_chunk_level(
        ["a"], ["a"], 10, qid="PE-01", task_type="事实型", gold_hop_depth=2)
    assert row["qid"] == "PE-01"
    assert row["task_type"] == "事实型"
    assert row["gold_hop_depth"] == 2
    assert row["level"] == "chunk"


def test_aggregate_chunk_level_averages_per_question_and_counts_empties():
    rows = [
        metrics.evaluate_question_chunk_level(["a", "b"], ["a"], 10, qid="Q1"),
        metrics.evaluate_question_chunk_level([], ["z"], 10, qid="Q2"),
    ]
    avg = metrics.aggregate_chunk_level(rows, "全题", K=10)
    assert avg["level"] == "chunk"
    assert avg["n_questions"] == 2
    assert avg["n_empty_gold"] == 0
    assert avg["n_empty_final"] == 1
    assert avg["recall_at_k"] == 0.5                  # (1.0 + 0) / 2
    assert avg["precision_at_k"] == 0.05              # (0.1 + 0) / 2
    assert set(metrics.CHUNK_METRIC_KEYS) <= set(avg)


def test_aggregate_chunk_level_rejects_document_rows():
    doc_row = metrics.recall_at_k_doc_level_diagnostic(["d1"], ["d1"], 10)
    with pytest.raises(ValueError):
        metrics.aggregate_chunk_level([doc_row], "混算", K=10)


def test_aggregate_doc_level_rejects_chunk_rows():
    chunk_row = metrics.evaluate_question_chunk_level(["a"], ["a"], 10, qid="Q")
    with pytest.raises(ValueError):
        metrics.aggregate_doc_level_diagnostic([chunk_row], "混算", K=10)


def test_doc_level_metric_keys_do_not_collide_with_chunk_level():
    row = metrics.recall_at_k_doc_level_diagnostic(["d1", "d2"], ["d1"], 10)
    assert row["level"] == "document"
    assert "recall_at_k_doc_level" in row
    assert "recall_at_k" not in row
    avg = metrics.aggregate_doc_level_diagnostic([row], "文档级", K=10)
    assert avg["level"] == "document"
    assert not any(key in avg for key in metrics.CHUNK_METRIC_KEYS)
