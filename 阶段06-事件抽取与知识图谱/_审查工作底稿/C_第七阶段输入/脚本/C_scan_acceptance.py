# -*- coding: utf-8 -*-
"""C 审查 —— 扫专项验收脚本的分组结构与判定方式（只读，只写本产物目录）。"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

FILES = ["工具/验收第5阶段数据.py", "工具/验收第6阶段.py", "工具/跨文档核验.py"]


def main():
    out = []
    for rel in FILES:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        text = io.open(path, encoding="utf-8").read()
        lines = text.split("\n")
        out.append("=" * 100)
        out.append("文件：%s　共 %d 行" % (rel, len(lines)))
        out.append("=" * 100)
        for idx, line in enumerate(lines, 1):
            s = line.strip()
            if re.match(r"^#\s*[A-Z]\s*[组\u3001.．-]", s) or re.match(r"^#\s*[A-Z]\s*$", s):
                out.append("%5d | %s" % (idx, s[:190]))
            elif re.match(r"^def main", s) or re.match(r"^def check", s):
                out.append("%5d | %s" % (idx, s[:190]))
            elif "打印" in s and s.startswith("#"):
                out.append("%5d | %s" % (idx, s[:190]))
        out.append("")
    dst = os.path.join(OUT, "raw_验收脚本分组结构.txt")
    with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print("[ok] %s" % os.path.relpath(dst, ROOT))


if __name__ == "__main__":
    main()
