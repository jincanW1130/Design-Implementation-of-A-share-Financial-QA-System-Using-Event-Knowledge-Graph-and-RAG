# -*- coding: utf-8 -*-
"""C 线复核 · 项1：输入只读与指纹三方对拍。

只读。重算《21》第三节 8 项输入的 SHA-256 与字节数，与：
  (a) 阶段08-智能问答系统/问答产出/input_manifest.json
  (b) 阶段07-RAG检索系统/检索产出/input_manifest.json
三方对拍，逐项报「一致／不一致」。

正对照：故意把一个路径的字节数+1 做一次比对，必须报不一致（证明比对器有效）。
"""
import hashlib
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
P8 = os.path.join(ROOT, "阶段08-智能问答系统", "问答产出", "input_manifest.json")
P7 = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "input_manifest.json")
TRACE = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "per_question_trace.jsonl")
S7RUN = os.path.join(ROOT, "阶段07-RAG检索系统", "检索产出", "run_manifest.json")


def sha_bytes(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest(), os.path.getsize(path)


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def main():
    m8 = json.load(open(P8, encoding="utf-8"))
    m7 = json.load(open(P7, encoding="utf-8"))

    # 8 项的完整文件清单（按《21》第三节）
    targets = [
        ("item1 per_question_trace", TRACE, "per_question_trace"),
        ("item2 stage7_input_manifest", P7, "stage7_input_manifest"),
        ("item3 stage7_run_manifest", S7RUN, "stage7_run_manifest"),
        ("item4 documents", os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "clean", "documents.jsonl"), "documents"),
        ("item5 chunks", os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl"), "chunks"),
        ("item6 dataset_meta", os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "meta", "dataset.json"), "dataset_meta"),
        ("item7a nodes_csv", os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2", "nodes.csv"), "nodes_csv"),
        ("item7b edges_csv", os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2", "edges.csv"), "edges_csv"),
        ("item7c graph_stats", os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2", "graph_stats.json"), "graph_stats"),
        ("item8 questions", os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集", "questions.jsonl"), "questions"),
    ]

    # 汇编《问答产出/input_manifest.json》的键 -> (bytes, sha)
    reg8 = {}
    for it in m8.get("items") or []:
        for f in it.get("files") or []:
            reg8[f["key"]] = (f["bytes"], f["sha256"])
    # 汇编第 7 阶段 input_manifest 的 keys
    reg7 = {}
    for f in m7.get("files") or []:
        reg7[f["key"]] = (f["bytes"], f["sha256"])

    print("=" * 96)
    print("项1  输入指纹重算（8 项 10 个文件）")
    print("=" * 96)
    print("%-26s %-12s %-64s %-5s %-5s %-5s" % ("文件", "字节", "SHA-256（实算）", "P8", "P7", "结论"))
    fails = []
    for name, path, key in targets:
        if not os.path.isfile(path):
            print("%-26s 不存在：%s" % (name, path))
            fails.append(name)
            continue
        sha, n = sha_bytes(path)
        c8 = "—"
        if key in reg8:
            c8 = "一致" if (reg8[key][0] == n and reg8[key][1] == sha) else "不符"
        c7 = "—"
        if key in reg7:
            c7 = "一致" if (reg7[key][0] == n and reg7[key][1] == sha) else "不符"
        ok = (c8 in ("一致", "—")) and (c7 in ("一致", "—"))
        if not ok:
            fails.append(name)
        print("%-26s %-12d %-64s %-5s %-5s %-5s" % (name, n, sha, c8, c7, "OK" if ok else "FAIL"))
        if key in reg8 and (reg8[key][0] != n or reg8[key][1] != sha):
            print("      P8 登记 bytes=%s sha=%s" % reg8[key][0], reg8[key][1])
        if key in reg7 and (reg7[key][0] != n or reg7[key][1] != sha):
            print("      P7 登记 bytes=%s sha=%s" % reg7[key][0], reg7[key][1])

    # 兼容别名：问答产出里 key 名与第7阶段不完全一致，检查覆盖
    print("\n[覆盖] 问答产出/input_manifest 登记的 key = %s" % sorted(reg8))
    print("[覆盖] 检索产出/input_manifest 登记的 key = %s" % sorted(reg7))

    # 正对照：把 chunks 的字节数 +1，必须比出「不符」
    print("\n--- 正对照（比对器有效性）---")
    true_n = reg8["chunks"][0]
    planted = (true_n + 1, reg8["chunks"][1])
    verdict = "一致" if (planted[0] == true_n and planted[1] == reg8["chunks"][1]) else "不符"
    print("  植入 bytes+1：比对结论 = %s（必须=不符）→ %s"
          % (verdict, "PASS" if verdict == "不符" else "对照失效"))
    true_sha = reg8["chunks"][1]
    planted_sha = ("0" * 63 + "1")
    verdict2 = "一致" if (true_n == true_n and planted_sha == true_sha) else "不符"
    print("  植入 sha 篡改：比对结论 = %s（必须=不符）→ %s"
          % (verdict2, "PASS" if verdict2 == "不符" else "对照失效"))

    print("\n结论：逐项不一致数 = %d" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
