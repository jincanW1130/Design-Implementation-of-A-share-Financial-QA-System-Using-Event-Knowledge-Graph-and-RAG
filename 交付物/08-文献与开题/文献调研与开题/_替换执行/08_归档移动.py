# -*- coding: utf-8 -*-
"""把「被替换条目」的替换前全文（PDF／docx）与译文移动到归档目录。

规则（作者裁定第 3 条）：
- 只移动将被替换的 14 条的替换前文件；保留的 6 条英文奠基与 2 条中文条目的全文**留在原位**；
- 不删除任何文件；保留原文件名；
- 归档目录内按原目录名分 `文献PDF\\` 与 `文献翻译\\` 两个子目录：这样项目文档里已有的
  `文献PDF/...` 路径写法（如《核心文献精选20篇.md》引用 FIN-17 全文）在归档后仍可解析，
  《跨文档核验.py》K 组（路径存在性）不会因此失败；该安排与原因写入归档 README。

用法：
    python 08_归档移动.py            # 干跑（只列出将移动的文件，不动盘）
    python 08_归档移动.py --apply    # 实际移动
"""
from __future__ import annotations

import io
import os
import shutil
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 交付物/08-文献与开题/文献调研与开题
PDF_DIR = os.path.join(BASE, "文献PDF")
TR_DIR = os.path.join(BASE, "文献翻译")
ARCH = os.path.join(BASE, "_归档_文献PDF_替换前")

# 被替换的 14 条（槽位）→ 替换前文件名主干
REPLACED = [
    ("KG-5", "KG-5_Li2026_FinKario"),
    ("KG-9", "KG-9_Zheng2019_Doc2EDAG"),
    ("KG-16", "KG-16_Tong2022_DocEE"),
    ("KG-17", "KG-17_Liu2024_DocEE-zh"),
    ("KG-19", "KG-19_Wang2022_MAVEN-ERE"),
    ("KG-29", "KG-29_Ding2021_JEL_EntityLinking"),
    ("RAG-10", "RAG-10_Gutierrez2024_HippoRAG"),
    ("RAG-24", "RAG-24_Min2023_FActScore"),
    ("FIN-16", "FIN-16_Saxena2021_CronKGQA"),
    ("FIN-17", "FIN-17_Mavromatis2022_TempoQR"),
    ("FIN-20", "FIN-20_Kumar2026_HalluBench"),
    ("SYS-4", "SYS-4_Zhang2024_LLM_LayeredArch"),
    ("SYS-8", "SYS-8_Sarmah2024_HybridRAG"),
    ("SYS-14", "SYS-14_Yan2025_HetaRAG"),
]


def main() -> None:
    apply = "--apply" in sys.argv
    plan: list[tuple[str, str]] = []
    for _slot, stem in REPLACED:
        plan.append((os.path.join(PDF_DIR, stem + ".pdf"), os.path.join(ARCH, "文献PDF", stem + ".pdf")))
        docx = os.path.join(PDF_DIR, stem + ".docx")
        if os.path.exists(docx):
            plan.append((docx, os.path.join(ARCH, "文献PDF", stem + ".docx")))
        tr = os.path.join(TR_DIR, stem + "_译文.docx")
        if os.path.exists(tr):
            plan.append((tr, os.path.join(ARCH, "文献翻译", stem + "_译文.docx")))
    print("将移动文件数：%d" % len(plan))
    missing = [s for s, _ in plan if not os.path.exists(s)]
    print("源文件缺失：%d %s" % (len(missing), missing))
    for s, d in plan:
        print("  %s\n    -> %s" % (os.path.relpath(s, BASE), os.path.relpath(d, BASE)))
    if not apply:
        print("（干跑：未移动任何文件）")
        return
    for s, d in plan:
        if not os.path.exists(s):
            continue
        os.makedirs(os.path.dirname(d), exist_ok=True)
        assert os.path.abspath(d).startswith(os.path.abspath(ARCH)), "目标越界"
        shutil.move(s, d)
    print("已移动 %d 个文件" % len(plan))


if __name__ == "__main__":
    main()
