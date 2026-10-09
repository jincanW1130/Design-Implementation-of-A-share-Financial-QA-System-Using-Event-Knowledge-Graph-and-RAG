# -*- coding: utf-8 -*-
"""临时诊断：为什么 HEAD 版 pipeline.py 在临时目录里加载时过不了 config 同目录守卫。"""
from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
CODE = os.path.join(ROOT, "交付物/03-代码", "检索")

tmp = tempfile.mkdtemp(prefix="b16_dbg_")
try:
    for name in ("config.py", "graph_query.py", "vector_search.py", "metrics.py"):
        shutil.copy2(os.path.join(CODE, name), os.path.join(tmp, name))
    proc = subprocess.run(["git", "show", "HEAD:交付物/03-代码/检索/pipeline.py"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    path = os.path.join(tmp, "pipeline.py")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(proc.stdout)
    print("临时目录 =", repr(tmp))
    print("模块路径 =", repr(path))
    print("abspath  =", repr(os.path.abspath(path)))
    print("dirname  =", repr(os.path.dirname(os.path.abspath(path))))
    print("sys.path[0:3] =", sys.path[:3])
    print("sys.modules 里已有的 config =", getattr(sys.modules.get("config"), "__file__", None))
    spec = importlib.util.spec_from_file_location("pipeline_old", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_old"] = mod
    try:
        spec.loader.exec_module(mod)
        print("加载成功；mod._HERE =", repr(getattr(mod, "_HERE", None)))
    except SystemExit as exc:
        print("SystemExit：", exc)
        print("sys.modules['config'].__file__ =", getattr(sys.modules.get("config"), "__file__", None))
finally:
    shutil.rmtree(tmp, ignore_errors=True)
