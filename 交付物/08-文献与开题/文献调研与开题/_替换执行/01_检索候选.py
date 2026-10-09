# -*- coding: utf-8 -*-
"""第 2 阶段「混合方案」执行：补齐/核实候选所需的公开检索（只做核实，不做综述检索）。

授权范围（作者裁定）：
- 只检索两类内容：①SYS-13 需要的中文「评测/基准类」候选；②裁定点名要求核实的池内候选
  （KG-7、RAG-15、SYS-2、SYS-16、SYS-18）的题录。
- 不登录、不使用任何账号或密码、不提交任何凭据、不点击任何下载链接、不访问 kns.cnki.net。
- 每个网络请求间隔 >= 2.5 秒。

产出：
- 证据/_检索页/<标签>.html          检索结果原始 HTML（新增核实证据）
- _替换执行/_检索结果_本轮.json      结构化结果（标题/作者/来源/链接）
- _替换执行/_请求日志.txt            逐条请求登记
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THIS_DIR = os.path.join(BASE, "_替换执行")
EVID_DIR = os.path.join(BASE, "_知网替换", "证据", "_检索页")
LOG = os.path.join(THIS_DIR, "_请求日志.txt")
JSON_OUT = os.path.join(THIS_DIR, "_检索结果_本轮.json")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# (标签, 检索式, 说明)
QUERIES: list[tuple[str, str, str]] = [
    ("KG-7", "知识关联视角下金融证券知识图谱构建与相关股票发现", "裁定点名的池内更优候选 KG-7 题录核实"),
    ("RAG-15", "面向大语言模型生成能力提升的检索增强生成研究进展", "裁定点名的池内更优候选 RAG-15 题录核实"),
    ("SYS-2", "基于Langchain-LLMs框架的智能问答系统的设计与实现", "裁定点名的池内更优候选 SYS-2 题录核实"),
    ("SYS-16", "基于大语言模型的知识图谱构建及应用研究", "裁定点名的池内更优候选 SYS-16 题录核实"),
    ("SYS-18", "融合知识图谱和大模型的高校科研管理问答系统设计", "裁定点名的池内更优候选 SYS-18 题录核实"),
    ("SYS-13新", "检索增强生成 系统 评测", "SYS-13 端点：中文评测/基准类候选"),
    ("SYS-13新b", "检索增强生成 评测框架", "SYS-13 端点：中文评测/基准类候选（第二式）"),
    ("SYS-13新c", "大语言模型 问答系统 性能评测", "SYS-13 端点：中文评测/基准类候选（第三式）"),
    ("RAG-15b", '"面向大语言模型生成能力提升的检索增强生成研究进展"', "RAG-15 精确题名复核（第二式）"),
    ("SYS-2b", "Langchain LLMs 框架 智能问答系统 设计与实现", "SYS-2 题录复核（第二式）"),
    ("SYS-16b", '"基于大语言模型的知识图谱构建及应用研究"', "SYS-16 精确题名复核（第二式）"),
    ("SYS-18b", '"融合知识图谱和大模型的高校科研管理问答系统设计"', "SYS-18 精确题名复核（第二式）"),
    ("SYS-13新d", "检索增强生成 基准 评测", "SYS-13 端点：中文评测/基准类候选（第四式）"),
    ("SYS-13新e", "检索增强生成 评价 综述", "SYS-13 端点：中文评测/基准类候选（第五式）"),
    ("SYS-13新f", "面向检索增强生成系统的流程优化方法研究", "SYS-13 端点：RAG 系统流程优化类候选复核"),
    ("RAG-15c", "刘澳迪 奚雪峰 周国栋", "RAG-15 题录复核（第三式：按作者）"),
    ("RAG-15d", "软件学报 检索增强生成 研究进展", "RAG-15 题录复核（第四式）"),
    ("SYS-2c", "基于Langchain的智能问答系统的设计与实现", "SYS-2 题录复核（第三式）"),
    ("SYS-16c", "张才科 基于大语言模型的知识图谱构建", "SYS-16 题录复核（第三式：按作者）"),
    ("SYS-18c", "王永 秦嘉俊 融合知识图谱和大模型 科研管理", "SYS-18 题录复核（第三式：按作者）"),
    ("SYS-13新g", "检索增强生成系统 组件 性能 优化", "SYS-13 端点：中文评测/基准类候选（第六式）"),
]


def log(method: str, note: str, url: str, info: str = "") -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{ts}\t{method}\t{note}\t{url}\t{info}\n")


def squeeze(t: str) -> str:
    return re.sub(r"\s+", " ", t or "").strip()


def parse_items(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    for li in soup.select("div.list-item"):
        a = li.select_one("p.tit a.left") or li.select_one("a.left")
        if not a:
            continue
        title = squeeze(a.get("title") or a.get_text())
        href = a.get("href") or ""
        if not href:
            continue
        src = li.select_one("p.source")
        authors = []
        if src:
            for x in src.select('a[href*="author="]'):
                t = squeeze(x.get_text())
                if t:
                    authors.append(t)
        journal = ""
        issue = ""
        if src:
            spans = [squeeze(x.get_text()) for x in src.select("a span")]
            if spans:
                journal = spans[0]
            if len(spans) > 1:
                issue = spans[1]
        fn = li.select_one("div.checkbox1")
        nr = li.select_one("p.nr")
        out.append({
            "title": title,
            "href": href,
            "authors": authors,
            "journal": journal,
            "issue": issue,
            "fn": squeeze(fn.get("data-fn") or "") if fn else "",
            "abstract": squeeze(nr.get_text())[:400] if nr else "",
            "li_text": squeeze(li.get_text())[:400],
        })
    return out


def reparse_only() -> None:
    """只重解析已落盘的检索页 HTML，不发起任何网络请求。"""
    if os.path.exists(JSON_OUT):
        with io.open(JSON_OUT, encoding="utf-8") as fh:
            results = json.load(fh)
    else:
        results = {}
    for tag, q, _why in QUERIES:
        html_path = os.path.join(EVID_DIR, f"{tag}.html")
        if not os.path.exists(html_path):
            continue
        with io.open(html_path, encoding="utf-8", errors="ignore") as fh:
            html = fh.read()
        items = parse_items(html)
        for it in items:
            it["href"] = urljoin("https://search.cnki.com.cn/", it["href"])
        results[tag] = items
        print(f"[{tag}] items={len(items)}")
        for it in items[:8]:
            print("    -", it["title"], "|", "、".join(it["authors"]), "|", it["journal"], it["issue"], "|", it["href"])
    with io.open(JSON_OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    print("reparse done")


def main() -> None:
    if "--reparse" in sys.argv:
        reparse_only()
        return
    os.makedirs(EVID_DIR, exist_ok=True)
    os.makedirs(THIS_DIR, exist_ok=True)
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://search.cnki.com.cn/search/index",
    })
    results: dict[str, list[dict]] = {}
    if os.path.exists(JSON_OUT):
        with io.open(JSON_OUT, encoding="utf-8") as fh:
            results = json.load(fh)
    log("-", "RUN_START", "01_检索候选.py")
    for tag, q, why in QUERIES:
        body = {
            "searchType": "MulityTermsSearch", "ArticleType": "0",
            "ParamIsNullOrEmpty": "false", "Islegal": "false",
            "Content": q, "Order": "1", "Page": "1",
        }
        url = "https://search.cnki.com.cn/search/listresult"
        try:
            r = session.post(url, data=body, timeout=45)
            r.encoding = "utf-8"
            html_path = os.path.join(EVID_DIR, f"{tag}.html")
            with io.open(html_path, "w", encoding="utf-8") as fh:
                fh.write(r.text)
            items = parse_items(r.text)
            for it in items:
                it["href"] = urljoin("https://search.cnki.com.cn/", it["href"])
            results[tag] = items
            log("POST", why, url, f"content={q} status={r.status_code} bytes={len(r.content)} items={len(items)}")
            print(f"[{tag}] {r.status_code} {len(r.content)}B items={len(items)} q={q}")
            for it in items[:5]:
                print("    -", it["title"], "|", "、".join(it["authors"]), "|", it["journal"], it["issue"], "|", it["href"])
        except Exception as exc:  # noqa: BLE001
            log("POST", why, url, f"content={q} ERROR={exc}")
            print(f"[{tag}] ERROR {exc}")
        time.sleep(2.6)
    with io.open(JSON_OUT, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    log("-", "RUN_END", f"{len(QUERIES)} queries")
    print("done")


if __name__ == "__main__":
    main()
