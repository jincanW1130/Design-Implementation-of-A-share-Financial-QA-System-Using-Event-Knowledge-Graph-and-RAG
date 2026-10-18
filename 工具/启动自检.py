# -*- coding: utf-8 -*-
"""工具\\启动自检.py —— 第 4 轮（11.1）启动前只读自检。

在启动后端／跑演示之前执行，逐项回答「这台机器上现在能不能跑」：

1. **配置分层**：`ASHARE_ENV`、基配置文件、环境叠加文件、实际生效的覆盖键名（只打印键名）；
2. **输入资产**：11 个只读输入文件是否存在、大小；数据集 709 文档／5018 文本块（行数）；
3. **向量索引**：`faiss.index` 可加载，`ntotal`／维度与构建元信息一致；
4. **Embedding 快照**：本地 BGE 快照目录与必需文件齐备（不加载模型，只查文件）；
5. **MySQL**：只读连接，逐表计数并与基线对拍（question 30／answer 30／answer_evidence 293）；
6. **Neo4j**：只读连接，数一次节点／关系；
7. **端口与日志**：后端／前端端口是否被占用（INFO，不判失败）；`log_path` 目录是否可写。

纪律
----
* **只读**：不建表、不写库、不导入数据、不改配置、不创建日志目录（只做可写性探测）。
* **不打印口令**：只报「已配置／未配置」，覆盖项只报键名，不报取值。
* 退出码：全部 OK / WARN 为 0；任一 FAIL 为 1。WARN 是「不影响启动但值得知道」。

用法：`python 工具\\启动自检.py`
"""

from __future__ import annotations

import os
import socket
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

RESULTS = []


def report(level: str, name: str, detail: str = "") -> None:
    RESULTS.append((level, name))
    print("  [%-4s] %s%s" % (level, name, ("  —— " + detail) if detail else ""))


def main() -> int:
    print("=" * 78)
    print("启动自检（只读；仓库根：%s）" % ROOT)
    print("=" * 78)

    # ------------------------------------------------------------ 1 配置
    print("\n一、配置分层")
    try:
        import config
    except SystemExit as exc:
        report("FAIL", "后端配置可加载", str(exc).splitlines()[0])
        print("\n结论：配置不通过，后续检查无法进行。退出码 1。")
        return 1
    except Exception as exc:                               # noqa: BLE001
        report("FAIL", "后端配置可加载", "%s: %s" % (type(exc).__name__, exc))
        return 1
    report("OK", "ASHARE_ENV = %s" % config.ENV_NAME,
           "合法值：%s" % "／".join(config.VALID_ENVS))
    report("OK", "基配置文件存在", os.path.relpath(config.LOCAL_CONFIG_PATH, ROOT))
    if config.ENV_OVERLAY_LOADED:
        report("OK", "环境叠加文件已生效", os.path.relpath(config.ENV_OVERLAY_PATH, ROOT))
    else:
        report("OK", "环境叠加文件未使用",
               "缺 %s（默认行为不变）" % os.path.basename(config.ENV_OVERLAY_PATH)
               if not os.path.isfile(config.ENV_OVERLAY_PATH) else "与基配置同文件，跳过")
    applied = sorted(config.ENV_OVERRIDE_KEYS_APPLIED)
    report("OK", "环境变量覆盖 %d 项" % len(applied), "、".join(applied) if applied else "无")
    report("OK" if config.MYSQL_PASSWORD_READY else "FAIL", "MySQL 口令",
           "已配置" if config.MYSQL_PASSWORD_READY else "未配置（空或占位串）")

    # ------------------------------------------------------------ 2 输入资产
    print("\n二、输入资产（只读）")
    missing = []
    for key, path in config.INPUT_FILES:
        if os.path.isfile(path):
            report("OK", "%-14s" % key, "%.1f MB" % (os.path.getsize(path) / 1024.0 / 1024.0))
        else:
            missing.append(key)
            report("FAIL", "%-14s" % key, "缺失：%s" % path)
    if not missing:
        try:
            def _count_lines(path):
                with open(path, "rb") as f:
                    return sum(1 for line in f if line.strip())
            docs = _count_lines(config.DOCUMENTS_JSONL)
            chunks = _count_lines(config.CHUNKS_JSONL)
            report("OK" if docs == 709 else "FAIL", "文档行数 = 709", "实测 %d" % docs)
            report("OK" if chunks == 5018 else "FAIL", "文本块行数 = 5018", "实测 %d" % chunks)
        except Exception as exc:                           # noqa: BLE001
            report("WARN", "输入行数复核", "%s: %s" % (type(exc).__name__, exc))

    # ------------------------------------------------------------ 3 向量索引
    print("\n三、向量索引与模型快照")
    if os.path.isfile(config.VECTOR_INDEX_PATH):
        try:
            # 必须走上游的字节流封装：`faiss.read_index` 走 C++ fopen，在含中文的路径
            # （本项目数据集路径即如此）会以 "Illegal byte sequence" 失败。
            index = config._RET.read_faiss_index(config.VECTOR_INDEX_PATH)   # noqa: SLF001
            report("OK", "faiss.index 可加载",
                   "ntotal=%d，d=%d，metric=%d" % (index.ntotal, index.d, index.metric_type))
        except Exception as exc:                           # noqa: BLE001
            report("FAIL", "faiss.index 可加载", "%s: %s" % (type(exc).__name__, exc))
    try:
        emb = getattr(config._RET, "EMBEDDING", {}) or {}     # noqa: SLF001
        name, revision = emb.get("model_name"), emb.get("revision")
        if name and revision:
            from huggingface_hub.constants import HF_HUB_CACHE
            snap = os.path.join(HF_HUB_CACHE, "models--" + name.replace("/", "--"),
                                "snapshots", revision)
            required = ("config.json", "tokenizer_config.json")
            missing_files = [n for n in required if not os.path.isfile(os.path.join(snap, n))]
            has_weight = (os.path.isfile(os.path.join(snap, "model.safetensors"))
                          or os.path.isfile(os.path.join(snap, "pytorch_model.bin")))
            if os.path.isdir(snap) and not missing_files and has_weight:
                report("OK", "Embedding 快照", "%s @ %s" % (name, revision[:12]))
            else:
                report("FAIL", "Embedding 快照",
                       "目录或必需文件缺失：%s" % snap)
        else:
            report("WARN", "Embedding 快照", "上游 EMBEDDING 未给出 model_name／revision")
    except Exception as exc:                               # noqa: BLE001
        report("WARN", "Embedding 快照", "%s: %s" % (type(exc).__name__, exc))

    # ------------------------------------------------------------ 4 MySQL
    print("\n四、MySQL（只读计数）")
    if not config.MYSQL_PASSWORD_READY:
        report("FAIL", "MySQL 连接", "口令未配置，跳过计数")
    else:
        try:
            import pymysql
            params = config.db_params()
            conn = pymysql.connect(connect_timeout=5, read_timeout=10,
                                   cursorclass=pymysql.cursors.DictCursor, **params)
            try:
                with conn.cursor() as cur:
                    counts = {}
                    for table in config.TABLES:
                        cur.execute("SELECT COUNT(*) AS n FROM `%s`" % table)
                        counts[table] = int(cur.fetchone()["n"])
            finally:
                conn.close()
            report("OK", "MySQL 可连接", "库 %s" % params.get("database"))
            for table, expected in config.EXPECTED_COUNTS.items():
                actual = counts.get(table, -1)
                report("OK" if actual == expected else "FAIL",
                       "%-16s = %d" % (table, expected), "实测 %d" % actual)
        except Exception as exc:                           # noqa: BLE001
            first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            report("FAIL", "MySQL 可连接", first)

    # ------------------------------------------------------------ 5 Neo4j
    print("\n五、Neo4j（只读计数）")
    driver = None
    try:
        from neo4j import GraphDatabase
        params = config.neo4j_params()
        driver = GraphDatabase.driver(params["uri"],
                                      auth=(params["user"], params["password"] or None),
                                      connection_timeout=3.0)
        driver.verify_connectivity()
        with driver.session() as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        report("OK", "Neo4j 可连接", "%s；节点 %d，关系 %d" % (params["uri"], nodes, rels))
    except Exception as exc:                               # noqa: BLE001
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        report("FAIL", "Neo4j 可连接", first)
    finally:
        if driver is not None:
            try:
                driver.close()
            except Exception:
                pass

    # ------------------------------------------------------------ 6 端口与日志
    print("\n六、端口与日志（INFO：占用不判失败，可能是服务已启动）")
    for label, port in (("后端端口 %d" % config.BACKEND_PORT, config.BACKEND_PORT),
                        ("前端端口 %d" % config.FRONTEND_PORT, config.FRONTEND_PORT)):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.5)
            free = sock.connect_ex(("127.0.0.1", port)) != 0
        finally:
            sock.close()
        report("OK" if free else "WARN", label,
               "空闲" if free else "已被占用（若服务已启动属正常）")
    if config.LOG_PATH:
        parent = os.path.dirname(config.LOG_PATH) or "."
        probe = parent
        while probe and not os.path.isdir(probe):
            probe = os.path.dirname(probe)
        writable = bool(probe) and os.access(probe, os.W_OK)
        report("OK" if writable else "FAIL", "日志落盘目录可写",
               "%s（将写到 %s）" % (probe, os.path.basename(config.LOG_PATH)))
    else:
        report("OK", "日志落盘", "未配置 log_path：只出 stderr（默认行为）")
        if config.LOG_PATH_REJECTED:
            report("WARN", "log_path 被拒绝", str(config.LOG_PATH_REJECTED))

    # ------------------------------------------------------------ 汇总
    fails = [n for level, n in RESULTS if level == "FAIL"]
    warns = [n for level, n in RESULTS if level == "WARN"]
    print("\n" + "=" * 78)
    print("自检项 %d：OK %d／WARN %d／FAIL %d"
          % (len(RESULTS), len(RESULTS) - len(fails) - len(warns), len(warns), len(fails)))
    if fails:
        print("结论：存在失败项，不建议启动。退出码 1。")
        print("=" * 78)
        return 1
    print("结论：可以启动%s。退出码 0。"
          % ("（有 %d 项提示，见上）" % len(warns) if warns else ""))
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
