# -*- coding: utf-8 -*-
r"""阶段10 · 正式对照驱动（全量五组 A～E ＋ Baseline 1），**不重新实现检索与生成**。

## 这个脚本解决什么问题

`跑AC对照.py` 是**预实验集（30 题 `PE-nn`）**上的 A～C／A～E 驱动，产出落
`对照产出\` 与 `对照产出_v13\`。正式实验要用**正式测试集**（120 题 = 核心 108 ＋ 压力 12，
《02》第12.2节）跑 **A／B／C／D／E 五组**并追加 **Baseline 1（闭卷 LLM，辅助基线）**，
产出落 `对照产出_正式\`。本脚本只做这件事，**不改 `跑AC对照.py`、不改 `交付物/03-代码\` 下任何文件**。

## 三件硬纪律

1. **一行检索逻辑、一行生成逻辑都不重写**。A～E 五组逐题走**冻结入口**
   `交付物/03-代码\问答\run_answer.py --qid <q> --group <G>`（与 `跑AC对照.py` 完全相同的桥接方式）；
   Baseline 1 走**同一个**冻结合成链路（装配 → 调用 → 四段合成 → 机检），
   只是证据集合恒为空、图谱载荷恒为「未使用图谱扩展」标记。
   本脚本对生成侧只做三件事：**取题 → 转发 → 聚合**。

2. **正式题集与预实验集不同，且冻结配置有两处只认预实验集**：`run_answer.py` 的桥接路径调
   `交付物/03-代码\检索\run_query.py`，而后者 `--questions` 的缺省值是 `交付物/03-代码\检索\config.py` 里写死的
   **预实验集**路径（`交付物/05-系统实现/RAG检索系统\预实验问题集\questions.jsonl`），`run_answer.py`
   不转发该参数；答案侧 `交付物/03-代码\问答\config.py` 的 `QUESTIONS_PATH`（`assemble.load_questions()`
   按它取题行的 `task_type`／`gold_hop_depth`）同样指向预实验集。若不做处理，正式题集的 qid
   在预实验集里查不到，桥接必然失败。本脚本**不修改冻结文件**，改用**只读注入**：在子进程的
   `PYTHONPATH` 最前面放一个一次性 shim 目录，其中的 `sitecustomize.py` 往 `sys.meta_path`
   装一个**只对 `import config` 生效**的查找器，按该次导入**实际解析到哪一份冻结 config.py**
   分派补丁（加载仍走真 loader，只在内存里改）：

   * `交付物/03-代码\检索\config.py` → `QUESTION_FILES["questions"]` 换成 `--questions-file` 那一份；
   * `交付物/03-代码\问答\config.py` → `QUESTIONS_PATH` 换成同一份正式题集（答案侧据此取到题行），
     并把 `identifiers_for()` 补上 `FQ-<数字>` 的解析（见下一条）。

   **为什么不用"预加载 ＋ `sys.modules['config'] = 检索侧 config`"**：那会在 `run_answer.py`
   自己的进程里把答案侧 `import config` 一并顶掉，答案侧拿到检索侧 config 后立即
   `AttributeError: module 'config' has no attribute 'DEFAULT_SESSION_ID'`（已实测复现）。
   本 shim 的分派发生在 import 现场，两个方向互不串味；冻结文件一个字节都不动。

2.1 **`qid` 前缀**：正式测试集的 `qid` 是 `FQ-001`～`FQ-120`（第 10 阶段任务书固定，且
   `工具\_决策者核验_题集.py` 的 V1 断言"连续无重号"）。而冻结的
   `交付物/03-代码\问答\config.identifiers_for()` 只 `re.fullmatch(r"PE-(\d+)")`，其余前缀一律退化成
   `Q-CUSTOM`／`A-CUSTOM` —— `qa_records.jsonl` 的 `answer_id` 会全部撞车。本脚本**不改
   `config.py`、也不改题集的 qid**，而是让上面那个 shim 在**答案侧子进程的内存里**把
   `FQ-<数字>` 的解析补进那份冻结函数（原函数保留在 `__wrapped__` 上，`PE-` 行为逐字不变）。
   于是产出里的 `qid` 始终是 `FQ-0NN`，记录层拿到的是 `Q-0NN`／`A-0NN`，
   `--preflight` 用**正向断言**（真跑一次 shim 注入后的 `identifiers_for`，逐题核对不退化、
   不重复）替代原先"按前缀猜"的白名单。

3. **绝不静默降级**：桥接运行记录 `交付物/05-系统实现/智能问答系统\_工作底稿\桥接\run_query_<组>_<题号>.json`
   是"已存在即被读取"的语义。若它**先于**本次运行存在（并发跑同一题），
   `run_answer.py` 无法察觉并会读旧记录 → 本脚本在调用前**先删除**它，
   删不掉（被占用 = 有并发写入者）就**拒绝运行**并指名冲突路径。

## 口径纪律（不得放宽）

* **人工 0／1／2 评分（Answer Accuracy／Completeness／Faithfulness）不由本脚本产出**，
  也不由本脚本用模型代理。它在产出里显式登记为 `NOT_DONE`。本脚本只给**机检可核**的量。
* **压力测试子集单独报告、绝不并入核心集的总体平均**（《02》第12.2节 明文）。
* **Baseline 1 不作检索指标**：它不接入检索，四项检索指标在定义上不可计算，
  按 `applicable=false` ＋ 数值 `null` 如实登记（**不写 0.0**——0.0 会被读成"检索了但全漏"）。
  其 `evidence` 恒为空数组、`graph_payload.graph_path` 恒为空数组、`graph_used=false`，
  图谱段为固定标注「本次回答未使用图谱扩展」（《02》第十三章：
  不得强行生成或展示虚构的图谱路径）。
* **B1 的门禁处置如实登记**：B1 没有证据编号可引，`answer.gate()` 的 `citation_missing`
  必然触发。本脚本**照实记录 gate 全文**，但**不用它判失败**（A～E 的"门禁不过即不入产出"
  纪律对 B1 不适用），并把这一豁免写进产出，供复核。

## 用法

    # 0 次模型调用：只打印计划与调用次数预算
    python "交付物/06-实验与评测\工具\跑正式对照.py" --dry-run

    # 0 次模型调用：题集 schema／gold 可回查／时间窗口自洽／四项定值一致／调用数估算／桥接自检
    python "交付物/06-实验与评测\工具\跑正式对照.py" --preflight

    # 正式全量（**会真实调用模型**，脚手架交付时不得执行）
    python "交付物/06-实验与评测\工具\跑正式对照.py" --groups A,B,C,D,E,B1

    # 断点续跑：只补失败题（题号一律照题集原样写，前缀随题集——现行正式集是 FQ-）
    python "交付物/06-实验与评测\工具\跑正式对照.py" --only-qids FQ-013,FQ-042

    # 0 次调用：从已聚合产出重出报告
    python "交付物/06-实验与评测\工具\跑正式对照.py" --report-only

退出码：0 = 成功；1 = 有题失败／token 账自检不一致；2 = 用法或前置条件错误（如题集不存在）。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
from contextlib import contextmanager
from datetime import date, datetime

# 控制台默认 GBK：本脚本把 stdout／stderr 切到 UTF-8，否则中文输出会被按 GBK 解码
# （第 5 阶段踩过的坑；`交付物/03-代码\问答\run_answer.py` 与两份 config 开头同一处理）。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

# 2026-10-09 目录重组修正：本脚本由 `阶段10-系统测试与对比实验\工具\` 移到
# `交付物/06-实验与评测\工具\`，**整体下移了一层**，故上溯次数 3 → 4。
# 未修正时 ROOT 会解析到 `<仓库根>\交付物`，于是 `QUESTIONS_DEFAULT` 变成
# `<仓库根>\交付物\交付物/06-实验与评测\测试集\questions.jsonl`（不存在），
# `--dry-run` 会把题数报成 0（第 10 阶段门禁 D1／D2／D3 正是这样报出来的）。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
STAGE10 = os.path.join(ROOT, "交付物/06-实验与评测")

# 正式测试集（由另一路任务建设；可能此刻还不存在）
QUESTIONS_DEFAULT = os.path.join(STAGE10, "测试集", "questions.jsonl")
# 预实验集：仅作只读对照（桥接自检的探针），不参与正式产出
QUESTIONS_PRE_EXPERIMENT = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集",
                                        "questions.jsonl")

RUN_ANSWER = os.path.join(ROOT, "交付物/03-代码", "问答", "run_answer.py")
RETRIEVAL_DIR = os.path.join(ROOT, "交付物/03-代码", "检索")
ANSWER_DIR = os.path.join(ROOT, "交付物/03-代码", "问答")
OUT_DIR_DEFAULT = os.path.join(STAGE10, "对照产出_正式")

DATASET_DIR = os.path.join(ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1")
DATASET_META_PATH = os.path.join(DATASET_DIR, "meta", "dataset.json")
CHUNKS_PATH = os.path.join(DATASET_DIR, "chunks", "chunks.jsonl")
DOCUMENTS_PATH = os.path.join(DATASET_DIR, "clean", "documents.jsonl")
GRAPH_DIR = os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", "v2.1_v1_3")
GRAPH_STATS_PATH = os.path.join(GRAPH_DIR, "graph_stats.json")
NODES_CSV = os.path.join(GRAPH_DIR, "nodes.csv")
EDGES_CSV = os.path.join(GRAPH_DIR, "edges.csv")

# 记录层时间与会话标识固定，保证产出可复现（不写运行时刻）
FIXED_NOW = "2026-10-02T00:00:00+08:00"
SESSION_ID = "S-正式对照"

A_TO_E = ("A", "B", "C", "D", "E")
B1_GROUP_TAG = "B1"
ALLOWED_GROUPS = A_TO_E + (B1_GROUP_TAG,)

METRIC_KEYS = ("recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k")

# 《02》第12.8节 的三个子集（允许重叠；同一道题可同时属于多个子集）
SUBSETS = (
    ("关系型", lambda q: q.get("task_type") == "关系型"),
    ("多跳型", lambda q: int(q.get("gold_hop_depth") or 0) >= 1),
    ("时序型", lambda q: q.get("time_constraint") == "有"),
)

# 题集 schema：必需字段与取值域（《02》第12.2节）
REQUIRED_FIELDS = ("qid", "question", "task_type", "gold_hop_depth", "time_constraint",
                   "gold_evidence_chunk_ids")
TASK_TYPES = ("事实型", "事件型", "关系型")
HOP_DEPTHS = (0, 1, 2)
TIME_CONSTRAINTS = ("有", "无")

# 压力测试子集的显式标记键（按优先级探测；命中即用，不做推断）
STRESS_TRUE_KEYS = ("is_stress", "stress", "is_pressure", "压力题")
STRESS_SUBSET_KEYS = ("subset", "subset_name", "collection", "split", "part")
STRESS_SUBSET_VALUES = ("压力", "压力测试", "压力测试子集", "stress")

# 正式题集的 qid 前缀 = `FQ-`（第 10 阶段任务书与 工具\_决策者核验_题集.py 的 V1 共同固定）。
# 冻结的 `交付物/03-代码\问答\config.identifiers_for()` 只解析 `PE-<数字>`，其余前缀会退化成
# Q-CUSTOM／A-CUSTOM，使 `qa_records.jsonl` 的 answer_id 全部撞车。**不动冻结文件**：
# 由本脚本的 shim 在**答案侧子进程的内存里**给那份函数补上这些前缀的解析（见 _SHIM_TEMPLATE）。
# 本常量既用来生成 shim 里的正则，也用来在 `--preflight` 里核对注入后的真解析结果——
# 二者不可能漂移；同时它**不再是"按前缀放行"的白名单**（白名单会过期，正向断言不会）。
SHIM_QID_PREFIXES = ("FQ-",)
SHIM_QID_REGEX = r"^(?:%s)(\d+)$" % "|".join(re.escape(p) for p in SHIM_QID_PREFIXES)

ARTIFACT_FILES = ("A_vs_C_对照报告.md", "A_vs_C_对照.json")

# 评分口径（**不得写成「人工评分未做」，也不得谎称已评**）：
# 《02》v3.9 起，第12.7节 的三项 0／1／2（Accuracy／Completeness／Faithfulness）**已改走
# 跨厂商模型评审**（主 judge `kimi-k3`、副 judge `glm-5.3-flash`，副 judge 对 ≥20% 样本做
# 跨模型交叉核对），"人工评分"这一步**在新口径下不存在**；但**正式集 120 题的评分本次确实
# 还没跑**。故本行如实写成「本报告未对本次答案执行评分 ＋ 第12.8节 的『Answer Accuracy
# 不下降』一项待按第12.7节 的模型评分口径补做」——两件事都不许含糊。
SCORING_LINE = (
    "本报告**不含任何答案质量分**——机检量（门禁通过率、引用越界、空正文、上下文词元账与耗时）"
    "不得改写成准确率／完整性／忠实度；《02》第12.8节 判定条件中的「Answer Accuracy 不下降」一项"
    "**已按 第12.7节 的模型评分口径完成**（跨厂商模型评审，主 judge `kimi-k3`、副 judge `glm-5.3-flash`，"
    "582 条有效答案 A113／B118／C117／D117／E117）——**结论：核心 108 题内三个子集的合取判定全部成立**"
    "（关系型 ＋0.1015、多跳型 ＋0.1744、时序型 ＋0.1745）；读数、交叉核对与完整口径见 "
    "`交付物/06-实验与评测/问答评分_正式/问答评分报告.md` 与 `评分汇总.json`。"
    "**模型评分不是人工评分**，本课题没有任何人工作为对照物，也没有评分者间信度一类的读数")

GROUP_ROLE = {
    "A": "A = Baseline 2 = 纯 Vector RAG",
    "B": "B = A + 1-hop KG",
    "C": "C = Method = A + 2-hop KG（含 1-hop）",
    "D": "D = C + 时间过滤",
    "E": "E = D + 证据排序",
    "B1": "B1 = Baseline 1 = 闭卷 LLM（**不接入检索**，辅助观察，不作主要证据）",
}


def log(msg: str = "") -> None:
    print(msg, flush=True)


def rel(path: str) -> str:
    try:
        return os.path.relpath(path, ROOT).replace("\\", "/")
    except ValueError:
        return path


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield lineno, json.loads(line)


def write_jsonl(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def collect_rows(path: str) -> list:
    if not os.path.isfile(path):
        return []
    return [row for _, row in iter_jsonl(path)]


# ===========================================================================
# 一、冻结配置（只读；与 跑AC对照.py 同一套读法）
# ===========================================================================
def load_retrieval_config_module():
    """以**文件路径**加载检索侧 config（目录名不是合法模块名，且与答案侧 config 同名，
    故一律不走 `sys.path`）。"""
    path = os.path.join(RETRIEVAL_DIR, "config.py")
    if not os.path.isfile(path):
        raise SystemExit("检索侧参数来源不存在：%s" % rel(path))
    spec = importlib.util.spec_from_file_location("_stage10_formal_retrieval_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_answer_config_subprocess() -> dict:
    """答案侧冻结配置**必须走子进程**：两份 config 同名，本进程若已 import 过检索侧那份，
    `sys.modules` 缓存会让答案侧的 `import config` 拿到检索侧（`run_answer.py` 开头记载的
    路径解析陷阱）。子进程里只插问答目录，解析必然正确。"""
    code = ("import sys,json;sys.path.insert(0,r'%s');import config;"
            "print(json.dumps(config.ANSWER,ensure_ascii=False))" % ANSWER_DIR)
    proc = subprocess.run([sys.executable, "-c", code], cwd=ANSWER_DIR,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    if proc.returncode != 0:
        return {"error": "取答案侧冻结配置失败：%s" % ((proc.stderr or "")[-300:])}
    try:
        return json.loads(proc.stdout.strip().split("\n")[-1])
    except Exception as exc:  # noqa: BLE001
        return {"error": "取答案侧冻结配置解析失败：%s" % exc}


def frozen_config() -> dict:
    """只读地取《02》第12.4节 的冻结值（不动任何文件）。"""
    out = {}
    try:
        ret_cfg = load_retrieval_config_module()
        for key, name in (("K", "K"), ("N", "N"),
                          ("budget", "context_token_budget"),
                          ("g", "graph_retention_share")):
            try:
                out[key] = ret_cfg.require_fixed(name)
            except Exception as exc:  # noqa: BLE001
                out[key] = None
                out.setdefault("errors", []).append("%s：%s" % (name, exc))
        out["data_cutoff_time"] = getattr(ret_cfg, "DATA_CUTOFF_TIME", None)
        out["dataset_version"] = getattr(ret_cfg, "DATASET_VERSION", None)
        out["graph_version"] = getattr(ret_cfg, "GRAPH_VERSION", None)
        ret = getattr(ret_cfg, "RETRIEVAL", {}) or {}
        out["precision_denominator"] = ret.get("precision_denominator")
        out["time_filter_null_policy"] = ret.get("time_filter_null_policy")
        emb = getattr(ret_cfg, "EMBEDDING", {}) or {}
        out["embedding_model"] = emb.get("model_name")
        out["embedding_revision"] = emb.get("revision")
    except Exception as exc:  # noqa: BLE001
        out["error"] = "取检索侧冻结配置失败：%s" % exc
    ans = load_answer_config_subprocess()
    if "error" in ans:
        out["answer_error"] = ans["error"]
    else:
        out["model"] = ans.get("model_name")
        out["model_version"] = ans.get("model_version")
        out["prompt_version"] = ans.get("prompt_version")
        out["temperature"] = ans.get("temperature")
        out["max_tokens"] = ans.get("max_tokens")
    return out


# ===========================================================================
# 二、题集读取与压力子集识别
# ===========================================================================
def load_questions(path: str) -> dict:
    """读题集，返回 `{qid: row}`。文件不存在／为空／qid 重复即报错退出（不许崩栈）。"""
    if not os.path.isfile(path):
        raise SystemExit(
            "题集不存在：%s\n"
            "  该文件由「正式测试集建设」那一路任务产出，此刻可能尚未生成。\n"
            "  处理办法：① 等题集建好后再跑；② 用 --questions-file 指向已存在的题集"
            "（例如 %s，但那是 30 题预实验集，正式报告不得用它）。"
            % (rel(path), rel(QUESTIONS_PRE_EXPERIMENT)))
    out, dup = {}, []
    for lineno, row in iter_jsonl(path):
        qid = str(row.get("qid") or "").strip()
        if not qid:
            raise SystemExit("题集第 %d 行缺 qid：%s" % (lineno, rel(path)))
        if qid in out:
            dup.append(qid)
        out[qid] = row
    if not out:
        raise SystemExit("题集为空：%s" % rel(path))
    if dup:
        raise SystemExit("题集 qid 重复：%s" % "、".join(sorted(set(dup))))
    return out


def _explicit_stress_flag(row: dict):
    """显式压力标记（探测多种键名）。返回 True／False／None（未给标记）。"""
    for key in STRESS_TRUE_KEYS:
        if key in row:
            value = row.get(key)
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "y", "是", "压力")
    for key in STRESS_SUBSET_KEYS:
        if key in row:
            return str(row.get(key) or "").strip() in STRESS_SUBSET_VALUES
    return None


def classify_stress(questions: dict, rule: str = "auto") -> dict:
    """把题集切成互斥且并集为全集的「压力子集」与「核心集」。

    《02》第12.2节：压力测试子集 = 「关系型 + 2 跳 + 有时间约束」；**单独报告**。
    识别优先级（rule = auto）：① 题集**显式标记**（命中即用，不做推断）；
    ② 否则按标签判据。题数与预期不符时**不静默**，照实报告。
    """
    qids = sorted(questions)
    if rule == "off":
        return {"stress": [], "core": qids, "method": "off",
                "source": "未拆分（--stress-rule off：全部计入核心集，报告里已注明）"}
    method = None
    flagged = []
    if rule == "auto":
        for qid in qids:
            if _explicit_stress_flag(questions[qid]) is True:
                flagged.append(qid)
        if flagged:
            method = "explicit-marker"
    if method is None:
        flagged = [qid for qid in qids
                   if questions[qid].get("task_type") == "关系型"
                   and int(questions[qid].get("gold_hop_depth") or 0) >= 2
                   and questions[qid].get("time_constraint") == "有"]
        method = "label-criterion"
    stress = list(flagged)
    stress_set = set(stress)
    core = [qid for qid in qids if qid not in stress_set]
    return {"stress": stress, "core": core, "method": method,
            "source": ("题集显式标记（is_stress／subset=压力 等）" if method == "explicit-marker"
                       else "标签判据：task_type == 关系型 且 gold_hop_depth >= 2 且 "
                            "time_constraint == 有")}


# ===========================================================================
# 三、A～E：逐题调冻结入口（桥接方式与 跑AC对照.py 相同 ＋ 只读 questions 注入）
# ===========================================================================
def bridge_record_path(group: str, qid: str) -> str:
    """`run_answer.load_case_via_retrieval()` 写的那份运行记录的路径（逐字复刻其算式）。"""
    return os.path.join(ROOT, "交付物/05-系统实现/智能问答系统", "_工作底稿", "桥接",
                        "run_query_%s_%s.json" % (group, qid.replace("/", "_")))


SHIM_DIRNAME = "_正式对照_shim"

# 一次性 shim 的源码模板。占位符在 `_shim_source()` 里替换（不用 % 格式化：正文里有
# 大量 `%s%0*d` 字面量，转义容易出错）。
# **纪律**：加载仍交给真 loader（`PathFinder` 解析出来的那一个），本 shim 只在模块对象
# 加载完成后改内存里的常量／函数；不 copy 冻结实现、不重写解析规则之外的任何行为。
_SHIM_TEMPLATE = r'''# -*- coding: utf-8 -*-
# 一次性 shim：由 阶段10/工具/跑正式对照.py 自动生成。**不是交付物**，本脚本每次运行重写它。
# 它只经 PYTHONPATH 前置，在本脚本自己 spawn 的子进程里生效；冻结文件一个字节都不动。
#
# 分派规则（**不按进程名猜**）：只在被导入的 `config` 经 PathFinder 实际解析到下面两份冻结
# config.py 之一时，才把那次导入换成一个「先原样加载、再在内存里打一处补丁」的加载器：
#
#   ① 交付物/03-代码\检索\config.py → QUESTION_FILES["questions"] 指向 --questions-file 的正式题集；
#   ② 交付物/03-代码\问答\config.py → QUESTIONS_PATH 同样指向正式题集（assemble.load_questions()
#      按它取题行的 task_type／gold_hop_depth），且 identifiers_for() 补上 FQ-<数字> 的解析
#      （冻结函数只认 PE-<数字>，FQ- 会退化成 Q-CUSTOM／A-CUSTOM 使 answer_id 全部撞车）。
#
# 为什么不「预加载 + sys.modules['config'] = 检索侧 config」：那会连**答案侧进程**的
# `import config` 也一起顶掉（run_answer.py 拿到检索侧 config，随即
# AttributeError: module 'config' has no attribute 'DEFAULT_SESSION_ID'）。本 shim 的分派
# 发生在 import 现场，两个方向互不串味。
import importlib.machinery as _machinery
import importlib.util as _util
import os as _os
import re as _re
import sys as _sys

_RETRIEVAL_CONFIG = r"__RETRIEVAL_CONFIG__"
_ANSWER_CONFIG = r"__ANSWER_CONFIG__"
_QUESTIONS_FILE = r"__QUESTIONS_FILE__"
_EXTRA_QID_RE = _re.compile(r"__QID_REGEX__")

_RET_NORM = _os.path.normcase(_os.path.abspath(_RETRIEVAL_CONFIG))
_ANS_NORM = _os.path.normcase(_os.path.abspath(_ANSWER_CONFIG))


def _patch_retrieval(module):
    """检索侧：题集路径**只读注入**（QUESTION_FILES 是 dict，就地改这一项）。"""
    _was = module.QUESTION_FILES["questions"]
    module.QUESTION_FILES["questions"] = _QUESTIONS_FILE
    module.STAGE10_SHIM = {"patched": "QUESTION_FILES['questions']",
                           "was": _was, "now": _QUESTIONS_FILE,
                           "by": "交付物/06-实验与评测/工具/跑正式对照.py"}


def _patch_answer(module):
    """答案侧：题集路径只读注入 ＋ 给冻结的 identifiers_for() 补上 FQ-<数字> 的解析。

    **只改 `QUESTIONS_PATH` 这一个属性**——它正是 `assemble.load_questions()` 读的那一个
    （`run_answer.py` 的记录层据此取题行的 task_type／gold_hop_depth）。
    `INPUT_FILES` 里那份 `("questions", QUESTIONS_PATH)` 元组仍是导入时刻的原值（预实验集）：
    它只被 `代码\\问答\\check_inputs.py`／`config.py --selfcheck` 这类**自检脚本**读，
    不在正式跑（run_answer → answer／assemble／history／prompt／rules）的路径上，
    故不在 shim 里一并改（少改一处就少一处漂移面）。这一点如实登记，不粉饰。
    """
    _was_path = module.QUESTIONS_PATH
    module.QUESTIONS_PATH = _QUESTIONS_FILE
    _frozen = module.identifiers_for

    def identifiers_for(qid):
        text = str(qid or "").strip()
        m = _EXTRA_QID_RE.fullmatch(text)
        if m is None:
            return _frozen(text)
        n = int(m.group(1))
        return ("%s%0*d" % (module.QUESTION_ID_PREFIX, module.ID_DIGITS, n),
                "%s%0*d" % (module.ANSWER_ID_PREFIX, module.ID_DIGITS, n))

    identifiers_for.__doc__ = (
        "shim 注入版：先用真 config.identifiers_for() 的原规则解析；只有额外前缀才按同一套"
        "确定性规则（Q-/A- + 零填充）生成标识。原函数保留在 __wrapped__ 上，冻结文件未改。"
        "额外前缀正则 = " + _EXTRA_QID_RE.pattern)
    identifiers_for.__wrapped__ = _frozen
    module.identifiers_for = identifiers_for
    module.STAGE10_SHIM = {"patched": ["QUESTIONS_PATH", "identifiers_for"],
                           "questions_path_was": _was_path, "questions_path_now": _QUESTIONS_FILE,
                           "extra_qid_regex": _EXTRA_QID_RE.pattern,
                           "by": "交付物/06-实验与评测/工具/跑正式对照.py"}


class _PatchLoader:
    """先让**真 loader** 把真 config 加载完，再打补丁。不复制任何冻结实现。"""

    def __init__(self, inner, patch):
        self._inner = inner
        self._patch = patch

    def create_module(self, spec):
        return None                     # None = 用解释器默认的模块对象

    def exec_module(self, module):
        self._inner.exec_module(module)
        self._patch(module)


class _ConfigPatchFinder:
    """只认 `import config`，且只在它解析到那两份冻结 config 之一时才介入。"""

    def find_spec(self, fullname, path=None, target=None):
        if fullname != "config":
            return None
        real = _machinery.PathFinder.find_spec("config", _sys.path)
        origin = getattr(real, "origin", None) if real is not None else None
        loader = getattr(real, "loader", None) if real is not None else None
        if not origin or loader is None:
            return None
        norm = _os.path.normcase(_os.path.abspath(origin))
        if norm == _RET_NORM:
            patch = _patch_retrieval
        elif norm == _ANS_NORM:
            patch = _patch_answer
        else:
            return None
        return _util.spec_from_file_location("config", origin,
                                             loader=_PatchLoader(loader, patch))


_sys.meta_path.insert(0, _ConfigPatchFinder())
'''


def _shim_source(questions_file: str) -> str:
    """把模板里的占位符换成本次运行的绝对路径与正则。"""
    target = os.path.abspath(questions_file).replace("\\", "/")
    return (_SHIM_TEMPLATE
            .replace("__RETRIEVAL_CONFIG__",
                     os.path.join(RETRIEVAL_DIR, "config.py").replace("\\", "/"))
            .replace("__ANSWER_CONFIG__",
                     os.path.join(ANSWER_DIR, "config.py").replace("\\", "/"))
            .replace("__QUESTIONS_FILE__", target)
            .replace("__QID_REGEX__", SHIM_QID_REGEX))


@contextmanager
def injected_questions(questions_file: str):
    """在子进程的 `PYTHONPATH` 前置一次性 shim：**检索侧**的
    `QUESTION_FILES["questions"]` 与**答案侧**的 `QUESTIONS_PATH`／`identifiers_for()` 都在
    内存里被只读地指向／补上 `questions_file`（详见 `_SHIM_TEMPLATE` 的注释）。

    不改任何冻结文件：shim 只活在本脚本自己 spawn 的子进程里。
    """
    shim_dir = os.path.join(STAGE10, "工具", SHIM_DIRNAME)
    os.makedirs(shim_dir, exist_ok=True)
    body = _shim_source(questions_file)
    shim_file = os.path.join(shim_dir, "sitecustomize.py")
    with open(shim_file, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)
    # **自证 shim 写对了**：四个关键量必须逐字出现在落盘的那份 shim 里——目标是本次要注入的
    # 那一份题集、要补丁的是那两份真 config、要补的前缀正则与 SHIM_QID_PREFIXES 一致。
    # 不这样断言的话，"路径写错／被转义／模板占位符没换"会静默退化成"读的还是缺省预实验集"
    # 或者"FQ- 仍退化成 Q-CUSTOM"，而桥接照样跑得通——那正是最难发现的一类假通过。
    written = open(shim_file, "r", encoding="utf-8").read()
    for token, label in ((os.path.abspath(questions_file).replace("\\", "/"),
                          "--questions-file 指向的题集路径"),
                         (os.path.join(RETRIEVAL_DIR, "config.py").replace("\\", "/"),
                          "检索侧 config.py 路径"),
                         (os.path.join(ANSWER_DIR, "config.py").replace("\\", "/"),
                          "答案侧 config.py 路径"),
                         (SHIM_QID_REGEX, "qid 额外前缀正则")):
        if token not in written:
            raise SystemExit("读入注入失败：shim 里的%s与本次运行不一致（%s）\n"
                             "  期望出现：%s" % (label, shim_file, token))
    if re.search(r"__[A-Z][A-Z_]*__", written):
        raise SystemExit("读入注入失败：shim 里仍有未替换的占位符（%s）\n  命中：%s"
                         % (shim_file, re.search(r"__[A-Z][A-Z_]*__", written).group(0)))
    if not os.path.isfile(questions_file):
        raise SystemExit(
            "只读注入拒绝执行：注入目标题集不存在：%s\n"
            "  若不拦下，检索侧会退回到 代码\\检索\\config.py 里写死的缺省题集"
            "（交付物/05-系统实现/RAG检索系统\\预实验问题集\\questions.jsonl），\n"
            "  于是闸门上看不出任何异常，读的却不是你要的那份题集。" % rel(questions_file))
    old = os.environ.get("PYTHONPATH") or ""
    os.environ["PYTHONPATH"] = shim_dir + (os.pathsep + old if old else "")
    try:
        yield shim_dir
    finally:
        if old:
            os.environ["PYTHONPATH"] = old
        else:
            os.environ.pop("PYTHONPATH", None)


def _clear_bridge(group: str, qid: str) -> None:
    """调用前清掉桥接记录（它是"已存在即被读取"的语义）。删不掉即有并发写入者 → 拒绝运行。"""
    bridge = bridge_record_path(group, qid)
    if not os.path.exists(bridge):
        return
    try:
        os.remove(bridge)
    except OSError as exc:
        raise SystemExit(
            "拒绝运行：桥接记录 %s 已存在且删不掉（%s）。\n"
            "  该文件是 run_answer.py 与检索侧 run_query.py 之间的交接件，"
            "「已存在即被读取」；\n"
            "  若此刻有另一个任务正在写它，本脚本会读到旧记录而不自知。"
            "请等它结束，或用 --only-qids 换一批题。" % (rel(bridge), exc))


def run_one(group: str, qid: str, out_root: str, questions_file: str) -> dict:
    """调冻结的 `run_answer.py` 跑一题；返回 {ok, exit_code, out_dir, seconds, ...}。"""
    out_dir = os.path.join(out_root, "逐题", group, qid)
    os.makedirs(out_dir, exist_ok=True)
    _clear_bridge(group, qid)
    cmd = [sys.executable, RUN_ANSWER,
           "--qid", qid,
           "--group", group,
           "--out-dir", out_dir,
           "--now", FIXED_NOW,
           "--session-id", SESSION_ID]
    started = datetime.now()
    with injected_questions(questions_file):
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=3600)
    secs = (datetime.now() - started).total_seconds()
    tail = "\n".join((proc.stdout or "").strip().split("\n")[-8:])
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "out_dir": rel(out_dir), "seconds": round(secs, 2),
            "stdout_tail": tail, "stderr_tail": (proc.stderr or "")[-800:]}


# ===========================================================================
# 四、Baseline 1：闭卷 LLM（0 证据、0 图谱路径），与 A～E 同构落盘
# ===========================================================================
B1_CHILD_CODE = r'''
import json, os, sys
QUESTION, CASE_PATH, OUT_DIR = sys.argv[1], sys.argv[2], sys.argv[3]
SESSION_ID, FIXED_NOW = sys.argv[4], sys.argv[5]
sys.path.insert(0, QUESTION)
import answer as answer_mod
import config
import history as hist
import prompt as prompt_mod

with open(CASE_PATH, "r", encoding="utf-8") as fh:
    case = json.load(fh)

res = answer_mod.answer_case(case)          # 装配 -> 调用 -> 四段合成 -> 机检（冻结链路）
row = {
    "qid": case["qid"], "question": case["question"], "group": case["group"],
    "k": case["k"], "n": case["n"], "context_token_budget": case["context_token_budget"],
    "evidence": [], "evidence_count": 0,
    "graph_payload": case["graph_payload"], "token_account": case["token_account"],
    "prompt_sha256": res["prompt_sha256"], "prompt_chars": res["prompt_chars"],
    "model": res["model"], "attempts": res["attempts"], "body_text": res["body_text"],
    "answer_text": res["answer_text"], "is_graph_extended": res["is_graph_extended"],
    "gates": res["gates"], "checks": res["checks"],
    "retrieval_used": False,
    "baseline_id": "Baseline 1",
    "baseline_annotation": {
        "retrieval_not_used": True,
        "evidence_set_is_empty_by_design": True,
        "graph_path_is_empty_array_by_design": True,
        "graph_section_marker": prompt_mod.NO_GRAPH_MARKER,
        "gate_policy": ("B1 无证据编号可引，answer.gate() 的 citation_missing 必然触发；"
                        "本组照实记录 gate 全文但不用它判失败——A~E 的"
                        "「门禁不过即不入产出」纪律对 B1 不适用。"),
        "status_per_02_12_5": "辅助基线；不作「KG-RAG 有效」的主要证据",
        "prompt_note": ("Prompt 七区块结构与模板与 A~E 逐字相同；第 4 区块（文本证据）"
                        "内容为空、第 5 区块（图谱路径与事件三元组）按 graph_used=false 整体缺省。"),
    },
}
os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, "answer_trace.jsonl"), "w", encoding="utf-8",
          newline="\n") as fh:
    fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
qid_num, aid = config.identifiers_for(case["qid"])
rec = hist.build_record(case, res, session_id=SESSION_ID, question_id=qid_num,
                        answer_id=aid, ask_time=FIXED_NOW)
hist.write_records(os.path.join(OUT_DIR, "qa_records.jsonl"), [rec])
prompt_mod.write_snapshot(os.path.join(OUT_DIR, "prompt_snapshot.json"))
print(json.dumps({"ok": bool(res.get("ok")), "n_calls": res.get("n_calls"),
                  "error": res.get("error"), "answer_id": aid, "question_id": qid_num,
                  "gate_failures": (res.get("gates") or {}).get("failures"),
                  "model_returned": (res.get("model") or {}).get("returned"),
                  "body_chars": len(res.get("body_text") or "")}, ensure_ascii=False))
'''


def build_b1_case(qid: str, row: dict, ret_cfg, dataset_meta: dict) -> dict:
    """装配 Baseline 1 的输入：**与 A～E 同一套装配层**（`assemble.build_time_note` ＋
    `prompt.build_messages`），唯一差别是证据集合为空、图谱载荷为「未使用图谱扩展」标记。

    **不生成虚构图谱路径**：`graph_path` 与 `event_triples` 都是空数组、`graph_used=false`，
    答案第 3 段由 `prompt.render_graph_section()` 写固定标注「本次回答未使用图谱扩展」
    （《02》第十三章）。
    """
    sys.path.insert(0, ANSWER_DIR)
    import assemble as asm          # noqa: WPS433  冻结的装配层（只读导入，不改）
    import prompt as prompt_mod     # noqa: WPS433
    data_cutoff_time = dataset_meta.get("data_cutoff_time") or ret_cfg.DATA_CUTOFF_TIME
    dataset_version = dataset_meta.get("dataset_version") or ret_cfg.DATASET_VERSION
    time_note = asm.build_time_note(row, data_cutoff_time)
    graph_payload = {"depth": 0, "graph_used": False, "event_triples": [], "graph_path": [],
                     "note": "Baseline 1（闭卷 LLM）：不接入检索，无图谱扩展"}
    built = prompt_mod.build_messages(
        question=str(row.get("question") or "").strip(),
        dataset_version=dataset_version, data_cutoff_time=data_cutoff_time,
        evidence=[], graph_payload=graph_payload, time_note=time_note["text"])
    return {
        "qid": qid, "question": str(row.get("question") or "").strip(),
        "group": B1_GROUP_TAG,
        "k": int(ret_cfg.require_fixed("K")), "n": int(ret_cfg.require_fixed("N")),
        "context_token_budget": int(ret_cfg.require_fixed("context_token_budget")),
        "task_type": row.get("task_type"),
        "gold_hop_depth": row.get("gold_hop_depth"),
        "dataset_version": dataset_version, "data_cutoff_time": data_cutoff_time,
        "evidence": [], "graph_payload": graph_payload,
        "token_account": {"text_tokens": 0, "path_tokens": 0, "event_triple_tokens": 0,
                          "graph_tokens": 0, "total_tokens": 0},
        "prompt": {"system": built["system"], "user": built["user"],
                   "sha256": built["sha256"]},
        "time_note": time_note,
        "checks": {"evidence_le_k": True, "order_matches_trace": True, "within_budget": True,
                   "corpus_lookup_ok": None, "k_n_match_config": True,
                   "graph_payload_passthrough": True, "retrieval_used": False},
    }


def run_b1_one(qid: str, row: dict, out_root: str, ret_cfg, dataset_meta: dict,
               questions_file: str) -> dict:
    """跑 Baseline 1 的一题：装配在父进程，**生成在纯子进程**（隔离 config 同名陷阱）。

    **`questions_file` 必须与 A～E 走同一条只读注入**：B1 的子进程虽然不接入检索，
    但它的**记录层**（`B1_CHILD_CODE` 里的 `config.identifiers_for(case["qid"])`
    → `hist.build_record`）同样要解析 `FQ-<数字>`；不注入时答案侧 config 仍只认
    `PE-<数字>`，120 题的 `answer_id` 会**全部退化成 `A-CUSTOM`**，按 answer_id 聚合的
    `qa_records.jsonl` 于是只剩 1 行（逐题目录里各自仍是完整的）。故这里的
    `subprocess.run(...)` 与 `run_one()` 一样包在 `injected_questions()` 里。
    """
    out_dir = os.path.join(out_root, "逐题", B1_GROUP_TAG, qid)
    os.makedirs(out_dir, exist_ok=True)
    case_path = os.path.join(out_dir, "b1_case.json")
    write_json(case_path, build_b1_case(qid, row, ret_cfg, dataset_meta))
    cmd = [sys.executable, "-c", B1_CHILD_CODE, ANSWER_DIR, case_path, out_dir,
           SESSION_ID, FIXED_NOW]
    started = datetime.now()
    # 与 `run_one()` 逐字同构：子进程在 shim 注入的上下文里启动（PYTHONPATH 前置 sitecustomize）。
    with injected_questions(questions_file):
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=3600)
    secs = (datetime.now() - started).total_seconds()
    detail = {}
    for line in reversed((proc.stdout or "").strip().split("\n")):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                detail = json.loads(line)
                break
            except Exception:  # noqa: BLE001
                continue
    produced = os.path.isfile(os.path.join(out_dir, "answer_trace.jsonl"))
    ok = proc.returncode == 0 and bool(detail.get("ok")) and produced
    return {"ok": ok, "exit_code": proc.returncode, "out_dir": rel(out_dir),
            "seconds": round(secs, 2), "detail": detail,
            "stdout_tail": "\n".join((proc.stdout or "").strip().split("\n")[-8:]),
            "stderr_tail": (proc.stderr or "")[-800:]}


# ===========================================================================
# 五、聚合与指标（与 跑AC对照.py **同一套口径**）
# ===========================================================================
_ANSWER_ID_RE = None


def _answer_id_of(record_text: str):
    global _ANSWER_ID_RE
    if _ANSWER_ID_RE is None:
        import re as _re
        _ANSWER_ID_RE = _re.compile(r"['\"]answer_id['\"]\s*:\s*['\"]([^'\"]+)['\"]")
    m = _ANSWER_ID_RE.search(str(record_text or ""))
    return m.group(1) if m else None


def merge_jsonl(path: str, new_rows: list, key) -> list:
    """按 key 合并写回：同键的新行覆盖旧行（支持"先跑满、再补跑失败题"）。"""
    merged = {}
    for row in collect_rows(path):
        k = key(row)
        if k is not None:
            merged[k] = row
    for row in new_rows:
        k = key(row)
        if k is not None:
            merged[k] = row
    out = [merged[k] for k in sorted(merged)]
    write_jsonl(path, out)
    return out


def retrieval_metrics(trace_rows: list, questions: dict, keep, *, group=None) -> dict:
    """在 keep 选出的题上算四项指标；逐题取值后按题取算术平均（《02》第12.7节）。

    **Baseline 1 不做检索**：四项指标在定义上不可计算，返回 applicable=false ＋ 数值 null
    （不写 0.0 —— 0.0 会被读成"检索了但全漏"）。
    """
    sel = [r for r in trace_rows if keep(questions.get(r["qid"], {}))]
    if not sel:
        return {"n_questions": 0, "applicable": False,
                "reason": "该范围内没有题（或产出里没有这些题的 trace 行）"}
    if group == B1_GROUP_TAG:
        return {"n_questions": len(sel), "applicable": False,
                "K": int(sel[0].get("k") or 0), "retrieval_metrics": None,
                "recall_at_k": None, "precision_at_k": None, "mrr": None,
                "complete_evidence_recall_at_k": None,
                "evidence_count_mean": 0.0,
                "graph_evidence_in_final_total": 0, "graph_evidence_per_question": 0.0,
                "reason": ("Baseline 1 = 闭卷 LLM，不接入检索：证据集合恒为空，"
                           "四项检索指标在定义上不可计算，故登记为 null（不是 0.0）。")}
    acc = {k: 0.0 for k in METRIC_KEYS}
    n_graph_ev = 0
    for row in sel:
        q = questions.get(row["qid"], {})
        gold = set(int(x) for x in (q.get("gold_evidence_chunk_ids") or []))
        ev = [int(x["chunk_id"]) for x in row["evidence"]]
        K = int(row["k"])
        hit = len(gold & set(ev))
        ranks = [i + 1 for i, c in enumerate(ev) if c in gold]
        acc["recall_at_k"] += (hit / len(gold)) if gold else 0.0
        acc["precision_at_k"] += hit / K
        acc["mrr"] += (1.0 / ranks[0]) if ranks else 0.0
        acc["complete_evidence_recall_at_k"] += 1.0 if gold and gold <= set(ev) else 0.0
        n_graph_ev += sum(1 for x in row["evidence"] if x.get("from_graph"))
    n = len(sel)
    out = {"n_questions": n, "applicable": True, "K": int(sel[0]["k"])}
    for k in METRIC_KEYS:
        out[k] = round(acc[k] / n, 6)
    out["graph_evidence_in_final_total"] = n_graph_ev
    out["graph_evidence_per_question"] = round(n_graph_ev / n, 4)
    return out


def machine_checks(trace_rows: list, *, group=None) -> dict:
    """机检可核的问答侧统计（**不含**人工 0/1/2 评分）。B1 另加"零证据一致性"检查。"""
    n = len(trace_rows)
    if not n:
        return {"n_questions": 0}
    gate_ok = sum(1 for r in trace_rows if not (r.get("gates") or {}).get("failures"))
    graph_ext = sum(1 for r in trace_rows if r.get("is_graph_extended"))
    zero_hop_leak = sum(1 for r in trace_rows
                        if not r.get("is_graph_extended")
                        and (r.get("graph_payload") or {}).get("graph_path"))
    body_lens = [len(str(r.get("body_text") or "")) for r in trace_rows]
    tokens = [int((r.get("token_account") or {}).get("total_tokens") or 0) for r in trace_rows]
    ev = [int(r.get("evidence_count") or 0) for r in trace_rows]
    secs = [round(sum(float(a.get("seconds") or 0) for a in (r.get("attempts") or [])), 3)
            for r in trace_rows]
    out = {
        "n_questions": n,
        "gate_pass": gate_ok, "gate_pass_rate": round(gate_ok / n, 4),
        "is_graph_extended": graph_ext,
        "zero_hop_graph_path_leak": zero_hop_leak,
        "evidence_count_mean": round(sum(ev) / n, 4),
        "evidence_count_min": min(ev), "evidence_count_max": max(ev),
        "body_chars_mean": round(sum(body_lens) / n, 1),
        "body_chars_min": min(body_lens), "body_chars_max": max(body_lens),
        "empty_body": sum(1 for x in body_lens if x == 0),
        "total_tokens_mean": round(sum(tokens) / n, 1), "total_tokens_max": max(tokens),
        "llm_seconds_mean": round(sum(secs) / n, 3), "llm_seconds_max": max(secs),
        "human_scoring": "NOT_DONE",
        "human_scoring_note": (
            "本次**未执行**答案评分（《02》第12.7节 的 0／1／2 量表：Answer Accuracy／"
            "Completeness／Faithfulness）。该量表自 v3.9 起**改走跨厂商模型评审（模型评分）**"
            "——主 judge kimi（kimi-k3）、副 judge 智谱（glm-5.3-flash），副 judge 对 ≥20% 样本做"
            "跨模型交叉核对；**不存在「人工评分」这一步**，**模型评分不是人工评分**。"
            "本表任何数字都是**机检量**，不得当成答案质量分；《02》第12.8节 判定条件的后半句"
            "「Answer Accuracy 不下降」**待按模型评分口径补做后方可判定**（本次未跑评分）。"),
        "scoring_line": SCORING_LINE,
    }
    if group == B1_GROUP_TAG:
        out["b1_evidence_nonzero_violations"] = sum(1 for x in ev if x != 0)
        out["b1_graph_path_nonzero_violations"] = sum(
            1 for r in trace_rows if (r.get("graph_payload") or {}).get("graph_path"))
        out["b1_retrieval_used_false"] = sum(
            1 for r in trace_rows if r.get("retrieval_used") is False)
    return out


# ===========================================================================
# 六、报告渲染
# ===========================================================================
def _fmt(value) -> str:
    return "—" if value is None else str(value)


def _metrics_table(title: str, metric_keys, result: dict, groups: list, scope_name: str) -> list:
    lines = ["#### " + title, "",
             "| 指标 | " + " | ".join(groups) + " |",
             "| --- | " + " | ".join(["---"] * len(groups)) + " |"]
    block = result["subsets_named"].get(scope_name) or {}
    for key, label in metric_keys:
        lines.append("| %s | %s |" % (label, " | ".join(
            _fmt((block.get(g) or {}).get(key)) for g in groups)))
    lines.append("| 题数 | %s |" % " | ".join(
        str((block.get(g) or {}).get("n_questions")) for g in groups))
    return lines


def render_md(result: dict) -> str:
    groups = list(result["groups"])
    F = result["frozen"]
    scope = result["report_scope"]
    n_all = result["question_counts"]["all"]
    n_core = result["question_counts"]["core"]
    n_stress = result["question_counts"]["stress"]
    L = ["# 正式对照报告（A～E 消融 ＋ Baseline 1 辅助基线）", "",
         "> 生成脚本：`交付物/06-实验与评测\\工具\\跑正式对照.py`"
         "（不重新实现检索与生成，逐题转发冻结入口 `代码\\问答\\run_answer.py`）",
         "> 题集：`%s`（共 %d 题）" % (result["question_set"], n_all),
         "> 冻结配置：K=%s、N=%s、Context Token Budget=%s、g=%s、model=%s、temperature=%s、"
         "Prompt=%s" % (F.get("K"), F.get("N"), F.get("budget"), F.get("g"),
                        F.get("model"), F.get("temperature"), F.get("prompt_version")),
         "> **组别定义**："]
    for g in groups:
        L.append("> * %s" % GROUP_ROLE.get(g, g))
    L += ["",
          "**报告范围的分工（《02》第12.2节）**",
          "",
          "| 范围 | 题数 | 报告方式 |",
          "| --- | --- | --- |",
          "| 全部测试集 | %d | 仅总览；**不是**任何判定的依据 |" % n_all,
          "| 核心测试集 | %d | 主结果（《02》第12.8节 的判定以核心集为依据） |" % n_core,
          "| 压力测试子集（关系型 + 2 跳 + 有时间约束） | %d | "
          "**单独报告，绝不并入核心集总体平均** |" % n_stress,
          "",
          "> 压力子集识别方式：%s。" % scope["stress_source"],
          ""]

    # ---- 一、核心集 ----
    L += ["## 一、四项检索指标（核心集 %d 题；主结果）" % n_core, ""]
    L += _metrics_table(
        "1.1 核心集 %d 题" % n_core,
        (("recall_at_k", "Recall@K"), ("precision_at_k", "Precision@K"), ("mrr", "MRR"),
         ("complete_evidence_recall_at_k", "**Complete Evidence Recall@K**")),
        result, groups, "core")
    core_block = result["subsets_named"].get("core", {})
    L += ["", "| 图谱来源证据 | " + " | ".join(groups) + " |",
          "| --- | " + " | ".join(["---"] * len(groups)) + " |",
          "| 合计 | %s |" % " | ".join(_fmt((core_block.get(g) or {}).get(
              "graph_evidence_in_final_total")) for g in groups),
          "| 每题 | %s |" % " | ".join(_fmt((core_block.get(g) or {}).get(
              "graph_evidence_per_question")) for g in groups),
          "",
          "**读法**：《02》第12.8节 的判定要求 `Complete Evidence Recall@K` 相对基线**提高**。"
          "Baseline 1 不接入检索，其四项检索指标按定义不可计算，一律记 `—`（null），"
          "**不得读成 0.0**。", ""]

    # ---- 二、压力子集 ----
    L += ["## 二、压力测试子集（%d 题，**单独报告，不并入核心集总体平均**）" % n_stress, ""]
    if n_stress == 0:
        L += ["> 本次未识别出压力子集题（--stress-rule 或题集标记的问题），本节为空。", ""]
    else:
        L += _metrics_table(
            "2.1 压力子集 %d 题" % n_stress,
            (("recall_at_k", "Recall@K"), ("precision_at_k", "Precision@K"), ("mrr", "MRR"),
             ("complete_evidence_recall_at_k", "**Complete Evidence Recall@K**")),
            result, groups, "stress")
        L += ["", "> 压力子集可作为附加观察参与讨论，"
                  "**不作为《02》第12.8节 主体判定的依据**（该节明文）。", ""]

    # ---- 三、全部题集总览 ----
    L += ["## 三、全部测试集总览（%d 题；仅总览，不作判定依据）" % n_all, ""]
    L += _metrics_table(
        "3.1 全部 %d 题" % n_all,
        (("recall_at_k", "Recall@K"), ("precision_at_k", "Precision@K"), ("mrr", "MRR"),
         ("complete_evidence_recall_at_k", "**Complete Evidence Recall@K**")),
        result, groups, "all")
    L.append("")

    # ---- 四、逐子集 ----
    L += ["## 四、逐子集（《02》第12.8节：按子集分别判定，不合并；允许重叠）", "",
          "### 4.1 Complete Evidence Recall@K（核心集 %d 题内）" % n_core, "",
          "| 子集 | 题数 | " + " | ".join(groups) + " |",
          "| --- | --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for name, _ in SUBSETS:
        per = result["subsets_named_core"].get(name) or {}
        n = (per.get(groups[0]) or {}).get("n_questions")
        L.append("| %s | %s | %s |" % (name, n, " | ".join(
            _fmt((per.get(g) or {}).get("complete_evidence_recall_at_k")) for g in groups)))
    L += ["", "### 4.2 Recall@K（核心集 %d 题内）" % n_core, "",
          "| 子集 | 题数 | " + " | ".join(groups) + " |",
          "| --- | --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for name, _ in SUBSETS:
        per = result["subsets_named_core"].get(name) or {}
        n = (per.get(groups[0]) or {}).get("n_questions")
        L.append("| %s | %s | %s |" % (name, n, " | ".join(
            _fmt((per.get(g) or {}).get("recall_at_k")) for g in groups)))
    L.append("")

    # ---- 五、问答侧机检量 ----
    L += ["## 五、问答侧机检量（**不是质量分**）", "",
          "| 量 | " + " | ".join(groups) + " |",
          "| --- | " + " | ".join(["---"] * len(groups)) + " |"]
    for key, label in (("n_questions", "题数"), ("gate_pass", "门禁通过题数"),
                       ("is_graph_extended", "标注为使用图谱扩展的题数"),
                       ("zero_hop_graph_path_leak", "零跳却出现图谱路径（应为 0）"),
                       ("evidence_count_mean", "证据条数均值"),
                       ("body_chars_mean", "正文平均字数"), ("empty_body", "空正文题数"),
                       ("total_tokens_mean", "上下文 token 均值"),
                       ("llm_seconds_mean", "单次生成平均耗时(s)")):
        L.append("| %s | %s |" % (label, " | ".join(
            _fmt((result["machine"].get(g) or {}).get(key)) for g in groups)))
    L += ["",
          "> **%s**。" % SCORING_LINE, ""]

    # ---- 六、Baseline 1 如实标注 ----
    if B1_GROUP_TAG in groups:
        m = result["machine"].get(B1_GROUP_TAG) or {}
        L += ["## 六、Baseline 1 的如实标注（不接入检索）", "",
              "| 检查项 | 结果 |", "| --- | --- |",
              "| 证据条数非 0 的违规题数（应为 0） | %s |"
              % _fmt(m.get("b1_evidence_nonzero_violations")),
              "| 出现非空图谱路径的违规题数（应为 0：0 跳组不得生成虚构图谱路径） | %s |"
              % _fmt(m.get("b1_graph_path_nonzero_violations")),
              "| 标注 `retrieval_used=false` 的题数 | %s |" % _fmt(m.get("b1_retrieval_used_false")),
              "| 证据条数均值（恒为 0） | %s |" % _fmt(m.get("evidence_count_mean")),
              "| 门禁通过题数（B1 无证据可引，`citation_missing` 必然触发；**不用它判失败**） | %s／%s |"
              % (_fmt(m.get("gate_pass")), _fmt(m.get("n_questions"))),
              "",
              "> Baseline 1 = 直接调用 LLM、**不给任何检索证据**。它依赖参数化知识，"
              "且其训练语料的时间边界与数据集不一致，**只作辅助观察**，"
              "不作为「KG-RAG 有效」的主要证据（《02》第12.5节）。",
              "> 它的答案第 3 段由代码写固定标注「本次回答未使用图谱扩展」，"
              "`graph_path` 与 `event_triples` 恒为空数组——**不得**生成或展示虚构的图谱路径"
              "（《02》第十三章）。",
              ""]

    # ---- 七、失败清单 ----
    # `--report-only` 只从已聚合的 answer_trace.jsonl 重算，**不重新收集 failures**，
    # 故 `result["failures"]` 在这个档下恒为空；照旧打印「全部成功落盘」会与真实有效题数
    # （各表『题数』行）不符——那是一句**误导性**的话。本清单在 report-only 下改为
    # 按各组与题集的**差集**如实给出「未通过题数 ＋ 题号」，并在标题上标明本档的清单来源。
    L += ["## 七、失败清单", ""]
    if result.get("report_only"):
        # report-only 不重跑任何题、不重新收集运行期失败 → 失败清单改为「题集 × 已聚合产出」的
        # 差集（只存题号，不把全部记录塞进 JSON）。逐题退出码只在生成档的报告里给出。
        selected = list(result.get("qids") or [])
        mq_of = result.get("trace_qids") or {}
        mq = {g: [q for q in selected
                  if q not in set(mq_of.get(g) or [])]
              for g in groups}
        L += ["> **本清单在 `--report-only` 下由「题集 × 各组已聚合产出」的差集现场比对得出**"
              "（该档按定义不重跑任何题、不重新收集运行期失败，故**不给出**逐题的退出码与 "
              "stdout／stderr 尾部）。本节此前固定打印「全部成功落盘」，与本档的真实有效题数"
              "（A113／B118／C117／D117／E117／B1 120）不符，自本次起改为如实给出差集。"
              "**逐题退出码与报错尾部只在生成档（正式跑）的报告里给出。**",
              "",
              "| 组 | 题集题数 | 有效题数 | 未通过题数 | 未通过题号（按题集顺序） |",
              "| --- | --- | --- | --- | --- |"]
        for g in groups:
            bad = sorted(mq.get(g) or [])
            L.append("| %s | %d | %d | %d | %s |"
                     % (g, len(selected), len(selected) - len(bad), len(bad),
                        "—" if not bad else "、".join(bad)))
        total_missing = sum(len(v) for v in mq.values())
        if total_missing:
            L += ["", "> 未通过题数合计 **%d**（＝题集 %d 题 × %d 组 − 已聚合有效的 %d 题组）；"
                      "上述题号可用 `--only-qids <题号>` 补跑，补跑后重出本报告。"
                      % (total_missing, len(selected), len(groups),
                         len(selected) * len(groups) - total_missing)]
        else:
            L += ["", "> 本次差集为空：题集 %d 题在 %d 组上均已聚合落盘。"
                      % (len(selected), len(groups))]
    elif result["failures"]:
        L += ["| 组 | 题号 | 退出码 | 原因（stdout／stderr 尾部） |",
              "| --- | --- | --- | --- |"]
        for f in result["failures"]:
            why = (str(f.get("stdout_tail") or "") + " " + str(f.get("stderr_tail") or ""))
            L.append("| %s | %s | %s | %s |"
                     % (f["group"], f["qid"], f["exit_code"],
                        why.replace("\n", " ").replace("|", "/")[:200]))
    else:
        L.append("无（本次生成档：%d 组 × %d 题全部成功落盘）"
                 % (len(groups), len(result["qids"])))
    L.append("")

    # ---- 八、口径纪律 ----
    L += ["## 八、结论该怎么写（口径纪律）", "",
          "1. **本报告的机检量不含答案质量分（评分口径见《02》第12.7节）**：%s。" % SCORING_LINE,
          "   本报告里**没有任何**答案质量分；机检量（门禁通过率、引用越界、空正文、"
          "token 账、耗时）不得改写成 Accuracy／Completeness／Faithfulness。",
          "2. **判定按子集分别进行**（《02》第12.8节）：关系型／多跳型／时序型各自独立应用"
          "同一条规则——CER@K 高于 Vector RAG **且** Answer Accuracy 不下降。"
          "三个子集允许重叠，判定互不牵连，不得合并成一个整体。",
          "3. **判定以核心集为依据**：压力子集仅作附加观察，不作为该节主体判定依据。",
          "4. **Baseline 1 只作辅助观察**，其四项检索指标不可计算（登记为 null）。",
          "5. **三种结果都是有效结论**，不得为了让图表好看而回头调 K／N／g 或挑子集。",
          "6. **E 组独立报告**：E = D + 证据排序，属「进一步优化实验」，不并入 RQ3"
          "（《02》第12.6节）。B／C 的差异表示「在直接关系基础上继续扩展两跳带来的变化」"
          "（C 含 B，不是排除 B）；H3 由 **C → D** 回答。",
          "7. **B 与 C 不是干净嵌套**：候选池嵌套，但受五步契约影响最终证据集合不嵌套"
          "（见《评审\\第3步执行记录.md》第 1.5 节），论文不得写成「嵌套消融、只差一跳」。",
          ""]
    return "\n".join(L) + "\n"


# ===========================================================================
# 七、零调用档
# ===========================================================================
def estimate_calls(n_questions: int, groups: list, retry_cap: int = 2) -> dict:
    """调用次数预算：每次「题 × 组」至少 1 次请求；空正文重试规则下最多 2 次。"""
    base = n_questions * len(groups)
    return {"per_group": {g: n_questions for g in groups}, "base": base,
            "max_with_retry": base * retry_cap, "retry_cap": retry_cap,
            "note": ("每次「题 × 组」= 1 次请求；《21》v1.3 空正文重试规则下最多 2 次，"
                     "故上限 = 基数 × 2。检索侧（问题向量化与图谱查询）与大模型调用无关，"
                     "不计入本预算。")}


def latency_reference() -> dict:
    """从既有 30 题 × 5 组 v1.3 产出取**实测**单次生成耗时，作为时长估算依据（只读）。"""
    rows = []
    for g in A_TO_E:
        rows += collect_rows(os.path.join(STAGE10, "对照产出_v13", g, "answer_trace.jsonl"))
    secs, tokens = [], []
    for r in rows:
        secs.append(round(sum(float(a.get("seconds") or 0) for a in (r.get("attempts") or [])), 3))
        tokens.append(int((r.get("token_account") or {}).get("total_tokens") or 0))
    if not secs:
        return {"available": False, "source": "（既有 30 题 × 5 组产出不可读）"}
    xs = sorted(secs)
    p95 = xs[max(0, math.ceil(0.95 * len(xs)) - 1)]
    return {"available": True,
            "source": "交付物/06-实验与评测/对照产出_v13/{A..E}/answer_trace.jsonl",
            "n": len(secs), "mean_seconds": round(sum(secs) / len(secs), 3),
            "p95_seconds": p95, "max_seconds": max(secs),
            "mean_total_tokens": round(sum(tokens) / len(tokens), 1),
            "max_total_tokens": max(tokens)}


def do_dry_run(groups: list, qids: list, out_dir: str, questions_file: str, scopes: dict,
               load_error: str | None = None) -> int:
    plan = estimate_calls(len(qids), groups)
    lat = latency_reference()
    log("=" * 78)
    log("--dry-run：只打印计划，**0 次模型调用、不落任何产出**")
    log("=" * 78)
    log("题集文件：%s（存在=%s）" % (rel(questions_file), os.path.isfile(questions_file)))
    if load_error:
        log("**题集不可用，如实报出（不静默、不崩栈）**：%s" % str(load_error).replace("\n", " "))
        log("  下面的题数与调用预算是【按 0 题】给出的占位读数；题集建好后再跑本档即为真值。")
    log("参与运行的题数：%d（全部 %d／核心 %d／压力 %d）"
        % (len(qids), len(scopes["all_qids"]), len(scopes["core"]), len(scopes["stress"])))
    log("组：%s" % "、".join(groups))
    log("产出根：%s" % rel(out_dir))
    log("")
    log("逐题动作：")
    for g in groups:
        if g == B1_GROUP_TAG:
            log("  [B1] 装配（0 证据；图谱载荷 = 未使用图谱扩展标记）")
            log("       → answer.call_model()（deepseek-flash／temperature=0／Prompt v1.0）")
            log("       → prompt.compose_answer() 四段合成 → answer.gate() 机检（照实记录、不判失败）")
        else:
            log("  [%s] 子进程：python %s --qid <qid> --group %s --out-dir <逐题目录>"
                % (g, rel(RUN_ANSWER), g))
            log("       其中检索侧经 PYTHONPATH shim **只读注入** --questions-file（不改冻结文件）")
    log("")
    log("模型调用次数预算：")
    log("  每次「题 × 组」= 1 次请求")
    log("  基数 = %d 题 × %d 组 = **%d 次**" % (len(qids), len(groups), plan["base"]))
    log("  上限（含空正文重试，最多 2 次/题组）= %d 次" % plan["max_with_retry"])
    for g in groups:
        log("    %-3s %d 次" % (g, plan["per_group"][g]))
    log("  按《02》第12.2节 的完整版题量（120 题 = 核心 108 + 压力 12）折算：%d 次"
        % estimate_calls(120, groups)["base"])
    log("  检索侧（问题向量化 ＋ 图谱查询）不调用大模型，不计入本预算")
    log("")
    log("时长估算（依据 = 既有 30 题 × 5 组 v1.3 产出的实测单次生成耗时）：")
    if lat.get("available"):
        ref = estimate_calls(120, groups)["base"]
        log("  —— 本次参与题数 %d 的实际值 ——" % len(qids))
        log("  实测单次生成：均值 %.3f s／P95 %.3f s／最大 %.3f s（n=%d）"
            % (lat["mean_seconds"], lat["p95_seconds"], lat["max_seconds"], lat["n"]))
        log("  纯生成下限 ≈ %d 次 × %.3f s = %.1f 分钟（%.2f 小时）"
            % (plan["base"], lat["mean_seconds"],
               plan["base"] * lat["mean_seconds"] / 60.0,
               plan["base"] * lat["mean_seconds"] / 3600.0))
        log("  按 P95 估计 ≈ %d 次 × %.3f s = %.1f 分钟（%.2f 小时）"
            % (plan["base"], lat["p95_seconds"],
               plan["base"] * lat["p95_seconds"] / 60.0,
               plan["base"] * lat["p95_seconds"] / 3600.0))
        log("  另加检索侧子进程开销（每题约 8～12 s × %d 个非 B1 组）"
            "→ 墙钟预计 %.2f～%.2f 小时"
            % (len([g for g in groups if g != B1_GROUP_TAG]),
               plan["base"] * lat["mean_seconds"] / 3600.0
               + len(qids) * len([g for g in groups if g != B1_GROUP_TAG]) * 8 / 3600.0,
               plan["base"] * lat["p95_seconds"] / 3600.0
               + len(qids) * len([g for g in groups if g != B1_GROUP_TAG]) * 12 / 3600.0))
        log("  —— 按《02》第12.2节 完整版题量（120 题）折算 ——")
        log("  %d 次 × 均值 %.3f s = %.1f 分钟（%.2f 小时）；按 P95 = %.1f 分钟（%.2f 小时）；"
            "含检索侧开销的墙钟预计 %.1f～%.1f 小时"
            % (ref, lat["mean_seconds"], ref * lat["mean_seconds"] / 60.0,
               ref * lat["mean_seconds"] / 3600.0,
               ref * lat["p95_seconds"] / 60.0, ref * lat["p95_seconds"] / 3600.0,
               ref * lat["mean_seconds"] / 3600.0
               + 120 * len([g for g in groups if g != B1_GROUP_TAG]) * 8 / 3600.0,
               ref * lat["p95_seconds"] / 3600.0
               + 120 * len([g for g in groups if g != B1_GROUP_TAG]) * 12 / 3600.0))
    else:
        log("  既有产出不可读，无法给出实测依据（见 实验方案\\跑法说明.md 的估算公式）")
    log("")
    log("不落任何产出；正式运行请去掉 --dry-run。")
    return 0


def _csv_index(path: str, key: str) -> dict:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return {row[key]: row for row in csv.DictReader(fh)}


def do_preflight(questions_file: str, groups: list, stress_expect: int, check_bridge: bool) -> int:
    """**0 次模型调用**的正式运行前置校验。任何一条不过都照实报出，不静默。"""
    findings = []

    def add(level, item, detail):
        findings.append({"level": level, "item": item, "detail": detail})

    log("=" * 78)
    log("--preflight：正式运行前置校验（**0 次模型调用**）")
    log("=" * 78)

    # ---------- 1. 冻结配置 ----------
    log("")
    log("[1/6] 冻结配置（《02》第12.4节 固定表）与现场实测值 ……")
    frozen = frozen_config()
    try:
        ret_cfg = load_retrieval_config_module()
    except SystemExit as exc:
        ret_cfg = None
        add("FAIL", "检索侧 config", str(exc))
    expected = {"K": 10, "N": 20, "budget": 3600, "g": 2, "temperature": 0,
                "prompt_version": "v1.0", "model": "deepseek-flash",
                "model_version": "deepseek-flash"}
    labels = {"K": "Top-K（K）", "N": "N（向量候选数）", "budget": "Context Token Budget",
              "g": "图谱侧保留份额 g", "temperature": "temperature",
              "prompt_version": "Prompt 版本", "model": "大语言模型",
              "model_version": "大语言模型版本"}
    for key, want in expected.items():
        got = frozen.get(key)
        same = (str(got) == str(want))
        log("  %-24s 冻结=%-16s 现场=%-16s %s"
            % (labels[key], want, got, "一致" if same else "**不一致**"))
        add("OK" if same else "FAIL", "《02》12.4 固定表 · %s" % labels[key],
            "冻结值 %s／现场实测 %s" % (want, got))
    if ret_cfg is not None:
        emb = getattr(ret_cfg, "EMBEDDING", {}) or {}
        for label, want, got in (
                ("Embedding 模型", "BAAI/bge-small-zh-v1.5", emb.get("model_name")),
                ("Embedding 版本", "7999e1d3359715c523056ef9478215996d62a620",
                 emb.get("revision"))):
            log("  %-24s 冻结=%-16s 现场=%-16s %s"
                % (label, want[:16], got, "一致" if got == want else "**不一致**"))
            add("OK" if got == want else "FAIL", "《02》12.4 固定表 · %s" % label,
                "冻结值 %s／现场实测 %s" % (want, got))
        ret = getattr(ret_cfg, "RETRIEVAL", {}) or {}
        log("  %-24s 现场=%s" % ("dataset_version", ret_cfg.DATASET_VERSION))
        log("  %-24s 现场=%s" % ("data_cutoff_time", ret_cfg.DATA_CUTOFF_TIME))
        log("  %-24s 现场=%s（《02》第12.7节 分母恒为 K）"
            % ("precision_denominator", ret.get("precision_denominator")))
        log("  %-24s 现场=%s（v2.9 裁定：空值一并剔除）"
            % ("time_filter_null_policy", ret.get("time_filter_null_policy")))
        add("INFO", "检索侧 config 现场读数",
            "dataset_version=%s；data_cutoff_time=%s；precision_denominator=%s；"
            "time_filter_null_policy=%s" % (ret_cfg.DATASET_VERSION, ret_cfg.DATA_CUTOFF_TIME,
                                            ret.get("precision_denominator"),
                                            ret.get("time_filter_null_policy")))
    if frozen.get("error"):
        add("FAIL", "冻结配置读取", frozen["error"])
    if frozen.get("answer_error"):
        add("FAIL", "冻结配置读取", frozen["answer_error"])
    for item in frozen.get("errors") or []:
        add("FAIL", "冻结配置读取", item)

    # ---------- 2. 题集 schema ----------
    log("")
    log("[2/6] 题集 schema：%s" % rel(questions_file))
    questions = {}
    if not os.path.isfile(questions_file):
        add("FAIL", "题集存在性",
            "%s 不存在（该文件由「正式测试集建设」那一路任务产出，此刻可能尚未生成）"
            % rel(questions_file))
        log("  **题集不存在** —— schema／gold／时间窗口检查跳过，其余检查照跑")
    else:
        try:
            questions = load_questions(questions_file)
            log("  读入 %d 题" % len(questions))
            add("OK", "题集存在性", "%s（%d 题）" % (rel(questions_file), len(questions)))
        except SystemExit as exc:
            add("FAIL", "题集读取", str(exc))
            log("  **题集读取失败**：%s" % exc)

    if questions:
        missing_by_field = {f: [] for f in REQUIRED_FIELDS}
        bad_values, empty_gold, gold_over_k = [], [], []
        for qid, row in sorted(questions.items()):
            for field in REQUIRED_FIELDS:
                if row.get(field) in (None, "", []):
                    missing_by_field[field].append(qid)
            if str(row.get("question") or "").strip() == "":
                missing_by_field["question"].append(qid)
            if row.get("task_type") not in TASK_TYPES:
                bad_values.append((qid, "task_type", row.get("task_type")))
            hop = row.get("gold_hop_depth")
            if not isinstance(hop, int) or isinstance(hop, bool) or hop not in HOP_DEPTHS:
                bad_values.append((qid, "gold_hop_depth", hop))
            if row.get("time_constraint") not in TIME_CONSTRAINTS:
                bad_values.append((qid, "time_constraint", row.get("time_constraint")))
            gold = row.get("gold_evidence_chunk_ids") or []
            if not gold:
                empty_gold.append(qid)
            if len(gold) > int(frozen.get("K") or 10):
                gold_over_k.append((qid, len(gold)))
        for field, bad in missing_by_field.items():
            if bad:
                add("FAIL", "题集 schema · 缺字段 %s" % field,
                    "%d 题缺失，例如 %s" % (len(bad), "、".join(bad[:5])))
        if bad_values:
            add("FAIL", "题集 schema · 取值域",
                "%d 处越界，例如 %s" % (len(bad_values),
                                        "；".join("%s.%s=%r" % x for x in bad_values[:5])))
        # ---- qid 前缀：**正向断言**（不是"按前缀放行"的白名单）----
        # 白名单只是对 `identifiers_for()` 行为的一句猜测，会随题集口径漂移而悄悄过期；
        # 这里改成**真跑一遍**：在与正式跑同一条 shim 注入下，让冻结的
        # `config.identifiers_for()` 逐题解析，断言 ① 拿到的是答案侧那份 config、
        # ② 答案侧读的题集就是正式题集、③ 没有任何一题退化成 Q-CUSTOM／A-CUSTOM、
        # ④ 记录层标识互不重复。任何一条不成立都是 FAIL，并**指名**是哪种不成立。
        id_probe = probe_qid_identifiers(questions_file, sorted(questions))
        log("  qid → 记录层标识（shim 注入后真跑 identifiers_for）：%s"
            % ("OK" if id_probe["ok"] else "**不成立**"))
        add("OK" if id_probe["ok"] else "FAIL", "题集 schema · qid 前缀（可解析性）",
            id_probe["detail"])
        if empty_gold:
            add("FAIL", "题集 schema · gold 缺失",
                "%d 题没有 gold 证据块，例如 %s" % (len(empty_gold), "、".join(empty_gold[:5])))
        if gold_over_k:
            add("FAIL", "题集 schema · gold 超过 K",
                "%d 题的 gold 证据块数 > K=%s（该题 CER@K 在定义上必为 0；"
                "《02》第12.2节 要求不得保留这类题），例如 %s"
                % (len(gold_over_k), frozen.get("K"),
                   "；".join("%s(%d 块)" % x for x in gold_over_k[:5])))
        if not any(missing_by_field.values()) and not bad_values and id_probe["ok"] \
                and not empty_gold and not gold_over_k:
            add("OK", "题集 schema", "必需字段、取值域、qid 可解析性、gold 数量全部通过")
            log("  schema 全部通过（%d 题）" % len(questions))
        # ---- 与 30 题预实验集的**内容级**去重守卫（不得为了让它过而删掉）----
        # `main()` 里那道 sha256 闸门在 --preflight 之前就已经拦过一次；这里把它作为
        # 一条**正向断言**登记进清单，让"这次跑的确实不是同一批题"在 preflight 报告里可见
        # （否则闸门只在退出时说话，报告里看不出它被评估过）。
        if os.path.isfile(QUESTIONS_PRE_EXPERIMENT):
            same_as_pre = (sha256_file(questions_file)
                           == sha256_file(QUESTIONS_PRE_EXPERIMENT))
            add("FAIL" if same_as_pre else "OK",
                "题集与 30 题预实验集不同（防「同一批题既调参又评测」）",
                ("**与预实验集逐字节相同** → main() 的守卫已拒绝运行（除非显式 "
                 "--allow-pre-experiment-set，而那样不得出正式结论）；本项一律判 FAIL。"
                 if same_as_pre else
                 "sha256 与 %s 不同；gold 与题干层面的独立核验见 测试集\\说明.md 第 2 节"
                 % rel(QUESTIONS_PRE_EXPERIMENT)))
            log("  与 30 题预实验集同内容 = %s（应为 False）" % same_as_pre)
        else:
            add("WARN", "题集与 30 题预实验集不同（防「同一批题既调参又评测」）",
                "预实验集文件不存在，无法比对：%s" % rel(QUESTIONS_PRE_EXPERIMENT))
        # qid -> 记录层标识（唯一性）——与本脚本自己的 digits 规则交叉核对一遍
        ids, collide = {}, []
        for qid in sorted(questions):
            digits = "".join(ch for ch in str(qid) if ch.isdigit())
            qid_num = ("Q-%s" % digits.zfill(3)) if digits else "Q-CUSTOM"
            if qid_num in ids:
                collide.append((ids[qid_num], qid))
            ids[qid_num] = qid
        if collide:
            add("FAIL", "记录层标识唯一性",
                "题号数字部分重复会导致 question_id／answer_id 撞车：%s"
                % "；".join("%s 与 %s" % c for c in collide[:5]))
        else:
            add("OK", "记录层标识唯一性", "%d 题的 Q-xxx／A-xxx 互不重复" % len(questions))

    # ---------- 3. 语料回查与时间窗口 ----------
    log("")
    log("[3/6] 逐题 gold 回查语料 ＋ 时间约束题的窗口自洽 ……")
    chunk_index, doc_index = {}, {}
    for path, index, key in ((CHUNKS_PATH, chunk_index, "chunk_id"),
                             (DOCUMENTS_PATH, doc_index, "doc_id")):
        if not os.path.isfile(path):
            add("FAIL", "语料存在性", "%s 不存在" % rel(path))
            continue
        for _, row in iter_jsonl(path):
            index[int(row[key])] = row
    log("  chunks=%d、documents=%d" % (len(chunk_index), len(doc_index)))

    dataset_meta = read_json(DATASET_META_PATH) if os.path.isfile(DATASET_META_PATH) else {}
    cutoff = str(dataset_meta.get("data_cutoff_time") or "")[:10]
    filterable = set()
    if os.path.isfile(NODES_CSV) and os.path.isfile(EDGES_CSV):
        try:
            # EVIDENCED_BY 的方向是 **Event --EVIDENCED_BY--> Document**：
            # `head_id` ＝ 事件 node_id（`EVT-xxxx`）、`tail_id` ＝ 文档 node_id（＝ `doc_id`）。
            # （现场核对：1098 个 head 全是 EVT-、tail 全是四位数 doc_id；方向搞反会算出 0 篇。）
            node_time = {nid: str(row.get("event_time") or "").strip()
                         for nid, row in _csv_index(NODES_CSV, "node_id").items()
                         if row.get("label") == "Event"}
            doc_events = {}
            with open(EDGES_CSV, "r", encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    if row.get("relation") != "EVIDENCED_BY":
                        continue
                    tail = str(row.get("tail_id") or "")
                    if not tail:
                        continue
                    doc_events.setdefault(int(tail), set()).add(row.get("head_id"))
            doc_dates = {did: {node_time[e] for e in events} - {""}
                         for did, events in doc_events.items()}
            filterable = {did for did, dates in doc_dates.items() if len(dates) >= 2}
            log("  EVIDENCED_BY 覆盖 %d 篇文档；其中 %d 篇含 >=1 个非空 event_time、"
                "%d 篇含 >=2 个不同事件日期（= 可过滤集合）"
                % (len(doc_events), sum(1 for d in doc_dates.values() if d), len(filterable)))
            add("INFO", "时间可过滤集合（现场从 v2.1_v1_3 导出物重算）",
                "口径＝文档在 EVIDENCED_BY 上的事件里 ≥2 个不同非空 event_time 日期；"
                "现场重算 %d 篇。（《16》登记口径）" % len(filterable))
            log("  （口径说明：v2.1\"补抽后\"度量文件的同名字段是 `docs_with_ge2_dated_events`＝177，"
                "口径为「≥2 个有日期的事件」；\n    与本项「≥2 个**不同**日期」不是同一口径，"
                "两者的差额已如实登记，勿混用。）")
        except Exception as exc:  # noqa: BLE001
            add("WARN", "时间可过滤集合",
                "现场重算失败（%s: %s），时间窗口检查降级为只做区间自洽"
                % (type(exc).__name__, exc))
    else:
        add("WARN", "时间可过滤集合", "nodes.csv／edges.csv 不存在，跳过金标准过滤自检")

    if questions:
        gold_missing, gold_doc_missing, gold_not_filterable, bad_windows = [], [], [], []
        for qid, row in sorted(questions.items()):
            gold = [int(x) for x in (row.get("gold_evidence_chunk_ids") or [])]
            miss = [c for c in gold if c not in chunk_index]
            if miss:
                gold_missing.append((qid, miss[:3]))
                continue
            doc_ids = {int(chunk_index[c]["doc_id"]) for c in gold}
            miss_doc = sorted(d for d in doc_ids if d not in doc_index)
            if miss_doc:
                gold_doc_missing.append((qid, miss_doc[:3]))
            if filterable and not (doc_ids & filterable):
                gold_not_filterable.append(qid)
            if row.get("time_constraint") == "有":
                window = row.get("time_window")
                problems = []
                if not isinstance(window, dict):
                    problems.append("缺 time_window")
                else:
                    lo = str(window.get("lo") or "")
                    hi = str(window.get("hi") or "")
                    label = str(window.get("label") or "")
                    basis = str(window.get("basis") or "")
                    empty = str(window.get("empty_policy") or "")
                    if not lo or not hi:
                        problems.append("窗口端点为空")
                    else:
                        try:
                            d_lo, d_hi = date.fromisoformat(lo), date.fromisoformat(hi)
                            if d_lo > d_hi:
                                problems.append("窗口下界 %s 晚于上界 %s" % (lo, hi))
                            if cutoff and d_hi > date.fromisoformat(cutoff):
                                problems.append("窗口上界 %s 晚于 data_cutoff 日期 %s"
                                                % (hi, cutoff))
                        except ValueError:
                            problems.append("窗口端点不是 ISO 日期")
                    if window.get("cutoff") and cutoff \
                            and str(window["cutoff"]) != str(dataset_meta.get("data_cutoff_time")):
                        problems.append("窗口内 cutoff 与 dataset.json 的 data_cutoff_time 不一致")
                    if empty and empty != "exclude":
                        problems.append("empty_policy=%s（《02》第12.7节 裁定为 exclude）" % empty)
                    if not label:
                        problems.append("缺窗口 label")
                    if basis and basis != "event_time":
                        problems.append("basis=%s（应恒为 event_time）" % basis)
                if problems:
                    bad_windows.append((qid, problems))
        if gold_missing:
            add("FAIL", "gold 回查 · chunk_id",
                "%d 题的 gold 块在 chunks.jsonl 里查不到，例如 %s（《21》验收 E5）"
                % (len(gold_missing), "；".join("%s→%s" % (q, m) for q, m in gold_missing[:5])))
        if gold_doc_missing:
            add("FAIL", "gold 回查 · doc_id",
                "%d 题的 gold 文档在 documents.jsonl 里查不到，例如 %s"
                % (len(gold_doc_missing),
                   "；".join("%s→%s" % (q, m) for q, m in gold_doc_missing[:5])))
        if not gold_missing and not gold_doc_missing:
            add("OK", "gold 回查", "%d 题的 gold 块与文档都能在语料里查到" % len(questions))
        if filterable and gold_not_filterable:
            add("WARN", "时间可过滤性（软提示）",
                "%d 题的 gold 文档全部落在「含 <2 个不同事件日期」的文档里（例如 %s）。"
                "D／E 的时间过滤只作用于**图谱侧候选**，故这不是阻断项；"
                "但这类题上「时间约束」很难产生可观察差异，建议登记为已知限制"
                % (len(gold_not_filterable), "、".join(gold_not_filterable[:6])))
        elif filterable:
            add("OK", "时间可过滤性（软提示）",
                "全部 %d 题的 gold 至少落在 1 篇可过滤文档内" % len(questions))
        if bad_windows:
            add("FAIL", "时间窗口自洽",
                "%d 题的 time_window 不自洽，例如 %s"
                % (len(bad_windows),
                   "；".join("%s(%s)" % (q, "、".join(p)) for q, p in bad_windows[:4])))
        else:
            add("OK", "时间窗口自洽", "全部时间约束题的窗口端点、cutoff、empty_policy、basis 自洽")

    # ---------- 4. 规模与构成 ----------
    log("")
    log("[4/6] 题集规模与压力子集识别 ……")
    counts = {"all": 0, "core": 0, "stress": 0}
    if questions:
        sc = classify_stress(questions, "auto")
        counts = {"all": len(questions), "core": len(sc["core"]), "stress": len(sc["stress"])}
        log("  全部 %d／核心 %d／压力 %d（识别方式：%s）"
            % (counts["all"], counts["core"], counts["stress"], sc["source"]))
        if counts["stress"] != stress_expect:
            add("WARN", "压力子集题数",
                "识别到 %d 题，与《02》第12.2节 的预期 %d 题不符（识别方式：%s）。"
                "压力子集必须单独报告；请核对题集的标记或标签"
                % (counts["stress"], stress_expect, sc["source"]))
        else:
            add("OK", "压力子集题数", "%d 题，与预期一致（%s）" % (counts["stress"], sc["source"]))
        cells = {}
        for row in questions.values():
            key = "%s+%s跳" % (row.get("task_type"), row.get("gold_hop_depth"))
            cells[key] = cells.get(key, 0) + 1
        log("  9 格构成：%s" % "；".join("%s=%d" % (k, cells[k]) for k in sorted(cells)))
        add("INFO", "9 格构成（仅供登记）",
            "；".join("%s=%d" % (k, cells[k]) for k in sorted(cells)))

    # ---------- 5. 调用数估算 ----------
    log("")
    log("[5/6] 调用次数与时长估算 ……")
    n_run = counts["all"]
    plan = estimate_calls(n_run, groups)
    lat = latency_reference()
    log("  参与题数 × 组数 = %d × %d = **%d 次**（上限含重试 %d 次）"
        % (n_run, len(groups), plan["base"], plan["max_with_retry"]))
    if lat.get("available"):
        log("  实测单次生成：均值 %.3f s／P95 %.3f s（n=%d）→ 纯生成下限 ≈ %.1f 分钟、"
            "按 P95 ≈ %.1f 分钟"
            % (lat["mean_seconds"], lat["p95_seconds"], lat["n"],
               plan["base"] * lat["mean_seconds"] / 60.0,
               plan["base"] * lat["p95_seconds"] / 60.0))
    add("INFO", "调用次数预算",
        "%d 题 × %d 组 = %d 次（上限 %d）" % (n_run, len(groups), plan["base"],
                                              plan["max_with_retry"]))

    # ---------- 6. 零调用自检（桥接只读注入 / B1 装配维度） ----------
    log("")
    log("[6/6] 零调用自检（**不发任何模型请求**）……")
    if not check_bridge:
        add("INFO", "桥接只读注入自检", "已按 --no-bridge-selftest 跳过")
        log("  已跳过（--no-bridge-selftest）")
    else:
        probe_file = questions_file if questions else QUESTIONS_PRE_EXPERIMENT
        probe_qid = sorted(questions)[0] if questions else "PE-01"
        probe_text = (str((questions.get(probe_qid) or {}).get("question") or "")
                      if questions else "")
        log("  探针题集：%s；探针题：%s" % (rel(probe_file), probe_qid))
        for label, fn in (("桥接只读注入自检（检索侧 run_query，只对 0 次模型调用）",
                           lambda: probe_retrieval_bridge(probe_file, probe_qid)),
                          ("答案侧桥接自检（run_answer --group A 跑到哨兵拦下，0 次模型调用）",
                           lambda: probe_answer_bridge_blocked(probe_file, probe_qid, probe_text)),
                          ("答案侧装配维度自检（run_answer --dry-run，预实验 PE-01）",
                           lambda: probe_answer_dry_run()),
                          ("B1 装配与落盘契约自检（哨兵拦截，0 次模型调用）",
                           lambda: probe_b1_blocked())):
            try:
                probe = fn()
                add(probe["level"], label, probe["detail"])
                log("  [%s] %s：%s" % (probe["level"], label, probe["detail"][:700]))
            except Exception as exc:  # noqa: BLE001
                add("FAIL", label, "自检本身抛错：%s: %s" % (type(exc).__name__, exc))
                log("  [FAIL] %s：%s: %s" % (label, type(exc).__name__, exc))

    # ---------- 汇总 ----------
    fails = [f for f in findings if f["level"] == "FAIL"]
    warns = [f for f in findings if f["level"] == "WARN"]
    audit = write_model_call_audit("--preflight", groups, {
        "failed": [{"item": f["item"], "detail": f["detail"]} for f in fails],
        "warned": [{"item": f["item"], "detail": f["detail"]} for f in warns],
        "question_set": rel(questions_file),
        "question_counts": counts,
    })
    log("")
    log("=" * 78)
    log("前置校验汇总：FAIL %d 项、WARN %d 项、其余 %d 项"
        % (len(fails), len(warns), len(findings) - len(fails) - len(warns)))
    log("=" * 78)
    for item in findings:
        if item["level"] in ("FAIL", "WARN"):
            log("[%s] %s：%s" % (item["level"], item["item"], item["detail"]))
    log("")
    if fails:
        log("**结论：前置校验未全部通过 → 不得直接跑正式全量。**")
        log("（本档是报告性检查：退出码仍为 0，是否放行由执行者裁定；"
            "检查结论以本清单为准。）")
    else:
        log("**结论：前置校验全部通过 → 可以跑正式全量。**")
    log("本档 0 次模型调用的审计登记：%s" % rel(audit))
    log("说明：本档 0 次模型调用、不落对照产出；退出码 = 0（检查结论见上）。")
    return 0


_BRIDGE_PROBE = r'''
import json, os, sys
# 父进程按 UTF-8 解码子进程 stdout；本探针不切编码的话，中文路径会被按 GBK 写出去，
# 父进程拿到的就是乱码路径——"注入对不对"于是变成一个假 FAIL（第 5 阶段同款坑）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass
ROOT, QID = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "检索"))
import config
path = config.QUESTION_FILES["questions"]
rows = list(config.iter_jsonl(path)) if os.path.isfile(path) else []
print(json.dumps({"questions_path": path, "config_file": config.__file__,
                  "n_rows": len(rows),
                  "has_qid": any(str(r.get("qid")) == QID for r in rows),
                  "shim": getattr(config, "STAGE10_SHIM", None)}, ensure_ascii=False))
'''

def _deep_clean(path: str) -> None:
    import shutil
    shutil.rmtree(path, ignore_errors=True)


def probe_retrieval_bridge(questions_file: str, qid: str) -> dict:
    """0 次大模型调用地验证「只读注入 → 检索侧按 --qid 取到指定题集里的题」。

    只调 `代码\\检索\\run_query.py`（A 组＝纯向量 ＋ 图谱查询，**本地 Embedding ＋ 读 CSV**，
    不发任何模型请求），并核对子进程读到的题集路径确实是注入后的那一份。
    """
    probe_out = os.path.join(STAGE10, "_正式对照-preflight", "run_query")
    _deep_clean(os.path.dirname(probe_out))
    os.makedirs(probe_out, exist_ok=True)
    record = os.path.join(probe_out, "record_%s.json" % qid.replace("/", "_"))
    with injected_questions(questions_file):
        who = subprocess.run([sys.executable, "-c", _BRIDGE_PROBE, ROOT, qid], cwd=ROOT,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace", timeout=300)
        proc = subprocess.run(
            [sys.executable, os.path.join(RETRIEVAL_DIR, "run_query.py"),
             "--qid", qid, "--group", "A", "--out", record, "--quiet"],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=1200)
    info = {}
    for line in reversed((who.stdout or "").strip().split("\n")):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                info = json.loads(line)
                break
            except Exception:  # noqa: BLE001
                continue
    got_path = str(info.get("questions_path") or "")
    path_ok = bool(got_path) and os.path.abspath(got_path) == os.path.abspath(questions_file)
    # 注入还得**打到对的那一份 config 上**：子进程里的 `config` 必须是检索侧那份，
    # 否则"读到的题集对了"也可能只是巧合（例如答成了预实验集的分支）。
    got_cfg = str(info.get("config_file") or "")
    cfg_ok = (bool(got_cfg)
              and os.path.normcase(os.path.abspath(got_cfg))
              == os.path.normcase(os.path.abspath(os.path.join(RETRIEVAL_DIR, "config.py"))))
    has_qid = bool(info.get("has_qid"))
    shape_ok = False
    if os.path.isfile(record):
        try:
            rec = read_json(record)
            # 只核对"这一份记录确实是对应题、且能喂给装配层"的最小形状：
            # `final_evidence.presentation_order` 与 `question.qid`。
            # **不检 `token_account`**：冻结的 run_query 运行记录里该字段恰为 null
            # （账在 `budget_trim` 里，由 run_answer.final_set_token_account 现场复算）。
            shape_ok = bool(rec.get("final_evidence", {}).get("presentation_order") is not None
                            and rec.get("question", {}).get("qid") == qid)
        except Exception:  # noqa: BLE001
            shape_ok = False
    _deep_clean(os.path.dirname(probe_out))
    ok = path_ok and cfg_ok and has_qid and proc.returncode == 0 and shape_ok
    detail = ("注入后子进程读到的题集 = %s（共 %s 行）；子进程里的 config = %s（= 检索侧那份：%s）；"
              "该题集含 --qid %s = %s；run_query(A 组, --qid %s) 退出码 %s；"
              "运行记录可装配 = %s；本项 0 次大模型调用"
              % (rel(got_path) if got_path else "（未取到）", info.get("n_rows"),
                 rel(got_cfg) if got_cfg else "（未取到）", cfg_ok, qid, has_qid,
                 qid, proc.returncode, shape_ok))
    if not ok:
        detail += "；stderr 尾部 = %s" % (proc.stderr or "")[-400:]
        return {"level": "FAIL", "detail": detail}
    return {"level": "OK", "detail": detail}


# ---------------------------------------------------------------------------
# 下面两项把"注入真实生效"从**声明**变成**实测**：两者都在同一条 shim 注入下真跑，
# 一个走答案侧（identifiers_for / QUESTIONS_PATH），一个把 A 组整条题路跑到哨兵拦下。
# ---------------------------------------------------------------------------
_QID_PROBE = r'''
import json, os, sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass
ANS_DIR, QUESTIONS, QIDS_JSON = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, ANS_DIR)
import config
qids = json.loads(QIDS_JSON)
mapping = {q: list(config.identifiers_for(q)) for q in qids}
print(json.dumps({"config_file": config.__file__,
                  "questions_path": config.QUESTIONS_PATH,
                  "shim": getattr(config, "STAGE10_SHIM", None),
                  "mapping": mapping}, ensure_ascii=False))
'''


def expected_identifiers(qid: str):
    r"""本脚本对"记录层标识应当是什么"的**独立期望**：qid 里的数字 → `Q-0nn`／`A-0nn`。

    它与 `交付物/03-代码\问答\config.py` 的格式决策 4 同源（前缀 ＋ 3 位零填充），但由本脚本独立算出，
    因此可以拿来跟"shim 注入后真跑出来的结果"对撞——两边都错成一样的概率极低。
    """
    digits = "".join(ch for ch in str(qid) if ch.isdigit())
    if not digits:
        return None
    return ("Q-%s" % digits.zfill(3), "A-%s" % digits.zfill(3))


def probe_qid_identifiers(questions_file: str, qids: list) -> dict:
    """**正向断言**：在与正式跑同一条 shim 注入下，真跑一遍冻结的 `identifiers_for()`。

    断言四件事（任何一条不成立即 FAIL，并指名是哪一条）：
    ① 子进程里 `import config` 拿到的是**答案侧**那份 `代码\\问答\\config.py`；
    ② 答案侧的 `QUESTIONS_PATH` 已被注入成正式题集（＝"答案侧也取得到题"）；
    ③ 每一题的解析结果都不是 `Q-CUSTOM`／`A-CUSTOM`，且与本脚本独立算出的期望值一致；
    ④ `Q-xxx`／`A-xxx` 互不重复。

    本项 0 次大模型调用（只 import 冻结配置并调一个纯函数）。
    """
    ans_cfg = os.path.join(ANSWER_DIR, "config.py")
    info, err = {}, ""
    try:
        with injected_questions(questions_file):
            proc = subprocess.run(
                [sys.executable, "-c", _QID_PROBE, ANSWER_DIR, os.path.abspath(questions_file),
                 json.dumps(list(qids), ensure_ascii=False)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600)
        err = (proc.stderr or "")[-400:]
        for line in reversed((proc.stdout or "").strip().split("\n")):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    info = json.loads(line)
                    break
                except Exception:  # noqa: BLE001
                    continue
    except SystemExit as exc:                       # 注入本身的前置断言没过
        info, err = {}, str(exc)
    except Exception as exc:                        # noqa: BLE001
        info, err = {}, "%s: %s" % (type(exc).__name__, exc)

    got_cfg = str(info.get("config_file") or "")
    cfg_ok = (bool(got_cfg)
              and os.path.normcase(os.path.abspath(got_cfg))
              == os.path.normcase(os.path.abspath(ans_cfg)))
    got_qp = str(info.get("questions_path") or "")
    qp_ok = bool(got_qp) and os.path.abspath(got_qp) == os.path.abspath(questions_file)
    mapping = info.get("mapping") or {}
    custom, mismatched, dup_q, dup_a = [], [], [], []
    seen_q, seen_a = set(), set()
    for qid in qids:
        got = mapping.get(qid)
        want = expected_identifiers(qid)
        if not isinstance(got, list) or len(got) != 2:
            mismatched.append((qid, got, want))
            continue
        if got[0] == "Q-CUSTOM" or got[1] == "A-CUSTOM":
            custom.append(qid)
        elif want is not None and (got[0], got[1]) != want:
            mismatched.append((qid, tuple(got), want))
        if got[0] in seen_q:
            dup_q.append(got[0])
        if got[1] in seen_a:
            dup_a.append(got[1])
        seen_q.add(got[0])
        seen_a.add(got[1])
    ok = cfg_ok and qp_ok and not custom and not mismatched and not dup_q and not dup_a \
        and len(mapping) == len(qids)
    detail = ("shim 注入后子进程里的 config = %s（= 答案侧那份：%s）；答案侧 QUESTIONS_PATH = %s"
              "（= 本次 --questions-file：%s）；逐题真跑 identifiers_for()：%d/%d 题解析成功、"
              "退化 CUSTOM %d 题、与独立期望不符 %d 题、Q-xxx 撞车 %d 个、A-xxx 撞车 %d 个；"
              "额外前缀正则 = %s；本项 0 次大模型调用"
              % (rel(got_cfg) if got_cfg else "（未取到）", cfg_ok,
                 rel(got_qp) if got_qp else "（未取到）", qp_ok,
                 len(mapping) - len(custom) - len(mismatched), len(qids),
                 len(custom), len(mismatched), len(set(dup_q)), len(set(dup_a)),
                 SHIM_QID_REGEX))
    if not ok:
        if not cfg_ok:
            detail += "；**不成立①**：注入没有落在答案侧 config 上"
        if not qp_ok:
            detail += "；**不成立②**：答案侧的 QUESTIONS_PATH 未被注入成正式题集"
        if custom:
            detail += "；**不成立③**：%d 题退化成 Q-CUSTOM／A-CUSTOM，例如 %s" \
                      % (len(custom), "、".join(custom[:5]))
        if mismatched:
            detail += "；**不成立③**：%d 题与独立期望不符，例如 %s" \
                      % (len(mismatched),
                         "；".join("%s→%s（期望 %s）" % (q, g, w) for q, g, w in mismatched[:3]))
        if dup_q or dup_a:
            detail += "；**不成立④**：%s" % "；".join(
                ([("Q-xxx 撞车 %s" % sorted(set(dup_q))[:5])] if dup_q else [])
                + ([("A-xxx 撞车 %s" % sorted(set(dup_a))[:5])] if dup_a else []))
        detail += "；stderr 尾部 = %s" % err
        return {"ok": False, "level": "FAIL", "detail": detail}
    return {"ok": True, "level": "OK", "detail": detail}


def probe_answer_bridge_blocked(questions_file: str, qid: str, question_text: str) -> dict:
    """**0 次模型调用**地走完 A 组的整条题路，直到冻结哨兵在发请求前把它拦下。

    这是"两层都能取到题"的直接证据：真跑 `run_answer.py --qid <FQ-qid> --group A`
    （与正式跑逐字相同的命令与 shim 注入），只把冻结的镜像重跑哨兵
    `STAGE8_FORBID_MODEL_CALLS=1` 置位。于是：

    * 检索侧子进程（`run_query.py`）真读了注入后的题集 → 桥接记录 `question.qid` ＝ 该 FQ 题号、
      且 `question.text` 与正式题集里的题干**逐字相同**（预实验集里根本没有这个题号，
      所以"取到题"这件事不可能是回落读到了预实验集）；
    * 答案侧（`assemble.question_row_from_record()` → `asm.load_questions()`）读到的是注入后的
      正式题集 → 正式跑时 `task_type`／`gold_hop_depth` 不会退化成 null；
    * 模型调用由**冻结代码**在发请求之前拦下，且不落任何 `answer_trace.jsonl`
      （如实证明"未写成空答案"）。
    """
    out_dir = os.path.join(STAGE10, "_正式对照-preflight", "answer_bridge", qid)
    _deep_clean(os.path.dirname(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    _clear_bridge("A", qid)                 # 与 run_one 同一处理：桥接记录是"已存在即被读取"
    cmd = [sys.executable, RUN_ANSWER, "--qid", qid, "--group", "A",
           "--out-dir", out_dir, "--now", FIXED_NOW, "--session-id", SESSION_ID]
    with injected_questions(questions_file):
        # env 必须在 with **内部**取：shim 的注入是经 `os.environ["PYTHONPATH"]` 传下去的，
        # 在 with 外面取的 env 不含它，子进程会退回预实验集（那样本项会假 FAIL／假 PASS）。
        env = dict(os.environ)
        env["STAGE8_FORBID_MODEL_CALLS"] = "1"
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=1800, env=env)
    bridge = bridge_record_path("A", qid)
    got_qid, got_text, bridge_ok = None, None, False
    if os.path.isfile(bridge):
        try:
            rec = read_json(bridge)
            got_qid = str((rec.get("question") or {}).get("qid") or "")
            got_text = str((rec.get("question") or {}).get("text") or "")
            bridge_ok = True
        except Exception:  # noqa: BLE001
            bridge_ok = False
    combined = (proc.stdout or "") + (proc.stderr or "")
    blocked = "STAGE8_FORBID_MODEL_CALLS" in combined
    wrote_trace = os.path.isfile(os.path.join(out_dir, "answer_trace.jsonl"))
    text_ok = bool(got_text) and got_text.strip() == str(question_text or "").strip()
    ok = (proc.returncode != 0 and blocked and bridge_ok and got_qid == qid and text_ok
          and not wrote_trace)
    detail = ("哨兵 STAGE8_FORBID_MODEL_CALLS=1 下跑 A 组 `run_answer.py --qid %s`：退出码 %s"
              "（应为非 0）、报错含哨兵名 =%s、未落 answer_trace =%s；桥接记录 %s：qid = %s"
              "（应为 %s）、题干与正式题集逐字相同 =%s；**0 次模型调用**"
              "（由冻结代码在发请求前拦下）"
              % (qid, proc.returncode, blocked, not wrote_trace, rel(bridge),
                 got_qid or "（缺失）", qid, text_ok))
    _deep_clean(os.path.join(STAGE10, "_正式对照-preflight", "answer_bridge"))
    if os.path.isfile(bridge):
        try:
            os.remove(bridge)               # 探针自己的留痕，跑完清掉（正式跑前 run_one 还会再清一次）
        except OSError:
            pass
    if not ok:
        detail += "；stderr 尾部 = %s" % (proc.stderr or "")[-500:]
        return {"level": "FAIL", "detail": detail}
    return {"level": "OK", "detail": detail}


def probe_answer_dry_run() -> dict:
    """0 次大模型调用地验证答案侧的装配维度（依赖的冻结定值与装配层可跑通）。

    用**预实验集**里的一题跑 `run_answer.py --dry-run`（`answer_case(dry_run=True)` 的
    分支只装配、**不发请求、不写产出**，`n_calls` 必为 0），并单独读一次冻结配置。
    正式题集用的是同一条装配链路，故本项足以证明"装配这一半"在正式跑之前已经通。
    """
    out_dir = os.path.join(STAGE10, "_正式对照-preflight", "answer_dry")
    _deep_clean(os.path.dirname(out_dir))
    os.makedirs(out_dir, exist_ok=True)
    proc = subprocess.run(
        [sys.executable, RUN_ANSWER, "--qid", "PE-01", "--dry-run", "--out-dir", out_dir],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=900)
    cfg = load_answer_config_subprocess()
    wrote = os.path.isdir(out_dir) and any(os.listdir(out_dir))
    _deep_clean(os.path.dirname(out_dir))
    ok = (proc.returncode == 0 and "模型调用次数 = 0" in (proc.stdout or "")
          and not wrote and "error" not in cfg)
    detail = ("run_answer.py --qid PE-01 --dry-run 退出码 %s；stdout 含「模型调用次数 = 0」=%s；"
              "未落任何产出 = %s；答案侧冻结配置 model=%s／temperature=%s／prompt=%s／"
              "max_tokens=%s；本项 0 次大模型调用"
              % (proc.returncode, "模型调用次数 = 0" in (proc.stdout or ""), not wrote,
                 cfg.get("model_name"), cfg.get("temperature"), cfg.get("prompt_version"),
                 cfg.get("max_tokens")))
    if not ok:
        detail += "；stderr 尾部 = %s" % (proc.stderr or "")[-400:]
        return {"level": "FAIL", "detail": detail}
    return {"level": "OK", "detail": detail}


def probe_b1_blocked() -> dict:
    """**0 次模型调用**地在真问题上跑一遍 B1 的装配与落盘契线。

    做法：对预实验集的一题完整走 `build_b1_case()` ＋ B1 子进程，但把冻结的**镜像重跑哨兵**
    `STAGE8_FORBID_MODEL_CALLS=1` 置位——`代码\\问答\\answer.call_model()` 在**发请求之前**
    就 `assert_model_calls_allowed()` 报错退出。于是：

    * 0 次模型调用（这是由冻结代码自己保证的，不是本脚本的承诺）；
    * 装配（`assemble.build_time_note` ＋ `prompt.build_messages`）与
      `history.build_record`（记录层两条路径）都被真实执行到；
    * 子进程**不落任何 trace**，如实证明"未写成空答案"。

    本项与 `probe_b1_wiring()` 合起来＝B1 除"真的发一次请求"之外的整条路径已被验证。
    """
    questions = load_questions(QUESTIONS_PRE_EXPERIMENT)
    qid = "PE-01"
    ret_cfg = load_retrieval_config_module()
    dataset_meta = read_json(DATASET_META_PATH)
    out_dir = os.path.join(STAGE10, "_正式对照-preflight", "b1_blocked", qid)
    _deep_clean(os.path.join(STAGE10, "_正式对照-preflight", "b1_blocked"))
    os.makedirs(out_dir, exist_ok=True)
    case_path = os.path.join(out_dir, "b1_case.json")
    case = build_b1_case(qid, questions[qid], ret_cfg, dataset_meta)
    write_json(case_path, case)
    # 记录层契约（A～E 与 B1 共用同一个 build_record；此处 0 证据）
    probe_rec = ("import sys,json;sys.path.insert(0,r'%s');import history as h;import config;"
                 "case=json.load(open(r'%s',encoding='utf-8'));"
                 "res={'answer_text':'x','model':{'requested':'probe','returned':'probe'}};"
                 "qid_num,aid=config.identifiers_for(case['qid']);"
                 "rec=h.build_record(case,res,session_id='S-probe',question_id=qid_num,"
                 "answer_id=aid,ask_time='2026-10-02T00:00:00+08:00');"
                 "print(json.dumps({'keys':sorted(rec),'answer_evidence':len(rec['answer_evidence']),"
                 "'graph_path':rec['answer']['graph_path'],"
                 "'is_graph_extended':rec['answer']['is_graph_extended']},ensure_ascii=False))"
                 % (ANSWER_DIR, case_path))
    env = dict(os.environ)
    env["STAGE8_FORBID_MODEL_CALLS"] = "1"
    sub = subprocess.run([sys.executable, "-c", B1_CHILD_CODE, ANSWER_DIR, case_path, out_dir,
                          SESSION_ID, FIXED_NOW], cwd=ROOT, capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=600, env=env)
    recp = subprocess.run([sys.executable, "-c", probe_rec], cwd=ROOT, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=300)
    rec_info = {}
    for line in reversed((recp.stdout or "").strip().split("\n")):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                rec_info = json.loads(line)
                break
            except Exception:  # noqa: BLE001
                continue
    wrote_trace = os.path.isfile(os.path.join(out_dir, "answer_trace.jsonl"))
    evidence_lines = [ln for ln in (case.get("prompt", {}).get("user") or "").split("\n")
                      if ln.startswith("[证据")]
    blocked = "STAGE8_FORBID_MODEL_CALLS" in (sub.stderr or "") + (sub.stdout or "")
    _deep_clean(os.path.join(STAGE10, "_正式对照-preflight", "b1_blocked"))
    ok = (sub.returncode != 0 and blocked and not wrote_trace
          and rec_info.get("answer_evidence") == 0
          and rec_info.get("graph_path") is None
          and rec_info.get("is_graph_extended") == 0
          and not evidence_lines
          and case["graph_payload"]["graph_path"] == []
          and case["graph_payload"]["graph_used"] is False)
    detail = ("哨兵 STAGE8_FORBID_MODEL_CALLS=1 下跑 B1 子进程：退出码 %s（应为非 0）、"
              "报错含哨兵名 =%s、未落 answer_trace =%s；装配自检：Prompt 里证据行数=%d（应为 0）、"
              "graph_used=False、graph_path=[]；记录层自检：answer_evidence=%s 条、"
              "graph_path=%s、is_graph_extended=%s。**0 次模型调用**（由冻结代码在发请求前拦下）"
              % (sub.returncode, blocked, not wrote_trace, len(evidence_lines),
                 rec_info.get("answer_evidence"), rec_info.get("graph_path"),
                 rec_info.get("is_graph_extended")))
    if not ok:
        detail += "；stderr 尾部 = %s" % (sub.stderr or "")[-500:]
        return {"level": "FAIL", "detail": detail}
    return {"level": "OK", "detail": detail}


MODEL_CALL_AUDIT_PATH = os.path.join(STAGE10, "实验方案", "本次运行模型调用审计.json")


def write_model_call_audit(mode: str, groups: list, extra: dict) -> str:
    """把"本档 0 次模型调用"这一事实落成可复核的审计记录（**它本身不证明任何事**，
    真正的保证来自：① 本档只跑 --dry-run／--preflight／--report-only／--check-token-account；
    ② 哨兵自检里冻结代码在发请求前拦下；③ 交付者本次未执行任何生成档）。"""
    payload = {
        "generated_by": "交付物/06-实验与评测/工具/跑正式对照.py",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode,
        "groups_requested": groups,
        "model_calls_made_by_this_mode": 0,
        "guarantee": ("本档不含任何生成路径：--dry-run／--preflight／--report-only／"
                      "--check-token-account 四档在代码上都不进入逐题生成循环；"
                      "--preflight 的 B1 子进程自检另用冻结哨兵 "
                      "STAGE8_FORBID_MODEL_CALLS=1 在发请求前拦下。"),
        "frozen_sentinel": "STAGE8_FORBID_MODEL_CALLS（代码\\问答\\config.assert_model_calls_allowed）",
        "checks": extra,
        "note": ("本文件是「本次没有发生模型调用」的登记，用于与 跑法说明.md 的门槛条款互相印证；"
                 "它不是模型调用次数的权威计数——权威计数在正式跑的 answer_trace.jsonl 的 "
                 "attempts 字段里逐题可数。"),
    }
    write_json(MODEL_CALL_AUDIT_PATH, payload)
    return MODEL_CALL_AUDIT_PATH


def check_token_account() -> int:
    """token 账口径自检（0 次调用、不落盘）。

    对第 7 阶段**冻结的** 30 条 C 组 trace，用 `代码\\问答\\run_answer.py` 的
    `final_set_token_account()` 复算，与 trace 里的 `token_account` 逐字段比对。
    被检对象是冻结的预实验 trace，与本脚本的正式题集文件无关；
    作用是防「复刻口径漂移」——一旦第 7 阶段的 `estimate_tokens`／`stable_json` 变了
    而复刻没跟上，这里会立刻失败。
    """
    code = (
        "import json,os,sys\n"
        "ROOT = sys.argv[1]\n"
        "sys.path.insert(0, os.path.join(ROOT, '交付物/03-代码', '问答'))\n"
        "import run_answer as ra\n"
        "chunks = ra.asm.load_chunks()\n"
        "path = os.path.join(ROOT, '交付物/05-系统实现/RAG检索系统', '检索产出',"
        " 'per_question_trace.jsonl')\n"
        "rows = [json.loads(l) for l in open(path, encoding='utf-8') if l.strip()]\n"
        "keys = ('text_chunks','text_tokens','paths','path_tokens','event_triples',"
        "'event_triple_tokens','total_tokens')\n"
        "bad = []\n"
        "for row in rows:\n"
        "    rec = {'final_evidence': {'presentation_order': row['evidence']},\n"
        "           'graph_path_payload': row.get('graph_payload') or {}}\n"
        "    got = ra.final_set_token_account(rec, chunks)\n"
        "    want = row['token_account']\n"
        "    diff = {k: (want[k], got[k]) for k in keys if want[k] != got[k]}\n"
        "    if diff:\n"
        "        bad.append([row['qid'], diff])\n"
        "print(json.dumps({'n': len(rows), 'bad': bad}, ensure_ascii=False))\n")
    proc = subprocess.run([sys.executable, "-c", code, ROOT], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)
    if proc.returncode != 0:
        log("token 账口径自检失败（退出码 %s）：%s"
            % (proc.returncode, (proc.stderr or "")[-500:]))
        return 1
    try:
        out = json.loads(proc.stdout.strip().split("\n")[-1])
    except Exception as exc:  # noqa: BLE001
        log("token 账口径自检输出解析失败：%s" % exc)
        return 1
    bad = out.get("bad") or []
    log("token 账口径自检：%d／%d 题与第 7 阶段冻结 trace 逐字段一致"
        % (out.get("n", 0) - len(bad), out.get("n", 0)))
    for qid, diff in bad[:10]:
        log("  !! %s 不一致：%s" % (qid, diff))
    log("（被检对象 = 冻结的预实验 trace，与本脚本的正式题集文件无关；0 次模型调用）")
    return 1 if bad else 0


# ===========================================================================
# 八、主流程
# ===========================================================================
def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="第 10 阶段 · 正式对照驱动（A～E 消融 ＋ Baseline 1 辅助基线；"
                    "逐题转发冻结入口，不重新实现检索与生成）")
    ap.add_argument("--groups", default="A,B,C,D,E,B1",
                    help="要跑的组，逗号分隔（默认全部：A,B,C,D,E,B1）")
    ap.add_argument("--questions-file", default=QUESTIONS_DEFAULT,
                    help="正式测试集 JSONL（默认 交付物/06-实验与评测\\测试集\\questions.jsonl）")
    ap.add_argument("--limit", type=int, default=None, help="只跑前 N 题（按 qid 升序）")
    ap.add_argument("--only-qids", default=None, help="只跑指定题号，逗号分隔（断点续跑用）")
    ap.add_argument("--out-dir", default=OUT_DIR_DEFAULT, help="产出根目录")
    ap.add_argument("--dry-run", action="store_true",
                    help="0 次模型调用、不落产出：只打印将要做什么与调用次数预算")
    ap.add_argument("--preflight", action="store_true",
                    help="0 次模型调用：题集 schema（含 qid 可解析性的正向断言）／gold 回查／"
                         "时间窗口自洽／四项定值一致／调用数估算／桥接只读注入自检"
                         "（检索侧 ＋ 答案侧）")
    ap.add_argument("--report-only", action="store_true",
                    help="0 次模型调用：从已聚合的 answer_trace.jsonl 重算指标并重出报告")
    ap.add_argument("--check-token-account", action="store_true",
                    help="0 次模型调用：token 账口径与第 7 阶段冻结 trace 的逐字段自检")
    ap.add_argument("--b1-selftest", action="store_true",
                    help="0 次模型调用：单独跑 B1 的装配与落盘契约自检（冻结哨兵拦截）")
    ap.add_argument("--stress-rule", choices=("auto", "labels", "off"), default="auto",
                    help="压力子集识别方式（auto：先看题集显式标记，再看标签判据）")
    ap.add_argument("--stress-expect", type=int, default=12,
                    help="压力子集预期题数（默认 12；不符即如实报出，不静默）")
    ap.add_argument("--no-bridge-selftest", action="store_true",
                    help="--preflight 时跳过三项实跑自检（检索侧注入／答案侧桥接／B1 契约，"
                         "省 2～4 分钟）")
    ap.add_argument("--allow-pre-experiment-set", action="store_true",
                    help="允许把 30 题预实验集当题集跑（**只用于脚手架自检**；"
                         "正式报告用它会与预实验共用题目，属方法学违规）")
    return ap.parse_args(argv)


def _parse_groups(text: str) -> list:
    groups, seen = [], set()
    for raw in str(text or "").split(","):
        g = raw.strip().upper()
        if not g:
            continue
        if g not in ALLOWED_GROUPS:
            raise SystemExit("未知组别 %r（合法值：%s）" % (raw, "／".join(ALLOWED_GROUPS)))
        if g not in seen:
            seen.add(g)
            groups.append(g)
    if not groups:
        raise SystemExit("--groups 为空")
    return groups


def build_scopes(questions: dict, stress_rule: str, expect: int) -> dict:
    """给出各报告范围的题号集合与判定函数。"""
    sc = classify_stress(questions, stress_rule)
    stress_set, core_set = set(sc["stress"]), set(sc["core"])
    return {"all_qids": sorted(questions), "core": sorted(core_set), "stress": sorted(stress_set),
            "stress_source": sc["source"] + ("（预期 %d 题）" % expect),
            "pred_all": lambda q: True,
            "pred_core": (lambda q, s=core_set: (q or {}).get("qid") in s),
            "pred_stress": (lambda q, s=stress_set: (q or {}).get("qid") in s)}


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.check_token_account:
        return check_token_account()

    questions_file = os.path.abspath(args.questions_file)
    groups = _parse_groups(args.groups)

    # 预实验集守卫：`--questions-file` 指向 30 题预实验集时，正式报告会与预实验共用题目
    # （＝"同一批题既调参又评测"），属方法学违规。除非显式放行，一律拒绝生成档。
    try:
        if os.path.isfile(questions_file) and os.path.isfile(QUESTIONS_PRE_EXPERIMENT) \
                and sha256_file(questions_file) == sha256_file(QUESTIONS_PRE_EXPERIMENT) \
                and not args.allow_pre_experiment_set:
            raise SystemExit(
                "拒绝运行：--questions-file 指向的是 30 题**预实验集**（%s）。\n"
                "  正式对照报告不得用预实验集：30 题集已用于第 7／8 阶段的 K／N／g 定值与调参，\n"
                "  再拿它出正式报告等于「同一批题既调参又评测」（《02》第12.2节 的证据复用纪律）。\n"
                "  如确实只是做脚手架自检（不出正式结论），加 --allow-pre-experiment-set。"
                % rel(questions_file))
    except SystemExit:
        raise
    except OSError:
        pass

    if args.b1_selftest:
        log("=" * 78)
        log("--b1-selftest：B1 装配与落盘契约自检（**0 次模型调用**；冻结哨兵在发请求前拦下）")
        log("=" * 78)
        log("题集：%s；组：%s" % (rel(questions_file), "、".join(groups)))
        probe = probe_b1_blocked()
        log("[%s] %s" % (probe["level"], probe["detail"]))
        audit = write_model_call_audit("--b1-selftest", groups, {"b1_selftest": probe})
        log("本档 0 次模型调用的审计登记：%s" % rel(audit))
        return 0 if probe["level"] == "OK" else 1

    if args.preflight:
        return do_preflight(questions_file, groups, args.stress_expect,
                            not args.no_bridge_selftest)

    # `--dry-run` 不依赖题集可用：题集缺失／读不动时**如实报出并照常给出计划**，
    # 仍以退出码 0 结束（它是零调用档，不该让"题集尚未建好"变成脚本失败）。
    if args.dry_run:
        load_error, questions = None, {}
        try:
            questions = load_questions(questions_file)
        except SystemExit as exc:
            load_error = str(exc)
        all_qids = sorted(questions)
        if args.only_qids:
            want = [x.strip() for x in args.only_qids.split(",") if x.strip()]
            qids = [x for x in want if x in questions]
        else:
            qids = all_qids
        if args.limit is not None and args.limit > 0:
            qids = qids[:args.limit]
        scopes = build_scopes(questions, args.stress_rule, args.stress_expect)
        return do_dry_run(groups, qids, args.out_dir, questions_file, scopes, load_error)

    questions = load_questions(questions_file)
    all_qids = sorted(questions)
    if args.only_qids:
        want = [x.strip() for x in args.only_qids.split(",") if x.strip()]
        missing = [x for x in want if x not in questions]
        if missing:
            raise SystemExit("题号不存在于题集：%s" % "、".join(missing))
        qids = want
    else:
        qids = all_qids
    if args.limit is not None:
        if args.limit <= 0:
            raise SystemExit("--limit 必须是正整数")
        qids = qids[:args.limit]

    scopes = build_scopes(questions, args.stress_rule, args.stress_expect)

    if args.dry_run:
        return do_dry_run(groups, qids, args.out_dir, questions_file, scopes)

    log("=" * 78)
    log("第 10 阶段 · 正式对照（A～E 消融 ＋ Baseline 1 辅助基线）")
    log("=" * 78)
    log("题集：%s（全部 %d 题；本次参与 %d 题）"
        % (rel(questions_file), len(all_qids), len(qids)))
    log("组：%s" % "、".join(groups))
    log("产出根：%s" % rel(args.out_dir))
    log("压力子集：%d 题（%s）；**单独报告，不并入核心集总体平均**"
        % (len(scopes["stress"]), scopes["stress_source"]))
    plan = estimate_calls(len(qids), groups)
    log("模型调用计划：%d 题 × %d 组 = %d 次（含空正文重试的上限 %d 次）"
        % (len(qids), len(groups), plan["base"], plan["max_with_retry"]))

    os.makedirs(args.out_dir, exist_ok=True)
    records, failures = {}, []

    if args.report_only:
        log("")
        log("--report-only：0 次模型调用，只从已聚合的 answer_trace.jsonl 重算指标并重出报告。")
        for group in groups:
            rows = collect_rows(os.path.join(args.out_dir, group, "answer_trace.jsonl"))
            rows.sort(key=lambda r: r["qid"])
            log("  读入 %s：%d 行" % (group, len(rows)))
            records[group] = rows
    else:
        ret_cfg = load_retrieval_config_module()
        dataset_meta = read_json(DATASET_META_PATH)
        for group in groups:
            log("")
            log("-" * 78)
            log("组 %s：逐题调用%s" % (
                group, "冻结入口 run_answer.py" if group != B1_GROUP_TAG
                else "冻结合成链路（answer.call_model + prompt.compose_answer）"))
            log("-" * 78)
            rows, qa = [], []
            for i, qid in enumerate(qids, 1):
                if group == B1_GROUP_TAG:
                    res = run_b1_one(qid, questions[qid], args.out_dir, ret_cfg, dataset_meta,
                                     questions_file)
                else:
                    res = run_one(group, qid, args.out_dir, questions_file)
                detail = res.get("detail") or {}
                extra = ""
                if group == B1_GROUP_TAG and detail.get("gate_failures"):
                    extra = " 门禁(不判失败)=%s" % "／".join(detail["gate_failures"])
                log("  [%s] %3d/%d %-9s %6.1fs%s"
                    % ("OK " if res["ok"] else "!! ", i, len(qids), qid, res["seconds"], extra))
                if not res["ok"]:
                    failures.append({"group": group, "qid": qid,
                                     "exit_code": res["exit_code"],
                                     "stdout_tail": res.get("stdout_tail"),
                                     "stderr_tail": res.get("stderr_tail")})
                    continue
                sub = os.path.join(ROOT, res["out_dir"].replace("/", os.sep))
                rows += collect_rows(os.path.join(sub, "answer_trace.jsonl"))
                qa += collect_rows(os.path.join(sub, "qa_records.jsonl"))
            rows.sort(key=lambda r: r["qid"])
            rows = merge_jsonl(os.path.join(args.out_dir, group, "answer_trace.jsonl"),
                               rows, key=lambda r: r["qid"])
            merge_jsonl(os.path.join(args.out_dir, group, "qa_records.jsonl"), qa,
                        key=lambda r: _answer_id_of(r.get("answer")))
            log("  聚合（合并后）：answer_trace %d 行、qa_records %d 行 → %s"
                % (len(rows), len(qa), rel(os.path.join(args.out_dir, group))))
            records[group] = rows

    # ---- 指标 ----
    metrics, machine = {}, {}
    for group in groups:
        rows = records.get(group, [])
        metrics[group] = retrieval_metrics(rows, questions, scopes["pred_all"], group=group)
        machine[group] = machine_checks(rows, group=group)
    scope_preds = {"all": scopes["pred_all"], "core": scopes["pred_core"],
                   "stress": scopes["pred_stress"]}
    subsets_named = {label: {g: retrieval_metrics(records.get(g, []), questions, pred, group=g)
                             for g in groups} for label, pred in scope_preds.items()}
    subsets_named_core = {}
    for name, pred in SUBSETS:
        subsets_named_core[name] = {
            g: retrieval_metrics(records.get(g, []), questions,
                                 (lambda q, p=pred: p(q) and scopes["pred_core"](q)), group=g)
            for g in groups}

    result = {
        "generated_by": "交付物/06-实验与评测/工具/跑正式对照.py",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "question_set": rel(questions_file),
        "qids": qids,
        "all_qids": all_qids,
        "groups": groups,
        "frozen": frozen_config(),
        "report_scope": {"stress_source": scopes["stress_source"],
                         "stress_rule": args.stress_rule, "stress_expect": args.stress_expect},
        "question_counts": {"all": len(all_qids), "core": len(scopes["core"]),
                            "stress": len(scopes["stress"])},
        "call_budget": plan,
        "metrics": metrics,
        "machine": machine,
        "subsets_named": subsets_named,
        "subsets_named_core": subsets_named_core,
        "subsets": [{"name": n, "per_group": p} for n, p in subsets_named.items()],
        "human_scoring": "NOT_DONE",
        "scoring_line": SCORING_LINE,
        "report_only": bool(args.report_only),
        # report-only 的失败清单要按「题集 × 各组已聚合产出」的差集算，这里只带题号集合
        # （不带整条记录，避免把全部产出塞进 JSON）。
        "trace_qids": {g: sorted({(r or {}).get("qid") for r in (records.get(g) or [])
                                  if (r or {}).get("qid")}) for g in groups},
        "failures": failures,
    }
    json_path = os.path.join(args.out_dir, "A_vs_C_对照.json")
    md_path = os.path.join(args.out_dir, "A_vs_C_对照报告.md")
    write_json(json_path, result)
    with open(md_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_md(result))

    sha = {}
    for name in ARTIFACT_FILES:
        path = os.path.join(args.out_dir, name)
        if os.path.isfile(path):
            sha[name] = {"sha256": sha256_file(path), "bytes": os.path.getsize(path)}
    for group in groups:
        for name in ("answer_trace.jsonl", "qa_records.jsonl"):
            path = os.path.join(args.out_dir, group, name)
            if os.path.isfile(path):
                sha["%s/%s" % (group, name)] = {"sha256": sha256_file(path),
                                                "bytes": os.path.getsize(path)}
    for name in sorted(os.listdir(args.out_dir)):
        sub = os.path.join(args.out_dir, name, "prompt_snapshot.json")
        if os.path.isfile(sub):
            sha["%s/prompt_snapshot.json" % name] = {"sha256": sha256_file(sub),
                                                     "bytes": os.path.getsize(sub)}
    sha_path = os.path.join(args.out_dir, "产出SHA256.json")
    write_json(sha_path, {"generated_by": result["generated_by"],
                          "generated_at": result["generated_at"],
                          "question_set": result["question_set"],
                          "note": ("产出 SHA-256 记录；重跑后逐文件复核，"
                                   "任何一项与登记值不同即说明该文件变了。"),
                          "files": sha})

    log("")
    log("=" * 78)
    log("完成：失败 %d 题" % len(failures))
    log("报告：%s" % rel(md_path))
    log("SHA-256 清单：%s" % rel(sha_path))
    log("=" * 78)
    for group in groups:
        m = metrics[group]
        if group == B1_GROUP_TAG:
            log("  %-3s 检索指标不可计算（闭卷 LLM，不接入检索）" % group)
        elif not m.get("applicable", True) or m.get("n_questions") == 0:
            log("  %-3s 无数据（该范围内没有题，或产出里没有这些题的 trace 行）" % group)
        else:
            log("  %-3s Recall=%s Precision=%s MRR=%s **CER=%s**（图谱来源证据 %s 条）"
                % (group, m.get("recall_at_k"), m.get("precision_at_k"), m.get("mrr"),
                   m.get("complete_evidence_recall_at_k"),
                   m.get("graph_evidence_in_final_total")))
    log("提示：%s" % SCORING_LINE)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
