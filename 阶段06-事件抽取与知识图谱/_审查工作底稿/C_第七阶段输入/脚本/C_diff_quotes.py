# -*- coding: utf-8 -*-
"""定位报告代码块与源文件之间的逐字符差异（只读，打印到 stdout）。"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))

SOURCES = [
    "02-项目执行总控文档.md",
    "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md",
    "阶段05-数据准备/13-数据准备（第五阶段）.md",
    "阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md",
]


def normalize(text: str) -> str:
    t = text
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'")):
        t = t.replace(a, b)
    lines = []
    for line in t.split("\n"):
        s = re.sub(r"\s+", " ", line.strip())
        if s:
            lines.append(s)
    return "\n".join(lines)


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S)
    blobs = {rel: normalize(io.open(os.path.join(ROOT, rel.replace("/", os.sep)), encoding="utf-8").read())
             for rel in SOURCES}
    for idx in (3, 23):
        block = normalize(blocks[idx - 1]).strip("\n")
        print("=" * 100)
        print("块#%d 归一化后的前 300 字符：\n%s" % (idx, block[:300]))
        blob = blobs["02-项目执行总控文档.md" if idx == 3 else "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md"]
        print("  比对源：%s" % ("02-项目执行总控文档.md" if idx == 3 else "10-系统总体设计（第四阶段）.md"))
        for part in [p for p in block.split("\n") if len(p) > 40]:
            if part in blob:
                print("  该行在《02》中逐字命中（归一化后）")
                continue
            lo, hi = 0, len(part)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if part[:mid] in blob:
                    lo = mid
                else:
                    hi = mid - 1
            k = max(0, lo - 30)
            print("  首个不匹配处（前缀长度 %d）" % lo)
            print("  报告中：…%s" % part[k:lo + 30])
            j = blob.find(part[:lo])
            if j >= 0:
                print("  《02》中：…%s" % blob[max(0, j + lo - 60):j + lo + 30])


if __name__ == "__main__":
    main()
