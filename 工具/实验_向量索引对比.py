# -*- coding: utf-8 -*-
"""工具\\实验_向量索引对比.py —— 第 6 轮：Flat／IVF-Flat／IVF-PQ／HNSW 离线实测。

**实验纪律**
------------
* 只在内存里**另建**近似索引做对比，**不写回数据集、不替换默认索引**；
  默认检索口径仍是 `IndexFlatIP`（5018×512，cosine）；
* 查询向量用 30 道预实验题经**同一份本地 BGE**（CLS 池化＋L2 归一化）编码，
  与线上检索同一口径；
* 评价两件事：
  1. **ANN Recall@10**：近似索引的 top-10 与 Flat 精确 top-10 的交集／10（30 题平均）；
  2. **Gold 命中率**：top-10 中是否含题集 gold 文本块（按 vector_map 从 vector_id 映射到
     chunk_id）——衡量近似是否损失业务召回；
* 查询耗时只计 `index.search()`，不含模型编码（编码在线上是每次提问一次，与索引类型无关）。

用法（仓库根目录）::

    python 工具\\实验_向量索引对比.py                 # 打印表并写默认 JSON
    python 工具\\实验_向量索引对比.py --out 路径.json
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
RETRIEVAL_DIR = os.path.join(ROOT, "交付物", "03-代码", "检索")
if RETRIEVAL_DIR not in sys.path:
    sys.path.insert(0, RETRIEVAL_DIR)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

import numpy as np  # noqa: E402

import config  # noqa: E402  （检索侧 config）
import vector_search  # noqa: E402

DEFAULT_OUT = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统/_工作底稿",
                           "向量索引对比_第6轮.json")
TOP_K = 10


def load_questions() -> list:
    path = config.QUESTION_FILES["questions"]
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return [r for r in rows if str(r.get("question") or "").strip()]


def load_vector_chunk_map() -> dict:
    out = {}
    with open(config.VECTOR_MAP_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                row = json.loads(line)
                out[int(row["vector_id"])] = int(row["chunk_id"])
    return out


def recall_at_k(exact_ids, approx_ids, k=TOP_K):
    return len(set(exact_ids[:k]) & set(approx_ids[:k])) / float(k)


def gold_hit(ids, gold, vmap, k=TOP_K):
    chunks = {vmap.get(int(i)) for i in ids[:k]}
    return bool(chunks & set(gold))


def timed_search(index, queries, repeats: int) -> dict:
    times = []
    for _ in range(repeats):
        for q in queries:
            t = time.perf_counter()
            index.search(q.reshape(1, -1), TOP_K)
            times.append((time.perf_counter() - t) * 1000.0)
    times.sort()
    q = lambda p: times[min(len(times) - 1, int(len(times) * p))]
    return {"n": len(times), "p50_ms": round(q(0.50), 4),
            "p95_ms": round(q(0.95), 4), "mean_ms": round(statistics.fmean(times), 4)}


def size_bytes(index) -> int:
    import faiss
    return int(faiss.serialize_index(index).nbytes)


def evaluate(name, index, queries, exact_ids, golds, vmap, repeats):
    ids = []
    for q in queries:
        _, got = index.search(q.reshape(1, -1), TOP_K)
        ids.append([int(x) for x in got[0]])
    recalls = [recall_at_k(e, g) for e, g in zip(exact_ids, ids)]
    golds_hit = [gold_hit(g, gold, vmap) for g, gold in zip(ids, golds)]
    return {
        "name": name,
        "recall_at_10_mean": round(statistics.fmean(recalls), 4),
        "recall_at_10_min": round(min(recalls), 4),
        "gold_hit_at_10": round(statistics.fmean(golds_hit), 4),
        "index_bytes": size_bytes(index),
        "latency": timed_search(index, queries, repeats),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Flat／IVF／HNSW 离线对比（只读数据集，不换默认索引）")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--repeats", type=int, default=20, help="每个配置对 30 题重复搜索的轮数")
    args = ap.parse_args()

    import faiss
    t0 = time.perf_counter()
    flat = config.read_faiss_index(config.INDEX_PATH)
    load_index_s = time.perf_counter() - t0
    ntotal, dim = flat.ntotal, flat.d
    base = np.ascontiguousarray(flat.reconstruct_n(0, ntotal), dtype="float32")
    print("[索引] Flat %d×%d，读取 %.3f s，类型=%s 度量=%s"
          % (ntotal, dim, load_index_s,
             type(flat).__name__, "IP(cosine)" if flat.metric_type == faiss.METRIC_INNER_PRODUCT else flat.metric_type))

    qs = load_questions()
    golds = [list(r.get("gold_evidence_chunk_ids") or []) for r in qs]
    vmap = load_vector_chunk_map()
    embedder = vector_search.LocalEmbedder(verbose=False)
    t0 = time.perf_counter()
    queries = embedder.encode([r["question"] for r in qs])
    encode_s = time.perf_counter() - t0
    print("[查询] %d 题编码 %.3f s（BGE %s）" % (len(qs), encode_s, embedder.model_name))

    exact_ids = []
    for q in queries:
        _, got = flat.search(q.reshape(1, -1), TOP_K)
        exact_ids.append([int(x) for x in got[0]])

    results = []
    t0 = time.perf_counter()
    results.append(evaluate("FlatIP（默认/精确基线）", flat, queries, exact_ids,
                            golds, vmap, args.repeats))
    flat_build_s = time.perf_counter() - t0

    # ---- IVF-Flat ---------------------------------------------------------
    nlist = 64
    ivf_build = {}
    t0 = time.perf_counter()
    quantizer = faiss.IndexFlatIP(dim)
    ivf = faiss.IndexIVFFlat(quantizer, dim, nlist, faiss.METRIC_INNER_PRODUCT)
    ivf.train(base)
    ivf.add(base)
    ivf_build["train+add_s"] = round(time.perf_counter() - t0, 4)
    for nprobe in (8, 16, 32):
        ivf.nprobe = nprobe
        row = evaluate("IVF-Flat nlist=%d nprobe=%d" % (nlist, nprobe), ivf, queries,
                       exact_ids, golds, vmap, args.repeats)
        row.update({"build_s": ivf_build["train+add_s"], "nlist": nlist, "nprobe": nprobe})
        results.append(row)

    # ---- IVF-PQ（32 子向量 × 8 bit，约 64 B/向量）--------------------------
    M, nbits = 32, 8
    t0 = time.perf_counter()
    quantizer = faiss.IndexFlatIP(dim)
    ivfpq = faiss.IndexIVFPQ(quantizer, dim, nlist, M, nbits, faiss.METRIC_INNER_PRODUCT)
    ivfpq.train(base)
    ivfpq.add(base)
    pq_build_s = round(time.perf_counter() - t0, 4)
    for nprobe in (8, 16, 32):
        ivfpq.nprobe = nprobe
        row = evaluate("IVF-PQ nlist=%d M=%d nbits=%d nprobe=%d" % (nlist, M, nbits, nprobe),
                       ivfpq, queries, exact_ids, golds, vmap, args.repeats)
        row.update({"build_s": pq_build_s, "nlist": nlist, "M": M, "nbits": nbits,
                    "nprobe": nprobe})
        results.append(row)

    # ---- HNSW -------------------------------------------------------------
    for ef_search in (32, 64, 128):
        t0 = time.perf_counter()
        hnsw = faiss.IndexHNSWFlat(dim, 32, faiss.METRIC_INNER_PRODUCT)
        hnsw.hnsw.efConstruction = 200
        hnsw.add(base)
        build_s = round(time.perf_counter() - t0, 4)
        hnsw.hnsw.efSearch = ef_search
        row = evaluate("HNSW M=32 efSearch=%d" % ef_search, hnsw, queries,
                       exact_ids, golds, vmap, args.repeats)
        row.update({"build_s": build_s, "hnsw_M": 32, "efConstruction": 200,
                    "efSearch": ef_search})
        results.append(row)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "environment": {
            "faiss": getattr(faiss, "__version__", "unknown"),
            "numpy": np.__version__,
            "python": sys.version.split()[0],
            "model_name": embedder.model_name,
            "model_revision": embedder.revision,
            "device": "cpu",
            "torch_num_threads": 1,
        },
        "corpus": {"ntotal": ntotal, "dim": dim,
                   "index_type": type(flat).__name__,
                   "metric": "inner_product(cosine on normalized vectors)",
                   "index_load_seconds": round(load_index_s, 4)},
        "queries": {"count": len(qs), "encode_seconds": round(encode_s, 4),
                    "top_k": TOP_K},
        "baseline_note": "ANN Recall@10 = 与 FlatIP 精确 top-10 的交集/10；gold_hit_at_10 = "
                         "top-10 含题集 gold 文本块的题占比。默认索引未被修改。",
        "results": results,
        "flat_eval_seconds": round(flat_build_s, 4),
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")

    print("\n%-46s %8s %8s %8s %10s %10s %12s"
          % ("index", "R@10", "R@10min", "gold", "p50 ms", "p95 ms", "bytes"))
    for r in results:
        print("%-46s %8.3f %8.3f %8.3f %10.4f %10.4f %12d"
              % (r["name"], r["recall_at_10_mean"], r["recall_at_10_min"],
                 r["gold_hit_at_10"], r["latency"]["p50_ms"], r["latency"]["p95_ms"],
                 r["index_bytes"]))
    print("\n结论 JSON：%s" % args.out)
    print("默认索引未改动：%s" % config.INDEX_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
