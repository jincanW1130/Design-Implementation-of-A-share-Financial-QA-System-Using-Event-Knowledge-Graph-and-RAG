#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""《10-系统总体设计（第四阶段）》专项验收（对应《09》§七 的验收标准 + §四 的 13 条硬约束）。

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
def chk(ok, label, detail=''):
    print('  [%s] %s%s' % ('OK ' if ok else 'FAIL', label, ('  ' + detail) if detail else ''))
    if not ok:
        fails.append(label)

for p in (P10, P02):
    if not os.path.exists(p):
        print('缺少输入文件：%s' % p)
        sys.exit(1)

with open(P10, 'r', encoding='utf-8') as f:
    t = f.read()
with open(P02, 'r', encoding='utf-8') as f:
    t02 = f.read()

print('=' * 78); print('一、《09》§七 验收标准'); print('=' * 78)

# 1 七个小节标题与《02》§15 第四章逐字一致
sec02 = re.search(r'### 第四章 系统设计(.*?)\n### 第五章', t02, re.S).group(1)
titles = re.findall(r'- (4\.\d) ([^\n]+)', sec02)
chk(len(titles) == 7, '《02》§15 第四章给出 7 个小节', str(len(titles)))
for num, title in titles:
    chk(('### %s %s' % (num, title)) in t, '节标题逐字一致：%s %s' % (num, title))

# 2 六层名称与顺序逐字
LAY = ['用户交互层', '业务服务层', '智能问答层', '向量检索模块', '图谱检索模块', '数据知识层']
chk(all(x in t for x in LAY), '六层名称全部出现')
i0 = t.find('层次顺序与名称与《02》§8.1 一致')
seq = t[i0:i0 + 200]
pos = [seq.find(x) for x in LAY]
chk(all(p >= 0 for p in pos) and pos == sorted(pos), '六层顺序正确（用户交互层→…→数据知识层）', str(pos))

# 3 六个模块名称逐字 + 顺序
MOD = ['财经信息管理', '财经事件抽取', '事件知识图谱', '智能问答', '证据追溯', '历史问答']
chk(all(m in t for m in MOD), '六个模块名称全部出现')
i0 = t.find('模块名称与《02》§6.2 逐字一致')
seq = t[i0:i0 + 200]
pos = [seq.find(m) for m in MOD]
chk(all(p >= 0 for p in pos) and pos == sorted(pos), '六个模块顺序与《02》§6.2 一致', str(pos))

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

print(); print('=' * 78); print('二、《09》§四 13 条硬约束'); print('=' * 78)

# 约束 4：不得出现"每条关系都带证据属性"的无限定表述
bad = [i for i, L in enumerate(t.split('\n'), 1)
       if '每条关系' in L and ('source_doc_id' in L or 'source_chunk_id' in L) and '除 EVIDENCED_BY' not in L]
chk(not bad, '约束 4 无无限定的"每条关系带证据属性"', str(bad))

# 约束 5：FAISS 不得称向量数据库
bad = [i for i, L in enumerate(t.split('\n'), 1) if '向量数据库' in L]
ok = all(('独立向量数据库' in t.split('\n')[i - 1]) or ('不按' in t.split('\n')[i - 1]) for i in bad)
chk(ok, '约束 5 FAISS 未被称作向量数据库（%d 处出现，均在排除语境）' % len(bad))

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
c02 = len(re.findall(r'《02》§\d', t))
c07 = len(re.findall(r'《07》', t))
chk(c02 >= 60 and c07 >= 20, '约束 12 来源标注充分（《02》§ 引用 %d 处，《07》 %d 处）' % (c02, c07))

print(); print('=' * 78); print('三、图与表编号'); print('=' * 78)
figs = sorted(set(int(m) for m in re.findall(r'图 4-(\d+)　', t)))
tabs = sorted(set(int(m) for m in re.findall(r'表 4-(\d+)　', t)))
chk(figs == list(range(1, 9)), '图编号 4-1～4-8 连续且共 8 张（符合《09》§九 图 ≤ 8）', str(figs))
chk(tabs == list(range(1, 14)), '表编号 4-1～4-13 连续且共 13 张（符合《09》§九 表 ≤ 13）', '共 %d 张' % len(tabs))
chk(t.count('```mermaid') == 8, 'Mermaid 图块 8 个', str(t.count('```mermaid')))

print(); print('=' * 78); print('四、文档头与正文关于图表数量的陈述必须与实测一致'); print('=' * 78)
chk('**表 4-1～表 4-13** 共 13 张' in t, '导言 §0.2 图表编号陈述为 13 张')
chk('图 8 张、表 13 张' in t, '导言 §0.2 图表数量说明为 8 图 13 表')
chk('8 张图、13 张表' in t, '附录交付说明为 8 图 13 表')
chk('表 4-12 共 12 张' not in t and '8 张图、23 张表' not in t, '无残留的旧图表数量陈述')

print(); print('=' * 78)
print('结论：%s' % ('全部通过' if not fails else '存在 %d 项失败：%s' % (len(fails), '；'.join(fails))))
print('=' * 78)
sys.exit(1 if fails else 0)
