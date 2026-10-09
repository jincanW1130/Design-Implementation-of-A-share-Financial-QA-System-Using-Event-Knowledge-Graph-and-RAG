# -*- coding: utf-8 -*-
"""把报告代码块 #3 与 #23 中的弯引号改回源文件使用的直引号，使引文逐字。

只改报告文件自身（本产物目录内），不改任何既有文件。
"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))

TARGET_BLOCKS = (3, 23)


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    pattern = re.compile(r"```[a-zA-Z]*\n(.*?)```", flags=re.S)
    counter = {"n": 0}

    def repl(match):
        counter["n"] += 1
        if counter["n"] in TARGET_BLOCKS:
            body = match.group(1)
            fixed = body.replace("\u201c", '"').replace("\u201d", '"')
            return match.group(0).replace(body, fixed)
        return match.group(0)

    new_text = pattern.sub(repl, text)
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new_text)
    print("已处理块 #%s" % ", ".join(str(x) for x in TARGET_BLOCKS))


if __name__ == "__main__":
    main()
