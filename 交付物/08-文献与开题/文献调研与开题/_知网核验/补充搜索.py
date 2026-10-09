# -*- coding: utf-8 -*-
"""补充搜索：对第一轮结果不理想的主题用新关键词重新检索。"""
from __future__ import annotations
import json, os, re, time
import requests
from bs4 import BeautifulSoup

try:
    import sys; sys.stdout.reconfigure(encoding="utf-8")
except: pass

SEARCH_POST = "https://search.cnki.com.cn/search/listresult"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"

# 需要补充搜索的主题
TOPICS = [
    ("KG-17",  "事件论元抽取 标注",            "中文文档级事件抽取；论元标注；schema"),
    ("RAG-11", "检索增强生成 评价 方法",       "RAG自动评估；检索/生成指标；忠实度"),
    ("RAG-24", "大模型 事实性 生成质量",       "事实性精度；幻觉检测；长文本生成"),
    ("FIN-17", "时序知识图谱 问答 时间",       "时序KGQA；时间约束推理"),
    ("FIN-20", "金融大语言模型 问答",          "金融大模型问答；证据；忠实度"),
    ("SYS-4",  "大模型 应用 架构设计",         "LLM应用架构；分层；系统设计"),
    ("SYS-13", "检索增强生成 综述",            "RAG综述；方法分类；系统架构"),
    ("SYS-14", "混合检索 向量 知识图谱",       "向量+图谱混合检索；多存储"),
]

def search_cnki(keyword, page=1):
    data = {
        "searchType": "MulityTermsSearch", "ArticleType": "0",
        "ParamIsNullOrEmpty": "false", "Islegal": "false",
        "Content": keyword, "Order": "1", "Page": str(page),
    }
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://search.cnki.com.cn/Search/Result",
    }
    r = requests.post(SEARCH_POST, data=data, headers=headers, timeout=40)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    for li in soup.select(".list-item"):
        a = li.select_one("p.tit a.left")
        if not a: continue
        title = re.sub(r"\s+", " ", a.get_text(" ", strip=True)).replace("CNKI文献","").strip()
        href = a.get("href","")
        if href.startswith("//"): href = "https:"+href
        nr = li.select_one("p.nr")
        abstract = re.sub(r"\s+"," ", nr.get_text(" ",strip=True)) if nr else ""
        source_p = li.select_one("p.source")
        authors = [x.get_text(" ",strip=True) for x in source_p.select('a[href*="author="]') if x.get_text(strip=True)] if source_p else []
        source_text = ""
        if source_p:
            sa = source_p.select_one("a[href*='cjfd/Detail']")
            source_text = re.sub(r"\s+"," ", sa.get_text(" ",strip=True)) if sa else re.sub(r"\s+"," ",source_p.get_text(" ",strip=True))
        ym = re.search(r"(20\d{2})", source_text or "")
        items.append({"title":title,"href":href,"authors":authors,"source":source_text,"year":ym.group(1) if ym else "","abstract":abstract[:300]})
    return items

def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "知网补充搜索结果.json")
    all_res = {}
    for i,(tid,kw,desc) in enumerate(TOPICS):
        print(f"[{i+1}/{len(TOPICS)}] {tid}: {kw}")
        try:
            items = search_cnki(kw)
            all_res[tid] = {"keyword":kw,"desc":desc,"items":items[:10]}
            for j,it in enumerate(items[:5]):
                print(f"  {j+1}. [{it['year']}] {it['title'][:55]} | {it['source'][:40]}")
        except Exception as e:
            print(f"  ERROR: {e}")
            all_res[tid] = {"keyword":kw,"desc":desc,"error":str(e),"items":[]}
        time.sleep(2.5)
    with open(out_path,"w",encoding="utf-8") as f:
        json.dump(all_res,f,ensure_ascii=False,indent=2)
    print(f"\nSaved: {out_path}")

if __name__ == "__main__":
    main()
