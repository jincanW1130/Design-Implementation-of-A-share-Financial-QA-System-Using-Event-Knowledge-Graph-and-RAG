# -*- coding: utf-8 -*-
"""C 线独立重算：9 格网格读数、饱和、g 曲线（不 import metrics，不 import pre_experiment）"""
import io, json, os, subprocess, sys, hashlib

MIRROR = r"C:\Users\15129\AppData\Local\Temp\re7_C\mirror"
WS = r"C:\Users\15129\Desktop\毕业设计\交付物/05-系统实现/RAG检索系统"
LOGDIR = r"C:\Users\15129\AppData\Local\Temp\re7_C\logs"
TMPDIR = os.path.join(MIRROR, "_C_tmp")
PY = sys.executable

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

questions = {r["qid"]: r for r in load_jsonl(os.path.join(WS, "预实验问题集", "questions.jsonl"))}
chunks = {int(r["chunk_id"]): r for r in load_jsonl(
    os.path.join(MIRROR, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl"))}

def norm(ids):
    out, seen = [], set()
    for x in ids or []:
        s = str(x)
        if s not in seen:
            seen.add(s); out.append(s)
    return out

def my_metrics(final_ids, gold_ids, K):
    top = norm(final_ids)[:K]
    gold = set(norm(gold_ids))
    hit = len(set(top) & gold)
    recall = hit / len(gold) if gold else 0.0
    prec = hit / K
    mrr = 0.0
    for i, c in enumerate(top, 1):
        if c in gold:
            mrr = 1.0 / i; break
    cer = 1.0 if (gold and gold <= set(top)) else 0.0
    return dict(recall_at_k=round(recall, 8), precision_at_k=round(prec, 8),
                mrr=round(mrr, 8), complete_evidence_recall_at_k=cer)

def text_tokens(final_ids):
    return sum(chunks[int(c)]["token_count"] for c in final_ids if int(c) in chunks)

def run_pipeline(K, N, B, g, tag):
    out = os.path.join(TMPDIR, "trace_%s.jsonl" % tag)
    cmd = [PY, "-X", "utf8", os.path.join(MIRROR, "交付物/03-代码", "检索", "pipeline.py"),
           "--group", "C", "--k", str(K), "--n", str(N), "--budget", str(B),
           "--graph-share", str(g), "--out", out, "--quiet"]
    p = subprocess.run(cmd, cwd=MIRROR, capture_output=True)
    with open(os.path.join(LOGDIR, "t4_%s.txt" % tag), "wb") as f:
        f.write(b"$ " + " ".join(cmd).encode("utf-8") + b"\n")
        f.write(p.stdout + b"\n--- stderr ---\n" + p.stderr)
    if p.returncode != 0:
        print("   pipeline rc=%d for %s" % (p.returncode, tag))
    rows = load_jsonl(out)
    med = sorted(text_tokens(r["final_evidence_chunk_ids"]) for r in rows)
    n = len(med)
    median = med[n // 2] if n % 2 else (med[n // 2 - 1] + med[n // 2]) / 2
    aggs = {k: round(sum(my_metrics(r["final_evidence_chunk_ids"],
                                    questions[r["qid"]]["gold_evidence_chunk_ids"], K)[k]
                         for r in rows) / n, 8)
            for k in ("recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k")}
    mean_ev = round(sum(len(r["final_evidence_chunk_ids"]) for r in rows) / n, 8)
    return dict(K=K, N=N, budget=B, g=g, median_text=median,
                mean_evidence_size=mean_ev, metrics=aggs, n_questions=n,
                sha=hashlib.sha256(open(out, "rb").read()).hexdigest()[:16])

os.makedirs(TMPDIR, exist_ok=True)
os.makedirs(LOGDIR, exist_ok=True)

CASES = [
    ("r1_K5_N20",   5, 20, 1593125, 2),
    ("r1_K10_N20", 10, 20, 1593125, 2),
    ("r1_K10_N50", 10, 50, 1593125, 2),
    ("r1_K10_N100", 10, 100, 1593125, 2),
    ("r1_K15_N20", 15, 20, 1593125, 2),
    ("r1_K15_N50", 15, 50, 1593125, 2),
    ("B3600_K15_N20", 15, 20, 3600, 2),
]
GCASES = [("g%d" % g, 10, 20, 3600, g) for g in (0, 1, 2, 3, 5)]

res = {}
print("== 独立重跑：网格读数（C 组）==")
print("%-16s %-4s %-5s %-11s %-12s %-11s %s" % ("case", "K", "N", "median_txt", "mean_ev", "CER", "metrics"))
for tag, K, N, B, g in CASES + GCASES:
    r = run_pipeline(K, N, B, g, tag)
    res[tag] = r
    print("%-16s %-4d %-5d %-11s %-12s %-11s %s" % (
        tag, K, N, r["median_text"], r["mean_evidence_size"],
        r["metrics"]["complete_evidence_recall_at_k"],
        json.dumps(r["metrics"], ensure_ascii=False)))

json.dump(res, open(os.path.join(r"C:\Users\15129\AppData\Local\Temp\re7_C", "t4_result.json"),
                    "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print()
print("== 对照产物 ==")
mat = load_jsonl(os.path.join(WS, "检索产出", "pre_experiment_matrix.jsonl"))
for r in mat:
    if r["round"] == "round1_nonbinding" and (r["K"], r["N"]) in ((5, 20), (10, 20), (10, 50), (10, 100), (15, 20), (15, 50)):
        print("matrix K=%-3d N=%-4d median=%-9s mean_ev=%-12s CER=%s" % (
            r["K"], r["N"], r["occupancy"]["text_tokens"]["median"],
            r["evidence_size"]["mean"], r["metrics"]["complete_evidence_recall_at_k"]))
ks = json.load(io.open(os.path.join(WS, "检索产出", "k_selection.json"), encoding="utf-8"))
br = ks["evidence"]["budget_rule"]
print("budget_rule median_text=%s raw=%s B=%s" % (br["median_text_tokens"], br["raw_value"], br["context_token_budget"]))
print("saturation scan 15 :", json.dumps(ks["evidence"]["saturation_under_budget"]["scan"]["15"], ensure_ascii=False))
print("g_curve primary rows:")
for r in ks["evidence"]["g_curve"]["primary_rows"]:
    print("  g=%s mean_ev=%-12s graph=%s/%s flags=%s metrics=%s" % (
        r["g"], r["mean_evidence_size"], r["graph_evidence_in_final_questions"],
        r["graph_evidence_in_final_total"], r["vs_g0_flags"], json.dumps(r["metrics"], ensure_ascii=False)))
