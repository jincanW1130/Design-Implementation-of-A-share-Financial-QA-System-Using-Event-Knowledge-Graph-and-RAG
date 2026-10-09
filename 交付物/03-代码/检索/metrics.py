# -*- coding: utf-8 -*-
"""代码\\检索\\metrics.py —— T10：四项检索指标的计算路径（第 7 阶段 RAG 检索系统）。

对应《18-第7阶段任务书（RAG检索系统）》第九节 T10 与 第八节 第 18／19 行。

**四项指标的口径一律以《02-项目执行总控文档》为准，本文件不自行发明公式。** 引用的节号：

* 《02》**第12.7节**（"评价指标与定义"）——四项指标的**定义原文**：

  - Recall@K（chunk 级）：Top-K 中命中的 gold 证据文本块数 ÷ 该问题 gold 证据文本块总数，按问题取平均。
  - Precision@K（chunk 级）：Top-K 中属于 gold 证据的文本块数 ÷ K，按问题取平均。
  - MRR（chunk 级）：第一个 gold 证据文本块所在排名的倒数，按问题取平均；前 K 内无 gold 证据则该问题记 0。
  - Complete Evidence Recall@K（问题级）：该问题的 gold 证据文本块全部出现在 Top-K 中记 1，
    否则记 0，按问题取平均。

  同节并规定："文档级只在需要诊断时作为辅助口径使用，且必须在论文中单独标注，**不得与 chunk 级混算**。"

* 《02》**第12.4节**（"实验配置固定表"）——Top-K（K）一行的说明：
  "**每个问题最终证据集合的文本块数量上限**，同时就是 12.7 节四项检索指标里的 K"。

* 《02》**第12.7节 第二～五步**——Top-K 证据集合的形成规则；
  其中第五步写明："为保证 Precision@K 的分母为 K 且可跨题比较……候选证据不足 K 的题目在
  **测试集构建阶段**调整……**题目一旦入库，不得因该题实验时的实际候选数少于 K 而将其排除，
  空缺位置记为未命中并按原指标定义计算**"。本文件据此实现"**分母恒为 K**"，
  **不实现任何运行时的筛题（删题）逻辑**（《18》第五节 硬约束 8；《10》第4.6.4节）。

* 《18》第五节 硬约束 7（主口径统一为文本块级）、硬约束 8（Precision@K 分母恒为 K）、
  第2.3节"检索指标四项"行、第六节 的格式决策 4（落盘格式）。

三条不可退让的纪律：

1. **只接受 `chunk_id`**：四个指标函数只吃 `chunk_id`（有序列表或集合都接受，内部一律按
   **集合语义**处理——同一文本块被两路命中只算一个证据，不重复计数）。文档级诊断**另开函数**、
   单独命名（`recall_at_k_doc_level_diagnostic`）、在返回值里带 `level: "document"` 标记，
   并且**绝不与 chunk 级放进同一个平均值**：`aggregate_chunk_level` 会拒绝任何 `level != "chunk"` 的行，
   `aggregate_doc_level_diagnostic` 会拒绝任何 `level != "document"` 的行。
2. **可重算**：给定同一份最终证据集合与 gold，输出**逐字节一致**——固定键序、固定排序、
   浮点一律 `round` 到 8 位；输出文件里**不写运行时间戳、不写耗时**（耗时只打印到 stdout）。
3. **K 是每个问题最终证据集合的文本块数量上限**，同时就是本文件四项指标里的 K；
   图谱路径与事件三元组**不计入 K**（检索指标只统计文本块级证据）。

本阶段链路 **0 次大语言模型／外部接口调用**：本文件是纯计算，不读索引、不读图谱、不联网、不读密钥。

用法::

    python 代码\\检索\\metrics.py --selftest
    python 代码\\检索\\metrics.py                       :: 产出 检索产出\\metrics_pre.jsonl
    python 代码\\检索\\metrics.py --k 10 --out <路径>
    python 代码\\检索\\metrics.py --from-trace 交付物/05-系统实现/RAG检索系统\\检索产出\\per_question_trace.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

try:  # 控制台为 GBK 时也要能输出中文
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # 极少见的非文本流 stdout，重设失败不致命
    pass

# config.py 与本脚本同目录，显式加入 sys.path，保证任意工作目录下都能导入。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  唯一参数来源，不得绕过

# 浮点固定精度（《18》第4.2节 幂等与可复现：参与逐字节比对的文件不得写入未定序的浮点值）
ROUND = 8

# 四项指标的固定顺序（键序固定；"按问题取平均"一律按此顺序）
CHUNK_METRIC_KEYS = ["recall_at_k", "precision_at_k", "mrr", "complete_evidence_recall_at_k"]

# 四项指标各自的作用层次（硬约束 7：主口径文本块级；Complete Evidence Recall 是问题级）
METRIC_LEVELS = {
    "recall_at_k": "chunk",
    "precision_at_k": "chunk",
    "mrr": "chunk",
    "complete_evidence_recall_at_k": "question",
}

# 题集里与检索无关、但用于第 10 阶段分组统计的标签（只透传，不参与指标计算）
TAG_KEYS = ["task_type", "gold_hop_depth", "time_constraint", "time_window"]


def _r(x) -> float:
    """固定精度：一律 round 到 8 位，保证逐字节可复现。"""
    return round(float(x), ROUND)


def _as_unique_ordered(ids):
    """把"有序列表或集合"统一成"按首次出现顺序去重的列表"（集合语义）。

    `chunk_id` 在 v2.1 的 `vector_map.jsonl`／`chunks.jsonl` 里形如 `1001001`（整数），
    而在图谱导出物的 `source_chunk_id` 里是字符串 `"1339012"`。为免 `1001001` 与
    `"1001001"` 被判成两个不同的块，这里统一按 `str` 规范化后再比较
    （硬约束 7、硬约束 14：两路候选统一映射到 `chunk_id` 后按集合语义合并）。
    """
    out, seen = [], set()
    for x in ids or ():
        s = str(x)
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _check_k(K) -> int:
    """K 必须是正整数（K 是每个问题最终证据集合的文本块数量上限）。"""
    k = int(K)
    if k < 1:
        raise ValueError("K 必须为正整数（收到 K=%r）；K 是每个问题最终证据集合的文本块数量上限" % (K,))
    return k


def _top_k_ids(final_ids, K):
    """按集合语义去重、保留原顺序、截断到前 K 个（Top-K 中"K 是数量上限"的落点）。"""
    return _as_unique_ordered(final_ids)[:_check_k(K)]


# --------------------------------------------------------------------------
# 一、四项指标（**只接受 chunk_id**）
# --------------------------------------------------------------------------
def recall_at_k(final_ids, gold_ids, K):
    """Recall@K（chunk 级）——"召回了多少"。

    口径（《02》**第12.7节**）：Top-K 中命中的 gold 证据文本块数 ÷ 该问题 gold 证据
    文本块总数，按问题取平均。K 是**每个问题最终证据集合的文本块数量上限**，
    同时就是本指标里的 K。

    `final_ids`／`gold_ids` 只接受 `chunk_id`：有序列表或集合都接受，内部按**集合语义**
    处理（同一文本块只算一次）。命中数取 `set(Top-K) ∩ set(gold)` 的元素个数。

    边界（不抛异常，明确记 0 并说明理由）：该问题 gold 证据为空 → 分母为 0，定义上
    不可召回，记 `0.0`；最终证据集合为空 → 命中数为 0，记 `0.0`。
    """
    gold = set(_as_unique_ordered(gold_ids))
    if not gold:
        return 0.0                      # 空 gold：分母为 0，记 0（不抛异常）
    top = _top_k_ids(final_ids, K)
    if not top:
        return 0.0                      # 空 final：命中 0
    return _r(len(set(top) & gold) / len(gold))


def precision_at_k(final_ids, gold_ids, K):
    """Precision@K（chunk 级）——**分母恒为 K**。

    口径（《02》**第12.7节**）：Top-K 中属于 gold 证据的文本块数 ÷ K，按问题取平均。
    K 是**每个问题最终证据集合的文本块数量上限**，同时就是本指标里的 K。

    **分母恒为 K（硬约束 8）**：实际候选数 M < K 时，空缺的 `K − M` 个位置记为未命中，
    分母仍是 K、不是 M；题目**保留、不删**（《02》第12.7节 第五步：题目一旦入库不得因
    实验时候选少而删题；《10》第4.6.4节）。本函数**没有**任何筛题分支。

    `final_ids`／`gold_ids` 只接受 `chunk_id`，按集合语义处理。gold 为空时命中数为 0，
    结果 `0.0`（分母仍是 K）。
    """
    k = _check_k(K)
    gold = set(_as_unique_ordered(gold_ids))
    top = _top_k_ids(final_ids, k)
    hits = len(set(top) & gold) if gold else 0
    return _r(hits / k)                 # 分母恒为 K：M < K 时空缺记未命中


def mrr(final_ids, gold_ids):
    """MRR（chunk 级）——第一个 gold 证据所在排名的倒数。

    口径（《02》**第12.7节**）：第一个 gold 证据文本块所在排名的倒数，按问题取平均；
    前 K 内无 gold 证据则该问题记 0。传入的 `final_ids` 已经是"不超过 K 个文本块"的
    最终证据集合（K 是**每个问题最终证据集合的文本块数量上限**），故本函数不再要 K。

    **调用方义务（2026-09-28 第二轮复审 B-15 整改）**：本函数按传入顺序取首个命中，
    因此调用方必须传**已经截断到前 K 个**的集合；`evaluate_question_chunk_level()`
    已按此口径改用 `final[:K]`（此前传的是未截断的 `final`，当 `|final| > K` 且 gold
    只落在第 K 名之后时会算出 `n_hit=0` 而 `mrr>0` 的矛盾读数）。

    `final_ids` 只接受 `chunk_id`，按集合语义去重后**按原顺序**找首个命中：
    排名从 1 起算，命中在第 r 位即 `1/r`。边界（不抛异常，记 0）：gold 为空，或
    集合内无命中 → `0.0`。
    """
    gold = set(_as_unique_ordered(gold_ids))
    if not gold:
        return 0.0                      # 空 gold：记 0
    for rank, cid in enumerate(_as_unique_ordered(final_ids), 1):
        if cid in gold:
            return _r(1.0 / rank)       # 首个命中在第 rank 位 → 1/rank
    return 0.0                          # 前 K 内无 gold 证据 → 记 0


def complete_evidence_recall_at_k(final_ids, gold_ids, K):
    """Complete Evidence Recall@K（**问题级**）——"是否被完整召回"。

    口径（《02》**第12.7节**）：该问题的 gold 证据文本块**全部**出现在 Top-K 中记 1，
    否则记 0，按问题取平均。K 是**每个问题最终证据集合的文本块数量上限**，
    同时就是本指标里的 K。

    本指标是**问题级**的 1／0 判断（gold ⊆ Top-K 即 1），**不是**题内比例；
    它的"平均"是对题取平均（逐题得 0 或 1 后再平均）。

    `final_ids`／`gold_ids` 只接受 `chunk_id`，按集合语义处理。边界（不抛异常，记 0）：
    gold 为空 → 问题级覆盖无定义，记 `0.0`；gold 非空而最终集合为空 → 覆盖不成立，记 `0.0`。
    """
    gold = set(_as_unique_ordered(gold_ids))
    if not gold:
        return 0.0                      # 空 gold：记 0（并说明理由）
    top = set(_top_k_ids(final_ids, K))
    return 1.0 if gold <= top else 0.0


# --------------------------------------------------------------------------
# 二、文档级诊断（**单独命名、单独标注**，绝不与 chunk 级混算）
# --------------------------------------------------------------------------
def recall_at_k_doc_level_diagnostic(final_doc_ids, gold_doc_ids, K):
    """【仅诊断｜文档级｜`level="document"`】文档级 Recall@K——**辅助口径，不入主口径**。

    《02》**第12.7节**："文档级只在需要诊断时作为辅助口径使用，且必须在论文中单独标注，
    **不得与 chunk 级混算**。"（《18》第五节 硬约束 7）

    隔离方式（三重，缺一不可）：

    1. **单独命名**：本函数名以 `_doc_level_diagnostic` 结尾，与四个主口径函数不同名，
       不会在"四项指标"的调用路径上被误用；
    2. **返回值带层次标记**：返回 `level: "document"`，且指标键写成
       `recall_at_k_doc_level`（与 chunk 级的 `recall_at_k` 不同名），数值无法被塞进
       chunk 级的同名键里；
    3. **聚合层的硬拦截**：`aggregate_chunk_level` 拒绝 `level != "chunk"` 的行，
       `aggregate_doc_level_diagnostic` 拒绝 `level != "document"` 的行——两级混算在
       聚合层直接抛错，不可能静默发生。

    `final_doc_ids`／`gold_doc_ids` 只接受 **doc_id**（不是 chunk_id）。K 是**每个问题
    最终证据集合的文本块数量上限**；文档级虽按"篇"诊断，仍沿用同一个 K 作为截断上限，
    以保证与 chunk 级对照时口径一致。
    """
    k = _check_k(K)
    gold = set(_as_unique_ordered(gold_doc_ids))
    top = _top_k_ids(final_doc_ids, k)
    if not gold:
        return {"level": "document", "metric": "recall_at_k_doc_level", "K": k,
                "n_gold_docs": 0, "n_final_docs": len(top),
                "recall_at_k_doc_level": 0.0,
                "note": "空 gold：分母为 0，记 0；文档级仅诊断，不得与 chunk 级混算"}
    return {"level": "document", "metric": "recall_at_k_doc_level", "K": k,
            "n_gold_docs": len(gold), "n_final_docs": len(top),
            "recall_at_k_doc_level": _r(len(set(top) & gold) / len(gold)),
            "note": "文档级仅诊断，不得与 chunk 级混算"}


# --------------------------------------------------------------------------
# 三、逐题取值与聚合（chunk 级；聚合层硬拦截混算）
# --------------------------------------------------------------------------
def evaluate_question_chunk_level(final_ids, gold_ids, K, qid=None, **extra):
    """算一题的四个 chunk 级指标，返回一行固定键序的字典（供落盘与聚合）。

    行内带 `level: "chunk"` 标记，并回填 `final_ids`／`gold_ids`（均为去重后的
    规范化 `chunk_id`，`final_ids` 已截断到 K），使这一行的数值可以被**独立重算**——
    这正是《18》第八节 第 18 行"以同一份最终证据集合与 gold 重算，逐题值与平均值
    逐字节一致"所要求的可核验性。

    K 是**每个问题最终证据集合的文本块数量上限**，同时就是四项指标里的 K：本函数把
    `final_ids` 去重后先截断到前 K 个（`top = final[:k]`），**四项指标都只用这前 K 个**算
    （2026-09-28 第二轮复审 B-15 整改：mrr 此前用的是未截断的 `final`，`|final| > K` 时会与
    另外三项自相矛盾）。
    `**extra` 用于透传标签（`task_type`／`gold_hop_depth`／`time_constraint`／`time_window`），
    只供第 10 阶段按子集分组统计，**不参与任何指标计算**。
    """
    k = _check_k(K)
    final = _as_unique_ordered(final_ids)
    gold = _as_unique_ordered(gold_ids)
    top = final[:k]
    hits = len(set(top) & set(gold))
    row = {
        "level": "chunk",
        "qid": qid,
        "K": k,
        "n_final": len(top),
        "n_gold": len(set(gold)),
        "n_hit": hits,
        "final_ids": top,
        "gold_ids": gold,
        "recall_at_k": recall_at_k(final, gold, k),
        "precision_at_k": precision_at_k(final, gold, k),
        # B-15（2026-09-28 整改）：四项指标一律只看**前 K 个**——mrr 此前传的是未截断的
        # `final`，`|final| > K` 且 gold 落在第 K 名之后时会与 recall／precision／CER
        # 自相矛盾（n_hit=0 而 mrr>0）。这里改用 `top = final[:k]`，与其余三项同源。
        "mrr": mrr(top, gold),
        "complete_evidence_recall_at_k": complete_evidence_recall_at_k(final, gold, k),
    }
    for key, value in extra.items():
        row[key] = value
    return row


def aggregate_chunk_level(rows, stat_scope, K=None, extra=None):
    """把逐题 chunk 级行聚合成**一行平均值**（按问题取平均）。

    **混算硬拦截**：任何 `level != "chunk"` 的行一律抛 `ValueError`，
    因此文档级行（`level="document"`）**不可能**进入本平均值。

    平均值行固定包含：`record_type`、`level="chunk"`、`stat_scope`（统计范围）、
    `n_questions`、`n_empty_gold`、`n_empty_final`、`K`，以及四项指标的算术平均。

    "按问题取平均"＝先逐题取值、再对题求算术平均（《02》第12.7节 四项定义里的
    "按问题取平均"）；空 gold／空 final 的题按上面的边界规则记 0 并计入 `n_questions`，
    同时用 `n_empty_gold`／`n_empty_final` 单独计数，使统计范围一眼可见。
    """
    rows = list(rows)
    for r in rows:
        if r.get("level") != "chunk":
            raise ValueError(
                "混算拦截：aggregate_chunk_level 只接受 level=\"chunk\" 的行，收到 level=%r"
                "（文档级只作诊断，必须走 aggregate_doc_level_diagnostic）" % (r.get("level"),))
    n = len(rows)
    avg = {}
    for key in CHUNK_METRIC_KEYS:
        vals = [float(r[key]) for r in rows if r.get(key) is not None]
        avg[key] = _r(sum(vals) / len(vals)) if vals else None
    out = {
        "record_type": "average",
        "level": "chunk",
        "stat_scope": stat_scope,
        "n_questions": n,
        "n_empty_gold": sum(1 for r in rows if int(r.get("n_gold", 0)) == 0),
        "n_empty_final": sum(1 for r in rows if int(r.get("n_final", 0)) == 0),
        "K": _check_k(K) if K is not None else (int(rows[0]["K"]) if rows else None),
        "metric_levels": dict(METRIC_LEVELS),
    }
    out.update(avg)
    if extra:
        out.update(extra)
    return out


def aggregate_doc_level_diagnostic(rows, stat_scope, K=None, extra=None):
    """文档级诊断的**独立**聚合器（返回 `level="document"` 的一行）。

    与 `aggregate_chunk_level` 完全分开：拒绝 `level != "document"` 的行，
    输出键只有 `recall_at_k_doc_level`，**不含**任何 chunk 级指标键——
    两份平均值的键集不相交，从结构上排除"两级混算"。
    """
    rows = list(rows)
    for r in rows:
        if r.get("level") != "document":
            raise ValueError(
                "混算拦截：aggregate_doc_level_diagnostic 只接受 level=\"document\" 的行，"
                "收到 level=%r" % (r.get("level"),))
    n = len(rows)
    vals = [float(r["recall_at_k_doc_level"]) for r in rows if r.get("recall_at_k_doc_level") is not None]
    out = {
        "record_type": "average",
        "level": "document",
        "metric": "recall_at_k_doc_level",
        "stat_scope": stat_scope,
        "n_questions": n,
        "K": _check_k(K) if K is not None else (int(rows[0]["K"]) if rows else None),
        "recall_at_k_doc_level": _r(sum(vals) / len(vals)) if vals else None,
        "note": "文档级仅诊断，不得与 chunk 级混算",
    }
    if extra:
        out.update(extra)
    return out


# --------------------------------------------------------------------------
# 四、题集／trace 读取（只读；缺文件不报错，交调用方决定）
# --------------------------------------------------------------------------
def load_questions(path):
    """读预实验问题集（只读）。返回 `qid -> 题记录` 的有序字典。"""
    questions = {}
    for row in config.iter_jsonl(path):
        questions[row["qid"]] = row
    return questions


def _extract_ids(value):
    """从 trace 的多种可能形态里抽出 chunk_id 列表（容错，不耦合具体 schema）。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        out = []
        for item in value:
            if isinstance(item, dict):
                for key in ("chunk_id", "chunk_ids", "id"):
                    if key in item:
                        sub = item[key]
                        out.extend(sub if isinstance(sub, (list, tuple, set)) else [sub])
                        break
            else:
                out.append(item)
        return out
    return [value]


def load_trace(path):
    """读逐题留痕（T7 的 `per_question_trace.jsonl`），抽出每题的**最终证据集合**。

    字段名做容错匹配（qid：`qid`／`question_id`／`id`；最终集合：
    `final_chunk_ids`／`final_ids`／`final_evidence_chunk_ids`／`final_evidence`／
    `top_k_chunk_ids`／`chunk_ids`），以免与 T7 的具体字段名耦合。

    返回 `(qid -> chunk_id 列表, 未识别记录数)`。本函数**只读**，不写任何东西。
    """
    qid_keys = ("qid", "question_id", "questionId", "id")
    final_keys = ("final_chunk_ids", "final_ids", "final_evidence_chunk_ids",
                  "final_evidence", "final_evidence_ids", "top_k_chunk_ids", "chunk_ids")
    by_qid, unknown = {}, 0
    for row in config.iter_jsonl(path):
        qid = None
        for key in qid_keys:
            if row.get(key) is not None:
                qid = str(row[key])
                break
        ids = None
        for key in final_keys:
            if key in row:
                ids = _extract_ids(row[key])
                break
        if qid is None or ids is None:
            unknown += 1
            continue
        by_qid[qid] = _as_unique_ordered(ids)
    return by_qid, unknown


def _graph_path_candidates(question):
    """【预实验占位口径】取题内 `graph_path[].source_chunk_id` 去重后的图谱侧候选文本块。

    这是**图谱侧候选**（《18》第三节 输入清单：图谱侧候选的唯一入池依据是关系上的
    `source_chunk_id`），**不是**五步契约产出的最终证据集合。仅当 T7 的
    `per_question_trace.jsonl` 尚未落盘时，用它让"计算路径"在 30 道真题上可端到端跑通，
    并在输出里逐行带 `final_ids_source` 标记、在元数据行里写明口径。**不得当作检索效果结论。**
    """
    ids = []
    for step in question.get("graph_path") or []:
        if isinstance(step, dict) and step.get("source_chunk_id") is not None:
            ids.append(step["source_chunk_id"])
    return _as_unique_ordered(ids)


# --------------------------------------------------------------------------
# 五、metrics_pre.jsonl 的构建与落盘
# --------------------------------------------------------------------------
def _meta_record(K, k_source, source_status, final_ids_rule, stat_scope, n_questions,
                 questions_path, gold_review_status=None):
    """输出文件的**第一行元数据记录**：把口径声明写进文件自身，使统计范围一眼可见。"""
    return {
        "gold_review_status": gold_review_status or [],
        "record_type": "metrics_meta",
        "level": "chunk",
        "metric_keys": list(CHUNK_METRIC_KEYS),
        "metric_levels": dict(METRIC_LEVELS),
        "definitions": {
            "recall_at_k": "chunk 级：Top-K 中命中的 gold 证据文本块数 ÷ 该问题 gold 证据文本块总数，按问题取平均（《02》第12.7节）",
            "precision_at_k": "chunk 级：Top-K 中属于 gold 证据的文本块数 ÷ K，按问题取平均；分母恒为 K（《02》第12.7节；硬约束 8）",
            "mrr": "chunk 级：第一个 gold 证据文本块所在排名的倒数，按问题取平均；前 K 内无 gold 证据则该问题记 0（《02》第12.7节）",
            "complete_evidence_recall_at_k": "问题级：该问题的 gold 证据文本块全部出现在 Top-K 中记 1，否则记 0，按问题取平均（《02》第12.7节）",
        },
        "precision_denominator": config.RETRIEVAL["precision_denominator"],   # "K"
        "precision_denominator_rule": "分母恒为 K：实际候选 M < K 时空缺的 K−M 个位置记未命中，分母仍是 K；题目保留、不删（《02》第12.7节 第五步；硬约束 8）",
        "question_level_metrics": ["complete_evidence_recall_at_k"],
        "averaging": "先逐题取值，再对题取算术平均（《02》第12.7节 四项定义里的“按问题取平均”）；空 gold／空 final 的题按定义记 0 并计入 n_questions，另以 n_empty_gold／n_empty_final 单独计数",
        "doc_level_diagnostic": "文档级只作诊断（recall_at_k_doc_level_diagnostic，带 level=\"document\" 标记），本文件不含任何文档级数值，两级绝不混算（《02》第12.7节；硬约束 7）",
        "K_definition": "K 是每个问题最终证据集合的文本块数量上限，同时就是四项指标里的 K（《02》第12.4节）",
        "K": K,
        "k_source": k_source,
        "source_status": source_status,
        "final_ids_rule": final_ids_rule,
        "stat_scope": stat_scope,
        "n_questions": n_questions,
        "gold_source": os.path.relpath(questions_path, config.ROOT).replace("\\", "/"),
        "round_digits": ROUND,
    }


def build_rows(questions, final_by_qid, K, final_ids_source):
    """按 `qid` 升序生成逐题行（固定排序，保证逐字节可复现）。"""
    rows = []
    for qid in sorted(final_by_qid.keys()):
        q = questions.get(qid)
        if q is None:
            continue                    # trace 里的题不在题集里 → 跳过（不臆造标签）
        extra = {key: q.get(key) for key in TAG_KEYS}
        extra["final_ids_source"] = final_ids_source
        row = evaluate_question_chunk_level(
            final_by_qid[qid], q.get("gold_evidence_chunk_ids") or [], K, qid=qid, **extra)
        rows.append(row)
    return rows


def write_metrics_pre(path, rows, meta):
    """落盘：第 1 行元数据 → 逐题行（按 qid 升序）→ 末行平均值。固定键序、固定排序。"""
    ordered = [meta] + rows
    avg = aggregate_chunk_level(
        rows,
        stat_scope=meta["stat_scope"],
        K=meta["K"],
        extra={"record_type": "average", "source_status": meta["source_status"],
               "k_source": meta["k_source"]})
    ordered.append(avg)
    config.write_jsonl(path, ordered)
    return ordered


def resolve_k(args):
    """K 的解析顺序：`--k` → T8 的 `k_selection.json` → `config.RETRIEVAL["K"]` → 占位默认 10。

    占位默认值**只在 T8／T7 尚未落盘时**使用，并在输出里以 `k_source` 显式标注，
    绝不静默兜底；T8 定值后 `--k`／`k_selection.json` 会覆盖它。
    """
    if args.k is not None:
        return _check_k(args.k), "cli:--k"
    sel = config.OUTPUT_FILES["k_selection"]
    if os.path.exists(sel):
        try:
            with open(sel, "r", encoding="utf-8") as f:
                data = json.load(f)
            for scope in (data, data.get("selected") or {}, data.get("K_selection") or {}):
                if isinstance(scope, dict):
                    for key in ("K", "k", "selected_K", "top_k"):
                        if scope.get(key) is not None:
                            return _check_k(scope[key]), "k_selection.json"
        except (ValueError, OSError):
            pass
    cfg_k = config.RETRIEVAL.get("K")
    if cfg_k is not None:
        return _check_k(cfg_k), "config.RETRIEVAL['K']"
    return 10, "placeholder_default_10_pending_T8"


def cmd_write(args) -> int:
    """产出 `检索产出\\metrics_pre.jsonl`（默认动作）。"""
    questions_path = args.questions or config.QUESTION_FILES["questions"]
    if not os.path.exists(questions_path):
        print("[metrics] 失败：题集不存在：%s" % questions_path)
        return 2
    questions = load_questions(questions_path)
    K, k_source = resolve_k(args)

    trace_path = args.from_trace
    explicit_trace = trace_path is not None
    if trace_path is None:
        trace_path = config.OUTPUT_FILES["per_question_trace"]

    if os.path.exists(trace_path):
        final_by_qid, unknown = load_trace(trace_path)
        source_status = "per_question_trace"
        final_ids_source = "per_question_trace.jsonl"
        final_ids_rule = ("逐题最终证据集合取自 T7 留痕 %s（五步契约第 5 步的最终证据集合，不超过 K）"
                          % os.path.relpath(trace_path, config.ROOT).replace("\\", "/"))
        missing = sorted(set(questions) - set(final_by_qid))
        stat_scope = ("预实验问题集全部 %d 题，其中 %d 题在 trace 中有最终证据集合；"
                      "逐题取值后按题算术平均" % (len(questions), len(final_by_qid)))
        if unknown:
            print("[metrics] 提示：trace 中有 %d 条记录未识别出 qid／最终证据集合，已跳过。" % unknown)
        if missing:
            print("[metrics] 提示：以下 %d 题在 trace 中缺失，未产出逐题行（不臆造数值）：%s"
                  % (len(missing), "、".join(missing)))
    elif explicit_trace:
        print("[SKIP] --from-trace 指定的文件不存在：%s" % trace_path)
        print("[SKIP] 按要求『文件缺失时打印提示并跳过』：不因此失败、不写输出、不耦合。")
        return 0
    else:
        # T7 尚未落盘：用题内 graph_path 的图谱侧候选占位，让计算路径可端到端跑通。
        final_by_qid = {qid: _graph_path_candidates(q) for qid, q in questions.items()}
        source_status = "provisional_placeholder_graph_side"
        final_ids_source = "graph_path.source_chunk_id"
        final_ids_rule = ("占位口径：逐题最终证据集合＝题内 graph_path[].source_chunk_id 去重后按原序截断到 K；"
                          "这是**图谱侧候选**，不是五步契约的最终证据集合。T7 的 per_question_trace.jsonl 落盘后，"
                          "用 `--from-trace` 复算即覆盖本文件。**不得作为检索效果结论。**")
        stat_scope = ("预实验问题集全部 %d 题，逐题取值的最终证据集合为占位口径（图谱侧候选）；"
                      "仅用于验证四项指标的计算路径，不构成检索效果结论" % len(questions))

    rows = build_rows(questions, final_by_qid, K, final_ids_source)
    if not rows:
        print("[metrics] 失败：没有任何可统计的题（逐题行为空）。")
        return 2
    gold_review_status = sorted({str(q.get("gold_review_status"))
                                 for q in questions.values() if q.get("gold_review_status")})
    meta = _meta_record(K, k_source, source_status, final_ids_rule,
                        stat_scope, len(rows), questions_path, gold_review_status)
    out_path = args.out or config.OUTPUT_FILES["metrics_pre"]
    write_metrics_pre(out_path, rows, meta)

    print("[metrics] K=%d（来源：%s）  source_status=%s" % (K, k_source, source_status))
    print("[metrics] 逐题行 %d 行 ＋ 元数据 1 行 ＋ 平均值 1 行" % len(rows))
    print("[metrics] 落盘：%s" % os.path.abspath(out_path))
    print("[metrics] sha256：%s" % sha256_file(out_path))
    print("[metrics] 文档级诊断函数（recall_at_k_doc_level_diagnostic）存在但**未**参与本文件；"
          "两级不混算。")
    if source_status.startswith("provisional"):
        print("[metrics] 注意：以上为**占位口径**（%s）；per_question_trace.jsonl 落盘后请用 "
              "--from-trace 复算覆盖。" % source_status)
    return 0


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------
# 六、自证（--selftest）
# --------------------------------------------------------------------------
def cmd_selftest(args) -> int:
    """逐条打印 [OK ]／[FAIL]；全过返回 0，否则 1。"""
    results = []

    def check(name, cond, detail=""):
        results.append(bool(cond))
        print("  [%s] %s%s" % ("OK  " if cond else "FAIL", name,
                               ("   → " + detail) if detail else ""))

    # 1 完全命中（final ⊇ gold）：Recall 与 Complete Evidence Recall 都为 1
    f, g, K = ["c1", "c2", "c3"], ["c1", "c2"], 5
    r1 = recall_at_k(f, g, K)
    c1 = complete_evidence_recall_at_k(f, g, K)
    check("完全命中：Recall@K == 1", r1 == 1.0, "Recall@K=%s" % r1)
    check("完全命中：Complete Evidence Recall@K == 1", c1 == 1.0,
          "Complete Evidence Recall@K=%s" % c1)

    # 2 部分命中：Recall 正确、Complete Evidence Recall 为 0
    f, g, K = ["c1", "x", "y"], ["c1", "c2"], 5
    r2 = recall_at_k(f, g, K)
    c2v = complete_evidence_recall_at_k(f, g, K)
    p2 = precision_at_k(f, g, K)
    check("部分命中：Recall@K == 0.5", r2 == 0.5, "Recall@K=%s" % r2)
    check("部分命中：Complete Evidence Recall@K == 0", c2v == 0.0,
          "Complete Evidence Recall@K=%s" % c2v)
    check("部分命中：Precision@K == 1/5", p2 == 0.2, "Precision@K=%s" % p2)

    # 3 M < K 的分母用例：final 只有 2 条、K=10、命中 1 条 → Precision@K = 0.1（分母是 10 不是 2）
    f, g, K = ["g1", "n1"], ["g1"], 10
    p3 = precision_at_k(f, g, K)
    row3 = evaluate_question_chunk_level(f, g, K, qid="PE-X")
    check("M<K 分母：Precision@K == 0.1（分母是 10 不是 2）", p3 == 0.1,
          "M=%d  K=%d  命中=1  Precision@K=%s" % (len(f), K, p3))
    check("M<K 分母：题被保留（逐题行存在且 n_final < K）",
          row3["n_final"] == 2 and row3["n_final"] < row3["K"] and row3["K"] == 10,
          "n_final=%d  K=%d" % (row3["n_final"], row3["K"]))
    check("M<K 分母：占位位置记未命中（命中数仍是 1，未补足）", row3["n_hit"] == 1,
          "n_hit=%d" % row3["n_hit"])

    # 4 MRR：首个命中排在第 3 位 → 1/3；并在第 1 位 / 无命中处各验一次
    m4 = mrr(["x", "y", "g1", "g2"], ["g1", "g2"])
    m4a = mrr(["g1", "x"], ["g1"])
    m4b = mrr(["x", "y"], ["g1"])
    check("MRR：首个命中在第 3 位 → 1/3", m4 == _r(1.0 / 3), "MRR=%s（1/3=%.8f）" % (m4, 1.0 / 3))
    check("MRR：首个命中在第 1 位 → 1", m4a == 1.0, "MRR=%s" % m4a)
    check("MRR：无命中 → 0", m4b == 0.0, "MRR=%s" % m4b)

    # 5 边界：空 gold 或空 final → 明确返回 0，不抛异常
    try:
        e1 = (recall_at_k(["a"], [], 10), precision_at_k(["a"], [], 10),
              mrr(["a"], []), complete_evidence_recall_at_k(["a"], [], 10))
        e2 = (recall_at_k([], ["a"], 10), precision_at_k([], ["a"], 10),
              mrr([], ["a"]), complete_evidence_recall_at_k([], ["a"], 10))
        e3 = (len(evaluate_question_chunk_level([], [], 10, qid="PE-E")),
              evaluate_question_chunk_level([], [], 10, qid="PE-E")["n_gold"])
        ok_empty = (e1 == (0.0, 0.0, 0.0, 0.0) and e2 == (0.0, 0.0, 0.0, 0.0)
                    and e3[1] == 0)
        check("空 gold／空 final：四项一律返回 0 且不抛异常", ok_empty,
              "空gold=%s  空final=%s" % (e1, e2))
    except Exception as exc:                                     # noqa: BLE001
        check("空 gold／空 final：四项一律返回 0 且不抛异常", False, "抛异常：%r" % exc)

    # 6 集合语义：有序列表 / 集合 / 含重复的列表 三种输入结果一致
    check("集合语义：列表＝集合＝含重复列表（同一 chunk 只算一次）",
          recall_at_k(["a", "a", "b"], ["a"], 5) == recall_at_k({"b", "a"}, {"a"}, 5)
          == recall_at_k(("a", "b"), ["a"], 5) == 1.0,
          "重复命中不重复计数")

    # 7 混算拦截：文档级行不得进入 chunk 级平均值；文档级诊断单独标注
    doc_row = recall_at_k_doc_level_diagnostic(["d1", "d2"], ["d1"], 10)
    blocked = False
    try:
        aggregate_chunk_level([dict(doc_row, level="document")], "x", K=10)
    except ValueError:
        blocked = True
    check("混算拦截：文档级行进入 chunk 级聚合即抛错", blocked,
          "aggregate_chunk_level 拒绝 level=\"document\"")
    check("文档级诊断单独标注：level == \"document\" 且指标键与 chunk 级不同名",
          doc_row["level"] == "document" and "recall_at_k_doc_level" in doc_row
          and "recall_at_k" not in doc_row,
          "keys=%s" % sorted(doc_row.keys()))
    doc_avg = aggregate_doc_level_diagnostic([doc_row], "文档级诊断", K=10)
    check("文档级平均值不含 chunk 级指标键（键集不相交）",
          doc_avg["level"] == "document"
          and not any(k in doc_avg for k in CHUNK_METRIC_KEYS),
          "doc-level keys=%s" % sorted(k for k in doc_avg if k not in
                                       ("record_type", "level", "metric", "stat_scope",
                                        "n_questions", "K", "note")))

    # 8 同一输入两次运行输出 sha256 相同（逐字节一致）
    fixt = os.path.join(config.DOCS_DIR, "_metrics_selftest")
    os.makedirs(fixt, exist_ok=True)
    rows = [evaluate_question_chunk_level(["a", "b"], ["a"], 10, qid="PE-01", task_type="事实型"),
            evaluate_question_chunk_level([], ["z"], 10, qid="PE-02", task_type="关系型")]
    meta = _meta_record(10, "selftest", "selftest", "selftest", "selftest", 2, "selftest")
    p_a = os.path.join(fixt, "a.jsonl")
    p_b = os.path.join(fixt, "b.jsonl")
    write_metrics_pre(p_a, rows, meta)
    write_metrics_pre(p_b, rows, meta)
    h_a, h_b = sha256_file(p_a), sha256_file(p_b)
    check("可重算：同一输入两次运行 sha256 相同", h_a == h_b, "sha256=%s" % h_a[:16])

    # 9 输出里不含时间戳／耗时字段
    with open(p_a, "r", encoding="utf-8") as fh:
        text = fh.read()
    check("输出不含时间戳／耗时字段",
          not any(w in text for w in ("timestamp", "elapsed", "duration", "seconds", "耗时")),
          "无 timestamp／elapsed／duration／耗时")

    # 10 `|final| > K`：四项指标必须都只看前 K 个（B-15 构造用例；旧实现在此处给出
    #    n_hit=0 而 mrr>0 的矛盾读数）
    f_big = ["c%02d" % i for i in range(1, 13)]        # 12 条 > K
    gold_out = ["c11"]                                 # 只落在第 11 名（K 之外）
    gold_in = ["c03"]                                  # 落在第 3 名（K 之内）
    row_big = evaluate_question_chunk_level(f_big, gold_out, 10, qid="PE-B15")
    row_in = evaluate_question_chunk_level(f_big, gold_in, 10, qid="PE-B15B")
    check("|final|>K：前 K 内无 gold 时 mrr == 0（与 n_hit／recall 同源，旧实现是 1/11）",
          row_big["n_final"] == 10 and row_big["n_hit"] == 0 and row_big["mrr"] == 0.0
          and row_big["mrr"] == mrr(f_big[:10], gold_out),
          "n_final=%d  n_hit=%d  mrr=%s  按 final[:K] 重算=%s"
          % (row_big["n_final"], row_big["n_hit"], row_big["mrr"], mrr(f_big[:10], gold_out)))
    check("|final|>K：gold 落在前 K 内时 mrr 仍是首个命中的倒数（1/3）",
          row_in["n_hit"] == 1 and row_in["mrr"] == _r(1.0 / 3),
          "n_hit=%d  mrr=%s" % (row_in["n_hit"], row_in["mrr"]))

    # L-5：自证用的 a.jsonl／b.jsonl 属临时产物，跑完即清，避免在 _工作底稿 里留垃圾。
    shutil.rmtree(fixt, ignore_errors=True)

    ok_all = all(results)
    print("-" * 60)
    print("  自证：%d／%d 通过 → %s" % (sum(results), len(results), "全部通过" if ok_all else "存在失败"))
    return 0 if ok_all else 1


# --------------------------------------------------------------------------
# 七、命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="T10 四项检索指标的计算路径（chunk 级；Precision@K 分母恒为 K）")
    p.add_argument("--k", "--K", dest="k", type=int, default=None,
                   help="K＝每个问题最终证据集合的文本块数量上限；缺省时依次取 k_selection.json、"
                        "config.RETRIEVAL['K']，都没有则用占位默认 10 并在输出里标注 k_source")
    p.add_argument("--questions", default=None,
                   help="题集路径（默认 config.QUESTION_FILES['questions']）")
    p.add_argument("--from-trace", dest="from_trace", default=None,
                   help="T7 的逐题留痕 JSONL；**文件缺失时打印提示并跳过**，不失败、不耦合")
    p.add_argument("--out", default=None,
                   help="输出路径（默认 config.OUTPUT_FILES['metrics_pre']）")
    p.add_argument("--selftest", action="store_true",
                   help="跑九组自证：完全命中／部分命中／M<K 分母／MRR／空边界／集合语义／混算拦截／"
                        "可重算 sha256／无时间戳")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return cmd_selftest(args)
    return cmd_write(args)


if __name__ == "__main__":
    sys.exit(main())
