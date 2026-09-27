# -*- coding: utf-8 -*-
"""把“仅排版差异”的代码块恢复成源文件里的逐字片段。

做法：把块内容与源文件都做空白归一（并把弯引号/直引号折叠），在源文件中定位该块对应的
原文区间，再用源文件的原始片段替换块内容。只改报告文件自身。
"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))

SOURCES = [
    "02-项目执行总控文档.md",
    "00-项目总览与索引.md",
    "阶段03-需求分析/07-需求分析（第三阶段）.md",
    "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md",
    "阶段05-数据准备/12-第5阶段任务书（数据准备）.md",
    "阶段05-数据准备/13-数据准备（第五阶段）.md",
    "阶段06-事件抽取与知识图谱/15-第6阶段任务书（事件抽取与知识图谱）.md",
    "阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md",
    "代码/数据准备/config.py",
    "代码/数据准备/embed.py",
    "代码/数据准备/chunk.py",
    "工具/验收第5阶段数据.py",
    "工具/验收第6阶段.py",
    "工具/跨文档核验.py",
]


def norm_char(ch: str) -> str:
    if ch in "\u201c\u201d":
        return '"'
    if ch in "\u2018\u2019":
        return "'"
    if ch == "\uff5c":
        return "|"
    return ch


def normalize_with_map(text: str):
    """返回（归一化字符串, 每个归一化字符在原文中的下标）。"""
    out = []
    pos = []
    prev_space = True
    for i, ch in enumerate(text):
        c = norm_char(ch)
        if c in " \t\r\n\u3000":
            if prev_space:
                continue
            out.append(" ")
            pos.append(i)
            prev_space = True
        else:
            out.append(c)
            pos.append(i)
            prev_space = False
    return "".join(out), pos


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    blobs = []
    for rel in SOURCES:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.isfile(p):
            blobs.append((rel, io.open(p, encoding="utf-8").read()))
    for rel, blob in list(blobs):
        if not blob:
            continue
    norm_sources = [(rel, b, *normalize_with_map(b)) for rel, b in blobs]

    pattern = re.compile(r"(?m)^```[a-zA-Z]*\n.*?^```\s*$", flags=re.S)
    matches = list(pattern.finditer(text))
    out = []
    last = 0
    fixed = []
    for n, m in enumerate(matches, 1):
        block = m.group(0)
        body = block.split("\n", 1)[1].rsplit("\n```", 1)[0]
        out.append(text[last:m.start()])
        if "\u2026" in body or n in (81, 84, 86, 125, 126, 127, 128, 132, 133, 136, 137, 138, 140, 142, 143):
            out.append(block)
            last = m.end()
            continue
        nb, _pos = normalize_with_map(body)
        nb = nb.strip()
        if len(nb) < 40:
            out.append(block)
            last = m.end()
            continue
        found = None
        for rel, src, nsrc, pos in norm_sources:
            j = nsrc.find(nb)
            if j >= 0:
                start = pos[j]
                end = pos[j + len(nb) - 1]
                found = (rel, src[start:end + 1])
                break
        if found and found[1] != body:
            fence_open = block.split("\n", 1)[0]
            out.append(fence_open + "\n" + found[1] + "\n```")
            fixed.append((n, found[0]))
        else:
            out.append(block)
        last = m.end()
    out.append(text[last:])
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(out))
    print("修复块数 %d" % len(fixed))
    for n, rel in fixed:
        print("  块#%d <- %s" % (n, rel))


if __name__ == "__main__":
    main()
