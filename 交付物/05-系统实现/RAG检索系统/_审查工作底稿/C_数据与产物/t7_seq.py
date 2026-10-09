# -*- coding: utf-8 -*-
"""C 线：复现验收工具的 10 条命令顺序，逐条记录退出码（判断 W2 失败是否可复现）"""
import os, subprocess, sys, time

MIRROR = r"C:\Users\15129\AppData\Local\Temp\stage7_accept_4odd_i5d"
PY = sys.executable
CODE = os.path.join(MIRROR, "交付物/03-代码", "检索")

def mem():
    try:
        import ctypes
        class M(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = M(); m.dwLength = ctypes.sizeof(M)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.dwMemoryLoad, m.ullAvailPhys // (1 << 20), m.ullTotalPhys // (1 << 20)
    except Exception as e:
        return ("?", "?", "?"), 0, 0

print("启动前 内存占用%%=%s 可用MB=%s 总MB=%s" % mem()[:3])

STEPS = [
    ("check_inputs", [os.path.join(CODE, "check_inputs.py")]),
    ("vector_search_selftest", [os.path.join(CODE, "vector_search.py"), "--selftest"]),
    ("graph_query_selftest", [os.path.join(CODE, "graph_query.py"), "--selftest"]),
    ("pipeline_selftest", [os.path.join(CODE, "pipeline.py"), "--selftest"]),
]
for cycle in ("run1", "run2"):
    STEPS.append(("cycle_%s_pipeline" % cycle,
                  [os.path.join(CODE, "pipeline.py"), "--group", "C", "--out",
                   os.path.join(MIRROR, "交付物/05-系统实现/RAG检索系统", "检索产出", "per_question_trace.jsonl")]))
    STEPS.append(("cycle_%s_pre_experiment" % cycle,
                  [os.path.join(CODE, "pre_experiment.py"), "--quiet"]))
    STEPS.append(("cycle_%s_metrics" % cycle, [os.path.join(CODE, "metrics.py")]))

for name, argv in STEPS:
    t0 = time.time()
    p = subprocess.run([PY, "-X", "utf8"] + argv, cwd=MIRROR, capture_output=True)
    err = p.stderr.decode("utf-8", "replace")
    flag = "OpenBLAS" in err
    print("%-26s rc=%d %.1fs openblas_err=%s 可用MB=%s" % (
        name, p.returncode, time.time() - t0, flag, mem()[1]))
