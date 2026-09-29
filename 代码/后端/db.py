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


class DbConnectError(RuntimeError):
    """MySQL 不可达／不可用（**启动期错误**，不是接口层的 ApiError）。"""

    def __init__(self, message: str, errno: int | None = None):
        self.errno = errno
        super().__init__(message)


# --------------------------------------------------------------------------
# 1. 连接
# --------------------------------------------------------------------------
_conn = None


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
    """进程内单例连接；掉线时 ping 一次并重连。"""
    global _conn
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


def probe() -> dict:
    """健康探针：返回 `{"ok": bool, "detail": str}`；**detail 不含口令**（`/api/health` 用）。

    三类结果分开报：凭据未配置（配置问题）／连不上（服务问题）／连通（带版本号）。
    """
    try:
        config.db_params()
    except SystemExit:
        return {"ok": False, "detail": "凭据未配置（config.local.json 的 mysql_password 待填）"}
    try:
        conn = get_conn()
        conn.ping(reconnect=True)
        return {"ok": True, "detail": server_version()}
    except DbConnectError as exc:
        return {"ok": False, "detail": str(exc).splitlines()[0]}
    except Exception as exc:
        return {"ok": False, "detail": "%s: %s" % (type(exc).__name__, exc)}


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
def ensure_database() -> str:
    """建库 `ashare_qa`（字符集 utf8mb4、排序规则 utf8mb4_0900_ai_ci）；已存在则不动。

    库名与字符集一律取配置，**不在代码里写死**（硬约束 1）。
    """
    name = config.db_database()
    charset = config.db_charset()
    conn = connect(with_database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE DATABASE IF NOT EXISTS `%s` CHARACTER SET %s COLLATE %s_0900_ai_ci"
                % (name, charset, charset))
        conn.commit()
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


def init_schema(path: str | None = None) -> int:
    """执行 `schema\\六张表.sql`（全部 `CREATE TABLE IF NOT EXISTS`，可重复执行）。"""
    sql_path = path or config.SCHEMA_SQL
    if not os.path.isfile(sql_path):
        raise SystemExit("DDL 文件不存在：%s" % sql_path)
    with open(sql_path, "r", encoding="utf-8") as f:
        statements = split_sql(f.read())
    conn = get_conn()
    with cursor(conn=conn) as cur:
        for stmt in statements:
            cur.execute(stmt)
    conn.commit()
    return len(statements)


def table_counts() -> dict:
    """六张表的行数（`{表名: 行数}`），顺序即 config.TABLES 的顺序。"""
    out = {}
    for table in config.TABLES:
        out[table] = int(scalar("SELECT COUNT(*) FROM `%s`" % table) or 0)
    return out


def table_columns(table: str) -> list:
    """`information_schema` 的列定义（供门禁 B1 逐字段比对）。"""
    return query(
        "SELECT ORDINAL_POSITION, COLUMN_NAME, COLUMN_TYPE, DATA_TYPE, IS_NULLABLE, "
        "       COLUMN_KEY, COLUMN_DEFAULT, EXTRA "
        "FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
        (config.db_database(), table))


def table_indexes(table: str) -> list:
    """索引与唯一键（供门禁 B2 取证）。"""
    return query(
        "SELECT INDEX_NAME, NON_UNIQUE, SEQ_IN_INDEX, COLUMN_NAME "
        "FROM information_schema.STATISTICS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
        "ORDER BY INDEX_NAME, SEQ_IN_INDEX",
        (config.db_database(), table))


def foreign_keys(table: str) -> list:
    """外键与 ON DELETE／ON UPDATE 行为（供门禁 B2 取证：RESTRICT 必须出现在
    `fk_ae_doc`／`fk_ae_chunk` 上）。"""
    return query(
        "SELECT k.CONSTRAINT_NAME, k.COLUMN_NAME, k.REFERENCED_TABLE_NAME, "
        "       k.REFERENCED_COLUMN_NAME, r.DELETE_RULE, r.UPDATE_RULE "
        "FROM information_schema.KEY_COLUMN_USAGE k "
        "JOIN information_schema.REFERENTIAL_CONSTRAINTS r "
        "  ON r.CONSTRAINT_SCHEMA=k.CONSTRAINT_SCHEMA AND r.CONSTRAINT_NAME=k.CONSTRAINT_NAME "
        "WHERE k.TABLE_SCHEMA=%s AND k.TABLE_NAME=%s AND k.REFERENCED_TABLE_NAME IS NOT NULL "
        "ORDER BY k.CONSTRAINT_NAME",
        (config.db_database(), table))


def primary_key(table: str) -> list:
    """主键列（按序）。`answer_evidence` 必须返回 ['answer_id', 'chunk_id']。"""
    rows = query(
        "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND CONSTRAINT_NAME='PRIMARY' "
        "ORDER BY ORDINAL_POSITION",
        (config.db_database(), table))
    return [r["COLUMN_NAME"] for r in rows]


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
