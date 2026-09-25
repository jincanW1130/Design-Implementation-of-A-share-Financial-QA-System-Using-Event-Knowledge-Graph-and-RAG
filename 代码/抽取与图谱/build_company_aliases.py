# -*- coding: utf-8 -*-
r"""build_company_aliases.py —— 为 T4 消歧准备「公司注册全称」别名补充（**数据**，不是规则）。

问题（2026-09-26 全量实测）：T4 的别名表原先只锚在 `代码\数据准备\config.py` 的
`COMPANIES[*].name`（**市场简称**，如 `万科A`／`宝钢股份`／`牧原股份`），而语料写的是
**工商登记全称**（`万科企业股份有限公司`／`宝山钢铁股份有限公司`／`牧原食品集团股份有限公司`）。
简称不是全称的子串，规则 R2（简称是全称展开）因此永远不触发：1888 条公司提及只消歧
618 条（32.7%），105 家配置公司里 15 家一条身份都没有。

本脚本**只补别名数据**，不动 `config.DISAMBIG["match_rules"]` 的两条规则（《10》第4.5.4节
＝《02》第9.2节，冻结）。产出 `company_registered_names.py`（与本脚本同目录的冻结数据模块），
由 `disambiguate.py` 只读加载，把每家配置公司的注册全称并入别名表。

取名的来源顺序（**只取实据，绝不手打**）：

1. **巨潮公司概况接口**（第 5 阶段已在用的 `config.ENDPOINTS["cninfo_company_intro"]`）：
   `GET /data20/companyOverview/getCompanyIntroduction?scode={code}`，
   名称取响应 `data.records[0].basicInformation[0].ORGNAME`（注册全称），
   同时记录 `ASECNAME`／`MARKET`／`F032V` 三个互相印证的字段与请求参数作为证据；
2. **接口给不出名字时**回落到**语料本身**：该代码的 `公告` 文档（`company_list` 含该代码）
   标题里按 `…公司(关于|就|…)` 形态harvest 注册名，**同一名字至少由 2 篇不同文档的标题
   相互印证**才采纳，并把印证篇数与 doc_id 清单写进证据；
3. 两条路都拿不到 → 如实登记 `unknown`，**不猜**（`disambiguate.py` 侧照旧进待消歧清单）。

用法（参数一律取自 `代码\数据准备\config.py` 与 `代码\抽取与图谱\config.py`）：

    python 代码\抽取与图谱\build_company_aliases.py                # 接口优先，语料兜底
    python 代码\抽取与图谱\build_company_aliases.py --no-network   # 只用语料兜底（离线复核）
    python 代码\抽取与图谱\build_company_aliases.py --out <路径>    # 只改落点（自测用）

退出码：`0` 全部配置公司都有名字或已如实登记 unknown；`1` 输入缺失／配置异常。
本脚本是**离线建档工具**，不属于 T3～T6 管线，`run_all.py` 不会调用它，也不会被重跑触发；
它不调用大模型（只发公司概况的 HTTP GET），不写数据集、不写抽取缓存。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  第 6 阶段唯一参数来源（只读路径与冻结 schema）


OUTPUT_MODULE = os.path.join(_HERE, "company_registered_names.py")
SUPPLEMENT_SCHEMA = "stage6-company-registered-names-1.0"

# 语料兜底用的注册名形态（《公司法》下的三种公司后缀；不带"公司"两字的简称不采纳）。
COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司")
NAME_RE = re.compile(
    r"([\u4e00-\u9fa5A-Za-z0-9（）()·\*]{4,40}?(?:%s))" % "|".join(COMPANY_SUFFIXES))
# 标题里出现在注册名之前的“前导语”切分点：命中则取其后一段（例：
# 「上海市方达律师事务所关于宝山钢铁股份有限公司差异化分红事项之法律意见书」→ 宝山钢铁股份有限公司）。
LEAD_CUTS = ("关于", "就", "律师事务所", "事务所", "意见书", "之", "的")
CORPUS_MIN_CORROBORATION = 2
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
REQUEST_INTERVAL_SECONDS = 0.4        # 礼貌限流：两次公司概况请求之间的最小间隔
REQUEST_TIMEOUT_SECONDS = 30.0


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_stage5_config():
    """只读加载第 5 阶段的 config（拿 COMPANIES 与端点），不改动它。"""
    path = config.DISAMBIG["alias_source_path"]
    if not os.path.isfile(path):
        raise SystemExit("配置公司集来源不存在（只读）：%s" % path)
    spec = importlib.util.spec_from_file_location("_stage5_data_prep_config_for_aliases", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def configured_companies(stage5):
    """[(stock_code, 简称)]，按代码升序（确定性）。"""
    rows, seen = [], set()
    for item in getattr(stage5, "COMPANIES"):
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        if not code or not name:
            raise SystemExit("配置公司集里有缺 code／name 的条目：%r" % (item,))
        if code in seen:
            raise SystemExit("配置公司集里 stock_code 重复：%s" % code)
        seen.add(code)
        rows.append((code, name))
    rows.sort()
    return rows


# --------------------------------------------------------------------------
# 来源 1：巨潮公司概况接口（与第 5 阶段 `event_first.py` 的解析口径逐字一致）
# --------------------------------------------------------------------------
def fetch_registered_name(url, code):
    """返回 (名称 或 None, 证据 dict)。HTTP/解析失败不抛异常，如实记在证据里。"""
    evidence = {"endpoint": url, "method": "GET", "param": {"scode": code},
                "field": "data.records[0].basicInformation[0].ORGNAME", "http_status": None}
    request = urllib.request.Request(
        url + "?scode=" + code,
        headers={"User-Agent": USER_AGENT,
                 "Referer": "https://www.cninfo.com.cn/",
                 "Accept": "application/json, text/plain, */*"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            evidence["http_status"] = int(getattr(resp, "status", 200))
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        evidence["http_status"] = int(exc.code)
        evidence["error"] = "HTTPError"
        return None, evidence
    except Exception as exc:                      # noqa: BLE001 —— 网络类失败一律落到证据里
        evidence["error"] = "%s: %s" % (type(exc).__name__, exc)
        return None, evidence
    if evidence["http_status"] != 200:
        evidence["error"] = "HTTP %s" % evidence["http_status"]
        return None, evidence
    try:
        payload = json.loads(raw)
    except ValueError:
        evidence["error"] = "响应不是 JSON"
        return None, evidence
    records = ((payload.get("data") or {}).get("records")) or []
    basic = ((records[0] if records else {}) or {}).get("basicInformation") or []
    info = basic[0] if basic else {}
    name = str(info.get("ORGNAME") or "").strip()
    evidence["response_short_name"] = str(info.get("ASECNAME") or "").strip()
    evidence["response_market"] = str(info.get("MARKET") or "").strip()
    evidence["response_industry"] = str(info.get("F032V") or "").strip()
    if not name:
        evidence["error"] = "basicInformation 未含 ORGNAME"
        return None, evidence
    return name, evidence


# --------------------------------------------------------------------------
# 来源 2：语料兜底（≥2 篇独立公告标题相互印证）
# --------------------------------------------------------------------------
def harvest_names(title):
    """从一条标题里 harvest 注册名候选（去掉前导语，只保留以公司后缀结尾的一段）。"""
    found = set()
    for match in NAME_RE.finditer(str(title or "")):
        candidate = match.group(1)
        for marker in LEAD_CUTS:
            index = candidate.rfind(marker)
            if index > 0:
                candidate = candidate[index + len(marker):]
        if len(candidate) >= 4 and candidate.endswith(COMPANY_SUFFIXES):
            found.add(candidate)
    return found


def corpus_corroboration(rows, code):
    """返回 {名字: {"count": n, "doc_ids": [...]}}；只统计该代码的公告标题。"""
    hits = {}
    for row in rows:
        if str(row.get("category") or "") != "公告":
            continue
        if code not in {str(c) for c in (row.get("company_list") or [])}:
            continue
        doc_id = int(row["doc_id"])
        for name in harvest_names(row.get("title")):
            entry = hits.setdefault(name, {"count": 0, "doc_ids": []})
            if doc_id not in entry["doc_ids"]:
                entry["doc_ids"].append(doc_id)
                entry["count"] += 1
    for entry in hits.values():
        entry["doc_ids"].sort()
    return hits


def pick_corpus_name(hits):
    """印证篇数 ≥2 才采纳；并列时取篇数多、再取名字字典序（确定性）。"""
    eligible = [(v["count"], k) for k, v in hits.items()
                if v["count"] >= CORPUS_MIN_CORROBORATION]
    if not eligible:
        return None, None
    eligible.sort(key=lambda item: (-item[0], item[1]))
    count, name = eligible[0]
    return name, {"corroboration_count": count,
                  "corroboration_doc_ids": list(hits[name]["doc_ids"]),
                  "harvest_rule": "标题里以公司后缀结尾的一段，去掉前导语"}


# --------------------------------------------------------------------------
# 建档
# --------------------------------------------------------------------------
def build_table(companies, docs_rows, endpoint_url, allow_network):
    table = {}
    last_request = 0.0
    for code, short_name in companies:
        name, source, evidence = None, "unknown", {}
        if allow_network:
            wait = REQUEST_INTERVAL_SECONDS - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()
            name, evidence = fetch_registered_name(endpoint_url, code)
            if name:
                source = "cninfo_company_intro"
        corroboration = corpus_corroboration(docs_rows, code)
        best_corpus, best_evidence = pick_corpus_name(corroboration)
        if not name and best_corpus:
            name, source = best_corpus, "corpus_corroborated_titles"
            evidence = dict(best_evidence)
            evidence["min_corroboration"] = CORPUS_MIN_CORROBORATION
        row = {"stock_code": code, "short_name": short_name,
               "registered_name": name, "source": source,
               "evidence": evidence,
               "corpus_corroboration_count":
                   int(corroboration.get(name, {}).get("count", 0)) if name else 0,
               "corpus_corroboration_doc_ids":
                   list(corroboration.get(name, {}).get("doc_ids", [])) if name else []}
        table[code] = row
    return table


def render_module(table, endpoint_url):
    """把冻结表写成 Python 数据模块（JSON 是合法 Python 字面量；键序固定 → 逐字节可复现）。"""
    counts = {}
    for row in table.values():
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    header = (
        "# -*- coding: utf-8 -*-\n"
        'r"""company_registered_names.py —— T4 消歧的「公司注册全称」别名补充（**冻结数据**）。\n'
        "\n"
        "本文件由 `build_company_aliases.py` 生成，**不要手改**：全部名字都取自实据，\n"
        "没有任何一条是手打或推测出来的。\n"
        "\n"
        "来源与证据逐家写在条目里：\n"
        "  * `source = cninfo_company_intro`：巨潮公司概况接口的 ORGNAME 字段（证据含请求参数、\n"
        "    HTTP 状态与 ASECNAME／MARKET／F032V 三个互相印证的响应字段）；\n"
        "  * `source = corpus_corroborated_titles`：接口给不出名字时从该代码的公告标题 harvest，\n"
        "    且**至少 2 篇不同文档的标题相互印证**（证据含印证篇数与 doc_id 清单）；\n"
        "  * `source = unknown`：两条路都拿不到，如实登记，等人工确认（**不猜**）。\n"
        "\n"
        "`CORPUS_CORROBORATION_*` 是对接口来源也顺手做的语料复核（只作审计，不参与别名）；\n"
        "`disambiguate.py` 只读本模块的 `REGISTERED_NAMES`。\n"
        '"""\n'
        "\n"
        "SUPPLEMENT_SCHEMA = %s\n"
        "SOURCE_ENDPOINT = %s\n"
        "SOURCE_ENDPOINT_FIELD = %s\n"
        "SOURCE_ENDPOINT_PARAM = \"scode\"\n"
        "CORPUS_MIN_CORROBORATION = %d\n"
        "SOURCE_COUNTS = %s\n"
        "\n"
        % (json.dumps(SUPPLEMENT_SCHEMA, ensure_ascii=False),
           json.dumps(endpoint_url, ensure_ascii=False),
           json.dumps("data.records[0].basicInformation[0].ORGNAME", ensure_ascii=False),
           CORPUS_MIN_CORROBORATION,
           json.dumps({k: counts[k] for k in sorted(counts)}, ensure_ascii=False)))
    body = "REGISTERED_NAMES = " + json.dumps(table, ensure_ascii=False, sort_keys=True,
                                              indent=4) + "\n"
    return header + body


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="建档：105 家配置公司的注册全称（巨潮公司概况接口优先，语料 ≥2 篇印证兜底）")
    parser.add_argument("--no-network", action="store_true",
                        help="不查接口，只用语料兜底（离线复核用；结果通常少于联网口径）")
    parser.add_argument("--out", default=None, help="产出模块落点（默认与脚本同目录）")
    args = parser.parse_args(argv)

    stage5 = load_stage5_config()
    companies = configured_companies(stage5)
    endpoint_url = str(stage5.ENDPOINTS["cninfo_company_intro"])
    if not os.path.isfile(config.DOCS_PATH):
        raise SystemExit("数据集缺失：%s" % config.DOCS_PATH)
    docs_rows = read_jsonl(config.DOCS_PATH)

    table = build_table(companies, docs_rows, endpoint_url, allow_network=not args.no_network)
    path = os.path.abspath(args.out) if args.out else OUTPUT_MODULE
    text = render_module(table, endpoint_url)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)

    counts = {}
    for row in table.values():
        counts[row["source"]] = counts.get(row["source"], 0) + 1
    unknown = [code for code in sorted(table) if table[code]["source"] == "unknown"]
    print("配置公司 %d 家；来源分布 %s"
          % (len(table), {k: counts[k] for k in sorted(counts)}))
    print("落点：%s（%d 字节）" % (path, len(text.encode("utf-8"))))
    if unknown:
        print("仍拿不到注册全称（如实登记，不猜）：%s" % "、".join(unknown))
    for code in sorted(table):
        row = table[code]
        if row["source"] == "cninfo_company_intro":
            print("  %s %-8s → %-24s [%s] 语料复核 %d 篇"
                  % (code, row["short_name"], row["registered_name"], row["source"],
                     row["corpus_corroboration_count"]))
        else:
            print("  %s %-8s → %-24s [%s]"
                  % (code, row["short_name"], row["registered_name"] or "（无）", row["source"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
