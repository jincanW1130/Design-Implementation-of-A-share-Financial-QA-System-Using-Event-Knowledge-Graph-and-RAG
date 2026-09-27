# -*- coding: utf-8 -*-
r"""T9 只读自检：四个交付物的禁用词、作废术语、Markdown 表格列数一致性。

注：本脚本要检查的禁用词一律用转义写法构造，避免脚本自身命中扫描
（沿用 `阶段06-事件抽取与知识图谱\_审查工作底稿\C_第七阶段输入\脚本\C_scrub_banned_term.py` 的做法）。
"""

import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FILES = [
    r"代码\检索\build_questions.py",
    r"阶段07-RAG检索系统\预实验问题集\questions.jsonl",
    r"阶段07-RAG检索系统\预实验问题集\题目模板.md",
    r"阶段07-RAG检索系统\预实验问题集\说明.md",
]
BAN = [
    "\u5411\u91cf\u6570\u636e\u5e93",
    "Lang" + "Chain",
    "Llama" + "Index",
    "Elastic" + "search",
    "Kaf" + "ka",
    "Kuber" + "netes",
    "\u91cf\u5316\u4ea4\u6613",
    "\u80a1\u7968\u9884\u6d4b",
    "\u5b9e\u65f6\u884c\u60c5",
    "\u591a\u6a21\u6001",
    "\u8bed\u97f3",
    "Ag" + "ent",
]
FENCE = "```"

for rel in FILES:
    path = os.path.join(ROOT, rel)
    if not os.path.exists(path):
        print("[缺失] %s" % rel)
        continue
    text = io.open(path, encoding="utf-8").read()
    hits = [w for w in BAN if w in text]
    bare = [i for i, l in enumerate(text.split("\n"), 1)
            if re.search(r"(?<!Complete )Evidence Recall", l)]
    print("%-58s 禁用词=%s 裸EvidenceRecall行=%s 字节=%d" % (
        rel, hits, bare, os.path.getsize(path)))

    if not rel.endswith(".md"):
        continue
    in_code = False
    block = []
    blocks = 0
    bad = 0
    for line in text.split("\n"):
        if line.strip().startswith(FENCE):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.strip().startswith("|"):
            block.append(line)
        elif block:
            cols = {len(r.strip().strip("|").split("|")) for r in block}
            blocks += 1
            if len(cols) > 1:
                bad += 1
                print("    !! 列数不一致：%s | %s" % (sorted(cols), block[0][:70]))
            block = []
    if block:
        cols = {len(r.strip().strip("|").split("|")) for r in block}
        blocks += 1
        if len(cols) > 1:
            bad += 1
            print("    !! 列数不一致：%s | %s" % (sorted(cols), block[0][:70]))
    print("    表格块=%d 列数不一致=%d" % (blocks, bad))
