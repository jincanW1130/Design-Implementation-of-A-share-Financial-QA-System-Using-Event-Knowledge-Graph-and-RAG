# -*- coding: utf-8 -*-
"""图谱层「含 ≥2 个公司参与方的事件数」独立计数（只读）。

## 为什么要单独写一个

路线 ③ 的 B 步（放宽入图策略）**唯一的核心成功判据**就是这一个数字：
现行 v1.2 图谱里含 ≥2 个公司参与方的 Event 极少（决策者独立复算 = **16**），
而抽取层有 287～309 个。本脚本**不复用 `graph_stats.json` 的汇总字段**，
而是直接从 `nodes.csv` + `edges.csv` 现场重算，用来**交叉验证**产物自报的读数。

## 口径

* 参与方 = `PARTICIPATES_IN` 边的 **Company 端点**（两边方向都认）；
* 事件 = `PARTICIPATES_IN` 边的 **Event 端点**；
* 「含 ≥2 公司」= 同一事件上**去重后**的 Company 节点数 ≥ 2；
* 若节点表带 `resolved_by` 列，额外按 `stock_code` / `name_only` 拆分统计。

## 用法

    python "交付物/06-实验与评测\\工具\\计数_图谱多公司事件.py"
    python "交付物/06-实验与评测\\工具\\计数_图谱多公司事件.py" --export <目录> --compare <另一目录>
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os

# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\工具\` 整体移到
# `交付物/06-实验与评测\工具\`（**下移一层**），求 ROOT 的上溯次数 3 → 4。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_EXPORT = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def read_csv(path: str) -> list:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def count(export_dir: str) -> dict:
    nodes = read_csv(os.path.join(export_dir, "nodes.csv"))
    edges = read_csv(os.path.join(export_dir, "edges.csv"))
    label = {r["node_id"]: r.get("label") for r in nodes}
    resolved_by = {r["node_id"]: (r.get("resolved_by") or "") for r in nodes}

    ev_comp = collections.defaultdict(set)
    for e in edges:
        if e.get("relation") != "PARTICIPATES_IN":
            continue
        h, t = e.get("head_id"), e.get("tail_id")
        if label.get(t) == "Event" and label.get(h) == "Company":
            ev_comp[t].add(h)
        elif label.get(h) == "Event" and label.get(t) == "Company":
            ev_comp[h].add(t)

    multi = {ev: c for ev, c in ev_comp.items() if len(c) >= 2}
    dist = collections.Counter(len(c) for c in multi.values())

    split = collections.Counter()
    has_col = any(v for v in resolved_by.values())
    if has_col:
        for ev, comps in multi.items():
            kinds = {resolved_by.get(c) or "unknown" for c in comps}
            if kinds == {"stock_code"}:
                split["全部有股票代码锚"] += 1
            elif "stock_code" in kinds:
                split["混合（含 name_only）"] += 1
            else:
                split["全部 name_only"] += 1

    return {
        "export_dir": os.path.relpath(export_dir, ROOT),
        "nodes_total": len(nodes),
        "edges_total": len(edges),
        "nodes_by_label": dict(collections.Counter(r.get("label") for r in nodes)),
        "edges_by_relation": dict(collections.Counter(e.get("relation") for e in edges)),
        "events_with_participants": len(ev_comp),
        "events_with_ge2_companies": len(multi),
        "participant_count_dist": dict(sorted(dist.items())),
        "resolved_by_split": dict(split),
        "has_resolved_by_column": has_col,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="图谱层多公司事件独立计数（只读）")
    ap.add_argument("--export", default=DEFAULT_EXPORT)
    ap.add_argument("--compare", default=None, help="可选：另一个导出目录，做并排对照")
    args = ap.parse_args()

    res = count(os.path.abspath(args.export))
    print("=" * 78)
    print("图谱层「含 ≥2 个公司参与方的事件数」独立计数（现场重算，不读汇总字段）")
    print("=" * 78)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    if args.compare:
        other = count(os.path.abspath(args.compare))
        print("-" * 78)
        print("对照：%s" % other["export_dir"])
        for k in ("nodes_total", "edges_total", "events_with_participants",
                  "events_with_ge2_companies"):
            print("  %-30s %8s → %8s" % (k, res[k], other[k]))
        print("  参与方分布  %s → %s" % (res["participant_count_dist"],
                                        other["participant_count_dist"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
