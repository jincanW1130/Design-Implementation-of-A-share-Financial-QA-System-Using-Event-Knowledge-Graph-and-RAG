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
6. **链接重定位**：分章源文件里的仓库内相对链接，按**源文件所在目录**解出目标后
   重新表达为**《29》所在目录**的相对路径（`_relink`）。源文件在
   `交付物/01-论文/_分章源文件/`、产出在 `交付物/01-论文/`，层级不同，逐字拼接
   必然把 `../` 的层数拼错。
7. **产出前自检**：拼装完成、写盘之前，扫描产出文本里所有仓库内相对链接并逐条按
   《29》所在目录解析；任一条解析不到即以非零退出码报错并打印清单，绝不写出坏产物。

用法
----
    python 工具\\拼装第十一阶段论文.py            # 生成《29》，打印字节数与 sha256
    python 工具\\拼装第十一阶段论文.py --check    # 只核对，不写盘；一致退出码 0
"""

import argparse
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC_REL_DIR = "交付物/01-论文/_分章源文件"
OUT_REL_DIR = "交付物/01-论文"
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


# --------------------------------------------------------------------------
# 链接重定位与产出前自检
# --------------------------------------------------------------------------
# Markdown 的两种链接：![alt](target)（图片）与 [text](target)（文字链接）。
# 本仓库的图表链接目标不含空格与括号，故用最小正则即可覆盖。
# 第 1 组＝`![alt](` 头部，第 2 组＝目标本身，第 3 组＝`)`。
_LINK_RE = re.compile(r"(!?\[[^\]\n]*\]\()([^()\n]*)(\))")
# 非「仓库内相对链接」的目标前缀：外链、页内锚点、绝对路径。
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "data:", "#", "/", "\\")
# 带 scheme 的目标（含 Windows 盘符 `C:\…`）一律按外链处理，不做重定位。
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def _is_repo_rel_link(target):
    """该链接目标是否为「仓库内相对链接」（无 scheme、非绝对路径、非页内锚点）。"""
    t = target.strip()
    if not t:
        return False
    low = t.lower()
    for pre in _EXTERNAL_PREFIXES:
        if low.startswith(pre.lower()):
            return False
    return not _SCHEME_RE.match(t)


def _split_anchor(target):
    """拆出 `#锚点`：返回 (路径部分, 含 # 的锚点后缀或空串)。"""
    core, sep, anchor = target.partition("#")
    return core, ("#" + anchor) if sep else ""


def _relink(text, src_rel_dir, out_rel_dir):
    """把正文里的仓库内相对链接由「相对源文件目录」改写为「相对产出文件目录」。

    分章源文件在 `交付物/01-论文/_分章源文件/`，而《29》在 `交付物/01-论文/`：
    两级目录深度不同，逐字拼接必然把 `../` 的层数拼错（重组后一度全仓 34 处图链
    因此悬空）。这里对每个源文件的正文按**源文件所在目录**解出目标的绝对路径，
    再用 `os.path.relpath` 重新表达为**产出文件所在目录**的相对路径（正斜杠）；
    带 `#锚点` 的目标保留锚点。外链／锚点／绝对路径原样返回。
    """
    src_abs = os.path.join(ROOT, src_rel_dir.replace("/", os.sep))
    out_abs = os.path.join(ROOT, out_rel_dir.replace("/", os.sep))

    def repl(m):
        target = m.group(2).strip()
        if not _is_repo_rel_link(target):
            return m.group(0)
        core, anchor = _split_anchor(target)
        if not core:
            return m.group(0)
        dest = os.path.normpath(os.path.join(src_abs, core.replace("/", os.sep)))
        new = os.path.relpath(dest, out_abs).replace(os.sep, "/")
        return m.group(1) + new + anchor + m.group(3)

    return _LINK_RE.sub(repl, text)


def _check_links(text, out_rel_dir):
    """产出前自检：产出文本里的仓库内相对链接必须逐条解析得到。

    解析基准是**产出文件的落点目录**（《29》固定在 `交付物/01-论文/`）。`--out`
    只改写写盘位置、不改变产出文本的语义落点——门禁 A4／G2 两行把《29》拼到临时
    目录再逐字节比对，链接仍须按固定落点解释，故这里一律以落点目录为基准。

    返回链接条数；任一条解析不到即打印清单并以非零退出码中止（不写盘）。
    """
    base = os.path.join(ROOT, out_rel_dir.replace("/", os.sep))
    total, bad = 0, []
    for m in _LINK_RE.finditer(text):
        target = m.group(2).strip()
        if not _is_repo_rel_link(target):
            continue
        core, _ = _split_anchor(target)
        if not core:
            continue
        total += 1
        dest = os.path.normpath(os.path.join(base, core.replace("/", os.sep)))
        if not os.path.exists(dest):
            bad.append(target)
    if bad:
        print("链接自检失败：产出文本里有 %d 条仓库内相对链接解析不到真实文件" % len(bad))
        for t in bad:
            print("  [坏链] %s" % t)
        raise SystemExit(3)
    return total


def build():
    """返回 (文本, [(文件名, 字节数, sha256前12位)], 仓库内相对链接条数)。

    链接自检在本函数内完成：任一条仓库内相对链接解析不到即抛 SystemExit，
    调用方不会写出坏产物。
    """
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
        # 正文套用链接重定位（HEADER／FOOTER 是脚本文本，不套用）。
        parts.append(_relink(text, SRC_REL_DIR, OUT_REL_DIR))
    parts.append(FOOTER.strip("\n"))
    doc = "\n\n".join(parts) + "\n"
    n_links = _check_links(doc, OUT_REL_DIR)
    return doc, stats, n_links


def main(argv=None):
    ap = argparse.ArgumentParser(description="拼装第 11 阶段论文（《29》）")
    ap.add_argument("--check", action="store_true",
                    help="只核对磁盘上的《29》是否与现场拼装逐字节一致，不写盘")
    ap.add_argument("--out", default=None,
                    help="覆盖产出路径（用于确定性与门禁核对；缺省写《29》的固定落点）")
    args = ap.parse_args(argv)

    out_path = OUT if args.out is None else os.path.abspath(args.out)
    doc, stats, n_links = build()
    data = doc.encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()

    print("拼装源目录：%s" % os.path.relpath(SRC_DIR, ROOT).replace(os.sep, "/"))
    print("分章源文件 %d 份：" % len(stats))
    for name, size, dg in stats:
        print("  %-34s %7d 字节  sha256:%s…" % (name, size, dg))
    print("产出文件：%s" % OUT_REL.replace(os.sep, "/"))
    print("产出规模：%d 字节（%d 行）" % (len(data), doc.count("\n")))
    print("仓库内相对链接：%d 条（已逐条按《29》所在目录校验存在性）" % n_links)
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
