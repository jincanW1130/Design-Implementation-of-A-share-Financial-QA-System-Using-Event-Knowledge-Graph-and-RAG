# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 12：定点查询（高管边、行业边、指定事件边）的 chunk_id。"""

import csv
import io
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


nodes = read_csv(os.path.join(GRAPH, "nodes.csv"))
edges = read_csv(os.path.join(GRAPH, "edges.csv"))
node_by_id = {n["node_id"]: n for n in nodes}


def show(title, pred):
    print("=== " + title)
    for e in edges:
        if pred(e):
            h, t = node_by_id[e["head_id"]], node_by_id[e["tail_id"]]
            print("  %s(%s) -%s-> %s(%s) role=%s conf=%s doc=%s chunk=%s" % (
                e["head_id"], h["name"], e["relation"], e["tail_id"], t["name"],
                e["role"], e["confidence"], e["source_doc_id"], e["source_chunk_id"]))


show("601138 工业富联 HAS_EXECUTIVE", lambda e: e["relation"] == "HAS_EXECUTIVE" and e["head_id"] == "601138")
show("000001 平安银行 HAS_EXECUTIVE", lambda e: e["relation"] == "HAS_EXECUTIVE" and e["head_id"] == "000001")
show("601138 工业富联 PARTICIPATES_IN(前12)", lambda e: e["relation"] == "PARTICIPATES_IN" and e["head_id"] == "601138")
show("所有 BELONGS_TO", lambda e: e["relation"] == "BELONGS_TO")
show("EVT-0001 相关边", lambda e: "EVT-0001" in (e["head_id"], e["tail_id"]))
show("EVT-0067 相关边", lambda e: "EVT-0067" in (e["head_id"], e["tail_id"]))
show("EVT-0135 相关边", lambda e: "EVT-0135" in (e["head_id"], e["tail_id"]))
show("EVT-0161 相关边", lambda e: "EVT-0161" in (e["head_id"], e["tail_id"]))
show("EVT-0251 相关边", lambda e: "EVT-0251" in (e["head_id"], e["tail_id"]))
show("EVT-0335/0337 相关边", lambda e: e["head_id"] in ("EVT-0335", "EVT-0337") or e["tail_id"] in ("EVT-0335", "EVT-0337"))
show("EVT-0205 相关边", lambda e: "EVT-0205" in (e["head_id"], e["tail_id"]))
show("600522 中天科技 全部语义边", lambda e: e["relation"] != "EVIDENCED_BY" and e["head_id"] == "600522")
show("EVT-0184/0185 相关边", lambda e: e["head_id"] in ("EVT-0184", "EVT-0185") or e["tail_id"] in ("EVT-0184", "EVT-0185"))
show("EVT-0275/0276 相关边", lambda e: e["head_id"] in ("EVT-0275", "EVT-0276") or e["tail_id"] in ("EVT-0275", "EVT-0276"))
