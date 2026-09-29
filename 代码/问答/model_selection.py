# -*- coding: utf-8 -*-
"""代码\\问答\\model_selection.py —— T2：三模型对照选型实验（**链外工具**）。

**只换模型，其余全同**（《21》第九节 执行顺序）：复用 `assemble.assemble_case` 的同一份
装配结果、同一 Prompt 文本、同一 `temperature`（config.ANSWER["temperature"]）、
同一 `max_tokens`。对 30 题逐题向 3 个候选各发一次请求（＝90 次调用），用标准库
`urllib`（**不新增任何依赖**）。

产出：

* `问答产出\\selection_matrix.jsonl` —— 一行 ＝ 一题一模型；固定键序、固定排序、
  **不写运行时间戳**（`seconds` 是实测读数，按《21》第2.5节 要求记录）；
* `问答产出\\selection_decision.json` —— 按《21》第2.5节 第 4 条改判规则逐条给出判定与
  执行证据；另含 Moonshot／kimi-k3 的排除证据。

**不做人工 0／1／2 评分**（《21》非目标 5），只落原始读数与机检读数。

**判据单一来源（2026-09-29，T5／T6 执行时）**：日期来源可核的判据与禁词表已抽到 `rules.py`，
本文件 import 它、删掉自己的重复实现，使**答案侧（`answer.py` 的机检门禁）与选型侧（本文件）
用同一套口径**。抽取前后本文件的产出**逐字节不变**（`--recheck` 前后对
`selection_matrix.jsonl` 与 `selection_decision.json` 取 SHA-256 比对，见收口报告）。

《21》**v1.2** 的三处修订在本文件里的落点：

1. **日期门禁＝日期来源可核**（修正 1）：不再把「晚于 `data_cutoff_time` 的日期」一律判越界
   ——证据原文里本来就写着未来的日期（PE-01 的「行权期有效期为2026年9月11日-2027年1月25日」），
   按旧口径会把正确引用原文的答案判成幻觉。现按硬约束 10 的三条来源判定
   （`allowed_dates()`）；落盘 `dates_mentioned`／`date_unverifiable`（＝越界）／
   `dates_beyond_cutoff`（**只统计、不计入失败**）。
2. **答案四段只有「回答」由模型生成**（修正 2）：本文件用 `prompt.compose_answer()` 拼装
   证据段／图谱段／时间段，并把「模型正文里出现系统专用字样」落成独立字段
   `body_graph_marker_leak`（旧判据「搜到『图谱／路径』字样就算通过」会漏判）。
3. **`max_tokens` 1024 → 2048**（修正 3）：三候选同值；`finish_reason` 一并落盘，
   用于识别 length 截断。

《21》**v1.3** 的两处修订在本文件里的落点：

1. **`max_tokens` 2048 → 16384**（配置修正）：推理型模型的推理 token 与正文 token **共用**
   该上限，2048 档下三个候选都会出现「推理吃光预算、正文为空」的行，2048 的「空答案率」
   反映的是配置而非模型能力，用它做选型读数是无效比较。16384 使最吃推理的题也稳定
   `finish=stop`（证据见 `config.ANSWER["max_tokens"]` 旁注）。
2. **空正文重试规则**（技术稳健性，不是实验变量）：某次请求返回**空正文**时，以**完全相同
   的配置**再请求一次（同模型、同 temperature、同 max_tokens、同 Prompt 文本、同证据集合）；
   **两次尝试都落进 `attempts`**（每次的时延／`finish_reason`／`prompt_tokens`／
   `completion_tokens`／是否空正文都能逐次看出），**两次都为空**才记 `empty_answer=1`。
   该规则对三个候选一律适用，故不引入新的实验变量。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assemble as asm        # noqa: E402
import config                 # noqa: E402
import prompt as prompt_mod   # noqa: E402
import rules                  # noqa: E402

# 机检：引用编号 `[证据n]`（《21》第五节 硬约束 9、第六节 格式决策 3）——
# 正则与解析**在 `rules.py`**（判据单一来源），此处只取别名。
CITATION_RE = rules.CITATION_RE

# 日期判据（提取日期／可核来源集合／截止日期部分）、引用解析与禁词表**已抽到 `rules.py`**，
# 本文件改为 import（判据单一来源：答案侧与选型侧同一套口径）。抽取前后本文件的产出
# 逐字节不变，证据见 `--recheck` 的前后 SHA-256（报告里给出）。
extract_dates = rules.extract_dates                                    # noqa: F401
allowed_dates = rules.allowed_dates                                    # noqa: F401
_cutoff_date = rules.cutoff_date                                       # noqa: F401
_cite_marks = rules.citation_marks                                     # noqa: F401


def machine_check(*, answer_text: str, body_text: str, case: dict) -> dict:
    """机检读数（v1.2 口径）。

    **作用域**：引用编号与「图谱标记泄漏」两项只看**模型生成的「回答」正文**（答案四段里
    唯一由模型写的段，其余三段由代码拼装，按构造即可核）；日期一项按《21》验收 E1 的
    字面「答案中每个年月日」看**答案全文**，且允许来源已覆盖证据正文／证据语料元数据／
    截止时间／判定区间端点，故代码拼装的三段不会产生假阳性。

    日期口径（v1.2 修正 1）：`date_unverifiable` 才是**越界**（三条来源都不满足）；
    `dates_beyond_cutoff` **只统计、不计入失败**，用于如实登记「证据原文里明写的未来日期」
    ——例如 PE-01 证据正文里的「行权期有效期为2026年9月11日-2027年1月25日」。
    """
    body = body_text or ""
    ev_count = len(case["evidence"])
    graph_used = bool(case["graph_payload"]["graph_used"])

    # ① 引用编号越界（作用域：模型正文）——判据在 rules.py（单一来源）
    cites = rules.citation_marks(body)
    oob = sorted({n for n in cites if n < 1 or n > ev_count})

    # ② 日期来源可核（《21》v1.2 硬约束 10／验收 E1）——判据在 rules.py（单一来源）
    dg = rules.date_gate(answer_text, case)       # 答案全文（E1 字面口径）
    allowed = rules.allowed_dates(case)
    body_dates = rules.extract_dates(body)        # 仅模型正文（细读数）
    unver_body = sorted(d for d in body_dates if d not in allowed)

    # ③ 图谱三方一致（D4／E2）：系统拼装的图谱段 ＋ 模型正文不得泄漏系统字样
    secs = prompt_mod.split_answer_sections(answer_text)
    gsec = (secs.get(prompt_mod.ANSWER_SECTIONS[2]) or "")
    has_path = bool(gsec.strip()) and (prompt_mod.NO_GRAPH_MARKER not in gsec)
    if graph_used:
        section_ok = has_path
    else:
        section_ok = gsec.strip() == prompt_mod.NO_GRAPH_MARKER
    leak = prompt_mod.NO_GRAPH_MARKER in body
    # 正文里出现系统段的三个小标题（不含「回答」二字本身——它是常用词，会误报）
    header_leak = any(t in body for t in prompt_mod.ANSWER_SECTIONS[1:])

    def _iso(ds):
        return [d.isoformat() for d in ds]

    return {
        "citation_marks": len(cites),
        "citation_out_of_range": oob,
        "citation_out_of_range_count": len(oob),
        "dates_mentioned": dg["dates_mentioned"],
        "date_unverifiable": dg["date_unverifiable"],
        "date_unverifiable_count": dg["date_unverifiable_count"],
        "body_dates_mentioned": _iso(sorted(body_dates)),
        "body_date_unverifiable": _iso(unver_body),
        "body_date_unverifiable_count": len(unver_body),
        "dates_beyond_cutoff": dg["dates_beyond_cutoff"],
        "dates_beyond_cutoff_count": dg["dates_beyond_cutoff_count"],
        "graph_used": graph_used,
        "system_graph_section_ok": bool(section_ok),
        "system_graph_section_has_path": bool(has_path),
        "system_graph_section_is_marker": gsec.strip() == prompt_mod.NO_GRAPH_MARKER,
        "body_graph_marker_leak": bool(leak),
        "body_section_header_leak": bool(header_leak),
        "empty_answer": len(body.strip()) == 0,
    }


def call_model(cand: dict, system: str, user: str, key: str) -> dict:
    """一次非流式调用（标准库 urllib）。返回原始读数；**不回显密钥**。"""
    payload = {
        "model": cand["model"],
        "temperature": config.require_fixed("temperature"),
        "max_tokens": config.require_fixed("max_tokens"),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        cand["endpoint"].rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=config.require_fixed("timeout_seconds")) as r:
            body = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "seconds": round(time.time() - t0, 3),
                "error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])}
    except Exception as e:
        return {"ok": False, "status": None, "seconds": round(time.time() - t0, 3),
                "error": "%s: %s" % (type(e).__name__, e)}
    seconds = round(time.time() - t0, 3)
    try:
        obj = json.loads(body)
        msg = (obj.get("choices") or [{}])[0].get("message") or {}
        usage = obj.get("usage") or {}
        content = msg.get("content") or ""
        return {
            "ok": True, "status": status, "seconds": seconds,
            "model_returned": obj.get("model"),
            "finish_reason": (obj.get("choices") or [{}])[0].get("finish_reason"),
            "answer_text": content,
            "empty_body": len(content.strip()) == 0,       # v1.3 空正文重试规则的判据
            "reasoning_chars": len(msg.get("reasoning_content") or ""),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
        }
    except Exception as e:
        return {"ok": False, "status": status, "seconds": seconds,
                "error": "响应解析失败 %s: %s；body 前 200 字：%s"
                         % (type(e).__name__, e, body[:200])}


# 机检结果落到矩阵行里的字段名（`run()` 与 `--recheck` 共用同一份清单，避免两处漂移）
MC_ROW_FIELDS = [
    "citation_marks", "citation_out_of_range", "citation_out_of_range_count",
    "dates_mentioned", "date_unverifiable", "date_unverifiable_count",
    "body_dates_mentioned", "body_date_unverifiable", "body_date_unverifiable_count",
    "dates_beyond_cutoff", "dates_beyond_cutoff_count",
    "graph_used", "system_graph_section_ok", "system_graph_section_has_path",
    "system_graph_section_is_marker", "body_graph_marker_leak",
    "body_section_header_leak", "empty_answer",
]


def apply_machine_check(row: dict, case: dict) -> dict:
    """按 `row` 里已落盘的 `answer_text`／`body_text` **离线重算**机检字段（不改模型输出）。

    机检是 (answer_text, body_text, case) 的纯函数，故可在不重新调用模型的前提下重算——
    用于修正检查器自身的口径缺陷（模型原始输出一个字节都不变）。
    """
    if not row.get("ok"):
        return row
    mc = machine_check(answer_text=row.get("answer_text") or "",
                       body_text=row.get("body_text") or "", case=case)
    for key in MC_ROW_FIELDS:
        row[key] = mc[key]
    return row


def recheck() -> int:
    """`--recheck`：只按已落盘的矩阵重算机检字段并重写矩阵与选型结论（**零模型调用**）。"""
    if not os.path.isfile(config.SELECTION_MATRIX_PATH):
        raise SystemExit("矩阵不存在，无法 --recheck：%s" % config.SELECTION_MATRIX_PATH)
    rows = [dict(r) for r in config.iter_jsonl(config.SELECTION_MATRIX_PATH)]
    cases = {c["qid"]: c for c in asm.assemble_all()}
    missing = sorted({r["qid"] for r in rows} - set(cases))
    if missing:
        raise SystemExit("矩阵里的 qid 在装配结果里找不到：%s" % "、".join(missing))
    for r in rows:
        apply_machine_check(r, cases[r["qid"]])
    rows.sort(key=lambda r: (r["qid"], r["candidate"]))
    config.write_jsonl(config.SELECTION_MATRIX_PATH, rows)
    calls = sum(len(r.get("attempts") or []) for r in rows)
    decision = build_decision(rows, list(cases.values()), calls, None)
    config.write_json(config.SELECTION_DECISION_PATH, decision)
    print("--recheck：按已落盘的模型输出重算机检字段，重写 %s（%d 行）与 %s"
          % (config.SELECTION_MATRIX_PATH, len(rows), config.SELECTION_DECISION_PATH))
    print("未发出任何请求（调用计数 0）；模型输出未做任何改写。")
    print_summary(decision["aggregates"])
    print("\n选型结论：%s" % decision["verdict"])
    return 0


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def _attempt(cand: dict, case: dict, key: str, attempts: list) -> dict:
    """发**一次**请求，并把这一次的读数追加进 `attempts`（逐次记录，便于事后看出是第几次）。

    每次尝试记录：序号／是否成功／时延／HTTP 状态／错误／`finish_reason`／是否空正文／
    `prompt_tokens`／`completion_tokens`／推理字数。**不回显密钥**。
    """
    r = call_model(cand, case["prompt"]["system"], case["prompt"]["user"], key)
    attempts.append({
        "attempt": len(attempts) + 1,
        "ok": r["ok"],
        "seconds": r["seconds"],
        "status": r.get("status"),
        "error": r.get("error"),
        "finish_reason": r.get("finish_reason"),
        # 空正文判据只在「请求成功但 content 为空串」时有意义；失败行记 None，不混为「空答案」
        "empty_body": (bool(r.get("empty_body")) if r["ok"] else None),
        "prompt_tokens": r.get("prompt_tokens"),
        "completion_tokens": r.get("completion_tokens"),
        "reasoning_chars": r.get("reasoning_chars"),
    })
    return r


def run(limit: int = None, dry_run: bool = False) -> int:
    if config.model_calls_forbidden():
        raise SystemExit("%s=1：T2 选型实验会发真实请求，镜像重跑期间**拒绝运行**。"
                         % config.FORBID_MODEL_CALLS_ENV)

    cases = asm.assemble_all()
    if limit is not None:
        cases = cases[:limit]
    print("装配完成：%d 题（每题的 Prompt SHA-256 已固定，三个候选共用同一份）" % len(cases))
    print("候选：%s" % "、".join(c["model"] for c in config.MODEL_CANDIDATES))
    print("temperature=%s max_tokens=%s（三候选全同）"
          % (config.require_fixed("temperature"), config.require_fixed("max_tokens")))

    if dry_run:
        print("\n--dry-run：只装配、不发请求。每题 Prompt 字数与证据条数：")
        for c in cases:
            print("  %s 证据 %d 条  total_tokens=%d  prompt=%d 字  sha256=%s"
                  % (c["qid"], len(c["evidence"]), c["token_account"]["total_tokens"],
                     len(c["prompt"]["system"]) + len(c["prompt"]["user"]),
                     c["prompt"]["sha256"][:12]))
        print("未发出任何请求（调用计数 0）。")
        return 0

    rows, calls = [], 0
    for cand in config.MODEL_CANDIDATES:
        key = config.api_key(cand["provider"])     # 缺失即明确报错退出
        print("\n--- 候选 %s（%s）---" % (cand["model"], cand["role"]))
        for c in cases:
            # 单题最多两次尝试，两次都如实登记（《21》第2.5节 与本阶段 v1.3 空正文重试规则）：
            #   ① 第 1 次请求失败  → 以完全相同配置重试一次（不静默丢弃）；
            #   ② 第 1 次正文为空  → 以完全相同配置再请求一次（v1.3：两次都空才判空答案）。
            attempts = []
            r = _attempt(cand, c, key, attempts)          # 第 1 次
            calls += 1
            if (not r["ok"]) or r.get("empty_body"):
                why = ("请求失败（%s）" % (r.get("error") or "")[:60]) if not r["ok"] \
                    else ("正文为空（finish_reason=%s）" % (r.get("finish_reason") or "n/a"))
                print("  %s 第 1 次%s，以完全相同的配置重试一次……" % (c["qid"], why))
                r = _attempt(cand, c, key, attempts)      # 第 2 次（同模型／温度／上限／Prompt）
                calls += 1

            if not r["ok"]:
                print("  %s FAIL（两次均失败）%s" % (c["qid"], (r.get("error") or "")[:100]))
                rows.append({
                    "qid": c["qid"], "candidate": cand["key"], "provider": cand["provider"],
                    "model_requested": cand["model"], "model_returned": None,
                    "ok": False, "error": r.get("error"), "seconds": r["seconds"],
                    "finish_reason": None, "attempts": attempts, "retried": True,
                    "prompt_tokens": None, "completion_tokens": None,
                    "body_text": "", "answer_text": "", "reasoning_chars": 0,
                    "citation_marks": 0, "citation_out_of_range": [],
                    "citation_out_of_range_count": 0, "dates_mentioned": [],
                    "date_unverifiable": [], "date_unverifiable_count": 0,
                    "body_dates_mentioned": [], "body_date_unverifiable": [],
                    "body_date_unverifiable_count": 0,
                    "dates_beyond_cutoff": [], "dates_beyond_cutoff_count": 0,
                    "graph_used": c["graph_payload"]["graph_used"],
                    "system_graph_section_ok": False,
                    "system_graph_section_has_path": False,
                    "system_graph_section_is_marker": False,
                    "body_graph_marker_leak": False, "body_section_header_leak": False,
                    # 请求失败**不是**「空答案」（v1.3 空答案只指「成功但正文为空」）——
                    # 失败由 `n_failures` 单列统计，两者不混计。
                    "empty_answer": False, "evidence_count": len(c["evidence"]),
                })
                continue

            # 答案形态：模型正文 ＋ 代码拼装的三段（《21》v1.2 硬约束 7／8）
            answer_text = prompt_mod.compose_answer(
                body=r["answer_text"], evidence=c["evidence"],
                graph_payload=c["graph_payload"],
                dataset_version=c["dataset_version"],
                data_cutoff_time=c["data_cutoff_time"], time_note=c["time_note"])
            mc = machine_check(answer_text=answer_text, body_text=r["answer_text"], case=c)
            print("  %s ok %.2fs finish=%s 尝试%d 引用%d(越界%d) 日期不可核%d(未来%d) "
                  "图谱段%s 正文泄漏%s 空答案%s"
                  % (c["qid"], r["seconds"], r.get("finish_reason"), len(attempts),
                     mc["citation_marks"], mc["citation_out_of_range_count"],
                     mc["date_unverifiable_count"], mc["dates_beyond_cutoff_count"],
                     "OK" if mc["system_graph_section_ok"] else "BAD",
                     "有" if mc["body_graph_marker_leak"] else "无",
                     "是" if mc["empty_answer"] else "否"))
            rows.append({
                "qid": c["qid"], "candidate": cand["key"], "provider": cand["provider"],
                "model_requested": cand["model"], "model_returned": r["model_returned"],
                "ok": True, "error": None, "seconds": r["seconds"],
                "finish_reason": r.get("finish_reason"),
                "attempts": attempts, "retried": len(attempts) > 1,
                "prompt_tokens": r["prompt_tokens"],
                "completion_tokens": r["completion_tokens"],
                "body_text": r["answer_text"], "answer_text": answer_text,
                "reasoning_chars": r["reasoning_chars"],
                "citation_marks": mc["citation_marks"],
                "citation_out_of_range": mc["citation_out_of_range"],
                "citation_out_of_range_count": mc["citation_out_of_range_count"],
                "dates_mentioned": mc["dates_mentioned"],
                "date_unverifiable": mc["date_unverifiable"],
                "date_unverifiable_count": mc["date_unverifiable_count"],
                "body_dates_mentioned": mc["body_dates_mentioned"],
                "body_date_unverifiable": mc["body_date_unverifiable"],
                "body_date_unverifiable_count": mc["body_date_unverifiable_count"],
                "dates_beyond_cutoff": mc["dates_beyond_cutoff"],
                "dates_beyond_cutoff_count": mc["dates_beyond_cutoff_count"],
                "graph_used": mc["graph_used"],
                "system_graph_section_ok": mc["system_graph_section_ok"],
                "system_graph_section_has_path": mc["system_graph_section_has_path"],
                "system_graph_section_is_marker": mc["system_graph_section_is_marker"],
                "body_graph_marker_leak": mc["body_graph_marker_leak"],
                "body_section_header_leak": mc["body_section_header_leak"],
                "empty_answer": mc["empty_answer"],
                "evidence_count": len(c["evidence"]),
            })

    # 固定排序：按 (qid, candidate) 升序；写盘用 sort_keys 固定键序
    rows.sort(key=lambda r: (r["qid"], r["candidate"]))
    config.write_jsonl(config.SELECTION_MATRIX_PATH, rows)
    print("\n已写：%s（%d 行）" % (config.SELECTION_MATRIX_PATH, len(rows)))

    decision = build_decision(rows, cases, calls, limit)
    config.write_json(config.SELECTION_DECISION_PATH, decision)
    print("已写：%s" % config.SELECTION_DECISION_PATH)
    print_summary(decision["aggregates"])
    print("\n选型结论：%s" % decision["verdict"])
    return 0


# --------------------------------------------------------------------------
# 汇总打印（决策者不必翻 JSON 就能把关键读数读出来）
# --------------------------------------------------------------------------
def _fmt_seconds(v):
    return "n/a" if v is None else "%.3f" % v


def print_summary(agg: dict) -> None:
    """把每个候选的汇总读数直接打到 stdout（《21》收口报告与决策者复跑用）。

    每候选一行，列为：失败数／重试数／空答数／`length` 截断数／引用越界数／
    `date_unverifiable`／`dates_beyond_cutoff`／`body_graph_marker_leak`／
    平均·中位·最大时延／`finish_reason` 分布。星号（*）表示该项按「次」计（其余按「题」计）。
    """
    print("\n" + "=" * 132)
    print("选型汇总（30 题 × 3 候选；读数来自本地矩阵，逐题明细与逐次尝试见 selection_matrix.jsonl）")
    print("=" * 132)
    hdr = ("%-16s %5s %5s %5s %7s %9s %13s %14s %15s %9s %9s %9s  %s"
           % ("候选", "失败", "重试", "空答", "length截", "引用越界*", "date不可核*",
              "dates超截止*", "正文图谱泄漏", "平均时延", "中位时延", "最大时延",
              "finish_reason 分布"))
    print(hdr)
    print("-" * 132)
    for key in sorted(agg):
        a = agg[key]
        dist = a.get("finish_reason_distribution") or {}
        dist_s = " ".join("%s=%d" % (k, dist[k]) for k in sorted(dist)) or "无"
        print("%-16s %5d %5d %5d %7d %9d %13d %14d %15d %9s %9s %9s  %s"
              % (key, a["n_failures"], a["n_retried"], a["empty_answer_cases"],
                 a.get("finish_length_cases", 0),
                 a["citation_out_of_range_total"], a["date_unverifiable_total"],
                 a["dates_beyond_cutoff_total"], a["body_graph_marker_leak_cases"],
                 _fmt_seconds(a["mean_seconds"]), _fmt_seconds(a["median_seconds"]),
                 _fmt_seconds(a["max_seconds"]), dist_s))
    print("-" * 132)
    print("空答数＝「请求成功但正文为空」且**两次尝试都为空**的题数；失败数＝两次尝试均失败的题数。")
    print("标 * 的三项按「次数／出现处」计；其余按「题数」计。重试卷数见各行的「重试」列。")
    print("=" * 132)


# --------------------------------------------------------------------------
# 判定
# --------------------------------------------------------------------------
def _aggregate(rows: list, cand_key: str, n_cases: int) -> dict:
    sub = [r for r in rows if r["candidate"] == cand_key]
    n = len(sub)
    fails = [i for i, r in enumerate(sub) if not r["ok"]]
    # 规则①：连续失败的最大长度（按 qid 顺序，即装配顺序）
    longest = cur = 0
    for r in sub:
        cur = cur + 1 if not r["ok"] else 0
        longest = max(longest, cur)

    def _count(field):
        return sum(r.get(field) or 0 for r in sub)

    # 引用编号越界：总次数 ＋ 涉及题数（一次调用内可出现多个越界编号）
    cite_total = _count("citation_out_of_range_count")
    cite_cases = sum(1 for r in sub if r["citation_out_of_range_count"] > 0)
    # 日期来源不可核（＝越界，v1.2 修正 1 的新口径）
    du_total = _count("date_unverifiable_count")
    du_cases = sum(1 for r in sub if r["date_unverifiable_count"] > 0)
    du_body_total = _count("body_date_unverifiable_count")
    # 证据原文里明写的未来日期：**只统计、不计入失败**
    dbc_total = _count("dates_beyond_cutoff_count")
    leak_cases = sum(1 for r in sub if r["body_graph_marker_leak"])
    header_leak_cases = sum(1 for r in sub if r["body_section_header_leak"])
    gsec_bad = sum(1 for r in sub if not r["system_graph_section_ok"])
    # 空答案**只统计请求成功但正文为空的题**（请求失败单列 n_failures；两者不混计）
    empty = sum(1 for r in sub if r["ok"] and r["empty_answer"])
    retried = sum(1 for r in sub if r.get("retried"))
    secs = [r["seconds"] for r in sub if r["seconds"] is not None]
    seconds_sorted = sorted(secs)
    finish = collections.Counter((r.get("finish_reason") or "n/a") for r in sub)
    finish_length = finish.get("length", 0)          # length 截断（＝触顶）的行数
    finish_stop = finish.get("stop", 0)
    return {
        "candidate": cand_key,
        "n_calls": sum(len(r.get("attempts") or [None]) for r in sub),
        "n_questions": n,
        "n_failures": sum(1 for r in sub if not r["ok"]),
        "n_retried": retried,
        "max_consecutive_failures": longest,
        # —— 规则②用的四项机检率（越低越好）——
        "citation_out_of_range_rate": round(cite_cases / n, 4) if n else None,
        "date_unverifiable_rate": round(du_cases / n, 4) if n else None,
        "empty_answer_rate": round(empty / n, 4) if n else None,
        "graph_section_bad_rate": round(gsec_bad / n, 4) if n else None,
        # —— 逐项原始次数（判决策者汇总表用）——
        "citation_out_of_range_total": cite_total,
        "citation_out_of_range_cases": cite_cases,
        "date_unverifiable_total": du_total,
        "date_unverifiable_cases": du_cases,
        "body_date_unverifiable_total": du_body_total,
        "dates_beyond_cutoff_total": dbc_total,
        "body_graph_marker_leak_cases": leak_cases,
        "body_section_header_leak_cases": header_leak_cases,
        "system_graph_section_bad_cases": gsec_bad,
        "empty_answer_cases": empty,
        "finish_length_cases": finish_length,
        "finish_stop_cases": finish_stop,
        "graph_cases": sum(1 for r in sub if r["graph_used"]),
        # —— 时延与 token ——
        "mean_seconds": round(sum(secs) / len(secs), 3) if secs else None,
        "median_seconds": (round(seconds_sorted[len(seconds_sorted) // 2], 3)
                           if seconds_sorted else None),
        "max_seconds": max(secs) if secs else None,
        "total_prompt_tokens": sum(r["prompt_tokens"] or 0 for r in sub),
        "total_completion_tokens": sum(r["completion_tokens"] or 0 for r in sub),
        "max_completion_tokens": max((r["completion_tokens"] or 0) for r in sub) if sub else None,
        "finish_reason_distribution": {k: finish[k] for k in sorted(finish)},
        "expected_cases": n_cases,
    }


def build_decision(rows: list, cases: list, calls: int, limit) -> dict:
    rules = config.SELECTION
    frozen = rules["frozen_candidate"]
    cand_keys = [c["key"] for c in config.MODEL_CANDIDATES]
    agg = {k: _aggregate(rows, k, len(cases)) for k in cand_keys}
    ref_keys = [k for k in cand_keys if k != frozen]     # 对照候选
    margin = rules["machine_check_margin"]

    # 规则①：冻结候选连续 3 次请求失败
    r1 = agg[frozen]["max_consecutive_failures"] >= rules["consecutive_failures_threshold"]

    # 规则②：机检读数显著劣于对照（逐项按百分点绝对差；越低越好的三项、越高越好的一项）
    worse = []
    for name, worse_is_higher in (("citation_out_of_range_rate", True),
                                  ("date_unverifiable_rate", True),
                                  ("empty_answer_rate", True),
                                  ("graph_section_bad_rate", True)):
        mine, best = agg[frozen].get(name), None
        for k in ref_keys:
            v = agg[k].get(name)
            if v is None:
                continue
            best = v if best is None else min(best, v)
        if mine is None or best is None:
            worse.append({"metric": name, "frozen": mine, "best_control": best,
                          "delta": None, "significant": False, "note": "读数缺失，不判显著"})
            continue
        delta = mine - best if worse_is_higher else best - mine
        worse.append({"metric": name, "frozen": mine, "best_control": best,
                      "delta": round(delta, 4), "significant": delta >= margin})
    r2 = any(w["significant"] for w in worse)

    # 规则③：30 题平均时延 > 30 s
    r3 = (agg[frozen]["mean_seconds"] or 0) > rules["mean_latency_limit_seconds"]

    triggered = [i for i, t in ((1, r1), (2, r2), (3, r3)) if t]
    verdict = ("维持 %s" % frozen) if not triggered else \
        ("触发改判规则 %s，冻结值改判待作者复核（本工具只给判定与证据，不自行改判）"
         % "／".join(str(i) for i in triggered))

    # Moonshot／kimi-k3 的排除证据（引用决策者的勘察原始输出）
    mx = dict(config.MOONSHOT_EXCLUSION)
    mx["evidence_found"] = os.path.isfile(mx["evidence_path"])
    mx_rows = []
    if mx["evidence_found"]:
        for row in config.read_json(mx["evidence_path"]).get("rows", []):
            if row.get("provider") == mx["provider"]:
                mx_rows.append({
                    "model": row.get("model"), "temperature": row.get("temperature"),
                    "ok": row.get("ok"), "seconds": row.get("seconds"),
                    "response_model": row.get("response_model"),
                })
    mx["observed_rows"] = mx_rows
    mx["observed_temperatures"] = sorted({r["temperature"] for r in mx_rows})
    mx["conclusion"] = ("勘察实测 %s 只在 temperature=1 下可用（见 observed_rows），"
                        "与《02》第12.4节 冻结的 temperature=%s 冲突，故不进入三候选对照。"
                        % (mx["model"], config.require_fixed("temperature")))

    return {
        "schema": "stage8-selection-decision-1.2",
        "purpose": "T2 三模型对照选型的判定与执行证据（《21》第2.5节 第 4 条改判规则）",
        "spec_version": "《21》v1.3（2026-09-29 修订：max_tokens 2048→16384，因该端点模型为"
                        "推理型、推理与正文共用输出预算，2048 档的「空答案率」反映配置而非模型"
                        "能力；并新增「空正文重试」规则——同配置重试一次，两次尝试都留痕，"
                        "两次都空才判空答案）",
        "frozen_candidate": frozen,
        "control_candidates": ref_keys,
        "only_thing_changed": "仅模型；装配结果、Prompt 文本、temperature、max_tokens 三候选全同",
        "temperature": config.require_fixed("temperature"),
        "max_tokens": config.require_fixed("max_tokens"),
        "empty_body_retry_rule": "某次请求返回空正文（content 为空串）时，以**完全相同的配置**"
                                 "（同模型／同 temperature／同 max_tokens／同 Prompt 文本／同证据"
                                 "集合）再请求一次；两次尝试都落进 selection_matrix.jsonl 的"
                                 "`attempts`（逐次含时延、finish_reason、prompt/completion tokens、"
                                 "是否空正文）；**两次都为空**才记 empty_answer=1。该规则对三个"
                                 "候选一律适用，不引入新的实验变量。",
        "archived_config_2048_readings": {
            "note": "上一轮 max_tokens=2048 的选型读数（selection_matrix.jsonl／"
                    "selection_decision.json）是**配置产物**而非模型能力读数（该档下三候选都出现"
                    "「推理吃光预算、正文为空」的行），已按《21》v1.3 从正式产出移出，留痕于下方"
                    "两份文件，仅作改动效果的对照，不作为选型依据。",
            "matrix_path": os.path.join(config.WORK_DIR, "selection_matrix_max2048.jsonl"),
            "decision_path": os.path.join(config.WORK_DIR, "selection_decision_max2048.json"),
        },
        "questions": len(cases),
        "total_calls": calls,
        "machine_check_scope": {
            "citation_out_of_range": "作用域＝模型生成的「回答」正文（引用记法 [证据n]）",
            "date_unverifiable": "作用域＝答案全文；允许来源＝证据正文／证据语料元数据"
                                 "（标题、发布时间）／data_cutoff_time 的日期部分／"
                                 "由窗口规则确定性推出的判定区间端点（最近 30 天、近期 90 天、"
                                 "最新＝基准日）＋ 题集 time_window 的 lo/hi",
            "dates_beyond_cutoff": "作用域＝答案全文；**只统计、不计入失败**，用于如实登记"
                                   "「证据原文里明写的未来日期」（不算缺陷）",
            "graph": "graph_used=1 ⇒ 系统拼装的图谱段有内容且不含固定标注；graph_used=0 ⇒ "
                     "系统段恰为该固定标注；模型正文出现该固定标注即 body_graph_marker_leak",
            "empty_answer": "**定义为模型生成的「回答」正文为空、且按 v1.3 空正文重试规则"
                            "重试一次后仍为空**（四段里的其余三段由代码拼装，按构造非空）；"
                            "请求失败不计入本项（单列 n_failures）。该情形通常与 "
                            "finish_reason=length 同时出现，即 completion 预算被推理载荷占满"
                            "导致正文未产出；max_tokens=16384 下应大幅减少。",
        },
        "prompt_sha256_by_qid": {c["qid"]: c["prompt"]["sha256"] for c in cases},
        "aggregates": agg,
        "rules": {
            "rule_1_consecutive_failures": {
                "threshold": rules["consecutive_failures_threshold"],
                "frozen_value": agg[frozen]["max_consecutive_failures"],
                "triggered": bool(r1),
            },
            "rule_2_machine_check_worse": {
                "margin": margin,
                "comparison": worse,
                "triggered": bool(r2),
            },
            "rule_3_mean_latency": {
                "limit_seconds": rules["mean_latency_limit_seconds"],
                "frozen_value": agg[frozen]["mean_seconds"],
                "triggered": bool(r3),
            },
        },
        "triggered_rules": triggered,
        "verdict": verdict,
        "moonshot_exclusion": mx,
        "notice": "本文件只登记 30 题预实验集上的**原始读数与机检读数**，不含人工评分，"
                  "不构成正式实验结论（《21》第1.2节、非目标 4／5）。"
                  "`dates_beyond_cutoff` 是证据原文里明写的未来日期（重试登记用），"
                  "**不是缺陷**；判失败的只有 `date_unverifiable`。",
    }


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="T2 三模型对照选型实验（链外工具）")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 题（小样本试跑）")
    ap.add_argument("--dry-run", action="store_true", help="只装配、不发请求")
    ap.add_argument("--recheck", action="store_true",
                    help="零调用：按已落盘的模型输出重算机检字段并重写矩阵与结论")
    args = ap.parse_args()
    if args.recheck:
        return recheck()
    return run(limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
