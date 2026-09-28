#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""《18-第7阶段任务书（RAG检索系统）》第 7 阶段交付物的阶段级验收（第八节 28 行逐行落地）。

**行数与编号**：《18》第八节 的表格共 **28 行**（分组 A～AB，末行「汇总与收口」）。本脚本逐行
落地这 28 行：行 → 检查组的映射直接写在每组标题里（例如「A、《18》第八节 第 1 行：…」），
**逐行 1:1、行序与表格一致**。

与另外两个脚本的分工（不重复实现、也不放宽）：

  * `工具\跨文档核验.py` —— 全工作区 Markdown 的通用一致性（检查 A～N：表格列数、跨文档节号
    引用、作废术语、证据属性口径、边界禁用词、路径存在性、索引登记、目录结构、《02》版本号）。
    它的 B／C／H／I／J／K／L／M／N 九项**自动覆盖**本表第 2、3、9、11、19、26、27、28 行的
    一部分；本脚本对这些行**只补足剩余部分，不放宽任何判定**，并在第 28 行**真的调用**它
    （`--strict-citations`），以它的退出码为准。
  * `代码\检索\` 各脚本的 `--selftest` —— 被验收对象的内建自检。本脚本**不采信其结论**：
    一律从输入、代码源码、镜像重跑的产物与《19》正文重新推导后比对；唯一显式引用自检产物的
    地方是第 11／12／14／15／16／17 行的**构造用例结果**与第 24 行的双跑指纹，且都标出读的
    是哪一份产物、并在镜像里**现场重跑生成**（不是读工作区的旧报告）。

**只读纪律（沿用 `工具\验收第6阶段.py` 的镜像根目录做法）**：本脚本对交付物只读。唯一的写动作
发生在系统临时目录里——把 `代码\检索\*.py`、数据集 v2.1 的 11 个输入、预实验问题集三件、
`检索产出\` 的既有产物与 `_工作底稿\_T11\T11_summary.json`（`run_query --run-manifest` 的输入）
**镜像**到一个临时根目录，在那里重跑：

    check_inputs → vector_search --selftest → graph_query --selftest → pipeline --selftest
    → run_query --selftest
    → （pipeline --group C → pre_experiment --quiet → metrics）× 2
    → run_query --run-manifest

再与工作区里的原产物逐字节比对。**绝不写入工作区的任何交付目录**；镜像文件数与本脚本的只读
证据在「汇总与收口」组打印（`--keep-tmp` 保留镜像目录供事后复核）。

用法：

    python 工具\验收第7阶段.py                    # 默认 --profile full：完整镜像重跑（收口判定用）
    python 工具\验收第7阶段.py --profile static   # 只做静态检查：需要镜像重跑的检查项记 SKIP（仅供
                                                  # 快速定位；**这个 profile 不作为收口判定**）
    python 工具\验收第7阶段.py --keep-tmp         # 保留镜像重跑用的临时目录

退出码：0 = full 档全部检查通过且无 SKIP；1 = 存在失败项、环境／链上失败或输入缺失；
        2 = `--profile static` 未执行需要镜像重跑的检查项（不得作为收口判定）。

纪律：**参数一律取 `代码\检索\config.py`**（路径、K／N／预算、g、模型与 revision、组开关都在
那里）；本脚本自带常量的部分只有两类，均已就地注释：① 数据集的表名白名单与禁用词形态
（按《02》第8.4节 与《18》第五节 硬约束 22 构造，拼串以免自我命中）；② 扫描器的正对照样本。
"""

from __future__ import annotations

import argparse
import ast
import atexit
import csv
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# 控制台为 GBK，先把标准输出重设成 UTF-8 再打印中文。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "工具")
CODE = os.path.join(ROOT, "代码", "检索")
STAGE7 = os.path.join(ROOT, "阶段07-RAG检索系统")
OUT = os.path.join(STAGE7, "检索产出")
QS = os.path.join(STAGE7, "预实验问题集")
STAGE5 = os.path.join(ROOT, "阶段05-数据准备")
STAGE6 = os.path.join(ROOT, "阶段06-事件抽取与知识图谱")
P18 = os.path.join(STAGE6, "18-第7阶段任务书（RAG检索系统）.md")
P19 = os.path.join(STAGE7, "19-第7阶段产出文档（RAG检索系统）.md")
P00 = os.path.join(ROOT, "00-项目总览与索引.md")
P02 = os.path.join(ROOT, "02-项目执行总控文档.md")
CROSS_DOC = os.path.join(TOOLS, "跨文档核验.py")

sys.path.insert(0, CODE)
import config  # noqa: E402  第 7 阶段唯一参数来源
import graph_query as gqlayer  # noqa: E402  七个接口的现场调用入口

# 拼串构造：本文件源码内不出现被禁用的四字连写术语，也不出现敏感凭证字样。
BANNED_VDB = "向量" + "数据库"
FORBIDDEN_IMPORT_ROOTS = {"aiohttp", "anthropic", "dashscope", "google.generativeai",
                          "http", "httpx", "openai", "requests", "socket", "urllib",
                          "zhipuai"}
ANSWER_MODEL_PAT = re.compile(
    r"(gpt-?\d|claude|gemini|qwen|ernie|chatglm|glm-\d|kimi|deepseek|llama|moonshot|文心|通义)",
    re.IGNORECASE)
MODEL_ALLOW_MARKS = ("第三方", "复核", "盲标", "留痕", "剥离", "非答案生成", "抽检",
                     "抽取模型", "上游数据生产参数")
DDL_PAT = re.compile(r"CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE", re.IGNORECASE)
SQL_TABLE_REF_PAT = re.compile(
    r"\b(?:FROM|JOIN|INTO|UPDATE|DELETE\s+FROM)\s+[`\"]?([A-Za-z_][A-Za-z0-9_]*)[`\"]?")
SIX_TABLE_NAMES = {"user", "document", "document_chunk", "question", "answer",
                   "answer_evidence"}
DEPLOY_ASSERT = re.compile(r"(已部署|部署了|已经部署|已上线|已运行)")
DEPLOY_NEG = re.compile(r"(未|不得|没有|无|非|禁止|不写|不接入|误读)")
PROHIBIT_NEG = re.compile(r"(不得|不新增|不出现|不产|禁止|没有|未|非)")
CREDENTIAL_NAME_PAT = re.compile(
    r"(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|"
    r"ZHIPU|OPENAI|DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)",
    re.IGNORECASE)

# C／I 两组的“开工指纹”是验收基线，必须独立于被检对象：下面 11 条取自
# 《18》第三节的冻结输入与第 5／6 阶段已入库的指纹记录，不在运行时读取
# `检索产出\input_manifest.json` 作为期望值。
FROZEN_INPUT_FINGERPRINTS = [
    ("documents", "阶段05-数据准备/数据集/v2.1/clean/documents.jsonl",
     4496547, "c838c608c20060adb1366d5c6f7566f9de25016110dc368f7f92fcb8a10f9eea"),
    ("chunks", "阶段05-数据准备/数据集/v2.1/chunks/chunks.jsonl",
     5322875, "2202cbf8e3915598fc9fa57a9fe6d32577705f59ce7bfdfab822903d949e8e44"),
    ("faiss_index", "阶段05-数据准备/数据集/v2.1/index/faiss.index",
     10276909, "4052ed9a251eb0c8276a2bb5fd81e7ced5e4ccdc6cc03c126c0740d68368ef87"),
    ("vector_map", "阶段05-数据准备/数据集/v2.1/index/vector_map.jsonl",
     284916, "e11569c8ba67e63d9af81bd959f0da10d80db0844e7e29fcc04165f17726614b"),
    ("build_meta", "阶段05-数据准备/数据集/v2.1/index/build_meta.json",
     964, "5d886d080d103088e99d9a76ebe0ec34bf9e4dbf81127d364a89389928dea9ee"),
    ("dataset_meta", "阶段05-数据准备/数据集/v2.1/meta/dataset.json",
     3108, "41c82bc43008eaba262c029776e32384417d3cbe9a265f93b6fcd8663f5fc988"),
    ("nodes_csv", "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/nodes.csv",
     708043, "04f2ac227e9595e2df7eefd1f14892edc3327d2b10e950b4f92e4d536c8cb524"),
    ("edges_csv", "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/edges.csv",
     131275, "e86f86d99bb1b227364bc09b05a46db00adfe114ed5f9b04820e82258252b3f0"),
    ("replay_cypher", "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/replay.cypher",
     727503, "8cdb68d0782b04a852614dbbfee51efe81885f059d957b2a96c9655746b6c9ae"),
    ("graph_stats", "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/graph_stats.json",
     24818, "443f437aa3f164ab76618029382f277be52828186d21d6f468ec29f2b5ac2b4a"),
    ("human_confirmation", "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/人工确认清单.json",
     6428, "a17268f8c0694e6b9b38c0c1db1ba89eb6a637b6f3674dd39f3d35ef380f6083"),
]
FROZEN_GRAPH_KEYS = ("nodes_csv", "edges_csv", "replay_cypher", "graph_stats",
                     "human_confirmation")
FROZEN_BY_KEY = {row[0]: row for row in FROZEN_INPUT_FINGERPRINTS}

# 固定结构：28 组、full 档 73 条内容检查 ＋ AB3 汇总 = 74 项；
# static 档未执行的正是 13 个镜像块内的 30 条内容检查
# （2026-09-28 第二轮复审 B-10 整改：W 组新增 W4、X 组新增 X4，两项都在镜像块内）。
EXPECTED_GROUP_ORDER = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L",
                        "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X",
                        "Y", "Z", "AA", "AB"]
EXPECTED_CONTENT_CHECKS = 73
EXPECTED_TOTAL_CHECKS = 74
EXPECTED_STATIC_UNRUN = 30

# U 组独立探针的常量取自《18》第2.3／2.4节与《02》第12.4节，不读
# `k_selection.json` 作为期望值。
GATE_CELL = {"K": 10, "N": 20, "context_token_budget": 3600, "g": 2}
GATE_K_GRID = (5, 10, 15)
GATE_N_GRID = (20, 50, 100)
GATE_G_PROBE = (0, 1, 2, 3, 5)

_ap = argparse.ArgumentParser(
    description="第 7 阶段（RAG 检索系统）：阶段级验收（《18》第八节 28 行逐行）")
_ap.add_argument("--profile", default="full", choices=["full", "static"],
                 help="full＝完整镜像重跑（默认，收口判定用）；static＝只做静态检查、"
                      "需要镜像重跑的检查项记 SKIP（仅供快速定位，不作为收口判定）")
_ap.add_argument("--keep-tmp", action="store_true", help="保留镜像重跑用的临时目录")
ARGS = _ap.parse_args()


# ---------------------------------------------------------------------------
# 报告器：沿用《验收第4阶段文档.py》《验收第5阶段数据.py》《验收第6阶段.py》的
# [OK ]/[FAIL]/[SKIP] 与末尾结论布局，另加 note()（只打印证据，不计入项数）。
# ---------------------------------------------------------------------------
results = []          # [(status, label, detail)]
fails = []
fail_evidence = []
env_fails = []
env_fail_evidence = []
unrun_count = 0
unrun_evidence = []


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
    return bool(ok)


def skip(label, detail=""):
    _emit("SKIP", label, detail)


def envfail(label, detail=""):
    """环境／链上失败：与内容失败分开记账，但同样使 full 档非零退出。"""
    print("  [ENV ] 环境／链上失败（非内容失败）：%s%s"
          % (label, ("  " + detail) if detail else ""))
    env_fails.append(label)
    env_fail_evidence.append((label, detail))


def mark_unrun(label, count, detail=""):
    """static 档的未执行项：既不伪装成通过，也不伪装成 SKIP。"""
    global unrun_count
    unrun_count += int(count)
    unrun_evidence.append((label, int(count), detail))
    print("  [UNRUN] %s：未执行 %d 项%s"
          % (label, int(count), ("  " + detail) if detail else ""))


def note(label, detail=""):
    print("  [OK ] %s%s" % (label, ("  " + detail) if detail else ""))


def br(seq, limit=4):
    seq = list(seq)
    head = "、".join(str(x) for x in seq[:limit])
    return head + ("…（共 %d 个）" % len(seq) if len(seq) > limit else "")


_SUMMARY_DONE = False


def _exit_guard():
    if _SUMMARY_DONE:
        return
    print()
    print("  [FAIL] 验收脚本自身抛异常中断：详见上方 Traceback（按失败记账）")
    print("  最终：检查项 %d 项，通过 %d，失败 %d"
          % (len(results), sum(1 for st, _l, _d in results if st == "OK"), len(fails) + 1))
    print("=" * 78)


atexit.register(_exit_guard)


# ---------------------------------------------------------------------------
# 通用读取与小工具
# ---------------------------------------------------------------------------
def read_text(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return default


def read_json(path, default=None):
    text = read_text(path)
    if text is None:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def read_jsonl(path):
    return [json.loads(line) for line in read_text(path, "").split("\n") if line.strip()]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def line_index(text, needle):
    for i, line in enumerate(text.split("\n"), 1):
        if needle in line:
            return i
    return None


def py_function_source(text, name):
    """取顶层函数的精确源码片段；解析失败或函数不存在时返回空串。"""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(text, node) or ""
    return ""


def section_text(text, start_heading, end_heading=None):
    """取 start_heading 起、end_heading 前的正文（标题行按整行精确匹配）。"""
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.strip() == start_heading:
            start = i
            break
    if start is None:
        return ""
    if end_heading is None:
        return "\n".join(lines[start:])
    for j in range(start + 1, len(lines)):
        if lines[j].strip() == end_heading:
            return "\n".join(lines[start:j])
    return "\n".join(lines[start:])


# ---------------------------------------------------------------------------
# 镜像重跑（唯一一次进程链，供 4／7／8／10～24／27／28 组共用）
# ---------------------------------------------------------------------------
REPLAY = {"error": None, "error_kind": None}
# 2026-09-28 第二轮复审 B-10 整改：`检索产出\run_manifest.json`（《18》第4.2／4.3节 点名的独立
# 入口 `run_query.py --run-manifest` 的产物）此前**零覆盖**——不在镜像链、不在产物新鲜度、
# 不在 T2／X2 逐字节比对集。现把它并入 MIRROR_OUTPUTS：镜像先删、链上 `run_query.py
# --run-manifest` 现场重生成、再与工作区交付产物逐字节比对（X4）。
MIRROR_OUTPUTS = ["input_manifest.json", "pre_experiment_matrix.jsonl", "k_selection.json",
                  "per_question_trace.jsonl", "metrics_pre.jsonl", "run_manifest.json"]
MIRROR_SCRATCH = ["pipeline_assertions.json", "pipeline_trace_D.jsonl",
                  "pipeline_trace_E.jsonl"]
# `run_query.py --run-manifest` 的**输入**（T11 的实测量留痕）：逐字节复跑 run_manifest.json
# 必须有它（否则 run_query 会退回"现场计数"分支而得到不同的字节）。按输入复制、**不参与
# 新鲜度判定**——新鲜度只看 run_manifest.json 本身是否由本次链上运行重新生成。
MIRROR_INPUT_EVIDENCE = ["阶段07-RAG检索系统/_工作底稿/_T11/T11_summary.json"]


class ChainFailure(RuntimeError):
    """环境／链上失败：在镜像链退出码非零或产物新鲜度不成立时立即抛出。"""


def mirror_items():
    items = []
    for name in sorted(os.listdir(CODE)):
        if name.endswith(".py"):
            items.append((os.path.join(CODE, name), os.path.join("代码", "检索", name)))
    for _key, path in config.INPUT_FILES:
        items.append((path, os.path.relpath(path, ROOT)))
    for name in ("questions.jsonl", "说明.md", "题目模板.md"):
        items.append((os.path.join(QS, name), os.path.relpath(os.path.join(QS, name), ROOT)))
    for name in MIRROR_OUTPUTS:
        path = os.path.join(OUT, name)
        if os.path.isfile(path):
            items.append((path, os.path.relpath(path, ROOT)))
    for rel_path in MIRROR_INPUT_EVIDENCE:
        path = os.path.join(ROOT, rel_path.replace("/", os.sep))
        if os.path.isfile(path):
            items.append((path, rel_path.replace("/", os.sep)))
    return items


def build_mirror():
    tmp = tempfile.mkdtemp(prefix="stage7_accept_")
    copied = skipped = 0
    for src, r in mirror_items():
        if not os.path.isfile(src):
            continue
        dst = os.path.join(tmp, r)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isfile(dst):
            skipped += 1
            continue
        shutil.copy2(src, dst)
        copied += 1
    return tmp, copied, skipped


def drop_mirror_outputs(tmp):
    """照第 6 阶段 `drop_exports()` 的做法，先删镜像里的旧产物并留下缺失态证据。"""
    out_dir = os.path.join(tmp, "阶段07-RAG检索系统", "检索产出")
    work_dir = os.path.join(tmp, "阶段07-RAG检索系统", "_工作底稿")
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(work_dir, exist_ok=True)
    state = {}
    for name in MIRROR_OUTPUTS:
        path = os.path.join(out_dir, name)
        state[name] = {"exists_before_drop": os.path.isfile(path)}
        if os.path.isfile(path):
            os.remove(path)
        state[name]["absent_after_drop"] = not os.path.exists(path)
        state[name]["exists_after_run"] = False
    for name in MIRROR_SCRATCH:
        path = os.path.join(work_dir, name)
        state["_工作底稿/" + name] = {"exists_before_drop": os.path.isfile(path)}
        if os.path.isfile(path):
            os.remove(path)
        state["_工作底稿/" + name]["absent_after_drop"] = not os.path.exists(path)
        state["_工作底稿/" + name]["exists_after_run"] = False
    return state


def stripped_env():
    """摘掉凭据类环境变量（只摘名字命中的；不打印任何取值），并置离线加载开关。"""
    pat = re.compile(r"(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|"
                     r"ZHIPU|OPENAI|DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)",
                     re.IGNORECASE)
    env = dict(os.environ)
    removed = sorted(name for name in env if pat.search(name))
    for name in removed:
        env.pop(name, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["HF_HUB_OFFLINE"] = "1"
    env["TRANSFORMERS_OFFLINE"] = "1"
    # 降低 OpenBLAS／OpenMP 的线程峰值，避免镜像内的本地 Embedding 前向在内存偏紧时
    # 因多线程分配失败而把环境问题误显示成内容问题。
    env["OPENBLAS_NUM_THREADS"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    env["MKL_NUM_THREADS"] = "1"
    return env, removed


def run_cmd(argv, cwd, tag, timeout=7200, write_log=True):
    env, removed = stripped_env()
    env[config.FORBID_MODEL_CALLS_ENV] = "1"
    log_dir = os.path.join(cwd, "_accept_logs")
    os.makedirs(log_dir, exist_ok=True)
    t0 = time.time()
    proc = subprocess.run([sys.executable] + list(argv), cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)
    seconds = round(time.time() - t0, 3)
    log_path = os.path.join(log_dir, tag + ".log") if write_log else None
    if write_log:
        with open(log_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("$ python " + " ".join(argv) + "\n--- stdout ---\n" + (proc.stdout or "")
                    + "\n--- stderr ---\n" + (proc.stderr or "")
                    + "\n--- stripped env (names only) = %d: %s ---\n"
                    % (len(removed), "、".join(removed) if removed else "无")
                    + "\n--- exit_code = %d / %.3fs ---\n" % (proc.returncode, seconds))
    return {"tag": tag, "argv": list(argv), "code": proc.returncode, "seconds": seconds,
            "stdout": proc.stdout or "", "stderr": proc.stderr or "", "log": log_path,
            "env_removed": removed,
            "forbid_model_calls": env.get(config.FORBID_MODEL_CALLS_ENV) == "1"}


def require_zero(result, label):
    if result["code"] == 0:
        return result
    stderr_tail = (result.get("stderr") or "").strip().splitlines()[-3:]
    raise ChainFailure("%s 退出码 %d%s" % (
        label, result["code"], "；stderr：" + " / ".join(stderr_tail) if stderr_tail else ""))


INDEPENDENT_PROBE_CODE = r'''
import json
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "代码", "检索"))
import metrics
import pipeline

questions = pipeline.load_questions(pipeline.config.QUESTION_FILES["questions"])
runner = pipeline.PipelineRunner(verbose=False)


def cell(k, n, g):
    # B-16（2026-09-28 整改）：g=0 不再走运行入口（run() 只接受 1 <= g <= K），
    # 独立探针里的 g=0 档改用显式命名的「原字面口径」退化通道 run_legacy_g0()。
    switches = pipeline.normalize_switches("C")
    if int(g) == pipeline.LEGACY_G0:
        run = runner.run_legacy_g0(questions, switches, int(n), int(k), 3600)
    else:
        run = runner.run(questions, switches, int(n), int(k), 3600, int(g))
    rows = [metrics.evaluate_question_chunk_level(
        rec["evidence"], q.get("gold_evidence_chunk_ids") or [], int(k), qid=rec["qid"])
        for rec, q in zip(run["records"], questions)]
    avg = metrics.aggregate_chunk_level(rows, "gate7 independent probe", int(k))
    return {
        "K": int(k), "N": int(n), "g": int(g), "n_questions": len(rows),
        "metrics": {key: avg[key] for key in metrics.CHUNK_METRIC_KEYS},
        "graph_evidence_in_final_total": sum(
            int(rec.get("graph_evidence_in_final_count") or 0) for rec in run["records"]),
    }


cells = {}
for k in (5, 10, 15):
    cells["K%d_N20" % k] = cell(k, 20, 2)
for n in (50, 100):
    cells["K10_N%d" % n] = cell(10, n, 2)
g_curve = {str(g): cell(10, 20, g) for g in (0, 1, 2, 3, 5)}
print("GATE7_INDEPENDENT=" + json.dumps(
    {"cells": cells, "g_curve": g_curve}, ensure_ascii=False, sort_keys=True))
'''.strip()


WORKSPACE_WATCH = None


def workspace_snapshot():
    """工作区只读证据：输入、交付代码／文档／产出、题集与本脚本自身。"""
    paths = [p for _k, p in config.INPUT_FILES]
    paths += [os.path.join(OUT, n) for n in MIRROR_OUTPUTS + ["run_manifest.json"]
              if os.path.isfile(os.path.join(OUT, n))]
    paths += [P18, P19, P00, P02, os.path.abspath(__file__)]
    paths += [os.path.join(CODE, n) for n in os.listdir(CODE)
              if n.endswith(".py") or n == "README.md"]
    paths += [os.path.join(QS, n) for n in ("questions.jsonl", "说明.md", "题目模板.md")]
    return {rel(p): sha256_file(p) for p in sorted(set(paths)) if os.path.isfile(p)}


def ensure_replay():
    global REPLAY, WORKSPACE_WATCH
    if REPLAY.get("done") or REPLAY.get("error"):
        return REPLAY
    if ARGS.profile == "static":
        REPLAY["error"] = "--profile static：跳过镜像重跑（仅供快速定位，不作为收口判定）"
        REPLAY["error_kind"] = "static"
        return REPLAY
    try:
        WORKSPACE_WATCH = workspace_snapshot()
        tmp, copied, skipped = build_mirror()
        REPLAY.update({"tmp": tmp, "copied": copied, "skipped": skipped})
        REPLAY["freshness"] = drop_mirror_outputs(tmp)
        m = lambda *parts: os.path.join(tmp, *parts)
        code_dir = m("代码", "检索")
        steps = [
            ("check_inputs", [os.path.join(code_dir, "check_inputs.py")]),
            ("vector_search_selftest", [os.path.join(code_dir, "vector_search.py"), "--selftest"]),
            ("graph_query_selftest", [os.path.join(code_dir, "graph_query.py"), "--selftest"]),
            ("pipeline_selftest", [os.path.join(code_dir, "pipeline.py"), "--selftest"]),
            # B-10：`run_query.py`（《18》第4.2节 点名的独立入口）进入镜像链，先跑它的 --selftest
            ("run_query_selftest", [os.path.join(code_dir, "run_query.py"), "--selftest",
                                    "--quiet"]),
        ]
        REPLAY["chain"] = []
        for tag, argv in steps:
            result = run_cmd(argv, tmp, "chain_" + tag)
            REPLAY["chain"].append(result)
            require_zero(result, "链上步骤 " + tag)
        cyc = []
        for cycle in ("run1", "run2"):
            r = {}
            r["pipeline"] = run_cmd([os.path.join(code_dir, "pipeline.py"), "--group", "C", "--out",
                                     m("阶段07-RAG检索系统", "检索产出", "per_question_trace.jsonl")],
                                    tmp, "cycle_%s_pipeline" % cycle)
            require_zero(r["pipeline"], "链上 %s pipeline" % cycle)
            r["pre_experiment"] = run_cmd([os.path.join(code_dir, "pre_experiment.py"), "--quiet"],
                                          tmp, "cycle_%s_pre_experiment" % cycle)
            require_zero(r["pre_experiment"], "链上 %s pre_experiment" % cycle)
            r["metrics"] = run_cmd([os.path.join(code_dir, "metrics.py")],
                                   tmp, "cycle_%s_metrics" % cycle)
            require_zero(r["metrics"], "链上 %s metrics" % cycle)
            r["sha"] = {n: sha256_file(m("阶段07-RAG检索系统", "检索产出", n))
                        for n in ("pre_experiment_matrix.jsonl", "k_selection.json",
                                  "per_question_trace.jsonl", "metrics_pre.jsonl")}
            cyc.append(r)
        REPLAY["cycles"] = cyc
        # B-10：让链上现场重生成 `检索产出\run_manifest.json`（镜像里的四个产出已由上面两轮
        # 重新写出；它自带的输入指纹／两次运行 SHA-256 也必须在镜像里能复现同样的字节）
        REPLAY["run_manifest_step"] = run_cmd(
            [os.path.join(code_dir, "run_query.py"), "--run-manifest", "--quiet"],
            tmp, "chain_run_query_run_manifest")
        require_zero(REPLAY["run_manifest_step"], "链上步骤 run_query --run-manifest")
        probe = run_cmd(["-c", INDEPENDENT_PROBE_CODE], tmp, "independent_metric_probe",
                        write_log=False)
        require_zero(probe, "U 组独立指标探针")
        probe_line = next((line for line in (probe.get("stdout") or "").splitlines()
                           if line.startswith("GATE7_INDEPENDENT=")), None)
        if probe_line is None:
            raise ChainFailure("U 组独立指标探针没有输出 GATE7_INDEPENDENT= 结果行")
        REPLAY["independent"] = json.loads(probe_line.split("=", 1)[1])
        fresh_bad = []
        for name in MIRROR_OUTPUTS:
            path = m("阶段07-RAG检索系统", "检索产出", name)
            row = REPLAY["freshness"][name]
            row["exists_after_run"] = os.path.isfile(path)
            if row["exists_after_run"]:
                row["sha256"] = sha256_file(path)
            if not row["absent_after_drop"] or not row["exists_after_run"]:
                fresh_bad.append(name)
        for name in MIRROR_SCRATCH:
            key = "_工作底稿/" + name
            path = m("阶段07-RAG检索系统", "_工作底稿", name)
            row = REPLAY["freshness"][key]
            row["exists_after_run"] = os.path.isfile(path)
            if row["exists_after_run"]:
                row["sha256"] = sha256_file(path)
            if not row["absent_after_drop"] or not row["exists_after_run"]:
                fresh_bad.append(key)
        if fresh_bad:
            raise ChainFailure("镜像产物新鲜度不成立（删除后不存在→运行后出现）：%s"
                               % "、".join(fresh_bad))
        REPLAY["mirror_out_dir"] = m("阶段07-RAG检索系统", "检索产出")
        REPLAY["assertions"] = read_json(
            m("阶段07-RAG检索系统", "_工作底稿", "pipeline_assertions.json"), default={})
        REPLAY["matrix"] = read_jsonl(m("阶段07-RAG检索系统", "检索产出",
                                        "pre_experiment_matrix.jsonl"))
        REPLAY["selection"] = read_json(m("阶段07-RAG检索系统", "检索产出", "k_selection.json"),
                                        default={})
        REPLAY["trace"] = read_jsonl(m("阶段07-RAG检索系统", "检索产出",
                                       "per_question_trace.jsonl"))
        REPLAY["metrics"] = read_jsonl(m("阶段07-RAG检索系统", "检索产出", "metrics_pre.jsonl"))
        REPLAY["trace_D"] = read_jsonl(m("阶段07-RAG检索系统", "_工作底稿", "pipeline_trace_D.jsonl"))
        REPLAY["trace_E"] = read_jsonl(m("阶段07-RAG检索系统", "_工作底稿", "pipeline_trace_E.jsonl"))
        REPLAY["mirror_files"] = sum(len(files) for _r, _d, files in os.walk(tmp))
        _env, removed = stripped_env()
        removed_seen = set(removed)
        for item in REPLAY.get("chain") or []:
            removed_seen.update(item.get("env_removed") or [])
        for cyc in REPLAY.get("cycles") or []:
            for item in cyc.values():
                if isinstance(item, dict):
                    removed_seen.update(item.get("env_removed") or [])
        REPLAY["env_removed"] = sorted(removed_seen)
        after = workspace_snapshot()
        REPLAY["workspace_unchanged"] = (WORKSPACE_WATCH == after)
        REPLAY["workspace_changed"] = sorted(
            k for k in set(WORKSPACE_WATCH) | set(after)
            if WORKSPACE_WATCH.get(k) != after.get(k))
        REPLAY["done"] = True
    except ChainFailure as exc:
        REPLAY["error"] = str(exc)
        REPLAY["error_kind"] = "environment_chain"
    except Exception as exc:
        REPLAY["error"] = "%s: %s" % (type(exc).__name__, exc)
        REPLAY["error_kind"] = "environment_chain"
    return REPLAY


def mirror_or_skip(prefix, labels, planned_checks):
    R = ensure_replay()
    if R.get("error"):
        if R.get("error_kind") == "environment_chain":
            for lab in labels:
                envfail("%s %s" % (prefix, lab), R["error"])
        else:
            for lab in labels:
                skip("%s %s" % (prefix, lab), "镜像重跑未执行：%s" % R["error"])
            mark_unrun(prefix, planned_checks,
                       "static 档未执行镜像块内的 %d 条内容检查" % planned_checks)
        return None
    return R


print()
print("=" * 78)
print("第 7 阶段（RAG 检索系统）专项验收：《18》第八节 28 行逐行（分组 A～AB）")
print("  工作区根目录：%s" % ROOT)
print("  profile=%s；镜像重跑=%s" % (ARGS.profile,
                                    "开启（默认）" if ARGS.profile == "full" else "跳过"))
print("=" * 78)


# ==========================================================================
print()
print("=" * 78)
print("A、《18》第八节 第 1 行：《19》的 9 个必备小节齐全（标题逐字、顺序一致）")
print("=" * 78)
TITLES = ["检索口径与配置", "检索管线实现", "预实验结果", "向量检索实现", "图谱检索实现",
          "证据融合与指标计算", "一致性检查结果", "已知限制与证据不足清单", "对下游的使用说明"]
t19 = read_text(P19, "")
h2 = [line.strip()[2:].strip() for line in t19.split("\n")
      if re.match(r"^##\s+\S", line) and not line.strip().startswith("###")]
chk(h2 == TITLES, "A1 《19》的 9 个必备小节逐字命中且顺序一致",
    "实测 H2 标题 %d 个：%s" % (len(h2), "、".join(h2)))
chk(len(t19) > 20000, "A2 《19》非空且含实质内容", "实测 %d 字符、%d 行"
    % (len(t19), t19.count("\n") + 1))


# ==========================================================================
print()
print("=" * 78)
print("B、《18》第八节 第 2 行：输入齐备：数据集 v2.1 六个 ＋ 图谱导出物 v2.1_v1_2 五个，"
      "且路径与第三节 的输入清单逐条一致")
print("=" * 78)
t18 = read_text(P18, "")
input_rows = [(key, os.path.relpath(path, ROOT)) for key, path in config.INPUT_FILES]
sec3_input = section_text(t18, "## 三、输入清单（已冻结，本阶段只引用、不改动）",
                          "## 四、产出清单")
dataset_rows = [r for r in FROZEN_INPUT_FINGERPRINTS[:6]]
graph_rows = [r for r in FROZEN_INPUT_FINGERPRINTS[6:]]
exist_bad = [r[1] for r in input_rows if not os.path.isfile(os.path.join(ROOT, r[1]))]
listed_bad = [row[1] for row in FROZEN_INPUT_FINGERPRINTS
              if row[1].replace("/", "\\") not in sec3_input]
chk([r[0] for r in input_rows] == [row[0] for row in FROZEN_INPUT_FINGERPRINTS]
    and len(FROZEN_INPUT_FINGERPRINTS) == 11
    and len(dataset_rows) == 6 and len(graph_rows) == 5,
    "B1 输入清单恰为 11 个（数据集 6 ＋ 图谱 5）",
    "实测 %d 个：数据集 %d、图谱 %d" % (len(input_rows), len(dataset_rows), len(graph_rows)))
chk(not exist_bad, "B2 11 个输入文件全部存在", "缺失 %d 个%s"
    % (len(exist_bad), "：" + br(exist_bad) if exist_bad else ""))
chk(not listed_bad, "B3 11 条相对路径与《18》第三节 的输入清单逐条一致",
    "未在第三节 逐字命中 %d 条%s"
    % (len(listed_bad), "：" + br(listed_bad) if listed_bad else ""))


# ==========================================================================
print()
print("=" * 78)
print("C、《18》第八节 第 3 行：输入只读：T11 结束时数据集 v2.1 与图谱导出物 v2.1_v1_2 的"
      "文件指纹与 T1 记录的开工指纹一致")
print("=" * 78)
manifest = read_json(config.INPUT_MANIFEST_PATH, default={})
mrows = manifest.get("files") or []
manifest_by_key = {str(row.get("key")): row for row in mrows}
m_bad = []
manifest_bad = []
for key, rel_path, expected_bytes, expected_sha in FROZEN_INPUT_FINGERPRINTS:
    p = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if (not os.path.isfile(p) or os.path.getsize(p) != expected_bytes
            or sha256_file(p) != expected_sha):
        m_bad.append(key)
    row = manifest_by_key.get(key) or {}
    if (row.get("path") != rel_path or int(row.get("bytes") or -1) != expected_bytes
            or row.get("sha256") != expected_sha):
        manifest_bad.append(key)
frozen_keys = [row[0] for row in FROZEN_INPUT_FINGERPRINTS]
chk([r["key"] for r in mrows] == frozen_keys
    and [k for k, _p in config.INPUT_FILES] == frozen_keys,
    "C1 指纹清单含 11 条且键序与独立冻结基线一致",
    "冻结基线 %d 条：%s；manifest 实测键=%s"
    % (len(frozen_keys), "、".join(frozen_keys), "、".join(str(r.get("key")) for r in mrows)))
chk(not m_bad and not manifest_bad,
    "C2 11 个输入逐个重算 SHA-256 与字节数，并与写死在脚本内的 T1 基线及 manifest 双重一致",
    "实际文件不一致 %d 条%s；manifest 不一致 %d 条%s；manifest.all_ok=%s"
    % (len(m_bad), "：" + br(m_bad) if m_bad else "",
       len(manifest_bad), "：" + br(manifest_bad) if manifest_bad else "",
       manifest.get("all_ok")))


# ==========================================================================
print()
print("=" * 78)
print("D、《18》第八节 第 4 行：向量索引可加载：ntotal = 5018、d = 512、metric_type 为内积；"
      "加载走字节流反序列化，不调用 read_index")
print("=" * 78)
try:
    index = config.read_faiss_index(config.INDEX_PATH)
    chk(int(index.ntotal) == 5018 and int(index.d) == 512 and int(index.metric_type) == 0,
        "D1 现场加载向量索引：三要素实测",
        "实测 ntotal=%d、d=%d、metric_type=%d（内积=0）"
        % (int(index.ntotal), int(index.d), int(index.metric_type)))
except Exception as exc:  # noqa: BLE001
    chk(False, "D1 现场加载向量索引：三要素实测", "加载失败：%s: %s" % (type(exc).__name__, exc))
code_texts = {n: read_text(os.path.join(CODE, n), "") for n in os.listdir(CODE)
              if n.endswith(".py")}
bad_read = [n for n, t in code_texts.items()
            if re.search(r"faiss\s*\.\s*(read_index|write_index)\s*\(", t)]
control = bool(re.search(r"faiss\s*\.\s*(read_index|write_index)\s*\(", "faiss.read_index(x)"))
chk(not bad_read and control, "D2 链上代码不调用向量索引库自带的读／写函数（正对照必须命中）",
    "命中 %d 个文件%s；正对照命中=%s；config.read_faiss_index 用 deserialize_index=%s"
    % (len(bad_read), "：" + br(bad_read) if bad_read else "", control,
       "deserialize_index" in (code_texts.get("config.py") or "")))
del index  # 释放镜像重跑前父进程持有的索引内存


# ==========================================================================
print()
print("=" * 78)
print("E、《18》第八节 第 5 行：三级映射双向可查（5018 行、vector_id 域 0..5017、"
      "chunk_id ↔ vector_id ↔ doc_id 全量重算）")
print("=" * 78)
vmap = read_jsonl(config.VECTOR_MAP_PATH)
chunks_rows = read_jsonl(config.CHUNKS_PATH)
fwd = {int(r["vector_id"]): (int(r["chunk_id"]), int(r["doc_id"])) for r in vmap}
chunk_map = {int(r["chunk_id"]): int(r["doc_id"]) for r in chunks_rows}
chunk_vec = {int(r["chunk_id"]): int(r["vector_id"]) for r in chunks_rows}
bad_fwd = [v for v, (c, d) in fwd.items() if chunk_map.get(c) != d or chunk_vec.get(c) != v]
bad_rev = [c for c, d in chunk_map.items() if fwd.get(chunk_vec.get(c, -1), (None, None))[0] != c]
chk(len(vmap) == 5018 and len(chunks_rows) == 5018 and len(fwd) == 5018
    and sorted(fwd) == list(range(5018)),
    "E1 映射行数 5018、vector_id 域恰为 0..5017",
    "实测 vmap=%d 行、chunks=%d 行、vector_id min=%d max=%d"
    % (len(vmap), len(chunks_rows), min(fwd), max(fwd)))
chk(not bad_fwd and not bad_rev, "E2 全量双向重算：正向错 0、反向漏 0",
    "正向不一致 %d 条、反向不一致 %d 条；抽样 vector_id 0／2509／5017 → %s"
    % (len(bad_fwd), len(bad_rev),
       "；".join("%d→chunk %d" % (v, fwd[v][0]) for v in (0, 2509, 5017))))


# ==========================================================================
print()
print("=" * 78)
print("F、《18》第八节 第 6 行：Embedding 与 revision 未变（config／build_meta／《02》三者一致）；"
      "查询侧不加指令前缀")
print("=" * 78)
bmeta = read_json(config.BUILD_META_PATH, default={})
dmeta = read_json(config.DATASET_META_PATH, default={})
t02 = read_text(P02, "")
emb = config.EMBEDDING
f_ok = (bmeta.get("model_name") == emb["model_name"]
        and bmeta.get("model_revision") == emb["revision"]
        and int(bmeta.get("dim") or 0) == int(emb["dim"])
        and bmeta.get("metric") == emb["metric"]
        and bool(bmeta.get("normalize_embeddings")) is bool(emb["normalize"])
        and bmeta.get("query_instruction") == ""
        and emb["model_name"] in t02 and emb["revision"] in t02)
chk(f_ok, "F1 config 与 build_meta 的模型名／revision／维度／度量／归一化与《02》一致",
    "实测 %s @ %s、dim=%s、metric=%s、query_instruction=%r"
    % (bmeta.get("model_name"), bmeta.get("model_revision"), bmeta.get("dim"),
       bmeta.get("metric"), bmeta.get("query_instruction")))
chk(dmeta.get("dataset_version") == config.DATASET_VERSION
    and dmeta.get("data_cutoff_time") == config.DATA_CUTOFF_TIME,
    "F2 dataset_version 与 data_cutoff_time 与 config 一致",
    "实测 %s／%s" % (dmeta.get("dataset_version"), dmeta.get("data_cutoff_time")))
chk(emb["query_instruction"] == "", "F3 查询侧不加指令前缀",
    "实测 query_instruction=%r（空串）" % emb["query_instruction"])


# ==========================================================================
print()
print("=" * 78)
print("G、《18》第八节 第 7 行：图谱查询层接口齐备（七个接口都有实现与调用入口）")
print("=" * 78)
gq = gqlayer.default_graph()
calls = [
    ("G1", lambda: gq.g1_one_hop("000001")),
    ("G2", lambda: gq.g2_two_hop("000001")),
    ("G3", lambda: gq.g3_events_by_type("股权")),
    ("G4", lambda: gq.g4_company_events("000001")),
    ("G5", lambda: gq.g5_event_evidence("EVT-0001")),
    ("G6", lambda: gq.g6_time_filter(["EVT-0045", "EVT-0046", "EVT-0029"],
                                     "2026-01-01", "2026-12-31")),
    ("G7", lambda: gq.g7_paths("000001", "EVT-0029", 2)),
]
g7_rows = []
for gid, fn in calls:
    try:
        res = fn()
        ok = isinstance(res, dict) and res.get("interface") == gid \
            and res.get("code") in ("OK", "EMPTY") and "cypher" in res
        g7_rows.append((gid, ok, "code=%s count=%s" % (res.get("code"), res.get("count"))))
    except Exception as exc:  # noqa: BLE001
        g7_rows.append((gid, False, "%s: %s" % (type(exc).__name__, exc)))
chk(all(ok for _g, ok, _d in g7_rows), "G1 七个接口逐个现场调用成功（含 EMPTY 语义，不抛异常）",
    br(["%s(%s)" % (g, d) for g, ok, d in g7_rows if ok], limit=7))
src_gq = read_text(os.path.join(CODE, "graph_query.py"), "")
impl_ok = all(("def g%d_" % i) in src_gq for i in range(1, 8)) and "def cypher_table(" in src_gq
chk(impl_ok, "G2 七个接口在 graph_query.py 中都有实现与调用入口",
    "实测 def g1_～g7_ 齐备=%s、cypher_table 存在=%s"
    % (all(("def g%d_" % i) in src_gq for i in range(1, 8)), "def cypher_table(" in src_gq))


# ==========================================================================
print()
print("=" * 78)
print("H、《18》第八节 第 8 行：图谱查询层与 Cypher 一一对应（七个接口，表 18-F 逐行齐备）")
print("=" * 78)
ctable = gqlayer.cypher_table()
ct_ok = [r["id"] for r in ctable] == ["G1", "G2", "G3", "G4", "G5", "G6", "G7"] \
    and all(r["cypher"].startswith("MATCH") for r in ctable)
chk(ct_ok, "H1 cypher_table() 输出七个接口的等效 Cypher（逐条以 MATCH 开头）",
    br(["%s:%s" % (r["id"], r["cypher"][:44]) for r in ctable], limit=7))
miss_cy = [r["id"] for r in ctable if r["cypher"] not in t19]
chk(not miss_cy, "H2 《19》第 5 节 列出同一张表（七条 Cypher 与接口清单逐行命中）",
    "未命中 %d 条%s；《19》含 G1～G7 行=%s"
    % (len(miss_cy), "：" + br(miss_cy) if miss_cy else "",
       all(("| %s |" % g) in t19 for g in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"))))
iface_kw = ["一跳邻居", "两跳邻居", "按事件类型取事件", "按公司取参与事件", "事件到证据块", "时间过滤", "路径枚举"]
chk(all(k in t19 for k in iface_kw), "H3 《19》的接口清单含七个接口的名称（与表 18-F 一致）",
    "命中的接口名 %d／7" % sum(1 for k in iface_kw if k in t19))
del gq  # G／H 已完成；M2 需要时再按需加载，避免与镜像子进程争内存


# ==========================================================================
print()
print("=" * 78)
print("I、《18》第八节 第 9 行：图谱导出物未被改动（五个文件与开工指纹一致）；交付物中不出现"
      "「已部署 Neo4j 服务」一类表述")
print("=" * 78)
g_bad = []
for key in FROZEN_GRAPH_KEYS:
    _key, rel_path, expected_bytes, expected_sha = FROZEN_BY_KEY[key]
    p = os.path.join(ROOT, rel_path.replace("/", os.sep))
    if (not os.path.isfile(p) or os.path.getsize(p) != expected_bytes
            or sha256_file(p) != expected_sha):
        g_bad.append(key)
chk(len(FROZEN_GRAPH_KEYS) == 5 and not g_bad,
    "I1 图谱导出物五个文件与写死在脚本内的独立开工指纹一致",
    "实测 %d 个文件、不一致 %d 个%s"
    % (len(FROZEN_GRAPH_KEYS), len(g_bad),
       "：" + br(g_bad) if g_bad else ""))


def scan_deploy_claims(targets):
    hits = []
    for name, text in targets:
        for i, line in enumerate(text.split("\n"), 1):
            if DEPLOY_ASSERT.search(line) and not DEPLOY_NEG.search(line):
                hits.append("%s:%d %s" % (name, i, line.strip()[:80]))
    return hits


def collect_delivery_texts():
    targets = [("《18》", t18), ("《19》", t19)]
    for n in sorted(os.listdir(CODE)):
        p = os.path.join(CODE, n)
        if os.path.isfile(p) and (n.endswith(".py") or n.endswith(".md")):
            targets.append(("代码/检索/" + n, read_text(p, "")))
    for base in (OUT, QS):
        for n in sorted(os.listdir(base)):
            p = os.path.join(base, n)
            if os.path.isfile(p):
                targets.append((rel(p), read_text(p, "")))
    return targets


delivery_targets = collect_delivery_texts()
deploy_hits = scan_deploy_claims(delivery_targets)
deploy_ctrl = bool(scan_deploy_claims([("CTRL-A", "本系统已部署知识图谱服务并对外提供查询。")])) \
    and bool(scan_deploy_claims([("CTRL-B", "本系统已部署 Neo4j 服务。")]))
chk(not deploy_hits and deploy_ctrl,
    "I2 第 7 阶段交付物不出现「已部署图谱服务」一类的肯定表述（含不带 Neo4j 字面的正对照）",
    "扫描 %d 个文本、命中 %d 处%s；正对照命中=%s；《19》含「未部署」=%s"
    % (len(delivery_targets), len(deploy_hits), "：" + br(deploy_hits) if deploy_hits else "",
       deploy_ctrl, "未部署" in t19))


# ==========================================================================
print()
print("=" * 78)
print("J、《18》第八节 第 10 行：图谱侧候选来源正确（唯一入池依据是 source_chunk_id；"
      "chunk 存在且 doc_id 与 source_doc_id 一致）")
print("=" * 78)
edges_rows = []
with open(config.EDGES_CSV, "r", encoding="utf-8", newline="") as f:
    edges_rows = list(csv.DictReader(f))
semantic = [r for r in edges_rows if r["relation"] != config.EVIDENCED_BY]
with_sc = [r for r in semantic if (r.get("source_chunk_id") or "").strip()]
not_in = [r for r in with_sc if int(r["source_chunk_id"]) not in chunk_map]
doc_mm = [r for r in with_sc
          if int(r["source_chunk_id"]) in chunk_map
          and str(chunk_map[int(r["source_chunk_id"])]) != str(r["source_doc_id"]).strip()]
chk(len(semantic) == 1625 and len(with_sc) == 1625 and not not_in and not doc_mm,
    "J1 全量重算：语义边 1625 条全部带 source_chunk_id，chunk 未命中 0、doc_id 不一致 0",
    "实测语义边 %d、带证据 %d、未命中 %d、不一致 %d"
    % (len(semantic), len(with_sc), len(not_in), len(doc_mm)))
trace_rows = read_jsonl(os.path.join(OUT, "per_question_trace.jsonl"))
audit_bad = []
excluded_nc_bad = []
evidenced_by_excluded = 0
payload_bad = []
for row in trace_rows:
    a = row.get("graph_audit") or {}
    if a.get("invalid_not_in_chunks") or a.get("invalid_doc_mismatch"):
        audit_bad.append(row["qid"])
    if a.get("excluded_no_chunk_id"):
        excluded_nc_bad.append(row["qid"])
    evidenced_by_excluded += int(a.get("excluded_evidenced_by") or 0)
    for path in (row.get("graph_payload") or {}).get("graph_path") or []:
        for r in path.get("relations") or []:
            ev = r.get("evidence") or {}
            cid = str(ev.get("source_chunk_id"))
            if cid == "None":
                continue
            if int(cid) not in chunk_map or str(chunk_map[int(cid)]) != str(ev.get("source_doc_id")):
                payload_bad.append(row["qid"])
chk(not audit_bad and not excluded_nc_bad and not payload_bad and evidenced_by_excluded >= 1,
    "J2 逐题 trace 的 graph_audit 无效计数全 0（EVIDENCED_BY 的排除计数 > 0 为正面证据），"
    "图谱载荷的每条证据都能回溯到同一 doc_id",
    "invalid 异常题 %d 个、缺 chunk_id 题 %d 个、载荷异常 %d 处；EVIDENCED_BY 被排除计数 %d；"
    "audit.chunk_refs 合计 %d"
    % (len(set(audit_bad)), len(set(excluded_nc_bad)), len(payload_bad), evidenced_by_excluded,
       sum((r.get("graph_audit") or {}).get("chunk_refs") or 0 for r in trace_rows)))


# ==========================================================================
print()
print("=" * 78)
print("K、《18》第八节 第 11 行：合并去重口径（chunk_id 无重复；两路同时命中的只保留一条、"
      "不计权不加分）")
print("=" * 78)
k_bad = [r["qid"] for r in trace_rows
         if not (r.get("checks") or {}).get("evidence_unique")
         or not (r.get("checks") or {}).get("candidates_unique")
         or r["evidence"] != r["final_evidence_chunk_ids"]
         or len(r["evidence"]) != len(set(r["evidence"]))]
dual_bad = [r["qid"] for r in trace_rows
            if any(r["evidence"].count(cid) != 1 for cid in r.get("dual_hit_in_final") or [])]
chk(not k_bad and not dual_bad, "K1 逐题 chunk_id 无重复、别名集合一致、两路同命中只出现一次",
    "异常题 %d 个；双命中入集题数 %d／30"
    % (len(set(k_bad + dual_bad)), sum(1 for r in trace_rows if r.get("dual_hit_in_final"))))
R = mirror_or_skip("K2", ["构造用例与镜像重跑产物"], 1)
if R:
    a3 = (R["assertions"] or {}).get("assertion_3a_unique_chunk") or {}
    a3b = (R["assertions"] or {}).get("assertion_3b_constructed_dual_hit") or {}
    detail3b = a3b.get("detail") or {}
    chk(bool(a3.get("ok")) and bool(a3b.get("ok"))
        and detail3b.get("entry_count") == 1 and not detail3b.get("extra_score_fields"),
        "K3 镜像重跑：3a 逐题唯一 + 3b 构造用例（两路命中同一 chunk）只保留一条、无额外加分",
        "3a ok=%s；3b ok=%s；构造 chunk_id=%s、hit_by=%s、入集条数=%s"
        % (a3.get("ok"), a3b.get("ok"), detail3b.get("chunk_id"), detail3b.get("hit_by"),
           detail3b.get("entry_count")))


# ==========================================================================
print()
print("=" * 78)
print("L、《18》第八节 第 12 行：时间过滤位置（按组启用，发生在两路候选合并与去重之前）")
print("=" * 78)
src_pipe = read_text(os.path.join(CODE, "pipeline.py"), "")
i_filt = line_index(src_pipe, "filter_record = apply_time_filter(")
i_merge = line_index(src_pipe, "merged_all = merge_candidates(")
i_filt_dummy = line_index("x\napply_time_filter(a,b,c)\nmerge_candidates(a,b,c)\n",
                          "apply_time_filter(a,b,c)")
i_merge_dummy = line_index("x\napply_time_filter(a,b,c)\nmerge_candidates(a,b,c)\n",
                           "merge_candidates(a,b,c)")
chk(i_filt and i_merge and i_filt < i_merge and i_filt_dummy < i_merge_dummy,
    "L1 代码级顺序断言：时间过滤的调用行号 < 合并去重的调用行号（含正对照）",
    "实测 apply_time_filter 第 %s 行、merge_candidates 第 %s 行；正对照 %s < %s"
    % (i_filt, i_merge, i_filt_dummy, i_merge_dummy))
R = mirror_or_skip("L2", ["一次运行日志与 D 组 trace 的段次序"], 1)
if R:
    selftest_log = ""
    for item in R["chain"]:
        if item["tag"] == "chain_pipeline_selftest":
            selftest_log = item["stdout"]
    d_rows = R["trace_D"]
    seg_ok = all(list(r["segments"]) == ["① 两路取候选", "② 合并去重", "③ 裁剪到预算",
                                         "④ 保留 K", "⑤ 最终证据集合"] for r in d_rows)
    filt_ok = all((r["segments"]["① 两路取候选"]["time_filter"]["enabled"]
                   and r["segments"]["① 两路取候选"]["time_filter"]["g6_called"]) for r in d_rows)
    graph_in = all(r["segments"]["② 合并去重"]["input_graph"]
                   == len(r["time_filter"]["kept_chunk_ids"]) for r in d_rows)
    log_ok = ("时间过滤     图谱" in selftest_log
              and selftest_log.find("时间过滤     图谱") < selftest_log.find("② 合并去重"))
    chk(seg_ok and filt_ok and graph_in and log_ok,
        "L2 一次运行日志：D 组段次序为 ①时间过滤（enabled＋g6_called）→ ②合并去重，"
        "且 ② 的图谱输入等于过滤后条数",
        "段次序一致=%s、D 组 30 题过滤启用=%s、②输入等于过滤后=%s、stdout 行序=%s"
        % (seg_ok, filt_ok, graph_in, log_ok))


# ==========================================================================
print()
print("=" * 78)
print("M、《18》第八节 第 13 行：空值剔除（D／E 组把 event_time 为空的候选一并剔除；"
      "用 544／1100 的空值事件构造用例）")
print("=" * 78)
with open(config.NODES_CSV, "r", encoding="utf-8", newline="") as f:
    node_rows = list(csv.DictReader(f))
event_nodes = [r for r in node_rows if r["label"] == "Event"]
null_ids = [r["node_id"] for r in event_nodes if not (r["event_time"] or "").strip()]
chk(len(event_nodes) == 1100 and len(null_ids) == 544,
    "M1 全量重算节点表：Event 1100 个、event_time 为空 544 个",
    "实测 Event=%d、空值=%d（%.1f%%）" % (len(event_nodes), len(null_ids),
                                        100.0 * len(null_ids) / max(1, len(event_nodes))))
gq = gqlayer.default_graph()
g6_null = gq.g6_time_filter(null_ids, "2000-01-01", "2030-12-31")
chk(g6_null.get("code") in ("OK", "EMPTY") and not g6_null.get("passed_ids")
    and len(g6_null.get("removed_null_ids") or []) == 544
    and g6_null.get("null_policy") == "exclude",
    "M2 构造用例：544 个空值事件全部被剔除、通过 0 个（显式 null_policy=exclude）",
    "实测 通过=%d、空值剔除=%d、越界剔除=%d、null_policy=%s"
    % (len(g6_null.get("passed_ids") or []), len(g6_null.get("removed_null_ids") or []),
       len(g6_null.get("removed_out_of_range_ids") or []), g6_null.get("null_policy")))
chk(config.RETRIEVAL.get("time_filter_null_policy") == "exclude"
    and "time_filter_null_policy" in src_pipe,
    "M3 空值分支是显式配置项（config.RETRIEVAL['time_filter_null_policy']='exclude'）",
    "实测 config=%r、pipeline.py 引用=%s"
    % (config.RETRIEVAL.get("time_filter_null_policy"),
       "time_filter_null_policy" in src_pipe))
del gq  # 七个接口的静态调用已完成；释放内存图给镜像子进程
R = mirror_or_skip("M4", ["D 组 trace 的空值剔除逐题留痕"], 1)
if R:
    d_rows = R["trace_D"]
    null_total = sum(len((r["time_filter"] or {}).get("removed_by_reason", {})
                         .get("null_time_event") or []) for r in d_rows)
    reasons_ok = all(set(((r["time_filter"] or {}).get("removed_by_reason") or {}).keys())
                     >= {"null_time_event", "out_of_range_event", "no_event_time"} for r in d_rows)
    chk(null_total > 0 and reasons_ok,
        "M4 镜像重跑的 D 组 trace：逐题记录空值／越界／无事件三类剔除原因，空值剔除总数 > 0",
        "实测 30 题空值剔除合计 %d 个；三类原因齐备=%s" % (null_total, reasons_ok))


# ==========================================================================
print()
print("=" * 78)
print("N、《18》第八节 第 14 行：保留 K 先于 D／E 分组排序（同一输入 D 与 E 的最终证据集合"
      "逐题完全相同）")
print("=" * 78)
R = mirror_or_skip("N1", ["镜像重跑的断言 1 与 D／E trace"], 2)
if R:
    a1 = (R["assertions"] or {}).get("assertion_1_d_equals_e") or {}
    per = a1.get("per_question") or []
    all_eq = len(per) == 30 and all(
        r.get("equal") and r.get("size_d") == r.get("size_e")
        and sorted(r.get("set_d") or []) == sorted(r.get("set_e") or []) for r in per)
    order_diff = sum(1 for r in per if r.get("order_differs"))
    chk(bool(a1.get("ok")) and all_eq and order_diff >= 1,
        "N1 逐题集合相等断言：30／30 题 D ≡ E（成员与大小），且至少 1 题顺序改变",
        "ok=%s、逐题相等=%s、顺序改变题数=%d" % (a1.get("ok"), all_eq, order_diff))
    dn = {r["qid"]: r["evidence"] for r in R["trace_D"]}
    en = {r["qid"]: r["evidence"] for r in R["trace_E"]}
    same_sets = len(dn) == 30 and all(sorted(dn[q]) == sorted(en[q]) for q in dn)
    order_same = sum(1 for q in dn if dn[q] != en[q])
    chk(same_sets and order_same >= 1,
        "N2 镜像重跑的 D／E 两份 trace 独立复核：逐题集合相等、至少 1 题顺序不同",
        "trace 题数 %d／%d；顺序不同题数=%d" % (len(dn), len(en), order_same))


# ==========================================================================
print()
print("=" * 78)
print("O、《18》第八节 第 15 行：C 与 D 可以不同（逐题双向差集与条数；差集为空的题"
      "不得进入后续对比统计）")
print("=" * 78)
R = mirror_or_skip("O1", ["镜像重跑的断言 2"], 3)
if R:
    a2 = (R["assertions"] or {}).get("assertion_2_c_vs_d_diff") or {}
    per = a2.get("per_question") or []
    consistent = all((r["count_removed"] > 0 or r["count_added"] > 0) == bool(r["measurable"])
                     for r in per)
    nonempty = sum(1 for r in per if r["measurable"])
    chk(bool(a2.get("ok")) and len(per) == 30 and consistent and nonempty >= 1,
        "O1 逐题双向差集：至少 1 题差集非空，可测标志与差集条数一致",
        "ok=%s、可测 %d／%d 题、标志一致=%s" % (a2.get("ok"), nonempty, len(per), consistent))
    chk("不可测" in (a2.get("rule") or "") or ("不可测" in t19 and "不得计入" in t19),
        "O2 差集为空的题必须标记「在该题上不可测」、不得进入后续对比统计",
        "断言记录的 rule 文本含「不可测」=%s；《19》含标记与排除语句=%s"
        % ("不可测" in (a2.get("rule") or ""), ("在该题上不可测" in t19 and "不得计入" in t19)))
    unclear_record = {r["qid"] for r in per if not r["measurable"]}
    all_qids = {str(r["qid"]) for r in R["trace_D"]}
    c_filtered = {str(r["qid"]): {str(x) for x in r.get("candidates_filtered") or []}
                  for r in R["trace"]}
    unclear_ind = set()
    for row in R["trace_D"]:
        qid = str(row["qid"])
        # 与 pipeline.make_assertion_2() 同一口径：C 的过滤后候选 vs D 的过滤后候选
        set_c = c_filtered.get(qid, set())
        set_d = {str(x) for x in row.get("candidates_filtered") or []}
        if not (set_c - set_d or set_d - set_c):
            unclear_ind.add(qid)
    o3_ok = (len(all_qids) == 30 and unclear_ind == unclear_record
             and 1 <= len(unclear_ind) < len(all_qids))
    chk(o3_ok,
        "O3 不可测集由 C／D 两份 trace 独立重算且与断言 2 一致（至少 1 题可测、至少 1 题不可测）",
        "独立重算：可测 %d／%d、不可测 %s；断言记录不可测 %s；集合一致=%s"
        % (len(all_qids - unclear_ind), len(all_qids),
           ",".join(sorted(unclear_ind)) or "无",
           ",".join(sorted(unclear_record)) or "无",
           unclear_ind == unclear_record))


# ==========================================================================
print()
print("=" * 78)
print("P、《18》第八节 第 16 行：裁剪规则固定（先裁远端图谱路径，再按分层保留顺序从尾部往前"
      "裁文本块；裁剪先于证据排序且不使用排序结果；g = 0 退化）")
print("=" * 78)
src_p = src_pipe
i_trim = line_index(src_p, "trimmed = trim_to_budget(")
i_keep = line_index(src_p, "kept = keep_top_k(")
i_order = line_index(src_p, "ordered = order_evidence(")
retention_body = py_function_source(src_p, "retention_breakdown")
layers = [retention_body.find('"layer1_vector_top"'), retention_body.find('"layer2_graph_new"'),
          retention_body.find('"layer3_vector_fill"')]
layer_lines = [line_index(retention_body, '"layer1_vector_top"'),
               line_index(retention_body, '"layer2_graph_new"'),
               line_index(retention_body, '"layer3_vector_fill"')]
layers_ok = all(pos >= 0 for pos in layers) and layers[0] < layers[1] < layers[2]
trim_body = py_function_source(src_p, "trim_to_budget")
trim_no_order_result = bool(trim_body) and "order_evidence(" not in trim_body
# 三层顺序的行为级复核（不只查字符串位置）：用构造记录直接调用 evidence_priority_key，
# 断言 第一层 < 第二层 < 第三层 < 尾部 四档键严格递增（把三层定义搬错位置即失败）。
try:
    import pipeline as _pl
    _probe_records = [
        {"chunk_id": 101, "vector_rank": 1},                            # 第一层
        {"chunk_id": 102, "vector_rank": None, "first_path_key": (1, 0)},  # 第二层（在 plan 里）
        {"chunk_id": 103, "vector_rank": 10},                           # 第三层（rank > K−g）
        {"chunk_id": 104, "vector_rank": None, "first_path_key": (2, 0)},  # 尾部
    ]
    _probe_tiers = [_pl.evidence_priority_key(r, 10, 1, {102: 0}) for r in _probe_records]
    tier_behavior_ok = (
        _probe_tiers[0][0] == _pl.LAYER1_VECTOR_TIER
        and _probe_tiers[1][0] == _pl.LAYER2_GRAPH_TIER
        and _probe_tiers[2][0] == _pl.LAYER3_VECTOR_FILL_TIER
        and _probe_tiers[3][0] == _pl.LEFTOVER_GRAPH_TIER
        and _pl.LAYER1_VECTOR_TIER < _pl.LAYER2_GRAPH_TIER
        < _pl.LAYER3_VECTOR_FILL_TIER < _pl.LEFTOVER_GRAPH_TIER)
except Exception as _exc:  # noqa: BLE001
    tier_behavior_ok = False
    _probe_tiers = ["%s: %s" % (type(_exc).__name__, _exc)]
pri_region = src_p[src_p.find("def priority_rule_text("):
                   src_p.find("# ---------------------------------------------------------------------------\n"
                              "# 一、开关与口径校验")]
pri_order = [pri_region.find(k) for k in ("第一层＝", "第二层＝", "第三层＝")]
pri_ok = (all(x >= 0 for x in pri_order) and pri_order[0] < pri_order[1] < pri_order[2]
          and all(k in pri_region for k in ("K−g", "至多取 g 个", "回填", "全局固化量")))
legacy_ok = ("LEGACY_PRIORITY_RULE" in src_p and "固定原始顺序" in src_p
             and re.search(r"if int\(g\) <= 0:\s*\n\s*return LEGACY_PRIORITY_RULE", src_p)
             is not None)
chk(i_trim and i_keep and i_order and i_trim < i_keep < i_order and layers_ok
    and trim_no_order_result and tier_behavior_ok,
    "P1 代码级顺序断言：裁剪 → 保留 K → 分组排序；三层实现标记严格递增；"
    "裁剪函数不使用分组排序结果；evidence_priority_key 的四档键行为级递增",
    "实测 trim 第 %s 行、keep 第 %s 行、order 第 %s 行；layer1/2/3 字符位=%s、行号=%s；"
    "口径文字的三层次序正确=%s；g<=0 返回原字面口径=%s；裁剪体存在=%s、"
    "不含 order_evidence=%s；四档行为键=%s、行为级递增=%s"
    % (i_trim, i_keep, i_order, layers, layer_lines, pri_ok, legacy_ok, bool(trim_body),
       "order_evidence(" not in trim_body,
       [t[0] if isinstance(t, tuple) else t for t in _probe_tiers], tier_behavior_ok))
chk("先" in src_p and "远端图谱路径" in src_p and "分层保留顺序" in src_p
    and "K−g" in src_p and "至多取 g 个" in src_p and "回填" in src_p,
    "P2 代码内的裁剪与保留顺序含「先裁远端图谱路径」与三层定义（K−g／至多 g／回填）",
    "实测 关键短语齐备=%s"
    % all(k in src_p for k in ("先", "远端图谱路径", "分层保留顺序", "K−g", "至多取 g 个", "回填")))
R = mirror_or_skip("P3", ["镜像重跑的裁剪运行日志与 g = 0 退化"], 2)
if R:
    a5 = (R["assertions"] or {}).get("assertion_5_g0_degenerates") or {}
    ret = (R["assertions"] or {}).get("retention_layers") or {}
    round2 = [r for r in R["matrix"] if r.get("round") == "round2_selected"] or [{}]
    bc = (round2[-1].get("budget_checks") or {})
    trim_ok = (bc.get("questions_with_trimmed_paths", 0) >= 1
               and bc.get("questions_with_trimmed_blocks", 0) >= 1
               and bc.get("questions_exceeding_budget") == 0)
    seg_ok = all(list(r["segments"]).index("③ 裁剪到预算") < list(r["segments"]).index("④ 保留 K")
                 for r in R["trace"])
    chk(bool(a5.get("ok")) and ret.get("g0_run_graph_evidence_total") == 0 and trim_ok and seg_ok,
        "P3 镜像重跑：运行日志显示裁剪与保留 K 的真实条数；g = 0 退化为原字面口径"
        "（图谱侧新增块入集 0 个）",
        "assertion_5 ok=%s；g0 入集=%s；round2 路径裁剪 %s 题／文本块裁剪 %s 题／超预算 %s 题；"
        "①～⑤ 段次序一致=%s"
        % (a5.get("ok"), ret.get("g0_run_graph_evidence_total"),
           bc.get("questions_with_trimmed_paths"), bc.get("questions_with_trimmed_blocks"),
           bc.get("questions_exceeding_budget"), seg_ok))
    chk("g = 0" in t19 and "退化" in t19 and "分层保留顺序" in t19,
        "P4 《19》写明分层保留顺序的三层、g 的全局固化量定位与 g = 0 退化",
        "实测 关键词齐备=%s"
        % all(k in t19 for k in ("分层保留顺序", "第一层", "第二层", "第三层", "全局固化量", "退化")))


# ==========================================================================
print()
print("=" * 78)
print("Q、《18》第八节 第 17 行：候选不足 K 不删题（M < K 的构造用例：题目保留、"
      "空缺记未命中）")
print("=" * 78)
R = mirror_or_skip("Q1", ["镜像重跑的断言 4 与 metrics 行数"], 3)
if R:
    a4 = (R["assertions"] or {}).get("assertion_4_precision_denominator") or {}
    chk(bool(a4.get("ok")) and a4.get("questions_in") == 30 and a4.get("questions_out") == 30,
        "Q1 构造用例：收紧预算后题目保留（输入 30／输出 30），空缺记未命中、分母恒为 K",
        "ok=%s、输入 %s 题、输出 %s 题、small_budget=%s"
        % (a4.get("ok"), a4.get("questions_in"), a4.get("questions_out"), a4.get("small_budget")))
    m_rows = R["metrics"]
    q_rows = [r for r in m_rows if r.get("qid")]
    chk(len(m_rows) == 32 and len(q_rows) == 30,
        "Q2 metrics_pre.jsonl 行数：30 题逐题 ＋ 元数据 ＋ 平均值（没有因候选不足删题）",
        "实测 总行 %d、逐题行 %d" % (len(m_rows), len(q_rows)))
    quiet = [r["qid"] for r in q_rows if r.get("n_final", 0) < 10]
    chk(all(r["precision_at_k"] == round(r["n_hit"] / 10.0, 8) for r in q_rows),
        "Q3 逐题 Precision@K = 命中数 ÷ 10（分母恒为 K，含 n_final=9 的题）",
        "实测 %d 题分母为 10；n_final<10 的题：%s" % (len(q_rows), br(quiet)))


# ==========================================================================
print()
print("=" * 78)
print("R、《18》第八节 第 18 行：四项指标可重算（与 第2.3节 逐条一致；逐题值与平均值"
      "逐字节一致）")
print("=" * 78)
questions = read_jsonl(os.path.join(QS, "questions.jsonl"))
qmap = {str(q["qid"]): q for q in questions}
R = mirror_or_skip("R1", ["镜像重跑的 metrics 产物"], 2)
if R:
    m_rows = R["metrics"]
    meta = next((r for r in m_rows if r.get("record_type") == "metrics_meta"), {})
    q_rows = {r["qid"]: r for r in m_rows if r.get("qid")}
    avg = next((r for r in m_rows if r.get("record_type") == "average"), {})
    K = int(config.require_fixed("K"))
    bad = []
    rec, prec, mrr, cer = [], [], [], []
    for qid, q in qmap.items():
        row = q_rows.get(qid)
        if row is None:
            bad.append(qid + ":缺行")
            continue
        gold = {str(x) for x in (q.get("gold_evidence_chunk_ids") or [])}
        final = [str(x) for x in (row.get("final_ids") or [])]
        hits = [i + 1 for i, cid in enumerate(final) if cid in gold]
        r_ = len(hits) / len(gold) if gold else 0.0
        p_ = len(hits) / float(K)
        m_ = (1.0 / hits[0]) if hits else 0.0
        c_ = 1.0 if gold <= set(final) else 0.0
        rec.append(r_); prec.append(p_); mrr.append(m_); cer.append(c_)
        if (row["recall_at_k"] != round(r_, 8) or row["precision_at_k"] != round(p_, 8)
                or row["mrr"] != round(m_, 8)
                or row["complete_evidence_recall_at_k"] != round(c_, 8)):
            bad.append(qid)
    avg_ok = (avg.get("recall_at_k") == round(sum(rec) / len(rec), 8)
              and avg.get("precision_at_k") == round(sum(prec) / len(prec), 8)
              and avg.get("mrr") == round(sum(mrr) / len(mrr), 8)
              and avg.get("complete_evidence_recall_at_k") == round(sum(cer) / len(cer), 8))
    chk(not bad and avg_ok and meta.get("level") == "chunk" and meta.get("K") == K,
        "R1 独立重算：30 题的 R／P／MRR／CER 与平均值逐题一致（round 8 位）",
        "不一致 %d 题%s；平均值重算一致=%s；均值 R=%.8f P=%.8f MRR=%.8f CER=%.8f"
        % (len(bad), "：" + br(bad) if bad else "", avg_ok, sum(rec) / len(rec),
           sum(prec) / len(prec), sum(mrr) / len(mrr), sum(cer) / len(cer)))
    chk(R["cycles"][0]["sha"]["metrics_pre.jsonl"] == R["cycles"][1]["sha"]["metrics_pre.jsonl"],
        "R2 同一输入两次运行 metrics_pre.jsonl 逐字节一致（SHA-256 相同）",
        "run1=%s；run2=%s"
        % (R["cycles"][0]["sha"]["metrics_pre.jsonl"], R["cycles"][1]["sha"]["metrics_pre.jsonl"]))


# ==========================================================================
print()
print("=" * 78)
print("S、《18》第八节 第 19 行：指标口径不混算（四项只接受 chunk_id；Precision@K 分母恒为 K）")
print("=" * 78)
R = mirror_or_skip("S1", ["镜像重跑的 metrics 产物"], 3)
if R:
    m_rows = R["metrics"]
    rows_ok = all(r.get("level") == "chunk" for r in m_rows if r.get("qid"))
    meta = next((r for r in m_rows if r.get("record_type") == "metrics_meta"), {})
    no_doc = not any(r.get("level") == "document" for r in m_rows)
    text_m = "\n".join(json.dumps(r, ensure_ascii=False) for r in m_rows)
    chk(rows_ok and no_doc and '"level": "document"' not in text_m
        and meta.get("precision_denominator") == "K"
        and meta.get("metric_levels", {}).get("complete_evidence_recall_at_k") == "question",
        "S1 metrics 产物的层级口径：逐题行全部 level=chunk；无文档级数值；分母恒为 K",
        "逐题行 chunk=%s、含 document 行=%s、precision_denominator=%s"
        % (rows_ok, not no_doc, meta.get("precision_denominator")))
    src_m = read_text(os.path.join(CODE, "metrics.py"), "")
    cmd_write_body = py_function_source(src_m, "cmd_write")
    doc_call_in_write = bool(re.search(r"recall_at_k_doc_level_diagnostic\s*\(",
                                       cmd_write_body))
    chk("recall_at_k_doc_level_diagnostic" in src_m and bool(cmd_write_body)
        and not doc_call_in_write,
        "S2 文档级诊断函数存在，但写盘函数 cmd_write 的函数体内不调用它；写盘路径只输出 chunk 级",
        "实测 诊断函数存在=%s、cmd_write 函数体字节=%d、"
        "cmd_write 内文档级调用=%s"
        % ("recall_at_k_doc_level_diagnostic" in src_m, len(cmd_write_body),
           doc_call_in_write))
    prec_ok = all(r["precision_at_k"] == round(r["n_hit"] / float(r["K"]), 8)
                  for r in m_rows if r.get("qid"))
    chk(prec_ok, "S3 逐题数值复核：Precision@K 的实际分母是 K（不是 M）",
        "实测 30／30 题满足 n_hit ÷ K")


# ==========================================================================
print()
print("=" * 78)
print("T、《18》第八节 第 20 行：预实验网格齐备（K ∈ {5,10,15} × N ∈ {20,50,100} 九格，"
      "四项指标与预算占用齐备，且每格 N ≥ K）")
print("=" * 78)
R = mirror_or_skip("T1", ["镜像重跑的网格产物"], 2)
if R:
    rows = R["matrix"]
    r1 = [r for r in rows if r.get("round") == "round1_nonbinding"]
    r2 = [r for r in rows if r.get("round") == "round2_selected"]
    combos = sorted((r["K"], r["N"]) for r in r1)
    want = sorted((k, n) for k in (5, 10, 15) for n in (20, 50, 100))
    metrics_ok = all(set(r.get("metrics") or {}) >=
                     {"recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k"}
                     for r in rows)
    occ_ok = all(set(r.get("occupancy") or {}) >=
                 {"text_tokens", "path_tokens", "event_triple_tokens"} for r in rows)
    nk_ok = all(r.get("N_geq_K") and r["N"] >= r["K"] for r in rows)
    chk(len(r1) == 9 and combos == want and len(r2) == 1 and metrics_ok and occ_ok and nk_ok,
        "T1 九格网格齐备：组合与 K×N 逐格一致、四项指标与预算分账三项齐备、每格 N ≥ K",
        "实测 第一轮 %d 格／第二轮 %d 格；组合=%s；指标齐备=%s；分账齐备=%s；N≥K=%s"
        % (len(r1), len(r2), combos == want, metrics_ok, occ_ok, nk_ok))
    ws_sha = sha256_file(os.path.join(OUT, "pre_experiment_matrix.jsonl"))
    chk(R["cycles"][0]["sha"]["pre_experiment_matrix.jsonl"] == ws_sha,
        "T2 镜像重跑的网格产物与工作区交付产物逐字节一致（SHA-256 相同）",
        "镜像=%s；工作区=%s" % (R["cycles"][0]["sha"]["pre_experiment_matrix.jsonl"], ws_sha))


# ==========================================================================
print()
print("=" * 78)
print("U、《18》第八节 第 21 行：定值符合选择规则（在满足预算的前提下 Complete Evidence "
      "Recall@K 饱和的最小 K；记录里有各档读数与饱和判定）")
print("=" * 78)
R = mirror_or_skip("U1", ["镜像重跑的 k_selection 产物"], 3)
if R:
    sel = R["selection"]
    selected = sel.get("selected") or {}
    rules = sel.get("rules") or {}
    sat = (sel.get("evidence") or {}).get("saturation_under_budget") or {}
    rows_sat = sat.get("rows") or []
    k_sel = selected.get("K")
    feasible = sat.get("feasible_K") or []
    probe = R.get("independent") or {}
    cells = probe.get("cells") or {}
    g_probe = probe.get("g_curve") or {}
    max_gold = max(len(set(str(x) for x in (q.get("gold_evidence_chunk_ids") or [])))
                   for q in questions)
    r1_rows = [r for r in R["matrix"] if r.get("round") == "round1_nonbinding"]
    median_by_k = {int(r["K"]): r["occupancy"]["text_tokens"]["median"]
                   for r in r1_rows if int(r["N"]) == 20}
    anchor_k = min(k for k in GATE_K_GRID if k >= max_gold)
    anchor_n = min(n for n in GATE_N_GRID if n >= anchor_k)
    budget_ind = int(math.ceil(float(median_by_k[anchor_k]) * 1.10 / 100.0) * 100)
    feasible_ind = [k for k in GATE_K_GRID
                    if k >= max_gold and float(median_by_k[k]) <= budget_ind]
    cer_under_ind = {k: float(cells["K%d_N20" % k]["metrics"]
                              ["complete_evidence_recall_at_k"]) for k in GATE_K_GRID}
    k_star_ind = feasible_ind[0]
    for current, nxt in zip(feasible_ind, feasible_ind[1:]):
        if cer_under_ind[nxt] > cer_under_ind[current] + 1e-12:
            k_star_ind = nxt
        else:
            break
    delta15_ind = round(cer_under_ind[15] - cer_under_ind[10], 8)
    delta15_recorded = next((r.get("delta_cer_vs_prev_under_budget") for r in rows_sat
                             if r.get("K") == 15), None)
    gold_excl_ind = (5 < max_gold) and (5 not in feasible_ind)
    budget_excl_ind = (float(median_by_k[15]) > budget_ind) and (15 not in feasible_ind)
    u1_ok = (k_sel == k_star_ind == GATE_CELL["K"]
             and int(selected.get("N") or -1) == GATE_CELL["N"]
             and int(selected.get("context_token_budget") or -1) == budget_ind
             and budget_ind == GATE_CELL["context_token_budget"]
             and feasible == feasible_ind
             and sat.get("selected_K") == k_sel
             and delta15_recorded is not None
             and abs(float(delta15_recorded) - delta15_ind) <= 1e-8
             and delta15_ind <= 0
             and gold_excl_ind and budget_excl_ind
             and "饱和" in (rules.get("K_rule") or ""))
    chk(u1_ok,
        "U1 K 的选择规则执行证据由独立探针重算：gold 排除 K=5、预算排除 K=15、"
        "K=10 处 Δ ≤ 0 且所选 K 为饱和最小可行档",
        "独立重算：max_gold=%d、预算=%d、可行集=%s、选定 K*=%d、Δ(K10→K15)=%+.8f；"
        "产物记录：选定 K=%s、可行集=%s、Δ=%s"
        % (max_gold, budget_ind, feasible_ind, k_star_ind, delta15_ind,
           k_sel, feasible, delta15_recorded))
    ncurve = (sel.get("evidence") or {}).get("N_curve") or []
    n_rows = [r for r in ncurve if r.get("K") == k_sel]
    n_cells_ind = [cells["K10_N%d" % n] for n in GATE_N_GRID]
    max_cer_ind = max(float(row["metrics"]["complete_evidence_recall_at_k"])
                      for row in n_cells_ind)
    min_n_ind = min(int(row["N"]) for row in n_cells_ind
                    if abs(float(row["metrics"]["complete_evidence_recall_at_k"])
                           - max_cer_ind) <= 1e-12)
    n_values_match = all(
        any(int(r.get("N") or -1) == int(row["N"])
            and abs(float(r["metrics"]["complete_evidence_recall_at_k"])
                    - float(row["metrics"]["complete_evidence_recall_at_k"])) <= 1e-12
            and all(abs(float(r["metrics"][key]) - float(row["metrics"][key])) <= 1e-12
                    for key in ("recall_at_k", "precision_at_k", "mrr"))
            for r in n_rows)
        for row in n_cells_ind)
    chk(min_n_ind == selected.get("N") and n_values_match
        and "最小" in (rules.get("N_rule") or ""),
        "U2 N 的选择规则执行证据由独立探针重算：取使 CER 达到最大值的**最小** N",
        "独立重算 N=%s、最大 CER=%.8f、最小 N=%d；产物 N 曲线题数=%d、选定 N=%s"
        % ([row["N"] for row in n_cells_ind], max_cer_ind, min_n_ind,
           len(n_rows), selected.get("N")))
    gcurve = (sel.get("evidence") or {}).get("g_curve") or {}
    g_rows = gcurve.get("primary_rows") or []
    adopted = gcurve.get("adopted_g")
    metric_keys = ("recall_at_k", "precision_at_k", "mrr",
                   "complete_evidence_recall_at_k")
    base_g0 = g_probe["0"]["metrics"]
    worse_by_probe = {
        g: any(float(g_probe[str(g)]["metrics"][key]) + 1e-12
               < float(base_g0[key]) for key in metric_keys)
        for g in GATE_G_PROBE if g > 0}
    not_worse_ind = {g: not worse_by_probe[g] for g in worse_by_probe}
    not_worse_ind[0] = True
    adopted_ind = max([g for g in GATE_G_PROBE if g >= 1 and not_worse_ind.get(g)],
                      default=1)
    g_rows_ind_ok = len(g_rows) == len(GATE_G_PROBE)
    for row in g_rows:
        expected = g_probe.get(str(row.get("g")))
        if expected is None:
            g_rows_ind_ok = False
            continue
        if any(abs(float(row["metrics"][key]) - float(expected["metrics"][key])) > 1e-12
               for key in metric_keys):
            g_rows_ind_ok = False
        if bool(row.get("not_worse_than_g0")) != bool(not_worse_ind.get(int(row["g"]))):
            g_rows_ind_ok = False
    g_ok = (g_rows_ind_ok and adopted == adopted_ind == selected.get("g") == GATE_CELL["g"]
            and adopted_ind >= 1
            and ("不低于下限 1" in (gcurve.get("criterion") or "")
                 or "g ≥ 1" in (gcurve.get("criterion") or ""))
            and int(g_probe["0"]["graph_evidence_in_final_total"]) == 0)
    chk(g_ok,
        "U3 g 的选择规则执行证据由独立探针重算：五点曲线、g=2 不劣于 g=0、"
        "g=3／5 劣化、含下限 1",
        "独立重算探针=%s、采用 g=%d；产物探针=%s、采用 g=%s、选定 g=%s；"
        "判据含下限 1=%s；g=0 图谱侧入集=%d"
        % (list(GATE_G_PROBE), adopted_ind, [r.get("g") for r in g_rows], adopted,
           selected.get("g"), ("不低于下限 1" in (gcurve.get("criterion") or "")),
           int(g_probe["0"]["graph_evidence_in_final_total"])))


# ==========================================================================
print()
print("=" * 78)
print("V、《18》第八节 第 22 行：K／N／Context Token Budget 已固化并登记（写进《19》"
      "并回《02》第12.7节 第一步与 第12.4节）")
print("=" * 78)
sec1 = section_text(t19, "## 检索口径与配置", "## 检索管线实现")
sel = read_json(os.path.join(OUT, "k_selection.json"), default={}).get("selected") or {}
cfg = {k: config.RETRIEVAL.get(k) for k in ("K", "N", "context_token_budget",
                                            "graph_retention_share")}
sel_ok = (sel.get("K") == 10 and sel.get("N") == 20
          and sel.get("context_token_budget") == 3600 and sel.get("g") == 2)
g_range_ok = (isinstance(cfg["graph_retention_share"], int)
              and 1 <= cfg["graph_retention_share"] <= cfg["K"])
chk(sel_ok and cfg["K"] == 10 and cfg["N"] == 20
    and cfg["context_token_budget"] == 3600 and cfg["graph_retention_share"] == 2
    and g_range_ok,
    "V1 config 与 k_selection 的选定值一致：K=10／N=20／3600／g=2，"
    "且 g 位于硬下限 1 与 K 之间（越界即失败）",
    "实测 config=%s；k_selection.selected=%s；g 合法域 1..K=%s"
    % (cfg, sel, g_range_ok))
p19_ok = all(x in sec1 for x in ("**10**", "**20**", "**3600**", "**2**"))
chk(p19_ok, "V2 《19》的「检索口径与配置」写出四个取值（每个都带来源）",
    "实测 命中 **10**／**20**／**3600**／**2**=%s" % p19_ok)
p02_fixed = bool(re.search(r"\|\s*Top-K（K）\s*\|\s*\*\*10\*\*", t02)) \
    and ("向量检索的候选数量 N＝**20**" in t02) \
    and bool(re.search(r"\|\s*Context Token Budget\s*\|\s*\*\*3600\*\*", t02)) \
    and bool(re.search(r"\|\s*图谱侧保留份额（g）\s*\|\s*\*\*2\*\*", t02))
p02_reg = ("图谱侧保留份额 g = 2、Top-K（K）= 10、N = 20、Context Token Budget = 3600" in t02)
p02_ok = p02_fixed and p02_reg
fixed_table = "第 7 阶段的四项检索侧配置量已由 T8 检索预实验定值并随本节登记冻结" in t02
chk(p02_ok and fixed_table, "V3 《02》第12.4节 固定表与 第12.7节 第一步 已登记四个取值",
    "实测 固定表四行命中=%s、登记句命中=%s、冻结语句=%s"
    % (p02_fixed, p02_reg, fixed_table))


# ==========================================================================
print()
print("=" * 78)
print("W、《18》第八节 第 23 行：0 次大语言模型调用（摘除密钥的环境下全链路跑通，"
      "运行记录里调用次数为 0）")
print("=" * 78)
chain_files = ["check_inputs.py", "vector_search.py", "graph_query.py", "pipeline.py",
               "pre_experiment.py", "metrics.py"]
chain_text = {n: read_text(os.path.join(CODE, n), "") for n in chain_files}


def _forbidden_module(name):
    name = str(name or "")
    return any(name == root or name.startswith(root + ".") for root in FORBIDDEN_IMPORT_ROOTS)


def _credential_literal(value):
    return isinstance(value, str) and bool(CREDENTIAL_NAME_PAT.search(value))


def scan_forbidden_paths(files):
    """扫描网络／凭据路径：import 根、getenv／environ 凭据名、URL 字面量。"""
    hits = []
    for name, text in files.items():
        try:
            tree = ast.parse(text)
        except SyntaxError:
            hits.append("%s:无法解析" % name)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _forbidden_module(alias.name):
                        hits.append("%s:%d:import %s" % (name, node.lineno, alias.name))
            elif isinstance(node, ast.ImportFrom):
                if _forbidden_module(node.module):
                    hits.append("%s:%d:from %s" % (name, node.lineno, node.module))
            elif isinstance(node, ast.Call):
                func = node.func
                attr = func.attr if isinstance(func, ast.Attribute) else (
                    func.id if isinstance(func, ast.Name) else "")
                if attr in ("getenv", "get") and node.args \
                        and _credential_literal(getattr(node.args[0], "value", None)):
                    hits.append("%s:%d:%s(凭据名)" % (name, node.lineno, attr))
            elif isinstance(node, ast.Subscript):
                value = node.value
                if isinstance(value, ast.Attribute) and value.attr == "environ" \
                        and _credential_literal(getattr(node.slice, "value", None)):
                    hits.append("%s:%d:environ[凭据名]" % (name, node.lineno))
        for i, line in enumerate(text.split("\n"), 1):
            if re.search(r"https?://", line, re.IGNORECASE):
                hits.append("%s:%d:URL 字面量" % (name, i))
    return hits


scan_files = dict(chain_text)
scan_files["run_query.py"] = read_text(os.path.join(CODE, "run_query.py"), "")
key_hits = scan_forbidden_paths(scan_files)
ctrl_text = (
    "import httpx\n"
    "import os\n"
    "TOKEN = os.getenv(\"OPENAI_API_KEY\")\n"
    "URL = \"https://example.invalid/v1\"\n"
)
ctrl_hits = scan_forbidden_paths({"CTRL": ctrl_text})
ctrl_ok = (any("import httpx" in h for h in ctrl_hits)
           and any("凭据名" in h for h in ctrl_hits)
           and any("URL 字面量" in h for h in ctrl_hits))
guard_declared = (getattr(config, "FORBID_MODEL_CALLS_ENV", "") == "STAGE7_FORBID_MODEL_CALLS")
chk(not key_hits and ctrl_ok and config.MODEL_CALLS_ALLOWED == 0 and guard_declared,
    "W1 链上六个脚本与 run_query.py 的网络／凭据路径 0 处；"
    "config 硬守卫已声明且正对照三类命中",
    "扫描文件 %d 个、命中 %d 处%s；正对照命中 %d 处%s；MODEL_CALLS_ALLOWED=%r；"
    "硬守卫=%s"
    % (len(scan_files), len(key_hits), "：" + br(key_hits) if key_hits else "",
       len(ctrl_hits), "：" + br(ctrl_hits) if ctrl_hits else "",
       config.MODEL_CALLS_ALLOWED, guard_declared))
R = mirror_or_skip("W2", ["摘除密钥的镜像全链路运行记录"], 3)
if R:
    codes = [c["code"] for c in R["chain"]]
    cycle_codes = [s["code"] for cyc in R["cycles"] for s in cyc.values()
                   if isinstance(s, dict) and "code" in s]
    all_zero = all(c == 0 for c in codes + cycle_codes)
    all_guarded = all(c.get("forbid_model_calls") for c in R["chain"]) and all(
        s.get("forbid_model_calls") for cyc in R["cycles"] for s in cyc.values()
        if isinstance(s, dict) and "code" in s)
    texts = [c["stdout"] for c in R["chain"]] + \
            [cyc["pre_experiment"]["stdout"] for cyc in R["cycles"]] + \
            [cyc["pipeline"]["stdout"] for cyc in R["cycles"]]
    claim = sum(t.count("0 次大语言模型／外部接口调用") for t in texts)
    removed = list(R.get("env_removed") or [])
    chk(all_zero and all_guarded,
        "W2 摘除密钥并启用运行时硬哨兵后全链路（六步 ＋ 两次三轮＋独立探针）退出码全 0；"
        "调用次数由“无网络／凭据路径即零调用”保证，不再以固定字面量为判据",
        "实测 退出码全 0=%s（%d 条命令）；硬哨兵生效=%s；真实摘除凭据类变量 %d 个：%s；"
        "stdout 打印 0 次调用 %d 处（仅作留痕）"
        % (all_zero, len(codes) + len(cycle_codes), all_guarded, len(removed),
           "、".join(removed) if removed else "无", claim))
    chk(("本地 Embedding 前向" in t19) and ("不计入「模型调用」" in t19)
        and ("全程未跑模型" in t19),
        "W3 《19》写明口径区分：本地 Embedding 前向不计入模型调用，但不得写成全程未跑模型",
        "实测 三处表述齐备=%s"
        % all(k in t19 for k in ("本地 Embedding 前向", "不计入「模型调用」", "全程未跑模型")))
    # B-10（2026-09-28 整改）：`run_query.py`（《18》第4.2节 点名的独立入口）此前不在镜像链上、
    # 零验收覆盖；现在它在镜像里真跑 --selftest，并把"自证结论：n／n 条通过"作为判据。
    rq_step = next((c for c in (R.get("chain") or [])
                    if c.get("tag") == "chain_run_query_selftest"), None)
    rq_out = (rq_step or {}).get("stdout") or ""
    rq_m = re.search(r"自证结论：(\d+)／(\d+) 条通过", rq_out)
    rq_ok = (rq_step is not None and rq_step.get("code") == 0 and rq_m is not None
             and rq_m.group(1) == rq_m.group(2))
    chk(rq_ok,
        "W4 run_query.py --selftest 在镜像链上真跑（独立入口进入覆盖）：退出码 0 且自证结论"
        "条数全部通过",
        "镜像链步骤 tag=%s；退出码=%s；自证结论=%s"
        % ((rq_step or {}).get("tag"), (rq_step or {}).get("code"),
           ("%s／%s 条通过" % (rq_m.group(1), rq_m.group(2))) if rq_m else "<未解析到>"))


# ==========================================================================
print()
print("=" * 78)
print("X、《18》第八节 第 24 行：重放逐字节一致（同一输入两次运行，网格结果、逐题 trace "
      "与指标输出逐字节一致）")
print("=" * 78)
R = mirror_or_skip("X1", ["两次运行的 SHA-256 比对"], 4)
if R:
    files = ["pre_experiment_matrix.jsonl", "k_selection.json",
             "per_question_trace.jsonl", "metrics_pre.jsonl"]
    same = all(R["cycles"][0]["sha"][n] == R["cycles"][1]["sha"][n] for n in files)
    ws_same = all(R["cycles"][0]["sha"][n] == sha256_file(os.path.join(OUT, n)) for n in files)
    chk(same, "X1 四个文件两次运行 SHA-256 相同（逐字节一致）",
        "；".join("%s %s==%s" % (n, R["cycles"][0]["sha"][n][:12],
                                 R["cycles"][1]["sha"][n][:12]) for n in files))
    # B-10：逐字节比对集扩到 MIRROR_OUTPUTS 的**全部六个**产物（含 run_manifest.json）
    outs = list(MIRROR_OUTPUTS)
    outs_same = all(sha256_file(os.path.join(R["mirror_out_dir"], n))
                    == sha256_file(os.path.join(OUT, n)) for n in outs)
    chk(ws_same and outs_same,
        "X2 镜像重跑的全部 %d 个 MIRROR_OUTPUTS 产物与工作区交付产物逐字节一致" % len(outs),
        "；".join("%s 工作区=%s" % (n, sha256_file(os.path.join(OUT, n))[:12]) for n in outs))
    no_ts = all(not any(k in ("timestamp", "seconds", "elapsed", "duration") for k in row)
                for row in R["matrix"])
    chk(no_ts, "X3 参与比对的文件不含运行时间戳与耗时字段",
        "实测 网格行内无 timestamp／seconds／elapsed／duration=%s" % no_ts)
    # B-10：run_manifest.json 的"可复跑"专项——它必须由链上 `run_query.py --run-manifest`
    # 在镜像里现场重生成（新鲜度另由 REPLAY['freshness'] 保证），并与工作区交付产物逐字节一致。
    rm_ws = os.path.join(OUT, "run_manifest.json")
    rm_mi = os.path.join(R["mirror_out_dir"], "run_manifest.json")
    rm_row = (R.get("freshness") or {}).get("run_manifest.json") or {}
    rm_sha_ws = sha256_file(rm_ws)
    rm_sha_mi = sha256_file(rm_mi) if os.path.isfile(rm_mi) else "<缺失>"
    rm_step = R.get("run_manifest_step") or {}
    chk(rm_row.get("absent_after_drop") and rm_row.get("exists_after_run")
        and rm_sha_ws == rm_sha_mi and rm_step.get("code") == 0,
        "X4 run_manifest.json 由链上 run_query.py --run-manifest 现场重生成（先删后生成），"
        "且与工作区交付产物逐字节一致",
        "镜像链步骤退出码=%s；删除后缺失=%s、运行后出现=%s；镜像 sha=%s…；工作区 sha=%s…；"
        "MIRROR_OUTPUTS=%s"
        % (rm_step.get("code"), rm_row.get("absent_after_drop"), rm_row.get("exists_after_run"),
           str(rm_sha_mi)[:16], rm_sha_ws[:16], "、".join(MIRROR_OUTPUTS)))


# ==========================================================================
print()
print("=" * 78)
print("Y、《18》第八节 第 25 行：预实验问题集（30 题、三个标签、参考答案与 gold 证据；"
      "gold 数 ≤ K；声明为预实验用、不是正式测试集、未复用 260 条参照集）")
print("=" * 78)
y_bad = []
gold_max = 0
n_time = 0
for q in questions:
    qid = str(q.get("qid"))
    gold = [int(x) for x in (q.get("gold_evidence_chunk_ids") or [])]
    gold_max = max(gold_max, len(gold))
    if q.get("time_constraint") == "有":
        n_time += 1
    if (q.get("task_type") not in ("事实型", "事件型", "关系型")
            or q.get("gold_hop_depth") not in (0, 1, 2)
            or q.get("time_constraint") not in ("有", "无")
            or not (q.get("reference_answer") or "").strip()
            or not gold or not (q.get("source_material") or [])
            or int(q.get("gold_evidence_count") or -1) != len(gold)
            or any(g not in chunk_map for g in gold)):
        y_bad.append(qid)
chk(len(questions) == 30 and len(set(str(q["qid"]) for q in questions)) == 30
    and not y_bad and gold_max <= int(config.require_fixed("K")),
    "Y1 30 题、qid 唯一、三标签取值合法、参考答案与 gold 齐备、gold 数 ≤ K=10",
    "实测 %d 题、异常 %d 题%s；最大 gold 数=%d；带时间约束 %d 题"
    % (len(questions), len(y_bad), "：" + br(y_bad) if y_bad else "", gold_max, n_time))
note("Y2 题集分布（只打印证据）", "gold 数区间 1～%d；带时间约束 %d 题；题集口径见 说明.md"
     % (gold_max, n_time))
readme_q = read_text(os.path.join(QS, "说明.md"), "")
no_formal = "它不是第 10 阶段的正式测试集" in readme_q
no_260 = "未复用第 6 阶段的 260 条抽取参照集" in readme_q
refset = "模型参照集" in readme_q
text_all = readme_q + "\n" + "\n".join(json.dumps(q, ensure_ascii=False) for q in questions)
forbid = ["人工" + "金标准", "人工" + "一致率"]
forb_hits = []
for i, line in enumerate(text_all.split("\n"), 1):
    if any(w in line for w in forbid) and not DEPLOY_NEG.search(line):
        forb_hits.append("第%d行:%s" % (i, line.strip()[:80]))
ctrl_sentence = "这是人工" + "金标准"
ref_ctrl = any(w in ctrl_sentence for w in forbid) and not DEPLOY_NEG.search(ctrl_sentence)
chk(no_formal and no_260 and refset and not forb_hits and ref_ctrl,
    "Y2 题集声明为非正式测试集、未复用 260 条参照集；题集文本不出现肯定的"
    "「人工金标准／人工一致率」（否定语境不计；正对照必须命中）",
    "实测 非正式声明=%s、未复用声明=%s、模型参照集定性=%s、禁用表述命中 %d 处、正对照=%s"
    % (no_formal, no_260, refset, len(forb_hits), ref_ctrl))


# ==========================================================================
print()
print("=" * 78)
print("Z、《18》第八节 第 26 行：索引登记（《18》与《19》均出现在《00》第三节 编号表"
      "与第四节 文件地图中）")
print("=" * 78)
t00 = read_text(P00, "")
sec3 = section_text(t00, "### 1. 文档编号（01～19）——项目自己的文档序列",
                    "### 2. 文献池编号（KG-n／RAG-n／FIN-n／SYS-n）——检索阶段的内部编号")
sec4 = section_text(t00, "## 四、文件地图", "## 五、冻结口径速查")
n18 = "18-第7阶段任务书（RAG检索系统）"
n19 = "19-第7阶段产出文档（RAG检索系统）"
chk(n18 in sec3 and n19 in sec3, "Z1 《18》与《19》都在《00》第三节 编号表里",
    "实测 《18》命中=%s、《19》命中=%s（编号表节内）" % (n18 in sec3, n19 in sec3))
chk(n18 in sec4 and n19 in sec4, "Z2 《18》与《19》都在《00》第四节 文件地图里",
    "实测 《18》命中=%s、《19》命中=%s（文件地图节内）" % (n18 in sec4, n19 in sec4))
chk(os.path.isfile(os.path.join(STAGE7, n19 + ".md")),
    "Z3 《19》文件实际落盘且文件名与登记一致",
    "实测 %s：%s" % (rel(P19), "存在" if os.path.isfile(P19) else "缺失"))


# ==========================================================================
print()
print("=" * 78)
print("AA、《18》第八节 第 27 行：术语与边界（无禁用四字连写术语；不新增第七张表、"
      "不产出 DDL、不出现六张表以外的表名；不出现答案生成模型型号）")
print("=" * 78)
aa_targets = list(delivery_targets)
vdb_hits = [name for name, text in aa_targets if BANNED_VDB in text]
vdb_ctrl = BANNED_VDB in ("外部样本：" + BANNED_VDB + "。")
chk(not vdb_hits and vdb_ctrl,
    "AA1 交付物中不含被禁用的四字连写术语（一律写「向量索引」或「向量检索组件」；正对照必须命中）",
    "扫描 %d 个交付文本、命中文件 %d 个%s；正对照=%s；《19》用「向量索引」=%d 次"
    % (len(aa_targets), len(vdb_hits), "：" + br(vdb_hits) if vdb_hits else "",
       vdb_ctrl, t19.count("向量索引")))
ddl_hits = [name for name, text in aa_targets if DDL_PAT.search(text)]
ddl_ctrl = bool(DDL_PAT.search("CREATE TABLE question (id INT);"))
seventh = []
for name, text in aa_targets:
    for i, line in enumerate(text.split("\n"), 1):
        if re.search(r"第七张表|七张表|7 张表|新增表", line) \
                and not PROHIBIT_NEG.search(line):
            seventh.append("%s:%d" % (name, i))


def scan_foreign_table_names(targets):
    hits = []
    for name, text in targets:
        for match in SQL_TABLE_REF_PAT.finditer(text):
            table = match.group(1)
            if table not in SIX_TABLE_NAMES:
                line = text.count("\n", 0, match.start()) + 1
                hits.append("%s:%d:%s" % (name, line, table))
    return hits


table_hits = scan_foreign_table_names(aa_targets)
table_ctrl = bool(scan_foreign_table_names([("CTRL", "SELECT * FROM secret_table;")]))
chk(not ddl_hits and ddl_ctrl and not seventh and not table_hits and table_ctrl
    and "六张表" in t19,
    "AA2 不产出 DDL、不新增第七张表、SQL 表名引用都在六张表白名单内；"
    "《19》写明六张表恒为六张（DDL 与越界表名两类正对照都必须命中）",
    "DDL 命中 %d 个文件%s；第七张表表述 %d 处；越界表名 %d 处%s；"
    "六张表白名单=%s；正对照 DDL=%s、表名=%s；《19》含六张表=%s"
    % (len(ddl_hits), "：" + br(ddl_hits) if ddl_hits else "", len(seventh),
       len(table_hits), "：" + br(table_hits) if table_hits else "",
       "、".join(sorted(SIX_TABLE_NAMES)), ddl_ctrl, table_ctrl,
       "六张表" in t19))
MODEL_SCAN_EXEMPT = {
    "代码/检索/build_questions.py": "题集构造与第三方复核登记",
    "代码/检索/config.py": "唯一参数来源；仅含硬守卫凭据名正则，不含答案生成模型型号",
    "代码/检索/third_party_review.py": "第三方复核执行脚本",
    "阶段07-RAG检索系统/预实验问题集/第三方复核报告.md": "第三方复核报告",
    "阶段07-RAG检索系统/预实验问题集/第三方复核台账.json": "第三方复核台账",
    "阶段07-RAG检索系统/预实验问题集/收口报告（千帆剥离与T8重绑）.md": "第三方复核留痕",
}
model_targets = [(n, t) for n, t in aa_targets if n not in MODEL_SCAN_EXEMPT]
model_hits = []
for name, text in model_targets:
    for i, line in enumerate(text.split("\n"), 1):
        if ANSWER_MODEL_PAT.search(line) and not any(m in line for m in MODEL_ALLOW_MARKS):
            model_hits.append("%s:%d" % (name, i))
model_ctrl = bool(ANSWER_MODEL_PAT.search("答案生成侧模型：" + "deep" + "seek-v9"))
chk(not model_hits and model_ctrl,
    "AA3 交付物不出现答案生成模型型号（第三方复核语境除外；正对照必须命中）",
    "未豁免命中 %d 处%s；正对照=%s；扫描范围 %d 个交付文本；显式排除 %d 个第三方"
    "复核文件（%s）"
    % (len(model_hits), "：" + br(model_hits) if model_hits else "", model_ctrl,
       len(model_targets), len(MODEL_SCAN_EXEMPT),
       "；".join("%s（%s）" % item for item in MODEL_SCAN_EXEMPT.items())))


# ==========================================================================
print()
print("=" * 78)
print("AB、《18》第八节 第 28 行：汇总与收口（`python 工具\\跨文档核验.py --strict-citations` "
      "与本脚本的退出码均为 0）")
print("=" * 78)
cross = subprocess.run([sys.executable, CROSS_DOC, "--strict-citations"], cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
cross_out = cross.stdout or ""
n2_line = next((l.strip() for l in cross_out.split("\n") if "扫描到依据声明" in l), "")
concl = next((l.strip() for l in cross_out.split("\n") if l.strip().startswith("结论")), "")
print("  跨文档核验输出（尾部）：")
for line in cross_out.strip().split("\n")[-6:]:
    print("    " + line)
chk(cross.returncode == 0, "AB1 跨文档核验（--strict-citations）退出码为 0",
    "实测 退出码=%d；%s；%s" % (cross.returncode, n2_line, concl))
R = ensure_replay()
if R.get("tmp"):
    removed = list(R.get("env_removed") or [])
    note("AB2 本脚本的只读证据（镜像根目录）",
         "镜像根目录 %s（文件 %d 个）；copied=%d、skipped=%d；工作区交付目录零写入；"
         "工作区指纹前后一致=%s%s；真实摘除凭据类变量 %d 个（%s）；"
         "MIRROR_OUTPUTS（%d 个：%s）删除后缺失态→运行后出现态全成立=%s"
         % (R["tmp"], R.get("mirror_files") or 0, R.get("copied") or 0,
            R.get("skipped") or 0,
            R.get("workspace_unchanged"),
            "" if not R.get("workspace_changed") else "（变化：%s）" % br(R.get("workspace_changed")),
            len(removed), "、".join(removed) if removed else "无",
            len(MIRROR_OUTPUTS), "、".join(MIRROR_OUTPUTS),
            all(row.get("absent_after_drop") and row.get("exists_after_run")
                for row in (R.get("freshness") or {}).values())))
else:
    if R.get("error_kind") == "environment_chain":
        envfail("AB2 本脚本的只读证据", R.get("error"))
    else:
        note("AB2 只读证据", "profile=%s：未建立镜像（%s）" % (ARGS.profile, R.get("error")))


def _result_group(label):
    match = re.match(r"^([A-Z]{1,2})\d", str(label))
    return match.group(1) if match else None


if ARGS.profile == "static":
    print("  [UNRUN] AB3 汇总不可判定：static 档有 %d 条内容检查未执行，"
          "不得宣称 28 组全部通过" % unrun_count)
    note("AB4 profile 声明",
         "--profile static 只做静态检查；未执行 %d 项，退出码 2，不作为收口判定依据"
         % unrun_count)
else:
    if env_fails:
        print("  [ENV ] 环境／链上失败（非内容失败）：AB3 汇总不参与内容判定")
    else:
        completed_before_summary = sum(1 for st, _l, _d in results if st in ("OK", "FAIL"))
        observed_groups = {_result_group(label) for st, label, _d in results
                           if st in ("OK", "FAIL")}
        observed_groups.discard(None)
        workspace_ok = bool(R.get("workspace_unchanged"))
        freshness_ok = bool(R.get("freshness")) and all(
            row.get("absent_after_drop") and row.get("exists_after_run")
            for row in R["freshness"].values())
        structure_ok = (observed_groups == set(EXPECTED_GROUP_ORDER)
                        and completed_before_summary == EXPECTED_CONTENT_CHECKS)
        chk(not fails and not env_fails and workspace_ok and freshness_ok and structure_ok,
            "AB3 本脚本 28 组检查全部通过（组结构与 %d 条内容检查计数同时成立；"
            "工作区零写入与产物新鲜度同时成立）" % EXPECTED_CONTENT_CHECKS,
            "实测 失败 %d 项、环境／链上失败 %d 项；组 %d／%d、内容检查 %d／%d；"
            "工作区透明=%s、产物新鲜=%s%s"
            % (len(fails), len(env_fails), len(observed_groups), len(EXPECTED_GROUP_ORDER),
               completed_before_summary, EXPECTED_CONTENT_CHECKS, workspace_ok, freshness_ok,
               "；失败：" + br(fails, limit=12) if fails else ""))

_SUMMARY_DONE = True
print()
executed = sum(1 for st, _l, _d in results if st in ("OK", "FAIL"))
passed = sum(1 for st, _l, _d in results if st == "OK")
skipped = sum(1 for st, _l, _d in results if st == "SKIP")
print("  最终：计划检查项 %d 项；已执行 %d、通过 %d、内容失败 %d、未执行 %d、SKIP %d；"
      "环境／链上失败 %d"
      % (EXPECTED_TOTAL_CHECKS, executed, passed, len(fails), unrun_count, skipped,
         len(env_fails)))
print("=" * 78)
if ARGS.profile == "static":
    print("结论：--profile static 未执行 %d 项（已列出上述 [UNRUN] 块），不得宣称全部通过；"
          "退出码 2。" % unrun_count)
    unrun_groups = {re.match(r"^([A-Z]{1,2})", lab).group(1)
                    for lab, _c, _d in unrun_evidence if re.match(r"^([A-Z]{1,2})", lab)}
    print("      静态档：28 组中仅 %d 组全部实际执行、其余 %d 组存在未执行项"
          "（未执行共 %d 个检查项）。"
          % (len(EXPECTED_GROUP_ORDER) - len(unrun_groups), len(unrun_groups), unrun_count))
    print("      提示：镜像内的 pre_experiment 是内存敏感步骤，高内存压力下会因 OpenBLAS 分配失败"
          "（Memory allocation still failed after 10 retries）非零退出——属已登记的环境脆弱性"
          "（《19》已知限制第 11 条），复跑验收时应避免与其他重型任务并发。")
elif env_fails:
    print("结论：环境／链上失败（非内容失败）%d 项，已中止相关镜像链；"
          "不能与真缺陷混判；退出码 1。" % len(env_fails))
    print("      提示：链上非零退出的最常见原因是**内存压力**——镜像内的 pre_experiment 在并发"
          "重型任务下会因 OpenBLAS 分配失败（Memory allocation still failed after 10 retries）"
          "非零退出；这属已登记的环境脆弱性（《19》已知限制第 11 条），不是检索链的逻辑缺陷，"
          "复跑时应避免并发。")
    for _lab, _det in env_fail_evidence:
        print("  - %s  %s" % (_lab, _det))
elif fails:
    print("结论：存在 %d 项内容失败（通过 %d 项、SKIP %d 项、未执行 %d 项）："
          % (len(fails), passed, skipped, unrun_count))
    for _lab, _det in fail_evidence:
        print("  - %s  %s" % (_lab, _det))
else:
    print("结论：全部通过（通过 %d 项／计划检查项 %d 项，未执行 0、SKIP 0）。"
          "第 7 阶段验收通过，退出码 0。" % (passed, EXPECTED_TOTAL_CHECKS))
print("=" * 78)

if REPLAY.get("tmp") and not ARGS.keep_tmp:
    shutil.rmtree(REPLAY["tmp"], ignore_errors=True)
elif REPLAY.get("tmp"):
    print("镜像重跑目录保留在：%s" % REPLAY["tmp"])
if ARGS.profile == "static":
    sys.exit(2)
sys.exit(1 if (fails or env_fails) else 0)
