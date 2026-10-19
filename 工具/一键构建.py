# -*- coding: utf-8 -*-
"""工具\\一键构建.py —— 第 4 轮（7.4）构建自动化：装依赖 → 跑测试 → 跑门禁 →
构建前端 → 导出论文。

设计纪律
--------
* **幂等**：所有步骤只读上游或重写固定产物（`dist/`、`构建产物/论文_一键构建.docx`）；
  不删数据资产、不改数据库、不新建分支、不 commit。
* **失败即停**：任一步非零退出立刻以该退出码结束，后续步骤不执行。
* **每步打印耗时**：最后汇总一张耗时表，便于定位慢步骤。
* **不跑 `验收第9阶段.py`**：它的 B5 会 `--reset` 重置六表（破坏性），本脚本永不调用。
* 论文导出**不写 `交付物/01-论文/`**：用 `--out` 指到 `交付物/10-部署/构建产物/`
  （该目录已被 .gitignore 覆盖），既验证了导出链路，又不触定稿目录。

用法
----
    python 工具\\一键构建.py                 # 完整流程
    python 工具\\一键构建.py --skip-deps     # 依赖已装好时跳过安装
    python 工具\\一键构建.py --gate          # 全门禁：单测→跨文档→第10→第11→契约快照→前端 test+build
    python 工具\\一键构建.py --skip-deps --skip-frontend --skip-paper   # 只跑后端测试与门禁

可选参数
--------
--gate            门禁模式：固定执行「后端单测→跨文档核验→验收第10→验收第11→
                  契约快照比对→前端 test＋build」，不装依赖、不导出论文；
                  与 `--skip-frontend`／`--skip-paper` 冲突时以门禁序列为准
--skip-deps       跳过 `pip install -r requirements.txt` 与前端依赖安装
--skip-frontend   跳过前端测试与构建
--skip-paper      跳过论文导出
--keep-going      某步失败后继续执行其余步骤（缺省关闭；最终仍以非零退出）
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(ROOT, "交付物", "03-代码", "前端")
BUILD_DIR = os.path.join(ROOT, "交付物", "10-部署", "构建产物")
PAPER_OUT = os.path.join(BUILD_DIR, "论文_一键构建.docx")
MIN_BACKEND_TESTS = 536
MIN_FRONTEND_TESTS = 75


def parse_pytest_counts(output: str) -> dict:
    """从 pytest -q 输出解析用例计数。

    只认 `<数字> passed/skipped/failed/errors`，避免把 "1 warning" 之类误当用例。
    独立审查（2026-10-19）：原门禁只读 `passed`，530 passed + 6 skipped 也能过门；
    这与「真实服务测试连不上就跳过」叠加时会假绿，故把 skipped 计入门禁。
    """
    text = str(output or "")

    def count(word: str) -> int:
        match = re.search(r"(\d+)\s+" + word + r"\b", text)
        return int(match.group(1)) if match else 0

    return {
        "passed": count("passed"),
        "skipped": count("skipped"),
        "failed": count("failed"),
        "errors": count("errors"),
    }


def backend_gate_error(counts: dict) -> str | None:
    """后端门禁判定；返回 None 表示通过。拆成函数便于负向标定测试。"""
    if counts.get("skipped"):
        return "后端单元测试存在 %d 个 skipped（门禁要求 0 skipped）" % counts["skipped"]
    if counts.get("failed") or counts.get("errors"):
        return "后端单元测试存在失败／错误（failed=%d, errors=%d）" % (
            counts.get("failed", 0), counts.get("errors", 0))
    if counts.get("passed", 0) < MIN_BACKEND_TESTS:
        return "后端单元测试（期望 ≥%d passed，实际 %d）" % (
            MIN_BACKEND_TESTS, counts.get("passed", 0))
    return None


def parse_vitest_counts(output: str) -> dict:
    """从 Vitest 汇总行 `Tests  N passed | M skipped (T)` 解析计数。"""
    text = str(output or "")
    line = ""
    match = re.search(r"^\s*Tests\s+(.+)$", text, re.M)
    if match:
        line = match.group(1)

    def count(word: str) -> int:
        found = re.search(r"(\d+)\s+" + word + r"\b", line)
        return int(found.group(1)) if found else 0

    return {
        "passed": count("passed"),
        "skipped": count("skipped"),
        "failed": count("failed"),
    }


def frontend_gate_error(counts: dict) -> str | None:
    if counts.get("skipped"):
        return "前端单元测试存在 %d 个 skipped（门禁要求 0 skipped）" % counts["skipped"]
    if counts.get("failed"):
        return "前端单元测试存在 %d 个 failed" % counts["failed"]
    if counts.get("passed", 0) < MIN_FRONTEND_TESTS:
        return "前端单元测试（期望 ≥%d passed，实际 %d）" % (
            MIN_FRONTEND_TESTS, counts.get("passed", 0))
    return None

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


class BuildFailure(RuntimeError):
    def __init__(self, step: str, code: int, elapsed: float = 0.0):
        super().__init__("%s 失败（退出码 %s）" % (step, code))
        self.step = step
        self.code = code
        self.elapsed = elapsed


def _which(name: str) -> str:
    path = shutil.which(name)
    if not path:
        # 走 BuildFailure 而不是 SystemExit：后者会绕过失败汇总与退出码语义。
        raise BuildFailure("查找命令 %r（请先安装并加入 PATH）" % name, 1)
    return path


def _tail(text: str, lines: int = 8) -> str:
    rows = [r for r in str(text or "").splitlines() if r.strip()]
    return "\n".join(rows[-lines:])


def run_step(title: str, cmd: list, cwd: str | None = None,
             env: dict | None = None) -> tuple:
    """跑一步；返回 (耗时秒, stdout+stderr)。失败抛 BuildFailure。"""
    print("\n" + "=" * 78)
    print("[构建] %s" % title)
    print("       %s" % " ".join(cmd))
    print("=" * 78)
    started = time.perf_counter()
    merged_env = dict(os.environ)
    merged_env.setdefault("PYTHONIOENCODING", "utf-8")
    merged_env.setdefault("PYTHONUTF8", "1")
    if env:
        merged_env.update(env)
    proc = subprocess.run(cmd, cwd=cwd or ROOT, env=merged_env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    elapsed = time.perf_counter() - started
    output = (proc.stdout or "") + (proc.stderr or "")
    tail = _tail(output)
    if tail:
        print(tail)
    print("[构建] %s：%s（%.1fs）"
          % (title, "OK" if proc.returncode == 0 else "FAIL", elapsed))
    if proc.returncode != 0:
        raise BuildFailure(title, proc.returncode, elapsed)
    return elapsed, output


def _node_deps_stale() -> bool:
    marker = os.path.join(FRONTEND_DIR, "node_modules", ".package-lock.json")
    lock = os.path.join(FRONTEND_DIR, "package-lock.json")
    if not os.path.isdir(os.path.join(FRONTEND_DIR, "node_modules")):
        return True
    if not os.path.isfile(marker):
        return True
    return os.path.getmtime(marker) < os.path.getmtime(lock)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="一键构建：装依赖→测试→门禁→前端构建→导出论文")
    ap.add_argument("--gate", action="store_true",
                    help="全门禁模式（单测→跨文档→第10→第11→契约快照→前端 test+build）")
    ap.add_argument("--skip-deps", action="store_true", help="跳过依赖安装")
    ap.add_argument("--skip-frontend", action="store_true", help="跳过前端测试与构建")
    ap.add_argument("--skip-paper", action="store_true", help="跳过论文导出")
    ap.add_argument("--keep-going", action="store_true", help="失败后继续其余步骤")
    args = ap.parse_args(argv)

    if args.gate:
        # 门禁序列是固定口径：不装依赖、不导出论文、前端必须跑。
        if args.skip_frontend or args.skip_paper:
            print("[gate] --gate 模式下忽略 --skip-frontend／--skip-paper（门禁必须覆盖前端）。")
        args.skip_deps = True
        args.skip_frontend = False
        args.skip_paper = True

    timings = []
    failures = []

    def step(title, cmd, cwd=None, env=None):
        try:
            elapsed, output = run_step(title, cmd, cwd=cwd, env=env)
            timings.append((title, elapsed, "OK"))
            return output
        except BuildFailure as exc:
            timings.append((title, exc.elapsed, "FAIL"))
            failures.append(exc)
            if not args.keep_going:
                raise
            return ""

    total_started = time.perf_counter()
    print("=" * 78)
    print("一键构建（仓库根：%s）" % ROOT)
    print("Python：%s" % sys.version.split()[0])
    print("=" * 78)

    try:
        # ---------------------------------------------------------------- 1
        npm = None
        if not args.skip_frontend:
            node = _which("node")
            npm = _which("npm")
            print("Node：%s；npm：%s" % (node, npm))

        # ---------------------------------------------------------------- 2
        if not args.skip_deps:
            step("安装 Python 依赖",
                 [sys.executable, "-m", "pip", "install", "-r",
                  os.path.join(ROOT, "requirements.txt")])
            if npm:
                if _node_deps_stale():
                    step("安装前端依赖（npm ci）", [npm, "ci", "--no-audit", "--no-fund"],
                         cwd=FRONTEND_DIR)
                else:
                    print("\n[构建] 前端依赖已是最新（node_modules 与 package-lock 同步），跳过 npm ci")
        else:
            print("\n[构建] --skip-deps：跳过依赖安装")

        # ---------------------------------------------------------------- 3
        out = step("后端单元测试",
                   [sys.executable, "-m", "pytest", "交付物/03-代码/测试", "-q"])
        backend_counts = parse_pytest_counts(out)
        problem = backend_gate_error(backend_counts)
        if problem:
            raise BuildFailure(problem, 1)

        # ---------------------------------------------------------------- 4
        step("跨文档核验", [sys.executable, os.path.join(ROOT, "工具", "跨文档核验.py"),
                            "--strict-citations"])
        step("验收第10阶段", [sys.executable, os.path.join(ROOT, "工具", "验收第10阶段.py")])
        step("验收第11阶段", [sys.executable, os.path.join(ROOT, "工具", "验收第11阶段.py")])
        step("契约快照比对", [sys.executable, os.path.join(ROOT, "工具", "契约快照.py")])
        # **刻意不调用 验收第9阶段.py**（B5 会 --reset 重置六表）。

        # ---------------------------------------------------------------- 5
        if not args.skip_frontend:
            fe = {"CI": "1"}
            out = step("前端单元测试", [npm, "run", "test"], cwd=FRONTEND_DIR, env=fe)
            # Vitest 会先打印 `Test Files  5 passed (5)`、再打印 `Tests  81 passed (81)`，
            # 必须锚定 "Tests"，否则会把测试文件数误当成用例数。
            fe_counts = parse_vitest_counts(out)
            problem = frontend_gate_error(fe_counts)
            if problem:
                raise BuildFailure(problem, 1)
            step("前端构建", [npm, "run", "build"], cwd=FRONTEND_DIR, env=fe)
        else:
            print("\n[构建] --skip-frontend：跳过前端测试与构建")

        # ---------------------------------------------------------------- 6
        if not args.skip_paper:
            os.makedirs(BUILD_DIR, exist_ok=True)
            step("导出论文（不写 01-论文）",
                 [sys.executable, os.path.join(ROOT, "工具", "导出论文docx.py"),
                  "--out", PAPER_OUT])
            if not os.path.isfile(PAPER_OUT) or os.path.getsize(PAPER_OUT) <= 0:
                raise BuildFailure("导出论文（产物不存在或为空：%s）" % PAPER_OUT, 1)
            with open(PAPER_OUT, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            print("论文产物：%s（%d 字节，sha256=%s）"
                  % (PAPER_OUT, os.path.getsize(PAPER_OUT), digest[:16]))
        else:
            print("\n[构建] --skip-paper：跳过论文导出")

    except BuildFailure as exc:
        if exc not in failures:            # step() 内已登记过的不重复追加
            failures.append(exc)
    finally:
        total = time.perf_counter() - total_started
        print("\n" + "=" * 78)
        print("构建耗时汇总（总 %.1fs）" % total)
        print("=" * 78)
        for title, elapsed, status in timings:
            print("  %-28s %8.1fs  %s" % (title, elapsed, status))
        if failures:
            print("\n构建失败：%s" % "；".join(str(f) for f in failures))
            print("=" * 78)
            return failures[0].code or 1
        if args.gate:
            print("\n门禁通过：单测／跨文档核验／第10／第11／契约快照／前端 test＋build 全部 OK。")
        skipped = any((args.skip_deps, args.skip_frontend, args.skip_paper))
        if not args.gate:
            print("\n构建成功：所选步骤全部完成%s。"
                  % ("（跳过的步骤见上）" if skipped else ""))
        print("=" * 78)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
