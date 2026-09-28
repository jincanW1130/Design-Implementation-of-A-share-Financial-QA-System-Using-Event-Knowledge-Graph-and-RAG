# -*- coding: utf-8 -*-
"""主审独立复核子代理的产物级结论（不采信自述）。只读工作区。"""
import io
import json
import math
import os

WS = r"C:\Users\15129\Desktop\毕业设计"
KS = os.path.join(WS, "阶段07-RAG检索系统", "检索产出", "k_selection.json")
s = json.load(io.open(KS, encoding="utf-8"))

print("== B-18 复核：round1_curve_note 硬编码数字 vs 同产物 round1_cer_curve ==")
note = None
ev = s.get("evidence", {})
for k, v in ev.items():
    if isinstance(v, str) and "0.1000" in v:
        note = (k, v)
print("  含 0.1000 的字段：", note)
rc = ev.get("round1_cer_curve") or {}
print("  round1_cer_curve 键 =", sorted(rc))
for a, b in ((5, 10), (10, 15)):
    row = []
    for n in ("20", "50", "100"):
        try:
            row.append((n, round(rc[str(b)][n] - rc[str(a)][n], 8)))
        except Exception as e:
            row.append((n, str(e)))
    print("  delta K=%d->%d :" % (a, b), row)

print()
print("== B-19 复核：config 敏感性叙述 vs 同产物 budget_sensitivity ==")
bs = ev.get("budget_sensitivity")
print("  budget_sensitivity 存在 =", bool(bs))
if bs:
    rows = bs if isinstance(bs, list) else bs.get("rows") or bs.get("cells") or []
    print("  结构键 =", list(bs)[:12] if isinstance(bs, dict) else "(list)")
    def show(r):
        print("   margin=%s budget=%s g0_mrr=%s g2_mrr=%s nw=%s" % (
            r.get("margin"), r.get("budget"), r.get("g0_mrr"), r.get("g2_mrr"),
            r.get("g2_not_worse_than_g0")))
    if isinstance(rows, list):
        for r in rows:
            if isinstance(r, dict):
                show(r)

print()
print("== B-21/B-22 复核：budget_feasible 读数与预算下 scan 的矛盾 ==")
sat = ev.get("saturation_under_budget") or {}
for r in sat.get("rows") or []:
    print("  K=%s median_text_tokens=%s budget=%s budget_feasible=%s gold_feasible=%s" % (
        r.get("K"), r.get("median_text_tokens"), r.get("context_token_budget"),
        r.get("budget_feasible"), r.get("gold_feasible")))
scan = s.get("scan") or s.get("scans")
if isinstance(scan, dict):
    for k, v in scan.items():
        if isinstance(v, dict) and "median_text_tokens" in v:
            print("  scan[%s].median_text_tokens=%s questions_holding_K_blocks=%s" % (
                k, v.get("median_text_tokens"), v.get("questions_holding_K_blocks")))

print()
print("== B-20 复核：预算由 K=10 基准格推出，再判 K=10 饱和 ==")
br = ev.get("budget_rule") or {}
print("  budget_rule =", br)
print("  rules.budget_margin =", (s.get("rules") or {}).get("budget_margin"))

print()
print("== 行 22/V 复核：selected 值 ==")
print("  selected =", s.get("selected"))
