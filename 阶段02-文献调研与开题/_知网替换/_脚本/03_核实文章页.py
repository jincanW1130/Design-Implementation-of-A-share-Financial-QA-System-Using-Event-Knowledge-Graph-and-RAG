# -*- coding: utf-8 -*-
"""本轮核实：逐条抓取对照表 20 条替换候选的知网公开文章页，留证并抽取字段。

纪律：
- 不登录、不使用任何账号或密码、不提交任何凭据；
- 只访问 cnki.com.cn / cdmd.cnki.com.cn 公开文章页，不访问 kns.cnki.net，
  不请求、不点击任何全文下载链接（只登记 href，不跳转）；
- 每个网络请求间隔 >= 2.5 秒。

产出：
- 证据/<原编号>.html   原始文章页 HTML
- 证据/<原编号>.txt    抽出的字段文本（键\t值）
- _脚本/_请求清单_本轮.txt  逐条请求登记
"""
from __future__ import annotations

import io
import os
import re
import shutil
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
REQ_LOG = os.path.join(SCRIPT_DIR, "_请求清单_本轮.txt")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# (原编号, 对照表所写题名, 文章页 URL)
TARGETS: list[tuple[str, str, str]] = [
    ("KG-5", "基于注意力机制的知识图谱推理方法研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-10749-1026398565.htm"),
    ("KG-9", "基于多维指令集微调的大语言模型金融事件抽取",
     "https://www.cnki.com.cn/Article/CJFDTotal-KXTS202608009.htm"),
    ("KG-16", "基于跨度和网络结构的篇章级事件抽取研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-10361-1026321974.htm"),
    ("KG-17", "基于自适应GNN的篇章级金融事件抽取系统研究与实现",
     "https://cdmd.cnki.com.cn/Article/CDMD-10140-1026248350.htm"),
    ("KG-19", "外部知识增强的事件共指消解方法",
     "https://www.cnki.com.cn/Article/CJFDTotal-RJXB202511014.htm"),
    ("KG-29", "面向开源情报的实体链接技术研究综述",
     "https://www.cnki.com.cn/Article/CJFDTotal-QBGC202503007.htm"),
    ("RAG-1", "检索增强生成综述：方法与应用",
     "https://www.cnki.com.cn/Article/CJFDTotal-JSJA202607012.htm"),
    ("RAG-9", "融合双驱动检索与结构安全增强的GraphRAG多跳推理方法研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-10431-1026344672.htm"),
    ("RAG-10", "基于图神经网络推理的知识图谱多跳问答方法研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-11660-1026346236.htm"),
    ("RAG-11", "基于文本图结构化的层次化检索增强生成方法",
     "https://www.cnki.com.cn/Article/CJFDTotal-SJSJ202608032.htm"),
    ("RAG-13", "基于检索增强的大语言模型问答方法研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-10358-1026362151.htm"),
    ("RAG-24", "AIGC嵌入图书馆知识发现服务的幻觉识别与信任度测量",
     "https://www.cnki.com.cn/Article/CJFDTotal-QBTS202609016.htm"),
    ("FIN-3", "基于检索增强生成的金融智能问答方法研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-10749-1026398545.htm"),
    ("FIN-16", "基于多粒度隐含时态感知的时序知识图谱问答研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-11660-1026346229.htm"),
    ("FIN-17", "SARIMA嵌入的时序知识图谱推理",
     "https://www.cnki.com.cn/Article/CJFDTotal-DZJY202606022.htm"),
    ("FIN-20", "一种基于扩散模型和知识图谱的智能金融问答系统的关键技术研究",
     "https://cdmd.cnki.com.cn/Article/CDMD-10013-1025075409.htm"),
    ("SYS-4", "水利知识图谱与大模型双向赋能技术探索",
     "https://www.cnki.com.cn/Article/CJFDTotal-FHKH202609011.htm"),
    ("SYS-8", "基于Hybrid RAG的LLM水产营养推荐架构",
     "https://www.cnki.com.cn/Article/CJFDTotal-SSDB202604002.htm"),
    ("SYS-13", "融合检索增强生成技术的国产轻量化大语言模型在专科问题解答中的效能评估",
     "https://www.cnki.com.cn/Article/CJFDTotal-ZXYX202609007.htm"),
    ("SYS-14", "基于知识图谱路径推理和大模型的电力智能检索引擎",
     "https://www.cnki.com.cn/Article/CJFDTotal-DWJS202608019.htm"),
]


def log_line(method: str, note: str, url: str, info: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with io.open(REQ_LOG, "a", encoding="utf-8") as fh:
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

    authors: list[str] = []
    for a in soup.select('a[href*="author"]'):
        name = squeeze(a.get_text())
        if name and 1 < len(name) <= 12 and name not in authors:
            if "免费下载" in name:
                continue
            authors.append(name)
    out["authors"] = "、".join(authors[:20])

    text = squeeze(soup.get_text(" ", strip=True))
    out["text_len"] = str(len(text))

    m = re.search(r"【摘要】\s*[:：]?\s*(.{0,1200}?)(?:【关键词】|【学位授予单位】|【引证文献】|下载App)", text)
    out["abstract"] = m.group(1)[:1200] if m else ""
    m = re.search(r"【关键词】\s*[:：]?\s*(.{0,300}?)(?:【|下载|更多同类)", text)
    if not m:
        m = re.search(r"关键词[：:]\s*(.{0,300}?)(?:【|下载|更多同类)", text)
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

    # 导师字段：页面是否提供（cdmd 公开页通常不提供）
    out["导师字段出现次数"] = str(len(re.findall(r"导师", text)))
    mm = re.search(r"【导师】\s*[:：]?\s*(.{0,60}?)(?:【|$)", text)
    out["导师"] = squeeze(mm.group(1)) if mm else ""

    # 下载入口：只登记 href，不访问
    links = []
    for a in soup.select("a"):
        t = squeeze(a.get_text())
        if "下载" in t and a.get("href"):
            links.append(f"{t}->{a['href']}")
    out["下载入口"] = " | ".join(links[:6])

    # 期刊页年份/期号
    m = re.search(r"《([^》]+)》\s*(\d{4})年(\d{1,2}|S\d{1,2}|\d{1,2}/\d{1,2})期", out.get("source_from_tag", ""))
    if m:
        out["期刊"] = m.group(1)
        out["年"] = m.group(2)
        out["期"] = m.group(3)
    else:
        out["期刊"] = ""
        out["年"] = ""
        out["期"] = ""
    m = re.search(r"《([^》]+)》\s*(\d{4})年(硕士|博士)论文", out.get("source_from_tag", ""))
    if m:
        out["单位"] = m.group(1)
        out["年份"] = m.group(2)
        out["学位"] = m.group(3)
    else:
        out["单位"] = ""
        out["年份"] = ""
        out["学位"] = ""
    return out


def reuse_existing(code: str, url: str) -> bool:
    """若历史证据 <编号>_1.html 内容对应当前目标 URL，则复制为 <编号>.html。"""
    for idx in (1, 2):
        src = os.path.join(EVID_DIR, f"{code}_{idx}.html")
        if not os.path.exists(src) or os.path.getsize(src) < 5000:
            continue
        with io.open(src, encoding="utf-8", errors="ignore") as fh:
            head = fh.read(4000)
        token = url.rstrip("/").rsplit("/", 1)[-1]
        if token.replace(".htm", "") in head:
            shutil.copyfile(src, os.path.join(EVID_DIR, f"{code}.html"))
            log_line("REUSE", "EXISTING", url, os.path.basename(src))
            return True
    return False


def main() -> None:
    os.makedirs(EVID_DIR, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    log_line("-", "RUN_START", "03_核实文章页.py")
    ok = 0
    for code, title, url in TARGETS:
        html_path = os.path.join(EVID_DIR, f"{code}.html")
        txt_path = os.path.join(EVID_DIR, f"{code}.txt")
        if os.path.exists(html_path) and os.path.getsize(html_path) > 5000:
            print(f"[skip] {code} exists")
            ok += 1
            continue
        if reuse_existing(code, url):
            html = io.open(html_path, encoding="utf-8", errors="ignore").read()
            fields = parse_page(html, url)
            fields["http_status"] = "reuse"
            fields["bytes"] = str(os.path.getsize(html_path))
            fields["对照表题名"] = title
            with io.open(txt_path, "w", encoding="utf-8") as fh:
                for k, v in fields.items():
                    fh.write(f"{k}\t{v}\n")
            print(f"[{code}] reuse | {fields.get('h1','')[:40]}")
            ok += 1
            continue
        try:
            r = session.get(url, timeout=45)
            r.encoding = "utf-8"
            with io.open(html_path, "w", encoding="utf-8") as fh:
                fh.write(r.text)
            fields = parse_page(r.text, url)
            fields["http_status"] = str(r.status_code)
            fields["bytes"] = str(len(r.content))
            fields["对照表题名"] = title
            with io.open(txt_path, "w", encoding="utf-8") as fh:
                for k, v in fields.items():
                    fh.write(f"{k}\t{v}\n")
            log_line("GET", "FETCH", url, f"status={r.status_code} bytes={len(r.content)}")
            print(f"[{code}] {r.status_code} {len(r.content)}B | {fields.get('h1','')[:40]} | {fields.get('source_from_tag','')[:30]}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            log_line("GET", "ERROR", url, str(exc)[:200])
            print(f"[{code}] ERROR {exc}")
        time.sleep(2.6)
    log_line("-", "RUN_END", f"ok={ok}/{len(TARGETS)}")
    print(f"done {ok}/{len(TARGETS)}")


if __name__ == "__main__":
    main()
