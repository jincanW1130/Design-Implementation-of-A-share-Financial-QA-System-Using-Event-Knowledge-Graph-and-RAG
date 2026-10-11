# -*- coding: utf-8 -*-
r"""工具\变异测试.py —— 变异测试试点执行器（审查报告「变异测试」维度两批目标的**第一批试点**）。

报告口径（苏雅域）：第一批目标＝metrics/rules/chunk/dedup 的变异分数 ≥80%。本试点对
**数据准备组件的两个判据核心**（`dedup.py` 的 `rank_key`／`decide_reason`——查重排序与
败者归因的一行之差即翻转结果的逻辑）实施**算子级变异**，用既有测试套件（test_e_data_prep，
46 例）判定 killed／survived，产出变异分数留档。

为什么自研而不装 mutmut：mutmut/cosmic-ray 需要联网安装与全局配置；本试点只需
「AST 单点变换 → 写回 → 跑测试 → 还原」的最小闭环，标准库可实现，且**不引入任何
产品依赖**（对冻结组件的依赖面零增加）。

安全纪律（写回产品文件的唯一例外，三重保护）
----------------------------------------
1. 变异源**只写回原路径**（`_bootstrap` 按固定路径加载，无法重定向）——写前备份原文、
   `finally` 无条件还原；
2. 还原后 **sha256 逐字节核验**，不一致即打印醒目告警并退出码 2；
3. 变异过程 `try/finally` 包裹，Ctrl-C／异常路径同样还原。

判读
----
* **killed**（变异体被测试杀死）＝该测试对该判据有实际防护力——好；
* **survived**（变异体存活）＝测试盲区——登记为发现（不判失败：这正是变异测试的产出）；
* **变异分数** ＝ killed / 全部变异体。

用法
----
    python 工具\变异测试.py                       # 全部试点目标
    python 工具\变异测试.py --only rank_key      # 只跑一个目标
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import shutil
import subprocess
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PREP = os.path.join(ROOT, "交付物", "03-代码", "数据准备")
TEST_CMD = [sys.executable, "-m", "pytest",
            os.path.join(ROOT, "交付物", "03-代码", "测试", "test_e_data_prep.py"),
            "-q", "-p", "no:cacheprovider"]

# 试点目标（报告第一批范围：rules/dedup）。fn＝模块级函数名。
TARGETS = [
    {"file": os.path.join(PREP, "dedup.py"), "fn": "rank_key", "label": "dedup.rank_key（查重排序键）"},
    {"file": os.path.join(PREP, "dedup.py"), "fn": "decide_reason", "label": "dedup.decide_reason（败者归因）"},
    {"file": os.path.join(PREP, "dedup.py"), "fn": "effective_url", "label": "dedup.effective_url（URL 归一）"},
]

CMP_FLIP = {ast.Lt: ast.GtE, ast.GtE: ast.Lt, ast.LtE: ast.Gt, ast.Gt: ast.LtE,
            ast.Eq: ast.NotEq, ast.NotEq: ast.Eq, ast.Is: ast.IsNot, ast.IsNot: ast.Is}
BIN_FLIP = {ast.Add: ast.Sub, ast.Sub: ast.Add}


class SingleMutant(ast.NodeTransformer):
    """在指定行号处做**单点**变异（每轮只变一处，保证变异体可归因）。"""

    def __init__(self, line, kind):
        self.line, self.kind, self.done = line, kind, False

    def visit_Compare(self, node):
        self.generic_visit(node)
        if not self.done and node.lineno == self.line and len(node.ops) == 1:
            op = type(node.ops[0])
            if op in CMP_FLIP and self.kind in ("cmp", "any"):
                node.ops = [CMP_FLIP[op]()]
                self.done = True
        return node

    def visit_BinOp(self, node):
        self.generic_visit(node)
        if not self.done and node.lineno == self.line and self.kind in ("bin", "any"):
            op = type(node.op)
            if op in BIN_FLIP:
                node.op = BIN_FLIP[op]()
                self.done = True
        return node


def function_lines(source: str, fn_name: str):
    """模块级函数的起止行（1-based，含装饰器之后的 def 行到函数体结束）。"""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return node.lineno, node.end_lineno
    return None


def mutation_points(source: str, fn_name: str, cap: int):
    """枚举目标函数内的可比对/可翻转点（行号 + 类型）。"""
    lo, hi = function_lines(source, fn_name)
    pts = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and lo <= node.lineno <= hi and len(node.ops) == 1 \
                and type(node.ops[0]) in CMP_FLIP:
            pts.append((node.lineno, "cmp"))
        elif isinstance(node, ast.BinOp) and lo <= node.lineno <= hi and type(node.op) in BIN_FLIP:
            pts.append((node.lineno, "bin"))
    # 去重（同行同类型只保留一个）并截断
    seen, out = set(), []
    for line, kind in pts:
        key = (line, kind)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out[:cap]


def run_tests() -> int:
    r = subprocess.run(TEST_CMD, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=180)
    return r.returncode


def sha256_of(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="变异测试试点（第一批：数据准备 rules/dedup）")
    ap.add_argument("--only", default=None, help="只跑指定 fn 名")
    ap.add_argument("--cap", type=int, default=6, help="每个目标的变异体上限（默认 6）")
    args = ap.parse_args(argv)

    print("=" * 78)
    print("变异测试试点（报告第一批目标的试点子集；判据：变异体被 test_e 杀死＝killed）")
    print("=" * 78)

    results = []
    started = time.time()
    for target in TARGETS:
        fn_name = target["fn"]
        if args.only and args.only != fn_name:
            continue
        path = target["file"]
        original = open(path, "r", encoding="utf-8").read()
        sha_before = sha256_of(path)
        pts = mutation_points(original, fn_name, args.cap)
        print("\n目标 %s：%d 个变异点" % (target["label"], len(pts)))
        killed = survived = 0
        try:
            for line, kind in pts:
                tree = ast.parse(original)
                mut = SingleMutant(line, kind)
                mut.visit(tree)
                if not mut.done:
                    continue
                mutated_src = ast.unparse(tree)
                open(path, "w", encoding="utf-8", newline="").write(mutated_src)
                try:
                    rc = run_tests()
                finally:
                    open(path, "w", encoding="utf-8", newline="").write(original)
                verdict = "killed" if rc != 0 else "survived"
                if rc != 0:
                    killed += 1
                else:
                    survived += 1
                print("  [line %3d %-4s] %s" % (line, kind, verdict))
                results.append({"target": fn_name, "line": line, "kind": kind,
                                "verdict": verdict})
        finally:
            # 三重保护之一：无条件还原（见模块 docstring）
            open(path, "w", encoding="utf-8", newline="").write(original)
        sha_after = sha256_of(path)
        if sha_before != sha_after:
            print("  !! 严重：还原后 sha256 与变异前不一致——请立即从 git 恢复 %s" % path)
            return 2
        score = (killed / (killed + survived)) if (killed + survived) else 0.0
        print("  变异分数（%s）＝ %d killed ／ %d survived ＝ %.0f%%"
              % (fn_name, killed, survived, score * 100))
        results.append({"target": fn_name, "score": round(score, 2),
                        "killed": killed, "survived": survived})

    print("\n" + "=" * 78)
    print("试点完成（%.0fs）。判读：survived 条目＝test_e 的盲区候选（登记进变异测试报告，"
          "不判产品缺陷）。" % (time.time() - started))
    print("还原核验：全部目标 sha256 与变异前一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
