# -*- coding: utf-8 -*-
"""改进执行 · A-6：未通过题次明细 + 口径敏感性（零模型调用、零联网）

对应《不足与展望-改进方案》A-6 实施步骤 1~3：
  1. 导出 18 题次未通过明细（按子集／组别／失败原因三个维度做分布分析）
  2. 对压力子集 12 题单独产出完整读数（不改分母口径，只补报告）
  3. 用全 120 题口径重算三个子集判定，与核心 108 题口径并列报告，检验方向一致性

外加"未通过计 0"第三种分母处理的敏感性对照，构成 2×2 口径矩阵：
  池：core（核心 108）／all（全部 120）
  分母处理：valid-only（现行：未通过剔除）／fail-as-zero（未通过计 0，分母固定）

未通过题次的重建口径：逐题/{组} 目录存在、但聚合 answer_trace.jsonl 中无该题
（与冻结报告"未通过答案侧冻结门禁的题不计入任何指标"一致）；
失败原因直接读各组该题目录下的 error_contract.json（只读）。

本脚本只读既有落盘产物、只写 `改进执行/A6_未通过题次与口径敏感性/` 下的新文件。
"""
from __future__ import annotations

import io
import json
import os
import sys

ROOT = r'C:\Users\15129\Desktop\毕业设计'
BASE = os.path.join(ROOT, '交付物', '06-实验与评测')
FORMAL_DIR = os.path.join(BASE, '对照产出_正式')
OUT_DIR = os.path.join(BASE, '改进执行', 'A6_未通过题次与口径敏感性')
GROUPS = ('A', 'B', 'C', 'D', 'E', 'B1')

SUBSETS = (
    ('关系型', lambda q: q.get('task_type') == '关系型'),
    ('多跳型', lambda q: int(q.get('gold_hop_depth') or 0) >= 1),
    ('时序型', lambda q: q.get('time_constraint') == '有'),
)


def log(msg: str) -> None:
    print(msg, flush=True)


def load_jsonl(path: str) -> list:
    rows = []
    with io.open(path, 'r', encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    q_formal = {r['qid']: r for r in load_jsonl(os.path.join(BASE, '测试集', 'questions.jsonl'))}

    # ---- 1. 未通过题次重建 ----
    detail = []
    for g in GROUPS:
        agg = set(r['qid'] for r in load_jsonl(os.path.join(FORMAL_DIR, g, 'answer_trace.jsonl')))
        allq = sorted(os.listdir(os.path.join(FORMAL_DIR, '逐题', g)))
        for qid in allq:
            if qid in agg:
                continue
            reason = []
            ec = os.path.join(FORMAL_DIR, '逐题', g, qid, 'error_contract.json')
            if os.path.isfile(ec):
                c = json.load(io.open(ec, encoding='utf-8'))
                reason = (c.get('extra', {}).get('failures', {}) or {}).get(qid, []) or c.get('extra', {}).get('failed_reasons', [])
                reason = list(reason) if isinstance(reason, (list, tuple)) else [str(reason)]
            q = q_formal.get(qid, {})
            detail.append({
                'group': g, 'qid': qid,
                'reason': reason,
                'subset': q.get('subset'),
                'task_type': q.get('task_type'),
                'gold_hop_depth': q.get('gold_hop_depth'),
                'time_constraint': q.get('time_constraint'),
            })

    # 分布统计
    from collections import Counter
    by_group = Counter(d['group'] for d in detail)
    by_qid = Counter(d['qid'] for d in detail)
    by_reason = Counter(r for d in detail for r in (d['reason'] or ['(未记录)']))
    by_subset = Counter(d['subset'] for d in detail)
    by_type = Counter(d['task_type'] for d in detail)

    log('=== 未通过题次明细 ===')
    log('总题次: %d | 不重复题号: %d' % (len(detail), len(by_qid)))
    log('按组: %s' % dict(by_group))
    log('按题号: %s' % dict(sorted(by_qid.items())))
    log('按失败原因: %s' % dict(by_reason))
    log('按子集: %s | 按类型: %s' % (dict(by_subset), dict(by_type)))

    # ---- 2. 口径敏感性（A vs C 主对比，2×2 矩阵）----
    # 读取逐题指标（来自 A-2 产物，同公式；此处现场重算保证自包含）
    def per_q(g):
        rows = load_jsonl(os.path.join(FORMAL_DIR, g, 'answer_trace.jsonl'))
        out = {}
        for row in rows:
            q = q_formal.get(row['qid'], {})
            gold = set(int(x) for x in (q.get('gold_evidence_chunk_ids') or []))
            ev = [int(x['chunk_id']) for x in row['evidence']]
            k = int(row['k'])
            hit = len(gold & set(ev))
            out[row['qid']] = {'cer': 1.0 if (gold and gold <= set(ev)) else 0.0,
                               'recall': (hit / len(gold)) if gold else 0.0}
        return out

    m = {g: per_q(g) for g in ('A', 'C')}

    def metric_over(pool_qids, valid_map, treatment):
        """pool_qids 为题目全集；valid_map 为已成功题字典。treatment: valid|zero。"""
        if treatment == 'valid':
            sel = [q for q in pool_qids if q in valid_map]
        else:
            sel = list(pool_qids)
        if not sel:
            return None
        acc_c = acc_r = 0.0
        n_eff = 0
        for q in sel:
            if q in valid_map:
                acc_c += valid_map[q]['cer']
                acc_r += valid_map[q]['recall']
            # else: 计 0，不累加
            n_eff += 1
        return {'n': n_eff, 'cer': round(acc_c / n_eff, 6), 'recall': round(acc_r / n_eff, 6)}

    sensitivity = {}
    for pool_name, subset_pred_filter in (('core', lambda q: q.get('subset') == '核心'),
                                          ('all', lambda q: True)):
        pool_all = sorted(qid for qid, q in q_formal.items() if subset_pred_filter(q))
        rows = {}
        for tname, treatment in (('valid_only', 'valid'), ('fail_as_zero', 'zero')):
            rows[tname] = {}
            for sname, pred in SUBSETS:
                sq = [q for q in pool_all if pred(q_formal[q])]
                rows[tname][sname] = {
                    'A': metric_over(sq, m['A'], treatment),
                    'C': metric_over(sq, m['C'], treatment),
                }
                dA = rows[tname][sname]['A']
                dC = rows[tname][sname]['C']
                rows[tname][sname]['delta_C_minus_A'] = {
                    'cer': round(dC['cer'] - dA['cer'], 6),
                    'recall': round(dC['recall'] - dA['recall'], 6),
                }
            # 总体（该池全体）
            rows[tname]['全部'] = {
                'A': metric_over(pool_all, m['A'], treatment),
                'C': metric_over(pool_all, m['C'], treatment),
            }
            dA = rows[tname]['全部']['A']
            dC = rows[tname]['全部']['C']
            rows[tname]['全部']['delta_C_minus_A'] = {
                'cer': round(dC['cer'] - dA['cer'], 6),
                'recall': round(dC['recall'] - dA['recall'], 6),
            }
        sensitivity[pool_name] = rows

    log('\n=== 口径敏感性（A vs C，CER / Recall）===')
    for pool_name in ('core', 'all'):
        for tname in ('valid_only', 'fail_as_zero'):
            for sname in ('全部', '关系型', '多跳型', '时序型'):
                r = sensitivity[pool_name][tname][sname]
                d = r['delta_C_minus_A']
                log('[%s/%s] %s: A(n=%d cer=%s) C(n=%d cer=%s) Δcer=%+.4f | Δrecall=%+.4f' % (
                    pool_name, tname, sname,
                    r['A']['n'], r['A']['cer'], r['C']['n'], r['C']['cer'], d['cer'], d['recall']))

    # ---- 方向一致性结论 ----
    direction_consistent = True
    evidence = []
    for pool_name in ('core', 'all'):
        for tname in ('valid_only', 'fail_as_zero'):
            for sname in ('全部', '关系型', '多跳型', '时序型'):
                d = sensitivity[pool_name][tname][sname]['delta_C_minus_A']
                evidence.append({'pool': pool_name, 'treatment': tname, 'subset': sname,
                                 'delta_cer': d['cer'], 'positive': d['cer'] > 0})
                if sname != '全部' and d['cer'] <= 0:
                    direction_consistent = False

    # ---- 汇出 ----
    out = {
        'meta': {
            '未通过题次重建口径': '逐题/{组} 存在但聚合 answer_trace.jsonl 缺失；与冻结报告"18 题次/8 题号"对账',
            '失败原因来源': '各组题目录下 error_contract.json（只读）',
            '口径矩阵': '池 ∈ {core, all} × 分母处理 ∈ {valid_only(现行), fail_as_zero(未通过计0)}',
        },
        'failures_detail': detail,
        'distributions': {
            'by_group': dict(by_group), 'by_qid': dict(by_qid), 'by_reason': dict(by_reason),
            'by_subset': dict(by_subset), 'by_type': dict(by_type),
            'n_episodes': len(detail), 'n_distinct_qids': len(by_qid),
        },
        'sensitivity': sensitivity,
        'direction_consistency': {
            '三子集在全部 8 个口径组合下 Δcer 均为正': bool(direction_consistent),
            'evidence': evidence,
        },
    }
    io.open(os.path.join(OUT_DIR, '口径敏感性与未通过题次.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True))
    log('\n方向一致性（三子集 Δcer 全为正）: %s' % direction_consistent)
    log('输出：%s' % OUT_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
