# -*- coding: utf-8 -*-
"""s2_graph_facts.py —— 从原始产物复算图谱侧读数（只读项目树）。"""
import os, csv, json, collections, datetime
ROOT = r"C:\Users\15129\Desktop\毕业设计"
G = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")
CACHE = os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "_抽取缓存", "v2.1_v1_2", "图谱管线")
nodes = {r["node_id"]: r for r in csv.DictReader(open(os.path.join(G, "nodes.csv"), encoding="utf-8"))}
edges = list(csv.DictReader(open(os.path.join(G, "edges.csv"), encoding="utf-8")))
print("[1] nodes.csv 逐行复算")
print("    行数=%d  列数=%d" % (len(nodes), len(next(iter(nodes.values())))))
lab = collections.Counter(r["label"] for r in nodes.values())
print("    label=%s" % dict(sorted(lab.items())))
ev = [r for r in nodes.values() if r["label"] == "Event"]
print("    Event=%d  其中 event_time 为空=%d" % (len(ev), sum(1 for r in ev if not (r["event_time"] or "").strip())))
comp = [r for r in nodes.values() if r["label"] == "Company"]
hconf = [r for r in comp if r["node_id"].startswith("HCONF")]
print("    Company=%d  无 stock_code=%d  HCONF=%d" % (len(comp), sum(1 for r in comp if not (r.get("stock_code") or "").strip()), len(hconf)))
print("[2] edges.csv 逐行复算")
rel = collections.Counter(e["relation"] for e in edges)
print("    行数=%d  关系分布=%s" % (len(edges), dict(sorted(rel.items(), key=lambda kv: -kv[1]))))
sem = [e for e in edges if e["relation"] != "EVIDENCED_BY"]
print("    语义边=%d  带 source_chunk_id=%d" % (len(sem), sum(1 for e in sem if (e.get("source_chunk_id") or "").strip())))
bt = [e for e in edges if e["relation"] == "BELONGS_TO"]
print("    BELONGS_TO=%d  valid_from 非空=%d  valid_to 非空=%d"
      % (len(bt), sum(1 for e in bt if (e.get("valid_from") or "").strip()), sum(1 for e in bt if (e.get("valid_to") or "").strip())))
print("    SUPPLIES=%d COMPETES_WITH=%d CUSTOMER_OF=%d" % (rel.get("SUPPLIES", 0), rel.get("COMPETES_WITH", 0), rel.get("CUSTOMER_OF", 0)))
print("[3] graph_stats.json")
gs = json.load(open(os.path.join(G, "graph_stats.json"), encoding="utf-8"))
print("    isolated_nodes.count=%s（类型 %s）ids 条数=%d；unresolved.relations_skipped=%s；event_time_null=%s"
      % (gs["isolated_nodes"]["count"], type(gs["isolated_nodes"]["count"]).__name__,
         len(gs["isolated_nodes"]["ids"]), gs["unresolved"]["relations_skipped"],
         gs["event_core_attributes"]["event_time_null_count"]))
print("    graph_check: checks=%s passed=%s failed_must=%s"
      % (gs["graph_check"]["checks"], gs["graph_check"]["passed"], gs["graph_check"]["failed_must"]))
print("[4] 消歧产物（待消歧 1070）")
d = json.load(open(os.path.join(CACHE, "消歧", "disambiguation.json"), encoding="utf-8"))
print("    counts.unresolved=%s by_reason=%s" % (d["counts"]["unresolved"], d["counts"]["unresolved_by_reason"]))
ur = os.path.join(CACHE, "消歧", "unresolved.jsonl")
print("    unresolved.jsonl 行数=%d" % sum(1 for l in open(ur, encoding="utf-8") if l.strip()))
print("[5] 时间可过滤性 66／49／40（自建 doc→event_time 映射复算）")
et = {nid: (r["event_time"] or "").strip() for nid, r in nodes.items() if r["label"] == "Event"}
doc_ev = collections.defaultdict(set)
for e in edges:
    if e["relation"] != "EVIDENCED_BY":
        continue
    h, t = e["head_id"], e["tail_id"]
    a = h if h in et else (t if t in et else None)
    b = t if a == h else (h if a == t else None)
    if a and b and et[a]:
        doc_ev[b].add(et[a][:10])
def span31(v):
    ds = sorted(v)
    return len(ds) >= 2 and (datetime.date.fromisoformat(ds[-1]) - datetime.date.fromisoformat(ds[0])).days >= 31
ge2 = sum(1 for v in doc_ev.values() if len(v) >= 2)
ge2m = sum(1 for v in doc_ev.values() if len({x[:7] for x in v}) >= 2)
sp = sum(1 for v in doc_ev.values() if span31(v))
print("    含>=2 个不同日期=%d  含>=2 个自然月=%d  跨度>=31 天=%d" % (ge2, ge2m, sp))
m = json.load(open(os.path.join(ROOT, r"交付物/03-代码\抽取与图谱\_全量\v2.1_v1_2\时间覆盖_度量.json"), encoding="utf-8"))
gm = m["graph_layer_after_backfill"]["metrics"]
print("    产物字段同口径=%s／%s／%s（另：字面口径 docs_with_ge2_nonnull_events=%s）"
      % (gm["docs_with_ge2_distinct_event_dates"], gm["docs_times_span_more_than_one_month"],
         gm["docs_times_span_ge_31_days"], gm["docs_with_ge2_nonnull_events"]))
