# -*- coding: utf-8 -*-
"""C 线：题集文档与 questions.jsonl 的字段／分布一致性"""
import io, json, os, re
from collections import Counter

ROOT = r"C:\Users\15129\Desktop\毕业设计"
QDIR = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

qs = load_jsonl(os.path.join(QDIR, "questions.jsonl"))
cnt = Counter(len(q["gold_evidence_chunk_ids"]) for q in qs)
print("questions.jsonl 实际 gold 条数分布 =", dict(sorted(cnt.items())))
print("gold_verified_by 取值 =", set(q["gold_verified_by"] for q in qs))
print("gold_review_status 取值 =", set(q["gold_review_status"] for q in qs))
print("rule 取值分布 =", Counter(q["gold_evidence_rule"] for q in qs))

for name in ("说明.md", "题目模板.md"):
    p = os.path.join(QDIR, name)
    s = io.open(p, encoding="utf-8").read()
    print()
    print("=" * 70)
    print(name, len(s), "字符")
    for pat in ("待作者逐题确认", "decision_maker_ai_verify_v1", "third_party_model_review_v1",
                "1 条 ×10", "2 条 ×11", "4 条 ×1", "4 条 ×2", "2 条 ×10", "8 条", "上限 7"):
        n = s.count(pat)
        if n:
            for m in re.finditer(re.escape(pat), s):
                a = max(0, m.start() - 120)
                print("  [%s x%d] ...%s..." % (pat, n, re.sub(r"\s+", " ", s[a:m.start() + 120])))
                break
