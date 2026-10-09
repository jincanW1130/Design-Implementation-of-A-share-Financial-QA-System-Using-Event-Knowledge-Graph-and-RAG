# -*- coding: utf-8 -*-
"""给报告里“非逐字”的代码块加「整理」标注，并把误入引文块的出处标签移到块外。

只改报告文件自身（本产物目录内）。
"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
REPORT = os.path.abspath(os.path.join(HERE, "..", "C_第七阶段设计输入侦察报告.md"))

# 块号 -> 块前的说明行（“整理”类）
LABELS = {
    81: "> **整理（非逐字）**：下列字段值取自 `原始输出\\raw_documents_前2行.txt`（该文件的原始格式为一行一个字段），此处为便于阅读保持同样的分行；`content` 已按 200 字符截断。",
    84: "> **整理（非逐字）**：下列节点样例取自 `原始输出\\raw_图谱导出_表头与样例.txt`，为便于阅读按字段分行；其余 25 列在这两行上均为空。",
    86: "> **整理（非逐字）**：下列边样例取自 `原始输出\\raw_图谱导出_表头与样例.txt`，为便于阅读按字段分行。",
    125: "> **摘录（非逐字）**：下列为 `config.py` 第 420／432～443 行的摘录，用 `...` 表示被省略的中间行。",
    126: "> **摘录（非逐字）**：下列为 `config.py` 第 44～48 行的摘录，用 `...` 表示被省略的中间行。",
    127: "> **摘录（非逐字）**：下列为 `chunk.py` 第 143～148 行的摘录，用 `...` 表示被省略的中间行。",
    128: "> **摘录（非逐字）**：下列为 `embed.py` 第 319～337 行的摘录，用 `...` 表示被省略的中间行。",
    132: "> **整理（非逐字）**：下列为 `12-第5阶段任务书（数据准备）.md` 的目录整理（小节标题逐字，未保留原文件的空行与缩进）。",
    133: "> **整理（非逐字）**：下列为 `15-第6阶段任务书（事件抽取与知识图谱）.md` 的目录整理（小节标题逐字，未保留原文件的空行与缩进）。",
    136: "> **整理（非逐字）**：下列为 `工具\\验收第6阶段.py` 的分组标题摘录（只取分组名，省略了分组内各行）。",
    137: "> **整理（非逐字）**：下列为 `工具\\验收第5阶段数据.py` 的分组标题摘录（只取分组名，省略了分组内各行）。",
    138: "> **整理（非逐字）**：下列为 `工具\\验收第6阶段.py` 第 209～266 行的两段注释摘录（原文两段之间隔有其他代码，此处并列）。",
    140: "> **整理（非逐字）**：下列为 `工具\\跨文档核验.py` 的分组名摘引（已去掉各行的 `# ----` 前缀与虚线）。",
    142: "> **整理（非逐字）**：下列为 `13-数据准备（第五阶段）.md` 的一级小节清单（标题逐字）。",
    143: "> **整理（非逐字）**：下列为 `16-事件抽取与知识图谱（第六阶段）.md` 的一级小节清单（标题逐字）。",
}

# 块号 -> （原块内首行标签, 需要移出块外的说明）
MOVE_LABEL = {
    88: "（《16》第9.1节）",
    89: "（《15》第4.3节）",
    90: "（《15》第6节）",
}


def main():
    text = io.open(REPORT, encoding="utf-8").read()
    pattern = re.compile(r"(?m)^```[a-zA-Z]*\n.*?^```\s*$", flags=re.S)
    matches = list(pattern.finditer(text))
    out = []
    last = 0
    for n, m in enumerate(matches, 1):
        block = m.group(0)
        out.append(text[last:m.start()])
        if n in MOVE_LABEL:
            tag = MOVE_LABEL[n]
            fence_open = block.split("\n", 1)[0]
            body = block.split("\n", 1)[1]
            body = body.replace(tag, "", 1)
            out.append("%s\n" % tag)
            out.append(fence_open + "\n" + body)
        else:
            if n in LABELS:
                out.append(LABELS[n] + "\n\n")
            out.append(block)
        last = m.end()
    out.append(text[last:])
    with io.open(REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("".join(out))
    print("已标注块：%s" % sorted(LABELS))
    print("已移出标签：%s" % sorted(MOVE_LABEL))


if __name__ == "__main__":
    main()
