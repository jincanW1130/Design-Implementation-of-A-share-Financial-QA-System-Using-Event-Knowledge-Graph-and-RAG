# -*- coding: utf-8 -*-
"""代码\\检索\\check_inputs.py —— T1：读取与校验第 7 阶段的输入，产出**输入指纹清单**。

做三件事（《18》T1、验收第 2／3／4／5 行）：

1. 存在性与指纹：`阶段05-数据准备\\数据集\\v2.1\\` 的六个文件与
   `阶段06-事件抽取与知识图谱\\图谱导出\\v2.1_v1_2\\` 的五个文件逐个记 SHA-256；
2. 前提复核：把《18》第2.2节 表 18-A～18-D 的读数逐项重算（语料规模、索引三要素、
   三级映射、图谱规模与边分布、事件时间空值、证据可回溯、已知边界）；
3. 落盘 `阶段07-RAG检索系统\\检索产出\\input_manifest.json`：**不含任何时间戳**，
   同一份输入两次运行逐字节一致（T11 用它比对"输入只读"）。

退出码：全部通过 0；任一项不通过 1（并逐条打印 [FAIL]）。
用法：`python 代码\\检索\\check_inputs.py`
"""

from __future__ import annotations

import collections
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402


def main() -> int:
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print("  [%s] %s%s" % ("OK  " if ok else "FAIL", name,
                               ("  —— " + detail) if detail else ""))
        return ok

    print("=" * 78)
    print("T1 输入校验：数据集 %s ＋ 图谱导出物 %s" % (config.DATASET_VERSION, config.GRAPH_VERSION))
    print("=" * 78)

    # ---------------------------------------------------------------- 1 指纹
    print("\n一、存在性与指纹（%d 个输入文件）" % len(config.INPUT_FILES))
    files = []
    all_exist = True
    for key, path in config.INPUT_FILES:
        exists = os.path.isfile(path)
        all_exist = all_exist and exists
        if exists:
            digest = config.sha256_file(path)
            size = os.path.getsize(path)
            files.append({"key": key, "path": os.path.relpath(path, config.ROOT).replace("\\", "/"),
                          "sha256": digest, "bytes": size})
            print("  [OK  ] %-20s %s  %d B" % (key, digest[:16], size))
        else:
            files.append({"key": key, "path": os.path.relpath(path, config.ROOT).replace("\\", "/"),
                          "sha256": None, "bytes": None})
            print("  [FAIL] %-20s 缺失：%s" % (key, path))
    check("输入文件齐备（11 个）", all_exist, "缺 %d 个" % (0 if all_exist else
          sum(1 for f in files if f["sha256"] is None)))
    if not all_exist:
        print("\n结论：输入不齐备，无法开工。退出码 1。")
        return 1

    # ------------------------------------------------------------ 2 向量侧
    print("\n二、向量侧（表 18-A）")
    docs = list(config.iter_jsonl(config.DOCS_PATH))
    chunks = list(config.iter_jsonl(config.CHUNKS_PATH))
    vmap = list(config.iter_jsonl(config.VECTOR_MAP_PATH))
    check("文档数 = %d" % config.CORPUS["documents"], len(docs) == config.CORPUS["documents"],
          "实测 %d" % len(docs))
    check("文本块数 = %d" % config.CORPUS["chunks"], len(chunks) == config.CORPUS["chunks"],
          "实测 %d" % len(chunks))
    check("三级映射行数 = %d" % config.CORPUS["vectors"], len(vmap) == config.CORPUS["vectors"],
          "实测 %d" % len(vmap))

    vids = [int(r["vector_id"]) for r in vmap]
    check("vector_id 域恰为 0..%d" % (config.CORPUS["vectors"] - 1),
          sorted(vids) == list(range(config.CORPUS["vectors"])),
          "min=%d max=%d 唯一=%s" % (min(vids), max(vids), len(set(vids)) == len(vids)))

    # 双向可查：vector_id → chunk_id → doc_id；反向亦然
    chunk_by_id = {int(c["chunk_id"]): c for c in chunks}
    fwd_err, rev_err = 0, 0
    seen_chunks = set()
    for r in vmap:
        cid = int(r["chunk_id"])
        seen_chunks.add(cid)
        if cid not in chunk_by_id or int(chunk_by_id[cid]["doc_id"]) != int(r["doc_id"]):
            fwd_err += 1
    if len(seen_chunks) != len(chunks):
        rev_err = len(chunks) - len(seen_chunks)
    check("三级映射双向可查（正向错 0 ／反向漏 0）", fwd_err == 0 and rev_err == 0,
          "正向错 %d、反向漏 %d" % (fwd_err, rev_err))

    toks = [int(c["token_count"]) for c in chunks]
    check("token_count 区间 %d～%d" % (config.CORPUS["token_count_min"], config.CORPUS["token_count_max"]),
          min(toks) == config.CORPUS["token_count_min"] and max(toks) == config.CORPUS["token_count_max"],
          "实测 %d～%d" % (min(toks), max(toks)))
    check("token_count 合计 = %d" % config.CORPUS["token_count_total"],
          sum(toks) == config.CORPUS["token_count_total"], "实测 %d" % sum(toks))

    build_meta = config.read_json(config.BUILD_META_PATH)
    meta = config.read_json(config.DATASET_META_PATH)
    check("Embedding 模型名与 revision 与《02》第12.4节 一致",
          build_meta.get("model_name") == config.EMBEDDING["model_name"]
          and build_meta.get("model_revision") == config.EMBEDDING["revision"],
          "%s @ %s" % (build_meta.get("model_name"), str(build_meta.get("model_revision"))[:12]))
    check("dataset_version = %s" % config.DATASET_VERSION,
          meta.get("dataset_version") == config.DATASET_VERSION, str(meta.get("dataset_version")))
    check("data_cutoff_time = %s" % config.DATA_CUTOFF_TIME,
          meta.get("data_cutoff_time") == config.DATA_CUTOFF_TIME, str(meta.get("data_cutoff_time")))

    # ------------------------------------------------------------ 3 索引加载
    print("\n三、索引加载（字节流反序列化，不调用 read_index）")
    index_info = {}
    try:
        import faiss

        index = config.read_faiss_index(config.INDEX_PATH)
        index_info = {"ntotal": int(index.ntotal), "d": int(index.d),
                      "metric_type": int(index.metric_type),
                      "metric_name": ("inner_product"
                                      if index.metric_type == faiss.METRIC_INNER_PRODUCT else "other")}
        check("ntotal = %d" % config.CORPUS["vectors"], index.ntotal == config.CORPUS["vectors"],
              "实测 %d" % index.ntotal)
        check("d = %d" % config.EMBEDDING["dim"], index.d == config.EMBEDDING["dim"],
              "实测 %d" % index.d)
        # 注意：FAISS 的 METRIC_INNER_PRODUCT ＝ 0、METRIC_L2 ＝ 1，必须比常量而不是比字面量
        check("metric_type 为内积（METRIC_INNER_PRODUCT = %d）" % faiss.METRIC_INNER_PRODUCT,
              index.metric_type == faiss.METRIC_INNER_PRODUCT,
              "实测 %d" % index.metric_type)
    except Exception as exc:                                     # noqa: BLE001
        check("索引可加载", False, "%s: %s" % (type(exc).__name__, exc))

    # ------------------------------------------------------------ 4 图谱侧
    print("\n四、图谱侧（表 18-B／18-D）")
    with open(config.NODES_CSV, "r", encoding="utf-8", newline="") as f:
        nodes = list(csv.DictReader(f))
    with open(config.EDGES_CSV, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        edge_cols = list(reader.fieldnames or [])
        edges = list(reader)
    check("节点数 = %d" % config.GRAPH_SIZE["nodes"], len(nodes) == config.GRAPH_SIZE["nodes"],
          "实测 %d" % len(nodes))
    check("边数 = %d" % config.GRAPH_SIZE["edges"], len(edges) == config.GRAPH_SIZE["edges"],
          "实测 %d" % len(edges))
    check("边表恰好 %d 列且与 config.EDGE_COLUMNS 一致" % len(config.EDGE_COLUMNS),
          edge_cols == config.EDGE_COLUMNS, "实测 %s" % ",".join(edge_cols))

    labels = collections.Counter(n["label"] for n in nodes)
    rels = collections.Counter(e["relation"] for e in edges)
    check("节点标签都在本体 7 类内", set(labels) <= set(config.NODE_LABELS), str(sorted(labels)))
    check("关系名都在 9 条内", set(rels) <= set(config.RELATIONS), str(sorted(rels)))

    events = [n for n in nodes if n["label"] == "Event"]
    null_events = sum(1 for n in events if not (n.get("event_time") or "").strip())
    check("Event 节点数 = %d" % config.GRAPH_SIZE["events"], len(events) == config.GRAPH_SIZE["events"],
          "实测 %d" % len(events))
    check("event_time 为空 = %d" % config.GRAPH_SIZE["events_without_time"],
          null_events == config.GRAPH_SIZE["events_without_time"],
          "实测 %d（%.1f%%）——D／E 组时间过滤要剔除的规模" % (null_events, 100.0 * null_events / max(len(events), 1)))

    semantic = [e for e in edges if e["relation"] != config.EVIDENCED_BY]
    with_sc = [e for e in semantic if (e.get("source_chunk_id") or "").strip()]
    miss = [e for e in with_sc if int(e["source_chunk_id"]) not in chunk_by_id]
    mismatch = [e for e in with_sc if int(e["source_chunk_id"]) in chunk_by_id
                and int(chunk_by_id[int(e["source_chunk_id"])]["doc_id"]) != int(e["source_doc_id"])]
    check("语义边数 = %d 且全部带 source_chunk_id" % config.GRAPH_SIZE["semantic_edges"],
          len(semantic) == config.GRAPH_SIZE["semantic_edges"] and len(with_sc) == len(semantic),
          "语义边 %d、带 source_chunk_id %d" % (len(semantic), len(with_sc)))
    check("证据可回溯（未命中 0 ／ doc_id 不一致 0）", not miss and not mismatch,
          "未命中 %d、不一致 %d" % (len(miss), len(mismatch)))

    replay_lines = len(open(config.REPLAY_CYPHER, "r", encoding="utf-8").read().splitlines())
    check("replay.cypher 行数 = %d" % config.GRAPH_SIZE["replay_cypher_lines"],
          replay_lines == config.GRAPH_SIZE["replay_cypher_lines"], "实测 %d" % replay_lines)

    graph_stats = config.read_json(config.GRAPH_STATS_PATH)
    # v2.1_v1_2 的 graph_check 是**扁平**结构：{checks, passed, failed, failed_must, known_gaps}
    gcheck = graph_stats.get("graph_check") or {}
    check("图谱机检 checks=%d、passed=%d、failed_must 为空"
          % (config.GRAPH_SIZE["checks"], config.GRAPH_SIZE["checks_passed"]),
          gcheck.get("checks") == config.GRAPH_SIZE["checks"]
          and gcheck.get("passed") == config.GRAPH_SIZE["checks_passed"]
          and not gcheck.get("failed_must"),
          str(gcheck))

    # 已知边界（表 18-D）：只记录、不作判失败
    company_no_code = sum(1 for n in nodes if n["label"] == "Company"
                          and not (n.get("stock_code") or "").strip())
    belongs_to = [e for e in edges if e["relation"] == "BELONGS_TO"]
    belongs_to_dated = sum(1 for e in belongs_to if (e.get("valid_from") or "").strip())
    boundaries = {
        "supplies": rels.get("SUPPLIES", 0),
        "competes_with": rels.get("COMPETES_WITH", 0),
        "customer_of": rels.get("CUSTOMER_OF", 0),
        "company_nodes": labels.get("Company", 0),
        "company_nodes_without_stock_code": company_no_code,
        "belongs_to": len(belongs_to),
        "belongs_to_with_valid_from": belongs_to_dated,
        "isolated_nodes": (graph_stats.get("isolated_nodes") or {}).get("count"),
        "relations_skipped": (graph_stats.get("unresolved") or {}).get("relations_skipped"),
    }
    print("\n五、已知边界（只登记、不判失败；《16》第八节 与 表 18-D）")
    print("  " + config.stable_json(boundaries))

    # ------------------------------------------------------------ 落盘
    manifest = {
        "schema": "stage7-input-manifest-1.0",
        "generated_by": "代码/检索/check_inputs.py",
        "stage": "07-RAG检索系统",
        "dataset_version": config.DATASET_VERSION,
        "graph_version": config.GRAPH_VERSION,
        "data_cutoff_time": config.DATA_CUTOFF_TIME,
        "files": files,
        "index": index_info,
        "corpus": {"documents": len(docs), "chunks": len(chunks), "vectors": len(vmap),
                   "token_count_min": min(toks), "token_count_max": max(toks),
                   "token_count_total": sum(toks)},
        "graph": {"nodes": len(nodes), "edges": len(edges), "edge_columns": edge_cols,
                  "labels": dict(sorted(labels.items())),
                  "relations": dict(sorted(rels.items())),
                  "events": len(events), "events_without_time": null_events,
                  "semantic_edges": len(semantic),
                  "semantic_edges_with_source_chunk_id": len(with_sc),
                  "replay_cypher_lines": replay_lines,
                  "graph_check": gcheck},
        "boundaries": boundaries,
        "checks": checks,
        "all_ok": all(c["ok"] for c in checks),
    }
    config.write_json(config.INPUT_MANIFEST_PATH, manifest)
    print("\n指纹清单已落盘：%s" % os.path.relpath(config.INPUT_MANIFEST_PATH, config.ROOT))

    ok = manifest["all_ok"]
    passed = sum(1 for c in checks if c["ok"])
    print("\n检查项 %d，通过 %d，失败 %d" % (len(checks), passed, len(checks) - passed))
    print("结论：%s" % ("全部通过，输入就绪。" if ok else "存在失败项，不得开工。"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
