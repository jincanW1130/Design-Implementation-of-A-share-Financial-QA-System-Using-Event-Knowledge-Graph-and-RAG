# -*- coding: utf-8 -*-
"""C 线：题集与 gold 的硬度复核（只读）"""
import csv, io, json, os, re
from collections import defaultdict, Counter

ROOT = r"C:\Users\15129\Desktop\毕业设计"
P7 = os.path.join(ROOT, "阶段07-RAG检索系统")
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

qs = load_jsonl(os.path.join(P7, "预实验问题集", "questions.jsonl"))
chunks = {str(r["chunk_id"]): r for r in load_jsonl(
    os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl"))}

def read_csv(p):
    with io.open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

nodes = read_csv(os.path.join(GRAPH, "nodes.csv"))
edges = read_csv(os.path.join(GRAPH, "edges.csv"))
node_by_id = {n["node_id"]: n for n in nodes}

print("=" * 70)
print("A. gold 证据块 存在性 / doc 一致性 / 数量")
print("=" * 70)
bad = []
for q in qs:
    for cid in q["gold_evidence_chunk_ids"]:
        c = chunks.get(str(cid))
        if c is None:
            bad.append((q["qid"], cid, "NOT_IN_CHUNKS"))
        elif int(c["doc_id"]) not in q["gold_evidence_doc_ids"]:
            bad.append((q["qid"], cid, "DOC_MISMATCH chunk_doc=%s gold_docs=%s" % (c["doc_id"], q["gold_evidence_doc_ids"])))
    # 反向：gold doc 是否至少有一个 gold chunk 落在其中
    docs_of_gold = {int(chunks[str(c)]["doc_id"]) for c in q["gold_evidence_chunk_ids"] if str(c) in chunks}
    extra = set(q["gold_evidence_doc_ids"]) - docs_of_gold
    if extra:
        bad.append((q["qid"], "-", "GOLD_DOC_WITHOUT_CHUNK %s" % sorted(extra)))
print("问题数:", len(qs), "| 异常条目:", len(bad))
for b in bad:
    print("  ", b)

n_golds = [(q["qid"], len(q["gold_evidence_chunk_ids"])) for q in qs]
mx = max(n for _, n in n_golds)
print("逐题 gold 数:", dict(n_golds))
print("最大 gold 数:", mx, "| 声明 gold_evidence_count 与列表长度一致:",
      all(q["gold_evidence_count"] == len(q["gold_evidence_chunk_ids"]) for q in qs))

print()
print("=" * 70)
print("B. gold_evidence_rule 与 gold 的自洽（16 题写「文档内全部文本块」）")
print("=" * 70)
for q in qs:
    if q["gold_evidence_rule"] != "文档内全部文本块":
        continue
    per_doc = defaultdict(list)
    for cid in q["gold_evidence_chunk_ids"]:
        c = chunks.get(str(cid))
        if c:
            per_doc[int(c["doc_id"])].append(str(cid))
    for d, ids in sorted(per_doc.items()):
        allchunks = sorted([c for c, v in chunks.items() if int(v["doc_id"]) == d])
        missing = [c for c in allchunks if c not in set(ids)]
        print("%-6s doc=%-5d gold块=%-3d 该文档总块=%-3d 缺=%s %s" % (
            q["qid"], d, len(ids), len(allchunks),
            ("%d %s" % (len(missing), missing[:8])) if missing else "0",
            "" if not missing else "<-- rule 与 gold 不一致"))

print()
print("=" * 70)
print("C. gold_verify_anchors：锚点块是否在 gold 内 + 引文是否能在该块原文中逐字命中")
print("=" * 70)
def norm_space(s):
    return re.sub(r"\s+", "", s or "")
anch_bad = []
for q in qs:
    gset = {str(c) for c in q["gold_evidence_chunk_ids"]}
    for a in q["gold_verify_anchors"]:
        cid = str(a["chunk_id"])
        c = chunks.get(cid)
        if c is None:
            anch_bad.append((q["qid"], cid, "anchor chunk 不在 chunks"));
            continue
        if cid not in gset:
            anch_bad.append((q["qid"], cid, "anchor 不在 gold 内"))
        if norm_space(a["quote"]) not in norm_space(c["content"]):
            anch_bad.append((q["qid"], cid, "引文未在该块原文命中: " + a["quote"][:40]))
print("锚点总数:", sum(len(q["gold_verify_anchors"]) for q in qs), "| 异常:", len(anch_bad))
for b in anch_bad:
    print("  ", b)

print()
print("=" * 70)
print("D. 时间约束 12 题：gold 文档是否都落在「≥2 个不同 event_time 日期」的文档集合")
print("=" * 70)
ev_edges = [e for e in edges if e["relation"] == "EVIDENCED_BY"]
print("EVIDENCED_BY 边数:", len(ev_edges))
event_doc = defaultdict(set)
for e in ev_edges:
    h, t = node_by_id.get(e["head_id"]), node_by_id.get(e["tail_id"])
    if h is None or t is None:
        continue
    if h["label"] == "Event" and t["label"] == "Document":
        event_doc[e["head_id"]].add(t["doc_id"])
    elif t["label"] == "Event" and h["label"] == "Document":
        event_doc[e["tail_id"]].add(h["doc_id"])
doc_dates = defaultdict(set)
events = [n for n in nodes if n["label"] == "Event"]
unlinked = 0
for ev in events:
    et = (ev["event_time"] or "").strip()
    if not et:
        continue
    docs = event_doc.get(ev["node_id"])
    if not docs:
        unlinked += 1
        continue
    for d in docs:
        doc_dates[d].add(et)
ge2 = {int(d) for d, s in doc_dates.items() if len(s) >= 2}
print("事件数:", len(events), "| 有 event_time 但无 EVIDENCED_BY 文档:", unlinked)
print("≥2 日期文档数:", len(ge2))
tw = [q for q in qs if q["time_constraint"] == "有"]
print("时间约束题数:", len(tw))
for q in tw:
    gd = set(q["gold_evidence_doc_ids"])
    ok = gd <= ge2
    print("%-6s gold_docs=%s all_in_ge2=%s %s | window=%s" % (
        q["qid"], sorted(gd), ok, "" if ok else "<<< 不在 ≥2日期集合: %s" % sorted(gd - ge2),
        q["time_window"]["label"] if q.get("time_window") else None))
