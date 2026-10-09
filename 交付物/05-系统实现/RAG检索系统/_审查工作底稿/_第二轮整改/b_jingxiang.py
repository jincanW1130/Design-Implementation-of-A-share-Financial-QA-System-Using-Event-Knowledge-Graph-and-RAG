# -*- coding: utf-8 -*-
"""通用工具：按《工具\\验收第7阶段.py》的镜像链在系统临时目录里重跑四个产出，并与工作区
交付产物**逐字节**比对；不同则打印 JSON 层差异（哪个键不同）。

用途（本轮整改的公用实验台）：
  * 核验 B-16 的 g 边界改造**没有**改变任何产物字节；
  * 核验 B-18／B-22 的代码改动在现行数据上是否只影响被点名的那一个字段；
  * 复核 B-10 里 `run_manifest.json` 的可复跑性。

只读工作区；临时目录用后删（--keep 可保留）。

用法：
    python 交付物/05-系统实现/RAG检索系统\\_审查工作底稿\\_第二轮整改\\b_jingxiang.py [--step pipeline,pre,metrics]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
CODE = os.path.join(ROOT, "交付物/03-代码", "检索")
OUT = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "检索产出")
QS = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集")
WATCH = ["pre_experiment_matrix.jsonl", "k_selection.json", "per_question_trace.jsonl",
         "metrics_pre.jsonl"]
INPUTS = [
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/clean/documents.jsonl",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/chunks/chunks.jsonl",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/index/faiss.index",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/index/vector_map.jsonl",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/index/build_meta.json",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/meta/dataset.json",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/nodes.csv",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/edges.csv",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/replay.cypher",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/graph_stats.json",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/人工确认清单.json",
]


def sha(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build(tmp, code_dir):
    pairs = []
    for name in sorted(os.listdir(code_dir)):
        if name.endswith(".py"):
            pairs.append((os.path.join(code_dir, name), "交付物/03-代码/检索/" + name))
    for rel in INPUTS:
        pairs.append((os.path.join(ROOT, rel.replace("/", os.sep)), rel))
    for name in ("questions.jsonl", "说明.md", "题目模板.md"):
        pairs.append((os.path.join(QS, name), "交付物/05-系统实现/RAG检索系统/预实验问题集/" + name))
    for name in WATCH:
        pairs.append((os.path.join(OUT, name), "交付物/05-系统实现/RAG检索系统/检索产出/" + name))
    pairs.append((os.path.join(OUT, "run_manifest.json"),
                  "交付物/05-系统实现/RAG检索系统/检索产出/run_manifest.json"))
    pairs.append((os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "_工作底稿", "_T11", "T11_summary.json"),
                  "交付物/05-系统实现/RAG检索系统/_工作底稿/_T11/T11_summary.json"))
    n = 0
    for src, rel in pairs:
        dst = os.path.join(tmp, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        n += 1
    return n


def env():
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    e["HF_HUB_OFFLINE"] = "1"
    e["TRANSFORMERS_OFFLINE"] = "1"
    e["OPENBLAS_NUM_THREADS"] = "1"
    e["OMP_NUM_THREADS"] = "1"
    e["MKL_NUM_THREADS"] = "1"
    e["STAGE7_FORBID_MODEL_CALLS"] = "1"
    return e


def run(argv, cwd):
    p = subprocess.run([sys.executable] + list(argv), cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env(), timeout=7200)
    return p.returncode, (p.stdout or ""), (p.stderr or "")


def diff_json(a, b, path=""):
    """打印两个 JSON 结构不同的键（递归，最多 40 条）。"""
    out = []

    def walk(x, y, p):
        if len(out) >= 40:
            return
        if type(x) is not type(y):
            out.append("%s: 类型 %s → %s" % (p, type(x).__name__, type(y).__name__))
        elif isinstance(x, dict):
            for k in sorted(set(x) | set(y)):
                if k not in x:
                    out.append("%s.%s: 新增 %r" % (p, k, str(y[k])[:80]))
                elif k not in y:
                    out.append("%s.%s: 消失 %r" % (p, k, str(x[k])[:80]))
                else:
                    walk(x[k], y[k], "%s.%s" % (p, k))
        elif isinstance(x, list):
            if len(x) != len(y):
                out.append("%s: 长度 %d → %d" % (p, len(x), len(y)))
            for i, (u, v) in enumerate(zip(x, y)):
                walk(u, v, "%s[%d]" % (p, i))
        elif x != y:
            out.append("%s: %r → %r" % (p, str(x)[:100], str(y)[:100]))

    walk(a, b, path)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code-dir", default=CODE, help="要镜像的代码目录（默认工作区 代码\\检索）")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--label", default="镜像重跑")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="stage7_bj_")
    print("=" * 78)
    print("%s：镜像 %s" % (args.label, tmp))
    print("代码目录：%s" % args.code_dir)
    print("=" * 78)
    try:
        n = build(tmp, args.code_dir)
        code = os.path.join(tmp, "交付物/03-代码", "检索")
        out_dir = os.path.join(tmp, "交付物/05-系统实现/RAG检索系统", "检索产出")
        for name in WATCH:
            p = os.path.join(out_dir, name)
            if os.path.isfile(p):
                os.remove(p)
        steps = [
            ("check_inputs", [os.path.join(code, "check_inputs.py")]),
            ("run_query_selftest", [os.path.join(code, "run_query.py"), "--selftest", "--quiet"]),
            ("pipeline", [os.path.join(code, "pipeline.py"), "--group", "C", "--out",
                          os.path.join(out_dir, "per_question_trace.jsonl"), "--quiet"]),
            ("pre_experiment", [os.path.join(code, "pre_experiment.py"), "--quiet"]),
            ("metrics", [os.path.join(code, "metrics.py")]),
            ("run_query_run_manifest", [os.path.join(code, "run_query.py"), "--run-manifest",
                                        "--quiet"]),
        ]
        ok = True
        for tag, argv in steps:
            rc, so, se = run(argv, tmp)
            print("  [%s] %-14s 退出码=%d（stdout %d 字节、stderr %d 字节）"
                  % ("OK  " if rc == 0 else "FAIL", tag, rc, len(so), len(se)))
            if rc != 0:
                ok = False
                print("     stderr 尾：%s" % (se.strip().splitlines()[-3:] if se.strip() else ""))
                print("     stdout 尾：%s" % (so.strip().splitlines()[-5:] if so.strip() else ""))
                break
        print("-" * 78)
        print("  镜像文件 %d 个（含 11 输入 ＋ 题集三件 ＋ 代码 ＋ 既有产物）" % n)
        if not ok:
            return 1
        for name in WATCH + ["run_manifest.json"]:
            ws = os.path.join(OUT, name)
            md = os.path.join(out_dir, name)
            exist = os.path.isfile(md)
            same = exist and sha(ws) == sha(md)
            print("  [%s] %-30s 工作区=%s… 镜像=%s…"
                  % ("OK  " if same else "DIFF", name, sha(ws)[:16],
                     sha(md)[:16] if exist else "<缺失>"))
            if not same and exist:
                if name.endswith(".jsonl"):
                    a = [json.loads(l) for l in open(ws, encoding="utf-8") if l.strip()]
                    b = [json.loads(l) for l in open(md, encoding="utf-8") if l.strip()]
                else:
                    a = json.load(open(ws, encoding="utf-8"))
                    b = json.load(open(md, encoding="utf-8"))
                for line in diff_json(a, b):
                    print("        · %s" % line)
        print("=" * 78)
        return 0
    finally:
        if args.keep:
            print("镜像保留在：%s" % tmp)
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
