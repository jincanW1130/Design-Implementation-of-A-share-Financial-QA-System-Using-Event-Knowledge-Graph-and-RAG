# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 02：EVIDENCED_BY 反查文档、按 event_time 日期计数、核对 66 篇。

口径（任务书 T9 设计约束 3）：
  nodes.csv 的 Event 行 → edges.csv 的 EVIDENCED_BY 边反查 Document 节点 → doc_id
  → 统计每个文档的“不同 event_time 日期”个数 → 取 >= 2 个日期的文档。
"""

import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


nodes = read_csv(os.path.join(GRAPH, "nodes.csv"))
edges = read_csv(os.path.join(GRAPH, "edges.csv"))
print("nodes:", len(nodes), "edges:", len(edges))

node_by_id = {n["node_id"]: n for n in nodes}
print("label counts:", {k: sum(1 for n in nodes if n["label"] == k) for k in sorted({n["label"] for n in nodes})})
rel_counts = defaultdict(int)
for e in edges:
    rel_counts[e["relation"]] += 1
print("relation counts:", dict(sorted(rel_counts.items())))

# 事件节点
events = [n for n in nodes if n["label"] == "Event"]
events_with_time = [n for n in events if (n["event_time"] or "").strip()]
print("events:", len(events), "with time:", len(events_with_time))

# EVIDENCED_BY 的方向抽样
ev_edges = [e for e in edges if e["relation"] == "EVIDENCED_BY"]
print("EVIDENCED_BY edges:", len(ev_edges))
for e in ev_edges[:3]:
    h, t = node_by_id.get(e["head_id"]), node_by_id.get(e["tail_id"])
    print("  head:", e["head_id"], h["label"] if h else "?", "| tail:", e["tail_id"], t["label"] if t else "?",
          "| doc:", t.get("doc_id") if t else None, "| src_chunk:", e["source_chunk_id"])

# Event -> Document via EVIDENCED_BY
event_doc = defaultdict(set)
for e in ev_edges:
    h, t = node_by_id.get(e["head_id"]), node_by_id.get(e["tail_id"])
    if h is None or t is None:
        continue
    if h["label"] == "Event" and t["label"] == "Document":
        event_doc[e["head_id"]].add(t["doc_id"])
    elif t["label"] == "Event" and h["label"] == "Document":
        event_doc[e["tail_id"]].add(h["doc_id"])
print("events linked to a Document via EVIDENCED_BY:", len(event_doc))

doc_dates = defaultdict(set)
doc_event_ids = defaultdict(set)
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
        doc_event_ids[d].add(ev["node_id"])
print("events with time but no EVIDENCED_BY doc:", unlinked)

ge2 = sorted([d for d, s in doc_dates.items() if len(s) >= 2])
print("documents with >=2 distinct event_time dates:", len(ge2))
print(ge2)

dist = defaultdict(int)
for d, s in doc_dates.items():
    dist[len(s)] += 1
print("date-count distribution (docs having >=1 dated event):", dict(sorted(dist.items())))

with io.open(os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "时间子集_ge2.json"), "w",
             encoding="utf-8", newline="\n") as f:
    json.dump({str(d): sorted(doc_dates[d]) for d in ge2}, f, ensure_ascii=False, indent=1, sort_keys=True)
print("written: _工作底稿/T9_勘察/时间子集_ge2.json")
