# -*- coding: utf-8 -*-
"""把《跨文档核验.py》的分组名代码块替换为源文件里的逐字注释行。"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))
SRC = os.path.join(ROOT, "工具", "跨文档核验.py")


def main():
    src_lines = io.open(SRC, encoding="utf-8").read().split("\n")
    picked = [ln.rstrip() for ln in src_lines
              if re.match(r"^#\s*-{2,}\s*[A-Z]\s", ln) or re.match(r"^#\s*-{2,}\s*[A-Z]\b.*-{2,}$", ln)]
    picked = [ln for ln in picked if re.match(r"^#\s*-+\s*[A-Z]", ln)]
    text = io.open(REPORT, encoding="utf-8").read()
    pattern = re.compile(r"(?m)^```[a-zA-Z]*\n.*?^```\s*$", flags=re.S)
    matches = list(pattern.finditer(text))
    out = []
    last = 0
    replaced = 0
    for n, m in enumerate(matches, 1):
        out.append(text[last:m.start()])
        block = m.group(0)
        body = block.split("\n", 1)[1].rsplit("\n```", 1)[0]
        if n == 140 or ("---- A 规模" in body and "---- B 表格列数" in body):
            head = block.split("\n", 1)[0]
            out.append(head + "\n" + "\n".join(picked) + "\n```")
            replaced += 1
        else:
            out.append(block)
        last = m.end()
    out.append(text[last:])
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(out))
    print("替换块数 %d，写入 %d 行" % (replaced, len(picked)))
    for ln in picked:
        print("  " + ln)


if __name__ == "__main__":
    main()
