# -*- coding: utf-8 -*-
"""代码\\后端\\db.py —— 第 9 阶段（前后端系统集成）MySQL 访问层。

访问方式：**PyMySQL ＋ 显式 SQL**，**不用 ORM**（《24》第六节 格式决策 2）
---------------------------------------------------------------------
理由（写在此处，便于论文与答辩引用）：本项目的第一条纪律是「口径以文档为准」，而表结构
的唯一出处是 `schema\\六张表.sql`——它与《10》第4.4.1节 表 4-6 逐字对应、可以直接对照阅读。
ORM 会把表结构藏进代码里，形成「第二处定义」，与 `六张表.sql` 各自漂移；第 7／8 阶段的
检索与问答链路也全部是显式 SQL 风格。故本层只用 PyMySQL 的 `Connection`／`Cursor`
与手写 SQL，不写任何 ORM 模型类（硬约束 3：不新增表、不新增字段）。

事务与连接
----------
* `autocommit=False`：写操作必须显式 `commit()`，异常路径 `rollback()`；
  `cursor(commit=True)` 上下文管理器把「提交／回滚」绑在同一个 with 上。
* 连接是**进程内单例**（懒建）：`get_conn()` 拿连接，掉线时 `ping()` 自动重连一次；
  服务侧并发由 uvicorn 的单进程事件循环 ＋ PyMySQL 的短事务保证（第一版不做连接池——
  本项目是单机演示与实验运行器，连接池属过度设计，登记为已知限制）。

错误分层的约定（《24》T2／T4 的执行要求）
-----------------------------------------
* **凭据缺失／仍是占位串**：由 `config.db_params()` 抛 `SystemExit`（提示里含
  「请检查 `代码\\后端\\config.local.json`」）——这是配置问题，不是运行期故障。
* **MySQL 连不上**：本文件抛 `DbConnectError`，消息里同样含
  「请检查 `代码\\后端\\config.local.json`」，并带上 pymysql 的原始错误码与原因。
  它**不是** `ApiError`（接口层的 3001 是「图谱服务不可用」、2003 是「文档被历史引用」，
  都不是「MySQL 挂了」）；接口层若要回码，由调用方决定（`/api/health` 把 mysql 探针
  标为失败即可）。
"""

from __future__ import annotations

import contextlib
import os
import sys
import threading

import pymysql
import pymysql.cursors

import config

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

CONFIG_HINT = "请检查 代码\\后端\\config.local.json"

# 连接超时（秒）：健康探针不能把服务拖住
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30
WRITE_TIMEOUT = 30
PROBE_TIMEOUT = 3
"""健康探针的专用连接／读超时（秒）：探针**每次新建短超时连接**、不碰共享单例，
即使共享连接半开也能在数秒内如实返回（M1，2026-10-11 审查）。"""


class DbConnectError(RuntimeError):
    """MySQL 不可达／不可用（**启动期错误**，不是接口层的 ApiError）。"""

    def __init__(self, message: str, errno: int | None = None):
        self.errno = errno
        super().__init__(message)


# --------------------------------------------------------------------------
# 1. 连接
# --------------------------------------------------------------------------
_conn = None
_CONN_LOCK = threading.RLock()
"""连接单例的创建／重连锁（M2，2026-10-11 审查）：`/api/health` 探针与业务请求并发时，
`get_conn` 的「ping → 失败 → 重连」是 check-then-act，无锁会互踩（两个线程同时判定连接
已死并各建一条，其中一条被静默丢弃甚至写坏共享状态）。RLock 可重入：`ping()` 内部再调
`get_conn()` 不会自锁。锁内含网络操作（ping），最坏情况下其他线程排队等待——比竞态互踩
安全，且这是单连接串行化方案的既定语义（见模块头「事务与连接」）。"""


def _params(with_database: bool = True) -> dict:
    """完整连接参数（**含口令**）：不得打印、不得写盘、不得进日志。"""
    params = config.db_params(with_database=with_database)
    params.update({"autocommit": False,
                   "cursorclass": pymysql.cursors.DictCursor,
                   "connect_timeout": CONNECT_TIMEOUT,
                   "read_timeout": READ_TIMEOUT,
                   "write_timeout": WRITE_TIMEOUT})
    return params


def describe_target(with_database: bool = True) -> str:
    """连接目标的可打印描述——**只含主机／端口／账号／库名，绝不含口令**。"""
    p = config.db_params(with_database=with_database)
    return "%s:%s/%s（user=%s）" % (p["host"], p["port"],
                                    p.get("database", "(未指定库)"), p["user"])


def connect(with_database: bool = True):
    """新建一条连接（不进入单例）。建库阶段用 `with_database=False`。"""
    params = _params(with_database=with_database)
    try:
        return pymysql.connect(**params)
    except pymysql.err.OperationalError as exc:
        errno = exc.args[0] if exc.args else None
        reason = exc.args[1] if len(exc.args) > 1 else str(exc)
        extra = {1045: "（账号或口令被拒：ERROR 1045）",
                 1049: "（库不存在：ERROR 1049——先跑 db.ensure_database()）",
                 2003: "（端口不通：ERROR 2003——MySQL 服务是否在运行？）"}.get(errno, "")
        raise DbConnectError(
            "MySQL 连接失败%s：%s → ERROR %s: %s\n%s"
            % (extra, describe_target(with_database), errno, reason, CONFIG_HINT),
            errno=errno)
    except pymysql.err.MySQLError as exc:
        raise DbConnectError(
            "MySQL 连接失败：%s → %s\n%s"
            % (describe_target(with_database), exc, CONFIG_HINT), errno=None)


def get_conn():
    """进程内单例连接；掉线时 ping 一次并重连（M2：持锁做 check-then-act，防并发互踩）。"""
    global _conn
    with _CONN_LOCK:
        if _conn is None:
            _conn = connect(with_database=True)
            return _conn
        try:
            _conn.ping(reconnect=True)
        except Exception:
            with contextlib.suppress(Exception):
                _conn.close()
            _conn = connect(with_database=True)
        return _conn


def close() -> None:
    global _conn
    with _CONN_LOCK:
        if _conn is not None:
            with contextlib.suppress(Exception):
                _conn.close()
            _conn = None


def ping() -> bool:
    """连通性探针：真则通。**不抛异常**（供 `/api/health` 用）。"""
    try:
        conn = get_conn()
        conn.ping(reconnect=True)
        return True
    except (DbConnectError, SystemExit):
        return False
    except Exception:
        return False


def server_version() -> str:
    row = query_one("SELECT VERSION() AS v")
    return str(row["v"]) if row else ""


def probe(timeout_seconds: int = PROBE_TIMEOUT) -> dict:
    """健康探针：返回 `{"ok": bool, "detail": str}`；**detail 不含口令**（`/api/health` 用）。

    三类结果分开报：凭据未配置（配置问题）／连不上（服务问题）／连通（带版本号）。

    M1（2026-10-11 审查）：**每次新建探针专用短超时连接**（connect/read 超时取
    `timeout_seconds`，默认 3s），不再 ping 共享单例——共享连接半开时 `ping()` 依赖
    TCP 重传最长可阻塞约 35s，会把 `/api/health`（进而整次探活）拖住；专用连接由
    连接超时兜底，探针数秒内必然返回。代价是每次探活新建一条连接（`/api/health`
    探活频率低，可接受）。
    """
    try:
        config.db_params()
    except SystemExit:
        return {"ok": False, "detail": "凭据未配置（config.local.json 的 mysql_password 待填）"}
    params = _params()
    params["connect_timeout"] = int(timeout_seconds)
    params["read_timeout"] = int(timeout_seconds)
    try:
        conn = pymysql.connect(**params)
    except pymysql.err.OperationalError as exc:
        errno = exc.args[0] if exc.args else None
        reason = exc.args[1] if len(exc.args) > 1 else str(exc)
        head = str(reason).splitlines()[0] if reason else ""
        return {"ok": False, "detail": "连接失败（ERROR %s: %s）" % (errno, head)}
    except pymysql.err.MySQLError as exc:
        return {"ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    except Exception as exc:
        return {"ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS v")
            row = cur.fetchone()
        return {"ok": True, "detail": str(row["v"]) if row else ""}
    except Exception as exc:
        return {"ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}
    finally:
        with contextlib.suppress(Exception):
            conn.close()


# --------------------------------------------------------------------------
# 2. 游标与事务
# --------------------------------------------------------------------------
@contextlib.contextmanager
def cursor(commit: bool = False, conn=None):
    """游标上下文管理器。

    `commit=True` 时成功即提交、异常即回滚；`commit=False` 时只负责关闭游标
    （读多写少，写路径统一显式提交或成组提交）。
    """
    connection = conn if conn is not None else get_conn()
    cur = connection.cursor()
    try:
        yield cur
        if commit:
            connection.commit()
    except Exception:
        if commit:
            with contextlib.suppress(Exception):
                connection.rollback()
        raise
    finally:
        with contextlib.suppress(Exception):
            cur.close()


def begin():
    """开始一个事务（返回连接本身，供成组提交使用）。"""
    conn = get_conn()
    conn.begin()
    return conn


def commit(conn=None) -> None:
    (conn if conn is not None else get_conn()).commit()


def rollback(conn=None) -> None:
    with contextlib.suppress(Exception):
        (conn if conn is not None else get_conn()).rollback()


# --------------------------------------------------------------------------
# 3. 读写（显式 SQL）
# --------------------------------------------------------------------------
def query(sql: str, args=None, conn=None) -> list:
    """返回行列表（每行是 dict，列名 → 值）。"""
    with cursor(conn=conn) as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def query_one(sql: str, args=None, conn=None):
    """返回首行（dict）或 None。"""
    rows = query(sql, args, conn=conn)
    return rows[0] if rows else None


def execute(sql: str, args=None, conn=None) -> int:
    """执行一条写语句，返回受影响行数（**不自动提交**）。"""
    with cursor(conn=conn) as cur:
        return cur.execute(sql, args)


def executemany(sql: str, seq_of_args, conn=None) -> int:
    """批量写（**不自动提交**）。"""
    with cursor(conn=conn) as cur:
        return cur.executemany(sql, list(seq_of_args))


def scalar(sql: str, args=None, conn=None):
    row = query_one(sql, args, conn=conn)
    if not row:
        return None
    return list(row.values())[0]


# --------------------------------------------------------------------------
# 4. 库与表（建库、建表、计数、元数据）
# --------------------------------------------------------------------------
def _ddl_privilege_error(exc: Exception, action: str) -> SystemExit:
    """把 DDL 权限拒绝（1044/1142）翻译成可执行的处置提示。

    运行期账号 `ashare_app` 只有 DML；建库／建表属于迁移期动作，应由迁移账号完成。
    不打印账号名与原始错误串（原生消息含 `user 'x'@'y'`），避免把凭据碎片写进终端／日志。
    """
    errno = exc.args[0] if getattr(exc, "args", None) else None
    if errno in (1044, 1142):
        return SystemExit(
            "MySQL 当前账号无权执行 %s（ERROR %s）。\n"
            "运行期账号仅授予 DML；建库／建表请使用迁移账号（或用 DBA 预先执行 schema\\六张表.sql）：\n"
            "    set ASHARE_MYSQL_USER=<迁移账号>\n"
            "    set ASHARE_MYSQL_PASSWORD=<迁移口令>\n"
            "库与六张表已存在时，本函数会自动跳过 DDL，不需要 DDL 权限。"
            % (action, errno))
    return SystemExit("MySQL 执行 %s 失败：%s"
                      % (action, str(exc).splitlines()[0] if str(exc) else type(exc).__name__))


def ensure_database() -> str:
    """建库 `ashare_qa`（字符集 utf8mb4、排序规则 utf8mb4_0900_ai_ci）；已存在则不动。

    库名与字符集一律取配置，**不在代码里写死**（硬约束 1）。
    独立审查（2026-10-19）：运行期账号已切为仅 DML。库已存在时**直接返回、不执行 DDL**，
    使 `tools/import_data.py` 在 DML-only 账号下也能完成写入；库不存在且账号无权 CREATE 时，
    给出可执行的迁移账号提示，而不是抛裸 OperationalError。
    """
    name = config.db_database()
    if database_exists():
        return name
    charset = config.db_charset()
    conn = connect(with_database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET %s COLLATE %s_0900_ai_ci"
                % (name, charset, charset))
        conn.commit()
    except pymysql.err.MySQLError as exc:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise _ddl_privilege_error(exc, "CREATE DATABASE") from exc
    finally:
        with contextlib.suppress(Exception):
            conn.close()
    return name


def database_exists() -> bool:
    name = config.db_database()
    try:
        row = query_one(
            "SELECT COUNT(*) AS n FROM information_schema.SCHEMATA WHERE SCHEMA_NAME=%s", (name,))
    except DbConnectError:
        return False
    return bool(row and row["n"])


def split_sql(text: str) -> list:
    """把 DDL 文件切成单条语句。

    本项目的 `六张表.sql` 刻意做到「语句内不出现分号」（列注释不用分号），因此这个朴素
    切分器足够可靠；行首 `--` 与空行按注释／空行丢弃。
    """
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        kept.append(line)
    return [stmt.strip() for stmt in "\n".join(kept).split(";") if stmt.strip()]


def schema_ready() -> bool:
    """六张表是否已全部存在（只读 information_schema，不触发任何 DDL）。"""
    placeholders = ", ".join(["%s"] * len(config.TABLES))
    rows = query(
        "SELECT TABLE_NAME AS name FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME IN (" + placeholders + ")",
        tuple([config.db_database()] + list(config.TABLES)))
    found = {str(row.get("name", "")).lower() for row in rows}
    return {str(t).lower() for t in config.TABLES} <= found


def init_schema(path: str | None = None) -> int:
    """执行 `schema\\六张表.sql`（全部 `CREATE TABLE IF NOT EXISTS`，可重复执行）。

    六张表已全部存在时直接返回 0、**不执行任何 DDL**：运行期 DML-only 账号也能安全调用
    （`tools/import_data.py` 的默认路径）。缺表且账号无 CREATE 权限时给出迁移账号提示。
    """
    if schema_ready():
        return 0
    sql_path = path or config.SCHEMA_SQL
    if not os.path.isfile(sql_path):
        raise SystemExit("DDL 文件不存在：%s" % sql_path)
    with open(sql_path, "r", encoding="utf-8") as f:
        statements = split_sql(f.read())
    conn = get_conn()
    try:
        with cursor(conn=conn) as cur:
            for stmt in statements:
                cur.execute(stmt)
        conn.commit()
    except pymysql.err.MySQLError as exc:
        with contextlib.suppress(Exception):
            conn.rollback()
        raise _ddl_privilege_error(exc, "CREATE TABLE") from exc
    return len(statements)


def table_counts() -> dict:
    """六张表的行数（`{表名: 行数}`），顺序即 config.TABLES 的顺序。"""
    out = {}
    for table in config.TABLES:
        out[table] = int(scalar("SELECT COUNT(*) FROM `%s`" % table) or 0)
    return out


# --------------------------------------------------------------------------
# 5. 自检（需要可用凭据；凭据未填时打印明确原因并以非零退出）
# --------------------------------------------------------------------------
def selftest() -> int:
    line = "=" * 74
    print(line)
    print("db.py 自检（PyMySQL ＋ 显式 SQL；库名与字符集取自 config）")
    print(line)
    print("  目标库 = %s（字符集 %s）" % (config.db_database(), config.db_charset()))
    try:
        config.db_params()            # 凭据校验（缺失即 SystemExit，消息里含配置路径）
        if not ping():
            raise DbConnectError("ping 失败（连接未建立）")
        print("  连接目标   = %s" % describe_target())
        print("  MySQL 版本 = %s" % server_version())
        print("  库存在     = %s" % database_exists())
        print("  六张表行数 = %s" % table_counts())
    except SystemExit as exc:
        print("  !! 凭据未就绪（这是配置问题，不是代码缺陷）：")
        print("  %s" % exc)
        print(line)
        return 3
    except DbConnectError as exc:
        print("  !! 未能连库：%s" % exc)
        print(line)
        return 2
    print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
