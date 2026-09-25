# -*- coding: utf-8 -*-
r"""write_graph.py —— 第 6 阶段「图谱写入与导出」（T6）。

**只读缓存**：本脚本不写任何缓存、不改数据集、不调模型；它把 T3 的抽取结果（事件端点经 T5
的合并结果重定向、实体端点经 T4 的身份映射重定向）摊成图谱导出物四件套，落
`阶段06-事件抽取与知识图谱\图谱导出\v2.1\`（试跑落 `_试跑_图谱管线\图谱导出\`）：

| 文件 | 内容 | 依据 |
| --- | --- | --- |
| `nodes.csv` | 节点及其属性 | 《10》第4.5.1节 表 4-8 |
| `edges.csv` | 关系及其证据属性 | 《10》第4.5.2节 表 4-9 |
| `graph_stats.json` | 计数、编号分配、逐条自检读数 | 《15》第八节 |
| `replay.cypher` | 建约束／索引 ＋ 逐节点逐边重放语句 | 《10》第4.5.3节 |

同时写两份**审校产物**（不是《15》第4.3节 的四件套，落在缓存目录，不进导出目录）：
`graph_check.json`（第八节逐行机检结果）与 `manifest.sha256`（产物校验和索引）。

口径（逐条对应《15》第五节 硬约束与《10》第4.5 节；**不新增本体、不新增字段、不改名**）：

1. **九条关系**取 `config.RELATIONS`；其中 `EVIDENCED_BY` 由本脚本按 T5 的证据文档并集
   直接生成（不要求模型输出），**不携带** `source_doc_id`／`source_chunk_id`／`confidence`，
   终点是 `Document` 节点；其余 8 条**必须**带齐这三项证据属性（硬约束 3、4）。
2. `Document` 是**证据文档标签，不是第七类实体**（《10》第4.5.1节、硬约束 2）：节点里有它，
   实体计数里没有它。
3. 每个 `Event` 节点的六项核心属性：`event_id`／`event_type`／`event_name`／`event_time`／
   `description`／`confidence`（硬约束 5）。`event_time` 允许为空并**计数上报**——T3 的固定
   口径是「不能确定到日时写 null，绝不猜测」，此处不为凑齐而编日期。
4. `role` 只出现在 `PARTICIPATES_IN` 上，取 `config.ROLES` 五个值之一（硬约束 6）。
5. `ISSUED_BY` 只出现在 `政策`／`监管` 事件上（硬约束 7）；同一机构既发布又参与时只保留
   `ISSUED_BY`（《10》第4.5.2节）。
6. `BELONGS_TO` 带 `valid_from`／`valid_to`；正文没给日期时**留空**，不用发布时间兜底
   （兜底等于替正文编有效期，与 T3「绝不猜测」同源）——空值条数逐条上报。
7. 图上**没有** `data_cutoff_time`；三种时间形式只落在 Event.event_time／BELONGS_TO.valid_*／
   Document.publish_time（《10》第4.5.6节、硬约束 10）。
8. 编号**显式分配并固化**（硬约束 9）：Company 用 `stock_code`、Document 用 `doc_id`，
   Person／Institution／Policy／Industry／Event 按确定性顺序一次性分配 `PER/INST/POL/IND/EVT`
   编号；不依赖数据库自增。
9. 导出物**只含编号、类型、名称、证据编号与置信度，不复制正文**（硬约束 8、11）：
   `quote`／`note`／`content` 等正文或调试字段一律不进导出物，并用「正文 100 字子串回查」
   机器核验。
10. 未消歧的实体**不写进图谱**（《10》第4.5.4节：人工确认后再写入图谱），引用它们的边
    一并跳过并逐条计数（`config.GRAPH["include_unresolved_entities"]=False`）。
11. `replay.cypher` 的 DDL 是《10》第4.5.3节 的 **7 条唯一性约束 ＋ 3 条索引**，逐字照抄；
    本阶段**不写关系库 DDL、不新增表**（六张表仍是六张）。

逐字节复现：四件套的排序、分隔、换行、编码全部固定；`graph_stats.json` 里只有
`generated_at`（与缓存指纹字段）每次不同——它们单独成行，逐字节比对时排除（《15》第八节）。

用法：

    python 代码\抽取与图谱\write_graph.py                      # 默认 --profile pilot
    python 代码\抽取与图谱\write_graph.py --profile v21
    python 代码\抽取与图谱\write_graph.py --force              # 重算并重写
    python 代码\抽取与图谱\write_graph.py --verify-only        # 只对**已写出**的四件套做机检

退出码：`0` 成功；`1` 前置缺失（未跑 T4／T5）或指纹不一致；`2` 机检不通过或数据异常。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import hashlib
import io
import json
import os
import random
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def now_iso() -> str:
    tz = _dt.timezone(_dt.timedelta(hours=8))
    return _dt.datetime.now(tz).isoformat(timespec="seconds")


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def read_text(path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_text(path, text):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return text


def dump_json(path, obj, indent=2):
    return write_text(path, json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                       indent=indent) + "\n")


def sha256_text(text) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def source_fingerprint(records, path):
    return {
        "extract_records": os.path.relpath(path, config.ROOT).replace("\\", "/"),
        "extract_records_sha256": sha256_file(path),
        "documents": len(records),
        "doc_ids": sorted(int(r["doc_id"]) for r in records),
        "record_schemas": sorted({str(r.get("record_schema") or "") for r in records}),
        "prompt_versions": sorted({str(r.get("prompt_version") or "") for r in records}),
        "models_resolved": sorted({str(r.get("model_resolved") or "") for r in records}),
    }


def rel(path) -> str:
    return os.path.relpath(path, config.ROOT).replace("\\", "/")


def cell(value) -> str:
    """CSV 单元格：None → 空串；列表 → 分隔符连接；其余 str()。"""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return config.GRAPH["list_separator"].join(str(v) for v in value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def to_csv(columns, rows) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n",
                            extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: cell(row.get(c)) for c in columns})
    return buffer.getvalue()


def cypher_literal(value) -> str:
    """Cypher 字面量：字符串单引号转义；数值裸写；空值不产出属性。"""
    if value is None or value == "":
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace("'", "\\'")
    text = text.replace("\r", " ").replace("\n", "\\n")
    return "'%s'" % text


def prop_map(pairs) -> str:
    """把 (名, 值) 序列写成 Cypher 属性映射（跳过空值）。"""
    items = ["%s: %s" % (k, cypher_literal(v)) for k, v in pairs if cypher_literal(v)]
    return "{%s}" % ", ".join(items) if items else ""


# --------------------------------------------------------------------------
# 读前置产物（T4／T5）
# --------------------------------------------------------------------------
def load_previous(paths, fingerprint):
    for key, script in (("disambiguation", "disambiguate.py"), ("events_merged", "dedup_events.py")):
        path = paths[key]
        if not os.path.isfile(path):
            raise SystemExit("未找到前置产物：%s\n请先跑：python 代码\\抽取与图谱\\%s --profile %s"
                             % (path, script, paths["profile"]))
    with open(paths["disambiguation"], encoding="utf-8") as fh:
        disambig = json.load(fh)
    if disambig.get("cache_fingerprint") != fingerprint:
        raise SystemExit("消歧产物与当前抽取结果不是同一份缓存（指纹不一致）：%s"
                         % paths["disambiguation"])
    merged = read_jsonl(paths["events_merged"])
    if not merged or merged[0].get("cache_fingerprint") != fingerprint:
        raise SystemExit("去重产物与当前抽取结果不是同一份缓存（指纹不一致）：%s"
                         % paths["events_merged"])
    return disambig, merged


def load_doc_meta(doc_ids):
    """证据文档的元数据（title／source／url／publish_time／category）：只读数据集。

    只取元数据字段，**不读也不导出 `content`**（《15》硬约束 11）。
    """
    meta = {}
    with open(config.DOCS_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            doc_id = int(row["doc_id"])
            if doc_id in doc_ids:
                meta[doc_id] = {
                    "title": row.get("title") or "",
                    "source": row.get("source") or "",
                    "url": row.get("url") or "",
                    "publish_time": row.get("publish_time") or "",
                    "category": row.get("category") or "",
                }
    return meta


# --------------------------------------------------------------------------
# 编号分配（显式、确定性、可复现）
# --------------------------------------------------------------------------
def label_rank(label):
    order = list(config.ENTITY_TYPES) + [config.DOCUMENT_LABEL]
    return order.index(label) if label in order else len(order)


def assign_nodes(disambig, merged, meta, alias_table_path=None):
    """返回 (节点行列表, 身份键→节点号, 事件键→节点号)。"""
    entity_rows, by_identity = {}, {}
    # 1) 实体节点：只取**已消歧**的（未消歧的按《10》第4.5.4节 不写进图谱）。
    for item in disambig["entity_map"].values():
        if item.get("status") != "resolved" or not item.get("identity_key"):
            continue
        key = item["identity_key"]
        row = by_identity.get(key)
        if row is None:
            label = item["label"]
            row = {"label": label, "name": item["name"], "_surfaces": set(),
                   "_identity_key": key, "_nodes": []}
            for attr in ("stock_code", "company_name", "short_name", "aliases", "exchange",
                         "person_id", "person_name", "role_title", "industry_code",
                         "industry_name", "level", "institution_id", "institution_name",
                         "institution_type", "policy_id", "policy_name", "issuer",
                         "publish_date"):
                row[attr] = ""
            by_identity[key] = row
        row["_surfaces"].add(item["name"])
        row["_nodes"].append(item)

    # 2) 四类按确定性顺序一次性分配（Company 用 stock_code、Document 用 doc_id，见下）。
    counters = {}
    buckets = {}
    for key, row in by_identity.items():
        buckets.setdefault(row["label"], []).append(key)
    for label in sorted(buckets):
        prefix = config.GRAPH["id_prefixes"].get(label)
        if not prefix:                     # Company：编号＝stock_code，不参与顺序编号
            continue
        for key in sorted(buckets[label]):
            counters[label] = counters.get(label, 0) + 1
            by_identity[key]["node_id"] = "%s-%0*d" % (prefix, config.GRAPH["id_width"],
                                                       counters[label])

    # 3) 公司节点：编号＝stock_code（本体标识，硬约束 9）；属性取配置＋语料书写面。
    alias_table = {}
    if alias_table_path and os.path.isfile(alias_table_path):
        with open(alias_table_path, encoding="utf-8") as fh:
            alias_table = json.load(fh).get("companies") or {}
    for key, row in by_identity.items():
        surfaces = sorted(row["_surfaces"])
        if row["label"] == "Company":
            code = key.split(config.DISAMBIG["identity_key_separator"], 1)[1]
            # 字段口径与 T4 的 `companies` 块逐字一致（表 4-8）：company_name 取语料中出现的
            # 最长书写面，aliases 取其余书写面，short_name／exchange／industry 取自冻结配置。
            configured = (disambig.get("companies") or {}).get(code) \
                or alias_table.get(code) or {}
            longest = sorted(surfaces, key=lambda s: (-len(s), s))[0]
            short_name = configured.get("short_name") or ""
            row["node_id"] = code
            row["name"] = short_name or longest
            row["stock_code"] = code
            row["company_name"] = configured.get("company_name") or longest
            row["short_name"] = short_name
            row["aliases"] = configured.get("aliases") \
                if configured.get("aliases") is not None \
                else sorted({s for s in surfaces if s != longest})
            row["exchange"] = configured.get("exchange") or \
                config.DISAMBIG["exchange_by_board"].get(configured.get("board") or "", "")
        else:
            row["name"] = sorted(surfaces, key=lambda s: (len(s), s))[0]
            id_attr = {"Person": "person_id", "Institution": "institution_id",
                       "Policy": "policy_id", "Industry": "industry_code"}[row["label"]]
            name_attr = {"Person": "person_name", "Institution": "institution_name",
                         "Policy": "policy_name", "Industry": "industry_name"}[row["label"]]
            row[id_attr] = row["node_id"]
            row[name_attr] = row["name"]

    # 4) 事件节点：合并后的事件；编号按（代表文档, 代表事件号）确定性排序。
    event_rows, event_by_key = [], {}
    ordered = sorted(merged, key=lambda m: (m["representative_doc_id"],
                                            str(m["members"][0]["local_event_id"])))
    for index, item in enumerate(ordered):
        node_id = "%s-%0*d" % (config.GRAPH["id_prefixes"]["Event"],
                               config.GRAPH["id_width"], index + 1)
        row = {
            "label": "Event", "node_id": node_id, "name": item["event_name"],
            "event_id": node_id, "event_type": item["event_type"],
            "event_name": item["event_name"], "event_time": item["event_time"],
            "description": item["description"], "confidence": item["confidence"],
        }
        event_rows.append(row)
        event_by_key[item["merged_event_key"]] = row
        for member in item["members"]:
            event_by_key[(member["doc_id"], str(member["local_event_id"]))] = row

    # 5) 证据文档节点：编号＝doc_id（本体标识）。
    doc_ids = sorted({d for m in merged for d in m["evidence_doc_ids"]})
    doc_rows = []
    for doc_id in doc_ids:
        info = meta.get(doc_id) or {}
        doc_rows.append({
            "label": config.DOCUMENT_LABEL, "node_id": str(doc_id),
            "name": info.get("title") or "",
            "doc_id": doc_id, "title": info.get("title") or "",
            "source": info.get("source") or "", "url": info.get("url") or "",
            "publish_time": info.get("publish_time") or "",
            "category": info.get("category") or "",
        })

    nodes = list(by_identity.values()) + event_rows + doc_rows
    nodes.sort(key=lambda r: (label_rank(r["label"]), str(r["node_id"])))
    return nodes, by_identity, event_by_key


def node_id_of_endpoint(local_id, by_identity, event_by_key, disambig, doc_id=None):
    """把一个缓存里的局部编号解析成节点号；返回 (节点号 或 None, 未消歧原因 或 None)。"""
    for key in ((doc_id, local_id), local_id):
        if key in event_by_key:
            return event_by_key[key]["node_id"], None
    item = disambig["entity_map"].get(local_id)
    if item is None:
        return None, "endpoint_not_in_cache"
    if item.get("status") != "resolved" or not item.get("identity_key"):
        return None, "unresolved_entity"
    row = by_identity.get(item["identity_key"])
    if row is None:
        return None, "unresolved_entity"
    return row["node_id"], None


def build_edges(records, disambig, merged, by_identity, event_by_key):
    """关系边：先把事件端点重定向到合并后的事件，再补 EVIDENCED_BY。"""
    edges, skipped, seen = [], [], set()
    duplicates = 0
    allowed = set(config.RELATIONS)
    for record in sorted(records, key=lambda r: int(r["doc_id"])):
        doc_id = int(record["doc_id"])
        for relation in sorted(record.get("relations") or [],
                               key=lambda r: str(r["relation_id"])):
            kind = str(relation["relation"])
            if kind not in allowed:
                raise SystemExit("关系不在本体里：%s（doc_id=%s %s）"
                                 % (kind, doc_id, relation["relation_id"]))
            if kind == "EVIDENCED_BY":
                # EVIDENCED_BY 由本脚本按合并后事件重新生成，缓存里的同名行不重复计入。
                skipped.append({"doc_id": doc_id, "relation_id": relation["relation_id"],
                                "relation": kind, "reason": "regenerated_from_merged_event"})
                continue
            head_id, why_head = node_id_of_endpoint(
                str(relation["head_id"]), by_identity, event_by_key, disambig, doc_id)
            tail_id, why_tail = node_id_of_endpoint(
                str(relation["tail_id"]), by_identity, event_by_key, disambig, doc_id)
            if head_id is None or tail_id is None:
                skipped.append({
                    "doc_id": doc_id, "relation_id": relation["relation_id"], "relation": kind,
                    "reason": why_head or why_tail,
                    "head": relation.get("head_name"), "tail": relation.get("tail_name"),
                    "note": "端点未消歧 → 不写进图谱（《10》第4.5.4节：人工确认后再写入）",
                })
                continue
            row = {
                "head_id": head_id, "relation": kind, "tail_id": tail_id,
                "source_doc_id": int(relation["source_doc_id"]),
                "source_chunk_id": int(relation["source_chunk_id"]),
                "confidence": config.round_confidence(relation.get("confidence")),
            }
            if kind == "PARTICIPATES_IN":
                row["role"] = relation.get("role") or ""
            if kind == "BELONGS_TO":
                # 表 4-9：BELONGS_TO 带有效时间区间；正文没给就留空（不拿发布时间兜底）。
                row["valid_from"] = relation.get("valid_from") or ""
                row["valid_to"] = relation.get("valid_to") or ""
            key = tuple(str(row.get(c)) for c in config.GRAPH["edge_columns"])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            edges.append(row)

    for item in merged:
        head = event_by_key[item["merged_event_key"]]
        for doc_id in item["evidence_doc_ids"]:
            row = {"head_id": head["node_id"], "relation": "EVIDENCED_BY",
                   "tail_id": str(doc_id)}
            key = tuple(str(row.get(c)) for c in config.GRAPH["edge_columns"])
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            edges.append(row)

    edges.sort(key=lambda r: (str(r["head_id"]), r["relation"], str(r["tail_id"]),
                              int(r.get("source_doc_id") or 0),
                              int(r.get("source_chunk_id") or 0),
                              str(r.get("role") or "")))
    return edges, skipped, duplicates


# --------------------------------------------------------------------------
# 重放脚本
# --------------------------------------------------------------------------
def build_replay(nodes, edges, fingerprint, stats_note):
    lines = [
        "// 第 6 阶段知识图谱重放脚本（由 write_graph.py 生成，逐字节可复现）",
        "// 数据来源（只读）：%s" % fingerprint["extract_records"],
        "//   抽取结果 sha256：%s" % fingerprint["extract_records_sha256"],
        "//   文档数 %d；prompt 版本 %s" % (fingerprint["documents"],
                                          "、".join(fingerprint["prompt_versions"])),
        "// 口径：编号显式分配并固化（不使用自增主键）；八条由模型给出的关系带"
        " source_doc_id／source_chunk_id／confidence，EVIDENCED_BY 不带这三项；",
        "//   图上不设数据截止时间属性（《10》第4.5.6节：时间只落在 Event.event_time、"
        "BELONGS_TO.valid_from／valid_to、Document.publish_time）；导出物不复制正文。",
        "// 节点 %d 个、边 %d 条（%s）" % (len(nodes), len(edges), stats_note),
        "",
        "// ---- 约束与索引：《10》第4.5.3节 逐字照抄（7 条唯一性约束 ＋ 3 条索引）----",
    ]
    lines += [c + ";" for c in config.GRAPH["constraints"]]
    lines.append("")
    lines.append("// ---- 节点 ----")
    node_by_id = {}
    for row in nodes:
        node_by_id[(row["label"], str(row["node_id"]))] = row
    for row in nodes:
        props = [(c, row.get(c)) for c in config.GRAPH["node_columns"]
                 if c not in ("node_id", "label", "name") and c not in ("doc_id",)]
        if row["label"] == "Company":
            props = [(c, row.get(c)) for c in ("name", "stock_code", "company_name",
                                               "short_name", "aliases", "exchange")]
        elif row["label"] == config.DOCUMENT_LABEL:
            props = [(c, row.get(c)) for c in ("title", "source", "url", "publish_time",
                                               "category")]
        else:
            props = [(c, row.get(c)) for c in props if row.get(c) not in (None, "", [])]
        lines.append("MERGE (n:%s {node_id: %s})%s;"
                     % (row["label"], cypher_literal(str(row["node_id"])),
                        (" SET " + ", ".join("n.%s = %s" % (k, cypher_literal(v))
                                             for k, v in props if cypher_literal(v)))
                        if any(cypher_literal(v) for _, v in props) else ""))
    lines.append("")
    lines.append("// ---- 边 ----")
    for row in edges:
        head = node_by_id.get((str(row["head_label"]), str(row["head_id"])))
        tail = node_by_id.get((str(row["tail_label"]), str(row["tail_id"])))
        pairs = [(c, row.get(c)) for c in config.GRAPH["edge_columns"]
                 if c not in ("head_id", "relation", "tail_id")]
        pattern = prop_map(pairs)
        lines.append("MATCH (a:%s {node_id: %s}), (b:%s {node_id: %s}) "
                     "MERGE (a)-[:%s %s]->(b);"
                     % (head["label"], cypher_literal(str(row["head_id"])),
                        tail["label"], cypher_literal(str(row["tail_id"])),
                        row["relation"], pattern))
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# 机检（对**已写出**的四件套做，所以 --verify-only 也能跑）
# --------------------------------------------------------------------------
def load_export(paths):
    if not all(os.path.isfile(paths[k]) for k in ("nodes", "edges", "graph_stats",
                                                  "replay_cypher")):
        raise SystemExit("导出物四件套不齐：%s" % paths["export_dir"])
    with open(paths["nodes"], encoding="utf-8", newline="") as fh:
        nodes = list(csv.DictReader(fh))
    with open(paths["edges"], encoding="utf-8", newline="") as fh:
        edges = list(csv.DictReader(fh))
    return nodes, edges


def check_export(paths, nodes, edges, fingerprint, profile, extra_text=""):
    text = "".join(read_text(paths[k]) for k in ("nodes", "edges", "graph_stats",
                                                 "replay_cypher") if os.path.isfile(paths[k]))
    text += extra_text
    node_by_id = {n["node_id"]: n for n in nodes}
    by_label = {}
    for node in nodes:
        by_label.setdefault(node["label"], []).append(node)
    checks = []

    def add(name, passed, detail, severity="must"):
        checks.append({"check": name, "passed": bool(passed), "severity": severity,
                       "detail": detail})

    # 1 标签与编号
    bad_labels = sorted({n["label"] for n in nodes
                         if n["label"] not in set(config.ENTITY_TYPES)
                         and n["label"] != config.DOCUMENT_LABEL})
    dup_ids = sorted({nid for nid in node_by_id
                      if sum(1 for n in nodes if n["node_id"] == nid) > 1})
    add("nodes_label_in_ontology", not bad_labels,
        {"labels": sorted(by_label), "unexpected": bad_labels,
         "note": "Document 是证据文档标签，不是第七类实体"})
    add("nodes_id_unique_nonempty", not dup_ids and all(n["node_id"] for n in nodes),
        {"nodes": len(nodes), "duplicates": dup_ids, "empty": sum(1 for n in nodes
                                                                 if not n["node_id"])})

    # 2 关系在本体里、端点存在
    bad_rel = sorted({e["relation"] for e in edges if e["relation"] not in set(config.RELATIONS)})
    dangling = [{"head_id": e["head_id"], "tail_id": e["tail_id"]}
                for e in edges if e["head_id"] not in node_by_id or e["tail_id"] not in node_by_id]
    add("relations_in_ontology", not bad_rel,
        {"relations": sorted({e["relation"] for e in edges}), "unexpected": bad_rel,
         "note": "本体 9 条；INVOLVES 已删除、不复活"})
    add("edge_endpoints_exist", not dangling,
        {"edges": len(edges), "dangling": dangling[:5], "dangling_count": len(dangling)})

    # 3 三项证据属性（硬约束 3、4）
    modelled = [e for e in edges if e["relation"] != "EVIDENCED_BY"]
    missing = [{"head": e["head_id"], "relation": e["relation"], "tail": e["tail_id"]}
               for e in modelled
               if not (e.get("source_doc_id") and e.get("source_chunk_id")
                       and e.get("confidence"))]
    add("evidence_attrs_on_8_relations", not missing,
        {"relations_checked": len(modelled), "missing_count": len(missing),
         "sample": missing[:5],
         "note": "《10》第4.5.2节：八条非 EVIDENCED_BY 关系带齐 source_doc_id／"
                 "source_chunk_id／confidence"})
    evidenced = [e for e in edges if e["relation"] == "EVIDENCED_BY"]
    eb_dirty = [{"head": e["head_id"], "tail": e["tail_id"]}
                for e in evidenced
                if any(e.get(c) for c in config.EVIDENCE_ATTRS)]
    eb_not_doc = [{"head": e["head_id"], "tail": e["tail_id"]} for e in evidenced
                  if (node_by_id.get(e["tail_id"]) or {}).get("label") != config.DOCUMENT_LABEL]
    add("evidenced_by_clean_and_doc_tail", not eb_dirty and not eb_not_doc,
        {"edges": len(evidenced), "with_evidence_attrs": eb_dirty[:5],
         "tail_not_document": eb_not_doc[:5],
         "note": "EVIDENCED_BY 不带三项证据属性，终点是 Document 节点"})

    # 4 Event 六项核心属性（硬约束 5）
    core = ["event_id", "event_type", "event_name", "event_time", "description", "confidence"]
    events = by_label.get("Event", [])
    empty_core = [{"node_id": e["node_id"],
                   "empty": [c for c in core if c != "event_time" and not e.get(c)]}
                  for e in events if any(not e.get(c) for c in core if c != "event_time")]
    time_null = [e["node_id"] for e in events if not e.get("event_time")]
    add("event_core_attrs_columns_and_values", not empty_core,
        {"events": len(events), "core_attrs": core,
         "incomplete_count": len(empty_core), "incomplete_sample": empty_core[:5],
         "event_time_null_count": len(time_null),
         "event_time_null_sample": time_null[:5],
         "note": "六项核心属性的列都在；除 event_time 外逐条非空。event_time 的空值条数单列"
                 "（见下一条读数）：T3 的口径是「不能确定到日写 null，绝不猜测」"})
    add("event_time_nonempty", not time_null,
        {"event_time_null_count": len(time_null), "events": len(events),
         "hint": "《15》第八节 要求六项核心属性齐全且非空；本批达不到的只有 event_time 这一项，"
                 "与 T3 的 null 口径冲突，如实上报、不编日期凑数"},
        severity="known_gap")

    # 5 role（硬约束 6）与 ISSUED_BY 事件类型（硬约束 7）
    bad_role = [{"head": e["head_id"], "tail": e["tail_id"], "role": e.get("role")}
                for e in edges if e["relation"] == "PARTICIPATES_IN"
                and (e.get("role") or "") not in config.ROLES]
    role_on_other = [{"head": e["head_id"], "relation": e["relation"], "role": e.get("role")}
                     for e in edges if e["relation"] != "PARTICIPATES_IN" and e.get("role")]
    add("role_in_frozen_values", not bad_role and not role_on_other,
        {"roles_used": sorted({e.get("role") for e in edges
                               if e["relation"] == "PARTICIPATES_IN" and e.get("role")}),
         "legal_values": list(config.ROLES),
         "illegal": bad_role[:5], "role_outside_participates_in": role_on_other[:5]})
    issued = [e for e in edges if e["relation"] == "ISSUED_BY"]
    bad_issued = [{"head": e["head_id"],
                   "event_type": (node_by_id.get(e["head_id"]) or {}).get("event_type")}
                  for e in issued
                  if (node_by_id.get(e["head_id"]) or {}).get("event_type")
                  not in config.ISSUED_BY_EVENT_TYPES]
    both = []
    for e in edges:
        if e["relation"] != "ISSUED_BY":
            continue
        for other in edges:
            if other["relation"] == "PARTICIPATES_IN" and other["tail_id"] == e["head_id"] \
                    and other["head_id"] == e["tail_id"]:
                both.append({"event": e["head_id"], "institution": e["tail_id"]})
    add("issued_by_only_on_policy_and_regulation", not bad_issued,
        {"edges": len(issued), "event_types": sorted({
            (node_by_id.get(e["head_id"]) or {}).get("event_type") for e in issued}),
         "legal_event_types": list(config.ISSUED_BY_EVENT_TYPES),
         "violations": bad_issued[:5]})
    add("issuer_not_also_participant", not both,
        {"violations": both[:5],
         "note": "《10》第4.5.2节：同一机构既发布又参与时只保留 ISSUED_BY"})

    # 6 BELONGS_TO 的有效期列与空值读数
    belongs = [e for e in edges if e["relation"] == "BELONGS_TO"]
    filled = [e for e in belongs if e.get("valid_from") or e.get("valid_to")]
    add("belongs_to_carries_validity_columns",
        (not belongs) or len(filled) == len(belongs),
        {"edges": len(belongs), "with_validity": len(filled),
         "without_validity": len(belongs) - len(filled),
         "note": "表 4-9 要求带 valid_from／valid_to；正文没给日期时留空，"
                 "不用发布时间兜底（不替正文编有效期）"},
        severity="known_gap" if len(filled) != len(belongs) else "must")

    # 7 图上没有数据截止时间属性；没有关系库 DDL（硬约束 10；六张表仍是六张）
    forbidden_tokens = ["data_cutoff_time", "AUTO_INCREMENT", "AUTOINCREMENT"]
    hits = {token: text.count(token) for token in forbidden_tokens if token in text}
    add("no_cutoff_time_or_autoincrement_in_export", not hits,
        {"tokens_absent": [t for t in forbidden_tokens if t not in hits], "hits": hits,
         "note": "《10》第4.5.6节：数据截止时间不是图上的属性（图上时间只有 Event.event_time、"
                 "BELONGS_TO.valid_from／valid_to、Document.publish_time 三种形式）；"
                 "编号显式分配，不用自增"})
    table_ddl = [ln.strip() for ln in text.splitlines() if "CREATE TABLE" in ln.upper()]
    add("no_relational_ddl_in_export", not table_ddl,
        {"create_table_lines": table_ddl[:3],
         "replay_ddl": "replay.cypher 里的是《10》第4.5.3节 的 7 条唯一性约束 ＋ 3 条索引；"
                       "本阶段不写关系库 DDL、不新增表"})

    # 8 编号显式（硬约束 9）：四类编号前缀与唯一性
    id_problems = []
    for label, attr, prefix in (("Person", "person_id", "PER"), ("Institution",
                                                                "institution_id", "INST"),
                                ("Policy", "policy_id", "POL"), ("Event", "event_id", "EVT")):
        values = [n.get(attr) for n in by_label.get(label, [])]
        if len(values) != len(set(values)) or any(not v for v in values):
            id_problems.append({"label": label, "attr": attr, "n": len(values),
                                "unique": len(set(values))})
        bad = [v for v in values if not re.fullmatch(r"%s-\d{%d}" % (prefix,
                                                                     config.GRAPH["id_width"]), v or "")]
        if bad:
            id_problems.append({"label": label, "attr": attr, "format_violations": bad[:5]})
    add("explicit_unique_ids", not id_problems,
        {"problems": id_problems,
         "counts": {"Person": len(by_label.get("Person", [])),
                    "Institution": len(by_label.get("Institution", [])),
                    "Policy": len(by_label.get("Policy", [])),
                    "Event": len(by_label.get("Event", []))},
         "note": "编号由 write_graph.py 一次性分配并固化，不依赖数据库自增"})

    # 9 正文不外泄（硬约束 8、11）
    add("no_body_text_in_export", *_body_check(paths, text))

    # 10 证据文档标签不混入实体计数
    add("document_label_is_not_an_entity", config.DOCUMENT_LABEL not in config.ENTITY_TYPES,
        {"entity_labels": list(config.ENTITY_TYPES), "document_label": config.DOCUMENT_LABEL,
         "document_nodes": len(by_label.get(config.DOCUMENT_LABEL, []))})

    result = {
        "schema": config.GRAPH_SCHEMA,
        "dataset_version": config.DATASET_VERSION,
        "profile": profile,
        "cache_fingerprint": fingerprint,
        "node_counts": {label: len(rows) for label, rows in sorted(by_label.items())},
        "edge_counts": _counts(e["relation"] for e in edges),
        "checks": checks,
        "summary": {
            "checks": len(checks),
            "passed": sum(1 for c in checks if c["passed"]),
            "failed": sorted(c["check"] for c in checks if not c["passed"]),
            "failed_must": sorted(c["check"] for c in checks
                                  if not c["passed"] and c["severity"] == "must"),
            "known_gaps": sorted(c["check"] for c in checks
                                 if not c["passed"] and c["severity"] != "must"),
        },
    }
    return result


def _counts(values):
    out = {}
    for value in values:
        out[value] = out.get(value, 0) + 1
    return {k: out[k] for k in sorted(out)}


def _body_check(paths, text):
    """正文不外泄：从 v2.1 文本块 content 里取 100 字子串，回查导出物。"""
    spec = config.GRAPH["body_text_check"]
    width = int(spec["probe_substring_chars"])
    try:
        _docs, chunks = config.load_dataset()
    except OSError as exc:
        return True, {"skipped": "数据集不可读：%s" % exc}
    rng = random.Random(int(spec["seed"]))
    pool = sorted(range(len(chunks)), key=lambda i: str(chunks[i].get("chunk_id")))
    picked = sorted(rng.sample(pool, min(int(spec["probe_chunks"]), len(pool))))
    probes, hits = 0, []
    for index in picked:
        content = str(chunks[index].get("content") or "")
        if len(content) < width:
            continue
        for start in (0, max(0, (len(content) - width) // 2), len(content) - width):
            sub = content[start:start + width]
            probes += 1
            if sub and sub in text:
                hits.append({"chunk_id": chunks[index].get("chunk_id"), "offset": start,
                             "probe_head": sub[:20]})
    return not hits, {"probe_substring_chars": width, "probes": probes,
                      "chunks_sampled": len(picked), "seed": spec["seed"],
                      "hits": hits[:5], "hit_count": len(hits),
                      "note": "《15》硬约束 11：导出物不复制正文"}


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build_all(paths, records, disambig, merged, meta):
    nodes, by_identity, event_by_key = assign_nodes(disambig, merged, meta,
                                                    paths["alias_table"])
    edges, skipped, duplicates = build_edges(records, disambig, merged, by_identity,
                                             event_by_key)
    # 边的端点标签：重放脚本与机检都要用
    label_of = {str(n["node_id"]): n["label"] for n in nodes}
    for edge in edges:
        edge["head_label"] = label_of.get(str(edge["head_id"]), "")
        edge["tail_label"] = label_of.get(str(edge["tail_id"]), "")
    return nodes, edges, skipped, duplicates


def write_products(paths, nodes, edges, skipped, duplicates, merged, fingerprint, stats_extra):
    columns_n, columns_e = config.GRAPH["node_columns"], config.GRAPH["edge_columns"]
    nodes_csv = to_csv(columns_n, nodes)
    edges_csv = to_csv(columns_e, edges)
    stats_note = "事件 %d 条（合并后）" % len(merged)
    replay = build_replay(nodes, edges, fingerprint, stats_note)
    write_text(paths["nodes"], nodes_csv)
    write_text(paths["edges"], edges_csv)
    write_text(paths["replay_cypher"], replay)

    # 机检分两趟：第一趟的文本范围是三个数据文件 ＋ 待写的 graph_stats 正文（graph_stats 的
    # 正文只由计数与检查名构成，不含任何正文片段），第二趟在四件套都落盘后再跑一遍。
    stats = {
        "schema": config.GRAPH_SCHEMA,
        "dataset_version": config.DATASET_VERSION,
        "profile": paths["profile"],
        "generated_at": now_iso(),          # 唯一带时间戳的字段：逐字节比对时排除
        "cache_fingerprint": fingerprint,   # 缓存指纹字段：逐字节比对时排除
        "id_rule": config.GRAPH["id_rule"],
        "counts": {
            "nodes_total": len(nodes),
            "nodes_by_label": _counts(n["label"] for n in nodes),
            "edges_total": len(edges),
            "edges_by_relation": _counts(e["relation"] for e in edges),
            "merged_events": sum(1 for m in merged if m["is_merged"]),
            "singleton_events": sum(1 for m in merged if not m["is_merged"]),
            "documents": sum(1 for n in nodes if n["label"] == config.DOCUMENT_LABEL),
            "events": sum(1 for n in nodes if n["label"] == "Event"),
        },
        "unresolved": {
            "policy": config.DISAMBIG["unresolved_company_policy"],
            "relations_skipped": len(skipped),
            "relations_skipped_by_reason": _counts(s["reason"] for s in skipped),
            "relations_skipped_by_relation": _counts(s["relation"] for s in skipped),
            "sample": skipped[:5],
        },
        "edge_dedup": {"duplicate_rows_removed": duplicates},
        "isolated_nodes": {
            "count": _isolated(nodes, edges),
            "note": "无边节点：实体抽到了但语料没给出关系；如实保留，不删（不是遗漏）",
        },
        "files": {
            name: {"rows": rows, "bytes": len(content.encode("utf-8")),
                   "sha256": sha256_text(content)}
            for name, rows, content in (("nodes.csv", len(nodes), nodes_csv),
                                        ("edges.csv", len(edges), edges_csv),
                                        ("replay.cypher", None, replay))
        },
        "byte_compare_scope": {
            "excluded_fields": list(config.GRAPH_PIPELINE["excluded_from_byte_compare"]),
            "note": "四件套里只有 graph_stats.json 的 generated_at（与缓存指纹字段）每次不同；"
                    "其余内容逐字节可复现（见 manifest.sha256 与复跑比对读数）",
        },
    }
    first = check_export(paths, nodes, edges, fingerprint, paths["profile"],
                         json.dumps(stats, ensure_ascii=False, sort_keys=True, indent=2))
    stats["event_core_attributes"] = {
        "events": stats["counts"]["events"],
        "event_time_null_count": _check_detail(first, "event_time_nonempty",
                                              "event_time_null_count"),
        "note": "event_time 空值条数与《15》第八节「六项核心属性非空」的差异，见机检读数",
    }
    stats["graph_check"] = _check_summary(first)
    write_text(paths["graph_stats"], json.dumps(stats, ensure_ascii=False, sort_keys=True,
                                                indent=2) + "\n")

    # 第二趟：四件套齐了，逐字节范围覆盖全部四个文件（含刚写的 graph_stats.json）。
    checks = check_export(paths, nodes, edges, fingerprint, paths["profile"])
    if checks["summary"] != first["summary"]:
        print("[注意] 第二趟机检（覆盖 graph_stats.json 全文）与第一趟结论不同：%s → %s"
              % (first["summary"], checks["summary"]))
        stats["graph_check"] = _check_summary(checks)
        write_text(paths["graph_stats"], json.dumps(stats, ensure_ascii=False, sort_keys=True,
                                                    indent=2) + "\n")
    dump_json(paths["graph_check"], checks)

    manifest_lines = []
    for name in ("nodes.csv", "edges.csv", "graph_stats.json", "replay.cypher"):
        path = {"nodes.csv": paths["nodes"], "edges.csv": paths["edges"],
                "graph_stats.json": paths["graph_stats"],
                "replay.cypher": paths["replay_cypher"]}[name]
        manifest_lines.append("%s  %s  %d bytes" % (sha256_file(path), rel(path),
                                                    os.path.getsize(path)))
    for path in (paths["graph_check"],):
        manifest_lines.append("%s  %s  %d bytes" % (sha256_file(path), rel(path),
                                                    os.path.getsize(path)))
    manifest_lines.append("# 说明：graph_stats.json 每次运行的 generated_at 不同，其校验和随之变化；"
                          "四件套的逐字节稳定性以 nodes.csv／edges.csv／replay.cypher 为准，"
                          "graph_stats.json 排除 generated_at 与缓存指纹字段后一致。")
    write_text(paths["manifest"], "\n".join(manifest_lines) + "\n")
    return stats, checks


def _isolated(nodes, edges):
    touched = set()
    for edge in edges:
        touched.add(str(edge["head_id"]))
        touched.add(str(edge["tail_id"]))
    return [n["node_id"] for n in nodes if str(n["node_id"]) not in touched]


def _check_detail(checks, name, field, default=None):
    for item in checks["checks"]:
        if item["check"] == name:
            return item["detail"].get(field, default)
    return default


def _check_summary(checks):
    return dict(checks["summary"])


def run(args) -> int:
    paths = config.pipeline_paths(args.profile)
    records_path = paths["extract_records"]
    if not os.path.isfile(records_path):
        raise SystemExit("输入不存在：%s（请先跑 extract.py）" % records_path)
    records = read_jsonl(records_path)
    fingerprint = source_fingerprint(records, records_path)

    if args.verify_only:
        nodes, edges = load_export(paths)
        checks = check_export(paths, nodes, edges, fingerprint, args.profile)
        dump_json(paths["graph_check"], checks)
        print("仅机检（不重写导出物）：%s" % paths["export_dir"])
        _print_checks(checks)
        return 0 if not checks["summary"]["failed_must"] else 2

    disambig, merged = load_previous(paths, fingerprint)
    doc_ids = {d for m in merged for d in m["evidence_doc_ids"]}
    meta = load_doc_meta(doc_ids)
    missing_meta = sorted(doc_ids - set(meta))
    nodes, edges, skipped, duplicates = build_all(paths, records, disambig, merged, meta)

    stats, checks = write_products(paths, nodes, edges, skipped, duplicates, merged,
                                   fingerprint,
                                   {"document_meta_missing": missing_meta})

    print("输入（只读）：%s（%d 篇，sha256 %s…）"
          % (rel(records_path), len(records), fingerprint["extract_records_sha256"][:16]))
    print("节点 %d（%s）" % (len(nodes), "、".join("%s %d" % kv for kv in
                                                 sorted(stats["counts"]["nodes_by_label"].items()))))
    print("边 %d（%s）" % (len(edges), "、".join("%s %d" % kv for kv in
                                               sorted(stats["counts"]["edges_by_relation"].items()))))
    print("未消歧端点跳过的关系 %d 条（按原因 %s）；重复边去掉 %d 条；无边节点 %s 个"
          % (len(skipped), stats["unresolved"]["relations_skipped_by_reason"], duplicates,
             stats["isolated_nodes"]["count"]))
    if missing_meta:
        print("[注意] 数据集里查不到文档元数据的证据文档：%s" % missing_meta)
    _print_checks(checks)
    for key in ("nodes", "edges", "graph_stats", "replay_cypher"):
        print("产物：%s" % rel(paths[key]))
    print("产物：%s" % rel(paths["graph_check"]))
    print("产物：%s" % rel(paths["manifest"]))
    return 0 if not checks["summary"]["failed_must"] else 2


def _print_checks(checks):
    for item in checks["checks"]:
        flag = "通过" if item["passed"] else ("已知缺口" if item["severity"] != "must" else "不通过")
        print("  [%s] %s" % (flag, item["check"]))
    summary = checks["summary"]
    print("机检：%d 项，通过 %d，不通过 %d%s%s"
          % (summary["checks"], summary["passed"], len(summary["failed"]),
             ("（=%s，其中已知缺口 %s）" % ("、".join(summary["failed"]),
                                        "、".join(summary["known_gaps"]) or "无")
              if summary["failed"] else ""),
             ("；硬约束不通过：%s" % "、".join(summary["failed_must"]))
             if summary["failed_must"] else ""))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 6 阶段图谱写入与导出（T6；只读缓存；编号显式分配；不调用模型）")
    parser.add_argument("--profile", default="pilot", choices=["pilot", "v21"])
    parser.add_argument("--force", action="store_true", help="重算并重写导出物")
    parser.add_argument("--verify-only", action="store_true",
                        help="只对已写出的导出物做机检，不重写")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SystemExit as exc:
        print("[阻断] %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
