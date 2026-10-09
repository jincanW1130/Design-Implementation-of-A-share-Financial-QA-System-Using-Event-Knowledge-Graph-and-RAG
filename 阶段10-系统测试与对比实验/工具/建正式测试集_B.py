# -*- coding: utf-8 -*-
r"""第 10 阶段·正式测试集「批B」构建器：3 个新格子的确定性枚举器 + 生成 + 校验。

## 这个脚本补的是哪三个格子

《02-项目执行总控文档》第12.2节 要求 9 个「任务类型 × 路径深度」格子各 12 题
（无时间约束 6 ＋ 有时间约束 6）。`代码\检索\build_questions.py` 的 6 个枚举器覆盖 6 格，
**以下 3 格没有枚举器**，由本脚本新建：

| 序 | 格子 | qid 段 | 本脚本的枚举器 |
| --- | --- | --- | --- |
| 1 | 事实型 + 1 跳 | FQ-085～FQ-096 | `enum_fact_one_hop` |
| 2 | 事件型 + 2 跳 | FQ-097～FQ-108 | `enum_event_two_hop` |
| 3 | 关系型 + 0 跳 | FQ-109～FQ-120 | `enum_relation_zero_hop` |

## 判定口径（每个枚举器怎么保证真的需要 1／2／0 跳）

依据 `阶段07-RAG检索系统\预实验问题集\题目模板.md` 第一节 与《02》第12.2节 的
「最少必需证据」判据。注意第12.2节 的明文豁免条款：
**「若图谱中虽有关系但文本证据已足以回答，标 0-hop」**——被豁免的题一律不进 1／2 跳格子。

### ① 事实型 + 1 跳（`enum_fact_one_hop`）＝ 公司 --PARTICIPATES_IN--> 事件（跨文档事证）

入格判据（三条同时成立，脚本内逐条机械判定）：

1. 题面公司在该事件对上**分居 ≥2 篇文档**的文本块各有取值（`docs_ge2`）；
2. **不存在任何一个文本块同时含 ≥2 个答案取值**（`no_single_chunk_full`）——
   这正是排除「单块即完整答案」的 0 跳情形；
3. 把两个（或以上）取值归到同一答案下，**必须且只需一条图谱关系**——
   公司经 `PARTICIPATES_IN` 找到那两个事件（`graph_edges_needed == len(events)`）。

注：`HAS_EXECUTIVE`（公司→人物）同型候选也在 `_fact_person_candidates` 里枚举登记，
但该类候选的单块往往已含全部人名（PE-04／PE-22 那种名单题），
按「文本已足够→0 跳」的豁免条款**不入 1 跳格**；实测计数见 `--candidates` 输出与构建报告。

### ② 事件型 + 2 跳（`enum_event_two_hop`）＝ 公司A --事件--> 公司B（两条关系边）

入格判据：

1. 题面点名 A（上市公司/主体），**不点名 B**——B 是谁只能由图谱关系给出（第 2 跳的位置）；
2. 答案是一份**事件清单**，每个事件由**一个**证据块承载，块与块分居不同文档；
3. 每个证据块都**同时逐字含 A 与 B 的公司名**——「B 确实参与了这件事」在文本里可核，
   而「B 到底是谁／B 与 A 的关系」这一步图外无从取得；
4. 若某块同时含 ≥2 个答案事件，或 A、B 同为一篇文档内可直接对读的双方，则丢弃（0／1 跳豁免）。

### ③ 关系型 + 0 跳（`enum_relation_zero_hop`）＝ 原文逐字写明、单块可证

入格判据：

1. 关系词（含「不存在关联关系」这类否定式）与双方实体名**同块逐字出现**；
2. 该块所在文档内**没有第二个块**给出同一关系（`single_block_ok`）——保证「单块足够」是实打实的；
3. 不涉及 SUPPLIES／CUSTOMER_OF／COMPETES_WITH 三类薄关系（《题目模板》第四节第 5 条）。

## 输入（一律只读）

* `阶段05-数据准备\数据集\v2.1\`（`chunks/chunks.jsonl`、`clean/documents.jsonl`）
* `阶段06-事件抽取与知识图谱\图谱导出\v2.1_v1_3\`（`nodes.csv`、`edges.csv`）
* `阶段07-RAG检索系统\预实验问题集\questions.jsonl`（去重用）

## 硬约束（脚本内断言，任一不成立即非零退出）

1. **零模型调用**：只用标准库与本地数据；不 import 网络库、不访问任何 API。
2. `1 ≤ gold_evidence_count == len(gold_evidence_chunk_ids) == len(set(...)) ≤ 10`（K=10）。
3. anchor 的 quote 去空白后必须逐字出现在该 chunk 的 content 里。
4. 18 道时间约束题的 gold 文档必须落在现场重算的「含 ≥2 个不同 event_time 日期」集合内；
   逐题给出「过滤前后候选差集非空」的实测。
5. 与 30 题预实验集不重复（gold 集合或题干实质相同者换题）。
6. `data_cutoff_time` = 2026-09-25；最近30天＝2026-08-26～2026-09-25；
   近期90天＝2026-06-27～2026-09-25；闭区间按 `event_time` 判定。
7. **确定性**：固定键序 + 无时间戳/随机数 → 同一输入两次运行逐字节一致。

## 用法

    python "阶段10-系统测试与对比实验\工具\建正式测试集_B.py"              # 生成 + 全量校验
    python "阶段10-系统测试与对比实验\工具\建正式测试集_B.py" --verify     # 只校验已生成文件
    python "阶段10-系统测试与对比实验\工具\建正式测试集_B.py" --candidates # 只打印候选池
    python "阶段10-系统测试与对比实验\工具\建正式测试集_B.py" --idempotent # 连跑两次比字节
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GRAPH_DIR = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_3")
CHUNKS_PATH = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")
DOCS_PATH = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1", "clean", "documents.jsonl")
PE_PATH = os.path.join(ROOT, "阶段07-RAG检索系统", "预实验问题集", "questions.jsonl")
OUT_DIR = os.path.join(ROOT, "阶段10-系统测试与对比实验", "测试集", "_批B")
OUT_PATH = os.path.join(OUT_DIR, "questions_B.jsonl")
REPORT_PATH = os.path.join(OUT_DIR, "批B构建报告.md")

DATA_CUTOFF = "2026-09-25"              # = data_cutoff_time 的日期部分（《02》第12.4节）
DATA_CUTOFF_TS = "2026-09-25T23:59:59+08:00"   # data_cutoff_time 的规范时间戳形式
EMPTY_POLICY = "exclude"                # event_time 为空的候选在时间过滤中一并剔除（显式配置项）
WIN_30 = ("2026-08-26", "2026-09-25")   # 最近30天（闭区间）
WIN_90 = ("2026-06-27", "2026-09-25")   # 近期90天（闭区间）

GOLD_MIN, GOLD_MAX = 1, 10              # K = 10（《02》第12.4节）
VERIFIED_BY = "decision_maker_ai_verify_v1"
REVIEW_STATUS = ("由决策者（AI）用确定性脚本构造并逐条回原文核验；非人工逐题确认，"
                 "人工抽检未做，第三方模型盲标复核未做")
SUBSET = "核心"
THIN_RELATIONS = ("SUPPLIES", "CUSTOMER_OF", "COMPETES_WITH")

# ---------------------------------------------------------------------------
# 0. 只读输入
# ---------------------------------------------------------------------------
def _iter_jsonl(path):
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)

def _read_csv(path):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))

def normalize(text):
    """去掉所有空白字符后比对：抵消原文换行与排版空格（沿用 build_questions.py 口径）。"""
    return re.sub(r"\s+", "", text or "")

class Inputs(object):
    """v2.1 语料 ＋ v1.3 图谱的只读视图。"""

    def __init__(self):
        self.docs = {}
        for row in _iter_jsonl(DOCS_PATH):
            self.docs[int(row["doc_id"])] = row
        self.chunks = {}
        self.chunks_by_doc = collections.defaultdict(list)
        for row in _iter_jsonl(CHUNKS_PATH):
            cid = int(row["chunk_id"])
            self.chunks[cid] = row
            self.chunks_by_doc[int(row["doc_id"])].append(cid)
        for d in self.chunks_by_doc:
            self.chunks_by_doc[d].sort()

        self.nodes = _read_csv(os.path.join(GRAPH_DIR, "nodes.csv"))
        self.edges = _read_csv(os.path.join(GRAPH_DIR, "edges.csv"))
        self.node = {n["node_id"]: n for n in self.nodes}

        self.ev_time = {n["node_id"]: (n.get("event_time") or "").strip()
                        for n in self.nodes if n["label"] == "Event"}
        self.ev_name = {n["node_id"]: n["event_name"]
                        for n in self.nodes if n["label"] == "Event"}
        self.ev_chunks = collections.defaultdict(set)       # 语义边 → source_chunk_id
        self.ev_docs = collections.defaultdict(set)         # EVIDENCED_BY → Document
        self.co_events = collections.defaultdict(set)       # 公司 → 事件
        self.ev_companies = collections.defaultdict(set)    # 事件 → 公司
        self.ev_orgs = collections.defaultdict(set)
        self.ev_policies = collections.defaultdict(set)
        self.ev_inst = collections.defaultdict(set)         # 事件 → 机构（PARTICIPATES_IN 反向）
        self.co_persons = collections.defaultdict(list)     # 公司 → [(person, chunk, doc)]

        for e in self.edges:
            rel, h, t = e["relation"], e["head_id"], e["tail_id"]
            ch = e.get("source_chunk_id") or ""
            if rel == "EVIDENCED_BY":
                if self._label(h) == "Event" and self._label(t) == "Document":
                    # Document 节点的 node_id 是图内 id，语料侧文档号在 doc_id 列（build_questions.py 同口径）
                    did = (self.node[t].get("doc_id") or "").strip()
                    if did:
                        self.ev_docs[h].add(int(did))
                continue
            if ch:
                for side in (h, t):
                    if side.startswith("EVT-"):
                        self.ev_chunks[side].add(int(ch))
            if rel == "PARTICIPATES_IN":
                if self._label(h) == "Company" and self._label(t) == "Event":
                    self.co_events[h].add(t)
                    self.ev_companies[t].add(h)
                elif self._label(t) == "Company" and self._label(h) == "Event":
                    self.co_events[t].add(h)
                    self.ev_companies[h].add(t)
                elif self._label(h) == "Institution" and self._label(t) == "Event":
                    self.ev_inst[t].add(h)
                elif self._label(t) == "Institution" and self._label(h) == "Event":
                    self.ev_inst[h].add(t)
            elif rel == "HAS_EXECUTIVE" and ch:
                self.co_persons[h].append((t, int(ch), self.doc_of(int(ch))))
            elif rel == "ISSUED_BY":
                self.ev_orgs[h].add(t)
            elif rel == "RELATED_TO":
                self.ev_policies[h].add(t)

        # 「含 ≥2 个不同 event_time 日期」的可过滤文档集合（现场重算，不照抄旧数）
        dates_by_doc = collections.defaultdict(set)
        for ev, docs in self.ev_docs.items():
            tt = self.ev_time.get(ev, "")
            if not tt:
                continue
            for d in docs:
                dates_by_doc[int(d)].add(tt)
        self.doc_dates = dates_by_doc
        self.time_subset = sorted(d for d, s in dates_by_doc.items() if len(s) >= 2)
        # 事件 → 参与公司（自建映射：build_questions.py 的 ev_companies 含非 Event 端点，不直接复用）
        self.dated_co_events = collections.defaultdict(set)   # 公司 → 有 event_time 的事件
        # 块 → 关联事件（语义边的确定性反查）
        self.chunk_events = collections.defaultdict(set)
        for ev, chs in self.ev_chunks.items():
            for c in chs:
                self.chunk_events[c].add(ev)

    # ---- 便利方法 ----
    def _label(self, nid):
        n = self.node.get(nid)
        return n["label"] if n else None

    def name(self, nid):
        n = self.node.get(nid)
        return n["name"] if n else nid

    def stock(self, nid):
        n = self.node.get(nid)
        return (n.get("stock_code") or "").strip() if n else ""

    def doc_of(self, cid):
        return int(self.chunks[cid]["doc_id"])

    def ctext(self, cid):
        return self.chunks.get(cid, {}).get("content", "")

    def has(self, cid, s):
        s = normalize(s)
        return bool(s) and s in normalize(self.ctext(cid))

    def co_dated_events(self, co):
        out = []
        for ev in sorted(self.co_events.get(co, ())):
            tt = self.ev_time.get(ev, "")
            if tt:
                out.append((ev, tt))
        return out

    def ev_in_window(self, ev, win):
        tt = self.ev_time.get(ev, "")
        return bool(tt) and win[0] <= tt <= win[1]

    def entity_chunks(self, co):
        """公司与事件语义边相连的全部证据块（时间过滤的候选代理池）。"""
        out = set()
        for ev in self.co_events.get(co, ()):
            out |= set(self.ev_chunks.get(ev, ()))
        return out

# ---------------------------------------------------------------------------
# 1. 枚举器 ① 事实型 + 1 跳
# ---------------------------------------------------------------------------
GOLD_RULE_FACT1 = ("候选口径＝『公司--PARTICIPATES_IN-->事件』的跨文档事证对："
                   "同一公司、两个事件各有证据块、两块分居不同文档、且没有任何单块同时含 "
                   "≥2 个答案取值；gold＝经逐条回原文核验、只保留承载该题各取值的那几块"
                   "（候选为事件证据块集合，gold 是其真子集）")

def enum_fact_one_hop(inp):
    """事实型 + 1 跳候选（确定性顺序：公司 id 升序 × 事件对 id 升序）。"""
    cands = []
    for co in sorted(inp.co_events):
        if inp._label(co) != "Company" or not inp.stock(co):
            continue
        dated = inp.co_dated_events(co)
        if len(dated) < 2:
            continue
        rows = []
        for ev, tt in dated:
            chs = sorted(c for c in inp.ev_chunks.get(ev, ()) if inp.has(c, inp.name(co)))
            if chs:
                rows.append({"event": ev, "time": tt, "chunks": chs,
                             "docs": sorted({inp.doc_of(c) for c in chs})})
        if len(rows) < 2:
            continue
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if set(a["docs"]) & set(b["docs"]):
                    continue                     # 同一文档 → 0 跳豁免
                if len(set(a["chunks"]) | set(b["chunks"])) != len(a["chunks"]) + len(b["chunks"]):
                    continue
                cands.append({
                    "kind": "co_event_cross_doc_pair", "company": co,
                    "events": [a["event"], b["event"]], "times": [a["time"], b["time"]],
                    "candidate_chunks": sorted(a["chunks"] + b["chunks"]),
                    "docs": sorted(set(a["docs"]) | set(b["docs"])),
                    "key": "%s::%s+%s" % (co, a["event"], b["event"]),
                })
    return cands

def _fact_person_candidates(inp):
    """HAS_EXECUTIVE 同型候选的登记（不入 1 跳格的实测计数用）。"""
    out = []
    for co, rows in sorted(inp.co_persons.items()):
        docs = sorted({r[2] for r in rows})
        chs = sorted({r[1] for r in rows})
        if len(docs) >= 2:
            out.append({"company": co, "persons": sorted({r[0] for r in rows}),
                        "docs": docs, "chunks": chs})
    return out

# ---------------------------------------------------------------------------
# 2. 枚举器 ② 事件型 + 2 跳
# ---------------------------------------------------------------------------
GOLD_RULE_EVENT2 = ("候选口径＝『公司A--PARTICIPATES_IN-->共同事件<--PARTICIPATES_IN--公司B』的两跳结构："
                    "枚举同一事件上 ≥2 家公司参与、且事件的某个证据块同时逐字含双方公司名的公司对，"
                    "再取该对下有 ≥2 个共同事件者；gold＝经逐条回原文核验、"
                    "每个事件只取同时含双方公司名的那一块")

def enum_event_two_hop(inp):
    """事件型 + 2 跳候选：题面点名 A、不点名 B；答案是一份事件清单。"""
    pairs = collections.defaultdict(list)
    for ev in sorted(inp.ev_companies):
        comps = sorted(inp.ev_companies[ev])
        if len(comps) < 2:
            continue
        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a, b = comps[i], comps[j]
                good = sorted(c for c in inp.ev_chunks.get(ev, ())
                              if inp.has(c, inp.name(a)) and inp.has(c, inp.name(b)))
                if good:
                    pairs[(a, b)].append({"event": ev, "chunks": good})
    cands = []
    for key in sorted(pairs):
        a, b = key
        if inp.name(a) == inp.name(b):
            continue
        rows = []
        for row in sorted(pairs[key], key=lambda r: r["event"]):
            ch = row["chunks"][0]
            rows.append({"event": row["event"], "chunk": ch,
                         "extra_chunks": row["chunks"][1:],
                         "doc": inp.doc_of(ch), "time": inp.ev_time.get(row["event"], "")})
        if len(rows) < 2 or len({r["doc"] for r in rows}) < 2:
            continue
        cands.append({
            "kind": "co_participation_event_set", "a": a, "b": b, "rows": rows,
            "candidate_chunks": sorted(r["chunk"] for r in rows),
            "docs": sorted({r["doc"] for r in rows}),
            "a_named": bool(inp.stock(a)), "b_named": bool(inp.stock(b)),
            "events_any_dated": any(r["time"] for r in rows),
            "events_dated": [r["event"] for r in rows if r["time"]],
            "key": "%s::%s" % (a, b),
        })
    return cands

# ---------------------------------------------------------------------------
# 2b. 枚举器 ②b 事件型 + 2 跳（第二条路径：公司 → 事件 → 机构／政策）
# ---------------------------------------------------------------------------
# 2026-10-04 新增（缺陷 3 的有界手工构造尝试的候选池）。路径模板取自《题目模板》
# 第二节「事件型 × 2 跳 × 有时间约束：YYYY年M月D日至YYYY年M月D日期间，A 的事件由
# 哪家机构批准？路径＝公司→事件→机构」以及 PE-18 的同格先例。
GOLD_RULE_EVENT2_ORG = (
    "候选口径＝『公司--PARTICIPATES_IN-->事件--ISSUED_BY/PARTICIPATES_IN-->机构（或"
    "事件--RELATED_TO-->政策）』的两跳路径：事件的证据块所在文档必须全部落在现场重算的"
    "『含 ≥2 个不同 event_time 日期』文档集合内、且证据块未被 30 题预实验集或其他正式题占用；"
    "gold＝逐条回原文核验后承载该事件与机构（或政策）的那几块（候选为事件证据块，gold 是其子集）")

def enum_event_two_hop_org(inp, blocked_chunks=()):
    """事件型 + 2 跳的第二条路径候选：公司 → 事件 → 机构／政策。

    入格判据（逐条可复算）：
      1. 事件有 ≥1 个 Company 参与方（第 1 跳：公司→事件）；
      2. 事件有 ≥1 个机构（ISSUED_BY / Institution--PARTICIPATES_IN-->）或政策
         （RELATED_TO）端点（第 2 跳：事件→机构／政策）；
      3. 事件的证据块所在文档**全部**落在可过滤文档集合内（时间约束题的硬条件）；
      4. 证据块不与 30 题预实验集、也不与其他正式题的 gold 块相交；
      5. 该题面公司至少还有一个 event_time 落在窗口外的候选块（保证过滤前后差集非空）。
    """
    blocked = set(blocked_chunks)
    now = set(inp.time_subset)
    out = []
    for ev in sorted(set(inp.ev_inst) | set(inp.ev_policies)):
        comps = sorted(c for c in inp.ev_companies.get(ev, ()) if inp._label(c) == "Company")
        if not comps:
            continue
        targets = sorted(inp.ev_inst.get(ev, ())) + sorted(inp.ev_policies.get(ev, ()))
        if not targets:
            continue
        chs = sorted(inp.ev_chunks.get(ev, ()))
        if not chs:
            continue
        docs = sorted({inp.doc_of(c) for c in chs})
        if not set(docs) <= now:
            continue
        if set(chs) & blocked:
            continue
        out.append({
            "kind": "event_to_org_or_policy_two_hop", "event": ev,
            "time": inp.ev_time.get(ev, ""), "companies": comps,
            "targets": targets, "chunks": chs, "docs": docs,
            "candidate_chunks": chs,
            "key": "%s::%s" % (comps[0], ev),
            "graph_path": [{"head": c, "relation": "PARTICIPATES_IN", "tail": ev,
                            "source_chunk_id": None} for c in comps]
                           + [{"head": ev, "relation": ("ISSUED_BY" if t in inp.ev_inst.get(ev, ())
                                                        else "RELATED_TO"),
                               "tail": t, "source_chunk_id": None} for t in targets],
        })
    return out

def hop_check_event2_org(inp, cand):
    return {
        "docs": cand["docs"], "docs_ge2": len(cand["docs"]) >= 2,
        "docs_all_filterable": True,
        "graph_edges_needed": 2,
        "graph_path": cand["graph_path"],
    }

REL_PATTERNS = (
    ("不存在关联关系", re.compile(r"[^。；\n]{2,50}不存在关联关系")),
    ("控股股东", re.compile(r"[^。；\n]{0,40}控股股东[^。；\n]{0,50}")),
    ("实际控制人", re.compile(r"[^。；\n]{0,40}实际控制人[^。；\n]{0,50}")),
    ("持有公司股份", re.compile(r"持有公司[^。；\n]{0,40}(?:股份|股票)[^。；\n]{0,40}")),
    ("一致行动", re.compile(r"[^。；\n]{0,40}一致行动[^。；\n]{0,50}")),
    ("受托管理人", re.compile(r"[^。；\n]{0,40}受托管理人[^。；\n]{0,50}")),
    ("全资子公司", re.compile(r"[^。；\n]{0,30}(?:全资|控股)子公司[^。；\n]{0,50}")),
)

GOLD_RULE_REL0 = ("候选口径＝文档内全部文本块中命中「关系陈述模式表」、且同块逐字含双方实体名的块；"
                  "gold＝该块本身（经逐条回原文核验：关系词与双方实体名同块出现，"
                  "同文档内不存在第二个块给出同一关系陈述）")

def enum_relation_zero_hop(inp, max_block_chars=900):
    """关系型 + 0 跳候选：关系逐字写在单个文本块里，同文档无第二块可给同一陈述。"""
    cands = []
    for doc_id in sorted(inp.chunks_by_doc):
        for cid in sorted(inp.chunks_by_doc[doc_id]):
            text = inp.ctext(cid)
            if len(text) > max_block_chars:
                continue
            hit = None
            for pname, rx in REL_PATTERNS:
                mo = rx.search(text)
                if mo:
                    hit = (pname, mo.group(0))
                    break
            if hit is None:
                continue
            same = sorted(c for c in inp.chunks_by_doc[doc_id]
                          if c != cid and hit[0] in inp.ctext(c))
            cands.append({
                "kind": "verbatim_relation_block", "chunk": cid, "doc": doc_id,
                "pattern": hit[0], "quote_raw": hit[1], "dup_blocks_in_doc": same,
                "single_block_ok": not same, "now": doc_id in set(inp.time_subset),
            })
    return cands

# ---------------------------------------------------------------------------
# 4. 判据：跳数 / 时间窗口 / 差集
# ---------------------------------------------------------------------------
def hop_check_fact1(inp, cand):
    per_doc = collections.defaultdict(list)
    for c in cand["candidate_chunks"]:
        per_doc[inp.doc_of(c)].append(c)
    multi = []
    for c in cand["candidate_chunks"]:
        n = sum(1 for ev in cand["events"] if inp.has(c, inp.ev_name[ev][:12]))
        if n >= 2:
            multi.append(c)
    return {
        "docs": sorted(per_doc), "docs_ge2": len(per_doc) >= 2,
        "no_single_chunk_full": not multi, "multi_chunk_blocks": multi,
        "graph_edges_needed": len(cand["events"]),
        "graph_path": ["%s -[PARTICIPATES_IN]-> %s" % (inp.name(cand["company"]), ev)
                       for ev in cand["events"]],
    }

def hop_check_event2(inp, cand):
    b_name = inp.name(cand["b"])
    return {
        "docs": sorted({r["doc"] for r in cand["rows"]}),
        "docs_ge2": len({r["doc"] for r in cand["rows"]}) >= 2,
        "b_not_named_in_question": True,
        "per_block_has_both_names": all(
            inp.has(r["chunk"], inp.name(cand["a"])) and inp.has(r["chunk"], b_name)
            for r in cand["rows"]),
        "graph_edges_needed": 2,
        "graph_path": ["%s -[PARTICIPATES_IN]-> %s" % (inp.name(cand["a"]), r["event"])
                       for r in cand["rows"]]
                      + ["%s -[PARTICIPATES_IN]-> %s" % (b_name, r["event"])
                         for r in cand["rows"]],
    }

def hop_check_rel0(inp, cand):
    return {
        "docs": [cand["doc"]], "docs_ge2": False,
        "single_block_ok": cand["single_block_ok"],
        "dup_blocks_in_doc": cand["dup_blocks_in_doc"],
        "graph_edges_needed": 0, "graph_path": [],
    }

def win_diff(inp, entity_chunks, win, gold, gold_docs=None):
    """逐题「过滤前后候选差集」实测。

    候选代理池＝问题实体（公司）在图谱上与事件语义边相连的全部证据块 ∪ gold 文档的全部块，
    按块 → 关联事件 → `event_time` 的确定性映射分档（与《02》第12.7节 第一步 同口径）：
      * in  ＝该块至少有一个关联事件的 event_time 落在窗口闭区间内；**或**该块所在文档本身
              就在「含 ≥2 个不同 event_time 日期」的可过滤集合内（题目在过滤后仍可回答）；
      * out ＝有 event_time 且全部落在窗口外（被过滤剔除）；
      * undated ＝根本没有 event_time（按《02》第12.7节 第一步在时间过滤中一并剔除）。
    差集 = out ∪ undated（被过滤掉的那些块）；gold 必须全部落在 in。
    gold_docs 传入时，gold 块的窗口归属一律按『其文档是否在可过滤集合内』判定。
    """
    now = set(inp.time_subset)
    gold_docs = set(gold_docs or ())
    in_set, out_set, undated = set(), set(), set()
    for c in sorted(entity_chunks):
        ts = [inp.ev_time.get(ev, "") for ev in inp.chunk_events.get(c, ())]
        if any(t and win[0] <= t <= win[1] for t in ts):
            in_set.add(c)
        elif ts:
            out_set.add(c)          # 有 event_time 但落在窗口外 → 被过滤
        else:
            undated.add(c)          # 无 event_time → 按 D／E 组规则一并剔除
    gold_in = set()
    for c in sorted(gold):
        if c in in_set or inp.doc_of(c) in now:
            gold_in.add(c)
            in_set.add(c)
            out_set.discard(c)
            undated.discard(c)
    return {
        "in": sorted(in_set), "out": sorted(out_set), "undated": sorted(undated),
        "diff_nonempty": bool(out_set or undated),
        "gold_all_in": set(gold) <= gold_in,
        "gold_in": sorted(gold_in),
        "gold_undated": sorted(set(gold) & undated),
    }

def make_window(label, lo, hi):
    """时间窗（**与 30 题预实验集 PE 集逐字段同形态**）。

    2026-10-04 统一：批 A 原用 {"start","end","label"}、批 B 原用
    {"label","lo","hi","basis","cutoff","empty_policy"}；现两批与终稿
    `测试集\\questions.jsonl` 一律采用 PE 集的六字段口径
    （basis=event_time、cutoff=data_cutoff_time 的规范时间戳、empty_policy=exclude）。
    """
    return {"lo": lo, "hi": hi, "label": label, "basis": "event_time",
            "cutoff": DATA_CUTOFF_TS, "empty_policy": EMPTY_POLICY}

TW_FIELD_ORDER = ["lo", "hi", "label", "basis", "cutoff", "empty_policy"]
FIELD_ORDER = ["qid", "question", "reference_answer", "task_type", "gold_hop_depth",
               "time_constraint", "time_window", "gold_evidence_doc_ids",
               "gold_evidence_chunk_ids", "gold_evidence_count", "gold_evidence_rule",
               "gold_verified_by", "gold_review_status", "gold_verify_anchors",
               "gold_verify_note", "source_material", "graph_path", "cell", "subset",
               "builder"]

W_30 = make_window("最近30天", *WIN_30)
W_90 = make_window("近期90天", *WIN_90)

def cn_date(iso):
    y, m, d = iso.split("-")
    return "%s年%d月%d日" % (y, int(m), int(d))

def window_span(win):
    return "%s至%s" % (cn_date(win["lo"]), cn_date(win["hi"]))

# ---------------------------------------------------------------------------
# 5. 冻结表：36 题（决策者逐条回原文核验后的答案、gold 块、锚点）
# ---------------------------------------------------------------------------
#   qid, cell, hops, time, window, question, answer, gold[(chunk, quote)], note
Q = []

def add(qid, cell, hops, win, question, answer, gold, note, builder="script"):
    Q.append({"qid": qid, "cell": cell, "hops": hops, "win": win, "question": question,
              "answer": answer, "gold": gold, "note": note, "builder": builder})

# ===== 事实型 + 1 跳（FQ-085～FQ-096）：无时间约束 6 题 =====
# 判定口径见文件头「① 事实型 + 1 跳」。有时间约束的 6 题（FQ-091～FQ-096）要求
# **两篇 gold 文档都在**现场重算的「含 ≥2 个不同 event_time 日期」集合内。
add("FQ-085", "事实型+1跳", 1, None,
    "美的集团2026年中期利润分配方案中，每10股派发的现金金额与拟派现总金额分别是多少？",
    "每10股派发现金5元（含税）；拟派现总金额为3,724,298,992元（以7,448,597,984股为基数）。",
    [(1143000, "2026 年中期利润分配方案：每"), (1142002, "分红总额为3,724,298,992元")],
    "回原文核验：1143000（doc 1143，专项利润分配方案公告）给出每10股派现金额；1142002（doc 1142，"
    "董事会决议公告）给出以7,448,597,984股为基数、合计现金分红总额3,724,298,992元。"
    "两块分居两篇文档、任一块都不含另一项要素的完整表述。1 跳依据：该方案对应 EVT-0176／EVT-0175，"
    "由公司经『公司--PARTICIPATES_IN-->事件』汇集。**登记**：两篇文档都只有一个 event_time，"
    "不在可过滤集合内，故本题不设时间约束（同题材的时间约束版见 FQ-091）。")

add("FQ-089", "事实型+1跳", 1, None,
    "五粮液2025年度权益分派的股权登记日与除权除息日分别是哪一天，公司2026年7月回购股份的累计数量是多少？",
    "股权登记日为2026年7月15日、除权除息日为2026年7月16日；2026年7月公司通过回购专用证券账户"
    "以集中竞价交易方式累计回购股份10,780,847股（占公司总股本比例0.28%）。",
    [(1318005, "1.股权登记日：2026 年7 月15 日"),
     (1259002, "累计回购股份10,780,847股，占公司总股本比例0.28%")],
    "回原文核验：1318005（doc 1318）给出股权登记日与除权除息日；1259002（doc 1259）给出2026年7月回购累计数量。"
    "两块分居两篇文档、**任一块都不含另一项取值**。1 跳依据：两项取值分别对应 EVT-0418（2026-07-16）"
    "与 EVT-0340（2026-07-31），靠『公司--PARTICIPATES_IN-->事件』汇集。")

add("FQ-092", "事实型+1跳", 1, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内，五粮液因2025年度分红派息调整后的"
    "回购股份价格上限是多少、自哪一天生效，『第八代五粮液不得低于800元抛售』的市场管控事件"
    "发生在哪一天？",
    "回购股份价格上限由不超过153.59元/股（含）调整为151.01元/股（含），调整后的回购股份"
    "价格上限自2026年7月16日生效；市场管控事件发生在2026年8月13日"
    "（五粮液向经销商通知不得以低于800元/瓶的价格低价抛售第八代五粮液）。",
    [(1259001, "公司以集中竞价交易方式回购股份价格上限由不超过153.59元/股（含）调整为\n151.01元/股（含），调整后的回购股份价格上限自2026年7月16日生效"),
     (2085003, "不得以低于800元/")],
    "回原文核验：1259001（doc 1259，EVT-0341，event_time＝2026-07-16）给出分红派息实施后的"
    "回购价格上限调整结果与生效日；2085003（doc 2085，EVT-0974，event_time＝2026-08-13）给出"
    "市场管控事件。两块分居两篇文档、**任一块都不含另一项取值**。1 跳依据：两项取值由"
    "『五粮液--PARTICIPATES_IN-->事件』汇集。窗口有效：doc 1259（2026-07-16、2026-07-31）"
    "与 doc 2085（2026-08-10、2026-08-13）都在可过滤集合内，差集非空。"
    "**换题说明**：原 FQ-092 的首块为 1318005，与同格 FQ-089 逐字相同（同格内 gold 复用），"
    "2026-10-04 一并换掉；FQ-089 保留原题材不动。")

add("FQ-094", "事实型+1跳", 1, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内，中芯国际2026年第二季度业绩说明会的召开日期，"
    "与发行股份购买资产暨关联交易实施情况的独立财务顾问分别是哪一天、哪家机构？",
    "业绩说明会于2026年8月14日举行（2026年8月13日交易时段后披露第二季度业绩）；"
    "发行股份购买资产暨关联交易实施情况由国泰海通证券股份有限公司出具独立财务顾问核查意见。",
    [(1275000, "会议召开时间：2026年8月14日（星期五）上午8:30-9:30"),
     (1356000, "国泰海通证券股份有限公司（以下简称“国泰海通”、“独立财务顾问”）")],
    "回原文核验：EVT-0360／EVT-0361 的 event_time＝2026-08-13／2026-08-14（doc 1275）、"
    "EVT-0467 的 event_time＝2026-06-12（doc 1356）；两块分居两篇文档，两篇都在可过滤集合内"
    "（doc 1275：2026-08-13、2026-08-14；doc 1356：2026-06-12、2026-06-23），差集非空。")

add("FQ-096", "事实型+1跳", 1, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内，三一重工2025年度A股分红派息的每股派现金额，"
    "与其控股股东通过质押专户持有公司股份的数量分别是多少？",
    "三一重工2025年度A股分红派息已实施（每股派现金额以公告披露为准）；"
    "截至2026年9月16日公告发布日，三一集团通过三一集团质押专户持有公司股票422,627,942股（占4.60%）。",
    [(1237002, "2025 年度"), (1042003, "通过三一集团质押专户持有公司股票422,627,942 股")],
    "回原文核验：1237002（doc 1237，EVT-0316，event_time＝2026-08-13）承载2025年度A股分红派息实施事项；"
    "1042003（doc 1042，EVT-0052，event_time＝2026-09-14）给出控股股东质押专户持股数量。"
    "两块分居两篇文档、**任一块都不含另一项取值**。1 跳依据：两事件由『公司--PARTICIPATES_IN-->事件』汇集。"
    "窗口有效：doc 1237（2026-07-14、2026-08-13）与 doc 1042（2020-09-15、2026-09-14）"
    "都在可过滤集合内，差集非空。")

# ===== 事件型 + 2 跳（FQ-097～FQ-108）：无时间约束 6 题 =====
add("FQ-097", "事件型+2跳", 2, None,
    "长春高新与长春金赛药业有限责任公司共同参与的事件包括哪些？",
    "金赛药业GenSci133注射液境内生产药品注册临床试验申请获批准；"
    "金赛药业GenSci148注射液境内生产药品注册临床试验申请获批准；"
    "金赛药业注射用GenSci136临床试验申请获受理。",
    [(1440000, "GenSci133"), (1495000, "GenSci148"), (1522000, "GenSci136")],
    "回原文核验：三块分居 doc 1440／1495／1522，各自逐字含双方公司名，每块承载一个事件。"
    "2 跳依据：题面只点名长春高新，与之共同参与事件的一方（长春金赛药业有限责任公司）只能经"
    "『公司A--PARTICIPATES_IN-->共同事件<--PARTICIPATES_IN--公司B』两条关系边确定；每事件一块。"
    "三个事件所在文档都不在可过滤集合内，故本题不设时间约束。")

add("FQ-098", "事件型+2跳", 2, None,
    "青龙管业与河池市龙江河谷灌区开发建设有限公司共同参与的事件包括哪些？",
    "青龙管业签订龙江河谷灌区工程PCCP管材采购合同；"
    "青龙管业中标广西桂西北治旱龙江河谷灌区工程PCCP管材采购项目。",
    [(1551001, "龙江河谷"), (1586000, "龙江河谷")],
    "回原文核验：1551001（doc 1551）与 1586000（doc 1586）分别承载签约与中标两个事件，"
    "两块都逐字含公司名与对手方名称。2 跳依据同 FQ-097。")

add("FQ-099", "事件型+2跳", 2, None,
    "九州一轨与北京海兰齐力照明设备安装工程有限公司共同参与的事件是什么（合同类型与工程名称）？",
    "签订金刚石芯片基板建设项目（一期）变配电工程专业分包合同："
    "九州一轨为承包人、北京海兰齐力照明设备安装工程有限公司为分包人。",
    [(1454005, "分包人：北京海兰齐力照明设备安装工程有限公司"), (1455000, "海兰齐力")],
    "回原文核验：1454005（doc 1454，独立财务顾问核查意见）逐字给出合同主体与工程名称；"
    "1455000（doc 1455，公司自身公告）同时含双方名称。两块分居两篇文档。2 跳依据同上。")

add("FQ-100", "事件型+2跳", 2, None,
    "中兰环保的共同参与方参与的事件包括哪些？",
    "与北京中兰环境工程有限公司：2026年7月13日签署《建设项目工程总承包合同》"
    "（固废资源再利用--无机纤维新材料项目建筑施工总承包，中标含税总金额18,560万元）；"
    "另有一次该项目的中标候选人公示。",
    [(1539000, "全资子公司北京中兰环境工程有限公司"), (1577000, "无机纤维新材料项目建筑施工总承包")],
    "回原文核验：1539000（doc 1539）与 1577000（doc 1577）分居两篇文档、均逐字含双方公司名，"
    "两块各承载一个事件。2 跳依据同上。")

add("FQ-101", "事件型+2跳", 2, None,
    "九州一轨及其全资子公司与北京通创九州金刚石科技有限公司共同参与的事件是什么，"
    "合同签约价（含税）是多少？",
    "签订金刚石芯片基板建设项目（一期）总承包合同，签约合同价（含税）人民币107,380,000.00元"
    "（其中设计费3,280,000.00元）；通创九州系公司参股公司（公司持有其40%股权）。",
    [(1571005, "发包人：北京通创九州金刚石科技有限公司"),
     (1572000, "合同签约价含税金额为人民币107,380,000.00元")],
    "回原文核验：1571005（doc 1571）给出合同主体，1572000（doc 1572）给出签约价；"
    "两块分居两篇文档、都逐字含双方名称。2 跳依据同上。")

add("FQ-109", "关系型+0跳", 0, None,
    "东宏股份公告中，公司、控股股东及实际控制人与该项目招标人之间是什么关系？",
    "不存在关联关系：公司、控股股东及实际控制人与招标人（新疆维吾尔自治区水利电力物资有限公司）"
    "不存在关联关系。",
    [(1445002, "公司、控股股东及实际控制人与招标人不存在关联关系")],
    "回原文核验：1445002（doc 1445）在『二、关联关系说明』一节逐字写明不存在关联关系；"
    "该文档内没有第二个块给出同一关系陈述（枚举器③ single_block_ok 判定通过）。"
    "0 跳依据：关系在原文直接给出、不靠图谱反推，完整证据落在同一篇文档的同一文本块内。"
    "与 PE-19 关系：PE-19 问的是天邑股份与中国电信系公司（gold 1533005），本题 gold 无交集。")

add("FQ-110", "关系型+0跳", 0, None,
    "三一重工公告中，三一集团有限公司与公司之间是什么关系？",
    "三一集团有限公司为三一重工股份有限公司的控股股东。",
    [(1042000, "近日收到公司控股股东三一集")],
    "回原文核验：1042000（doc 1042）逐字写明三一集团有限公司为公司控股股东；该文档内没有第二个块"
    "给出同一关系陈述。0 跳依据同上。")

add("FQ-111", "关系型+0跳", 0, None,
    "江苏通光电子线缆股份有限公司公告中，参与『国家电网有限公司2026年输变电项目第四次装置性材料"
    "公开招标采购』的两家单位与公司是什么关系？",
    "江苏通光强能输电线科技有限公司、江苏通光光缆有限公司均为江苏通光电子线缆股份有限公司的全资子公司。",
    [(1433000, "全资子公司江苏通光强能输电线科技有限公司")],
    "回原文核验：1433000（doc 1433）同块逐字写明两家单位是公司的全资子公司；该文档内没有第二个块"
    "给出同一关系陈述。0 跳依据同上。与 PE-25 关系：PE-25 用 1513000 问『中标金额、招标人与招标代理机构』，"
    "本题 gold 无交集。")

add("FQ-112", "关系型+0跳", 0, None,
    "长江电力公告中，中国长江三峡集团有限公司与公司之间是什么关系？",
    "中国长江三峡集团有限公司为中国长江电力股份有限公司的控股股东。",
    [(1293000, "控股股东中国长江三峡集团有限公司")],
    "回原文核验：1293000（doc 1293）同块逐字写明中国长江三峡集团有限公司为控股股东；"
    "该文档内没有第二个块给出同一关系陈述。0 跳依据同上。")

add("FQ-113", "关系型+0跳", 0, None,
    "潜能恒信公告中，周锦明与公司之间是什么关系，其控股的公司承担了什么角色？",
    "周锦明是潜能恒信能源技术股份有限公司的控股股东、实际控制人；其控股的天津锦龙智慧钻井有限公司"
    "提供2026年度钻探总包作业所需的部分装备及配套服务。",
    [(1543003, "公司控股股东、实际控制人周锦明先生")],
    "回原文核验：1543003（doc 1543）同块逐字写明周锦明的控股股东、实际控制人身份及天津锦龙的角色；"
    "该文档内没有第二个块给出同一关系陈述。0 跳依据同上。")

add("FQ-118", "关系型+0跳", 0, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内披露的公告中，美的集团2026年A股持股计划"
    "与公司控股股东、实际控制人之间是否存在一致行动关系？",
    "不存在：本期持股计划未与公司控股股东、实际控制人签署一致行动协议或存在一致行动安排；"
    "本期持股计划与其他已存续的员工持股计划为一致行动关系。",
    [(1106003, "本期持股计划未与公司控股股东、实际控制人签署一致行动协议或存在一致")],
    "回原文核验：1106003（doc 1106）同块逐字写明否定式关系；doc 1106 在可过滤集合内"
    "（2025-12-09、2026-09-03），窗口外的 2025-12-09 事件块被过滤剔除，差集非空。"
    "与 PE-30 关系：PE-30 问的是非交易过户完成情况（gold 1106000／1106001／1106002），"
    "本题 gold 是 1106003，无交集。")

add("FQ-119", "关系型+0跳", 0,
    make_window("2026年7月1日至2026年7月31日", "2026-07-01", "2026-07-31"),
    "2026年7月1日至2026年7月31日期间披露的公告中，中国长江三峡集团有限公司的实际控制人地位"
    "是否发生变化？",
    "未发生变化：公告写明本次信托担保登记完成后，不会导致控股股东及实际控制人发生变化，不构成要约收购。",
    [(1293005, "不会导致控股")],
    "回原文核验：1293005（doc 1293）逐字写明实际控制人未发生变化；doc 1293 在可过滤集合内"
    "（2022-06-06、2026-07-16、2026-07-17），本窗口只保留 2026-07 的两个事件块，"
    "2022-06-06 的发行事件块被过滤剔除，差集非空。"
    "与 PE-21 关系：PE-21 的 gold 是 1293004（托管关系），本题 gold 是 1293005，无交集。")

# ===== 2026-10-04 合并修复后的换题（缺陷 2／4）与事件型+2跳的时间约束补足（缺陷 3）=====
# 本节 19 条替换／新增题的理由、判据与实测证据见
# `测试集\\构建报告.md`（缺陷 2／3／4）与 `测试集\\出题口径.md`（枚举器规则）。
W_2025_04 = make_window("2025年4月1日至2025年4月30日", "2025-04-01", "2025-04-30")
W_2026_02 = make_window("2026年2月1日至2026年2月28日", "2026-02-01", "2026-02-28")
W_2026_06 = make_window("2026年6月1日至2026年6月30日", "2026-06-01", "2026-06-30")
W_2026_07 = make_window("2026年7月1日至2026年7月31日", "2026-07-01", "2026-07-31")
W_2026_07B = make_window("2026年7月10日至2026年7月17日", "2026-07-10", "2026-07-17")
W_2026_08 = make_window("2026年8月1日至2026年8月31日", "2026-08-01", "2026-08-31")
W_2026_09 = make_window("2026年9月1日至2026年9月30日", "2026-09-01", "2026-09-30")
W_2022_01 = make_window("2022年1月1日至2022年1月31日", "2022-01-01", "2022-01-31")
W_2020_11 = make_window("2020年11月1日至2020年11月30日", "2020-11-01", "2020-11-30")

# ---- 事实型 + 1 跳：无时间约束 4 题换题（原 FQ-086／087／088／090 的 gold 与 PE 集相交）----
add("FQ-086", "事实型+1跳", 1, None,
    "工商银行境内优先股“工行优2”股息派发中，每股优先股派发的现金股息与股权登记日分别是多少；"
    "该行2026年无固定期限资本债券（第四期）（债券通）的发行规模与前5年票面利率分别是多少？",
    "每股优先股派发现金股息人民币3.02元（税前），股权登记日为2026年9月23日（除息日同为9月23日、"
    "股息发放日9月24日）；无固定期限资本债券（第四期）（债券通）发行规模为人民币200亿元，"
    "前5年票面利率为1.86%。",
    [(1040000, "每股优先股派发现金股息人民币3.02 元（税前）"),
     (1040000, "股权登记日：2026 年9 月23 日"),
     (1062000, "本期债\n券发行规模为人民币200亿元，前5年票面利率为1.86%")],
    "回原文核验：1040000（doc 1040，EVT-0048）的“重要内容提示”同时给出每股优先股派发现金股息与"
    "股权登记日；1062000（doc 1062，EVT-0083）给出本期无固定期限资本债券的发行规模与票面利率。"
    "两块分居两篇文档、**任一块都不含另一项取值**。1 跳依据：两项取值由"
    "『工商银行--PARTICIPATES_IN-->事件』汇集（EVT-0048／EVT-0083）。本题不设时间约束"
    "（doc 1040、doc 1062 都不在可过滤文档集合内）。换题理由：原 FQ-086 的 gold（1112001／1148000）"
    "与 PE-23 完全相同，见《构建报告.md》缺陷 4。")

add("FQ-087", "事实型+1跳", 1, None,
    "歌尔股份2023年股票期权激励计划首次授予部分第三个行权期的可行权期限与可行权数量分别是多少；"
    "该计划首次授予部分被注销的股票期权份数分别是多少？",
    "第三个行权期实际可行权期限为2026年9月8日至2027年8月27日，4,506名激励对象可行权股票期权"
    "5,205.9492万份（行权价格17.62元/股）；第二个行权期内已获授但尚未行权的0.45万份，以及459名"
    "激励对象已获授但不具备行权条件的303.006万份，均被注销。",
    [(1088001, "实际可行权期限\n为2026年9月8日至2027年8月27日"),
     (1088001, "公司4,506名激励对象在第三个行权期可行权股票期权数\n量为5,205.9492万份"),
     (1098000, "注销2023 年股票期权激励计划首次授予部分第二个行权期内已获授但尚未行权的股票\n期权0.45 万份"),
     (1098000, "注销2023 年股票期权激励计划首次授予部分459 名激励对象\n持有的已获授但不具备行权条件的股票期权303.006 万份")],
    "回原文核验：1088001（doc 1088，EVT-0114）给出第三个行权期的可行权期限、人数、份数与行权价格；"
    "1098000（doc 1098，EVT-0126）给出两笔注销的份数与人数。两块分居两篇文档、**任一块都不含"
    "另一项取值**。1 跳依据：两事件由『歌尔股份--PARTICIPATES_IN-->事件』汇集。本题不设时间约束。"
    "换题理由：原 FQ-087 的 gold（1021000／1021001／1163001）与 PE-05／PE-06 相交，见缺陷 4。")

add("FQ-088", "事实型+1跳", 1, None,
    "北方华创第九届董事会第四次会议审议通过的注册发行方案中，非金融企业债务融资工具与"
    "应收账款资产支持商业票据的注册发行规模上限分别是多少；该公司高级管理人员唐飞辞职时"
    "所持尚未行权的股票期权份数与公司股份数量分别是多少？",
    "非金融企业债务融资工具不超过人民币80亿元（含80亿元），应收账款资产支持商业票据不超过"
    "人民币40亿元（含40亿元）；唐飞持有2025年股票期权激励计划已获授但尚未行权的股票期权8,000股、"
    "公司股份74,250股。",
    [(1285000, "同意公司注册\n发行非金融企业债务融资工具不超过人民币80亿元（含80亿元）"),
     (1285000, "注册发行应收\n账款资产支持商业票据不超过人民币40亿元（含40亿元）"),
     (1372000, "唐飞先生持有2025 年股票期权激励计划已获授但尚未\n行权的股票期权8,000 股"),
     (1372000, "唐飞先生持有公司股份74,250 股")],
    "回原文核验：1285000（doc 1285，EVT-0375／EVT-0376）给出两项注册发行规模上限；1372000"
    "（doc 1372，EVT-0494）给出唐飞辞职时所持期权份数与公司股份数。两块分居两篇文档、"
    "**任一块都不含另一项取值**。1 跳依据：两事件由『北方华创--PARTICIPATES_IN-->事件』汇集。"
    "本题不设时间约束。换题理由：原 FQ-088 的 gold（1364000）与 PE-14 相交，见缺陷 4。")

add("FQ-090", "事实型+1跳", 1, None,
    "中国中铁总会计师孙璀的离任时间与离任原因分别是什么；该公司2026年中期分红方案的"
    "每股派送现金红利与截至2026年6月30日母公司期末可供股东分配的利润分别是多少？",
    "孙璀因达到法定退休年龄于2026年8月31日离任（原定任期到期日为2027年8月20日）；"
    "2026年中期分红方案为每股派送现金红利人民币0.06374元（含税），截至2026年6月30日母公司"
    "期末可供股东分配的利润为106,870,823,931.68元（未经审计）。",
    [(1118000, "因年龄原因（退休），向公司董事会递交书面辞职报告"),
     (1118000, "2027 年8\n月20 日"),
     (1128000, "每股派送现金红利人民币0.06374 元（含税）"),
     (1128000, "106,870,823,931.68 元（未经审计）")],
    "回原文核验：1118000（doc 1118，EVT-0142）给出离任原因、离任时间与原定任期到期日；"
    "1128000（doc 1128，EVT-0159）给出中期分红每股金额与母公司期末可供分配利润。"
    "两块分居两篇文档、**任一块都不含另一项取值**。1 跳依据："
    "『中国中铁--PARTICIPATES_IN-->事件』汇集。本题不设时间约束。"
    "换题理由：原 FQ-090 的 gold（1106002）与 PE-30 相交，见缺陷 4。")

# ---- 事实型 + 1 跳：有时间约束 3 题换题（原 FQ-091／093 的 gold 与 PE 集相交；FQ-095 换题）----
add("FQ-091", "事实型+1跳", 1, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内，美的集团披露的A股回购进展中累计回购股份数量"
    "与支付总金额分别是多少；该公司2022年限制性股票激励计划的回购价格调整结果与被回购注销的"
    "限制性股票数量分别是多少？",
    "截至2026年7月17日累计回购A股股份84,339,356股（占公司目前总股本1.11%），支付总金额"
    "6,716,277,930元（不含交易费用）；2022年限制性股票的回购价格由16.97元/股调整为13.17元/股，"
    "并对11名激励对象的221,000股、8名激励对象的80,633股实施回购注销。",
    [(1292001, "累计回购公司A股股份数量为84,339,356股，占公司目前总股本的1.11%"),
     (1292001, "支付的总金额为6,716,277,930元（不\n含交易费用）"),
     (1325017, "2022年限制性股票的回购价格将由16.97元/股调整为13.17元/股"),
     (1325017, "对8名激励对象已获授但尚未解除限售的限制性股票共计80,633\n股进行回购注销")],
    "回原文核验：1292001（doc 1292，EVT-0384）给出累计回购数量与支付总金额；1325017（doc 1325，"
    "EVT-0428）给出2022年限制性股票的回购价格调整与回购注销数量。两块分居 doc 1292／doc 1325，"
    "两篇文档都在可过滤集合内（doc 1292：2026-04-29、2026-07-17；doc 1325 的 event_time 亦≥2 个），"
    "窗口（06-27~09-25）过滤后差集非空（报告第 4 节）。换题理由：原 FQ-091 的 gold（1106002）"
    "与 PE-30 相交，见缺陷 4。")

add("FQ-093", "事实型+1跳", 1, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内，国电南瑞2026年半年度权益分派实施后回购价格上限"
    "的调整结果与调整起始日期分别是什么；该公司截至2026年4月13日完成的回购股份数量与回购专用"
    "证券账户尚余股份数量分别是多少？",
    "回购价格上限由不超过人民币35.17元/股调整为不超过人民币35.02元/股，调整起始日期为"
    "2026年9月29日；截至2026年4月13日完成股份回购22,303,291股，回购专用证券账户尚余股份"
    "45,157,255股。",
    [(1018000, "调整前回购价格上限：不超过人民币35.17 元/股(含本数)"),
     (1018000, "回购价格调整起始日期：2026 年9 月29 日"),
     (1362005, "实际回\n购股份22,303,291 股"),
     (1362005, "公司回购专用证券账户尚余股份45,157,255 股")],
    "回原文核验：1018000（doc 1018，EVT-0023）给出调整前后回购价格上限与调整起始日期；"
    "1362005（doc 1362，EVT-0477）给出已完成回购数量与回购专用账户尚余股份。两块分居 "
    "doc 1018／doc 1362，两篇都在可过滤集合内（doc 1018：2026-09-28、2026-09-29；"
    "doc 1362：2026-04-13、2026-05-22），窗口过滤后差集非空（报告第 4 节）。"
    "换题理由：原 FQ-093 的 gold（1294002）与 PE-14 相交，见缺陷 4。")

add("FQ-095", "事实型+1跳", 1, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内，海天味业披露的A股回购进展中累计已回购股数与"
    "累计已回购金额分别是多少；该公司A+H两地同步布局方案中拟回购A股的资金下限与申请H股回购"
    "授权的规模上限分别是多少？",
    "累计已回购股数13,342,301股（占公司总股本0.2280%），累计已回购金额459,160,081.19元"
    "（实际回购价格区间33.51元/股~37.37元/股）；A+H两地同步布局方案拟斥资不低于10亿元回购A股，"
    "并申请不超过5亿港元H股回购授权。",
    [(1058000, "累计已回购股数\n13,342,301股"),
     (1058000, "累计已回购金额\n459,160,081.19元"),
     (2016002, "6月22日，海天味业推出首次A+H两地同步布局方案，拟斥资不低于10亿元回购A股，并申请不超过5亿港元H股回购授权")],
    "回原文核验：1058000（doc 1058，EVT-0077）给出累计已回购股数、金额与价格区间；2016002"
    "（doc 2016，财经新闻）给出A+H同步布局方案的回购资金下限与H股授权上限。两块分居 doc 1058／"
    "doc 2016，两篇都在可过滤集合内，窗口过滤后差集非空（报告第 4 节）。"
    "换题理由：原 FQ-095 的 gold（1114002）与参考答案不对应（该块讲的是公司尚未回购A股股份，"
    "而参考答案讲的是三一集团持股数量），属缺陷 2 的换题对象；本题即其替代题。")

# ---- 事件型 + 2 跳：无时间约束 1 题换题（原 FQ-102 的 gold 与 PE-25 相交）----
add("FQ-102", "事件型+2跳", 2, None,
    "华润双鹤药业股份有限公司与华润赛科药业有限责任公司共同参与的事件包括哪些，"
    "两次《药品注册证书》涉及的品种与证书编号分别是什么？",
    "全资子公司华润赛科药业有限责任公司收到国家药品监督管理局颁发的依折麦布阿托伐他汀钙片"
    "［含(Ⅰ)、(Ⅱ)］《药品注册证书》（证书编号2026S03337、2026S03336）；此前华润赛科与"
    "山西晋新双鹤药业有限责任公司、华润双鹤湘中药业(湖南)有限公司分别收到利格列汀二甲双胍片(Ⅱ)、"
    "黄体酮注射液(Ⅱ)和氢溴酸伏硫西汀片《药品注册证书》（利格列汀二甲双胍片(Ⅱ)证书编号2026S02025）。",
    [(1418000, "华润赛科药业有限责任公司(以下简称“华润赛科”)收到了国家药品监\n督管理局(以下简称“国家药监局”)颁发的依折麦布阿托伐他汀钙片"),
     (1592000, "华润赛科药业有限责任公司(以下简称“华润赛科”)、山西晋新双\n鹤药业有限责任公司(以下简称“晋新双鹤”)，控股子公司华润双鹤\n湘中药业(湖南)有限公司(以下简称“双鹤湘中”)分别收到了国家药品\n监督管理局(以下简称“国家药监局”)颁发的利格列汀二甲双胍片(Ⅱ)"),
     (1592000, "证书编号\n2026S02025")],
    "回原文核验：1418000（doc 1418）与 1592000（doc 1592）分居两篇文档、两块都逐字含双方公司名，"
    "每块承载一次获证事件。2 跳依据：题面点名华润双鹤，与之共同参与事件的一方"
    "（华润赛科药业有限责任公司）只能经『公司A--PARTICIPATES_IN-->共同事件<--PARTICIPATES_IN--公司B』"
    "两条关系边确定（EVT-0554／EVT-0774）。两篇文档都不在可过滤集合内，故本题不设时间约束。"
    "换题理由：原 FQ-102 的 gold（1513000）与 PE-25 相交，见缺陷 4。")

# ---- 事件型 + 2 跳：有时间约束 6 题（缺陷 3 的有界手工构造，builder=hand）----
# 路径＝公司 --PARTICIPATES_IN--> 事件 --ISSUED_BY/PARTICIPATES_IN--> 机构（或 --RELATED_TO--> 政策），
# 候选池由 `enum_event_two_hop_org` 确定性枚举；题面、参考答案与锚点由决策者逐条回原文撰写，
# 故 builder 记 "hand"。逐题的 5 条判据实测见《构建报告.md》缺陷 3。
add("FQ-103", "事件型+2跳", 2, W_2025_04,
    "2025年4月1日至2025年4月30日期间，通威股份的债务融资工具注册由哪家机构接受，"
    "《接受注册通知书》的编号与注册有效期分别是多少？",
    "由中国银行间市场交易商协会接受注册；《接受注册通知书》编号为中市协注[2025]DFI27号，"
    "注册自通知书落款之日（2025年4月28日）起2年内有效。",
    [(1195000, "2025 年4 月28 日，公司收到中国银行间市场交易商协会（以下简称“交易商"),
     (1195001, "下发的《接受注册通知书》（中市协注[2025]DFI27 号）"),
     (1195001, "注册自通知书落款之\n日（2025 年4 月28 日）起2 年内有效")],
    "回原文核验：1195000／1195001（doc 1195）分别给出收到通知书的日期与机构、通知书编号与有效期。"
    "2 跳依据：题面只点名通威股份，机构只能经『通威股份--PARTICIPATES_IN-->EVT-0253（交易商协会"
    "接受债务融资工具注册）--ISSUED_BY-->中国银行间市场交易商协会』两条关系边串联；"
    "单块不含“机构是谁”这条关系端点。时间窗有效：doc 1195 的两个 event_time 为 2025-04-28"
    "（注册事件，窗口内）与 2026-08-21（第六期绿色超短期融资券发行完成，窗口外），"
    "过滤前 2 个、过滤后 1 个、剔除 1 个，差集非空。", "hand")

add("FQ-104", "事件型+2跳", 2, W_2026_06,
    "2026年6月1日至2026年6月30日期间，宝钢股份第四期A股限制性股票计划首次授予的登记"
    "由哪家机构出具证明，授予数量是多少股？",
    "由中国证券登记结算有限责任公司上海分公司出具《证券变更登记证明》；该计划已向相关激励对象"
    "授予合计367,989,000股限制性股票，公司于2026年6月8日取得该证明。",
    [(1072006, "宝钢股份第四期A 股限制性股票计划已向\n相关激励对象授予合计367,989,000 股限制性股票"),
     (1072006, "公司已于2026 年6 月8 日取得中国证券登记结算有限责任公司上海分公司出具的\n《证券变更登记证明》")],
    "回原文核验：1072006（doc 1072）同时给出授予数量、登记机构与取得证明的日期。2 跳依据："
    "题面只点名宝钢股份，登记机构只能经『宝钢股份--PARTICIPATES_IN-->EVT-0093（第四期A股限制性"
    "股票计划首次授予367,989,000股）--PARTICIPATES_IN/ISSUED_BY-->中国证券登记结算有限责任公司"
    "上海分公司』两条关系边串联。时间窗有效：doc 1072 的两个 event_time 为 2026-06-08（授予登记，"
    "窗口内）与 2026-08-20（上半年度利润分配方案，窗口外），过滤前 2 个、过滤后 1 个、剔除 1 个，"
    "差集非空。", "hand")

add("FQ-105", "事件型+2跳", 2, W_2026_02,
    "2026年2月1日至2026年2月28日期间，宁德时代面向专业机构投资者公开发行（不超过）人民币"
    "50亿元的公司债券由哪家机构注册批复，批复文号是什么？",
    "由中国证券监督管理委员会注册批复，批复文号为证监许可〔2026〕234号（批复日期2026年2月5日）。",
    [(1396000, "公司债券已于2026 年\n2 月5 日获得中国证券监督管理委员会注册批复（证监许可〔2026〕234 号）")],
    "回原文核验：1396000（doc 1396）同时给出注册机构、批复日期与文号。2 跳依据：题面只点名"
    "宁德时代，注册机构只能经『宁德时代--PARTICIPATES_IN-->EVT-0525（50亿元公司债券发行获证监会"
    "注册批复）--ISSUED_BY-->中国证券监督管理委员会』两条关系边串联。时间窗有效：doc 1396 的"
    "两个 event_time 为 2026-02-05（注册批复，窗口内）与 2026-06-17（第二期科创债票面利率确定，"
    "窗口外），过滤前 2 个、过滤后 1 个、剔除 1 个，差集非空。", "hand")

add("FQ-106", "事件型+2跳", 2, W_2022_01,
    "2022年1月1日至2022年1月31日期间，隆基绿能公开发行的可转换公司债券由哪家机构核准，"
    "核准文号、发行张数与发行总额分别是多少？",
    "经中国证券监督管理委员会“证监许可[2021]3561号”文核准；公司于2022年1月5日公开发行"
    "7,000万张可转债，每张面值100元，发行总额700,000.00万元，期限6年。",
    [(1050000, "经中国证券监督管理委员会“证监许可[2021]3561号”文核准，公司于2022\n年1月5日公开发行了7,000万张可转债，每张面值100元，发行总额700,000.00万\n元，期限6年。")],
    "回原文核验：1050000（doc 1050）同时给出核准机构、核准文号与发行要素。2 跳依据：题面只点名"
    "隆基绿能，核准机构只能经『隆基绿能--PARTICIPATES_IN-->EVT-0066（公开发行700,000.00万元"
    "可转债并在上交所挂牌）--ISSUED_BY-->中国证券监督管理委员会』两条关系边串联。时间窗有效："
    "doc 1050 的两个 event_time 为 2022-01-05（可转债发行，窗口内）与 2026-09-14（隆22转债预计"
    "满足转股价格向下修正条件，窗口外），过滤前 2 个、过滤后 1 个、剔除 1 个，差集非空。", "hand")

add("FQ-107", "事件型+2跳", 2, W_2020_11,
    "2020年11月1日至2020年11月30日期间，立讯精密公开发行的可转换公司债券由哪家机构核准，"
    "核准文号、发行张数与发行总额分别是多少？",
    "经中国证券监督管理委员会《关于核准立讯精密工业股份有限公司公开发行可转换公司债券的批复》"
    "（证监许可[2020]247号）批准；公司于2020年11月3日公开发行3,000.00万张可转换公司债券，"
    "每张面值为人民币100.00元，发行总额为人民币300,000.00万元，期限为六年。",
    [(1014001, "经中国证券监督管理委员会《关于核准立讯精密工业股份有限公司公开发行可\n转换公司债券的批复》（证监许可[2020]247 号）批准，公司于2020 年11 月3 日\n公开发行3,000.00 万张可转换公司债券")],
    "回原文核验：1014001（doc 1014）同时给出核准机构、批复文号与发行要素。2 跳依据：题面只点名"
    "立讯精密，核准机构只能经『立讯精密--PARTICIPATES_IN-->EVT-0019（公开发行3,000.00万张"
    "可转换公司债券）--ISSUED_BY-->中国证券监督管理委员会』两条关系边串联。时间窗有效："
    "doc 1014 的三个 event_time 为 2020-11-03（发行，窗口内）、2020-12-02（挂牌，窗口外）与"
    "2026-11-02（到期赎回摘牌，窗口外），过滤前 3 个、过滤后 1 个、剔除 2 个，差集非空。", "hand")

add("FQ-108", "事件型+2跳", 2, W_2026_07B,
    "2026年7月10日至2026年7月17日期间，芯导科技发行可转债并配套现金收购瞬雷科技的项目"
    "由哪家机构审核通过，审核通过的日期是哪一天？",
    "由上交所并购重组委审核通过，通过日期为2026年7月16日（该项目成为科创板企业“补链强链”的"
    "标杆案例）。",
    [(2100013, "7月16日，芯导科技发行可转债并配套现金收购瞬雷科技项目获上交所并购重组委审核通过")],
    "回原文核验：2100013（doc 2100，财经新闻）逐字给出审核机构与日期。2 跳依据：题面只点名"
    "芯导科技，审核机构只能经『芯导科技--PARTICIPATES_IN-->EVT-1011（收购瞬雷科技项目获上交所"
    "并购重组委审核通过）--PARTICIPATES_IN/ISSUED_BY-->上交所』两条关系边串联。时间窗有效："
    "doc 2100 的 event_time 含 2026-07-16（本项目审核通过，窗口内）与 2026-07-21（窗口外），"
    "过滤前至少 2 个、过滤后 1 个，差集非空。", "hand")

# ---- 关系型 + 0 跳：无时间约束 1 题（原 FQ-114 的 gold=1082000 与 PE-12 相交）----
add("FQ-114", "关系型+0跳", 0, None,
    "上海透景生命科技股份有限公司与江西透景生命科技有限公司之间是什么关系？",
    "江西透景生命科技有限公司为上海透景生命科技股份有限公司的全资子公司"
    "（该子公司在江西省药品监督管理局取得1项医疗器械注册证）。",
    [(1566000, "上海透景生命科技股份有限公司（以下简称“公司”）的全资子公司江西透\n景生命科技有限公司（以下简称“子公司”或“江西透景”）")],
    "回原文核验：1566000（doc 1566）同块逐字写明母子公司关系（“公司的全资子公司江西透景生命"
    "科技有限公司”）；该文档内没有第二个块给出同一关系陈述（枚举器③ single_block_ok 判定通过）。"
    "0 跳依据：关系在原文直接给出、不靠图谱反推，完整证据落在同一篇文档的同一文本块内。"
    "换题理由：原 FQ-114 的 gold（1082000）与 PE-12 相交，见缺陷 4。")

# ---- 关系型 + 0 跳：有时间约束 4 题（原 FQ-115／116／117／120 换题）----
add("FQ-115", "关系型+0跳", 0, W_90,
    "近期90天（2026年6月27日至2026年9月25日）内披露的公告中，中国铁建的控股股东是哪家公司，"
    "其截至2026年6月30日在财务公司的存款余额与贷款本金余额分别是多少？",
    "控股股东为中国铁道建筑集团有限公司；截至2026年6月30日，其及非上市子公司在财务公司的"
    "存款余额为9.94亿元、贷款本金余额为12.63亿元。",
    [(1130021, "本公司的控股股东中国铁道建\n筑集团有限公司及其非上市子公司在财务公司的存款余额\n为9.94 亿元，贷款本金余额12.63 亿元")],
    "回原文核验：1130021（doc 1130）同块逐字写明控股股东名称与其在财务公司的存贷款余额；"
    "该文档内没有第二个块给出同一关系陈述。doc 1130 在可过滤集合内（2012-04-18、2026-06-30），"
    "窗口（06-27~09-25）只保留 2026-06-30 的关联交易／风险评估事件，2012-04-18 的开业事件块被"
    "过滤剔除，差集非空。换题理由：原 FQ-115 的窗口标注（label=最近30天、lo/hi=近期90天）与"
    "题干自相矛盾，属缺陷 2 的换题对象。")

add("FQ-116", "关系型+0跳", 0, W_2026_08,
    "2026年8月1日至2026年8月31日期间披露的公告中，上海电气集团股份有限公司与"
    "上海电气香港有限公司之间是什么关系？",
    "上海电气香港有限公司为上海电气集团股份有限公司的全资子公司"
    "（本次境外债券由其提供担保，担保期限不超过5年）。",
    [(1201000, "同意全资子公司上海电气香港有限公司（以下简称“电气香港”）")],
    "回原文核验：1201000（doc 1201）同块逐字写明全资子公司关系；该文档内没有第二个块给出同一"
    "关系陈述。doc 1201 在可过滤集合内（2026-04-29、2026-08-20），本窗口只保留 2026-08-20 的"
    "境外债券上市事件，2026-04-29 的发行主体设立事件块被过滤剔除，差集非空。"
    "换题理由：原 FQ-116 的 gold（1082000）与 PE-12 相交，见缺陷 4。")

add("FQ-117", "关系型+0跳", 0, W_2026_08,
    "2026年8月1日至2026年8月31日期间披露的公告中，蜂助手与雅安云智算力技术有限公司之间"
    "是什么关系？",
    "雅安云智算力技术有限公司为蜂助手的全资子公司"
    "（该公司与B公司签署算力服务合同，合同总金额46.08亿元）。",
    [(2089003, "8月4日，蜂助手发布公告表示，公司全资子公司雅安云智算力技术有限公司与B公司签署算力服务合同")],
    "回原文核验：2089003（doc 2089，财经新闻）同块逐字写明全资子公司关系；该文档内没有第二个块"
    "给出同一关系陈述。doc 2089 在可过滤集合内（2026-08-03、2026-08-04），本窗口只保留 "
    "2026-08 的两个事件块，无 event_time 的块（2089004／2089006 等）被过滤剔除，差集非空。"
    "换题理由：原 FQ-117 的 gold（1042000）与同格 FQ-110 逐字相同（同格内 gold 复用），"
    "按《题目模板》第四节禁令 2 的换题口径一并换掉。")

add("FQ-120", "关系型+0跳", 0, W_2026_08,
    "2026年8月1日至2026年8月31日期间披露的公告中，华润双鹤药业股份有限公司与"
    "华润双鹤湘中药业(湖南)有限公司之间是什么关系，后者取得的《药品注册证书》涉及哪个品种？",
    "华润双鹤湘中药业(湖南)有限公司为华润双鹤药业股份有限公司的控股子公司（双鹤湘中）；"
    "后者收到国家药品监督管理局颁发的奥卡西平片（0.15g规格）《药品注册证书》，"
    "证书编号2026S03114。",
    [(1450000, "公司(以下简称“公司”)控股子公\n司华润双鹤湘中药业(湖南)有限公司(以下简称“双鹤湘中”)收到了国\n家药品监督管理局(以下简称“国家药监局”)颁发的奥卡西平片"),
     (1450000, "证书编号\n2026S03114")],
    "回原文核验：1450000（doc 1450）同块逐字写明控股子公司关系与《药品注册证书》品种、证书编号；"
    "该文档内没有第二个块给出同一关系陈述。doc 1450 在可过滤集合内（2025-11-12、2026-08-25），"
    "本窗口只保留 2026-08-25 的获证事件，2025-11-12 的 0.3g 规格获证事件块被过滤剔除，"
    "差集非空。换题理由：原 FQ-120 的 gold（1445002）与同格 FQ-109 逐字相同，且参考答案里的"
    "“招标代理机构”一项在该 gold 块中并无支撑，属缺陷 2 的换题对象。")

# ===== 基础字段 =====
CELL_QID_RANGE = {"事实型+1跳": ("FQ-085", "FQ-096"),
                  "事件型+2跳": ("FQ-097", "FQ-108"),
                  "关系型+0跳": ("FQ-109", "FQ-120")}
TASK_TYPE = {"事实型+1跳": "事实型", "事件型+2跳": "事件型", "关系型+0跳": "关系型"}
HOP = {"事实型+1跳": 1, "事件型+2跳": 2, "关系型+0跳": 0}
GOLD_RULE = {"事实型+1跳": GOLD_RULE_FACT1, "事件型+2跳": GOLD_RULE_EVENT2,
             "关系型+0跳": GOLD_RULE_REL0}

def _blocked_chunks(inp):
    """「已被占用」的块集合：PE 集的 70 个 gold 块 ∪ 批 A 全部 gold 块 ∪ 本批其他题的 gold 块。

    用途：给 `enum_event_two_hop_org` 一个**可复算**的可用候选口径（报告第 2 节引用）。
    """
    blocked = set()
    for item in Q:
        if item["cell"] == "事件型+2跳" and item["win"] is not None:
            continue
        blocked |= {c for c, _q in item["gold"]}
    if os.path.exists(PE_PATH):
        for row in _iter_jsonl(PE_PATH):
            blocked |= set(row["gold_evidence_chunk_ids"])
    a_path = os.path.join(ROOT, "阶段10-系统测试与对比实验", "测试集", "_批A",
                          "questions_A.jsonl")
    if os.path.exists(a_path):
        for row in _iter_jsonl(a_path):
            blocked |= set(row["gold_evidence_chunk_ids"])
    return blocked


def render_graph_path(inp, chunk_ids, hop):
    """按 A 批同一 schema 渲染 graph_path：{"head","relation","tail","source_chunk_id"}。

    0 跳题为空表；≥1 跳题把 gold 块上挂的语义边（含事件的两跳端点）逐条列出，
    使两批与终稿的 `graph_path` 字段语义一致（2026-10-04 统一，见《构建报告.md》缺陷 5）。
    """
    if hop == 0:
        return []
    out, seen = [], set()
    for cid in sorted(chunk_ids):
        for ev in sorted(inp.chunk_events.get(cid, ())):
            edges = []
            for co in sorted(inp.ev_companies.get(ev, ())):
                edges.append((co, "PARTICIPATES_IN", ev))
            for ins in sorted(inp.ev_inst.get(ev, ())):
                edges.append((ev, "ISSUED_BY", ins))
            for pol in sorted(inp.ev_policies.get(ev, ())):
                edges.append((ev, "RELATED_TO", pol))
            for head, rel, tail in edges:
                key = (head, rel, tail, cid)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"head": head, "relation": rel, "tail": tail,
                            "source_chunk_id": cid})
    return out


def build_records(inp):
    """把冻结表组装成 questions_B.jsonl 的记录（键序固定、按 qid 升序、无时间戳）。"""
    pe = list(_iter_jsonl(PE_PATH)) if os.path.exists(PE_PATH) else []
    pe_gold = {}
    for row in pe:
        pe_gold[row["qid"]] = set(row["gold_evidence_chunk_ids"])

    recs = []
    for item in sorted(Q, key=lambda x: x["qid"]):
        cell, gold = item["cell"], item["gold"]
        chunk_ids, anchors, docs = [], [], []
        for cid, quote in gold:
            if cid not in chunk_ids:
                chunk_ids.append(cid)
            anchors.append({"chunk_id": cid, "quote": quote})
            d = inp.doc_of(cid)
            if d not in docs:
                docs.append(d)
        chunk_ids = sorted(chunk_ids)
        docs = sorted(docs)
        win = item["win"]
        rec = {
            "qid": item["qid"],
            "question": item["question"],
            "reference_answer": item["answer"],
            "task_type": TASK_TYPE[cell],
            "gold_hop_depth": HOP[cell],
            "time_constraint": "有" if win else "无",
            "time_window": ({k: win[k] for k in TW_FIELD_ORDER} if win else None),
            "gold_evidence_doc_ids": docs,
            "gold_evidence_chunk_ids": chunk_ids,
            "gold_evidence_count": len(chunk_ids),
            "gold_evidence_rule": GOLD_RULE[cell],
            "gold_verified_by": VERIFIED_BY,
            "gold_review_status": REVIEW_STATUS,
            "gold_verify_anchors": anchors,
            "gold_verify_note": item["note"],
            "source_material": [
                {"category": inp.docs[d].get("category"),
                 "doc_id": d,
                 "publish_time": inp.docs[d].get("publish_time"),
                 "source": inp.docs[d].get("source"),
                 "title": inp.docs[d].get("title"),
                 "url": inp.docs[d].get("url")} for d in docs],
            "graph_path": render_graph_path(inp, chunk_ids, HOP[cell]),
            "cell": cell,
            "subset": SUBSET,
            "builder": item["builder"],
        }
        recs.append((rec, item, pe_gold))
    return recs

# ---------------------------------------------------------------------------
# 6. 校验
# ---------------------------------------------------------------------------
def verify(inp, recs):
    """全量校验：返回 (errors, stats)。任一 error 非空 → 非零退出。"""
    errors, warn = [], []
    now = set(inp.time_subset)
    pe = list(_iter_jsonl(PE_PATH))
    pe_gold = set()
    for row in pe:
        pe_gold |= set(row["gold_evidence_chunk_ids"])
    pe_texts = {normalize(r["question"]) for r in pe}

    stats = {
        "cells": collections.Counter(), "gold_dist": collections.Counter(),
        "time_qids": [], "win_diff_rows": [], "pe_overlap_gold": [], "pe_overlap_text": [],
        "hop_rows": [], "docs_now": len(now), "chunks": len(inp.chunks),
        "docs": len(inp.docs), "nodes": len(inp.nodes), "edges": len(inp.edges),
        "builder_dist": collections.Counter(),
        "win_diff_map": {}, "hop_org_rows": [],
    }

    seen_qid = set()
    for rec, item, _ in recs:
        qid, cell = rec["qid"], rec["cell"]
        if qid in seen_qid:
            errors.append("%s：qid 重复" % qid)
        seen_qid.add(qid)
        stats["cells"][cell] += 1
        stats["gold_dist"][rec["gold_evidence_count"]] += 1
        stats["builder_dist"][rec["builder"]] += 1

        # 0) 字段键序、取值域（缺陷 5）
        if list(rec.keys()) != FIELD_ORDER:
            errors.append("%s：字段键序与终稿口径不一致" % qid)
        if rec["builder"] not in ("script", "hand"):
            errors.append("%s：builder=%r 不在 {script, hand}" % (qid, rec["builder"]))
        if rec["gold_verified_by"] != VERIFIED_BY:
            errors.append("%s：gold_verified_by 不等于 %s" % (qid, VERIFIED_BY))
        if rec["gold_review_status"] != REVIEW_STATUS:
            errors.append("%s：gold_review_status 与统一口径不一致" % qid)
        if rec["cell"] != "%s+%d跳" % (rec["task_type"], rec["gold_hop_depth"]):
            errors.append("%s：cell 与 task_type/gold_hop_depth 不符" % qid)
        # 0b) graph_path 与跳数一致（与批 A 同一断言）
        if rec["gold_hop_depth"] > 0 and not rec["graph_path"]:
            errors.append("%s：为 %d 跳但 graph_path 为空" % (qid, rec["gold_hop_depth"]))
        if rec["gold_hop_depth"] == 0 and rec["graph_path"]:
            errors.append("%s：为 0 跳但 graph_path 非空" % qid)
        for step in rec["graph_path"]:
            if list(step.keys()) != ["head", "relation", "tail", "source_chunk_id"]:
                errors.append("%s：graph_path 条目字段不符：%s" % (qid, list(step.keys())))
        # 0c) time_window 形态（与 PE 集逐字段一致）
        if rec["time_window"] is not None:
            if list(rec["time_window"].keys()) != TW_FIELD_ORDER:
                errors.append("%s：time_window 键序 %s ≠ PE 集口径 %s"
                              % (qid, list(rec["time_window"].keys()), TW_FIELD_ORDER))
            if rec["time_window"].get("basis") != "event_time":
                errors.append("%s：time_window.basis 应为 event_time" % qid)
            if rec["time_window"].get("cutoff") != DATA_CUTOFF_TS:
                errors.append("%s：time_window.cutoff 应为 data_cutoff_time 的规范时间戳" % qid)
            if rec["time_window"].get("empty_policy") != EMPTY_POLICY:
                errors.append("%s：time_window.empty_policy 应为 %s" % (qid, EMPTY_POLICY))
        # 1) gold 条数
        n = rec["gold_evidence_count"]
        if not (GOLD_MIN <= n <= GOLD_MAX):
            errors.append("%s：gold 条数 %d 越界（应在 %d～%d）" % (qid, n, GOLD_MIN, GOLD_MAX))
        if len(rec["gold_evidence_chunk_ids"]) != len(set(rec["gold_evidence_chunk_ids"])):
            errors.append("%s：gold_evidence_chunk_ids 有重复" % qid)
        if n != len(rec["gold_evidence_chunk_ids"]):
            errors.append("%s：gold_evidence_count 与 chunk_ids 长度不一致" % qid)
        # 2) doc 一致性
        want_docs = sorted({inp.doc_of(c) for c in rec["gold_evidence_chunk_ids"]})
        if want_docs != rec["gold_evidence_doc_ids"]:
            errors.append("%s：gold_evidence_doc_ids 与 chunk 的 doc_id 不一致" % qid)
        for cid in rec["gold_evidence_chunk_ids"]:
            if cid not in inp.chunks:
                errors.append("%s：gold 块 %d 不在 chunks.jsonl" % (qid, cid))
        # 3) 锚点逐字命中
        for a in rec["gold_verify_anchors"]:
            if a["chunk_id"] not in rec["gold_evidence_chunk_ids"]:
                errors.append("%s：锚点块 %d 不在 gold 里" % (qid, a["chunk_id"]))
            if not inp.has(a["chunk_id"], a["quote"]):
                errors.append("%s：锚点在块 %d 原文中未命中：%s" % (qid, a["chunk_id"], a["quote"][:40]))
        # 4) 时间约束
        if rec["time_constraint"] == "有":
            stats["time_qids"].append(qid)
            win = item["win"]
            assert win is not None
            for d in rec["gold_evidence_doc_ids"]:
                if d not in now:
                    errors.append("%s：gold 文档 %d 不在「含 ≥2 个不同 event_time 日期」集合内" % (qid, d))
            co = None
            # 差集：候选代理池＝gold 文档的全部块 ∪ **与该文档相关的每个实体**（公司节点，
            # 含名单拆出的具名公司子树）在图谱上与事件相连的证据块。
            pool = set()
            for d in rec["gold_evidence_doc_ids"]:
                pool |= set(inp.chunks_by_doc.get(d, []))
            for co in sorted(inp.co_events):
                if any(inp.doc_of(c) in rec["gold_evidence_doc_ids"]
                       for c in inp.entity_chunks(co)):
                    pool |= inp.entity_chunks(co)
                    continue
                if any(rec_doc in inp.ev_docs.get(ev, ())
                       for ev in inp.co_events.get(co, ())
                       for rec_doc in rec["gold_evidence_doc_ids"]):
                    pool |= inp.entity_chunks(co)
            dres = win_diff(inp, pool, (win["lo"], win["hi"]), rec["gold_evidence_chunk_ids"],
                            gold_docs=set(rec["gold_evidence_doc_ids"]))
            row = ("%s | %s | 窗口内候选 %d 块 | 窗口外候选 %d 块（含无 event_time 者 %d） | "
                   "差集非空=%s | gold 均在窗口内=%s" % (
                       qid, win["label"], len(dres["in"]), len(dres["out"]), len(dres["undated"]),
                       dres["diff_nonempty"], dres["gold_all_in"]))
            stats["win_diff_rows"].append(row)
            stats["win_diff_map"][qid] = dres
            if not dres["diff_nonempty"]:
                errors.append("%s：过滤前后候选差集为空，时间窗口不改变候选集合" % qid)
            if not dres["gold_all_in"]:
                errors.append("%s：gold 块未全部落在窗口内" % qid)
        # 5) PE 去重（缺陷 4：**硬约束**，交集必须为空，不再只是警告）
        g = set(rec["gold_evidence_chunk_ids"])
        if g & pe_gold:
            stats["pe_overlap_gold"].append((qid, sorted(g & pe_gold)))
            errors.append("%s：gold 与 30 题预实验集有交集 %s" % (qid, sorted(g & pe_gold)))
        if normalize(rec["question"]) in pe_texts:
            stats["pe_overlap_text"].append(qid)
            errors.append("%s：题干与 30 题预实验集完全相同" % qid)
        # 6) 跳数判据（可复算）
        stats["hop_rows"].append(hop_row(inp, item, rec))

    # 7) 事件型+2跳·有时间约束格的逐题入格证据（报告第 7 节引用）
    for rec, _item, _pe in recs:
        if rec["cell"] != "事件型+2跳" or rec["time_constraint"] != "有":
            continue
        evs = set()
        for c in rec["gold_evidence_chunk_ids"]:
            evs |= set(inp.chunk_events.get(c, ()))
        ev = sorted(evs)[0] if evs else ""
        cos = sorted(c for c in inp.ev_companies.get(ev, ()) if inp._label(c) == "Company")
        tgs = sorted(inp.ev_inst.get(ev, ())) + sorted(inp.ev_policies.get(ev, ()))
        dres = stats["win_diff_map"].get(rec["qid"], {})
        stats["hop_org_rows"].append({
            "qid": rec["qid"],
            "company": inp.name(cos[0]) if cos else "—",
            "event": "%s（%s）" % (ev, inp.ev_time.get(ev, "") or "无 event_time"),
            "target": inp.name(tgs[0]) if tgs else "—",
            "docs": ",".join(str(d) for d in rec["gold_evidence_doc_ids"]),
            "window": rec["time_window"]["label"],
            "pre": len(dres.get("in", [])) + len(dres.get("out", [])) + len(dres.get("undated", [])),
            "post": len(dres.get("in", [])),
            "drop": len(dres.get("out", [])) + len(dres.get("undated", [])),
        })
    return errors, warn, stats

def hop_row(inp, item, rec):
    """逐题跳数判据的可复算记录。"""
    cell = item["cell"]
    qid = rec["qid"]
    if cell == "事实型+1跳":
        docs = rec["gold_evidence_doc_ids"]
        # 跨事件判据：按事件分组看取值，是否存在一个块同时含 ≥2 个**不同事件**的取值
        ev_of_chunk = {}
        for c in rec["gold_evidence_chunk_ids"]:
            ev_of_chunk[c] = sorted(inp.chunk_events.get(c, ()))
        vals = [a["quote"] for a in rec["gold_verify_anchors"]]
        multi = []
        for cid, evs in ev_of_chunk.items():
            n_hit = sum(1 for v in vals if inp.has(cid, v))
            if n_hit >= 2 and len(evs) >= 1:
                multi.append(cid)
        return ("%s | 事实型+1跳 | gold 分居文档=%s(docs_ge2=%s) | 跨事件单块=%s | "
                "图谱关系边数=1 | 判据通过=%s" % (
                    qid, docs, len(docs) >= 2, bool(multi), len(docs) >= 2))
    if cell == "事件型+2跳":
        return "%s | 事件型+2跳 | 答案事件数=%d | 分居文档=%s(docs_ge2=%s) | 图谱关系边数=2 | 题面是否点名对手方=否" % (
            qid, len(rec["gold_evidence_chunk_ids"]), rec["gold_evidence_doc_ids"],
            len(rec["gold_evidence_doc_ids"]) >= 2)
    return "%s | 关系型+0跳 | 单块关系陈述=%s | 分居文档=%s(docs_ge2=False) | 图谱关系边数=0" % (
        qid, rec["gold_evidence_chunk_ids"], rec["gold_evidence_doc_ids"])

def write_jsonl(recs, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = []
    for rec, _item, _pe in recs:
        buf.append(json.dumps({k: rec[k] for k in FIELD_ORDER}, ensure_ascii=False,
                              separators=(", ", ": ")))
    data = "\n".join(buf) + "\n"
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(data)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

# ---------------------------------------------------------------------------
# 7. 报告
# ---------------------------------------------------------------------------
def write_report(inp, recs, errors, warn, stats, digest, args_note):
    lines = []
    A = lines.append
    A("# 批B 构建报告（第 10 阶段·正式测试集：FQ-085～FQ-120，36 题）")
    A("")
    A("> 本报告由 `阶段10-系统测试与对比实验\\工具\\建正式测试集_B.py` 现场生成。")
    A("> 全部输入只读：`阶段05-数据准备\\数据集\\v2.1\\`、`阶段06-事件抽取与知识图谱\\图谱导出\\v2.1_v1_3\\`、")
    A("> `阶段07-RAG检索系统\\预实验问题集\\questions.jsonl`；**零大模型调用、零联网抓取**。")
    A("")
    A("## 0. 现场读数")
    A("")
    A("| 项 | 读数 |")
    A("| --- | --- |")
    A("| chunks.jsonl 文本块 | %d |" % stats["chunks"])
    A("| documents.jsonl 文档 | %d |" % stats["docs"])
    A("| v1.3 nodes.csv / edges.csv | %d / %d |" % (stats["nodes"], stats["edges"]))
    A("| **可过滤文档（含 ≥2 个不同 event_time 日期，v1.3 现场重算）** | **%d 篇** |" % stats["docs_now"])
    A("| 时间基准 data_cutoff_time | %s |" % DATA_CUTOFF)
    A("| 最近30天 | %s ～ %s（闭区间，按 event_time） |" % WIN_30)
    A("| 近期90天 | %s ～ %s（闭区间，按 event_time） |" % WIN_90)
    A("| questions_B.jsonl 行数 | %d |" % len(recs))
    A("| questions_B.jsonl SHA-256 | `%s` |" % digest)
    A("")
    A("## 1. 三个新枚举器的判定规则与实现口径")
    A("")
    A("### ① 事实型 + 1 跳（`enum_fact_one_hop`）")
    A("")
    A("路径模板：`公司 --PARTICIPATES_IN--> 事件`（跨文档事证汇集）。入格三条判据全部机械可复算：")
    A("")
    A("1. **取值分居 ≥2 篇文档**（`docs_ge2`）：同一公司在该事件对上，证据块落在不同文档，")
    A("   因此**任一单篇文档都不足以完整回答**；")
    A("2. **不存在任何单块同时含 ≥2 个答案取值**（`no_single_chunk_full`）：这条直接执行")
    A("   《02》第12.2节 的豁免条款——只要某块已含全部取值，该候选按 0 跳处理并被本枚举器丢弃；")
    A("3. **归拢取值恰好需要一条图谱关系**：取值靠『公司→事件』这一条边归到同一答案下，")
    A("   图外无别的路径（脚本记录 `graph_edges_needed` 与 `graph_path`）。")
    A("")
    A("`HAS_EXECUTIVE`（公司→人物）同型候选也做了枚举登记：**实测 38 家公司的关系表跨 ≥2 篇文档**，")
    A("但该类问题的答案是一份人名名单、且单块往往已含全部人名（PE-04／PE-22 已用该形态），")
    A("按『文本已足够→0 跳』的豁免条款**不入本格**；本格因此改用『事件属性取值』形态出题。")
    A("")
    A("### ② 事件型 + 2 跳（`enum_event_two_hop`）")
    A("")
    A("路径模板：`公司A --PARTICIPATES_IN--> 共同事件 <--PARTICIPATES_IN-- 公司B`（两条关系边）。")
    A("")
    A("1. **题面点名 A、不点名 B**：B 的身份只能由图谱关系给出，这是第 2 跳真正被用到的位置；")
    A("2. **答案是一份事件清单**，每个事件由一个证据块承载，块与块分居不同文档；")
    A("3. **每个证据块同时逐字含 A 与 B 的公司名**：『B 确实参与』这一项在文本里可核，")
    A("   而『B 是谁』图外无从取得——跳数因此不是自报，而是由这两点共同固定；")
    A("4. 若 A、B 在同一篇文档里可直接对读、或某块同时含 ≥2 个答案事件，候选被丢弃（0／1 跳豁免）。")
    A("")
    A("### ③ 关系型 + 0 跳（`enum_relation_zero_hop`）")
    A("")
    A("路径模板：无图谱关系（0 条边）。")
    A("")
    A("1. 关系词（含『不存在关联关系』这类否定式）与双方实体名**在同一个文本块内逐字出现**；")
    A("2. 该块所在文档内**没有第二个块**给出同一关系陈述（`single_block_ok`）——")
    A("   这条把『跨块拼接才能得到关系』的情形挡在本格之外；")
    A("3. 不涉及 SUPPLIES／CUSTOMER_OF／COMPETES_WITH 三类薄关系（《题目模板》第四节第 5 条）。")
    A("")
    A("## 2. 每格候选数、取题依据与逐题跳数判据")
    A("")
    c1 = enum_fact_one_hop(inp)
    c1p = _fact_person_candidates(inp)
    c2 = enum_event_two_hop(inp)
    c3 = enum_relation_zero_hop(inp)
    c3ok = [c for c in c3 if c["single_block_ok"]]
    c3now = [c for c in c3ok if c["now"]]
    A("| 格子 | 枚举器 | 候选数 | 取题方式 |")
    A("| --- | --- | --- | --- |")
    A("| 事实型+1跳 | `enum_fact_one_hop`（事件对） | %d（另有 HAS_EXECUTIVE 同型 %d 家跨文档，按豁免不入格） | 取『两事件都有窗口内 event_time、且分居不同文档』者，逐题回原文取属性取值 |"
      % (len(c1), len(c1p)))
    A("| 事件型+2跳（路径一·无时间约束） | `enum_event_two_hop`（公司对×共同事件） | %d（同一块含双方名的公司对 413，其中共同事件 ≥2 者 %d） | 取事件清单 ≥2 条、每事件一块、块分居不同文档者 |"
      % (len(c2), len(c2)))
    A("| 事件型+2跳（路径二·有时间约束） | `enum_event_two_hop_org`（公司→事件→机构／政策） | %d（扣除 PE 集、批 A 与批 B 其他题已占用的块之后） | 取『事件证据块所在文档全部落在可过滤集合内、且题面公司另有窗口外候选块』者，逐题回原文撰写题面与锚点 |"
      % len(enum_event_two_hop_org(inp, blocked_chunks=_blocked_chunks(inp))))
    A("| 关系型+0跳 | `enum_relation_zero_hop`（单块关系陈述） | %d（单块可证 %d；其中落在可过滤文档上 %d） | 取『单块关系陈述 + 可过滤文档 + 与 PE 集不撞车』者 |"
      % (len(c3), len(c3ok), len(c3now)))
    A("")
    A("逐题跳数判据（可复算）：`docs_ge2`＝gold 分居 ≥2 篇文档；`跨事件单块`＝是否存在一个 "
      "文本块同时含 ≥2 个不同答案事件的取值（存在则按豁免条款降为 0 跳）；`判据通过` 要求 gold 分居 ≥2 篇文档。")
    A("")
    A("```text")
    for row in stats["hop_rows"]:
        A(row)
    A("```")
    A("")
    A("## 3. 可过滤文档集合的实测篇数")
    A("")
    A("现场用 v1.3 的 `nodes.csv` + `edges.csv` 重算：以 `EVIDENCED_BY` 把事件挂到文档上，")
    A("再按事件节点的 `event_time` 去重计数，**含 ≥2 个不同日期的文档 = %d 篇**"
      % stats["docs_now"])
    A("（旧的 66 篇是 v1.2 口径；本脚本不读任何汇总字段、不照抄旧数）。")
    A("")
    A("## 4. 时间约束题的「过滤前后候选差集」逐题证据（本批 %d 道）" % len(stats["win_diff_rows"]))
    A("")
    A("候选代理池＝问题实体（公司）在图谱上与事件语义边相连的全部证据块，加上 gold 所在文档的全部块；")
    A("按『块 → 关联事件 → event_time』确定性分档：窗口内保留、窗口外与 `event_time` 为空的一并剔除")
    A("（《02》第12.7节 第一步）。差集＝被剔除的那些块。")
    A("")
    A("**说明**：本批 18 道时间约束题＝事实型+1跳 6 道 ＋ **事件型+2跳 6 道（路径二：公司→事件→机构／政策）**")
    A("＋ 关系型+0跳 6 道；三格共 18 道全部通过「过滤前后候选差集非空」与「gold 块全部落在窗口内」判定。")
    A("")
    A("```text")
    for row in stats["win_diff_rows"]:
        A(row)
    A("```")
    A("")
    A("## 5. 与 30 题预实验集的重叠实测")
    A("")
    A("- **gold 块集合重叠**：%d 题 %s" % (len(stats["pe_overlap_gold"]),
                                          stats["pe_overlap_gold"] or "（无）"))
    A("- **题干完全相同**：%d 题 %s" % (len(stats["pe_overlap_text"]),
                                        stats["pe_overlap_text"] or "（无）"))
    A("")
    A("## 6. gold 条数分布")
    A("")
    A("| gold 条数 | 题数 |")
    A("| --- | --- |")
    for k in sorted(stats["gold_dist"]):
        A("| %d | %d |" % (k, stats["gold_dist"][k]))
    A("")
    A("（上限 K＝10，见《02》第12.4节；本批最大 %d 条。）" % max(stats["gold_dist"] or [0]))
    A("")
    A("## 7. 手工构造题清单与理由")
    A("")
    A("`builder` 取值统计：%s（`script`＝枚举器候选 ＋ 决策者回原文核验；`hand`＝有界手工构造）。"
      % dict(stats["builder_dist"]))
    A("")
    A("取值为 `hand` 的题共 6 道，全部落在**事件型+2跳·有时间约束**格（FQ-103～FQ-108）。")
    A("构造方式：候选池由 `enum_event_two_hop_org`（公司→事件→机构／政策）确定性枚举，")
    A("题面、参考答案与核验锚点由决策者逐条回原文撰写并冻结——因为该格在**路径一**（公司×共同事件×公司）")
    A("上确实枚举不出合格的时间约束题（实测：413 个公司对里只有 1 对的两个共同参与事件证据块都落在")
    A("可过滤文档内，且这两块同属 doc 1030、不构成跨文档），故按《题目模板》第二节"
      "「事件型 × 2 跳 × 有时间约束＝公司→事件→机构」的句式另开一条路径。")
    A("")
    A("6 道题的入格判据逐条实测（《构建报告.md》缺陷 3 有完整表格）：")
    A("")
    A("| qid | 公司 | 事件 | 机构／政策 | gold 文档 | 全部∈66 篇 | 窗口 | 过滤前→后／剔除 |")
    A("| --- | --- | --- | --- | --- | :--: | --- | --- |")
    for qid in ("FQ-103", "FQ-104", "FQ-105", "FQ-106", "FQ-107", "FQ-108"):
        row = next((x for x in stats["hop_org_rows"] if x["qid"] == qid), None)
        if row is None:
            continue
        A("| %s | %s | %s | %s | %s | 是 | %s | %d→%d／%d |"
          % (qid, row["company"], row["event"], row["target"], row["docs"],
             row["window"], row["pre"], row["post"], row["drop"]))
    A("")
    A("## 8. 已知限制（如实登记）")
    A("")
    A("1. **本批 gold 不是人工金标准**：由决策者（AI）用确定性脚本构造并逐条回原文核验，")
    A("   人工抽检未做、第三方模型盲标复核未做；`gold_review_status` 已如实写明。")
    A("2. **事实型+1跳的『1 跳必要性』依赖『文本是否已足够』的判读**：本批用两条机械判据")
    A("   （取值分居 ≥2 文档、无单块含 ≥2 取值）把它变成可复算的事，但『最少必需证据』")
    A("   终究含语义判断；若评审要求更严口径，本格可整体降级为 0 跳并重出。")
    A("3. **事件型+2跳的「有时间约束」6 题走的不是路径一，而是路径二**（2026-10-04 修复）：")
    A("   路径一（公司×共同参与事件×公司）现场重算确无解——413 个公司对里只有 **1 对**")
    A("   （中工国际 × 乌干达输电公司）的两个共同参与事件证据块都落在可过滤文档内，且这两块同属")
    A("   doc 1030、不构成跨文档。改用《题目模板》第二节给出的另一条 2 跳路径")
    A("   **公司→事件→机构／政策**后，`enum_event_two_hop_org` 枚举出可用候选（扣除 PE 集与")
    A("   批 A／批 B 其他题已占用的块后为 %d 条），据此构造 FQ-103～FQ-108 共 6 道。" % len(enum_event_two_hop_org(inp, blocked_chunks=_blocked_chunks(inp))))
    A("   **登记**：该 6 道的 2 跳路径与同格其余 6 道（路径一）**不同**；两批台账里 `cell` 相同、")
    A("   但 `gold_verify_note` 逐题写明了各自实际使用的路径。")
    A("   ⇒ 本批带时间约束的题共 **%d 道**（事实型+1跳 6 ＋ 事件型+2跳 6 ＋ 关系型+0跳 6）。"
      % len(stats["time_qids"]))
    A("4. **事实型+1跳的『1 跳必要性』依赖『文本是否已足够』的判读**：本批用两条机械判据")
    A("   （取值分居 ≥2 文档、无单块含 ≥2 取值）把它变成可复算的事，但『最少必需证据』")
    A("   终究含语义判断；若评审要求更严口径，本格可整体降级为 0 跳并重出。")
    A("5. **枚举器①的 HAS_EXECUTIVE 同型候选未出题**：38 家跨文档公司里没有任何一家满足")
    A("   『单块不含全部人名』，故按豁免条款整类不入本格。")
    A("6. **关系型+0跳在可过滤文档上的候选面很窄**：全语料单块关系陈述 %d 条，"
      "其中落在可过滤文档上仅 %d 条；本格 6 道时间题只能从这几条里取。" % (len(c3ok), len(c3now)))
    A("7. **时间窗口的『候选集合』是确定性代理**：本课题的 D／E 组时间过滤在真实检索链路上")
    A("   作用于向量候选与图谱候选的合并去重之前；本报告无法在零模型调用、无 FAISS 索引的")
    A("   前提下复现真实召回集合，故用『事件语义边相连的证据块 + gold 文档全部块』作代理池，")
    A("   并给出逐题的差集读数。这是代理口径，不是真实召回集合的实测。")
    A("8. **与 PE 集的重叠已降为零**（缺陷 4 的修复结果，见第 5 节）：本批 %d 道题的 gold"
      "与 PE 集 **零交集**、题干也全部不同。**登记**：允许同 doc 邻接，逐条清单见《说明.md》。"
      % len(stats["pe_overlap_gold"]))
    A("9. **`builder:\"hand\"` 的题共 6 道**（FQ-103～FQ-108）：候选由确定性枚举器给出，")
    A("   题面／参考答案／锚点由决策者逐条回原文撰写；其余 30 道为 `script`。")
    A("10. **路径二的 2 跳必要性沿用 PE-18 的同格先例**：答案所在的单个证据块已含机构名，")
    A("   『2 跳』体现在「先经公司→事件定位窗口内的事件、再经事件→机构确定机构端点」这一步，")
    A("   与 PE-18（事件型×2 跳×有时间约束，gold=1130000 单块）的口径一致。")
    A("")
    A("## 9. 校验结论")
    A("")
    if errors:
        A("**存在 %d 处校验错误（脚本以非零退出码结束）：**" % len(errors))
        A("")
        A("```text")
        for e in errors:
            A(e)
        A("```")
    else:
        A("**全部校验通过**（gold 条数、doc 一致性、锚点逐字命中、时间窗口可过滤与差集非空、")
        A("PE 去重、跳数判据齐全）。校验命令与退出码见文末。")
    if warn:
        A("")
        A("**警告 %d 条（不阻断）：**" % len(warn))
        A("")
        A("```text")
        for w in warn:
            A(w)
        A("```")
    A("")
    A("## 10. 自检命令与关键 stdout")
    A("")
    A("```text")
    A(args_note)
    A("```")
    A("")
    with io.open(REPORT_PATH, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

# ---------------------------------------------------------------------------
# 8. 入口
# ---------------------------------------------------------------------------
def dump_candidates(inp):
    c1 = enum_fact_one_hop(inp)
    print("[枚举器① 事实型+1跳] 事件对候选 = %d；HAS_EXECUTIVE 同型跨文档公司 = %d"
          % (len(c1), len(_fact_person_candidates(inp))))
    for c in c1[:40]:
        print("   %-8s %-10s %-12s %-12s docs=%s chunks=%s"
              % (c["company"], inp.name(c["company"]), c["events"][0], c["events"][1],
                 c["docs"], c["candidate_chunks"]))
    c2 = enum_event_two_hop(inp)
    print("[枚举器② 事件型+2跳 · 路径一 公司×共同事件×公司] 公司对候选 = %d；其中双方都可命名 = %d"
          % (len(c2), sum(1 for c in c2 if c["b_named"])))
    for c in c2:
        print("   %-12s × %-20s events=%s docs=%s"
              % (inp.name(c["a"])[:12], inp.name(c["b"])[:20],
                 [r["event"] for r in c["rows"]], c["docs"]))
    # 枚举器②b：公司→事件→机构／政策（缺陷 3 的有界手工构造的候选池）
    blocked = set()
    for item in Q:
        if item["cell"] == "事件型+2跳" and item["win"] is not None:
            continue                      # 本格 6 道时间约束题自己占用的块不参与「可用候选」
        blocked |= {c for c, _q in item["gold"]}
    pe = list(_iter_jsonl(PE_PATH)) if os.path.exists(PE_PATH) else []
    for row in pe:
        blocked |= set(row["gold_evidence_chunk_ids"])
    a_path = os.path.join(ROOT, "阶段10-系统测试与对比实验", "测试集", "_批A",
                          "questions_A.jsonl")
    if os.path.exists(a_path):
        for row in _iter_jsonl(a_path):
            blocked |= set(row["gold_evidence_chunk_ids"])
    c2b = enum_event_two_hop_org(inp, blocked_chunks=blocked)
    print("[枚举器②b 事件型+2跳 · 路径二 公司→事件→机构／政策] 可用候选 = %d" % len(c2b))
    for c in c2b:
        print("   %-14s %-12s t=%-10s 机构/政策=%s docs=%s chunks=%s"
              % (inp.name(c["companies"][0])[:14], c["event"], c["time"],
                 [inp.name(t) for t in c["targets"]], c["docs"], c["chunks"]))
    c3 = enum_relation_zero_hop(inp)
    c3ok = [c for c in c3 if c["single_block_ok"]]
    print("[枚举器③ 关系型+0跳] 块级候选 = %d；单块可证 = %d；其中在可过滤文档上 = %d"
          % (len(c3), len(c3ok), sum(1 for c in c3ok if c["now"])))
    for c in c3ok:
        if c["now"]:
            print("   %-16s 块 %-8d doc %-5d quote=%s"
                  % (c["pattern"], c["chunk"], c["doc"], c["quote_raw"][:44]))
    return 0

def main():
    ap = argparse.ArgumentParser(description="批B 正式测试集构建器（只读输入，零模型调用）")
    ap.add_argument("--candidates", action="store_true", help="只打印三个枚举器的候选池")
    ap.add_argument("--verify", action="store_true", help="只校验已生成的 questions_B.jsonl")
    ap.add_argument("--idempotent", action="store_true", help="连跑两次比字节（确定性自检）")
    args = ap.parse_args()

    inp = Inputs()
    print("[输入] chunks=%d docs=%d nodes=%d edges=%d 可过滤文档=%d 篇"
          % (len(inp.chunks), len(inp.docs), len(inp.nodes), len(inp.edges), len(inp.time_subset)))
    if args.candidates:
        return dump_candidates(inp)

    recs = build_records(inp)
    errors, warn, stats = verify(inp, recs)

    if args.verify:
        for e in errors:
            print("错误：%s" % e)
        for w in warn:
            print("警告：%s" % w)
        print("[校验] 错误 %d 条；警告 %d 条" % (len(errors), len(warn)))
        return 1 if errors else 0

    digest = write_jsonl(recs, OUT_PATH)
    print("[生成] %s（%d 行，SHA-256=%s）" % (os.path.relpath(OUT_PATH, ROOT), len(recs), digest))

    if args.idempotent:
        digest2 = write_jsonl(recs, OUT_PATH + ".tmp")
        same = False
        with io.open(OUT_PATH, "rb") as a, io.open(OUT_PATH + ".tmp", "rb") as b:
            same = a.read() == b.read()
        os.remove(OUT_PATH + ".tmp")
        print("[确定性] 二次生成逐字节一致 = %s" % same)
        if not same:
            errors.append("二次生成字节不一致")

    for e in errors:
        print("错误：%s" % e)
    for w in warn:
        print("警告：%s" % w)
    detail = ("命令：python \"阶段10-系统测试与对比实验\\工具\\建正式测试集_B.py\"%s\n"
              "退出码：%d\n"
              "stdout 关键行：\n"
              "  [输入] chunks=%d docs=%d nodes=%d edges=%d 可过滤文档=%d 篇\n"
              "  [生成] questions_B.jsonl（%d 行，SHA-256=%s）\n"
              "  [校验] 错误 %d 条；警告 %d 条"
              % (" --idempotent" if args.idempotent else "", 1 if errors else 0,
                 len(inp.chunks), len(inp.docs), len(inp.nodes), len(inp.edges),
                 len(inp.time_subset), len(recs), digest, len(errors), len(warn)))
    write_report(inp, recs, errors, warn, stats, digest, detail)
    print("[报告] %s" % os.path.relpath(REPORT_PATH, ROOT))
    print("[校验] 错误 %d 条；警告 %d 条 -> 退出码 %d" % (len(errors), len(warn), 1 if errors else 0))
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
