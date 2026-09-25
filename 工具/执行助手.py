# -*- coding: utf-8 -*-
"""执行助手 —— 把「执行指令时踩过的坑」固化成可复用原语。

来源：2026-09-25 的一次执行复盘。该复盘共列出 27 起失误（工具使用 12、判断与规格 12、
环境不确定 3），归成 6 类根因。**本模块只负责其中能机械修复的部分**；纯纪律条款
（改口径前 grep 依赖方、批量前小样本试跑、结论必须独立复现、守卫精度要校准）
见 README.md 的「执行纪律」一节，那几条没法写成代码。

本文件不属于交付物，不参与文档编号。

三条最贵的坑，也是本模块存在的理由：

1. **用 PowerShell 解析 UTF-8 数据**：默认按 GBK 解码；更糟的是 ``ConvertFrom-Json``
   失败时给出的是**看起来成功的结果**——实测一份 99 篇文档的 JSONL 被算成
   ``doc_id set identical = True (count 1)``，即"只有 1 条记录"却报告"一致"。
   → 数据一律交给 Python：``read_jsonl`` / ``read_text``。
2. **在 shell 里写代码**：要过 PowerShell 与 Python 两层解释器，引号转义规则不同，
   实测三次全中（``python -c`` 的 ``\\"`` 被吃掉、Python 字符串里嵌 ASCII 双引号、
   ``git commit -m`` 的多行消息被拆成参数）。→ 逻辑一律落成 ``.py`` 文件；
   git 提交用 ``git_commit``（走 ``-F 文件``）。
3. **扫描器给出假阴性**：实测 ``Select-String -SimpleMatch -AllMatches`` 对一份
   **确实存在**的词返回 0 命中，差点被当成"未出现该词"写进结论。→ ``scan()``
   强制要求一个**正对照**字符串；对照不命中就直接抛异常，因为那说明扫描器坏了，
   而不是"没找到"。

命令行自检：``python 工具\\执行助手.py selftest``
"""

from __future__ import annotations

import glob as _glob
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time

__all__ = [
    "setup", "run", "read_text", "write_text", "read_jsonl", "write_jsonl",
    "git", "git_commit", "git_push", "scan", "sha16", "ControlFailed",
]

ROOT_DEFAULT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


class ControlFailed(RuntimeError):
    """正对照未命中——扫描器坏了，不是"没找到"。"""


# --------------------------------------------------------------------------
# 编码
# --------------------------------------------------------------------------
def setup():
    """把本进程的 stdout/stderr 改成 UTF-8，返回模块自身以便链式调用。

    起因：控制台默认 GBK，中文输出全是乱码（实测 ``阶段05-数据准备`` 打成
    ``�׶�05-����׼��``），误判过好几次。
    """
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    return sys.modules[__name__]


# --------------------------------------------------------------------------
# 跑外部命令
# --------------------------------------------------------------------------
def run(cmd, cwd=None, tail=40, timeout=1800):
    """跑一条外部命令，按 UTF-8 解码，只回**尾部 tail 行**。

    完整输出落临时文件，返回值里带上路径——需要更多时按需读，不要一次全灌进上下文。
    起因：一次没加收口的输出回了 120 KB 乱码，直接冲掉大段上下文。
    """
    if isinstance(cmd, (list, tuple)):
        args = list(cmd)
    else:
        args = cmd
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout,
                       shell=isinstance(cmd, str))
    out = (p.stdout or "") + (("\n[stderr]\n" + p.stderr) if p.stderr else "")
    lines = out.splitlines()
    body = "\n".join(lines[-tail:]) if tail and len(lines) > tail else out
    note = ""
    if tail and len(lines) > tail:
        fh = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False,
                                         encoding="utf-8", newline="\n")
        fh.write(out)
        fh.close()
        note = "\n…（共 %d 行，已截尾显示 %d 行；完整输出：%s）" % (len(lines), tail, fh.name)
    return p.returncode, body + note


# --------------------------------------------------------------------------
# 文件读写（一律 UTF-8 + LF）
# --------------------------------------------------------------------------
def read_text(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def write_text(path, text, newline="\n"):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)


def read_jsonl(path):
    rows = []
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def sha16(text):
    """正文指纹：UTF-8 编码后 SHA-256 的前 16 位十六进制。"""
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()[:16]


# --------------------------------------------------------------------------
# git
# --------------------------------------------------------------------------
def git(*args, cwd=None):
    """git 包装：固定 ``-c core.quotepath=false``。

    起因：不加这一项时中文路径会被输出成八进制转义（``"\\346\\226\\207..."``），
    下游 ``Test-Path`` 直接报 ``Illegal characters in path``。
    另外：git 会把**正常输出写到 stderr**，所以调用方不要用
    ``$ErrorActionPreference='Stop'`` 把它当错误中断全脚本。
    """
    return run(["git", "-c", "core.quotepath=false"] + list(args), cwd=cwd, tail=200)


def git_commit(message, cwd=None, add_all=True, paths=None):
    """提交：消息先写临时文件，再 ``git commit -F``。

    起因：``git commit -m $msg`` 在 PowerShell 里遇到多行或含引号的消息会被拆成
    多个参数，实测报 ``error: pathspec 'YYYY-MM-DD' did not match any file(s) known to git``。
    """
    if add_all:
        c, o = git("add", "-A", cwd=cwd)
        if c != 0:
            return c, "git add 失败：\n" + o
    elif paths:
        c, o = git("add", "--", *paths, cwd=cwd)
        if c != 0:
            return c, "git add 失败：\n" + o
    fh = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                     encoding="utf-8", newline="\n")
    fh.write(message if message.endswith("\n") else message + "\n")
    fh.close()
    try:
        return git("commit", "-F", fh.name, cwd=cwd)
    finally:
        try:
            os.remove(fh.name)
        except OSError:
            pass


def git_push(branch="main", cwd=None, polls=12, wait=25, probe="https://github.com/"):
    """推送：**先探测连通再推**，不通就等，不要盲目重试。

    起因：本机到 GitHub 的连接会成片被重置（``Recv failure: Connection was reset`` /
    ``Failed to connect to github.com:443 after 21077 ms``）。盲试时每次都要白等 21 秒，
    实测两轮推送合计失败 11 次才成功；改成"先探测、通了再推"后 4 轮内成功。
    """
    import urllib.request
    last = ""
    for i in range(1, polls + 1):
        ok = False
        try:
            req = urllib.request.Request(probe, method="HEAD")
            with urllib.request.urlopen(req, timeout=15):
                ok = True
        except Exception:
            ok = False
        if ok:
            c, o = git("push", "origin", branch, cwd=cwd)
            if c == 0:
                return 0, "第 %d 轮探测连通后推送成功\n%s" % (i, o)
            last = o
        time.sleep(wait)
    return 1, "连续 %d 轮未能推送成功；本地提交完好，稍后重试即可。最后一次输出：\n%s" % (polls, last)


# --------------------------------------------------------------------------
# 带正对照的扫描
# --------------------------------------------------------------------------
def scan(pattern, paths, control=None, flags=re.I, exts=None):
    """在给定路径里做正则扫描，**强制正对照**。

    ``control`` 必须是一个你**确信语料里一定存在**的字符串。若 control 命中 0 次，
    抛 :class:`ControlFailed`——因为那说明扫描器坏了，而不是"没找到"。
    这是本模块里最重要的一个函数：假阴性比假阳性危险得多，它长得像"干净结果"。

    起因：实测 ``Select-String -SimpleMatch -AllMatches`` 统计一份**确实有**该词的文档
    返回 0 命中，差点被当成"未出现禁用词"写进结论。

    返回 ``[(文件, 行号, 行内容), ...]``；``control_hits`` 供调用方打印留痕。
    """
    files = []
    for p in paths:
        if os.path.isdir(p):
            for f in sorted(_glob.glob(os.path.join(p, "**", "*"), recursive=True)):
                if os.path.isfile(f) and (exts is None or os.path.splitext(f)[1] in exts):
                    files.append(f)
        elif os.path.isfile(p):
            files.append(p)

    rx = re.compile(pattern, flags)
    control_hits = 0
    hits = []
    for f in files:
        try:
            text = read_text(f)
        except (UnicodeDecodeError, OSError):
            continue
        if control:
            control_hits += text.count(control)
        for i, line in enumerate(text.split("\n"), 1):
            if rx.search(line):
                hits.append((f, i, line.strip()))

    if control is not None and control_hits == 0:
        raise ControlFailed(
            "正对照 %r 在 %d 个文件里 0 命中——扫描器或语料路径有问题，"
            "本次扫描结果（%d 处命中）不可采信。" % (control, len(files), len(hits)))
    scan.control_hits = control_hits
    return hits


scan.control_hits = 0


# --------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------
def selftest():
    setup()
    print("=" * 74)
    print("执行助手自检")
    print("=" * 74)
    ok = True

    # 1 UTF-8 往返
    tmp = tempfile.mkdtemp(prefix="exec_helper_")
    p = os.path.join(tmp, "中文目录", "示例.jsonl")
    rows = [{"doc_id": 1001, "标题": "平安银行关于…的公告"}, {"doc_id": 1002, "标题": "含全角标点，与｜竖线"}]
    write_jsonl(p, rows)
    back = read_jsonl(p)
    same = back == rows
    ok &= same
    print("  1) UTF-8 JSONL 往返（含中文路径、全角标点、竖线）：%s" % ("通过" if same else "失败"))

    # 2 run 收口
    code, out = run([sys.executable, "-c",
                     "import sys\nfor i in range(500): print('line %d' % i)"], tail=5)
    lines = out.splitlines()
    capped = code == 0 and len(lines) <= 8 and "完整输出" in out
    ok &= capped
    print("  2) run() 输出收口：%s（%d 行，末尾 5 行 + 落盘提示）" % ("通过" if capped else "失败", len(lines)))

    # 3 正对照
    write_text(os.path.join(tmp, "语料.md"), "向量索引与向量检索组件\nFORSETCONTROL 标记\n")
    hits = scan("向量索引", [tmp], control="FORSETCONTROL")
    c_ok = len(hits) == 1 and scan.control_hits == 1
    ok &= c_ok
    print("  3) scan() 正对照命中：%s（命中 %d 处，对照 %d 次）"
          % ("通过" if c_ok else "失败", len(hits), scan.control_hits))

    # 4 正对照失效时必须抛异常（模拟"扫描器坏了"）
    raised = False
    try:
        scan("向量索引", [tmp], control="这个串一定不存在_zzz")
    except ControlFailed:
        raised = True
    ok &= raised
    print("  4) scan() 对照失效时抛 ControlFailed：%s" % ("通过" if raised else "失败"))

    # 5 sha16 稳定
    s = sha16("abc") == sha16("abc".encode("utf-8")) and len(sha16("abc")) == 16
    ok &= s
    print("  5) sha16() 稳定且 16 位：%s" % ("通过" if s else "失败"))

    print()
    print("结论：%s" % ("全部通过" if ok else "存在失败项"))
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(selftest())
    setup()
    print(__doc__.strip().splitlines()[0])
    print("子命令：selftest")
