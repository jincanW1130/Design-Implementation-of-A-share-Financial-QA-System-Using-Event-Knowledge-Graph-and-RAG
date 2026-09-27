# -*- coding: utf-8 -*-
"""A3 补充：把 A3 与 A3b 两次扫描的命中行数汇总成「口径 × 文档」覆盖矩阵。只读。"""
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))


def counts(path):
    s = open(path, encoding='utf-8').read()
    out = []
    for blk in re.split(r'={90,}', s):
        m = re.search(r'【(.+?)】', blk)
        if not m:
            continue
        c = dict(re.findall(r'\[(\d\d)\] (?:命中 )?(\d+) 行', blk))
        out.append((m.group(1), c))
    return out


A = dict(counts(os.path.join(HERE, 'raw_A3_口径一致性.txt')))
B = dict(counts(os.path.join(HERE, 'raw_A3b_零命中复核.txt')))
DOCS = ['01', '02', '04', '07', '10', '13', '15', '16', '00']
print('A3/A3b 覆盖矩阵（单元格 = 第一轮命中行数 ／ 第二轮替代措辞命中行数；“-”= 第一次扫描未含该项）')
print()
print('| 口径项 | ' + ' | '.join(DOCS) + ' |')
print('| --- | ' + ' | '.join(['---'] * len(DOCS)) + ' |')
for name, c in A.items():
    alt_name = None
    for b in B:
        if name.split('（')[0][:4] in b:
            alt_name = b
    row = []
    for d in DOCS:
        a = c.get(d, '0')
        b_ = B[alt_name].get(d, '-') if alt_name else '-'
        row.append('%s / %s' % (a, b_))
    print('| %s | %s |' % (name, ' | '.join(row)))
print()
print('说明：第二列只在 A3b 里对少数零命中项做了替代措辞复核，其余显示 “-”。')
