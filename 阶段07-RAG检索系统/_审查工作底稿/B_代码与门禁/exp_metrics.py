# -*- coding: utf-8 -*-
"""对抗实验：metrics.py 的边界与混算拦截。在镜像里跑（只读工作区）。"""
import os
import sys

MIR = r"C:\Users\15129\AppData\Local\Temp\re7_B\mirror"
sys.path.insert(0, os.path.join(MIR, "代码", "检索"))
import metrics as M  # noqa: E402

def show(tag, fn):
    try:
        print("%-46s -> %r" % (tag, fn()))
    except Exception as exc:
        print("%-46s -> %s: %s" % (tag, type(exc).__name__, exc))

print("== 1. Precision@K 分母是否恒为 K（M<K）==")
show("P@K(final=3项, gold=1项命中, K=10)", lambda: M.precision_at_k([1, 2, 3], [1], 10))
show("  = 1/10 ?", lambda: M.precision_at_k([1, 2, 3], [1], 10) == 0.1)
show("P@K(final=10项命中3, K=10)", lambda: M.precision_at_k(list(range(10)), [0, 1, 2], 10))
show("P@K(final=空, K=10)", lambda: M.precision_at_k([], [1, 2], 10))
show("P@K(gold=空, K=10)", lambda: M.precision_at_k([1, 2], [], 10))
show("P@K(K=0) 期望抛错", lambda: M.precision_at_k([1], [1], 0))

print()
print("== 2. 空 gold / 空 final 边界（是否抛异常）==")
show("recall 空gold", lambda: M.recall_at_k([1], [], 10))
show("recall 空final", lambda: M.recall_at_k([], [1], 10))
show("mrr 空gold", lambda: M.mrr([1], []))
show("mrr 空final", lambda: M.mrr([], [1]))
show("cer 空gold", lambda: M.complete_evidence_recall_at_k([1], [], 10))
show("cer 空final", lambda: M.complete_evidence_recall_at_k([], [1], 10))
show("doc级 空gold", lambda: M.recall_at_k_doc_level_diagnostic([], [], 10))
show("doc级 空final", lambda: M.recall_at_k_doc_level_diagnostic([], ["d1"], 10))

print()
print("== 3. 文档级 / chunk 级混算拦截 ==")
row_chunk = M.evaluate_question_chunk_level([1, 2], [1], 10, qid="Q1")
row_doc = M.recall_at_k_doc_level_diagnostic(["d1"], ["d1"], 10)
show("aggregate_chunk_level(混入 document 行)",
     lambda: M.aggregate_chunk_level([row_chunk, row_doc], "x"))
show("aggregate_doc_level_diagnostic(混入 chunk 行)",
     lambda: M.aggregate_doc_level_diagnostic([row_doc, row_chunk], "x"))
show("aggregate_chunk_level(纯 chunk 行)",
     lambda: M.aggregate_chunk_level([row_chunk], "x")["recall_at_k"])

print()
print("== 4. 关键一致性攻击：final_ids 超过 K 个时 MRR 是否只用前 K ==")
r = M.evaluate_question_chunk_level([11, 12, 13], [13], 2, qid="Qx")
print("  evaluate_question_chunk_level(final=[11,12,13], gold=[13], K=2)")
for k in ("K", "n_final", "n_hit", "recall_at_k", "precision_at_k", "mrr",
          "complete_evidence_recall_at_k"):
    print("     %-30s = %r" % (k, r[k]))
print("  自洽性：n_hit=0 却 mrr>0 ？（前 K 内无 gold，按《02》应记 0）")
print("      -> n_hit=%r  mrr=%r  不一致=%s" % (r["n_hit"], r["mrr"], r["n_hit"] == 0 and r["mrr"] > 0))
print("  若先截断到 K 再算：mrr=%r" % M.mrr([11, 12], [13]))

print()
print("== 5. 字符串/整数 chunk_id 归一 ==")
show("P@K('1001' vs 1001)", lambda: M.precision_at_k(["1001"], [1001], 10))
show("recall('1001' vs 1001)", lambda: M.recall_at_k(["1001"], [1001], 10))
