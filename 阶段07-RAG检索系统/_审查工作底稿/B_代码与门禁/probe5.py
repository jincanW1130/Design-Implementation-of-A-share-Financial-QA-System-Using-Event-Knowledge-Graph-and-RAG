# -*- coding: utf-8 -*-
import os, re, glob
ROOT = r'C:\Users\15129\Desktop\毕业设计'
BS = chr(92)
STAGES = [d for d in sorted(glob.glob(os.path.join(ROOT, '阶段*'))) if os.path.isdir(d)]
paths = sorted(glob.glob(os.path.join(ROOT, '*.md')))
for sd in STAGES:
    paths += sorted(glob.glob(os.path.join(sd, '*.md')))
D = {os.path.basename(p): open(p, encoding='utf-8').read() for p in paths}
out = []
cur = 'v3.2'
CITE_REF = re.compile(r'《02[^》]*》[^《]{0,30}?(v\d+\.\d+)')
DECL = re.compile(r'依据|上游|需求来源')
SKIP = re.compile(r'^(?:02|05|06|08|11)-')
MARKS = ('版本链', '未改变', '不影响', '历史', '留痕')
out.append('== 真实工作区 N2 扫到的依据声明，逐条给出去重/豁免理由 ==')
n = 0
for name in sorted(D):
    if SKIP.match(name):
        continue
    for i, L in enumerate(D[name].split('\n'), 1):
        if not DECL.search(L):
            continue
        for ver in dict.fromkeys(CITE_REF.findall(L)):
            n += 1
            if ver == cur:
                why = '版本=当前'
            elif cur in L:
                why = '同行提到当前版本 %s' % cur
            else:
                hit = [m for m in MARKS if m in L]
                why = ('同行含标记 %s' % hit) if hit else '★无豁免→应判过期'
            out.append('  %2d %s:%d  %s  → %s' % (n, name, i, ver, why))
out.append('  合计 %d 处' % n)
out.append('')
out.append('== 不检查的扩展名（.json/.jsonl/.txt/.cypher/...）按 K 同一套搜索目录判定的悬空 token ==')
LIT = os.path.join(ROOT, '阶段02-文献调研与开题')
SEC = os.path.join(ROOT, '阶段04-系统总体设计', '_分节源文件')
SEARCH = [ROOT, LIT, os.path.join(LIT, '文献PDF'), os.path.join(LIT, '文献翻译'),
          os.path.join(ROOT, '工具'), os.path.join(ROOT, '图表'), os.path.join(ROOT, '代码'), SEC] + STAGES
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '代码', '*')) if os.path.isdir(d)]
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '阶段05-数据准备', '数据集', '*')) if os.path.isdir(d)]
SEARCH += [os.path.join(ROOT, '阶段05-数据准备', '_试跑')]
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '阶段05-数据准备', '数据集', '抽取评测集', '*')) if os.path.isdir(d)]
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '阶段06-事件抽取与知识图谱', '图谱导出', '*')) if os.path.isdir(d)]
ARCH = glob.glob(os.path.join(LIT, '_归档_*'))
ARCH += [d for d in glob.glob(os.path.join(LIT, '_归档_*', '*')) if os.path.isdir(d)]
WHITE = re.compile(r'(输入|输出|模板)\.|^\{|^\d+_\d+_|^[A-Z]+-\d+_[A-Za-z]+\d+_|\.\.\.$|…|^X\.md$|_译文\.docx$|方向X_|^[^' + BS + BS + r'/]*\{[^}]*\}')
EXT = re.compile(r'`([^`\n]+\.(?:json|jsonl|txt|cypher|ya?ml|log|parquet|db|ndjson))`')
miss = {}
for name in D:
    for tok in EXT.findall(D[name]):
        if tok.startswith('http') or WHITE.search(tok) or ' ' in tok:
            continue
        cands = [os.path.join(d, tok) for d in SEARCH]
        if BS not in tok and '/' not in tok:
            cands += [os.path.join(d, os.path.basename(tok)) for d in SEARCH + ARCH]
        if not any(os.path.exists(c) for c in cands):
            miss.setdefault(tok, []).append(name)
out.append('  按 K 的搜索目录仍找不到的（K 完全不会报的）token：%d 个' % len(miss))
for k, v in sorted(miss.items())[:60]:
    out.append('    %-56s <- %s' % (k, '、'.join(sorted(set(v))[:3])))
open(r'C:\Users\15129\AppData\Local\Temp\re7_B\probe5.txt', 'w', encoding='utf-8').write('\n'.join(out))
print('done')
