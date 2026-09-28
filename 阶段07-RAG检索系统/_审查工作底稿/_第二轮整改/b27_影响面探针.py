# -*- coding: utf-8 -*-
"""B-26／B-27／B-29 的影响面测量：把"收紧判据"后**新增**的失败逐条列出来，据此决定修还是登记。

测量项：
  C-(a) 未知文档号 `《99》第x.y节`：现行实现静默 continue；收紧后是否真的有失败；
  C-(b) 链式引用（同一处 `第x节、第y节`）：现行只校验首个节号；全部校验后是否真的有失败；
  C-(c) 父节匹配（`k.startswith(sec + '.')` 这一支）：收紧后是否真的有失败；
  J    禁用词的"引入/使用语境"正判据（引入|使用|采用|接入|部署|上线|投产|实现|支持）＋否定词：
       现行只报告；收紧后现行的 10 处"?"行里有多少会判失败；
  B    表格列数：把行内代码（反引号）里的竖线剔除后再拆列，现行判定的 1 个错位块是否消失。

只读；结果打印到 stdout。
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
STAGES = [d for d in sorted(glob.glob(os.path.join(ROOT, "阶段*"))) if os.path.isdir(d)]
paths = sorted(glob.glob(os.path.join(ROOT, "*.md")))
for sd in STAGES:
    paths += sorted(glob.glob(os.path.join(sd, "*.md")))
D = {os.path.basename(p): open(p, encoding="utf-8").read() for p in paths}

CN = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
      '十': 10, '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16,
      '十七': 17, '十八': 18, '十九': 19, '二十': 20}


def sections(t):
    keys = set()
    for L in t.split("\n"):
        m = re.match(r'^##\s*([一二三四五六七八九十]+)、', L)
        if m and m.group(1) in CN:
            keys.add(str(CN[m.group(1)]))
        m = re.match(r'^#{3,4}\s*([0-9]+(?:\.[0-9]+)+)', L)
        if m:
            k = m.group(1)
            keys.add(k)
            parts = k.split('.')
            for i in range(1, len(parts)):
                keys.add('.'.join(parts[:i]))
        m = re.match(r'^#{3,4}\s*\d+\s+([A-Z])', L)
        if m:
            keys.add('附录' + m.group(1))
    return keys


SEC = {name: sections(D[name]) for name in D}
bynum = {}
for name in D:
    m = re.match(r'^(\d\d)-', name)
    if m:
        bynum[m.group(1)] = name

print("=" * 78)
print("B-26／B-27／B-29 影响面测量（工作区 %s）" % ROOT)
print("参与核验文档 %d 份；被引文档号 %s" % (len(D), ",".join(sorted(bynum))))
print("=" * 78)

# ---- C-(a) 未知文档号 ----
unknown = []
for name in D:
    for i, L in enumerate(D[name].split("\n"), 1):
        for doc, sec in re.findall(r'《(\d\d)》第(\d+(?:\.\d+)*)节', L):
            if doc not in bynum:
                unknown.append("%s:%d  《%s》第%s节" % (name, i, doc, sec))
print("\nC-(a) 未知文档号（现行静默 continue；收紧后判失败）：%d 处" % len(unknown))
for x in unknown[:20]:
    print("   !! %s" % x)

# ---- C-(b) 链式引用 ----
chain_bad, chain_total = [], 0
pat = re.compile(r'《(\d\d)》第(\d+(?:\.\d+)*)节((?:[、，]第\d+(?:\.\d+)*节)+)')
for name in D:
    for i, L in enumerate(D[name].split("\n"), 1):
        for doc, first, tail in pat.findall(L):
            nums = [first] + re.findall(r'第(\d+(?:\.\d+)*)节', tail)
            chain_total += len(nums)
            if doc not in bynum:
                continue
            keys = SEC[bynum[doc]]
            for sec in nums:
                if not any(sec == k or sec.startswith(k + '.') or k.startswith(sec + '.')
                           for k in keys):
                    chain_bad.append("%s:%d  《%s》第%s节（链式，首个=%s）"
                                     % (name, i, doc, sec, first))
print("\nC-(b) 链式引用：链上共 %d 个节号；**现行只校验首个**，全部校验后新增失败 %d 处"
      % (chain_total, len(chain_bad)))
for x in chain_bad[:30]:
    print("   !! %s" % x)

# ---- C-(c) 父节松匹配（k.startswith(sec + '.')）----
loose = []
for name in D:
    for i, L in enumerate(D[name].split("\n"), 1):
        for doc, sec in re.findall(r'《(\d\d)》第(\d+(?:\.\d+)*)节', L):
            if doc not in bynum:
                continue
            keys = SEC[bynum[doc]]
            strict = any(sec == k or sec.startswith(k + '.') for k in keys)
            loose_ok = any(k.startswith(sec + '.') for k in keys)
            if loose_ok and not strict:
                loose.append("%s:%d  《%s》第%s节（严格匹配失败、父节松匹配才过）"
                             % (name, i, doc, sec))
print("\nC-(c) 只靠父节松匹配（k.startswith(sec+'.')）才通过的引用：%d 处" % len(loose))
for x in loose[:30]:
    print("   !! %s" % x)

# ---- J 组：引入/使用语境的收紧判据 ----
BAN = ['向量数据库', 'LangChain', 'LlamaIndex', 'Elasticsearch', 'Kafka', 'Kubernetes',
       '量化交易', '股票预测', '实时行情', '多模态', '语音', 'Agent']
NEG = r'不引入|不研究|不接入|不处理|不提供|不涉及|不得|禁止|不再|边界|除外|不同|vs|不按|不是|不称|never|明确不'
POS = r'引入|使用|采用|接入|部署|上线|投产|实现|支持|依赖|基于|调用|选择|内置'
cur_hits, strict_hits = [], []
for name in sorted(D):
    for i, L in enumerate(D[name].split("\n"), 1):
        for w in BAN:
            if w in L:
                if not re.search(NEG, L):
                    cur_hits.append("%s:%d  「%s」" % (name, i, w))
                    if re.search(POS, L) and not re.search(r'(写成|误写|又称|旧称|原称|一栏|原为|改为|不准|不得再)', L):
                        strict_hits.append("%s:%d  「%s」" % (name, i, w))
print("\nJ 组：现行（无否定词即打印）命中 %d 处；**收紧为「有引入/使用类正向词且无否定词」**"
      "后仍命中 %d 处" % (len(cur_hits), len(strict_hits)))
for x in strict_hits:
    print("   !! %s" % x)

# ---- B 组：行内代码里的竖线 ----
def blocks(t):
    res, cur, fence = [], [], False
    for L in t.split("\n"):
        if L.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        s = L.strip()
        if s.startswith("|") and s.endswith("|"):
            cur.append(s)
        else:
            if len(cur) >= 2:
                res.append(cur)
            cur = []
    if len(cur) >= 2:
        res.append(cur)
    return res


bad_old = bad_new = 0
for name in D:
    for b in blocks(D[name]):
        old = {len(r.strip('|').split('|')) for r in b}
        masked = [re.sub(r'`[^`]*`', lambda m: m.group(0).replace('|', '\u0001'), r) for r in b]
        new = {len(r.strip('|').split('|')) for r in masked}
        if len(old) > 1:
            bad_old += 1
        if len(new) > 1:
            bad_new += 1
        if len(old) != len(new):
            print("   [块] %s：现行列数集合=%s；行内代码感知后=%s"
                  % (name, sorted(old), sorted(new)))
            for r in b:
                print("        cols_old=%d cols_new=%d  %s"
                      % (len(r.strip('|').split('|')),
                         len(re.sub(r'`[^`]*`', lambda m: m.group(0).replace('|', '\u0001'),
                                    r).strip('|').split('|')), r[:150]))
print("\nB 组：现行拆列判「块内不一致」%d 块；剔除行内代码里的竖线后 %d 块" % (bad_old, bad_new))
print("=" * 78)
