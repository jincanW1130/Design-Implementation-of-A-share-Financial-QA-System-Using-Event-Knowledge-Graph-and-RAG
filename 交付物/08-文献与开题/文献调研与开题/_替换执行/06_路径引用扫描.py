# -*- coding: utf-8 -*-
"""扫描工作区全部 Markdown，列出所有以反引号写法引用「将被归档文件」的 token，
用于预判《跨文档核验.py》K 组（路径存在性）在归档后是否会失败。
只读，不修改任何文件。
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PREFIXES = [
    "KG-5_Li2026_FinKario", "KG-9_Zheng2019_Doc2EDAG", "KG-16_Tong2022_DocEE",
    "KG-17_Liu2024_DocEE-zh", "KG-19_Wang2022_MAVEN-ERE", "KG-29_Ding2021_JEL_EntityLinking",
    "RAG-10_Gutierrez2024_HippoRAG", "RAG-24_Min2023_FActScore", "FIN-16_Saxena2021_CronKGQA",
    "FIN-17_Mavromatis2022_TempoQR", "FIN-20_Kumar2026_HalluBench", "SYS-4_Zhang2024_LLM_LayeredArch",
    "SYS-8_Sarmah2024_HybridRAG", "SYS-14_Yan2025_HetaRAG",
]


def main() -> None:
    files = sorted(glob.glob(os.path.join(ROOT, "*.md")))
    for sd in sorted(glob.glob(os.path.join(ROOT, "阶段*"))):
        files += sorted(glob.glob(os.path.join(sd, "*.md")))
    n = 0
    for p in files:
        t = io.open(p, encoding="utf-8").read()
        for m in re.finditer(r"`([^`\n]{3,160}?)`", t):
            tok = m.group(1)
            if any(pre in tok for pre in PREFIXES):
                has_dir = ("/" in tok) or ("\\" in tok)
                print(f"{os.path.relpath(p, ROOT)}\t{'DIR' if has_dir else 'bare'}\t{tok}")
                n += 1
    print("total", n)


if __name__ == "__main__":
    main()
