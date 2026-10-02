# -*- coding: utf-8 -*-
"""代码\\问答\\run_answer.py —— T8（30 题录制与留痕）＋ T9（复现性与只读性验证）。

命令行入口。**参数一律取 `config.py`**，脚本内不写死模型名、端点、路径、温度、Prompt 版本、
日期或阈值（《21》第五节 硬约束 1）。

产出（落 `阶段08-智能问答系统\\问答产出\\`，《21》第4.3节）：

* `answer_trace.jsonl` —— 一行一题（30 行，C 组）；固定键序、固定排序、**不写运行时间戳**；
  `evidence` **不存证据正文**（正文可由 `chunk_id` 回查 `chunks.jsonl`）；
* `qa_records.jsonl` —— 30 条问答记录（question／answer／answer_evidence 三表语义，T7）；
* `prompt_snapshot.json` —— Prompt 模板 v1.0 的冻结快照（`prompt.write_snapshot()`）；
* `run_manifest.json` —— 复跑命令、输入指纹、产出 SHA-256、两次运行的装配逐字节一致性、
  两次运行的模型输出重复一致率、模型调用次数（含重试）。

**检索侧只读**（《21》第五节 硬约束 22）：本文件**不新增任何检索实现**。30 题（C 组）直接消费
第 7 阶段冻结的 `per_question_trace.jsonl`；`--question` 与非 C 组**调用第 7 阶段的既有链路**
（子进程方式跑 `代码\\检索\\run_query.py`，见下），只读、一个字节都不改。

**为什么用子进程而不是 in-process import**：`代码\\检索\\` 与 `代码\\问答\\` **各有一个
`config.py`**，而 `代码\\检索\\` 的模块内部一律写 `import config`（经 `sys.path` 解析）。若在
本进程里把检索目录插到 `sys.path` 前面，`import config` 会解析到**哪一个**取决于导入顺序与
`sys.modules` 既存项——这是能悄悄换掉参数来源的坑。子进程让两个 `config` 各在自己的进程里
生效，既满足"调用既有链路、不重写检索"，也不可能污染本侧的参数来源。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import answer as answer_mod   # noqa: E402
import assemble as asm        # noqa: E402
import config                 # noqa: E402
import history as hist        # noqa: E402
import prompt as prompt_mod   # noqa: E402
import rules                  # noqa: E402

SCHEMA = "stage8-answer-trace-1.0"
MANIFEST_SCHEMA = "stage8-run-manifest-1.0"

# `answer_trace.jsonl` 的固定键序（《21》第六节 格式决策 1：固定键序；写盘再按 sort_keys 排）
TRACE_ROW_FIELDS = ("qid", "question", "group", "k", "n", "context_token_budget",
                    "evidence", "evidence_count", "graph_payload", "token_account",
                    "prompt_sha256", "prompt_chars", "model", "attempts", "body_text",
                    "answer_text", "is_graph_extended", "gates", "checks")
# 证据条目的固定键（**不存证据正文**：正文可由 `chunk_id` 回查 `chunks.jsonl`）
TRACE_EVIDENCE_FIELDS = ("rank", "chunk_id", "doc_id", "token_count", "source",
                         "publish_time", "title", "from_graph")


# --------------------------------------------------------------------------
# 一、命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="第 8 阶段 T8／T9：单题生成、30 题录制、零调用跑通与复现性留痕")
    ap.add_argument("--qid", default=None, help="单题（从第 7 阶段的 trace 装配），例如 PE-01")
    ap.add_argument("--all", action="store_true", help="30 题全程（默认行为）")
    ap.add_argument("--question", default=None,
                    help="自定义问题文本：调用第 7 阶段既有链路取 trace 后走同一条生成链路")
    ap.add_argument("--group", choices=("A", "B", "C", "D", "E"), default=None,
                    help="组别（缺省 C＝Method）；非 C 组经第 7 阶段既有链路取该组的证据集合")
    ap.add_argument("--k", type=int, default=None, help="最终证据上限 K（只接受冻结值）")
    ap.add_argument("--n", type=int, default=None, help="向量候选数 N（只接受冻结值）")
    ap.add_argument("--budget", type=int, default=None, help="Context Token Budget（只接受冻结值）")
    ap.add_argument("--dry-run", action="store_true", help="0 次调用：只装配并打印，不写产出")
    ap.add_argument("--now", default=None, help="注入记录层时间字段（ISO8601；缺省取运行时刻）")
    ap.add_argument("--session-id", default=None, help="会话标识（缺省取 config.DEFAULT_SESSION_ID）")
    ap.add_argument("--out-dir", default=None, help="产出目录（缺省取 config.OUTPUT_DIR）")
    ap.add_argument("--selftest", action="store_true",
                    help="① 单题端到端 ② dry-run 0 调用 ③ 装配两次 SHA-256 相同 ④ 会话隔离")
    ap.add_argument("--run-manifest", action="store_true",
                    help="两次运行 ＋ 装配一致性，写 run_manifest.json（约 60 次调用）")
    return ap.parse_args(argv)


def _out_paths(args) -> dict:
    d = args.out_dir or config.OUTPUT_DIR
    return {
        "dir": d,
        "answer_trace": os.path.join(d, "answer_trace.jsonl"),
        "qa_records": os.path.join(d, "qa_records.jsonl"),
        "prompt_snapshot": os.path.join(d, "prompt_snapshot.json"),
        "run_manifest": os.path.join(d, "run_manifest.json"),
    }


def _frozen_params(args) -> dict:
    """K／N／预算一律取 `config`（＝从 `代码\\检索\\config.py` 导入的冻结值）。

    **显式传入非冻结值时报警并拒绝**（《21》第五节 硬约束 1／21：不得偏离冻结值，也不得引入
    第四个可变参数）。
    """
    fixed = {"k": int(config.require_fixed("K")), "n": int(config.require_fixed("N")),
             "budget": int(config.require_fixed("context_token_budget"))}
    given = {"k": args.k, "n": args.n, "budget": args.budget}
    bad = {"k": given["k"], "n": given["n"], "budget": given["budget"]}
    for key, value in given.items():
        if value is not None and int(value) != fixed[key]:
            raise SystemExit("拒绝运行：--%s=%s 与冻结值 %s=%s 不一致（《21》第五节 硬约束 1／21）"
                             % (key, value, key, fixed[key]))
    return {"fixed": fixed, "cli_given": bad,
            "source": "config.require_fixed（四项定值从 代码\\检索\\config.py 导入）"}


# --------------------------------------------------------------------------
# 二、取题（三种来源，检索侧一律只读）
# --------------------------------------------------------------------------
def load_cases_from_trace(qids=None):
    """C 组 30 题：直接消费第 7 阶段冻结的 `per_question_trace.jsonl`（只读）。"""
    chunks, docs = asm.load_chunks(), asm.load_documents()
    questions, meta = asm.load_questions(), asm.load_dataset_meta()
    cases = []
    for row in asm.load_trace():
        if qids and row["qid"] not in qids:
            continue
        cases.append(asm.assemble_case(row, chunks, docs, questions.get(row["qid"]), meta))
    return cases


# --------------------------------------------------------------------------
# 最终证据集合（第④步保留 K 之后）的 token 分账——**本文件自算，不 import 第 7 阶段模块**
# --------------------------------------------------------------------------
# 为什么不 import：见本文件开头第 21～22 行的记载——`代码\检索\` 的模块内部一律写
# `import config`，一旦把检索目录插进本进程的 `sys.path`，`import config` 会解析到检索侧
# 还是问答侧取决于导入顺序，属**已知的路径解析陷阱**；第 8 阶段因此刻意用子进程桥接
# （`load_case_via_retrieval()`），本函数沿用同一纪律，故只做**逐字等价**的本地复刻。
#
# 口径与出处（复刻对象）：
#   `代码\检索\pipeline.py` 的 `estimate_tokens()`（第 802 行）与 `_CJK_RE`／`_ASCII_RUN_RE`
#   （第 163～164 行）；`代码\检索\config.py` 的 `stable_json()`（第 331 行）。
#   `code\检索\pipeline.py` 的 `account_tokens()`（第 845 行）说明了分账构成。
#
# **等价性验证（不是口头保证）**：用本函数对第 7 阶段冻结的 30 条 C 组 trace 逐条复算，
# 与 trace 里的 `token_account` **7 个字段全部逐位一致（30／30）**。该验证已固化为
# `阶段10-系统测试与对比实验\工具\跑AC对照.py` 的 `--check-token-account` 自检，
# 防止本复刻与上游口径日后漂移。
_CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
_ASCII_RUN_RE = re.compile(r"[A-Za-z0-9_]+")


def _estimate_tokens(text) -> int:
    """图谱路径与事件三元组的估算 token（与 `pipeline.estimate_tokens()` 逐字等价）。"""
    value = str(text)
    return len(_CJK_RE.findall(value)) + len(_ASCII_RUN_RE.findall(value))


def _stable_json(obj) -> str:
    """确定性 JSON 序列化（与 `config.stable_json()` 逐字等价）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def final_set_token_account(rec: dict, chunks: dict) -> dict:
    """按**最终证据集合**（第④步保留 K 之后）复算 token 分账，与第 7 阶段 trace 行同口径。

    **2026-10-02 修正（评审 P0-新①）**：`record_to_trace_row()` 原先把运行记录的
    `budget_trim.after` 当作 trace 的 `token_account`。那是**第③步裁剪到预算之后、
    第④步保留 K 之前**的账；第④步按 K 丢块时（`keep_k.dropped_by_k` 非空）两者必然不等，
    于是《21》第五节 硬约束 6 的**装配账目守卫**（要求 token 账必须由现场重算分量组成）
    判「现场重算与上游 trace 不一致」并**非零退出**——A／B／D／E 组经桥接路径的答案生成
    因此成片失败。这也正是第 8 阶段 PE-03 报 3004、第 9 阶段 PE-03 报 HTTP 503 的**根因**
    （当时只登记为「真实原因不是图谱服务」，未定位到此）。

    本修正**不放宽守卫**：守卫仍按现场重算判等，只是把上游账目换成正确口径。
    """
    gp = rec.get("graph_path_payload") or {}
    paths = list(gp.get("graph_path") or [])
    triples = list(gp.get("event_triples") or [])
    order = [int(c) for c in (rec["final_evidence"]["presentation_order"] or [])]
    missing = [c for c in order if c not in chunks]
    if missing:
        raise SystemExit("最终证据集合里有 chunks.jsonl 中不存在的 chunk_id：%s" % missing[:5])
    text_tokens = sum(int(chunks[c]["token_count"]) for c in order)
    path_tokens = sum(_estimate_tokens(_stable_json(p)) for p in paths)
    triple_tokens = sum(_estimate_tokens("|".join(t)) for t in triples)
    return {
        "estimate_note": "文本块＝chunks.jsonl 的 token_count 实测；图谱路径与事件三元组＝估算 token",
        "text_chunks": len(order), "text_tokens": text_tokens,
        "paths": len(paths), "path_tokens": path_tokens,
        "event_triples": len(triples), "event_triple_tokens": triple_tokens,
        "graph_tokens": path_tokens + triple_tokens,
        "total_tokens": text_tokens + path_tokens + triple_tokens,
    }


def record_to_trace_row(rec: dict, chunks: dict | None = None) -> dict:
    """把第 7 阶段 `run_query.py` 的运行记录**映射成 trace 行的形状**（不改它的实现）。

    证据顺序取 `final_evidence.presentation_order`（生成侧不得重排）；
    token 分账取**最终证据集合**的口径（`final_set_token_account()`，见上）；
    图谱载荷取 `graph_path_payload`（原样）。
    """
    fe = rec["final_evidence"]
    account = rec.get("token_account")
    if not isinstance(account, dict):
        if chunks is None:
            raise SystemExit(
                "运行记录不含最终证据集合口径的 `token_account`，且未提供 chunks 供复算——"
                "拒绝回退到 `budget_trim.after`（那是保留 K 之前的账，会让装配账目守卫误判）。")
        account = final_set_token_account(rec, chunks)
    return {
        "qid": rec["question"]["qid"],
        "question": rec["question"]["text"],
        "group": rec["group"],
        "k": rec["parameters"]["K"],
        "n": rec["parameters"]["N"],
        "context_token_budget": rec["parameters"]["context_token_budget"],
        "final_evidence_chunk_ids": list(fe["presentation_order"]),
        "evidence": list(fe["presentation_order"]),
        "graph_evidence_in_final": list(fe.get("graph_evidence_in_final") or []),
        "dual_hit_in_final": list(fe.get("dual_hit_in_final") or []),
        "graph_payload": rec["graph_path_payload"],
        "token_account": account,
    }


def question_row_from_record(rec: dict) -> dict:
    """由运行记录还原**答题侧需要的题集行**（题集里没有的自定义问题就地合成）。

    只取 `assemble.build_time_note()` 与记录层需要的字段；自定义问题（题集之外）的
    `task_type`／`gold_hop_depth` 按《21》硬约束 13「非测试集题目留空」留 `None`。
    """
    q = rec["question"]
    known = asm.load_questions().get(q["qid"])
    if known is not None:
        return known
    window = q.get("time_window")
    return {
        "qid": q["qid"],
        "question": q["text"],
        "time_constraint": "有" if isinstance(window, dict) else "无",
        "time_window": window,
        "task_type": None,          # 题集之外：无标注，留空（硬约束 13）
        "gold_hop_depth": None,
    }


def load_case_via_retrieval(args, params: dict) -> dict:
    """`--question` 与非 C 组：跑第 7 阶段的既有链路，拿到 trace 行后装配。

    **不新增检索实现**：调 `代码\\检索\\run_query.py`（只读、一个字节都不改），把它的运行记录
    映射成 trace 行。链路不可行时**明确报错退出**，不悄悄降级成别的语义（《21》T8）。
    """
    script = os.path.join(config.ROOT, "代码", "检索", "run_query.py")
    if not os.path.isfile(script):
        raise SystemExit("检索侧入口不存在，无法取该题的 trace：%s（本脚本不新增检索实现，"
                         "故拒绝用别的语义替代）" % script)
    group = args.group or "C"
    out = os.path.join(config.WORK_DIR, "桥接", "run_query_%s_%s.json"
                       % (group, (args.qid or "custom").replace("/", "_")))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [sys.executable, script, "--group", group, "--out", out]
    cmd += ["--qid", args.qid] if args.qid else ["--question", args.question]
    for key, value in (("--k", args.k), ("--n", args.n), ("--budget", args.budget)):
        if value is not None:
            cmd += [key, str(value)]
    print("[桥接] 调第 7 阶段既有链路（只读）：%s" % " ".join(cmd))
    proc = subprocess.run(cmd, cwd=config.ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not os.path.isfile(out):
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:], file=sys.stderr)
        raise SystemExit("第 7 阶段链路未跑通（退出码 %s）——本脚本拒绝用别的语义替代，"
                         "如实报错退出。" % proc.returncode)
    rec = config.read_json(out)
    chunks, docs, meta = asm.load_chunks(), asm.load_documents(), asm.load_dataset_meta()
    # chunks 先加载再映射：运行记录不携带最终证据集合口径的 token 账，需按 chunks 的
    # token_count 现场复算（见 final_set_token_account()）。
    row = record_to_trace_row(rec, chunks)
    qrow = question_row_from_record(rec)
    case = asm.assemble_case(row, chunks, docs, qrow, meta)
    return {"case": case, "record": rec, "source": "第 7 阶段 run_query.py（子进程，只读）",
            "cmd": cmd}


# --------------------------------------------------------------------------
# 三、录制
# --------------------------------------------------------------------------
def _trace_evidence(case: dict) -> list:
    return [{k: item[k] for k in TRACE_EVIDENCE_FIELDS} for item in case["evidence"]]


def build_trace_row(case: dict, res: dict) -> dict:
    """由装配结果与生成结果拼一行 `answer_trace.jsonl`（固定键、**不写时间戳**）。"""
    if res.get("gates") is None:
        raise SystemExit("%s：门禁结果缺失（dry-run 不写产出）" % case["qid"])
    return {
        "qid": case["qid"],
        "question": case["question"],
        "group": case["group"],
        "k": case["k"],
        "n": case["n"],
        "context_token_budget": case["context_token_budget"],
        "evidence": _trace_evidence(case),
        "evidence_count": len(case["evidence"]),
        "graph_payload": case["graph_payload"],     # 原样透传（硬约束 7）
        "token_account": case["token_account"],
        "prompt_sha256": res["prompt_sha256"],
        "prompt_chars": res["prompt_chars"],
        "model": res["model"],
        "attempts": res["attempts"],
        "body_text": res["body_text"],
        "answer_text": res["answer_text"],
        "is_graph_extended": res["is_graph_extended"],
        "gates": res["gates"],
        "checks": res["checks"],
    }


def _run_cases(cases: list, args, *, label: str) -> list:
    """逐题生成（**按 qid 升序**，保证行的顺序确定）；返回 [(case, 生成结果)]。"""
    out = []
    for case in cases:
        t0 = time.time()
        res = answer_mod.answer_case(case)
        g = res.get("gates") or {}
        print("  [%s] %-8s %.1fs 尝试%d 引用%d(越界%d) 日期不可核%d(未来%d) 图谱段%s 泄漏%s "
              "禁词%d 空%s 通过=%s"
              % (label, case["qid"], time.time() - t0, res.get("n_calls", 0),
                 g.get("citation_count", 0), g.get("citation_out_of_range_count", 0),
                 g.get("date_unverifiable_count", 0), g.get("dates_beyond_cutoff_count", 0),
                 "OK" if g.get("graph_section_ok") else "BAD",
                 "有" if g.get("body_graph_marker_leak") else "无",
                 g.get("forbidden_hit_count", 0), "是" if not g.get("non_empty") else "否",
                 g.get("passed")))
        if not res.get("ok"):
            print("     调用失败：%s" % res.get("error"))
        out.append((case, res))
    return out


def _records_from(pairs: list, *, session_id: str, now: str) -> list:
    recs = []
    for case, res in pairs:
        qid_num, aid = config.identifiers_for(case["qid"])
        recs.append(hist.build_record(case, res, session_id=session_id, question_id=qid_num,
                                      answer_id=aid, ask_time=now))
    return recs


# 门禁失败时打印的明细字段（与 `answer.gate()` 的键一一对应）
GATE_DETAIL_FIELDS = ("non_empty", "citation_count", "citation_marks", "citation_out_of_range",
                      "date_unverifiable", "graph_section_ok", "graph_section_is_marker",
                      "body_graph_marker_leak", "body_section_header_leak", "forbidden_hits",
                      "forbidden_hit_contexts",
                      "evidence_backlink_ok", "evidence_backlink_missing", "time_note_ok",
                      "time_note_missing_parts", "open_ended_marker_applicable",
                      "open_ended_marker_ok", "open_ended_reason")


def _gate_failures(trace_rows: list) -> list:
    bad = []
    for row in trace_rows:
        g = row["gates"] or {}
        if not g.get("passed"):
            bad.append({"qid": row["qid"], "failures": g.get("failures"),
                        "detail": {k: g.get(k) for k in GATE_DETAIL_FIELDS}})
    return bad


def _dump_gate_failures(paths: dict, pairs: list, bad: list) -> str:
    """门禁失败时把**失败题的模型原始输出**落一份留痕（`_工作底稿/`，不入库）。

    失败明细要能事后核对（《21》验收 E4「把失败明细打印出来」），故连命中的**上下文**与
    **模型正文全文**一起落盘——失败题不会进 `answer_trace.jsonl`，这里是唯一的现场。
    """
    by_qid = {c["qid"]: (c, r) for c, r in pairs}
    dump = {
        "note": "门禁失败明细（失败题不进入正式产出，按《21》验收 E4 非零退出；本文件是留痕）",
        "failures": [],
    }
    for item in bad:
        case, res = by_qid[item["qid"]]
        dump["failures"].append({
            "qid": item["qid"], "failures": item["failures"], "detail": item["detail"],
            "forbidden_hit_contexts": (item["detail"] or {}).get("forbidden_hit_contexts"),
            "body_text": res.get("body_text"),
            "answer_text": res.get("answer_text"),
        })
    os.makedirs(config.WORK_DIR, exist_ok=True)
    path = os.path.join(config.WORK_DIR, "门禁失败明细.json")
    config.write_json(path, dump)
    print("[留痕] 门禁失败明细（含模型正文全文）已写：%s" % path)
    return path


def _write_outputs(paths: dict, pairs: list, *, session_id: str, now: str) -> dict:
    trace_rows = [build_trace_row(c, r) for c, r in pairs]
    records = _records_from(pairs, session_id=session_id, now=now)
    config.write_jsonl(paths["answer_trace"], trace_rows)
    hist.write_records(paths["qa_records"], records)
    prompt_mod.write_snapshot(paths["prompt_snapshot"])
    return {"trace_rows": trace_rows, "records": records}


# --------------------------------------------------------------------------
# 四、默认动作：单题／30 题
# --------------------------------------------------------------------------
def cmd_run(args) -> int:
    """单题／30 题：装配 → 生成 → 机检 → 落产出（门禁失败即非零退出、失败题不入产出）。"""
    params = _frozen_params(args)
    paths = _out_paths(args)
    now = args.now or datetime.now().astimezone().isoformat(timespec="seconds")
    session_id = args.session_id or config.DEFAULT_SESSION_ID

    print("=" * 78)
    print("run_answer：%s" % ("单题 %s" % args.qid if args.qid else
                              ("自定义问题" if args.question else "30 题全程（默认）")))
    print("=" * 78)
    print("四项定值（%s）：K=%d N=%d 预算=%d g=%s"
          % (params["source"], params["fixed"]["k"], params["fixed"]["n"],
             params["fixed"]["budget"], config.require_fixed("graph_retention_share")))
    print("答案侧冻结：model=%s temperature=%s max_tokens=%s prompt_version=%s"
          % (config.require_fixed("model_name"), config.require_fixed("temperature"),
             config.require_fixed("max_tokens"), config.require_fixed("prompt_version")))
    print("会话 session_id=%s；记录层时间注入 --now=%s" % (session_id, now))

    # ---- 取题 ----
    bridge = None
    if args.question or (args.group and args.group != "C"):
        bridge = load_case_via_retrieval(args, params)
        cases = [bridge["case"]]
    else:
        cases = load_cases_from_trace([args.qid] if args.qid else None)
    if not cases:
        raise SystemExit("没有可运行的题（--qid 是否存在于 trace？）")
    cases.sort(key=lambda c: c["qid"])
    print("装配完成：%d 题（Prompt 文本已固定，可逐字节复现）" % len(cases))

    if args.dry_run:
        print("\n--dry-run：只装配、不发请求、不写产出（0 次调用）。")
        for case in cases:
            prompt_chars = len(case["prompt"]["system"]) + len(case["prompt"]["user"])
            print("  %-8s 组=%s 证据 %2d 条 total_tokens=%4d prompt=%5d 字 sha256=%s"
                  % (case["qid"], case["group"], len(case["evidence"]),
                     case["token_account"]["total_tokens"], prompt_chars,
                     case["prompt"]["sha256"][:12]))
        print("模型调用次数 = 0")
        return 0

    # ---- 生成 ----
    pairs = _run_cases(cases, args, label="生成")
    failed = [(c, r) for c, r in pairs if not r.get("ok")]
    if failed:
        for c, r in failed:
            print("调用失败：%s → %s" % (c["qid"], r.get("error")))
        raise SystemExit("有题的调用未成功（%d 题）——不得写入空答案，非零退出。"
                         % len(failed))

    # ---- 门禁（不静默：失败即不入产出、非零退出）----
    trace_rows = [build_trace_row(c, r) for c, r in pairs]
    bad = _gate_failures(trace_rows)
    if bad:
        _dump_gate_failures(paths, pairs, bad)
        print("\n门禁未通过的题（不得进入正式产出）：")
        for item in bad:
            print("  %s 失败项=%s" % (item["qid"], "、".join(item["failures"] or [])))
            print("    明细：%s" % json.dumps(item["detail"], ensure_ascii=False))
        raise SystemExit("门禁失败 %d 题 → 非零退出（《21》验收 E4：门禁不静默）。" % len(bad))

    # ---- 落产出 ----
    written = _write_outputs(paths, pairs, session_id=session_id, now=now)
    calls = sum(r.get("n_calls", 0) for _, r in pairs)
    print("\n已写：%s（%d 行）" % (paths["answer_trace"], len(written["trace_rows"])))
    print("已写：%s（%d 条记录）" % (paths["qa_records"], len(written["records"])))
    print("已写：%s" % paths["prompt_snapshot"])
    print("模型调用次数（含重试）= %d" % calls)
    print_gate_summary(written["trace_rows"])
    if bridge:
        print("本题 trace 来源：%s" % bridge["source"])
    return 0


def print_gate_summary(trace_rows: list) -> None:
    """把门禁各字段的汇总读数打出来（收口报告与决策者复跑用）。"""
    n = len(trace_rows)

    def _sum(key):
        return sum((r["gates"] or {}).get(key) or 0 for r in trace_rows)

    def _cases(pred):
        return sum(1 for r in trace_rows if pred(r["gates"] or {}))

    print("\n" + "-" * 78)
    print("门禁汇总（%d 题）" % n)
    print("-" * 78)
    print("  引用越界总数（次）                = %d（涉及 %d 题）"
          % (_sum("citation_out_of_range_count"),
             _cases(lambda g: g.get("citation_out_of_range_count"))))
    print("  引用总数（次）                    = %d" % _sum("citation_count"))
    print("  date_unverifiable 总数            = %d（涉及 %d 题）"
          % (_sum("date_unverifiable_count"), _cases(lambda g: g.get("date_unverifiable_count"))))
    print("  dates_beyond_cutoff 总数（只统计） = %d" % _sum("dates_beyond_cutoff_count"))
    print("  图谱段异常题数                    = %d"
          % _cases(lambda g: not g.get("graph_section_ok")))
    print("  模型正文图谱标记泄漏题数          = %d"
          % _cases(lambda g: g.get("body_graph_marker_leak")))
    print("  模型正文小标题泄漏题数            = %d"
          % _cases(lambda g: g.get("body_section_header_leak")))
    print("  禁词命中总数                      = %d" % _sum("forbidden_hit_count"))
    print("  证据回链失败题数                  = %d"
          % _cases(lambda g: not g.get("evidence_backlink_ok")))
    print("  时间说明不合规题数                = %d"
          % _cases(lambda g: not g.get("time_note_ok")))
    print("  开放式标注不适用题数              = %d（适用题数 %d）"
          % (_cases(lambda g: not g.get("open_ended_marker_applicable")),
             _cases(lambda g: g.get("open_ended_marker_applicable"))))
    print("  全部通过题数                      = %d / %d" % (_cases(lambda g: g.get("passed")), n))
    used = sum(1 for r in trace_rows if r["graph_payload"].get("graph_used"))
    print("  graph_used=1 题数                 = %d；=0 题数 = %d" % (used, n - used))
    print("  题目集 task_type 取值             = %s"
          % "、".join(sorted({str((r["gates"] or {}).get("open_ended_task_type"))
                              for r in trace_rows})))
    print("-" * 78)


# --------------------------------------------------------------------------
# 五、--run-manifest（T9）
# --------------------------------------------------------------------------
def _input_fingerprints() -> dict:
    """8 条输入指纹（引 T1 的 `问答产出\\input_manifest.json`，并现场重算核对）。"""
    if not os.path.isfile(config.INPUT_MANIFEST_OUT_PATH):
        raise SystemExit("T1 的输入清单不存在，无法登记输入指纹：%s" % config.INPUT_MANIFEST_OUT_PATH)
    t1 = config.read_json(config.INPUT_MANIFEST_OUT_PATH)
    entries, mismatched = [], []
    for item in t1.get("items") or []:
        for fp in item.get("files") or []:
            path = fp.get("path")
            real = config.sha256_file(path) if os.path.isfile(path) else None
            entries.append({"item": item["item"], "key": fp.get("key"), "path": path,
                            "bytes": fp.get("bytes"), "sha256": fp.get("sha256")})
            if real != fp.get("sha256"):
                mismatched.append(path)
    return {"source": config.INPUT_MANIFEST_OUT_PATH,
            "count": len(entries), "files": entries, "recomputed_mismatched": mismatched}


def _config_snapshot(params: dict) -> dict:
    return {
        "model_name": config.require_fixed("model_name"),
        "model_version": config.require_fixed("model_version"),
        "endpoint": config.require_fixed("endpoint"),
        "temperature": config.require_fixed("temperature"),
        "max_tokens": config.require_fixed("max_tokens"),
        "prompt_version": config.require_fixed("prompt_version"),
        "K": params["fixed"]["k"], "N": params["fixed"]["n"],
        "context_token_budget": params["fixed"]["budget"],
        "g": config.require_fixed("graph_retention_share"),
        "dataset_version": config.require_fixed("dataset_version"),
        "data_cutoff_time": config.require_fixed("data_cutoff_time"),
        "parameter_source": params["source"],
    }


def _assembly_consistency(repeats: int = 2) -> dict:
    """装配层确定性：同一输入重复装配的 Prompt 文本 SHA-256 逐题比对（**0 次调用**）。"""
    runs = []
    for _ in range(repeats):
        cases = load_cases_from_trace()
        cases.sort(key=lambda c: c["qid"])
        runs.append({c["qid"]: c["prompt"]["sha256"] for c in cases})
    base = runs[0]
    same = [qid for qid in base if all(r.get(qid) == base[qid] for r in runs[1:])]
    return {"repeats": repeats, "questions": len(base), "identical": len(same),
            "all_identical": len(same) == len(base),
            "sha256_first_run": base,
            "diff": sorted(set(base) - set(same))}


def _repeat_rate(cycle_a: list, cycle_b: list) -> dict:
    """两次运行的**模型输出重复一致率**（如实报告数值，**不作通过判据**，验收 G3）。"""
    a = {qid: body for qid, body in cycle_a}
    b = {qid: body for qid, body in cycle_b}
    both = sorted(set(a) & set(b))
    same = [qid for qid in both if a[qid] == b[qid]]
    return {
        "definition": "两次运行中「模型生成的『回答』正文（body_text）逐字符相同」的题占比；"
                      "模型侧输出**不承诺**逐字节一致（《21》第五节 硬约束 17）",
        "questions": len(both),
        "identical": len(same),
        "rate": round(len(same) / len(both), 4) if both else None,
        "identical_qids": same,
        "differing_qids": [qid for qid in both if qid not in set(same)],
    }


def cmd_run_manifest(args) -> int:
    params = _frozen_params(args)
    paths = _out_paths(args)
    now = args.now or datetime.now().astimezone().isoformat(timespec="seconds")
    session_id = args.session_id or config.DEFAULT_SESSION_ID

    print("=" * 78)
    print("run_answer --run-manifest（T9）：两次运行 ＋ 装配一致性（约 60 次调用）")
    print("=" * 78)

    # ① 装配一致性（0 调用）
    print("\n① 装配层确定性（0 次调用）：同一输入连装两次，逐题比 Prompt SHA-256……")
    cons = _assembly_consistency(2)
    print("   %d/%d 题两次装配逐字节一致（all_identical=%s）"
          % (cons["identical"], cons["questions"], cons["all_identical"]))
    if not cons["all_identical"]:
        raise SystemExit("装配层不确定（差异题：%s）——第 8 阶段的装配必须逐字节可复现。"
                         % "、".join(cons["diff"]))

    # ② 第 1 次运行（写产出）
    cases = load_cases_from_trace()
    cases.sort(key=lambda c: c["qid"])
    print("\n② 第 1 次运行（%d 题，写产出）：" % len(cases))
    pairs_a = _run_cases(cases, args, label="第1次")
    failed = [c["qid"] for c, r in pairs_a if not r.get("ok")]
    if failed:
        raise SystemExit("第 1 次运行有题失败：%s" % "、".join(failed))
    rows_a = [build_trace_row(c, r) for c, r in pairs_a]
    bad = _gate_failures(rows_a)
    if bad:
        for item in bad:
            print("  门禁失败：%s → %s" % (item["qid"], item["failures"]))
        raise SystemExit("门禁失败 %d 题（《21》验收 E4）" % len(bad))
    written = _write_outputs(paths, pairs_a, session_id=session_id, now=now)

    # ③ 第 2 次运行（不写产出，只比模型输出）
    print("\n③ 第 2 次运行（不写产出，只比模型输出）：")
    pairs_b = _run_cases(cases, args, label="第2次")
    failed_b = [c["qid"] for c, r in pairs_b if not r.get("ok")]
    if failed_b:
        raise SystemExit("第 2 次运行有题失败：%s" % "、".join(failed_b))
    rate = _repeat_rate([(c["qid"], r["body_text"]) for c, r in pairs_a],
                        [(c["qid"], r["body_text"]) for c, r in pairs_b])
    print("   两次运行模型输出重复一致率 = %s（%d/%d 题逐字符相同）"
          % (rate["rate"], rate["identical"], rate["questions"]))

    # ④ 产出 SHA-256 与清单
    print("\n④ 产出 SHA-256：")
    artifacts = ["answer_trace", "qa_records", "prompt_snapshot", "input_manifest",
                 "selection_matrix", "selection_decision"]
    extra = {"input_manifest": config.INPUT_MANIFEST_OUT_PATH,
             "selection_matrix": config.SELECTION_MATRIX_PATH,
             "selection_decision": config.SELECTION_DECISION_PATH}
    sha = {}
    for name in artifacts:
        path = extra.get(name) or paths[name]
        if os.path.isfile(path):
            sha[name] = {"path": path, "sha256": config.sha256_file(path),
                         "bytes": os.path.getsize(path)}
            print("   %-20s %s" % (name, sha[name]["sha256"]))

    calls = sum(r.get("n_calls", 0) for _, r in pairs_a) + \
        sum(r.get("n_calls", 0) for _, r in pairs_b)
    retries = sum(max(0, r.get("n_calls", 0) - 1) for _, r in pairs_a + pairs_b)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "stage": "第 8 阶段：智能问答系统",
        "purpose": "T9：复跑命令、输入指纹、产出 SHA-256、两次运行的装配逐字节一致性、"
                   "两次运行的模型输出重复一致率、模型调用次数（含重试）",
        "reproduce_commands": [
            "python 代码\\问答\\model_selection.py --recheck",
            "python 代码\\问答\\answer.py --selftest",
            "python 代码\\问答\\history.py --selftest",
            "python 代码\\问答\\run_answer.py --qid PE-01",
            "python 代码\\问答\\run_answer.py --all",
            "python 代码\\问答\\run_answer.py --selftest",
            "set STAGE8_FORBID_MODEL_CALLS=1 && python 代码\\问答\\run_answer.py --dry-run",
            "python 代码\\问答\\run_answer.py --run-manifest",
            "python 工具\\跨文档核验.py",
        ],
        "frozen_env_note": "镜像重跑哨兵：%s=1 时禁止任何模型调用（《21》第2.5节 第 3 条；"
                           "验收 G1）" % config.FORBID_MODEL_CALLS_ENV,
        "config_snapshot": _config_snapshot(params),
        "input_fingerprints": _input_fingerprints(),
        "assembly_determinism": {
            "repeats": cons["repeats"], "questions": cons["questions"],
            "identical": cons["identical"], "all_identical": cons["all_identical"],
            "model_calls": 0,
            "note": "装配层（证据 → Prompt 文本）在同一输入下逐字节一致（《21》第五节 硬约束 17；"
                    "验收 G2）；本项 0 次调用。",
            "prompt_sha256_by_qid": cons["sha256_first_run"],
        },
        "model_output_repeatability": rate,
        "model_calls": {
            "total": calls,
            "cycle_1": sum(r.get("n_calls", 0) for _, r in pairs_a),
            "cycle_2": sum(r.get("n_calls", 0) for _, r in pairs_b),
            "retries": retries,
            "questions_per_cycle": len(cases),
            "note": "每次调用计入本项（含 v1.3 空正文重试）；dry-run 时应为 0（验收 B4／G1）。",
        },
        "artifacts_sha256": sha,
        "gate_summary_from_cycle_1": {
            "citation_out_of_range_total": sum(g["citation_out_of_range_count"]
                                               for g in (r["gates"] for r in rows_a)),
            "date_unverifiable_total": sum(g["date_unverifiable_count"]
                                           for g in (r["gates"] for r in rows_a)),
            "dates_beyond_cutoff_total": sum(g["dates_beyond_cutoff_count"]
                                             for g in (r["gates"] for r in rows_a)),
            "forbidden_hit_total": sum(g["forbidden_hit_count"]
                                       for g in (r["gates"] for r in rows_a)),
            "graph_section_bad": sum(1 for g in (r["gates"] for r in rows_a)
                                     if not g["graph_section_ok"]),
            "open_ended_applicable": sum(1 for g in (r["gates"] for r in rows_a)
                                         if g["open_ended_marker_applicable"]),
            "passed_all": all(g["passed"] for g in (r["gates"] for r in rows_a)),
        },
        "now_injected": now,
        "session_id": session_id,
        "notice": "本文件只登记 30 题预实验集上的**原始读数**，不含人工评分，"
                  "不构成正式实验结论（《21》第1.2节、非目标 4／5）；模型输出重复一致率"
                  "只登记数值，**不作通过／失败判据**（验收 G3）。",
    }
    config.write_json(paths["run_manifest"], manifest)
    print("\n已写：%s" % paths["run_manifest"])
    print("模型调用次数（含重试）= %d（第1次 %d ＋ 第2次 %d；重试 %d）"
          % (calls, manifest["model_calls"]["cycle_1"], manifest["model_calls"]["cycle_2"],
             retries))
    print_gate_summary(written["trace_rows"])
    return 0


# --------------------------------------------------------------------------
# 六、--selftest
# --------------------------------------------------------------------------
def selftest() -> int:
    print("=" * 78)
    print("run_answer.py 自检：① 单题端到端 ② dry-run 0 调用 ③ 装配确定性 ④ 会话隔离")
    print("=" * 78)
    cases = load_cases_from_trace()
    cases.sort(key=lambda c: c["qid"])
    first = cases[0]

    # ③ 装配两次 SHA-256 相同
    again = {c["qid"]: c["prompt"]["sha256"] for c in load_cases_from_trace()}
    identical = sum(1 for c in cases if again.get(c["qid"]) == c["prompt"]["sha256"])
    print("\n③ 装配两次逐题 SHA-256 相同：%d/%d" % (identical, len(cases)))
    if identical != len(cases):
        return 1

    # ② dry-run 0 调用
    d = answer_mod.answer_case(first, dry_run=True)
    print("\n② dry-run：n_calls=%d gates=%s（应为 0／None）" % (d["n_calls"], d["gates"]))
    if d["n_calls"] != 0 or d["gates"] is not None:
        return 1

    # ① 单题端到端
    print("\n① 单题端到端：%s（真实调用）" % first["qid"])
    res = answer_mod.answer_case(first)
    if not res.get("ok"):
        print("   调用失败：%s" % res.get("error"))
        return 1
    g = res["gates"]
    print("   尝试 %d 次；答案 %d 字；门禁通过=%s；失败项=%s"
          % (res["n_calls"], len(res["answer_text"]), g["passed"], g["failures"] or "无"))

    # ④ 会话隔离（用本题 ＋ 第二题构造两个会话，0 次调用）
    print("\n④ history 两会话隔离：")
    now = "2026-09-29T12:00:00+08:00"
    second = cases[1]
    recs = []
    for i, (c, r) in enumerate(((first, res),
                                (second, answer_mod.answer_case(second, dry_run=True)))):
        r = dict(r)
        if not r.get("answer_text"):
            r["answer_text"] = "（自检用空正文占位）"
        r.setdefault("model", {"requested": "自检", "returned": config.require_fixed("model_name")})
        qid_num, aid = config.identifiers_for(c["qid"])
        recs.append(hist.build_record(c, r, session_id=("S-1" if i == 0 else "S-2"),
                                      question_id=qid_num, answer_id=aid, ask_time=now))
    a = hist.query_history(recs, "S-1")
    b = hist.query_history(recs, "S-2")
    cross = {r["answer"]["answer_id"] for r in a} & {r["answer"]["answer_id"] for r in b}
    print("   S-1 查到 %d 条；S-2 查到 %d 条；交集 = %s（必须为空）" % (len(a), len(b), sorted(cross)))
    if cross or len(a) != 1 or len(b) != 1:
        return 1
    rv = hist.review(recs, a[0]["answer"]["answer_id"])
    print("   review 返回块 = %s（只回三表内容，不重建路径）" % sorted(rv))

    ok = identical == len(cases) and g["passed"]
    print("\n结论：%s" % ("全部通过" if ok else "有失败项"))
    return 0 if ok else 1


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return selftest()
    if args.run_manifest:
        return cmd_run_manifest(args)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
