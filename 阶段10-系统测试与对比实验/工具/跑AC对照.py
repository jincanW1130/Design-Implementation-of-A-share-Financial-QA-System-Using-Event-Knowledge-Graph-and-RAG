# -*- coding: utf-8 -*-
"""第 10 阶段（系统测试 + 对比实验）——A vs C 单变量对照驱动。

## 这个脚本解决什么问题

评审发现（《评审（前九阶段·七维度）.md》P0-1／P0-2）：本课题的立论根基是"事件知识图谱
比纯向量 RAG 更能检索多跳/关系/时序信息"，但**第 7～9 阶段的交付产物里只有 C 组（Method），
A 组（＝Baseline 2＝纯 Vector RAG）从未进入任何交付产物**，因此 RQ2／H1 一直没有对照。

本脚本**不修改任何冻结文件**，只做三件事：
  1. 逐题调用**冻结的**第 8 阶段入口 `代码\\问答\\run_answer.py`，对 A 与 C 两组各跑满 30 题
     （A 组走 `--group A` 的桥接路径，由第 7 阶段的 `run_query.py` 现取 trace；
      C 组走冻结的 `per_question_trace.jsonl`，只读）；
  2. 把逐题产出聚合成分组产出（`answer_trace.jsonl`／`qa_records.jsonl`）；
  3. 按《02》第 12.7／12.8 节的口径算**四项检索指标**（总体 + 关系型／多跳型／时序型三个子集），
     并汇总**机检可核**的问答侧统计量。

## 为什么不自己实现检索或生成

《02》第 12.4 节要求所有对比组使用同一 Embedding、同一模型、同一 temperature、同一 Prompt
版本、同一 K／N／预算。本脚本**一行检索逻辑、一行生成逻辑都不重写**，全部转发给冻结入口，
以保证 A 与 C 之间**唯一变量是"是否使用事件知识图谱"**。

## 口径纪律（不得放宽）

* **人工 0／1／2 评分（Answer Accuracy／Completeness／Faithfulness）不由本脚本产出**，
  也不由本脚本用模型代理。它在产出里显式登记为 `NOT_DONE`，必须由作者人工完成
  （《02》第 12.7 节：人工评分 + ≥20% 样本间隔 ≥3 天二次复评）。
  本脚本只给出**机检可核**的量（引用编号越界、图谱标记泄漏、门禁通过率、证据条数、
  图谱来源证据数、token 账、耗时）。
* 本脚本**不**据此下"KG 是否有效"的结论——结论按《02》第 12.8 节判定规则由人工给出。

## 用法

    python "阶段10-系统测试与对比实验\\工具\\跑AC对照.py"                 # A + C 各 30 题
    python "阶段10-系统测试与对比实验\\工具\\跑AC对照.py" --qids PE-01     # 冒烟：只跑一题
    python "阶段10-系统测试与对比实验\\工具\\跑AC对照.py" --groups A        # 只跑 A 组
    python "阶段10-系统测试与对比实验\\工具\\跑AC对照.py" --dry-run         # 只打印计划，0 次调用

退出码：0 = 全部题成功；1 = 有题失败（失败清单落盘，不静默）。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STAGE10 = os.path.join(ROOT, "阶段10-系统测试与对比实验")
QUESTIONS = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集", "questions.jsonl")
RUN_ANSWER = os.path.join(ROOT, "代码", "问答", "run_answer.py")
OUT_DIR = os.path.join(STAGE10, "对照产出")

# 记录层时间与会话标识固定，保证产出可复现（不写运行时刻）
FIXED_NOW = "2026-10-02T00:00:00+08:00"
SESSION_ID = "S-AC-对照"

METRIC_KEYS = ("recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k")

# 《02》第 12.8 节的三个子集（允许重叠；同一道题可同时属于多个子集）
SUBSETS = (
    ("关系型", lambda q: q.get("task_type") == "关系型"),
    ("多跳型", lambda q: int(q.get("gold_hop_depth") or 0) >= 1),
    ("时序型", lambda q: q.get("time_constraint") == "有"),
)


def log(msg: str) -> None:
    print(msg, flush=True)


def load_questions() -> dict:
    out = {}
    with open(QUESTIONS, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                out[row["qid"]] = row
    return out


# ---------------------------------------------------------------------------
# 1. 跑一组：逐题调冻结入口
# ---------------------------------------------------------------------------
def run_one(group: str, qid: str, out_root: str) -> dict:
    """调冻结的 run_answer.py 跑一题；返回 {ok, exit_code, out_dir, stdout_tail}。"""
    out_dir = os.path.join(out_root, "逐题", group, qid)
    os.makedirs(out_dir, exist_ok=True)
    cmd = [sys.executable, RUN_ANSWER,
           "--qid", qid,
           "--group", group,
           "--out-dir", out_dir,
           "--now", FIXED_NOW,
           "--session-id", SESSION_ID]
    started = datetime.now()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=1800)
    secs = (datetime.now() - started).total_seconds()
    tail = "\n".join((proc.stdout or "").strip().split("\n")[-6:])
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "out_dir": os.path.relpath(out_dir, ROOT), "seconds": round(secs, 2),
            "stdout_tail": tail, "stderr_tail": (proc.stderr or "")[-500:]}


def collect_rows(path: str) -> list:
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


_ANSWER_ID_RE = None


def _answer_id_of(record_text: str):
    """从 `qa_records` 的记录串里取 `answer_id`（该文件的行是字符串化的 dict）。"""
    global _ANSWER_ID_RE
    if _ANSWER_ID_RE is None:
        import re as _re
        _ANSWER_ID_RE = _re.compile(r"['\"]answer_id['\"]\s*:\s*['\"]([^'\"]+)['\"]")
    m = _ANSWER_ID_RE.search(str(record_text or ""))
    return m.group(1) if m else None


def merge_jsonl(path: str, new_rows: list, key) -> list:
    """按 `key` 合并写回：同键的新行覆盖旧行。

    用途：**补跑**。`--qids` 只跑少数题时，若直接覆盖聚合文件会把其余题抹掉；
    合并后「跑一题补一题」不会破坏已完成的 30 题产物。
    """
    old = collect_rows(path)
    merged = {}
    for row in old:
        k = key(row)
        if k is not None:
            merged[k] = row
    for row in new_rows:
        k = key(row)
        if k is not None:
            merged[k] = row
    out = [merged[k] for k in sorted(merged)]
    write_jsonl(path, out)
    return out


def write_jsonl(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# 2. 四项检索指标（K = 每题最终证据集合上限，取自 trace 的 k 字段）
# ---------------------------------------------------------------------------
def retrieval_metrics(trace_rows: list, questions: dict, keep) -> dict:
    """在 `keep` 选出的题上算四项指标；逐题取值后按题取算术平均（《02》第12.7节）。"""
    sel = [r for r in trace_rows if keep(questions.get(r["qid"], {}))]
    if not sel:
        return {"n_questions": 0}
    acc = {k: 0.0 for k in METRIC_KEYS}
    n_graph_ev = 0
    for row in sel:
        q = questions.get(row["qid"], {})
        gold = set(int(x) for x in (q.get("gold_evidence_chunk_ids") or []))
        ev = [int(x["chunk_id"]) for x in row["evidence"]]
        K = int(row["k"])
        hit = len(gold & set(ev))
        ranks = [i + 1 for i, c in enumerate(ev) if c in gold]
        acc["recall_at_k"] += (hit / len(gold)) if gold else 0.0
        acc["precision_at_k"] += hit / K
        acc["mrr"] += (1.0 / ranks[0]) if ranks else 0.0
        acc["complete_evidence_recall_at_k"] += 1.0 if gold and gold <= set(ev) else 0.0
        n_graph_ev += sum(1 for x in row["evidence"] if x.get("from_graph"))
    n = len(sel)
    out = {"n_questions": n, "K": int(sel[0]["k"])}
    for k in METRIC_KEYS:
        out[k] = round(acc[k] / n, 6)
    out["graph_evidence_in_final_total"] = n_graph_ev
    out["graph_evidence_per_question"] = round(n_graph_ev / n, 4)
    return out


# ---------------------------------------------------------------------------
# 3. 机检可核的问答侧统计（**不含**人工 0/1/2 评分）
# ---------------------------------------------------------------------------
def machine_checks(trace_rows: list) -> dict:
    n = len(trace_rows)
    if not n:
        return {"n_questions": 0}
    gate_ok = sum(1 for r in trace_rows if not (r.get("gates") or {}).get("failures"))
    graph_ext = sum(1 for r in trace_rows if r.get("is_graph_extended"))
    zero_hop_leak = 0
    for r in trace_rows:
        if not r.get("is_graph_extended") and (r.get("graph_payload") or {}).get("graph_path"):
            zero_hop_leak += 1
    body_lens = [len(str(r.get("body_text") or "")) for r in trace_rows]
    tokens = [int((r.get("token_account") or {}).get("total_tokens") or 0) for r in trace_rows]
    ev = [int(r.get("evidence_count") or 0) for r in trace_rows]
    secs = [round(sum(float(a.get("seconds") or 0) for a in (r.get("attempts") or [])), 3)
            for r in trace_rows]
    return {
        "n_questions": n,
        "gate_pass": gate_ok,
        "gate_pass_rate": round(gate_ok / n, 4),
        "is_graph_extended": graph_ext,
        "zero_hop_graph_path_leak": zero_hop_leak,
        "evidence_count_mean": round(sum(ev) / n, 4),
        "evidence_count_min": min(ev), "evidence_count_max": max(ev),
        "body_chars_mean": round(sum(body_lens) / n, 1),
        "body_chars_min": min(body_lens), "body_chars_max": max(body_lens),
        "empty_body": sum(1 for x in body_lens if x == 0),
        "total_tokens_mean": round(sum(tokens) / n, 1),
        "total_tokens_max": max(tokens),
        "llm_seconds_mean": round(sum(secs) / n, 3),
        "llm_seconds_max": max(secs),
        "human_scoring": "NOT_DONE",
        "human_scoring_note": (
            "人工 0／1／2 评分（Answer Accuracy／Completeness／Faithfulness）与 ≥20% 样本的"
            "间隔 ≥3 天二次复评**尚未做**（《02》第12.7节）。本表任何数字都是**机检量**，"
            "不得当成答案质量分；在人工评分完成前，第 12.8 节的判定条件"
            "「Answer Accuracy 不下降」无法判定。"),
    }


def render_md(result: dict) -> str:
    groups = [g for g in result.get("groups") or ["A", "C"]]
    M = result["metrics"]
    A, C = M.get("A") or {}, M.get("C") or {}
    title = ("A vs C 单变量对照（第 10 阶段 · 首次交付级对照）" if groups == ["A", "C"]
             else "消融 A～E 对照（第 10 阶段）")
    L = ["# " + title, "",
         "> 生成脚本：`阶段10-系统测试与对比实验\\工具\\跑AC对照.py`",
         "> 问题集：`阶段07-RAG检索系统\\预实验问题集\\questions.jsonl`（30 题）",
         "> 冻结配置：K=%s、N=%s、Context Token Budget=%s、g=%s、model=%s、Prompt=%s" % (
             result["frozen"].get("K"), result["frozen"].get("N"),
             result["frozen"].get("budget"), result["frozen"].get("g"),
             result["frozen"].get("model"), result["frozen"].get("prompt_version")),
         "> **A ＝ Baseline 2 ＝ 纯 Vector RAG；B ＝ A＋1-hop KG；C ＝ Method ＝ A＋2-hop KG"
         "（含 1-hop）；D ＝ C＋时间过滤；E ＝ D＋证据排序。**",
         "> 继承关系 C ⊆ D ⊆ E，逐项只增一个模块；五组共用同一 K／N／预算／g／模型／Prompt。",
         ""]
    L += ["## 一、四项检索指标（总体 30 题）", "",
          "| 指标 | " + " | ".join(groups) + " |",
          "| --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for k, label in (("recall_at_k", "Recall@K"), ("precision_at_k", "Precision@K"),
                     ("mrr", "MRR"),
                     ("complete_evidence_recall_at_k", "**Complete Evidence Recall@K**")):
        L.append("| %s | %s |" % (label, " | ".join(str((M.get(g) or {}).get(k)) for g in groups)))
    L.append("| 图谱来源证据：合计 | %s |" %
             " | ".join(str((M.get(g) or {}).get("graph_evidence_in_final_total")) for g in groups))
    L.append("| 图谱来源证据：每题 | %s |" %
             " | ".join(str((M.get(g) or {}).get("graph_evidence_per_question")) for g in groups))
    L += ["",
          "**读法**：《02》第 12.8 节的判定要求 `Complete Evidence Recall@K` 相对基线**提高**。"
          "若该行在各组之间完全相同，则 CER 这一半的判定条件在**任何子集上都不成立**。", ""]

    L += ["## 二、逐子集（《02》第 12.8 节：按子集分别判定，不合并）", "",
          "### 2.1 Complete Evidence Recall@K", "",
          "| 子集 | 题数 | " + " | ".join(groups) + " |",
          "| --- | --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for name, _, per_group in result["subsets"]:
        n = (per_group.get("A") or {}).get("n_questions")
        L.append("| %s | %s | %s |" % (name, n, " | ".join(
            str((per_group.get(g) or {}).get("complete_evidence_recall_at_k")) for g in groups)))
    L += ["", "### 2.2 Recall@K", "",
          "| 子集 | 题数 | " + " | ".join(groups) + " |",
          "| --- | --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for name, _, per_group in result["subsets"]:
        n = (per_group.get("A") or {}).get("n_questions")
        L.append("| %s | %s | %s |" % (name, n, " | ".join(
            str((per_group.get(g) or {}).get("recall_at_k")) for g in groups)))
    L.append("")

    L += ["## 三、问答侧机检量（**不是质量分**）", "",
          "| 量 | " + " | ".join(groups) + " |",
          "| --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for k, label in (("n_questions", "题数"), ("gate_pass", "门禁通过题数"),
                     ("is_graph_extended", "标注为使用图谱扩展的题数"),
                     ("zero_hop_graph_path_leak", "零跳却出现图谱路径（应为 0）"),
                     ("evidence_count_mean", "证据条数均值"),
                     ("body_chars_mean", "正文平均字数"), ("empty_body", "空正文题数"),
                     ("total_tokens_mean", "上下文 token 均值"),
                     ("llm_seconds_mean", "单次生成平均耗时(s)")):
        L.append("| %s | %s |" % (label, " | ".join(
            str((result["machine"].get(g) or {}).get(k)) for g in groups)))
    L += ["",
          "> **人工 0／1／2 评分（Answer Accuracy／Completeness／Faithfulness）尚未进行**——"
          "本表全部为机检量。在人工评分完成前，《02》第 12.8 节判定条件中的"
          "「该子集的 Answer Accuracy 不下降」一项**无法判定**。", ""]

    L += ["## 四、失败清单", ""]
    if result["failures"]:
        L += ["| 组 | 题号 | 退出码 | 原因（stdout 尾部） |", "| --- | --- | --- | --- |"]
        for f in result["failures"]:
            L.append("| %s | %s | %s | %s |" % (f["group"], f["qid"], f["exit_code"],
                                                str(f["stdout_tail"]).replace("\n", " ")[:180]))
    else:
        L.append("无（%d 组 × 30 题全部成功落盘）" % len(groups))
    L += ["", "## 五、结论该怎么写（口径纪律）", "",
          "按《02》第 12.8 节：若某子集上 KG-RAG 的 Complete Evidence Recall@K **高于** Vector RAG，"
          "且 Answer Accuracy 不下降，才判「知识图谱在该类问题上提供了额外检索价值」。"]
    L.append("**三种结果都是有效结论**，不得为了让图表好看而回头调 K／N／g 或挑子集。")
    if groups != ["A", "C"]:
        L += ["",
              "**消融继承关系的读法**（《02》第 12.6 节）：B／C 的差异表示"
              "「在直接关系基础上继续扩展两跳带来的变化」（C 含 B，不是排除 B）；"
              "H3 由 **C → D** 回答（唯一变量＝时间过滤）；E 属**独立的进一步优化实验**，"
              "不并入 RQ3，须单独报告。"]
    return "\n".join(L) + "\n"


def check_token_account() -> int:
    """自检：本驱动所依赖的「最终证据集合 token 分账」复刻是否与第 7 阶段口径逐位一致。

    做法：对第 7 阶段冻结的 30 条 C 组 trace，用 `代码\\问答\\run_answer.py` 的
    `final_set_token_account()` 复算，与 trace 里的 `token_account` 逐字段比对。

    这条自检是防漂移用的：`run_answer.py` 为了让桥接路径通过装配账目守卫，必须自己复算
    这笔账（不能 import 第 7 阶段模块，见该文件开头的路径解析陷阱说明）。一旦第 7 阶段的
    `estimate_tokens`／`stable_json` 口径变了而本复刻没跟上，这里会立刻失败。
    """
    sys.path.insert(0, os.path.join(ROOT, "代码", "问答"))
    import run_answer as ra  # noqa: WPS433
    chunks = ra.asm.load_chunks()
    trace_path = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "per_question_trace.jsonl")
    rows = collect_rows(trace_path)
    keys = ("text_chunks", "text_tokens", "paths", "path_tokens",
            "event_triples", "event_triple_tokens", "total_tokens")
    bad = []
    for row in rows:
        rec = {"final_evidence": {"presentation_order": row["evidence"]},
               "graph_path_payload": row.get("graph_payload") or {}}
        got = ra.final_set_token_account(rec, chunks)
        want = row["token_account"]
        diff = {k: (want[k], got[k]) for k in keys if want[k] != got[k]}
        if diff:
            bad.append((row["qid"], diff))
    print("token 账口径自检：%d／%d 题与第 7 阶段冻结 trace 逐字段一致"
          % (len(rows) - len(bad), len(rows)))
    for qid, diff in bad[:10]:
        print("  !! %s 不一致：%s" % (qid, diff))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="A vs C 单变量对照（第 10 阶段）")
    ap.add_argument("--groups", default="A,C", help="要跑的组，逗号分隔（默认 A,C）")
    ap.add_argument("--qids", default=None, help="只跑指定题号，逗号分隔（冒烟用）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，0 次调用")
    ap.add_argument("--check-token-account", action="store_true",
                    help="只做 token 账口径自检（0 次调用、不落盘）")
    ap.add_argument("--report-only", action="store_true",
                    help="0 次调用：从已聚合的 answer_trace.jsonl 重算指标并重出报告")
    ap.add_argument("--out-dir", default=OUT_DIR)
    args = ap.parse_args()

    if args.check_token_account:
        return check_token_account()

    questions = load_questions()
    qids = sorted(questions)
    if args.qids:
        want = [x.strip() for x in args.qids.split(",") if x.strip()]
        missing = [x for x in want if x not in questions]
        if missing:
            raise SystemExit("题号不存在于问题集：%s" % "、".join(missing))
        qids = want
    groups = [g.strip().upper() for g in args.groups.split(",") if g.strip()]

    log("=" * 78)
    log("第 10 阶段 · A vs C 单变量对照")
    log("=" * 78)
    log("题集：%s（%d 题）" % (os.path.relpath(QUESTIONS, ROOT), len(qids)))
    log("组：%s" % "、".join(groups))
    log("产出根：%s" % os.path.relpath(args.out_dir, ROOT))
    log("模型调用计划：%d 题 × %d 组 = %d 次（A 组另需 %d 次本地检索；检索不调用模型）"
        % (len(qids), len(groups), len(qids) * len(groups),
           len(qids) if "A" in groups else 0))
    if args.dry_run:
        log("\n--dry-run：不调用、不落盘。")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    records = {}
    failures = []
    if args.report_only:
        # 0 次模型调用：只从已聚合的 answer_trace.jsonl 重算指标并重出报告。
        # 用途：修报告措辞／冻结配置读取时不必重跑 60 次调用。
        log("\n--report-only：不调用模型，只从已聚合产出重算。")
        for group in groups:
            rows = collect_rows(os.path.join(args.out_dir, group, "answer_trace.jsonl"))
            rows.sort(key=lambda r: r["qid"])
            log("  读入 %s：%d 行" % (group, len(rows)))
            records[group] = rows
    else:
        for group in groups:
            log("\n" + "-" * 78)
            log("组 %s：逐题调用冻结入口 run_answer.py" % group)
            log("-" * 78)
            rows, qa = [], []
            for i, qid in enumerate(qids, 1):
                res = run_one(group, qid, args.out_dir)
                flag = "OK " if res["ok"] else "!! "
                log("  [%s] %2d/%d %-7s %5.1fs" % (flag, i, len(qids), qid, res["seconds"]))
                if not res["ok"]:
                    failures.append({"group": group, "qid": qid, **{k: res[k] for k in
                                                                   ("exit_code", "stdout_tail", "stderr_tail")}})
                    continue
                sub = os.path.join(res["out_dir"].replace("/", os.sep))
                rows += collect_rows(os.path.join(ROOT, sub, "answer_trace.jsonl"))
                qa += collect_rows(os.path.join(ROOT, sub, "qa_records.jsonl"))
            rows.sort(key=lambda r: r["qid"])
            # 合并写回（不覆盖）：支持「先跑满题集、再补跑失败题」的补跑工作流。
            rows = merge_jsonl(os.path.join(args.out_dir, group, "answer_trace.jsonl"),
                               rows, key=lambda r: r["qid"])
            merge_jsonl(os.path.join(args.out_dir, group, "qa_records.jsonl"),
                        qa, key=lambda r: _answer_id_of(r.get("answer")))
            log("  聚合（合并后）：answer_trace %d 行、qa_records %d 行 → %s"
                % (len(rows), len(qa), os.path.join(os.path.relpath(args.out_dir, ROOT), group)))
            records[group] = rows

    # ---- 指标 ----
    metrics, machine, subsets = {}, {}, []
    for group in groups:
        rows = records.get(group, [])
        metrics[group] = retrieval_metrics(rows, questions, lambda q: True)
        machine[group] = machine_checks(rows)
    for name, pred in SUBSETS:
        per = {g: retrieval_metrics(records.get(g, []), questions, pred) for g in groups}
        subsets.append((name, None, per))

    cfg = _frozen_config()
    result = {"generated_by": "阶段10-系统测试与对比实验/工具/跑AC对照.py",
              "generated_at": datetime.now().isoformat(timespec="seconds"),
              "question_set": os.path.relpath(QUESTIONS, ROOT),
              "qids": qids, "groups": groups,
              "frozen": cfg, "metrics": metrics, "machine": machine,
              "subsets": [{"name": n, "per_group": per} for n, _, per in subsets],
              "failures": failures}
    with open(os.path.join(args.out_dir, "A_vs_C_对照.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2, sort_keys=True)
    with open(os.path.join(args.out_dir, "A_vs_C_对照报告.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md({**result, "subsets": subsets}))

    log("\n" + "=" * 78)
    log("完成：失败 %d 题" % len(failures))
    log("报告：%s" % os.path.join(os.path.relpath(args.out_dir, ROOT), "A_vs_C_对照报告.md"))
    log("=" * 78)
    for group in groups:
        m = metrics[group]
        log("  %s：Recall=%s Precision=%s MRR=%s **CER=%s**（图谱来源证据 %s 条）" % (
            group, m.get("recall_at_k"), m.get("precision_at_k"), m.get("mrr"),
            m.get("complete_evidence_recall_at_k"), m.get("graph_evidence_in_final_total")))
    return 1 if failures else 0


def _frozen_config() -> dict:
    """只读地取冻结配置（不动任何文件）。"""
    sys.path.insert(0, os.path.join(ROOT, "代码", "检索"))
    out = {}
    try:
        import config as ret_cfg  # noqa: WPS433
        # 四项定值走检索侧的 `require_fixed()`（TBD 即报错退出，不用默认值兜底）。
        for key, name in (("K", "K"), ("N", "N"),
                          ("budget", "context_token_budget"),
                          ("g", "graph_retention_share")):
            try:
                out[key] = ret_cfg.require_fixed(name)
            except Exception as exc:  # noqa: BLE001
                out[key] = None
                out.setdefault("errors", []).append("%s：%s" % (name, exc))
    except Exception as exc:  # noqa: BLE001
        out["error"] = "取检索侧冻结配置失败：%s" % exc
    try:
        # 答案侧**必须走子进程**：`代码\检索\config.py` 与 `代码\问答\config.py` 同名，
        # 本进程已 `import config` 取过检索侧那份，再 import 会命中 `sys.modules` 缓存、
        # 拿到的仍是检索侧（这正是 `代码\问答\run_answer.py` 开头记载的路径解析陷阱，
        # 第 8 阶段因此用子进程桥接）。子进程里只插问答目录，解析必然正确。
        qa_dir = os.path.join(ROOT, "代码", "问答")
        code = ("import sys,json;sys.path.insert(0,r'%s');import config;"
                "print(json.dumps(config.ANSWER,ensure_ascii=False))" % qa_dir)
        proc = subprocess.run([sys.executable, "-c", code], cwd=qa_dir,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=120)
        if proc.returncode == 0:
            ans = json.loads(proc.stdout.strip().split("\n")[-1])
            out["model"] = ans.get("model_name")
            out["prompt_version"] = ans.get("prompt_version")
            out["temperature"] = ans.get("temperature")
        else:
            out["answer_error"] = "取答案侧冻结配置失败：%s" % (proc.stderr or "")[-300:]
    except Exception as exc:  # noqa: BLE001
        out["answer_error"] = "取答案侧冻结配置失败：%s" % exc
    return out


if __name__ == "__main__":
    raise SystemExit(main())
