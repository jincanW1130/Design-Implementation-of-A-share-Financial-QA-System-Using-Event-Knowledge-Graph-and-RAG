# -*- coding: utf-8 -*-
"""B2：从 extracted.jsonl 与图谱导出物重算《16》第3／6／7／8节声明的全部数字。

只读工作区。输出 stdout（调用方重定向留档）。
"""
import csv
import hashlib
import io
import json
import os
import re
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
EXTRACT_DIR = os.path.join(ROOT, '代码', '抽取与图谱', '_全量', 'v2.1_v1_2')
EXPORT_DIR = os.path.join(ROOT, '阶段06-事件抽取与知识图谱', '图谱导出', 'v2.1_v1_2')
CACHE_DIR = os.path.join(ROOT, '阶段05-数据准备', '数据集', '_抽取缓存', 'v2.1_v1_2')
V21 = os.path.join(ROOT, '阶段05-数据准备', '数据集', 'v2.1')


def read_jsonl(path):
    out = []
    with io.open(path, encoding='utf-8') as f:
        for ln in f:
            ln = ln.strip()
            if ln:
                out.append(json.loads(ln))
    return out


def sha256_file(p):
    h = hashlib.sha256()
    with io.open(p, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def squash(s):
    return re.sub(r'\s+', '', s or '')


def main():
    recs = read_jsonl(os.path.join(EXTRACT_DIR, 'extracted.jsonl'))
    verify = json.load(io.open(os.path.join(EXTRACT_DIR, 'verify.json'), encoding='utf-8'))
    stats = json.load(io.open(os.path.join(EXPORT_DIR, 'graph_stats.json'), encoding='utf-8'))
    backfill = json.load(io.open(os.path.join(EXTRACT_DIR, 'event_time_backfill.json'), encoding='utf-8'))
    tcov = json.load(io.open(os.path.join(EXTRACT_DIR, '时间覆盖_度量.json'), encoding='utf-8'))
    chunks = {c['chunk_id']: c for c in read_jsonl(os.path.join(V21, 'chunks', 'chunks.jsonl'))}

    print('#### B2-01 extracted.jsonl 基本量')
    print('records =', len(recs))
    print('distinct doc_id =', len(set(r['doc_id'] for r in recs)))
    ent_types = Counter()
    ev_types = Counter()
    rel_types = Counter()
    roles = Counter()
    n_ent = n_ev = n_rel = n_evd = 0
    rejected_total = 0
    warnings_total = 0
    for r in recs:
        for e in r.get('entities') or []:
            ent_types[e.get('type')] += 1
            n_ent += 1
        for e in r.get('events') or []:
            ev_types[e.get('event_type')] += 1
            n_ev += 1
        for rel in r.get('relations') or []:
            rel_types[rel.get('relation')] += 1
            if rel.get('relation') == 'PARTICIPATES_IN':
                roles[rel.get('role')] += 1
            n_rel += 1
        for e in r.get('evidenced_by') or []:
            n_evd += 1
        rejected_total += (r.get('counts') or {}).get('rejected', 0)
        warnings_total += len(r.get('warnings') or [])
    print('entities =', n_ent, dict(ent_types))
    print('events =', n_ev, dict(ev_types))
    print('relations(数组口径) =', n_rel, dict(rel_types))
    print('evidenced_by =', n_evd)
    print('roles =', dict(roles))
    print('counts.rejected 求和 =', rejected_total)
    print('warnings 条数 =', warnings_total)
    print('verify.ontology =', json.dumps(verify['ontology'], ensure_ascii=False))
    print('verify.rejected =', json.dumps(verify['rejected'], ensure_ascii=False))
    print('verify.evidence =', json.dumps({k: v for k, v in verify['evidence'].items() if k != 'examples'},
                                          ensure_ascii=False))
    print('verify.roles =', json.dumps(verify['roles'], ensure_ascii=False))

    print()
    print('#### B2-02 证据可定位逐条重算（entities／events／relations 的 quote 落到 source_chunk_id）')
    checked = 0
    ok = 0
    bad = []
    attrs_missing = []
    for r in recs:
        items = []
        for e in r.get('entities') or []:
            items.append(('entity', e))
        for e in r.get('events') or []:
            items.append(('event', e))
        for rel in r.get('relations') or []:
            items.append(('relation', rel))
        for kind, it in items:
            if it.get('relation') == 'EVIDENCED_BY':
                continue
            checked += 1
            cid = it.get('source_chunk_id')
            did = it.get('source_doc_id')
            if cid not in chunks:
                bad.append((kind, r['doc_id'], cid, 'chunk_missing'))
                continue
            if chunks[cid]['doc_id'] != did:
                bad.append((kind, r['doc_id'], cid, 'doc_mismatch'))
                continue
            if squash(it.get('quote')) and squash(it.get('quote')) in squash(chunks[cid]['content']):
                ok += 1
            else:
                bad.append((kind, r['doc_id'], cid, 'quote_not_found'))
            for k in ('source_doc_id', 'source_chunk_id', 'confidence'):
                if it.get(k) in (None, ''):
                    attrs_missing.append((kind, r['doc_id'], k))
    print('checked =', checked, ' ok =', ok, ' bad =', len(bad), bad[:5])
    print('三项证据属性缺失 =', len(attrs_missing), attrs_missing[:5])
    print('注：verify.evidence.items_checked =', verify['evidence']['items_checked'],
          ' items_ok =', verify['evidence']['items_ok'])
    print('注：verify.evidence_attrs =', json.dumps(verify['evidence_attrs'], ensure_ascii=False))

    print()
    print('#### B2-03 event_time 两级口径')
    null_ev = [e for r in recs for e in (r.get('events') or []) if not e.get('event_time')]
    nonnull_ev = [e for r in recs for e in (r.get('events') or []) if e.get('event_time')]
    print('抽取层 events =', n_ev, ' 空 =', len(null_ev), ' 非空 =', len(nonnull_ev))
    print('抽取层空值按类型 =', dict(Counter(e['event_type'] for e in null_ev)))
    print('backfill.counts =', json.dumps(backfill.get('counts', {}), ensure_ascii=False)[:1200])
    print('backfill.keys =', list(backfill.keys()))
    print('时间覆盖_度量 extraction_layer_after_backfill =',
          json.dumps(tcov.get('extraction_layer_after_backfill'), ensure_ascii=False)[:1200])
    print('时间覆盖_度量 graph_layer =', json.dumps(tcov.get('graph_layer'), ensure_ascii=False)[:1200])
    print('graph_stats.event_time_basis =', json.dumps(stats['event_time_basis'], ensure_ascii=False))
    print('graph_stats.event_core_attributes =', json.dumps(stats['event_core_attributes'], ensure_ascii=False))

    print()
    print('#### B2-04 BELONGS_TO 有效期')
    bel = [rel for r in recs for rel in (r.get('relations') or []) if rel.get('relation') == 'BELONGS_TO']
    with_validity = [b for b in bel if b.get('valid_from') or b.get('valid_to')]
    print('抽取侧 BELONGS_TO =', len(bel), ' 带有效期 =', len(with_validity))
    print('抽取侧 BELONGS_TO 的键集合 =', sorted(set(k for b in bel for k in b.keys())))

    print()
    print('#### B2-05 无参与主体的事件')
    ev_ids_with_participant = set()
    for r in recs:
        for rel in r.get('relations') or []:
            if rel.get('relation') == 'PARTICIPATES_IN':
                ev_ids_with_participant.add(rel.get('tail_id'))
    all_ev_ids = set(e['event_id'] for r in recs for e in (r.get('events') or []))
    print('事件总数 =', len(all_ev_ids), ' 有 PARTICIPATES_IN 的 =', len(ev_ids_with_participant),
          ' 无参与主体 =', len(all_ev_ids - ev_ids_with_participant))

    print()
    print('#### B2-06 导出物：文件级')
    for fn in ('nodes.csv', 'edges.csv', 'graph_stats.json', 'replay.cypher', '人工确认清单.json'):
        p = os.path.join(EXPORT_DIR, fn)
        print('%-22s bytes=%d sha256=%s' % (fn, os.path.getsize(p), sha256_file(p)))
    print('graph_stats.files =', json.dumps(stats['files'], ensure_ascii=False))

    print()
    print('#### B2-07 导出物：nodes.csv 重算')
    with io.open(os.path.join(EXPORT_DIR, 'nodes.csv'), encoding='utf-8', newline='') as f:
        nrows = list(csv.DictReader(f))
    label_cnt = Counter(r['label'] for r in nrows)
    print('rows =', len(nrows), ' cols =', len(nrows[0].keys()))
    print('by_label =', dict(sorted(label_cnt.items())))
    print('sum =', sum(label_cnt.values()))
    print('distinct node_id =', len(set(r['node_id'] for r in nrows)))
    hconf = [r for r in nrows if r['node_id'].startswith('HCONF-')]
    print('HCONF 节点 =', len(hconf), ' 无 stock_code 的 HCONF =',
          sum(1 for r in hconf if not r.get('stock_code')))
    print('HCONF node_ids =', sorted(r['node_id'] for r in hconf))
    ev_nodes = [r for r in nrows if r['label'] == 'Event']
    print('Event 节点 =', len(ev_nodes), ' event_type 分布 =', dict(Counter(r['event_type'] for r in ev_nodes)))
    print('Event 节点 event_time 空 =', sum(1 for r in ev_nodes if not r.get('event_time')))
    doc_nodes = [r for r in nrows if r['label'] == 'Document']
    print('Document 节点 =', len(doc_nodes), ' distinct doc_id =', len(set(r['doc_id'] for r in doc_nodes)))

    print()
    print('#### B2-08 导出物：edges.csv 重算')
    with io.open(os.path.join(EXPORT_DIR, 'edges.csv'), encoding='utf-8', newline='') as f:
        erows = list(csv.DictReader(f))
    rel_cnt = Counter(r['relation'] for r in erows)
    print('rows =', len(erows), ' cols =', len(erows[0].keys()))
    print('edges_by_relation =', dict(sorted(rel_cnt.items())))
    print('edges_total =', sum(rel_cnt.values()))
    sem = [r for r in erows if r['relation'] != 'EVIDENCED_BY']
    print('语义边（8 条关系） =', len(sem), ' 三项证据属性缺失 =',
          sum(1 for r in sem if not r['source_doc_id'] or not r['source_chunk_id'] or not r['confidence']))
    pid = [r for r in erows if r['relation'] == 'PARTICIPATES_IN']
    print('PARTICIPATES_IN role 分布 =', dict(Counter(r['role'] for r in pid)))
    evd = [r for r in erows if r['relation'] == 'EVIDENCED_BY']
    evd_by_head = Counter(r['head_id'] for r in evd)
    print('EVIDENCED_BY =', len(evd), ' head 数 =', len(evd_by_head),
          ' 恰 1 条 =', sum(1 for v in evd_by_head.values() if v == 1),
          ' 恰 2 条 =', sum(1 for v in evd_by_head.values() if v == 2),
          ' >2 条 =', sum(1 for v in evd_by_head.values() if v > 2))
    doc_ids = set(r['node_id'] for r in doc_nodes)
    print('EVIDENCED_BY head 全是 Event 节点 =', all(r['head_id'] in set(r2['node_id'] for r2 in ev_nodes) for r in evd),
          '；tail 全是 Document 节点 =', all(r['tail_id'] in doc_ids for r in evd))
    print('（说明：Document 节点编号＝裸 doc_id，不带 DOC- 前缀，见《16》6.1 的 id_rule）')
    bel_edges = [r for r in erows if r['relation'] == 'BELONGS_TO']
    print('BELONGS_TO =', len(bel_edges), ' 带有效期 =',
          sum(1 for r in bel_edges if r['valid_from'] or r['valid_to']))
    issued = [r for r in erows if r['relation'] == 'ISSUED_BY']
    ev_type_of = {r['node_id']: r['event_type'] for r in ev_nodes}
    bad_issued = [r['head_id'] for r in issued if ev_type_of.get(r['head_id']) not in ('政策', '监管')]
    print('ISSUED_BY =', len(issued), ' 非政策／监管事件的 ISSUED_BY =', len(bad_issued), bad_issued[:5])
    part_pairs = set((r['tail_id'], r['head_id']) for r in pid)
    iss_pairs = set((r['head_id'], r['tail_id']) for r in issued)
    print('issuer 同时是 participant 的对数 =', len(part_pairs & iss_pairs))

    print()
    print('#### B2-09 悬空端点、孤立节点')
    node_ids = set(r['node_id'] for r in nrows)
    dangling = [r for r in erows if r['head_id'] not in node_ids or r['tail_id'] not in node_ids]
    print('悬空边 =', len(dangling))
    touched = set()
    for r in erows:
        touched.add(r['head_id'])
        touched.add(r['tail_id'])
    iso = [r for r in nrows if r['node_id'] not in touched]
    print('孤立节点 =', len(iso), ' by_label =', dict(Counter(r['label'] for r in iso)))
    print('graph_stats.isolated_nodes =', json.dumps(stats['isolated_nodes'], ensure_ascii=False))

    print()
    print('#### B2-10 三条对账恒等式')
    print('恒等式1 实体侧：3293 − 1070 待消歧 = 2223 → 998 节点 + 12 HCONF + 692 Document + 1100 Event = 2802')
    print('  实测 nodes_total =', stats['counts']['nodes_total'], ' by_label 实测 =', dict(label_cnt))
    print('恒等式2 事件侧：1114 − 14 = 1100；Event 节点实测 =', label_cnt.get('Event'))
    print('恒等式3 关系侧：2506 − 878 − 1 − 2 = 1625（+29 人工确认恢复）；1625 + EVIDENCED_BY = 2736')
    print('  实测 edges_total =', stats['counts']['edges_total'], ' 语义边 =', len(sem), ' EVIDENCED_BY =', len(evd))
    print('graph_stats.counts =', json.dumps(stats['counts'], ensure_ascii=False))
    print('graph_stats.edge_dedup =', json.dumps(stats['edge_dedup'], ensure_ascii=False))
    print('graph_stats.unresolved =', json.dumps(stats['unresolved']['relations_skipped_by_relation'],
                                                ensure_ascii=False),
          ' total =', stats['unresolved']['relations_skipped'])
    print('graph_stats.issuer_participation_dropped =',
          json.dumps({k: v for k, v in stats['issuer_participation_dropped'].items() if k != 'basis'},
                     ensure_ascii=False))

    print()
    print('#### B2-11 HCONF 人工确认')
    confirm_path = os.path.join(EXPORT_DIR, '人工确认清单.json')
    confirm = json.load(io.open(confirm_path, encoding='utf-8'))
    print('确认文件 sha256 =', sha256_file(confirm_path), ' bytes =', os.path.getsize(confirm_path))
    print('schema =', confirm.get('schema'), ' confirmed_by =', confirm.get('confirmed_by'),
          ' confirmed_at =', confirm.get('confirmed_at'))
    items = confirm.get('items') or confirm.get('entries') or []
    print('条目数 =', len(items), ' confirmed=true =', sum(1 for i in items if i.get('confirmed')))
    print('graph_stats.human_confirmation =',
          json.dumps({k: v for k, v in stats['human_confirmation'].items()
                      if k != 'confirmed_names'}, ensure_ascii=False)[:1500])
    hconf_edges = [r for r in erows if r['head_id'].startswith('HCONF-') or r['tail_id'].startswith('HCONF-')]
    print('以 HCONF 节点为端点的导出边 =', len(hconf_edges),
          ' 按关系 =', dict(Counter(r['relation'] for r in hconf_edges)))

    print()
    print('#### B2-12 三条可过滤性读数（重算）')
    ev_time = {r['node_id']: (r.get('event_time') or '').strip() for r in ev_nodes}
    evdoc = defaultdict(set)
    for r in evd:
        evdoc[r['tail_id']].add(r['head_id'])
    dates_per_doc = {}
    for did, evs in evdoc.items():
        dates_per_doc[did] = [ev_time.get(e) for e in evs if ev_time.get(e)]
    print('图谱层 含 >=2 个不同 event_time 日期的文档 =',
          sum(1 for v in dates_per_doc.values() if len(set(v)) >= 2))
    print('图谱层 含 >=2 个不同自然月的文档 =',
          sum(1 for v in dates_per_doc.values() if len(set(x[:7] for x in v)) >= 2))
    from datetime import date

    def span31(v):
        try:
            yy = sorted(date(int(x[:4]), int(x[5:7]), int(x[8:10])) for x in set(v))
        except ValueError:
            return False
        return bool(yy) and (yy[-1] - yy[0]).days >= 31
    print('图谱层 同文档日期跨度 >=31 天 =', sum(1 for v in dates_per_doc.values() if span31(v)))
    ext = defaultdict(list)
    for r in recs:
        for e in r.get('events') or []:
            if e.get('event_time'):
                ext[r['doc_id']].append(e['event_time'])
    print('抽取层 含 >=2 个不同日期 =', sum(1 for v in ext.values() if len(set(v)) >= 2))
    print('抽取层 字面口径「>=2 条 event_time 非空」 =', sum(1 for v in ext.values() if len(v) >= 2))
    print('抽取层 含 >=2 个自然月 =', sum(1 for v in ext.values() if len(set(x[:7] for x in v)) >= 2))
    print('抽取层 日期跨度 >=31 天 =', sum(1 for v in ext.values() if span31(v)))
    print('时间覆盖_度量.json 摘要 =', json.dumps(
        {k: v for k, v in tcov.items() if isinstance(v, (int, float, str, list)) and 'doc' in k.lower()
         or k in ('headroom', 'filterability')}, ensure_ascii=False)[:2000])
    print('时间覆盖_度量.json 全键 =', list(tcov.keys()))
    print('时间覆盖_度量.graph_layer_after_backfill =',
          json.dumps(tcov.get('graph_layer_after_backfill'), ensure_ascii=False)[:1200])

    print()
    print('#### B2-12b 去重层 events_without_participants（已消歧口径）')
    merged_path = os.path.join(CACHE_DIR, '图谱管线', '去重', 'events_merged.jsonl')
    merged = read_jsonl(merged_path)
    print('events_merged.jsonl 行数 =', len(merged))
    print('participants 为空的事件 =', sum(1 for m in merged if not m.get('participants')))
    print('既有 participants 为空、也有 unresolved_peers 的事件 =',
          sum(1 for m in merged if not m.get('participants') and m.get('unresolved_peers')))
    print('participants 为空且 unresolved_peers 也为空 =',
          sum(1 for m in merged if not m.get('participants') and not m.get('unresolved_peers')))

    print()
    print('#### B2-13 run_history.jsonl 成本台账')
    rh = read_jsonl(os.path.join(EXTRACT_DIR, 'run_history.jsonl'))
    print('条数 =', len(rh))
    keys = set()
    for r in rh:
        keys.update(r.keys())
    print('键 =', sorted(keys))
    for i, r in enumerate(rh):
        print('  [%d] %s' % (i, json.dumps(r, ensure_ascii=False)[:700]))
    print('--- token 汇总 ---')
    print('prompt_tokens 合计 =', sum(r.get('prompt_tokens') or 0 for r in rh))
    print('completion_tokens 合计 =', sum(r.get('completion_tokens') or 0 for r in rh))
    print('total_tokens 合计 =', sum(r.get('total_tokens') or 0 for r in rh))
    print('逐条 total_tokens =', [r.get('total_tokens') for r in rh])
    print('逐条 api_calls =', [r.get('api_calls') for r in rh])
    print('逐条 documents =', [r.get('documents') for r in rh])
    print('v1.2 抽取链合计（第 2＋3 条；不含第 1 条冒烟） =',
          sum((r.get('total_tokens') or 0) for r in rh[1:]))
    print('含冒烟的合计 =', sum((r.get('total_tokens') or 0) for r in rh))

    print()
    print('#### B2-14 verify.json reproducibility')
    print(json.dumps(verify['reproducibility'], ensure_ascii=False, indent=1)[:3000])
    print('verify.documents =', verify['documents'], ' documents_missing =', verify.get('documents_missing'))
    print('scope_note =', verify.get('scope_note'))


if __name__ == '__main__':
    main()
