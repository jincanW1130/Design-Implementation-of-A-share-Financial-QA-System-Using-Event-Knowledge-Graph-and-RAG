# -*- coding: utf-8 -*-
"""代码\\问答\\check_inputs.py —— T1：输入校验 ＋ 输入指纹清单。

产出 `交付物/05-系统实现/智能问答系统\\问答产出\\input_manifest.json`：

* 逐项记录《21》第三节 的八项输入（展开为 10 个文件）的 `path`／`bytes`／`sha256`／`mtime`
  （`mtime` 只作参考，**不参与比对**）；
* 核对实测规模（trace 30 行且 `group` 全为 `C`；`chunks` 5018、`documents` 709；
  图谱 `nodes.csv` 2802 行／`edges.csv` 2736 行，**口径＝不含表头**；`dataset_version`
  与 `data_cutoff_time` 的实测值）；
* 与第 7 阶段的 `检索产出\\input_manifest.json` **交叉对拍**（同一文件在两处的 `sha256`
  必须一致，按路径匹配；字段名不同则按路径归一化后匹配）；
* **任何规模不符即非零退出并打印证据。**

规模期望值一律取 `config.EXPECTED_SCALE`（源自 `代码\\检索\\config.py`），题量期望值由
题集自身行数推出——脚本内不写死数字（《21》第五节 硬约束 1）。
"""

from __future__ import annotations

import csv
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

SCHEMA = "stage8-input-manifest-1.0"


def _norm_rel(path: str) -> str:
    """相对 ROOT 的归一化路径（正斜杠、小写），供跨清单按路径匹配。"""
    rel = os.path.relpath(os.path.abspath(path), config.ROOT)
    return rel.replace("\\", "/").replace("/./", "/").lower()


def _count_text_lines(path: str) -> int:
    """按文本行计（含表头；不含文件末尾换行产生的空行）。"""
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for _ in f:
            n += 1
    return n


def _count_csv_data_rows(path: str) -> int:
    """CSV 的数据行数＝总行数 − 表头（按 csv 模块解析，避免手搓切分）。"""
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = sum(1 for _ in csv.reader(f))
    return rows - 1


def fingerprint(path: str) -> dict:
    st = os.stat(path)
    return {
        "path": path,
        "bytes": os.path.getsize(path),
        "sha256": config.sha256_file(path),
        "mtime": st.st_mtime,          # 只作参考，不参与比对（《21》第三节）
    }


def load_stage7_fingerprints() -> dict:
    """第 7 阶段清单里的 (归一化路径 → sha256)。字段名不同则按路径匹配。"""
    obj = config.read_json(config.INPUT_MANIFEST_PATH)
    out = {}
    for entry in obj.get("files") or []:
        p = entry.get("path")
        sha = entry.get("sha256")
        if isinstance(p, str) and isinstance(sha, str):
            out[_norm_rel(os.path.join(config.ROOT, p.replace("/", os.sep)))] = sha
    return out


def main() -> int:
    print("=" * 72)
    print("check_inputs.py —— 第 8 阶段 T1 输入校验与输入指纹清单")
    print("=" * 72)

    checks = []          # (名称, 是否通过, 证据)
    items = []           # 《21》第三节 的八项，每项挂若干文件
    failures = []

    def check(name, ok, detail):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print("  [%s] %-44s %s" % ("OK  " if ok else "FAIL", name, detail))
        if not ok:
            failures.append(name)

    # ---- 逐文件指纹：按《21》第三节 的八项分组（第 7 项是图谱导出物三件）----
    item_of = {
        "per_question_trace": 1, "stage7_input_manifest": 2, "stage7_run_manifest": 3,
        "documents": 4, "chunks": 5, "dataset_meta": 6,
        "nodes_csv": 7, "edges_csv": 7, "graph_stats": 7, "questions": 8,
    }
    missing = [k for k, p in config.INPUT_FILES if not os.path.isfile(p)]
    check("输入文件齐备（10 个，对应《21》第三节 八项）",
          not missing, "缺 %d 个%s" % (len(missing), ("：" + "、".join(missing)) if missing else ""))
    by_item = {}
    for key, path in config.INPUT_FILES:
        fp = fingerprint(path) if os.path.isfile(path) else {
            "path": path, "bytes": None, "sha256": None, "mtime": None}
        fp["key"] = key
        by_item.setdefault(item_of[key], []).append(fp)
    for item in sorted(by_item):
        items.append({"item": item, "files": by_item[item]})

    # ---- 实测规模 ----
    print("\n--- 实测规模核对（期望值取自 代码\\检索\\config.py）---")
    trace_rows = list(config.iter_jsonl(config.TRACE_PATH))
    question_rows = _count_text_lines(config.QUESTIONS_PATH)
    group_set = sorted({r.get("group") for r in trace_rows})
    check("trace 行数 = 题集行数（实测 %d）" % len(trace_rows),
          len(trace_rows) == question_rows,
          "trace=%d 题集=%d" % (len(trace_rows), question_rows))
    check("trace 的 group 全为 C", group_set == ["C"], "group 取值 = %s" % group_set)

    doc_rows = _count_text_lines(config.DOCUMENTS_PATH)
    chk_rows = _count_text_lines(config.CHUNKS_PATH)
    check("documents.jsonl = %d 行" % config.EXPECTED_SCALE["documents"],
          doc_rows == config.EXPECTED_SCALE["documents"], "实测 %d" % doc_rows)
    check("chunks.jsonl = %d 行" % config.EXPECTED_SCALE["chunks"],
          chk_rows == config.EXPECTED_SCALE["chunks"], "实测 %d" % chk_rows)

    nodes_all = _count_text_lines(config.NODES_CSV)
    edges_all = _count_text_lines(config.EDGES_CSV)
    nodes_data = _count_csv_data_rows(config.NODES_CSV)
    edges_data = _count_csv_data_rows(config.EDGES_CSV)
    check("nodes.csv = %d 行（不含表头）" % config.EXPECTED_SCALE["nodes_excl_header"],
          nodes_data == config.EXPECTED_SCALE["nodes_excl_header"],
          "总行 %d − 表头 1 = %d（数据行）" % (nodes_all, nodes_data))
    check("edges.csv = %d 行（不含表头）" % config.EXPECTED_SCALE["edges_excl_header"],
          edges_data == config.EXPECTED_SCALE["edges_excl_header"],
          "总行 %d − 表头 1 = %d（数据行）" % (edges_all, edges_data))

    meta = config.read_json(config.DATASET_META_PATH)
    ds_ver = meta.get("dataset_version")
    cutoff = meta.get("data_cutoff_time")
    check("dataset_version = %s" % config.DATASET_VERSION,
          ds_ver == config.DATASET_VERSION, "实测 %r" % ds_ver)
    check("data_cutoff_time = %s" % config.DATA_CUTOFF_TIME,
          cutoff == config.DATA_CUTOFF_TIME, "实测 %r" % cutoff)

    # ---- 与第 7 阶段清单交叉对拍 ----
    print("\n--- 与第 7 阶段 检索产出\\input_manifest.json 交叉对拍 ---")
    stage7 = load_stage7_fingerprints()
    ours = {}
    for key, path in config.INPUT_FILES:
        ours[_norm_rel(path)] = config.sha256_file(path)
    matched = sorted(set(ours) & set(stage7))
    mismatched = [p for p in matched if ours[p] != stage7[p]]
    check("同路径 sha256 在两处一致（对上了 %d 条）" % len(matched),
          not mismatched, "比对 %d 条，不一致 %d 条%s"
          % (len(matched), len(mismatched), ("：" + "、".join(mismatched)) if mismatched else ""))
    print("    对上的文件：%s" % "、".join(os.path.basename(p) for p in matched))
    print("    第 7 阶段清单共 %d 条指纹；本阶段八项里未在第 7 阶段登记的：%s"
          % (len(stage7), "、".join(os.path.basename(p) for p in sorted(set(ours) - set(stage7)))))

    # ---- 落盘 ----
    all_ok = not failures
    manifest = {
        "schema": SCHEMA,
        "stage": "第 8 阶段：智能问答系统",
        "purpose": "T1 输入指纹清单与只读基线（开工记一次，收工逐项重算比对）",
        "dataset_version": ds_ver,
        "data_cutoff_time": cutoff,
        "mtime_note": "mtime 只作参考，不参与比对（《21》第三节）",
        "graph_csv_scale_basis": "不含表头的数据行数（检索侧 config.GRAPH_SIZE 的登记口径）",
        "items": items,
        "checks": checks,
        "scale_measured": {
            "trace_rows": len(trace_rows),
            "questions_rows": question_rows,
            "trace_groups": group_set,
            "documents_rows": doc_rows,
            "chunks_rows": chk_rows,
            "nodes_csv_total_lines": nodes_all,
            "nodes_csv_data_rows": nodes_data,
            "edges_csv_total_lines": edges_all,
            "edges_csv_data_rows": edges_data,
            "dataset_version": ds_ver,
            "data_cutoff_time": cutoff,
        },
        "cross_check_stage7": {
            "manifest_path": config.INPUT_MANIFEST_PATH,
            "stage7_fingerprints": len(stage7),
            "matched_by_path": matched,
            "matched_count": len(matched),
            "mismatched": mismatched,
        },
        "all_ok": all_ok,
    }
    config.write_json(config.INPUT_MANIFEST_OUT_PATH, manifest)
    print("\n已写：%s" % config.INPUT_MANIFEST_OUT_PATH)
    print("检查项 %d 项，失败 %d 项；all_ok=%s"
          % (len(checks), len(failures), all_ok))
    print("=" * 72)
    if failures:
        print("规模不符，非零退出。失败项：%s" % "、".join(failures))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
