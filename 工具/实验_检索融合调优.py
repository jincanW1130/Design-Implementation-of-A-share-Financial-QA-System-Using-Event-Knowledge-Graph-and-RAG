# -*- coding: utf-8 -*-
"""120 题正式集上的离线检索融合调优与 Flat/HNSW 对比。

实验只读输入：

* ``交付物/06-实验与评测/测试集/questions.jsonl``（120 题及 gold chunk ids）；
* ``数据集/v2.1/chunks/chunks.jsonl``（5018 块，构建内存 BM25）；
* ``数据集/v2.1/index/faiss.index``（现有 FlatIP，只读）；
* 本地缓存的 BGE ``BAAI/bge-small-zh-v1.5``；
* Graph v1.3 ``nodes.csv``（规则式查询扩展的实体别名来源）。

零 LLM 调用、零联网、零数据库写入。HNSW 索引只序列化到 ``TemporaryDirectory``，
退出时自动删除，不覆盖现有 FAISS 索引。输出固定落在
``交付物/05-系统实现/RAG检索系统/_工作底稿/检索融合调优_20261020.json``
或 ``--out`` 指定路径。

用法::

    python 工具/实验_检索融合调优.py
    python 工具/实验_检索融合调优.py --repeats 20 --bootstrap 10000
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import statistics
import sys
import tempfile
import time
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
RETRIEVAL_DIR = os.path.join(ROOT, "交付物", "03-代码", "检索")
ENHANCEMENT_DIR = os.path.join(ROOT, "交付物", "03-代码", "增强")
while RETRIEVAL_DIR in sys.path:
    sys.path.remove(RETRIEVAL_DIR)
while ENHANCEMENT_DIR in sys.path:
    sys.path.remove(ENHANCEMENT_DIR)
sys.path.insert(0, ENHANCEMENT_DIR)
sys.path.insert(0, RETRIEVAL_DIR)       # 裸名 config 必须命中检索侧

import config  # noqa: E402
import metrics  # noqa: E402
import vector_search  # noqa: E402
import hybrid_retrieval as hybrid  # noqa: E402
from lexical_search import LexicalIndex  # noqa: E402

K = int(config.RETRIEVAL["K"])
RETRIEVAL_K = int(config.RETRIEVAL["N"])
DEFAULT_QUESTIONS = os.path.join(
    ROOT, "交付物", "06-实验与评测", "测试集", "questions.jsonl")
DEFAULT_OUT = os.path.join(
    ROOT, "交付物", "05-系统实现", "RAG检索系统", "_工作底稿",
    "检索融合调优_20261020.json")

RRF_GRID_K = (10, 60, 100)
RRF_GRID_WEIGHTS = ((1, 1), (2, 1), (1, 2))
SCORE_GRID_MODES = ("minmax", "zscore")
SCORE_GRID_ALPHAS = (0.3, 0.5, 0.7)
EXPANSION_GRID = (False, True)
BOOTSTRAP_SEED = 20261020


def load_jsonl(path: str) -> list[dict]:
    """读取 UTF-8 JSONL，跳过空行。"""

    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def sha256_file(path: str) -> str:
    """分块计算文件 SHA-256，仅用于输入溯源。"""

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], probability: float) -> float:
    """线性插值分位数；空序列返回 0.0。"""

    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * float(probability)
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def first_gold_rank(ids: list[int], gold: list[int]) -> int | None:
    """返回首个 gold 的 1 起排名；前 K 无命中返回 None。"""

    gold_set = {int(value) for value in gold}
    for rank, chunk_id in enumerate(ids[:K], 1):
        if int(chunk_id) in gold_set:
            return rank
    return None


def evaluate_ids(ids: list[int], gold: list[int]) -> dict:
    """计算单题 R@10、MRR、Complete@10、Hit@1 与首个 gold 位次。"""

    top = [int(value) for value in ids[:K]]
    gold_ids = [int(value) for value in gold]
    rank = first_gold_rank(top, gold_ids)
    return {
        "recall_at_10": metrics.recall_at_k(top, gold_ids, K),
        "mrr": metrics.mrr(top, gold_ids),
        "complete_at_10": metrics.complete_evidence_recall_at_k(top, gold_ids, K),
        "hit_at_1": 1.0 if rank == 1 else 0.0,
        "first_gold_rank": rank,
    }


def summarize(name: str, details: list[dict], timings_ms: list[float],
              config_row: dict | None = None) -> dict:
    """聚合逐题指标与单题检索＋融合耗时 P50/P95。"""

    ranks = [row["first_gold_rank"] for row in details
             if row["first_gold_rank"] is not None]
    metrics_out = {
        "recall_at_10": round(statistics.fmean(row["recall_at_10"] for row in details), 6),
        "mrr": round(statistics.fmean(row["mrr"] for row in details), 6),
        "complete_at_10": round(
            statistics.fmean(row["complete_at_10"] for row in details), 6),
        "hit_at_1": round(statistics.fmean(row["hit_at_1"] for row in details), 6),
        "first_gold_rank_mean": round(statistics.fmean(ranks), 4) if ranks else None,
        "first_gold_hit_questions": len(ranks),
        "p50_ms": round(percentile(timings_ms, 0.50), 4),
        "p95_ms": round(percentile(timings_ms, 0.95), 4),
    }
    out = {
        "name": name,
        "question_count": len(details),
        "metrics": metrics_out,
        "details": details,
    }
    if config_row is not None:
        out["grid_parameters"] = config_row
    return out


def build_variant(
    label: str,
    expand: bool,
    questions: list[dict],
    searcher,
    lexical_index,
    alias_catalog,
) -> dict:
    """在一种查询扩展开关下预取两路 Top-N，并记录真实单题耗时。"""

    rows = []
    expanded_count = 0
    started = time.perf_counter()
    for question in questions:
        text = str(question["question"])
        t0 = time.perf_counter()
        query = hybrid.expand_query(
            text, enabled=expand, catalog=alias_catalog, max_terms=8)
        expansion_ms = (time.perf_counter() - t0) * 1000.0
        if query != text:
            expanded_count += 1

        t1 = time.perf_counter()
        vector_rows, _vector_timing = searcher.search(query, RETRIEVAL_K)
        vector_ms = (time.perf_counter() - t1) * 1000.0

        t2 = time.perf_counter()
        lexical_rows = lexical_index.search(query, RETRIEVAL_K)
        lexical_ms = (time.perf_counter() - t2) * 1000.0
        rows.append({
            "query": query,
            "vector": list(vector_rows),
            "lexical": list(lexical_rows),
            "expansion_ms": expansion_ms,
            "vector_ms": vector_ms,
            "lexical_ms": lexical_ms,
        })
    return {
        "label": label,
        "expand": bool(expand),
        "expanded_question_count": expanded_count,
        "prepare_seconds": round(time.perf_counter() - started, 4),
        "rows": rows,
    }


def grid_configs() -> list[dict]:
    """返回全部 30 个融合配置：15 个融合组合 × 扩展开/关。"""

    configs = []
    for expand in EXPANSION_GRID:
        suffix = "on" if expand else "off"
        for rrf_k in RRF_GRID_K:
            for weights in RRF_GRID_WEIGHTS:
                configs.append({
                    "config_id": "rrf-k%d-w%d-%d-exp-%s"
                                 % (rrf_k, weights[0], weights[1], suffix),
                    "family": "rrf",
                    "rrf_k": rrf_k,
                    "weights": list(weights),
                    "expand": expand,
                })
        for mode in SCORE_GRID_MODES:
            for alpha in SCORE_GRID_ALPHAS:
                configs.append({
                    "config_id": "%s-a%.1f-exp-%s" % (mode, alpha, suffix),
                    "family": mode,
                    "alpha": alpha,
                    "expand": expand,
                })
    return configs


def run_grid(
    questions: list[dict],
    variants: dict[str, dict],
    configs: list[dict],
) -> list[dict]:
    """执行全部网格；计时含该配置使用的两路检索与融合，不含一次性建索引/载模。"""

    results = []
    for config_row in configs:
        variant = variants["on" if config_row["expand"] else "off"]
        details, timings = [], []
        for question, prepared in zip(questions, variant["rows"]):
            t0 = time.perf_counter()
            if config_row["family"] == "rrf":
                fused = hybrid.rrf(
                    {"vector": prepared["vector"], "lexical": prepared["lexical"]},
                    k=config_row["rrf_k"],
                    weights=tuple(config_row["weights"]),
                )
            else:
                fused = hybrid.score_fusion(
                    prepared["vector"], prepared["lexical"],
                    mode=config_row["family"],
                    alpha=config_row["alpha"],
                )
            fusion_ms = (time.perf_counter() - t0) * 1000.0
            ids = [int(row["chunk_id"]) for row in fused[:K]]
            details.append(evaluate_ids(ids, question["gold_evidence_chunk_ids"]))
            timings.append(
                prepared["expansion_ms"] + prepared["vector_ms"]
                + prepared["lexical_ms"] + fusion_ms)
        results.append(summarize(
            config_row["config_id"], details, timings, config_row))
    return results


def baseline_results(
    questions: list[dict],
    variants: dict[str, dict],
) -> dict[str, dict]:
    """计算向量、BM25 与现有 RRF-60 三个对照。"""

    off = variants["off"]
    vector_details, vector_times = [], []
    lexical_details, lexical_times = [], []
    rrf_details, rrf_times = [], []
    for question, prepared in zip(questions, off["rows"]):
        vector_ids = [int(row["chunk_id"]) for row in prepared["vector"][:K]]
        lexical_ids = [int(row["chunk_id"]) for row in prepared["lexical"][:K]]
        t0 = time.perf_counter()
        fused = hybrid.rrf(
            {"vector": prepared["vector"], "lexical": prepared["lexical"]},
            k=60, weights=(1, 1))
        fusion_ms = (time.perf_counter() - t0) * 1000.0
        rrf_ids = [int(row["chunk_id"]) for row in fused[:K]]
        gold = question["gold_evidence_chunk_ids"]
        vector_details.append(evaluate_ids(vector_ids, gold))
        lexical_details.append(evaluate_ids(lexical_ids, gold))
        rrf_details.append(evaluate_ids(rrf_ids, gold))
        vector_times.append(prepared["vector_ms"])
        lexical_times.append(prepared["lexical_ms"])
        rrf_times.append(
            prepared["vector_ms"] + prepared["lexical_ms"] + fusion_ms)
    return {
        "vector": summarize("vector-flatip", vector_details, vector_times),
        "bm25": summarize("bm25-char-1to3", lexical_details, lexical_times),
        "rrf_60": summarize("rrf-k60-equal-weight", rrf_details, rrf_times),
    }


def paired_bootstrap(
    left: list[float],
    right: list[float],
    seed: int,
    samples: int,
) -> dict:
    """配对 bootstrap：对逐题差值有放回抽样，报告均值和 95% 百分位 CI。"""

    deltas = [float(a) - float(b) for a, b in zip(left, right)]
    if not deltas:
        return {
            "n_pairs": 0,
            "mean_delta": 0.0,
            "ci95_low": 0.0,
            "ci95_high": 0.0,
            "significant_95": False,
        }
    rng = random.Random(int(seed))
    n = len(deltas)
    means = []
    for _ in range(int(samples)):
        total = 0.0
        for _ in range(n):
            total += deltas[rng.randrange(n)]
        means.append(total / n)
    means.sort()
    low = percentile(means, 0.025)
    high = percentile(means, 0.975)
    return {
        "n_pairs": n,
        "mean_delta": round(statistics.fmean(deltas), 8),
        "ci95_low": round(low, 8),
        "ci95_high": round(high, 8),
        "significant_95": bool(low > 0.0 or high < 0.0),
        "bootstrap_samples": int(samples),
        "seed": int(seed),
    }


def two_sided_sign_test(wins: int, losses: int) -> float:
    """精确二项符号检验（H0: wins=losses），ties 不进入分母。"""

    n = int(wins) + int(losses)
    if n == 0:
        return 1.0
    tail = min(int(wins), int(losses))
    probability = sum(math.comb(n, index) for index in range(tail + 1)) / (2 ** n)
    return min(1.0, 2.0 * probability)


def compare_significance(
    best: dict,
    baselines: dict[str, dict],
    bootstrap_samples: int,
) -> dict:
    """最优网格配置对三个基线的配对 bootstrap 与 R@10 符号检验。"""

    comparisons = {}
    metric_keys = ("recall_at_10", "mrr", "complete_at_10", "hit_at_1")
    for baseline_name, baseline in baselines.items():
        metric_rows = {}
        for metric_key in metric_keys:
            left = [float(row[metric_key]) for row in best["details"]]
            right = [float(row[metric_key]) for row in baseline["details"]]
            metric_rows[metric_key] = paired_bootstrap(
                left, right, BOOTSTRAP_SEED, bootstrap_samples)
        wins = ties = losses = 0
        for best_row, base_row in zip(best["details"], baseline["details"]):
            if best_row["recall_at_10"] > base_row["recall_at_10"]:
                wins += 1
            elif best_row["recall_at_10"] < base_row["recall_at_10"]:
                losses += 1
            else:
                ties += 1
        comparisons[baseline_name] = {
            "metrics": metric_rows,
            "recall_at_10_sign_test": {
                "wins": wins,
                "ties": ties,
                "losses": losses,
                "two_sided_p_value": round(two_sided_sign_test(wins, losses), 8),
            },
        }
    return comparisons


def subset_summary(
    details: list[dict],
    questions: list[dict],
    subset: str,
    timings_ms: list[float] | None = None,
) -> dict:
    """按正式题集的 core/stress 标签给聚合指标做补充拆分。"""

    indices = [
        index for index, question in enumerate(questions)
        if str(question.get("subset") or "") == subset
    ]
    if not indices:
        return {"n_questions": 0}
    rows = [details[index] for index in indices]
    out = {
        "n_questions": len(rows),
        "recall_at_10": round(
            statistics.fmean(row["recall_at_10"] for row in rows), 6),
        "mrr": round(statistics.fmean(row["mrr"] for row in rows), 6),
        "complete_at_10": round(
            statistics.fmean(row["complete_at_10"] for row in rows), 6),
        "hit_at_1": round(statistics.fmean(row["hit_at_1"] for row in rows), 6),
    }
    if timings_ms is not None:
        subset_times = [timings_ms[index] for index in indices]
        out["p50_ms"] = round(percentile(subset_times, 0.50), 4)
        out["p95_ms"] = round(percentile(subset_times, 0.95), 4)
    return out


def load_vector_map() -> dict[int, int]:
    """读取 vector_id → chunk_id 只读映射。"""

    return {
        int(row["vector_id"]): int(row["chunk_id"])
        for row in load_jsonl(config.VECTOR_MAP_PATH)
    }


def search_ids(index, query_vectors, top_k: int) -> list[list[int]]:
    """对一组查询向量执行确定顺序的 top-k 检索，返回 vector_id 列表。"""

    out = []
    for query in query_vectors:
        _distances, ids = index.search(query.reshape(1, -1), int(top_k))
        out.append([int(value) for value in ids[0] if int(value) >= 0])
    return out


def timed_index_search(
    index,
    query_vectors,
    top_k: int,
    repeats: int,
) -> dict:
    """只计 ``index.search`` 的毫秒延迟，不含 BGE 编码。"""

    samples = []
    for _ in range(max(1, int(repeats))):
        for query in query_vectors:
            t0 = time.perf_counter()
            index.search(query.reshape(1, -1), int(top_k))
            samples.append((time.perf_counter() - t0) * 1000.0)
    return {
        "samples": len(samples),
        "p50_ms": round(percentile(samples, 0.50), 4),
        "p95_ms": round(percentile(samples, 0.95), 4),
        "mean_ms": round(statistics.fmean(samples), 4),
    }


def hnsw_comparison(
    flat_index,
    query_vectors,
    questions: list[dict],
    vector_to_chunk: dict[int, int],
    repeats: int,
) -> dict:
    """建 M=16/32、efSearch=64/128 的 HNSW 并对比 Flat；临时索引退出即删。"""

    import faiss
    import numpy as np

    faiss.omp_set_num_threads(1)
    ntotal, dim = int(flat_index.ntotal), int(flat_index.d)
    base = np.ascontiguousarray(
        flat_index.reconstruct_n(0, ntotal), dtype="float32")
    exact_ids = search_ids(flat_index, query_vectors, K)
    exact_gold = []
    for ids, question in zip(exact_ids, questions):
        chunks = {vector_to_chunk[vid] for vid in ids[:K]}
        exact_gold.append(bool(chunks & {int(x) for x in question["gold_evidence_chunk_ids"]}))
    flat_latency = timed_index_search(flat_index, query_vectors, K, repeats)

    results = [{
        "name": "FlatIP（现有默认，精确）",
        "hnsw_M": None,
        "efSearch": None,
        "efConstruction": None,
        "recall_consistency_at_10": 1.0,
        "recall_consistency_min": 1.0,
        "top10_exact_set_match_rate": 1.0,
        "gold_hit_at_10": round(statistics.fmean(exact_gold), 6),
        "index_bytes": int(faiss.serialize_index(flat_index).nbytes),
        "build_seconds": 0.0,
        "latency": flat_latency,
    }]

    temp_dir_path = ""
    with tempfile.TemporaryDirectory(prefix="rag_hnsw_") as temp_dir:
        temp_dir_path = temp_dir
        for hnsw_m in (16, 32):
            t0 = time.perf_counter()
            index = faiss.IndexHNSWFlat(dim, int(hnsw_m), faiss.METRIC_INNER_PRODUCT)
            index.hnsw.efConstruction = 200
            index.add(base)
            build_seconds = time.perf_counter() - t0
            for ef_search in (64, 128):
                index.hnsw.efSearch = int(ef_search)
                approx_ids = search_ids(index, query_vectors, K)
                overlaps = []
                exact_matches = []
                approx_gold = []
                for exact, approx, question in zip(exact_ids, approx_ids, questions):
                    overlaps.append(
                        len(set(exact[:K]) & set(approx[:K])) / float(K))
                    exact_matches.append(set(exact[:K]) == set(approx[:K]))
                    chunks = {vector_to_chunk[vid] for vid in approx[:K]}
                    approx_gold.append(bool(
                        chunks & {int(x) for x in question["gold_evidence_chunk_ids"]}))
                blob = faiss.serialize_index(index)
                file_name = "hnsw_M%d_ef%d.faiss" % (hnsw_m, ef_search)
                with open(os.path.join(temp_dir, file_name), "wb") as handle:
                    handle.write(blob.tobytes())
                results.append({
                    "name": "HNSW M=%d efSearch=%d" % (hnsw_m, ef_search),
                    "hnsw_M": int(hnsw_m),
                    "efSearch": int(ef_search),
                    "efConstruction": 200,
                    "recall_consistency_at_10": round(
                        statistics.fmean(overlaps), 6),
                    "recall_consistency_min": round(min(overlaps), 6),
                    "top10_exact_set_match_rate": round(
                        statistics.fmean(exact_matches), 6),
                    "gold_hit_at_10": round(statistics.fmean(approx_gold), 6),
                    "index_bytes": int(blob.nbytes),
                    "temporary_file_name": file_name,
                    "build_seconds": round(build_seconds, 4),
                    "latency": timed_index_search(
                        index, query_vectors, K, repeats),
                })
    temporary_cleaned = bool(temp_dir_path) and not os.path.exists(temp_dir_path)

    return {
        "definition": {
            "recall_consistency_at_10": "HNSW 与 FlatIP 的 Top-10 vector_id 集合交集 / 10，按题平均",
            "top10_exact_set_match_rate": "Top-10 vector_id 集合与 FlatIP 完全相同的题占比",
            "gold_hit_at_10": "Top-10 经 vector_map 映射后含任一 gold chunk 的题占比",
            "latency": "仅 index.search，不含 BGE 编码；CPU 单线程；重复 %d 轮" % repeats,
        },
        "temporary_index_directory": "TemporaryDirectory（自动删除）",
        "temporary_indexes_cleaned": bool(temporary_cleaned),
        "existing_flat_index_unchanged": True,
        "results": results,
    }


def selection_key(result: dict) -> tuple:
    """预登记的最优配置规则：R@10 → Complete → MRR → Hit@1 → P95 → 名称。"""

    metric = result["metrics"]
    return (
        -metric["recall_at_10"],
        -metric["complete_at_10"],
        -metric["mrr"],
        -metric["hit_at_1"],
        metric["p95_ms"],
        result["name"],
    )


def build_recommendation(
    best: dict,
    baselines: dict[str, dict],
    significance: dict,
) -> dict:
    """按预登记规则生成采用建议，明确 1pp 门槛与过拟合风险。"""

    best_recall = best["metrics"]["recall_at_10"]
    bm25_recall = baselines["bm25"]["metrics"]["recall_at_10"]
    delta_pp = (best_recall - bm25_recall) * 100.0
    comparison = significance["bm25"]["metrics"]["recall_at_10"]
    if delta_pp < 1.0:
        decision = "不显著、不建议采用"
        reason = "相对 BM25 单路的 R@10 提升不足 1 个百分点"
    elif not comparison["significant_95"]:
        decision = "不建议采用"
        reason = "R@10 提升达到 1pp，但配对 bootstrap 95% CI 跨 0"
    else:
        decision = "仅保留离线候选，不接入默认链路"
        reason = "正式集上显著，但网格在同一题集选择参数，存在模型选择偏差"
    return {
        "criterion": "先按 R@10，再按 Complete@10、MRR、Hit@1、较低 P95、配置名排序",
        "best_grid_config": best["name"],
        "best_grid_parameters": best.get("grid_parameters"),
        "best_grid_recall_at_10": best_recall,
        "bm25_recall_at_10": bm25_recall,
        "delta_vs_bm25_pp": round(delta_pp, 6),
        "bootstrap_95_ci_vs_bm25": [
            comparison["ci95_low"], comparison["ci95_high"]],
        "decision": decision,
        "reason": reason,
        "overfitting_warning": (
            "正式集大量题目直接复用公告标题、公司全称、精确数字与日期，字符 BM25 "
            "天然占优；本网格又在同一 120 题上选参，没有独立确认集，故任何提升都"
            "不能外推到开放问法或其它语料。"
        ),
        "default_link_status": "未接入默认检索链路与 /api/qa/ask",
    }


def print_grid(title: str, rows: list[dict]) -> None:
    """打印配置级均值表。"""

    print("\n[表] %s" % title)
    header = ("%-30s %7s %7s %7s %7s %8s %9s %9s"
              % ("config", "R@10", "MRR", "Comp10", "Hit@1", "首gold", "P50ms", "P95ms"))
    print(header)
    print("-" * len(header))
    for row in rows:
        metric = row["metrics"]
        first = metric["first_gold_rank_mean"]
        print("%-30s %7.4f %7.4f %7.4f %7.4f %8s %9.3f %9.3f"
              % (row["name"], metric["recall_at_10"], metric["mrr"],
                 metric["complete_at_10"], metric["hit_at_1"],
                 "-" if first is None else "%.2f" % first,
                 metric["p50_ms"], metric["p95_ms"]))


def main(argv=None) -> int:
    """执行完整网格、显著性、HNSW 对比并写 JSON。"""

    parser = argparse.ArgumentParser(description="120 题离线检索融合调优")
    parser.add_argument("--questions", default=DEFAULT_QUESTIONS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--repeats", type=int, default=10,
                        help="HNSW/Flat 查询延迟每题的重复轮数")
    parser.add_argument("--bootstrap", type=int, default=5000,
                        help="配对 bootstrap 重采样次数")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    questions = load_jsonl(args.questions)
    if len(questions) != 120:
        raise SystemExit("正式集应为 120 题，实际 %d 题：%s"
                         % (len(questions), args.questions))
    missing = [row.get("qid") for row in questions
               if not row.get("gold_evidence_chunk_ids")]
    if missing:
        raise SystemExit("存在空 gold 题，拒绝调优：%s" % "、".join(map(str, missing[:10])))

    chunks = load_jsonl(config.CHUNKS_PATH)
    print("[输入] 题集 %d｜语料 %d｜K=%d｜两路候选 N=%d"
          % (len(questions), len(chunks), K, RETRIEVAL_K))

    t0 = time.perf_counter()
    lexical_index = LexicalIndex.build(chunks)
    lexical_build_seconds = time.perf_counter() - t0
    print("[索引] BM25 token=%d posting=%d 构建 %.2fs（内存，不落盘）"
          % (len(lexical_index.postings), lexical_index.posting_count,
             lexical_build_seconds))

    t0 = time.perf_counter()
    searcher = vector_search.VectorSearcher(verbose=False)
    model_load_seconds = time.perf_counter() - t0
    print("[索引] 本地 BGE＋FlatIP 加载 %.2fs（只读 %s）"
          % (model_load_seconds, config.INDEX_PATH))

    t0 = time.perf_counter()
    alias_catalog = hybrid.load_alias_catalog()
    alias_load_seconds = time.perf_counter() - t0
    print("[扩展] 实体目录 %d 组、%d 个书写面；来源 nodes.csv v2.1_v1_3（只读）"
          % (len(alias_catalog.groups), len(alias_catalog.by_surface)))

    variants = {
        "off": build_variant(
            "expansion-off", False, questions, searcher, lexical_index, alias_catalog),
        "on": build_variant(
            "expansion-on", True, questions, searcher, lexical_index, alias_catalog),
    }
    print("[检索] 扩展 off/on 预取完成：expand on 改变 %d／%d 题"
          % (variants["on"]["expanded_question_count"], len(questions)))

    baselines = baseline_results(questions, variants)
    baseline_grid_rows = [baselines["vector"], baselines["bm25"], baselines["rrf_60"]]
    print_grid("基线（120 题，K=10）", baseline_grid_rows)

    configs = grid_configs()
    grid_rows = run_grid(questions, variants, configs)
    ordered = sorted(grid_rows, key=selection_key)
    print_grid("全网格 %d 配置（按预登记规则排序）" % len(ordered), ordered)
    best = ordered[0]
    significance = compare_significance(best, baselines, args.bootstrap)
    recommendation = build_recommendation(best, baselines, significance)

    subsets = {}
    for subset in ("核心", "压力"):
        subsets[subset] = {
            "vector": subset_summary(
                baselines["vector"]["details"], questions, subset),
            "bm25": subset_summary(
                baselines["bm25"]["details"], questions, subset),
            "rrf_60": subset_summary(
                baselines["rrf_60"]["details"], questions, subset),
            "best_grid": subset_summary(best["details"], questions, subset),
        }

    print("\n[最优网格] %s" % best["name"])
    for name in ("vector", "bm25", "rrf_60"):
        metric = baselines[name]["metrics"]
        comparison = significance[name]["metrics"]["recall_at_10"]
        sign = significance[name]["recall_at_10_sign_test"]
        print("  对 %-7s ΔR@10=%+.4f pp  bootstrap95%%CI=[%+.4f, %+.4f]  "
              "胜/平/负=%d/%d/%d p=%.4g"
              % (name, (best["metrics"]["recall_at_10"]
                        - metric["recall_at_10"]) * 100.0,
                 comparison["ci95_low"] * 100.0,
                 comparison["ci95_high"] * 100.0,
                 sign["wins"], sign["ties"], sign["losses"],
                 sign["two_sided_p_value"]))
    print("[采用建议] %s：%s" % (recommendation["decision"],
                               recommendation["reason"]))

    t0 = time.perf_counter()
    query_vectors = searcher.embedder.encode(
        [str(row["question"]) for row in questions])
    flat_index = config.read_faiss_index(config.INDEX_PATH)
    hnsw = hnsw_comparison(
        flat_index, query_vectors, questions, load_vector_map(), args.repeats)
    hnsw_seconds = time.perf_counter() - t0
    print("\n[表] Flat／HNSW 召回一致性与查询延迟（120 题，Top-10）")
    header = ("%-31s %10s %10s %10s %8s %9s %9s"
              % ("index", "一致率", "最低", "集合全同", "gold", "P50ms", "P95ms"))
    print(header)
    print("-" * len(header))
    for row in hnsw["results"]:
        print("%-31s %10.4f %10.4f %10.4f %8.4f %9.4f %9.4f"
              % (row["name"], row["recall_consistency_at_10"],
                 row["recall_consistency_min"], row["top10_exact_set_match_rate"],
                 row["gold_hit_at_10"], row["latency"]["p50_ms"],
                 row["latency"]["p95_ms"]))

    payload = {
        "schema": "retrieval-fusion-tuning/v1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": {
            "formal_questions": len(questions),
            "K": K,
            "retrieval_candidates_per_channel": RETRIEVAL_K,
            "fusion_grid_configs": len(grid_rows),
            "llm_api_calls": 0,
            "network_calls": 0,
            "database_writes": 0,
            "existing_vector_index_mode": "read-only",
        },
        "inputs": {
            "questions": {
                "path": os.path.relpath(args.questions, ROOT).replace("\\", "/"),
                "sha256": sha256_file(args.questions),
            },
            "chunks": {
                "path": os.path.relpath(config.CHUNKS_PATH, ROOT).replace("\\", "/"),
                "sha256": sha256_file(config.CHUNKS_PATH),
                "count": len(chunks),
            },
            "faiss_index": {
                "path": os.path.relpath(config.INDEX_PATH, ROOT).replace("\\", "/"),
                "sha256": sha256_file(config.INDEX_PATH),
            },
            "alias_source": {
                "path": os.path.relpath(alias_catalog.source, ROOT).replace("\\", "/"),
                "groups": len(alias_catalog.groups),
                "surfaces": len(alias_catalog.by_surface),
                "fields": [
                    "name", "stock_code", "company_name", "short_name", "aliases",
                ],
            },
        },
        "methodology": {
            "metrics": {
                "recall_at_10": "Top-10 命中的 gold 块数 / 该题 gold 块总数，按题平均",
                "mrr": "首个 gold 排名倒数，前 10 无命中记 0",
                "complete_at_10": "全部 gold 都在 Top-10 记 1，否则 0",
                "hit_at_1": "第 1 名是 gold 记 1，否则 0",
                "first_gold_rank_mean": "仅在 Top-10 至少命中一个 gold 的题上取平均",
            },
            "latency": "每配置逐题计时，含查询扩展、两路 Top-20 检索与融合；不含一次性 BM25 建索引和 BGE 载模",
            "significance": (
                "逐题配对差值的有放回 bootstrap（5000 次、seed=20261020）给出 "
                "95% 百分位 CI；CI 不含 0 才称显著；R@10 另做 ties 排除后的双侧精确符号检验"
            ),
            "best_selection_rule": (
                "网格结果按 R@10、Complete@10、MRR、Hit@1 降序，再按 P95 与配置名升序；"
                "该规则在看结果前固定"
            ),
        },
        "grid_spec": {
            "rrf_k": list(RRF_GRID_K),
            "rrf_weights": [list(item) for item in RRF_GRID_WEIGHTS],
            "score_modes": list(SCORE_GRID_MODES),
            "score_alphas": list(SCORE_GRID_ALPHAS),
            "query_expansion": ["off", "on"],
            "total_configs": len(grid_rows),
        },
        "baselines": baselines,
        "grid_results": ordered,
        "best_grid": best,
        "significance": significance,
        "subsets": subsets,
        "recommendation": recommendation,
        "hnsw_comparison": hnsw,
        "engineering": {
            "bm25_index_build_seconds": round(lexical_build_seconds, 4),
            "vector_model_load_seconds": round(model_load_seconds, 4),
            "alias_catalog_load_seconds": round(alias_load_seconds, 4),
            "hnsw_experiment_seconds": round(hnsw_seconds, 4),
            "total_seconds_before_write": round(time.perf_counter() - started, 4),
        },
        "notes": [
            "零大模型 API 调用；唯一模型是本地缓存的 BGE 查询编码。",
            "RRF-60 等权、扩展关闭的网格格与现有正式集基线完全同口径。",
            "正式集用于网格选参，没有独立确认集，存在模型选择偏差。",
            "题集大量复用标题、精确数字与公司全称，BM25 天然占优，结论不可外推。",
            "默认检索链路 /api/qa/ask 与检索/pipeline.py 未接入本模块。",
        ],
    }
    payload["engineering"]["total_seconds"] = round(
        time.perf_counter() - started, 4)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    print("\n[落盘] %s" % os.path.abspath(args.out))
    print("[边界] 未接入默认链路；未改现有 FAISS 索引；临时 HNSW 目录已删除=%s"
          % hnsw["temporary_indexes_cleaned"])
    print("[总耗时] %.2fs" % (time.perf_counter() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
