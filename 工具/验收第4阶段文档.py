#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""《10-系统总体设计（第四阶段）》专项验收（对应《09》第七节 的验收标准 + 第四节 的 13 条硬约束）。

与《跨文档核验.py》的分工：核验脚本查**全工作区**的通用一致性（表格列数、节号可解析、
术语、路径、登记），本脚本查**《10》自身**是否满足《09》写下的验收标准。

用法：python 工具\验收第4阶段文档.py
退出码：0 = 全部通过；1 = 存在失败项。
"""
import os, re, sys, io

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P10 = os.path.join(ROOT, '阶段04-系统总体设计', '10-系统总体设计（第四阶段）.md')
P02 = os.path.join(ROOT, '02-项目执行总控文档.md')

fails = []
ITEMS = [0]           # B-31 结构断言用：已执行的检查项条数（每调一次 chk 记 1）
SECTIONS = []         # B-31 结构断言用：实际打印出的节标题顺序
def chk(ok, label, detail=''):
    ITEMS[0] += 1
    print('  [%s] %s%s' % ('OK ' if ok else 'FAIL', label, ('  ' + detail) if detail else ''))
    if not ok:
        fails.append(label)

def sec(title):
    """节标题：打印 ＋ 记账（B-31 结构断言据此验「节结构未缺」）。"""
    SECTIONS.append(title)
    print(); print('=' * 78); print(title); print('=' * 78)

for p in (P10, P02):
    if not os.path.exists(p):
        print('缺少输入文件：%s' % p)
        sys.exit(1)

with open(P10, 'r', encoding='utf-8') as f:
    t = f.read()
with open(P02, 'r', encoding='utf-8') as f:
    t02 = f.read()

sec('一、《09》第七节 验收标准')

# 1 七个小节标题与《02》第15节 第四章逐字一致
sec02 = re.search(r'### 第四章 系统设计(.*?)\n### 第五章', t02, re.S).group(1)
titles = re.findall(r'- (4\.\d) ([^\n]+)', sec02)
chk(len(titles) == 7, '《02》第15节 第四章给出 7 个小节', str(len(titles)))
# 2026-09-29（C 线 A 线判据加固，只增不减）：原判据是子串匹配 `('### 4.7 接口设计') in t`，
# 于是「`### 4.7 接口设计` 后面再缀一个 `X`」照样通过——标题被改写也无人发现。改为**整行逐字**。
_LINES10 = t.split('\n')
for num, title in titles:
    want = '### %s %s' % (num, title)
    hit = want in _LINES10
    near = [L for L in _LINES10 if L.startswith('### %s' % num)]
    chk(hit, '节标题整行逐字一致：%s %s' % (num, title),
        '' if hit else '实测该编号的标题行：%s' % (near[:2] if near else '**该编号标题行缺失**'))

# 2 六层名称与顺序逐字
LAY = ['用户交互层', '业务服务层', '智能问答层', '向量检索模块', '图谱检索模块', '数据知识层']
chk(all(x in t for x in LAY), '六层名称全部出现')
i0 = t.find('层次顺序与名称与《02》第8.1节 一致')
seq = t[i0:i0 + 200]
pos = [seq.find(x) for x in LAY]
chk(all(p >= 0 for p in pos) and pos == sorted(pos), '六层顺序正确（用户交互层→…→数据知识层）', str(pos))

# 3 六个模块名称逐字 + 顺序
MOD = ['财经信息管理', '财经事件抽取', '事件知识图谱', '智能问答', '证据追溯', '历史问答']
chk(all(m in t for m in MOD), '六个模块名称全部出现')
i0 = t.find('模块名称与《02》第6.2节 逐字一致')
seq = t[i0:i0 + 200]
pos = [seq.find(m) for m in MOD]
chk(all(p >= 0 for p in pos) and pos == sorted(pos), '六个模块顺序与《02》第6.2节 一致', str(pos))

# 4 本体口径 6/8/9
ENT = ['Company', 'Person', 'Industry', 'Institution', 'Event', 'Policy']
chk(all(e in t for e in ENT), '6 类实体标签齐全')
EV8 = ['业绩事件', '监管事件', '股权事件', '投资并购事件', '重大合同事件', '产品事件', '政策事件', '重大经营事件']
chk(all(e in t for e in EV8), '8 种核心事件类型齐全')
REL = ['BELONGS_TO', 'SUPPLIES', 'CUSTOMER_OF', 'COMPETES_WITH', 'HAS_EXECUTIVE',
       'PARTICIPATES_IN', 'ISSUED_BY', 'RELATED_TO', 'EVIDENCED_BY']
chk(all(r in t for r in REL), '9 条核心关系齐全')
chk('**6 类实体**' in t and '**9 条核心关系**' in t, '6／9 口径以加粗口径出现')

# 5 "除 EVIDENCED_BY 外" + 证据属性三项
n = t.count('除 EVIDENCED_BY 外')
chk(n >= 5, '"除 EVIDENCED_BY 外"出现 %d 处（≥5）' % n)
for k in ['source_doc_id', 'source_chunk_id', 'confidence']:
    chk(k in t, '证据属性出现：%s' % k)

# 6 六张表名齐全
TB6 = ['user', 'document', 'document_chunk', 'question', 'answer', 'answer_evidence']
chk(all(('`%s`' % x) in t or (x in t) for x in TB6), '六张表名齐全')
chk('**恒为六张**' in t, '"恒为六张"口径出现')
chk(('user 表**保持为空' in t) or ('保持为空、不写入数据' in t), 'user 表始终建立且保持为空')

# 7 Method = C 组、Baseline 2 = A 组
chk('**Method ＝ 消融 C 组 ＝ Vector RAG + 2-hop Event KG' in t, 'Method ＝ C 组逐字写入')
chk('**Baseline 2 ＝ A 组**' in t, 'Baseline 2 ＝ A 组逐字写入')

# 8 Top-K 五步契约逐字
STEPS = [
    '同一个文本块无论被哪一路命中都只算一个证据',
    '保留到 K 个文本块，且这一步必须发生在 D／E 分组排序之前',
    '两路候选统一映射到 chunk_id 并按 chunk_id 去重',
    '每个问题最终证据集合的文本块数量上限',
]
for s in STEPS:
    chk(s in t, 'Top-K 契约逐字：%s' % s[:22] + '…')

# 9 排除检查：user 表可选 / 可以不建立（"不采用……做法"是显式否定，属正确表述，不计入）
BANNED_USER = ['可选表', '可以不建立']
for b in BANNED_USER:
    chk(b not in t, '未出现排除表述：%s' % b)
chk('不采用"按条件决定是否建表"的做法' in t, '显式声明不采用"按条件决定是否建表"的做法')

# 10 FR 在 4.2 与 4.7 都有落点
s42 = t[t.find('### 4.2 '):t.find('### 4.3 ')]
s47 = t[t.find('### 4.7 '):]
for i in range(1, 7):
    fr = 'FR-%02d' % i
    chk(fr in s42 and fr in s47, '%s 在 4.2 与 4.7 都有落点' % fr)

# 11 UC-01~07 在 4.3 都有落点
s43 = t[t.find('### 4.3 '):t.find('### 4.4 ')]
for i in range(1, 8):
    uc = 'UC-%02d' % i
    chk(uc in s43, '%s 在 4.3 有落点' % uc)

# 12 NFR 对应
for nfr, where in [('NFR-01', '4.1'), ('NFR-03', '4.1'), ('NFR-06', '4.7')]:
    chk(nfr in t, '%s 已对应（%s）' % (nfr, where))

sec('二、《09》第四节 13 条硬约束')

# 约束 4：不得出现"每条关系都带证据属性"的无限定表述
bad = [i for i, L in enumerate(t.split('\n'), 1)
       if '每条关系' in L and ('source_doc_id' in L or 'source_chunk_id' in L) and '除 EVIDENCED_BY' not in L]
chk(not bad, '约束 4 无无限定的"每条关系带证据属性"', str(bad))

# 约束 5：FAISS 不得称〈向量＋数据库〉
# 术语纪律：本文件不以字面量书写该四字术语，运行时由两个字串拼接（与仓库既有先例一致）。
TERM5 = '向量' + '数据库'
# 2026-09-29（C 线 A 线判据加固，只增不减）：原判据按**整行**豁免——只要该行任意位置出现
# `不按`，这一行里该术语的**所有**出现一律放行（`or ('不按' in L)`），等于「同行一个
# 不按免责全行」。改为**逐处（逐词）判定**：对每一处出现，只有当 ① 它是「独立」＋该术语的
# 整词前缀，或 ② 它**前面 12 个字符以内**有显式否定词（不按／不称／不把／不引入…）
# 时才豁免；否则计为违规。这样「同一行里既有一处正确表述、又有一处把 FAISS 叫该术语」
# 不再能互相掩护。
NEG5 = re.compile(r'不按|不称|不把|不作为|不视作|不叫作|不引入|不采用|不用于|不是|非')
bad5 = []
for i, L in enumerate(t.split('\n'), 1):
    for m in re.finditer(TERM5, L):
        if L[max(0, m.start() - 2):m.start()] == '独立':
            continue
        if NEG5.search(L[max(0, m.start() - 12):m.start()]):
            continue
        bad5.append('%d:…%s…' % (i, L[max(0, m.start() - 18):m.end() + 12]))
chk(not bad5, '约束 5 FAISS 未被称作%s（逐处判定：仅"独立%s"整词或'
              '就近（≤12 字）显式否定可豁免）' % (TERM5, TERM5),
    '未被豁免的表述 %d 处%s' % (len(bad5), '：' + '；'.join(bad5[:4]) if bad5 else ''))

# 约束 6：session_id 是 question 表字段；history 表不得复活
chk('session_id 是 **question 表的字段，不是新表**' in t, '约束 6 session_id 归属 question 表')
chk('history 表已删除、不复活' in t, '约束 6 history 表不复活')

# 约束 7：data_cutoff_time 不属于任何表；最新/最近/近期按 event_time
chk('**数据集版本级属性，不属于任何表**' in t, '约束 7 data_cutoff_time 归属')
chk('**一律以 event_time 判定**' in t, '约束 7 相对时间按 event_time 判定')
for s in ['**最新**', '**最近**', '**近期**']:
    chk(s in t, '约束 7 判定规则表含 %s' % s)

# 约束 8：0 跳显式标注
chk('本次回答未使用图谱扩展' in t and '不得强行生成或展示虚构的图谱路径' in t, '约束 8 0 跳显式标注与禁止虚构路径')

# 约束 9：不引入的技术清单
for w in ['LangChain', 'LlamaIndex', 'Milvus', 'Qdrant', 'Weaviate', 'Elasticsearch', 'Kafka', 'Kubernetes']:
    line = [L for L in t.split('\n') if w in L]
    chk(bool(line) and all(re.search(r'不引入|不按|不采用', L) for L in line), '约束 9 %s 仅出现在排除语境' % w)

# 约束 10：模型 TBD
chk('TBD' in t and '不写死型号' in t, '约束 10 模型型号保持 TBD')

# 约束 11：接口范围
chk('不做注册、不做找回密码、不做多角色与细粒度权限' in t, '约束 11 接口范围限于第一版')

# 约束 12：来源可回溯（抽样：设计条目均带来源标注）
c02 = len(re.findall(r'《02》第\d+(?:\.\d+)*节', t))
c07 = len(re.findall(r'《07》', t))
chk(c02 >= 60 and c07 >= 20, '约束 12 来源标注充分（《02》第x.y节 引用 %d 处，《07》 %d 处）' % (c02, c07))

sec('三、图与表编号')
figs = sorted(set(int(m) for m in re.findall(r'图 4-(\d+)　', t)))
tabs = sorted(set(int(m) for m in re.findall(r'表 4-(\d+)　', t)))
chk(figs == list(range(1, 9)), '图编号 4-1～4-8 连续且共 8 张（符合《09》第九节 图 ≤ 8）', str(figs))
chk(tabs == list(range(1, 14)), '表编号 4-1～4-13 连续且共 13 张（符合《09》第九节 表 ≤ 13）', '共 %d 张' % len(tabs))
chk(t.count('```mermaid') == 8, 'Mermaid 图块 8 个', str(t.count('```mermaid')))

sec('四、文档头与正文关于图表数量的陈述必须与实测一致')
chk('**表 4-1～表 4-13** 共 13 张' in t, '导言 第0.2节 图表编号陈述为 13 张')
chk('图 8 张、表 13 张' in t, '导言 第0.2节 图表数量说明为 8 图 13 表')
chk('8 张图、13 张表' in t, '附录交付说明为 8 图 13 表')
chk('表 4-12 共 12 张' not in t and '8 张图、23 张表' not in t, '无残留的旧图表数量陈述')

# B-31 结构断言（C 线整改，2026-09-29，仿《验收第7阶段.py》AB3）：汇总不得只判 `fails` 是否
# 为空——那样「整节被删」「某项检查被整段删掉」都会静默通过。这里同冻结「节结构 ＋ 检查项计数」，
# 恒定值不符即 FAIL。**增删检查项／改节标题时必须同步改这两个常量**（这正是「重数」的目的）。
EXPECTED_ITEMS_4 = 76
EXPECTED_SECTIONS_4 = ['一、《09》第七节 验收标准', '二、《09》第四节 13 条硬约束', '三、图与表编号',
                       '四、文档头与正文关于图表数量的陈述必须与实测一致']
_observed_items = ITEMS[0]               # 本项自身尚未记账，故此处即为「本项之前的检查项数」
chk(_observed_items == EXPECTED_ITEMS_4 and SECTIONS == EXPECTED_SECTIONS_4,
    'B-31 结构断言：检查项计数与节结构同冻结期望一致（%d 项、%d 节，均不含本项自身）'
    % (EXPECTED_ITEMS_4, len(EXPECTED_SECTIONS_4)),
    '实测 检查项 %d／%d；节 %d／%d%s'
    % (_observed_items, EXPECTED_ITEMS_4, len(SECTIONS), len(EXPECTED_SECTIONS_4),
       '' if SECTIONS == EXPECTED_SECTIONS_4 else '（实测节序：%s）' % '、'.join(SECTIONS)))

print(); print('=' * 78)
print('结论：%s' % ('全部通过' if not fails else '存在 %d 项失败：%s' % (len(fails), '；'.join(fails))))
print('=' * 78)
sys.exit(1 if fails else 0)
