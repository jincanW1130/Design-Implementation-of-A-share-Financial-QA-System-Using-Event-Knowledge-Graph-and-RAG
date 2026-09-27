# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 11：66 篇内事件的全部语义边（供 2 跳题选题）。"""

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
node_by_id = {n["node_id"]: n for n in nodes}

ev_doc = {}
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        ev_doc[e["head_id"]] = node_by_id[e["tail_id"]]["doc_id"]

with io.open(os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "T9_勘察", "时间子集_ge2.json"), encoding="utf-8") as f:
    GE2 = set(json.load(f).keys())

per_ev = defaultdict(list)
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        continue
    per_ev[e["head_id"]].append((e, "out"))
    per_ev[e["tail_id"]].append((e, "in"))

for ev in sorted(per_ev, key=lambda x: (int(ev_doc.get(x, "9999").lstrip("0") or 0), x)):
    doc = ev_doc.get(ev)
    if doc is None or doc not in GE2:
        continue
    lines = []
    for e, side in per_ev[ev]:
        if e["relation"] == "PARTICIPATES_IN" and side == "in":
            lines.append("      in  <-%s- %s(%s)" % (e["relation"], e["head_id"], node_by_id[e["head_id"]]["name"]))
        elif e["relation"] == "PARTICIPATES_IN" and side == "out":
            lines.append("      out -%s-> %s(%s)" % (e["relation"], e["tail_id"], node_by_id[e["tail_id"]]["name"]))
        elif e["relation"] == "ISSUED_BY":
            lines.append("      -ISSUED_BY-> %s(%s)" % (e["tail_id"], node_by_id[e["tail_id"]]["name"]))
        elif e["relation"] == "RELATED_TO":
            lines.append("      -RELATED_TO-> %s(%s)" % (e["tail_id"], node_by_id[e["tail_id"]]["name"]))
        else:
            lines.append("      -%s- %s/%s" % (e["relation"], e["head_id"], e["tail_id"]))
    nd = node_by_id[ev]
    print("doc %4s | %s | %-6s | %-10s | %s" % (doc, ev, nd["event_type"], nd["event_time"], nd["event_name"][:46]))
    for ln in lines:
        print(ln)
