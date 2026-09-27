# -*- coding: utf-8 -*-
"""A4 遗留缺陷与开放项：把散落在文档／工作底稿里的待办、延后、已知缺口逐条抽出并带出处。只读。"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))


def show(path, start, end, label=''):
    p = os.path.join(ROOT, path)
    lines = open(p, encoding='utf-8').read().splitlines()
    print('=' * 96)
    print('%s  [%s] 第 %d～%d 行' % (label, path, start, end))
    print('-' * 96)
    for i in range(start, min(end, len(lines)) + 1):
        print('%s:%d| %s' % (os.path.basename(path), i, lines[i - 1][:400]))
    print()


print('#' * 96)
print('A4-1 《00》第六节 待办与延后项（全部行）')
show('00-项目总览与索引.md', 236, 259, '00 第六节')

print('#' * 96)
print('A4-2 《16》第八节 已知限制与证据不足清单（各小节首行 + 对下游后果行）')
p16 = os.path.join(ROOT, '阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md')
l16 = open(p16, encoding='utf-8').read().splitlines()
for i, ln in enumerate(l16[565:703], 566):
    if re.match(r'^###{3,4} 8\.', ln) or re.search(r'第 10 阶段|必须写进题量规划|不得|不是人工|未人工复核|未做', ln):
        print('16:%d| %s' % (i, ln[:400]))
print()

print('#' * 96)
print('A4-3 工作底稿：对照_未验证清单.md（逐字）')
print(open(os.path.join(ROOT, '代码/抽取与图谱/_全量/v2.1_v1_2/对照_未验证清单.md'), encoding='utf-8').read())

print('#' * 96)
print('A4-4 工作底稿：对照_新增错误_人工复核.md 的 8.1（逐字）')
t = open(os.path.join(ROOT, '代码/抽取与图谱/_全量/v2.1_v1_2/对照_新增错误_人工复核.md'), encoding='utf-8').read()
i, j = t.find('### 8.1'), t.find('### 8.2')
print(t[i:j])

print('#' * 96)
print('A4-5 两份 v1.2 报告的「未做到／不确定」段（逐字）')
for p, a, b in [('代码/抽取与图谱/_全量/_默认口径切换/本任务报告.md', '## ⑤ 未做到／不确定', '## ⑥'),
                ('代码/抽取与图谱/_全量/_默认口径切换/第二步_登记与收口/本任务报告.md', '## ⑥ 未做到／不确定', '## ⑦')]:
    tt = open(os.path.join(ROOT, p), encoding='utf-8').read()
    print('-' * 96)
    print(p)
    print(tt[tt.index(a):tt.index(b)])

print('#' * 96)
print('A4-6 v1.2 的 verify.json 复现性字段')
j = json.load(open(os.path.join(ROOT, '代码/抽取与图谱/_全量/v2.1_v1_2/verify.json'), encoding='utf-8'))
print(json.dumps(j['reproducibility'], ensure_ascii=False, indent=1))
print('《16》是否登记该字段为 false：')
for i, ln in enumerate(l16, 1):
    if 'identical_across_runs' in ln:
        print('  16:%d| %s' % (i, ln.strip()[:300]))

print()
print('#' * 96)
print('A4-7 已被后续工作取代、但原文仍在的旧条目（机械定位）')
markers = [
    ('对照_未验证清单.md 第 7 条（v1.2 读数未回填） -> 已由第二步/《16》v1.7 取代',
     '代码/抽取与图谱/_全量/v2.1_v1_2/对照_未验证清单.md', 'v1.2 的读数尚未回填到任何正式登记文件'),
    ('对照_未验证清单.md 第 8 条（不能作为交付物） -> EVT-1036 已修（write_graph 退出码 0）',
     '代码/抽取与图谱/_全量/v2.1_v1_2/对照_未验证清单.md', '不能直接作为交付物'),
    ('对照报告 §8.1（必须处理：EVT-1036） -> 已修',
     '代码/抽取与图谱/_全量/v2.1_v1_2/对照报告.md', '必须处理'),
    ('本轮交付报告 §⑦-1（硬约束失败未修） -> 已修',
     '代码/抽取与图谱/_全量/v2.1_v1_2/本轮交付报告.md', '硬约束失败未修'),
    ('本轮交付报告 §⑦-5（T5 判据待更新） -> 第二步已重锚',
     '代码/抽取与图谱/_全量/v2.1_v1_2/本轮交付报告.md', '需要在切换时一并更新'),
]
for label, path, needle in markers:
    p = os.path.join(ROOT, path)
    lines = open(p, encoding='utf-8').read().splitlines()
    hit = [(i, ln) for i, ln in enumerate(lines, 1) if needle in ln]
    print('  * %s' % label)
    for i, ln in hit:
        print('      %s:%d| %s' % (os.path.basename(path), i, ln.strip()[:240]))
print()
print('  取代动作的落地证据（《16》修订记录 v1.7 / §6.2）：')
for i, ln in enumerate(l16, 1):
    if 'issuer_participation_dropped' in ln and ('退出码' in ln or 'count' in ln or '写边前' in ln):
        print('      16:%d| %s' % (i, ln.strip()[:300]))
print()
print('  未取代的旧条目对照（《15》正文与《16》现行口径）：')
p15 = os.path.join(ROOT, '阶段06-事件抽取与知识图谱/15-第6阶段任务书（事件抽取与知识图谱）.md')
l15 = open(p15, encoding='utf-8').read().splitlines()
for i, ln in enumerate(l15, 1):
    if ('图谱导出\\v2.1\\' in ln and 'v2.1_v1_2' not in ln) or 'stage6-extract-v1.1' in ln:
        print('      15:%d| %s' % (i, ln.strip()[:300]))
