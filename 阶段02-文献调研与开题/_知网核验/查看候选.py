# -*- coding: utf-8 -*-
import json, sys
sys.stdout.reconfigure(encoding="utf-8")
with open(r'阶段02-文献调研与开题\_知网核验\知网替换文献搜索结果_v2.json','r',encoding='utf-8') as f:
    data = json.load(f)
targets = ['KG-5','KG-9','KG-16','KG-17','KG-19','KG-29','RAG-1','RAG-9','RAG-10','RAG-13','RAG-24','FIN-3','FIN-16','FIN-20','SYS-4','SYS-8','SYS-13','SYS-14']
for tid in targets:
    if tid in data:
        items = data[tid].get('items',[])
        kw = data[tid].get('keyword','')
        print(f'\n=== {tid} (kw: {kw}) ===')
        for i,it in enumerate(items[:3]):
            yr = it.get('year','')
            print(f'  {i+1}. [{yr}] {it["title"][:60]}')
            print(f'     authors={it.get("authors",[])}')
            print(f'     source={it.get("source","")[:80]}')
            print(f'     href={it.get("href","")}')
