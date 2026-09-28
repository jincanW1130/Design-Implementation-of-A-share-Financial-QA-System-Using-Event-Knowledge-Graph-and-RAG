# -*- coding: utf-8 -*-
"""独立复现实验：在 re7_B/mirror 里跑两轮（pipeline --group C → pre_experiment → metrics），
比对四个产物的 SHA-256 是否两轮相同、且是否等于**工作区**交付产物。
不采信门禁脚本的自述；本脚本自己起进程、自己算哈希。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

MIR = r"C:\Users\15129\AppData\Local\Temp\re7_B\mirror"
WS_OUT = r"C:\Users\15129\Desktop\毕业设计\阶段07-RAG检索系统\检索产出"
CODE = os.path.join(MIR, "代码", "检索")
OUT = os.path.join(MIR, "阶段07-RAG检索系统", "检索产出")
FILES = ["pre_experiment_matrix.jsonl", "k_selection.json",
         "per_question_trace.jsonl", "metrics_pre.jsonl"]

env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
env["HF_HUB_OFFLINE"] = "1"
env["TRANSFORMERS_OFFLINE"] = "1"
for name in list(env):
    if any(s in name.upper() for s in ("API_KEY", "SECRET", "TOKEN", "MOONSHOT", "DASHSCOPE",
                                      "OPENAI", "DEEPSEEK", "ANTHROPIC", "GEMINI", "ZHIPU")):
        env.pop(name, None)


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run(tag, argv):
    t0 = time.time()
    p = subprocess.run([sys.executable] + argv, cwd=MIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env, timeout=7200)
    dt = time.time() - t0
    tail = (p.stdout or "").strip().split("\n")
    print("  [%s] exit=%d  %.1fs  末行=%s" % (tag, p.returncode, dt, tail[-1][:70] if tail else ""))
    if p.returncode != 0:
        print("  stderr:", (p.stderr or "")[-600:])
    return p.returncode


cycles = []
for i in (1, 2):
    print("=== 第 %d 轮 ===" % i)
    codes = []
    codes.append(run("pipeline", [os.path.join(CODE, "pipeline.py"), "--group", "C",
                                 "--out", os.path.join(OUT, "per_question_trace.jsonl")]))
    codes.append(run("pre_experiment", [os.path.join(CODE, "pre_experiment.py"), "--quiet"]))
    codes.append(run("metrics", [os.path.join(CODE, "metrics.py")]))
    cycles.append({"codes": codes, "sha": {n: sha(os.path.join(OUT, n)) for n in FILES}})

print()
print("%-30s %-18s %-18s %-18s" % ("文件", "轮1", "轮2", "工作区"))
allsame = True
ws_same = True
for n in FILES:
    a, b = cycles[0]["sha"][n], cycles[1]["sha"][n]
    w = sha(os.path.join(WS_OUT, n))
    allsame = allsame and (a == b)
    ws_same = ws_same and (a == w)
    print("%-30s %-18s %-18s %-18s  两轮同=%s 与工作区同=%s"
          % (n, a[:16], b[:16], w[:16], a == b, a == w))
print()
print("两轮逐字节一致 =", allsame)
print("镜像产物 == 工作区交付产物 =", ws_same)
print("退出码 =", [cycles[0]["codes"], cycles[1]["codes"]])
