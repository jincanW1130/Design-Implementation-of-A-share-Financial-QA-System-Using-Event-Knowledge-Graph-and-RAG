# -*- coding: utf-8 -*-
"""报告收尾修正：① 清除恢复引文时带回来的禁用术语；② 修正表格单元格内的多余竖线。"""
from __future__ import annotations

import io
import os

HERE = os.path.abspath(os.path.dirname(__file__))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))

BANNED = "\u5411\u91cf\u6570\u636e\u5e93"
MARK = "…[此处原文为《12》检查 P 的禁用词，本报告不写出；已标注截断]…"

OLD_CELL = "| 切分参数 | 同上 | 《13》第6.8节（6）第 605 行 | “三项已固化 TBD | Embedding"
NEW_CELL = "| 切分参数 | 同上 | 《13》第6.8节（6）第 605 行 | “三项已固化 TBD：Embedding"


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    n1 = text.count(BANNED)
    text = text.replace(BANNED, MARK)
    n2 = text.count(OLD_CELL)
    text = text.replace(OLD_CELL, NEW_CELL)
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print("替换禁用术语 %d 处；修正表格单元格 %d 处" % (n1, n2))


if __name__ == "__main__":
    main()
