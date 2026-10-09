# -*- coding: utf-8 -*-
"""B2 补充：从 extracted.jsonl ＋ 消歧产物独立重算「消歧率／待消歧构成／跳过边」。

对齐《16》第4.3／4.4／6.2 与 8.4 的声明值。
"""
import io
import json
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
CACHE = os.path.join(ROOT, '交付物/04-数据与知识图谱/数据准备', '数据集', '_抽取缓存', 'v2.1_v1_2')
EXTRACT = os.path.join(ROOT, '交付物/03-代码', '抽取与图谱', '_全量', 'v2.1_v1_2')


def read_jsonl(p):
    return [json.loads(l) for l in io.open(p, encoding='utf-8') if l.strip()]


def main():
    recs = read_jsonl(os.path.join(EXTRACT, 'extracted.jsonl'))
    dis = json.load(io.open(os.path.join(CACHE, '图谱管线', '消歧', 'disambiguation.json'),
                            encoding='utf-8'))
    emap = dis['entity_map']
    un = read_jsonl(os.path.join(CACHE, '图谱管线', '消歧', 'unresolved.jsonl'))

    print('#### 消歧计数（重算 vs 声明）')
    by_label = defaultdict(lambda: [0, 0])
    for r in recs:
        for e in (r.get('entities') or []):
            info = emap.get(e['entity_id'])
            ok = bool(info and info.get('identity_key'))
            by_label[e['type']][0 if ok else 1] += 1
    dec = dis['counts']['by_label']
    for lab in ('Company', 'Institution', 'Person', 'Policy', 'Industry'):
        rr, uu = by_label[lab]
        d = dec.get(lab, {})
        print('  %-12s 重算 resolved=%d unresolved=%d total=%d ｜ 声明 resolved=%s unresolved=%s total=%s ｜ %s'
              % (lab, rr, uu, rr + uu, d.get('resolved'), d.get('unresolved'), d.get('total'),
                 '一致' if (rr == d.get('resolved') and uu == d.get('unresolved')) else '不一致'))
    print('  Company 消歧率 重算 = %.4f（《16》8.4 声明 41.4%%）'
          % (by_label['Company'][0] / sum(by_label['Company'])))

    print()
    print('#### 待消歧构成（unresolved.jsonl 的 reason 分布）')
    print('  条目数 =', len(un), ' reason 分布 =', dict(Counter(x.get('reason') for x in un)))
    print('  《16》4.4 声明：no_alias_match 1063 ＋ distinct_entity_marker 7 = 1070')

    print()
    print('#### 跳过边（端点未消歧）按关系重算')

    def resolved_entity(eid):
        info = emap.get(eid)
        return bool(info and info.get('identity_key'))

    skipped = Counter()
    peer_missing = Counter()
    for r in recs:
        for rel in (r.get('relations') or []):
            kind = rel['relation']
            head, tail = rel['head_id'], rel['tail_id']
            if kind == 'PARTICIPATES_IN':
                peer = head
            elif kind in ('ISSUED_BY', 'RELATED_TO'):
                peer = tail
            else:
                peer = None
            if peer is not None:
                if peer not in emap:
                    peer_missing[kind] += 1
                elif not resolved_entity(peer):
                    skipped[kind] += 1
            else:
                if not resolved_entity(head) or not resolved_entity(tail):
                    skipped[kind] += 1
    print('  重算跳过 =', dict(skipped), ' 合计 =', sum(skipped.values()))
    print('  peer 不在 entity_map 的关系数 =', dict(peer_missing))
    print('  声明值：PARTICIPATES_IN 662／HAS_EXECUTIVE 135／BELONGS_TO 40／SUPPLIES 29／'
          'COMPETES_WITH 7／CUSTOMER_OF 5，合计 878')

    print()
    print('#### 公司身份数')
    print('  company_identities 声明 =', dis['counts'].get('company_identities'),
          '；重算 entity_map 里 Company 的不同数字代码身份 =',
          len({v['identity_key'] for v in emap.values()
               if str(v.get('identity_key') or '').startswith('Company:')
               and str(v['identity_key']).split(':', 1)[1].isdigit()}))


if __name__ == '__main__':
    main()
