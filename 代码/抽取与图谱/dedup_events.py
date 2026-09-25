# -*- coding: utf-8 -*-
r"""dedup_events.py —— 第 6 阶段「事件去重」（T5）。

规则来源（**只引用、不新增**）：《10-系统总体设计（第四阶段）》第4.5.4节
（＝《02》第9.2节）：

> 本课题的事件去重规则是：按 **event_type ＋ 参与主体 ＋ 时间窗口 ＋ 触发词相似度**
> 判定同一事件的多来源描述，**四项条件同时满足**时判定为同一事件并合并；合并后保留
> 全部证据文档，通过 EVIDENCED_BY 关系全部挂在合并后的事件节点上，发布时间最早的
> 一份作为主要来源展示，其余来源作为补充证据保留；合并动作记录在抽取日志中。

本脚本据此把四项条件逐条落成可复核的判据（阈值与口径全在 `config.DEDUP`）：

| 条件 | 判据 | 口径 |
| --- | --- | --- |
| 1 event_type | 两侧事件类型相等 | 本体 8 种之一 |
| 2 参与主体 | 两侧参与主体**集合相等** | 参与主体＝`PARTICIPATES_IN` 起点 ∪ `ISSUED_BY` 终点（《10》第4.5.2节：事件参与主体统一由这两条关系表达）；任一端点未消歧 → 本条件不成立 |
| 3 时间窗口 | 两侧 `event_time` 都有值且相差 ≤ `time_window_days` | T3 的固定口径是「不能确定到日时写 null，绝不猜测」，故**不用发布时间顶替**；缺失即不成立 |
| 4 触发词相似度 | `event_name` 的字符二元组 Jaccard ≥ `similarity_min` | T3 未产出 trigger（README 第 5 节：trigger 只作调试字段），故取 event_name；确定性、无随机 |

**依赖 T4**：参与主体的身份键来自 `disambiguate.py` 的产物，且它的缓存指纹必须与本脚本
读到的抽取结果一致——**不在未消歧的实体上做去重**（《15》第九节：T4 与 T5 不能并行）。

**合并后**（《10》第4.5.4节）：证据文档取全部成员的**并集**（这是「保留全部证据文档」
的落点）；代表成员取发布时间最早的证据文档所在成员；`event_time` 取成员中最早的非空日期；
`confidence` 取成员最大值（四舍五入到 3 位）。合并动作逐条写进 `merge_log.jsonl`。

用法（参数一律取自 `代码\抽取与图谱\config.py`）：

    python 代码\抽取与图谱\dedup_events.py                  # 默认 --profile pilot
    python 代码\抽取与图谱\dedup_events.py --profile v21
    python 代码\抽取与图谱\dedup_events.py --force          # 忽略已有产物，重算并重写
    python 代码\抽取与图谱\dedup_events.py --self-test-only # 只跑「保留全部证据文档」自检

退出码：`0` 成功（含跳过）；`1` 前置缺失（未跑 T4）或指纹不一致；`2` 数据异常。不调用模型。
"""

from __future__ import annotations

import argparse
import copy
import datetime as _dt
import hashlib
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
# 基础工具
# --------------------------------------------------------------------------
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


def source_fingerprint(records, path):
    """与 T4 完全同构的输入指纹（T5 用它核对「去重依赖的消歧结论是不是同一份缓存」）。"""
    return {
        "extract_records": os.path.relpath(path, config.ROOT).replace("\\", "/"),
        "extract_records_sha256": sha256_file(path),
        "documents": len(records),
        "doc_ids": sorted(int(r["doc_id"]) for r in records),
        "record_schemas": sorted({str(r.get("record_schema") or "") for r in records}),
        "prompt_versions": sorted({str(r.get("prompt_version") or "") for r in records}),
        "models_resolved": sorted({str(r.get("model_resolved") or "") for r in records}),
    }


def char_bigrams(text):
    text = str(text or "")
    return {text[i:i + 2] for i in range(len(text) - 1)} if len(text) > 1 else set()


def bigram_jaccard(a, b):
    """字符二元组 Jaccard 相似度（确定性；两侧都没有二元组时返回 0.0）。"""
    sa, sb = char_bigrams(a), char_bigrams(b)
    if not sa or not sb:
        return 0.0
    return round(len(sa & sb) / float(len(sa | sb)), int(config.DEDUP["similarity_round"]))


def parse_date(value):
    if not value:
        return None
    try:
        return _dt.date.fromisoformat(str(value))
    except ValueError:
        return None


# --------------------------------------------------------------------------
# 读取 T4 的结论（T5 的前置）
# --------------------------------------------------------------------------
def load_disambiguation(paths, fingerprint):
    path = paths["disambiguation"]
    if not os.path.isfile(path):
        raise SystemExit("未找到 T4 的消歧产物：%s\n请先跑：python 代码\\抽取与图谱\\disambiguate.py "
                         "--profile %s（去重依赖消歧后的实体身份，不得在未消歧的实体上去重）。"
                         % (path, paths["profile"]))
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if payload.get("cache_fingerprint") != fingerprint:
        raise SystemExit("消歧产物与当前抽取结果不是同一份缓存（指纹不一致）：%s\n"
                         "请先重跑 disambiguate.py（必要时加 --force）。" % path)
    return payload


# --------------------------------------------------------------------------
# 事件视图
# --------------------------------------------------------------------------
def build_events(records, entity_map):
    """把缓存里的事件与其关系摊平成去重用的视图（全部按确定性顺序）。"""
    events, skipped_relations = [], []
    for record in sorted(records, key=lambda r: int(r["doc_id"])):
        doc_id = int(record["doc_id"])
        local_events = sorted(record.get("events") or [], key=lambda e: str(e["event_id"]))
        by_event = {}
        for event in local_events:
            local_id = str(event["event_id"])
            by_event[local_id] = {
                "doc_id": doc_id,
                "local_event_id": local_id,
                "event_type": str(event["event_type"]),
                "event_name": str(event["event_name"]),
                "event_time": event.get("event_time"),
                "description": str(event.get("description") or ""),
                "confidence": config.round_confidence(event.get("confidence")),
                "publish_time": str(record.get("publish_time") or ""),
                "evidence_doc_ids": [doc_id],
                "participants": [],     # PARTICIPATES_IN（含 role）
                "issued_by": [],        # ISSUED_BY
                "related_to": [],       # RELATED_TO
                "unresolved_peers": [],  # 端点未消歧的关系：只记账，不进图（《10》第4.5.4节）
            }
        for relation in sorted(record.get("relations") or [],
                               key=lambda r: str(r["relation_id"])):
            kind = str(relation["relation"])
            tail_id, head_id = str(relation["tail_id"]), str(relation["head_id"])
            target = None
            if kind == "PARTICIPATES_IN" and tail_id in by_event:
                target = by_event[tail_id]
            elif kind in ("ISSUED_BY", "RELATED_TO") and head_id in by_event:
                target = by_event[head_id]
            if target is None:
                continue
            peer_local = head_id if kind == "PARTICIPATES_IN" else tail_id
            peer = entity_map.get(peer_local)
            if peer is None:
                skipped_relations.append({"doc_id": doc_id, "relation_id": relation["relation_id"],
                                          "relation": kind, "reason": "peer_not_in_entity_map",
                                          "peer_id": peer_local})
                continue
            if not peer.get("identity_key"):
                # 端点未消歧：不写进图（《10》第4.5.4节：人工确认后再写入图谱），
                # 但按原样记账，并让「参与主体」条件因此不成立。
                target["unresolved_peers"].append({
                    "relation": kind, "peer_entity_id": peer_local, "peer_name": peer["name"],
                    "label": peer["label"], "role": relation.get("role"),
                    "source_doc_id": int(relation["source_doc_id"]),
                    "source_chunk_id": int(relation["source_chunk_id"]),
                })
                continue
            row = {
                "identity_key": peer["identity_key"],
                "label": peer["label"],
                "name": peer["name"],
                "source_doc_id": int(relation["source_doc_id"]),
                "source_chunk_id": int(relation["source_chunk_id"]),
                "confidence": config.round_confidence(relation.get("confidence")),
            }
            if kind == "PARTICIPATES_IN":
                row["role"] = relation.get("role")
                target["participants"].append(row)
            elif kind == "ISSUED_BY":
                target["issued_by"].append(row)
            else:
                target["related_to"].append(row)
        for local_id in sorted(by_event):
            event = by_event[local_id]
            for key in ("participants", "issued_by", "related_to"):
                event[key].sort(key=lambda r: (str(r["identity_key"]), r["source_doc_id"],
                                               r["source_chunk_id"], r.get("role") or ""))
            event["unresolved_peers"].sort(key=lambda r: (r["relation"], r["peer_entity_id"]))
            keys = {r["identity_key"] for r in event["participants"] + event["issued_by"]}
            event["participant_keys"] = sorted(keys)
            event["participant_keys_unresolved"] = sorted({
                "未消歧:%s" % r["peer_name"] for r in event["unresolved_peers"]
                if r["relation"] in config.DEDUP["participants_relations"]})
            events.append(event)
    events.sort(key=lambda e: (e["doc_id"], e["local_event_id"]))
    return events, skipped_relations


def evaluate_pair(a, b, publish_time_by_doc):
    """四项条件逐条求值，返回 (是否合并, conditions, detail)。"""
    conditions, detail = {}, {}

    conditions["event_type"] = a["event_type"] == b["event_type"]
    detail["event_type"] = {"a": a["event_type"], "b": b["event_type"]}

    unresolved = set(a["participant_keys_unresolved"]) | set(b["participant_keys_unresolved"])
    same_participants = a["participant_keys"] == b["participant_keys"]
    conditions["participants"] = bool(same_participants) and not unresolved
    detail["participants"] = {
        "a": a["participant_keys"], "b": b["participant_keys"],
        "equal": bool(same_participants),
        "unresolved": sorted(unresolved),
        "note": "参与主体＝PARTICIPATES_IN 起点 ∪ ISSUED_BY 终点；集合相等且端点全部已消歧才成立",
    }

    date_a, date_b = parse_date(a["event_time"]), parse_date(b["event_time"])
    window = int(config.DEDUP["time_window_days"])
    if date_a is None or date_b is None:
        conditions["time_window"] = False
        days = None
        why = "event_time_missing_no_fallback"
    else:
        days = abs((date_a - date_b).days)
        conditions["time_window"] = days <= window
        why = "within_window" if conditions["time_window"] else "outside_window"
    detail["time_window"] = {
        "a": a["event_time"], "b": b["event_time"], "days_apart": days,
        "window_days": window, "verdict": why,
        "note": "缺日期即不成立：不用发布时间顶替（T3 的固定口径是绝不猜测）",
    }

    similarity = bigram_jaccard(a["event_name"], b["event_name"])
    conditions["trigger_similarity"] = similarity >= float(config.DEDUP["similarity_min"])
    detail["trigger_similarity"] = {
        "field": config.DEDUP["similarity_field"],
        "metric": config.DEDUP["similarity_metric"],
        "a": a["event_name"], "b": b["event_name"],
        "similarity": similarity, "min": float(config.DEDUP["similarity_min"]),
        "note": "T3 未产出 trigger（只作调试字段），故取 event_name 的字符二元组 Jaccard",
    }

    merged = all(conditions[c] for c in config.DEDUP["conditions"])
    detail["publish_time"] = {"a": publish_time_by_doc.get(a["doc_id"], ""),
                              "b": publish_time_by_doc.get(b["doc_id"], "")}
    return merged, conditions, detail


def _find(parent, key):
    while parent[key] != key:
        parent[key] = parent[parent[key]]
        key = parent[key]
    return key


def _union(parent, rank, a, b):
    ra, rb = _find(parent, a), _find(parent, b)
    if ra == rb:
        return
    if rank[ra] < rank[rb]:
        ra, rb = rb, ra
    parent[rb] = ra
    if rank[ra] == rank[rb]:
        rank[ra] += 1


def merge_groups(events, merged_pairs):
    parent = {_event_key(e): _event_key(e) for e in events}
    rank = {k: 0 for k in parent}
    for a, b in merged_pairs:
        _union(parent, rank, _event_key(a), _event_key(b))
    groups = {}
    for event in events:
        groups.setdefault(_find(parent, _event_key(event)), []).append(event)
    return [sorted(members, key=_event_key) for _, members in sorted(groups.items())]


def _event_key(event):
    return (event["doc_id"], event["local_event_id"])


def build_merged_event(members, index, publish_time_by_doc):
    """把一组同事件合并成一条合并事件（证据文档取并集，代表取发布时间最早的一份）。"""
    members_sorted = sorted(
        members,
        key=lambda e: (publish_time_by_doc.get(e["doc_id"], ""), e["doc_id"],
                       e["local_event_id"]))
    representative = members_sorted[0]
    times = [parse_date(e["event_time"]) for e in members_sorted]
    times = [t for t in times if t is not None]
    event_time = min(times).isoformat() if times else None
    confidences = [e["confidence"] for e in members_sorted if e["confidence"] is not None]
    evidence_docs = sorted({doc for e in members_sorted for doc in e["evidence_doc_ids"]})

    def collect(field, extra_keys):
        rows, seen = [], set()
        for event in members_sorted:
            for row in event[field]:
                key = (row["identity_key"], row["source_doc_id"], row["source_chunk_id"],
                       tuple(str(row.get(k) or "") for k in extra_keys))
                if key in seen:
                    continue
                seen.add(key)
                rows.append(row)
        rows.sort(key=lambda r: (str(r["identity_key"]), r["source_doc_id"],
                                 r["source_chunk_id"],
                                 tuple(str(r.get(k) or "") for k in extra_keys)))
        return rows

    return {
        "merged_event_key": "MEVT-%0*d" % (int(config.GRAPH["id_width"]), index),
        "is_merged": len(members_sorted) > 1,
        "member_count": len(members_sorted),
        "members": [{"doc_id": e["doc_id"], "local_event_id": e["local_event_id"],
                     "event_time": e["event_time"], "confidence": e["confidence"]}
                    for e in members_sorted],
        "event_type": representative["event_type"],
        "event_name": representative["event_name"],
        "event_time": event_time,
        "description": representative["description"],
        "confidence": max(confidences) if confidences else None,
        "representative_doc_id": representative["doc_id"],
        "evidence_doc_ids": evidence_docs,
        "participants": collect("participants", ("role",)),
        "issued_by": collect("issued_by", ()),
        "related_to": collect("related_to", ()),
        "rule": {
            "representative": config.DEDUP["representative_rule"],
            "event_time": config.DEDUP["event_time_rule"],
            "confidence": config.DEDUP["confidence_rule"],
            "evidence": config.DEDUP["evidence_rule"],
        },
    }


# --------------------------------------------------------------------------
# 自检：合并后必须保留**全部**证据文档（用真实缓存复制成第二篇，不编造内容）
# --------------------------------------------------------------------------
def self_test(records, entity_map, paths):
    """把真实缓存里事件最多的一篇复制成一篇合成文档，验证合并组的证据文档并集。"""
    spec = config.DEDUP["self_test"]
    if not spec.get("enabled"):
        return {"enabled": False}
    by_doc = {}
    for record in records:
        by_doc[int(record["doc_id"])] = record
    source_doc = min(by_doc, key=lambda d: (-len(by_doc[d].get("events") or []), d))
    if not (by_doc[source_doc].get("events") or []):
        return {"enabled": True, "passed": False, "reason": "缓存里没有事件，无法自检"}

    offset = int(spec["doc_id_offset"])
    synthetic = copy.deepcopy(by_doc[source_doc])
    synthetic_doc_id = int(source_doc) + offset
    synthetic["doc_id"] = synthetic_doc_id
    id_map, synthetic_map = {}, {}
    for entity in synthetic.get("entities") or []:
        old = str(entity["entity_id"])
        new = "ENT-%d-%s" % (synthetic_doc_id, old.rsplit("-", 1)[-1])
        id_map[old] = new
        original = entity_map.get(old)          # 同一个实体、同一个身份键，只是换了一篇文档
        if original is not None:
            synthetic_map[new] = dict(original, entity_id=new, doc_id=synthetic_doc_id)
        entity["entity_id"] = new
        entity["source_doc_id"] = synthetic_doc_id
    for event in synthetic.get("events") or []:
        old = str(event["event_id"])
        new = "EVT-%d-%s" % (synthetic_doc_id, old.rsplit("-", 1)[-1])
        id_map[old] = new
        event["event_id"] = new
        event["source_doc_id"] = synthetic_doc_id
    for relation in (synthetic.get("relations") or []) + (synthetic.get("evidenced_by") or []):
        for field in ("head_id", "tail_id"):
            if str(relation.get(field)) in id_map:
                relation[field] = id_map[str(relation[field])]
        relation["source_doc_id"] = synthetic_doc_id

    records2 = [r for r in records] + [synthetic]
    entity_map2 = dict(entity_map)
    entity_map2.update(synthetic_map)

    events, _ = build_events(records2, entity_map2)
    publish_time_by_doc = {int(r["doc_id"]): str(r.get("publish_time") or "") for r in records2}
    pairs = []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if events[i]["event_type"] != events[j]["event_type"]:
                continue
            merged, _, _ = evaluate_pair(events[i], events[j], publish_time_by_doc)
            if merged:
                pairs.append((events[i], events[j]))
    groups = merge_groups(events, pairs)
    multi = [g for g in groups if len(g) > 1]
    result = {
        "schema": config.DEDUP_SCHEMA,
        "enabled": True,
        "note": "自检夹具：把真实缓存里事件最多的一篇（doc_id=%d）原样复制成一篇合成文档"
                "（doc_id=%d），不改一个字；只用于验证「合并后保留全部证据文档」，"
                "不进导出物、不进合并日志。" % (source_doc, synthetic_doc_id),
        "source_doc_id": source_doc,
        "synthetic_doc_id": synthetic_doc_id,
        "merged_group_count": len(multi),
        "passed": False,
        "group": None,
    }
    if not multi:
        result["reason"] = "合成文档与源文档没有合并成组（见九项条件的逐条判据）"
        return result
    # 选中**同时含合成文档与源文档**的那一组，而不是 multi[0]：
    # 12 篇试跑里真实语料没有任何合并组，multi[0] 恰好就是夹具组；2026-09-26 全量放量
    # （709 篇、19 组真实合并）暴露了这一取法的失真——multi[0] 会取到与夹具无关的真实组
    # （实测取到 doc 1001 的同篇合并组，证据文档只有 1001，故 len(evidence) > 1 不成立）。
    # 夹具组的选取必须显式锚定 synthetic_doc_id；锚不到即判自检不通过，不退回 multi[0]。
    members = next((g for g in multi
                    if any(e["doc_id"] == synthetic_doc_id for e in g)
                    and any(e["doc_id"] == int(source_doc) for e in g)), None)
    if members is None:
        result["reason"] = ("合成文档（doc_id=%d）与源文档（doc_id=%d）没有并进同一组，"
                            "夹具校验不成立" % (synthetic_doc_id, int(source_doc)))
        return result
    merged = build_merged_event(members, 1, publish_time_by_doc)
    evidence = set(merged["evidence_doc_ids"])
    expected = {e["doc_id"] for e in members}
    result["group"] = {
        "member_keys": [{"doc_id": e["doc_id"], "local_event_id": e["local_event_id"]}
                        for e in members],
        "member_evidence_docs": [e["evidence_doc_ids"] for e in members],
        "merged_evidence_doc_ids": merged["evidence_doc_ids"],
        "expected_union": sorted(expected),
        "all_members_retained": evidence == expected,
    }
    result["passed"] = bool(evidence == expected and len(evidence) > 1)
    return result


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def run(args) -> int:
    paths = config.pipeline_paths(args.profile)
    records_path = paths["extract_records"]
    if not os.path.isfile(records_path):
        raise SystemExit("输入不存在：%s（请先跑 extract.py）" % records_path)
    records = read_jsonl(records_path)
    fingerprint = source_fingerprint(records, records_path)
    disambig = load_disambiguation(paths, fingerprint)
    entity_map = disambig["entity_map"]

    if args.self_test_only:
        result = self_test(records, entity_map, paths)
        dump_json(paths["dedup_self_test"], result)
        print("自检结果：passed=%s（%s）" % (result.get("passed"), result.get("note", "")))
        return 0 if result.get("passed") else 2

    if os.path.isfile(paths["merge_log"]) and os.path.isfile(paths["events_merged"]) \
            and not args.force:
        with open(paths["events_merged"], encoding="utf-8") as fh:
            first = fh.readline()
        if first:
            previous = json.loads(first)
            if previous.get("cache_fingerprint") == fingerprint:
                print("[跳过] 去重产物已是最新（缓存指纹一致）：%s" % paths["merge_log"])
                print("       删掉产物或用 --force 可重算。")
                return 0

    publish_time_by_doc = {int(r["doc_id"]): str(r.get("publish_time") or "") for r in records}
    events, skipped_relations = build_events(records, entity_map)
    if not events:
        print("输入里没有事件：%s" % records_path)
        return 1

    log_rows, merged_pairs = [], []
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            a, b = events[i], events[j]
            # 条件 1 不成立就不必逐条求值——四条件必须同时满足，其中一条已不成立。
            if a["event_type"] != b["event_type"]:
                continue
            merged, conditions, detail = evaluate_pair(a, b, publish_time_by_doc)
            if merged:
                merged_pairs.append((a, b))
            log_rows.append({
                "doc_id_a": a["doc_id"], "event_id_a": a["local_event_id"],
                "doc_id_b": b["doc_id"], "event_id_b": b["local_event_id"],
                "event_type": a["event_type"],
                "conditions": {c: conditions[c] for c in config.DEDUP["conditions"]},
                "detail": detail,
                "decision": "merged" if merged else "not_merged",
                "first_failed_condition": next(
                    (c for c in config.DEDUP["conditions"] if not conditions[c]), None),
            })
    log_rows.sort(key=lambda r: (r["doc_id_a"], r["event_id_a"], r["doc_id_b"], r["event_id_b"]))

    groups = merge_groups(events, merged_pairs)
    groups.sort(key=lambda g: (g[0]["doc_id"], g[0]["local_event_id"]))
    merged_events = [build_merged_event(g, index + 1, publish_time_by_doc)
                     for index, g in enumerate(groups)]
    for row in merged_events:
        row["cache_fingerprint"] = fingerprint

    merged_groups = [m for m in merged_events if m["is_merged"]]
    summary = {
        "schema": config.DEDUP_SCHEMA,
        "dataset_version": config.DATASET_VERSION,
        "profile": args.profile,
        "cache_fingerprint": fingerprint,
        "rule": {
            "conditions": config.DEDUP["conditions"],
            "participants": config.DEDUP["participants_rule"],
            "time_window_days": config.DEDUP["time_window_days"],
            "time_window_requires_both_dates": config.DEDUP["time_window_requires_both_dates"],
            "similarity": {"field": config.DEDUP["similarity_field"],
                           "metric": config.DEDUP["similarity_metric"],
                           "min": config.DEDUP["similarity_min"],
                           "note": "trigger 未由 T3 产出（只作调试字段），故取 event_name"},
            "linkage": config.DEDUP["linkage"],
            "evidence": config.DEDUP["evidence_rule"],
        },
        "counts": {
            "events_before": len(events),
            "events_after": len(merged_events),
            "candidate_pairs": len(log_rows),
            "merged_pairs": len(merged_pairs),
            "merged_groups": len(merged_groups),
            "events_merged_away": len(events) - len(merged_events),
            "max_group_size": max((m["member_count"] for m in merged_events), default=0),
            "max_evidence_docs_in_group": max(
                (len(m["evidence_doc_ids"]) for m in merged_events), default=0),
            "events_without_participants": sum(1 for m in merged_events
                                               if not m["participants"]),
            "events_without_event_time": sum(1 for m in merged_events
                                            if not m["event_time"]),
            "relations_skipped": len(skipped_relations),
        },
        "first_failed_condition_histogram": _histogram(log_rows),
        "merged_groups_detail": [{
            "merged_event_key": m["merged_event_key"],
            "event_type": m["event_type"],
            "event_name": m["event_name"],
            "member_count": m["member_count"],
            "evidence_doc_ids": m["evidence_doc_ids"],
        } for m in merged_groups],
    }

    dump_jsonl(paths["merge_log"], log_rows)
    dump_jsonl(paths["events_merged"], merged_events)
    dump_json(paths["merge_summary"], summary)
    result = self_test(records, entity_map, paths)
    dump_json(paths["dedup_self_test"], result)

    print("输入：%s（%d 篇，指纹 %s…）；消歧产物指纹一致 ✓"
          % (records_path, len(records), fingerprint["extract_records_sha256"][:16]))
    print("事件 %d 条；类型相同因而进入逐条判据的候选对 %d 对；四条件同时满足 %d 对；"
          "合并成组 %d 组，事件数 %d → %d"
          % (len(events), len(log_rows), len(merged_pairs), len(merged_groups),
             len(events), len(merged_events)))
    print("逐条判据的首个不成立条件分布：%s" % summary["first_failed_condition_histogram"])
    if merged_groups:
        for m in merged_groups:
            print("  [合并] %s 成员 %d：证据文档 %s"
                  % (m["merged_event_key"], m["member_count"], m["evidence_doc_ids"]))
    else:
        print("  [说明] 本批数据没有任何一对事件四条件同时满足——不硬凑合并；"
              "逐条判据见 merge_log.jsonl。")
    print("自检（合并后保留全部证据文档）：passed=%s；成员证据 %s → 合并后 %s"
          % (result.get("passed"),
             result.get("group", {}).get("member_evidence_docs") if result.get("group") else "-",
             result.get("group", {}).get("merged_evidence_doc_ids") if result.get("group") else "-"))
    print("产物：%s（%d 条判据）" % (paths["merge_log"], len(log_rows)))
    print("      %s（%d 条合并后事件）" % (paths["events_merged"], len(merged_events)))
    print("      %s" % paths["merge_summary"])
    print("      %s" % paths["dedup_self_test"])
    return 0


def _histogram(log_rows):
    counts = {}
    for row in log_rows:
        key = row["first_failed_condition"] or "all_satisfied"
        counts[key] = counts.get(key, 0) + 1
    return {k: counts[k] for k in sorted(counts)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 6 阶段事件去重（T5；四条件同时满足才合并；不调用模型）")
    parser.add_argument("--profile", default="pilot", choices=["pilot", "v21"])
    parser.add_argument("--force", action="store_true", help="忽略已有产物，重算并重写")
    parser.add_argument("--self-test-only", action="store_true",
                        help="只跑「合并后保留全部证据文档」的自检，不重写去重产物")
    args = parser.parse_args(argv)
    try:
        return run(args)
    except SystemExit as exc:
        print("[阻断] %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
