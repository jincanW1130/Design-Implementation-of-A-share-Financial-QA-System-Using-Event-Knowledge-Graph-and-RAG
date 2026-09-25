# -*- coding: utf-8 -*-
r"""event_first.py —— v2.1 事件类型优先补样：市场级检索、事件组匹配与公司排名。

本模块是第 5 阶段数据管线在 **v2.1** 上新增的"事件类型优先"采样模式的公共实现，供两处使用：

  1. `python 代码\数据准备\event_first.py --probe`：一次性勘察——按事件组关键词跑**市场级**
     巨潮检索（`POST /new/hisAnnouncement/query`，只给 `searchkey`，不给 `stock`），
     去高亮标签、按组正则过滤标题、按公司排名，写出勘察证据
     `代码\数据准备\勘察\event_first_probe.json`（**刻意放在数据集目录之外**：证据里逐条
     保留了命中的公告标题，而标题里会带产品／药物代号〔如 SYS6090〕一类的字符串；
     数据集内部的结构化文件要过"不得写死外来标识符"的守卫，语料原文与勘察证据不进去，
     避免把来源原文误判成写死的型号），并打印可直接冻结进 `config.COMPANIES` 的新增公司名单；
  2. `fetch.py` 的定向补样环节：用 `scan_groups()` 拿到的同一批市场级命中作为**新增公司**的
     候选池（因此"排名所用的命中"与"实际选入的候选"是同一份数据），再按每家 ≤6 篇、
     level-2 等间距铺开选入。

纪律（与其它脚本一致）：
  * 参数一律来自 `config.py`（关键词、正则、页数上限、列名都在 `config.EVENT_FIRST`）；
  * 真实数据：只读来源返回的标题／时间／链接，抓不到就登记，绝不生成或改写；
  * 限流：所有请求都走 `fetch.HttpClient`，即 `config.HTTP["min_interval_seconds"]` 全局下限；
  * 市场级检索固定一个 `column`（config.EVENT_FIRST["market_column"]）：2026-09-25 实测
    `column="szse"` 与 `column="sse"` 返回同一页、同一 `totalRecordNum`（市场级检索与 column
    无关），**不得按 szse／sse 各查一遍**，否则同一篇公告被重复计数；不传 column 会混入港股
    代码（同一家公司的 H 股），故显式固定为一个值。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402
from fetch import FetchError, HttpClient, ms_to_date  # noqa: E402

_RE_TAGS = re.compile(r"</?em>|<[^>]+>", re.I)


# --------------------------------------------------------------------------
# 1. 文本与事件组口径（正则一律取自 config.EVENT_FIRST，本文件不复制字面量）
# --------------------------------------------------------------------------
def strip_em(value) -> str:
    """去掉巨潮检索注入的 <em>／</em> 高亮标签（以及其它残留标签），并压掉多余空白。"""
    if value is None:
        return ""
    text = _RE_TAGS.sub("", str(value)).replace("\u00a0", " ")
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


def group_names() -> list:
    """config 里冻结的事件组名（顺序即 config 中的声明顺序）。"""
    return list((config.EVENT_FIRST.get("groups") or {}).keys())


def group_cfg(name: str) -> dict:
    groups = config.EVENT_FIRST.get("groups") or {}
    if name not in groups:
        raise KeyError("config.EVENT_FIRST['groups'] 未定义事件组：%r（已定义：%s）"
                       % (name, "、".join(groups)))
    return groups[name]


def title_matches_group(title: str, group: str) -> bool:
    """组级标题判定（re.search，作用于去标签后的 announcementTitle）。"""
    pattern = group_cfg(group).get("title_pattern")
    return bool(pattern) and re.search(pattern, title or "") is not None


def title_hits_pollution(title: str, group: str) -> bool:
    """命中该组的"污染排除"模式（产品组用它排除再融资类标题：发行／股票／债券／募集…）。"""
    pattern = group_cfg(group).get("exclude_pattern")
    return bool(pattern) and re.search(pattern, title or "") is not None


def matched_group_titles(title: str) -> list:
    """标题命中了哪些事件组（同时命中两组时两家名单都算它）。"""
    return [g for g in group_names()
            if title_matches_group(title, g) and not title_hits_pollution(title, g)]


# --------------------------------------------------------------------------
# 2. 市场级检索（searchkey + seDate，不给 stock；每页最多 30 条，须翻页）
# --------------------------------------------------------------------------
def market_search_keyword(http: HttpClient, keyword: str):
    """一个关键词跑完窗口内的所有页，返回 (hits, stats)。

    hits：按 announcementId（缺失时退回落款链接）去重的命中，字段已去标签；
    stats：该关键词的 totalRecordNum、翻页数、收集条数、标题未含关键词的条数
    （后者是"检索命中标题级"的凭据；>0 说明关键词也匹配到了别的字段）。
    """
    cfg = config.EVENT_FIRST
    url = config.ENDPOINTS["cninfo_query"]
    column = cfg["market_column"]
    page_size = int(cfg["search_page_size"])
    max_pages = int(cfg["max_pages_per_keyword"])
    form_base = {
        "pageSize": page_size,
        "column": column,
        "tabName": "fulltext",
        "searchkey": keyword,
        "seDate": "%s~%s" % (config.WINDOW_START, config.WINDOW_END),
        "isHLtitle": "true",
    }
    hits, seen = [], set()
    total = None
    pages_fetched = 0
    title_miss = 0
    for page in range(1, max_pages + 1):
        form = dict(form_base)
        form["pageNum"] = page
        try:
            resp = http.post(url, data=form,
                             headers={"Referer": config.SOURCES["公告"]["home"] + "/"})
        except FetchError as exc:
            return hits, {"keyword": keyword, "total_record_num": total,
                          "pages_fetched": pages_fetched, "collected": len(hits),
                          "error": str(exc)}
        pages_fetched += 1
        if resp.status_code != 200:
            return hits, {"keyword": keyword, "total_record_num": total,
                          "pages_fetched": pages_fetched, "collected": len(hits),
                          "error": "HTTP %d" % resp.status_code}
        try:
            payload = json.loads(resp.content.decode("utf-8", "replace"))
        except ValueError:
            return hits, {"keyword": keyword, "total_record_num": total,
                          "pages_fetched": pages_fetched, "collected": len(hits),
                          "error": "响应不是 JSON"}
        if total is None:
            total = payload.get("totalRecordNum")
        items = payload.get("announcements") or []
        for item in items:
            title = strip_em(item.get("announcementTitle"))
            adjunct = (item.get("adjunctUrl") or "").strip()
            aid = item.get("announcementId")
            key = str(aid) if aid not in (None, "") else ("adjunct:" + adjunct)
            if key in seen:
                continue
            seen.add(key)
            if keyword not in title:
                title_miss += 1
            hits.append({
                "announcement_id": str(aid) if aid not in (None, "") else None,
                "code": str(item.get("secCode") or "").strip(),
                "name": strip_em(item.get("secName")),
                "title": title,
                "publish_time": ms_to_date(item.get("announcementTime")),
                "content_url": adjunct,
                "org_id": item.get("orgId"),
                "announcement_time_ms": item.get("announcementTime"),
                "keyword": keyword,
            })
        if len(items) < page_size:
            break
    stats = {"keyword": keyword, "total_record_num": total, "pages_fetched": pages_fetched,
             "collected": len(hits), "keywords_in_title_missing": title_miss,
             "distinct_companies": len({h["code"] for h in hits if h["code"]})}
    return hits, stats


def scan_groups(http: HttpClient, groups=None):
    """按事件组跑完所有关键词的市场级检索，返回 {组名: {"hits": ..., "keyword_stats": ...}}。

    hits 为该组全部关键词命中的并集（按 announcementId 去重、已去高亮标签），
    组内再按组正则过滤标题（产品组另按 exclude_pattern 剔除再融资污染）。
    """
    groups = groups or group_names()
    out = {}
    for group in groups:
        cfg = group_cfg(group)
        per_keyword = {}
        merged, seen = [], set()
        for keyword in cfg.get("keywords") or []:
            hits, stats = market_search_keyword(http, keyword)
            per_keyword[keyword] = stats
            for hit in hits:
                key = hit["announcement_id"] or ("adjunct:" + hit["content_url"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(hit)
        kept, dropped_pollution = [], []
        for hit in merged:
            if not hit["publish_time"] or not (
                    config.WINDOW_START <= hit["publish_time"] <= config.WINDOW_END):
                continue
            if not title_matches_group(hit["title"], group):
                continue
            if title_hits_pollution(hit["title"], group):
                dropped_pollution.append(hit)
                continue
            kept.append(hit)
        out[group] = {"hits": kept, "keyword_stats": per_keyword,
                      "collected_before_regex": len(merged),
                      "dropped_by_pollution": len(dropped_pollution)}
    return out


# --------------------------------------------------------------------------
# 3. 公司排名（按"该窗口内命中该事件组的**不重复公告数**"降序）
# --------------------------------------------------------------------------
def rank_key(row: dict):
    """排序键：命中公告数降序 → 命中关键词种数降序 → 股票代码升序（确定性，可复现）。"""
    return (-int(row["matched_announcements"]), -int(row["matched_keywords"]),
            str(row["code"]))


def company_ranking(hits) -> list:
    """按公司聚合命中公告，返回按 rank_key 升序的排名表。"""
    per = {}
    for hit in hits:
        code = hit.get("code") or ""
        if not code:
            continue
        row = per.setdefault(code, {"code": code, "name": hit.get("name") or "",
                                    "announcement_ids": set(), "keywords": set(),
                                    "samples": []})
        row["announcement_ids"].add(hit.get("announcement_id") or hit.get("content_url"))
        row["keywords"].add(hit.get("keyword"))
        if len(row["samples"]) < 3:
            row["samples"].append({"title": hit.get("title"),
                                   "publish_time": hit.get("publish_time")})
        if not row["name"] and hit.get("name"):
            row["name"] = hit["name"]
    rows = []
    for row in per.values():
        rows.append({
            "code": row["code"], "name": row["name"],
            "matched_announcements": len(row["announcement_ids"]),
            "matched_keywords": len(row["keywords"]),
            "keywords": sorted(k for k in row["keywords"] if k),
            "samples": row["samples"],
        })
    rows.sort(key=rank_key)
    return rows


# --------------------------------------------------------------------------
# 4. 行业／板块（巨潮同一站点的公司概况接口，只读来源）
# --------------------------------------------------------------------------
def _board_and_column(market: str):
    market = market or ""
    if "上交所" in market:
        return market, "sse"
    if "深交所" in market:
        return market, "szse"
    return market or None, None


def company_profile(http: HttpClient, code: str) -> dict:
    """公司名称／行业／板块。行业取巨潮公司概况接口返回的证监会行业分类，原文照录。"""
    url = config.ENDPOINTS["cninfo_company_intro"]
    out = {"code": code, "industry": None, "market": None, "cninfo_column": None,
           "full_name": None, "short_name": None, "note": ""}
    try:
        resp = http.get(url, params={"scode": code},
                        headers={"Referer": config.SOURCES["公告"]["home"] + "/"})
    except FetchError as exc:
        out["note"] = "公司概况接口失败：%s" % exc
        return out
    if resp.status_code != 200:
        out["note"] = "公司概况接口 HTTP %d" % resp.status_code
        return out
    try:
        payload = json.loads(resp.content.decode("utf-8", "replace"))
    except ValueError:
        out["note"] = "公司概况接口响应不是 JSON"
        return out
    records = ((payload.get("data") or {}).get("records")) or []
    basic = ((records[0] if records else {}) or {}).get("basicInformation") or []
    info = basic[0] if basic else {}
    if not info:
        out["note"] = "公司概况接口未返回 basicInformation"
        return out
    market, column = _board_and_column(info.get("MARKET"))
    out.update({
        "industry": (info.get("F032V") or "").strip() or None,
        "market": market,
        "cninfo_column": column,
        "full_name": (info.get("ORGNAME") or "").strip() or None,
        "short_name": (info.get("F002V") or "").strip() or None,
        "note": "行业＝巨潮公司概况接口的证监会行业分类字段，板块＝MARKET；均原文照录",
    })
    return out


# --------------------------------------------------------------------------
# 5. 勘察入口：写出 reports\event_first_probe.json，并打印可冻结的新增公司名单
# --------------------------------------------------------------------------
def probe(argv=None) -> int:
    parser = argparse.ArgumentParser(description="v2.1 事件类型优先补样：市场级检索勘察")
    parser.add_argument("--profile", choices=["v1", "pilot"], default="v1")
    parser.add_argument("--out", default=None,
                        help="证据 JSON 落点（默认 代码\\数据准备\\勘察\\event_first_probe.json）")
    parser.add_argument("--top", type=int, default=None,
                        help="每个事件组预备的候选公司数（默认＝该组目标家数 + 10 家）")
    parser.add_argument("--no-profile", action="store_true",
                        help="不查行业／板块（少发请求，仅供快速自测）")
    args = parser.parse_args(argv)

    out_path = os.path.abspath(args.out) if args.out else \
        os.path.join(_HERE, "勘察", "event_first_probe.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    http = HttpClient()
    t0 = time.monotonic()
    print("=== event_first.py --probe（市场级检索勘察）===")
    print("检索列 column=%s；时间窗 %s ~ %s；每页 %d 条；每关键词最多 %d 页"
          % (config.EVENT_FIRST["market_column"], config.WINDOW_START, config.WINDOW_END,
             config.EVENT_FIRST["search_page_size"], config.EVENT_FIRST["max_pages_per_keyword"]))
    print("端点：%s（不给 stock 参数＝市场级）" % config.ENDPOINTS["cninfo_query"])

    scanned = scan_groups(http)
    existing = {str(c["code"]) for c in config.COMPANIES}
    evidence = {
        "report": "event_first_probe",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "market_column": config.EVENT_FIRST["market_column"],
        "window": [config.WINDOW_START, config.WINDOW_END],
        "search_endpoint": config.ENDPOINTS["cninfo_query"],
        "existing_company_count": len(existing),
        "groups": {},
    }
    for group in group_names():
        cfg = group_cfg(group)
        data = scanned[group]
        ranking = company_ranking(data["hits"])
        new_rows = [r for r in ranking if r["code"] not in existing]
        target = int(cfg.get("min_new_companies") or 0)
        top_n = args.top if args.top else target + 10
        chosen = new_rows[:top_n]
        print("\n---- 事件组：%s（目标新增 ≥%d 家）----" % (group, target))
        print("标题正则：%s" % cfg.get("title_pattern"))
        if cfg.get("exclude_pattern"):
            print("污染排除：%s" % cfg.get("exclude_pattern"))
        per_keyword = data["keyword_stats"]
        for keyword in cfg.get("keywords") or []:
            s = per_keyword.get(keyword) or {}
            print("  关键词 %-8s 接口 totalRecordNum=%-5s 实翻 %s 页、收集 %s 条、"
                  "标题未含该词 %s 条"
                  % (keyword, s.get("total_record_num"), s.get("pages_fetched"),
                     s.get("collected"), s.get("keywords_in_title_missing", 0)))
        print("  合并命中 %d 条（去重后）→ 标题过组正则且未被污染排除：%d 条；"
              "被污染排除 %d 条；命中公司 %d 家（其中新增候选 %d 家）"
              % (data["collected_before_regex"], len(data["hits"]),
                 data["dropped_by_pollution"], len(ranking), len(new_rows)))
        profiles = []
        if not args.no_profile:
            for row in chosen:
                prof = company_profile(http, row["code"])
                profiles.append({"code": row["code"],
                                 "name": row["name"] or prof.get("short_name") or "",
                                 "industry": prof.get("industry"),
                                 "market": prof.get("market"),
                                 "cninfo_column": prof.get("cninfo_column"),
                                 "full_name": prof.get("full_name"),
                                 "note": prof.get("note"),
                                 "matched_announcements": row["matched_announcements"],
                                 "matched_keywords": row["matched_keywords"],
                                 "keywords": row["keywords"],
                                 "samples": row["samples"]})
        else:
            profiles = [dict(row) for row in chosen]
        evidence["groups"][group] = {
            "title_pattern": cfg.get("title_pattern"),
            "exclude_pattern": cfg.get("exclude_pattern"),
            "keywords": list(cfg.get("keywords") or []),
            "keyword_stats": per_keyword,
            "collected_before_regex": data["collected_before_regex"],
            "matched_announcements": len(data["hits"]),
            "dropped_by_pollution": data["dropped_by_pollution"],
            "distinct_companies": len(ranking),
            "new_candidate_companies": len(new_rows),
            "target_new_companies": target,
            "top_candidates": profiles,
            "ranking_all_new": new_rows,
        }
        print("  前 %d 家新增候选（按命中公告数降序）：" % min(12, len(profiles)))
        for row in profiles[:12]:
            print("    %s %-8s %-14s 命中 %d 条 / 关键词 %s"
                  % (row["code"], row["name"], (row.get("industry") or "-")[:14],
                     row["matched_announcements"], "、".join(row.get("keywords") or [])))
    evidence["request_count"] = http.request_count
    evidence["error_count"] = http.error_count
    evidence["elapsed_seconds"] = round(time.monotonic() - t0, 1)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(evidence, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("\n证据已写入：%s（HTTP 请求 %d 次、异常 %d 次、用时 %.1fs）"
          % (out_path, http.request_count, http.error_count, time.monotonic() - t0))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="v2.1 事件类型优先补样（市场级检索与排名）")
    parser.add_argument("--probe", action="store_true", help="跑市场级勘察并写证据 JSON")
    args, rest = parser.parse_known_args(argv)
    if args.probe:
        return probe(rest)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
