# -*- coding: utf-8 -*-
"""第 11 阶段（论文撰写与材料整理）专项验收门禁。

逐行实现《28-第11阶段任务书（论文撰写与材料整理）》第八节的验收标准
（A～G 七组、共 23 行）。**行号、标题与判据在运行时从《28》第八节解析**，
解析集合与脚本注册集合不一致即按退出码 2 退出（防「文档改了、脚本没跟上」）。

用法
----
    python 工具\\验收第11阶段.py                     # full 档：23 行逐行判；退出码 0／1／2
    python 工具\\验收第11阶段.py --profile static    # 不实跑子进程；实况行记 UNRUN；退出码 2
    python 工具\\验收第11阶段.py --selftest          # 临时镜像 ＋ 定向篡改反例，逐例比对

退出码
------
    0  full 档 23 行全部 [OK]
    1  有内容失败
    2  有检查项未执行（static 档／环境未就绪／行结构错误／自检未通过）

约束：零大模型 API 调用、零联网；除 selftest 的临时镜像外不写工作区任何文件。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:                                                        # GBK 控制台 → UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                           # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# 子进程环境：显式注入 PYTHONIOENCODING=utf-8。
# 默认（无环境变量）时父进程的 stdout 是管道 ⇒ Python 按 locale（cp936／GBK）编码，
# 子进程同样按 GBK 写管道、父进程按 utf-8 解码 ⇒ 全是替换字符，判据 A4 会误判 FAIL。
# 父子两侧编码一致后，子进程中文输出才能被父进程正确读取并匹配「核对结果：OK」。
def subenv(extra=None):
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    if extra:
        e.update(extra)
    return e


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

TASKBOOK_REL = "交付物/01-论文/28-第11阶段任务书（论文撰写与材料整理）.md"
PAPER_REL = "交付物/01-论文/29-第11阶段产出文档（毕业论文）.md"
SRC_REL = "交付物/01-论文/_分章源文件"
ASSEMBLER_REL = "工具/拼装第十一阶段论文.py"
MASTER_REL = "02-项目执行总控文档.md"
PROPOSAL_REL = "交付物/08-文献与开题/文献调研与开题/04-开题报告.md"
EXTRACT_JSON_REL = "交付物/06-实验与评测/抽取评测/抽取评测指标.json"
NFR_JSON_REL = "交付物/06-实验与评测/系统指标/NFR_readings.json"

# 「被禁的四字连写术语」按既有门禁的同一做法**拼接构造**，避免脚本自身成为命中源。
BANNED = "向量" + "数据库"

SOURCE_ORDER = [
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

FIG_IDS = ["图 4-%d" % i for i in range(1, 9)]
TAB_IDS = ["表 4-%d" % i for i in range(1, 14)]

# 抽取侧「头条读数」：出现在哪一小节，该小节就必须带「模型参照集口径」限定语。
EXTRACT_TOKENS = ["0.5360", "0.0972", "0.1202", "0.3947",
                  "0.5631", "0.4348", "0.4439"]

# 问答/评分侧的口径限定语与「不得出现正向人工口径」的表述集合。
CALIBER_MODEL_SCORE = "模型评分口径"
CALIBER_MODEL_REF = "模型参照集口径"
HUMAN_POSITIVE_TOKENS = ["人工金标准", "作者评分", "人工评分",
                         "评分者一致性", "评分信度", "评分稳定性",
                         # 以下两串是"把模型口径误写成人工口径"时的典型产物（例如把
                         # 「模型评分口径下的准确率」整体替换为「人工评分口径下的准确率」）：
                         # 它们本身就是"以人工为对照物"的正向表述，故并入同一禁列。
                         "人工标注口径", "人工评分口径"]
NEGATION_MARKERS = ["不得", "不能", "不是", "不存在", "未", "非", "缺少",
                    "不采用", "不构成", "推进到", "补充", "待", "TODO"]

# 6.7～6.10 四节：正式全量读数回填后的判据（2026-10-08 重基线；原判据「四节内无任何
# 指标读数」与「各含 ≥3 条 TODO」绑在「正式全量未运行」这一已到期的事实上，见《28》第八节）。
SKELETON_SECTIONS = ["6.7 检索实验", "6.8 问答对比实验",
                     "6.9 消融实验", "6.10 失败案例分析"]
METRIC_DECIMAL = re.compile(r"\d+\.\d{3,}")
# 指标读数不得是"拍脑袋的数"：本值域＝四项检索指标（Recall@K／Precision@K／MRR／
# Complete Evidence Recall@K）在文本块级口径下的全部可能取值区间——最低一档是
# Precision@K 在 120 题口径下的小值（0.0778 一级），再往下就不是本作用域内的量了。
# 大于 1 的数则是 0／1／2 量表的均值（如答案准确性）或耗时，由节内标注的来源文件
# 承担溯源；错误码 3004 之类的整型读数不含小数点，天然不落入本判据。
MIN_METRIC_VALUE, MAX_METRIC_VALUE = 0.02, 1.00
# 跨模型一致率里的 **平均绝对差（MAD）** 一类读数可以低于上面那个下限：它是两家 judge
# 在同一量表上逐条差值的均值，值域天然贴近 0（实测 0.0084／0.0924），与"四项检索指标
# 在文本块级口径下的可能取值区间"不是同一个量。**这不是放宽判据**：凡落在下面这个更窄
# 值域里的读数，一律**必须同时**在节内标注的已登记来源文件中逐字命中（ALLOW_SMALL_TOKENS
# 之外的小值仍然按原下限判 FAIL），比只查复算池更严。
SMALL_METRIC_MIN = 0.005
ALLOW_SMALL_TOKENS = ("0.0084", "0.0168")
# 图谱来源证据的"每题（块）"、每题证据条数均值等计数类读数允许超过 1
MAX_COUNT_VALUE = 12.00
ROUND_DIGITS = (3, 4, 5, 6)
TOLERANCE = 5e-7
# 复算源与溯源来源（均为只读的已落盘产物）
CMP_DIR_REL = "交付物/06-实验与评测/对照产出_正式"
TRACE_REL_TMPL = CMP_DIR_REL + "/%s/answer_trace.jsonl"
QSET_REL = "交付物/06-实验与评测/测试集/questions.jsonl"
REPORT_REL = CMP_DIR_REL + "/A_vs_C_对照报告.md"
REPORT_JSON_REL = CMP_DIR_REL + "/A_vs_C_对照.json"
QA_SCORE_REL = "交付物/06-实验与评测/问答评分/问答评分报告.md"
# 正式集问答质量评分报告：6.8.1 的五组三维度均值、0／1／2 分布、跨模型一致率与 12.8 判定
# 逐项取自该文件；F4 重基线（2026-10-09）后它是 6.8 节的**注册溯源来源**，故列入白名单。
QA_SCORE_FORMAL_REL = "交付物/06-实验与评测/问答评分_正式/问答评分报告.md"
# 同上报告的机读汇总（五组均值、12.8 判定逐子集读数、跨模型一致率、调用账）：
# 6.8.1 的派生量（如 12.8 判定表里 C 组减 A 组的差值）由它现场复算，故一并登记为只读来源。
QA_SCORE_SUMMARY_REL = "交付物/06-实验与评测/问答评分_正式/评分汇总.json"
# 30 题预实验集的对照报告：6.8 节引用该批评分读数、6.7 节点明预实验集与正式集的方向差异，
# 后者是"并存不可混引"的另一半，故一并作为可标注的溯源来源。
PRE_REPORT_REL = "交付物/06-实验与评测/对照产出_v13/A_vs_C_对照报告.md"
# 图谱导出物与正式题集：6.10 节的①类计数（锚定／未锚定）直接由图谱边表与题集算出，
# 故这两个只读产物同样作为可标注的溯源来源。
GRAPH_EDGES_REL = "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/edges.csv"
SRC_WHITELIST = (REPORT_REL, REPORT_JSON_REL, QA_SCORE_REL, QA_SCORE_FORMAL_REL,
                 PRE_REPORT_REL, GRAPH_EDGES_REL, QSET_REL)
# 三段口径 → 报告落点标识（见《02》第12.2节）
RANGE_IDS = {"all": "全部120", "core": "核心108", "stress": "压力12"}
# 6.7～6.10 里「回填未完成」的显式占位与已失效的时点断言（命中即 FAIL）
STALE_MARKERS = [
    "TODO-6.7-", "TODO-6.8-", "TODO-6.9-", "TODO-6.10-",
    "待正式全量实验完成后撰写",
    "正式全量实验未运行",
    "尚未运行，本节",
]
# 6.8 问答对比实验里已到期的时点断言（2026-10-09 F4 重基线新增，只作用于 6.8 节）。
# 正式集问答质量评分完成后，6.8.1／6.8.2／6.8.3 三节都不得再出现这些只属于"未评分"
# 阶段的话；6.1 节的时点留痕段落不在本节范围内，故不受影响。
STALE_6_8_MARKERS = [
    "尚未执行",
    "该位置如实登记为待补",
    "6.8.1 的待补读数",
]
# 正式集问答质量评分报告里「五组 × 三维度均值」主表的表头片段（用于现场解析来源文件）。
# 取"三维度总览（均值）"表（第五节之前的那张，A～E 五组齐备）；只比对前四列，
# 报告末列一旦增删本判据仍能定位。
QA_FORMAL_TABLE_HEADER = "| 组 | Answer Accuracy | Completeness | Faithfulness |"

# 规模读数 → 声明的出处文件（逐个交叉核对）。
SCALE_TRACE = [
    ("709", "交付物/04-数据与知识图谱/数据准备/13-数据准备（第五阶段）.md"),
    ("5018", "交付物/04-数据与知识图谱/数据准备/13-数据准备（第五阶段）.md"),
    ("105", "交付物/04-数据与知识图谱/数据准备/13-数据准备（第五阶段）.md"),
    ("3607", "交付物/04-数据与知识图谱/事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md"),
    ("3614", "交付物/04-数据与知识图谱/事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md"),
    ("1098", "交付物/04-数据与知识图谱/事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md"),
    ("544", "交付物/04-数据与知识图谱/事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md"),
    ("249", "交付物/06-实验与评测/27-第10阶段产出文档（系统测试与对比实验）.md"),
    ("121", "交付物/03-代码/测试/README.md"),
    ("44", "交付物/05-系统实现/前后端系统集成/25-第9阶段产出文档（前后端系统集成）.md"),
]

# 跨文档核验允许的两项登记（其余一律 FAIL）
CROSSDOC_ALLOWED = [
    "计划外的阶段目录",
    "带号文档均已登记",
]

# 计划行：行号、标题、判据（运行时与《28》第八节解析结果逐行比对）
ROWS = [
    ("A1", "《29》存在且含题目与版本信息块、文末含修订记录位"),
    ("A2", "分章源文件 10 份齐备且与拼装顺序表一致"),
    ("A3", "《29》与 10 份源文件均为 UTF-8 无 BOM、LF 换行"),
    ("A4", "磁盘上的《29》与现场拼装逐字节一致（实跑 --check 退出码 0）"),
    ("B1", "一级标题（七章）与《02》第十五节 逐条一致且顺序一致"),
    ("B2", "二级标题（43 节）与《02》第十五节 逐条一致且顺序一致"),
    ("C1", "出现抽取头条读数处，同小节内必带「模型参照集口径」限定语"),
    ("C2", "出现「准确率」处必带「模型评分口径／模型参照集口径」或为否定／待补语境"),
    ("C3", "无正向人工口径表述（相关表述只允许出现在否定或限定语境）"),
    ("D1", "被禁的四字连写术语 0 命中"),
    ("D2", "参考文献 22 篇且与《04》第十一节 逐条一致"),
    ("D3", "正文引用编号 ⊆ [1]～[22]，且 22 条编号全部被引用"),
    ("E1", "图 4-1～图 4-8 全部被引用"),
    ("E2", "表 4-1～表 4-13 全部被引用"),
    ("E3", "9 条图注 PNG 相对路径与 9 条正文图片链接均真实存在"),
    ("F1", "抽取 F1 读数可在《抽取评测指标.json》中逐项找到"),
    ("F2", "NFR 读数可在《NFR_readings.json》中逐项找到"),
    ("F3", "规模读数可在声明的源文件中逐个找到"),
    ("F4", "6.7～6.10 四节已按正式全量读数回填，且每个读数可复算／可溯源"),
    ("G1", "6.7～6.10 四节齐备、无未回填占位、逐子集 CER 已按现行留痕重算、D/E 集合比对成立"),
    ("G2", "拼装确定性：连跑两次产出逐字节一致，且与磁盘《29》一致"),
    ("G3", "写范围自检：阶段十一目录只含《28》《29》、分章源文件目录与提交件目录"),
    ("G4", "跨文档核验 --strict-citations 的失败项 ⊆ 两项登记"),
]

SUBPROCESS_ROWS = {"A4", "G2", "G4"}     # static 档不实跑的行


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
class Ctx(object):
    def __init__(self, root, profile):
        self.root = root
        self.profile = profile
        self._cache = {}

    def p(self, rel):
        return os.path.join(self.root, rel.replace("/", os.sep))

    def text(self, rel):
        """读入文本（UTF-8、去 BOM、换行归一为 LF）。

        缓存按**内容指纹**失效：同一个 Ctx 复用期间，只要文件字节变了，
        下一次调用就会重读；文件被删掉再把旧的文本吐出来也不可能发生。
        （旧实现按路径缓存且永不失效，导致自检里「改源文件 + 重跑拼装」类
        反例在同一次运行内读到的永远是基线文本，实测失败集恒为空。）
        """
        path = self.p(rel)
        if not os.path.isfile(path):
            self._cache.pop(rel, None)
            return None
        with io.open(path, "rb") as fh:
            raw = fh.read()
        fp = hashlib.sha256(raw).hexdigest()
        hit = self._cache.get(rel)
        if hit is not None and hit[0] == fp:
            return hit[1]
        t = raw.decode("utf-8", "replace")
        if t.startswith("\ufeff"):
            t = t[1:]
        t = t.replace("\r\n", "\n").replace("\r", "\n")
        self._cache[rel] = (fp, t)
        return t

    def raw(self, rel):
        path = self.p(rel)
        if not os.path.isfile(path):
            return None
        with io.open(path, "rb") as fh:
            return fh.read()


def paper(ctx):
    return ctx.text(PAPER_REL) or ""


def sections(text):
    """按一级／二级标题切块：返回 [(标题, 正文), …]（# 与 ## 同级切分）。"""
    out, cur_title, cur = [], "<前言>", []
    for line in text.split("\n"):
        if re.match(r"^#{1,2}\s+\S", line):
            out.append((cur_title, "\n".join(cur)))
            cur_title, cur = line.lstrip("#").strip(), []
        else:
            cur.append(line)
    out.append((cur_title, "\n".join(cur)))
    return out


def head_title(sec_title):
    """去掉标题行里可能带的 '#' 前缀（已剥离）；用于匹配小节名。"""
    return sec_title.strip()


def parse_master_toc(ctx):
    """从《02》第十五节 解析 (章列表, 节列表)。"""
    t = ctx.text(MASTER_REL)
    if not t:
        return None, None, "《02》缺失"
    m = re.search(r"^##\s*十五、论文目录\s*$", t, re.M)
    if not m:
        return None, None, "《02》未找到「十五、论文目录」"
    seg = t[m.end():]
    m2 = re.search(r"^##\s*十六、", seg, re.M)
    if m2:
        seg = seg[:m2.start()]
    # 章标题的章号体例：2026-10-10 起论文按学校模板改为**阿拉伯数字**（`第1章 绪论`），
    # 故此处同时接受两种体例（`第[一二三四五六七]章` 与 `第\d章`）。
    # **判据强度未变**：仍是"抽出来的这串文本必须与《29》逐条、按顺序完全一致"，
    # 只是把"章号的写法"这一**成文时的形态假设**放开；配合 _toc_compare 里新增的
    # "解析结果不得为空"守卫，空转通过的口子也被堵上（见那里的注释）。
    ch = re.findall(r"^###\s*(第(?:[一二三四五六七]|\d)章\s*\S.*?)\s*$", seg, re.M)
    sec = re.findall(r"^-\s*(\d\.\d\s+\S.*?)\s*$", seg, re.M)
    return ch, sec, ""


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# A 组：交付形态
# --------------------------------------------------------------------------
def a1(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在或为空：%s" % PAPER_REL
    missing = []
    if "基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现" not in t.split("\n")[0]:
        missing.append("文首题目")
    for key in ("| 文档编号 |", "| 文档版本 |", "| 拼装顺序 |"):
        if key not in t:
            missing.append("版本信息块字段 %s" % key)
    if "# 修订记录" not in t:
        missing.append("文末修订记录位")
    if missing:
        return "FAIL", "缺：" + "、".join(missing)
    b = ctx.raw(PAPER_REL)
    return "OK", "《29》%d 字节（%d 行）；文首题目＋版本信息块＋文末修订记录位齐备" % (
        len(b), t.count("\n"))


def a2(ctx):
    d = ctx.p(SRC_REL)
    if not os.path.isdir(d):
        return "FAIL", "分章源文件目录不存在：%s" % SRC_REL
    have = sorted(f for f in os.listdir(d) if f.endswith(".md"))
    missing = [f for f in SOURCE_ORDER if f not in have]
    extra = [f for f in have if f not in SOURCE_ORDER]
    if missing or extra:
        return "FAIL", "缺 %s；多 %s" % (missing, extra)
    return "OK", "10 份齐备且与拼装顺序表一致：%s" % "、".join(SOURCE_ORDER[:3]) + " … " + SOURCE_ORDER[-1]


def a3(ctx):
    bad = []
    targets = [PAPER_REL] + ["%s/%s" % (SRC_REL, f) for f in SOURCE_ORDER]
    for rel in targets:
        b = ctx.raw(rel)
        if b is None:
            bad.append("%s 缺失" % rel)
            continue
        if b.startswith(b"\xef\xbb\xbf"):
            bad.append("%s 带 BOM" % os.path.basename(rel))
        if b"\r" in b:
            bad.append("%s 含 CR" % os.path.basename(rel))
    if bad:
        return "FAIL", "；".join(bad)
    return "OK", "11 个文件均 UTF-8 无 BOM、LF 换行"


def a4(ctx):
    if ctx.profile == "static":
        return "UNRUN", "static 档不实跑子进程"
    script = ctx.p(ASSEMBLER_REL)
    if not os.path.isfile(script):
        return "FAIL", "拼装脚本缺失：%s" % ASSEMBLER_REL
    r = subprocess.run([sys.executable, script, "--check"], cwd=ctx.root,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=subenv())
    out = r.stdout.decode("utf-8", "replace")
    tail = [ln for ln in out.splitlines() if ln.startswith("核对结果")]
    if r.returncode == 0 and tail and tail[0].startswith("核对结果：OK"):
        return "OK", "实跑 `--check` 退出码 0；%s" % tail[0]
    return "FAIL", "实跑 `--check` 退出码 %d；%s" % (r.returncode,
                                                tail[0] if tail else out.strip()[-120:])


# --------------------------------------------------------------------------
# B 组：章节目录与《02》第十五节 一致
# --------------------------------------------------------------------------
def _toc_compare(ctx, which):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    ch02, sec02, err = parse_master_toc(ctx)
    if err:
        return "FAIL", err
    if which == "ch":
        got = re.findall(r"^#\s*(第(?:[一二三四五六七]|\d)章\s*\S.*?)\s*$", t, re.M)
        want = ch02
    else:
        got = re.findall(r"^##\s*(\d\.\d\s+\S.*?)\s*$", t, re.M)
        want = sec02
    # 守卫（2026-10-10 加严）：两侧**同时解析为空**时 `gn == wn` 会成立，判据就"空转通过"了
    # ——本次改章号体例（中文数字 → 阿拉伯数字）时实测到：旧正则两侧都解析不出，
    # 于是走进 OK 分支、在 `wn[0]` 上撞 IndexError 才暴露出来。**若无那次崩溃，这里会静默判 OK。**
    # 故先断言两侧都非空：判据必须真的作用在"七章"与"43 节"上，而不是作用在空列表上。
    if not want or not got:
        return "FAIL", "解析结果为空：《02》第十五节 %d 条 /《29》%d 条——判据失去作用对象" % (
            len(want), len(got))
    gn = [norm(x) for x in got]
    wn = [norm(x) for x in want]
    if gn == wn:
        return "OK", "逐条一致：%d 条（%s … %s）" % (len(wn), wn[0], wn[-1])
    diff = []
    for i in range(max(len(gn), len(wn))):
        a = wn[i] if i < len(wn) else "<缺>"
        b = gn[i] if i < len(gn) else "<缺>"
        if a != b:
            diff.append("#%d 《02》=%s / 《29》=%s" % (i + 1, a, b))
    return "FAIL", "《02》%d 条 / 《29》%d 条；首个不一致：%s" % (
        len(wn), len(gn), diff[0] if diff else "（数量不符）")


def b1(ctx):
    return _toc_compare(ctx, "ch")


def b2(ctx):
    return _toc_compare(ctx, "sec")


# --------------------------------------------------------------------------
# C 组：口径限定语
# --------------------------------------------------------------------------
def c1(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    hits = [tk for tk in EXTRACT_TOKENS if tk in t]
    if not hits:
        return "FAIL", "全文未出现任何抽取头条读数（%s）——判据失去作用对象" % EXTRACT_TOKENS[0]
    bad = []
    for title, body in sections(t):
        if not any(tk in body for tk in EXTRACT_TOKENS):
            continue
        if CALIBER_MODEL_REF not in body:
            bad.append(title)
    if bad:
        return "FAIL", "出现抽取读数但小节内无「%s」限定语：%s" % (CALIBER_MODEL_REF, "、".join(bad))
    return "OK", "出现抽取头条读数的小节全部带「%s」限定语（命中读数 %d 个）" % (
        CALIBER_MODEL_REF, len(hits))


def c2(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    if CALIBER_MODEL_SCORE not in t:
        return "FAIL", "全文未出现「%s」限定语" % CALIBER_MODEL_SCORE
    if CALIBER_MODEL_REF not in t:
        return "FAIL", "全文未出现「%s」限定语" % CALIBER_MODEL_REF
    bad = []
    for i, line in enumerate(t.split("\n"), 1):
        if "准确率" not in line:
            continue
        if CALIBER_MODEL_SCORE in line or CALIBER_MODEL_REF in line:
            continue
        if any(mk in line for mk in NEGATION_MARKERS):
            continue
        bad.append("L%d" % i)
    if bad:
        return "FAIL", "下列行出现「准确率」却无口径限定语、亦非否定／待补语境：%s" % "、".join(bad)
    return "OK", "全文 %d 处「准确率」均带口径限定语或处于否定／待补语境" % t.count("准确率")


def c3(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    bad = []
    for i, line in enumerate(t.split("\n"), 1):
        toks = [tk for tk in HUMAN_POSITIVE_TOKENS if tk in line]
        if not toks:
            continue
        if any(mk in line for mk in NEGATION_MARKERS):
            continue
        bad.append("L%d（%s）" % (i, "、".join(toks)))
    if bad:
        return "FAIL", "下列行出现正向人工口径表述：%s" % "、".join(bad)
    return "OK", "人工口径相关表述全部处于否定／限定语境"


# --------------------------------------------------------------------------
# D 组：术语与文献
# --------------------------------------------------------------------------
def d1(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    n = t.count(BANNED)
    if n:
        lines = [i for i, ln in enumerate(t.split("\n"), 1) if BANNED in ln]
        return "FAIL", "被禁术语命中 %d 处：L%s" % (n, "、L".join(map(str, lines[:5])))
    return "OK", "被禁术语 0 命中；允许写法在文（向量索引 %d 次、向量检索组件 %d 次）" % (
        t.count("向量索引"), t.count("向量检索组件"))


def _refs_from(text, pat):
    out = []
    for m in re.finditer(pat, text, re.M):
        out.append(norm(m.group(0)))
    return out


def d2(ctx):
    t = paper(ctx)
    p = ctx.text(PROPOSAL_REL)
    if not t:
        return "FAIL", "《29》不存在"
    if not p:
        return "FAIL", "《04-开题报告》缺失"
    m = re.search(r"^##\s*十一、参考文献\s*$", p, re.M)
    if not m:
        return "FAIL", "《04》未找到「十一、参考文献」"
    seg = p[m.end():]
    m2 = re.search(r"^###\s*参考文献著录说明", seg, re.M)
    if m2:
        seg = seg[:m2.start()]
    want = _refs_from(seg, r"^\[\d+\]\s*.*$")
    want = [re.sub(r"\s+", " ", x).strip() for x in want]
    got_all = _refs_from(t, r"^\[\d+\]\s*.*$")
    got = [re.sub(r"\s+", " ", x).strip() for x in got_all]
    if len(want) != 22:
        return "FAIL", "《04》第十一节 解析出 %d 条（期望 22）" % len(want)
    if got == want:
        return "OK", "参考文献 22 条与《04》第十一节 逐条逐字一致"
    if len(got) != len(want):
        return "FAIL", "条数不一致：《29》%d 条 / 《04》%d 条" % (len(got), len(want))
    for i, (a, b) in enumerate(zip(want, got)):
        if a != b:
            return "FAIL", "第 %d 条不一致：《04》=%s ／《29》=%s" % (i + 1, a[:60], b[:60])
    return "FAIL", "参考文献表不一致"


def d3(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    nums = sorted({int(x) for x in re.findall(r"\[(\d{1,2})\]", t)})
    if not nums:
        return "FAIL", "正文未出现任何形如 [n] 的引用编号"
    bad = [n for n in nums if n < 1 or n > 22]
    if bad:
        return "FAIL", "越界引用编号：%s" % bad
    miss = [n for n in range(1, 23) if n not in nums]
    if miss:
        return "FAIL", "22 条文献中有 %d 条未被正文引用：%s" % (len(miss), miss)
    return "OK", "正文引用编号集合恰为 [1]～[22]（22 条全部被引用）"


# --------------------------------------------------------------------------
# E 组：图表
# --------------------------------------------------------------------------
# 正文图片链接 ![alt](target)；第 1 组＝目标本身。目标不含空格与括号。
IMG_LINK_RE = re.compile(r"!\[[^\]\n]*\]\(([^()\n]*)\)")
# 非「仓库内相对目标」的前缀：外链、页内锚点、绝对路径。
LINK_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "data:", "#", "/", "\\")
# 带 scheme 的目标（含 Windows 盘符 `C:\…`）一律按外链处理。
LINK_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*:")


def _is_repo_rel_link(target):
    """该链接目标是否为「仓库内相对目标」（无 scheme、非绝对路径、非页内锚点）。"""
    t = target.strip()
    if not t:
        return False
    low = t.lower()
    for pre in LINK_EXTERNAL_PREFIXES:
        if low.startswith(pre.lower()):
            return False
    return not LINK_SCHEME_RE.match(t)


def _resolve_rel_link(base_dir, target):
    """把仓库内相对目标按 base_dir 解析为绝对路径（带 `#锚点` 时去锚点）。"""
    core = target.split("#", 1)[0].strip()
    if not core:
        return None
    return os.path.normpath(os.path.join(base_dir, core.replace("/", os.sep)))


def e1(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    miss = [f for f in FIG_IDS if f not in t]
    if miss:
        return "FAIL", "未被引用：%s" % "、".join(miss)
    hits = {f: t.count(f) for f in FIG_IDS}
    return "OK", "图 4-1～图 4-8 全部被引用；逐条次数 %s" % hits


def e2(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    miss = [f for f in TAB_IDS if f not in t]
    if miss:
        return "FAIL", "未被引用：%s" % "、".join(miss)
    return "OK", "表 4-1～表 4-13 全部被引用（13 张齐备）"


def e3(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    # ① 图注：反引号包裹的 `交付物/09-图表/…png`（仓库根相对）去重后恰 9 条，逐条存在
    paths = sorted(set(re.findall(r"`(交付物/09-图表/[^`\n]+\.png)`", t)))
    if len(paths) != 9:
        return "FAIL", "图注中声明的 PNG 路径为 %d 条（期望 9）" % len(paths)
    missing = [p for p in paths if not os.path.isfile(ctx.p(p))]
    if missing:
        return "FAIL", "下列 PNG 路径在磁盘上不存在：%s" % "、".join(missing)
    # ② 正文图片链接：![](...) 的仓库内相对目标按**《29》所在目录**逐条解析。
    #    2026-10-10 加严：旧判据只看图注里的反引号路径，正文 ![]() 全裂也照样给 OK
    #    （重组把 `../` 层数拼错后，9 条图注路径全都写得对、9 个正文链接全悬空）。
    #    现在要求：条数同为 9 条、逐条存在、且解析出的 PNG 与图注声明的 9 条是同一组。
    base = os.path.dirname(ctx.p(PAPER_REL))
    refs = [m.group(1).strip() for m in IMG_LINK_RE.finditer(t)]
    refs = [r for r in refs if _is_repo_rel_link(r)]
    if len(refs) != 9:
        return "FAIL", ("正文图片链接（![](...)）的仓库内相对目标为 %d 条（期望 9 条）"
                        % len(refs))
    bad, resolved = [], set()
    for r in refs:
        dest = _resolve_rel_link(base, r)
        if dest is None or not os.path.exists(dest):
            bad.append(r)
        else:
            resolved.add(os.path.relpath(dest, ctx.root).replace(os.sep, "/"))
    if bad:
        return "FAIL", ("下列正文图片链接按《29》所在目录解析不到真实文件：%s"
                        % "、".join(bad))
    if resolved != set(paths):
        return "FAIL", ("正文图片链接解析出的 PNG 与图注声明的 9 条不是同一组；"
                        "只在链接侧：%s；只在图注侧：%s"
                        % (sorted(resolved - set(paths))[:4],
                           sorted(set(paths) - resolved)[:4]))
    return "OK", "9 条图注 PNG 路径与 9 条正文图片链接全部真实存在（两侧为同一组 9 张图）"


# --------------------------------------------------------------------------
# F 组：读数溯源
# --------------------------------------------------------------------------
def _json(ctx, rel):
    b = ctx.raw(rel)
    if b is None:
        return None, "文件缺失：%s" % rel
    try:
        return json.loads(b.decode("utf-8")), ""
    except Exception as exc:      # noqa: BLE001
        return None, "JSON 解析失败：%s" % exc


def f1(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    data, err = _json(ctx, EXTRACT_JSON_REL)
    if err:
        return "FAIL", err
    pool = set()
    try:
        for seg in data["results"]["metrics"].values():
            for task in seg.values():
                for variant in task.values():
                    v = variant.get("f1")
                    if isinstance(v, (int, float)):
                        pool.add("%.4f" % v)
    except Exception as exc:      # noqa: BLE001
        return "FAIL", "抽取指标结构无法解析：%s" % exc
    bad = [tk for tk in EXTRACT_TOKENS if tk not in pool]
    if bad:
        return "FAIL", "下列读数在《抽取评测指标.json》里找不到对应值：%s" % bad
    return "OK", "7 个抽取 F1 读数逐项命中《抽取评测指标.json》（候选池 %d 个四位小数）" % len(pool)


def f2(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    data, err = _json(ctx, NFR_JSON_REL)
    if err:
        return "FAIL", err
    raw = json.dumps(data, ensure_ascii=False)
    toks = ["14.994", "37.048", "39.405", "7.312", "29.306", "31.773", "7.683", "8.091"]
    miss_doc = [tk for tk in toks if tk not in t]
    miss_src = [tk for tk in toks if tk not in raw]
    if miss_doc:
        return "FAIL", "《29》缺读数：%s" % miss_doc
    if miss_src:
        return "FAIL", "《NFR_readings.json》里找不到读数：%s" % miss_src
    if data.get("nfr02", {}).get("back_to_back_100", {}).get("other_failure") != 0:
        return "FAIL", "NFR-02 背靠背档的「其它失败」不为 0，本行判据的前提不成立"
    return "OK", "8 个 NFR-01 读数与 NFR-02 的「其它失败＝0」逐项命中《NFR_readings.json》"


def f3(ctx):
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    bad = []
    for tok, rel in SCALE_TRACE:
        src = ctx.text(rel)
        if src is None:
            bad.append("%s 的出处文件缺失（%s）" % (tok, rel))
        elif tok not in t:
            bad.append("%s 不在《29》中" % tok)
        elif tok not in src:
            bad.append("%s 在出处 %s 中找不到" % (tok, rel))
    if bad:
        return "FAIL", "；".join(bad)
    return "OK", "%d 组规模读数在《29》与声明的出处文件中双向命中" % len(SCALE_TRACE)


def _parse_mean_table(text, header):
    """从 markdown 文本里取「组 | 三个维度均值 | 条数」主表，返回 {组: [AA, Comp, Faith]}。

    header 为表头行的**逐字前缀**（本文件用 QA_FORMAL_TABLE_HEADER 指向正式集
    问答质量评分报告第三节的"三维度总览（均值）"表；该表的表头末列是已评条数，
    故这里只比对前三列，保证报告末列一旦增删本判据仍能定位）。表头行之后按 markdown
    表格行逐行取值：第一格取 A～E 组字母，其后三格取浮点；解析不到任何一行即返回
    空字典（由调用方判 FAIL）。
    """
    groups = {}
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith(header):
            start = i
            break
    if start is None:
        return groups
    for row in lines[start + 1:]:
        cells = [c.strip() for c in row.strip().strip("|").split("|")]
        if len(cells) < 4:
            if row.strip() and not row.strip().startswith("|"):
                break                      # 表格已结束
            continue
        g = cells[0].split()[0] if cells[0].split() else ""
        if g not in ("A", "B", "C", "D", "E"):
            if groups:
                break                      # 第一张表的 A～E 行已收齐，收工
            continue
        try:
            groups[g] = [float(cells[1]), float(cells[2]), float(cells[3])]
        except ValueError:
            continue
    return groups


def _f4_formal_qa(ctx, t, bodies):
    """F4 的第三组断言（2026-10-09 重基线新增）：正式集问答质量评分**真的**完成了。

    旧判据把"6.8 节不得出现正式集问答评分读数"绑在"该评分尚未执行"这一事实断言上；
    评分跑完并依法回填后，旧判据必然为假（见《28》第八节 F4 行与《02》v3.10 的
    B6／F6 段同款处置）。新判据不再看守空章节，而是逐条断言**新事实**：

    (a) 正式集问答质量评分报告必须存在于注册的溯源来源里（缺报告 ⇒ 无法断言）；
    (b) 6.8.1 的标题必须已由"待补"改为**已完成**，且 6.8 三节内不得再出现只属于
        "未评分"阶段的时点断言（STALE_6_8_MARKERS）；
    (c) 报告主表列出的**每一组**，其三维度均值必须**逐项出现在 6.8.1 的正文里**
        （正文不得只报一两组、也不得只报一个维度）；
    (d) 12.8 判定表的三个子集的 CER 与 Answer Accuracy **逐项与报告 JSON 的派生池同值**
        且已登记进 6.8.1 正文（判定表的读数必须能由冻结留痕与派生池算出，不是凭空写的）。

    返回 (ok, detail)；ok 为 True 时 detail 为结论句。
    """
    rep = ctx.text(QA_SCORE_FORMAL_REL)
    if not rep:
        return False, "正式集问答质量评分报告缺失：%s（无法断言 6.8 已完成）" % QA_SCORE_FORMAL_REL
    body = bodies.get("6.8 问答对比实验") or ""
    if "### 6.8.1" not in body:
        return False, "6.8 节缺 6.8.1 小节"
    head = body.split("### 6.8.2")[0]
    if "已完成" not in head:
        return False, "6.8.1 未登记为「已完成」（正式集问答质量评分已完成这一事实未回填）"
    stale = [mk for mk in STALE_6_8_MARKERS if mk in body]
    if stale:
        return False, "6.8 节残留只属于「未评分」阶段的时点断言：%s" % "、".join(stale)
    ref = _parse_mean_table(rep, QA_FORMAL_TABLE_HEADER)
    if not ref:
        return False, "正式集问答质量评分报告的第三节主表解析不到任何组（判据失去作用对象）"
    miss = []
    for g in sorted(ref):
        vals = ref[g]
        for i, lab in enumerate(("Answer Accuracy", "Completeness", "Faithfulness")):
            strs = _metric_strings(vals[i])
            if not any(s in rep for s in strs):
                miss.append("报告主表 %s 组 %s 的 %s 不在报告正文中" % (g, lab, vals[i]))
            elif not any(s in body for s in strs):
                miss.append("6.8.1 正文未逐项登记 %s 组 %s＝%s" % (g, lab, vals[i]))
    js = _load_json(ctx, QA_SCORE_SUMMARY_REL)
    if js is None:
        miss.append("正式报告 JSON 缺失，无法断言 12.8 判定表")
    else:
        for rec in (js.get("judgement_12_8_answer_accuracy_half") or []):
            for key in ("cer_A", "cer_C", "answer_accuracy_A", "answer_accuracy_C"):
                v = rec.get(key)
                if v is None:
                    miss.append("报告 JSON 缺 12.8 判定的 %s（子集 %s）" % (key, rec.get("subset")))
                    continue
                strs = _metric_strings(float(v))
                if not any(s in body for s in strs):
                    miss.append("6.8.1 正文未登记 12.8 判定的 %s＝%s（子集 %s）"
                                % (key, v, rec.get("subset")))
    if miss:
        return False, "；".join(miss[:4])
    return True, ("正式集问答质量评分报告主表的 %d 组 × 3 维均值已逐项命中 6.8.1 正文；"
                  "6.8 节无「未评分」阶段的时点断言；12.8 判定表的 %d 个子集的 CER 与 "
                  "Answer Accuracy 逐项命中" % (len(ref),
                                          len(js.get("judgement_12_8_answer_accuracy_half") or [])))


def f4(ctx):
    """6.7～6.10 四节已按正式全量读数回填，且每个读数可复算／可溯源。

    判据重基线（2026-10-08，见《28》第八节 F4 行与《02》v3.12 的同款处置）：
    旧判据＝「四节内无任何指标读数（正式全量未运行，不得预填）」——正式全量跑完
    并依法回填后，该判据必然为假。新判据不再看守空章节，而是逐条断言**新事实**：
    (a) 四节里必须真的出现 ≥3 位小数的指标读数（空章节不再合格）；
    (b) 每个读数必须能在**从冻结运行留痕与冻结题集现场重算**的池子里找到，或在
        本节自己用反引号标注出处的已登记来源文件里逐字命中（不得凭空出现）；
    (c) 重算必须与正式报告逐项一致，且报告必须逐项列出要求上报的读数。

    F4 再加重基线（2026-10-09，见《28》第八节 F4 行的第二段）：
    (d) 第三组断言 `_f4_formal_qa`——正式集问答质量评分**已完成**这一新事实：
        6.8.1 登记为已完成、6.8 三节内无只属于"未评分"阶段的时点断言、评分报告
        主表的每组三维度均值逐项命中 6.8.1 正文、12.8 判定表的三子集 CER 与
        Answer Accuracy 逐项命中。旧判据里"6.8 不得出现评分读数"这一条随之作废。
    """
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    bodies = {}
    for name in SKELETON_SECTIONS:
        body = _section_body(t, name)
        if body is None:
            return "FAIL", "%s 小节缺失" % name
        bodies[name] = body
    # (a) 四节各自必须含指标读数
    empty = [nm for nm, b in bodies.items() if not METRIC_DECIMAL.search(b)]
    if empty:
        return "FAIL", "下列小节内没有任何 ≥3 位小数的指标读数（回填未完成）：%s" % "、".join(empty)
    # 题集与运行留痕。留痕缺一组即无法断言"该组读数可由留痕复算"——按 FAIL 退出，
    # 但只在**缺失**时报红，不以"必须五组齐备"为前提（缺组的根因由 G1／G2 等行定位）。
    rows, missing = {}, []
    for g in ("A", "B", "C", "D", "E"):
        got = _load_jsonl(ctx, TRACE_REL_TMPL % g)
        if got is None:
            missing.append(g)
            continue
        rows[g] = {r["qid"]: r for r in got}
    if missing:
        return "FAIL", "复算源缺失：%s／answer_trace.jsonl（无法断言四节读数可复算）" % "、".join(missing)
    qs = _load_jsonl(ctx, QSET_REL)
    if qs is None:
        return "FAIL", "复算源缺失：%s（无法断言四节读数可复算）" % QSET_REL
    rep = ctx.text(REPORT_REL) or ""
    if not rep:
        return "FAIL", "正式报告缺失：%s" % REPORT_REL
    groups = {}
    for q in qs:
        for rng in _range_of(q):
            groups.setdefault(rng, []).append(q)
    assert set(groups) == set(RANGE_IDS), "题集三段口径解析异常：%s" % sorted(groups)
    # 复算池：三段口径 ＋ 核心集内的三个子集（《02》第12.8节 的判定单元，允许重叠）
    scopes = [(RANGE_IDS[rng], ql) for rng, ql in sorted(groups.items())]
    for nm, pred in (("关系型", lambda q: q.get("task_type") == "关系型"),
                     ("多跳型", lambda q: int(q.get("gold_hop_depth") or 0) >= 1),
                     ("时序型", lambda q: q.get("time_constraint") == "有")):
        scopes.append((nm, [q for q in groups["core"] if pred(q)]))
    # 图谱来源证据的每题均值（6.7 与 6.9 的第二个表）也在复算池里：它是从冻结留痕的
    # 逐题「图谱侧新增块进入最终证据集合」计数现场重算的，不是报告独有量。
    pool = {}
    for rng_label, ql in scopes:
        for g in ("A", "B", "C", "D", "E"):
            m = _metrics(g, ql, rows[g])
            for key, val in (("recall", m["recall"]), ("precision", m["precision"]),
                             ("mrr", m["mrr"]), ("cer", m["cer"])):
                for d in ROUND_DIGITS:
                    pool[(rng_label, g, key, d)] = "%.*f" % (d, val)
    for rng_label, ql in scopes:
        for g in ("A", "B", "C", "D", "E"):
            vals = [_graph_evidence_count(rows[g].get(q["qid"])) for q in ql
                    if q["qid"] in rows[g]]
            if not vals:
                continue
            mean = sum(vals) / float(len(vals))
            for d in ROUND_DIGITS:
                pool[(rng_label, g, "graph_evidence_per_question", d)] = "%.*f" % (d, mean)
    # 每题证据条数均值（6.9 节引用的机检量，9.8034 一级）同样是可复算量
    for rng_label, ql in scopes:
        for g in ("A", "B", "C", "D", "E"):
            vals = [len(rows[g][q["qid"]].get("evidence") or []) for q in ql
                    if q["qid"] in rows[g]]
            if not vals:
                continue
            mean = sum(vals) / float(len(vals))
            for d in ROUND_DIGITS:
                pool[(rng_label, g, "evidence_count_mean", d)] = "%.*f" % (d, mean)
    # ①类「gold 块被图谱语义边锚定的比例」（6.10 节）也是现场重算量：边表 → 带来源
    # 文本块的语义边集合，题集 gold → 全部 gold 块，两者求交后取比值。
    rate = _anchor_rate(ctx, qs)
    if rate is not None:
        for d in ROUND_DIGITS:
            pool[("graph", "-", "gold_anchor_rate", d)] = "%.*f" % (d, rate)
    # 《02》第12.8节 判定表里的 **Answer Accuracy 差值**（C 组减 A 组）是**派生量**：
    # 由正式集问答评分汇总（`问答评分_正式/评分汇总.json`，6.8.1 节内标注的已登记来源
    # 的机读产物）逐子集现场相减得到，故一并进复算池——正文里出现的 ＋0.1015／＋0.1744／
    # ＋0.1745 因此不是"凭空写的数"，而是可从冻结读数复算的差值。
    rj0 = _load_json(ctx, QA_SCORE_SUMMARY_REL)
    for rec in ((rj0 or {}).get("judgement_12_8_answer_accuracy_half") or []):
        a, c = rec.get("answer_accuracy_A"), rec.get("answer_accuracy_C")
        if a is None or c is None:
            continue
        for d in ROUND_DIGITS:
            pool[("12.8", rec.get("subset") or "-", "aa_gap_C_minus_A", d)] = "%.*f" % (d, float(c) - float(a))
    # (c) 报告自报值 == 复算值；且**凡报告列出的组**，其核心 108 题四项指标必须
    #     在报告正文里逐项登记。这一条同时盯住两件事：正文读数的出处仍在报告里
    #     （可溯源），以及报告一旦被只含单一组的重跑覆盖（某一组的列消失），本行
    #     立刻报红。之所以按"报告列出的组"遍历，是为了让本判据在**不含重跑痕迹的
    #     最小镜像**里也可判定（自检镜像必须能给出 0 失败基线）。
    bad = []
    ts = TOLERANCE
    rj = _load_json(ctx, REPORT_JSON_REL)
    if rj is None:
        return "FAIL", "正式报告 JSON 缺失：%s" % REPORT_JSON_REL
    for key, label in (("recall", "Recall@K"),
                       ("precision", "Precision@K"),
                       ("mrr", "MRR"),
                       ("cer", "Complete Evidence Recall@K")):
        for g in [x for x in ("A", "B", "C", "D", "E") if x in (rj.get("groups") or [])]:
            val = _metrics(g, groups["core"], rows[g])[key]
            if not any(fmt in rep for fmt in _metric_strings(val)):
                bad.append("报告未逐项登记核心 108 题的 %s／%s（复算 %s）"
                           % (g, label, "%.6f" % val))
    # 报告自报值 == 复算值（正式报告 JSON 与冻结留痕逐项一致）
    for g in ("A", "B", "C", "D", "E"):
        blk = ((rj.get("subsets_named") or {}).get("core") or {}).get(g) or {}
        if not blk:
            continue
        m = _metrics(g, groups["core"], rows[g])
        for key in ("recall_at_k", "precision_at_k", "mrr",
                    "complete_evidence_recall_at_k"):
            rep_v = blk.get(key)
            if rep_v is None:
                bad.append("报告 JSON 缺 core.%s.%s" % (g, key))
                continue
            calc = {"recall_at_k": m["recall"], "precision_at_k": m["precision"],
                    "mrr": m["mrr"],
                    "complete_evidence_recall_at_k": m["cer"]}[key]
            if abs(float(rep_v) - calc) > ts:
                bad.append("报告 JSON 与复算不一致：core.%s.%s 报告 %s / 复算 %.6f"
                           % (g, key, rep_v, calc))
    if bad:
        return "FAIL", "；".join(bad[:4])
    # (b) 四节里每个 ≥3 位小数的读数必须可复算，或出自**本节自己用反引号标注过**的已登记
    #     来源文件（凡引用了来源的节，其读数不得是来源里查不到的数）。
    probsn = []
    for name, body in bodies.items():
        allowed = {}
        for rel in _source_paths(body):
            txt = ctx.text(rel)
            if txt:
                allowed[rel] = txt
        for tok in sorted(set(METRIC_DECIMAL.findall(body))):
            val = float(tok)
            # 图谱来源证据的"每题（块）"是计数类读数（可达 1.x／2.x），单独放宽上界
            hi = MAX_COUNT_VALUE if val > MAX_METRIC_VALUE else MAX_METRIC_VALUE
            if not (MIN_METRIC_VALUE <= val <= hi):
                # 唯一例外：跨模型一致率里的平均绝对差一类读数（ALLOW_SMALL_TOKENS），
                # 它们改用更窄的值域 SMALL_METRIC_MIN 起判，并且**必须**在来源文件中命中。
                if not (tok in ALLOW_SMALL_TOKENS and SMALL_METRIC_MIN <= val):
                    probsn.append("%s 内 %s 不在本判据的值域 [%s, %s] 内"
                                  % (name, tok, MIN_METRIC_VALUE, MAX_METRIC_VALUE))
                    continue
            hit_pool = any(v == tok for v in pool.values())
            hit_src = any(tok in txt for txt in allowed.values())
            if not (hit_pool or hit_src):
                probsn.append("%s 内 %s 既不可由冻结留痕复算、也不在节内标注的来源文件中"
                              % (name, tok))
    if probsn:
        return "FAIL", "；".join(probsn[:4])
    ok_qa, det_qa = _f4_formal_qa(ctx, t, bodies)
    if not ok_qa:
        return "FAIL", det_qa
    n_dec = sum(len(METRIC_DECIMAL.findall(b)) for b in bodies.values())
    rep_g = [x for x in ("A", "B", "C", "D", "E") if x in (rj.get("groups") or [])]
    return "OK", ("四节共 %d 个读数：全部可由冻结留痕复算、或在节内标注的来源文件中逐字命中；"
                  "报告当前覆盖 %s 组的自报值与复算逐项一致；%s；%s"
                  % (n_dec, "／".join(rep_g) or "零", det_qa,
                     "、".join("%s %d 个" % (nm, len(METRIC_DECIMAL.findall(b)))
                               for nm, b in bodies.items())))


def _section_body(text, name):
    """取 '## <name>' 到下一个同级或更高级标题之间的正文；找不到返回 None。"""
    lines = text.split("\n")
    start = None
    for i, ln in enumerate(lines):
        if re.match(r"^##\s+" + re.escape(name) + r"\s*$", ln):
            start = i + 1
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start, len(lines)):
        if re.match(r"^#{1,2}\s+\S", lines[j]):
            end = j
            break
    return "\n".join(lines[start:end])


# --------------------------------------------------------------------------
# G 组：骨架与门禁
# --------------------------------------------------------------------------
def _load_jsonl(ctx, rel):
    """读 JSONL／JSON 产物；文件缺失返回 None（由调用方决定 FAIL 还是跳过）。

    一道防线：正式报告 JSON 是**缩进多行**的普通 JSON（不是 JSONL），若按行解析会
    在首行就抛错。这里先试整体解析，成功即整份返回（对象包成单元素列表）；失败再按行解析。
    """
    t = ctx.text(rel)
    if t is None:
        return None
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, list) else [obj]
    except ValueError:
        pass
    out = []
    for ln in t.split("\n"):
        ln = ln.strip()
        if ln:
            out.append(json.loads(ln))
    return out


def _load_json(ctx, rel):
    """读普通 JSON 产物；文件缺失返回 None。"""
    t = ctx.text(rel)
    if t is None:
        return None
    return json.loads(t)


def _range_of(q):
    """题行落入哪几段口径：全部 / 核心 / 压力（按《02》第12.2节 的标签）。"""
    out = ["all"]
    out.append("stress" if q.get("subset") == "压力" else "core")
    return out


def _metric_strings(val):
    """一个指标值的全部合理写法（报告里同一读数可能写成 `0.12`、`0.1200`、`0.120000`）。

    只看"值"对不对，不看格式：先按 2～6 位小数各取一种写法，再去掉尾零取最短写法。
    这样「0.12」与「0.120000」都被承认，而 0.121 之类的偏差仍然不被承认。
    """
    out = set()
    for d in (2, 3, 4, 5, 6):
        out.add("%.*f" % (d, val))
    short = ("%.6f" % val).rstrip("0").rstrip(".")
    out.add(short if "." in short else short + ".0")
    return out


def _anchor_rate(ctx, qs):
    """6.10 节①类的锚定率：被图谱语义边锚定的 gold 块 ÷ 全部 gold 块。

    边表用 `csv` 标准库按表头取 `source_chunk_id` 列（不靠列序），题集取
    `gold_evidence_chunk_ids`。任一输入缺失即返回 None（该读数不进复算池）。
    """
    raw = ctx.text(GRAPH_EDGES_REL)
    if raw is None:
        return None
    anchored = set()
    for row in csv.DictReader(io.StringIO(raw)):
        sc = (row.get("source_chunk_id") or "").strip()
        if sc:
            anchored.add(sc)
    gold = []
    for q in qs:
        gold.extend(str(c) for c in (q.get("gold_evidence_chunk_ids") or []))
    if not gold:
        return None
    return sum(1 for c in gold if c in anchored) / float(len(gold))


def _graph_evidence_count(row):
    """该题最终证据集合里「图谱侧新增」的块数（6.7 与 6.9 第二个表的口径）。

    判据：答案留痕里标了 `from_graph=true` 的证据条数。若该题没有有效答案，返回 0。
    """
    if not row:
        return 0
    return sum(1 for e in (row.get("evidence") or []) if e.get("from_graph"))


def _metrics(group, qlist, rows):
    """从**冻结运行留痕与冻结题集**现场重算四项检索指标（文本块级、分母＝有效题数）。

    与《02》第12.7节 的定义逐条一致：Precision@K 的分母恒为 K；MRR 在前 K 内
    无 gold 时记 0；Complete Evidence Recall@K 为"全部命中记 1、否则记 0"。
    没有任何一处分母取自报告自报值——这是"不与报告自报值互为依据"的落点。
    """
    k = None
    n = 0
    rec = pre = mrr = cer = 0.0
    for q in qlist:
        row = rows.get(q["qid"])
        if row is None:
            continue
        if k is None:
            k = int(row.get("k") or 10)
        n += 1
        gold = set(int(c) for c in q["gold_evidence_chunk_ids"])
        ev = [int(e["chunk_id"]) for e in row.get("evidence") or []][:k]
        hit = [c for c in ev if c in gold]
        rec += len(hit) / float(len(gold))
        pre += len(hit) / float(k)
        mrr += (1.0 / (ev.index(hit[0]) + 1)) if hit else 0.0
        cer += 1.0 if gold <= set(ev) else 0.0
    if not n:
        return {"n": 0, "recall": 0.0, "precision": 0.0, "mrr": 0.0, "cer": 0.0, "k": k or 10}
    return {"n": n, "recall": rec / n, "precision": pre / n,
            "mrr": mrr / n, "cer": cer / n, "k": k or 10}


def _source_paths(body):
    """取本节内以反引号标注出处的相对路径（已登记来源文件的四种后缀都收）。"""
    out = []
    for tok in re.findall(r"`([^`\n]+)`", body):
        tok = tok.strip().strip("/")
        if not tok.endswith((".md", ".json", ".jsonl", ".csv")):
            continue
        if tok.startswith(("http://", "https://")):
            continue
        rel = tok.replace("\\", "/")
        if rel in SRC_WHITELIST:
            out.append(rel)
    return out


def g1(ctx):
    """6.7～6.10 四节齐备、无未回填占位；报告与复算不一致的历史读数已重算；D/E 集合比对成立。

    判据重基线（2026-10-08）：旧判据＝「四节各含 ≥3 条显式 TODO」——正式全量跑完并
    依法回填后，该判据必然为假（回填后的正文不该再留 TODO）。新判据改为断言**新事实**，
    且比旧判据更难满足：四节必须存在（原内核保留）、每节必须含指标读数、正文不得再留
    任何未回填占位或已失效的时点断言、且**用冻结留痕现场复算**校验两处可比对结论——
    正式报告里已与现行复算不一致的历史读数（预实验集的 A 组同值）必须已在正文中重算，
    D 组与 E 组的证据集合必须逐题相同。

    2026-10-09 追加登记（正式集问答质量评分完成后）：本行判据**未重基线、判据反而更严**——
    6.8 三节里的"未评分"阶段时点断言由 F4 的第三组断言 `_f4_formal_qa` 逐条看守
    （STALE_6_8_MARKERS），本行仍按原内核断言四节齐备、无 TODO 占位与两处复算比对。
    """
    t = paper(ctx)
    if not t:
        return "FAIL", "《29》不存在"
    bad, counts = [], {}
    for name in SKELETON_SECTIONS:
        body = _section_body(t, name)
        if body is None:
            bad.append("%s 小节缺失" % name)
            continue
        counts[name] = len(METRIC_DECIMAL.findall(body))
        if not counts[name]:
            bad.append("%s 内无指标读数（回填未完成）" % name)
    if bad:
        return "FAIL", "；".join(bad)
    stale = []
    for name in SKELETON_SECTIONS:
        body = _section_body(t, name)
        for mk in STALE_MARKERS:
            if mk in body:
                stale.append("%s 内残留未回填占位「%s」" % (name, mk))
    if stale:
        return "FAIL", "；".join(stale[:4])
    rows = {}
    for g in ("A", "B", "C", "D", "E"):
        got = _load_jsonl(ctx, TRACE_REL_TMPL % g)
        if got is None:
            return "FAIL", "复算源缺失：%s（无法断言 D/E 比对）" % (TRACE_REL_TMPL % g)
        rows[g] = {r["qid"]: r for r in got}
    qs = _load_jsonl(ctx, QSET_REL)
    if qs is None:
        return "FAIL", "复算源缺失：%s" % QSET_REL
    groups = {}
    for q in qs:
        for rng in _range_of(q):
            groups.setdefault(rng, []).append(q)
    # ① 报告自报的逐子集读数必须与现行复算一致（历史读数是否已重算）
    recalc = []
    for nm, pred in (("关系型", lambda q: q.get("task_type") == "关系型"),
                     ("多跳型", lambda q: int(q.get("gold_hop_depth") or 0) >= 1),
                     ("时序型", lambda q: q.get("time_constraint") == "有")):
        ql = [q for q in groups["core"] if pred(q)]
        for g in ("A", "B", "C", "D", "E"):
            recalc.append("%.6f" % _metrics(g, ql, rows[g])["cer"])
    # ② D 与 E 的证据集合必须逐题相同（"E 只改顺序"）；顺序必须逐题不同
    dsame = doff = 0
    common = [q for q in groups["all"]
              if q["qid"] in rows["D"] and q["qid"] in rows["E"]]
    for q in common:
        a = [int(e["chunk_id"]) for e in rows["D"][q["qid"]]["evidence"]]
        b = [int(e["chunk_id"]) for e in rows["E"][q["qid"]]["evidence"]]
        if set(a) == set(b):
            dsame += 1
        if a != b:
            doff += 1
    if common and dsame != len(common):
        bad.append("D／E 证据集合并非逐题相同：%d／%d" % (dsame, len(common)))
    if common and doff != len(common):
        bad.append("D／E 呈现顺序并非逐题不同：%d／%d" % (doff, len(common)))
    if bad:
        return "FAIL", "；".join(bad[:4])
    return "OK", ("四节齐备且无未回填占位（读数个数 %s）；逐子集 CER 已按现行留痕复算"
                  "（%d 个复算值）；D／E 证据集合逐题相同（%d／%d）、呈现顺序逐题不同"
                  "（%d／%d）"
                  % (counts, len(recalc), dsame, len(common), doff, len(common)))


def _run_assembler(ctx, out_path=None):
    script = ctx.p(ASSEMBLER_REL)
    if not os.path.isfile(script):
        return None, "拼装脚本缺失"
    cmd = [sys.executable, script]
    if out_path:
        cmd += ["--out", out_path]
    r = subprocess.run(cmd, cwd=ctx.root, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, env=subenv())
    return r.returncode, r.stdout.decode("utf-8", "replace")


def g2(ctx):
    if ctx.profile == "static":
        return "UNRUN", "static 档不实跑子进程"
    tmp = tempfile.mkdtemp(prefix="s11asm_")
    try:
        o1 = os.path.join(tmp, "a.md")
        o2 = os.path.join(tmp, "b.md")
        rc1, _ = _run_assembler(ctx, o1)
        rc2, _ = _run_assembler(ctx, o2)
        if rc1 != 0 or rc2 != 0:
            return "FAIL", "拼装脚本退出码 %s／%s（期望 0／0）" % (rc1, rc2)
        b1 = open(o1, "rb").read()
        b2 = open(o2, "rb").read()
        if b1 != b2:
            return "FAIL", "两次拼装产出不一致（%d vs %d 字节）" % (len(b1), len(b2))
        on_disk = ctx.raw(PAPER_REL)
        if on_disk != b1:
            return "FAIL", "两次拼装一致，但与磁盘上的《29》不一致"
        return "OK", "连跑两次逐字节一致（%d 字节，sha256:%s…），且与磁盘《29》一致" % (
            len(b1), hashlib.sha256(b1).hexdigest()[:12])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def g3(ctx):
    d = ctx.p("交付物/01-论文")
    if not os.path.isdir(d):
        return "FAIL", "阶段十一目录不存在"
    # G3 重基线（2026-10-10）：本阶段新增了 **Word 成稿** 这一正当产物，落点
    # `交付物/01-论文/提交件/`（学校要求的文件名体例 `姓名_学号_题目.docx`）。
    # 旧判据「条目集合恰为 {《28》,《29},_分章源文件}」是**成文时的事实断言**，
    # 新增产物后必然对**正确产物**报红，故允许集合补入 `提交件`。
    # **方向是收紧不是放宽**：仍然断言「集合恰好相等」（不是「包含」），并**新增两条**
    # 对提交件目录的断言（恰 1 份 `.docx`、且非空）；旧判据的合理内核一条未删。
    allowed = {"28-第11阶段任务书（论文撰写与材料整理）.md",
               "29-第11阶段产出文档（毕业论文）.md",
               "_分章源文件",
               "提交件"}
    have = set(os.listdir(d))
    extra = sorted(have - allowed)
    miss = sorted(allowed - have)
    if extra:
        return "FAIL", "阶段十一目录存在计划外条目：%s" % extra
    if miss:
        return "FAIL", "阶段十一目录缺条目：%s" % miss
    src = sorted(f for f in os.listdir(ctx.p(SRC_REL)) if f.endswith(".md"))
    if len(src) != 10:
        return "FAIL", "分章源文件为 %d 份（期望 10）" % len(src)
    for rel in (ASSEMBLER_REL, "工具/验收第11阶段.py"):
        if not os.path.isfile(ctx.p(rel)):
            return "FAIL", "本阶段新增脚本缺失：%s" % rel
    # 提交件目录：**新增的两条断言**（重基线时一并加严，见上文注释）
    sub = ctx.p("交付物/01-论文/提交件")
    if not os.path.isdir(sub):
        return "FAIL", "提交件目录不存在：%s" % sub
    docxs = sorted(f for f in os.listdir(sub) if f.lower().endswith(".docx"))
    if len(docxs) != 1:
        return "FAIL", "提交件目录的 .docx 为 %d 份（期望恰 1 份）：%s" % (len(docxs), docxs)
    sub_size = os.path.getsize(os.path.join(sub, docxs[0]))
    if sub_size <= 0:
        return "FAIL", "提交件为空文件：%s" % docxs[0]
    return "OK", ("阶段十一目录仅含《28》《29》、_分章源文件（10 份）与提交件（1 份非空 .docx，"
                  "%d 字节）；本阶段两个新脚本就位" % sub_size)


def g4(ctx):
    if ctx.profile == "static":
        return "UNRUN", "static 档不实跑子进程"
    script = ctx.p("工具/跨文档核验.py")
    if not os.path.isfile(script):
        return "FAIL", "跨文档核验脚本缺失"
    r = subprocess.run([sys.executable, script, "--strict-citations"],
                       cwd=ctx.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=subenv())
    out = r.stdout.decode("utf-8", "replace")
    fails = [ln.strip() for ln in out.splitlines()
             if re.match(r"^\s*\[(FAIL|失败)\]", ln) or re.match(r"^\s*!!", ln)]
    if r.returncode == 0 and not fails:
        return "OK", "实跑退出码 0（0 失败）"
    unallowed = [f for f in fails
                 if not any(a in f for a in CROSSDOC_ALLOWED)]
    if unallowed:
        return "FAIL", "退出码 %d；存在两项登记之外的失败：%s" % (
            r.returncode, "；".join(unallowed[:4]))
    return "FAIL", "退出码 %d；失败项 %d 条（均属两项已登记项，未登记项需由 Lead 收口）：%s" % (
        r.returncode, len(fails), "；".join(fails[:4]))


IMPL = {
    "A1": a1, "A2": a2, "A3": a3, "A4": a4,
    "B1": b1, "B2": b2,
    "C1": c1, "C2": c2, "C3": c3,
    "D1": d1, "D2": d2, "D3": d3,
    "E1": e1, "E2": e2, "E3": e3,
    "F1": f1, "F2": f2, "F3": f3, "F4": f4,
    "G1": g1, "G2": g2, "G3": g3, "G4": g4,
}


# --------------------------------------------------------------------------
# 行结构：从《28》第八节解析并比对
# --------------------------------------------------------------------------
def parse_taskbook_rows(ctx):
    t = ctx.text(TASKBOOK_REL)
    if not t:
        return None, None
    m = re.search(r"^##\s*八、验收标准.*$", t, re.M)
    if not m:
        return None, None
    seg = t[m.end():]
    m2 = re.search(r"^##\s*九、", seg, re.M)
    if m2:
        seg = seg[:m2.start()]
    pairs = re.findall(r"^\|\s*([A-G]\d{1,2})\s*\|\s*([^|]+?)\s*\|", seg, re.M)
    parsed = [(rid, norm(title)) for rid, title in pairs]
    return parsed, seg


def check_rowstructure(ctx):
    parsed, _ = parse_taskbook_rows(ctx)
    if parsed is None:
        return "FAIL", "《28》缺失或未找到「八、验收标准」"
    registered = [(rid, title) for rid, title in ROWS]
    if parsed != registered:
        only_p = [r for r in parsed if r not in registered]
        only_r = [r for r in registered if r not in parsed]
        return "FAIL", "《28》第八节 %d 行 vs 脚本注册 %d 行；多 %s；缺 %s" % (
            len(parsed), len(registered), only_p[:3], only_r[:3])
    return "OK", "《28》第八节解析 %d 行，与脚本注册集合逐行 1:1" % len(parsed)


# --------------------------------------------------------------------------
# 跑一遍
# --------------------------------------------------------------------------
def run_all(ctx, quiet=False):
    row_ok, results = check_rowstructure(ctx)
    if row_ok == "FAIL":
        return None, row_ok, results
    out = {}
    for rid, title in ROWS:
        try:
            status, detail = IMPL[rid](ctx)
        except Exception as exc:                       # noqa: BLE001
            status, detail = "FAIL", "检查项抛出异常：%r" % exc
        out[rid] = (status, detail)
        if not quiet:
            print("  [%-5s] %-4s %s" % (status, rid, title))
            print("          %s" % detail)
    return out, "OK", ""


def summarize(results, elapsed_note=""):
    n_ok = sum(1 for s, _ in results.values() if s == "OK")
    n_fail = sum(1 for s, _ in results.values() if s == "FAIL")
    n_unrun = sum(1 for s, _ in results.values() if s == "UNRUN")
    groups = {}
    for rid, (s, _) in results.items():
        groups.setdefault(rid[0], [0, 0, 0])[{"OK": 0, "FAIL": 1, "UNRUN": 2}[s]] += 1
    print()
    print("  分组：", "；".join(
        "%s 组 OK %d／FAIL %d／UNRUN %d" % (k, v[0], v[1], v[2])
        for k, v in sorted(groups.items())))
    print("  合计：计划 %d 行；OK %d；FAIL %d；UNRUN %d%s"
          % (len(results), n_ok, n_fail, n_unrun, elapsed_note))
    if n_fail:
        print("  结论：有内容失败 %d 行：%s ⇒ 退出码 1"
              % (n_fail, "、".join(r for r, (s, _) in results.items() if s == "FAIL")))
        return 1
    if n_unrun:
        print("  结论：有检查项未执行 %d 行：%s ⇒ 退出码 2"
              % (n_unrun, "、".join(r for r, (s, _) in results.items() if s == "UNRUN")))
        return 2
    print("  结论：%d 行全部 [OK] ⇒ 退出码 0" % len(results))
    return 0


# --------------------------------------------------------------------------
# 自检：临时镜像 ＋ 定向篡改
# --------------------------------------------------------------------------
MIRROR_FILES = [
    MASTER_REL, PROPOSAL_REL, ASSEMBLER_REL, TASKBOOK_REL, PAPER_REL,
    EXTRACT_JSON_REL, NFR_JSON_REL,
    "交付物/04-数据与知识图谱/数据准备/13-数据准备（第五阶段）.md",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md",
    "交付物/06-实验与评测/27-第10阶段产出文档（系统测试与对比实验）.md",
    "交付物/05-系统实现/前后端系统集成/25-第9阶段产出文档（前后端系统集成）.md",
    "交付物/03-代码/测试/README.md",
    # F4／G1 重基线后新增的复算源与溯源来源（只读；自检镜像必须一并复制，
    # 否则镜像里 F4／G1 会因"复算源缺失"报红，反例的期望集就不再是本判据的命中面）
    QSET_REL, REPORT_REL, REPORT_JSON_REL, QA_SCORE_REL, PRE_REPORT_REL,
    GRAPH_EDGES_REL,
    # F4 第二段重基线（2026-10-09，正式集问答质量评分已完成）新增：6.8.1 的
    # 五组三维度均值与 12.8 判定表的溯源来源与机读汇总，缺它 F4 的新断言无法判定。
    QA_SCORE_FORMAL_REL, QA_SCORE_SUMMARY_REL,
    # G3 重基线（2026-10-10，允许并断言"提交件"目录）新增：G3 现在断言
    # `交付物/01-论文/提交件/` 恰有 1 份非空 `.docx`，**自检镜像必须一并复制它**，
    # 否则镜像里 G3 会因"提交件缺失"报红、原样对照就不是 0 内容失败（与上文 F4／G1 同一种坑）。
    "交付物/01-论文/提交件/王锦灿_20234225193_基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现.docx",
] + [TRACE_REL_TMPL % g for g in ("A", "B", "C", "D", "E")]
MIRROR_PNGS = [
    "交付物/09-图表/第4阶段图/图4-1-六层架构与部署形态.png",
    "交付物/09-图表/第4阶段图/图4-2-提问问答完整业务流程.png",
    "交付物/09-图表/第4阶段图/图4-3-后台导入修改删除与重新处理流程.png",
    "交付物/09-图表/第4阶段图/图4-4-六张表的ER图.png",
    "交付物/09-图表/第4阶段图/图4-5-向量原文三级映射链路.png",
    "交付物/09-图表/第4阶段图/图4-6-知识图谱本体总览.png",
    "交付物/09-图表/第4阶段图/图4-7-检索管线组件与数据流.png",
    "交付物/09-图表/第4阶段图/图4-8-A-E五组配置路径.png",
    # E3 重基线（2026-10-10，8 条 → 9 条）新增：第三章 3.3 的图 3-1（正式 UML 用例图）；
    # 缺它镜像里 E3 会因"路径少一条"报红，原样对照的失败集就不再为空。
    "交付物/09-图表/第3阶段图/图3-1-系统用例图.png",
]


def build_mirror(dst):
    for rel in MIRROR_FILES:
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        if not os.path.isfile(src):
            raise SystemExit("镜像源缺失：%s" % rel)
        d = os.path.join(dst, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(src, d)
    for f in SOURCE_ORDER:
        rel = "%s/%s" % (SRC_REL, f)
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        d = os.path.join(dst, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copy2(src, d)
    for rel in MIRROR_PNGS:
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        d = os.path.join(dst, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(d), exist_ok=True)
        with open(d, "wb") as fh:                 # 占位：判据只查存在性
            fh.write(b"PNGPLACEHOLDER")
    os.makedirs(os.path.join(dst, "工具"), exist_ok=True)
    if not os.path.isfile(os.path.join(dst, "工具", "验收第11阶段.py")):
        shutil.copy2(os.path.abspath(__file__),
                     os.path.join(dst, "工具", "验收第11阶段.py"))


def _write(rel_root, rel, data):
    path = os.path.join(rel_root, rel.replace("/", os.sep))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    if mode == "wb":
        with open(path, "wb") as fh:
            fh.write(data)
    else:
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(data)


def _read(rel_root, rel):
    path = os.path.join(rel_root, rel.replace("/", os.sep))
    with open(path, "rb") as fh:
        return fh.read()


def _regen(mirror):
    """在镜像里重跑拼装脚本，使《29》与源文件保持一致。"""
    script = os.path.join(mirror, "工具", "拼装第十一阶段论文.py")
    r = subprocess.run([sys.executable, script], cwd=mirror,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       env=subenv())
    if r.returncode != 0:
        raise SystemExit("镜像内拼装失败：%s"
                         % r.stdout.decode("utf-8", "replace")[-400:])


def _tamper_replace(rel, old, new, src=True, replace_all=False):
    """把 rel 里的 old 换成 new；src=True 时随后重跑拼装（源文件 → 《29》）。

    replace_all=True 用于"同一个读数在多处出现"的场合：只改一处，另一处仍会把
    该值带回判据的比对面，反例就形同虚设。
    """
    def fn(mirror):
        t = _read(mirror, rel).decode("utf-8")
        if old not in t:
            raise SystemExit("篡改目标不存在：%s ← %s" % (rel, old[:40]))
        _write(mirror, rel, t.replace(old, new) if replace_all else t.replace(old, new, 1))
        if src:
            _regen(mirror)
    return fn


def _tamper_replace_all_src(old, new):
    """在**全部**分章源文件里做同一处替换，再重跑拼装。

    同一个串可能散落在多份源文件里（例如「表 4-13」既在第四章的表题里、
    也在第六章讨论接口口径的段落里）。只改一份，目标串仍留在《29》里，
    判据自然不会变红——那样的反例形同虚设，必须把它移到「所有出现处」。

    2026-10-09 追加登记：本函数现在是**口径类反例的默认改法**。判据里的
    C1／C3／E1 都只断言"某一类串在小节／全文里的出现形态"，因此只要《29》
    里还有一处旧串幸存（例如第六章 6.8 与第七章各自都写着「模型评分口径」、
    「图 4-8」在第四章与第六章各出现多次），反例就因为**旁证串**而不变红。
    这正是"反例必须覆盖所有出现处"这条纪律的适用面，不是判据被弱化。
    """
    def fn(mirror):
        hit = []
        for f in SOURCE_ORDER:
            rel = "%s/%s" % (SRC_REL, f)
            t = _read(mirror, rel).decode("utf-8")
            if old in t:
                hit.append(f)
                _write(mirror, rel, t.replace(old, new))
        if not hit:
            raise SystemExit("篡改目标不存在于任何分章源文件：%s" % old)
        _regen(mirror)
    return fn


def _tamper_delete(rel, src=True):
    def fn(mirror):
        os.remove(os.path.join(mirror, rel.replace("/", os.sep)))
        if src:
            _regen(mirror)
    return fn


def _tamper_json(rel, key_path, newval):
    def fn(mirror):
        data = json.loads(_read(mirror, rel).decode("utf-8"))
        node = data
        for k in key_path[:-1]:
            node = node[k]
        if node[key_path[-1]] == newval:
            raise SystemExit("篡改目标新值与旧值相同")
        node[key_path[-1]] = newval
        _write(mirror, rel, json.dumps(data, ensure_ascii=False, indent=2))
    return fn


def _tamper_json_nodes(rel, nodes):
    """一次改多个节点：nodes = [([键路径…], 新值), …]。

    单点篡改不足以把目标值移出候选池时用（同一个读数可能在多处出现，
    只改一处、另一处仍把它带回候选池 ⇒ 反例形同虚设）。
    """
    def fn(mirror):
        data = json.loads(_read(mirror, rel).decode("utf-8"))
        for key_path, newval in nodes:
            node = data
            for k in key_path[:-1]:
                node = node[k]
            if node[key_path[-1]] == newval:
                raise SystemExit("篡改目标新值与旧值相同：%s" % ".".join(key_path))
            node[key_path[-1]] = newval
        _write(mirror, rel, json.dumps(data, ensure_ascii=False, indent=2))
    return fn


def _tamper_drop_lines(rel, pred):
    def fn(mirror):
        t = _read(mirror, rel).decode("utf-8")
        kept = [ln for ln in t.split("\n") if not pred(ln)]
        if len(kept) == len(t.split("\n")):
            raise SystemExit("篡改未命中任何行：%s" % rel)
        _write(mirror, rel, "\n".join(kept))
        _regen(mirror)
    return fn


def _tamper_jsonl_first_two(rel):
    """把某组 answer_trace.jsonl 的**首题**证据顺序对调（集合不变、呈现顺序变）。"""
    def fn(mirror):
        rows = [json.loads(l) for l in
                _read(mirror, rel).decode("utf-8").split("\n") if l.strip()]
        ev = rows[0]["evidence"]
        if len(ev) < 2:
            raise SystemExit("首题证据不足 2 条，无法对调：%s" % rel)
        ev[0], ev[1] = ev[1], ev[0]
        _write(mirror, rel, "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    return fn


def _tamper_jsonl_swap_groups(rel_a, rel_b):
    """让 A、B 两组在**某一题**上的证据集合不再相同。

    先在同题号里找一组集合本来就不相同的题（真实痕迹里 D／E 的每题集合都相同、
    顺序都不同，所以这一步是"有没有可用的差异题"的前置），再把这题在 A 组里的
    证据整条替换为 B 组的那一条。于是该题的集合比对必然失败——这正是"E 只改顺序"
    那条断言应当抓住的情形。
    """
    def fn(mirror):
        ra = [json.loads(l) for l in
              _read(mirror, rel_a).decode("utf-8").split("\n") if l.strip()]
        rb = [json.loads(l) for l in
              _read(mirror, rel_b).decode("utf-8").split("\n") if l.strip()]
        mb = {r["qid"]: r for r in rb}
        target = None
        for r in ra:
            other = mb.get(r["qid"])
            if other is None:
                continue
            sa = set(e["chunk_id"] for e in r["evidence"])
            sb = set(e["chunk_id"] for e in other["evidence"])
            if sa != sb:
                target = (r, other)
                break
        if target is None:
            # 真实痕迹上 D／E 的每题集合都相同，无法"取其不同"：改为在 A 组某一题上
            # **删掉一条证据**。集合因此少一块，与 B 组的同题集合不再相同——这正是
            # "D／E 的证据集合逐题相同"这条断言应当抓住的情形。
            for r in ra:
                if len(r["evidence"]) >= 2:
                    r["evidence"] = r["evidence"][:-1]
                    target = (r, mb.get(r["qid"]))
                    break
        if target is None:
            raise SystemExit("找不到可制造集合差异的题：%s / %s" % (rel_a, rel_b))
        _write(mirror, rel_a,
               "\n".join(json.dumps(r, ensure_ascii=False) for r in ra) + "\n")
    return fn


def _tamper_jsonl_drop_last(rel):
    """删掉某组 answer_trace.jsonl 的最后一行（该组少一题）。"""
    def fn(mirror):
        lines = [l for l in _read(mirror, rel).decode("utf-8").split("\n") if l.strip()]
        if len(lines) < 2:
            raise SystemExit("行数不足，无法删行：%s" % rel)
        _write(mirror, rel, "\n".join(lines[:-1]) + "\n")
    return fn


SRC = SRC_REL

# 自检镜像按 static 档构建（G4 需要整仓、A4／G2 需要实跑子进程），
# 这三行在本档恒为 UNRUN（≠ FAIL），因此**不得**出现在任何反例的期望集里。
SELFTEST_PROFILE = "static"
SELFTEST_UNRUN = {"A4", "G2", "G4"}

CASES = [
    ("① 删掉 01 中的二级标题「## 1.2 研究意义」",
     _tamper_drop_lines(SRC + "/01-第一章-绪论.md",
                        lambda ln: ln.strip() == "## 1.2 研究意义"),
     {"B2"}),
    ("② 往 06 的 6.7 节注入一条未回填占位 TODO（回填后本不该再留 TODO）",
     _tamper_replace(SRC + "/06-第六章-系统测试与实验分析.md",
                     "全部数值由本节的独立复算脚本从",
                     "**TODO-6.7-9**：待补。全部数值由本节的独立复算脚本从"),
     {"G1"}),
    ("③ 在 06 的 6.7 节内插入编造读数 0.612345",
     _tamper_replace(SRC + "/06-第六章-系统测试与实验分析.md",
                     "**本节的数据来源。**正式全量实验的运行脚本",
                     "**本节的数据来源。**本次实测 CER 为 0.612345。正式全量实验的运行脚本"),
     {"F4"}),
    # 该处篡改同时命中三行：C1（出现抽取读数的小节内不再有「模型参照集口径」限定语）、
    # C3（出现正向人工口径表述）、C2（被改成的句子带「准确率」而既无口径限定语、
    # 也不在否定／待补语境）。三行都是判据自身的应有反应，不是旁及。
    # **改法如实登记（2026-10-09 重基线）**：该串散落在多份源文件里，只改 06 的一份，
    # 07 与 00-前置里其余的「模型参照集口径」仍会把 C1／C2 的判据面撑住，反例就形同
    # 虚设；故改为**全源文件**替换（这也是用例 ⑨ 的既有做法）。
    ("④ 把全部源文件里的「模型参照集口径下的抽取表现」改成「人工金标准下的抽取准确率」",
     _tamper_replace_all_src("模型参照集口径下的抽取表现", "人工金标准下的抽取准确率"),
     {"C1", "C2", "C3"}),
    # 用例 ⑤ 的命中面按现行正文如实收窄为 C3：正文里凡出现「准确率」的行本就带否定／
    # 待补标记（"不得读作""不能当准确率读""不存在这一步"），故把它改成「人工评分口径」
    # 之后 C2 不再变红；这是判据的正确行为，不是放行。**C2 的专属反例是用例 ③**——
    # 注入的编造读数行同时把该节内唯一的「模型评分口径下的准确率」替换掉，令 C2 变成
    # "全文未出现模型评分口径"而报红（实测期望集已按此写法登记）。
    # **改法如实登记（2026-10-09 重基线）**：同用例 ④，「模型评分口径」散落在 06／07／
    # 00-前置 三份源文件里，故改为全源文件替换，否则残留的旧串会让 C2／C3 双双沉默。
    ("⑤ 把全部源文件里的「模型评分口径」改成「人工评分口径」",
     _tamper_replace_all_src("模型评分口径", "人工评分口径"),
     {"C3"}),
    ("⑥ 在 02 中注入被禁的四字连写术语",
     _tamper_replace(SRC + "/02-第二章-相关技术.md",
                     "向量检索组件", "向量检索组件（即一类" + BANNED + "）"),
     {"D1"}),
    ("⑦ 删掉 90 中的最后一条参考文献",
     _tamper_drop_lines(SRC + "/90-参考文献.md",
                        lambda ln: ln.startswith("[22]")),
     {"D2"}),
    ("⑧ 删掉图 4-5 的 PNG 文件",
     _tamper_delete("交付物/09-图表/第4阶段图/图4-5-向量原文三级映射链路.png", src=False),
     {"E3"}),
    # 「表 4-13」在分章源文件里出现两处来源：第四章的表题（04）与第六章讨论接口
    # 口径的段落（06）。只改 04 一份，06 里的「表 4-13」仍会在《29》中出现，E2 不会红
    # ⇒ 篡改必须覆盖**所有出现处**。
    ("⑨ 把全部源文件中的「表 4-13」改成「表 4-14」（第四章表题 ＋ 第六章口径段）",
     _tamper_replace_all_src("表 4-13", "表 4-14"),
     {"E2"}),
    ("⑩ 把全部源文件中的「图 4-8」改成「图 4-9」（第四章图题 ＋ 第六章引用处）",
     _tamper_replace_all_src("图 4-8", "图 4-9"),
     {"E1"}),
    # 0.535975 在《抽取评测指标.json》里出现两次（合计/entities/main 与 合计/entities/compat），
    # 四位小数都是 0.5360；只改一处，另一处仍把 0.5360 留在候选池里 ⇒ F1 不会变红。
    ("⑪ 篡改《抽取评测指标.json》实体合计 F1 的两处来源（0.535975 → 0.499999）",
     _tamper_json_nodes(EXTRACT_JSON_REL,
                        [(["results", "metrics", "合计", "entities", "main", "f1"], 0.499999),
                         (["results", "metrics", "合计", "entities", "compat", "f1"], 0.499999)]),
     {"F1"}),
    ("⑫ 篡改《NFR_readings.json》的端到端均值（14.994 → 99.999）",
     _tamper_json(NFR_JSON_REL, ["nfr01", "end_to_end", "mean"], 99.999),
     {"F2"}),
    ("⑬ 把 07 的一级标题「# 第7章 总结与展望」改成「# 第7章 总结」",
     _tamper_replace(SRC + "/07-第七章-总结与展望.md",
                     "# 第7章 总结与展望", "# 第7章 总结"),
     {"B1"}),
    # 删源文件同时打红三行：A2（10 份齐备性）、A3（11 个目标文件的存在性／编码）、
    # G3（分章源文件份数）。A4／G2 在本档为 UNRUN（非 FAIL），按定义不可计入期望。
    ("⑭ 删掉分章源文件 91-致谢.md（级联：A2／A3／G3 一并变红）",
     _tamper_delete(SRC + "/91-致谢.md", src=False),
     {"A2", "A3", "G3"}),
    # 以下三个反例是 F4／G1 重基线（2026-10-08）后新增的，各自锁住新判据的一条腿：
    # ⑮ 锁「报告的登记必须与现行复算一致」——把报告自报的核心集 A 组 Recall@K
    #    改成一个凭空值，复算值随之与报告不一致 ⇒ F4 必须报红。
    ("⑮ 篡改《A_vs_C_对照.json》核心集 A 组 Recall@K（0.776144 → 0.776999）",
     _tamper_json(REPORT_JSON_REL,
                  ["subsets_named", "core", "A", "recall_at_k"], 0.776999),
     {"F4"}),
    # ⑯ 锁「D 与 E 的证据集合必须逐题相同」——把 D 组首题证据里的一个块换成 E 组首题
    #    独有的块，于是 D 少一块、E 多一块，集合比对必然失败（只对调组内顺序抓不到这条，
    #    因为 D／E 的集合本来就相同、顺序本来就不同）。
    ("⑯ 把《对照产出_正式/D/answer_trace.jsonl》某题的一条证据删掉（D/E 集合不再逐题相同）",
     _tamper_jsonl_swap_groups(TRACE_REL_TMPL % "D", TRACE_REL_TMPL % "E"),
     {"G1"}),
    # ⑰ 锁「D 与 E 必须逐题可比」——删掉 E 组 trace 最后一行：该组少一题、其读数
    #    也不再可由留痕复算。**如实登记这条反例的命中面只有 F4**：G1 的比对建立在
    #    同题号交集上，"少一题"不会破坏"集合逐题相同"这一相对性质（C∩D∩E 由 117
    #    降到 116，仍然逐题相同），所以 G1 不报红才是判据的正确行为。
    ("⑰ 删掉《对照产出_正式/E/answer_trace.jsonl》最后一行（E 组少一题；命中面只有 F4）",
     _tamper_jsonl_drop_last(TRACE_REL_TMPL % "E"),
     {"F4"}),
    # ⑱ 锁 F4 第二段重基线（2026-10-09）新增的那条腿：正式集问答质量评分报告被改掉
    #    一个组的均值后，"6.8.1 正文必须逐项登记报告主表列出的每组三维度均值"这条
    #    必然失败（全文替换，确保报告与正文两侧都不再含该值）。**如实登记本反例的
    #    命中面只有 F4**：G1 不看 6.8 的评分读数，故 G1 不报红是判据的正确行为。
    ("⑱ 把《问答评分_正式/问答评分报告.md》B 组的 Answer Accuracy 均值 1.8390 改成 1.7777",
     _tamper_replace(QA_SCORE_FORMAL_REL, "1.8390", "1.7777", src=False,
                     replace_all=True),
     {"F4"}),
    # ⑲ 锁 E3 重基线（2026-10-10，8 条 → 9 条）新增的那条腿：第三章图 3-1 的 PNG 被删后，
    #    "9 条图注 PNG 路径全部真实存在"必然失败。与 ⑧（删图 4-5）同一条判据的两个命中面。
    ("⑲ 删掉图 3-1 的 PNG 文件",
     _tamper_delete("交付物/09-图表/第3阶段图/图3-1-系统用例图.png", src=False),
     {"E3"}),
    # ⑳ 锁 E3 加严（2026-10-10，「只看图注路径」→「图注路径 ＋ 正文图片链接」）新增的
    #    那条腿：只把《29》里图 4-5 的**正文图片链接目标**改成不存在的文件名，**图注一字不动**。
    #    此时第 ① 条腿（9 条图注路径）照旧全绿，只有第 ② 条腿能报红——这正是旧判据放过
    #    「图注写得对、正文 9 个链接全裂」那类产物的缺口。
    #    **改法如实登记**：必须直接改产出《29》而不能改源文件再重拼——第 2 步给两个拼装脚本
    #    加了产出前链接自检，源文件里塞坏链会让拼装脚本自己以非零退出码中止（`_regen` 会抛
    #    SystemExit），反例就够不到 E3；这也正是"两道防线"的分工：脚本挡住源文件侧，
    #    E3 挡住产出侧（手改《29》）。
    ("⑳ 把《29》里图 4-5 的正文图片链接目标改成不存在的文件名（图注不动）",
     _tamper_replace(PAPER_REL,
                     "](../09-图表/第4阶段图/图4-5-向量原文三级映射链路.png)",
                     "](../09-图表/第4阶段图/图4-5-已破坏的链接.png)",
                     src=False),
     {"E3"}),
]


def _run_static(mirror, ctx=None):
    """跑一遍自检镜像，返回 FAIL 行号列表；行结构自检失败返回 None。

    ctx 为 None 时新建；传入已有 Ctx 时，其文本缓存按内容指纹失效，
    所以「改源文件 → 重跑拼装 → 再读」一定读到新内容。
    """
    if ctx is None:
        ctx = Ctx(mirror, SELFTEST_PROFILE)
    res, _, _ = run_all(ctx, quiet=True)
    if res is None:
        return None
    return sorted(r for r, (s, _) in res.items() if s == "FAIL")


def selftest():
    tmp = tempfile.mkdtemp(prefix="s11self_")
    mirror = os.path.join(tmp, "mirror")
    try:
        build_mirror(mirror)
        # 期望集必须落在本档可达的行上：UNRUN 行不可能变红，写进期望就是「结构性不可达」。
        unreachable = sorted({rid for _, _, exp in CASES for rid in exp} & SELFTEST_UNRUN)
        if unreachable:
            print("自检用例期望集含本档恒为 UNRUN 的行：%s ⇒ 结构化不可达，自检不通过"
                  % unreachable)
            return 2
        mctx = Ctx(mirror, SELFTEST_PROFILE)
        base_fail = _run_static(mirror, mctx)
        if base_fail is None:
            print("原样对照：行结构自检失败 —— 自检不通过")
            return 2
        n_rows = len(ROWS)
        n_unrun = len(SELFTEST_UNRUN)
        print("自检镜像：%s（档位 %s）" % (mirror, SELFTEST_PROFILE))
        print("原样对照：%d 行；FAIL %d 行 %s；UNRUN %d 行 %s"
              % (n_rows, len(base_fail), base_fail, n_unrun, sorted(SELFTEST_UNRUN)))
        if base_fail:
            print("原样对照应为 0 内容失败 —— 自检不通过")
            return 2

        all_ok = True
        n_hit = 0
        for idx, (name, apply_fn, expected) in enumerate(CASES, 1):
            saved = {}
            for rel in set(MIRROR_FILES + ["%s/%s" % (SRC_REL, f) for f in SOURCE_ORDER]
                           + MIRROR_PNGS + [PAPER_REL, TASKBOOK_REL]):
                p = os.path.join(mirror, rel.replace("/", os.sep))
                if os.path.isfile(p):
                    with open(p, "rb") as fh:
                        saved[rel] = fh.read()
            try:
                apply_fn(mirror)
            except SystemExit as exc:
                print("  例 %02d %s ⇒ 篡改失败：%s" % (idx, name, exc))
                all_ok = False
                break
            # 篡改后跑两遍：一遍复用基线那个 Ctx（锁死「缓存必须随内容失效」），
            # 一遍新建 Ctx（锁死「与对象复用无关」）。两遍都必须命中期望。
            got_reuse = _run_static(mirror, mctx)
            got = _run_static(mirror)
            match = (got is not None and got_reuse is not None
                     and got == sorted(expected) and got_reuse == sorted(expected))
            # 还原：先把被删掉的补回来，再逐字节写回原内容
            for rel, blob in saved.items():
                _write(mirror, rel, blob)
            restored = _run_static(mirror, mctx)
            ok = match and restored == []
            all_ok = all_ok and ok
            n_hit += 1 if ok else 0
            print("  例 %02d %s" % (idx, name))
            print("        期望 FAIL 集 %s" % sorted(expected))
            print("        实测（复用基线 Ctx）%s ／（新建 Ctx）%s ⇒ %s"
                  % (got_reuse, got, "一致" if match else "不一致"))
            print("        还原后 FAIL 集 %s ⇒ %s"
                  % (restored, "OK" if restored == [] else "还原不干净"))
        print()
        if all_ok:
            print("自检结论：原样对照 0 内容失败；%d 个反例逐例「期望 FAIL 集 ＝ 实测 FAIL 集」"
                  "（复用 Ctx 与新建 Ctx 两遍都命中）、还原复核失败集为空 ⇒ 退出码 0"
                  % len(CASES))
            return 0
        print("自检结论：存在不一致（逐例命中 %d／%d）⇒ 退出码 2" % (n_hit, len(CASES)))
        return 2
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="第 11 阶段专项验收门禁（《28》第八节 23 行）")
    ap.add_argument("--profile", choices=["full", "static"], default="full")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    print("=" * 78)
    print("第 11 阶段（论文撰写与材料整理）专项验收门禁")
    print("=" * 78)
    print("工作区：%s" % ROOT)
    print("档位：%s" % args.profile)
    print("行结构：从《28》第八节解析并与脚本注册集合逐行比对")
    print()

    ctx = Ctx(ROOT, args.profile)
    rows, rk, rd = run_all(ctx)
    if rows is None:
        print("[FAIL] 行结构自检：%s" % rd)
        print("结论：行结构错误 ⇒ 退出码 2")
        return 2
    print("[OK  ] 行结构自检：%s" % rd)
    print()
    return summarize(rows)


if __name__ == "__main__":
    sys.exit(main())
