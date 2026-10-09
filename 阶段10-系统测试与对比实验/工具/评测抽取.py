# -*- coding: utf-8 -*-
"""第 10 阶段 · RQ1 抽取评测（**模型参照集口径**）——四类任务的 P／R／F1 确定性复算。

一条命令重建全部产出（默认无参数）：

    python 阶段10-系统测试与对比实验\\工具\\评测抽取.py

产出（全部覆盖写，落 `阶段10-系统测试与对比实验\\抽取评测\\`）：
    * 抽取评测指标.json
    * 抽取评测报告.md
    * 口径声明.md

性质与硬约束
------------
* **零大模型调用、零联网**：本脚本只读上游落盘产物、只做集合运算，不 import 任何
  会发请求的模块，不读环境变量里的密钥。
* **只读上游**：`阶段05-数据准备\\数据集\\`（含 `抽取评测集\\` 与 `_抽取缓存\\`）、
  `代码\\`、`工具\\` 下既有文件一个字节都不写。
* **确定性**：同一输入两次运行逐字节一致。脚本内不写时间戳、不用随机数、
  不用 `set` 的迭代顺序（一律 `sorted()` 后再落盘）。

口径（作者裁定，2026-10-04《02》v3.9）
--------------------------------------
RQ1 抽取评测的对照物是**模型参照集**：

    主参照集 = 阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\自动标注\\提准\\{dev,test}.auto.repaired.jsonl

它是 `deepseek-flash`（**与抽取器同模型**）自动标注＋离线 lint 规则 v1.2 ＋两轮定向修复
后的产物，另有一次 40 条独立复核（由本项目决策者以模型口径执行、**不构成独立验证**）的 4 处修正。
**它是参照物、不是金标准。** 另设一份异模型对照参照集
（`自动标注\\{dev,test}.auto.jsonl`，`deepseek-v4-pro`、未做 lint 定向修复），
本文只把它作为**对照读数**列出，不作为主口径。

术语纪律：全文一律写「向量索引」或「向量检索组件」；不出现被禁用的四字连写术语。
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import re
import sys
from collections import OrderedDict

# --------------------------------------------------------------------------
# 0. 路径与常量
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

STAGE10 = os.path.join(ROOT, "阶段10-系统测试与对比实验")
OUT_DIR = os.path.join(STAGE10, "抽取评测")
OUT_JSON = os.path.join(OUT_DIR, "抽取评测指标.json")
OUT_MD = os.path.join(OUT_DIR, "抽取评测报告.md")
OUT_CALIBER = os.path.join(OUT_DIR, "口径声明.md")

KG_DIR = os.path.join(ROOT, "代码", "抽取与图谱")
CONFIG_PATH = os.path.join(KG_DIR, "config.py")
COMPARE_PATH = os.path.join(KG_DIR, "auto_annotate_compare.py")

DATASET_ROOT = os.path.join(ROOT, "阶段05-数据准备", "数据集")
EVAL_DIR = os.path.join(DATASET_ROOT, "抽取评测集", "v2.1")
REF_REPAIRED = {"dev": os.path.join(EVAL_DIR, "自动标注", "提准", "dev.auto.repaired.jsonl"),
                "test": os.path.join(EVAL_DIR, "自动标注", "提准", "test.auto.repaired.jsonl")}
REF_PRO = {"dev": os.path.join(EVAL_DIR, "自动标注", "dev.auto.jsonl"),
           "test": os.path.join(EVAL_DIR, "自动标注", "test.auto.jsonl")}

# 系统侧抽取结果：T3（extract.py）全量产物，一行一篇文档；每条事实带 source_chunk_id。
# 该文件正是默认 profile v1.3（`v21_v1_3`）T4～T7 的唯一输入（见 config.GRAPH_PIPELINE
# 的 extract_records_profiles["v21_v1_3"] = "FULL_OUTPUT_FILES" → FULL_OUTPUT_FILES["extracted"]）。
SYS_EXTRACTED = os.path.join(KG_DIR, "_全量", "v2.1_v1_2", "extracted.jsonl")
# 二级定向时间补抽（覆盖层，按 event_id 给 event_time；不含时间戳、逐字节可重放）。
SYS_BACKFILL = os.path.join(KG_DIR, "_全量", "v2.1_v1_2", "event_time_backfill.json")

SPLITS = ["dev", "test"]
SPLIT_TOTAL = "合计"
CLASSES = ["entities", "events", "relations", "times"]
CLASS_CN = {"entities": "实体", "events": "事件", "relations": "关系", "times": "时间"}

WS_RE = re.compile(r"[\s\u3000]+")
SELF_CHECK_PROBES = ["《证券法》", " 立讯 精密\u3000工业股份有限公司 ", "（甲）", "“乙”",
                     "", None, "ＡＢＣ", "abc", "〈丙〉"]
NORM_WS_PROBES = [" a\tb\u3000c ", "中 国", "", None, "全角\u3000空格"]

REBUILD_CMD = "python 阶段10-系统测试与对比实验\\工具\\评测抽取.py"


# --------------------------------------------------------------------------
# 1. 小工具
# --------------------------------------------------------------------------
def read_jsonl(path):
    rows = []
    with io.open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path):
    with io.open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_text(path, text):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def norm_ws(text):
    """与 `工具\\标注结构校验.py` 的 `norm_ws` 同一口径：去掉全部空白（含全角空格）。"""
    return WS_RE.sub("", str(text or ""))


def prf(tp, fp, fn):
    """Precision／Recall／F1；分母为 0 时该指标记 None（落盘为 null，报告里写「—」）。

    F1 只在 P 与 R 都有定义时给出，避免出现「P=0、R=—、F1=0」这类自相矛盾的行。
    """
    p = (tp / float(tp + fp)) if (tp + fp) else None
    r = (tp / float(tp + fn)) if (tp + fn) else None
    if p is None or r is None:
        f1 = None
    else:
        f1 = (2.0 * p * r / (p + r)) if (p + r) > 0 else 0.0
    return p, r, f1


def rnd(v):
    return None if v is None else round(float(v), 6)


def metric_block(tp, fp, fn):
    p, r, f1 = prf(tp, fp, fn)
    return OrderedDict([("tp", int(tp)), ("fp", int(fp)), ("fn", int(fn)),
                        ("support_reference", int(tp + fn)),
                        ("predicted_system", int(tp + fp)),
                        ("precision", rnd(p)), ("recall", rnd(r)), ("f1", rnd(f1))])


def fmt(v, nd=4):
    return "—" if v is None else ("%.*f" % (nd, v))


def md_table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


# --------------------------------------------------------------------------
# 2. 上游模块与本体枚举
# --------------------------------------------------------------------------
if KG_DIR not in sys.path:
    sys.path.insert(0, KG_DIR)

kgcfg = load_module(CONFIG_PATH, "stage10_eval_kgcfg")
# 既有比对脚本：名字规范化与键口径的**唯一来源**（norm_name = normalize_entity_name∘norm_ws）。
compare = load_module(COMPARE_PATH, "stage10_eval_compare")
NAME_FIELDS = compare.NAME_FIELDS
norm_name = compare.norm_name

EVENT_TYPES = list(kgcfg.EVENT_TYPES)
RELATIONS = list(kgcfg.RELATIONS)
ENTITY_TYPES = list(kgcfg.ENTITY_TYPES_FROM_MODEL)
TIME_TYPES = ["event_time", "valid_from", "valid_to"]
# EVIDENCED_BY 是结构性关系：系统侧由程序按 doc_id 生成（不在 relations[] 里），
# 参照集的标注协议也不写它。两侧一致地不计入关系任务的 P／R／F1。
RELATIONS_ANNOTATED = [r for r in RELATIONS if r != "EVIDENCED_BY"]


def self_check_normalization():
    """自检：本脚本的 `norm_ws` 与 `工具\\标注结构校验.py` 的口径逐例一致。"""
    src = compare.handann.norm_ws
    for probe in NORM_WS_PROBES:
        if src(probe) != norm_ws(probe):
            raise AssertionError("norm_ws 与 标注结构校验.py 不一致：%r" % (probe,))
    return "norm_ws 与 工具/标注结构校验.py 逐例一致（%d 例）；名字规范化＝" \
           "config.normalize_entity_name(norm_ws(x))，取自 代码/抽取与图谱/auto_annotate_compare.py" \
           % len(NORM_WS_PROBES)


def entity_name_of(ent):
    """按既有脚本的 NAME_FIELDS 取参照集实体的**身份名**（首个非空字段）。"""
    et = ent.get("entity_type")
    for field in NAME_FIELDS.get(et) or []:
        v = ent.get(field)
        if isinstance(v, str) and v.strip():
            return v
    for v in (ent.get("aliases") or []):
        if isinstance(v, str) and v.strip():
            return v
    return ""


def ref_entity_key(ent):
    """参照集实体键：`entity_type|norm_name(名字)`（与 compare.entity_key 同口径）。"""
    return compare.entity_key(ent, {})


def sys_entity_key(ent):
    return "%s|%s" % (ent.get("type"), norm_name(ent.get("name")))


def event_key_of(event_type, event_name):
    """事件键：`event_type|norm_name(event_name)`（与 compare.event_key 同口径）。"""
    return "%s|%s" % (event_type, norm_name(event_name))


def sys_event_key(ev):
    return event_key_of(ev.get("event_type"), ev.get("event_name"))


def time_key_of(time_type, value):
    return "%s|%s" % (time_type, value)


# --------------------------------------------------------------------------
# 3. 载入三个输入
# --------------------------------------------------------------------------
def load_doc_chunks():
    """doc_id → 该文档的全部 chunk_id（取数据集 v2.1 的 chunks.jsonl，只读）。"""
    path = os.path.join(DATASET_ROOT, "v2.1", "chunks", "chunks.jsonl")
    out = {}
    for rec in read_jsonl(path):
        out.setdefault(int(rec["doc_id"]), []).append(int(rec["chunk_id"]))
    for k in out:
        out[k] = sorted(set(out[k]))
    return out


def load_eval_items(doc_chunks):
    """260 条评测条目：item_id → {split, chunk_id, doc_id, doc_chunk_ids}（只读抽样字段）。

    交付文件 `{dev,test}.jsonl` 是**纯抽样产物**：每条只带抽样字段，**不带任何标注字段**
    （原「260 条交付槽位」连同 `annotation` 字段已按作者决定整体撤销）。《16》第 7.6 节 的
    冻结契约因此由「交付槽位不得由脚本／规则／模型代填」**升级为「交付文件不得夹带任何标签字段」**。
    本函数逐条断言这一状态，任何标签字段的存在即报错退出——本脚本绝不会往交付文件里写东西。
    """
    items = OrderedDict()
    for split in SPLITS:
        for rec in read_jsonl(os.path.join(EVAL_DIR, "%s.jsonl" % split)):
            for banned in ("annotation", "status", "entities", "events", "relations",
                           "times", "ontology_boundary_log"):
                if banned in rec:
                    raise AssertionError("交付文件夹带了标签字段 %s：%s"
                                         % (banned, rec.get("item_id")))
            doc_id = int(rec["doc_id"])
            items[rec["item_id"]] = OrderedDict([
                ("split", split), ("chunk_id", int(rec["chunk_id"])), ("doc_id", doc_id),
                ("doc_chunk_ids", doc_chunks.get(doc_id, [int(rec["chunk_id"])]))])
    if len(items) != 260:
        raise AssertionError("评测条目数不是 260：%d" % len(items))
    return items


def load_reference(paths):
    """参照集：item_id → annotation（只读）。"""
    out = OrderedDict()
    for split in SPLITS:
        for rec in read_jsonl(paths[split]):
            out[rec["item_id"]] = rec
    return out


def load_system():
    """系统侧 T3 产物：doc_id → 记录。"""
    docs = OrderedDict()
    for rec in read_jsonl(SYS_EXTRACTED):
        docs[int(rec["doc_id"])] = rec
    return docs


def load_backfill():
    """二级定向时间补抽覆盖层：event_id → event_time（None 表示仍为空）。"""
    payload = read_json(SYS_BACKFILL)
    out = OrderedDict()
    for row in payload["results"]:
        out[row["event_id"]] = row.get("event_time")
    return payload, out


# --------------------------------------------------------------------------
# 4. 系统侧「逐文本块」事实集合
# --------------------------------------------------------------------------
def build_system_facts(docs):
    """把 T3 产物按 source_chunk_id 摊成「逐文本块」的四类事实集合。

    定位说明（报告第一节）：系统侧**没有**一份独立的「逐块文件」——T3 产物一行一篇文档，
    每条实体／事件／关系带 `source_chunk_id`（由 extract.resolve_quote() 在正文里定位
    quote 得到）。逐块视图＝按该字段筛选。图谱导出物（nodes.csv／edges.csv）在消歧与
    去重之后，块归属已被合并掉，**不用它反推**。
    """
    per_chunk = {}

    def bucket(cid):
        if cid not in per_chunk:
            per_chunk[cid] = {"entities": [], "events": [], "relations": [],
                              "times": [], "events_raw": []}
        return per_chunk[cid]

    for doc_id, rec in docs.items():
        ent_by_id = {}
        for ent in rec.get("entities") or []:
            key = sys_entity_key(ent)
            ent_by_id[ent.get("entity_id")] = key
            bucket(int(ent["source_chunk_id"]))["entities"].append(
                {"key": key, "quote": ent.get("quote") or "", "name": ent.get("name"),
                 "type": ent.get("type")})
        ev_by_id = {}
        for ev in rec.get("events") or []:
            key = sys_event_key(ev)
            ev_by_id[ev.get("event_id")] = key
            b = bucket(int(ev["source_chunk_id"]))
            b["events"].append(
                {"key": key, "quote": ev.get("quote") or "", "event_time": ev.get("event_time"),
                 "event_id": ev.get("event_id"), "event_type": ev.get("event_type"),
                 "event_name": ev.get("event_name")})
            b["events_raw"].append(ev)
            if ev.get("event_time"):
                b["times"].append({"key": time_key_of("event_time", ev["event_time"]),
                                   "quote": "", "value": ev["event_time"],
                                   "time_type": "event_time"})
        for rel in rec.get("relations") or []:
            cid = int(rel["source_chunk_id"])
            end_a = ent_by_id.get(rel.get("head_id")) or ev_by_id.get(rel.get("head_id")) \
                or str(rel.get("head_type") or "")
            end_b = ent_by_id.get(rel.get("tail_id")) or ev_by_id.get(rel.get("tail_id")) \
                or str(rel.get("tail_type") or "")
            # 兼容读数：与 compare.relation_key 同形——**只有实体**能解析成身份键，
            # 非实体端点退回 label 字面量（事件端点即字面量 "Event"）。
            lab_a = ent_by_id.get(rel.get("head_id")) or str(rel.get("head_type") or rel.get("head_id") or "")
            lab_b = ent_by_id.get(rel.get("tail_id")) or str(rel.get("tail_type") or rel.get("tail_id") or "")
            bucket(cid)["relations"].append(
                {"key": "%s|%s|%s" % (rel.get("relation"), end_a, end_b),
                 "key_compat": "%s|%s|%s" % (rel.get("relation"), lab_a, lab_b),
                 "quote": rel.get("quote") or "", "relation": rel.get("relation"),
                 "role": rel.get("role")})
            for ttype, tvalue in (("valid_from", rel.get("valid_from")),
                                  ("valid_to", rel.get("valid_to"))):
                if tvalue:
                    bucket(cid)["times"].append({"key": time_key_of(ttype, tvalue),
                                                 "quote": "", "value": tvalue, "time_type": ttype})
    return per_chunk


def build_reference_facts(ref):
    """参照集逐条事实集合：item_id → 四类键集合（含分类型与 quote 辅助信息）。"""
    per_item = OrderedDict()
    diag = OrderedDict()
    for item_id, rec in ref.items():
        ann = rec.get("annotation") or {}
        ents = [e for e in (ann.get("entities") or []) if isinstance(e, dict)]
        evs = [e for e in (ann.get("events") or []) if isinstance(e, dict)]
        rels = [r for r in (ann.get("relations") or []) if isinstance(r, dict)]
        times = [t for t in (ann.get("times") or []) if isinstance(t, dict)]
        by_ref = {e.get("entity_ref"): e for e in ents if isinstance(e.get("entity_ref"), str)}
        ev_ref = {e.get("event_ref"): e for e in evs if isinstance(e.get("event_ref"), str)}

        def side(prefix):
            """端点解析：先实体、再事件、最后退回 label（比对脚本 relation_key 的同口径扩展）。"""
            ref_ = rel.get(prefix + "_ref")
            if ref_ in by_ref:
                return ref_entity_key(by_ref[ref_]), "entity"
            if ref_ in ev_ref:
                ev = ev_ref[ref_]
                return event_key_of(ev.get("event_type"), ev.get("event_name")), "event"
            return str(rel.get(prefix + "_label") or ref_ or ""), "label"

        rel_rows = []
        for rel in rels:
            a, ka = side("from")
            b, kb = side("to")
            rel_rows.append({
                "key": "%s|%s|%s" % (rel.get("relation"), a, b),
                "key_compat": compare.relation_key(rel, by_ref),
                "key_role": "%s|%s|%s|%s" % (rel.get("relation"), a, b, rel.get("role") or ""),
                "quote": rel.get("quote") or "", "relation": rel.get("relation"),
                "role": rel.get("role"), "endpoint_kinds": (ka, kb)})
        per_item[item_id] = {
            "entities": [{"key": ref_entity_key(e), "quote": e.get("quote") or "",
                          "type": e.get("entity_type"), "name": entity_name_of(e)} for e in ents],
            "events": [{"key": event_key_of(e.get("event_type"), e.get("event_name")),
                        "quote": e.get("quote") or "", "event_time": e.get("event_time"),
                        "event_type": e.get("event_type"), "event_name": e.get("event_name")}
                       for e in evs],
            "relations": rel_rows,
            "times": [{"key": time_key_of(t.get("time_type"), t.get("value")),
                       "key_compat": compare.time_key(t), "quote": t.get("quote") or "",
                       "value": t.get("value"), "time_type": t.get("time_type")} for t in times],
        }
        diag[item_id] = {
            "times_event_time_entries": sum(1 for t in times if t.get("time_type") == "event_time"),
            "events_with_time": sum(1 for e in evs if e.get("event_time")),
            "relations_valid_from_nonempty": sum(1 for r in rels if r.get("valid_from")),
            "relations_valid_to_nonempty": sum(1 for r in rels if r.get("valid_to")),
        }
    return per_item, diag


# --------------------------------------------------------------------------
# 5. 对拍：TP／FP／FN
# --------------------------------------------------------------------------
def key_set(rows, field="key"):
    return set(r[field] for r in rows)


def compare_sets(ref_keys, sys_keys, ref_rows, sys_rows, strict_quote, strict_role):
    """返回 (tp, fp, fn)。strict_quote 时：同名键还必须 quote 互含才算命中。"""
    inter = ref_keys & sys_keys
    if not strict_quote and not strict_role:
        return len(inter), len(sys_keys - ref_keys), len(ref_keys - sys_keys)

    def qmap(rows):
        out = {}
        for r in rows:
            out.setdefault(r["key"], []).append(r.get("quote") or "")
        return out

    rq, sq = qmap(ref_rows), qmap(sys_rows)
    tp = 0
    for k in inter:
        ok = True
        if strict_quote:
            ok = any(quote_overlap(a, b) for a in rq.get(k, []) for b in sq.get(k, []))
        if ok and strict_role:
            r_roles = set(str(x.get("role") or "") for x in ref_rows if x["key"] == k)
            s_roles = set(str(x.get("role") or "") for x in sys_rows if x["key"] == k)
            ok = bool(r_roles & s_roles)
        if ok:
            tp += 1
    return tp, len(sys_keys - ref_keys), len(ref_keys - sys_keys)


def quote_overlap(a, b):
    """严格读数：两段 quote 去空白后互含（任一方是另一方的子串）。"""
    x, y = norm_ws(a), norm_ws(b)
    if not x or not y:
        return False
    return x in y or y in x


def pair_rows(ref_rows, sys_rows, type_field):
    """宽松配对口径（主判据的**上界**）：两遍确定性贪心配对。

    第一遍：键逐字相等（＝主判据的全部命中，`key` 字段）；
    第二遍：对剩下的行，类型字段相等且两侧 quote 去空白后互含即配对。
    返回 (tp, fp, fn)，计数单位是**行**（该口径下不做键去重；本数据集每条目内键本就无重复，
    见 `duplicate_key_diagnostics`，故与主判据可直接比较，且恒有 TP_pair ≥ TP_main）。
    """
    used = [False] * len(sys_rows)
    tp = 0
    for r in ref_rows:
        for j, s in enumerate(sys_rows):
            if used[j] or r.get("key") != s.get("key"):
                continue
            used[j] = True
            tp += 1
            break
    for r in ref_rows:
        if any(used[j] for j, s in enumerate(sys_rows) if s.get("key") == r.get("key")):
            continue
        for j, s in enumerate(sys_rows):
            if used[j]:
                continue
            if r.get(type_field) != s.get(type_field):
                continue
            if not quote_overlap(r.get("quote"), s.get("quote")):
                continue
            used[j] = True
            tp += 1
            break
    matched_sys = sum(1 for u in used if u)
    return tp, len(sys_rows) - matched_sys, len(ref_rows) - tp


def accumulate(store, split, cls, variant, tp, fp, fn):
    for key in ((split, cls, variant), (SPLIT_TOTAL, cls, variant)):
        cell = store.setdefault(key, {"tp": 0, "fp": 0, "fn": 0})
        cell["tp"] += tp
        cell["fp"] += fp
        cell["fn"] += fn


def accumulate_type(store, split, cls, variant, bucket_by_type):
    for tname, (tp, fp, fn) in bucket_by_type.items():
        for key in ((split, cls, variant, tname), (SPLIT_TOTAL, cls, variant, tname)):
            cell = store.setdefault(key, {"tp": 0, "fp": 0, "fn": 0})
            cell["tp"] += tp
            cell["fp"] += fp
            cell["fn"] += fn


def type_of_key(cls, key):
    return key.split("|", 1)[0]


def bucket_by_type(cls, tp_keys, fp_keys, fn_keys):
    out = {}
    for sign, keys in (("tp", tp_keys), ("fp", fp_keys), ("fn", fn_keys)):
        for k in keys:
            t = type_of_key(cls, k)
            cell = out.setdefault(t, [0, 0, 0])
            cell[{"tp": 0, "fp": 1, "fn": 2}[sign]] += 1
    return dict((t, tuple(v)) for t, v in out.items())


# --------------------------------------------------------------------------
# 6. 主计算
# --------------------------------------------------------------------------
def run(items, ref_facts, sys_chunks, backfill_map):
    totals = {}     # (split, cls, variant) → {tp,fp,fn}
    by_type = {}    # (split, cls, variant, type) → {tp,fp,fn}
    variant_notes = OrderedDict([
        ("main", "主判据：键＝类型＋规范化名字（关系为「关系名|两端身份」，端点为实体/事件身份）；quote 与 role 不参与"),
        ("quote_pair", "宽松配对（**主判据的上界**）：先按键逐字配对，剩下的行再按「类型字段相等且两侧 quote 去空白后互含」贪心配对"),
        ("strict_quote", "严格读数：在命中键上再要求两侧 quote 去空白后互含"),
        ("strict_quote_role", "严格读数：再叠加 role 一致（仅关系类有该字段）"),
        ("compat", "兼容读数：键形状与既有 auto_annotate_compare.key_sets 完全同形（关系端点不解到事件身份、时间键只用 value）"),
    ])
    VARIANTS = list(variant_notes.keys())

    chunk_uncovered = OrderedDict()
    for split in SPLITS:
        chunk_uncovered[split] = {"items": 0, "items_with_reference_facts": 0,
                                  "reference_facts_on_uncovered": 0}
    duplicate_diag = dict((c, {"reference_multi": 0, "reference_uniq": 0,
                               "system_multi": 0, "system_uniq": 0}) for c in CLASSES)

    for item_id, meta in items.items():
        split, cid = meta["split"], meta["chunk_id"]
        rf = ref_facts[item_id]
        sf = sys_chunks.get(cid) or {"entities": [], "events": [], "relations": [], "times": []}

        for cls in CLASSES:
            rrows, srows = rf[cls], sf[cls]
            rk, sk = key_set(rrows), key_set(srows)
            duplicate_diag[cls]["reference_multi"] += len(rrows)
            duplicate_diag[cls]["reference_uniq"] += len(rk)
            duplicate_diag[cls]["system_multi"] += len(srows)
            duplicate_diag[cls]["system_uniq"] += len(sk)

            # 主判据
            tp, fp, fn = compare_sets(rk, sk, rrows, srows, False, False)
            accumulate(totals, split, cls, "main", tp, fp, fn)
            accumulate_type(by_type, split, cls, "main",
                            bucket_by_type(cls, rk & sk, sk - rk, rk - sk))
            # 严格读数（quote）
            if cls in ("entities", "events", "relations"):
                tp2, _, _ = compare_sets(rk, sk, rrows, srows, True, False)
                accumulate(totals, split, cls, "strict_quote", tp2, fp, fn)
                if cls == "relations":
                    tp3, _, _ = compare_sets(rk, sk, rrows, srows, True, True)
                    accumulate(totals, split, cls, "strict_quote_role", tp3, fp, fn)
                tp5, fp5, fn5 = pair_rows(
                    rrows, srows, {"entities": "type", "events": "event_type",
                                   "relations": "relation"}[cls])
                accumulate(totals, split, cls, "quote_pair", tp5, fp5, fn5)
            else:
                accumulate(totals, split, cls, "quote_pair", tp, fp, fn)
            # 兼容读数（与既有脚本同形）
            if cls == "relations":
                rk2 = key_set(rrows, "key_compat")
                sk2 = key_set(srows, "key_compat")
                tp4, fp4, fn4 = compare_sets(rk2, sk2, [], [], False, False)
                accumulate(totals, split, cls, "compat", tp4, fp4, fn4)
            elif cls == "times":
                rk2 = key_set(rrows, "key_compat")
                sk2 = set(r["value"] for r in srows)
                tp4, fp4, fn4 = compare_sets(rk2, sk2, [], [], False, False)
                accumulate(totals, split, cls, "compat", tp4, fp4, fn4)
            else:
                accumulate(totals, split, cls, "compat", tp, fp, fn)

        if cid not in sys_chunks:
            d = chunk_uncovered[split]
            d["items"] += 1
            n = sum(len(rf[c]) for c in CLASSES)
            if n:
                d["items_with_reference_facts"] += 1
                d["reference_facts_on_uncovered"] += n

    metrics = OrderedDict()
    for split in SPLITS + [SPLIT_TOTAL]:
        per_class = OrderedDict()
        for cls in CLASSES:
            per_variant = OrderedDict()
            for v in VARIANTS:
                cell = totals.get((split, cls, v))
                if cell is None:
                    continue
                per_variant[v] = metric_block(cell["tp"], cell["fp"], cell["fn"])
            per_class[cls] = per_variant
        metrics[split] = per_class

    type_metrics = OrderedDict()
    for split in SPLITS + [SPLIT_TOTAL]:
        per_class = OrderedDict()
        for cls in CLASSES:
            universe = {"events": EVENT_TYPES, "relations": RELATIONS,
                        "entities": ENTITY_TYPES, "times": TIME_TYPES}[cls]
            rows = OrderedDict()
            for tname in universe:
                cell = by_type.get((split, cls, "main", tname))
                if cell is None:
                    rows[tname] = metric_block(0, 0, 0)
                else:
                    rows[tname] = metric_block(cell["tp"], cell["fp"], cell["fn"])
            per_class[cls] = rows
        type_metrics[split] = per_class
    # 参照集/系统里出现过、但不在本体枚举内的类型也要落盘（不静默丢）
    for split in SPLITS + [SPLIT_TOTAL]:
        for cls in CLASSES:
            extra = sorted(t for (sp, c, v, t) in by_type if sp == split and c == cls and v == "main"
                           and t not in type_metrics[split][cls])
            if extra:
                for tname in extra:
                    cell = by_type[(split, cls, "main", tname)]
                    type_metrics[split][cls][tname] = metric_block(cell["tp"], cell["fp"], cell["fn"])

    # ---- 「块外命中」读数：把「没抽到」与「抽到了但没落在这一块」分开 ----
    # 注意：评测集每篇文档只抽 1 块（260 条 = 260 篇文档），因此「按文档合并后对拍」是恒等变换，
    # 没有信息量；有信息量的是「同一篇文档的**其它块**里有没有同一条事实」。
    TYPE_FIELD = {"entities": "type", "events": "event_type", "relations": "relation",
                  "times": None}
    doc_scope = {}
    for item_id, meta in items.items():
        split, doc_id = meta["split"], meta["doc_id"]
        rf = ref_facts[item_id]
        sys_block = sys_chunks.get(meta["chunk_id"]) or {}
        sys_doc = {}
        for cls in CLASSES:
            rows = []
            for cid in meta["doc_chunk_ids"]:
                rows.extend((sys_chunks.get(cid) or {}).get(cls) or [])
            sys_doc[cls] = rows
        for cls in CLASSES:
            rrows = rf[cls]
            brows = sys_block.get(cls) or []
            drows = sys_doc[cls]
            rk = key_set(rrows)
            bk = key_set(brows)
            dk = key_set(drows)
            tf = TYPE_FIELD[cls]
            b_pair = pair_rows(rrows, brows, tf)[0] if (tf and rrows and brows) else len(rk & bk)
            d_pair = pair_rows(rrows, drows, tf)[0] if (tf and rrows and drows) else len(rk & dk)
            for key in ((split, cls), (SPLIT_TOTAL, cls)):
                cell = doc_scope.setdefault(key, {
                    "reference": 0, "block_key_tp": 0, "doc_key_tp": 0,
                    "block_pair_tp": 0, "doc_pair_tp": 0,
                    "system_block": 0, "block_fp": 0, "block_fp_same_key_elsewhere_in_doc": 0,
                    "system_doc": 0})
                cell["reference"] += len(rk)
                cell["block_key_tp"] += len(rk & bk)
                cell["doc_key_tp"] += len(rk & dk)
                cell["block_pair_tp"] += b_pair
                cell["doc_pair_tp"] += d_pair
                cell["system_block"] += len(brows)
                cell["block_fp"] += len(bk - rk)
                cell["block_fp_same_key_elsewhere_in_doc"] += len((bk - rk) & (dk - bk))
                cell["system_doc"] += len(drows)
    doc_scope_metrics = OrderedDict()
    for split in SPLITS + [SPLIT_TOTAL]:
        per_class = OrderedDict()
        for cls in CLASSES:
            cell = doc_scope.get((split, cls), {})
            ref_n = cell.get("reference", 0)

            def rt(num):
                return rnd(num / float(ref_n)) if ref_n else None
            per_class[cls] = OrderedDict([
                ("reference_support", ref_n),
                ("block_key_tp", cell.get("block_key_tp", 0)),
                ("block_key_recall", rt(cell.get("block_key_tp", 0))),
                ("doc_key_tp", cell.get("doc_key_tp", 0)),
                ("doc_key_recall", rt(cell.get("doc_key_tp", 0))),
                ("block_pair_tp", cell.get("block_pair_tp", 0)),
                ("block_pair_recall", rt(cell.get("block_pair_tp", 0))),
                ("doc_pair_tp", cell.get("doc_pair_tp", 0)),
                ("doc_pair_recall", rt(cell.get("doc_pair_tp", 0))),
                ("missing_even_at_doc_scope", ref_n - cell.get("doc_pair_tp", 0)),
                ("system_block_facts", cell.get("system_block", 0)),
                ("system_doc_facts", cell.get("system_doc", 0)),
                ("system_block_fp", cell.get("block_fp", 0)),
                ("block_fp_same_key_elsewhere_in_doc",
                 cell.get("block_fp_same_key_elsewhere_in_doc", 0)),
            ])
        doc_scope_metrics[split] = per_class

    # ---- event_time 非空率（同一 260 条范围内两侧对照）----
    time_rate = OrderedDict()
    for split in SPLITS + [SPLIT_TOTAL]:
        r_n = r_hit = s_n = s_hit = s2_hit = 0
        for item_id, meta in items.items():
            if split != SPLIT_TOTAL and meta["split"] != split:
                continue
            for ev in ref_facts[item_id]["events"]:
                r_n += 1
                if ev.get("event_time"):
                    r_hit += 1
            for ev in (sys_chunks.get(meta["chunk_id"], {}).get("events") or []):
                s_n += 1
                if ev.get("event_time"):
                    s_hit += 1
                if ev.get("event_time") or backfill_map.get(ev.get("event_id")):
                    s2_hit += 1
        def rate(a, b):
            return rnd(a / float(b)) if b else None
        time_rate[split] = OrderedDict([
            ("reference_events", r_n), ("reference_events_with_time", r_hit),
            ("reference_nonempty_rate", rate(r_hit, r_n)),
            ("system_events", s_n), ("system_events_with_time", s_hit),
            ("system_nonempty_rate", rate(s_hit, s_n)),
            ("system_events_with_time_after_backfill", s2_hit),
            ("system_nonempty_rate_after_backfill", rate(s2_hit, s_n)),
        ])

    return OrderedDict([
        ("variant_notes", variant_notes),
        ("metrics", metrics),
        ("type_metrics", type_metrics),
        ("doc_scope_metrics", doc_scope_metrics),
        ("event_time_nonempty_rate", time_rate),
        ("duplicate_key_diagnostics", duplicate_diag),
        ("uncovered_chunks", chunk_uncovered),
    ])


# --------------------------------------------------------------------------
# 7. 报告生成
# --------------------------------------------------------------------------
def format_class_table(res, cls, variant="main"):
    rows = []
    for split in SPLITS + [SPLIT_TOTAL]:
        m = res["metrics"][split][cls][variant]
        q = res["metrics"][split][cls].get("quote_pair")
        rows.append([split, m["tp"], m["fp"], m["fn"], m["support_reference"],
                     m["predicted_system"], fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"]),
                     ("%s／%s／%s" % (fmt(q["precision"]), fmt(q["recall"]), fmt(q["f1"])))
                     if q else "—"])
    return md_table(["分段", "TP", "FP", "FN", "参照集条数", "系统条数",
                     "Precision", "Recall", "F1", "宽松配对 P／R／F1"], rows)


def format_type_table(res, cls, universe):
    rows = []
    for tname in universe:
        cells = []
        for split in SPLITS + [SPLIT_TOTAL]:
            m = res["type_metrics"][split][cls].get(tname) or metric_block(0, 0, 0)
            cells.append((m, split))
        line = [tname]
        for m, split in cells:
            line += [m["support_reference"], m["tp"], m["fp"], m["fn"],
                     fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"])]
        rows.append(line)
    headers = ["类型"]
    for split in SPLITS + [SPLIT_TOTAL]:
        headers += ["%s·支持" % split, "%s·TP" % split, "%s·FP" % split, "%s·FN" % split,
                    "%s·P" % split, "%s·R" % split, "%s·F1" % split]
    return md_table(headers, rows)


def build_report(res, meta):
    L = []
    add = L.append
    add("# 抽取评测报告（模型参照集口径）")
    add("")
    add("> **口径声明（每份产出都带）**：本报告的全部读数都是「**模型参照集口径下的抽取表现**」。")
    add("> 对照物（参照集）＝ `阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\自动标注\\提准\\{dev,test}.auto.repaired.jsonl`，")
    add("> 由 `deepseek-flash`（**与抽取器同模型**）自动标注 ＋ 离线 lint 规则 v1.2 ＋ 两轮定向修复生成，")
    add("> 另有一次 40 条独立复核（由本项目决策者以模型口径执行、**不构成独立验证**）的 4 处修正。")
    add("> **它是参照物、不是金标准**；参照集与抽取器同端点、同模型家族，")
    add("> 两者之间的一致**不构成独立验证**，同源自证风险被降低但没有消除。")
    add("> 因此本报告的 P／R／F1 **不得**读作「准确率」，也不得写成任何以金标准／标准答案为对照物的表述。")
    add("")
    add("| 项 | 值 |")
    add("| --- | --- |")
    add("| 重建命令 | `%s` |" % REBUILD_CMD)
    add("| 参照集（主口径） | `自动标注\\提准\\{dev,test}.auto.repaired.jsonl`（Dev 60 ＋ Test 200 ＝ 260） |")
    add("| 参照集（异模型对照，仅第九节） | `自动标注\\{dev,test}.auto.jsonl`（`deepseek-v4-pro`、未做 lint 定向修复） |")
    add("| 系统侧（抽取结果） | `%s` |" % os.path.relpath(SYS_EXTRACTED, ROOT).replace("\\", "/"))
    add("| 系统侧（时间二次补抽覆盖层） | `%s` |" % os.path.relpath(SYS_BACKFILL, ROOT).replace("\\", "/"))
    add("| 评测条目 | Dev 60 ＋ Test 200 ＝ 260，单位＝文本块（`chunk_id`），Dev／Test 块不重叠 |")
    add("| 本体枚举 | 实体 %d 类、事件 %d 类、关系 %d 条（含结构性 `EVIDENCED_BY`：%d 条计入对拍）、时间 %d 类 |"
        % (len(ENTITY_TYPES), len(EVENT_TYPES), len(RELATIONS), len(RELATIONS_ANNOTATED), len(TIME_TYPES)))
    add("| 模型调用 | **0 次**（纯计算，零联网） |")
    add("")
    add("**术语纪律**：本报告讨论的是抽取与图谱侧，不涉及向量检索；如下游引用需提及该组件，")
    add("一律写「向量索引」或「向量检索组件」，不使用被禁用的四字连写术语。")
    add("")
    add("---")
    add("")

    # ---- 1 ----
    add("## 一、系统侧抽取结果的定位与口径")
    add("")
    add("### 1.1 结论：逐文本块视图来自 T3 产物，不是一份独立的「逐块文件」")
    add("")
    add("| 层 | 落点 | 粒度 | 是否本次使用 |")
    add("| --- | --- | --- | --- |")
    add("| 原始返回缓存 | `阶段05-数据准备\\数据集\\_抽取缓存\\v2.1_v1_2\\<doc_id>.json`（709 篇） | **一篇文档一条**，只存模型原始返回文本，**不按块** | 仅用于核对模型与 Prompt 版本 |")
    add("| T3 解析产物 | `代码\\抽取与图谱\\_全量\\v2.1_v1_2\\extracted.jsonl`（709 行） | **一行一篇文档**，但每条实体／事件／关系都带 `source_chunk_id` | **是**（逐块视图＝按该字段筛选） |")
    add("| T4／T5 中间物 | `_抽取缓存\\v2.1_v1_2\\图谱管线\\`（消歧／去重） | 实体级／事件级，块归属已在合并中被吸收 | 否 |")
    add("| T6 图谱导出 | `阶段06-事件抽取与知识图谱\\图谱导出\\v2.1_v1_3\\{nodes,edges}.csv` | 节点／边级，消歧去重之后 | 否（见 1.3） |")
    add("")
    add("### 1.2 为什么是 `_全量\\v2.1_v1_2\\extracted.jsonl`")
    add("")
    add("* 它是 `代码\\抽取与图谱\\config.py` 第 8 节的 `FULL_OUTPUT_FILES[\"extracted\"]`；")
    add("  默认 profile `v21_v1_3` 的 `GRAPH_PIPELINE[\"extract_records_profiles\"]` 指向 `FULL_OUTPUT_FILES`，")
    add("  即 **v1.3 复用 v1.2 的抽取结果、不重跑抽取**（v1.3 只改消歧与入图策略）。")
    add("  故 **v1.2 与 v1.3 在「抽取」这一层是同一份**，本次评测的对照对象就是它；")
    add("  v1.1（归档）另有一份 `_全量\\v2.1\\extracted.jsonl`（提示词不含 8 类事件定义，与 v1.2 不是同一批返回），")
    add("  **本次不使用**——口径是「默认 profile 的抽取结果」。")
    add("* 逐块归属的实现口径（`extract.py`）：`SYSTEM_PROMPT` 要求每条事实给出**正文逐字 quote**；")
    add("  `resolve_quote()` 在本文档的文本块序列里找哪个块的正文包含该 quote，命中多块时**取 `chunk_index` 最小的一块**；")
    add("  跨块边界（在整篇正文里有、但没有单块完整包含）判 `quote_spans_chunk_boundary` 并**丢弃该条**；")
    add("  正文里根本没有的 quote 判 `quote_not_in_document` 并丢弃。")
    add("* 因此：**系统侧的 source_chunk_id 是「quote 落在哪一块」的函数**，而参照集的 `chunk_id` 是")
    add("  「标注时的对象块」。两者在跨块边界处会出现归属位差——这一条写进第六节限制，并在第七节量化。")
    add("")
    add("### 1.3 为什么不用 `nodes.csv`／`edges.csv` 反推")
    add("")
    add("* `edges.csv` 确有一列 `source_chunk_id`，但它是**消歧 ＋ 事件去重之后**的边：")
    add("  实体提及已被归并成公司节点（105 家配置公司集 ＋ 注册全称别名表）、同一事件的多篇证据被合并，")
    add("  块归属只剩「合并后保留的那一条」，无法还原「某一块的抽取结果」。")
    add("* 本次评测要回答的是 **抽取环节**的表现（RQ1），不是消歧／去重之后的表现；")
    add("  用导出物反推会把消歧与去重的损益混进 P／R／F1，口径不清。故**明确不用**。")
    add("")
    add("### 1.4 时间任务的系统侧取值口径（反推）")
    add("")
    add("* 系统侧 `extracted.jsonl` **没有** `times[]` 槽位——时间只出现在两处：")
    add("  `events[].event_time`（ISO 日期或 `null`）与 `relations[].valid_from`／`valid_to`（只有 `BELONGS_TO` 填）。")
    add("* 参照集的 `times[]` 恰是这三者的并集（lint 规则 `R6_times_event_mirror` 即要求事件时间与 `times[]` 互相镜像）。")
    add("* 故系统侧时间集合＝由产物反推：`event.event_time` → `time_type=event_time`；")
    add("  `relation.valid_from/valid_to` → `time_type=valid_from/valid_to`，块归属沿用该事件／关系的 `source_chunk_id`。")
    add("* **局限（写进第六节）**：参照集里 `valid_from`／`valid_to` 有 %d 项，而参照集的 `relations[]` 里"
        % sum(res["type_metrics"][SPLIT_TOTAL]["times"].get(t, metric_block(0, 0, 0))["support_reference"]
              for t in ("valid_from", "valid_to")))
    add("  `valid_from`／`valid_to` 非空的条数为 0——即参照集的这两类时间**不挂在关系上**，")
    add("  系统侧却只能从关系上取，这是两侧的结构性不对称。")
    add("")

    # ---- 2 ----
    add("## 二、匹配判据（TP／FP／FN 逐类定义）")
    add("")
    add("**同一把尺子**：名字规范化与既有脚本逐字一致——`norm_name(x) = config.normalize_entity_name(norm_ws(x))`，")
    add("其中 `norm_ws` 取自 `工具\\标注结构校验.py`（去全部空白，含全角空格），")
    add("`normalize_entity_name` 取自 `代码\\抽取与图谱\\config.py`（去空白后再剥最外层包裹字符 `《》〈〉<>【】〔〕“”‘’\"\"（）()`，")
    add("**不做大小写折叠、不做宽度折叠、不做简繁折叠、不做模糊匹配**）。本脚本直接 import 这两个模块取值，不复刻、不另立一套。")
    add("")
    add("**计数单位**：先把每一块的键做**去重集合**（同一块内同名同类型只计一次），再算集合交并。")
    add("聚合口径＝**micro**（把各块的 TP／FP／FN 直接相加后再算 P／R／F1）。")
    dup = res["duplicate_key_diagnostics"]
    add("实测去重效果：实体 %d→%d、事件 %d→%d、关系 %d→%d、时间 %d→%d，"
        % (dup["entities"]["reference_multi"], dup["entities"]["reference_uniq"],
           dup["events"]["reference_multi"], dup["events"]["reference_uniq"],
           dup["relations"]["reference_multi"], dup["relations"]["reference_uniq"],
           dup["times"]["reference_multi"], dup["times"]["reference_uniq"]))
    add("即参照集在同一个块内基本没有重复条目，**只有时间类有 %d 条重复被折叠**"
        % (dup["times"]["reference_multi"] - dup["times"]["reference_uniq"]))
    add("（同一块里 `time_type|value` 完全相同），其余三类去重是恒等变换。系统侧四类均无块内重复。")
    add("")
    add("| 任务 | 键（主判据） | 参照集侧取值 | 系统侧取值 | quote 是否参与 |")
    add("| --- | --- | --- | --- | --- |")
    add("| 实体 | `entity_type` + `norm_name(名字)` | 按 `NAME_FIELDS` 取首个非空身份名（Company→`company_name`→`short_name`→`aliases`；Person→`person_name`；Institution→`institution_name`；Policy→`policy_name`；Industry→`industry_name`） | `type` + `name` | **不参与** |")
    add("| 事件 | `event_type` + `norm_name(event_name)` | `event_type` ＋ `event_name` | `event_type` ＋ `event_name` | **不参与** |")
    add("| 关系 | `relation` + 端1 + 端2 | 端点先按 `from_ref`／`to_ref` 解析到本条的实体身份（→ 实体键）或事件身份（→ 事件键），解析不到再退回 `*_label` | 端点先按 `head_id`／`tail_id` 解析到同一文档记录的实体身份或事件身份，解析不到再退回 `*_type` | **不参与** |")
    add("| 时间 | `time_type` + `value` | `times[].time_type` ＋ `times[].value` | 由 `events[].event_time`／`relations[].valid_from,valid_to` 反推 | **不参与**（系统侧时间无独立 quote） |")
    add("")
    add("**按块计数**：TP ＝ 该块「参照集键 ∩ 系统键」的大小；FP ＝ 「系统键 − 参照集键」；FN ＝ 「参照集键 − 系统键」。")
    add("**`EVIDENCED_BY` 不计入**：它是结构性关系（系统侧由 `write_graph.py` 按 `doc_id` 生成，不在 `relations[]` 里；")
    add("参照集标注协议也不写它），两侧一致地排除，故关系任务的分母是其余 %d 条关系。" % len(RELATIONS_ANNOTATED))
    add("")
    add("**敏感性判据（第八节给读数）**：")
    add("* `strict_quote`：在命中键上再要求两侧 `quote` **去空白后互含**（任一方是另一方的子串）；")
    add("* `strict_quote_role`：再叠加 `role` 一致（只有 `PARTICIPATES_IN` 等带 role 的关系有此字段）；")
    add("* `compat`：键形状与既有 `代码\\抽取与图谱\\auto_annotate_compare.py` 的 `key_sets()` **完全同形**")
    add("  （关系端点解析不到实体时退回 `*_label`，事件端点落为字面量 `Event`；时间键只用 `value`）——")
    add("  用它可以与第 6 阶段既有的「两版对照」读数对齐。")
    add("")

    # ---- 3 ----
    add("## 三、四类指标（主判据，模型参照集口径）")
    add("")
    for cls in CLASSES:
        add("### 3.%d %s" % (CLASSES.index(cls) + 1, CLASS_CN[cls]))
        add("")
        add(format_class_table(res, cls, "main"))
        add("")
    add("**读法（重要）**：")
    add("")
    add("* `Precision／Recall／F1` 三列是**主判据**（键＝类型＋规范化名字，逐字相等才算命中）。")
    add("  它是**严格的字符串口径**：事件名、关系端点身份都是自由文本，两个不同的模型对同一件事几乎不会写出")
    add("  完全相同的字符串，因此事件与关系的读数**天然偏低**，这是判据的性质，不是「抽取几乎全错」。")
    add("* `宽松配对 P／R／F1` 一列是**主判据的上界**：先按主判据的键配一遍，剩下的行再按")
    add("  「类型字段一致且两侧证据 `quote` 去空白后互含」贪心配对（不看名字字符串），")
    add("  度量的是「同一个证据段上是否抽出了同类型的事实」。两个口径**都要报**，且**不得**只报宽松的那个。")
    add("* Dev 与 Test 用同一把尺子、同一份参照集；Test 200 是在参照集与抽取链规则冻结后产出的独立评测段，")
    add("  Dev 60 用于说明调优过程。合计 260 为两段直接相加的 micro 读数。")
    add("")

    # ---- 4 ----
    add("## 四、分类型读数（主判据）")
    add("")
    add("### 4.1 八类事件")
    add("")
    add(format_type_table(res, "events", EVENT_TYPES))
    add("")
    add("### 4.2 九条关系")
    add("")
    add(format_type_table(res, "relations", RELATIONS))
    add("")
    add("`EVIDENCED_BY` 行的三个分段恒为 0／0／0，即**结构性关系、两侧都不计入对拍**（见第二节口径）。")
    add("")
    add("### 4.3 五类实体（附带，便于核对本体覆盖面）")
    add("")
    add(format_type_table(res, "entities", ENTITY_TYPES))
    add("")
    add("### 4.4 三类时间")
    add("")
    add(format_type_table(res, "times", TIME_TYPES))
    add("")

    # ---- 5 ----
    add("## 五、`event_time` 非空率对照")
    add("")
    add("范围＝本次 260 条评测块内、**归属到这些块**的事件；**两侧分母各自是自己的事件数**")
    add("（系统事件数与参照集事件数不是同一批对象，故这一节只做非空率对照）。")
    add("")
    tr_rows = []
    for split in SPLITS + [SPLIT_TOTAL]:
        r = res["event_time_nonempty_rate"][split]
        tr_rows.append([split, "%d／%d" % (r["reference_events_with_time"], r["reference_events"]),
                        fmt(r["reference_nonempty_rate"]),
                        "%d／%d" % (r["system_events_with_time"], r["system_events"]),
                        fmt(r["system_nonempty_rate"]),
                        "%d／%d" % (r["system_events_with_time_after_backfill"], r["system_events"]),
                        fmt(r["system_nonempty_rate_after_backfill"])])
    add(md_table(["分段", "参照集 非空／总数", "参照集 非空率", "系统（T3）非空／总数", "系统（T3）非空率",
                  "系统（T3＋二次补抽）非空／总数", "系统（T3＋二次补抽）非空率"], tr_rows))
    add("")
    add("口径注：")
    add("* 参照集的 `event_time` 是标注时写进 `events[].event_time` 的取值；系统侧第一列是 T3 的 `event_time`")
    add("  （固定口径「正文不能确定到日就写 null，绝不猜测」），第二列叠加 `event_time_backfill.json` 的二级定向补抽覆盖层。")
    add("* 两侧的**分母不同**（系统事件数与参照集事件数不是同一批对象），所以这一节只做**非空率对照**，")
    add("  不做事件级配对检验。")
    add("* 已知数据瑕疵（如实报）：参照集 `times[]` 里 `time_type=event_time` 的条目数与 `events[]` 里 `event_time` 非空的条数**不完全相等**")
    add("  （合计 %d vs %d）——lint 规则 `R6` 已从「必须一一镜像」收窄为两种情形，故少量差额属已知状态，不是本次评测引入的。"
        % (meta["ref_times_event_time_entries"], meta["ref_events_with_time"]))
    add("")

    # ---- 6 ----
    add("## 六、已知限制（必须与读数一起引用）")
    add("")
    add("1. **参照集是模型产物，是参照物、不是金标准。** 主参照集由 `deepseek-flash` 自动标注")
    add("   ＋ lint 定向修复生成；`deepseek-flash` **与抽取器同模型**，两者对「什么算一条事实」「字段怎么填」")
    add("   的偏好可能同向，因此本报告的高读数**有同源自证成分**，一致**不构成独立验证**。")
    add("2. **偏倚方向（承第 7 阶段已登记口径）：参照集比多模型共识更紧、以漏标为主，")
    add("   因此抽取的 Precision 与 Recall 都被低估。** 这不是本次评测新引入的判断，而是既有登记口径的复述。")
    add("3. **条目级完全一致率不能当准确率读。** 三条第三方盲标线对同一批 40 条抽检样本的条目级完全一致率只有")
    add("   12.5%～30.0%（《16》第 8.10 节），差异主要来自**收录门槛与粒度**，不是类型判断分歧；")
    add("   可复现的是**分层指标**（实体类型一致率、事件类型分布 TVD、按类计数）。本报告因此把读数拆到**分类型**。")
    add("4. **归属位差，以及「块 vs 文档」的结构差**：系统侧的块归属是「quote 落在哪一块」的函数，")
    add("   参照集是「标注对象就是这一块」。本次有")
    uncovered_total = (res["uncovered_chunks"]["dev"]["items"]
                       + res["uncovered_chunks"]["test"]["items"])
    uncovered_has_ref = (res["uncovered_chunks"]["dev"]["items_with_reference_facts"]
                         + res["uncovered_chunks"]["test"]["items_with_reference_facts"])
    uncovered_facts = (res["uncovered_chunks"]["dev"]["reference_facts_on_uncovered"]
                       + res["uncovered_chunks"]["test"]["reference_facts_on_uncovered"])
    add("   **%d／260 块**（Dev %d、Test %d）在系统侧**没有任何事实被归属到它**，其中 **%d 块**在参照集里是有事实的"
        % (uncovered_total, res["uncovered_chunks"]["dev"]["items"],
           res["uncovered_chunks"]["test"]["items"], uncovered_has_ref))
    add("   （参照集在这些块上共 %d 条事实，逐条计入 FN）。更根本的一层是" % uncovered_facts)
    add("   参照集**逐块**过模型（每条目只标注该块）、系统**逐文档**过模型")
    add("   （`extract.py` 把整篇正文一次性给模型，并设 `MAX_EVENTS` 等条数上限），")
    add("   而被评测块只占其文档平均 %.1f 个文本块中的 1 个。第七节的**三级阶梯**把这一层量化。" 
        % meta["chunks_per_eval_doc"])
    add("5. **判据松紧的影响**（第八节给全部读数）：`quote` 参与匹配后 TP 只会减少")
    add("   （要求两侧引文互含，而两次抽取常常选不同长度的引文）；`role` 参与后关系 TP 再减少；")
    add("   `compat` 判据把事件端点压成字面量 `Event`（关系端点不再区分到哪一个事件），")
    add("   粒度更粗。**主判据与宽松配对之间的落差（事件 F1 0.10 vs 0.43、关系 0.12 vs 0.44）")
    add("   本身就说明：「事件名／端点名是自由文本」这一条对读数的影响远大于抽取能力本身**——")
    add("   引用任何单一口径的数字时都必须说明是哪一个口径。")
    add("6. **没有对拍、也无法对拍的字段**：")
    add("   * 参照集实体的类型专属属性（`stock_code`／`short_name`／`aliases`／`exchange`／`institution_type`／")
    add("     `policy_id`／`issuer`／`publish_date`／`person_id`／`role_title`／`industry_code`／`level`）——")
    add("     系统侧的抽取 schema **只输出** `name`／`type`／`quote`，这些属性在 T3 **根本不抽**，缺失属本体层差异，不是抽取错误；")
    add("   * 参照集 `events[].participants[]`（参与方数组）——系统侧把参与方编码在 `relations[].PARTICIPATES_IN` 里，形状不同；")
    add("   * 参照集 `ontology_boundary_log`（本体边界登记）与 `notes`——系统侧无对应槽位；")
    add("   * 参照集 `times[].quote` 与 `events[].description`／`confidence`——本次不比（`description`／`confidence` 两侧都有，")
    add("     但因表述自由、无客观判据，纳进来只会制造噪声；这是**有意不测**，不是遗漏）；")
    add("   * **`valid_from`／`valid_to` 在两侧的结构不对称**：参照集这两类时间共 %d 条，"
        % (res["type_metrics"][SPLIT_TOTAL]["times"]["valid_from"]["support_reference"]
           + res["type_metrics"][SPLIT_TOTAL]["times"]["valid_to"]["support_reference"]))
    add("     但参照集 `relations[]` 里 `valid_from`／`valid_to` **非空的条数为 0**（不挂在关系上、只登记在 `times[]`）；")
    add("     系统侧却只能从 `BELONGS_TO` 关系的 `valid_from`／`valid_to` 反推——")
    add("     因此第 4.4 节 `valid_from`／`valid_to` 两行的召回为 0，**主要是口径不对称造成的，不能读成「系统完全不会抽时序」**。")
    rel_types_with_support = len([t for t in RELATIONS_ANNOTATED
                                  if res["type_metrics"][SPLIT_TOTAL]["relations"][t]["support_reference"] > 0])
    add("7. **本体覆盖面的两侧不对称**（第 4 节表里直接可见）：系统侧抽出了 %d 类关系，"
        % len(RELATIONS_ANNOTATED))
    add("   参照集只出现 %d 类；系统侧多出的类型（表中支持数为 0 的行）全部落成 FP，" % rel_types_with_support)
    add("   这是「参照集没标」而非「系统抽错」——引用分类型表时必须一起读。")
    add("8. **类型必须一致才算命中**：键里含类型，故「名字抽对、类型判错」会同时记 1 个 FP ＋ 1 个 FN。")
    add("   若改成「只比名字不看类型」，实体读数会更高；本次坚持含类型，因为本体类型判定本身就是 RQ1 的一部分。")
    add("9. **反向对照（异模型参照集）只作对照**：第 9 节用 `deepseek-v4-pro` 的未修复标注重算了一遍；")
    add("   它是**异模型**、同源风险更低，但没有经过 lint 定向修复，硬命中更多。两份读数并列，**不用来互相证明谁对**。")
    add("")
    add("---")
    add("")

    # ---- 7 ----
    add("## 七、「没抽到」还是「抽到了但没落在这一块」")
    add("")
    add("**为什么不做「按文档合并后对拍」**：评测集的抽样规则是**每篇文档只抽 1 个文本块**")
    add("（`sampling.chunk_pick_rule`；实测 260 条 ＝ 260 篇文档、无一篇多于 1 条），")
    add("所以「把同一文档的各块合并」是恒等变换、没有信息量。有信息量的是下面这三级阶梯——")
    add("同一批事实，逐个放宽「算命中」的条件：")
    add("")
    add("1. **块级·主判据**：系统在这一块上给出了同键事实（＝第三节的 TP）；")
    add("2. **文档内·主判据**：系统在**同一篇文档的任何一块**上给出了同键事实——")
    add("   与 1 的差＝**归属位差**（抽取到了，但 quote 落在别的块上）；")
    add("3. **文档内·证据段配对**：系统在同一篇文档里给出了**类型相同、且证据 `quote` 互含**的事实——")
    add("   与 2 的差＝**命名差异**（抽到了同一件事，但事件名／端点名字符串不同）。")
    add("")
    add("余下的 `参照集条数 − 第 3 级命中` 才是「**连证据段都对不上**」的部分，是这次评测里最接近")
    add("「真实漏抽」的读数（仍受参照集本身收录门槛的影响）。")
    add("")
    add("| 任务 | 分段 | 参照集条数 | ①块级·同键 | ①召回 | ②文档内·同键 | ②召回 | ③文档内·证据段配对 | ③召回 | 连证据段都对不上 | 该块上系统条数 | 该块上 FP | 其中同键在本文档别处也出现 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for cls in CLASSES:
        for split in SPLITS + [SPLIT_TOTAL]:
            m = res["doc_scope_metrics"][split][cls]
            add("| %s | %s | %d | %d | %s | %d | %s | %d | %s | %d | %d | %d | %d |"
                % (CLASS_CN[cls], split, m["reference_support"], m["block_key_tp"],
                   fmt(m["block_key_recall"]), m["doc_key_tp"], fmt(m["doc_key_recall"]),
                   m["doc_pair_tp"], fmt(m["doc_pair_recall"]), m["missing_even_at_doc_scope"],
                   m["system_block_facts"], m["system_block_fp"],
                   m["block_fp_same_key_elsewhere_in_doc"]))
    add("")
    add("读法：")
    add("* 最后一列本次四类两段**全为 0**——这不是巧合：`extract.py` 在同一篇文档内对同键实体显式去重")
    add("  （`entity_duplicate` 警告），事件与关系也各只保留一处，所以**同一个键不可能同时落在两个块上**。")
    add("  因此「该块上 FP」不是归属位差能解释的，而是系统在这一块上确实多给了参照集没标的事实。")
    add("* 系统侧在 260 篇评测文档上共产出 %d 条事件（平均 %.2f 条／篇，与全量 709 篇的 1.57 条／篇接近），"
        % (res["doc_scope_metrics"][SPLIT_TOTAL]["events"]["system_doc_facts"],
           res["doc_scope_metrics"][SPLIT_TOTAL]["events"]["system_doc_facts"] / 260.0))
    add("  但其中只有 %d 条落在被标注的那一块上（这些文档平均每篇 %.1f 个文本块）——"
        % (res["doc_scope_metrics"][SPLIT_TOTAL]["events"]["system_block_facts"],
           meta["chunks_per_eval_doc"]))
    add("  **被评测块只是文档里的一块**，系统却是整篇文档一次过模型、再按 quote 落块，")
    add("  这一层结构差是块级读数偏低的主要来源之一。")
    add("")

    # ---- 8 ----
    add("## 八、判据敏感性（松／紧如何影响读数，合计 260）")
    add("")
    rows = []
    for cls in CLASSES:
        variants = list(res["metrics"][SPLIT_TOTAL][cls].keys())
        for v in variants:
            m = res["metrics"][SPLIT_TOTAL][cls][v]
            rows.append([CLASS_CN[cls], v, m["tp"], m["fp"], m["fn"],
                         fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"])])
    add(md_table(["任务", "判据", "TP", "FP", "FN", "Precision", "Recall", "F1"], rows))
    add("")
    for v, note in res["variant_notes"].items():
        add("* `%s`：%s" % (v, note))
    add("")
    add("注：`strict_quote`／`strict_quote_role` 只在**命中键**上加严，因此它们的 FP／FN 仍沿用主判据的值，")
    add("只有 TP 变小——这样三列可以直接看出「加严 quote／role 会损失多少命中」。")
    add("`quote_pair` 是完整的重配对，TP／FP／FN 三者都随之变化。")
    add("")

    # ---- 9 ----
    add("## 九、反向对照：把参照集换成 `deepseek-v4-pro` 未修复版")
    add("")
    add("> 这一节**不是主口径**，只是把同一把尺子换一把参照物。pro 版是**异模型**（同源风险更低），")
    add("> 但没有经过 lint 定向修复（硬命中更多）。两份读数并列，**不得**用其中一份去证明另一份对或错。")
    add("")
    add("| 任务 | 分段 | TP | FP | FN | Precision | Recall | F1 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for cls in CLASSES:
        for split in SPLITS + [SPLIT_TOTAL]:
            m = meta["pro_metrics"][split][cls]["main"]
            add("| %s | %s | %d | %d | %d | %s | %s | %s |"
                % (CLASS_CN[cls], split, m["tp"], m["fp"], m["fn"],
                   fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"])))
    add("")
    add("主参照集与反向对照的参照集规模对照（同一 260 条块）：")
    add("")
    add(md_table(["任务", "主参照集（提准）条数", "反向对照（pro）条数"],
                 [[CLASS_CN[c], meta["ref_sizes"]["repaired"][c], meta["ref_sizes"]["pro"][c]]
                  for c in CLASSES]))
    add("")

    # ---- 10 ----
    add("## 十、复算")
    add("")
    add("```")
    add(REBUILD_CMD)
    add("```")
    add("")
    add("零模型调用、零联网；同一输入两次运行逐字节一致（三个产出文件均为固定顺序、`\\n` 换行、UTF-8 无 BOM）。")
    add("自检项：`python 阶段10-系统测试与对比实验\\工具\\评测抽取.py --selftest`。")
    add("")
    return "\n".join(L)


def build_caliber(res, meta):
    L = []
    add = L.append
    add("# 口径声明（可直接引用进论文）")
    add("")
    add("## 一、这次评测的参照集是什么")
    add("")
    add("本次 RQ1 抽取评测的对照物是**模型参照集**，路径为")
    add("`阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\自动标注\\提准\\{dev,test}.auto.repaired.jsonl`")
    add("（Dev 60 ＋ Test 200 ＝ 260 条，单位是文本块，编号即 `chunk_id`）。")
    add("")
    add("它的生成链条是：`deepseek-flash` 按 Prompt `stage6-auto-annotate-v1.0-flash` 在 temperature 0 下逐条自动标注")
    add("（`status = auto_annotated`，每条带 `provenance` 与 token 账），再由**离线** lint（`auto_annotate_lint.py`，规则 v1.2）")
    add("扫出硬命中条目，只对这些条目做**定向修复**（`auto_annotate_repair.py`，Prompt `stage6-auto-annotate-flash-repair-v1.0`），")
    add("修复后硬命中 0 处／0 条；最后有一次 40 条独立复核（由本项目决策者执行）的 4 处修正。")
    add("")
    add("**它是参照物、不是金标准；参照集与抽取器同端点同模型家族 ⇒ 同源自证风险被降低但没有消除、两者一致不构成独立验证。**")
    add("")
    add("## 二、为什么这一口径不构成独立验证")
    add("")
    add("因为本课题的评测**一律为模型口径**：抽取以**模型参照集**为参照物、问答以跨厂商模型评审为口径。")
    add("抽取评测集的交付文件")
    add("`阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\{dev,test}.jsonl` 是**纯抽样产物**：")
    add("每条只带抽样字段，**不带任何标注字段**（原「260 条交付槽位」连同 `annotation` 字段已按作者决定整体撤销）。")
    add("因此本次评测**没有**、也不会把参照集内容写进交付文件，")
    add("而是另立一份公开、可复算的**模型参照集**，并把系统抽取结果与它对照。")
    add("**它是参照物，不是金标准。**")
    add("")
    add("## 三、本次读数（主判据，micro；口径见《抽取评测报告》第二节）")
    add("")
    add("| 任务 | 分段 | TP | FP | FN | Precision | Recall | F1 | 宽松配对 F1（上界） |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for cls in CLASSES:
        for split in SPLITS + [SPLIT_TOTAL]:
            m = res["metrics"][split][cls]["main"]
            q = res["metrics"][split][cls].get("quote_pair") or {}
            add("| %s | %s | %d | %d | %d | %s | %s | %s | %s |"
                % (CLASS_CN[cls], split, m["tp"], m["fp"], m["fn"],
                   fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"]), fmt(q.get("f1"))))
    add("")
    add("## 四、指标该怎么读")
    add("")
    add("1. 只能表述为「**模型参照集口径下的抽取表现**」。")
    add("2. 读数是「系统抽取结果 vs 模型参照集」在实体／事件／关系／时间四类任务上的 Precision／Recall／F1，")
    add("   Dev 60 用于说明调优过程，Test 200 是独立评测段，合计 260。")
    add("3. **Dev 与 Test 用同一把尺子、同一份参照集、同一套匹配判据**；判据逐类写在《抽取评测报告》第二节。")
    add("4. 分类型读数（8 类事件、9 条关系、5 类实体、3 类时间）比总读数更可靠——")
    add("   第三方盲标复核显示：条目级「完全一致率」很低（12.5%～30.0%），而**分层指标**")
    add("   （实体类型一致率 κ 0.98～1.00、事件类型分布 TVD 0.06～0.13）可跨厂商复现。")
    add("5. 参照集与抽取器**同端点、同模型家族**（主参照集用的 `deepseek-flash` 更与抽取器同模型），")
    add("   同源自证风险被降低但没有消除，两者之间的一致**不构成独立验证**。")
    add("6. 偏倚方向已登记：**参照集比多模型共识更紧、以漏标为主，因此抽取的 Precision 与 Recall 都被低估。**")
    add("")
    add("## 五、不得怎么读")
    add("")
    add("* **不得**把这些数字写成「准确率」或「金标准下的抽取准确率」。")
    add("* **不得**出现以金标准／标准答案为对照物的表述（如把模型参照集称作金标准或标准答案）。")
    add("* **不得**把参照集与抽取结果之间的一致当作「独立验证」。")
    add("* **不得**把某一类的总读数单独拿出来支撑「抽取质量达标」——必须连**分类型读数**与")
    add("  《抽取评测报告》第六节的已知限制一起引用。")
    add("* **不得**把这套读数当检索 gold 或检索测试集使用（它只可作出题素材，且必须保持「模型参照集」定性）。")
    add("")
    add("## 六、复算")
    add("")
    add("```")
    add(REBUILD_CMD)
    add("```")
    add("")
    add("零模型调用、零联网；同一输入两次运行逐字节一致。")
    add("")
    return "\n".join(L)


# --------------------------------------------------------------------------
# 8. 入口
# --------------------------------------------------------------------------
def build_all():
    norm_note = self_check_normalization()
    doc_chunks = load_doc_chunks()
    items = load_eval_items(doc_chunks)
    ref_rep = load_reference(REF_REPAIRED)
    ref_pro = load_reference(REF_PRO)
    if set(ref_rep) != set(items) or set(ref_pro) != set(items):
        raise AssertionError("参照集条目集合与评测条目集合不一致")
    docs = load_system()
    backfill_payload, backfill_map = load_backfill()

    ref_facts, ref_diag = build_reference_facts(ref_rep)
    ref_facts_pro, _ = build_reference_facts(ref_pro)
    sys_chunks = build_system_facts(docs)

    res = run(items, ref_facts, sys_chunks, backfill_map)
    res_pro = run(items, ref_facts_pro, sys_chunks, backfill_map)

    ref_sizes = OrderedDict()
    for label, facts in (("repaired", ref_facts), ("pro", ref_facts_pro)):
        ref_sizes[label] = OrderedDict(
            (c, sum(len(facts[i][c]) for i in items)) for c in CLASSES)

    diag = OrderedDict([
        ("norm_ws_source", norm_note),
        ("extract_products", OrderedDict([
            ("raw_cache_dir", "阶段05-数据准备/数据集/_抽取缓存/v2.1_v1_2/"),
            ("raw_cache_note", "709 篇，一篇文档一条原始返回；不按文本块"),
            ("raw_cache_model_resolved", sorted(set(
                json.load(io.open(os.path.join(DATASET_ROOT, "_抽取缓存", "v2.1_v1_2",
                                               fn), encoding="utf-8")).get("model_resolved")
                for fn in os.listdir(os.path.join(DATASET_ROOT, "_抽取缓存", "v2.1_v1_2"))
                if fn.endswith(".json")))),
            ("t3_records", "代码/抽取与图谱/_全量/v2.1_v1_2/extracted.jsonl"),
            ("t3_docs", len(docs)),
            ("t3_records_schema", sorted(set(r.get("record_schema") for r in docs.values()))),
            ("t3_prompt_version", sorted(set(r.get("prompt_version") for r in docs.values()))),
            ("backfill_schema", backfill_payload.get("schema")),
            ("backfill_profile", backfill_payload.get("profile")),
        ])),
        ("reference_models", OrderedDict([
            ("repaired", OrderedDict([
                ("path", "阶段05-数据准备/数据集/抽取评测集/v2.1/自动标注/提准/{dev,test}.auto.repaired.jsonl"),
                ("model_resolved", sorted(set(
                    (ref_rep[i]["annotation"].get("provenance") or {}).get("model_resolved")
                    for i in items))),
                ("prompt_versions", sorted(set(
                    (ref_rep[i]["annotation"].get("provenance") or {}).get("prompt_version")
                    for i in items))),
                ("temperatures", sorted(set(
                    (ref_rep[i]["annotation"].get("provenance") or {}).get("temperature")
                    for i in items), key=lambda x: (x is None, x))),
                ("status", sorted(set(ref_rep[i]["annotation"].get("status") for i in items))),
            ])),
            ("pro", OrderedDict([
                ("path", "阶段05-数据准备/数据集/抽取评测集/v2.1/自动标注/{dev,test}.auto.jsonl"),
                ("model_resolved", sorted(set(
                    (ref_pro[i]["annotation"].get("provenance") or {}).get("model_resolved")
                    for i in items))),
                ("prompt_versions", sorted(set(
                    (ref_pro[i]["annotation"].get("provenance") or {}).get("prompt_version")
                    for i in items))),
                ("status", sorted(set(ref_pro[i]["annotation"].get("status") for i in items))),
            ])),
        ])),
        ("reference_sizes_raw", ref_sizes),
        ("reference_times_vs_events", OrderedDict([
            ("times_event_time_entries", sum(ref_diag[i]["times_event_time_entries"] for i in items)),
            ("events_with_time", sum(ref_diag[i]["events_with_time"] for i in items)),
            ("relations_valid_from_nonempty", sum(ref_diag[i]["relations_valid_from_nonempty"] for i in items)),
            ("relations_valid_to_nonempty", sum(ref_diag[i]["relations_valid_to_nonempty"] for i in items)),
        ])),
    ])

    payload = OrderedDict([
        ("schema", "stage10-extraction-eval-1.0"),
        ("title", "RQ1 抽取评测指标（模型参照集口径）"),
        ("caliber", OrderedDict([
            ("label", "模型参照集口径下的抽取表现"),
            ("reference_primary", "阶段05-数据准备/数据集/抽取评测集/v2.1/自动标注/提准/{dev,test}.auto.repaired.jsonl"),
            ("reference_secondary", "阶段05-数据准备/数据集/抽取评测集/v2.1/自动标注/{dev,test}.auto.jsonl"),
            ("is_reference_human_annotated", False),
            ("statement", "参照集为模型自动标注（deepseek-flash，与抽取器同模型）经 lint 定向修复后的产物，"
                          "另有一次由本项目决策者以模型口径执行的 40 条独立复核修正；它是参照物、不是金标准。"),
            ("rebuild_command", REBUILD_CMD),
            ("model_calls", 0),
        ])),
        ("scope", OrderedDict([
            ("items", len(items)),
            ("dev", sum(1 for i in items if items[i]["split"] == "dev")),
            ("test", sum(1 for i in items if items[i]["split"] == "test")),
            ("unit", "chunk（文本块）"),
            ("ontology", OrderedDict([
                ("entity_types", ENTITY_TYPES),
                ("event_types", EVENT_TYPES),
                ("relations", RELATIONS),
                ("relations_scored", RELATIONS_ANNOTATED),
                ("time_types", TIME_TYPES),
            ])),
        ])),
        ("diagnostics", diag),
        ("results", OrderedDict([
            ("variant_notes", res["variant_notes"]),
            ("metrics", res["metrics"]),
            ("type_metrics", res["type_metrics"]),
            ("doc_scope_metrics", res["doc_scope_metrics"]),
            ("event_time_nonempty_rate", res["event_time_nonempty_rate"]),
            ("duplicate_key_diagnostics", res["duplicate_key_diagnostics"]),
            ("uncovered_chunks", res["uncovered_chunks"]),
        ])),
        ("counter_reference_readings", OrderedDict([
            ("note", "把参照集换成 deepseek-v4-pro 未修复版的对照读数；不是主口径。"),
            ("metrics", res_pro["metrics"]),
            ("type_metrics", res_pro["type_metrics"]),
            ("doc_scope_metrics", res_pro["doc_scope_metrics"]),
        ])),
    ])

    meta = {
        "pro_metrics": res_pro["metrics"],
        "ref_sizes": ref_sizes,
        "ref_times_event_time_entries": diag["reference_times_vs_events"]["times_event_time_entries"],
        "ref_events_with_time": diag["reference_times_vs_events"]["events_with_time"],
        "chunks_per_eval_doc": (sum(len(i["doc_chunk_ids"]) for i in items.values())
                                / float(len(items))),
    }

    write_text(OUT_JSON, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text(OUT_MD, build_report(res, meta) + "\n")
    write_text(OUT_CALIBER, build_caliber(res, meta) + "\n")
    return payload, res, meta


def print_summary(res, meta):
    print("=" * 78)
    print("RQ1 抽取评测（模型参照集口径）——四类任务 P／R／F1（主判据，micro）")
    print("=" * 78)
    for cls in CLASSES:
        print("-- %s" % CLASS_CN[cls])
        for split in SPLITS + [SPLIT_TOTAL]:
            m = res["metrics"][split][cls]["main"]
            q = res["metrics"][split][cls].get("quote_pair") or {}
            print("   %-5s TP=%-5d FP=%-5d FN=%-5d  P=%s R=%s F1=%s  ｜宽松配对 P=%s R=%s F1=%s"
                  % (split, m["tp"], m["fp"], m["fn"],
                     fmt(m["precision"]), fmt(m["recall"]), fmt(m["f1"]),
                     fmt(q.get("precision")), fmt(q.get("recall")), fmt(q.get("f1"))))
    print("-- event_time 非空率")
    for split in SPLITS + [SPLIT_TOTAL]:
        r = res["event_time_nonempty_rate"][split]
        print("   %-5s 参照集 %s／%s=%s ；系统(T3) %s／%s=%s ；系统(T3+补抽) %s／%s=%s"
              % (split, r["reference_events_with_time"], r["reference_events"],
                 fmt(r["reference_nonempty_rate"]), r["system_events_with_time"], r["system_events"],
                 fmt(r["system_nonempty_rate"]), r["system_events_with_time_after_backfill"],
                 r["system_events"], fmt(r["system_nonempty_rate_after_backfill"])))
    print("-- 未归属块")
    for split in SPLITS:
        d = res["uncovered_chunks"][split]
        print("   %-5s 无系统事实的块 %d；其中参照集有事实的 %d；这些块上参照集事实 %d 条"
              % (split, d["items"], d["items_with_reference_facts"], d["reference_facts_on_uncovered"]))
    print("-- 反向对照（pro 参照集，合计 260）")
    for cls in CLASSES:
        m = meta["pro_metrics"][SPLIT_TOTAL][cls]["main"]
        print("   %-4s P=%s R=%s F1=%s" % (CLASS_CN[cls], fmt(m["precision"]),
                                           fmt(m["recall"]), fmt(m["f1"])))


def selftest():
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        return bool(cond)

    payload, res, meta = build_all()
    doc_chunks = load_doc_chunks()
    items = load_eval_items(doc_chunks)
    ok("评测条目 260（Dev 60 ＋ Test 200）",
       len(items) == 260 and sum(1 for i in items if items[i]["split"] == "dev") == 60)
    ok("每篇文档只抽 1 块（260 条 ＝ 260 篇文档）",
       len(set((items[i]["split"], items[i]["doc_id"]) for i in items)) == 260,
       "故「按文档合并后对拍」是恒等变换，已改用「块外命中」读数")
    ok("交付槽位仍为空（冻结契约）", True, "load_eval_items 已逐条断言 status 与四槽位为空")
    for cls in CLASSES:
        for split in SPLITS + [SPLIT_TOTAL]:
            m = res["metrics"][split][cls]["main"]
            ok("%s/%s TP+FN==参照集条数" % (cls, split),
               m["support_reference"] == m["tp"] + m["fn"])
            ok("%s/%s TP+FP==系统条数" % (cls, split),
               m["predicted_system"] == m["tp"] + m["fp"])
        tot = res["metrics"][SPLIT_TOTAL][cls]["main"]
        d = res["metrics"]["dev"][cls]["main"]
        t = res["metrics"]["test"][cls]["main"]
        ok("%s 合计==Dev+Test（micro 可加）" % cls,
           (tot["tp"], tot["fp"], tot["fn"]) == (d["tp"] + t["tp"], d["fp"] + t["fp"], d["fn"] + t["fn"]))
        for split in SPLITS + [SPLIT_TOTAL]:
            mm = res["metrics"][split][cls]["main"]
            qq = res["metrics"][split][cls]["quote_pair"]
            ok("%s/%s 宽松配对的 TP ≥ 主判据 TP（上界性质）" % (cls, split),
               qq["tp"] >= mm["tp"], "%d ≥ %d" % (qq["tp"], mm["tp"]))
            ds = res["doc_scope_metrics"][split][cls]
            ok("%s/%s 块级命中==主判据 TP；文档内同键 ≥ 块级；证据段配对 ≥ 同键" % (cls, split),
               ds["block_key_tp"] == mm["tp"]
               and ds["doc_key_tp"] >= ds["block_key_tp"]
               and ds["doc_pair_tp"] >= ds["doc_key_tp"]
               and ds["block_pair_tp"] >= ds["block_key_tp"],
               "块级同键 %d／文档内同键 %d／块级配对 %d／文档内配对 %d"
               % (ds["block_key_tp"], ds["doc_key_tp"], ds["block_pair_tp"], ds["doc_pair_tp"]))
    ok("times 的 support == 参照集 times 去重后的条数（原始 %d → 去重 %d）"
       % (meta["ref_sizes"]["repaired"]["times"],
          res["duplicate_key_diagnostics"]["times"]["reference_uniq"]),
       res["metrics"][SPLIT_TOTAL]["times"]["main"]["support_reference"]
       == res["duplicate_key_diagnostics"]["times"]["reference_uniq"])
    ok("EVIDENCED_BY 不计入关系对拍",
       res["type_metrics"][SPLIT_TOTAL]["relations"]["EVIDENCED_BY"]["support_reference"] == 0
       and res["type_metrics"][SPLIT_TOTAL]["relations"]["EVIDENCED_BY"]["predicted_system"] == 0)
    ok("8 类事件全部出现在分类型表", all(t in res["type_metrics"][SPLIT_TOTAL]["events"] for t in EVENT_TYPES))
    ok("9 条关系全部出现在分类型表", all(t in res["type_metrics"][SPLIT_TOTAL]["relations"] for t in RELATIONS))
    for p in (OUT_JSON, OUT_MD, OUT_CALIBER):
        ok("产出存在：%s" % os.path.basename(p), os.path.isfile(p))
    bad = [c for c in checks if not c[1]]
    for name, good, detail in checks:
        print("  [%s] %s%s" % ("OK " if good else "FAIL", name, ("  " + detail) if detail else ""))
    print("自检：%d 项，通过 %d，失败 %d" % (len(checks), len(checks) - len(bad), len(bad)))
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="RQ1 抽取评测（模型参照集口径）确定性复算")
    ap.add_argument("--selftest", action="store_true", help="重建产出并跑内部一致性自检")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    payload, res, meta = build_all()
    print_summary(res, meta)
    print("-" * 78)
    for p in (OUT_JSON, OUT_MD, OUT_CALIBER):
        print("已写：%s" % os.path.relpath(p, ROOT).replace("\\", "/"))
    print("模型调用：0 次；联网：无")
    return 0


if __name__ == "__main__":
    sys.exit(main())
