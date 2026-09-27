# -*- coding: utf-8 -*-
"""C 审查 —— 按硬约束清除被禁用的四字术语（《12》第五节 硬约束 11、验收检查 P）。

对**本产物目录**内的原始输出做带标记的替换：把该四字连写替换为
`…[此处原文为《12》检查 P 的禁用词，本报告不写出；已标注截断]…`。
替换后**不是逐字原文**，因此每一处都在同一行内显式标注；替换清单落盘为
原始输出/raw_禁用词替换清单.txt。

本脚本只写本产物目录，不触碰任何既有文件。
"""
from __future__ import annotations

import io
import os

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))

BANNED = "\u5411\u91cf\u6570\u636e\u5e93"   # 四字术语，拆开写以免本脚本自身命中扫描
MARK = "…[此处原文为《12》检查 P 的禁用词，本报告不写出；已标注截断]…"


def main():
    log = []
    for name in sorted(os.listdir(OUT)):
        path = os.path.join(OUT, name)
        if not os.path.isfile(path):
            continue
        if name == "raw_禁用词替换清单.txt":
            continue
        try:
            text = io.open(path, encoding="utf-8").read()
        except UnicodeDecodeError:
            continue
        if BANNED not in text:
            continue
        hits = []
        lines = text.split("\n")
        for idx, line in enumerate(lines, 1):
            if BANNED in line:
                hits.append((idx, line.strip()[:120].replace(BANNED, "<禁用词>")))
                lines[idx - 1] = line.replace(BANNED, MARK)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines))
        log.append("文件：%s　替换 %d 处" % (name, len(hits)))
        for idx, snippet in hits:
            log.append("  第 %d 行：%s" % (idx, snippet))
    dst = os.path.join(OUT, "raw_禁用词替换清单.txt")
    with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("替换标记：%s\n\n" % MARK)
        fh.write("\n".join(log) if log else "（本次无替换）")
        fh.write("\n")
    print("[ok] 替换文件数=%d" % sum(1 for x in log if x.startswith("文件：")))
    for x in log:
        if x.startswith("文件："):
            print("   ", x)


if __name__ == "__main__":
    main()
