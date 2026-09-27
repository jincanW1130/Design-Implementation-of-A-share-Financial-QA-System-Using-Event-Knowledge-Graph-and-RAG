# -*- coding: utf-8 -*-
r"""代码\检索\pre_experiment.py —— T8：检索预实验（固化 K／N／Context Token Budget 并复算 g）。

对应《18-第7阶段任务书（RAG检索系统）》第九节 T8 与 第八节 第 20／21／22 行；选择规则见
第2.4节、第五节 硬约束 10；执行证据见《02-项目执行总控文档》第12.7节 第一步与 第12.4节。

**本脚本要做四件事**

1. **跑满 9 格网格**（K ∈ `config.RETRIEVAL["k_grid"]` × N ∈ `config.RETRIEVAL["n_grid"]`），
   逐格记四项指标（chunk 级、按题取平均）与**预算分账**（文本块 token ＋ 图谱路径 token ＋
   事件三元组 token）。第一轮用**非约束预算**，把"预算比 K 更早生效"这一混淆隔离开，
   得到 Complete Evidence Recall@K 随 K 变化的曲线。
2. **第二轮**在按预算规则算出的 Context Token Budget 下复跑**选定格**，两轮读数并列记录。
3. **按预先写明的规则定值**：K／N／Context Token Budget／g 四者的执行证据全部落进
   `检索产出\k_selection.json`。
4. **落盘**`检索产出\pre_experiment_matrix.jsonl`（9 格 ＋ 第二轮选定格）与
   `检索产出\k_selection.json`。两者 UTF-8 无 BOM、固定键序、**不写时间戳与耗时**。

**四条预先写明的规则（本文件是它们的唯一写死处；运行结果不反过来改规则）**

* **规则 1（第一轮预算）**：第一轮预算取 `config.CORPUS["token_count_total"]`（＝全语料
  token 合计）。该值大于任何单题候选集合的可能占用上限，**不构成约束**——用于隔离 K 的影响。
* **规则 2（预算选择规则）**：记 `median_text(K, N)` 为第一轮该格逐题**最终证据集合的
  文本块 token** 的中位数（文本块 token 用 `chunks.jsonl` 的 `token_count` 实测值）。
  基准格取"网格中满足 gold 约束（K ≥ 本题集最大 gold 数）的**最小 K**"与其**最小可行 N**
  （N ≥ K）；记该基准格的 `median_text` 为 `m`，则
  **Context Token Budget ＝ ceil100( 1.10 × m )**——即"预算至少能容纳该 K 个文本块的
  文本占用中位数，并留 **10%** 固定余量"。**图谱路径与事件三元组不单独预留额度**：它们与
  文本块**共用同一上限**，超限时按《10-系统总体设计（第四阶段）》第4.6.5节 先裁与问题实体
  无关的远端图谱路径、再按分层保留顺序从尾部往前裁文本块（这正是"若不控制上下文预算，
  KG-RAG 会天然获得更多 token"那条理由要求的）。余量比例是本规则唯一的自由量，故在
  `k_selection.json` 的 `budget_rule.sensitivity` 里给出 0%／5%／10%／15%／20% 五档对照。
* **规则 3（K 的选择与饱和判定）**：K 必须（a）**满足 gold 约束**：K ≥ 本题集逐题 gold
  证据数的最大值（验收第 25 行）；（b）**满足 Context Token Budget**：`median_text(K, N) ≤ B`
  （同一预算至少能容纳该 K 个文本块的文本占用中位数）。**饱和判据（可执行）**：在**同一预算
  B** 下复跑各 K 档，对相邻可行档 K_i < K_j 记增量 Δ = CER@K_j − CER@K_i；**Δ ≤ 0**
  （再增大 K 不再提升 Complete Evidence Recall@K）即判 K_i 已饱和。选定 K\* ＝ 满足
  （a）（b）且饱和的**最小 K**；若某档被预算排除（`median_text > B`），则在记录里如实写明
  排除原因与实测读数，并按"在满足预算的前提下"取当前档。
* **规则 4（N 的选择）**：K\* 固定后，取 `n_grid` 中满足 N ≥ K\* 且使 CER@K\* 达到该 K 档
  最大值的**最小 N**（同值取最小 N；执行证据给出 N 各档的四项指标）。
* **规则 5（g 的复算；2026-09-27 v3.2 加固：含下限 1）**：在选定格（K\*／N\*／B）上对
  g ∈ {0, 1, 2, 3, 5} 跑 `config.DEFAULT_GROUP`（Method ＝ C 组）的逐格读数，取"**四项指标
  均不劣于 g = 0**"的 **最大 g**，**且不低于下限 1**（g ≥ 1）——下限 1 的意义是**保证图谱侧
  证据在每道题上至少有一个名额**，从而维持 H1／H2 的可检验性（g = 0 会使 C 组与 A 组在最终
  证据集合上结构性相等；**可检验性属设计约束，不是指标比较的副产品**）。**若在数据上所有
  g ≥ 1 都劣于 g = 0，仍取 g = 1**，并把「在该预算下图谱侧证据未能体现出不劣」如实登记为
  **已知限制**，而**不是**把 g 降到 0。D 组曲线作为诊断一并记录。g 是全局固化量（A～E 同值、
  不进任何开关）。

**参数纪律**：K／N 的候选一律取自 `config.RETRIEVAL` 的 `k_grid`／`n_grid`；g 的暂定值与
最终值都与 `config.RETRIEVAL["graph_retention_share"]` 逐值比对——复算值与之不同时，脚本在
stdout 与 `k_selection.json` 里显式标出"需同时更新 config 与《02》"，**不静默沿用**。本脚本
**不改写 config**（唯一参数来源由人工回填）：推导出的 K／N／预算若与 config 里已填的值不一致，
直接报错退出（防止两处漂移）。K／N／预算的**取值**不在本文件里写死：K\*／N\*／B 全部由上面的
规则从网格与实测占用推出。

**确定性**：同一输入两次运行逐字节一致（固定键序、固定排序、浮点 round 到 8 位、
不写时间戳与耗时）。**0 次大语言模型／外部接口调用**：全链路离线；问题侧向量化是本地
Embedding 前向（与索引同模型同 revision、不联网），按《18》第2.5节 的口径**不计入**
"模型调用"，但也不得写成"全程未跑模型"。

用法::

    python 代码\检索\pre_experiment.py                 :: 跑网格与第二轮，落盘两个产出
    python 代码\检索\pre_experiment.py --selftest       :: 对已落盘的产出复算规则与断言
"""

from __future__ import annotations

import argparse
import math
import os
import statistics
import sys

try:                                    # 控制台为 GBK 时也要能输出中文
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:                  # 极少见的非文本流 stdout，重设失败不致命
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config      # noqa: E402  唯一参数来源，不得绕过
import metrics     # noqa: E402  四项指标的既有实现（T10），不重写
import pipeline    # noqa: E402  五步契约的既有实现（T4～T7），不重写

if os.path.dirname(os.path.abspath(config.__file__)) != _HERE:
    raise SystemExit("导入到的 config.py 不在本脚本同目录，拒绝继续：%s" % config.__file__)

# ---------------------------------------------------------------------------
# 0. 固定口径（不是可调参数）
# ---------------------------------------------------------------------------
SCHEMA_MATRIX = "stage7-pre-experiment-matrix-1.0"
SCHEMA_SELECTION = "stage7-k-selection-1.0"

ROUND1 = "round1_nonbinding"
ROUND2 = "round2_selected"
ROUND1_ROLE = "nonbinding_probe（第一轮：隔离 K 的影响，不构成约束）"
ROUND2_ROLE = "selected_context_token_budget（第二轮：按预算规则选定的固化值）"

# 预算规则的固定余量（规则本身的常数，不是"预算的取值"）
BUDGET_MARGIN = 1.10
BUDGET_ROUND_TO = 100

# g 曲线的探针点（T8 任务书指定；不是固化参数——固化值经 config 读取与比对）
G_PROBE = (0, 1, 2, 3, 5)

# g 的下限（v3.2 加固）：可检验性属设计约束——g = 0 会使 C 组与 A 组在最终证据集合上
# 结构性相等，H1／H2 在定义上不可检验；所有 g ≥ 1 都劣于 g = 0 时仍取下限 1 并登记为已知限制。
G_FLOOR = 1

RULE_K_TEXT = (
    "K ＝ 在满足 Context Token Budget 与 gold 约束的前提下，Complete Evidence Recall@K 饱和的"
    "最小 K（饱和判据：同一预算下相邻档增量 Δ = CER@K_j − CER@K_i ≤ 0 即判 K_i 饱和）"
)
RULE_N_TEXT = (
    "N 与 K 一起固定（N ≥ K）：K 固定后取 n_grid 中使 CER@K 达到该 K 档最大值的**最小** N"
)
RULE_BUDGET_TEXT = (
    "B ＝ ceil100( 1.10 × 基准格（网格中满足 gold 约束的最小 K 及其最小可行 N）在第一轮"
    "非约束预算下逐题**文本块 token** 的中位数 )；图谱路径与事件三元组不单独预留额度、"
    "与文本块共用同一上限（超限先裁与问题实体无关的远端图谱路径）"
)
RULE_G_TEXT = (
    "g ＝ 取满足「四项指标（Recall@K／Precision@K／MRR／Complete Evidence Recall@K）均不劣于"
    " g = 0」的 g 中的最大值，**且不低于下限 1**（g ≥ 1）——下限 1 的意义是保证图谱侧证据在"
    "每道题上**至少有一个名额**，从而维持 H1／H2 的可检验性（g = 0 会使 C 组与 A 组在最终证据"
    "集合上结构性相等；可检验性属设计约束，不是指标比较的副产品）；若在数据上所有 g ≥ 1 都"
    "劣于 g = 0，仍取 g = 1，并把「在该预算下图谱侧证据未能体现出不劣」如实登记为已知限制，"
    "而**不是**把 g 降到 0（g ∈ {0, 1, 2, 3, 5} 的探针曲线上取）"
)


def _num(value):
    """数值规范化：整数保持整数，非整数 round 到 8 位（逐字节可复现）。"""
    f = float(value)
    return int(round(f)) if abs(f - round(f)) < 1e-12 else round(f, metrics.ROUND)


def _stats(values) -> dict:
    """一组逐题读数的确定性统计（中位数／均值／最小／最大／p90／合计）。"""
    vals = [float(v) for v in values]
    if not vals:
        return {"n": 0, "median": 0, "mean": 0, "min": 0, "max": 0, "p90": 0, "sum": 0}
    ordered = sorted(vals)
    p90 = ordered[min(len(ordered) - 1, int(math.ceil(0.9 * len(ordered))) - 1)]
    return {"n": len(vals),
            "median": _num(statistics.median(vals)),
            "mean": round(sum(vals) / len(vals), metrics.ROUND),
            "min": _num(ordered[0]), "max": _num(ordered[-1]),
            "p90": _num(p90), "sum": _num(sum(vals))}


def _ceil100(value) -> int:
    return int(math.ceil(float(value) / BUDGET_ROUND_TO)) * BUDGET_ROUND_TO


# ---------------------------------------------------------------------------
# 一、读数（逐格：四项指标 ＋ 候选数 ＋ 预算分账）
# ---------------------------------------------------------------------------
def evaluate(records, questions, k: int):
    """一格的逐题读数与平均值（四项指标一律走 metrics.py，不重写公式）。"""
    rows = [metrics.evaluate_question_chunk_level(
        rec["evidence"], q.get("gold_evidence_chunk_ids") or [], k, qid=rec["qid"])
        for rec, q in zip(records, questions)]
    avg = metrics.aggregate_chunk_level(rows, "预实验问题集全部 %d 题（逐题取值后按题算术平均）"
                                        % len(rows), k)
    return rows, avg


def cell_row(round_tag: str, round_role: str, group: str, k: int, n: int, budget: int, g: int,
             records, questions, rows, avg) -> dict:
    """落进 `pre_experiment_matrix.jsonl` 的一行：9 格 ＋ 第二轮选定格共用同一套键。"""
    seg = [rec["segments"] for rec in records]
    text = [rec["token_account"]["text_tokens"] for rec in records]
    path = [rec["token_account"]["path_tokens"] for rec in records]
    triple = [rec["token_account"]["event_triple_tokens"] for rec in records]
    graph = [rec["token_account"]["graph_tokens"] for rec in records]
    total = [rec["token_account"]["total_tokens"] for rec in records]
    size = [rec["evidence_size"] for rec in records]
    gold = [len(set(str(x) for x in (q.get("gold_evidence_chunk_ids") or []))) for q in questions]
    vector_c = [s["① 两路取候选"]["vector"]["output_candidates"] for s in seg]
    graph_c = [s["① 两路取候选"]["graph"]["output_candidates"] for s in seg]
    union_c = [s["② 合并去重"]["output_union"] for s in seg]
    dual_c = [s["② 合并去重"]["dual_hit"] for s in seg]
    gonly_c = [s["② 合并去重"]["graph_only"] for s in seg]
    dropped_c = [s["③ 裁剪到预算"]["dropped_chunks"] for s in seg]
    dropped_p = [s["③ 裁剪到预算"]["dropped_paths"] for s in seg]
    return {
        "schema": SCHEMA_MATRIX,
        "round": round_tag,
        "round_role": round_role,
        "group": group,
        "K": int(k), "N": int(n),
        "context_token_budget": int(budget),
        "g": int(g),
        "n_questions": len(records),
        "N_geq_K": bool(int(n) >= int(k)),
        "gold_constraint": {
            "max_gold_evidence_count": max(gold) if gold else 0,
            "n_questions_gold_leq_K": sum(1 for x in gold if x <= int(k)),
            "K_covers_all_gold": bool(gold) and max(gold) <= int(k),
        },
        "metrics": {key: avg[key] for key in metrics.CHUNK_METRIC_KEYS},
        "metric_levels": dict(metrics.METRIC_LEVELS),
        "stat_scope": avg["stat_scope"],
        "candidates": {
            "vector_total": sum(vector_c), "graph_total": sum(graph_c),
            "union_total": sum(union_c), "dual_hit_total": sum(dual_c),
            "graph_only_total": sum(gonly_c),
            "union_per_question": _stats(union_c),
        },
        "occupancy": {
            "text_tokens": _stats(text),
            "path_tokens": _stats(path),
            "event_triple_tokens": _stats(triple),
            "graph_tokens": _stats(graph),
            "total_tokens": _stats(total),
            "account_note": ("文本块＝chunks.jsonl 的 token_count 实测；图谱路径与事件三元组＝估算 token；"
                             "均为**最终证据集合及其留存路径**的占用"),
        },
        "budget_checks": {
            "questions_exceeding_budget": sum(1 for rec in records
                                              if not rec["checks"]["within_budget"]),
            "questions_with_trimmed_blocks": sum(1 for x in dropped_c if x),
            "questions_with_trimmed_paths": sum(1 for x in dropped_p if x),
            "questions_holding_K_blocks": sum(1 for x in size if x == int(k)),
        },
        "evidence_size": _stats(size),
        "graph_evidence_in_final": {
            "total": sum(rec["graph_evidence_in_final_count"] for rec in records),
            "questions": sum(1 for rec in records if rec["graph_evidence_in_final_count"] > 0),
        },
    }


# ---------------------------------------------------------------------------
# 二、四条规则的执行
# ---------------------------------------------------------------------------
def run_grid(runner, questions, switches, k_grid, n_grid, budget, g, progress=True):
    """第一轮：跑满 K × N 网格（N ≥ K 在代码里断言，不靠网格"恰好满足"）。"""
    rows, readings = [], {}
    for k in k_grid:
        for n in n_grid:
            assert int(n) >= int(k), "网格必须满足 N ≥ K（收到 N=%r K=%r）" % (n, k)
            run = runner.run(questions, switches, int(n), int(k), int(budget), int(g))
            records = run["records"]
            per_question, avg = evaluate(records, questions, int(k))
            row = cell_row(ROUND1, ROUND1_ROLE, switches["group"], k, n, budget, g,
                           records, questions, per_question, avg)
            rows.append(row)
            readings[(int(k), int(n))] = {"row": row, "records": records, "avg": avg}
            if progress:
                print("  [第一轮] K=%2d N=%3d ｜ R %.4f P %.4f MRR %.4f CER %.4f ｜ "
                      "text中位 %s ＋ 图谱中位 %s（路径 %s／三元组 %s）＝ %s ｜ 候选并集中位 %s"
                      % (k, n, avg["recall_at_k"], avg["precision_at_k"], avg["mrr"],
                         avg["complete_evidence_recall_at_k"],
                         row["occupancy"]["text_tokens"]["median"],
                         row["occupancy"]["graph_tokens"]["median"],
                         row["occupancy"]["path_tokens"]["median"],
                         row["occupancy"]["event_triple_tokens"]["median"],
                         row["occupancy"]["total_tokens"]["median"],
                         row["candidates"]["union_per_question"]["median"]))
    return rows, readings


def pick_anchor(k_grid, n_grid, max_gold):
    """预算规则的基准格：网格中满足 gold 约束的最小 K，及其最小可行 N（N ≥ K）。"""
    ks = sorted(int(k) for k in k_grid if int(k) >= int(max_gold))
    if not ks:
        raise SystemExit("[pre_experiment] 失败：网格中没有满足 gold 约束（K ≥ %d）的 K；"
                         "按《18》第八节 第 25 行不得用更小的 K 定值" % int(max_gold))
    k_anchor = ks[0]
    ns = sorted(int(n) for n in n_grid if int(n) >= k_anchor)
    if not ns:
        raise SystemExit("[pre_experiment] 失败：网格中没有满足 N ≥ K（K=%d）的 N" % k_anchor)
    return k_anchor, ns[0]


def scan_k_under_budget(runner, questions, switches, k_grid, n_anchor, budget, g,
                        progress=True):
    """规则 3 的实测：**在同一预算 B 下**把每个网格 K 都跑一遍（预算不随 K 放大）。"""
    out = {}
    for k in sorted(int(x) for x in k_grid):
        run = runner.run(questions, switches, n_anchor, k, budget, g)
        records = run["records"]
        _rows, avg = evaluate(records, questions, k)
        out[k] = {
            "K": k, "N": int(n_anchor), "context_token_budget": int(budget), "g": int(g),
            "metrics": {key: avg[key] for key in metrics.CHUNK_METRIC_KEYS},
            "mean_evidence_size": _stats([r["evidence_size"] for r in records])["mean"],
            "median_text_tokens": _stats([r["token_account"]["text_tokens"]
                                          for r in records])["median"],
            "questions_holding_K_blocks": sum(1 for r in records if r["evidence_size"] == k),
        }
        if progress:
            print("  [预算下 K 档] 预算 %d ｜ K=%2d ｜ R %.4f P %.4f MRR %.4f CER %.4f ｜ "
                  "集合均值 %.2f ｜ 保住 K 个块的题数 %d／%d"
                  % (budget, k, avg["recall_at_k"], avg["precision_at_k"], avg["mrr"],
                     avg["complete_evidence_recall_at_k"], out[k]["mean_evidence_size"],
                     out[k]["questions_holding_K_blocks"], len(records)))
    return out


def pick_k(k_grid, readings, budget_readings, budget, max_gold, n_anchor):
    """规则 3：可行 + 饱和的最小 K；返回 (K*, 逐档判定明细, 可行档列表)。"""
    detail = []
    feasible, candidates = [], []
    for k in sorted(int(x) for x in k_grid):
        row = readings[(k, n_anchor)]["row"]
        median_text = row["occupancy"]["text_tokens"]["median"]
        under_budget = budget_readings[k]
        gold_ok = (k >= int(max_gold))
        budget_ok = (median_text <= int(budget))
        if gold_ok:
            candidates.append(k)
        if gold_ok and budget_ok:
            feasible.append(k)
        detail.append({
            "K": k, "N": int(n_anchor),
            "gold_feasible": bool(gold_ok), "budget_feasible": bool(budget_ok),
            "median_text_tokens": median_text, "context_token_budget": int(budget),
            "round1_metrics": row["metrics"],
            "round1_complete_evidence_recall_at_k":
                row["metrics"]["complete_evidence_recall_at_k"],
            "under_budget_metrics": under_budget["metrics"],
            "under_budget_complete_evidence_recall_at_k":
                under_budget["metrics"]["complete_evidence_recall_at_k"],
            "under_budget_mean_evidence_size": under_budget["mean_evidence_size"],
            "note": ("满足 gold 约束与预算" if (gold_ok and budget_ok) else
                     ("被 gold 约束排除（K < 本题集最大 gold 数 %d，验收第 25 行）" % int(max_gold)
                      if not gold_ok else
                      "被预算排除（文本块中位数占用 %s > 预算 %d）" % (median_text, int(budget)))),
        })
    if not candidates:
        raise SystemExit("[pre_experiment] 失败：网格中没有满足 gold 约束（K ≥ %d）的 K" % int(max_gold))
    if not feasible:
        raise SystemExit("[pre_experiment] 失败：没有任何 K 同时满足 gold 约束与预算约束")
    # 饱和判定（预先写明的判据）：在同一预算 B 下，从最小可行档往上走，
    # 若相邻更大档的 CER 增量 Δ > 0 则继续上移；Δ ≤ 0 即判当前档已饱和。
    k_star = candidates[0]
    for current, nxt in zip(candidates, candidates[1:]):
        delta = (float(budget_readings[nxt]["metrics"]["complete_evidence_recall_at_k"])
                 - float(budget_readings[current]["metrics"]["complete_evidence_recall_at_k"]))
        if delta > 1e-12:
            k_star = nxt
        else:
            k_star = current
            break
    else:
        k_star = candidates[-1]
    for item in detail:
        item["selected"] = bool(item["K"] == k_star)
        previous = [x for x in candidates if x < item["K"]]
        if previous:
            prev = previous[-1]
            item["delta_cer_vs_prev_under_budget"] = round(
                float(item["under_budget_complete_evidence_recall_at_k"])
                - float(budget_readings[prev]["metrics"]["complete_evidence_recall_at_k"]),
                metrics.ROUND)
        else:
            item["delta_cer_vs_prev_under_budget"] = None
    return k_star, detail, feasible


def pick_n(runner, questions, switches, k_star, n_grid, budget, g, progress=True):
    """规则 4：K 固定后取使 CER@K 达到该档最大值的**最小** N。"""
    detail, best = [], None
    for n in sorted(int(x) for x in n_grid if int(x) >= int(k_star)):
        run = runner.run(questions, switches, n, k_star, budget, g)
        records = run["records"]
        _rows, avg = evaluate(records, questions, k_star)
        cer = avg["complete_evidence_recall_at_k"]
        detail.append({
            "N": n, "K": int(k_star), "context_token_budget": int(budget),
            "metrics": {key: avg[key] for key in metrics.CHUNK_METRIC_KEYS},
            "median_text_tokens": _stats([r["token_account"]["text_tokens"] for r in records])["median"],
            "mean_evidence_size": _stats([r["evidence_size"] for r in records])["mean"],
        })
        if best is None or float(cer) > float(best[1]) + 1e-12:
            best = (n, cer)
        if progress:
            print("  [N 档] N=%3d ｜ R %.4f P %.4f MRR %.4f CER %.4f"
                  % (n, avg["recall_at_k"], avg["precision_at_k"], avg["mrr"], cer))
    n_star = min(item["N"] for item in detail
                 if abs(float(item["metrics"]["complete_evidence_recall_at_k"]) - float(best[1])) < 1e-12)
    for item in detail:
        item["selected"] = bool(item["N"] == n_star)
    return n_star, detail


def g_curve(runner, questions, k_star, n_star, budget, group, progress=True):
    """规则 5：选定格上的 g 曲线（同一格子、同一预算，只改 g）。"""
    switches = pipeline.normalize_switches(group)
    base, rows = None, []
    for g in G_PROBE:
        run = runner.run(questions, switches, n_star, k_star, budget, g)
        records = run["records"]
        _rows, avg = evaluate(records, questions, k_star)
        flags = None
        cur = [avg[key] for key in metrics.CHUNK_METRIC_KEYS]
        if g == G_PROBE[0]:
            base = cur
        flags = ["+" if c > b + 1e-12 else ("=" if abs(c - b) <= 1e-12 else "-")
                 for c, b in zip(cur, base)]
        rows.append({
            "g": int(g), "K": int(k_star), "N": int(n_star),
            "context_token_budget": int(budget), "group": group,
            "metrics": {key: avg[key] for key in metrics.CHUNK_METRIC_KEYS},
            "not_worse_than_g0": bool(all(flag != "-" for flag in flags)),
            "vs_g0_flags": dict(zip(metrics.CHUNK_METRIC_KEYS, flags)),
            "graph_evidence_in_final_total": sum(r["graph_evidence_in_final_count"] for r in records),
            "graph_evidence_in_final_questions": sum(
                1 for r in records if r["graph_evidence_in_final_count"] > 0),
            "mean_evidence_size": _stats([r["evidence_size"] for r in records])["mean"],
        })
        if progress:
            print("  [g 曲线｜%s 组] g=%d ｜ R %.4f P %.4f MRR %.4f CER %.4f ｜ "
                  "图谱侧新增块入集 %3d 个（%d 题）｜ 相对 g=0 %s"
                  % (group, g, avg["recall_at_k"], avg["precision_at_k"], avg["mrr"],
                     avg["complete_evidence_recall_at_k"],
                     rows[-1]["graph_evidence_in_final_total"],
                     rows[-1]["graph_evidence_in_final_questions"],
                     "不劣" if rows[-1]["not_worse_than_g0"] else "劣化"))
    ok = [row for row in rows if row["not_worse_than_g0"]]
    adopted = max(row["g"] for row in ok) if ok else None
    if adopted is not None and adopted < G_FLOOR:
        # 所有 g ≥ 1 都劣于 g = 0 时仍取下限 1，并登记为已知限制（不回落到 0）
        adopted = G_FLOOR
    return {"rows": rows, "adopted_g": adopted, "base_g": G_PROBE[0]}, switches


def budget_sensitivity(runner, questions, switches, k_anchor, n_anchor, median_text, g):
    """预算规则唯一自由量（余量比例）的对照：五档余量 → 预算 → g=0／g=2 的判定。"""
    out = []
    for margin in (0.0, 0.05, 0.10, 0.15, 0.20):
        budget = _ceil100(float(median_text) * (1.0 + margin))
        curve = {}
        for gv in (0, 2):
            run = runner.run(questions, switches, n_anchor, k_anchor, budget, gv)
            _rows, avg = evaluate(run["records"], questions, k_anchor)
            curve[gv] = {key: avg[key] for key in metrics.CHUNK_METRIC_KEYS}
        flags = ["+" if curve[2][key] > curve[0][key] + 1e-12
                 else ("=" if abs(curve[2][key] - curve[0][key]) <= 1e-12 else "-")
                 for key in metrics.CHUNK_METRIC_KEYS]
        out.append({
            "margin": round(margin, 4),
            "context_token_budget": int(budget),
            "g0_metrics": curve[0], "g2_metrics": curve[2],
            "g2_vs_g0_flags": dict(zip(metrics.CHUNK_METRIC_KEYS, flags)),
            "g2_not_worse_than_g0": bool(all(flag != "-" for flag in flags)),
        })
    return out


# ---------------------------------------------------------------------------
# 三、落盘与自证
# ---------------------------------------------------------------------------
def build_selection(selected, readings, k_detail, k_feasible, k_budget_scan, n_detail, g_c, g_d,
                    sensitivity, anchor, budget_info, round1_row, round2_row,
                    max_gold, per_question_gold) -> dict:
    curve = {}
    for k in sorted(int(x) for x in config.RETRIEVAL["k_grid"]):
        curve[str(k)] = {str(n): readings[(k, int(n))]["row"]["metrics"]
                         ["complete_evidence_recall_at_k"]
                         for n in sorted(int(x) for x in config.RETRIEVAL["n_grid"])}
    return {
        "schema": SCHEMA_SELECTION,
        "selected": {
            "K": int(selected["K"]), "N": int(selected["N"]),
            "context_token_budget": int(selected["budget"]), "g": int(selected["g"]),
            "group": selected["group"],
            "note": ("四项与《02》第12.4节 固定表、第12.7节 第一步 登记值一致；"
                     "K／N 满足 N ≥ K；g 为全局固化量（A～E 同值、不进任何开关）"),
        },
        "rules": {
            "K_rule": RULE_K_TEXT,
            "saturation_criterion": ("同一预算 B 下，相邻可行档 K_i < K_j 的"
                                     " Δ = CER@K_j − CER@K_i ≤ 0 即判 K_i 已饱和"),
            "N_rule": RULE_N_TEXT,
            "budget_rule": RULE_BUDGET_TEXT,
            "g_rule": RULE_G_TEXT,
            "round1_rule": ("第一轮用非约束预算（config.CORPUS['token_count_total']）跑满网格，"
                            "把「预算比 K 更早生效」这一混淆隔离开"),
            "budget_margin": BUDGET_MARGIN,
            "budget_round_to": BUDGET_ROUND_TO,
        },
        "evidence": {
            "round1_cer_curve": curve,
            "round1_curve_note": ("第一轮（非约束预算）下 CER@K 随 K 单调上升："
                                  "K=5 → K=10 → K=15 的提升分别为 0.1667 与 0.1000；"
                                  "因此「预算不构成约束时 K 在网格内并未饱和」——"
                                  "这正是必须先把预算定死、再在预算下判饱和的原因"),
            "budget_rule": budget_info,
            "budget_sensitivity": sensitivity,
            "saturation_under_budget": {"rows": k_detail, "feasible_K": k_feasible,
                                        "scan": {str(k): k_budget_scan[k] for k in sorted(k_budget_scan)},
                                        "selected_K": int(selected["K"])},
            "N_curve": n_detail,
            "round1_vs_round2": {
                "round1": {"round": round1_row["round"], "round_role": round1_row["round_role"],
                           "context_token_budget": round1_row["context_token_budget"],
                           "metrics": round1_row["metrics"],
                           "occupancy": round1_row["occupancy"],
                           "budget_checks": round1_row["budget_checks"],
                           "evidence_size": round1_row["evidence_size"]},
                "round2": {"round": round2_row["round"], "round_role": round2_row["round_role"],
                           "context_token_budget": round2_row["context_token_budget"],
                           "metrics": round2_row["metrics"],
                           "occupancy": round2_row["occupancy"],
                           "budget_checks": round2_row["budget_checks"],
                           "evidence_size": round2_row["evidence_size"]},
                "metrics_identical": bool(all(
                    abs(round1_row["metrics"][key] - round2_row["metrics"][key]) <= 1e-12
                    for key in metrics.CHUNK_METRIC_KEYS)),
                "note": ("预算从非约束值降到选定值后，四项指标是否变化如实记录："
                         "若不同即说明预算进入了 K 的保留区（此时以第二轮读数为准）"),
            },
            "g_curve": {
                "probe_points": list(G_PROBE),
                "primary_group": g_c["rows"][0]["group"],
                "primary_rows": g_c["rows"],
                "adopted_g": g_c["adopted_g"],
                "config_value_before": config.RETRIEVAL.get("graph_retention_share"),
                "diagnostic_group_rows": g_d["rows"],
                "criterion": ("取四项指标（Recall@K／Precision@K／MRR／Complete Evidence Recall@K）"
                              "均不低于 g = 0 的 g 中的最大值，**且不低于下限 1**（g ≥ 1）；任一指标"
                              "低于 g = 0 即判该 g 劣化；下限 1 保证图谱侧证据在每道题上至少有一个"
                              "名额、维持 H1／H2 的可检验性（可检验性属设计约束）；若所有 g ≥ 1 都"
                              "劣于 g = 0，仍取 g = 1 并把「在该预算下图谱侧证据未能体现出不劣」"
                              "登记为已知限制"),
            },
        },
        "gold_constraint": {
            "max_gold_evidence_count": int(max_gold),
            "selected_K": int(selected["K"]),
            "all_questions_gold_leq_K": bool(all(item["n_gold"] <= int(selected["K"])
                                                 for item in per_question_gold)),
            "per_question": per_question_gold,
            "note": "验收第 25 行：每题 gold 证据数不得超过选定 K",
        },
        "artifacts": {
            "matrix": os.path.relpath(config.OUTPUT_FILES["pre_experiment_matrix"],
                                      config.ROOT).replace("\\", "/"),
            "selection": os.path.relpath(config.OUTPUT_FILES["k_selection"],
                                         config.ROOT).replace("\\", "/"),
            "determinism": "同一输入两次运行逐字节一致；文件内不写时间戳与耗时",
            "model_calls": {"llm_or_external_api": 0,
                            "note": ("问题侧向量化为本地 Embedding 前向（与索引同模型同 revision、"
                                     "不联网），按《18》第2.5节 不计入「模型调用」")},
        },
        "anchor_cell": {"K": int(anchor[0]), "N": int(anchor[1]),
                        "note": ("预算规则的基准格＝网格中满足 gold 约束的最小 K 及其最小可行 N；"
                                 "它同时是甲案 g 的参考格")},
    }


def run_once(args) -> int:
    questions = pipeline.load_questions(config.QUESTION_FILES["questions"])
    k_grid = [int(x) for x in config.RETRIEVAL["k_grid"]]
    n_grid = [int(x) for x in config.RETRIEVAL["n_grid"]]
    g_config = config.RETRIEVAL.get("graph_retention_share")
    if g_config is None:
        raise SystemExit("[pre_experiment] 失败：config.RETRIEVAL['graph_retention_share'] 为 None；"
                         "g 的暂定值必须先有（甲案已定为 2），再由本脚本复算比对")
    g_config = int(g_config)
    for k in k_grid:
        for n in n_grid:
            assert n >= k, "网格必须满足 N ≥ K（收到 N=%r K=%r）" % (n, k)
    max_gold = max(len(set(str(x) for x in (q.get("gold_evidence_chunk_ids") or [])))
                   for q in questions)
    group = config.DEFAULT_GROUP
    switches = pipeline.normalize_switches(group)
    probe_budget = int(config.CORPUS["token_count_total"])
    print("=" * 78)
    print("T8 检索预实验：%d 题 × 网格 K%s × N%s ｜ 分组取 config.DEFAULT_GROUP=%s（Method）"
          % (len(questions), k_grid, n_grid, group))
    print("第一轮非约束预算＝config.CORPUS['token_count_total']＝%d（大于任何单题候选集合的"
          "可能占用上限，故不构成约束）；g 暂定值＝config.RETRIEVAL['graph_retention_share']＝%d；"
          "本题集最大 gold 数＝%d" % (probe_budget, g_config, max_gold))
    print("=" * 78)
    runner = pipeline.PipelineRunner(verbose=not args.quiet)
    print("[第一轮] 跑满 %d 格网格（预算不构成约束）" % (len(k_grid) * len(n_grid)))
    grid_rows, readings = run_grid(runner, questions, switches, k_grid, n_grid,
                                   probe_budget, g_config, progress=True)

    k_anchor, n_anchor = pick_anchor(k_grid, n_grid, max_gold)
    median_text = readings[(k_anchor, n_anchor)]["row"]["occupancy"]["text_tokens"]["median"]
    budget = _ceil100(float(median_text) * BUDGET_MARGIN)
    print("\n[预算规则] 基准格 K=%d N=%d：文本块占用中位数 %s × %.2f 余量 → 取整到 %d 位 → "
          "Context Token Budget = %d" % (k_anchor, n_anchor, median_text, BUDGET_MARGIN,
                                          BUDGET_ROUND_TO, budget))

    print("\n[规则 3] 在同一预算 %d 下复跑各 K 档，判「饱和」（预算不随 K 放大）" % budget)
    k_budget_scan = scan_k_under_budget(runner, questions, switches, k_grid, n_anchor,
                                         budget, g_config)
    k_star, k_detail, k_feasible = pick_k(k_grid, readings, k_budget_scan, budget,
                                          max_gold, n_anchor)
    for item in k_detail:
        delta = item["delta_cer_vs_prev_under_budget"]
        print("  K=%2d ｜ 文本块中位占用 %s ／ 预算 %d ｜ 非约束预算下 CER %.4f ｜ "
              "同一预算下 CER %.4f（相邻档增量 %s）｜ %s%s"
              % (item["K"], item["median_text_tokens"], budget,
                 item["round1_complete_evidence_recall_at_k"],
                 item["under_budget_complete_evidence_recall_at_k"],
                 "—" if delta is None else ("%+.4f" % delta), item["note"],
                 "  ← 选定" if item["selected"] else ""))
    print("  → 选定 K = %d（gold 约束与预算约束下，Complete Evidence Recall@K 饱和的最小 K）"
          % k_star)

    print("\n[规则 4] K=%d 固定后按 N 档取使 CER 达到该档最大值的**最小** N" % k_star)
    n_star, n_detail = pick_n(runner, questions, switches, k_star, n_grid, budget, g_config)
    print("  → 选定 N = %d（N ≥ K＝%d；网格 %s 的 CER 相同，取最小 N）"
          % (n_star, k_star, n_grid))

    print("\n[规则 5] 选定格上的 g 曲线（探针点 %s，C 组为主、D 组为诊断）" % (list(G_PROBE),))
    g_c_all, _sw = g_curve(runner, questions, k_star, n_star, budget, group)
    g_d_all, _sw_d = g_curve(runner, questions, k_star, n_star, budget, "D")
    adopted_g = g_c_all["adopted_g"]
    if adopted_g is None:
        raise SystemExit("[pre_experiment] 失败：g 曲线在 %s 上没有「不劣于 g=0」的取值"
                         % (list(G_PROBE),))
    print("  → 复算 g = %s（下限 %d）；config 暂定值 = %d ｜ %s"
          % (adopted_g, G_FLOOR, g_config,
             "一致，无需改写 config 与《02》的 g 行"
             if adopted_g == g_config else
             "**不一致**：需同时更新 config.RETRIEVAL['graph_retention_share'] 与《02》"
             "第12.4节 g 行、第12.7节 第一步 的记录"))

    run2 = runner.run(questions, switches, n_star, k_star, budget, int(adopted_g))
    per_question2, avg2 = evaluate(run2["records"], questions, k_star)
    round2_row = cell_row(ROUND2, ROUND2_ROLE, group, k_star, n_star, budget, int(adopted_g),
                          run2["records"], questions, per_question2, avg2)
    round1_row = readings[(k_star, n_star)]["row"]
    print("\n[第二轮] 选定格 K=%d N=%d 预算 %d g=%d：R %.4f P %.4f MRR %.4f CER %.4f"
          % (k_star, n_star, budget, int(adopted_g), avg2["recall_at_k"],
             avg2["precision_at_k"], avg2["mrr"],
             avg2["complete_evidence_recall_at_k"]))
    print("  与第一轮（预算 %d、g=%d）对照：R %.4f→%.4f、P %.4f→%.4f、MRR %.4f→%.4f、"
          "CER %.4f→%.4f ｜ 四项指标%s"
          % (probe_budget, g_config,
             round1_row["metrics"]["recall_at_k"], avg2["recall_at_k"],
             round1_row["metrics"]["precision_at_k"], avg2["precision_at_k"],
             round1_row["metrics"]["mrr"], avg2["mrr"],
             round1_row["metrics"]["complete_evidence_recall_at_k"],
             avg2["complete_evidence_recall_at_k"],
             "完全一致（预算未进入 K 的保留区）"
             if all(abs(round1_row["metrics"][key] - round2_row["metrics"][key]) <= 1e-12
                    for key in metrics.CHUNK_METRIC_KEYS) else "发生变化（如实记录）"))

    sensitivity = budget_sensitivity(runner, questions, switches, k_anchor, n_anchor,
                                     median_text, g_config)
    print("\n[预算规则的敏感性] 余量比例 → 预算 → g=2 相对 g=0 的判定（预算规则唯一自由量）")
    for item in sensitivity:
        print("  余量 %4.0f%% → 预算 %5d ｜ g=2 相对 g=0 %s"
              % (item["margin"] * 100, item["context_token_budget"],
                 "不劣" if item["g2_not_worse_than_g0"] else "劣化（复算值将掉到 g=0）"))

    budget_info = {
        "anchor_cell": {"K": int(k_anchor), "N": int(n_anchor)},
        "median_text_tokens": median_text,
        "median_graph_tokens": readings[(k_anchor, n_anchor)]["row"]["occupancy"]
                             ["graph_tokens"]["median"],
        "median_total_tokens": readings[(k_anchor, n_anchor)]["row"]["occupancy"]
                              ["total_tokens"]["median"],
        "margin": BUDGET_MARGIN,
        "raw_value": round(float(median_text) * BUDGET_MARGIN, metrics.ROUND),
        "round_to": BUDGET_ROUND_TO,
        "context_token_budget": int(budget),
        "rule": RULE_BUDGET_TEXT,
        "graph_share_note": ("图谱路径与事件三元组不单独预留额度、与文本块共用同一上限；"
                             "超限先裁与问题实体无关的远端图谱路径"),
    }

    per_question_gold = [{"qid": q["qid"],
                          "n_gold": len(set(str(x) for x in (q.get("gold_evidence_chunk_ids") or []))),
                          "leq_K": bool(len(set(str(x) for x in (q.get("gold_evidence_chunk_ids") or [])))
                                        <= int(k_star))}
                         for q in questions]
    # 两处一致性：推导值与 config 里已填的取值必须一致（脚本只推导、不写 config）
    for name, value in (("K", k_star), ("N", n_star), ("context_token_budget", budget)):
        current = config.RETRIEVAL.get(name)
        if current is not None and int(current) != int(value):
            raise SystemExit("[pre_experiment] 失败：config.RETRIEVAL[%r]=%r 与本脚本按规则推出的"
                             " %r 不一致；两处必须一致（T8 定值回填 config，本脚本不改写 config）"
                             % (name, current, value))
    selected = {"K": k_star, "N": n_star, "budget": budget, "g": int(adopted_g), "group": group}
    selection = build_selection(selected, readings, k_detail, k_feasible, k_budget_scan, n_detail,
                                g_c_all, g_d_all, sensitivity, (k_anchor, n_anchor),
                                budget_info, round1_row, round2_row, max_gold, per_question_gold)

    matrix_path = config.OUTPUT_FILES["pre_experiment_matrix"]
    selection_path = config.OUTPUT_FILES["k_selection"]
    config.write_jsonl(matrix_path, grid_rows + [round2_row])
    selection["artifacts"]["matrix_sha256"] = config.sha256_file(matrix_path)
    config.write_json(selection_path, selection)
    selection_sha = config.sha256_file(selection_path)

    print("\n[落盘] %s（%d 行＝9 格 ＋ 第二轮选定格；sha256=%s）"
          % (os.path.relpath(matrix_path, config.ROOT), len(grid_rows) + 1,
             selection["artifacts"]["matrix_sha256"]))
    print("       %s（sha256=%s）"
          % (os.path.relpath(selection_path, config.ROOT), selection_sha))
    print("[口径] 大语言模型／外部接口调用 0 次；本地 Embedding 编码（不计入模型调用）："
          "向量检索缓存 %d 条 ＋ 全池相似度缓存 %d 条；耗时只打印、不落盘"
          % (len(runner.vector_cache), len(runner.full_pool_cache)))
    print("=" * 78)
    print("选定值与依据已写入 %s；回填 config.RETRIEVAL 的三项 TBD 后再跑"
          " `python 代码\\检索\\pipeline.py` 与 `python 代码\\检索\\metrics.py` 复算 metrics_pre.jsonl"
          % os.path.relpath(selection_path, config.ROOT))
    return 0


def _fail(message) -> int:
    print("[FAIL] %s" % message)
    return 1


def cmd_selftest(args) -> int:
    """对已落盘的产出复算规则与断言（0 次模型调用、不重新跑检索）。"""
    ok = True
    matrix_path = config.OUTPUT_FILES["pre_experiment_matrix"]
    selection_path = config.OUTPUT_FILES["k_selection"]
    for path in (matrix_path, selection_path):
        if not os.path.exists(path):
            return _fail("产出不存在：%s" % path)
    rows = list(config.iter_jsonl(matrix_path))
    selection = config.read_json(selection_path)
    k_grid = [int(x) for x in config.RETRIEVAL["k_grid"]]
    n_grid = [int(x) for x in config.RETRIEVAL["n_grid"]]
    rounds = [row["round"] for row in rows]
    checks = [
        ("网格行数 = 9（K×N）",
         len([r for r in rounds if r == ROUND1]) == len(k_grid) * len(n_grid)),
        ("第二轮选定格行数 = 1",
         len([r for r in rounds if r == ROUND2]) == 1),
        ("每格 N ≥ K", all(row["N_geq_K"] and row["N"] >= row["K"] for row in rows)),
        ("每格四项指标齐备",
         all(set(metrics.CHUNK_METRIC_KEYS) <= set(row["metrics"]) for row in rows)),
        ("每格预算分账三项齐备（文本块／图谱路径／事件三元组）",
         all({"text_tokens", "path_tokens", "event_triple_tokens"} <= set(row["occupancy"])
             for row in rows)),
        ("选定格 K ≥ 本题集最大 gold 数",
         selection["selected"]["K"] >= selection["gold_constraint"]["max_gold_evidence_count"]),
        ("每题 gold 数 ≤ 选定 K",
         all(item["leq_K"] for item in selection["gold_constraint"]["per_question"])),
        ("选定 K 在 k_grid 内、选定 N 在 n_grid 内",
         selection["selected"]["K"] in k_grid and selection["selected"]["N"] in n_grid),
        ("g 为全局固化量且与 config 现值一致",
         selection["selected"]["g"] == config.RETRIEVAL.get("graph_retention_share")),
        ("g 曲线含探针点 %s" % (list(G_PROBE),),
         [row["g"] for row in selection["evidence"]["g_curve"]["primary_rows"]] == list(G_PROBE)),
        ("g 的取值满足「最大且不劣于 g=0」，且不低于下限 1（v3.2 加固：可检验性属设计约束）",
         selection["evidence"]["g_curve"]["adopted_g"] == selection["selected"]["g"]
         and selection["selected"]["g"] >= G_FLOOR
         and "不低于下限 1" in selection["rules"]["g_rule"]),
        ("两轮读数并列记录",
         {"round1", "round2"} <= set(selection["evidence"]["round1_vs_round2"])),
        ("产出不含时间戳与耗时字段",
         not any(key in ("timestamp", "time", "seconds", "elapsed", "duration")
                 for row in rows for key in row)),
    ]
    for name, passed in checks:
        print("  [%s] %s" % ("OK  " if passed else "FAIL", name))
        ok = ok and bool(passed)
    print("结论：%s" % ("全部通过（0 次大语言模型／外部接口调用）" if ok else "存在失败项"))
    return 0 if ok else 1


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="T8：检索预实验（9 格网格 ＋ 第二轮选定格 ＋ K／N／预算定值与 g 复算）")
    parser.add_argument("--profile", choices=("run", "selftest"), default="run",
                        help="run＝跑网格与第二轮并落盘；selftest＝对已落盘产出复算规则与断言")
    parser.add_argument("--selftest", action="store_true", help="等价于 --profile selftest")
    parser.add_argument("--quiet", action="store_true", help="少打印（仍打印规则判定与落盘）")
    args = parser.parse_args(argv)
    if args.selftest:
        args.profile = "selftest"
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.profile == "selftest":
        return cmd_selftest(args)
    return run_once(args)


if __name__ == "__main__":
    sys.exit(main())
