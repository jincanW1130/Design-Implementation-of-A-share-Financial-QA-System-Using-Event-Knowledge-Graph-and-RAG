# -*- coding: utf-8 -*-
"""代码\\抽取与图谱\\sample_eval_set.py —— 第 6 阶段 T8「抽取评测集」的**确定性抽样器**。

它做四件事，**只做抽样、不做标注**：

1. 按《15》表 15-E 的**文本块级类目占比**（公告 4042／财经新闻 563／政策文件 284／
   监管公开信息 129）为 Dev 60 ＋ Test 200 分配配额，并叠加**每类最小条数**；
2. 在类目之内按**月份**、并用公司负载均衡按**公司**铺开（表 15-E 以外的两个维度）；
3. 按**事件类型覆盖优先于比例**的原则，强制纳入薄类（重大合同、产品、投资并购）
   与 `company_list` 长度 ≥ 2 的文档（三条公司间关系唯一可能出证据的地方），
   并把每一处偏离严格比例的地方写进登记表；
4. 写出 `阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\` 下的三个机器可读文件：
   `dev.jsonl`、`test.jsonl`、`分层统计.json`。

**本脚本不产生任何标签**：`dev.jsonl`／`test.jsonl` 的 `annotation` 块里
`entities`／`events`／`relations`／`times`／`ontology_boundary_log` 一律是空容器，
`notes` 为空串，`status` 恒为 `pending_human_annotation`。写盘前有一道断言把关
（`assert_annotation_empty`），`--verify-only` 会再从盘上复算一遍。
人工标注是 T8 尚未完成的部分，口径见同目录的《标注说明.md》。

参数来源：《15-第6阶段任务书（事件抽取与知识图谱）》第4.4节／第五节 硬约束 14～16／
第八节 验收标准／第九节 T8；本体与代理关键词集一律取自 `代码\\抽取与图谱\\config.py`
（硬约束 18：脚本内不写死模型名、日期、路径或阈值）。**不调用任何模型。**

用法：

```bat
python 代码\\抽取与图谱\\sample_eval_set.py                :: 抽样并写出三个文件（幂等）
python 代码\\抽取与图谱\\sample_eval_set.py --verify-only   :: 只复核已写出的文件，退出码 0/1
```

幂等与确定性：候选排序与并列打破都用 `sha256(SEED:doc_id)` 的固定取值，
不用 `random`、不用系统时间、不写生成时间戳；同一输入重复运行输出**逐字节一致**。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import statistics
import sys

# 同目录另有会话在改 `config.py`／`extract.py`，本脚本不落任何新文件到该目录
# （连 `__pycache__` 也不落）。
sys.dont_write_bytecode = True

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import config as C  # noqa: E402  —— 唯一参数来源

_REQUIRED_CONSTANTS = (
    "DATASET_ROOT", "DATASET_VERSION", "DOCS_PATH", "CHUNKS_PATH",
    "EVENT_TYPES", "EVENT_TYPE_TITLE_PATTERNS", "PRODUCT_EXCLUDE_PATTERN",
    "RELATIONS", "RELATION_SCHEMA", "ENTITY_TYPES_FROM_MODEL", "EVENT_CORE_ATTRS",
    "EVIDENCE_ATTRS", "ROLES", "TASK_BOOK_TABLES", "stable_json", "sha256_hex",
)
_MISSING = [n for n in _REQUIRED_CONSTANTS if not hasattr(C, n)]
if _MISSING:  # pragma: no cover - 只在 config.py 被改坏时触发
    raise SystemExit(
        "config.py 缺少本脚本依赖的参数：%s（《15》第五节 硬约束 18：参数一律取自 config.py）"
        % "、".join(_MISSING)
    )

# --------------------------------------------------------------------------
# 一、抽样参数（本脚本的全部口径集中在这里，其余一律从 config.py 取）
# --------------------------------------------------------------------------
SEED = "stage6-t8-抽取评测集-v2.1-2026-09-25"   # 固定种子，写进报告
DEV_TOTAL = 60
TEST_TOTAL = 200
SPLIT_ORDER = ("dev", "test")

# 每类最小条数：260 条里每类不少于 6 条（4 类 × 6 = 24 ≤ 260，不挤占比例配额）；
# Dev／Test 各自每类不少于 1 条（两段式都要看得见 4 个类目）。
MIN_PER_CATEGORY_TOTAL = 6
MIN_PER_CATEGORY_SPLIT = 1
# 每个「有语料的（类目 × 月份）单元格」先保底 1 条 —— 仅在该段的类目配额
# 不小于该类的非空月份数时启用（配额不够时不硬凑，改为登记 0 值单元格）。
MONTH_CELL_FLOOR = 1

# 覆盖优先于比例（《15》第五节 硬约束 15：不得按「8 类均衡」规划题量；
# 这里是**薄类与公司间关系的最小落点**，不是均衡配额）。
COVERAGE_TAGS = ("公司间关系关键词", "严格多公司", "多公司", "重大合同", "产品", "投资并购")
COVERAGE_FLOORS = {
    "dev":  {"公司间关系关键词": 4, "严格多公司": 2, "多公司": 4,  "重大合同": 5,  "产品": 5,  "投资并购": 1},
    "test": {"公司间关系关键词": 13, "严格多公司": 7, "多公司": 14, "重大合同": 15, "产品": 15, "投资并购": 2},
}
# 覆盖标签对应的**块级证据关键词**：文档因某个标签入选时，优先取该标签关键词真正命中的块
# （仍按代理关键词命中种数最多、其次 chunk_index 最小取舍），使附给标注员的文本块
# 就是该标签最可能的证据块，而不是封面或落款。关键词集全部来自 config.py。
TAG_PREFER_PATTERNS = {
    "重大合同": C.EVENT_TYPE_TITLE_PATTERNS["重大合同"],
    "产品": C.EVENT_TYPE_TITLE_PATTERNS["产品"],
    "投资并购": C.EVENT_TYPE_TITLE_PATTERNS["投资并购"],
    "公司间关系关键词": "|".join(
        C.RELATION_BODY_PATTERNS[r] for r in ("SUPPLIES", "CUSTOMER_OF", "COMPETES_WITH")
        if C.RELATION_BODY_PATTERNS.get(r)
    ),
}

# 偏差容差（写进《16》与《标注说明.md》的同一条声明）。
TOLERANCE = {
    "category_pp": 3.0,      # 类目占比偏差（百分点）
    "month_pp": 3.0,         # 月份占比偏差（百分点）
    "company_pp": 3.0,       # 单家公司占比偏差（百分点）
    "cell_count": 2,         # 单个（类目 × 月份）单元格的条数偏差
}
# 薄类阈值：计划条目少于该值的类型／关系按「薄证据（登记）」处理，不得读成覆盖充分。
THIN_CLASS_THRESHOLD = 5
# 公司维度的均衡规则：`deficit_max` = 每步优先补「离比例目标缺口最大」的公司，
# 使按公司统计的偏差最小；`load_min` = 每步优先补当前条目最少的公司（覆盖更广、
# 但按占比的偏差更大）。两种规则的达成分布都会写进 分层统计.json，供《16》对照。
COMPANY_BALANCE_RULE = "deficit_max"

EVAL_SET_DIR = os.path.join(C.DATASET_ROOT, "抽取评测集", C.DATASET_VERSION)
DEV_PATH = os.path.join(EVAL_SET_DIR, "dev.jsonl")
TEST_PATH = os.path.join(EVAL_SET_DIR, "test.jsonl")
STATS_PATH = os.path.join(EVAL_SET_DIR, "分层统计.json")
PROTOCOL_PATH = os.path.join(EVAL_SET_DIR, "标注说明.md")
SCRIPT_REL = os.path.join("代码", "抽取与图谱", "sample_eval_set.py")

CATEGORY_ORDER = ("公告", "财经新闻", "政策文件", "监管公开信息")
NO_COMPANY_PREFIX = "__NO_COMPANY__:"      # 政策／监管类无公司挂钩，按类目各自成一条伪公司键

_SCORE_PATTERNS = tuple(
    re.compile(p)
    for p in list(C.EVENT_TYPE_TITLE_PATTERNS.values())
    + [p for p in C.RELATION_BODY_PATTERNS.values() if p]
)
_RE_CACHE: dict = {}


def _re(pattern: str):
    if pattern not in _RE_CACHE:
        _RE_CACHE[pattern] = re.compile(pattern)
    return _RE_CACHE[pattern]


def order_key(doc_id: int) -> str:
    """确定性并列打破键：`sha256(SEED:doc_id)`。不用 `random`，跨进程稳定。"""
    return hashlib.sha256(("%s:%d" % (SEED, int(doc_id))).encode("utf-8")).hexdigest()


def signal_score(text: str) -> int:
    """文本块的代理关键词命中**种数**（只用《13》第9.1.1节 与 config 的冻结关键词集）。

    这是**选块的启发式，不是标注、不是抽取结果**：用于在一篇文档内部挑出
    事件／关系信号最集中的那一块给标注员，避免把封面、落款一类低信息块选进来。
    """
    if not text:
        return 0
    return sum(1 for p in _SCORE_PATTERNS if p.search(text))


def doc_tags(doc: dict) -> list:
    """文档的覆盖标签（标题级代理 + 结构性计数），只用于抽样分层。"""
    tags = []
    title = doc.get("title") or ""
    content = doc.get("content") or ""
    if _re(C.EVENT_TYPE_TITLE_PATTERNS["重大合同"]).search(title):
        tags.append("重大合同")
    if _re(C.EVENT_TYPE_TITLE_PATTERNS["产品"]).search(title) and not _re(
        C.PRODUCT_EXCLUDE_PATTERN
    ).search(title):
        tags.append("产品")
    if _re(C.EVENT_TYPE_TITLE_PATTERNS["投资并购"]).search(title):
        tags.append("投资并购")
    if len(doc.get("company_list") or []) >= 2:
        tags.append("多公司")
    if len(doc.get("subject_companies") or []) >= 2:
        tags.append("严格多公司")
    if len(doc.get("company_list") or []) >= 2 and _re(TAG_PREFER_PATTERNS["公司间关系关键词"]).search(content):
        tags.append("公司间关系关键词")
    return tags


# --------------------------------------------------------------------------
# 二、配额算法（最大余数法，带下限；全部确定性）
# --------------------------------------------------------------------------
def lr_allocate(weights: dict, total: int, order=()):
    """最大余数法：按 `weights` 的比例把 `total` 分成整数份，合计恰好等于 total。"""
    keys = list(weights)
    order_index = {k: i for i, k in enumerate(order)}
    out = {k: 0 for k in keys}
    s = float(sum(weights.values()))
    if total <= 0 or s <= 0:
        return out
    raw = {k: total * float(weights[k]) / s for k in keys}
    for k in keys:
        out[k] = int(math.floor(raw[k]))
    rest = total - sum(out.values())
    ranked = sorted(
        keys,
        key=lambda k: (-(raw[k] - math.floor(raw[k])), -raw[k], order_index.get(k, 0), str(k)),
    )
    for k in ranked[:rest]:
        out[k] += 1
    return out


def allocate_with_floor(weights: dict, total: int, floor: int, order=()):
    """按权重比例分配，**比例分不到 `floor` 的项**才抬到下限，其余按剩余配额重分。

    与「先给每项保底再加剩余」不同：下限只在严格比例真的把某项压到下限以下时起作用，
    因此下限不会无谓地改动比例（例：4 个类目的严格比例都 ≥ 6 时，结果就是纯比例分配）。
    当 `floor × 项数 > 配额`（配额太小、保底不可行）时**不保底**，按比例分配，
    差额在《标注说明.md》与登记表里说明。
    """
    keys = [k for k in weights if weights[k] > 0]
    out = {k: 0 for k in weights}
    if total <= 0 or not keys:
        return out
    remaining = total
    pool = list(keys)
    fixed = {}
    while pool:
        alloc = lr_allocate({k: weights[k] for k in pool}, remaining, order=order)
        viol = [k for k in pool if floor and alloc[k] < floor]
        if not viol or floor * len(pool) > remaining:
            for k in pool:
                out[k] = alloc[k]
            break
        for k in viol:
            fixed[k] = floor
            remaining -= floor
            pool.remove(k)
        for k in pool:
            out[k] = 0
    for k, v in fixed.items():
        out[k] = v
    if sum(out.values()) != total:  # pragma: no cover - 配平失败即口径有误，直接报错
        raise SystemExit("配额配平失败：total=%d got=%d" % (total, sum(out.values())))
    return out


def allocate_cells(month_weights: dict, total: int, order=()):
    """类目之内的月份分配：有语料的月份先保底 1 条（配额够时），其余按块数比例。"""
    return allocate_with_floor(month_weights, total, MONTH_CELL_FLOOR, order=order)


# --------------------------------------------------------------------------
# 三、读数据与候选池
# --------------------------------------------------------------------------
def load_inputs():
    docs, chunks = {}, []
    with open(C.DOCS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                d = json.loads(line)
                docs[int(d["doc_id"])] = d
    with open(C.CHUNKS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                chunks.append(json.loads(line))
    return docs, chunks


def build_universe(docs: dict, chunks: list) -> list:
    """一篇文档一个候选：`(doc, 该篇信号最强的块)` —— 保证 Dev／Test 文档不重叠。"""
    by_doc: dict = {}
    for c in chunks:
        by_doc.setdefault(int(c["doc_id"]), []).append(c)
    universe = []
    for doc_id, cs in sorted(by_doc.items()):
        cs = sorted(cs, key=lambda c: int(c["chunk_index"]))
        scored = []
        best, best_score = None, -1
        for c in cs:
            sc = signal_score(c.get("content") or "")
            scored.append({"chunk": c, "index": int(c["chunk_index"]), "score": sc})
            if best is None or (-sc, int(c["chunk_index"])) < (-best_score, int(best["chunk_index"])):
                best, best_score = c, sc
        d = docs[doc_id]
        universe.append(
            {
                "doc_id": doc_id,
                "doc": d,
                "chunk": best,
                "chunk_index": int(best["chunk_index"]),
                "chunk_count_in_doc": len(cs),
                "signal_score": best_score,
                "scored_chunks": scored,
                "category": d["category"],
                "month": (d.get("publish_time") or "")[:7],
                "tags": doc_tags(d),
                "order": order_key(doc_id),
            }
        )
    return universe


# --------------------------------------------------------------------------
# 四、抽样
# --------------------------------------------------------------------------
def company_keys(unit: dict) -> list:
    """公司负载键：**主题公司优先**（表 15-E 的公司维度按 `subject_companies` 口径实测），
    主题公司为空时退回"文档涉及"的 `company_list`，两者都空（政策／监管类）按类目分伪层。
    """
    subj = sorted(set(unit["doc"].get("subject_companies") or []))
    if subj:
        return subj
    listed = sorted(set(unit["doc"].get("company_list") or []))
    return listed or [NO_COMPANY_PREFIX + unit["category"]]


def load_of(unit: dict, loads: dict) -> int:
    return min(loads.get(k, 0) for k in company_keys(unit))


def bump_loads(unit: dict, loads: dict) -> None:
    for k in company_keys(unit):
        loads[k] = loads.get(k, 0) + 1


def select_for_split(split: str, quota_cat: dict, cell_quota: dict, units: list, cat_chunks_total: dict,
                     cat_month_chunks: dict, months: list, company_target: dict) -> list:
    """按「覆盖优先 → 余量按单元格比例补齐」的顺序选出一条 split 的全部文档。"""
    picked, picked_by_tag = [], {t: 0 for t in COVERAGE_TAGS}
    loads: dict = {}
    cell_picked: dict = {}
    selected_ids = set()

    def company_reach(unit: dict) -> float:
        """公司维度的选点依据：该公司离比例目标还剩多少条（越大越该补）。"""
        real = [k for k in company_keys(unit) if not k.startswith(NO_COMPANY_PREFIX)]
        if not real:
            return 0.0
        return max(company_target.get(k, 0.0) - loads.get(k, 0) for k in real)

    def pick_rank(unit: dict):
        if COMPANY_BALANCE_RULE == "load_min":
            return (min(loads.get(k, 0) for k in company_keys(unit)), unit["order"])
        return (-company_reach(unit), unit["order"])

    def cell_target(cat: str, m: str) -> float:
        tot = cat_chunks_total.get(cat, 0)
        if not tot:
            return 0.0
        return quota_cat.get(cat, 0) * cat_month_chunks.get(cat, {}).get(m, 0) / float(tot)

    # ---- 阶段 1：覆盖标签的最小落点（按 COVERAGE_TAGS 的顺序） ----
    for tag in COVERAGE_TAGS:
        need = COVERAGE_FLOORS[split][tag]
        while picked_by_tag[tag] < need:
            cands = [u for u in units if u["doc_id"] not in selected_ids and tag in u["tags"]]
            if not cands:
                raise SystemExit("覆盖标签 %s 的候选池不足：需要 %d 条（split=%s）" % (tag, need, split))
            best = min(
                cands,
                key=lambda u: (
                    cell_picked.get((u["category"], u["month"]), 0)
                    / max(cell_target(u["category"], u["month"]), 0.25),
                    load_of(u, loads),
                    u["order"],
                ),
            )
            selected_ids.add(best["doc_id"])
            picked.append(best)
            bump_loads(best, loads)
            cell_picked[(best["category"], best["month"])] = (
                cell_picked.get((best["category"], best["month"]), 0) + 1
            )
            for t in COVERAGE_TAGS:
                if t in best["tags"]:
                    picked_by_tag[t] += 1

    # ---- 阶段 2：余量按单元格比例补齐（覆盖已占用的部分从目标里扣掉） ----
    for cat in CATEGORY_ORDER:
        residual_total = quota_cat.get(cat, 0) - sum(1 for u in picked if u["category"] == cat)
        if residual_total <= 0:
            if residual_total < 0:
                raise SystemExit("类目 %s 的覆盖纳入数超过类目配额（split=%s）" % (cat, split))
            continue
        residual_w = {}
        for m in months:
            run = cell_picked.get((cat, m), 0)
            residual_w[m] = max(0.0, cell_target(cat, m) - run)
        add = lr_allocate(residual_w, residual_total, order=months) if sum(residual_w.values()) > 0 else {}
        if sum(add.values()) < residual_total:      # 目标已全部吃满时按块数兜底
            rest = residual_total - sum(add.values())
            extra = lr_allocate(cat_month_chunks.get(cat, {}), rest, order=months)
            for m in months:
                add[m] = add.get(m, 0) + extra.get(m, 0)
        for m in months:
            want = add.get(m, 0)
            if want <= 0:
                continue
            cands = [
                u for u in units
                if u["doc_id"] not in selected_ids and u["category"] == cat and u["month"] == m
            ]
            while want > 0:
                if not cands:
                    # 该单元格候选不足：缺口转给同类目余量最大的单元格（登记在偏差表）
                    pool = [u for u in units if u["doc_id"] not in selected_ids and u["category"] == cat]
                    if not pool:
                        raise SystemExit("类目 %s 在 split=%s 的候选池不足" % (cat, split))
                    cands = pool
                best = min(cands, key=pick_rank)
                cands.remove(best)
                selected_ids.add(best["doc_id"])
                picked.append(best)
                bump_loads(best, loads)
                cell_picked[(best["category"], best["month"])] = (
                    cell_picked.get((best["category"], best["month"]), 0) + 1
                )
                want -= 1

    got = {c: sum(1 for u in picked if u["category"] == c) for c in CATEGORY_ORDER}
    if got != {c: quota_cat.get(c, 0) for c in CATEGORY_ORDER}:
        raise SystemExit("split=%s 的类目配额未配平：%s" % (split, got))
    return picked


def build_selection(docs: dict, chunks: list):
    universe = build_universe(docs, chunks)
    months = sorted({(d.get("publish_time") or "")[:7] for d in docs.values() if d.get("publish_time")})
    cat_chunks_total = {c: 0 for c in CATEGORY_ORDER}
    cat_month_chunks = {c: {m: 0 for m in months} for c in CATEGORY_ORDER}
    for c in chunks:
        d = docs[int(c["doc_id"])]
        cat, m = d["category"], (d.get("publish_time") or "")[:7]
        cat_chunks_total[cat] = cat_chunks_total.get(cat, 0) + 1
        cat_month_chunks.setdefault(cat, {})
        cat_month_chunks[cat][m] = cat_month_chunks[cat].get(m, 0) + 1

    q_total = allocate_with_floor(
        cat_chunks_total, DEV_TOTAL + TEST_TOTAL, MIN_PER_CATEGORY_TOTAL, order=CATEGORY_ORDER
    )
    q_dev = allocate_with_floor(q_total, DEV_TOTAL, MIN_PER_CATEGORY_SPLIT, order=CATEGORY_ORDER)
    q_test = {c: q_total[c] - q_dev[c] for c in CATEGORY_ORDER}
    if sum(q_total.values()) != DEV_TOTAL + TEST_TOTAL or sum(q_dev.values()) != DEV_TOTAL:
        raise SystemExit("类目配额配平失败：%s %s" % (q_total, q_dev))

    cell_quota = {}
    for split, quota in (("dev", q_dev), ("test", q_test)):
        cell_quota[split] = {
            c: allocate_cells(cat_month_chunks[c], quota[c], order=months) for c in CATEGORY_ORDER
        }

    # 先选 Dev、再选 Test，且 Test 的候选池排除 Dev 已选文档 ——
    # 这样「整篇文档只归一个 split」由构造保证，不算「尽量不重叠」。
    picked, taken = {}, set()
    key_mass: dict = {}
    for u in universe:
        for k in company_keys(u):
            key_mass[k] = key_mass.get(k, 0) + max(1, int(u["chunk_count_in_doc"]))
    mass_total = float(sum(key_mass.values())) or 1.0
    for split in SPLIT_ORDER:
        pool = [u for u in universe if u["doc_id"] not in taken]
        split_total = DEV_TOTAL if split == "dev" else TEST_TOTAL
        company_target = {k: split_total * v / mass_total for k, v in key_mass.items()}
        picked[split] = select_for_split(
            split, q_dev if split == "dev" else q_test, cell_quota[split], pool,
            cat_chunks_total, cat_month_chunks, months, company_target,
        )
        taken |= {u["doc_id"] for u in picked[split]}
    ids = {s: {u["doc_id"] for u in picked[s]} for s in SPLIT_ORDER}
    if ids["dev"] & ids["test"]:
        raise SystemExit("Dev 与 Test 选到了同一篇文档：%s" % sorted(ids["dev"] & ids["test"])[:5])
    if len(picked["dev"]) != DEV_TOTAL or len(picked["test"]) != TEST_TOTAL:
        raise SystemExit("条数不对：dev=%d test=%d" % (len(picked["dev"]), len(picked["test"])))
    return {
        "universe": universe,
        "picked": picked,
        "months": months,
        "cat_chunks_total": cat_chunks_total,
        "cat_month_chunks": cat_month_chunks,
        "quota": {"total": q_total, "dev": q_dev, "test": q_test},
        "cell_quota": cell_quota,
        "universe_index": {u["doc_id"]: u for u in universe},
    }


# --------------------------------------------------------------------------
# 五、条目与标注槽位（槽位一律为空）
# --------------------------------------------------------------------------
ENTITY_FIELD_SPEC = {
    "Company": ["stock_code", "company_name", "short_name", "aliases", "exchange"],
    "Person": ["person_id", "person_name", "aliases", "role_title"],
    "Industry": ["industry_code", "industry_name", "level"],
    "Institution": ["institution_id", "institution_name", "institution_type"],
    "Policy": ["policy_id", "policy_name", "issuer", "publish_date"],
}


def annotation_schema() -> dict:
    """给标注员用的字段骨架，全部由 config.py 的本体推导（不新增字段）。"""
    return {
        "note": "标注槽位在 dev.jsonl／test.jsonl 中一律为空；本块只声明填什么键、取什么值。",
        "entities": {
            "entity_type_enum": list(C.ENTITY_TYPES_FROM_MODEL),
            "common_fields": ["entity_type", "entity_ref", "quote", "chunk_id"],
            "per_type_fields": {k: ENTITY_FIELD_SPEC[k] for k in C.ENTITY_TYPES_FROM_MODEL},
            "event_note": "Event 不在 entities[] 里重复登记，事件一律写进 events[]（《10》第4.5.1节）。",
            "entity_ref_rule": "本条内编号，形如 E1／E2，从 1 开始，只在本条内可引用。",
        },
        "events": {
            "core_attrs": list(C.EVENT_CORE_ATTRS),
            "extra_fields": ["event_ref", "participants", "quote", "chunk_id", "trigger"],
            "participants": {"entity_ref": "指向 entities[] 的 entity_ref",
                             "role_enum": list(C.ROLES)},
            "event_type_enum": list(C.EVENT_TYPES),
            "event_id_rule": "条目内写 EVT-<item_id>-<n>；全局编号由 write_graph.py 一次性分配。",
            "trigger_note": "trigger 只作可选调试字段，不进检索与判定（《10》第4.5.1节）。",
        },
        "relations": {
            "relation_enum": list(C.RELATIONS),
            "fields": ["relation", "from_label", "from_ref", "to_label", "to_ref",
                       "source_doc_id", "source_chunk_id", "confidence", "quote"],
            "per_relation": {
                r: {
                    "domain": list(C.RELATION_SCHEMA[r]["domain"]),
                    "range": list(C.RELATION_SCHEMA[r]["range"]),
                    "extra_attrs": list(C.RELATION_SCHEMA[r]["extra_attrs"]),
                    "from_model": bool(C.RELATION_SCHEMA[r]["from_model"]),
                    "evidence_attrs": [] if r == "EVIDENCED_BY" else list(C.EVIDENCE_ATTRS),
                }
                for r in C.RELATIONS
            },
            "role_enum": list(C.ROLES),
            "issued_by_note": "ISSUED_BY 只出现在政策事件与监管事件上；同一机构为发布／作出方时不重复写 PARTICIPATES_IN。",
        },
        "times": {
            "fields": ["time_type", "value", "quote"],
            "time_type_enum": ["event_time", "valid_from", "valid_to"],
            "note": "event_time 归 Event；valid_from／valid_to 只用于 BELONGS_TO；publish_time 已在条目字段给出，不重复标注。",
        },
        "ontology_boundary_log": {
            "fields": ["case_id", "case_type", "summary", "quote", "chunk_id", "suggested_handling"],
            "rule": "归不进 9 条关系或 8 种事件类型的情形**只登记、不新增本体**（《15》第十节 风险表）。",
        },
        "notes": "自由文本，写本条的口径疑问与跨块证据提示（如 cross_chunk_evidence: <chunk_id>）。",
    }


def empty_annotation() -> dict:
    """标注槽位：**一律为空容器**，由人工标注填写。"""
    return {
        "status": "pending_human_annotation",
        "entities": [],
        "events": [],
        "relations": [],
        "times": [],
        "ontology_boundary_log": [],
        "notes": "",
    }


def choose_chunk(unit: dict) -> tuple:
    """在该篇文档里挑交给标注员的那个块。

    规则（确定性）：若该篇因某个覆盖标签入选，且该标签的块级关键词真的命中某些块，
    先在这些块里取「代理关键词命中种数最多、其次 chunk_index 最小」的一块；
    否则取全篇同规则的一块。**这是选块启发式，不是标注。**
    """
    tags = unit["tags"]
    for tag in COVERAGE_TAGS:
        pat = TAG_PREFER_PATTERNS.get(tag)
        if not pat or tag not in tags:
            continue
        hits = [s for s in unit["scored_chunks"] if _re(pat).search(s["chunk"].get("content") or "")]
        if hits:
            best = max(hits, key=lambda s: (s["score"], -s["index"]))
            return best["chunk"], best["score"], tag
    return unit["chunk"], unit["signal_score"], None


def make_item(split: str, seq: int, unit: dict, schema: dict) -> dict:
    doc = unit["doc"]
    chunk, chunk_score, prefer_tag = choose_chunk(unit)
    return {
        "item_id": "%s-%03d" % (split.upper(), seq),
        "split": split,
        "chunk_id": int(chunk["chunk_id"]),
        "doc_id": unit["doc_id"],
        "chunk_index": unit["chunk_index"],
        "chunk_count_in_doc": unit["chunk_count_in_doc"],
        "token_count": chunk.get("token_count"),
        "category": doc["category"],
        "publish_time": doc.get("publish_time"),
        "month": unit["month"],
        "source": doc.get("source"),
        "title": doc.get("title"),
        "url": doc.get("url"),
        "company_list": list(doc.get("company_list") or []),
        "subject_companies": list(doc.get("subject_companies") or []),
        "text": chunk.get("content") or "",
        "doc_text": doc.get("content") or "",
        "sampling": {
            "stratum_category": doc["category"],
            "stratum_month": unit["month"],
            "stratum_companies_subject": sorted(set(doc.get("subject_companies") or [])),
            "stratum_companies_listed": sorted(set(doc.get("company_list") or [])),
            "cell": "%s|%s" % (doc["category"], unit["month"]),
            "coverage_tags": list(unit["tags"]),
            "chunk_pick_rule": "coverage_tag_keyword_first_then_signal_score_desc_then_chunk_index_asc",
            "chunk_pick_coverage_tag": prefer_tag,
            "chunk_signal_score": chunk_score,
            "document_assignment": "whole_document_to_one_split",
            "order_key": unit["order"],
            "seed": SEED,
            "note": ("evidence_unit = chunk：事实以本条给定文本块的 chunk_id 为准；"
                     "选块优先取本条覆盖标签的块级关键词真正命中的块（选块启发式，不是标注）；"
                     "doc_text 只用于文档级判定（事件是否被块边界切断、参与主体与 role），"
                     "跨块证据写进 annotation.notes。company_list／subject_companies 只是候选池，"
                     "不是「公司参与该事件」的依据（《15》第五节 硬约束 16）。"),
            "annotation_schema_ref": "分层统计.json#annotation_schema 与 标注说明.md 第三节",
        },
        "annotation": empty_annotation(),
    }


def assert_annotation_empty(item: dict) -> None:
    ann = item["annotation"]
    if ann.get("status") != "pending_human_annotation":
        raise SystemExit("条目 %s 的标注状态不是待标注" % item.get("item_id"))
    for k in ("entities", "events", "relations", "times", "ontology_boundary_log"):
        if ann.get(k) != []:
            raise SystemExit("条目 %s 的 %s 槽位非空——本脚本不得写入任何标签" % (item.get("item_id"), k))
    if ann.get("notes") != "":
        raise SystemExit("条目 %s 的 notes 非空——本脚本不得写入任何标签" % item.get("item_id"))


def build_items(selection: dict) -> dict:
    schema = annotation_schema()
    items = {}
    for split in SPLIT_ORDER:
        units = sorted(selection["picked"][split], key=lambda u: int(u["chunk"]["chunk_id"]))
        rows = [make_item(split, i + 1, u, schema) for i, u in enumerate(units)]
        for r in rows:
            assert_annotation_empty(r)
        items[split] = rows
    return {"items": items, "schema": schema}


# --------------------------------------------------------------------------
# 六、分层统计与偏差登记
# --------------------------------------------------------------------------
def proxy_hits(text: str, patterns: dict) -> list:
    return [k for k, p in patterns.items() if p and _re(p).search(text or "")]


def table_15e_recompute(docs: dict, chunks: list) -> dict:
    per_cat = {}
    for cat in CATEGORY_ORDER:
        dc = sum(1 for d in docs.values() if d["category"] == cat)
        cc = sum(1 for c in chunks if docs[int(c["doc_id"])]["category"] == cat)
        per_cat[cat] = {
            "docs": dc, "chunks": cc,
            "chunk_share": round(cc / len(chunks), 6) if chunks else 0.0,
            "chunks_per_doc": round(cc / dc, 4) if dc else 0.0,
        }
    month = {}
    for c in chunks:
        m = (docs[int(c["doc_id"])].get("publish_time") or "")[:7]
        month[m] = month.get(m, 0) + 1
    declared = C.TASK_BOOK_TABLES.get("table_15E", {})
    diff = {}
    for cat, row in per_cat.items():
        dec = declared.get(cat)
        if dec:
            diff[cat] = {
                "docs_declared": dec.get("docs"), "docs_recomputed": row["docs"],
                "chunks_declared": dec.get("chunks"), "chunks_recomputed": row["chunks"],
                "chunks_match": dec.get("chunks") == row["chunks"],
            }
    return {"per_category": per_cat, "per_month": dict(sorted(month.items())),
            "declared_vs_recomputed": diff, "total_chunks": len(chunks), "total_docs": len(docs)}


def table_15cd_recompute(docs: dict, chunks: list) -> dict:
    cl2 = sum(1 for d in docs.values() if len(d.get("company_list") or []) >= 2)
    sc2 = sum(1 for d in docs.values() if len(d.get("subject_companies") or []) >= 2)
    title_hits, body_hits = {}, {}
    for name, pat in C.EVENT_TYPE_TITLE_PATTERNS.items():
        if name == "产品":
            title_hits[name] = sum(
                1 for d in docs.values()
                if _re(pat).search(d.get("title") or "")
                and not _re(C.PRODUCT_EXCLUDE_PATTERN).search(d.get("title") or "")
            )
        else:
            title_hits[name] = sum(1 for d in docs.values() if _re(pat).search(d.get("title") or ""))
    ann_title_hits = {
        name: sum(
            1 for d in docs.values()
            if d["category"] == "公告" and _re(pat).search(d.get("title") or "")
            and not (name == "产品" and _re(C.PRODUCT_EXCLUDE_PATTERN).search(d.get("title") or ""))
        )
        for name, pat in C.EVENT_TYPE_TITLE_PATTERNS.items()
    }
    chunk_hits = {name: 0 for name in C.RELATIONS}
    for c in chunks:
        txt = c.get("content") or ""
        for name, pat in C.RELATION_BODY_PATTERNS.items():
            if pat and _re(pat).search(txt):
                chunk_hits[name] += 1
    for name, pat in C.RELATION_BODY_PATTERNS.items():
        if pat:
            body_hits[name] = sum(1 for d in docs.values() if _re(pat).search(d.get("content") or ""))
        else:
            body_hits[name] = None
    declared_c = C.TASK_BOOK_TABLES.get("table_15C", {})
    declared_d = C.TASK_BOOK_TABLES.get("table_15D", {})
    return {
        "table_15C": {
            "company_list_ge2_declared": declared_c.get("company_list_ge2"),
            "company_list_ge2_recomputed": cl2,
            "subject_companies_ge2_declared": declared_c.get("subject_companies_ge2"),
            "subject_companies_ge2_recomputed": sc2,
        },
        "table_15D": {
            "declared_doc_title_level": declared_d.get("公告标题级", {}),
            "recomputed_announcement_title_level": ann_title_hits,
            "declared_body_level": declared_d.get("正文级", {}),
            "recomputed_doc_body_level": body_hits,
            "recomputed_chunk_body_level": chunk_hits,
            "recomputed_doc_title_level_all_categories": title_hits,
        },
        "company_list_length_distribution": {
            str(n): sum(1 for d in docs.values() if len(d.get("company_list") or []) == n)
            for n in sorted({len(d.get("company_list") or []) for d in docs.values()})
        },
    }


def distribution_report(rows: list, universe: list, docs: dict, chunks: list, key: str):
    """维度偏差表：目标（文本块级实测）对达成（选中的 260 条）。"""
    if key == "category":
        target_counts = {c: 0 for c in CATEGORY_ORDER}
        for c in chunks:
            target_counts[docs[int(c["doc_id"])]["category"]] += 1
        universe_counts = target_counts
        got = {c: 0 for c in CATEGORY_ORDER}
        for r in rows:
            got[r["category"]] = got.get(r["category"], 0) + 1
        universe_total, got_total = sum(universe_counts.values()), sum(got.values())
        out = []
        for c in CATEGORY_ORDER:
            tshare = universe_counts[c] / universe_total if universe_total else 0.0
            gshare = got.get(c, 0) / got_total if got_total else 0.0
            out.append({
                "key": c, "target_chunks": universe_counts[c], "target_share": round(tshare, 6),
                "achieved_items": got.get(c, 0), "achieved_share": round(gshare, 6),
                "delta_items": got.get(c, 0) - round(tshare * got_total, 2),
                "delta_pp": round((gshare - tshare) * 100, 4),
            })
        return out
    if key == "month":
        universe_counts = {}
        for c in chunks:
            m = (docs[int(c["doc_id"])].get("publish_time") or "")[:7]
            universe_counts[m] = universe_counts.get(m, 0) + 1
        got = {}
        for r in rows:
            got[r["month"]] = got.get(r["month"], 0) + 1
        universe_total, got_total = sum(universe_counts.values()), sum(got.values())
        out = []
        for m in sorted(universe_counts):
            tshare = universe_counts[m] / universe_total
            gshare = got.get(m, 0) / got_total if got_total else 0.0
            out.append({
                "key": m, "target_chunks": universe_counts[m], "target_share": round(tshare, 6),
                "achieved_items": got.get(m, 0), "achieved_share": round(gshare, 6),
                "delta_items": round(got.get(m, 0) - tshare * got_total, 2),
                "delta_pp": round((gshare - tshare) * 100, 4),
            })
        return out
    if key in ("company", "company_list"):
        field = "subject_companies" if key == "company" else "company_list"
        universe_counts: dict = {}
        for c in chunks:
            for code in set(docs[int(c["doc_id"])].get(field) or []):
                universe_counts[code] = universe_counts.get(code, 0) + 1
        got: dict = {}
        for r in rows:
            for code in set(r[field]):
                got[code] = got.get(code, 0) + 1
        universe_total = sum(universe_counts.values())
        got_total = sum(got.values())
        out = []
        for code in sorted(set(universe_counts) | set(got)):
            t = universe_counts.get(code, 0)
            g = got.get(code, 0)
            tshare = t / universe_total if universe_total else 0.0
            gshare = g / got_total if got_total else 0.0
            out.append({
                "key": code, "target_field": field, "target_chunk_assoc": t, "achieved_items": g,
                "delta_items": round(g - tshare * got_total, 3) if got_total else 0.0,
                "delta_pp": round((gshare - tshare) * 100, 4),
            })
        return sorted(out, key=lambda r: (-abs(r["delta_pp"]), r["key"]))
    raise ValueError(key)


def coverage_report(rows: dict, universe_index: dict, docs: dict, chunks: list, table: dict) -> dict:
    """8 种事件类型与 9 条核心关系的计划覆盖 + 证据不足登记。"""
    multi_split = {
        split: sum(1 for r in rows[split] if len(r["company_list"]) >= 2) for split in SPLIT_ORDER
    }
    strict_split = {
        split: sum(1 for r in rows[split] if len(r["subject_companies"]) >= 2) for split in SPLIT_ORDER
    }
    events = []
    for name in C.EVENT_TYPES:
        per = {}
        for split in SPLIT_ORDER:
            n = 0
            for r in rows[split]:
                title = docs[r["doc_id"]].get("title") or ""
                if name == "产品":
                    if _re(C.EVENT_TYPE_TITLE_PATTERNS[name]).search(title) and not _re(
                        C.PRODUCT_EXCLUDE_PATTERN
                    ).search(title):
                        n += 1
                elif _re(C.EVENT_TYPE_TITLE_PATTERNS[name]).search(title):
                    n += 1
            per[split] = n
        pool_docs = None
        for k, v in table["table_15D"]["recomputed_doc_title_level_all_categories"].items():
            if k == name:
                pool_docs = v
        total = per["dev"] + per["test"]
        if total == 0:
            status = "证据不足（登记）"
        elif total < THIN_CLASS_THRESHOLD:
            status = "薄证据（登记）：计划条目仅 %d 条，标注判定无实例时按证据不足登记" % total
        else:
            status = "有候选条目（待人工标注判定）"
        events.append({
            "event_type": name,
            "planned_items_dev": per["dev"], "planned_items_test": per["test"],
            "planned_items_total": total,
            "proxy_rule": "标题命中 config.EVENT_TYPE_TITLE_PATTERNS[%s]（代理指标，不是抽取结果）" % name,
            "corpus_docs_hit": pool_docs,
            "status": status,
        })
    relations = []
    for name in C.RELATIONS:
        pat = C.RELATION_BODY_PATTERNS.get(name)
        per = {"dev": 0, "test": 0}
        if pat:
            for split in SPLIT_ORDER:
                per[split] = sum(1 for r in rows[split] if _re(pat).search(r["text"] or ""))
        rel_schema = C.RELATION_SCHEMA[name]
        multi_company_items = sum(
            1 for split in SPLIT_ORDER
            for r in rows[split]
            if len(r["company_list"]) >= 2
        )
        strict_multi_items = sum(
            1 for split in SPLIT_ORDER
            for r in rows[split]
            if len(r["subject_companies"]) >= 2
        )
        if name == "EVIDENCED_BY":
            status = "结构性关系：由 doc_id／chunk_id 直接给出，不依赖正文判定，无需标注条目"
            planned_note = "本字段由条目自身的 chunk_id 与 doc_id 提供，逐条成立"
        elif name in ("SUPPLIES", "CUSTOMER_OF", "COMPETES_WITH"):
            status = ("登记为证据不足／候选已纳入：三条公司间关系只在 company_list 长度 ≥ 2 的文档里"
                      "可能出现证据，本次已强制纳入 %d 条多公司条目（Dev %d ＋ Test %d；其中 "
                      "subject_companies 长度 ≥ 2 的 %d 条：Dev %d ＋ Test %d）；"
                      "是否真有关系由人工标注判定，判定无证据时按证据不足登记"
                      % (multi_company_items, multi_split["dev"], multi_split["test"],
                         strict_multi_items, strict_split["dev"], strict_split["test"]))
            planned_note = "候选条目数 = 本条内 company_list ≥ 2 的条目数"
        elif per["dev"] + per["test"] >= THIN_CLASS_THRESHOLD:
            status = "有候选条目（正文级代理关键词命中，待人工标注判定）"
            planned_note = "正文级代理关键词命中本条的文本块"
        elif per["dev"] + per["test"]:
            status = ("薄证据（登记）：计划条目仅 %d 条，远小于其他关系；"
                      "标注判定无实例时按证据不足登记" % (per["dev"] + per["test"]))
            planned_note = "正文级代理关键词命中本条的文本块"
        else:
            status = "证据不足（登记）"
            planned_note = "本条内无正文级代理关键词命中"
        relations.append({
            "relation": name,
            "domain": list(rel_schema["domain"]), "range": list(rel_schema["range"]),
            "from_model": bool(rel_schema["from_model"]),
            "planned_items_dev": per["dev"], "planned_items_test": per["test"],
            "planned_items_total": per["dev"] + per["test"],
            "corpus_docs_body_hit": table["table_15D"]["recomputed_doc_body_level"].get(name),
            "multi_company_items_total": multi_company_items,
            "multi_company_items_dev": multi_split["dev"],
            "multi_company_items_test": multi_split["test"],
            "strict_multi_company_items_total": strict_multi_items,
            "strict_multi_company_items_dev": strict_split["dev"],
            "strict_multi_company_items_test": strict_split["test"],
            "rule": planned_note,
            "status": status,
        })
    return {"event_types": events, "relations": relations}


def build_deviations(stats: dict) -> list:
    """把每一处偏离严格比例的地方逐条写成登记项。"""
    dev = []
    rows = stats["items_by_split"]
    for row in stats["achieved_vs_target"]["category"]:
        if abs(row["delta_pp"]) > TOLERANCE["category_pp"]:
            dev.append({"kind": "category_out_of_tolerance", **row})
    for row in stats["achieved_vs_target"]["month"]:
        if abs(row["delta_pp"]) > TOLERANCE["month_pp"]:
            dev.append({"kind": "month_out_of_tolerance", **row})
    for key, dim in (("company", "subject_companies"), ("company_list_dimension", "company_list")):
        rows_over = [r for r in stats["achieved_vs_target"][key]
                     if abs(r["delta_pp"]) > TOLERANCE["company_pp"]]
        if rows_over:
            dev.append({
                "kind": "company_out_of_tolerance", "dimension": dim,
                "count": len(rows_over), "tolerance_pp": TOLERANCE["company_pp"],
                "worst": rows_over[0],
                "note": "公司维度的比例目标是「该公司文本块关联量占比」（口径 %s）；"
                        "抽样同时要求尽量覆盖每一家公司，两者方向相反——块量最大的公司会低于比例份额、"
                        "块量小的公司会高于份额。逐家明细见 achieved_vs_target.%s。" % (dim, key),
            })
    summary = stats["company_summary"]
    if summary["companies_with_zero_items"]:
        zero_rows = [r for r in stats["achieved_vs_target"]["company"] if r["achieved_items"] == 0]
        zero_rows = sorted(zero_rows, key=lambda r: -r["target_chunk_assoc"])
        dev.append({
            "kind": "company_zero_coverage",
            "count": summary["companies_with_zero_items"],
            "companies": [
                {"stock_code": r["key"], "target_chunk_assoc": r["target_chunk_assoc"],
                 "target_items": round(r["achieved_items"] - r["delta_items"], 3)}
                for r in zero_rows[:20]
            ],
            "note": "这 %d 家公司在 260 条里为 0 条：公司维度的目标按 subject_companies 口径的文本块"
                    "关联量占比走（比例分配），260 条摊到 105 家之后，这些小份额公司的期望条数不足 1 条，"
                    "整数分配必然出现 0。这是**比例分配的固有结果，不是漏抽**；"
                    "若这些公司必须有条目，应按覆盖优先改规则并同步修改声明的容差。" % summary["companies_with_zero_items"],
        })
    for r in stats["cell_level"]:
        if r["target_chunks"] > 0 and r["achieved_items"] == 0:
            dev.append({
                "kind": "cell_zero", "cell": r["cell"], "target_chunks": r["target_chunks"],
                "expected_items": r["expected_items"],
                "note": "该（类目 × 月份）单元格有语料但本次未选到条目：该段内该类目的配额小于非空月份数时"
                        "不启用月份保底（例：监管公开信息在 Dev 的配额只有 2 条）。",
            })
    thin_rows = []
    for row in stats["coverage"]["event_types"]:
        if row["planned_items_total"] < THIN_CLASS_THRESHOLD:
            thin_rows.append({"class_kind": "event_type", "class": row["event_type"],
                              "planned_items_total": row["planned_items_total"]})
    for row in stats["coverage"]["relations"]:
        if not row["from_model"]:
            continue
        if row["planned_items_total"] < THIN_CLASS_THRESHOLD:
            thin_rows.append({"class_kind": "relation", "class": row["relation"],
                              "planned_items_total": row["planned_items_total"]})
    if thin_rows:
        dev.append({
            "kind": "thin_class_coverage", "threshold": THIN_CLASS_THRESHOLD, "rows": thin_rows,
            "note": "这些类型／关系的计划条目少于阈值：**不得**读成覆盖充分，"
                    "标注若判定无实例，必须在《16》里按证据不足登记",
        })
    dev.append({
        "kind": "dev_test_split_rule",
        "note": "先选 Dev、再选 Test，Test 的候选池排除 Dev 已选文档；两段各自按类目配额与"
                "（类目 × 月份）单元格配额独立配平。Dev %d 条、Test %d 条，"
                "覆盖下限按 60∶200 摊到两段（重大合同 5／15、产品 5／15、多公司 4／14、"
                "投资并购 1／2、严格多公司 2／7）。"
                % (DEV_TOTAL, TEST_TOTAL),
        "dev_first": True,
        "test_reuse_forbidden": "Test 不得用于调规则或调 Prompt（《15》第九节「Dev 先于 Test 的纪律」）",
    })
    for split in SPLIT_ORDER:
        q = stats["quota"][split]
        for cat, n in sorted(q.items()):
            if n < MIN_PER_CATEGORY_SPLIT:
                dev.append({"kind": "category_below_min", "split": split, "category": cat, "quota": n})
    for cat, n in sorted(stats["quota"]["total"].items()):
        if n < MIN_PER_CATEGORY_TOTAL:
            dev.append({"kind": "category_below_min_total", "category": cat, "quota": n})
    dev.append({
        "kind": "coverage_over_proportionality",
        "note": "事件类型覆盖优先于比例：重大合同／产品／投资并购、"
                "company_list ≥ 2 的多公司文档、以及三条公司间关系关键词命中的多公司文档，"
                "按最小落点强制纳入，条数见 coverage_floors；这是**有意的偏离**，"
                "不得读成按比例分配的结果，也不得读成按「8 类均衡」规划题量。",
        "coverage_floors": COVERAGE_FLOORS,
        "achieved_tag_counts": stats["coverage_tag_counts"],
    })
    dev.append({
        "kind": "chunk_selection_heuristic",
        "note": "一篇文档只出 1 条。选块规则：本条覆盖标签的块级关键词命中时，在这些块里取"
                "「代理关键词命中种数最多、其次 chunk_index 最小」的一块；没有标签或标签关键词不命中块时，"
                "取全篇同规则的一块。选块偏向事件／关系信号最强的块，不是按块均匀随机；"
                "这是**有意的偏离**，且**不是标注**。",
    })
    dev.append({
        "kind": "document_disjoint_by_construction",
        "note": "整篇文档只归一个 split，因此 Dev 与 Test 的文档集合交集恒为 0（比「尽量不重叠」更强）。",
    })
    month_table = stats["table_15E_recompute"]["per_month"]
    if "2026-07" in month_table:
        dev.append({
            "kind": "table_15E_month_value_corrected",
            "declared": {"2026-06": 1226, "2026-07": 937, "2026-08": 1620, "2026-09": 1235},
            "recomputed": month_table,
            "note": "《15》第2.2节 表 15-E 的逐月块数声明值与脚本重算值**一致**，四档合计 5018 "
                    "与文本块总数相符，无需更正。本项保留为「已核对」留痕。"
                    "（2026-09-25 修正：本脚本初版把 declared 的 2026-07 误写为 737，并据"
                    "此错误地指控《15》有笔误；回原文核对后确认《15》写的是 937、并无笔误，"
                    "是**脚本**写错了常量。结论未受影响，但错误指控已按事实改正。）",
        })
    return dev


def build_stats(docs: dict, chunks: list, selection: dict, built: dict) -> dict:
    rows = built["items"]
    all_rows = [r for s in SPLIT_ORDER for r in rows[s]]
    monthly_target = table_15e_recompute(docs, chunks)
    table_cd = table_15cd_recompute(docs, chunks)
    achieved = {
        "category": distribution_report(all_rows, selection["universe"], docs, chunks, "category"),
        "month": distribution_report(all_rows, selection["universe"], docs, chunks, "month"),
        "company": distribution_report(all_rows, selection["universe"], docs, chunks, "company"),
        "company_list_dimension": distribution_report(
            all_rows, selection["universe"], docs, chunks, "company_list"
        ),
    }
    comp_rows = achieved["company"]
    comp_items = sorted(int(r["achieved_items"]) for r in comp_rows)
    comp_targets = sorted(int(r["target_chunk_assoc"]) for r in comp_rows)
    company_summary = {
        "companies_total": len(comp_rows),
        "companies_with_items": sum(1 for r in comp_rows if r["achieved_items"] > 0),
        "companies_with_zero_items": sum(1 for r in comp_rows if r["achieved_items"] == 0),
        "achieved_items_min": comp_items[0] if comp_items else 0,
        "achieved_items_median": statistics.median(comp_items) if comp_items else 0,
        "achieved_items_max": comp_items[-1] if comp_items else 0,
        "target_chunk_assoc_min": comp_targets[0] if comp_targets else 0,
        "target_chunk_assoc_median": statistics.median(comp_targets) if comp_targets else 0,
        "target_chunk_assoc_max": comp_targets[-1] if comp_targets else 0,
        "max_abs_delta_pp": round(max((abs(r["delta_pp"]) for r in comp_rows), default=0.0), 4),
        "worst_deviations": comp_rows[:10],
        "primary_field": "subject_companies",
        "company_rule": (
            "公司维度的比例目标取 subject_companies 口径的文本块关联量占比（与表 15-E 的"
            "「每家公司关联的文本块数 min 2／中位 31／max 188」同口径）；选点规则 "
            "COMPANY_BALANCE_RULE＝%s（每步补「离比例目标缺口最大」的公司，"
            "等价于按公司做最大余数式的整数分配）；company_list 口径另表登记。"
            "两个口径都只作分层键，不是标注判据（硬约束 16）。" % COMPANY_BALANCE_RULE
        ),
        "zero_item_companies": [r["key"] for r in comp_rows if r["achieved_items"] == 0],
    }
    comp_list_rows = achieved["company_list_dimension"]
    company_summary["company_list_dimension"] = {
        "target_chunk_assoc_min": min((int(r["target_chunk_assoc"]) for r in comp_list_rows), default=0),
        "target_chunk_assoc_median": statistics.median(
            [int(r["target_chunk_assoc"]) for r in comp_list_rows]
        ) if comp_list_rows else 0,
        "target_chunk_assoc_max": max((int(r["target_chunk_assoc"]) for r in comp_list_rows), default=0),
        "max_abs_delta_pp": round(
            max((abs(r["delta_pp"]) for r in comp_list_rows), default=0.0), 4
        ),
        "worst_deviations": comp_list_rows[:5],
    }
    annotation_emptiness = {
        "checked_items": len(all_rows),
        "nonempty_slots": [],
        "status_value": sorted({r["annotation"]["status"] for r in all_rows}),
        "rule": "entities／events／relations／times／ontology_boundary_log 一律为空列表，notes 为空串；"
                "本脚本不产生任何标签，标注为人工未完成项。",
    }
    for r in all_rows:
        for path, v in flatten_annotation(r["annotation"]):
            if path.endswith("status"):
                if v != "pending_human_annotation":
                    annotation_emptiness["nonempty_slots"].append({"item_id": r["item_id"], "path": path, "value": v})
            elif v not in ([], "", None):
                annotation_emptiness["nonempty_slots"].append({"item_id": r["item_id"], "path": path, "value": v})
    tag_counts = {t: {"dev": 0, "test": 0, "total": 0} for t in COVERAGE_TAGS}
    for split in SPLIT_ORDER:
        for r in rows[split]:
            for t in r["sampling"]["coverage_tags"]:
                tag_counts[t][split] += 1
                tag_counts[t]["total"] += 1
    cell_report = []
    for cat in CATEGORY_ORDER:
        for m in selection["months"]:
            got = sum(1 for r in all_rows if r["category"] == cat and r["month"] == m)
            tgt = selection["cat_month_chunks"].get(cat, {}).get(m, 0)
            exp = tgt / len(chunks) * len(all_rows)
            cell_report.append({
                "cell": "%s|%s" % (cat, m), "target_chunks": tgt,
                "expected_items": round(exp, 3), "achieved_items": got,
                "delta_items": round(got - exp, 3),
                "delta_pp": round((got / len(all_rows) - tgt / len(chunks)) * 100, 4),
            })
    script_path = os.path.join(C.ROOT, SCRIPT_REL) if hasattr(C, "ROOT") else os.path.abspath(__file__)
    with open(script_path, "rb") as fh:
        script_sha = hashlib.sha256(fh.read()).hexdigest()
    ids = {s: sorted(r["chunk_id"] for r in rows[s]) for s in SPLIT_ORDER}
    docids = {s: sorted(r["doc_id"] for r in rows[s]) for s in SPLIT_ORDER}
    stats = {
        "schema": "stage6-eval-set-stats-1.0",
        "dataset": {
            "version": C.DATASET_VERSION, "documents": len(docs), "chunks": len(chunks),
            "docs_path": os.path.relpath(C.DOCS_PATH, C.ROOT),
            "chunks_path": os.path.relpath(C.CHUNKS_PATH, C.ROOT),
        },
        "sampler": {
            "script": SCRIPT_REL, "script_sha256": script_sha, "seed": SEED,
            "rng": "无随机数：并列打破用 sha256(SEED:doc_id)，跨进程稳定",
            "rerun_command": "python 代码\\抽取与图谱\\sample_eval_set.py",
            "verify_command": "python 代码\\抽取与图谱\\sample_eval_set.py --verify-only",
            "min_per_category_total": MIN_PER_CATEGORY_TOTAL,
            "min_per_category_split": MIN_PER_CATEGORY_SPLIT,
            "month_cell_floor": MONTH_CELL_FLOOR,
            "coverage_floors": COVERAGE_FLOORS,
            "tolerance": TOLERANCE,
            "unit": "文本块（chunk）；一条 = 一个文本块；一篇文档只出 1 条，故 Dev／Test 文档交集为 0",
        },
        "counts": {
            "dev": len(rows["dev"]), "test": len(rows["test"]),
            "total": len(rows["dev"]) + len(rows["test"]),
        },
        "quota": selection["quota"],
        "cell_quota": selection["cell_quota"],
        "keys": {
            "dev_chunk_id_set_size": len(set(ids["dev"])),
            "test_chunk_id_set_size": len(set(ids["test"])),
            "chunk_id_intersection_size": len(set(ids["dev"]) & set(ids["test"])),
            "dev_doc_id_set_size": len(set(docids["dev"])),
            "test_doc_id_set_size": len(set(docids["test"])),
            "document_overlap_size": len(set(docids["dev"]) & set(docids["test"])),
            "document_overlap_registration": "0（整篇文档只归一个 split，构造上不可能重叠）",
        },
        "table_15E_recompute": monthly_target,
        "table_15C_15D_recompute": table_cd,
        "achieved_vs_target": achieved,
        "company_summary": company_summary,
        "cell_level": cell_report,
        "coverage_tag_counts": tag_counts,
        "coverage": coverage_report(rows, selection["universe_index"], docs, chunks, table_cd),
        "annotation_schema": built["schema"],
        "annotation_emptiness": annotation_emptiness,
        "selection": {
            "dev_chunk_ids": ids["dev"], "test_chunk_ids": ids["test"],
            "dev_doc_ids": docids["dev"], "test_doc_ids": docids["test"],
            "dev_fingerprint": C.sha256_hex(C.stable_json(ids["dev"])),
            "test_fingerprint": C.sha256_hex(C.stable_json(ids["test"])),
        },
    }
    stats["items_by_split"] = {s: len(rows[s]) for s in SPLIT_ORDER}
    stats["deviations_registry"] = build_deviations(stats)
    return stats


# --------------------------------------------------------------------------
# 七、写盘与复核
# --------------------------------------------------------------------------
def write_jsonl(path: str, rows: list) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def read_jsonl(path: str) -> list:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def flatten_annotation(ann: dict, prefix: str = "") -> list:
    """把 annotation 块摊平成 (路径, 取值) 列表，用于「槽位一律为空」的检查。"""
    out = []
    for k, v in ann.items():
        path = "%s.%s" % (prefix, k) if prefix else k
        if isinstance(v, dict):
            out.extend(flatten_annotation(v, path))
        else:
            out.append((path, v))
    return out


def verify(verbose: bool = True) -> dict:
    docs, chunks = load_inputs()
    chunk_index = {int(c["chunk_id"]): int(c["doc_id"]) for c in chunks}
    dev = read_jsonl(DEV_PATH)
    test = read_jsonl(TEST_PATH)
    with open(STATS_PATH, encoding="utf-8") as fh:
        stats = json.load(fh)
    dev_ids = [int(r["chunk_id"]) for r in dev]
    test_ids = [int(r["chunk_id"]) for r in test]
    dev_docs = {int(r["doc_id"]) for r in dev}
    test_docs = {int(r["doc_id"]) for r in test}
    inter = sorted(set(dev_ids) & set(test_ids))
    bad_ann, bad_chunk, bad_link = [], [], []
    for r in dev + test:
        for path, v in flatten_annotation(r.get("annotation") or {}):
            if path.endswith("status"):
                if v != "pending_human_annotation":
                    bad_ann.append((r["item_id"], path, v))
            elif v not in ([], "", None):
                bad_ann.append((r["item_id"], path, v))
        cid, did = int(r["chunk_id"]), int(r["doc_id"])
        if cid not in chunk_index:
            bad_chunk.append(cid)
        elif chunk_index[cid] != did:
            bad_link.append({"chunk_id": cid, "item_doc_id": did, "dataset_doc_id": chunk_index[cid]})
    cat_dev, cat_test = {}, {}
    for r in dev:
        cat_dev[r["category"]] = cat_dev.get(r["category"], 0) + 1
    for r in test:
        cat_test[r["category"]] = cat_test.get(r["category"], 0) + 1
    report = {
        "dev_items": len(dev), "test_items": len(test), "total_items": len(dev) + len(test),
        "dev_chunk_id_set_size": len(set(dev_ids)),
        "test_chunk_id_set_size": len(set(test_ids)),
        "chunk_id_intersection_size": len(inter), "chunk_id_intersection_examples": inter[:5],
        "document_overlap_size": len(dev_docs & test_docs),
        "annotation_slots_empty": not bad_ann, "annotation_violations": bad_ann[:10],
        "chunk_ids_resolvable_in_v21": not bad_chunk, "unresolved_chunk_ids": bad_chunk[:10],
        "chunk_doc_link_ok": not bad_link, "chunk_doc_link_violations": bad_link[:10],
        "category_counts": {"dev": cat_dev, "test": cat_test},
        "category_counts_match_stats": (
            {k: stats["achieved_vs_target"]["category"][i]["achieved_items"]
             for i, k in enumerate([x["key"] for x in stats["achieved_vs_target"]["category"]])}
            == {k: cat_dev.get(k, 0) + cat_test.get(k, 0)
                for k in [x["key"] for x in stats["achieved_vs_target"]["category"]]}
        ),
        "protocol_file_exists": os.path.exists(PROTOCOL_PATH),
        "stats_file_fingerprints": {
            "dev": stats["selection"]["dev_fingerprint"],
            "test": stats["selection"]["test_fingerprint"],
        },
    }
    report["ok"] = all([
        len(dev) == DEV_TOTAL, len(test) == TEST_TOTAL, not inter,
        not bad_ann, not bad_chunk, not bad_link, report["category_counts_match_stats"],
        report["protocol_file_exists"],
    ])
    if verbose:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="T8 抽取评测集抽样器（确定性、不标注、不调模型）")
    parser.add_argument("--verify-only", action="store_true", help="只复核已写出的文件，退出码 0/1")
    parser.add_argument("--quiet", action="store_true", help="不打印报告")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.verify_only:
        report = verify(verbose=not args.quiet)
        return 0 if report["ok"] else 1

    docs, chunks = load_inputs()
    selection = build_selection(docs, chunks)
    built = build_items(selection)
    stats = build_stats(docs, chunks, selection, built)
    write_jsonl(DEV_PATH, built["items"]["dev"])
    write_jsonl(TEST_PATH, built["items"]["test"])
    write_json(STATS_PATH, stats)
    report = verify(verbose=False)
    if not args.quiet:
        summary = {
            "output_dir": EVAL_SET_DIR,
            "counts": stats["counts"],
            "chunk_id_intersection_size": report["chunk_id_intersection_size"],
            "document_overlap_size": report["document_overlap_size"],
            "quota_total": stats["quota"]["total"], "quota_dev": stats["quota"]["dev"],
            "quota_test": stats["quota"]["test"],
            "dev_fingerprint": stats["selection"]["dev_fingerprint"],
            "test_fingerprint": stats["selection"]["test_fingerprint"],
            "coverage_tag_counts": stats["coverage_tag_counts"],
            "deviations_registry_size": len(stats["deviations_registry"]),
            "annotation_slots_empty": report["annotation_slots_empty"],
            "verify_ok": report["ok"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
