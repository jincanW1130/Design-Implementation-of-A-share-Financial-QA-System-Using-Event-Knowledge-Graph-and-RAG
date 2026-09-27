# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 13：核对脚本内 66 篇口径与勘察口径的差异。"""

import csv
import io
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


nodes = read_csv(os.path.join(GRAPH, "nodes.csv"))
edges = read_csv(os.path.join(GRAPH, "edges.csv"))
node_by_id = {n["node_id"]: n for n in nodes}

event_doc = {}
for e in edges:
    if e["relation"] != "EVIDENCED_BY":
        continue
    h, t = node_by_id.get(e["head_id"]), node_by_id.get(e["tail_id"])
    if h is not None and t is not None and h["label"] == "Event" and t["label"] == "Document":
        event_doc.setdefault(e["head_id"], set()).add(t["doc_id"])

dates = defaultdict(set)
for ev, docs in event_doc.items():
    et = (node_by_id[ev]["event_time"] or "").strip()
    if not et:
        continue
    for d in docs:
        dates[d].add(et)

ge2 = sorted(d for d, s in dates.items() if len(s) >= 2)
print("本口径 >=2 日期文档数：", len(ge2))
print(ge2)

with io.open(os.path.join(HERE, "时间子集_ge2.json"), encoding="utf-8") as f:
    old = set(json.load(f).keys())
print("与勘察_02 的差集（脚本有、勘察无）：", sorted(set(ge2) - old))
print("与勘察_02 的差集（勘察有、脚本无）：", sorted(old - set(ge2)))

# 多文档归属的事件
for ev, docs in sorted(event_doc.items()):
    if len(docs) > 1:
        print("  事件 %s 归属多篇文档：%s | %s" % (ev, sorted(docs), node_by_id[ev]["event_name"][:40]))
