# -*- coding: utf-8 -*-
import sys, os, re
sys.path.insert(0, r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *

DOC02 = ('# 项目执行总控文档 v3.2\n\n| 项 | 值 |\n|---|---|\n| 版本 | v3.2 |\n\n'
         '## 一、总则\n\n### 1.2 修订记录\n\n| 版本 | 日期 | 说明 |\n|---|---|---|\n| v3.2 | 2026-09-27 | 新 |\n\n'
         '## 五、边界\n\n### 5.1 边界一\n\n正文。\n')


def doc07(src, keep38=True, keep72=True):
    s = '# 07-需求分析\n\n## 一、总则\n\n### 1.3 需求来源清单\n\n| 序号 | 来源 | 说明 |\n|---|---|---|\n| 1 | %s | x |\n\n---\n\n' % src
    s += '## 三、功能需求\n\n'
    for i in range(1, 7):
        s += '### 3.%d 条目%d（FR-%02d）\n\n- 来源追溯：%s\n\n' % (i, i, i, src)
    if keep38:
        s += '### 3.8 功能需求汇总表\n\n| 编号 | 名称 | 优先级 | 备注 | 来源依据 |\n|---|---|---|---|---|\n'
        for i in range(1, 7):
            s += '| FR-%02d | a | 高 | x | %s |\n' % (i, src)
        s += '\n---\n\n'
    if keep72:
        s += '## 七、追溯\n\n### 7.2 需求追溯矩阵\n\n| 编号 | 名称 | 来源依据 | 验收 | 备注 |\n|---|---|---|---|---|\n'
        for i in range(1, 7):
            s += '| FR-%02d | a | %s | y | z |\n' % (i, src)
        for i in range(1, 8):
            s += '| UC-%02d | a | %s | y | z |\n' % (i, src)
        for i in range(1, 7):
            s += '| NFR-%02d | a | %s | y | z |\n' % (i, src)
    return s + '\n## 八、附\n\n结束。\n'


def mkd(keep38, keep72, extra_name=None, extra_txt=''):
    files = {'02-项目执行总控文档.md': DOC02,
             '交付物/07-设计与需求/需求分析/07-需求分析.md': doc07('《02》第5.1节', keep38, keep72),
             '00-项目总览与索引.md': '# 00\n\n- 02-项目执行总控文档\n- 07-需求分析\n'}
    for s in ['交付物/08-文献与开题/选题与项目规划', '交付物/08-文献与开题/文献调研与开题', '交付物/07-设计与需求/需求分析', '交付物/07-设计与需求/总体设计', '交付物/04-数据与知识图谱/数据准备']:
        files[s + '/y.md'] = '# y\n'
    files['交付物/07-设计与需求/总体设计/_分节源文件/x.md'] = '# x\n'
    if extra_name:
        files['交付物/07-设计与需求/需求分析/' + extra_name] = extra_txt
    return build('f_%s_%s_%s' % (keep38, keep72, extra_name), files)


def grab(out, keys):
    return [l.strip() for l in out.split('\n') if any(k in l for k in keys)]


for tag, k38, k72 in [('基线（3.8 与 7.2 都在）', True, True),
                      ('删掉 3.8 与 7.2 两个标题', False, False),
                      ('只删 7.2 标题', True, False)]:
    d = mkd(k38, k72)
    rc, out = run(d)
    print('== %s == exit=%d' % (tag, rc))
    for l in grab(out, ['正文引用的节都在来源清单', '矩阵来源均在条目追溯范围内', '两表 FR 来源逐字一致', 'FR/UC/NFR 编号全部覆盖']):
        print('    ', l)
    print()

print('== H：裸 Evidence Recall 放在不同编号的文件里 ==')
for name in ['05-记录.md', '14-审核报告.md', '17-审查报告.md', '19-产出.md']:
    d = mkd(True, True, name, '# x\n\n本系统采用 Evidence Recall 作为指标。\n')
    rc, out = run(d)
    r = grab(out, ['无裸 Evidence Recall'])
    print('    %-14s exit=%d  %s' % (name, rc, r[0] if r else '?'))
