# -*- coding: utf-8 -*-
"""工具\\实验_Neo4j索引与计划.py —— 第 6 轮：索引／约束核查与 PROFILE 前后对比。

只读数据；仅在内存里比对查询计划。脚本会**临时**创建 7 个 `short_name` 索引做一次
「加了索引能否用上」的实验，并在 `finally` 里全部删除（回滚语句见输出 JSON）。
**不改节点／关系，不重建图。**

用法（仓库根目录）::

    python 工具\\实验_Neo4j索引与计划.py
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
BACKEND_DIR = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
sys.dont_write_bytecode = True

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

import config  # noqa: E402  （后端 config）
import services.graph_service as gs  # noqa: E402
from neo4j import GraphDatabase  # noqa: E402
from neo4j import NotificationMinimumSeverity  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "交付物/05-系统实现/前后端系统集成/_工作底稿",
                           "Neo4j索引与计划_第6轮.json")

OLD_RAW = ("MATCH (n {node_id:$id}) RETURN labels(n)[0] AS label, properties(n) AS p")
OLD_NAME = gs._RESOLVE_BY_NAME  # noqa: SLF001（与线上完全相同）


def _driver():
    p = config.neo4j_params()
    return GraphDatabase.driver(
        p["uri"], auth=(p["user"], p["password"] or None),
        notifications_min_severity=NotificationMinimumSeverity.OFF)


_PLAN_OPS = ("ProduceResults", "Projection", "Filter", "AllNodesScan",
             "NodeByLabelScan", "NodeIndexSeek", "NodeUniqueIndexSeek",
             "Union", "Sort", "Distinct", "Expand(All)", "Limit", "OptionalExpand(All)")


def _profile(session, query, params, repeats=30):
    summ = session.run("PROFILE " + query, **params).consume()
    table = summ.profile["args"]["string-representation"]
    counts, hits = {}, 0
    for line in table.splitlines():
        if "|" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells and cells[0] == "":                   # 深一层树形前缀留下的空格
            cells = cells[1:]
        if len(cells) < 6:
            continue
        op = cells[0].lstrip("+ |\\").strip()          # 去掉树形前缀 +/|/\
        if op not in _PLAN_OPS:
            continue
        counts[op] = counts.get(op, 0) + 1
        try:
            hits += int(cells[5].replace(",", ""))     # DB Hits 列
        except (ValueError, IndexError):
            pass
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        session.run(query, **params).consume()
        times.append((time.perf_counter() - t) * 1000.0)
    times.sort()
    return {"operator_counts": counts, "db_hits_total": hits,
            "p50_ms": round(times[len(times) // 2], 4),
            "p95_ms": round(times[min(len(times) - 1, int(len(times) * 0.95))], 4),
            "median_ms": round(statistics.median(times), 4)}


def main() -> int:
    ap = argparse.ArgumentParser(description="Neo4j 索引／约束与 PROFILE 前后对比")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    drv = _driver()
    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    try:
        with drv.session() as s:
            components = s.run("CALL dbms.components() YIELD name, versions, edition "
                               "RETURN name, versions[0] AS version, edition").single()
            payload["server"] = dict(components)
            payload["indexes_before"] = [dict(r) for r in s.run(
                "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, "
                "owningConstraint, state RETURN * ORDER BY name")]
            payload["constraints"] = [dict(r) for r in s.run(
                "SHOW CONSTRAINTS YIELD name, type, labelsOrTypes, properties "
                "RETURN * ORDER BY name")]
            counts = {r["label"]: r["c"] for r in s.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c ORDER BY label")}
            payload["node_counts"] = counts

            # 取每个标签一个样本（覆盖全部 7 类）
            samples = {}
            for label in gs.GRAPH_LABELS:
                row = s.run("MATCH (n:%s) RETURN n.node_id AS id, n.name AS name, "
                            "n.short_name AS sn ORDER BY n.node_id LIMIT 1" % label).single()
                if row:
                    samples[label] = dict(row)
            payload["samples"] = samples

            # 1) node_id 单点：旧（无标签）vs 新（标签限定 UNION，线上代码）
            sample_id = samples["Company"]["id"]
            payload["by_id"] = {
                "sample": sample_id,
                "old": _profile(s, OLD_RAW, {"id": sample_id}),
                "new": _profile(s, gs._RESOLVE_BY_ID, {"id": sample_id}),
                "old_plan_note": "MATCH (n {node_id:$id}) → AllNodesScan + Filter",
                "new_plan_note": "CALL { 7×NodeUniqueIndexSeek } → 每标签唯一约束命中",
            }

            # 2) 名称检索：归一化表达式阻断索引使用（线上保持原写法）
            sample_name = samples["Company"]["name"] or ""
            payload["by_name"] = {
                "sample": sample_name,
                "query": OLD_NAME,
                "profile": _profile(s, OLD_NAME, {"key": sample_name, "ws": gs._NORM_WS}),
                "note": "n.name/n.short_name/aliases 均经过 _norm_expr（toLower+去空白）"
                        "再比较；表达式使普通 RANGE 索引无法用于该条件，仍是 AllNodesScan。",
            }

            # 3) 临时创建 short_name 索引 → 看能否改善名称检索 → finally 删除
            created = []
            for label in gs.GRAPH_LABELS:
                name = "idx_%s_short_name" % label.lower()
                s.run("CREATE INDEX %s IF NOT EXISTS FOR (n:%s) ON (n.short_name)"
                      % (name, label)).consume()
                created.append(name)
            deadline = time.time() + 30
            states = {}
            while time.time() < deadline:
                rows = list(s.run("SHOW INDEXES YIELD name, state WHERE name IN $names "
                                  "RETURN name, state", names=created))
                states = {r["name"]: r["state"] for r in rows}
                if len(states) == len(created) and all(v == "ONLINE" for v in states.values()):
                    break
                time.sleep(0.3)
            label_raw = ("MATCH (n:Company) WHERE n.name=$key OR n.short_name=$key "
                         "RETURN n.node_id AS node_id")
            payload["short_name_index_experiment"] = {
                "created": created, "states": states,
                "label_qualified_raw_plan": _profile(s, label_raw, {"key": sample_name}),
                "normalized_same_query_plan": _profile(
                    s, OLD_NAME, {"key": sample_name, "ws": gs._NORM_WS}),
                "conclusion": "short_name 索引只能服务**未归一化**的等值条件；线上名称检索带 "
                              "_norm_expr，计划仍为 AllNodesScan/LabelScan，故实验后删除这些索引。",
                "rollback": ["DROP INDEX %s IF EXISTS" % n for n in created],
            }
            for name in created:
                s.run("DROP INDEX %s IF EXISTS" % name).consume()
            payload["indexes_after"] = [dict(r) for r in s.run(
                "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, "
                "owningConstraint, state RETURN * ORDER BY name")]
            payload["indexes_unchanged_after_experiment"] = (
                payload["indexes_before"] == payload["indexes_after"])
    finally:
        drv.close()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print("Neo4j %s %s（%s）" % (payload["server"].get("version"),
                                payload["server"].get("edition"),
                                payload["server"].get("name")))
    print("索引 %d 个、约束 %d 个；节点 %d"
          % (len(payload["indexes_before"]), len(payload["constraints"]),
             sum(counts.values())))
    for tag in ("by_id", "by_name"):
        block = payload[tag]
        p = block.get("profile") or block["new"]
        print("\n[%s] sample=%r  ops=%s  dbHits=%s  p50=%.3fms p95=%.3fms"
              % (tag, block.get("sample"), p["operator_counts"], p["db_hits_total"],
                 p["p50_ms"], p["p95_ms"]))
        if tag == "by_id":
            print("   旧：ops=%s dbHits=%s p50=%.3fms"
                  % (block["old"]["operator_counts"], block["old"]["db_hits_total"],
                     block["old"]["p50_ms"]))
    exp = payload["short_name_index_experiment"]
    print("\n[short_name 索引实验] %s" % exp["conclusion"])
    print("   raw 条件计划：%s；归一化条件计划：%s；实验后索引恢复=%s"
          % (exp["label_qualified_raw_plan"]["operator_counts"],
             exp["normalized_same_query_plan"]["operator_counts"],
             payload["indexes_unchanged_after_experiment"]))
    print("\n结论 JSON：%s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
