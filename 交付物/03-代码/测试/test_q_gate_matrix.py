# -*- coding: utf-8 -*-
"""Q 组 · 答案机检门禁的 11 项失败判定矩阵（第三轮 9.x）。

`问答\\answer.py::gate()` 的失败项共 11 种。既有 C 组只覆盖了
`citation_out_of_range` 一项；本组用**合成语料索引**（不读真实数据集、不连库）构造一个
基线通过样例，然后每次只破坏一个判据，确认：

* 对应失败项出现，且 `passed=False`；
* 基线样例本身 `failures == []`，避免「全都失败所以看不出来」；
* 11 种失败项在整张矩阵里**恰好各出现一次**（空正文同时触发 citation_missing 属预期）。

不启动模型、不访问网络；`_corpus_index` 用 monkeypatch 换成两条合成块。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

answer_mod = _bootstrap.load_module("问答", "answer.py")
prompt_mod = _bootstrap.load_module("问答", "prompt.py")
qcfg = _bootstrap.component_config("问答")

DATASET_VERSION = qcfg.DATASET_VERSION
CUTOFF = qcfg.DATA_CUTOFF_TIME

NOT_USED = {"graph_used": False, "graph_path": [], "event_triples": [],
            "note": "未使用图谱扩展", "reason": "检索深度为 0"}
TIME_NONE = {"time_constraint": "无", "basis": "event_time",
             "data_cutoff_time": CUTOFF, "window_label": None, "lo": None, "hi": None,
             "text": "数据截止时间：%s\n本题**不含相对时间表述**，无判定区间。" % CUTOFF}

CHUNKS = {
    1: {"chunk_id": 1, "doc_id": 1, "token_count": 10, "content": "合成块一"},
    2: {"chunk_id": 2, "doc_id": 2, "token_count": 10, "content": "合成块二"},
}
DOCS = {
    1: {"doc_id": 1, "title": "合成公告", "source": "cninfo", "category": "公告",
        "publish_time": "2026-03-02", "url": "https://example.invalid/1"},
    2: {"doc_id": 2, "title": "合成新闻", "source": "eastmoney", "category": "财经新闻",
        "publish_time": "2026-03-03", "url": "https://example.invalid/2"},
}


def _evidence(chunk_id=1, doc_id=1):
    return {"rank": 1 if chunk_id == 1 else 2, "chunk_id": chunk_id, "doc_id": doc_id,
            "token_count": 10, "text": "合成证据正文，不含日期。", "title": "合成标题",
            "source": "cninfo", "category": "公告", "publish_time": "2026-03-02",
            "url": "https://example.invalid/x", "from_graph": False}


def _case(**overrides):
    case = {
        "qid": "Q-GATE", "question": "合成问题", "group": "C",
        "evidence": [_evidence(1, 1), _evidence(2, 2)],
        "graph_payload": dict(NOT_USED), "time_note": dict(TIME_NONE),
        "dataset_version": DATASET_VERSION, "data_cutoff_time": CUTOFF,
        "task_type": "事实型",
    }
    case.update(overrides)
    return case


def _answer(case, body, graph_payload=None, time_note=None):
    return prompt_mod.compose_answer(
        body=body, evidence=case["evidence"],
        graph_payload=graph_payload if graph_payload is not None else case["graph_payload"],
        dataset_version=DATASET_VERSION, data_cutoff_time=CUTOFF,
        time_note=time_note if time_note is not None else case["time_note"])


@pytest.fixture(autouse=True)
def synthetic_index(monkeypatch):
    monkeypatch.setattr(answer_mod, "_corpus_index", lambda: (CHUNKS, DOCS))
    monkeypatch.setattr(answer_mod, "_INDEX_CACHE", {}, raising=False)


def test_baseline_answer_passes_all_gates():
    case = _case()
    body = "合成回答，引用 [证据1] 与 [证据2]。"
    result = answer_mod.gate(case, body, _answer(case, body))
    assert result["failures"] == []
    assert result["passed"] is True
    assert result["evidence_backlink_ok"] is True
    assert result["time_note_ok"] is True


def _mutation_cases():
    """返回 (id, case, body, answer, 期望失败项集合)。每次只破坏一个判据。"""

    # ① 引用越界：m=2，正文引用 [证据3]
    c = _case()
    b = "越界引用 [证据3]。"
    yield "citation_out_of_range", c, b, _answer(c, b), {"citation_out_of_range"}

    # ② 没有任何引用
    c = _case()
    b = "这段回答没有引用任何证据。"
    yield "citation_missing", c, b, _answer(c, b), {"citation_missing"}

    # ③ 日期无法回溯到证据/题集
    c = _case()
    b = "凭空写一个 2019年1月1日 [证据1]。"
    yield "date_unverifiable", c, b, _answer(c, b), {"date_unverifiable"}

    # ④ 图谱实际使用，但答案图谱段仍是「未使用」固定标注
    c = _case(graph_payload={"graph_used": True, "graph_path": [], "event_triples": [],
                             "note": "x", "reason": "x"})
    b = "合成回答 [证据1]。"
    yield "graph_section", c, b, _answer(c, b, graph_payload=NOT_USED), {"graph_section"}

    # ⑤ 模型正文泄漏「未使用图谱扩展」固定标注
    c = _case()
    b = "本次回答未使用图谱扩展 [证据1]。"
    yield "body_graph_marker_leak", c, b, _answer(c, b), {"body_graph_marker_leak"}

    # ⑥ 模型正文泄漏系统拼装段的小标题
    c = _case()
    b = "证据来源如下 [证据1]。"
    yield "body_section_header_leak", c, b, _answer(c, b), {"body_section_header_leak"}

    # ⑦ 禁词
    c = _case()
    b = "本回答不构成投资建议 [证据1]。"
    yield "forbidden_terms", c, b, _answer(c, b), {"forbidden_terms"}

    # ⑧ 证据回链在语料里查不到
    c = _case(evidence=[_evidence(1, 1), {**_evidence(2, 2), "chunk_id": 999999}])
    b = "合成回答 [证据1] 与 [证据2]。"
    yield "evidence_backlink", c, b, _answer(c, b), {"evidence_backlink"}

    # ⑨ 空正文（同时必然没有引用）
    c = _case()
    b = "   "
    yield "empty_answer", c, b, _answer(c, b), {"empty_answer", "citation_missing"}

    # ⑩ 有相对时间约束，但答案的时间段缺少判定区间
    c = _case(time_note={
        "time_constraint": "有", "basis": "event_time", "data_cutoff_time": CUTOFF,
        "window_label": "2026-08-26 至 2026-09-25", "lo": "2026-08-26", "hi": "2026-09-25",
        "text": "窗口：2026-08-26 至 2026-09-25"})
    b = "合成回答 [证据1]。"
    yield "time_note", c, b, _answer(c, b, time_note=TIME_NONE), {"time_note"}

    # ⑪ 开放式题缺少固定标注
    c = _case(task_type="分析型")
    b = "开放式分析但没有固定标注 [证据1]。"
    yield "open_ended_marker", c, b, _answer(c, b), {"open_ended_marker"}


@pytest.mark.parametrize("name,case,body,text,expected",
                         list(_mutation_cases()), ids=[m[0] for m in _mutation_cases()])
def test_each_gate_failure_is_detected(name, case, body, text, expected):
    result = answer_mod.gate(case, body, text)
    assert result["passed"] is False
    assert expected.issubset(set(result["failures"])), (name, result["failures"])


def test_matrix_covers_all_eleven_failure_types():
    seen = set()
    for _name, case, body, text, _expected in _mutation_cases():
        seen.update(answer_mod.gate(case, body, text)["failures"])
    assert seen == {
        "citation_out_of_range", "citation_missing", "date_unverifiable",
        "graph_section", "body_graph_marker_leak", "body_section_header_leak",
        "forbidden_terms", "evidence_backlink", "empty_answer", "time_note",
        "open_ended_marker",
    }
