# -*- coding: utf-8 -*-
"""代码\\后端\\services\\graph_service.py —— 第 9 阶段 T3：**图谱查询服务（双后端）**。

给后端提供与第 7 阶段 `代码\\检索\\graph_query.py` **同一套语义**的图谱查询能力，
后端可在两个**可切换**的实现之间选择：

| 后端名 | 实现 | 说明 |
| --- | --- | --- |
| `neo4j`（默认） | 本文件 `Neo4jGraphQuery` | 把 G1～G7 逐条写成 Cypher，跑在**本机真实 Neo4j 实例**上（`bolt://127.0.0.1:7687`） |
| `memory` | 直接包装第 7 阶段的 `GraphQuery` | 第 7 阶段的内存图后端，**一个字节都没改**，只是 import 复用（硬约束 17：结构相同） |

两个后端**返回同一个 envelope**：`{code, interface, query_key, cypher, sort_key, count,
results, **extra}`；`code` 取值同为 `OK`／`EMPTY`／`NOT_FOUND`／`INVALID_INPUT`
（匹配不到不抛异常）；排序键写法与第 7 阶段逐字相同；证据三项规则一致（除
`EVIDENCED_BY` 外都带 `source_doc_id`／`source_chunk_id`／`confidence`，`EVIDENCED_BY`
的这三项为 `null`）；G5 边界一致（`EVIDENCED_BY` 只落 `document_refs`、不产生文本块级
候选）；G6 空值策略一致（显式参数 `null_policy ∈ {exclude, keep}`，默认取
`config.RETRIEVAL["time_filter_null_policy"]`＝`exclude`）。

后端选择（硬约束 17）
-------------------
`GRAPH_BACKEND` 环境变量 → 后端 `config.py` 的同名开关（若作者日后加上）→ **缺省 `neo4j`**。
命令行 `--backend neo4j|memory` 可临时覆盖，仅用于取证与对拍。

**注意：不改 `代码\\检索\\graph_query.py` 的任何字节**——本文件只 `import` 它，
并且只复用三种东西：`GraphQuery` 类、`CYPHER`（表 18-F 的等效 Cypher 字符串）与
`EVENT_CORE_ATTRS`／`NULL_POLICIES` 等常量。内存后端就是它本人的实例。

`--parity-check`（验收 E5）
--------------------------
对**同一组确定的查询**分别跑两个后端，逐项比对**关键字段**：结果载荷、
**排序键序列**、**节点集合**、**关系集合（edge_id）**、**chunk_id 集合**、
以及 `code`／`count`／`sort_key`。任何一项不一致即**非零退出**并打印明细。

如实登记（写进 README 与报告，不粉饰）
------------------------------------
* 归一化（`_norm`：剔除全部空白＋转小写）在 Cypher 侧用 `reduce` ＋ `replace` 对
  **Python `str.split()` 认的全部空白字符**逐个删除，再 `toLower`——因此与本文件
  `_norm` 在**ASCII 与中日韩字符**上等价。二者仍有理论差异：`toLower()` 走 Java 的
  单字符小写映射，Python `str.lower()` 走 Unicode 全量映射（如 `İ`／`ß` 这类字符会
  不同）。**本批数据里 `name`／`short_name`／`aliases` 不含此类字符**，故实测一致；
  这一点登记为限制。
* 字符串比较／排序：内存后端按 Python 码位排序，Neo4j 按 UTF-16 代码单元排序。
  本批数据全在 BMP 内，实测一致；含增补平面字符时会分叉，登记为限制。
* `_s()`（Python `strip()`）在 Cypher 侧用 `trim()` 近似（Java 空白定义）；本批 CSV
  **没有任何列存在两端空白**（导入前已实测），故实测一致。
* Neo4j 后端在 G6 上按第 7 阶段的写法**逐事件**取 `chunk_id`（与内存后端同样的
  N 次调用），这是行为一致优先于往返次数的一次取舍，登记为已知限制。
* 内存后端返回的 `results` 与 Neo4j 后端**在关键字段上一致**；`cypher` 字段两端同为
  表 18-F 的等效 Cypher 字符串（同一常量）。Neo4j 后端**实际执行**的 Cypher 不塞进
  envelope（以免两端 envelope 出现额外键），改用 `NEO4J_CYPHER` 常量与
  `Neo4jGraphQuery.last_cypher()` 单独给出，供取证。

用法
----
    python 代码\\后端\\services\\graph_service.py --selftest
    python 代码\\后端\\services\\graph_service.py --parity-check
    python 代码\\后端\\services\\graph_service.py --cypher-table
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))              # 交付物/03-代码\后端\services
_BACKEND = os.path.dirname(_HERE)                               # 交付物/03-代码\后端
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402  （后端 config：路径、Neo4j 连接参数；**只读**）

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                                    # noqa: BLE001
            pass

GRAPH_QUERY_PATH = os.path.join(config.ROOT, "交付物/03-代码", "检索", "graph_query.py")
NEO4J_BACKEND = "neo4j"
MEMORY_BACKEND = "memory"
DEFAULT_BACKEND = NEO4J_BACKEND


# --------------------------------------------------------------------------
# 0. 加载第 7 阶段模块（**不改它任何一个字节**）
# --------------------------------------------------------------------------
def _load_module(name: str, path: str):
    import importlib.util
    if not os.path.isfile(path):
        raise SystemExit("模块不存在：%s" % path)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit("无法加载模块 %s（%s）" % (name, path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# `交付物/03-代码\检索\graph_query.py` 内部写的是 `import config`，而本目录也有一个 `config`
# （后端 config）。做法：先把**检索侧** config 以 "config" 之名放进 sys.modules，
# 让 graph_query 在 exec 期间拿到它；加载完成后再把 "config" 换回后端 config。
# graph_query 模块全局里的 `config` 已绑定到检索侧那个模块对象，后面的替换不影响它。
_BACKEND_CONFIG = config
_SAVED_CONFIG = sys.modules.get("config")
RETRIEVAL_CONFIG = _load_module("config", config.RETRIEVAL_CONFIG_PATH)
try:
    _GQ = _load_module("stage7_graph_query", GRAPH_QUERY_PATH)
finally:
    if _SAVED_CONFIG is not None:
        sys.modules["config"] = _SAVED_CONFIG

GraphQuery = _GQ.GraphQuery
CYPHER = _GQ.CYPHER                       # 表 18-F 的等效 Cypher（两端 envelope 共用）
EVENT_CORE_ATTRS = list(_GQ.EVENT_CORE_ATTRS)
NULL_POLICIES = tuple(_GQ.NULL_POLICIES)

RC_OK = _GQ.RC_OK
RC_EMPTY = _GQ.RC_EMPTY
RC_NOT_FOUND = _GQ.RC_NOT_FOUND
RC_INVALID_INPUT = _GQ.RC_INVALID_INPUT

EVIDENCED_BY = RETRIEVAL_CONFIG.EVIDENCED_BY
EVIDENCE_ATTRS = list(RETRIEVAL_CONFIG.EVIDENCE_ATTRS)
EVENT_TYPES = list(RETRIEVAL_CONFIG.EVENT_TYPES)


# --------------------------------------------------------------------------
# 1. 通用小工具（与 graph_query 同名同义）
# --------------------------------------------------------------------------
def _s(value) -> str:
    return (value or "").strip()


def _norm(text: str) -> str:
    """标识归一化：剔除全部空白、转小写（与 `graph_query._norm` 逐字同义）。"""
    return "".join(_s(text).split()).lower()


def _envelope(interface: str, code: str, query_key: dict, sort_key: str,
              results: list, **extra) -> dict:
    """两端共用的返回体形状（`cypher` 取表 18-F 的等效 Cypher，两端逐字一致）。"""
    return {"code": code, "interface": interface, "query_key": query_key,
            "cypher": CYPHER[interface], "sort_key": sort_key,
            "count": len(results), "results": results, **extra}


def _jsonable(obj):
    """把 Neo4j 驱动返回的 dict/list 递归转成纯 Python 结构（供打印与比对）。"""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


# --------------------------------------------------------------------------
# 2. Cypher 片段与语句（Neo4j 后端）
# --------------------------------------------------------------------------
# Python `str.split()` 认的空白字符全集——Cypher 侧的归一化逐个删掉它们，
# 使 `_norm_expr` 与上面的 `_norm` 等价（理论差异见模块头「如实登记」）。
_NORM_WS = [chr(c) for c in (0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x1C, 0x1D, 0x1E, 0x1F, 0x20, 0x85, 0xA0, 0x1680, 0x2028, 0x2029, 0x202F, 0x205F, 0x3000, 0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200A)]


def _norm_expr(var: str) -> str:
    """与 `_norm(var)` 等价的 Cypher 表达式（`$ws` 传 `_NORM_WS`）。"""
    return ("toLower(reduce(_acc = coalesce(%s, ''), _w IN $ws | replace(_acc, _w, '')))"
            % var)


def _brief(v: str) -> str:
    """节点简述（等价 `GraphQuery._node_brief`）：node_id／label／name／stock_code。"""
    return ("{node_id: %(v)s.node_id, label: labels(%(v)s)[0], "
            "name: coalesce(trim(%(v)s.name), ''), "
            "stock_code: coalesce(trim(%(v)s.stock_code), '')}" % {"v": v})


def _event_view(v: str) -> str:
    """Event 视图（等价 `GraphQuery._event_view`）：node_id／label ＋ 六项核心属性。"""
    parts = ["node_id: %s.node_id" % v, "label: labels(%s)[0]" % v]
    parts += ["%s: coalesce(trim(%s.%s), '')" % (a, v, a) for a in EVENT_CORE_ATTRS]
    return "{" + ", ".join(parts) + "}"


def _rel_map(r: str) -> str:
    """路径上的关系项（等价 `GraphQuery._rel_item` 的字段集合，方向稍后在 Python 定）。"""
    return ("{edge_id: %(r)s.edge_id, relation: type(%(r)s), "
            "role: coalesce(trim(%(r)s.role), ''), "
            "source_doc_id: %(r)s.source_doc_id, "
            "source_chunk_id: %(r)s.source_chunk_id, "
            "confidence: %(r)s.confidence, "
            "s: startNode(%(r)s).node_id, t: endNode(%(r)s).node_id}" % {"r": r})


# G1～G7 在 Neo4j 后端上**实际执行**的 Cypher（与表 18-F 的等效 Cypher 同义；
# 参数用 $name 占位）。`--cypher-table` 会把它连同上表逐一打印，供取证。
NEO4J_CYPHER = {
    "G1": ("MATCH (a {node_id:$id})-[r]-(b) "
           "RETURN a.node_id AS a_id, r.edge_id AS edge_id, type(r) AS relation, "
           "CASE WHEN startNode(r) = a THEN 'out' ELSE 'in' END AS direction, "
           "b.node_id AS neighbor, coalesce(trim(r.role), '') AS role, "
           "r.source_doc_id AS source_doc_id, r.source_chunk_id AS source_chunk_id, "
           "r.confidence AS confidence, " + _brief("b") + " AS neighbor_node"),
    "G2": ("MATCH p = (a {node_id:$id})-[rs*1..2]-(b) "
           "RETURN [n IN nodes(p) | n.node_id] AS node_ids, "
           "[r IN relationships(p) | " + _rel_map("r") + "] AS rels"),
    "G3": "MATCH (e:Event) WHERE e.event_type = $type RETURN " + _event_view("e") + " AS ev",
    "G4": ("MATCH (c:Company)-[:PARTICIPATES_IN]->(e:Event) WHERE c.node_id IN $ids "
           "RETURN " + _event_view("e") + " AS ev"),
    "G5": ("MATCH (e {node_id:$id})-[r]-(x) "
           "RETURN type(r) AS relation, r.edge_id AS edge_id, "
           "CASE WHEN startNode(r) = e THEN 'out' ELSE 'in' END AS direction, "
           "x.node_id AS neighbor, coalesce(trim(r.role), '') AS role, "
           "r.source_doc_id AS source_doc_id, r.source_chunk_id AS source_chunk_id, "
           "r.confidence AS confidence, " + _brief("x") + " AS counterpart"),
    "G6": ("MATCH (n) WHERE n.node_id IN $ids "
           "RETURN " + _event_view("n") + " AS ev"),
    "G7": ("MATCH p = (a)-[rs*1..%d]-(b) "
           "WHERE a.node_id IN $from_ids AND b.node_id IN $to_ids "
           "RETURN [n IN nodes(p) | n.node_id] AS node_ids, "
           "[r IN relationships(p) | " + _rel_map("r") + "] AS rels"),
}

_RESOLVE_BY_ID = "MATCH (n {node_id:$id}) RETURN n.node_id AS node_id"
_RESOLVE_BY_CODE = ("MATCH (n {stock_code:$code}) RETURN n.node_id AS node_id "
                    "ORDER BY n.node_id")
_RESOLVE_BY_NAME = ("MATCH (n) WHERE %s = $key OR %s = $key "
                    "OR any(_a IN split(coalesce(n.aliases, ''), '|') WHERE %s = $key) "
                    "RETURN n.node_id AS node_id ORDER BY n.node_id"
                    % (_norm_expr("n.name"), _norm_expr("n.short_name"), _norm_expr("_a")))
_LABELS_OF = "MATCH (n) WHERE n.node_id IN $ids RETURN n.node_id AS node_id, labels(n)[0] AS label"
_LABEL_OF = "MATCH (n {node_id:$id}) RETURN labels(n)[0] AS label"


# --------------------------------------------------------------------------
# 3. Neo4j 后端
# --------------------------------------------------------------------------
class Neo4jGraphQuery:
    """图谱查询层的 **Neo4j 后端**：G1～G7 逐条落到 Cypher，语义与内存后端相同。"""

    name = NEO4J_BACKEND

    def __init__(self, driver=None, database=None):
        self._driver = driver if driver is not None else _make_driver()
        self._database = database
        self._session = None
        self._last_cypher = []

    # ------------------------------------------------------------ 连接与会话
    def _run(self, query: str, **params):
        if self._session is None:
            self._session = self._driver.session(database=self._database)
        self._last_cypher.append(query)
        return [_jsonable(dict(rec)) for rec in self._session.run(query, **params)]

    def last_cypher(self, clear: bool = True) -> list:
        """最近若干次调用实际执行过的 Cypher（取证用；envelope 里不放，保持两端同形）。"""
        out = list(self._last_cypher)
        if clear:
            self._last_cypher = []
        return out

    def close(self) -> None:
        if self._session is not None:
            try:
                self._session.close()
            except Exception:                                # noqa: BLE001
                pass
            self._session = None
        try:
            self._driver.close()
        except Exception:                                    # noqa: BLE001
            pass

    def server_info(self) -> dict:
        rows = self._run("CALL dbms.components() YIELD name, versions, edition "
                         "RETURN name, versions[0] AS version, edition")
        info = rows[0] if rows else {}
        params = config.neo4j_params()
        return {"uri": params["uri"], "kernel": info.get("name"),
                "version": info.get("version"), "edition": info.get("edition")}

    # ------------------------------------------------------------ 标识匹配
    def resolve_node(self, identifier: str) -> dict:
        ident = _s(identifier)
        if not ident:
            return {"code": RC_INVALID_INPUT, "node_ids": [], "matched_by": None,
                    "detail": "标识为空"}
        ids = [r["node_id"] for r in self._run(_RESOLVE_BY_ID, id=ident)]
        if ids:                                                  # ① node_id
            return {"code": RC_OK, "node_ids": [ident], "matched_by": "node_id"}
        if len(ident) == 6 and ident.isdigit():                  # ② stock_code
            ids = [r["node_id"] for r in self._run(_RESOLVE_BY_CODE, code=ident)]
            if ids:
                return {"code": RC_OK, "node_ids": sorted(ids), "matched_by": "stock_code"}
        key = _norm(ident)                                       # ③ name／short_name／aliases
        ids = [r["node_id"] for r in self._run(_RESOLVE_BY_NAME, key=key, ws=_NORM_WS)]
        if ids:
            return {"code": RC_OK, "node_ids": sorted(ids), "matched_by": "name"}
        return {"code": RC_NOT_FOUND, "node_ids": [], "matched_by": None,
                "detail": "三种标识（node_id／stock_code／name·short_name·aliases）都未匹配到"}

    def resolve_company(self, identifier: str) -> dict:
        res = self.resolve_node(identifier)
        if res["code"] != RC_OK:
            return res
        labels = {r["node_id"]: r["label"]
                  for r in self._run(_LABELS_OF, ids=list(res["node_ids"]))}
        companies = [nid for nid in res["node_ids"] if labels.get(nid) == "Company"]
        if not companies:
            return {"code": RC_INVALID_INPUT, "node_ids": [], "matched_by": res["matched_by"],
                    "detail": "命中 %s 但标签不是 Company" % ",".join(res["node_ids"])}
        return {"code": RC_OK, "node_ids": companies, "matched_by": res["matched_by"]}

    # ------------------------------------------------------------ 内部小工具
    @staticmethod
    def _evidence(relation: str, row: dict):
        """证据三项：`EVIDENCED_BY` 为 `None`；其余按 `EVIDENCE_ATTRS` 取（缺属性按空串）。"""
        if relation == EVIDENCED_BY:
            return None
        return {a: (row.get(a) or "") for a in EVIDENCE_ATTRS}

    def _rel_item(self, row: dict) -> dict:
        relation = row["relation"]
        return {"edge_id": row["edge_id"], "relation": relation,
                "direction": row["direction"], "neighbor": row["neighbor"],
                "role": row.get("role") or "",
                "evidence": self._evidence(relation, row)}

    # ---------------------------------------------------------------- G1
    def g1_one_hop(self, identifier: str, label: str | None = None) -> dict:
        res = self.resolve_node(identifier)
        query_key = {"identifier": _s(identifier), "matched_by": res["matched_by"]}
        sort_key = "(relation, direction, neighbor, edge_id)"
        if res["code"] != RC_OK:
            return _envelope("G1", res["code"], query_key, sort_key, [],
                             node_ids=[], detail=res.get("detail", ""))
        # 与内存后端同序（按已排序的 node_ids 逐个起步），同一 edge_id 后写覆盖先写
        by_edge: dict = {}
        for nid in res["node_ids"]:
            for row in self._run(NEO4J_CYPHER["G1"], id=nid):
                item = self._rel_item(row)
                item["neighbor_node"] = row["neighbor_node"]
                by_edge[row["edge_id"]] = item
        items = list(by_edge.values())
        if label:
            items = [it for it in items if it["neighbor_node"]["label"] == label]
        items.sort(key=lambda it: (it["relation"], it["direction"], it["neighbor"], it["edge_id"]))
        code = RC_OK if items else RC_EMPTY
        return _envelope("G1", code, query_key, sort_key, items, node_ids=res["node_ids"])

    # ---------------------------------------------------------------- G2
    def _paths(self, cypher: str, **params) -> list:
        """把 Cypher 返回的 `node_ids`／`rels` 还原成与内存后端同形的路径项。"""
        paths = []
        for row in self._run(cypher, **params):
            nodes = list(row["node_ids"])
            rels = []
            for i, rel in enumerate(row["rels"]):
                direction = "out" if rel["s"] == nodes[i] else "in"
                rels.append({"edge_id": rel["edge_id"], "relation": rel["relation"],
                             "direction": direction, "neighbor": nodes[i + 1],
                             "role": rel.get("role") or "",
                             "evidence": self._evidence(rel["relation"], rel)})
            paths.append({"depth": len(nodes) - 1, "start": nodes[0], "end": nodes[-1],
                          "nodes": nodes, "relations": rels})
        return paths

    def g2_two_hop(self, identifier: str, label: str | None = None) -> dict:
        res = self.resolve_node(identifier)
        query_key = {"identifier": _s(identifier), "matched_by": res["matched_by"]}
        sort_key = "(depth, nodes, relations, edge_ids, directions)"
        if res["code"] != RC_OK:
            return _envelope("G2", res["code"], query_key, sort_key, [],
                             node_ids=[], detail=res.get("detail", ""))
        query = NEO4J_CYPHER["G2"]
        params = {}
        if label:
            query = query + " WHERE labels(b)[0] = $label"
            params["label"] = label
        paths = []
        for nid in res["node_ids"]:
            paths += self._paths(query, id=nid, **params)
        paths = GraphQuery._sort_paths(paths)        # 复用第 7 阶段的同一排序键
        code = RC_OK if paths else RC_EMPTY
        return _envelope("G2", code, query_key, sort_key, paths,
                         node_ids=res["node_ids"],
                         one_hop_count=sum(1 for p in paths if p["depth"] == 1))

    # ---------------------------------------------------------------- G3
    def g3_events_by_type(self, event_type: str) -> dict:
        et = _s(event_type)
        query_key = {"type": et}
        sort_key = "(event_time, node_id)"
        if et not in EVENT_TYPES:
            return _envelope("G3", RC_INVALID_INPUT, query_key, sort_key, [],
                             detail="event_type 不在 %s" % EVENT_TYPES)
        results = [r["ev"] for r in self._run(NEO4J_CYPHER["G3"], type=et)]
        results.sort(key=lambda e: (e["event_time"], e["node_id"]))
        return _envelope("G3", RC_OK if results else RC_EMPTY, query_key, sort_key, results)

    # ---------------------------------------------------------------- G4
    def g4_company_events(self, identifier: str) -> dict:
        res = self.resolve_company(identifier)
        query_key = {"identifier": _s(identifier), "matched_by": res["matched_by"]}
        sort_key = "(event_time, node_id)"
        if res["code"] != RC_OK:
            return _envelope("G4", res["code"], query_key, sort_key, [],
                             node_ids=[], detail=res.get("detail", ""))
        seen, results = set(), []
        for r in self._run(NEO4J_CYPHER["G4"], ids=list(res["node_ids"])):
            ev = r["ev"]
            if ev["node_id"] in seen:
                continue
            seen.add(ev["node_id"])
            results.append(ev)
        results.sort(key=lambda e: (e["event_time"], e["node_id"]))
        code = RC_OK if results else RC_EMPTY
        return _envelope("G4", code, query_key, sort_key, results, node_ids=res["node_ids"])

    # ---------------------------------------------------------------- G5
    def g5_event_evidence(self, event_id: str) -> dict:
        eid = _s(event_id)
        query_key = {"id": eid}
        sort_key = "(relation, source_chunk_id, source_doc_id, edge_id)"
        rows = self._run(_LABEL_OF, id=eid)
        if not rows:
            return _envelope("G5", RC_NOT_FOUND, query_key, sort_key, [],
                             chunks=[], document_refs=[], detail="节点不存在：%s" % eid)
        if rows[0]["label"] != "Event":
            return _envelope("G5", RC_INVALID_INPUT, query_key, sort_key, [],
                             chunks=[], document_refs=[],
                             detail="标识 %s 不是 Event 节点" % eid)
        chunks, docs = [], []
        for row in self._run(NEO4J_CYPHER["G5"], id=eid):
            if row["relation"] == EVIDENCED_BY:
                # 只用于展示来源文档：不带 source_chunk_id，**不产生文本块级候选**（硬约束 14）
                docs.append({"relation": row["relation"], "direction": row["direction"],
                             "document_id": row["neighbor"], "edge_id": row["edge_id"],
                             "document": row["counterpart"]})
                continue
            item = self._rel_item(row)
            if not item["evidence"] or not item["evidence"].get("source_chunk_id"):
                continue                                  # 唯一入池依据：带 source_chunk_id
            item["counterpart"] = row["counterpart"]
            chunks.append(item)
        chunks.sort(key=lambda it: (it["relation"], it["evidence"]["source_chunk_id"],
                                    it["evidence"]["source_doc_id"], it["edge_id"]))
        docs.sort(key=lambda d: (d["document_id"], d["edge_id"]))
        chunk_ids = sorted({it["evidence"]["source_chunk_id"] for it in chunks},
                           key=lambda x: (len(x), x))
        code = RC_OK if (chunks or docs) else RC_EMPTY
        return _envelope("G5", code, query_key, sort_key, chunks,
                         chunk_ids=chunk_ids, document_refs=docs)

    def event_chunk_ids(self, event_id: str) -> list:
        """单个事件经 8 条语义边携带的 `chunk_id` 集合（升序）；**不含 `EVIDENCED_BY`**。"""
        return self.g5_event_evidence(event_id)["chunk_ids"]

    # ---------------------------------------------------------------- G6
    def g6_time_filter(self, event_ids, lo: str, hi: str, null_policy: str | None = None) -> dict:
        policy = (config.RETRIEVAL["time_filter_null_policy"]
                  if null_policy is None else null_policy)
        query_key = {"ids": list(event_ids or []), "lo": _s(lo), "hi": _s(hi),
                     "null_policy": policy}
        sort_key = "node_id"
        if policy not in NULL_POLICIES:
            return _envelope("G6", RC_INVALID_INPUT, query_key, sort_key, [],
                             detail="null_policy 只能是 %s" % (NULL_POLICIES,))
        lo_s, hi_s = _s(lo), _s(hi)
        if not lo_s or not hi_s or lo_s > hi_s:
            return _envelope("G6", RC_INVALID_INPUT, query_key, sort_key, [],
                             detail="时间闭区间非法：lo=%r hi=%r" % (lo_s, hi_s))
        ids = [_s(x) for x in (event_ids or [])]
        views = {r["ev"]["node_id"]: r["ev"] for r in self._run(NEO4J_CYPHER["G6"], ids=ids)}
        unknown = [x for x in ids if x not in views]
        if unknown:
            return _envelope("G6", RC_INVALID_INPUT, query_key, sort_key, [],
                             detail="事件标识不存在：%s" % ",".join(unknown))

        passed, removed_null, removed_range = [], [], []
        for eid in ids:
            et = views[eid]["event_time"]                       # 已 coalesce/trim 成字符串
            if not et:                                          # 空值：按显式策略处置
                if policy == "exclude":
                    removed_null.append(eid)
                    continue
                passed.append(eid)
                continue
            if lo_s <= et <= hi_s:
                passed.append(eid)
            else:
                removed_range.append(eid)
        passed.sort()
        removed_null.sort()
        removed_range.sort()
        removed = sorted(removed_null + removed_range)

        survived_chunks, removed_chunks = set(), set()
        for eid in passed:
            survived_chunks.update(self.event_chunk_ids(eid))
        for eid in removed:
            removed_chunks.update(self.event_chunk_ids(eid))
        ck = lambda s: sorted(s, key=lambda x: (len(x), x))     # noqa: E731
        diff = removed_chunks - survived_chunks
        diff_rev = survived_chunks - removed_chunks
        code = RC_OK if passed else RC_EMPTY
        return _envelope(
            "G6", code, query_key, sort_key,
            [views[x] for x in passed],
            passed_ids=passed, removed_ids=removed,
            removed_null_ids=removed_null, removed_out_of_range_ids=removed_range,
            null_policy=policy,
            chunk_ids_in_scope=ck(survived_chunks | removed_chunks),
            chunk_ids_survived=ck(survived_chunks),
            chunk_ids_removed=ck(removed_chunks),
            chunk_id_diff=ck(diff),
            chunk_id_diff_reverse=ck(diff_rev),
        )

    # ---------------------------------------------------------------- G7
    def g7_paths(self, from_id: str, to_id: str, max_depth: int = 2) -> dict:
        query_key = {"from": _s(from_id), "to": _s(to_id), "max_depth": max_depth}
        sort_key = "(depth, nodes, relations, edge_ids, directions)"
        if not isinstance(max_depth, int) or not (1 <= max_depth <= 2):
            return _envelope("G7", RC_INVALID_INPUT, query_key, sort_key, [],
                             detail="max_depth 只能是 1 或 2")
        rf, rt = self.resolve_node(from_id), self.resolve_node(to_id)
        if rf["code"] != RC_OK or rt["code"] != RC_OK:
            return _envelope("G7", RC_NOT_FOUND, query_key, sort_key, [],
                             detail="起点或终点未匹配到")
        paths = self._paths(NEO4J_CYPHER["G7"] % max_depth,
                            from_ids=list(rf["node_ids"]), to_ids=list(rt["node_ids"]))
        paths = GraphQuery._sort_paths(paths)        # 复用第 7 阶段的同一排序键
        return _envelope("G7", RC_OK if paths else RC_EMPTY, query_key, sort_key, paths,
                         graph_path=[self.graph_path_payload(p) for p in paths])

    def graph_path_payload(self, path: dict) -> dict:
        return {"start": path["start"], "end": path["end"], "depth": path["depth"],
                "nodes": list(path["nodes"]),
                "relations": [{"relation": r["relation"], "direction": r["direction"],
                               "neighbor": r["neighbor"], "role": r["role"],
                               "evidence": (dict(r["evidence"]) if r["evidence"] else None)}
                              for r in path["relations"]]}

    @staticmethod
    def not_used_graph_marker() -> dict:
        return {"graph_used": False, "graph_path": [], "note": "未使用图谱扩展"}


def _make_driver():
    """建 Neo4j driver（参数取 `config.neo4j_params()`；**口令不回显、不进日志**）。"""
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise SystemExit("未安装 neo4j 驱动：%s（本阶段不新增依赖）" % exc)
    params = config.neo4j_params()
    driver = GraphDatabase.driver(params["uri"], auth=(params["user"], params["password"]))
    try:
        driver.verify_connectivity()
    except Exception as exc:                                  # noqa: BLE001
        try:
            driver.close()
        except Exception:                                     # noqa: BLE001
            pass
        raise SystemExit(
            "Neo4j 连接失败（%s）：%s\n服务未启动？本机 Neo4j 以容器形态运行在 WSL2 内——"
            "先执行：wsl -d Ubuntu -u root -- docker start ashare-neo4j\n"
            "（连接串可打印，口令不打印）" % (type(exc).__name__, params["uri"]))
    return driver


# --------------------------------------------------------------------------
# 4. 后端选择
# --------------------------------------------------------------------------
def resolve_backend_name(name: str | None = None) -> str:
    """`GRAPH_BACKEND` 环境变量 → 后端 config 开关 → 缺省 `neo4j`。"""
    chosen = (name or os.environ.get("GRAPH_BACKEND")
              or getattr(config, "GRAPH_BACKEND", None) or DEFAULT_BACKEND)
    chosen = str(chosen).strip().lower()
    if chosen not in (NEO4J_BACKEND, MEMORY_BACKEND):
        raise SystemExit("未知的 GRAPH_BACKEND=%r（合法值：%s／%s）"
                         % (chosen, NEO4J_BACKEND, MEMORY_BACKEND))
    return chosen


def open_backend(name: str | None = None):
    """打开一个图谱查询后端实例。`memory` 就是第 7 阶段的 `GraphQuery`（未改一字节）。"""
    chosen = resolve_backend_name(name)
    if chosen == MEMORY_BACKEND:
        return GraphQuery(), MEMORY_BACKEND
    return Neo4jGraphQuery(), NEO4J_BACKEND


def close_backend(graph) -> None:
    close = getattr(graph, "close", None)
    if callable(close):
        close()


# ==========================================================================
# 5. --selftest
# ==========================================================================
def selftest(backend: str | None = None) -> int:
    graph, name = open_backend(backend)
    checks = []

    def check(label, ok, detail=""):
        checks.append({"name": label, "ok": bool(ok), "detail": detail})
        print("  [%s] %s%s" % ("OK  " if ok else "FAIL", label,
                               ("  —— " + detail) if detail else ""))
        return ok

    line = "=" * 78
    print(line)
    print("graph_service.py 自检｜后端 = %s" % name)
    print(line)
    if name == NEO4J_BACKEND:
        info = graph.server_info()
        print("  Neo4j：%s（%s %s %s）" % (info["uri"], info["kernel"],
                                           info["version"], info["edition"]))
        print("  实现形态：容器形态运行在 WSL2 内（镜像 neo4j:5-community，容器名 "
              "ashare-neo4j）；未装 Docker Desktop、未注册 Windows 服务；"
              "本地单实例，非集群／非高可用／非生产部署。")
    else:
        print("  内存图后端：直接复用第 7 阶段 代码\\检索\\graph_query.py 的 GraphQuery")

    print("\n一、七个接口各跑通至少一次")
    g1 = graph.g1_one_hop("000001")
    check("G1 一跳邻居（000001）", g1["code"] in (RC_OK, RC_EMPTY),
          "code=%s count=%d" % (g1["code"], g1["count"]))
    g2 = graph.g2_two_hop("000001")
    check("G2 两跳邻居（000001）", g2["code"] in (RC_OK, RC_EMPTY),
          "code=%s 路径 %d（一跳 %s）" % (g2["code"], g2["count"], g2.get("one_hop_count")))
    g3 = graph.g3_events_by_type("股权")
    check("G3 按事件类型（股权）", g3["code"] in (RC_OK, RC_EMPTY),
          "code=%s count=%d" % (g3["code"], g3["count"]))
    g4 = graph.g4_company_events("000001")
    check("G4 按公司取参与事件（000001）", g4["code"] in (RC_OK, RC_EMPTY),
          "code=%s count=%d" % (g4["code"], g4["count"]))
    g5 = graph.g5_event_evidence("EVT-0001")
    check("G5 事件到证据块（EVT-0001）", g5["code"] in (RC_OK, RC_EMPTY),
          "code=%s 语义边项 %d、chunk_id %d、来源文档 %d"
          % (g5["code"], g5["count"], len(g5["chunk_ids"]), len(g5["document_refs"])))
    ev_ids = [e["node_id"] for e in graph.g4_company_events("000001")["results"]]
    g6 = graph.g6_time_filter(ev_ids, "2026-06-26", "2026-09-22")
    check("G6 时间过滤（000001 的 %d 个事件 / [2026-06-26, 2026-09-22]）" % len(ev_ids),
          g6["code"] in (RC_OK, RC_EMPTY),
          "code=%s 通过 %d、空值剔除 %d、越界剔除 %d、chunk_id 差集 %d"
          % (g6["code"], len(g6["passed_ids"]), len(g6["removed_null_ids"]),
             len(g6["removed_out_of_range_ids"]), len(g6["chunk_id_diff"])))
    g7 = graph.g7_paths("000001", ev_ids[0] if ev_ids else "EVT-0029", max_depth=2)
    check("G7 路径枚举（000001 → %s，max_depth=2）" % (ev_ids[0] if ev_ids else "EVT-0029"),
          g7["code"] in (RC_OK, RC_EMPTY), "code=%s 路径 %d" % (g7["code"], g7["count"]))

    print("\n二、边界与返回码（匹配不到不抛异常）")
    r_nf = graph.g1_one_hop("不存在的公司XYZ")
    check("未匹配 → NOT_FOUND", r_nf["code"] == RC_NOT_FOUND, r_nf["code"])
    r_iv = graph.g3_events_by_type("不存在的类型")
    check("非法入参 → INVALID_INPUT", r_iv["code"] == RC_INVALID_INPUT, r_iv["code"])
    check("G5 对非 Event 标识 → INVALID_INPUT",
          graph.g5_event_evidence("000001")["code"] == RC_INVALID_INPUT,
          graph.g5_event_evidence("000001")["code"])
    check("G7 深度非法 → INVALID_INPUT",
          graph.g7_paths("000001", "000063", max_depth=3)["code"] == RC_INVALID_INPUT)
    check("G6 区间反序 → INVALID_INPUT",
          graph.g6_time_filter(ev_ids, "2026-09-22", "2026-06-26")["code"] == RC_INVALID_INPUT)
    check("G6 空值策略非法 → INVALID_INPUT",
          graph.g6_time_filter(ev_ids, "2026-06-26", "2026-09-22",
                               null_policy="skip")["code"] == RC_INVALID_INPUT)
    check("EVIDENCED_BY 的关系项不带证据三项",
          all(it["evidence"] is None for it in graph.g5_event_evidence("EVT-0001")["results"]
              if it["relation"] == EVIDENCED_BY),
          "G5 的 results 仅含语义边，另见 document_refs")

    print("\n三、按名称匹配「没有 stock_code」的公司节点（HCONF 前缀）")
    hconf = _first_hconf_name(graph, name)
    if hconf:
        r = graph.resolve_company(hconf)
        check("G4 按名称匹配 HCONF 公司（%s）" % hconf, r["code"] in (RC_OK, RC_EMPTY, RC_INVALID_INPUT),
              "code=%s matched_by=%s node_ids=%s" % (r["code"], r["matched_by"], r["node_ids"]))
    else:
        check("HCONF 公司节点存在", False, "未取到无 stock_code 的公司名")

    check("event_chunk_ids（EVT-0001）", isinstance(graph.event_chunk_ids("EVT-0001"), list),
          "%d 个 chunk_id" % len(graph.event_chunk_ids("EVT-0001")))
    marker = graph.not_used_graph_marker()
    check("未用图谱标记", marker.get("graph_used") is False and marker.get("graph_path") == [],
          str(marker))

    if name == NEO4J_BACKEND:
        print("\n四、Neo4j 后端实际执行的 Cypher（G1～G7 逐条对应，取证用）")
        for gid in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
            print("  %s  %s" % (gid, NEO4J_CYPHER[gid]))

    passed = sum(1 for c in checks if c["ok"])
    print("\n自检项 %d，通过 %d，失败 %d" % (len(checks), passed, len(checks) - passed))
    print("结论：%s" % ("全部通过。" if passed == len(checks) else "存在失败项。"))
    print(line)
    close_backend(graph)
    return 0 if passed == len(checks) else 1


def _first_hconf_name(graph, backend: str) -> str | None:
    """取一个「没有 stock_code 的公司」的名称（内存后端与 Neo4j 后端都能取）。"""
    if backend == NEO4J_BACKEND:
        rows = graph._run("MATCH (n:Company) WHERE n.stock_code IS NULL "
                          "RETURN n.name AS name ORDER BY n.node_id LIMIT 1")
        return rows[0]["name"] if rows else None
    for nid in sorted(graph.nodes):
        n = graph.nodes[nid]
        if _s(n.get("label")) == "Company" and not _s(n.get("stock_code")):
            return _s(n.get("name"))
    return None


# ==========================================================================
# 6. --parity-check（验收 E5）
# ==========================================================================
def _fingerprint(interface: str, env: dict) -> dict:
    """把一次查询结果压成**可比对的关键字段**（排序键序列／节点集合／关系集合／chunk_id 集合）。"""
    res = env.get("results") or []
    # envelope 里除「两端必然同形的七项」之外的其余字段（node_ids／one_hop_count／
    # document_refs／graph_path／passed_ids／chunk_id 各集合／detail…）——整份深度比对。
    extras = {k: v for k, v in env.items()
              if k not in ("code", "interface", "query_key", "cypher", "sort_key",
                           "count", "results")}
    fp = {"code": env.get("code"), "count": env.get("count"),
          "sort_key": env.get("sort_key"), "payload": res, "extras": extras}
    nodes, edges, rels, chunks, seq = set(), set(), set(), set(), []
    if interface == "G1":
        seq = [(it["relation"], it["direction"], it["neighbor"], it["edge_id"]) for it in res]
        nodes |= {it["neighbor"] for it in res} | set(env.get("node_ids") or [])
        edges |= {it["edge_id"] for it in res}
        rels |= {it["relation"] for it in res}
    elif interface in ("G2", "G7"):
        for p in res:
            seq.append((p["depth"], tuple(p["nodes"]),
                        tuple(r["relation"] for r in p["relations"]),
                        tuple(r["edge_id"] for r in p["relations"]),
                        tuple(r["direction"] for r in p["relations"])))
            nodes |= set(p["nodes"])
            edges |= {r["edge_id"] for r in p["relations"]}
            rels |= {r["relation"] for r in p["relations"]}
    elif interface in ("G3", "G4"):
        seq = [(e["event_time"], e["node_id"]) for e in res]
        nodes |= {e["node_id"] for e in res}
    elif interface == "G5":
        seq = [(it["relation"], it["evidence"]["source_chunk_id"],
                it["evidence"]["source_doc_id"], it["edge_id"]) for it in res]
        nodes |= {it["neighbor"] for it in res}
        nodes |= {d["document_id"] for d in (env.get("document_refs") or [])}
        edges |= {it["edge_id"] for it in res}
        edges |= {d["edge_id"] for d in (env.get("document_refs") or [])}
        rels |= {it["relation"] for it in res}
        rels |= {d["relation"] for d in (env.get("document_refs") or [])}
        chunks |= set(env.get("chunk_ids") or [])
    elif interface == "G6":
        seq = list(env.get("passed_ids") or [])
        nodes |= set(env.get("passed_ids") or []) | set(env.get("removed_ids") or [])
        chunks |= set(env.get("chunk_ids_in_scope") or [])
    fp.update({"sort_seq": seq, "nodes": sorted(nodes), "edges": sorted(edges),
               "relations": sorted(rels), "chunk_ids": sorted(chunks, key=lambda x: (len(x), x))})
    # G6 的九组集合（passed_ids／chunk_id_diff…）与 null_policy 均在 `extras` 里深度比对
    return fp


def _parity_queries() -> list:
    """确定的一组查询：3 家公司的 G1/G2、3 个事件类型的 G3、2 家公司的 G4、
    3 个事件的 G5、1 组 G6 时间过滤、2 组 G7 路径（均满足或超过验收 E5 的下限）。"""
    return [
        ("G1", "000001"), ("G1", "000063"), ("G1", "600028"),
        ("G2", "000001"), ("G2", "000063"), ("G2", "600028"),
        ("G3", "股权"), ("G3", "业绩"), ("G3", "投资并购"),
        ("G4", "000001"), ("G4", "000063"),
        ("G5", "EVT-0001"), ("G5", "EVT-0356"), ("G5", "EVT-0721"),
        ("G7", ("000001", "EVT-0029")), ("G7", ("000063", "EVT-0356")),
    ]


def _run_one(graph, interface: str, arg) -> dict:
    if interface == "G1":
        return graph.g1_one_hop(arg)
    if interface == "G2":
        return graph.g2_two_hop(arg)
    if interface == "G3":
        return graph.g3_events_by_type(arg)
    if interface == "G4":
        return graph.g4_company_events(arg)
    if interface == "G5":
        return graph.g5_event_evidence(arg)
    if interface == "G6":
        return graph.g6_time_filter(arg[0], arg[1], arg[2])
    if interface == "G7":
        return graph.g7_paths(arg[0], arg[1], max_depth=2)
    raise SystemExit("未知接口：%s" % interface)


def parity_check(verbose: bool = True) -> int:
    line = "=" * 78
    print(line)
    print("graph_service.py 后端对拍（--parity-check）：memory ↔ neo4j")
    print(line)

    mem, _ = open_backend(MEMORY_BACKEND)
    neo, _ = open_backend(NEO4J_BACKEND)
    info = neo.server_info()
    print("  memory 后端：第 7 阶段 GraphQuery（内存图）")
    print("  neo4j  后端：%s（%s %s %s）" % (info["uri"], info["kernel"],
                                             info["version"], info["edition"]))
    print()

    # G6 的入参由内存后端确定（确定性），两个后端拿到**同一组**事件与同一个区间
    g6_ids = [e["node_id"] for e in mem.g4_company_events("000001")["results"]]
    g6_arg = (g6_ids, "2026-06-26", "2026-09-22")
    queries = _parity_queries() + [("G6", g6_arg)]

    groups, bad = [], []
    print("  %-4s %-34s %6s %-6s %-4s %s"
          % ("接口", "查询键", "结果数", "结论", "节点", "不一致的关键字段（边/chunk）"))
    print("  " + "-" * 92)
    for interface, arg in queries:
        env_m = _run_one(mem, interface, arg)
        env_n = _run_one(neo, interface, arg)
        fp_m, fp_n = _fingerprint(interface, env_m), _fingerprint(interface, env_n)
        fields = ["code", "count", "sort_key", "sort_seq", "nodes", "edges",
                  "relations", "chunk_ids", "payload", "extras"]
        diff = [f for f in fields if fp_m.get(f) != fp_n.get(f)]
        label = _key_label(interface, arg)
        ok = not diff
        groups.append({"interface": interface, "query_key": label, "match": ok, "diff": diff,
                       "count": fp_m.get("count"), "nodes": len(fp_m.get("nodes") or []),
                       "edges": len(fp_m.get("edges") or []),
                       "chunk_ids": len(fp_m.get("chunk_ids") or [])})
        if not ok:
            bad.append((interface, label, diff, fp_m, fp_n))
        print("  %-4s %-34s %6s %-6s %-4s %s"
              % (interface, label, fp_m.get("count"), "一致" if ok else "**不一致**",
                 len(fp_m.get("nodes") or []),
                 "、".join(diff) if diff else "边 %d／chunk %d"
                 % (len(fp_m.get("edges") or []), len(fp_m.get("chunk_ids") or []))))

    print()
    print("  对拍组数 %d，全一致 %d，不一致 %d" % (len(groups), len(groups) - len(bad), len(bad)))
    if bad and verbose:
        print("\n--- 不一致明细 ---")
        for interface, label, diff, fp_m, fp_n in bad:
            print("  · %s %s" % (interface, label))
            for f in diff:
                print("      字段 %s：" % f)
                print("        memory = %s" % _short(fp_m.get(f)))
                print("        neo4j  = %s" % _short(fp_n.get(f)))

    print("\n  结论：%s" % ("两个后端在全部关键字段上逐项一致。" if not bad
                            else "**存在不一致——如实报出，不遮掩。**"))
    print(line)
    close_backend(mem)
    close_backend(neo)
    return 0 if not bad else 1


def _key_label(interface: str, arg) -> str:
    if interface == "G6":
        return "ids=%d lo=%s hi=%s" % (len(arg[0]), arg[1], arg[2])
    if interface == "G7":
        return "%s → %s (max_depth=2)" % (arg[0], arg[1])
    return str(arg)


def _short(value, limit: int = 240) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "…（共 %d 字符）" % len(text)


# ==========================================================================
# 7. CLI
# ==========================================================================
def cypher_table() -> int:
    print("接口\t等效 Cypher（表 18-F，两端 envelope 共用）")
    for gid in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
        print("%s\t%s" % (gid, CYPHER[gid]))
    print()
    print("接口\tNeo4j 后端实际执行的 Cypher（同一语义，逐条对应）")
    for gid in ("G1", "G2", "G3", "G4", "G5", "G6", "G7"):
        print("%s\t%s" % (gid, NEO4J_CYPHER[gid]))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 9 阶段 T3：图谱查询服务（neo4j／memory 双后端，同一套语义）")
    parser.add_argument("--selftest", action="store_true", help="七个接口与边界各跑通一次")
    parser.add_argument("--parity-check", action="store_true",
                        help="两个后端逐项对拍关键字段，不一致即非零退出（验收 E5）")
    parser.add_argument("--cypher-table", action="store_true",
                        help="打印 G1～G7 的等效 Cypher 与 Neo4j 后端实际执行的 Cypher")
    parser.add_argument("--backend", choices=[NEO4J_BACKEND, MEMORY_BACKEND], default=None,
                        help="临时指定后端（缺省取 GRAPH_BACKEND 环境变量，再缺省 neo4j）")
    args = parser.parse_args(argv)

    if args.cypher_table:
        return cypher_table()
    if args.parity_check:
        print("（--backend 对 --parity-check 无效：它本来就要两个后端都跑）\n")
        return parity_check()
    if args.selftest:
        return selftest(args.backend)

    print("当前后端选择：%s（GRAPH_BACKEND=%r）"
          % (resolve_backend_name(), os.environ.get("GRAPH_BACKEND")))
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
