# -*- coding: utf-8 -*-
"""新口径四张表的逐格机械校验（零模型调用、零联网）

对论文第六章的四张口径表做**逐格对照**：
  表 6-2（抽取·金标准主表） ←→ 改进执行/三模型金标准/新口径抽取指标.json（rows 结构化对照）
  表 6-3（抽取·对照口径）   ←→ 交付物/06-实验与评测/抽取评测/抽取评测指标.json（文本命中，与 F1 门禁同法）
  表 6-15（问答·三模型主表）←→ 评分综合汇总.json by_group（新值）＋ 问答评分_正式/评分汇总.json（括号对照值）
  表 6-22（12.8 判定表）    ←→ 评分综合汇总.json judgement（AA 新值）＋ A_vs_C_对照.json subsets_named_core（CER）

退出码 0＝全部逐格一致；1＝存在 MISMATCH（打印逐格清单）。
本脚本可反复重跑，作为口径表格的常驻守门工具。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys
from collections import OrderedDict

ROOT = r'C:\Users\15129\Desktop\毕业设计'
CH6 = os.path.join(ROOT, '交付物', '01-论文', '_分章源文件', '06-第六章-系统测试与实验分析.md')
GOLD = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', '三模型金标准')
NEW_EXT = os.path.join(GOLD, '新口径抽取指标.json')
OLD_EXT = os.path.join(ROOT, '交付物', '06-实验与评测', '抽取评测', '抽取评测指标.json')
SYN = os.path.join(GOLD, '评分综合汇总.json')
OLD_QA = os.path.join(ROOT, '交付物', '06-实验与评测', '问答评分_正式', '评分汇总.json')
AC = os.path.join(ROOT, '交付物', '06-实验与评测', '对照产出_正式', 'A_vs_C_对照.json')

TASK_CN = {'实体': 'entity', '事件': 'event', '关系': 'relation', '时间': 'time'}
SPLIT_CN = {'开发集': 'dev', '测试集': 'test', '合计': '合计'}


def log(msg):
    print(msg, flush=True)


def load(p):
    return json.load(io.open(p, encoding='utf-8'))


def section(t, start_kw, end_kws):
    i = t.find(start_kw)
    if i < 0:
        return ''
    j = len(t)
    for kw in end_kws:
        k = t.find(kw, i + 1)
        if 0 <= k < j:
            j = k
    return t[i:j]


def parse_rows(block):
    rows = [l for l in block.split('\n') if l.strip().startswith('|') and '---' not in l]
    return rows[1:]   # [0] 是表头；分隔线已被过滤


def cells(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def feq(a, b, tol=5e-5):
    a = str(a).strip('*').strip()
    b = str(b).strip('*').strip()
    try:
        return abs(float(a) - float(b)) <= tol
    except ValueError:
        return a == b


def main():
    problems = []
    checked = 0
    ch6 = io.open(CH6, encoding='utf-8').read()
    new_ext = load(NEW_EXT)
    syn = load(SYN)
    old_qa = load(OLD_QA)
    ac = load(AC)

    # ---------- 表 6-2（新口径抽取主表）----------
    blk = section(ch6, '**表 6-2', ['**表 6-3', '**匹配判据', '两套读数的对照'])
    rows = parse_rows(blk)
    by_key = {(r['task'], r['split']): r for r in new_ext['rows']}
    for line in rows:
        c = cells(line)
        task, split = c[0], c[1]
        key = (task, SPLIT_CN[split])   # json rows 的 task 为中文、split 为 dev/test/合计
        ref = by_key.get(key)
        if not ref:
            problems.append('表6-2 %s/%s：新口径 json 无对应行' % (task, split))
            continue
        nm = ref['new_main']
        for label, got, want in (('TP', c[2], nm['tp']), ('FP', c[3], nm['fp']), ('FN', c[4], nm['fn'])):
            checked += 1
            if int(got) != int(want):
                problems.append('表6-2 %s/%s %s: 表=%s json=%s' % (task, split, label, got, want))
        for label, got, want in (('P', c[5], nm['p']), ('R', c[6], nm['r']), ('F1', c[7], nm['f1']),
                                 ('宽松F1', c[8], ref['new_loose_f1'])):
            checked += 1
            if not feq(got, want):
                problems.append('表6-2 %s/%s %s: 表=%s json=%s' % (task, split, label, got, want))
    log('表 6-2：%d 行逐格校验完成' % len(rows))

    # ---------- 表 6-3（对照口径）----------
    blk = section(ch6, '**表 6-3', ['两套读数的对照给出三条', '**评分主体'])
    rows = parse_rows(blk)
    old_res = (load(OLD_EXT).get('results') or {}).get('metrics') or {}
    CLS_KEY = {'实体': 'entities', '事件': 'events', '关系': 'relations', '时间': 'times'}
    for line in rows:
        c = cells(line)
        task, split = c[0], '合计'   # 表 6-3 只报合计段、无分段列
        mm = (old_res.get(split) or {}).get(CLS_KEY[task]) or {}
        main_v, loose_v = mm.get('main') or {}, mm.get('quote_pair') or {}
        pairs = [('命中', c[1], main_v.get('tp')), ('误报', c[2], main_v.get('fp')), ('漏报', c[3], main_v.get('fn')),
                 ('P', c[4], main_v.get('precision')), ('R', c[5], main_v.get('recall')), ('F1', c[6], main_v.get('f1')),
                 ('宽松F1', c[7], loose_v.get('f1'))]
        for label, got, want in pairs:
            checked += 1
            if want is None or not feq(got.strip('*'), want):
                problems.append('表6-3 %s/%s %s: 表=%s json=%s' % (task, split, label, got, want))
    log('表 6-3：%d 行结构化对照完成' % len(rows))

    # ---------- 表 6-15（问答三模型主表）----------
    blk = section(ch6, '**表 6-15', ['**表 6-16'])
    rows = parse_rows(blk)
    old_by_group = old_qa.get('by_group') or {}
    for line in rows:
        c = cells(line)
        g = c[0][0]  # 'A 组 · ...' → 'A'
        dims = [('AA', c[1], 'answer_accuracy'), ('Comp', c[2], 'completeness'), ('Faith', c[3], 'faithfulness')]
        for label, cell, dim in dims:
            mm = re.search(r'([0-9.]+)（([0-9.]+)）', cell)
            if not mm:
                problems.append('表6-15 %s %s：格式不含（对照）值：%r' % (g, label, cell))
                continue
            new_v, old_v = mm.group(1), mm.group(2)
            checked += 1
            want_new = (syn.get('by_group') or {}).get(g, {}).get(dim)
            if want_new is None or not feq(new_v, want_new):
                problems.append('表6-15 %s %s 新值: 表=%s json=%s' % (g, label, new_v, want_new))
            checked += 1
            # 旧对照值：旧汇总结构 by_group[g].dimensions[dim].mean
            want_old = ((((old_by_group.get(g) or {}).get('dimensions') or {}).get(dim)) or {}).get('mean')
            if want_old is None or not feq(old_v, want_old):
                problems.append('表6-15 %s %s 对照值: 表=%s 旧json=%s' % (g, label, old_v, want_old))
    log('表 6-15：%d 行逐格校验完成' % len(rows))

    # ---------- 表 6-22（12.8 判定表）----------
    blk = section(ch6, '**表 6-22', ['（AA 为三模型综合口径'])
    rows = parse_rows(blk)
    judge = {r['subset']: r for r in (syn.get('judgement_12_8_answer_accuracy_half_three_model') or [])}
    old_judge = {r.get('subset'): r for r in (old_qa.get('judgement_12_8_answer_accuracy_half') or [])}
    snc = ac.get('subsets_named_core') or {}
    for line in rows:
        c = cells(line)
        sub = c[0]
        checked += 1
        if int(c[1]) != {'关系型': 36, '多跳型': 72, '时序型': 54}[sub]:
            problems.append('表6-22 %s 题数: %s' % (sub, c[1]))
        # CER 两列 ← A_vs_C_对照.json
        for col, g in ((2, 'A'), (3, 'C')):
            checked += 1
            want = ((snc.get(sub) or {}).get(g) or {}).get('complete_evidence_recall_at_k')
            if want is None or not feq(c[col], want):
                problems.append('表6-22 %s CER@K(%s): 表=%s json=%s' % (sub, g, c[col], want))
        # AA 两列 ← 三模型 judgement
        checked += 1
        if sub not in judge or not feq(c[5], judge[sub]['answer_accuracy_A']):
            problems.append('表6-22 %s AA(A): 表=%s json=%s' % (sub, c[5], judge.get(sub, {}).get('answer_accuracy_A')))
        checked += 1
        if sub not in judge or not feq(c[6], judge[sub]['answer_accuracy_C']):
            problems.append('表6-22 %s AA(C): 表=%s json=%s' % (sub, c[6], judge.get(sub, {}).get('answer_accuracy_C')))
        # ② Δ 列
        checked += 1
        m = re.search(r'＋([0-9.]+)', c[7])
        if not m or not feq(m.group(1), judge.get(sub, {}).get('gap_C_minus_A')):
            problems.append('表6-22 %s Δ: 表=%s json=%s' % (sub, c[7], judge.get(sub, {}).get('gap_C_minus_A')))
    log('表 6-22：%d 行逐格校验完成' % len(rows))

    log('')
    log('共校验 %d 格；问题 %d 项' % (checked, len(problems)))
    for pb in problems:
        log('  MISMATCH: %s' % pb)
    out = os.path.join(GOLD, '新口径表格逐格校验.json')
    io.open(out, 'w', encoding='utf-8', newline='\n').write(json.dumps(
        {'checked_cells': checked, 'problems': problems,
         'result': 'OK' if not problems else 'MISMATCH'}, ensure_ascii=False, indent=1))
    log('结果落盘: %s' % out)
    return 0 if not problems else 1


if __name__ == '__main__':
    sys.exit(main())