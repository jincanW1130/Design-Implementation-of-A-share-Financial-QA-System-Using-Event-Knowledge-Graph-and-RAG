# -*- coding: utf-8 -*-
"""B-15 构造用例：`|final| > K` 时四项指标必须自洽（不许出现 n_hit=0 而 mrr>0）。

旧实现：`evaluate_question_chunk_level` 里 recall／precision／CER 用 `final[:K]`，
而 mrr 用**未截断**的 `final`。当 gold 只出现在第 K 名之后时，同一题会同时出现
`n_hit=0` 与 `mrr>0`，违反《02》第12.7节「前 K 内无 gold 记 0」。

本脚本只调用 `代码\\检索\\metrics.py` 的函数；不写任何产物文件。
"""
from __future__ import annotations

import io
import os
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "代码", "检索"))

import metrics                                              # noqa: E402

K = 10
final = ["c%02d" % i for i in range(1, 13)]                  # 12 个文本块：超过 K
gold = ["c11"]                                               # 只落在第 11 名（K 之外）
gold_in = ["c03"]                                            # 落在第 3 名（K 之内）

row = metrics.evaluate_question_chunk_level(final, gold, K, qid="B15-LATENT")
row_in = metrics.evaluate_question_chunk_level(final, gold_in, K, qid="B15-INSIDE")

print("=" * 78)
print("B-15 构造用例：|final|=%d > K=%d" % (len(final), K))
print("  用例 1：gold=%s（只在第 11 名，K 之外）" % gold)
print("  用例 2：gold=%s（在第 3 名，K 之内）" % gold_in)
print("=" * 78)
print("用例 1 逐题行（旧实现会打印 mrr>0）：")
for key in ("qid", "K", "n_final", "n_gold", "n_hit", "recall_at_k", "precision_at_k", "mrr",
            "complete_evidence_recall_at_k"):
    print("  %-30s %s" % (key, row[key]))
print("用例 2 逐题行：")
for key in ("qid", "K", "n_final", "n_gold", "n_hit", "recall_at_k", "precision_at_k", "mrr",
            "complete_evidence_recall_at_k"):
    print("  %-30s %s" % (key, row_in[key]))

checks = {
    "用例 1：前 K 内无 gold → n_hit == 0": row["n_hit"] == 0,
    "用例 1：前 K 内无 gold → recall_at_k == 0": row["recall_at_k"] == 0.0,
    "用例 1：前 K 内无 gold → mrr == 0（旧实现在此处失败）": row["mrr"] == 0.0,
    "用例 1：CER@K == 0": row["complete_evidence_recall_at_k"] == 0.0,
    "用例 1：mrr 与「按 final[:K] 重算」一致":
        row["mrr"] == metrics.mrr(final[:K], gold),
    "用例 2：命中在第 3 名 → mrr == 1/3": row_in["mrr"] == round(1.0 / 3.0, 8),
    "用例 2：n_hit == 1 且 recall == 1.0": row_in["n_hit"] == 1 and row_in["recall_at_k"] == 1.0,
    "口径一致性：|final|>K 时 n_hit==0 蕴含 mrr==0":
        (row["n_hit"] == 0) == (row["mrr"] == 0.0),
}
print("-" * 78)
for label, ok in checks.items():
    print("  [%s] %s" % ("OK  " if ok else "FAIL", label))
print("-" * 78)
print("结论：%d／%d 通过 → %s"
      % (sum(checks.values()), len(checks),
         "全部通过（新实现）" if all(checks.values()) else "存在失败（旧实现的潜伏缺陷）"))
print("=" * 78)
sys.exit(0 if all(checks.values()) else 1)
