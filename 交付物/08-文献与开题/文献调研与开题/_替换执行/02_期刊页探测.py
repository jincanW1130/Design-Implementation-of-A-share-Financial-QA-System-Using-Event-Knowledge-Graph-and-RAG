# -*- coding: utf-8 -*-
"""探测知网公开期刊目录页（cnki.com.cn/Journal/...）是否可直接访问，
用于核实裁定点名的池内候选（SYS-16、SYS-18、RAG-15）题录。

纪律：不登录、不下载、不点击全文入口；请求间隔 >= 2.6 秒。
产出：证据/_检索页/<标签>_期刊页.html 与 _替换执行/_期刊页探测.txt
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
EVID = os.path.join(BASE, "_知网替换", "证据", "_检索页")
OUT = os.path.join(BASE, "_替换执行", "_期刊页探测.txt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

URLS = [
    ("KXTS_journal", "https://www.cnki.com.cn/Journal/I-I1-KXTS.htm", ""),
    ("KXTS_2024_10", "https://www.cnki.com.cn/Journal/I-I1-KXTS-2024-10.htm", "SYS-16"),
    ("KXTS_2025_01", "https://www.cnki.com.cn/Journal/I-I1-KXTS-2025-01.htm", "SYS-18"),
    ("RJXB_journal", "https://www.cnki.com.cn/Journal/I-I1-RJXB.htm", "RAG-15"),
]


def squeeze(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def main() -> None:
    os.makedirs(EVID, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    lines = []
    for tag, url, why in URLS:
        try:
            r = s.get(url, timeout=45)
            r.encoding = "utf-8"
            p = os.path.join(EVID, f"{tag}.html")
            with io.open(p, "w", encoding="utf-8") as fh:
                fh.write(r.text)
            soup = BeautifulSoup(r.text, "html.parser")
            title = squeeze(soup.title.get_text()) if soup.title else ""
            links = [a.get("href") for a in soup.select("a[href]") if a.get("href")]
            art = [x for x in links if "Article" in x][:5]
            lines.append(f"{tag}\t{why}\tstatus={r.status_code}\tbytes={len(r.content)}\ttitle={title}\tarticle_links={len([x for x in links if 'Article' in x])}\tsample={art}")
            print(f"[{tag}] {r.status_code} {len(r.content)}B title={title} articles={len([x for x in links if 'Article' in x])}")
            print("    ", art[:3])
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{tag}\t{why}\tERROR={exc}")
            print(f"[{tag}] ERROR {exc}")
        time.sleep(2.6)
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("done")


if __name__ == "__main__":
    main()
