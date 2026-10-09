# -*- coding: utf-8 -*-
"""代码\\后端\\tools\\import_data.py —— 第 9 阶段 T2 的**数据库导入**（幂等）。

把三份上游产物导入 MySQL 的六张表（`user` 表**不写入任何行**，B8）：

    documents.jsonl（709 行）  → document
    chunks.jsonl    （5018 行）→ document_chunk
    qa_records.jsonl（30 条，含 question／answer／answer_evidence 三块）
                    （30／30／293）→ question／answer／answer_evidence

--------------------------------------------------------------------------
一、字段映射表（**按真实数据逐项读出来的，不凭猜**）
--------------------------------------------------------------------------
下表左侧是 JSONL 里实际存在的字段名（由 `--dry-run` 逐个打印，可与本表对照），
右侧是 `schema\\六张表.sql` 里的列名（逐字对齐《10》第4.4.1节 表 4-6）。

【A】documents.jsonl → `document`

  源字段            → 目标列                 转换与说明
  doc_id            → document.doc_id        直取（1001…4020）
  title             → document.title         直取
  content           → document.content       直取（LONGTEXT）
  source            → document.source        直取（巨潮资讯网／中证网／……）
  url               → document.url           直取（可空列；上游 709 行均非空）
  publish_time      → document.publish_time  "2026-09-25" → DATETIME（补 00:00:00）
  ingest_time       → document.ingest_time   "2026-09-25T21:19:14+08:00" → 剥时区偏移
  ingest_time       → document.create_time   **上游无 create_time 字段**：按「导入即建记录」
                                             以入库时间作为记录创建时间（见 §三 决策 2）
  category          → document.category      直取（公告／财经新闻／政策文件／监管公开信息）
  company_list      → document.company_list  数组 → 英文逗号连接（["601633"] → "601633"）
  （未使用）content_sha256_16、subject_companies：**不落库**（表 4-6 无对应列，不新增字段）

【B】chunks.jsonl → `document_chunk`（6 列逐字直取，无转换）

  chunk_id → chunk_id ／ doc_id → doc_id ／ chunk_index → chunk_index
  content → content ／ token_count → token_count ／ vector_id → vector_id（可空列，上游均非空）

【C】qa_records.jsonl["question"] → `question`

  question_id       → question.question_id   "Q-001" → 1（**剥字母前缀取整数**，见 §三 决策 1）
  user_id           → question.user_id       直取（30 条均为 null；第一版不启用登录）
  session_id        → question.session_id    直取（30 条均为 "S-001"）
  question_text     → question.question_text 直取
  task_type         → question.task_type     直取（事实型 9／事件型 9／关系型 12）
  gold_hop_depth    → question.gold_hop_depth 直取（0／1／2）
  time_constraint   → question.time_constraint "无"→0、"有"→1（TINYINT，见 §三 决策 1）
  ask_time          → question.ask_time      剥时区偏移

【D】qa_records.jsonl["answer"] → `answer`

  answer_id         → answer.answer_id       "A-001" → 1（剥字母前缀）
  question_id       → answer.question_id     "Q-001" → 1（与 [C] 同一个值，30 条逐条相等）
  answer_text       → answer.answer_text     直取（四段答案正文，LONGTEXT）
  graph_path        → answer.graph_path      **JSON 文本原样入库**（表 4-6 为 JSON 列；
                                             30 条全部非空，is_graph_extended 全为 1）
  model_name        → answer.model_name      直取（deepseek-flash）
  prompt_version    → answer.prompt_version  直取（v1.0）
  is_graph_extended → answer.is_graph_extended 直取（0／1）
  create_time       → answer.create_time     剥时区偏移

【E】qa_records.jsonl["answer_evidence"]（每条记录一个数组）→ `answer_evidence`

  answer_id     → answer_evidence.answer_id     "A-001" → 1
  chunk_id      → answer_evidence.chunk_id      直取（整数）
  doc_id        → answer_evidence.doc_id        直取（整数）
  rank          → answer_evidence.rank          **按 qa_records 里的 rank 原样写入**
  evidence_type → answer_evidence.evidence_type 直取（公告来源 234／相关事件 53／新闻来源 6）
  联合主键 (answer_id, chunk_id)：30 条记录内无重复组合（293 行全部唯一）

【F】`user` 表

  **无来源**：第一版不启用登录，`user` 表不写入任何行（B8：`SELECT COUNT(*) FROM user` = 0）。
  表本身照建（表数量恒为六张，不采用「按条件决定是否建表」的做法，《10》第4.4.1节）。

--------------------------------------------------------------------------
二、导入顺序、幂等策略与 --limit 的引用闭包
--------------------------------------------------------------------------
* **导入顺序与外键一致**：document → document_chunk → question → answer → answer_evidence
  （父表在前；`config.IMPORT_ORDER`）。
* **幂等策略：默认走 `INSERT … ON DUPLICATE KEY UPDATE`**（task 书给出的两个选项中取此）。
  理由：① 不清表，天然可重复执行——第二次运行命中主键走 UPDATE 分支，行数与第一次完全
  一致（B5），且不会因为「源变短」而残留旧行以外的意外破坏；② 该写法命中 PyMySQL
  `executemany` 的批量插入快路（一条语句一次往返），5018 个文本块不必逐行往返；
  ③ 增量友好的代价（源若缩减则旧行仍在）由 `--reset` 覆盖，两条路径并用即可既幂等又确定。
  `--reset` 走**另一条**策略——**事务内先删后插**：按外键顺序（answer_evidence → answer →
  question → document_chunk → document）清空五张表后再插入，把库拉回干净状态，供「行数与
  上游产物逐项对拍」使用。**两条路径都是幂等的**（第二次运行行数不变）。
* **`--limit N` 的引用闭包**：限制的是 documents 与 qa_records 的条数；`document_chunk`
  取「被纳入文档的全部文本块」，`answer_evidence` 取「被纳入回答的全部证据」，并**反向补齐**
  证据引用到的文档与其文本块——否则外键不成立（`fk_ae_doc`／`fk_ae_chunk` 是 RESTRICT，
  缺父行会直接报错）。闭包只增不减，因此小样本运行仍然满足全部外键。
* **`--dry-run` 不连库**：只解析、统计与打印映射，供「小样本先行」的纪律使用。

--------------------------------------------------------------------------
三、两处**必须写明**的值域转换（上游字段名与《10》表 4-6 的类型不同）
--------------------------------------------------------------------------
决策 1（标识与 0／1 标注的落库形态）：
  * `qa_records.jsonl` 的 `question_id`／`answer_id` 是**带字母前缀的字符串**（"Q-001"／
    "A-001"），而表 4-6 把 `question.question_id`／`answer.answer_id`／
    `answer_evidence.answer_id` 定为 **BIGINT**。本脚本按**确定性规则**剥去前缀字母取整数
    （"Q-001" → 1、"A-030" → 30），**不引入映射表、不新增列**（硬约束 3：不新增字段）。
    该转换是**可逆**的（`Q-%03d`／`A-%03d`），下游接口层若要回 `A-001` 形式，按同一规则还原。
  * `question.time_constraint` 上游取值为 "无"／"有" 两个中文串，表 4-6 定为 **TINYINT**
    （0／1）。按 "无"→0、"有"→1 转换；**取值域之外的任何第三种取值都会报错退出**，
    不做静默兜底。
决策 2（`document.create_time` 的取值）：
  上游 `documents.jsonl` 只有 `ingest_time`（并且 `document.ingest_time` 列已经用它），
  表 4-6 另有 NOT NULL 的 `create_time`（"记录创建时间"）。本脚本以 **ingest_time** 作为
  `create_time`——导入动作即建记录，两者同值；**不新增列、不填 NULL**（列不可空）。
  该选择只影响「记录创建时间」这一运维属性，不影响任何检索、证据或相对时间口径
  （《10》第4.4.5节：publish_time／ingest_time 都不是相对时间的判定依据）。

--------------------------------------------------------------------------
四、CLI
--------------------------------------------------------------------------
    python 代码\\后端\\tools\\import_data.py --dry-run        # 只解析与统计，不连库
    python 代码\\后端\\tools\\import_data.py --limit 100      # 小样本真写（upsert）
    python 代码\\后端\\tools\\import_data.py --reset          # 清空五表后全量重导
    python 代码\\后端\\tools\\import_data.py                  # 全量 upsert

结束时打印六张表行数与「与上游产物对拍」的结果；**不一致即非零退出**。
结果写入 `交付物/05-系统实现/前后端系统集成\\集成产出\\db_counts.json`（`--dry-run` 不写）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # 交付物/03-代码\后端

import config  # noqa: E402  （路径注入后再导入）

# --------------------------------------------------------------------------
# 列清单（与 schema\六张表.sql 逐字一致）
# --------------------------------------------------------------------------
DOC_COLS = ["doc_id", "title", "content", "source", "url", "publish_time",
            "ingest_time", "category", "company_list", "create_time"]
CHUNK_COLS = ["chunk_id", "doc_id", "chunk_index", "content", "token_count", "vector_id"]
QUESTION_COLS = ["question_id", "user_id", "session_id", "question_text", "task_type",
                 "gold_hop_depth", "time_constraint", "ask_time"]
ANSWER_COLS = ["answer_id", "question_id", "answer_text", "graph_path", "model_name",
               "prompt_version", "is_graph_extended", "create_time"]
EVIDENCE_COLS = ["answer_id", "chunk_id", "doc_id", "rank", "evidence_type"]

PRIMARY_KEYS = {
    "document": ["doc_id"],
    "document_chunk": ["chunk_id"],
    "question": ["question_id"],
    "answer": ["answer_id"],
    "answer_evidence": ["answer_id", "chunk_id"],
}

# 清空顺序（外键安全的 child → parent；`user` 表不在其中，全程不写不删）
CLEAR_ORDER = ["answer_evidence", "answer", "question", "document_chunk", "document"]

# VARCHAR／CHAR 列的长度上限（照 schema\六张表.sql；越界即报错，不静默截断）
MAX_LEN = {
    "document": {"title": 512, "source": 128, "url": 1024, "category": 64, "company_list": 512},
    "question": {"session_id": 36, "task_type": 16},
    "answer": {"model_name": 128, "prompt_version": 16},
    "answer_evidence": {"evidence_type": 32},
}

TIME_CONSTRAINT_MAP = {"无": 0, "有": 1}


# --------------------------------------------------------------------------
# 1. 值域转换
# --------------------------------------------------------------------------
def to_int_id(value, where: str) -> int:
    """标识别名的确定性转换：整数直取；"Q-001"／"A-001" 剥前缀取整数。

    剥不出数字（如 "Q-CUSTOM"）即报错退出——**不猜、不兜底**（该情形不在本批 30 条内）。
    """
    if isinstance(value, bool):
        raise SystemExit("%s：标识字段收到布尔值 %r，不符合预期。" % (where, value))
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    digits = ""
    for ch in text:
        if ch.isdigit():
            digits += ch
        elif digits:
            break
    if not digits:
        raise SystemExit("%s：无法从 %r 解析出整数标识（本批数据应为 Q-001／A-001 形式）。"
                         % (where, value))
    return int(digits)


def to_datetime(value, where: str):
    """ISO 8601 字符串 → `datetime`（DATETIME 列不能存时区，故剥掉偏移存墙上时间）。

    第三／四节口径：《24》第六节 格式决策 4 要求**接口响应**的时间字段为 ISO 8601 且
    `data_cutoff_time` 保留 `+08:00`；而 MySQL 的 DATETIME 列不存时区，故列内保存
    `+08:00` 对应的墙上时间（与上游字符串去掉偏移后的字面值一致，逐字可核）。
    """
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        dt = _dt.datetime.fromisoformat(text)
    except ValueError:
        raise SystemExit("%s：无法解析为时间（收到 %r）。" % (where, value))
    return dt.replace(tzinfo=None)


def to_time_constraint(value, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int) and value in (0, 1):
        return value
    text = str(value).strip()
    if text in TIME_CONSTRAINT_MAP:
        return TIME_CONSTRAINT_MAP[text]
    try:
        num = int(text)
    except ValueError:
        raise SystemExit("%s：time_constraint 取值 %r 不在映射域 %s 内，不做静默兜底。"
                         % (where, value, TIME_CONSTRAINT_MAP))
    if num in (0, 1):
        return num
    raise SystemExit("%s：time_constraint 整数取值 %r 不在 {0,1} 内。" % (where, value))


def company_list_to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, (list, tuple)):
        return ",".join(str(x) for x in value) or None
    return str(value)


def to_tinyint(value, where: str) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise SystemExit("%s：无法把 %r 转成 0／1。" % (where, value))


# --------------------------------------------------------------------------
# 2. 读来源、构造行（含 --limit 的引用闭包）
# --------------------------------------------------------------------------
class Batch:
    """一次导入的全部行（已按目标表列序整理好，写库阶段只管写）。"""

    def __init__(self):
        self.documents = []          # [(col…), …]
        self.chunks = []
        self.questions = []
        self.answers = []
        self.evidence = []
        self.source_counts = {}
        self.closure_added = {"documents": 0, "chunks": 0}
        self.field_names = {}

    def counts(self) -> dict:
        return {"document": len(self.documents), "document_chunk": len(self.chunks),
                "question": len(self.questions), "answer": len(self.answers),
                "answer_evidence": len(self.evidence), "user": 0}


def collect(limit: int | None) -> Batch:
    """读三份上游产物并映射成六表行（**只读，不连库**）。"""
    docs_all = list(config.iter_jsonl(config.DOCUMENTS_JSONL))
    chunks_all = list(config.iter_jsonl(config.CHUNKS_JSONL))
    records_all = list(config.iter_jsonl(config.QA_RECORDS_JSONL))

    b = Batch()
    b.source_counts = {"documents": len(docs_all), "chunks": len(chunks_all),
                       "qa_records": len(records_all)}

    # 字段名清单：按真实数据取（前 30 行求并集，避免只看到第一行的字段）
    b.field_names = {
        "documents": sorted({k for row in docs_all[:30] for k in row}),
        "chunks": sorted({k for row in chunks_all[:30] for k in row}),
        "qa_records_top": sorted({k for row in records_all[:30] for k in row}),
        "qa_records.question": sorted({k for row in records_all[:30] for k in row["question"]}),
        "qa_records.answer": sorted({k for row in records_all[:30] for k in row["answer"]}),
        "qa_records.answer_evidence": sorted(
            {k for row in records_all[:30] for item in row["answer_evidence"] for k in item}),
    }

    docs = docs_all[:limit] if limit else docs_all
    records = records_all[:limit] if limit else records_all

    # —— 引用闭包：证据指向的文档与其全部文本块必须纳入（否则 RESTRICT 外键不成立）——
    base_doc_ids = {d["doc_id"] for d in docs}
    evidence_src = [item for record in records for item in record["answer_evidence"]]
    doc_ids = base_doc_ids | {e["doc_id"] for e in evidence_src}
    by_doc = {}
    for c in chunks_all:
        by_doc.setdefault(c["doc_id"], []).append(c)

    docs = [d for d in docs_all if d["doc_id"] in doc_ids]          # 补齐被证据引用的文档
    chunks = [c for doc in doc_ids for c in by_doc.get(doc, [])]    # 这些文档的全部文本块

    chunk_ids = {c["chunk_id"] for c in chunks}
    missing = {e["chunk_id"] for e in evidence_src} - chunk_ids
    if missing:
        chunks += [c for c in chunks_all if c["chunk_id"] in missing]
        chunk_ids |= missing
    b.closure_added = {"documents": len(doc_ids) - len(base_doc_ids),
                       "chunks": len(chunks)}

    # —— A. document ——
    for d in docs:
        ingest = to_datetime(d.get("ingest_time"), "documents.ingest_time")
        b.documents.append((
            int(d["doc_id"]),
            d["title"],
            d["content"],
            d["source"],
            d.get("url"),
            to_datetime(d.get("publish_time"), "documents.publish_time"),
            ingest,
            d.get("category"),
            company_list_to_text(d.get("company_list")),
            ingest,                       # create_time ← ingest_time（§三 决策 2）
        ))

    # —— B. document_chunk ——
    for c in chunks:
        b.chunks.append((
            int(c["chunk_id"]), int(c["doc_id"]), int(c["chunk_index"]),
            c["content"], int(c["token_count"]),
            None if c.get("vector_id") is None else int(c["vector_id"]),
        ))

    # —— C／D／E. question／answer／answer_evidence ——
    for record in records:
        q, a = record["question"], record["answer"]
        qid_src = q.get("question_id")
        aid_src = a.get("answer_id")
        qid = to_int_id(qid_src, "question.question_id(%r)" % (qid_src,))
        aid = to_int_id(aid_src, "answer.answer_id(%r)" % (aid_src,))
        linked = to_int_id(a.get("question_id"), "answer.question_id(%r)" % (a.get("question_id"),))
        if linked != qid:
            raise SystemExit("问答记录内部不一致：question_id=%s 与 answer.question_id=%s 不等。"
                             % (qid_src, a.get("question_id")))

        b.questions.append((
            qid,
            None if q.get("user_id") is None else to_int_id(q["user_id"], "question.user_id"),
            q.get("session_id"),
            q["question_text"],
            q.get("task_type"),
            None if q.get("gold_hop_depth") is None
            else int(q["gold_hop_depth"]),
            to_time_constraint(q.get("time_constraint"), "question.time_constraint"),
            to_datetime(q.get("ask_time"), "question.ask_time"),
        ))
        b.answers.append((
            aid, qid, a["answer_text"],
            a.get("graph_path"),                    # JSON 文本原样入库
            a["model_name"], a["prompt_version"],
            to_tinyint(a.get("is_graph_extended"), "answer.is_graph_extended"),
            to_datetime(a.get("create_time"), "answer.create_time"),
        ))
        for item in record["answer_evidence"]:
            b.evidence.append((
                to_int_id(item.get("answer_id"), "answer_evidence.answer_id(%r)"
                          % (item.get("answer_id"),)),
                int(item["chunk_id"]), int(item["doc_id"]),
                int(item["rank"]),                      # 原样写入
                item["evidence_type"],
            ))

    _check_lengths(b)
    _check_references(b)
    return b


def _check_lengths(b: Batch) -> None:
    """列长越界即报错（不静默截断——截断会破坏「逐字一致」）。"""
    tables = {"document": (DOC_COLS, b.documents), "question": (QUESTION_COLS, b.questions),
              "answer": (ANSWER_COLS, b.answers),
              "answer_evidence": (EVIDENCE_COLS, b.evidence)}
    for table, (cols, rows) in tables.items():
        limits = MAX_LEN.get(table, {})
        for row in rows:
            for col, value in zip(cols, row):
                if col in limits and isinstance(value, str) and len(value) > limits[col]:
                    raise SystemExit("%s.%s 超长：%d > %d（不静默截断）。"
                                     % (table, col, len(value), limits[col]))


def _check_references(b: Batch) -> None:
    """写库前的引用完整性预检（与数据库外键同一判据，失败即报错、不做部分导入）。"""
    doc_ids = {row[0] for row in b.documents}
    chunk_ids = {row[0] for row in b.chunks}
    q_ids = {row[0] for row in b.questions}
    a_ids = {row[0] for row in b.answers}
    problems = []
    for row in b.chunks:
        if row[1] not in doc_ids:
            problems.append("document_chunk.chunk_id=%s 的 doc_id=%s 不在本批 document 内" % (row[0], row[1]))
    for row in b.answers:
        if row[1] not in q_ids:
            problems.append("answer.answer_id=%s 的 question_id=%s 不在本批 question 内" % (row[0], row[1]))
    for row in b.evidence:
        if row[0] not in a_ids:
            problems.append("answer_evidence.answer_id=%s 不在本批 answer 内" % row[0])
        if row[1] not in chunk_ids:
            problems.append("answer_evidence.chunk_id=%s 不在本批 document_chunk 内" % row[1])
        if row[2] not in doc_ids:
            problems.append("answer_evidence.doc_id=%s 不在本批 document 内" % row[2])
    if problems:
        raise SystemExit("引用完整性预检失败（%d 处）：\n  - %s"
                         % (len(problems), "\n  - ".join(problems[:20])))
    combos = [(r[0], r[1]) for r in b.evidence]
    if len(set(combos)) != len(combos):
        raise SystemExit("answer_evidence 的 (answer_id, chunk_id) 出现重复——"
                         "与联合主键「同一答案下同一文本块只算一个证据」冲突。")


# --------------------------------------------------------------------------
# 3. 写库
# --------------------------------------------------------------------------
def upsert_sql(table: str, cols: list) -> str:
    """`INSERT … ON DUPLICATE KEY UPDATE`（幂等默认路径；命中 PyMySQL 批量快路）。"""
    collist = ", ".join("`%s`" % c for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    updates = ", ".join("`%s`=VALUES(`%s`)" % (c, c)
                        for c in cols if c not in PRIMARY_KEYS[table])
    return "INSERT INTO `%s` (%s) VALUES (%s) ON DUPLICATE KEY UPDATE %s" % (
        table, collist, placeholders, updates)


def insert_sql(table: str, cols: list) -> str:
    collist = ", ".join("`%s`" % c for c in cols)
    placeholders = ", ".join(["%s"] * len(cols))
    return "INSERT INTO `%s` (%s) VALUES (%s)" % (table, collist, placeholders)


def write_batch(b: Batch, reset: bool, verbose: bool = True) -> dict:
    """把整批行写进库（**单事务**）：`--reset` 先按外键顺序清空五表，否则走 upsert。"""
    import db                                            # 延迟导入：--dry-run 不需要 pymysql

    if verbose:
        print("\n[写库] 目标库 %s（字符集 %s）" % (config.db_database(), config.db_charset()))
    created = db.ensure_database()
    if verbose:
        print("[写库] 建库 %s：完成（IF NOT EXISTS，幂等）" % created)
    n_stmt = db.init_schema()
    if verbose:
        print("[写库] 建表：执行 %d 条 DDL（schema\\六张表.sql，全部 IF NOT EXISTS）" % n_stmt)

    conn = db.get_conn()
    conn.begin()
    try:
        if reset:
            if verbose:
                print("[写库] --reset：按外键顺序清空五张表（user 不动）→ %s" % " → ".join(CLEAR_ORDER))
            with db.cursor(conn=conn) as cur:
                for table in CLEAR_ORDER:
                    cur.execute("DELETE FROM `%s`" % table)
        with db.cursor(conn=conn) as cur:
            pairs = [("document", DOC_COLS, b.documents, upsert_sql if not reset else insert_sql),
                     ("document_chunk", CHUNK_COLS, b.chunks, upsert_sql if not reset else insert_sql),
                     ("question", QUESTION_COLS, b.questions, upsert_sql if not reset else insert_sql),
                     ("answer", ANSWER_COLS, b.answers, upsert_sql if not reset else insert_sql),
                     ("answer_evidence", EVIDENCE_COLS, b.evidence,
                      upsert_sql if not reset else insert_sql)]
            written = {}
            for table, cols, rows, builder in pairs:
                sql = builder(table, cols)
                if rows:
                    cur.executemany(sql, rows)
                written[table] = len(rows)
                if verbose:
                    print("[写库] %-16s 写入 %5d 行" % (table, len(rows)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return written


# --------------------------------------------------------------------------
# 4. 对拍与留痕
# --------------------------------------------------------------------------
def compare(counts: dict, full: bool) -> tuple:
    """与上游产物对拍。返回 `(明细, 是否全部一致)`。"""
    detail = {}
    ok = True
    for table, expected in config.EXPECTED_COUNTS.items():
        got = int(counts.get(table, -1))
        good = (got == expected) if full else True
        detail[table] = {"db": got, "expected": expected if full else None, "match": good}
        if full and not good:
            ok = False
    return detail, ok


def write_db_counts(b: Batch, counts: dict, detail: dict, all_match: bool, full: bool,
                    limit: int | None, reset: bool) -> str:
    """写 `交付物/05-系统实现/前后端系统集成\\集成产出\\db_counts.json`（固定字段 ＋ 运行时间戳）。"""
    inputs = {}
    for name, path in (("documents", config.DOCUMENTS_JSONL),
                       ("chunks", config.CHUNKS_JSONL),
                       ("qa_records", config.QA_RECORDS_JSONL),
                       ("dataset_meta", config.DATASET_META_PATH)):
        inputs[name] = {"path": os.path.relpath(path, config.ROOT),
                        "bytes": os.path.getsize(path),
                        "sha256": config.sha256_file(path),
                        "rows": (config.count_jsonl(path)
                                 if path.endswith(".jsonl") else None)}
    payload = {
        "stage": "第 9 阶段（前后端系统集成）",
        "task": "T2 数据库落地与导入",
        "database": config.db_database(),
        "charset": config.db_charset(),
        "tables": config.TABLES,
        "table_count": len(config.TABLES),
        "counts": {t: int(counts.get(t, 0)) for t in config.TABLES},
        "comparison": detail,
        "all_match": bool(all_match),
        "comparison_basis": ("全量：与上游产物登记行数逐项对拍" if full
                            else "小样本（--limit %s）：对拍基准＝本批来源行数" % limit),
        "mode": "full" if full else "limit",
        "limit": limit,
        "strategy": ("reset-delete-then-insert" if reset else "upsert-on-duplicate-key"),
        "user_rows": 0,
        "user_empty_basis": "第一版不启用登录；user 表不写入任何行（B8）",
        "source_counts": b.source_counts,
        "input_fields": b.field_names,
        "inputs": inputs,
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    path = os.path.join(config.OUTPUT_DIR, "db_counts.json")
    config.write_json(path, payload)
    return path


# --------------------------------------------------------------------------
# 5. 主流程
# --------------------------------------------------------------------------
def print_batch_stats(b: Batch, limit: int | None) -> None:
    print("=" * 74)
    print("导入解析结果（本阶段只读来源、未连库）")
    print("=" * 74)
    print("--- 三份输入的行数与真实字段名（映射表按这些字段写，不凭猜）---")
    print("  documents.jsonl     行数=%-5d 字段=%s"
          % (b.source_counts["documents"], "、".join(b.field_names["documents"])))
    print("  chunks.jsonl        行数=%-5d 字段=%s"
          % (b.source_counts["chunks"], "、".join(b.field_names["chunks"])))
    print("  qa_records.jsonl    行数=%-5d 顶层键=%s"
          % (b.source_counts["qa_records"], "、".join(b.field_names["qa_records_top"])))
    print("    · question        字段=%s" % "、".join(b.field_names["qa_records.question"]))
    print("    · answer          字段=%s" % "、".join(b.field_names["qa_records.answer"]))
    print("    · answer_evidence 字段=%s" % "、".join(b.field_names["qa_records.answer_evidence"]))
    print("  meta\\dataset.json   dataset_version=%s  data_cutoff_time=%s"
          % (config.dataset_meta()["dataset_version"], config.dataset_meta()["data_cutoff_time"]))
    print()
    print("--- 本批计划写入的行数（--limit %s 下的引用闭包：证据指向的文档与文本块一并纳入）---"
          % ("无" if not limit else limit))
    for table in config.IMPORT_ORDER:
        print("  %-16s %5d 行" % (table, b.counts()[table]))
    print("  %-16s %5d 行（不写入任何行；第一版不启用登录）" % ("user", 0))
    if limit:
        print("  其中引用闭包补入的 document 数 = %d（证据指向、但不在前 %d 篇内的文档）"
              % (b.closure_added["documents"], limit))
        print("  被纳入文档的全部文本块 = %d 行（外键 fk_chunk_doc 要求父行齐备）"
              % b.closure_added["chunks"])
    print()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 9 阶段 T2：数据集 v2.1 与 qa_records.jsonl 导入 MySQL 六张表（幂等）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只解析与统计，不连库、不写库")
    parser.add_argument("--reset", action="store_true",
                        help="按外键顺序清空五张表后全量重导（user 不动）")
    parser.add_argument("--limit", type=int, default=None, metavar="N",
                        help="只取前 N 篇文档与前 N 条问答记录（引用闭包自动补齐）")
    args = parser.parse_args(argv)

    limit = args.limit
    if limit is not None and limit <= 0:
        print("--limit 必须是正整数（收到 %r）" % limit, file=sys.stderr)
        return 2

    b = collect(limit)
    print_batch_stats(b, limit)

    if args.dry_run:
        print("[--dry-run] 未连库、未写库；真写请去掉 --dry-run 或改用 --limit N。")
        print("=" * 74)
        return 0

    written = write_batch(b, reset=args.reset)

    import db                                             # 已在 write_batch 里导入过
    counts = db.table_counts()
    full = (limit is None)
    detail, all_match = compare(counts, full)

    print("\n--- 六张表行数（写库后实测）---")
    for table in config.TABLES:
        print("  %-16s %5d 行" % (table, counts[table]))
    print("\n--- 与上游产物对拍（基准：document 709／document_chunk 5018／question 30／"
          "answer 30／answer_evidence 293）---")
    for table in config.EXPECTED_COUNTS:
        d = detail[table]
        if full:
            print("  %-16s 库内=%-5d 上游=%-5d %s"
                  % (table, d["db"], d["expected"], "一致" if d["match"] else "**不一致**"))
        else:
            print("  %-16s 库内=%-5d 上游=%s（小样本，不参与全量对拍）"
                  % (table, d["db"], d["expected"]))
    print("  结论：%s" % ("全部一致" if all_match else "**存在不一致**"))

    path = write_db_counts(b, counts, detail, all_match, full, limit, args.reset)
    print("\n[留痕] 已写 %s" % os.path.relpath(path, config.ROOT))
    print("=" * 74)
    return 0 if all_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
