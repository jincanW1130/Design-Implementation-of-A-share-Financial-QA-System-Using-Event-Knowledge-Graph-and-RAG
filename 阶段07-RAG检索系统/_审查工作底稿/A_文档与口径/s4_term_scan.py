# -*- coding: utf-8 -*-
"""s4_term_scan.py —— 术语与边界扫描（含正对照）。"""
import os, re
ROOT = r"C:\Users\15129\Desktop\毕业设计"
T = []
def add(p, label):
    T.append((label, p))
add(os.path.join(ROOT, "阶段07-RAG检索系统", "19-第7阶段产出文档（RAG检索系统）.md"), "《19》")
add(os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "18-第7阶段任务书（RAG检索系统）.md"), "《18》")
for n in sorted(os.listdir(os.path.join(ROOT, "代码", "检索"))):
    if n.endswith((".py", ".md")):
        add(os.path.join(ROOT, "代码", "检索", n), "代码/检索/" + n)
for base in ("检索产出", "预实验问题集"):
    d0 = os.path.join(ROOT, "阶段07-RAG检索系统", base)
    for d, _, fs in os.walk(d0):
        for f in sorted(fs):
            add(os.path.join(d, f), base + "/" + os.path.relpath(os.path.join(d, f), d0))
print("扫描目标数 = %d（《19》《18》＋代码\\检索\\*.py/*.md ＋ 检索产出\\** ＋ 预实验问题集\\**）" % len(T))
BANNED = "向量" + "数据库"
MODEL = re.compile(r"(gpt-?\d|claude|gemini|qwen|ernie|chatglm|glm-\d|kimi|deepseek|llama|moonshot|文心|通义)", re.I)
ALLOW = ("第三方", "复核", "盲标", "留痕", "剥离", "非答案生成", "抽检", "抽取模型")
DEPLOY = re.compile(r"(已部署|部署了|已经部署|已上线|已运行)")
NEG = re.compile(r"(未|不得|没有|无|非|禁止|不写|不接入|误读)")
X = lambda p: open(p, encoding="utf-8", errors="replace").read()
print("\n(a) 被禁用的四字连写术语「%s」的命中：%d 处（正对照=%s）"
      % (BANNED, sum(X(p).count(BANNED) for _, p in T), BANNED in ("x" + BANNED + "x")))
hits = [(l, i, ln.strip()[:110]) for l, p in T for i, ln in enumerate(X(p).split("\n"), 1) if BANNED in ln]
for h in hits: print("    ", h)
print("\n(b) 「Neo4j + 已部署类肯定表述」命中：")
cnt = 0
for l, p in T:
    for i, ln in enumerate(X(p).split("\n"), 1):
        if "Neo4j" in ln and DEPLOY.search(ln) and not NEG.search(ln):
            print("     %s:%d  %s" % (l, i, ln.strip()[:120])); cnt += 1
print("    合计 %d 处" % cnt)
print("\n(c) 答案生成模型型号（未带第三方／抽取等豁免语境）命中：")
cnt = 0
for l, p in T:
    for i, ln in enumerate(X(p).split("\n"), 1):
        if MODEL.search(ln) and not any(m in ln for m in ALLOW):
            print("     %s:%d  %s" % (l, i, ln.strip()[:120])); cnt += 1
print("    合计 %d 处" % cnt)
print("\n(d) 含「答案生成」且同行出现模型型号的行：")
cnt = 0
for l, p in T:
    for i, ln in enumerate(X(p).split("\n"), 1):
        if "答案生成" in ln and MODEL.search(ln):
            print("     %s:%d  %s" % (l, i, ln.strip()[:120])); cnt += 1
print("    合计 %d 处" % cnt)
print("\n(e) 六张表以外的表名候选（\\bhistory|session|log|tags|feedback|categories\\b 一类，人工判读）：")
for l, p in T:
    for i, ln in enumerate(X(p).split("\n"), 1):
        for m in re.finditer(r"\b(history|session|user_profile|logs?|audit|metadata|tags?|comments?|feedback|categor(y|ies))\b", ln):
            print("     %s:%d  [%s]  %s" % (l, i, m.group(0), ln.strip()[:110]))
