# -*- coding: utf-8 -*-
r"""「提高 event_time 抽取覆盖率」能救回多少可过滤文档 —— 结构性上限估算（只读、零模型调用）。

## 问题

《02》第12.2节 要求正式测试集每格 6 道带时间约束的题（时序型），而《16》第 9.4 节登记的
可过滤性主口径是「**该文档的事件里有 ≥2 个不同 `event_date`**」——
v1.2 实测只有 **66 篇**（补抽前 44 篇）。这条硬约束是正式 120 题测试集目前唯一的瓶颈
（关系型 2 跳的瓶颈已由候选口径 v1.3 解决：多公司事件 16 → 286）。

《16》9.4 还写明：图谱层 `event_time` 空值 **544／1100（49.5%）**。于是问题变成：
**如果把这些空值填上，能多出多少可过滤文档？** 本脚本给出**上限**，供作者决定是否值得投入补抽。

## 为什么能给出「上限」

一个文档要拥有「≥2 个不同 event_date」，它至少要佐证 **≥2 个事件**——这是**结构性的**
（一个事件最多贡献一个日期）。所以：

    上限 = 「佐证 ≥2 个事件」的文档数

无论抽取做得多好都不可能突破。再把这个上限拆开，才能区分「可救回」与「救不回」：

| 情形 | 现状 | 补抽能否救回 |
| --- | --- | --- |
| A. ≥2 个事件，但非空 event_time **< 2 条** | 时间字段缺 | **能**——正是补抽的目标 |
| B. ≥2 个已填日期，但**全部同一天** | 日期齐全然而相同 | **不能**——日期本来就一样，不是抽取缺陷 |
| C. 只有 0～1 个事件 | 事件本身就没有 | **不能**——要的是多抽事件，不是补时间 |

## 口径

与 `交付物/03-代码\抽取与图谱\config.py` 的 `时间覆盖_度量.json` 保持一致：
`docs_with_ge2_distinct_event_dates` 按**文档所佐证事件的 `event_time` 去重后 ≥2** 计。
本脚本同时给出图谱层（去重后，＝《16》的 66 口径）与抽取层（去重前）。

## 用法

    python "交付物/06-实验与评测\\工具\\估时间覆盖上限.py"
    python "交付物/06-实验与评测\\工具\\估时间覆盖上限.py" --export <图谱导出目录>
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


def measure(export_dir: str) -> dict:
    nodes = {r["node_id"]: r for r in read_csv(os.path.join(export_dir, "nodes.csv"))}
    edges = read_csv(os.path.join(export_dir, "edges.csv"))

    # 文档 → 它佐证的事件集合（EVIDENCED_BY: Event -[EVIDENCED_BY]-> Document）
    doc_events = collections.defaultdict(set)
    for e in edges:
        if e.get("relation") != "EVIDENCED_BY":
            continue
        h, t = e.get("head_id"), e.get("tail_id")
        if nodes.get(h, {}).get("label") == "Event" and nodes.get(t, {}).get("label") == "Document":
            doc_events[t].add(h)

    docs_total = sum(1 for r in nodes.values() if r.get("label") == "Document")
    ev_total = sum(1 for r in nodes.values() if r.get("label") == "Event")
    ev_null = sum(1 for r in nodes.values()
                  if r.get("label") == "Event" and not (r.get("event_time") or "").strip())

    ge2_events = 0            # 上限：佐证 ≥2 个事件的文档
    ge2_distinct = 0          # 现状主口径：≥2 个不同日期
    ge2_nonnull = 0           # 字面口径：≥2 条非空 event_time
    recoverable = 0           # A 类：≥2 事件但非空 <2 条
    same_date = 0             # B 类：≥2 非空但全同一天
    too_few_events = 0        # C 类：≤1 个事件
    a_zero_dated = 0          # A 类细分：≥2 事件、一条日期都没抽到
    a_one_dated = 0           # A 类细分：≥2 事件、只抽到 1 条日期
    b_same_eq_publish = 0     # B 类细分：共享日期 == 文档 publish_time 的日期（年份锚定产物）
    b_same_ne_publish = 0     # B 类细分：共享日期 != publish_time（真实同一天，救不回）
    ev_per_doc = collections.Counter()

    for doc, evs in doc_events.items():
        ev_per_doc[len(evs)] += 1
        dates = [(nodes[e].get("event_time") or "").strip() for e in evs]
        dated = [d for d in dates if d]
        if len(evs) >= 2:
            ge2_events += 1
            if len(set(dated)) >= 2:
                ge2_distinct += 1
            elif len(dated) < 2:
                recoverable += 1
                if not dated:
                    a_zero_dated += 1
                else:
                    a_one_dated += 1
            else:
                same_date += 1
                pub = (nodes.get(doc, {}).get("publish_time") or "").strip()
                if pub and pub[:10] == dated[0][:10]:
                    b_same_eq_publish += 1
                else:
                    b_same_ne_publish += 1
        else:
            too_few_events += 1
        if len(dated) >= 2:
            ge2_nonnull += 1

    docs_no_events = docs_total - len(doc_events)
    ceiling = ge2_events
    # 「同一天率」的经验值：在**已抽到 ≥2 条日期**的文档里，日期全部相同占多少。
    # 用它把 A 类的乐观值折成现实值——因为补抽填上的日期也可能彼此相同。
    same_rate = (same_date / float(ge2_nonnull)) if ge2_nonnull else 0.0
    realistic = ge2_distinct + int(round(recoverable * (1.0 - same_rate)))
    return {
        "export_dir": os.path.relpath(export_dir, ROOT),
        "docs_total": docs_total,
        "docs_with_no_event": docs_no_events,
        "events_total": ev_total,
        "events_event_time_null": ev_null,
        "events_event_time_null_pct": round(100.0 * ev_null / ev_total, 1) if ev_total else None,
        "docs_with_ge2_events_CEILING": ceiling,
        "docs_with_ge2_distinct_event_dates_NOW": ge2_distinct,
        "docs_with_ge2_nonnull_events": ge2_nonnull,
        "gap_to_ceiling": ceiling - ge2_distinct,
        "class_A_recoverable_by_backfill": recoverable,
        "class_A_zero_dated": a_zero_dated,
        "class_A_one_dated": a_one_dated,
        "class_B_all_same_date": same_date,
        "class_B_same_eq_publish_time": b_same_eq_publish,
        "class_B_same_ne_publish_time": b_same_ne_publish,
        "class_C_too_few_events": too_few_events,
        "empirical_same_date_rate": round(same_rate, 4),
        "OPTIMISTIC_ceiling": ge2_distinct + recoverable,
        "REALISTIC_estimate": realistic,
        "events_per_doc_dist": dict(sorted(ev_per_doc.items())),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="event_time 覆盖率提升的结构性上限估算（只读）")
    ap.add_argument("--export", default=DEFAULT_EXPORT)
    ap.add_argument("--export-b", default=None, help="可选：第二个导出目录做对照")
    args = ap.parse_args()

    res = measure(os.path.abspath(args.export))
    print("=" * 78)
    print("「提高 event_time 覆盖率」能救回多少可过滤文档 —— 结构性上限（只读、零模型调用）")
    print("=" * 78)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    print("")
    print("-" * 78)
    print("判读")
    print("-" * 78)
    print("  文档总数                       %5d（其中 %d 篇没有任何事件）"
          % (res["docs_total"], res["docs_with_no_event"]))
    print("  现状主口径（≥2 个不同日期）      %5d  ← 《16》9.4 登记的可过滤性主口径"
          % res["docs_with_ge2_distinct_event_dates_NOW"])
    print("  结构性上限（佐证 ≥2 个事件）     %5d  ← 无论抽取多好都不可能超过"
          % res["docs_with_ge2_events_CEILING"])
    print("  ⇒ 到上限的缺口                 %5d" % res["gap_to_ceiling"])
    print("     A 类「日期不足」可被补抽救回    %5d（其中一条日期都没抽到 %d、只抽到 1 条 %d）"
          % (res["class_A_recoverable_by_backfill"], res["class_A_zero_dated"],
             res["class_A_one_dated"]))
    print("     B 类「日期本就同一天」救不回    %5d（共享日期==发布日 %d、!= 发布日 %d）"
          % (res["class_B_all_same_date"], res["class_B_same_eq_publish_time"],
             res["class_B_same_ne_publish_time"]))
    print("     C 类「只有 0～1 个事件」       %5d（要的是多抽事件，不是补时间）"
          % res["class_C_too_few_events"])
    print("")
    print("  【上限】乐观：%d 篇（假设 A 类补上的日期两两不同）"
          % res["OPTIMISTIC_ceiling"])
    print("  【现实】按经验「同一天率」%.1f%%（= %d／%d，在已抽到 ≥2 条日期的文档里测得）折算："
          % (100 * res["empirical_same_date_rate"], res["class_B_all_same_date"],
             res["docs_with_ge2_nonnull_events"]))
    print("         %d 篇" % res["REALISTIC_estimate"])
    print("  事件表：%d 个事件中 %d 个 event_time 为空（%s%%）"
          % (res["events_total"], res["events_event_time_null"],
             res["events_event_time_null_pct"]))

    if args.export_b:
        other = measure(os.path.abspath(args.export_b))
        print("")
        print("-" * 78)
        print("对照：%s" % other["export_dir"])
        for k in ("docs_with_ge2_distinct_event_dates_NOW", "docs_with_ge2_events_CEILING",
                  "class_A_recoverable_by_backfill", "class_B_all_same_date",
                  "REALISTIC_estimate"):
            print("  %-42s %6s → %6s" % (k, res[k], other[k]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
