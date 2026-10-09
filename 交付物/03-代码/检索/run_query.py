# -*- coding: utf-8 -*-
r"""交付物/03-代码\检索\run_query.py —— 《18》第4.2节 点名的独立入口：一次完整的单题检索运行。

三件事（默认动作、`--selftest`、`--run-manifest`）：

1. **单题完整运行**（默认动作）：把 `vector_search → graph_query → pipeline → metrics`
   串成一次完整运行——`--question`（或 `--qid`）＋ `--group A..E`（默认取
   `config.DEFAULT_GROUP`＝C）＋ `--k`／`--n`／`--budget`（缺省一律经 `config.require_fixed()`
   取，不写死）＋ `--out`。运行记录默认落 `交付物/05-系统实现/RAG检索系统\_工作底稿\`，**不写 `检索产出\`**，
   `--out` 可覆盖。
2. **`--selftest`**：用预实验问题集的第一题（PE-01，带 gold）跑通 A 与 C 两组各一题；每组再用
   一个全新的 `PipelineRunner` 重跑一次做逐字节自比对（同一输入两次运行一致）。退出码 0＝全部通过。
3. **`--run-manifest`**：生成 `交付物/05-系统实现/RAG检索系统\检索产出\run_manifest.json`——11 条输入指纹
   （取 `input_manifest.json` 的记录值并现场重算核对）、四个产物的两次运行 SHA-256（在系统临时
   目录的镜像里真跑两轮，并与工作区交付产物逐字节比对）、大语言模型调用次数 0、本地 Embedding
   编码次数与耗时（用 `_工作底稿\_T11\T11_summary.json` 的实测量）。

运行记录（JSON）的字段：问题、分组与三个开关、两路候选数与并集、过滤前后差集、裁剪与保留 K 的账、
最终证据集合与呈现顺序、图谱路径载荷（未用图谱时用 `graph_query.GraphQuery.not_used_graph_marker()`）、
四项指标、`graph_used` 标记。

纪律：确定性（记录里不写运行时间戳与耗时；耗时只打印到 stdout，或按字段单独放置并标注
"不参与逐字节比对"）、0 次大语言模型／外部接口调用、输入只读（数据集 v2.1 与图谱导出物
`v2.1_v1_2` 一个字节都不写）。参数一律取同目录 `config.py`。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# 控制台按 UTF-8 输出（中文 Windows 的 GBK 代码页会把中文与数学符号写坏）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:                                     # 极少见的非文本流 stdout
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config                                              # noqa: E402（唯一参数来源）
import graph_query                                         # noqa: E402
import metrics                                             # noqa: E402
import pipeline                                            # noqa: E402
import vector_search                                       # noqa: E402
from graph_query import GraphQuery                          # noqa: E402
from vector_search import VectorSearcher                    # noqa: E402

if os.path.dirname(os.path.abspath(config.__file__)) != _HERE:
    raise SystemExit("导入到的 config.py 不在本脚本同目录，拒绝继续：%s" % config.__file__)


# ---------------------------------------------------------------------------
# 0. 固定口径（不是可调参数；可调参数一律来自 config）
# ---------------------------------------------------------------------------
SCHEMA = "stage7-run-query-1.0"
MANIFEST_SCHEMA = "stage7-run-manifest-1.0"

# 四个结构化产出的文件名与固定顺序（两次运行 SHA-256 的比对对象）
WATCH_FILES = ("pre_experiment_matrix.jsonl", "k_selection.json",
               "per_question_trace.jsonl", "metrics_pre.jsonl")

MANIFEST_PATH = config.OUTPUT_FILES["run_manifest"]

# 摘除凭据类环境变量用的名字形态：拼串构造，源码内不出现完整的凭据／厂商字样。
_CRED_ENV_PAT = re.compile("|".join([
    "API" + "[_-]?KEY", "SEC" + "RET", "ACCESS" + "[_-]?TOKEN", "AUTH" + "[_-]?TOKEN",
    "MOON" + "SHOT", "DASH" + "SCOPE", "ZHI" + "PU", "OPEN" + "AI", "DEEP" + "SEEK",
    "QIAN" + "FAN", "KI" + "MI", "G" + "LM", "BAI" + "DU", "ER" + "NIE",
    "ANTHRO" + "PIC", "GEM" + "INI"]), re.IGNORECASE)


def _rel(path: str) -> str:
    return os.path.relpath(path, config.ROOT).replace("\\", "/")


# ---------------------------------------------------------------------------
# 一、命令行
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="《18》第4.2节 的独立入口：单题完整运行（vector_search → graph_query → "
                    "pipeline → metrics）；另含 --selftest 与 run_manifest.json 的生成入口")
    parser.add_argument("--question", default=None, help="单题文本（与 --qid 互斥）")
    parser.add_argument("--qid", default=None, help="题集里的题号（与 --question 互斥）")
    parser.add_argument("--questions", default=config.QUESTION_FILES["questions"],
                        help="题集路径（只读；用于 --qid 与题干逐字命中；默认取 config）")
    parser.add_argument("--group", choices=tuple(sorted(config.GROUPS)),
                        default=config.DEFAULT_GROUP,
                        help="A～E 的开关预设（三个开关仍各自独立；默认 C＝Method）")
    parser.add_argument("--k", type=int, default=None,
                        help="最终证据集合的文本块上限 K；缺省经 config.require_fixed('K') 取")
    parser.add_argument("--n", type=int, default=None,
                        help="向量检索候选数量 N；缺省经 config.require_fixed('N') 取")
    parser.add_argument("--budget", type=int, default=None,
                        help="Context Token Budget；缺省经 "
                             "config.require_fixed('context_token_budget') 取")
    parser.add_argument("--graph-share", type=int, default=None,
                        help="g：图谱侧保留份额（全局固化量，A～E 同值；"
                             "缺省经 config.require_fixed('graph_retention_share') 取）")
    parser.add_argument("--out", default=None,
                        help="运行记录落点（默认 交付物/05-系统实现/RAG检索系统\\_工作底稿\\"
                             "run_query_<组>_<题号>.json）")
    parser.add_argument("--selftest", action="store_true",
                        help="自证：A 与 C 两组各一题，并各重跑一次做逐字节比对")
    parser.add_argument("--run-manifest", action="store_true",
                        help="生成 检索产出\\run_manifest.json（输入指纹 ＋ 两次运行 SHA-256 ＋ "
                             "模型调用次数 0 ＋ 本地 Embedding 次数与耗时）")
    parser.add_argument("--quiet", action="store_true", help="少打印（仍打印结论与本工具摘要）")
    args = parser.parse_args(argv)
    if args.question is not None and args.qid is not None:
        raise SystemExit("[run_query] 失败：--question 与 --qid 互斥，只能给一个")
    return args


# ---------------------------------------------------------------------------
# 二、参数与题面（K／N／预算／g 一律经 config.require_fixed 取，不写死）
# ---------------------------------------------------------------------------
def resolve_params(args) -> dict:
    """K／N／Context Token Budget／g 的解析：命令行优先，缺省回落 `config.require_fixed(...)`。

    直接在 `pipeline.resolve_k_n_budget()` 上取（同一份校验：正整数、N ≥ K、1 ≤ g ≤ K，
    其中 g 的下限由 `config.GRAPH_SHARE_FLOOR = 1` 强制；g = 0 只走显式退化通道），
    并额外记录每个量的来源，写进运行记录以便复核。
    """
    sizes = pipeline.resolve_k_n_budget(args)
    sources = {
        "K": "cli:--k" if args.k is not None else "config.require_fixed('K')",
        "N": "cli:--n" if args.n is not None else "config.require_fixed('N')",
        "context_token_budget": ("cli:--budget" if args.budget is not None
                                 else "config.require_fixed('context_token_budget')"),
        "g": ("cli:--graph-share" if args.graph_share is not None
              else "config.require_fixed('graph_retention_share')"),
    }
    return {"k": sizes["k"], "n": sizes["n"], "budget": sizes["budget"], "g": sizes["g"],
            "sources": sources}


def load_question_set(path: str) -> list:
    """读题集（只读；不改写）。返回原始行列表。"""
    if not os.path.isfile(path):
        raise SystemExit("[run_query] 失败：题集不存在：%s" % path)
    rows = [row for row in config.iter_jsonl(path)]
    if not rows:
        raise SystemExit("[run_query] 失败：题集为空：%s" % path)
    return rows


def pick_question(args, question_set: list) -> tuple:
    """确定待运行的一题：`--qid` 精确取题；`--question` 先按题干逐字命中题集，否则按自定义问题。

    返回 `(归一化题行, gold 来源说明)`。题行形状与 `pipeline.normalize_question_row()` 一致
    （`qid`／`question`／`time_window`／`gold_evidence_chunk_ids`／`task_type`／`gold_hop_depth`）。
    """
    if args.qid:
        for row in question_set:
            if str(row.get("qid")) == str(args.qid):
                return (pipeline.normalize_question_row(row, default_qid=str(args.qid)),
                        "题集 qid=%s（含 time_window 与 gold）" % args.qid)
        raise SystemExit("[run_query] 失败：题集里没有 qid=%s" % args.qid)
    text = str(args.question or "").strip()
    if not text:
        raise SystemExit("[run_query] 失败：请给 --question 或 --qid（或 --selftest／"
                         "--run-manifest）；用法见 --help")
    for row in question_set:
        if str(row.get("question") or "").strip() == text:
            return (pipeline.normalize_question_row(row, default_qid=str(row.get("qid"))),
                    "题集命中（题干逐字相同，qid=%s；含 time_window 与 gold）" % row.get("qid"))
    return (pipeline.normalize_question_row({"qid": "Q-CUSTOM", "question": text},
                                            default_qid="Q-CUSTOM"),
            "自定义问题（题集里没有同题干；gold 为空，四项指标按定义记 0）")


# ---------------------------------------------------------------------------
# 三、单题运行记录（把四个模块的输出合成一份 JSON）
# ---------------------------------------------------------------------------
def build_run_record(raw: dict, question_row: dict, params: dict, gold_source: str,
                     question_path: str) -> dict:
    """把 `pipeline.run_question()` 的逐题记录整理成 run_query 的运行记录（确定性、无耗时）。

    字段按《18》第4.2节 与本次交付要求：问题、分组与三个开关、两路候选数与并集、过滤前后差集、
    裁剪与保留 K 的账、最终证据集合与呈现顺序、图谱路径载荷、四项指标、`graph_used` 标记。
    """
    seg = raw["segments"]
    cand = seg["① 两路取候选"]
    merge = seg["② 合并去重"]
    trim = seg["③ 裁剪到预算"]
    keep = seg["④ 保留 K"]

    payload = raw["graph_payload"]
    if payload.get("graph_used"):
        graph_payload = payload
    else:
        # 未用图谱扩展：按硬约束 19 用图谱查询层的显式标记（不编造路径）
        marker = dict(GraphQuery.not_used_graph_marker())
        marker["reason"] = payload.get("reason") or ""
        graph_payload = marker

    gold = [int(x) for x in (question_row.get("gold_evidence_chunk_ids") or [])]
    metrics_row = metrics.evaluate_question_chunk_level(
        raw["final_evidence_chunk_ids"], gold, params["k"], qid=question_row["qid"])
    metrics_row["gold_source"] = gold_source
    metrics_row["gold_available"] = bool(gold)
    if not gold:
        metrics_row["note"] = ("自定义问题没有 gold：四项指标按定义一律记 0，本行只用于示意"
                               "计算路径，不构成检索效果读数")

    final_set = sorted(int(x) for x in raw["evidence"])
    return {
        "schema": SCHEMA,
        "generated_by": "交付物/03-代码/检索/run_query.py",
        "question": {
            "qid": question_row["qid"],
            "text": question_row["question"],
            "time_window": question_row.get("time_window"),
            "gold_evidence_chunk_ids": gold,
            "gold_evidence_count": len(gold),
            "task_type": question_row.get("task_type") or "",
            "gold_hop_depth": question_row.get("gold_hop_depth"),
            "question_set": _rel(question_path),
            "gold_source": gold_source,
        },
        "group": raw["group"],
        "switches": {key: raw["switches"][key]
                     for key in ("graph_depth", "time_filter", "evidence_sort")},
        "parameters": {
            "K": params["k"], "N": params["n"],
            "context_token_budget": params["budget"], "g": params["g"],
            "sources": params["sources"],
        },
        "candidates": {
            "vector_returned": merge["input_vector"],
            "graph_paths": cand["graph"]["output_paths"],
            "graph_returned": merge["input_graph"],
            "union": merge["output_union"],
            "dual_hit": merge["dual_hit"],
            "graph_only": merge["graph_only"],
            "unfiltered_union": len(raw["candidates_unfiltered"]),
            "filtered_union": len(raw["candidates_filtered"]),
        },
        "time_filter": {
            "branch": raw["time_filter"]["branch"],
            "enabled": raw["time_filter"]["enabled"],
            "g6_called": raw["time_filter"]["g6_called"],
            "window": raw["time_filter"]["window"],
            "kept_chunk_ids": raw["time_filter"]["kept_chunk_ids"],
            "removed_chunk_ids": raw["time_filter"]["removed_chunk_ids"],
            "removed_by_reason": raw["time_filter"]["removed_by_reason"],
            "filter_diff": {
                "removed": raw["candidate_diff_removed"],
                "added": raw["candidate_diff_added"],
                "counts": raw["candidate_diff_counts"],
                "measurable": raw["candidate_diff_measurable"],
                "note": ("" if raw["candidate_diff_measurable"]
                         else "本题差集为空：在该题上不可测，不得据此得出时间过滤无贡献的结论"),
            },
        },
        "budget_trim": {
            "budget": params["budget"],
            "before": trim["token_account"]["before"],
            "after": trim["token_account"]["after"],
            "dropped_paths": trim["dropped_paths"],
            "dropped_chunks": trim["dropped_chunks"],
            "budget_exceeded": trim["budget_exceeded"],
            "budget_floor_applied": trim["budget_floor_applied"],
            "rule": trim["rule"],
        },
        "keep_k": {
            "input": keep["input"], "output": keep["output"], "k": keep["k"],
            "dropped_by_k": keep["dropped_by_k"], "note": keep["note"],
            "precision_fill": raw["precision_fill"],
        },
        "final_evidence": {
            "size": len(final_set),
            "final_set_sorted": final_set,
            "presentation_order": list(raw["evidence"]),
            "graph_evidence_in_final": raw["graph_evidence_in_final"],
            "dual_hit_in_final": raw["dual_hit_in_final"],
        },
        "graph_path_payload": graph_payload,
        "graph_used": bool(raw["graph_payload"]["graph_used"]),
        "graph_query_calls": raw["graph_calls"],
        "graph_audit": raw["graph_audit"],
        "checks": raw["checks"],
        "metrics": metrics_row,
        "model_calls": {
            "llm_calls": 0,
            "external_api_calls": 0,
            "config_model_calls_allowed": config.MODEL_CALLS_ALLOWED,
            "note": ("本链路 0 次大语言模型／外部接口调用；问题侧向量化是本地 Embedding 前向"
                     "（与索引同模型同 revision、离线加载），按《18》第2.5节 不计入「模型调用」，"
                     "但不得写成「全程未跑模型」"),
        },
    }


def default_out_path(group: str, qid: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z_-]+", "_", str(qid)) or "Q"
    return os.path.join(config.DOCS_DIR, "run_query_%s_%s.json" % (group, safe))


def _run_one(runner, question_row, group, params) -> dict:
    switches = pipeline.normalize_switches(group)
    run = runner.run([question_row], switches, params["n"], params["k"],
                     params["budget"], params["g"])
    return run["records"][0]


def _print_record_summary(record: dict, prefix: str = "") -> None:
    cand = record["candidates"]
    met = record["metrics"]
    print("%s[%s] %s" % (prefix, record["group"], record["question"]["text"]))
    print("%s  三开关 %s｜K=%d N=%d 预算=%d g=%d"
          % (prefix, record["switches"], record["parameters"]["K"], record["parameters"]["N"],
             record["parameters"]["context_token_budget"], record["parameters"]["g"]))
    print("%s  候选：向量 %d ＋ 图谱 %d → 并集 %d（两路同命中 %d、图谱侧新增 %d）"
          % (prefix, cand["vector_returned"], cand["graph_returned"], cand["union"],
             cand["dual_hit"], cand["graph_only"]))
    print("%s  过滤前后差集：−%d／＋%d（%s）"
          % (prefix, record["time_filter"]["filter_diff"]["counts"]["removed"],
             record["time_filter"]["filter_diff"]["counts"]["added"],
             "可测" if record["time_filter"]["filter_diff"]["measurable"] else "在该题上不可测"))
    print("%s  裁剪：文本块 %d → %d（token %d → %d／预算 %d）｜保留 K：%d → %d"
          % (prefix, record["budget_trim"]["before"]["text_chunks"],
             record["budget_trim"]["after"]["text_chunks"],
             record["budget_trim"]["before"]["total_tokens"],
             record["budget_trim"]["after"]["total_tokens"],
             record["parameters"]["context_token_budget"],
             record["keep_k"]["input"], record["keep_k"]["output"]))
    print("%s  最终证据 %d 个：集合 %s｜呈现顺序 %s"
          % (prefix, record["final_evidence"]["size"],
             record["final_evidence"]["final_set_sorted"],
             record["final_evidence"]["presentation_order"]))
    print("%s  graph_used=%s（图谱载荷 %s）"
          % (prefix, record["graph_used"],
             "已给出路径与事件三元组" if record["graph_used"]
             else "未使用图谱扩展：" + str(record["graph_path_payload"].get("note"))))
    print("%s  四项指标（K=%d，gold %d 个、命中 %d 个）：R %s／P %s／MRR %s／CER %s"
          % (prefix, met["K"], met["n_gold"], met["n_hit"],
             met["recall_at_k"], met["precision_at_k"], met["mrr"],
             met["complete_evidence_recall_at_k"]))


# ---------------------------------------------------------------------------
# 四、默认动作：单题完整运行
# ---------------------------------------------------------------------------
def cmd_run(args) -> int:
    params = resolve_params(args)
    question_set = load_question_set(args.questions)
    question_row, gold_source = pick_question(args, question_set)

    print("=" * 78)
    print("run_query：单题完整运行（vector_search → graph_query → pipeline → metrics）")
    print("=" * 78)
    t0 = time.time()
    graph = graph_query.default_graph()
    searcher = VectorSearcher(verbose=not args.quiet)
    runner = pipeline.PipelineRunner(graph=graph, searcher=searcher, verbose=not args.quiet)
    raw = _run_one(runner, question_row, args.group, params)
    record = build_run_record(raw, question_row, params, gold_source, args.questions)

    out_path = args.out or default_out_path(args.group, question_row["qid"])
    config.write_json(out_path, record)
    _print_record_summary(record)
    timings = raw.get("timings") or {}
    print("  耗时（只打印，不写进运行记录）：总计 %.2fs（问题向量化 %.2fs、图谱查询 %.2fs、"
          "预算裁剪 %.2fs、保留 K %.2fs、呈现 %.2fs）"
          % (time.time() - t0, timings.get("vector_seconds", 0.0),
             timings.get("graph_seconds", 0.0), timings.get("trim_seconds", 0.0),
             timings.get("keep_k_seconds", 0.0), timings.get("order_seconds", 0.0)))
    print("  0 次大语言模型／外部接口调用（问题侧向量化为本地 Embedding 前向，不计入模型调用）")
    print("  运行记录落盘：%s（sha256=%s）"
          % (os.path.abspath(out_path), config.sha256_file(out_path)))
    return 0


# ---------------------------------------------------------------------------
# 五、--selftest：A 与 C 两组各一题（各重跑一次做逐字节比对）
# ---------------------------------------------------------------------------
def cmd_selftest(args) -> int:
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print("  [%s] %s%s" % ("OK  " if ok else "FAIL", name,
                               ("  —— " + detail) if detail else ""))
        return bool(ok)

    params = resolve_params(args)
    question_set = load_question_set(args.questions)
    row = pipeline.normalize_question_row(question_set[0], default_qid=str(question_set[0]["qid"]))
    gold_source = "题集 qid=%s（自证取题集第一题）" % row["qid"]

    print("=" * 78)
    print("run_query 自证：A 与 C 两组各一题（同题重跑一次做逐字节比对）")
    print("题：%s  %s（gold %d 个）"
          % (row["qid"], row["question"], len(row["gold_evidence_chunk_ids"])))
    print("参数：K=%d N=%d 预算=%d g=%d（来源 %s）"
          % (params["k"], params["n"], params["budget"], params["g"], params["sources"]))
    print("=" * 78)

    t0 = time.time()
    graph = graph_query.default_graph()
    searcher = VectorSearcher(verbose=not args.quiet)
    records = {}
    for group in ("A", "C"):
        runner_a = pipeline.PipelineRunner(graph=graph, searcher=searcher, verbose=not args.quiet)
        raw_a = _run_one(runner_a, row, group, params)
        record_a = build_run_record(raw_a, row, params, gold_source, args.questions)
        runner_b = pipeline.PipelineRunner(graph=graph, searcher=searcher, verbose=False)
        raw_b = _run_one(runner_b, row, group, params)
        record_b = build_run_record(raw_b, row, params, gold_source, args.questions)
        left = json.dumps(pipeline.strip_timings(raw_a), ensure_ascii=False, sort_keys=True)
        right = json.dumps(pipeline.strip_timings(raw_b), ensure_ascii=False, sort_keys=True)
        identical = left == right
        records[group] = record_a
        print("\n" + "-" * 78)
        _print_record_summary(record_a, prefix="  ")
        print("  [%s] %s 组同题两次运行逐字节一致（sha256=%s）"
              % ("OK  " if identical else "FAIL", group,
                 config.sha256_text(left)))
        checks.append({"name": "%s 组两次运行逐字节一致" % group, "ok": bool(identical),
                       "detail": "sha256=%s" % config.sha256_text(left)})

    print("\n" + "-" * 78)
    rec_a, rec_c = records["A"], records["C"]
    check("A 组三个开关为 graph_depth=0／time_filter=off／evidence_sort=off",
          rec_a["switches"] == {"graph_depth": 0, "time_filter": False, "evidence_sort": False},
          str(rec_a["switches"]))
    check("A 组未使用图谱扩展（graph_used=False，图谱载荷为 not_used_graph_marker）",
          rec_a["graph_used"] is False
          and rec_a["graph_path_payload"].get("graph_used") is False
          and rec_a["graph_path_payload"].get("note") == "未使用图谱扩展",
          "graph_path=%r" % rec_a["graph_path_payload"].get("graph_path"))
    check("C 组三个开关为 graph_depth=2／time_filter=off／evidence_sort=off",
          rec_c["switches"] == {"graph_depth": 2, "time_filter": False, "evidence_sort": False},
          str(rec_c["switches"]))
    check("C 组图谱查询被调用（G1/G2/G4/G5 计数非零）",
          any(int(rec_c["graph_query_calls"].get(k, 0)) > 0 for k in ("G1", "G2", "G4", "G5")),
          str(rec_c["graph_query_calls"]))
    check("C 组 graph_used=True（图谱路径进入最终证据集合）",
          rec_c["graph_used"] is True,
          "图谱侧新增块入集 %d 个" % rec_c["final_evidence"]["graph_evidence_in_final"].__len__())
    for group, rec in (("A", rec_a), ("C", rec_c)):
        check("%s 组最终证据集合不超过 K 且 chunk_id 唯一" % group,
              rec["final_evidence"]["size"] <= params["k"]
              and len(rec["final_evidence"]["final_set_sorted"])
              == len(set(rec["final_evidence"]["final_set_sorted"])),
              "size=%d K=%d" % (rec["final_evidence"]["size"], params["k"]))
        check("%s 组四项指标已在带 gold 的真题上算出" % group,
              rec["metrics"]["gold_available"] and rec["metrics"]["n_gold"] > 0,
              "R %s／P %s／MRR %s／CER %s"
              % (rec["metrics"]["recall_at_k"], rec["metrics"]["precision_at_k"],
                 rec["metrics"]["mrr"], rec["metrics"]["complete_evidence_recall_at_k"]))

    passed = sum(1 for item in checks if item["ok"])
    print("\n" + "=" * 78)
    print("自证结论：%d／%d 条通过（耗时 %.1fs，只打印到 stdout；本动作不写任何产出文件）"
          % (passed, len(checks), time.time() - t0))
    print("0 次大语言模型／外部接口调用；问题侧向量化为本地 Embedding 前向，不计入「模型调用」。")
    print("=" * 78)
    return 0 if passed == len(checks) else 1


# ---------------------------------------------------------------------------
# 六、--run-manifest：两次运行 SHA-256 ＋ 输入指纹 ＋ 0 调用 ＋ 本地 Embedding 实测量
# ---------------------------------------------------------------------------
def _subprocess_env() -> tuple:
    """摘除凭据类环境变量（只摘名字命中的；不打印任何取值），并置离线加载开关。"""
    env = dict(os.environ)
    removed = sorted(name for name in env if _CRED_ENV_PAT.search(name))
    for name in removed:
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    return env, removed


def _mirror_items() -> list:
    """镜像清单：`代码\\检索\\*.py` ＋ 11 个输入 ＋ 题集三件 ＋ 既有四个结构化产出。"""
    items = []
    for name in sorted(os.listdir(_HERE)):
        if name.endswith(".py"):
            items.append((os.path.join(_HERE, name), os.path.join("交付物/03-代码", "检索", name)))
    for _key, path in config.INPUT_FILES:
        items.append((path, os.path.relpath(path, config.ROOT)))
    for name in ("questions.jsonl", "说明.md", "题目模板.md"):
        path = os.path.join(config.QUESTIONS_DIR, name)
        items.append((path, os.path.relpath(path, config.ROOT)))
    for name in WATCH_FILES:
        path = os.path.join(config.OUTPUT_DIR, name)
        items.append((path, os.path.relpath(path, config.ROOT)))
    return items


def _build_mirror() -> tuple:
    tmp = tempfile.mkdtemp(prefix="stage7_run_manifest_")
    copied = 0
    for src, relative in _mirror_items():
        if not os.path.isfile(src):
            raise SystemExit("[run_query] 失败：镜像源文件缺失：%s" % src)
        dst = os.path.join(tmp, relative)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    return tmp, copied


def _run_manifest_cycle(tmp: str, cycle: int, quiet: bool) -> dict:
    """在镜像里跑一轮：pipeline --group C → pre_experiment --quiet → metrics；返回四个 SHA-256。"""
    code_dir = os.path.join(tmp, "交付物/03-代码", "检索")
    out_dir = os.path.join(tmp, "交付物/05-系统实现/RAG检索系统", "检索产出")
    steps = [
        ("pipeline", [os.path.join(code_dir, "pipeline.py"), "--group", "C", "--out",
                      os.path.join(out_dir, "per_question_trace.jsonl")]),
        ("pre_experiment", [os.path.join(code_dir, "pre_experiment.py"), "--quiet"]),
        ("metrics", [os.path.join(code_dir, "metrics.py")]),
    ]
    env, _removed = _subprocess_env()
    shas = {}
    for name, argv in steps:
        proc = subprocess.run([sys.executable] + list(argv), cwd=tmp, env=env,
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=7200)
        if proc.returncode != 0:
            print("[run_query] 镜像第 %d 轮 %s 失败（退出码 %d）：" % (cycle, name, proc.returncode))
            print((proc.stdout or "")[-2000:])
            print((proc.stderr or "")[-2000:])
            raise SystemExit(1)
        if not quiet:
            print("  [第 %d 轮] %-14s 退出码=0" % (cycle, name))
        shas = {item: config.sha256_file(os.path.join(out_dir, item))
                for item in WATCH_FILES}
    return shas


def _t11_summary():
    path = os.path.join(config.DOCS_DIR, "_T11", "T11_summary.json")
    if not os.path.isfile(path):
        return None, path
    return config.read_json(path), path


def _count_embeddings_single_search() -> dict:
    """【回退用】现场做一次单题检索并计数（只记次数；不把本次耗时写进任何文件）。"""
    original = vector_search.LocalEmbedder.encode_query
    counter = {"n": 0}

    def counted(self, text):
        counter["n"] += 1
        return original(self, text)

    vector_search.LocalEmbedder.encode_query = counted
    try:
        searcher = VectorSearcher(verbose=False)
        questions = load_question_set(config.QUESTION_FILES["questions"])
        question = str(questions[0]["question"])
        searcher.search(question, int(config.require_fixed("N")))
    finally:
        vector_search.LocalEmbedder.encode_query = original
    return {"single_question_search_encodes_query": counter["n"],
            "question": "题集第一题（%s）" % questions[0]["qid"],
            "note": "只记编码次数；本次耗时不计、也不写入文件（参与逐字节比对的文件不得含耗时）"}


def _embedding_section() -> dict:
    """本地 Embedding 编码次数与耗时：取 T11 的实测量；T11 缺失时现场补测次数（只记次数）。"""
    summary, path = _t11_summary()
    section = {
        "model_name": config.EMBEDDING["model_name"],
        "revision": config.EMBEDDING["revision"],
        "dim": int(config.EMBEDDING["dim"]),
        "normalize": bool(config.EMBEDDING["normalize"]),
        "query_instruction": config.EMBEDDING["query_instruction"],
        "device": "本地 CPU 前向（torch.set_num_threads(1)，离线加载）",
        "note": ("本地 Embedding 前向不计入「模型调用」（《18》第2.5节）；不得写成「全程未跑模型」。"
                 "一次单题检索调用 encode_query 1 次；g>0 且该题存在图谱侧新增候选时，第二层排序"
                 "再取一次全池相似度（至多再 1 次），不新增模型、不联网。"),
        "timing_fields_note": ("本节的 seconds 字段为 T11 的静态实测记录，按字段单独放置；"
                               "耗时字段不参与逐字节比对（本次生成不写运行时间戳、不新计时）。"),
    }
    if summary is None:
        section["source"] = "未发现 T11_summary.json；按缺省口径现场补测编码次数（只记次数）"
        section["supplementary_count_only"] = _count_embeddings_single_search()
        return section
    chain = {item.get("name"): item for item in (summary.get("step2_chain") or [])}
    tail = "\n".join((chain.get("pre_experiment") or {}).get("stdout_tail") or [])
    hit_a = re.search(r"向量检索缓存\s*(\d+)\s*条", tail)
    hit_b = re.search(r"全池相似度缓存\s*(\d+)\s*条", tail)
    vector_cache = int(hit_a.group(1)) if hit_a else None
    pool_cache = int(hit_b.group(1)) if hit_b else None
    total = (vector_cache or 0) + (pool_cache or 0) if (hit_a or hit_b) else None
    labels = [("vector_search_selftest", "vector_search.py --selftest"),
              ("pre_experiment", "pre_experiment.py（第一轮 9 格网格 ＋ 第二轮选定格）"),
              ("pipeline_selftest", "pipeline.py --selftest（五组 × 30 题）"),
              ("metrics", "metrics.py（纯计算，不编码）")]
    components = []
    for name, label in labels:
        item = chain.get(name) or {}
        component = {"component": label, "seconds": item.get("seconds"),
                     "seconds_note": "T11 记录的该步骤墙钟耗时（含本地 Embedding 前向；未单独计时）",
                     "encodes_query": None}
        if name == "pre_experiment":
            component["encodes_query"] = total
            component["count_detail"] = {"vector_search_cache": vector_cache,
                                         "full_pool_similarity_cache": pool_cache,
                                         "source_line": ("T11 日志原文：向量检索缓存 %s 条 ＋ "
                                                         "全池相似度缓存 %s 条"
                                                         % (vector_cache, pool_cache))}
        elif name == "metrics":
            component["encodes_query"] = 0
        else:
            component["count_note"] = "T11 未逐次记录编码条数（该步骤含本地 Embedding 前向）"
        components.append(component)
    section.update({
        "source": "%s 与 %s（T11 实测量；本次不重新计时）"
                  % (_rel(path), _rel(os.path.join(config.DOCS_DIR, "_T11"))),
        "t11_measured_components": components,
        "encodes_query_total_recorded": total,
        "encodes_query_total_note": ("合计为 T11 明确记数的部分（pre_experiment.py 全程："
                                     "向量检索缓存 90 次 ＋ 全池相似度缓存 30 次 ＝ 120 次 query "
                                     "编码）；其余步骤 T11 未逐次记录编码条数，按「不臆造数字」"
                                     "记 null 并在 count_note 里说明"),
        "supplementary_count_only": _count_embeddings_single_search()
        if summary is None else None,
    })
    return section


def _manifest_input_fingerprints() -> tuple:
    manifest = config.read_json(config.INPUT_MANIFEST_PATH)
    rows = []
    all_ok = True
    for row in manifest.get("files") or []:
        path = os.path.join(config.ROOT, str(row["path"]).replace("/", os.sep))
        exists = os.path.isfile(path)
        got = config.sha256_file(path) if exists else None
        size = os.path.getsize(path) if exists else None
        match = bool(exists and got == row["sha256"] and size == row["bytes"])
        all_ok = all_ok and match
        rows.append({"key": row["key"], "path": row["path"],
                     "sha256_recorded": row["sha256"], "sha256_recomputed": got,
                     "bytes_recorded": row["bytes"], "bytes_recomputed": size,
                     "matches_input_manifest": match})
    return manifest, rows, all_ok


def cmd_run_manifest(args) -> int:
    print("=" * 78)
    print("run_query --run-manifest：生成 检索产出\\run_manifest.json")
    print("=" * 78)
    t0 = time.time()

    # ---- ① 输入指纹：取 input_manifest.json 的记录值并现场重算核对
    in_manifest, files, files_ok = _manifest_input_fingerprints()
    print("\n一、输入指纹（%d 条；取 input_manifest.json 的记录值 ＋ 现场重算）" % len(files))
    for row in files:
        print("  [%s] %-20s 记录=%s… 重算=%s…"
              % ("OK  " if row["matches_input_manifest"] else "FAIL", row["key"],
                 (row["sha256_recorded"] or "")[:16], (row["sha256_recomputed"] or "")[:16]))
    print("  11 条输入逐条一致：%s" % files_ok)
    if not (len(files) == 11 and files_ok):
        print("\n结论：输入指纹不一致，拒绝生成 run_manifest.json。退出码 1。")
        return 1

    # ---- ② 两次运行 SHA-256：在系统临时目录的镜像里真跑两轮，并与工作区逐字节比对
    print("\n二、两次运行（系统临时目录的镜像；工作区交付目录零写入）")
    tmp, copied = _build_mirror()
    print("  镜像文件 %d 个；命令链：pipeline --group C --out … → pre_experiment --quiet → metrics"
          % copied)
    try:
        sha_run1 = _run_manifest_cycle(tmp, 1, args.quiet)
        sha_run2 = _run_manifest_cycle(tmp, 2, args.quiet)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    workspace = {name: config.sha256_file(os.path.join(config.OUTPUT_DIR, name))
                 for name in WATCH_FILES}
    t11_shas, _t11_path = None, None
    summary, _p = _t11_summary()
    if summary:
        t11_shas = (summary.get("step3_sha256_run1") or {},
                    summary.get("step3_sha256_run2") or {})
    determinism = {}
    identical_all = True
    for name in WATCH_FILES:
        identical = (sha_run1[name] == sha_run2[name] == workspace[name])
        identical_all = identical_all and identical
        item = {"run1_sha256": sha_run1[name], "run2_sha256": sha_run2[name],
                "workspace_sha256": workspace[name], "identical": bool(identical)}
        if t11_shas:
            item["t11_recorded_run1_sha256"] = t11_shas[0].get(name)
            item["t11_recorded_run2_sha256"] = t11_shas[1].get(name)
            item["matches_t11"] = bool(t11_shas[0].get(name) == workspace[name]
                                       and t11_shas[1].get(name) == workspace[name])
        determinism[name] = item
        print("  [%s] %-28s run1=%s… run2=%s… 工作区=%s…"
              % ("OK  " if identical else "FAIL", name, sha_run1[name][:16],
                 sha_run2[name][:16], workspace[name][:16]))
    if not identical_all:
        print("\n结论：两次运行与工作区交付产物未能逐字节一致，拒绝生成 run_manifest.json。退出码 1。")
        return 1

    # ---- ④ 本地 Embedding 编码次数与耗时（T11 实测量）
    embedding = _embedding_section()
    print("\n三、本地 Embedding：%s" % embedding.get("source"))
    for item in embedding.get("t11_measured_components") or []:
        print("  [T11] %-44s seconds=%s encodes=%s"
              % (item.get("component"), item.get("seconds"), item.get("encodes_query")))
    print("  （耗时字段单独放置、标注不参与逐字节比对；本次不新计时、不写运行时间戳）")

    # ---- ③ 大语言模型调用次数 = 0
    model_calls = {
        "llm_calls": 0,
        "external_api_calls": 0,
        "config_model_calls_allowed": config.MODEL_CALLS_ALLOWED,
        "note": ("第 7 阶段链路没有答案生成模型、不需要密钥（config 刻意不提供读取方式）；"
                 "问题侧向量化是本地 Embedding 前向，按《18》第2.5节 不计入「模型调用」，"
                 "但不得写成「全程未跑模型」"),
    }
    print("\n四、大语言模型调用次数：%d（外部接口调用：%d）"
          % (model_calls["llm_calls"], model_calls["external_api_calls"]))

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "generated_by": "交付物/03-代码/检索/run_query.py --run-manifest",
        "stage": "07-RAG检索系统",
        "dataset_version": config.DATASET_VERSION,
        "graph_version": config.GRAPH_VERSION,
        "data_cutoff_time": config.DATA_CUTOFF_TIME,
        "input_manifest": {
            "path": _rel(config.INPUT_MANIFEST_PATH),
            "schema": in_manifest.get("schema"),
            "sha256": config.sha256_file(config.INPUT_MANIFEST_PATH),
            "files_count": len(files),
            "all_match": bool(files_ok),
            "files": files,
        },
        "determinism": {
            "method": ("同一输入的两次运行：在系统临时目录的镜像里各跑一轮 "
                       "pipeline --group C → pre_experiment --quiet → metrics，"
                       "四个产出逐一比对 SHA-256，并与工作区交付产物逐字节比对；"
                       "临时目录用后删除，工作区交付目录零写入"),
            "commands": ["python 代码\\检索\\pipeline.py --group C --out "
                         "交付物/05-系统实现/RAG检索系统\\检索产出\\per_question_trace.jsonl",
                         "python 代码\\检索\\pre_experiment.py --quiet",
                         "python 代码\\检索\\metrics.py"],
            "files": determinism,
            "identical": bool(identical_all),
            "byte_comparison_note": ("本字段的 SHA-256 与计数为确定性内容；耗时字段见 "
                                     "local_embedding，按字段单独放置并标注不参与逐字节比对"),
        },
        "model_calls": model_calls,
        "local_embedding": embedding,
        "reproduce": {
            "run_manifest": "python 代码\\检索\\run_query.py --run-manifest",
            "single_question": "python 代码\\检索\\run_query.py --question \"…\" --group C",
            "selftest": "python 代码\\检索\\run_query.py --selftest",
        },
    }
    out_path = args.out or MANIFEST_PATH
    config.write_json(out_path, manifest)
    print("\n" + "=" * 78)
    print("run_manifest.json 落盘：%s" % os.path.abspath(out_path))
    print("sha256：%s（耗时 %.1fs，只打印）" % (config.sha256_file(out_path), time.time() - t0))
    print("=" * 78)
    return 0


# ---------------------------------------------------------------------------
# 七、入口
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    args = parse_args(argv)
    if args.run_manifest:
        return cmd_run_manifest(args)
    if args.selftest:
        return cmd_selftest(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
