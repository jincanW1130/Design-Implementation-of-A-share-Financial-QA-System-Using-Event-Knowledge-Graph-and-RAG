# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 06：从 66 篇中筛“多事件文档”，打印事件/日期/证据块紧凑清单。"""

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
docs = {d["doc_id"]: d for d in iter_jsonl(os.path.join(DATA, "clean", "documents.jsonl"))}
chunks_by_doc = defaultdict(list)
for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl")):
    chunks_by_doc[c["doc_id"]].append(c)

ev_doc = defaultdict(set)
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        ev_doc[node_by_id[e["tail_id"]]["doc_id"]].add(e["head_id"])

ev_edges = defaultdict(list)
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        continue
    for side in ("head_id", "tail_id"):
        ev = e[side]
        if ev.startswith("EVT-"):
            ev_edges[ev].append(e)

with io.open(os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "时间子集_ge2.json"), encoding="utf-8") as f:
    ge2 = json.load(f)

rows = []
for docid_s in ge2:
    d = int(docid_s)
    evs = sorted(ev_doc[str(d)])
    dated = [ev for ev in evs if (node_by_id[ev]["event_time"] or "").strip()]
    rows.append((len(dated), len(set(node_by_id[ev]["event_time"] for ev in dated)), d))
rows.sort(reverse=True)

print("=== 66 篇中按“有时间的 Event 数”排序（doc_id | dated_events | distinct_dates | chunks）")
for nd_, ndd, d in rows[:30]:
    print("  doc %5d | dated=%2d | dates=%d | chunks=%2d | %s" % (
        d, nd_, ndd, len(chunks_by_doc[d]), docs[d]["title"][:56]))

print()
print("=== 多事件文档的事件明细（dated>=2 的前 14 篇）")
for nd_, ndd, d in rows[:14]:
    print("-" * 90)
    print("DOC %d | %s | publish %s" % (d, docs[d]["title"][:70], docs[d]["publish_time"]))
    for ev in sorted(ev_doc[str(d)]):
        n = node_by_id[ev]
        chs = sorted({e["source_chunk_id"] for e in ev_edges.get(ev, []) if e["source_chunk_id"]})
        print("   %s | %-6s | %-10s | %s | chunks=%s" % (
            ev, n["event_type"], n["event_time"], n["event_name"][:52], ",".join(chs) or "-"))
