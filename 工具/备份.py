# -*- coding: utf-8 -*-
"""工具\\备份.py —— 第 4 轮（11.2）本机数据备份与**导入回验**。

备份内容（每次运行产出一个带时间戳的目录，落在 `交付物/10-部署/备份/`，已被 .gitignore 覆盖）：

| 子目录／文件 | 来源 | 说明 |
| --- | --- | --- |
| `mysql/ashare_qa.sql` | `mysqldump` | `--single-transaction --quick`，含六表数据；不含建库语句 |
| `neo4j/nodes.jsonl`、`relationships.jsonl` | Neo4j 逻辑导出 | 逐节点／逐关系 JSONL，按 elementId 排序，可重放 |
| `vector/faiss.index`、`vector_map.jsonl`、`build_meta.json` | 数据集 index 目录 | 原样复制（只读输入） |
| `manifest.json` | 本脚本 | 文件 sha256／字节数、六表计数、Neo4j 计数、环境与工具版本；**不含口令** |

**导入回验**：dump 完成后先建临时库 `ashare_qa_bakverify_<时间戳>`，用 `mysql` 客户端把
dump 灌进去，逐表比对计数，再 `DROP DATABASE`。临时库一定在 finally 中删除；正式库
`ashare_qa` 全程只读，不写入。这样「备份文件可恢复」有实测证据，不是只看看文件大小。

运行期账号只有 DML 时（`ashare_app`），建／删临时库需要迁移账号权限（独立审查 2026-10-19）：

* **推荐**：用迁移账号环境变量运行备份（只影响本进程，不改 config.local.json）：
  `set ASHARE_MYSQL_USER=…` / `set ASHARE_MYSQL_PASSWORD=…`；
* 若确实没有迁移账号，可显式 `--skip-verify`：仍生成 dump／Neo4j／向量备份，
  但 **manifest 的 `verify.skipped=true` 如实标记「未做恢复回验」**；
* 真实运行会在**写任何文件之前**先建／删一个探针库做权限预检；权限不足即退出 1，
  不再留下「dump 已写、回验失败」的半成品目录（这是本次审查修掉的回归）。

纪律
----
* 口令只写进 `%TEMP%` 下的临时 option 文件（尽力设 0600），进程结束即删除；不打印、不入 manifest。
* `--dry-run` 只做连通性与可用性检查、打印计划，不创建目录、不写任何文件、不建临时库。
* 退出码：成功 0；任一步失败 1（并保留已完成的部分与本轮目录，便于排障）。
* 不触碰 Docker 容器：Neo4j 走 bolt 逻辑导出，不需要 `docker exec`，也不影响保活。

保留期清理（第二轮第 9 轮）
--------------------------
`--keep N`（默认 **3**）只保留输出根目录下**最近 N 份**备份目录（按目录名时间戳倒序），
更旧的整目录删除。安全边界：
* 只认「目录名严格匹配 `YYYYMMDD_HHMMSS`」且**目录内有 `manifest.json`** 的目录——别的
  文件／目录（如手工放的说明、临时文件）一律不碰；
* 只删除输出根目录的**直接子目录**且 realpath 必须仍在根目录内（不跟随符号链接）；
* **只在本次备份成功后才清理**；备份失败时旧备份原样保留；`--dry-run` 只打印将删除哪些；
* **本次刚生成的目录永不删除**（系统时钟回拨时它可能排在旧备份之后，单独保护）。

用法
----
    python 工具\\备份.py                 # 完整备份 + 导入回验 + 保留最近 3 份
    python 工具\\备份.py --keep 7        # 保留最近 7 份
    python 工具\\备份.py --dry-run       # 只检查并打印计划（含保留期计划）
    python 工具\\备份.py --skip-verify   # 没有迁移账号时：生成备份但不做恢复回验
    python 工具\\备份.py --out D:\\bak   # 指定输出根目录
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "交付物", "03-代码", "后端")
DEFAULT_OUT_ROOT = os.path.join(ROOT, "交付物", "10-部署", "备份")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

VERIFY_TABLES = ("user", "document", "document_chunk", "question", "answer", "answer_evidence")


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _find_mysql_bin(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for base in (r"C:\Program Files\MySQL\MySQL Server 8.4\bin",
                 r"C:\Program Files\MySQL\MySQL Server 8.0\bin",
                 r"C:\Program Files\MySQL\MySQL Server 9.0\bin"):
        candidate = os.path.join(base, name + ".exe")
        if os.path.isfile(candidate):
            return candidate
    return None


def _option_file(password: str, host: str, port: int, user: str):
    """写临时 MySQL option 文件；返回值 (路径, 清理函数)。口令不进命令行。"""
    fd, path = tempfile.mkstemp(prefix="ashare_bak_", suffix=".cnf")
    escaped = password.replace("\\", "\\\\").replace('"', '\\"')
    content = (
        "[client]\n"
        "host=%s\n"
        "port=%d\n"
        "user=%s\n"
        'password="%s"\n'
        "default-character-set=utf8mb4\n"
        % (host, port, user, escaped)
    )
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    try:
        os.chmod(path, 0o600)
    except Exception:
        pass

    def cleanup():
        try:
            os.remove(path)
        except OSError:
            pass
    return path, cleanup


def _db_counts(cursor) -> dict:
    counts = {}
    for table in VERIFY_TABLES:
        cursor.execute("SELECT COUNT(*) AS n FROM `%s`" % table)
        counts[table] = int(cursor.fetchone()["n"])
    return counts


def _connect(config):
    import pymysql
    params = config.db_params()
    return pymysql.connect(connect_timeout=5, read_timeout=60,
                           cursorclass=pymysql.cursors.DictCursor, **params), params


def _preflight_verify_db(db_params: dict, verify_db: str) -> tuple:
    """在写文件前证明当前账号能 CREATE/DROP 回验库。

    返回 `(ok, detail)`。探针库名带 `_probe` 后缀，创建后立刻删除；即使 DROP 失败也只会
    留下一个空的 `ashare_qa_bakverify_*_probe`（不会动正式库）。
    """
    import pymysql
    probe = verify_db + "_probe"
    admin = None
    created = False
    try:
        admin = pymysql.connect(connect_timeout=5, read_timeout=30,
                                cursorclass=pymysql.cursors.DictCursor, **db_params)
        with admin.cursor() as cur:
            cur.execute("CREATE DATABASE `%s` CHARACTER SET utf8mb4 "
                        "COLLATE utf8mb4_0900_ai_ci" % probe)
        admin.commit()
        created = True
        with admin.cursor() as cur:
            cur.execute("DROP DATABASE `%s`" % probe)
        admin.commit()
        created = False
        return True, ""
    except pymysql.err.MySQLError as exc:
        errno = exc.args[0] if getattr(exc, "args", None) else None
        return False, "ERROR %s（CREATE/DROP DATABASE 被拒绝）" % errno
    except Exception as exc:                                    # noqa: BLE001
        return False, (str(exc).splitlines()[0] if str(exc) else type(exc).__name__)
    finally:
        if created and admin is not None:
            try:
                with admin.cursor() as cur:
                    cur.execute("DROP DATABASE IF EXISTS `%s`" % probe)
                admin.commit()
            except Exception:
                pass
        if admin is not None:
            try:
                admin.close()
            except Exception:
                pass


BACKUP_DIR_RE = re.compile(r"^\d{8}_\d{6}$")


def _list_backup_dirs(out_root: str) -> list:
    """列出可识别的备份目录：`YYYYMMDD_HHMMSS` 且含 `manifest.json`，按时间倒序。"""
    if not os.path.isdir(out_root):
        return []
    entries = []
    for name in os.listdir(out_root):
        path = os.path.join(out_root, name)
        if os.path.islink(path) or not os.path.isdir(path):
            continue
        if not BACKUP_DIR_RE.match(name):
            continue
        if not os.path.isfile(os.path.join(path, "manifest.json")):
            continue
        entries.append((name, path))
    entries.sort(key=lambda item: item[0], reverse=True)
    return entries


def _prune_backups(out_root: str, keep: int, dry_run: bool = False,
                   protect: str | None = None) -> list:
    """只保留最近 `keep` 份备份；返回被删除（或 dry-run 下将被删除）的目录名。

    `protect`：本次刚生成的备份目录（绝不允许删除——即使系统时钟回拨导致它的目录名
    排在旧备份之后）。其余安全边界见模块 docstring：仅直接子目录、目录名匹配、
    含 manifest.json、realpath 在根内。
    """
    root_real = os.path.realpath(out_root)
    protect_real = os.path.realpath(protect) if protect else None
    stale = _list_backup_dirs(out_root)[keep:]
    removed = []
    for name, path in stale:
        path_real = os.path.realpath(path)
        if protect_real and path_real == protect_real:
            print("      [SKIP] 保留本次备份（时钟回拨保护）：%s" % name)
            continue
        # 双保险：必须是输出根的直接子目录，且仍未逃出根目录
        if os.path.dirname(path_real) != root_real or not os.path.isdir(path_real):
            print("      [SKIP] 不删除（路径不在输出根内或已不是目录）：%s" % name)
            continue
        if not os.path.isfile(os.path.join(path_real, "manifest.json")):
            print("      [SKIP] 不删除（缺 manifest.json，可能不是本脚本产物）：%s" % name)
            continue
        if dry_run:
            print("      [dry-run] 将删除旧备份：%s" % name)
        else:
            try:
                shutil.rmtree(path_real)
                print("      已删除旧备份：%s" % name)
            except OSError as exc:
                print("      [WARN] 删除旧备份失败（%s）：%s" % (name, exc))
                continue
        removed.append(name)
    return removed


def _export_neo4j(config, out_dir: str) -> dict:
    from neo4j import GraphDatabase
    params = config.neo4j_params()
    driver = GraphDatabase.driver(params["uri"],
                                  auth=(params["user"], params["password"] or None),
                                  connection_timeout=5.0)
    nodes_path = os.path.join(out_dir, "nodes.jsonl")
    rels_path = os.path.join(out_dir, "relationships.jsonl")
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            nodes = sorted(
                (dict(r["n"]) for r in session.run(
                    "MATCH (n) RETURN {eid: elementId(n), labels: labels(n), props: properties(n)} AS n")),
                key=lambda x: x["eid"])
            rels = sorted(
                (dict(r["r"]) for r in session.run(
                    "MATCH (a)-[r]->(b) RETURN {eid: elementId(r), type: type(r), "
                    "start: elementId(a), end: elementId(b), props: properties(r)} AS r")),
                key=lambda x: x["eid"])
        with open(nodes_path, "w", encoding="utf-8", newline="\n") as f:
            for row in nodes:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        with open(rels_path, "w", encoding="utf-8", newline="\n") as f:
            for row in rels:
                f.write(json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n")
        return {"nodes": len(nodes), "relationships": len(rels)}
    finally:
        try:
            driver.close()
        except Exception:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="备份 MySQL／Neo4j／向量索引并做导入回验")
    ap.add_argument("--dry-run", action="store_true", help="只检查并打印计划，不写文件")
    ap.add_argument("--out", default=DEFAULT_OUT_ROOT, help="输出根目录（默认 交付物/10-部署/备份）")
    ap.add_argument("--keep", type=int, default=3,
                    help="只保留最近 N 份备份目录（默认 3；仅清理本脚本产物）")
    ap.add_argument("--skip-verify", action="store_true",
                    help="没有迁移账号时跳过临时库回验；manifest 会标记 verify.skipped=true")
    args = ap.parse_args(argv)
    if args.keep < 1:
        ap.error("--keep 必须 ≥ 1（至少保留本次备份）")

    print("=" * 78)
    print("备份%s（仓库根：%s）" % ("（dry-run，不写文件）" if args.dry_run else "", ROOT))
    print("=" * 78)

    try:
        import config
    except SystemExit as exc:
        print("[FAIL] 后端配置不可加载：%s" % str(exc).splitlines()[0])
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = os.path.join(args.out, stamp)
    mysqldump = _find_mysql_bin("mysqldump")
    mysql_cli = _find_mysql_bin("mysql")

    print("  MySQL 数据库   = %s" % config._LOCAL["mysql_database"])       # noqa: SLF001
    print("  Neo4j          = %s" % config.neo4j_params()["uri"])
    print("  mysqldump      = %s" % (mysqldump or "未找到"))
    print("  mysql 客户端   = %s" % (mysql_cli or "未找到"))
    print("  输出目录       = %s" % target)
    print("  保留份数       = %d（更旧的同格式备份目录会在成功后清理）" % args.keep)
    if not (mysqldump and mysql_cli):
        print("[FAIL] 找不到 mysqldump／mysql 客户端，无法完成备份与回验。")
        return 1

    # 先做只读连通性检查（dry-run 也做，确认「现在能备份」）
    conn, db_params = None, None
    try:
        conn, db_params = _connect(config)
        with conn.cursor() as cur:
            counts_before = _db_counts(cur)
        print("  六表计数       = %s" % json.dumps(counts_before, ensure_ascii=False, sort_keys=True))
    except Exception as exc:                               # noqa: BLE001
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print("[FAIL] MySQL 连接／计数失败：%s" % first)
        return 1
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    free_bytes = shutil.disk_usage(os.path.dirname(args.out) or ROOT).free
    print("  可用磁盘       = %.1f GB" % (free_bytes / 1024.0 / 1024.0 / 1024.0))
    if free_bytes < 1024 * 1024 * 1024:
        print("[WARN] 可用磁盘不足 1 GB，备份可能失败。")

    verify_db = "ashare_qa_bakverify_" + stamp
    if args.skip_verify:
        print("  导入回验       = 跳过（--skip-verify；manifest 将如实标记）")
    elif args.dry_run:
        print("  回验权限       = dry-run 不建探针库；真实运行会在写文件前预检 CREATE/DROP")
    else:
        ok, detail = _preflight_verify_db(db_params, verify_db)
        if not ok:
            print("[FAIL] 导入回验需要 CREATE/DROP DATABASE 权限，当前账号不具备：%s" % detail)
            print("       运行期账号仅 DML。请改用迁移账号环境变量运行：")
            print("         set ASHARE_MYSQL_USER=<迁移账号>")
            print("         set ASHARE_MYSQL_PASSWORD=<迁移口令>")
            print("       或显式加 --skip-verify 生成「未回验」备份（manifest 会如实标记）。")
            print("       未创建任何备份目录／文件。")
            return 1
        print("  回验权限       = CREATE/DROP DATABASE 预检通过")

    if args.dry_run:
        print("\n[dry-run] 计划：")
        print("  1. mysqldump --single-transaction → %s/mysql/ashare_qa.sql" % target)
        print("  2. Neo4j 逻辑导出 → %s/neo4j/{nodes,relationships}.jsonl" % target)
        print("  3. 复制向量索引三件 → %s/vector/" % target)
        print("  4. 建临时库回验 dump，逐表比对后 DROP DATABASE%s"
              % ("（已指定 --skip-verify，将跳过）" if args.skip_verify else "（写文件前先做权限预检）"))
        print("  5. 写 manifest.json（sha256／计数／版本，不含口令）")
        print("  6. 保留最近 %d 份备份（含本次待生成的一份），清理更旧的同格式目录：" % args.keep)
        existing = _list_backup_dirs(args.out)
        print("     当前可识别 %d 份" % len(existing))
        # 模拟「本次备份已生成」后的状态：现有目录里只需再留 keep-1 份
        _prune_backups(args.out, args.keep - 1, dry_run=True)
        print("\n结论：检查通过，可执行真实备份。退出码 0。")
        return 0

    out_mysql = os.path.join(target, "mysql")
    out_neo4j = os.path.join(target, "neo4j")
    out_vector = os.path.join(target, "vector")
    for path in (out_mysql, out_neo4j, out_vector):
        os.makedirs(path, exist_ok=True)

    option_path, cleanup_option = _option_file(
        db_params["password"], db_params["host"], db_params["port"], db_params["user"])
    verify_created = False
    manifest = {
        "schema": "stage11-backup-1.0",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "env": config.ENV_NAME,
        "mysql": {"database": db_params.get("database"), "tables": counts_before},
        "neo4j": {"uri": config.neo4j_params()["uri"]},
        "files": [],
        "verify": {"temp_database": verify_db, "imported": False, "counts_match": False,
                   "skipped": bool(args.skip_verify),
                   "reason": "--skip-verify" if args.skip_verify else ""},
        "retention": {"keep": args.keep, "deleted": []},
    }
    started = time.perf_counter()
    try:
        # ---------------------------------------------------------- MySQL dump
        dump_path = os.path.join(out_mysql, "ashare_qa.sql")
        print("\n[1/4] mysqldump → %s" % os.path.relpath(dump_path, ROOT))
        cmd = [mysqldump, "--defaults-extra-file=" + option_path,
               "--single-transaction", "--quick", "--no-tablespaces",
               "--set-gtid-purged=OFF", "--default-character-set=utf8mb4",
               "--hex-blob", db_params.get("database")]
        with open(dump_path, "wb") as out:
            proc = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError("mysqldump 失败：%s"
                               % (proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:]))
        print("      %.2f MB，sha256=%s"
              % (os.path.getsize(dump_path) / 1024.0 / 1024.0, _sha256(dump_path)[:16]))

        # ---------------------------------------------------------- Neo4j 导出
        print("\n[2/4] Neo4j 逻辑导出")
        neo = _export_neo4j(config, out_neo4j)
        manifest["neo4j"].update(neo)
        print("      节点 %(nodes)d，关系 %(relationships)d" % neo)

        # ---------------------------------------------------------- 向量索引
        print("\n[3/4] 复制向量索引三件")
        for src, name in ((config.VECTOR_INDEX_PATH, "faiss.index"),
                          (config.VECTOR_MAP_PATH, "vector_map.jsonl"),
                          (config.BUILD_META_PATH, "build_meta.json")):
            dst = os.path.join(out_vector, name)
            shutil.copy2(src, dst)
            print("      %-18s %.2f MB" % (name, os.path.getsize(dst) / 1024.0 / 1024.0))

        # ---------------------------------------------------------- 导入回验
        if args.skip_verify:
            print("\n[4/4] 导入回验：按 --skip-verify 跳过（manifest 已标记 verify.skipped=true）")
        else:
            print("\n[4/4] 导入回验：建临时库 → 灌入 dump → 逐表比对 → 删库")
            import pymysql
            admin = pymysql.connect(connect_timeout=5, read_timeout=120,
                                    cursorclass=pymysql.cursors.DictCursor, **db_params)
            try:
                with admin.cursor() as cur:
                    cur.execute("CREATE DATABASE `%s` CHARACTER SET utf8mb4 "
                                "COLLATE utf8mb4_0900_ai_ci" % verify_db)
                admin.commit()
                verify_created = True
                import_cmd = [mysql_cli, "--defaults-extra-file=" + option_path,
                              "--default-character-set=utf8mb4", verify_db]
                with open(dump_path, "rb") as src:
                    proc = subprocess.run(import_cmd, stdin=src, stderr=subprocess.PIPE)
                if proc.returncode != 0:
                    raise RuntimeError("mysql 导入临时库失败：%s"
                                       % (proc.stderr.decode("utf-8", "replace").strip().splitlines()[-1:]))
                with admin.cursor() as cur:
                    cur.execute("USE `%s`" % verify_db)
                    counts_after = _db_counts(cur)
                manifest["verify"]["imported"] = True
                manifest["verify"]["counts"] = counts_after
                manifest["verify"]["counts_match"] = counts_after == counts_before
                for table in VERIFY_TABLES:
                    same = counts_after.get(table) == counts_before.get(table)
                    print("      %-16s 源 %d／回验 %d  %s"
                          % (table, counts_before.get(table, -1), counts_after.get(table, -1),
                             "OK" if same else "FAIL"))
                if not manifest["verify"]["counts_match"]:
                    raise RuntimeError("导入后计数与源库不一致")
            finally:
                try:
                    if verify_created:
                        with admin.cursor() as cur:
                            cur.execute("DROP DATABASE `%s`" % verify_db)
                        admin.commit()
                        print("      临时库已删除：%s" % verify_db)
                finally:
                    admin.close()

        # ---------------------------------------------------------- manifest
        for base, _, names in os.walk(target):
            for name in names:
                if name == "manifest.json":
                    continue
                path = os.path.join(base, name)
                manifest["files"].append({
                    "path": os.path.relpath(path, target).replace("\\", "/"),
                    "bytes": os.path.getsize(path),
                    "sha256": _sha256(path),
                })
        manifest["files"].sort(key=lambda x: x["path"])
        manifest["elapsed_seconds"] = round(time.perf_counter() - started, 2)
        manifest_path = os.path.join(target, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        print("\n备份完成：%s" % target)
        print("  manifest：%s（%d 个文件）"
              % (os.path.relpath(manifest_path, ROOT), len(manifest["files"])))

        # ---------------------------------------------------------- 保留期清理
        # 必须在 manifest 写好后执行：本脚本按「目录内有 manifest.json」识别自家产物，
        # 这样本次备份才算进「最近 N 份」。
        print("\n[保留期] 只保留最近 %d 份备份（含本次）" % args.keep)
        deleted = _prune_backups(args.out, args.keep, protect=target)
        if deleted:
            manifest["retention"]["deleted"] = deleted
            with open(manifest_path, "w", encoding="utf-8", newline="\n") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
                f.write("\n")
            print("      已清理 %d 份旧备份（清单已回写 manifest）" % len(deleted))
        else:
            print("      没有需要清理的旧备份。")

        if args.skip_verify:
            print("结论：备份文件已生成，但**未做导入回验**（--skip-verify；manifest verify.skipped=true）。退出码 0。")
        else:
            print("结论：备份＋导入回验通过。退出码 0。")
        return 0
    except Exception as exc:                               # noqa: BLE001
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        print("\n[FAIL] %s" % first)
        print("      已完成的部分保留在：%s" % target)
        return 1
    finally:
        cleanup_option()


if __name__ == "__main__":
    raise SystemExit(main())
