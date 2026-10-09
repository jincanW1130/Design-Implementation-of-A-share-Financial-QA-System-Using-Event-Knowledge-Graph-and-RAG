# -*- coding: utf-8 -*-
"""C 线：第三方复核的可复现与性质（只读缓存重放＋独立重算）"""
import hashlib, io, json, os
from collections import Counter

ROOT = r"C:\Users\15129\Desktop\毕业设计"
P7 = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统")
WD = os.path.join(P7, "_工作底稿", "第三方复核")
QDIR = os.path.join(P7, "预实验问题集")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

rev = dict((v, dict((r["qid"], r) for r in load_jsonl(os.path.join(WD, v, "review.jsonl"))))
           for v in ("kimi", "zhipu", "qianfan"))
qs = dict((r["qid"], r) for r in load_jsonl(os.path.join(QDIR, "questions.jsonl")))
ledger = json.load(io.open(os.path.join(QDIR, "第三方复核台账.json"), encoding="utf-8"))

print("=" * 70)
print("A. 逐家 verdict 分布 / usage / attempts（由 review.jsonl 独立重算）")
print("=" * 70)
usage = {}
attempts = {}
for v in ("kimi", "zhipu", "qianfan"):
    rows = list(rev[v].values())
    c = Counter(r["verdict"] for r in rows)
    u = Counter()
    for r in rows:
        for k, x in r["usage"].items():
            u[k] += x
    usage[v] = dict(u)
    attempts[v] = sum(r["attempts"] for r in rows)
    print(v, "n=%d" % len(rows), "verdicts=%s" % dict(c), "attempts=%d" % attempts[v], "usage=%s" % dict(u))
tot2 = Counter()
for v in ("kimi", "zhipu"):
    tot2.update(usage[v])
tot3 = Counter()
for v in ("kimi", "zhipu", "qianfan"):
    tot3.update(usage[v])
print("两家合计(确认):", dict(tot2), "| 三家合计(留痕):", dict(tot3))
print("台账 usage_totals:", ledger["usage_totals"])
print("台账 usage_totals_all_lines_trace:", ledger["usage_totals_all_lines_trace"])
print("确认口径 total 一致:", tot2["total_tokens"] == ledger["usage_totals"]["total_tokens"])
print("留痕口径 total 一致:", tot3["total_tokens"] == ledger["usage_totals_all_lines_trace"]["total_tokens"])

print()
print("=" * 70)
print("B. 跨厂商一致率（独立重算：verdict 逐题相等）")
print("=" * 70)
def agree(vs):
    consistent, per = [], {}
    for q in sorted(qs):
        vals = [rev[v][q]["verdict"] for v in vs]
        per[q] = dict(zip(vs, vals))
        if len(set(vals)) == 1:
            consistent.append(q)
    return consistent, per
c2, per2 = agree(["kimi", "zhipu"])
c3, per3 = agree(["kimi", "zhipu", "qianfan"])
print("确认口径(kimi+zhipu): %d/%d = %.4f ; 分歧=%s" % (
    len(c2), len(qs), len(c2) / len(qs), [q for q in sorted(qs) if q not in c2]))
print("留痕口径(三家): %d/%d = %.4f ; 分歧=%s" % (
    len(c3), len(qs), len(c3) / len(qs), [q for q in sorted(qs) if q not in c3]))
print("台账 cross_vendor:", ledger["cross_vendor"]["consistent_questions"],
      ledger["cross_vendor"]["consistency_rate"], ledger["cross_vendor"]["comparable_questions"])
print("台账 all_lines_trace:", ledger["cross_vendor_all_lines_trace"]["consistent_questions"],
      ledger["cross_vendor_all_lines_trace"]["consistency_rate"])

print()
print("=" * 70)
print("C. questions.jsonl 的 third_party_review 字段 ↔ review.jsonl / 台账")
print("=" * 70)
bad = []
for q in sorted(qs):
    t = qs[q]["third_party_review"]
    for v in ("kimi", "zhipu", "qianfan"):
        if t["verdicts"][v] != rev[v][q]["verdict"]:
            bad.append((q, v, "verdict", t["verdicts"][v], rev[v][q]["verdict"]))
        if t["answer_supported"][v] != rev[v][q]["answer_supported"]:
            bad.append((q, v, "answer_supported", t["answer_supported"][v], rev[v][q]["answer_supported"]))
        if t["models"][v] != rev[v][q]["model_resolved"]:
            bad.append((q, v, "model", t["models"][v], rev[v][q]["model_resolved"]))
    exp = (rev["kimi"][q]["verdict"] == rev["zhipu"][q]["verdict"])
    if t["consistent"] != exp:
        bad.append((q, "-", "consistent", t["consistent"], exp))
    if t["confirmed_lines"] != ["kimi", "zhipu"]:
        bad.append((q, "-", "confirmed_lines", t["confirmed_lines"], ["kimi", "zhipu"]))
    if not (t.get("excluded", {}).get("qianfan", {}) or {}).get("excluded_per_author"):
        bad.append((q, "-", "excluded.qianfan", t.get("excluded"), "excluded_per_author=True"))
print("逐题字段异常条数:", len(bad))
for b in bad:
    print("  ", b)

print()
print("=" * 70)
print("D. 报告/台账里与复核相关的 sha256 与现场是否一致")
print("=" * 70)
claims = [
    (os.path.join(WD, "kimi", "review.jsonl"), "660bb66b003cfc2c910af998987ca890d7f7006c0f8ba8106d8b94ad890a7822"),
    (os.path.join(WD, "zhipu", "review.jsonl"), "1359c5cdc80082fc964760a97d424fb42501d6226256f011435d1a03a2edcfd2"),
    (os.path.join(WD, "kimi", "summary.json"), "0f3672ac6dd165a0a8202a9d87b5607371fa00da7eaa570776bd915030cfde6f"),
    (os.path.join(WD, "zhipu", "summary.json"), "66a4e9094e316a46a23dabc800904c4c83efc9efb7c96ac18abd64e403c02972"),
    (os.path.join(WD, "cross_vendor.json"), "13ee59589d76bd94bd8ba124587cee16630529947119084c7a312662d35c0068"),
    (os.path.join(WD, "cross_vendor_all_lines_trace.json"), "fbe079864a42ee4f3d4f08fd62af1b8c976dcfe0b065c036530da40f13eddbfe"),
    (os.path.join(QDIR, "第三方复核台账.json"), "c6a63fd0623bf7a40ed24fc559c5c89898d2e36cf80e44f5181fc1b937f77241"),
    (os.path.join(WD, "qianfan", "review.jsonl"), "575339475f95baff938c286d91155338e81fdb7355d1bf424bdd8e3723488478"),
    (os.path.join(WD, "qianfan", "summary.json"), "90c28b5deebebca1f3537bf2783dff7dfcf85642f45752ac09137b91c17ccba4"),
]
for p, h in claims:
    a = sha256(p) if os.path.exists(p) else None
    print("%-40s 报告=%s 现场=%s %s" % (
        os.path.relpath(p, ROOT), h[:12], (a or "MISSING")[:12],
        "一致" if a == h else "<<< 不一致"))

print()
print("=" * 70)
print("E. 现场 cross_vendor.json ↔ 我的重算")
print("=" * 70)
cv = json.load(io.open(os.path.join(WD, "cross_vendor.json"), encoding="utf-8"))
cv3 = json.load(io.open(os.path.join(WD, "cross_vendor_all_lines_trace.json"), encoding="utf-8"))
print("cross_vendor.json 头:", json.dumps(dict((k, v) for k, v in cv.items()
                                              if k != "per_question"), ensure_ascii=False))
print("per_question 键名:", list(cv["per_question"][0].keys()))
mism = [r["qid"] for r in cv["per_question"] if r["verdicts"] != per2[r["qid"]]]
print("cross_vendor per_question 与我的重算不一致:", mism)
print("all_lines per_question 与我的重算不一致:", [r["qid"] for r in cv3["per_question"]
                                                    if r["verdicts"] != per3[r["qid"]]])
