# -*- coding: utf-8 -*-
r"""disambiguate.py —— 第 6 阶段「实体消歧」（T4）。

规则来源（**只引用、不新增**）：《10-系统总体设计（第四阶段）》第4.5.4节
（＝《02》第9.2节）。原文的口径是两句：

> **实体对齐以 stock_code 为锚**：抽到的公司名称先与别名表匹配，匹配成功则归并到对应的
> stock_code 节点；匹配失败进入待消歧列表，人工确认后再写入图谱。

本脚本据此做三件事：

1. **建别名表**（`alias_table.json`）：来源是第 5 阶段已冻结的 105 家配置公司集
   （`代码\数据准备\config.py` 的 `COMPANIES`，**只读**），每家给出 stock_code、简称、
   行业、板块与 exchange；再并入**公司注册全称**别名补充
   （`代码\抽取与图谱\company_registered_names.py`，由 `build_company_aliases.py` 建档：
   巨潮公司概况接口优先、语料标题 ≥2 篇印证兜底，逐家带来源与证据）。
   2026-09-26 全量实测的成因：语料写工商登记全称（`万科企业股份有限公司`、
   `宝山钢铁股份有限公司`、`牧原食品集团股份有限公司`），而配置里只有市场简称
   （`万科A`、`宝钢股份`、`牧原股份`）——简称不是全称的子串，R2 永不触发，
   1888 条公司提及只消歧 618 条、105 家里 15 家没有身份。**补的是别名数据，不是规则**。
2. **逐条实体判身份**（`disambiguation.json`）：Company 按 `config.DISAMBIG["match_rules"]`
   的两条规则匹配 stock_code（R1 精确、R2 全称展开；两条规则本身**未改**，只是别名表里
   每个 code 的书写面从「简称」扩为「简称 ＋ 注册全称」，见下）；其余四类实体按
   `non_company_rule`（同类型 ＋ 同名即同一实体，最小规则，不做跨写法归并）。
   每条实体得到一个**身份键**（`<标签>:<身份>`，如 `Company:600309`），T5 的参与主体、
   T6 的节点编号都以它为准。
3. **未命中的进待消歧清单**（`unresolved.jsonl`）：一条一行，带 `reason` 与可复核的细节，
   **不猜、不合并**（《15》第五节 硬约束 18 的幂等与「不得静默省略」同源）。

两条匹配规则（按序求值，规则本身不新增本体）：

* **R1 精确**：归一后的名称 == 别名表里该 code 的任一书写面（**简称或注册全称**），
  或 == 6 位股票代码；
* **R2 全称展开**：归一后的名称**包含**别名表里该 code 的任一书写面，且残余串里不含任何一个
  `distinct_entity_markers`（控股／投资／实业／资本／集团控股）。例：
  「万华化学集团股份有限公司」→ 600309（残余「集团股份有限公司」无限定词）；
  「上海电气集团股份有限公司」→ 601727，而「上海电气控股集团有限公司」的残余含
  「控股」，判为**另一个主体**，进待消歧清单——这正是「不同实体被合并成一个节点」那一类。

两条规则的判定顺序、限定词清单与归一化口径都**没有改**（《10》第4.5.4节 ＝《02》第9.2节，
冻结）；改的只是别名表里的数据：每个 code 除简称外，还带 1 条由 `build_company_aliases.py`
建档的注册全称（来源与证据写在 `company_registered_names.py` 与 `alias_table.json` 里，
拿不到就如实登记 `unknown`、绝不手打）。

归一化只动空白与最外层包裹字符（`config.normalize_entity_name`），不做大小写折叠、
不做标点归一、不做模糊匹配、不做编辑距离——宁可进待消歧清单，也不做有把握不了的合并。

用法（参数一律取自 `代码\抽取与图谱\config.py`）：

    python 代码\抽取与图谱\disambiguate.py                  # 默认 --profile pilot
    python 代码\抽取与图谱\disambiguate.py --profile v21    # 全量 709 篇（T3 放量后）
    python 代码\抽取与图谱\disambiguate.py --force          # 忽略已有产物，重算并重写

退出码：`0` 成功（含「已是最新、跳过」）；`1` 输入缺失或缓存指纹与产物不一致；
`2` 数据异常（配置公司集重复、枚举越界等）。全程不调用模型。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib.util
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402


# --------------------------------------------------------------------------
# 基础工具（与 extract.py 同风格：显式排序、确定性序列化、UTF-8 无 BOM）
# --------------------------------------------------------------------------
def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def dump_json(path, obj, indent=2):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=indent) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def dump_jsonl(path, rows):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
             for r in rows]
    text = ("\n".join(lines) + "\n") if lines else ""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def load_records(profile):
    """读 T4～T7 的唯一输入：extract.py 解析后的抽取结果（一行一篇）。"""
    path = config.extract_records_path(profile)
    if not os.path.isfile(path):
        raise SystemExit(
            "输入不存在：%s\n请先跑抽取（python 代码\\抽取与图谱\\extract.py --profile %s）；"
            "T4 不自己调模型，也不猜。" % (path, profile))
    return read_jsonl(path)


def source_fingerprint(records, path):
    """输入指纹：文件 sha256 ＋ 记录数与 schema／prompt 版本（只看缓存，不看时间）。"""
    schema_set = sorted({str(r.get("record_schema") or "") for r in records})
    prompt_set = sorted({str(r.get("prompt_version") or "") for r in records})
    model_set = sorted({str(r.get("model_resolved") or "") for r in records})
    return {
        "extract_records": os.path.relpath(path, config.ROOT).replace("\\", "/"),
        "extract_records_sha256": sha256_file(path),
        "documents": len(records),
        "doc_ids": sorted(int(r["doc_id"]) for r in records),
        "record_schemas": schema_set,
        "prompt_versions": prompt_set,
        "models_resolved": model_set,
    }


# --------------------------------------------------------------------------
# 别名表（只读第 5 阶段的 105 家配置公司集 ＋ 只读注册全称补充）
# --------------------------------------------------------------------------
def load_registered_names():
    """只读加载「公司注册全称」补充数据模块；返回 (per_code 表, 模块元信息)。"""
    path = config.DISAMBIG["registered_names_path"]
    if not os.path.isfile(path):
        raise SystemExit(
            "注册全称补充数据不存在：%s\n请先建档：python 代码\\抽取与图谱\\build_company_aliases.py"
            % path)
    spec = importlib.util.spec_from_file_location("_stage6_company_registered_names", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # 只读该文件，不改动它
    schema = str(getattr(module, "SUPPLEMENT_SCHEMA", "") or "")
    if schema != config.DISAMBIG["registered_names_schema"]:
        raise SystemExit("注册全称补充数据 schema 不符：%s（期望 %s）"
                         % (schema, config.DISAMBIG["registered_names_schema"]))
    table = getattr(module, config.DISAMBIG["registered_names_attr"])
    if not isinstance(table, dict) or not table:
        raise SystemExit("注册全称补充数据为空或形态不符：%s" % path)
    return table, {
        "path": os.path.relpath(path, config.ROOT).replace("\\", "/"),
        "schema": schema,
        "source_endpoint": str(getattr(module, "SOURCE_ENDPOINT", "") or ""),
        "source_endpoint_field": str(getattr(module, "SOURCE_ENDPOINT_FIELD", "") or ""),
        "corpus_min_corroboration": int(getattr(module, "CORPUS_MIN_CORROBORATION", 0) or 0),
        "source_counts": dict(getattr(module, "SOURCE_COUNTS", {}) or {}),
    }


def build_alias_table():
    """从 `config.DISAMBIG["alias_source_path"]` 读 COMPANIES，建 stock_code → 别名条目。"""
    path = config.DISAMBIG["alias_source_path"]
    if not os.path.isfile(path):
        raise SystemExit("别名表来源不存在（只读）：%s" % path)
    spec = importlib.util.spec_from_file_location("_stage5_data_prep_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)          # 只读该文件，不改动它
    companies = getattr(module, config.DISAMBIG["alias_source_attr"])
    registered, _meta = load_registered_names()

    table, duplicates = {}, []
    for item in companies:
        code = str(item.get("code") or "").strip()
        name = str(item.get("name") or "").strip()
        if not code or not name:
            raise SystemExit("配置公司集里有缺 code／name 的条目：%r" % (item,))
        if code in table:
            duplicates.append(code)
        board = item.get("board")
        supplement = registered.get(code) or {}
        registered_name = str(supplement.get("registered_name") or "").strip()
        aliases = [registered_name] if registered_name else []
        normalized_aliases = sorted({config.normalize_entity_name(a) for a in aliases
                                     if config.normalize_entity_name(a)})
        normalized_short = config.normalize_entity_name(name)
        table[code] = {
            "stock_code": code,
            "short_name": name,
            "normalized_short_name": normalized_short,
            # 别名表里该 code 的**全部书写面**（简称 ＋ 注册全称）；匹配规则读它，不读别的。
            "normalized_alias_surfaces": sorted({normalized_short} | set(normalized_aliases)),
            "registered_name": registered_name,
            "normalized_registered_name": config.normalize_entity_name(registered_name),
            "registered_name_source": str(supplement.get("source") or "unknown"),
            "registered_name_evidence": supplement.get("evidence") or {},
            "corpus_corroboration_count": int(supplement.get("corpus_corroboration_count") or 0),
            "corpus_corroboration_doc_ids": list(supplement.get("corpus_corroboration_doc_ids") or []),
            "industry": item.get("industry") or "",
            "board": board or "",
            "exchange": config.DISAMBIG["exchange_by_board"].get(board, ""),
        }
    if duplicates:
        raise SystemExit("配置公司集里 stock_code 重复：%s" % sorted(set(duplicates)))
    missing = sorted(code for code in table if not table[code]["registered_name"])
    if missing:
        print("[注意] %d 家配置公司没有注册全称（照《15》：如实留在待消歧清单，不猜）：%s"
              % (len(missing), "、".join(missing)))
    return {code: table[code] for code in sorted(table)}


def match_company(name_norm, alias_table):
    """返回 (命中代码或 None, 规则, 细节)。规则见 config.DISAMBIG["match_rules"]。

    与 2026-09-26 之前逐字一致的两条规则；唯一的差别是 `alias_table[code]` 现在给了
    **多个书写面**（简称 ＋ 注册全称），匹配对每个书写面求值——这是别名数据，不是新规则。
    """
    hits, blocked = {}, []
    for code in sorted(alias_table):
        surfaces = [s for s in (alias_table[code].get("normalized_alias_surfaces")
                                or [alias_table[code]["normalized_short_name"]]) if s]
        if not surfaces:
            continue
        if name_norm == code or any(name_norm == surface for surface in surfaces):
            hits.setdefault(code, "R1_exact_name_or_code")
            continue
        surface_hit, blocked_entry = None, None
        for surface in surfaces:
            if len(surface) < int(config.DISAMBIG["min_short_name_chars"]):
                continue
            if surface in name_norm:
                residual = name_norm.replace(surface, "", 1)
                marker = next((m for m in config.DISAMBIG["distinct_entity_markers"]
                               if m in residual), None)
                if marker:
                    # 残余含「不同主体限定词」：判为另一个主体，不做合并（《10》第4.5.4节 的第二类问题）。
                    if blocked_entry is None:
                        blocked_entry = {"code": code, "marker": marker,
                                         "residual": residual, "surface": surface}
                    continue
                surface_hit = surface
                break
        if surface_hit:
            hits.setdefault(code, "R2_full_name_contains_short_name")
        elif blocked_entry:
            blocked.append(blocked_entry)

    exact = sorted(code for code, rule in hits.items() if rule == "R1_exact_name_or_code")
    detail = {"matched_codes": sorted(hits), "blocked_by_marker": blocked}
    if len(exact) == 1:
        return exact[0], "R1_exact_name_or_code", detail
    if len(hits) == 1:
        code = sorted(hits)[0]
        return code, hits[code], detail
    if len(hits) > 1:
        return None, "ambiguous_alias", detail
    if blocked:
        return None, "distinct_entity_marker", detail
    return None, "no_alias_match", detail


# --------------------------------------------------------------------------
# 逐条实体判身份
# --------------------------------------------------------------------------
def disambiguate_records(records, alias_table):
    entity_map, unresolved = {}, []
    companies_seen = {}
    for record in sorted(records, key=lambda r: int(r["doc_id"])):
        doc_id = int(record["doc_id"])
        doc_codes = {str(c) for c in (record.get("company_list") or [])}
        for entity in sorted(record.get("entities") or [], key=lambda e: str(e["entity_id"])):
            local_id = str(entity["entity_id"])
            label = str(entity["type"])
            raw_name = str(entity.get("name") or "")
            name_norm = config.normalize_entity_name(raw_name)
            if label not in config.ENTITY_TYPES:
                raise SystemExit("实体类型不在本体里：doc_id=%s %s=%s"
                                 % (doc_id, local_id, label))
            item = {
                "entity_id": local_id, "doc_id": doc_id, "label": label,
                "name": raw_name, "normalized_name": name_norm,
            }
            if label == "Company":
                code, rule, detail = match_company(name_norm, alias_table)
                item["rule"] = rule
                if code:
                    item["identity_key"] = "Company%s%s" % (
                        config.DISAMBIG["identity_key_separator"], code)
                    item["status"] = "resolved"
                    # company_list 只作**标注**（《15》硬约束 16：它的松口径不作依据）。
                    item["in_doc_company_list"] = code in doc_codes
                    entry = companies_seen.setdefault(code, {"surfaces": set(), "doc_ids": set()})
                    entry["surfaces"].add(raw_name)
                    entry["doc_ids"].add(doc_id)
                else:
                    item["identity_key"] = None
                    item["status"] = "unresolved"
                    unresolved.append({
                        "doc_id": doc_id, "entity_id": local_id, "label": label,
                        "name": raw_name, "normalized_name": name_norm,
                        "reason": rule,
                        "matched_codes": detail["matched_codes"],
                        "blocked_by_marker": detail["blocked_by_marker"],
                        "in_doc_company_list": sorted(doc_codes),
                        "note": "按《10》第4.5.4节：匹配失败进待消歧列表，人工确认后再写入图谱；"
                                "本阶段不猜、不合并。",
                    })
            else:
                if not name_norm:
                    raise SystemExit("实体名为空：doc_id=%s %s" % (doc_id, local_id))
                item["identity_key"] = "%s%s%s" % (
                    label, config.DISAMBIG["identity_key_separator"], name_norm)
                item["status"] = "resolved"
                item["rule"] = config.DISAMBIG["non_company_rule"]
            entity_map[local_id] = item
    return entity_map, unresolved, companies_seen


def build_company_index(alias_table, companies_seen):
    """Company 字段（表 4-8 口径）：stock_code、company_name（公司全称）、short_name（简称）、
    aliases（其他书写面）、exchange、industry。

    口径只来自两处、都不猜：`short_name`／`exchange`／`industry` 取第 5 阶段已冻结的配置公司集；
    `company_name` 取**语料中出现过的最长书写面**（最完整的法定名称，确定性取法），`aliases`
    取其余书写面。T6 的 Company 节点属性与这里逐字一致（同一套字段名、同一套取法）。
    """
    index = {}
    for code in sorted(companies_seen):
        entry = alias_table[code]
        surfaces = sorted(companies_seen[code]["surfaces"])
        longest = sorted(surfaces, key=lambda s: (-len(s), s))[0]
        index[code] = {
            "stock_code": code,
            "company_name": longest,
            "short_name": entry["short_name"],
            "registered_name": entry.get("registered_name") or "",
            "registered_name_source": entry.get("registered_name_source") or "unknown",
            "aliases": [s for s in surfaces if s != longest],
            "exchange": entry["exchange"],
            "industry": entry["industry"],
            "observed_surfaces": surfaces,
            "doc_ids": sorted(companies_seen[code]["doc_ids"]),
        }
    return index


def build_industry_index(alias_table, entity_map):
    """Industry 节点的属性来源：抽取到的行业名 ＋ 配置里同名行业（供 `level` 等留空时参考）。"""
    configured = {}
    for code in sorted(alias_table):
        industry = alias_table[code]["industry"]
        if industry:
            configured.setdefault(config.normalize_entity_name(industry), []).append(code)
    index = {}
    for item in entity_map.values():
        if item["label"] != "Industry":
            continue
        key = item["identity_key"]
        index[key] = {
            "identity_key": key,
            "industry_name": item["normalized_name"],
            "configured_codes": sorted(configured.get(item["normalized_name"], [])),
            "level": "",   # 表 4-8 有 level 属性，但语料未给行业层级：留空，不猜
        }
    return {k: index[k] for k in sorted(index)}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run(args) -> int:
    paths = config.pipeline_paths(args.profile)
    records = load_records(args.profile)
    if not records:
        print("输入为空：%s（T4 不产出空产物）" % paths["extract_records"])
        return 1
    fingerprint = source_fingerprint(records, paths["extract_records"])

    if os.path.isfile(paths["disambiguation"]) and not args.force:
        with open(paths["disambiguation"], encoding="utf-8") as fh:
            previous = json.load(fh)
        if previous.get("cache_fingerprint") == fingerprint:
            print("[跳过] 消歧产物已是最新（缓存指纹一致）：%s" % paths["disambiguation"])
            print("       删掉该文件或用 --force 可重算。")
            return 0
        print("[注意] 已有产物与当前缓存指纹不一致，重算：%s" % paths["disambiguation"])

    alias_table = build_alias_table()
    _registered_table, registered_meta = load_registered_names()
    entity_map, unresolved, companies_seen = disambiguate_records(records, alias_table)
    unresolved.sort(key=lambda r: (r["doc_id"], r["entity_id"], r["reason"]))
    company_index = build_company_index(alias_table, companies_seen)
    industry_index = build_industry_index(alias_table, entity_map)

    by_label = {}
    for item in entity_map.values():
        by_label.setdefault(item["label"], {"total": 0, "resolved": 0, "unresolved": 0})
        by_label[item["label"]]["total"] += 1
        by_label[item["label"]][item["status"]] += 1
    reason_counts = {}
    for row in unresolved:
        reason_counts[row["reason"]] = reason_counts.get(row["reason"], 0) + 1

    alias_payload = {
        "schema": config.DISAMBIG_SCHEMA,
        "dataset_version": config.DATASET_VERSION,
        "source": {
            "path": os.path.relpath(config.DISAMBIG["alias_source_path"], config.ROOT)
                    .replace("\\", "/"),
            "attribute": config.DISAMBIG["alias_source_attr"],
            "registered_names_path": registered_meta["path"],
            "registered_names_attr": config.DISAMBIG["registered_names_attr"],
            "registered_names_schema": registered_meta["schema"],
            "registered_names_endpoint": registered_meta["source_endpoint"],
            "registered_names_endpoint_field": registered_meta["source_endpoint_field"],
            "registered_names_corpus_min_corroboration":
                registered_meta["corpus_min_corroboration"],
            "registered_names_source_counts":
                {k: registered_meta["source_counts"][k]
                 for k in sorted(registered_meta["source_counts"])},
            "note": ("只读第 5 阶段已冻结的配置公司集（公司名单与简称不改），另只读"
                     "build_company_aliases.py 建档的注册全称补充（逐家带来源与证据）；"
                     "本文件不改动数据来源，也不新增公司。"),
        },
        "match_rules": config.DISAMBIG["match_rules"],
        "distinct_entity_markers": config.DISAMBIG["distinct_entity_markers"],
        "normalized_alias_surfaces_note": (
            "每个 code 的 normalized_alias_surfaces ＝ 归一化简称 ∪ 归一化注册全称；"
            "两条匹配规则对其中每一个书写面求值（数据扩展，规则未改）"),
        "companies": alias_table,
        "company_count": len(alias_table),
    }
    disambig_payload = {
        "schema": config.DISAMBIG_SCHEMA,
        "dataset_version": config.DATASET_VERSION,
        "profile": args.profile,
        # 本文件**不写时间戳**：消歧映射与待消歧清单要能被逐字节比对（《15》第八节），
        # 只有 T6 的 graph_stats.json 按《15》第八节 允许留 `generated_at`（单独成行、不参与比较）。
        "cache_fingerprint": fingerprint,
        "rule": {
            "company": config.DISAMBIG["match_rules"],
            "non_company": config.DISAMBIG["non_company_rule"],
            "normalize": "去空白 ＋ 剥最外层包裹字符（config.normalize_entity_name）",
            "unresolved_company_policy": config.DISAMBIG["unresolved_company_policy"],
            "note": "身份键 <标签>:<身份>；未消歧的公司 identity_key 为 null。",
        },
        "entity_map": entity_map,
        "companies": company_index,
        "industries": industry_index,
        "counts": {
            "entities": len(entity_map),
            "resolved": sum(1 for i in entity_map.values() if i["status"] == "resolved"),
            "unresolved": len(unresolved),
            "by_label": {k: by_label[k] for k in sorted(by_label)},
            "unresolved_by_reason": {k: reason_counts[k] for k in sorted(reason_counts)},
            "company_identities": len(company_index),
            "company_identities_with_multiple_surfaces":
                sum(1 for c in company_index.values() if len(c["observed_surfaces"]) > 1),
            "company_registered_name_sources":
                {src: sum(1 for e in alias_table.values()
                          if (e.get("registered_name_source") or "unknown") == src)
                 for src in sorted({(e.get("registered_name_source") or "unknown")
                                    for e in alias_table.values()})},
            "company_registered_names_missing":
                sum(1 for e in alias_table.values() if not e.get("registered_name")),
        },
    }
    dump_json(paths["alias_table"], alias_payload)
    dump_json(paths["disambiguation"], disambig_payload)
    dump_jsonl(paths["unresolved"], unresolved)

    print("输入：%s（%d 篇，sha256=%s…）"
          % (paths["extract_records"], len(records), fingerprint["extract_records_sha256"][:16]))
    print("别名表：%d 家配置公司（只读自 %s）"
          % (len(alias_table), alias_payload["source"]["path"]))
    registered_counts = {k: registered_meta["source_counts"][k]
                         for k in sorted(registered_meta["source_counts"])}
    print("        注册全称补充 %s：来源分布 %s"
          % (registered_meta["path"], registered_counts or {"unknown": len(alias_table)}))
    print("实体 %d 条：已判身份 %d／待消歧 %d"
          % (len(entity_map), disambig_payload["counts"]["resolved"], len(unresolved)))
    for label in sorted(by_label):
        stat = by_label[label]
        print("  %-12s 共 %-3d 已判 %-3d 待消歧 %-3d"
              % (label, stat["total"], stat["resolved"], stat["unresolved"]))
    if reason_counts:
        print("  待消歧原因：%s" % {k: reason_counts[k] for k in sorted(reason_counts)})
    print("归并出的公司身份 %d 个（其中 %d 个有多种写法被归并到同一个 stock_code）"
          % (disambig_payload["counts"]["company_identities"],
             disambig_payload["counts"]["company_identities_with_multiple_surfaces"]))
    print("产物：%s" % paths["alias_table"])
    print("      %s" % paths["disambiguation"])
    print("      %s（%d 条）" % (paths["unresolved"], len(unresolved)))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 6 阶段实体消歧（T4；参数一律取自 config.py，不调用模型）")
    parser.add_argument("--profile", default="pilot", choices=["pilot", "v21"],
                        help="pilot＝12 篇试跑（默认）；v21＝全量 709 篇")
    parser.add_argument("--force", action="store_true", help="忽略已有产物，重算并重写")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SystemExit as exc:
        print("[阻断] %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
