# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 04：66 篇时间子集文档明细 + 语料总体分布。"""

import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")
DATA = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1")


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def iter_jsonl(path):
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


nodes = read_csv(os.path.join(GRAPH, "nodes.csv"))
edges = read_csv(os.path.join(GRAPH, "edges.csv"))
node_by_id = {n["node_id"]: n for n in nodes}

docs = {}
for d in iter_jsonl(os.path.join(DATA, "clean", "documents.jsonl")):
    docs[d["doc_id"]] = d
chunks_by_doc = defaultdict(list)
for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl")):
    chunks_by_doc[c["doc_id"]].append(c)

print("docs:", len(docs), "chunks:", sum(len(v) for v in chunks_by_doc.values()))
print("category counts:", dict(sorted(Counter(d["category"] for d in docs.values()).items())))
print("source counts:", dict(sorted(Counter(d["source"] for d in docs.values()).items())))
print("doc_id ranges:", dict(sorted(Counter(str(d["doc_id"])[0] for d in docs.values()).items())))
print("publish_time min/max:", min(d["publish_time"] for d in docs.values()), max(d["publish_time"] for d in docs.values()))

ev_doc = defaultdict(set)
for e in edges:
    if e["relation"] != "EVIDENCED_BY":
        continue
    docid = node_by_id[e["tail_id"]]["doc_id"]
    ev_doc[docid].add(e["head_id"])

with io.open(os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "时间子集_ge2.json"), encoding="utf-8") as f:
    ge2 = {int(k): v for k, v in json.load(f).items()}

print()
print("=== 66 docs detail: doc_id | category | publish | n_chunks | n_events | n_dates | title")
rows = []
for d in sorted(ge2):
    doc = docs[d]
    dates = ge2[d]
    rows.append((d, doc["category"], doc["publish_time"], len(chunks_by_doc[d]),
                 len(ev_doc[d]), len(dates), doc["title"], dates))
    print("  %5d | %-4s | %s | %3d | %3d | %d | %s" % (
        d, doc["category"], doc["publish_time"], len(chunks_by_doc[d]), len(ev_doc[d]),
        len(dates), doc["title"][:58]))

print()
print("=== 66 docs: chunk counts distribution")
print(sorted(Counter(r[3] for r in rows).items()))

print()
print("=== top docs by chunk count in whole corpus")
top = sorted(chunks_by_doc.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:15]
for d, cs in top:
    doc = docs[d]
    print("  doc %5d | chunks %3d | %-4s | %s | %s" % (d, len(cs), doc["category"], doc["publish_time"], doc["title"][:60]))
