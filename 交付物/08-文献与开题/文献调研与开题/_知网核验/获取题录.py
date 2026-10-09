# -*- coding: utf-8 -*-
"""访问知网文章页获取完整题录信息。"""
from __future__ import annotations
import requests, re, sys
from bs4 import BeautifulSoup
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

URLS = [
    ("KG-9",  "https://www.cnki.com.cn/Article/CJFDTOTAL-KXTS202608009.htm"),
    ("RAG-1", "https://www.cnki.com.cn/Article/CJFDTOTAL-JSJA202607012.htm"),
    ("SYS-8", "https://www.cnki.com.cn/Article/CJFDTOTAL-SSDB202604002.htm"),
    ("SYS-14","https://www.cnki.com.cn/Article/CJFDTOTAL-DWJS202608019.htm"),
    ("FIN-17","https://www.cnki.com.cn/Article/CJFDTOTAL-DZJY202606022.htm"),
    ("KG-29", "https://www.cnki.com.cn/Article/CJFDTOTAL-QBGC202603010.htm"),
]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"

for tag, url in URLS:
    print(f"\n=== {tag}: {url} ===")
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
        r.encoding = r.apparent_encoding
        soup = BeautifulSoup(r.text, "html.parser")
        # title
        t = soup.select_one("h1") or soup.select_one("title")
        print("TITLE:", t.get_text(strip=True) if t else "N/A")
        # 找作者
        authors = [a.get_text(strip=True) for a in soup.select("p.author a, .author a, #authorlen a")]
        print("AUTHORS:", authors)
        # 找来源/期刊
        src = soup.select_one("p.organ a, .organ a, #srcart, .sourname")
        print("SOURCE:", src.get_text(strip=True) if src else "N/A")
        # 找摘要
        abs_div = soup.select_one("div.abstract, #ChDivSummary, .abstract-text")
        if abs_div:
            print("ABSTRACT:", abs_div.get_text(strip=True)[:200])
        # 找年卷期 - 在页面文本中搜索
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(20\d{2})\s*年", text)
        if m: print("YEAR_FOUND:", m.group(0))
        # 找关键词
        kw = soup.select("p.keywords a, .keywords a")
        if kw: print("KEYWORDS:", [k.get_text(strip=True) for k in kw])
    except Exception as e:
        print(f"ERROR: {e}")
