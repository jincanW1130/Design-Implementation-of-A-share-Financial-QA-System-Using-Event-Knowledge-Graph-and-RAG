# -*- coding: utf-8 -*-
r"""跑并落盘：执行一条命令，把完整 stdout／stderr／退出码原样写成 UTF-8 日志。

本工具只做「执行 + 落盘」，不解析、不改写、不截断被执行的输出；
控制台只打印退出码与日志路径，避免冲掉会话上下文。

用法（在仓库根目录执行）：

    python 阶段06-事件抽取与知识图谱\_整改_第一步\_工具\跑并落盘.py <日志路径> \
        [--cwd <目录>] [--env KEY=VALUE ...] [--unset KEY ...] -- <命令> [参数 ...]
"""
import os
import subprocess
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(argv):
    if "--" not in argv:
        print(__doc__)
        return 2
    split = argv.index("--")
    head, command = argv[:split], argv[split + 1:]
    if not head or not command:
        print(__doc__)
        return 2
    log_path = head[0]
    cwd = None
    env_over = {}
    env_unset = []
    i = 1
    while i < len(head):
        if head[i] == "--cwd":
            cwd = head[i + 1]
            i += 2
        elif head[i] == "--env":
            key, _, value = head[i + 1].partition("=")
            env_over[key] = value
            i += 2
        elif head[i] == "--unset":
            env_unset.append(head[i + 1])
            i += 2
        else:
            print("未知参数：%s" % head[i])
            return 2
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    while not os.path.exists(os.path.join(root, ".git")) and os.path.dirname(root) != root:
        root = os.path.dirname(root)
    cwd = os.path.abspath(cwd or root)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    for key in env_unset:
        env.pop(key, None)
    env.update(env_over)

    started = time.time()
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    seconds = round(time.time() - started, 3)

    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    parts = ["$ %s" % " ".join(command),
             "cwd: %s" % cwd,
             "env_overrides: %s" % (env_over or {}),
             "env_unset: %s" % env_unset,
             "exit_code: %d" % proc.returncode,
             "wall_clock_seconds: %.3f" % seconds,
             "", "--- stdout ---", proc.stdout or "", "--- stderr ---", proc.stderr or ""]
    with open(log_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(parts))
    stdout_lines = (proc.stdout or "").splitlines()
    print("exit_code=%d  seconds=%.3f" % (proc.returncode, seconds))
    print("日志：%s（stdout %d 行、stderr %d 行）"
          % (log_path, len(stdout_lines), len((proc.stderr or "").splitlines())))
    for line in stdout_lines[-6:]:
        print("  | %s" % line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
