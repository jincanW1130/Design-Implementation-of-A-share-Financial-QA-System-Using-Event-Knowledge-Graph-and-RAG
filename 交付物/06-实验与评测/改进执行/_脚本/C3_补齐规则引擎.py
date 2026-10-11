# -*- coding: utf-8 -*-
"""C-3 补齐规则引擎（零模型调用、零联网）——为 role_title / institution_type / issuer 产出规则口径补齐数据。

输入（只读）：图谱导出 v2.1_v1_3/nodes.csv ＋ 数据集 v2.1/chunks/chunks.jsonl（5018 块正文）
输出（只写 改进执行/C3_本体空列清单/）：
  补齐数据_role_title.jsonl · 补齐数据_institution_type.jsonl · 补齐数据_issuer.jsonl
  补齐统计.json
口径：全部为确定性规则（词典/正则），逐条带 quote 与 chunk_id 定位、可人工复核；
命中数据**不写入**冻结导出物——下一版导出生效前须人工逐条校验（见《撤销与补齐登记.md》）。
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
from collections import Counter

ROOT = r'C:\Users\15129\Desktop\毕业设计'
GRAPH = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '事件抽取与知识图谱', '图谱导出', 'v2.1_v1_3')
CHUNKS = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '数据准备', '数据集', 'v2.1', 'chunks', 'chunks.jsonl')
OUT = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', 'C3_本体空列清单')


def log(m):
    print(m, flush=True)


def load_nodes():
    with io.open(os.path.join(GRAPH, 'nodes.csv'), encoding='utf-8') as fh:
        return list(csv.DictReader(fh))


def load_chunks():
    rows = []
    with io.open(CHUNKS, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                rows.append(r)
    return rows


def esc(s):
    return re.escape(str(s or ''))


# ---------------- role_title：人名 ± 窗口内称谓模式 ----------------
TITLE_DICT = [
    '董事长', '副董事长', '总经理', '副总经理', '首席执行官', '总裁', '副总裁',
    '董事会秘书', '财务总监', '监事会主席', '监事', '独立董事', '独立非执行董事',
    '非执行董事', '执行董事', '董事', '职工代表监事', '首席财务官', '总工程师',
    '副总经理（主持工作）', '行长', '副行长', '经理', '主任', '主席',
]
VERB_PAT = r'(?:选举|推选|聘任|聘用|任命|委派|推举|聘请|获聘|聘任为)'


def rule_role_title(persons, chunks):
    out = []
    hit = 0
    verb_hits = dict_hits = 0
    for p in persons:
        name = (p.get('person_name') or '').strip()
        if not name or len(name) < 2 or len(name) > 6:
            continue
        pat_verb = re.compile(r'%s[^。]{0,40}?%s[^。]{0,6}?为\s*([^\s，。；、、）)]{2,18})' % (VERB_PAT, esc(name)))
        pat_titl = re.compile(r'%s(?:先生|女士|博士)?[^。]{0,14}?(担任|出任|上任|任)[^。]{0,8}?([^\s，。；、）)]{2,18})' % esc(name))
        found = None
        for ch in chunks:
            text = ch.get('content') or ''
            if name not in text:
                continue
            m = pat_verb.search(text)
            if m and name in text[max(0, m.start() - 40):m.end() + 10]:
                found = (m.group(1).strip(), ch, '称谓动词模式', text[max(0, m.start() - 30):m.end() + 6])
                verb_hits += 1
                break
            m2 = pat_titl.search(text)
            if m2 and name in text[max(0, m2.start() - 30):m2.end() + 10]:
                found = (m2.group(2).strip(), ch, '担任模式', text[max(0, m2.start() - 30):m2.end() + 6])
                verb_hits += 1
                break
        if not found:
            # 词典兜底：人名 ±25 字窗口出现职务词
            for ch in chunks:
                text = ch.get('content') or ''
                k = text.find(name)
                if k < 0:
                    continue
                win = text[max(0, k - 25):k + len(name) + 25]
                for tit in TITLE_DICT:
                    j = win.find(tit)
                    if j >= 0 and abs((win.index(name) if name in win else 0) - j) <= 25:
                        found = (tit, ch, '职务词典兜底', win)
                        dict_hits += 1
                        break
                if found:
                    break
        if found:
            hit += 1
            val, ch, rule, quote = found
            out.append({'node_id': p['node_id'], 'person_name': name, 'proposed_role_title': val,
                        'rule': rule, 'chunk_id': ch.get('chunk_id'), 'quote': quote[-160:]})
    return out, {'total': len(persons), 'hit': hit, 'verb_hits': verb_hits, 'dict_hits': dict_hits}


# ---------------- institution_type：机构名词典分类 ----------------
TYPE_RULES = [
    ('监管机构', r'证监会|银保监|金融监督管理|金融监管局|市场监管|发展和改革|发展改革委|财政部|中国人民银行|国资委|工业和信息化|生态环境|住房和城乡建设|交通运输|农业农村|卫生健康|国家能源局|应急管理|审计署|统计局'),
    ('交易所', r'证券交易所|期货交易所|交易所'),
    ('银行', r'银行'),
    ('证券公司', r'证券(?:股份|有限)?(?:公司)?|券商'),
    ('保险', r'保险'),
    ('基金', r'基金'),
    ('信托', r'信托'),
    ('评级机构', r'评级|资信评估|信用评级'),
    ('协会', r'协会|联合会|学会|商会'),
    ('研究院', r'研究院|研究所|大学|学院'),
    ('会计师事务所', r'会计师事务所'),
    ('律师事务所', r'律师事务所'),
]


def rule_institution_type(institutions):
    out = []
    hit = 0
    type_dist = Counter()
    for ins in institutions:
        name = (ins.get('institution_name') or '').strip()
        if not name:
            continue
        val = None
        for label, pat in TYPE_RULES:
            if re.search(pat, name):
                val = label
                break
        if val:
            hit += 1
            type_dist[val] += 1
            out.append({'node_id': ins['node_id'], 'institution_name': name,
                        'proposed_institution_type': val, 'rule': '机构名词典'})
    return out, {'total': len(institutions), 'hit': hit, 'type_dist': dict(type_dist)}


# ---------------- issuer：政策名关联的发文机关模式 ----------------
ISSUER_PAT = re.compile(
    r'([\u4e00-\u9fff]{2,22}?(?:人民政府|发展和改革委员会|发展改革委|财政部|中国人民银行|国资委|'
    r'工业和信息化部|商务部|住房和城乡建设部|生态环境部|交通运输部|农业农村部|卫生健康委|'
    r'证券监督管理委员会|金融监督管理总局|市场监督管理局|国家能源局|应急管理部|税务总局|统计局))'
    r'[^。]{0,16}(?:印发|发布|出台|颁发|联合印发)')


def rule_issuer(policies, chunks, by_text_index):
    out = []
    hit = 0
    for pol in policies:
        pname = (pol.get('policy_name') or '').strip()
        if not pname:
            continue
        core = pname[:14] if len(pname) >= 6 else pname
        found = None
        for ch in chunks:
            text = ch.get('content') or ''
            if pname[:8] not in text and core not in text:
                continue
            # 窗口：政策名出现处 ±80 字内找发文机关模式
            for k in [m.start() for m in re.finditer(re.escape(pname[:8]), text)]:
                win = text[max(0, k - 80):k + len(pname) + 40]
                m = ISSUER_PAT.search(win) or re.search(
                    r'([\u4e00-\u9fff]{2,20}?(?:厅|局|委员会|办公室|政府))[^。]{0,12}(?:印发|发布|出台)', win)
                if m:
                    found = (m.group(1), ch, '印发机关模式', win)
                    break
            if found:
                break
        if found:
            hit += 1
            val, ch, rule, quote = found
            out.append({'node_id': pol['node_id'], 'policy_name': pname, 'proposed_issuer': val,
                        'rule': rule, 'chunk_id': ch.get('chunk_id'), 'quote': quote[-160:]})
    return out, {'total': len(policies), 'hit': hit}


def main():
    os.makedirs(OUT, exist_ok=True)
    nodes = load_nodes()
    chunks = load_chunks()
    log('nodes=%d chunks=%d' % (len(nodes), len(chunks)))

    persons = [r for r in nodes if r['label'] == 'Person']
    institutions = [r for r in nodes if r['label'] == 'Institution']
    policies = [r for r in nodes if r['label'] == 'Policy']

    r1, s1 = rule_role_title(persons, chunks)
    r2, s2 = rule_institution_type(institutions)
    r3, s3 = rule_issuer(policies, chunks, None)

    for name, data in (('role_title', r1), ('institution_type', r2), ('issuer', r3)):
        p = os.path.join(OUT, '补齐数据_%s.jsonl' % name)
        with io.open(p, 'w', encoding='utf-8', newline='\n') as fh:
            for row in data:
                fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
        log('%s: %d 条 → %s' % (name, len(data), os.path.basename(p)))

    stats = {'role_title': s1, 'institution_type': s2, 'issuer': s3,
             'note': '全部为确定性规则口径、零模型调用；命中数据写入导出物前须人工逐条校验；'
                     '本数据不改动冻结导出物 v2.1_v1_3，下一版导出生效。'}
    io.open(os.path.join(OUT, '补齐统计.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(stats, ensure_ascii=False, indent=1, sort_keys=True))
    log('统计: %s' % json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())