# -*- coding: utf-8 -*-
"""为20个英文文献主题在知网搜索最相关的中文替换文献。

KG-21、KG-28已是中文文献且在知网命中，不在此搜索范围内。
"""
from __future__ import annotations

import json
import os
import re
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

try:
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SEARCH_POST = "https://search.cnki.com.cn/search/listresult"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

# 20个需要替换的主题：编号 -> (中文检索关键词, 原文献落点摘要)
# 用短而精准的核心术语，避免多关键词OR匹配发散
TOPICS = [
    ("KG-5",  "金融知识图谱构建",              "事件增强金融KG自动构建；两阶段图检索；关系粒度"),
    ("KG-9",  "金融事件抽取",                  "中文金融文档级事件抽取；跨句论元；多事件共存"),
    ("KG-16", "篇章级事件抽取",                "文档级事件抽取标注体系；事件类型-论元双层粒度"),
    ("KG-17", "篇章级事件抽取 中文",            "中文文档级事件抽取；论元标注一致性；schema"),
    ("KG-19", "事件共指消解",                  "事件共指链；时序/因果/子事件关系；事件去重"),
    ("KG-29", "命名实体链接",                  "金融公司名实体链接；企业专有实体消歧"),
    ("RAG-1",  "检索增强生成",                  "RAG基本框架；向量检索+生成；baseline来源"),
    ("RAG-9",  "GraphRAG",                     "图谱增强RAG；全局摘要；社区检测"),
    ("RAG-10", "知识图谱 多跳问答",            "图遍历多跳检索；路径扩展；个性化PageRank"),
    ("RAG-11", "RAG 评测",                     "RAG自动评估；检索/生成指标分离；忠实度"),
    ("RAG-13", "多跳问答",                      "多跳问答；支撑事实标注；跳数标签"),
    ("RAG-24", "大语言模型 幻觉",              "事实性精度；原子事实；长文本生成幻觉"),
    ("FIN-3",  "金融问答系统",                  "金融问答基准；证据链；公告文件问答"),
    ("FIN-16", "时序知识图谱",                  "时序KGQA；时间区间建模；时间约束"),
    ("FIN-17", "时序知识图谱 问答",            "时序问题分解；时间约束子图检索"),
    ("FIN-20", "金融大模型 幻觉",              "金融KG-QA忠实度；文本+图谱双证据；幻觉检测"),
    ("SYS-4",  "大语言模型 系统架构",          "LLM应用分层架构；前后端分离；职责解耦"),
    ("SYS-8",  "混合检索 知识图谱",            "向量+图谱双路检索；金融场景；混合RAG"),
    ("SYS-13", "RAG 性能",                     "RAG端到端性能测试；组件级变量控制"),
    ("SYS-14", "向量检索 知识图谱 融合",       "多存储协同；关系库+图谱+向量；证据追溯"),
]


def search_cnmi(keyword: str, page: int = 1, timeout: int = 40) -> dict:
    """POST到知网搜索API，返回解析后的结果列表。"""
    data = {
        "searchType": "MulityTermsSearch",
        "ArticleType": "0",
        "ParamIsNullOrEmpty": "false",
        "Islegal": "false",
        "Content": keyword,
        "Order": "1",  # 按相关度
        "Page": str(page),
    }
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://search.cnki.com.cn/Search/Result",
    }
    r = requests.post(SEARCH_POST, data=data, headers=headers, timeout=timeout)
    r.raise_for_status()
    html = r.text
    return parse_results(html)


def parse_results(html: str) -> dict:
    """解析知网搜索结果HTML。"""
    soup = BeautifulSoup(html, "html.parser")
    items = []

    # 总数
    total = ""
    # 知网空间结果页通常有 totalcount
    m = re.search(r'共找到[约]?\s*(\d+)\s*条', html)
    if m:
        total = m.group(1)

    for li in soup.select(".list-item"):
        # 标题
        a = li.select_one("p.tit a.left")
        if not a:
            continue
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True))
        title = title.replace("CNKI文献", "").strip()
        href = a.get("href", "")
        if href.startswith("//"):
            href = "https:" + href

        # 摘要
        nr = li.select_one("p.nr")
        abstract = re.sub(r"\s+", " ", nr.get_text(" ", strip=True)) if nr else ""

        # 来源（作者+期刊+年份）
        source_p = li.select_one("p.source")
        authors = []
        source_text = ""
        year = ""
        if source_p:
            for author_a in source_p.select('a[href*="author="]'):
                name = author_a.get_text(" ", strip=True)
                if name:
                    authors.append(name)
            # 出处链接后面的文本
            source_span = source_p.select_one("a[href*='cjfd/Detail']")
            if source_span:
                source_text = re.sub(r"\s+", " ", source_span.get_text(" ", strip=True))
            else:
                # 尝试其他方式获取出处
                all_text = re.sub(r"\s+", " ", source_p.get_text(" ", strip=True))
                source_text = all_text

        # 被引/下载
        dl_cite = li.select_one("p.dl")
        dl_text = re.sub(r"\s+", " ", dl_cite.get_text(" ", strip=True)) if dl_cite else ""

        # 从source_text提取年份
        ym = re.search(r"(20\d{2})", source_text)
        if ym:
            year = ym.group(1)

        items.append({
            "title": title,
            "href": href,
            "authors": authors,
            "source": source_text,
            "year": year,
            "abstract": abstract[:300],
            "dl_cite": dl_text,
        })

    return {"total": total, "items": items}


def main():
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "知网替换文献搜索结果_v2.json")
    all_results = {}

    for i, (topic_id, keyword, desc) in enumerate(TOPICS):
        print(f"[{i+1}/{len(TOPICS)}] {topic_id}: {keyword}")
        try:
            result = search_cnmi(keyword)
            all_results[topic_id] = {
                "keyword": keyword,
                "desc": desc,
                "total": result["total"],
                "items": result["items"][:10],  # 取前10条
            }
            print(f"  -> {result['total']}条结果, 取前{len(result['items'][:10])}条")
            for j, it in enumerate(result["items"][:5]):
                print(f"     {j+1}. [{it['year']}] {it['title'][:50]} | {it['source'][:40]}")
        except Exception as e:
            print(f"  -> 错误: {e}")
            all_results[topic_id] = {"keyword": keyword, "desc": desc, "error": str(e), "items": []}
        time.sleep(2.5)  # 每条间隔

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
