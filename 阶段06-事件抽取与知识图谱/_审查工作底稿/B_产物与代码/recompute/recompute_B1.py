# -*- coding: utf-8 -*-
"""B1：从 documents.jsonl / chunks.jsonl 重算《13》第5／6.7／6.8节声明的可算量。

只读工作区，输出到 stdout（由调用方重定向到 raw/ 下留档）。
"""
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..'))
V21 = os.path.join(ROOT, '阶段05-数据准备', '数据集', 'v2.1')


def read_jsonl(path):
    out = []
    with io.open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def line(*a):
    print(*a)


def main():
    docs = read_jsonl(os.path.join(V21, 'clean', 'documents.jsonl'))
    chunks = read_jsonl(os.path.join(V21, 'chunks', 'chunks.jsonl'))
    meta = json.load(io.open(os.path.join(V21, 'meta', 'dataset.json'), encoding='utf-8'))
    build_meta = json.load(io.open(os.path.join(V21, 'index', 'build_meta.json'), encoding='utf-8'))
    vm = read_jsonl(os.path.join(V21, 'index', 'vector_map.jsonl'))
    report = json.load(io.open(os.path.join(V21, 'reports', 'consistency_report.json'), encoding='utf-8'))
    chunk_stats = json.load(io.open(os.path.join(V21, 'reports', 'chunk_stats.json'), encoding='utf-8'))
    time_cov = json.load(io.open(os.path.join(V21, 'reports', 'time_coverage.json'), encoding='utf-8'))
    company_cov = json.load(io.open(os.path.join(V21, 'reports', 'company_coverage.json'), encoding='utf-8'))

    line('#### B1-01 规模')
    line('documents_lines =', len(docs))
    line('chunks_lines =', len(chunks))
    line('doc_id_unique =', len(set(d['doc_id'] for d in docs)))
    line('chunk_id_unique =', len(set(c['chunk_id'] for c in chunks)))
    line('vector_map_lines =', len(vm))
    line('build_meta.ntotal =', build_meta.get('ntotal'), 'dim =', build_meta.get('dim'))

    line()
    line('#### B1-02 类目分布')
    cat = Counter(d['category'] for d in docs)
    line('category_counts =', dict(sorted(cat.items(), key=lambda kv: -kv[1])))
    line('category_source =', dict(Counter((d['category'], d['source']) for d in docs)))
    chunk_cat = Counter()
    cat_of_doc = {d['doc_id']: d['category'] for d in docs}
    for c in chunks:
        chunk_cat[cat_of_doc.get(c['doc_id'], '<unknown>')] += 1
    line('chunks_by_category =', dict(chunk_cat))

    line()
    line('#### B1-03 公司数与行业数')
    codes = set()
    for d in docs:
        for c0 in d.get('company_list') or []:
            codes.add(c0)
    line('company_list_union_size =', len(codes))
    all_sources = set()
    for d in docs:
        for c0 in d.get('subject_companies') or []:
            all_sources.add(c0)
    line('subject_companies_union_size =', len(all_sources))
    line('meta.dataset.json 里的公司/行业读数 =',
         json.dumps({k: v for k, v in meta.items() if 'compan' in k or 'industr' in k or 'sector' in k},
                    ensure_ascii=False))

    # 行业数：从 config.COMPANIES 的 industry 字段重算（不 import config，直接解析其常量太重；改为读 meta）
    line('dataset.json keys =', list(meta.keys()))

    line()
    line('#### B1-04 时间')
    pub = sorted(d['publish_time'] for d in docs)
    line('publish_time_min =', pub[0], ' max =', pub[-1])
    line('distinct_publish_dates =', len(set(pub)))
    blank_pub = sum(1 for d in docs if not d.get('publish_time'))
    line('blank_publish_time =', blank_pub)
    cutoff = meta.get('data_cutoff_time') or '2026-09-25T23:59:59+08:00'
    line('data_cutoff_time(meta) =', meta.get('data_cutoff_time'))
    cutoff_date = cutoff[:10]
    later = [d['doc_id'] for d in docs if d['publish_time'] > cutoff_date]
    line('later_than_cutoff_doc_ids =', later)
    from datetime import date
    y, m, dd = (int(x) for x in pub[0].split('-'))
    span = (date(int(cutoff_date[:4]), int(cutoff_date[5:7]), int(cutoff_date[8:10])) - date(y, m, dd)).days
    line('cutoff_minus_earliest_days =', span)
    months = Counter(d['publish_time'][:7] for d in docs)
    line('by_month =', dict(sorted(months.items())))
    recent = sum(1 for d in docs if '2026-08-27' <= d['publish_time'] <= '2026-09-25')
    earlier = sum(1 for d in docs if '2026-06-17' <= d['publish_time'] <= '2026-08-26')
    line('bucket_recent =', recent, ' bucket_earlier =', earlier,
         ' outside =', len(docs) - recent - earlier)

    line()
    line('#### B1-05 doc_id 分块')
    blocks = {'公告': (1000, 2000), '财经新闻': (2000, 3000), '政策文件': (3000, 4000),
              '监管公开信息': (4000, 5000)}
    out_of_block = []
    per_block = defaultdict(list)
    for d in docs:
        lo, hi = blocks.get(d['category'], (None, None))
        if lo is None or not (lo < d['doc_id'] < hi):
            out_of_block.append((d['doc_id'], d['category']))
        per_block[d['category']].append(d['doc_id'])
    line('out_of_block =', out_of_block)
    for k, v in per_block.items():
        line('  %s: n=%d min=%d max=%d' % (k, len(v), min(v), max(v)))

    line()
    line('#### B1-06 chunk_id = doc_id*1000 + chunk_index（逐条）')
    bad_formula = [c['chunk_id'] for c in chunks if c['chunk_id'] != c['doc_id'] * 1000 + c['chunk_index']]
    line('mismatched =', len(bad_formula), bad_formula[:5])
    per_doc_idx = defaultdict(list)
    for c in chunks:
        per_doc_idx[c['doc_id']].append(c['chunk_index'])
    gap = [k for k, v in per_doc_idx.items() if sorted(v) != list(range(len(v)))]
    line('documents_with_index_gap_or_nonint =', len(gap), gap[:5])
    no_chunk = [d['doc_id'] for d in docs if d['doc_id'] not in per_doc_idx]
    line('documents_without_any_chunk =', len(no_chunk), no_chunk[:5])
    unknown = set(per_doc_idx) - set(d['doc_id'] for d in docs)
    line('chunks_with_unknown_doc_id =', len(unknown))

    line()
    line('#### B1-07 切分口径 400/512/128/50')
    # 复算：块字符长度、重叠、边界优先级不可直接复算（需要重跑切分器）；这里只核验产物是否自洽于四要素
    lens = [len(c['content']) for c in chunks]
    line('chunk_chars min/mean/max =', min(lens), round(sum(lens) / len(lens), 2), max(lens))
    over_max = [(c['chunk_id'], len(c['content'])) for c in chunks if len(c['content']) > 512]
    line('chunks_over_max_chars(512) =', len(over_max), over_max[:5])
    under_min = [(c['chunk_id'], len(c['content'])) for c in chunks if len(c['content']) < 128]
    line('chunks_under_min_chars(128) =', len(under_min), under_min[:5])
    # 重叠：相邻块尾部/头部 50 字符窗口的公共后缀-前缀
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c['doc_id']].append(c)
    ov = []
    for did, cs in by_doc.items():
        cs.sort(key=lambda x: x['chunk_index'])
        for a, b in zip(cs, cs[1:]):
            k = 0
            m = min(50, len(a['content']), len(b['content']))
            while k < m and a['content'][len(a['content']) - k - 1] == b['content'][m - k - 1 if False else k]:
                k += 1
            # 简化：直接找最长 k<=50 使 a 的后缀 == b 的前缀
            k = 0
            for kk in range(min(50, len(a['content']), len(b['content'])), 0, -1):
                if a['content'][-kk:] == b['content'][:kk]:
                    k = kk
                    break
            ov.append(k)
    line('adjacent_pairs =', len(ov), ' overlap_50_hits =', sum(1 for x in ov if x == 50),
         ' overlap_gt0 =', sum(1 for x in ov if x > 0), ' overlap_gt50 =', sum(1 for x in ov if x > 50))
    line('chunk_stats.min_chars_exemptions =',
         chunk_stats.get('min_chars_exemptions'), ' keys=', list(chunk_stats.keys()))
    line('token_count min/max/sum =',
         min(c['token_count'] for c in chunks), max(c['token_count'] for c in chunks),
         sum(c['token_count'] for c in chunks))
    line('vector_id domain =', min(c['vector_id'] for c in chunks), max(c['vector_id'] for c in chunks),
         ' distinct =', len(set(c['vector_id'] for c in chunks)))

    line()
    line('#### B1-08 每公司文档数')
    per_company = Counter()
    for d in docs:
        for c0 in set(d.get('company_list') or []):
            per_company[c0] += 1
    vals = sorted(per_company.values())
    line('companies_in_company_list =', len(per_company))
    if vals:
        line('min =', vals[0], ' median =', vals[len(vals) // 2], ' max =', vals[-1],
             ' >=5 =', sum(1 for v in vals if v >= 5))
    line('company_coverage.json =', json.dumps(company_cov, ensure_ascii=False)[:1200])

    line()
    line('#### B1-09 一致性报告 14 项')
    line('report keys =', list(report.keys()))
    line('summary =', json.dumps(report.get('summary'), ensure_ascii=False))
    checks = report.get('checks') or report.get('items') or []
    if isinstance(checks, list):
        for c in checks:
            line('  ', json.dumps({k: c.get(k) for k in ('name', 'id', 'passed', 'result') if k in c},
                                  ensure_ascii=False)[:200])

    line()
    line('#### B1-10 S 组守卫（索引集中度）')
    cnt = Counter(c['doc_id'] for c in chunks)
    top = cnt.most_common(5)
    line('top5_doc_chunk_counts =', top)
    line('top1_share = %.4f%%' % (100.0 * top[0][1] / len(chunks)))
    line('top5_share = %.4f%%' % (100.0 * sum(n for _, n in top) / len(chunks)))
    # 同标题跨公司复用
    by_title = defaultdict(set)
    t2docs = defaultdict(list)
    for d in docs:
        key = re.sub(r'\s+', '', d['title'])
        by_title[key].add(frozenset(d.get('company_list') or []))
        t2docs[key].append(d['doc_id'])
    cross = {k: v for k, v in by_title.items() if len(v) > 1 and any(v)}
    line('titles_reused_across_company_sets =', len(cross))
    dup_titles = {k: v for k, v in t2docs.items() if len(v) > 1}
    line('duplicate_normalized_titles =', len(dup_titles), list(dup_titles.items())[:3])

    line()
    line('#### B1-11 三个判重键')
    urls = [d['url'] for d in docs]
    line('distinct_urls =', len(set(urls)), ' blank =', sum(1 for u in urls if not u))
    fps = [d.get('content_sha256_16') for d in docs]
    line('distinct_fingerprints =', len(set(fps)), ' blank =', sum(1 for f in fps if not f))
    # 重算指纹
    import hashlib
    mism = []
    for d in docs:
        h = hashlib.sha256(d['content'].encode('utf-8')).hexdigest()[:16]
        if h != d.get('content_sha256_16'):
            mism.append(d['doc_id'])
    line('fingerprint_recompute_mismatch =', len(mism), mism[:5])

    line()
    line('#### B1-12 company_list / subject_companies 口径')
    empty_cl = Counter(d['category'] for d in docs if not d.get('company_list'))
    line('empty_company_list_by_cat =', dict(empty_cl))
    bad = [d['doc_id'] for d in docs if d.get('company_list') is None or not isinstance(d.get('company_list'), list)]
    line('null_or_nonlist_company_list =', len(bad))
    bad2 = [d['doc_id'] for d in docs if d.get('subject_companies') is None or not isinstance(d.get('subject_companies'), list)]
    line('null_or_nonlist_subject_companies =', len(bad2))
    not_subset = [d['doc_id'] for d in docs
                  if not set(d.get('subject_companies') or []) <= set(d.get('company_list') or [])]
    line('subject_not_subset_of_company_list =', len(not_subset), not_subset[:5])
    ge2_cl = sum(1 for d in docs if len(d.get('company_list') or []) >= 2)
    ge2_sc = sum(1 for d in docs if len(d.get('subject_companies') or []) >= 2)
    line('company_list_ge2 =', ge2_cl, ' subject_companies_ge2 =', ge2_sc)

    line()
    line('#### B1-13 meta\\dataset.json 与《13》声明')
    line(json.dumps(meta, ensure_ascii=False, indent=1)[:4000])

    line()
    line('#### B1-14 time_coverage.json 原文')
    line(json.dumps(time_cov, ensure_ascii=False, indent=1)[:3000])


if __name__ == '__main__':
    main()
