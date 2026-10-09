# -*- coding: utf-8 -*-
"""C 审查 —— 核对第 6 阶段登记的可过滤性与时间覆盖读数（只读，只写本产物目录）。"""
from __future__ import annotations

import io
import json
import os

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

BASE = os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "_全量", "v2.1_v1_2")


def main():
    os.makedirs(OUT, exist_ok=True)
    cov = json.load(io.open(os.path.join(BASE, "时间覆盖_度量.json"), encoding="utf-8"))
    payload = {
        "source_file": os.path.relpath(os.path.join(BASE, "时间覆盖_度量.json"), ROOT),
        "backfill": cov.get("backfill"),
        "extraction_layer_after_backfill": {
            "events": cov["extraction_layer_after_backfill"]["events"],
            "events_with_time": cov["extraction_layer_after_backfill"]["events_with_time"],
            "events_without_time": cov["extraction_layer_after_backfill"]["events_without_time"],
            "docs_with_ge2_dated_events": cov["extraction_layer_after_backfill"]["metrics"]["docs_with_ge2_dated_events"],
            "docs_times_span_more_than_one_month": cov["extraction_layer_after_backfill"]["metrics"]["docs_times_span_more_than_one_month"],
            "docs_times_span_ge_31_days": cov["extraction_layer_after_backfill"]["metrics"]["docs_times_span_ge_31_days"],
            "doc_ids_ge2_count": len(cov["extraction_layer_after_backfill"]["metrics"]["doc_ids_ge2"]),
            "doc_ids_multi_month_count": len(cov["extraction_layer_after_backfill"]["metrics"]["doc_ids_multi_month"]),
        },
    }
    graph_keys = [k for k in cov.keys() if "graph" in k]
    payload["top_level_keys"] = list(cov.keys())
    payload["graph_layer_keys"] = graph_keys
    for k in graph_keys:
        v = cov[k]
        if isinstance(v, dict):
            payload[k] = {
                "keys": list(v.keys())[:12],
                "events": v.get("events"),
                "events_with_time": v.get("events_with_time"),
                "events_without_time": v.get("events_without_time"),
            }
    with io.open(os.path.join(OUT, "raw_第6阶段度量核对.json"), "w",
                 encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])


if __name__ == "__main__":
    main()
