# -*- coding: utf-8 -*-
"""C 审查 —— 从图谱导出物复算第 6 阶段登记的关键读数（只读，只写本产物目录）。

复算项：节点标签分布、Event 的 event_time 空值数、Company 的 HCONF 节点数、
边按关系的分布、孤立节点、证据属性完整性与 §16 第八章登记的读数逐项对照。
"""
from __future__ import annotations

import csv
import io
import json
import os

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
GRAPH = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def rows(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            yield row


def main():
    node_rows = list(rows(os.path.join(GRAPH, "nodes.csv")))
    edge_rows = list(rows(os.path.join(GRAPH, "edges.csv")))

    by_label = {}
    for r in node_rows:
        by_label[r["label"]] = by_label.get(r["label"], 0) + 1

    event_nodes = [r for r in node_rows if r["label"] == "Event"]
    event_time_empty = sum(1 for r in event_nodes if not (r["event_time"] or "").strip())
    event_time_nonempty = len(event_nodes) - event_time_empty

    company_nodes = [r for r in node_rows if r["label"] == "Company"]
    hconf = [r for r in company_nodes if (r["node_id"] or "").startswith("HCONF-")]
    no_stock = [r for r in company_nodes if not (r["stock_code"] or "").strip()]

    by_relation = {}
    for r in edge_rows:
        by_relation[r["relation"]] = by_relation.get(r["relation"], 0) + 1

    # 证据属性完整性（除 EVIDENCED_BY 外 8 条关系）
    missing_evidence = 0
    for r in edge_rows:
        if r["relation"] == "EVIDENCED_BY":
            continue
        if not (r["source_doc_id"] or "").strip() or not (r["source_chunk_id"] or "").strip() \
                or not (r["confidence"] or "").strip():
            missing_evidence += 1
    evidenced_by_with_evidence = sum(
        1 for r in edge_rows if r["relation"] == "EVIDENCED_BY"
        and ((r["source_doc_id"] or "").strip() or (r["source_chunk_id"] or "").strip())
    )
    belongs_rows = [x for x in edge_rows if x["relation"] == "BELONGS_TO"]
    belongs_validity = {
        "BELONGS_TO_rows": len(belongs_rows),
        "BELONGS_TO_with_valid_from": sum(1 for x in belongs_rows if (x["valid_from"] or "").strip()),
        "BELONGS_TO_with_valid_to": sum(1 for x in belongs_rows if (x["valid_to"] or "").strip()),
    }
    roles = {}
    for r in edge_rows:
        if r["relation"] == "PARTICIPATES_IN":
            roles[r["role"]] = roles.get(r["role"], 0) + 1

    # 孤立节点：在边中既不作 head 也不作 tail
    used = set()
    for r in edge_rows:
        used.add(r["head_id"])
        used.add(r["tail_id"])
    isolated = [r["node_id"] for r in node_rows if r["node_id"] not in used]
    isolated_by_label = {}
    label_of = {r["node_id"]: r["label"] for r in node_rows}
    for nid in isolated:
        lab = label_of.get(nid, "?")
        isolated_by_label[lab] = isolated_by_label.get(lab, 0) + 1

    # chunk_id 是否真实存在于 v2.1 chunks.jsonl，且 doc_id 与 source_doc_id 一致
    chunk_owner = {}
    with io.open(os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl"),
                 encoding="utf-8") as fh:
        for line in fh:
            c = json.loads(line)
            chunk_owner[str(c["chunk_id"])] = c["doc_id"]
    src_chunks = [r for r in edge_rows if (r["source_chunk_id"] or "").strip()]
    unknown_chunk = [r for r in src_chunks if r["source_chunk_id"] not in chunk_owner]
    doc_mismatch = [r for r in src_chunks
                    if r["source_chunk_id"] in chunk_owner
                    and str(chunk_owner[r["source_chunk_id"]]) != str(r["source_doc_id"])]

    payload = {
        "nodes_total": len(node_rows),
        "nodes_by_label": by_label,
        "company_nodes": len(company_nodes),
        "hconf_company_nodes": len(hconf),
        "company_nodes_without_stock_code": len(no_stock),
        "event_nodes": len(event_nodes),
        "event_time_empty": event_time_empty,
        "event_time_nonempty": event_time_nonempty,
        "edges_total": len(edge_rows),
        "edges_by_relation": by_relation,
        "missing_evidence_attrs_except_evidenced_by": missing_evidence,
        "evidenced_by_rows_carrying_evidence_attrs": evidenced_by_with_evidence,
        "belongs_to_with_valid_from": belongs_validity,
        "participates_in_role_distribution": roles,
        "isolated_nodes": len(isolated),
        "isolated_nodes_by_label": isolated_by_label,
        "distinct_source_chunk_ids": len({r["source_chunk_id"] for r in src_chunks}),
        "source_chunk_id_unknown_in_v21": len(unknown_chunk),
        "source_doc_id_mismatch": len(doc_mismatch),
        "note_doc_id_0_edges": sum(1 for r in edge_rows if (r["source_doc_id"] or "").strip() == "0"),
    }
    dst = os.path.join(OUT, "raw_图谱导出_复算读数.json")
    with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
