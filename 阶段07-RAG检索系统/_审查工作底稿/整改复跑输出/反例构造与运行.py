# -*- coding: utf-8 -*-
"""在临时硬链接副本上复现 B-32／B-33 与 g 越界三个反例；工作区只读。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUTDIR = Path(__file__).resolve().parent
EXCLUDE_PARTS = {".git", ".idea", "__pycache__", "_scratch_cnki"}


def clone_tree(prefix: str) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix=prefix))
    for base, dirs, files in os.walk(ROOT):
        base_path = Path(base)
        rel = base_path.relative_to(ROOT)
        if any(part in EXCLUDE_PARTS for part in rel.parts):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d not in EXCLUDE_PARTS]
        target_dir = tmp / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            if name.endswith((".pyc", ".pyo")):
                continue
            src = base_path / name
            dst = target_dir / name
            try:
                os.link(src, dst)
            except OSError:
                shutil.copy2(src, dst)
    return tmp


def run_case(name: str, root: Path, args):
    proc = subprocess.run([sys.executable, "-X", "utf8", str(root / "工具" / "验收第7阶段.py")]
                          + list(args),
                          cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    text = "RETURN_CODE=%d\n\n" % proc.returncode + (proc.stdout or "") + (proc.stderr or "")
    path = OUTDIR / name
    path.write_text(text, encoding="utf-8", newline="\n")
    print("%s -> %s（RETURN_CODE=%d）" % (name, path, proc.returncode))


def main() -> int:
    cases = []
    try:
        # 反例①：链上 metrics.py 退出非 0。
        case1 = clone_tree("re7_case_metrics_")
        original_metrics = (ROOT / "代码" / "检索" / "metrics.py").read_text(encoding="utf-8")
        marker = 'if __name__ == "__main__":\n    sys.exit(main())\n'
        if marker not in original_metrics:
            raise RuntimeError("反例①的 metrics 入口标记未命中")
        (case1 / "代码" / "检索" / "metrics.py").unlink()
        (case1 / "代码" / "检索" / "metrics.py").write_text(
            original_metrics.replace(
                marker,
                'if __name__ == "__main__":\n'
                '    print("反例①：metrics 强制退出 3")\n'
                '    sys.exit(3)\n'),
            encoding="utf-8", newline="\n")
        cases.append(("反例1_metrics非零.txt", case1, []))

        # 反例②：镜像保留旧产物，链上不重跑；新鲜度前提应判环境／链上失败。
        case2 = clone_tree("re7_case_stale_")
        gate = case2 / "工具" / "验收第7阶段.py"
        source = gate.read_text(encoding="utf-8")
        old = '        REPLAY["freshness"] = drop_mirror_outputs(tmp)'
        new = (
            '        REPLAY["freshness"] = {}\n'
            '        _out_dir = os.path.join(tmp, "阶段07-RAG检索系统", "检索产出")\n'
            '        for _name in MIRROR_OUTPUTS:\n'
            '            _path = os.path.join(_out_dir, _name)\n'
            '            REPLAY["freshness"][_name] = {\n'
            '                "exists_before_drop": os.path.isfile(_path),\n'
            '                "absent_after_drop": False,\n'
            '                "exists_after_run": os.path.isfile(_path),\n'
            '            }\n'
            '        raise ChainFailure("反例②：镜像保留旧产物且链上未重跑")'
        )
        if old not in source:
            raise RuntimeError("反例②注入点未命中")
        gate.unlink()
        gate.write_text(source.replace(old, new, 1), encoding="utf-8", newline="\n")
        cases.append(("反例2_旧产物不重跑.txt", case2, []))

        # 反例③：config 的 g 越界（K=10、g=11）；static 即可由 V1 拒绝。
        case3 = clone_tree("re7_case_g_")
        cfg = case3 / "代码" / "检索" / "config.py"
        source = cfg.read_text(encoding="utf-8")
        if '"graph_retention_share": 2,' not in source:
            raise RuntimeError("反例③注入点未命中")
        cfg.unlink()
        cfg.write_text(source.replace('"graph_retention_share": 2,',
                                      '"graph_retention_share": 11,', 1),
                       encoding="utf-8", newline="\n")
        cases.append(("反例3_g越界.txt", case3, ["--profile", "static"]))

        for name, root, args in cases:
            run_case(name, root, args)
    finally:
        for _name, root, _args in cases:
            shutil.rmtree(root, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
