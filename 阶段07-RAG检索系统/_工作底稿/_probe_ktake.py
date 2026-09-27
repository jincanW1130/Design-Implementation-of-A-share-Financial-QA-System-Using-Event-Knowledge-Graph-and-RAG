# -*- coding: utf-8 -*-
"""只读勘察：K 截取的两读法（字面＝向量前 K；图谱优先）在 30 题 gold 上的差别。

只读输入；不写任何产出。
"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "代码", "检索"))

import config                                                    # noqa: E402
import pipeline as P                                             # noqa: E402
from vector_search import VectorSearcher                         # noqa: E402


def main() -> int:
    graph = P.default_graph()
    chunks = P.load_chunks()
    docs = P.load_documents()
    rows = P.load_questions(config.QUESTION_FILES["questions"])
    runner = P.PipelineRunner(graph=graph, chunks=chunks, documents=docs, verbose=False)
    runner.ensure_searcher()
    import collections
    blame = []
    for row in rows:
        entities = P.resolve_question_entities(graph, row["question"])
        types = P.question_event_types(row["question"])
        side = P.collect_graph_candidates(graph, entities["seeds"], types, 2, chunks)
        vec, _ = runner.searcher.search(row["question"], 20)
        merged = P.merge_candidates(vec, side["candidates"], chunks)["records"]
        near_ordinals = {p["ordinal"] for p in side["paths"] if p["anchor_distance"] == 0}
        near_ids = {cid for cid, rec in side["candidates"].items()
                    if set(rec["path_ordinals"]) & near_ordinals}
        gold = set(row["gold_evidence_chunk_ids"])
        top10 = {r["chunk_id"] for r in P.fixed_original_order(merged, side["paths"])[:10]}
        chosen = sorted(merged, key=lambda r: (
            (0 if r["vector_rank"] is None and r["chunk_id"] in near_ids else
             1 if r["vector_rank"] is None else 2),
            (r.get("first_path_key") or (10 ** 9, 0)),
            (r["vector_rank"] if r["vector_rank"] is not None else 10 ** 9),
            r["chunk_id"]))[:10]
        got = {r["chunk_id"] for r in chosen}
        blame.append({"qid": row["qid"], "gold": len(gold), "near": len(near_ids),
                      "graph_all": len(side["candidates"]),
                      "gold_in_near": len(gold & near_ids), "gold_in_graph": len(gold & set(side["candidates"])),
                      "gold_in_vec10": len(gold & top10),
                      "literal_complete": gold <= top10, "near_first_complete": gold <= got})
    print("qid    gold near graph | gold∩near gold∩graph gold∩vec10 | literal near_first")
    for b in blame:
        print("%s %4d %4d %5d | %8d %10d %8d | %7s %10s"
              % (b["qid"], b["gold"], b["near"], b["graph_all"], b["gold_in_near"],
                 b["gold_in_graph"], b["gold_in_vec10"], b["literal_complete"],
                 b["near_first_complete"]))
    for k in (5, 10, 15):
        line = []
        for rule in ("literal", "graph_first", "near_graph_first", "near_vector_far"):
            ok = 0
            rec_sum = 0.0
            for row in rows:
                entities = P.resolve_question_entities(graph, row["question"])
                types = P.question_event_types(row["question"])
                side = P.collect_graph_candidates(graph, entities["seeds"], types, 2, chunks)
                vec, _ = runner.searcher.search(row["question"], 20)
                merged = P.merge_candidates(vec, side["candidates"], chunks)["records"]
                near_ordinals = {p["ordinal"] for p in side["paths"] if p["anchor_distance"] == 0}
                def near(rec):
                    return bool(set(rec.get("graph_path_ordinals") or []) & near_ordinals)
                if rule == "literal":
                    chosen = P.fixed_original_order(merged, side["paths"])[:k]
                elif rule == "graph_first":
                    chosen = sorted(merged, key=P.evidence_priority_key)[:k]
                elif rule == "near_graph_first":
                    chosen = sorted(merged, key=lambda r: (
                        (0 if r["vector_rank"] is None and near(r) else
                         1 if r["vector_rank"] is None else 2),
                        (r.get("first_path_key") or (10 ** 9, 0)),
                        (r["vector_rank"] if r["vector_rank"] is not None else 10 ** 9),
                        r["chunk_id"]))[:k]
                else:
                    chosen = sorted(merged, key=lambda r: (
                        (0 if r["vector_rank"] is not None else
                         (1 if near(r) else 2)),
                        (r["vector_rank"] if r["vector_rank"] is not None else
                         (r.get("first_path_key") or (10 ** 9, 0))[0]),
                        r["chunk_id"]))[:k]
                got = {r["chunk_id"] for r in chosen}
                gold = set(row["gold_evidence_chunk_ids"])
                rec_sum += len(got & gold) / len(gold) if gold else 0.0
                ok += 1 if gold and gold <= got else 0
            line.append("%s: Complete=%d/30 平均Recall=%.3f" % (rule, ok, rec_sum / len(rows)))
        print("K=%2d  " % k + "  |  ".join(line))
    return 0


if __name__ == "__main__":
    sys.exit(main())
