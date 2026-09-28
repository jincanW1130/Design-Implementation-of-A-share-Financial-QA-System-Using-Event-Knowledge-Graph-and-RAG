# -*- coding: utf-8 -*-
"""检索变体探测：测试知网公开检索（search.cnki.com.cn）的 searchType 与分页，
用于核实裁定点名的池内候选（SYS-16、SYS-18、RAG-15、SYS-2）题录。
纪律同前：不登录、不下载；请求间隔 >= 2.6 秒。
产出：证据/_检索页/变体_<标签>.html 与 _替换执行/_检索变体.txt
"""
from __future__ import annotations

import io
import os
import sys
import time

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVID = os.path.join(BASE, "_知网替换", "证据", "_检索页")
OUT = os.path.join(BASE, "_替换执行", "_检索变体.txt")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

# (标签, searchType, Content, Page)
TRIES = [
    ("SYS16_t1", "Title", "基于大语言模型的知识图谱构建及应用研究", "1"),
    ("SYS16_p2", "MulityTermsSearch", "基于大语言模型的知识图谱构建及应用研究", "2"),
    ("SYS18_t1", "Title", "融合知识图谱和大模型的高校科研管理问答系统设计", "1"),
    ("SYS18_p2", "MulityTermsSearch", "融合知识图谱和大模型的高校科研管理问答系统设计", "2"),
    ("RAG15_t1", "Title", "面向大语言模型生成能力提升的检索增强生成研究进展", "1"),
    ("RAG15_kw", "Keyword", "检索增强生成 研究进展 软件学报", "1"),
    ("SYS2_t1", "Title", "基于Langchain-LLMs框架的智能问答系统的设计与实现", "1"),
    ("SYS2_kw", "Keyword", "Langchain LLMs 智能问答系统 延边大学", "1"),
]


def main() -> None:
    os.makedirs(EVID, exist_ok=True)
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": "https://search.cnki.com.cn/search/index",
    })
    lines = []
    for tag, stype, content, page in TRIES:
        body = {
            "searchType": stype, "ArticleType": "0",
            "ParamIsNullOrEmpty": "false", "Islegal": "false",
            "Content": content, "Order": "1", "Page": page,
        }
        url = "https://search.cnki.com.cn/search/listresult"
        try:
            r = s.post(url, data=body, timeout=45)
            r.encoding = "utf-8"
            with io.open(os.path.join(EVID, f"变体_{tag}.html"), "w", encoding="utf-8") as fh:
                fh.write(r.text)
            n = r.text.count('class="list-item"')
            hit = ""
            for probe in ("基于大语言模型的知识图谱构建及应用研究",
                          "融合知识图谱和大模型的高校科研管理问答系统设计",
                          "面向大语言模型生成能力提升的检索增强生成研究进展",
                          "基于Langchain-LLMs框架的智能问答系统的设计与实现"):
                if probe in r.text:
                    hit += probe + ";"
            lines.append(f"{tag}\t{stype}\tpage={page}\tstatus={r.status_code}\tbytes={len(r.content)}\titems={n}\thit={hit}")
            print(f"[{tag}] {stype} p{page} {r.status_code} {len(r.content)}B items={n} hit={hit}")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"{tag}\t{stype}\tERROR={exc}")
            print(f"[{tag}] ERROR {exc}")
        time.sleep(2.6)
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("done")


if __name__ == "__main__":
    main()
