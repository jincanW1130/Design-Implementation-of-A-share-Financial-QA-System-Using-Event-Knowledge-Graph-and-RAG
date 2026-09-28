# -*- coding: utf-8 -*-
"""按交付要求跑 8 项验证并把原始输出写成 UTF-8 文本（避免 PowerShell 重定向的编码问题）。

用法：python 09_跑验证.py
产出：_替换执行/_验证输出/07_跨文档核验_替换后.txt
      _替换执行/_验证输出/08_跨文档核验strict_替换后.txt
      _替换执行/_验证输出/09_验收第4阶段_替换后.txt
      _替换执行/_验证输出/10_git_status.txt
"""
from __future__ import annotations

import io
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTDIR = os.path.join(ROOT, "阶段02-文献调研与开题", "_替换执行", "_验证输出")
os.makedirs(OUTDIR, exist_ok=True)

JOBS = [
    ("07_跨文档核验_替换后.txt", [sys.executable, os.path.join(ROOT, "工具", "跨文档核验.py")]),
    ("08_跨文档核验strict_替换后.txt", [sys.executable, os.path.join(ROOT, "工具", "跨文档核验.py"), "--strict-citations"]),
    ("09_验收第4阶段_替换后.txt", [sys.executable, os.path.join(ROOT, "工具", "验收第4阶段文档.py")]),
    ("10_git_status.txt", ["git", "status", "--short"]),
]


def main() -> None:
    for out, cmd in JOBS:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True)
        txt = p.stdout.decode("utf-8", errors="replace") + p.stderr.decode("utf-8", errors="replace")
        io.open(os.path.join(OUTDIR, out), "w", encoding="utf-8").write(txt)
        print("=" * 70)
        print("%s  ->  exit=%d  (%d 字节)" % (out, p.returncode, len(txt.encode("utf-8"))))
        tail = [L for L in txt.split("\n") if "[FAIL]" in L or "退出码" in L]
        for L in tail[:12]:
            print("   ", L.strip())


if __name__ == "__main__":
    main()
