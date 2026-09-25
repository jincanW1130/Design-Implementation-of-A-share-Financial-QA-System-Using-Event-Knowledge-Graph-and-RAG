# -*- coding: utf-8 -*-
"""第 5 阶段数据管线入口脚本。

按《12》第九节 的 T1→T8 顺序串起各环节，每个环节作为**独立子进程**执行：

    fetch.py -> dedup.py -> clean.py -> chunk.py -> embed.py -> check.py

透传 `--profile` / `--dir` / `--force`；任一环节退出码非 0 立即停止（不进入下一环节），
最后打印每个环节的退出码与耗时汇总表，并以其退出码作为本脚本的退出码。

纪律：
  * 本脚本不自己实现任何环节逻辑，只做编排；
  * 不写数据集以外的路径；正式封版用 `--profile v1`，`--dir` 仅供自测；
  * 术语：FAISS 在全部输出里称"向量索引／向量检索组件"。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

# 控制台为 GBK，必须重设编码后再输出中文。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# (阶段名, 脚本文件名, 中文说明)
STAGES = [
    ("fetch", "fetch.py", "T1-T3 采集与原始数据落盘"),
    ("dedup", "dedup.py", "T4a 文本级去重"),
    ("clean", "clean.py", "T4b 清洗与结构化"),
    ("chunk", "chunk.py", "T5 切分"),
    ("embed", "embed.py", "T6 向量化与三级映射"),
    ("check", "check.py", "T8 一致性检查"),
]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="第 5 阶段数据管线入口：fetch -> ... -> check")
    p.add_argument("--profile", choices=["v1", "pilot"], default="v1",
                   help="v1（默认）写正式数据集目录；pilot 写 _试跑\\")
    p.add_argument("--dir", default=None,
                   help="仅供自测：覆盖数据集根目录（正式封版不得使用）")
    p.add_argument("--force", action="store_true",
                   help="忽略已完成标记，强制重跑各环节")
    p.add_argument("--only", default=None,
                   help="仅运行指定环节及其之后（环节名，如 chunk）——调试用，不改变正式口径")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    root = os.path.abspath(args.dir) if args.dir else config.dataset_dir(args.profile)

    stages = STAGES
    if args.only:
        names = [s[0] for s in STAGES]
        if args.only not in names:
            print("[run_all] 失败：--only 只能是 %s 之一" % "/".join(names))
            return 2
        stages = STAGES[names.index(args.only):]

    print("=" * 78)
    print("[run_all] 第 5 阶段数据管线  profile=%s" % args.profile)
    print("[run_all] 数据集根目录：%s" % root)
    if args.dir:
        print("[run_all] 注意：--dir 仅供自测，不产出正式交付物")
    print("[run_all] 环节：%s" % " -> ".join(s[0] for s in stages))
    print("=" * 78)

    results = []          # (阶段名, 脚本, 退出码, 耗时, 状态)
    failed_stage = None
    t_pipeline = time.time()

    for name, script, desc in stages:
        path = os.path.join(HERE, script)
        if not os.path.isfile(path):
            print("\n[run_all] 失败：找不到环节脚本 %s（%s）" % (path, desc))
            results.append((name, script, 127, 0.0, "脚本缺失"))
            failed_stage = (name, 127)
            break

        cmd = [sys.executable, path, "--profile", args.profile]
        if args.dir:
            cmd += ["--dir", args.dir]
        if args.force:
            cmd += ["--force"]

        print("\n" + "-" * 78)
        print("[run_all] >>> %s（%s）" % (name, desc))
        print("[run_all]     %s" % " ".join(cmd))
        print("-" * 78)

        t0 = time.time()
        try:
            # 不捕获输出：子进程直接继承控制台，中文与进度实时可见。
            proc = subprocess.run(cmd, cwd=os.getcwd())
            code = proc.returncode
        except Exception as exc:                     # 子进程根本起不来
            print("[run_all] 环节 %s 启动失败：%s: %s" % (name, type(ex).__name__, exc))
            code = 126
        elapsed = time.time() - t0

        if code == 0:
            results.append((name, script, code, elapsed, "成功"))
            print("[run_all] <<< %s 完成，退出码 0，耗时 %.2fs" % (name, elapsed))
        else:
            results.append((name, script, code, elapsed, "失败"))
            print("[run_all] <<< %s 失败，退出码 %d，耗时 %.2fs——按序停止，不进入后续环节"
                  % (name, code, elapsed))
            failed_stage = (name, code)
            break

    total = time.time() - t_pipeline

    print("\n" + "=" * 78)
    print("[run_all] 各环节汇总（profile=%s）" % args.profile)
    print("=" * 78)
    header = "%-8s %-12s %-24s %8s %10s  %s" % ("环节", "脚本", "说明", "退出码", "耗时(秒)", "状态")
    print(header)
    print("-" * 78)
    desc_of = {s[0]: s[2] for s in STAGES}
    for name, script, code, elapsed, status in results:
        print("%-8s %-12s %-24s %8d %10.2f  %s"
              % (name, script, desc_of.get(name, ""), code, elapsed, status))
    print("-" * 78)
    if failed_stage is None:
        print("[run_all] 全部 %d 个环节成功，管线总耗时 %.2fs" % (len(results), total))
        print("[run_all] 回收：数据集目录 %s" % root)
        return 0
    print("[run_all] 管线在 %s 环节中断（退出码 %d），共执行 %d/%d 个环节，总耗时 %.2fs"
          % (failed_stage[0], failed_stage[1], len(results), len(STAGES), total))
    return failed_stage[1]


if __name__ == "__main__":
    sys.exit(main())
