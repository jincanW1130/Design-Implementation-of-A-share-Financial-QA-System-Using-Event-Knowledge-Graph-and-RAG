# -*- coding: utf-8 -*-
"""s3_citation_audit.py —— 自写《02》依据声明审计（不只跑 N2）+ 三处版本号复算。"""
import os, re, subprocess
ROOT = r"C:\Users\15129\Desktop\毕业设计"
CUR = "v3.2"
SKIP = ("\\.git", "__pycache__", "_审查工作底稿", "_整改_第一步", "_整改_第二步", "_工作底稿", "_归档", "_试跑")
DOCS = []
for d, _, fs in os.walk(ROOT):
    if any(x in d for x in SKIP):
        continue
    for f in fs:
        if not f.endswith(".md"):
            continue
        rel = os.path.relpath(os.path.join(d, f), ROOT); top = rel.split(os.sep)[0]
        if rel.count(os.sep) == 0 or (top.startswith("阶段") and rel.count(os.sep) == 1) or top in ("工具", "代码"):
            DOCS.append(rel)
V = re.compile(r"《02[-—][^》]*》[^\n]{0,12}?\**(v\d+\.\d+)")
KEY = re.compile(r"(依据|上游|需求来源)")
REC = ("05-", "06-", "08-", "11-", "14-", "17-")
print("[1] 依据声明行（含显式版本号）逐行审计，当前基线 %s" % CUR)
n = 0
for rel in sorted(set(DOCS)):
    base = os.path.basename(rel)
    for i, line in enumerate(open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read().split("\n"), 1):
        if "《02" not in line or not KEY.search(line):
            continue
        m = V.search(line)
        if not m:
            continue
        n += 1
        ver = m.group(1)
        chain = (CUR in line) or any(w in line for w in ("版本链", "未改变", "不影响", "历史", "留痕", "编制时", "升为", "其后", "审核时为"))
        rec = base[:3] in REC
        state = "OK" if ver == CUR else ("已交代(版本链)" if chain else ("记录类留痕" if rec else "★过期引用"))
        print("    %-14s %s:%d  声明版本=%s 记录类=%s" % (state, rel, i, ver, rec))
        if ver != CUR:
            print("       原文: %s" % line.strip()[:170])
print("    依据声明行总数 = %d" % n)
print("\n[2] 正文里指向《02》某节的版本号（非依据声明行，N2 不覆盖）")
P = re.compile(r"《02》第12\.[47]节 v\d\.\d")
for rel in sorted(set(DOCS)):
    for i, line in enumerate(open(os.path.join(ROOT, rel), encoding="utf-8", errors="replace").read().split("\n"), 1):
        for m in P.finditer(line):
            print("    %s:%d  %s" % (rel, i, m.group(0)))
            print("       ...%s..." % line[max(0, m.start()-70):m.end()+30])
print("\n[3] 《02》三处版本号（现行工作区）")
lines = open(os.path.join(ROOT, "02-项目执行总控文档.md"), encoding="utf-8").read().split("\n")
title = re.search(r"v(\d+\.\d+)\s*$", lines[0].strip()).group(1)
field = next(re.match(r"\|\s*版本\s*\|\s*v([\d.]+)", l) for l in lines[:30] if re.match(r"\|\s*版本\s*\|", l)).group(1)
last = [re.match(r"\|\s*(v[\d.]+)\s*\|", l) for l in lines]
last = [m.group(1).lstrip("v") for m in last if m][-1]
print("    标题=v%s  版本字段=v%s  修订记录末行=v%s  -> %s" % (title, field, last, "三处一致" if title == field == last else "★不一致"))
print("\n[4] git 历史中《02》三处版本号（可回溯范围）")
def git(*a):
    return subprocess.run(["git", "-c", "core.quotepath=false"] + list(a), cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
for line in git("log", "--format=%H\t%ad\t%s", "--date=short", "--", "02-项目执行总控文档.md").strip().split("\n"):
    sha, date, subj = line.split("\t", 2)
    ls = git("show", f"{sha}:02-项目执行总控文档.md").split("\n")
    t = re.search(r"v(\d+\.\d+)\s*$", ls[0].strip()).group(1)
    f = next(re.match(r"\|\s*版本\s*\|\s*v([\d.]+)", l) for l in ls[:30] if re.match(r"\|\s*版本\s*\|", l)).group(1)
    ms = [re.match(r"\|\s*(v[\d.]+)\s*\|", l) for l in ls]
    lv = [m.group(1).lstrip("v") for m in ms if m][-1]
    print("    %s %s 标题=v%s 版本字段=v%s 修订末行=v%s -> %s  %s"
          % (sha[:8], date, t, f, lv, "三处一致" if t == f == lv else "★不一致", subj[:30]))
