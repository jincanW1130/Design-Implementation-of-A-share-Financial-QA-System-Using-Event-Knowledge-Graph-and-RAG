# -*- coding: utf-8 -*-
r"""F8-c 取证（函数级负向用例，只读＋临时目录）：`_dropped_from_stats` 不再「读不到就按 0」。

四种输入：
  A 文件不存在            → (None, 说明)      ← 调用方必须按失败记账（改后）
  B 文件不可解析          → (None, 说明)
  C 文件可读、无该字段    → (0, 说明)         ← 归档口径的正常形态（计数为 0 不新增字段）
  D 文件可读、字段完整    → (该计数, "")
"""
import json
import os
import sys
import tempfile

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".git")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "抽取与图谱"))

import write_graph  # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="F8c_dropped_")
    missing = os.path.join(tmp, "missing.json")
    broken = os.path.join(tmp, "broken.json")
    without = os.path.join(tmp, "without.json")
    with_count = os.path.join(tmp, "with_count.json")
    with open(broken, "w", encoding="utf-8") as fh:
        fh.write("{ not json")
    json.dump({"counts": {}}, open(without, "w", encoding="utf-8"))
    json.dump({"issuer_participation_dropped": {"count": 3}},
              open(with_count, "w", encoding="utf-8"))
    cases = [("A 文件不存在", missing), ("B 文件不可解析", broken),
             ("C 无该字段（归档口径）", without), ("D 字段完整", with_count)]
    for label, path in cases:
        value, note = write_graph._dropped_from_stats({"graph_stats": path})
        print("%s → count=%r；说明=%r" % (label, value, note))
    real = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_2",
                        "graph_stats.json")
    value, note = write_graph._dropped_from_stats({"graph_stats": real})
    print("E 现行 v1.2 产物 → count=%r；说明=%r" % (value, note))
    print("调用方约定：count=None 时 add(..., False, ...) 按失败记账（读不到 ≠ 丢弃 0 条）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
