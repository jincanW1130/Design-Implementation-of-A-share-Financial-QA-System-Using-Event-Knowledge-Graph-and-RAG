# -*- coding: utf-8 -*-
"""C 线独立重算：四项指标（不 import metrics）"""
import io, json, os, sys

ROOT = r"C:\Users\15129\Desktop\毕业设计"
P7 = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统")
OUT = os.path.join(P7, "检索产出")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

trace = {r["qid"]: r for r in load_jsonl(os.path.join(OUT, "per_question_trace.jsonl"))}
questions = {r["qid"]: r for r in load_jsonl(os.path.join(P7, "预实验问题集", "questions.jsonl"))}
mrows = load_jsonl(os.path.join(OUT, "metrics_pre.jsonl"))
meta = [r for r in mrows if r.get("record_type") == "metrics_meta"]
avg = [r for r in mrows if r.get("record_type") == "average"]
perq = [r for r in mrows if r.get("record_type") not in ("metrics_meta", "average")]

print("rows: meta=%d perq=%d avg=%d" % (len(meta), len(perq), len(avg)))
K = meta[0]["K"]
print("K in metrics meta =", K, "; k_selection K =",
      json.load(io.open(os.path.join(OUT, "k_selection.json"), encoding="utf-8"))["selected"]["K"])

def norm_ids(ids):
    out, seen = [], set()
    for x in ids or []:
        s = str(x)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out

def mine(final_ids, gold_ids, K):
    top = norm_ids(final_ids)[:K]
    gold = set(norm_ids(gold_ids))
    n_hit = len(set(top) & gold)
    recall = (n_hit / len(gold)) if gold else 0.0
    precision = (n_hit / K)                 # 分母恒为 K
    mrr = 0.0
    for i, c in enumerate(top, 1):
        if c in gold:
            mrr = 1.0 / i
            break
    complete = 1.0 if (gold and gold <= set(top)) else 0.0
    return {"recall_at_k": round(recall, 8), "precision_at_k": round(precision, 8),
            "mrr": round(mrr, 8), "complete_evidence_recall_at_k": complete,
            "n_hit": n_hit, "n_gold": len(gold), "n_final": len(top)}

print()
print("== 逐题对拍（我重算 vs metrics_pre.jsonl）==")
print("%-6s %-9s %-9s %-9s %-9s" % ("qid", "recall", "precision", "mrr", "complete"))
bad = []
mine_rows = []
for qid in sorted(questions, key=lambda q: (len(q), q)):
    q = questions[qid]
    t = trace.get(qid)
    final_ids = t["final_evidence_chunk_ids"] if t else []
    gold_ids = q["gold_evidence_chunk_ids"]
    if t:
        assert t["k"] == K, (qid, t["k"])
    m = mine(final_ids, gold_ids, K)
    mine_rows.append((qid, m))
    rec = next((r for r in perq if r["qid"] == qid), None)
    diffs = []
    for k in ("recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k"):
        a = m[k]
        b = rec[k]
        if abs(float(a) - float(b)) > 1e-12:
            diffs.append("%s mine=%r file=%r" % (k, a, b))
    if rec.get("n_gold") != m["n_gold"] or rec.get("n_final") != m["n_final"] or rec.get("n_hit") != m["n_hit"]:
        diffs.append("counts mine n_gold=%d n_final=%d n_hit=%d file n_gold=%s n_final=%s n_hit=%s"
                     % (m["n_gold"], m["n_final"], m["n_hit"], rec.get("n_gold"), rec.get("n_final"), rec.get("n_hit")))
    # gold ids equality
    if norm_ids(rec.get("gold_ids")) != norm_ids(gold_ids):
        diffs.append("gold_ids differ")
    if norm_ids(rec.get("final_ids")) != norm_ids(final_ids)[:K]:
        diffs.append("final_ids differ")
    print("%-6s %-9s %-9s %-9s %-9s %s" % (qid, m["recall_at_k"], m["precision_at_k"],
                                            m["mrr"], m["complete_evidence_recall_at_k"],
                                            "" if not diffs else " <<< " + "; ".join(diffs)))
    if diffs:
        bad.append((qid, diffs))

n = len(mine_rows)
avg_mine = {k: round(sum(r[1][k] for r in mine_rows) / n, 8)
            for k in ("recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k")}
print()
print("== 平均值对拍 ==")
print("%-32s %-14s %-14s %s" % ("metric", "file", "mine", "match"))
for k, v in avg_mine.items():
    fv = avg[0][k]
    print("%-32s %-14s %-14s %s" % (k, fv, v, abs(float(fv) - v) < 1e-12))

print()
print("== 边界与分母体检 ==")
print("empty gold in questions:", sum(1 for q in questions.values() if not q["gold_evidence_chunk_ids"]))
print("empty final in trace  :", sum(1 for t in trace.values() if not t["final_evidence_chunk_ids"]))
nfinal = sorted(len(t["final_evidence_chunk_ids"]) for t in trace.values())
print("final set sizes (min..max):", nfinal[0], "..", nfinal[-1], "| <K count:", sum(1 for x in nfinal if x < K))
print("precision identity check: file precision == n_hit/K for all rows:",
      all(abs(r["precision_at_k"] - r["n_hit"] / K) < 1e-12 for r in perq))
print("avg precision == mean(n_hit/K):", round(sum(r["n_hit"] for r in perq) / (n * K), 8))

print()
print("mismatches:", len(bad))
for qid, d in bad:
    print(" ", qid, d)
