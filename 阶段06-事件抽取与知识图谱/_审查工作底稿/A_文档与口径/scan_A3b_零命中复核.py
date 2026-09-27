# -*- coding: utf-8 -*-
"""A3 补充：对第一轮 0 命中的口径项，用替代措辞复核，避免把「换了说法」误判成「缺失」。只读。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
DOCS = {
    '01': '阶段01-选题与项目规划/01-项目总体方案（导师审阅版）.md',
    '02': '02-项目执行总控文档.md',
    '04': '阶段02-文献调研与开题/04-开题报告.md',
    '07': '阶段03-需求分析/07-需求分析（第三阶段）.md',
    '10': '阶段04-系统总体设计/10-系统总体设计（第四阶段）.md',
    '13': '阶段05-数据准备/13-数据准备（第五阶段）.md',
    '15': '阶段06-事件抽取与知识图谱/15-第6阶段任务书（事件抽取与知识图谱）.md',
    '16': '阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md',
    '00': '00-项目总览与索引.md',
}
ALT = [
    ('MySQL 恒六表（替代措辞）', [r'六张表', r'六表', r'不引入新表', r'不新增表']),
    ('历史证据保护（替代措辞）', [r'禁止物理删除', r'不可再用于新检索', r'历史证据', r'删除请求']),
    ('0 跳处理（替代措辞）', [r'未使用图谱扩展', r'不使用图谱扩展', r'图谱扩展', r'0 跳']),
    ('内容合规（替代措辞）', [r'模型分析', r'公开事实', r'不确定性', r'免责', r'风险提示']),
    ('用户角色与登录（替代措辞）', [r'普通用户', r'注册', r'匿名', r'权限', r'session']),
    ('候选不足 K（替代措辞）', [r'候选不足', r'候选.*不足', r'空缺.*未命中', r'分母仍为 K']),
    ('系统指标（替代措辞）', [r'P95', r'成功率', r'并发', r'响应时间']),
    ('抽取评测集两段式（替代措辞）', [r'两段式', r'互不重叠', r'只测一次', r'Dev', r'Test']),
]
for name, pats in ALT:
    print('=' * 92)
    print('【%s】' % name)
    for k, p in DOCS.items():
        t = open(os.path.join(ROOT, p), encoding='utf-8').read().splitlines()
        hits = []
        for i, ln in enumerate(t, 1):
            if any(re.search(x, ln) for x in pats):
                hits.append((i, ln.strip()))
        print('  [%s] %d 行' % (k, len(hits)))
        for i, ln in hits[:4]:
            print('      %s:%d| %s' % (k, i, ln[:230]))
