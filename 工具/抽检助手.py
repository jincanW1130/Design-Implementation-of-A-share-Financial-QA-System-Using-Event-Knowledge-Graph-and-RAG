# -*- coding: utf-8 -*-
"""工具\\抽检助手.py —— 第 6 阶段抽取评测集（v2.1）的**逐条抽检工作台**（离线；不调模型）。

本工具对 260 条自动标注（**模型参照集**，在 `自动标注\\` 下、只读）做 **40 条逐条抽检**，
把抽中条目铺成可复核的工作区，并在复核后算出「复核改动与模型参照集的一致率」。它**不产生任何标签、
不改任何既有产物**：读 `自动标注\\`，写 `自动标注\\抽检\\`（该路径落在 `.gitignore` 覆盖的
`阶段05-数据准备/数据集/` 之下，可用 `git check-ignore -v <路径>` 复核）。

| 子命令 | 作用 |
| --- | --- |
| `export` | 确定性抽 40 条（10 dev ＋ 30 test），铺工作台：`_抽检台账.json`、`工作区\\{dev,test}\\<ITEM>.md`、`抽检说明.md` |
| `check`  | 用 `工具\\标注结构校验.py` 的公开入口 `validate_annotation` 校验这 40 条的结构合法性；并报「已复核／未复核」进度 |
| `diff`   | 把工作区与 `自动标注\\{dev,test}.auto.jsonl` 逐项比对，写 `抽检\\一致率报告.md`（条目级一致率、改动明细、枚举字段精确一致率、`notes` 码分布、Wilson 95% 外推） |
| `selftest` | 在系统临时目录里自检：抽样确定性、8 类事件覆盖、`diff` 定位能力、未复核检出、源文件未被改 |

用法：

```powershell
python 工具\\抽检助手.py export
python 工具\\抽检助手.py check
python 工具\\抽检助手.py diff
python 工具\\抽检助手.py selftest
```

## 抽样规则（确定、可复算；逐项写进 `_抽检台账.json`）

* 固定种子 `stage6-spotcheck-v1-2026-09-27`；并列打破键 `sha256(种子:item_id)`（十六进制升序）。
  **不用随机数、不写生成时间戳到确定性产物里**。
* 配额 10 条 dev ＋ 30 条 test。
* **事件类型覆盖优先**：8 类事件每类在抽中集合里至少出现 2 次。覆盖槽位（16 个）按配额比例用
  最大余数法分摊到两个 split，然后按「轮」推进——每轮按 `config.EVENT_TYPES` 顺序逐类补 1 条
  （dev 先、test 后），同类候选按 `sha256(种子:item_id)` 升序取用；某 split 的覆盖槽位用尽或该类
  达标即换下一个。仍不达标时跨 split 兜底，并把未达标类型逐条登记在台账里。
* **其余配额**在 split 内按 `category`（公告／财经新闻／政策文件／监管公开信息）用**最大余数法**
  按 `自动标注\\{split}.auto.jsonl` 的类目占比分配；类目候选不足时按余数名次轮转补足并登记。
* **抽样与抽取链的输出无关**：抽样只读 `自动标注\\{dev,test}.auto.jsonl`（模型参照集）与
  `自动标注\\工作区\\`；**不读** `代码\\抽取与图谱\\_全量\\`、**不读** `图谱导出\\`。
  否则一致率会变成自证。这一条同时写在台账与报告里。

## `check`／`diff` 的口径

* 结构校验**不另立一套**：直接 import `工具\\标注结构校验.py` 的 `validate_annotation`——
  **同一个函数、同一套错误码**；工作区文件级的问题（文件名／split／抽样字段／文本块摘要）
  沿用同一套码（`parse_error`／`filename_mismatch`／`split_mismatch`／`sampled_field_changed`／
  `text_changed`／`text_digest_mismatch`）。
* **复核完成的判据是「复核时新写下的 `notes`」**（不是 `status`）：`notes` 非空 **且**（与模型参照集里的
  `notes` 不同 **或** 能解析出已知错误码）才算复核完成。模型自己写的 `notes`（如
  `empty_but_checked: true`、一句口径说明）**不算复核完成**——否则未动的文件会被误判成已复核
  （模型参照集里有 93 条带自述 `notes`）。条目级三者互斥且合计 40：未复核（unreviewed）；
  `notes` 写好了且五个内容槽位（`entities`／`events`／`relations`／`times`／
  `ontology_boundary_log`）无改动 ⇒ 一致（agree）；否则 ⇒ 有改动（corrected）。
* `diff` **忽略 `status` 与 `provenance` 两键**（不是可复核内容）；`notes` 只用来判复核状态与统计码，
  不算内容改动。
* 比对一律先去空白（含全角空格）；实体的名字键按类型取
  `company_name`／`person_name`／`industry_name`／`institution_name`／`policy_name`。
* 用词纪律：报告与说明里只用「一致率」「抽检」「模型参照集」，不出现其它口径的说法。

退出口径：`check` 有结构问题非 0（只是没复核完不算失败）；`diff` 有条目缺失／解析不了时非 0；
`selftest` 全通过 0、任一断言失败 1。
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, OrderedDict

try:  # 控制台默认可能是 GBK，先把标准输出重设成 UTF-8 再打印中文。
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# ==========================================================================
# 0. 常量与路径
# ==========================================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_THIS_DIR)

CONFIG_PATH = os.path.join(ROOT, "代码", "抽取与图谱", "config.py")
KERNEL_PATH = os.path.join(ROOT, "工具", "标注结构校验.py")
TOOL_RELPATH = "工具\\抽检助手.py"
KERNEL_RELPATH = "工具\\标注结构校验.py"

EVAL_SUBDIR = "抽取评测集"
AUTO_DIRNAME = "自动标注"
SPOT_DIRNAME = "抽检"
WS_DIRNAME = "工作区"
LEDGER_NAME = "_抽检台账.json"
GUIDE_NAME = "抽检说明.md"
REPORT_NAME = "一致率报告.md"

SEED = "stage6-spotcheck-v1-2026-09-27"
SPLITS = ("dev", "test")
QUOTA = {"dev": 10, "test": 30}
TOTAL = sum(QUOTA.values())
COVER_PER_TYPE = 2
CATEGORIES = ["公告", "财经新闻", "政策文件", "监管公开信息"]

# 实体的名字键：**没有统一的 name 键**，按 entity_type 取（《标注说明.md》第3.1节）。
ENTITY_NAME_KEYS = OrderedDict([
    ("Company", "company_name"),
    ("Person", "person_name"),
    ("Industry", "industry_name"),
    ("Institution", "institution_name"),
    ("Policy", "policy_name"),
])

# 复核只写在 `notes` 里的错误码（码在前，可逗号组合，中文冒号后跟一句说明）。
ERROR_CODES = [
    ("OK", "完全同意，不用改"),
    ("E_TYPE", "实体类型归错"),
    ("E_MISS", "漏标（实体／事件／关系）"),
    ("E_EXTRA", "多标（原文不成立）"),
    ("V_TYPE", "事件类型归错"),
    ("V_TIME", "时间无原文支撑，或该为 `null`"),
    ("V_GRAIN", "事件粒度（一件事拆成多条／两件事压成一条）"),
    ("R_REL", "关系类型或方向错"),
    ("R_ROLE", "`role` 取错"),
    ("Q_WEAK", "证据（`quote`）不足或不支撑该条"),
]
CODE_MEANINGS = OrderedDict(ERROR_CODES)

LEDGER_SCHEMA = "stage6-spotcheck-ledger-1.0"
CONTENT_SLOTS = ("entities", "events", "relations", "times", "ontology_boundary_log")
IGNORED_KEYS = ("status", "provenance", "notes")
DICT_DIFF_SKIP = ("participants",)     # 参与方在事件的 role 配对里单独比对（避免重复记账）

TIMESTAMP_KEY_RE = re.compile(r"(^|_)(timestamp|time|generated_at|created_at|updated_at)$")
CODE_PREFIX_RE = re.compile(
    r"^([A-Za-z_]+(?:\s*[,，、/＋+]\s*[A-Za-z_]+)*)\s*[:：]")
CODE_SPLIT_RE = re.compile(r"\s*[,，、/＋+]\s*")

CROSS_DOC_FORBIDDEN_PATHS = ("_全量", "图谱导出")   # 抽样不许读（selftest 会核这一条）


def _load_py_module(name: str, path: str):
    if not os.path.isfile(path):
        raise SystemExit("找不到依赖模块：%s" % path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_config():
    """本体参数唯一来源：`代码\\抽取与图谱\\config.py`（离线，不联网）。"""
    return _load_py_module("stage6_extract_config", CONFIG_PATH)


def load_kernel():
    """复用 `工具\\标注结构校验.py`：公开校验入口 `validate_annotation` 与解析／摘要小工具。"""
    return _load_py_module("stage6_annot_struct_kernel", KERNEL_PATH)


_KERNEL_CACHE = None


def kernel_mod():
    """缓存的 `标注结构校验` 模块（内部函数用；命令行入口各自显式 load 一次）。"""
    global _KERNEL_CACHE
    if _KERNEL_CACHE is None:
        _KERNEL_CACHE = load_kernel()
    return _KERNEL_CACHE


def default_eval_dir(cfg) -> str:
    return os.path.join(cfg.DATASET_ROOT, EVAL_SUBDIR, cfg.DATASET_VERSION)


def default_auto_dir(cfg) -> str:
    return os.path.join(default_eval_dir(cfg), AUTO_DIRNAME)


def default_spot_dir(cfg) -> str:
    return os.path.join(default_auto_dir(cfg), SPOT_DIRNAME)


# ==========================================================================
# 1. 小工具（读写一律 utf-8；确定性产物一律 \n 换行、无时间戳）
# ==========================================================================
def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text_atomic(path: str, text: str) -> None:
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".spotcheck-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    return sha256_bytes(read_bytes(path))


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sample_key(item_id: str) -> str:
    """并列打破键：`sha256(种子:item_id)`（十六进制，升序）。确定性、与内容无关。"""
    return sha256_text("%s:%s" % (SEED, item_id))


def dump_json(obj, indent: int = 2) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=indent)


def rel(path: str) -> str:
    try:
        r = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return path if r.startswith("..") else r


def cell(value, limit: int = 160) -> str:
    """Markdown 表格单元格：换行折成空格、竖线转义、过长截断。"""
    if value is None:
        s = "null"
    elif isinstance(value, str):
        s = value
    else:
        s = json.dumps(value, ensure_ascii=False)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    s = s.replace("|", "\\|")
    if not s:
        s = "（空）"
    return s if len(s) <= limit else s[:limit] + "…"


def tree_digest(root: str) -> str:
    """目录的（相对路径, sha256）清单摘要；用于 selftest 的「源文件前后一致」。"""
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            entries.append("%s %s" % (os.path.relpath(p, root).replace("\\", "/"),
                                      sha256_file(p)))
    return sha256_text("\n".join(sorted(entries)))


def read_jsonl(path: str):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line, object_pairs_hook=OrderedDict))
    return rows


# ==========================================================================
# 2. 抽样（确定、可复算）
# ==========================================================================
def largest_remainder(counts, total: int, order):
    """最大余数法：`counts` 为各类目实测条数，`total` 为待分配名额，`order` 为固定类目顺序。

    返回 (alloc, detail, rank)：余数并列时按 `order` 的先后（确定、可复算）。`rank` 是
    「余数降序、并列按固定顺序」的名次，用于类目候选不足时的补位轮转。
    """
    n = sum(int(counts.get(c, 0)) for c in order)
    alloc = OrderedDict((c, 0) for c in order)
    detail = []
    if total <= 0 or n <= 0:
        for c in order:
            detail.append(OrderedDict([
                ("类目", c), ("实测条数", int(counts.get(c, 0))),
                ("占比", 0.0), ("精确配额", 0.0), ("向下取整", 0),
                ("余数", 0.0), ("分配", 0), ("是否进位", False)]))
        return alloc, detail, list(order)
    exact = {c: total * int(counts.get(c, 0)) / n for c in order}
    floors = {c: int(math.floor(exact[c])) for c in order}
    rem = total - sum(floors.values())
    rank = sorted(order, key=lambda c: (-(exact[c] - floors[c]), order.index(c)))
    for i, c in enumerate(rank):
        alloc[c] = floors[c] + (1 if i < rem else 0)
    for c in order:
        detail.append(OrderedDict([
            ("类目", c), ("实测条数", int(counts.get(c, 0))),
            ("占比", round(int(counts.get(c, 0)) / n, 6)),
            ("精确配额", round(exact[c], 6)), ("向下取整", floors[c]),
            ("余数", round(exact[c] - floors[c], 6)), ("分配", alloc[c]),
            ("是否进位", bool(alloc[c] - floors[c]))]))
    return alloc, detail, rank


def build_index(rows_by_split, cfg):
    """item_id → {split, category, event_types}；事件类型取自模型参照集的 `events[].event_type`。"""
    index = OrderedDict()
    for split in SPLITS:
        for rec in rows_by_split.get(split, []):
            iid = rec.get("item_id")
            types = sorted({e.get("event_type") for e in (rec["annotation"].get("events") or [])
                            if e.get("event_type")},
                           key=lambda t: (list(cfg.EVENT_TYPES).index(t)
                                          if t in list(cfg.EVENT_TYPES) else len(cfg.EVENT_TYPES), t))
            index[iid] = OrderedDict([
                ("item_id", iid), ("split", split), ("category", rec.get("category")),
                ("event_types", types),
            ])
    return index


def build_sample(index, cfg):
    """确定性抽样。返回 plan（全部可复算；不含任何时间戳）。"""
    types = list(cfg.EVENT_TYPES)
    quota = OrderedDict((s, QUOTA[s]) for s in SPLITS)
    cover_budget = COVER_PER_TYPE * len(types)

    # ① 覆盖槽位按配额比例分摊到 split（最大余数法；并列按 split 固定顺序 dev→test）
    cap, cap_detail, cap_rank = largest_remainder(quota, cover_budget, SPLITS)

    selected = OrderedDict()          # item_id → {途径, 覆盖类型}
    used = OrderedDict((s, 0) for s in SPLITS)
    cap_used = OrderedDict((s, 0) for s in SPLITS)
    hits = OrderedDict((t, []) for t in types)
    cover_log = []

    def candidates(etype, split):
        out = [iid for iid, v in index.items()
               if v["split"] == split and etype in v["event_types"] and iid not in selected]
        out.sort(key=lambda i: (sample_key(i), i))
        return out

    def take(iid, etype, route, use_cap):
        v = index[iid]
        selected[iid] = OrderedDict([("item_id", iid), ("split", v["split"]),
                                     ("category", v["category"]),
                                     ("event_types", list(v["event_types"])),
                                     ("入选途径", route), ("抽样键", sample_key(iid))])
        used[v["split"]] += 1
        if use_cap:
            cap_used[v["split"]] += 1
        if etype:
            hits[etype].append(iid)
            cover_log.append(OrderedDict([("event_type", etype), ("item_id", iid),
                                          ("split", v["split"]), ("途径", route)]))

    # ② 覆盖优先：按轮推进（每轮按 config.EVENT_TYPES 顺序逐类补 1 条，dev 先、test 后）
    for _round in range(COVER_PER_TYPE):
        for etype in types:
            if len(hits[etype]) >= COVER_PER_TYPE:
                continue
            for split in SPLITS:
                if len(hits[etype]) >= COVER_PER_TYPE:
                    break
                if cap_used[split] >= cap[split]:
                    continue
                cand = candidates(etype, split)
                if not cand:
                    continue
                take(cand[0], etype, "覆盖:%s" % etype, True)

    # ③ 兜底：某个 split 的覆盖槽位用尽（或该类在该 split 无条目）时，跨 split 补齐
    for etype in types:
        while len(hits[etype]) < COVER_PER_TYPE:
            best = None
            for split in SPLITS:
                if used[split] >= quota[split]:
                    continue
                cand = candidates(etype, split)
                if not cand:
                    continue
                if best is None or (sample_key(cand[0]), cand[0]) < (sample_key(best), best):
                    best = cand[0]
            if best is None:
                break
            take(best, etype, "覆盖兜底:%s" % etype, False)

    unmet = []
    for etype in types:
        if len(hits[etype]) < COVER_PER_TYPE:
            unmet.append(OrderedDict([
                ("event_type", etype), ("目标", COVER_PER_TYPE), ("实际", len(hits[etype])),
                ("原因", "可用候选不足或配额已满：抽中集合里该类型只有 %d 条" % len(hits[etype]))]))

    # ④ 其余配额：split 内按 category 占比用最大余数法分配，类目内按抽样键升序取用
    cat_detail = OrderedDict()
    cat_taken = OrderedDict()
    redistribute_log = []
    for split in SPLITS:
        counts = Counter(v["category"] for v in index.values() if v["split"] == split)
        remaining = quota[split] - used[split]
        alloc, detail, rank = largest_remainder(counts, remaining, CATEGORIES)
        cat_detail[split] = OrderedDict([
            ("配额", quota[split]), ("覆盖占用", used[split]), ("其余配额", remaining),
            ("类目占比来源", "%s.auto.jsonl 的 category 实测条数" % split),
            ("类目明细", detail), ("补位名次", rank)])
        taken = OrderedDict((c, 0) for c in CATEGORIES)
        for c in CATEGORIES:
            cand = [iid for iid, v in index.items()
                    if v["split"] == split and v["category"] == c and iid not in selected]
            cand.sort(key=lambda i: (sample_key(i), i))
            for iid in cand[:alloc[c]]:
                take(iid, None, "类目:%s" % c, False)
                taken[c] += 1
        leftover = remaining - sum(taken.values())
        if leftover > 0:
            while leftover > 0:
                progressed = False
                for c in rank:
                    if leftover <= 0:
                        break
                    cand = [iid for iid, v in index.items()
                            if v["split"] == split and v["category"] == c and iid not in selected]
                    cand.sort(key=lambda i: (sample_key(i), i))
                    if not cand:
                        continue
                    take(cand[0], None, "类目补位:%s" % c, False)
                    taken[c] += 1
                    leftover -= 1
                    progressed = True
                if not progressed:
                    break
        if leftover > 0:
            redistribute_log.append("split=%s 仍有 %d 个名额没有候选可用（已登记，不静默）"
                                    % (split, leftover))
        cat_taken[split] = OrderedDict([
            ("分配", alloc), ("实取", taken),
            ("分配合计", sum(alloc.values())), ("实取合计", sum(taken.values()))])

    items = sorted(selected.values(),
                   key=lambda v: (SPLITS.index(v["split"]), v["item_id"]))
    final_counts = OrderedDict()
    for split in SPLITS:
        c = Counter(v["category"] for v in items if v["split"] == split)
        final_counts[split] = OrderedDict((cat, c.get(cat, 0)) for cat in CATEGORIES)
    return OrderedDict([
        ("types", types), ("quota", quota), ("cover_budget", cover_budget),
        ("cover_cap", cap), ("cover_cap_detail", cap_detail), ("cover_cap_rank", cap_rank),
        ("cover_log", cover_log), ("hits", hits), ("unmet", unmet),
        ("cat_detail", cat_detail), ("cat_taken", cat_taken),
        ("redistribute_log", redistribute_log), ("items", items),
        ("final_counts", final_counts),
    ])


# ==========================================================================
# 3. export
# ==========================================================================
def read_plan_inputs(auto_dir: str):
    rows_by_split = OrderedDict()
    for split in SPLITS:
        path = os.path.join(auto_dir, "%s.auto.jsonl" % split)
        if not os.path.isfile(path):
            raise SystemExit("找不到模型参照集：%s" % path)
        rows_by_split[split] = read_jsonl(path)
    return rows_by_split


def render_ledger(plan, rows_by_split, auto_dir, spot_dir, script_sha):
    pop = OrderedDict()
    for split in SPLITS:
        c = Counter(r.get("category") for r in rows_by_split[split])
        pop[split] = OrderedDict([
            ("条目数", len(rows_by_split[split])),
            ("类目实测条数", OrderedDict((cat, c.get(cat, 0)) for cat in CATEGORIES)),
            ("类目占比", OrderedDict((cat, round(c.get(cat, 0) / max(1, len(rows_by_split[split])), 6))
                                     for cat in CATEGORIES)),
        ])
    cover = []
    for etype in plan["types"]:
        ids = plan["hits"][etype]
        cover.append(OrderedDict([
            ("event_type", etype), ("目标条数", COVER_PER_TYPE), ("抽中条数", len(ids)),
            ("是否达标", len(ids) >= COVER_PER_TYPE), ("贡献 item_id", ids)]))
    rules = [
        "固定种子 `%s`；并列打破键 `sha256(种子:item_id)`（十六进制升序）。不用随机数、不写生成时间戳。" % SEED,
        "配额 %d 条 dev ＋ %d 条 test。" % (QUOTA["dev"], QUOTA["test"]),
        "事件类型覆盖优先：8 类事件每类在抽中集合里至少出现 %d 次；覆盖槽位（%d 个）按配额比例用"
        "最大余数法分摊到 split，再按轮推进（每轮按 config.EVENT_TYPES 顺序逐类补 1 条，dev 先、test 后），"
        "同类候选按 sha256(种子:item_id) 升序取用。" % (COVER_PER_TYPE, plan["cover_budget"]),
        "其余配额在 split 内按 category（%s）用最大余数法按 `自动标注\\{split}.auto.jsonl` 的类目占比分配；"
        "类目内候选按 sha256(种子:item_id) 升序取用；类目候选不足时按余数名次轮转补足并登记。"
        % "／".join(CATEGORIES),
        "余数并列时按类目固定顺序 %s（确定、可复算）。" % "→".join(CATEGORIES),
    ]
    algorithm = [
        "① 读 `自动标注\\{dev,test}.auto.jsonl`（只读），按 item_id 建索引：split／category／"
        "events[].event_type（去重、按 config.EVENT_TYPES 顺序排序）。",
        "② 覆盖槽位 = %d × %d = %d；按 split 配额 %s 用最大余数法分摊 → %s。"
        % (len(plan["types"]), COVER_PER_TYPE, plan["cover_budget"],
           json.dumps(plan["quota"], ensure_ascii=False), json.dumps(plan["cover_cap"], ensure_ascii=False)),
        "③ 覆盖优先：按轮推进；每个 (轮, 事件类型, split) 最多取 1 条；候选按抽样键升序。",
        "④ 兜底：某类型仍不足 2 条时跨 split 取（仍受 split 配额约束），不足则登记未达标。",
        "⑤ 其余配额 = 配额 − 覆盖占用；按 split 内 category 占比做最大余数法（实测条数为分母），"
        "类目内候选按抽样键升序取用；类目不足时按余数名次轮转补位。",
        "⑥ 全部 40 条按 (split 顺序, item_id) 排序写台账；工作区文件从 `自动标注\\工作区\\` 逐字节复制。",
    ]
    items = []
    for v in plan["items"]:
        items.append(OrderedDict([
            ("item_id", v["item_id"]), ("split", v["split"]), ("category", v["category"]),
            ("event_types", v["event_types"]), ("入选途径", v["入选途径"]),
            ("抽样键", v["抽样键"])]))
    return OrderedDict([
        ("schema", LEDGER_SCHEMA),
        ("tool", TOOL_RELPATH),
        ("tool_sha256", script_sha),
        ("定位", "40 条逐条抽检（%d dev ＋ %d test），用于估计复核改动与模型参照集的一致率；"
                 "**不是全量复核**，外推到 260 条只是粗略区间。" % (QUOTA["dev"], QUOTA["test"])),
        ("种子", SEED),
        ("并列打破键", "sha256(种子:item_id)（十六进制升序）"),
        ("配额", OrderedDict([("dev", QUOTA["dev"]), ("test", QUOTA["test"]), ("合计", TOTAL)])),
        ("事件类型覆盖目标", OrderedDict([("每类至少", COVER_PER_TYPE),
                                          ("事件类型", plan["types"])])),
        ("抽样规则", rules),
        ("算法简述", algorithm),
        ("抽取链无关声明",
         "本抽检的抽样**只读** `%s`（模型参照集）与 `%s`；**不读** `代码\\抽取与图谱\\_全量\\`、"
         "**不读** `阶段06-事件抽取与知识图谱\\图谱导出\\`（selftest 用**文件访问审计**核这一条："
         "export／check／diff 全程没有打开过这两条目录下的任何文件）。因此抽样与抽取链的输出无关，"
         "一致率不是抽取链的自证。"
         % (rel(os.path.join(auto_dir, "{dev,test}.auto.jsonl")),
            rel(os.path.join(auto_dir, WS_DIRNAME)))),
        ("抽样输入", pop),
        ("覆盖槽位分摊（最大余数法）", OrderedDict([
            ("输入", OrderedDict([("配额", plan["quota"]), ("待分配", plan["cover_budget"])])),
            ("明细", plan["cover_cap_detail"]), ("余数名次", plan["cover_cap_rank"]),
            ("分摊结果", plan["cover_cap"])])),
        ("覆盖情况", cover),
        ("未达标类型登记", plan["unmet"]),
        ("分层结果（抽中集合）", plan["final_counts"]),
        ("其余配额分配（最大余数法）", plan["cat_detail"]),
        ("其余配额实取", plan["cat_taken"]),
        ("补位登记", plan["redistribute_log"]),
        ("覆盖取用顺序", plan["cover_log"]),
        ("items", items),
        ("落点", OrderedDict([("自动标注目录", rel(auto_dir)), ("抽检目录", rel(spot_dir))])),
        ("生成方式", "python 工具\\抽检助手.py export（确定性；台账与工作区文件不含生成时间戳）"),
    ])


def cmd_export(args) -> int:
    cfg = load_config()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    auto_dir = os.path.abspath(args.auto_dir or os.path.join(eval_dir, AUTO_DIRNAME))
    spot_dir = os.path.abspath(args.spot_dir or os.path.join(auto_dir, SPOT_DIRNAME))

    rows_by_split = read_plan_inputs(auto_dir)
    index = build_index(rows_by_split, cfg)
    plan = build_sample(index, cfg)
    script_sha = sha256_file(os.path.abspath(__file__))

    # ① 台账（确定性；无时间戳）
    ledger = render_ledger(plan, rows_by_split, auto_dir, spot_dir, script_sha)
    write_text_atomic(os.path.join(spot_dir, LEDGER_NAME), dump_json(ledger) + "\n")

    # ② 工作区（从自动标注工作区**逐字节复制**；已改动的文件默认保留，--force 才覆盖）
    kept, copied, missing = [], 0, []
    for v in plan["items"]:
        split, iid = v["split"], v["item_id"]
        src = os.path.join(auto_dir, WS_DIRNAME, split, "%s.md" % iid)
        dst = os.path.join(spot_dir, WS_DIRNAME, split, "%s.md" % iid)
        if not os.path.isfile(src):
            missing.append(rel(src))
            continue
        data = read_bytes(src)
        if os.path.isfile(dst) and read_bytes(dst) != data and not args.force:
            kept.append(rel(dst))
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(data)
        copied += 1

    # ③ 一页纸操作指引
    write_text_atomic(os.path.join(spot_dir, GUIDE_NAME),
                      render_guide(plan, ledger, spot_dir, auto_dir))

    print("export：抽检目录 %s" % spot_dir)
    print("  台账 %s（%d 条：dev %d ＋ test %d）"
          % (LEDGER_NAME, len(plan["items"]),
             sum(1 for v in plan["items"] if v["split"] == "dev"),
             sum(1 for v in plan["items"] if v["split"] == "test")))
    print("  工作区：新写／覆盖 %d 个文件（与自动标注工作区逐字节相同）；保留既有改动 %d 个%s"
          % (copied, len(kept), "：" + "、".join(kept) if kept else ""))
    if missing:
        print("  **缺失源文件 %d 个**：%s" % (len(missing), "、".join(missing)))
    print("  8 类事件覆盖：")
    for row in ledger["覆盖情况"]:
        print("    %-6s 目标 %d｜抽中 %d｜%s"
              % (row["event_type"], row["目标条数"], row["抽中条数"],
                 "达标" if row["是否达标"] else "未达标（已登记）"))
    if plan["unmet"]:
        print("  **未达标类型 %d 个**（逐条登记在台账的「未达标类型登记」）：%s"
              % (len(plan["unmet"]), "、".join(u["event_type"] for u in plan["unmet"])))
    print("  分层结果：%s" % json.dumps(ledger["分层结果（抽中集合）"], ensure_ascii=False))
    print("  抽样与抽取链输出无关：只读 自动标注\\{dev,test}.auto.jsonl 与 自动标注\\工作区\\。")
    return 0


def render_guide(plan, ledger, spot_dir, auto_dir) -> str:
    code_rows = "\n".join("| `%s` | %s |" % (c, m) for c, m in ERROR_CODES)
    lines = [
        "# 抽检说明 —— 逐条抽检工作台（40 条）",
        "",
        "> 一页纸。**只改每个 `.md` 里「三、标注槽位」的那个 json 块**，并把结论写进该块的 `notes`。",
        "> 抽中集合：%d 条（dev %d ＋ test %d）；种子 `%s`；抽样只读模型参照集 `%s`，"
        "与抽取链的输出无关。"
        % (len(plan["items"]), QUOTA["dev"], QUOTA["test"], SEED, rel(auto_dir)),
        "",
        "## 一、要复核的四类内容（另加一个登记处）",
        "",
        "1. **实体 `entities[]`**：`entity_type` 是否归对（Company／Person／Industry／Institution／Policy）；"
        "该类型的必填属性（如 Company 的 `company_name`／`stock_code`）；名字键（按类型取 "
        "`company_name`／`person_name`／`industry_name`／`institution_name`／`policy_name`）；"
        "`quote` 是否在本条文本块里逐字可定位。",
        "2. **事件 `events[]`**：`event_type`（8 类）是否归对；**粒度**（一件事拆成多条／两件事压成一条）；"
        "`event_name`；`event_time`（撑不住就 `null`，不要猜）；参与方 `participants[]` 的 `role`。",
        "3. **关系 `relations[]`**：`relation`（9 条）与**方向**；两端引用（`from_ref`／`to_ref`）；"
        "`PARTICIPATES_IN` 的 `role`；三项证据属性（`source_doc_id`／`source_chunk_id`／`confidence`，"
        "`EVIDENCED_BY` 除外）。",
        "4. **时间 `times[]`**：`time_type`（`event_time`／`valid_from`／`valid_to`）与 `value` 是否有原文支撑。",
        "5. **登记处 `ontology_boundary_log[]`**：归不进 8 类事件／9 条关系的情况写这里（只登记、不改本体）。",
        "",
        "## 二、怎么做（三步）",
        "",
        "- **只改 json 块**：上面 17 项字段与两段文本（`text`／`doc_text`）是抽样写的，改了 `check` 会报；"
        "`status` **保持 `auto_annotated` 不要动**，`provenance` 也不要动。",
        "- **每条都要写 `notes`**（复核时新写下的 `notes` 才算复核完成，空着会被算成「未复核」）："
        "**码在前，中文冒号后跟一句说明**；多个码用逗号组合。"
        "例：`V_TYPE,R_ROLE：事件该判「产品」；role 该是「涉及方」`。",
        "- **模型自己写的 `notes` 不算你的复核**（如 `empty_but_checked: true` 或一句口径说明，"
        "260 条里有 93 条带这种自述）：**用你的结论替换它**；只在末尾追加一句、或原样留着，"
        "这条都会被算成「未复核」。",
        "- **完全同意也要写**：`OK：完全同意，不用改`（写 `OK` 就说明这条复核过了）。",
        "- **不确定的怎么办**：写进 `ontology_boundary_log`（`case_id` 用 `OB-<item_id>-<n>`，"
        "`case_type` 取 event_type_boundary／relation_boundary／role_boundary／company_out_of_scope／"
        "relation_insufficient／time_ambiguous／chunk_boundary，`suggested_handling` 里可以写建议）。",
        "  **不许自造第 10 条关系**，也不许新增实体类型（不引入 Product／Location），"
        "更不许把 `INVOLVES` 之类写进 `relations`。",
        "",
        "## 三、错误码表（只写在 `notes` 里）",
        "",
        "| 码 | 含义 |",
        "| --- | --- |",
        code_rows,
        "",
        "## 四、改完跑哪两条命令",
        "",
        "```powershell",
        "python 工具\\抽检助手.py check     # 结构校验 ＋ 已复核／未复核进度（有结构问题退出码非 0）",
        "python 工具\\抽检助手.py diff      # 写 抽检\\一致率报告.md（条目级一致率、改动明细、码分布）",
        "```",
        "",
        "`check` 只是「还没复核完」不算失败（会把未复核条数打出来）；"
        "`diff` 的判据：`notes` 非空**且**（与模型原 `notes` 不同或能解析出已知码）。",
        "",
        "## 五、口径提醒",
        "",
        "- 一致率是 **40 条抽检** 的估计，**不是全量复核**；外推 260 条只是粗略区间（Wilson 95%）。",
        "- `status`／`provenance` 不是可复核内容，`diff` 会忽略它们。",
        "- 报告与本页只用「一致率」「抽检」「模型参照集」这三种说法。",
        "- 台账（`%s`）里有种子、抽样规则、算法简述、40 个 item_id、覆盖情况与"
        "「抽样与抽取结果无关」的声明。" % LEDGER_NAME,
        "",
        "## 六、抽中集合（%d 条）" % len(plan["items"]),
        "",
        "| item_id | split | category | 含哪些事件类型 | 入选途径 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for v in plan["items"]:
        lines.append("| %s | %s | %s | %s | %s |"
                     % (v["item_id"], v["split"], cell(v["category"]),
                        "／".join(v["event_types"]) or "（无事件）", cell(v["入选途径"])))
    lines.append("")
    return "\n".join(lines)


# ==========================================================================
# 4. check
# ==========================================================================
def load_ledger(spot_dir: str):
    path = os.path.join(spot_dir, LEDGER_NAME)
    if not os.path.isfile(path):
        raise SystemExit("找不到抽检台账：%s（先跑 export）" % path)
    return json.loads(read_text(path), object_pairs_hook=OrderedDict)


class Problems(list):
    """问题清单（与 `工具\\标注结构校验.py` 的打印口径一致）。"""

    def add(self, kind, path, item_id, field, value, message):
        self.append(OrderedDict([("kind", kind), ("file", path), ("item_id", item_id),
                                 ("field", field), ("value", value), ("message", message)]))


def load_auto_annotations(auto_dir: str):
    ann = OrderedDict()
    rows = OrderedDict()
    for split in SPLITS:
        for rec in read_jsonl(os.path.join(auto_dir, "%s.auto.jsonl" % split)):
            ann[rec["item_id"]] = rec.get("annotation")
            rows[rec["item_id"]] = rec
    return ann, rows


_AUTO_ANN_CACHE = {}


def auto_ann_of(auto_dir: str, item_id: str):
    """模型参照集里某条的 annotation（selftest 造改动前的底稿用；按目录缓存一次）。"""
    key = os.path.abspath(auto_dir)
    if key not in _AUTO_ANN_CACHE:
        _AUTO_ANN_CACHE[key] = load_auto_annotations(auto_dir)[0]
    return _AUTO_ANN_CACHE[key].get(item_id) or {}


def iter_spot_entries(ledger, spot_dir):
    for v in ledger.get("items", []):
        yield (v["item_id"], v["split"],
               os.path.join(spot_dir, WS_DIRNAME, v["split"], "%s.md" % v["item_id"]))


def check_spot(ledger, spot_dir, auto_dir, cfg, kernel, verbose=True):
    """返回 (problems, 统计)。结构校验复用 `kernel.validate_annotation`。"""
    problems = Problems()
    _, auto_rows = load_auto_annotations(auto_dir)
    handled = set()
    reviewed, unreviewed = [], []
    for iid, split, path in iter_spot_entries(ledger, spot_dir):
        handled.add(os.path.abspath(path))
        if not os.path.isfile(path):
            problems.add("file_missing", path, iid, "文件", path, "抽中的条目在工作区里没有文件")
            continue
        meta, text, annotation, errs = kernel.parse_item_file(path)
        for e in errs:
            problems.add("parse_error", path, (meta or {}).get("item_id", iid), "文件结构",
                         os.path.basename(path), e)
        if meta is not None:
            if os.path.basename(path) != "%s.md" % meta.get("item_id"):
                problems.add("filename_mismatch", path, meta.get("item_id"), "文件名",
                             os.path.basename(path),
                             "文件名应与 item_id 一致（%s.md）" % meta.get("item_id"))
            if meta.get("split") != split:
                problems.add("split_mismatch", path, meta.get("item_id"), "split",
                             meta.get("split"), "文件在 `%s\\` 下，但 meta.split=%s" % (split, meta.get("split")))
            rec = auto_rows.get(iid)
            if rec is None:
                problems.add("item_id_unknown", path, iid, "item_id", iid,
                             "item_id 不在 自动标注\\{dev,test}.auto.jsonl 里")
            else:
                for k in ("chunk_id", "doc_id"):
                    if meta.get(k) != rec.get(k):
                        problems.add("sampled_field_changed", path, iid, "meta.%s" % k,
                                     meta.get(k), "抽样字段不许改：模型参照集里 %s=%s" % (k, rec.get(k)))
                if text is None or kernel.text_digest(text) != kernel.text_digest(rec.get("text")):
                    problems.add("text_changed", path, iid, "text",
                                 kernel.text_digest(text or ""),
                                 "工作区里的文本块与模型参照集里的不是同一段（抽样字段不许改）")
            if text is not None and meta.get("text_digest") != kernel.text_digest(text):
                problems.add("text_digest_mismatch", path, iid, "meta.text_digest",
                             meta.get("text_digest"),
                             "META 里的 text_digest 与本条文本块重算的摘要不符")
        if annotation is None:
            continue
        auto_row = auto_rows.get(iid) or {}
        old_notes = ((auto_row.get("annotation") or {}).get("notes")
                     if isinstance(auto_row.get("annotation"), dict) else "")
        if is_reviewed(annotation.get("notes"), old_notes):
            reviewed.append(iid)
        else:
            unreviewed.append(iid)
        rec = auto_rows.get(iid) or meta or {}
        for p in kernel.validate_annotation(
                {"item_id": iid, "chunk_id": rec.get("chunk_id"), "doc_id": rec.get("doc_id"),
                 "text": text, "annotation": annotation}, cfg, path):
            problems.append(p)
    # 游离文件（不在台账里的 .md）
    for split in SPLITS:
        d = os.path.join(spot_dir, WS_DIRNAME, split)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if name.endswith(".md") and os.path.abspath(os.path.join(d, name)) not in handled:
                problems.add("stray_file", os.path.join(d, name), name[:-3], "文件", name,
                             "该文件不在抽检台账的 40 条里（不参与 diff）")
    summary = OrderedDict([
        ("total", len(ledger.get("items", []))), ("reviewed", len(reviewed)),
        ("unreviewed", len(unreviewed)), ("unreviewed_ids", unreviewed),
        ("reviewed_ids", reviewed),
    ])
    if verbose:
        print("check：抽检工作区 %s" % spot_dir)
        print("  台账 %d 条｜已复核 %d 条｜未复核 %d 条（判据：复核时新写下的 notes，见抽检说明）"
              % (summary["total"], summary["reviewed"], summary["unreviewed"]))
        if unreviewed:
            show = "、".join(unreviewed[:12]) + ("…" if len(unreviewed) > 12 else "")
            print("  未复核：%s" % show)
        if not problems:
            print("  **0 个结构问题**：40 条的结构校验全部通过（与 `工具\\标注结构校验.py` 同一份校验内核）。")
        else:
            print("  %d 个结构问题：" % len(problems))
            for p in problems:
                print("    [%s] 文件=%s | item_id=%s | 字段=%s | 值=%s | %s"
                      % (p["kind"], rel(p["file"]), p["item_id"], p["field"], p["value"],
                         p["message"]))
    return problems, summary


def cmd_check(args) -> int:
    cfg = load_config()
    kernel = load_kernel()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    auto_dir = os.path.abspath(args.auto_dir or os.path.join(eval_dir, AUTO_DIRNAME))
    spot_dir = os.path.abspath(args.spot_dir or os.path.join(auto_dir, SPOT_DIRNAME))
    ledger = load_ledger(spot_dir)
    problems, summary = check_spot(ledger, spot_dir, auto_dir, cfg, kernel, verbose=True)
    if problems:
        print("check 失败：%d 个结构问题（退出码 1）；未复核 %d 条不算失败"
              % (len(problems), summary["unreviewed"]))
        return 1
    print("check 通过（退出码 0）；未复核 %d 条（未复核不算失败）" % summary["unreviewed"])
    return 0


# ==========================================================================
# 5. diff —— 配对、改动明细、枚举字段精确一致率
# ==========================================================================
def norm(text) -> str:
    return re.sub(r"[\s\u3000]+", "", str(text if text is not None else ""))


def canon(value):
    """比对前的规范化：字符串去空白、列表逐项、字典逐键（其它原样）。"""
    if isinstance(value, str):
        return norm(value)
    if isinstance(value, list):
        return [canon(v) for v in value]
    if isinstance(value, dict):
        return {k: canon(v) for k, v in value.items()}
    return value


def fmt(value, limit: int = 160) -> str:
    if value is None:
        s = "null"
    elif isinstance(value, str):
        s = value
    elif isinstance(value, (int, float, bool)):
        s = json.dumps(value, ensure_ascii=False)
    else:
        s = json.dumps(value, ensure_ascii=False)
    s = s.replace("\n", " ").strip()
    return s if len(s) <= limit else s[:limit] + "…"


def key_of(*parts):
    """配对键：任一分量为空即返回 None（不参与该轮配对）。"""
    out = []
    for p in parts:
        p = norm(p)
        if not p:
            return None
        out.append(p)
    return tuple(out)


def pair_lists(old_list, new_list, pass_defs):
    """按 `pass_defs`（[(keyfn, unique_only), …]）逐轮配对。

    返回 (pairs, old_left, new_left)：pairs 是 (i, j) 下标对；余下的分别是「被删」与「新增」。
    `unique_only=True` 的轮次只在键在两侧都唯一时配对（避免歧义误配）。
    """
    old_list = old_list or []
    new_list = new_list or []
    used_old = [False] * len(old_list)
    used_new = [False] * len(new_list)
    pairs = []
    for keyfn, unique_only in pass_defs:
        bo, bn = OrderedDict(), OrderedDict()
        for i, e in enumerate(old_list):
            if used_old[i]:
                continue
            k = keyfn(e)
            if k is None:
                continue
            bo.setdefault(k, []).append(i)
        for j, e in enumerate(new_list):
            if used_new[j]:
                continue
            k = keyfn(e)
            if k is None:
                continue
            bn.setdefault(k, []).append(j)
        for k in sorted(set(bo) & set(bn)):
            if unique_only and (len(bo[k]) != 1 or len(bn[k]) != 1):
                continue
            for i, j in zip(bo[k], bn[k]):
                if used_old[i] or used_new[j]:
                    continue
                used_old[i] = True
                used_new[j] = True
                pairs.append((i, j))
    old_left = [i for i in range(len(old_list)) if not used_old[i]]
    new_left = [j for j in range(len(new_list)) if not used_new[j]]
    return pairs, old_left, new_left


def entity_name(e) -> str:
    if not isinstance(e, dict):
        return ""
    t = e.get("entity_type")
    k = ENTITY_NAME_KEYS.get(t)
    if k and str(e.get(k) or "").strip():
        return str(e.get(k))
    for kk in ENTITY_NAME_KEYS.values():
        if str(e.get(kk) or "").strip():
            return str(e.get(kk))
    return ""


ENTITY_PASSES = [
    (lambda e: key_of(e.get("entity_type"), entity_name(e)), False),
    (lambda e: key_of(entity_name(e)), True),
    (lambda e: key_of(e.get("entity_ref")), True),
]
EVENT_PASSES = [
    (lambda e: key_of(e.get("event_type"), e.get("event_name")), False),
    (lambda e: key_of(e.get("event_type"), norm(e.get("quote"))[:20]), False),
    (lambda e: key_of(e.get("event_ref")), True),
    (lambda e: key_of(e.get("event_name")), True),
    (lambda e: key_of(norm(e.get("quote"))[:20]), True),
]
RELATION_PASSES = [
    (lambda r: key_of(r.get("relation"), r.get("from_ref"), r.get("to_ref")), False),
    (lambda r: key_of(r.get("from_ref"), r.get("to_ref")), True),
    (lambda r: key_of(r.get("relation"), norm(r.get("quote"))[:20]), False),
]
TIME_PASSES = [
    (lambda t: key_of(t.get("time_type"), t.get("value")), False),
    (lambda t: key_of(t.get("value")), True),
    (lambda t: key_of(norm(t.get("quote"))[:20]), True),
]
OBLOG_PASSES = [
    (lambda o: key_of(o.get("case_id")), True),
    (lambda o: key_of(o.get("case_type"), norm(o.get("summary"))[:20]), True),
]
PARTICIPANT_PASSES = [
    (lambda p: key_of(p.get("entity_ref")), True),
]


def label_entity(e, idx):
    return "实体 %s · %s%s" % (e.get("entity_ref") or ("#%d" % (idx + 1)),
                               e.get("entity_type") or "?",
                               (" · " + entity_name(e)) if entity_name(e) else "")


def label_event(e, idx):
    name = str(e.get("event_name") or "").strip() or (norm(e.get("quote"))[:20] + "…"
                                                      if e.get("quote") else "（无名）")
    return "事件 %s · %s · %s" % (e.get("event_ref") or ("#%d" % (idx + 1)),
                                  e.get("event_type") or "?", name)


def label_relation(r, idx):
    return "关系 %s · %s→%s" % (r.get("relation") or "?",
                                "%s %s" % (r.get("from_label") or "", r.get("from_ref") or "?"),
                                "%s %s" % (r.get("to_label") or "", r.get("to_ref") or "?"))


def label_time(t, idx):
    return "时间 #%d · %s · %s" % (idx + 1, t.get("time_type") or "?", t.get("value") or "（空）")


def label_oblog(o, idx):
    return "本体边界 %s · %s" % (o.get("case_id") or ("#%d" % (idx + 1)),
                                 o.get("case_type") or "?")


def summarize_entry(e) -> str:
    return fmt(e, limit=200)


def diff_dict(old, new, label, prefix, rows, keep_keys=()):
    """逐字段比对两个 dict（忽略 IGNORED_KEYS），把差异写进 rows。"""
    keys = list(old.keys()) + [k for k in new.keys() if k not in old]
    for k in keys:
        if k in IGNORED_KEYS and k not in keep_keys:
            continue
        if k in DICT_DIFF_SKIP and k not in keep_keys:
            continue                      # 参与方由 events 段的 role 配对单独比对
        p = "%s.%s" % (prefix, k)
        if k not in new:
            rows.append(OrderedDict([("定位", label), ("字段", p), ("旧值", fmt(old[k])),
                                     ("新值", "（字段被删）")]))
        elif k not in old:
            rows.append(OrderedDict([("定位", label), ("字段", p), ("旧值", "（无）"),
                                     ("新值", fmt(new[k]))]))
        elif isinstance(old[k], dict) and isinstance(new[k], dict):
            diff_dict(old[k], new[k], label, p, rows, keep_keys)
        else:
            if canon(old[k]) != canon(new[k]):
                rows.append(OrderedDict([("定位", label), ("字段", p), ("旧值", fmt(old[k])),
                                         ("新值", fmt(new[k]))]))


def diff_annotation(old, new, iid):
    """返回 (改动行 rows, 枚举字段计数 stats)。忽略 status／provenance；notes 单独统计。"""
    rows = []
    stats = OrderedDict((k, [0, 0]) for k in
                        ("entity_type", "event_type", "relation", "role",
                         "event_time", "time_type", "time_value"))

    old_ent, new_ent = old.get("entities") or [], new.get("entities") or []
    pairs, o_left, n_left = pair_lists(old_ent, new_ent, ENTITY_PASSES)
    for i, j in pairs:
        diff_dict(old_ent[i], new_ent[j], label_entity(old_ent[i], i), "entities[%d]" % i, rows)
        stats["entity_type"][0] += 1
        stats["entity_type"][1] += int(canon(old_ent[i].get("entity_type"))
                                       == canon(new_ent[j].get("entity_type")))
    for i in o_left:
        rows.append(OrderedDict([("定位", label_entity(old_ent[i], i)), ("字段", "entities[%d]" % i),
                                 ("旧值", summarize_entry(old_ent[i])), ("新值", "（删除：多标）")]))
    for j in n_left:
        rows.append(OrderedDict([("定位", label_entity(new_ent[j], j)), ("字段", "entities[%d]" % j),
                                 ("旧值", "（无）"), ("新值", summarize_entry(new_ent[j]))]))

    old_ev, new_ev = old.get("events") or [], new.get("events") or []
    pairs, o_left, n_left = pair_lists(old_ev, new_ev, EVENT_PASSES)
    for i, j in pairs:
        label = label_event(old_ev[i], i)
        diff_dict(old_ev[i], new_ev[j], label, "events[%d]" % i, rows)
        stats["event_type"][0] += 1
        stats["event_type"][1] += int(canon(old_ev[i].get("event_type"))
                                      == canon(new_ev[j].get("event_type")))
        stats["event_time"][0] += 1
        stats["event_time"][1] += int(canon(old_ev[i].get("event_time"))
                                      == canon(new_ev[j].get("event_time")))
        pp, po_left, pn_left = pair_lists(old_ev[i].get("participants"),
                                          new_ev[j].get("participants"), PARTICIPANT_PASSES)
        for a, b in pp:
            pa, pb = (old_ev[i].get("participants") or [])[a], (new_ev[j].get("participants") or [])[b]
            stats["role"][0] += 1
            stats["role"][1] += int(canon(pa.get("role")) == canon(pb.get("role")))
            if canon(pa.get("role")) != canon(pb.get("role")):
                rows.append(OrderedDict([
                    ("定位", label), ("字段", "events[%d].participants[%d].role" % (i, a)),
                    ("旧值", fmt(pa.get("role"))), ("新值", fmt(pb.get("role")))]))
        for a in po_left:
            rows.append(OrderedDict([
                ("定位", label), ("字段", "events[%d].participants[%d]" % (i, a)),
                ("旧值", summarize_entry((old_ev[i].get("participants") or [])[a])),
                ("新值", "（删除：多标）")]))
        for b in pn_left:
            rows.append(OrderedDict([
                ("定位", label), ("字段", "events[%d].participants[新增%d]" % (i, b)),
                ("旧值", "（无）"),
                ("新值", summarize_entry((new_ev[j].get("participants") or [])[b]))]))
    for i in o_left:
        rows.append(OrderedDict([("定位", label_event(old_ev[i], i)), ("字段", "events[%d]" % i),
                                 ("旧值", summarize_entry(old_ev[i])), ("新值", "（删除：多标）")]))
    for j in n_left:
        rows.append(OrderedDict([("定位", label_event(new_ev[j], j)), ("字段", "events[%d]" % j),
                                 ("旧值", "（无）"), ("新值", summarize_entry(new_ev[j]))]))

    old_rel, new_rel = old.get("relations") or [], new.get("relations") or []
    pairs, o_left, n_left = pair_lists(old_rel, new_rel, RELATION_PASSES)
    for i, j in pairs:
        diff_dict(old_rel[i], new_rel[j], label_relation(old_rel[i], i), "relations[%d]" % i, rows)
        stats["relation"][0] += 1
        stats["relation"][1] += int(canon(old_rel[i].get("relation"))
                                    == canon(new_rel[j].get("relation")))
    for i in o_left:
        rows.append(OrderedDict([("定位", label_relation(old_rel[i], i)), ("字段", "relations[%d]" % i),
                                 ("旧值", summarize_entry(old_rel[i])), ("新值", "（删除：多标）")]))
    for j in n_left:
        rows.append(OrderedDict([("定位", label_relation(new_rel[j], j)), ("字段", "relations[%d]" % j),
                                 ("旧值", "（无）"), ("新值", summarize_entry(new_rel[j]))]))

    old_t, new_t = old.get("times") or [], new.get("times") or []
    pairs, o_left, n_left = pair_lists(old_t, new_t, TIME_PASSES)
    for i, j in pairs:
        diff_dict(old_t[i], new_t[j], label_time(old_t[i], i), "times[%d]" % i, rows)
        stats["time_type"][0] += 1
        stats["time_type"][1] += int(canon(old_t[i].get("time_type"))
                                     == canon(new_t[j].get("time_type")))
        if canon(old_t[i].get("time_type")) == "event_time":
            stats["time_value"][0] += 1
            stats["time_value"][1] += int(canon(old_t[i].get("value"))
                                          == canon(new_t[j].get("value")))
    for i in o_left:
        rows.append(OrderedDict([("定位", label_time(old_t[i], i)), ("字段", "times[%d]" % i),
                                 ("旧值", summarize_entry(old_t[i])), ("新值", "（删除：多标）")]))
    for j in n_left:
        rows.append(OrderedDict([("定位", label_time(new_t[j], j)), ("字段", "times[%d]" % j),
                                 ("旧值", "（无）"), ("新值", summarize_entry(new_t[j]))]))

    old_o, new_o = old.get("ontology_boundary_log") or [], new.get("ontology_boundary_log") or []
    pairs, o_left, n_left = pair_lists(old_o, new_o, OBLOG_PASSES)
    for i, j in pairs:
        diff_dict(old_o[i], new_o[j], label_oblog(old_o[i], i),
                  "ontology_boundary_log[%d]" % i, rows)
    for i in o_left:
        rows.append(OrderedDict([("定位", label_oblog(old_o[i], i)),
                                 ("字段", "ontology_boundary_log[%d]" % i),
                                 ("旧值", summarize_entry(old_o[i])), ("新值", "（删除）")]))
    for j in n_left:
        rows.append(OrderedDict([("定位", label_oblog(new_o[j], j)),
                                 ("字段", "ontology_boundary_log[%d]" % j),
                                 ("旧值", "（无）"), ("新值", summarize_entry(new_o[j]))]))
    return rows, stats


def parse_codes(notes: str):
    """从 `notes` 里取错误码：码在前、中文冒号分隔；返回 (codes, 未识别的码)。"""
    s = (notes or "").strip()
    if not s:
        return [], []
    m = CODE_PREFIX_RE.match(s)
    parts = CODE_SPLIT_RE.split(m.group(1)) if m else [s]
    codes = [p.strip().upper() for p in parts if p.strip()]
    known = [c for c in codes if c in CODE_MEANINGS]
    unknown = [c for c in codes if c not in CODE_MEANINGS]
    return known, unknown


def is_reviewed(new_notes, old_notes) -> bool:
    """复核完成的判据：复核时新写下的 `notes`（见文件头口径）。

    `notes` 非空，且（与模型参照集里的 `notes` 不同，或能解析出已知错误码）。模型自己写的
    `notes` 原样留着 ⇒ 未复核（模型参照集里有 93 条带自述 `notes`，不能当成复核完成）。
    """
    n = str(new_notes if new_notes is not None else "").strip()
    if not n:
        return False
    if n != str(old_notes if old_notes is not None else "").strip():
        return True
    known, _unknown = parse_codes(n)
    return bool(known)


def wilson_interval(x: int, n: int, z: float = 1.96):
    """Wilson 95% 区间：返回 (中心, 半径, 下界, 上界)。"""
    if n <= 0:
        return 0.0, 0.0, 0.0, 0.0
    p = x / n
    d = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / d
    half = (z / d) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return center, half, max(0.0, center - half), min(1.0, center + half)


def build_diff(spot_dir: str, ledger, auto_dir: str):
    """比对工作区与模型参照集，返回可渲染的结果字典（确定性；与复核当前进度有关）。"""
    auto_ann, auto_rows = load_auto_annotations(auto_dir)
    items, problems = [], Problems()
    counts = OrderedDict([("agree", 0), ("corrected", 0), ("unreviewed", 0)])
    code_counter = Counter()
    unknown_codes = []
    stats_total = OrderedDict((k, [0, 0]) for k in
                              ("entity_type", "event_type", "relation", "role",
                               "event_time", "time_type", "time_value"))
    for v in ledger.get("items", []):
        iid, split = v["item_id"], v["split"]
        path = os.path.join(spot_dir, WS_DIRNAME, split, "%s.md" % iid)
        if not os.path.isfile(path):
            problems.add("file_missing", path, iid, "文件", path, "工作区里没有该条目的文件")
            continue
        meta, text, new_ann, errs = kernel_mod().parse_item_file(path)
        if new_ann is None:
            problems.add("parse_error", path, iid, "annotation", os.path.basename(path),
                         "标注块解析不了：%s" % "；".join(errs))
            continue
        old_ann = auto_ann.get(iid)
        if old_ann is None:
            problems.add("item_id_unknown", path, iid, "item_id", iid,
                         "item_id 不在 自动标注\\{dev,test}.auto.jsonl 里")
            continue
        notes = new_ann.get("notes") if isinstance(new_ann.get("notes"), str) else ""
        old_notes = old_ann.get("notes") if isinstance(old_ann.get("notes"), str) else ""
        reviewed = is_reviewed(notes, old_notes)
        rows, stats = diff_annotation(old_ann, new_ann, iid)
        for k, (pairs, agrees) in stats.items():
            stats_total[k][0] += pairs
            stats_total[k][1] += agrees
        codes, unknown = parse_codes(notes) if reviewed else ([], [])
        for c in codes:
            code_counter[c] += 1
        if unknown:
            unknown_codes.append(OrderedDict([("item_id", iid), ("写法", notes.strip()[:60]),
                                              ("未识别的码", unknown)]))
        if not reviewed:
            state = "unreviewed"
        elif rows:
            state = "corrected"
        else:
            state = "agree"
        counts[state] += 1
        items.append(OrderedDict([
            ("item_id", iid), ("split", split), ("category", v.get("category")),
            ("state", state), ("复核", "已复核" if reviewed else "未复核"),
            ("notes", notes), ("模型原 notes", old_notes), ("codes", codes), ("未识别的码", unknown),
            ("changes", rows), ("change_count", len(rows)),
            ("event_types", v.get("event_types") or []),
        ]))
    x = counts["agree"]
    center, half, lo, hi = wilson_interval(x, TOTAL)
    return OrderedDict([
        ("counts", counts), ("items", items), ("problems", list(problems)),
        ("code_counts", OrderedDict((c, code_counter.get(c, 0)) for c, _ in ERROR_CODES)),
        ("unknown_codes", unknown_codes), ("enum_stats", stats_total),
        ("wilson", OrderedDict([("x", x), ("n", TOTAL), ("z", 1.96), ("p", x / TOTAL),
                                ("center", center), ("half", half), ("lo", lo), ("hi", hi),
                                ("lo_260", lo * 260), ("hi_260", hi * 260)])),
    ])


ENUM_LABELS = OrderedDict([
    ("entity_type", "`entity_type`（配对成功的实体上）"),
    ("event_type", "`event_type`（配对成功的事件上）"),
    ("relation", "`relation`（配对成功的关系上）"),
    ("role", "`role`（配对成功的事件参与方上）"),
    ("event_time", "`event_time`（配对成功的事件上；`null` 与 `null` 也算一致）"),
    ("time_type", "`time_type`（配对成功的时间条目上，附加项）"),
    ("time_value", "`times[].value`（配对成功且旧值为 `event_time` 的条目上，附加项）"),
])


def render_diff_md(result, ledger, spot_dir, auto_dir) -> str:
    counts = result["counts"]
    n_reviewed = counts["agree"] + counts["corrected"]
    w = result["wilson"]
    lines = [
        "# 抽检一致率报告（第 6 阶段抽取评测集 v2.1）",
        "",
        "> **这只是 40 条的抽检估计，不是全量复核**：本报告比对的是 40 条逐条抽检的改动与"
        "`自动标注\\{dev,test}.auto.jsonl`（模型参照集），不是对 260 条的结论。",
        "> 抽样只读模型参照集 `%s`，**不读** `代码\\抽取与图谱\\_全量\\`、**不读** `图谱导出\\`，"
        "因此抽样与抽取链的输出无关（一致率不是抽取链的自证）。"
        % rel(auto_dir),
        "> 用词：本报告只用「一致率」「抽检」「模型参照集」。",
        "",
        "## 一、条目级结果（三者互斥，合计 %d）" % TOTAL,
        "",
        "| 项 | 条数 | 说明 |",
        "| --- | --- | --- |",
        "| 完全未改（agree） | %d | `notes` 非空，且五个内容槽位（entities／events／relations／times／"
        "ontology_boundary_log）与模型参照集无改动 |" % counts["agree"],
        "| 有改动（corrected） | %d | `notes` 非空，且至少一处内容改动 |" % counts["corrected"],
        "| 未复核（unreviewed） | %d | 还没有复核时新写下的 `notes`（判据见下；与 `status` 无关） |"
        % counts["unreviewed"],
        "| 合计 | %d | dev %d 条 ＋ test %d 条（抽检台账 `%s` 可复算） |"
        % (TOTAL, QUOTA["dev"], QUOTA["test"], LEDGER_NAME),
        "",
        "### 1.1 条目清单（逐条定位）",
        "",
        "> 复核完成的判据：`notes` 非空，**且**与模型参照集里的 `notes` 不同（或能解析出已知错误码）。"
        "模型自己写的 `notes`（如 `empty_but_checked: true`、一句口径说明）原样留着不算复核完成。",
        "",
        "| item_id | split | category | 复核 | 条目级 | 改动处数 | notes 码 | notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for it in result["items"]:
        lines.append("| %s | %s | %s | %s | %s | %d | %s | %s |"
                     % (it["item_id"], it["split"], cell(it["category"]), it["复核"],
                        {"agree": "完全未改（agree）", "corrected": "有改动（corrected）",
                         "unreviewed": "未复核（unreviewed）"}[it["state"]],
                        it["change_count"], "、".join(it["codes"]) or "（无）",
                        cell(it["notes"], 80) if it["notes"] else "（空）"))

    lines += [
        "",
        "## 二、改动明细表（逐条：哪个字段、旧值 → 新值、发生在哪个实体／事件／关系上）",
        "",
    ]
    total_changes = sum(it["change_count"] for it in result["items"])
    if total_changes == 0:
        lines.append("**无改动行**（全部已复核条目与模型参照集逐字段一致，或还没有复核完成的条目）。")
    else:
        lines += [
            "| # | item_id | 条目级 | 定位 | 字段 | 旧值 | 新值 |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        n = 0
        for it in result["items"]:
            for row in it["changes"]:
                n += 1
                lines.append("| %d | %s | %s | %s | %s | %s | %s |"
                             % (n, it["item_id"],
                                {"agree": "完全未改", "corrected": "有改动",
                                 "unreviewed": "未复核"}[it["state"]],
                                cell(row["定位"], 90),
                                cell(row["字段"], 70), cell(row["旧值"], 110), cell(row["新值"], 110)))
        lines.append("")
        lines.append("共 %d 处改动（含整条新增／删除；整条改动在「字段」列标出所在槽位）。" % total_changes)

    lines += [
        "",
        "## 三、枚举字段精确一致率（在配对成功的前提下）",
        "",
        "| 字段 | 配对成功数 | 一致数 | 一致率 |",
        "| --- | --- | --- | --- |",
    ]
    for key, label in ENUM_LABELS.items():
        pairs, agrees = result["enum_stats"][key]
        rate = ("%d／%d ＝ %.2f%%" % (agrees, pairs, 100.0 * agrees / pairs)) if pairs else "无配对条目"
        lines.append("| %s | %d | %d | %s |" % (label, pairs, agrees, rate))
    lines += [
        "",
        "> 配对规则（先精确后退化；退化轮只在键在两侧都唯一时配对，避免歧义）："
        "实体 = `entity_type`＋名字键（`company_name`／`person_name`／`industry_name`／"
        "`institution_name`／`policy_name`，去空白）→ 名字键 → `entity_ref`；"
        "事件 = `event_type`＋`event_name` → `event_type`＋`quote` 前 20 字 → `event_ref` → "
        "`event_name` → `quote` 前 20 字；关系 = `relation`＋两端引用 → 两端引用 → "
        "`relation`＋`quote` 前 20 字；时间 = `time_type`＋`value` → `value` → `quote` 前 20 字；"
        "本体边界 = `case_id` → `case_type`＋`summary` 前 20 字。"
        "配不上的条目按「整条新增／删除」写进改动明细表，**不计入**本节的分母。",
        "",
        "## 四、错误类型分布（复核写在 `notes` 里的码）",
        "",
        "| 码 | 含义 | 条数 |",
        "| --- | --- | --- |",
    ]
    for code, meaning in ERROR_CODES:
        lines.append("| `%s` | %s | %d |" % (code, meaning, result["code_counts"][code]))
    lines += [
        "",
        "> 计的是「带该码的条目数」；一条可以带多个码，故合计可大于已复核条数（%d）。" % n_reviewed,
    ]
    if result["unknown_codes"]:
        lines.append("")
        lines.append("**未识别的码**（不匹配「码在前、中文冒号分隔」的写法，请改写）：")
        for u in result["unknown_codes"]:
            lines.append("- `%s`：%s（未识别 %s）"
                         % (u["item_id"], cell(u["写法"], 60), "、".join(u["未识别的码"])))

    lines += [
        "",
        "## 五、结论段",
        "",
        "- 条目级一致率：**%d／%d ＝ %.2f%%**（agree／40；未复核条目按「未达成一致」计入分母）。"
        % (counts["agree"], TOTAL, 100.0 * counts["agree"] / TOTAL),
        "- 其中已复核条目内：%d／%d ＝ %s。"
        % (counts["agree"], n_reviewed,
           ("%.2f%%" % (100.0 * counts["agree"] / n_reviewed)) if n_reviewed else "无已复核条目"),
        "- 已复核 %d 条（agree %d ＋ corrected %d）／未复核 %d 条；改动共 %d 处。"
        % (n_reviewed, counts["agree"], counts["corrected"], counts["unreviewed"], total_changes),
        "",
        "**这只是 40 条的抽检估计，不是全量复核**。按该比率外推 260 条只是粗略区间：",
        "",
        "```text",
        "Wilson 95%% 区间（输入：n = %d，x = %d，p̂ = x/n = %.4f，z = 1.96）" % (TOTAL, w["x"], w["p"]),
        "  中心 = (p̂ + z²/(2n)) / (1 + z²/n)",
        "  半径 = z / (1 + z²/n) × √( p̂(1−p̂)/n + z²/(4n²) )",
        "  区间 = [中心 − 半径, 中心 + 半径]",
        "       = [%.4f − %.4f, %.4f + %.4f]" % (w["center"], w["half"], w["center"], w["half"]),
        "       = [%.4f, %.4f] ＝ [%.2f%%, %.2f%%]" % (w["lo"], w["hi"], 100 * w["lo"], 100 * w["hi"]),
        "外推 260 条：260 × [%.4f, %.4f] ≈ [%.1f, %.1f] 条（四舍五入，只作粗略区间）"
        % (w["lo"], w["hi"], w["lo_260"], w["hi_260"]),
        "```",
        "",
        "## 六、口径与限制",
        "",
        "- **复核完成的判据**：`notes` 非空，且与模型参照集里的 `notes` 不同（或能解析出已知错误码）——"
        "判据与 `status` 无关；模型自己写的 `notes` 不算复核完成。`status`／`provenance` 不是可复核内容，"
        "`diff` 忽略这两键，`notes` 只用于判状态与统计码。",
        "- 比对一律先去空白（含全角空格）；实体的名字键按类型取（`company_name`／`person_name`／"
        "`industry_name`／`institution_name`／`policy_name`）。",
        "- 抽样与抽取链的输出无关：只读模型参照集 `%s` 与 `%s`；不读 `代码\\抽取与图谱\\_全量\\`、"
        "不读 `图谱导出\\`。种子与 40 个 item_id 见 `%s`。"
        % (rel(os.path.join(auto_dir, "{dev,test}.auto.jsonl")),
           rel(os.path.join(auto_dir, WS_DIRNAME)), LEDGER_NAME),
        "- 事件（或实体／关系／时间）配不上时按「整条新增／删除」登记，**不计入**枚举字段一致率的分母；"
        "因此枚举字段的一致率只在配对成功的子集上成立，不能读成全量口径。",
        "- 未复核条目即使内容有改动，也按「未复核」计入（条目级三者互斥），其改动仍列在明细表里备查。",
        "",
    ]
    if result["problems"]:
        lines += ["## 七、待处理问题", ""]
        for p in result["problems"]:
            lines.append("- [%s] %s（item_id=%s：%s）" % (p["kind"], rel(p["file"]),
                                                          p["item_id"], p["message"]))
        lines.append("")
    return "\n".join(lines)


def cmd_diff(args) -> int:
    cfg = load_config()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    auto_dir = os.path.abspath(args.auto_dir or os.path.join(eval_dir, AUTO_DIRNAME))
    spot_dir = os.path.abspath(args.spot_dir or os.path.join(auto_dir, SPOT_DIRNAME))
    ledger = load_ledger(spot_dir)
    result = build_diff(spot_dir, ledger, auto_dir)
    md = render_diff_md(result, ledger, spot_dir, auto_dir)
    out = os.path.join(spot_dir, REPORT_NAME)
    write_text_atomic(out, md if md.endswith("\n") else md + "\n")
    counts = result["counts"]
    w = result["wilson"]
    print("diff：一致率报告 %s" % out)
    print("  条目级：agree %d｜corrected %d｜unreviewed %d（合计 %d）"
          % (counts["agree"], counts["corrected"], counts["unreviewed"], TOTAL))
    print("  条目级一致率 %d／%d ＝ %.2f%%；Wilson 95%% 区间 [%.2f%%, %.2f%%]；"
          "外推 260 条 ≈ [%.1f, %.1f]"
          % (counts["agree"], TOTAL, 100.0 * counts["agree"] / TOTAL,
             100 * w["lo"], 100 * w["hi"], w["lo_260"], w["hi_260"]))
    print("  改动 %d 处；枚举字段配对（entity_type %d／event_type %d／relation %d／role %d／event_time %d）"
          % (sum(it["change_count"] for it in result["items"]),
             result["enum_stats"]["entity_type"][0], result["enum_stats"]["event_type"][0],
             result["enum_stats"]["relation"][0], result["enum_stats"]["role"][0],
             result["enum_stats"]["event_time"][0]))
    if result["problems"]:
        print("  有 %d 个待处理问题（报告「待处理问题」节）：" % len(result["problems"]))
        for p in result["problems"]:
            print("    [%s] %s（item_id=%s）" % (p["kind"], rel(p["file"]), p["item_id"]))
        return 1
    print("  这只是 40 条的抽检估计，不是全量复核。")
    return 0


# ==========================================================================
# 6. selftest
# ==========================================================================
def _assert(cond, label, evidence) -> bool:
    print("  [%s] %s —— %s" % ("PASS" if cond else "FAIL", label, evidence))
    return bool(cond)


# 文件访问审计：selftest 用它证明「export／check／diff 全程没有碰过抽取链的输出目录」。
_AUDIT_STATE = {"on": False, "hits": [], "count": 0}
_AUDIT_INSTALLED = False
_AUDIT_EVENTS = ("open", "os.listdir", "os.scandir", "os.mkdir", "os.remove", "os.rename",
                 "os.replace", "shutil.copyfile", "shutil.copytree")


def install_audit_hook() -> None:
    """装一次审计钩子（默认关闭；selftest 期间打开）。"""
    global _AUDIT_INSTALLED
    if _AUDIT_INSTALLED:
        return

    def _hook(event, args):
        if not _AUDIT_STATE["on"] or event not in _AUDIT_EVENTS:
            return
        for a in args:
            try:
                p = os.fspath(a)
            except TypeError:
                continue
            if isinstance(p, bytes):
                p = p.decode("utf-8", "replace")
            if isinstance(p, str) and p:
                _AUDIT_STATE["count"] += 1
                _AUDIT_STATE["hits"].append(p)

    sys.addaudithook(_hook)
    _AUDIT_INSTALLED = True


def snapshot_deterministic(root: str):
    """确定性快照：台账按 JSON 逐键比对（去掉时间戳类字段），工作区文件逐字节。"""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            p = os.path.join(dirpath, name)
            r = os.path.relpath(p, root).replace("\\", "/")
            if name == LEDGER_NAME:
                obj = json.loads(read_text(p), object_pairs_hook=OrderedDict)
                out[r] = dump_json(strip_timestamps(obj))
            else:
                out[r] = sha256_file(p)
    return out


def strip_timestamps(obj):
    if isinstance(obj, dict):
        return OrderedDict((k, strip_timestamps(v)) for k, v in obj.items()
                           if not TIMESTAMP_KEY_RE.search(str(k)))
    if isinstance(obj, list):
        return [strip_timestamps(v) for v in obj]
    return obj


def write_annotation_block(path: str, annotation) -> None:
    """把标注块替换成 `annotation`（保留文件其余部分与围栏），供 selftest 造改动。"""
    kernel = kernel_mod()
    raw = read_text(path)
    i = raw.find(kernel.MARK_ANN_BEGIN)
    j = raw.find(kernel.MARK_ANN_END)
    if i < 0 or j < 0:
        raise RuntimeError("缺少 ANNOTATION 锚点：%s" % path)
    head = raw[:i + len(kernel.MARK_ANN_BEGIN)]
    tail = raw[j:]
    body = "\n```json\n%s\n```\n" % dump_json(annotation)
    write_text_atomic(path, head + body + tail)


def cmd_selftest(args) -> int:
    cfg = load_config()
    kernel = load_kernel()
    real_eval = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    real_auto = os.path.abspath(args.auto_dir or os.path.join(real_eval, AUTO_DIRNAME))
    src_auto_jsonl = [os.path.join(real_auto, "%s.auto.jsonl" % s) for s in SPLITS]
    src_ws = os.path.join(real_auto, WS_DIRNAME)
    for p in src_auto_jsonl + [src_ws]:
        if not os.path.exists(p):
            print("selftest 失败：找不到源 %s" % p)
            return 1
    before = OrderedDict([(p, sha256_file(p)) for p in src_auto_jsonl])
    before_ws = tree_digest(src_ws)

    print("抽检助手 selftest（在系统临时目录里跑，不碰真实产物）")
    print("  临时根目录：%s" % tempfile.gettempdir())
    tmp = tempfile.mkdtemp(prefix="spotcheck-selftest-")
    ok = True
    install_audit_hook()
    _AUDIT_STATE["on"] = True
    _AUDIT_STATE["hits"] = []
    _AUDIT_STATE["count"] = 0
    try:
        # ① 把真实输入镜像到临时目录
        t_auto = os.path.join(tmp, AUTO_DIRNAME)
        os.makedirs(t_auto, exist_ok=True)
        for p in src_auto_jsonl:
            shutil.copyfile(p, os.path.join(t_auto, os.path.basename(p)))
        shutil.copytree(src_ws, os.path.join(t_auto, WS_DIRNAME))

        rows_by_split = read_plan_inputs(t_auto)
        index = build_index(rows_by_split, cfg)
        plan = build_sample(index, cfg)
        ledger = render_ledger(plan, rows_by_split, t_auto,
                               os.path.join(t_auto, SPOT_DIRNAME), "SELFTEST")

        # ② 抽样确定性：连跑两次 export（写到两个目录），台账与 40 个工作区文件逐字节一致
        spot_a = os.path.join(tmp, "抽检_a")
        spot_b = os.path.join(tmp, "抽检_b")
        write_spot_tree(spot_a, plan, ledger, t_auto)
        write_spot_tree(spot_b, plan, ledger, t_auto)
        snap_a = snapshot_deterministic(spot_a)
        snap_b = snapshot_deterministic(spot_b)
        diff_files = sorted(k for k in set(snap_a) | set(snap_b) if snap_a.get(k) != snap_b.get(k))
        n_ws = sum(1 for k in snap_a if k.startswith("%s/" % WS_DIRNAME))
        n_all = len(snap_a)
        ok &= _assert(not diff_files and n_ws == TOTAL and n_all == TOTAL + 2,
                      "抽样确定性：连跑两次 export，台账＋说明＋%d 个工作区文件逐字节一致" % n_ws,
                      "比对 %d 个文件（台账 1＋说明 1＋工作区 %d）；不一致 %d 个%s"
                      % (n_all, n_ws, len(diff_files),
                         "：" + "、".join(diff_files[:5]) if diff_files else ""))

        # ③ 覆盖：8 类事件每类 ≥2，或未达标项已登记
        cover = ledger["覆盖情况"]
        unmet = ledger["未达标类型登记"]
        bad = [r for r in cover if r["抽中条数"] < COVER_PER_TYPE
               and r["event_type"] not in [u["event_type"] for u in unmet]]
        ok &= _assert(not bad,
                      "强制覆盖：8 类事件每类 ≥%d 条，或未达标项已登记" % COVER_PER_TYPE,
                      "达标 %d／%d；未达标已登记 %d 个%s"
                      % (sum(1 for r in cover if r["是否达标"]), len(cover), len(unmet),
                         "：" + "、".join(u["event_type"] for u in unmet) if unmet else ""))

        # ④ check：未改动的 40 条 → 40 未复核、0 结构问题
        spot_c = os.path.join(tmp, "抽检_c")
        shutil.copytree(spot_a, spot_c)
        problems, summary = check_spot(ledger, spot_c, t_auto, cfg, kernel, verbose=False)
        ok &= _assert(not problems and summary["unreviewed"] == TOTAL,
                      "未复核检出：未改动的工作区报 40 条未复核、0 个结构问题",
                      "未复核 %d／%d；结构问题 %d 个%s"
                      % (summary["unreviewed"], TOTAL, len(problems),
                         "：" + problems[0]["message"] if problems else ""))

        # ⑤ diff 定位能力：改一个 entity_type、一个 relation、把另一条 notes 写成 OK
        ent_items = [v for v in plan["items"]
                     if (auto_ann_of(t_auto, v["item_id"]).get("entities") or [])]
        rel_items = [v for v in plan["items"]
                     if (auto_ann_of(t_auto, v["item_id"]).get("relations") or [])]
        if len(ent_items) < 1 or len(rel_items) < 2:
            ok &= _assert(False, "selftest 造改动：抽中集合里要有带实体／关系的条目",
                          "带实体 %d 条、带关系 %d 条" % (len(ent_items), len(rel_items)))
            raise SystemExit(1)
        a_item = ent_items[0]
        b_item = next(v for v in rel_items
                      if v["item_id"] != a_item["item_id"])
        c_item = next(v for v in plan["items"]
                      if v["item_id"] not in (a_item["item_id"], b_item["item_id"]))
        a_id, b_id, c_id = a_item["item_id"], b_item["item_id"], c_item["item_id"]
        a_path = os.path.join(spot_c, WS_DIRNAME, a_item["split"], "%s.md" % a_id)
        _, _, ann_a, _ = kernel.parse_item_file(a_path)
        old_type = ann_a["entities"][0]["entity_type"]
        new_type = "Institution" if old_type != "Institution" else "Company"
        ann_a["entities"][0]["entity_type"] = new_type
        ann_a["notes"] = "E_TYPE：实体类型应为 %s（抽检造改动）" % old_type
        write_annotation_block(a_path, ann_a)
        b_path = os.path.join(spot_c, WS_DIRNAME, b_item["split"], "%s.md" % b_id)
        _, _, ann_b, _ = kernel.parse_item_file(b_path)
        old_rel = ann_b["relations"][0]["relation"]
        new_rel = "RELATED_TO" if old_rel != "RELATED_TO" else "PARTICIPATES_IN"
        ann_b["relations"][0]["relation"] = new_rel
        ann_b["notes"] = "R_REL：关系类型应为 %s（抽检造改动）" % old_rel
        write_annotation_block(b_path, ann_b)
        c_path = os.path.join(spot_c, WS_DIRNAME, c_item["split"], "%s.md" % c_id)
        _, _, ann_c, _ = kernel.parse_item_file(c_path)
        ann_c["notes"] = "OK：完全同意，不用改"
        write_annotation_block(c_path, ann_c)

        result = build_diff(spot_c, ledger, t_auto)
        counts = result["counts"]
        by_id = {it["item_id"]: it for it in result["items"]}
        rows = [r for it in result["items"] for r in it["changes"]]
        a_rows = [r for r in by_id[a_id]["changes"] if r["字段"].endswith(".entity_type")]
        b_rows = [r for r in by_id[b_id]["changes"] if r["字段"].endswith(".relation")]
        ok &= _assert(counts["corrected"] == 2 and counts["agree"] == 1
                      and counts["unreviewed"] == TOTAL - 3,
                      "diff 条目级分类：corrected×2、agree×1、unreviewed×%d" % (TOTAL - 3),
                      "实测 agree %d｜corrected %d｜unreviewed %d"
                      % (counts["agree"], counts["corrected"], counts["unreviewed"]))
        ok &= _assert(len(rows) == 2 and len(a_rows) == 1 and len(b_rows) == 1
                      and a_rows[0]["旧值"] == old_type and a_rows[0]["新值"] == new_type
                      and b_rows[0]["旧值"] == old_rel and b_rows[0]["新值"] == new_rel,
                      "diff 定位精度：entity_type 与 relation 两处改动被精确报出（共 2 处，无多余）",
                      "%s：%s→%s（定位「%s」）；%s：%s→%s（定位「%s」）；改动行合计 %d"
                      % (a_id, old_type, new_type, a_rows[0]["定位"] if a_rows else "缺",
                         b_id, old_rel, new_rel, b_rows[0]["定位"] if b_rows else "缺", len(rows)))
        ok &= _assert(by_id[c_id]["state"] == "agree" and by_id[c_id]["codes"] == ["OK"]
                      and not by_id[c_id]["changes"],
                      "notes 写成 OK 的条目：判为已复核且完全未改（agree），码统计为 OK",
                      "%s：state=%s、codes=%s、改动 %d 处"
                      % (c_id, by_id[c_id]["state"], by_id[c_id]["codes"],
                         by_id[c_id]["change_count"]))
        n_un = sum(1 for it in result["items"] if it["state"] == "unreviewed")
        empty_un = sum(1 for it in result["items"]
                       if it["state"] == "unreviewed" and not it["notes"].strip())
        left_over = n_un - empty_un
        misjudged = [it["item_id"] for it in result["items"]
                     if it["state"] == "unreviewed"
                     and is_reviewed(it["notes"], it["模型原 notes"])]
        ok &= _assert(n_un == TOTAL - 3 and not misjudged,
                      "未复核检出：没有复核 notes 的条目被算作未复核（含模型自述 notes 的条目）",
                      "未复核 %d 条＝notes 为空 %d 条 ＋ 仍是模型原样 %d 条；误判 %d 条"
                      % (n_un, empty_un, left_over, len(misjudged)))

        # ⑥ 抽样与抽取链无关：全程审计文件访问，没碰过抽取链的输出目录
        _AUDIT_STATE["on"] = False
        forbidden = [p for p in _AUDIT_STATE["hits"]
                     if any(f in p.replace("/", "\\") for f in CROSS_DOC_FORBIDDEN_PATHS)]
        ok &= _assert(not forbidden,
                      "抽样与抽取链无关：export／check／diff 全程没有打开过 `代码\\抽取与图谱\\_全量\\`"
                      " 与 `图谱导出\\` 下的任何文件（文件访问审计）",
                      "审计文件访问 %d 次；命中禁用目录 %d 次%s"
                      % (_AUDIT_STATE["count"], len(forbidden),
                         "：" + "、".join(sorted(set(forbidden))[:3]) if forbidden else ""))

        # ⑦ 源文件未被改
        after = OrderedDict([(p, sha256_file(p)) for p in src_auto_jsonl])
        after_ws = tree_digest(src_ws)
        changed = [rel(p) for p in before if before[p] != after[p]]
        ok &= _assert(not changed and before_ws == after_ws,
                      "源文件未被改：自动标注\\{dev,test}.auto.jsonl 与 工作区\\ 的 sha256 前后一致",
                      "jsonl %d 个（%s）＋工作区摘要 %s→%s；变化 %d 个%s"
                      % (len(before), "、".join(v[:12] for v in before.values()),
                         before_ws[:12], after_ws[:12], len(changed),
                         "：" + "、".join(changed) if changed else ""))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest %s（退出码 %d）" % ("通过" if ok else "失败", 0 if ok else 1))
    return 0 if ok else 1


def write_spot_tree(spot_dir: str, plan, ledger, auto_dir: str) -> None:
    """selftest 用：按 export 的口径铺一棵抽检目录（台账＋工作区＋说明）。"""
    write_text_atomic(os.path.join(spot_dir, LEDGER_NAME), dump_json(ledger) + "\n")
    for v in plan["items"]:
        src = os.path.join(auto_dir, WS_DIRNAME, v["split"], "%s.md" % v["item_id"])
        dst = os.path.join(spot_dir, WS_DIRNAME, v["split"], "%s.md" % v["item_id"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(read_bytes(src))
    write_text_atomic(os.path.join(spot_dir, GUIDE_NAME), render_guide(plan, ledger, spot_dir, auto_dir))


# ==========================================================================
# 7. 命令行
# ==========================================================================
def build_parser():
    ap = argparse.ArgumentParser(
        prog="抽检助手",
        description="第 6 阶段抽取评测集（v2.1）的逐条抽检工作台："
                    "确定性抽 40 条（10 dev ＋ 30 test）、结构校验、一致率报告、自检（离线）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("export", "确定性抽 40 条并铺工作台（台账＋工作区＋说明）"),
                           ("check", "结构校验 ＋ 已复核／未复核进度"),
                           ("diff", "写一致率报告（一致率、改动明细、码分布、区间）"),
                           ("selftest", "在临时目录里自检（不碰真实产物）")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--eval-dir", default=None,
                       help="抽取评测集目录（默认由 config.DATASET_ROOT／DATASET_VERSION 推出）")
        p.add_argument("--auto-dir", default=None, help="自动标注目录（默认 <eval-dir>\\自动标注）")
        p.add_argument("--spot-dir", default=None, help="抽检目录（默认 <auto-dir>\\抽检）")
        if name == "export":
            p.add_argument("--force", action="store_true",
                           help="覆盖工作区里已被复核改动的文件（默认保留，不覆盖）")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return {"export": cmd_export, "check": cmd_check,
            "diff": cmd_diff, "selftest": cmd_selftest}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
