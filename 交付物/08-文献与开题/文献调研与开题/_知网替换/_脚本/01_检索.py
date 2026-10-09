# -*- coding: utf-8 -*-
"""知网空间检索：用 Playwright 无头浏览器打开检索结果页，并在页内发起同名检索请求，
读取渲染后的结果条目。

纪律：
- 不登录、不使用任何账号或密码、不提交任何凭据；
- 不点击任何下载链接、不访问 kns.cnki.net；
- 每条检索之间间隔 >= 2 秒；
- 统计与推广类第三方子资源在浏览器层拦截，并如实登记为 BLOCKED。

产出：
- _脚本/_检索结果.json                 逐条检索的结构化结果
- _脚本/_请求清单.txt                  全部请求（含被拦截项）逐行登记
- 证据/_检索页/<原编号>_<序号>.html    检索结果原始 HTML
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from urllib.parse import quote, urlparse

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(BASE, "_脚本")
EVID_DIR = os.path.join(BASE, "证据", "_检索页")
RESULT_JSON = os.path.join(SCRIPT_DIR, "_检索结果.json")
REQ_LOG = os.path.join(SCRIPT_DIR, "_请求清单.txt")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

# 拦截名单：与检索无关的统计、推广与推荐类第三方子资源
BLOCK_HOSTS = {
    "c.cnzz.com",
    "icon.cnzz.com",
    "s4.cnzz.com",
    "z11.cnzz.com",
    "mall.cnki.net",
    "search.cnki.net",
    "hm.baidu.com",
}

TOPICS: list[tuple[str, list[str]]] = [
    ("KG-5", ["金融知识图谱 构建", "事件知识图谱 构建"]),
    ("KG-9", ["金融事件抽取", "金融文本 事件抽取 模型"]),
    ("KG-16", ["篇章级事件抽取", "文档级事件抽取 论元"]),
    ("KG-17", ["中文 篇章级事件抽取", "中文事件抽取 数据集"]),
    ("KG-19", ["事件共指消解", "事件关系抽取 因果关系 时序关系"]),
    ("KG-21", ["金融突发事件 事理知识图谱"]),
    ("KG-28", ["实体消歧 综述"]),
    ("KG-29", ["实体链接 综述", "金融领域 实体链接"]),
    ("RAG-1", ["检索增强生成 综述", "检索增强生成 大语言模型 应用"]),
    ("RAG-9", ["图检索增强生成", "知识图谱 增强 检索增强生成"]),
    ("RAG-10", ["知识图谱 多跳问答", "知识图谱 多跳推理 检索"]),
    ("RAG-11", ["检索增强生成 评估", "检索增强生成 评价指标"]),
    ("RAG-13", ["多跳问答 数据集", "多跳问答 综述"]),
    ("RAG-24", ["大语言模型 幻觉 综述", "大模型 事实性 评估"]),
    ("FIN-3", ["金融 问答 大语言模型", "金融 检索增强 问答 系统"]),
    ("FIN-16", ["时序知识图谱 问答", "时序知识图谱 综述"]),
    ("FIN-17", ["时序知识图谱 时间 推理", "时间感知 知识图谱 问答"]),
    ("FIN-20", ["金融 大语言模型 幻觉", "知识图谱 问答 幻觉 评测"]),
    ("SYS-4", ["大语言模型 应用系统 架构", "大模型 软件 分层 架构"]),
    ("SYS-8", ["知识图谱 向量 混合检索", "混合检索 增强生成 知识图谱"]),
    ("SYS-13", ["检索增强生成 系统 性能", "大模型 应用 评测基准"]),
    ("SYS-14", ["异构数据 存储 检索 大模型", "向量 知识图谱 融合 检索系统"]),
]

# 第二轮补充检索：第一轮结果发散或同构度不足的主题
SUPPLEMENT: list[tuple[str, list[str]]] = [
    ("RAG-11", ["RAG 评估框架", "检索增强生成 忠实度 指标"]),
    ("RAG-24", ["大语言模型 幻觉 评测"]),
    ("SYS-13", ["检索增强生成 系统 评测"]),
    ("SYS-4", ["智能问答系统 设计与实现 架构"]),
    ("FIN-3", ["金融 问答 数据集"]),
    ("KG-16", ["事件论元 标注"]),
    ("KG-29", ["开源情报 实体链接"]),
]

# 第三轮补充检索：仍缺同构候选的主题
ROUND3: list[tuple[str, list[str]]] = [
    ("RAG-11", ["检索增强生成 评测基准"]),
    ("RAG-9", ["GraphRAG 综述"]),
    ("FIN-20", ["金融大模型 评测"]),
    ("SYS-4", ["大模型应用 分层设计"]),
    ("RAG-13", ["多跳问答 证据"]),
    ("KG-29", ["实体链接技术研究综述"]),
]

PARSE_JS = r"""
async (kw) => {
  const body = new URLSearchParams({
    searchType: 'MulityTermsSearch', ArticleType: '0',
    ParamIsNullOrEmpty: 'false', Islegal: 'false',
    Content: kw, Order: '1', Page: '1'
  });
  const r = await fetch('/search/listresult', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
              'X-Requested-With': 'XMLHttpRequest'},
    body
  });
  const html = await r.text();
  const doc = new DOMParser().parseFromString(html, 'text/html');
  const items = [];
  doc.querySelectorAll('.list-item').forEach((li, idx) => {
    const a = li.querySelector('p.tit a.left');
    const nr = li.querySelector('p.nr');
    const src = li.querySelector('p.source');
    const authors = [];
    if (src) src.querySelectorAll('a[href*="author="]').forEach(x => {
      const t = (x.textContent || '').trim();
      if (t) authors.push(t);
    });
    let journal = '', issue = '', type = '';
    if (src) {
      const spans = src.querySelectorAll('a span');
      if (spans.length > 0) journal = (spans[0].textContent || '').trim();
      if (spans.length > 1) issue = (spans[1].textContent || '').trim();
      const tail = (src.textContent || '').trim().split(/\s+/);
      type = tail[tail.length - 1] || '';
    }
    const kwEl = li.querySelector('p.info_left');
    const dlEl = li.querySelector('p.info_right');
    const fn = li.querySelector('div.checkbox1');
    items.push({
      n: idx + 1,
      title: a ? (a.getAttribute('title') || a.textContent.trim()) : '',
      href: a ? (a.getAttribute('href') || '') : '',
      authors, journal, issue, type,
      keywords: kwEl ? (kwEl.textContent || '').replace(/\s+/g, ' ').trim() : '',
      dl_cite: dlEl ? (dlEl.textContent || '').replace(/\s+/g, ' ').trim() : '',
      abstract: nr ? (nr.textContent || '').replace(/\s+/g, ' ').trim() : '',
      fn: fn ? (fn.getAttribute('data-fn') || '') : ''
    });
  });
  return {status: r.status, len: html.length, html, items};
}
"""


def log_line(method: str, rtype: str, note: str, url: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(REQ_LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{ts}\t{method}\t{rtype}\t{note}\t{url}\n")


def main() -> None:
    os.makedirs(EVID_DIR, exist_ok=True)
    results: dict[str, list[dict]] = {}
    if os.path.exists(RESULT_JSON):
        with open(RESULT_JSON, encoding="utf-8") as fh:
            results = json.load(fh)

    log_line("-", "-", "RUN_START", "01_检索.py")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(user_agent=UA)
        page = ctx.new_page()

        def on_route(route, request):  # noqa: ANN001
            host = urlparse(request.url).netloc
            if host in BLOCK_HOSTS:
                log_line(request.method, request.resource_type, "BLOCKED", request.url)
                route.abort()
            else:
                log_line(request.method, request.resource_type, "ALLOW", request.url)
                route.continue_()

        page.route("**/*", on_route)

        for code, queries in TOPICS + SUPPLEMENT + ROUND3:
            done = results.setdefault(code, [])
            done_queries = {q["query"] for q in done}
            for qi, kw in enumerate(queries, 1):
                if kw in done_queries:
                    print(f"[skip] {code} #{qi} {kw}")
                    continue
                url = "https://search.cnki.com.cn/Search/Result?content=" + quote(kw)
                print(f"[{code} #{qi}] {kw}")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2500)
                res = page.evaluate(PARSE_JS, kw)
                raw_html = res.pop("html")
                ev = os.path.join(EVID_DIR, f"{code}_{qi}.html")
                with open(ev, "w", encoding="utf-8") as fh:
                    fh.write(raw_html)
                rec = {"query": kw, "url": url, "evidence": os.path.basename(ev)}
                rec.update(res)
                done.append(rec)
                print(f"    -> status={res['status']} items={len(res['items'])}")
                with open(RESULT_JSON, "w", encoding="utf-8") as fh:
                    json.dump(results, fh, ensure_ascii=False, indent=1)
                time.sleep(2.5)

        browser.close()
    log_line("-", "-", "RUN_END", "01_检索.py")
    print("done ->", RESULT_JSON)


if __name__ == "__main__":
    main()
