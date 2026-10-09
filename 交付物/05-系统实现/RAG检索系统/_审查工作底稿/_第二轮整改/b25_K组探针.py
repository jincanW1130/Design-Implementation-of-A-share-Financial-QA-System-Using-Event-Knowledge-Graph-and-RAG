# -*- coding: utf-8 -*-
"""B-25 探针：把《工具\\跨文档核验.py》K 组（路径存在性）的**现行逻辑**与**扩展后逻辑**
各跑一遍，逐条列出"修前看不见 / 修后暴露"的反引号 token，供分类（真悬空／可解析别名／
第三方复核留痕）。

只读：不写工作区任何文件；结果打印到 stdout。

用法（工作区根目录下）：
    python 交付物/05-系统实现/RAG检索系统\\_审查工作底稿\\_第二轮整改\\b25_K组探针.py
"""
from __future__ import annotations

import fnmatch
import io
import os
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))

STAGES = [d for d in sorted(__import__("glob").glob(os.path.join(ROOT, "阶段*")))
          if os.path.isdir(d)]
LITDIR = os.path.join(ROOT, "交付物/08-文献与开题/文献调研与开题")
SECDIR = os.path.join(ROOT, "交付物/07-设计与需求/总体设计", "_分节源文件")


def docs():
    out = sorted(__import__("glob").glob(os.path.join(ROOT, "*.md")))
    for sd in STAGES:
        out += sorted(__import__("glob").glob(os.path.join(sd, "*.md")))
    return out


def load(p):
    with open(p, "r", encoding="utf-8") as f:
        return f.read()


D = {os.path.basename(p): load(p) for p in docs()}

WHITE = re.compile(r"(输入|输出|模板)\.|^\{|^\d+_\d+_|^[A-Z]+-\d+_[A-Za-z]+\d+_|\.\.\.$|…"
                   r"|^X\.md$|_译文\.docx$|方向X_|^[^\\/]*\{[^}]*\}")

ARCH = __import__("glob").glob(os.path.join(LITDIR, "_归档_*"))
ARCH += [d for d in __import__("glob").glob(os.path.join(LITDIR, "_归档_*", "*"))
         if os.path.isdir(d)]
SEARCH = [ROOT, LITDIR, os.path.join(LITDIR, "文献PDF"), os.path.join(LITDIR, "文献翻译"),
          os.path.join(ROOT, "工具"), os.path.join(ROOT, "图表"), os.path.join(ROOT, "代码"),
          SECDIR] + STAGES
SEARCH += [d for d in __import__("glob").glob(os.path.join(ROOT, "交付物/03-代码", "*")) if os.path.isdir(d)]
SEARCH += [d for d in __import__("glob").glob(os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "*"))
           if os.path.isdir(d)]
SEARCH += [os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "_试跑")]
SEARCH += [d for d in __import__("glob").glob(
    os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "抽取评测集", "*")) if os.path.isdir(d)]
SEARCH += [d for d in __import__("glob").glob(
    os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "*")) if os.path.isdir(d)]

LEGACY = {"文献调研": LITDIR, "10-系统总体设计（第四阶段）": SECDIR}
RENAMED = {"11-第二轮复审判定与修订决议（2026-09-23）.md":
           "11-第4阶段复审判定与修订决议（2026-09-23）.md"}


def legacy_paths(tok):
    out = []
    for old, new in LEGACY.items():
        for sep in ("\\", "/"):
            if tok.startswith(old + sep):
                rest = tok[len(old) + 1:]
                for base in [new] + ARCH:
                    out += [os.path.join(base, rest), os.path.join(base, os.path.basename(rest))]
    alt = RENAMED.get(os.path.basename(tok))
    if alt:
        for d in SEARCH + ARCH:
            out.append(os.path.join(d, alt))
    return out


OLD_EXT = re.compile(r"`([^`\n]+\.(?:md|py|html|csv|docx|pdf|png|svg))`")
NEW_EXT = re.compile(r"`([^`\n]+\.(?:md|py|html|csv|docx|pdf|png|svg|json|jsonl|txt|cypher))`")


def old_exists(tok):
    cands = [os.path.join(d, tok) for d in SEARCH]
    if "\\" not in tok and "/" not in tok:
        for d in SEARCH + ARCH:
            cands.append(os.path.join(d, os.path.basename(tok)))
    cands += legacy_paths(tok)
    return any(os.path.exists(c) for c in cands)


SKIP_DIRS = {".git", "__pycache__", ".idea"}
INDEX = []          # (相对路径小写正斜杠, 是否目录)
for _dp, _dn, _fn in os.walk(ROOT):
    _dn[:] = [d for d in _dn if d not in SKIP_DIRS]
    _rel = os.path.relpath(_dp, ROOT).replace("\\", "/")
    if _rel != ".":
        INDEX.append((_rel.lower(), True))
    for _f in _fn:
        _r = (os.path.join(_rel, _f) if _rel != "." else _f).replace("\\", "/")
        INDEX.append((_r.lower(), False))


def new_exists(tok):
    t = tok.replace("\\", "/").strip().lower()
    if any(ch in t for ch in "*?["):
        # 通配写法（`exp_*.py`／`交付物/03-代码\检索\*.py`）：按模式匹配，命中任意一条即算存在
        return any(fnmatch.fnmatch(rel, t) or fnmatch.fnmatch(rel, "*/" + t)
                   for rel, _isdir in INDEX)
    if "/" in t:
        if any(rel == t or rel.endswith("/" + t) for rel, _isdir in INDEX):
            return True
    elif any(rel == t or rel.split("/")[-1] == t for rel, _isdir in INDEX):
        return True
    # 旧路径别名／改名登记（与现行 K 组同一套别名；别名解析成功即算存在）
    return any(os.path.exists(c) for c in legacy_paths(tok))


def scan(ext_re, exists, note=""):
    miss = []
    seen_tokens = 0
    for name in D:
        for idx, line in enumerate(D[name].split("\n"), 1):
            for tok in ext_re.findall(line):
                seen_tokens += 1
                if tok.startswith("http") or WHITE.search(tok) or " " in tok:
                    continue
                if not exists(tok):
                    miss.append((name, idx, tok, line.strip()))
    return seen_tokens, miss


print("=" * 78)
print("B-25 探针：K 组扩展名白名单／搜索深度的修前 vs 修后")
print("工作区：%s" % ROOT)
print("参与核验文档 %d 份；磁盘索引条目 %d 条（排除 .git／__pycache__／.idea）" % (len(D), len(INDEX)))
print("=" * 78)

n_old, miss_old = scan(OLD_EXT, old_exists)
n_new, miss_new = scan(NEW_EXT, new_exists)
print("\n[修前] 白名单 8 种扩展名：匹配 %d 个反引号 token，判悬空 %d 条" % (n_old, len(miss_old)))
for name, idx, tok, _line in sorted(set(miss_old)):
    print("   !! %s:%d  %s" % (name, idx, tok))

print("\n[修后] 白名单 21 种扩展名 ＋ 全树索引（含通配支持）：匹配 %d 个 token，"
      "判悬空 %d 条" % (n_new, len(miss_new)))
for name, idx, tok, line in sorted(set(miss_new)):
    print("   !! %s:%d  %s" % (name, idx, tok))
    print("        ｜%s" % line[:150])

old_tokens = {(n, t) for n, _i, t, _l in miss_old}
new_tokens = {(n, t) for n, _i, t, _l in miss_new}
print("\n[新暴露] 修前不可见（扩展名盲区）、修后判悬空：%d 条" % len(new_tokens - old_tokens))
for name, idx, tok, line in sorted(set(miss_new)):
    if (name, tok) in new_tokens - old_tokens:
        print("   NEW!! %s:%d  %s" % (name, idx, tok))
        print("         ｜%s" % line[:150])
print("\n[已消解] 修前判悬空、修后判存在：%d 条" % len(old_tokens - new_tokens))
for name, tok in sorted(old_tokens - new_tokens):
    print("   FIXED %-46s %s" % (name, tok))

by_ext = {}
for name in D:
    for tok in re.findall(r"`([^`\n]+)`", D[name]):
        m = re.search(r"(\.[A-Za-z0-9_]+)$", tok)
        if m:
            by_ext.setdefault(m.group(1).lower(), 0)
            by_ext[m.group(1).lower()] += 1
print("\n[分布] 参与核验文档的反引号 token 扩展名分布（全部 %d 种，按出现次数降序）：" % len(by_ext))
for ext, cnt in sorted(by_ext.items(), key=lambda kv: (-kv[1], kv[0])):
    print("   %-14s %d" % (ext, cnt))
print("=" * 78)
