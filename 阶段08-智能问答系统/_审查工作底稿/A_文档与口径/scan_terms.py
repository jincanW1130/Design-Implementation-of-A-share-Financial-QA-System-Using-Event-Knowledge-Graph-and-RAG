# -*- coding: utf-8 -*-
"""A 线术语/边界扫描（只读）——每条扫描先做正对照，再扫真实文档。"""
import io, os, sys, re, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"C:\Users\15129\Desktop\毕业设计"

# 构造禁用连写，脚本自身不被命中
BANNED_TERM = "向量" + "数据库"

# 活的编号文档（排除工作底稿/审查工作底稿/阶段08的产出目录）
DOCS = []
for pat in ["00-*.md", "01-*.md", "02-*.md", "03-*.md"]:
    DOCS += glob.glob(os.path.join(ROOT, pat))
for d in sorted(os.listdir(ROOT)):
    p = os.path.join(ROOT, d)
    if os.path.isdir(p) and re.match(r"阶段0[1-8]-", d):
        for f in sorted(os.listdir(p)):
            if re.match(r"\d\d-.*\.md$", f) and "审查工作底稿" not in f:
                DOCS.append(os.path.join(p, f))
DOCS += glob.glob(os.path.join(ROOT, "代码", "**", "*.md"), recursive=True)
DOCS += [os.path.join(ROOT, "工具", "README.md")]
DOCS = sorted(set(DOCS))
print("扫描文档数：%d" % len(DOCS))


def scan(pat, label, control_text, files, show=6):
    print("\n" + "=" * 70)
    print("【%s】 正则=%s" % (label, pat.pattern))
    rx = re.compile(pat)
    hit = rx.search(control_text)
    print("  正对照：样本=%r → %s" % (control_text, "命中 OK" if hit else "*** 未命中，扫描器坏 ***"))
    n = 0
    for f in files:
        for i, L in enumerate(open(f, encoding="utf-8", errors="replace").read().split("\n"), 1):
            if rx.search(L):
                n += 1
                if n <= show:
                    rel = os.path.relpath(f, ROOT)
                    print("    %s:%d  %s" % (rel, i, L.strip()[:110]))
    print("  真实命中行数=%d" % n)
    return n


# 1) 禁用连写
scan(re.compile(re.escape(BANNED_TERM)), "禁用连写（向量+数据库）",
     "本系统以" + BANNED_TERM + "作为主存储。", DOCS)

# 2) 部署 Neo4j 服务 的声称
scan(re.compile(r"(已|正式|实际)(部署|搭建|上线)[^。\n]{0,12}Neo4j|Neo4j[^。\n]{0,8}(服务|实例)[^。\n]{0,6}(已|运行|启动|部署)"),
     "声称已部署 Neo4j 服务", "本项目已部署 Neo4j 服务并对外提供查询。", DOCS)

# 3) 「模型分析（非公开事实）」标注
scan(re.compile(r"模型分析（非公开事实）|模型分析\(非公开事实\)"),
     "「模型分析（非公开事实）」标注", "开放式分析须标注「模型分析（非公开事实）」。", DOCS)

# 4) 「本次回答未使用图谱扩展」固定标注
scan(re.compile(r"本次回答未使用图谱扩展"), "固定标注「本次回答未使用图谱扩展」",
     "页面固定显示「本次回答未使用图谱扩展」。", DOCS)

# 5) 越界声称：建库 / DDL / CREATE TABLE / 前端 / 正式 120 题 / 人工评分 / 微调
for pat, lbl, ctrl in [
    (r"CREATE\s+TABLE", "DDL/CREATE TABLE", "执行 CREATE TABLE user ();"),
    (r"建库|建表语句|物理建表", "建库/建表语句", "本阶段完成建库与建表语句。"),
    (r"前端(页面|实现|代码|已完成)", "前端实现声称", "本阶段已完成前端实现。"),
    (r"人工(评分|打分|0-1-2|0/1/2)", "人工评分声称", "完成人工评分 0-1-2。"),
    (r"微调|finetune|fine-tune|LoRA", "模型微调声称", "对模型做了 LoRA 微调。"),
    (r"120\s*题|120 道|正式实验(已|结果|完成)", "正式 120 题实验声称", "已完成 120 题正式实验并给出结果。"),
]:
    scan(re.compile(pat), lbl, ctrl, DOCS, show=10)
