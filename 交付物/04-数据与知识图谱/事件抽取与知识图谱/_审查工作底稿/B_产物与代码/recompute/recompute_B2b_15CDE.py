# -*- coding: utf-8 -*-
"""B2 补充：独立重算《16》第7.4节 表 15-C／15-D／15-E 的读数（不调用 sample_eval_set 的实现）。

只用 v2.1 的 documents.jsonl／chunks.jsonl ＋ config 里的正则与声明值。
"""
import io
import json
import os
import re
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
V21 = os.path.join(ROOT, '交付物/04-数据与知识图谱/数据准备', '数据集', 'v2.1')


def load_cfg(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def read_jsonl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def main():
    C = load_cfg('cfg6', os.path.join(ROOT, '交付物/03-代码', '抽取与图谱', 'config.py'))
    docs = read_jsonl(os.path.join(V21, 'clean', 'documents.jsonl'))
    chunks = read_jsonl(os.path.join(V21, 'chunks', 'chunks.jsonl'))
    dmap = {d['doc_id']: d for d in docs}

    print('#### 表 15-C')
    cl2 = sum(1 for d in docs if len(d.get('company_list') or []) >= 2)
    sc2 = sum(1 for d in docs if len(d.get('subject_companies') or []) >= 2)
    print('company_list >= 2     声明 %s  重算 %s  %s' %
          (C.TASK_BOOK_TABLES['table_15C']['company_list_ge2'], cl2,
           '一致' if C.TASK_BOOK_TABLES['table_15C']['company_list_ge2'] == cl2 else '不一致'))
    print('subject_companies >= 2 声明 %s  重算 %s  %s' %
          (C.TASK_BOOK_TABLES['table_15C']['subject_companies_ge2'], sc2,
           '一致' if C.TASK_BOOK_TABLES['table_15C']['subject_companies_ge2'] == sc2 else '不一致'))
    print('占比：company_list>=2 = %.1f%%、subject_companies>=2 = %.1f%%' %
          (100.0 * cl2 / len(docs), 100.0 * sc2 / len(docs)))

    print()
    print('#### 表 15-D（公告标题级 8 类事件 ＋ 正文级 3 条关系）')
    dec = C.TASK_BOOK_TABLES['table_15D']['公告标题级']
    for name, pat in C.EVENT_TYPE_TITLE_PATTERNS.items():
        rx = re.compile(pat)
        n = 0
        for d in docs:
            if d['category'] != '公告':
                continue
            t = d.get('title') or ''
            if rx.search(t) and not (name == '产品'
                                     and re.compile(C.PRODUCT_EXCLUDE_PATTERN).search(t)):
                n += 1
        print('  公告标题级 %-6s 声明 %-4s 重算 %-4s %s' %
              (name, dec.get(name), n, '一致' if dec.get(name) == n else '不一致'))
    allcat = {}
    for name, pat in C.EVENT_TYPE_TITLE_PATTERNS.items():
        rx = re.compile(pat)
        allcat[name] = sum(1 for d in docs if rx.search(d.get('title') or '')
                           and not (name == '产品'
                                    and re.compile(C.PRODUCT_EXCLUDE_PATTERN).search(d.get('title') or '')))
    print('  （全类目标题级，供《16》7.5 的「全类目命中篇」对照）=', json.dumps(allcat, ensure_ascii=False))
    decb = C.TASK_BOOK_TABLES['table_15D']['正文级']
    for name in ('SUPPLIES', 'CUSTOMER_OF', 'COMPETES_WITH'):
        pat = C.RELATION_BODY_PATTERNS.get(name)
        n = sum(1 for d in docs if pat and re.compile(pat).search(d.get('content') or ''))
        print('  正文级 %-14s 声明 %-4s 重算 %-4s %s' %
              (name, decb.get(name), n, '一致' if decb.get(name) == n else '不一致'))

    print()
    print('#### 表 15-E（文本块级）')
    decE = C.TASK_BOOK_TABLES['table_15E']
    by_cat = {}
    by_month = {}
    for c in chunks:
        cat = dmap[c['doc_id']]['category']
        by_cat[cat] = by_cat.get(cat, 0) + 1
        m = (dmap[c['doc_id']].get('publish_time') or '')[:7]
        by_month[m] = by_month.get(m, 0) + 1
    for cat in ('公告', '财经新闻', '政策文件', '监管公开信息'):
        decv = decE[cat]
        print('  %-8s 文档 声明 %-4s 重算 %-4s ｜ 块 声明 %-5s 重算 %-5s ｜ 占比 声明 %s 重算 %.3f ｜ 块/篇 声明 %s 重算 %.2f'
              % (cat, decv['docs'],
                 sum(1 for d in docs if d['category'] == cat),
                 decv['chunks'], by_cat.get(cat, 0),
                 decv['chunk_share'], by_cat.get(cat, 0) / len(chunks),
                 decv['chunks_per_doc'],
                 by_cat.get(cat, 0) / max(1, sum(1 for d in docs if d['category'] == cat))))
    print('  逐月块数 重算 =', json.dumps(dict(sorted(by_month.items())), ensure_ascii=False),
          '（《16》7.4 声明 2026-06 1226／2026-07 937／2026-08 1620／2026-09 1235）')
    print('  合计 声明 %s 重算 %s' % (decE['合计']['chunks'], len(chunks)))


if __name__ == '__main__':
    main()
