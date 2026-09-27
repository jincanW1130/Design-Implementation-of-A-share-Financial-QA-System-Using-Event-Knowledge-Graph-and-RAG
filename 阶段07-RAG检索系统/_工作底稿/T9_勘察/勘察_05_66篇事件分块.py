# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 05：66 篇时间子集文档的“事件 + 分块 + 语义边”明细，落勘察文本。"""

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
OUT = os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "66篇事件与分块.txt")


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
docs = {d["doc_id"]: d for d in iter_jsonl(os.path.join(DATA, "clean", "documents.jsonl"))}
chunks_by_doc = defaultdict(list)
for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl")):
    chunks_by_doc[c["doc_id"]].append(c)

ev_doc = defaultdict(set)
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        ev_doc[node_by_id[e["tail_id"]]["doc_id"]].add(e["head_id"])

with io.open(os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "时间子集_ge2.json"), encoding="utf-8") as f:
    ge2 = json.load(f)

out = []
for docid_s in sorted(ge2, key=int):
    d = int(docid_s)
    doc = docs[d]
    evs = sorted(ev_doc[str(d)])
    out.append("=" * 100)
    out.append("DOC %d | %s | %s | chunks=%d | dates=%s" % (
        d, doc["category"], doc["title"], len(chunks_by_doc[d]), ",".join(sorted(ge2[docid_s]))))
    out.append("  url=%s | publish=%s | company_list=%s" % (doc["url"], doc["publish_time"], doc["company_list"]))
    out.append("-" * 40 + " EVENTS (%d)" % len(evs))
    ev_chunks = defaultdict(set)
    for ev in evs:
        nd = node_by_id[ev]
        out.append("  %s | %-6s | %-10s | %s" % (ev, nd["event_type"], nd["event_time"], nd["event_name"]))
        for e in edges:
            if e["relation"] == "EVIDENCED_BY":
                continue
            if ev in (e["head_id"], e["tail_id"]) and e["source_chunk_id"]:
                ev_chunks[ev].add(e["source_chunk_id"])
                out.append("      edge %s(%s) -%s-> %s(%s) chunk=%s role=%s conf=%s" % (
                    e["head_id"], node_by_id[e["head_id"]]["name"] if e["head_id"] in node_by_id else "?",
                    e["relation"], e["tail_id"],
                    node_by_id[e["tail_id"]]["name"] if e["tail_id"] in node_by_id else "?",
                    e["source_chunk_id"], e["role"], e["confidence"]))
    out.append("-" * 40 + " CHUNKS (%d)" % len(chunks_by_doc[d]))
    for c in sorted(chunks_by_doc[d], key=lambda x: x["chunk_index"]):
        mark = ""
        for ev, cs in ev_chunks.items():
            if str(c["chunk_id"]) in cs:
                mark += " [EV %s]" % ev
        first = c["content"].replace("\n", " ")[:110]
        out.append("  %d idx=%d tok=%d%s | %s" % (c["chunk_id"], c["chunk_index"], c["token_count"], mark, first))

with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(out) + "\n")
print("written:", OUT)
print("lines:", len(out))
