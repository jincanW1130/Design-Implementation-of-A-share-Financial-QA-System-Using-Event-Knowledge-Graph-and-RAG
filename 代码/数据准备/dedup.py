# -*- coding: utf-8 -*-
r"""T4a 文本级去重（第 5 阶段数据准备管线）。

契约（`代码\数据准备\README.md` 一、二、三.3.7；《12-第5阶段任务书》第五节 硬约束 3／5／7、第八节）：

    输入  raw\{doc_id}.json          只读；raw\ 采集后不可修改（《12》第4.2节）
    输出  reports\dedup_log.jsonl    每条冲突一行：双方 doc_id、命中的规则、保留方

三条判重口径全部取自 config.DEDUP（脚本内不写死）：
    1) url        全数据集唯一（同源同链接只入一次）
    2) title      规范化后唯一（去首尾空白、去全角空格、合并连续空白）
    3) 正文指纹   SHA-256 前 N 位唯一（config.DEDUP["content_fingerprint"] == "sha256_16"）

冲突裁决：保留 publish_time 更早的一条；并列时取 content_url/page_url 更短的一条；
仍并列取 doc_id 更小的一条（用户指定口径）。

《12》第八节 修订后的监管公开信息口径：同题文档（行政处罚决定书等）先按"原标题（当事人）"构造
后才允许判重；若仍冲突，只允许用来源文档自身已有的文号／索引号消歧，不得臆造标题。本脚本据此
在 title 判重键上做两步：① 标题规范化；② 若 category 为监管公开信息且来源自带文号／索引号
（config.DEDUP["regulator_title_disambiguation"] 打开时），把该标识并入判重键——标识只来自
来源字段，不生成当事人名；没有标识的文档仍按规范化标题判重。

被淘汰的文档**不改动 raw\ 文件**：raw\ 是《12》第4.2节 规定的不可变目录，因此去重结论只写
`reports\dedup_log.jsonl`，由 clean.py 读取后排除。（README 第一节 表格中"对 raw\ 打重复标记"
的写法与《12》第4.2节 的不可变口径冲突，本实现按《12》与用户口径执行，已在交付报告中登记。）

依赖方向：正文指纹按 clean.py 的清洗结果计算、标题规范化复用 clean.py 的实现，从而使
clean\documents.jsonl 里 content_sha256_16 的唯一性由构造保证（《12》第八节"正文 SHA-256 前
16 位唯一"这一验收项落在 clean 产物上）。因此本脚本需与 clean.py 同目录部署。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  唯一参数来源，不得写死任何参数
from clean import clean_body, content_fingerprint, normalize_title, source_disambiguator  # noqa: E402

# 规则名（仅作日志标识；是否启用由 config.DEDUP 的键决定）
RULE_URL = "url"
RULE_TITLE = "title"
RULE_FINGERPRINT = "content_sha256_16"
RULE_KEY_KIND = {
    RULE_URL: "url",
    RULE_TITLE: "normalized_title",
    RULE_FINGERPRINT: "cleaned_body_sha256_16",
}
REGULATOR_CATEGORY = "监管公开信息"
TIE_BREAK_NOTE = "earlier_publish_time > shorter_content_url/page_url > smaller_doc_id"


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=r"第 5 阶段 T4a：文本级去重（只写 reports\dedup_log.jsonl，不改 raw\）"
    )
    parser.add_argument("--profile", choices=["v1", "pilot"], default="v1",
                        help="数据集形态：v1（默认）或 pilot")
    parser.add_argument("--dir", dest="dir_override", default=None,
                        help="仅供自测：把数据集根目录改到任意临时目录")
    parser.add_argument("--force", action="store_true",
                        help="忽略已完成标记，强制重跑本环节")
    return parser.parse_args(argv)


def resolve_root(args) -> str:
    if args.dir_override:
        return os.path.abspath(args.dir_override)
    return os.path.abspath(config.dataset_dir(args.profile))


# --------------------------------------------------------------------------
# 读入 raw\
# --------------------------------------------------------------------------
def collect_raw_paths(raw_dir: str):
    names = sorted(n for n in os.listdir(raw_dir)
                   if n.endswith(".json") and not n.startswith("_"))
    return [os.path.join(raw_dir, n) for n in names]


def load_raw_docs(raw_dir: str):
    docs = []
    seen = set()
    for path in collect_raw_paths(raw_dir):
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        if not isinstance(obj, dict) or "doc_id" not in obj:
            raise ValueError("raw 文件缺少 doc_id 字段：%s" % path)
        doc_id = int(obj["doc_id"])
        if doc_id in seen:
            raise ValueError("raw 目录内 doc_id 重复：%d" % doc_id)
        seen.add(doc_id)
        obj["_raw_path"] = path
        docs.append(obj)
    docs.sort(key=lambda d: int(d["doc_id"]))
    return docs


def is_up_to_date(outputs, inputs) -> bool:
    """已完成标记：所有输出都存在，且不比任何输入旧。"""
    if not all(os.path.exists(p) for p in outputs):
        return False
    if not inputs:
        return True
    return min(os.path.getmtime(p) for p in outputs) >= max(os.path.getmtime(p) for p in inputs)


# --------------------------------------------------------------------------
# 判重口径
# --------------------------------------------------------------------------
def active_rules():
    """按 config.DEDUP 的开关决定启用哪些规则（url → title → 正文指纹）。"""
    rules = []
    if config.DEDUP.get("url_unique"):
        rules.append(RULE_URL)
    if config.DEDUP.get("title_unique_within_dataset"):
        rules.append(RULE_TITLE)
    if config.DEDUP.get("content_fingerprint"):
        rules.append(RULE_FINGERPRINT)
    return rules


def effective_url(doc) -> str:
    """文档的对外链接：优先 content_url（正文链接），缺失时回退 page_url。"""
    return str(doc.get("content_url") or doc.get("page_url") or "").strip()


def publish_time(doc) -> str:
    return str(doc.get("publish_time") or "").strip()


def rule_key(rule: str, doc):
    """返回该规则下的判重键；None 表示该文档在此规则下不可比较（空键不参与判重）。"""
    if rule == RULE_URL:
        url = effective_url(doc)
        return url or None
    if rule == RULE_TITLE:
        title = normalize_title(doc.get("title"))
        if not title:
            return None
        if (config.DEDUP.get("regulator_title_disambiguation")
                and str(doc.get("category") or "") == REGULATOR_CATEGORY):
            tag = source_disambiguator(doc)
            if tag:
                return "%s（%s）" % (title, tag)
        return title
    if rule == RULE_FINGERPRINT:
        body = clean_body(doc.get("raw_text"))
        if not body:
            return None
        return content_fingerprint(body)
    raise ValueError("未知规则：%r" % rule)


def key_kind(rule: str, key: str, doc) -> str:
    """日志自解释用：本次判重键是纯规范化标题，还是并入来源文号／索引号之后的标题。"""
    if (rule == RULE_TITLE
            and str(doc.get("category") or "") == REGULATOR_CATEGORY
            and key != normalize_title(doc.get("title"))):
        return "normalized_title+source_wenhao/index_no"
    return RULE_KEY_KIND[rule]


def rank_key(doc):
    """保留优先级：publish_time 更早 > 链接更短 > doc_id 更小（空 publish_time 视为最晚）。"""
    pt = publish_time(doc)
    return (0 if pt else 1, pt, len(effective_url(doc)), int(doc["doc_id"]))


def decide_reason(winner, loser) -> str:
    """给出胜者胜出的那一条判定（日志的 decided_by 字段）。"""
    wp, lp = publish_time(winner), publish_time(loser)
    if wp != lp and (wp or lp):
        return "earlier_publish_time"
    if len(effective_url(winner)) != len(effective_url(loser)):
        return "shorter_url"
    return "smaller_doc_id"


def decide(docs, rules):
    """逐规则判重；被淘汰的文档从后续规则的比较池中移除。返回 (decisions, survivors)。"""
    alive = {int(d["doc_id"]): d for d in docs}
    decisions = []
    for rule in rules:
        groups = {}
        for doc_id in sorted(alive):
            key = rule_key(rule, alive[doc_id])
            if key is None:
                continue
            groups.setdefault(key, []).append(doc_id)
        for key in sorted(groups):
            members = groups[key]
            if len(members) < 2:
                continue
            ordered = sorted(members, key=lambda i: rank_key(alive[i]))
            winner, losers = ordered[0], ordered[1:]
            winner_doc = alive[winner]
            dropped_detail = []
            for doc_id in losers:
                loser_doc = alive[doc_id]
                dropped_detail.append({
                    "doc_id": doc_id,
                    "publish_time": publish_time(loser_doc),
                    "url_len": len(effective_url(loser_doc)),
                    "decided_by": decide_reason(winner_doc, loser_doc),
                })
                alive.pop(doc_id)
            decisions.append({
                "rule": rule,
                "key": key,
                "key_kind": key_kind(rule, key, winner_doc),
                "candidates": sorted(members),
                "winner": winner,
                "dropped": losers,
                "winner_publish_time": publish_time(winner_doc),
                "winner_url_len": len(effective_url(winner_doc)),
                "dropped_detail": dropped_detail,
                "tie_break": TIE_BREAK_NOTE,
            })
    return decisions, alive


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------
def write_jsonl(path: str, records) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=False) + "\n")
    os.replace(tmp, path)


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    t0 = time.perf_counter()
    args = parse_args(argv)
    root = resolve_root(args)
    raw_dir = os.path.join(root, "raw")
    reports_dir = os.path.join(root, "reports")
    log_path = os.path.join(reports_dir, "dedup_log.jsonl")

    if not os.path.isdir(raw_dir):
        print("[dedup] 错误：找不到 raw\\ 目录：%s" % raw_dir, file=sys.stderr)
        return 2
    raw_paths = collect_raw_paths(raw_dir)
    docs = load_raw_docs(raw_dir)
    if not docs:
        print("[dedup] 错误：raw\\ 目录内没有 {doc_id}.json：%s" % raw_dir, file=sys.stderr)
        return 2

    if not args.force and is_up_to_date([log_path], raw_paths):
        print("[dedup] 已完成，跳过（--force 可强制重跑）：%s" % log_path)
        return 0

    rules = active_rules()
    decisions, survivors = decide(docs, rules)
    write_jsonl(log_path, decisions)

    per_rule = {r: 0 for r in rules}
    dropped_total = 0
    for rec in decisions:
        per_rule[rec["rule"]] = per_rule.get(rec["rule"], 0) + 1
        dropped_total += len(rec["dropped"])
    print("[dedup] profile=%s dir=%s 输入=%d 条，冲突组=%d（%s），淘汰=%d，保留=%d，耗时=%.2fs"
          % (args.profile, root, len(docs), len(decisions),
             "，".join("%s:%d" % (k, v) for k, v in per_rule.items()),
             dropped_total, len(survivors), time.perf_counter() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
