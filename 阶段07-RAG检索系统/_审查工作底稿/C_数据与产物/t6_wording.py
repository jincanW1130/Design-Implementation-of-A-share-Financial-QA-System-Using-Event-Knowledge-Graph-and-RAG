# -*- coding: utf-8 -*-
"""C 线：逐字查「人工确认／人工一致率／金标准」的每一次出现与语境"""
import io, os, re

ROOT = r"C:\Users\15129\Desktop\毕业设计"
QDIR = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集")
TARGETS = [
    os.path.join(QDIR, "第三方复核报告.md"),
    os.path.join(QDIR, "第三方复核台账.json"),
    os.path.join(QDIR, "questions.jsonl"),
    os.path.join(QDIR, "说明.md"),
    os.path.join(QDIR, "题目模板.md"),
    os.path.join(QDIR, "收口报告（千帆剥离与T8重绑）.md"),
]
WORDS = ["人工确认", "人工一致率", "人工复核", "人工构造", "人工金标准", "金标准"]

for p in TARGETS:
    s = io.open(p, encoding="utf-8", errors="replace").read()
    print("=" * 78)
    print(os.path.basename(p), "｜", {w: s.count(w) for w in WORDS if s.count(w)})
    for w in WORDS:
        for m in re.finditer(re.escape(w), s):
            a = max(0, m.start() - 60)
            b = min(len(s), m.start() + len(w) + 60)
            seg = re.sub(r"\s+", " ", s[a:b])
            neg = "否定语境候选" if re.search(r"(不是|非|无|未|不得|不能|没有|禁止|≠|不写)",
                                              s[max(0, m.start() - 20):m.start() + len(w) + 20]) else "正向候选"
            print("  [%s][%s] ...%s..." % (w, neg, seg))
