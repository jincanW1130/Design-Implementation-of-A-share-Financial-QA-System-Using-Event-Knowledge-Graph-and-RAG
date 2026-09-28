# -*- coding: utf-8 -*-
"""对抗实验：graph_query 的 EVIDENCED_BY 边界与 12 个无 stock_code 的 HCONF 节点可达性；
vector_search 是否走 deserialize_index、查询侧是否加指令前缀。"""
import csv
import io
import os
import re
import sys

MIR = r"C:\Users\15129\AppData\Local\Temp\re7_B\mirror"
CODE = os.path.join(MIR, "代码", "检索")
sys.path.insert(0, CODE)
import config  # noqa: E402
import graph_query as G  # noqa: E402

g = G.default_graph()

# ---- 1. EVIDENCED_BY 的客观事实：条数与是否带 source_chunk_id
with io.open(config.EDGES_CSV, encoding="utf-8", newline="") as fh:
    edges = list(csv.DictReader(fh))
ev = [e for e in edges if e["relation"] == "EVIDENCED_BY"]
sem = [e for e in edges if e["relation"] != "EVIDENCED_BY"]
print("EVIDENCED_BY 边数 =", len(ev))
print("  其中带非空 source_chunk_id 的 =", sum(1 for e in ev if (e.get("source_chunk_id") or "").strip()))
print("语义边（非 EVIDENCED_BY）数 =", len(sem), "；带 source_chunk_id =",
      sum(1 for e in sem if (e.get("source_chunk_id") or "").strip()))

# ---- 2. 全量事件：G5 的 chunk_ids 是否与"只经语义边"独立重算一致；EVIDENCED_BY 是否泄漏
with io.open(config.NODES_CSV, encoding="utf-8", newline="") as fh:
    nodes = list(csv.DictReader(fh))
events = [n["node_id"] for n in nodes if n["label"] == "Event"]
# 由边表独立重算：event_id -> set(source_chunk_id)（只取语义边）
from collections import defaultdict  # noqa: E402
by_event = defaultdict(set)
leak = defaultdict(set)
for e in edges:
    sc = (e.get("source_chunk_id") or "").strip()
    if e["relation"] == "EVIDENCED_BY":
        for end in (e["head_id"], e["tail_id"]):
            if end in set(events):
                if sc:
                    leak[end].add(sc)
        continue
    if not sc:
        continue
    for end in (e["head_id"], e["tail_id"]):
        if end in set(events):
            by_event[end].add(sc)

bad, leaked = [], 0
for eid in events:
    got = set(g.g5_event_evidence(eid)["chunk_ids"])
    want = by_event.get(eid, set())
    if got != want:
        bad.append(eid)
    if got & leak.get(eid, set()):
        leaked += 1
print("Event 总数 =", len(events))
print("G5 chunk_ids 与「只经语义边」独立重算不一致的 Event =", len(bad), bad[:5])
print("G5 结果里出现 EVIDENCED_BY 证据块的 Event =", leaked)
# 对照：event_chunk_ids 是否与 G5 一致
print("event_chunk_ids(e) == g5.chunk_ids 不符的事件 =",
      sum(1 for eid in events[:300] if g.event_chunk_ids(eid) != g.g5_event_evidence(eid)["chunk_ids"]))

# ---- 3. 12 个无 stock_code 的公司节点是否可达（按名称解析 + G4）
nocomp = [n for n in nodes if n["label"] == "Company" and not (n.get("stock_code") or "").strip()]
print()
print("无 stock_code 的 Company 节点 =", len(nocomp))
reach_ok, reach_bad, g4_ok = 0, [], 0
for n in nocomp:
    r = g.resolve_node(n["node_id"])
    by_name = g.resolve_company(n["node_id"])
    by_short = g.resolve_node((n.get("name") or "").strip()) if (n.get("name") or "").strip() else None
    ok = (r.get("code") == "OK" and by_short is not None and by_short.get("node_id") == n["node_id"])
    if ok:
        reach_ok += 1
    else:
        reach_bad.append((n["node_id"], n.get("name"), r.get("code"),
                          None if by_short is None else by_short.get("code")))
    g4 = g.g4_company_events(n["node_id"])
    if g4.get("code") in ("OK", "EMPTY"):
        g4_ok += 1
print("按 node_id 解析成功且按 name 解析回同一节点 =", reach_ok, "/", len(nocomp))
print("  失败项 =", reach_bad)
print("G4 对它们的返回码 ∈ {OK, EMPTY}（不抛错）=", g4_ok, "/", len(nocomp))
print("样例：")
for n in nocomp[:12]:
    r = g.resolve_node((n.get("name") or "").strip())
    print("   %-12s name=%-14s -> %s / %s" % (n["node_id"], (n.get("name") or "").strip()[:14],
                                              r.get("code"), r.get("matched_by")))

# ---- 4. vector_search：是否 read_index；查询侧是否加前缀
print()
vs = io.open(os.path.join(CODE, "vector_search.py"), encoding="utf-8").read()
allpy = {}
for n in sorted(os.listdir(CODE)):
    if n.endswith(".py"):
        allpy[n] = io.open(os.path.join(CODE, n), encoding="utf-8").read()
hits = [n for n, t in allpy.items() if re.search(r"faiss\s*\.\s*(read_index|write_index)\s*\(", t)]
print("代码里调用 faiss.read_index/write_index 的文件 =", hits or "（无）")
print("config.read_faiss_index 含 deserialize_index =", "deserialize_index" in allpy["config.py"])
print("vector_search 含 deserialize_index =", "deserialize_index" in vs)
print("vector_search 含 faiss. =", sorted(set(re.findall(r"faiss\.\w+", vs))))
m = re.search(r"def encode_query.*?\n(.*?)\n\n", vs, re.S)
print("encode_query 片段:")
for line in (m.group(0).split("\n")[:14] if m else ["(未找到)"]):
    print("   ", line.rstrip())
print("config.EMBEDDING.query_instruction =", repr(config.EMBEDDING.get("query_instruction")))
print("SELFTEST_VECTOR_IDS =", getattr(__import__("vector_search"), "SELFTEST_VECTOR_IDS", None))
