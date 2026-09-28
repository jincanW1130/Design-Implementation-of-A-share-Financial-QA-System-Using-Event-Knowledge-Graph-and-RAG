# -*- coding: utf-8 -*-
"""程序化逐字比对：《18》表 18-F 七行里的等效 Cypher 串 vs graph_query.CYPHER。"""
import io
import os
import re
import sys

WS = r"C:\Users\15129\Desktop\毕业设计"
sys.path.insert(0, os.path.join(WS, "代码", "检索"))
import graph_query as gq  # noqa: E402

p18 = os.path.join(WS, "阶段06-事件抽取与知识图谱", "18-第7阶段任务书（RAG检索系统）.md")
lines = io.open(p18, encoding="utf-8").read().split("\n")

rows = {}
for ln in lines:
    m = re.match(r"^\|\s*(G[1-7])\s*\|", ln)
    if m:
        gid = m.group(1)
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        # 最后一格是等效 Cypher；去掉反引号
        cy = cells[-1].replace("`", "").strip()
        rows[gid] = cy

print("提取到 %d 行：%s" % (len(rows), sorted(rows)))
allok = True
for gid in ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]:
    doc = rows.get(gid)
    impl = gq.CYPHER.get(gid)
    same = (doc == impl)
    allok = allok and same
    print("%s  逐字相同=%s" % (gid, same))
    if not same:
        print("   doc   = %r" % doc)
        print("   impl  = %r" % impl)
        for i in range(min(len(doc or ""), len(impl or ""))):
            if doc[i] != impl[i]:
                print("   首个差异位 %d: doc=%r impl=%r" % (i, doc[i], impl[i]))
                break
        print("   len doc=%d impl=%d" % (len(doc or ""), len(impl or "")))
print("全部七行逐字相同 = %s" % allok)

# 附加：cypher_table() 的输出是否与 CYPHER 一致
tbl = gq.cypher_table()
print("cypher_table()==CYPHER:", tbl == gq.CYPHER)
