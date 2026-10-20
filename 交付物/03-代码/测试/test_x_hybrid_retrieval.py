# -*- coding: utf-8 -*-
"""X 组：离线混合检索模块的公式、边界、扩展与默认兼容性。"""

from __future__ import annotations

import math
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

hybrid = _bootstrap.load_module("增强", "hybrid_retrieval.py")
lexical = _bootstrap.load_module("增强", "lexical_search.py")


def _ids(rows):
    return [int(row["chunk_id"]) for row in rows]


@pytest.mark.parametrize(
    "rankings,k,expected,expected_order",
    [
        (
            {"only": [10, 20]},
            60,
            {10: 1 / 61, 20: 1 / 62},
            [10, 20],
        ),
        (
            {"vector": [1, 2], "lexical": [2, 3]},
            60,
            {2: 1 / 62 + 1 / 61, 1: 1 / 61, 3: 1 / 62},
            [2, 1, 3],
        ),
        (
            [[4, 5, 6], [6, 4]],
            10,
            {4: 1 / 11 + 1 / 12, 5: 1 / 12, 6: 1 / 13 + 1 / 11},
            [4, 6, 5],
        ),
    ],
)
def test_rrf_hand_calculated_cases(rankings, k, expected, expected_order):
    rows = hybrid.rrf(rankings, k=k)

    assert _ids(rows) == expected_order
    assert [row["rrf_rank"] for row in rows] == list(range(1, len(rows) + 1))
    for row in rows:
        assert row["rrf_score"] == pytest.approx(expected[row["chunk_id"]], abs=1e-8)


def test_rrf_weights_change_channel_influence():
    rankings = {"vector": [1, 2], "lexical": [2, 1]}

    vector_heavy = hybrid.rrf(rankings, k=60, weights=(2, 1))
    lexical_heavy = hybrid.rrf(rankings, k=60, weights=(1, 2))

    assert _ids(vector_heavy)[0] == 1
    assert _ids(lexical_heavy)[0] == 2
    assert vector_heavy[0]["rrf_score"] > vector_heavy[1]["rrf_score"]
    assert lexical_heavy[0]["rrf_score"] > lexical_heavy[1]["rrf_score"]


def test_rrf_zero_weight_and_empty_boundaries():
    rankings = {"vector": [1, 2], "lexical": [2, 3]}

    only_vector = hybrid.rrf(rankings, k=60, weights=(1, 0))
    only_lexical = hybrid.rrf(rankings, k=60, weights=(0, 1))

    assert _ids(only_vector) == [1, 2]
    assert _ids(only_lexical) == [2, 3]
    assert hybrid.rrf([], k=60) == []
    assert hybrid.rrf({"empty": []}, k=60) == []


def test_rrf_rejects_bad_weights_and_k():
    with pytest.raises(ValueError, match="长度"):
        hybrid.rrf([[1], [2]], weights=(1,))
    with pytest.raises(ValueError, match="非负"):
        hybrid.rrf([[1]], weights=(-1,))
    with pytest.raises(ValueError, match="非负"):
        hybrid.rrf([[1]], k=-1)


def test_rrf_default_matches_existing_baseline_exactly():
    rankings = {
        "vector": [{"chunk_id": 9}, {"chunk_id": 3}, {"chunk_id": 7}],
        "lexical": [{"chunk_id": 3}, {"chunk_id": 9}, {"chunk_id": 1}],
    }

    assert hybrid.rrf(rankings) == lexical.rrf_fuse(rankings, k_rrf=60)


def test_normalization_minmax_and_zscore_hand_calculated():
    scores = {"1": 0.0, "2": 5.0, "3": 10.0}

    assert hybrid.normalize_scores(scores, "minmax") == {1: 0.0, 2: 0.5, 3: 1.0}
    z = hybrid.normalize_scores(scores, "zscore")
    expected_std = math.sqrt(50.0 / 3.0)
    assert z[1] == pytest.approx(-5.0 / expected_std)
    assert z[2] == pytest.approx(0.0)
    assert z[3] == pytest.approx(5.0 / expected_std)


def test_normalization_zero_variance_and_empty_boundaries():
    assert hybrid.normalize_scores({1: 7.0, 2: 7.0}, "minmax") == {1: 1.0, 2: 1.0}
    assert hybrid.normalize_scores({1: 7.0, 2: 7.0}, "zscore") == {1: 0.0, 2: 0.0}
    assert hybrid.normalize_scores({}, "minmax") == {}
    assert hybrid.normalize_scores({}, "zscore") == {}
    with pytest.raises(ValueError, match="mode"):
        hybrid.normalize_scores({1: 1.0}, "rank")


def test_score_fusion_alpha_changes_order_and_keeps_raw_scores():
    vec = [
        {"chunk_id": 1, "similarity": 1.0},
        {"chunk_id": 2, "similarity": 0.5},
    ]
    lex = [
        {"chunk_id": 2, "lexical_score": 10.0},
        {"chunk_id": 3, "lexical_score": 9.0},
    ]

    vector_heavy = hybrid.score_fusion(vec, lex, mode="minmax", alpha=0.75)
    lexical_heavy = hybrid.score_fusion(vec, lex, mode="minmax", alpha=0.25)

    assert _ids(vector_heavy) == [1, 2, 3]
    assert _ids(lexical_heavy) == [2, 1, 3]
    by_id = {row["chunk_id"]: row for row in vector_heavy}
    assert by_id[2]["vector_score"] == 0.5
    assert by_id[2]["lexical_score"] == 10.0
    assert "vector_score" not in by_id[3]


def test_score_fusion_zscore_is_deterministic_and_missing_channel_is_zero():
    vec = {1: 0.9, 2: 0.8}
    lex = {2: 4.0, 3: 2.0}

    first = hybrid.score_fusion(vec, lex, mode="zscore", alpha=0.5)
    second = hybrid.score_fusion(vec, lex, mode="zscore", alpha=0.5)

    assert first == second
    assert _ids(first) == [1, 2, 3]
    by_id = {row["chunk_id"]: row for row in first}
    assert by_id[1]["lexical_norm"] == 0.0
    assert by_id[3]["vector_norm"] == 0.0


def test_score_fusion_rejects_bad_alpha_and_missing_score():
    with pytest.raises(ValueError, match="alpha"):
        hybrid.score_fusion({1: 1.0}, {1: 1.0}, alpha=1.2)
    with pytest.raises(ValueError, match="分数字段"):
        hybrid.score_fusion([{"chunk_id": 1, "other": 1.0}], {})


def _catalog():
    return hybrid.AliasCatalog.from_rows([
        {
            "node_id": "000001",
            "label": "Company",
            "name": "甲银行",
            "stock_code": "000001",
            "company_name": "甲银行股份有限公司",
            "short_name": "甲银行",
            "aliases": "甲行|A银行",
        },
        {
            "node_id": "EVT-1",
            "label": "Event",
            "name": "绿色转型",
            "aliases": "绿转|低碳升级",
        },
    ])


def test_query_expansion_switch_and_rule_terms_are_deterministic():
    catalog = _catalog()
    question = "甲行与绿转有什么进展"

    off = hybrid.expand_query(question, enabled=False, catalog=catalog)
    on_a = hybrid.expand_query(question, enabled=True, catalog=catalog)
    on_b = hybrid.expand_query(question, enabled=True, catalog=catalog)

    assert off == question
    assert on_a == on_b
    assert on_a != off
    assert "000001" in on_a
    assert "甲银行股份有限公司" in on_a
    assert "低碳升级" in on_a
    assert on_a.count("000001") == 1


def test_query_expansion_improves_constructed_gold_hit():
    catalog = _catalog()
    index = lexical.LexicalIndex.build([
        {"chunk_id": 101, "doc_id": 1, "content": "000001 净利润同比增长"},
        {"chunk_id": 202, "doc_id": 2, "content": "完全无关的天气记录"},
    ])

    plain_query = "甲行业绩"
    expanded_query = hybrid.expand_query(
        plain_query, enabled=True, catalog=catalog, max_terms=8)
    plain = index.search(plain_query, n=2)
    expanded = index.search(expanded_query, n=2)

    assert 101 not in _ids(plain)
    assert 101 in _ids(expanded)
    assert 101 in _ids(hybrid.lexical_scores(expanded_query, 2, index=index))


class _FakeVector:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, question, n):
        self.calls.append((question, n))
        return list(self.rows[:n]), {"encode_seconds": 0.0, "search_seconds": 0.0}


class _FakeLexical:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def search(self, question, n=10):
        self.calls.append((question, n))
        return list(self.rows[:n])


def test_vector_and_lexical_wrappers_delegate_and_validate_k():
    vec = _FakeVector([{"chunk_id": 1, "similarity": 0.9}])
    lex = _FakeLexical([{"chunk_id": 2, "lexical_score": 3.0}])

    assert hybrid.vector_scores("问题", 3, searcher=vec)[0]["chunk_id"] == 1
    assert hybrid.lexical_scores("问题", 3, index=lex)[0]["chunk_id"] == 2
    assert vec.calls == [("问题", 3)]
    assert lex.calls == [("问题", 3)]
    with pytest.raises(ValueError, match="正整数"):
        hybrid.vector_scores("问题", 0, searcher=vec)
    with pytest.raises(ValueError, match="正整数"):
        hybrid.lexical_scores("问题", 0, index=lex)


def test_hybrid_search_default_equals_rrf_60_and_is_deterministic():
    vec_rows = [
        {"chunk_id": 1, "similarity": 0.9},
        {"chunk_id": 2, "similarity": 0.8},
        {"chunk_id": 3, "similarity": 0.7},
    ]
    lex_rows = [
        {"chunk_id": 2, "lexical_score": 8.0},
        {"chunk_id": 3, "lexical_score": 7.0},
        {"chunk_id": 4, "lexical_score": 6.0},
    ]
    vec = _FakeVector(vec_rows)
    lex = _FakeLexical(lex_rows)
    expected = hybrid.rrf({"vector": vec_rows, "lexical": lex_rows}, k=60)

    first = hybrid.hybrid_search(
        "问题", vector_searcher=vec, lexical_index=lex, expand=False)
    second = hybrid.hybrid_search(
        "问题", vector_searcher=vec, lexical_index=lex, expand=False)

    assert first == second == expected
    assert vec.calls == [("问题", 20), ("问题", 20)]
    assert lex.calls == [("问题", 20), ("问题", 20)]


def test_hybrid_search_score_mode_and_parameter_validation():
    vec = _FakeVector([
        {"chunk_id": 1, "similarity": 0.9},
        {"chunk_id": 2, "similarity": 0.8},
    ])
    lex = _FakeLexical([
        {"chunk_id": 2, "lexical_score": 8.0},
        {"chunk_id": 1, "lexical_score": 7.0},
    ])

    rows = hybrid.hybrid_search(
        "问题", k=1, retrieval_k=2, method="zscore", alpha=0.3,
        vector_searcher=vec, lexical_index=lex)

    assert len(rows) == 1
    assert rows[0]["chunk_id"] == 2
    with pytest.raises(ValueError, match="retrieval_k"):
        hybrid.hybrid_search(
            "问题", k=3, retrieval_k=2, vector_searcher=vec, lexical_index=lex)
    with pytest.raises(ValueError, match="method"):
        hybrid.hybrid_search(
            "问题", method="unknown", vector_searcher=vec, lexical_index=lex)
