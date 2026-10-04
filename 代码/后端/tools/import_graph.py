# -*- coding: utf-8 -*-
"""代码\\后端\\tools\\import_graph.py —— 第 9 阶段 T3：**图谱导入 Neo4j（幂等）**。

把**现行**`阶段06-事件抽取与知识图谱\\图谱导出\\v2.1_v1_3\\` 的 `nodes.csv`（33 列／3607 行）与
`edges.csv`（9 列／3614 行）导入**本机真实 Neo4j 服务**，并把库内计数与上游
`graph_stats.json` 逐项对拍（《24-第9阶段任务书》第八节 E 组 E1／E2、第五节 硬约束 16）。

上游与只读
----------
两份 CSV 与 `graph_stats.json` 一律 `open(..., "r", encoding="utf-8")` **只读**：
不改输入、不写回、不动 `replay.cypher`（硬约束 15）。路径全部取 `代码\\后端\\config.py`
（唯一参数来源），不写死。Neo4j 连接参数取 `config.neo4j_params()`，**口令只从
`config.local.json` 读**：不写死、不回显、不落盘、不进日志（硬约束 2／4）——
本文件打印的连接信息只含 URI 与账号，**任何情况下不打印口令**。

实现形态（如实登记；《24》第2.4节 的必固化 1）
---------------------------------------------
本机 Neo4j 以 **container 形态运行在 WSL2 内**（镜像 `neo4j:5-community`，容器名
`ashare-neo4j`，端口映射 `7474／7687` → Windows 侧 `bolt://127.0.0.1:7687`）。
**未安装 Docker Desktop、未注册 Windows 服务**；这是真实的本地 Neo4j 实例，
既不是集群也不是高可用／生产部署（硬约束 21、E6）。

幂等策略（硬约束 4）
-------------------
节点：`MERGE (n:<Label> {node_id: row.node_id}) SET n = row.props`。
关系：`MERGE (a)-[r:<TYPE> {…}]->(b) SET r = row.props`。两条路径都按自然键匹配，
重复运行不产生第二份行，库内计数与第一次完全一致。

**关系匹配键的一处如实登记（不许改口径蒙混）**：题述的匹配键是「关系端点 ＋ 类型 ＋
证据三项」。本批 `edges.csv` 实测存在 **5 组共 10 行**满足该键却**不是同一行**的平行边
（v1.2 与 v1.3 两版实测同为 5 组；组内的键与 `role` 见产物的 `dup_key_audit` 字段）
——它们的 `role` 不同（如「主体」与「涉及方」）。若严格只用题述三项作匹配键，`MERGE`
会把每组并成 1 条，库内关系数将**比 `edges.csv` 少 5 条**，与硬约束 16／E1 的
登记读数冲突。
处置：匹配键取「端点 ＋ 类型 ＋ 证据三项 ＋ **role**」——实测「9 列（含 role）全同」的
重复组为 **0**，该键在整份 `edges.csv` 上**唯一**，因此既完整保留全部 3614 行，
又满足幂等。**这不是调整统计口径**：对拍基准就是 `nodes.csv`／`edges.csv` 的去表头
行数本身（现行 v1.3：3607／3614），一个数字都没动；
差别只在「用哪组属性把 CSV 的每一行唯一地认出来」。脚本导入前会**断言该键唯一**，
不唯一即报错退出（见 `check_edge_unique_keys`）。

关系上另写一个 `edge_id` 属性（＝ CSV 行序，0 起，确定性）：它是内存图后端
（`代码\\检索\\graph_query.py`）里每条边的既有标识，也是 G1／G5／G7 排序键的组成部分；
不写它，Neo4j 后端就无法与内存图后端给出结构相同的结果（硬约束 17）。除 `edge_id`
与 CSV 已有的关系列之外，**不新增任何属性**；`EVIDENCED_BY` 按硬约束**不写**
`source_doc_id`／`source_chunk_id`／`confidence` 三项证据属性（《02》第9.2.3节、《24》）。

节点属性只写该行**非空**的列（空串不写，避免把 null 语义污染）；`label` 列即 Neo4j 标签，
不重复写成属性；`event_time`／`publish_time`／`publish_date` 等时间列**以字符串原样存**，
不转成 Neo4j 的时间类型——保持与 CSV 逐字一致，便于对拍。

CLI
---
    python 代码\\后端\\tools\\import_graph.py --dry-run       # 只读 CSV 与统计，不连库
    python 代码\\后端\\tools\\import_graph.py --reset         # 先 MATCH (n) DETACH DELETE n 再全量导入
    python 代码\\后端\\tools\\import_graph.py --verify-only   # 只对拍不写
    python 代码\\后端\\tools\\import_graph.py                 # 幂等导入（不清库）

结束时打印计数对拍表（CSV／Neo4j／graph_stats 三方），**任一项不一致即非零退出**；
并把 `阶段09-前后端系统集成\\集成产出\\graph_counts.json` 落盘（`--dry-run` 不写）。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))            # 代码\后端\tools
_BACKEND = os.path.dirname(_HERE)                             # 代码\后端
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402  （路径注入后再导入）

# 控制台默认 GBK：导入时即把 stdout／stderr 切到 UTF-8（本项目在中文 Windows 上跑）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# --------------------------------------------------------------------------
# 1. 常量（全部取上游 config：标签、关系、证据三项、批量上限）
# --------------------------------------------------------------------------
# 图谱侧常量（NODE_LABELS／RELATIONS／EVIDENCE_ATTRS…）定义在**检索侧** config
# （`代码\检索\config.py`）里；后端 `config.py` 只把它整份导成 `RETRIEVAL` 一项，
# 未逐项透出。这里按后端 config 给出的 `RETRIEVAL_CONFIG_PATH` **按文件路径**加载同一份
# 上游配置（与 `代码\检索\graph_query.py` 读到的是同一处定义），**不另抄一份字面量**
# （硬约束 5：口径以文档为准）。用独立模块名加载，避免与后端 `config` 撞名。
def _load_retrieval_config():
    import importlib.util
    path = config.RETRIEVAL_CONFIG_PATH
    spec = importlib.util.spec_from_file_location("_stage9_graph_retrieval_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_RET = _load_retrieval_config()

NODE_LABELS = list(_RET.NODE_LABELS)                          # 7 个标签
RELATIONS = list(_RET.RELATIONS)                              # 9 条核心关系
SEMANTIC_RELATIONS = list(_RET.SEMANTIC_RELATIONS)            # 8 条（不含 EVIDENCED_BY）
EVIDENCED_BY = _RET.EVIDENCED_BY                               # 'EVIDENCED_BY'
EVIDENCE_ATTRS = list(_RET.EVIDENCE_ATTRS)                    # [source_doc_id, source_chunk_id, confidence]
EDGE_COLUMNS = list(_RET.EDGE_COLUMNS)                        # edges.csv 的 9 列（列名校验用）
EVENT_TRIPLE_FIELDS = list(_RET.EVENT_TRIPLE_FIELDS)

DEFAULT_BATCH = 500                                           # 每批 ≤500（硬约束：UNWIND 分批）

# 关系匹配键的字段（见模块头「关系匹配键的一处如实登记」）
REL_KEY_FIELDS = EVIDENCE_ATTRS + ["role"]

OUT_PATH = os.path.join(config.OUTPUT_DIR, "graph_counts.json")

DEPLOYMENT_NOTE = ("Neo4j 以容器形态运行在 WSL2 内（镜像 neo4j:5-community，容器名 "
                   "ashare-neo4j，端口映射 7474／7687 → Windows 侧 bolt://127.0.0.1:7687）；"
                   "未安装 Docker Desktop、未注册 Windows 服务。这是本地单实例，"
                   "不是集群、不是高可用、不是生产部署。")


# --------------------------------------------------------------------------
# 2. 读输入（只读）与导入前校验
# --------------------------------------------------------------------------
def _s(value) -> str:
    """CSV 字段统一按字符串读；None → 空串；两端空白剔除（只用于判空与展示）。"""
    return (value or "").strip()


def read_csv(path: str) -> tuple:
    """只读一份 CSV，返回 `(列名列表, 行列表)`；行内按字段名取值，**不按位置解析**。"""
    if not os.path.isfile(path):
        raise SystemExit("输入不存在：%s（本阶段只读上游，不做兜底）" % path)
    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return cols, rows


def check_nodes(cols: list, rows: list) -> None:
    """节点导入前校验：列名齐全、`label` 在 7 个标签内、`node_id` 非空且唯一。"""
    for needed in ("node_id", "label", "name"):
        if needed not in cols:
            raise SystemExit("nodes.csv 缺列 %r（实测列：%s）" % (needed, "、".join(cols)))
    bad_label = sorted({_s(r.get("label")) for r in rows} - set(NODE_LABELS))
    if bad_label:
        raise SystemExit("nodes.csv 出现 NODE_LABELS 之外的标签：%s" % "、".join(bad_label))
    empty = [i for i, r in enumerate(rows) if not _s(r.get("node_id"))]
    if empty:
        raise SystemExit("nodes.csv 有 %d 行 node_id 为空（首行行号 %s）" % (len(empty), empty[0]))
    seen = {}
    dup = []
    for i, r in enumerate(rows):
        nid = r["node_id"]
        if nid in seen:
            dup.append((nid, seen[nid], i))
        else:
            seen[nid] = i
    if dup:
        raise SystemExit("nodes.csv 的 node_id 不唯一（%d 组，首组 %s）——MERGE 会并成一行，"
                         "与 nodes.csv 的 %d 行冲突；不做静默合并。"
                         % (len(dup), dup[0], len(rows)))


def check_edges(cols: list, edge_rows: list, node_ids: set) -> None:
    """边导入前校验：列名与 `config.EDGE_COLUMNS` 逐字一致、端点存在、关系名合法。"""
    expected = list(EDGE_COLUMNS)
    if cols != expected:
        raise SystemExit("edges.csv 列与检索侧 config.EDGE_COLUMNS 不一致：\n  实测 %s\n  期望 %s"
                         % ("、".join(cols), "、".join(expected)))
    bad_rel = sorted({_s(r.get("relation")) for r in edge_rows} - set(RELATIONS))
    if bad_rel:
        raise SystemExit("edges.csv 出现 RELATIONS 之外的关系类型：%s" % "、".join(bad_rel))
    dangling = [(i, r["head_id"], r["tail_id"]) for i, r in enumerate(edge_rows)
                if r["head_id"] not in node_ids or r["tail_id"] not in node_ids]
    if dangling:
        raise SystemExit("edges.csv 有 %d 条边的端点不在 nodes.csv 内（首条 %s）——"
                         "导入会凭空造出无标签节点，与 nodes.csv 的 %d 个节点冲突；"
                         "不做静默丢弃。" % (len(dangling), dangling[0], len(node_ids)))


def check_edge_unique_keys(edge_rows: list) -> dict:
    """断言 MERGE 匹配键在整份 `edges.csv` 上唯一（见模块头「关系匹配键」）。

    返回 `{"semantic_key": 键字段, "semantic_dups": […], "evidenced_dups": […],
           "role_only_dups": […]}`。

    * 语义边（8 条）：键 ＝ 端点 ＋ 类型 ＋ 证据三项 ＋ role，必须唯一；
    * `EVIDENCED_BY`：不带证据三项，键 ＝ 端点 ＋ 类型，必须唯一；
    * 另报一份「只用题述三项作键」的重复清单，供留痕与报告引用——
      **它非空正是本文件把 role 并入键的原因**，不是失败。
    """
    def counter(keyf, rows):
        c = {}
        for i, r in enumerate(rows):
            c.setdefault(keyf(r), []).append(i)
        return {k: v for k, v in c.items() if len(v) > 1}

    sem = [r for r in edge_rows if r["relation"] != EVIDENCED_BY]
    evd = [r for r in edge_rows if r["relation"] == EVIDENCED_BY]

    sem_dups = counter(lambda r: (r["head_id"], r["relation"], r["tail_id"],
                                  r["source_doc_id"], r["source_chunk_id"], r["confidence"],
                                  r["role"]), sem)
    evd_dups = counter(lambda r: (r["head_id"], r["relation"], r["tail_id"]), evd)
    role_only_dups = counter(lambda r: (r["head_id"], r["relation"], r["tail_id"],
                                        r["source_doc_id"], r["source_chunk_id"], r["confidence"]),
                             sem)
    if sem_dups:
        raise SystemExit("8 条语义边里存在 %d 组「端点＋类型＋证据三项＋role」完全相同的边：%s——"
                         "MERGE 会并成一行，与 edges.csv 的 %d 行冲突；不做静默合并。"
                         % (len(sem_dups), list(sem_dups.items())[:3], len(edge_rows)))
    if evd_dups:
        raise SystemExit("EVIDENCED_BY 里存在 %d 组「端点＋类型」完全相同的边：%s——"
                         "MERGE 会并成一行，与 edges.csv 的 %d 行冲突。"
                         % (len(evd_dups), list(evd_dups.items())[:3], len(edge_rows)))
    return {"semantic_key_fields": ["head_id"] + REL_KEY_FIELDS + ["relation", "tail_id"],
            "semantic_dup_groups": 0,
            "evidenced_by_key_fields": ["head_id", "relation", "tail_id"],
            "evidenced_by_dup_groups": 0,
            "three_field_only_dup_groups": len(role_only_dups),
            "three_field_only_dups": [
                {"key": list(k), "row_indexes": v,
                 "roles": [edge_rows[i]["role"] for i in v]}
                for k, v in sorted(role_only_dups.items())]}


# --------------------------------------------------------------------------
# 3. 构造导入行
# --------------------------------------------------------------------------
def build_node_rows(rows: list) -> dict:
    """按标签分组：`{label: [{"node_id": …, "props": {…非空列…}}]}`。

    属性只写**该行非空的列**（空串不写），`label` 列不写成属性（它已是 Neo4j 标签）。
    值原样存（不做 strip、不做类型转换）——与 CSV 逐字一致，便于对拍。
    """
    out = {label: [] for label in NODE_LABELS}
    for row in rows:
        label = _s(row.get("label"))
        props = {}
        for key, value in row.items():
            if key == "label":
                continue                                   # label 即 Neo4j 标签
            if value is None:
                continue
            if not _s(value):
                continue                                   # 空串不写（避免 null 语义污染）
            props[key] = value
        out[label].append({"node_id": row["node_id"], "props": props})
    return out


def build_edge_rows(edge_rows: list) -> dict:
    """按关系类型分组：`{relation: [{"head_id","tail_id","edge_id","props"}…]}`。

    * `edge_id` ＝ CSV 行序（0 起，确定性；内存图后端沿用的同一条边的标识）；
    * 8 条语义边：props 含 `edge_id` ＋ 证据三项 ＋ `role`（本批 `role` 有空值，
      **空 role 一律写空串**——它是 MERGE 匹配键的一部分，键必须对每行都存在；
      实测该键在整份 CSV 上唯一，见 `check_edge_unique_keys`）
      ＋ 非空的 `valid_from`／`valid_to`（本批全空，故不写）；
    * `EVIDENCED_BY`：props **只有** `edge_id`——**不写**证据三项（硬约束）。
    """
    out = {rel: [] for rel in RELATIONS}
    for idx, row in enumerate(edge_rows):
        rel = row["relation"]
        props = {"edge_id": idx}
        if rel != EVIDENCED_BY:
            for attr in EVIDENCE_ATTRS:
                props[attr] = row.get(attr, "")
            props["role"] = row.get("role", "")
            for attr in ("valid_from", "valid_to"):
                if _s(row.get(attr)):
                    props[attr] = row[attr]
        out[rel].append({"head_id": row["head_id"], "tail_id": row["tail_id"],
                         "edge_id": idx, "props": props})
    return out


def csv_counts(rows: list, edge_rows: list) -> dict:
    """从两份 CSV 直接统计（去表头计数）：总节点／总关系／逐标签／逐关系。"""
    by_label = {label: 0 for label in NODE_LABELS}
    for r in rows:
        by_label[_s(r.get("label"))] += 1
    by_rel = {rel: 0 for rel in RELATIONS}
    for r in edge_rows:
        by_rel[_s(r.get("relation"))] += 1
    return {"nodes_total": len(rows), "edges_total": len(edge_rows),
            "nodes_by_label": by_label, "edges_by_relation": by_rel}


# --------------------------------------------------------------------------
# 4. Neo4j 连接与 DDL
# --------------------------------------------------------------------------
def connect_driver():
    """建 Neo4j driver（参数取 `config.neo4j_params()`；**口令不回显、不进日志**）。"""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:                                  # 本阶段不新增依赖
        raise SystemExit("未安装 neo4j 驱动：%s\n本阶段不新增依赖，请使用已装的 neo4j 包。"
                         % exc)
    params = config.neo4j_params()
    driver = GraphDatabase.driver(params["uri"], auth=(params["user"], params["password"]))
    return driver


def connect_friendly():
    """建连接并把「服务不可达／认证失败」翻译成**不含口令**的明确错误。"""
    driver = connect_driver()
    params = config.neo4j_params()
    try:
        driver.verify_connectivity()
    except Exception as exc:                                    # noqa: BLE001
        with _suppress(driver.close):
            pass
        name = type(exc).__name__
        hint = ("服务未启动？本机 Neo4j 以容器形态运行在 WSL2 内——"
                "先执行：wsl -d Ubuntu -u root -- docker start ashare-neo4j")
        raise SystemExit("Neo4j 连接失败（%s）：%s\n%s\n（连接串可打印，口令不打印）"
                         % (name, params["uri"], hint))
    return driver


class _suppress:
    """极简 `contextlib.suppress` 替代，避免额外 import。"""

    def __init__(self, func):
        self.func = func

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        try:
            self.func()
        except Exception:                                       # noqa: BLE001
            pass
        return True


def ddl_statements() -> list:
    """约束与索引语句（全部 `IF NOT EXISTS`，可重复执行）。

    * 每个标签一条 `node_id` 唯一约束（MERGE 的匹配键要它才快且强）；
    * `Company(stock_code)`／`Company(name)` 与其余各标签的 `name` 索引
      （查询层按名称／代码解析实体时用）。
    """
    stmts = []
    for label in NODE_LABELS:
        stmts.append("CREATE CONSTRAINT con_%s_node_id IF NOT EXISTS "
                     "FOR (n:%s) REQUIRE n.node_id IS UNIQUE" % (label.lower(), label))
    index_specs = [("idx_company_stock_code", "Company", "stock_code"),
                   ("idx_company_name", "Company", "name")]
    index_specs += [("idx_%s_name" % label.lower(), label, "name")
                    for label in NODE_LABELS if label != "Company"]
    for name, label, prop in index_specs:
        stmts.append("CREATE INDEX %s IF NOT EXISTS FOR (n:%s) ON (n.%s)"
                     % (name, label, prop))
    return stmts


def apply_ddl(session) -> int:
    stmts = ddl_statements()
    for stmt in stmts:
        session.run(stmt).consume()
    return len(stmts)


NODE_CYPHER = ("UNWIND $rows AS row "
               "MERGE (n:%s {node_id: row.node_id}) "
               "SET n = row.props")

SEMANTIC_REL_CYPHER = ("UNWIND $rows AS row "
                       "MATCH (a {node_id: row.head_id}) "
                       "MATCH (b {node_id: row.tail_id}) "
                       "MERGE (a)-[r:%s {source_doc_id: row.props.source_doc_id, "
                       "source_chunk_id: row.props.source_chunk_id, "
                       "confidence: row.props.confidence, role: row.props.role}]->(b) "
                       "SET r = row.props")

EVIDENCED_BY_CYPHER = ("UNWIND $rows AS row "
                       "MATCH (a {node_id: row.head_id}) "
                       "MATCH (b {node_id: row.tail_id}) "
                       "MERGE (a)-[r:EVIDENCED_BY]->(b) "
                       "SET r = row.props")


# --------------------------------------------------------------------------
# 5. 导入
# --------------------------------------------------------------------------
def import_nodes(session, node_rows: dict, batch: int, verbose: bool = True) -> int:
    total = 0
    for label in NODE_LABELS:
        rows = node_rows.get(label) or []
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            session.run(NODE_CYPHER % label, rows=chunk).consume()
            total += len(chunk)
            if verbose:
                print("  [节点] %-12s 第 %d 批：%d 行（累计 %d）"
                      % (label, i // batch + 1, len(chunk), total))
    return total


def import_edges(session, edge_rows: dict, batch: int, verbose: bool = True) -> int:
    total = 0
    for rel in RELATIONS:
        rows = edge_rows.get(rel) or []
        if not rows:
            if verbose:
                print("  [关系] %-16s 本批 0 条（上游即为 0；不建关系类型）" % rel)
            continue
        cypher = EVIDENCED_BY_CYPHER if rel == EVIDENCED_BY else SEMANTIC_REL_CYPHER % rel
        for i in range(0, len(rows), batch):
            chunk = rows[i:i + batch]
            session.run(cypher, rows=chunk).consume()
            total += len(chunk)
            if verbose:
                print("  [关系] %-16s 第 %d 批：%d 条（累计 %d）"
                      % (rel, i // batch + 1, len(chunk), total))
    return total


def reset_graph(session, verbose: bool = True) -> int:
    """`MATCH (n) DETACH DELETE n`（先删关系再删节点，DETACH 一步到位）。"""
    rec = session.run("MATCH (n) DETACH DELETE n RETURN count(n) AS c").single()
    removed = int(rec["c"]) if rec else 0
    if verbose:
        print("[reset] MATCH (n) DETACH DELETE n：删除 %d 个节点（连带其全部关系）" % removed)
    return removed


# --------------------------------------------------------------------------
# 6. 库内计数与对拍
# --------------------------------------------------------------------------
def db_counts(session) -> dict:
    """从 Neo4j 查计数：总量 ＋ 逐标签 ＋ 逐关系（**逐项查**，不做推算）。"""
    nodes_total = int(session.run("MATCH (n) RETURN count(n) AS c").single()["c"])
    edges_total = int(session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"])
    by_label = {}
    for label in NODE_LABELS:
        by_label[label] = int(session.run(
            "MATCH (n:%s) RETURN count(n) AS c" % label).single()["c"])
    by_rel = {}
    for rel in RELATIONS:
        by_rel[rel] = int(session.run(
            "MATCH ()-[r:%s]->() RETURN count(r) AS c" % rel).single()["c"])
    return {"nodes_total": nodes_total, "edges_total": edges_total,
            "nodes_by_label": by_label, "edges_by_relation": by_rel}


def neo4j_info(session) -> dict:
    row = session.run("CALL dbms.components() YIELD name, versions, edition "
                      "RETURN name, versions[0] AS version, edition").single()
    params = config.neo4j_params()
    return {"uri": params["uri"], "user": params["user"],
            "kernel": row["name"] if row else None,
            "version": row["version"] if row else None,
            "edition": row["edition"] if row else None,
            "deployment": DEPLOYMENT_NOTE}


def stats_counts(stats: dict) -> dict:
    """从 `graph_stats.json` 取对拍基准（逐标签／逐关系；缺失的键按 0 处理并标注）。"""
    c = stats.get("counts") or {}
    by_label = c.get("nodes_by_label") or {}
    by_rel = c.get("edges_by_relation") or {}
    return {"nodes_total": c.get("nodes_total"), "edges_total": c.get("edges_total"),
            "nodes_by_label": {k: by_label.get(k, 0) for k in NODE_LABELS},
            "edges_by_relation": {k: by_rel.get(k, 0) for k in RELATIONS},
            "nodes_by_label_raw_keys": sorted(by_label),
            "edges_by_relation_raw_keys": sorted(by_rel)}


def compare_rows(csv_c: dict, neo_c: dict, st_c: dict) -> tuple:
    """三方对拍表：CSV／Neo4j／graph_stats 逐项给读数与结论（不成立即整体 False）。"""
    rows = []

    def add(item, c, n, s):
        ok = True
        if c is not None and n is not None and c != n:
            ok = False
        if c is not None and s is not None and c != s:
            ok = False
        if n is not None and s is not None and n != s:
            ok = False
        rows.append({"item": item, "csv": c, "neo4j": n, "graph_stats": s, "match": ok})

    add("nodes_total", csv_c["nodes_total"], neo_c.get("nodes_total"), st_c["nodes_total"])
    add("edges_total", csv_c["edges_total"], neo_c.get("edges_total"), st_c["edges_total"])
    for label in NODE_LABELS:
        add("node:%s" % label, csv_c["nodes_by_label"][label],
            (neo_c.get("nodes_by_label") or {}).get(label), st_c["nodes_by_label"][label])
    for rel in RELATIONS:
        add("edge:%s" % rel, csv_c["edges_by_relation"][rel],
            (neo_c.get("edges_by_relation") or {}).get(rel), st_c["edges_by_relation"][rel])
    return rows, all(r["match"] for r in rows)


def print_table(rows: list) -> None:
    def fmt(v):
        return "—" if v is None else str(v)

    print("  %-26s %8s %8s %12s   %s" % ("项目", "CSV", "Neo4j", "graph_stats", "结论"))
    print("  " + "-" * 70)
    for r in rows:
        print("  %-26s %8s %8s %12s   %s"
              % (r["item"], fmt(r["csv"]), fmt(r["neo4j"]), fmt(r["graph_stats"]),
                 "一致" if r["match"] else "**不一致**"))


# --------------------------------------------------------------------------
# 7. 留痕
# --------------------------------------------------------------------------
def write_graph_counts(csv_c, neo_c, st_c, rows, all_match, info, mode,
                       dup_info, inputs, extra=None) -> str:
    payload = {
        "schema": "stage9-graph-counts-1.0",
        "stage": "第 9 阶段（前后端系统集成）",
        "task": "T3 图谱服务化：Neo4j 导入与计数对拍",
        "mode": mode,
        "neo4j": info,
        "counts": {"nodes_total": (neo_c or {}).get("nodes_total"),
                   "edges_total": (neo_c or {}).get("edges_total"),
                   "nodes_by_label": (neo_c or {}).get("nodes_by_label"),
                   "edges_by_relation": (neo_c or {}).get("edges_by_relation")},
        "csv_counts": csv_c,
        "graph_stats_counts": st_c,
        "comparison": rows,
        "all_match": bool(all_match),
        # 2026-10-03：原为写死字符串，切到 v1.3 后仍印 2802／2736（**产物在撒谎**），
        # 现改为按本次实际读入的 CSV 计数生成。
        "comparison_basis": ("对拍基准 ＝ nodes.csv／edges.csv 的去表头行数本身："
                             "节点 %d／关系 %d（两版口径都不写死，一律现场计数）"
                             % (csv_c["nodes_total"], csv_c["edges_total"])),
        "merge_key_note": (
            "节点 MERGE 键 ＝ node_id；语义边 MERGE 键 ＝ 端点＋类型＋证据三项＋role；"
            "EVIDENCED_BY 键 ＝ 端点＋类型（不带证据三项）。role 并入键的原因见本文件"
            "模块头与 dup_key_audit 字段：仅用『端点＋类型＋证据三项』会把 %d 组 role 不同"
            "的平行边各并成 1 条，关系数将变成 %d ≠ %d。"
            % (dup_info["three_field_only_dup_groups"],
               csv_c["edges_total"] - dup_info["three_field_only_dup_groups"],
               csv_c["edges_total"])),
        "dup_key_audit": dup_info,
        "relation_types_present": [r for r in RELATIONS
                                   if (neo_c or {}).get("edges_by_relation", {}).get(r, 0) > 0],
        "relation_types_zero": [r for r in RELATIONS
                                if (neo_c or {}).get("edges_by_relation", {}).get(r, 0) == 0],
        "evidenced_by_note": ("EVIDENCED_BY 不写 source_doc_id／source_chunk_id／confidence "
                             "三项证据属性（《02》第9.2.3节、《24》硬约束）；它另带 edge_id，"
                             "只用于展示来源文档、不产生文本块级候选。"),
        "inputs": inputs,
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    if extra:
        payload.update(extra)
    config.write_json(OUT_PATH, payload)
    return OUT_PATH


def fingerprint_inputs() -> dict:
    out = {}
    for name, path in (("nodes_csv", config.NODES_CSV), ("edges_csv", config.EDGES_CSV),
                       ("graph_stats", config.GRAPH_STATS_PATH)):
        out[name] = {"path": os.path.relpath(path, config.ROOT),
                     "bytes": os.path.getsize(path),
                     "sha256": config.sha256_file(path)}
    return out


# --------------------------------------------------------------------------
# 8. 主流程
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 9 阶段 T3：图谱导入 Neo4j（幂等）＋ 计数三方对拍（CSV↔Neo4j↔graph_stats，"
                    "规模一律现场计数、不写死）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只读 CSV 与统计、不连库、不写库（对拍只做 CSV ↔ graph_stats 两方）")
    parser.add_argument("--reset", action="store_true",
                        help="先 MATCH (n) DETACH DELETE n 再全量导入")
    parser.add_argument("--verify-only", action="store_true",
                        help="只对拍库内计数，不写库（仍会落 graph_counts.json）")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH, metavar="N",
                        help="UNWIND 分批大小（默认 %d，硬上限 500）" % DEFAULT_BATCH)
    args = parser.parse_args(argv)

    if args.batch_size <= 0 or args.batch_size > DEFAULT_BATCH:
        print("--batch-size 必须在 1..%d 之间（收到 %r）" % (DEFAULT_BATCH, args.batch_size),
              file=sys.stderr)
        return 2
    if args.dry_run and (args.reset or args.verify_only):
        print("--dry-run 不与 --reset／--verify-only 同用（前者不连库，后两者要连库）",
              file=sys.stderr)
        return 2

    line = "=" * 78
    print(line)
    print("T3 图谱导入 Neo4j（幂等）｜图谱导出物 %s" % config.GRAPH_VERSION)
    print(line)

    # —— 一、读输入（只读）——
    node_cols, node_rows = read_csv(config.NODES_CSV)
    edge_cols, edge_rows = read_csv(config.EDGES_CSV)
    stats = config.read_json(config.GRAPH_STATS_PATH)
    print("  输入 nodes.csv：%d 列／%d 行" % (len(node_cols), len(node_rows)))
    print("  输入 edges.csv：%d 列／%d 行" % (len(edge_cols), len(edge_rows)))
    print("  对拍基准 graph_stats.json：counts.nodes_total=%s  counts.edges_total=%s"
          % ((stats.get("counts") or {}).get("nodes_total"),
             (stats.get("counts") or {}).get("edges_total")))
    print()

    # —— 二、导入前校验（不成立的即报错退出，不做静默合并／丢弃）——
    check_nodes(node_cols, node_rows)
    node_ids = {r["node_id"] for r in node_rows}
    check_edges(edge_cols, edge_rows, node_ids)
    dup_info = check_edge_unique_keys(edge_rows)
    print("  导入前校验：label 合法、node_id 唯一、边端点全部存在 ✓")
    print("  关系匹配键审计：语义边「端点＋类型＋证据三项＋role」重复组 %d；"
          "EVIDENCED_BY「端点＋类型」重复组 %d"
          % (dup_info["semantic_dup_groups"], dup_info["evidenced_by_dup_groups"]))
    print("    · **只用题述三项**「端点＋类型＋证据三项」会撞上的重复组：%d 组（role 不同）"
          % dup_info["three_field_only_dup_groups"])
    for d in dup_info["three_field_only_dups"]:
        print("      %s  行号 %s  role=%s" % (tuple(d["key"]), d["row_indexes"], d["roles"]))
    print()

    c_counts = csv_counts(node_rows, edge_rows)
    node_import = build_node_rows(node_rows)
    edge_import = build_edge_rows(edge_rows)
    s_counts = stats_counts(stats)
    inputs = fingerprint_inputs()

    # —— 三、--dry-run：两方对拍后返回 ——
    if args.dry_run:
        print("--- 逐项统计（CSV，去表头计数）---")
        print("  总节点 %d ／ 总关系 %d" % (c_counts["nodes_total"], c_counts["edges_total"]))
        for label in NODE_LABELS:
            print("    · %-12s %5d" % (label, c_counts["nodes_by_label"][label]))
        for rel in RELATIONS:
            print("    · %-16s %5d" % (rel, c_counts["edges_by_relation"][rel]))
        print()
        rows, all_match = compare_rows(c_counts, {}, s_counts)
        print("--- 与 graph_stats.json 逐项对拍（--dry-run 不连库，Neo4j 列为 —）---")
        print_table(rows)
        print()
        print("  结论：%s" % ("CSV 与 graph_stats 逐项一致" if all_match
                              else "**CSV 与 graph_stats 存在不一致**"))
        print("[--dry-run] 未连库、未写库、未写 graph_counts.json；真导入去掉 --dry-run。")
        print(line)
        return 0 if all_match else 1

    # —— 四、连库 ——
    driver = connect_friendly()
    try:
        with driver.session() as session:
            info = neo4j_info(session)
            print("  已连 Neo4j：%s（%s %s %s）"
                  % (info["uri"], info["kernel"], info["version"], info["edition"]))
            print("  实现形态：%s" % DEPLOYMENT_NOTE)
            print()

            if args.verify_only:
                print("[--verify-only] 只对拍，不写库。")
            else:
                if args.reset:
                    reset_graph(session)
                print("[DDL] 约束与索引：执行 %d 条（全部 IF NOT EXISTS，可重复执行）"
                      % apply_ddl(session))
                print("[导入] 节点（按标签分组 UNWIND，每批 ≤%d）" % args.batch_size)
                n1 = import_nodes(session, node_import, args.batch_size)
                print("[导入] 关系（按关系类型分组 UNWIND，每批 ≤%d）" % args.batch_size)
                n2 = import_edges(session, edge_import, args.batch_size)
                print("[导入] 完成：送批节点 %d、关系 %d" % (n1, n2))

            n_counts = db_counts(session)
            info = neo4j_info(session)
    finally:
        with _suppress(driver.close):
            pass

    # —— 五、三方对拍 ——
    print()
    print("--- 库内计数（Neo4j 实测）---")
    print("  总节点 %d ／ 总关系 %d" % (n_counts["nodes_total"], n_counts["edges_total"]))
    for label in NODE_LABELS:
        print("    · %-12s %5d" % (label, n_counts["nodes_by_label"][label]))
    for rel in RELATIONS:
        print("    · %-16s %5d" % (rel, n_counts["edges_by_relation"][rel]))
    print()
    rows, all_match = compare_rows(c_counts, n_counts, s_counts)
    print("--- 逐项对拍（CSV ↔ Neo4j ↔ graph_stats，任一项不一致即失败）---")
    print_table(rows)
    print()
    print("  结论：%s" % ("三方逐项一致：节点 %d、关系 %d"
                          % (n_counts["nodes_total"], n_counts["edges_total"])
                          if all_match else "**存在不一致——不改口径，如实报出双方读数**"))
    if n_counts["edges_by_relation"].get("SUPPLIES", 0) == 0:
        print("  说明：第 9 条核心关系 SUPPLIES 本批 0 条（上游即为 0），"
              "库内不存在该关系类型——这是数据事实，不是导入遗漏。")

    mode = "verify-only" if args.verify_only else ("reset-import" if args.reset else "import")
    path = write_graph_counts(c_counts, n_counts, s_counts, rows, all_match, info, mode,
                              dup_info, inputs)
    print("\n[留痕] 已写 %s" % os.path.relpath(path, config.ROOT))
    print(line)
    return 0 if all_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
