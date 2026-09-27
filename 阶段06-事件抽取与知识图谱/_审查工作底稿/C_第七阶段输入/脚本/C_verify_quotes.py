# -*- coding: utf-8 -*-
"""C 审查 —— 逐字校验：报告里的代码块是否能在源文件中原样命中。

规则：
  * 只校验长度 >= 30 字符的代码块；
  * 含 `…` 的块按 `…` 切段，逐段校验；
  * 命中即算通过；未命中则把首个不匹配位置与前 3 个最相似的源行片段打印出来，供人工复核。
"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出", "raw_逐字校验结果.txt"))

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


def load_sources():
    blobs = {}
    for rel in SOURCES:
        p = os.path.join(ROOT, rel.replace("/", os.sep))
        if os.path.isfile(p):
            blobs[rel] = io.open(p, encoding="utf-8").read()
    # 同时把本审查自己的原始输出纳入比对（JSONL 逐字段留痕、图谱样例等取自这些文件）
    raw_dir = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
    if os.path.isdir(raw_dir):
        for name in sorted(os.listdir(raw_dir)):
            p = os.path.join(raw_dir, name)
            # 排除本脚本自己的输出，避免自指污染（否则上一轮未命中的块会因为被写进
            # 结果文件而在下一轮“命中”）
            if name in ("raw_逐字校验结果.txt",):
                continue
            if os.path.isfile(p) and name.endswith((".txt", ".md")):
                blobs["原始输出/" + name] = io.open(p, encoding="utf-8").read()
    return blobs


def normalize(text: str) -> str:
    """把引号风格、前导列表符号、空白与换行差异归一，用于区分“排版差异”与“内容差异”。"""
    t = text
    for a, b in (("\u201c", '"'), ("\u201d", '"'), ("\u2018", "'"), ("\u2019", "'"),
                 ("\uff5c", "|"), ("\u3000", " ")):
        t = t.replace(a, b)
    lines = []
    for line in t.split("\n"):
        s = line.strip()
        s = re.sub(r"^[-*\u2022]\s+", "", s)
        s = re.sub(r"^\d+[.\uff0e]\s+", "", s)
        s = re.sub(r"\s+", " ", s)
        if s:
            lines.append(s)
    return " ".join(lines)


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", text, flags=re.S)
    blobs = load_sources()
    norm_blobs = [normalize(b) for b in blobs.values()]
    ok = []
    bad = []
    layout = []
    skipped = []
    for i, block in enumerate(blocks, 1):
        body = block.strip("\n")
        if len(body) < 30:
            skipped.append((i, body))
            continue
        parts = [p.strip("\n") for p in body.split("…") if len(p.strip("\n")) >= 30]
        if not parts:
            skipped.append((i, body))
            continue
        missing = []
        missing_norm = []
        for part in parts:
            if not any(part in blob for blob in blobs.values()):
                npart = normalize(part)
                if any(npart in nb for nb in norm_blobs):
                    missing_norm.append(part)
                else:
                    missing.append(part)
        if missing:
            bad.append((i, body, missing))
        elif missing_norm:
            layout.append((i, body, missing_norm))
        else:
            ok.append(i)

    lines = []
    lines.append("报告：%s" % os.path.relpath(REPORT, ROOT))
    lines.append("代码块总数 %d；逐字命中 %d；仅排版差异（引号风格／列表符号／空白换行）%d；内容差异 %d；跳过（过短）%d"
                 % (len(blocks), len(ok), len(layout), len(bad), len(skipped)))
    lines.append("")
    lines.append("=" * 100)
    lines.append("一、仅排版差异的块（内容可逐字对上，差异只在引号风格、前导列表符号或空白换行）")
    for i, body, _m in layout:
        lines.append("  块 #%d：%s" % (i, body.strip().split("\n")[0][:110]))
    lines.append("")
    lines.append("=" * 100)
    lines.append("二、内容差异的块（归一化后仍无法命中，需人工复核）")
    for i, body, missing in bad:
        lines.append("=" * 100)
        lines.append("未命中：第 %d 个代码块" % i)
        lines.append("---- 报告中的块（前 600 字符）----")
        lines.append(body[:600])
        lines.append("---- 未命中的段（前 600 字符）----")
        lines.append(missing[0][:600])
        lines.append("")
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    print("块总数 %d；逐字命中 %d；仅排版差异 %d；内容差异 %d；跳过 %d"
          % (len(blocks), len(ok), len(layout), len(bad), len(skipped)))
    print("---- 仅排版差异的块 ----")
    for i, body, _m in layout:
        print("  块#%d %s" % (i, body.strip().split("\n")[0][:90]))
    print("---- 内容差异的块 ----")
    for i, _b, missing in bad:
        print("  未命中 块#%d：%s" % (i, missing[0][:90].replace("\n", " ")))


if __name__ == "__main__":
    main()
