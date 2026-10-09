# -*- coding: utf-8 -*-
"""报告自检：① 禁用术语残留；② 表格列数一致性（单元格内不得出现多余的竖线）；③ 引文字体统计。"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出", "raw_报告自检.txt"))

BANNED = "\u5411\u91cf\u6570\u636e\u5e93"


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    lines = text.split("\n")
    log = []

    # ① 禁用术语
    hits = [i + 1 for i, ln in enumerate(lines) if BANNED in ln]
    log.append("① 禁用术语命中行：%s" % (hits if hits else "无"))

    # ② 表格列数一致性
    table_no = 0
    in_table = False
    expect = None
    bad = []
    for i, ln in enumerate(lines, 1):
        s = ln.strip()
        if s.startswith("|") and s.endswith("|"):
            n = s.count("|")
            if not in_table:
                in_table = True
                table_no += 1
                expect = n
            elif n != expect:
                bad.append((i, table_no, expect, n, s[:90]))
        else:
            in_table = False
            expect = None
    log.append("② 表格块数：%d；列数不一致的行：%d" % (table_no, len(bad)))
    for i, t, e, n, s in bad:
        log.append("    第 %d 行（表 %d）：期望 %d 个竖线，实际 %d —— %s" % (i, t, e, n, s))

    # ③ 代码块统计
    blocks = re.findall(r"(?m)^```[a-zA-Z]*\n.*?^```\s*$", text, flags=re.S)
    labels = len(re.findall(r"\*\*(整理|摘录)（非逐字）\*\*", text))
    log.append("③ 代码块总数：%d；带「整理／摘录（非逐字）」标注的块：%d" % (len(blocks), labels))

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
