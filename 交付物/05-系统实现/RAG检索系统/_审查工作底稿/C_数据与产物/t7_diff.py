# -*- coding: utf-8 -*-
"""C 线：T12 验收日志 vs 现场重跑输出的规范化比对"""
import io, re, difflib

T12 = r"C:\Users\15129\Desktop\毕业设计\交付物/05-系统实现/RAG检索系统\_工作底稿\_T12"
MINE = r"C:\Users\15129\AppData\Local\Temp\re7_C\logs"


def norm(path):
    s = io.open(path, encoding="utf-8", errors="replace").read()
    s = re.sub(r"stage7_accept_[a-z0-9_]+", "<MIRROR>", s)
    s = re.sub(r"\d+\.\d+s", "<T>s", s)
    s = re.sub(r"\d+\.\d{3}\s*秒", "<T>秒", s)
    s = re.sub(r"摘除凭据类变量 \d+ 个", "摘除凭据类变量 <N> 个", s)
    s = re.sub(r"文件 \d+ 个", "文件 <N> 个", s)
    s = re.sub(r"copied=\d+、skipped=\d+", "copied=<N>、skipped=<N>", s)
    return [l.rstrip() for l in s.split("\n") if l.strip()]


PAIRS = [
    ("验收第7阶段_full_stdout.txt", "t7_full_mine.txt"),
    ("验收第7阶段_static_stdout.txt", "t7_static_mine.txt"),
    ("验收第7阶段_keep-tmp_stdout.txt", "t7_full_mine.txt"),
]
for a, b in PAIRS:
    A = norm(T12 + "\\" + a)
    B = norm(MINE + "\\" + b)
    d = [l for l in difflib.unified_diff(A, B, lineterm="", n=0)
         if l.startswith(("+", "-")) and not l.startswith(("+++", "---"))]
    print("=" * 70)
    print("%s（记录 %d 行） vs %s（现场 %d 行）：差异行 %d" % (a, len(A), b, len(B), len(d)))
    for l in d[:40]:
        print("   ", l[:180])
