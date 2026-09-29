# -*- coding: utf-8 -*-
"""逐项复算《22》里可复算的数字（只读）。"""
import io, os, sys, json, re, hashlib, statistics

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"C:\Users\15129\Desktop\毕业设计"
QA = os.path.join(ROOT, r"阶段08-智能问答系统\问答产出")
CIT = re.compile(r"\[证据\s*(\d+)\]")


def jl(name, base=QA):
    with open(os.path.join(base, name), encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def j(name, base=QA):
    return json.load(open(os.path.join(base, name), encoding="utf-8"))


tr = jl("answer_trace.jsonl")
qr = jl("qa_records.jsonl")
rm = j("run_manifest.json")
sd = j("selection_decision.json")
ps = j("prompt_snapshot.json")
im = j("input_manifest.json")
sm = jl("selection_matrix.jsonl")

out = []
P = lambda *a: out.append(" ".join(str(x) for x in a))

P("== 4.3 单候选两轮录制的门禁读数 ==")
P("题数", len(tr))
P("attempts 合计(本次一轮)", sum(len(r["attempts"]) for r in tr))
P("引用总数 sum citation_count =", sum(r["gates"]["citation_count"] for r in tr))
P("citation_out_of_range_count sum =", sum(r["gates"]["citation_out_of_range_count"] for r in tr))
P("date_unverifiable_count sum =", sum(r["gates"]["date_unverifiable_count"] for r in tr))
P("dates_beyond_cutoff_count sum =", sum(r["gates"]["dates_beyond_cutoff_count"] for r in tr))
P("forbidden_hit_count sum =", sum(r["gates"]["forbidden_hit_count"] for r in tr))
P("forbidden_terms_size（各题）", sorted({r["gates"]["forbidden_terms_size"] for r in tr}))
P("graph_section_ok 全真", all(r["gates"]["graph_section_ok"] for r in tr))
P("body_graph_marker_leak 全假", all(not r["gates"]["body_graph_marker_leak"] for r in tr))
P("body_section_header_leak 全假", all(not r["gates"]["body_section_header_leak"] for r in tr))
P("evidence_backlink_ok 全真", all(r["gates"]["evidence_backlink_ok"] for r in tr))
P("time_note_ok 全真", all(r["gates"]["time_note_ok"] for r in tr))
P("passed 全真", all(r["gates"]["passed"] for r in tr))
P("finish_reason 分布", {})
fr = {}
for r in tr:
    for a in r["attempts"]:
        fr[a["finish_reason"]] = fr.get(a["finish_reason"], 0) + 1
P("  attempts[].finish_reason 计数", fr)
P("空正文尝试次数", sum(1 for r in tr for a in r["attempts"] if a.get("empty_body")))
# 引用记法出现次数（答案全文）
marks_full = sum(len(CIT.findall(r["answer_text"])) for r in tr)
marks_body = sum(len(CIT.findall(r["body_text"])) for r in tr)
P("引用记法出现次数（answer_text 全文正则）=", marks_full)
P("引用记法出现次数（body_text 仅回答正文）=", marks_body)
P("「回答」正文长度 min/max =", min(len(r["body_text"]) for r in tr), max(len(r["body_text"]) for r in tr))
P("题集 PE 序号抽查 body 长度:", [(r["qid"], len(r["body_text"])) for r in tr[:3]])

P()
P("== 3.2 token 分账 ==")
fields = ["text_tokens", "path_tokens", "event_triple_tokens", "graph_tokens", "total_tokens"]
for k in fields:
    vals = [r["token_account"][k] for r in tr]
    P(f"{k}: min={min(vals)} max={max(vals)} sum={sum(vals)}")
pc = [r["prompt_chars"] for r in tr]
P(f"prompt_chars: min={min(pc)} max={max(pc)} sum={sum(pc)}")
# 逐题表比对
PERQ = """PE-01 10 3361 120 21 141 3502 2 6396
PE-02 9 2804 377 55 432 3236 1 7130
PE-03 10 2894 90 23 113 3007 2 5682
PE-04 10 3439 129 9 138 3577 2 6257
PE-05 10 2887 210 43 253 3140 2 6358
PE-06 10 2887 210 43 253 3140 2 6404
PE-07 10 3367 181 36 217 3584 2 6639
PE-08 10 3023 183 25 208 3231 2 5981
PE-09 10 2869 210 40 250 3119 2 6335
PE-10 10 2837 118 23 141 2978 2 5600
PE-11 10 3206 60 16 76 3282 2 6129
PE-12 9 3323 91 16 107 3430 1 5887
PE-13 10 3161 265 22 287 3448 2 6759
PE-14 10 3339 171 28 199 3538 2 6681
PE-15 10 3389 150 29 179 3568 2 6537
PE-16 8 2615 560 35 595 3210 0 6906
PE-17 10 3106 151 40 191 3297 2 6165
PE-18 10 2830 225 37 262 3092 2 6387
PE-19 9 2943 591 36 627 3570 1 7741
PE-20 10 3282 181 41 222 3504 2 6555
PE-21 10 3039 155 23 178 3217 2 6304
PE-22 10 3156 416 27 443 3599 2 7044
PE-23 10 3487 60 16 76 3563 2 5956
PE-24 10 3099 120 30 150 3249 2 6215
PE-25 10 3216 271 40 311 3527 2 6571
PE-26 9 2858 440 9 449 3307 1 7414
PE-27 10 3177 106 18 124 3301 2 6519
PE-28 10 2849 150 31 181 3030 2 5998
PE-29 9 3095 231 37 268 3363 1 6675
PE-30 10 3274 264 35 299 3573 2 6953"""
mism = []
for line in PERQ.strip().split("\n"):
    p = line.split()
    qid = p[0]
    row = next(r for r in tr if r["qid"] == qid)
    ta = row["token_account"]
    fg = sum(1 for e in row["evidence"] if e.get("from_graph"))
    got = [len(row["evidence"]), ta["text_tokens"], ta["path_tokens"], ta["event_triple_tokens"],
           ta["graph_tokens"], ta["total_tokens"], fg, row["prompt_chars"]]
    exp = [int(x) for x in p[1:]]
    if got != exp:
        mism.append((qid, exp, got))
P("3.2 逐题表比对：不一致", len(mism))
for m in mism:
    P("  MISMATCH", m)
P("evidence 条数分布", {n: sum(1 for r in tr if len(r['evidence']) == n) for n in (8, 9, 10)})
P("total_tokens 最大值", max(r["token_account"]["total_tokens"] for r in tr))

P()
P("== 3.3 from_graph / depth ==")
tot_fg = sum(1 for r in tr for e in r["evidence"] if e.get("from_graph"))
qs_fg = sum(1 for r in tr if any(e.get("from_graph") for e in r["evidence"]))
P("from_graph 入集总数", tot_fg, "至少1块的题数", qs_fg)
P("PE-16 from_graph", sum(1 for e in next(r for r in tr if r['qid'] == 'PE-16')["evidence"] if e.get("from_graph")))
P("depth 取值集合", sorted({r["graph_payload"]["depth"] for r in tr}))
P("graph_payload 键", sorted(tr[0]["graph_payload"].keys()))
P("checks 六项全真题数", sum(1 for r in tr if all(r["checks"].values())))

P()
P("== 4.2 trace 固定键 ==")
P("TRACE_ROW_FIELDS 键数", len(tr[0].keys()), list(tr[0].keys()))

P()
P("== run_manifest ==")
P("model_calls", json.dumps(rm["model_calls"], ensure_ascii=False))
P("model_output_repeatability", json.dumps(rm["model_output_repeatability"], ensure_ascii=False))
P("assembly_determinism", json.dumps(rm["assembly_determinism"], ensure_ascii=False)[:600])
P("artifacts_sha256 键", sorted(rm["artifacts_sha256"].keys()))
P("reproduce_commands 条数", len(rm["reproduce_commands"]))
for c in rm["reproduce_commands"]:
    P("   -", c)
P("input_fingerprints 条数", len(rm["input_fingerprints"]), type(rm["input_fingerprints"]))
P("gate_summary_from_cycle_1", json.dumps(rm["gate_summary_from_cycle_1"], ensure_ascii=False)[:800])
P("config_snapshot", json.dumps(rm["config_snapshot"], ensure_ascii=False)[:800])

P()
P("== input_manifest ==")
P("items 条数", len(im["items"]))
P("items 路径", [i.get("path") for i in im["items"]])
P("all_ok", im.get("all_ok"))

P()
P("== prompt_snapshot ==")
P("template_sha256", ps["template_sha256"])
P("block_order", ps["block_order"])
P("section_headers", ps["section_headers"])
P("prompt_version", ps["prompt_version"])

P()
P("== 产物 SHA-256 现场重算 ==")
for fn in sorted(os.listdir(QA)):
    if fn.endswith(".jsonl") or fn.endswith(".json"):
        p = os.path.join(QA, fn)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        b = os.path.getsize(p)
        P(f"  {fn}  sha256={h}  bytes={b}")
P("run_manifest 登记的 answer_trace sha256 =", rm["artifacts_sha256"].get("answer_trace"))
P("run_manifest 登记的 prompt_snapshot sha256 =", rm["artifacts_sha256"].get("prompt_snapshot"))

P()
P("== selection_decision ==")
P("total_calls", sd["total_calls"], "verdict", sd["verdict"], "triggered", sd["triggered_rules"])
P("only_thing_changed", sd["only_thing_changed"])
P("rules", json.dumps(sd["rules"], ensure_ascii=False)[:1200])
P("aggregates", json.dumps(sd["aggregates"], ensure_ascii=False)[:2500])
P("moonshot_exclusion", json.dumps(sd["moonshot_exclusion"], ensure_ascii=False)[:800])
P("machine_check_scope", json.dumps(sd["machine_check_scope"], ensure_ascii=False)[:800])
P("frozen_candidate", sd["frozen_candidate"], "control_candidates", sd["control_candidates"])

P()
P("== selection_matrix 现场重算 ==")
cands = sorted({r["candidate"] for r in sm})
P("候选", cands, "总行数", len(sm))
for c in cands:
    rows = [r for r in sm if r["candidate"] == c]
    secs = [r["seconds"] for r in rows if r.get("ok")]
    P(f"  {c}: 行={len(rows)} 失败={sum(1 for r in rows if not r.get('ok'))} "
      f"空答案={sum(1 for r in rows if r.get('empty_answer'))} "
      f"citzero={sum(1 for r in rows if r.get('citation_out_of_range_count'))} "
      f"datzero={sum(1 for r in rows if r.get('date_unverifiable_count'))} "
      f"beyond={sum(r.get('dates_beyond_cutoff_count') or 0 for r in rows)} "
      f"leak={sum(1 for r in rows if r.get('body_graph_marker_leak'))}")
    P(f"     平均时延={statistics.mean(secs):.3f} 中位={statistics.median(secs):.3f} 最大={max(secs):.3f}")
    P(f"     completion_tokens max={max(r['completion_tokens'] for r in rows if r.get('completion_tokens') is not None)}")
    P(f"     total_prompt_tokens={sum(r['prompt_tokens'] for r in rows if r.get('prompt_tokens'))}")
    P(f"     total_completion_tokens={sum(r['completion_tokens'] for r in rows if r.get('completion_tokens'))}")

P()
P("== 记录层 evidence_type 计数 ==")
cnt = {}
for r in qr:
    for e in r["answer_evidence"]:
        cnt[e["evidence_type"]] = cnt.get(e["evidence_type"], 0) + 1
P("evidence_type 计数", cnt, "总条数", sum(cnt.values()))
P("qa_records session_id 集合", sorted({r['question']['session_id'] for r in qr}))
P("question_id 前3", [r['question']['question_id'] for r in qr[:3]])

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "recompute_22.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("\n".join(out))
