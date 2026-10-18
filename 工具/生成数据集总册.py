# -*- coding: utf-8 -*-
"""生成《数据集总册》与机器可读清单：只读盘点，不移动、不修改任何数据。"""
import os, json, hashlib, datetime

ROOT = r"C:\Users\15129\Desktop\毕业设计"
OUT_MD = os.path.join(ROOT, r"交付物\04-数据与知识图谱\数据集总册.md")
OUT_JS = os.path.join(ROOT, r"交付物\04-数据与知识图谱\数据集清单.json")

GROUPS = [
    # (角色, 阶段, 相对路径, 说明, 是否计入"交付级真值")
    ("真值·数据集", "第 5 阶段", r"数据准备\数据集\v2.1", "现行数据集 v2.1：105 家公司／709 篇／5018 块；含 clean／chunks／meta／index（FAISS）", True),
    ("评测集", "第 5 阶段", r"数据准备\数据集\抽取评测集", "抽取评测用的 260 块评测集（v2.1）", True),
    ("中间产物", "第 5～6 阶段", r"数据准备\数据集\_抽取缓存", "抽取管线缓存（可重跑重建）；后台接口会读取其落点，故不删", False),
    ("派生·图谱", "第 6 阶段", r"事件抽取与知识图谱\图谱导出\v2.1_v1_3", "现行图谱导出：nodes.csv／edges.csv／graph_stats.json（3607 节点／3614 边）", True),
    ("派生·图谱（历史）", "第 6 阶段", r"事件抽取与知识图谱\图谱导出\v2.1_v1_2", "v1.2 口径导出（历史，2802／2736）", False),
    ("派生·检索", "第 7 阶段", r"05-系统实现\RAG检索系统\检索产出", "逐题检索 trace（per_question_trace.jsonl）", True),
    ("派生·检索", "第 7 阶段", r"05-系统实现\RAG检索系统\预实验问题集", "30 题预实验问题集（questions.jsonl）", True),
    ("派生·问答", "第 8 阶段", r"05-系统实现\智能问答系统\问答产出", "问答产出 qa_records.jsonl（30 条基线，导入 MySQL 的来源）", True),
    ("集成产物", "第 9 阶段", r"05-系统实现\前后端系统集成\集成产出", "冒烟矩阵／异常场景／耗时／输入指纹／库表计数等 86 件", True),
    ("实验·测试集", "第 10 阶段", r"06-实验与评测\测试集", "正式 120 题测试集 questions.jsonl（核心 108＋压力 12）", True),
    ("实验·对照（现行）", "第 10 阶段", r"06-实验与评测\对照产出_正式", "正式全量 A～E＋B1 落盘读数（现行主结果）", True),
    ("实验·对照（历史）", "第 10 阶段", r"06-实验与评测\对照产出_v13", "v1.3 时期五组（历史）", False),
    ("实验·对照（历史）", "第 10 阶段", r"06-实验与评测\对照产出", "v1.2 时期读数（历史）", False),
    ("实验·问答评分（现行）", "第 10 阶段", r"06-实验与评测\问答评分_正式", "正式集 582 条答案的三模型评审结果", True),
    ("实验·问答评分（历史）", "第 10 阶段", r"06-实验与评测\问答评分", "30 题预实验集那一组（历史／对照）", False),
    ("实验·抽取评测", "第 10 阶段", r"06-实验与评测\抽取评测", "抽取评测报告与指标（模型参照集／金标准）", True),
    ("实验·系统指标", "第 10 阶段", r"06-实验与评测\系统指标", "NFR-01／NFR-02 读数", True),
    ("实验·复现包", "第 10 阶段", r"06-实验与评测\复现包", "复现用脚本与说明", True),
]

def stat_dir(p):
    n = sz = 0
    for b, _, fs in os.walk(p):
        for f in fs:
            n += 1
            try: sz += os.path.getsize(os.path.join(b, f))
            except OSError: pass
    return n, sz

def sha256_of(p, cap=64 * 1024 * 1024):
    if os.path.getsize(p) > cap:
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()

KEY = {
 r"数据准备\数据集\v2.1": [r"meta\dataset.json", r"clean\documents.jsonl", r"chunks\chunks.jsonl", r"index\faiss.index"],
 r"事件抽取与知识图谱\图谱导出\v2.1_v1_3": [r"graph_stats.json", r"nodes.csv", r"edges.csv"],
 r"05-系统实现\RAG检索系统\检索产出": [r"per_question_trace.jsonl"],
 r"05-系统实现\RAG检索系统\预实验问题集": [r"questions.jsonl"],
 r"05-系统实现\智能问答系统\问答产出": [r"qa_records.jsonl"],
 r"05-系统实现\前后端系统集成\集成产出": [r"input_manifest.json", r"db_counts.json", r"smoke_matrix.jsonl", r"error_scenarios.jsonl"],
 r"06-实验与评测\测试集": [r"questions.jsonl"],
}

entries = []
for role, stage, rel, note, is_truth in GROUPS:
    p = os.path.join(ROOT, "交付物", "04-数据与知识图谱", rel) if rel.startswith(("数据准备", "事件抽取")) \
        else os.path.join(ROOT, "交付物", rel)
    if not os.path.isdir(p):
        entries.append({"role": role, "stage": stage, "path": rel, "exists": False, "note": note})
        continue
    n, sz = stat_dir(p)
    keys = []
    for k in KEY.get(rel, []):
        fp = os.path.join(p, k)
        if os.path.isfile(fp):
            rows = None
            if k.endswith(".jsonl"):
                try:
                    with open(fp, "rb") as fh: rows = sum(1 for _ in fh)
                except OSError: pass
            keys.append({"file": k.replace("\\", "/"), "bytes": os.path.getsize(fp),
                         "rows": rows, "sha256": sha256_of(fp)})
    rel_from_root = os.path.relpath(p, ROOT).replace("\\", "/")
    entries.append({"role": role, "stage": stage, "path": rel_from_root,
                    "files": n, "bytes": sz, "is_delivery_truth": is_truth,
                    "note": note, "key_files": keys})

manifest = {"generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "root": "交付物/", "entries": entries,
            "note": "只读盘点产物；本文件不移动任何数据。真值仍落在各自阶段目录（§「为什么不做物理搬迁」）。"}
json.dump(manifest, open(OUT_JS, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

tot = sum(e.get("bytes", 0) for e in entries)
truth = sum(e.get("bytes", 0) for e in entries if e.get("is_delivery_truth"))
lines = []
lines.append("# 数据集总册（全项目数据资产唯一入口）\n")
lines.append("> 由 `工具/生成数据集总册.py` 生成；机器可读清单见同目录 **`数据集清单.json`**（含核心文件的 SHA-256 与行数）。\n")
lines.append("> **本册只做盘点与索引，不移动任何文件**：数据仍落在产生它的阶段目录里，路径与门禁指纹保持不变。\n")
lines.append("> 最后生成：%s\n" % manifest["generated_at"])
lines.append("## 一、总量\n")
lines.append("| 口径 | 体积 |")
lines.append("| --- | ---: |")
lines.append("| 全部数据资产 | **%.1f MB**（%d 个目录组） |" % (tot / 1048576, len(entries)))
lines.append("| 其中**交付级真值** | **%.1f MB** |" % (truth / 1048576))
lines.append("| 其中历史版本／中间缓存／对照 | %.1f MB |" % ((tot - truth) / 1048576))
lines.append("\n## 二、清单（按角色）\n")
lines.append("| 角色 | 阶段 | 路径 | 文件数 | 体积 | 交付真值 |")
lines.append("| --- | --- | --- | ---: | ---: | :--: |")
for e in entries:
    if not e.get("exists", True):
        lines.append("| %s | %s | `%s` | — | **缺失** | |" % (e["role"], e["stage"], e["path"]))
        continue
    lines.append("| %s | %s | `%s` | %d | %.1f MB | %s |" % (
        e["role"], e["stage"], e["path"], e["files"], e["bytes"] / 1048576,
        "✅" if e["is_delivery_truth"] else ""))
lines.append("\n## 三、核心文件的指纹（可复算）\n")
lines.append("| 文件 | 字节 | 行数 | SHA-256（前 16 位） |")
lines.append("| --- | ---: | ---: | --- |")
for e in entries:
    for k in e.get("key_files", []):
        lines.append("| `%s/%s` | %d | %s | `%s…` |" % (
            e["path"], k["file"], k["bytes"], k["rows"] if k["rows"] is not None else "—",
            (k["sha256"] or ">64MB 未算")[:16]))
lines.append("\n## 四、从源到成品的复现链\n")
lines.append("```text")
lines.append("原始公告/新闻/政策  →  数据准备（抓取→清洗→切块→向量化）  →  数据集 v2.1（709 篇／5018 块／FAISS）")
lines.append("                                   ↓ 事件抽取＋消歧＋去重")
lines.append("                            图谱导出 v2.1_v1_3（3607 节点／3614 边）")
lines.append("                                   ↓ 导入")
lines.append("        MySQL 六表（30 条基线问答）  ＋  Neo4j（图谱）  ＋  向量索引")
lines.append("                                   ↓ 检索＋问答")
lines.append("        检索产出／问答产出  →  测试集（120 题）  →  对照产出_正式／问答评分_正式")
lines.append("```\n")
lines.append("## 五、为什么不做物理搬迁（重要）\n")
lines.append("把数据**搬到同一个目录**技术上可行，但代价是重基线：\n")
lines.append("1. **8 个上游指纹**（《24》第三节 I1）与 **16 个实验指纹**（《26》第三节 G4／G5）都按**精确路径**登记 SHA-256，搬移即全红；")
lines.append("2. `交付物/03-代码/后端/api/admin.py` 里有 `_抽取缓存` 的**路径映射常量**，搬移会打断后台「抽取产物」查看；")
lines.append("3. 论文、《25》《27》等文档有数十处按路径引用，搬移要同步改写并重跑跨文档核验。\n")
lines.append("因此本项目的既有口径是：**数据留在产生它的阶段目录，用「本总册 ＋ 清单」做逻辑整合**（唯一入口、可校验、可复算）。\n")
lines.append("> 若确实需要一份「拷贝式打包」（用于交付或归档），可另建 `交付物/04-数据与知识图谱/数据集打包/`，")
lines.append("> 只拷贝交付级真值（约 %.0f MB）、保留原路径不动，并把两份的 SHA-256 一起登记。" % (truth / 1048576))
open(OUT_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")
print("已生成：")
print("  ", OUT_MD)
print("  ", OUT_JS)
print("数据资产合计 %.1f MB；交付级真值 %.1f MB" % (tot / 1048576, truth / 1048576))
