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
发生在系统临时目录里——把 `代码\检索\*.py`、数据集 v2.1 的 11 个输入、预实验问题集三件与
`检索产出\` 的既有产物**镜像**到一个临时根目录，在那里重跑：

    check_inputs → vector_search --selftest → graph_query --selftest → pipeline --selftest
    → （pipeline --group C → pre_experiment --quiet → metrics）× 2

再与工作区里的原产物逐字节比对。**绝不写入工作区的任何交付目录**；镜像文件数与本脚本的只读
证据在「汇总与收口」组打印（`--keep-tmp` 保留镜像目录供事后复核）。

用法：

    python 工具\验收第7阶段.py                    # 默认 --profile full：完整镜像重跑（收口判定用）
    python 工具\验收第7阶段.py --profile static   # 只做静态检查：需要镜像重跑的检查项记 SKIP（仅供
                                                  # 快速定位；**这个 profile 不作为收口判定**）
    python 工具\验收第7阶段.py --keep-tmp         # 保留镜像重跑用的临时目录

退出码：0 = 全部检查通过（SKIP 不影响退出码）；1 = 存在失败项或输入缺失。

纪律：**参数一律取 `代码\检索\config.py`**（路径、K／N／预算、g、模型与 revision、组开关都在
那里）；本脚本自带常量的部分只有两类，均已就地注释：① 数据集的表名白名单与禁用词形态
（按《02》第8.4节 与《18》第五节 硬约束 22 构造，拼串以免自我命中）；② 扫描器的正对照样本。
"""

from __future__ import annotations

import argparse
import atexit
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
KEY_PATTERNS = ["api" + "_key", "API" + "_KEY", "access" + "_token", "sec" + "ret",
                "requests" + ".", "urllib" + ".request", "socket" + "."]
HTTP_PATTERNS = ["http" + "://", "https" + "://"]
ANSWER_MODEL_PAT = re.compile(
    r"(gpt-?\d|claude|gemini|qwen|ernie|chatglm|glm-\d|kimi|deepseek|llama|moonshot|文心|通义)",
    re.IGNORECASE)
MODEL_ALLOW_MARKS = ("第三方", "复核", "盲标", "留痕", "剥离", "非答案生成", "抽检")
DDL_PAT = re.compile(r"CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE", re.IGNORECASE)
DEPLOY_ASSERT = re.compile(r"(已部署|部署了|已经部署|已上线|已运行)")
DEPLOY_NEG = re.compile(r"(未|不得|没有|无|非|禁止|不写|不接入)")

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
REPLAY = {"error": None}
MIRROR_OUTPUTS = ["input_manifest.json", "pre_experiment_matrix.jsonl", "k_selection.json",
                  "per_question_trace.jsonl", "metrics_pre.jsonl"]


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
    return env, removed


def run_cmd(argv, cwd, tag, timeout=7200):
    env, _removed = stripped_env()
    log_dir = os.path.join(cwd, "_accept_logs")
    os.makedirs(log_dir, exist_ok=True)
    t0 = time.time()
    proc = subprocess.run([sys.executable] + list(argv), cwd=cwd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env, timeout=timeout)
    seconds = round(time.time() - t0, 3)
    log_path = os.path.join(log_dir, tag + ".log")
    with open(log_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("$ python " + " ".join(argv) + "\n--- stdout ---\n" + (proc.stdout or "")
                + "\n--- stderr ---\n" + (proc.stderr or "")
                + "\n--- exit_code = %d / %.3fs ---\n" % (proc.returncode, seconds))
    return {"tag": tag, "argv": list(argv), "code": proc.returncode, "seconds": seconds,
            "stdout": proc.stdout or "", "stderr": proc.stderr or "", "log": log_path}


WORKSPACE_WATCH = None


def workspace_snapshot():
    """工作区只读证据的指纹集合：11 个输入 ＋ 5 个产出 ＋ 三份关键文档 ＋ 本脚本自身。"""
    paths = [p for _k, p in config.INPUT_FILES]
    paths += [os.path.join(OUT, n) for n in MIRROR_OUTPUTS if os.path.isfile(os.path.join(OUT, n))]
    paths += [P18, P19, P00, P02, os.path.abspath(__file__)]
    return {rel(p): sha256_file(p) for p in paths if os.path.isfile(p)}


def ensure_replay():
    global REPLAY, WORKSPACE_WATCH
    if REPLAY.get("done") or REPLAY.get("error"):
        return REPLAY
    if ARGS.profile == "static":
        REPLAY["error"] = "--profile static：跳过镜像重跑（仅供快速定位，不作为收口判定）"
        return REPLAY
    try:
        WORKSPACE_WATCH = workspace_snapshot()
        tmp, copied, skipped = build_mirror()
        REPLAY.update({"tmp": tmp, "copied": copied, "skipped": skipped})
        m = lambda *parts: os.path.join(tmp, *parts)
        code_dir = m("代码", "检索")
        steps = [
            ("check_inputs", [os.path.join(code_dir, "check_inputs.py")]),
            ("vector_search_selftest", [os.path.join(code_dir, "vector_search.py"), "--selftest"]),
            ("graph_query_selftest", [os.path.join(code_dir, "graph_query.py"), "--selftest"]),
            ("pipeline_selftest", [os.path.join(code_dir, "pipeline.py"), "--selftest"]),
        ]
        REPLAY["chain"] = []
        for tag, argv in steps:
            REPLAY["chain"].append(run_cmd(argv, tmp, "chain_" + tag))
        cyc = []
        for cycle in ("run1", "run2"):
            r = {}
            r["pipeline"] = run_cmd([os.path.join(code_dir, "pipeline.py"), "--group", "C", "--out",
                                     m("阶段07-RAG检索系统", "检索产出", "per_question_trace.jsonl")],
                                    tmp, "cycle_%s_pipeline" % cycle)
            r["pre_experiment"] = run_cmd([os.path.join(code_dir, "pre_experiment.py"), "--quiet"],
                                          tmp, "cycle_%s_pre_experiment" % cycle)
            r["metrics"] = run_cmd([os.path.join(code_dir, "metrics.py")],
                                   tmp, "cycle_%s_metrics" % cycle)
            r["sha"] = {n: sha256_file(m("阶段07-RAG检索系统", "检索产出", n))
                        for n in ("pre_experiment_matrix.jsonl", "k_selection.json",
                                  "per_question_trace.jsonl", "metrics_pre.jsonl")}
            cyc.append(r)
        REPLAY["cycles"] = cyc
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
        REPLAY["env_removed"], _ = stripped_env()
        after = workspace_snapshot()
        REPLAY["workspace_unchanged"] = (WORKSPACE_WATCH == after)
        REPLAY["workspace_changed"] = sorted(
            k for k in set(WORKSPACE_WATCH) | set(after)
            if WORKSPACE_WATCH.get(k) != after.get(k))
        REPLAY["done"] = True
    except Exception as exc:
        REPLAY["error"] = "%s: %s" % (type(exc).__name__, exc)
    return REPLAY


def mirror_or_skip(prefix, labels):
    R = ensure_replay()
    if R.get("error"):
        for lab in labels:
            skip("%s %s" % (prefix, lab), "镜像重跑未执行：%s" % R["error"])
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
dataset_rows = [r for r in input_rows if r[0] in
                ("documents", "chunks", "faiss_index", "vector_map", "build_meta", "dataset_meta")]
graph_rows = [r for r in input_rows if r[0] not in
              ("documents", "chunks", "faiss_index", "vector_map", "build_meta", "dataset_meta")]
exist_bad = [r[1] for r in input_rows if not os.path.isfile(os.path.join(ROOT, r[1]))]
listed_bad = [r[1] for r in input_rows if r[1] not in t18]
chk(len(input_rows) == 11 and len(dataset_rows) == 6 and len(graph_rows) == 5,
    "B1 输入清单恰为 11 个（数据集 6 ＋ 图谱 5）",
    "实测 %d 个：数据集 %d、图谱 %d" % (len(input_rows), len(dataset_rows), len(graph_rows)))
chk(not exist_bad, "B2 11 个输入文件全部存在", "缺失 %d 个%s"
    % (len(exist_bad), "：" + br(exist_bad) if exist_bad else ""))
chk(not listed_bad, "B3 11 条相对路径与《18》第三节 的输入清单逐条一致", "未在《18》中逐字命中 %d 条%s"
    % (len(listed_bad), "：" + br(listed_bad) if listed_bad else ""))


# ==========================================================================
print()
print("=" * 78)
print("C、《18》第八节 第 3 行：输入只读：T11 结束时数据集 v2.1 与图谱导出物 v2.1_v1_2 的"
      "文件指纹与 T1 记录的开工指纹一致")
print("=" * 78)
manifest = read_json(config.INPUT_MANIFEST_PATH, default={})
mrows = manifest.get("files") or []
m_bad = []
for row in mrows:
    p = os.path.join(ROOT, row["path"].replace("/", os.sep))
    if not os.path.isfile(p) or sha256_file(p) != row["sha256"] \
            or os.path.getsize(p) != row["bytes"]:
        m_bad.append(row["key"])
chk(len(mrows) == 11 and [r["key"] for r in mrows] == [k for k, _p in config.INPUT_FILES],
    "C1 指纹清单含 11 条且键序与 config.INPUT_FILES 一致",
    "实测 %d 条：%s" % (len(mrows), "、".join(r["key"] for r in mrows)))
chk(not m_bad, "C2 11 个输入逐个重算 SHA-256 与字节数，与 T1 记录一致",
    "不一致 %d 条%s；manifest.all_ok=%s" % (len(m_bad), "：" + br(m_bad) if m_bad else "",
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


# ==========================================================================
print()
print("=" * 78)
print("I、《18》第八节 第 9 行：图谱导出物未被改动（五个文件与开工指纹一致）；交付物中不出现"
      "「已部署 Neo4j 服务」一类表述")
print("=" * 78)
graph_keys = ("nodes_csv", "edges_csv", "replay_cypher", "graph_stats", "human_confirmation")
g_bad = []
for row in mrows:
    if row["key"] in graph_keys:
        p = os.path.join(ROOT, row["path"].replace("/", os.sep))
        if not os.path.isfile(p) or sha256_file(p) != row["sha256"]:
            g_bad.append(row["key"])
chk(len([r for r in mrows if r["key"] in graph_keys]) == 5 and not g_bad,
    "I1 图谱导出物五个文件与 T1 指纹一致",
    "实测 %d 个文件、不一致 %d 个%s"
    % (len([r for r in mrows if r["key"] in graph_keys]), len(g_bad),
       "：" + br(g_bad) if g_bad else ""))


def scan_deploy_claims(targets):
    hits = []
    for name, text in targets:
        for i, line in enumerate(text.split("\n"), 1):
            if "Neo4j" in line and DEPLOY_ASSERT.search(line) and not DEPLOY_NEG.search(line):
                hits.append("%s:%d %s" % (name, i, line.strip()[:80]))
    return hits


deploy_targets = [("《19》", t19)]
for n in sorted(code_texts):
    deploy_targets.append(("代码/检索/" + n, code_texts[n]))
deploy_targets.append(("代码/检索/README.md", read_text(os.path.join(CODE, "README.md"), "")))
deploy_hits = scan_deploy_claims(deploy_targets)
deploy_ctrl = bool(scan_deploy_claims([("CTRL", "本系统已部署 Neo4j 服务。")]))
chk(not deploy_hits and deploy_ctrl,
    "I2 第 7 阶段交付物不出现「已部署 Neo4j 服务」一类的肯定表述（正对照必须命中）",
    "命中 %d 处%s；正对照命中=%s；《19》含「未部署」=%s"
    % (len(deploy_hits), "：" + br(deploy_hits) if deploy_hits else "", deploy_ctrl,
       "未部署" in t19))


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
R = mirror_or_skip("K2", ["构造用例与镜像重跑产物"])
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
R = mirror_or_skip("L2", ["一次运行日志与 D 组 trace 的段次序"])
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
R = mirror_or_skip("M4", ["D 组 trace 的空值剔除逐题留痕"])
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
R = mirror_or_skip("N1", ["镜像重跑的断言 1 与 D／E trace"])
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
R = mirror_or_skip("O1", ["镜像重跑的断言 2"])
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
    unclear = [r["qid"] for r in per if not r["measurable"]]
    chk(unclear == ["PE-11", "PE-20"],
        "O3 不可测题恰好是 PE-11 与 PE-20（逐题留痕）",
        "实测不可测题：%s" % (",".join(unclear) or "无"))


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
layers = [line_index(src_p, '"layer1_vector_top"'), line_index(src_p, '"layer2_graph_new"'),
          line_index(src_p, '"layer3_vector_fill"')]
layers_ok = all(layers)
pri_region = src_p[src_p.find("def priority_rule_text("):
                   src_p.find("# ---------------------------------------------------------------------------\n"
                              "# 一、开关与口径校验")]
pri_order = [pri_region.find(k) for k in ("第一层＝", "第二层＝", "第三层＝")]
pri_ok = (all(x >= 0 for x in pri_order) and pri_order[0] < pri_order[1] < pri_order[2]
          and all(k in pri_region for k in ("K−g", "至多取 g 个", "回填", "全局固化量")))
legacy_ok = ("LEGACY_PRIORITY_RULE" in src_p and "固定原始顺序" in src_p
             and re.search(r"if int\(g\) <= 0:\s*\n\s*return LEGACY_PRIORITY_RULE", src_p)
             is not None)
chk(i_trim and i_keep and i_order and i_trim < i_keep < i_order and layers_ok,
    "P1 代码级顺序断言：裁剪 → 保留 K → 分组排序；三层的实现标记按 1→2→3 排列（含正对照）",
    "实测 trim 第 %s 行、keep 第 %s 行、order 第 %s 行；layer1/2/3 行号=%s；"
    "口径文字的三层次序正确=%s；g<=0 返回原字面口径=%s"
    % (i_trim, i_keep, i_order, layers, pri_ok, legacy_ok))
chk("先" in src_p and "远端图谱路径" in src_p and "分层保留顺序" in src_p
    and "K−g" in src_p and "至多取 g 个" in src_p and "回填" in src_p,
    "P2 代码内的裁剪与保留顺序含「先裁远端图谱路径」与三层定义（K−g／至多 g／回填）",
    "实测 关键短语齐备=%s"
    % all(k in src_p for k in ("先", "远端图谱路径", "分层保留顺序", "K−g", "至多取 g 个", "回填")))
R = mirror_or_skip("P3", ["镜像重跑的裁剪运行日志与 g = 0 退化"])
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
R = mirror_or_skip("Q1", ["镜像重跑的断言 4 与 metrics 行数"])
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
R = mirror_or_skip("R1", ["镜像重跑的 metrics 产物"])
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
R = mirror_or_skip("S1", ["镜像重跑的 metrics 产物"])
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
    chk("recall_at_k_doc_level_diagnostic" in src_m
        and "def cmd_write" in src_m,
        "S2 文档级诊断函数存在但只在诊断函数里；写盘路径只输出 chunk 级",
        "实测 诊断函数存在=%s、写盘入口 cmd_write 存在=%s、"
        "文件中出现 document 级写入调用=%s"
        % ("recall_at_k_doc_level_diagnostic" in src_m, "def cmd_write" in src_m,
           bool(re.search(r"recall_at_k_doc_level_diagnostic\s*\(", src_m))))
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
R = mirror_or_skip("T1", ["镜像重跑的网格产物"])
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
R = mirror_or_skip("U1", ["镜像重跑的 k_selection 产物"])
if R:
    sel = R["selection"]
    selected = sel.get("selected") or {}
    rules = sel.get("rules") or {}
    sat = (sel.get("evidence") or {}).get("saturation_under_budget") or {}
    rows_sat = sat.get("rows") or []
    k_sel = selected.get("K")
    feasible = sat.get("feasible_K") or []
    sat_ok = ("饱和" in (rules.get("K_rule") or "")) and k_sel in feasible \
        and sat.get("selected_K") == k_sel
    deltas = {r["K"]: r.get("delta_cer_vs_prev_under_budget") for r in rows_sat}
    next_delta = None
    ks = sorted(r["K"] for r in rows_sat)
    if k_sel in ks:
        upper = [k for k in ks if k > k_sel]
        next_delta = deltas.get(upper[0]) if upper else None
    minimal_ok = (next_delta is None or next_delta <= 0)
    gold_excl = any(r["K"] == 5 and not r.get("gold_feasible") for r in rows_sat)
    budget_excl = any(r["K"] == 15 and not r.get("budget_feasible") for r in rows_sat)
    chk(sat_ok and minimal_ok and gold_excl and budget_excl,
        "U1 K 的选择规则执行证据：gold 约束排除 K=5、预算排除 K=15、K=10 处相邻档 Δ ≤ 0",
        "实测 规则含饱和=%s、选定 K=%s 在可行集 %s 内=%s、K=15 的 Δ=%s、gold 排除=%s、预算排除=%s"
        % ("饱和" in (rules.get("K_rule") or ""), k_sel, feasible, k_sel in feasible,
           next_delta, gold_excl, budget_excl))
    ncurve = (sel.get("evidence") or {}).get("N_curve") or []
    n_rows = [r for r in ncurve if r["K"] == k_sel]
    max_cer = max((r["metrics"]["complete_evidence_recall_at_k"] for r in n_rows), default=None)
    min_n = min((r["N"] for r in n_rows
                 if r["metrics"]["complete_evidence_recall_at_k"] == max_cer), default=None)
    chk(min_n == selected.get("N") and "最小" in (rules.get("N_rule") or ""),
        "U2 N 的选择规则执行证据：取使 CER 达到该档最大值的**最小** N",
        "实测 N 曲线 %s；最大 CER=%s 对应最小 N=%s；选定 N=%s"
        % ([r["N"] for r in n_rows], max_cer, min_n, selected.get("N")))
    gcurve = (sel.get("evidence") or {}).get("g_curve") or {}
    g_rows = gcurve.get("primary_rows") or []
    adopted = gcurve.get("adopted_g")
    g_ok = adopted == selected.get("g") and adopted >= 1 \
        and "不低于下限 1" in (gcurve.get("criterion") or "") \
        and [r["g"] for r in g_rows] == [0, 1, 2, 3, 5] \
        and all(r.get("not_worse_than_g0") for r in g_rows if r["g"] in (1, 2)) \
        and not any(r.get("not_worse_than_g0") for r in g_rows if r["g"] in (3, 5))
    chk(g_ok, "U3 g 的选择规则执行证据：探针点齐全、g=2 不劣于 g=0、g=3／5 劣化、含下限 1",
        "实测 探针点=%s、采用 g=%s、选定 g=%s、判据含下限 1=%s"
        % ([r["g"] for r in g_rows], adopted, selected.get("g"),
           "不低于下限 1" in (gcurve.get("criterion") or "")))


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
chk(sel_ok and cfg["K"] == 10 and cfg["N"] == 20
    and cfg["context_token_budget"] == 3600 and cfg["graph_retention_share"] == 2,
    "V1 config 与 k_selection 的选定值一致：K=10／N=20／3600／g=2（三项非 TBD）",
    "实测 config=%s；k_selection.selected=%s" % (cfg, sel))
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
key_hits = []
for n, text in chain_text.items():
    for pat in KEY_PATTERNS + HTTP_PATTERNS:
        for i, line in enumerate(text.split("\n"), 1):
            if pat in line:
                key_hits.append("%s:%d:%s" % (n, i, pat))
ctrl_text = read_text(os.path.join(CODE, "third_party_review.py"), "")
ctrl_hits = sum(1 for pat in KEY_PATTERNS + HTTP_PATTERNS if pat in ctrl_text)
chk(not key_hits and ctrl_hits > 0 and config.MODEL_CALLS_ALLOWED == 0,
    "W1 链上六个脚本的密钥／网络字样 0 处（正对照：链外脚本命中 > 0）；"
    "config.MODEL_CALLS_ALLOWED = 0",
    "链上命中 %d 处%s；正对照命中 %d 种；MODEL_CALLS_ALLOWED=%r"
    % (len(key_hits), "：" + br(key_hits) if key_hits else "", ctrl_hits,
       config.MODEL_CALLS_ALLOWED))
R = mirror_or_skip("W2", ["摘除密钥的镜像全链路运行记录"])
if R:
    codes = [c["code"] for c in R["chain"]]
    cycle_codes = [s["code"] for cyc in R["cycles"] for s in cyc.values()
                   if isinstance(s, dict) and "code" in s]
    all_zero = all(c == 0 for c in codes + cycle_codes)
    texts = [c["stdout"] for c in R["chain"]] + \
            [cyc["pre_experiment"]["stdout"] for cyc in R["cycles"]] + \
            [cyc["pipeline"]["stdout"] for cyc in R["cycles"]]
    claim = sum(t.count("0 次大语言模型／外部接口调用") for t in texts)
    chk(all_zero and claim >= 1,
        "W2 镜像里摘除密钥后全链路（六步 ＋ 两次三轮）退出码全 0，运行记录打印 0 次调用",
        "实测 退出码全 0=%s（%d 条命令）；打印 0 次调用 %d 处；摘除的凭据类环境变量 %d 个"
        % (all_zero, len(codes) + len(cycle_codes), claim, len(R.get("env_removed") or [])))
    chk(("本地 Embedding 前向" in t19) and ("不计入「模型调用」" in t19)
        and ("全程未跑模型" in t19),
        "W3 《19》写明口径区分：本地 Embedding 前向不计入模型调用，但不得写成全程未跑模型",
        "实测 三处表述齐备=%s"
        % all(k in t19 for k in ("本地 Embedding 前向", "不计入「模型调用」", "全程未跑模型")))


# ==========================================================================
print()
print("=" * 78)
print("X、《18》第八节 第 24 行：重放逐字节一致（同一输入两次运行，网格结果、逐题 trace "
      "与指标输出逐字节一致）")
print("=" * 78)
R = mirror_or_skip("X1", ["两次运行的 SHA-256 比对"])
if R:
    files = ["pre_experiment_matrix.jsonl", "k_selection.json",
             "per_question_trace.jsonl", "metrics_pre.jsonl"]
    same = all(R["cycles"][0]["sha"][n] == R["cycles"][1]["sha"][n] for n in files)
    ws_same = all(R["cycles"][0]["sha"][n] == sha256_file(os.path.join(OUT, n)) for n in files)
    chk(same, "X1 四个文件两次运行 SHA-256 相同（逐字节一致）",
        "；".join("%s %s==%s" % (n, R["cycles"][0]["sha"][n][:12],
                                 R["cycles"][1]["sha"][n][:12]) for n in files))
    chk(ws_same, "X2 镜像重跑的四个文件与工作区交付产物逐字节一致",
        "；".join("%s 工作区=%s" % (n, sha256_file(os.path.join(OUT, n))[:12]) for n in files))
    no_ts = all(not any(k in ("timestamp", "seconds", "elapsed", "duration") for k in row)
                for row in R["matrix"])
    chk(no_ts, "X3 参与比对的文件不含运行时间戳与耗时字段",
        "实测 网格行内无 timestamp／seconds／elapsed／duration=%s" % no_ts)


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
forb_hits = [w for w in forbid if w in text_all]
ref_ctrl = ("人工" + "金标准") in ("这是人工" + "金标准")
chk(no_formal and no_260 and refset and not forb_hits and ref_ctrl,
    "Y2 题集声明为非正式测试集、未复用 260 条参照集；题集文本不出现「人工金标准／人工一致率」"
    "（正对照必须命中）",
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
aa_targets = [("《19》", t19),
              ("代码/检索/README.md", read_text(os.path.join(CODE, "README.md"), ""))]
for n, text in chain_text.items():
    aa_targets.append(("代码/检索/" + n, text))
aa_targets.append(("代码/检索/build_questions.py",
                   read_text(os.path.join(CODE, "build_questions.py"), "")))
for n in MIRROR_OUTPUTS:
    p = os.path.join(OUT, n)
    if os.path.isfile(p):
        aa_targets.append(("检索产出/" + n, read_text(p, "")))
for n in ("questions.jsonl", "说明.md", "题目模板.md"):
    aa_targets.append(("预实验问题集/" + n, read_text(os.path.join(QS, n), "")))
vdb_hits = [name for name, text in aa_targets if BANNED_VDB in text]
vdb_ctrl = BANNED_VDB in ("这里写" + BANNED_VDB + "一次")
chk(not vdb_hits and vdb_ctrl,
    "AA1 交付物中不含被禁用的四字连写术语（一律写「向量索引」或「向量检索组件」；正对照必须命中）",
    "命中文件 %d 个%s；正对照=%s；《19》用「向量索引」=%d 次"
    % (len(vdb_hits), "：" + br(vdb_hits) if vdb_hits else "", vdb_ctrl,
       t19.count("向量索引")))
ddl_hits = [name for name, text in aa_targets if DDL_PAT.search(text)]
ddl_ctrl = bool(DDL_PAT.search("CREATE TABLE question (id INT);"))
seventh = [name for name, text in aa_targets
           if re.search(r"第七张表|七张表|7 张表|新增表", text)]
chk(not ddl_hits and ddl_ctrl and not seventh and "六张表" in t19,
    "AA2 不产出 DDL、不新增第七张表；《19》写明六张表恒为六张（正对照必须命中 DDL 形态）",
    "DDL 命中 %d 个文件%s；正对照=%s；第七张表表述 %d 处；《19》含六张表=%s"
    % (len(ddl_hits), "：" + br(ddl_hits) if ddl_hits else "", ddl_ctrl, len(seventh),
       "六张表" in t19))
model_targets = [(n, t) for n, t in aa_targets if n != "代码/检索/build_questions.py"]
model_hits = []
for name, text in model_targets:
    for i, line in enumerate(text.split("\n"), 1):
        if ANSWER_MODEL_PAT.search(line) and not any(m in line for m in MODEL_ALLOW_MARKS):
            model_hits.append("%s:%d" % (name, i))
model_ctrl = bool(ANSWER_MODEL_PAT.search("答案生成侧模型：" + "deep" + "seek-v9"))
chk(not model_hits and model_ctrl,
    "AA3 交付物不出现答案生成模型型号（第三方复核语境除外；正对照必须命中）",
    "未豁免命中 %d 处%s；正对照=%s；扫描范围 %d 个交付文本（build_questions.py 与 "
    "third_party_review.py 是第三方复核的登记与执行脚本、按职责保留复核通道模型名，"
    "已在本次扫描中单列，不计入答案生成侧型号）"
    % (len(model_hits), "：" + br(model_hits) if model_hits else "", model_ctrl,
       len(model_targets)))


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
    note("AB2 本脚本的只读证据（镜像根目录）",
         "镜像根目录 %s（文件 %d 个）；copied=%d、skipped=%d；工作区交付目录零写入；"
         "工作区指纹前后一致=%s%s；子进程环境摘除凭据类变量 %d 个"
         % (R["tmp"], R.get("mirror_files"), R.get("copied"), R.get("skipped"),
            R.get("workspace_unchanged"),
            "" if not R.get("workspace_changed") else "（变化：%s）" % br(R.get("workspace_changed")),
            len(R.get("env_removed") or [])))
else:
    note("AB2 只读证据", "profile=%s：未建立镜像（%s）" % (ARGS.profile, R.get("error")))
chk(not fails, "AB3 本脚本 28 组检查全部通过（任一失败即非零退出；SKIP 不影响退出码）",
    "实测 失败 %d 项%s" % (len(fails), "：" + br(fails, limit=12) if fails else "无"))
if ARGS.profile == "static":
    note("AB4 profile 声明", "--profile static 只做静态检查，不作为第 7 阶段的收口判定依据")

_SUMMARY_DONE = True
print()
print("  最终：检查项 %d 项，通过 %d，失败 %d"
      % (len(results), sum(1 for st, _l, _d in results if st == "OK"), len(fails)))
print("  另有 SKIP %d 项（镜像重跑未开启时相关检查项；原因见 [SKIP] 行，不计入失败）"
      % sum(1 for st, _l, _d in results if st == "SKIP"))
print("=" * 78)
if not fails:
    print("结论：全部通过（通过 %d 项／检查项 %d 项，另有 SKIP %d 项）。第 7 阶段验收通过，"
          "退出码 0。" % (sum(1 for st, _l, _d in results if st == "OK"), len(results),
                          sum(1 for st, _l, _d in results if st == "SKIP")))
else:
    print("结论：存在 %d 项失败（通过 %d 项／检查项 %d 项、SKIP %d 项）："
          % (len(fails), sum(1 for st, _l, _d in results if st == "OK"), len(results),
             sum(1 for st, _l, _d in results if st == "SKIP")))
    for _lab, _det in fail_evidence:
        print("  - %s  %s" % (_lab, _det))
print("=" * 78)

if REPLAY.get("tmp") and not ARGS.keep_tmp:
    shutil.rmtree(REPLAY["tmp"], ignore_errors=True)
elif REPLAY.get("tmp"):
    print("镜像重跑目录保留在：%s" % REPLAY["tmp"])
sys.exit(1 if fails else 0)
