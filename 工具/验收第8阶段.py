#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""《21-第8阶段任务书（智能问答系统）》第八节 39 行验收标准的**阶段级专项门禁**（T10）。

**行数与编号**：《21》第八节 的表格共 **39 行**（分组 A 4 ＋ B 4 ＋ C 6 ＋ D 6 ＋ E 5 ＋
F 4 ＋ G 6 ＋ H 4；v1.5 计数更正）。本脚本逐行落地这 39 行：**行 → 检查组的映射直接写在
每组标题里**（例如「A、《21》第八节 A 组（第 1～4 行：A1 …）」），逐行 1:1、行序与表格一致。
full 档必须能读出 39／39。

**不采信被验收对象的自检**：`代码\问答\*.py --selftest` 的结论一律不作为验收依据。本脚本
从**输入文件、代码源码、装配层现场重算、产出文件原文**四条线独立推导后再比对；唯一引用
被验对象产物的地方是「读它的产出文件」本身（`answer_trace.jsonl`／`qa_records.jsonl`／
`run_manifest.json`／`prompt_snapshot.json`），且一律**现场重算关键量**（引用编号／日期来源／
禁词／图谱三方／字段名／指纹）而不是读它登记的结论。

**零模型调用**：《21》第五节 硬约束 18。本脚本**不发任何大模型请求**：所有检查都在
「重算装配 ＋ 读产物 ＋ 跑 0 调用命令行」范围内。唯一用到的两条子进程分别是
`run_answer.py --dry-run`（在 `STAGE8_FORBID_MODEL_CALLS=1` 哨兵下，自报调用计数必须为 0）
与 `工具\跨文档核验.py --strict-citations`（G5），两者都不调用模型。

**只读纪律**：本脚本对工作区只读，**不写入任何交付目录**。需要写盘的只有临时文件（系统临时
目录），`--keep-tmp` 可保留镜像根供事后复核。`--selftest` 的镜像根也建在系统临时目录里。

用法：

    python 工具\验收第8阶段.py                    # 默认 --profile full：39 行全执行（收口判定用）
    python 工具\验收第8阶段.py --profile static   # 只做静态检查：需要子进程／重算装配的检查项记
                                                  # 未执行（**这个档不作为收口判定**，退出码 2）
    python 工具\验收第8阶段.py --selftest         # 负向校准：原样副本 ＋ 5 个反例（见 --help）
    python 工具\验收第8阶段.py --root PATH        # 对镜像根／被篡改副本运行（默认＝仓库根）
    python 工具\验收第8阶段.py --keep-tmp         # 保留临时目录

退出码：0 = full 档 39 行全部通过；1 = 存在失败项或环境／链上失败；2 = `--profile static`
（存在未执行项）或 `--selftest` 的对照结论不成立。

**脚本自带常量的说明**：验收判据、冻结值、字段清单、区块标题、映射表等一律**现场从被判文档
读出来**（《21》第五节、《02》第12.4节、《10》表 4-6 与表 4-12、《19》第 8 节）。脚本内只保留
三类常量，均就地注明出处：① 期望行数与分组（《21》第八节 表头）；② 检索侧四项定值的期望值
（《21》第五节 硬约束 1，用于反过来核对 `代码\检索\config.py` 是否被改动）；③ 表格行标签
（用于在原文里定位表格行）。
"""

from __future__ import annotations

import argparse
import ast
import atexit
import hashlib
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

SCRIPT = os.path.abspath(__file__)
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT))

# ---------------------------------------------------------------------------
# 期望结构（《21》第八节 表头与 v1.5 计数更正），用于「计数自洽」自证。
# ---------------------------------------------------------------------------
EXPECTED_ROW_GROUPS = {"A": 4, "B": 4, "C": 6, "D": 6, "E": 5, "F": 4, "G": 6, "H": 4}
EXPECTED_TOTAL_ROWS = 39
# static 档未执行的行：需要子进程（A3／G1／G5）或需要重算装配（C2／C3／C4／C6／G2），
# 以及只能在 full 档判定的 G6。
STATIC_UNRUN_ROWS = ("A3", "C2", "C3", "C4", "C6", "G1", "G2", "G5", "G6")

# 检索侧四项定值的期望值（《21》第五节 硬约束 1 与《02》第12.4节）：用于**反向核对**
# `代码\检索\config.py` 未被改动，不作为答案侧参数的兜底。
EXPECT_FIXED = {"K": 10, "N": 20, "context_token_budget": 3600,
                "graph_retention_share": 2}

# 答案侧冻结值（《21》第五节 硬约束 2 与第2.4节 作者裁定）。运行时优先从《21》原文解析，
# 解析不到才退回这组常量（并在输出里注明退回了）。
FROZEN_ANSWER_FALLBACK = {
    "model_name": "deepseek-flash",
    "model_version": "deepseek-flash",
    "temperature": 0,
    "endpoint": "https://api.deepseek.com/v1",
    "max_tokens": 16384,
    "prompt_version": "v1.0",
}

# 七区块标题（《10》第4.6.8节 表 4-12）：运行时从《10》原文解析，这里只留解析不成功时的
# 行标签白名单，用于定位表格行。
BLOCK_TABLE_LABELS = ("1", "2", "3", "4", "5", "6", "7")

# 记录层字段名（《21》第五节 硬约束 13 逐字列出；与《10》第4.4.1节 表 4-6 同源）。
# 运行时与 `代码\问答\history.py` 的三个字段元组逐项比对，两处都必须与下面一致。
# `question.user_id` 是表 4-6 的**可空外键**（`fk_question_user`，「登录未启用时为空」）——
# 《21》硬约束 13 的逐字列表漏了它，而表 4-6 为准绳，故 F1 的**必备字段集**含 `user_id`
# （全面审查 C-01；第一版不启用登录，值恒为 `null`）。
ROW13_FIELDS = {
    "question": ("question_id", "user_id", "session_id", "question_text", "task_type",
                 "gold_hop_depth", "time_constraint", "ask_time"),
    "answer": ("answer_id", "question_id", "answer_text", "graph_path", "model_name",
               "prompt_version", "is_graph_extended", "create_time"),
    "answer_evidence": ("answer_id", "chunk_id", "doc_id", "rank", "evidence_type"),
}

# `evidence_type` 的四类取值（《21》第五节 硬约束 15）＋ 由 **documents.jsonl 的 category**
# 推得来源类型的**写死映射**（《10》表 4-6／prompt 同源口径）。F1 用它**独立重算**每条证据的
# 期望来源类型，与 `qa_records.jsonl` 的登记值逐条比对——**不 import 被验对象的映射表**，否则
# 就成了「用实现验实现」（全面审查 B-03／C-05）。判据顺序与 `prompt.source_type_label` 一致：
# **图谱侧新增块优先**（`from_graph=true` → 相关事件），否则按 category 查表，missing／表外 → 回答来源。
EVIDENCE_TYPE_SET = ("回答来源", "新闻来源", "公告来源", "相关事件")
EVIDENCE_TYPE_BY_CATEGORY = {
    "公告": "公告来源",
    "政策文件": "公告来源",
    "监管公开信息": "公告来源",
    "财经新闻": "新闻来源",       # 键＝数据真实取值，不是近义词「新闻」
}
EVIDENCE_TYPE_DEFAULT = "回答来源"
EVIDENCE_TYPE_GRAPH = "相关事件"


def expected_evidence_type(category, from_graph) -> str:
    """由文档 category ＋ 是否图谱侧新增块**独立重算**期望来源类型（门禁内部写死）。"""
    if from_graph:
        return EVIDENCE_TYPE_GRAPH
    return EVIDENCE_TYPE_BY_CATEGORY.get(category, EVIDENCE_TYPE_DEFAULT)


def _question_number(value):
    """从 `Q-0nn` 或 `PE-nn` 里取题号整数（`Q-001`→1、`PE-01`→1）；取不到返回 None。

    用题号（而非字符串）做匹配，避免 `Q-001`↔`PE-01` 这种位宽不一致的假失配。
    """
    m = re.fullmatch(r"(?:Q|PE)-0*(\d+)", str(value or "").strip())
    return int(m.group(1)) if m else None

# 《22》的 9 个必备小节（《21》第 137 行 逐字给出）。括号内为注解，比对时只取括号前的
# 核心标题，并要求在《22》里以标题行形式**按序**出现。
DOC22_SECTIONS = (
    "答案生成口径与配置",
    "Prompt 模板 v1.0 的实现与区块结构",
    "证据 → Prompt 装配与预算分账",
    "生成链路与答案形态",
    "证据追溯与图谱路径",
    "记录层与历史问答",
    "三模型对照选型读数与裁定",
    "已知限制与证据不足清单",
    "对下游（第 9／10 阶段）的使用说明",
)

# 拼串构造：本文件源码内不出现被禁用的四字连写术语，也不出现任何敏感凭证字样。
BANNED_SPLIT = "向量" + "数据库"
TERM_FAISS_OK = "向量索引"
DDL_PAT = re.compile(r"CREATE\s+TABLE|ALTER\s+TABLE|DROP\s+TABLE", re.IGNORECASE)
DB_CONN_PAT = re.compile(
    r"(pymysql|mysql\.connector|MySQLdb|sqlalchemy|jdbc:|mysql://|"
    r"host\s*=\s*[\"'](?:localhost|127\.0\.0\.1)|port\s*=\s*3306)", re.IGNORECASE)
API_IMPORT_PAT = re.compile(
    r"^\s*(?:from|import)\s+(flask|fastapi|django|tornado|bottle|sanic|aiohttp\.web)\b",
    re.IGNORECASE)
FRONTEND_EXT = (".html", ".htm", ".vue", ".js", ".jsx", ".ts", ".tsx", ".css")
DDL_EXT = (".sql", ".ddl")
CRED_PAT = re.compile(
    r"(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|"
    r"ZHIPU|OPENAI|DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)",
    re.IGNORECASE)


# ---------------------------------------------------------------------------
# 参数
# ---------------------------------------------------------------------------
_ap = argparse.ArgumentParser(
    description="第 8 阶段（智能问答系统）：专项验收（《21》第八节 39 行逐行）")
_ap.add_argument("--root", default=REPO_ROOT,
                 help="被验收对象所在根目录（默认＝仓库根）；用于对镜像根／被篡改副本运行")
_ap.add_argument("--profile", default="full", choices=["full", "static"],
                 help="full＝39 行全执行（默认，收口判定用）；static＝需要子进程／重算装配的"
                      "检查项记未执行（不作为收口判定，退出码 2）")
_ap.add_argument("--selftest", action="store_true",
                 help="负向校准：先跑原样副本（正向对照），再构造 5 个反例断言门禁真的 FAIL")
_ap.add_argument("--keep-tmp", action="store_true", help="保留临时目录（镜像根）")
_ap.add_argument("--emit-json", default=None,
                 help="把逐行状态写成 JSON（供 --selftest 判读；默认不写）")
ARGS = _ap.parse_args()
ROOT = os.path.abspath(ARGS.root)


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
    text = read_text(path)
    if text is None:
        return None
    return [json.loads(line) for line in text.split("\n") if line.strip()]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def line_index(text, needle):
    for i, line in enumerate(text.split("\n"), 1):
        if needle in line:
            return i
    return None


def br(seq, limit=4):
    seq = list(seq)
    head = "、".join(str(x) for x in seq[:limit])
    return head + ("…（共 %d 个）" % len(seq) if len(seq) > limit else "")


def rel(path, base=None):
    try:
        return os.path.relpath(path, base or ROOT).replace("\\", "/")
    except ValueError:
        return path


def resolve_under_root(path, root):
    """把清单里登记的**绝对路径**落到本根下：正常情形原样返回；`--root` 指向镜像根时，
    清单里仍是原仓库的绝对路径，此时按「从某个存在的顶层目录起」的尾部在 root 下重定位。

    这样 A1 的指纹复算与 G4 的产物 SHA-256 复算才**真的在核本根下的文件**，而不是
    在核原仓库的文件（否则镜像里这两项形同虚设）。
    """
    if not path:
        return None
    p = os.path.normpath(path)
    try:
        if os.path.isfile(p) and os.path.commonpath(
                [os.path.abspath(p), os.path.abspath(root)]) == os.path.abspath(root):
            return p
    except ValueError:
        pass
    parts = p.replace("\\", "/").split("/")
    for i in range(len(parts)):
        cand = os.path.join(root, *parts[i:])
        if os.path.isfile(cand):
            return cand
    return None


def table_row(text, first_cell, col=1):
    """在 Markdown 表格里取「首列 == first_cell」那一行的第 col 个单元格（0 起）。"""
    for line in text.split("\n"):
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if cells and cells[0].strip("*` ") == first_cell and len(cells) > col:
            return cells[col]
    return None


def strip_emphasis(s):
    return re.sub(r"[*`\s]", "", s or "")


# ---------------------------------------------------------------------------
# 报告器（沿用《验收第7阶段.py》的 [OK ]/[FAIL]/[SKIP] 布局，另加 note()）：
# 每一行验收项登记一次，行号（A1…H4）与状态一起记账，供「计数自洽」自证。
# ---------------------------------------------------------------------------
class Gate(object):
    def __init__(self, root, profile, capture=None):
        self.root = os.path.abspath(root)
        self.profile = profile
        self.capture = capture            # 非 None 时输出进列表而不打印（供 --selftest 内部复用）
        self.rows = []                    # [(gid, status)]
        self.fails = []                   # [(gid, label, detail)]
        self.env_fails = []
        self.unrun = []
        self.skips = []
        self.notes = []
        self.mods = {}
        self.cache = {}

    # --- 输出 ---------------------------------------------------------------
    def out(self, s=""):
        if self.capture is None:
            print(s)
        else:
            self.capture.append(s)

    def _emit(self, status, label, detail=""):
        self.out("  [%s] %s%s" % (status.ljust(4), label, ("  " + detail) if detail else ""))

    def note(self, label, detail=""):
        self.notes.append((label, detail))
        self.out("  [OK ] %s%s" % (label, ("  " + detail) if detail else ""))

    def group(self, title):
        self.out("")
        self.out("-" * 78)
        self.out(title)
        self.out("-" * 78)

    def row(self, gid, ok, label, detail=""):
        status = "OK" if ok else "FAIL"
        self._emit(status, "%s %s" % (gid, label), detail)
        self.rows.append((gid, status))
        if not ok:
            self.fails.append((gid, label, detail))
        return bool(ok)

    def row_skip(self, gid, label, detail=""):
        self._emit("SKIP", "%s %s" % (gid, label), detail)
        self.rows.append((gid, "SKIP"))
        self.skips.append((gid, label, detail))

    def row_unrun(self, gid, label, detail=""):
        self._emit("UNRUN", "%s %s" % (gid, label), detail)
        self.rows.append((gid, "UNRUN"))
        self.unrun.append((gid, label, detail))

    def static_unrun(self, gid, label, detail=""):
        """static 档跳过该项（记未执行、不算通过、也不算失败）；返回是否已跳过。"""
        if self.profile == "static":
            self.row_unrun(gid, label, detail)
            return True
        return False

    def envfail(self, label, detail=""):
        self.out("  [ENV ] 环境／链上失败（非内容失败）：%s%s"
                 % (label, ("  " + detail) if detail else ""))
        self.env_fails.append((label, detail))

    # --- 路径 ---------------------------------------------------------------
    def p(self, *parts):
        return os.path.join(self.root, *parts)

    @property
    def stage8(self):
        return self.p("阶段08-智能问答系统")

    @property
    def out_dir(self):
        return os.path.join(self.stage8, "问答产出")

    @property
    def code8(self):
        return self.p("代码", "问答")

    @property
    def stage7out(self):
        return self.p("阶段07-RAG检索系统", "检索产出")

    # --- 模块加载（被验收对象，从 --root 下加载；只读） ----------------------
    def load_modules(self):
        if self.mods:
            return self.mods
        qa = self.code8
        if not os.path.isdir(qa):
            return {}
        sys.path.insert(0, qa)
        for name in ("config", "rules", "prompt", "assemble", "answer", "history",
                     "run_answer", "check_inputs"):
            sys.modules.pop(name, None)
        try:
            import config
            import rules
            import prompt as prompt_mod
            import assemble as asm
            import answer as ans
            import history as hist
        except Exception as exc:                      # noqa: BLE001 环境失败而非内容失败
            self.envfail("加载 代码\\问答 模块", "%s: %s" % (type(exc).__name__, exc))
            return {}
        self.mods = {"config": config, "rules": rules, "prompt": prompt_mod,
                     "assemble": asm, "answer": ans, "history": hist,
                     "root_seen": getattr(config, "ROOT", None)}
        return self.mods

    def cached(self, key, fn):
        if key not in self.cache:
            self.cache[key] = fn()
        return self.cache[key]

    # --- 共用数据 -----------------------------------------------------------
    def answered(self):
        """answer_trace.jsonl 的 30 行（qid → 行）。"""
        return self.cached("answer_trace", lambda: {
            r["qid"]: r for r in (read_jsonl(os.path.join(self.out_dir,
                                                          "answer_trace.jsonl")) or [])})

    def records(self):
        return self.cached("records", lambda: read_jsonl(
            os.path.join(self.out_dir, "qa_records.jsonl")) or [])

    def stage7_trace(self):
        return self.cached("s7trace", lambda: {
            r["qid"]: r for r in (read_jsonl(os.path.join(self.stage7out,
                                                          "per_question_trace.jsonl"))
                                  or [])})

    def questions(self):
        return self.cached("questions", lambda: read_jsonl(
            os.path.join(self.root, "阶段07-RAG检索系统", "预实验问题集",
                         "questions.jsonl")) or [])

    def assembled(self, repeat=0):
        """现场重算装配（0 次模型调用）。repeat=1 时再算一遍，供确定性比对。"""
        key = "assembled%d" % repeat
        if key in self.cache:
            return self.cache[key]
        mods = self.load_modules()
        if not mods:
            return []
        try:
            cases = mods["assemble"].assemble_all()
        except BaseException as exc:                  # noqa: BLE001
            self.envfail("现场重算装配（assemble_all）",
                         "%s: %s" % (type(exc).__name__, exc))
            cases = []
        self.cache[key] = cases
        return cases

    def cases_by_qid(self, repeat=0):
        key = "cases%d" % repeat
        if key not in self.cache:
            self.cache[key] = {c["qid"]: c for c in self.assembled(repeat)}
        return self.cache[key]

    def git_status(self):
        """`git -c core.quotepath=false status --porcelain`；返回 (ok, lines, detail)。"""
        if "git" in self.cache:
            return self.cache["git"]
        if not os.path.isdir(os.path.join(self.root, ".git")):
            res = (False, [], "根目录下无 .git（不是 git 仓库）：%s" % self.root)
            self.cache["git"] = res
            return res
        try:
            proc = subprocess.run(
                ["git", "-c", "core.quotepath=false", "status", "--porcelain"],
                cwd=self.root, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            res = (False, [], "git 调用失败：%s" % exc)
            self.cache["git"] = res
            return res
        lines = [l for l in (proc.stdout or "").split("\n") if l.strip()]
        res = (proc.returncode == 0, lines, "exit=%d、%d 条" % (proc.returncode, len(lines)))
        self.cache["git"] = res
        return res


# ---------------------------------------------------------------------------
# A 组：输入与只读
# ---------------------------------------------------------------------------
def group_a(g):
    g.group("A、《21》第八节 A 组（第 1～4 行：A1 输入指纹清单可复算 ／ A2 输入只读 ／ "
            "A3 检索侧未被改动 ／ A4 无数据库动作）")

    manifest_path = os.path.join(g.out_dir, "input_manifest.json")
    manifest = read_json(manifest_path)

    # 现场重算 10 个文件（＝《21》第三节 八项）的字节数与 SHA-256。
    recomputed = []
    if manifest and isinstance(manifest.get("items"), list):
        for item in manifest["items"]:
            for f in (item.get("files") or []):
                path = resolve_under_root(f.get("path"), g.root)
                row = {"item": item.get("item"), "key": f.get("key"), "path": path,
                       "bytes_m": f.get("bytes"), "sha_m": f.get("sha256")}
                if path and os.path.isfile(path):
                    row["bytes_r"] = os.path.getsize(path)
                    row["sha_r"] = sha256_file(path)
                else:
                    row["bytes_r"] = row["sha_r"] = None
                recomputed.append(row)
    ok_files = [r for r in recomputed
                if r["bytes_r"] == r["bytes_m"] and r["sha_r"] == r["sha_m"]]
    bad = [r for r in recomputed if r not in ok_files]

    # A1：清单可复算 ＋ 与第 7 阶段 input_manifest 同路径对拍。
    s7man = read_json(os.path.join(g.stage7out, "input_manifest.json")) or {}
    s7_map = {}
    for f in (s7man.get("files") or []):
        s7_map[strip_emphasis(f.get("path", "")).replace("/", "\\").lower()] = f
    crossed = mismatched = 0
    for r in recomputed:
        key = os.path.relpath(r["path"], g.root).replace("/", "\\").lower() if r["path"] else ""
        hit = s7_map.get(key)
        if hit:
            crossed += 1
            if hit.get("sha256") != r["sha_r"]:
                mismatched += 1
    if not manifest:
        g.row("A1", False, "输入指纹清单可复算",
              "读不到《21》第三节 的 8 条指纹清单：%s" % rel(manifest_path, g.root))
    else:
        g.row("A1", len(bad) == 0 and len(recomputed) == 10 and mismatched == 0,
              "输入指纹清单可复算",
              "items=%d files=%d；收工重算一致 %d／%d；与第 7 阶段 input_manifest 同路径对拍"
              "%d 条、不一致 %d 条%s"
              % (len(manifest.get("items") or []), len(recomputed), len(ok_files),
                 len(recomputed), crossed, mismatched,
                 "" if not bad else "；不一致：" + br([
                     "%s(登记 %s／重算 %s)" % (r["key"], (r["sha_m"] or "")[:12],
                                              (r["sha_r"] or "缺失")[:12]) for r in bad], 3)))

    # A2：开工值 vs 收工值逐项一致 ＋ 清单自报读数现场复算（数据集版本、行数、图谱规模）。
    live = {}
    if manifest:
        ds = read_json(os.path.join(g.root, "阶段05-数据准备", "数据集", "v2.1", "meta",
                                    "dataset.json")) or {}
        ds2 = ds.get("dataset") if isinstance(ds.get("dataset"), dict) else ds
        chunks = read_jsonl(os.path.join(g.root, "阶段05-数据准备", "数据集", "v2.1",
                                         "chunks", "chunks.jsonl"))
        docs = read_jsonl(os.path.join(g.root, "阶段05-数据准备", "数据集", "v2.1", "clean",
                                       "documents.jsonl"))
        # 2026-10-03 口径切换：图谱交付口径由 v2.1_v1_2 切到 **v2.1_v1_3**（见《02》修订记录 v3.6）。
        nodes = read_text(os.path.join(g.root, "阶段06-事件抽取与知识图谱", "图谱导出",
                                       "v2.1_v1_3", "nodes.csv"), "")
        edges = read_text(os.path.join(g.root, "阶段06-事件抽取与知识图谱", "图谱导出",
                                       "v2.1_v1_3", "edges.csv"), "")
        live = {
            "dataset_version": ds2.get("dataset_version"),
            "data_cutoff_time": ds2.get("data_cutoff_time"),
            "chunks_rows": len(chunks or []),
            "documents_rows": len(docs or []),
            "nodes_csv_data_rows": max(len(nodes.strip().split("\n")) - 1, 0) if nodes else None,
            "edges_csv_data_rows": max(len(edges.strip().split("\n")) - 1, 0) if edges else None,
            "trace_rows": len(g.stage7_trace()),
            "questions_rows": len(g.questions()),
        }
        claimed = dict(manifest.get("scale_measured") or {})
        claimed.update({"dataset_version": manifest.get("dataset_version"),
                        "data_cutoff_time": manifest.get("data_cutoff_time")})
        diff = {k: (claimed.get(k), live.get(k)) for k in live
                if k in claimed and claimed.get(k) != live.get(k)}
        same = len(bad) == 0 and not diff
        g.row("A2", same, "输入只读（开工值与收工值逐项一致）",
              "8 项 10 文件：字节数＋SHA-256 逐项一致 %d／%d；清单自报读数现场复算："
              "dataset_version=%s、data_cutoff_time=%s、chunks=%s、documents=%s、"
              "nodes=%s、edges=%s%s"
              % (len(ok_files), len(recomputed), live.get("dataset_version"),
                 live.get("data_cutoff_time"), live.get("chunks_rows"),
                 live.get("documents_rows"), live.get("nodes_csv_data_rows"),
                 live.get("edges_csv_data_rows"),
                 "" if not diff else "；不一致：" + br(["%s 登记 %r／实测 %r" % (k, v[0], v[1])
                                                   for k, v in diff.items()], 3)))

    # A3：`git status --porcelain` 中检索侧无条目。
    if g.static_unrun("A3", "检索侧未被改动（git status --porcelain）",
                      "static 档不跑子进程"):
        pass
    else:
        ok_git, lines, gdetail = g.git_status()
        scoped = [l for l in lines
                  if ("代码/检索/" in l.replace("\\", "/")
                      or "阶段07-RAG检索系统/检索产出/" in l.replace("\\", "/"))]
        if not ok_git:
            g.envfail("A3 git status 不可用", gdetail)
        g.row("A3", ok_git and not scoped, "检索侧未被改动（git status --porcelain）",
              "git %s；题目范围为 代码/检索/ 与 阶段07-RAG检索系统/检索产出/，命中 %d 条%s"
              % (gdetail, len(scoped),
                 "" if not scoped else "：" + br([l.strip() for l in scoped], 3)))

    # A4：仓库内无建表语句／无连接串／*.sql 缺失；六表口径仍可读。
    ddl_hits = []
    for name in sorted(os.listdir(g.code8)) if os.path.isdir(g.code8) else []:
        if not name.endswith(".py"):
            continue
        path = os.path.join(g.code8, name)
        text = read_text(path, "")
        for i, line in enumerate(text.split("\n"), 1):
            if DDL_PAT.search(line) or DB_CONN_PAT.search(line):
                ddl_hits.append("%s:%d %s" % (rel(path, g.root), i, line.strip()[:60]))
    sql_files = []
    for dirpath, dirnames, filenames in os.walk(g.root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            if fn.lower().endswith(DDL_EXT):
                sql_files.append(rel(os.path.join(dirpath, fn), g.root))
    # **时点限定（2026-09-30，第 9 阶段 T2 落地时按《24-第9阶段任务书（前后端系统集成）》
    # 第4.7节 的登记调整）**：「仓库内无 *.sql／*.ddl」是**第 8 阶段收口时点**的判据——第 8 阶段
    # 刻意不写 DDL、不建库（六张表只在文档里）。第 9 阶段的 T2 起，`代码\后端\schema\六张表.sql`
    # 是**合法且必需**的产出（六张表的建表脚本），再把它判失败等于用一条会随时点失效的判据否掉
    # 后续阶段。故改为：**只在第 9 阶段开工后豁免第 9 阶段的 DDL 所在目录**（`代码\后端\`），
    # 其余任何位置出现 *.sql／*.ddl 仍然判失败；豁免项**在输出里逐条列出**（不是静默放过）。
    # 判据不放宽：A4 的主体（`代码\问答\` 交付范围内无建表语句、无连接串；《02》六表口径可读）
    # **一字未动**。
    p9_marker = g.p(os.path.join("阶段09-前后端系统集成",
                                 "24-第9阶段任务书（前后端系统集成）.md"))
    stage9_started = os.path.isfile(p9_marker)
    # 注意：`rel()` 返回的路径用**正斜杠**（POSIX 风格），故豁免前缀也用正斜杠比较。
    exempt_prefix = "代码/后端"
    sql_unexpected = [f for f in sql_files
                      if not (stage9_started and f.lower().startswith(exempt_prefix))]
    sql_exempt = [f for f in sql_files if f not in sql_unexpected]
    p02 = read_text(os.path.join(g.root, "02-项目执行总控文档.md"), "")
    six_names = ("user", "document", "document_chunk", "question", "answer",
                 "answer_evidence")
    sec91 = ""
    m = re.search(r"###\s*9\.1[^\n]*\n(.*?)(?=\n###\s|\n##\s|\Z)", p02, re.S)
    if m:
        sec91 = m.group(1)
    six_ok = bool(sec91) and all(n in sec91 for n in six_names) and ("六张" in sec91
                                                                    or "6 张" in sec91)
    g.row("A4", not ddl_hits and not sql_unexpected and six_ok,
          "无数据库动作（第 8 阶段交付范围内无建表语句／无连接串；"
          "仓库内 *.sql 的时点限定见下）",
          "代码\\问答 下 DDL／连接串命中 %d 处%s；仓库内 *.sql／*.ddl %d 个%s；"
          "其中第 9 阶段开工后豁免 %d 个（豁免目录＝代码\\后端\\，标志文件%s）；"
          "待判 *.sql／*.ddl %d 个%s；《02》第9.1节 六表口径可读=%s"
          % (len(ddl_hits), "" if not ddl_hits else "：" + br(ddl_hits, 3),
             len(sql_files), "" if not sql_files else "：" + br(sql_files, 3),
             len(sql_exempt), "存在" if stage9_started else "不存在",
             len(sql_unexpected), "" if not sql_unexpected else "：" + br(sql_unexpected, 3),
             six_ok))


# ---------------------------------------------------------------------------
# B 组：冻结配置
# ---------------------------------------------------------------------------
def group_b(g):
    g.group("B、《21》第八节 B 组（第 5～8 行：B1 模型三值一致 ／ B2 参数无第二份字面量 ／ "
            "B3 Prompt 版本一致 ／ B4 调用次数如实）")
    mods = g.load_modules()
    p21 = g.p("阶段08-智能问答系统", "21-第8阶段任务书（智能问答系统）.md")
    t21 = read_text(p21, "")
    p02 = read_text(os.path.join(g.root, "02-项目执行总控文档.md"), "")
    if not mods:
        for gid, label in (("B1", "模型三值一致"), ("B2", "参数无第二份字面量"),
                           ("B3", "Prompt 版本一致"), ("B4", "调用次数如实")):
            g.row(gid, False, label, "环境失败：代码\\问答 模块不可加载")
        return
    cfg = mods["config"]
    answer_cfg = dict(getattr(cfg, "ANSWER", {}) or {})

    # 《21》第五节 硬约束 2 的冻结值（现场从原文解析，解析不到退回常量并注明）。
    frozen = dict(FROZEN_ANSWER_FALLBACK)
    parsed = {}
    for name, pat in (("model_name", r"`model_name\s*=\s*\"([^\"]+)\"`"),
                      ("model_version", r"`model_version\s*=\s*\"([^\"]+)\"`"),
                      ("temperature", r"`temperature\s*=\s*(\d+)`"),
                      ("endpoint", r"`endpoint\s*=\s*\"([^\"]+)\"`"),
                      ("max_tokens", r"`max_tokens\s*=\s*(\d+)`")):
        m = re.search(pat, t21)
        if m:
            parsed[name] = m.group(1)
    src_note = "《21》原文解析"
    if parsed:
        if "temperature" in parsed:
            frozen["temperature"] = int(parsed["temperature"])
        if "max_tokens" in parsed:
            frozen["max_tokens"] = int(parsed["max_tokens"])
        for k in ("model_name", "model_version", "endpoint"):
            if k in parsed:
                frozen[k] = parsed[k]
    else:
        src_note = "退回脚本常量（《21》原文未解析到）"
    line_h2 = line_index(t21, "model_name = ")

    three = ("model_name", "model_version", "temperature")
    bad3 = {k: (frozen.get(k), answer_cfg.get(k)) for k in three
            if answer_cfg.get(k) != frozen.get(k)}
    ep_bad = answer_cfg.get("endpoint") != frozen.get("endpoint")
    # `max_tokens`（硬约束 2 的冻结值，现场从《21》第五节 解析进 frozen["max_tokens"]）：
    # 旧实现把它解析进来后**从未参与比较**，实测改成 8192 全档 39 行无一行报错（B-04）。
    mt_bad = answer_cfg.get("max_tokens") != frozen.get("max_tokens")

    # 《02》第12.4节 已登记的行（temperature／Prompt 版本）逐字比对；大语言模型两行仍 TBD 时
    # 只登记口径（v3.3 登记属 T12），不作失败判据——这一点在输出里显式说明。
    t_temp = strip_emphasis(table_row(p02, "temperature", 1))
    t_prompt = strip_emphasis(table_row(p02, "Prompt 版本", 1))
    t_llm = table_row(p02, "大语言模型", 1) or ""
    t_llm_ver = table_row(p02, "模型版本", 1) or ""
    reg_bad = []
    if t_temp and t_temp != str(frozen["temperature"]):
        reg_bad.append("《02》12.4 temperature=%r／config=%r" % (t_temp, frozen["temperature"]))
    if t_prompt and t_prompt != frozen["prompt_version"]:
        reg_bad.append("《02》12.4 Prompt 版本=%r／config=%r" % (t_prompt,
                                                              frozen["prompt_version"]))
    llm_tbd = "TBD" in t_llm or "TBD" in t_llm_ver
    llm_bad = []
    if not llm_tbd:
        if frozen["model_name"] not in t_llm:
            llm_bad.append("《02》12.4 大语言模型=%r 未含 %r" % (strip_emphasis(t_llm),
                                                            frozen["model_name"]))
        if frozen["model_version"] not in t_llm_ver:
            llm_bad.append("《02》12.4 模型版本=%r 未含 %r" % (strip_emphasis(t_llm_ver),
                                                          frozen["model_version"]))
    b1_ok = not bad3 and not ep_bad and not mt_bad and not reg_bad and not llm_bad
    g.row("B1", b1_ok, "模型三值一致（《21》第五节 硬约束 2 ＋《02》第12.4节 登记）",
          "model_name=%s／model_version=%s／temperature=%s／endpoint=%s／max_tokens=%s"
          "（冻结值 max_tokens=%s；%s；《21》第 %s 行）；"
          "《02》12.4 已登记行 temperature=%r、Prompt 版本=%r，不一致 %d 处%s；"
          "大语言模型行=%s"
          % (answer_cfg.get("model_name"), answer_cfg.get("model_version"),
             answer_cfg.get("temperature"), answer_cfg.get("endpoint"),
             answer_cfg.get("max_tokens"), frozen.get("max_tokens"), src_note,
             line_h2, t_temp, t_prompt, len(reg_bad) + len(llm_bad) + (1 if mt_bad else 0),
             "" if not (reg_bad or llm_bad or mt_bad) else "：" + br(
                 reg_bad + llm_bad + (["max_tokens config=%r／冻结=%r"
                                       % (answer_cfg.get("max_tokens"), frozen.get("max_tokens"))]
                                      if mt_bad else []), 3),
             "仍为 TBD（v3.3 登记属 T12，本行按《21》的裁定值比对，不以《02》尚未登记的"
             "行判失败）" if llm_tbd else strip_emphasis(t_llm)[:40]))

    # B2：四项定值由 代码\检索\config.py 导入；其余模块不得出现第二份字面量。
    ret = getattr(cfg, "RETRIEVAL", {}) or {}
    fixed_bad = {k: (v, ret.get(k)) for k, v in EXPECT_FIXED.items() if ret.get(k) != v}
    cfg_k = getattr(cfg, "K", None)
    cfg_n = getattr(cfg, "N", None)
    cfg_bud = getattr(cfg, "CONTEXT_TOKEN_BUDGET", None)
    cfg_g = getattr(cfg, "G", None)
    # ① 四个**导出值**必须分别等于冻结值（旧实现只判「不是 None」——写死 `K = 8` 也判 [OK]，
    #    输出里「检索侧 K=10／config 导入 K=8」自相矛盾；全面审查 B-01、反例 R2 变体 case7）。
    cfg_export = {"K": (cfg_k, EXPECT_FIXED["K"]), "N": (cfg_n, EXPECT_FIXED["N"]),
                  "CONTEXT_TOKEN_BUDGET": (cfg_bud, EXPECT_FIXED["context_token_budget"]),
                  "G": (cfg_g, EXPECT_FIXED["graph_retention_share"])}
    export_bad = {k: (v[0], v[1]) for k, v in cfg_export.items() if v[0] != v[1]}
    # 其余模块：不得出现 3600／16384 字面量（四项里最具区分度的两个），不得顶层重声明这
    # 四个名字，且四项的**取用**必须经 config 走：`config.<名>` 属性访问、或
    # `config.require_fixed("<键>")`、或 `config.RETRIEVAL["<键>"]` 下标（AST 取证据）。
    lit_bad = []
    use_sites = {}          # 逻辑键 → [证据串]
    attr_names = set()
    used_modules = []
    for name in sorted(os.listdir(g.code8)):
        if not name.endswith(".py") or name == "config.py":
            continue
        path = os.path.join(g.code8, name)
        text = read_text(path, "")
        used_modules.append(name)
        try:
            tree = ast.parse(text)
        except SyntaxError:
            lit_bad.append("%s 解析失败" % name)
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, int) \
                    and not isinstance(node.value, bool) \
                    and node.value in (3600, 16384):
                lit_bad.append("%s:%d 字面量 %s" % (rel(path, g.root), node.lineno, node.value))
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                    and node.value.id == "config":
                attr_names.add(node.attr)
                if node.attr in ("K", "N", "CONTEXT_TOKEN_BUDGET", "G"):
                    use_sites.setdefault(node.attr, []).append(
                        "%s:%d" % (name, node.lineno))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and isinstance(node.func.value, ast.Name) \
                    and node.func.value.id == "config" \
                    and node.func.attr == "require_fixed" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    use_sites.setdefault(arg.value, []).append(
                        "%s:%d require_fixed" % (name, node.lineno))
        # 顶层赋值 `K = 10` 这类第二份字面量
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for tgt in node.targets:
                    if isinstance(tgt, ast.Name) and tgt.id in ("K", "N",
                                                                "CONTEXT_TOKEN_BUDGET", "G"):
                        lit_bad.append("%s:%d 顶层赋值 %s" % (rel(path, g.root), node.lineno,
                                                          tgt.id))
    # ② `config.py` 单独做 AST 检查：四个名字的**赋值右侧必须引用从检索侧加载的对象**
    #    （`_need(...)`／`_RET`／`RETRIEVAL`），**不得是整数字面量**。旧实现用
    #    `if ... or name == "config.py": continue` 把**唯一的参数来源文件本身**跳过了，
    #    于是往 `config.py` 写一行 `K = 8` 也判 [OK]（B-01：第二份字面量恰恰藏在它声称设防
    #    的那个文件里）。注意 `ANSWER["max_tokens"] = 16384` 不在这四个名字里，不误报。
    src_bad = []
    cfg_tree = None
    try:
        cfg_tree = ast.parse(read_text(os.path.join(g.code8, "config.py"), ""))
    except SyntaxError as exc:
        src_bad.append("config.py 解析失败：%s" % exc)
    if cfg_tree is not None:
        imported_names = {"_need", "_RET", "RETRIEVAL"}
        assigned = {}
        for node in cfg_tree.body:
            tgt_names = []
            if isinstance(node, ast.Assign):
                tgt_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                tgt_names = [node.target.id]
                node = ast.Assign(targets=[node.target], value=node.value)
            for t in tgt_names:
                if t in ("K", "N", "CONTEXT_TOKEN_BUDGET", "G"):
                    assigned.setdefault(t, node)
        for name in ("K", "N", "CONTEXT_TOKEN_BUDGET", "G"):
            node = assigned.get(name)
            if node is None or node.value is None:
                src_bad.append("config.py 顶层未把 %s 赋成检索侧导入值" % name)
                continue
            ids = {n.id for n in ast.walk(node.value) if isinstance(n, ast.Name)}
            ints = sorted({n.value for n in ast.walk(node.value)
                           if isinstance(n, ast.Constant) and isinstance(n.value, int)
                           and not isinstance(n.value, bool)})
            if not (ids & imported_names):
                src_bad.append("config.py:%d %s 的右侧未引用检索侧对象（%s）"
                               % (node.lineno, name, br(sorted(ids), 3) or "无标识符"))
            if ints:
                src_bad.append("config.py:%d %s 的右侧含整数字面量 %s"
                               % (node.lineno, name, br(ints, 3)))

    # 四项定值各自的取用证据（键名与 代码\检索\config.py 的字段名一致）。
    need_keys = {"K": ("K",), "N": ("N",),
                 "context_token_budget": ("CONTEXT_TOKEN_BUDGET", "context_token_budget"),
                 "graph_retention_share": ("G", "graph_retention_share")}
    missing_attrs = []
    for logical, aliases in need_keys.items():
        if not any(a in use_sites for a in aliases):
            missing_attrs.append(logical)
    b2_ok = not fixed_bad and not lit_bad and not missing_attrs and not export_bad and not src_bad
    g.row("B2", b2_ok, "参数无第二份字面量（四项由 代码\\检索\\config.py 导入）",
          "检索侧四项实测 K=%s、N=%s、budget=%s、g=%s；config 导出 K=%s／N=%s／budget=%s／g=%s"
          "（应与冻结值逐项相等）；其余 %d 个模块的取用证据：%s；config.py 四名右侧均引用"
          "检索侧对象=%s%s"
          % (ret.get("K"), ret.get("N"), ret.get("context_token_budget"),
             ret.get("graph_retention_share"), cfg_k, cfg_n, cfg_bud, cfg_g,
             len(used_modules),
             "；".join("%s←%s" % (k, br(v, 2)) for k, v in sorted(use_sites.items())) or "（无）",
             not src_bad,
             "" if b2_ok else "；问题：" + br(list(fixed_bad) + lit_bad
                                            + ["导出值与冻结值不符：%s" % (export_bad,)
                                               if export_bad else ""] + src_bad
                                            + ["四项中未按名取用：%s" % x for x in
                                               sorted(missing_attrs)], 4)))

    # B3：Prompt 版本一致（prompt.py ／ config ／ 快照 ／ 《02》登记 四处）。
    pv = getattr(mods["prompt"], "PROMPT_VERSION", None)
    snap = read_json(os.path.join(g.out_dir, "prompt_snapshot.json")) or {}
    snap_pv = snap.get("prompt_version") or snap.get("version") or snap.get("PROMPT_VERSION")
    rm = read_json(os.path.join(g.out_dir, "run_manifest.json")) or {}
    rm_pv = (rm.get("config_snapshot") or {}).get("prompt_version")
    b3_bad = []
    for lab, val in (("prompt.PROMPT_VERSION", pv), ("config.ANSWER", answer_cfg.get(
            "prompt_version")), ("prompt_snapshot.json", snap_pv),
            ("run_manifest.config_snapshot", rm_pv)):
        if val != "v1.0":
            b3_bad.append("%s=%r" % (lab, val))
    if t_prompt and t_prompt != "v1.0":
        b3_bad.append("《02》12.4 Prompt 版本=%r" % t_prompt)
    g.row("B3", not b3_bad, "Prompt 版本一致（== v1.0，且与《02》第12.4节 一致）",
          "prompt.PROMPT_VERSION=%r、config.ANSWER=%r、快照=%r、run_manifest=%r、"
          "《02》12.4=%r%s"
          % (pv, answer_cfg.get("prompt_version"), snap_pv, rm_pv, t_prompt,
             "" if not b3_bad else "；不一致：" + br(b3_bad, 4)))

    # B4：调用次数如实。run_manifest 自报 vs 从 answer_trace 的 attempts 现场重算。
    mc = rm.get("model_calls") or {}
    rows = sorted(g.answered().values(), key=lambda r: r["qid"])
    attempts_total = sum(len(r.get("attempts") or []) for r in rows)
    retries_live = attempts_total - len(rows)
    retried = [r["qid"] for r in rows if len(r.get("attempts") or []) > 1]
    declared_total = mc.get("total")
    declared_retries = mc.get("retries")
    per_cycle = mc.get("questions_per_cycle")
    cycles = {k: v for k, v in mc.items()
              if re.fullmatch(r"cycle_\d+", str(k)) and isinstance(v, int)}
    n_rows = len(rows)
    cycles_ok = bool(cycles) and all(v == n_rows for v in cycles.values())
    b4_ok = (n_rows == 30 and per_cycle == n_rows and cycles_ok
             and declared_total == sum(cycles.values())
             and (declared_retries == retries_live))
    g.row("B4", b4_ok, "调用次数如实（run_manifest 自报 vs 现场重算）",
          "题数=%d；run_manifest：%s、每轮 questions_per_cycle=%s、total=%s、retries=%s；"
          "现场重算：answer_trace 的 attempts 合计 %d ＝ %d 题 × 1 次，重试 %d 次、重试题 %s；"
          "dry-run 为 0 由 G1 核"
          % (n_rows, "／".join("%s=%s" % (k, v) for k, v in sorted(cycles.items())),
             per_cycle, declared_total, declared_retries, attempts_total, n_rows,
             retries_live, br(retried) if retried else "无"))


# ---------------------------------------------------------------------------
# C 组：Prompt 装配
# ---------------------------------------------------------------------------
def group_c(g):
    g.group("C、《21》第八节 C 组（第 9～14 行：C1 七区块齐全且顺序固定 ／ C2 第 2 区块每次注入 ／ "
            "C3 证据顺序未被重排 ／ C4 预算不突破 ／ C5 未使用图谱扩展时的区块处理 ／ C6 装配确定性）")
    mods = g.load_modules()
    cases = g.cases_by_qid()
    cases2 = g.cases_by_qid(1)
    p10 = read_text(os.path.join(g.root, "阶段04-系统总体设计",
                                 "10-系统总体设计（第四阶段）.md"), "")
    blocks = list(getattr(mods["prompt"], "BLOCK_TITLES", []) or []) if mods else []

    # C1：表 4-12 的七区块标题与顺序，与 prompt.BLOCK_TITLES 逐字比对。
    table_blocks = []
    for lab in BLOCK_TABLE_LABELS:
        cell = table_row(p10, lab, 1)
        if cell:
            table_blocks.append(strip_emphasis(cell))
    line_t412 = line_index(p10, "表 4-12")
    c1_ok = (table_blocks == blocks and len(blocks) == 7)
    g.row("C1", c1_ok, "七区块齐全且顺序固定",
          "prompt.BLOCK_TITLES=%s；《10》表 4-12（第 %s 行）=%s；一致=%s"
          % (json.dumps(blocks, ensure_ascii=False), line_t412,
             json.dumps(table_blocks, ensure_ascii=False), table_blocks == blocks))
    # 渲染后的文本里七区块标题按序出现（再核一遍「顺序固定」）。
    if cases:
        sample = cases[sorted(cases)[0]]["prompt"]
        text = (sample.get("system") or "") + "\n" + (sample.get("user") or "")
        # 按区块标题的**标题形态**「【标题】」定位（区块 1 的正文里也提到了「文本证据」
        # 「图谱路径与事件三元组」，裸串定位会被这些提及干扰）。
        pos = [text.find("【%s】" % t) for t in blocks]
        ordered = all(p >= 0 for p in pos) and pos == sorted(pos)
        g.note("C1 补充证据", "%s 渲染文本中七个区块标题按「【标题】」形态均出现且顺序一致=%s"
               "（位置 %s）" % (sorted(cases)[0], ordered, pos))
    else:
        g.note("C1 补充证据", "装配不可用，未做渲染文本序核")

    # C2：30 题逐题 Prompt 文本含 dataset_version 与 data_cutoff_time 字面值。
    if g.static_unrun("C2", "第 2 区块每次注入（30 题逐题）", "static 档不重算装配"):
        pass
    elif not cases:
        g.envfail("C2 现场重算装配", "assemble_all 失败或不可用")
    else:
        missing = []
        for qid in sorted(cases):
            c = cases[qid]
            blob = (c["prompt"].get("system") or "") + (c["prompt"].get("user") or "")
            for lit, lab in ((c["dataset_version"], "dataset_version"),
                             (c["data_cutoff_time"], "data_cutoff_time")):
                if lit not in blob:
                    missing.append("%s 缺 %s(%s)" % (qid, lab, lit))
        g.row("C2", not missing and len(cases) == 30, "第 2 区块每次注入（30 题逐题）",
              "逐题检查 %d 题，缺字面值 %d 处%s；字面值：dataset_version=%s、"
              "data_cutoff_time=%s"
              % (len(cases), len(missing), "" if not missing else "：" + br(missing, 3),
                 (cases[sorted(cases)[0]]["dataset_version"] if cases else None),
                 (cases[sorted(cases)[0]]["data_cutoff_time"] if cases else None)))

    # C3：证据顺序未被重排（两层：产物文件的呈现顺序 ＋ 现场重算的顺序）。
    if g.static_unrun("C3", "证据顺序未被重排（30／30）", "static 档不重算装配"):
        pass
    else:
        s7 = g.stage7_trace()
        prod_bad, recomp_bad, checked = [], [], 0
        for qid in sorted(g.answered()):
            a = g.answered()[qid]
            gold = (s7.get(qid) or {}).get("final_evidence_chunk_ids")
            if gold is None:
                continue
            checked += 1
            stored = [e["chunk_id"] for e in (a.get("evidence") or [])]
            if stored != gold:
                prod_bad.append("%s 呈现序 %s ≠ trace %s" % (qid, br(stored, 3), br(gold, 3)))
            if qid in cases:
                rec = [e["chunk_id"] for e in cases[qid]["evidence"]]
                if rec != gold:
                    recomp_bad.append("%s 重算序 %s ≠ trace %s" % (qid, br(rec, 3), br(gold, 3)))
        g.row("C3", checked == 30 and not prod_bad, "证据顺序未被重排（30／30）",
              "逐题比对 answer_trace 呈现顺序 vs 第 7 阶段 final_evidence_chunk_ids："
              "比对 %d 题、不一致 %d 题%s；现场重算装配的顺序不一致 %d 题%s"
              % (checked, len(prod_bad), "" if not prod_bad else "：" + br(prod_bad, 2),
                 len(recomp_bad), "" if not recomp_bad else "：" + br(recomp_bad, 2)))

    # C4：预算不突破（逐题）。**三项都要查**（全面审查 B-02／C-06：旧实现只查「现场重算的」
    # 那一列，登记的登记值 `answer_trace.jsonl` 一字未查——把某题的 `total_tokens` 改成
    # 3601 仍判 [OK]，因为超限看的是重算列；这就是 C-06 说的「行级假阴性」）：
    #   ① 现场重算：text(逐条 Σ token_count) + path + event_triple == total（分量自洽）；
    #   ② 现场重算值 ≤ 预算；
    #   ③ 登记值（answer_trace.jsonl）== 现场重算值 且 ≤ 预算。
    if g.static_unrun("C4", "预算不突破（≤ 3600，逐题）", "static 档不重算装配"):
        pass
    elif not cases:
        g.envfail("C4 现场重算装配", "assemble_all 失败或不可用")
    else:
        over, sum_bad, add_bad, reg_bad = [], [], [], []
        budget = None
        traced = g.answered()
        for qid in sorted(cases):
            c = cases[qid]
            ta = c["token_account"]
            budget = c.get("context_token_budget")
            # ① 现场重算分量自洽：total 必须由 text(逐条重算) + path + event_triple 组成
            s = sum(e["token_count"] for e in c["evidence"])
            if ta["text_tokens"] != s:
                sum_bad.append("%s text_tokens=%d ≠ Σ token_count=%d" % (qid, ta["text_tokens"], s))
            live = s + ta["path_tokens"] + ta["event_triple_tokens"]
            if ta["total_tokens"] != live:
                add_bad.append("%s 现场 total=%d ≠ text+path+triple=%d"
                               % (qid, ta["total_tokens"], live))
            # ② 现场重算值 ≤ 预算
            if ta["total_tokens"] > budget:
                over.append("%s 现场 total=%d > %d" % (qid, ta["total_tokens"], budget))
            # ③ 登记值（产物 answer_trace.jsonl）== 现场重算值，且 ≤ 预算
            row = traced.get(qid)
            if row is None:
                reg_bad.append("%s 不在 answer_trace.jsonl 里" % qid)
                continue
            rta = row.get("token_account") or {}
            r_total = rta.get("total_tokens")
            if r_total != ta["total_tokens"]:
                reg_bad.append("%s 登记 total=%s ≠ 现场重算=%d" % (qid, r_total, ta["total_tokens"]))
            if isinstance(r_total, int) and r_total > budget:
                reg_bad.append("%s 登记 total=%d > %d" % (qid, r_total, budget))
        worst = max((cases[q]["token_account"]["total_tokens"] for q in cases), default=None)
        c4_ok = (not over and not sum_bad and not add_bad and not reg_bad and budget == 3600)
        g.row("C4", c4_ok, "预算不突破（≤ 3600，逐题）",
              "预算=%s；30 题现场重算 total_tokens 最大值=%s；① 现场 text+path+triple ≠ total %d 题%s；"
              "② 现场超限 %d 题%s；③ 登记值 ≠ 现场重算或登记超限 %d 题%s；"
              "text_tokens 与逐条 token_count 之和不一致 %d 题%s"
              % (budget, worst, len(add_bad), "" if not add_bad else "：" + br(add_bad, 3),
                 len(over), "" if not over else "：" + br(over, 3),
                 len(reg_bad), "" if not reg_bad else "：" + br(reg_bad, 3),
                 len(sum_bad), "" if not sum_bad else "：" + br(sum_bad, 3)))

    # C5：未使用图谱扩展时的区块处理（单元级正反两向）。
    if not mods or not cases:
        g.row("C5", False, "未使用图谱扩展时的区块处理（单元级正反两向）",
              "环境失败：装配不可用")
    else:
        pm = mods["prompt"]
        c = cases[sorted(cases)[0]]
        ev = c["evidence"][:1]
        gused = dict(c["graph_payload"])
        gused["graph_used"] = True
        gfalse = json.loads(json.dumps(c["graph_payload"], ensure_ascii=False))
        gfalse["graph_used"] = False
        gfalse["graph_path"] = []
        gfalse["event_triples"] = []
        kw = dict(question=c["question"], dataset_version=c["dataset_version"],
                  data_cutoff_time=c["data_cutoff_time"], evidence=ev,
                  time_note=c["time_note"])
        m_false = pm.build_messages(graph_payload=gfalse, **kw)
        m_true = pm.build_messages(graph_payload=gused, **kw)
        blob_false = (m_false["system"] or "") + "\n" + (m_false["user"] or "")
        blob_true = (m_true["system"] or "") + "\n" + (m_true["user"] or "")
        marker = pm.NO_GRAPH_MARKER
        graph_title = pm.BLOCK_TITLES[4]
        # 区块标题按**标题形态**「【标题】」判定：第 1 区块的正文里也提到了「图谱路径与
        # 事件三元组」这个短语，裸串判定会被这处提及误导。
        graph_head = "【%s】" % graph_title
        # 口径（代码\\问答\\prompt.py 第 15 行 与《21》第五节 硬约束 8）：graph_used 为假时
        # 第 5 区块**整体缺省**（不输出空标题），且「未使用图谱扩展」的固定字样只出现在**系统
        # 拼装的四段答案**里，不写进 Prompt 区块。故正反两向的判据是：
        #   假 → Prompt 文本里既无图谱区块标题、也无该固定字样；
        #   真 → Prompt 文本里有图谱区块标题，且该区块渲染出实体内容。
        render_false = pm.render_graph_block(gfalse)
        render_true = pm.render_graph_block(gused)
        ok_false = (graph_head not in blob_false) and (marker not in blob_false) \
            and render_false == ""
        ok_true = (graph_head in blob_true) and bool(render_true.strip())
        # 固定字样的落点在四段答案的图谱段：假 → 恰为该字样；真 → 有路径内容、无该字样。
        ans_false = pm.compose_answer(body="门禁单元用正文 [证据1]。", evidence=ev,
                                      graph_payload=gfalse, dataset_version=c["dataset_version"],
                                      data_cutoff_time=c["data_cutoff_time"],
                                      time_note=c["time_note"])
        ans_true = pm.compose_answer(body="门禁单元用正文 [证据1]。", evidence=ev,
                                     graph_payload=gused, dataset_version=c["dataset_version"],
                                     data_cutoff_time=c["data_cutoff_time"],
                                     time_note=c["time_note"])
        sec_false = pm.split_answer_sections(ans_false).get("知识图谱路径")
        sec_true = pm.split_answer_sections(ans_true).get("知识图谱路径")
        sec_false = sec_false if isinstance(sec_false, str) else (sec_false or {}).get("text", "")
        sec_true = sec_true if isinstance(sec_true, str) else (sec_true or {}).get("text", "")
        sec_ok = (sec_false.strip() == marker) and bool(sec_true.strip()) \
            and (sec_true.strip() != marker)
        all30_true = all(bool(cases[q]["graph_payload"].get("graph_used")) for q in cases)
        g.row("C5", ok_false and ok_true and sec_ok,
              "未使用图谱扩展时的区块处理（单元级正反两向）",
              "graph_used=False → Prompt 含图谱区块标题=%s、含固定字样=%s、第 5 区块渲染=%r；"
              "graph_used=True → 含图谱区块标题=%s、区块渲染 %d 字符；四段答案的图谱段："
              "假→%r（应恰为固定字样）、真→%d 字符（应有路径、无固定字样）；"
              "30 题 graph_used 全为真=%s（故本行判定落在单元级正反两向，而非题面抽样）"
              % (graph_head in blob_false, marker in blob_false, render_false,
                 graph_head in blob_true, len(render_true), sec_false.strip(),
                 len(sec_true.strip()), all30_true))

    # C6：装配确定性（同一输入两次装配 Prompt 文本 SHA-256 相同，30／30）。
    if g.static_unrun("C6", "装配确定性（两次装配 SHA-256 相同，30／30）",
                      "static 档不重算装配"):
        pass
    elif not cases or not cases2:
        g.envfail("C6 现场重算装配", "assemble_all 两次中至少一次失败")
    else:
        diff = [q for q in sorted(cases)
                if cases[q]["prompt"]["sha256"] != cases2[q]["prompt"]["sha256"]]
        same_as_trace = [q for q in sorted(cases)
                         if q in g.answered()
                         and cases[q]["prompt"]["sha256"] != g.answered()[q].get(
                             "prompt_sha256")]
        g.row("C6", len(diff) == 0 and len(cases) == 30,
              "装配确定性（两次装配 SHA-256 相同，30／30）",
              "逐题两次装配比对 %d 题、SHA-256 不一致 %d 题%s；与 answer_trace 登记的 "
              "prompt_sha256 不一致 %d 题%s（两次装配均为 0 次模型调用）"
              % (len(cases), len(diff), "" if not diff else "：" + br(diff, 3),
                 len(same_as_trace), "" if not same_as_trace else "：" + br(same_as_trace, 3)))


# ---------------------------------------------------------------------------
# D 组：生成与答案形态
# ---------------------------------------------------------------------------
def group_d(g):
    g.group("D、《21》第八节 D 组（第 15～20 行：D1 30 题全部生成 ／ D2 引用编号落在集合内 ／ "
            "D3 引用覆盖率 ／ D4 图谱段与标注二选一 ／ D5 数据截止与判定区间 ／ D6 开放式问题标注）")
    mods = g.load_modules()
    rows = g.answered()
    cases = g.cases_by_qid()
    rules = mods["rules"] if mods else None
    pm = mods["prompt"] if mods else None

    # D1：30 行、逐行 answer_text 非空。
    empty = [q for q, r in rows.items() if not (r.get("answer_text") or "").strip()]
    g.row("D1", len(rows) == 30 and not empty, "30 题全部生成（answer_trace 30 行、正文非空）",
          "answer_trace.jsonl 行数=%d；answer_text 为空的行 %d 条%s；qa_records.jsonl 行数=%d"
          % (len(rows), len(empty), "" if not empty else "：" + br(empty, 3),
             len(g.records())))

    # D2／D3：引用编号与覆盖率（现场用 rules.py 重算，不读它的登记结论）。
    # D2 看**答案全文**（含代码拼装的【证据来源】段，该段逐条标 `[证据n]`，n=1..m）；D3 看
    # **模型正文【回答】段**——「引用覆盖率」问的是模型有没有真的引，把代码拼装的标签算进去
    # 会让这一项恒真。
    oor, nocite, gate_bad = [], [], []
    cited_stat = []
    for qid in sorted(rows):
        r = rows[qid]
        m = len(r.get("evidence") or [])
        marks = rules.citation_marks(r["answer_text"])
        out = [n for n in marks if n < 1 or n > m]
        if out:
            oor.append("%s 越界 n=%s（m=%d）" % (qid, br(sorted(set(out)), 3), m))
        stored = (r.get("gates") or {}).get("citation_out_of_range")
        if stored:
            gate_bad.append("%s 登记的 citation_out_of_range=%s" % (qid, br(stored, 3)))
        body = r.get("body_text")
        if not body:
            secs = pm.split_answer_sections(r["answer_text"]) if pm else {}
            sec = secs.get("回答")
            body = sec if isinstance(sec, str) else ((sec or {}).get("text") or "")
        cited = sorted({n for n in rules.citation_marks(body) if 1 <= n <= m})
        cited_stat.append((qid, len(cited), m))
        if not cited:
            nocite.append(qid)
    g.row("D2", not oor, "引用编号落在集合内（1 ≤ n ≤ m，越界 0 次）",
          "逐题解析 `[证据n]`（rules.CITATION_RE）30 题：越界 %d 题%s；登记值与现场重算不一致 "
          "%d 题%s" % (len(oor), "" if not oor else "：" + br(oor, 2), len(gate_bad),
                     "" if not gate_bad else "：" + br(gate_bad, 2)))
    lo = min((c for _q, c, _m in cited_stat), default=None)
    hi = max((c for _q, c, _m in cited_stat), default=None)
    tot_c = sum(c for _q, c, _m in cited_stat)
    tot_m = sum(m for _q, _c, m in cited_stat)
    g.row("D3", not nocite and len(cited_stat) == 30,
          "引用覆盖率（每题模型正文至少 1 个落在 1..m 的引用）",
          "逐题在模型正文【回答】段解析 `[证据n]`：0 引用的题 %d 题%s；"
          "逐题被引去重条数最少 %s、最多 %s；合计被引 %d 条／可得 %d 条（%.1f%%）"
          % (len(nocite), "" if not nocite else "：" + br(nocite, 3), lo, hi, tot_c, tot_m,
             100.0 * tot_c / tot_m if tot_m else 0.0))

    # D4：图谱段与固定标注二选一（三方一致，30／30）。
    marker = pm.NO_GRAPH_MARKER if pm else "本次回答未使用图谱扩展"
    section_key = "知识图谱路径"
    d4 = []
    for qid in sorted(rows):
        r = rows[qid]
        used = bool((r.get("graph_payload") or {}).get("graph_used"))
        secs = pm.split_answer_sections(r["answer_text"]) if pm else {}
        sec = secs.get(section_key)
        if sec is None:
            d4.append("%s 四段里无【%s】" % (qid, section_key))
            continue
        sec_body = sec if isinstance(sec, str) else (sec.get("text") or "")
        if used:
            if marker in sec_body or not sec_body.strip():
                d4.append("%s graph_used=1 但系统段=%s" % (qid, br([sec_body.strip()[:20]], 1)))
        else:
            if sec_body.strip() != marker:
                d4.append("%s graph_used=0 但系统段=%r" % (qid, sec_body.strip()[:30]))
    body_leak = [q for q in sorted(rows)
                 if marker in (rows[q].get("body_text") or "")]
    g.row("D4", not d4 and not body_leak, "图谱段与标注二选一（三方一致，30／30）",
          "30 题：graph_used=1 的题系统段有内容且无固定标注、graph_used=0 的题恰为固定标注；"
          "不符 %d 题%s；模型正文出现该固定字样（泄漏）%d 题%s"
          % (len(d4), "" if not d4 else "：" + br(d4, 2), len(body_leak),
             "" if not body_leak else "：" + br(body_leak, 3)))

    # D5：带时间约束的题（题集 time_constraint=「有」）答案含数据截止时间与判定区间。
    qmap = {q.get("qid"): q for q in g.questions()}
    cutoff = None
    need = []
    for qid in sorted(rows):
        q = qmap.get(qid) or {}
        if str(q.get("time_constraint") or "").strip() == "有":
            need.append(qid)
    miss = []
    for qid in need:
        r = rows[qid]
        # 截止时间从现场重算的分区取（`answer_trace.jsonl` 的 token_account 里没有日期，
        # 旧的 `(r.get("token_account") and None)` 恒为 None、是死代码；全面审查 B-05）。
        cutoff = cutoff or (cases.get(qid) or {}).get("data_cutoff_time")
        date_part = (cutoff or "")[:10]
        secs = pm.split_answer_sections(r["answer_text"]) if pm else {}
        sec = secs.get("数据截至与判定区间")
        sec_body = sec if isinstance(sec, str) else ((sec or {}).get("text") or "")
        if date_part and date_part not in sec_body:
            miss.append("%s 时间段缺截止日期 %s" % (qid, date_part))
        if "判定区间" not in sec_body:
            miss.append("%s 时间段未写「判定区间」" % qid)
    g.row("D5", len(need) == 12 and not miss, "数据截止与判定区间（带时间约束的 12 题）",
          "题集 time_constraint=「有」%d 题；时间段缺截止日期或「判定区间」%d 处%s；"
          "data_cutoff_time=%s" % (len(need), len(miss),
                                   "" if not miss else "：" + br(miss, 2), cutoff))

    # D6：开放式问题标注（无开放式题时「不适用」通过并打印理由）。
    types = sorted({str((q or {}).get("task_type")) for q in g.questions()})
    open_qids = [q.get("qid") for q in g.questions()
                 if str(q.get("task_type")) in tuple(getattr(mods["config"],
                                                            "OPEN_ENDED_TASK_TYPES", ()))]
    open_marker = pm.MODEL_ANALYSIS_MARKER if pm else "模型分析（非公开事实）"
    if not open_qids:
        g.row("D6", True, "开放式问题标注（题集标注）",
              "不适用：题集 30 题的 task_type 取值为 %s，其中按 config.OPEN_ENDED_TASK_TYPES="
              "%s 判定为开放式题的为 0 题，故本行以「不适用」通过（判据＝《21》第八节 D6 "
              "「无开放式题时该行以不适用通过并打印理由」）"
              % (json.dumps(types, ensure_ascii=False),
                 json.dumps(list(getattr(mods["config"], "OPEN_ENDED_TASK_TYPES", ())),
                            ensure_ascii=False)))
    else:
        lack = [q for q in open_qids
                if open_marker not in (rows.get(q, {}).get("answer_text") or "")]
        g.row("D6", not lack, "开放式问题标注（题集标注）",
              "开放式题 %d 题；缺「%s」标注 %d 题%s"
              % (len(open_qids), open_marker, len(lack),
                 "" if not lack else "：" + br(lack, 3)))


# ---------------------------------------------------------------------------
# E 组：防幻觉门禁
# ---------------------------------------------------------------------------
def group_e(g):
    g.group("E、《21》第八节 E 组（第 21～25 行：E1 日期来源可核 ／ E2 图谱三方一致 ／ "
            "E3 禁词 0 命中 ／ E4 门禁不静默 ／ E5 证据正文可回链）")
    mods = g.load_modules()
    rows = g.answered()
    cases = g.cases_by_qid()
    rules = mods["rules"] if mods else None
    pm = mods["prompt"] if mods else None
    marker = pm.NO_GRAPH_MARKER if pm else "本次回答未使用图谱扩展"

    # E1：日期来源可核（现场用 rules.date_gate 重算；证据明写的未来日期只统计不判越界）。
    bad, beyond_total, stored_bad = [], 0, []
    for qid in sorted(rows):
        c = cases.get(qid)
        if not c:
            bad.append("%s 无装配结果，无法重算" % qid)
            continue
        dg = rules.date_gate(rows[qid]["answer_text"], c)
        beyond_total += dg["dates_beyond_cutoff_count"]
        if dg["date_unverifiable_count"]:
            bad.append("%s 越界日期 %s" % (qid, br(dg["date_unverifiable"], 3)))
        if (rows[qid].get("gates") or {}).get("date_unverifiable"):
            stored_bad.append(qid)
    g.row("E1", not bad, "日期来源可核（越界 0 次）",
          "逐题用 rules.date_gate 现场重算 30 题：越界 %d 题%s；证据明写、晚于截止时间的日期"
          "合计 %d 个（按硬约束 10 只统计、不判越界）；登记值与重算不一致 %d 题%s"
          % (len(bad), "" if not bad else "：" + br(bad, 2), beyond_total,
             len(stored_bad), "" if not stored_bad else "：" + br(stored_bad, 3)))

    # E2：图谱三方一致（graph_payload.graph_used ／ 记录 is_graph_extended ／ 答案四段呈现）。
    rec_by_aid = {}
    for r in g.records():
        aid = (r.get("answer") or {}).get("answer_id")
        rec_by_aid[aid] = r
    mism = []
    for qid in sorted(rows):
        cfg_ = mods["config"]
        _, aid = cfg_.identifiers_for(qid)
        rec = rec_by_aid.get(aid)
        used = bool((rows[qid].get("graph_payload") or {}).get("graph_used"))
        is_ext = (rec.get("answer") or {}).get("is_graph_extended") if rec else None
        secs = pm.split_answer_sections(rows[qid]["answer_text"]) if pm else {}
        sec = secs.get("知识图谱路径")
        sec_body = sec if isinstance(sec, str) else ((sec or {}).get("text") or "")
        has_path = bool(sec_body.strip()) and sec_body.strip() != marker
        triad = (int(used) == int(is_ext if is_ext is not None else -1) ==
                 (1 if has_path else 0))
        if not triad:
            mism.append("%s graph_used=%s、记录 is_graph_extended=%s、四段呈现%s"
                        % (qid, int(used), is_ext, "有路径" if has_path else "标注"))
    leak = [q for q in sorted(rows)
            if marker in (rows[q].get("body_text") or "")
            or "【" in (rows[q].get("body_text") or "")]
    g.row("E2", not mism and not leak, "图谱三方一致（30／30）",
          "三方（graph_payload.graph_used ／ 记录 is_graph_extended ／ 答案四段呈现）"
          "不一致 %d 题%s；模型正文出现系统专用字样（固定标注或【小标题】）%d 题%s"
          % (len(mism), "" if not mism else "：" + br(mism, 2), len(leak),
             "" if not leak else "：" + br(leak, 3)))

    # E3：禁词 0 命中（rules.FORBIDDEN_TERMS 现场重算）。
    hits = []
    for qid in sorted(rows):
        fg = rules.forbidden_gate(rows[qid]["answer_text"])
        if fg["forbidden_hit_count"]:
            hits.append("%s 命中 %s" % (qid, br(fg["forbidden_hits"], 3)))
    g.row("E3", not hits, "禁词 0 命中",
          "禁词表（rules.FORBIDDEN_TERMS，%d 个固定常量）逐题扫描答案全文 30 题：命中 %d 题%s"
          % (len(rules.FORBIDDEN_TERMS), len(hits),
             "" if not hits else "：" + br(hits, 2)))

    # E4：门禁不静默——正式产出里无失败题（现场重算），且生成脚本的失败路径可指认到源码行。
    failing = []
    for qid in sorted(rows):
        r = rows[qid]
        m = len(r.get("evidence") or [])
        cit = rules.citation_gate(r["answer_text"], m)
        dg = rules.date_gate(r["answer_text"], cases[qid]) if qid in cases else {
            "date_unverifiable_count": 0}
        fg = rules.forbidden_gate(r["answer_text"])
        if cit["citation_out_of_range"] or not cit["citation_marks"] \
                or dg["date_unverifiable_count"] or fg["forbidden_hit_count"]:
            failing.append(qid)
    ra_path = os.path.join(g.code8, "run_answer.py")
    ra_text = read_text(ra_path, "")
    exit_lines = [i for i, l in enumerate(ra_text.split("\n"), 1)
                  if re.search(r"return\s+1\b|sys\.exit\(1\)|非零退出|SystemExit", l)]
    gate_fail_line = line_index(ra_text, "_gate_failures")
    gs = (read_json(os.path.join(g.out_dir, "run_manifest.json")) or {}).get(
        "gate_summary_from_cycle_1") or {}
    e4_ok = (not failing and len(rows) == 30 and bool(exit_lines)
             and gs.get("passed_all") is True)
    g.row("E4", e4_ok, "门禁不静默（失败题不进入正式产出）",
          "现场重算四类门禁（引用越界／无引用／日期越界／禁词）后正式产出中的失败题 %d 题%s；"
          "run_manifest 门禁汇总 passed_all=%s（citation_out_of_range=%s、date_unverifiable=%s、"
          "forbidden=%s、graph_section_bad=%s）；生成脚本的非零退出路径见 %s 第 %s 行"
          "（门禁失败汇总 %s 第 %s 行）——本门禁遵守零调用纪律，不现场触发失败链"
          % (len(failing), "" if not failing else "：" + br(failing, 3),
             gs.get("passed_all"), gs.get("citation_out_of_range_total"),
             gs.get("date_unverifiable_total"), gs.get("forbidden_hit_total"),
             gs.get("graph_section_bad"), rel(ra_path, g.root), br(exit_lines, 3),
             rel(ra_path, g.root), gate_fail_line))

    # E5：证据正文可回链（chunk_id／doc_id 在语料里可查）。
    mods_c = mods["config"] if mods else None
    chunks = {}
    docs = {}
    if mods_c:
        try:
            chunks = mods["assemble"].load_chunks()
            docs = mods["assemble"].load_documents()
        except BaseException as exc:                  # noqa: BLE001
            g.envfail("E5 加载语料索引", str(exc))
    miss = []
    ev_total = 0
    for qid in sorted(rows):
        for e in (rows[qid].get("evidence") or []):
            ev_total += 1
            if e.get("chunk_id") not in chunks:
                miss.append("%s chunk_id=%s 不在 chunks.jsonl" % (qid, e.get("chunk_id")))
            if e.get("doc_id") not in docs:
                miss.append("%s doc_id=%s 不在 documents.jsonl" % (qid, e.get("doc_id")))
    for r in g.records():
        for e in (r.get("answer_evidence") or []):
            if e.get("chunk_id") not in chunks:
                miss.append("记录 %s chunk_id=%s 不在语料" % (r.get("answer") or {},
                                                        e.get("chunk_id")))
    g.row("E5", not miss and ev_total > 0, "证据正文可回链（缺失 0 条）",
          "trace 证据条目 %d 条 ＋ 记录层 evidence 行，逐条在 chunks.jsonl 与 documents.jsonl "
          "中查得；缺失 %d 条%s" % (ev_total, len(miss),
                                    "" if not miss else "：" + br(miss, 3)))


# ---------------------------------------------------------------------------
# F 组：记录层与历史问答
# ---------------------------------------------------------------------------
def group_f(g):
    g.group("F、《21》第八节 F 组（第 26～29 行：F1 三表字段覆盖 ／ F2 联合唯一 ／ F3 会话隔离 ／ "
            "F4 回看不重渲染路径）")
    mods = g.load_modules()
    p21 = read_text(g.p("阶段08-智能问答系统", "21-第8阶段任务书（智能问答系统）.md"), "")
    records = g.records()

    # F1：逐条含硬约束 13 的全部字段名，无缺、无多余业务字段；且 history.py 的字段元组同源。
    hist = mods["history"] if mods else None
    tuple_bad = []
    for key in ("question", "answer", "answer_evidence"):
        declared = tuple(getattr(hist, "%s_FIELDS" % key.upper(), ()) ) if hist else ()
        if declared != tuple(ROW13_FIELDS[key]):
            tuple_bad.append("history.%s_FIELDS=%s ≠ 硬约束 13" % (key.upper(), declared))
    missing, extra = [], []
    for i, r in enumerate(records, 1):
        for key in ("question", "answer", "answer_evidence"):
            obj = r.get(key)
            if key == "answer_evidence":
                rows_ = obj or []
                for j, e in enumerate(rows_, 1):
                    gap = set(ROW13_FIELDS[key]) - set(e)
                    sur = set(e) - set(ROW13_FIELDS[key])
                    if gap or sur:
                        missing.append("第%d行 answer_evidence[%d] 缺 %s" % (i, j, br(gap, 3)))
                        extra.append("第%d行 answer_evidence[%d] 多 %s" % (i, j, br(sur, 3)))
            else:
                obj = obj or {}
                gap = set(ROW13_FIELDS[key]) - set(obj)
                sur = set(obj) - set(ROW13_FIELDS[key])
                if gap:
                    missing.append("第%d行 %s 缺 %s" % (i, key, br(gap, 3)))
                if sur:
                    extra.append("第%d行 %s 多 %s" % (i, key, br(sur, 3)))
    top_bad = [i for i, r in enumerate(records, 1) if set(r) != {"question", "answer",
                                                                 "answer_evidence"}]

    # F1 补充（全面审查 B-03／C-05）：`evidence_type` 的**取值**同样是字段覆盖的一部分。
    # 旧实现只比字段名、不看值，把某条改成表外取值仍判 [OK]。这里做三件事：
    #   ① 逐条断言 `evidence_type` ∈ 四类之一（表外取值即失败）；
    #   ② 由 **documents.jsonl 的 category ＋ 是否图谱侧新增块独立重算**期望标签并逐条比对；
    #   ③ 统计并打印四类各自的计数（让「新闻来源恒为 0」这类口径偏差可见）。
    ev_type_bad, ev_type_counts = [], {t: 0 for t in EVIDENCE_TYPE_SET}
    docs_idx, graph_side_by_qid = {}, {}
    if mods:
        try:
            docs_idx = mods["assemble"].load_documents()
        except BaseException as exc:                  # noqa: BLE001 环境失败而非内容失败
            g.envfail("F1 加载 documents.jsonl", str(exc))
    # 「图谱侧新增块」优先取现场重算的装配结果（`evidence[i].from_graph`）；装配不可用则退回
    # 第 7 阶段 trace 的 `graph_evidence_in_final`（assemble 的同一判据来源）。按题分组，
    # 避免「同一块在这题是图谱侧、在那题不是」被跨题并集误判。
    for qid, c in (g.cases_by_qid() or {}).items():
        graph_side_by_qid[qid] = {e["chunk_id"] for e in c["evidence"] if e.get("from_graph")}
    if not graph_side_by_qid:
        for qid, srow in (g.stage7_trace() or {}).items():
            graph_side_by_qid[qid] = set(srow.get("graph_evidence_in_final") or [])
    # 题号（整数）→ 题集 qid，作为记录 `question_id` 与装配 case 的桥（位宽无关）。
    qid_by_num = {}
    for q in (g.questions() or []):
        num = _question_number(q.get("qid"))
        if num is not None:
            qid_by_num[num] = q.get("qid")
    for i, r in enumerate(records, 1):
        qid = qid_by_num.get(_question_number((r.get("question") or {}).get("question_id")))
        gside = graph_side_by_qid.get(qid, set())
        for j, e in enumerate((r.get("answer_evidence") or []), 1):
            lab = e.get("evidence_type")
            if lab not in ev_type_counts:
                ev_type_bad.append("第%d行 answer_evidence[%d] 表外取值 %r" % (i, j, lab))
                continue
            ev_type_counts[lab] += 1
            cat = (docs_idx.get(e.get("doc_id")) or {}).get("category")
            exp = expected_evidence_type(cat, e.get("chunk_id") in gside)
            if lab != exp:
                ev_type_bad.append("第%d行 answer_evidence[%d] chunk=%s 记 %r ≠ 重算 %r"
                                   "（category=%r，图谱侧=%s）"
                                   % (i, j, e.get("chunk_id"), lab, exp, cat,
                                      e.get("chunk_id") in gside))
    f1_ok = (not missing and not extra and not tuple_bad and not top_bad and not ev_type_bad)
    g.row("F1", f1_ok, "三表字段覆盖（逐条：无缺、无多余业务字段）",
          "qa_records.jsonl %d 条；字段缺 %d 处、多 %d 处%s；顶层键异常 %d 条%s；"
          "history.py 三表元组与硬约束 13 一致=%s；evidence_type 取值/重算不符 %d 处%s；"
          "四类计数=%s"
          % (len(records), len(missing), len(extra),
             "" if not (missing or extra) else "：" + br(missing + extra, 3),
             len(top_bad), "" if not top_bad else "：" + br(top_bad, 3), not tuple_bad,
             len(ev_type_bad), "" if not ev_type_bad else "：" + br(ev_type_bad, 3),
             json.dumps(ev_type_counts, ensure_ascii=False)))

    # F2：同一 answer_id 下 chunk_id 不重复；rank 为 1..m 连续。
    f2 = []
    for i, r in enumerate(records, 1):
        ae = r.get("answer_evidence") or []
        aid = (r.get("answer") or {}).get("answer_id")
        cids = [e.get("chunk_id") for e in ae]
        dup = sorted({c for c in cids if cids.count(c) > 1})
        ranks = sorted(e.get("rank") for e in ae)
        if dup:
            f2.append("第%d行 %s chunk_id 重复 %s" % (i, aid, br(dup, 3)))
        if ranks != list(range(1, len(ae) + 1)):
            f2.append("第%d行 %s rank=%s 非 1..%d 连续" % (i, aid, br(ranks, 4), len(ae)))
    all_aids = [(r.get("answer") or {}).get("answer_id") for r in records]
    g.row("F2", not f2 and len(set(all_aids)) == len(all_aids),
          "联合唯一（(answer_id, chunk_id) 不重复、rank 1..m 连续）",
          "%d 条记录、answer_id 唯一=%s；违反 %d 处%s"
          % (len(records), len(set(all_aids)) == len(all_aids), len(f2),
             "" if not f2 else "：" + br(f2, 3)))

    # F3：会话隔离（构造两个 session_id 的记录后按会话查询，双方互不可见）。
    if not mods:
        g.row("F3", False, "会话隔离（构造用例自证）", "环境失败：模块不可加载")
    else:
        cases = g.cases_by_qid()
        hist_ = mods["history"]
        prompt_ = mods["prompt"]
        cfg_ = mods["config"]
        qids = sorted(cases)[:2]
        if len(qids) < 2:
            g.row("F3", False, "会话隔离（构造用例自证）", "装配结果不足两题，无法构造")
        else:
            ask = "2026-09-29T12:00:00+08:00"
            built = []
            for i, qid in enumerate(qids):
                c = cases[qid]
                body = "门禁构造用例正文，引用 [证据1]；日期 %s。" % c["data_cutoff_time"][:10]
                answer_text = prompt_.compose_answer(
                    body=body, evidence=c["evidence"], graph_payload=c["graph_payload"],
                    dataset_version=c["dataset_version"],
                    data_cutoff_time=c["data_cutoff_time"], time_note=c["time_note"])
                qid_num, aid = cfg_.identifiers_for(qid)
                built.append(hist_.build_record(
                    c, {"answer_text": answer_text, "model": {"requested": aid,
                                                              "returned": aid}},
                    session_id=("S-8A" if i == 0 else "S-8B"), question_id=qid_num,
                    answer_id=aid, ask_time=ask))
            a = hist_.query_history(built, "S-8A")
            b = hist_.query_history(built, "S-8B")
            a_ids = {(r["answer"].get("answer_id")) for r in a}
            b_ids = {(r["answer"].get("answer_id")) for r in b}
            cross = a_ids & b_ids
            ok = (len(a) == 1 and len(b) == 1 and not cross
                  and len(a) + len(b) == len(built))
            g.row("F3", ok, "会话隔离（构造用例自证）",
                  "构造 2 条记录（S-8A／S-8B，未调用模型）：query_history(S-8A) 得 %s、"
                  "query_history(S-8B) 得 %s、交集 %s（应为空）；两会话之和 %d ＝ 构造数 %d"
                  % (br(a_ids, 3), br(b_ids, 3), br(cross, 3) if cross else "∅",
                     len(a) + len(b), len(built)))

    # F4：回看只返回三表内容，不含路径重建结果。
    if not records:
        g.row("F4", False, "回看不重渲染路径", "读不到 qa_records.jsonl")
    else:
        hist_ = mods["history"]
        row0 = records[0]
        aid = (row0.get("answer") or {}).get("answer_id")
        rev = hist_.review(records, aid)
        keys = set(rev)
        ans_keys = set(rev.get("answer") or {})
        stored_gp = (row0.get("answer") or {}).get("graph_path")
        same_text = rev.get("answer", {}).get("graph_path") == stored_gp
        forbidden_keys = {"graph_payload", "graph_path_text", "graph_rendered",
                          "graph_path_view", "rendered_path", "nodes", "path_text"}
        leak_keys = sorted(k for k in (keys | ans_keys) if k in forbidden_keys
                           or "render" in k.lower())
        notfound = hist_.review(records, "A-999").get("found")
        ok = (rev.get("found") is True and keys == {"found", "question", "answer",
                                                    "answer_evidence"}
              and not leak_keys and same_text and notfound is False)
        g.row("F4", ok, "回看不重渲染路径（只回 graph_path 原文）",
              "review(%s) 顶层键=%s（应为 found／question／answer／answer_evidence）；"
              "answer 键=%s；graph_path 与记录原文逐字符相同=%s；路径重建类键 %d 个%s；"
              "review(不存在的 id).found=%s"
              % (aid, sorted(keys), sorted(ans_keys), same_text, len(leak_keys),
                 "" if not leak_keys else "：" + br(leak_keys, 3), notfound))


# ---------------------------------------------------------------------------
# G 组：复现性与门禁
# ---------------------------------------------------------------------------
def group_g(g):
    g.group("G、《21》第八节 G 组（第 30～35 行：G1 零调用跑通 ／ G2 装配逐字节一致 ／ "
            "G3 模型重复一致率 ／ G4 run_manifest 完整 ／ G5 跨文档核验 ／ G6 专项验收）")

    # G1：STAGE8_FORBID_MODEL_CALLS=1 下 `run_answer.py --dry-run` 退出码 0 且调用计数为 0。
    if g.static_unrun("G1", "零调用跑通（--dry-run，退出码 0、调用计数 0）",
                      "static 档不跑子进程"):
        pass
    else:
        run_py = os.path.join(g.code8, "run_answer.py")
        tmp = tempfile.mkdtemp(prefix="stage8_dryrun_")
        env = dict(os.environ)
        removed = sorted(n for n in env if CRED_PAT.search(n))
        for n in removed:
            env.pop(n, None)
        env["PYTHONIOENCODING"] = "utf-8"
        env["STAGE8_FORBID_MODEL_CALLS"] = "1"
        argv = [sys.executable, run_py, "--dry-run", "--out-dir", tmp]
        try:
            proc = subprocess.run(argv, cwd=g.root, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", env=env, timeout=1800)
            code, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
        except (OSError, subprocess.SubprocessError) as exc:
            code, out, err = -1, "", str(exc)
        m = re.search(r"模型调用次数\s*=\s*(\d+)", out)
        calls = int(m.group(1)) if m else None
        wrote = [n for n in (os.listdir(tmp) if os.path.isdir(tmp) else [])]
        if not ARGS.keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)
        if code == -1:
            g.envfail("G1 子进程不可用", err)
        g.row("G1", code == 0 and calls == 0, "零调用跑通（--dry-run，退出码 0、调用计数 0）",
              "python 代码\\问答\\run_answer.py --dry-run（STAGE8_FORBID_MODEL_CALLS=1）："
              "退出码=%d、自报模型调用次数=%s、临时 out-dir 产物 %d 个；stderr 末行=%r"
              % (code, calls, len(wrote), (err.strip().splitlines() or [""])[-1][:80]))

    # G2：两次运行 Prompt 文本 SHA-256 相同（30／30）——现场重算 ＋ 产物登记 ＋ run_manifest。
    if g.static_unrun("G2", "装配逐字节一致（30／30）", "static 档不重算装配"):
        pass
    else:
        cases = g.cases_by_qid()
        cases2 = g.cases_by_qid(1)
        rm = read_json(os.path.join(g.out_dir, "run_manifest.json")) or {}
        det = rm.get("assembly_determinism") or {}
        by_qid = det.get("prompt_sha256_by_qid") or {}
        bad = []
        for qid in sorted(cases):
            a = cases[qid]["prompt"]["sha256"]
            b = cases2[qid]["prompt"]["sha256"]
            c = by_qid.get(qid)
            t = (g.answered().get(qid) or {}).get("prompt_sha256")
            if not (a == b == t == c):
                bad.append("%s 重算1=%s／重算2=%s／trace=%s／run_manifest=%s"
                           % (qid, a[:10], b[:10], (t or "")[:10], (c or "")[:10]))
        g.row("G2", not bad and len(cases) == 30, "装配逐字节一致（30／30）",
              "四方一致（现场两次装配／answer_trace 登记／run_manifest 逐题表）比对 %d 题、"
              "不一致 %d 题%s；run_manifest 自报 identical=%s、repeats=%s、model_calls=%s"
              % (len(cases), len(bad), "" if not bad else "：" + br(bad, 2),
                 det.get("identical"), det.get("repeats"), det.get("model_calls")))

    # G3：模型重复一致率——**只登记数值，不作通过判据**（《21》第八节 G3）。
    rm = read_json(os.path.join(g.out_dir, "run_manifest.json")) or {}
    rep = rm.get("model_output_repeatability") or {}
    rate = rep.get("rate")
    ident = rep.get("identical")
    diff = rep.get("differing_qids") or []
    consistent = (isinstance(rate, (int, float)) and 0 <= rate <= 1
                  and isinstance(ident, int) and ident + len(diff) == rep.get("questions"))
    g.row("G3", bool(rep) and consistent, "模型重复一致率（仅登记数值，不作判据）",
          "run_manifest.model_output_repeatability：rate=%s（identical=%s／questions=%s，"
          "两次运行「回答」正文逐字符相同）；本行**只登记数值**，按《21》第八节 G3 "
          "「数值如实报告，不作为通过／失败判据」，不参与任何通过判定" % (rate, ident,
                                                                    rep.get("questions")))

    # G4：run_manifest 完整（复跑命令、输入指纹、六个产出 SHA-256、调用次数）——并现场重算 SHA。
    rc = rm.get("reproduce_commands") or []
    fp = rm.get("input_fingerprints") or {}
    arts = rm.get("artifacts_sha256") or {}
    mc = rm.get("model_calls") or {}
    # `selection_matrix`／`selection_decision` 会被选型复检（`model_selection.py --recheck`）
    # 重写。按裁定，本门禁**不依赖这两份文件的数值**（只要求存在且可解析），故它们的产物
    # 指纹若对不上只**登记为注记**，不计入本行失败；其余四个产物按硬判据复算。
    VOLATILE_ART = ("selection_matrix", "selection_decision")
    art_bad, art_volatile = [], []
    for key, row in sorted(arts.items()):
        path = resolve_under_root(row.get("path"), g.root)
        if not path or not os.path.isfile(path):
            (art_volatile if any(v in key for v in VOLATILE_ART) else art_bad).append(
                "%s 文件在本根下不存在（登记 %s）" % (key, row.get("path")))
            continue
        live_sha = sha256_file(path)
        live_bytes = os.path.getsize(path)
        if live_sha != row.get("sha256") or live_bytes != row.get("bytes"):
            msg = "%s 登记 %s／重算 %s" % (key, (row.get("sha256") or "")[:12], live_sha[:12])
            if any(v in key for v in VOLATILE_ART):
                art_volatile.append(msg)
            else:
                art_bad.append(msg)
    g.row("G4", len(rc) >= 1 and len(fp.get("files") or []) >= 10 and len(arts) >= 6
          and mc.get("total") is not None and not art_bad,
          "run_manifest 完整（复跑命令／输入指纹／六个产出 SHA-256／调用次数）",
          "reproduce_commands=%d 条；input_fingerprints=%d 个文件（recomputed_mismatched=%s）；"
          "artifacts_sha256=%d 个（现场重算不一致 %d 个%s）；model_calls.total=%s"
          % (len(rc), len(fp.get("files") or []), fp.get("recomputed_mismatched"),
             len(arts), len(art_bad), "" if not art_bad else "：" + br(art_bad, 3),
             mc.get("total")))
    if art_volatile:
        g.note("G4 注记（选型复检在写，不作判据）",
               "；".join(art_volatile) + "——按裁定，本门禁只要求这两份文件存在且可解析，"
               "不依赖其数值")

    # G5：跨文档核验（镜像根无全工作区时不成立，记未执行）。
    if g.static_unrun("G5", "跨文档核验（--strict-citations 退出码 0）",
                      "static 档不跑子进程"):
        pass
    elif not os.path.isdir(g.p("阶段02-文献调研与开题")):
        g.row_unrun("G5", "跨文档核验（--strict-citations 退出码 0）",
                    "根目录 %s 下无 阶段02-文献调研与开题（镜像根不含全工作区），"
                    "本项在镜像里不成立" % g.root)
    else:
        tool = g.p("工具", "跨文档核验.py")
        argv = [sys.executable, tool, "--strict-citations"]
        try:
            proc = subprocess.run(argv, cwd=g.root, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=1800)
            code, tail = proc.returncode, (proc.stdout or "").strip().splitlines()
        except (OSError, subprocess.SubprocessError) as exc:
            code, tail = -1, [str(exc)]
        g.row("G5", code == 0, "跨文档核验（--strict-citations 退出码 0）",
              "python 工具\\跨文档核验.py --strict-citations：退出码=%d；末行=%r"
              % (code, (tail or [""])[-1][:100]))

    # G6：专项验收（full 档 39 行全部通过）——在 summary 阶段判定（见 main）。
    return


def group_h(g):
    g.group("H、《21》第八节 H 组（第 36～39 行：H1 《22》九节齐全 ／ H2 读数有来源 ／ "
            "H3 限制继承 ／ H4 非目标未被越界）")
    p22 = g.p("阶段08-智能问答系统", "22-第8阶段产出文档（智能问答系统）.md")
    t22 = read_text(p22)
    p19 = read_text(os.path.join(g.root, "阶段07-RAG检索系统",
                                 "19-第7阶段产出文档（RAG检索系统）.md"), "")
    missing_note = "《22》尚未落盘：%s" % rel(p22, g.root)

    # H1：9 个必备小节的标题逐字存在且顺序一致。
    if t22 is None:
        g.row("H1", False, "《22》九节齐全（9 个必备小节的标题逐字存在且顺序一致）",
              missing_note + "；判据＝《21》第八节 H1，缺文档即 FAIL（不放宽、不 skip）")
    else:
        headings = [l.strip().lstrip("#").strip() for l in t22.split("\n")
                    if l.strip().startswith("#")]
        pos, cursor, bad = [], 0, []
        for sec in DOC22_SECTIONS:
            found = None
            for i in range(cursor, len(headings)):
                if headings[i].startswith(sec):
                    found = i
                    break
            if found is None:
                bad.append("缺「%s」（其后未再出现）" % sec)
            else:
                pos.append(found)
                cursor = found + 1
        g.row("H1", not bad and len(pos) == 9, "《22》九节齐全（9 个必备小节的标题逐字存在且"
              "顺序一致）",
              "必备小节 %d 个；按序命中 %d 个%s；《21》第 137 行 给出的标题清单即判据"
              % (len(DOC22_SECTIONS), len(pos),
                 "" if not bad else "：" + br(bad, 3)))

    # H2：每处数字都给出源文件或复算命令。
    if t22 is None:
        g.row("H2", False, "读数有来源（每处数字给出源文件或复算命令）",
              missing_note + "；判据＝《21》第八节 H2")
    else:
        marker_pat = re.compile(r"(\.jsonl|\.json|\.csv|\.md|\.py|python\s|《|来源|复算|命令)")
        offenders = []
        for i, line in enumerate(t22.split("\n"), 1):
            if not re.search(r"\d", line) or line.strip().startswith("|"):
                continue
            if not marker_pat.search(line):
                offenders.append("第 %d 行：%s" % (i, line.strip()[:60]))
        g.row("H2", not offenders, "读数有来源（每处数字给出源文件或复算命令）",
              "逐行扫描带数字的正文行：缺来源标记 %d 行%s（判据为机检启发式：该行须含文件名／"
              "python 命令／《文档》号／「来源」「复算」「命令」之一）"
              % (len(offenders), "" if not offenders else "：" + br(offenders, 3)))

    # H3：第 8 节继承《19》第 8 节的已知限制（至少 5 条逐条引用）。
    if t22 is None:
        g.row("H3", False, "限制继承（《22》第 8 节继承《19》第 8 节，至少 5 条逐条引用）",
              missing_note + "；判据＝《21》第八节 H3")
    else:
        sec19 = ""
        m = re.search(r"##\s*已知限制与证据不足清单\s*\n(.*?)(?=\n###\s|\n##\s|\Z)", p19, re.S)
        if m:
            sec19 = m.group(1)
        items19 = [int(x) for x in re.findall(r"^\s*(\d{1,2})\.\s+\*\*", sec19, re.M)]
        refs = set()
        for n in re.findall(r"《19》[^\n。]{0,30}?第\s*(\d{1,2})\s*条", t22):
            refs.add(int(n))
        # 退一步：第 8 节内部若以「《19》第 8 节 第 n 条」形式引用
        for n in re.findall(r"第\s*8\s*节[^\n。]{0,30}?第\s*(\d{1,2})\s*条", t22):
            refs.add(int(n))
        valid = {r for r in refs if r in items19}
        g.row("H3", len(valid) >= 5, "限制继承（《22》第 8 节继承《19》第 8 节，至少 5 条逐条引用）",
              "《19》第 8 节 编号条目 %d 条；《22》中逐条引用且编号在范围内的 %d 条%s"
              % (len(items19), len(valid), "" if len(valid) >= 5 else "（不足 5 条）"))

    # H4：非目标未被越界（本阶段自己的交付范围内无前端／接口／DDL 产物；git status 无 阶段09-）。
    fe, ddl, api = [], [], []
    for base in (g.stage8, g.code8):
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != ".git"]
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                low = fn.lower()
                if low.endswith(FRONTEND_EXT):
                    fe.append(rel(p, g.root))
                if low.endswith(DDL_EXT):
                    ddl.append(rel(p, g.root))
                if low.endswith(".py"):
                    for i, line in enumerate(read_text(p, "").split("\n"), 1):
                        if API_IMPORT_PAT.match(line):
                            api.append("%s:%d %s" % (rel(p, g.root), i, line.strip()[:40]))
    stage09 = [d for d in os.listdir(g.root) if d.startswith("阶段09")
               and os.path.isdir(g.p(d))]
    ok_git, lines, gdetail = g.git_status()
    git09 = [l for l in lines if "阶段09" in l]
    # 全仓库 *.sql／*.ddl 只在 A4 判；此处按《21》H4 的范围（本阶段交付物）判定，并在
    # 输出里如实注明范围，避免把既有的图表与文献 HTML 误判成第 8 阶段的前端产物。
    #
    # **时点限定（2026-09-29，第 9 阶段开工时按《24-第9阶段任务书（前后端系统集成）》
    # 第4.7节 的登记调整）**：`阶段09-*` 目录与 git status 里的 `阶段09-` 条目是**第 8 阶段
    # 收口时点**的判据——它要守的是「第 8 阶段没越界做第 9 阶段的事」。第 9 阶段一经开工，
    # 该目录的存在就是**预期状态**，再把它判失败等于用一条会随时点失效的判据否掉后续阶段。
    # 故改为：仅当 `阶段09-前后端系统集成\24-第9阶段任务书（前后端系统集成）.md`（第 9 阶段
    # 开工的标志文件）**不存在**时，`阶段09-*` 才计入失败；存在则记 note 并说明。判据不放宽：
    # 「第 8 阶段交付范围内无前端／接口／DDL 产物」这一条**一字未动**，仍逐文件扫描并硬判。
    p9_marker = g.p(os.path.join("阶段09-前后端系统集成",
                                 "24-第9阶段任务书（前后端系统集成）.md"))
    stage9_started = os.path.isfile(p9_marker)
    ok_h4 = (not fe) and (not ddl) and (not api) and (stage9_started or not stage09) \
        and (stage9_started or not git09)
    g.row("H4", ok_h4,
          "非目标未被越界（第 8 阶段交付范围内无前端／接口／DDL 产物；"
          "阶段09- 的出现按开工标志作时点限定）",
          "扫描范围＝阶段08-智能问答系统\\ 与 代码\\问答\\（本阶段交付范围）：前端类 %d 个%s、"
          "DDL 类 %d 个%s、接口框架 import %d 处%s；根目录 阶段09-* 目录 %d 个；"
          "git status 中 阶段09- 条目 %d 条（git %s）；第 9 阶段开工标志＝%s"
          % (len(fe), "" if not fe else "：" + br(fe, 3), len(ddl),
             "" if not ddl else "：" + br(ddl, 3), len(api), "" if not api else "：" + br(api, 3),
             len(stage09), len(git09), gdetail,
             "存在（按预期，不计失败）" if stage9_started else "不存在（按收口时点判定）"))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def term_discipline(g):
    """术语纪律自检（任务要求 9）：FAISS 一律写「向量索引」；不出现被禁的四字连写术语；
    不声称部署了图数据库服务。只打印注记，**不占《21》第八节 的行**（故不影响 39／39 计数）。
    """
    banned = "向量" + "数据库"          # 拼串构造：本文件源码里不出现该连写术语本身
    neoj = "Neo" + "4j"
    claim_pat = re.compile(r"(部署|已启动|已运行|运行中|已连上|已连接|服务已|生产环境)")
    # 否定/禁止的措辞（「不得声称部署」「不部署」「未部署」）是**合规**写法，先排掉，
    # 否则把《21》的硬约束本身判成违规。
    neg_pat = re.compile(r"(不得|不部署|未部署|没有部署|不声称|不写|不连|禁止|无需|不要)")
    # 本脚本要**指名**这些术语才能自检（「FAISS 一律写『向量索引』」），故本脚本只参与
    # 「被禁连写术语」一项；FAISS／图数据库服务两项只在**被验收的文档与代码**上判定。
    audit = [("代码\\问答\\README.md", os.path.join(g.code8, "README.md"))]
    for name in sorted(os.listdir(g.code8)) if os.path.isdir(g.code8) else []:
        if name.endswith(".py"):
            audit.append(("代码\\问答\\" + name, os.path.join(g.code8, name)))
    for extra in ("21-第8阶段任务书（智能问答系统）.md",
                  "22-第8阶段产出文档（智能问答系统）.md"):
        audit.append(("阶段08-智能问答系统\\" + extra, os.path.join(g.stage8, extra)))

    banned_hits, faiss_raw, faiss_bare, neoj_claims = [], [], [], []
    scanned = 0
    for label, path in dict([("本脚本", SCRIPT)] + audit).items():
        text = read_text(path)
        if text is None:
            continue
        scanned += 1
        for i, line in enumerate(text.split("\n"), 1):
            if banned in line:
                banned_hits.append("%s 第 %d 行" % (label, i))
            if label == "本脚本":
                continue
            if "FAISS" in line.upper():
                faiss_raw.append("%s 第 %d 行" % (label, i))
                if "向量索引" not in line:
                    faiss_bare.append("%s 第 %d 行：%s" % (label, i, line.strip()[:60]))
            if neoj in line and claim_pat.search(line) and not neg_pat.search(line):
                neoj_claims.append("%s 第 %d 行：%s" % (label, i, line.strip()[:60]))
    used = sum(1 for _l, p in audit if os.path.isfile(p)
               and "向量索引" in (read_text(p) or ""))
    g.note("术语纪律自检（任务要求 9，不占 39 行）",
           "扫描 %d 个文件（本脚本只查被禁连写术语；其余 %d 个为被验收的文档与代码）："
           "被禁连写术语命中 %d 处%s；写「向量索引」的被验收文件 %d 个；"
           "FAISS 原样写法 %d 处（同句已写「向量索引」的按合规计，仍原样单用的 %d 处%s）；"
           "图数据库服务声称 %d 处%s（否定／禁止措辞不计）"
           % (scanned, scanned - 1, len(banned_hits),
              "" if not banned_hits else "：" + br(banned_hits, 3), used, len(faiss_raw),
              len(faiss_bare), "" if not faiss_bare else "：" + br(faiss_bare, 3),
              len(neoj_claims), "" if not neoj_claims else "：" + br(neoj_claims, 3)))


def run_body(g):
    g.load_modules()
    term_discipline(g)
    group_a(g)
    group_b(g)
    group_c(g)
    group_d(g)
    group_e(g)
    group_f(g)
    group_g(g)
    group_h(g)


def finish(g, quiet=False):
    """G6、计数自洽与总结论。返回退出码。"""
    ids = [r[0] for r in g.rows]
    expected_ids = []
    for letter in "ABCDEFGH":
        for i in range(1, EXPECTED_ROW_GROUPS[letter] + 1):
            expected_ids.append("%s%d" % (letter, i))
    # G6（专项验收）只能在其余 38 行落定后才判定，故它按设计排在末位——此处 ids 尚未含
    # G6，比对的即是「A1…H4 逐位（不含 G6）」。
    expected_order = [x for x in expected_ids if x != "G6"]
    struct_ok = (ids == expected_order)
    executed = sum(1 for _g, st in g.rows if st in ("OK", "FAIL"))
    passed = sum(1 for _g, st in g.rows if st == "OK")

    # G6：full 档 39 行全部通过。
    if g.profile == "static":
        g.row_unrun("G6", "专项验收（full 档 39 行全部通过）", "static 档不判定收口结论")
    else:
        others = [(gid, st) for gid, st in g.rows if gid != "G6"]
        g.row("G6", all(st == "OK" for _gid, st in others) and struct_ok
              and len(others) == EXPECTED_TOTAL_ROWS - 1,
              "专项验收（full 档 39 行全部通过）",
              "本档 39 行中除 G6 外通过 %d／%d；行结构自洽=%s（%s）"
              % (sum(1 for _gid, st in others if st == "OK"), len(others), struct_ok,
                 "行序＝A1…H4 逐位一致（G6 按设计末位）" if struct_ok else
                 "实测行序：%s" % br(ids, 40)))

    g.out("")
    g.out("=" * 78)
    g.out("  组／行映射：《21》第八节 A 组 A1～A4 ／ B 组 B1～B4 ／ C 组 C1～C6 ／ "
          "D 组 D1～D6 ／ E 组 E1～E5 ／ F 组 F1～F4 ／ G 组 G1～G6 ／ H 组 H1～H4")
    per_group = {}
    for gid, st in g.rows:
        per_group.setdefault(gid[0], []).append((gid, st))
    g.out("  分组计数：" + "；".join(
        "%s %d／%d" % (k, sum(1 for _i, st in v if st in ("OK", "FAIL")),
                       EXPECTED_ROW_GROUPS[k]) for k, v in sorted(per_group.items())))
    executed = sum(1 for _g, st in g.rows if st in ("OK", "FAIL"))
    passed = sum(1 for _g, st in g.rows if st == "OK")
    failed = sum(1 for _g, st in g.rows if st == "FAIL")
    unrun = len(g.unrun)
    skipped = len(g.skips)
    g.out("  最终：计划行 %d 行；已执行 %d／%d、通过 %d、失败 %d、未执行 %d、SKIP %d；"
          "环境／链上失败 %d" % (EXPECTED_TOTAL_ROWS, executed, EXPECTED_TOTAL_ROWS,
                             passed, failed, unrun, skipped, len(g.env_fails)))
    if not struct_ok:
        g.out("  [FAIL] 计数自洽：实测行序与《21》第八节 的 A1…H4 不一致：%s" % br(ids, 45))
    if g.profile == "static":
        g.out("结论：--profile static 有 %d 行未执行（见上方 [UNRUN]），不得作为收口判定；"
              "退出码 2。" % unrun)
    elif g.env_fails:
        g.out("结论：环境／链上失败（非内容失败）%d 项，不能与真缺陷混判；退出码 1。"
              % len(g.env_fails))
        for lab, det in g.env_fails:
            g.out("  - %s  %s" % (lab, det))
    elif g.fails:
        g.out("结论：存在 %d 项内容失败（通过 %d 行、未执行 %d、SKIP %d）："
              % (len(g.fails), passed, unrun, skipped))
        for gid, label, det in g.fails:
            g.out("  - %s %s  %s" % (gid, label, det))
    else:
        g.out("结论：39 行全部通过（通过 %d 行／计划 39 行，未执行 0、SKIP 0）。"
              "第 8 阶段专项验收通过，退出码 0。" % passed)
    g.out("=" * 78)

    if ARGS.emit_json:
        payload = {"rows": [{"id": gid, "status": st} for gid, st in g.rows],
                   "fails": [gid for gid, _l, _d in g.fails],
                   "unrun": [gid for gid, _l, _d in g.unrun],
                   "env_fails": [lab for lab, _d in g.env_fails],
                   "struct_ok": struct_ok}
        with open(ARGS.emit_json, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    if g.profile == "static":
        return 2
    return 1 if (g.fails or g.env_fails) else 0


# ---------------------------------------------------------------------------
# 负向校准（--selftest）
# ---------------------------------------------------------------------------
# 镜像需要的最小文件集：10 个只读输入 ＋ 代码 ＋ 产出 ＋ 判据文档 ＋ 生成脚本。
MIRROR_FILES = (
    # `.gitignore` 要一起带进镜像：A3／H4 依赖 `git status --porcelain`，而仓库根
    # `.gitignore` 里的 `__pycache__/`／`*.py[cod]` 正是让「导入镜像模块产生的字节码缓存」
    # 不进入 status 的原因；少了它，镜像里 A3 会被 `代码/检索/__pycache__/` 误判。
    ".gitignore",
    "代码/检索/config.py",
    "代码/问答/config.py", "代码/问答/rules.py", "代码/问答/prompt.py",
    "代码/问答/assemble.py", "代码/问答/answer.py", "代码/问答/history.py",
    "代码/问答/run_answer.py", "代码/问答/model_selection.py", "代码/问答/check_inputs.py",
    "代码/问答/README.md",
    "阶段07-RAG检索系统/检索产出/per_question_trace.jsonl",
    "阶段07-RAG检索系统/检索产出/input_manifest.json",
    "阶段07-RAG检索系统/检索产出/run_manifest.json",
    "阶段07-RAG检索系统/预实验问题集/questions.jsonl",
    "阶段05-数据准备/数据集/v2.1/clean/documents.jsonl",
    "阶段05-数据准备/数据集/v2.1/chunks/chunks.jsonl",
    "阶段05-数据准备/数据集/v2.1/meta/dataset.json",
    "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_3/nodes.csv",
    "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_3/edges.csv",
    "阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_3/graph_stats.json",
    "阶段08-智能问答系统/21-第8阶段任务书（智能问答系统）.md",
    # 《22》必须一起带进镜像：H1／H2／H3 判的就是它。少了它，H1／H2／H3 在**原样副本**上就
    # 会 FAIL，「正向对照」失去意义（原本「3 个反例」里没有一条能覆盖 H 组；H 组的正控也是
    # 空的）——加上它，正向对照才真的能证明 H 组判据在「文档齐全」时判 [OK]。
    "阶段08-智能问答系统/22-第8阶段产出文档（智能问答系统）.md",
    "阶段08-智能问答系统/问答产出/input_manifest.json",
    "阶段08-智能问答系统/问答产出/prompt_snapshot.json",
    "阶段08-智能问答系统/问答产出/answer_trace.jsonl",
    "阶段08-智能问答系统/问答产出/qa_records.jsonl",
    "阶段08-智能问答系统/问答产出/run_manifest.json",
    "阶段08-智能问答系统/问答产出/selection_matrix.jsonl",
    "阶段08-智能问答系统/问答产出/selection_decision.json",
    "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md",
    "阶段07-RAG检索系统/19-第7阶段产出文档（RAG检索系统）.md",
    "00-项目总览与索引.md",
    "02-项目执行总控文档.md",
)
ANSWER_TRACE_REL = "阶段08-智能问答系统/问答产出/answer_trace.jsonl"
QA_RECORDS_REL = "阶段08-智能问答系统/问答产出/qa_records.jsonl"


def build_mirror(tag):
    tmp = tempfile.mkdtemp(prefix="stage8_accept_%s_" % tag)
    copied = missing = 0
    for relp in MIRROR_FILES:
        src = os.path.join(REPO_ROOT, relp.replace("/", os.sep))
        if not os.path.isfile(src):
            missing += 1
            continue
        dst = os.path.join(tmp, relp.replace("/", os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1
    # 让 A3／H4 能在镜像里真跑：把镜像初始化成一个已提交的 git 仓库。
    git_ok = init_git(tmp)
    return tmp, copied, missing, git_ok


def init_git(root):
    def run(*args):
        return subprocess.run(["git", "-c", "user.name=acceptance-gate",
                               "-c", "user.email=gate@local", "-c", "commit.gpgsign=false"]
                              + list(args), cwd=root, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900)
    try:
        if run("init", "-q").returncode != 0:
            return False
        run("add", "-A")
        if run("commit", "-q", "-m", "mirror").returncode != 0:
            return False
        return run("status", "--porcelain").returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def rewrite_jsonl(path, fn):
    rows = [json.loads(l) for l in read_text(path, "").split("\n") if l.strip()]
    fn(rows)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def tamper_evidence_order(root):
    """反例①：颠倒 PE-01 的 evidence 顺序（应触发 C3）。"""
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-01":
                r["evidence"] = list(reversed(r.get("evidence") or []))
    rewrite_jsonl(os.path.join(root, ANSWER_TRACE_REL.replace("/", os.sep)), fn)
    return "颠倒 PE-01 的 evidence 数组顺序（rank 字段未同步）"


def tamper_citation(root):
    """反例②：把 PE-02 的引用编号改成越界（应触发 D2／E4）。"""
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-02":
                r["answer_text"] = (r.get("answer_text") or "").replace("[证据1]", "[证据99]", 1)
    rewrite_jsonl(os.path.join(root, ANSWER_TRACE_REL.replace("/", os.sep)), fn)
    return "把 PE-02 的 [证据1] 改成 [证据99]（m=10 → 越界）"


def tamper_graph_section(root):
    """反例③：把 PE-03 的图谱段换成固定标注，而 graph_used 仍为真（应触发 D4／E2）。"""
    sys.path.insert(0, os.path.join(root, "代码", "问答"))
    for name in ("config", "rules", "prompt", "assemble", "answer", "history"):
        sys.modules.pop(name, None)
    import prompt as pm  # noqa: E402

    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-03":
                secs = pm.split_answer_sections(r.get("answer_text") or "")
                sec = secs.get("知识图谱路径")
                body = sec if isinstance(sec, str) else ((sec or {}).get("text") or "")
                r["answer_text"] = (r.get("answer_text") or "").replace(
                    "【知识图谱路径】\n" + body,
                    "【知识图谱路径】\n" + pm.NO_GRAPH_MARKER)
    rewrite_jsonl(os.path.join(root, ANSWER_TRACE_REL.replace("/", os.sep)), fn)
    return "把 PE-03 的系统图谱段替换为「%s」，graph_used 仍为真" % pm.NO_GRAPH_MARKER


def tamper_total_tokens(root):
    """反例④：把 PE-04 的 `token_account.total_tokens` 抬到 3601（应触发 C4／G4）。

    这是全面审查 C-06 的还原：旧 C4 只看「现场重算」那一列，登记值一字未查，于是把登记
    的 `total_tokens` 改成超预算值也判 [OK]。修后的 C4 会把登记值与现场重算值逐题比对，
    并对登记值判「≤ 预算」。
    """
    def fn(rows):
        for r in rows:
            if r.get("qid") == "PE-04":
                ta = dict(r.get("token_account") or {})
                ta["total_tokens"] = 3601           # > 预算 3600，且 ≠ 现场重算值
                r["token_account"] = ta
    rewrite_jsonl(os.path.join(root, ANSWER_TRACE_REL.replace("/", os.sep)), fn)
    return "把 PE-04 的 token_account.total_tokens 改成 3601（> 预算 3600）"


def tamper_evidence_type(root):
    """反例⑤：把 qa_records.jsonl 首条 answer_evidence 的 `evidence_type` 改成表外取值
    （应触发 F1／G4）。

    这是全面审查 B-03／C-05 的还原：旧 F1 只比三表**字段名**、不看**取值**，把
    `evidence_type` 改成「新闻稿倒查」这种表外串也判 [OK]。修后的 F1 会逐条断言取值 ∈ 四类，
    并由 documents.jsonl 的 category ＋ 图谱侧标记**独立重算**再比对。
    """
    p = os.path.join(root, QA_RECORDS_REL.replace("/", os.sep))
    rows = [json.loads(l) for l in read_text(p, "").split("\n") if l.strip()]
    done = None
    for r in rows:
        ev = r.get("answer_evidence") or []
        if ev:
            ev[0]["evidence_type"] = "新闻稿倒查"        # 四类之外
            done = "%s/%s" % ((r.get("answer") or {}).get("answer_id"), ev[0].get("chunk_id"))
            break
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return "把 qa_records.jsonl 首条 answer_evidence（%s）的 evidence_type 改成表外取值「新闻稿倒查」" % done


def run_mirror_gate(root, label, emit_path, keep):
    """在镜像根上跑一次门禁（子进程，避免模块缓存串味）。返回读出的 JSON。"""
    argv = [sys.executable, SCRIPT, "--root", root, "--profile", "full",
            "--emit-json", emit_path]
    if keep:
        argv.append("--keep-tmp")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    t0 = time.time()
    proc = subprocess.run(argv, cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=env, timeout=7200)
    data = read_json(emit_path) or {}
    data["_exit"] = proc.returncode
    data["_seconds"] = round(time.time() - t0, 1)
    data["_stdout_tail"] = (proc.stdout or "").strip().splitlines()[-4:]
    data["_label"] = label
    logp = emit_path.replace(".json", ".log")
    with open(logp, "w", encoding="utf-8", newline="\n") as f:
        f.write("$ python 本脚本 --root %s --profile full\n--- stdout ---\n%s\n"
                "--- stderr ---\n%s\n--- exit=%d ---\n"
                % (root, proc.stdout or "", proc.stderr or "", proc.returncode))
    data["_log"] = logp
    return data


def selftest():
    print("=" * 78)
    print("负向校准（--selftest）：原样副本必须全过；5 个反例必须被真的判 FAIL")
    print("=" * 78)
    print("镜像根：系统临时目录（只读要求：本脚本不写工作区；镜像只读于交付目录）")
    print("说明：镜像不含 阶段02 全工作区，故 G5（跨文档核验）在镜像里记未执行；"
          "《22》已随镜像带入，故 H1／H2／H3 在**原样副本**上应判 [OK]（正向对照非空）。")
    print()

    base_fail = {"G6"}
    # 除反例①改的是 `answer_trace.jsonl`（`run_manifest.json` 登记的产物）外，反例④也改它、
    # 反例⑤改的是同样被登记的 `qa_records.jsonl`——三者都会让 G4 现场重算的 SHA-256 对不上，
    # 于是 G4 一并 FAIL。这是**正确的连带失败**（恰好证明 G4 的产物指纹复算真的在跑），故写进
    # 期望集，不做特殊处理。
    cases = [("pristine", None), ("case1-evidence-order", tamper_evidence_order),
             ("case2-citation", tamper_citation), ("case3-graph-section", tamper_graph_section),
             ("case4-total-tokens", tamper_total_tokens),
             ("case5-evidence-type", tamper_evidence_type)]
    expect_extra = {"pristine": set(), "case1-evidence-order": {"C3", "G4"},
                    "case2-citation": {"D2", "E4", "G4"},
                    "case3-graph-section": {"D4", "E2", "G4"},
                    "case4-total-tokens": {"C4", "G4"},
                    "case5-evidence-type": {"F1", "G4"}}
    results = {}
    tmpdirs = []
    verdict = True
    for tag, tamper in cases:
        root, copied, missing, git_ok = build_mirror(tag)
        tmpdirs.append(root)
        desc = "原样副本（正向对照）"
        if tamper:
            desc = tamper(root)
        emit = os.path.join(root, "_accept_rows.json")
        data = run_mirror_gate(root, tag, emit, ARGS.keep_tmp)
        got = set(data.get("fails") or [])
        unrun = set(data.get("unrun") or [])
        expected = base_fail | expect_extra[tag]
        ok = (got == expected) and unrun == {"G5"} and data.get("_exit") == 1
        verdict = verdict and ok
        results[tag] = (desc, ok, got, expected, unrun, data)
        print("-" * 78)
        print("[%s] %s" % ("PASS" if ok else "FAIL", tag))
        print("  构造：%s" % desc)
        print("  镜像：%d 个文件（缺 %d）、git 仓库=%s、用时 %s s、退出码 %s"
              % (copied, missing, git_ok, data.get("_seconds"), data.get("_exit")))
        print("  期望 FAIL 集：%s" % "、".join(sorted(expected)))
        print("  实测 FAIL 集：%s" % "、".join(sorted(got)))
        print("  实测未执行：%s（期望仅 G5）" % ("、".join(sorted(unrun)) or "∅"))
        new = sorted(got - base_fail)
        miss = sorted(expect_extra[tag] - got)
        print("  反例新增 FAIL：%s%s" % ("、".join(new) or "∅",
                                     "（其中 G4 为连带：反例改的是 answer_trace.jsonl／"
                                     "qa_records.jsonl，正是 run_manifest 登记的产物，"
                                     "G4 现场重算 SHA-256 自然对不上）"
                                     if ("G4" in new and tag != "pristine") else ""))
        if miss:
            print("  未捕获的期望行：%s" % "、".join(miss))
        if not ARGS.keep_tmp:
            print("  （镜像目录已删；--keep-tmp 可保留）")
    print("-" * 78)
    print("逐例结论：")
    for tag, _t in cases:
        desc, ok, got, expected, _u, _d = results[tag]
        print("  [%s] %-22s 期望 %s ／ 实测 %s"
              % ("PASS" if ok else "FAIL", tag, "、".join(sorted(expected)) or "∅",
                 "、".join(sorted(got)) or "∅"))
    if not ARGS.keep_tmp:
        for root in tmpdirs:
            shutil.rmtree(root, ignore_errors=True)
    else:
        print("镜像目录保留：%s" % "；".join(tmpdirs))
    print("=" * 78)
    print("校准结论：%s" % ("正向对照（原样副本）与 5 个反例的实测 FAIL 集与期望一致，"
                        "守卫自身通过校准。" if verdict else
                        "存在与期望不一致的用例，守卫未通过校准（见上）。"))
    print("=" * 78)
    return 0 if verdict else 2


def main():
    if ARGS.selftest:
        return selftest()
    print("=" * 78)
    print("第 8 阶段（智能问答系统）专项验收：《21》第八节 39 行逐行")
    print("被验收根目录：%s" % ROOT)
    print("profile=%s；零模型调用（本脚本不发任何大模型请求）；对工作区只读"
          % ARGS.profile)
    if ROOT != REPO_ROOT:
        print("注意：--root 覆盖了仓库根（%s ≠ %s），用于镜像／被篡改副本" % (ROOT, REPO_ROOT))
    print("=" * 78)
    g = Gate(ROOT, ARGS.profile)
    run_body(g)
    return finish(g)


_SUMMARY_DONE = False


def _exit_guard():
    if _SUMMARY_DONE:
        return
    print()
    print("  [FAIL] 验收脚本自身抛异常中断：详见上方 Traceback（按失败记账）")
    print("=" * 78)


atexit.register(_exit_guard)

if __name__ == "__main__":
    _code = main()
    _SUMMARY_DONE = True
    sys.exit(_code)
