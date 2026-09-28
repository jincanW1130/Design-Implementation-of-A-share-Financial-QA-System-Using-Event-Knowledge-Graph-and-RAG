# -*- coding: utf-8 -*-
"""C 线：抽 ≥10 题回原文，逐题给出依据片段（供人工判定 成立／不足／多余）"""
import io, json, os, sys

ROOT = r"C:\Users\15129\Desktop\毕业设计"
P7 = os.path.join(ROOT, "阶段07-RAG检索系统")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

qs = dict((r["qid"], r) for r in load_jsonl(os.path.join(P7, "预实验问题集", "questions.jsonl")))
chunks = dict((str(r["chunk_id"]), r) for r in load_jsonl(
    os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")))

WANT = sys.argv[1:] or ["PE-01", "PE-04", "PE-06", "PE-10", "PE-11", "PE-12", "PE-13",
                        "PE-14", "PE-19", "PE-20", "PE-22", "PE-24", "PE-26", "PE-29", "PE-30"]
for q in WANT:
    r = qs[q]
    print("=" * 78)
    print("%s | %s | hop=%s | time=%s" % (q, r["task_type"], r["gold_hop_depth"], r["time_constraint"]))
    print("问：", r["question"])
    print("答：", r["reference_answer"])
    print("rule:", r["gold_evidence_rule"], "| gold:", r["gold_evidence_chunk_ids"])
    for cid in r["gold_evidence_chunk_ids"]:
        c = chunks[str(cid)]
        print("  --- chunk %s（doc %s, %d token）---" % (cid, c["doc_id"], c["token_count"]))
        body = c["content"].replace("\n", "")
        print("   ", body[:900])
    print("verify_note:", r["gold_verify_note"][:400])
