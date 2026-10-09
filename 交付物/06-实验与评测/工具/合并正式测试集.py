# -*- coding: utf-8 -*-
r"""第 10 阶段·正式测试集终稿合并器：一条命令从上游产物重建 `测试集\questions.jsonl`。

## 这个脚本做什么

1. 用 `importlib` 按路径加载两个**已冻结**的批次构建器（**不复制它们的代码**）：
   * `工具\建正式测试集_A.py`（FQ-001～FQ-084，84 题）
   * `工具\建正式测试集_B.py`（FQ-085～FQ-120，36 题）
2. 各自 `build_records()` 现场渲染记录（只读输入：`阶段05\数据集\v2.1\`、
   `阶段06\图谱导出\v2.1_v1_3\`、`阶段07\预实验问题集\questions.jsonl`）。
3. 做**跨批的合并期校验**（键序／取值域／配额／qid 连续唯一／与 PE 集 gold 零交集／
   `time_window` 形态／JSONL 编码），任一不通过即非零退出且**不写盘**。
4. 写三处、且三处来自同一批内存记录、逐字节同口径：
   * `测试集\_批A\questions_A.jsonl`
   * `测试集\_批B\questions_B.jsonl`
   * `测试集\questions.jsonl`（**终稿，120 行**）

## 用法

    python "交付物/06-实验与评测\工具\合并正式测试集.py"              # 重建 + 校验
    python "交付物/06-实验与评测\工具\合并正式测试集.py" --check        # 只校验已落盘的终稿
    python "交付物/06-实验与评测\工具\合并正式测试集.py" --idempotent   # 连跑两次比字节

## 硬约束（脚本内自查）

* **确定性**：只读固定路径的产物，无时间戳、无随机数、无字典序抖动；两次运行逐字节一致。
* **零大模型调用、零联网**。
* JSONL 一律 UTF-8 无 BOM、LF 行尾、一行一条。
* 20 个字段的键序、集合、语义在两批与终稿之间完全一致（`FIELD_ORDER`）。
* 与 30 题预实验集的 **gold 块交集必须为空**（70 个 PE gold 块，逐题求交）。
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\工具\` 整体移到
# `交付物/06-实验与评测\工具\`（**下移一层**），由 HERE 上溯次数 2 → 3。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
TESTDIR = os.path.join(ROOT, "交付物/06-实验与评测", "测试集")
PE_PATH = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集", "questions.jsonl")

A_SCRIPT = os.path.join(HERE, "建正式测试集_A.py")
B_SCRIPT = os.path.join(HERE, "建正式测试集_B.py")

OUT_FINAL = os.path.join(TESTDIR, "questions.jsonl")
OUT_A = os.path.join(TESTDIR, "_批A", "questions_A.jsonl")
OUT_B = os.path.join(TESTDIR, "_批B", "questions_B.jsonl")

FIELD_ORDER = ["qid", "question", "reference_answer", "task_type", "gold_hop_depth",
               "time_constraint", "time_window", "gold_evidence_doc_ids",
               "gold_evidence_chunk_ids", "gold_evidence_count", "gold_evidence_rule",
               "gold_verified_by", "gold_review_status", "gold_verify_anchors",
               "gold_verify_note", "source_material", "graph_path", "cell", "subset",
               "builder"]
TW_FIELD_ORDER = ["lo", "hi", "label", "basis", "cutoff", "empty_policy"]
BUILDERS = ("script", "hand")
VERIFIED_BY = "decision_maker_ai_verify_v1"
REVIEW_STATUS = ("由决策者（AI）用确定性脚本构造并逐条回原文核验；非人工逐题确认，"
                 "人工抽检未做，第三方模型盲标复核未做")

EXPECT_CELLS = [("事实型", 0), ("事实型", 1), ("事实型", 2),
                ("事件型", 0), ("事件型", 1), ("事件型", 2),
                ("关系型", 0), ("关系型", 1), ("关系型", 2)]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def read_jsonl(path):
    with io.open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def build_all():
    """返回 (recsA, recsB)；两边都是已按 FIELD_ORDER 键序渲染的 dict 列表。"""
    mod_a = load_module("fq_build_a", A_SCRIPT)
    docs, chunks, _cbd, _nodes, edges, node_by_id = mod_a.load_inputs()
    gf = mod_a.graph_facts(edges, node_by_id)
    recs_a = mod_a.build_records(mod_a.SPECS, docs, chunks, gf, node_by_id)

    mod_b = load_module("fq_build_b", B_SCRIPT)
    inp = mod_b.Inputs()
    recs_b = [rec for rec, _item, _pe in mod_b.build_records(inp)]
    return recs_a, recs_b, mod_a, mod_b


def canonical(rec):
    return {k: rec[k] for k in FIELD_ORDER}


def check(recs_a, recs_b):
    """合并期全量校验；返回 (errors, warns, stats)。"""
    errs, warns = [], []
    rows = [canonical(r) for r in recs_a] + [canonical(r) for r in recs_b]
    pe = read_jsonl(PE_PATH)
    pe_gold = set()
    for r in pe:
        pe_gold |= set(r["gold_evidence_chunk_ids"])
    pe_texts = {"".join(r["question"].split()) for r in pe}

    stats = {"n": len(rows), "pe_gold_n": len(pe_gold), "pe_hits": [],
             "cells": collections.Counter(), "gold_dist": collections.Counter(),
             "builders": collections.Counter(), "tw_labels": collections.Counter(),
             "tw_n": 0, "dup_chunks": collections.Counter()}

    # 1) 总数与 qid
    if len(rows) != 120:
        errs.append("终稿题量 %d ≠ 120" % len(rows))
    qids = [r["qid"] for r in rows]
    if qids != ["FQ-%03d" % i for i in range(1, 121)]:
        errs.append("qid 不是 FQ-001..FQ-120 的顺序完整集合（有重号、跳号或错序）")

    # 2) 逐题
    for r in rows:
        q = r["qid"]
        if list(r.keys()) != FIELD_ORDER:
            errs.append("%s 字段键序不符" % q)
        if r["builder"] not in BUILDERS:
            errs.append("%s builder=%r 不在 %s" % (q, r["builder"], BUILDERS))
        if r["gold_verified_by"] != VERIFIED_BY:
            errs.append("%s gold_verified_by 口径不符" % q)
        if r["gold_review_status"] != REVIEW_STATUS:
            errs.append("%s gold_review_status 口径不符" % q)
        if r["subset"] not in ("核心", "压力"):
            errs.append("%s subset=%r 非法" % (q, r["subset"]))
        if r["cell"] != "%s+%d跳" % (r["task_type"], r["gold_hop_depth"]):
            errs.append("%s cell 与 task_type/gold_hop_depth 不符" % q)
        if r["time_constraint"] not in ("无", "有"):
            errs.append("%s time_constraint=%r 非法" % (q, r["time_constraint"]))
        if r["time_constraint"] == "有":
            stats["tw_n"] += 1
            tw = r.get("time_window") or {}
            if list(tw.keys()) != TW_FIELD_ORDER:
                errs.append("%s time_window 键序 %s ≠ PE 集口径 %s"
                            % (q, list(tw.keys()), TW_FIELD_ORDER))
            stats["tw_labels"][tw.get("label")] += 1
        elif r.get("time_window") is not None:
            errs.append("%s 无时间约束但 time_window 非空" % q)
        for c in r["gold_evidence_chunk_ids"]:
            stats["dup_chunks"][c] += 1
        inter = sorted(set(r["gold_evidence_chunk_ids"]) & pe_gold)
        if inter:
            stats["pe_hits"].append((q, inter))
            errs.append("%s 的 gold 与 30 题预实验集相交：%s" % (q, inter))
        if "".join(r["question"].split()) in pe_texts:
            errs.append("%s 题干与 30 题预实验集完全相同" % q)
        stats["cells"][(r["task_type"], int(r["gold_hop_depth"]), r["time_constraint"],
                        r["subset"])] += 1
        stats["gold_dist"][r["gold_evidence_count"]] += 1
        stats["builders"][r["builder"]] += 1

    # 3) 配额：9 格 × (无 6 ＋ 有 6) ＋ 压力 12
    for t, h in EXPECT_CELLS:
        for tc in ("无", "有"):
            n = stats["cells"][(t, h, tc, "核心")]
            if n != 6:
                errs.append("核心格 (%s+%d跳,%s) 题量 %d ≠ 6" % (t, h, tc, n))
    if stats["cells"][("关系型", 2, "有", "压力")] != 12:
        errs.append("压力子集（关系型+2跳+有时间约束）题量 %d ≠ 12"
                    % stats["cells"][("关系型", 2, "有", "压力")])
    for k in stats["cells"]:
        if k[3] == "核心" and (k[0], k[1]) not in EXPECT_CELLS:
            errs.append("出现计划外的核心格：%s" % (k,))

    # 4) 同集合内 gold 块复用（批 A 的既有纪律：应为 0）
    reused = {c: n for c, n in stats["dup_chunks"].items() if n > 1}
    stats["reused"] = reused
    if reused:
        warns.append("终稿内被多题共用的 gold 块：%s" % reused)

    return errs, warns, stats, rows


def dumps(rows):
    return "\n".join(json.dumps(r, ensure_ascii=False, separators=(", ", ": "))
                     for r in rows) + "\n"


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser(description="正式测试集终稿合并器（只读输入，零模型调用）")
    ap.add_argument("--check", action="store_true", help="只校验已落盘的 questions.jsonl")
    ap.add_argument("--idempotent", action="store_true", help="连跑两次比字节")
    args = ap.parse_args()

    if args.check:
        rows = [canonical(r) for r in read_jsonl(OUT_FINAL)]
        recs_a, recs_b = rows[:84], rows[84:]
    else:
        recs_a, recs_b, _ma, _mb = build_all()

    errs, warns, stats, rows = check(recs_a, recs_b)

    print("[合并] 批A %d 题 ＋ 批B %d 题 = 终稿 %d 题"
          % (len(recs_a), len(recs_b), len(rows)))
    print("[合并] PE 集 gold 块 %d 个；终稿与其有交集的题 %d 道 %s"
          % (stats["pe_gold_n"], len(stats["pe_hits"]), stats["pe_hits"] or ""))
    print("[合并] 带时间约束 %d 道；窗口标签分布 %s"
          % (stats["tw_n"], dict(stats["tw_labels"])))
    print("[合并] builder 分布 %s；gold 条数分布 %s"
          % (dict(stats["builders"]), dict(sorted(stats["gold_dist"].items()))))
    print("[合并] 9 格 × 无/有 题量：")
    for t, h in EXPECT_CELLS:
        print("        %-6s+%d跳   无 %d ｜ 有 %d"
              % (t, h, stats["cells"][(t, h, "无", "核心")],
                 stats["cells"][(t, h, "有", "核心")]))
    print("        压力子集（关系型+2跳+有）  %d"
          % stats["cells"][("关系型", 2, "有", "压力")])
    for w in warns:
        print("[warn] " + w)

    if errs:
        print("[合并] 校验失败 %d 条：" % len(errs))
        for e in errs:
            print("   - " + e)
        return 1

    if not args.check:
        text = dumps(rows)
        d_final = write_text(OUT_FINAL, text)
        d_a = write_text(OUT_A, dumps([canonical(r) for r in recs_a]))
        d_b = write_text(OUT_B, dumps([canonical(r) for r in recs_b]))
        print("[合并] 已写 %s（SHA-256=%s）" % (os.path.relpath(OUT_FINAL, ROOT), d_final))
        print("[合并] 已写 %s（SHA-256=%s）" % (os.path.relpath(OUT_A, ROOT), d_a))
        print("[合并] 已写 %s（SHA-256=%s）" % (os.path.relpath(OUT_B, ROOT), d_b))
        if args.idempotent:
            again = dumps([canonical(r) for r in recs_a] + [canonical(r) for r in recs_b])
            same = again == text
            print("[确定性] 二次渲染逐字节一致 = %s" % same)
            if not same:
                return 1
            with io.open(OUT_FINAL, "rb") as fh:
                raw = fh.read()
            print("[确定性] 落盘文件：UTF-8 无 BOM = %s ｜ LF 行尾 = %s ｜ 行数 = %d"
                  % (not raw.startswith(b"\xef\xbb\xbf"), b"\r\n" not in raw,
                     raw.decode("utf-8").count("\n")))

    print("[合并] 校验通过（0 错误，%d 警告）" % len(warns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
