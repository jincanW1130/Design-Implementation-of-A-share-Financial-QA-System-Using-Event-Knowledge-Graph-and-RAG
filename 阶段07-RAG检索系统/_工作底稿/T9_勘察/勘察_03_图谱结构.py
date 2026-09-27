# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 03：关系 x 标签组合、事件类型、公司/人物/机构可用素材。"""

import csv
import io
import os
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


nodes = read_csv(os.path.join(GRAPH, "nodes.csv"))
edges = read_csv(os.path.join(GRAPH, "edges.csv"))
node_by_id = {n["node_id"]: n for n in nodes}

pair = Counter()
for e in edges:
    h = node_by_id.get(e["head_id"])
    t = node_by_id.get(e["tail_id"])
    pair[(e["relation"], h["label"] if h else "?", t["label"] if t else "?")] += 1
print("=== relation x (head_label -> tail_label)")
for k, v in sorted(pair.items()):
    print("  %-16s %-12s -> %-12s %5d" % (k[0], k[1], k[2], v))

print()
print("=== semantic edges sample 20")
n = 0
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        continue
    h = node_by_id.get(e["head_id"])
    t = node_by_id.get(e["tail_id"])
    print("  %s(%s) -%s-> %s(%s) doc=%s chunk=%s role=%s conf=%s" % (
        e["head_id"], h["name"] if h else "?", e["relation"],
        e["tail_id"], t["name"] if t else "?", e["source_doc_id"], e["source_chunk_id"],
        e["role"], e["confidence"]))
    n += 1
    if n >= 20:
        break

print()
print("=== Event type distribution")
et_all = Counter()
et_time = Counter()
for nd in nodes:
    if nd["label"] != "Event":
        continue
    et_all[nd["event_type"]] += 1
    if (nd["event_time"] or "").strip():
        et_time[nd["event_type"]] += 1
for k in sorted(et_all):
    print("  %-10s all=%4d  with_time=%4d" % (k, et_all[k], et_time[k]))

print()
print("=== Event with time, sample 12")
m = 0
for nd in nodes:
    if nd["label"] == "Event" and (nd["event_time"] or "").strip():
        print("  %s | %s | %s | %s | %s" % (nd["node_id"], nd["event_type"], nd["event_time"],
                                            (nd["event_name"] or "")[:40],
                                            (nd["description"] or "")[:60].replace("\n", " ")))
        m += 1
        if m >= 12:
            break

print()
print("=== Company nodes")
comps = [n for n in nodes if n["label"] == "Company"]
print("companies:", len(comps), "with stock_code:", sum(1 for n in comps if (n["stock_code"] or "").strip()))
for nd in comps[:5]:
    print("  ", nd["node_id"], nd["name"], nd["stock_code"], nd["short_name"])

print()
print("=== HAS_EXECUTIVE count per company (top 15)")
he = defaultdict(int)
for e in edges:
    if e["relation"] == "HAS_EXECUTIVE":
        he[e["head_id"]] += 1
for k, v in sorted(he.items(), key=lambda kv: (-kv[1], kv[0]))[:15]:
    print("  ", k, node_by_id[k]["name"], v)

print()
print("=== semantic edges per source_doc_id (top 20)")
ds = defaultdict(int)
for e in edges:
    if e["relation"] != "EVIDENCED_BY":
        ds[e["source_doc_id"]] += 1
for k, v in sorted(ds.items(), key=lambda kv: (-kv[1], kv[0]))[:20]:
    print("  doc", k, "semantic_edges=", v)
