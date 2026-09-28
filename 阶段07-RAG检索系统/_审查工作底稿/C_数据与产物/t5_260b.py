# -*- coding: utf-8 -*-
"""C 线：260 条参照集的 chunk_id 与 30 题 gold / 检索结果 的交集"""
import io, json, os, re

ROOT = r"C:\Users\15129\Desktop\毕业设计"
WS = os.path.join(ROOT, "阶段05-数据准备", "数据集", "抽取评测集", "v2.1",
                  "自动标注_flash", "工作区")
P7 = os.path.join(ROOT, "阶段07-RAG检索系统")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

ref = {}
for sub in ("dev", "test"):
    d = os.path.join(WS, sub)
    for name in sorted(os.listdir(d)):
        s = io.open(os.path.join(d, name), encoding="utf-8", errors="replace").read(2000)
        m = re.search(r'"item_id":\s*"([^"]+)".*?"chunk_id":\s*(\d+),\s*"doc_id":\s*(\d+)', s, re.S)
        if m:
            ref[m.group(1)] = (int(m.group(2)), int(m.group(3)))
ref_chunks = set(c for c, _d in ref.values())
ref_docs = set(d for _c, d in ref.values())
print("参照集条目 =", len(ref), "｜不同 chunk =", len(ref_chunks), "｜不同 doc =", len(ref_docs))
print("参照集 doc 号（前 40）= ", sorted(ref_docs)[:40])

qs = load_jsonl(os.path.join(P7, "预实验问题集", "questions.jsonl"))
gold_chunks = set()
gold_docs = set()
src_docs = set()
for q in qs:
    gold_chunks |= set(int(c) for c in q["gold_evidence_chunk_ids"])
    gold_docs |= set(int(c) for c in q["gold_evidence_doc_ids"])
    for s in q["source_material"]:
        src_docs.add(int(s["doc_id"]))
print()
print("30 题 gold 块 =", len(gold_chunks), "｜gold 文档 =", len(gold_docs),
      "｜题面文档 =", len(src_docs), "｜并集文档 =", len(gold_docs | src_docs))
inter_c = sorted(gold_chunks & ref_chunks)
inter_d = sorted((gold_docs | src_docs) & ref_docs)
print("gold 块 ∩ 参照集块 =", len(inter_c), inter_c)
print("题目文档 ∩ 参照集文档 =", len(inter_d), inter_d)

trace = load_jsonl(os.path.join(P7, "检索产出", "per_question_trace.jsonl"))
final_chunks = set()
for t in trace:
    final_chunks |= set(int(c) for c in t["final_evidence_chunk_ids"])
print("检索最终证据（30 题并集）块数 =", len(final_chunks),
      "｜其中落在参照集块 =", len(final_chunks & ref_chunks))
