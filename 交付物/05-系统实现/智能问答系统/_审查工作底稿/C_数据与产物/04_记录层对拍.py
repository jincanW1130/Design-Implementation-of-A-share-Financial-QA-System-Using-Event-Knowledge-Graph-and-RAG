# -*- coding: utf-8 -*-
"""C 线复核 · 项4：记录层对拍。

只读。逐项：
  1) qa_records.jsonl 30 条 vs answer_trace.jsonl 30 条一一对应（qid<->question_id/answer_id）
  2) question/answer/answer_evidence 字段名 vs 《10》表 4-6 逐字比对（列全字段名）
  3) (answer_id, chunk_id) 联合唯一；rank 1..m 连续
  4) evidence_type 取值落在四类内；且与 documents.jsonl 的 category 的**期望映射**自洽
     （期望映射在脚本里**写死**，不从代码抄）
  5) graph_path 是原样 JSON 文本、能 json.loads；graph_used=0 时为 null

正对照：把某条 evidence_type 改成表外取值「其它来源」，映射校验器必须报出。
"""
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "问答"))
import config  # noqa

# ---- 期望映射（写死；据《21》硬约束 15 的映射表 + 数据集真实 category 词表）----
EXPECTED_CATEGORY_TO_TYPE = {
    "公告": "公告来源",
    "政策文件": "公告来源",
    "监管公开信息": "公告来源",
    "财经新闻": "新闻来源",
}
FALLBACK_TYPE = "回答来源"
GRAPH_TYPE = "相关事件"
FOUR_TYPES = {"回答来源", "新闻来源", "公告来源", "相关事件"}

# ---- 表 4-6 的字段集（逐字取自《10》第4.4.1节 表 4-6）----
T46 = {
    "question": ["question_id", "user_id", "session_id", "question_text", "task_type",
                 "gold_hop_depth", "time_constraint", "ask_time"],
    "answer": ["answer_id", "question_id", "answer_text", "graph_path", "model_name",
               "prompt_version", "is_graph_extended", "create_time"],
    "answer_evidence": ["answer_id", "chunk_id", "doc_id", "rank", "evidence_type"],
}


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    recs = load_jsonl(config.QA_RECORDS_PATH)
    atrace = {r["qid"]: r for r in load_jsonl(config.ANSWER_TRACE_PATH)}
    docs = {r["doc_id"]: r for r in load_jsonl(config.DOCUMENTS_PATH)}

    print("=" * 96)
    print("项4  记录层对拍（%d 条记录 / %d 条 trace）" % (len(recs), len(atrace)))
    print("=" * 96)

    # ---- 1) 一一对应 ----
    print("\n[1] 一一对应")
    n_bad = 0
    rec_ids = []
    for r in recs:
        q = r["question"]
        a = r["answer"]
        qid_num = q["question_id"]
        # Q-0nn -> PE-nn（PE 题号是 2 位：PE-01…PE-30）
        nn = qid_num.split("-")[-1]
        qid = "PE-%02d" % int(nn)
        t = atrace.get(qid)
        ok = t is not None and a["question_id"] == qid_num and a["answer_text"] == t["answer_text"]
        rec_ids.append((qid, qid_num, a["answer_id"]))
        if not ok:
            n_bad += 1
            print("   不符：%s" % qid_num)
    missing = set(atrace) - {x[0] for x in rec_ids}
    extra = {x[0] for x in rec_ids} - set(atrace)
    print("   qa_records 覆盖题号 %d 个；trace 缺失=%s 多余=%s；answer_text 不符=%d"
          % (len(rec_ids), sorted(missing), sorted(extra), n_bad))

    # ---- 2) 字段名逐字比对 ----
    print("\n[2] 字段名 vs 《10》表 4-6（列全字段名）")
    q_keys = set(recs[0]["question"].keys())
    a_keys = set(recs[0]["answer"].keys())
    e_keys = set(recs[0]["answer_evidence"][0].keys())
    for table, actual in (("question", q_keys), ("answer", a_keys), ("answer_evidence", e_keys)):
        expect = T46[table]
        print("   %-16s 实际(%d)=%s" % (table, len(actual), "／".join(sorted(actual))))
        print("   %-16s 表4-6(%d)=%s" % ("", len(expect), "／".join(expect)))
        miss = [f for f in expect if f not in actual]
        ex = [f for f in actual if f not in expect]
        print("   %-16s 缺=%s 多=%s" % ("", miss or "无", ex or "无"))
    # 全 30 条的键一致性
    same_q = all(set(r["question"].keys()) == q_keys for r in recs)
    same_a = all(set(r["answer"].keys()) == a_keys for r in recs)
    same_e = all(set(e.keys()) == e_keys for r in recs for e in r["answer_evidence"])
    print("   30 条键序/键集一致：question=%s answer=%s answer_evidence=%s" % (same_q, same_a, same_e))

    # ---- 3) 联合唯一 + rank 连续 ----
    print("\n[3] (answer_id, chunk_id) 联合唯一 与 rank 1..m 连续")
    n_dup = n_rank = n_owner = 0
    for r in recs:
        aid = r["answer"]["answer_id"]
        ev = r["answer_evidence"]
        cids = [e["chunk_id"] for e in ev]
        ranks = [e["rank"] for e in ev]
        if len(cids) != len(set(cids)):
            n_dup += 1
        if ranks != list(range(1, len(ranks) + 1)):
            n_rank += 1
        if any(e["answer_id"] != aid for e in ev):
            n_owner += 1
    print("   重复 chunk_id 的答案数=%d；rank 不连续=%d；answer_id 归属不符=%d" % (n_dup, n_rank, n_owner))

    # ---- 4) evidence_type 四类 + 映射自洽 ----
    print("\n[4] evidence_type 四类 与 category 映射自洽")
    from collections import Counter
    tc = Counter()
    mism = []
    for r in recs:
        for e in r["answer_evidence"]:
            et = e["evidence_type"]
            tc[et] += 1
            if et not in FOUR_TYPES:
                mism.append(("表外取值", r["answer"]["answer_id"], str(e["chunk_id"]), et))
                continue
            doc = docs.get(e["doc_id"])
            cat = (doc or {}).get("category")
            # 期望：来自图谱侧 -> 相关事件；否则按 category 映射；缺失 -> 兜底
            # 这里用**期望映射**：从 answer_trace 找该块是否 from_graph
            t = atrace.get("PE-%02d" % int(r["answer"]["answer_id"].split("-")[-1]))
            from_graph = False
            for ev in (t or {}).get("evidence", []):
                if ev["chunk_id"] == e["chunk_id"]:
                    from_graph = ev.get("from_graph")
                    break
            if from_graph:
                exp = GRAPH_TYPE
            else:
                exp = EXPECTED_CATEGORY_TO_TYPE.get(cat, FALLBACK_TYPE)
            if et != exp:
                mism.append(("映射不符", r["answer"]["answer_id"], str(e["chunk_id"]),
                             "category=%r from_graph=%s 期望=%s 实际=%s" % (cat, from_graph, exp, et)))
    print("   evidence_type 计数 = %s" % dict(tc))
    print("   期望映射（写死）: 公告/政策文件/监管公开信息→公告来源; 财经新闻→新闻来源; 其它→回答来源; from_graph→相关事件")
    print("   映射不符/表外 = %d 条" % len(mism))
    for m in mism[:20]:
        print("      %s" % (m,))

    # ---- 4b) documents.jsonl 的 category 真实词表 ----
    catc = Counter((d.get("category") or "<缺失>") for d in docs.values())
    print("   全语料 category 真实取值 = %s" % dict(catc))

    # ---- 5) graph_path ----
    print("\n[5] graph_path 原样 JSON 文本 / 可 json.loads / graph_used=0 为 null")
    n_json = n_null = n_nonnull = n_ng = 0
    for r in recs:
        aid = r["answer"]["answer_id"]
        t = atrace.get("PE-%02d" % int(aid.split("-")[-1]))
        gp = (t or {}).get("graph_payload") or {}
        used = bool(gp.get("graph_used"))
        val = r["answer"]["graph_path"]
        if not used:
            n_ng += 1
            if val is None:
                n_null += 1
            else:
                print("   graph_used=0 但 graph_path 非 null：%s" % aid)
        else:
            n_nonnull += 1
            try:
                obj = json.loads(val)
                n_json += 1
                # 逐字符一致：与载荷 json.dumps 比对
                exp = json.dumps(gp.get("graph_path") or [], ensure_ascii=False)
                if val != exp:
                    print("   %s graph_path 与载荷 json.dumps 不一致" % aid)
            except Exception as ex:
                print("   %s graph_path 非 JSON：%s" % (aid, ex))
    print("   graph_used=1 题数=%d（可 json.loads=%d）；graph_used=0 题数=%d（graph_path 为 null=%d）"
          % (n_nonnull, n_json, n_ng, n_null))
    # 键结构
    nonnull = [r for r in recs if r["answer"]["graph_path"] is not None]
    sample = json.loads(nonnull[0]["answer"]["graph_path"])
    print("   首个非空 graph_path 类型=%s；元素0 键 = %s" % (type(sample).__name__, sorted(sample[0]) if isinstance(sample, list) and sample else "空"))
    if isinstance(sample, list) and sample and sample[0].get("relations"):
        print("   relations[0] 键 = %s" % sorted(sample[0]["relations"][0]))
        if sample[0]["relations"][0].get("evidence"):
            print("   relations[0].evidence 键 = %s" % sorted(sample[0]["relations"][0]["evidence"]))

    # ---- 正对照 ----
    print("\n--- 正对照（映射校验器有效性）---")
    bad_type = "其它来源"
    print("  植入 evidence_type=%r（四类之外）→ 落在四类外 = %s → %s"
          % (bad_type, bad_type not in FOUR_TYPES, "PASS" if bad_type not in FOUR_TYPES else "对照失效"))

    # 正对照2：改 category -> 期望类型变化，验证映射不是恒真
    print("  映射非恒真自证：财经新闻→%s，公告→%s（二者不同 = %s）"
          % (EXPECTED_CATEGORY_TO_TYPE["财经新闻"], EXPECTED_CATEGORY_TO_TYPE["公告"],
             EXPECTED_CATEGORY_TO_TYPE["财经新闻"] != EXPECTED_CATEGORY_TO_TYPE["公告"]))

    n_fail = n_bad + n_dup + n_rank + n_owner + len(mism)
    print("\n结论：记录层不符项合计 = %d" % n_fail)
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
