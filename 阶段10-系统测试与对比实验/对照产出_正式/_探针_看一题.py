# -*- coding: utf-8 -*-
"""只读探针：打印指定组最近一题 trace 的 attempts／token 账摘要（0 次模型调用）。"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GROUP = sys.argv[1] if len(sys.argv) > 1 else "A"

d = os.path.join(HERE, "逐题", GROUP)
if not os.path.isdir(d):
    print("目录不存在：%s" % d)
    sys.exit(1)
qs = sorted(os.listdir(d))
# 正在跑的题已建目录但尚未落 trace，取最后一个**确实有 trace** 的题
qs = [q for q in qs if os.path.isfile(os.path.join(d, q, "answer_trace.jsonl"))]
if not qs:
    print("该组尚无已落盘题")
    sys.exit(1)
qid = qs[-1]
f = os.path.join(d, qid, "answer_trace.jsonl")
r = json.loads(open(f, encoding="utf-8").readline())
print("组=%s 题号=%s 已落盘=%d 题" % (GROUP, qid, len(qs)))
print("evidence_count = %s" % r.get("evidence_count"))
print("gates.ok       = %s" % (r.get("gates") or {}).get("ok"))
print("gates.failures = %s" % (r.get("gates") or {}).get("failures"))
print("attempts       = %s" % json.dumps(r.get("attempts"), ensure_ascii=False))
print("body_chars     = %d" % len(r.get("body_text") or ""))
print("token_account  = %s" % json.dumps(r.get("token_account"), ensure_ascii=False))
print("model          = %s" % json.dumps(r.get("model"), ensure_ascii=False))
