# -*- coding: utf-8 -*-
"""工具\\数据质量校验.py —— 入库前数据质量校验（第三轮 5.4，2026-10-18）。

定位
----
这是 `import_data.py` 之前的**只读门禁**：先校验数据集与问答产出，再决定是否导入。
与 `数据准备/check.py`（导出后的 T8 一致性核对）互补：

* `check.py`：已导出数据之间的一致性（计数／ID／时间／来源），偏“结果复核”；
* 本脚本：**入库前的必填／类型／主键唯一／外键／重复**检查，偏“导入前置条件”，
  并可选对当前 MySQL 做**只读**交叉核对（计数、孤儿行、文本一致性）。

安全边界
--------
* **只读**：本脚本不执行任何 INSERT/UPDATE/DELETE/DDL，不调用 `ensure_database()`、
  `init_schema()`，也不写数据库。
* **干跑**：默认只读文件＋读库核对；`--skip-db` 可完全离线。
* 报告写到文件（默认 `交付物/06-实验与评测/系统指标/数据质量校验_第三轮.json`）。

用法
----
    python 工具\\数据质量校验.py                 # 文件 + 只读 MySQL 交叉核对
    python 工具\\数据质量校验.py --skip-db       # 完全离线
    python 工具\\数据质量校验.py --out 某路径.json

退出码：0 = 0 违规；1 = 有违规；2 = 输入缺失/无法解析等运行错误。
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import config  # noqa: E402  （复用后端配置中的路径口径）

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

DEFAULT_OUT = os.path.join(
    ROOT, "交付物", "06-实验与评测", "系统指标", "数据质量校验_第三轮.json")

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ISO_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
SHA16_RE = re.compile(r"^[0-9a-f]{16}$")

MAX_DETAILS = 200


# --------------------------------------------------------------------------
# 1. 基础工具
# --------------------------------------------------------------------------
class Report:
    """收集违规项与统计；违规项只为定位问题，不修改任何数据。"""

    def __init__(self) -> None:
        self.violations: list[dict] = []
        self.violation_total = 0
        self.stats: dict = {}
        self.db: dict = {"status": "skipped"}

    def add(self, code: str, where: str, field: str, detail: str) -> None:
        self.violation_total += 1
        if len(self.violations) < MAX_DETAILS:
            self.violations.append({
                "code": code, "where": where, "field": field, "detail": detail})

    def fail(self, code: str, where: str, field: str, detail: str) -> None:
        self.add(code, where, field, detail)

    def truncate(self, items, n=10):
        items = list(items)
        return items[:n] + (["…(+%d)" % (len(items) - n)] if len(items) > n else [])


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def load_jsonl(path: str, report: Report, label: str) -> list:
    rows = []
    if not os.path.isfile(path):
        report.fail("INPUT_MISSING", label, "-", "文件不存在：%s" % path)
        return rows
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                report.fail("JSON_INVALID", label, "-",
                            "第 %d 行不是合法 JSON：%s" % (lineno, exc))
                continue
            if not isinstance(obj, dict):
                report.fail("JSON_NOT_OBJECT", label, "-",
                            "第 %d 行顶层不是对象（实际 %s）" % (lineno, type(obj).__name__))
                continue
            obj["__line__"] = lineno
            rows.append(obj)
    return rows


def require(report: Report, where: str, row: dict, field: str, kind: str) -> bool:
    """必填 + 类型检查；返回是否通过（同时保证后续取值安全）。"""
    if field not in row or row[field] is None:
        report.fail("REQUIRED_MISSING", where, field, "字段缺失或为 null")
        return False
    value = row[field]
    if kind == "int":
        if not _is_int(value):
            report.fail("TYPE_INVALID", where, field,
                        "期望 int，实际 %s（%r）" % (type(value).__name__, value))
            return False
        return True
    if kind == "str":
        if not _nonempty_str(value):
            report.fail("VALUE_EMPTY", where, field,
                        "期望非空字符串，实际 %r" % (value,))
            return False
        return True
    if kind == "list":
        if not isinstance(value, list):
            report.fail("TYPE_INVALID", where, field,
                        "期望 list，实际 %s" % type(value).__name__)
            return False
        return True
    if kind == "dict":
        if not isinstance(value, dict):
            report.fail("TYPE_INVALID", where, field,
                        "期望 dict，实际 %s" % type(value).__name__)
            return False
        return True
    raise ValueError("unknown kind %r" % kind)


def duplicate_values(values, report: Report, where: str, field: str) -> int:
    counts = collections.Counter(values)
    dups = {k: v for k, v in counts.items() if v > 1}
    for key, n in list(dups.items())[:20]:
        report.fail("DUPLICATE", where, field, "值 %r 出现 %d 次" % (key, n))
    return len(dups)


def _iso_ok(value: str, pattern) -> bool:
    if not isinstance(value, str) or not pattern.match(value):
        return False
    try:
        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        try:
            _dt.date.fromisoformat(value)
            return True
        except ValueError:
            return False


# --------------------------------------------------------------------------
# 2. 文件级校验
# --------------------------------------------------------------------------
def check_documents(rows: list, report: Report) -> dict:
    where = "documents.jsonl"
    if not rows:
        report.fail("EMPTY_DATASET", where, "-", "文档集为空")
    for i, row in enumerate(rows):
        w = "%s#%s" % (where, row.get("doc_id", "行%d" % (i + 1)))
        for field in ("doc_id", "title", "content", "source", "category",
                      "url", "publish_time", "ingest_time", "content_sha256_16"):
            kind = "int" if field == "doc_id" else "str"
            require(report, w, row, field, kind)
        if _nonempty_str(row.get("publish_time")) and not _iso_ok(row["publish_time"], ISO_DATE_RE):
            report.fail("DATE_INVALID", w, "publish_time", "期望 YYYY-MM-DD，实际 %r" % row["publish_time"])
        if _nonempty_str(row.get("ingest_time")) and not _iso_ok(row["ingest_time"], ISO_DATETIME_RE):
            report.fail("DATETIME_INVALID", w, "ingest_time",
                        "期望带时区的 ISO 日期时间，实际 %r" % row["ingest_time"])
        if _nonempty_str(row.get("content_sha256_16")) and not SHA16_RE.match(row["content_sha256_16"]):
            report.fail("HASH_INVALID", w, "content_sha256_16",
                        "期望 16 位小写十六进制，实际 %r" % row["content_sha256_16"])
        for list_field in ("company_list", "subject_companies"):
            if list_field in row and row[list_field] is not None:
                require(report, w, row, list_field, "list")

    dup_doc = duplicate_values([r.get("doc_id") for r in rows], report, where, "doc_id")
    dup_url = duplicate_values([r.get("url") for r in rows], report, where, "url")
    dup_title = duplicate_values([r.get("title") for r in rows], report, where, "title")
    return {
        "rows": len(rows),
        "unique_doc_id": len({r.get("doc_id") for r in rows}),
        "duplicate_doc_id": dup_doc,
        "duplicate_url": dup_url,
        "duplicate_title": dup_title,
    }


def check_chunks(rows: list, doc_ids: set, report: Report) -> dict:
    where = "chunks.jsonl"
    if not rows:
        report.fail("EMPTY_DATASET", where, "-", "切块集为空")
    for i, row in enumerate(rows):
        w = "%s#%s" % (where, row.get("chunk_id", "行%d" % (i + 1)))
        for field in ("chunk_id", "doc_id", "chunk_index", "token_count", "vector_id"):
            require(report, w, row, field, "int")
        require(report, w, row, "content", "str")
        if _is_int(row.get("chunk_index")) and row["chunk_index"] < 0:
            report.fail("VALUE_RANGE", w, "chunk_index", "期望 >= 0，实际 %d" % row["chunk_index"])
        if _is_int(row.get("token_count")) and row["token_count"] <= 0:
            report.fail("VALUE_RANGE", w, "token_count", "期望 > 0，实际 %d" % row["token_count"])
        if _is_int(row.get("vector_id")) and row["vector_id"] < 0:
            report.fail("VALUE_RANGE", w, "vector_id", "期望 >= 0，实际 %d" % row["vector_id"])
        if _is_int(row.get("doc_id")) and row["doc_id"] not in doc_ids:
            report.fail("FK_MISSING", w, "doc_id",
                        "doc_id=%s 在 documents.jsonl 中不存在" % row["doc_id"])

    dup_chunk = duplicate_values([r.get("chunk_id") for r in rows], report, where, "chunk_id")
    dup_vec = duplicate_values([r.get("vector_id") for r in rows], report, where, "vector_id")
    dup_doc_idx = duplicate_values(
        [(r.get("doc_id"), r.get("chunk_index")) for r in rows], report, where, "(doc_id, chunk_index)")
    covered = {r.get("doc_id") for r in rows}
    uncovered = sorted(doc_ids - covered)
    for doc_id in uncovered[:20]:
        report.fail("CHUNK_COVERAGE", where, "doc_id",
                    "文档 doc_id=%s 没有任何切块" % doc_id)
    return {
        "rows": len(rows),
        "unique_chunk_id": len({r.get("chunk_id") for r in rows}),
        "duplicate_chunk_id": dup_chunk,
        "duplicate_vector_id": dup_vec,
        "duplicate_doc_index": dup_doc_idx,
        "documents_without_chunk": len(uncovered),
    }


def check_qa_records(rows: list, doc_ids: set, chunk_map: dict, report: Report) -> dict:
    where = "qa_records.jsonl"
    if not rows:
        report.fail("EMPTY_DATASET", where, "-", "问答记录为空")
    qids, aids = [], []
    evidence_total = 0
    for i, rec in enumerate(rows):
        w = "%s#%s" % (where, i + 1)
        for key in ("question", "answer", "answer_evidence"):
            if key not in rec:
                report.fail("REQUIRED_MISSING", w, key, "顶层字段缺失")
        q = rec.get("question") if isinstance(rec.get("question"), dict) else {}
        a = rec.get("answer") if isinstance(rec.get("answer"), dict) else {}
        e = rec.get("answer_evidence") if isinstance(rec.get("answer_evidence"), list) else []
        if not q:
            report.fail("TYPE_INVALID", w, "question", "期望非空 dict")
        if not a:
            report.fail("TYPE_INVALID", w, "answer", "期望非空 dict")
        if not e:
            report.fail("VALUE_EMPTY", w, "answer_evidence", "证据列表为空")

        qid = q.get("question_id")
        aid = a.get("answer_id")
        if qid is not None:
            qids.append(qid)
        if aid is not None:
            aids.append(aid)
        for field in ("question_id", "question_text", "session_id", "ask_time",
                      "task_type", "time_constraint"):
            require(report, "%s.question" % w, q, field, "str")
        if _nonempty_str(q.get("ask_time")) and not _iso_ok(q["ask_time"], ISO_DATETIME_RE):
            report.fail("DATETIME_INVALID", "%s.question" % w, "ask_time",
                        "期望带时区的 ISO 日期时间，实际 %r" % q["ask_time"])
        if "gold_hop_depth" in q:
            require(report, "%s.question" % w, q, "gold_hop_depth", "int")

        for field in ("answer_id", "question_id", "answer_text", "model_name",
                      "prompt_version", "create_time"):
            require(report, "%s.answer" % w, a, field, "str")
        if _nonempty_str(a.get("create_time")) and not _iso_ok(a["create_time"], ISO_DATETIME_RE):
            report.fail("DATETIME_INVALID", "%s.answer" % w, "create_time",
                        "期望带时区的 ISO 日期时间，实际 %r" % a["create_time"])
        if a.get("question_id") not in (None, qid):
            report.fail("FK_MISMATCH", "%s.answer" % w, "question_id",
                        "answer.question_id=%r 与 question.question_id=%r 不一致"
                        % (a.get("question_id"), qid))
        if "is_graph_extended" in a:
            require(report, "%s.answer" % w, a, "is_graph_extended", "int")
            if _is_int(a["is_graph_extended"]) and a["is_graph_extended"] not in (0, 1):
                report.fail("VALUE_RANGE", "%s.answer" % w, "is_graph_extended",
                            "期望 0/1，实际 %r" % a["is_graph_extended"])
        if "graph_path" in a and a["graph_path"] is not None:
            try:
                gp = json.loads(a["graph_path"]) if isinstance(a["graph_path"], str) else a["graph_path"]
                if not isinstance(gp, list):
                    raise ValueError("顶层不是 list")
            except Exception as exc:
                report.fail("JSON_INVALID", "%s.answer" % w, "graph_path",
                            "无法解析为 JSON 列表：%s" % exc)

        seen_pairs = set()
        for j, ev in enumerate(e):
            ew = "%s.answer_evidence[%d]" % (w, j)
            if not isinstance(ev, dict):
                report.fail("TYPE_INVALID", ew, "-", "证据项不是对象")
                continue
            evidence_total += 1
            for field in ("answer_id", "chunk_id", "doc_id", "rank", "evidence_type"):
                kind = "int" if field in ("chunk_id", "doc_id", "rank") else "str"
                require(report, ew, ev, field, kind)
            if ev.get("answer_id") not in (None, aid):
                report.fail("FK_MISMATCH", ew, "answer_id",
                            "证据 answer_id=%r 与 answer.answer_id=%r 不一致"
                            % (ev.get("answer_id"), aid))
            chunk_id = ev.get("chunk_id")
            doc_id = ev.get("doc_id")
            if _is_int(doc_id) and doc_id not in doc_ids:
                report.fail("FK_MISSING", ew, "doc_id",
                            "doc_id=%s 在 documents.jsonl 中不存在" % doc_id)
            if _is_int(chunk_id):
                chunk = chunk_map.get(chunk_id)
                if chunk is None:
                    report.fail("FK_MISSING", ew, "chunk_id",
                                "chunk_id=%s 在 chunks.jsonl 中不存在" % chunk_id)
                elif _is_int(doc_id) and chunk.get("doc_id") != doc_id:
                    report.fail("FK_MISMATCH", ew, "doc_id",
                                "证据 doc_id=%s 与切块所属 doc_id=%s 不一致"
                                % (doc_id, chunk.get("doc_id")))
            if _is_int(ev.get("rank")) and ev["rank"] <= 0:
                report.fail("VALUE_RANGE", ew, "rank", "期望 > 0，实际 %d" % ev["rank"])
            pair = (ev.get("answer_id"), chunk_id)
            if pair in seen_pairs:
                report.fail("DUPLICATE", ew, "(answer_id, chunk_id)", "同一答案内证据重复：%r" % (pair,))
            seen_pairs.add(pair)

        ranks = [ev.get("rank") for ev in e if isinstance(ev, dict) and _is_int(ev.get("rank"))]
        if ranks and len(ranks) != len(set(ranks)):
            report.fail("DUPLICATE", w, "rank", "同一答案内 rank 重复：%r" % sorted(ranks))

    dup_q = duplicate_values(qids, report, where, "question_id")
    dup_a = duplicate_values(aids, report, where, "answer_id")
    return {
        "rows": len(rows),
        "questions": len(qids),
        "answers": len(aids),
        "evidence": evidence_total,
        "duplicate_question_id": dup_q,
        "duplicate_answer_id": dup_a,
    }


# --------------------------------------------------------------------------
# 3. 只读数据库交叉核对
# --------------------------------------------------------------------------
def check_database(doc_stats: dict, chunk_stats: dict, qa_stats: dict,
                   docs: list, chunks: list, recs: list, report: Report) -> dict:
    """只读核对：计数、孤儿行、重复、文本/证据一致性。**不写库。**"""
    try:
        import db  # noqa: F401  （延迟导入：--skip-db 时无需连库）
    except Exception as exc:
        report.fail("DB_IMPORT_FAILED", "mysql", "-", "%s: %s" % (type(exc).__name__, exc))
        return {"status": "unavailable", "error": str(exc)}
    try:
        counts = db.table_counts()
        version = db.server_version()
    except Exception as exc:
        report.fail("DB_UNAVAILABLE", "mysql", "-", "%s: %s" % (type(exc).__name__, exc))
        return {"status": "unavailable", "error": str(exc)}

    expected = {
        "document": doc_stats["rows"],
        "document_chunk": chunk_stats["rows"],
        "question": qa_stats["questions"],
        "answer": qa_stats["answers"],
        "answer_evidence": qa_stats["evidence"],
    }
    for table, want in expected.items():
        got = counts.get(table)
        if got != want:
            report.fail("DB_COUNT_MISMATCH", "mysql:%s" % table, "COUNT(*)",
                        "期望 %d（来自文件），实际 %s" % (want, got))

    orphan_sql = [
        ("chunk_orphan_doc",
         "SELECT COUNT(*) AS n FROM document_chunk c "
         "LEFT JOIN document d ON d.doc_id=c.doc_id WHERE d.doc_id IS NULL"),
        ("answer_orphan_question",
         "SELECT COUNT(*) AS n FROM answer a "
         "LEFT JOIN question q ON q.question_id=a.question_id WHERE q.question_id IS NULL"),
        ("evidence_orphan_answer",
         "SELECT COUNT(*) AS n FROM answer_evidence e "
         "LEFT JOIN answer a ON a.answer_id=e.answer_id WHERE a.answer_id IS NULL"),
        ("evidence_orphan_chunk",
         "SELECT COUNT(*) AS n FROM answer_evidence e "
         "LEFT JOIN document_chunk c ON c.chunk_id=e.chunk_id WHERE c.chunk_id IS NULL"),
        ("evidence_orphan_doc",
         "SELECT COUNT(*) AS n FROM answer_evidence e "
         "LEFT JOIN document d ON d.doc_id=e.doc_id WHERE d.doc_id IS NULL"),
        ("evidence_doc_mismatch",
         "SELECT COUNT(*) AS n FROM answer_evidence e "
         "JOIN document_chunk c ON c.chunk_id=e.chunk_id "
         "WHERE e.doc_id<>c.doc_id"),
        ("question_over_baseline",
         "SELECT COUNT(*) AS n FROM question WHERE question_id>%d" % qa_stats["questions"]),
    ]
    orphan = {}
    for name, sql in orphan_sql:
        try:
            n = int(db.scalar(sql) or 0)
        except Exception as exc:
            report.fail("DB_QUERY_FAILED", "mysql", name, "%s: %s" % (type(exc).__name__, exc))
            n = -1
        orphan[name] = n
        if n > 0:
            report.fail("DB_ORPHAN", "mysql", name, "检出 %d 行" % n)

    dup_sql = [
        ("document_doc_id", "SELECT COUNT(*) AS n FROM (SELECT doc_id FROM document GROUP BY doc_id HAVING COUNT(*)>1) t"),
        ("chunk_chunk_id", "SELECT COUNT(*) AS n FROM (SELECT chunk_id FROM document_chunk GROUP BY chunk_id HAVING COUNT(*)>1) t"),
        ("chunk_vector_id", "SELECT COUNT(*) AS n FROM (SELECT vector_id FROM document_chunk GROUP BY vector_id HAVING COUNT(*)>1) t"),
        ("question_question_id", "SELECT COUNT(*) AS n FROM (SELECT question_id FROM question GROUP BY question_id HAVING COUNT(*)>1) t"),
        ("answer_answer_id", "SELECT COUNT(*) AS n FROM (SELECT answer_id FROM answer GROUP BY answer_id HAVING COUNT(*)>1) t"),
    ]
    duplicates = {}
    for name, sql in dup_sql:
        try:
            n = int(db.scalar(sql) or 0)
        except Exception as exc:
            report.fail("DB_QUERY_FAILED", "mysql", name, "%s: %s" % (type(exc).__name__, exc))
            n = -1
        duplicates[name] = n
        if n > 0:
            report.fail("DB_DUPLICATE", "mysql", name, "检出 %d 组重复" % n)

    # 文本一致性：以 question_text 对齐文件与库（避免依赖 Q-001 与 1 的编号映射）
    db_q_texts = {r["question_text"] for r in db.query("SELECT question_text FROM question")}
    db_a_texts = {r["answer_text"] for r in db.query("SELECT answer_text FROM answer")}
    file_q_texts = {r["question"]["question_text"] for r in recs}
    file_a_texts = {r["answer"]["answer_text"] for r in recs}
    q_missing = file_q_texts - db_q_texts
    a_missing = file_a_texts - db_a_texts
    if q_missing:
        report.fail("DB_TEXT_MISMATCH", "mysql:question", "question_text",
                    "文件中有 %d 条问题文本在库中找不到；示例：%r"
                    % (len(q_missing), sorted(q_missing)[0]))
    if a_missing:
        report.fail("DB_TEXT_MISMATCH", "mysql:answer", "answer_text",
                    "文件中有 %d 条答案文本在库中找不到；示例：%r"
                    % (len(a_missing), sorted(a_missing)[0]))

    # 证据集合一致性：按问题文本对齐，比较 chunk_id 集合
    db_evidence = {}
    rows = db.query(
        "SELECT q.question_text, e.chunk_id FROM answer_evidence e "
        "JOIN answer a ON a.answer_id=e.answer_id "
        "JOIN question q ON q.question_id=a.question_id")
    for row in rows:
        db_evidence.setdefault(row["question_text"], set()).add(row["chunk_id"])
    file_evidence = {
        r["question"]["question_text"]: {ev["chunk_id"] for ev in r["answer_evidence"]}
        for r in recs}
    evidence_mismatch = 0
    for text, chunk_ids in file_evidence.items():
        if db_evidence.get(text) != chunk_ids:
            evidence_mismatch += 1
    if evidence_mismatch:
        report.fail("DB_EVIDENCE_MISMATCH", "mysql:answer_evidence", "-",
                    "%d 条问题的证据 chunk_id 集合与文件不一致" % evidence_mismatch)

    return {
        "status": "checked",
        "server_version": version,
        "counts": counts,
        "expected_counts": expected,
        "orphan": orphan,
        "duplicates": duplicates,
        "text_mismatch": {"question": len(q_missing), "answer": len(a_missing)},
        "evidence_mismatch_questions": evidence_mismatch,
        "note": "只读核对；未执行任何写操作。",
    }


# --------------------------------------------------------------------------
# 4. 主流程
# --------------------------------------------------------------------------
def build_report(documents_path: str, chunks_path: str, qa_path: str,
                 skip_db: bool = False) -> Report:
    report = Report()
    docs = load_jsonl(documents_path, report, "documents.jsonl")
    chunks = load_jsonl(chunks_path, report, "chunks.jsonl")
    recs = load_jsonl(qa_path, report, "qa_records.jsonl")

    doc_stats = check_documents(docs, report)
    doc_ids = {r.get("doc_id") for r in docs if _is_int(r.get("doc_id"))}
    chunk_stats = check_chunks(chunks, doc_ids, report)
    chunk_map = {r.get("chunk_id"): r for r in chunks if _is_int(r.get("chunk_id"))}
    qa_stats = check_qa_records(recs, doc_ids, chunk_map, report)

    report.stats = {
        "documents": doc_stats,
        "chunks": chunk_stats,
        "qa_records": qa_stats,
        "files": {
            "documents": os.path.abspath(documents_path),
            "chunks": os.path.abspath(chunks_path),
            "qa_records": os.path.abspath(qa_path),
        },
    }
    if not skip_db:
        report.db = check_database(doc_stats, chunk_stats, qa_stats, docs, chunks, recs, report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="入库前数据质量校验（只读、干跑）")
    parser.add_argument("--documents", default=config.DOCUMENTS_JSONL)
    parser.add_argument("--chunks", default=config.CHUNKS_JSONL)
    parser.add_argument("--qa-records", default=config.QA_RECORDS_JSONL)
    parser.add_argument("--out", default=DEFAULT_OUT, help="JSON 报告输出路径")
    parser.add_argument("--skip-db", action="store_true", help="不连 MySQL，仅校验文件")
    args = parser.parse_args(argv)

    report = build_report(args.documents, args.chunks, args.qa_records,
                          skip_db=args.skip_db)
    payload = {
        "tool": "工具/数据质量校验.py",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "dry-run/read-only",
        "violation_total": report.violation_total,
        "violations": report.violations,
        "stats": report.stats,
        "db": report.db,
    }
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print("=" * 72)
    print("入库前数据质量校验（只读、干跑）")
    print("=" * 72)
    print("  documents.jsonl      = %d 行" % report.stats.get("documents", {}).get("rows", 0))
    print("  chunks.jsonl         = %d 行" % report.stats.get("chunks", {}).get("rows", 0))
    print("  qa_records.jsonl     = %d 条问答 / %d 条证据"
          % (report.stats.get("qa_records", {}).get("rows", 0),
             report.stats.get("qa_records", {}).get("evidence", 0)))
    if report.db.get("status") == "checked":
        print("  MySQL 只读交叉核对   = 已执行（版本 %s）" % report.db.get("server_version"))
    elif report.db.get("status") == "unavailable":
        print("  MySQL 只读交叉核对   = 不可用（文件级结果仍有效）")
    else:
        print("  MySQL 只读交叉核对   = 已跳过（--skip-db）")
    print("  违规总数             = %d" % report.violation_total)
    for item in report.violations[:20]:
        print("    - [%s] %s / %s：%s"
              % (item["code"], item["where"], item["field"], item["detail"]))
    if report.violation_total > len(report.violations):
        print("    …（仅显示前 %d 条，完整清单见报告）" % len(report.violations))
    print("  报告                 = %s" % out)
    print("=" * 72)
    print("结论：%s" % ("0 违规，可进入导入步骤（本次未导入、未改库）"
                       if report.violation_total == 0 else "存在违规，请先修复再导入"))
    return 0 if report.violation_total == 0 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断（未写库）。", file=sys.stderr)
        raise SystemExit(130)
