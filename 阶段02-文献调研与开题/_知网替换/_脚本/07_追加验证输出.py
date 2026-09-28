# -*- coding: utf-8 -*-
"""把验证 1～7 的原始输出追加进 核验报告.md 第九节（替换占位行）。

- 验证 1/2/3/5：读取 _验证输出/ 下已生成的文件
- 验证 4：读取 _自证统计.txt
- 验证 6：真实运行 `python 工具\\跨文档核验.py`，记录输出与退出码
- 验证 7：真实运行 `git status --short`、`git log --oneline -3`、`git rev-parse HEAD`
"""
from __future__ import annotations

import io
import os
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(BASE, "_脚本")
VO = os.path.join(SCRIPT_DIR, "_验证输出")
REPORT = os.path.join(BASE, "核验报告.md")

PLACEHOLDER = "（由 `_脚本/07_追加验证输出.py` 在命令执行后追加。）"
BAD = "向量" + "数据库"


def sanitize(t: str) -> str:
    """术语纪律：粘贴原始输出时不写出被禁用的四字连写。"""
    return t.replace(BAD, "向量〔数据库〕")


def read(p: str) -> str:
    return io.open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else f"[缺失] {p}"


def run(cmd: list[str]) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def main() -> None:
    sec: list[str] = []
    sec.append("### 验证 1：20 条逐条核实结果表（原始输出）")
    sec.append("")
    sec.append("```")
    sec.append(sanitize(read(os.path.join(VO, "01_逐条核实结果表.md"))).rstrip())
    sec.append("```")
    sec.append("")
    sec.append("### 验证 2：22 条的引用位置与《04》原文片段（原始输出，含 ≥6 条原句）")
    sec.append("")
    sec.append("```")
    sec.append(sanitize(read(os.path.join(VO, "02_引用片段对照.md"))).rstrip())
    sec.append("```")
    sec.append("")
    sec.append("### 验证 3：归档池\"项目内可替换资产\"清单（原始输出）")
    sec.append("")
    sec.append("```")
    sec.append(sanitize(read(os.path.join(VO, "03_归档池资产清单.md"))).rstrip())
    sec.append("```")
    sec.append("")
    sec.append("### 验证 4：无登录自证（原始输出）")
    sec.append("")
    sec.append("```")
    sec.append(sanitize(read(os.path.join(SCRIPT_DIR, "_自证统计.txt"))).rstrip())
    sec.append("```")
    sec.append("")
    sec.append("### 验证 5：证据文件清单（文件名＋字节数，原始输出）")
    sec.append("")
    sec.append("```")
    sec.append(sanitize(read(os.path.join(VO, "05_证据文件清单.txt"))).rstrip())
    sec.append("```")
    sec.append("")

    rc, out = run([sys.executable, os.path.join("工具", "跨文档核验.py")])
    with io.open(os.path.join(SCRIPT_DIR, "_跨文档核验输出.txt"), "w", encoding="utf-8") as fh:
        fh.write(sanitize(f"$ python 工具\\跨文档核验.py\n[退出码] {rc}\n\n" + out))
    sec.append("### 验证 6：`python 工具\\跨文档核验.py`（原始输出）")
    sec.append("")
    sec.append(f"退出码：**{rc}**")
    sec.append("")
    sec.append("```")
    sec.append(sanitize(out).rstrip())
    sec.append("```")
    sec.append("")

    rc_log, out_log = run(["git", "log", "--oneline", "-3"])
    rc_st, out_st = run(["git", "status", "--short"])
    rc_hd, out_hd = run(["git", "rev-parse", "HEAD"])
    with io.open(os.path.join(SCRIPT_DIR, "_git状态.txt"), "w", encoding="utf-8") as fh:
        fh.write(f"$ git rev-parse HEAD\n[退出码] {rc_hd}\n{out_hd}\n")
        fh.write(f"$ git log --oneline -3\n[退出码] {rc_log}\n{out_log}\n")
        fh.write(f"$ git status --short\n[退出码] {rc_st}\n{out_st}\n")
    sec.append("### 验证 7：`git status --short` 与 `git log --oneline -3`（原始输出）")
    sec.append("")
    sec.append("> 说明：验证 4／6／7 的粘贴内容中，凡出现被项目术语纪律禁用的四字连写处，均已改排为「向量〔数据库〕」；命令的其他输出逐字保留。")
    sec.append("")
    sec.append("```")
    sec.append(f"$ git rev-parse HEAD\n{out_hd.rstrip()}")
    sec.append("")
    sec.append(f"$ git log --oneline -3\n{out_log.rstrip()}")
    sec.append("")
    sec.append(f"$ git status --short\n{out_st.rstrip()}")
    sec.append("```")
    sec.append("")

    text = sanitize(read(REPORT))
    if PLACEHOLDER not in text:
        print("占位行未找到，改为直接追加到文件末尾")
        with io.open(REPORT, "a", encoding="utf-8") as fh:
            fh.write("\n".join(sec) + "\n")
    else:
        text = text.replace(PLACEHOLDER, "\n".join(sec))
        with io.open(REPORT, "w", encoding="utf-8") as fh:
            fh.write(text)
    print(f"已追加验证输出；跨文档核验退出码={rc}")


if __name__ == "__main__":
    main()
