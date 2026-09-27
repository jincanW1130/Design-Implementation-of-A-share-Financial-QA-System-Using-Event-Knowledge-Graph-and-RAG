# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 16：抽取核验锚点周围的原文片段（用于交付报告的抽样证据）。"""

import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DATA = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1")
Q = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集", "questions.jsonl")
SCRIPT = os.path.join(ROOT, "代码", "检索", "build_questions.py")

WANT = ["PE-01", "PE-03", "PE-07", "PE-11", "PE-13", "PE-16", "PE-22", "PE-28", "PE-29", "PE-30"]


def iter_jsonl(path):
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


CHUNKS = {int(c["chunk_id"]): c for c in iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl"))}
ROWS = {r["qid"]: r for r in iter_jsonl(Q)}

# 从脚本里取锚点（冻结表是脚本内的常量，这里按文本解析，避免重复维护）
src = io.open(SCRIPT, encoding="utf-8").read()
anchors_by_qid = {}
for m in re.finditer(r'qid="(PE-\d+)"(.*?)\n    \),', src, re.S):
    qid, body = m.group(1), m.group(2)
    anchors = re.findall(r'\((\d+),\s*"([^"]+)"\)', body)
    if anchors:
        anchors_by_qid[qid] = [(int(a), b) for a, b in anchors]


def norm(text):
    return re.sub(r"\s+", "", text)


for qid in WANT:
    row = ROWS[qid]
    print("=" * 96)
    print("%s | %s" % (qid, row["question"]))
    for cid, anchor in anchors_by_qid.get(qid, [])[:3]:
        content = norm(CHUNKS[cid]["content"])
        key = norm(anchor)
        i = content.find(key)
        lo = max(0, i - 45)
        hi = min(len(content), i + len(key) + 45)
        print("  [chunk %d] …%s…" % (cid, content[lo:hi]))
