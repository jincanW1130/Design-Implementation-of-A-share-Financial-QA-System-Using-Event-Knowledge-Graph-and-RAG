# -*- coding: utf-8 -*-
"""把引文块内行首的 `* ` 列表符号改回源文件的 `- `，并给块 #82 补「整理」标注。"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))

TARGETS = (88, 91, 92, 93, 94, 119, 120)
LABEL_82 = "> **整理（非逐字）**：下列文本块样例取自 `原始输出\\raw_chunks_前2行.txt`（该文件的原始格式为一行一个字段），此处为便于阅读压成两行；`content` 已按 200 字符截断。"


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    pattern = re.compile(r"(?m)^```[a-zA-Z]*\n.*?^```\s*$", flags=re.S)
    matches = list(pattern.finditer(text))
    out = []
    last = 0
    for n, m in enumerate(matches, 1):
        out.append(text[last:m.start()])
        block = m.group(0)
        if n in TARGETS:
            head, rest = block.split("\n", 1)
            body, tail = rest.rsplit("\n```", 1)
            body = "\n".join(re.sub(r"^\* ", "- ", ln) for ln in body.split("\n"))
            out.append(head + "\n" + body + "\n```")
        elif n == 82:
            out.append(LABEL_82 + "\n\n" + block)
        else:
            out.append(block)
        last = m.end()
    out.append(text[last:])
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(out))
    print("已修正列表符号的块：%s；已给块 #82 补标注" % sorted(TARGETS))


if __name__ == "__main__":
    main()
