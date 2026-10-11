# -*- coding: utf-8 -*-
"""改进执行 · C-3：本体恒空列清单（零模型调用、零联网）

对应《不足与展望-改进方案》C-3 实施步骤 1~2：
  列出 7 个恒空列清单，逐个判定"应补齐"还是"应撤销"（判定依据附在报告中）。

数据源（只读）：图谱导出/v2.1_v1_3/nodes.csv + edges.csv
核对目标：论文第五章声明的"导出物 schema 中有 7 列在本版恒为空串
          （节点表 5 列：职务/层级/机构类型/发文机关/发布日期；边表 2 列：有效期起/止）"

本脚本只读既有落盘产物、只写 `改进执行/C3_本体空列清单/` 下的新文件。
"""
from __future__ import annotations

import csv
import io
import json
import os
import sys

ROOT = r'C:\Users\15129\Desktop\毕业设计'
GRAPH_DIR = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '事件抽取与知识图谱', '图谱导出', 'v2.1_v1_3')
OUT_DIR = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', 'C3_本体空列清单')

# 论文第五章声明的 7 列（用于核对）
DECLARED = {
    'nodes': ['role_title', 'level', 'institution_type', 'issuer', 'publish_date'],
    'edges': ['valid_from', 'valid_to'],
}


def log(msg: str) -> None:
    print(msg, flush=True)


def col_stats(rows, col):
    n = sum(1 for r in rows if (r.get(col) or '').strip())
    return n


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    nodes = list(csv.DictReader(io.open(os.path.join(GRAPH_DIR, 'nodes.csv'), encoding='utf-8')))
    edges = list(csv.DictReader(io.open(os.path.join(GRAPH_DIR, 'edges.csv'), encoding='utf-8')))

    stats = {'nodes': {}, 'edges': {}}
    for name, rows in (('nodes', nodes), ('edges', edges)):
        for c in rows[0].keys():
            stats[name][c] = col_stats(rows, c)

    empty_nodes = [c for c, n in stats['nodes'].items() if n == 0]
    empty_edges = [c for c, n in stats['edges'].items() if n == 0]

    # 与论文声明核对
    declared_ok = (sorted(empty_nodes) == sorted(DECLARED['nodes']) and sorted(empty_edges) == sorted(DECLARED['edges']))

    # 判定表（依据在报告中展开）
    judgments = [
        {'col': 'role_title', 'table': 'nodes', 'label': 'Person', 'meaning': '人物职务（董事长/独立董事等）',
         'verdict': '补齐', 'priority': 'v2-中', 'path': '文本可抽：公告中"姓名+职务"称谓模式；先裁定"职务写节点还是写 HAS_EXECUTIVE 边的 role 列"，避免双写'},
        {'col': 'level', 'table': 'nodes', 'label': 'Industry', 'meaning': '行业层级（一级/二级/三级）',
         'verdict': '补齐或撤销（两可，需消费方裁定）', 'priority': 'v2-低',
         'path': '补齐需接标准行业分类层级映射（外部数据）；若无消费方则按撤销流程处理'},
        {'col': 'institution_type', 'table': 'nodes', 'label': 'Institution', 'meaning': '机构类型（监管/交易所/银行/协会）',
         'verdict': '补齐', 'priority': 'v2-中', 'path': '词典+规则（308 个节点规模小，可规则覆盖+人工校验）'},
        {'col': 'issuer', 'table': 'nodes', 'label': 'Policy', 'meaning': '发文机关',
         'verdict': '补齐', 'priority': 'v2-中', 'path': '政策文本抽取（"国务院/证监会/发改委印发"模式）；102 个 Policy 规模可控'},
        {'col': 'publish_date', 'table': 'nodes', 'label': 'Document', 'meaning': '发布日期',
         'verdict': '撤销（建议）', 'priority': 'v2-高（低成本）', 'path': '与 publish_time 重复（692 行已有值）；重复列无消费方（检索侧不读）'},
        {'col': 'valid_from', 'table': 'edges', 'label': 'BELONGS_TO', 'meaning': '关系有效期起',
         'verdict': '撤销或降级为可选（建议）', 'priority': 'v2-中',
         'path': '语料不含行业归属变更的可判证据；该列使 graph_check 恒缺 1 项（belongs_to_carries_validity_columns）；撤销列可同步撤销/降级该检查'},
        {'col': 'valid_to', 'table': 'edges', 'label': 'BELONGS_TO', 'meaning': '关系有效期止',
         'verdict': '撤销或降级为可选（建议）', 'priority': 'v2-中',
         'path': '同 valid_from，两列同进同出'},
    ]

    out = {
        'meta': {
            '数据源': '图谱导出/v2.1_v1_3/nodes.csv + edges.csv',
            '核对目标': '论文第五章"7 列恒为空串"声明',
            '恒空列小结': {'nodes': empty_nodes, 'edges': empty_edges,
                       'total': len(empty_nodes) + len(empty_edges)},
            '与论文声明一致': bool(declared_ok),
        },
        'column_fill_stats': stats,
        'judgments': judgments,
    }
    io.open(os.path.join(OUT_DIR, '恒空列清单.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))

    log('=== C-3 恒空列清单 ===')
    log('nodes 恒空列（%d）: %s' % (len(empty_nodes), empty_nodes))
    log('edges 恒空列（%d）: %s' % (len(empty_edges), empty_edges))
    log('与论文第五章声明一致: %s' % declared_ok)
    log('输出：%s' % OUT_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
