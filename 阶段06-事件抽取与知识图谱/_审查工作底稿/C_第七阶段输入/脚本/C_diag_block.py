# -*- coding: utf-8 -*-
"""诊断：打印指定代码块，并报告它在各比对源中的命中情况。"""
from __future__ import annotations

import io
import os
import re
import sys

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))


def main():
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 81
    text = io.open(REPORT, encoding="utf-8").read()
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S)
    block = blocks[idx - 1].strip("\n")
    print("块总数", len(blocks))
    print("---- 块#%d（前 700 字符）----" % idx)
    print(block[:700])
    print("---- 检索各源 ----")
    targets = []
    for rel in ("02-项目执行总控文档.md",
                "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md",
                "阶段05-数据准备/13-数据准备（第五阶段）.md",
                "阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md",
                "代码/数据准备/config.py", "代码/数据准备/embed.py", "代码/数据准备/chunk.py"):
        targets.append((rel, os.path.join(ROOT, rel.replace("/", os.sep))))
    raw_dir = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
    for name in sorted(os.listdir(raw_dir)):
        if name.endswith((".txt", ".md")):
            targets.append(("原始输出/" + name, os.path.join(raw_dir, name)))
    parts = [p for p in block.split("\n") if len(p) > 25]
    for rel, path in targets:
        if not os.path.isfile(path):
            continue
        blob = io.open(path, encoding="utf-8").read()
        hit = [i for i, p in enumerate(parts) if p in blob]
        if hit:
            print("  命中 %s：%d/%d 行" % (rel, len(hit), len(parts)))


if __name__ == "__main__":
    main()
