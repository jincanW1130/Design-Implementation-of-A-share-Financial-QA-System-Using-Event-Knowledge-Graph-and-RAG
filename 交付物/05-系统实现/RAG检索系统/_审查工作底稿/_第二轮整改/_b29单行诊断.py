# -*- coding: utf-8 -*-
"""单行诊断：`交付物/07-设计与需求/需求分析\\08-…` L13 行的反引号与竖线结构。"""
import io
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
path = os.path.join(ROOT, "交付物/07-设计与需求/需求分析", "08-跨文档一致性复核与修订（2026-09-23）.md")
line = open(path, encoding="utf-8").read().split("\n")[68]          # 第 69 行（0 基）
masked = re.sub(r'`[^`]*`', lambda m: m.group(0).replace("|", "\u0001"), line)
print("反引号个数 =", line.count("`"), "（奇数即有不配对的代码跨度）")
print("竖线个数 =", line.count("|"))
print("现行列数 =", len(line.strip("|").split("|")))
print("掩蔽后列数 =", len(masked.strip("|").split("|")))
print("掩蔽后新增竖线占位 =", masked.count("\u0001"))
print("\n原文：\n%s" % line)
print("\n掩蔽后：\n%s" % masked)
