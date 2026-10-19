# -*- coding: utf-8 -*-
"""工具\\链路耗时取证.py —— 一次真实问答链路的耗时分解（第三轮 8.3）。

背景
----
后端日志已经输出一行“问答链路耗时分解：backend_wait=…；llm_calls=…；llm_seconds=…；
graph_used=…；evidence=…；out_dir=…”。本脚本把该行涉及的事实**结构化落盘**，
便于写报告、对比优化前后、答辩展示，而不需要手工翻日志。

两种用法
--------
1. 解析已有运行目录（**零成本、只读**）：

       python 工具\\链路耗时取证.py --latest
       python 工具\\链路耗时取证.py --run-dir <qa_runs/ask_C_xxx>

2. 现场跑一次真实问答并解析（会调用模型、会写库）：

       python 工具\\链路耗时取证.py --execute --cleanup

   `--execute` 使用**新的随机 session_id**，向本机 8000 发一次 `/api/qa/ask`；
   结束后 `--cleanup` 只删除本次 session 且 `question_id>30` 的行（级联删除 answer /
   answer_evidence），把数据库恢复到 30/30/293 基线。**不带 `--cleanup` 时不会删除**，
   需要人工用 SQL 清理并在报告中注明。

产物
----
默认写 `交付物/06-实验与评测/系统指标/链路耗时取证_第三轮.json`：
backend_wait、LLM 调用次数/秒数、链路其余部分、检索/图谱/证据/预算读数、门禁失败项、
prompt 字符数与哈希、out_dir、request_id。**不记录问题原文、不记录答案原文、不记录任何密钥。**
HTTP 只保留状态码、request_id、answer_id／question_id、empty／reused 与错误码。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import config  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

RUN_ROOT = os.path.join(config.WORK_DIR, "qa_runs")
DEFAULT_OUT = os.path.join(
    ROOT, "交付物", "06-实验与评测", "系统指标", "链路耗时取证_第三轮.json")
BASE_QUESTION_COUNT = 30


def _read_jsonl_first(path: str):
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                return json.loads(line)
    return None


def list_run_dirs() -> list[str]:
    if not os.path.isdir(RUN_ROOT):
        return []
    dirs = [os.path.join(RUN_ROOT, d) for d in os.listdir(RUN_ROOT)
            if d.startswith("ask_") and os.path.isdir(os.path.join(RUN_ROOT, d))]
    return sorted(dirs, key=lambda p: os.path.getmtime(p))


def latest_run_dir() -> str | None:
    dirs = list_run_dirs()
    return dirs[-1] if dirs else None


def parse_run_dir(run_dir: str, backend_wait: float | None = None,
                  request_id: str | None = None, http: dict | None = None) -> dict:
    """把 qa_run 目录解析成耗时分解与链路读数（只读）。"""
    run_dir = os.path.abspath(run_dir)
    trace = _read_jsonl_first(os.path.join(run_dir, "answer_trace.jsonl")) or {}
    record = _read_jsonl_first(os.path.join(run_dir, "qa_records.jsonl")) or {}
    answer = record.get("answer") if isinstance(record.get("answer"), dict) else {}
    question = record.get("question") if isinstance(record.get("question"), dict) else {}

    attempts = trace.get("attempts") if isinstance(trace.get("attempts"), list) else []
    llm_seconds = [a.get("seconds") for a in attempts
                   if isinstance(a, dict) and isinstance(a.get("seconds"), (int, float))]
    llm_sum = round(sum(float(s) for s in llm_seconds), 3)
    chain_other = None
    if backend_wait is not None:
        chain_other = round(max(float(backend_wait) - llm_sum, 0.0), 3)

    graph_payload = trace.get("graph_payload") if isinstance(trace.get("graph_payload"), dict) else {}
    graph_used = bool(trace.get("graph_used") or graph_payload.get("graph_used")
                      or trace.get("is_graph_extended"))
    token_account = trace.get("token_account") if isinstance(trace.get("token_account"), dict) else {}
    gates = trace.get("gates") if isinstance(trace.get("gates"), dict) else {}
    failures = gates.get("failures") if isinstance(gates.get("failures"), list) else []
    question_text = str(question.get("question_text") or trace.get("question") or "")
    answer_text = str(answer.get("answer_text") or trace.get("answer_text") or "")

    return {
        "run_dir": run_dir,
        "request_id": request_id,
        "backend_wait_seconds": (round(float(backend_wait), 3)
                                 if backend_wait is not None else None),
        "llm_calls": len(llm_seconds),
        "llm_seconds": llm_seconds,
        "llm_total_seconds": llm_sum,
        "chain_other_seconds": chain_other,
        "chain_other_note": ("backend_wait − Σllm_seconds；含检索子进程启动、向量化、图谱查询、"
                             "装配、落库与 HTTP 开销" if chain_other is not None else "未提供墙钟"),
        "attempts": attempts,
        "graph_used": graph_used,
        "graph_event_triples": len(graph_payload.get("event_triples") or []),
        "graph_path_nodes": len(graph_payload.get("graph_path") or []),
        "evidence_count": int(trace.get("evidence_count") or len(trace.get("evidence") or [])),
        "k": trace.get("k"),
        "n": trace.get("n"),
        "context_token_budget": trace.get("context_token_budget"),
        "token_account": token_account,
        "gates_passed": bool(gates.get("passed")),
        "gate_failures": failures,
        "prompt_chars": trace.get("prompt_chars"),
        "prompt_sha256": trace.get("prompt_sha256"),
        "question_chars": len(question_text),
        "question_sha256_16": hashlib.sha256(question_text.encode("utf-8")).hexdigest()[:16],
        "answer_chars": len(answer_text),
        "answer_id": answer.get("answer_id"),
        "question_id": answer.get("question_id"),
        "http": http or {},
        "files": sorted(os.listdir(run_dir)) if os.path.isdir(run_dir) else [],
    }


def _http_ask(question: str, session_id: str, timeout: int = 320) -> tuple[dict, float]:
    payload = json.dumps({"question": question, "session_id": session_id},
                         ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/qa/ask", data=payload, method="POST",
        headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode("utf-8"))
            rid = dict(r.headers).get("x-request-id")
            return {"http": r.status, "body": body, "request_id": rid}, time.perf_counter() - started
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = None
        rid = dict(e.headers).get("x-request-id")
        return {"http": e.code, "body": body, "request_id": rid}, time.perf_counter() - started


def compact_http(raw: dict | None) -> dict:
    """把一次 HTTP 响应裁剪成可落盘的**非正文**读数。

    2026-10-18 第三轮自查：早期版本把整个响应体写进报告，违反了本脚本
    「不记录问题/答案原文」的承诺。这里只保留排障必需的标识与状态。
    """
    raw = raw or {}
    body = raw.get("body") if isinstance(raw.get("body"), dict) else {}
    data = body.get("data") if isinstance(body.get("data"), dict) else {}
    error_code = body.get("code") if isinstance(body.get("code"), int) else None
    return {
        "status": raw.get("http"),
        "request_id": raw.get("request_id"),
        "answer_id": data.get("answer_id"),
        "question_id": data.get("question_id"),
        "empty": data.get("empty"),
        "reused": data.get("reused"),
        "error_code": error_code,
    }


def cleanup_session(session_id: str) -> dict:
    """删除本次脚本产生的 question_id>30 行（级联清理 answer/evidence）。"""
    import db
    before = db.table_counts()
    with db.cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM question WHERE session_id=%s AND question_id>%s",
            (session_id, BASE_QUESTION_COUNT))
        deleted = cur.rowcount
    after = db.table_counts()
    return {"session_id": session_id, "deleted_questions": int(deleted),
            "before": before, "after": after,
            "baseline_restored": (after.get("question") == BASE_QUESTION_COUNT
                                  and after.get("answer") == BASE_QUESTION_COUNT
                                  and after.get("answer_evidence") == 293)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="一次真实问答链路的耗时分解")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--latest", action="store_true", help="解析最近一次 qa_run（默认）")
    group.add_argument("--run-dir", help="解析指定 qa_run 目录")
    group.add_argument("--execute", action="store_true", help="现场跑一次真实问答")
    parser.add_argument("--question", default=None, help="--execute 时的问题（默认取 Q-001 原文）")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--cleanup", action="store_true",
                        help="--execute 后删除本次 session 的 question_id>30 行")
    parser.add_argument("--timeout", type=int, default=320)
    args = parser.parse_args(argv)

    session_id = None
    http_info = None
    backend_wait = None
    request_id = None
    run_dir = args.run_dir

    if args.execute:
        question = args.question
        if not question:
            first = _read_jsonl_first(config.QA_RECORDS_JSONL) or {}
            question = ((first.get("question") or {}).get("question_text")
                        or "长城汽车2023年股票期权激励计划第二个行权期的有效期是什么时间段？")
        session_id = str(uuid.uuid4())
        before_dirs = set(list_run_dirs())
        print("现场提问：session_id=%s，问题长度=%d 字……" % (session_id, len(question)))
        raw_http, backend_wait = _http_ask(question, session_id, args.timeout)
        request_id = raw_http.get("request_id")
        body = raw_http.get("body") or {}
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        http_info = compact_http(raw_http)
        print("HTTP %s，request_id=%s，墙钟=%.2fs，answer_id=%s，empty=%s，reused=%s"
              % (raw_http.get("http"), request_id, backend_wait,
                 data.get("answer_id"), data.get("empty"), data.get("reused")))
        # 给文件系统一点落盘时间，再找本次新增的运行目录
        time.sleep(0.5)
        new_dirs = [d for d in list_run_dirs() if d not in before_dirs]
        if new_dirs:
            run_dir = max(new_dirs, key=lambda p: os.path.getmtime(p))
        elif data.get("reused"):
            print("本次命中复用，没有新的 qa_run 目录。")
        else:
            print("警告：未发现新的 qa_run 目录，仅报告 HTTP 墙钟。")
        if data.get("empty"):
            print("本次为空结果（HTTP 200，不落库）。")

    if not run_dir:
        run_dir = latest_run_dir()
    if not run_dir:
        print("没有可解析的 qa_run 目录。", file=sys.stderr)
        return 2
    if not os.path.isdir(run_dir):
        print("运行目录不存在：%s" % run_dir, file=sys.stderr)
        return 2

    report = parse_run_dir(run_dir, backend_wait=backend_wait,
                           request_id=request_id, http=http_info)
    if args.execute and args.cleanup:
        report["cleanup"] = cleanup_session(session_id)
        if not report["cleanup"]["baseline_restored"]:
            print("警告：清理后计数未回到 30/30/293，请人工核对！", file=sys.stderr)
    elif args.execute:
        report["cleanup"] = {"performed": False,
                             "note": "未带 --cleanup；本次可能写入 question_id>30，请人工清理。"}

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=" * 72)
    print("链路耗时取证")
    print("=" * 72)
    print("  run_dir              = %s" % report["run_dir"])
    print("  request_id           = %s" % report["request_id"])
    print("  backend_wait         = %s s" % report["backend_wait_seconds"])
    print("  llm_calls / seconds  = %d / %s s" % (report["llm_calls"], report["llm_total_seconds"]))
    print("  chain_other          = %s s" % report["chain_other_seconds"])
    print("  graph_used           = %s（事件三元组 %d、路径记录 %d）"
          % (report["graph_used"], report["graph_event_triples"], report["graph_path_nodes"]))
    print("  evidence / K / N     = %d / %s / %s"
          % (report["evidence_count"], report["k"], report["n"]))
    print("  token total / budget = %s / %s"
          % (report["token_account"].get("total_tokens"), report["context_token_budget"]))
    print("  gates_passed         = %s（失败项：%s）"
          % (report["gates_passed"], report["gate_failures"] or "无"))
    if "cleanup" in report:
        c = report["cleanup"]
        print("  清理                 = %s" % (
            "已删除 %d 条 question，计数=%s" % (c.get("deleted_questions"), c.get("after"))
            if c.get("performed", True) else c.get("note")))
    print("  报告                 = %s" % out)
    print("=" * 72)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断。", file=sys.stderr)
        raise SystemExit(130)
