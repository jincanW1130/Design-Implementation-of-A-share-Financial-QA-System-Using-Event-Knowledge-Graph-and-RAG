# -*- coding: utf-8 -*-
"""三模型综合合成（零模型调用、零联网）

输入（只读）：
  抽取侧：deepseek=既有主参照集（提准）；kimi/glm=本目录 标注_kimi/标注_glm 产物
  问答侧：本目录 评分/评分记录_{deepseek,kimi,zhipu}.jsonl（全量运行产物）
输出（只写本目录）：
  综合金标准_抽取.jsonl / 综合评分.jsonl / 综合读数汇总.json / 三模型综合读数报告.md

口径（复用项目既有的跨模型匹配键，见 auto_annotate_compare.py）：
  实体键＝类型＋规范化名字；事件键＝类型＋规范化事件名；关系键＝两端复合；times 键＝value 值
  条目级金标准＝≥2/3 家出现（共识门限）；属性级无共识处标 unresolved、不猜测
  问答综合分＝三家均值（主）与多数/中位（辅）；有效家数<3 标 degraded

用法：
  python 三模型_综合.py --extract    # 抽取侧综合（标注全量完成后）
  python 三模型_综合.py --qa         # 问答侧综合（评分全量完成后）
  python 三模型_综合.py --report     # 汇总报告（依赖前两项产物）
"""
from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import io
import json
import os
import statistics
import sys
from collections import Counter, OrderedDict

ROOT = r'C:\Users\15129\Desktop\毕业设计'
EXTRACT_DIR = os.path.join(ROOT, '交付物', '03-代码', '抽取与图谱')
DATASET_DIR = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '数据准备', '数据集', '抽取评测集', 'v2.1')
GOLD_DIR = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', '三模型金标准')
ANN_DS = os.path.join(DATASET_DIR, '自动标注', '提准')          # deepseek-flash 主参照集
ANN_KIMI = os.path.join(GOLD_DIR, '标注_kimi')
ANN_GLM = os.path.join(GOLD_DIR, '标注_glm')
QA_DIR = os.path.join(GOLD_DIR, '评分')

MEMBERS = ('deepseek', 'kimi', 'glm')
CATS = ('entities', 'events', 'relations', 'times')
DIMS = ('answer_accuracy', 'completeness', 'faithfulness')


def log(msg: str) -> None:
    print('[%s] %s' % (_dt.datetime.now().strftime('%H:%M:%S'), msg), flush=True)


def load_cmp():
    if EXTRACT_DIR not in sys.path:
        sys.path.insert(0, EXTRACT_DIR)
    spec = importlib.util.spec_from_file_location('auto_annotate_compare', os.path.join(EXTRACT_DIR, 'auto_annotate_compare.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules['auto_annotate_compare'] = mod
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path):
    rows = []
    with io.open(path, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_ann_member(label: str) -> dict:
    base = {'deepseek': ANN_DS, 'kimi': ANN_KIMI, 'glm': ANN_GLM}[label]
    out = {}
    for split in ('dev', 'test'):
        p = os.path.join(base, '%s.auto.jsonl' % split)
        if label == 'deepseek':
            p = os.path.join(base, '%s.auto.repaired.jsonl' % split)
        if not os.path.isfile(p):
            continue
        for rec in read_jsonl(p):
            out[rec['item_id']] = rec
    return out


def _event_loose_key(ev: dict) -> str:
    """事件宽松键：只保留 `event_type` 与事件名里的核心名词（去数字/去修饰）。

    严格键是 `类型|完整事件名`，但事件名是模型自由文本、三家措辞差异极大
    （实测严格共识仅 50/750），故另给一个宽松键用于观察"同一事实、不同措辞"的共识度。
    """
    import re as _re
    name = str(ev.get('event_name') or '')
    core = _re.sub(r'[0-9年月日%．.,，、（）()《》"\'\s\-—_]', '', name)
    # 取最长的连续中文/英文片段（≥2 字）作核心
    parts = [p for p in _re.findall(r'[\u4e00-\u9fffA-Za-z]{2,}', core) if len(p) >= 2]
    key = max(parts, key=len) if parts else core[:8]
    return '%s|%s' % (ev.get('event_type'), key)


def extract_synthesis(cmp_mod) -> int:
    anns = {m: load_ann_member(m) for m in MEMBERS}
    sizes = {m: len(v) for m, v in anns.items()}
    log('成员条目数: %s' % sizes)
    if sizes['kimi'] == 0 or sizes['glm'] == 0:
        log('⚠ kimi/glm 标注尚未完成（0 条），暂不可综合。')
        return 1

    all_items = sorted(set().union(*[set(v.keys()) for v in anns.values()]))

    def key_sets_of(member, item_id):
        rec = anns[member].get(item_id)
        if rec is None:
            return None
        ann = rec.get('annotation') or {}
        ks = cmp_mod.key_sets(ann)
        # 追加事件宽松键集合（观察"同事实不同措辞"的共识度）
        ks['events_loose'] = Counter(_event_loose_key(e) for e in cmp_mod.dicts(ann.get('events')))
        return ks

    out_rows = []
    agg = {m: Counter() for m in MEMBERS}
    cons = Counter()
    pair_jac = {tuple(sorted(p)): [] for p in [(a, b) for a in MEMBERS for b in MEMBERS if a < b]}
    pair_strict = {k: 0 for k in pair_jac}

    for item_id in all_items:
        ks = {m: key_sets_of(m, item_id) for m in MEMBERS}
        row = OrderedDict([('item_id', item_id),
                           ('chunk_id', (anns['deepseek'].get(item_id) or anns['kimi'].get(item_id) or {}).get('chunk_id')),
                           ('split', (anns['deepseek'].get(item_id) or {}).get('split'))])
        cons_row = OrderedDict()
        # strict 只按"条目"计一次（跨类别全等的条目对），故先收集该条目的各类集合
        # 展示与共识用类别（含事件宽松键；strict 判定只算四类严格键）
        DISPLAY_CATS = CATS + ('events_loose',)
        item_sets = {cat: {m: (set(ks[m][cat].keys()) if ks[m] is not None else set()) for m in MEMBERS}
                     for cat in DISPLAY_CATS}
        for cat in DISPLAY_CATS:
            sets = item_sets[cat]
            union = set().union(*sets.values())
            for m in MEMBERS:
                agg[m][cat] += len(sets[m])
            gold = sorted(k for k in union if sum(1 for m in MEMBERS if k in sets[m]) >= 2)
            cons[cat] += len(gold)
            detail = {}
            for k in sorted(union):
                support = [m for m in MEMBERS if k in sets[m]]
                if len(support) >= 2:
                    detail[k] = support
            cons_row[cat] = OrderedDict([('n_gold', len(gold)), ('keys', gold),
                                         ('n_union', len(union)), ('support_detail', detail)])
            # 两两一致性（逐类别）
            for (a, b) in pair_jac:
                sa, sb = sets[a], sets[b]
                if not sa and not sb:
                    j = 1.0
                else:
                    j = len(sa & sb) / len(sa | sb) if (sa | sb) else 1.0
                pair_jac[(a, b)].append(j)
        # strict（逐条目·跨类别全等）只加一次
        for (a, b) in pair_jac:
            if all(item_sets[cat][a] == item_sets[cat][b] for cat in CATS):
                pair_strict[(a, b)] += 1
        row['consensus'] = cons_row
        out_rows.append(row)

    agg_out = {
        'members': {m: dict(agg[m]) for m in MEMBERS},
        'consensus': dict(cons),
        'pairwise': {('%s-%s' % k): {'mean_jaccard': round(sum(v) / len(v), 4) if v else None,
                                     'strict_item_rate': round(pair_strict[k] / len(all_items), 4)}
                     for k, v in pair_jac.items()},
        'n_items': len(all_items),
    }
    with io.open(os.path.join(GOLD_DIR, '综合金标准_抽取.jsonl'), 'w', encoding='utf-8', newline='\n') as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
    io.open(os.path.join(GOLD_DIR, '抽取综合汇总.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(agg_out, ensure_ascii=False, indent=1, sort_keys=True))
    log('抽取综合完成：%d 条 → 综合金标准_抽取.jsonl' % len(out_rows))
    log('成员规模: %s' % agg_out['members'])
    log('共识规模: %s' % agg_out['consensus'])
    log('两两一致: %s' % agg_out['pairwise'])
    return 0


def qa_synthesis(dataset='formal') -> int:
    # 问答侧的评委槽位与文件命名：deepseek/kimi 与抽取侧同名；glm 在评分侧落盘名为 zhipu
    QA_SLOTS = (('deepseek', 'deepseek'), ('kimi', 'kimi'), ('glm', 'zhipu'))
    recs = {}
    for slot, fname in QA_SLOTS:
        suffix = '' if dataset == 'formal' else '_pr'
        qa_dir = QA_DIR if dataset == 'formal' else os.path.join(GOLD_DIR, '评分_预实验')
        p = os.path.join(qa_dir, '评分记录_%s%s.jsonl' % (fname, suffix))
        if not os.path.isfile(p):
            log('⚠ 缺少 %s（评分运行未完成？）' % p)
            return 1
        recs[slot] = {r['answer_key']: r for r in read_jsonl(p)}
    counts = {j: len(v) for j, v in recs.items()}
    log('评分记录数: %s' % counts)

    all_keys = sorted(set(recs['deepseek'].keys()) & set(recs['kimi'].keys()) & set(recs['glm'].keys()))
    log('三家共同覆盖答案: %d' % len(all_keys))

    out_rows = []
    agg = {}
    agree_stat = Counter()
    for key in all_keys:
        row = OrderedDict([('answer_key', key)])
        for dim in DIMS:
            vals = {}
            for j in MEMBERS:
                v = ((recs[j][key].get('scores') or {}).get(dim))
                vals[j] = v
            ok_vals = [v for v in vals.values() if isinstance(v, int)]
            n_ok = len(ok_vals)
            mean = round(sum(ok_vals) / n_ok, 4) if n_ok else None
            if n_ok == 3:
                mc = Counter(ok_vals).most_common()
                majority = mc[0][0] if mc[0][1] >= 2 else None
                spread = max(ok_vals) - min(ok_vals)
                if spread == 0:
                    agree_stat['all_equal'] += 1
                elif mc[0][1] == 2:
                    agree_stat['two_one'] += 1
                else:
                    agree_stat['all_diff'] += 1
                agreement = 'all3' if spread == 0 else ('majority2' if mc[0][1] == 2 else 'split')
            else:
                majority, agreement = None, 'degraded'
            row[dim] = OrderedDict([('scores', vals), ('mean', mean), ('majority', majority),
                                    ('agreement', agreement)])
        out_rows.append(row)

    for dim in DIMS:
        means = [r[dim]['mean'] for r in out_rows if r[dim]['mean'] is not None]
        agg[dim] = {'n': len(means), 'mean_of_means': round(sum(means) / len(means), 4) if means else None}
    # 按组均分
    by_group = {}
    for r in out_rows:
        g = r['answer_key'].split('__')[0]
        by_group.setdefault(g, []).append(r)
    group_stats = {}
    for g, rows_list in sorted(by_group.items()):
        group_stats[g] = {dim: round(sum(x[dim]['mean'] for x in rows_list if x[dim]['mean'] is not None)
                                     / len([x for x in rows_list if x[dim]['mean'] is not None]), 4)
                          for dim in DIMS}

    tag = '' if dataset == 'formal' else '_预实验'
    with io.open(os.path.join(GOLD_DIR, '综合评分%s.jsonl' % tag), 'w', encoding='utf-8', newline='\n') as fh:
        for r in out_rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
    # 12.8 判定（三模型综合口径）：核心 108 题三子集的 AA（A/C 均值与差值）。
    # 数据源：综合行（answer_key）→ deepseek 记录（qid）→ questions.jsonl（subset/类型标签）。
    qs_path = os.path.join(ROOT, '交付物', '06-实验与评测', '测试集', 'questions.jsonl')
    qs = {r['qid']: r for r in read_jsonl(qs_path)} if os.path.isfile(qs_path) else {}
    ds_recs = {}
    ds_path = os.path.join(QA_DIR, '评分记录_deepseek.jsonl')
    if os.path.isfile(ds_path):
        for r in read_jsonl(ds_path):
            ds_recs[r['answer_key']] = r
    core_sub = {}
    for r in out_rows:
        meta = ds_recs.get(r['answer_key']) or {}
        q = qs.get(meta.get('qid')) or {}
        if q.get('subset') != '核心':
            continue
        aa = r['answer_accuracy']['mean']
        if aa is None:
            continue
        for sname, pred in (('关系型', q.get('task_type') == '关系型'),
                            ('多跳型', int(q.get('gold_hop_depth') or 0) >= 1),
                            ('时序型', q.get('time_constraint') == '有')):
            if pred:
                core_sub.setdefault((sname, 'A' if r['answer_key'].startswith('A__') else
                                     ('C' if r['answer_key'].startswith('C__') else None)), []).append(aa)
    judgement = []
    for sname in ('关系型', '多跳型', '时序型'):
        a_list = core_sub.get((sname, 'A')) or []
        c_list = core_sub.get((sname, 'C')) or []
        if not a_list or not c_list:
            continue
        a = round(sum(a_list) / len(a_list), 4)
        c = round(sum(c_list) / len(c_list), 4)
        judgement.append(OrderedDict([('subset', sname), ('answer_accuracy_A', a),
                                      ('answer_accuracy_C', c),
                                      ('gap_C_minus_A', round(c - a, 4)),
                                      ('holds', bool(c >= a))]))
    gap = round((group_stats.get('C', {}).get('answer_accuracy') or 0)
              - (group_stats.get('A', {}).get('answer_accuracy') or 0), 4)
    summary = {'dataset': dataset, 'n_answers': len(out_rows), 'overall': agg, 'by_group': group_stats,
               'aa_gap_C_minus_A': gap,
               'agreement': dict(agree_stat),
               'judgement_12_8_answer_accuracy_half_three_model': judgement,
               'note': 'AA＝三模型综合均值口径；gap＝C−A。对照组口径见 交付物/06-实验与评测/问答评分_正式/评分汇总.json'}
    io.open(os.path.join(GOLD_DIR, '评分综合汇总%s.json' % tag), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(summary, ensure_ascii=False, indent=1, sort_keys=True))
    log('问答综合完成：%d 条' % len(out_rows))
    log('总体均分: %s' % agg)
    log('分组均分: %s' % group_stats)
    log('一致分布: %s' % dict(agree_stat))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--extract', action='store_true')
    ap.add_argument('--qa', action='store_true')
    ap.add_argument('--qa-pr', action='store_true', help='对预实验集评分做综合')
    ap.add_argument('--report', action='store_true')
    args = ap.parse_args()
    rc = 0
    if args.extract or not (args.extract or args.qa or args.report):
        rc |= extract_synthesis(load_cmp())
    if args.qa or not (args.extract or args.qa or args.report):
        rc |= qa_synthesis()
    if args.qa_pr:
        rc |= qa_synthesis('pr')
    return rc


if __name__ == '__main__':
    sys.exit(main())
