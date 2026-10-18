# -*- coding: utf-8 -*-
"""代码\\检索\\reranker.py —— 可插拔重排序（Rerank）接口（第 10 轮新增）。

定位与纪律
----------
本模块只提供**最终证据顺序**的可插拔钩子，不训练、不加载任何模型，也不改变默认实验口径：

* `rerank_records(records, question, reranker=None)`：纯函数。
  - `reranker is None`（默认）→ **原样返回原列表**（顺序、成员、字段一字不改）；
  - 注入自定义 `reranker` → 由它给出新的顺序；返回值必须是输入记录的**排列**——
    不得增删记录、不得重复、不得替换成别的记录（违反即 `ValueError`，防止"重排"
    悄悄变成"换证据"）。
* `rerank_record(record, question, reranker=None, chunks=None)`：对 `pipeline.run_question()`
  产出的**一条 trace** 做包装式重排；默认 `None` 时原样返回**同一个对象**。
* `rerank_result(result, questions, reranker=None, chunks=None)`：对 `PipelineRunner.run()`
  的整个结果做同样的包装；默认 `None` 时原样返回**同一个对象**。
* `RerankedRunner(runner, reranker=None)`：`PipelineRunner` 的透明包装器，接口与
  `run(questions, switches, n, k, budget, g)` 一致。

为什么是"包装"而不是改 `pipeline.py`
------------------------------------
`pipeline.py` 是第 10 阶段门禁 G4 登记的**上游只读文件**（SHA-256 基线）；直接改它会让
46 行验收失败。且五步契约把证据**集合**冻结在第④步「保留 K」，③④⑤三步各自用同一套
分层排序键重新排序，在合并阶段插入重排会被下游覆盖、成为"看起来接入了、实际无效果"
的空接口。因此本模块在 pipeline **输出之后**重排**最终证据的呈现顺序**：集合不变
（Recall@K 不变）、顺序可变（MRR 可能变化），默认完全透明。

`reranker` 可以是可调用对象 `f(question, records) -> records`，也可以是带
`rerank(question, records)` 方法的对象（接口见 `Reranker` Protocol）。本模块不 import
config、不读索引、不联网，是纯排序适配层。

若未来要做真正改变候选集合的 Cross-Encoder 重排，必须作为**新实验组**在「④ 保留 K」
之前引入，并同步重跑 A～E 的冻结口径，不能走默认链路。
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence


class Reranker(Protocol):
    """自定义重排器的最小接口（结构化类型，不要求继承）。"""

    def rerank(self, question: str, records: Sequence[dict]) -> Sequence[dict]:
        """返回 `records` 的一个排列（成员相同、顺序可变）。"""


def _call_reranker(reranker: Any, question: str, records: list) -> list:
    """统一调用形态：对象方法优先，其次是可调用对象；其余一律 `TypeError`。"""
    method = getattr(reranker, "rerank", None)
    if callable(method):
        ordered = method(question, list(records))
    elif callable(reranker):
        ordered = reranker(question, list(records))
    else:
        raise TypeError("reranker 必须是可调用对象或带 rerank(question, records) 的对象，"
                        "收到 %r" % type(reranker).__name__)
    if ordered is None:
        raise ValueError("reranker 返回了 None；必须返回输入记录的一个排列")
    return list(ordered)


def _check_permutation(records: list, ordered: list) -> None:
    """重排结果必须是输入记录的排列：成员数、chunk_id 集合都不变。"""
    if len(ordered) != len(records):
        raise ValueError("reranker 改变了记录条数：输入 %d 条、输出 %d 条"
                         % (len(records), len(ordered)))
    original_ids = []
    for record in records:
        if "chunk_id" not in record:
            raise ValueError("reranker 的输入记录缺 chunk_id，无法校验重排结果")
        original_ids.append(int(record["chunk_id"]))
    new_ids = []
    for record in ordered:
        if not isinstance(record, dict) or "chunk_id" not in record:
            raise ValueError("reranker 的输出必须是输入记录本身（含 chunk_id 的字典）")
        new_ids.append(int(record["chunk_id"]))
    if len(set(new_ids)) != len(new_ids):
        raise ValueError("reranker 输出含重复 chunk_id：%s" % new_ids)
    if sorted(new_ids) != sorted(original_ids):
        raise ValueError("reranker 输出不是输入记录的排列：输入 %s、输出 %s"
                         % (sorted(original_ids), sorted(new_ids)))


def rerank_records(records, question: str, reranker=None) -> list:
    """对候选记录做可选重排；默认 `None` 时**原样返回原列表**（零行为变化）。

    * 只改顺序，不改任何字段：记录对象本身透传（`similarity`／`vector_rank` 等仍是原值）；
    * 输出必须是输入的一个排列，否则抛 `ValueError`；
    * `question` 供重排器使用，本函数不读取、不改写它。
    """
    items = records if isinstance(records, list) else list(records)
    if reranker is None:
        return items
    ordered = _call_reranker(reranker, str(question), items)
    _check_permutation(items, ordered)
    return ordered


def rerank_record(record, question=None, reranker=None, chunks=None) -> dict:
    """对一条 pipeline trace 的最终证据顺序做可选重排。

    * 默认 `reranker is None` → **原样返回同一个 record 对象**（不复制、不改写）；
    * 注入时复制外层 record（不改调用方对象），只改 `evidence`／
      `final_evidence_chunk_ids` 与 trace 第⑤段的 `order`；集合、计数与其他字段不变；
    * 传给 reranker 的记录含 `chunk_id`、`orig_rank`，并在 `chunks` 给出时附 `content`，
      便于未来的 Cross-Encoder 读取正文；它必须返回这些记录的一个排列。
    """
    if reranker is None:
        return record
    if not isinstance(record, dict):
        raise TypeError("record 必须是 pipeline 产出的 trace 字典")
    evidence = record.get("evidence")
    if evidence is None:
        evidence = record.get("final_evidence_chunk_ids") or []
    ids = [int(chunk_id) for chunk_id in evidence]
    rows = []
    for index, chunk_id in enumerate(ids, 1):
        row = {"chunk_id": chunk_id, "orig_rank": index}
        if chunks is not None:
            row["content"] = str((chunks.get(chunk_id) or {}).get("content") or "")
        rows.append(row)
    ordered = rerank_records(rows, question if question is not None else "", reranker)
    new_ids = [int(row["chunk_id"]) for row in ordered]

    result = dict(record)
    result["evidence"] = new_ids
    if "final_evidence_chunk_ids" in record:
        result["final_evidence_chunk_ids"] = list(new_ids)
    segments = record.get("segments")
    if isinstance(segments, dict) and "⑤ 最终证据集合" in segments:
        segment = dict(segments["⑤ 最终证据集合"])
        segment["order"] = list(new_ids)
        segment["presentation_rule"] = (
            str(segment.get("presentation_rule") or "")
            + "；末尾由注入的 reranker 重排（默认不启用）")
        new_segments = dict(segments)
        new_segments["⑤ 最终证据集合"] = segment
        result["segments"] = new_segments
    result["rerank_applied"] = True
    return result


def rerank_result(result, questions, reranker=None, chunks=None) -> dict:
    """对 `PipelineRunner.run()` 的整个结果做包装式重排；默认 None 返回同一对象。"""
    if reranker is None:
        return result
    questions_by_qid = {str(row["qid"]): row["question"] for row in questions or []}
    records = [rerank_record(record, questions_by_qid.get(str(record.get("qid")), ""),
                             reranker, chunks)
               for record in result.get("records") or []]
    wrapped = dict(result)
    wrapped["records"] = records
    return wrapped


class RerankedRunner:
    """`PipelineRunner` 的透明包装器：默认 `reranker=None` 时行为与原对象完全一致。"""

    def __init__(self, runner, reranker=None):
        self.runner = runner
        self.reranker = reranker

    def run(self, questions, switches, n: int, k: int, budget: int, g: int) -> dict:
        result = self.runner.run(questions, switches, n, k, budget, g)
        return rerank_result(result, questions, self.reranker,
                             getattr(self.runner, "chunks", None))
