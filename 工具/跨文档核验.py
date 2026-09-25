# -*- coding: utf-8 -*-
"""
跨文档核验脚本（工作区通用）

用途：对本项目工作区里的 Markdown 文档做一遍机器可复现的一致性核验。
      第 3 阶段产出后首次编写（v2.2 修订），第 4 阶段及以后每次产出新文档后都应重跑。

用法：
    python 工具\跨文档核验.py                # 默认工作区 = 本脚本所在目录的上一级
    python 工具\跨文档核验.py <工作区路径>   # 指定其它路径

退出码：0 = 全部通过；1 = 存在失败项（明细在输出里）。

检查项：
    A 文档规模（行数按文本行计，不含文件末尾换行产生的空行）
    B 表格列数一致性（跳过 ``` 代码块）
    C 跨文档节号引用可解析性（《0N》§x.y 是否真的存在于被引文档中）
    D 《07》来源清单覆盖（按文档分别归属节号）
    E 需求追溯矩阵来源 ⊆ 条目"来源追溯"
    F §3.8 汇总表 与 §7.2 矩阵 的 FR 来源逐字一致
    G 需求编号覆盖（FR/UC/NFR）
    H 作废术语残留（裸 Evidence Recall 等）
    I 未限定范围的证据属性表述（H1 类）
    J 边界禁用词出现在"引入/使用"语境
    K 文档内提到的文件路径是否存在
    L 工作区内的 0N- 文档是否都登记在《00》索引里
    M 目录结构（阶段目录齐全、根目录只留入口与基线）
"""
import os, re, sys, glob, io

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

ROOT = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2026-09-25 起工作区按阶段分目录：入口《00》与基线《02》留在根目录，其余带号文档进 阶段NN-* 子目录。
STAGE_GLOB = os.path.join(ROOT, '阶段*')
STAGES = [d for d in sorted(glob.glob(STAGE_GLOB)) if os.path.isdir(d)]
LITDIR = os.path.join(ROOT, '阶段02-文献调研与开题')          # 《03》与文献资产
SECDIR = os.path.join(ROOT, '阶段04-系统总体设计', '_分节源文件')  # 《10》的分节源文件

CN = {'一':1,'二':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9,'十':10,
      '十一':11,'十二':12,'十三':13,'十四':14,'十五':15,'十六':16,'十七':17,'十八':18,'十九':19,'二十':20}

def docs():
    """根目录 + 每个阶段目录一层的 Markdown。分节源文件不参与核验（它们是《10》的输入，不是独立文档）。"""
    out = sorted(glob.glob(os.path.join(ROOT, '*.md')))
    for sd in STAGES:
        out += sorted(glob.glob(os.path.join(sd, '*.md')))
    return out

def load(p):
    with open(p, 'r', encoding='utf-8') as f:
        return f.read()

def nlines(t):
    n = len(t.split('\n'))
    return n - 1 if t.endswith('\n') else n

fails = []
def report(ok, label, detail=''):
    print('  [%s] %s%s' % ('OK ' if ok else 'FAIL', label, ('  ' + detail) if detail else ''))
    if not ok:
        fails.append(label)

_PATHS = docs()
_NAMES = [os.path.basename(p) for p in _PATHS]
DUP = sorted({n for n in _NAMES if _NAMES.count(n) > 1})
D = {os.path.basename(p): load(p) for p in _PATHS}
print('  参与核验的文档 %d 份：%s' % (len(D), '、'.join(sorted(D))))
report(not DUP, '文档文件名互不重名（否则会互相覆盖）', '重名 %s' % DUP)

# ---- A 规模 -------------------------------------------------------------
print('=' * 78); print('A 文档规模'); print('=' * 78)
for name in sorted(D):
    t = D[name]
    print('  %-46s %5d 行 %8d 字节 %7.1f KB' % (name, nlines(t), len(t.encode('utf-8')), len(t.encode('utf-8')) / 1024))

# ---- B 表格列数 ---------------------------------------------------------
print(); print('=' * 78); print('B 表格列数一致性'); print('=' * 78)
def table_blocks(t):
    res, cur, fence = [], [], False
    for L in t.split('\n'):
        if L.strip().startswith('```'):
            fence = not fence; continue
        if fence: continue
        s = L.strip()
        if s.startswith('|') and s.endswith('|'): cur.append(s)
        else:
            if len(cur) >= 2: res.append(cur)
            cur = []
    if len(cur) >= 2: res.append(cur)
    return res
total_blocks = 0
for name in sorted(D):
    tb = table_blocks(D[name])
    bad = sum(1 for b in tb if len({len(r.strip('|').split('|')) for r in b}) > 1)
    total_blocks += len(tb)
    if bad: report(False, '%s 表格列数' % name, '%d/%d 块错位' % (bad, len(tb)))
print('  合计 %d 个表格块' % total_blocks)
report(all(not any(len({len(r.strip('|').split('|')) for r in b}) > 1 for b in table_blocks(D[n])) for n in D),
       '所有表格列数一致')

# ---- C 跨文档节号引用可解析 --------------------------------------------
print(); print('=' * 78); print('C 跨文档节号引用可解析性'); print('=' * 78)
def sections(t):
    keys = set()
    for L in t.split('\n'):
        m = re.match(r'^##\s*([一二三四五六七八九十]+)、', L)
        if m and m.group(1) in CN: keys.add(str(CN[m.group(1)]))
        m = re.match(r'^#{3,4}\s*([0-9]+(?:\.[0-9]+)+)', L)
        if m:
            k = m.group(1); keys.add(k)
            parts = k.split('.')
            for i in range(1, len(parts)): keys.add('.'.join(parts[:i]))
        m = re.match(r'^#{3,4}\s*\d+\s+([A-Z])', L)   # 01/04 的无号小节
        if m: keys.add('附录' + m.group(1))
    return keys
SEC = {name: sections(D[name]) for name in D}
bynum = {}
for name in D:
    m = re.match(r'^(\d\d)-', name)
    if m: bynum[m.group(1)] = name
unres = []
for name in D:
    for mm in re.finditer(r'《(\d\d)》§(\d+(?:\.\d+)*)', D[name]):
        doc, sec = mm.group(1), mm.group(2)
        if doc not in bynum: continue
        keys = SEC[bynum[doc]]
        if not any(sec == k or sec.startswith(k + '.') or k.startswith(sec + '.') for k in keys):
            unres.append('%s -> 《%s》§%s' % (name, doc, sec))
print('  被引文档：%s' % ', '.join(sorted(bynum)))
if unres:
    for u in sorted(set(unres)): print('    !! %s' % u)
report(not unres, '所有《0N》§x.y 引用均可解析', '%d 处无法解析' % len(set(unres)))

# ---- D 《07》来源清单覆盖 ----------------------------------------------
print(); print('=' * 78); print('D 《07》来源清单覆盖'); print('=' * 78)
n7 = next((n for n in D if n.startswith('07-')), None)
if n7:
    t7 = D[n7]
    m = re.search(r'### 1\.3 需求来源清单(.*?)(?:\n---\n|\n## )', t7, re.S)
    if m:
        seg, body = m.group(1), t7.replace(m.group(1), '')
        rows = [r for r in seg.strip().split('\n') if r.strip().startswith('|')]
        keys = {(d, s) for d, s in re.findall(r'《(0[24])》§([0-9]+(?:\.[0-9]+)*)', seg)}
        cited = set()
        for mm in re.finditer(r'《(0[24])》§([0-9]+(?:\.[0-9]+)*)((?:[、，]§[0-9]+(?:\.[0-9]+)*|[～~-]§?[0-9]+(?:\.[0-9]+)*)*)', body):
            cited.add((mm.group(1), mm.group(2)))
            for num in re.findall(r'§([0-9]+(?:\.[0-9]+)*)', mm.group(3)): cited.add((mm.group(1), num))
            for num in re.findall(r'[～~-]([0-9]+(?:\.[0-9]+)*)', mm.group(3)): cited.add((mm.group(1), num))
        miss = sorted('《%s》§%s' % (d, s) for d, s in cited
                      if not any(d == kd and (s == k or s.startswith(k + '.') or k.startswith(s + '.')) for kd, k in keys))
        print('  来源清单 %d 行；一级来源 %d 个节号；正文引用 %d 个（文档, 节号）对' % (len(rows) - 2, len(keys), len(cited)))
        for x in miss: print('    !! 未覆盖 %s' % x)
        report(not miss, '正文引用的节都在来源清单中', '%d 处未覆盖' % len(miss))
    else:
        report(False, '未找到 §1.3 需求来源清单')

    # ---- E 矩阵 ⊆ 条目追溯 ----
    print(); print('=' * 78); print('E 追溯矩阵来源 ⊆ 条目"来源追溯"'); print('=' * 78)
    frs = {}
    for b in re.split(r'\n### ', t7):
        mm = re.match(r'(3\.\d)\s[^\n（]+（FR-(\d\d)）', b)
        if mm:
            tr = re.search(r'- 来源追溯：(.+)', b)
            frs['FR-' + mm.group(2)] = tr.group(1) if tr else ''
    mat = re.search(r'### 7\.2 需求追溯矩阵(.*?)\n## 八、', t7, re.S)
    mat = mat.group(1) if mat else ''
    prob = []
    for row in mat.strip().split('\n'):
        c = [x.strip() for x in row.strip('|').split('|')]
        if len(c) >= 3 and re.fullmatch(r'FR-0\d', c[0]) and c[0] in frs:
            trk = set(re.findall(r'§([0-9]+(?:\.[0-9]+)*)', frs[c[0]]))
            for s in re.findall(r'《0[24]》§([0-9]+(?:\.[0-9]+)*)', c[2]):
                if not any(s == x or s.startswith(x + '.') or x.startswith(s + '.') for x in trk):
                    prob.append('%s 矩阵 §%s' % (c[0], s))
    for p in prob: print('    !! %s' % p)
    report(not prob, '矩阵来源均在条目追溯范围内', '%d 处越界' % len(prob))

    # ---- F §3.8 vs §7.2 ----
    print(); print('=' * 78); print('F §3.8 汇总表 与 §7.2 矩阵 的 FR 来源一致'); print('=' * 78)
    s38 = re.search(r'### 3\.8 功能需求汇总表(.*?)\n---', t7, re.S)
    s38 = s38.group(1) if s38 else ''
    a, b2 = {}, {}
    for row in s38.strip().split('\n'):
        c = [x.strip() for x in row.strip('|').split('|')]
        if len(c) >= 5 and re.fullmatch(r'FR-0\d', c[0]): a[c[0]] = c[4]
    for row in mat.strip().split('\n'):
        c = [x.strip() for x in row.strip('|').split('|')]
        if len(c) >= 5 and re.fullmatch(r'FR-0\d', c[0]): b2[c[0]] = c[2]
    diff = [k for k in set(a) | set(b2) if a.get(k) != b2.get(k)]
    for k in diff: print('    !! %s\n       3.8=%s\n       7.2=%s' % (k, a.get(k), b2.get(k)))
    report(not diff, '两表 FR 来源逐字一致', '%d 处不一致' % len(diff))

    # ---- G 编号覆盖 ----
    print(); print('=' * 78); print('G 需求编号覆盖'); print('=' * 78)
    ids = set(re.findall(r'\| ((?:FR|UC|NFR)-0\d) \|', mat))
    want = {'FR-%02d' % i for i in range(1, 7)} | {'UC-%02d' % i for i in range(1, 8)} | {'NFR-%02d' % i for i in range(1, 7)}
    report(want <= ids, 'FR/UC/NFR 编号全部覆盖', '缺失 %s' % sorted(want - ids))

# ---- H 作废术语 ---------------------------------------------------------
print(); print('=' * 78); print('H 作废术语残留'); print('=' * 78)
TRACE = re.compile(r'更名为|原"|原为|原写|旧口径|已由|已于')
# 记录类文件（评审决议、交接记录、复核记录）会引用旧写法，属修订留痕，不参与口径残留检查
RECORDS = re.compile(r'^(05|06|08)-')
hits = []
for name in D:
    if RECORDS.match(name): continue
    for i, L in enumerate(D[name].split('\n'), 1):
        if re.search(r'(?<!Complete )Evidence Recall', L) and not TRACE.search(L):
            hits.append('%s:%d' % (name, i))
for h in hits: print('    !! %s' % h)
report(not hits, '无裸 Evidence Recall（不含修订留痕）', '%d 处' % len(hits))

# ---- I 证据属性口径 -----------------------------------------------------
print(); print('=' * 78); print('I 未限定范围的证据属性表述'); print('=' * 78)
bad = []
for name in D:
    if RECORDS.match(name): continue
    for i, L in enumerate(D[name].split('\n'), 1):
        s = L.strip()
        if TRACE.search(s) or re.match(r'^\|\s*v\d', s): continue
        if '每条关系' in s and ('source_doc_id' in s or 'source_chunk_id' in s) and not re.search(r'除 EVIDENCED_BY', s):
            bad.append('%s:%d' % (name, i))
        for p in [r'9 条核心关系都', r'每条核心关系的必需属性', r'每条核心关系都']:
            if re.search(p, s): bad.append('%s:%d' % (name, i))
for x in sorted(set(bad)): print('    !! %s' % x)
report(not bad, '证据属性表述均已限定范围（不含记录类文件）', '%d 处' % len(set(bad)))

# ---- J 禁用词 -----------------------------------------------------------
print(); print('=' * 78); print('J 边界禁用词（仅报告，供人工判断语境）'); print('=' * 78)
BAN = ['向量数据库', 'LangChain', 'LlamaIndex', 'Elasticsearch', 'Kafka', 'Kubernetes',
       '量化交易', '股票预测', '实时行情', '多模态', '语音', 'Agent']
for name in sorted(D):
    for i, L in enumerate(D[name].split('\n'), 1):
        for w in BAN:
            if w in L:
                ctx_ok = bool(re.search(r'不引入|不研究|不接入|不处理|不提供|不涉及|不得|禁止|不再|边界|除外|不同|vs|不按|不是|不称|never|明确不', L))
                if not ctx_ok:
                    print('    ?  %s:%d  「%s」  %s' % (name, i, w, L.strip()[:80]))
print('  （? 行需人工确认语境；出现"不引入/不研究"等否定语境的已自动过滤）')

# ---- K 路径存在性 -------------------------------------------------------
print(); print('=' * 78); print('K 文档内提到的文件路径是否存在'); print('=' * 78)
WHITE = re.compile(r'(输入|输出|模板)\.|^\{|^\d+_\d+_|^[A-Z]+-\d+_[A-Za-z]+\d+_|\.\.\.$|^X\.md$|_译文\.docx$|方向X_|^[^\\/]*\{[^}]*\}')
# 已在文档中声明、但尚未创建的产出（计划产出）。新增计划产出时在此登记，创建后请立即删除对应条目。
PLANNED = {'13-数据准备（第五阶段）.md', '验收第5阶段数据.py'}
# 归档目录（含其下一层子目录）
ARCH = glob.glob(os.path.join(LITDIR, '_归档_*'))
ARCH += [d for d in glob.glob(os.path.join(LITDIR, '_归档_*', '*')) if os.path.isdir(d)]
# 查找候选位置：根目录、阶段目录、文献资产目录、工具、图表、代码；分节源文件目录单列
SEARCH = [ROOT, LITDIR, os.path.join(LITDIR, '文献PDF'), os.path.join(LITDIR, '文献翻译'),
          os.path.join(ROOT, '工具'), os.path.join(ROOT, '图表'), os.path.join(ROOT, '代码'), SECDIR] + STAGES
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '代码', '*')) if os.path.isdir(d)]
# 旧路径别名：2026-09-25 目录重组前的写法。记录类文档（《05》《06》《08》）会逐字保留当时的路径，
# 那是留痕不是缺陷，因此旧前缀在这里映射到新位置再判定存在性，而不是去改写历史记录。
LEGACY = {'文献调研': LITDIR, '10-系统总体设计（第四阶段）': SECDIR}
# 重命名登记（旧名 → 新名）：《00》4.9 是对照表，记录类文档里也会出现旧名，那是历史留痕不是悬空路径。
# 新增改名时在此登记，并在《00》4.9 补一行。
RENAMED = {'11-第二轮复审判定与修订决议（2026-09-23）.md': '11-第4阶段复审判定与修订决议（2026-09-23）.md'}
def legacy_paths(tok):
    out = []
    for old, new in LEGACY.items():
        for sep in ('\\', '/'):
            if tok.startswith(old + sep):
                rest = tok[len(old) + 1:]
                out += [os.path.join(new, rest), os.path.join(new, os.path.basename(rest))]
    alt = RENAMED.get(os.path.basename(tok))
    if alt:
        for d in SEARCH + ARCH: out.append(os.path.join(d, alt))
    return out
miss = set()
for name in D:
    for tok in re.findall(r'`([^`\n]+\.(?:md|py|html|csv|docx|pdf|png|svg))`', D[name]):
        if tok.startswith('http') or WHITE.search(tok) or ' ' in tok: continue
        if os.path.basename(tok) in PLANNED: continue
        cands = []
        for d in SEARCH: cands.append(os.path.join(d, tok))
        for d in SEARCH + ARCH: cands.append(os.path.join(d, os.path.basename(tok)))
        cands += legacy_paths(tok)
        if not any(os.path.exists(c) for c in cands):
            miss.add('%s  提到  %s' % (name, tok))
for x in sorted(miss): print('    !! %s' % x)
report(not miss, '文档提到的文件均存在（含阶段目录、归档目录与旧路径别名）', '%d 处悬空' % len(miss))

# ---- L 索引登记 ---------------------------------------------------------
print(); print('=' * 78); print('L 工作区内的 0N- 文档是否都登记在《00》索引'); print('=' * 78)
n0 = next((n for n in D if n.startswith('00-')), None)
if n0:
    unreg = []
    for n in sorted(D):
        if n == n0 or not re.match(r'^\d\d-', n): continue
        if n[:-3] not in D[n0]:
            unreg.append(n)
    for u in unreg: print('    !! %s 未在《00》中出现' % u)
    report(not unreg, '带号文档均已登记', '%d 份未登记' % len(unreg))

# ---- M 目录结构 ---------------------------------------------------------
print(); print('=' * 78); print('M 目录结构（按阶段分目录）'); print('=' * 78)
WANT_STAGES = ['阶段01-选题与项目规划', '阶段02-文献调研与开题', '阶段03-需求分析',
               '阶段04-系统总体设计', '阶段05-数据准备']
have = {os.path.basename(d) for d in STAGES}
for s in WANT_STAGES:
    report(s in have, '阶段目录存在：%s' % s)
report(os.path.isdir(SECDIR), '《10》的分节源文件目录存在：阶段04-系统总体设计\\_分节源文件')
# 根目录只留入口《00》与基线《02》，其余带号文档一律进阶段目录
stray = sorted(n for n in os.listdir(ROOT)
               if re.match(r'^\d\d-.*\.md$', n) and not n.startswith(('00-', '02-')))
for s in stray: print('    !! 根目录仍留有带号文档：%s' % s)
report(not stray, '根目录只留《00》入口与《02》基线', '%d 份未归档' % len(stray))
# 每个带号文档必须落在某个阶段目录里（根目录的 00／02 除外）
misplaced = [n for n in D if re.match(r'^\d\d-', n) and n not in os.listdir(ROOT)
             and not any(os.path.exists(os.path.join(sd, n)) for sd in STAGES)]
report(not misplaced, '每份带号文档都落在阶段目录中', '%s' % misplaced)
# 10- 同名目录必须已消除
report(not os.path.isdir(os.path.join(ROOT, '10-系统总体设计（第四阶段）')),
       '已消除与《10》交付文档同名的目录')
# 旧的 文献调研\ 目录必须已迁走
report(not os.path.isdir(os.path.join(ROOT, '文献调研')),
       '旧的 文献调研\\ 目录已迁入阶段目录')

print(); print('=' * 78)
print('结论：%s' % ('全部通过' if not fails else '存在 %d 项失败：%s' % (len(fails), '；'.join(fails))))
print('=' * 78)
sys.exit(1 if fails else 0)
