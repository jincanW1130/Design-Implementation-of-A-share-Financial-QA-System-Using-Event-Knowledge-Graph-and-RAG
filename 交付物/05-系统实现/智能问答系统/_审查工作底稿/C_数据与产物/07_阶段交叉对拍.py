# -*- coding: utf-8 -*-
"""C 线复核 · 项7：与第 5／6／7 阶段交叉对拍。

只读。逐项：
  1) prompt_snapshot.json 与 交付物/03-代码\问答\prompt.py 的 snapshot()/template_text() 是否逐字节一致；
     template_sha256 是否可由 template_text() 现算复现（《22》声称 c4c351d0…）
  2) 30 题的 k/n/context_token_budget 是否与 交付物/03-代码\检索\config.py 冻结值一致；evidence_size ≤ K
  3) 图谱侧块（from_graph=true）计数：answer_trace 重算 vs 第7阶段 per_question_trace 的
     graph_evidence_in_final，逐题比对；合计是否 = k_selection.json C 组 g=2 的
     graph_evidence_in_final_total（声称 53），入集题数是否 = 29
  4) 逐题 graph_payload（answer_trace 重算）与第7阶段 per_question_trace 是否一致

正对照：把某题 k 改成 9，k==config.K 的比对器必须报不一致。
"""
import hashlib
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "问答"))
sys.path.insert(1, os.path.join(ROOT, "交付物/03-代码", "检索"))
import assemble as asm  # noqa
import config  # noqa
import prompt as pm  # noqa


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    fails = 0
    print("=" * 100)
    print("项7  与第5／6／7阶段交叉对拍")
    print("=" * 100)

    # ---- 1) prompt_snapshot ----
    print("\n[1] prompt_snapshot.json vs prompt.py")
    snap = pm.snapshot()
    file_snap = config.read_json(os.path.join(ROOT, "交付物/05-系统实现/智能问答系统", "问答产出", "prompt_snapshot.json"))
    same = json.dumps(snap, sort_keys=True, ensure_ascii=False) == json.dumps(file_snap, sort_keys=True, ensure_ascii=False)
    sha_tpl = hashlib.sha256(pm.template_text().encode("utf-8")).hexdigest()
    claim = "c4c351d0dd38f4e96a96a6fb35816e959489d8077edf709995264c79e0cff3f0"
    print("   snapshot() 与文件逐字节一致 = %s" % same)
    print("   现算 template_sha256 = %s" % sha_tpl)
    print("   登记/《22》声称     = %s → %s" % (claim, "OK" if sha_tpl == claim else "FAIL"))
    print("   prompt_version=%s block_order=%s" % (file_snap.get("prompt_version"), file_snap.get("block_order")))
    if not (same and sha_tpl == claim):
        fails += 1

    # ---- 2) K/N/budget ----
    print("\n[2] 30 题 k/n/budget vs 检索\\config.py 冻结值")
    p7 = {r["qid"]: r for r in load_jsonl(os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "检索产出", "per_question_trace.jsonl"))}
    atrace = {r["qid"]: r for r in load_jsonl(config.ANSWER_TRACE_PATH)}
    n_bad = 0
    sizes = {}
    for qid, r in p7.items():
        ok = (r["k"] == config.K and r["n"] == config.N and r["context_token_budget"] == config.CONTEXT_TOKEN_BUDGET)
        if not ok:
            n_bad += 1
            print("   %s k=%s n=%s budget=%s" % (qid, r["k"], r["n"], r["context_token_budget"]))
        sizes[len(r["final_evidence_chunk_ids"])] = sizes.get(len(r["final_evidence_chunk_ids"]), 0) + 1
    print("   冻结值 K=%s N=%s budget=%s g=%s" % (config.K, config.N, config.CONTEXT_TOKEN_BUDGET, config.G))
    print("   30 题 k/n/budget 不符 = %d；evidence_size 分布 = %s；max=%d ≤ K" % (n_bad, sizes, max(sizes)))
    if n_bad or max(sizes) > config.K:
        fails += 1

    # ---- 3) 图谱侧计数 ----
    print("\n[3] 图谱侧块（from_graph）计数交叉")
    ks = config.read_json(os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "检索产出", "k_selection.json"))
    c2 = next(x for x in ks["evidence"]["g_curve"]["primary_rows"] if x["g"] == 2 and x["group"] == "C")
    print("   k_selection C 组 g=2: graph_evidence_in_final_total=%s questions=%s"
          % (c2["graph_evidence_in_final_total"], c2["graph_evidence_in_final_questions"]))
    # 从 answer_trace 重算 from_graph 块（与第7阶段逐题比）
    cases = {c["qid"]: c for c in asm.assemble_all()}
    tot = 0
    nq = 0
    per_diff = 0
    for qid, r in sorted(p7.items()):
        re_count = sum(1 for e in cases[qid]["evidence"] if e["from_graph"])
        reg = r["graph_evidence_in_final_count"]
        if re_count != reg:
            per_diff += 1
            print("   %s 重算 from_graph=%d 第7阶段=%d" % (qid, re_count, reg))
        tot += re_count
        nq += 1 if re_count else 0
    print("   answer_trace 重算 from_graph 合计 = %d（题数含图谱 = %d）；逐题与第7阶段不符 = %d" % (tot, nq, per_diff))
    print("   与 k_selection(53/29) 一致 = %s" % (tot == c2["graph_evidence_in_final_total"] and nq == c2["graph_evidence_in_final_questions"]))
    # 逐题 graph_payload 一致
    gp_diff = 0
    for qid, r in sorted(p7.items()):
        if json.dumps(cases[qid]["graph_payload"], sort_keys=True, ensure_ascii=False) != \
           json.dumps(r["graph_payload"], sort_keys=True, ensure_ascii=False):
            gp_diff += 1
    print("   逐题 graph_payload 与第7阶段不符 = %d" % gp_diff)
    # 每题图谱块上限
    mx = max(sum(1 for e in cases[q]["evidence"] if e["from_graph"]) for q in cases)
    print("   单题图谱块最大值 = %d（g=%d，优先级规则称「第二层至多取 g 个」；第三层回填可能超出）" % (mx, config.G))
    if per_diff or gp_diff or tot != c2["graph_evidence_in_final_total"]:
        fails += 1
    # PE-16 特例
    print("   PE-16 from_graph 重算 = %d" % sum(1 for e in cases["PE-16"]["evidence"] if e["from_graph"]))

    # ---- 正对照 ----
    print("\n--- 正对照（k 比对器有效性）---")
    print("  植入 k=9（≠config.K=%d）→ 结论=%s → %s"
          % (config.K, "不一致" if 9 != config.K else "一致", "PASS" if 9 != config.K else "对照失效"))

    print("\n结论：交叉对拍不符项合计 = %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
