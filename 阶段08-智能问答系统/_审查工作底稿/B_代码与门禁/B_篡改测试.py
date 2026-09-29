# -*- coding: utf-8 -*-
"""复核线 B 的**独立**假阴性测试：镜像 ＋ 篡改，逐例跑 工具\验收第8阶段.py 并比对期望。

不复用 `验收第8阶段.py --selftest`（它自带的三例不算完成）。本脚本自建镜像、自造反例。
只读工作区；全部动作发生在系统临时目录。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8")

REPO = r"C:\Users\15129\Desktop\毕业设计"
GATE = os.path.join(REPO, "工具", "验收第8阶段.py")

# 镜像文件集：门禁自带 MIRROR_FILES 的超集（补上《22》，使 H1/H2/H3 能走「通过」路径）
FILES = [
    ".gitignore",
    "代码/检索/config.py",
    "代码/问答/config.py", "代码/问答/rules.py", "代码/问答/prompt.py",
    "代码/问答/assemble.py", "代码/问答/answer.py", "代码/问答/history.py",
    "代码/问答/run_answer.py", "代码/问答/model_selection.py", "代码/问答/check_inputs.py",
    "代码/问答/README.md",
    "阶段07-RAG检索系统/检索产出/per_question_trace.jsonl",
    "阶段07-RAG检索系统/检索产出/input_manifest.json",
    "阶段07-RAG检索系统/检索产出/run_manifest.json",
    "阶段07-RAG检索系统/预实验问题集/questions.jsonl",
    "阶段05-数据准备/数据集/v2.1/clean/documents.jsonl",
    "阶段05-数据准备/数据集/v2.1/chunks/chunks.jsonl",
    "阶段05-数据准备/数据集/v2.1/meta/dataset.json",
    "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/nodes.csv",
    "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/edges.csv",
    "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/graph_stats.json",
    "阶段08-智能问答系统/21-第8阶段任务书（智能问答系统）.md",
    "阶段08-智能问答系统/22-第8阶段产出文档（智能问答系统）.md",
    "阶段08-智能问答系统/问答产出/input_manifest.json",
    "阶段08-智能问答系统/问答产出/prompt_snapshot.json",
    "阶段08-智能问答系统/问答产出/answer_trace.jsonl",
    "阶段08-智能问答系统/问答产出/qa_records.jsonl",
    "阶段08-智能问答系统/问答产出/run_manifest.json",
    "阶段08-智能问答系统/问答产出/selection_matrix.jsonl",
    "阶段08-智能问答系统/问答产出/selection_decision.json",
    "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md",
    "阶段07-RAG检索系统/19-第7阶段产出文档（RAG检索系统）.md",
    "00-项目总览与索引.md",
    "02-项目执行总控文档.md",
]
TRACE_REL = "阶段08-智能问答系统/问答产出/answer_trace.jsonl"
REC_REL = "阶段08-智能问答系统/问答产出/qa_records.jsonl"
MAN_REL = "阶段08-智能问答系统/问答产出/run_manifest.json"


def build_mirror(tag):
    root = tempfile.mkdtemp(prefix="B_mirror_%s_" % tag)
    for relp in FILES:
        src = os.path.join(REPO, relp.replace("/", os.sep))
        dst = os.path.join(root, relp.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    subprocess.run(["git", "-c", "user.name=g", "-c", "user.email=g@l",
                    "-c", "commit.gpgsign=false", "init", "-q"], cwd=root, capture_output=True)
    subprocess.run(["git", "-c", "user.name=g", "-c", "user.email=g@l",
                    "-c", "commit.gpgsign=false", "add", "-A"], cwd=root, capture_output=True)
    subprocess.run(["git", "-c", "user.name=g", "-c", "user.email=g@l",
                    "-c", "commit.gpgsign=false", "commit", "-q", "-m", "m"],
                   cwd=root, capture_output=True)
    return root


def read_jsonl(p):
    with open(p, "r", encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def write_jsonl(p, rows):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def patch_jsonl(p, fn):
    rows = read_jsonl(p)
    fn(rows)
    write_jsonl(p, rows)


def sync_manifest_sha(root):
    """把 run_manifest 里 6 个产物的 SHA-256/字节数改成现场实测值（「聪明篡改」）。

    绕过 G4 的产物新鲜度检查，用于回答「撇开 SHA 校验，语义判据本身存不存在」。
    """
    mp = os.path.join(root, MAN_REL.replace("/", os.sep))
    with open(mp, "r", encoding="utf-8") as f:
        man = json.load(f)
    for key, row in (man.get("artifacts_sha256") or {}).items():
        cand = os.path.join(root, row["path"].replace("/", os.sep)) \
            if os.path.isabs(row["path"]) is False else row["path"]
        # 清单里 path 是**绝对路径**（指向原仓库）→ 改写到镜像内的同相对路径
        rel = os.path.relpath(row["path"], REPO)
        cand = os.path.join(root, rel)
        if os.path.isfile(cand):
            import hashlib
            h = hashlib.sha256()
            with open(cand, "rb") as fh:
                for b in iter(lambda: fh.read(1 << 20), b""):
                    h.update(b)
            row["sha256"] = h.hexdigest()
            row["bytes"] = os.path.getsize(cand)
    with open(mp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(man, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def graph_replace(rows, qid, marker):
    """把某题 answer_text 的【知识图谱路径】段内容换成 marker。"""
    heads = ["【回答】", "【证据来源】", "【知识图谱路径】", "【数据截至与判定区间】"]
    for r in rows:
        if r.get("qid") != qid:
            continue
        t = r.get("answer_text") or ""
        i = t.find(heads[2])
        j = t.find(heads[3])
        if i >= 0 and j > i:
            r["answer_text"] = t[:i] + heads[2] + "\n" + marker + "\n\n" + t[j:]


# ---------------- 反例 ----------------
def c1_evidence_order(root):
    patch_jsonl(os.path.join(root, TRACE_REL.replace("/", os.sep)),
                lambda rows: [r.__setitem__("evidence", list(reversed(r.get("evidence") or [])))
                              for r in rows if r.get("qid") == "PE-01"])
    return "颠倒 PE-01 的 evidence 数组顺序"


def c2_citation(root):
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-02":
                r["answer_text"] = (r.get("answer_text") or "").replace("[证据1]", "[证据99]", 1)
    patch_jsonl(os.path.join(root, TRACE_REL.replace("/", os.sep)), fn)
    return "PE-02 的 [证据1] → [证据99]"


def c3_graph_section(root):
    patch_jsonl(os.path.join(root, TRACE_REL.replace("/", os.sep)),
                lambda rows: graph_replace(rows, "PE-03", "本次回答未使用图谱扩展"))
    return "PE-03 图谱段换成固定标注，graph_used 仍为真"


def c4_total_tokens(root):
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-01":
                r["token_account"]["total_tokens"] = 3601
    patch_jsonl(os.path.join(root, TRACE_REL.replace("/", os.sep)), fn)
    return "PE-01 的 token_account.total_tokens → 3601（> 预算 3600）"


def c5_evidence_type(root):
    def fn(rows):
        for r in rows:
            if (r.get("answer") or {}).get("answer_id") == "A-001":
                for e in (r.get("answer_evidence") or []):
                    e["evidence_type"] = "表外取值"
    patch_jsonl(os.path.join(root, REC_REL.replace("/", os.sep)), fn)
    return "A-001 的 answer_evidence[].evidence_type → 表外取值"


def c6_temperature(root):
    p = os.path.join(root, "代码", "问答", "config.py")
    with open(p, "r", encoding="utf-8") as f:
        t = f.read()
    t = t.replace('"temperature": 0,', '"temperature": 0.7,', 1)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    return "代码\\问答\\config.py 的 ANSWER['temperature'] → 0.7"


def c7_k_literal(root):
    p = os.path.join(root, "代码", "问答", "config.py")
    with open(p, "r", encoding="utf-8") as f:
        t = f.read()
    t = t.replace('K = _need("K")', "K = 8", 1)
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(t)
    return "代码\\问答\\config.py 的 K = _need(\"K\") → 字面量 K = 8"


def c8_manifest_calls(root):
    p = os.path.join(root, MAN_REL.replace("/", os.sep))
    with open(p, "r", encoding="utf-8") as f:
        man = json.load(f)
    man["model_calls"]["total"] = 999
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(man, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return "run_manifest.model_calls.total → 999"


def run_gate(root, tag):
    emit = os.path.join(root, "_rows.json")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run([sys.executable, GATE, "--root", root, "--profile", "full",
                           "--emit-json", emit], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=7200)
    with open(emit, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_exit"] = proc.returncode
    with open(os.path.join(root, "..", "_log_%s.txt" % tag), "w", encoding="utf-8",
              newline="\n") as f:
        f.write(proc.stdout or "")
    return data


def main():
    cases = [
        ("pristine", None, set()),
        ("case1-evidence-order", c1_evidence_order, {"C3"}),
        ("case2-citation", c2_citation, {"D2", "E4"}),
        ("case3-graph-section", c3_graph_section, {"D4", "E2"}),
        ("case4-total-tokens", c4_total_tokens, {"C4"}),
        ("case5-evidence-type", c5_evidence_type, {"F1"}),
        ("case6-temperature", c6_temperature, {"B1"}),
        ("case7-k-literal", c7_k_literal, {"B2"}),
        ("case8-manifest-calls", c8_manifest_calls, {"B4"}),
    ]
    results = []
    tmpdirs = []
    for tag, tamper, expect in cases:
        root = build_mirror(tag)
        tmpdirs.append(root)
        desc = "原样副本（正向对照）"
        if tamper:
            desc = tamper(root)
        data = run_gate(root, tag)
        got = set(data.get("fails") or [])
        unrun = set(data.get("unrun") or [])
        envf = set(data.get("env_fails") or [])
        results.append((tag, desc, expect, got, unrun, envf, data["_exit"]))
        print("[%s] %s" % (tag, desc))
        print("     退出码=%s  FAIL=%s  UNRUN=%s  ENV=%s"
              % (data["_exit"], sorted(got), sorted(unrun), sorted(envf)))
        sys.stdout.flush()

    base = set(results[0][3])
    print("\n" + "=" * 78)
    print("基线（原样副本）FAIL 集 = %s（这些是镜像本身缺 阶段02 等造成的，非篡改所致）" % sorted(base))
    print("=" * 78)
    print("%-22s %-28s %-30s %s" % ("反例", "期望 FAIL", "实测新增 FAIL", "判定"))
    for tag, desc, expect, got, unrun, envf, ec in results[1:]:
        new = sorted(got - base)
        exp = sorted(expect)
        verdict = "抓到" if set(exp) <= set(got) else "★漏判★"
        print("%-22s %-28s %-30s %s" % (tag, "、".join(exp) or "∅", "、".join(new) or "∅", verdict))
    print("=" * 78)

    # ---- 聪明篡改：改完再同步 run_manifest 的产物 SHA，绕过 G4 ----
    print("\n【聪明篡改】改完 answer_trace/qa_records 后同步 run_manifest.artifacts_sha256，"
          "绕过 G4 的产物新鲜度检查：")
    for tag, tamper, expect in (("smart4-total-tokens", c4_total_tokens, {"C4"}),
                                ("smart5-evidence-type", c5_evidence_type, {"F1"})):
        root = build_mirror(tag)
        tmpdirs.append(root)
        tamper(root)
        sync_manifest_sha(root)
        data = run_gate(root, tag)
        got = set(data.get("fails") or [])
        new = sorted(got - base)
        print("  %-24s 期望 FAIL=%-10s 实测新增 FAIL=%-12s 退出码=%s → %s"
              % (tag, "、".join(sorted(expect)), "、".join(new) or "∅", data["_exit"],
                 "抓到" if expect <= got else "★漏判（假阴性）★"))

    for d in tmpdirs:
        shutil.rmtree(d, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
