# -*- coding: utf-8 -*-
r"""按「任务类型 × 路径深度」9 格统计**可做时序型**的候选数（只读、零模型调用）。

## 目的

《02》第12.2节 要求**每格 12 题 = 无时间约束 6 ＋ 有时间约束 6**（完整版），即需要
**54 道核心 ＋ 12 道压力 = 66 道**带时间约束的题。此前 `测试集可行性分析.md` 已按
「候选的全部 gold 块都落在『含 ≥2 个不同事件日期』的文档内」这一**从严格口径**逐格统计，
发现**至少 3 个格子做不到**（事件型 1 跳 0、关系型 2 跳 0、关系型 1 跳仅 3）。

本次要回答的是**新问题**：两件事发生之后，哪些格子还是不够？
* 候选口径 `v1.3` 把「关系型 2 跳」的图结构上限由 16 个多公司事件抬到 **286** 个；
* `event_time` 补抽的**结构性上限**能把可过滤文档由 **66 篇**抬到 **240 篇**（乐观）。

## 口径（**复用** `交付物/03-代码\检索\build_questions.py` 的枚举器，不另立一套）

* 候选池：直接调用**冻结的** `build_questions.generate_candidates()`（6 个枚举器）；
  `交付物/03-代码\检索\` 是冻结目录、**只读不改**，本脚本只在**运行期**把
  `config.NODES_CSV` / `config.EDGES_CSV` 指向不同图谱导出目录，从而对同一套枚举器
  分别喂 v1.2 与 v1.3。
* 「可做时序型」：候选的**全部** `candidate_gold_chunk_ids` 都落在可过滤文档集合内
  （与该分析同一判据）。
* 「已被 30 题集占用」：候选的 gold 块与 30 题集的 gold 块**有交集**即算占用。

## 可过滤文档的三种情景

| 情景 | 文档集合 | 篇数 |
| --- | --- | --- |
| `NOW` | 已有 ≥2 个不同 `event_date` 的文档 | 66 |
| `OPT` | `NOW` ＋「佐证 ≥2 个事件但日期不足」的 A 类文档（＝补抽的**结构性上限**） | 240 |
| `REAL` | `NOW` ＋ A 类中按经验「同一天率」43.6% 折算后的部分 | ≈164（**按比例内插，非具体集合**） |

`REAL` 不是一个确定的文档集合（取决于补抽实际填出什么日期），故**只用于对照内插**；
判定「某格是否可达」以 **`OPT` 为准**——`OPT` 都到不了，补抽就一定到不了。

## 用法

    python "交付物/06-实验与评测\工具\统计分格可时序候选.py"
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import os
import sys

# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\工具\` 整体移到
# `交付物/06-实验与评测\工具\`（**下移一层**），求 ROOT 的上溯次数 3 → 4。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
G_V12 = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")
G_V13 = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_3")

# 只读导入冻结的检索侧模块。**导入顺序有讲究**：`交付物/03-代码\数据准备\config.py` 与
# `交付物/03-代码\检索\config.py` 同名，后插者胜出；本脚本要的是**检索侧**那一份。
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "数据准备"))
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "检索"))
import build_questions as BQ          # noqa: E402  （冻结；只调用、不修改）

CELLS = [("事实型", 0), ("事实型", 1), ("事实型", 2),
         ("事件型", 0), ("事件型", 1), ("事件型", 2),
         ("关系型", 0), ("关系型", 1), ("关系型", 2)]
KIND_BY_CELL = {("事实型", 0): "document_fact", ("事件型", 0): "event_fact",
                ("事实型", 2): "event_to_org_or_policy", ("事件型", 1): "company_event_set",
                ("关系型", 1): "company_person_set", ("关系型", 2): "co_participation_event"}


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def doc_date_and_event_maps(graph_dir):
    """从图谱导出物算两个文档集合：NOW（≥2 个不同日期）与 A 类（≥2 事件但日期不足）。

    ⚠️ **文档 id 必须归一成 int**：`nodes.csv` 的 `node_id` 是字符串（Document 节点形如 `"1001"`），
    而 `chunks.jsonl` 的 `doc_id` 是整数。不做归一的话集合求交恒为空、`time_*` 会全变 0
    （本脚本首版就踩了这个坑）。
    """
    nodes = {r["node_id"]: r for r in read_csv_rows(os.path.join(graph_dir, "nodes.csv"))}
    edges = read_csv_rows(os.path.join(graph_dir, "edges.csv"))
    doc_events = collections.defaultdict(set)
    for e in edges:
        if e.get("relation") != "EVIDENCED_BY":
            continue
        h, t = e.get("head_id"), e.get("tail_id")
        if nodes.get(h, {}).get("label") == "Event" and nodes.get(t, {}).get("label") == "Document":
            try:
                doc_events[int(t)].add(h)
            except (TypeError, ValueError):
                continue

    now, a_class = set(), set()
    for doc, evs in doc_events.items():
        dates = {(nodes[e].get("event_time") or "").strip() for e in evs}
        dates.discard("")
        if len(dates) >= 2:
            now.add(doc)
        elif len(evs) >= 2:
            a_class.add(doc)
    return now, a_class


def build_inputs(graph_dir):
    """把冻结模块的 config 指向指定图谱目录，再建 Inputs（**不改任何文件**）。"""
    BQ.config.NODES_CSV = os.path.join(graph_dir, "nodes.csv")
    BQ.config.EDGES_CSV = os.path.join(graph_dir, "edges.csv")
    return BQ.Inputs()


def cand_docs(cand, inputs):
    """候选的 gold 块落在哪些文档上。"""
    return {int(inputs.chunks[c]["doc_id"]) for c in cand["candidate_gold_chunk_ids"]
            if c in inputs.chunks}


def analyse(graph_dir, gold_all):
    inputs = build_inputs(graph_dir)
    cands = BQ.generate_candidates(inputs)
    now, a_class = doc_date_and_event_maps(graph_dir)
    opt = now | a_class

    rows = {}
    for cell in CELLS:
        rows[cell] = {"kind": KIND_BY_CELL.get(cell, "（无枚举器）"), "total": 0, "used": 0,
                      "unused": 0, "time_now": 0, "time_opt": 0}
    for c in cands:
        cell = (c["task_type"], c["gold_hop_depth"])
        if cell not in rows:
            continue
        r = rows[cell]
        r["total"] += 1
        docs = cand_docs(c, inputs)
        # 「已被 30 题集占用」＝候选的 gold 块与**全部 30 题**的 gold 块有交集
        # （不是只跟自己那一格比——首版按格比只得到个位数，与已发布的 38／46／… 对不上）。
        used = bool(set(c["candidate_gold_chunk_ids"]) & gold_all)
        if used:
            r["used"] += 1
        else:
            r["unused"] += 1
            if docs and docs <= now:
                r["time_now"] += 1
            if docs and docs <= opt:
                r["time_opt"] += 1
    return {"rows": rows, "docs_now": len(now), "docs_a_class": len(a_class),
            "docs_opt": len(opt), "cand_total": len(cands)}


def main() -> int:
    ap = argparse.ArgumentParser(description="9 格可时序型候选统计（只读）")
    ap.add_argument("--json", default=None, help="把结果写成 JSON")
    args = ap.parse_args()

    qpath = BQ.config.QUESTION_FILES["questions"]
    qs = [json.loads(l) for l in open(qpath, encoding="utf-8") if l.strip()]
    gold_all = set()
    for q in qs:
        gold_all.update(q["gold_evidence_chunk_ids"])

    res = {}
    for tag, gdir in (("v1.2", G_V12), ("v1.3", G_V13)):
        print("=" * 100)
        print("图谱口径 %s（%s）" % (tag, os.path.relpath(gdir, ROOT)))
        print("=" * 100)
        a = analyse(gdir, gold_all)
        res[tag] = a
        print("  可过滤文档：NOW %d 篇；A 类（≥2 事件但日期不足）%d 篇；**OPT 上限 %d 篇**"
              % (a["docs_now"], a["docs_a_class"], a["docs_opt"]))
        print("  枚举器候选总数：%d" % a["cand_total"])
        print("")
        print("  %-14s %-22s %6s %6s %6s %9s %9s" %
              ("格子", "枚举器", "候选", "已用", "未用", "可时序NOW", "可时序OPT"))
        print("  " + "-" * 88)
        for cell in CELLS:
            r = a["rows"][cell]
            print("  %-14s %-22s %6d %6d %6d %9d %9d"
                  % ("%s+%d跳" % (cell[0], cell[1]), r["kind"], r["total"], r["used"],
                     r["unused"], r["time_now"], r["time_opt"]))
        print("")
        short = [c for c in CELLS if a["rows"][c]["time_opt"] < 6]
        print("  ⇒ **OPT 上限下仍凑不出 6 道时序题的格子**：%s"
              % ("、".join("%s+%d跳(有%d)" % (c[0], c[1], a["rows"][c]["time_opt"]) for c in short) or "无"))
        enum_short = [c for c in short if a["rows"][c]["kind"] != "（无枚举器）"]
        print("     其中**有枚举器**的：%s"
              % ("、".join("%s+%d跳(有%d)" % (c[0], c[1], a["rows"][c]["time_opt"])
                           for c in enum_short) or "无"))
        print("     （无枚举器的 3 格本就需手工构造，枚举器为 0 不代表不能出题；见可行性分析第二节注）")
        print("")

    if args.json:
        os.makedirs(os.path.dirname(os.path.abspath(args.json)), exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({t: {k: v for k, v in a.items() if k != "rows"} |
                       {"rows": {"%s+%d跳" % (c[0], c[1]): a["rows"][c] for c in CELLS}}
                       for t, a in res.items()}, fh, ensure_ascii=False, indent=2, sort_keys=True)
        print("已写：%s" % os.path.relpath(args.json, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
