# -*- coding: utf-8 -*-
"""扫描归档池（四方向 + 四补充 + 汇总）中的全部中文条目，输出：

- _脚本/_归档池中文条目.json   结构化清单

只读归档文件与 文献PDF/ 目录，不写任何归档文件。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BASE)
ARCH = os.path.join(ROOT, "_归档_20260923_文献调研过程文件")
PDFDIR = os.path.join(ROOT, "文献PDF")
OUT = os.path.join(BASE, "_脚本", "_归档池中文条目.json")

# (文件, 基础条目编号前缀)  方向文件里 [1]..[n] 的编号需补前缀
FILES = [
    (os.path.join(ARCH, "方向一_知识图谱文献.md"), "KG-"),
    (os.path.join(ARCH, "方向二_RAG文献.md"), "RAG-"),
    (os.path.join(ARCH, "方向三_金融问答文献.md"), "FIN-"),
    (os.path.join(ARCH, "方向四_软件系统文献.md"), "SYS-"),
    (os.path.join(ARCH, "_补充", "KG_补充候选.md"), ""),
    (os.path.join(ARCH, "_补充", "RAG_补充候选.md"), ""),
    (os.path.join(ARCH, "_补充", "FIN_补充候选.md"), ""),
    (os.path.join(ARCH, "_补充", "SYS_补充候选.md"), ""),
    (os.path.join(ARCH, "03-文献调研汇总.md"), ""),
]

CJK = re.compile(r"[\u4e00-\u9fff]")


def squeeze(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def pdf_names() -> list[str]:
    return sorted(os.listdir(PDFDIR)) if os.path.isdir(PDFDIR) else []


def has_pdf(code: str, names: list[str]) -> str:
    hit = [n for n in names if n.startswith(code + "_")]
    return hit[0] if hit else ""


def source_of(citation: str) -> str:
    """从题录行里截取出处片段（启发式，仅用于人工核对）。"""
    m = re.search(r"\.\s*([^.]{4,60}?),\s*(19|20)\d{2}", citation)
    if m:
        return squeeze(m.group(1))
    m = re.search(r"(《[^》]+》[^,，。]*)", citation)
    if m:
        return squeeze(m.group(1))
    m = re.search(r"(19|20)\d{2}", citation)
    return ""


def year_of(citation: str) -> str:
    ys = re.findall(r"(19|20)\d{2}", citation)
    m = re.findall(r"((?:19|20)\d{2})", citation)
    return m[-1] if m else ""


def main() -> None:
    names = pdf_names()
    records: list[dict] = []
    for path, prefix in FILES:
        if not os.path.exists(path):
            print("缺失", path)
            continue
        text = io.open(path, encoding="utf-8").read()
        rel = os.path.relpath(path, ROOT)
        entries: list[tuple[str, str]] = []
        # 形态 A：代码块内的 [n] 题录
        for block in re.findall(r"```(.*?)```", text, re.S):
            lines = [l for l in block.splitlines()]
            if not lines:
                continue
            first = next((l for l in lines if l.strip()), "")
            m = re.match(r"^\[(\d+)\]\s*(.+)", first.strip())
            if m:
                entries.append((prefix + m.group(1) if prefix else m.group(1), squeeze(m.group(2))))
        # 形态 B：标题式 [KG-16] / [RAG-16] / [1]
        for m in re.finditer(r"^###?\s*\[([A-Z]*-?\d+)\]\s*(.+)$", text, re.M):
            raw = m.group(1)
            code = raw
            if re.fullmatch(r"\d+", raw) and prefix:
                code = prefix + raw
            entries.append((code, squeeze(m.group(2))))
        # 形态 C：**[KG-1] 题录**
        for m in re.finditer(r"^\*\*\[([A-Z]+-\d+|F?\d+)\]\s*(.+?)\*\*\s*$", text, re.M):
            raw = m.group(1)
            code = raw
            if re.fullmatch(r"\d+", raw) and prefix:
                code = prefix + raw
            entries.append((code, squeeze(m.group(2))))
        # 形态 A 补：代码块里的 [KG-16] / [RAG-16] 题录
        for block in re.findall(r"```(.*?)```", text, re.S):
            first = next((l for l in block.splitlines() if l.strip()), "")
            m = re.match(r"^\[([A-Z]*-?\d+)\]\s*(.+)", first.strip())
            if m and not re.fullmatch(r"\d+", m.group(1)):
                entries.append((m.group(1), squeeze(m.group(2))))
        # 去重（汇总文件与方向文件重复时保留两份，按 文件+编号+题录 去重）
        seen = set()
        for code, citation in entries:
            key = (code, citation[:80])
            if key in seen:
                continue
            seen.add(key)
            # 判断中文：题名部分（作者与出处之间）含 CJK
            title_part = citation
            m = re.match(r"^(.*?)\.\s+(.*)", citation)
            if m:
                title_part = m.group(2)
            title_part = re.split(r"[.,]\s*(?:19|20)\d{2}|[.,]\s*(?:arXiv|arXiv:)", title_part)[0]
            is_cn = len(CJK.findall(title_part)) >= 4
            pdf = has_pdf(code, names) if re.match(r"^[A-Z]+-\d+$", code) else ""
            records.append(
                {
                    "来源文件": rel,
                    "编号": code,
                    "题录": citation,
                    "是否中文": is_cn,
                    "疑似出处": source_of(citation),
                    "疑似年份": year_of(citation),
                    "项目内PDF": pdf,
                }
            )
    with io.open(OUT, "w", encoding="utf-8") as fh:
        json.dump(records, fh, ensure_ascii=False, indent=1)
    cn = [r for r in records if r["是否中文"]]
    cn_pdf = [r for r in cn if r["项目内PDF"]]
    print(f"总条目 {len(records)}；中文条目 {len(cn)}；其中项目内已有PDF {len(cn_pdf)}")
    print("->", OUT)


if __name__ == "__main__":
    main()
