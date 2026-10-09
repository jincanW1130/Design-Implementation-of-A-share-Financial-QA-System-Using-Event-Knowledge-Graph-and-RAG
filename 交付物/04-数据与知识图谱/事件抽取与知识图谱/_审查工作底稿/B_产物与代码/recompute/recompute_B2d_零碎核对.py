# -*- coding: utf-8 -*-
"""B2 补充：零碎但可逐条重算的声明值。"""
import io
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
V21 = os.path.join(ROOT, '交付物/04-数据与知识图谱/数据准备', '数据集', 'v2.1')
EXPORT = os.path.join(ROOT, '交付物/04-数据与知识图谱/事件抽取与知识图谱', '图谱导出', 'v2.1_v1_2')


def read_jsonl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def count_files(p):
    n = 0
    for dp, dn, fn in os.walk(p):
        n += len(fn)
    return n


def main():
    docs = read_jsonl(os.path.join(V21, 'clean', 'documents.jsonl'))
    chunks = read_jsonl(os.path.join(V21, 'chunks', 'chunks.jsonl'))
    stats = json.load(io.open(os.path.join(EXPORT, 'graph_stats.json'), encoding='utf-8'))
    cs = json.load(io.open(os.path.join(V21, 'reports', 'chunk_stats.json'), encoding='utf-8'))

    print('#### 低于 min_chars 的 7 块是否都满足豁免条件（整篇 < target_chars 且单块）')
    doc_len = {d['doc_id']: len(d['content']) for d in docs}
    n_chunks = Counter(c['doc_id'] for c in chunks)
    ok = True
    for e in cs['min_chars_exemptions']:
        d = e['doc_id']
        cond = (doc_len[d] < 400) and (n_chunks[d] == 1) and e['chars'] == doc_len[d]
        ok &= cond
        print('  doc %s：块长 %d＝整篇 %d；篇内块数 %d；整篇<400=%s → %s'
              % (d, e['chars'], doc_len[d], n_chunks[d], doc_len[d] < 400, '满足' if cond else '不满足'))
    print('  结论：', '全部满足豁免' if ok else '存在不满足项')

    print()
    print('#### 没有事件的文档（Document 节点 = 709 − 17）')
    have = set()
    for r in read_jsonl(os.path.join(ROOT, '交付物/03-代码', '抽取与图谱', '_全量', 'v2.1_v1_2',
                                    'extracted.jsonl')):
        if r.get('events'):
            have.add(r['doc_id'])
    no_ev = sorted(d['doc_id'] for d in docs if d['doc_id'] not in have)
    declared = [1066, 1228, 1235, 1252, 1337, 1348, 1378, 1391, 2030, 2032, 2033, 2036, 2064,
                2084, 2092, 2094, 2105]
    print('  重算无事件文档 %d 篇 = %s' % (len(no_ev), no_ev))
    print('  《16》6.1 声明 %d 篇 = %s' % (len(declared), declared))
    print('  是否一致 =', no_ev == sorted(declared))
    print('  692 = 709 − %d' % len(no_ev))

    print()
    print('#### 缓存文件数（口径留档）')
    for p in ('交付物/04-数据与知识图谱/数据准备/数据集/_抽取缓存/v2.1_v1_2',
              '交付物/04-数据与知识图谱/数据准备/数据集/_抽取缓存/v2.1',
              '交付物/04-数据与知识图谱/数据准备/数据集/_抽取缓存/v2.1_v1_2/时间补抽',
              '交付物/04-数据与知识图谱/数据准备/数据集/_抽取缓存/v2.1/时间补抽',
              '交付物/04-数据与知识图谱/数据准备/数据集/_抽取缓存/v2.1_v1_2/图谱管线',
              '交付物/04-数据与知识图谱/数据准备/数据集/_抽取缓存/v2.1_v1_2/_29篇_旧缓存备份_20260927'):
        full = os.path.join(ROOT, p.replace('/', os.sep))
        print('  %-64s %d 个文件' % (p, count_files(full)))

    print()
    print('#### graph_stats 里几个字段的类型（供报告核对）')
    print('  isolated_nodes.count 类型 =', type(stats['isolated_nodes']['count']).__name__,
          ' 长度 =', len(stats['isolated_nodes']['count']))
    print('  edge_dedup.duplicate_rows_removed =', stats['edge_dedup']['duplicate_rows_removed'])
    print('  counts.singleton_events =', stats['counts']['singleton_events'],
          ' merged_events =', stats['counts']['merged_events'])


if __name__ == '__main__':
    main()
