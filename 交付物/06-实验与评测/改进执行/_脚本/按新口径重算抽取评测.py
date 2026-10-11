# -*- coding: utf-8 -*-
"""用三模型共识金标准重算 RQ1 抽取评测（零模型调用、零联网）

设计要点：**判据零改动**——本脚本 import 冻结的《工具/评测抽取.py》，
只把它的主口径参照集（REF_REPAIRED）换成我们生成的三模型共识金标准，
其余（键口径、micro 聚合、主/宽松两判据、比对函数）全部复用，
因此新读数与论文旧读数**完全可比**，差异只来自"对照物换了"。

产出（只写本目录）：
  新口径抽取指标.json     ← 含新旧并列读数，便于逐项对照
  新旧读数对照.md         ← 自动生成的新旧对照表
"""
from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
from collections import OrderedDict

ROOT = r'C:\Users\15129\Desktop\毕业设计'
EVAL_SCRIPT = os.path.join(ROOT, '交付物', '06-实验与评测', '工具', '评测抽取.py')
GOLD = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', '三模型金标准')
CONSENSUS = os.path.join(GOLD, '金标准参照集')
OUT = GOLD

CLS_CN = {'entities': '实体', 'events': '事件', 'relations': '关系', 'times': '时间'}
V_MAIN, V_LOOSE = 'main', 'quote_pair'


def log(msg):
    print('[newcaliber] %s' % msg, flush=True)


def load_eval_module():
    spec = importlib.util.spec_from_file_location('eval_extract', EVAL_SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules['eval_extract'] = m
    spec.loader.exec_module(m)
    return m


def prf(cell):
    tp, fp, fn = cell['tp'], cell['fp'], cell['fn']
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


def main():
    m = load_eval_module()
    log('已加载冻结评测脚本（判据零改动）')

    m.self_check_normalization()
    doc_chunks = m.load_doc_chunks()
    items = m.load_eval_items(doc_chunks)

    ref_consensus = {
        'dev': os.path.join(CONSENSUS, 'dev.auto.consensus.jsonl'),
        'test': os.path.join(CONSENSUS, 'test.auto.consensus.jsonl'),
    }
    for sp, p in ref_consensus.items():
        if not os.path.isfile(p):
            log('缺少共识参照集: %s' % p)
            return 1
    ref_gold = m.load_reference(ref_consensus)
    if set(ref_gold) != set(items):
        log('❌ 共识参照集条目集合与评测条目集合不一致（%d vs %d）' % (len(ref_gold), len(items)))
        return 1
    log('共识参照集条目集合校验通过: %d 条' % len(ref_gold))

    docs = m.load_system()
    _, backfill_map = m.load_backfill()
    ref_facts, _ = m.build_reference_facts(ref_gold)
    sys_chunks = m.build_system_facts(docs)
    res = m.run(items, ref_facts, sys_chunks, backfill_map)
    log('新口径复算完成')

    # —— 新旧并列（res["metrics"][split][cls][variant] 已是算好的 P/R/F1）——
    old_ref, _ = m.build_reference_facts(m.load_reference(m.REF_REPAIRED))
    res_old = m.run(items, old_ref, sys_chunks, backfill_map)

    SPLITS = list(m.SPLITS) + [m.SPLIT_TOTAL]
    rows = []
    for cls in m.CLASSES:
        for split in SPLITS:
            om = res_old['metrics'][split][cls].get(V_MAIN)
            nm = res['metrics'][split][cls].get(V_MAIN)
            if not om or not nm:
                continue
            oq = res_old['metrics'][split][cls].get(V_LOOSE) or {}
            nq = res['metrics'][split][cls].get(V_LOOSE) or {}
            rows.append(OrderedDict([
                ('task', CLS_CN[cls]), ('split', split),
                ('old_main', {'p': om['precision'], 'r': om['recall'], 'f1': om['f1'],
                              'tp': om['tp'], 'fp': om['fp'], 'fn': om['fn'],
                              'ref_n': om.get('support_reference')}),
                ('old_loose_f1', oq.get('f1')),
                ('new_main', {'p': nm['precision'], 'r': nm['recall'], 'f1': nm['f1'],
                              'tp': nm['tp'], 'fp': nm['fp'], 'fn': nm['fn'],
                              'ref_n': nm.get('support_reference')}),
                ('new_loose_f1', nq.get('f1')),
            ]))

    payload = OrderedDict([
        ('schema', 'stage10-extraction-eval-consensus-1.0'),
        ('title', 'RQ1 抽取评测读数（金标准·三模型综合 vs 旧·单模型参照集）'),
        ('caliber', OrderedDict([
            ('new_label', '金标准（三模型综合）口径'),
            ('members', ['deepseek-flash', 'kimi-k2.7-code', 'glm-5.3-flash']),
            ('consensus_rule', '逐条事实被 ≥2/3 家认领即入金标准；字段值取优先级最高者（deepseek→kimi→glm）'),
            ('reference_new', '改进执行/三模型金标准/金标准参照集/{dev,test}.auto.consensus.jsonl'),
            ('reference_old', '04-…/抽取评测集/v2.1/自动标注/提准/{dev,test}.auto.repaired.jsonl（deepseek-flash 单模型）'),
            ('note', '判据与聚合口径完全一致（复用冻结《评测抽取.py》），唯一差异是对照物；两套读数并列，不互相替换。'),
            ('model_calls', 0),
        ])),
        ('gold_sizes', OrderedDict(
            (CLS_CN[c], sum(len(ref_facts[i][c]) for i in items)) for c in m.CLASSES)),
        ('rows', rows),
    ])
    p_json = os.path.join(OUT, '新口径抽取指标.json')
    io.open(p_json, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(payload, ensure_ascii=False, indent=1))

    lines = ['# 新旧抽取读数对照（金标准·三模型综合 vs 旧·单模型参照集）', '',
             '> **判据与聚合口径完全一致**（复用冻结《工具/评测抽取.py》），唯一差异是对照物。',
             '> 旧＝单模型参照集（deepseek-flash，deepseek 同源自证）；新＝三模型共识金标准（≥2/3 认领）。',
             '> **两套读数并列报告，不互相替换。**', '',
             '| 任务 | 分段 | 旧 P | 旧 R | 旧 F1 | 旧宽松F1 | 新 P | 新 R | 新 F1 | 新宽松F1 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in rows:
        om, nm = r['old_main'], r['new_main']
        lines.append('| %s | %s | %.4f | %.4f | **%.4f** | %.4f | %.4f | %.4f | **%.4f** | %.4f |' % (
            r['task'], r['split'], om['p'], om['r'], om['f1'], r['old_loose_f1'] or 0,
            nm['p'], nm['r'], nm['f1'], r['new_loose_f1'] or 0))
    p_md = os.path.join(OUT, '新旧读数对照.md')
    io.open(p_md, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')

    log('金标准规模: %s' % payload['gold_sizes'])
    for r in rows:
        if r['split'] == 'total':
            log('  %s 旧F1=%.4f → 新F1=%.4f' % (r['task'], r['old_main']['f1'], r['new_main']['f1']))
    log('输出: %s / %s' % (os.path.basename(p_json), os.path.basename(p_md)))
    return 0


if __name__ == '__main__':
    sys.exit(main())