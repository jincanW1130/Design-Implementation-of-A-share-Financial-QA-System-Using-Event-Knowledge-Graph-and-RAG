# -*- coding: utf-8 -*-
"""勘察 问答产出 下的文件结构（只读）。"""
import io, os, sys, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"C:\Users\15129\Desktop\毕业设计"
QA = os.path.join(ROOT, r"交付物/05-系统实现/智能问答系统\问答产出")


def jl(name):
    rows = []
    with open(os.path.join(QA, name), encoding="utf-8") as f:
        for l in f:
            if l.strip():
                rows.append(json.loads(l))
    return rows


def j(name):
    return json.load(open(os.path.join(QA, name), encoding="utf-8"))


print("### answer_trace.jsonl")
rows = jl("answer_trace.jsonl")
print("行数", len(rows))
print("顶层键", list(rows[0].keys()))
print("keys 子键", list(rows[0].get("checks", {}).keys()), list(rows[0].get("gates", {}).keys()))
print("token_account 键", list(rows[0].get("token_account", {}).keys()))
print("第1行完整（截断）:")
print(json.dumps(rows[0], ensure_ascii=False)[:3000])
print()
print("### qa_records.jsonl")
qr = jl("qa_records.jsonl")
print("行数", len(qr), "顶层键", list(qr[0].keys()))
print("question 键", list(qr[0]["question"].keys()))
print("answer 键", list(qr[0]["answer"].keys()))
print("answer_evidence[0]", qr[0]["answer_evidence"][0])
print("evidence 条数逐题", [len(r["answer_evidence"]) for r in qr])
print()
for nm in ["run_manifest.json", "selection_decision.json", "prompt_snapshot.json", "input_manifest.json"]:
    try:
        d = j(nm)
        print("###", nm, "顶层键", list(d.keys()))
    except Exception as ex:
        print("###", nm, "ERR", ex)
sm = jl("selection_matrix.jsonl")
print("### selection_matrix.jsonl 行数", len(sm), "顶层键", list(sm[0].keys()))
print("候选集合", sorted({r.get("candidate") or r.get("model") for r in sm}))
