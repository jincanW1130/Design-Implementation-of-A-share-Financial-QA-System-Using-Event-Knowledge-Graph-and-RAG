# -*- coding: utf-8 -*-
"""列出《03》《04》里所有"反引号 token 中含 * "的写法（跨文档核验 K 组会把通配写法按真判处理）。"""
from __future__ import annotations

import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for name in ("03-精选文献库（22篇）.md", "04-开题报告.md"):
    p = os.path.join(BASE, name)
    t = io.open(p, encoding="utf-8").read()
    print("==", name)
    for m in re.finditer(r"`([^`\n]*)`", t):
        tok = m.group(1)
        if "*" in tok:
            print("   ", tok)
