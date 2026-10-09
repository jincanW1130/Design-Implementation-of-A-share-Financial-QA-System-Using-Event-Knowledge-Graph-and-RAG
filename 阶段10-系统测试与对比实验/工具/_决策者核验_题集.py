# -*- coding: utf-8 -*-
"""决策者独立核验：正式测试集（FQ-001～FQ-120）的硬约束。

与建集脚本**不复用任何代码**——本脚本从 chunks.jsonl 与图谱导出物现场重算，
目的就是让"两把尺子"互相印证（项目纪律：已完成必须独立复现）。

可过滤文档集合的算法**对齐** `阶段10-...\工具\统计分格可时序候选.py` 的既有口径
（Document ←EVIDENCED_BY← Event，取 event_time，文档 id 归一为 int）。

核验项：
  V1 条数 / qid 连续唯一 / cell 与题量配额（9 格 × 12 ＋ 压力 12）
  V2 gold 条数 1..10、count == len(set(chunk_ids))、doc_ids 与 chunk 的 doc_id 一致
  V3 每条 anchor 的 quote 去空白后在对应 chunk 的 content 中逐字命中
  V4 带时间约束的题：gold 所在文档 ⊆「含 >=2 个不同 event_time 日期」的可过滤文档集合
  V5 time_window 字段形态与 PE 集一致（lo/hi/label/basis/cutoff/empty_policy）、
     落在 data_cutoff_time 之内、lo <= hi
  V6 与 30 题预实验集（PE-01～PE-30）的重叠（题干/gold 集合）
  V7 标签自洽：task_type/gold_hop_depth 与 cell 一致
  V8 source_material 的 doc_id 均在 documents.jsonl 中

用法：python <本脚本> [题集路径...]
"""
from __future__ import annotations

import collections
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
DS = os.path.join(ROOT, '阶段05-数据准备', '数据集', 'v2.1')
GRAPH = os.path.join(ROOT, '阶段06-事件抽取与知识图谱', '图谱导出', 'v2.1_v1_3')
PE = os.path.join(ROOT, '阶段07-RAG检索系统', '预实验问题集', 'questions.jsonl')

EXPECT_CELLS = [('事实型', 0), ('事实型', 1), ('事实型', 2),
                ('事件型', 0), ('事件型', 1), ('事件型', 2),
                ('关系型', 0), ('关系型', 1), ('关系型', 2)]
PE_TW_KEYS = {'lo', 'hi', 'label', 'basis', 'cutoff', 'empty_policy'}
CUTOFF = '2026-09-25'


def scrub(s):
    return re.sub(r'\s+', '', s or '')


def load_jsonl(path):
    with io.open(path, encoding='utf-8') as f:
        return [json.loads(l) for l in f if l.strip()]


def read_csv_rows(path):
    with open(path, 'r', encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh))


def doc_date_and_event_maps(graph_dir):
    """对齐 `统计分格可时序候选.py::doc_date_and_event_maps` 的既有口径。"""
    nodes = {r['node_id']: r for r in read_csv_rows(os.path.join(graph_dir, 'nodes.csv'))}
    edges = read_csv_rows(os.path.join(graph_dir, 'edges.csv'))
    doc_events = collections.defaultdict(set)
    for e in edges:
        if e.get('relation') != 'EVIDENCED_BY':
            continue
        h, t = e.get('head_id'), e.get('tail_id')
        if nodes.get(h, {}).get('label') == 'Event' and nodes.get(t, {}).get('label') == 'Document':
            try:
                doc_events[int(t)].add(h)
            except (TypeError, ValueError):
                continue
    now, a_class = set(), set()
    for doc, evs in doc_events.items():
        dates = {(nodes[e].get('event_time') or '').strip() for e in evs}
        dates.discard('')
        if len(dates) >= 2:
            now.add(doc)
        elif len(evs) >= 2:
            a_class.add(doc)
    return now, a_class


def main(paths):
    fails, warns = [], []

    chunks = {int(r['chunk_id']): r for r in load_jsonl(
        os.path.join(DS, 'chunks', 'chunks.jsonl'))}
    docs = {int(r['doc_id']): r for r in load_jsonl(
        os.path.join(DS, 'clean', 'documents.jsonl'))}
    print('语料：chunks=%d  documents=%d' % (len(chunks), len(docs)))

    filterable, a_class = doc_date_and_event_maps(GRAPH)
    print('可过滤文档（现场重算，>=2 个不同 event_time 日期）：%d 篇；A 类（>=2 事件但日期不足）%d 篇'
          % (len(filterable), len(a_class)))

    pe = load_jsonl(PE) if os.path.exists(PE) else []
    pe_gold = {frozenset(int(x) for x in r['gold_evidence_chunk_ids']) for r in pe}
    pe_q = {scrub(r['question']) for r in pe}
    print('PE 集：%d 题' % len(pe))

    allrows = []
    for p in paths:
        if not os.path.exists(p):
            fails.append('题集不存在：%s' % p)
            continue
        rows = load_jsonl(p)
        allrows.extend(rows)
        print('== %s：%d 条' % (os.path.basename(os.path.dirname(p)) + '/' + os.path.basename(p),
                                len(rows)))

    # ---- V1 配额 ----
    cell_ct = collections.defaultdict(list)
    for r in allrows:
        cell_ct[(r['task_type'], int(r['gold_hop_depth']), r['time_constraint'],
                 r['subset'])].append(r['qid'])
    for t, h in EXPECT_CELLS:
        for tc in ('无', '有'):
            n = len(cell_ct[(t, h, tc, '核心')])
            if n != 6:
                fails.append('V1 核心格 (%s+%d跳,%s) 题量 %d ≠ 6' % (t, h, tc, n))
    if len(cell_ct[('关系型', 2, '有', '压力')]) != 12:
        fails.append('V1 压力子集题量 %d ≠ 12' % len(cell_ct[('关系型', 2, '有', '压力')]))
    if len(allrows) != 120:
        fails.append('V1 总题量 %d ≠ 120' % len(allrows))
    qids = [r['qid'] for r in allrows]
    if len(set(qids)) != len(qids):
        fails.append('V1 qid 有重复')
    if sorted(set(qids)) != ['FQ-%03d' % i for i in range(1, 121)]:
        fails.append('V1 qid 不是 FQ-001..FQ-120 的完整集合')
    print('V1 题量：总 %d｜核心 %d｜压力 %d' % (
        len(allrows), sum(1 for r in allrows if r['subset'] == '核心'),
        sum(1 for r in allrows if r['subset'] == '压力')))

    # ---- 逐题 ----
    n_anchor = 0
    n_tw = 0
    overlap_q, overlap_g = [], []
    tw_keys = collections.Counter()
    for r in allrows:
        q = r['qid']
        cids = [int(x) for x in r['gold_evidence_chunk_ids']]
        dids = [int(x) for x in r['gold_evidence_doc_ids']]
        if not (1 <= len(cids) <= 10):
            fails.append('V2 %s gold 条数 %d 不在 1..10' % (q, len(cids)))
        if int(r['gold_evidence_count']) != len(cids):
            fails.append('V2 %s gold_evidence_count 与列表长度不符' % q)
        if len(set(cids)) != len(cids):
            fails.append('V2 %s gold chunk_id 有重复' % q)
        real_docs = set()
        for c in cids:
            if c not in chunks:
                fails.append('V2 %s gold chunk %d 不在语料中' % (q, c))
            else:
                real_docs.add(int(chunks[c]['doc_id']))
        if real_docs and set(dids) != real_docs:
            fails.append('V2 %s gold doc_ids %s 与 chunk 实际 %s 不符'
                         % (q, sorted(dids), sorted(real_docs)))
        for a in r['gold_verify_anchors']:
            c = int(a['chunk_id'])
            if c not in chunks:
                fails.append('V3 %s anchor chunk %d 不在语料' % (q, c))
                continue
            if scrub(a['quote']) not in scrub(chunks[c]['content']):
                fails.append('V3 %s anchor 未在 chunk %d 原文中逐字命中：%r'
                             % (q, c, a['quote'][:40]))
            else:
                n_anchor += 1
        if r['time_constraint'] == '有':
            n_tw += 1
            outside = sorted(set(dids) - filterable)
            if outside:
                fails.append('V4 %s 时间约束题 gold 文档不在可过滤集合：%s' % (q, outside))
            tw = r.get('time_window') or {}
            tw_keys[tuple(sorted(tw.keys()))] += 1
            if set(tw.keys()) != PE_TW_KEYS:
                fails.append('V5 %s time_window 键集合 %s 与 PE 集口径 %s 不一致'
                             % (q, sorted(tw.keys()), sorted(PE_TW_KEYS)))
            lo, hi = tw.get('lo'), tw.get('hi')
            if not lo or not hi:
                fails.append('V5 %s time_window 缺 lo/hi' % q)
            else:
                if lo > hi:
                    fails.append('V5 %s 窗口 lo > hi' % q)
                if hi > CUTOFF:
                    fails.append('V5 %s 窗口 hi=%s 超过 data_cutoff_time=%s' % (q, hi, CUTOFF))
        else:
            if r.get('time_window'):
                fails.append('V5 %s 无时间约束但 time_window 非空' % q)
        if r['cell'] != '%s+%d跳' % (r['task_type'], int(r['gold_hop_depth'])):
            fails.append('V7 %s cell=%s 与 task_type/hop 不符' % (q, r['cell']))
        for sm in r.get('source_material') or []:
            if int(sm['doc_id']) not in docs:
                fails.append('V8 %s source_material doc %s 不在 documents' % (q, sm['doc_id']))
        if frozenset(cids) in pe_gold:
            overlap_g.append(q)
        if scrub(r['question']) in pe_q:
            overlap_q.append(q)

    print('V2/V3：anchor 逐字命中 %d 条' % n_anchor)
    print('V4：带时间约束题 %d 道' % n_tw)
    print('V5：time_window 键集合分布 %s' % dict(tw_keys))
    print('V6：与 PE 集 gold 集合完全相同的题 %d 道 %s' % (len(overlap_g), overlap_g))
    print('V6：与 PE 集题干完全相同的题 %d 道 %s' % (len(overlap_q), overlap_q))
    if overlap_q:
        fails.append('V6 题干与 PE 集重复：%s' % overlap_q)

    print('\n' + '=' * 70)
    if fails:
        c = collections.Counter(re.match(r'^(V\d)', x).group(1) for x in fails)
        print('失败 %d 项（按组：%s）：' % (len(fails), dict(c)))
        for x in sorted(fails)[:60]:
            print('  !! %s' % x)
        if len(fails) > 40:
            print('  ... 另有 %d 项' % (len(fails) - 40))
    else:
        print('全部核验项通过（V1～V8）')
    print('=' * 70)
    return 1 if fails else 0


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        args = [os.path.join(ROOT, '阶段10-系统测试与对比实验', '测试集', '_批A', 'questions_A.jsonl'),
                os.path.join(ROOT, '阶段10-系统测试与对比实验', '测试集', '_批B', 'questions_B.jsonl')]
    raise SystemExit(main(args))
