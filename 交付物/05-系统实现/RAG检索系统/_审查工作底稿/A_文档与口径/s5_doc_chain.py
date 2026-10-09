# -*- coding: utf-8 -*-
"""s5_doc_chain.py —— 口径链落点矩阵 ＋ 《18》产出清单 vs 实物 ＋ 《18》第八节 28 行 vs 脚本 28 组。"""
import os, re
ROOT = r"C:\Users\15129\Desktop\毕业设计"
F = {
 "《02》12.4": r"02-项目执行总控文档.md",
 "《02》12.7": r"02-项目执行总控文档.md",
 "《10》4.6.3-4.6.6": r"交付物/07-设计与需求/总体设计\10-系统总体设计（第四阶段）.md",
 "《10》源文件4.6": r"交付物/07-设计与需求/总体设计\_分节源文件\4.6-RAG检索架构.md",
 "《18》": r"交付物/04-数据与知识图谱/事件抽取与知识图谱\18-第7阶段任务书（RAG检索系统）.md",
 "《19》": r"交付物/05-系统实现/RAG检索系统\19-第7阶段产出文档（RAG检索系统）.md",
 "config.py": r"交付物/03-代码\检索\config.py",
 "检索README": r"交付物/03-代码\检索\README.md",
}
def load(p): return open(os.path.join(ROOT, p), encoding="utf-8").read()
def lineno(p, pat, regex=False):
    out = []
    for i, l in enumerate(load(p).split("\n"), 1):
        ok = re.search(pat, l) if regex else (pat in l)
        if ok: out.append(i)
    return out
print("[1] g 下限（g ≥ 1）落点")
for k, p in F.items():
    n = len(lineno(p, "g ≥ 1")) + len(lineno(p, "不低于下限 1"))
    print("    %-18s 命中行号=%s" % (k, sorted(set(lineno(p, "g ≥ 1") + lineno(p, "不低于下限 1")))))
print("\n[2] 旧 g 规则文本「在不劣于 g=0 的四项指标的前提下，让图谱侧证据进入最终集合的最大 g」（不含下限）")
for k, p in F.items():
    hits = [i for i in lineno(p, "让图谱侧证据进入最终集合的最大 g")]
    print("    %-18s 命中行号=%s" % (k, hits))
print("\n[3] 三层定义关键词命中数")
for k, p in F.items():
    t = load(p)
    print("    %-18s 第一层=%d 第二层=%d 第三层=%d K−g=%d 回填=%d 并列=%d"
          % (k, t.count("第一层"), t.count("第二层"), t.count("第三层"), t.count("K−g"), t.count("回填"), t.count("并列")))
print("\n[4] 四项定值在各落点是否出现")
for k, p in F.items():
    t = load(p)
    print("    %-18s K=10:%s N=20:%s 3600:%s g=2:%s" % (k, "10" in t, "20" in t, "3600" in t, "g = 2" in t or "g=2" in t or "g ＝ 2" in t))
print("\n[5] 工具\\拼装第四阶段文档.py 中的旧规则文本")
p = r"工具\拼装第四阶段文档.py"
print("    行号=%s" % sorted(set(lineno(p, "让图谱侧证据进入最终集合的最大 g") + lineno(p, "g ≥ 1"))))
print("\n[6] 《18》4.2／4.3 产出清单 vs 实物")
code = sorted(n for n in os.listdir(os.path.join(ROOT, "交付物/03-代码", "检索")) if n != "__pycache__")
out = sorted(os.listdir(os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "检索产出")))
t18 = load(F["《18》"])
print("    代码\\检索\\ 实际 %d 件：%s" % (len(code), code))
print("    检索产出\\ 实际 %d 件：%s" % (len(out), out))
for name in ("check_inputs", "input_manifest", "third_party_review"):
    print("    《18》中「%s」出现次数=%d" % (name, t18.count(name)))
print("    《18》4.2 表列出的脚本：%s" % re.findall(r"^\| (?:代码\\检索\\)?([a-z_]+\.py) \|", t18, re.M))
print("\n[7] 《18》第八节 28 行 vs 验收第7阶段.py 的 28 组")
rows = re.findall(r"^\|\s*(\d+)（([A-Z]{1,2})）\s*\|", t18, re.M)
print("    《18》表行数=%d，行号序列连续=%s，组字母=%s" % (len(rows), [int(r[0]) for r in rows] == list(range(1, 29)), [r[1] for r in rows]))
g7 = load(r"工具\验收第7阶段.py")
groups = re.findall(r'print\("([A-Z]{1,2})、《18》第八节 第 (\d+) 行', g7)
print("    脚本分组数=%d，映射=%s" % (len(groups), groups))
print("    1:1 对应=%s" % ([ (g, int(n)) for g, n in groups ] == [(a, i) for i, (num, a) in enumerate(rows, 1)]))
print("    脚本 chk 调用数=%d（报告 72 项；含 chk_int 等辅助）" % len(re.findall(r"\bchk\(", g7)))
