# -*- coding: utf-8 -*-
"""跑一条门禁命令，把 stdout／stderr 与**退出码**一起落成 UTF-8 文本（避免 PowerShell 转码问题）。

用法（工作区根目录）：python 阶段07-RAG检索系统\\_审查工作底稿\\_第二轮整改\\_跑门禁.py <标签> <脚本> [参数...]
"""
import io
import os
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
label = sys.argv[1]
argv = sys.argv[2:]
env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
p = subprocess.run([sys.executable] + argv, cwd=ROOT, capture_output=True, text=True,
                   encoding="utf-8", errors="replace", env=env, timeout=7200)
out = os.path.join(_HERE, label + ".txt")
with open(out, "w", encoding="utf-8", newline="\n") as f:
    f.write(p.stdout or "")
    f.write("\n--- stderr ---\n")
    f.write(p.stderr or "")
    f.write("\n--- exit_code = %d ---\n" % p.returncode)
print("%s：退出码 %d → %s" % (label, p.returncode, out))
