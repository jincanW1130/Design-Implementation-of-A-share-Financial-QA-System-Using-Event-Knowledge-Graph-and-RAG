# -*- coding: utf-8 -*-
"""独立自建镜像（不复用门禁的 build_mirror）：把代码 + 11 个输入 + 题集 + 5 个产出
复制到 re7_B/mirror，供对抗实验在其中运行。工作区只读。"""
import io
import os
import shutil
import sys

WS = r"C:\Users\15129\Desktop\毕业设计"
MIR = r"C:\Users\15129\AppData\Local\Temp\re7_B\mirror"
sys.path.insert(0, os.path.join(WS, "交付物/03-代码", "检索"))
import config  # noqa: E402

QS = os.path.join(WS, "交付物/05-系统实现/RAG检索系统", "预实验问题集")
OUT = os.path.join(WS, "交付物/05-系统实现/RAG检索系统", "检索产出")
MIRROR_OUTPUTS = ["input_manifest.json", "pre_experiment_matrix.jsonl", "k_selection.json",
                  "per_question_trace.jsonl", "metrics_pre.jsonl"]

if os.path.isdir(MIR):
    shutil.rmtree(MIR)

items = []
for name in sorted(os.listdir(os.path.join(WS, "交付物/03-代码", "检索"))):
    if name.endswith(".py"):
        items.append((os.path.join(WS, "交付物/03-代码", "检索", name), os.path.join("交付物/03-代码", "检索", name)))
for _k, path in config.INPUT_FILES:
    items.append((path, os.path.relpath(path, WS)))
for name in ("questions.jsonl", "说明.md", "题目模板.md"):
    items.append((os.path.join(QS, name), os.path.relpath(os.path.join(QS, name), WS)))
for name in MIRROR_OUTPUTS:
    p = os.path.join(OUT, name)
    if os.path.isfile(p):
        items.append((p, os.path.relpath(p, WS)))

copied = []
for src, r in items:
    if not os.path.isfile(src):
        print("MISSING", src)
        continue
    dst = os.path.join(MIR, r)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)
    copied.append(r)
print("mirror=%s  copied=%d" % (MIR, len(copied)))
for r in copied:
    print("  ", r)
