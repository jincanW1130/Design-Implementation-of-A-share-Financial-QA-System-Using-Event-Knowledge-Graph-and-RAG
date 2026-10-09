# -*- coding: utf-8 -*-
"""审查 A 的只读复算驱动：把要跑的命令写成文件，避开控制台/argv 的 GBK 编码坑。
所有被调脚本一律只读。用法：python _run.py <case>
"""
import io, os, sys, subprocess, json, hashlib, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
OUT = os.path.join(ROOT, r"交付物/05-系统实现/智能问答系统\_审查工作底稿\A_文档与口径")


def run(name, cmd, cwd=ROOT, env=None):
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    e["PYTHONUTF8"] = "1"
    if env:
        e.update(env)
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, env=e)
    log = os.path.join(OUT, name + ".log")
    with open(log, "wb") as f:
        f.write(b"$ " + " ".join(cmd).encode("utf-8") + b"\n")
        f.write(b"EXIT=" + str(p.returncode).encode() + b"\n")
        f.write(b"--- STDOUT ---\n" + p.stdout + b"\n--- STDERR ---\n" + p.stderr)
    print("=" * 30, name, "EXIT=", p.returncode, "->", log)
    print(p.stdout.decode("utf-8", "replace")[-6000:])
    if p.stderr.strip():
        print("---STDERR---")
        print(p.stderr.decode("utf-8", "replace")[-3000:])
    return p.returncode, p.stdout.decode("utf-8", "replace")


if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else ""
    py = sys.executable
    if case == "crossdoc":
        run("crossdoc_strict", [py, r"工具\跨文档核验.py", "--strict-citations"])
    elif case == "acc8full":
        run("acc8_full", [py, r"工具\验收第8阶段.py"])
    elif case == "acc8static":
        run("acc8_static", [py, r"工具\验收第8阶段.py", "--profile", "static"])
    elif case == "acc8selftest":
        run("acc8_selftest", [py, r"工具\验收第8阶段.py", "--selftest"])
    else:
        print("unknown case:", case)
