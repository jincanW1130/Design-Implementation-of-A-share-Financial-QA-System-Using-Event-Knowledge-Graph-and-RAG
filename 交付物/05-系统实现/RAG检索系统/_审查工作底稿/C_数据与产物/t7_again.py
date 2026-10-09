# -*- coding: utf-8 -*-
"""C 线：第三次现场重跑验收工具，并采样内存，判断 W2 失败是否可复现"""
import os, subprocess, sys, threading, time

ROOT = r"C:\Users\15129\Desktop\毕业设计"
LOGS = r"C:\Users\15129\AppData\Local\Temp\re7_C\logs"

def avail():
    import ctypes
    class M(ctypes.Structure):
        _fields_ = [("l", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tp", ctypes.c_ulonglong),
                    ("ap", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong),
                    ("apf", ctypes.c_ulonglong), ("tv", ctypes.c_ulonglong),
                    ("av", ctypes.c_ulonglong), ("aev", ctypes.c_ulonglong)]
    m = M(); m.l = ctypes.sizeof(M)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.load, m.ap >> 20, m.apf >> 20

samples = []
stop = False
def sampler():
    while not stop:
        samples.append(avail())
        time.sleep(2)

t = threading.Thread(target=sampler)
t.start()
argv = [sys.executable, "-X", "utf8", os.path.join(ROOT, "工具", "验收第7阶段.py"), "--keep-tmp"]
t0 = time.time()
p = subprocess.run(argv, cwd=ROOT, capture_output=True)
stop = True
t.join()
out = p.stdout.decode("utf-8", "replace")
f = open(os.path.join(LOGS, "t7_full_mine3.txt"), "w", encoding="utf-8")
f.write(out)
f.close()
print("rc =", p.returncode, "耗时 %.1fs" % (time.time() - t0))
print("内存采样：load%% min=%s max=%s ｜ 可用物理 MB min=%s ｜ 可用提交 MB min=%s" % (
    min(s[0] for s in samples), max(s[0] for s in samples),
    min(s[1] for s in samples), min(s[2] for s in samples)))
for line in out.split("\n"):
    if "W2" in line or "AB3" in line or line.startswith("结论") or line.startswith("  最终"):
        print("   ", line.strip()[:200])
