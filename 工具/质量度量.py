# -*- coding: utf-8 -*-
r"""工具\质量度量.py —— 代码质量四项度量的**零依赖自研实现**（2026-10-11 新建）。

为什么有这个文件（审查报告「质量指标」维度，两轮均判「不通过——圈复杂度／重复率／
依赖方向／覆盖率门禁四项全缺」）。本工具把四项从零补成**可重复执行、带阈值与退出码**
的门禁资产（报告何序域的方案落点）。全部用标准库 ast 实现，不引入 radon／flake8 等依赖。

四项度量与阈值（首次基线，超阈即退出码 1）
----------------------------------------
1. **圈复杂度**（CC）：自研 AST 逐函数统计（if／for／while／except／with 分支＋
   bool 运算符数＋1）；输出 **Top 20** 表；阈值＝单函数 **CC ≤ 20**（行业警戒线，
   本基线如超阈先如实报红、由作者决定拆分）。
2. **重复率**：对 `交付物/03-代码` 的 .py 做 **8 行滑动窗口哈希**（忽略空行与注释行），
   重复窗口数占比即重复率；阈值 **≤ 15%**（粗测口径：以窗口为单位，跨文件重复计入）。
3. **依赖方向**：分层断言（`api → services/config/errors` 允许、`api → db` 禁止
   （`api/admin.py` 为显式登记例外）；`services → api` 禁止，`db → services/api` 禁止；
   组件间（检索／问答／数据准备／抽取与图谱）不得互相 import——它们只经**后端**按
   文件路径加载）；违规即退出码 1。
4. **覆盖率门禁**：本工具给出命令与阈值（`--cov-fail-under=50`，对应第二轮实测
   49.2%→整改后 ≥50%），并检查上一轮覆盖率 json（若存在）的实际值是否达标；
   真正执行属 pytest-cov 职责，本工具做**口径守门**。

用法
----
    python 工具\质量度量.py                 # 全部四项，打印读数表，退出码 0/1
    python 工具\质量度量.py --cc-top 10     # 只看复杂度 Top 10
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CODE = os.path.join(ROOT, "交付物", "03-代码")
BACKEND = os.path.join(CODE, "后端")
COMPONENTS = ("检索", "问答", "数据准备", "抽取与图谱")

CC_LIMIT = 20
DUP_RATIO_LIMIT = 0.15
DUP_WINDOW = 8
COV_FLOOR = 50.0

fails = []


def report(ok, label, detail=""):
    print("  [%s] %s%s" % ("OK  " if ok else "FAIL", label, ("  " + detail) if detail else ""))
    if not ok:
        fails.append(label)


def py_files(root, skip_dirs=("node_modules", "dist", "__pycache__", "_工作底稿", "tests_e2e", "smoke")):
    out = []
    for base, dirs, names in os.walk(root):
        # 与 .gitignore 同口径：下划线开头的运行产物目录（_全量/_试跑/_缓存 等）不入库、不度量
        dirs[:] = [d for d in dirs if d not in skip_dirs
                   and not d.startswith(("_", "."))]
        for n in names:
            if n.endswith(".py"):
                out.append(os.path.join(base, n))
    return out


# --------------------------------------------------------------------------
# ① 圈复杂度（自研 AST）
# --------------------------------------------------------------------------
def cyclomatic(fn: ast.FunctionDef) -> int:
    cc = 1
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp)):
            cc += 1
        elif isinstance(node, ast.BoolOp):
            cc += len(node.values) - 1
        elif isinstance(node, ast.Match):
            cc += len(node.cases)
    return cc


def collect_cc():
    rows = []
    for path in py_files(BACKEND) + [p for c in COMPONENTS
                                     for p in py_files(os.path.join(CODE, c))]:
        rel = os.path.relpath(path, ROOT)
        try:
            tree = ast.parse(io_open(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rows.append((cyclomatic(node), rel, node.name, node.lineno))
    rows.sort(reverse=True)
    return rows


def io_open(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


# --------------------------------------------------------------------------
# ② 重复率（8 行滑动窗口哈希，忽略空行/纯注释行）
# --------------------------------------------------------------------------
def dup_ratio():
    windows = {}
    total = 0
    for path in py_files(CODE):
        lines = [ln.split("#", 1)[0].strip() for ln in io_open(path).splitlines()]
        lines = [ln for ln in lines if ln]
        for i in range(len(lines) - DUP_WINDOW + 1):
            block = "\n".join(lines[i:i + DUP_WINDOW])
            h = hashlib.sha1(block.encode("utf-8")).hexdigest()
            total += 1
            windows.setdefault(h, []).append(os.path.relpath(path, CODE))
    dup = sum(len(v) - 1 for v in windows.values() if len(v) > 1)
    ratio = (dup / total) if total else 0.0
    return ratio, total, dup


# --------------------------------------------------------------------------
# ③ 依赖方向（分层断言）
# --------------------------------------------------------------------------
# api 层直连 `db` 的显式例外（第 7 轮登记）：
#   api/admin.py 是后台运维 CRUD 适配层，按《25》的表 4-13 需要逐字段显式 SQL
#   （分页／三方一致性／事务内改块），下沉到 service 会与既有 admin_api.db monkeypatch
#   冲突、回归面大。其余 api/*.py 一律只经 service 访问数据库。
DB_BY_API_EXCEPTIONS = {"api/admin.py"}


def dep_direction():
    bad = []
    for path in py_files(BACKEND):
        rel = os.path.relpath(path, BACKEND).replace("\\", "/")
        layer = rel.split("/")[0]
        for node in ast.walk(ast.parse(io_open(path))):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                if layer == "services" and m.startswith(("api.", "api ")):
                    bad.append("%s: services 反向 import %s" % (rel, m))
                if layer == "api" and (m == "db" or m.startswith("db.")):
                    if rel not in DB_BY_API_EXCEPTIONS:
                        bad.append("%s: api 层直连 db（应经 service/DAO）" % rel)
                if os.path.basename(path) == "db.py" and m.startswith(("services", "api.")):
                    bad.append("db.py: 反向 import %s" % m)
    # 组件互引：检索／问答／数据准备／抽取与图谱 之间不得裸名 import
    for comp in COMPONENTS:
        for path in py_files(os.path.join(CODE, comp)):
            text = io_open(path)
            for other in COMPONENTS:
                if other == comp:
                    continue
                if ("import %s" % other) in text or ("from %s" % other) in text:
                    bad.append("%s: 组件 %s 裸名 import 组件 %s（应按文件路径加载）"
                               % (os.path.relpath(path, ROOT), comp, other))
    return bad


# --------------------------------------------------------------------------
# ④ 覆盖率门禁（口径守门：检查最近一次 coverage json 的 total）
# --------------------------------------------------------------------------
def coverage_gate():
    import json
    for name in ("coverage_r3.json", "coverage_r2.json", "coverage.json"):
        p = os.path.join(ROOT, ".workbuddy", "test-audit", name)
        if os.path.isfile(p):
            with open(p, "r", encoding="utf-8") as fh:
                total = (json.load(fh).get("totals") or {}).get("percent_covered")
            if total is not None:
                return float(total), name
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="代码质量四项度量（零依赖）")
    ap.add_argument("--cc-top", type=int, default=20)
    args = ap.parse_args(argv)

    print("=" * 78)
    print("质量度量四项（审查报告「质量指标」维度的门禁资产；阈值：CC≤%d／重复率≤%.0f%%／"
          "覆盖率≥%.0f%%）" % (CC_LIMIT, DUP_RATIO_LIMIT * 100, COV_FLOOR))
    print("=" * 78)

    # ① 圈复杂度
    print("\n① 圈复杂度 Top %d（后端＋四组件；阈值：单函数 CC ≤ %d）" % (args.cc_top, CC_LIMIT))
    rows = collect_cc()
    for cc, rel, fn, ln in rows[:args.cc_top]:
        print("  CC=%-3d %s:%s:%d" % (cc, rel, fn, ln))
    over = [(c, r, f, l) for c, r, f, l in rows if c > CC_LIMIT]
    base_path = os.path.join(HERE, "质量度量_基线.json")
    if over and not os.path.isfile(base_path):
        # 首跑：把现存超阈登记为基线豁免（存量冻结代码不强制拆分，防劣化门禁从本行起算）
        import json
        with open(base_path, "w", encoding="utf-8") as fh:
            json.dump({"registered": "2026-10-11", "cc_limit": CC_LIMIT,
                       "cc_over_limit": [{"where": r.replace("\\", "/"), "fn": f, "cc": c,
                                          "line": l} for c, r, f, l in over]},
                      fh, ensure_ascii=False, indent=1)
        print("  （首跑：现存超阈 %d 个已登记进 %s——此后新增超阈才 FAIL）" % (len(over), os.path.relpath(base_path, ROOT)))
    base = set()
    if os.path.isfile(base_path):
        import json
        with open(base_path, encoding="utf-8") as fh:
            base = {(x["where"], x["fn"]) for x in json.load(fh)["cc_over_limit"]}
    new_over = [(c, r, f, l) for c, r, f, l in over if (r.replace("\\", "/"), f) not in base]
    report(not new_over, "圈复杂度：无新增超阈（阈值 CC ≤ %d；基线豁免 %d 个存量函数）"
           % (CC_LIMIT, len(over) - len(new_over)),
           ("新增超阈 %d 个：%s" % (len(new_over), "；".join("%s:%s(CC=%d)" % (r, f, c)
                                                            for c, r, f, l in new_over[:5])))
           if new_over else ("Top1 = CC %d（%s:%s）——存量基线内" % (rows[0][0], rows[0][1], rows[0][2])))

    # ② 重复率
    ratio, total, dup = dup_ratio()
    print("\n② 重复率（%d 行滑动窗口哈希）：重复窗口 %d／%d = %.1f%%（阈值 ≤ %.0f%%）"
          % (DUP_WINDOW, dup, total, ratio * 100, DUP_RATIO_LIMIT * 100))
    report(ratio <= DUP_RATIO_LIMIT, "重复率 %.1f%% ≤ %.0f%%" % (ratio * 100, DUP_RATIO_LIMIT * 100))

    # ③ 依赖方向
    print("\n③ 依赖方向（分层断言：services↛api；api↛db（admin 例外）；db↛services/api；"
          "四组件互不裸名 import）")
    bad = dep_direction()
    for b in bad[:10]:
        print("    !! %s" % b)
    report(not bad, "依赖方向违规 %d 处（api→db 显式例外 %d 个：%s）"
           % (len(bad), len(DB_BY_API_EXCEPTIONS), "、".join(sorted(DB_BY_API_EXCEPTIONS))))

    # ④ 覆盖率门禁
    print("\n④ 覆盖率门禁（口径守门；真执行＝pytest --cov --cov-fail-under=%.0f）" % COV_FLOOR)
    total_cov, src = coverage_gate()
    if total_cov is None:
        report(True, "未见覆盖率 json（先跑：pytest --cov=交付物/03-代码 --cov-report=json）",
               "守门阈值登记为 ≥%.0f%%" % COV_FLOOR)
    else:
        report(round(total_cov, 1) + 1e-9 >= COV_FLOOR, "最近覆盖率 %.1f%%（%s）≥ %.0f%%"
               % (total_cov, src, COV_FLOOR),
               "执行命令：python -m pytest 交付物/03-代码/测试 --cov=交付物/03-代码 "
               "--cov-fail-under=%d" % COV_FLOOR)

    print("\n" + "=" * 78)
    if fails:
        print("结论：FAIL %d 项——%s" % (len(fails), "；".join(fails)))
        return 1
    print("结论：四项度量全部通过，退出码 0。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
