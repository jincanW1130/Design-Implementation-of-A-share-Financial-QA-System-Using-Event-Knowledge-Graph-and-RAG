# -*- coding: utf-8 -*-
"""代码\\检索\\lexical_search.py —— 纯 Python BM25／字符 n-gram 词汇检索（第 10 轮新增）。

定位
----
本模块只用于**离线对照实验**：在 30 题预实验集上比较词汇通道与现有向量通道的
Recall@10／首条命中，并给出 RRF 融合的诊断读数。它**不接入默认检索链路**、
不修改 A～E 五组口径、不调用任何大模型／外部接口。

实现要点（零新增依赖，仅用标准库）
--------------------------------
* 分词：中文连续片段切 **1～3 字符滑窗**；英文／数字连续串整体转小写（股票代码
  `600519`、指标 `2026` 因此是强匹配的完整 token）。
* 索引：倒排表 `token -> array('I')`，每项编码为 `(块序号 << 10) | min(tf, 1023)`；
  用 `array` 而非 Python 元组列表，把 5018 块约 540 万条 posting 的常驻内存压到
  几十 MB 量级（实测见实验脚本输出）。
* 打分：标准 BM25（`k1=1.5`、`b=0.75`），IDF 采用 `log(1 + (N-df+0.5)/(df+0.5))`。
* 排序：分数降序、并列按 `chunk_id` 升序（确定性，便于复现）。

接口
----
    index = LexicalIndex.build(chunks)          # chunks: [{chunk_id, doc_id, content}, ...]
    rows = index.search("问题", n=10)           # [{chunk_id, doc_id, lexical_score, lexical_rank}]
    fused = rrf_fuse({"vector": rows_a, "lexical": rows_b}, k_rrf=60)
"""

from __future__ import annotations

import heapq
import math
import re
from array import array
from collections import Counter

_CJK_RE = re.compile(r"[一-鿿]+")
_ALNUM_RE = re.compile(r"[A-Za-z0-9]+")
_TF_BITS = 10
_TF_MAX = (1 << _TF_BITS) - 1


def tokenize(text, ngram_min: int = 1, ngram_max: int = 3) -> list:
    """中文按字符 n-gram、英文/数字按整串切分；空文本返回 `[]`。"""
    text = str(text or "")
    tokens = []
    for run in _CJK_RE.findall(text):
        for size in range(int(ngram_min), int(ngram_max) + 1):
            if size > len(run):
                break
            for start in range(len(run) - size + 1):
                tokens.append(run[start:start + size])
    for run in _ALNUM_RE.findall(text):
        tokens.append(run.lower())
    return tokens


class LexicalIndex:
    """内存倒排索引 + BM25 打分器（构建一次、可反复查询）。"""

    def __init__(self, postings, chunk_ids, doc_ids, lengths, k1=1.5, b=0.75,
                 ngram_min=1, ngram_max=3):
        self.postings = postings
        self.chunk_ids = list(chunk_ids)
        self.doc_ids = list(doc_ids)
        self.lengths = list(lengths)
        self.k1 = float(k1)
        self.b = float(b)
        self.ngram_min = int(ngram_min)
        self.ngram_max = int(ngram_max)
        self.total_chunks = len(self.chunk_ids)
        self.avgdl = (sum(self.lengths) / self.total_chunks) if self.total_chunks else 0.0
        self.posting_count = sum(len(p) for p in self.postings.values())

    @classmethod
    def build(cls, chunks, ngram_min: int = 1, ngram_max: int = 3,
              k1: float = 1.5, b: float = 0.75) -> "LexicalIndex":
        """从 `chunks.jsonl` 的行构建索引（只读 `chunk_id`／`doc_id`／`content`）。"""
        postings = {}
        chunk_ids, doc_ids, lengths = [], [], []
        for index, row in enumerate(chunks):
            text = str(row.get("content") or "")
            tokens = tokenize(text, ngram_min, ngram_max)
            chunk_ids.append(int(row["chunk_id"]))
            doc_ids.append(int(row["doc_id"]))
            lengths.append(len(tokens))
            for token, tf in Counter(tokens).items():
                postings.setdefault(token, array("I")).append(
                    (index << _TF_BITS) | min(int(tf), _TF_MAX))
        return cls(postings, chunk_ids, doc_ids, lengths, k1=k1, b=b,
                   ngram_min=ngram_min, ngram_max=ngram_max)

    def search(self, question: str, n: int = 10) -> list:
        """BM25 检索，返回按分数降序的至多 `n` 条（并列按 `chunk_id` 升序）。"""
        n = int(n)
        if n < 1 or not self.total_chunks:
            return []
        query_tokens = set(tokenize(question, self.ngram_min, self.ngram_max))
        scores = {}
        for token in query_tokens:
            posting = self.postings.get(token)
            if not posting:
                continue
            df = len(posting)
            idf = math.log(1.0 + (self.total_chunks - df + 0.5) / (df + 0.5))
            for encoded in posting:
                index = encoded >> _TF_BITS
                tf = encoded & _TF_MAX
                norm = self.k1 * (1.0 - self.b
                                  + self.b * self.lengths[index] / self.avgdl)
                scores[index] = scores.get(index, 0.0) + idf * tf * (self.k1 + 1.0) / (tf + norm)
        ranked = heapq.nlargest(
            n, scores.items(),
            key=lambda item: (item[1], -self.chunk_ids[item[0]]))
        return [{"chunk_id": self.chunk_ids[index], "doc_id": self.doc_ids[index],
                 "lexical_score": round(float(score), 8), "lexical_rank": rank}
                for rank, (index, score) in enumerate(ranked, 1)]


def rrf_fuse(rankings, k_rrf: int = 60) -> list:
    """Reciprocal Rank Fusion：`score = Σ 1/(k_rrf + rank)`（rank 从 1 起）。

    `rankings` 可为 `{通道名: 行列表}` 或行列表的序列；行可为含 `chunk_id` 的字典或裸 ID。
    返回 `[{chunk_id, rrf_score, rrf_rank, sources}]`，分数降序、并列按 `chunk_id` 升序。
    本函数只用于离线诊断，不接入默认链路。
    """
    groups = list(rankings.values()) if isinstance(rankings, dict) else list(rankings)
    names = list(rankings.keys()) if isinstance(rankings, dict) else [
        "ranking%d" % i for i in range(1, len(groups) + 1)]
    scores, sources = {}, {}
    for name, rows in zip(names, groups):
        for rank, row in enumerate(rows, 1):
            chunk_id = row.get("chunk_id") if isinstance(row, dict) else row
            if chunk_id is None:
                continue
            chunk_id = int(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (int(k_rrf) + rank)
            sources.setdefault(chunk_id, {})[name] = rank
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [{"chunk_id": chunk_id, "rrf_score": round(float(score), 8),
             "rrf_rank": rank, "sources": sources[chunk_id]}
            for rank, (chunk_id, score) in enumerate(ordered, 1)]
