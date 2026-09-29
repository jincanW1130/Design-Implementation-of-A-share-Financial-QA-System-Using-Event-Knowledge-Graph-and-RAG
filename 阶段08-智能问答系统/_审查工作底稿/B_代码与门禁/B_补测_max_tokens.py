# -*- coding: utf-8 -*-
"""B-04 实测：把 config.ANSWER['max_tokens'] 改掉，看门禁（B1）是否失败。"""
from __future__ import annotations
import importlib.util
import os
import shutil
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("bt", os.path.join(HERE, "B_篡改测试.py"))
bt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bt)

root = bt.build_mirror("max_tokens")
try:
    p = os.path.join(root, "代码", "问答", "config.py")
    with open(p, "r", encoding="utf-8") as f:
        t = f.read()
    before = t
    t = t.replace('"max_tokens": 16384,', '"max_tokens": 8192,', 1)
    assert t != before, "未找到 max_tokens 字面量，替换失败"
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    data = bt.run_gate(root, "case-max_tokens")
    # 基线（原样副本）FAIL 集 = {'G6'}（镜像缺 阶段02- 使 G5 UNRUN）
    base = {"G6"}
    new = sorted(set(data.get("fails") or []) - base)
    print("期望 FAIL = B1")
    print("实测 退出码=%s  FAIL=%s  新增失败=%s" % (data["_exit"],
                                              sorted(data.get("fails") or []), new or "∅"))
    print("判定：%s" % ("抓到" if "B1" in (data.get("fails") or []) else "★漏判（假阴性）★"))
    # 抓 B1 行原文
    for l in open(os.path.join(os.environ.get("TEMP", "/tmp"),
                               "_log_case-max_tokens.txt"), encoding="utf-8"):
        if "B1 " in l and l.strip().startswith("["):
            print("B1 行：", l.rstrip()[:200])
finally:
    shutil.rmtree(root, ignore_errors=True)
