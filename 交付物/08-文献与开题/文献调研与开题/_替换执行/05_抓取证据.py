# -*- coding: utf-8 -*-
"""为本次「混合替换」补齐证据文件（落 _知网替换/证据/，与原证据同格式）。

纪律：不登录、不下载、不点击任何全文入口；请求间隔 >= 2.6 秒。
产出：证据/<编号>.html 与 证据/<编号>.txt（键\t值），以及 _替换执行/_抓取证据.txt 日志。
"""
from __future__ import annotations

import io
import os
import re
import shutil
import sys
import time

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(BASE, "_知网替换", "证据")
SCANDIR = os.path.join(EVID, "_替换页")
OUT = os.path.join(BASE, "_替换执行", "_抓取证据.txt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# (证据名, 页面 URL 或 "" 表示复用已抓取 HTML, 复用来源, 对照表/裁定所写题名)
TARGETS = [
    ("KG-7", "https://www.cnki.com.cn/Article/CJFDTOTAL-XDTQ2022Z1017.htm", "",
     "知识关联视角下金融证券知识图谱构建与相关股票发现"),
    ("SYS-16", "", os.path.join(SCANDIR, "SYS-16_扫描_命中.html"),
     "基于大语言模型的知识图谱构建及应用研究"),
    ("SYS-18", "", os.path.join(SCANDIR, "SYS-18_扫描_命中.html"),
     "融合知识图谱和大模型的高校科研管理问答系统设计"),
    ("SYS-13新_张广东", "https://cdmd.cnki.com.cn/Article/CDMD-10431-1026344679.htm", "",
     "面向检索增强生成系统的流程优化方法研究"),
    ("SYS-13新_吴海周", "https://www.cnki.com.cn/Article/CJFDTOTAL-GYKJ202607044.htm", "",
     "基于RAG机制的知识库问答性能优化与参数调控研究"),
]


def squeeze(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def parse_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, str] = {"url": url}
    tt = soup.find("title")
    out["page_title"] = squeeze(tt.get_text()) if tt else ""
    if out["page_title"]:
        m = re.match(r"^(.*?)--(.*)$", out["page_title"])
        if m:
            out["title_from_tag"] = squeeze(m.group(1))
            out["source_from_tag"] = squeeze(m.group(2))
    h1 = soup.find("h1")
    out["h1"] = squeeze(h1.get_text()) if h1 else ""
    authors = []
    for a in soup.select('a[href*="author"]'):
        name = squeeze(a.get_text())
        if name and 1 < len(name) <= 12 and name not in authors and "免费下载" not in name:
            authors.append(name)
    out["authors"] = "、".join(authors[:20])
    text = squeeze(soup.get_text(" ", strip=True))
    out["text_len"] = str(len(text))
    m = re.search(r"【摘要】\s*[:：]?\s*(.{0,1200}?)(?:【关键词】|【学位授予单位】|【引证文献】|下载App)", text)
    out["abstract"] = m.group(1)[:1200] if m else ""
    m = re.search(r"【关键词】\s*[:：]?\s*(.{0,300}?)(?:【|下载|更多同类)", text)
    out["keywords"] = m.group(1)[:300] if m else ""
    m = re.search(r"(DOI|doi)[:：]?\s*(10\.[0-9]{4,9}/[^\s，。；]+)", text)
    out["doi"] = m.group(2) if m else ""
    for label, pat in (
        ("基金", r"【基金】\s*[:：]?\s*(.{0,200}?)(?:【|作者|摘要)"),
        ("机构", r"【机构】\s*[:：]?\s*(.{0,200}?)(?:【|摘要|关键词)"),
        ("分类号", r"【分类号】\s*[:：]?\s*(.{0,60}?)(?:【|下载)"),
        ("学位授予单位", r"【学位授予单位】\s*[:：]?\s*(.{0,60}?)(?:【|学位级别|$)"),
        ("学位级别", r"【学位级别】\s*[:：]?\s*(.{0,20}?)(?:【|学位授予年份|$)"),
        ("学位授予年份", r"【学位授予年份】\s*[:：]?\s*(.{0,20}?)(?:【|下载|$)"),
    ):
        mm = re.search(pat, text)
        out[label] = squeeze(mm.group(1)) if mm else ""
    out["导师字段出现次数"] = str(len(re.findall(r"导师", text)))
    mm = re.search(r"【导师】\s*[:：]?\s*(.{0,60}?)(?:【|$)", text)
    out["导师"] = squeeze(mm.group(1)) if mm else ""
    links = []
    for a in soup.select("a"):
        t = squeeze(a.get_text())
        if "下载" in t and a.get("href"):
            links.append(f"{t}->{a['href']}")
    out["下载入口"] = " | ".join(links[:6])
    m = re.search(r"《([^》]+)》\s*(\d{4})年(\d{1,2}|S\d{1,2}|\d{1,2}/\d{1,2})期", out.get("source_from_tag", ""))
    if m:
        out["期刊"], out["年"], out["期"] = m.group(1), m.group(2), m.group(3)
    else:
        out["期刊"] = out["年"] = out["期"] = ""
    m = re.search(r"《([^》]+)》\s*(\d{4})年(硕士|博士)论文", out.get("source_from_tag", ""))
    if m:
        out["单位"], out["年份"], out["学位"] = m.group(1), m.group(2), m.group(3)
    else:
        out["单位"] = out["年份"] = out["学位"] = ""
    return out


def main() -> None:
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    lines = []
    for code, url, reuse, expect in TARGETS:
        html_path = os.path.join(EVID, f"{code}.html")
        txt_path = os.path.join(EVID, f"{code}.txt")
        try:
            if reuse:
                shutil.copyfile(reuse, html_path)
                html = io.open(html_path, encoding="utf-8", errors="ignore").read()
                src_url = "(复用：" + os.path.basename(reuse) + ")"
                fields = parse_page(html, src_url)
                fields["http_status"] = "reuse"
                fields["bytes"] = str(os.path.getsize(html_path))
                print(f"[{code}] reuse {os.path.basename(reuse)}")
            else:
                r = s.get(url, timeout=45)
                r.encoding = "utf-8"
                with io.open(html_path, "w", encoding="utf-8") as fh:
                    fh.write(r.text)
                fields = parse_page(r.text, url)
                fields["http_status"] = str(r.status_code)
                fields["bytes"] = str(len(r.content))
                print(f"[{code}] {r.status_code} {len(r.content)}B | {fields.get('h1','')[:40]}")
                time.sleep(2.6)
            fields["对照表题名"] = expect
            with io.open(txt_path, "w", encoding="utf-8") as fh:
                for k, v in fields.items():
                    fh.write(f"{k}\t{v}\n")
            lines.append(f"{code}\t{fields.get('h1','')}\t{fields.get('authors','')}\t{fields.get('source_from_tag','')}\t{fields.get('期刊','')} {fields.get('年','')}-{fields.get('期','')}\t{fields.get('单位','')} {fields.get('年份','')} {fields.get('学位','')}\t{fields.get('http_status')}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{code}\tERROR={exc}")
            print(f"[{code}] ERROR {exc}")
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("done")


if __name__ == "__main__":
    main()
