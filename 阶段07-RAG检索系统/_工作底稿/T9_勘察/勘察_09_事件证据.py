# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 09：给定 event_id 或公司代码，打印事件、边、证据块全文。

用法：
  python 勘察_09_事件证据.py event EVT-0007 EVT-0236
  python 勘察_09_事件证据.py company 000001
  python 勘察_09_事件证据.py pair 000001 600887      # 两公司的共同参与事件
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
DOCS = {d["doc_id"]: d for d in iter_jsonl(os.path.join(DATA, "clean", "documents.jsonl"))}
CHUNKS = {c["chunk_id"]: c for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl"))}


def show_chunk(cid, head=None):
    c = CHUNKS.get(int(cid))
    if c is None:
        print("    [chunk %s NOT FOUND]" % cid)
        return
    body = c["content"] if head is None else c["content"][:head]
    print("    --- chunk %d (doc %d idx %d) doc_title=%s" % (
        c["chunk_id"], c["doc_id"], c["chunk_index"], DOCS[c["doc_id"]]["title"][:50]))
    print(body.replace("\n", " | "))


def dump_event(ev):
    nd = node_by_id.get(ev)
    print("=" * 100)
    print("EVENT %s | %s | %s | %s" % (
        ev, nd["event_type"], nd["event_time"], nd["event_name"]))
    print("  description: %s" % (nd["description"] or "")[:300])
    es = [e for e in edges if ev in (e["head_id"], e["tail_id"])]
    for e in es:
        h, t = node_by_id.get(e["head_id"]), node_by_id.get(e["tail_id"])
        print("  %s(%s) -%s-> %s(%s) role=%s doc=%s chunk=%s conf=%s" % (
            e["head_id"], h["label"], e["relation"], e["tail_id"], t["label"],
            e["role"], e["source_doc_id"], e["source_chunk_id"], e["confidence"]))
    for e in es:
        if e["source_chunk_id"]:
            show_chunk(e["source_chunk_id"])
    if nd["label"] == "Event":
        for e in es:
            if e["relation"] == "EVIDENCED_BY":
                d = node_by_id[e["tail_id"]]
                chunks = sorted(int(c["chunk_id"]) for c in CHUNKS.values() if str(c["doc_id"]) == d["doc_id"])
                print("  [EVIDENCED_BY doc %s] chunks=%s" % (d["doc_id"], chunks))
                print("    title: %s" % d["title"])


def main(argv):
    mode = argv[0]
    if mode == "event":
        for ev in argv[1:]:
            dump_event(ev)
    elif mode == "company":
        code = argv[1]
        nd = node_by_id.get(code)
        print("COMPANY", code, nd["name"] if nd else "?")
        evs = sorted({e["tail_id"] for e in edges if e["head_id"] == code and e["relation"] == "PARTICIPATES_IN"})
        for ev in evs:
            dump_event(ev)
    elif mode == "pair":
        a, b = argv[1], argv[2]
        ea = {e["tail_id"] for e in edges if e["head_id"] == a and e["relation"] == "PARTICIPATES_IN"}
        eb = {e["tail_id"] for e in edges if e["head_id"] == b and e["relation"] == "PARTICIPATES_IN"}
        for ev in sorted(ea & eb):
            dump_event(ev)
    else:
        print("unknown mode")


main(sys.argv[1:])
