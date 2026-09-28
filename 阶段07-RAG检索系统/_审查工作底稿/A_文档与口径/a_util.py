# -*- coding: utf-8 -*-
"""A 线共用检索工具 v2：只读项目树，支持文件与目录两种 root。"""
import os, re

ROOT = r"C:\Users\15129\Desktop\毕业设计"
SKIP_DIRS = {".git", "__pycache__", ".idea", "node_modules", ".venv", "venv"}

def iter_files(exts=None, roots=None):
    bases = roots if roots else [ROOT]
    for base in bases:
        b = base if os.path.isabs(base) else os.path.join(ROOT, base)
        if os.path.isfile(b):
            if not exts or b.lower().endswith(tuple(e.lower() for e in exts)):
                yield b
            continue
        for dirpath, dirnames, filenames in os.walk(b):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for f in sorted(filenames):
                if exts and not f.lower().endswith(tuple(e.lower() for e in exts)):
                    continue
                yield os.path.join(dirpath, f)

def grep(pattern, exts=(".md",), roots=None, regex=False, ctx=0, maxhits=None, width=500):
    rx = re.compile(pattern) if regex else None
    hits = 0
    for p in iter_files(exts, roots):
        try:
            lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
        except Exception as e:
            print("ERR", p, e); continue
        for i, l in enumerate(lines, 1):
            ok = rx.search(l) if rx else (pattern in l)
            if ok:
                rel = os.path.relpath(p, ROOT)
                if ctx:
                    for j in range(max(1, i-ctx), min(len(lines), i+ctx)+1):
                        mark = ">>" if j == i else "  "
                        print(f"{rel}:{j}:{mark} {lines[j-1][:width]}")
                    print("   " + "-"*40)
                else:
                    print(f"{rel}:{i}: {l[:width]}")
                hits += 1
                if maxhits and hits >= maxhits:
                    return

def show(path, a, b):
    p = path if os.path.isabs(path) else os.path.join(ROOT, path)
    lines = open(p, encoding="utf-8", errors="replace").read().split("\n")
    for i in range(a, min(b, len(lines)) + 1):
        print(f"{i}: {lines[i-1]}")
