# -*- coding: utf-8 -*-
import io, os, sys, json, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"C:\Users\15129\Desktop\毕业设计"
QA = os.path.join(ROOT, r"阶段08-智能问答系统\问答产出")
jl = lambda n: [json.loads(l) for l in open(os.path.join(QA, n), encoding="utf-8") if l.strip()]
j = lambda n: json.load(open(os.path.join(QA, n), encoding="utf-8"))
tr = jl("answer_trace.jsonl")
sm = jl("selection_matrix.jsonl")

print("### body 长度逐题（body_text / attempts[0].body_chars / answer_text 回答段）")
import re
for r in tr:
    hui = r["answer_text"].split("【证据来源】")[0]
    print(r["qid"], len(r["body_text"]), r["attempts"][0].get("body_chars"), len(hui))

L = [len(r["body_text"]) for r in tr]
print("body_text  min/max", min(L), max(L))
print("body_chars min/max", min(r["attempts"][0]["body_chars"] for r in tr), max(r["attempts"][0]["body_chars"] for r in tr))
print("回答段 len min/max", min(len(r["answer_text"].split("【证据来源】")[0]) for r in tr), max(len(r["answer_text"].split("【证据来源】")[0]) for r in tr))
print("answer_text 全文 min/max", min(len(r["answer_text"]) for r in tr), max(len(r["answer_text"]) for r in tr))

print()
print("### 中位时延：deepseek-flash 秒数排序")
s = sorted(r["seconds"] for r in sm if r["candidate"] == "deepseek-flash")
print(s)
print("statistics.median", statistics.median(s), "s[14],s[15]", s[14], s[15], "avg", (s[14]+s[15])/2)
print("s[15]=", s[15], "  index15(0based) ")
# 也看 attempts 展开
print("### v4-pro / glm 中位")
for c in ("deepseek-v4-pro", "glm-5.3-flash"):
    s2 = sorted(r["seconds"] for r in sm if r["candidate"] == c)
    print(c, "median", statistics.median(s2), "s14,s15", s2[14], s2[15], "avg", (s2[14]+s2[15])/2)

print()
print("### run_manifest input_fingerprints 结构")
rm = j("run_manifest.json")
print(json.dumps(rm["input_fingerprints"], ensure_ascii=False, indent=1)[:3000])

print()
print("### input_manifest items")
im = j("input_manifest.json")
print(json.dumps(im["items"], ensure_ascii=False, indent=1)[:3000])
