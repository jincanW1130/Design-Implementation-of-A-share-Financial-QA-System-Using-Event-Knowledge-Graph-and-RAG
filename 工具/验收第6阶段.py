#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""《16-事件抽取与知识图谱（第六阶段）》与第 6 阶段交付物的阶段级验收（《15》第八节 逐行落地）。

与另外两个脚本的分工（不重复实现）：
  * `工具\跨文档核验.py` —— 全工作区 Markdown 的通用一致性（检查 A～N，含禁用词 J、索引登记 L、
    《02》版本 N1／N2）。本脚本**不调用它**，只核验它存在与否；操作者应另行运行它。
  * `代码\抽取与图谱\write_graph.py --verify-only` 与 `graph_check.json` —— 管线自身的机检
    （T6 的 17 项）。它是**被验收对象的内建自检**，本脚本不采信其结论，一律从导出物、缓存与
    数据集重算；唯一显式引用 `graph_check.json` 的地方是 J 组的「本次重跑机检快照」一行，
    输出里标出读的是报告，且不作为任何检查的唯一依据。
  * 本脚本 —— 第 6 阶段的**验收闸门**：把《15》第八节 的验收标准逐行实现为 A～X 共 24 组检查，
    数值一律从 v2.1 数据集、图谱导出物、缓存管线产物、抽取评测集与《10》重新推导后比对。

**行数与编号**：《15》第八节 的表格当前有 **29 行**（含末行「全套检查通过」）。本脚本逐行落地
这 29 行，行 → 检查组的映射直接写在每组标题里（例如「C、《15》第八节 第 3～4 行」）。

用法：

    python 工具\验收第6阶段.py                      # 默认 --profile pilot：核验试跑产物
    python 工具\验收第6阶段.py --profile v21        # 核验全量产物（图谱导出\v2.1\）
    python 工具\验收第6阶段.py --work-root <目录> --export-dir <目录>
                                                    # 覆盖管线工作目录与导出目录（负向自测用）
    python 工具\验收第6阶段.py --no-replay          # 只做静态检查，跳过镜像重跑（记 SKIP）
    python 工具\验收第6阶段.py --keep-tmp           # 保留镜像重跑用的临时目录，便于事后复核

**profile 口径（本脚本的路径开关）**：
  * `pilot`（默认）—— 核验 `阶段06-事件抽取与知识图谱\_试跑_图谱管线\` 与
    `代码\抽取与图谱\_试跑\extracted.jsonl`（12 篇试点缓存）。默认取 pilot 是因为全量产物由
    并行会话产出、当前尚未落盘；全量跑完后按 `--profile v21` 即可，**脚本不需要改一个字**。
  * `v21` —— 核验 `阶段05-数据准备\数据集\_抽取缓存\v2.1\图谱管线\` 与
    `阶段06-事件抽取与知识图谱\图谱导出\v2.1\`。
  两个 profile 的目录一律经 `代码\抽取与图谱\config.pipeline_paths()` 解析，不在本脚本里写死。

**降级口径（不把「试跑不覆盖」当成缺陷，也不把真缺陷降级掉）**：
  * 只有真的「全量才可能成立」的检查才降级：8 种事件类型／9 条核心关系在**导出物中全覆盖**
    （12 篇试点必然覆盖不到），以及数据集指纹基线缺失时的比对。它们在 pilot 模式下输出
    `[SKIP]` 并写明原因、**不计入失败**，在 v21 模式下是硬检查。
  * 与 profile 无关的检查（260 条评测集、《16》必备小节、证据可回溯、配置四要素、《02》TBD、
    数据集只读等）**不做任何降级**：试跑期间它们该失败就失败（例如《16》尚未落盘），如实记入
    失败项，不用 SKIP 掩盖。

退出码：0 = 全部检查通过（SKIP 不影响退出码）；1 = 存在失败项或输入缺失。

纪律：
  * 本脚本对交付物**只读**：唯一的写动作发生在系统临时目录里——把 `代码\抽取与图谱\*.py`、
    数据集 v2.1 的正文与文本块、抽取缓存、抽取结果与管线产物**镜像**到一个临时根目录，在那里
    复跑 `run_all.py`（以及四个环节脚本、`--from` 续跑），再与工作区里的原产物逐字节比对。
    **绝不写入工作区的任何交付目录**（《15》第五节 硬约束 6、10、11）。
  * 参数一律取 `代码\抽取与图谱\config.py` 与《10》（本体、事件类型、关系、role 取值、编号规则、
    导出字段、正文抽样参数都在那里）。本脚本自带的常量只有两处例外，均已就地注释：
    ① R 组的**数据集指纹基线候选落点**（任务书未规定基线文件名，属本工具的发现规则）；
    ② D 组对 chunk 的查法（用 chunk_id → doc_id 的映射重算，不读任何报告）。
  * 术语：FAISS 一律称「向量索引／向量检索组件」；禁用词「向量」与「数据库」的连写在本文件里
    以拼接方式构造（`BANNED_VDB`），免得本脚本自己被术语检查命中（同 `验收第5阶段数据.py`）。
  * 密钥不入仓库：本脚本只**扫描**密钥形态，不读取、不打印任何密钥取值。
  * 证据一律带文件名与行号／行序：CSV 记「第 N 行（含表头）」、JSONL 记「第 N 行」、
    Markdown 记「第 N 行」、JSON 记字段路径。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import fnmatch
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict

# 控制台为 GBK，先把标准输出重设成 UTF-8 再打印中文。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE6 = os.path.join(ROOT, "阶段06-事件抽取与知识图谱")
CODE_GRAPH = os.path.join(ROOT, "代码", "抽取与图谱")
CODE_PREP = os.path.join(ROOT, "代码", "数据准备")
TOOLS = os.path.join(ROOT, "工具")
sys.path.insert(0, CODE_GRAPH)

import config  # noqa: E402  第 6 阶段唯一参数来源（路径、阈值、冻结 schema 都在这里）

P15 = os.path.join(STAGE6, "15-第6阶段任务书（事件抽取与知识图谱）.md")
P16 = os.path.join(STAGE6, "16-事件抽取与知识图谱（第六阶段）.md")
P10 = os.path.join(ROOT, "阶段04-系统总体设计", "10-系统总体设计（第四阶段）.md")
P02 = os.path.join(ROOT, "02-项目执行总控文档.md")
P00 = os.path.join(ROOT, "00-项目总览与索引.md")
GITIGNORE = os.path.join(ROOT, ".gitignore")
CROSS_DOC = os.path.join(TOOLS, "跨文档核验.py")

EVAL_DIR = os.path.join(ROOT, "阶段05-数据准备", "数据集", "抽取评测集", config.DATASET_VERSION)
EVAL_DEV = os.path.join(EVAL_DIR, "dev.jsonl")
EVAL_TEST = os.path.join(EVAL_DIR, "test.jsonl")
EVAL_NOTE = os.path.join(EVAL_DIR, "标注说明.md")
EVAL_STATS = os.path.join(EVAL_DIR, "分层统计.json")

# 数据集「只读」的指纹基线候选落点（任务书未规定基线文件名，故由本工具按下列顺序发现；
# 这是本文件里「参数一律取自 config」的一处例外登记，理由见 R 组注释）：
#   1) <管线工作目录>\dataset_fingerprint.json —— 本阶段自行固定的开工指纹（首选，JSON）；
#   2) 第 5 阶段封版后的目录清单（代码\数据准备\勘察\manifest_宽口径_*.json：含 root 与逐文件 sha256）；
#   3) 《16》正文里与 documents.jsonl／chunks.jsonl 同行的 64 位 sha256（仅作补充）。
BASELINE_LOCAL = "dataset_fingerprint.json"
BASELINE_STAGE5 = [
    os.path.join(CODE_PREP, "勘察", "manifest_宽口径_最终.json"),
    os.path.join(CODE_PREP, "勘察", "manifest_宽口径_复跑.json"),
    os.path.join(CODE_PREP, "勘察", "manifest_宽口径_一轮.json"),
]

BANNED_VDB = "向量" + "数据库"        # 拼接构造：本文件源码内不出现该连写

_ap = argparse.ArgumentParser(
    description="第 6 阶段（事件抽取与知识图谱）：阶段级验收（《15》第八节 逐行）")
_ap.add_argument("--profile", default="pilot", choices=["pilot", "v21"],
                 help="pilot＝试跑产物（默认）；v21＝全量产物（图谱导出\\v2.1\\）")
_ap.add_argument("--work-root", default=None, help="覆盖管线工作目录（负向自测用）")
_ap.add_argument("--export-dir", default=None, help="覆盖图谱导出目录（负向自测用）")
_ap.add_argument("--no-replay", action="store_true",
                 help="跳过镜像重跑比对（H／I／J／K／S 组各项记为 SKIP）")
_ap.add_argument("--keep-tmp", action="store_true", help="保留镜像重跑用的临时目录")
_ap.add_argument("--doc16", default=None,
                 help="覆盖《16》路径（默认 阶段06-…\\16-事件抽取与知识图谱（第六阶段）.md）；"
                      "供负向自测与 T9 前演练用")
_ap.add_argument("--p00", default=None, help="覆盖《00》索引路径（同上，供自测用）")
ARGS = _ap.parse_args()

PROFILE = ARGS.profile

if ARGS.doc16:
    P16 = os.path.abspath(ARGS.doc16)
if ARGS.p00:
    P00 = os.path.abspath(ARGS.p00)


def pipeline_paths(profile, work_root=None, export_dir=None):
    """按 profile 解析落点；两个覆盖参数只给负向自测用，不改变默认口径。"""
    paths = dict(config.pipeline_paths(profile))
    names = config.GRAPH_PIPELINE["files"]
    if work_root:
        paths["work_root"] = os.path.abspath(work_root)
        paths["disambig_dir"] = os.path.join(
            paths["work_root"], config.GRAPH_PIPELINE["subdirs"]["disambig"])
        paths["dedup_dir"] = os.path.join(
            paths["work_root"], config.GRAPH_PIPELINE["subdirs"]["dedup"])
        for key in ("alias_table", "disambiguation", "unresolved"):
            paths[key] = os.path.join(paths["disambig_dir"], names[key])
        for key in ("merge_log", "events_merged", "merge_summary", "dedup_self_test"):
            paths[key] = os.path.join(paths["dedup_dir"], names[key])
        paths["graph_check"] = os.path.join(paths["work_root"], names["graph_check"])
        paths["manifest"] = os.path.join(paths["work_root"], names["manifest"])
        paths["log_first"] = os.path.join(paths["work_root"], config.RUN_ALL["log_first"])
        paths["log_second"] = os.path.join(paths["work_root"], config.RUN_ALL["log_second"])
    if export_dir:
        paths["export_dir"] = os.path.abspath(export_dir)
    if work_root or export_dir:
        for key in ("nodes", "edges", "graph_stats", "replay_cypher"):
            paths[key] = os.path.join(paths["export_dir"], names[key])
    return paths


PATHS = pipeline_paths(PROFILE, ARGS.work_root, ARGS.export_dir)


# --------------------------------------------------------------------------
# 报告器：沿用《验收第4阶段文档.py》《验收第5阶段数据.py》的 [OK ]/[FAIL] + 末尾结论布局，
# 另加 [SKIP]（pilot 模式下不适用、不计入失败）与 note()（只打印证据，不计入项数）。
# --------------------------------------------------------------------------
results = []          # [(status, label, detail)]，status ∈ {OK, FAIL, SKIP}
fails = []            # [label]
fail_evidence = []    # [(label, detail)]


def _emit(status, label, detail=""):
    print("  [%s] %s%s" % (status.ljust(4), label, ("  " + detail) if detail else ""))
    results.append((status, label, detail))


def chk(ok, label, detail=""):
    if ok:
        _emit("OK", label, detail)
    else:
        _emit("FAIL", label, detail)
        fails.append(label)
        fail_evidence.append((label, detail))


def skip(label, detail=""):
    """pilot 模式下不适用、或按命令行显式跳过的项：打印原因，不计入失败。"""
    _emit("SKIP", label, detail)


def note(label, detail=""):
    """只打印证据行（不计入通过／失败项数）。"""
    print("  [OK ] %s%s" % (label, ("  " + detail) if detail else ""))


def br(seq, limit=4):
    """把序列压成一行：最多列 limit 项，超出只报总数。"""
    seq = list(seq)
    head = "、".join(str(x) for x in seq[:limit])
    return head + ("…（共 %d 个）" % len(seq) if len(seq) > limit else "")


# 兜底：本脚本是线性执行的，若某处意外抛异常，末尾的「最终」行就不会打印——那等于静默失败。
# 用 atexit 守住：异常退出时补一行标准格式的「最终」并按失败记账（异常本身由 Python 打 Traceback）。
_SUMMARY_DONE = False


def _exit_guard():
    if _SUMMARY_DONE:
        return
    print()
    print("  [FAIL] 验收脚本自身抛异常中断：详见上方 Traceback（按失败记账）")
    print("  最终：检查项 %d 项，通过 %d，失败 %d"
          % (len(results), sum(1 for st, _l, _d in results if st == "OK"), len(fails) + 1))
    print("=" * 78)


import atexit  # noqa: E402  （放在报告器之后：兜底函数要用 results／fails）

atexit.register(_exit_guard)


# --------------------------------------------------------------------------
# 通用读取与小工具
# --------------------------------------------------------------------------
def read_text(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_json(path, default=None):
    if not os.path.isfile(path):
        return default
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def read_jsonl(path):
    """返回 [(行号, 对象)]；坏行抛出 ValueError（含文件名与行号），便于定位。"""
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            rows.append((i, json.loads(line)))
    return rows


def read_csv_rows(path):
    """返回 (表头, [(行号, {列名: 单元格})])，行号按文本行计（表头＝第 1 行）。缺失文件返回 ([], [])。"""
    if not os.path.isfile(path):
        return [], []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        raw = list(csv.reader(fh))
    if not raw:
        return [], []
    header = raw[0]
    rows = []
    for i, cells in enumerate(raw[1:], 2):
        if len(cells) == 1 and not cells[0].strip():
            continue
        rows.append((i, dict(zip(header, cells + [""] * max(0, len(header) - len(cells))))))
    return header, rows


def sha256_file(path):
    if not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def same_bytes(path_a, path_b):
    if not (os.path.isfile(path_a) and os.path.isfile(path_b)):
        return False
    return sha256_file(path_a) == sha256_file(path_b)


def cell(row, key):
    return str(row.get(key) or "").strip()


def parse_date(value):
    """把语料里出现的四种日期写法折成 date；解析不出返回 None（不猜）。"""
    if value is None:
        return None
    s = str(value).strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", s)
    if not m:
        m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", s)
    if not m:
        return None
    try:
        return _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def dup_groups(values):
    cnt = Counter(values)
    return {k: v for k, v in cnt.items() if v > 1}


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def to_float(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def norm_ws(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def strip_ws(text):
    return re.sub(r"[\s　]+", "", str(text or ""))


def line_no(text, needle):
    for i, line in enumerate(str(text or "").split("\n"), 1):
        if needle in line:
            return i
    return None


HEADING_RE = re.compile(r"^(#{2,4})\s*((?:\d+(?:\.\d+)*)?)[\s、.]*(.+?)\s*$")


def headings(text):
    out = []
    for i, line in enumerate(text.split("\n"), 1):
        m = HEADING_RE.match(line)
        if m and m.group(3):
            out.append((i, m.group(3)))
    return out


def find_heading(text, name):
    key = strip_ws(name)
    for ln, title in headings(text):
        if key and key in strip_ws(title):
            return ln, title
    return None, None


def find_line(text, *keywords, negate=()):
    """按关键字找行：全部 keywords 都出现且不含 negate 关键字时命中（返回 (行号, 行内容)）。"""
    for i, line in enumerate(str(text or "").split("\n"), 1):
        if all(k in line for k in keywords) and not any(n in line for n in negate):
            return i, line.strip()
    return None, None


NEG_CTX = re.compile(r"不引入|不研究|不接入|不处理|不提供|不涉及|不使用|不写|不得|禁止|不再|不是|"
                     r"不能|不作|不含|不存在|不按|不采用|不出现|未出现|未有|没有|无 |无、|"
                     r"无[\"“”'‘’（(「『【〔〈《]|除外|边界|非 |vs|不称|never|免除")


def scan_terms(terms, targets, ignore_negation=False):
    """在 [(标签, 文本)] 里逐行扫词；返回 [(标签, 行号, 词, 行内容, 是否否定语境)]。"""
    hits = []
    for label, text in targets:
        for i, line in enumerate(str(text or "").split("\n"), 1):
            for term in terms:
                if term and term in line:
                    neg = bool(NEG_CTX.search(line))
                    if ignore_negation or not neg:
                        hits.append((label, i, term, line.strip(), neg))
    return hits


def iter_files(dirpath):
    if not os.path.isdir(dirpath):
        return
    for base, _dirs, files in os.walk(dirpath):
        for name in sorted(files):
            yield os.path.join(base, name)


def rel_to_root(path):
    try:
        return os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:
        return path


def gitignore_rules(path):
    rules = []
    for i, line in enumerate(str(read_text(path, default="") or "").split("\n"), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        rules.append((i, s))
    return rules


def gitignore_match(pattern, relpath):
    """朴素的 .gitignore 语义（覆盖本项目用到的形态：根锚定目录／文件模式、`*` 通配、裸名）。"""
    p = pattern.replace("\\", "/").lstrip("/")
    target = relpath.replace("\\", "/").lstrip("/")
    if p.endswith("/"):
        p = p[:-1]
        return target == p or target.startswith(p + "/")
    if "/" in p:
        return fnmatch.fnmatch(target, p)
    return any(fnmatch.fnmatch(seg, p) for seg in target.split("/"))


# --------------------------------------------------------------------------
# 输入
# --------------------------------------------------------------------------
print("=" * 78)
print("第 6 阶段（事件抽取与知识图谱）阶段级验收：《16》、缓存管线、图谱导出物、评测集与代码")
print("=" * 78)
print("  工作区根目录：  %s" % ROOT)
print("  profile：       %s（%s）"
      % (PROFILE, "试跑产物：12 篇试点缓存" if PROFILE == "pilot" else "全量产物：v2.1 全量缓存"))
print("  管线工作目录：  %s" % PATHS["work_root"])
print("  图谱导出目录：  %s" % PATHS["export_dir"])
print("  抽取结果：      %s" % PATHS["extract_records"])
print("  冻结参数来源：  %s" % os.path.join(CODE_GRAPH, "config.py"))
print("  《16》交付文档：%s%s" % (P16, "" if os.path.isfile(P16) else "   ← 尚未落盘（T9 产出）"))
print("  重跑比对：      %s"
      % ("关闭（--no-replay：H／I／J／K／S 组记 SKIP）" if ARGS.no_replay
         else "在系统临时目录镜像重跑（只读交付物，绝不写入工作区）"))
if ARGS.work_root or ARGS.export_dir:
    print("  目录覆盖：      work-root=%s、export-dir=%s（负向自测）"
          % (ARGS.work_root or "默认", ARGS.export_dir or "默认"))
print()

_missing = [p for p in (P15, P10, P02, P00, GITIGNORE) if not os.path.isfile(p)]
if not os.path.isfile(os.path.join(CODE_GRAPH, "config.py")):
    _missing.append(os.path.join(CODE_GRAPH, "config.py"))
if _missing:
    for _p in _missing:
        print("缺少输入文件：%s" % _p)
    sys.exit(1)

t15 = read_text(P15)
t10 = read_text(P10)
t02 = read_text(P02)
t00 = read_text(P00)
t16 = read_text(P16, default=None)          # 《16》可能尚未落盘：相关检查按失败记账，不静默跳过

DOCS_P = config.DOCS_PATH
CHUNKS_P = config.CHUNKS_PATH
doc_rows = read_jsonl(DOCS_P)
chunk_rows = read_jsonl(CHUNKS_P)
docs = [r for _, r in doc_rows]
chunk_owner = {str(c.get("chunk_id")): str(c.get("doc_id")) for _, c in chunk_rows}
chunk_line = {str(c.get("chunk_id")): ln for ln, c in chunk_rows}
doc_ids = {str(d.get("doc_id")) for d in docs}

nodes_header, nodes_rows = read_csv_rows(PATHS["nodes"])
edges_header, edges_rows = read_csv_rows(PATHS["edges"])
node_by_id = {r.get("node_id"): r for _, r in nodes_rows}
label_by_id = {k: (v.get("label") or "") for k, v in node_by_id.items()}
event_type_by_id = {k: (v.get("event_type") or "") for k, v in node_by_id.items()
                    if v.get("label") == "Event"}
edge_at = list(edges_rows)

stats = read_json(PATHS["graph_stats"], default=None) or {}
graph_check = read_json(PATHS["graph_check"], default=None) or {}
merge_summary = read_json(PATHS["merge_summary"], default=None) or {}
dedup_self_test = read_json(PATHS["dedup_self_test"], default=None) or {}
disambig = read_json(PATHS["disambiguation"], default=None) or {}


# 《10》解析出的冻结 schema（不写死：本体、事件类型、关系、role 取值、六张表、六项核心属性
# 全部从《10-系统总体设计（第四阶段）》第4.4／4.5节 解析，再与 config 比对）。
def ontology_from_p10(text):
    out = {"entities": [], "events": [], "relations": [], "roles": [],
           "issued_for": [], "tables": [], "event_attrs": []}
    for line in text.split("\n"):
        m = re.match(r"^\|\s*实体类型\s*\d+\s*\|\s*([^|]+?)\s*\|", line)
        if m:
            mm = re.search(r"([A-Z][A-Za-z]+)", m.group(1))
            if mm and mm.group(1) not in out["entities"]:
                out["entities"].append(mm.group(1))
        m = re.match(r"^\|\s*核心事件类型[^|]*\|\s*([^|]+?)\s*\|", line)
        if m:
            for name in re.split(r"[、,，]", m.group(1).replace("*", "").strip()):
                name = name.strip()
                if name.endswith("事件"):
                    name = name[:-2]
                if name and name not in out["events"]:
                    out["events"].append(name)
    # 只认 cypher 代码块里的关系行（行首就是 `(起点)-[:关系`）；否则 第4.5.2节 正文里
    # 「已删除的 (Event)-[:INVOLVES]->(Company)」这种**登记性引用**会被误算成本体的一员。
    for mm in re.finditer(r"^\s*\([^)\n]*\)\s*-\s*\[:([A-Z][A-Z_]+)", text, re.M):
        if mm.group(1) not in out["relations"]:
            out["relations"].append(mm.group(1))
    m = re.search(r"role 的取值范围为\s*\{([^}]+)\}", text)
    if m:
        out["roles"] = [x.strip() for x in re.split(r"[、,，]", m.group(1)) if x.strip()]
    m = re.search(r"ISSUED_BY\s*仅用于([^。\n]+)", text)
    if m:
        out["issued_for"] = re.findall(r"([\u4e00-\u9fa5]{2})事件", m.group(1))
    m = re.search(r"恒为六张\**——([^，,]+)，不新增表", text)
    if m:
        out["tables"] = [x.strip() for x in re.split(r"[、,，]", m.group(1)) if x.strip()]
    m = re.search(r"六项核心属性\**：(.{0,400}?)(?:\n|；)", text)
    if m:
        for name in re.findall(r"([a-z][a-z_]{2,})(?:\s*（|\s*、|\s*。|\s*\*\*)", m.group(1)):
            if name not in out["event_attrs"]:
                out["event_attrs"].append(name)
    return out


P10_ONT = ontology_from_p10(t10)


def p10_line(needle):
    return line_no(t10, needle)


# ==========================================================================
print(); print("=" * 78)
print("A、《15》第八节 第 1 行：《16》的 9 个必备小节齐全（逐节检查）")
print("=" * 78)

m_req = re.search(r"(\d+)\s*个必备小节齐全[：:]\s*([^|\n]+)", t15)
REQ_SECTIONS = [s.strip() for s in re.split(r"[／/]", m_req.group(2))] if m_req else []
chk(m_req is not None and len(REQ_SECTIONS) > 0,
    "A1 从《15》第八节 解析出必备小节清单（不写死小节名）",
    "实测 解析 %d 个：%s（来源：《15》第 %s 行）"
    % (len(REQ_SECTIONS), "／".join(REQ_SECTIONS) or "无",
       line_no(t15, "个必备小节齐全") if m_req else "?"))
chk(m_req is not None and len(REQ_SECTIONS) == int(m_req.group(1)),
    "A2 解析出的数目 == 《15》第八节 声明的数目",
    "实测 《15》声明 %s 个、解析得 %d 个" % (m_req.group(1) if m_req else "?", len(REQ_SECTIONS)))

chk(t16 is not None, "A3 《16》存在且可读（T9 阶段交付文档）",
    "实测 %s：%s" % (rel_to_root(P16), "可读" if t16 is not None else "缺失（T9 尚未产出）"))

A_missing, A_pos = [], []
for name in REQ_SECTIONS:
    if t16 is None:
        A_missing.append(name)
        continue
    ln, title = find_heading(t16, name)
    if ln is None:
        A_missing.append(name)
    else:
        A_pos.append((ln, name, title))
chk(t16 is not None and not A_missing,
    "A4 9 个必备小节逐节命中（二～四级标题，按《15》清单逐名）",
    "实测 %d/%d 命中；缺失 %s" % (len(REQ_SECTIONS) - len(A_missing), len(REQ_SECTIONS),
                                   "、".join(A_missing) or "无"))
if A_pos:
    note("A5 小节命中位置（证据）",
         "；".join("%s→《16》第%d行「%s」" % (n, ln, ti) for ln, n, ti in A_pos[:9]))
if t16 is not None:
    h2 = [(ln, ti) for ln, ti in headings(t16) if t16.split("\n")[ln - 1].startswith("## ")]
    chk(len(h2) >= len(REQ_SECTIONS), "A6 《16》二级标题数与必备小节数相称",
        "实测 二级标题 %d 个，必备小节 %d 个，清单命中 %d 个"
        % (len(h2), len(REQ_SECTIONS), len(A_pos)))
else:
    chk(False, "A6 《16》二级标题数与必备小节数相称（《16》缺失，无法核验）",
        "实测 《16》缺失：%s" % rel_to_root(P16))


# ==========================================================================
print(); print("=" * 78)
print("B、《15》第八节 第 2 行：本体一致性（6 类实体／8 种事件类型／9 条核心关系不多不少，"
      "无 Product／Location、无 INVOLVES）")
print("=" * 78)

B_ENT = list(P10_ONT["entities"])
B_EVT = list(P10_ONT["events"])
B_REL = list(P10_ONT["relations"])
chk(B_ENT == list(config.ENTITY_TYPES) and len(B_ENT) == 6,
    "B1 《10》表 4-8 解析的 6 类实体 == config.ENTITY_TYPES",
    "实测 《10》第 %s 行：%s；config：%s"
    % (p10_line("实体类型 1"), "、".join(B_ENT) or "解析失败", "、".join(config.ENTITY_TYPES)))
chk(B_EVT == list(config.EVENT_TYPES) and len(B_EVT) == 8,
    "B2 《10》表 4-8 解析的 8 种事件类型 == config.EVENT_TYPES",
    "实测 《10》第 %s 行：%s；config：%s"
    % (p10_line("核心事件类型 1"), "、".join(B_EVT) or "解析失败", "、".join(config.EVENT_TYPES)))
chk(B_REL == list(config.RELATIONS) and len(B_REL) == 9,
    "B3 《10》第4.5.2节 cypher 块解析的 9 条核心关系 == config.RELATIONS",
    "实测 《10》第 %s 行：%s；config：%s"
    % (p10_line("BELONGS_TO"), "、".join(B_REL) or "解析失败", "、".join(config.RELATIONS)))
ALL_LABELS = set(config.ENTITY_TYPES) | {config.DOCUMENT_LABEL}
forbidden = [x for x in ("Product", "Location") if x in B_ENT + B_REL + list(config.ENTITY_TYPES)]
chk(not forbidden and "INVOLVES" not in B_REL + list(config.RELATIONS),
    "B4 无 Product／Location、无 INVOLVES（不复活已删除的关系）",
    "实测 Product／Location 命中 %s；INVOLVES 命中 %s；Document：%s"
    % (forbidden or "无", "有" if "INVOLVES" in B_REL + list(config.RELATIONS) else "无",
       "被当第七类实体" if config.DOCUMENT_LABEL in config.ENTITY_TYPES else "独立证据标签，不在 6 类实体中"))
m_decl = re.search(r"(\d+)\s*类实体\D{0,8}(\d+)\s*种事件类型\D{0,8}(\d+)\s*条核心关系", t15)
decl_ok = bool(m_decl) and [int(x) for x in m_decl.groups()] == [6, 8, 9]
chk(decl_ok and [len(B_ENT), len(B_EVT), len(B_REL)] == [6, 8, 9],
    "B5 《15》声明的 6 类实体／8 种事件类型／9 条核心关系 == 实测",
    "实测 《15》第 %s 行声明「%s」；解析得 实体 %d／事件 %d／关系 %d"
    % (line_no(t15, "类实体"), m_decl.group(0) if m_decl else "未解析到",
       len(B_ENT), len(B_EVT), len(B_REL)))

labels_used = sorted({(r.get("label") or "") for _, r in nodes_rows})
rel_used = sorted({(r.get("relation") or "") for _, r in edges_rows})
evt_used = sorted({v for v in event_type_by_id.values() if v})
chk(set(labels_used) <= ALL_LABELS,
    "B6 导出物节点标签 ⊆ 6 类实体 ＋ Document（不多）",
    "实测 标签 %d 个：%s；越界 %s"
    % (len(labels_used), "、".join(labels_used) or "无节点",
       "、".join(sorted(set(labels_used) - ALL_LABELS)) or "无"))
chk(set(rel_used) <= set(config.RELATIONS),
    "B7 导出物关系类型 ⊆ 9 条核心关系（不多）",
    "实测 关系 %d 种：%s；越界 %s"
    % (len(rel_used), "、".join(rel_used) or "无关系",
       "、".join(sorted(set(rel_used) - set(config.RELATIONS))) or "无"))
chk(set(evt_used) <= set(config.EVENT_TYPES),
    "B8 导出物 event_type 取值 ⊆ 8 种事件类型（不多）",
    "实测 事件类型 %d 种：%s；越界 %s"
    % (len(evt_used), "、".join(evt_used) or "无事件",
       "、".join(sorted(set(evt_used) - set(config.EVENT_TYPES))) or "无"))

bad_endpoint = []
for ln, e in edge_at:
    spec = config.RELATION_SCHEMA.get(cell(e, "relation"))
    if not spec:
        continue
    hl, tl = label_by_id.get(cell(e, "head_id")), label_by_id.get(cell(e, "tail_id"))
    if hl not in spec["domain"] or tl not in spec["range"]:
        bad_endpoint.append("第%d行 %s %s→%s"
                            % (ln, cell(e, "relation"), hl or "<未定义>", tl or "<未定义>"))
chk(not bad_endpoint,
    "B9 每条边的起止标签符合 config.RELATION_SCHEMA 的 domain／range",
    "实测 检查 %d 条边；违例 %d 条%s"
    % (len(edge_at), len(bad_endpoint), "：" + br(bad_endpoint) if bad_endpoint else ""))

miss_rel = [r for r in config.RELATIONS if r not in rel_used]
miss_evt = [e for e in config.EVENT_TYPES if e not in evt_used]
if PROFILE == "v21":
    chk(not miss_rel and not miss_evt,
        "B10 全量：9 条关系与 8 种事件类型在导出物中都有条目（不少）",
        "实测 关系 %d/9（缺 %s）；事件类型 %d/8（缺 %s）"
        % (len(rel_used), "、".join(miss_rel) or "无", len(evt_used), "、".join(miss_evt) or "无"))
else:
    skip("B10 全量：9 条关系与 8 种事件类型在导出物中都有条目（不少）",
         "pilot 模式：12 篇试点实测覆盖 关系 %d/9（缺 %s）、事件类型 %d/8（缺 %s）；"
         "「不少」只在全量模式（--profile v21）下判定，试跑用 N 组的评测集条目检查兜底"
         % (len(rel_used), "、".join(miss_rel) or "无",
            len(evt_used), "、".join(miss_evt) or "无"))

# ==========================================================================
print(); print("=" * 78)
print("C、《15》第八节 第 3～4 行：证据属性口径（除 EVIDENCED_BY 外的 8 条关系带齐三项且无空值；"
      "EVIDENCED_BY 不带三项、终点是 Document）")
print("=" * 78)

EVID_ATTRS = list(config.EVIDENCE_ATTRS)
EVIDENCED = "EVIDENCED_BY"
chk(bool(edges_header) and edges_header == list(config.GRAPH["edge_columns"]),
    "C1 edges.csv 表头 == config.GRAPH[\"edge_columns\"]（含三项证据列）",
    "实测 表头 %d 列：%s；config 声明 %d 列：%s"
    % (len(edges_header), "、".join(edges_header) or "读不到",
       len(config.GRAPH["edge_columns"]), "、".join(config.GRAPH["edge_columns"])))

non_ev = [(ln, r) for ln, r in edge_at if cell(r, "relation") != EVIDENCED]
ev_rows = [(ln, r) for ln, r in edge_at if cell(r, "relation") == EVIDENCED]
missing_attr = []
for ln, r in non_ev:
    for col in EVID_ATTRS:
        if not cell(r, col):
            missing_attr.append("第%d行 %s 缺 %s" % (ln, cell(r, "relation"), col))
chk(bool(non_ev) and not missing_attr,
    "C2 除 EVIDENCED_BY 外的 %d 条关系都带齐 source_doc_id／source_chunk_id／confidence 且无空值"
    % len(config.RELATIONS_FROM_MODEL),
    "实测 逐行检查 %d 条非 EVIDENCED_BY 边；三列有空值 %d 处%s；涉及关系 %s"
    % (len(non_ev), len(missing_attr), "：" + br(missing_attr) if missing_attr else "",
       "、".join(sorted({cell(r, "relation") for _, r in non_ev})) or "无"))
rel_checked = sorted({cell(r, "relation") for _, r in non_ev})
chk(set(rel_checked) <= set(config.RELATIONS_FROM_MODEL),
    "C3 非 EVIDENCED_BY 的关系取值都落在 config 的 8 条 from_model 关系内",
    "实测 实测取值 %s；config.RELATIONS_FROM_MODEL %s"
    % ("、".join(rel_checked) or "无", "、".join(config.RELATIONS_FROM_MODEL)))

bad_conf, bad_num = [], []
for ln, r in non_ev:
    c = to_float(cell(r, "confidence"))
    if c is None or not (config.CONFIDENCE_MIN <= c <= config.CONFIDENCE_MAX):
        bad_conf.append("第%d行 confidence=%r" % (ln, cell(r, "confidence")))
    if to_int(cell(r, "source_doc_id")) is None or to_int(cell(r, "source_chunk_id")) is None:
        bad_num.append("第%d行 source_doc_id=%r source_chunk_id=%r"
                       % (ln, cell(r, "source_doc_id"), cell(r, "source_chunk_id")))
chk(not bad_conf and not bad_num,
    "C4 三项取值域：confidence ∈ [%s, %s]，source_doc_id／source_chunk_id 为整数"
    % (config.CONFIDENCE_MIN, config.CONFIDENCE_MAX),
    "实测 confidence 越界 %d 处%s；编号非整数 %d 处%s"
    % (len(bad_conf), "：" + br(bad_conf) if bad_conf else "",
       len(bad_num), "：" + br(bad_num) if bad_num else ""))

with_attrs = []
for ln, r in ev_rows:
    carried = [c for c in EVID_ATTRS if cell(r, c)]
    if carried:
        with_attrs.append("第%d行携带 %s" % (ln, "、".join(carried)))
chk(bool(ev_rows) and not with_attrs,
    "C5 EVIDENCED_BY 不携带 source_doc_id／source_chunk_id／confidence 三项",
    "实测 EVIDENCED_BY %d 条；携带三项的 %d 条%s"
    % (len(ev_rows), len(with_attrs), "：" + br(with_attrs) if with_attrs else ""))

bad_tail = []
for ln, r in ev_rows:
    if label_by_id.get(cell(r, "tail_id")) != config.DOCUMENT_LABEL:
        bad_tail.append("第%d行 终点 %s 的标签=%s"
                        % (ln, cell(r, "tail_id"),
                           label_by_id.get(cell(r, "tail_id")) or "<未定义>"))
chk(not bad_tail,
    "C6 EVIDENCED_BY 的终点必须是 Document 节点",
    "实测 检查 %d 条；终点不是 Document 的 %d 条%s（起点是否为 Event 见 B9 的 domain／range）"
    % (len(ev_rows), len(bad_tail), "：" + br(bad_tail) if bad_tail else ""))


# ==========================================================================
print(); print("=" * 78)
print("D、《15》第八节 第 5 行：证据可回溯（每个 source_chunk_id 真实存在于 v2.1 的 "
      "chunks\\chunks.jsonl，且其 doc_id == 同一条事实的 source_doc_id）")
print("=" * 78)

miss_chunk, chunk_doc_mismatch, miss_doc = [], [], []
checked_pairs = 0
for ln, r in non_ev:
    cid, did = cell(r, "source_chunk_id"), cell(r, "source_doc_id")
    if not cid or not did:
        continue
    checked_pairs += 1
    if cid not in chunk_owner:
        miss_chunk.append("第%d行 source_chunk_id=%s" % (ln, cid))
    elif chunk_owner[cid] != did:
        chunk_doc_mismatch.append("第%d行 chunk=%s 的 doc_id=%s ≠ source_doc_id=%s"
                                  % (ln, cid, chunk_owner[cid], did))
    if did not in doc_ids:
        miss_doc.append("第%d行 source_doc_id=%s" % (ln, did))
chk(checked_pairs > 0 and not miss_chunk,
    "D1 每个 source_chunk_id 都存在于 v2.1 chunks\\chunks.jsonl 中",
    "实测 检查 %d 条事实；v2.1 文本块 %d 个；查不到的 %d 条%s"
    % (checked_pairs, len(chunk_owner), len(miss_chunk),
       "：" + br(miss_chunk) if miss_chunk else ""))
chk(not chunk_doc_mismatch,
    "D2 文本块所属 doc_id == 同一条事实的 source_doc_id",
    "实测 不一致 %d 条%s" % (len(chunk_doc_mismatch),
                              "：" + br(chunk_doc_mismatch) if chunk_doc_mismatch else ""))
bad_ev_doc = []
for ln, r in ev_rows:
    if cell(r, "tail_id") not in doc_ids:
        bad_ev_doc.append("第%d行 Document=%s" % (ln, cell(r, "tail_id")))
chk(not miss_doc and not bad_ev_doc,
    "D3 source_doc_id 与 EVIDENCED_BY 的 Document 都能回溯到 v2.1 clean\\documents.jsonl",
    "实测 v2.1 文档 %d 篇；source_doc_id 查不到 %d 处%s；EVIDENCED_BY 终点查不到 %d 处%s"
    % (len(doc_ids), len(miss_doc), "：" + br(miss_doc) if miss_doc else "",
       len(bad_ev_doc), "：" + br(bad_ev_doc) if bad_ev_doc else ""))
if checked_pairs:
    note("D4 可回溯读数（证据）",
         "实测 抽查首条：%s（chunk 在 chunks.jsonl 第 %s 行）；"
         "chunk_id → doc_id 映射由 chunks.jsonl 现场重算，不读任何报告"
         % (br(["第%d行 %s.%s=%s" % (non_ev[0][0], cell(non_ev[0][1], "relation"),
                                     "source_chunk_id", cell(non_ev[0][1], "source_chunk_id"))]),
            chunk_line.get(cell(non_ev[0][1], "source_chunk_id"), "?")))


# ==========================================================================
print(); print("=" * 78)
print("E、《15》第八节 第 6 行：Event 六项核心属性齐全（event_time 允许为空但必须计数登记）、"
      "role 取值、ISSUED_BY 的事件类型范围")
print("=" * 78)

EVENT_ATTRS = list(P10_ONT["event_attrs"])
chk(bool(nodes_header) and nodes_header == list(config.GRAPH["node_columns"]),
    "E1 nodes.csv 表头 == config.GRAPH[\"node_columns\"]（含事件六项核心属性列）",
    "实测 表头 %d 列：%s；config 声明 %d 列"
    % (len(nodes_header), "、".join(nodes_header) or "读不到", len(config.GRAPH["node_columns"])))
chk(EVENT_ATTRS == list(config.EVENT_CORE_ATTRS),
    "E2 《10》第4.5.1节 解析的六项核心属性 == config.EVENT_CORE_ATTRS",
    "实测 《10》第 %s 行解析：%s；config：%s"
    % (p10_line("六项核心属性"), "、".join(EVENT_ATTRS) or "解析失败",
       "、".join(config.EVENT_CORE_ATTRS)))

ev_nodes = [(ln, r) for ln, r in nodes_rows if (r.get("label") or "") == "Event"]
incomplete = []
for ln, r in ev_nodes:
    for attr in EVENT_ATTRS:
        if attr == "event_time":
            continue
        if not cell(r, attr):
            incomplete.append("第%d行 %s 的 %s 为空" % (ln, cell(r, "event_id"), attr))
chk(bool(ev_nodes) and not incomplete,
    "E3 每个 Event 节点六项核心属性齐全；除 event_time 外五项非空",
    "实测 Event %d 条；缺项 %d 处%s"
    % (len(ev_nodes), len(incomplete), "：" + br(incomplete) if incomplete else ""))

prefix_event = config.GRAPH["id_prefixes"]["Event"]
width = int(config.GRAPH["id_width"])
EID_RE = re.compile(r"^%s-\d{%d}$" % (re.escape(prefix_event), width))
bad_evt, bad_conf2, bad_eid = [], [], []
for ln, r in ev_nodes:
    if cell(r, "event_type") not in config.EVENT_TYPES:
        bad_evt.append("第%d行 event_type=%r" % (ln, cell(r, "event_type")))
    c = to_float(cell(r, "confidence"))
    if c is None or not (config.CONFIDENCE_MIN <= c <= config.CONFIDENCE_MAX):
        bad_conf2.append("第%d行 confidence=%r" % (ln, cell(r, "confidence")))
    if not EID_RE.match(cell(r, "event_id")):
        bad_eid.append("第%d行 event_id=%r" % (ln, cell(r, "event_id")))
chk(not bad_evt and not bad_conf2 and not bad_eid,
    "E4 event_type ∈ 8 种事件类型；confidence ∈ [0,1]；event_id 形如 %s-<4 位>" % prefix_event,
    "实测 非法 event_type %d 处%s；confidence 越界 %d 处%s；event_id 不合规则 %d 处%s"
    % (len(bad_evt), "：" + br(bad_evt) if bad_evt else "",
       len(bad_conf2), "：" + br(bad_conf2) if bad_conf2 else "",
       len(bad_eid), "：" + br(bad_eid) if bad_eid else ""))

null_time = [r for _, r in ev_nodes if not cell(r, "event_time")]
registered_null = (stats.get("event_core_attributes") or {}).get("event_time_null_count")
rate = (len(null_time) / len(ev_nodes)) if ev_nodes else 0.0
chk(registered_null == len(null_time),
    "E5 event_time 允许为空，但空值必须在 graph_stats.json 计数登记",
    "实测 现场重算空值 %d/%d（%.1f%%）；graph_stats.json 登记 %s（字段 "
    "event_core_attributes.event_time_null_count）"
    % (len(null_time), len(ev_nodes), 100 * rate, registered_null))
if t16 is not None:
    ln16, line16 = find_line(t16, "event_time", "空值")
    chk(ln16 is not None, "E6 《16》报告 event_time 空值率",
        "实测 《16》第 %s 行：%s" % (ln16, norm_ws(line16)[:110] if line16 else "未找到含"
                                 "'event_time' 与 '空值' 的行"))
else:
    chk(False, "E6 《16》报告 event_time 空值率（《16》缺失，无法核验）",
        "实测 《16》缺失：%s；现场重算空值率 %.1f%%（%d/%d）"
        % (rel_to_root(P16), 100 * rate, len(null_time), len(ev_nodes)))

LEGAL_ROLES = list(P10_ONT["roles"]) or list(config.ROLES)
chk(LEGAL_ROLES == list(config.ROLES),
    "E7 《10》第4.5.2节 解析的 5 个合法 role == config.ROLES",
    "实测 《10》第 %s 行：%s；config：%s"
    % (p10_line("role 的取值范围"), "、".join(LEGAL_ROLES), "、".join(config.ROLES)))
bad_role, role_outside = [], []
for ln, r in edge_at:
    rv = cell(r, "role")
    if not rv:
        continue
    if rv not in LEGAL_ROLES:
        bad_role.append("第%d行 role=%r" % (ln, rv))
    if cell(r, "relation") != "PARTICIPATES_IN":
        role_outside.append("第%d行 %s 带 role=%s" % (ln, cell(r, "relation"), rv))
chk(not bad_role and not role_outside,
    "E8 role 取值落在五个合法值内，且只出现在 PARTICIPATES_IN 上",
    "实测 非法取值 %d 处%s；出现在其它关系上 %d 处%s；本批用到的 role：%s"
    % (len(bad_role), "：" + br(bad_role) if bad_role else "",
       len(role_outside), "：" + br(role_outside) if role_outside else "",
       "、".join(sorted({cell(r, "role") for _, r in edge_at if cell(r, "role")})) or "无"))

issued_viol = []
issued_types = []
for ln, r in edge_at:
    if cell(r, "relation") != "ISSUED_BY":
        continue
    et = event_type_by_id.get(cell(r, "head_id"))
    issued_types.append(et)
    if et not in config.ISSUED_BY_EVENT_TYPES:
        issued_viol.append("第%d行 起点 %s 的 event_type=%s" % (ln, cell(r, "head_id"), et))
chk(not issued_viol,
    "E9 ISSUED_BY 只出现在政策事件与监管事件上",
    "实测 ISSUED_BY %d 条，起点事件类型 %s；config.ISSUED_BY_EVENT_TYPES=%s；违例 %d 条%s"
    % (len(issued_types), dict(Counter(issued_types)) or "无",
       "、".join(config.ISSUED_BY_EVENT_TYPES), len(issued_viol),
       "：" + br(issued_viol) if issued_viol else ""))


# ==========================================================================
print(); print("=" * 78)
print("F、《15》第八节 第 7 行：BELONGS_TO 带 valid_from／valid_to；data_cutoff_time 不出现在"
      "任何节点或关系上")
print("=" * 78)

chk("valid_from" in edges_header and "valid_to" in edges_header,
    "F1 edges.csv 带 valid_from／valid_to 两列（表 4-9 的额外属性）",
    "实测 表头：%s；两列%s"
    % ("、".join(edges_header) or "读不到",
       "齐备" if {"valid_from", "valid_to"} <= set(edges_header) else "缺 " +
       "、".join(sorted({"valid_from", "valid_to"} - set(edges_header)))))
bt_rows = [(ln, r) for ln, r in edge_at if cell(r, "relation") == "BELONGS_TO"]
bad_date, bad_order, filled = [], [], []
for ln, r in bt_rows:
    vf, vt = cell(r, "valid_from"), cell(r, "valid_to")
    if vf or vt:
        filled.append("第%d行 %s~%s" % (ln, vf or "(空)", vt or "(空)"))
    if (vf and parse_date(vf) is None) or (vt and parse_date(vt) is None):
        bad_date.append("第%d行 valid_from=%r valid_to=%r" % (ln, vf, vt))
    elif vf and vt and parse_date(vf) > parse_date(vt):
        bad_order.append("第%d行 %s > %s" % (ln, vf, vt))
chk(bool(bt_rows) and not bad_date and not bad_order,
    "F2 BELONGS_TO 的 valid_from／valid_to 可解析、区间有序（空值＝正文未给日期，逐条登记）",
    "实测 BELONGS_TO %d 条；带值 %d 条；日期不可解析 %d 处%s；起点晚于终点 %d 处%s（格式取自"
    " config.TIME[\"format\"]=%s）"
    % (len(bt_rows), len(filled), len(bad_date),
       "：" + br(bad_date) if bad_date else "", len(bad_order),
       "：" + br(bad_order) if bad_order else "", config.TIME["format"]))
note("F3 证据（有效期填值率）",
     "实测 带值 %d/%d 条%s；T6 的 graph_check.json 把「全部无有效期」登记为已知缺口，"
     "《16》须登记该缺口与影响（本条只判列与取值，不判填值率）"
     % (len(filled), len(bt_rows), "：" + br(filled) if filled else ""))

cutoff_hits = scan_terms(["data_cutoff_time"],
                         [("nodes.csv", read_text(PATHS["nodes"], "")),
                          ("edges.csv", read_text(PATHS["edges"], "")),
                          ("replay.cypher", read_text(PATHS["replay_cypher"], ""))])
chk(not cutoff_hits,
    "F4 data_cutoff_time 不出现在任何节点或关系上（图谱上只有 event_time／publish_time／"
    "valid_from／valid_to）",
    "实测 三个导出文件逐行扫描（排除否定语境）：命中 %d 处%s"
    % (len(cutoff_hits), "：" + br(["%s 第%d行" % (a, b) for a, b, _c, _d, _e in cutoff_hits])
       if cutoff_hits else "（graph_stats.json 是统计文件，单独看：%s）"
       % ("命中，见 J 组比对" if "data_cutoff_time" in read_text(PATHS["graph_stats"], "") else "无命中")))


# ==========================================================================
print(); print("=" * 78)
print("G、《15》第八节 第 8 行：编号显式且唯一（event_id／policy_id／institution_id／person_id "
      "无重复、无空值、不是数据库自增）")
print("=" * 78)

node_ids = [cell(r, "node_id") for _, r in nodes_rows]
chk(not dup_groups(node_ids) and all(node_ids),
    "G1 node_id 无重复、无空值",
    "实测 节点 %d 个、distinct %d；重复 %s；空值 %d 个"
    % (len(node_ids), len(set(node_ids)), br(sorted(dup_groups(node_ids))) or "无",
       sum(1 for x in node_ids if not x)))

ID_FIELDS = [("Event", "event_id"), ("Policy", "policy_id"),
             ("Institution", "institution_id"), ("Person", "person_id")]
id_detail, id_problems = [], []
for label, field in ID_FIELDS:
    vals = [(ln, cell(r, field)) for ln, r in nodes_rows if (r.get("label") or "") == label]
    nonempty = [v for _ln, v in vals if v]
    dups = sorted(dup_groups(nonempty))
    empty = len(vals) - len(nonempty)
    id_detail.append("%s %d 条：distinct %d、重复 %s、空值 %d"
                     % (field, len(vals), len(set(nonempty)), br(dups) or "无", empty))
    if dups or empty or not vals:
        id_problems.append("%s（重复 %s、空值 %d、节点数 %d）"
                           % (field, br(dups) or "无", empty, len(vals)))
chk(not id_problems,
    "G2 event_id／policy_id／institution_id／person_id 无重复、无空值（逐类检查）",
    "实测 " + "；".join(id_detail))
note("G3 证据（逐类读数）", "；".join(id_detail))

mismatch, prefix_bad = [], []
for label, field in ID_FIELDS:
    pref = config.GRAPH["id_prefixes"].get(label)
    pat = re.compile(r"^%s-\d{%d}$" % (re.escape(pref or ""), int(config.GRAPH["id_width"])))
    for ln, r in nodes_rows:
        if (r.get("label") or "") != label:
            continue
        if cell(r, field) != cell(r, "node_id"):
            mismatch.append("第%d行 %s=%s ≠ node_id=%s"
                            % (ln, field, cell(r, field), cell(r, "node_id")))
        if not pat.match(cell(r, field)):
            prefix_bad.append("第%d行 %s=%r（应形如 %s-<4 位>）"
                              % (ln, field, cell(r, field), pref))
chk(not mismatch and not prefix_bad,
    "G4 四类编号 == node_id，且形如 config.GRAPH[\"id_prefixes\"] ＋ id_width 的显式规则",
    "实测 与 node_id 不一致 %d 处；不合前缀规则 %d 处；公司＝stock_code、文档＝doc_id"
    "（config.GRAPH[\"id_rule\"]）"
    % (len(mismatch), len(prefix_bad))
    + ("：" + br(mismatch + prefix_bad) if (mismatch or prefix_bad) else ""))

auto_hits = scan_terms(["AUTO_INCREMENT", "AUTOINCREMENT"],
                       [("nodes.csv", read_text(PATHS["nodes"], "")),
                        ("edges.csv", read_text(PATHS["edges"], "")),
                        ("replay.cypher", read_text(PATHS["replay_cypher"], ""))])
chk(not auto_hits,
    "G5 导出物不含数据库自增字样（编号由本阶段一次性显式分配；重放可复现见 J 组）",
    "实测 AUTO_INCREMENT／AUTOINCREMENT 命中 %d 处%s"
    % (len(auto_hits), "：" + br(["%s 第%d行" % (a, b) for a, b, _c, _d, _e in auto_hits])
       if auto_hits else ""))


# --------------------------------------------------------------------------
# 镜像重跑（H／I／J／K／S 组共用的唯一一次进程链）
# --------------------------------------------------------------------------
REPLAY = None
REPLAY_KEYS = ("nodes", "edges", "replay_cypher", "graph_stats", "alias_table",
               "disambiguation", "unresolved", "merge_log", "events_merged",
               "merge_summary", "dedup_self_test")


def extract_table(profile):
    return getattr(config, config.GRAPH_PIPELINE["extract_records_profiles"][profile])


def mirror_items():
    """返回 [(源文件, 临时根下的相对路径)]：只镜像重跑必需的输入与产物。"""
    items = []
    for name in sorted(os.listdir(CODE_GRAPH)):
        if name.endswith(".py"):
            items.append((os.path.join(CODE_GRAPH, name), os.path.join("代码", "抽取与图谱", name)))
    items.append((os.path.join(CODE_PREP, "config.py"), os.path.join("代码", "数据准备", "config.py")))
    for p in (config.DOCS_PATH, config.CHUNKS_PATH):
        items.append((p, os.path.relpath(p, config.ROOT)))
    for p in iter_files(config.CACHE_DIR):
        items.append((p, os.path.relpath(p, config.ROOT)))
    rec = PATHS["extract_records"]
    items.append((rec, os.path.relpath(rec, config.ROOT)))
    for p in iter_files(os.path.dirname(rec)):
        items.append((p, os.path.relpath(p, config.ROOT)))
    for p in iter_files(PATHS["work_root"]):
        items.append((p, os.path.relpath(p, config.ROOT)))
    return items


def build_mirror():
    tmp = tempfile.mkdtemp(prefix="stage6_accept_")
    copied, skipped = 0, 0
    for src, rel in mirror_items():
        if not os.path.isfile(src):
            continue
        dst = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isfile(dst):
            skipped += 1
            continue
        shutil.copy2(src, dst)
        copied += 1
    return tmp, copied, skipped


def run_cmd(cmd, cwd, timeout=1800):
    """在镜像里跑一条命令；子进程环境里**摘掉 LLM_API_KEY**——重放不得调用模型（密钥不打印）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop(config.LLM["api_key_env"], None)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=env)
    return {"cmd": cmd, "code": proc.returncode, "seconds": round(time.time() - t0, 3),
            "stdout": proc.stdout or "", "stderr": proc.stderr or "",
            "key_removed": config.LLM["api_key_env"]}


def drop_exports(export_dir):
    for name in config.GRAPH_PIPELINE["files"].values():
        fp = os.path.join(export_dir, name)
        if os.path.isfile(fp):
            os.remove(fp)


def json_equal_without_fields(path_a, path_b, drop):
    a, b = read_json(path_a, default=None), read_json(path_b, default=None)
    if a is None or b is None:
        return False, ["读不到文件"]
    a = {k: v for k, v in a.items() if k not in drop}
    b = {k: v for k, v in b.items() if k not in drop}
    diff = sorted(set(a) | set(b))
    diff = [k for k in diff if a.get(k) != b.get(k)]
    return not diff, diff


def ensure_replay():
    """把镜像建好、跑完进程链并算好比对结果；只跑一次（全局缓存）。"""
    global REPLAY
    if REPLAY is not None:
        return REPLAY
    REPLAY = {"error": None, "key_removed": config.LLM["api_key_env"]}
    if ARGS.no_replay:
        REPLAY["error"] = "--no-replay：命令行显式跳过镜像重跑"
        return REPLAY
    try:
        tmp, copied, skipped = build_mirror()
        REPLAY.update({"tmp": tmp, "copied": copied, "skipped": skipped})
        py = sys.executable
        code_run = os.path.join(tmp, "代码", "抽取与图谱")
        run_all = os.path.join(code_run, "run_all.py")
        export_mirror = os.path.join(tmp, os.path.relpath(PATHS["export_dir"], config.ROOT))
        REPLAY["orig_hash"] = {k: sha256_file(PATHS[k]) for k in REPLAY_KEYS}
        mirror_paths = {k: os.path.join(tmp, os.path.relpath(PATHS[k], config.ROOT))
                        for k in REPLAY_KEYS}
        REPLAY["mirror"] = mirror_paths
        # ① 先删掉镜像里的导出物：按第八节 第 11 行「删掉导出物、只读缓存重跑」
        drop_exports(export_mirror)
        REPLAY["run_all"] = run_cmd([py, run_all, "--profile", PROFILE, "--force"], cwd=tmp)
        REPLAY["hash_after_run_all"] = {k: sha256_file(mirror_paths[k]) for k in REPLAY_KEYS}
        # ② 四个环节脚本各自单独执行（第八节 第 25 行的「可单独执行」）
        REPLAY["stage_runs"] = {}
        for stage in config.RUN_ALL["stages"]:
            # extract.py 的 --force 是「忽略缓存、重新调用模型」（会真的花钱），单独执行时不下传；
            # 其余三个阶段 --force 重算即可（《15》第4.2节 的幂等与续跑口径）。
            args_stage = ["--profile", PROFILE]
            if stage["name"] != "extract":
                args_stage.append("--force")
            REPLAY["stage_runs"][stage["name"]] = run_cmd(
                [py, os.path.join(code_run, stage["script"])] + args_stage, cwd=tmp)
        # ③ 再整链跑一遍（幂等：重复执行不产生重复 event_id）
        REPLAY["run_all_2"] = run_cmd([py, run_all, "--profile", PROFILE, "--force"], cwd=tmp)
        REPLAY["hash_after_run_all_2"] = {k: sha256_file(mirror_paths[k]) for k in REPLAY_KEYS}
        # ④ 断点续跑：从 T5 起往后跑
        REPLAY["from_run"] = run_cmd([py, run_all, "--profile", PROFILE, "--from", "dedup_events"],
                                     cwd=tmp)
        # ⑤ 再删一次导出物，只跑 write_graph（第八节 第 11 行的逐字节复现）
        drop_exports(export_mirror)
        REPLAY["write_graph_again"] = run_cmd(
            [py, os.path.join(code_run, "write_graph.py"), "--profile", PROFILE, "--force"],
            cwd=tmp)
        REPLAY["mirror_hash"] = {k: sha256_file(v) for k, v in REPLAY["mirror"].items()}
        REPLAY["byte_equal"] = {k: (REPLAY["orig_hash"][k] is not None
                                    and REPLAY["orig_hash"][k] == REPLAY["mirror_hash"][k])
                                for k in REPLAY_KEYS}
        drop = list(config.GRAPH_PIPELINE["excluded_from_byte_compare"])
        ok_stats, diff_keys = json_equal_without_fields(
            PATHS["graph_stats"], REPLAY["mirror"]["graph_stats"], drop)
        REPLAY["stats_equal"], REPLAY["stats_diff"] = ok_stats, diff_keys
        REPLAY["stats_drop"] = drop
        # ⑥ 重跑后的读数（直接读镜像里的机器可读产物）
        table = extract_table(PROFILE)
        hist_path = os.path.join(tmp, os.path.relpath(table["run_history"], config.ROOT))
        hist = read_jsonl(hist_path) if os.path.isfile(hist_path) else []
        REPLAY["history_last"] = hist[-1][1] if hist else {}
        REPLAY["run_history_path"] = hist_path
        msum_path = os.path.join(tmp, os.path.relpath(PATHS["merge_summary"], config.ROOT))
        REPLAY["merge_summary_new"] = read_json(msum_path, default={}) or {}
        dis_path = os.path.join(tmp, os.path.relpath(PATHS["disambiguation"], config.ROOT))
        REPLAY["disambiguation_new"] = read_json(dis_path, default={}) or {}
        st_path = REPLAY["mirror"]["dedup_self_test"]
        REPLAY["dedup_self_test_new"] = read_json(st_path, default={}) or {}
        merged_path = REPLAY["mirror"]["events_merged"]
        REPLAY["events_merged_new"] = [r for _, r in read_jsonl(merged_path)] \
            if os.path.isfile(merged_path) else []
    except Exception as exc:                  # 镜像／重跑本身的异常也要有证据，不能静默
        REPLAY["error"] = "%s: %s" % (type(exc).__name__, exc)
    return REPLAY


def replay_or_skip(prefix, labels):
    """给 H／I／J／K／S 组用：重跑不可用时逐个记 SKIP（原因写明），返回 (R, usable)。"""
    R = ensure_replay()
    if R.get("error"):
        for lab in labels:
            skip("%s %s" % (prefix, lab), "镜像重跑未执行：%s" % R["error"])
        return R, False
    return R, True


def mirror_note(R, tail=3):
    """把重跑命令的尾部输出压成一行证据。"""
    if R.get("error"):
        return R["error"]
    parts = []
    for name in ("run_all", "write_graph_again", "from_run"):
        if name in R:
            parts.append("%s 退出码=%s/%.2fs" % (name, R[name]["code"], R[name]["seconds"]))
    return "；".join(parts)


# ==========================================================================
print(); print("=" * 78)
print("H、《15》第八节 第 9 行：实体消歧可复算（同一份缓存重跑 disambiguate.py，"
      "消歧映射与待消歧清单逐字节一致）")
print("=" * 78)

R, ok_replay = replay_or_skip("H", ["H1 消歧重跑退出码为 0",
                                    "H2 消歧产物逐字节一致",
                                    "H3 消歧读数一致"])
if ok_replay:
    srun = R["stage_runs"]["disambiguate"]
    chk(srun["code"] == 0, "H1 disambiguate.py 单独重跑退出码为 0",
        "实测 命令：python %s --profile %s --force；退出码=%s、耗时 %.2fs%s%s"
        % (os.path.join("代码", "抽取与图谱", "disambiguate.py"), PROFILE, srun["code"],
           srun["seconds"],
           "；stderr 尾部：" + norm_ws(srun["stderr"])[-160:] if srun["stderr"] else "",
           "；stdout 尾部：" + norm_ws(srun["stdout"])[-200:] if srun["code"] else ""))
    pairs = [("disambiguation.json", "disambiguation"), ("unresolved.jsonl", "unresolved"),
             ("alias_table.json", "alias_table")]
    bad = ["%s（原 %s vs 重跑 %s）"
           % (name, (R["orig_hash"][key] or "缺")[:12], (R["mirror_hash"][key] or "缺")[:12])
           for name, key in pairs if not R["byte_equal"][key]]
    chk(not bad, "H2 消歧映射与待消歧清单逐字节一致（sha256 比对）",
        "实测 逐字节一致 %d/%d；不一致 %s；原文：%s"
        % (len(pairs) - len(bad), len(pairs), "；".join(bad) or "无",
           "；".join("%s=%s" % (n, (R["mirror_hash"][k] or "缺")[:16]) for n, k in pairs)))
    old_c = (disambig.get("counts") or {})
    new_c = (R["disambiguation_new"].get("counts") or {})
    same = all(old_c.get(k) == new_c.get(k)
               for k in ("entities", "resolved", "unresolved", "company_identities"))
    chk(bool(old_c) and same, "H3 重跑后的消歧读数与原产物一致（实体／已消歧／待消歧／公司身份）",
        "实测 原 %s；重跑 %s" % ({k: old_c.get(k) for k in
                                 ("entities", "resolved", "unresolved", "company_identities")},
                                {k: new_c.get(k) for k in
                                 ("entities", "resolved", "unresolved", "company_identities")}))
    note("H4 重跑证据（镜像内的命令与耗时）",
         "镜像：%s（复制 %d 个文件）；%s" % (R["tmp"], R["copied"], mirror_note(R)))


# ==========================================================================
print(); print("=" * 78)
print("I、《15》第八节 第 10 行：事件去重可复算（重跑 dedup_events.py，合并日志逐字节一致；"
      "被合并事件保留全部证据文档）")
print("=" * 78)

R, ok_replay = replay_or_skip("I", ["I1 去重重跑退出码为 0", "I2 合并日志逐字节一致",
                                    "I3 其余去重产物逐字节一致",
                                    "I4 被合并事件保留全部证据文档"])
if ok_replay:
    srun = R["stage_runs"]["dedup_events"]
    chk(srun["code"] == 0, "I1 dedup_events.py 单独重跑退出码为 0",
        "实测 退出码=%s、耗时 %.2fs；判据条数（merge_log 行数）= %d%s"
        % (srun["code"], srun["seconds"],
           len(read_jsonl(PATHS["merge_log"])) if os.path.isfile(PATHS["merge_log"]) else 0,
           "；stdout 尾部：" + norm_ws(srun["stdout"])[-200:] if srun["code"] else ""))
    chk(R["byte_equal"]["merge_log"], "I2 合并日志 merge_log.jsonl 逐字节一致",
        "实测 原 %s vs 重跑 %s（字节数 %s）"
        % ((R["orig_hash"]["merge_log"] or "缺")[:16], (R["mirror_hash"]["merge_log"] or "缺")[:16],
           os.path.getsize(PATHS["merge_log"]) if os.path.isfile(PATHS["merge_log"]) else "缺"))
    pairs = [("events_merged.jsonl", "events_merged"), ("merge_summary.json", "merge_summary"),
             ("dedup_self_test.json", "dedup_self_test")]
    bad = [n for n, k in pairs if not R["byte_equal"][k]]
    chk(not bad, "I3 合并后事件集合、汇总与自检文件逐字节一致",
        "实测 一致 %d/%d；不一致 %s；sha256：%s"
        % (len(pairs) - len(bad), len(pairs), "、".join(bad) or "无",
           "；".join("%s=%s" % (n, (R["mirror_hash"][k] or "缺")[:12]) for n, k in pairs)))
    self_test = R["dedup_self_test_new"] or dedup_self_test
    group = (self_test or {}).get("group") or {}
    members_ok = bool(self_test.get("passed")) and group.get("all_members_retained") is True
    merged_events = [r for r in (R["events_merged_new"] or []) if r.get("is_merged")]
    union_ok, union_bad = True, []
    for ev in merged_events:
        need = set()
        for m in (ev.get("members") or []):
            need.update(m.get("evidence_doc_ids") or [])
        if not need <= set(ev.get("evidence_doc_ids") or []):
            union_ok = False
            union_bad.append(ev.get("merged_event_key"))
    chk(members_ok and union_ok,
        "I4 被合并事件保留全部证据文档（自检 ＋ 逐组证据并集校验）",
        "实测 自检 passed=%s、all_members_retained=%s、期望并集 %s→实得 %s；本批合并组 %d 个"
        "（证据并集校验 %s%s）"
        % (self_test.get("passed"), group.get("all_members_retained"),
           group.get("expected_union"), group.get("merged_evidence_doc_ids"),
           len(merged_events), "通过" if union_ok else "不通过",
           "，异常组 " + br(union_bad) if union_bad else ""))


# ==========================================================================
print(); print("=" * 78)
print("J、《15》第八节 第 11 行：图谱导出物与缓存重放一致（删掉导出物、只读缓存重跑 "
      "write_graph.py，两次导出物逐字节一致；generated_at 与缓存指纹字段除外）")
print("=" * 78)

R, ok_replay = replay_or_skip("J", ["J1 图谱写入重跑退出码为 0", "J2 nodes.csv 逐字节一致",
                                    "J3 edges.csv 逐字节一致", "J4 replay.cypher 逐字节一致",
                                    "J5 graph_stats.json 排除字段后一致"])
if ok_replay:
    wrun = R["stage_runs"]["write_graph"]
    again = R["write_graph_again"]
    chk(wrun["code"] == 0 and again["code"] == 0,
        "J1 删掉导出物后 write_graph.py 重跑退出码为 0（两次：单独执行 ＋ 再删再跑）",
        "实测 单独执行退出码=%s、再删再跑退出码=%s；整链 run_all 退出码=%s"
        % (wrun["code"], again["code"], R["run_all"]["code"]))
    for cid, name, key in (("J2", "nodes.csv", "nodes"), ("J3", "edges.csv", "edges"),
                           ("J4", "replay.cypher", "replay_cypher")):
        chk(R["byte_equal"][key], "%s %s 逐字节一致（sha256 比对）" % (cid, name),
            "实测 原 %s vs 重跑 %s；字节数 %s"
            % ((R["orig_hash"][key] or "缺")[:16], (R["mirror_hash"][key] or "缺")[:16],
               os.path.getsize(PATHS[key]) if os.path.isfile(PATHS[key]) else "缺"))
    chk(R["stats_equal"],
        "J5 graph_stats.json 排除 %s 后一致"
        % "／".join(config.GRAPH_PIPELINE["excluded_from_byte_compare"]),
        "实测 排除字段 %s；差异字段 %s；两文件 sha256 原 %s vs 重跑 %s（含 generated_at 时本就不等）"
        % ("、".join(R["stats_drop"]), br(R["stats_diff"]) or "无",
           (R["orig_hash"]["graph_stats"] or "缺")[:12],
           (R["mirror_hash"]["graph_stats"] or "缺")[:12]))
    note("J6 逐字节比对读数（证据）",
         "四件套 sha256（原→重跑）：nodes %s→%s；edges %s→%s；replay %s→%s；stats %s→%s"
         % tuple(x for key in ("nodes", "edges", "replay_cypher", "graph_stats")
                 for x in ((R["orig_hash"][key] or "缺")[:12], (R["mirror_hash"][key] or "缺")[:12])))
    if graph_check:
        sm = graph_check.get("summary") or {}
        note("J7 被验收对象的内建自检快照（读 graph_check.json，仅作参考）",
             "T6 机检 %s 项：通过 %s、不通过 %s（其中 known_gap %s）"
             % (sm.get("checks"), sm.get("passed"), "、".join(sm.get("failed") or []) or "无",
                "、".join(sm.get("known_gaps") or []) or "无"))


# ==========================================================================
print(); print("=" * 78)
print("K、《15》第八节 第 12 行：重放不调用模型（重跑过程中的模型调用次数为 0）")
print("=" * 78)

R, ok_replay = replay_or_skip("K", ["K1 重跑模型调用次数为 0", "K2 缓存命中覆盖全部文档",
                                    "K3 重跑子进程摘掉密钥（不可能调用模型）",
                                    "K4 T4～T6 源码内无模型客户端"])
if ok_replay:
    last = R.get("history_last") or {}
    api_calls = last.get("api_calls_total", last.get("api_calls"))
    limit = int(config.RUN_ALL["max_api_calls_on_replay"])
    chk(api_calls == 0 and api_calls is not None,
        "K1 重跑过程中模型调用次数为 0（上限 config.RUN_ALL[\"max_api_calls_on_replay\"]=%d）" % limit,
        "实测 镜像内 run_history.jsonl 末条：api_calls_total=%s ≤ 上限 %d；"
        "文件 %s（第 %d 条记录）"
        % (api_calls, limit, rel_to_root(R["run_history_path"]),
           len(read_jsonl(R["run_history_path"])) if os.path.isfile(R["run_history_path"]) else 0))
    docs_n = last.get("documents") or last.get("doc_count")
    chk(last.get("cache_hits") == docs_n and last.get("fetched") == 0,
        "K2 缓存命中覆盖全部文档（cache_hits == 文档数、fetched == 0）",
        "实测 cache_hits=%s、documents=%s、fetched=%s、retries=%s"
        % (last.get("cache_hits"), docs_n, last.get("fetched"), last.get("retries")))
    chk(True, "K3 重跑子进程显式摘掉 %s（缓存未命中即硬失败，不可能静默调用模型）"
        % config.LLM["api_key_env"],
        "实测 本脚本用 env.pop(\"%s\") 构造子进程环境，只打印变量名、不读取值；"
        "重跑退出码：run_all=%s、run_all_2=%s、from=%s、write_graph=%s"
        % (config.LLM["api_key_env"], R["run_all"]["code"], R["run_all_2"]["code"],
           R["from_run"]["code"], R["write_graph_again"]["code"]))
    net_imports = []
    net_pat = re.compile(r"^\s*(?:import|from)\s+(openai|requests|urllib|httpx|aiohttp|http\.client)\b",
                         re.M)
    for stage in config.RUN_ALL["stages"]:
        if stage["name"] == "extract":
            continue                     # extract.py 是唯一允许调用模型的环节
        src = read_text(os.path.join(CODE_GRAPH, stage["script"]), default="")
        for m in net_pat.finditer(src):
            net_imports.append("%s 第 %d 行 %s" % (stage["script"],
                                                  src[:m.start()].count("\n") + 1, m.group(1)))
    chk(not net_imports,
        "K4 disambiguate／dedup_events／write_graph 源码内无模型或 HTTP 客户端 import",
        "实测 三个脚本命中 %d 处%s；extract.py 单独豁免（它是唯一会调模型的环节，"
        "缓存齐全时 api_calls_total=0）"
        % (len(net_imports), "：" + br(net_imports) if net_imports else ""))


# ==========================================================================
print(); print("=" * 78)
print("L、《15》第八节 第 13 行：缓存目录位于数据集版本的同级位置且不在公开仓库"
      "（.gitignore 覆盖，导出物不含正文）")
print("=" * 78)

# 「与数据集版本目录同级」＝ `_抽取缓存\` 与 `v2.1\` 同级（都挂在数据集根之下）、且缓存目录按版本分子目录：
#   数据集\v2.1\         ← 版本目录
#   数据集\_抽取缓存\v2.1\ ← 缓存目录（每版一个子目录，下划线前缀表示不是数据集内容）
cache_root_parent = os.path.dirname(os.path.abspath(config.CACHE_ROOT).rstrip("\\/"))
version_dir_parent = os.path.dirname(os.path.abspath(config.DATASET_DIR).rstrip("\\/"))
cache_dir_ok = (os.path.normcase(cache_root_parent) == os.path.normcase(version_dir_parent)
                and os.path.basename(os.path.abspath(config.CACHE_DIR)) == config.DATASET_VERSION)
chk(cache_dir_ok and os.path.isdir(config.CACHE_DIR),
    "L1 缓存根目录与数据集版本目录同级、且按版本分子目录（<数据集根>\\_抽取缓存\\<版本>\\）且存在",
    "实测 config.CACHE_ROOT=%s（父=%s）、config.DATASET_DIR=%s（父=%s）；同级=%s；"
    "缓存子目录名=%s（期望 %s）；目录存在=%s"
    % (rel_to_root(config.CACHE_ROOT), os.path.basename(cache_root_parent),
       rel_to_root(config.DATASET_DIR), os.path.basename(version_dir_parent),
       os.path.normcase(cache_root_parent) == os.path.normcase(version_dir_parent),
       os.path.basename(os.path.abspath(config.CACHE_DIR)), config.DATASET_VERSION,
       os.path.isdir(config.CACHE_DIR)))

rules = gitignore_rules(GITIGNORE)
cache_rel = rel_to_root(config.CACHE_DIR) + "/probe.json"
eval_rel = rel_to_root(EVAL_DIR) + "/dev.jsonl"
cache_hits = [(ln, pat) for ln, pat in rules if gitignore_match(pat, cache_rel)]
eval_hits = [(ln, pat) for ln, pat in rules if gitignore_match(pat, eval_rel)]
chk(cache_hits and eval_hits,
    "L2 .gitignore 覆盖抽取缓存与评测集目录（两处都不入公开仓库）",
    "实测 .gitignore 规则 %d 条；缓存命中规则 %s；评测集命中规则 %s（行号＋模式）"
    % (len(rules), br(["第%d行 %s" % (a, b) for a, b in cache_hits], 2) or "无",
       br(["第%d行 %s" % (a, b) for a, b in eval_hits], 2) or "无"))

export_inside_dataset = os.path.abspath(PATHS["export_dir"]).startswith(
    os.path.abspath(config.DATASET_ROOT) + os.sep)
chk(not export_inside_dataset,
    "L3 图谱导出物放在数据集版本目录之外（硬约束 11；导出物可随仓库提交）",
    "实测 导出目录 %s；数据集根 %s；是否在数据集内=%s"
    % (rel_to_root(PATHS["export_dir"]), rel_to_root(config.DATASET_ROOT), export_inside_dataset))
export_rel = rel_to_root(PATHS["export_dir"]) + "/nodes.csv"
export_ignored = [(ln, pat) for ln, pat in rules if gitignore_match(pat, export_rel)]
note("L4 证据（导出物是否被 .gitignore 排除）",
     "实测 %s → %s" % (rel_to_root(PATHS["export_dir"]),
                       "被排除（需人工确认：真导出物应随仓库提交）" if export_ignored
                       else "未被排除（与《15》第4.3节 一致）"))


# ==========================================================================
print(); print("=" * 78)
print("M、《15》第八节 第 14 行：导出物不复制正文（抽样比对导出物字段与 v2.1 正文片段，"
      "无长文本命中）")
print("=" * 78)

forbidden_fields = [f for f in config.GRAPH["forbidden_export_fields"]
                    if f in nodes_header + edges_header]
chk(not forbidden_fields,
    "M1 导出物表头不含被禁字段（%s）" % "／".join(config.GRAPH["forbidden_export_fields"]),
    "实测 nodes.csv 表头 %d 列、edges.csv 表头 %d 列；被禁字段命中 %s"
    % (len(nodes_header), len(edges_header), br(forbidden_fields) or "无"))

probe = config.GRAPH["body_text_check"]
export_text_all = "\n".join(read_text(p, default="") for p in
                            (PATHS["nodes"], PATHS["edges"], PATHS["graph_stats"],
                             PATHS["replay_cypher"]))
n_chars = int(probe["probe_substring_chars"])
rng = random.Random(int(probe["seed"]))
candidates = [str(c.get("content") or "") for _, c in chunk_rows]
candidates = [c for c in candidates if len(c) >= n_chars]
sample = rng.sample(candidates, min(int(probe["probe_chunks"]), len(candidates)))
probes, hits, hits_norm = 0, [], []
for text in sample:
    for _ in range(3):
        start = rng.randrange(0, len(text) - n_chars + 1)
        piece = text[start:start + n_chars]
        probes += 1
        if piece in export_text_all:
            hits.append(piece[:40])
        elif strip_ws(piece) and strip_ws(piece) in strip_ws(export_text_all):
            hits_norm.append(piece[:40])
chk(probes > 0 and not hits,
    "M2 抽样 %d 块 × 3 段 × %d 字符的正文子串，导出物文件内 0 命中" % (len(sample), n_chars),
    "实测 探针 %d 条（分块抽样 %d 块／可选 %d 块，seed=%s，参数取 "
    "config.GRAPH[\"body_text_check\"]）；命中 %d 条%s；去空白后命中 %d 条%s"
    % (probes, len(sample), len(candidates), probe["seed"], len(hits),
       "：" + br(hits) if hits else "", len(hits_norm),
       "：" + br(hits_norm) if hits_norm else ""))

# ==========================================================================
print(); print("=" * 78)
print("N、《15》第八节 第 15～18 行：抽取评测集（Dev 60 ＋ Test 200 ＝ 260、两段式、chunk_id 不重叠、"
      "文档重叠登记、分层与表 15-E 一致、8 类事件类型与 9 条关系要么有条目要么登记为证据不足、"
      "不得出现「按 8 类均衡」的分层声明）")
print("=" * 78)

eval_files = [("dev.jsonl", EVAL_DEV), ("test.jsonl", EVAL_TEST),
              ("标注说明.md", EVAL_NOTE), ("分层统计.json", EVAL_STATS)]
miss_eval = [n for n, p in eval_files if not os.path.isfile(p)]
chk(not miss_eval, "N1 评测集四件齐全（与数据集版本目录同级，落 %s）" % rel_to_root(EVAL_DIR),
    "实测 %d/%d 存在；缺失 %s"
    % (len(eval_files) - len(miss_eval), len(eval_files), "、".join(miss_eval) or "无"))
dev_rows = read_jsonl(EVAL_DEV) if os.path.isfile(EVAL_DEV) else []
test_rows = read_jsonl(EVAL_TEST) if os.path.isfile(EVAL_TEST) else []
eval_stats = read_json(EVAL_STATS, default=None) or {}
eval_note = read_text(EVAL_NOTE, default="") or ""
n_dev, n_test = len(dev_rows), len(test_rows)
bad_split = [ln for ln, r in dev_rows if r.get("split") != "dev"] + \
            [ln for ln, r in test_rows if r.get("split") != "test"]
chk(n_dev == 60 and n_test == 200 and n_dev + n_test == 260 and not bad_split,
    "N2 Dev 60 ＋ Test 200 ＝ 260 条，两段式（split 字段与文件归属一致）",
    "实测 dev.jsonl %d 条、test.jsonl %d 条、合计 %d；split 字段不符 %d 条；"
    "文件行数校验 %s" % (n_dev, n_test, n_dev + n_test, len(bad_split),
                     "通过" if eval_stats.get("counts", {}).get("total") == 260 else
                     "分层统计.json 未登记 260（读报告，仅作参考）"))

need_fields = ["chunk_id", "doc_id", "annotation"]
ann_keys = ["entities", "events", "relations", "times", "notes"]
field_bad, statuses = [], Counter()
for name, rows in (("dev.jsonl", dev_rows), ("test.jsonl", test_rows)):
    for ln, r in rows:
        for f in need_fields:
            if f not in r:
                field_bad.append("%s 第%d行 缺 %s" % (name, ln, f))
        ann = r.get("annotation") or {}
        for k in ann_keys:
            if k not in ann:
                field_bad.append("%s 第%d行 annotation 缺 %s" % (name, ln, k))
        statuses[ann.get("status")] += 1
chk(not field_bad,
    "N3 每条都带 chunk_id／doc_id 与 annotations 骨架（entities／events／relations／times／notes）",
    "实测 检查 %d 条；缺字段 %d 处%s；标注状态分布 %s"
    % (n_dev + n_test, len(field_bad), "：" + br(field_bad) if field_bad else "",
       dict(statuses)))
if set(statuses) == {"pending_human_annotation"}:
    note("N3 证据（人工标注状态）",
         "实测 %d 条全部为 pending_human_annotation：T8 的选点与配额已落盘，人工标注尚未填写；"
         "这正是 N9 与 O4 需要《16》登记证据不足清单的原因" % sum(statuses.values()))

dev_ids = [r.get("chunk_id") for _, r in dev_rows]
test_ids = [r.get("chunk_id") for _, r in test_rows]
all_ids = dev_ids + test_ids
inter = set(dev_ids) & set(test_ids)
chk(not inter and not dup_groups(all_ids) and len(set(all_ids)) == len(all_ids),
    "N4 Dev 与 Test 的 chunk_id 不重叠；260 个文本块互不重复（一个文本块只算一个证据）",
    "实测 dev %d 个、test %d 个、交集 %d 个%s；重复 chunk_id %s"
    % (len(set(dev_ids)), len(set(test_ids)), len(inter),
       "：" + br(sorted(inter)) if inter else "",
       br(sorted(dup_groups(all_ids))) or "无"))

dev_docs = {r.get("doc_id") for _, r in dev_rows}
test_docs = {r.get("doc_id") for _, r in test_rows}
doc_overlap = sorted(dev_docs & test_docs)
if not doc_overlap:
    chk(True, "N5 文档集合重叠部分已在《标注说明.md》登记（实测交集为 0）",
        "实测 dev 文档 %d 个、test 文档 %d 个、交集 %d 个；交集为空故无需登记；"
        "分层统计.json 登记 document_overlap_size=%s"
        % (len(dev_docs), len(test_docs), len(doc_overlap),
           (eval_stats.get("keys") or {}).get("document_overlap_size")))
else:
    unreg = [str(d) for d in doc_overlap if str(d) not in eval_note]
    chk(not unreg, "N5 文档集合重叠部分已在《标注说明.md》登记（%d 篇重叠）" % len(doc_overlap),
        "实测 交集 %d 篇；未在《标注说明.md》出现的 %s"
        % (len(doc_overlap), br(unreg) or "无"))

# 表 15-E 的三维度重算：数据集侧按文本块占比，评测集侧按条目占比
doc_by_id = {str(d.get("doc_id")): d for d in docs}
cat_chunks, month_chunks, comp_chunks = Counter(), Counter(), Counter()
for _, c in chunk_rows:
    d = doc_by_id.get(str(c.get("doc_id"))) or {}
    cat_chunks[str(d.get("category"))] += 1
    month_chunks[str(d.get("publish_time"))[:7]] += 1
    for code in (d.get("subject_companies") or []):
        comp_chunks[str(code)] += 1
total_chunks = sum(cat_chunks.values())
eval_rows = [r for _, r in dev_rows] + [r for _, r in test_rows]
cat_items, month_items, comp_items = Counter(), Counter(), Counter()
for r in eval_rows:
    cat_items[str(r.get("category"))] += 1
    month_items[str(r.get("month") or str(r.get("publish_time"))[:7])] += 1
    for code in (r.get("subject_companies") or []):
        comp_items[str(code)] += 1
# 容差与「达成侧」的分母口径都照 T8 的选样器（分层统计.json 的 sampler 段）：
#   类目／月份：分母＝条目数（260）；公司：分母＝公司与条目的关联总数
#   （`subject_companies` 一处多公司就计多次，config 与 分层统计.json 的 company_rule 都是这个口径）
tol = (eval_stats.get("sampler") or {}).get("tolerance") or eval_stats.get("tolerance") or {}
n_items = max(1, len(eval_rows))
dim_report, dim_bad = [], []
dim_pairs = []
for dim, tol_key, base, got in (("category", "category_pp", cat_chunks, cat_items),
                                ("month", "month_pp", month_chunks, month_items),
                                ("company", "company_pp", comp_chunks, comp_items)):
    dim_pairs.append((dim, tol_key, base, got, sum(base.values()), sum(got.values())))
for dim, tol_key, base, got, base_total, got_total in dim_pairs:
    keys = sorted(set(base) | set(got))
    dev_list = []
    for k in keys:
        tgt = base.get(k, 0) / float(base_total) if base_total else 0.0
        ach = got.get(k, 0) / float(got_total) if got_total else 0.0
        dev_list.append((abs(ach - tgt) * 100.0, k, tgt, ach))
    dev_list.sort(reverse=True)
    worst = dev_list[0] if dev_list else (0.0, "-", 0.0, 0.0)
    limit = tol.get(tol_key)
    ok = (limit is not None) and worst[0] <= float(limit)
    dim_report.append("%s：最大偏差 %.4f pp（%s，阈值 %s pp）" % (dim, worst[0], worst[1], limit))
    if not ok:
        dim_bad.append("%s 最大偏差 %.4f pp > %s" % (dim, worst[0], limit))
chk(not dim_bad,
    "N6 标注分层与表 15-E 的文本块级实测分布一致（类目／月份／公司三维度偏差在容差内）",
    "实测 数据集侧文本块 %d 个、评测集侧条目 %d 条（容差取自分层统计.json 的 sampler.tolerance：%s）；%s"
    % (total_chunks, n_items, tol or "未登记", "；".join(dim_report)))

# 差异逐项登记：分层统计.json 的 achieved_vs_target[*].delta_pp 与现场重算逐项对齐
registered = (eval_stats.get("achieved_vs_target") or {})
reg_mismatch = []
for dim, tol_key, base, got, base_total, got_total in dim_pairs:
    reg = {str(x.get("key")): x for x in (registered.get(dim) or []) if isinstance(x, dict)}
    for k in sorted(set(base) | set(got)):
        if k not in reg:
            reg_mismatch.append("%s/%s 未登记" % (dim, k))
            continue
        tgt = base.get(k, 0) / float(base_total) if base_total else 0.0
        ach = got.get(k, 0) / float(got_total) if got_total else 0.0
        mine = round((ach - tgt) * 100.0, 4)
        theirs = reg[k].get("delta_pp")
        if theirs is None or abs(float(theirs) - mine) > 0.01:
            reg_mismatch.append("%s/%s 登记 %s vs 重算 %s" % (dim, k, theirs, mine))
chk(not reg_mismatch,
    "N7 差异逐项登记且与现场重算一致（分层统计.json 的 delta_pp 逐项核对）",
    "实测 登记键 %s；不一致 %d 项%s"
    % ("、".join("%s %d 项" % (d, len(registered.get(d) or []))
                 for d, _t, _b, _g, _bt, _gt in dim_pairs),
       len(reg_mismatch), "：" + br(reg_mismatch) if reg_mismatch else ""))

if t16 is not None:
    ln16, line16 = find_line(t16, "容差")
    # 容差取值不写死：与现场读到的 分层统计.json（sampler.tolerance）逐一对照，数值必须一致。
    tol_vals = [float(v) for k, v in (tol or {}).items()
                if k.endswith("_pp") and isinstance(v, (int, float))]
    nums16 = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", line16 or "")]
    ok16 = (ln16 is not None and bool(tol_vals)
            and all(any(abs(n - t) < 1e-6 for n in nums16) for t in set(tol_vals)))
    chk(ok16, "N8 《16》声明分层容差并逐项登记差异",
        "实测 《16》第 %s 行：%s；分层统计.json 的容差 %s（该行解析出数值 %s，须逐一出现）"
        % (ln16, norm_ws(line16)[:110] if line16 else "未找到含「容差」的行", tol or "未登记", nums16))
else:
    chk(False, "N8 《16》声明分层容差并逐项登记差异（《16》缺失，无法核验）",
        "实测 《16》缺失：%s；现场容差（分层统计.json）=%s" % (rel_to_root(P16), tol or "未登记"))

evt_ann, rel_ann, ent_ann = Counter(), Counter(), Counter()
for r in eval_rows:
    ann = r.get("annotation") or {}
    for e in (ann.get("events") or []):
        et = e.get("event_type") if isinstance(e, dict) else None
        evt_ann[str(et)] += 1
    for x in (ann.get("relations") or []):
        rn = x.get("relation") if isinstance(x, dict) else str(x)
        rel_ann[str(rn)] += 1
    for e in (ann.get("entities") or []):
        ent_ann[str(e.get("type") if isinstance(e, dict) else e)] += 1
miss_types = [x for x in config.EVENT_TYPES if not evt_ann.get(x)]
miss_rels = [x for x in config.RELATIONS if not rel_ann.get(x)]


def thin_registration(text, name):
    """在《16》里找「<name> … 证据不足／无条目」的**同一行**登记（不许只看全文共现）。"""
    if not text:
        return None, None
    for ln, line in enumerate(text.split("\n"), 1):
        if name in line and any(k in line for k in ("证据不足", "无标注条目", "无条目", "未取得",
                                                    "0 条", "零条", "条目为 0", "条目数 0")):
            return ln, line.strip()
    return None, None


unregistered = []
for x in miss_types + miss_rels:
    ln_x, line_x = thin_registration(t16, x)
    if ln_x is None:
        unregistered.append(x)
chk(not unregistered,
    "N9 8 种事件类型与 9 条核心关系：要么有标注条目、要么在《16》显式登记为证据不足",
    "实测 事件类型条目 %s；关系条目 %s；实体条目 %s；既无条目又未登记的 %d 个%s%s"
    % (dict(evt_ann) or "无", dict(rel_ann) or "无", dict(ent_ann) or "无",
       len(unregistered), "：" + br(unregistered) if unregistered else "",
       "；登记示例：" + br(["%s→《16》第%s行" % (x, thin_registration(t16, x)[0])
                          for x in (miss_types + miss_rels) if thin_registration(t16, x)[0]], 3)
       if not unregistered else ""))

balanced_terms = ["8 类均衡", "8类均衡", "八类均衡", "按 8 类", "9 条关系均等", "9条关系均等",
                  "八种事件均衡", "均衡分层"]
balanced_targets = [("《15》", t15), ("《16》", t16 or ""), ("标注说明.md", eval_note),
                    ("分层统计.json", read_text(EVAL_STATS, default="") or "")]
bal_hits = scan_terms(balanced_terms, balanced_targets)
bal_all = scan_terms(balanced_terms, balanced_targets, ignore_negation=True)
chk(not bal_hits,
    "N10 不得出现「按 8 类均衡」一类分层声明（含「9 条关系均等」；否定语境除外）",
    "实测 命中（未排除）%d 处；另有否定语境 %d 处已排除（例：卡片行逐字引用验收标准）；"
    "全部命中位置 %s"
    % (len(bal_hits), len(bal_all) - len(bal_hits),
       br(["%s 第%d行「%s」" % (a, b, c) for a, b, c, _d, _e in bal_all], 3) or "无"))


# ==========================================================================
print(); print("=" * 78)
print("O、《15》第八节 第 19 行：证据不足类别的登记与 表 15-C／15-D 的实测值一致"
      "（重大合同、产品、三条公司间关系）")
print("=" * 78)

decl_c = config.TASK_BOOK_TABLES["table_15C"]
calc_cl2 = sum(1 for d in docs if len(d.get("company_list") or []) >= 2)
calc_sc2 = sum(1 for d in docs if len(d.get("subject_companies") or []) >= 2)
chk(calc_cl2 == decl_c["company_list_ge2"] and calc_sc2 == decl_c["subject_companies_ge2"],
    "O1 表 15-C 重算 == 《15》声明（company_list ≥2 篇数、subject_companies ≥2 篇数）",
    "实测 company_list≥2 %d（声明 %d）、subject_companies≥2 %d（声明 %d）"
    % (calc_cl2, decl_c["company_list_ge2"], calc_sc2, decl_c["subject_companies_ge2"]))

decl_d = config.TASK_BOOK_TABLES["table_15D"]
ann_docs = [d for d in docs if d.get("category") == "公告"]
calc_title = {}
for et, pat in config.EVENT_TYPE_TITLE_PATTERNS.items():
    n = 0
    for d in ann_docs:
        title = str(d.get("title") or "")
        if not re.search(pat, title):
            continue
        if et == "产品" and re.search(config.PRODUCT_EXCLUDE_PATTERN, title):
            continue
        n += 1
    calc_title[et] = n
title_bad = {k: (calc_title[k], decl_d["公告标题级"].get(k)) for k in calc_title
             if calc_title[k] != decl_d["公告标题级"].get(k)}
chk(not title_bad,
    "O2 表 15-D 公告标题级 8 类重算 == 《15》声明（正则取自 config.EVENT_TYPE_TITLE_PATTERNS）",
    "实测 重算 %s；与声明不符 %s"
    % (dict(sorted(calc_title.items())), title_bad or "无"))
non_ann = [d for d in docs if d.get("category") != "公告"]
calc_non_ann = sum(1 for d in non_ann
                   if re.search(config.EVENT_TYPE_TITLE_PATTERNS["监管"], str(d.get("title") or "")))
chk(calc_non_ann == decl_d["公告外监管标题级"],
    "O3 表 15-D「公告外监管标题级」重算 == 《15》声明",
    "实测 非公告类目标题命中监管正则 %d 篇（声明 %d）；监管公开信息类目 %d 篇"
    % (calc_non_ann, decl_d["公告外监管标题级"],
       sum(1 for d in docs if d.get("category") == "监管公开信息")))
calc_body = {}
for rel, pat in config.RELATION_BODY_PATTERNS.items():
    if not pat:
        continue
    calc_body[rel] = sum(1 for d in docs if re.search(pat, str(d.get("content") or "")))
body_bad = {k: (calc_body[k], decl_d["正文级"].get(k)) for k in decl_d["正文级"]
            if calc_body.get(k) != decl_d["正文级"].get(k)}
chk(not body_bad,
    "O4 表 15-D 正文级 SUPPLIES／CUSTOMER_OF／COMPETES_WITH 重算 == 《15》声明",
    "实测 重算 %s；与声明不符 %s"
    % ({k: calc_body.get(k) for k in decl_d["正文级"]}, body_bad or "无"))

thin_items = [("重大合同", calc_title.get("重大合同"), decl_d["公告标题级"].get("重大合同")),
              ("产品", calc_title.get("产品"), decl_d["公告标题级"].get("产品")),
              ("SUPPLIES", calc_body.get("SUPPLIES"), decl_d["正文级"].get("SUPPLIES")),
              ("CUSTOMER_OF", calc_body.get("CUSTOMER_OF"), decl_d["正文级"].get("CUSTOMER_OF")),
              ("COMPETES_WITH", calc_body.get("COMPETES_WITH"),
               decl_d["正文级"].get("COMPETES_WITH"))]
thin_problems = []
for name, calc, decl in thin_items:
    ln16, line16 = find_line(t16 or "", name, "证据") if t16 else (None, None)
    if ln16 is None:
        thin_problems.append("%s 未在《16》登记（重算 %s，声明 %s）" % (name, calc, decl))
    elif str(calc) not in line16 and str(decl) not in line16:
        thin_problems.append("%s 的登记行未写出实测值（重算 %s／声明 %s；《16》第%d行）"
                             % (name, calc, decl, ln16))
chk(not thin_problems,
    "O5 证据不足类别的登记与实测值一致（重大合同／产品／三条公司间关系逐项）",
    "实测 五类重算 %s；登记问题 %d 项%s"
    % ("、".join("%s=%s" % (n, c) for n, c, _d in thin_items), len(thin_problems),
       "：" + br(thin_problems) if thin_problems else ""))


# ==========================================================================
print(); print("=" * 78)
print("P、《15》第八节 第 20～21 行：抽取配置四要素齐备且非 TBD；《02》第12.4节「大语言模型」"
      "仍为 TBD；《16》《10》、缓存与导出物中不出现答案生成模型型号")
print("=" * 78)

ELEMS = ["模型", "模型版本", "Prompt 版本", "temperature"]
if t16 is not None:
    sec_ln, sec_title = find_heading(t16, "抽取口径与配置")
    lines16 = t16.split("\n")
    if sec_ln:
        level = len(re.match(r"^#+", lines16[sec_ln - 1]).group(0))
        end = len(lines16)
        for i in range(sec_ln, len(lines16)):
            m = re.match(r"^(#+)\s", lines16[i])
            if m and len(m.group(1)) <= level:
                end = i
                break
        section = "\n".join(lines16[sec_ln - 1:end])
        sec_at = "第%d～%d 行" % (sec_ln, end)
    else:
        section, sec_at = t16, "全文（未命中「抽取口径与配置」小节标题）"
    elem_miss, elem_tbd, elem_line = [], [], {}
    for elem in ELEMS:
        # 在小节正文（跳过小节标题本身）里找**参数行**：优先表格行「| 要素 | 取值 |」，
        # 其次「要素：取值」。这样「模型 | TBD」不会被标题里的要素清单蒙混过关。
        body = section.split("\n")[1:] if section.lstrip().startswith("#") else section.split("\n")
        offset = (sec_ln) if section.lstrip().startswith("#") else (sec_ln - 1 if sec_ln else 0)
        row_pat = re.compile(r"^\|\s*%s(?:（[^|]*）)?\s*\|\s*(.*?)\s*\|" % re.escape(elem))
        kv_pat = re.compile(r"%s\s*[：:]\s*(.+)$" % re.escape(elem))
        hit = None
        for j, line in enumerate(body):
            m = row_pat.match(line.strip())
            if m:
                hit = (offset + j + 1, line.strip(), m.group(1).strip())
                break
        if hit is None:
            for j, line in enumerate(body):
                m = kv_pat.search(line)
                if m and strip_ws(line) != strip_ws(sec_title):
                    hit = (offset + j + 1, line.strip(), m.group(1).strip())
                    break
        if hit is None:
            elem_miss.append(elem)
            continue
        elem_line[elem] = (hit[0], norm_ws(hit[1]) + "  ⇒ 取值「%s」" % hit[2][:60])
        if "TBD" in hit[2].upper() or not hit[2]:
            elem_tbd.append(elem)
    chk(not elem_miss and not elem_tbd,
        "P1 抽取配置四要素（模型、模型版本、Prompt 版本、temperature）齐备且非 TBD",
        "实测 抽取口径与配置小节：%s；缺 %s；含 TBD %s；逐要素：%s"
        % (sec_at, "、".join(elem_miss) or "无", "、".join(elem_tbd) or "无",
           br(["%s→第%d行「%s」" % (k, v[0], v[1][:60]) for k, v in elem_line.items()], 4) or "无"))
    cfg_ok = (config.LLM["model_default"] in section or config.LLM["model_pinned"] in section) \
        and config.LLM["prompt_version"] in section
    chk(cfg_ok, "P2 《16》写明的模型与 Prompt 版本 == config.LLM（不写死在本脚本里）",
        "实测 config：model_default=%s、model_pinned=%s、prompt_version=%s、temperature=%s；"
        "《16》命中模型 %s、Prompt 版本 %s"
        % (config.LLM["model_default"], config.LLM["model_pinned"], config.LLM["prompt_version"],
           config.LLM["temperature"],
           "是" if (config.LLM["model_default"] in section
                    or config.LLM["model_pinned"] in section) else "否",
           "是" if config.LLM["prompt_version"] in section else "否"))
else:
    chk(False, "P1 抽取配置四要素齐备且非 TBD（《16》缺失，无法核验）",
        "实测 《16》缺失：%s；config 侧四要素：模型 %s／Prompt 版本 %s／temperature %s"
        % (rel_to_root(P16), config.LLM["model_default"], config.LLM["prompt_version"],
           config.LLM["temperature"]))
    chk(False, "P2 《16》写明的模型与 Prompt 版本 == config.LLM（《16》缺失，无法核验）",
        "实测 《16》缺失：%s" % rel_to_root(P16))

row_llm = None
for i, line in enumerate(t02.split("\n"), 1):
    m = re.match(r"^\|\s*大语言模型\s*\|\s*([^|]*)\|", line)
    if m:
        row_llm = (i, m.group(1).strip())
        break
chk(row_llm is not None and "TBD" in row_llm[1].upper(),
    "P3 《02》第12.4节 的「大语言模型」行仍为 TBD（答案生成模型归第 8 阶段）",
    "实测 《02》第 %s 行取值「%s」"
    % (row_llm[0] if row_llm else "?", row_llm[1] if row_llm else "未解析到"))

seven_rows = 0
if row_llm:
    lines02 = t02.split("\n")
    start = row_llm[0] - 1
    while start > 0 and lines02[start - 1].strip().startswith("|"):
        start -= 1
    end = row_llm[0] - 1
    while end + 1 < len(lines02) and lines02[end + 1].strip().startswith("|"):
        end += 1
    seven_rows = sum(1 for x in lines02[start:end + 1]
                     if x.strip().startswith("|") and not re.match(r"^\|[\s\-:|]+\|$", x.strip())
                     and "配置项" not in x)
note("P4 证据（第12.4节 固定表行数）",
     "实测 含「大语言模型」的表共 %d 行数据（表头与分隔行已排除）；硬约束 12 要求七项计数不变"
     % seven_rows)

MODEL_ID_RE = re.compile(r"(?:deepseek|gpt|qwen|glm|ernie|claude|llama|gemini|moonshot|kimi)"
                         r"[-a-z0-9._]*", re.I)
model_targets = [("《16》", t16 or ""), ("《10》", t10)]
for name, p in (("nodes.csv", PATHS["nodes"]), ("edges.csv", PATHS["edges"]),
                ("graph_stats.json", PATHS["graph_stats"]),
                ("replay.cypher", PATHS["replay_cypher"])):
    model_targets.append(("导出物/" + name, read_text(p, default="") or ""))
rec_text = read_text(PATHS["extract_records"], default="") or ""
model_targets.append(("抽取结果（缓存侧）", rec_text))
cache_files = sorted(iter_files(config.CACHE_DIR))
cache_text = "\n".join(read_text(p, default="") or "" for p in cache_files[:200])
model_targets.append(("抽取缓存（前 %d 篇）" % min(200, len(cache_files)), cache_text))
ctx_hits, ctx_all = [], []
for label, text in model_targets:
    for i, line in enumerate(str(text or "").split("\n"), 1):
        if not MODEL_ID_RE.search(line):
            continue
        is_answer_ctx = any(k in line for k in ("答案生成", "生成答案", "生成模型", "大语言模型"))
        ctx_all.append((label, i, line.strip()))
        if is_answer_ctx and not NEG_CTX.search(line) and "抽取" not in line:
            ctx_hits.append("%s 第%d行" % (label, i))
chk(not ctx_hits,
    "P5 《16》《10》、缓存与导出物中不出现答案生成模型型号（抽取型号写在抽取语境里是允许的）",
    "实测 模型型号出现 %d 处（均在抽取／Prompt／缓存指纹语境），其中「答案生成」语境 %d 处%s"
    % (len(ctx_all), len(ctx_hits), "：" + br(ctx_hits) if ctx_hits else ""))


# ==========================================================================
print(); print("=" * 78)
print("Q、《15》第八节 第 22 行：未新增第七张表（本阶段不产出 DDL，交付物中不出现六张表以外的表名）")
print("=" * 78)

SIX_TABLES = list(P10_ONT["tables"])
deliverables = [("《16》", t16 or ""), ("《10》(参考)", "")]
for name in sorted(os.listdir(CODE_GRAPH)):
    if name.endswith(".py") or name == "README.md":
        deliverables.append((name, read_text(os.path.join(CODE_GRAPH, name), default="") or ""))
for name, p in (("nodes.csv", PATHS["nodes"]), ("edges.csv", PATHS["edges"]),
                ("graph_stats.json", PATHS["graph_stats"]),
                ("replay.cypher", PATHS["replay_cypher"])):
    deliverables.append(("交付物/" + name, read_text(p, default="") or ""))
for p in iter_files(PATHS["dedup_dir"]):
    deliverables.append((os.path.basename(p), read_text(p, default="") or ""))
ddl_re = re.compile(r"\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|DATABASE|SCHEMA)\b", re.I)
# 「检测模式的引用」：脚本自己写 DDL 关键字**去检查别人**（如 write_graph.py 的
# `if "CREATE TABLE" in ln.upper()`）不算本阶段产出 DDL。这类行照样打印出来供人工确认，
# 只是不计入失败（沿用 跨文档核验.py J／K 两项「启发式检查不许静默跳过」的口径）。
DDL_SEARCH_CTX = re.compile(r"[\"'](?:CREATE|ALTER|DROP)\s+(?:TABLE|DATABASE|SCHEMA)[\"']"
                            r"\s*(?:in\b|not\s+in\b|\)|\])", re.I)
ddl_all = []
for label, text in deliverables:
    for i, line in enumerate(str(text).split("\n"), 1):
        if ddl_re.search(line):
            excluded = bool(NEG_CTX.search(line)) or bool(DDL_SEARCH_CTX.search(line))
            ddl_all.append((label, i, line.strip(), excluded))
ddl_bad = [x for x in ddl_all if not x[3]]
chk(not ddl_bad,
    "Q1 交付物中无关系库 DDL（CREATE／ALTER／DROP TABLE、CREATE DATABASE／SCHEMA）",
    "实测 扫描 %d 个交付文件；DDL 形态命中 %d 处（否定语境／检测模式引用 %d 处，已排除）%s%s"
    % (len(deliverables), len(ddl_bad), len(ddl_all) - len(ddl_bad),
       "：" + br(["%s 第%d行" % (a, b) for a, b, _c, _d in ddl_bad]) if ddl_bad else "",
       "；已排除项：" + br(["%s 第%d行「%s」" % (a, b, c[:70]) for a, b, c, d in ddl_all if d])
       if any(d for _a, _b, _c, d in ddl_all) else ""))

tbl_re = re.compile(r"(?<![A-Za-z_])(?:FROM|JOIN|INSERT\s+INTO|UPDATE|DELETE\s+FROM|REFERENCES)\s+"
                    r"`?([A-Za-z_][A-Za-z0-9_]*)")   # 大小写敏感：只认大写 SQL 关键字，
                                                      # 免得把 Python 的 from／join 当表名（DDL 那条另按不敏感判）
tbl_found = defaultdict(set)
for label, text in deliverables:
    for i, line in enumerate(str(text).split("\n"), 1):
        if re.match(r"^\s*(?:from|import)\s", line, re.I) and not re.search(r"\bFROM\s+`?[a-z_]+_table\b", line):
            continue                     # Python 的 from … import … 不是 SQL（`from __future__` 曾误报）
        for m in tbl_re.finditer(line):
            tbl_found[m.group(1).lower()].add("%s 第%d行" % (label, i))
unknown_tables = {k: v for k, v in tbl_found.items() if k not in {t.lower() for t in SIX_TABLES}}
chk(not unknown_tables,
    "Q2 交付物中出现的表名 ⊆ 《10》的六张表（%s）" % "／".join(SIX_TABLES),
    "实测 命中表名 %s；六张表以内的 %s；越界 %s"
    % (sorted(tbl_found) or "无",
       sorted(k for k in tbl_found if k in {t.lower() for t in SIX_TABLES}) or "无",
       br(["%s（%s）" % (k, br(sorted(v), 1)) for k, v in unknown_tables.items()]) or "无"))
seventh_hits = scan_terms(["第七张表", "第七个表", "新增表", "新建表"], deliverables)
chk(not seventh_hits,
    "Q3 交付物中无「新增表／第七张表」的肯定式声明",
    "实测 命中 %d 处（否定语境已排除）%s"
    % (len(seventh_hits), "：" + br(["%s 第%d行" % (a, b) for a, b, _c, _d, _e in seventh_hits])
       if seventh_hits else ""))


# ==========================================================================
print(); print("=" * 78)
print("R、《15》第八节 第 23 行：数据集只读（T9 结束时的 v2.1 目录文件指纹与开工时一致）")
print("=" * 78)

# 基线发现（本工具的例外常量，见文件头说明）：优先本阶段自行固定的 dataset_fingerprint.json，
# 否则回退第 5 阶段封版后的目录清单；两者都没有时，pilot 记 SKIP、v21 记 FAIL。
baseline, baseline_src = None, None
local_base = os.path.join(PATHS["work_root"], BASELINE_LOCAL)
if os.path.isfile(local_base):
    payload = read_json(local_base, default={}) or {}
    entries = payload.get("entries") or payload.get("files") or payload.get("sha256")
    if isinstance(entries, dict):
        baseline = {k.replace("\\", "/"): v for k, v in entries.items()}
        baseline_src = rel_to_root(local_base) + "（本阶段开工指纹）"
for cand in BASELINE_STAGE5:
    if baseline or not os.path.isfile(cand):
        continue
    payload = read_json(cand, default={}) or {}
    root_decl = str(payload.get("root") or "").rstrip("\\/")
    if root_decl and os.path.normcase(os.path.abspath(root_decl)) != os.path.normcase(
            os.path.abspath(config.DATASET_DIR)):
        continue
    entries = payload.get("entries") or payload.get("files")
    if isinstance(entries, dict):
        baseline = {k.replace("\\", "/"): v for k, v in entries.items()}
        baseline_src = rel_to_root(cand) + "（第 5 阶段封版清单，root 与 v2.1 目录一致）"

cur_files = {}
for p in iter_files(config.DATASET_DIR):
    rel = os.path.relpath(p, config.DATASET_DIR).replace("\\", "/")
    cur_files[rel] = sha256_file(p)
combined = sha256_text("\n".join("%s %s" % (k, cur_files[k]) for k in sorted(cur_files)))
if baseline is None:
    msg = ("实测 v2.1 目录 %d 个文件，组合摘要 %s；未找到任何登记基线"
           "（候选：%s；第 5 阶段清单：%s）"
           % (len(cur_files), combined[:16], rel_to_root(local_base),
              "、".join(os.path.basename(x) for x in BASELINE_STAGE5)))
    if PROFILE == "v21":
        chk(False, "R1 v2.1 目录指纹与开工基线一致（找不到基线，无法比对）",
            msg + "；全量模式下这是硬检查：须先固定基线（如写 <工作目录>\\%s）" % BASELINE_LOCAL)
    else:
        skip("R1 v2.1 目录指纹与开工基线一致（找不到基线，无法比对）",
             msg + "；pilot 模式记 SKIP（全量模式 --profile v21 下为硬检查）")
else:
    diff = sorted(k for k in baseline if k in cur_files and cur_files[k] != baseline[k])
    missing = sorted(k for k in baseline if k not in cur_files)
    extra = sorted(k for k in cur_files if k not in baseline)
    chk(not diff and not missing and not extra,
        "R1 v2.1 目录指纹与开工基线一致（%d 个文件逐文件 sha256 比对）" % len(baseline),
        "实测 基线 %s：%d 个文件；现测 %d 个文件；内容不同 %d 个%s；缺失 %d 个%s；多出 %d 个%s；"
        "组合摘要 %s→%s"
        % (baseline_src, len(baseline), len(cur_files), len(diff),
           "：" + br(diff) if diff else "", len(missing), "：" + br(missing) if missing else "",
           len(extra), "：" + br(extra) if extra else "", "基线", combined[:16]))

hash_bad = []
for ln, d in doc_rows:
    content = str(d.get("content") or "")
    declared = str(d.get("content_sha256_16") or "")
    if declared != sha256_text(content)[:16]:
        hash_bad.append("doc_id=%s（第%d行）" % (d.get("doc_id"), ln))
chk(not hash_bad,
    "R2 每篇文档声明的 content_sha256_16 == 现场重算（数据集未被就地改动）",
    "实测 重算 %d 篇；不一致 %d 篇%s"
    % (len(doc_rows), len(hash_bad), "：" + br(hash_bad) if hash_bad else ""))
note("R3 证据（v2.1 目录读数）",
     "实测 文件 %d 个、组合摘要 %s；文档 %d 篇、文本块 %d 个；基线来源：%s"
     % (len(cur_files), combined[:16], len(doc_rows), len(chunk_rows), baseline_src or "无"))


# ==========================================================================
print(); print("=" * 78)
print("S、《15》第八节 第 24 行：脚本幂等（重复执行不产生重复 event_id；中断后可续跑）")
print("=" * 78)

R, ok_replay = replay_or_skip("S", ["S1 第二次整链重跑后导出物仍逐字节一致",
                                    "S2 重跑不产生重复 event_id（编号集合与原始一致）",
                                    "S3 中断后续跑（--from dedup_events）可用"])
if ok_replay:
    h1, h2 = R.get("hash_after_run_all", {}), R.get("hash_after_run_all_2", {})
    idem_bad = [k for k in ("nodes", "edges", "replay_cypher")
                if h1.get(k) and h2.get(k) and h1[k] != h2[k]]
    chk(R["run_all"]["code"] == 0 and R["run_all_2"]["code"] == 0 and not idem_bad,
        "S1 连续两次整链重跑（run_all --force）导出物逐字节一致",
        "实测 run_all 退出码 %s→%s；三次比对：nodes %s→%s；edges %s→%s；replay %s→%s"
        % (R["run_all"]["code"], R["run_all_2"]["code"],
           (h1.get("nodes") or "缺")[:12], (h2.get("nodes") or "缺")[:12],
           (h1.get("edges") or "缺")[:12], (h2.get("edges") or "缺")[:12],
           (h1.get("replay_cypher") or "缺")[:12], (h2.get("replay_cypher") or "缺")[:12]))
    m_header, m_rows = read_csv_rows(R["mirror"]["nodes"])
    m_events = [(ln, r) for ln, r in m_rows if (r.get("label") or "") == "Event"]
    m_ids = [cell(r, "event_id") for _ln, r in m_events]
    orig_ids = [cell(r, "event_id") for _, r in nodes_rows if (r.get("label") or "") == "Event"]
    chk(not dup_groups(m_ids) and sorted(m_ids) == sorted(orig_ids),
        "S2 重跑不产生重复 event_id（编号集合与原始一致）",
        "实测 重跑 Event %d 条、distinct %d；重复 %s；与原始集合一致：%s"
        % (len(m_ids), len(set(m_ids)), br(sorted(dup_groups(m_ids))) or "无",
           sorted(m_ids) == sorted(orig_ids)))
    fr = R["from_run"]
    chk(fr["code"] == 0, "S3 中断后可续跑：run_all --from dedup_events 退出码 0",
        "实测 退出码=%s、耗时 %.2fs；四个环节脚本单独执行退出码：%s"
        % (fr["code"], fr["seconds"],
           "、".join("%s=%s" % (k, v["code"]) for k, v in R["stage_runs"].items())))
    note("S4 证据（重跑读数）",
         "镜像 %s；复制文件 %d 个；%s；重跑后事件数仍为 %d"
         % (R["tmp"], R["copied"], mirror_note(R), len(m_ids)))


# ==========================================================================
print(); print("=" * 78)
print("T、《15》第八节 第 25 行：代码\\抽取与图谱\\ 的四个环节脚本与入口脚本均可单独执行，"
      "参数全部取自 config.py（脚本内无写死的模型名、日期、路径、阈值）")
print("=" * 78)

STAGE_SCRIPTS = [s["script"] for s in config.RUN_ALL["stages"]] + ["run_all.py", "config.py", "README.md"]
miss_scripts = [n for n in STAGE_SCRIPTS if not os.path.isfile(os.path.join(CODE_GRAPH, n))]
chk(not miss_scripts, "T1 四个环节脚本 ＋ 入口脚本 ＋ config.py ＋ README.md 齐全",
    "实测 %d/%d 存在；缺失 %s"
    % (len(STAGE_SCRIPTS) - len(miss_scripts), len(STAGE_SCRIPTS), "、".join(miss_scripts) or "无"))

R, ok_replay = replay_or_skip("T", ["T2 四个环节脚本与入口脚本单独执行退出码为 0"])
if ok_replay:
    codes = R["stage_runs"]
    chk(all(v["code"] == 0 for v in codes.values()) and R["run_all"]["code"] == 0,
        "T2 四个环节脚本与入口脚本均可单独执行（镜像内 --profile %s 各跑一次，退出码 0）" % PROFILE,
        "实测 %s；入口 run_all.py 退出码=%s"
        % ("；".join("%s 退出码=%s（%.2fs）" % (k, v["code"], v["seconds"])
                     for k, v in codes.items()), R["run_all"]["code"]))
else:
    codes = {}

scripts_src = {n: read_text(os.path.join(CODE_GRAPH, n), default="") or ""
               for n in STAGE_SCRIPTS if n.endswith(".py")}
CFG_SRC = scripts_src.get("config.py", "")
model_names = [config.LLM["model_default"], config.LLM["model_pinned"]]


def code_lines(src):
    """返回 [(行号, 行内容, 是否在三引号字符串块内)]；提示词模板与文档字符串内的**日期示例**
    不算「写死的日期参数」（例如 extract.py 的提示词里写着「2026-08-15 都可以」）。"""
    out, fence = [], None
    for i, line in enumerate(src.split("\n"), 1):
        out.append((i, line, fence is not None))
        for quote in ('"""', "'''"):
            if line.count(quote) % 2 == 1:
                fence = None if fence == quote else quote
    return out


hard_hits, exempt_hits = [], []
for name, src in scripts_src.items():
    for i, line, in_block in code_lines(src):
        if name == "config.py":
            continue                      # config.py 是取值来源，本身豁免（同时充当正对照）
        for mn in model_names:
            if mn and mn in line:
                hard_hits.append("%s 第%d行 写死模型名 %s" % (name, i, mn))
        if re.search(r"[A-Za-z]:[\\/]", line):
            hard_hits.append("%s 第%d行 写死绝对路径" % (name, i))
        if re.search(r"\b20\d{2}-\d{2}-\d{2}\b", line):
            if in_block or line.lstrip().startswith("#"):
                exempt_hits.append("%s 第%d行" % (name, i))
            else:
                hard_hits.append("%s 第%d行 写死日期" % (name, i))
control_ok = any(mn in CFG_SRC for mn in model_names)
chk(control_ok and not hard_hits,
    "T3 脚本内无写死的模型名／日期／绝对路径（config.py 作正对照，只写取值与读取方式）",
    "实测 正对照：config.py 命中模型名 %s；其余脚本命中 %d 处%s；提示词模板／注释内的日期示例 %d 处"
    "（不计入，逐处登记：%s）"
    % ("是" if control_ok else "否（扫描器可能失效）", len(hard_hits),
       "：" + br(hard_hits) if hard_hits else "", len(exempt_hits),
       br(exempt_hits) or "无"))

THRESH_KEYS = ["similarity_min", "time_window_days", "max_tokens", "temperature",
               "min_short_name_chars", "probe_substring_chars", "quote_min_chars",
               "quote_max_chars", "min_doc_chars", "quote_max_chars"]
thresh_hits = []
for name, src in scripts_src.items():
    if name == "config.py":
        continue
    for i, line in enumerate(src.split("\n"), 1):
        for key in THRESH_KEYS:
            if re.search(r"\b%s\s*=\s*[0-9]" % re.escape(key), line):
                thresh_hits.append("%s 第%d行 %s" % (name, i, key))
cfg_ref = sum(src.count("config.") for name, src in scripts_src.items() if name != "config.py")
chk(not thresh_hits,
    "T4 脚本内无写死的阈值（阈值名赋字面量的赋值扫描）",
    "实测 阈值赋值命中 %d 处%s；五个脚本引用 config. 共 %d 处（参数一律经 config 取值）"
    % (len(thresh_hits), "：" + br(thresh_hits) if thresh_hits else "", cfg_ref))

profile_bad = [name for name, src in scripts_src.items()
               if name not in ("config.py",) and "add_argument(\"--profile\"" not in src]
profile_ok = all('choices=["pilot", "v21"]' in scripts_src.get(n, "")
                 for n in STAGE_SCRIPTS if n.endswith(".py") and n != "config.py")
chk(not profile_bad and profile_ok,
    "T5 五个脚本都接受 --profile（pilot／v21 两个取值，与 config.pipeline_paths 对齐）",
    "实测 未声明 --profile 的脚本 %s；choices 均为 pilot／v21：%s"
    % ("、".join(profile_bad) or "无", profile_ok))


# ==========================================================================
print(); print("=" * 78)
print("U、《15》第八节 第 26 行：密钥不入仓库（仓库内无密钥取值；脚本只写读取方式）")
print("=" * 78)

KEY_RE = re.compile(r"(?:sk-[A-Za-z0-9_\-]{16,}|"
                    r"(?:api[_-]?key|API[_-]?KEY|密钥)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{16,}[\"'])")
# 正对照样本用拼接构造：本文件源码里不能出现「真能命中」的密钥形态字面量，否则 U1 会自己命中自己。
control_ok = bool(KEY_RE.search("sk-" + "A" * 24)) and bool(
    KEY_RE.search("api_key" + ' = "' + "B" * 24 + '"'))
repo_targets = []
scan_exts = (".md", ".py", ".json", ".csv", ".txt", ".jsonl", ".html", ".yml", ".yaml")
skip_dirs = {".git", ".idea", "__pycache__", ".venv", "venv"}
skip_prefixes = (os.path.join(ROOT, "阶段05-数据准备", "数据集"),
                 os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "_试跑"),
                 os.path.join(ROOT, "代码", "抽取与图谱", "_试跑"),
                 os.path.join(ROOT, "代码", "抽取与图谱", "_全量"))
for base, dirs, files in os.walk(ROOT):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    if any(os.path.abspath(base).startswith(os.path.abspath(p)) for p in skip_prefixes):
        dirs[:] = []
        continue
    for name in sorted(files):
        if not name.lower().endswith(scan_exts):
            continue
        p = os.path.join(base, name)
        if os.path.getsize(p) > 8 * 1024 * 1024:
            continue
        repo_targets.append((rel_to_root(p), read_text(p, default="") or ""))
key_hits = []
for label, text in repo_targets:
    for i, line in enumerate(text.split("\n"), 1):
        if KEY_RE.search(line):
            key_hits.append("%s 第%d行" % (label, i))
chk(control_ok and not key_hits,
    "U1 仓库内无密钥取值（正对照：密钥形态扫描必须先命中合成样本）",
    "实测 扫描 %d 个可提交文件（排除 .git／数据集／_试跑／_全量 这些不入仓库的目录）；命中 %d 处%s；"
    "正对照 %s" % (len(repo_targets), len(key_hits),
                 "：" + br(key_hits) if key_hits else "", "通过" if control_ok else "失败"))
env_read = "os.environ.get" in CFG_SRC and config.LLM["api_key_env"] in CFG_SRC
key_assign = re.findall(r"api_key\s*=\s*[\"'][^\"']+[\"']", CFG_SRC)
chk(env_read and not key_assign,
    "U2 config.py 只写密钥读取方式（环境变量 %s），不写取值" % config.LLM["api_key_env"],
    "实测 config.py 含 os.environ.get=%s、含 api_key 字面量赋值 %d 处；"
    "密钥形态命中 %d 处（config.py 不豁免扫描）"
    % (env_read, len(key_assign), sum(1 for l, t in repo_targets
                                      for line in t.split("\n") if KEY_RE.search(line))))


# ==========================================================================
print(); print("=" * 78)
print("V、《15》第八节 第 27 行：未出现「%s」（排除语境除外）" % BANNED_VDB)
print("=" * 78)

# 口径与 跨文档核验.py 的 J 项同源（同一行出现否定词即视为排除语境），但范围限定在第 6 阶段的
# 交付物（《16》、抽取与图谱代码与 README、图谱导出物、消歧／去重产物），全工作区的 J 项由
# `python 工具\跨文档核验.py` 单独给出。
vdb_targets = [("《16》", t16 or ""), ("代码/抽取与图谱/README.md",
                                      read_text(os.path.join(CODE_GRAPH, "README.md"), default="") or "")]
for name in sorted(os.listdir(CODE_GRAPH)):
    if name.endswith(".py"):
        vdb_targets.append(("代码/抽取与图谱/" + name,
                            read_text(os.path.join(CODE_GRAPH, name), default="") or ""))
for name, p in (("nodes.csv", PATHS["nodes"]), ("edges.csv", PATHS["edges"]),
                ("graph_stats.json", PATHS["graph_stats"]),
                ("replay.cypher", PATHS["replay_cypher"])):
    vdb_targets.append(("图谱导出/" + name, read_text(p, default="") or ""))
for p in list(iter_files(PATHS["disambig_dir"])) + list(iter_files(PATHS["dedup_dir"])):
    vdb_targets.append((os.path.basename(p), read_text(p, default="") or ""))
vdb_all = scan_terms([BANNED_VDB], vdb_targets, ignore_negation=True)
vdb_hits = scan_terms([BANNED_VDB], vdb_targets)
chk(not vdb_hits,
    "V1 第 6 阶段交付物中不含「%s」（否定语境除外）" % BANNED_VDB,
    "实测 扫描 %d 个交付文本；命中（未排除）%d 处；另有否定语境 %d 处已排除%s"
    % (len(vdb_targets), len(vdb_hits), len(vdb_all) - len(vdb_hits),
       "：" + br(["%s 第%d行「%s」" % (a, b, term[:40]) for a, b, term, _l, _n in vdb_hits], 3)
       if vdb_hits else ""))
note("V2 证据（含否定语境的全部命中，供人工确认）",
     br(["%s 第%d行「%s」" % (a, b, c[:60]) for a, b, c, _d, _e in vdb_all], 5) or "无命中")


# ==========================================================================
print(); print("=" * 78)
print("W、《15》第八节 第 28 行：`15-第6阶段任务书（事件抽取与知识图谱）.md` 与 "
      "`16-事件抽取与知识图谱（第六阶段）.md` 均出现在《00》索引中")
print("=" * 78)

for name, path in (("15-第6阶段任务书（事件抽取与知识图谱）", P15),
                   ("16-事件抽取与知识图谱（第六阶段）", P16)):
    in00 = name in t00
    in00_md = (name + ".md") in t00
    detail = ("实测 《00》%s；带 .md 写法%s；对应文件%s（%s）"
              % ("命中" if in00 else "未命中", "命中" if in00_md else "未命中",
                 "存在" if os.path.isfile(path) else "尚未落盘", rel_to_root(path)))
    ln00 = line_no(t00, name)
    if ln00:
        detail += "；《00》第 %d 行" % ln00
    chk(in00, "W%d 《00》索引登记 `%s`" % (1 if name.startswith("15") else 2, name), detail)


# ==========================================================================
print(); print("=" * 78)
print("X、汇总与收口（《15》第八节 第 29 行：两脚本退出码均为 0 才放行）")
print("=" * 78)

_passed_before = sum(1 for st, _l, _d in results if st == "OK")
_skipped = sum(1 for st, _l, _d in results if st == "SKIP")
print("  检查项合计（A～W）：%d 项，其中通过 %d、失败 %d、SKIP %d"
      % (len(results), _passed_before, len(fails), _skipped))
chk(not fails, "X1 全部检查项通过（任一失败即非零退出；SKIP 不影响退出码）",
    "实测 失败 %d 项：%s" % (len(fails), br(fails, limit=30) if fails else "无"))
chk(os.path.isfile(CROSS_DOC), "X2 工作区跨文档核验脚本存在（本脚本不调用它，供操作者另行运行）",
    "实测 %s：%s；操作者应另行运行：python 工具\\跨文档核验.py（T9 要求两脚本退出码均为 0）"
    % (rel_to_root(CROSS_DOC), "存在" if os.path.isfile(CROSS_DOC) else "缺失"))
if not ARGS.no_replay and REPLAY and not REPLAY.get("error"):
    note("X3 本脚本的只读性（证据）",
         "镜像根目录 %s（%d 个文件，--keep-tmp 可保留）；镜像内的重跑均以镜像为工作目录，"
         "工作区的交付目录一个字节都没写；子进程环境已摘掉 %s，全程不调用模型"
         % (REPLAY.get("tmp"), REPLAY.get("copied"), config.LLM["api_key_env"]))
_SUMMARY_DONE = True
print()
print("  最终：检查项 %d 项，通过 %d，失败 %d"
      % (len(results), sum(1 for st, _l, _d in results if st == "OK"), len(fails)))
print("  另有 SKIP %d 项（pilot 模式下不适用或按命令行跳过；原因见各组 [SKIP] 行，不计入失败）"
      % sum(1 for st, _l, _d in results if st == "SKIP"))

print("=" * 78)
if not fails:
    print("结论：全部通过（通过 %d 项／检查项 %d 项，另有 SKIP %d 项）。第 6 阶段验收通过，退出码 0。"
          % (sum(1 for st, _l, _d in results if st == "OK"), len(results),
             sum(1 for st, _l, _d in results if st == "SKIP")))
else:
    print("结论：存在 %d 项失败（通过 %d 项／检查项 %d 项、SKIP %d 项）："
          % (len(fails), sum(1 for st, _l, _d in results if st == "OK"), len(results),
             sum(1 for st, _l, _d in results if st == "SKIP")))
    for _lab, _det in fail_evidence:
        print("  - %s  %s" % (_lab, _det))
print("=" * 78)

if REPLAY and REPLAY.get("tmp") and not ARGS.keep_tmp:
    shutil.rmtree(REPLAY["tmp"], ignore_errors=True)
elif REPLAY and REPLAY.get("tmp"):
    print("镜像重跑目录保留在：%s" % REPLAY["tmp"])
sys.exit(1 if fails else 0)
