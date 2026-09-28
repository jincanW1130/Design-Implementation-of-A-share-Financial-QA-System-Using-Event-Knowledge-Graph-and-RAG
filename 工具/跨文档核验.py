# -*- coding: utf-8 -*-
"""
跨文档核验脚本（工作区通用）

用途：对本项目工作区里的 Markdown 文档做一遍机器可复现的一致性核验。
      第 3 阶段产出后首次编写（v2.2 修订），第 4 阶段及以后每次产出新文档后都应重跑。

用法：
    python 工具\跨文档核验.py                     # 默认工作区 = 本脚本所在目录的上一级
    python 工具\跨文档核验.py <工作区路径>        # 指定其它路径
    python 工具\跨文档核验.py --strict-citations  # N2 的过期引用按失败处理（默认只报告）

退出码：0 = 全部通过；1 = 存在失败项（明细在输出里；--strict-citations 下含 N2 的过期引用）。

检查项：
    A 文档规模（行数按文本行计，不含文件末尾换行产生的空行）
    B 表格列数一致性（跳过 ``` 代码块）
    C 跨文档节号引用可解析性（《0N》第x.y节 是否真的存在于被引文档中）
    D 《07》来源清单覆盖（按文档分别归属节号）
    E 需求追溯矩阵来源 ⊆ 条目"来源追溯"
    F 第3.8节 汇总表 与 第7.2节 矩阵 的 FR 来源逐字一致
    G 需求编号覆盖（FR/UC/NFR）
    H 作废术语残留（裸 Evidence Recall 等）
    I 未限定范围的证据属性表述（H1 类）
    J 边界禁用词出现在"引入/使用"语境
    K 文档内提到的文件路径是否存在
    L 工作区内的 0N- 文档是否都登记在《00》索引里
    M 目录结构（阶段目录齐全、根目录只留入口与基线）
    N1 《02》自身三处版本号一致（标题末尾／版本字段／第1.2节 修订记录末行）
    N2 其余文档引用《02》的版本是否等于当前基线（默认只报告；--strict-citations 门禁）
"""
import os, re, sys, glob, io, fnmatch

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

# 参数：第一个非 `--` 参数 = 工作区根目录；--strict-citations 把 N2 的过期引用转为门禁（默认只报告）。
FLAGS = {a for a in sys.argv[1:] if a.startswith('--')}
UNKNOWN = sorted(FLAGS - {'--strict-citations'})
if UNKNOWN:
    print('未知参数：%s' % '、'.join(UNKNOWN))
    print('用法：python 工具\\跨文档核验.py [工作区路径] [--strict-citations]')
    sys.exit(2)
STRICT_CITATIONS = '--strict-citations' in FLAGS
POSITIONAL = [a for a in sys.argv[1:] if not a.startswith('--')]
ROOT = os.path.abspath(POSITIONAL[0]) if POSITIONAL else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

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
def report(ok, label, detail='', gating=True):
    """gating=False 的项（如 N2 的默认模式）只打印结果，不写入 fails，因而不影响退出码。"""
    print('  [%s] %s%s' % ('OK ' if ok else ('FAIL' if gating else 'WARN'), label,
                           ('  ' + detail) if detail else ''))
    if not ok and gating:
        fails.append(label)

_PATHS = docs()
_NAMES = [os.path.basename(p) for p in _PATHS]
DUP = sorted({n for n in _NAMES if _NAMES.count(n) > 1})
D = {os.path.basename(p): load(p) for p in _PATHS}
print('  参与核验的文档 %d 份：%s' % (len(D), '、'.join(sorted(D))))
print('  引用版本审计：%s' % ('门禁（--strict-citations：N2 的过期引用计入退出码）' if STRICT_CITATIONS
                              else '只报告（默认：N2 的过期引用不改变退出码，加 --strict-citations 转为门禁）'))
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
# 2026-09-28（第二轮复审 B-27 整改，只动这两处判据；其余不变）：
#   ① **未知文档号不再静默跳过**：此前 `《99》第1.1节` 因 `doc not in bynum` 直接 continue，
#      等于"声称在查全部《0N》引用，却对不存在的文档号视而不见"；现在照样报出。
#   ② **链式引用逐个校验**：`《07》第3.1节、第9.9节` 此前只校验首个节号；现在把链上
#      （`、`／`，`／`～` 连接）的每个节号都单独校验（实测现行工作区链上 213 个节号，
#      逐个校验后新增失败 0 处——属于"加牙不加噪"）。
#   ③ 父节松匹配（`k.startswith(sec + '.')`）本轮**不改**：它与 `sections()` 的派生父键
#      等价（实测靠它单独通过的引用 0 处），改动只会重新定义"父节引用"的语义而不会增加覆盖。
unres = []
for name in D:
    for mm in re.finditer(r'《(\d\d)》第(\d+(?:\.\d+)*)节'
                          r'((?:[、，]第\d+(?:\.\d+)*节|[～~-]第?\d+(?:\.\d+)*节)*)', D[name]):
        doc, sec, tail = mm.group(1), mm.group(2), mm.group(3)
        nums = [sec] + re.findall(r'第(\d+(?:\.\d+)*)节', tail) \
            + re.findall(r'[～~-]第?(\d+(?:\.\d+)*)节', tail)
        if doc not in bynum:
            for s in nums:
                unres.append('%s -> 《%s》第%s节（本工作区没有编号 %s 的文档）'
                             % (name, doc, s, doc))
            continue
        keys = SEC[bynum[doc]]
        for s in nums:
            if not any(s == k or s.startswith(k + '.') or k.startswith(s + '.') for k in keys):
                unres.append('%s -> 《%s》第%s节' % (name, doc, s))
print('  被引文档：%s' % ', '.join(sorted(bynum)))
if unres:
    for u in sorted(set(unres)): print('    !! %s' % u)
report(not unres, '所有《0N》第x.y节 引用均可解析（含链式引用的每个节号；未知文档号报出）',
       '%d 处无法解析' % len(set(unres)))

# ---- D 《07》来源清单覆盖 ----------------------------------------------
print(); print('=' * 78); print('D 《07》来源清单覆盖'); print('=' * 78)
n7 = next((n for n in D if n.startswith('07-')), None)
if n7:
    t7 = D[n7]
    m = re.search(r'### 1\.3 需求来源清单(.*?)(?:\n---\n|\n## )', t7, re.S)
    if m:
        seg, body = m.group(1), t7.replace(m.group(1), '')
        rows = [r for r in seg.strip().split('\n') if r.strip().startswith('|')]
        keys = {(d, s) for d, s in re.findall(r'《(0[24])》第([0-9]+(?:\.[0-9]+)*)节', seg)}
        cited = set()
        for mm in re.finditer(r'《(0[24])》第([0-9]+(?:\.[0-9]+)*)节((?:[、，]第[0-9]+(?:\.[0-9]+)*节|[～~-]第?[0-9]+(?:\.[0-9]+)*节)*)', body):
            cited.add((mm.group(1), mm.group(2)))
            for num in re.findall(r'第([0-9]+(?:\.[0-9]+)*)节', mm.group(3)): cited.add((mm.group(1), num))
            for num in re.findall(r'[～~-]第?([0-9]+(?:\.[0-9]+)*)节', mm.group(3)): cited.add((mm.group(1), num))
        miss = sorted('《%s》第%s节' % (d, s) for d, s in cited
                      if not any(d == kd and (s == k or s.startswith(k + '.') or k.startswith(s + '.')) for kd, k in keys))
        print('  来源清单 %d 行；一级来源 %d 个节号；正文引用 %d 个（文档, 节号）对' % (len(rows) - 2, len(keys), len(cited)))
        for x in miss: print('    !! 未覆盖 %s' % x)
        report(not miss, '正文引用的节都在来源清单中', '%d 处未覆盖' % len(miss))
    else:
        report(False, '未找到 第1.3节 需求来源清单')

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
            trk = set(re.findall(r'第([0-9]+(?:\.[0-9]+)*)节', frs[c[0]]))
            for s in re.findall(r'《0[24]》第([0-9]+(?:\.[0-9]+)*)节', c[2]):
                if not any(s == x or s.startswith(x + '.') or x.startswith(s + '.') for x in trk):
                    prob.append('%s 矩阵 第%s节' % (c[0], s))
    for p in prob: print('    !! %s' % p)
    report(not prob, '矩阵来源均在条目追溯范围内', '%d 处越界' % len(prob))

    # ---- F 第3.8节 vs 第7.2节 ----
    print(); print('=' * 78); print('F 第3.8节 汇总表 与 第7.2节 矩阵 的 FR 来源一致'); print('=' * 78)
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
# 2026-09-28（第二轮复审 B-26 整改，只加"扫描器可用性正对照"，不改命中判定强度）：
# J 组此前**只 print、不进 fails**——扫描器自身坏掉（词表被删、正则写错）也无人发现。
# 现在补一条正对照并真正 report()：构造样本必须命中"未否定的边界词"，否则 J 组判失败。
# 至于把"真实文档里的未否定命中"本身升为门禁：实测收紧为「有引入/使用类正向词且无否定词」
# 后，现行 5 处正当表述（如《03》"本库不含…"缺否定词形态、《01》的题目收敛说明）会被误判为
# 失败，需要文档侧配合——本轮登记不改判据强度（详见整改报告 B-26）。
J_NEG = re.compile(r'不引入|不研究|不接入|不处理|不提供|不涉及|不得|禁止|不再|边界|除外|不同|vs|不按|不是|不称|never|明确不')
J_CTRL = '本系统引入' + BAN[0] + '作为主存储并对外提供查询。'
J_CTRL_OK = any(w in J_CTRL for w in BAN) and not J_NEG.search(J_CTRL)
for name in sorted(D):
    for i, L in enumerate(D[name].split('\n'), 1):
        for w in BAN:
            if w in L:
                ctx_ok = bool(J_NEG.search(L))
                if not ctx_ok:
                    print('    ?  %s:%d  「%s」  %s' % (name, i, w, L.strip()[:80]))
print('  （? 行需人工确认语境；出现"不引入/不研究"等否定语境的已自动过滤）')
report(J_CTRL_OK, 'J 组语境扫描器可用（构造样本必须命中未否定的边界词）',
       '构造样本命中=%s；真实文档的命中仍逐行列出、不进退出码（需人工判断语境）' % J_CTRL_OK)

# ---- K 路径存在性 -------------------------------------------------------
print(); print('=' * 78); print('K 文档内提到的文件路径是否存在'); print('=' * 78)
# 2026-09-28（第二轮复审 B-25 整改，只改"扩展名白名单／路径存在性"这一块）：
#   ① 扩展名白名单补齐 `.json`／`.jsonl`／`.txt`／`.cypher`（原 8 种把数据侧交付物整片漏掉；
#      实测参与核验文档的反引号 token 里 `.json` 232 处、`.jsonl` 154 处、`.txt` 74 处、
#      `.cypher` 30 处看不见）；
#   ② 存在性判定由"15 个搜索目录、只到一层深"改为**全树索引**（排除 .git／__pycache__／.idea）：
#      原实现够不到 `数据集\v2.1\chunks\chunks.jsonl`、`图谱导出\v2.1_v1_2\…`、`_工作底稿\…`
#      这类两层以上的路径，文件在盘上也可能被判悬空（只扩扩展名会制造大量误报，两者必须一起改）；
#   ③ 通配写法（`exp_*.py`、`代码\检索\*.py`）改为**真判**：必须匹配到 ≥1 个真实文件；
#   ④ 三类"不是工作区内的路径"的写法**单独逐条列出**、不计悬空（不隐藏、不静默）：
#      · 非路径写法：占位符 `raw\{doc_id}.json`、缩略写法 `...\raw\gate_x.txt`、纯后缀 `.out.txt`；
#      · 工作区外路径：`%TEMP%\stage7audit\...` 这类以环境变量／盘符起头、落在工作区外的写法；
#      · 第三方复核留痕：同一文档已把某批文件登记为"落盘在仓库外"（文档内出现 `%VAR%\…` 或
#        `...\…` 缩略写法）时，该文档内与登记项同名的裸文件名（或与登记项同一行的裸文件名）
#        按工作区外留痕处理——这是**逐条打印**的豁免，且只在"该文档确实登记了工作区外留痕"
#        时生效，通道挪不到普通交付文档上去掩盖真正的悬空引用。
#   别名（LEGACY／RENAMED）与归档目录仍按原样解析；索引只增加"候选落点"，不豁免任何判定。
WHITE = re.compile(r'(输入|输出|模板)\.|^\{|^\d+_\d+_|^[A-Z]+-\d+_[A-Za-z]+\d+_|\.\.\.$|…|^X\.md$|_译文\.docx$|方向X_|^[^\\/]*\{[^}]*\}')
# K 组识别的扩展名白名单（2026-09-28 由 8 种扩到 12 种；扩名单后新暴露的悬空路径见整改报告）
K_TOKEN = re.compile(r'`([^`\n]+\.(?:md|py|html|csv|docx|pdf|png|svg|json|jsonl|txt|cypher))`')
PLACEHOLDER = re.compile(r'\{[^}]*\}')                    # 占位符写法（模板路径）
ABBREV = re.compile(r'\.\.\.|…')                          # 缩略写法（`...\raw\…`）
EXTERNAL = re.compile(r'^(%[^%]+%|[A-Za-z]:)[\\/]')       # 工作区外写法（`%TEMP%\…`／`C:\…`）
WILDCARD = re.compile(r'[*?\[]')                          # 通配写法（按真判，不豁免）
# 已在文档中声明、但尚未创建的产出（计划产出）。新增计划产出时在此登记，创建后请立即删除对应条目。
# 2026-09-27 按编写约定 5 清空（审查 A 的 A1.4）：第 6 阶段的 9 条生效登记
# （`16-事件抽取与知识图谱（第六阶段）.md`、`extract.py`、`disambiguate.py`、`dedup_events.py`、
#  `write_graph.py`、`标注说明.md`、`代码\抽取与图谱\README.md`、`代码\抽取与图谱\config.py`、
#  `代码\抽取与图谱\run_all.py`）**全部已在磁盘上**，留着只会掩盖真正的悬空路径。
# 更早的 `nodes.csv`／`edges.csv`（2026-09-26 落盘）与 `验收第6阶段.py`（2026-09-25 落盘）
# 已按同一约定移除。分类规则保留在这里，供下一次登记时照用：
#   * 裸文件名 —— 在任意位置都算已登记；
#   * 带路径 —— 只匹配该路径。
# 带路径这一类是 2026-09-25 加的：`代码\抽取与图谱\README.md` 若按裸名 `README.md`
# 登记，会连带跳过全项目所有 README.md 的悬空判定，副作用大于收益。
PLANNED = set()
PLANNED_BARE = {p for p in PLANNED if '\\' not in p and '/' not in p}
PLANNED_PATH = {p.replace('/', '\\').lower() for p in PLANNED if ('\\' in p or '/' in p)}
def is_planned(tok):
    """裸文件名按文件名匹配；带路径的 token 按路径后缀匹配（见 PLANNED 的说明）。"""
    if os.path.basename(tok) in PLANNED_BARE:
        return True
    t = tok.replace('/', '\\').lower()
    return any(t == p or t.endswith('\\' + p) or p.endswith('\\' + t) for p in PLANNED_PATH)
print('  （计划产出登记：PLANNED %d 条——按编写约定 5，文件一旦落盘就立即移出；'
      '核验项 A～N 共 14 项，与登记数不是一回事）' % len(PLANNED))
# 归档目录（含其下一层子目录）
ARCH = glob.glob(os.path.join(LITDIR, '_归档_*'))
ARCH += [d for d in glob.glob(os.path.join(LITDIR, '_归档_*', '*')) if os.path.isdir(d)]
# 查找候选位置：根目录、阶段目录、文献资产目录、工具、图表、代码；分节源文件目录单列
SEARCH = [ROOT, LITDIR, os.path.join(LITDIR, '文献PDF'), os.path.join(LITDIR, '文献翻译'),
          os.path.join(ROOT, '工具'), os.path.join(ROOT, '图表'), os.path.join(ROOT, '代码'), SECDIR] + STAGES
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '代码', '*')) if os.path.isdir(d)]
# 数据集（第 5 阶段起存在）：文档里按**数据集内的相对路径**写（`meta\sources.csv`、
# `reports\consistency_report.md` 等），所以把每个版本目录也列入查找位置；
# `_试跑\` 同理（《12》第九节 要求的小规模验证目录）。
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '阶段05-数据准备', '数据集', '*')) if os.path.isdir(d)]
SEARCH += [os.path.join(ROOT, '阶段05-数据准备', '_试跑')]
# 抽取评测集（第 6 阶段起存在）：文档里既有带路径的写法（`阶段05-…\抽取评测集\v2.1\标注说明.md`），
# 也有**裸文件名**（`标注说明.md`、`dev.jsonl`、`分层统计.json`）。版本目录与数据集版本目录、
# 图谱导出版本目录同一处理：把 `抽取评测集\<版本>\` 也列入查找位置。
# 2026-09-27：按编写约定 5 清空 PLANNED 后，K 立刻暴露《15》《16》里裸引用的 `标注说明.md`
# 两处「悬空」；回查确认文件真实存在（`阶段05-数据准备\数据集\抽取评测集\v2.1\标注说明.md`，
# 也在同目录的带路径写法里），属 K 的**搜索范围缺口**、不是文档引用错——按约定 6 扩大搜索范围，
# 不把它塞回 PLANNED（那才会掩盖真正的悬空路径）。扩范围只增加候选落点，不豁免任何判定。
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '阶段05-数据准备', '数据集', '抽取评测集', '*'))
           if os.path.isdir(d)]
# 第 6 阶段的图谱导出物（`图谱导出\v2.1\`）：《16》与《00》里既有带路径的写法、也有裸文件名（`nodes.csv`、`edges.csv`），把每个导出版本目录也列入查找位置。
SEARCH += [d for d in glob.glob(os.path.join(ROOT, '阶段06-事件抽取与知识图谱', '图谱导出', '*')) if os.path.isdir(d)]
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
                # 别名目标既可能在阶段目录下，也可能在后来的归档目录下：2026-09-25 重组时
                # `文献调研\方向X_*.md` 全部迁进了 `_归档_*`，只查 new 会漏。
                for base in [new] + ARCH:
                    out += [os.path.join(base, rest),
                            os.path.join(base, os.path.basename(rest))]
    alt = RENAMED.get(os.path.basename(tok))
    if alt:
        for d in SEARCH + ARCH: out.append(os.path.join(d, alt))
    return out


# 全树索引（B-25 整改的"搜索深度"落点）：相对路径（小写、正斜杠）＋ 是否目录。
IDX_SKIP = {'.git', '__pycache__', '.idea'}
PATH_INDEX = []
for _dp, _dn, _fn in os.walk(ROOT):
    _dn[:] = [d for d in _dn if d not in IDX_SKIP]
    _rel = os.path.relpath(_dp, ROOT).replace('\\', '/')
    if _rel != '.':
        PATH_INDEX.append((_rel.lower(), True))
    for _f in _fn:
        _r = ((_rel + '/') if _rel != '.' else '') + _f
        PATH_INDEX.append((_r.replace('\\', '/').lower(), False))


def _norm(tok):
    return tok.replace('\\', '/').strip().lower()


def indexed(tok):
    """全树索引查找：带目录成分的 token 按**路径后缀**匹配；裸文件名按**文件名**匹配。"""
    t = _norm(tok)
    if '/' in t:
        return any(rel == t or rel.endswith('/' + t) for rel, _isdir in PATH_INDEX)
    return any(rel == t or rel.rsplit('/', 1)[-1] == t for rel, _isdir in PATH_INDEX)


def glob_hits(tok):
    """通配写法按**真判**：带目录成分按整条相对路径匹配，裸写法按文件名匹配。"""
    t = _norm(tok)
    if '/' in t:
        return [rel for rel, _isdir in PATH_INDEX if fnmatch.fnmatch(rel, t)]
    return [rel for rel, _isdir in PATH_INDEX if fnmatch.fnmatch(rel.rsplit('/', 1)[-1], t)]


# 第三方复核留痕：逐文档收集"工作区外／缩略写法"里登记过的文件名（含与之同一行的裸文件名）。
TRACE_NAMES = {}
for _name in D:
    _all, _line = set(), {}
    for _i, _L in enumerate(D[_name].split('\n'), 1):
        _toks = re.findall(r'`([^`\n]+)`', _L)
        _ext = [t for t in _toks if EXTERNAL.match(t) or ABBREV.search(t)]
        for _t in _ext:
            _all.add(os.path.basename(_norm(_t).rstrip('/')))
        if _ext:
            _line[_i] = {os.path.basename(_norm(t).rstrip('/')) for t in _toks}
    TRACE_NAMES[_name] = (_all, _line)

# 逐 token（同一 token 在同一文档里可能出现多次）归一个"最宽判定"：只要有一处能解析／
# 属于已登记的三类写法，就不算悬空；只有**处处都解析不到**的 token 才判悬空。
# 顺序＝优先级（越靠后越"宽"）：同一 token 在一处判悬空、另一处能解析／属已登记写法时，取宽的。
VERDICT_ORDER = ['miss', 'tmpl', 'external', 'trace', 'wild', 'planned', 'exists', 'skip']
verdicts = {}          # (name, token) -> [rank, 首个行号]


def _mark(key, verdict, line_no):
    row = verdicts.get(key)
    rank = VERDICT_ORDER.index(verdict)
    if row is None or rank > row[0]:
        verdicts[key] = [rank, line_no]


for name in D:
    _all, _line = TRACE_NAMES[name]
    for i, L in enumerate(D[name].split('\n'), 1):
        for tok in K_TOKEN.findall(L):
            key = (name, tok)
            if tok.startswith('http') or ' ' in tok:
                _mark(key, 'skip', i); continue
            if PLACEHOLDER.search(tok) or ABBREV.search(tok) \
                    or os.path.basename(_norm(tok).rstrip('/')).startswith('.'):
                _mark(key, 'tmpl', i); continue
            if EXTERNAL.match(tok):
                _mark(key, 'external', i); continue
            if WILDCARD.search(tok):
                _mark(key, 'wild' if glob_hits(tok) else 'miss', i); continue
            if WHITE.search(tok):
                _mark(key, 'skip', i); continue
            if is_planned(tok):
                _mark(key, 'planned', i); continue
            if indexed(tok) or any(os.path.exists(c) for c in legacy_paths(tok)):
                _mark(key, 'exists', i); continue
            base = os.path.basename(_norm(tok).rstrip('/'))
            if '\\' not in tok and '/' not in tok and (base in _all or base in _line.get(i, ())):
                _mark(key, 'trace', i); continue
            _mark(key, 'miss', i)


def _rows(verdict):
    return ['%s:%d  %s' % (name, line_no, tok)
            for (name, tok), (rank, line_no) in verdicts.items()
            if VERDICT_ORDER[rank] == verdict]


k_tmpl, k_ext, k_trace, k_wild = _rows('tmpl'), _rows('external'), _rows('trace'), _rows('wild')
miss = set('%s  提到  %s%s' % (name, tok,
                              '（通配写法，匹配不到任何文件）' if WILDCARD.search(tok) else '')
           for (name, tok), (rank, _i) in verdicts.items() if VERDICT_ORDER[rank] == 'miss')
k_tmpl.sort(); k_ext.sort(); k_trace.sort(); k_wild.sort()
print('  非路径写法（占位符／缩略／纯后缀）%d 处：' % len(k_tmpl))
for x in k_tmpl: print('    ~ %s' % x)
print('  工作区外路径（不计存在性）%d 处：' % len(k_ext))
for x in k_ext: print('    ~ %s' % x)
print('  第三方复核留痕（工作区外原始输出的同批登记，按文档逐条豁免）%d 处：' % len(k_trace))
for x in k_trace: print('    ~ %s' % x)
print('  通配写法（真判：匹配到 ≥1 个真实文件）%d 处：' % len(k_wild))
for x in k_wild: print('    ~ %s' % x)
for x in sorted(miss): print('    !! %s' % x)
report(not miss, '文档提到的文件均存在（全树索引 ＋ 旧路径别名；通配写法按真判）',
       '%d 处悬空；另有非路径写法 %d 处、工作区外路径 %d 处、第三方复核留痕 %d 处、'
       '通配写法 %d 处（逐条列出）'
       % (len(miss), len(k_tmpl), len(k_ext), len(k_trace), len(k_wild)))

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

# ---- N 《02》版本号一致性 与 引用版本审计 ---------------------------------
print(); print('=' * 78); print('N 《02》的版本号在标题、版本字段与修订记录三处是否一致'); print('=' * 78)
# 起因（2026-09-25 实测）：第1.2节 修订记录一路记到 v2.5，而标题与文档信息表的版本字段
# 仍停在 v2.3——v2.4／v2.5 两次登记只改了 第1.2节，没有回改表头，漂移了两个版本且无人发现。
# N1 把三处对齐：标题末尾的版本、`| 版本 |` 字段、第1.2节 修订记录里最后一行版本（门禁项）。
# N2 顺着 N1 得到的当前版本审计其余文档的引用：默认只报告，--strict-citations 时转为门禁。
n2 = next((n for n in D if n.startswith('02-')), None)
if n2:
    t2 = D[n2]
    lines2 = t2.splitlines()
    m_title = re.search(r'项目执行总控文档\s*(v\d+\.\d+)\s*$', lines2[0]) if lines2 else None
    m_field = re.search(r'\|\s*版本\s*\|\s*(v\d+\.\d+)', t2)
    m_last = None
    for ln in lines2:
        mm = re.match(r'\|\s*(v\d+\.\d+)\s*\|\s*\d{4}-\d{2}-\d{2}\s*\|', ln)
        if mm: m_last = mm
    got = [('标题', m_title.group(1) if m_title else None),
           ('版本字段', m_field.group(1) if m_field else None),
           ('修订记录末行', m_last.group(1) if m_last else None)]
    print('  N1 三处版本号一致（门禁项：任一不一致即非零退出）')
    for label, v in got:
        print('    %-12s %s' % (label, v or '<未解析到>'))
    vals = {v for _, v in got}
    ok_n = (None not in vals) and len(vals) == 1
    if not ok_n:
        print('    !! 三处版本号不一致：%s' % sorted(str(v) for v in vals))
    report(ok_n, '《02》标题／版本字段／修订记录末行的版本号一致', '%s' % (sorted(vals)[0] if ok_n else '不一致'))

    # ---- N2 引用的《02》版本审计（默认只报告；--strict-citations 时门禁）----
    # 口径：逐行扫描参与核验的文档，排除《02》自身与 05／06／08／11 记录类文件（它们按职责逐字保留
    # 历史措辞）；行内出现《02 且含 vX.Y 版本号即算引用，同一行重复出现同一版本只算一处。
    # 被引版本不等于当前版本时，只有同一行带「版本链／未改变／不影响／历史／留痕」之一才可接受。
    cur_ver = next((v for _, v in got if v), None)     # N1 解析出的当前基线版本（三处一致时唯一）
    print('  N2 引用《02》的版本审计（当前基线 %s；模式：%s）'
          % (cur_ver or '<未解析到>',
             '门禁（--strict-citations：过期引用计入退出码）' if STRICT_CITATIONS
             else '只报告（默认：过期引用不影响退出码，加 --strict-citations 转为门禁）'))
    if cur_ver is None:
        print('    （N1 未解析出当前版本，N2 跳过：没有可比对的当前基线版本；N1 已按失败处理）')
    else:
        CITE_SKIP = re.compile(r'^(?:02|05|06|08|11)-')
        CITE_MARKS = ('版本链', '未改变', '不影响', '历史', '留痕')
        # 只审计**依据声明行**：只有文档在头部声明"依据／上游／需求来源"时，才会写出它所依据的
        # 《02》版本。正文里的旧版本叙述（如《00》"《02》由 v2.1 → v2.2 → v2.3"）是历史陈述，
        # 不是依据声明，纳入只会制造噪声。
        CITE_DECL = re.compile(r'依据|上游|需求来源')
        # 版本号必须**紧跟在《02…》之后**，且中间不再出现另一处《》引用——否则同一行里其他文档
        # 或数据集的版本号（如"…与数据集 v1.0"）会被误算成《02》的版本。
        CITE_REF = re.compile(r'《02[^》]*》[^《]{0,30}?(v\d+\.\d+)')
        print('    口径：只审计**依据声明行**（含"依据／上游／需求来源"）；版本号须紧跟在《02…》'
              '之后且中间无其他《》引用；被引版本非当前时需同行带 %s 之一' % '／'.join(CITE_MARKS))
        cites = []          # [(文件名, 行号, 被引版本, 行内容)]
        for name in sorted(D):
            if CITE_SKIP.match(name): continue
            for i, L in enumerate(D[name].split('\n'), 1):
                if not CITE_DECL.search(L): continue
                for ver in dict.fromkeys(CITE_REF.findall(L)):
                    cites.append((name, i, ver, L))
        # 判定口径（2026-09-25 校准过一次）：被引版本非当前版本时，**只有同一行既没提到当前
        # 版本、也没带版本链标记**才算过期。
        # 加"提到当前版本"这一条，是因为实际修法常常写成
        # 「（编制时为 v2.5，第 5 阶段完成后已登记为 v2.6）」——那种写法已经把版本链讲清楚了，
        # 却因为不含 版本链／未改变 这些字样被上一版误报。**守卫的假阳性与假阴性一样要修，
        # 但修的是守卫，不是文档。**
        stale = [c for c in cites
                 if c[2] != cur_ver
                 and cur_ver not in c[3]
                 and not any(m in c[3] for m in CITE_MARKS)]
        for name, i, ver, _L in stale:
            print('    !! %s L%d  依据《02》%s（当前 %s）' % (name, i, ver, cur_ver))
        print('    扫描到依据声明 %d 处（已排除《02》自身与 05／06／08／11 记录类文件）；其中过期 %d 处'
              % (len(cites), len(stale)))
        if stale and not STRICT_CITATIONS:
            print('    （只报告：以上过期引用不影响本次退出码；加 --strict-citations 可转为门禁）')
        report(not stale, 'N2 引用的《02》版本等于当前基线或同行带版本链说明',
               '引用 %d 处、过期 %d 处%s'
               % (len(cites), len(stale),
                  '（--strict-citations 计入门禁）' if STRICT_CITATIONS else '（只报告）'),
               gating=STRICT_CITATIONS)

# ---- O 题录指纹一致性 ---------------------------------------------------
# 2026-09-28 新增（依《文献替换独立核验》的门禁缺口 G1／G3／G4）：独立核验的破坏性实验证明，
# 把《03》总表或分节的题名换成另一个名字、把《04》引用编号错一位、把总表「全文」列的文件名
# 改成不存在的文件，四道门禁全部放行。K 项只查“反引号路径在不在”，而**总表「全文」列没有
# 反引号**，扫不到；`_替换执行/07_文档自检.py` 又恒以 0 退出、不构成门禁。
# 因此这里加一份**外部金标准**（`_替换执行/22条题录指纹.json`，由 `_替换执行/11_生成题录指纹.py`
# 生成），据它比对四件事，本项计入退出码：
#   O1 指纹文件本身自洽（22 条、槽位互不重复、每条 sha256 与总 sha256 可重算一致）；
#   O2 《03》第二节总表 22 行的 槽位／题名／年 与指纹一致（**直接按表格列解析，不依赖反引号**）；
#   O3 《03》总表「全文」列的文件名与指纹一致，且该文件在 `文献PDF/` 下真实存在；
#   O4 《04》参考文献表 22 行与指纹逐条一致（题名与首作者均须出现在该行）；
#   O5 《04》正文引用编号：集合＝[1,22]、按首次出现顺序严格递增、每条的出现次数与指纹一致
#      （出现次数这一条是为“把某次出现的编号错一位”而设：只查集合与首现顺序抓不到它）。
# 只增不减：不修改 A～N 的任何判据。
print(); print('=' * 78); print('O 题录指纹（22 条）一致性：以 _替换执行/22条题录指纹.json 为外部金标准'); print('=' * 78)
_o3 = next((n for n in D if n.startswith('03-')), None)
_o4 = next((n for n in D if n.startswith('04-')), None)
_ofl = os.path.join(LITDIR, '_替换执行', '22条题录指纹.json')
_fp = None
if not os.path.exists(_ofl):
    report(False, 'O 题录指纹文件存在：阶段02-文献调研与开题\\_替换执行\\22条题录指纹.json', '文件不存在')
else:
    try:
        import json as _json
        _fp = _json.load(io.open(_ofl, encoding='utf-8'))
        report(True, 'O 题录指纹文件可解析')
    except Exception as _e:
        report(False, 'O 题录指纹文件可解析', '解析失败：%s' % _e)

O_SLOTS = ["KG-5", "KG-9", "KG-16", "KG-17", "KG-19", "KG-21", "KG-28", "KG-29",
           "RAG-1", "RAG-9", "RAG-10", "RAG-11", "RAG-13", "RAG-24",
           "FIN-3", "FIN-16", "FIN-17", "FIN-20", "SYS-4", "SYS-8", "SYS-13", "SYS-14"]


def _sha(s):
    import hashlib
    return hashlib.sha256(s.encode('utf-8')).hexdigest()


if _fp is not None and _o3 and _o4:
    ROWS = _fp.get('条目', [])
    if len(ROWS) != 22:
        report(False, 'O1 指纹条数为 22', '实测 %d 条' % len(ROWS))
    else:
        report(True, 'O1 指纹条数为 22')
    _slots = [r.get('槽位') for r in ROWS]
    report(_slots == O_SLOTS, 'O1 指纹槽位集合与顺序为既定 22 槽位',
           '实测 %s' % ('、'.join(_slots) if _slots != O_SLOTS else '一致'))
    _bad = []
    for r in ROWS:
        canon = '|'.join([r.get('槽位', ''), r.get('题名', ''), r.get('作者', ''), r.get('出处', ''),
                          r.get('年', ''), r.get('卷期页', ''), r.get('全文', ''), str(r.get('引用编号', ''))])
        if _sha(canon) != r.get('sha256'):
            _bad.append(r.get('槽位'))
    report(not _bad, 'O1 指纹每条 sha256 可重算一致', '不一致 %s' % _bad)
    report(_sha('\n'.join(r.get('sha256', '') for r in ROWS)) == _fp.get('总sha256'),
           'O1 指纹 总sha256 可重算一致')

    # ---- O2／O3 《03》第二节总表（按表格列解析，不依赖反引号）----
    _t3 = D[_o3]
    _m2 = re.search(r'## 二、文献库总表(.*?)\n---\n', _t3, re.S)
    _tot = {}
    if _m2:
        for _mm in re.finditer(r'^\| ((?:KG|RAG|FIN|SYS)-\d+) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| '
                               r'([^|]+?) \| ([^|]+?) \| ([^|]+?) \|', _m2.group(1), re.M):
            _s, _ti, _dd, _yr, _pr, _fu, _ld = [x.strip() for x in _mm.groups()]
            _fm = re.search(r'（([^）]+)）', _fu)
            _tot[_s] = {'题名': _ti, '年': _yr, '全文': (_fm.group(1).strip() if _fm else _fu)}
    _mism = []
    for r in ROWS:
        _t = _tot.get(r['槽位'])
        if not _t:
            _mism.append('%s 不在总表' % r['槽位']); continue
        if _t['题名'] != r['题名']:
            _mism.append('%s 题名（总表 %r ≠ 指纹 %r）' % (r['槽位'], _t['题名'], r['题名']))
        if _t['年'] != r['年']:
            _mism.append('%s 年份（总表 %r ≠ 指纹 %r）' % (r['槽位'], _t['年'], r['年']))
        if _t['全文'] != r['全文']:
            _mism.append('%s 全文列（总表 %r ≠ 指纹 %r）' % (r['槽位'], _t['全文'], r['全文']))
    for _x in _mism:
        print('    !! %s' % _x)
    report(not _mism, 'O2/O3 《03》总表 22 行的 槽位/题名/年/全文列 与指纹一致', '%d 处不一致' % len(_mism))
    _missing = [r['全文'] for r in ROWS
                if not os.path.exists(os.path.join(LITDIR, '文献PDF', r['全文']))]
    report(not _missing, 'O3 指纹的 22 个全文文件均在 文献PDF/ 下存在', '缺 %s' % _missing)

    # ---- O4 《04》参考文献表 22 行 ----
    _t4 = D[_o4]
    _i11 = _t4.index('## 十一、参考文献')
    _body, _refs = _t4[:_i11], _t4[_i11:]
    _ref = {int(a): b for a, b in re.findall(r'^\[(\d+)\] (.+)$', _refs, re.M)}
    _rbad = []
    if sorted(_ref) != list(range(1, 23)):
        _rbad.append('参考文献表编号不是 1..22：%s' % sorted(_ref))
    for r in ROWS:
        _n = int(r['引用编号'])
        _ln = _ref.get(_n, '')
        _firstauthor = r['作者'].split(',')[0].strip()
        if r['题名'] not in _ln:
            _rbad.append('[%d] 题名未出现：%r' % (_n, r['题名']))
        if _firstauthor and _firstauthor not in _ln:
            _rbad.append('[%d] 首作者 %r 未出现' % (_n, _firstauthor))
    for _x in _rbad:
        print('    !! %s' % _x)
    report(not _rbad, 'O4 《04》参考文献表 22 行与指纹逐条一致（题名＋首作者）', '%d 处不一致' % len(_rbad))

    # ---- O5 《04》正文引用编号 ----
    _seq = []
    for _no, _L in enumerate(_body.split('\n'), 1):
        for _mm in re.finditer(r'\[(\d+)\]', _L):
            _seq.append((_no, int(_mm.group(1))))
    _nums = [n for _, n in _seq]
    _occ = {n: _nums.count(n) for n in sorted(set(_nums))}
    _first = {}
    for _no, _n in _seq:
        _first.setdefault(_n, _no)
    _order = [x[0] for x in sorted(_first.items(), key=lambda kv: (kv[1], kv[0]))]
    report(sorted(set(_nums)) == list(range(1, 23)), 'O5 正文引用编号集合 ＝ [1]～[22]',
           '实测 %s' % sorted(set(_nums)))
    report(_order == list(range(1, 23)), 'O5 正文引用编号按首次出现顺序严格递增',
           '首现顺序 %s' % _order)
    _cbad = [(r['槽位'], r['引用编号'], _occ.get(int(r['引用编号']), 0), r.get('正文引用次数'))
             for r in ROWS if _occ.get(int(r['引用编号']), 0) != r.get('正文引用次数')]
    for _x in _cbad:
        print('    !! %s [%s] 正文出现 %d 次 ≠ 指纹 %s 次' % _x)
    report(not _cbad, 'O5 正文每条引用出现次数与指纹一致', '%d 条不一致' % len(_cbad))

print(); print('=' * 78)
print('结论：%s' % ('全部通过' if not fails else '存在 %d 项失败：%s' % (len(fails), '；'.join(fails))))
print('=' * 78)
sys.exit(1 if fails else 0)
