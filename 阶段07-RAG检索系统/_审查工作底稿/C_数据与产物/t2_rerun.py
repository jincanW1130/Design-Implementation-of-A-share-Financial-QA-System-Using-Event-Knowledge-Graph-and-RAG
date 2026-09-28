import hashlib, io, json, os, subprocess, sys, time

MIRROR = r"C:\Users\15129\AppData\Local\Temp\re7_C\mirror"
WS = r"C:\Users\15129\Desktop\毕业设计\阶段07-RAG检索系统\检索产出"
LOGDIR = r"C:\Users\15129\AppData\Local\Temp\re7_C\logs"
OUTDIR = os.path.join(MIRROR, "阶段07-RAG检索系统", "检索产出")
PY = sys.executable

FILES = ["per_question_trace.jsonl", "pre_experiment_matrix.jsonl",
         "k_selection.json", "metrics_pre.jsonl"]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def run(cmd, log):
    t0 = time.time()
    p = subprocess.run(cmd, cwd=MIRROR, capture_output=True)
    dt = time.time() - t0
    with open(log, "wb") as f:
        f.write(b"$ " + " ".join(cmd).encode("utf-8") + b"\n")
        f.write(p.stdout)
        f.write(b"\n--- stderr ---\n")
        f.write(p.stderr)
    print("  [%s] rc=%d %.2fs -> %s" % (os.path.basename(cmd[1]), p.returncode, dt, log))
    return p.returncode


def one_run(tag):
    print("== run %s ==" % tag)
    runs = [
        ([PY, "-X", "utf8", os.path.join(MIRROR, "代码", "检索", "pipeline.py"),
          "--group", "C", "--out", os.path.join(MIRROR, "阶段07-RAG检索系统", "检索产出",
                                                 "per_question_trace.jsonl")],
         os.path.join(LOGDIR, "t2_%s_pipeline.txt" % tag)),
        ([PY, "-X", "utf8", os.path.join(MIRROR, "代码", "检索", "pre_experiment.py"), "--quiet"],
         os.path.join(LOGDIR, "t2_%s_pre_experiment.txt" % tag)),
        ([PY, "-X", "utf8", os.path.join(MIRROR, "代码", "检索", "metrics.py")],
         os.path.join(LOGDIR, "t2_%s_metrics.txt" % tag)),
    ]
    rcs = [run(c, l) for c, l in runs]
    return {f: sha256_file(os.path.join(OUTDIR, f)) for f in FILES}, rcs


os.makedirs(LOGDIR, exist_ok=True)
res = {}
for tag in ("run1", "run2"):
    res[tag], rcs = one_run(tag)
    if any(rcs):
        print("  !! non-zero rc:", rcs)

print()
print("== sha256 对照 ==")
print("%-28s %-8s %-8s %-8s %-8s" % ("file", "ws", "run1", "run2", "r1==r2==ws"))
summary = {}
for f in FILES:
    ws = sha256_file(os.path.join(WS, f))
    a, b = res["run1"][f], res["run2"][f]
    same = (a == b == ws)
    print("%-28s %-8s %-8s %-8s %s" % (f, ws[:8], a[:8], b[:8], same))
    summary[f] = {"ws": ws, "run1": a, "run2": b, "identical": same}

with open(os.path.join(r"C:\Users\15129\AppData\Local\Temp\re7_C", "t2_summary.json"),
          "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=1)

if all(v["identical"] for v in summary.values()):
    print("\n结论：四个产物两次运行互相一致，且与工作区交付件逐字节一致。")
else:
    print("\n结论：存在不一致（见上表）。")
