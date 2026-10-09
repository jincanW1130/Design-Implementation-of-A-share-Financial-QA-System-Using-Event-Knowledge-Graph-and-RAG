# -*- coding: utf-8 -*-
"""C 线：保留镜像重跑现场（--keep-tmp），定位 W2 失败命令"""
import os, re, subprocess, sys

ROOT = r"C:\Users\15129\Desktop\毕业设计"
LOGS = r"C:\Users\15129\AppData\Local\Temp\re7_C\logs"
os.makedirs(LOGS, exist_ok=True)
argv = [sys.executable, "-X", "utf8", os.path.join(ROOT, "工具", "验收第7阶段.py"), "--keep-tmp"]
p = subprocess.run(argv, cwd=ROOT, capture_output=True)
out = p.stdout.decode("utf-8", "replace")
f = open(os.path.join(LOGS, "t7_full_keep_mine.txt"), "w", encoding="utf-8")
f.write(out)
f.close()
print("rc =", p.returncode)
m = re.search(u"\u955c\u50cf\u91cd\u8dd1\u76ee\u5f55\u4fdd\u7559\u5728\uff1a(.+)", out)
mirror = m.group(1).strip() if m else ""
print("mirror =", mirror)
logdir = os.path.join(mirror, "_accept_logs")
names = sorted(os.listdir(logdir)) if os.path.isdir(logdir) else []
for name in names:
    raw = open(os.path.join(logdir, name), "rb").read().decode("utf-8", "replace")
    lines = [l for l in raw.strip().split("\n") if l.strip()]
    print("---", name)
    for l in lines[-4:]:
        print("     ", l[:200])
