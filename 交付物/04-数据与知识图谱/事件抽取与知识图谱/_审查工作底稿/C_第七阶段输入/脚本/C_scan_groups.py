# -*- coding: utf-8 -*-
"""C 审查 —— 打印两份验收脚本的分组标题（紧跟 `print(); print('=' * 78)` 之后的打印行）。"""
from __future__ import annotations

import io
import os

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))


def main():
    out = []
    for rel in ("工具/验收第5阶段数据.py", "工具/验收第6阶段.py"):
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        lines = io.open(path, encoding="utf-8").read().split("\n")
        out.append("=" * 100)
        out.append("文件：%s　共 %d 行" % (rel, len(lines)))
        out.append("=" * 100)
        for idx, line in enumerate(lines):
            if "print('=' * 78)" in line or 'print("=" * 78)' in line:
                if "print();" not in line:
                    continue
                for j in range(idx, min(idx + 4, len(lines))):
                    s = lines[j].strip()
                    if s.startswith("print") and j != idx:
                        out.append("%5d | %s" % (j + 1, s[:180]))
        out.append("")
    dst = os.path.join(OUT, "raw_验收脚本分组标题.txt")
    with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print("[ok] %s" % os.path.relpath(dst, ROOT))


if __name__ == "__main__":
    main()
