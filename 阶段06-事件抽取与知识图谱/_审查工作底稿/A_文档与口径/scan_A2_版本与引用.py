# -*- coding: utf-8 -*-
"""A2 版本与引用一致性：文档头部版本三处对齐 + 跨文档引用（含中文数字节号）落点核验。只读。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
DOCS = {
    '00': '00-项目总览与索引.md',
    '01': '阶段01-选题与项目规划/01-项目总体方案（导师审阅版）.md',
    '02': '02-项目执行总控文档.md',
    '03': '阶段02-文献调研与开题/03-精选文献库（22篇）.md',
    '04': '阶段02-文献调研与开题/04-开题报告.md',
    '05': '阶段02-文献调研与开题/05-评审修订决议（2026-09-23）.md',
    '06': '阶段02-文献调研与开题/06-第二阶段完成与交接（2026-09-23）.md',
    '07': '阶段03-需求分析/07-需求分析（第三阶段）.md',
    '08': '阶段03-需求分析/08-跨文档一致性复核与修订（2026-09-23）.md',
    '09': '阶段04-系统总体设计/09-第4阶段任务书（系统总体设计）.md',
    '10': '阶段04-系统总体设计/10-系统总体设计（第四阶段）.md',
    '11': '阶段04-系统总体设计/11-第4阶段复审判定与修订决议（2026-09-23）.md',
    '12': '阶段05-数据准备/12-第5阶段任务书（数据准备）.md',
    '13': '阶段05-数据准备/13-数据准备（第五阶段）.md',
    '14': '阶段05-数据准备/14-前五阶段审核报告（2026-09-25）.md',
    '15': '阶段06-事件抽取与知识图谱/15-第6阶段任务书（事件抽取与知识图谱）.md',
    '16': '阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md',
}
TEXT = {k: open(os.path.join(ROOT, p), encoding='utf-8').read() for k, p in DOCS.items()}

print('=' * 96)
print('A2-1 每份文档的「标题版本／版本字段／修订记录末行」')
print('=' * 96)
for k in sorted(TEXT):
    lines = TEXT[k].splitlines()
    title = lines[0] if lines else ''
    v_title = re.findall(r'v\d+\.\d+', title)
    v_field = re.findall(r'\|\s*版本\s*\|\s*([^|]*)', TEXT[k])
    v_field_ver = [re.search(r'v\d+\.\d+', x).group(0) for x in v_field if re.search(r'v\d+\.\d+', x)]
    hdr = [l for l in lines if re.match(r'^#+\s*(修订记录|第十二节|.*修订记录)', l)]
    rev = []
    for l in lines:
        m = re.match(r'^\|\s*(v\d+\.\d+)\s*\|\s*(\d{4}-\d{2}-\d{2})', l)
        if m:
            rev.append((m.group(1), m.group(2)))
    rev_note = [(m.group(1), m.group(2)) for m in re.finditer(r'\*\*(v\d+\.\d+)（(\d{4}-\d{2}-\d{2})', TEXT[k])]
    print('  [%s] %s' % (k, DOCS[k]))
    print('      标题版本：%s' % (v_title or '（标题无版本号）'))
    print('      版本字段：%s' % (v_field_ver or '（无 |版本| 字段）'))
    print('      修订记录表行：%s' % (['%s@%s' % x for x in rev] or '（无表格行）'))
    print('      修订记录加粗行：%s' % (['%s@%s' % x for x in rev_note] or '（无）'))
    print('      修订记录相关标题：%s' % (hdr or '（无）'))

print()
print('=' * 96)
print('A2-2 跨文档引用落点核验（《0N》第x.y节 与 《0N》第<中文数字>节，严格匹配标题）')
print('=' * 96)
CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
      '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17,
      '十八': 18, '十九': 19, '二十': 20}
ANCH = {}
for k, t in TEXT.items():
    a = set()
    for L in t.splitlines():
        m = re.match(r'^##\s*([一二三四五六七八九十]+)、', L)
        if m and m.group(1) in CN:
            a.add(str(CN[m.group(1)]))
        m = re.match(r'^#{3,4}\s*([0-9]+(?:\.[0-9]+)*)', L)
        if m:
            a.add(m.group(1))
    ANCH[k] = a
unres = []
cnt = {}
for k, t in TEXT.items():
    for m in re.finditer(r'《(\d\d)》第(\d+(?:\.\d+)*)节', t):
        d, s = m.group(1), m.group(2)
        if d not in ANCH:
            continue
        cnt[d] = cnt.get(d, 0) + 1
        if s not in ANCH[d] and not any(x.startswith(s + '.') for x in ANCH[d]):
            unres.append('%s -> 《%s》第%s节（该文档实际节号：%s）' % (DOCS[k], d, s, sorted(ANCH[d])))
    for m in re.finditer(r'《(\d\d)》第([一二三四五六七八九十]+)节', t):
        d, s = m.group(1), m.group(2)
        if d not in ANCH or s not in CN:
            continue
        cnt[d] = cnt.get(d, 0) + 1
        if str(CN[s]) not in ANCH[d]:
            unres.append('%s -> 《%s》第%s节（=第%d节，该文档实际节号：%s）' % (DOCS[k], d, s, CN[s], sorted(ANCH[d])))
print('  被引次数（按被引文档）：', dict(sorted(cnt.items(), key=lambda x: -x[1])))
print()
print('  无法解析的引用 %d 处：' % len(unres))
for u in sorted(set(unres)):
    print('    !! %s' % u)

print()
print('=' * 96)
print('A2-3 被引用方/引用方版本声明抽查（《02》外部引用 + 各文档依据行版本号）')
print('=' * 96)
for k, t in TEXT.items():
    if k in ('00', '02'):
        continue
    for i, L in enumerate(t.splitlines(), 1):
        if re.search(r'《02[^》]*》[^|]{0,24}v\d+\.\d+', L) and re.search(r'依据|上游|来源', L):
            ver = re.findall(r'《02[^》]*》[^|]{0,24}(v\d+\.\d+)', L)
            print('  %s:%d 引用《02》版本=%s' % (k, i, ver))
