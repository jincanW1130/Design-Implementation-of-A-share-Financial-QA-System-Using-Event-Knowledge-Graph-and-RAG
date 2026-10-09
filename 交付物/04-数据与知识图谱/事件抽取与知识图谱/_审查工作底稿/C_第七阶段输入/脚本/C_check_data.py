# -*- coding: utf-8 -*-
"""C 审查 —— 实际数据与图谱导出物的字段核对（只读，只写本产物目录）。

产出：
  原始输出/raw_documents_前2行.txt
  原始输出/raw_chunks_前2行.txt
  原始输出/raw_字段核对_数据集.json
  原始输出/raw_图谱导出_表头与样例.txt
  原始输出/raw_replay_cypher_前若干行.txt
  原始输出/raw_图谱导出_结构核对.json
"""
from __future__ import annotations

import csv
import io
import json
import os

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

DS = os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1")
GRAPH = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def truncate(value, limit=200):
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + "…[截断，全长 %d 字符]" % len(value)
    if isinstance(value, list):
        return [truncate(v, limit) for v in value]
    if isinstance(value, dict):
        return {k: truncate(v, limit) for k, v in value.items()}
    return value


def read_first_lines(path, n):
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            if idx >= n:
                break
            rows.append(json.loads(line))
    return rows


def dump_jsonl_sample(name, path, n=2, limit=200):
    rows = read_first_lines(path, n)
    lines = []
    lines.append("文件：%s" % os.path.relpath(path, ROOT))
    lines.append("取样：前 %d 行（长文本按 %d 字符截断）" % (n, limit))
    lines.append("")
    for i, row in enumerate(rows, 1):
        lines.append("---- 第 %d 行：字段顺序（JSON 对象键序）----" % i)
        lines.append(" | ".join(row.keys()))
        lines.append("---- 第 %d 行：逐字段值（截断）----" % i)
        for k, v in row.items():
            lines.append("%s = %s" % (k, json.dumps(truncate(v, limit), ensure_ascii=False)))
        lines.append("")
    with io.open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return rows


def field_profile(rows):
    prof = []
    for row in rows:
        for k, v in row.items():
            entry = None
            for e in prof:
                if e["field"] == k:
                    entry = e
                    break
            if entry is None:
                entry = {"field": k, "types": [], "null_in_sample": 0, "sample_values": []}
                prof.append(entry)
            t = type(v).__name__
            if t not in entry["types"]:
                entry["types"].append(t)
            if v is None:
                entry["null_in_sample"] += 1
            elif len(entry["sample_values"]) < len(rows):
                entry["sample_values"].append(truncate(v, 120))
    return prof


def key_order(path):
    orders = {}
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            keys = tuple(json.loads(line).keys())
            orders[keys] = orders.get(keys, 0) + 1
    return [{"key_order": list(k), "rows": v} for k, v in orders.items()]


def main():
    os.makedirs(OUT, exist_ok=True)
    docs_path = os.path.join(DS, "clean", "documents.jsonl")
    chunks_path = os.path.join(DS, "chunks", "chunks.jsonl")

    docs = dump_jsonl_sample("raw_documents_前2行.txt", docs_path, 2)
    chunks = dump_jsonl_sample("raw_chunks_前2行.txt", chunks_path, 2)

    doc_orders = key_order(docs_path)
    chunk_orders = key_order(chunks_path)

    counts = {}
    with io.open(docs_path, encoding="utf-8") as fh:
        counts["documents_rows"] = sum(1 for _ in fh)
    with io.open(chunks_path, encoding="utf-8") as fh:
        counts["chunks_rows"] = sum(1 for _ in fh)
    with io.open(os.path.join(DS, "index", "vector_map.jsonl"), encoding="utf-8") as fh:
        counts["vector_map_rows"] = sum(1 for _ in fh)

    build_meta = json.load(io.open(os.path.join(DS, "index", "build_meta.json"), encoding="utf-8"))
    dataset_meta = json.load(io.open(os.path.join(DS, "meta", "dataset.json"), encoding="utf-8"))

    payload = {
        "documents_field_profile_first2": field_profile(docs),
        "chunks_field_profile_first2": field_profile(chunks),
        "documents_key_order_all_rows": doc_orders,
        "chunks_key_order_all_rows": chunk_orders,
        "row_counts": counts,
        "build_meta": truncate(build_meta, 400),
        "dataset_meta": truncate(dataset_meta, 400),
    }

    facts = {}
    with io.open(docs_path, encoding="utf-8") as fh:
        cats = {}
        for line in fh:
            row = json.loads(line)
            cats[row.get("category")] = cats.get(row.get("category"), 0) + 1
        facts["documents_by_category"] = cats
    with io.open(chunks_path, encoding="utf-8") as fh:
        null_vector = 0
        tmin = None
        tmax = None
        total_chunks = 0
        for line in fh:
            row = json.loads(line)
            total_chunks += 1
            if row.get("vector_id") is None:
                null_vector += 1
            tc = row.get("token_count")
            if isinstance(tc, int):
                tmin = tc if tmin is None else min(tmin, tc)
                tmax = tc if tmax is None else max(tmax, tc)
        facts["chunks_total"] = total_chunks
        facts["chunks_vector_id_null"] = null_vector
        facts["chunks_token_count_min"] = tmin
        facts["chunks_token_count_max"] = tmax
    payload["recomputed_facts"] = facts

    with io.open(os.path.join(OUT, "raw_字段核对_数据集.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    # ---- 图谱导出物 ----
    lines = []
    structure = {}
    for fname in ("nodes.csv", "edges.csv"):
        path = os.path.join(GRAPH, fname)
        with io.open(path, encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh)
            rows = [next(reader) for _ in range(6)]
        header = rows[0]
        samples = rows[1:]
        lines.append("=" * 100)
        lines.append("文件：%s" % os.path.relpath(path, ROOT))
        lines.append("表头（%d 列）：%s" % (len(header), " | ".join(header)))
        lines.append("")
        for i, row in enumerate(samples, 1):
            lines.append("---- 样例第 %d 行 ----" % i)
            for h, v in zip(header, row):
                lines.append("%s = %s" % (h, truncate(v, 160)))
            lines.append("")
        structure[fname] = {"columns": header, "n_columns": len(header), "sampled_rows": len(samples)}

    path = os.path.join(GRAPH, "replay.cypher")
    head = []
    total = 0
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            total += 1
            if total <= 40:
                head.append(line.rstrip("\n"))
    lines.append("=" * 100)
    lines.append("文件：%s　总行数 %d" % (os.path.relpath(path, ROOT), total))
    lines.append("前 40 行：")
    lines.extend(head)
    with io.open(os.path.join(OUT, "raw_图谱导出_表头与样例.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))

    with io.open(os.path.join(OUT, "raw_replay_cypher_前若干行.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 文件：%s\n# 总行数 %d\n\n" % (os.path.relpath(path, ROOT), total))
        fh.write("\n".join(head))
        fh.write("\n")

    stmt_kinds = {}
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("//"):
                continue
            key = s.split(" ")[0].upper()
            stmt_kinds[key] = stmt_kinds.get(key, 0) + 1
    structure["replay_cypher"] = {"total_lines": total, "leading_statement_kinds": stmt_kinds}

    gs = json.load(io.open(os.path.join(GRAPH, "graph_stats.json"), encoding="utf-8"))
    structure["graph_stats_top_level_keys"] = list(gs.keys())
    structure["graph_stats_counts"] = gs.get("counts")
    structure["graph_stats_files"] = gs.get("files")
    with io.open(os.path.join(OUT, "raw_图谱导出_结构核对.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(structure, fh, ensure_ascii=False, indent=2)

    print("[ok] documents 行数=%d　chunks 行数=%d　vector_map 行数=%d" % (
        counts["documents_rows"], counts["chunks_rows"], counts["vector_map_rows"]))
    print("[ok] documents 键序种类=%d　chunks 键序种类=%d" % (len(doc_orders), len(chunk_orders)))
    print("[ok] 图谱导出：nodes 列=%d　edges 列=%d　replay 行=%d" % (
        structure["nodes.csv"]["n_columns"], structure["edges.csv"]["n_columns"], total))


if __name__ == "__main__":
    main()
