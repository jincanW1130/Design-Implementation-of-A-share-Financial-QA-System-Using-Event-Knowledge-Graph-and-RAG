# -*- coding: utf-8 -*-
"""工具\\实验_BM25离线对照.py —— 第 10 轮：BM25／字符 n-gram 与向量检索的**离线对照**。

口径（严格限定，先读）
----------------------
* 题集：30 题预实验集（`检索/config.py` 的 `QUESTION_FILES["questions"]`），**不改题、不改 gold**。
* 向量基线：现有 `VectorSearcher.search(question, 10)`（本地 bge-small-zh-v1.5 + FAISS），
  与正式链路使用的同一份索引；**只取 Top-10**，不经过图谱通道与五步裁剪。
* 词汇通道：`增强/lexical_search.py` 的纯 Python BM25（字符 1～3 n-gram），Top-10。
* RRF：向量 Top-20 ＋ 词汇 Top-20 融合后取 Top-10（**仅诊断**，不是产品链路）。
* 指标：`检索/metrics.py` 的 Recall@10、MRR；另行统计 Hit@1（首位即命中）、
  Hit@10（前 10 有命中）、Complete Evidence Recall@10 与首个 gold 的平均位次。
* **不调用大模型、不联网、不写数据库、不改默认实验口径**；结果只打印到 stdout。

用法::

    python 工具\\实验_BM25离线对照.py
    python 工具\\实验_BM25离线对照.py --ngram-min 1 --ngram-max 2
    # 第四轮：正式集（120 题，含 gold_evidence_chunk_ids）同口径复验
    python 工具\\实验_BM25离线对照.py --questions 交付物\\06-实验与评测\\测试集\\questions.jsonl --json <落盘路径>
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
ENHANCEMENT_DIR = os.path.join(ROOT, "交付物", "03-代码", "增强")
# 先插增强层、再插检索层：保证裸名 `import config` 命中**检索**组件（本脚本的唯一
# 参数来源），而 `import lexical_search` 仍能在检索层之后命中增强层。
if ENHANCEMENT_DIR not in sys.path:
    sys.path.insert(0, ENHANCEMENT_DIR)
if RETRIEVAL_DIR not in sys.path:
    sys.path.insert(0, RETRIEVAL_DIR)

import config            # noqa: E402  检索组件唯一参数来源
import metrics           # noqa: E402
import lexical_search    # noqa: E402  工程增强层（原 检索/lexical_search.py）
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
    parser.add_argument("--questions", default=config.QUESTION_FILES["questions"],
                        help="题集 JSONL（缺省为 30 题预实验集；正式集需含 gold_evidence_chunk_ids）")
    parser.add_argument("--json", default=None,
                        help="把平均值与逐题明细写入该 JSON 路径（缺省只打印）")
    args = parser.parse_args(argv)

    questions = load_jsonl(args.questions)
    missing_gold = [row.get("qid") for row in questions
                    if not (row.get("gold_evidence_chunk_ids") or [])]
    if missing_gold:
        print("[对照] 题集缺少 gold_evidence_chunk_ids（%d 题）：%s —— 无法计算检索指标，退出。"
              % (len(missing_gold), "、".join(str(q) for q in missing_gold[:10])))
        return 2
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
            "subset": row.get("subset"),
            "gold_count": len(gold),
            "vector_recall": vector_eval["recall_at_k"],
            "lexical_recall": lexical_eval["recall_at_k"],
            "hybrid_recall": hybrid_eval["recall_at_k"],
            "vector_first_rank": vector_eval["first_hit_rank"],
            "lexical_first_rank": lexical_eval["first_hit_rank"],
            "hybrid_first_rank": hybrid_eval["first_hit_rank"],
        })
    search_seconds = time.time() - t2

    def _summaries(rows_v, rows_l, rows_h):
        return [summarize("vector（现有基线）", rows_v),
                summarize("BM25（字符 n-gram）", rows_l),
                summarize("RRF（向量+BM25，诊断）", rows_h)]

    summaries = _summaries(vector_rows, lexical_rows, hybrid_rows)

    # 正式集带 `subset`（核心／压力）：压力子集单独报告，不并入核心平均。
    subsets = sorted({str(row.get("subset")) for row in questions if row.get("subset")})
    subset_summaries = {}
    for subset in subsets:
        idx = [i for i, row in enumerate(questions) if str(row.get("subset")) == subset]
        subset_summaries[subset] = _summaries(
            [vector_rows[i] for i in idx], [lexical_rows[i] for i in idx],
            [hybrid_rows[i] for i in idx])

    def _print_summaries(title, items):
        print("\n[结果] %s（K=%d；指标为 chunk 级，Complete 为问题级）" % (title, K))
        header = "%-24s %8s %8s %8s %8s %8s %8s" % (
            "system", "R@10", "MRR", "Complete", "Hit@1", "Hit@10", "首命中均位")
        print(header)
        print("-" * len(header))
        for item in items:
            first = item["first_hit_rank_mean_of_hits"]
            print("%-24s %8.4f %8.4f %8.4f %8.4f %8.4f %8s"
                  % (item["system"], item["recall_at_10"], item["mrr"],
                     item["complete_at_10"], item["hit_at_1"], item["hit_at_10"],
                     "-" if first is None else "%.2f" % first))

    _print_summaries("%d 题平均" % len(questions), summaries)
    for subset in subsets:
        n_sub = sum(1 for row in questions if str(row.get("subset")) == subset)
        _print_summaries("子集「%s」%d 题平均" % (subset, n_sub), subset_summaries[subset])

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
    print("[耗时] 词汇索引 %.2f s｜向量加载 %.2f s｜%d 题×两路检索 %.2f s"
          % (build_seconds, load_seconds, len(questions), search_seconds))

    if args.json:
        payload = {
            "generated_by": "工具/实验_BM25离线对照.py",
            "questions_file": os.path.relpath(args.questions, ROOT).replace("\\", "/"),
            "question_count": len(questions),
            "K": K, "N": N,
            "bm25": {"ngram_min": args.ngram_min, "ngram_max": args.ngram_max,
                     "k1": args.k1, "b": args.b},
            "rrf_k": args.rrf_k,
            "summaries": summaries,
            "subsets": {key: value for key, value in subset_summaries.items()},
            "engineering": {
                "tokens": len(index.postings),
                "postings": index.posting_count,
                "index_build_seconds": round(build_seconds, 2),
                "vector_model_load_seconds": round(load_seconds, 2),
                "search_seconds": round(search_seconds, 2),
                "tracemalloc_peak_mb": round(peak / 1024 / 1024, 2),
            },
            "detail": detail,
            "notes": [
                "离线诊断：向量侧独立 Top-10，不经过图谱通道／五步裁剪／证据排序",
                "零 LLM 调用、零联网、零写库；未改题集与默认 A～E 口径",
            ],
        }
        out_dir = os.path.dirname(os.path.abspath(args.json))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.json, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("[落盘] %s" % os.path.abspath(args.json))
    return 0


if __name__ == "__main__":
    sys.exit(main())
