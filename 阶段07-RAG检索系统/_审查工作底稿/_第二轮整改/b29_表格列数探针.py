# -*- coding: utf-8 -*-
"""B-29 探针：按《工具\\跨文档核验.py》B 组（表格列数）的现行逻辑，找出被判"块内列数不一致"
的表格块，并打印行号、列数与原文，用于区分"真错位"与"行内代码里带竖线导致的误判"。

只读；结果打印到 stdout。
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
STAGES = [d for d in sorted(glob.glob(os.path.join(ROOT, "阶段*"))) if os.path.isdir(d)]
docs = sorted(glob.glob(os.path.join(ROOT, "*.md")))
for sd in STAGES:
    docs += sorted(glob.glob(os.path.join(sd, "*.md")))


def table_blocks(t):
    """与《跨文档核验.py》逐字相同的现行实现（不做任何加工）。"""
    res, cur, fence = [], [], False
    for L in t.split("\n"):
        if L.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        s = L.strip()
        if s.startswith("|") and s.endswith("|"):
            cur.append(s)
        else:
            if len(cur) >= 2:
                res.append(cur)
            cur = []
    if len(cur) >= 2:
        res.append(cur)
    return res


def split_cells(row):
    """现行拆列：strip('|') 后按 '|' 切。"""
    return row.strip("|").split("|")


def split_cells_aware(row):
    """修后拆列：先剔除行内代码（反引号）里的竖线，再切。"""
    masked = re.sub(r"`[^`]*`", lambda m: m.group(0).replace("|", "\u0001"), row)
    return masked.strip("|").split("|")


print("=" * 78)
print("B-29 探针：表格列数块内不一致的定位（现行 split 与「行内代码感知」split 的对照）")
print("=" * 78)
bad_blocks = 0
for path in docs:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    # 与现行实现一样按文件整体扫块，但保留行号
    cur, fence, start = [], False, None
    for i, L in enumerate(lines, 1):
        if L.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        s = L.strip()
        if s.startswith("|") and s.endswith("|"):
            if not cur:
                start = i
            cur.append(s)
        else:
            if len(cur) >= 2:
                n_old = {len(split_cells(r)) for r in cur}
                n_new = {len(split_cells_aware(r)) for r in cur}
                if len(n_old) > 1:
                    bad_blocks += 1
                    print("\n!! %s 第 %d 行起 %d 行：现行列数集合=%s；行内代码感知后=%s"
                          % (os.path.basename(path), start, len(cur), sorted(n_old),
                             sorted(n_new)))
                    for k, r in enumerate(cur):
                        print("   [%d] cols_old=%d cols_new=%d  %s"
                              % (start + k, len(split_cells(r)), len(split_cells_aware(r)),
                                 r[:120]))
            cur = []
    if len(cur) >= 2:
        n_old = {len(split_cells(r)) for r in cur}
        if len(n_old) > 1:
            bad_blocks += 1
            print("\n!! %s 第 %d 行起（文件末）%d 行：现行列数集合=%s"
                  % (os.path.basename(path), start, len(cur), sorted(n_old)))
print("\n合计现行判「块内不一致」的表格块：%d" % bad_blocks)
