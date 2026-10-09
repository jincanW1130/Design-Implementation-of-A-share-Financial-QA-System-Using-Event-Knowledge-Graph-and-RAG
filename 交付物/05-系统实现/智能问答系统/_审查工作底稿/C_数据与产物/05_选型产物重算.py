# -*- coding: utf-8 -*-
"""C 线复核 · 项5：从 selection_matrix.jsonl（90 行）重算 selection_decision.json 的每一列。

只读。逐列比对：失败／重试／空答／length 截断／引用越界／date_unverifiable／
dates_beyond_cutoff／正文泄漏／平均·中位·最大时延／finish_reason 分布／token 合计／
最大 completion／max_consecutive_failures／graph_cases／各 rate。

另核：三候选的 Prompt 文本（prompt_sha256）是否完全相同（“只换模型”的成立条件）
——按 decision.prompt_sha256_by_qid 与 assemble.py 现场重算比对（同一套装配）。
核 model_requested 与 model_returned 是否一致。

正对照：把某候选的 dates_beyond_cutoff_count 之和 +1，比对器必须报不一致。
"""
import json
import os
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "问答"))
import assemble as asm  # noqa
import config  # noqa


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def recompute_agg(rows):
    secs = [r["seconds"] for r in rows if r.get("seconds") is not None]
    fr = {}
    for r in rows:
        fr[r.get("finish_reason")] = fr.get(r.get("finish_reason"), 0) + 1
    # max_consecutive_failures：按 qid 顺序的最长连续 ok=False
    order = sorted(rows, key=lambda r: r["qid"])
    mcf = cur = 0
    for r in order:
        if not r.get("ok"):
            cur += 1
            mcf = max(mcf, cur)
        else:
            cur = 0
    n = len(rows)
    return {
        "n_questions": n,
        "expected_cases": n,
        "n_calls": sum((r.get("attempts") and len(r["attempts"])) or 0 for r in rows),
        "n_failures": sum(1 for r in rows if not r.get("ok")),
        "n_retried": sum(1 for r in rows if r.get("retried")),
        "empty_answer_cases": sum(1 for r in rows if r.get("empty_answer")),
        "finish_length_cases": sum(1 for r in rows if r.get("finish_reason") == "length"),
        "finish_stop_cases": sum(1 for r in rows if r.get("finish_reason") == "stop"),
        "citation_out_of_range_total": sum(r.get("citation_out_of_range_count") or 0 for r in rows),
        "citation_out_of_range_cases": sum(1 for r in rows if r.get("citation_out_of_range_count")),
        "date_unverifiable_total": sum(r.get("date_unverifiable_count") or 0 for r in rows),
        "date_unverifiable_cases": sum(1 for r in rows if r.get("date_unverifiable_count")),
        "body_date_unverifiable_total": sum(r.get("body_date_unverifiable_count") or 0 for r in rows),
        "dates_beyond_cutoff_total": sum(r.get("dates_beyond_cutoff_count") or 0 for r in rows),
        "body_graph_marker_leak_cases": sum(1 for r in rows if r.get("body_graph_marker_leak")),
        "body_section_header_leak_cases": sum(1 for r in rows if r.get("body_section_header_leak")),
        "system_graph_section_bad_cases": sum(1 for r in rows if not r.get("system_graph_section_ok")),
        "graph_cases": sum(1 for r in rows if r.get("graph_used")),
        "mean_seconds": round(statistics.mean(secs), 3) if secs else None,
        "median_seconds": round(statistics.median(secs), 3) if secs else None,
        "max_seconds": round(max(secs), 3) if secs else None,
        "total_prompt_tokens": sum(r.get("prompt_tokens") or 0 for r in rows),
        "total_completion_tokens": sum(r.get("completion_tokens") or 0 for r in rows),
        "max_completion_tokens": max((r.get("completion_tokens") or 0) for r in rows),
        "finish_reason_distribution": fr,
        "max_consecutive_failures": mcf,
        "empty_answer_rate": round(sum(1 for r in rows if r.get("empty_answer")) / n, 4),
        "citation_out_of_range_rate": round(sum(1 for r in rows if r.get("citation_out_of_range_count")) / n, 4),
        "date_unverifiable_rate": round(sum(1 for r in rows if r.get("date_unverifiable_count")) / n, 4),
        "graph_section_bad_rate": round(sum(1 for r in rows if not r.get("system_graph_section_ok")) / n, 4),
    }


def main():
    rows = load_jsonl(config.SELECTION_MATRIX_PATH)
    dec = config.read_json(config.SELECTION_DECISION_PATH)
    aggs = dec["aggregates"]

    by = {}
    for r in rows:
        by.setdefault(r["candidate"], []).append(r)
    print("=" * 100)
    print("项5  选型产物重算（矩阵 %d 行；候选 %s）" % (len(rows), sorted(by)))
    print("=" * 100)

    # 候选行数
    print("\n[候选行数] %s（期望每候选 30）" % {k: len(v) for k, v in by.items()})

    # 逐列比对
    COLS = ["n_questions", "expected_cases", "n_calls", "n_failures", "n_retried",
            "empty_answer_cases", "finish_length_cases", "finish_stop_cases",
            "citation_out_of_range_total", "citation_out_of_range_cases",
            "date_unverifiable_total", "date_unverifiable_cases", "body_date_unverifiable_total",
            "dates_beyond_cutoff_total", "body_graph_marker_leak_cases",
            "body_section_header_leak_cases", "system_graph_section_bad_cases", "graph_cases",
            "mean_seconds", "median_seconds", "max_seconds",
            "total_prompt_tokens", "total_completion_tokens", "max_completion_tokens",
            "finish_reason_distribution", "max_consecutive_failures",
            "empty_answer_rate", "citation_out_of_range_rate", "date_unverifiable_rate",
            "graph_section_bad_rate"]
    n_diff = 0
    for cand in sorted(by):
        rec = recompute_agg(by[cand])
        reg = aggs.get(cand, {})
        print("\n--- 候选 %s ---" % cand)
        for col in COLS:
            rv, gv = rec.get(col), reg.get(col)
            if rv != gv:
                n_diff += 1
                print("   DIFF %-32s 重算=%r 登记=%r" % (col, rv, gv))
        # 额外：candidate 字段
        if reg.get("candidate") != cand:
            n_diff += 1
            print("   DIFF candidate 字段 重算=%r 登记=%r" % (cand, reg.get("candidate")))
    print("\n聚合逐列不一致数 = %d" % n_diff)

    # model_requested vs model_returned
    print("\n[model_requested vs model_returned]")
    n_mm = 0
    for cand in sorted(by):
        for r in by[cand]:
            if r.get("model_requested") != r.get("model_returned"):
                n_mm += 1
                print("   不一致 %s %s req=%r ret=%r" % (cand, r["qid"], r.get("model_requested"), r.get("model_returned")))
    print("   不一致数 = %d" % n_mm)

    # 正文泄漏 & 小标题（decision 里的两个 _cases）
    print("\n[正文图谱标记泄漏 / 小标题泄漏 逐候选]")
    for cand in sorted(by):
        leak = sum(1 for r in by[cand] if r.get("body_graph_marker_leak"))
        hdr = sum(1 for r in by[cand] if r.get("body_section_header_leak"))
        print("   %-16s 图谱标记泄漏=%d 小标题泄漏=%d" % (cand, leak, hdr))

    # prompt_sha256：三候选是否同一套（decision 只有一份 by_qid）
    print("\n[Prompt 文本（prompt_sha256）一致性 —— “只换模型”的成立条件]")
    cases = {c["qid"]: c for c in asm.assemble_all()}
    dec_sha = dec.get("prompt_sha256_by_qid") or {}
    n_sha_diff = 0
    for qid, c in cases.items():
        if dec_sha.get(qid) != c["prompt"]["sha256"]:
            n_sha_diff += 1
            print("   DIFF %s 重算=%s 登记=%s" % (qid, c["prompt"]["sha256"], dec_sha.get(qid)))
    print("   装配层重算 vs decision.prompt_sha256_by_qid：不一致 %d / %d" % (n_sha_diff, len(cases)))
    print("   decision 只有一份 prompt_sha256_by_qid（%d 题），即三候选共用同一套 Prompt 文本"
          % len(dec_sha))
    print("   only_thing_changed 登记 = %r" % dec.get("only_thing_changed"))
    # 交叉：矩阵里是否逐候选各自存了 prompt 指纹（无 -> 以 decision 的单份为证）
    has_prompt_field = any("prompt_sha256" in r for r in rows)
    print("   矩阵行内是否含 prompt_sha256 字段 = %s" % has_prompt_field)

    # 裁定规则
    print("\n[裁定规则逐条]")
    rules = dec.get("rules") or {}
    print("   rule_1: %s" % json.dumps(rules.get("rule_1_consecutive_failures"), ensure_ascii=False))
    print("   rule_2: margin=%s triggered=%s" % (rules.get("rule_2_machine_check_worse", {}).get("margin"),
                                                rules.get("rule_2_machine_check_worse", {}).get("triggered")))
    for c in rules.get("rule_2_machine_check_worse", {}).get("comparison", []):
        print("      %s" % json.dumps(c, ensure_ascii=False))
    print("   rule_3: %s" % json.dumps(rules.get("rule_3_mean_latency"), ensure_ascii=False))
    print("   verdict=%r triggered_rules=%r total_calls=%s" % (dec.get("verdict"),
                                                               dec.get("triggered_rules"), dec.get("total_calls")))
    total_calls_re = sum(len(r.get("attempts") or []) for r in rows)
    print("   矩阵重算总调用 = %d（登记 total_calls=%s）" % (total_calls_re, dec.get("total_calls")))

    # 正对照
    print("\n--- 正对照（聚合比对器有效性）---")
    planted = recompute_agg(by["deepseek-flash"])
    planted = dict(planted)
    planted["dates_beyond_cutoff_total"] += 1
    verdict = "一致" if planted["dates_beyond_cutoff_total"] == aggs["deepseek-flash"]["dates_beyond_cutoff_total"] else "不一致"
    print("  植入 dates_beyond_cutoff_total+1 → 结论=%s（必须=不一致）→ %s"
          % (verdict, "PASS" if verdict == "不一致" else "对照失效"))

    return 1 if (n_diff or n_mm or n_sha_diff or total_calls_re != dec.get("total_calls")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
