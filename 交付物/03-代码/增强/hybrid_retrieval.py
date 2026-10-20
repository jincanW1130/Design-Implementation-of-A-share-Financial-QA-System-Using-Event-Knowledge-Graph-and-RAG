# -*- coding: utf-8 -*-
"""离线混合检索：向量／BM25 候选、加权 RRF、分数融合与规则式查询扩展。

本模块是**可插拔增强层**：函数默认口径仍是 RRF-60 两路等权。2026-10-20 起，
``zscore(alpha=0.3, 无查询扩展)`` 已作为**可选档**被 ``检索/pipeline.py`` 按文件路径
懒加载（``--retrieval hybrid-zscore``，pipeline 默认仍为 ``vector``），并由线上后端
``ASHARE_RETRIEVAL_MODE`` 默认启用；其余配置不进入默认链路。它只复用现有只读资产：

* 向量：``检索/vector_search.py`` 的 ``VectorSearcher``（现有 FAISS FlatIP 索引
  与本地 BGE；只读，不重建索引）；
* 词汇：``增强/lexical_search.py`` 的字符 1～3-gram BM25；
* 查询扩展：``交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/
  nodes.csv`` 的 ``name``、``stock_code``、``company_name``、``short_name``、
  ``aliases`` 列（Graph v1.3 只读导出物）。

默认口径
--------
``hybrid_search(question)`` 等价于现有 RRF 基线：两路各取 Top-20，
RRF ``k=60``、两路等权，然后取 Top-10；**不启用查询扩展**。纯融合函数
``rrf(rank_lists)`` 的默认值同样是 ``k=60``、``weights=(1, 1)``，输出与
``lexical_search.rrf_fuse(..., k_rrf=60)`` 的分数、顺序和并列规则一致。

零网络、零大模型 API 调用。BGE 仅在首次调用默认 ``vector_scores`` 时从本机缓存
离线加载；单元测试可以注入轻量替身，不加载模型或真实索引。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import math
import os
import re
import statistics
import sys
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias

_HERE = os.path.dirname(os.path.abspath(__file__))
_RETRIEVAL_DIR = os.path.abspath(os.path.join(_HERE, "..", "检索"))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_GRAPH_NODES_PATH = os.path.join(
    _ROOT,
    "交付物",
    "04-数据与知识图谱",
    "事件抽取与知识图谱",
    "图谱导出",
    "v2.1_v1_3",
    "nodes.csv",
)

_MISSING = object()
_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_SPACE_RE = re.compile(r"\s+")
_ALIAS_SPLIT_RE = re.compile(r"[|;；]")
_EXPANSION_STOPWORDS = frozenset({
    "公司", "本公司", "该公司", "发行人", "上市公司", "集团", "有限", "股份",
})

_MODULE_LOCK = threading.RLock()
_RETRIEVAL_CONFIG: Any = None
_VECTOR_MODULE: Any = None
_LEXICAL_MODULE: Any = None
_DEFAULT_VECTOR_SEARCHER: Any = None
_DEFAULT_LEXICAL_INDEX: Any = None
_DEFAULT_ALIAS_CATALOG: "AliasCatalog | None" = None

RankRow: TypeAlias = Mapping[str, Any] | int | str
RankLists: TypeAlias = Mapping[str, Sequence[RankRow]] | Sequence[Sequence[RankRow]]
ScoreRows: TypeAlias = Mapping[str | int, float] | Sequence[Mapping[str, Any]]


class VectorSearcherLike(Protocol):
    """``vector_scores`` 需要的最小向量检索接口。"""

    def search(self, question: str, n: int) -> tuple[list[dict], dict]:
        """返回候选行和耗时字典。"""


class LexicalIndexLike(Protocol):
    """``lexical_scores`` 需要的最小 BM25 检索接口。"""

    def search(self, question: str, n: int = 10) -> list[dict]:
        """返回按 BM25 分数降序排列的候选行。"""


@dataclass(frozen=True)
class _AliasGroup:
    """一个实体（公司优先按股票代码）的全部书写面。"""

    key: str
    label: str
    stock_code: str
    terms: tuple[str, ...]


@dataclass
class AliasCatalog:
    """只读实体别名目录；由 ``nodes.csv`` 的实体字段确定性构建。"""

    groups: tuple[_AliasGroup, ...]
    by_surface: dict[str, _AliasGroup]
    by_code: dict[str, _AliasGroup]
    source: str

    @classmethod
    def from_rows(
        cls,
        rows: Sequence[Mapping[str, Any]],
        source: str = "in-memory rows",
    ) -> "AliasCatalog":
        """从 Graph v1.3 ``nodes.csv`` 同形字典行构建目录。

        同一书写面优先绑定到带六位股票代码的 Company；否则保留 ``node_id``
        对应的实体。所有列表按输入行顺序去重，保证相同输入得到相同目录。
        """

        groups: list[_AliasGroup] = []
        group_index: dict[str, int] = {}
        for row in rows:
            label = str(row.get("label") or "").strip()
            node_id = str(row.get("node_id") or "").strip()
            code = str(row.get("stock_code") or "").strip()
            if not (len(code) == 6 and code.isdigit()):
                code = ""
            key = code or node_id
            if not key:
                continue

            raw_terms: list[str] = []
            fields = ["name", "stock_code", "company_name", "short_name"]
            if label == "Person":
                fields.append("person_name")
            elif label == "Institution":
                fields.append("institution_name")
            elif label == "Event":
                fields.append("event_name")
            elif label == "Policy":
                fields.append("policy_name")
            elif label == "Industry":
                fields.append("industry_name")
            for field in fields:
                raw_terms.append(str(row.get(field) or ""))
            for part in _ALIAS_SPLIT_RE.split(str(row.get("aliases") or "")):
                raw_terms.append(part)

            terms: list[str] = []
            seen: set[str] = set()
            for raw in raw_terms:
                term = _SPACE_RE.sub("", str(raw or "")).strip()
                norm = _normalize_surface(term)
                if not norm or norm in seen:
                    continue
                if not (len(norm) == 6 and norm.isdigit()) and (
                    len(norm) < 2 or norm in _EXPANSION_STOPWORDS
                ):
                    continue
                seen.add(norm)
                terms.append(term)
            if not terms:
                continue
            group = _AliasGroup(key=key, label=label, stock_code=code,
                                terms=tuple(terms))
            if key in group_index:
                old = groups[group_index[key]]
                merged = list(old.terms)
                merged_seen = {_normalize_surface(term) for term in merged}
                for term in group.terms:
                    norm = _normalize_surface(term)
                    if norm not in merged_seen:
                        merged.append(term)
                        merged_seen.add(norm)
                groups[group_index[key]] = _AliasGroup(
                    key=old.key,
                    label=old.label,
                    stock_code=old.stock_code,
                    terms=tuple(merged),
                )
            else:
                group_index[key] = len(groups)
                groups.append(group)

        by_surface: dict[str, _AliasGroup] = {}
        by_code: dict[str, _AliasGroup] = {}
        # 行顺序固定；遇到冲突时“有代码的 Company”覆盖无代码实体。
        for group in groups:
            if group.stock_code:
                by_code[group.stock_code] = group
            for term in group.terms:
                norm = _normalize_surface(term)
                if not norm:
                    continue
                old = by_surface.get(norm)
                if old is None or (not old.stock_code and group.stock_code):
                    by_surface[norm] = group
        return cls(groups=tuple(groups), by_surface=by_surface, by_code=by_code,
                   source=source)


def _load_module_by_path(module_name: str, path: str) -> Any:
    """按文件路径加载模块，避免四个同名 ``config.py`` 串味。"""

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("无法加载模块：%s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _load_retrieval_config() -> Any:
    """加载并缓存检索侧 ``config.py``（只读参数来源）。"""

    global _RETRIEVAL_CONFIG
    with _MODULE_LOCK:
        if _RETRIEVAL_CONFIG is None:
            _RETRIEVAL_CONFIG = _load_module_by_path(
                "_hybrid_retrieval_config",
                os.path.join(_RETRIEVAL_DIR, "config.py"),
            )
        return _RETRIEVAL_CONFIG


def _load_vector_module() -> Any:
    """加载现有 ``vector_search.py``，加载期临时绑定检索侧 ``config``。"""

    global _VECTOR_MODULE
    with _MODULE_LOCK:
        if _VECTOR_MODULE is not None:
            return _VECTOR_MODULE
        retrieval_config = _load_retrieval_config()
        saved_config = sys.modules.get("config", _MISSING)
        saved_path = list(sys.path)
        try:
            sys.modules["config"] = retrieval_config
            if _RETRIEVAL_DIR not in sys.path:
                sys.path.insert(0, _RETRIEVAL_DIR)
            _VECTOR_MODULE = _load_module_by_path(
                "_hybrid_vector_search",
                os.path.join(_RETRIEVAL_DIR, "vector_search.py"),
            )
        finally:
            sys.path[:] = saved_path
            if saved_config is _MISSING:
                sys.modules.pop("config", None)
            else:
                sys.modules["config"] = saved_config
        return _VECTOR_MODULE


def _load_lexical_module() -> Any:
    """加载增强层现有 ``lexical_search.py``（纯标准库，无重依赖）。"""

    global _LEXICAL_MODULE
    with _MODULE_LOCK:
        if _LEXICAL_MODULE is None:
            _LEXICAL_MODULE = _load_module_by_path(
                "_hybrid_lexical_search",
                os.path.join(_HERE, "lexical_search.py"),
            )
        return _LEXICAL_MODULE


def _default_vector_searcher() -> Any:
    """懒加载默认本地 BGE＋FAISS 检索器；只读现有索引，不重建、不写回。"""

    global _DEFAULT_VECTOR_SEARCHER
    with _MODULE_LOCK:
        if _DEFAULT_VECTOR_SEARCHER is None:
            module = _load_vector_module()
            _DEFAULT_VECTOR_SEARCHER = module.VectorSearcher(verbose=False)
        return _DEFAULT_VECTOR_SEARCHER


def _read_jsonl(path: str) -> list[dict]:
    """读取 UTF-8 JSONL，跳过空行。"""

    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _default_lexical_index() -> Any:
    """在内存中懒构建现有 BM25 索引；不落任何索引文件。"""

    global _DEFAULT_LEXICAL_INDEX
    with _MODULE_LOCK:
        if _DEFAULT_LEXICAL_INDEX is None:
            module = _load_lexical_module()
            chunks = _read_jsonl(str(_load_retrieval_config().CHUNKS_PATH))
            _DEFAULT_LEXICAL_INDEX = module.LexicalIndex.build(chunks)
        return _DEFAULT_LEXICAL_INDEX


def load_alias_catalog(path: str | None = None) -> AliasCatalog:
    """读取 Graph v1.3 ``nodes.csv`` 并构建只读别名目录。

    ``path`` 缺省指向正式图谱导出物。传入其他路径仅供离线实验或测试；本函数
    从不写 CSV、不连接 Neo4j。
    """

    source = os.path.abspath(path or _GRAPH_NODES_PATH)
    with open(source, "r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return AliasCatalog.from_rows(rows, source=source)


def _default_alias_catalog() -> AliasCatalog:
    """懒加载并缓存默认别名目录。"""

    global _DEFAULT_ALIAS_CATALOG
    with _MODULE_LOCK:
        if _DEFAULT_ALIAS_CATALOG is None:
            _DEFAULT_ALIAS_CATALOG = load_alias_catalog()
        return _DEFAULT_ALIAS_CATALOG


def vector_scores(
    question: str,
    k: int,
    searcher: VectorSearcherLike | None = None,
) -> list[dict]:
    """返回向量 Top-``k`` 候选；默认复用现有本地 BGE＋FAISS 只读索引。

    候选行保持 ``VectorSearcher.search`` 的原始字段与顺序。``searcher`` 可注入
    任何实现 ``search(question, n)`` 的替身，用于不加载模型的单测。
    """

    k = int(k)
    if k < 1:
        raise ValueError("k 必须为正整数，收到 %d" % k)
    engine = searcher or _default_vector_searcher()
    rows, _timing = engine.search(str(question), k)
    return list(rows)


def lexical_scores(
    question: str,
    k: int,
    index: LexicalIndexLike | None = None,
) -> list[dict]:
    """返回 BM25 Top-``k`` 候选；默认复用增强层内存倒排索引。"""

    k = int(k)
    if k < 1:
        raise ValueError("k 必须为正整数，收到 %d" % k)
    engine = index or _default_lexical_index()
    return list(engine.search(str(question), n=k))


def _normalize_surface(text: str) -> str:
    """实体书写面归一化：去空白、casefold；不删除标点以免误并专名。"""

    return _SPACE_RE.sub("", str(text or "")).casefold()


def expand_query(
    question: str,
    enabled: bool = True,
    catalog: AliasCatalog | None = None,
    max_terms: int = 8,
) -> str:
    """按实体规则把股票代码／公司名／实体别名补进查询。

    规则：

    1. 六位股票代码按数字边界命中后，补对应公司的简称、全称与别名；
    2. 公司名或别名命中后，补其余书写面与股票代码；
    3. 其他实体别名命中后，补其图谱导出物中的名称与别名。

    追加词按“目录中的书写面顺序”确定性去重，最多 ``max_terms`` 个。
    ``enabled=False`` 原样返回去首尾空白的查询，供默认基线显式关闭扩展。
    """

    text = str(question or "").strip()
    if not enabled or not text:
        return text
    catalog = catalog or _default_alias_catalog()
    normalized = _normalize_surface(text)
    matched: list[_AliasGroup] = []
    seen_keys: set[str] = set()

    for code in sorted(set(_CODE_RE.findall(normalized))):
        group = catalog.by_code.get(code)
        if group is not None and group.key not in seen_keys:
            matched.append(group)
            seen_keys.add(group.key)

    for surface, group in sorted(
        catalog.by_surface.items(),
        key=lambda item: (-len(item[0]), item[0]),
    ):
        if surface not in normalized or group.key in seen_keys:
            continue
        matched.append(group)
        seen_keys.add(group.key)
        if len(matched) >= 8:
            break

    additions: list[str] = []
    seen_terms = {_normalize_surface(text)}
    for group in matched:
        ordered_terms = sorted(
            group.terms,
            key=lambda term: (
                0 if _normalize_surface(term) == group.stock_code else 1,
                0 if len(_normalize_surface(term)) <= 8 else 1,
                group.terms.index(term),
            ),
        )
        for term in ordered_terms:
            norm = _normalize_surface(term)
            if not norm or norm in seen_terms:
                continue
            additions.append(term)
            seen_terms.add(norm)
            if len(additions) >= int(max_terms):
                return text + " " + " ".join(additions)
    return text + (" " + " ".join(additions) if additions else "")


def _ranking_groups(rank_lists: RankLists) -> tuple[list[str], list[Sequence[RankRow]]]:
    """把字典或序列形态的排名统一成 ``(通道名, 排名列表)``。"""

    if isinstance(rank_lists, Mapping):
        names = [str(name) for name in rank_lists.keys()]
        groups = [list(rank_lists[name]) for name in rank_lists.keys()]
        return names, groups
    groups = [list(rows) for rows in rank_lists]
    return ["ranking%d" % index for index in range(1, len(groups) + 1)], groups


def rrf(
    rank_lists: RankLists,
    k: int = 60,
    weights: Sequence[float] = (1, 1),
) -> list[dict]:
    """加权 Reciprocal Rank Fusion。

    公式为 ``score(d) = Σ_channel weight_c / (k + rank_c(d))``，rank 从 1 起。
    输入可为 ``{通道名: 行列表}`` 或行列表序列；行可为含 ``chunk_id`` 的字典、
    整数或数字字符串。输出按融合分降序、并列按 ``chunk_id`` 升序，字段为
    ``chunk_id``／``rrf_score``／``rrf_rank``／``sources``。

    空输入返回空列表；单列表、零权重和通道间并列均有确定行为。默认
    ``k=60``、两路等权，与现有 ``lexical_search.rrf_fuse(..., k_rrf=60)`` 等价。
    """

    names, groups = _ranking_groups(rank_lists)
    if not groups:
        return []
    numeric_weights = [float(weight) for weight in weights]
    if (len(groups) == 1 and len(numeric_weights) > 1
            and all(weight == 1.0 for weight in numeric_weights)):
        numeric_weights = numeric_weights[:1]
    if len(numeric_weights) != len(groups):
        raise ValueError("weights 长度 %d 与排名列表数 %d 不一致"
                         % (len(numeric_weights), len(groups)))
    k = int(k)
    if k < 0:
        raise ValueError("RRF k 必须非负，收到 %d" % k)
    if any(not math.isfinite(weight) or weight < 0 for weight in numeric_weights):
        raise ValueError("RRF weights 必须是有限非负数：%r" % (weights,))

    scores: dict[int, float] = {}
    sources: dict[int, dict[str, int]] = {}
    for name, rows, weight in zip(names, groups, numeric_weights):
        if weight == 0:
            continue
        for rank, row in enumerate(rows, 1):
            chunk_id = row.get("chunk_id") if isinstance(row, Mapping) else row
            if chunk_id is None:
                continue
            chunk_id = int(chunk_id)
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
            sources.setdefault(chunk_id, {})[name] = rank

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {
            "chunk_id": chunk_id,
            "rrf_score": round(float(score), 8),
            "rrf_rank": rank,
            "sources": sources[chunk_id],
        }
        for rank, (chunk_id, score) in enumerate(ordered, 1)
    ]


def normalize_scores(
    scores: Mapping[str | int, float],
    mode: str = "minmax",
) -> dict[int, float]:
    """按通道做 min-max 或 z-score 归一化。

    * ``minmax``：``(s-min)/(max-min)``；零极差时该通道全部记 1.0；
    * ``zscore``：``(s-mean)/pstdev``；零标准差时该通道全部记 0.0；
    * 空输入返回空字典。以上边界语义固定，避免除零且可单测。
    """

    values = {int(chunk_id): float(score) for chunk_id, score in scores.items()}
    if not values:
        return {}
    if mode == "minmax":
        low, high = min(values.values()), max(values.values())
        if high == low:
            return {chunk_id: 1.0 for chunk_id in values}
        return {
            chunk_id: (score - low) / (high - low)
            for chunk_id, score in values.items()
        }
    if mode == "zscore":
        mean = statistics.fmean(values.values())
        std = statistics.pstdev(values.values())
        if std == 0.0:
            return {chunk_id: 0.0 for chunk_id in values}
        return {
            chunk_id: (score - mean) / std
            for chunk_id, score in values.items()
        }
    raise ValueError("mode 只支持 'minmax' 或 'zscore'，收到 %r" % (mode,))


def _score_map(rows: ScoreRows, keys: Sequence[str]) -> dict[int, float]:
    """把候选行或 ``{chunk_id: score}`` 统一为分数字典；重复 ID 取最高分。"""

    if isinstance(rows, Mapping):
        out: dict[int, float] = {}
        for chunk_id, score in rows.items():
            cid, value = int(chunk_id), float(score)
            out[cid] = max(out.get(cid, value), value)
        return out
    out = {}
    for row in rows:
        if not isinstance(row, Mapping) or "chunk_id" not in row:
            raise ValueError("分数融合行必须是含 chunk_id 的字典")
        cid = int(row["chunk_id"])
        value = None
        for key in keys:
            if row.get(key) is not None:
                value = float(row[key])
                break
        if value is None:
            raise ValueError("chunk_id=%d 缺可识别分数字段 %s" % (cid, tuple(keys)))
        out[cid] = max(out.get(cid, value), value)
    return out


def score_fusion(
    vec: ScoreRows,
    lex: ScoreRows,
    mode: str = "minmax",
    alpha: float = 0.5,
) -> list[dict]:
    """向量／BM25 分数归一化后加权融合。

    ``alpha`` 是向量权重，词汇权重为 ``1-alpha``；只对候选并集输出，缺失通道
    归一化分记 0。输出按融合分降序、并列按 ``chunk_id`` 升序，并保留两路原分与
    归一化分，便于误差分析。
    """

    alpha = float(alpha)
    if not math.isfinite(alpha) or not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha 必须在 [0, 1]，收到 %r" % alpha)
    vec_raw = _score_map(vec, ("similarity", "vector_score", "score"))
    lex_raw = _score_map(lex, ("lexical_score", "score"))
    vec_norm = normalize_scores(vec_raw, mode)
    lex_norm = normalize_scores(lex_raw, mode)
    chunk_ids = sorted(set(vec_norm) | set(lex_norm))
    rows = []
    for chunk_id in chunk_ids:
        vec_value = vec_norm.get(chunk_id, 0.0)
        lex_value = lex_norm.get(chunk_id, 0.0)
        score = alpha * vec_value + (1.0 - alpha) * lex_value
        row = {
            "chunk_id": chunk_id,
            "fusion_score": round(float(score), 8),
            "vector_norm": round(float(vec_value), 8),
            "lexical_norm": round(float(lex_value), 8),
        }
        if chunk_id in vec_raw:
            row["vector_score"] = round(float(vec_raw[chunk_id]), 8)
        if chunk_id in lex_raw:
            row["lexical_score"] = round(float(lex_raw[chunk_id]), 8)
        rows.append(row)
    rows.sort(key=lambda row: (-row["fusion_score"], row["chunk_id"]))
    for rank, row in enumerate(rows, 1):
        row["fusion_rank"] = rank
    return rows


def hybrid_search(
    question: str,
    k: int = 10,
    retrieval_k: int = 20,
    method: str = "rrf",
    rrf_k: int = 60,
    weights: Sequence[float] = (1, 1),
    mode: str = "minmax",
    alpha: float = 0.5,
    expand: bool = False,
    vector_searcher: VectorSearcherLike | None = None,
    lexical_index: LexicalIndexLike | None = None,
    alias_catalog: AliasCatalog | None = None,
) -> list[dict]:
    """组合两路候选并截断到 ``k``；默认等于现有 RRF-60 基线。

    默认 ``method='rrf'``、``rrf_k=60``、两路等权、``expand=False``：两路各取
    Top-``retrieval_k``（默认 20），融合后取 Top-``k``（默认 10）。选择
    ``method='minmax'`` 或 ``'zscore'`` 时改走 ``score_fusion``。依赖可注入，
    因而本函数在单测中不需要真实 BGE 或 FAISS。
    """

    if int(k) < 1 or int(retrieval_k) < int(k):
        raise ValueError("要求 retrieval_k >= k >= 1")
    query = expand_query(question, enabled=bool(expand), catalog=alias_catalog)
    vec = vector_scores(query, int(retrieval_k), searcher=vector_searcher)
    lex = lexical_scores(query, int(retrieval_k), index=lexical_index)
    if method == "rrf":
        fused = rrf({"vector": vec, "lexical": lex}, k=rrf_k, weights=weights)
    elif method in ("minmax", "zscore"):
        fused = score_fusion(vec, lex, mode=method, alpha=alpha)
    else:
        raise ValueError("method 只支持 'rrf'／'minmax'／'zscore'，收到 %r"
                         % (method,))
    return fused[:int(k)]


__all__ = [
    "AliasCatalog",
    "expand_query",
    "hybrid_search",
    "lexical_scores",
    "load_alias_catalog",
    "normalize_scores",
    "rrf",
    "score_fusion",
    "vector_scores",
]
