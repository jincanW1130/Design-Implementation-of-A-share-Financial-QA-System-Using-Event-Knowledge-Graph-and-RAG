# -*- coding: utf-8 -*-
"""A 组 · Top-K 五步契约与分层保留顺序 —— 被测文件：`代码\\检索\\pipeline.py`。

覆盖的硬口径（出处见 `代码\\检索\\README.md` 第四节、《18》表 18-E）：

1. **合并去重**：两路命中同一 `chunk_id` 只算一个证据、不重复计数、**不加分**；
2. **时间过滤发生在合并去重之前**：构造一个"先过滤／后过滤结果不同"的用例，
   断言实现取的是"先过滤"（向量侧的命中不被图谱侧的过滤决定误删）；
3. **裁剪到 Context Token Budget**：超限时**先裁与问题实体无关的远端图谱路径**，
   再按**分层保留顺序从尾部往前**裁文本块；
4. **保留 K（第④步）先于分组排序（第⑤步）**；
5. **分层保留顺序三层**：第一层＝向量侧原始排名升序前 (K−g) 个；第二层＝图谱侧新增块按
   对问题的向量相似度降序、**并列按 `chunk_id` 升序**、至多 g 个；第三层＝向量侧剩余回填；
   尾部＝未被第二层取到的图谱侧新增块；
6. **D 组与 E 组的最终证据集合必然相同**（只有顺序可以不同）。

测试全部离线：图谱用临时目录里的合成 CSV ＋ 真实 `GraphQuery`，向量侧用进程内替身
（夹具见 `conftest.py`），不联网、不调模型、不读真实数据集与图谱导出物。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402
from conftest import QUESTION  # noqa: E402

pipe = _bootstrap.load_module("检索", "pipeline.py")
cfg = _bootstrap.component_config("检索")


# ---------------------------------------------------------------------------
# 小工具：构造 pipeline 各步的输入记录（字段名与 `merge_candidates` 的产出同形）
# ---------------------------------------------------------------------------
def _record(chunk_id, token_count=100, vector_rank=None, similarity=None,
            first_path_key=None, path_ordinals=(), relations=(), events=(),
            question_similarity=None):
    return {
        "chunk_id": int(chunk_id), "doc_id": 1,
        "vector_id": (int(vector_rank) - 1) if vector_rank is not None else None,
        "vector_rank": (int(vector_rank) if vector_rank is not None else None),
        "similarity": similarity,
        "hit_by": ["vector"] if vector_rank is not None else ["graph"],
        "graph_path_ordinals": list(path_ordinals),
        "graph_events": list(events), "graph_relations": list(relations),
        "graph_sources": ["G1"] if vector_rank is None else [],
        "first_path_key": first_path_key,
        "graph_anchor_min": 0,
        "token_count": int(token_count),
        "question_similarity": question_similarity,
    }


def _path(ordinal, anchor_distance, edge_id=0, events=(), depth=1):
    return {"ordinal": int(ordinal), "source": "G1", "start": "N_A", "end": "N_B",
            "depth": int(depth), "nodes": ["N_A", "N_B"],
            "relations": [{"edge_id": int(edge_id), "relation": "RELATED_TO",
                           "direction": "out", "neighbor": "N_B", "role": "主体",
                           "evidence": {"source_doc_id": "1", "source_chunk_id": "1",
                                        "confidence": "0.9"}}],
            "anchor_distance": int(anchor_distance), "events": list(events)}


def _chunks(*chunk_ids, token_count=100):
    return {int(cid): {"chunk_id": int(cid), "doc_id": 1, "token_count": int(token_count),
                       "content": ""} for cid in chunk_ids}


class _BudgetGraph:
    """**只给预算裁剪用**的最小图替身：实现 `trim_to_budget`／`account_tokens` 用到的那两个接口。

    `graph_path_payload` 返回 `{}` ⇒ 路径与事件三元组的估算 token 恒为 0，
    于是"预算算术"只由文本块的 `token_count` 决定，断言可以精确到块。
    （用真实 `GraphQuery` 的那条链路由 `test_run_question_end_to_end` 覆盖，防止替身掩盖不兼容。）
    """

    def __init__(self):
        self.nodes = {}

    def graph_path_payload(self, path):
        return {}


# ---------------------------------------------------------------------------
# A1 合并去重：同一 chunk_id 只算一个证据、不加分
# ---------------------------------------------------------------------------
def test_merge_dedup_counts_once_and_adds_no_score(synthetic_graph):
    graph_case = synthetic_graph
    chunks = graph_case.chunks
    graph_side = pipe.collect_graph_candidates(
        graph_case.graph, ["N_C1"], [], 2, chunks)

    assert 101 in graph_side["candidates"], "合成图上应有 101 这个图谱侧候选"

    # 构造"两路命中同一块"：假向量候选把这个块也命中一次（rank=1、similarity=0.5）
    fake_vector_row = {"vector_id": -1, "similarity": 0.5, "chunk_id": 101,
                       "doc_id": chunks[101]["doc_id"], "vector_rank": 1}
    merged = pipe.merge_candidates([fake_vector_row, dict(fake_vector_row)],   # 连向量侧也给重复行
                                   graph_side["candidates"], chunks)
    hits = [rec for rec in merged["records"] if int(rec["chunk_id"]) == 101]

    assert len(hits) == 1, "同一 chunk_id 只能算一个证据"
    assert hits[0]["hit_by"] == ["graph", "vector"], "两路命中应记为 hit_by=[graph, vector]"
    assert float(hits[0]["similarity"]) == 0.5, "相似度必须原样来自向量侧，不得被改写"
    assert int(hits[0]["vector_rank"]) == 1, "原始排名必须原样保留"
    assert not [k for k in hits[0] if k in ("score", "boost", "weight", "adjusted_similarity")], \
        "合并去重不得引入任何加分字段"
    assert merged["counts"]["union"] == len({rec["chunk_id"] for rec in merged["records"]})
    assert merged["counts"]["dual_hit"] == 1


# ---------------------------------------------------------------------------
# A2 时间过滤必须发生在合并去重**之前**（构造"先后顺序结果不同"的用例）
# ---------------------------------------------------------------------------
def test_time_filter_happens_before_merge(synthetic_graph):
    """标定"先后顺序在本用例上**结果不同**"，并给出各原语在两种顺序下的读数。

    **职责边界（重要，避免过度声称）**：本用例只调用
    `collect_graph_candidates`／`apply_time_filter`／`graph_candidates_after_filter`／
    `merge_candidates` 这几个**原语**，**没有**调用 `run_question`——而"先过滤还是先合并"
    是在 `run_question` 里写死的调用顺序。所以本用例证明的是"这条判据能区分两种顺序"
    （判据的**标定**），**不是**"实现取的是先过滤"。
    对**实现顺序**的防线是同文件的 `test_run_question_end_to_end`：它直接读 trace 段落
    （图谱侧 5 个候选 → 合并只吃过滤后的 2 个）；一旦实现改回"先合并、再按图谱侧结论删块"，
    那一条会立刻变红。
    """
    graph_case = synthetic_graph
    graph, chunks = graph_case.graph, graph_case.chunks
    graph_side = pipe.collect_graph_candidates(graph, ["N_C1"], ["业绩"], 2, chunks)

    # 105 是"路径上没有事件"的图谱侧候选（合成边 N_C1 -RELATED_TO-> N_C2）；
    # 它同时也是向量侧 rank=1 的候选——这正是能区分先后顺序的那块。
    assert set(graph_side["candidates"]) == {101, 102, 103, 104, 105}

    filter_record = pipe.apply_time_filter(graph, graph_side, QUESTION, chunks)
    assert filter_record["branch"] == "time_filter" and filter_record["g6_called"] is True
    assert filter_record["kept_chunk_ids"] == [101, 104]
    assert filter_record["removed_chunk_ids"] == [102, 103, 105]
    assert filter_record["removed_by_reason"] == {
        "null_time_event": [102], "out_of_range_event": [103], "no_event_time": [105]}

    # —— 实现路径：过滤图谱侧 → 再合并（`run_question` 第①②步的取法）
    filtered = pipe.graph_candidates_after_filter(graph_side, filter_record)
    merged_ok = pipe.merge_candidates(graph_case.vector_rows, filtered, chunks)
    ids_ok = [rec["chunk_id"] for rec in merged_ok["records"]]

    # —— 反例路径：先合并、再拿图谱侧的过滤结论去删（这是被排除的写法）
    merged_all = pipe.merge_candidates(graph_case.vector_rows, graph_side["candidates"], chunks)
    removed = set(filter_record["removed_chunk_ids"])
    ids_wrong = [rec["chunk_id"] for rec in merged_all["records"]
                 if rec["chunk_id"] not in removed]

    assert ids_wrong != ids_ok, "本用例必须能区分先后顺序，否则断言是空的"
    assert 105 in ids_ok, "向量侧的命中不得因为图谱侧的过滤决定而被删掉"
    assert 105 not in ids_wrong, "反例路径确实会误删 105"
    by_id = {rec["chunk_id"]: rec for rec in merged_ok["records"]}
    assert by_id[105]["hit_by"] == ["vector"], "105 在图谱侧已被过滤，不得再标成两路命中"
    assert by_id[101]["hit_by"] == ["graph", "vector"], "101 在窗口内，应保留两路命中"
    assert merged_ok["counts"]["dual_hit"] == 1


# ---------------------------------------------------------------------------
# A3 端到端一题：从 trace 的段落读数上看"过滤先于合并"
# ---------------------------------------------------------------------------
def _run_question(graph_case, searcher, evidence_sort=False, budget=None, k=None, g=None):
    graph, chunks, documents = graph_case.graph, graph_case.chunks, graph_case.documents
    switches = {"graph_depth": 2, "time_filter": True, "evidence_sort": bool(evidence_sort),
                "_group": ("E" if evidence_sort else "D")}
    return pipe.run_question(
        QUESTION, switches, graph, searcher, chunks, documents,
        n=int(cfg.require_fixed("N")),
        k=int(k if k is not None else cfg.require_fixed("K")),
        budget=int(budget if budget is not None else cfg.require_fixed("context_token_budget")),
        g=int(g if g is not None else cfg.require_fixed("graph_retention_share")),
        vector_cache={}, graph_cache={}, full_pool_cache={})


def test_run_question_end_to_end(synthetic_graph, fake_searcher):
    """**"过滤先于合并"这条纪律的真正防线**：读数取自 `run_question` 写下的 trace 段落。

    同文件的 `test_time_filter_happens_before_merge` 只标定"两种顺序结果不同"（用的是原语，
    不经过 `run_question`）；决定顺序的那几行在 `run_question` 里，因此必须有本条用例。
    下面的 `wrong_order_graph_input` 就是"先合并"那条路会给出的读数：
    与 trace 里的 2 不同，说明本条断言**能**区分两种实现。
    """
    record = _run_question(synthetic_graph, fake_searcher())
    segments = record["segments"]

    # 反例读数：把**未过滤**的图谱侧直接交给合并去重会是多少个（＝先合并那条路的输入）
    graph_side = pipe.collect_graph_candidates(
        synthetic_graph.graph, ["N_C1"], ["业绩"], 2, synthetic_graph.chunks)
    wrong_order_graph_input = len(graph_side["candidates"])

    # ① 两路取候选：图谱侧 5 个候选；② 合并去重只吃**过滤后**的 2 个
    assert segments["① 两路取候选"]["graph"]["output_candidates"] == 5
    assert segments["② 合并去重"]["input_graph"] == 2, \
        "合并去重的图谱侧输入必须是过滤后的集合（过滤先于合并）"
    assert wrong_order_graph_input == 5 != segments["② 合并去重"]["input_graph"], \
        "本断言必须能区分「先合并」与「先过滤」两种实现"
    assert segments["② 合并去重"]["dual_hit"] == 1
    # 图谱侧被过滤掉 3 个块（含 105）；但 105 在向量侧仍命中，故**候选差集只有 102／103**
    # ——"过滤只筛图谱侧、向量侧不受影响"的正面证据（两者对照着看才有意义）
    assert record["time_filter"]["removed_chunk_ids"] == [102, 103, 105]
    assert record["candidate_diff_removed"] == [102, 103]

    k = int(cfg.require_fixed("K"))
    g = int(cfg.require_fixed("graph_retention_share"))
    # 第④步：分层保留顺序取前 K（本题候选 4 个 < K，全部保留且不删题）
    assert record["evidence"] == [105, 101, 999, 104], \
        "第一层＝向量侧原始排名升序（105,101,999）→ 第二层＝图谱侧新增块（104）"
    assert record["graph_evidence_in_final"] == [104]
    assert record["dual_hit_in_final"] == [101]
    assert record["evidence_size"] == len(set(record["evidence"])) <= k
    assert record["checks"] == {"evidence_unique": True, "candidates_unique": True,
                               "within_budget": True, "kept_le_k": True}
    assert record["precision_fill"]["denominator"] == k
    assert record["precision_fill"]["vacant"] == k - record["evidence_size"]
    assert g == cfg.RETRIEVAL["graph_retention_share"]


def test_run_question_D_and_E_share_the_same_evidence_set(synthetic_graph, fake_searcher):
    """《02》第12.6节 与《18》表 18-E 的硬断言：D 与 E 的最终证据集合必然相同。

    只有第⑤步的分组排序（E 组单变量）允许改变顺序——本用例同时验证"集合相同、顺序不同"，
    因此它不是一条恒真的空断言。
    """
    d = _run_question(synthetic_graph, fake_searcher(), evidence_sort=False)
    e = _run_question(synthetic_graph, fake_searcher(), evidence_sort=True)
    assert set(d["evidence"]) == set(e["evidence"])
    assert len(d["evidence"]) == len(e["evidence"])
    assert d["switches"] == {"graph_depth": 2, "time_filter": True, "evidence_sort": False}
    assert e["switches"] == {"graph_depth": 2, "time_filter": True, "evidence_sort": True}
    assert d["evidence"] != e["evidence"], "E 组只改顺序；本用例的顺序确实变了（非空断言）"


# ---------------------------------------------------------------------------
# A4 裁剪第一轮：先裁与问题实体无关的远端图谱路径（最远的先裁）
# ---------------------------------------------------------------------------
def test_trim_drops_remote_paths_first():
    k, g = 10, 2
    records = [
        _record(1, vector_rank=1, similarity=0.9),
        _record(2, vector_rank=2, similarity=0.8),
        _record(3, vector_rank=3, similarity=0.7),
        _record(20, path_ordinals=[1], first_path_key=(1, 0), question_similarity=0.5),
        _record(21, path_ordinals=[2], first_path_key=(2, 0), question_similarity=0.4),
        _record(4, vector_rank=4, similarity=0.6),
        _record(5, vector_rank=5, similarity=0.5),
        _record(22, path_ordinals=[5], first_path_key=(5, 0), question_similarity=0.3),
        _record(23, path_ordinals=[6], first_path_key=(6, 0), question_similarity=0.2),
    ]
    paths = [_path(1, 0, edge_id=1), _path(2, 0, edge_id=2),
             _path(5, 2, edge_id=5),          # 远端：anchor_distance=2（最远）
             _path(6, 1, edge_id=6)]          # 远端：anchor_distance=1
    chunks = _chunks(1, 2, 3, 4, 5, 20, 21, 22, 23, token_count=100)
    plan = pipe.plan_graph_layer(records, k, g)
    order_key = pipe.retention_key(k, g, plan["layer2_positions"])

    trimmed = pipe.trim_to_budget(records, paths, _BudgetGraph(), chunks,
                                  budget=700, g=g, order_key=order_key)

    assert trimmed["before"]["total_tokens"] == 900
    assert trimmed["after"]["total_tokens"] == 700
    assert trimmed["dropped_paths"] == [5, 6], \
        "远端无关图谱路径必须先被裁掉，且最远的(anchor_distance=2)在前"
    assert [(d["chunk_id"], d["reason"]) for d in trimmed["dropped_chunks"]] == [
        (22, "支撑路径被裁（远端无关图谱路径）"),
        (23, "支撑路径被裁（远端无关图谱路径）"),
    ], "先出局的必须是『只由被裁远端路径支撑』的图谱侧新增块"
    assert 1 not in trimmed["dropped_paths"] and 2 not in trimmed["dropped_paths"], \
        "从问题实体直接出发的路径是最后手段，本轮不得被裁"
    assert [rec["chunk_id"] for rec in trimmed["records"]] == [1, 2, 3, 20, 21, 4, 5]
    assert trimmed["budget_exceeded"] is False


# ---------------------------------------------------------------------------
# A5 裁剪第二轮：按分层保留顺序**从尾部往前**裁文本块
# ---------------------------------------------------------------------------
def test_trim_drops_chunks_from_tail_in_layered_order():
    k, g = 5, 2
    records = [
        _record(1, vector_rank=1),
        _record(2, vector_rank=2),
        _record(3, vector_rank=3),
        _record(20, path_ordinals=[1], first_path_key=(1, 0), question_similarity=0.9),
        _record(21, path_ordinals=[2], first_path_key=(2, 0), question_similarity=0.8),
        _record(4, vector_rank=4),
        _record(5, vector_rank=5),
        _record(22, path_ordinals=[3], first_path_key=(3, 0), question_similarity=0.1),
    ]
    paths = [_path(1, 0, edge_id=1), _path(2, 0, edge_id=2), _path(3, 0, edge_id=3)]
    chunks = _chunks(1, 2, 3, 4, 5, 20, 21, 22, token_count=100)
    plan = pipe.plan_graph_layer(records, k, g)
    order_key = pipe.retention_key(k, g, plan["layer2_positions"])

    # 分层升序＝[1,2,3,20,21,4,5,22]；从尾部往前裁到 400 token ⇒ 裁 22 → 5 → 4 → 21
    trimmed = pipe.trim_to_budget(records, paths, _BudgetGraph(), chunks,
                                  budget=400, g=g, order_key=order_key)

    assert trimmed["dropped_paths"] == [], "本题没有远端路径，不得误裁路径"
    assert [d["chunk_id"] for d in trimmed["dropped_chunks"]] == [22, 5, 4, 21]
    assert [rec["chunk_id"] for rec in trimmed["records"]] == [1, 2, 3, 20]
    assert trimmed["budget_exceeded"] is False
    assert trimmed["after"]["total_tokens"] == 400

    # —— 负向标定：换回"原字面口径"的排序键，裁掉的就不是这 4 个块了。
    # 这条断言证明本用例**真的在测分层顺序**，而不是一条对任何顺序都成立的空断言；
    # 旧口径下被挤出去的是图谱侧新增块 20（P0 现场：图谱侧证据进不了最终集合）。
    legacy_drops = [rec["chunk_id"] for rec in
                    sorted(records, key=pipe.legacy_priority_key, reverse=True)][:4]
    assert legacy_drops == [22, 21, 20, 5] != [22, 5, 4, 21]
    legacy_kept = [cid for cid in (1, 2, 3, 4, 5, 20, 21, 22) if cid not in set(legacy_drops)]
    assert legacy_kept == [1, 2, 3, 4] != [1, 2, 3, 20]


# ---------------------------------------------------------------------------
# A6 分层保留顺序：三层定义 + 第二层并列按 chunk_id 升序
# ---------------------------------------------------------------------------
def test_layered_retention_order_and_tie_break():
    k, g = 5, 2
    # 图谱侧三块的相似度刻意打平（0.5 / 0.5）且**逆序给出**，让"并列按 chunk_id 升序"可观测
    records = [
        _record(21, path_ordinals=[2], first_path_key=(2, 0), question_similarity=0.5),
        _record(20, path_ordinals=[1], first_path_key=(1, 0), question_similarity=0.5),
        _record(22, path_ordinals=[3], first_path_key=(3, 0), question_similarity=0.1),
        _record(1, vector_rank=1), _record(2, vector_rank=2), _record(3, vector_rank=3),
        _record(4, vector_rank=4), _record(5, vector_rank=5),
    ]
    plan = pipe.plan_graph_layer(records, k, g)
    positions = plan["layer2_positions"]

    assert plan["cut"] == k - g == 3
    assert plan["layer2_ids"] == [20, 21], "相似度并列时按 chunk_id 升序取前 g 个"

    order = [rec["chunk_id"] for rec in pipe.fixed_original_order(records, [], k, g, positions)]
    assert order == [1, 2, 3, 20, 21, 4, 5, 22], \
        "第一层(向量前 K−g) → 第二层(图谱侧新增块≤g) → 第三层(向量侧剩余回填) → 尾部"

    by_id = {rec["chunk_id"]: rec for rec in records}
    tier = lambda cid: pipe.evidence_priority_key(by_id[cid], k, g, positions)[0]
    assert tier(3) == pipe.LAYER1_VECTOR_TIER
    assert tier(4) == pipe.LAYER3_VECTOR_FILL_TIER
    assert tier(20) == pipe.LAYER2_GRAPH_TIER
    assert tier(22) == pipe.LEFTOVER_GRAPH_TIER
    assert [pipe.LAYER1_VECTOR_TIER, pipe.LAYER2_GRAPH_TIER,
            pipe.LAYER3_VECTOR_FILL_TIER, pipe.LEFTOVER_GRAPH_TIER] == [0, 1, 2, 3], \
        "四档标号的顺序不可颠倒"

    # 输入顺序不得影响结果（并列规则是确定性的必要条件）
    reversed_order = [rec["chunk_id"] for rec in
                      pipe.fixed_original_order(list(reversed(records)), [], k, g, positions)]
    assert reversed_order == order


def test_keep_top_k_takes_the_first_k_of_the_layered_order():
    k, g = 5, 2
    records = [_record(1, vector_rank=1), _record(2, vector_rank=2), _record(3, vector_rank=3),
               _record(20, path_ordinals=[1], first_path_key=(1, 0), question_similarity=0.9),
               _record(21, path_ordinals=[2], first_path_key=(2, 0), question_similarity=0.8),
               _record(4, vector_rank=4), _record(5, vector_rank=5),
               _record(22, path_ordinals=[3], first_path_key=(3, 0), question_similarity=0.1)]
    plan = pipe.plan_graph_layer(records, k, g)
    kept = pipe.keep_top_k({"records": records}, k, g, plan["layer2_positions"])

    assert [rec["chunk_id"] for rec in kept["records"]] == [1, 2, 3, 20, 21]
    assert kept["dropped"] == [4, 5, 22]
    assert kept["candidates"] == 8 and kept["kept"] == k
    assert "截取先于分组排序" in kept["note"]


def test_keep_top_k_keeps_questions_whose_candidates_are_fewer_than_k():
    """候选不足 K：全部保留、**不删题**，空缺记未命中（分母恒为 K）。"""
    k, g = 10, 2
    records = [_record(1, vector_rank=1), _record(2, vector_rank=2)]
    kept = pipe.keep_top_k({"records": records}, k, g, {})
    assert kept["kept"] == 2
    assert kept["precision_fill"] == {"denominator": k, "candidates": 2, "vacant": k - 2,
                                      "note": "候选不足 K：空缺位置记未命中，题目保留"}


# ---------------------------------------------------------------------------
# A7 第④步先于第⑤步；D 与 E 的最终证据集合相同（表 18-E 断言 1）
# ---------------------------------------------------------------------------
def test_keep_k_precedes_group_sort_and_D_equals_E(synthetic_graph):
    k, g = 5, 2
    records = [_record(1, vector_rank=1), _record(2, vector_rank=2), _record(3, vector_rank=3),
               _record(20, path_ordinals=[1], first_path_key=(1, 0), relations=["RELATED_TO"],
                       question_similarity=0.9),
               _record(21, path_ordinals=[2], first_path_key=(2, 0), relations=["RELATED_TO"],
                       question_similarity=0.8),
               _record(4, vector_rank=4), _record(5, vector_rank=5),
               _record(22, path_ordinals=[3], first_path_key=(3, 0), relations=["RELATED_TO"],
                       question_similarity=0.1)]
    chunks = _chunks(1, 2, 3, 4, 5, 20, 21, 22, token_count=10)
    plan = pipe.plan_graph_layer(records, k, g)
    positions = plan["layer2_positions"]

    kept = pipe.keep_top_k({"records": records}, k, g, positions)
    assert [rec["chunk_id"] for rec in kept["records"]] == [1, 2, 3, 20, 21], \
        "第④步在第⑤步之前：先按分层保留顺序截取前 K，再谈顺序"

    d = pipe.order_evidence(synthetic_graph.graph, kept["records"], [], enabled=False,
                            seeds=[], documents={}, chunks=chunks, k=k, g=g,
                            layer2_positions=positions)
    e = pipe.order_evidence(synthetic_graph.graph, kept["records"], [], enabled=True,
                            seeds=[], documents={}, chunks=chunks, k=k, g=g,
                            layer2_positions=positions)

    assert set(d["order"]) == set(e["order"]) == {1, 2, 3, 20, 21}
    assert d["order"] == [1, 2, 3, 20, 21], "D 组＝分层保留顺序"
    assert e["order"] != d["order"], "E 组只改顺序；本用例的顺序确实变了（非空断言）"
    assert e["keys"] == list(cfg.EVIDENCE_SORT_KEYS)
    assert [rec["chunk_id"] for rec in e["records"]] == e["order"]
    assert sorted(rec["chunk_id"] for rec in e["records"]) == sorted(d["order"])


# ---------------------------------------------------------------------------
# A8 g = 0 退化为"原字面口径"（legacy_priority_key）；g 的取值域显式校验
# ---------------------------------------------------------------------------
def test_g0_degenerates_to_legacy_key():
    k = 5
    records = [_record(1, vector_rank=1), _record(2, vector_rank=2),
               _record(20, path_ordinals=[1], first_path_key=(1, 0), question_similarity=0.9),
               _record(3, vector_rank=3),
               _record(21, path_ordinals=[2], first_path_key=(2, 0), question_similarity=0.1)]
    new_asc = [rec["chunk_id"] for rec in sorted(records, key=pipe.retention_key(k, 0))]
    legacy_asc = [rec["chunk_id"] for rec in sorted(records, key=pipe.legacy_priority_key)]
    assert new_asc == legacy_asc
    assert new_asc[:k] == legacy_asc[:k]
    assert ([rec["chunk_id"] for rec in sorted(records, key=pipe.retention_key(k, 0), reverse=True)]
            == [rec["chunk_id"] for rec in sorted(records, key=pipe.legacy_priority_key, reverse=True)])
    assert new_asc == [1, 2, 3, 20, 21], "g=0：向量侧在前、图谱侧新增块按路径出现顺序追加在后"
    assert pipe.priority_rule_text(k, 0) == pipe.LEGACY_PRIORITY_RULE


@pytest.mark.parametrize("g", [-1, 11, 99])
def test_low_level_g_out_of_range_raises(g):
    """B-16 整改：越界 g 一律抛错，**不静默夹取**（修订前是 `g = max(0, int(g))`）。"""
    with pytest.raises(ValueError):
        pipe._check_low_level_g(10, g)


def test_run_entry_g_lower_bound_is_one():
    """运行入口与命令行只接受 1 ≤ g ≤ K；g=0 只能走显式命名的退化回归通道。"""
    assert cfg.check_graph_share(1, 10) == 1
    assert cfg.check_graph_share(10, 10) == 10
    with pytest.raises(ValueError):
        cfg.check_graph_share(0, 10)
    with pytest.raises(ValueError):
        cfg.check_graph_share(11, 10)
    assert cfg.GRAPH_SHARE_FLOOR == 1
