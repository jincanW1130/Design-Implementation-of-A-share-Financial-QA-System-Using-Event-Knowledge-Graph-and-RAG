# -*- coding: utf-8 -*-
"""对抗实验：pipeline.py 的四条断言是否**可失败**（非空转），以及 g 的边界行为。"""
import io
import os
import re
import sys

MIR = r"C:\Users\15129\AppData\Local\Temp\re7_B\mirror"
sys.path.insert(0, os.path.join(MIR, "代码", "检索"))
import pipeline as P  # noqa: E402

print("=" * 78)
print("A. 四条断言的「可失败性」（喂入被污染的输入，断言必须判假）")
print("=" * 78)

# --- 断言 1：D ≡ E —— 喂入集合不同的两份记录
ok = [{"qid": "Q1", "evidence": [1, 2, 3]}, {"qid": "Q2", "evidence": [7]}]
bad = [{"qid": "Q1", "evidence": [1, 2]}, {"qid": "Q2", "evidence": [7]}]
r = P.assert_d_equals_e(ok, ok)
print("断言1 正确输入   -> ok=%s（应为 True）" % r["ok"])
r = P.assert_d_equals_e(ok, bad)
print("断言1 污染输入   -> ok=%s（应为 False）  missing_in_e=%s"
      % (r["ok"], r["per_question"][0]["missing_in_e"]))
# 顺序不同但集合相同 -> 仍 True（这正是「逐题相等」的语义）
shuf = [{"qid": "Q1", "evidence": [3, 1, 2]}, {"qid": "Q2", "evidence": [7]}]
r = P.assert_d_equals_e(ok, shuf)
print("断言1 仅顺序不同 -> ok=%s（应为 True，语义=集合相等）；order_differs=%s"
      % (r["ok"], r["per_question"][0]["order_differs"]))

# --- 断言 2：C 与 D 可以不同
c = [{"qid": "Q1", "candidates_filtered": [1, 2, 3]}]
d = [{"qid": "Q1", "candidates_filtered": [1, 2]}]
print("断言2 有差异     -> ok=%s、可测题=%d（应为 True/1）"
      % (P.assert_c_vs_d(c, d)["ok"], P.assert_c_vs_d(c, d)["measurable_questions"]))
d2 = [{"qid": "Q1", "candidates_filtered": [3, 2, 1]}]
r = P.assert_c_vs_d(c, d2)
print("断言2 完全相同   -> ok=%s（应为 False，即「==」不成立）" % r["ok"])

# --- 断言 3：同一 chunk 只算一次
dup = [{"qid": "Q1", "evidence": [1, 1, 2], "candidates_filtered": [1, 2]}]
print("断言3 有重复     -> ok=%s（应为 False）" % P.assert_dedup(dup)["ok"])
uniq = [{"qid": "Q1", "evidence": [1, 2], "candidates_filtered": [2, 1]}]
print("断言3 无重复     -> ok=%s（应为 True）" % P.assert_dedup(uniq)["ok"])

# --- 断言 4：Precision@K 分母恒为 K —— 直接看其判据函数（需要 runner）
print("断言4 需要真实 runner，见 B 段（用镜像重跑产物核对）。")

print()
print("=" * 78)
print("B. 断言 4 的判据：用镜像里的 metrics 产物**独立重算**「分母是不是 K」")
print("=" * 78)
import json  # noqa: E402

mi = os.path.join(MIR, "阶段07-RAG检索系统", "检索产出", "metrics_pre.jsonl")
rows = [json.loads(l) for l in io.open(mi, encoding="utf-8") if l.strip()]
q = [r for r in rows if r.get("qid")]
badK, badM, vac = [], [], []
for r in q:
    if r["precision_at_k"] != round(r["n_hit"] / float(r["K"]), 8):
        badK.append(r["qid"])
    if r["n_final"] and r["precision_at_k"] != round(r["n_hit"] / float(r["n_final"]), 8):
        badM.append(r["qid"])          # 若按 M 作分母也不等，说明确实用的是 K
    if r["n_final"] < r["K"]:
        vac.append((r["qid"], r["n_final"], r["K"], r["precision_at_k"]))
print("逐题行数 =", len(q))
print("按 K 作分母不等的题 =", badK, "（应为空）")
print("按 M=n_final 作分母**会**不等（即不是按 M）的题数 =", len(badM))
print("n_final < K 的题（空缺记未命中，分母仍 K）：")
for t in vac:
    print("   qid=%s n_final=%d K=%d P@K=%.8f  (=n_hit/%d)" % (t[0], t[1], t[2], t[3], t[2]))
print("n_final 最小值 =", min(r["n_final"] for r in q), "；K =", q[0]["K"])

print()
print("=" * 78)
print("C. 分层保留顺序：g=0 是否与原字面键同序；g>0 是否真的改变次序；g 越界行为")
print("=" * 78)


def rec(cid, rank=None, sim=None, first=None):
    d = {"chunk_id": cid}
    if rank is not None:
        d["vector_rank"] = rank
    if sim is not None:
        d["question_similarity"] = sim
    if first is not None:
        d["first_path_key"] = first
    return d


# 候选：向量侧 4 个（rank 1..4），图谱侧 3 个（无向量排名），K=5,g=2
recs = [rec(101, rank=1), rec(102, rank=2), rec(103, rank=3), rec(104, rank=4),
        rec(201, sim=0.9, first=(5, 1)), rec(202, sim=0.5, first=(6, 2)),
        rec(203, sim=0.7, first=(7, 3))]
K, G = 5, 2
plan = P.plan_graph_layer(recs, K, G)
print("plan_graph_layer(K=%d,g=%d) 第二层名额 = %s" % (K, G, plan["layer2_ids"]))
asc_new = [r["chunk_id"] for r in sorted(recs, key=P.retention_key(K, G, plan["layer2_positions"]))]
asc_leg = [r["chunk_id"] for r in sorted(recs, key=P.legacy_priority_key)]
print("分层键(g=2) 升序 =", asc_new)
print("原字面键     升序 =", asc_leg)
print("二者相同 =", asc_new == asc_leg, "（应 False：g=2 确实改变次序 -> 断言 5 非空转）")
asc_g0 = [r["chunk_id"] for r in sorted(recs, key=P.retention_key(K, 0, {}))]
print("分层键(g=0) 升序 =", asc_g0)
print("分层键(g=0) == 原字面键 =", asc_g0 == asc_leg, "（应 True：g=0 退化）")

print()
print("--- g 越界 / 负数 ---")
for g in (-1, 0, 1, K, K + 1, 999):
    try:
        key = P.retention_key(K, g, P.plan_graph_layer(recs, K, g)["layer2_positions"])
        seq = [r["chunk_id"] for r in sorted(recs, key=key)]
        print("  g=%-4d plan.layer2=%s  前K个=%s"
              % (g, P.plan_graph_layer(recs, K, g)["layer2_ids"], seq[:K]))
    except Exception as exc:
        print("  g=%-4d -> %s: %s" % (g, type(exc).__name__, exc))
try:
    P.evidence_priority_key(rec(201, sim=0.9), K, -5)
    print("  evidence_priority_key(g=-5) 未抛错（内部 max(0,int(g)) 夹取）")
except Exception as exc:
    print("  evidence_priority_key(g=-5) ->", type(exc).__name__, exc)

print()
print("--- CLI 边界：resolve_k_n_budget 对越界 g 是否拒绝 ---")


class _A:
    k, n, budget, graph_share = 10, 20, 3600, None


for g in (-1, 11, 10, 0):
    a = _A()
    a.graph_share = g
    try:
        out = P.resolve_k_n_budget(a)
        print("  --graph-share=%-3d -> 接受 %s" % (g, out))
    except SystemExit as exc:
        print("  --graph-share=%-3d -> SystemExit: %s" % (g, exc))
a = _A(); a.k, a.n = 20, 10
try:
    P.resolve_k_n_budget(a)
    print("  N<K -> 接受（不应发生）")
except SystemExit as exc:
    print("  N<K -> SystemExit: %s" % (exc,))

print()
print("=" * 78)
print("D. legacy_priority_key 是否与**修订前**（b64953f）的 evidence_priority_key 同义")
print("=" * 78)
old = io.open(r"C:\Users\15129\AppData\Local\Temp\re7_B\old_pipeline.py", encoding="utf-8").read()
m = re.search(r"def evidence_priority_key\(record\) -> tuple:(.*?)\n\n", old, re.S)
body = m.group(1) if m else "(未找到)"
print("旧函数体（b64953f 代码/检索/pipeline.py）:")
for line in body.strip().split("\n"):
    print("   ", line)
new = io.open(os.path.join(MIR, "代码", "检索", "pipeline.py"), encoding="utf-8").read()
m2 = re.search(r"def legacy_priority_key\(record\) -> tuple:(.*?)\n\n\n", new, re.S)
print("新 legacy_priority_key 函数体:")
for line in (m2.group(1).strip().split("\n") if m2 else ["(未找到)"]):
    print("   ", line)
