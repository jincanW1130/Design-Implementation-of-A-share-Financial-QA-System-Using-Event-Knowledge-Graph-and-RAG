# -*- coding: utf-8 -*-
"""拼装第十一阶段论文（第 11 阶段交付物《29》）。

职责
----
把 `交付物/01-论文\\_分章源文件\\` 下的分章源文件按**固定顺序**拼装为
`交付物/01-论文\\29-第11阶段产出文档（毕业论文）.md`。

硬性要求（与《28-第11阶段任务书》的验收标准对应）
--------------------------------------------------
1. **确定性**：同一输入两次运行，输出逐字节一致。脚本内不写任何时间戳、
   临时路径、随机数或运行环境信息；产出文档的版本信息块为固定字面量。
2. **编码与换行**：UTF-8 无 BOM、LF 换行。
3. **文首**：题目 ＋ 版本信息块。
4. **文末**：修订记录位（固定表格，含本版行）。
5. 产出文档**由脚本生成**，不得手改；`--check` 档用于核对磁盘上的《29》
   是否与一次现场拼装逐字节一致（供门禁 static 档使用）。

用法
----
    python 工具\\拼装第十一阶段论文.py            # 生成《29》，打印字节数与 sha256
    python 工具\\拼装第十一阶段论文.py --check    # 只核对，不写盘；一致退出码 0
"""

import argparse
import hashlib
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC_DIR = os.path.join(ROOT, "交付物/01-论文", "_分章源文件")
OUT_REL = os.path.join("交付物/01-论文", "29-第11阶段产出文档（毕业论文）.md")
OUT = os.path.join(ROOT, OUT_REL)

# 拼装顺序＝分章源文件名的字典序（00 → 01 → … → 07 → 90 → 91），
# 这里显式列出，避免目录枚举顺序随文件系统变化而改变产出。
ORDER = [
    "00-前置.md",
    "01-第一章-绪论.md",
    "02-第二章-相关技术.md",
    "03-第三章-系统需求分析.md",
    "04-第四章-系统设计.md",
    "05-第五章-系统实现.md",
    "06-第六章-系统测试与实验分析.md",
    "07-第七章-总结与展望.md",
    "90-参考文献.md",
    "91-致谢.md",
]

TITLE = "基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现"

HEADER = """# {title}

> 本文是第 11 阶段（论文撰写与材料整理）的**交付文档**，落点 `交付物/01-论文/29-第11阶段产出文档（毕业论文）.md`。
> 本文件**由 `工具/拼装第十一阶段论文.py` 按分章源文件的固定顺序生成，不得手改**；改动请改 `交付物/01-论文/_分章源文件/` 下的对应源文件后重跑拼装脚本。

| 项 | 取值 |
| --- | --- |
| 文档编号 | `29-`（第 11 阶段交付物；《28-第11阶段任务书（论文撰写与材料整理）》第 4 节 产出清单） |
| 所属阶段 | 第 11 阶段：论文撰写与材料整理 |
| 文档版本 | v1.0 |
| 载体形态 | Markdown 全文草稿 ＋ 分章源文件（**本次不产 Word**；格式待学校模板下发后灌入，见任务书第 6 节 格式决策） |
| 章节目录依据 | 《02-项目执行总控文档》第十五节「论文目录」（一级与二级标题逐字一致，未增删） |
| 拼装顺序 | 00 前置 → 01 第一章 → 02 第二章 → 03 第三章 → 04 第四章 → 05 第五章 → 06 第六章 → 07 第七章 → 90 参考文献 → 91 致谢 |
| 读数口径 | 抽取读数一律为「**模型参照集口径下的抽取表现**」；问答读数一律为「**模型评分口径（跨厂商模型评审）**」；正式全量实验（120 题 × 6 组）**已运行完成**，第六章 6.7～6.10 已按该落点的正式读数回填；正式集的问答质量评分（模型评分口径）**已完成**（582 条有效答案，6.8.1 已填入五组三维度均值、0／1／2 分布、跨模型一致率与调用账），《02》第12.8节 合取判定的后半句在核心 108 题的三个子集上**全部成立** |
| 术语口径 | 涉及该组件时一律写「向量索引」或「向量检索组件」；被禁的四字连写术语全文 0 命中 |

---

"""

FOOTER = """
---

# 修订记录

> 本表由作者维护；`工具/拼装第十一阶段论文.py` 每次重跑都会原样重排本表所在区块的模板，**修订单本身写在分章源文件或本表内**，并按任务书第十一节 的修订规则留痕。

| 版本 | 日期 | 修订内容 |
| --- | --- | --- |
| v1.0 | 2026-10-07 | 初版：按《02》第十五节「论文目录」写出一级与二级标题；完成前置（题目／摘要／关键词／Abstract／Keywords）、第一章至第五章、第六章 6.1～6.6 与第七章正文；第六章 6.7～6.10 留为带明确 TODO 的骨架（正式全量实验未运行，不预填任何读数）；参考文献 22 篇按 GB/T 7714—2015 著录；第一次拼装由 `工具/拼装第十一阶段论文.py` 生成。 |
| v1.1 | 2026-10-08 | 正式全量实验（120 题 × 6 组）完成后回填第六章 6.7～6.10 四节（检索实验／问答对比实验／消融实验／失败案例分析）：填入三段口径（全部 120／核心 108／压力 12）的有效题数、五组四项检索指标、逐子集读数、消融逐项效果、C→D 与 D→E 的逐题比对、失败题清单与分母口径、六类失败归因的代理判据与复算命令；6.8 节如实登记正式集问答质量评分为待补（模型评分口径尚未执行）；同步《00-前置》的摘要与 Abstract（保留原句为成文时点留痕，另起回填登记段）；被禁四字连写术语仍为 0 命中。 |
| v1.2 | 2026-10-09 | **正式集问答质量评分完成后回填第六章 6.8 与 6.10、第七章三问三假设的终局结论、以及摘要与 Abstract。** ① **6.8.1 由「待补」改为实测回填**：五组 × 三维度均值（表 6-13）与 0／1／2 分布（表 6-14～6-16）、跨模型一致率（表 6-17）、不一致复核与最终分（表 6-18）、调用与 token 账（表 6-19）、《02》第12.8节 三子集完整判定（表 6-20）与六条连读限制；表 6-21／6-22 为 6.8.2 的范围受限对照、6.9 与后续表号顺延为表 6-23／6-24。② **6.8.2 显式写成与正式集方向相反**（预实验集 A 组最高、正式集 C 组高于 A 组），两套读数并存不可混引。③ **6.10 的 ⑤ 类补齐**：模型评分口径下 Faithfulness 判 0 分 0 条／判 1 分 20 条（16 道不同题号）逐条清单（表 6-25）与可复算命令，正式集与 30 题预实验集两批读数分列。④ **第七章**：RQ2 两半都已给出、H1 改为「成立」、H2 两半都可判定、H3 不判定状态不变而措辞与模型口径对齐；第三部分第一条的登记改为「已完成」、展望首条换为「把本次评分做成可复现的复评」。⑤ 被禁四字连写术语仍为 0 命中；评分口径一律为模型口径，无任何正向人工口径表述。 |
| v1.3 | 2026-10-10 | **第三章 3.3 增补正式 UML 用例图（图 3-1）**：① 新增配图 `交付物/09-图表/第3阶段图/图3-1-系统用例图.png`（同目录含手绘 SVG 源 `图3-1-系统用例图.svg` 与渲染脚本 `_渲染.py`：playwright（msedge、无头）渲染、DPR 3.5、白底、图题绘在图上、渲染过程不联网）与正文引用（说明句＋`![图 3-1 …]`＋居中图注，图注含 PNG 相对路径）；图的内容＝两类参与者、UC-01～UC-07 七个用例与 UC-07 对 UC-01／UC-04 的 «extend» 条件性扩展（条件与范围注明在图的注释框内），与《07》第四节 的用例定义逐条一致。② **`工具/验收第11阶段.py` 的 E3 判据随之重基线：8 条 → 9 条**（判据更严、非放宽；`MIRROR_PNGS` 与自检用例同步补入图 3-1，**反例 18 → 19**，只增不减），《28》第八节 E3 行、硬约束 9 与格式决策 8 同步更新（见《28》修订记录 v1.4）。③ 除 3.3 的一处插入外，其余分章源文件**一字未改**；文首版本信息块其余字段未改；被禁四字连写术语仍为 0 命中。 |
"""


def _read_text(path):
    """读入源文件：UTF-8（容忍 BOM），换行统一为 LF，去掉尾部空行。"""
    with open(path, "rb") as fh:
        raw = fh.read()
    text = raw.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n")


def build():
    """返回 (文本, [(文件名, 字节数, sha256前12位)])；纯函数，无副作用。"""
    parts = [HEADER.format(title=TITLE).rstrip("\n")]
    stats = []
    for name in ORDER:
        path = os.path.join(SRC_DIR, name)
        if not os.path.isfile(path):
            raise SystemExit("缺少分章源文件：%s" % os.path.join(SRC_DIR, name))
        text = _read_text(path)
        if not text:
            raise SystemExit("分章源文件为空：%s" % name)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
        stats.append((name, len(text.encode("utf-8")), digest))
        parts.append(text)
    parts.append(FOOTER.strip("\n"))
    doc = "\n\n".join(parts) + "\n"
    return doc, stats


def main(argv=None):
    ap = argparse.ArgumentParser(description="拼装第 11 阶段论文（《29》）")
    ap.add_argument("--check", action="store_true",
                    help="只核对磁盘上的《29》是否与现场拼装逐字节一致，不写盘")
    ap.add_argument("--out", default=None,
                    help="覆盖产出路径（用于确定性与门禁核对；缺省写《29》的固定落点）")
    args = ap.parse_args(argv)

    out_path = OUT if args.out is None else os.path.abspath(args.out)
    doc, stats = build()
    data = doc.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()

    print("拼装源目录：%s" % os.path.relpath(SRC_DIR, ROOT).replace(os.sep, "/"))
    print("分章源文件 %d 份：" % len(stats))
    for name, size, dg in stats:
        print("  %-34s %7d 字节  sha256:%s…" % (name, size, dg))
    print("产出文件：%s" % OUT_REL.replace(os.sep, "/"))
    print("产出规模：%d 字节（%d 行）" % (len(data), doc.count("\n")))
    print("产出 sha256：%s" % digest)
    print("编码：UTF-8 无 BOM；换行：LF；含时间戳/随机量：否（确定性拼装）")

    if args.check:
        if not os.path.isfile(OUT):
            print("核对结果：FAIL —— 产出文件不存在")
            return 1
        with open(OUT, "rb") as fh:
            on_disk = fh.read()
        if on_disk == data:
            print("核对结果：OK —— 磁盘上的《29》与现场拼装逐字节一致")
            return 0
        print("核对结果：FAIL —— 磁盘上的《29》与现场拼装不一致"
              "（磁盘 %d 字节 / sha256:%s）"
              % (len(on_disk), hashlib.sha256(on_disk).hexdigest()))
        return 1

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as fh:
        fh.write(data)
    print("已写出：%s" % (OUT_REL.replace(os.sep, "/") if args.out is None
                        else os.path.relpath(out_path, ROOT).replace(os.sep, "/")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
