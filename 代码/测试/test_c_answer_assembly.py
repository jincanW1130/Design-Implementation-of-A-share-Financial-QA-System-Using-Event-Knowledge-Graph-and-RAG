# -*- coding: utf-8 -*-
"""C 组 · 答案装配的三段确定性拼装与 token 账 —— 被测文件：`代码\\问答\\` 的
`assemble.py`／`prompt.py`／`rules.py`／`answer.py`／`run_answer.py`。

覆盖（《21》第五节 硬约束 5／6／7／8／9／10；评审 P1-12）：

1. **三段由代码确定性拼装**：「回答」之外的【证据来源】【知识图谱路径】【数据截至与判定区间】
   由 `prompt.compose_answer()` 拼装，同样输入两次**逐字节一致**；
2. **0 跳（未使用图谱扩展）** 必须出现固定标注「本次回答未使用图谱扩展」，
   且**不得生成虚构图谱路径**（`graph_path` 为空表、段落正文恰为标注本身）；
3. **证据编号引用不得越界**：`[证据n]` 的 n ∉ 1..m 即判失败（`answer.gate` 的 `failures`）；
4. **token 账取"保留 K 之后"的最终证据集合口径**（`run_answer.final_set_token_account()`）
   —— 这是第 8 阶段修过的**真缺陷**（原先取 `budget_trim.after`，即"裁到预算之后、保留 K
   之前"的账），本文件用三条用例把它钉住，含 `assemble.assemble_case()` 的装配账目守卫；
5. 顺带钉住 `prompt.SOURCE_TYPE_BY_CATEGORY` 的**键必须等于语料里的真实 category 取值**
   （2026-09-29 实测到的同类缺陷：把「财经新闻」写成近义词「新闻」，整类证据静默落到兜底类）。

标了 `pytest.skip` 的用例只依赖**只读**读取数据集（`阶段05-数据准备\\数据集\\v2.1\\`），
文件缺失即跳过；其余用例全部离线、零外部依赖。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

prompt_mod = _bootstrap.load_module("问答", "prompt.py")
rules = _bootstrap.load_module("问答", "rules.py")
asm = _bootstrap.load_module("问答", "assemble.py")
answer_mod = _bootstrap.load_module("问答", "answer.py")
run_answer = _bootstrap.load_module("问答", "run_answer.py")
qcfg = _bootstrap.component_config("问答")

DATASET_VERSION = qcfg.DATASET_VERSION
DATA_CUTOFF_TIME = qcfg.DATA_CUTOFF_TIME


# ---------------------------------------------------------------------------
# 夹具与构造器
# ---------------------------------------------------------------------------
def _evidence_item(rank, chunk_id=1, doc_id=1, category="公告", from_graph=False, **extra):
    item = {"rank": rank, "chunk_id": chunk_id, "doc_id": doc_id,
            "token_count": 10, "text": "合成正文：本次披露不涉及任何金额。",
            "title": "合成标题", "source": "cninfo", "category": category,
            "publish_time": "2026-03-02", "url": "https://example.invalid/x",
            "from_graph": from_graph}
    item.update(extra)
    return item


NOT_USED_PAYLOAD = {"graph_used": False, "graph_path": [], "event_triples": [],
                    "note": "未使用图谱扩展", "reason": "检索深度为 0"}

USED_PAYLOAD = {
    "graph_used": True, "depth": 2, "note": "路径列表与事件三元组计入 Context Token Budget，不计入 K",
    "event_triples": [["E-A", "业绩", "2026-03-01"]],
    "graph_path": [{"start": "N_C1", "end": "EV_A", "depth": 1, "nodes": ["N_C1", "EV_A"],
                    "relations": [{"relation": "PARTICIPATES_IN", "direction": "out",
                                   "neighbor": "EV_A", "role": "主体",
                                   "evidence": {"source_doc_id": "1", "source_chunk_id": "101",
                                                "confidence": "0.90"}}]}],
}

TIME_NOTE_NONE = {"time_constraint": "无", "basis": "event_time",
                  "data_cutoff_time": DATA_CUTOFF_TIME,
                  "window_label": None, "lo": None, "hi": None,
                  "text": "数据截止时间：%s\n本题**不含相对时间表述**，无判定区间。" % DATA_CUTOFF_TIME}


def _compose(body, evidence, payload, time_note=TIME_NOTE_NONE):
    return prompt_mod.compose_answer(body=body, evidence=evidence, graph_payload=payload,
                                     dataset_version=DATASET_VERSION,
                                     data_cutoff_time=DATA_CUTOFF_TIME, time_note=time_note)


# ---------------------------------------------------------------------------
# C1 三段确定性拼装：四段结构 + 两次拼装逐字节一致
# ---------------------------------------------------------------------------
def test_compose_answer_is_byte_identical_across_two_calls():
    evidence = [_evidence_item(1), _evidence_item(2, chunk_id=2, doc_id=2, category="财经新闻")]
    a = _compose("回答正文，引用 [证据1] 与 [证据2]。", evidence, USED_PAYLOAD)
    b = _compose("回答正文，引用 [证据1] 与 [证据2]。", evidence, USED_PAYLOAD)
    assert a == b, "三段由代码拼装，同样输入必须逐字节一致"
    assert len(a.encode("utf-8")) == len(b.encode("utf-8"))

    sections = prompt_mod.split_answer_sections(a)
    assert list(sections) == prompt_mod.ANSWER_SECTIONS == [
        "回答", "证据来源", "知识图谱路径", "数据截至与判定区间"]
    assert sections["回答"] == "回答正文，引用 [证据1] 与 [证据2]。", "「回答」段必须逐字等于模型正文"
    assert "[证据1] chunk_id=1 doc_id=1 来源类型=公告来源" in sections["证据来源"]
    assert "[证据2] chunk_id=2 doc_id=2 来源类型=新闻来源" in sections["证据来源"]
    assert sections["数据截至与判定区间"].startswith("数据版本：%s" % DATASET_VERSION)
    assert DATA_CUTOFF_TIME in sections["数据截至与判定区间"]
    # 段头只出现一次（切段不留残迹）
    for header in prompt_mod.SECTION_HEADERS:
        assert a.count(header) == 1


def test_compose_answer_does_not_rewrite_the_model_body():
    body = "  含前后空白的正文 [证据1]  "
    text = _compose(body, [_evidence_item(1)], USED_PAYLOAD)
    sections = prompt_mod.split_answer_sections(text)
    assert sections["回答"] == body.strip(), "装配层不得改写模型正文（非目标 10）"


# ---------------------------------------------------------------------------
# C2 0 跳：固定标注必须出现，且不得生成虚构图谱路径
# ---------------------------------------------------------------------------
def test_zero_hop_uses_the_fixed_marker_and_invents_no_path():
    text = _compose("正文 [证据1]", [_evidence_item(1)], NOT_USED_PAYLOAD)
    sections = prompt_mod.split_answer_sections(text)
    graph_section = sections["知识图谱路径"]
    assert graph_section == prompt_mod.NO_GRAPH_MARKER == "本次回答未使用图谱扩展"
    assert NOT_USED_PAYLOAD["graph_path"] == []
    assert "->" not in graph_section and "—" not in graph_section, "不得生成虚构图谱路径"
    assert "depth=" not in graph_section
    assert prompt_mod.NO_GRAPH_MARKER not in sections["回答"]
    assert prompt_mod.render_graph_section(NOT_USED_PAYLOAD) == prompt_mod.NO_GRAPH_MARKER
    assert prompt_mod.render_graph_section({}) == prompt_mod.NO_GRAPH_MARKER


def test_graph_used_renders_the_path_and_omits_the_marker():
    text = _compose("正文 [证据1]", [_evidence_item(1, from_graph=True)], USED_PAYLOAD)
    graph_section = prompt_mod.split_answer_sections(text)["知识图谱路径"]
    assert prompt_mod.NO_GRAPH_MARKER not in text
    assert "depth=2" in graph_section
    assert "N_C1 -PARTICIPATES_IN(" in graph_section
    assert "source_chunk_id=101" in graph_section
    assert "E-A / 业绩 / 2026-03-01" in graph_section


def test_prompt_blocks_omit_the_graph_block_when_not_used(retrieval_mod, synthetic_graph):
    """第 5 区块（图谱路径与事件三元组）在 `graph_used` 为假时**整体缺省**，不留空标题。"""
    graph = synthetic_graph.graph
    zero_hop = retrieval_mod.build_answer_graph_payload(graph, [], [], depth=0)
    assert zero_hop["graph_used"] is False and zero_hop["graph_path"] == []
    assert zero_hop["note"] == "未使用图谱扩展"
    assert zero_hop["reason"] == "检索深度为 0"

    built = prompt_mod.build_messages(question="问题原文", dataset_version=DATASET_VERSION,
                                      data_cutoff_time=DATA_CUTOFF_TIME,
                                      evidence=[_evidence_item(1)],
                                      graph_payload=zero_hop, time_note=TIME_NOTE_NONE)
    assert "【图谱路径与事件三元组】" not in built["user"]
    assert built["graph_used"] is False
    assert built["user"].count("【") == 4, "七个区块中有图谱区块时才是 5 个标题，缺省时是 4 个"

    built_used = prompt_mod.build_messages(question="问题原文", dataset_version=DATASET_VERSION,
                                           data_cutoff_time=DATA_CUTOFF_TIME,
                                           evidence=[_evidence_item(1)],
                                           graph_payload=USED_PAYLOAD, time_note=TIME_NOTE_NONE)
    assert "【图谱路径与事件三元组】" in built_used["user"]
    assert built_used["graph_used"] is True


# ---------------------------------------------------------------------------
# C3 证据编号引用不得越界
# ---------------------------------------------------------------------------
def test_citation_gate_flags_out_of_range_marks():
    gate = rules.citation_gate("结论见 [证据2] 与 [证据10]；另见 [证据99]。", 10)
    assert gate["citation_marks"] == [2, 10, 99]
    assert gate["citation_out_of_range"] == [99]
    assert gate["citation_out_of_range_count"] == 1
    assert gate["cited_ranks"] == [2, 10]
    assert rules.citation_gate("无引用的一段话", 3)["citation_out_of_range"] == []
    assert rules.citation_gate("无引用的一段话", 3)["citation_marks"] == []
    assert rules.citation_gate("[证据0]", 3)["citation_out_of_range"] == [0], \
        "编号从 1 起算，0 也是越界"


@pytest.fixture(scope="module")
def real_corpus_head():
    """从真实数据集里取**前两行**文本块与其文档（**只读**；文件缺失即跳过整组用例）。"""
    chunks_path = getattr(qcfg, "CHUNKS_PATH", None)
    docs_path = getattr(qcfg, "DOCUMENTS_PATH", None)
    if not chunks_path or not docs_path or not os.path.isfile(chunks_path) \
            or not os.path.isfile(docs_path):
        pytest.skip("只读依赖缺失：%s" % chunks_path)
    chunks, docs = [], {}
    with open(chunks_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            chunks.append(json.loads(line))
            if len(chunks) >= 2:
                break
    need = {row["doc_id"] for row in chunks}
    with open(docs_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row["doc_id"] in need:
                docs[row["doc_id"]] = row
            if len(docs) == len(need):
                break
    return chunks, docs


def test_gate_fails_on_out_of_range_citation(real_corpus_head):
    """越界引用必须被判失败（`answer.gate` 的 `failures` 里出现 citation_out_of_range）。"""
    chunks, docs = real_corpus_head
    evidence = []
    for rank, row in enumerate(chunks, 1):
        doc = docs[row["doc_id"]]
        evidence.append({"rank": rank, "chunk_id": row["chunk_id"], "doc_id": row["doc_id"],
                         "token_count": row["token_count"], "text": row.get("content") or "",
                         "title": doc.get("title"), "source": doc.get("source"),
                         "category": doc.get("category"), "publish_time": doc.get("publish_time"),
                         "url": doc.get("url"), "from_graph": False})
    case = {"qid": "C-CITE", "question": "合成问题", "group": "C", "evidence": evidence,
            "graph_payload": NOT_USED_PAYLOAD, "time_note": TIME_NOTE_NONE,
            "dataset_version": DATASET_VERSION, "data_cutoff_time": DATA_CUTOFF_TIME,
            "task_type": "事实型"}
    assert len(evidence) == 2, "夹具必须真的取到 2 条语料证据，否则本用例是空的"

    bad_body = "越界引用 [证据3]"                       # m == 2，3 越界
    bad_answer = _compose(bad_body, evidence, NOT_USED_PAYLOAD)
    bad = answer_mod.gate(case, bad_body, bad_answer)
    assert bad["citation_out_of_range"] == [3]
    assert "citation_out_of_range" in bad["failures"]
    assert bad["passed"] is False

    good_body = "合法引用 [证据1] 与 [证据2]"
    good = answer_mod.gate(case, good_body, _compose(good_body, evidence, NOT_USED_PAYLOAD))
    assert good["citation_out_of_range"] == []
    assert "citation_out_of_range" not in good["failures"]
    assert good["evidence_backlink_ok"] is True


# ---------------------------------------------------------------------------
# C4 来源类型映射的键必须等于语料里的真实 category 取值
# ---------------------------------------------------------------------------
def test_source_type_mapping_covers_every_real_category():
    docs_path = getattr(qcfg, "DOCUMENTS_PATH", None)
    if not docs_path or not os.path.isfile(docs_path):
        pytest.skip("只读依赖缺失：%s" % docs_path)
    categories = set()
    with open(docs_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                categories.add(json.loads(line).get("category"))
    unknown = sorted(c for c in categories if c and c not in prompt_mod.SOURCE_TYPE_BY_CATEGORY)
    assert len(categories) >= 4, "语料的 category 词表不该少于 4 类（否则夹具没读到真数据）"
    assert unknown == [], ("语料里出现映射表没覆盖的 category %s——它会静默落到兜底类"
                           "「%s」（2026-09-29 的同类缺陷：键名与真实取值不一致）"
                           % (unknown, prompt_mod.SOURCE_TYPE_DEFAULT))
    assert prompt_mod.SOURCE_TYPE_BY_CATEGORY.get("财经新闻") == "新闻来源"
    assert prompt_mod.source_type_label({"category": "财经新闻"}) == "新闻来源"
    assert prompt_mod.source_type_label({"category": "不存在的类目"}) == prompt_mod.SOURCE_TYPE_DEFAULT
    assert prompt_mod.source_type_label({"category": "公告", "from_graph": True}) \
        == prompt_mod.SOURCE_TYPE_GRAPH


# ---------------------------------------------------------------------------
# C5 token 账：必须是「保留 K 之后」的最终证据集合口径（第 8 阶段真缺陷的回归防线）
# ---------------------------------------------------------------------------
def _run_record(chunk_ids, token_counts, paths=(), triples=()):
    """伪造一份第 7 阶段 `run_query.py` 的运行记录：`budget_trim.after` 故意用"保留 K 之前"的口径。"""
    chunks = {int(cid): {"chunk_id": int(cid), "doc_id": 1, "token_count": int(tc),
                         "content": "正文"} for cid, tc in zip(chunk_ids, token_counts)}
    kept = [int(cid) for cid in chunk_ids]
    kept_tokens = int(sum(token_counts))
    # 旧缺陷的现场：`budget_trim.after` 是"裁剪到预算之后、保留 K 之前"的账，比最终集合多两块
    after_tokens = kept_tokens + 2 * 50
    return {
        "question": {"qid": "C-TOKEN", "text": "合成问题"},
        "group": "D",
        "parameters": {"K": int(qcfg.K), "N": int(qcfg.N),
                       "context_token_budget": int(qcfg.CONTEXT_TOKEN_BUDGET)},
        "final_evidence": {"presentation_order": kept, "graph_evidence_in_final": [],
                           "dual_hit_in_final": []},
        "graph_path_payload": {"graph_used": bool(paths or triples), "depth": 2,
                               "graph_path": list(paths), "event_triples": [list(t) for t in triples]},
        "budget_trim": {"after": {"text_chunks": len(kept) + 2, "text_tokens": after_tokens,
                                  "paths": len(paths), "path_tokens": 0,
                                  "event_triples": len(triples), "event_triple_tokens": 0,
                                  "graph_tokens": 0, "total_tokens": after_tokens}},
    }, chunks


def test_final_set_token_account_follows_the_final_evidence_set():
    rec, chunks = _run_record([101, 102, 103], [100, 200, 300],
                              triples=[["E-A", "业绩", "2026-03-01"]])
    account = run_answer.final_set_token_account(rec, chunks)
    assert account["text_chunks"] == 3
    assert account["text_tokens"] == 600
    assert account["total_tokens"] == 600 + account["path_tokens"] + account["event_triple_tokens"]
    assert account["text_tokens"] != rec["budget_trim"]["after"]["text_tokens"], \
        "本用例必须能区分两种口径，否则断言是空的"


def test_record_to_trace_row_never_falls_back_to_budget_trim():
    """P0-新① 回归防线：不得再用 `budget_trim.after`（保留 K 之前的账）。"""
    rec, chunks = _run_record([101, 102, 103], [100, 200, 300])
    row = run_answer.record_to_trace_row(rec, chunks)
    assert row["token_account"] == run_answer.final_set_token_account(rec, chunks)
    assert row["token_account"]["text_chunks"] == 3
    assert row["token_account"]["text_tokens"] == 600
    assert row["token_account"]["total_tokens"] != rec["budget_trim"]["after"]["total_tokens"]
    assert row["final_evidence_chunk_ids"] == [101, 102, 103]
    assert row["k"] == int(qcfg.K) and row["n"] == int(qcfg.N)


def test_record_to_trace_row_refuses_to_guess_without_chunks():
    rec, _chunks = _run_record([101, 102, 103], [100, 200, 300])
    with pytest.raises(SystemExit) as excinfo:
        run_answer.record_to_trace_row(rec)
    assert "budget_trim.after" in str(excinfo.value), \
        "错误信息必须点明拒绝回退到 budget_trim.after"


def _assemble_inputs(chunk_ids, token_counts, graph_payload):
    chunk_index, doc_index = {}, {}
    for cid, tc in zip(chunk_ids, token_counts):
        chunk_index[cid] = {"chunk_id": cid, "doc_id": 1, "token_count": tc,
                            "content": "合成正文 [证据1]"}
    doc_index[1] = {"doc_id": 1, "title": "合成标题", "source": "cninfo", "category": "公告",
                    "publish_time": "2026-03-02", "url": "https://example.invalid/x"}
    question_row = {"qid": "C-ASSEMBLE", "question": "合成问题", "time_constraint": "无",
                    "time_window": None, "task_type": "事实型", "gold_hop_depth": 2}
    dataset_meta = {"dataset_version": DATASET_VERSION, "data_cutoff_time": DATA_CUTOFF_TIME}
    return chunk_index, doc_index, question_row, dataset_meta


def test_assemble_case_is_deterministic_and_guards_the_token_account():
    chunk_ids, token_counts = [101, 102, 103], [100, 200, 300]
    rec, chunks = _run_record(chunk_ids, token_counts)
    row = run_answer.record_to_trace_row(rec, chunks)
    payload = {"graph_used": False, "graph_path": [], "event_triples": [],
               "note": "未使用图谱扩展", "reason": "检索深度为 0"}
    row["graph_payload"] = payload
    chunk_index, doc_index, question_row, dataset_meta = _assemble_inputs(
        chunk_ids, token_counts, payload)

    first = asm.assemble_case(row, chunk_index, doc_index, question_row, dataset_meta)
    second = asm.assemble_case(row, chunk_index, doc_index, question_row, dataset_meta)
    assert first["prompt"]["sha256"] == second["prompt"]["sha256"]
    assert first["prompt"]["system"] == second["prompt"]["system"]
    assert first["prompt"]["user"] == second["prompt"]["user"]
    assert first["evidence"] == second["evidence"]
    assert [item["chunk_id"] for item in first["evidence"]] == chunk_ids, \
        "生成侧不得重排、不得裁剪证据（硬约束 5／6）"
    assert first["token_account"]["text_tokens"] == 600
    assert first["checks"]["graph_payload_passthrough"] is True

    # —— 装配账目守卫：把账换成"保留 K 之前"的口径（旧缺陷的现场）→ 必须报错退出
    tampered = dict(row, token_account=dict(rec["budget_trim"]["after"]))
    with pytest.raises(SystemExit) as excinfo:
        asm.assemble_case(tampered, chunk_index, doc_index, question_row, dataset_meta)
    message = str(excinfo.value)
    assert "token 账现场重算与上游 trace 不一致" in message
    assert str(rec["budget_trim"]["after"]["total_tokens"]) in message
    assert str(600) in message


def test_assemble_case_rejects_evidence_beyond_k_or_out_of_corpus():
    chunk_ids = [101, 102, 103]
    token_counts = [10, 10, 10]
    rec, chunks = _run_record(chunk_ids, token_counts)
    row = run_answer.record_to_trace_row(rec, chunks)
    row["graph_payload"] = {"graph_used": False, "graph_path": [], "event_triples": [],
                            "note": "未使用扩展", "reason": "检索深度为 0"}
    chunk_index, doc_index, question_row, dataset_meta = _assemble_inputs(
        chunk_ids, token_counts, row["graph_payload"])

    missing = dict(row, final_evidence_chunk_ids=[101, 424242])
    with pytest.raises(SystemExit):
        asm.assemble_case(missing, chunk_index, doc_index, question_row, dataset_meta)

    over_k = dict(row, final_evidence_chunk_ids=list(range(1, int(qcfg.K) + 2)))
    over_index = dict(chunk_index)
    for cid in over_k["final_evidence_chunk_ids"]:
        over_index[cid] = {"chunk_id": cid, "doc_id": 1, "token_count": 1, "content": "x"}
    over_row = dict(over_k, token_account={**row["token_account"],
                                           "text_tokens": len(over_k["final_evidence_chunk_ids"]),
                                           "path_tokens": 0, "event_triple_tokens": 0,
                                           "graph_tokens": 0,
                                           "total_tokens": len(over_k["final_evidence_chunk_ids"])})
    with pytest.raises(SystemExit) as excinfo:
        asm.assemble_case(over_row, over_index, doc_index, question_row, dataset_meta)
    assert "超过 K" in str(excinfo.value)


# ---------------------------------------------------------------------------
# C6 日期来源可核与禁词（判据单一来源 `rules.py`）
# ---------------------------------------------------------------------------
def test_date_gate_accepts_allowed_sources_and_flags_the_rest():
    case = {"evidence": [{"text": "公告写明的行权期为2026年9月11日至2027年1月25日。",
                          "title": "合成标题", "publish_time": "2026-03-02"}],
            "graph_payload": NOT_USED_PAYLOAD,
            "time_note": {"time_constraint": "无"}}
    good = rules.date_gate("证据里的日期是 2026年9月11日，另见公告原文的 2027年1月25日。", case)
    assert good["date_unverifiable"] == []
    assert "2027-01-25" in good["dates_beyond_cutoff"]        # 晚于截止时间：只统计、不计失败
    assert good["date_unverifiable_count"] == 0
    bad = rules.date_gate("凭空写一个 2019年1月1日。", case)
    assert bad["date_unverifiable"] == ["2019-01-01"]
    assert bad["date_unverifiable_count"] == 1


def test_forbidden_terms_are_a_fixed_constant():
    hits = rules.forbidden_gate("本回答不构成投资建议，也不给出任何目标价。")
    assert hits["forbidden_hits"] == ["投资建议", "目标价"]
    assert rules.forbidden_gate("公告中提及股东减持与风险提示，本次预计不产生影响。")["forbidden_hits"] == []
    assert not (set(rules.FORBIDDEN_EXCLUDED_CORPUS_WORDS) & set(rules.FORBIDDEN_TERMS))
    assert rules.forbidden_terms() == rules.FORBIDDEN_TERMS
