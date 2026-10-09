# -*- coding: utf-8 -*-
"""正式全量对照实验 · 模型调用台账生成器（只读产出、不发动任何模型调用）。

用途
----
把 `对照产出_正式\{组}\answer_trace.jsonl` 与 `对照产出_正式\逐题\{组}\{题号}\answer_trace.jsonl`
里的 `attempts` 数组逐条展开，落成一份**调用级台账** `调用台账.json`：
每一行 = 一次真实的模型请求（含重试），字段为
    时间窗（该题组子进程的起止墙钟时刻，秒级）、组、题号、第几次尝试、
    prompt_tokens／completion_tokens、HTTP 状态、成功与否、空正文标志、耗时秒。

**不含任何凭据**：只读取 trace 里的记账字段，不接触 config.local.json、不读环境变量、
不打印任何 key。本文件**不修改**任何冻结代码、门禁脚本或上游交付物。

用法（0 次模型调用）
-------------------
    python "阶段10-系统测试与对比实验\\对照产出_正式\\建调用台账.py"
"""
import json
import os
import sys
from collections import OrderedDict
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
GROUPS = ("A", "B", "C", "D", "E", "B1")
LEDGER_PATH = os.path.join(HERE, "调用台账.json")


def iter_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def collect_per_question():
    """返回 {组: {题号: 文件mtime}}，以及「逐题」目录里已成功落盘的题号集合。"""
    base = os.path.join(HERE, "逐题")
    per_group = OrderedDict()
    for g in GROUPS:
        d = os.path.join(base, g)
        rows = OrderedDict()
        if os.path.isdir(d):
            for qid in sorted(os.listdir(d)):
                f = os.path.join(d, qid, "answer_trace.jsonl")
                if os.path.isfile(f):
                    rows[qid] = os.path.getmtime(f)
        per_group[g] = rows
    return per_group


def main():
    per_group = collect_per_question()

    calls = []
    totals = OrderedDict()
    for g in GROUPS:
        n_calls = n_ok = n_retry = 0
        tok_p = tok_c = 0
        rows = []
        # 组聚合文件（合并写回的结果，一行一题）；逐题文件作为交叉核对
        agg = os.path.join(HERE, g, "answer_trace.jsonl")
        if os.path.isfile(agg):
            rows = list(iter_jsonl(agg))
        n_rows_agg = len(rows)
        n_rows_perq = len(per_group[g])

        for r in rows:
            qid = r.get("qid")
            attempts = r.get("attempts") or []
            for a in attempts:
                n_calls += 1
                ok = bool(a.get("ok"))
                if ok:
                    n_ok += 1
                if int(a.get("attempt") or 1) > 1:
                    n_retry += 1
                tok_p += int(a.get("prompt_tokens") or 0)
                tok_c += int(a.get("completion_tokens") or 0)
                calls.append(OrderedDict([
                    ("group", g),
                    ("qid", qid),
                    ("attempt", int(a.get("attempt") or 1)),
                    ("ok", ok),
                    ("http_status", a.get("status")),
                    ("finish_reason", a.get("finish_reason")),
                    ("empty_body", bool(a.get("empty_body"))),
                    ("error", a.get("error")),
                    ("prompt_tokens", int(a.get("prompt_tokens") or 0)),
                    ("completion_tokens", int(a.get("completion_tokens") or 0)),
                    ("seconds", float(a.get("seconds") or 0.0)),
                    ("body_chars", int(a.get("body_chars") or 0)),
                    ("reasoning_chars", int(a.get("reasoning_chars") or 0)),
                ]))
        totals[g] = OrderedDict([
            ("n_questions_in_group_file", n_rows_agg),
            ("n_questions_with_per_question_trace", n_rows_perq),
            ("n_calls", n_calls),
            ("n_calls_ok", n_ok),
            ("n_calls_retried", n_retry),
            ("prompt_tokens", tok_p),
            ("completion_tokens", tok_c),
            ("total_tokens", tok_p + tok_c),
        ])

    all_p = sum(t["prompt_tokens"] for t in totals.values())
    all_c = sum(t["completion_tokens"] for t in totals.values())
    all_calls = sum(t["n_calls"] for t in totals.values())

    # 时间窗：以各组逐题 trace 文件的 mtime 的最小／最大值近似该组运行区间
    windows = OrderedDict()
    for g in GROUPS:
        ms = list(per_group[g].values())
        if ms:
            windows[g] = OrderedDict([
                ("first_per_question_trace_mtime", datetime.fromtimestamp(min(ms)).isoformat(timespec="seconds")),
                ("last_per_question_trace_mtime", datetime.fromtimestamp(max(ms)).isoformat(timespec="seconds")),
            ])

    ledger = OrderedDict([
        ("generated_by", "阶段10-系统测试与对比实验/对照产出_正式/建调用台账.py"),
        ("source", "对照产出_正式/{组}/answer_trace.jsonl 与 对照产出_正式/逐题/{组}/{题号}/answer_trace.jsonl 的 attempts 字段"),
        ("credential_note", "本台账不含任何凭据：只读取 trace 的记账字段（tokens／状态／耗时）。"),
        ("time_note", "attempts 里没有绝对墙钟时刻（冻结入口只记相对耗时），故时间窗用逐题 trace 文件的 mtime 近似；秒级。"),
        ("groups", list(GROUPS)),
        ("totals_per_group", totals),
        ("overall", OrderedDict([
            ("n_calls", all_calls),
            ("n_calls_ok", sum(t["n_calls_ok"] for t in totals.values())),
            ("n_calls_retried", sum(t["n_calls_retried"] for t in totals.values())),
            ("prompt_tokens", all_p),
            ("completion_tokens", all_c),
            ("total_tokens", all_p + all_c),
        ])),
        ("time_windows", windows),
        ("calls", calls),
    ])
    with open(LEDGER_PATH, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(ledger, fh, ensure_ascii=False, indent=2, sort_keys=False)

    print("台账已写出：%s" % LEDGER_PATH)
    print("总调用 %d 次（成功 %d、重试 %d）；prompt_tokens=%d、completion_tokens=%d、合计=%d"
          % (all_calls, ledger["overall"]["n_calls_ok"], ledger["overall"]["n_calls_retried"],
             all_p, all_c, all_p + all_c))
    for g in GROUPS:
        t = totals[g]
        print("  %-3s 题数 %3d／逐题 %3d ｜ 调用 %3d ｜ tokens %d"
              % (g, t["n_questions_in_group_file"], t["n_questions_with_per_question_trace"],
                 t["n_calls"], t["total_tokens"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
