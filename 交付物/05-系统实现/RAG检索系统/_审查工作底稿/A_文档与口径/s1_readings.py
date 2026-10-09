# -*- coding: utf-8 -*-
"""s1_readings.py —— 复算《19》第 3／6 节的关键读数（只读项目树）。"""
import os, json
ROOT = r"C:\Users\15129\Desktop\毕业设计"
O = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "检索产出")
Q = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集", "questions.jsonl")
K = 10
def jl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]
tr, qs = jl(os.path.join(O, "per_question_trace.jsonl")), jl(Q)
gold = {q["qid"]: set(q["gold_evidence_chunk_ids"]) for q in qs}
R = P = M = C = 0.0
for t in tr:
    g = gold[t["qid"]]; top = t["final_evidence_chunk_ids"][:K]
    hit = len(set(top) & g)
    R += hit / len(g); P += hit / K
    M += next((1.0 / i for i, c in enumerate(top, 1) if c in g), 0.0)
    C += 1.0 if g <= set(top) else 0.0
n = len(tr)
print("[1] 独立复算四项指标（K=10，source=per_question_trace.jsonl + questions.jsonl）")
print("    n=%d  Recall@K=%.8f Precision@K=%.8f MRR=%.8f CER@K=%.8f" % (n, R/n, P/n, M/n, C/n))
avg = [r for r in jl(os.path.join(O, "metrics_pre.jsonl")) if r.get("record_type") == "average"][0]
print("    metrics_pre.jsonl 平均值行：Recall=%.8f Precision=%.8f MRR=%.8f CER=%.8f level=%s 分母=%s"
      % (avg["recall_at_k"], avg["precision_at_k"], avg["mrr"], avg["complete_evidence_recall_at_k"],
         avg["level"], avg.get("precision_denominator", "-")))
rows = jl(os.path.join(O, "pre_experiment_matrix.jsonl"))
print("\n[2] 9 格网格（round=round1_nonbinding，C 组，非约束预算）")
print("    K  N  Recall    Precision MRR       CER       text_median")
for r in rows[:9]:
    m = r["metrics"]
    print("    %-2d %-3d %.4f    %.4f    %.4f    %.4f    %s"
          % (r["K"], r["N"], m["recall_at_k"], m["precision_at_k"], m["mrr"],
             m["complete_evidence_recall_at_k"], r["occupancy"]["text_tokens"]["median"]))
r10 = rows[9]
print("\n[3] 选定格（round2_selected 第 10 行）")
print("    K=%s N=%s budget=%s g=%s metrics=%s" % (r10["K"], r10["N"], r10["context_token_budget"], r10["g"],
      {k: round(v, 8) for k, v in r10["metrics"].items()}))
print("    evidence_size.mean=%s  holding_K=%s  trimmed_paths=%s  trimmed_blocks=%s  exceeding=%s"
      % (r10["evidence_size"]["mean"], r10["budget_checks"]["questions_holding_K_blocks"],
         r10["budget_checks"]["questions_with_trimmed_paths"],
         r10["budget_checks"]["questions_with_trimmed_blocks"],
         r10["budget_checks"]["questions_exceeding_budget"]))
print("    graph_evidence_in_final=%s" % r10["graph_evidence_in_final"])
c = r10["candidates"]
print("    candidates: vector=%s graph=%s dual_hit=%s graph_only=%s union_total=%s union/q min=%s med=%s max=%s"
      % (c["vector_total"], c["graph_total"], c["dual_hit_total"], c["graph_only_total"], c["union_total"],
         c["union_per_question"]["min"], c["union_per_question"]["median"], c["union_per_question"]["max"]))
ks = json.load(open(os.path.join(O, "k_selection.json"), encoding="utf-8"))
print("\n[4] g 曲线（k_selection.json evidence.g_curve.primary_rows）")
for r in ks["evidence"]["g_curve"]["primary_rows"]:
    m = r["metrics"]
    print("    g=%s  %.4f/%.4f/%.4f/%.4f  入集 %s 个（%s 题）  不劣于g0=%s"
          % (r["g"], m["recall_at_k"], m["precision_at_k"], m["mrr"], m["complete_evidence_recall_at_k"],
             r["graph_evidence_in_final_total"], r["graph_evidence_in_final_questions"], r["not_worse_than_g0"]))
print("    criterion=%s" % ks["evidence"]["g_curve"]["criterion"][:90])
print("    rules.g_rule=%s" % ks["rules"]["g_rule"][:110])
print("\n[5] 预算余量敏感性（五档）")
for r in ks["evidence"]["budget_sensitivity"]:
    print("    预算 %s（余量 %s）g0.MRR=%s g2.MRR=%s 不劣=%s"
          % (r["context_token_budget"], r["margin"], r["g0_metrics"]["mrr"], r["g2_metrics"]["mrr"],
             r["g2_not_worse_than_g0"]))
print("\n[6] K 饱和与预算排除（evidence.saturation_under_budget.rows）")
for r in ks["evidence"]["saturation_under_budget"]["rows"]:
    print("    K=%s round1_CER=%s under_budget_CER=%s Δ=%s 预算可容=%s gold可容=%s note=%s"
          % (r["K"], r["round1_complete_evidence_recall_at_k"], r["under_budget_complete_evidence_recall_at_k"],
             r["delta_cer_vs_prev_under_budget"], r["budget_feasible"], r["gold_feasible"], r["note"]))
print("    selected=%s" % json.dumps(ks["selected"], ensure_ascii=False))
print("\n[7] N 曲线（evidence.N_curve）")
for r in ks["evidence"]["N_curve"]:
    print("    K=%s N=%s CER=%s selected=%s" % (r["K"], r["N"], r["metrics"]["complete_evidence_recall_at_k"], r["selected"]))
