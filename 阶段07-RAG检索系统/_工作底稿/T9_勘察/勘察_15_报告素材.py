# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 15：生成交付报告需要的两类证据（时间子集逐题证据、核验锚点原文）。"""

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
DATA = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1")
Q = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集", "questions.jsonl")


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
CHUNKS = {int(c["chunk_id"]): c for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl"))}

ev_docs = defaultdict(set)
for e in edges:
    if e["relation"] == "EVIDENCED_BY":
        ev_docs[e["head_id"]].add(node_by_id[e["tail_id"]]["doc_id"])
dates_by_doc = defaultdict(set)
for ev, docs in ev_docs.items():
    et = (node_by_id[ev]["event_time"] or "").strip()
    if et:
        for d in docs:
            dates_by_doc[d].add(et)

rows = list(iter_jsonl(Q))
print("=" * 100)
print("A. 12 道时间约束题：gold 文档与“该文档的不同 event_time 日期”")
for r in rows:
    if r["time_constraint"] != "有":
        continue
    docs = r["gold_evidence_doc_ids"]
    detail = "；".join("doc %d 日期[%s]" % (d, ",".join(sorted(dates_by_doc[str(d)]))) for d in docs)
    print("%s | %s | %s | gold=%s" % (r["qid"], r["time_window"]["label"],
                                      r["time_window"]["lo"] + "~" + r["time_window"]["hi"],
                                      ",".join(str(c) for c in r["gold_evidence_chunk_ids"])))
    print("     " + detail)

print()
print("=" * 100)
print("B. 逐题核验锚点在原文中的上下文（前 12 题）")
for r in rows[:12]:
    print("-" * 100)
    print("%s | %s" % (r["qid"], r["question"]))
    for cid in r["gold_evidence_chunk_ids"]:
        c = CHUNKS[cid]
        print("  chunk %d（doc %d idx %d）全文去空白后长度 %d" % (
            cid, c["doc_id"], c["chunk_index"], len(c["content"])))
