# -*- coding: utf-8 -*-
"""逐字符定位报告代码块与源文件行的差异（打印差异片段的 repr）。"""
from __future__ import annotations

import difflib
import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S)
    targets = [(3, "02-项目执行总控文档.md", "829"), (23, "交付物/07-设计与需求/总体设计/10-系统总体设计（第四阶段）.md", "496-498")]
    for idx, rel, linespec in targets:
        src = io.open(os.path.join(ROOT, rel.replace("/", os.sep)), encoding="utf-8").read().split("\n")
        if "-" in linespec:
            a, b = linespec.split("-")
            src_text = "\n".join(src[int(a) - 1:int(b)])
        else:
            src_text = src[int(linespec) - 1]
        blk = blocks[idx - 1].strip("\n")
        print("=" * 100)
        print("块#%d vs %s 第 %s 行" % (idx, rel, linespec))
        sm = difflib.SequenceMatcher(None, blk, src_text, autojunk=False)
        shown = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                continue
            print("  [%s] 报告=%r  源=%r" % (tag, blk[i1:i2][:120], src_text[j1:j2][:120]))
            shown += 1
            if shown >= 12:
                print("  …（其余差异省略）")
                break
        if shown == 0:
            print("  无差异")


if __name__ == "__main__":
    main()
