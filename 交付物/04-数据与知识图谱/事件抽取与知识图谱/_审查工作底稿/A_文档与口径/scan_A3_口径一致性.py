# -*- coding: utf-8 -*-
"""A3 冻结口径一致性：《00》第五节 逐项在《01》《02》《04》《07》《10》《13》《16》(+《15》)里找对应表述。

只读。输出到 stdout（由调用方保存为原始输出）。
口径：对每一项给出「每份文档出现次数 + 命中行的文件:行号 与原文（截断）」。
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
DOCS = {
    '00': '00-项目总览与索引.md',
    '01': '交付物/08-文献与开题/选题与项目规划/01-项目总体方案（导师审阅版）.md',
    '02': '02-项目执行总控文档.md',
    '04': '交付物/08-文献与开题/文献调研与开题/04-开题报告.md',
    '07': '交付物/07-设计与需求/需求分析/07-需求分析（第三阶段）.md',
    '10': '交付物/07-设计与需求/总体设计/10-系统总体设计（第四阶段）.md',
    '13': '交付物/04-数据与知识图谱/数据准备/13-数据准备（第五阶段）.md',
    '15': '交付物/04-数据与知识图谱/事件抽取与知识图谱/15-第6阶段任务书（事件抽取与知识图谱）.md',
    '16': '交付物/04-数据与知识图谱/事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md',
}
# 归一化：去掉所有空白字符，避免「6 类实体」与「6类实体」这类空格差异造成假阴性
LINES = {}
NLINES = {}
for k, p in DOCS.items():
    LINES[k] = open(os.path.join(ROOT, p), encoding='utf-8').read().splitlines()
    NLINES[k] = [re.sub(r'\s+', '', x) for x in LINES[k]]
ORDER = ['01', '02', '04', '07', '10', '13', '16', '15', '00']

ITEMS = [
    ('题目', [r'基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现']),
    ('RQ1/RQ2/RQ3', [r'RQ1', r'RQ2', r'RQ3']),
    ('研究假设 H1/H2/H3', [r'\bH1\b', r'\bH2\b', r'\bH3\b']),
    ('不做统计显著性检验', [r'统计显著性']),
    ('6 类实体', [r'6 类实体', r'六类实体']),
    ('8 种核心事件类型', [r'8 种核心事件类型', r'8 种事件类型', r'八种事件类型']),
    ('9 条核心关系', [r'9 条核心关系', r'9 条关系', r'九条关系']),
    ('证据属性三件套', [r'source_doc_id', r'source_chunk_id', r'confidence']),
    ('除 EVIDENCED_BY 外', [r'除 EVIDENCED_BY 外', r'EVIDENCED_BY']),
    ('功能模块六项', [r'财经信息管理', r'财经事件抽取', r'事件知识图谱', r'智能问答', r'证据追溯', r'历史问答']),
    ('用户角色与登录', [r'普通用户', r'登录', r'session_id']),
    ('三存储', [r'MySQL', r'Neo4j', r'FAISS']),
    ('时间口径', [r'data_cutoff_time', r'event_time', r'最近', r'近期', r'30 天', r'90 天']),
    ('测试集 120/60', [r'120', r'108', r'54']),
    ('抽取评测集 Dev/Test', [r'Dev', r'Test 200', r'两段式', r'不重叠']),
    ('对比与消融', [r'Baseline 1', r'Baseline 2', r'\bMethod\b', r'消融', r'C ⊆ D ⊆ E']),
    ('Method=C 组', [r'Method ＝ C 组', r'Method ＝ 消融 C 组', r'C 组']),
    ('Top-K', [r'Top-K', r'五步契约', r'chunk_id']),
    ('时间过滤位置', [r'时间过滤']),
    ('历史证据保护', [r'answer_evidence', r'ON DELETE RESTRICT', r'物理删除']),
    ('候选不足 K', [r'候选不足']),
    ('MySQL 恒六表', [r'恒为六张', r'恒六张']),
    ('检索指标', [r'Recall@K', r'Precision@K', r'MRR', r'Complete Evidence Recall@K']),
    ('问答指标', [r'Answer Accuracy', r'Faithfulness', r'Completeness']),
    ('系统指标', [r'P95', r'95%', r'10 并发', r'100 次']),
    ('0 跳处理', [r'0 跳', r'本次回答未使用图谱扩展', r'虚构']),
    ('内容合规', [r'模型分析（非公开事实）', r'公开事实']),
    ('Prompt v1.2/v1.1', [r'stage6-extract-v1\.2', r'stage6-extract-v1\.1']),
    ('v1.2 规模读数', [r'3293', r'1114', r'2506', r'2802', r'2736', r'1070']),
    ('时间覆盖读数', [r'544', r'494', r'空值率', r'49\.5']),
    ('可过滤性三条读数', [r'177', r'139', r'66', r'49', r'40 篇']),
    ('v1.1 规模读数', [r'3512', r'3767', r'1649', r'1616']),
]

for name, pats in ITEMS:
    npats = [re.sub(r'\s+', '', p) for p in pats]
    print('=' * 96)
    print('【%s】' % name)
    print('-' * 96)
    for k in ORDER:
        hits = []
        for i, ln in enumerate(NLINES[k], 1):
            for p in npats:
                if re.search(p, ln):
                    hits.append((i, LINES[k][i - 1].strip()))
                    break
        print('  [%s] 命中 %d 行：%s' % (k, len(hits), DOCS[k]))
        for i, ln in hits:
            print('      %s:%d| %s' % (k, i, ln[:260]))
    print()
