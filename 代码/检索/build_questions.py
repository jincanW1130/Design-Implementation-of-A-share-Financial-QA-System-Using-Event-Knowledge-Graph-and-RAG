# -*- coding: utf-8 -*-
"""T9 预实验问题集（30 题）的确定性构建脚本。

依据：`阶段06-事件抽取与知识图谱\18-第7阶段任务书（RAG检索系统）.md`
第九节 T9、第4.4节（题集四件与两条题集纪律）、第六节 格式决策 5、第七节 非目标 6／7、
第八节 第 25 行（题集的验收判据）、第五节 硬约束 20；
《02-项目执行总控文档》第12.2节（题目标签体系）与 第12.8节（按子集判定、核心 108 题）。

本脚本做三件事，全部**只读**输入（数据集 v2.1 与图谱导出物 v2.1_v1_2 一个字节都不写）：

1. `--profile candidates`：从 v2.1 与图谱导出物**确定性枚举候选题目**，
   并按规则抽取候选 gold 证据块；候选默认只打印计数，给 `--out` 才落盘。
2. `--profile freeze`：把**决策者（AI）用确定性脚本构造并逐条回原文核验**的 30 题
   固化为 `config.QUESTION_FILES["questions"]`；同一输入两次运行逐字节一致
   （不写时间戳、不写随机数、不依赖字典遍历顺序）。
3. `--profile verify`：只读 `questions.jsonl`，把构建期断言**重跑一遍**
   （供 T11／T12 复核）。

三条口径必须与文档一致，不得在本脚本里偷改：

* gold 证据上限 **8 条**；30 题里 1 条的、3～5 条的、6～8 条的三种档位都要有实例
  （T8 才能找出 Complete Evidence Recall@K 饱和的最小 K）。
* **带时间约束的题**，其 gold 证据所在文档必须落在"含 ≥2 个不同 `event_time` 日期"的
  66 篇里（v1.2 现行口径；脚本内现场复算，数目不符即报错退出）。
* `gold_verified_by` 写 `third_party_model_review_v1`（原值另存于 `third_party_review.prior_verified_by`）：
  这套 gold 由**决策者（AI）**用确定性脚本构造并逐条回原文核验，再交**两家第三方模型盲标复核**
  （`kimi`＋`zhipu`，prompt 版本 `stage7-thirdparty-review-v1.0`），最后由决策者**回原文逐条裁定**。
  第三方模型复核**不是人工抽检、不是金标准**；报告里的一切比率都是**模型间一致率**，**不等于事实**；
  人工抽检仍未做，不得写成"人工构造"或"人工金标准"。
  另一条第三方线（百度千帆 `ernie-5.1`）**原已完整跑通（30/30、0 失败、60,073 token）**，但作者裁定该
  通道不可用、其凭据已从 `代码\\抽取与图谱\\config.local.json` 删除，故**不参与本次确认**；它的逐题
  verdict 与模型名仍在 `third_party_review` 里保留并标 `excluded`，30 条原始返回与结果留痕在
  `阶段07-RAG检索系统\\_工作底稿\\第三方复核\\qianfan\\`（不删改、不入库）。

术语纪律：全文不写出被禁用的四字连写术语（一律写「向量索引」或「向量检索组件」）。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import config  # noqa: E402  （同目录的 config.py 是唯一参数来源）

if os.path.dirname(os.path.abspath(config.__file__)) != HERE:
    raise SystemExit("导入到的 config.py 不在本脚本同目录，拒绝继续：%s" % config.__file__)


# ---------------------------------------------------------------------------
# 0. 常量与标签域（取值只来自《02》第12.2节，不自行发明）
# ---------------------------------------------------------------------------
TASK_TYPES = ("事实型", "事件型", "关系型")
HOP_DEPTHS = (0, 1, 2)
TIME_LABELS = ("无", "有")
GOLD_MAX = 8                     # T9 设计约束 2：gold 证据条数上限
GOLD_MIN = 1
GOLD_BANDS = ((1, 1), (3, 5), (6, 8))   # 必须有实例的三档
TIME_SUBSET_EXPECTED = 66        # 表 18-C 的 v1.2 现行口径；不符即报错退出
VERIFIED_BY = "third_party_model_review_v1"
REVIEW_STATUS = ("经两家第三方模型盲标复核（kimi＋zhipu）＋决策者回原文裁定；非人工逐题确认，人工抽检未做，"
                 "复核结论不等于事实")
PRIOR_VERIFIED_BY = "decision_maker_ai_verify_v1"

# ---------------------------------------------------------------------------
# 0b. 第三方模型盲标复核的登记（T9 追加；明细见 代码\检索\third_party_review.py 与
#     阶段07-RAG检索系统\预实验问题集\第三方复核报告.md、第三方复核台账.json）
#     本表只登记结果，不含任何凭据；参与确认的两家是不同厂商，构成跨厂商独立证据。
#     另一条第三方线已按作者指示从确认口径剥离：本表保留其逐题 verdict 与模型名，
#     并在 third_party_review.excluded 里标 excluded=true 与原因（只作留痕，不参与一致率）。
# ---------------------------------------------------------------------------
REVIEW_PROMPT_VERSION = "stage7-thirdparty-review-v1.0"
REVIEW_OUTPUT_SCHEMA = "stage7-thirdparty-review-1.0"
REVIEW_VENDORS = (("kimi", "kimi-k3"), ("zhipu", "glm-5.3-flash"))
REVIEW_EXCLUDED_VENDORS = (("qianfan", "ernie-5.1"),)
REVIEW_SCOPE = "参与本次确认的线＝kimi（kimi-k3）＋zhipu（glm-5.3-flash）两家"
REVIEW_EXCLUDED_REASON = ("百度千帆（ernie-5.1）线按作者指示剥离：该通道已被判定不可用、凭据已从 "
                          "代码\\抽取与图谱\\config.local.json 删除，故不参与本次确认；该线实测曾完整跑通"
                          "（30 题 0 失败、60,073 token），其 30 条原始返回与结果保留在 "
                          "阶段07-RAG检索系统\\_工作底稿\\第三方复核\\qianfan\\ 作为留痕，不删不改。")
REVIEW_DEFAULT_ADJUDICATION = "参与确认的两家（kimi、zhipu）判定一致，维持现行 gold 与参考答案（只登记不改）"
# qid -> {厂商: (verdict, answer_supported)}
THIRD_PARTY_VERDICTS = {
    "PE-01": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-02": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-03": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-04": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-05": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-06": {"kimi": ("成立", True), "qianfan": ("部分成立", True), "zhipu": ("成立", True)},
    "PE-07": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-08": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-09": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-10": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-11": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-12": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-13": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-14": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-15": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-16": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-17": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-18": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-19": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-20": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-21": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-22": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-23": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-24": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-25": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-26": {"kimi": ("部分成立", False), "qianfan": ("部分成立", False), "zhipu": ("部分成立", False)},
    "PE-27": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-28": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
    "PE-29": {"kimi": ("成立", True), "qianfan": ("部分成立", True), "zhipu": ("部分成立", True)},
    "PE-30": {"kimi": ("成立", True), "qianfan": ("成立", True), "zhipu": ("成立", True)},
}
# 只有原文明确支持的修正才动 gold／参考答案；其余一律只登记不改。
THIRD_PARTY_ADJUDICATION = {
    "PE-06": ("只登记不改：参与确认的两家（kimi、zhipu）均判“成立”，维持现行 gold 与参考答案；"
              "已按作者指示剥离的一条第三方线（不参与确认、只作留痕）判“部分成立”系误读"
              "（把“品种一”的单只发行金额当成合计发行总额），原文 1021001 已写明"
              "“发行总额为人民币45亿元”、1021002 写明“品种二 5亿元”，40亿＋5亿＝45亿，两处一致。"),
    "PE-26": ("已按原文改 gold：参与确认的两家（kimi、zhipu）一致指出参考答案里的两份框架协议名称不在原 gold 块内"
              "（已剥离的一条线同向，只作留痕）；"
              "回原文 1502001／1533001 逐字给出协议全称，属 gold 证据不足，"
              "故补入 1502001、1533001（gold 由 2 块增至 4 块），候选规则相应改为“文档内全部文本块”。"),
    "PE-29": ("已按原文改参考答案：参与确认的两家为 1:1 分歧（kimi“成立”、zhipu“部分成立”）；"
              "zhipu 指出原文 1001001 同一块内并列“首次授予第二个行权期”与“预留授予第一个行权期”"
              "两条均自 2026-09-11 起行权的事件，原答案漏了后者（kimi 也把该点记入 missing_from_answer），"
              "回原文确认属实，属参考答案不完整，gold 证据块不变（1001000、1001001）。"),
}


def third_party_review_block(qid: str) -> dict:
    """把盲标复核的结论固化成 questions.jsonl 里的 third_party_review 字段。

    确认口径＝`REVIEW_VENDORS` 两家（consistent 只按这两家算）；已剥离线按留痕口径
    保留 verdict 与模型名，并在 `excluded` 里标 `excluded: true` 与原因。
    """
    verdicts = THIRD_PARTY_VERDICTS[qid]
    return {
        "prompt_version": REVIEW_PROMPT_VERSION,
        "output_schema": REVIEW_OUTPUT_SCHEMA,
        "review_scope": REVIEW_SCOPE,
        "confirmed_lines": [v for v, _ in REVIEW_VENDORS],
        "models": {v: m for v, m in review_models()},
        "verdicts": {v: verdicts[v][0] for v, _ in review_models()},
        "answer_supported": {v: verdicts[v][1] for v, _ in review_models()},
        "excluded": {v: {"excluded": True, "excluded_per_author": True, "reason": REVIEW_EXCLUDED_REASON}
                     for v, _ in REVIEW_EXCLUDED_VENDORS},
        "consistent": len({verdicts[v][0] for v, _ in REVIEW_VENDORS}) == 1,
        "adjudication": THIRD_PARTY_ADJUDICATION.get(qid, REVIEW_DEFAULT_ADJUDICATION),
        "prior_verified_by": PRIOR_VERIFIED_BY,
    }


def review_models() -> tuple:
    """确认口径两家 ＋ 留痕口径一家的（厂商, 模型名）登记（models 里保留被剥离线）。"""
    return tuple(REVIEW_VENDORS) + tuple(REVIEW_EXCLUDED_VENDORS)
EDGE_COLUMNS = config.EDGE_COLUMNS
RELATIVE_WINDOW_LABELS = {"最近30天": 30, "近期90天": 90}


def _cutoff_date() -> _dt.date:
    return _dt.datetime.fromisoformat(config.DATA_CUTOFF_TIME).date()


def resolve_window(spec_window):
    """把题目的时间窗口解析成闭区间；相对窗口一律以 data_cutoff_time 为基准。"""
    if spec_window is None:
        return None
    label = spec_window["label"]
    cutoff = _cutoff_date()
    if label in RELATIVE_WINDOW_LABELS:
        lo = cutoff - _dt.timedelta(days=RELATIVE_WINDOW_LABELS[label])
        hi = cutoff
    else:
        lo, hi = spec_window["lo"], spec_window["hi"]
    out = {
        "label": label,
        "lo": lo.isoformat() if hasattr(lo, "isoformat") else lo,
        "hi": hi.isoformat() if hasattr(hi, "isoformat") else hi,
        "basis": "event_time",
        "cutoff": config.DATA_CUTOFF_TIME,
        "empty_policy": config.RETRIEVAL["time_filter_null_policy"],
    }
    if spec_window.get("lo") and out["lo"] != spec_window["lo"]:
        raise SystemExit("窗口下界与脚本登记不一致：%s != %s" % (out["lo"], spec_window["lo"]))
    if spec_window.get("hi") and out["hi"] != spec_window["hi"]:
        raise SystemExit("窗口上界与脚本登记不一致：%s != %s" % (out["hi"], spec_window["hi"]))
    return out


def _cn_date(iso: str) -> str:
    y, m, d = iso.split("-")
    return "%s年%d月%d日" % (y, int(m), int(d))


def normalize_text(text: str) -> str:
    """去掉所有空白字符后比对，抵消原文里的换行与排版空格。"""
    return re.sub(r"\s+", "", text)


# ---------------------------------------------------------------------------
# 1. 只读输入
# ---------------------------------------------------------------------------
def read_csv_rows(path: str):
    with io.open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


class Inputs(object):
    """v2.1 与图谱导出物的只读视图。"""

    def __init__(self):
        self.docs = {}
        for row in config.iter_jsonl(config.DOCS_PATH):
            self.docs[int(row["doc_id"])] = row
        self.chunks = {}
        self.chunks_by_doc = {}
        for row in config.iter_jsonl(config.CHUNKS_PATH):
            cid = int(row["chunk_id"])
            self.chunks[cid] = row
            self.chunks_by_doc.setdefault(int(row["doc_id"]), []).append(cid)
        for doc_id in self.chunks_by_doc:
            self.chunks_by_doc[doc_id].sort()

        self.nodes = read_csv_rows(config.NODES_CSV)
        self.edges = read_csv_rows(config.EDGES_CSV)
        if list(self.edges[0].keys()) != EDGE_COLUMNS:
            raise SystemExit("edges.csv 列名与 config.EDGE_COLUMNS 不一致，拒绝继续")
        self.node_by_id = {n["node_id"]: n for n in self.nodes}

        self.event_docs = {}           # event_id -> 文档集合（EVIDENCED_BY 反查；一个事件可归多篇文档）
        self.event_chunks = {}         # event_id -> 语义边上的 source_chunk_id 集合
        self.event_companies = {}      # event_id -> Company 参与者
        self.event_orgs = {}           # event_id -> ISSUED_BY 机构
        self.event_policies = {}       # event_id -> RELATED_TO 政策
        self.company_events = {}       # company_id -> 事件集合
        self.company_persons = {}      # company_id -> 人物集合
        for edge in self.edges:
            rel = edge["relation"]
            head, tail = edge["head_id"], edge["tail_id"]
            if rel == "EVIDENCED_BY":
                h, t = self.node_by_id.get(head), self.node_by_id.get(tail)
                if h is not None and t is not None and h["label"] == "Event" and t["label"] == "Document":
                    self.event_docs.setdefault(head, set()).add(t["doc_id"])
                continue
            if edge["source_chunk_id"]:
                for side in (head, tail):
                    if side.startswith("EVT-"):
                        self.event_chunks.setdefault(side, set()).add(int(edge["source_chunk_id"]))
            if rel == "PARTICIPATES_IN":
                h, t = self.node_by_id.get(head), self.node_by_id.get(tail)
                if h is not None and t is not None and h["label"] == "Company" and t["label"] == "Event":
                    self.company_events.setdefault(head, set()).add(tail)
                    self.event_companies.setdefault(tail, set()).add(head)
            elif rel == "HAS_EXECUTIVE":
                self.company_persons.setdefault(head, set()).add(tail)
            elif rel == "ISSUED_BY":
                self.event_orgs.setdefault(head, set()).add(tail)
            elif rel == "RELATED_TO":
                self.event_policies.setdefault(head, set()).add(tail)

        # 含 >=2 个不同 event_time 日期的文档（表 18-C 的 v1.2 现行口径）
        dates_by_doc = {}
        for ev, doc_ids in self.event_docs.items():
            nd = self.node_by_id.get(ev)
            if nd is None:
                continue
            et = (nd.get("event_time") or "").strip()
            if not et:
                continue
            for doc_id in doc_ids:
                dates_by_doc.setdefault(doc_id, set()).add(et)
        self.doc_dates = dates_by_doc
        self.time_subset = sorted(int(d) for d, s in dates_by_doc.items() if len(s) >= 2)

    # ---- 便利查询 ----
    def event_name(self, ev):
        return self.node_by_id[ev]["event_name"]

    def doc_of_chunk(self, cid):
        return int(self.chunks[cid]["doc_id"])

    def edge_row(self, head, relation, tail):
        for edge in self.edges:
            if edge["head_id"] == head and edge["relation"] == relation and edge["tail_id"] == tail:
                return edge
        return None


# ---------------------------------------------------------------------------
# 2. 候选题目枚举（--profile candidates）
# ---------------------------------------------------------------------------
def _company_name(inputs, cid):
    return inputs.node_by_id[cid]["name"]


def generate_candidates(inputs: Inputs):
    """确定性枚举候选题目；顺序由固定排序键决定，不依赖字典遍历顺序。"""
    out = []
    companies = sorted(c for c, n in inputs.node_by_id.items() if n["label"] == "Company")
    events = sorted(e for e, n in inputs.node_by_id.items() if n["label"] == "Event")

    # ① 文档型事实候选（0 跳）：每篇文档 1 条
    for doc_id in sorted(inputs.chunks_by_doc):
        out.append({
            "candidate_kind": "document_fact",
            "task_type": "事实型",
            "gold_hop_depth": 0,
            "subject": "doc:%d" % doc_id,
            "candidate_gold_chunk_ids": sorted(inputs.chunks_by_doc[doc_id]),
            "template": "《%s》公告/报道披露了哪些要点？" % inputs.docs[doc_id]["title"],
        })

    # ② 事件型候选（0 跳）：每个有证据块的事件 1 条
    for ev in events:
        chs = sorted(inputs.event_chunks.get(ev, ()))
        if not chs:
            continue
        out.append({
            "candidate_kind": "event_fact",
            "task_type": "事件型",
            "gold_hop_depth": 0,
            "subject": "event:%s" % ev,
            "candidate_gold_chunk_ids": chs,
            "template": "%s事件的主要内容是什么？" % inputs.event_name(ev),
        })

    # ③ 公司-事件集合候选（1 跳）：公司参与 >=2 个事件
    for cid in companies:
        evs = sorted(inputs.company_events.get(cid, ()))
        chs = sorted({c for ev in evs for c in inputs.event_chunks.get(ev, ())})
        if len(evs) < 2 or not chs:
            continue
        out.append({
            "candidate_kind": "company_event_set",
            "task_type": "事件型",
            "gold_hop_depth": 1,
            "subject": "company:%s" % cid,
            "candidate_gold_chunk_ids": chs,
            "template": "%s参与了哪些事件？" % _company_name(inputs, cid),
        })

    # ④ 公司-人物集合候选（1 跳）：公司的高管边落在 >=1 个证据块
    for cid in companies:
        persons = sorted(inputs.company_persons.get(cid, ()))
        if not persons:
            continue
        chs = sorted({int(e["source_chunk_id"]) for e in inputs.edges
                      if e["head_id"] == cid and e["relation"] == "HAS_EXECUTIVE" and e["source_chunk_id"]})
        out.append({
            "candidate_kind": "company_person_set",
            "task_type": "关系型",
            "gold_hop_depth": 1,
            "subject": "company:%s" % cid,
            "candidate_gold_chunk_ids": chs,
            "template": "%s披露的董事及高级管理人员包括哪些人？" % _company_name(inputs, cid),
        })

    # ⑤ 共同参与事件候选（2 跳）：事件有 >=2 个公司参与者
    for ev in events:
        comps = sorted(inputs.event_companies.get(ev, ()))
        if len(comps) < 2:
            continue
        out.append({
            "candidate_kind": "co_participation_event",
            "task_type": "关系型",
            "gold_hop_depth": 2,
            "subject": "event:%s" % ev,
            "candidate_gold_chunk_ids": sorted(inputs.event_chunks.get(ev, ())),
            "template": "%s与%s共同参与的事件是什么？" % (_company_name(inputs, comps[0]), _company_name(inputs, comps[1])),
        })

    # ⑥ 事件-机构／政策候选（2 跳）
    for ev in events:
        tails = sorted(list(inputs.event_orgs.get(ev, ())) + list(inputs.event_policies.get(ev, ())))
        if not tails:
            continue
        out.append({
            "candidate_kind": "event_to_org_or_policy",
            "task_type": "事实型",
            "gold_hop_depth": 2,
            "subject": "event:%s" % ev,
            "candidate_gold_chunk_ids": sorted(inputs.event_chunks.get(ev, ())),
            "template": "%s涉及哪家机构或哪份政策文件？" % inputs.event_name(ev),
        })

    for i, cand in enumerate(out, 1):
        cand["candidate_id"] = "C%04d" % i
    return out


def profile_candidates(inputs: Inputs, out_path):
    cands = generate_candidates(inputs)
    counts = {}
    for cand in cands:
        key = (cand["candidate_kind"], cand["task_type"], cand["gold_hop_depth"])
        counts[key] = counts.get(key, 0) + 1
    print("[T9] 候选题目总数 %d" % len(cands))
    for key in sorted(counts):
        print("      %-24s %-4s %d 跳：%d 条" % (key[0], key[1], key[2], counts[key]))
    if out_path:
        config.write_jsonl(out_path, cands)
        print("[T9] 候选池已写入：%s" % out_path)
    return cands


# ---------------------------------------------------------------------------
# 3. 冻结表：决策者（AI）逐条回原文核验后的 30 题
# ---------------------------------------------------------------------------
# 字段约定：window=None 表示时间约束=无；anchors 是"核验锚点"，
# 逐条给出 (chunk_id, 原文片段)，脚本会到 chunks.jsonl 的 content 里逐字比对（忽略空白）。
W30 = {"label": "最近30天", "lo": "2026-08-26", "hi": "2026-09-25"}


def _w(label, lo, hi):
    return {"label": label, "lo": lo, "hi": hi}


FROZEN_QUESTIONS = [
    # ---------------- 事实型 × 0 跳 ----------------
    dict(
        qid="PE-01", task_type="事实型", gold_hop_depth=0, time_constraint="无", window=None,
        question="长城汽车《2023年股票期权激励计划》首次授予股票期权第二个行权期的行权期有效期是什么时间段？",
        reference_answer="行权期有效期为2026年9月11日至2027年1月25日，自2026年9月11日开始行权。",
        gold=[1001001], docs=[1001],
        rule=dict(kind="doc_chunks", doc_ids=[1001], note="该题属文本型，候选来自 doc 1001 的全部文本块"),
        edges_spec=[],
        anchors=[(1001001, "行权期有效期为2026年9月11日-2027年1月25日")],
        note="回原文核验：1001000 只交代“2026年1月26日进入第二个行权期”，不含有效期；1001001 明确“行权期有效期为2026年9月11日-2027年1月25日，2026年9月11日开始行权”。故 gold 只留 1001001，候选块 1001000 不进入 gold。",
    ),
    dict(
        qid="PE-02", task_type="事实型", gold_hop_depth=0, time_constraint="无", window=None,
        question="特变电工控股公司特变电工新疆新能源股份有限公司2026年度第一期绿色科技创新债券的发行额度、期限与发行利率分别是多少？",
        reference_answer="发行额度10亿元人民币，期限3+N年，发行利率2.1%。",
        gold=[1342001], docs=[1342],
        rule=dict(kind="doc_chunks", doc_ids=[1342], note="候选来自 doc 1342 的全部文本块"),
        edges_spec=[],
        anchors=[(1342001, "发行额度10亿元人民币，期限3+N年")],
        note="回原文核验：1342001 同时给出“发行额度10 亿元人民币，期限3+N 年，起息日为2026年6月29日……发行利率为2.1%”；1342000 只交代董事会与注册背景，不进入 gold。",
    ),
    dict(
        qid="PE-03", task_type="事实型", gold_hop_depth=0, time_constraint="有", window=W30,
        question="最近30天（2026年8月26日至2026年9月25日）内，阳光电源控股子公司参与设立的苏州华旭新能股权投资合伙企业完成了哪项登记，备案编码是多少？",
        reference_answer="已完成中国证券投资基金业协会备案；备案编码为SEX000，备案时间2026年9月22日。",
        gold=[1010001], docs=[1010],
        rule=dict(kind="doc_chunks", doc_ids=[1010], note="候选来自 doc 1010 的全部文本块"),
        edges_spec=[],
        anchors=[(1010001, "本基金已完成中国证券投资基金业协会备案"),
                 (1010001, "备案编码：SEX000")],
        note="回原文核验：1010001 同时给出备案事实、备案编码 SEX000、备案时间 2026 年 9 月 22 日；1010000 只交代 2026 年 7 月 23 日的设立背景。该文档在“含 ≥2 个不同日期”的 66 篇内（2026-07-23、2026-09-22），最近 30 天窗口内只剩 09-22 备案事件。",
    ),
    # ---------------- 事实型 × 1 跳 ----------------
    dict(
        qid="PE-04", task_type="事实型", gold_hop_depth=1, time_constraint="无", window=None,
        question="工业富联披露的董事及高级管理人员包括哪些人？",
        reference_answer="郑弘孟（董事长、总经理）、黄德才、杨秋瑾、许兴仁、丁肇邦、林奂汝（职工代表董事）、张瑞雄（副总经理）、白家南等。",
        gold=[1279014, 1279015, 1339008, 1339009, 1339010, 1339011, 1339012],
        docs=[1279, 1339],
        rule=dict(kind="company_persons", company_ids=["601138"], note="HAS_EXECUTIVE 143 条边中属于工业富联的 9 条"),
        edges_spec=[("601138", "HAS_EXECUTIVE", "PER-0003"), ("601138", "HAS_EXECUTIVE", "PER-0124"),
                    ("601138", "HAS_EXECUTIVE", "PER-0202"), ("601138", "HAS_EXECUTIVE", "PER-0204"),
                    ("601138", "HAS_EXECUTIVE", "PER-0259"), ("601138", "HAS_EXECUTIVE", "PER-0307"),
                    ("601138", "HAS_EXECUTIVE", "PER-0327"), ("601138", "HAS_EXECUTIVE", "PER-0397")],
        anchors=[(1339008, "郑弘孟"), (1339009, "黄德才"), (1339010, "杨秋瑾"), (1339011, "许兴仁"),
                 (1339012, "丁肇邦"), (1279014, "林奂汝"), (1279015, "张瑞雄")],
        note="回原文核验：9 条 HAS_EXECUTIVE 边落在 7 个不同文本块（doc 1279 两块、doc 1339 五块）；逐块比对确认每块都给出人名与职务表述，任缺一块都无法完整列出名单，故 gold 取 7 块。",
    ),
    dict(
        qid="PE-05", task_type="事实型", gold_hop_depth=1, time_constraint="无", window=None,
        question="宁德时代2026年完成发行的绿色科技创新债券分别有哪几期，各自的发行日期是什么？",
        reference_answer="第六期（2026年8月26日发行）、第七期（2026年9月21日发行）。",
        gold=[1021000, 1163000], docs=[1021, 1163],
        rule=dict(kind="doc_chunks", doc_ids=[1021, 1163],
                  note="候选来自两篇“发行完成”公告的全部文本块；事件侧由登记的 PARTICIPATES_IN 边另行核验"),
        edges_spec=[("300750", "PARTICIPATES_IN", "EVT-0027"), ("300750", "PARTICIPATES_IN", "EVT-0206")],
        anchors=[(1021000, "2026年9月21日，公司成功发行了2026年度第七期绿色科技创新债券"),
                 (1163000, "2026年8月26日，公司成功发行了2026年度第六期绿色科技创新债券")],
        note="回原文核验：1021000 与 1163000 各给出一次“发行完成”的日期与期数；同一事件在另一篇公告里的对应块（1021000/1163000 之外的块）只用于补充金额，未纳入本题 gold。",
    ),
    dict(
        qid="PE-06", task_type="事实型", gold_hop_depth=1, time_constraint="有", window=W30,
        question="最近30天（2026年8月26日至2026年9月25日）内，宁德时代完成发行的绿色科技创新债券合计发行总额是多少？",
        reference_answer="合计115亿元：第六期发行总额70亿元，第七期发行总额45亿元。",
        gold=[1021000, 1021001, 1163000, 1163001], docs=[1021, 1163],
        rule=dict(kind="doc_chunks", doc_ids=[1021, 1163],
                  note="候选来自两篇“发行完成”公告的全部文本块"),
        edges_spec=[("300750", "PARTICIPATES_IN", "EVT-0027"), ("300750", "PARTICIPATES_IN", "EVT-0206")],
        anchors=[(1021001, "发行总额为人民币45亿元"), (1163001, "发行总额为人民币70亿元"),
                 (1021000, "2026年9月21日，公司成功发行了2026年度第七期绿色科技创新债券"),
                 (1163000, "2026年8月26日，公司成功发行了2026年度第六期绿色科技创新债券")],
        note="回原文核验：两篇公告各两块，日期在 xxx000 块、发行总额在 xxx001 块。两篇文档都在 66 篇内；窗口内为 08-26 与 09-21 两次发行，04-23 的注册事件（doc 1163 的 EVT-0205）落在窗口外，时间过滤会改变候选集合。",
    ),
    # ---------------- 事实型 × 2 跳 ----------------
    dict(
        qid="PE-07", task_type="事实型", gold_hop_depth=2, time_constraint="无", window=None,
        question="保利发展2026年度第一期中期票据的联席主承销商中，中国工商银行股份有限公司担任什么角色？",
        reference_answer="中国工商银行股份有限公司是本期中期票据的联席主承销商之一（主承销为渤海银行股份有限公司）。",
        gold=[1005000, 1005001], docs=[1005],
        rule=dict(kind="shared_events", company_ids=["600048", "601398"], note="保利发展与工商银行的共同参与事件 EVT-0007"),
        edges_spec=[("600048", "PARTICIPATES_IN", "EVT-0007"), ("601398", "PARTICIPATES_IN", "EVT-0007")],
        anchors=[(1005000, "保利发展控股集团股份有限公司2026年度第一期中期票据"),
                 (1005001, "联席主承销")],
        note="回原文核验：1005000 给出发行人、债券简称与期限，1005001 才列出“联席主承销：中国工商银行股份有限公司、中国建设银行股份有限公司”；两块缺一不能同时确认发行主体与工商银行的角色。",
    ),
    dict(
        qid="PE-08", task_type="事实型", gold_hop_depth=2, time_constraint="无", window=None,
        question="东宏股份与万华化学集团物资有限公司签订的采购框架合同中，买方与合同预估总金额分别是什么？",
        reference_answer="买方为万华化学集团物资有限公司；合同预估总金额为人民币18,000万元。",
        gold=[1500002, 2090000], docs=[1500, 2090],
        rule=dict(kind="shared_events", company_ids=["603856", "600309"], note="东宏股份与万华化学的共同参与事件 EVT-0659／EVT-0989"),
        edges_spec=[("603856", "PARTICIPATES_IN", "EVT-0659"), ("600309", "PARTICIPATES_IN", "EVT-0659"),
                    ("603856", "PARTICIPATES_IN", "EVT-0989"), ("600309", "PARTICIPATES_IN", "EVT-0989")],
        anchors=[(1500002, "万华化学集团物资有限公司（以下简称“买方”）"),
                 (2090000, "分别签订了中标标段对应的《采购框架合同》")],
        note="回原文核验：1500002 明确买方为万华化学集团物资有限公司并给出对方基本情况；2090000（证券日报网 2026-08-06）给出“合同预估总金额为人民币18，000万元”。两块分别来自公告与报道，跨文档合起来才能完整回答。",
    ),
    dict(
        qid="PE-09", task_type="事实型", gold_hop_depth=2, time_constraint="有",
        window=_w("2026年4月1日至2026年4月30日", "2026-04-01", "2026-04-30"),
        question="2026年4月1日至2026年4月30日期间，宁德时代的科技创新债券注册由哪家机构接受？",
        reference_answer="中国银行间市场交易商协会（2026年4月23日出具《接受注册通知书》，中市协注〔2026〕MTN339号）。",
        gold=[1163000], docs=[1163],
        rule=dict(kind="event_org", event_ids=["EVT-0205"], note="EVT-0205 的 ISSUED_BY 边指向中国银行间市场交易商协会"),
        edges_spec=[("300750", "PARTICIPATES_IN", "EVT-0205"), ("EVT-0205", "ISSUED_BY", "INST-0069")],
        anchors=[(1163000, "2026年4月23日，公司收到中国银行间市场交易商协会出具的《接受注册通知书》")],
        note="回原文核验：1163000 同时给出公司、日期、机构与通知书编号。候选规则还命中了同一事件在 doc 1021 的对应块，核验后只保留 doc 1163 的 1163000（同一事件的重复表述不重复计入 gold）。doc 1163 在 66 篇内（2026-01-15、2026-08-26），窗口只保留 04-23 注册事件。",
    ),
    # ---------------- 事件型 × 0 跳 ----------------
    dict(
        qid="PE-10", task_type="事件型", gold_hop_depth=0, time_constraint="无", window=None,
        question="工商银行2026年8月28日董事会会议审议通过了哪些议案？",
        reference_answer="五项议案：《中国工商银行“十五五”时期发展规划》、2026半年度报告及摘要、2026半年度资本管理第三支柱信息披露报告、2026年中期利润分配方案、“工行优2”股息分配。",
        gold=[1127000, 1127001, 1127002], docs=[1127],
        rule=dict(kind="doc_chunks", doc_ids=[1127], note="候选来自 doc 1127 的全部文本块"),
        edges_spec=[],
        anchors=[(1127000, "会议应出席董事13名"), (1127001, "关于2026半年度报告及摘要的议案"),
                 (1127002, "派发股息21.14亿元人民币")],
        note="回原文核验：三块依次列出五项议案的名称与表决情况；任缺一块都无法完整列出五项议案，故 gold 取全部三块。",
    ),
    dict(
        qid="PE-11", task_type="事件型", gold_hop_depth=0, time_constraint="无", window=None,
        question="中国中铁2026年第二季度对外担保公告中列出的被担保人有哪些？",
        reference_answer="共10家：中铁一局集团物资工贸有限公司、中铁一局集团（海南）国际建设有限公司、中铁国际集团商贸有限公司、中铁电气化局集团（香港）有限公司、鲁班工业品（天津）有限公司、中铁物贸集团西安有限公司、中铁物贸集团武汉有限公司、中铁武汉勘察设计院有限公司、中铁四川生态城投资有限公司、汕头市牛田洋快速通道投资发展有限公司。",
        gold=[1193000, 1193001, 1193002, 1193003, 1193004, 1193005, 1193006], docs=[1193],
        rule=dict(kind="doc_chunks", doc_ids=[1193], note="候选来自 doc 1193 的全部文本块"),
        edges_spec=[],
        anchors=[(1193000, "中铁一局集团物资工贸有限公司"), (1193001, "中铁国际集团商贸有限公司"),
                 (1193002, "鲁班工业品（天津）有限公司"), (1193003, "中铁物贸集团西安有限公司"),
                 (1193004, "中铁物贸集团武汉有限公司"), (1193005, "中铁四川生态城投资有限公司"),
                 (1193006, "汕头市牛田洋快速通道投资发展有限公司")],
        note="回原文核验：被担保人基本情况表横跨 1193000～1193006 七块，逐块比对序号 1～10 的公司名称均真实出现；1193007 起的担保协议表属另一张表，不计入本题 gold。",
    ),
    dict(
        qid="PE-12", task_type="事件型", gold_hop_depth=0, time_constraint="有", window=W30,
        question="最近30天（2026年8月26日至2026年9月25日）内，中国石化与中国石化集团公司签订的持续关联交易补充协议是哪一份，协议期限到什么时候？",
        reference_answer="《持续关联交易第八补充协议》（2026年9月7日签订），互供协议期限至2027年12月31日止。",
        gold=[1082000, 1082002], docs=[1082],
        rule=dict(kind="doc_chunks", doc_ids=[1082], note="候选来自 doc 1082 的全部文本块"),
        edges_spec=[],
        anchors=[(1082000, "本次修订尚需提交本公司临时股东会审议"),
                 (1082002, "本公司与中国石化集团公司已于2026年9月7日签订了持续关联交易第八补充协议")],
        note="回原文核验：1082000 交代本次修订的性质与后续程序，1082002 给出签订日期、协议名称与期限。doc 1082 在 66 篇内（2026-07-09、2026-09-07），窗口内只剩 09-07 的补充协议事件，07-09 的航油公司重组事件被过滤。",
    ),
    # ---------------- 事件型 × 1 跳 ----------------
    dict(
        qid="PE-13", task_type="事件型", gold_hop_depth=1, time_constraint="无", window=None,
        question="工业富联披露的股份回购相关事件包括哪些？",
        reference_answer="2026年7月27日董事会审议通过回购方案（10亿～20亿元、价格上限103元/股）；2026年8月19日首次回购2,414,402股；2026年8月累计回购14,010,229股；回购实施完毕，累计回购15,833,353股。",
        gold=[1025002, 1100002, 1207001, 1207002, 1279000], docs=[1025, 1100, 1207, 1279],
        rule=dict(kind="company_events_match", company_ids=["601138"], keywords=["回购"],
                  note="工业富联参与、事件名含“回购”的全部事件"),
        edges_spec=[("601138", "PARTICIPATES_IN", "EVT-0031"), ("601138", "PARTICIPATES_IN", "EVT-0129"),
                    ("601138", "PARTICIPATES_IN", "EVT-0275"), ("601138", "PARTICIPATES_IN", "EVT-0276"),
                    ("601138", "PARTICIPATES_IN", "EVT-0365")],
        anchors=[(1025002, "累计回购公司股份数量15,833,353股"), (1100002, "回购公司股份14,010,229股"),
                 (1207001, "审议通过了《关于以集中竞价交易方式回购公司股份的议案》"),
                 (1207002, "首次回购公司股份2,414,402股"),
                 (1279000, "回购股份金额：不低于人民币10亿元（含），不超过人民币20亿元（含）")],
        note="回原文核验：5 个事件分别落在 4 篇文档的 5 个证据块（1025002、1100002、1207001、1207002、1279000）；其中 1279000 给出回购方案要素（金额10亿～20亿元、价格上限103元/股）。单篇文档不含全部事件，属 1 跳汇集的题。保留说明（2026-09-28，回应复核 D6）：1279000 与 1207001 同属 2026-07-27 回购方案事件的另一篇公告（doc 1279 的回购报告书），按 题目模板.md 第三节 第 3 条本可删；本次**保留**——它是方案要素（金额区间与价格上限）在回购报告书里的原文表述，保留只抬高 gold 分母、使 Recall 偏保守（不把不成立说成成立），且删块会改变已冻结的四项指标读数与 检索产出 的既有产物数值。按「不改既有产物数值」的约束保留并在此登记。",
    ),
    dict(
        qid="PE-14", task_type="事件型", gold_hop_depth=1, time_constraint="无", window=None,
        question="中天科技披露的股份回购与员工持股计划相关事件包括哪些？",
        reference_answer="第六期回购进展（截至2026年7月底累计回购200.13万股）；回购价格上限自2026年7月15日起由40.00元/股调整为39.74元/股；2026年7月17日首次回购25.30万股；第五期回购于2025年11月5日实施完毕（18,790,800股）；第二期员工持股计划第二个锁定期于2026年5月21日届满（可解锁471.04万股）；1,665万股于2024年5月20日非交易过户至第二期员工持股计划账户。",
        gold=[1244002, 1294001, 1294002, 1320005, 1364000, 1364002], docs=[1244, 1294, 1320, 1364],
        rule=dict(kind="company_events_match", company_ids=["600522"], keywords=["回购", "员工持股"],
                  note="中天科技参与、事件名含“回购”或“员工持股”的全部事件"),
        edges_spec=[("600522", "PARTICIPATES_IN", "EVT-0324"), ("600522", "PARTICIPATES_IN", "EVT-0388"),
                    ("600522", "PARTICIPATES_IN", "EVT-0389"), ("600522", "PARTICIPATES_IN", "EVT-0421"),
                    ("600522", "PARTICIPATES_IN", "EVT-0480"), ("600522", "PARTICIPATES_IN", "EVT-0481")],
        anchors=[(1244002, "已累计回购股份200.13万股"),
                 (1294001, "回购股份价格上限由不超过人民币40.00元/股（含）调整为不超过人民币39.74元/股（含）"),
                 (1294002, "公司通过集中竞价交易方式首次回购股份25.30万股"),
                 (1320005, "2025年11月5日，公司本次回购股份时间届满，回购计划实施完毕"),
                 (1364000, "第二个锁定期已于2026年5月21日届满"),
                 (1364002, "以非交易过户的方式过户至公司第二期员工持股计划证券账户")],
        note="回原文核验：6 块逐块给出各自事件的日期与数量；候选规则另命中 1244001（同一调价事件的另一篇公告表述），核验后不重复计入 gold。单篇文档无法覆盖全部事件，属 1 跳汇集。",
    ),
    dict(
        qid="PE-15", task_type="事件型", gold_hop_depth=1, time_constraint="有", window=W30,
        question="最近30天（2026年8月26日至2026年9月25日）内，格力电器实施的事件包括哪些，调整后的回购价格上限是多少元/股？",
        reference_answer="2026年8月27日实施2025年年度权益分派（每10股派发现金股利20.00元，除权除息日08-27），并据此将回购价格上限由56.55元/股调整为54.55元/股。",
        gold=[1205000, 1205002, 1205003], docs=[1205],
        rule=dict(kind="doc_chunks", doc_ids=[1205], note="候选来自 doc 1205 的全部文本块"),
        edges_spec=[("000651", "PARTICIPATES_IN", "EVT-0272"), ("000651", "PARTICIPATES_IN", "EVT-0273")],
        anchors=[(1205000, "调整后回购价格上限：54.55元/股"), (1205002, "除权除息日为：2026年8月27日"),
                 (1205003, "56.55元/股-1.9998230元/股=54.55元/股")],
        note="回原文核验：1205000 给出调整前后价格与生效日，1205002 给出权益分派的登记日与除权除息日，1205003 给出计算过程与《上市公司股份回购规则》依据。doc 1205 在 66 篇内（2026-06-30、2026-08-27），窗口只保留 08-27 的两个事件。",
    ),
    # ---------------- 事件型 × 2 跳 ----------------
    dict(
        qid="PE-16", task_type="事件型", gold_hop_depth=2, time_constraint="无", window=None,
        question="平安银行与伊利股份共同参与的事件是什么？",
        reference_answer="交易商协会接受伊利股份债务融资工具注册（注册通知书编号中市协注〔2026〕DFI57号）；平安银行是该项注册的联席主承销商之一。",
        gold=[1183000, 1183001], docs=[1183],
        rule=dict(kind="shared_events", company_ids=["000001", "600887"], note="平安银行与伊利股份的共同参与事件 EVT-0236"),
        edges_spec=[("000001", "PARTICIPATES_IN", "EVT-0236"), ("600887", "PARTICIPATES_IN", "EVT-0236")],
        anchors=[(1183000, "交易商协会接受公司债务融资工具注册"),
                 (1183001, "由中信银行股份有限公司、平安银行股份有限公司")],
        note="回原文核验：1183000 给出伊利股份收到《接受注册通知书》与事件本身，1183001 才列出平安银行为联席主承销商之一；两块合起来才能确认“共同参与”，属跨实体 2 跳。",
    ),
    dict(
        qid="PE-17", task_type="事件型", gold_hop_depth=2, time_constraint="无", window=None,
        question="中工国际全资子公司中国中元与哪家公司签署了储能电站工程总承包合同，合同金额是多少？",
        reference_answer="与安徽元控储充新能源科技有限公司签署安徽省合肥市长丰县100MW/102MWh独立混合储能电站工程总承包合同，合同金额人民币112,738.00万元。",
        gold=[1373000, 1373001], docs=[1373],
        rule=dict(kind="shared_events", company_ids=["002051", "HCONF-0008"], note="中工国际与元控储充（HCONF-0008）的共同参与事件 EVT-0496"),
        edges_spec=[("002051", "PARTICIPATES_IN", "EVT-0496"), ("HCONF-0008", "PARTICIPATES_IN", "EVT-0496"),
                    ("HCONF-0003", "PARTICIPATES_IN", "EVT-0496")],
        anchors=[(1373000, "安徽省合肥市长丰县100MW/102MWh独立混合储能电站工程总承包合同"),
                 (1373001, "发包人：安徽元控储充新能源科技有限公司")],
        note="回原文核验：1373000 给出签约主体、项目名称与金额；1373001 给出“发包人：安徽元控储充新能源科技有限公司／承包人：中国中元国际工程有限公司”。三家参与方中的中国中元与元控储充都是人工确认写入的 HCONF 公司节点（只有名称、没有 stock_code），两家公司节点经事件 EVT-0496 相连，属 2 跳。",
    ),
    dict(
        qid="PE-18", task_type="事件型", gold_hop_depth=2, time_constraint="有",
        window=_w("2012年4月1日至2012年4月30日", "2012-04-01", "2012-04-30"),
        question="2012年4月1日至2012年4月30日期间，中国铁建财务有限公司由哪家机构批准开业运营？",
        reference_answer="经原中国银监会（银监复〔2012〕137号文）批准，于2012年4月18日正式开业运营。",
        gold=[1130000], docs=[1130],
        rule=dict(kind="event_org", event_ids=["EVT-0161"], note="EVT-0161 的 ISSUED_BY 边指向原中国银监会"),
        edges_spec=[("601186", "PARTICIPATES_IN", "EVT-0161"), ("EVT-0161", "ISSUED_BY", "INST-0122")],
        anchors=[(1130000, "财务公司于2012年4月18日经原中国银监会银监复〔2012〕137号文批准正式开业运营")],
        note="回原文核验：1130000 同时给出日期、批准机构与文号。doc 1130 在 66 篇内（2012-04-18、2026-06-30），窗口内只剩 2012-04-18 的开业事件，2026-06-30 的业绩事件被过滤。",
    ),
    # ---------------- 关系型 × 0 跳 ----------------
    dict(
        qid="PE-19", task_type="关系型", gold_hop_depth=0, time_constraint="无", window=None,
        question="天邑股份与中国电信集团有限公司、中国电信股份有限公司之间是否存在关联关系？",
        reference_answer="不存在关联关系；公告同时说明两家中国电信系公司是公司的长期客户、履约能力有保证。",
        gold=[1533005], docs=[1533],
        rule=dict(kind="doc_chunks", doc_ids=[1533], note="候选来自 doc 1533 的全部文本块"),
        edges_spec=[],
        anchors=[(1533005, "中国电信集团有限公司、中国电信股份有限公司与公司及公司董事、高级管理人员不存在关联关系")],
        note="回原文核验：1533005 逐字写明“不存在关联关系”，并给出“长期客户”的定性；该关系在原文直接给出，属文本型 0 跳。",
    ),
    dict(
        qid="PE-20", task_type="关系型", gold_hop_depth=0, time_constraint="无", window=None,
        question="中国石化集团公司持有中国石化多少股份（按公告披露）？",
        reference_answer="持有中国石化69.95%股份（含间接持股），与其联系人构成公司的关联人。",
        gold=[1082021], docs=[1082],
        rule=dict(kind="doc_chunks", doc_ids=[1082], note="候选来自 doc 1082 的全部文本块"),
        edges_spec=[],
        anchors=[(1082021, "持有本公司69.95%股份（含间接持股）的股东")],
        note="回原文核验：1082021 在“上海上市规则和香港上市规则的要求”一节写明持股比例与关联人定性；属文本型 0 跳。",
    ),
    dict(
        qid="PE-21", task_type="关系型", gold_hop_depth=0, time_constraint="有",
        window=_w("2026年7月1日至2026年7月31日", "2026-07-01", "2026-07-31"),
        question="2026年7月1日至2026年7月31日期间，中国三峡集团为G三峡EB2补充担保及信托登记的过程中，中信证券承担什么角色，登记机构是谁？",
        reference_answer="中信证券为G三峡EB2的受托管理人（担保及信托财产以其名义持有）；登记机构为中国证券登记结算有限责任公司上海分公司。",
        gold=[1293004], docs=[1293],
        rule=dict(kind="doc_chunks", doc_ids=[1293], note="候选来自 doc 1293 的全部文本块"),
        edges_spec=[],
        anchors=[(1293004, "向中国证券登记结算有限责任公司上海分公司申请就G三峡EB2补充的担保及信托财产"),
                 (1293004, "上述担保及信托财产将以受托管理人中信证券名义持有")],
        note="回原文核验：1293004 逐字给出中信证券的受托管理人角色与登记机构。doc 1293 在 66 篇内（2022-06-06、2026-07-16、2026-07-17），窗口只保留 2026-07 的两个事件，2022-06-06 的发行事件被过滤。",
    ),
    # ---------------- 关系型 × 1 跳 ----------------
    dict(
        qid="PE-22", task_type="关系型", gold_hop_depth=1, time_constraint="无", window=None,
        question="平安银行披露的董事及高级管理人员包括哪些人？",
        reference_answer="董事长谢永林，行长冀光恒，董事郭晓涛、付欣、蔡方方、项有志、高鹏，副行长吴雷鸣等。",
        gold=[1200000, 1231000, 1274001, 1337000, 1355000], docs=[1200, 1231, 1274, 1337, 1355],
        rule=dict(kind="company_persons", company_ids=["000001"], note="HAS_EXECUTIVE 143 条边中属于平安银行的 10 条"),
        edges_spec=[("000001", "HAS_EXECUTIVE", "PER-0010"), ("000001", "HAS_EXECUTIVE", "PER-0029"),
                    ("000001", "HAS_EXECUTIVE", "PER-0062"), ("000001", "HAS_EXECUTIVE", "PER-0288"),
                    ("000001", "HAS_EXECUTIVE", "PER-0308"), ("000001", "HAS_EXECUTIVE", "PER-0331"),
                    ("000001", "HAS_EXECUTIVE", "PER-0370"), ("000001", "HAS_EXECUTIVE", "PER-0384")],
        anchors=[(1337000, "董事长谢永林"), (1231000, "冀光恒行长"),
                 (1355000, "核准吴雷鸣先生平安银行股份有限公司副行长的任职资格"),
                 (1274001, "董事长谢永林、董事郭晓涛、付欣和蔡方方回避表决"),
                 (1200000, "核准高鹏先生平安银行股份有限公司董事的任职资格")],
        note="回原文核验：10 条 HAS_EXECUTIVE 边落在 5 个不同文本块（1337000、1231000、1355000、1274001、1200000），逐块确认人名与职务；名单跨 4 篇文档，属 1 跳汇集。保留说明（2026-09-28，回应复核 D6）：1274001 里的「董事长谢永林、董事郭晓涛、付欣和蔡方方」四人及其职务已被 1337000 覆盖，按 题目模板.md 第三节 第 3 条本可删；本次**保留**——该块是同一批人名在另一篇公告（doc 1274 董事会决议）中的原文表述，保留只抬高 gold 分母、使 Recall 偏保守，且删块会改变已冻结的四项指标读数与 检索产出 的既有产物数值。按「不改既有产物数值」的约束保留并在此登记。",
    ),
    dict(
        qid="PE-23", task_type="关系型", gold_hop_depth=1, time_constraint="无", window=None,
        question="中天科技披露的董事及高级管理人员包括哪些人？",
        reference_answer="董事长薛驰，总经理陆伟，财务负责人高洪时，董事会秘书胡梓木，独立董事王益民、王军、沈洁。",
        gold=[1112001, 1148000], docs=[1112, 1148],
        rule=dict(kind="company_persons", company_ids=["600522"], note="HAS_EXECUTIVE 边的证据块"),
        edges_spec=[("600522", "HAS_EXECUTIVE", "PER-0278"), ("600522", "HAS_EXECUTIVE", "PER-0294"),
                    ("600522", "HAS_EXECUTIVE", "PER-0341"), ("600522", "HAS_EXECUTIVE", "PER-0382")],
        anchors=[(1112001, "公司董事长薛驰先生"), (1148000, "本次会议由董事长薛驰先生主持")],
        note="回原文核验：1112001 给出业绩说明会参加人员（董事长、独立董事、总经理、财务负责人、董事会秘书），1148000 的董事会决议公告再次确认董事长薛驰；两块跨两篇文档，候选规则另命中 1148000 之外的重复块，核验后不重复计入。",
    ),
    dict(
        qid="PE-24", task_type="关系型", gold_hop_depth=1, time_constraint="有",
        window=_w("2026年8月1日至2026年8月15日", "2026-08-01", "2026-08-15"),
        question="2026年8月1日至2026年8月15日期间，宁德时代因实施2026年中期分红而调整后的回购价格上限是多少元/股？",
        reference_answer="由573元/股调整为571.60元/股，自2026年8月10日（除权除息日）起生效。",
        gold=[1257009, 1257010], docs=[1257],
        rule=dict(kind="doc_chunks", doc_ids=[1257],
                  note="候选来自 2026 年中期分红实施公告的全部文本块；事件侧由登记的 PARTICIPATES_IN 边另行核验"),
        edges_spec=[("300750", "PARTICIPATES_IN", "EVT-0337")],
        anchors=[(1257009, "公司回购价格上限由573元/股调整为571.60元/股"),
                 (1257010, "571.60元/股（保留两位小数")],
        note="回原文核验：1257009 给出调整前后价格，1257010 补齐计算式收尾，两块合起来才是完整表述。doc 1257 在 66 篇内（2026-07-25、2026-08-10），窗口只保留 08-10 的分派与调价事件。",
    ),
    # ---------------- 关系型 × 2 跳（含 4 道“关系型 + 2 跳 + 有时间约束”的压力格） ----------------
    dict(
        qid="PE-25", task_type="关系型", gold_hop_depth=2, time_constraint="无", window=None,
        question="新北洋控股子公司荣鑫科技中标的中国工商银行2026年度网点新型客户交互终端项目，招标人与中标人分别是谁？",
        reference_answer="招标人为中国工商银行股份有限公司；中标人为威海新北洋荣鑫科技股份有限公司（招标代理机构为中信国际招标有限公司）。",
        gold=[1513000], docs=[1513],
        rule=dict(kind="shared_events", company_ids=["002376", "601398"], note="新北洋与工商银行的共同参与事件 EVT-0677／EVT-0996"),
        edges_spec=[("002376", "PARTICIPATES_IN", "EVT-0677"), ("601398", "PARTICIPATES_IN", "EVT-0677")],
        anchors=[(1513000, "确认荣鑫科技为“中国工商银行股份有限公司2026年度网点新型客户交互终端项目中标人")],
        note="回原文核验：1513000 同时给出招标人、中标人与招标代理机构；两家公司节点经事件 EVT-0677 相连，属 2 跳（同一事件在两篇公告里的重复块只保留公告正文块）。",
    ),
    dict(
        qid="PE-26", task_type="关系型", gold_hop_depth=2, time_constraint="无", window=None,
        question="天邑股份与中国电信集团有限公司、中国电信股份有限公司共同签署过哪些集中采购框架协议？",
        reference_answer="两份：《中国电信家庭FTTR产品（2026年-2027年）集中采购项目》框架协议（2026年8月3日签署）与《中国电信天翼智屏产品（2026年）集中采购项目》框架协议（2026年7月13日签署）。",
        gold=[1502001, 1502005, 1533001, 1533005], docs=[1502, 1533],
        rule=dict(kind="doc_chunks", doc_ids=[1502, 1533],
                  note="候选来自两篇公告的全部文本块；共同参与事件 EVT-0662／EVT-0704 由登记的 PARTICIPATES_IN 边另行核验"),
        edges_spec=[("300504", "PARTICIPATES_IN", "EVT-0662"), ("HCONF-0004", "PARTICIPATES_IN", "EVT-0662"),
                    ("300504", "PARTICIPATES_IN", "EVT-0704"), ("HCONF-0005", "PARTICIPATES_IN", "EVT-0704")],
        anchors=[(1502001, "《中国电信家庭FTTR产品（2026年-2027年）集中采购项目设备及相关服务采购框架协议"),
                 (1533001, "《中国电信天翼智屏产品（2026年）集中采购项目设备及相关服务采购框架协议"),
                 (1502005, "买方：中国电信集团有限公司、中国电信股份有限公司"),
                 (1533005, "买方：中国电信集团有限公司、中国电信股份有限公司")],
        note="回原文核验（T9 初版）＋第三方复核裁定（T9 追加）：1502001／1533001 逐字给出两份框架协议全称（FTTR 与天翼智屏），1502005／1533005 分别给出买卖双方与签署时间（2026年8月3日／2026年7月13日），四块合起来才是“共同签署过哪些框架协议”的完整答案；两家中国电信系节点是人工确认写入的 HCONF 节点（只有名称、没有 stock_code），本题正是为覆盖该边界。参与本次确认的两家（kimi＋zhipu）一致指出原 gold 只含协议正文块、不含协议名称块（已按作者指示剥离的一条线同向，只作留痕），回原文确认属实，故由 2 块补为 4 块。",
    ),
    dict(
        qid="PE-27", task_type="关系型", gold_hop_depth=2, time_constraint="有",
        window=_w("2026年7月1日至2026年7月20日", "2026-07-01", "2026-07-20"),
        question="2026年7月1日至2026年7月20日期间，天邑股份与中国电信系公司签订的框架协议中，买卖双方分别是谁，协议签署时间是什么时候？",
        reference_answer="买方为中国电信集团有限公司、中国电信股份有限公司；卖方为四川天邑康和通信股份有限公司；签署时间为2026年7月13日。",
        gold=[1533001, 1533005], docs=[1533],
        rule=dict(kind="doc_chunks", doc_ids=[1533],
                  note="候选来自该公告的全部文本块；共同参与事件 EVT-0704 由登记的 PARTICIPATES_IN 边另行核验"),
        edges_spec=[("300504", "PARTICIPATES_IN", "EVT-0704"), ("HCONF-0004", "PARTICIPATES_IN", "EVT-0704"),
                    ("HCONF-0005", "PARTICIPATES_IN", "EVT-0704")],
        anchors=[(1533001, "确定公司为《中国电信天翼智屏产品（2026年）集中采购项目》成交人"),
                 (1533005, "买方：中国电信集团有限公司、中国电信股份有限公司")],
        note="回原文核验：1533001 给出成交与签约事实，1533005 给出买卖双方与签署时间。doc 1533 在 66 篇内（2026-07-01、2026-07-13），窗口只保留 07-13 的签约事件，07-01 的成交事件被过滤。",
    ),
    dict(
        qid="PE-28", task_type="关系型", gold_hop_depth=2, time_constraint="有",
        window=_w("2026年9月1日至2026年9月30日", "2026-09-01", "2026-09-30"),
        question="2026年9月1日至2026年9月30日期间，隆基绿能依据《上海证券交易所上市公司自律监管指引第12号——可转换公司债券》披露的事件是什么？",
        reference_answer="“隆22转债”预计满足转股价格向下修正条件的提示性公告事件：自2026年9月1日起至9月14日已有十个交易日收盘价低于当期转股价格的85%。",
        gold=[1050006], docs=[1050],
        rule=dict(kind="event_org", event_ids=["EVT-0067"], note="EVT-0067 的 RELATED_TO 边指向该指引（源块 1050006）"),
        edges_spec=[("601012", "PARTICIPATES_IN", "EVT-0067"), ("EVT-0067", "RELATED_TO", "POL-0013")],
        anchors=[(1050006, "《上海证券交易所上市公司自律监管指引第12号——可转换公司债券》"),
                 (1050006, "自2026年9月1日起至2026年9月14日")],
        note="回原文核验：1050006 既给出事件（预计触发转股价格向下修正条件）又逐字引用该指引。doc 1050 在 66 篇内（2022-01-05、2026-09-14），窗口只保留 09-14 的事件。",
    ),
    dict(
        qid="PE-29", task_type="关系型", gold_hop_depth=2, time_constraint="有",
        window=_w("2026年9月1日至2026年9月30日", "2026-09-01", "2026-09-30"),
        question="2026年9月1日至2026年9月30日期间，长城汽车依据《上市公司股权激励管理办法》发生的股票期权行权事件是什么？",
        reference_answer="两起：2023年股票期权激励计划首次授予股票期权第二个行权期（期权代码1000000573，有效期2026年9月11日至2027年1月25日）与预留授予股票期权第一个行权期（期权代码1000000794，有效期2026年9月11日至2027年1月23日），均于2026年9月11日开始行权。",
        gold=[1001000, 1001001], docs=[1001],
        rule=dict(kind="event_org", event_ids=["EVT-0001"], note="EVT-0001 的 RELATED_TO 边指向《上市公司股权激励管理办法》（源块 1001000）"),
        edges_spec=[("601633", "PARTICIPATES_IN", "EVT-0001"), ("EVT-0001", "RELATED_TO", "POL-0009")],
        anchors=[(1001000, "根据《上市公司股权激励管理办法》"),
                 (1001001, "预留授予股票期权于2026年1月24日进入第一个行权期"),
                 (1001001, "行权期有效期为2026年9月11日-2027年1月25日")],
        note="回原文核验（T9 初版）＋第三方复核裁定（T9 追加）：1001000 给出政策依据与“进入第二个行权期”的开头，1001001 在同一块内并列披露首次授予第二个行权期与预留授予第一个行权期两条事件，二者行权期均自 2026年9月11日 起算，故答案须一并给出；gold 证据块仍为 1001000、1001001（块数不变，答案补全）。doc 1001 在 66 篇内（2026-09-11、2026-10-01），窗口只保留 09-11 的行权事件，2026-10-01 的限制行权期事件被过滤。",
    ),
    dict(
        qid="PE-30", task_type="关系型", gold_hop_depth=2, time_constraint="有", window=W30,
        question="最近30天（2026年8月26日至2026年9月25日）内，美的集团依据《关于上市公司实施员工持股计划试点的指导意见》办理的持股计划事件是什么，过户股份数量是多少？",
        reference_answer="2026年A股持股计划非交易过户完成：15,772,385股过户至持股计划专用证券账户，占公司总股本0.21%，锁定期为2026年9月3日至2028年9月2日。",
        gold=[1106000, 1106001, 1106002], docs=[1106],
        rule=dict(kind="doc_chunks", doc_ids=[1106],
                  note="候选来自该公告的全部文本块；事件与政策由登记的 RELATED_TO／PARTICIPATES_IN 边另行核验"),
        edges_spec=[("000333", "PARTICIPATES_IN", "EVT-0135"), ("EVT-0135", "RELATED_TO", "POL-0048"),
                    ("INST-0062", "PARTICIPATES_IN", "EVT-0135")],
        anchors=[(1106000, "根据《关于上市公司实施员工持股计划试点的指导意见》"),
                 (1106001, "开立了本次员工持股计划专用证券账户"),
                 (1106002, "过户股份数量为15,772,385股")],
        note="回原文核验：1106000 给出政策依据，1106001 给出专户开立与过户登记，1106002 给出过户数量与锁定期。doc 1106 在 66 篇内（2025-12-09、2026-09-03），窗口只保留 09-03 的过户完成事件。",
    ),
]


# ---------------------------------------------------------------------------
# 4. 候选 gold 抽取与逐条核验
# ---------------------------------------------------------------------------
def derive_candidate_chunks(inputs: Inputs, spec):
    """按冻结表登记的规则重算候选 gold 证据块（人工核验前的候选集合）。"""
    rule = spec["rule"]
    kind = rule["kind"]
    if kind == "doc_chunks":
        out = set()
        for doc_id in rule["doc_ids"]:
            out |= set(inputs.chunks_by_doc.get(int(doc_id), ()))
        return out, "候选口径＝文档内全部文本块；gold＝经回原文核验后的子集（16 道文本型候选题中 15 道的 gold 是该文档全部块的真子集）"
    if kind == "event_evidence":
        out = set()
        for ev in rule["event_ids"]:
            out |= set(inputs.event_chunks.get(ev, ()))
        return out, "事件语义边上的 source_chunk_id"
    if kind == "company_events":
        out = set()
        for cid in rule["company_ids"]:
            for ev in inputs.company_events.get(cid, ()):
                out |= set(inputs.event_chunks.get(ev, ()))
        return out, "公司参与事件的证据块"
    if kind == "company_events_match":
        out = set()
        for cid in rule["company_ids"]:
            for ev in sorted(inputs.company_events.get(cid, ())):
                name = inputs.event_name(ev)
                if any(kw in name for kw in rule["keywords"]):
                    out |= set(inputs.event_chunks.get(ev, ()))
        return out, "公司参与且事件名命中关键词的事件证据块"
    if kind == "company_persons":
        out = set()
        for cid in rule["company_ids"]:
            for edge in inputs.edges:
                if edge["head_id"] == cid and edge["relation"] == "HAS_EXECUTIVE" and edge["source_chunk_id"]:
                    out.add(int(edge["source_chunk_id"]))
        return out, "公司 HAS_EXECUTIVE 边上的 source_chunk_id"
    if kind == "shared_events":
        want = set(rule["company_ids"])
        out = set()
        for ev, comps in inputs.event_companies.items():
            if len(comps & want) >= 2:
                out |= set(inputs.event_chunks.get(ev, ()))
        return out, "给定公司共同参与事件的证据块"
    if kind == "event_org":
        out = set()
        for ev in rule["event_ids"]:
            out |= set(inputs.event_chunks.get(ev, ()))
            tails = set(inputs.event_orgs.get(ev, ())) | set(inputs.event_policies.get(ev, ()))
            for tail in tails:
                for edge in inputs.edges:
                    if edge["head_id"] == ev and edge["tail_id"] == tail and edge["source_chunk_id"]:
                        out.add(int(edge["source_chunk_id"]))
        return out, "事件到机构／政策边上的 source_chunk_id"
    raise SystemExit("未知的候选规则：%s" % kind)


def build_rows(inputs: Inputs, verbose=True):
    """把冻结表固化为 questions.jsonl 的行，并逐条做构建期断言。"""
    problems = []
    qids = [q["qid"] for q in FROZEN_QUESTIONS]
    if len(qids) != len(set(qids)):
        raise SystemExit("qid 重复")
    if len(specs := FROZEN_QUESTIONS) != 30:
        raise SystemExit("冻结表题量不是 30：%d" % len(specs))
    missing_review = [q for q in qids if q not in THIRD_PARTY_VERDICTS]
    if missing_review:
        raise SystemExit("以下题缺第三方盲标复核登记：%s" % missing_review)
    if len(inputs.time_subset) != TIME_SUBSET_EXPECTED:
        raise SystemExit("含 >=2 个不同 event_time 日期的文档为 %d 篇，与 v1.2 现行口径的 %d 篇不符，停止构建"
                         % (len(inputs.time_subset), TIME_SUBSET_EXPECTED))

    rows = []
    for spec in FROZEN_QUESTIONS:
        qid = spec["qid"]
        task_type, hop, tlabel = spec["task_type"], spec["gold_hop_depth"], spec["time_constraint"]
        if task_type not in TASK_TYPES:
            problems.append("%s 任务类型越界：%s" % (qid, task_type))
        if hop not in HOP_DEPTHS:
            problems.append("%s 路径深度越界：%s" % (qid, hop))
        if tlabel not in TIME_LABELS:
            problems.append("%s 时间约束标签越界：%s" % (qid, tlabel))
        if (tlabel == "有") != (spec["window"] is not None):
            problems.append("%s 时间约束标签与窗口不一致" % qid)

        window = resolve_window(spec["window"])
        gold = list(spec["gold"])
        if not (GOLD_MIN <= len(gold) <= GOLD_MAX):
            problems.append("%s gold 条数越界：%d" % (qid, len(gold)))
        if len(gold) != len(set(gold)):
            problems.append("%s gold 有重复 chunk_id" % qid)

        # 候选规则 -> 候选集合（人工核验前的候选池），核验后的 gold 必须是其子集
        candidate, rule_text = derive_candidate_chunks(inputs, spec)
        extra = sorted(set(gold) - candidate)
        if extra:
            problems.append("%s gold 不在候选规则命中集合内：%s" % (qid, extra))

        gold_docs = set()
        for cid in gold:
            if cid not in inputs.chunks:
                problems.append("%s gold 块在 chunks.jsonl 中不存在：%d" % (qid, cid))
                continue
            gold_docs.add(inputs.doc_of_chunk(cid))
        if gold_docs != set(int(d) for d in spec["docs"]):
            problems.append("%s 声明文档与 gold 所在文档不一致：%s vs %s" % (qid, sorted(gold_docs), spec["docs"]))
        if tlabel == "有" and not gold_docs <= set(inputs.time_subset):
            problems.append("%s 的 gold 文档不在“含 >=2 个不同日期”的 %d 篇内：%s"
                            % (qid, TIME_SUBSET_EXPECTED, sorted(gold_docs - set(inputs.time_subset))))

        # 核验锚点：逐条到 chunks.jsonl 的 content 里比对（忽略空白）
        for cid, anchor in spec["anchors"]:
            if cid not in inputs.chunks:
                problems.append("%s 锚点块不存在：%d" % (qid, cid))
                continue
            if normalize_text(anchor) not in normalize_text(inputs.chunks[cid]["content"]):
                problems.append("%s 锚点在块 %d 的原文中未命中：%s" % (qid, cid, anchor))
        if set(a[0] for a in spec["anchors"]) - set(gold):
            problems.append("%s 锚点块必须都在 gold 内" % qid)

        # 图路径：登记的每条关系边都要真实存在，且其 source_chunk_id 落在候选集合内
        graph_path = []
        for head, relation, tail in spec["edges_spec"]:
            edge = inputs.edge_row(head, relation, tail)
            if edge is None:
                problems.append("%s 登记的边不存在：%s -%s-> %s" % (qid, head, relation, tail))
                continue
            graph_path.append({
                "head_id": head, "relation": relation, "tail_id": tail,
                "source_doc_id": edge["source_doc_id"], "source_chunk_id": edge["source_chunk_id"],
            })
            if edge["source_chunk_id"] and int(edge["source_chunk_id"]) not in candidate:
                problems.append("%s 边的 source_chunk_id 不在候选集合内：%s" % (qid, edge["source_chunk_id"]))
        if hop == 0 and spec["edges_spec"]:
            problems.append("%s 标 0 跳却登记了关系边" % qid)
        if hop >= 1 and len(spec["edges_spec"]) < hop:
            problems.append("%s 标 %d 跳但登记的边不足" % (qid, hop))

        # 题面里的时间窗口字样
        if tlabel == "有":
            lo, hi = window["lo"], window["hi"]
            if window["label"] in RELATIVE_WINDOW_LABELS:
                if window["label"] not in spec["question"]:
                    problems.append("%s 题面未出现相对时间词：%s" % (qid, window["label"]))
            if _cn_date(lo) not in spec["question"] or _cn_date(hi) not in spec["question"]:
                problems.append("%s 题面未写出窗口两端日期：%s~%s" % (qid, lo, hi))

        source_material = []
        for doc_id in sorted(int(d) for d in spec["docs"]):
            doc = inputs.docs[doc_id]
            source_material.append({
                "doc_id": doc_id, "title": doc["title"], "source": doc["source"],
                "url": doc["url"], "publish_time": doc["publish_time"], "category": doc["category"],
            })

        rows.append({
            "qid": qid,
            "question": spec["question"],
            "task_type": task_type,
            "gold_hop_depth": hop,
            "time_constraint": tlabel,
            "time_window": window,
            "reference_answer": spec["reference_answer"],
            "gold_evidence_chunk_ids": sorted(gold),
            "gold_evidence_doc_ids": sorted(gold_docs),
            "gold_evidence_count": len(gold),
            "graph_path": graph_path,
            "source_material": source_material,
            "gold_evidence_rule": rule_text,
            "gold_verified_by": VERIFIED_BY,
            "gold_review_status": REVIEW_STATUS,
            "third_party_review": third_party_review_block(qid),
            "gold_verify_anchors": [
                {"chunk_id": cid, "quote": quote} for cid, quote in spec["anchors"]
            ],
            "gold_verify_note": spec["note"],
        })

    # ---- 题集层面的分布断言（T9 设计约束 2 与 4）----
    cells = {}
    band_hit = {b: 0 for b in GOLD_BANDS}
    for row in rows:
        key = (row["task_type"], row["gold_hop_depth"], row["time_constraint"])
        cells[key] = cells.get(key, 0) + 1
        for lo, hi in GOLD_BANDS:
            if lo <= row["gold_evidence_count"] <= hi:
                band_hit[(lo, hi)] += 1
    for tt in TASK_TYPES:
        for hd in HOP_DEPTHS:
            for tl in TIME_LABELS:
                if cells.get((tt, hd, tl), 0) == 0:
                    problems.append("标签组合缺实例：%s × %d 跳 × 时间约束%s" % (tt, hd, tl))
    for band, cnt in band_hit.items():
        if cnt == 0:
            problems.append("gold 条数档位 %d~%d 无实例" % band)
    if cells.get(("关系型", 2, "有"), 0) < 4:
        problems.append("压力格“关系型 × 2 跳 × 有时间约束”不足 4 题：%d" % cells.get(("关系型", 2, "有"), 0))

    if problems:
        print("[T9] 构建期断言未通过，共 %d 条：" % len(problems))
        for p in problems:
            print("    !! %s" % p)
        raise SystemExit(2)

    if verbose:
        print("[T9] 构建期断言全部通过；题量 %d；含 >=2 个不同日期的文档 %d 篇（与 v1.2 现行口径一致）"
              % (len(rows), len(inputs.time_subset)))
        print("[T9] 标签分布（任务类型 × 路径深度 × 时间约束）：")
        for tt in TASK_TYPES:
            for hd in HOP_DEPTHS:
                got = {tl: cells.get((tt, hd, tl), 0) for tl in TIME_LABELS}
                print("      %-4s × %d 跳：无 %d 题 / 有 %d 题" % (tt, hd, got["无"], got["有"]))
        dist = {}
        for row in rows:
            dist[row["gold_evidence_count"]] = dist.get(row["gold_evidence_count"], 0) + 1
        print("[T9] gold 条数分布：" + "、".join("%d 条 %d 题" % (k, dist[k]) for k in sorted(dist)))
    return rows


# ---------------------------------------------------------------------------
# 5. 三个 profile
# ---------------------------------------------------------------------------
def profile_freeze(inputs: Inputs, out_path):
    rows = build_rows(inputs)
    config.write_jsonl(out_path, rows)
    print("[T9] 已固化 %d 题：%s" % (len(rows), out_path))
    return rows


def profile_verify(inputs: Inputs, path):
    rows = build_rows(inputs, verbose=False)
    on_disk = list(config.iter_jsonl(path))
    if len(on_disk) != len(rows):
        raise SystemExit("磁盘上的题量与冻结表不一致：%d vs %d" % (len(on_disk), len(rows)))
    for a, b in zip(rows, on_disk):
        if config.stable_json(a) != config.stable_json(b):
            raise SystemExit("第 %s 题与磁盘内容不一致" % a["qid"])
    print("[T9] verify 通过：%d 题与冻结表逐题一致；磁盘文件 %s" % (len(rows), path))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(description="T9 预实验问题集的确定性构建（只读输入）")
    parser.add_argument("--profile", choices=["candidates", "freeze", "verify"], default="freeze")
    parser.add_argument("--out", default=None, help="候选池或 questions.jsonl 的落点（默认取 config.QUESTION_FILES）")
    args = parser.parse_args(argv)

    inputs = Inputs()
    if args.profile == "candidates":
        profile_candidates(inputs, args.out)
    elif args.profile == "freeze":
        profile_freeze(inputs, args.out or config.QUESTION_FILES["questions"])
    else:
        profile_verify(inputs, args.out or config.QUESTION_FILES["questions"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
