# -*- coding: utf-8 -*-
r"""C 线复核 · 项8：破坏试验（核心动作）。

在**系统临时目录**里建镜像根（复用 工具\验收第8阶段.py 自己的 build_mirror/files 清单，
不在工作区写任何东西），构造 5 个反例，逐个跑
    python 工具\验收第8阶段.py --root <镜像根> --profile full --emit-json ...
读出实测 FAIL 集，与「原样副本」基线 FAIL 集相减得「新增 FAIL」，
再与期望的 FAIL 行比对，判定「捕获／漏网（假阴性）」。

反例（对 问答产出\ 的副本做，不碰工作区）：
  ① 引用编号越界：把某题正文里一个 [证据n] 改成 [证据99]
  ② 证据顺序颠倒：把 PE-01 的 evidence 数组顺序反转
  ③ 图谱段替换：把某个 graph_used=true 题的「知识图谱路径」段换成
     「本次回答未使用图谱扩展」，而 graph_used 仍为真
  ④ 预算越限：把某题 token_account.total_tokens 改成 3601
  ⑤ evidence_type 表外取值：把某条 answer_evidence 的 evidence_type 改成「其它来源」

正对照：原样副本的基线 FAIL 集必须稳定（同一镜像连跑两次一致）；且每个反例必须真的改动了文件字节。
"""
import importlib.util
import json
import os
import shutil
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

# 复用门禁脚本本体（模块级会按默认 root=REPO_ROOT 解析参数；这里把 argv 收干净）
sys.argv = ["验收第8阶段.py"]
_spec = importlib.util.spec_from_file_location(
    "stage8_gate", os.path.join(ROOT, "工具", "验收第8阶段.py"))
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

TRACE_REL = gate.ANSWER_TRACE_REL
QA_REL = "阶段08-智能问答系统/问答产出/qa_records.jsonl"


def _trace_path(root):
    return os.path.join(root, TRACE_REL.replace("/", os.sep))


def _qa_path(root):
    return os.path.join(root, QA_REL.replace("/", os.sep))


def tamper_citation(root):
    """① 把 PE-02 正文里一个 [证据1] 改成 [证据99]（m<99 → 越界）。"""
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-02":
                r["answer_text"] = (r.get("answer_text") or "").replace("[证据1]", "[证据99]", 1)
    gate.rewrite_jsonl(_trace_path(root), fn)
    return "PE-02 正文 [证据1]→[证据99]（越界）"


def tamper_order(root):
    """② 反转 PE-01 的 evidence 数组顺序。"""
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-01":
                r["evidence"] = list(reversed(r.get("evidence") or []))
    gate.rewrite_jsonl(_trace_path(root), fn)
    return "PE-01 evidence 数组顺序反转"


def tamper_graph(root):
    """③ 把 PE-03 的系统图谱段换成固定标注，graph_used 仍为真。"""
    sys.path.insert(0, os.path.join(root, "代码", "问答"))
    for name in ("config", "rules", "prompt", "assemble", "answer", "history"):
        sys.modules.pop(name, None)
    import prompt as pm  # noqa

    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-03":
                secs = pm.split_answer_sections(r.get("answer_text") or "")
                sec = secs.get("知识图谱路径")
                body = sec if isinstance(sec, str) else ((sec or {}).get("text") or "")
                r["answer_text"] = (r.get("answer_text") or "").replace(
                    "【知识图谱路径】\n" + body,
                    "【知识图谱路径】\n" + pm.NO_GRAPH_MARKER)
    gate.rewrite_jsonl(_trace_path(root), fn)
    return "PE-03 图谱段→「%s」（graph_used 仍真）" % pm.NO_GRAPH_MARKER


def tamper_budget(root):
    """④ 把 PE-04 的 token_account.total_tokens 改成 3601（>3600）。"""
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-04":
                r["token_account"]["total_tokens"] = 3601
    gate.rewrite_jsonl(_trace_path(root), fn)
    return "PE-04 token_account.total_tokens→3601（>3600）"


def tamper_evidence_type(root):
    """⑤ 把第 1 条记录的首个 answer_evidence.evidence_type 改成表外取值「其它来源」。"""
    def fn(rows):
        ae = rows[0].get("answer_evidence") or []
        if ae:
            ae[0]["evidence_type"] = "其它来源"
    gate.rewrite_jsonl(_qa_path(root), fn)
    return "第1条记录 answer_evidence[0].evidence_type→「其它来源」"


CASES = [
    ("case1-citation-oob", tamper_citation, {"D2", "E4"}),
    ("case2-evidence-order", tamper_order, {"C3"}),
    ("case3-graph-section", tamper_graph, {"D4", "E2"}),
    ("case4-budget-over", tamper_budget, {"C4"}),
    ("case5-evidence-type", tamper_evidence_type, set()),
]


def run_gate(root, label, emit):
    return gate.run_mirror_gate(root, label, emit, keep=False)


def sha_of(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    tmpdirs = []
    print("=" * 100)
    print("项8  破坏试验（镜像根在系统临时目录；门禁＝工具\\验收第8阶段.py --root --profile full）")
    print("=" * 100)

    # --- 基线：原样副本 ---
    root, copied, missing, git_ok = gate.build_mirror("baseline")
    tmpdirs.append(root)
    base = run_gate(root, "baseline", os.path.join(root, "_rows.json"))
    def failset(d):
        return set(d.get("fails") or []) | set(d.get("env_fails") or [])

    def rowmap(d):
        return {r["id"]: r["status"] for r in (d.get("rows") or [])}

    base_fail = failset(base)
    base_unrun = set(base.get("unrun") or [])
    print("\n[基线] 原样副本：复制 %d 文件（缺 %d）、git=%s、退出码 %s"
          % (copied, missing, git_ok, base.get("_exit")))
    print("   基线 FAIL 集 = %s" % ("、".join(sorted(base_fail)) or "∅"))
    print("   基线 环境失败 = %s" % ("、".join(sorted(base.get("env_fails") or [])) or "∅"))
    print("   基线未执行 = %s" % ("、".join(sorted(base_unrun)) or "∅"))

    # 正对照1：基线可重现（再建一个原样镜像，FAIL 集必须相同）
    root2, _, _, _ = gate.build_mirror("baseline2")
    tmpdirs.append(root2)
    base2 = run_gate(root2, "baseline2", os.path.join(root2, "_rows.json"))
    base2_fail = failset(base2)
    print("   [正对照1] 第二个原样副本 FAIL 集 = %s → 与基线相同 = %s"
          % ("、".join(sorted(base2_fail)), base_fail == base2_fail))

    results = []
    for tag, fn, expect_rows in CASES:
        r, c, m, gk = gate.build_mirror(tag)
        tmpdirs.append(r)
        # 改动前字节指纹
        tgt = _qa_path(r) if "evidence-type" in tag else _trace_path(r)
        before = sha_of(tgt)
        desc = fn(r)
        after = sha_of(tgt)
        changed = before != after
        emit = os.path.join(r, "_rows.json")
        data = run_gate(r, tag, emit)
        got = failset(data)
        unrun = set(data.get("unrun") or [])
        added = got - base_fail
        expected_added = set(expect_rows) | {"G4"}  # 改产物必触发 G4 指纹复算
        results.append({
            "tag": tag, "desc": desc, "changed": changed, "exit": data.get("_exit"),
            "added": sorted(added), "expected": sorted(expected_added),
            "got": sorted(got), "unrun": sorted(unrun), "data": data,
        })
        print("\n" + "-" * 100)
        print("[%s] %s" % (tag, desc))
        print("   文件确实被改动 = %s；退出码 = %s" % (changed, data.get("_exit")))
        print("   期望新增 FAIL 行 = %s" % ("、".join(sorted(expected_added)) or "∅"))
        print("   实测新增 FAIL 行 = %s" % ("、".join(sorted(added)) or "∅"))

    # --- 汇总判定 ---
    print("\n" + "=" * 100)
    print("破坏试验结果表")
    print("=" * 100)
    print("%-22s %-14s %-9s %-26s %-26s %s"
          % ("反例", "期望新增FAIL", "退出码", "实测新增FAIL", "实测未执行", "判定"))
    n_fn = 0
    for x in results:
        exp = set(x["expected"])
        add = set(x["added"])
        if x["tag"] == "case5-evidence-type":
            ok = not add  # 期望：表外 evidence_type 无人检查 → 漏网
            verdict = "漏网（假阴性）" if ok else "被捕获"
            if ok:
                n_fn += 1
        else:
            ok = len(add) > 0
            verdict = "被捕获" if ok else "漏网（假阴性）"
            if not ok:
                n_fn += 1
        print("%-22s %-14s %-9s %-26s %-26s %s"
              % (x["tag"], "、".join(sorted(exp)) or "∅", x["exit"],
                 "、".join(x["added"]) or "∅", "、".join(x["unrun"]) or "∅", verdict))

    # 关键行明细：逐个反例，把期望行在实测里的状态抓出来
    print("\n[关键行状态明细]（每个反例，逐期望行给出实测状态）")
    for x in results:
        rm = rowmap(x["data"])
        for rk in sorted(set(x["expected"])):
            print("   %-22s %-4s = %s" % (x["tag"], rk, rm.get(rk)))
        # 该反例里所有非 OK 行
        bad = {k: v for k, v in rm.items() if v != "OK"}
        print("   %-22s 全部非 OK 行 = %s" % ("", "、".join("%s:%s" % (k, v) for k, v in sorted(bad.items())) or "∅"))

    print("\n漏网（假阴性）数 = %d" % n_fn)
    print("未执行行（各反例）＝ %s" % {x["tag"]: x["unrun"] for x in results})
    print("\n[临时镜像根] 将在本脚本退出时删除：")
    for t in tmpdirs:
        print("   %s" % t)
    for t in tmpdirs:
        shutil.rmtree(t, ignore_errors=True)
    print("   已删除。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
