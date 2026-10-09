import json, io, os
P = r"C:\Users\15129\Desktop\毕业设计\交付物/05-系统实现/RAG检索系统\预实验问题集\questions.jsonl"
rows = [json.loads(l) for l in io.open(P, encoding="utf-8") if l.strip()]
out = ["| qid | task | hop | time | gold数 | gold_evidence_rule | docs | anchors数 | anchor块集==gold? | 无锚点的gold块 |",
       "|---|---|---|---|---|---|---|---|---|---|"]
noanchor_total = 0
mismatch = []
for r in rows:
    gold = sorted(r["gold_evidence_chunk_ids"])
    anchors = sorted({a["chunk_id"] for a in r["gold_verify_anchors"]})
    missing = sorted(set(gold) - set(anchors))
    noanchor_total += len(missing)
    if missing: mismatch.append((r["qid"], missing))
    docs = r["gold_evidence_doc_ids"]
    out.append("| %s | %s | %s | %s | %d | %s | %s | %d | %s | %s |" % (
        r["qid"], r["task_type"], r["gold_hop_depth"], r["time_constraint"],
        r["gold_evidence_count"], r["gold_evidence_rule"], ",".join(map(str,docs)),
        len(r["gold_verify_anchors"]),
        "是" if not missing else "否",
        ",".join(map(str,missing)) or "-"))
out.append("")
out.append("gold块总数=%d；无锚点的gold块合计=%d；涉及题=%s" % (
    sum(r["gold_evidence_count"] for r in rows), noanchor_total, mismatch))
# 锚点引用但不在 gold 内的（脚本已断言必须为0）
bad = [(r["qid"], sorted({a["chunk_id"] for a in r["gold_verify_anchors"]} - set(r["gold_evidence_chunk_ids"]))) for r in rows]
bad = [b for b in bad if b[1]]
out.append("锚点不在gold内的题=%s" % (bad or "无"))
# gold 是否超出候选规则命中集（脚本已断言）
io.open("report.md","w",encoding="utf-8").write("\n".join(out))
print("ok", len(rows))
