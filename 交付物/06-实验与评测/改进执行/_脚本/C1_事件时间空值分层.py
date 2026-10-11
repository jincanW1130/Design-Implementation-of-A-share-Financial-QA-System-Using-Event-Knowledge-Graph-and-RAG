# -*- coding: utf-8 -*-
"""改进执行 · C-1：事件时间空值分层统计（零模型调用、零联网）

对应《不足与展望-改进方案》C-1 实施步骤 1（分层统计空值来源）与改进上限估算。

数据源（只读）：
  交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/
    nodes.csv（3607 节点，含 Event 1098）
    edges.csv（3614 边，EVIDENCED_BY: Event → Document）

分层口径（两层交叉）：
  第一层：空值事件的文本可解析性（name+description）
    L1 绝对日期（年-月-日 完整）   → 抽取遗漏，可直接补抽
    L2 部分日期（年月 或 月日）     → 抽取遗漏，可配合文档年份补抽
    L3 仅相对时间表述（近日/本月/年内/当日…） → 需规则+参照日期换算
    L4 无任何时间信息               → 只能靠文档元数据兜底或判为真缺失
  第二层：源文档可得性（EVIDENCED_BY → Document.publish_time）
    with_doc / without_doc

改进情景（空值率下降路径，均按现有 1098 事件总量计算）：
  S1 补抽 L1+L2               null → 544 − |L1+L2|
  S2 S1 + L3(有文档)规则换算   → 再减 L3_with_doc
  S3 S2 + L4(有文档)兜底       → 再减 L4_with_doc（推断时间，需时限字段标记）
  残余 = L3_without_doc + L4_without_doc

本脚本只读既有落盘产物、只写 `改进执行/C1_事件时间空值分层/` 下的新文件。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
from collections import Counter

ROOT = r'C:\Users\15129\Desktop\毕业设计'
GRAPH_DIR = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '事件抽取与知识图谱', '图谱导出', 'v2.1_v1_3')
OUT_DIR = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', 'C1_事件时间空值分层')

# ---- 文本模式 ----
RE_FULL_DATE = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日')
RE_ISO_DATE = re.compile(r'(20\d{2})-(\d{2})-(\d{2})')
RE_YEAR_MONTH = re.compile(r'(20\d{2})\s*年\s*(\d{1,2})\s*月(?!\s*\d{1,2}\s*日)')
RE_MONTH_DAY = re.compile(r'(?<![0-9])(\d{1,2})\s*月\s*(\d{1,2})\s*日')
REL_TOKENS = (
    '近日', '近期', '日前', '最近', '不久',
    '上周', '本周', '下周', '上月', '本月', '当月', '次月',
    '上季度', '本季度', '下季度', '当季',
    '年内', '年初', '年中', '年底', '今年', '去年', '明年', '当年', '次年', '翌年',
    '同日', '当日', '即日', '次日', '翌日', '前一日',
    '一季度', '二季度', '三季度', '四季度', '第一季度', '第二季度', '第三季度', '第四季度',
    '上半年', '下半年', '上一年', '本年度', '上年度', '财年', '月末', '月初', '期末',
)


def log(msg: str) -> None:
    print(msg, flush=True)


def classify_text(text: str) -> str:
    """返回 L1/L2/L3/L4。"""
    if RE_FULL_DATE.search(text) or RE_ISO_DATE.search(text):
        return 'L1_绝对日期'
    if RE_YEAR_MONTH.search(text) or RE_MONTH_DAY.search(text):
        return 'L2_部分日期'
    for tok in REL_TOKENS:
        if tok in text:
            return 'L3_相对时间'
    return 'L4_无时间信息'


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)

    nodes = list(csv.DictReader(io.open(os.path.join(GRAPH_DIR, 'nodes.csv'), encoding='utf-8')))
    edges = list(csv.DictReader(io.open(os.path.join(GRAPH_DIR, 'edges.csv'), encoding='utf-8')))

    # doc_id -> publish_time
    doc_pub = {r['node_id']: (r.get('publish_time') or '').strip()
               for r in nodes if r['label'] == 'Document'}
    # event -> docs（EVIDENCED_BY）
    ev_docs = {}
    for e in edges:
        if e['relation'] == 'EVIDENCED_BY':
            ev_docs.setdefault(e['head_id'], []).append(e['tail_id'])

    events = [r for r in nodes if r['label'] == 'Event']
    empty = [r for r in events if not (r.get('event_time') or '').strip()]
    nonempty = [r for r in events if (r.get('event_time') or '').strip()]

    # ---- 分层 ----
    detail_rows = []
    layer_hist = Counter()
    layer_doc = Counter()   # (层, 有文档/无文档)
    for r in empty:
        text = (r.get('name') or '') + ' ' + (r.get('description') or '')
        layer = classify_text(text)
        docs = ev_docs.get(r['node_id'], [])
        has_pub = any(doc_pub.get(d) for d in docs)
        layer_hist[layer] += 1
        layer_doc[(layer, 'with_doc' if has_pub else 'without_doc')] += 1
        detail_rows.append({
            'event_id': r['node_id'], 'event_type': r.get('event_type'),
            'layer': layer, 'n_docs': len(docs), 'has_publish_time': has_pub,
            'name': (r.get('name') or '')[:60],
            'description': (r.get('description') or '')[:120],
        })

    n_events = len(events)
    n_empty = len(empty)
    n_nonempty = len(nonempty)

    # ---- 改进情景 ----
    l1 = layer_hist['L1_绝对日期']
    l2 = layer_hist['L2_部分日期']
    l3_doc = layer_doc[('L3_相对时间', 'with_doc')]
    l4_doc = layer_doc[('L4_无时间信息', 'with_doc')]
    l3_nodoc = layer_doc[('L3_相对时间', 'without_doc')]
    l4_nodoc = layer_doc[('L4_无时间信息', 'without_doc')]

    scen = {
        '现状': {'null': n_empty, 'null_rate': round(n_empty / n_events, 6)},
        'S1_补抽绝对与部分日期': {'null': n_empty - l1 - l2},
        'S2_加相对时间规则换算(有文档)': {'null': n_empty - l1 - l2 - l3_doc},
        'S3_加文档元数据兜底(有文档)': {'null': n_empty - l1 - l2 - l3_doc - l4_doc},
    }
    for k, v in scen.items():
        if 'null_rate' not in v:
            v['null_rate'] = round(v['null'] / n_events, 6)

    # ---- 输出 ----
    out = {
        'meta': {
            '数据源': '图谱导出/v2.1_v1_3/nodes.csv + edges.csv（图谱交付口径）',
            '分层定义': {
                'L1_绝对日期': '文本含 年月日 完整日期（抽取遗漏，可直接补抽）',
                'L2_部分日期': '文本含 年月 或 月日（可配合文档年份补抽）',
                'L3_相对时间': '文本含相对时间表述（需规则+参照日期换算）',
                'L4_无时间信息': '文本无任何时间线索（只能文档元数据兜底或判真缺失）',
            },
            '文档可得性': 'EVIDENCED_BY → Document.publish_time 是否可解析',
        },
        'counts': {
            'events_total': n_events,
            'event_time_nonempty': n_nonempty,
            'event_time_empty': n_empty,
            'empty_rate': round(n_empty / n_events, 6),
        },
        'layer_hist': dict(layer_hist),
        'layer_x_doc': {f'{k[0]}|{k[1]}': v for k, v in layer_doc.items()},
        'scenarios': scen,
        'residual': {
            'L3_without_doc': l3_nodoc,
            'L4_without_doc': l4_nodoc,
            'total_residual': l3_nodoc + l4_nodoc,
        },
        'samples': {lay: [d for d in detail_rows if d['layer'] == lay][:5]
                    for lay in ('L1_绝对日期', 'L2_部分日期', 'L3_相对时间', 'L4_无时间信息')},
    }
    io.open(os.path.join(OUT_DIR, '分层统计.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
    # 全量明细（供后续补抽工作直接使用）
    with io.open(os.path.join(OUT_DIR, '空值事件分层明细.jsonl'), 'w', encoding='utf-8', newline='\n') as fh:
        for d in sorted(detail_rows, key=lambda x: (x['layer'], x['event_id'])):
            fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + '\n')

    log('=== C-1 事件时间空值分层（v2.1_v1_3）===')
    log('事件总数 %d | 非空 %d | 空值 %d（%.1f%%）' % (n_events, n_nonempty, n_empty, 100 * n_empty / n_events))
    log('分层：%s' % dict(layer_hist))
    log('分层×文档：%s' % {f'{k[0]}/{k[1]}': v for k, v in sorted(layer_doc.items())})
    log('\n改进情景：')
    for k, v in scen.items():
        log('  %s: null=%d (%.1f%%)' % (k, v['null'], 100 * v['null_rate']))
    log('  残余（无文档可兜底）: %d' % (l3_nodoc + l4_nodoc))
    log('\n输出：%s' % OUT_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
