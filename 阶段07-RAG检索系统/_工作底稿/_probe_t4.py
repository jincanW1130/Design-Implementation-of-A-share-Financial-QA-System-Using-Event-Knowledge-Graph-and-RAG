# -*- coding: utf-8 -*-
"""T4～T7 开工前的只读勘察：问题→实体匹配、图谱侧候选规模、时间窗口可用性。

只读输入；不写任何产出（本文件的落点在第 7 阶段自己的 _工作底稿\）。
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "代码", "检索"))

import config                                                    # noqa: E402
from graph_query import GraphQuery                               # noqa: E402


def norm(text) -> str:
    return "".join(str(text).split()).lower()


def match_entities(gq, question):
    nq = norm(question)
    taken = [False] * len(nq)
    hits = []
    for key in sorted(gq.by_name.keys(), key=lambda k: (-len(k), k)):
        if len(key) < 2:
            continue
        start = 0
        while True:
            i = nq.find(key, start)
            if i < 0:
                break
            if not any(taken[i:i + len(key)]):
                for j in range(i, i + len(key)):
                    taken[j] = True
                hits.append((key, i, list(gq.by_name[key])))
            start = i + 1
    for m in re.finditer(r"(?<!\d)\d{6}(?!\d)", nq):
        if m.group(0) in gq.by_code:
            hits.append((m.group(0), m.start(), list(gq.by_code[m.group(0)])))
    return hits


def main() -> int:
    gq = GraphQuery()
    rows = [json.loads(l) for l in open(config.QUESTION_FILES["questions"], encoding="utf-8")
            if l.strip()]
    chunks = {int(r["chunk_id"]): r for r in config.iter_jsonl(config.CHUNKS_PATH)}

    stat_optA = stat_optB = 0
    for r in rows:
        hits = match_entities(gq, r["question"])
        by_label = {}
        for key, _, ids in hits:
            for nid in ids:
                by_label.setdefault(gq.nodes[nid].get("label", ""), set()).add(nid)
        seeds = sorted({nid for _, _, ids in hits for nid in ids})
        def edge_chunks(nid):
            out = set()
            for rec in gq.adj.get(nid, []):
                e = gq.edges[rec["edge_id"]]
                if e["relation"] in config.SEMANTIC_RELATIONS and e["evidence"] \
                        and e["evidence"].get("source_chunk_id"):
                    out.add(int(e["evidence"]["source_chunk_id"]))
            return out

        # 严格一跳：种子节点的入射语义边
        one_hop = set()
        for nid in seeds:
            one_hop |= edge_chunks(nid)
        # 事件侧（G4：公司参与事件；G5：事件证据）
        ev = set()
        for nid in seeds:
            if gq.nodes[nid].get("label") == "Company":
                for e in gq.g4_company_events(nid)["results"]:
                    ev.add(e["node_id"])
        ev_chunks = set()
        for eid in ev:
            ev_chunks |= {int(x) for x in gq.event_chunk_ids(eid)}
        depth1 = one_hop | ev_chunks
        # 二跳：一跳邻居的入射语义边
        nbr = {rec["neighbor"] for nid in seeds for rec in gq.adj.get(nid, [])}
        two = set()
        for nid in nbr:
            two |= edge_chunks(nid)
        depth2 = depth1 | two
        gold = set(int(x) for x in r["gold_evidence_chunk_ids"])
        types = [t for t in config.EVENT_TYPES if t in r["question"]]
        tok1 = sum(int(chunks[c]["token_count"]) for c in depth1 if c in chunks)
        tok2 = sum(int(chunks[c]["token_count"]) for c in depth2 if c in chunks)
        # 候选块 → 路径上的事件集合（严格 d2 口径、只取一对一路径即可近似）
        seed_set = set(seeds)
        dist = {nid: 0 for nid in seed_set}
        frontier = sorted(seed_set)
        for hop in (1, 2):
            nxt = []
            for nid in frontier:
                for rec in gq.adj.get(nid, []):
                    nb = rec["neighbor"]
                    if nb not in dist:
                        dist[nb] = hop
                        nxt.append(nb)
            frontier = sorted(nxt)
            if hop == 1:
                one_hop_nodes = sorted(dist)
        cand_events = {}
        for nid in sorted(dist):
            if dist[nid] > 1:
                continue
            for rec in gq.adj.get(nid, []):
                e = gq.edges[rec["edge_id"]]
                if e["relation"] not in config.SEMANTIC_RELATIONS or not e["evidence"] \
                        or not e["evidence"].get("source_chunk_id"):
                    continue
                cid = int(e["evidence"]["source_chunk_id"])
                evs = {n for n in (nid, rec["neighbor"])
                       if gq.nodes.get(n, {}).get("label") == "Event"}
                cand_events.setdefault(cid, set()).update(evs)
        for eid in [n for n in dist if gq.nodes.get(n, {}).get("label") == "Event" and dist[n] <= 1]:
            for c in gq.event_chunk_ids(eid):
                cand_events.setdefault(int(c), set()).add(eid)
        win = r.get("time_window") or {}
        lo, hi = win.get("lo"), win.get("hi")
        if not lo:
            nonempty = sorted({gq.nodes[e]["event_time"] for e in {x for s in cand_events.values() for x in s}
                               if str(gq.nodes.get(e, {}).get("event_time") or "").strip()})
            lo = nonempty[0] if nonempty else config.DATA_CUTOFF_TIME[:10]
            hi = nonempty[-1] if nonempty else config.DATA_CUTOFF_TIME[:10]
        removed_ev = {e for e in {x for s in cand_events.values() for x in s}
                      if not (str(gq.nodes[e].get("event_time") or "").strip() and lo <= gq.nodes[e]["event_time"] <= hi)}
        removedA = {c for c, evs in cand_events.items() if not (evs - removed_ev)}
        removedB = {c for c, evs in cand_events.items() if evs and not (evs - removed_ev)}
        stat_optA += 1 if removedA else 0
        stat_optB += 1 if removedB else 0
        print("%s hop=%d 实体=%s 种子=%d 类型词=%s | 严格d1=%d(gold %d/%d) 严格d2=%d(gold %d/%d) "
              "| G5扩展d1=%d块/%d tok(gold %d/%d) G5扩展d2=%d块/%d tok(gold %d/%d)"
              " | 候选块=%d 事件=%d D剔除(严格)=%d D剔除(宽松)=%d"
              % (r["qid"], r["gold_hop_depth"],
                 {k: len(v) for k, v in sorted(by_label.items())}, len(seeds), types,
                 len(one_hop), len(gold & one_hop), len(gold),
                 len(one_hop | two), len(gold & (one_hop | two)), len(gold),
                 len(depth1), tok1, len(gold & depth1), len(gold),
                 len(depth2), tok2, len(gold & depth2), len(gold),
                 len(cand_events), len({x for s in cand_events.values() for x in s}),
                 len(removedA), len(removedB)))
    print("\nD 组差集非空的题数：严格口径 %d/30，宽松口径 %d/30" % (stat_optA, stat_optB))
    return 0


if __name__ == "__main__":
    sys.exit(main())
