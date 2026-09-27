# -*- coding: utf-8 -*-
"""只读汇总：A～E 组 trace 的逐题集合大小、预算占用、可测性与组间差异（供交付报告）。"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DIR = os.path.join(_ROOT, "阶段07-RAG检索系统", "_工作底稿")


def load(group):
    path = os.path.join(_DIR, "pipeline_trace_%s.jsonl" % group)
    rows = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    return {row["qid"]: row for row in rows}


def main() -> int:
    groups = {name: load(name) for name in ("A", "B", "C", "D", "E")}
    qids = list(groups["D"])
    print("题目  gold  A C D E(集合大小)  D预算占用  D可测差异条数  载荷(D)  D集合−A集合")
    same_ac = payload_d = 0
    for qid in qids:
        d = groups["D"][qid]
        a = groups["A"][qid]
        c = groups["C"][qid]
        b = groups["B"][qid]
        e = groups["E"][qid]
        diff_ac = sorted(set(c["evidence"]) - set(a["evidence"]))
        if diff_ac:
            same_ac += 1
        if d["graph_payload"]["graph_used"]:
            payload_d += 1
        print("%s %4d  %2d/%2d/%2d/%2d    %4d/%-4d   %3d 个%s    %s    %s"
              % (qid, len(d["gold_evidence_chunk_ids"]) if "gold_evidence_chunk_ids" in d
                 else -1, len(a["evidence"]), len(c["evidence"]), len(d["evidence"]),
                 len(e["evidence"]), d["token_account"]["total_tokens"],
                 d["context_token_budget"], d["candidate_diff_counts"]["removed"],
                 "（可测）" if d["candidate_diff_measurable"] else "（不可测）",
                 "有" if d["graph_payload"]["graph_used"] else "无", diff_ac or "-"))
    print("\nC 与 A 的最终证据集合不同的题数：%d／%d" % (same_ac, len(qids)))
    print("D 组出现图谱路径载荷的题数：%d／%d" % (payload_d, len(qids)))
    for name in ("A", "B", "C", "D", "E"):
        rows = groups[name]
        sizes = [len(r["evidence"]) for r in rows.values()]
        tokens = [r["token_account"]["total_tokens"] for r in rows.values()]
        print("%s 组：集合大小 %d～%d（均 %.2f），预算占用 %d～%d token"
              % (name, min(sizes), max(sizes), sum(sizes) / len(sizes),
                 min(tokens), max(tokens)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
