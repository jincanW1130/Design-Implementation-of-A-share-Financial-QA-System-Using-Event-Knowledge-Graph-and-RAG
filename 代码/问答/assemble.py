# -*- coding: utf-8 -*-
"""代码\\问答\\assemble.py —— T4：把 trace 的一行装配成一份完整的生成输入。

输入（只读）：`阶段07-RAG检索系统\\检索产出\\per_question_trace.jsonl`；证据正文取
`chunks.jsonl`（权威来源），文档元数据取 `documents.jsonl`，时间口径取题集
`questions.jsonl` 与 `dataset.json`。

**确定性**：同一输入两次装配的 Prompt 文本 SHA-256 相同（《21》第五节 硬约束 17、
验收 C6）。本模块不重排证据、不重新裁剪、不重算 token（《21》第五节 硬约束 5／6、
第六节 格式决策 8）。

`from_graph` 的判据（题面给的判据**经实测不成立**，故改用 trace 已有的字段，见下方
`_graph_side_ids` 的注释）。
"""

from __future__ import annotations

import copy
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config   # noqa: E402
import prompt as prompt_mod   # noqa: E402


# --------------------------------------------------------------------------
# 读取
# --------------------------------------------------------------------------
def load_trace() -> list:
    """读 `per_question_trace.jsonl`（30 行，C 组）。"""
    return list(config.iter_jsonl(config.TRACE_PATH))


def load_chunks() -> dict:
    """`chunk_id` → chunks.jsonl 的整行（含 `token_count` 与正文 `content`）。"""
    return {row["chunk_id"]: row for row in config.iter_jsonl(config.CHUNKS_PATH)}


def load_documents() -> dict:
    """`doc_id` → documents.jsonl 的整行。"""
    return {row["doc_id"]: row for row in config.iter_jsonl(config.DOCUMENTS_PATH)}


def load_questions() -> dict:
    """`qid` → questions.jsonl 的整行。"""
    return {row["qid"]: row for row in config.iter_jsonl(config.QUESTIONS_PATH)}


def load_dataset_meta() -> dict:
    return config.read_json(config.DATASET_META_PATH)


# --------------------------------------------------------------------------
# 时间判定说明
# --------------------------------------------------------------------------
def build_time_note(question_row: dict, data_cutoff_time: str) -> dict:
    """按题集的 `time_constraint`／`time_window` 与数据截止时间生成本题的时间判定说明。

    `time_constraint` 在题集里的取值是**「有」／「无」**（不是 0／1），不得假设成布尔。
    """
    tc = question_row.get("time_constraint")
    if tc not in ("有", "无"):
        raise SystemExit("题集 %s 的 time_constraint 取值异常：%r（只认「有」／「无」）"
                         % (question_row.get("qid"), tc))
    window = question_row.get("time_window")
    note = {
        "time_constraint": tc,
        "basis": "event_time",
        "data_cutoff_time": data_cutoff_time,
        "window_label": None,
        "lo": None,
        "hi": None,
    }
    if tc == "有":
        if not isinstance(window, dict):
            raise SystemExit("题集 %s 标了「有」时间约束但没有 time_window" % question_row.get("qid"))
        note.update({
            "basis": window.get("basis") or "event_time",
            "window_label": window.get("label"),
            "lo": window.get("lo"),
            "hi": window.get("hi"),
        })
        note["text"] = (
            "数据截止时间：%s\n本题的相对时间判定区间为：%s（%s 至 %s，基准 %s）。\n"
            "回答中涉及时间时，请给出该判定区间与数据截止时间。"
            % (data_cutoff_time, window.get("label"), window.get("lo"), window.get("hi"),
               note["basis"]))
    else:
        note["text"] = (
            "数据截止时间：%s\n本题**不含相对时间表述**，无判定区间；"
            "回答中涉及时间时，只需给出数据截止时间，不得使用截止时间之后的信息。"
            % data_cutoff_time)
    return note


# --------------------------------------------------------------------------
# 图谱侧判据
# --------------------------------------------------------------------------
def _graph_side_ids(trace_row: dict) -> set:
    """最终证据集合里「只在图谱侧出现」的块。

    **题面给的判据经实测不成立**：原判据是「块不在 `candidates_unfiltered` 里」，但
    `candidates_unfiltered` 实际是**向量侧与图谱侧的并集**（PE-01 实测 33 条 ＝ 向量 20 ＋
    图谱 16 − 双命中 3，且 `candidates_unfiltered == candidates_filtered`），最终证据必然
    落在并集内，故该判据在 30 题上给出 0 个块（实测：30 题里只有 1 题因空集而"成立"）。
    按题面授权改用 trace 里已有的、能区分图谱侧新增块的字段：

        `graph_evidence_in_final`（最终证据集合中来自图谱侧的块）

    实测合计 53 个块，与第 7 阶段 `k_selection.json` 的 g=2 复算「入集 53 个（29／30 题）」
    一致；它与 `dual_hit_in_final`（双命中块）互斥，正是「只在图谱侧出现」的语义。
    """
    return set(trace_row.get("graph_evidence_in_final") or [])


# --------------------------------------------------------------------------
# 装配
# --------------------------------------------------------------------------
def assemble_case(trace_row: dict, chunk_index: dict, doc_index: dict,
                  question_row: dict, dataset_meta: dict | None = None) -> dict:
    """把 trace 的一行装配成一份完整的生成输入（确定性；键固定）。"""
    if question_row is None:
        raise SystemExit("题集里找不到 %r" % trace_row.get("qid"))
    dataset_meta = dataset_meta or load_dataset_meta()
    data_cutoff_time = dataset_meta.get("data_cutoff_time") or config.DATA_CUTOFF_TIME

    final_ids = list(trace_row["final_evidence_chunk_ids"])
    graph_side = _graph_side_ids(trace_row)

    evidence = []
    for rank, cid in enumerate(final_ids, 1):
        if cid not in chunk_index:
            raise SystemExit("证据块 %r 不在 chunks.jsonl 里（《21》验收 E5）" % cid)
        ch = chunk_index[cid]
        doc_id = ch["doc_id"]
        if doc_id not in doc_index:
            raise SystemExit("证据块 %r 的 doc_id %r 不在 documents.jsonl 里" % (cid, doc_id))
        doc = doc_index[doc_id]
        evidence.append({
            "rank": rank,                                    # 1 起，呈现序号
            "chunk_id": cid,
            "doc_id": doc_id,
            "token_count": ch["token_count"],                # 取字段值，不重算
            "text": ch["content"],                           # 正文取 chunks.jsonl
            "title": doc.get("title"),
            "source": doc.get("source"),
            "category": doc.get("category"),                 # 供「来源类型」标签使用
            "publish_time": doc.get("publish_time"),
            "url": doc.get("url"),
            "from_graph": cid in graph_side,
        })

    ta = trace_row["token_account"]
    token_account = {
        "text_tokens": sum(item["token_count"] for item in evidence),   # 逐条求和
        "path_tokens": ta["path_tokens"],                  # 以下四项取 trace 读数，不重算
        "event_triple_tokens": ta["event_triple_tokens"],
        "graph_tokens": ta["graph_tokens"],
        "total_tokens": ta["total_tokens"],
    }

    # 图谱载荷**原样透传**（一个字段都不加工；《21》第五节 硬约束 7）
    graph_payload = copy.deepcopy(trace_row["graph_payload"])

    time_note = build_time_note(question_row, data_cutoff_time)

    built = prompt_mod.build_messages(
        question=trace_row["question"],
        dataset_version=dataset_meta.get("dataset_version") or config.DATASET_VERSION,
        data_cutoff_time=data_cutoff_time,
        evidence=evidence,
        graph_payload=graph_payload,
        time_note=time_note["text"],
    )

    # ---- 装配层自检：不成立即抛错退出（不静默截断、不重排、不兜底）----
    if len(evidence) > int(config.K):
        raise SystemExit("%s：证据条数 %d 超过 K=%d"
                         % (trace_row["qid"], len(evidence), config.K))
    if [item["chunk_id"] for item in evidence] != final_ids:
        raise SystemExit("%s：证据顺序与 final_evidence_chunk_ids 不一致（生成侧不得重排）"
                         % trace_row["qid"])
    if token_account["total_tokens"] > int(config.CONTEXT_TOKEN_BUDGET):
        raise SystemExit("%s：装配后 total_tokens=%d 超过 Context Token Budget=%d——"
                         "第 8 阶段不重新裁剪，超限必须报错退出（不得静默截断）"
                         % (trace_row["qid"], token_account["total_tokens"],
                            config.CONTEXT_TOKEN_BUDGET))
    if int(trace_row["k"]) != int(config.K) or int(trace_row["n"]) != int(config.N):
        raise SystemExit("%s：trace 的 K/N＝%s/%s 与导入的四项定值 %s/%s 不一致"
                         % (trace_row["qid"], trace_row["k"], trace_row["n"],
                            config.K, config.N))
    checks = {
        "evidence_le_k": True,
        "order_matches_trace": True,
        "within_budget": True,
        "corpus_lookup_ok": True,
        "k_n_match_config": True,
        "graph_payload_passthrough": graph_payload == trace_row["graph_payload"],
    }

    return {
        "qid": trace_row["qid"],
        "question": trace_row["question"],
        "group": trace_row["group"],
        # 题集标注字段（记录层 question 表的三个字段；《21》第五节 硬约束 13）。
        # `task_type` 是开放式问题识别的**唯一**判据（硬约束 12：不得靠关键词猜）；
        # `gold_hop_depth` 与 `time_constraint` 是题集标注，非测试集题目留空。
        "task_type": question_row.get("task_type"),
        "gold_hop_depth": question_row.get("gold_hop_depth"),
        "k": trace_row["k"],
        "n": trace_row["n"],
        "context_token_budget": trace_row["context_token_budget"],
        # 版本级属性（《21》v1.2 硬约束 7）：答案的「数据截至与判定区间」段由代码拼装时取这两项
        "dataset_version": dataset_meta.get("dataset_version") or config.DATASET_VERSION,
        "data_cutoff_time": data_cutoff_time,
        "evidence": evidence,
        "graph_payload": graph_payload,
        "token_account": token_account,
        "prompt": {"system": built["system"], "user": built["user"],
                   "sha256": built["sha256"]},
        "time_note": time_note,
        "checks": checks,
    }


def assemble_all(trace_rows=None, chunk_index=None, doc_index=None,
                 questions=None, dataset_meta=None) -> list:
    trace_rows = trace_rows if trace_rows is not None else load_trace()
    chunk_index = chunk_index if chunk_index is not None else load_chunks()
    doc_index = doc_index if doc_index is not None else load_documents()
    questions = questions if questions is not None else load_questions()
    dataset_meta = dataset_meta if dataset_meta is not None else load_dataset_meta()
    return [assemble_case(r, chunk_index, doc_index, questions.get(r["qid"]), dataset_meta)
            for r in trace_rows]


# --------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------
def selftest() -> int:
    print("=" * 72)
    print("assemble.py 自检（30 题逐题装配 + PE-01 两次装配自证）")
    print("=" * 72)
    chunks, docs, questions, meta = load_chunks(), load_documents(), load_questions(), load_dataset_meta()
    trace = load_trace()
    print("trace %d 行；chunks 索引 %d；documents 索引 %d；题集 %d"
          % (len(trace), len(chunks), len(docs), len(questions)))
    print("K=%s N=%s 预算=%s（导入自 代码\\检索\\config.py）"
          % (config.K, config.N, config.CONTEXT_TOKEN_BUDGET))

    cases = assemble_all(trace, chunks, docs, questions, meta)
    print("\n%-7s %-4s %-5s %-9s %-8s %-12s %s"
          % ("qid", "证据", "图谱", "prompt字数", "总token", "sha256前12", "时间约束"))
    for c in cases:
        print("%-7s %-4d %-5s %-9d %-8d %-12s %s"
              % (c["qid"], len(c["evidence"]),
                 "是" if c["graph_payload"]["graph_used"] else "否",
                 len(c["prompt"]["system"]) + len(c["prompt"]["user"]),
                 c["token_account"]["total_tokens"],
                 c["prompt"]["sha256"][:12], c["time_note"]["time_constraint"]))
    tot = [c["token_account"]["total_tokens"] for c in cases]
    print("\ntotal_tokens 范围 = %d ～ %d（预算 %d）"
          % (min(tot), max(tot), config.CONTEXT_TOKEN_BUDGET))
    print("证据条数范围 = %d ～ %d（K=%d）"
          % (min(len(c["evidence"]) for c in cases),
             max(len(c["evidence"]) for c in cases), config.K))
    print("图谱侧新增块合计 = %d" % sum(
        1 for c in cases for e in c["evidence"] if e["from_graph"]))

    # PE-01 两次装配自证
    r0 = trace[0]
    a = assemble_case(r0, chunks, docs, questions[r0["qid"]], meta)
    b = assemble_case(r0, chunks, docs, questions[r0["qid"]], meta)
    same = a["prompt"]["sha256"] == b["prompt"]["sha256"]
    print("\nPE-01 两次装配：sha256 %s == %s → %s"
          % (a["prompt"]["sha256"][:12], b["prompt"]["sha256"][:12],
             "相同" if same else "不同"))
    assert same, "PE-01 两次装配的 Prompt SHA-256 必须相同（确定性）"

    print("\n--- PE-01 的 Prompt 全文（前 600 字）---")
    print((a["prompt"]["system"] + "\n\n" + a["prompt"]["user"])[:600])
    print("=" * 72)
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="证据 → Prompt 装配（T4）")
    ap.add_argument("--selftest", action="store_true", help="30 题逐题装配并自证确定性")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    ap.print_help()
    raise SystemExit(0)
