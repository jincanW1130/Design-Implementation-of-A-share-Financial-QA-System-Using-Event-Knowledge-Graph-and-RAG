# -*- coding: utf-8 -*-
"""工具\\实验_检索冷启动分解.py —— 第 6 轮：检索单题冷启动的测量与分解。

测量口径（全部只读，不改检索结果、不改默认架构）
------------------------------------------------
1. **端到端冷启动**：从仓库根目录 `subprocess` 启动 `检索\\run_query.py --qid PE-01`，
   记录「父进程墙钟」＝解释器启动＋导入＋加载模型＋检索＋落盘，并解析其自报的
   「总计／问题向量化／图谱查询／预算裁剪」耗时；
2. **阶段分解**：在独立子进程里按真实导入顺序逐段计时——
   `numpy/faiss` → 检索 config／vector_search／graph_query／pipeline → `load_pool`
   → `import torch` → `import transformers` → 模型权重加载 → 单题编码 → 全池排序；
3. **进程内复用（warm）**：同一进程只加载一次 `VectorSearcher`，连续检索同一题 N 次，
   给出首题与后续题的中位数——这是「常驻／预热进程」方案能拿到的收益上界。

用法（仓库根目录）::

    python 工具\\实验_检索冷启动分解.py
    python 工具\\实验_检索冷启动分解.py --runs 3 --out 自定义.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
RETRIEVAL_DIR = os.path.join(ROOT, "交付物", "03-代码", "检索")
RUN_QUERY = os.path.join(RETRIEVAL_DIR, "run_query.py")
DEFAULT_OUT = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统/_工作底稿",
                           "检索冷启动分解_第6轮.json")
QID = "PE-01"

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    return env


def run_end_to_end() -> dict:
    """启动一次 run_query.py（独立进程），返回墙钟与它自报的分项耗时。"""
    out_path = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统/_工作底稿",
                            "_冷启动探针_run_query.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, RUN_QUERY, "--qid", QID, "--out", out_path],
        cwd=ROOT, env=_env(), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=180)
    wall = time.perf_counter() - t0
    text = (proc.stdout or "") + (proc.stderr or "")
    total = re.search(r"总计\s*([0-9.]+)s", text)
    enc = re.search(r"问题向量化\s*([0-9.]+)s", text)
    graph = re.search(r"图谱查询\s*([0-9.]+)s", text)
    budget = re.search(r"预算裁剪\s*([0-9.]+)s", text)
    return {
        "returncode": proc.returncode,
        "outer_wall_seconds": round(wall, 4),
        "reported_total_seconds": float(total.group(1)) if total else None,
        "reported_encode_seconds": float(enc.group(1)) if enc else None,
        "reported_graph_seconds": float(graph.group(1)) if graph else None,
        "reported_budget_seconds": float(budget.group(1)) if budget else None,
    }


# 在独立子进程里逐段计时；只 import 与加载，不写任何文件。
_STAGE_CODE = r"""
import json, sys, time
sys.path.insert(0, r"{retrieval_dir}")
sys.dont_write_bytecode = True
marks = {{}}
t = time.perf_counter()
import numpy, faiss
marks["import_numpy_faiss"] = time.perf_counter() - t
t = time.perf_counter()
import config
marks["import_config"] = time.perf_counter() - t
t = time.perf_counter()
import vector_search
marks["import_vector_search"] = time.perf_counter() - t
t = time.perf_counter()
import graph_query, pipeline
marks["import_graph_pipeline"] = time.perf_counter() - t
t = time.perf_counter()
index, forward, backward, chunks = vector_search.load_pool()
marks["load_pool"] = time.perf_counter() - t
t = time.perf_counter()
import torch
marks["import_torch"] = time.perf_counter() - t
t = time.perf_counter()
from transformers import AutoModel, AutoTokenizer
marks["import_transformers"] = time.perf_counter() - t
t = time.perf_counter()
embedder = vector_search.LocalEmbedder(verbose=False)
marks["embedder_construct"] = time.perf_counter() - t
marks["tokenizer_plus_model_load"] = getattr(embedder, "load_seconds", None)
question = "长城汽车《2023年股票期权激励计划》首次授予股票期权第二个行权期的行权期有效期是什么时间段？"
t = time.perf_counter()
qvec = embedder.encode_query(question)
marks["encode_one_question"] = time.perf_counter() - t
t = time.perf_counter()
vector_search.rank_pairs(index, qvec, int(index.ntotal))
marks["rank_full_pool"] = time.perf_counter() - t
marks["ntotal"] = int(index.ntotal)
marks["dim"] = int(index.d)
print(json.dumps(marks, ensure_ascii=False))
"""


def run_stage_breakdown() -> dict:
    code = _STAGE_CODE.format(retrieval_dir=RETRIEVAL_DIR.replace("\\", "\\\\"))
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=_env(),
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=180)
    wall = time.perf_counter() - t0
    line = ""
    for candidate in reversed((proc.stdout or "").strip().splitlines()):
        if candidate.strip().startswith("{"):
            line = candidate.strip()
            break
    data = json.loads(line) if line else {}
    data["outer_wall_seconds"] = round(wall, 4)
    data["returncode"] = proc.returncode
    if proc.returncode != 0:
        data["stderr_tail"] = (proc.stderr or "")[-800:]
    return data


def run_warm_reuse(repeats: int = 12) -> dict:
    """同一进程内加载一次，连续检索；给出首题与后续题的分位耗时。"""
    if RETRIEVAL_DIR not in sys.path:
        sys.path.insert(0, RETRIEVAL_DIR)
    import vector_search  # noqa: E402

    question = ("长城汽车《2023年股票期权激励计划》首次授予股票期权第二个行权期的"
                "行权期有效期是什么时间段？")
    t0 = time.perf_counter()
    searcher = vector_search.VectorSearcher(verbose=False)
    load_s = time.perf_counter() - t0
    times = []
    for _ in range(repeats):
        t = time.perf_counter()
        searcher.search(question, 20)
        times.append((time.perf_counter() - t) * 1000.0)
    warm = sorted(times[1:])
    return {
        "load_once_seconds": round(load_s, 4),
        "first_query_ms": round(times[0], 3),
        "warm_queries": len(warm),
        "warm_p50_ms": round(warm[len(warm) // 2], 3),
        "warm_p95_ms": round(warm[min(len(warm) - 1, int(len(warm) * 0.95))], 3),
        "warm_mean_ms": round(statistics.fmean(warm), 3),
    }


def _median(values):
    vals = [v for v in values if isinstance(v, (int, float))]
    return round(statistics.median(vals), 4) if vals else None


def main() -> int:
    ap = argparse.ArgumentParser(description="检索单题冷启动测量与阶段分解（只读）")
    ap.add_argument("--runs", type=int, default=3, help="端到端冷启动与阶段分解各跑几次")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    e2e = [run_end_to_end() for _ in range(max(1, args.runs))]
    stages = [run_stage_breakdown() for _ in range(max(1, args.runs))]
    warm = run_warm_reuse()

    stage_keys = ["import_numpy_faiss", "import_config", "import_vector_search",
                  "import_graph_pipeline", "load_pool", "import_torch",
                  "import_transformers", "embedder_construct",
                  "tokenizer_plus_model_load", "encode_one_question", "rank_full_pool"]
    stage_medians = {k: _median([s.get(k) for s in stages]) for k in stage_keys}
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question_id": QID,
        "environment": {"python": sys.version.split()[0],
                        "platform": sys.platform,
                        "hf_offline": True},
        "end_to_end_runs": e2e,
        "end_to_end_outer_wall_median_seconds": _median(
            [r["outer_wall_seconds"] for r in e2e]),
        "end_to_end_reported_total_median_seconds": _median(
            [r["reported_total_seconds"] for r in e2e]),
        "stage_runs": stages,
        "stage_medians_seconds": stage_medians,
        "stage_sum_median_seconds": round(sum(v for v in stage_medians.values()
                                              if v is not None), 4),
        "warm_in_process": warm,
        "note": "只测量、不改检索结果；warm 为同进程复用 VectorSearcher 的收益上界。",
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print("端到端冷启动（%d 次）：墙钟中位 %.3f s，run_query 自报总计中位 %.3f s"
          % (len(e2e), payload["end_to_end_outer_wall_median_seconds"],
             payload["end_to_end_reported_total_median_seconds"] or 0))
    print("\n阶段分解（中位，秒）：")
    for k in stage_keys:
        v = stage_medians.get(k)
        print("  %-30s %s" % (k, "-" if v is None else "%.4f" % v))
    print("  %-30s %.4f" % ("合计", payload["stage_sum_median_seconds"]))
    print("\n同进程复用：一次性加载 %.3f s；首题 %.3f ms；后续 %d 题 p50 %.3f ms / p95 %.3f ms"
          % (warm["load_once_seconds"], warm["first_query_ms"], warm["warm_queries"],
             warm["warm_p50_ms"], warm["warm_p95_ms"]))
    print("\n结论 JSON：%s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
