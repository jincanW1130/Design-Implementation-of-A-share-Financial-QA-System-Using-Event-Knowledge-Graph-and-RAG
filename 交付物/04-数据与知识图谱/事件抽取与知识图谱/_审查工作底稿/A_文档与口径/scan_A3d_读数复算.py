# -*- coding: utf-8 -*-
"""A3 补充：按产物复算 v1.1／v1.2 的关键读数与《16》第3.7节 的三条对账恒等式。只读。"""
import json
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))


def load(rel):
    with open(os.path.join(ROOT, rel), encoding='utf-8') as f:
        return json.load(f)


print('=' * 92)
print('A3d-1 可过滤性三条读数（复算，来源 时间覆盖_度量.json）')
print('=' * 92)
for tag, rel in [('v1.1 归档', '交付物/03-代码/抽取与图谱/_全量/v2.1/时间覆盖_度量.json'),
                 ('v1.2 现行', '交付物/03-代码/抽取与图谱/_全量/v2.1_v1_2/时间覆盖_度量.json')]:
    j = load(rel)
    m = j['extraction_layer_after_backfill']['metrics']
    g = j['graph_layer_after_backfill']['metrics']
    print('%s：抽取层 不同日期 %d／≥2 自然月 %d／跨度≥31 天 %d；图谱层 %d／%d／%d；字面口径（≥2 条 event_time 非空）%d' % (
        tag, len(m['doc_ids_ge2']), len(m['doc_ids_multi_month']), m['docs_times_span_ge_31_days'],
        len(g['doc_ids_ge2']), len(g['doc_ids_multi_month']), g['docs_times_span_ge_31_days'],
        m['docs_with_ge2_dated_events']))
print()

print('=' * 92)
print('A3d-2 v1.2 时间覆盖（复算）')
print('=' * 92)
j2 = load('交付物/03-代码/抽取与图谱/_全量/v2.1_v1_2/时间覆盖_度量.json')
for k in ['extraction_layer_before_backfill', 'extraction_layer_after_backfill', 'graph_layer_after_backfill']:
    v = j2[k]
    print('  %-38s 事件 %s／非空 %s／空 %s（%.1f%%）' % (
        k, v['events'], v['events_with_time'], v['events_without_time'],
        100.0 * v['events_without_time'] / v['events']))
print('  backfill:', j2['backfill'])
print()

print('=' * 92)
print('A3d-3 《16》3.7 三条对账恒等式（用 graph_stats.json 复算）')
print('=' * 92)
gv12 = load('交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/graph_stats.json')
c = gv12['counts']
er = c['edges_by_relation']
nod = c['nodes_by_label']
sem = sum(v for k, v in er.items() if k != 'EVIDENCED_BY')
print('  nodes_by_label:', nod, '合计', sum(nod.values()), '（文件声明 %s）' % c.get('nodes_total'))
print('  edges_by_relation:', er, '合计', sum(er.values()), '（文件声明 %s）' % c.get('edges_total'))
print('  语义边合计 =', sem)
print('  ① 实体侧：3293 − 1070 = %d；998 节点拆解 104＋73＋316＋403＋102 = %d；＋12 = %d；＋692＋1100 = %d' % (
    3293 - 1070, 104 + 73 + 316 + 403 + 102, 998 + 12, 998 + 12 + 692 + 1100))
print('  ② 事件侧：1114 − 14 = %d' % (1114 - 14))
print('  ③ 关系侧：2506 − 878 − 1 − 2 = %d；＋1111 = %d' % (2506 - 878 - 1 - 2, (2506 - 878 - 1 - 2) + 1111))
print()

print('=' * 92)
print('A3d-4 两版导出物数据行数（与《16》第6章的对照）')
print('=' * 92)
for tag, sub in [('v1.1 归档', 'v2.1'), ('v1.2 现行', 'v2.1_v1_2')]:
    for f in ['nodes.csv', 'edges.csv']:
        p = os.path.join(ROOT, '交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出', sub, f)
        n = sum(1 for _ in open(p, encoding='utf-8')) - 1
        print('  %s %-10s 数据行 %d' % (tag, f, n))
print()

print('=' * 92)
print('A3d-5 字面口径与「不同日期」口径的独立复算（extracted.jsonl ＋ event_time_backfill.json）')
print('=' * 92)
for tag, base in [('v1.1 归档', '交付物/03-代码/抽取与图谱/_全量/v2.1'),
                  ('v1.2 现行', '交付物/03-代码/抽取与图谱/_全量/v2.1_v1_2')]:
    ov = load(base + '/event_time_backfill.json')
    patch = {r['event_id']: r['event_time'] for r in ov['results'] if r.get('event_time')}
    before, after = {}, {}
    with open(os.path.join(ROOT, base + '/extracted.jsonl'), encoding='utf-8') as f:
        for ln in f:
            rec = json.loads(ln)
            for e in rec.get('events') or []:
                before.setdefault(rec['doc_id'], []).append(e.get('event_time'))
                after.setdefault(rec['doc_id'], []).append(e.get('event_time') or patch.get(e.get('event_id')))
    lit = lambda dd: len([d for d, v in dd.items() if sum(1 for x in v if x) >= 2])
    dis = lambda dd: len([d for d, v in dd.items() if len({x for x in v if x}) >= 2])
    print('  %s：文档 %d；字面口径（≥2 条非空）%d → %d；不同日期口径 %d → %d' % (
        tag, len(after), lit(before), lit(after), dis(before), dis(after)))
