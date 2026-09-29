# -*- coding: utf-8 -*-
"""C 线复核 · 项2：装配层重算（用 代码\问答\assemble.py 独立重算 30 题）。

只读。逐项：
  1) 证据顺序 vs per_question_trace.jsonl 的 final_evidence_chunk_ids 逐位一致
  2) token_account.total_tokens <= 3600，报范围
  3) text_tokens == 逐条 token_count 之和（并与 chunks.jsonl 的字段值核）
  4) 同一输入两次装配的 Prompt SHA-256 相同
  5) 重算的 prompt_sha256 与该题 answer_trace.jsonl 登记值比对

正对照：把 PE-01 的证据顺序颠倒后重新装配，必须与 trace 不一致（证明顺序比对器有效）。
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


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    trace = asm.load_trace()
    chunks = asm.load_chunks()
    docs = asm.load_documents()
    questions = asm.load_questions()
    meta = asm.load_dataset_meta()

    cases = asm.assemble_all(trace, chunks, docs, questions, meta)
    # 第二次装配（独立再跑一遍）
    cases2 = asm.assemble_all(asm.load_trace(), chunks, docs, questions, meta)

    atrace = {r["qid"]: r for r in load_jsonl(config.ANSWER_TRACE_PATH)}

    print("K=%s N=%s 预算=%s g=%s （导入自 代码\\检索\\config.py）"
          % (config.K, config.N, config.CONTEXT_TOKEN_BUDGET, config.G))
    print("=" * 110)
    print("%-7s %-4s %-9s %-10s %-13s %-9s %-7s %-6s %-6s %-6s"
          % ("qid", "证据", "总token", "text复核", "顺序", "两次SHA", "traceSHA", "图谱", "预算", "结论"))
    tot = []
    n_order_bad = n_sha_bad = n_sha2_bad = n_text_bad = n_budget_bad = n_trace_bad = 0
    for c, c2 in zip(cases, cases2):
        qid = c["qid"]
        trow = next(r for r in trace if r["qid"] == qid)
        # 1) 顺序
        order_ok = [e["chunk_id"] for e in c["evidence"]] == list(trow["final_evidence_chunk_ids"])
        # 2) 预算
        total = c["token_account"]["total_tokens"]
        tot.append(total)
        budget_ok = total <= 3600
        # 3) text_tokens 复核
        sum_tc = sum(e["token_count"] for e in c["evidence"])
        text_ok = (c["token_account"]["text_tokens"] == sum_tc)
        # 3b) token_count 与 chunks.jsonl 字段一致（未重算）
        tc_field_ok = all(e["token_count"] == chunks[e["chunk_id"]]["token_count"] for e in c["evidence"])
        # 4) 两次装配 SHA
        sha2_ok = c["prompt"]["sha256"] == c2["prompt"]["sha256"]
        # 5) 与 answer_trace 登记值比对
        reg = atrace.get(qid, {}).get("prompt_sha256")
        trace_ok = (reg == c["prompt"]["sha256"])
        n_order_bad += 0 if order_ok else 1
        n_budget_bad += 0 if budget_ok else 1
        n_text_bad += 0 if (text_ok and tc_field_ok) else 1
        n_sha2_bad += 0 if sha2_ok else 1
        n_trace_bad += 0 if trace_ok else 1
        print("%-7s %-4d %-9d %-10s %-13s %-9s %-7s %-6s %-6s %-6s"
              % (qid, len(c["evidence"]), total,
                 "OK" if (text_ok and tc_field_ok) else "BAD",
                 "OK" if order_ok else "BAD",
                 "OK" if sha2_ok else "BAD",
                 "OK" if trace_ok else ("BAD:%s" % str(reg)[:6]),
                 "是" if c["graph_payload"]["graph_used"] else "否",
                 "OK" if budget_ok else "超限",
                 "OK" if (order_ok and budget_ok and text_ok and sha2_ok and trace_ok) else "FAIL"))
        if not trace_ok:
            print("      重算=%s\n      登记=%s" % (c["prompt"]["sha256"], reg))

    print("-" * 110)
    print("total_tokens 范围 = %d ～ %d（预算 3600）" % (min(tot), max(tot)))
    print("text_tokens 复核不符题数 = %d；顺序不符 = %d；两次装配不符 = %d；trace 登记不符 = %d；超预算 = %d"
          % (n_text_bad, n_order_bad, n_sha2_bad, n_trace_bad, n_budget_bad))
    gg = sum(1 for c in cases for e in c["evidence"] if e["from_graph"])
    print("from_graph 块合计 = %d" % gg)
    print("证据条数分布 = %s" % json.dumps(
        {k: sum(1 for c in cases if len(c["evidence"]) == k) for k in sorted({len(c["evidence"]) for c in cases})},
        ensure_ascii=False))

    # 正对照：颠倒 PE-01 证据顺序，必与 trace 不一致
    print("\n--- 正对照（顺序比对器有效性）---")
    bad = json.loads(json.dumps(trace[0]))
    bad["final_evidence_chunk_ids"] = list(reversed(bad["final_evidence_chunk_ids"]))
    try:
        cb = asm.assemble_case(bad, chunks, docs, questions.get(bad["qid"]), meta)
        order_ok = [e["chunk_id"] for e in cb["evidence"]] == list(trace[0]["final_evidence_chunk_ids"])
        print("  颠倒 PE-01 顺序后：order_matches_trace = %s（必须 False）→ %s"
              % (order_ok, "PASS" if not order_ok else "对照失效"))
    except SystemExit as e:
        print("  颠倒 PE-01 顺序后装配抛错（判据生效）：%s → PASS" % str(e)[:80])

    fails = n_text_bad + n_order_bad + n_sha2_bad + n_trace_bad + n_budget_bad
    print("\n结论：不一致项合计 = %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
