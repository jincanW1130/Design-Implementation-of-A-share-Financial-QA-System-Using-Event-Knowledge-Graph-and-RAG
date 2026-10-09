# -*- coding: utf-8 -*-
"""只读探针：打印正式测试集的规模／子集／压力标记构成，以及各组落盘进度（0 次模型调用）。"""
import json
import os

# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\` 整体移到
# `交付物/06-实验与评测\对照产出_正式\`（**下移一层**），求 ROOT 的上溯次数 3 → 4。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
Q = os.path.join(ROOT, "交付物/06-实验与评测", "测试集", "questions.jsonl")
OUT = os.path.join(ROOT, "交付物/06-实验与评测", "对照产出_正式")

rows = []
with open(Q, encoding="utf-8") as fh:
    for line in fh:
        line = line.strip()
        if line:
            rows.append(json.loads(line))

print("题集：%s" % os.path.relpath(Q, ROOT).replace("\\", "/"))
print("题数：%d" % len(rows))
print("字段：%s" % sorted(rows[0].keys()))
print()

for name, pred in (("关系型", lambda r: r.get("task_type") == "关系型"),
                   ("多跳型", lambda r: int(r.get("gold_hop_depth") or 0) >= 1),
                   ("时序型", lambda r: r.get("time_constraint") == "有")):
    sel = [r["qid"] for r in rows if pred(r)]
    print("%-6s 题数 %3d" % (name, len(sel)))
print()

stress = [r["qid"] for r in rows
          if r.get("is_stress") or r.get("subset") in ("压力", "压力测试", "压力测试子集")]
print("显式压力标记题数：%d（%s）" % (len(stress), "、".join(stress)))
core = [r["qid"] for r in rows if r["qid"] not in set(stress)]
print("核心题数：%d" % len(core))

# 核心集内的三子集题数（12.8 判定用）
cset = set(core)
for name, pred in (("关系型", lambda r: r.get("task_type") == "关系型"),
                   ("多跳型", lambda r: int(r.get("gold_hop_depth") or 0) >= 1),
                   ("时序型", lambda r: r.get("time_constraint") == "有")):
    sel = [r["qid"] for r in rows if r["qid"] in cset and pred(r)]
    print("核心集内 %-6s 题数 %3d" % (name, len(sel)))
print()

print("各组落盘进度：")
base = os.path.join(OUT, "逐题")
tot = 0
for g in ("A", "B", "C", "D", "E", "B1"):
    d = os.path.join(base, g)
    n = 0
    if os.path.isdir(d):
        n = sum(1 for q in os.listdir(d)
                if os.path.isfile(os.path.join(d, q, "answer_trace.jsonl")))
    tot += n
    print("  %-3s %3d / 120" % (g, n))
print("  合计 %d / 720" % tot)
