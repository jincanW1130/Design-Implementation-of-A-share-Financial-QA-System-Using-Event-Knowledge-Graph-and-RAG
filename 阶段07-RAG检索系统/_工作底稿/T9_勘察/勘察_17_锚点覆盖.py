# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 17：检查每题 gold 的每个块是否都有核验锚点。"""

import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
SRC = os.path.join(ROOT, "代码", "检索", "build_questions.py")

src = io.open(SRC, encoding="utf-8").read()
missing = []
total = 0
for m in re.finditer(r'qid="(PE-\d+)"(.*?)\n    \),', src, re.S):
    qid, body = m.group(1), m.group(2)
    gold = [int(x) for x in re.search(r"gold=\[([^\]]*)\]", body).group(1).split(",") if x.strip()]
    anchors = [int(a) for a, _ in re.findall(r"\((\d+),\s*\"([^\"]+)\"\)", body)]
    total += 1
    lack = [c for c in gold if c not in anchors]
    if lack:
        missing.append((qid, lack, gold))
for qid, lack, gold in missing:
    print("%s 缺锚点的 gold 块：%s（gold=%s）" % (qid, lack, gold))
print("解析到 %d 题；存在未加锚点 gold 块的题 %d 道" % (total, len(missing)))
