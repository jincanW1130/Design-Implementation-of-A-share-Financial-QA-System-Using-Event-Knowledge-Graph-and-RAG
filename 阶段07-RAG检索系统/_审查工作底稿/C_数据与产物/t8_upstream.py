# -*- coding: utf-8 -*-
"""C 线：第 7 阶段引用的上游读数，回到上游产物独立重算"""
import csv, io, json, os
from collections import Counter, defaultdict

ROOT = r"C:\Users\15129\Desktop\毕业设计"
G = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")

def read_csv(p):
    with io.open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

nodes = read_csv(os.path.join(G, "nodes.csv"))
edges = read_csv(os.path.join(G, "edges.csv"))
gs = json.load(io.open(os.path.join(G, "graph_stats.json"), encoding="utf-8"))
conf = json.load(io.open(os.path.join(G, "人工确认清单.json"), encoding="utf-8"))

print("== 基本规模 ==")
print("nodes.csv 行数 =", len(nodes), "（声称 2802）")
print("edges.csv 行数 =", len(edges), "（声称 2736）")
rel = Counter(e["relation"] for e in edges)
print("关系分布 =", dict(sorted(rel.items())))
print("EVIDENCED_BY =", rel.get("EVIDENCED_BY"), "（声称 1111）")
sem = [e for e in edges if e["relation"] != "EVIDENCED_BY"]
print("语义边（非 EVIDENCED_BY）= %d（声称 1625）；带 source_chunk_id = %d（声称 1625）" % (
    len(sem), sum(1 for e in sem if (e["source_chunk_id"] or "").strip())))
print("BELONGS_TO=%d" % rel.get("BELONGS_TO", 0))
bt = [e for e in edges if e["relation"] == "BELONGS_TO"]
print("BELONGS_TO 中 valid_from/valid_to 均为空 = %d/%d（声称 14/14 全空）" % (
    sum(1 for e in bt if not (e["valid_from"] or "").strip() and not (e["valid_to"] or "").strip()),
    len(bt)))

lab = Counter(n["label"] for n in nodes)
print("标签分布 =", dict(sorted(lab.items())))
events = [n for n in nodes if n["label"] == "Event"]
ev_nt = [n for n in events if not (n["event_time"] or "").strip()]
print("Event 节点 = %d（声称 1100）；event_time 空 = %d（声称 544，%.1f%%）" % (
    len(events), len(ev_nt), 100.0 * len(ev_nt) / len(events)))

print()
print("== 孤立节点（自己从 nodes+edges 重算）==")
deg = defaultdict(int)
for e in edges:
    deg[e["head_id"]] += 1
    deg[e["tail_id"]] += 1
iso = [n["node_id"] for n in nodes if deg.get(n["node_id"], 0) == 0]
print("度数为 0 的节点数 = %d（声称 435）" % len(iso))

print()
print("== graph_stats.json 读数 ==")
def dig(o, path):
    cur = o
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return "<缺失: %s>" % k
    return cur
for k in ("isolated_nodes", "unresolved", "graph_check", "relations_skipped",
          "event_core_attributes", "event_time_basis"):
    v = gs.get(k, "<无此键>")
    print("graph_stats.%s = %s" % (k, json.dumps(v, ensure_ascii=False)[:400]))
print("graph_stats 顶层键 =", list(gs.keys()))

print()
print("== 人工确认清单 / HCONF ==")
print("类型 =", type(conf).__name__, "顶层键 =", list(conf.keys()) if isinstance(conf, dict) else len(conf))
txt = json.dumps(conf, ensure_ascii=False)
print("清单中出现 HCONF 次数 =", txt.count("HCONF"))
print("节点表里 HCONF 节点 =", sum(1 for n in nodes if "HCONF" in n["node_id"]))
print("HCONF 且 Company 标签 =", sum(1 for n in nodes if "HCONF" in n["node_id"] and n["label"] == "Company"))
hconf_no_code = [n["node_id"] for n in nodes if "HCONF" in n["node_id"]
                 and not (n["stock_code"] or "").strip()]
print("HCONF 无 stock_code =", len(hconf_no_code), hconf_no_code[:20])
comp = [n for n in nodes if n["label"] == "Company"]
print("Company 节点 = %d（声称 116）；其中无 stock_code = %d（声称 12）" % (
    len(comp), sum(1 for n in comp if not (n["stock_code"] or "").strip())))
print("人工确认清单条目数 =", len(conf) if not isinstance(conf, dict) else
      {k: (len(v) if isinstance(v, list) else v) for k, v in conf.items()})
