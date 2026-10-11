# -*- coding: utf-8 -*-
"""改进执行 · A-2：配对显著性检验 + 样本量曲线（零模型调用、零联网）

对应《不足与展望-改进方案》A-2 实施步骤 1~3：
  1. 导出两轮实验的逐题明细（每题每组的四项检索指标）
  2. 对 A vs C（主）/ B vs C / C vs D / D vs E 做配对检验，输出 p 值、效应量、95% CI
  3. 做样本量曲线（n=30/60/90/满池），验证"分辨力随 n 提升"的假设

口径纪律（与冻结脚本逐字一致）：
  - 指标公式逐字复刻《跑AC对照.py retrieval_metrics()》：
      recall_at_k = |gold∩ev|/|gold|；precision = |gold∩ev|/K
      mrr = 1/首个 gold 命中排名；complete_evidence_recall = 1[gold ⊆ ev]
      组级读数 = 逐题算术平均，round 6 位
  - 两套题池（与冻结报告的三段口径对应）：
      pool=all  ：全部 120 题口径的共同有效题（D/E 为 117）
      pool=core ：核心 108 题口径的共同有效题（判定口径）
    配对检验在两套池上分别进行；子集检验在 core 池上进行（与判定口径一致）
  - 预实验集（30 题）与正式集（120 题）两套读数并存、不可混引、不可相加

本脚本只读既有落盘产物、只写 `改进执行/A2_配对显著性检验/` 下的新文件，
不覆写任何正式产出目录。
"""
from __future__ import annotations

import io
import json
import os
import sys

import numpy as np
from scipy import stats

ROOT = r'C:\Users\15129\Desktop\毕业设计'
BASE = os.path.join(ROOT, '交付物', '06-实验与评测')
FORMAL_DIR = os.path.join(BASE, '对照产出_正式')
PRE_DIR = os.path.join(BASE, '对照产出_v13')
OUT_DIR = os.path.join(BASE, '改进执行', 'A2_配对显著性检验')

SEED = 20261010
B_BOOT = 10000       # 配对 bootstrap 次数
B_CURVE = 5000       # 样本量曲线每档重采样次数
GROUPS_FORMAL = ('A', 'B', 'C', 'D', 'E', 'B1')
GROUPS_PRE = ('A', 'B', 'C', 'D', 'E')

SUBSETS = (
    ('关系型', lambda q: q.get('task_type') == '关系型'),
    ('多跳型', lambda q: int(q.get('gold_hop_depth') or 0) >= 1),
    ('时序型', lambda q: q.get('time_constraint') == '有'),
)

PAIR_DEFS = (
    ('A', 'C', 'RQ2 主对比：A(纯向量) → C(两跳图谱)'),
    ('B', 'C', '深度维：B(一跳) → C(两跳)'),
    ('C', 'D', '时间过滤维：C → D'),
    ('D', 'E', '证据排序维：D → E'),
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


def load_questions(path: str) -> dict:
    out = {}
    for row in load_jsonl(path):
        out[row['qid']] = row
    return out


# ---------------------------------------------------------------------------
# 1. 逐题指标（公式逐字复刻冻结脚本）
# ---------------------------------------------------------------------------
def per_question_metrics(trace_rows: list, questions: dict) -> dict:
    out = {}
    for row in trace_rows:
        q = questions.get(row['qid'], {})
        gold = set(int(x) for x in (q.get('gold_evidence_chunk_ids') or []))
        ev = [int(x['chunk_id']) for x in row['evidence']]
        k = int(row['k'])
        hit = len(gold & set(ev))
        ranks = [i + 1 for i, c in enumerate(ev) if c in gold]
        out[row['qid']] = {
            'cer': 1.0 if (gold and gold <= set(ev)) else 0.0,
            'recall_at_k': (hit / len(gold)) if gold else 0.0,
            'precision_at_k': hit / k,
            'mrr': (1.0 / ranks[0]) if ranks else 0.0,
            'k': k,
            'n_ev': len(ev),
            'n_gold': len(gold),
        }
    return out


def agg(metrics: dict, qids: list, questions: dict, subset_pred=None) -> dict:
    sel = [q for q in qids if subset_pred is None or subset_pred(questions.get(q, {}))]
    if not sel:
        return {'n_questions': 0}
    acc = {'cer': 0.0, 'recall_at_k': 0.0, 'precision_at_k': 0.0, 'mrr': 0.0}
    for q in sel:
        m = metrics[q]
        for k in acc:
            acc[k] += m[k]
    n = len(sel)
    return {
        'n_questions': n,
        'complete_evidence_recall_at_k': round(acc['cer'] / n, 6),
        'recall_at_k': round(acc['recall_at_k'] / n, 6),
        'precision_at_k': round(acc['precision_at_k'] / n, 6),
        'mrr': round(acc['mrr'] / n, 6),
    }


# ---------------------------------------------------------------------------
# 2. 配对检验工具
# ---------------------------------------------------------------------------
def mcnemar_exact(baseline_cer: np.ndarray, method_cer: np.ndarray) -> dict:
    """CER 为 0/1 二元结果 → 配对 McNemar（精确二项检验，双侧）。

    约定：baseline=左侧组、method=右侧组，Δ 方向恒为「右侧 − 左侧」。
    """
    b = int(np.sum((baseline_cer == 0) & (method_cer == 1)))  # 左失右得（增益）
    c = int(np.sum((baseline_cer == 1) & (method_cer == 0)))  # 左得右失（回退）
    n_disc = b + c
    if n_disc == 0:
        return {'gain_pairs_leftfail_rightpass': b, 'regress_pairs_leftpass_rightfail': c,
                'n_discordant': 0, 'p_value': 1.0, 'note': '零不一致对'}
    p = stats.binomtest(min(b, c), n_disc, 0.5, alternative='two-sided').pvalue
    return {'gain_pairs_leftfail_rightpass': b, 'regress_pairs_leftpass_rightfail': c,
            'n_discordant': n_disc, 'p_value': float(p)}


def wilcoxon_signed(baseline: np.ndarray, method: np.ndarray) -> dict:
    """连续指标（recall/mrr）→ Wilcoxon 符号秩检验（双侧）+ 匹配对秩二列效应量。"""
    d = method - baseline
    nz = d[d != 0]
    if len(nz) == 0:
        return {'n_nonzero': 0, 'p_value': 1.0, 'rank_biserial': 0.0, 'note': '全部差值为 0'}
    res = stats.wilcoxon(baseline, method, alternative='two-sided')
    ranks = stats.rankdata(np.abs(d[d != 0]))
    wp = float(np.sum(ranks[d[d != 0] > 0]))
    wn = float(np.sum(ranks[d[d != 0] < 0]))
    r = (wp - wn) / (wp + wn) if (wp + wn) > 0 else 0.0
    return {
        'n_nonzero': int(len(nz)),
        'n_positive_right_better': int(np.sum(d > 0)),
        'n_negative_right_worse': int(np.sum(d < 0)),
        'p_value': float(res.pvalue),
        'rank_biserial': round(float(r), 4),
    }


def paired_bootstrap(baseline: np.ndarray, method: np.ndarray, b: int = B_BOOT, seed: int = SEED) -> dict:
    """配对 bootstrap：Δ = mean(method) − mean(baseline) 的 95% CI（对题目索引重采样）。"""
    rng = np.random.default_rng(seed)
    n = len(baseline)
    idx = rng.integers(0, n, size=(b, n))
    d = method[idx] - baseline[idx]
    dm = d.mean(axis=1)
    lo, hi = np.percentile(dm, [2.5, 97.5])
    return {
        'delta_right_minus_left': round(float(np.mean(method) - np.mean(baseline)), 6),
        'ci95_lower': round(float(lo), 6),
        'ci95_upper': round(float(hi), 6),
        'ci_width': round(float(hi - lo), 6),
        'p_delta_gt_0': round(float(np.mean(dm > 0)), 4),
        'p_delta_lt_0': round(float(np.mean(dm < 0)), 4),
        'bootstrap_n': b,
    }


def full_paired_report(b_cer, m_cer, b_recall, m_recall, b_mrr, m_mrr, label: str) -> dict:
    """b_* = 左侧（baseline）数组；m_* = 右侧（method）数组；Δ 恒为右减左。"""
    out = {'label': label, 'n_pairs': int(len(b_cer))}
    out['cer_mcnemar'] = mcnemar_exact(b_cer, m_cer)
    out['cer_bootstrap'] = paired_bootstrap(b_cer, m_cer)
    out['recall_wilcoxon'] = wilcoxon_signed(b_recall, m_recall)
    out['recall_bootstrap'] = paired_bootstrap(b_recall, m_recall)
    out['mrr_wilcoxon'] = wilcoxon_signed(b_mrr, m_mrr)
    out['mrr_bootstrap'] = paired_bootstrap(b_mrr, m_mrr)
    return out


def power_at_n(delta: float, sigma_d: float, n: int, alpha: float = 0.05) -> float:
    if sigma_d <= 0:
        return 1.0 if delta != 0 else 0.0
    lam = delta / (sigma_d / np.sqrt(n))
    z = stats.norm.ppf(1 - alpha / 2)
    return float(1 - stats.norm.cdf(z - lam) + stats.norm.cdf(-z - lam))


def mde_at_n(sigma_d: float, n: int, alpha: float = 0.05, power: float = 0.80) -> float:
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_p = stats.norm.ppf(power)
    return float((z_a + z_p) * sigma_d / np.sqrt(n))


def n_required(delta: float, sigma_d: float, power: float):
    if delta is None or delta <= 0 or sigma_d <= 0:
        return None
    z_a = stats.norm.ppf(0.975)
    z_p = stats.norm.ppf(power)
    return int(np.ceil(((z_a + z_p) * sigma_d / delta) ** 2))


def pair_arrays(m_left: dict, m_right: dict, qids: list):
    b_cer = np.array([m_left[q]['cer'] for q in qids])
    m_cer = np.array([m_right[q]['cer'] for q in qids])
    b_rec = np.array([m_left[q]['recall_at_k'] for q in qids])
    m_rec = np.array([m_right[q]['recall_at_k'] for q in qids])
    b_mrr = np.array([m_left[q]['mrr'] for q in qids])
    m_mrr = np.array([m_right[q]['mrr'] for q in qids])
    return b_cer, m_cer, b_rec, m_rec, b_mrr, m_mrr


# ---------------------------------------------------------------------------
# 3. 主流程
# ---------------------------------------------------------------------------
def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    q_formal = load_questions(os.path.join(BASE, '测试集', 'questions.jsonl'))
    q_pre = load_questions(os.path.join(ROOT, '交付物', '05-系统实现', 'RAG检索系统', '预实验问题集', 'questions.jsonl'))

    m_formal, m_pre = {}, {}
    for g in GROUPS_FORMAL:
        rows = load_jsonl(os.path.join(FORMAL_DIR, g, 'answer_trace.jsonl'))
        m_formal[g] = per_question_metrics(rows, q_formal)
    for g in GROUPS_PRE:
        rows = load_jsonl(os.path.join(PRE_DIR, g, 'answer_trace.jsonl'))
        m_pre[g] = per_question_metrics(rows, q_pre)

    # ---- 一致性自检：复算组级读数 vs 冻结报告值（all 口径）----
    frozen = json.load(io.open(os.path.join(FORMAL_DIR, 'A_vs_C_对照.json'), encoding='utf-8'))
    checks = []
    for g in ('A', 'B', 'C', 'D', 'E'):
        mine = agg(m_formal[g], sorted(m_formal[g].keys()), q_formal)
        ref = frozen['metrics'][g]
        ok = (mine['n_questions'] == ref['n_questions']
              and abs(mine['complete_evidence_recall_at_k'] - ref['complete_evidence_recall_at_k']) < 1e-9
              and abs(mine['recall_at_k'] - ref['recall_at_k']) < 1e-9
              and abs(mine['mrr'] - ref['mrr']) < 1e-9)
        checks.append({'group': g, 'my_n': mine['n_questions'], 'ref_n': ref['n_questions'],
                       'cer_mine': mine['complete_evidence_recall_at_k'],
                       'cer_ref': ref['complete_evidence_recall_at_k'], 'consistent': bool(ok)})
    log('=== 一致性自检（复算 vs 冻结 A_vs_C_对照.json，all 口径）===')
    for c in checks:
        log('  %s: n=%s/%s cer=%s/%s -> %s' % (c['group'], c['my_n'], c['ref_n'],
                                               c['cer_mine'], c['cer_ref'], 'OK' if c['consistent'] else 'MISMATCH'))
    all_consistent = all(c['consistent'] for c in checks)

    # core 口径自检（对照冻结 subsets_named_core 的三子集读数）
    core_checks = []
    snc = frozen.get('subsets_named_core', {})
    for sname, pred in SUBSETS:
        for g in ('A', 'C'):
            qids = sorted(m_formal[g].keys())
            mine = agg(m_formal[g], qids, q_formal, subset_pred=lambda x, p=pred: x.get('subset') == '核心' and p(x))
            ref = (snc.get(sname, {}) or {}).get(g, {})
            if ref:
                ok = (mine['n_questions'] == ref.get('n_questions')
                      and abs(mine['complete_evidence_recall_at_k'] - ref.get('complete_evidence_recall_at_k', -1)) < 1e-9)
                core_checks.append({'subset': sname, 'group': g, 'my_n': mine['n_questions'],
                                    'ref_n': ref.get('n_questions'),
                                    'cer_mine': mine['complete_evidence_recall_at_k'],
                                    'cer_ref': ref.get('complete_evidence_recall_at_k'),
                                    'consistent': bool(ok)})
    log('\n=== core 口径自检（三子集 × A/C）===')
    for c in core_checks:
        log('  %s/%s: n=%s/%s cer=%s/%s -> %s' % (c['subset'], c['group'], c['my_n'], c['ref_n'],
                                                  c['cer_mine'], c['cer_ref'], 'OK' if c['consistent'] else 'MISMATCH'))

    # ---- 配对检验（两套池）----
    pairs = {}
    for (g1, g2, label) in PAIR_DEFS:
        base_all = sorted(set(m_formal[g1].keys()) & set(m_formal[g2].keys()))
        base_core = [q for q in base_all if q_formal[q].get('subset') == '核心']
        key = f'{g1}->{g2}'
        rep = {'pair': key, 'label': label}
        for pool_name, pool_qids in (('all', base_all), ('core', base_core)):
            aa = pair_arrays(m_formal[g1], m_formal[g2], pool_qids)
            r = full_paired_report(*aa, f'{label} / pool={pool_name}')
            r['qids_n'] = len(pool_qids)
            rep.setdefault('pools', {})[pool_name] = r
        # 子集检验：core 池
        rep['subsets_core'] = {}
        for sname, pred in SUBSETS:
            sq = [q for q in base_core if pred(q_formal.get(q, {}))]
            if not sq:
                continue
            aa = pair_arrays(m_formal[g1], m_formal[g2], sq)
            r = full_paired_report(*aa, f'{label} / pool=core / {sname}')
            r['n_pairs'] = len(sq)
            rep['subsets_core'][sname] = r
        # 压力子集附加观察（单独报告、绝不并入核心口径）
        sq = [q for q in base_all if q_formal[q].get('subset') == '压力']
        if sq:
            aa = pair_arrays(m_formal[g1], m_formal[g2], sq)
            r = full_paired_report(*aa, f'{label} / pool=stress（附加观察，单独报告）')
            r['n_pairs'] = len(sq)
            rep['subsets_stress_addendum'] = r
        pairs[key] = rep

    # ---- 样本量曲线（A vs C，两套池）----
    curves = {}
    for pool_name in ('all', 'core'):
        if pool_name == 'all':
            ac_qids = sorted(set(m_formal['A'].keys()) & set(m_formal['C'].keys()))
        else:
            ac_qids = sorted(q for q in set(m_formal['A'].keys()) & set(m_formal['C'].keys())
                             if q_formal[q].get('subset') == '核心')
        d_cer = np.array([m_formal['C'][q]['cer'] - m_formal['A'][q]['cer'] for q in ac_qids])
        d_rec = np.array([m_formal['C'][q]['recall_at_k'] - m_formal['A'][q]['recall_at_k'] for q in ac_qids])
        sigma_cer = float(np.std(d_cer, ddof=1))
        sigma_rec = float(np.std(d_rec, ddof=1))
        curve = {'total_pool': len(ac_qids), 'observed': {
            'delta_cer_mean': round(float(np.mean(d_cer)), 6),
            'delta_recall_mean': round(float(np.mean(d_rec)), 6),
            'sigma_d_cer': round(sigma_cer, 6),
            'sigma_d_recall': round(sigma_rec, 6)}, 'points': []}
        curve['n_required_from_observed'] = {
            'power_80': n_required(float(np.mean(d_cer)), sigma_cer, 0.80),
            'power_90': n_required(float(np.mean(d_cer)), sigma_cer, 0.90),
            'power_95': n_required(float(np.mean(d_cer)), sigma_cer, 0.95),
            'note': '按观测 Δ 与 σ_d 反推的达标样本量（配对均值检验、双侧 α=0.05）',
        }
        rng = np.random.default_rng(SEED + (1 if pool_name == 'all' else 2))
        for n in (30, 60, 90, len(ac_qids)):
            if n > len(ac_qids):
                continue
            draws = rng.integers(0, len(ac_qids), size=(B_CURVE, n))
            dcs = d_cer[draws].mean(axis=1)
            drs = d_rec[draws].mean(axis=1)
            lo_c, hi_c = np.percentile(dcs, [2.5, 97.5])
            lo_r, hi_r = np.percentile(drs, [2.5, 97.5])
            curve['points'].append({
                'n': n,
                'delta_cer_mean': round(float(dcs.mean()), 6),
                'ci95_lower': round(float(lo_c), 6),
                'ci95_upper': round(float(hi_c), 6),
                'ci_width': round(float(hi_c - lo_c), 6),
                'p_delta_gt_0': round(float(np.mean(dcs > 0)), 4),
                'delta_recall_mean': round(float(drs.mean()), 6),
                'recall_ci_width': round(float(hi_r - lo_r), 6),
                'recall_p_delta_gt_0': round(float(np.mean(drs > 0)), 4),
                'mde80_cer': round(float((stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) * sigma_cer / np.sqrt(n)), 6),
                'power80_for_observed_delta_cer': round(power_at_n(float(np.mean(d_cer)), sigma_cer, n), 4),
                'power80_for_observed_delta_recall': round(power_at_n(float(np.mean(d_rec)), sigma_rec, n), 4),
            })
        curves[pool_name] = curve

    # ---- 预实验集（30 题）A vs C（Δ 方向＝C−A）----
    ac_pre = sorted(set(m_pre['A'].keys()) & set(m_pre['C'].keys()))
    pre_rep = full_paired_report(*pair_arrays(m_pre['A'], m_pre['C'], ac_pre), '预实验集（30 题）A_vs_C（Δ方向＝C−A）')
    pre_rep['qids_n'] = len(ac_pre)
    pre_means = {g: agg(m_pre[g], sorted(m_pre[g].keys()), q_pre) for g in GROUPS_PRE}
    same_cross_groups = True
    for q in ac_pre:
        vals = {m_pre[g][q]['cer'] for g in GROUPS_PRE}
        if len(vals) > 1:
            same_cross_groups = False
            break
    pre_rep['cer_identical_across_all_groups_per_question'] = bool(same_cross_groups)

    # ---- 汇出 ----
    out_metrics = {
        'meta': {
            '说明': '逐题四项检索指标，公式复刻冻结脚本《跑AC对照.py retrieval_metrics()》',
            'formal_question_set': '交付物/06-实验与评测/测试集/questions.jsonl（120 题）',
            'pre_question_set': '交付物/05-系统实现/RAG检索系统/预实验问题集/questions.jsonl（30 题）',
        },
        'formal': {g: m_formal[g] for g in GROUPS_FORMAL},
        'pre': {g: m_pre[g] for g in GROUPS_PRE},
    }
    out_tests = {
        'meta': {
            '一致性自检_all口径': checks, '全部一致': bool(all_consistent),
            '一致性自检_core子集': core_checks,
            '配对检验口径': '共同有效题（两组均有效的交集）；all 池＝全部 120 题口径，core 池＝核心 108 题口径（判定口径）',
            'seed': SEED, 'bootstrap_n': B_BOOT, 'curve_bootstrap_n': B_CURVE,
        },
        'formal_pairs': pairs,
        'sample_size_curve': curves,
        'pre_experiment': {'A_vs_C': pre_rep, 'group_means': pre_means},
    }
    io.open(os.path.join(OUT_DIR, '逐题指标.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(out_metrics, ensure_ascii=False, indent=1, sort_keys=True))
    io.open(os.path.join(OUT_DIR, '检验结果.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(out_tests, ensure_ascii=False, indent=1, sort_keys=True))

    # ---- 控制台摘要 ----
    log('\n=== A vs C 正式集 ===')
    a = pairs['A->C']
    for pool in ('all', 'core'):
        p = a['pools'][pool]
        log('[%s 池 n=%d]' % (pool, p['qids_n']))
        log('  CER (C−A):  Δ=%s  95%%CI=[%s, %s]  McNemar p=%s (增益对=%s, 回退对=%s)' % (
            p['cer_bootstrap']['delta_right_minus_left'], p['cer_bootstrap']['ci95_lower'],
            p['cer_bootstrap']['ci95_upper'], p['cer_mcnemar']['p_value'],
            p['cer_mcnemar']['gain_pairs_leftfail_rightpass'], p['cer_mcnemar']['regress_pairs_leftpass_rightfail']))
        log('  Recall (C−A): Δ=%s  CI=[%s, %s]  Wilcoxon p=%s  r=%s' % (
            p['recall_bootstrap']['delta_right_minus_left'], p['recall_bootstrap']['ci95_lower'],
            p['recall_bootstrap']['ci95_upper'], p['recall_wilcoxon']['p_value'],
            p['recall_wilcoxon']['rank_biserial']))
    log('\n=== 其余配对（core 池摘要）===')
    for key in ('B->C', 'C->D', 'D->E'):
        p = pairs[key]['pools']['core']
        log('  %s n=%d: CERΔ=%s (p=%s) | RecallΔ=%s (p=%s) | MRRΔ=%s (p=%s)' % (
            key, p['qids_n'],
            p['cer_bootstrap']['delta_right_minus_left'], p['cer_mcnemar']['p_value'],
            p['recall_bootstrap']['delta_right_minus_left'], p['recall_wilcoxon']['p_value'],
            p['mrr_bootstrap']['delta_right_minus_left'], p['mrr_wilcoxon']['p_value']))
    log('\n=== 样本量曲线（core 池）===')
    for pt in curves['core']['points']:
        log('  n=%3d  ΔCE=%s  CI宽=%s  P(ΔCE>0)=%s  MDE80=%s  功效=%s' % (
            pt['n'], pt['delta_cer_mean'], pt['ci_width'], pt['p_delta_gt_0'],
            pt['mde80_cer'], pt['power80_for_observed_delta_cer']))
    log('  达标样本量(core): %s' % json.dumps(curves['core']['n_required_from_observed'], ensure_ascii=False))
    log('  达标样本量(all) : %s' % json.dumps(curves['all']['n_required_from_observed'], ensure_ascii=False))
    log('\n=== 预实验集（30 题）A vs C ===')
    log('  CER (C−A): Δ=%s  CI=[%s, %s]  McNemar p=%s  | 逐题 CER 五组全同=%s' % (
        pre_rep['cer_bootstrap']['delta_right_minus_left'], pre_rep['cer_bootstrap']['ci95_lower'],
        pre_rep['cer_bootstrap']['ci95_upper'], pre_rep['cer_mcnemar']['p_value'],
        pre_rep['cer_identical_across_all_groups_per_question']))
    log('\n输出：%s' % OUT_DIR)
    return 0


if __name__ == '__main__':
    sys.exit(main())
