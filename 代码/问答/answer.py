# -*- coding: utf-8 -*-
"""代码\\问答\\answer.py —— T5（单题生成链路与答案形态）＋ T6（机检门禁）。

一条链路：**装配 → 调用 → 合成四段答案 → 机检**。

* 装配 —— 直接消费 `assemble.assemble_case()` 的结果（第 7 阶段的最终证据集合 ＋ 图谱载荷，
  **不重排、不重裁、不重算 token**；《21》第五节 硬约束 5／6）。
* 调用 —— 标准库 `urllib` 发一次非流式请求；**发请求前先过 `config.assert_model_calls_allowed()`**
  （镜像重跑哨兵，《21》第2.5节 第 3 条）。**空正文重试规则**（《21》v1.3 第五节 硬约束 2）：
  某次请求成功但 `content` 为空串时，以**完全相同的配置**重试一次，两次尝试都落进 `attempts`；
  **两次都空该题判失败**（非零退出），**不得**写入空答案。
* 合成 —— `prompt.compose_answer()`：只有「回答」正文由模型生成，「证据来源」／「知识图谱路径」
  （或未使用时的固定标注）／「数据截至与判定区间」三段由代码**确定性拼装**（《21》v1.2 硬约束 7／8）。
* 机检 —— `gate()`：引用编号／日期来源／图谱三方一致／禁词／证据回链／非空／时间说明／开放式标注。

**判据单一来源**：日期来源可核与禁词表在 `rules.py`（与选型侧 `model_selection.py` 同一套口径）。

**门禁不静默**（《21》验收 E4）：任一门禁失败的题**不得进入正式产出**——本模块只负责判定并
把失败明细放进返回值，由调用方（`run_answer.py`）非零退出并把明细打印出来。
"""

from __future__ import annotations

import argparse
import json
import os
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


class ModelCallError(SystemExit):
    """调用层不可继续的错误（哨兵置位／请求两次都空／请求失败）。"""


# --------------------------------------------------------------------------
# 一、调用（标准库 urllib；不新增任何第三方依赖）
# --------------------------------------------------------------------------
def _one_attempt(messages: list, model: str, max_tokens: int) -> dict:
    """发**一次**请求并返回原始读数（不回显密钥）。"""
    payload = {
        "model": model,
        "temperature": config.require_fixed("temperature"),
        "max_tokens": max_tokens,
        "messages": messages,
    }
    key = config.api_key("deepseek" if model in _deepseek_models() else _provider_of(model))
    req = urllib.request.Request(
        config.require_fixed("endpoint").rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=config.require_fixed("timeout_seconds")) as r:
            raw = r.read().decode("utf-8", "replace")
            status = r.status
    except urllib.error.HTTPError as e:
        return {"ok": False, "status": e.code, "seconds": round(time.time() - t0, 3),
                "error": "HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300])}
    except Exception as e:                                      # 超时／连接失败／DNS……
        return {"ok": False, "status": None, "seconds": round(time.time() - t0, 3),
                "error": "%s: %s" % (type(e).__name__, e)}
    seconds = round(time.time() - t0, 3)
    try:
        obj = json.loads(raw)
        msg = (obj.get("choices") or [{}])[0].get("message") or {}
        usage = obj.get("usage") or {}
        content = msg.get("content") or ""
        return {
            "ok": True, "status": status, "seconds": seconds,
            "model_returned": obj.get("model"),
            "finish_reason": (obj.get("choices") or [{}])[0].get("finish_reason"),
            "body_text": content,
            "empty_body": len(content.strip()) == 0,
            "reasoning_chars": len(msg.get("reasoning_content") or ""),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "error": None,
        }
    except Exception as e:
        return {"ok": False, "status": status, "seconds": seconds,
                "error": "响应解析失败 %s: %s；body 前 200 字：%s"
                         % (type(e).__name__, e, raw[:200])}


def _deepseek_models() -> set:
    return {c["model"] for c in config.MODEL_CANDIDATES if c["provider"] == "deepseek"}


def _provider_of(model: str) -> str:
    for c in config.MODEL_CANDIDATES:
        if c["model"] == model:
            return c["provider"]
    return "deepseek"          # 端点仍取冻结的 ANSWER["endpoint"]（不猜别的供应商）


def call_model(messages, *, model: str = None, max_tokens: int = None) -> dict:
    """发一次请求（空正文按 v1.3 规则重试一次），返回原始读数 ＋ 逐次 `attempts`。

    `messages` 可以是 `{"system":…, "user":…}`（装配层的形状）或标准的
    `[{"role":…, "content":…}, …]` 列表。

    返回：`ok`（**请求成功且正文非空**）／`model_requested`／`model_returned`／`seconds`
    （末次尝试的时延）／`total_seconds`／`prompt_tokens`／`completion_tokens`／
    `finish_reason`／`body_text`／`reasoning_chars`／`error`／`attempts`／`n_calls`。
    """
    config.assert_model_calls_allowed("answer.call_model")
    model = model or config.resolve_model("answer")
    max_tokens = int(max_tokens or config.require_fixed("max_tokens"))
    if isinstance(messages, dict):
        payload_messages = [{"role": "system", "content": messages.get("system") or ""},
                            {"role": "user", "content": messages.get("user") or ""}]
    else:
        payload_messages = list(messages)

    attempts = []

    def _record(res: dict) -> dict:
        row = {
            "attempt": len(attempts) + 1,
            "ok": bool(res["ok"]),
            "seconds": res.get("seconds"),
            "status": res.get("status"),
            "error": res.get("error"),
            "finish_reason": res.get("finish_reason"),
            # 空正文判据只在「请求成功但 content 为空串」时有意义；失败行记 None，不混为「空答案」
            "empty_body": (bool(res.get("empty_body")) if res["ok"] else None),
            "body_chars": len((res.get("body_text") or "").strip()),
            "prompt_tokens": res.get("prompt_tokens"),
            "completion_tokens": res.get("completion_tokens"),
            "reasoning_chars": res.get("reasoning_chars"),
        }
        attempts.append(row)
        return row

    # 第 1 次
    last = _one_attempt(payload_messages, model, max_tokens)
    _record(last)
    # v1.3 空正文重试规则：**请求成功但正文为空** → 以完全相同的配置再请求一次
    if last["ok"] and last["empty_body"]:
        last = _one_attempt(payload_messages, model, max_tokens)
        _record(last)

    ok = bool(last["ok"]) and not bool(last.get("empty_body"))
    error = last.get("error")
    if last["ok"] and last["empty_body"]:
        error = ("两次尝试的正文均为空串（finish_reason=%s、completion=%s）——"
                 "按《21》v1.3 第五节 硬约束 2 判该题失败，不得写入空答案"
                 % (last.get("finish_reason"), last.get("completion_tokens")))
    return {
        "ok": ok,
        "model_requested": model,
        "model_returned": last.get("model_returned"),
        "seconds": last.get("seconds"),
        "total_seconds": round(sum(a["seconds"] or 0 for a in attempts), 3),
        "prompt_tokens": last.get("prompt_tokens"),
        "completion_tokens": last.get("completion_tokens"),
        "finish_reason": last.get("finish_reason"),
        "body_text": last.get("body_text") or "",
        "reasoning_chars": last.get("reasoning_chars"),
        "error": error,
        "attempts": attempts,
        "n_calls": len(attempts),
        "empty_body": bool(last["ok"] and last.get("empty_body")),
    }


# --------------------------------------------------------------------------
# 二、机检门禁（T6）
# --------------------------------------------------------------------------
_INDEX_CACHE = {}


def _corpus_index() -> tuple:
    """(`chunk_id` → chunks 行, `doc_id` → documents 行)；只读、进程内缓存。"""
    if "chunks" not in _INDEX_CACHE:
        _INDEX_CACHE["chunks"] = asm.load_chunks()
        _INDEX_CACHE["docs"] = asm.load_documents()
    return _INDEX_CACHE["chunks"], _INDEX_CACHE["docs"]


def evidence_backlink(case: dict) -> dict:
    """逐条证据的 `chunk_id`／`doc_id` 在语料里可查（验收 E5；缺失 0 条是门禁）。"""
    chunks, docs = _corpus_index()
    missing = []
    for item in case["evidence"]:
        cid, did = item["chunk_id"], item["doc_id"]
        if cid not in chunks:
            missing.append({"chunk_id": cid, "reason": "chunks.jsonl 里查不到"})
        elif did not in docs:
            missing.append({"chunk_id": cid, "doc_id": did, "reason": "documents.jsonl 里查不到"})
        elif chunks[cid]["doc_id"] != did:
            missing.append({"chunk_id": cid, "doc_id": did,
                            "reason": "chunks.jsonl 记的 doc_id=%s 与证据条不一致"
                                      % chunks[cid]["doc_id"]})
    return {"evidence_backlink_ok": not missing, "evidence_backlink_missing": missing,
            "evidence_checked": len(case["evidence"])}


def gate(case: dict, body_text: str, answer_text: str) -> dict:
    """T6 机检门禁：读一遍就给出全部判据与失败项（**全部通过 `passed` 才为真**）。

    作用域（写在返回里，便于复核）：
    * 引用编号、图谱标记泄漏、小标题泄漏 —— 只看**模型生成的「回答」正文** `body_text`
      （答案四段里唯一由模型写的段，其余三段由代码拼装、按构造即可核）；
    * 日期来源 —— 按《21》验收 E1 的字面「答案中每个年月日」看**答案全文** `answer_text`；
      三段系统拼装的文本全部落在允许来源内（构造上），故不会产生假阳性；
    * 禁词 —— 看**答案全文**（超集；实测 30 题的系统拼装三段命中 0，故等同看模型正文）；
    * 开放式标注 —— 按题集 `task_type` 判（硬约束 12：不得靠关键词猜）；题集里没有开放式题时
      记 `not_applicable = true` 并给出依据。
    """
    evidence = case["evidence"]
    m = len(evidence)
    graph_used = bool(case["graph_payload"]["graph_used"])

    cg = rules.citation_gate(body_text, m)                  # ① 引用编号（模型正文）
    dg = rules.date_gate(answer_text, case)                 # ② 日期来源（答案全文）
    body_dg = rules.date_gate(body_text, case)              # ②' 只号模型正文（细读数）
    fg = rules.forbidden_gate(answer_text)                  # ③ 禁词（答案全文）

    # ④ 图谱三方一致（D4／E2）
    secs = prompt_mod.split_answer_sections(answer_text)
    gsec = (secs.get(prompt_mod.ANSWER_SECTIONS[2]) or "")
    has_path = bool(gsec.strip()) and (prompt_mod.NO_GRAPH_MARKER not in gsec)
    if graph_used:
        graph_section_ok = has_path
    else:
        graph_section_ok = gsec.strip() == prompt_mod.NO_GRAPH_MARKER
    leak = prompt_mod.NO_GRAPH_MARKER in (body_text or "")
    # 模型正文里出现系统段的三个小标题（不含「回答」二字本身——它是常用词，会误报）
    header_leak = any(t in (body_text or "") for t in prompt_mod.ANSWER_SECTIONS[1:])
    # 写进记录层的取值：0／1（《21》第五节 硬约束 8 的取值口径「is_graph_extended = 0」）
    is_graph_extended = 1 if graph_used else 0

    # ⑤ 证据回链（E5）
    bl = evidence_backlink(case)

    # ⑥ 非空
    non_empty = len((body_text or "").strip()) > 0

    # ⑦ 数据截至与判定区间（D5）：`time_constraint == "有"` 的题，答案的
    #    「数据截至与判定区间」段须含**判定区间**与**数据截止时间**
    tn = case.get("time_note") or {}
    tsec = (secs.get(prompt_mod.ANSWER_SECTIONS[3]) or "")
    cutoff = case.get("data_cutoff_time") or config.DATA_CUTOFF_TIME
    time_applicable = (tn.get("time_constraint") == "有")
    if time_applicable:
        need = [str(tn.get("window_label") or ""), str(tn.get("lo") or ""), str(tn.get("hi") or ""),
                cutoff]
        missing_parts = [x for x in need if x and x not in tsec]
        time_note_ok = not missing_parts
    else:
        missing_parts = []
        # 无时间约束的题：只要求该段给出数据截止时间（判定区间一栏应显式说明"无判定区间"）
        time_note_ok = (cutoff in tsec)
    # 无时间约束时另核一句"无判定区间"的显式说明
    if not time_applicable:
        time_note_ok = time_note_ok and ("无判定区间" in tsec)

    # ⑧ 开放式分析标注（D6；判据＝题集 task_type，不靠关键词猜）
    task_type = case.get("task_type")
    is_open = task_type in config.OPEN_ENDED_TASK_TYPES
    if is_open:
        open_applicable = True
        open_ok = prompt_mod.MODEL_ANALYSIS_MARKER in (body_text or "")
        open_reason = "题集 task_type=%r 属开放式类型 %s，要求含固定标注" % (
            task_type, "、".join(config.OPEN_ENDED_TASK_TYPES))
    else:
        open_applicable = False
        open_ok = True          # 不适用即通过
        open_reason = ("题集 task_type=%r 不在开放式类型 %s 里；本题集无开放式题，按"
                       "《21》验收 D6 的「无开放式题时该行以不适用通过并打印理由」处理"
                       % (task_type, "、".join(config.OPEN_ENDED_TASK_TYPES)))

    failures = []
    if cg["citation_out_of_range_count"]:
        failures.append("citation_out_of_range")
    if not cg["citation_marks"]:
        failures.append("citation_missing")                 # D3：至少 1 个引用
    if dg["date_unverifiable_count"]:
        failures.append("date_unverifiable")
    if not graph_section_ok:
        failures.append("graph_section")
    if leak:
        failures.append("body_graph_marker_leak")
    if header_leak:
        failures.append("body_section_header_leak")
    if fg["forbidden_hit_count"]:
        failures.append("forbidden_terms")
    if not bl["evidence_backlink_ok"]:
        failures.append("evidence_backlink")
    if not non_empty:
        failures.append("empty_answer")
    if not time_note_ok:
        failures.append("time_note")
    if open_applicable and not open_ok:
        failures.append("open_ended_marker")

    return {
        # 引用编号
        "citation_marks": cg["citation_marks"],
        "citation_count": cg["citation_count"],
        "citation_out_of_range": cg["citation_out_of_range"],
        "citation_out_of_range_count": cg["citation_out_of_range_count"],
        "cited_ranks": cg["cited_ranks"],
        # 日期来源
        "date_gate_scope": "答案全文（E1 字面口径）",
        "dates_mentioned": dg["dates_mentioned"],
        "date_unverifiable": dg["date_unverifiable"],
        "date_unverifiable_count": dg["date_unverifiable_count"],
        "body_date_unverifiable": body_dg["date_unverifiable"],
        "body_date_unverifiable_count": body_dg["date_unverifiable_count"],
        "dates_beyond_cutoff": dg["dates_beyond_cutoff"],
        "dates_beyond_cutoff_count": dg["dates_beyond_cutoff_count"],
        # 图谱
        "graph_used": graph_used,
        "is_graph_extended": is_graph_extended,
        "is_graph_extended_consistent": is_graph_extended == (
            1 if case["graph_payload"].get("graph_used") else 0),
        "graph_section_ok": bool(graph_section_ok),
        "graph_section_has_path": bool(has_path),
        "graph_section_is_marker": gsec.strip() == prompt_mod.NO_GRAPH_MARKER,
        "body_graph_marker_leak": bool(leak),
        "body_section_header_leak": bool(header_leak),
        # 其他
        "forbidden_hits": fg["forbidden_hits"],
        "forbidden_hit_count": fg["forbidden_hit_count"],
        "forbidden_hit_contexts": fg["forbidden_hit_contexts"],
        "forbidden_terms_size": fg["forbidden_terms_size"],
        "evidence_backlink_ok": bl["evidence_backlink_ok"],
        "evidence_backlink_missing": bl["evidence_backlink_missing"],
        "non_empty": bool(non_empty),
        "time_constraint": tn.get("time_constraint"),
        "time_note_applicable": bool(time_applicable),
        "time_note_ok": bool(time_note_ok),
        "time_note_missing_parts": missing_parts,
        "open_ended_marker_applicable": bool(open_applicable),
        "open_ended_marker_ok": bool(open_ok),
        "open_ended_task_type": task_type,
        "open_ended_reason": open_reason,
        "citation_count_ok": bool(cg["citation_marks"]),
        # 总判定
        "passed": not failures,
        "failures": failures,
    }


# --------------------------------------------------------------------------
# 三、单题生成链路（T5）
# --------------------------------------------------------------------------
def answer_case(case: dict, *, dry_run: bool = False) -> dict:
    """装配 → 调用 → 合成四段答案 → 机检（一题一条结果，键固定）。

    `dry_run=True` 时**0 次调用**，只回装配结果与 Prompt 的 SHA-256（《21》验收 G1）。
    """
    prompt_obj = case["prompt"]
    prompt_text = prompt_obj["system"] + "\n\n" + prompt_obj["user"]
    prompt_sha = prompt_obj.get("sha256") or config.sha256_text(prompt_text)
    base = {
        "qid": case["qid"],
        "question": case["question"],
        "group": case["group"],
        "prompt_sha256": prompt_sha,
        "prompt_chars": len(prompt_text),
        "evidence_count": len(case["evidence"]),
        "is_graph_extended": bool(case["graph_payload"]["graph_used"]),
        "checks": case["checks"],
    }
    if dry_run:
        base.update({"dry_run": True, "n_calls": 0, "model": None,
                     "attempts": [], "body_text": "", "answer_text": "", "gates": None})
        return base

    res = call_model(prompt_obj, model=config.resolve_model("answer"))
    base["dry_run"] = False
    base["n_calls"] = res["n_calls"]
    base["model"] = {"requested": res["model_requested"], "returned": res["model_returned"]}
    base["attempts"] = res["attempts"]
    base["prompt_tokens"] = res["prompt_tokens"]
    base["completion_tokens"] = res["completion_tokens"]
    base["finish_reason"] = res["finish_reason"]
    base["seconds"] = res["seconds"]
    base["reasoning_chars"] = res["reasoning_chars"]
    base["body_text"] = res["body_text"]
    if not res["ok"]:
        base.update({"ok": False, "error": res["error"], "answer_text": "", "gates": None})
        return base

    answer_text = prompt_mod.compose_answer(
        body=res["body_text"], evidence=case["evidence"], graph_payload=case["graph_payload"],
        dataset_version=case["dataset_version"], data_cutoff_time=case["data_cutoff_time"],
        time_note=case["time_note"])
    base.update({"ok": True, "error": None, "answer_text": answer_text,
                 "gates": gate(case, res["body_text"], answer_text)})
    return base


# --------------------------------------------------------------------------
# 四、自检（单题端到端 ＋ dry-run 0 调用 ＋ 装配两次 SHA-256 相同）
# --------------------------------------------------------------------------
def _case_for(qid: str) -> dict:
    cases = {c["qid"]: c for c in asm.assemble_all()}
    if qid not in cases:
        raise SystemExit("题集 trace 里没有 qid=%s" % qid)
    return cases[qid]


def selftest() -> int:
    print("=" * 72)
    print("answer.py 自检（T5／T6：单题端到端 ＋ dry-run 0 调用 ＋ 装配确定性）")
    print("=" * 72)
    qid = "PE-01"
    c1, c2 = _case_for(qid), _case_for(qid)
    print("① 装配两次的 Prompt SHA-256：")
    print("   第 1 次 %s" % c1["prompt"]["sha256"])
    print("   第 2 次 %s" % c2["prompt"]["sha256"])
    same = c1["prompt"]["sha256"] == c2["prompt"]["sha256"]
    print("   相同=%s" % same)
    assert same, "装配两次的 Prompt SHA-256 必须相同"

    print("\n② dry-run（0 次调用）：")
    d = answer_case(c1, dry_run=True)
    print("   n_calls=%d  prompt_chars=%d  prompt_sha256=%s"
          % (d["n_calls"], d["prompt_chars"], d["prompt_sha256"][:16]))
    assert d["n_calls"] == 0 and d["gates"] is None

    print("\n③ 单题端到端（%s，真实调用）：" % qid)
    r = answer_case(c1)
    if not r.get("ok"):
        print("   调用失败：%s" % r.get("error"))
        return 1
    print("   调用尝试 %d 次；finish_reason=%s；正文 %d 字；答案全文 %d 字"
          % (r["n_calls"], r["finish_reason"], len(r["body_text"]), len(r["answer_text"])))
    g = r["gates"]
    for key in ("citation_count", "citation_out_of_range_count", "date_unverifiable_count",
                "dates_beyond_cutoff_count", "graph_section_ok", "body_graph_marker_leak",
                "body_section_header_leak", "forbidden_hit_count", "evidence_backlink_ok",
                "non_empty", "time_note_ok", "open_ended_marker_applicable",
                "open_ended_marker_ok", "passed"):
        print("   %-32s = %s" % (key, g[key]))
    print("   失败项 = %s" % (g["failures"] or "无"))
    print("\n--- 模型正文（前 300 字）---")
    print(r["body_text"][:300])
    print("\n--- 答案四段的段标题与长度 ---")
    for title, text in prompt_mod.split_answer_sections(r["answer_text"]).items():
        print("   【%s】%d 字" % (title, len(text)))
    print("=" * 72)
    return 0 if g["passed"] else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="T5／T6：单题生成链路与机检门禁")
    ap.add_argument("--selftest", action="store_true", help="PE-01 端到端 ＋ dry-run 0 调用")
    ap.add_argument("--qid", default="PE-01", help="自检用的题号")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
