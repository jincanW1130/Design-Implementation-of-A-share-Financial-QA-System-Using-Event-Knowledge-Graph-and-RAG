# -*- coding: utf-8 -*-
"""逐条抓取候选文献的知网空间文章页，留证并抽取字段。

纪律：
- 不登录、不使用账号或密码、不提交任何凭据；
- 只访问文章页（cnki.com.cn / cdmd.cnki.com.cn），不访问 kns.cnki.net，
  不点击、不请求任何 PDF/CAJ 下载链接；
- 每个请求间隔 >= 2 秒。

产出：
- 证据/<原编号>_<候选序号>.html   原始文章页 HTML
- 证据/<原编号>_<候选序号>.txt    抽出的字段文本
- _脚本/_请求清单.txt            追加逐条请求登记
"""
from __future__ import annotations

import os
import re
import sys
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(BASE, "_脚本")
EVID_DIR = os.path.join(BASE, "证据")
REQ_LOG = os.path.join(SCRIPT_DIR, "_请求清单.txt")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# (原编号, 候选序号, 文章页 URL)
CANDIDATES: list[tuple[str, int, str]] = [
    # 方向一 知识图谱
    ("KG-5", 1, "https://cdmd.cnki.com.cn/Article/CDMD-10213-1021900210.htm"),
    ("KG-5", 2, "https://cdmd.cnki.com.cn/Article/CDMD-11845-1025532318.htm"),
    ("KG-9", 1, "https://www.cnki.com.cn/Article/CJFDTotal-KXTS202608009.htm"),
    ("KG-9", 2, "https://cdmd.cnki.com.cn/Article/CDMD-10702-1025432270.htm"),
    ("KG-16", 1, "https://www.cnki.com.cn/Article/CJFDTotal-SDDX202407004.htm"),
    ("KG-17", 1, "https://cdmd.cnki.com.cn/Article/CDMD-10140-1026248350.htm"),
    ("KG-19", 1, "https://www.cnki.com.cn/Article/CJFDTotal-RJXB202511014.htm"),
    ("KG-19", 2, "https://www.cnki.com.cn/Article/CJFDTotal-JYRJ202605001.htm"),
    ("KG-21", 1, "https://www.cnki.com.cn/Article/CJFDTotal-XNZY202203011.htm"),
    ("KG-28", 1, "https://www.cnki.com.cn/Article/CJFDTotal-KZYC202105001.htm"),
    ("KG-29", 1, "https://www.cnki.com.cn/Article/CJFDTotal-QBGC202503007.htm"),
    ("KG-29", 2, "https://www.cnki.com.cn/Article/CJFDTotal-BJDZ202101013.htm"),
    # 方向二 RAG
    ("RAG-1", 1, "https://www.cnki.com.cn/Article/CJFDTotal-JSJA202607012.htm"),
    ("RAG-9", 1, "https://www.cnki.com.cn/Article/CJFDTotal-XDTQ202603010.htm"),
    ("RAG-9", 2, "https://www.cnki.com.cn/Article/CJFDTotal-WHQC202604013.htm"),
    ("RAG-10", 1, "https://www.cnki.com.cn/Article/CJFDTotal-JSJA202609004.htm"),
    ("RAG-10", 2, "https://cdmd.cnki.com.cn/Article/CDMD-11660-1026346236.htm"),
    ("RAG-11", 1, "https://www.cnki.com.cn/Article/CJFDTotal-QBXB202508010.htm"),
    ("RAG-11", 2, "https://www.cnki.com.cn/Article/CJFDTotal-ZYJC202607013.htm"),
    ("RAG-13", 1, "https://www.cnki.com.cn/Article/CJFDTotal-NYJX202614026.htm"),
    ("RAG-13", 2, "https://cdmd.cnki.com.cn/Article/CDMD-10574-1026374805.htm"),
    ("RAG-24", 1, "https://www.cnki.com.cn/Article/CJFDTotal-ZZYZ202617008.htm"),
    ("RAG-24", 2, "https://www.cnki.com.cn/Article/CJFDTotal-QBTS202609016.htm"),
    # 方向三 金融问答
    ("FIN-3", 1, "https://cdmd.cnki.com.cn/Article/CDMD-10749-1026398545.htm"),
    ("FIN-16", 1, "https://www.cnki.com.cn/Article/CJFDTotal-JFYZ202609006.htm"),
    ("FIN-16", 2, "https://cdmd.cnki.com.cn/Article/CDMD-11660-1026346229.htm"),
    ("FIN-17", 1, "https://www.cnki.com.cn/Article/CJFDTotal-DZJY202606022.htm"),
    ("FIN-20", 1, "https://www.cnki.com.cn/Article/CJFDTotal-ZGJN202606017.htm"),
    ("FIN-20", 2, "https://cdmd.cnki.com.cn/Article/CDMD-10431-1026344616.htm"),
    # 方向四 软件系统
    ("SYS-4", 1, "https://www.cnki.com.cn/Article/CJFDTotal-SZJT202602019.htm"),
    ("SYS-8", 1, "https://www.cnki.com.cn/Article/CJFDTotal-SSDB202604002.htm"),
    ("SYS-8", 2, "https://www.cnki.com.cn/Article/CJFDTotal-DWJS202608019.htm"),
    ("SYS-13", 1, "https://www.cnki.com.cn/Article/CJFDTotal-GYKJ202607044.htm"),
    ("SYS-13", 2, "https://www.cnki.com.cn/Article/CJFDTotal-JSJA2026S1058.htm"),
    ("SYS-14", 1, "https://www.cnki.com.cn/Article/CJFDTotal-DKJS202603009.htm"),
    ("SYS-14", 2, "https://www.cnki.com.cn/Article/CJFDTotal-SJSJ202608032.htm"),
]


def log_line(method: str, note: str, url: str, info: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(REQ_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{ts}\t{method}\tarticle\t{note}\t{url}\t{info}\n")


def squeeze(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_page(html: str, url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {"url": url}

    title_tag = soup.find("title")
    out["page_title"] = squeeze(title_tag.get_text()) if title_tag else ""
    if out["page_title"]:
        m = re.match(r"^(.*?)--(.*)$", out["page_title"])
        if m:
            out["title_from_tag"] = squeeze(m.group(1))
            out["source_from_tag"] = squeeze(m.group(2))

    h1 = soup.find("h1")
    out["h1"] = squeeze(h1.get_text()) if h1 else ""

    # 作者：页面作者栏链接
    authors = []
    for a in soup.select('a[href*="author"]'):
        name = squeeze(a.get_text())
        if name and 1 < len(name) <= 12 and name not in authors:
            authors.append(name)
    if not authors:
        node = soup.select_one("#authorlen, .author")
        if node:
            authors = [squeeze(x) for x in re.split(r"[;,，、\s]+", node.get_text()) if squeeze(x)]
    out["authors"] = ", ".join(authors[:20])

    text = squeeze(soup.get_text(" ", strip=True))
    out["text_len"] = str(len(text))

    m = re.search(r"【摘要】\s*[:：]?\s*(.{0,900}?)(?:【关键词】|关键词|【引证文献】|下载App)", text)
    out["abstract"] = m.group(1)[:900] if m else ""
    m = re.search(r"关键词[：:]\s*(.{0,200}?)(?:【|下载|更多同类)", text)
    out["keywords"] = m.group(1)[:200] if m else ""
    m = re.search(r"(DOI|doi)[:：]?\s*(10\.[0-9]{4,9}/[^\s，。；]+)", text)
    out["doi"] = m.group(2) if m else ""
    m = re.search(r"(下载|被引)\s*[:：]?\s*[（(]?\s*(\d+)", text)
    out["download_first"] = m.group(2) if m else ""
    m = re.search(r"被引[（(]?\s*(\d+)", text)
    out["cited"] = m.group(1) if m else ""
    for label, pat in (
        ("基金", r"基金[：:]\s*(.{0,160}?)(?:【|作者|摘要)"),
        ("机构", r"机构[：:]\s*(.{0,120}?)(?:【|摘要|关键词)"),
    ):
        mm = re.search(pat, text)
        out[label] = mm.group(1) if mm else ""
    return out


def main() -> None:
    os.makedirs(EVID_DIR, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    log_line("GET", "RUN_START", "02_抓文章页.py")
    ok = 0
    for code, idx, url in CANDIDATES:
        html_path = os.path.join(EVID_DIR, f"{code}_{idx}.html")
        txt_path = os.path.join(EVID_DIR, f"{code}_{idx}.txt")
        if os.path.exists(html_path) and os.path.getsize(html_path) > 5000:
            print(f"[skip] {code}_{idx}")
            ok += 1
            continue
        try:
            r = session.get(url, timeout=45)
            r.encoding = r.apparent_encoding or "utf-8"
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write(r.text)
            fields = parse_page(r.text, url)
            fields["http_status"] = str(r.status_code)
            fields["bytes"] = str(len(r.content))
            with open(txt_path, "w", encoding="utf-8") as fh:
                for k, v in fields.items():
                    fh.write(f"{k}\t{v}\n")
            log_line("GET", "FETCH", url, f"status={r.status_code} bytes={len(r.content)}")
            print(f"[{code}_{idx}] {r.status_code} {len(r.content)}B | {fields.get('h1','')[:40]} | {fields.get('source_from_tag','')[:28]}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            log_line("GET", "ERROR", url, str(exc)[:200])
            print(f"[{code}_{idx}] ERROR {exc}")
        time.sleep(2.2)
    log_line("GET", "RUN_END", f"ok={ok}/{len(CANDIDATES)}")
    print(f"done {ok}/{len(CANDIDATES)}")


if __name__ == "__main__":
    main()
