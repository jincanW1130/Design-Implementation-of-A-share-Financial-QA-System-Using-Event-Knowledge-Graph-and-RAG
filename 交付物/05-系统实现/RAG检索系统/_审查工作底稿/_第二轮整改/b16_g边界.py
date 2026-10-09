# -*- coding: utf-8 -*-
"""B-16 构造用例：g 的取值域 `1 ≤ g ≤ K` —— 旧行为（静默夹取／接受 0）vs 新行为（抛错）。

旧行为取自 **git HEAD（74b78ab）的 `代码\\检索\\pipeline.py`**（本轮改动未提交，HEAD 即修订前基线），
在临时目录里连同 config／graph_query／vector_search 一起加载为独立模块 `pipeline_old`；新行为取自
当前工作区的 `代码\\检索\\pipeline.py`。两边都：① 直接调库入口；② 走 CLI 的参数解析路径；③ 试
g=0 的显式退化通道。

只读：不写工作区（临时目录用后删）。
"""
from __future__ import annotations

import argparse
import importlib.util
import io
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


def load_old_pipeline(tmp):
    """把 HEAD 版 pipeline.py 与工作区同目录的 config／graph_query／vector_search 放进临时目录后加载。"""
    for name in ("config.py", "graph_query.py", "vector_search.py", "metrics.py"):
        shutil.copy2(os.path.join(CODE, name), os.path.join(tmp, name))
    proc = subprocess.run(["git", "show", "HEAD:交付物/03-代码/检索/pipeline.py"], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise SystemExit("取 HEAD 版 pipeline.py 失败：%s" % (proc.stderr or ""))
    with open(os.path.join(tmp, "pipeline.py"), "w", encoding="utf-8", newline="\n") as f:
        f.write(proc.stdout)
    spec = importlib.util.spec_from_file_location("pipeline_old", os.path.join(tmp, "pipeline.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pipeline_old"] = mod
    spec.loader.exec_module(mod)
    # 旧模块已加载完毕：把它带进来的临时目录模块撤出 sys.modules，免得后面 `import pipeline`
    # （新实现）拿到临时目录里的 config 而被同目录守卫拒绝。旧模块自身的全局引用不受影响。
    keep = {name: sys.modules.pop(name) for name in
            ("config", "graph_query", "vector_search", "metrics") if name in sys.modules}
    mod.__dict__["_b16_kept"] = keep
    if tmp in sys.path:
        sys.path.remove(tmp)
    return mod


def stub_runner(mod):
    """不加载任何输入的 PipelineRunner 替身：run() 里的逐题函数换成桩，只看边界校验。"""
    inst = object.__new__(mod.PipelineRunner)
    inst.verbose = False
    inst.graph = None
    inst.chunks = {}
    inst.documents = {}
    inst.searcher = object()
    inst.vector_cache = {}
    inst.graph_cache = {}
    inst.full_pool_cache = {}
    inst._case_questions = []
    mod.run_question = lambda *a, **kw: {"chunk_id": 1, "qid": "STUB"}
    return inst


SW = {"group": "C", "switches": {"graph_depth": 2, "time_filter": False, "evidence_sort": False}}


def probe(mod, label, has_legacy_channel):
    print("\n" + "-" * 78)
    print("【%s】" % label)
    print("-" * 78)
    # ① 库函数：分层保留键与第二层名额（纯函数，不读输入）
    recs = [{"chunk_id": 101 + i, "vector_rank": i + 1, "first_path_key": (1, i)}
            for i in range(3)]
    recs += [{"chunk_id": 201 + i, "vector_rank": None, "first_path_key": (2, i)}
             for i in range(3)]
    for g in (0, 11, -1):
        try:
            plan = mod.plan_graph_layer(recs, 10, g)
            cut = mod.plan_graph_layer(recs, 10, g)["cut"]
            order = [r["chunk_id"] for r in sorted(recs, key=mod.retention_key(10, g,
                                                                            plan["layer2_positions"]))]
            print("  evidence_priority_key/plan_graph_layer：g=%-3d → 未抛错；cut=K−g=%d、"
                  "第二层名额=%d，排序前 5 个=%s" % (g, cut, len(plan["layer2_ids"]), order[:5]))
        except Exception as exc:                              # noqa: BLE001
            print("  evidence_priority_key/plan_graph_layer：g=%-3d → 抛错 %s：%s"
                  % (g, type(exc).__name__, str(exc).split("\n")[0][:110]))
    # ② 库入口 PipelineRunner.run
    for g in (0, 11, -1):
        inst = stub_runner(mod)
        try:
            inst.run([{"qid": "Q"}], SW, 20, 10, 3600, g)
            print("  PipelineRunner.run(..., g=%-3d) → 未抛错（静默接受）" % g)
        except Exception as exc:                              # noqa: BLE001
            print("  PipelineRunner.run(..., g=%-3d) → 抛错 %s：%s"
                  % (g, type(exc).__name__, str(exc).split("\n")[0][:110]))
    # ③ CLI 的参数解析路径（resolve_k_n_budget）
    for g in (0, 11, -1):
        args = argparse.Namespace(k=10, n=20, budget=3600, graph_share=g,
                                  legacy_g0_degeneration=False)
        try:
            out = mod.resolve_k_n_budget(args)
            print("  CLI resolve_k_n_budget(--graph-share %-3d) → 未抛错：g=%d"
                  % (g, out["g"]))
        except SystemExit as exc:
            print("  CLI resolve_k_n_budget(--graph-share %-3d) → SystemExit：%s"
                  % (g, str(exc).split("\n")[0][:110]))
        except Exception as exc:                              # noqa: BLE001
            print("  CLI resolve_k_n_budget(--graph-share %-3d) → 抛错 %s：%s"
                  % (g, type(exc).__name__, str(exc).split("\n")[0][:110]))
    # ④ 显式退化通道（新实现才有）
    if has_legacy_channel:
        inst = stub_runner(mod)
        got = inst.run_legacy_g0([{"qid": "Q"}], SW, 20, 10, 3600)
        print("  显式退化通道 run_legacy_g0(...) → 未抛错：g=%s、题数=%d"
              % (got["g"], len(got["records"])))


def main():
    tmp = tempfile.mkdtemp(prefix="b16_old_")
    try:
        old = load_old_pipeline(tmp)
        sys.path.insert(0, CODE)
        import pipeline as new
        print("=" * 78)
        print("B-16 g 边界对照：合法域 1 ≤ g ≤ K（g=0 只走显式退化通道）")
        print("旧行为 = git HEAD(74b78ab) 的 代码\\检索\\pipeline.py（未改一字）")
        print("新行为 = 当前工作区的 代码\\检索\\pipeline.py（config.check_graph_share 显式校验）")
        print("=" * 78)
        probe(old, "修前（HEAD 版）：静默夹取／接受 g=0", False)
        probe(new, "修后（本轮）：越界即抛错", True)
        print("\n" + "-" * 78)
        print("真命令行（新实现）：")
        for argv in (["--graph-share", "0"], ["--graph-share", "11"], ["--graph-share", "-1"]):
            proc = subprocess.run([sys.executable, os.path.join(CODE, "pipeline.py")] + argv
                                  + ["--limit", "1", "--quiet"], cwd=ROOT, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace")
            tail = [l for l in (proc.stdout or "").split("\n") if l.strip()][-1:] \
                + [l for l in (proc.stderr or "").split("\n") if l.strip()][-1:]
            print("  python pipeline.py %s → 退出码 %d；%s"
                  % (" ".join(argv), proc.returncode, " / ".join(x.strip()[:120] for x in tail)))
        print("=" * 78)
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
