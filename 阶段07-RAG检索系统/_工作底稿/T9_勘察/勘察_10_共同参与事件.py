# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 10：多公司共同参与事件一览（含证据块与所属文档是否在 66 篇内）。"""

import csv
import io
import json
import os
import sys
from collections import defaultdict

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
DOCS = {d["doc_id"]: d for d in iter_jsonl(os.path.join(DATA, "clean", "documents.jsonl"))}
CHUNKS = {c["chunk_id"]: c for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl"))}

with io.open(os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "时间子集_ge2.json"), encoding="utf-8") as f:
    GE2 = set(json.load(f).keys())

ev_companies = defaultdict(set)
ev_chunks = defaultdict(set)
for e in edges:
    if e["relation"] == "PARTICIPATES_IN":
        h = node_by_id[e["head_id"]]
        if h["label"] == "Company":
            ev_companies[e["tail_id"]].add(e["head_id"])
        if e["source_chunk_id"]:
            ev_chunks[e["tail_id"]].add(e["source_chunk_id"])

print("多公司共同参与事件：")
for ev, comps in sorted(ev_companies.items()):
    if len(comps) < 2:
        continue
    nd = node_by_id[ev]
    docs = sorted({str(CHUNKS[int(c)]["doc_id"]) for c in ev_chunks[ev]})
    in66 = [d for d in docs if d in GE2]
    print("%s | %s | %s | %s" % (ev, nd["event_type"], nd["event_time"], nd["event_name"][:44]))
    print("    公司: %s" % "、".join(node_by_id[c]["name"] for c in sorted(comps)))
    print("    证据块: %s | 文档: %s | 在66篇内: %s" % (
        ",".join(sorted(ev_chunks[ev])), ",".join(docs), ",".join(in66) or "无"))
