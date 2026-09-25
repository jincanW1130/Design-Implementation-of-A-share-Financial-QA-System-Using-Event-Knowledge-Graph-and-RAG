# -*- coding: utf-8 -*-
r"""v21_report.py —— v2.1 定向补样的实测报告（只读，不改任何数据集）。

用法：

    python 代码\数据准备\v21_report.py

脚本把《v2.1 定向补样》要回答的问题逐条算出来并打印：

  1. 市场级检索：每个关键词的 totalRecordNum 与命中公司数、每个事件组的命中公告数、
     命中公司数与污染排除数（读 `代码\数据准备\勘察\event_first_probe.json`，与
     `event_first.py --probe` 同源）；
  2. 新增公司名单（代码／名称／行业／板块／事件组／选入公告数）；
  3. v2.1 的最终规模：doc_count、chunk_count、company_count、类目分布、逐月直方图、两个时间桶；
  4. 三个动机指标的 before → after：标题命中"重大合同"族／"产品"族（已排再融资污染）的公告数、
     `company_list` 长度 ≥2 的文档数；
  5. 版本关系自检：v2.1 的 clean 文档集合是否包含 v2.0 的全部 clean 文档（逐篇比对正文指纹）。

所有数字都由数据集文件重算，不读 reports\consistency_report.json 的结论。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402


def read_jsonl(path):
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def month_histogram(dates):
    months = sorted({d[:7] for d in dates if d})
    if not months:
        return {}
    hist = {}
    year, month = int(months[0][:4]), int(months[0][5:7])
    last = (int(months[-1][:4]), int(months[-1][5:7]))
    while (year, month) <= last:
        hist["%04d-%02d" % (year, month)] = 0
        month += 1
        if month > 12:
            year, month = year + 1, 1
    for d in dates:
        if d:
            hist[d[:7]] = hist.get(d[:7], 0) + 1
    return hist


def group_counts(docs, group):
    pattern = config.EVENT_FIRST["groups"][group]["title_pattern"]
    exclude = config.EVENT_FIRST["groups"][group].get("exclude_pattern")
    hits = [d for d in docs
            if d.get("category") == "公告" and re.search(pattern, str(d.get("title") or ""))]
    if exclude:
        hits = [d for d in hits if not re.search(exclude, str(d.get("title") or ""))]
    return hits


def summarize_dataset(root, label):
    docs = read_jsonl(os.path.join(root, "clean", "documents.jsonl"))
    chunks = read_jsonl(os.path.join(root, "chunks", "chunks.jsonl"))
    dates = [str(d.get("publish_time") or "") for d in docs]
    covered = set()
    per_company = Counter()
    per_company_cat = Counter()
    for d in docs:
        for code in d.get("company_list") or []:
            covered.add(str(code))
            per_company[str(code)] += 1
            per_company_cat[(str(code), d.get("category"))] += 1
    recent = [d for d in docs if config.BUCKET_RECENT[0] <= str(d.get("publish_time"))
              <= config.BUCKET_RECENT[1]]
    earlier = [d for d in docs if config.BUCKET_EARLIER[0] <= str(d.get("publish_time"))
               <= config.BUCKET_EARLIER[1]]
    per_doc_chunks = Counter(c.get("doc_id") for c in chunks)
    out = {
        "label": label,
        "root": root,
        "doc_count": len(docs),
        "chunk_count": len(chunks),
        "company_count": len(covered),
        "category_counts": dict(Counter(d.get("category") for d in docs)),
        "publish_time_min": min(dates) if dates else None,
        "publish_time_max": max(dates) if dates else None,
        "per_month_histogram": month_histogram(dates),
        "bucket_recent": len(recent),
        "bucket_earlier": len(earlier),
        "group_contract": len(group_counts(docs, "重大合同")),
        "group_product_raw": len([d for d in docs if d.get("category") == "公告"
                                  and re.search(config.EVENT_FIRST["groups"]["产品"]["title_pattern"],
                                                str(d.get("title") or ""))]),
        "group_product": len(group_counts(docs, "产品")),
        "docs_company_list_ge2": sum(1 for d in docs
                                     if len(d.get("company_list") or []) >= 2),
        "docs_subject_companies_ge2": sum(1 for d in docs
                                          if len(d.get("subject_companies") or []) >= 2),
        "chunks_per_doc_max": max(per_doc_chunks.values()) if chunks else 0,
        "per_company_docs": dict(sorted(per_company.items())),
        "per_company_category": {"%s|%s" % k: v for k, v in per_company_cat.items()},
        "docs": docs,
    }
    return out


def content_fingerprint(text):
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="v2.1 定向补样实测报告（只读）")
    parser.add_argument("--base", default=config.dataset_dir_for_version("v2.0"))
    parser.add_argument("--target", default=config.dataset_dir("v1"))
    parser.add_argument("--probe", default=os.path.join(_HERE, "勘察",
                                                       "event_first_probe.json"))
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)

    base = summarize_dataset(os.path.abspath(args.base), "v2.0")
    targ = summarize_dataset(os.path.abspath(args.target), "v2.1")

    print("=" * 78)
    print("v2.1 定向补样实测报告（全部数字由数据集文件重算）")
    print("=" * 78)
    probe_path = os.path.abspath(args.probe)
    probe = read_json(probe_path) if os.path.isfile(probe_path) else {}
    print("\n一、市场级检索（端点 %s，column=%s，窗口 %s）"
          % (probe.get("search_endpoint") or config.ENDPOINTS["cninfo_query"],
             probe.get("market_column") or config.EVENT_FIRST["market_column"],
             "~".join(probe.get("window") or [config.WINDOW_START, config.WINDOW_END])))
    for group, data in (probe.get("groups") or {}).items():
        print("  -- 事件组：%s（标题正则 %s%s）" % (group, data.get("title_pattern"),
              "；污染排除 %s" % data["exclude_pattern"] if data.get("exclude_pattern") else ""))
        for keyword, stat in (data.get("keyword_stats") or {}).items():
            print("     关键词 %-8s totalRecordNum=%-6s 收集 %-4s 条；命中公司 %s 家"
                  % (keyword, stat.get("total_record_num"), stat.get("collected"),
                     stat.get("distinct_companies")))
        print("     组内合并命中公告 %s 条（污染排除 %s 条）／命中公司 %s 家／新增候选 %s 家"
              % (data.get("matched_announcements"), data.get("dropped_by_pollution"),
                 data.get("distinct_companies"), data.get("new_candidate_companies")))
    print("  （证据文件：%s）" % probe_path)

    print("\n二、新增公司名单（config.COMPANIES 中带 event_groups 的条目）")
    new_companies = [c for c in config.COMPANIES if c.get("event_groups")]
    for i, comp in enumerate(new_companies, 1):
        code = str(comp["code"])
        ann_n = targ["per_company_category"].get("%s|公告" % code, 0)
        news_n = targ["per_company_category"].get("%s|财经新闻" % code, 0)
        print("  %2d. %s %-8s %-26s 板块 %-10s 事件组 %-10s 选入公告 %s 篇＋新闻 %s 篇"
              "（v2.0 共含 %s 篇）"
              % (i, comp["code"], comp.get("name"), comp.get("industry") or "-",
                 comp.get("board") or "-", "、".join(comp.get("event_groups") or []),
                 ann_n, news_n, base["per_company_docs"].get(code, 0)))

    print("\n三、规模与分布（v2.0 → v2.1）")
    for key in ("doc_count", "chunk_count", "company_count"):
        print("  %-16s %s → %s" % (key, base[key], targ[key]))
    print("  类目分布        %s → %s" % (base["category_counts"], targ["category_counts"]))
    print("  逐月直方图      %s → %s"
          % (base["per_month_histogram"], targ["per_month_histogram"]))
    print("  时间桶 recent   %s → %s" % (base["bucket_recent"], targ["bucket_recent"]))
    print("  时间桶 earlier  %s → %s" % (base["bucket_earlier"], targ["bucket_earlier"]))
    print("  时间范围        %s~%s → %s~%s"
          % (base["publish_time_min"], base["publish_time_max"],
             targ["publish_time_min"], targ["publish_time_max"]))
    print("  单篇最多文本块  %s → %s" % (base["chunks_per_doc_max"], targ["chunks_per_doc_max"]))

    print("\n四、三个动机指标（before → after）")
    print("  标题命中《重大合同》族的公告           %s → %s"
          % (base["group_contract"], targ["group_contract"]))
    print("  标题命中《产品》族的公告（已排污染）   %s → %s"
          % (base["group_product"], targ["group_product"]))
    print("  其中未排除再融资污染的计数             %s → %s"
          % (base["group_product_raw"], targ["group_product_raw"]))
    print("  company_list 长度 ≥2 的文档            %s → %s"
          % (base["docs_company_list_ge2"], targ["docs_company_list_ge2"]))
    print("  subject_companies 长度 ≥2 的文档       %s → %s"
          % (base["docs_subject_companies_ge2"], targ["docs_subject_companies_ge2"]))

    print("\n五、版本关系自检（v2.1 ⊇ v2.0）")
    base_fp = {d.get("doc_id"): content_fingerprint(d.get("content")) for d in base["docs"]}
    targ_fp = {d.get("doc_id"): content_fingerprint(d.get("content")) for d in targ["docs"]}
    missing = sorted(set(base_fp) - set(targ_fp))
    changed = sorted(did for did in set(base_fp) & set(targ_fp) if base_fp[did] != targ_fp[did])
    print("  v2.0 clean 文档 %d 篇；在 v2.1 中缺失 %d 篇%s；正文指纹变化 %d 篇%s"
          % (len(base_fp), len(missing), "：" + str(missing[:10]) if missing else "",
             len(changed), "：" + str(changed[:10]) if changed else ""))
    new_ids = sorted(set(targ_fp) - set(base_fp))
    print("  既有 doc_id 全部保留：%s（共同 doc_id %d 个；v2.1 新增 %d 个）"
          % (not missing, len(set(base_fp) & set(targ_fp)), len(new_ids)))
    if new_ids:
        by_cat = Counter(d.get("category") for d in targ["docs"]
                         if d.get("doc_id") in set(new_ids))
        print("  新增 doc_id 分布：%s；区间 %s~%s" % (dict(by_cat), new_ids[0], new_ids[-1]))
    for cat in config.CATEGORIES:
        ids = sorted(d.get("doc_id") for d in targ["docs"] if d.get("category") == cat)
        if ids:
            print("  块 %-6s 占用 %d 个编号，%d~%d（区段 %d+）"
                  % (cat, len(ids), ids[0], ids[-1], config.DOC_ID_BLOCK[cat]))

    if args.json_out:
        payload = {k: {kk: vv for kk, vv in v.items() if kk != "docs"}
                   for k, v in (("v2.0", base), ("v2.1", targ))}
        payload["new_companies"] = [
            {"code": c["code"], "name": c.get("name"), "industry": c.get("industry"),
             "board": c.get("board"), "event_groups": c.get("event_groups"),
             "selected_docs": targ["per_company_docs"].get(str(c["code"]), 0)}
            for c in new_companies]
        payload["probe"] = probe
        with open(args.json_out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("\nJSON 摘要已写入：%s" % os.path.abspath(args.json_out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
