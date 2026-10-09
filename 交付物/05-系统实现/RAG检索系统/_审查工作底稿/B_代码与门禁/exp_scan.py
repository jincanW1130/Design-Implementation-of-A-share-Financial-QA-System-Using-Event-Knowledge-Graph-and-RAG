# -*- coding: utf-8 -*-
"""自己的扫描器：把门禁 W1/AA 用的模式集跑遍 交付物/03-代码\检索\ 全体 .py（不是只跑链上六个），
并用正对照证明扫描器有效；同时搜 STAGE6_FORBID_MODEL_CALLS 一类重放守卫。"""
import io
import os
import re
import sys

WS = r"C:\Users\15129\Desktop\毕业设计"
CODE = os.path.join(WS, "交付物/03-代码", "检索")

BANNED = "向量" + "数据库"
KEY = ["api" + "_key", "API" + "_KEY", "access" + "_token", "sec" + "ret",
       "requests" + ".", "urllib" + ".request", "socket" + "."]
HTTP = ["http" + "://", "https" + "://"]
MODEL = re.compile(r"(gpt-?\d|claude|gemini|qwen|ernie|chatglm|glm-\d|kimi|deepseek|llama|"
                   r"moonshot|文心|通义)", re.IGNORECASE)

files = sorted(n for n in os.listdir(CODE) if n.endswith(".py"))
texts = {n: io.open(os.path.join(CODE, n), encoding="utf-8").read() for n in files}

CHAIN = ["check_inputs.py", "vector_search.py", "graph_query.py", "pipeline.py",
         "pre_experiment.py", "metrics.py"]

print("代码\\检索 下 .py 文件：%d 个 -> %s" % (len(files), files))
print()
print("== A. 密钥／网络字样（W1 模式集）逐文件 ==")
hdr = "%-24s" % "文件"
for p in KEY + HTTP:
    hdr += " %s" % (p[:8].ljust(8))
print(hdr)
for n in files:
    t = texts[n]
    line = "%-24s" % n
    for p in KEY + HTTP:
        c = sum(1 for L in t.split("\n") if p in L)
        line += " %s" % (str(c).ljust(8))
    print(line)
print()
print("-- 逐处命中（含行号）--")
for n in files:
    for p in KEY + HTTP:
        for i, L in enumerate(texts[n].split("\n"), 1):
            if p in L:
                print("   %s:%d  [%s]  %s" % (n, i, p, L.strip()[:90]))
print()
print("== 正对照（扫描器有效性）==")
ctrl = "s = 'http://x'; requests.get(s); k='api_key'; socket.socket(); urllib.request.urlopen"
print("   合成样本命中数 =", sum(1 for p in KEY + HTTP if p in ctrl), "（应 >0）")
print("   third_party_review.py 命中种类 =",
      sum(1 for p in KEY + HTTP if p in texts.get("third_party_review.py", "")))
print()
print("== B. 禁用四字术语 ==")
for n in files:
    c = texts[n].count(BANNED)
    if c:
        for i, L in enumerate(texts[n].split("\n"), 1):
            if BANNED in L:
                print("   %s:%d  %s" % (n, i, L.strip()[:90]))
print("   正对照（合成串命中）= %s" % (BANNED in ("x" + BANNED + "y")))
print()
print("== C. 答案生成模型型号（AA3 口径）==")
for n in files:
    hits = sorted(set(m.group(0).lower() for m in MODEL.finditer(texts[n])))
    if hits:
        print("   %-24s %s" % (n, hits))
print("   正对照 =", bool(MODEL.search("gpt-4o")))
print()
print("== D. STAGE6 风格重放／禁网守卫 ==")
pat = re.compile(r"STAGE\d*_FORBID|FORBID_MODEL|MODEL_CALLS_ALLOWED|OFFLINE|HF_HUB_OFFLINE|"
                 r"TRANSFORMERS_OFFLINE|NO_NETWORK|ALLOW_NETWORK")
root = WS
found = []
for dp, dn, fn in os.walk(root):
    if ".git" in dp or "__pycache__" in dp:
        continue
    for f in fn:
        if f.endswith((".py", ".md", ".json", ".cfg", ".toml")):
            p = os.path.join(dp, f)
            try:
                t = io.open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            for i, L in enumerate(t.split("\n"), 1):
                if pat.search(L):
                    found.append((os.path.relpath(p, root).replace(os.sep, "/"), i,
                                  L.strip()[:100]))
print("   命中 %d 处：" % len(found))
for r in found[:60]:
    print("   %s:%d  %s" % r)
