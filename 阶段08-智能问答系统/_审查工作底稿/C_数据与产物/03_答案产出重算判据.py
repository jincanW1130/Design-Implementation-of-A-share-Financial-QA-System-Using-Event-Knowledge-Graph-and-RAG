# -*- coding: utf-8 -*-
"""C 线复核 · 项3：用 代码\问答\rules.py 的判据对 answer_trace.jsonl 的 30 条答案重新判一遍。

**不读产出里的 gates 作为输入**：重新从 answer_trace.jsonl 取 body_text／answer_text，
经 assemble 重建 case（证据集合／图谱载荷／时间口径），调 rules.py ＋ prompt.split/NO_GRAPH_MARKER
重算每一项判据，再与产出里登记的 gates 逐题逐字段比对。

覆盖：
  * 引用编号 [证据n] 是否越界（n<1 或 n>m）
  * 日期是否「来源可核」（date_unverifiable）＋ dates_beyond_cutoff（只统计）
  * 模型正文是否出现「本次回答未使用图谱扩展」或系统小标题
  * 禁词是否命中
  * 图谱段与 graph_used 三方一致

正对照：把 PE-01 的正文里 [证据1] 改成 [证据99]，越界判据必须报 1。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "代码", "问答"))
import assemble as asm  # noqa
import config  # noqa
import prompt as prompt_mod  # noqa
import rules  # noqa


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def recompute(case, body_text, answer_text):
    """独立重算（不依赖答案产出的 gates）。字段名与 answer.gate() 对齐以便逐字段比对。"""
    m = len(case["evidence"])
    graph_used = bool(case["graph_payload"]["graph_used"])
    cg = rules.citation_gate(body_text, m)
    dg = rules.date_gate(answer_text, case)
    fg = rules.forbidden_gate(answer_text)
    secs = prompt_mod.split_answer_sections(answer_text)
    gsec = (secs.get(prompt_mod.ANSWER_SECTIONS[2]) or "")
    has_path = bool(gsec.strip()) and (prompt_mod.NO_GRAPH_MARKER not in gsec)
    graph_section_ok = has_path if graph_used else (gsec.strip() == prompt_mod.NO_GRAPH_MARKER)
    leak = prompt_mod.NO_GRAPH_MARKER in (body_text or "")
    header_leak = any(t in (body_text or "") for t in prompt_mod.ANSWER_SECTIONS[1:])
    return {
        "citation_marks": cg["citation_marks"],
        "citation_count": cg["citation_count"],
        "citation_out_of_range": cg["citation_out_of_range"],
        "citation_out_of_range_count": cg["citation_out_of_range_count"],
        "dates_mentioned": dg["dates_mentioned"],
        "date_unverifiable": dg["date_unverifiable"],
        "date_unverifiable_count": dg["date_unverifiable_count"],
        "dates_beyond_cutoff": dg["dates_beyond_cutoff"],
        "dates_beyond_cutoff_count": dg["dates_beyond_cutoff_count"],
        "graph_used": graph_used,
        "is_graph_extended": 1 if graph_used else 0,
        "graph_section_ok": bool(graph_section_ok),
        "graph_section_has_path": bool(has_path),
        "graph_section_is_marker": gsec.strip() == prompt_mod.NO_GRAPH_MARKER,
        "body_graph_marker_leak": bool(leak),
        "body_section_header_leak": bool(header_leak),
        "forbidden_hits": fg["forbidden_hits"],
        "forbidden_hit_count": fg["forbidden_hit_count"],
        "forbidden_terms_size": fg["forbidden_terms_size"],
    }


CHECK_FIELDS = ["citation_marks", "citation_count", "citation_out_of_range",
                "citation_out_of_range_count", "dates_mentioned", "date_unverifiable",
                "date_unverifiable_count", "dates_beyond_cutoff", "dates_beyond_cutoff_count",
                "graph_used", "is_graph_extended", "graph_section_ok", "graph_section_has_path",
                "graph_section_is_marker", "body_graph_marker_leak", "body_section_header_leak",
                "forbidden_hits", "forbidden_hit_count", "forbidden_terms_size"]


def main():
    cases = {c["qid"]: c for c in asm.assemble_all()}
    rows = load_jsonl(config.ANSWER_TRACE_PATH)

    print("=" * 100)
    print("项3  答案门禁重算（%d 条）" % len(rows))
    print("=" * 100)
    print("%-7s %-5s %-6s %-6s %-7s %-6s %-6s %-6s %-6s %-6s"
          % ("qid", "越界", "日期不可核", "未来日期", "禁词", "图谱段", "标记泄漏", "小标题", "引用数", "逐字段"))
    n_mismatch = 0
    mismatch_detail = []
    sum_cit = sum_oob = sum_du = sum_bc = sum_fb = 0
    for r in rows:
        qid = r["qid"]
        case = cases[qid]
        rec = recompute(case, r["body_text"], r["answer_text"])
        reg = r["gates"]
        diffs = []
        for f in CHECK_FIELDS:
            rv, gv = rec.get(f), reg.get(f)
            if rv != gv:
                diffs.append((f, rv, gv))
        # 逐字段（含 passed／failures 的整体一致性由上面字段推出，另单列）
        sum_cit += rec["citation_count"]
        sum_oob += rec["citation_out_of_range_count"]
        sum_du += rec["date_unverifiable_count"]
        sum_bc += rec["dates_beyond_cutoff_count"]
        sum_fb += rec["forbidden_hit_count"]
        flag = "OK" if not diffs else "DIFF"
        if diffs:
            n_mismatch += 1
            mismatch_detail.append((qid, diffs))
        print("%-7s %-5d %-6d %-7d %-7d %-6s %-7s %-7s %-7d %-6s"
              % (qid, rec["citation_out_of_range_count"], rec["date_unverifiable_count"],
                 rec["dates_beyond_cutoff_count"], rec["forbidden_hit_count"],
                 "OK" if rec["graph_section_ok"] else "BAD",
                 "有" if rec["body_graph_marker_leak"] else "无",
                 "有" if rec["body_section_header_leak"] else "无",
                 rec["citation_count"], flag))
        for f, rv, gv in diffs:
            print("      DIFF %s: 重算=%r 登记=%r" % (f, rv, gv))

    print("-" * 100)
    print("重算合计：引用数=%d 越界=%d date_unverifiable=%d dates_beyond_cutoff=%d 禁词=%d"
          % (sum_cit, sum_oob, sum_du, sum_bc, sum_fb))
    print("逐字段不一致题数 = %d" % n_mismatch)

    # passed 一致性与 failures
    print("\n--- passed／failures 重算 ---")
    from collections import Counter
    passed_re = 0
    for r in rows:
        g = r["gates"]
        passed_re += 1 if g.get("passed") else 0
    print("产出登记 passed=True 题数 = %d / %d" % (passed_re, len(rows)))

    # 正对照：把 PE-01 正文 [证据1] 改成 [证据99]
    print("\n--- 正对照（越界比对器有效性）---")
    r0 = rows[0]
    bad_body = (r0["body_text"] or "").replace("[证据1]", "[证据99]", 1)
    if "[证据99]" not in bad_body:
        # 若无 [证据1]，直接追加一个越界引用
        bad_body = (r0["body_text"] or "") + " 见 [证据99]。"
    cg = rules.citation_gate(bad_body, len(cases[r0["qid"]]["evidence"]))
    print("  植入 [证据99]（m=%d）后 citation_out_of_range = %s → %s"
          % (len(cases[r0["qid"]]["evidence"]), cg["citation_out_of_range"],
             "PASS" if cg["citation_out_of_range"] else "对照失效"))

    return 1 if n_mismatch else 0


if __name__ == "__main__":
    raise SystemExit(main())
