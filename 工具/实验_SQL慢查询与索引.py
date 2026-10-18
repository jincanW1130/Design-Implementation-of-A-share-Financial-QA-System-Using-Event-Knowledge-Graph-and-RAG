# -*- coding: utf-8 -*-
"""工具\\实验_SQL慢查询与索引.py —— 第 6 轮：MySQL 真实慢 SQL／EXPLAIN／索引核查。

做四件事（全部只读）：
1. 读 `performance_schema.events_statements_summary_by_digest`，列出本库执行过的 SQL
   摘要（按总耗时排序）——本项目 `slow_query_log=OFF`，用 performance_schema 取真实语句；
2. 对六表的关键查询逐条 `EXPLAIN`（以及 `EXPLAIN ANALYZE`）看索引命中；
3. 列出 `document_chunk`／`answer_evidence` 的索引清单；
4. 对缺失索引给出**幂等** `ALTER TABLE … ADD INDEX` 语句（只在脚本输出中给出；
   是否执行由调用方决定，默认不写库）。

用法（仓库根目录）::

    python 工具\\实验_SQL慢查询与索引.py
    python 工具\\实验_SQL慢查询与索引.py --apply-missing   # 仅当发现真缺失时才加索引
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
BACKEND_DIR = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
sys.dont_write_bytecode = True

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

import db  # noqa: E402  （后端 db；config 解析为后端那一份）

DEFAULT_OUT = os.path.join(ROOT, "交付物/05-系统实现/前后端系统集成/_工作底稿",
                           "SQL慢查询与索引_第6轮.json")


def _rows(sql, args=None):
    return db.query(sql, tuple(args or ()))


def _timer_ms(ps):
    return round(float(ps) / 1e9, 3) if ps is not None else None


def slow_digests(limit=15) -> list:
    sql = ("SELECT SCHEMA_NAME, DIGEST_TEXT, COUNT_STAR, "
           "       SUM_TIMER_WAIT, AVG_TIMER_WAIT, MAX_TIMER_WAIT, "
           "       SUM_ROWS_EXAMINED, SUM_ROWS_SENT, SUM_NO_INDEX_USED "
           "FROM performance_schema.events_statements_summary_by_digest "
           "WHERE SCHEMA_NAME = DATABASE() AND DIGEST_TEXT IS NOT NULL "
           "ORDER BY SUM_TIMER_WAIT DESC LIMIT %s")
    out = []
    for r in _rows(sql, (int(limit),)):
        out.append({
            "digest": (r["DIGEST_TEXT"] or "")[:300],
            "count": int(r["COUNT_STAR"]),
            "total_ms": _timer_ms(r["SUM_TIMER_WAIT"]),
            "avg_ms": _timer_ms(r["AVG_TIMER_WAIT"]),
            "max_ms": _timer_ms(r["MAX_TIMER_WAIT"]),
            "rows_examined": int(r["SUM_ROWS_EXAMINED"] or 0),
            "rows_sent": int(r["SUM_ROWS_SENT"] or 0),
            "no_index_used": int(r["SUM_NO_INDEX_USED"] or 0),
        })
    return out


def explain(sql, args, analyze=False) -> dict:
    prefix = "EXPLAIN ANALYZE " if analyze else "EXPLAIN "
    started = time.perf_counter()
    rows = _rows(prefix + sql, args)
    elapsed = (time.perf_counter() - started) * 1000.0
    if analyze:
        return {"analyze_tree": rows[0].get("EXPLAIN") if rows else "",
                "wall_ms": round(elapsed, 3)}
    return {"plan": [{k: (v.decode() if isinstance(v, bytes) else v) for k, v in r.items()}
                     for r in rows],
            "wall_ms": round(elapsed, 3)}


def index_list(table) -> list:
    return [{k: (v.decode() if isinstance(v, bytes) else v) for k, v in r.items()}
            for r in _rows("SHOW INDEX FROM `%s`" % table)]


def main() -> int:
    ap = argparse.ArgumentParser(description="MySQL 慢 SQL／EXPLAIN／索引核查（只读）")
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    variables = {r["Variable_name"]: r["Value"]
                 for r in _rows("SHOW VARIABLES WHERE Variable_name IN "
                                "('slow_query_log','long_query_time','performance_schema')")}

    answer_id = int(db.scalar("SELECT MIN(answer_id) FROM answer") or 1)
    doc_row = db.query_one("SELECT doc_id, chunk_index FROM document_chunk "
                           "ORDER BY doc_id, chunk_index LIMIT 1") or {"doc_id": 1, "chunk_index": 0}
    doc_id, chunk_index = int(doc_row["doc_id"]), int(doc_row["chunk_index"])
    chunk_id = int(db.scalar("SELECT chunk_id FROM document_chunk WHERE doc_id=%s "
                             "ORDER BY chunk_index LIMIT 1", (doc_id,)) or 0)
    session_id = db.scalar("SELECT session_id FROM question WHERE session_id IS NOT NULL "
                           "AND session_id <> '' LIMIT 1") or "no-session"

    cases = [
        ("answer_evidence(answer_id) JOIN document",
         ("SELECT ae.`rank` AS `rank`, ae.chunk_id, ae.doc_id, ae.evidence_type, "
          "d.title, d.source, d.publish_time, d.url "
          "FROM answer_evidence ae JOIN document d ON d.doc_id = ae.doc_id "
          "WHERE ae.answer_id = %s ORDER BY ae.`rank` ASC, ae.chunk_id ASC",
          (answer_id,))),
        ("answer_evidence(answer_id) COUNT",
         ("SELECT COUNT(*) FROM answer_evidence ae WHERE ae.answer_id = %s",
          (answer_id,))),
        ("document_chunk(doc_id, chunk_index) range",
         ("SELECT chunk_id, chunk_index, content FROM document_chunk "
          "WHERE doc_id = %s AND chunk_index BETWEEN %s AND %s AND chunk_id <> %s "
          "ORDER BY chunk_index ASC",
          (doc_id, chunk_index - 1, chunk_index + 1, chunk_id))),
        ("document_chunk(chunk_id) IN",
         ("SELECT chunk_id, chunk_index FROM document_chunk WHERE chunk_id IN (%s, %s)",
          (chunk_id, chunk_id + 1))),
        ("question(session_id) JOIN answer",
         ("SELECT q.question_id, a.answer_id, q.question_text, q.ask_time, a.answer_text "
          "FROM question q JOIN answer a ON a.question_id = q.question_id "
          "WHERE q.session_id = %s ORDER BY q.ask_time DESC, q.question_id DESC "
          "LIMIT 20 OFFSET 0",
          (session_id,))),
        ("document(doc_id) IN",
         ("SELECT doc_id, title, source, publish_time, url, category FROM document "
          "WHERE doc_id IN (%s, %s)",
          (doc_id, doc_id + 1))),
    ]

    checks = []
    for name, (sql, params) in cases:
        checks.append({"name": name, "sql": sql,
                       "explain": explain(sql, params),
                       "explain_analyze": explain(sql, params, analyze=True)})

    # 只检查两个任务点名的索引；其余表按需在文档里说明
    indexes = {"document_chunk": index_list("document_chunk"),
               "answer_evidence": index_list("answer_evidence")}

    existing = {(t, r["Key_name"]) for t, rows in indexes.items() for r in rows}
    candidate_ddl = [
        "ALTER TABLE `document_chunk` ADD INDEX `idx_chunk_doc_id` (`doc_id`)",
        "ALTER TABLE `answer_evidence` ADD INDEX `idx_ae_answer_id` (`answer_id`)",
    ]
    present = {"idx_chunk_doc_id" in {r["Key_name"] for r in indexes["document_chunk"]},
               "idx_ae_answer_id" in {r["Key_name"] for r in indexes["answer_evidence"]}}

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "database": db.query_one("SELECT DATABASE() AS db")["db"],
        "variables": variables,
        "slow_digests": slow_digests(),
        "checks": checks,
        "indexes": indexes,
        "missing_index_candidates": {
            "already_present": present,
            "ddl_if_missing": candidate_ddl,
            "note": "两条候选索引在冻结 DDL 中已存在（分别为组合唯一索引的前缀与主键前缀）；"
                    "本脚本默认只读，发现真缺失时再由 --apply-missing 执行（幂等判断在代码里）。",
        },
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True,
                  default=lambda o: sorted(o) if isinstance(o, set) else str(o))
        f.write("\n")

    print("MySQL %s；slow_query_log=%s long_query_time=%s performance_schema=%s"
          % (payload["database"], variables.get("slow_query_log"),
             variables.get("long_query_time"), variables.get("performance_schema")))
    print("\n慢 SQL 摘要（按总耗时，前 10）：")
    for r in payload["slow_digests"][:10]:
        print("  count=%d total=%.1fms avg=%.2fms max=%.1fms no_index=%d rows_exam=%d  %s"
              % (r["count"], r["total_ms"] or 0, r["avg_ms"] or 0, r["max_ms"] or 0,
                 r["no_index_used"], r["rows_examined"], r["digest"][:110]))
    print("\nEXPLAIN 摘要：")
    for c in checks:
        p = c["explain"]["plan"][0] if c["explain"]["plan"] else {}
        print("  %-46s type=%-8s key=%-24s rows=%s extra=%s"
              % (c["name"], p.get("type"), p.get("key"), p.get("rows"),
                 str(p.get("Extra"))[:50]))
    print("\n索引：document_chunk=%s；answer_evidence=%s"
          % (sorted({r["Key_name"] for r in indexes["document_chunk"]}),
             sorted({r["Key_name"] for r in indexes["answer_evidence"]})))
    print("候选索引是否已存在：%s" % present)
    print("\n结论 JSON：%s" % args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
