# -*- coding: utf-8 -*-
"""三模型共识金标准 → 标准参照集格式（零模型调用、零联网）

用途：让**冻结的**《工具/评测抽取.py》零改动跑一遍，得到与旧读数**完全可比**的新读数——
因为判据、键口径、比对逻辑全部复用原脚本，本脚本只负责"把三模型共识变成一个标注文件"。

做法：对每个 item_id，分别取三家标注中**被 ≥2 家认领**的条目作为金标准条目；
条目的字段值取"首个认领者（按 deepseek→kimi→glm 优先级）"，并记录支持度。
输出格式与 `自动标注/提准/{dev,test}.auto.repaired.jsonl` 一致（顶层含 `annotation`）。

产出（只写本目录）：
  金标准参照集/{dev,test}.auto.consensus.jsonl   ← 可直接喂给评测抽取.py
  金标准参照集/共识说明.json                     ← 支持度统计
"""
from __future__ import annotations

import io
import json
import os
from collections import Counter, OrderedDict

ROOT = r'C:\Users\15129\Desktop\毕业设计'
GOLD = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', '三模型金标准')
EVAL_DIR = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '数据准备', '数据集', '抽取评测集', 'v2.1')
DS_REF = os.path.join(EVAL_DIR, '自动标注', '提准')
KIMI = os.path.join(GOLD, '标注_kimi')
GLM = os.path.join(GOLD, '标注_glm')
OUT = os.path.join(GOLD, '金标准参照集')

MEMBERS = ('deepseek', 'kimi', 'glm')     # 优先级顺序（认领冲突时取靠前者）
DIRS = {'deepseek': DS_REF, 'kimi': KIMI, 'glm': GLM}


def log(msg):
    print('[consensus] %s' % msg, flush=True)


def read_jsonl(path):
    rows = []
    with io.open(path, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_member(label):
    base = DIRS[label]
    out = {}
    for split in ('dev', 'test'):
        suffix = '.auto.repaired.jsonl' if label == 'deepseek' else '.auto.jsonl'
        p = os.path.join(base, '%s%s' % (split, suffix))
        if os.path.isfile(p):
            for rec in read_jsonl(p):
                out[rec['item_id']] = rec
    return out


def ent_key(e):
    """实体键：类型 + 首个可用名字字段（与 compare.entity_key 同口径的简化版）。

    这里**不复用** compare 模块（避免跨目录依赖），而是按同一 NAME_FIELDS 顺序取名；
    名字规范化交由评测脚本的 norm_name 处理（此处只做去空白与外层剥离的等价近似）。
    """
    NAME_FIELDS = {
        'Company': ['company_name', 'short_name'],
        'Person': ['person_name'],
        'Industry': ['industry_name'],
        'Institution': ['institution_name'],
        'Policy': ['policy_name'],
    }
    et = e.get('entity_type')
    for f in NAME_FIELDS.get(et) or []:
        v = e.get(f)
        if isinstance(v, str) and v.strip():
            return (et, v.strip())
    for v in (e.get('aliases') or []):
        if isinstance(v, str) and v.strip():
            return (et, v.strip())
    return (et, str(e.get('entity_ref') or ''))


def ev_key(e):
    return (e.get('event_type'), str(e.get('event_name') or '').strip())


def rel_key(r, ent_by_ref):
    def side(p):
        ref = r.get(p + '_ref')
        if ref in ent_by_ref:
            e = ent_by_ref[ref]
            et, nm = ent_key(e)
            return '%s|%s' % (et, nm)
        return str(r.get(p + '_label') or ref or '')
    return (r.get('relation'), side('from'), side('to'))


def main():
    os.makedirs(OUT, exist_ok=True)
    anns = {m: load_member(m) for m in MEMBERS}
    log('成员条目数: %s' % {m: len(v) for m, v in anns.items()})
    all_ids = sorted(set().union(*[set(v.keys()) for v in anns.values()]))
    log('并集条目: %d' % len(all_ids))

    support_stat = Counter()
    out_by_split = {'dev': [], 'test': []}

    for item_id in all_ids:
        per_member = {}
        for m in MEMBERS:
            rec = anns[m].get(item_id)
            per_member[m] = (rec.get('annotation') or {}) if rec else {}

        def consensus(kind, keyfn):
            """返回被 >=2 家认领的条目（认领值取优先级最高的成员）。

            注意：同一成员可能对同一 key 重复输出（多角色/多证据行），
            认领数必须按**成员去重**，否则会把"一家多行"误算成"多家共识"。
            """
            claimed = OrderedDict()   # key -> {member: obj}
            for m in MEMBERS:
                ann = per_member[m]
                objs = ann.get(kind) or []
                if kind == 'relations':
                    by_ref = {e.get('entity_ref'): e for e in (ann.get('entities') or [])
                              if isinstance(e, dict)}
                    for o in objs:
                        if not isinstance(o, dict):
                            continue
                        k = keyfn(o, by_ref)
                        claimed.setdefault(k, OrderedDict()).setdefault(m, o)
                else:
                    for o in objs:
                        if not isinstance(o, dict):
                            continue
                        k = keyfn(o)
                        claimed.setdefault(k, OrderedDict()).setdefault(m, o)
            gold = []
            for k, by_member in claimed.items():
                if len(by_member) >= 2:          # 按成员去重后的家数
                    support_stat[(kind, len(by_member))] += 1
                    gold.append((k, by_member))
            return gold

        ents = consensus('entities', lambda e: ent_key(e))
        evs = consensus('events', lambda e: ev_key(e))
        rels = consensus('relations', lambda r, by_ref: rel_key(r, by_ref))

        # 时间类：按 value 共识（同样按成员去重）
        time_claims = OrderedDict()
        for m in MEMBERS:
            for t in (per_member[m].get('times') or []):
                if not isinstance(t, dict):
                    continue
                time_claims.setdefault((t.get('time_type'), t.get('value')), OrderedDict()).setdefault(m, t)
        times = [(k, by_member) for k, by_member in time_claims.items() if len(by_member) >= 2]
        for _, by_member in times:
            support_stat[('times', len(by_member))] += 1

        def pick(by_member):
            """字段值取优先级最高的认领成员（deepseek→kimi→glm）。"""
            for m in MEMBERS:
                if m in by_member:
                    return by_member[m]
            return list(by_member.values())[0]

        def members_of(by_member):
            return [m for m in MEMBERS if m in by_member]

        # 组装标准 annotation（字段名与参照集一致）
        ent_list, ev_list, rel_list, time_list = [], [], [], []
        ref_i = 0
        for k, by_member in ents:
            o = pick(by_member)
            ref_i += 1
            # 完整保留原对象的全部字段（company_name / stock_code / aliases 等），
            # 只重写 entity_ref 与 _support——评测脚本的实体键依赖这些名字字段。
            row = OrderedDict(o)
            row['entity_ref'] = 'E%d' % ref_i
            row['_support'] = members_of(by_member)
            ent_list.append(row)
        ref_v = 0
        for k, by_member in evs:
            o = pick(by_member)
            ref_v += 1
            row = OrderedDict(o)
            row['event_ref'] = 'V%d' % ref_v
            row['_support'] = members_of(by_member)
            ev_list.append(row)
        for k, by_member in rels:
            o = pick(by_member)
            row = OrderedDict(o)
            row['_support'] = members_of(by_member)
            rel_list.append(row)
        for k, by_member in times:
            o = pick(by_member)
            row = OrderedDict(o)
            row['time_type'] = k[0]
            row['value'] = k[1]
            row['_support'] = members_of(by_member)
            time_list.append(row)

        ann = OrderedDict([
            ('entities', ent_list), ('events', ev_list), ('relations', rel_list),
            ('times', time_list), ('ontology_boundary_log', []),
            ('notes', '三模型共识金标准（≥2/3 认领）'),
            ('status', 'consensus_gold'),
        ])

        # 端点重映射：共识实体的事件/实体 ref 已被重编号为 E*/V*，
        # 关系里的 from_ref/to_ref 必须同步改写，否则端点解析会落空。
        ref_map = {}
        for i, (k, by_member) in enumerate(ents, 1):
            src = pick(by_member)
            if src.get('entity_ref'):
                ref_map[src['entity_ref']] = 'E%d' % i
        for i, (k, by_member) in enumerate(evs, 1):
            src = pick(by_member)
            if src.get('event_ref'):
                ref_map[src['event_ref']] = 'V%d' % i
        for rel in rel_list:
            for side in ('from', 'to'):
                rf = '%s_ref' % side
                if rf in rel and rel[rf] in ref_map:
                    rel[rf] = ref_map[rel[rf]]

        # 以 deepseek（优先）的原始行做骨架，替换 annotation
        base_rec = anns['deepseek'].get(item_id) or anns['kimi'].get(item_id) or anns['glm'].get(item_id)
        row = OrderedDict()
        for k, v in base_rec.items():
            if k == 'annotation':
                continue
            row[k] = v
        row['annotation'] = ann
        split = base_rec.get('split') or ('dev' if item_id.startswith('DEV') else 'test')
        out_by_split.setdefault(split, []).append(row)

    for split, rows in out_by_split.items():
        p = os.path.join(OUT, '%s.auto.consensus.jsonl' % split)
        with io.open(p, 'w', encoding='utf-8', newline='\n') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')
        log('%s: %d 条 → %s' % (split, len(rows), os.path.basename(p)))

    io.open(os.path.join(OUT, '共识说明.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps({'支持度分布': {'%s_%d家' % (k[0], k[1]): v for k, v in sorted(support_stat.items())}},
                   ensure_ascii=False, indent=1))
    log('共识条目支持度: %s' % dict(support_stat))
    log('输出目录: %s' % OUT)


if __name__ == '__main__':
    main()