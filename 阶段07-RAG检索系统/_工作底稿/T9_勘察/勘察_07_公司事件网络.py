# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 07：公司-事件-机构网络结构，找 1 跳/2 跳候选素材。"""

import csv
import io
import json
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

company_events = defaultdict(set)
company_event_edges = defaultdict(list)
event_companies = defaultdict(set)
inst_events = defaultdict(set)
person_company = defaultdict(set)
company_persons = defaultdict(set)
industry_companies = defaultdict(set)
policy_events = defaultdict(set)

for e in edges:
    rel = e["relation"]
    if rel == "PARTICIPATES_IN":
        h, t = node_by_id[e["head_id"]], node_by_id[e["tail_id"]]
        if h["label"] == "Company" and t["label"] == "Event":
            company_events[e["head_id"]].add(e["tail_id"])
            company_event_edges[e["head_id"]].append(e)
            event_companies[e["tail_id"]].add(e["head_id"])
    elif rel == "HAS_EXECUTIVE":
        company_persons[e["head_id"]].add(e["tail_id"])
        person_company[e["tail_id"]].add(e["head_id"])
    elif rel == "ISSUED_BY":
        inst_events[e["tail_id"]].add(e["head_id"])
    elif rel == "BELONGS_TO":
        industry_companies[e["tail_id"]].add(e["head_id"])
    elif rel == "RELATED_TO":
        policy_events[e["tail_id"]].add(e["head_id"])

print("=== 公司：参与事件数 / 有 chunk 证据的事件数 / 高管数（按事件数前 25）")
rows = []
for cid, evs in company_events.items():
    chs = {e["source_chunk_id"] for e in company_event_edges[cid] if e["source_chunk_id"]}
    rows.append((len(evs), len(chs), len(company_persons[cid]), cid))
rows.sort(reverse=True)
for n_ev, n_ch, n_pe, cid in rows[:25]:
    print("  %s %-10s events=%2d evidence_chunks=%2d persons=%d" % (
        cid, node_by_id[cid]["name"], n_ev, n_ch, n_pe))

print()
print("=== 多公司共同参与的事件（>=2 家公司，前 20）")
multi = [(len(v), k) for k, v in event_companies.items() if len(v) >= 2]
multi.sort(reverse=True)
for n, ev in multi[:20]:
    names = "、".join(node_by_id[c]["name"] for c in sorted(event_companies[ev]))
    print("  %s | %-6s | %-10s | %s | %s" % (
        ev, node_by_id[ev]["event_type"], node_by_id[ev]["event_time"],
        node_by_id[ev]["event_name"][:44], names))
print("  total multi-company events:", len(multi))

print()
print("=== 行业 → 公司（BELONGS_TO，>=2 家的行业）")
for ind, comps in sorted(industry_companies.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    if len(comps) >= 1:
        print("  %s %s <- %s" % (ind, node_by_id[ind]["name"],
                                 "、".join(node_by_id[c]["name"] for c in sorted(comps))))

print()
print("=== 机构 → 事件（ISSUED_BY，前 15）")
for inst, evs in sorted(inst_events.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:15]:
    print("  %s %s -> %d events" % (inst, node_by_id[inst]["name"], len(evs)))

print()
print("=== 事件 → 政策（RELATED_TO，前 10）")
for pol, evs in sorted(policy_events.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:10]:
    print("  %s %s <- %d events" % (pol, node_by_id[pol]["name"][:40], len(evs)))

print()
print("=== 公司-公司薄类关系全量")
for e in edges:
    if e["relation"] in ("CUSTOMER_OF", "COMPETES_WITH", "SUPPLIES"):
        print("  %s(%s) -%s-> %s(%s) doc=%s chunk=%s" % (
            e["head_id"], node_by_id[e["head_id"]]["name"], e["relation"],
            e["tail_id"], node_by_id[e["tail_id"]]["name"], e["source_doc_id"], e["source_chunk_id"]))

print()
print("=== 语义边按 relation 的 chunk 覆盖")
for rel in sorted({e["relation"] for e in edges}):
    es = [e for e in edges if e["relation"] == rel]
    with_chunk = sum(1 for e in es if e["source_chunk_id"])
    print("  %-16s edges=%4d with_chunk=%4d" % (rel, len(es), with_chunk))
