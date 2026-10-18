# -*- coding: utf-8 -*-
"""代码\\后端\\services\\qa_service.py —— 第 9 阶段（前后端系统集成）问答业务层。

本文件是接口层（`api\\qa.py`／`api\\evidence.py`／`api\\history.py`）与
「六张表 ＋ 第 8 阶段问答链路」之间的**唯一**中间层：接口层只做参数校验与响应封装，
一切取数、落库、链路调用都在这里。

第一纪律：**复用，不复制**（《24》第五节 硬约束 15）
---------------------------------------------------
问答链路（检索 → 证据组装 → 生成 → 三段汇编）**一个字节都不重写**，一律走第 8 阶段的
入口脚本：

    python 代码\\问答\\run_answer.py --question "<原文>" --group <G> --now <ISO>
           --session-id <SID> --out-dir <临时目录>

（该脚本**只读**，本阶段不得修改。）链路把本次运行的全部产物写进 `--out-dir`：

* `qa_records.jsonl` —— 本次问答记录（question／answer／answer_evidence 三个字典），
  本文件据此落库并组装接口载荷；
* `answer_trace.jsonl` —— 检索与生成的逐跳轨迹（只用于日志与排障，不进响应体）。

失败归类（《24》第五节的错误码纪律；**评审 P1-9 已把判据换成结构化契约**）
----------------------------------------------------------------------------
* 子进程**超时**（阈值取 `config.ANSWER["timeout_seconds"]`，配置唯一来源）→ `ApiError(3002)`；
* 子进程**非零退出** → **先读上游落在 `--out-dir\\error_contract.json` 的结构化失败契约**
  （由 `run_answer.py` 以 `SystemExit` 退出前写盘，`error_code` 取值出自 `errors.CODES`），
  契约有效即以它为准、**一条日志文本都不看**；**只有契约缺失／不可解析时**才回落到
  `_classify_failure()` 原有的中文措辞匹配，并在回落时打一条 **WARNING**（不静默）。
* 子进程**退出码为 0 但没有产物** → 3003（链路没跑完，按不可用处理）。
三类都把 stdout／stderr 摘要写**日志**，**绝不进响应体**（硬约束 7）。

会话与幂等（硬约束 6／接口纪律）
---------------------------------
* `session_id` **一律按调用方传入的值**使用（第一版由前端生成 UUID）——
  **不得**用第 8 阶段脚本里的默认值 `S-001` 覆盖；
* 同一 `(session_id, question_text)` 重复提问复用同一对 `question_id`／`answer_id`，
  写入全部按主键 upsert（`ON DUPLICATE KEY UPDATE`），不产生重复行；
* `answer_evidence` 先按 `answer_id` 删旧再插新（同一事务内），避免残留过期证据行；
* `` `rank` `` 是 MySQL 8 的关键字，SQL 里一律反引号包裹。

ID 分配
-------
第 8 阶段的字符串 ID（`Q-001`／`A-001`，自定义问题则是 `Q-CUSTOM`／`A-CUSTOM`）无法
直连 BIGINT 列，故本层**自行分配整数 ID**：取 `GREATEST(MAX(question_id), MAX(answer_id)) + 1`，
保证已导入的 1～30 号记录永不被覆盖。

并发
----
`db.py` 的连接是**进程内单例**，PyMySQL 连接不是线程安全的。本模块所有取数／落库都在
`_DB_LOCK` 内完成；接口层的长耗时动作（跑链路）通过 `asyncio.to_thread` 放到工作线程，
但进锁后立刻串行化，因此共享连接不会并发使用（登记为已知限制：多 worker 部署需先换连接池）。
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime

import config
import db
import errors
import observability
from errors import ApiError

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger

# --------------------------------------------------------------------------
# 0. 路径与常量（**全部取自 config，不写死取值**）
# --------------------------------------------------------------------------
RUN_ANSWER_SCRIPT = os.path.join(config.ROOT, "交付物/03-代码", "问答", "run_answer.py")
"""第 8 阶段问答入口（**只读**）。"""

RUN_DIR = os.path.join(config.WORK_DIR, "qa_runs")
"""临时运行目录的父目录（每次提问一个子目录，留痕便于排障；不入库）。"""

CHAIN_TIMEOUT_SECONDS = int(config.ANSWER["timeout_seconds"])
"""链路超时阈值：取自生成侧 `ANSWER["timeout_seconds"]`（配置唯一来源，硬约束 1）。"""

DEFAULT_GROUP = config.DEFAULT_GROUP or "C"
"""默认实验组：取自检索侧 `config.DEFAULT_GROUP`（当前 = C，即 graph_depth=2）。"""

TASK_TYPES = ("事实型", "事件型", "关系型")
"""测试集标注的三种题型（`question.task_type`）。"""

ANSWER_TYPE_FALLBACK = "未标注"
"""非测试集题目（题集里查不到）的 `answer_type` 取值。

《24》要求：非测试集题目给一个**合理且不是「事实型」**的默认值并登记。
取「未标注」的理由：它是**如实的缺省**——链路确实没有这道题的题型标注，
不猜「事件型／关系型」以免把无标注当成有标注（该取值在《25-文档更新登记》里登记）。
"""

TIME_SECTION_HEADER = "【数据截至与判定区间】"
"""答案末段的段落头（字面量取自第 8 阶段 `代码\\问答\\prompt.py` 的 `ANSWER_SECTIONS`）。

`time_interpretation` 只能从这一段里**照抄**，不得自行推算判定区间。
"""

SUMMARY_LIMIT = 100
"""历史列表里 `answer_summary` 的截断长度（字符）。"""

NEIGHBOR_RADIUS = 2
"""`GET /api/documents/{doc_id}/chunks/{chunk_id}` 的相邻块半径（前后各 2 块）。"""

CONTRACT_FILENAME = "error_contract.json"
"""上游第 8 阶段 `run_answer.py` 落下的**失败契约**文件名（评审 P1-9）。

契约放在调用方传进去的 `--out-dir` 下，故本层无需新增任何约定参数即可读到它。
契约的 `error_code` 取值一律来自 `errors.CODES`；本层**先读契约，读不到才回落措辞匹配**。
"""

EVIDENCE_TYPES = ("回答来源", "新闻来源", "公告来源", "相关事件")
"""`answer_evidence.evidence_type` 的四个取值（表 4-6 规定）。"""

# 共享连接串行化（见模块 docstring「并发」一节）
_DB_LOCK = threading.RLock()

# 问答链路的**重资源串行锁**（2026-10-18 全面审查 A5 新增）。
# 实测：3 条并发 `POST /api/qa/ask` 会把页面文件打满——每个子进程都要加载一次本地
# BGE 模型（`AutoModel.from_pretrained`），第三个直接 `OSError: 页面文件太小（1455）`，
# 三条请求全部 500。单机演示形态下按「同一时刻只跑一条链路」串行化，其余请求排队；
# 每条链路各自仍有 `config.ANSWER["timeout_seconds"]` 的超时上限。
_ASK_LOCK = threading.Lock()


def _fresh_conn():
    """取共享连接，并**结束其隐式长事务**，让下一次读取到新鲜快照。

    `db.py` 的连接是 `autocommit=False` 的进程内单例；MySQL 在 REPEATABLE READ 下于
    **首次一致读**处取快照并保持到事务结束——于是「服务启动之后由别的进程写入的行」
    （如 `tools\\import_data.py` 的导入）在本连接里**读不到**，接口就会回陈旧数据。
    每次读操作前先 `commit()` 结束隐式事务即可（连接空闲时它不改变任何数据）；
    写路径自己会 `begin()`（同样隐式结束上一个事务）。**不改 `db.py`**，在本层收口。
    """
    conn = db.get_conn()
    with contextlib.suppress(Exception):
        conn.commit()
    return conn

_SQL_QUESTION_UPSERT = (
    "INSERT INTO question (question_id, user_id, session_id, question_text, "
    "task_type, gold_hop_depth, time_constraint, ask_time) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE session_id=VALUES(session_id), "
    "question_text=VALUES(question_text), task_type=VALUES(task_type), "
    "gold_hop_depth=VALUES(gold_hop_depth), time_constraint=VALUES(time_constraint), "
    "ask_time=VALUES(ask_time)"
)

_SQL_ANSWER_UPSERT = (
    "INSERT INTO answer (answer_id, question_id, answer_text, graph_path, model_name, "
    "prompt_version, is_graph_extended, create_time) "
    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
    "ON DUPLICATE KEY UPDATE question_id=VALUES(question_id), "
    "answer_text=VALUES(answer_text), graph_path=VALUES(graph_path), "
    "model_name=VALUES(model_name), prompt_version=VALUES(prompt_version), "
    "is_graph_extended=VALUES(is_graph_extended), create_time=VALUES(create_time)"
)

_SQL_EVIDENCE_INSERT = (
    "INSERT INTO answer_evidence (answer_id, chunk_id, doc_id, `rank`, evidence_type) "
    "VALUES (%s, %s, %s, %s, %s)"
)


# --------------------------------------------------------------------------
# 1. 小工具
# --------------------------------------------------------------------------
def _iso(value) -> str | None:
    """datetime → ISO 8601 字符串（`2026-09-25T10:00:00`）；None 原样返回。

    时间一律 ISO 8601（《24》第六节 格式决策 4）。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _to_dt(text) -> datetime | None:
    """ISO 8601 文本 → `datetime`（写库用）。时区后缀在此剥离：列是 DATETIME（本地墙钟）。

    与第 9 阶段导入侧 `tools\\import_data.py` 的同一口径：`+08:00` 的**绝对时刻**保留为
    本地墙钟；`data_cutoff_time` 本身在响应里**原样带 `+08:00`**（不经过本函数）。
    """
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.replace(tzinfo=None)
    text = str(text).strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        raise
    return parsed.replace(tzinfo=None)


def _to_int_id(value):
    """把上游的 `Q-001`／`A-001` 一类标识折成整数；折不出返回 None。"""
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else None


def _time_constraint_flag(raw):
    """`time_constraint` 的「有／无（或 1／0）」→ TINYINT 0／1；未标注返回 None。"""
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return 1 if raw else 0
    if isinstance(raw, (int, float)):
        return int(raw)
    text = str(raw).strip()
    if text in ("有", "是", "True", "true", "1"):
        return 1
    if text in ("无", "否", "False", "false", "0"):
        return 0
    logger.warning("question.time_constraint 取值无法识别：%r → 按未标注（NULL）处理", raw)
    return None


def _first_jsonl(path: str):
    """读 JSONL 的第一条非空记录；文件不存在或为空返回 None。"""
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                return json.loads(line)
    return None


def _summary(answer_text) -> str:
    """`answer_summary`：取【回答】段正文、压空白、截断到 `SUMMARY_LIMIT` 字。"""
    text = str(answer_text or "")
    head = text.split("【", 1)[0] if text.startswith("【") else text
    head = " ".join(head.split())
    if not head:
        head = " ".join(text.split())
    return head[:SUMMARY_LIMIT] + ("……" if len(head) > SUMMARY_LIMIT else "")


# --------------------------------------------------------------------------
# 2. 链路调用（复用第 8 阶段入口，不重写检索与生成）
# --------------------------------------------------------------------------
def read_error_contract(out_dir: str) -> dict | None:
    """读上游 `run_answer.py` 落下的失败契约 `<out_dir>\\error_contract.json`。

    返回 `{"error_code","reason","schema","extra"}`（**已按 `errors.CODES` 校验**）或 `None`。
    `None` 有三种情况，调用方只需知道"没有可用的结构化契约"：
    ① 文件不存在（上游在改动前跑出的运行目录、或失败发生在落盘之前——如被杀进程）；
    ② 文件在但**读不动**（不是 UTF-8、权限不足）；
    ③ 文件能读但不是契约（JSON 坏、顶层不是对象、`error_code` 不是整数、**码不在 `errors.CODES` 里**）。

    第 ③ 种最要紧：**不认识的码一律当"没有契约"处理**，绝不把上游写错的一个数字透传给响应体
    （`ApiError` 对未登记码会告警并按 9999 取 message／http，但响应体里仍回那个码——那等于把
    "上游写错"变成一个凭空出现的错误码）。宁可回落到措辞匹配，也不引入未登记码。
    """
    path = os.path.join(str(out_dir or ""), CONTRACT_FILENAME)
    if not out_dir or not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        logger.warning("失败契约存在但读不动（%s：%s）——按「契约缺失」处理，回落措辞匹配。",
                       type(exc).__name__, exc)
        return None
    if not isinstance(payload, dict):
        return None
    try:
        code = int(payload.get("error_code"))
    except (TypeError, ValueError):
        return None
    if code not in errors.CODES:
        logger.warning("失败契约里的 error_code=%r 不在 errors.CODES 里（上游写错？）——"
                       "按「契约缺失」处理，回落措辞匹配，不透传未登记的码。", payload.get("error_code"))
        return None
    return {"error_code": code, "reason": payload.get("reason"),
            "schema": payload.get("schema"), "extra": payload.get("extra")}


def _classify_failure(text: str, contract_path: str | None = None,
                      exit_code=None, out_dir: str | None = None) -> int:
    """子进程非零退出时定错误码。**先读结构化契约，契约不可用时才回落措辞匹配（并告警）。**

    判定顺序（评审 P1-9 落地后的口径）
    ----------------------------------
    ① **结构化契约优先**：读 `<out_dir>\\error_contract.json`（由上游第 8 阶段的
       `run_answer.py` 在每次以 `SystemExit` 退出前落盘，判据全是结构化字段、**不含任何措辞**）。
       契约有效即以它为准，**一条日志文本都不看**；命中时会记一条 INFO 说明码的来源。
    ② **契约缺失／不可解析时才回落**到本函数原有的中文措辞匹配（守卫 → 索引 → 图谱 → 模型），
       并在**回落时打一条 WARNING**（"回落到措辞匹配"）——**不静默**。回落分支的判据与取值
       **一个字节都没改**（`test_d_backend_errors.py` 的 D5／D6／D7 逐条钉住的正是它）。

    两种入口都能用：
    * `_classify_failure(日志文本)`（既有调用形态，等同于"契约缺失"）；
    * `_classify_failure(日志文本, contract_path=…, exit_code=…, out_dir=…)`（`_run_chain` 用）。

    回落时的判定顺序（**不变**）：**先判守卫，再判索引／图谱，最后判模型侧**。

    * `3004` 上游第 8 阶段的「装配账目守卫」——它既不是图谱故障也不是模型故障，故先认这一条
      （2026-09-30 实测 PE-03 落在这条上，早期版本会被误标成 3001）。
    * `3003` 向量索引不可用；`3001` 图谱服务不可用。
    * `3002` 模型侧失败（超时／连接失败）——2026-10-04 口径切换复测时新认的一条。

    **2026-10-04 修掉一处真缺陷（同一天在第 9 阶段门禁上实测到）**：原判据的 `graph_marks`
    里有一个**裸词 `"图谱"`**，而第 8 阶段的每次失败都会在日志尾部打印装配状态行
    `[生成] PE-0x … 图谱段BAD …`——它**含"图谱"二字**，于是**任何**模型侧失败都会被判成
    `3001（图谱服务不可用）`。后果不只是报错串不准：第 9 阶段门禁把 `3001` 与 `3004` 一起
    当成「上游守卫码、本轮跳过该题」，**一整类真故障因此被静默跳过**——2026-10-04 实测到
    答案生成侧到 `api.deepseek.com` 的 HTTPS 连接整段失败（`URLError: SSL:
    UNEXPECTED_EOF_WHILE_READING`）时，D1 逐题打印「HTTP 503 code=3001：本轮跳过（上游守卫）」，
    D2 直接记 UNRUN，**没有一个字提到模型侧失败**。故：
    ① `graph_marks` 收窄为**具体的传输／服务标识**（不再用裸词"图谱"）；
    ② 新增 `model_marks` 分支返回 **3002**——该码早已登记在 `errors.py` 的 `CODES` 里
       （"大模型接口超时"，HTTP 504）却**从未被返回过**，是一枚死码，此处正好启用；
    ③ 兜底由 `3001` 改为 **9999（未归类）**：判不出类别时如实说"不知道"，而不是替图谱认领故障。

    **2026-10-07（评审 P1-9）**：① 的结构化契约上线后，上面这批措辞判据**只在回落路径**生效；
    正常路径（上游正常落盘契约）由 `error_contract.json` 直接给码。
    """
    out_dir = out_dir or (os.path.dirname(contract_path) if contract_path else None)
    contract = read_error_contract(out_dir) if out_dir else None
    if contract is not None:
        logger.info("问答链路错误码取自上游结构化契约（非措辞匹配）：error_code=%s reason=%s "
                    "exit=%s out_dir=%s", contract["error_code"], contract.get("reason"),
                    exit_code, out_dir)
        return int(contract["error_code"])

    logger.warning("上游未提供可用的失败契约（out_dir=%s）——**回落到措辞匹配**判定错误码"
                   "（该路径依赖中文措辞，属已知技术债，评审 P1-9）；"
                   "exit=%s；日志尾部前 300 字：%s", out_dir, exit_code, (text or "")[:300])

    low = (text or "").lower()
    guard_marks = ("token 账现场重算与上游 trace 不一致", "预算守卫", "现场 text+path+event_triple")
    index_marks = ("faiss", "向量索引", "索引文件", "vector_map", "build_meta",
                   "vector index", "向量检索")
    # 收窄后的图谱标识：只认传输层／服务层的具体字样，**不再用裸词"图谱"**
    # （"图谱段BAD"是装配状态行，任何失败都会打印，不能当作图谱故障的证据）。
    graph_marks = ("neo4j", "bolt", "7687", "graphdatabase", "graphservice",
                   "图谱服务", "图谱查询层", "graphreader")
    # 模型侧：连接失败／超时／TLS 中断／显式的调用失败字样。放在图谱之后判，
    # 因为图谱侧的传输错误同样会带 "connection refused" 之类的通用字样。
    model_marks = ("urlerror", "ssl", "timed out", "timeout", "connection reset",
                   "调用失败", "大模型", "deepseek", "api.deepseek.com")
    if any(mark in low for mark in guard_marks):
        return 3004
    if any(mark in low for mark in index_marks):
        return 3003
    if any(mark in low for mark in graph_marks):
        return 3001
    if any(mark in low for mark in model_marks):
        return 3002
    logger.warning("问答链路非零退出但**未能归类**（不含守卫／索引／图谱／模型侧标记），"
                   "按 9999 未归类返回；日志尾部前 300 字：%s", (text or "")[:300])
    return 9999


def _is_citation_only_failure(contract) -> bool:
    """契约是否属于「**只**因缺引用被守卫拦下」。

    2026-10-18 全面审查 F2：`citation_missing` 表示模型没给出 `[证据n]`——对
    「没有检索价值的输入」（乱码、脚本片段、路径穿越串）这是**正常结果**，不该按
    502 报错。此类失败改判为 **2002（查询结果为空，HTTP 200）**，由前端提示
    「未检索到可引用证据」。其余失败类型（越界引用、装配账目不符等）仍是 3004。
    """
    if not contract:
        return False
    if contract.get("reason") != "answer_gate_failed":
        return False
    failures = (contract.get("extra") or {}).get("failures") or {}
    reasons = [set(v or []) for v in failures.values()]
    if not reasons or not any(reasons):
        return False                      # 空失败集不算「只有缺引用」
    return all(r and r <= {"citation_missing"} for r in reasons)


def _kill_process_tree(pid: int) -> None:
    """整树终止一个进程（S3，2026-10-11 审查）。

    * Windows：`taskkill /F /T /PID`——/T 沿父子关系杀整棵树（链路内层 fork 的
      `run_query.py` 一并终止）；
    * POSIX：子进程由 `start_new_session=True` 成为新会话／进程组长，
      `killpg(SIGKILL)` 整组终止。

    任何失败只记日志、不抛（终止路径本身已在报 3002，别让清理动作改变错误语义）。
    """
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True)
        else:
            import signal                            # noqa: PLC0415（仅 POSIX 分支需要）
            with contextlib.suppress(ProcessLookupError):
                os.killpg(os.getpgid(pid), signal.SIGKILL)
    except Exception as exc:                         # noqa: BLE001
        logger.warning("进程树终止异常（pid=%s）：%s: %s", pid, type(exc).__name__, exc)


# --------------------------------------------------------------------------
# 2.5 qa_runs 运行留痕清理（M5，2026-10-11 审查：临时目录此前只增不删）
# --------------------------------------------------------------------------
QA_RUNS_RETENTION_DAYS = int(getattr(config, "QA_RUNS_RETENTION_DAYS", 7) or 7)
"""`qa_runs` 运行目录的保留天数（取自 `config.local.json` 可选键
`qa_runs_retention_days`，缺省 7 天——运维留痕参数，不是业务口径）。"""

_RUNS_CLEANUP_INTERVAL = 24 * 3600.0
_runs_last_cleanup = 0.0


def cleanup_qa_runs(keep_days: int | None = None) -> int:
    """删除 `qa_runs` 下保留期之外的 `ask_*` 运行目录，返回删除数。

    只删本模块自己创建的 `ask_*` 前缀目录（前缀即本模块 `tempfile.mkdtemp` 的指纹）；
    任何失败只记日志、**不抛**——清理是运维动作，绝不能影响问答链路。
    """
    days = int(keep_days) if keep_days is not None else QA_RUNS_RETENTION_DAYS
    removed = 0
    try:
        if not os.path.isdir(RUN_DIR):
            return 0
        cutoff = time.time() - days * 86400.0
        with os.scandir(RUN_DIR) as entries:
            for entry in entries:
                try:
                    if not (entry.is_dir() and entry.name.startswith("ask_")):
                        continue
                    if entry.stat().st_mtime < cutoff:
                        shutil.rmtree(entry.path, ignore_errors=True)
                        removed += 1
                except OSError:
                    continue
        if removed:
            logger.info("qa_runs 清理：删除 %d 个 %d 天前的运行目录（%s）",
                        removed, days, RUN_DIR)
    except Exception as exc:                         # noqa: BLE001
        logger.warning("qa_runs 清理失败（不影响问答）：%s: %s", type(exc).__name__, exc)
    return removed


def _cleanup_qa_runs_throttled() -> None:
    """每日一次的节流清理：启动时由 main.create_app 调一次，此后由链路调用触发。"""
    global _runs_last_cleanup                        # noqa: PLW0603
    now = time.monotonic()
    if now - _runs_last_cleanup < _RUNS_CLEANUP_INTERVAL:
        return
    _runs_last_cleanup = now
    cleanup_qa_runs()


def _run_chain(question: str, group: str, session_id: str, now_iso: str) -> dict:
    """调第 8 阶段入口跑一次完整问答链路，返回 `(记录, 轨迹, 运行目录)` 三者组成的字典。

    这是**同步阻塞**调用（10～30 秒），由接口层用 `asyncio.to_thread` 放到工作线程执行，
    不阻塞事件循环。

    2026-10-11 按 S3 改用 `Popen` ＋ **进程树整杀**：链路内层还会再 fork 检索子进程
    （`run_query.py`，持 torch＋FAISS，数百 MB），原先 `subprocess.run(timeout=…)` 超时
    只杀直接子进程 `run_answer.py`，孙进程成孤儿（Windows 无进程组管控、POSIX 下也不随
    父进程退出）——反复超时即孤儿累积。现改为：Windows 下子进程以
    `CREATE_NEW_PROCESS_GROUP` 起树、超时 `taskkill /F /T` 整树终止；POSIX 下
    `start_new_session=True` 使子进程成为新会话／进程组长、超时 `killpg` 整组终止。
    """
    os.makedirs(RUN_DIR, exist_ok=True)
    _cleanup_qa_runs_throttled()                    # M5：每日节流清理过期运行目录
    out_dir = tempfile.mkdtemp(prefix="ask_%s_" % str(group), dir=RUN_DIR)
    cmd = [sys.executable, RUN_ANSWER_SCRIPT,
           "--question", question,
           "--group", str(group),
           "--now", now_iso,
           "--session-id", str(session_id),
           "--out-dir", out_dir]
    logger.info("调用第 8 阶段问答链路：group=%s session_id=%s out_dir=%s 超时=%ds",
                group, session_id, out_dir, CHAIN_TIMEOUT_SECONDS)
    started = datetime.now()
    # S3：把子进程放进独立进程组／作业树，超时才能整树终止（见函数 docstring）
    popen_kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
                    if os.name == "nt" else {"start_new_session": True})
    try:
        proc = subprocess.Popen(cmd, cwd=config.ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, encoding="utf-8",
                                errors="replace", **popen_kwargs)
    except OSError as exc:
        logger.exception("问答链路无法启动：%s", exc)
        raise ApiError(3001, detail="无法启动 %s：%s" % (RUN_ANSWER_SCRIPT, exc))
    try:
        stdout, stderr = proc.communicate(timeout=CHAIN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        # communicate 超时**不杀**进程（官方语义）；此时整棵进程树仍然存活，
        # 先整树终止再回收管道，杜绝持 torch＋FAISS 的孙进程孤儿（S3）。
        logger.warning("问答链路超时（%ds）：out_dir=%s（整树终止 pid=%s）stdout=%s stderr=%s",
                       CHAIN_TIMEOUT_SECONDS, out_dir, proc.pid,
                       _redact_question(_tail(getattr(exc, "stdout", "")), question),
                       _redact_question(_tail(getattr(exc, "stderr", "")), question))
        _kill_process_tree(proc.pid)
        with contextlib.suppress(Exception):
            proc.communicate(timeout=30)            # 回收管道与退出码（树已死，立即返回）
        raise ApiError(3002, detail="run_answer 超时 %ds（out_dir=%s）"
                       % (CHAIN_TIMEOUT_SECONDS, out_dir))
    finally:
        # 资源释放兜底（第 2 轮）：正常路径 `communicate` 已关闭管道；超时路径若第二次
        # 回收也失败，这里显式关一次，避免文件句柄滞留到 GC。重复 close 是幂等的。
        for _pipe in (getattr(proc, "stdout", None), getattr(proc, "stderr", None)):
            if _pipe is not None:
                with contextlib.suppress(Exception):
                    _pipe.close()

    elapsed = (datetime.now() - started).total_seconds()
    if proc.returncode != 0:
        # 评审 P1-9：**先读上游的结构化失败契约**（判据不含任何措辞）；
        # 契约缺失／不可解析时 _classify_failure 才回落措辞匹配，并打 WARNING（不静默）。
        contract = read_error_contract(out_dir) if out_dir else None
        # 2026-10-18 全面审查 F2：只缺引用 → 不是故障，按「查询结果为空」正常返回。
        if _is_citation_only_failure(contract):
            logger.info("问答未检索到可引用证据（装配守卫 citation_missing）：正常空结果，"
                        "按 2002 语义返回 HTTP 200；out_dir=%s 耗时=%.1fs", out_dir, elapsed)
            return {"empty": True, "empty_reason": "no_citable_evidence",
                    "out_dir": out_dir, "elapsed_seconds": round(elapsed, 1), "now": now_iso}
        code = _classify_failure((stdout or "") + "\n" + (stderr or ""),
                                 exit_code=proc.returncode, out_dir=out_dir)
        logger.warning("问答链路非零退出：exit=%s 耗时=%.1fs out_dir=%s\n--- stdout 尾部 ---\n%s"
                       "\n--- stderr 尾部 ---\n%s", proc.returncode, elapsed, out_dir,
                       _redact_question(_tail(stdout), question),
                       _redact_question(_tail(stderr), question))
        raise ApiError(code, detail="run_answer 退出码 %s（耗时 %.1fs，out_dir=%s）"
                       % (proc.returncode, elapsed, out_dir))
    logger.info("问答链路完成：耗时 %.1fs out_dir=%s", elapsed, out_dir)

    record = _first_jsonl(os.path.join(out_dir, "qa_records.jsonl"))
    if not isinstance(record, dict):
        logger.warning("问答链路未产出 qa_records.jsonl 记录：out_dir=%s stdout=%s",
                       out_dir, _redact_question(_tail(stdout), question))
        raise ApiError(3003, detail="qa_records.jsonl 无记录（out_dir=%s）" % out_dir)
    trace = _first_jsonl(os.path.join(out_dir, "answer_trace.jsonl"))

    # 第 4 轮 8.3（链路追踪）：一次问答的耗时分解只落日志，**不进响应体**。
    # 口径：backend_wait＝后端等待整条子进程链路的墙钟；llm_seconds＝answer_trace 里每次
    # 模型调用的实测秒数（含重试）；其余（检索子进程启动、向量化、图谱查询、装配、落盘）
    # 归入「链路其余部分」，可由 backend_wait − Σllm_seconds 得出。
    # 与 out_dir ＋ 请求 ID 一起即可把「后端→检索子进程→图谱→LLM」串起来；
    # **不打印问题原文、不打印 Prompt、不打印模型密钥**。
    attempts = trace.get("attempts") if isinstance(trace, dict) else None
    llm_seconds = [a.get("seconds") for a in attempts or []
                   if isinstance(a, dict) and isinstance(a.get("seconds"), (int, float))]
    logger.info("问答链路耗时分解：backend_wait=%.1fs；llm_calls=%d；llm_seconds=%s；"
                "graph_used=%s；evidence=%s；out_dir=%s",
                elapsed, len(llm_seconds), llm_seconds,
                (trace or {}).get("graph_used") if isinstance(trace, dict) else None,
                (trace or {}).get("evidence_count") if isinstance(trace, dict) else None,
                out_dir)

    return {"record": record, "trace": trace, "out_dir": out_dir,
            "elapsed_seconds": round(elapsed, 1), "now": now_iso}


def _tail(text, limit: int = 2000) -> str:
    """日志尾部摘要（**只进日志**；stdout／stderr 可能很长）。"""
    text = str(text or "")
    return text[-limit:] if len(text) > limit else text


def _redact_question(text, question: str) -> str:
    """把日志片段里出现的**问题正文**替换成摘要（长度＋SHA-256 前 12 位）。

    上游链路在失败时可能把题目原文（或含题目的 Prompt／异常栈）打到 stdout／stderr；
    本函数在写日志前统一脱敏，保证日志里不再出现完整用户问题。
    只按「原文精确匹配」替换：上游若做了 JSON 转义（\\uXXXX）则匹配不到，属已知边界，
    已在《性能与架构优化方案》里登记；不为了脱敏去改写上游输出。
    """
    body = str(text or "")
    q = str(question or "")
    if q and q in body:
        body = body.replace(q, "[问题已脱敏 %s]" % _question_digest(q))
    return body


# --------------------------------------------------------------------------
# 3. 载荷组装（字段与表 4-13 逐项对齐）
# --------------------------------------------------------------------------
def answer_type_of(task_type: object) -> str:
    """`answer_type`：取自题目集标注 `question.task_type`；无标注时用登记过的缺省值。"""
    text = str(task_type or "").strip()
    if text in TASK_TYPES:
        return text
    if text:
        return text
    return ANSWER_TYPE_FALLBACK


def time_interpretation_of(answer_text: object) -> str | None:
    """从答案的「数据截至与判定区间」段落里**照抄**判定区间。

    段落头是第 8 阶段 `prompt.py` 里的固定字面量，本函数只做切片，不重算、不臆造；
    该段缺失（例如上游改了段名）时返回 None 并记一条告警。
    """
    text = str(answer_text or "")
    index = text.find(TIME_SECTION_HEADER)
    if index < 0:
        logger.warning("答案里没有 %s 段——time_interpretation 置空（不臆造判定区间）",
                       TIME_SECTION_HEADER)
        return None
    body = text[index + len(TIME_SECTION_HEADER):].strip()
    return body or None


def _evidence_rows(answer_id: int, evidence_type: str | None = None) -> list:
    """证据明细：`answer_evidence` 关联 `document` 取元数据，按 `` `rank` `` 升序。"""
    sql = ("SELECT ae.`rank` AS `rank`, ae.chunk_id, ae.doc_id, ae.evidence_type, "
           "       d.title, d.source, d.publish_time, d.url "
           "FROM answer_evidence ae JOIN document d ON d.doc_id = ae.doc_id "
           "WHERE ae.answer_id = %s")
    args = [int(answer_id)]
    if evidence_type:
        sql += " AND ae.evidence_type = %s"
        args.append(evidence_type)
    sql += " ORDER BY ae.`rank` ASC, ae.chunk_id ASC"
    with _DB_LOCK:
        _fresh_conn()
        rows = db.query(sql, args)
    return [{"rank": int(r["rank"]), "doc_id": int(r["doc_id"]), "chunk_id": int(r["chunk_id"]),
             "evidence_type": r["evidence_type"], "title": r["title"], "source": r["source"],
             "publish_time": _iso(r["publish_time"]), "url": r["url"]} for r in rows]


def evidence_groups(items: list) -> dict:
    """把证据按四个类型计数（四类键**恒在**，没有的记 0）。"""
    groups = {name: 0 for name in EVIDENCE_TYPES}
    for item in items:
        name = item.get("evidence_type")
        groups[name] = groups.get(name, 0) + 1
    return groups


def _graph_path_of_answer(answer_id: int):
    """读 `answer.graph_path` 的**原始 JSON 文本**并解析；未使用图谱扩展时返回 (0, None)。

    硬约束 11／组 E：路径一律取自落库的原文，**不得重建或伪造**。
    """
    with _DB_LOCK:
        _fresh_conn()
        row = db.query_one("SELECT is_graph_extended, graph_path FROM answer WHERE answer_id = %s",
                           (int(answer_id),))
    if row is None:
        raise ApiError(2001, detail="answer_id=%s 不存在" % answer_id)
    raw = row["graph_path"]
    extended = int(row["is_graph_extended"] or 0)
    if raw is None or raw == "":
        return extended, None
    if isinstance(raw, (list, dict)):
        return extended, raw
    try:
        return extended, json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("answer_id=%s 的 graph_path 不是合法 JSON 文本，按原样返回文本",
                       answer_id)
        return extended, str(raw)


# --------------------------------------------------------------------------
# 4. 落库
# --------------------------------------------------------------------------
def _next_ids(conn, session_id: str, question_text: str):
    """分配（或复用）整数 `question_id`／`answer_id`。

    先按 `(session_id, question_text)` 找已有记录 —— 找到就复用（幂等）；
    找不到再取 `GREATEST(MAX(question_id), MAX(answer_id)) + 1`，确保已导入的 1～30 号不被覆盖。
    """
    existing = db.query_one(
        "SELECT q.question_id AS qid, a.answer_id AS aid FROM question q "
        "LEFT JOIN answer a ON a.question_id = q.question_id "
        "WHERE q.session_id = %s AND q.question_text = %s ORDER BY q.question_id DESC LIMIT 1",
        (session_id, question_text), conn=conn)
    max_q = int(db.scalar("SELECT COALESCE(MAX(question_id), 0) FROM question", conn=conn) or 0)
    max_a = int(db.scalar("SELECT COALESCE(MAX(answer_id), 0) FROM answer", conn=conn) or 0)
    if existing and existing["qid"] is not None:
        qid = int(existing["qid"])
        if existing["aid"] is not None:
            return qid, int(existing["aid"])
        return qid, max(max_q, max_a) + 1      # 问题在、答案缺（异常残缺）→ 补一个不冲突的号
    nxt = max(max_q, max_a) + 1                # 两表取同一号，保证与已导入的 1～30 号不撞
    return nxt, nxt


def _persist(record: dict, question_id: int, answer_id: int) -> dict:
    """把链路记录落进三张表（一个事务内），返回落库后回读的证据明细。

    顺序：question → answer → answer_evidence（外键依赖）。全按主键 upsert；
    `answer_evidence` 先删后插，避免同一 `answer_id` 上残留过期证据行。
    """
    question = record.get("question") or {}
    answer = record.get("answer") or {}
    evidences = record.get("answer_evidence") or []

    answer_text = str(answer.get("answer_text") or "")
    graph_path = answer.get("graph_path")
    if graph_path is not None and not isinstance(graph_path, str):
        graph_path = json.dumps(graph_path, ensure_ascii=False)
    if graph_path == "":
        graph_path = None

    rows = []
    for item in evidences:
        chunk_id = _to_int_id(item.get("chunk_id"))
        doc_id = _to_int_id(item.get("doc_id"))
        if chunk_id is None or doc_id is None:
            logger.warning("证据项缺 chunk_id／doc_id，跳过：%r", item)
            continue
        rows.append((int(answer_id), chunk_id, doc_id,
                     int(item.get("rank") or len(rows) + 1),
                     str(item.get("evidence_type") or EVIDENCE_TYPES[0])))

    with _DB_LOCK:
        conn = _fresh_conn()
        try:
            conn.begin()
            with db.cursor(conn=conn) as cur:
                cur.execute(_SQL_QUESTION_UPSERT, (
                    int(question_id), None, question.get("session_id"),
                    str(question.get("question_text") or ""),
                    question.get("task_type"),
                    (int(question["gold_hop_depth"])
                     if question.get("gold_hop_depth") not in (None, "") else None),
                    _time_constraint_flag(question.get("time_constraint")),
                    _to_dt(question.get("ask_time"))))
                cur.execute(_SQL_ANSWER_UPSERT, (
                    int(answer_id), int(question_id), answer_text, graph_path,
                    str(answer.get("model_name") or config.ANSWER_MODEL),
                    str(answer.get("prompt_version") or config.PROMPT_VERSION),
                    int(answer.get("is_graph_extended") or 0),
                    _to_dt(answer.get("create_time") or question.get("ask_time"))))
                cur.execute("DELETE FROM answer_evidence WHERE answer_id = %s", (int(answer_id),))
                if rows:
                    cur.executemany(_SQL_EVIDENCE_INSERT, rows)
            conn.commit()
        except Exception:
            with contextlib.suppress(Exception):
                conn.rollback()
            raise
    return _evidence_rows(answer_id)


# --------------------------------------------------------------------------
# 5. 对外接口：POST /api/qa/ask
# --------------------------------------------------------------------------
def _question_digest(question: str) -> str:
    """日志脱敏用的题目摘要：只保留长度与 SHA-256 前 12 位，**不把题目正文写进日志**。

    用户问题会原样落库（`question.question_text`），这是业务需要；但应用日志面向排障，
    没有必要再留存一份可读正文（六.3 敏感信息最小化）。摘要足以把「同一条日志」与
    「同一条提问」对上，且不可逆。
    """
    raw = str(question or "").encode("utf-8")
    return "len=%d sha256=%s" % (len(question or ""), hashlib.sha256(raw).hexdigest()[:12])


def _reuse_existing_answer(session_id: str, question_text: str) -> dict | None:
    """同一会话内**重复提问**：命中已落库的成功回答时返回其完整载荷（不跑链路、不写库）。

    为什么在跑链路之前查一次
    ------------------------
    旧实现只在落库阶段按 `(session_id, question_text)` 复用 `question_id`／`answer_id`，
    但**模型链路已经完整跑过一遍**：重复提问仍会消耗 10～30 秒与一次模型调用，然后
    用同一组 ID 覆盖旧答案。语料与 Prompt 都是冻结口径，覆盖后的内容不会变化，因此
    这里把「复用」提前到链路之前——命中即原样返回既有回答，并在载荷里带
    `reused=true` 与 `notice`，前端据此给出「已问过、复用已有回答」的提示。

    只认**有正文的完整记录**（`answer_text` 非空）；空结果本来就不落库，残缺记录
    仍走正常链路重新生成。`reuse=False` 的后台受控实验（A～E 组）不会走这条捷径。
    """
    with _DB_LOCK:
        _fresh_conn()
        row = db.query_one(
            "SELECT q.question_id, q.task_type, a.answer_id, a.answer_text "
            "FROM question q JOIN answer a ON a.question_id = q.question_id "
            "WHERE q.session_id = %s AND q.question_text = %s "
            "ORDER BY q.question_id DESC LIMIT 1",
            (str(session_id), str(question_text)))
    if row is None or not str(row["answer_text"] or "").strip():
        return None

    answer_id = int(row["answer_id"])
    extended, graph_path = _graph_path_of_answer(answer_id)
    notice = ("这个问题在当前会话中已经问过，直接复用已有回答（question_id=%d、"
              "answer_id=%d），未重复调用模型。" % (int(row["question_id"]), answer_id))
    return {
        "answer_id": answer_id,
        "question_id": int(row["question_id"]),
        "answer_text": str(row["answer_text"]),
        "evidence": _evidence_rows(answer_id),
        "graph_path": graph_path,
        "is_graph_extended": int(extended),
        "time_interpretation": time_interpretation_of(str(row["answer_text"])),
        "data_cutoff_time": config.dataset_meta()["data_cutoff_time"],
        "answer_type": answer_type_of(row["task_type"]),
        "reused": True,
        "notice": notice,
    }


def ask(question: str, session_id: str, group: str | None = None,
        reuse: bool = False) -> dict:
    """跑一次问答链路并落库，返回表 4-13 规定的载荷。

    `session_id` **按调用方传入值**使用（前端生成的 UUID），不使用脚本默认值 `S-001`。

    `reuse` 由调用方显式选择：**面向用户的 `/api/qa/ask` 传 True**（同一会话内重复
    提问直接复用既有回答、不重复调用模型）；后台受控实验 A～E 组与直接调用保持
    默认 False（每次都跑新链路，保证分组对比与底层行为不变）。
    """
    group = group or DEFAULT_GROUP
    # A5：串行化重资源链路（见 _ASK_LOCK 注释）；排队期间不计入本条链路的超时。
    with _ASK_LOCK:
        if reuse:
            reused = _reuse_existing_answer(session_id, question)
            if reused is not None:
                observability.record_qa_retrieval(reused=True)
                logger.info("重复提问复用已有回答：question_id=%s answer_id=%s session=%s %s",
                            reused["question_id"], reused["answer_id"], session_id,
                            _question_digest(question))
                return reused
        ran = _run_chain(question, group, session_id, datetime.now().astimezone().isoformat(
            timespec="seconds"))
    # 第三轮 8.2：检索侧计数在链路返回后、分支处理前写入，空结果也计入一次向量检索。
    _trace = ran.get("trace") if isinstance(ran.get("trace"), dict) else {}
    try:
        _evidence_count = int(_trace.get("evidence_count") or 0)
    except (TypeError, ValueError):
        _evidence_count = 0
    _graph_used = bool(_trace.get("graph_used")
                       or (_trace.get("graph_payload") or {}).get("graph_used"))
    observability.record_qa_retrieval(
        evidence_count=_evidence_count,
        graph_used=_graph_used,
        empty=bool(ran.get("empty")))
    # 2026-10-18 全面审查 F2：没有可引用证据时**不落库、不造答案**，按 2002 语义返回
    # 正常空结果（HTTP 200），由前端给友好提示。旧行为是 502＋3004「装配账目守卫未通过」。
    if ran.get("empty"):
        logger.info("问答空结果（未检索到可引用证据）：%s session=%s 耗时=%.1fs",
                    _question_digest(question), session_id, ran["elapsed_seconds"])
        return {
            "empty": True,
            "empty_reason": ran.get("empty_reason") or "no_citable_evidence",
            "reused": False,
            "notice": "未检索到可引用的证据：这个问题在现有数据里找不到能支撑回答的原文。"
                      "可以换一种问法，或指明公司、时间与事件类型后再试。",
            "answer_id": None,
            "question_id": None,
            "answer_text": "",
            "evidence": [],
            "graph_path": None,
            "is_graph_extended": 0,
            "time_interpretation": None,
            "data_cutoff_time": config.dataset_meta()["data_cutoff_time"],
            "answer_type": ANSWER_TYPE_FALLBACK,
        }
    record = ran["record"]
    question_block = record.get("question") or {}
    answer_block = record.get("answer") or {}

    # 会话号以**请求值**为准（链路记录里的 session_id 理论上相同，但仍以调用方为准）
    question_block["session_id"] = session_id

    # N2（2026-10-11 复评）：ID 分配与落库**合并进同一锁段**——原先分配后即释放锁，
    # 并发时另一线程的 _next_ids 会读到前者未提交前的 MAX，可分配出同一 (qid, aid)
    # 静默互覆。_DB_LOCK 是 RLock（可重入），_persist 内部的 with _DB_LOCK 不会自锁。
    with _DB_LOCK:
        conn = _fresh_conn()
        question_id, answer_id = _next_ids(conn, session_id, question)
        items = _persist(record, question_id, answer_id)

    answer_text = str(answer_block.get("answer_text") or "")
    extended, graph_path = _graph_path_of_answer(answer_id)
    payload = {
        "answer_id": int(answer_id),
        "question_id": int(question_id),
        "answer_text": answer_text,
        "evidence": items,
        "graph_path": graph_path,
        "is_graph_extended": int(extended),
        "time_interpretation": time_interpretation_of(answer_text),
        "data_cutoff_time": config.dataset_meta()["data_cutoff_time"],
        "answer_type": answer_type_of(question_block.get("task_type")),
    }
    logger.info("问答落库完成：question_id=%s answer_id=%s 证据=%d 条 图谱扩展=%s 耗时=%.1fs",
                question_id, answer_id, len(items), extended, ran["elapsed_seconds"])
    return payload


# --------------------------------------------------------------------------
# 6. 对外接口：GET /api/qa/answers/{answer_id}
# --------------------------------------------------------------------------
def answer_row(answer_id: int) -> dict | None:
    """`answer` 联合 `question` 取一行；不存在返回 None。"""
    with _DB_LOCK:
        _fresh_conn()
        return db.query_one(
            "SELECT a.answer_id, a.question_id, a.answer_text, a.graph_path, a.model_name, "
            "       a.prompt_version, a.is_graph_extended, a.create_time, "
            "       q.session_id, q.question_text, q.ask_time, q.task_type "
            "FROM answer a JOIN question q ON q.question_id = a.question_id "
            "WHERE a.answer_id = %s", (int(answer_id),))


def get_answer(answer_id: int) -> dict:
    """单条回答详情；不存在抛 `ApiError(2001)`。"""
    row = answer_row(answer_id)
    if row is None:
        raise ApiError(2001, detail="answer_id=%s 不存在" % answer_id)
    extended, graph_path = _graph_path_of_answer(answer_id)
    return {
        "answer_id": int(row["answer_id"]),
        "question_id": int(row["question_id"]),
        "question_text": row["question_text"],
        "answer_text": row["answer_text"],
        "evidence": _evidence_rows(answer_id),
        "graph_path": graph_path,
        "is_graph_extended": int(extended),
        "model_name": row["model_name"],
        "prompt_version": row["prompt_version"],
        "create_time": _iso(row["create_time"]),
    }


# --------------------------------------------------------------------------
# 7. 对外接口：GET /api/config/meta
# --------------------------------------------------------------------------
def config_meta() -> dict:
    """只读元信息（表 4-13）：数据集版本、截止时间、Prompt 版本、K／N／预算、模型名。

    **只报当前固定口径**，不暴露任何可切换的实验配置（不在接口层提供 A～E 组切换）。
    """
    meta = config.dataset_meta()
    return {
        "dataset_version": meta["dataset_version"],
        "data_cutoff_time": meta["data_cutoff_time"],
        "prompt_version": config.PROMPT_VERSION,
        "k": config.K,
        "n": config.N,
        "context_token_budget": config.CONTEXT_TOKEN_BUDGET,
        "model_name": config.ANSWER_MODEL,
    }


# --------------------------------------------------------------------------
# 8. 对外接口：GET /api/evidence/{answer_id}[/graph-path]
# --------------------------------------------------------------------------
def evidence_of_answer(answer_id: int, evidence_type: str | None = None,
                       group_by: str | None = None) -> dict:
    """证据分组与明细；答案不存在抛 `ApiError(2001)`；证据为空返回空结果（HTTP 200）。"""
    row = answer_row(answer_id)
    if row is None:
        raise ApiError(2001, detail="answer_id=%s 不存在" % answer_id)
    items = _evidence_rows(answer_id, evidence_type=evidence_type)
    data = {"answer_id": int(answer_id), "groups": evidence_groups(items),
            "items": items, "total": len(items)}
    if group_by == "evidence_type":
        grouped = {name: [it for it in items if it["evidence_type"] == name]
                   for name in EVIDENCE_TYPES}
        data["items_grouped"] = {name: group for name, group in grouped.items() if group}
    return data


def graph_path_of_answer(answer_id: int) -> dict:
    """图谱路径：`is_graph_extended`／`paths`（**落库原文**解析）／`display_mode`。

    `display_mode` = `path`（本次回答用了图谱扩展）或 `not_used`（未使用）。
    **不重建、不伪造**路径（硬约束 11）：`paths` 直接来自 `answer.graph_path`。
    """
    extended, paths = _graph_path_of_answer(answer_id)
    return {"answer_id": int(answer_id), "is_graph_extended": int(extended),
            "paths": paths, "display_mode": "path" if extended else "not_used"}


# --------------------------------------------------------------------------
# 9. 对外接口：GET /api/documents/{doc_id}/chunks/{chunk_id}
# --------------------------------------------------------------------------
def chunk_detail(doc_id: int, chunk_id: int) -> dict:
    """文本块原文与相邻块＋所属文档元数据；不存在（或不属于该文档）抛 `ApiError(2001)`。

    `chunk_content` 一律**照抄数据库**（即与上游 `chunks.jsonl` 一致），不改写、不截断、不摘要。
    """
    with _DB_LOCK:
        _fresh_conn()
        chunk = db.query_one(
            "SELECT chunk_id, doc_id, chunk_index, content FROM document_chunk "
            "WHERE chunk_id = %s", (int(chunk_id),))
        if chunk is None or int(chunk["doc_id"]) != int(doc_id):
            raise ApiError(2001, detail="chunk_id=%s 不属于 doc_id=%s（或不存在）"
                           % (chunk_id, doc_id))
        doc = db.query_one("SELECT doc_id, title, source, publish_time, url FROM document "
                           "WHERE doc_id = %s", (int(doc_id),))
        if doc is None:
            raise ApiError(2001, detail="doc_id=%s 不存在" % doc_id)
        neighbors = db.query(
            "SELECT chunk_id, chunk_index, content FROM document_chunk "
            "WHERE doc_id = %s AND chunk_index BETWEEN %s AND %s AND chunk_id <> %s "
            "ORDER BY chunk_index ASC",
            (int(doc_id), int(chunk["chunk_index"]) - NEIGHBOR_RADIUS,
             int(chunk["chunk_index"]) + NEIGHBOR_RADIUS, int(chunk_id)))
    return {
        "chunk_id": int(chunk["chunk_id"]),
        "chunk_index": int(chunk["chunk_index"]),
        "chunk_content": chunk["content"],
        "neighbor_chunks": [{"chunk_id": int(n["chunk_id"]),
                             "chunk_index": int(n["chunk_index"]),
                             "chunk_content": n["content"]} for n in neighbors],
        "doc": {"doc_id": int(doc["doc_id"]), "title": doc["title"], "source": doc["source"],
                "publish_time": _iso(doc["publish_time"]), "url": doc["url"]},
    }


# --------------------------------------------------------------------------
# 10. 对外接口：GET /api/history[/{question_id}]
# --------------------------------------------------------------------------
def history_list(session_id: str, page: int, page_size: int) -> dict:
    """按会话分页列出历史问答（`ask_time` 倒序）；无数据返回空结果（HTTP 200）。

    `session_id` 是**强制**过滤条件（FR-06 会话隔离），缺失由接口层按 1002 拒。
    """
    with _DB_LOCK:
        _fresh_conn()
        total = int(db.scalar(
            "SELECT COUNT(*) FROM question q JOIN answer a ON a.question_id = q.question_id "
            "WHERE q.session_id = %s", (session_id,)) or 0)
        rows = db.query(
            "SELECT q.question_id, a.answer_id, q.question_text, q.ask_time, a.answer_text, "
            "       (SELECT COUNT(*) FROM answer_evidence ae WHERE ae.answer_id = a.answer_id) "
            "       AS evidence_count "
            "FROM question q JOIN answer a ON a.question_id = q.question_id "
            "WHERE q.session_id = %s "
            "ORDER BY q.ask_time DESC, q.question_id DESC LIMIT %s OFFSET %s",
            (session_id, int(page_size), int((page - 1) * page_size)))
    items = [{"question_id": int(r["question_id"]), "answer_id": int(r["answer_id"]),
              "question_text": r["question_text"], "ask_time": _iso(r["ask_time"]),
              "answer_summary": _summary(r["answer_text"]),
              "evidence_count": int(r["evidence_count"] or 0)} for r in rows]
    return {"total": total, "items": items, "page": int(page), "page_size": int(page_size)}


def history_detail(question_id: int, session_id: str) -> dict:
    """按 `question_id` 回看一条历史问答；**必须属于该会话**，否则抛 `ApiError(2001)`。

    【回顾只还原三表内容，不重新渲染图谱路径】：这里只回 `graph_path_available`（布尔），
    **不返回路径本体**。
    """
    with _DB_LOCK:
        _fresh_conn()
        row = db.query_one(
            "SELECT q.question_id, q.session_id, q.question_text, q.ask_time, q.task_type, "
            "       a.answer_id, a.answer_text, a.graph_path, a.model_name, a.prompt_version "
            "FROM question q LEFT JOIN answer a ON a.question_id = q.question_id "
            "WHERE q.question_id = %s", (int(question_id),))
    if row is None:
        raise ApiError(2001, detail="question_id=%s 不存在" % question_id)
    if str(row["session_id"] or "") != str(session_id):
        raise ApiError(2001, detail="question_id=%s 不属于会话 %s（FR-06 会话隔离）"
                       % (question_id, session_id))
    answer_id = row["answer_id"]
    items = _evidence_rows(answer_id) if answer_id is not None else []
    graph_path = row["graph_path"]
    return {
        "question_id": int(row["question_id"]),
        "question_text": row["question_text"],
        "ask_time": _iso(row["ask_time"]),
        "answer_id": int(answer_id) if answer_id is not None else None,
        "answer_text": row["answer_text"],
        "evidence": items,
        "graph_path_available": bool(graph_path not in (None, "", "null", "[]")),
    }
