# -*- coding: utf-8 -*-
"""C 线：现场重跑 工具\验收第7阶段.py 的两个 profile，原样留痕（UTF-8）"""
import os, subprocess, sys, time

ROOT = r"C:\Users\15129\Desktop\毕业设计"
LOGS = r"C:\Users\15129\AppData\Local\Temp\re7_C\logs"
os.makedirs(LOGS, exist_ok=True)

for profile, tag in (("static", "t7_static_mine.txt"), ("full", "t7_full_mine.txt")):
    argv = [sys.executable, "-X", "utf8", os.path.join(ROOT, "工具", "验收第7阶段.py")]
    if profile == "static":
        argv.append("--profile")
        argv.append("static")
    t0 = time.time()
    p = subprocess.run(argv, cwd=ROOT, capture_output=True)
    dt = time.time() - t0
    with open(os.path.join(LOGS, tag), "wb") as f:
        f.write(b"$ " + " ".join(argv).encode("utf-8") + b"\n")
        f.write(p.stdout)
        f.write(b"\n--- stderr ---\n")
        f.write(p.stderr)
    print("%s rc=%d %.1fs bytes=%d stderr=%d" % (tag, p.returncode, dt, len(p.stdout), len(p.stderr)))
