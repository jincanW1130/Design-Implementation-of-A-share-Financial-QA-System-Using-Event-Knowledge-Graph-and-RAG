# -*- coding: utf-8 -*-
"""工具\\实验_BM25离线对照.py —— 第 10 轮：BM25／字符 n-gram 与向量检索的**离线对照**。

口径（严格限定，先读）
----------------------
* 题集：30 题预实验集（`检索/config.py` 的 `QUESTION_FILES["questions"]`），**不改题、不改 gold**。
* 向量基线：现有 `VectorSearcher.search(question, 10)`（本地 bge-small-zh-v1.5 + FAISS），
  与正式链路使用的同一份索引；**只取 Top-10**，不经过图谱通道与五步裁剪。
* 词汇通道：`检索/lexical_search.py` 的纯 Python BM25（字符 1～3 n-gram），Top-10。
* RRF：向量 Top-20 ＋ 词汇 Top-20 融合后取 Top-10（**仅诊断**，不是产品链路）。
* 指标：`检索/metrics.py` 的 Recall@10、MRR；另行统计 Hit@1（首位即命中）、
  Hit@10（前 10 有命中）、Complete Evidence Recall@10 与首个 gold 的平均位次。
* **不调用大模型、不联网、不写数据库、不改默认实验口径**；结果只打印到 stdout。

用法::

    python 工具\\实验_BM25离线对照.py
    python 工具\\实验_BM25离线对照.py --ngram-min 1 --ngram-max 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import tracemalloc

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # pragma: no cover
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
RETRIEVAL_DIR = os.path.join(ROOT, "交付物", "03-代码", "检索")
if RETRIEVAL_DIR not in sys.path:
    sys.path.insert(0, RETRIEVAL_DIR)

import config            # noqa: E402  检索组件唯一参数来源
import metrics           # noqa: E402
import lexical_search    # noqa: E402
from vector_search import VectorSearcher   # noqa: E402

K = int(config.RETRIEVAL["K"])
N = int(config.RETRIEVAL["N"])


def load_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def first_hit_rank(ids, gold):
    gold = {str(x) for x in gold}
    for rank, chunk_id in enumerate(ids[:K], 1):
        if str(chunk_id) in gold:
            return rank
    return None


def evaluate(ids, gold):
    ids = [int(x) for x in ids[:K]]
    gold = [int(x) for x in gold]
    rank = first_hit_rank(ids, gold)
    return {
        "recall_at_k": metrics.recall_at_k(ids, gold, K),
        "mrr": metrics.mrr(ids, gold),
        "complete_at_k": metrics.complete_evidence_recall_at_k(ids, gold, K),
        "hit_at_1": 1.0 if rank == 1 else 0.0,
        "hit_at_10": 1.0 if rank is not None else 0.0,
        "first_hit_rank": rank,
    }


def mean(rows, key):
    return sum(float(row[key]) for row in rows) / len(rows) if rows else 0.0


def summarize(name, rows):
    hit_ranks = [row["first_hit_rank"] for row in rows if row["first_hit_rank"] is not None]
    return {
        "system": name,
        "questions": len(rows),
        "recall_at_10": round(mean(rows, "recall_at_k"), 4),
        "mrr": round(mean(rows, "mrr"), 4),
        "complete_at_10": round(mean(rows, "complete_at_k"), 4),
        "hit_at_1": round(mean(rows, "hit_at_1"), 4),
        "hit_at_10": round(mean(rows, "hit_at_10"), 4),
        "first_hit_rank_mean_of_hits": (round(sum(hit_ranks) / len(hit_ranks), 2)
                                        if hit_ranks else None),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="BM25／字符 n-gram 与向量检索的离线对照")
    parser.add_argument("--ngram-min", type=int, default=1)
    parser.add_argument("--ngram-max", type=int, default=3)
    parser.add_argument("--k1", type=float, default=1.5)
    parser.add_argument("--b", type=float, default=0.75)
    parser.add_argument("--rrf-k", type=int, default=60)
    args = parser.parse_args(argv)

    questions = load_jsonl(config.QUESTION_FILES["questions"])
    chunks = load_jsonl(config.CHUNKS_PATH)
    print("[对照] 题集 %d 题｜语料 %d 块｜K=%d、N=%d｜BM25 n-gram=%d～%d、k1=%.2f、b=%.2f"
          % (len(questions), len(chunks), K, N, args.ngram_min, args.ngram_max,
             args.k1, args.b))

    # ---- 词汇索引（只读 chunks.jsonl；不落盘、不碰正式数据集）
    tracemalloc.start()
    t0 = time.time()
    index = lexical_search.LexicalIndex.build(
        chunks, ngram_min=args.ngram_min, ngram_max=args.ngram_max,
        k1=args.k1, b=args.b)
    build_seconds = time.time() - t0
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    print("[对照] 词汇索引：token 数 %d｜posting 数 %d｜构建 %.2f s｜tracemalloc 峰值 %.1f MB"
          % (len(index.postings), index.posting_count, build_seconds, peak / 1024 / 1024))

    # ---- 向量基线（加载本地模型，仅检索；不触发问答与图谱）
    t1 = time.time()
    searcher = VectorSearcher(verbose=False)
    load_seconds = time.time() - t1
    print("[对照] 向量模型加载 %.2f s" % load_seconds)

    vector_rows, lexical_rows, hybrid_rows, detail = [], [], [], []
    t2 = time.time()
    for row in questions:
        question, gold = row["question"], row["gold_evidence_chunk_ids"]
        vector_top20, _timings = searcher.search(question, N)
        lexical_top20 = index.search(question, N)
        fused = lexical_search.rrf_fuse(
            {"vector": vector_top20, "lexical": lexical_top20}, k_rrf=args.rrf_k)

        vector_ids = [item["chunk_id"] for item in vector_top20[:K]]
        lexical_ids = [item["chunk_id"] for item in lexical_top20[:K]]
        hybrid_ids = [item["chunk_id"] for item in fused[:K]]

        vector_eval = evaluate(vector_ids, gold)
        lexical_eval = evaluate(lexical_ids, gold)
        hybrid_eval = evaluate(hybrid_ids, gold)
        vector_rows.append(vector_eval)
        lexical_rows.append(lexical_eval)
        hybrid_rows.append(hybrid_eval)
        detail.append({
            "qid": row["qid"], "task_type": row.get("task_type"),
            "gold_count": len(gold),
            "vector_recall": vector_eval["recall_at_k"],
            "lexical_recall": lexical_eval["recall_at_k"],
            "hybrid_recall": hybrid_eval["recall_at_k"],
            "vector_first_rank": vector_eval["first_hit_rank"],
            "lexical_first_rank": lexical_eval["first_hit_rank"],
            "hybrid_first_rank": hybrid_eval["first_hit_rank"],
        })
    search_seconds = time.time() - t2

    summaries = [summarize("vector（现有基线）", vector_rows),
                 summarize("BM25（字符 n-gram）", lexical_rows),
                 summarize("RRF（向量+BM25，诊断）", hybrid_rows)]
    print("\n[结果] 30 题平均（K=%d；指标为 chunk 级，Complete 为问题级）" % K)
    header = "%-24s %8s %8s %8s %8s %8s %8s" % (
        "system", "R@10", "MRR", "Complete", "Hit@1", "Hit@10", "首命中均位")
    print(header)
    print("-" * len(header))
    for item in summaries:
        first = item["first_hit_rank_mean_of_hits"]
        print("%-24s %8.4f %8.4f %8.4f %8.4f %8.4f %8s"
              % (item["system"], item["recall_at_10"], item["mrr"],
                 item["complete_at_10"], item["hit_at_1"], item["hit_at_10"],
                 "-" if first is None else "%.2f" % first))

    wins = sum(1 for row in detail if row["lexical_recall"] > row["vector_recall"])
    ties = sum(1 for row in detail if row["lexical_recall"] == row["vector_recall"])
    losses = len(detail) - wins - ties
    print("\n[逐题 R@10] BM25 相对向量：胜 %d 题／平 %d 题／负 %d 题" % (wins, ties, losses))
    print("[逐题明细]")
    print("%-6s %-6s %5s %8s %8s %8s %8s %8s %8s" % (
        "qid", "题型", "gold", "vec_R", "lex_R", "hyb_R", "vec首", "lex首", "hyb首"))
    for row in detail:
        print("%-6s %-6s %5d %8.3f %8.3f %8.3f %8s %8s %8s" % (
            row["qid"], row["task_type"] or "-", row["gold_count"],
            row["vector_recall"], row["lexical_recall"], row["hybrid_recall"],
            "-" if row["vector_first_rank"] is None else row["vector_first_rank"],
            "-" if row["lexical_first_rank"] is None else row["lexical_first_rank"],
            "-" if row["hybrid_first_rank"] is None else row["hybrid_first_rank"]))

    print("\n[口径声明] 本实验为**离线诊断**：向量侧只取独立 Top-K，不经过图谱通道、五步裁剪、"
          "证据排序；未跑 LLM、未联网、未改题集与默认实验口径。结论不得直接外推为正式 A～E 组读数。")
    print("[耗时] 词汇索引 %.2f s｜向量加载 %.2f s｜60 次检索 %.2f s"
          % (build_seconds, load_seconds, search_seconds))
    return 0


if __name__ == "__main__":
    sys.exit(main())
