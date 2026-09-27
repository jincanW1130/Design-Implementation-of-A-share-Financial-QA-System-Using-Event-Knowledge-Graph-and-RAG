# -*- coding: utf-8 -*-
"""A1 登记一致性：把《00》第四节 4.1～4.10 的文件地图与磁盘实际内容逐条对照。只读。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
t00 = open(os.path.join(ROOT, '00-项目总览与索引.md'), encoding='utf-8').read()

print('ROOT =', ROOT)
print('=' * 78)
print('A1-1 《00》第四节各小节抽取的路径/文件名 -> 存在性判定')
print('=' * 78)
sec4 = t00[t00.index('## 四、文件地图'):t00.index('## 五、冻结口径速查')]
parts = re.split(r'\n### (4\.\d+) ', sec4)
subs = {}
for i in range(1, len(parts) - 1, 2):
    subs[parts[i]] = parts[i + 1]
print('第四节小节：', sorted(subs))
SEARCH = [ROOT]
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in ('.git', '__pycache__', '.idea')]
    SEARCH.append(dp)
SEARCH = list(dict.fromkeys(SEARCH))


def exists(tok):
    tok = tok.strip().strip('`').replace('/', '\\')
    if not tok:
        return None
    for base in SEARCH:
        if os.path.exists(os.path.join(base, tok)):
            return os.path.join(base, tok)
    return None


problems = []
for k in sorted(subs):
    toks = re.findall(r'`([^`\n]+)`', subs[k])
    cand = []
    for t in toks:
        tt = t.strip()
        if not tt or tt.startswith('--') or ' ' in tt:
            continue
        if re.search(r'\.(md|csv|json|jsonl|html|py|txt|cypher|pdf|docx|sha256|index)$', tt) or tt.endswith('\\') or '\\' in tt:
            cand.append(tt)
    for t in cand:
        if exists(t) is None:
            problems.append((k, t))
print()
for k, t in problems:
    print('  !! [%s] 登记了但磁盘上找不到：%s' % (k, t))
print('  小结：登记但不存在 %d 处' % len(problems))
print()
print('=' * 78)
print('A1-2 反向：实际目录内容 -> 是否被《00》登记')
print('=' * 78)
WATCH = ['阶段01-选题与项目规划', '阶段02-文献调研与开题', '阶段03-需求分析',
         '阶段04-系统总体设计', '阶段05-数据准备', '阶段06-事件抽取与知识图谱',
         '代码', '图表', '工具']
SKIP_HINT = ('\\数据集\\', '\\_试跑', '\\_归档', '\\文献PDF', '\\文献翻译',
             '\\__pycache__', '\\_抽取缓存', '\\_审查工作底稿')
unreg = []
for rel in WATCH:
    d = os.path.join(ROOT, rel)
    for dp, dn, fn in os.walk(d):
        dn[:] = [x for x in dn if x != '__pycache__']
        if any(h in dp + '\\' for h in SKIP_HINT):
            continue
        for f in sorted(fn):
            p = os.path.join(dp, f)
            r = os.path.relpath(p, ROOT)
            if os.path.basename(r) in t00 or r in t00 or r.replace('\\', '/') in t00:
                continue
            unreg.append(r)
print('  未在《00》任何位置出现的文件（已排除数据集/试跑/归档/文献原文/本底稿）：')
for r in unreg:
    print('    ?? %s' % r)
print('  小结：未登记 %d 份' % len(unreg))
print()
print('=' * 78)
print('A1-3 核验脚本 M 项复算：根目录带号文档')
print('=' * 78)
stray = sorted(n for n in os.listdir(ROOT)
               if re.match(r'^\d\d-.*\.md$', n) and not n.startswith(('00-', '02-')))
print('  根目录 .md：', sorted(n for n in os.listdir(ROOT) if n.endswith('.md')))
print('  违规带号文档：', stray if stray else '无')
print('  根目录全部条目：')
for n in sorted(os.listdir(ROOT)):
    print('    -', n)
print()
print('=' * 78)
print('A1-4 《00》第三节文档编号表 vs 实际文件')
print('=' * 78)
sec3 = t00[t00.index('## 三、三套编号体系'):t00.index('## 四、文件地图')]
rows = re.findall(r'^\|\s*(\d\d)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*$', sec3, re.M)
print('  第三节文档编号表 %d 行：' % len(rows))
allmd = []
for dp, dn, fn in os.walk(ROOT):
    dn[:] = [d for d in dn if d not in ('.git', '__pycache__', '.idea')]
    for f in fn:
        if f.endswith('.md'):
            allmd.append(os.path.relpath(os.path.join(dp, f), ROOT))
for num, name, loc in rows:
    name = name.strip().strip('《》')
    hits = [m for m in allmd if os.path.basename(m).startswith(num + '-')]
    declared = loc.strip().strip('`')
    ok = False
    for h in hits:
        if declared == '根目录':
            ok = (os.path.dirname(h) == '')
        else:
            ok = h.startswith(declared)
        if ok:
            break
    print('    %s | 声明=%s | 实际=%s | %s' % (num, declared, hits if hits else 'NOT FOUND', 'OK' if ok else '!!'))
print()
print('=' * 78)
print('A1-5 文献资产口径复算')
print('=' * 78)
pdf = os.path.join(ROOT, '阶段02-文献调研与开题', '文献PDF')
files = sorted(os.listdir(pdf)) if os.path.isdir(pdf) else []
print('  文献PDF 目录实际文件数：', len(files))
print('  其中 PDF：', len([f for f in files if f.lower().endswith('.pdf')]))
print('  其中 DOCX：', len([f for f in files if f.lower().endswith('.docx')]))
for f in files:
    print('    -', f)
trans = os.path.join(ROOT, '阶段02-文献调研与开题', '文献翻译')
tf = sorted(os.listdir(trans)) if os.path.isdir(trans) else []
print('  文献翻译 目录实际文件数：', len(tf))
for f in tf:
    print('    -', f)
arch = os.path.join(ROOT, '阶段02-文献调研与开题', '_归档_20260923_文献调研过程文件')
af = []
if os.path.isdir(arch):
    for dp, dn, fn in os.walk(arch):
        for f in fn:
            af.append(os.path.relpath(os.path.join(dp, f), arch))
print('  归档目录文件数（递归）：', len(af))
for f in sorted(af):
    print('    -', f)

print()
print('=' * 78)
print('A1-6 《00》4.7 登记的图谱导出物 vs 实际目录内容')
print('=' * 78)
for sub in ['v2.1', 'v2.1_v1_2']:
    d = os.path.join(ROOT, '阶段06-事件抽取与知识图谱', '图谱导出', sub)
    print('  目录 %s 实际内容：' % sub)
    for f in sorted(os.listdir(d)):
        print('    %-24s 在《00》全文中%s' % (f, '出现' if f in t00 else '**未出现**'))
print()
print('=' * 78)
print('A1-7 关键文件是否在《00》全文中被点名')
print('=' * 78)
for rel in ['代码\\README.md', '代码\\数据准备\\README.md', '代码\\抽取与图谱\\README.md',
            '代码\\抽取与图谱\\config.py', '代码\\抽取与图谱\\run_all.py',
            '14-前五阶段审核报告（2026-09-25）.md',
            '15-第6阶段任务书（事件抽取与知识图谱）.md',
            '16-事件抽取与知识图谱（第六阶段）.md',
            '图谱导出\\v2.1_v1_2\\', '图谱导出\\v2.1\\',
            '抽取评测集', '自动标注', '第三方复核']:
    variants = [rel, rel.replace('\\', '/'), rel.rstrip('\\'), os.path.splitext(rel)[0]]
    hit = any(v in t00 for v in variants)
    print('  %-46s %s' % (rel, '出现（%s）' % [v for v in variants if v in t00][:1] if hit else '**未出现**'))

print()
print('=' * 78)
print('A1-8 核验脚本 PLANNED 集合的“已落盘但未清理”复算（编写约定 5）')
print('=' * 78)
psrc = open(os.path.join(ROOT, '工具', '跨文档核验.py'), encoding='utf-8').read()
i = psrc.index('PLANNED = {')
j = psrc.index('\n}', i)
body = psrc[i:j]
live, dead = [], []
for ln in body.splitlines()[1:]:
    tgt = live if not ln.strip().startswith('#') else dead
    tgt += re.findall(r"'([^'\n]+)'", ln)
pl = sorted(set(live))
pl_dead = sorted(set(dead))
print('  PLANNED 块里的【生效】条目 %d 个；被注释掉的条目 %d 个：%s' % (len(pl), len(pl_dead), pl_dead))
print('  PLANNED 条目 %d 个：' % len(pl))
for t in pl:
    t2 = t.replace('/', '\\')
    hit = None
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in ('.git', '__pycache__', '.idea')]
        if '\\' in t2:
            cand = os.path.join(ROOT, t2)
            hit = cand if os.path.exists(cand) else None
        else:
            if os.path.basename(t2) in fn:
                hit = os.path.join(dp, os.path.basename(t2))
        if hit:
            break
    print('    %-42s 磁盘上%s' % (t, ('存在 → ' + os.path.relpath(hit, ROOT)) if hit else '**不存在**'))
readme = open(os.path.join(ROOT, '工具', 'README.md'), encoding='utf-8').read()
m = re.search(r'当前 `PLANNED` 登记的是第 6 阶段的 (\d+) 项计划产出', readme)
print('  《工具\\README.md》声称 PLANNED = %s 项；脚本实际 = %d 项' % (m.group(1) if m else '（未找到该句）', len(pl)))

print()
print('=' * 78)
print('A1-9 《00》第六节 待办与延后项 逐行（供 A4 汇总）')
print('=' * 78)
sec6 = t00[t00.index('## 六、待办与延后项'):t00.index('## 七、下一步')]
for i, ln in enumerate(sec6.splitlines(), 1):
    if ln.startswith('|') and '---' not in ln:
        print('  %s' % ln.strip()[:300])
