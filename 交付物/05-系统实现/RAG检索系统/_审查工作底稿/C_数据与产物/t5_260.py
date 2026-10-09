# -*- coding: utf-8 -*-
"""C 线：核 questions.jsonl 有没有把第 6 阶段 260 条抽取参照集当成检索测试集／出题素材"""
import io, json, os, re
from collections import Counter

ROOT = r"C:\Users\15129\Desktop\毕业设计"
S6 = os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "抽取评测集", "v2.1")
P7 = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统")

def load_jsonl(p):
    with io.open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]

qs = load_jsonl(os.path.join(P7, "预实验问题集", "questions.jsonl"))
qdocs = set()
for q in qs:
    for s in q["source_material"]:
        qdocs.add(int(s["doc_id"]))
    for d in q["gold_evidence_doc_ids"]:
        qdocs.add(int(d))
print("30 题涉及文档 =", len(qdocs))
print("题面引用文档 =", sorted(qdocs))

# 260 参照集：自动标注台账 与 工作区 TEST/DEV 文件的 doc 号
led = json.load(io.open(os.path.join(S6, "自动标注_flash", "自动标注台账.json"), encoding="utf-8"))
def find_docs(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("doc_id", "doc") and isinstance(v, (int, str)):
                m = re.match(r"^\D*(\d{4})", str(v))
                if m:
                    out.add(int(m.group(1)))
            find_docs(v, out)
    elif isinstance(o, list):
        for v in o:
            find_docs(v, out)

led_docs = set()
find_docs(led, led_docs)
print("台账里出现的 4 位 doc 号 =", len(led_docs))

ws = os.path.join(S6, "自动标注_flash", "工作区")
ws_docs = set()
for sub in ("dev", "test"):
    d = os.path.join(ws, sub)
    for name in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        s = io.open(os.path.join(d, name), encoding="utf-8", errors="replace").read()
        m = re.search(r"(?:doc_id|文档号|文档)[^\d]{0,12}(\d{4})", s)
        if m:
            ws_docs.add(int(m.group(1)))
print("工作区 dev/test 头部行可提取 doc 号 =", len(ws_docs), sorted(ws_docs)[:20])

overlap = qdocs & (led_docs | ws_docs)
print("30 题涉及文档与 260 参照集(台账∪工作区)的交集 =", len(overlap), sorted(overlap)[:30])

# 参照集规模核对
print()
print("自动标注台账 keys =", list(led.keys())[:15])
for k, v in led.items():
    if isinstance(v, list):
        print("  ", k, "list", len(v))
    elif isinstance(v, dict):
        print("  ", k, "dict", list(v.keys())[:8])
    else:
        print("  ", k, "=", json.dumps(v, ensure_ascii=False)[:120])
