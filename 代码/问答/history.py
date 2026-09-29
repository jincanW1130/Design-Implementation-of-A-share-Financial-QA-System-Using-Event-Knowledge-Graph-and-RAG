# -*- coding: utf-8 -*-
"""代码\\问答\\history.py —— T7：记录层与历史问答（FR-06，六表语义的 JSONL 形态）。

**只落 JSONL**（《21》非目标 2：不建库、不写 DDL、不连数据库、不新增表）。一条记录 ＝
一条 question ＋ 其 answer ＋ 其 answer_evidence 数组，字段名**逐字取《10-系统总体设计
（第四阶段）》第4.4.1节 表 4-6**，不新增字段、不改字段名（《21》第五节 硬约束 13）。

| 表 | 字段 |
| --- | --- |
| question | `question_id`／`session_id`／`question_text`／`task_type`／`gold_hop_depth`／`time_constraint`／`ask_time` |
| answer | `answer_id`／`question_id`／`answer_text`／`graph_path`／`model_name`／`prompt_version`／`is_graph_extended`／`create_time` |
| answer_evidence | `answer_id`／`chunk_id`／`doc_id`／`rank`／`evidence_type` |

关键纪律：

* **`(answer_id, chunk_id)` 联合唯一**（硬约束 14）：同一答案下同一文本块只一条记录；`rank`
  为 1 起连续（验收 F2）。
* **`answer.graph_path`**：`graph_used` 为假时为 `null`；为真时是**原样 JSON 文本**——
  `graph_payload.graph_path` 一个字段都不加工、不重排、不渲染（硬约束 7、验收 F4）。
* **`evidence_type` 取四类之一**（硬约束 15），与 `prompt.source_type_label` **同源**，
  不自造类别。
* **会话隔离**（硬约束 16）：按 `session_id` 过滤，不同会话互不可见；第一版不启用登录。
* **回看不重渲染图谱路径**（硬约束 16、验收 F4）：`review()` 只还原三表内容，
  `graph_path` 只回原文 JSON 文本，**不得**重建／渲染任何路径视图。
* `ask_time`／`create_time` 由命令行 `--now` 注入（格式决策 5；本模块不读系统时间）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble as asm        # noqa: E402
import config                 # noqa: E402
import prompt as prompt_mod   # noqa: E402

# 三张表的字段名（**逐字取《10》表 4-6**；`--selftest` 与验收 F1 按这三份清单逐字段比对）
QUESTION_FIELDS = ("question_id", "session_id", "question_text", "task_type",
                   "gold_hop_depth", "time_constraint", "ask_time")
ANSWER_FIELDS = ("answer_id", "question_id", "answer_text", "graph_path", "model_name",
                 "prompt_version", "is_graph_extended", "create_time")
ANSWER_EVIDENCE_FIELDS = ("answer_id", "chunk_id", "doc_id", "rank", "evidence_type")


# --------------------------------------------------------------------------
# 一、构造记录
# --------------------------------------------------------------------------
def _graph_path_text(case: dict):
    """`answer.graph_path` 的取值：**原样 JSON 文本**；未使用图谱扩展时为 `null`。

    直接对 `case["graph_payload"]["graph_path"]` 做 `json.dumps`（`ensure_ascii=False`）——
    `json.loads` 保序、`json.dumps` 也保序，故文本与原载荷**逐字符一致**；**不排序、不渲染、
    不加工**（硬约束 7）。落成**字符串**还有一个作用：`write_jsonl(..., sort_keys=True)`
    只会重排本行的顶层键，不会动这个字符串内部的键序。
    """
    gp = case.get("graph_payload") or {}
    if not gp.get("graph_used"):
        return None
    return json.dumps(gp.get("graph_path") or [], ensure_ascii=False)


def build_record(case: dict, answer_result: dict, *, session_id: str, question_id: str,
                 answer_id: str, ask_time: str) -> dict:
    """由装配结果与生成结果构造**一条**记录（question ＋ answer ＋ answer_evidence）。

    返回的顶层只有 `question`／`answer`／`answer_evidence` 三个键，不含任何其他业务字段
    （《21》验收 F1「无缺、无多余业务字段」）。
    """
    gp = case.get("graph_payload") or {}
    graph_used = bool(gp.get("graph_used"))
    model = answer_result.get("model") or {}
    model_name = model.get("returned") or model.get("requested") or config.require_fixed("model_name")
    tn = case.get("time_note") or {}

    question = {
        "question_id": question_id,
        "session_id": session_id,
        "question_text": case["question"],
        # 以下三个是题集标注字段；非测试集题目（题集里没有的题）留空
        "task_type": case.get("task_type"),
        "gold_hop_depth": case.get("gold_hop_depth"),
        "time_constraint": tn.get("time_constraint"),
        "ask_time": ask_time,
    }
    answer = {
        "answer_id": answer_id,
        "question_id": question_id,
        "answer_text": answer_result.get("answer_text") or "",
        "graph_path": _graph_path_text(case),
        "model_name": model_name,
        "prompt_version": prompt_mod.PROMPT_VERSION,
        # 硬约束 8 的取值口径是 0／1；与 `graph_payload.graph_used` 三方一致（验收 E2）
        "is_graph_extended": 1 if graph_used else 0,
        # `create_time` 与 `ask_time` 同由 `--now` 注入（格式决策 5：本模块不读系统时间）
        "create_time": ask_time,
    }
    seen = set()
    evidence_rows = []
    for item in case["evidence"]:
        cid = item["chunk_id"]
        if (answer_id, cid) in seen:            # 硬约束 14：(answer_id, chunk_id) 联合唯一
            raise SystemExit("记录层：answer_id=%s 下 chunk_id=%r 重复（联合唯一约束）"
                             % (answer_id, cid))
        seen.add((answer_id, cid))
        evidence_rows.append({
            "answer_id": answer_id,
            "chunk_id": cid,
            "doc_id": item["doc_id"],
            "rank": item["rank"],               # 1 起连续，与呈现顺序一致
            "evidence_type": prompt_mod.source_type_label(item),   # 四类之一，与 prompt 同源
        })
    return {"question": question, "answer": answer, "answer_evidence": evidence_rows}


# --------------------------------------------------------------------------
# 二、落盘与读取
# --------------------------------------------------------------------------
def _dump_line(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append_records(path: str, records: list) -> str:
    """把记录**追加**写进 JSONL（一行一条；UTF-8、不带 BOM、固定键序）。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        for row in records:
            f.write(_dump_line(row) + "\n")
    return path


def write_records(path: str, records: list) -> str:
    """整表重写（确定性；`--all` 用一次覆盖写，避免追加造成重复行）。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in records:
            f.write(_dump_line(row) + "\n")
    os.replace(tmp, path)
    return path


def load_records(path: str) -> list:
    """读 JSONL；文件不存在返回空表（第一版不建库，空表是合法状态）。"""
    if not os.path.isfile(path):
        return []
    return [row for row in config.iter_jsonl(path)]


# --------------------------------------------------------------------------
# 三、历史问答（只按会话过滤；回看不重渲染图谱路径）
# --------------------------------------------------------------------------
def query_history(records: list, session_id: str) -> list:
    """按会话查询：**只返回该 `session_id`** 的记录，按 `ask_time` 升序（硬约束 16）。

    `ask_time` 相同时按 `question_id`、再按 `answer_id` 升序，保证顺序确定。
    """
    mine = [r for r in records if (r.get("question") or {}).get("session_id") == session_id]
    mine.sort(key=lambda r: ((r.get("question") or {}).get("ask_time") or "",
                             (r.get("question") or {}).get("question_id") or "",
                             (r.get("answer") or {}).get("answer_id") or ""))
    return mine


def review(records: list, answer_id: str) -> dict:
    """回看一条答案：**只还原 question／answer／answer_evidence 三表内容**（验收 F4）。

    `graph_path` 只回**原文 JSON 文本**（`answer` 表里存的字符串原样带出），
    **不得**重建／渲染路径视图——故本函数的返回值里没有任何"路径渲染"产物
    （无节点名、无 `start—关系→end` 之类的成品），也没有 `graph_payload` 字段。
    找不到 `answer_id` 时返回 `found=False`。
    """
    for row in records:
        ans = row.get("answer") or {}
        if ans.get("answer_id") == answer_id:
            return {
                "found": True,
                "question": dict(row.get("question") or {}),
                "answer": dict(ans),                       # graph_path 原样带出
                "answer_evidence": [dict(e) for e in (row.get("answer_evidence") or [])],
            }
    return {"found": False, "question": None, "answer": None, "answer_evidence": []}


def list_answers(records: list, session_id: str) -> list:
    """某会话的回看目录（题号／提问时间／答案 id／是否使用图谱扩展）——**不含路径**。"""
    out = []
    for row in query_history(records, session_id):
        q, a = row.get("question") or {}, row.get("answer") or {}
        out.append({"question_id": q.get("question_id"), "ask_time": q.get("ask_time"),
                    "answer_id": a.get("answer_id"), "question_text": q.get("question_text"),
                    "is_graph_extended": a.get("is_graph_extended"),
                    "evidence_count": len(row.get("answer_evidence") or [])})
    return out


# --------------------------------------------------------------------------
# 四、自检（0 次模型调用：用装配结果 ＋ 合成的回答结果构造记录）
# --------------------------------------------------------------------------
def _fixture(cases: dict, qid: str) -> tuple:
    """构造一条 (case, answer_result)，**不调用模型**（合成的 `body_text` 只用于自检）。"""
    case = cases[qid]
    body = "自检用合成正文，引用 [证据1]；日期 %s。" % case["time_note"]["data_cutoff_time"][:10]
    answer_text = prompt_mod.compose_answer(
        body=body, evidence=case["evidence"], graph_payload=case["graph_payload"],
        dataset_version=case["dataset_version"], data_cutoff_time=case["data_cutoff_time"],
        time_note=case["time_note"])
    return case, {"answer_text": answer_text, "model": {"requested": "自检", "returned": "自检"}}


def selftest() -> int:
    print("=" * 72)
    print("history.py 自检（T7：记录层与会话隔离；0 次模型调用）")
    print("=" * 72)
    cases = {c["qid"]: c for c in asm.assemble_all()}
    qids = sorted(cases)[:2]
    if len(qids) < 2:
        raise SystemExit("题集不足两题，无法做会话隔离自检")
    ask_time = "2026-09-29T12:00:00+08:00"          # 自检用固定时间（不读系统时间）

    records = []
    for i, qid in enumerate(qids):
        case, ar = _fixture(cases, qid)
        qid_num, aid = config.identifiers_for(qid)
        records.append(build_record(
            case, ar, session_id=("S-A" if i == 0 else "S-B"),
            question_id=qid_num, answer_id=aid, ask_time=ask_time))
    print("已构造 %d 条记录（会话 %s）：%s"
          % (len(records), "、".join(sorted({r["question"]["session_id"] for r in records})),
             "、".join(r["answer"]["answer_id"] for r in records)))

    # ① 两会话隔离
    a = query_history(records, "S-A")
    b = query_history(records, "S-B")
    print("\n① 两会话隔离：")
    print("   会话 S-A 查到 %d 条：%s" % (len(a), [r["answer"]["answer_id"] for r in a]))
    print("   会话 S-B 查到 %d 条：%s" % (len(b), [r["answer"]["answer_id"] for r in b]))
    id_a = {r["answer"]["answer_id"] for r in a}
    id_b = {r["answer"]["answer_id"] for r in b}
    print("   两个会话的 answer_id 交集 = %s（必须为空）" % sorted(id_a & id_b))
    assert len(a) == 1 and len(b) == 1 and not (id_a & id_b), "会话隔离失败"
    assert query_history(records, "S-NOT-EXIST") == []

    # ② 联合唯一（同一 answer_id 下 chunk_id 不重复、rank 连续）
    print("\n② (answer_id, chunk_id) 联合唯一与 rank 连续：")
    ok_all = True
    for row in records:
        ans_id = row["answer"]["answer_id"]
        ev = row["answer_evidence"]
        cids = [e["chunk_id"] for e in ev]
        ranks = [e["rank"] for e in ev]
        unique = len(cids) == len(set(cids))
        continuous = ranks == list(range(1, len(ranks) + 1))
        all_belongs = all(e["answer_id"] == ans_id for e in ev)
        ok_all = ok_all and unique and continuous and all_belongs
        print("   %s：证据 %d 条｜chunk_id 唯一=%s｜rank 连续（1..%d）=%s｜answer_id 归属一致=%s"
              % (ans_id, len(ev), unique, len(ranks), continuous, all_belongs))
    assert ok_all, "联合唯一或 rank 连续性失败"

    # ③ 回看不重渲染路径（只回 graph_path 原文；返回值里没有路径重建成品）
    print("\n③ 回看不重渲染图谱路径：")
    rv = review(records, records[0]["answer"]["answer_id"])
    print("   返回块 = %s（只允许 found／question／answer／answer_evidence）" % sorted(rv))
    assert sorted(rv) == ["answer", "answer_evidence", "found", "question"], sorted(rv)
    assert sorted(rv["question"]) == sorted(QUESTION_FIELDS), sorted(rv["question"])
    assert sorted(rv["answer"]) == sorted(ANSWER_FIELDS), sorted(rv["answer"])
    assert all(sorted(e) == sorted(ANSWER_EVIDENCE_FIELDS) for e in rv["answer_evidence"])
    # 原文可比：review 回的 graph_path 文本与载荷里的 graph_path 逐字符一致
    src = cases[qids[0]]["graph_payload"]
    if rv["answer"]["graph_path"] is None:
        print("   graph_path = null（本题未使用图谱扩展）")
        assert not src.get("graph_used")
    else:
        rebuilt = json.loads(rv["answer"]["graph_path"])
        print("   graph_path 是原样 JSON 文本（%d 字），与载荷逐字符一致=%s"
              % (len(rv["answer"]["graph_path"]),
                 rv["answer"]["graph_path"] == json.dumps(src["graph_path"], ensure_ascii=False)))
        assert rebuilt == src["graph_path"]
    # 回看**不得新建**任何路径视图：把 `answer_text` 排除在外（它是**存下来的答案原文**，
    # 里面本来就含开发生成时由代码拼装的图谱段，不是回看时重建的），其余的返回内容里
    # 不得出现载荷字段名或渲染特征串。
    scan = {"question": rv["question"], "answer_evidence": rv["answer_evidence"],
            "answer.graph_path": rv["answer"]["graph_path"]}
    blob = json.dumps(scan, ensure_ascii=False)
    for banned in ("graph_payload", "event_triples", "->", "→", "role=", "source_chunk_id=",
                   "confidence=", "关系（"):
        assert banned not in blob, "回看返回值里出现了路径重建成品：%s" % banned
    print("   自证：`answer_text` 之外的返回内容不含 graph_payload／event_triples 字段，")
    print("         也不含箭头、「role=／source_chunk_id=／confidence=／关系（」等渲染特征串")
    assert review(records, "A-NOT-EXIST")["found"] is False

    # ④ 字段名逐字覆盖
    print("\n④ 字段名逐字覆盖（《10》表 4-6）：")
    print("   question       = %s" % "、".join(QUESTION_FIELDS))
    print("   answer         = %s" % "、".join(ANSWER_FIELDS))
    print("   answer_evidence= %s" % "、".join(ANSWER_EVIDENCE_FIELDS))
    print("\n   一条记录的结构示例（前 300 字）：")
    print("   " + _dump_line(records[0])[:300])
    print("=" * 72)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="T7：记录层与历史问答（FR-06）")
    ap.add_argument("--selftest", action="store_true", help="会话隔离／联合唯一／回看不重渲染")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
