# -*- coding: utf-8 -*-
"""按知网文章 ID 段扫描，核实裁定点名的池内候选 SYS-16／SYS-18 题录。

背景：池内候选 SYS-16／SYS-18 均刊于《计算机科学与探索》（知网刊名代码 KXTS），
公开检索页（search.cnki.com.cn）对其题名无命中；本脚本只在**该刊对应年期的公开文章页 ID 段**
内逐条 GET，命中即停，用于核实题录（不下载、不登录、不点击全文入口）。
请求间隔 >= 2.6 秒。
产出：证据/_替换页/SYS16_扫描_<id>.html（仅命中页）与 _替换执行/_按刊号扫描.txt
"""
from __future__ import annotations

import io
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(BASE, "_知网替换", "证据", "_替换页")
OUT = os.path.join(BASE, "_替换执行", "_按刊号扫描.txt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# (标签, 文章 ID 前缀, 起, 止, 目标题名关键词)
SCAN = [
    ("SYS-18", "https://www.cnki.com.cn/Article/CJFDTotal-KXTS202501%03d.htm", 1, 25,
     "融合知识图谱和大模型的高校科研管理问答系统设计"),
    ("SYS-16", "https://www.cnki.com.cn/Article/CJFDTotal-KXTS202410%03d.htm", 1, 30,
     "基于大语言模型的知识图谱构建及应用研究"),
]


def squeeze(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def main() -> None:
    os.makedirs(EVID, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    lines = []
    for label, pattern, lo, hi, target in SCAN:
        found = False
        for i in range(lo, hi + 1):
            url = pattern % i
            try:
                r = s.get(url, timeout=30)
                r.encoding = "utf-8"
                soup = BeautifulSoup(r.text, "html.parser")
                title = squeeze(soup.title.get_text()) if soup.title else ""
                ok = target in title or target in r.text[:200000]
                lines.append(f"{label}\t{i}\tstatus={r.status_code}\tbytes={len(r.content)}\thit={ok}\ttitle={title[:80]}")
                print(f"[{label}] {i} {r.status_code} {len(r.content)}B hit={ok} {title[:60]}")
                if ok:
                    p = os.path.join(EVID, f"{label}_扫描_命中.html")
                    with io.open(p, "w", encoding="utf-8") as fh:
                        fh.write(r.text)
                    lines.append(f"{label}\tFOUND\t{url}")
                    found = True
                    break
            except Exception as exc:  # noqa: BLE001
                lines.append(f"{label}\t{i}\tERROR={exc}")
                print(f"[{label}] {i} ERROR {exc}")
            time.sleep(2.6)
        lines.append(f"{label}\tRESULT\tfound={found}")
        print(f"[{label}] found={found}")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("done")


if __name__ == "__main__":
    main()
