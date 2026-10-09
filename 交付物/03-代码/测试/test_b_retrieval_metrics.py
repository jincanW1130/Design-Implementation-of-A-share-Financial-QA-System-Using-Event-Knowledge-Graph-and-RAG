# -*- coding: utf-8 -*-
"""B 组 · 四项检索指标的边界 —— 被测文件：`代码\\检索\\metrics.py`。

口径出处：《02》第12.7节 的四项定义 ＋ 第12.4节 的 K 定义 ＋ 第五节 硬约束 7／8。
被测的四个纯函数只吃 `chunk_id`：`recall_at_k`／`precision_at_k`／`mrr`／
`complete_evidence_recall_at_k`，另加逐题行 `evaluate_question_chunk_level` 与
两个聚合器（chunk 级／文档级诊断**不得混算**）。

边界清单（评审 P1-12 点名要覆盖的）：
空 gold、gold 全不在 Top-K、gold 恰好在第 K 位、gold 数 > K、重复 chunk_id，
以及"M < K 时分母恒为 K"与"|final| > K 时四项指标都只看前 K 个"两条回归。

本文件是**纯计算**测试：不读索引、不读图谱、不联网、不调模型。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

metrics = _bootstrap.load_module("检索", "metrics.py")

K = 10


# ---------------------------------------------------------------------------
# B1 完全命中 / 部分命中：四项指标的基本口径
# ---------------------------------------------------------------------------
def test_full_hit_all_four_metrics():
    final, gold = ["c1", "c2", "c3"], ["c1", "c2"]
    assert metrics.recall_at_k(final, gold, 5) == 1.0
    assert metrics.complete_evidence_recall_at_k(final, gold, 5) == 1.0
    assert metrics.precision_at_k(final, gold, 5) == 0.4          # 2 命中 ÷ K=5
    assert metrics.mrr(final, gold) == 1.0                        # 首个命中在第 1 位


def test_partial_hit_metrics():
    final, gold = ["c1", "x", "y"], ["c1", "c2"]
    assert metrics.recall_at_k(final, gold, 5) == 0.5
    assert metrics.complete_evidence_recall_at_k(final, gold, 5) == 0.0
    assert metrics.precision_at_k(final, gold, 5) == 0.2
    assert metrics.mrr(["x", "y", "c1"], gold) == metrics._r(1.0 / 3)


# ---------------------------------------------------------------------------
# B2 边界一：空 gold（分母为 0，定义上不可召回 → 一律记 0，且**不抛异常**）
# ---------------------------------------------------------------------------
def test_empty_gold_returns_zero_without_raising():
    assert metrics.recall_at_k(["a"], [], K) == 0.0
    assert metrics.precision_at_k(["a"], [], K) == 0.0
    assert metrics.mrr(["a"], []) == 0.0
    assert metrics.complete_evidence_recall_at_k(["a"], [], K) == 0.0
    row = metrics.evaluate_question_chunk_level(["a"], [], K, qid="B-EMPTY-GOLD")
    assert row["n_gold"] == 0 and row["n_hit"] == 0
    assert [row[key] for key in metrics.CHUNK_METRIC_KEYS] == [0.0, 0.0, 0.0, 0.0]


def test_empty_final_returns_zero_without_raising():
    assert metrics.recall_at_k([], ["a"], K) == 0.0
    assert metrics.precision_at_k([], ["a"], K) == 0.0
    assert metrics.mrr([], ["a"]) == 0.0
    assert metrics.complete_evidence_recall_at_k([], ["a"], K) == 0.0


# ---------------------------------------------------------------------------
# B3 边界二：gold 全不在 Top-K
# ---------------------------------------------------------------------------
def test_gold_entirely_outside_top_k():
    final = ["n%02d" % i for i in range(1, 11)]
    gold = ["g1", "g2"]
    assert metrics.recall_at_k(final, gold, K) == 0.0
    assert metrics.precision_at_k(final, gold, K) == 0.0
    assert metrics.mrr(final, gold) == 0.0
    assert metrics.complete_evidence_recall_at_k(final, gold, K) == 0.0


# ---------------------------------------------------------------------------
# B4 边界三：gold 恰好在第 K 位（在）与第 K+1 位（不在）
# ---------------------------------------------------------------------------
def test_gold_exactly_at_position_k_is_inside():
    final = ["n%02d" % i for i in range(1, K)] + ["gold-at-K"]     # 第 10 位是 gold
    gold = ["gold-at-K"]
    assert len(final) == K and final[K - 1] == "gold-at-K"
    assert metrics.recall_at_k(final, gold, K) == 1.0
    assert metrics.complete_evidence_recall_at_k(final, gold, K) == 1.0
    assert metrics.mrr(final, gold) == metrics._r(1.0 / K)
    assert metrics.precision_at_k(final, gold, K) == metrics._r(1.0 / K)


def test_gold_at_position_k_plus_one_is_outside():
    final = ["n%02d" % i for i in range(1, K + 1)] + ["gold-at-K+1"]
    gold = ["gold-at-K+1"]
    row = metrics.evaluate_question_chunk_level(final, gold, K, qid="B-K+1")
    assert row["n_final"] == K, "逐题行的 final_ids 必须截断到前 K 个"
    assert row["n_hit"] == 0
    assert row["recall_at_k"] == 0.0
    assert row["complete_evidence_recall_at_k"] == 0.0
    assert row["mrr"] == 0.0, "第 K+1 位的 gold 不在 Top-K 内，MRR 记 0"


# ---------------------------------------------------------------------------
# B5 边界四：gold 数 > K（Recall 的分母是 gold 总数，不是 K）
# ---------------------------------------------------------------------------
def test_gold_count_larger_than_k():
    final = ["g%02d" % i for i in range(1, 13)]                    # 12 条，全部是 gold
    gold = list(final)
    assert len(gold) > K
    assert metrics.recall_at_k(final, gold, K) == metrics._r(K / len(gold))
    assert metrics.precision_at_k(final, gold, K) == 1.0            # 前 K 个全是 gold
    assert metrics.complete_evidence_recall_at_k(final, gold, K) == 0.0, \
        "gold 未被完整召回 ⇒ 问题级指标记 0"


# ---------------------------------------------------------------------------
# B6 边界五：重复 chunk_id（集合语义：同一文本块只算一次）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("final", [
    ["a", "a", "b"],
    ("a", "b"),
    ["a", "b", "a", "b"],
])
def test_duplicate_chunk_ids_are_set_semantics(final):
    gold = ["a"]
    assert metrics.recall_at_k(final, gold, 5) == 1.0
    assert metrics.precision_at_k(final, gold, 5) == metrics._r(1.0 / 5)
    assert metrics.mrr(final, gold) == 1.0, "去重后首个命中仍排在第 1 位"


def test_set_input_has_no_order_but_still_counts_once():
    """集合输入没有"第几位"可言：召回／精度按集合语义，MRR 只能取到"命中在 1 或 2 位"。

    这条用例的作用是把"MRR 依赖**顺序**、其余三项依赖**集合**"这一口径差别写明——
    调用方要给 MRR 传有序表（`evaluate_question_chunk_level` 传的正是 `final[:K]`）。
    """
    final, gold = {"a", "b"}, ["a"]
    assert metrics.recall_at_k(final, gold, 5) == 1.0
    assert metrics.precision_at_k(final, gold, 5) == metrics._r(1.0 / 5)
    assert metrics.mrr(final, gold) in (1.0, 0.5)


def test_duplicate_gold_ids_do_not_inflate_the_denominator():
    assert metrics.recall_at_k(["a"], ["a", "a", "a"], K) == 1.0
    assert metrics.recall_at_k(["a", "b"], ["a", "a", "b", "b"], K) == 1.0


def test_integer_and_string_chunk_ids_are_the_same_block():
    """`chunk_id` 在图谱侧是字符串、在数据集里是整数，两者必须视为同一个块。"""
    assert metrics.recall_at_k([1001001], ["1001001"], K) == 1.0
    assert metrics.recall_at_k(["1001001"], [1001001], K) == 1.0


# ---------------------------------------------------------------------------
# B7 分母恒为 K（硬约束 8）：M < K 时空缺记未命中、题目保留、不实现删题
# ---------------------------------------------------------------------------
def test_precision_denominator_is_always_k():
    final, gold = ["g1", "n1"], ["g1"]                             # M=2 < K=10
    assert metrics.precision_at_k(final, gold, K) == metrics._r(1.0 / K)
    row = metrics.evaluate_question_chunk_level(final, gold, K, qid="B-M<K")
    assert row["n_final"] == 2 and row["n_hit"] == 1
    assert row["K"] == K
    # 空缺的 K−M 个位置记未命中：命中数不得被补足
    assert row["n_hit"] == 1


def test_questions_with_fewer_candidates_are_not_dropped():
    """候选不足 K（含候选为空的题）照样产出逐题行——**不实现运行时的删题**（硬约束 8）。"""
    questions = {
        "B-01": {"qid": "B-01", "gold_evidence_chunk_ids": ["g1"], "task_type": "事实型"},
        "B-02": {"qid": "B-02", "gold_evidence_chunk_ids": ["g1"], "task_type": "事实型"},
    }
    final_by_qid = {"B-01": ["n1", "n2"], "B-02": []}
    rows = metrics.build_rows(questions, final_by_qid, K, "本用例构造")
    assert [row["qid"] for row in rows] == ["B-01", "B-02"]
    assert [row["n_final"] for row in rows] == [2, 0]
    assert all(row["K"] == K for row in rows)
    assert rows[1]["precision_at_k"] == 0.0 and rows[1]["n_hit"] == 0


# ---------------------------------------------------------------------------
# B8 |final| > K：四项指标只能看前 K 个（B-15 回归；旧实现给出 n_hit=0 而 mrr>0）
# ---------------------------------------------------------------------------
def test_mrr_uses_only_the_first_k_when_final_exceeds_k():
    final = ["c%02d" % i for i in range(1, 13)]                    # 12 条 > K
    gold_late = ["c11"]                                            # 只落在第 11 名（K 之外）
    row = metrics.evaluate_question_chunk_level(final, gold_late, K, qid="B-B15")
    assert row["n_final"] == K and row["n_hit"] == 0
    assert row["recall_at_k"] == 0.0 and row["precision_at_k"] == 0.0
    assert row["mrr"] == 0.0, "mrr 必须与 n_hit／recall 同源（旧实现在此给 1/11）"
    assert row["mrr"] == metrics.mrr(final[:K], gold_late)

    gold_early = ["c03"]
    row2 = metrics.evaluate_question_chunk_level(final, gold_early, K, qid="B-B15B")
    assert row2["n_hit"] == 1 and row2["mrr"] == metrics._r(1.0 / 3)


def test_b15_regression_guard_really_catches_the_old_implementation(monkeypatch):
    """**负向标定**：把 `mrr` 钉成"按未截断的 final 找首个命中"会给的读数，上面那条用例的
    判据必须立刻不成立——否则它只是"看起来在测"。

    B-15 修订前的调用点是 `mrr(final, gold)`（未截断），`|final| > K` 且 gold 落在第 K 名
    之后时会给出 `n_hit=0` 而 `mrr=1/11` 的矛盾读数；修订后统一用 `top = final[:K]`。
    """
    final = ["c%02d" % i for i in range(1, 13)]
    gold_late = ["c11"]
    # ① 旧读数：未截断 → 1/11
    assert metrics.mrr(final, gold_late) == metrics._r(1.0 / 11)
    # ② 现行读数：只看前 K 个 → 0，且与 n_hit 同源
    row = metrics.evaluate_question_chunk_level(final, gold_late, K, qid="B-B15-CAL")
    assert (row["n_final"], row["n_hit"], row["mrr"]) == (K, 0, 0.0)
    # ③ 标定：把 mrr 换回旧读数，本条用例的 mrr 判据立刻不成立
    monkeypatch.setattr(metrics, "mrr", lambda ids, gold_ids: metrics._r(1.0 / 11))
    broken = metrics.evaluate_question_chunk_level(final, gold_late, K, qid="B-B15-CAL")
    assert broken["mrr"] == metrics._r(1.0 / 11) != row["mrr"]
    assert broken["mrr"] != 0.0, "旧读数下本用例必然失败 ⇒ 判据有效（负向标定）"


# ---------------------------------------------------------------------------
# B9 逐题行可独立重算（固定精度 8 位；同一输入两次调用逐字节一致）
# ---------------------------------------------------------------------------
def test_question_row_is_recomputable_and_rounds_to_eight_digits():
    final, gold = ["a", "b", "c"], ["a", "d", "e"]
    row = metrics.evaluate_question_chunk_level(final, gold, 7, qid="B-RECOMPUTE")
    assert row["recall_at_k"] == metrics.recall_at_k(row["final_ids"], row["gold_ids"], row["K"])
    assert row["precision_at_k"] == metrics.precision_at_k(row["final_ids"], row["gold_ids"], row["K"])
    assert row["mrr"] == metrics.mrr(row["final_ids"], row["gold_ids"])
    assert row["complete_evidence_recall_at_k"] == metrics.complete_evidence_recall_at_k(
        row["final_ids"], row["gold_ids"], row["K"])
    assert metrics.evaluate_question_chunk_level(final, gold, 7, qid="B-RECOMPUTE") == row
    assert row["recall_at_k"] == round(row["recall_at_k"], 8)
    assert metrics.ROUND == 8


def test_invalid_k_raises():
    with pytest.raises(ValueError):
        metrics.precision_at_k(["a"], ["a"], 0)
    with pytest.raises(ValueError):
        metrics.evaluate_question_chunk_level(["a"], ["a"], -1)


# ---------------------------------------------------------------------------
# B10 文档级诊断与 chunk 级**不得混算**（硬约束 7）
# ---------------------------------------------------------------------------
def test_doc_level_diagnostic_cannot_be_mixed_into_chunk_level_average():
    doc_row = metrics.recall_at_k_doc_level_diagnostic(["d1", "d2"], ["d1"], K)
    assert doc_row["level"] == "document"
    assert "recall_at_k_doc_level" in doc_row and "recall_at_k" not in doc_row
    with pytest.raises(ValueError):
        metrics.aggregate_chunk_level([doc_row], "文档级行不得进 chunk 级平均值", K=K)

    chunk_rows = [metrics.evaluate_question_chunk_level(["a"], ["a"], K, qid="B-01")]
    with pytest.raises(ValueError):
        metrics.aggregate_doc_level_diagnostic(chunk_rows, "chunk 级行不得进文档级聚合", K=K)


def test_chunk_level_average_is_arithmetic_mean_over_questions():
    rows = [metrics.evaluate_question_chunk_level(["a"], ["a"], K, qid="B-01"),
            metrics.evaluate_question_chunk_level([], ["z"], K, qid="B-02")]
    avg = metrics.aggregate_chunk_level(rows, "本测试的 2 题", K=K)
    assert avg["level"] == "chunk" and avg["n_questions"] == 2
    assert avg["n_empty_final"] == 1 and avg["n_empty_gold"] == 0
    assert avg["recall_at_k"] == metrics._r((1.0 + 0.0) / 2)
    assert avg["complete_evidence_recall_at_k"] == metrics._r((1.0 + 0.0) / 2)
    assert set(metrics.CHUNK_METRIC_KEYS) <= set(avg)
