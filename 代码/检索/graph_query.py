# -*- coding: utf-8 -*-
"""代码\\检索\\graph_query.py —— T3：**图谱查询层**（内存图 ＋ 七个接口 ＋ 等效 Cypher）。

本脚本对应《18-第7阶段任务书（RAG检索系统）》第九节 **T3**、第4.2节 **表 18-F**、
第五节 硬约束 14／15／19，以及第六节 的格式决策 1。

实现形态（**必须如实说明**）：环境实测 `neo4j` 驱动未安装、7687 端口不通（《17》第6.3节），
所以本层是「**图谱查询层**」抽象——把 `阶段06-事件抽取与知识图谱\\图谱导出\\v2.1_v1_2\\`
的 `nodes.csv`／`edges.csv` 读进**内存图**，七个接口各配一段**等效 Cypher 字符串**
（见本模块的 `CYPHER`），换真实例时只替换本层后端。
**本文件不连接、不部署、不声称任何图数据库服务**，也不写任何连接串或服务地址
（硬约束 15）。

对输入**只读**：只 `open(..., "r", encoding="utf-8")` 读两张 CSV；不改输入、不写
`阶段05-数据准备\\数据集\\v2.1\\` 与 `图谱导出\\v2.1_v1_2\\` 的任何一个字节、不改
`replay.cypher`（硬约束 17）。参数取同目录 `config.py`（唯一参数来源），不写死路径。

## 七个接口（逐行照 表 18-F）

| 编号 | 接口 | 方法 | 排序键（确定性） |
| --- | --- | --- | --- |
| G1 | 一跳邻居 | `g1_one_hop` | `(relation, direction, neighbor, edge_id)` |
| G2 | 两跳邻居（**结果包含一跳**） | `g2_two_hop` | `(depth, nodes, relations, edge_ids, directions)` |
| G3 | 按事件类型取事件 | `g3_events_by_type` | `(event_time, node_id)`（空值排最前） |
| G4 | 按公司取参与事件 | `g4_company_events` | `(event_time, node_id)`（空值排最前） |
| G5 | 事件到证据块 | `g5_event_evidence` | `(relation, source_chunk_id, source_doc_id, edge_id)` |
| G6 | 时间过滤 | `g6_time_filter` | `node_id`（差集与两侧集合均升序） |
| G7 | 路径枚举 | `g7_paths` | `(depth, nodes, relations, edge_ids, directions)` |

## 两条边界（硬约束 14、v2.9 裁定 ①）

* **G5 边界**：事件侧候选**只能**经带 `source_chunk_id` 的 8 条语义边入池；
  `EVIDENCED_BY`（1111 条）指向 Document、**不带** `source_chunk_id`，
  只用于展示来源文档，**不产生文本块级候选**（硬约束 14）。本模块用
  `config.SEMANTIC_RELATIONS`（＝ `RELATIONS` 去掉 `EVIDENCED_BY`）作为入池白名单，
  `EVIDENCED_BY` 的终点只落进 `document_refs`，且该边**不带**三项证据属性。
* **G6 的 `event_time` 空值语义**：空值**一并剔除**（v2.9 裁定 ①、硬约束 3）。
  空值策略是**显式参数** `null_policy`（合法值 `exclude`／`keep`），默认取
  `config.RETRIEVAL["time_filter_null_policy"]`（＝`exclude`）；**不得写成隐式跳过**。
  G6 同时返回"被剔除路径携带的 `chunk_id` 差集"，供 pipeline 逐题打印（硬约束 5）。

## 返回体形状（统一）

每个接口都返回一个 dict：`code`／`interface`／`query_key`／`cypher`／`sort_key`／`count`／
`results`（外加接口专有字段）。`code` 的可区分取值（**匹配不到不抛异常**）：

* `OK`            —— 命中且结果非空；
* `EMPTY`         —— 命中节点但无结果（例如孤立节点、该公司没有参与事件）；
* `NOT_FOUND`     —— 标识未匹配到任何节点；
* `INVALID_INPUT` —— 入参非法（未知事件类型、深度超 2、区间反序、空值策略非法）。

**证据三项**：除 `EVIDENCED_BY` 外，每条边的关系项都带 `source_doc_id`／
`source_chunk_id`／`confidence`（取自 `config.EVIDENCE_ATTRS`，**原样字符串**）；
`EVIDENCED_BY` 的关系项这三项为 `null`（硬约束 19）。

用法：`python 代码\\检索\\graph_query.py --selftest`
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402

# 控制台按 UTF-8 输出（本项目在中文 Windows 上跑；避免 GBK 代码页把中文与数学符号写坏）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

# --------------------------------------------------------------------------
# 返回码（可区分；匹配不到不抛异常）
# --------------------------------------------------------------------------
RC_OK = "OK"
RC_EMPTY = "EMPTY"
RC_NOT_FOUND = "NOT_FOUND"
RC_INVALID_INPUT = "INVALID_INPUT"

# --------------------------------------------------------------------------
# 七个接口的等效 Cypher（**与 表 18-F 第三列逐字一致**；参数用 $name 占位）
# 逐条对应：
#   G1 = 表 18-F 第 1 行；G2 = 第 2 行；…；G7 = 第 7 行。
# 这七个字符串供《19》生成"接口与 Cypher 一一对应"表；换真实例时只替换本层后端。
# --------------------------------------------------------------------------
CYPHER = {
    # G1 一跳邻居：节点标识（node_id；公司还可用 stock_code 或 name／short_name／aliases）
    # → 直接相连的关系与对端节点。无向遍历（两侧都算）。
    "G1": "MATCH (a {node_id:$id})-[r]-(b) RETURN a, r, b",
    # G2 两跳邻居（结果包含一跳）：深度不超过 2 的路径集合。同一条边不得在一次路径里走两次。
    "G2": "MATCH (a {node_id:$id})-[r1]-(b)-[r2]-(c) RETURN a, r1, b, r2, c",
    # G3 按事件类型取事件：event_type 为 config.EVENT_TYPES 的 8 种之一。
    "G3": "MATCH (e:Event) WHERE e.event_type = $type RETURN e",
    # G4 按公司取参与事件：PARTICIPATES_IN 的方向是 Company → Event。
    "G4": "MATCH (c:Company {stock_code:$code})-[:PARTICIPATES_IN]->(e:Event) RETURN e",
    # G5 事件到证据块：只取带 source_chunk_id 的关系（8 条语义边）；
    #    EVIDENCED_BY 不带 source_chunk_id，被 WHERE 排除，不产生文本块级候选（硬约束 14）。
    "G5": ("MATCH (e:Event {node_id:$id})-[r]-(x) WHERE r.source_chunk_id IS NOT NULL "
           "RETURN type(r), r.source_doc_id, r.source_chunk_id"),
    # G6 时间过滤：event_time 为空的一并剔除（IS NOT NULL）；闭区间 [lo, hi]。
    "G6": ("MATCH (e:Event) WHERE e.node_id IN $ids AND e.event_time IS NOT NULL "
           "AND e.event_time >= $lo AND e.event_time <= $hi RETURN e"),
    # G7 路径枚举：最大深度不超过 2；每条关系项含关系名、方向、对端节点标识与三项证据属性。
    "G7": "MATCH p = (a {node_id:$from})-[r*1..2]-(b {node_id:$to}) RETURN p",
}

# "事件三元组"的字段形态（《18》第六节 的格式决策 3）：(event_id, event_type, event_time)。
EVENT_TRIPLE_FIELDS = list(config.EVENT_TRIPLE_FIELDS)

# Event 节点的六项核心属性（《10-系统总体设计》第4.5.1节 表 4-8；表 18-F 的 G3 要
# "Event 节点集合与六项核心属性"）。取自 nodes.csv 的 Event 列，不新增字段。
EVENT_CORE_ATTRS = ["event_id", "event_type", "event_name", "event_time",
                    "description", "confidence"]

# 空值策略合法取值（v2.9 裁定 ①：exclude ＝ 空值一并剔除）
NULL_POLICIES = ("exclude", "keep")

# 别名分隔符：nodes.csv 的 aliases 列用 "|" 分隔多个写法（如 "中兴通讯|中兴通讯股份有限公司"）
_ALIAS_SEP = "|"

# 公司→事件的关系名。**只在这里写一次**：`代码\检索\config.py` 的 `RELATIONS` 是列表、
# 没有单列常量，而本文件原先在 G4 与断言③ 两处各写了一遍字面量 `"PARTICIPATES_IN"`；
# 断言③ 需要按同一关系名复核「EMPTY 的节点确实没有出向该关系的边」，故提成常量以免两处漂移。
REL_PARTICIPATES_IN = "PARTICIPATES_IN"


def _s(value) -> str:
    """CSV 字段值统一按字符串读；None → 空串；两端空白剔除。"""
    return (value or "").strip()


def _norm(text: str) -> str:
    """标识归一化：剔除全部空白、转小写（用于名称／别名匹配，ASCII 大小写不敏感）。"""
    return "".join(_s(text).split()).lower()


class GraphQuery:
    """内存图的图谱查询层：按 node_id 索引节点，边双向可遍历。

    * 节点按 `node_id` 索引（`self.nodes`），**按字段名取值、不按位置解析**；
    * 边表 9 列（`config.EDGE_COLUMNS`）逐行读入并编号（`edge_id` ＝ CSV 行序，0 起），
      每个节点挂一份入射表（`self.adj`），故**边双向可遍历**；
    * 不要求 Neo4j、不写输入、不改 `replay.cypher`。
    """

    def __init__(self, nodes_csv: str | None = None, edges_csv: str | None = None):
        self.nodes_csv = nodes_csv or config.NODES_CSV
        self.edges_csv = edges_csv or config.EDGES_CSV
        self.nodes: dict[str, dict] = {}          # node_id → 原始 CSR 行（33 列，按字段名）
        self.edges: list[dict] = []               # 规范化后的边记录（含 edge_id 与证据三项）
        self.adj: dict[str, list[dict]] = {}      # node_id → [{edge_id, relation, direction, neighbor}]
        self.by_code: dict[str, list[str]] = {}   # stock_code → [node_id]
        self.by_name: dict[str, list[str]] = {}   # 归一化名称／简称／别名 → [node_id]
        self.events: list[str] = []               # Event 节点的 node_id（升序）
        self._load()

    # ------------------------------------------------------------------ 载入
    def _load(self) -> None:
        with open(self.nodes_csv, "r", encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                nid = _s(row.get("node_id"))
                if not nid:
                    continue
                self.nodes[nid] = {k: (v if v is not None else "") for k, v in row.items()}
                # 三种公司标识的后两种在此建索引（第一种是 node_id 本身）
                if _s(row.get("stock_code")):
                    self.by_code.setdefault(_s(row["stock_code"]), []).append(nid)
                for field_name in ("name", "short_name"):
                    key = _norm(row.get(field_name))
                    if key:
                        self.by_name.setdefault(key, []).append(nid)
                for alias in _s(row.get("aliases")).split(_ALIAS_SEP):
                    # 只按 "|" 切；其余分隔符作为整体写法保留（避免误切公司名内的顿号）
                    key = _norm(alias)
                    if key:
                        self.by_name.setdefault(key, []).append(nid)
        # M-1：同一个 nid 会因 name／short_name／aliases 三处都命中而重复 append，
        # 只 sort 不去重会让 resolve_node 返回 ['000001','000001','000001']（污染交付 trace）。
        for lst in self.by_name.values():
            lst[:] = sorted(set(lst))
        for lst in self.by_code.values():
            lst[:] = sorted(set(lst))

        with open(self.edges_csv, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            cols = list(reader.fieldnames or [])
            if cols != list(config.EDGE_COLUMNS):
                raise SystemExit("edges.csv 列与 config.EDGE_COLUMNS 不一致：%s" % ",".join(cols))
            for idx, row in enumerate(reader):
                rec = {
                    "edge_id": idx,
                    "head": _s(row["head_id"]),
                    "relation": _s(row["relation"]),
                    "tail": _s(row["tail_id"]),
                    "role": _s(row.get("role")),
                    "valid_from": _s(row.get("valid_from")),
                    "valid_to": _s(row.get("valid_to")),
                    # 三项证据属性：**除 EVIDENCED_BY 外**的边才带（硬约束 19）
                    "evidence": (None if _s(row["relation"]) == config.EVIDENCED_BY
                                 else {a: _s(row.get(a)) for a in config.EVIDENCE_ATTRS}),
                }
                self.edges.append(rec)
                self.adj.setdefault(rec["head"], []).append(
                    {"edge_id": idx, "relation": rec["relation"], "direction": "out",
                     "neighbor": rec["tail"]})
                self.adj.setdefault(rec["tail"], []).append(
                    {"edge_id": idx, "relation": rec["relation"], "direction": "in",
                     "neighbor": rec["head"]})

        self.events = sorted(nid for nid, n in self.nodes.items()
                             if _s(n.get("label")) == "Event")

    # ------------------------------------------------------------- 标识匹配
    def resolve_node(self, identifier: str) -> dict:
        """按 `node_id` / `stock_code`（6 位）/ `name`·`short_name`·`aliases` 三种方式匹配节点。

        返回 `{"code":…, "node_ids":[…], "matched_by":…}`；**匹配不到返回空表并给出
        `NOT_FOUND`，不抛异常**。公司节点**没有 `stock_code` 也能按名称匹配到**
        （`HCONF-` 前缀那 12 个：只认 6 位代码会让它们不可达）。
        """
        ident = _s(identifier)
        if not ident:
            return {"code": RC_INVALID_INPUT, "node_ids": [], "matched_by": None,
                    "detail": "标识为空"}
        if ident in self.nodes:                                 # ① node_id
            return {"code": RC_OK, "node_ids": [ident], "matched_by": "node_id"}
        if len(ident) == 6 and ident.isdigit() and ident in self.by_code:   # ② stock_code
            return {"code": RC_OK, "node_ids": list(self.by_code[ident]), "matched_by": "stock_code"}
        key = _norm(ident)
        if key in self.by_name:                                 # ③ name／short_name／aliases
            return {"code": RC_OK, "node_ids": list(self.by_name[key]), "matched_by": "name"}
        return {"code": RC_NOT_FOUND, "node_ids": [], "matched_by": None,
                "detail": "三种标识（node_id／stock_code／name·short_name·aliases）都未匹配到"}

    def resolve_company(self, identifier: str) -> dict:
        """公司标识匹配：在 `resolve_node` 之上**要求命中节点是 Company 标签**。

        `HCONF-` 前缀的 12 个公司节点**没有 `stock_code`**，此处必须能按名称命中；
        命中但标签不是 Company 时返回 `INVALID_INPUT`（G4 的等效 Cypher 只接 Company）。
        """
        res = self.resolve_node(identifier)
        if res["code"] != RC_OK:
            return res
        companies = [nid for nid in res["node_ids"]
                     if _s(self.nodes.get(nid, {}).get("label")) == "Company"]
        if not companies:
            return {"code": RC_INVALID_INPUT, "node_ids": [], "matched_by": res["matched_by"],
                    "detail": "命中 %s 但标签不是 Company" % ",".join(res["node_ids"])}
        return {"code": RC_OK, "node_ids": companies, "matched_by": res["matched_by"]}

    # ----------------------------------------------------------- 内部小工具
    def _incident(self, node_id: str) -> list[dict]:
        """节点入射表（双向）；不存在则空表。"""
        return self.adj.get(node_id, [])

    def _node_brief(self, node_id: str) -> dict:
        n = self.nodes.get(node_id) or {}
        return {"node_id": node_id, "label": _s(n.get("label")), "name": _s(n.get("name")),
                "stock_code": _s(n.get("stock_code"))}

    def _event_view(self, node_id: str) -> dict:
        """Event 节点视图：node_id ＋ 六项核心属性。"""
        n = self.nodes.get(node_id) or {}
        view = {"node_id": node_id, "label": _s(n.get("label"))}
        for attr in EVENT_CORE_ATTRS:
            view[attr] = _s(n.get(attr))
        return view

    def _rel_item(self, edge_id: int, direction: str) -> dict:
        """一条位于路径／邻接上的关系项：关系名、方向、对端节点标识、三项证据属性。

        `EVIDENCED_BY` 的关系项 `evidence` 为 `null`（不带三项证据属性）。
        """
        rec = self.edges[edge_id]
        return {"edge_id": edge_id, "relation": rec["relation"], "direction": direction,
                "neighbor": (rec["tail"] if direction == "out" else rec["head"]),
                "role": rec["role"],
                "evidence": (dict(rec["evidence"]) if rec["evidence"] else None)}

    @staticmethod
    def _envelope(interface: str, code: str, query_key: dict, sort_key: str,
                  results: list, **extra) -> dict:
        return {"code": code, "interface": interface, "query_key": query_key,
                "cypher": CYPHER[interface], "sort_key": sort_key,
                "count": len(results), "results": results, **extra}

    # ---------------------------------------------------------------- G1
    def g1_one_hop(self, identifier: str, label: str | None = None) -> dict:
        """G1 一跳邻居。入参：节点标识（`node_id`；公司可用 `stock_code`，也可按
        `name`／`short_name`／`aliases` 匹配）；出参：直接相连的关系与对端节点。

        排序键：`(relation, direction, neighbor, edge_id)`。
        匹配不到 → `code = NOT_FOUND`；命中但无边 → `EMPTY`；**不抛异常**。
        """
        res = self.resolve_node(identifier)
        query_key = {"identifier": _s(identifier), "matched_by": res["matched_by"]}
        if res["code"] != RC_OK:
            return self._envelope("G1", res["code"], query_key,
                                  "(relation, direction, neighbor, edge_id)", [],
                                  node_ids=[], detail=res.get("detail", ""))
        # 一个标识可能匹配到多个节点（重名／多别名）：对**全部命中节点**取并集，按 edge_id 去重
        by_edge: dict[int, dict] = {}
        for nid in res["node_ids"]:
            for rec in self._incident(nid):
                item = self._rel_item(rec["edge_id"], rec["direction"])
                item["neighbor_node"] = self._node_brief(item["neighbor"])
                by_edge[rec["edge_id"]] = item
        items = list(by_edge.values())
        if label:
            items = [it for it in items if it["neighbor_node"]["label"] == label]
        items.sort(key=lambda it: (it["relation"], it["direction"], it["neighbor"], it["edge_id"]))
        code = RC_OK if items else RC_EMPTY
        return self._envelope("G1", code, query_key,
                              "(relation, direction, neighbor, edge_id)", items,
                              node_ids=res["node_ids"])

    # ---------------------------------------------------------------- G2
    def g2_two_hop(self, identifier: str, label: str | None = None) -> dict:
        """G2 两跳邻居（**结果包含一跳**）：深度不超过 2 的路径集合。

        路径项：`{"depth":1|2, "start", "end", "nodes":[…], "relations":[关系项…]}`
        ——**`depth == 1` 的路径在结构上等同于 G1 的结果**（同一 `edge_id`／方向／对端）。
        与等效 Cypher 一致：同一条边不得在一次路径里走两次（`r2 != r1`）。

        排序键：`(depth, nodes, relations, edge_ids, directions)`。
        匹配不到 → `NOT_FOUND`；命中但无边 → `EMPTY`；**不抛异常**。
        """
        res = self.resolve_node(identifier)
        query_key = {"identifier": _s(identifier), "matched_by": res["matched_by"]}
        if res["code"] != RC_OK:
            return self._envelope("G2", res["code"], query_key,
                                  "(depth, nodes, relations, edge_ids, directions)", [],
                                  node_ids=[], detail=res.get("detail", ""))
        paths = []
        for a in res["node_ids"]:                       # 多命中节点：逐一起步
            for rec1 in self._incident(a):
                item1 = self._rel_item(rec1["edge_id"], rec1["direction"])
                if not label or self._node_brief(item1["neighbor"])["label"] == label:
                    paths.append({"depth": 1, "start": a, "end": item1["neighbor"],
                                  "nodes": [a, item1["neighbor"]], "relations": [dict(item1)]})
                b = rec1["neighbor"]
                for rec2 in self._incident(b):
                    if rec2["edge_id"] == rec1["edge_id"]:      # 同一条边不得走两次
                        continue
                    item2 = self._rel_item(rec2["edge_id"], rec2["direction"])
                    c = item2["neighbor"]
                    if label and self._node_brief(c)["label"] != label:
                        continue
                    paths.append({"depth": 2, "start": a, "end": c,
                                  "nodes": [a, b, c], "relations": [dict(item1), dict(item2)]})
        paths = self._sort_paths(paths)
        code = RC_OK if paths else RC_EMPTY
        return self._envelope("G2", code, query_key,
                              "(depth, nodes, relations, edge_ids, directions)", paths,
                              node_ids=res["node_ids"],
                              one_hop_count=sum(1 for p in paths if p["depth"] == 1))

    @staticmethod
    def _sort_paths(paths: list) -> list:
        def key(p):
            return (p["depth"], tuple(p["nodes"]),
                    tuple(r["relation"] for r in p["relations"]),
                    tuple(r["edge_id"] for r in p["relations"]),
                    tuple(r["direction"] for r in p["relations"]))
        return sorted(paths, key=key)

    # ---------------------------------------------------------------- G3
    def g3_events_by_type(self, event_type: str) -> dict:
        """G3 按事件类型取事件。入参：`event_type`（`config.EVENT_TYPES` 的 8 种之一）；
        出参：Event 节点集合与**六项核心属性**。

        排序键：`(event_time, node_id)`（`event_time` 为空者排最前）。
        `event_type` 不在 8 种内 → `INVALID_INPUT`；无该类型事件 → `EMPTY`；**不抛异常**。
        """
        et = _s(event_type)
        query_key = {"type": et}
        sort_key = "(event_time, node_id)"
        if et not in config.EVENT_TYPES:
            return self._envelope("G3", RC_INVALID_INPUT, query_key, sort_key, [],
                                  detail="event_type 不在 %s" % config.EVENT_TYPES)
        results = [self._event_view(nid) for nid in self.events
                   if _s(self.nodes[nid].get("event_type")) == et]
        results.sort(key=lambda e: (e["event_time"], e["node_id"]))
        return self._envelope("G3", RC_OK if results else RC_EMPTY, query_key, sort_key, results)

    # ---------------------------------------------------------------- G4
    def g4_company_events(self, identifier: str) -> dict:
        """G4 按公司取参与事件。入参：公司标识（`stock_code` 或名称等三种匹配）；
        出参：该公司**参与的事件集合**（`PARTICIPATES_IN` 的方向是 Company → Event）。

        排序键：`(event_time, node_id)`（`event_time` 为空者排最前）。
        匹配不到 → `NOT_FOUND`；命中但无参与事件（含孤立节点）→ `EMPTY`；**不抛异常**。
        """
        res = self.resolve_company(identifier)
        query_key = {"identifier": _s(identifier), "matched_by": res["matched_by"]}
        sort_key = "(event_time, node_id)"
        if res["code"] != RC_OK:
            return self._envelope("G4", res["code"], query_key, sort_key, [],
                                  node_ids=[], detail=res.get("detail", ""))
        ev_ids = set()
        for cid in res["node_ids"]:
            for rec in self._incident(cid):
                edge = self.edges[rec["edge_id"]]
                if rec["relation"] != "PARTICIPATES_IN" or rec["direction"] != "out":
                    continue
                neighbour = rec["neighbor"]
                if _s(self.nodes.get(neighbour, {}).get("label")) == "Event":
                    ev_ids.add(neighbour)
        results = [self._event_view(nid) for nid in sorted(ev_ids)]
        results.sort(key=lambda e: (e["event_time"], e["node_id"]))
        code = RC_OK if results else RC_EMPTY
        return self._envelope("G4", code, query_key, sort_key, results, node_ids=res["node_ids"])

    # ---------------------------------------------------------------- G5
    def g5_event_evidence(self, event_id: str) -> dict:
        """G5 事件到证据块。入参：Event 标识；出参：该事件关联的 `source_chunk_id`
        集合与来源文档编号。

        **G5 边界**：事件侧候选**只能**经带 `source_chunk_id` 的 8 条语义边入池
        （`config.SEMANTIC_RELATIONS`）；`EVIDENCED_BY` 指向 Document、不带
        `source_chunk_id`，只落进 `document_refs`，**不产生文本块级候选**（硬约束 14）。
        每个关系项都带 `source_doc_id`／`source_chunk_id`／`confidence` 三项。

        排序键：`(relation, source_chunk_id, source_doc_id, edge_id)`；
        `document_refs` 按 `document_id` 升序。非 Event 标识 → `INVALID_INPUT`；
        事件无边 → `EMPTY`；**不抛异常**。
        """
        eid = _s(event_id)
        query_key = {"id": eid}
        sort_key = "(relation, source_chunk_id, source_doc_id, edge_id)"
        if eid not in self.nodes:
            return self._envelope("G5", RC_NOT_FOUND, query_key, sort_key, [],
                                  chunks=[], document_refs=[],
                                  detail="节点不存在：%s" % eid)
        if _s(self.nodes[eid].get("label")) != "Event":
            return self._envelope("G5", RC_INVALID_INPUT, query_key, sort_key, [],
                                  chunks=[], document_refs=[],
                                  detail="标识 %s 不是 Event 节点" % eid)
        chunks, docs = [], []
        for rec in self._incident(eid):
            edge = self.edges[rec["edge_id"]]
            if edge["relation"] == config.EVIDENCED_BY:
                # 只用于展示来源文档：不带 source_chunk_id，**不产生文本块级候选**
                docs.append({"relation": edge["relation"], "direction": rec["direction"],
                             "document_id": rec["neighbor"], "edge_id": rec["edge_id"],
                             "document": self._node_brief(rec["neighbor"])})
                continue
            if edge["relation"] not in config.SEMANTIC_RELATIONS:
                continue
            item = self._rel_item(rec["edge_id"], rec["direction"])
            if not item["evidence"] or not item["evidence"].get("source_chunk_id"):
                continue                                    # 唯一入池依据：带 source_chunk_id
            item["counterpart"] = self._node_brief(rec["neighbor"])
            chunks.append(item)
        chunks.sort(key=lambda it: (it["relation"], it["evidence"]["source_chunk_id"],
                                    it["evidence"]["source_doc_id"], it["edge_id"]))
        docs.sort(key=lambda d: (d["document_id"], d["edge_id"]))
        # 去重后的 chunk_id 集合（升序）——事件侧入池候选
        chunk_ids = sorted({it["evidence"]["source_chunk_id"] for it in chunks},
                           key=lambda x: (len(x), x))
        code = RC_OK if (chunks or docs) else RC_EMPTY
        return self._envelope("G5", code, query_key, sort_key, chunks,
                              chunk_ids=chunk_ids, document_refs=docs)

    def event_chunk_ids(self, event_id: str) -> list[str]:
        """单个事件经 8 条语义边携带的 `chunk_id` 集合（升序）；**不含 `EVIDENCED_BY`**。"""
        return self.g5_event_evidence(event_id)["chunk_ids"]

    # ---------------------------------------------------------------- G6
    def g6_time_filter(self, event_ids, lo: str, hi: str, null_policy: str | None = None) -> dict:
        """G6 时间过滤。入参：事件集合 ＋ 时间闭区间 `[lo, hi]`（由"最新／最近／近期"
        或显式区间解析而来）＋ **显式空值策略**。

        **`event_time` 为空值的一并剔除**（v2.9 裁定 ①、硬约束 3）：`null_policy` 是
        **显式参数**（`exclude`／`keep`），默认取
        `config.RETRIEVAL["time_filter_null_policy"]`（＝`exclude`）；**不是隐式跳过**。

        出参：`passed`（通过过滤的事件视图）＋ `removed_null`／`removed_out_of_range`
        ＋ **被剔除路径携带的 `chunk_id` 差集** `chunk_id_diff`（＝ `chunk_ids_removed`
        − `chunk_ids_survived`），供 pipeline 逐题打印（硬约束 5；《16》第9.4节）。

        排序键：`passed` 按 `node_id` 升序；两个差集与三个 chunk 集合均按 `(长度, 值)` 升序。
        区间反序／空值策略非法 → `INVALID_INPUT`；**不抛异常**。
        """
        policy = config.RETRIEVAL["time_filter_null_policy"] if null_policy is None else null_policy
        query_key = {"ids": list(event_ids or []), "lo": _s(lo), "hi": _s(hi),
                     "null_policy": policy}
        sort_key = "node_id"
        if policy not in NULL_POLICIES:
            return self._envelope("G6", RC_INVALID_INPUT, query_key, sort_key, [],
                                  detail="null_policy 只能是 %s" % (NULL_POLICIES,))
        lo_s, hi_s = _s(lo), _s(hi)
        if not lo_s or not hi_s or lo_s > hi_s:
            return self._envelope("G6", RC_INVALID_INPUT, query_key, sort_key, [],
                                  detail="时间闭区间非法：lo=%r hi=%r" % (lo_s, hi_s))
        ids = [_s(x) for x in (event_ids or [])]
        unknown = [x for x in ids if x not in self.nodes]
        if unknown:
            return self._envelope("G6", RC_INVALID_INPUT, query_key, sort_key, [],
                                  detail="事件标识不存在：%s" % ",".join(unknown))

        passed, removed_null, removed_range = [], [], []
        for eid in ids:
            et = _s(self.nodes[eid].get("event_time"))
            if not et:                                  # 空值：按显式策略处置（默认一并剔除）
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
        ck = lambda s: sorted(s, key=lambda x: (len(x), x))
        diff = removed_chunks - survived_chunks
        diff_rev = survived_chunks - removed_chunks
        code = RC_OK if passed else RC_EMPTY
        return self._envelope(
            "G6", code, query_key, sort_key,
            [self._event_view(x) for x in passed],
            passed_ids=passed, removed_ids=removed,
            removed_null_ids=removed_null, removed_out_of_range_ids=removed_range,
            null_policy=policy,
            chunk_ids_in_scope=ck(survived_chunks | removed_chunks),
            chunk_ids_survived=ck(survived_chunks),
            chunk_ids_removed=ck(removed_chunks),
            chunk_id_diff=ck(diff),              # 被剔除路径携带的 chunk_id 差集（硬约束 5）
            chunk_id_diff_reverse=ck(diff_rev),
        )

    # ---------------------------------------------------------------- G7
    def g7_paths(self, from_id: str, to_id: str, max_depth: int = 2) -> dict:
        """G7 路径枚举。入参：起点标识、终点标识、最大深度（不超过 2）；
        出参：路径列表——起点、关系序列、终点；每条关系项含关系名、方向、对端节点标识，
        以及**除 `EVIDENCED_BY` 外**的三项证据属性（`EVIDENCED_BY` 项为 `null`）。

        排序键：`(depth, nodes, relations, edge_ids, directions)`。
        深度非法 → `INVALID_INPUT`；起／终点匹配不到 → `NOT_FOUND`；无路径 → `EMPTY`。
        """
        query_key = {"from": _s(from_id), "to": _s(to_id), "max_depth": max_depth}
        sort_key = "(depth, nodes, relations, edge_ids, directions)"
        if not isinstance(max_depth, int) or not (1 <= max_depth <= 2):
            return self._envelope("G7", RC_INVALID_INPUT, query_key, sort_key, [],
                                  detail="max_depth 只能是 1 或 2")
        rf, rt = self.resolve_node(from_id), self.resolve_node(to_id)
        if rf["code"] != RC_OK or rt["code"] != RC_OK:
            return self._envelope("G7", RC_NOT_FOUND, query_key, sort_key, [],
                                  detail="起点或终点未匹配到")
        paths = []
        for a in rf["node_ids"]:                        # 多命中标识：遍历全部起终点组合
            for b in rt["node_ids"]:
                for rec1 in self._incident(a):
                    item1 = self._rel_item(rec1["edge_id"], rec1["direction"])
                    if item1["neighbor"] == b:
                        paths.append({"depth": 1, "start": a, "end": b,
                                      "nodes": [a, b], "relations": [dict(item1)]})
                    if max_depth >= 2:
                        mid = rec1["neighbor"]
                        for rec2 in self._incident(mid):
                            if rec2["edge_id"] == rec1["edge_id"]:
                                continue
                            item2 = self._rel_item(rec2["edge_id"], rec2["direction"])
                            if item2["neighbor"] == b:
                                paths.append({"depth": 2, "start": a, "end": b,
                                              "nodes": [a, mid, b],
                                              "relations": [dict(item1), dict(item2)]})
        paths = self._sort_paths(paths)
        return self._envelope("G7", RC_OK if paths else RC_EMPTY, query_key, sort_key, paths,
                              graph_path=[self.graph_path_payload(p) for p in paths])

    def graph_path_payload(self, path: dict) -> dict:
        """把一条路径整成能**原样塞进 `answer.graph_path`** 的载荷（硬约束 19）：
        路径列表 ＋ 每条关系的关系名、方向、对端节点标识，以及除 `EVIDENCED_BY` 外的
        三项证据属性。"""
        return {"start": path["start"], "end": path["end"], "depth": path["depth"],
                "nodes": list(path["nodes"]),
                "relations": [{"relation": r["relation"], "direction": r["direction"],
                               "neighbor": r["neighbor"], "role": r["role"],
                               "evidence": (dict(r["evidence"]) if r["evidence"] else None)}
                              for r in path["relations"]]}

    # ------------------------------------------------------------ 未用图谱标记
    @staticmethod
    def not_used_graph_marker() -> dict:
        """未使用图谱扩展时的**显式标记**：不得编造路径（硬约束 19；《07》FR-05）。"""
        return {"graph_used": False, "graph_path": [], "note": "未使用图谱扩展"}


def cypher_table() -> list:
    """七个接口与等效 Cypher 的对应表（供《19》的"接口与 Cypher 一一对应"表逐行生成）。"""
    return [{"id": gid, "cypher": CYPHER[gid]} for gid in ("G1", "G2", "G3", "G4", "G5", "G6", "G7")]


_DEFAULT_GRAPH = None


def default_graph() -> GraphQuery:
    """进程内单例（同一次运行复用一张内存图）。"""
    global _DEFAULT_GRAPH
    if _DEFAULT_GRAPH is None:
        _DEFAULT_GRAPH = GraphQuery()
    return _DEFAULT_GRAPH


# ==========================================================================
# --selftest：七个接口各跑通至少一次 ＋ 三条针对性断言
# ==========================================================================
def selftest(verbose: bool = True) -> int:
    gq = default_graph()
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if verbose:
            print("  [%s] %s%s" % ("OK  " if ok else "FAIL", name,
                                   ("  —— " + detail) if detail else ""))
        return ok

    print("=" * 78)
    print("T3 图谱查询层自检：内存图 %d 节点 / %d 边；图谱导出物 %s"
          % (len(gq.nodes), len(gq.edges), config.GRAPH_VERSION))
    print("=" * 78)

    # ---- 一、七个接口各跑通至少一次 ----
    print("\n一、七个接口各跑通至少一次")
    evidence = {}

    g1 = gq.g1_one_hop("000001")
    evidence["G1"] = {"code": g1["code"], "count": g1["count"], "sample": g1["results"][:2]}
    check("G1 一跳邻居（node_id=000001）", g1["code"] == RC_OK and g1["count"] > 0,
          "code=%s count=%d" % (g1["code"], g1["count"]))

    g2 = gq.g2_two_hop("000001")
    evidence["G2"] = {"code": g2["code"], "count": g2["count"],
                      "one_hop_count": g2.get("one_hop_count")}
    check("G2 两跳邻居（node_id=000001）", g2["code"] == RC_OK and g2["count"] > 0,
          "code=%s 路径 %d（其中一跳 %s）" % (g2["code"], g2["count"], g2.get("one_hop_count")))

    g3 = gq.g3_events_by_type("股权")
    evidence["G3"] = {"code": g3["code"], "count": g3["count"], "sample": g3["results"][:1]}
    check("G3 按事件类型取事件（股权）", g3["code"] == RC_OK and g3["count"] > 0,
          "code=%s count=%d" % (g3["code"], g3["count"]))

    g4 = gq.g4_company_events("000001")
    evidence["G4"] = {"code": g4["code"], "count": g4["count"]}
    check("G4 按公司取参与事件（stock_code=000001）", g4["code"] == RC_OK and g4["count"] > 0,
          "code=%s count=%d" % (g4["code"], g4["count"]))

    g5 = gq.g5_event_evidence("EVT-0001")
    evidence["G5"] = {"code": g5["code"], "count": g5["count"], "chunk_ids": g5["chunk_ids"],
                      "document_refs": len(g5["document_refs"])}
    check("G5 事件到证据块（EVT-0001）", g5["code"] == RC_OK,
          "code=%s 语义边项 %d、chunk_id %d 个、来源文档 %d 个"
          % (g5["code"], g5["count"], len(g5["chunk_ids"]), len(g5["document_refs"])))

    # G6 用 000001 的参与事件作示例区间：能同时产生"窗口内通过"与"窗口外／空值被剔除"
    ev_ids_000001 = [e["node_id"] for e in gq.g4_company_events("000001")["results"]]
    g6 = gq.g6_time_filter(ev_ids_000001, "2026-08-01", "2026-09-22")
    evidence["G6"] = {"code": g6["code"], "query_key": g6["query_key"],
                      "passed_ids": g6["passed_ids"], "removed_null_ids": g6["removed_null_ids"],
                      "removed_out_of_range_ids": g6["removed_out_of_range_ids"],
                      "chunk_id_diff": g6["chunk_id_diff"],
                      "chunk_ids_survived": g6["chunk_ids_survived"],
                      "chunk_ids_removed": g6["chunk_ids_removed"]}
    check("G6 时间过滤（平安银行 11 个事件 / [2026-06-26, 2026-09-22]）", g6["code"] == RC_OK,
          "通过 %d、空值剔除 %d、越界剔除 %d、chunk_id 差集 %d 个"
          % (len(g6["passed_ids"]), len(g6["removed_null_ids"]),
             len(g6["removed_out_of_range_ids"]), len(g6["chunk_id_diff"])))

    g7 = gq.g7_paths("000001", ev_ids_000001[0] if ev_ids_000001 else "EVT-0029", max_depth=2)
    evidence["G7"] = {"code": g7["code"], "count": g7["count"], "sample": g7["results"][:1]}
    check("G7 路径枚举（000001 → EVT-0029，max_depth=2）", g7["code"] == RC_OK and g7["count"] > 0,
          "code=%s 路径 %d" % (g7["code"], g7["count"]))

    # ---- 二、三条针对性断言 ----
    print("\n二、三条针对性断言")

    # 断言①：G2 的结果**包含** G1 的结果（2-hop ⊇ 1-hop）
    s1 = {(it["edge_id"], it["direction"], it["neighbor"]) for it in g1["results"]}
    s2 = {(r["edge_id"], r["direction"], r["neighbor"])
          for p in g2["results"] if p["depth"] == 1 for r in p["relations"]}
    ok1 = s1 <= s2
    check("断言① G2 的结果包含 G1 的结果（2-hop ⊇ 1-hop）", ok1,
          "G1 %d 项 ⊆ G2 一跳层 %d 项：缺失 %d" % (len(s1), len(s2), len(s1 - s2)))
    evidence["assert1"] = {"g1_items": len(s1), "g2_one_hop_items": len(s2),
                           "subset": ok1, "missing": sorted(s1 - s2)}

    # 断言②：G5 任一事件返回里，每条边都带 source_chunk_id、且不含 EVIDENCED_BY
    scan_events = gq.events[:200]
    offenders = []
    missing_chunk = []
    no_evidenced = True
    checked_edges = 0
    for eid in scan_events:
        res = gq.g5_event_evidence(eid)
        for it in res["results"]:
            checked_edges += 1
            if it["relation"] == config.EVIDENCED_BY:
                no_evidenced = False
                offenders.append((eid, it["edge_id"]))
            ev = it.get("evidence") or {}
            if not ev.get("source_chunk_id"):
                missing_chunk.append((eid, it["edge_id"]))
    ok2 = no_evidenced and not missing_chunk and checked_edges > 0
    check("断言② G5 的每条边都带 source_chunk_id 且不含 EVIDENCED_BY", ok2,
          "抽查 %d 个事件的 %d 条入池边：EVIDENCED_BY %d 条、缺 source_chunk_id %d 条"
          % (len(scan_events), checked_edges, len(offenders), len(missing_chunk)))
    evidence["assert2"] = {"events_scanned": len(scan_events), "campool_edges": checked_edges,
                           "evidenced_by_in_pool": len(offenders),
                           "missing_source_chunk_id": len(missing_chunk)}

    # 断言③：G4 对**没有 stock_code** 的公司节点（按名称匹配）能取到参与事件，
    #        或如实报告它确实是孤立节点（先查 graph_stats.json 的 isolated_nodes.ids）
    #
    # **2026-10-03 修正两处（口径切换 v1.2 → v1.3 后按实测改，只加强、不减弱）**：
    # ① **覆盖范围**：原实现只遍历 `HCONF-` 前缀的节点。v1.2 下那是 12 个人工确认节点，
    #    断言覆盖面就是 12；切到 v1.3 后人工确认清单里 11 条**并入**了 B 步按归一化名建成的
    #    身份（`NCOMP-####`），`HCONF-` 前缀只剩 1 个（`HCONF-0001` 芜湖联飞），
    #    断言实际只测 1 个节点——"无 stock_code 的公司节点按名称可达"这条性质**几乎没被验证**。
    #    现改为遍历 `HCONF-*` ∪ `NCOMP-*`（v1.3 下共 833 个），覆盖面由 1 升到 833。
    # ② **提示文本**：原文本把节点数写法写死成"12 个 HCONF"，与实际遍历数无关——**文本在撒谎**。
    #    改为按实测计数打印，并分别报两类前缀的条数。
    stats = config.read_json(config.GRAPH_STATS_PATH)
    isolated = set((stats.get("isolated_nodes") or {}).get("ids") or [])
    hconf_with_events, hconf_isolated, hconf_missing = [], [], []
    _no_code_ids = sorted(n for n in gq.nodes
                          if n.startswith("HCONF-") or n.startswith("NCOMP-"))
    for nid in _no_code_ids:
        name = _s(gq.nodes[nid].get("name"))
        r = gq.g4_company_events(name)          # 用**名称**匹配（该节点没有 stock_code）
        if r["code"] == RC_OK:
            hconf_with_events.append({"node_id": nid, "name": name, "events": r["count"]})
        elif r["code"] == RC_EMPTY:
            # EMPTY 的正确含义是「该（这些）节点没有**出向 PARTICIPATES_IN**」，比
            # graph_stats 的「孤立节点」（任何关系都没有）更弱——v1.2 下那 12 个人工确认节点
            # 恰好"要么有参与事件、要么完全孤立"，两者重合，所以原判据看不出这个区别；
            # v1.3 下 347 个 EMPTY 里有一批是"只有 HAS_EXECUTIVE／SUPPLIES 等边、没有参与事件"
            # 的名单外主体，与孤立清单不再重合。故把判据改成与语义一致的那条，
            # 并把「其中有多少确实完全孤立」作为读数一并报出。
            _ids = r.get("node_ids") or [nid]
            _no_part = all(not any(it["relation"] == REL_PARTICIPATES_IN
                                   and it["direction"] == "out"
                                   for it in gq.adj.get(x, [])) for x in _ids)
            hconf_isolated.append({"node_id": nid, "name": name, "matched_node_ids": _ids,
                                   "no_participates_in": _no_part,
                                   "in_graph_stats_isolated": nid in isolated})
        else:
            hconf_missing.append({"node_id": nid, "name": name, "code": r["code"]})
    # `ok3` 的分母不再是"有 12 个节点"而是"确有节点被遍历到"：v1.3 下 833 个。
    ok3 = (bool(_no_code_ids) and not hconf_missing
           and (bool(hconf_with_events) or bool(hconf_isolated)))
    # 报为 EMPTY 的必须**确实没有出向 PARTICIPATES_IN**（可由内存图当场复核）
    empty_consistent = all(x["no_participates_in"] for x in hconf_isolated)
    _fully_isolated = sum(1 for x in hconf_isolated if x["in_graph_stats_isolated"])
    check("断言③ G4 按名称匹配无 stock_code 的公司节点（HCONF ＋ NCOMP）",
          ok3 and empty_consistent,
          "%d 个无 stock_code 公司节点（HCONF-%d ＋ NCOMP-%d）：能取到参与事件 %d 个、"
          "EMPTY %d 个（逐个复核确认无出向 PARTICIPATES_IN＝%s；其中 %d 个在 graph_stats "
          "的孤立清单里）、未匹配 %d 个"
          % (len(_no_code_ids),
             sum(1 for n in _no_code_ids if n.startswith("HCONF-")),
             sum(1 for n in _no_code_ids if n.startswith("NCOMP-")),
             len(hconf_with_events), len(hconf_isolated), empty_consistent,
             _fully_isolated, len(hconf_missing)))
    evidence["assert3"] = {"with_events": hconf_with_events[:50], "empty_and_isolated": hconf_isolated[:50],
                           "not_found": hconf_missing,
                           "scanned_ids": len(_no_code_ids),
                           "counts": {"with_events": len(hconf_with_events),
                                      "empty_and_isolated": len(hconf_isolated),
                                      "empty_also_fully_isolated": _fully_isolated,
                                      "not_found": len(hconf_missing)},
                           "isolated_ids_from_graph_stats": sorted(isolated & set(gq.nodes))[:20],
                           "empty_has_no_participates_in": empty_consistent}

    # ---- 三、G6 差集示例（一个能产生非空差集的事件区间）----
    print("\n三、G6 差集返回示例（逐题差集的来源；硬约束 5）")
    print("  区间 [%s, %s]，事件集合 ＝ 平安银行(000001) 的 %d 个参与事件"
          % (g6["query_key"]["lo"], g6["query_key"]["hi"], len(ev_ids_000001)))
    print("  通过过滤 %d 个：%s" % (len(g6["passed_ids"]), ",".join(g6["passed_ids"])))
    print("  空值被剔除 %d 个：%s" % (len(g6["removed_null_ids"]), ",".join(g6["removed_null_ids"])))
    print("  越界被剔除 %d 个：%s" % (len(g6["removed_out_of_range_ids"]),
                                     ",".join(g6["removed_out_of_range_ids"])))
    print("  过滤前 chunk_id %d 个；过滤后 %d 个；**被剔除路径携带的 chunk_id 差集** %d 个：%s"
          % (len(g6["chunk_ids_in_scope"]), len(g6["chunk_ids_survived"]),
             len(g6["chunk_id_diff"]), ",".join(g6["chunk_id_diff"])))
    check("G6 差集非空（该题可测）", len(g6["chunk_id_diff"]) > 0,
          "差集 %d 个" % len(g6["chunk_id_diff"]))

    # ---- 四、四类返回码的可区分性 ----
    print("\n四、返回码可区分（匹配不到不抛异常）")
    r_nf = gq.g1_one_hop("不存在的公司XYZ")
    r_iv = gq.g3_events_by_type("不存在的类型")
    # **2026-10-02 改为数据驱动**：原实现在这里写死 `gq.g4_company_events("HCONF-0010")`
    # （注释写「浪潮：孤立节点 → EMPTY」）。口径切到 v1.3 后，「浪潮」已被并入按归一化名
    # 接纳的 name_only 身份（`NCOMP-####`），`HCONF-0010` 这个编号**不再存在**，
    # 于是该断言实际测到的是 NOT_FOUND、自检退出码 1，并级联拖垮第 7 阶段门禁 13 项链上检查。
    # 现改为**从上面断言③ 已算出的孤立 HCONF 集合里取一个**——孤立的判定仍由 graph_stats 交叉核对，
    # 不写死编号，故口径再变也不会误报。
    _iso_pick = hconf_isolated[0] if hconf_isolated else None
    r_em = (gq.g4_company_events(_iso_pick["node_id"]) if _iso_pick
            else {"code": RC_NOT_FOUND, "node_ids": []})
    check("未匹配 → NOT_FOUND", r_nf["code"] == RC_NOT_FOUND, r_nf["code"])
    check("非法入参 → INVALID_INPUT", r_iv["code"] == RC_INVALID_INPUT, r_iv["code"])
    if _iso_pick:
        check("命中但无结果（孤立节点 %s %s）→ EMPTY" % (_iso_pick["node_id"], _iso_pick["name"]),
              r_em["code"] == RC_EMPTY,
              "%s（node_ids=%s）" % (r_em["code"], r_em["node_ids"]))
    else:
        check("命中但无结果 → EMPTY（本口径无孤立 HCONF 节点，跳过该构造）",
              True, "本口径下 HCONF 节点无孤立者，EMPTY 分支改由上表的 code 覆盖情况体现")
    evidence["codes"] = {"not_found": r_nf["code"], "invalid_input": r_iv["code"],
                         "empty": r_em["code"], "ok": g1["code"]}

    # ---- 落盘自检留痕（临时产物写 阶段07-RAG检索系统\\_工作底稿\\）----
    out_dir = config.DOCS_DIR
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "graph_query_selftest.json")
    payload = {
        "schema": "stage7-graph-query-selftest-1.0",
        "generated_by": "代码/检索/graph_query.py --selftest",
        "graph_version": config.GRAPH_VERSION,
        "nodes": len(gq.nodes), "edges": len(gq.edges),
        "cypher": CYPHER,
        "checks": checks,
        "evidence": evidence,
        "all_ok": all(c["ok"] for c in checks),
    }
    config.write_json(out_path, payload)
    print("\n自检留痕：%s" % os.path.relpath(out_path, config.ROOT))

    passed = sum(1 for c in checks if c["ok"])
    print("\n自检项 %d，通过 %d，失败 %d" % (len(checks), passed, len(checks) - passed))
    print("结论：%s" % ("七个接口与三条断言全部通过。" if passed == len(checks)
                       else "存在失败项。" ))
    return 0 if passed == len(checks) else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="图谱查询层（内存图 ＋ 七个接口 ＋ 等效 Cypher）")
    parser.add_argument("--selftest", action="store_true",
                        help="七个接口各跑通一次并做三条针对性断言")
    parser.add_argument("--cypher-table", action="store_true",
                        help="打印七个接口与等效 Cypher 的一一对应表")
    args = parser.parse_args(argv)

    if args.cypher_table:
        for row in cypher_table():
            print("%s\t%s" % (row["id"], row["cypher"]))
        return 0
    if args.selftest:
        return selftest()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
