# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 01：输入结构、字段、规模与关键分布。

只读；不写任何输入文件；输出打印到 stdout（UTF-8）。
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")
DATA = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1")


def head(path, n):
    out = []
    with io.open(path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            out.append(line.rstrip("\n"))
    return out


print("=== nodes.csv 表头与前 3 行")
for line in head(os.path.join(GRAPH, "nodes.csv"), 4):
    print(line[:1000])

print()
print("=== edges.csv 表头与前 3 行")
for line in head(os.path.join(GRAPH, "edges.csv"), 4):
    print(line[:1000])

print()
print("=== documents.jsonl 第 1 行字段")
with io.open(os.path.join(DATA, "clean", "documents.jsonl"), encoding="utf-8") as f:
    doc = json.loads(f.readline())
for k, v in doc.items():
    print("  %-22s = %s" % (k, repr(v)[:170]))

print()
print("=== chunks.jsonl 第 1 行字段")
with io.open(os.path.join(DATA, "chunks", "chunks.jsonl"), encoding="utf-8") as f:
    ch = json.loads(f.readline())
for k, v in ch.items():
    print("  %-22s = %s" % (k, repr(v)[:170]))

print()
print("=== graph_stats.json")
with io.open(os.path.join(GRAPH, "graph_stats.json"), encoding="utf-8") as f:
    gs = json.load(f)
print(json.dumps(gs, ensure_ascii=False, indent=1, sort_keys=True)[:4000])
