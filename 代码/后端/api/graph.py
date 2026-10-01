# -*- coding: utf-8 -*-
"""代码\\后端\\api\\graph.py —— 第 9 阶段事件知识图谱接口（表 4-13 的五条）。

| 方法 | 路径 | 处理 | 错误码 |
| --- | --- | --- | --- |
| GET | `/api/graph/entities` | 按名称或代码查实体（`keyword`／`type`／分页） | 1002 |
| GET | `/api/graph/entities/{node_id}/neighbors` | 一跳邻居（可选 `relation`／`direction`） | 1002／2001 |
| GET | `/api/graph/paths` | 多跳路径（`from_node` ＋ `to_node` 或 `relation`、`hop`） | 1002 |
| GET | `/api/graph/events` | 按条件查事件（`event_type`／`stock_code`／时间窗／分页） | 1002 |
| GET | `/api/graph/events/{event_id}` | 事件详情与多来源证据 | 2001 |

七条纪律
--------
1. **不修改 `services\\graph_service.py`**：G1／G3／G4／G5／G6／G7 六个既有查询接口**直接调用**
   （本文件只做接口层的参数校验、过滤与响应整形）；表 4-13 里图谱侧没有覆盖到的三件事——
   实体检索、`from_node ＋ relation` 的定关系多跳、全量事件列举——在本文件里另写
   `GraphReader`，并按后端（`neo4j`／`memory`）分别实现，语义与既有接口保持一致。
2. **空结果不是错误**（硬约束 6／错误码表）：查不到一律 HTTP 200 ＋ 空 `items`／空 `paths`／
   空 `nodes`＋`edges`（表 4-13 中该语义对应错误码 **2002**；本项目既有三条接口的既定做法是
   **用空数据表达、响应体里不出现 2002 这个码**，本文件沿用同一做法，见 `api\\evidence.py`
   模块头第 1 条的同一口径）。
3. **图谱服务不可用 → 3001**：`graph_service.open_backend()` 在 Neo4j 连不上时以 `SystemExit`
   报告（`_make_driver()` 的口径），本文件把它与其它异常一并收敛为 `ApiError(3001)`；
   **不做任何自动降级**（不去偷偷换成内存后端绕开 Neo4j 不可用）。
4. **时间过滤一律按 `event_time`**（《24》硬约束与 v2.9 裁定 ①）：`event_time` 为空的 Event
   **一并剔除**（空值策略取自 `config.RETRIEVAL["time_filter_null_policy"]`，当前为 `exclude`，
   与 G6 的 `null_policy` 同源）。
5. **路径上的证据三项**：除 `EVIDENCED_BY` 外的关系项一律返回 `source_doc_id`／
   `source_chunk_id`／`confidence`；`EVIDENCED_BY` 指向 Document 节点，此时返回
   `evidence_doc_id` 而**不返回**上述三项（《10》第 4.7.3 节）。
6. **响应体纪律**：错误响应键集合恰为 `{code, message}`（`detail` 只进日志）；成功一律
   `errors.ok(...)` 信封，分页数据用 `errors.ok_page(...)`。
7. **只读**：本文件不写任何数据库表、不改任何上游文件；全部是对 MySQL 只读查询 ＋
   图谱后端的只读查询。
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from datetime import datetime

from fastapi import APIRouter

import db
import errors
from services import graph_service as gs

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger
router = APIRouter(tags=["graph"])

# --------------------------------------------------------------------------
# 1. 口径常量（全部取自既有出处，不写死）
# --------------------------------------------------------------------------
ENTITY_LABELS = ("Company", "Person", "Industry", "Institution", "Event", "Policy")
"""表 4-13 的 `type` 合法取值（**六个实体标签**；`Document` 是证据标签，不算第 7 个实体）。"""

RELATIONS = tuple(gs.RETRIEVAL_CONFIG.SEMANTIC_RELATIONS) + (gs.EVIDENCED_BY,)
"""9 条核心关系：8 条核心语义关系（检索侧 config 的 `SEMANTIC_RELATIONS`）＋ `EVIDENCED_BY`。"""

EVIDENCE_ATTRS = list(gs.EVIDENCE_ATTRS)
EVIDENCED_BY = gs.EVIDENCED_BY
EVENT_TYPES = list(gs.EVENT_TYPES)

PAGE_SIZE_MAX = 200
"""`page_size` 上限（与 `api\\history.py` 同值，防止一次拉全图）。"""

DEFAULT_PAGE_SIZE = 20

MAX_NODE_ID_LEN = 128
"""实体详情路径参数 `node_id` 的长度上限（超长 → 1002）。本项目最长的节点标识形如
`PER-0001`／`EVT-0236`／`HCONF-…`，128 足够宽裕，只用于挡住异常长的输入。"""

PROP_SKIP = frozenset({"node_id", "label", "name", "stock_code"})
"""`properties` 里不再重复这四个顶层字段（表 4-13 把它们单列在 `items` 上）。"""

NULL_TIME_POLICY = str(gs.RETRIEVAL_CONFIG.RETRIEVAL.get("time_filter_null_policy", "exclude"))
"""`event_time` 空值策略：与检索侧 config 的 `RETRIEVAL.time_filter_null_policy` 同源（当前 `exclude`）。"""


# --------------------------------------------------------------------------
# 2. 通用小工具
# --------------------------------------------------------------------------
def _s(value) -> str:
    """统一成字符串（None → ""），与 `graph_service._s` 同义。"""
    return "" if value is None else str(value)


def _norm(text) -> str:
    """归一：小写并删除全部空白（与 `graph_service._norm`／`graph_query._norm` 同一套规则）。"""
    return "".join(_s(text).lower().split())


def _as_int(value):
    """能转 int 就转，否则 None（图谱侧编号有的是字符串、有的是数字，两种都收）。"""
    if value is None or value == "":
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _iso(value) -> str:
    """datetime → ISO 字符串（`T` 分隔）；已经是字符串就原样返回。"""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    return _s(value)


def _parse_int(raw, name: str, default=None):
    """查询参数取整数；空串／缺失取默认值，非法值抛 `ApiError(1002)`。"""
    if raw is None or _s(raw).strip() == "":
        return default
    try:
        return int(_s(raw).strip())
    except (TypeError, ValueError):
        raise errors.ApiError(1002, detail="%s 不是整数：%r" % (name, raw))


def _page_args(page, page_size) -> tuple:
    """分页参数统一校验（`page ≥ 1`、`1 ≤ page_size ≤ PAGE_SIZE_MAX`），非法 → 1002。"""
    page_no = _parse_int(page, "page", default=1)
    if page_no is None or page_no < 1:
        raise errors.ApiError(1002, detail="page 必须是不小于 1 的整数：%r" % page)
    size = _parse_int(page_size, "page_size", default=DEFAULT_PAGE_SIZE)
    if size is None or size < 1 or size > PAGE_SIZE_MAX:
        raise errors.ApiError(1002, detail="page_size 必须是 1～%d 的整数：%r"
                              % (PAGE_SIZE_MAX, page_size))
    return page_no, size


def _truthy(raw) -> bool:
    """布尔开关：`1`／`true`／`yes`／`on`（大小写不敏感）为真，其余（含缺省）为假。

    用于 `with_evidence`／`with_properties`（第 9 阶段新增的**可选**开关）：缺省与任何
    非真值都按「关」处理，以保证「不带参数时响应逐字节与旧版一致」这条硬约束不受参数杂音影响。
    """
    return _s(raw).strip().lower() in ("1", "true", "yes", "on")


def _node_id_arg(node_id) -> str:
    """实体详情路径参数 `node_id` 的校验：去首尾空白后**非空且不超长**，否则 1002。

    （`node_id` 取不存在的取值时不算「格式错误」，那是 2001；这里只挡空串与异常长串。）
    """
    nid = _s(node_id).strip()
    if not nid:
        raise errors.ApiError(1002, detail="node_id 为空")
    if len(nid) > MAX_NODE_ID_LEN:
        raise errors.ApiError(1002, detail="node_id 超长（%d > %d）：%r…"
                              % (len(nid), MAX_NODE_ID_LEN, nid[:32]))
    return nid


def _properties_of(raw: dict) -> dict:
    """从节点的**原始属性字典**里取**真实属性**（原样取值，不改名、不补造、不派生）。

    只做两件**减法的、不改值**的事：
    * 去掉 `PROP_SKIP` 的四个顶层字段（`node_id`／`label`／`name`／`stock_code`）——
      它们已单列在 `node` brief 上；这与 `/api/graph/entities` 的 `entity_item` **同一口径**；
    * **空串／None 的属性如实省略**（由 `property_notes` 逐条说明），不填占位、不补默认值。
    """
    return {k: v for k, v in (raw or {}).items()
            if k not in PROP_SKIP and v not in (None, "")}


def _properties_ordered(raw: dict) -> dict:
    """真实属性字典，按**键升序**重建（供实体详情与 `with_properties` 开关使用）。

    排序有两个理由：① 前端可**按固定顺序**渲染；② **Neo4j 不保证** `properties(n)` 的键
    迭代顺序稳定，直接回传原始顺序会让同一节点的键序在多次请求间漂移。
    （`/api/graph/entities` 列表接口的 `properties` 为保持向后兼容**沿用图谱原始顺序**，
    不在此处改动——见 `entity_item`。）
    """
    props = _properties_of(raw)
    return {k: props[k] for k in sorted(props)}


def _property_notes(raw: dict, props: dict) -> list:
    """对**图谱中确实存在该属性、但取值为空／缺失**的情形逐条如实说明（不隐藏、不补造）。

    实测：本图谱在导入时**已丢弃空属性**，故稳健节点（七类标签）的 `property_notes` 通常为空；
    一旦某个节点确有某属性列而值为空串／缺失，这里会补一条 `{key, note}`；当整个节点没有任何
    可展示属性时，再补一条总说明。**注意**：Neo4j 后端下「值为空串」与「属性缺失」不可区分
    （导入即丢弃），故二者共用同一句说明。
    """
    notes = []
    for key in sorted(k for k in (raw or {}) if k not in PROP_SKIP):
        if key in props:
            continue
        notes.append({"key": key, "value": None,
                      "note": "本节点无该属性（图谱中为缺失或空串，已省略）"})
    if not props:
        notes.append({"key": None, "value": None,
                      "note": "本节点在图谱中没有任何可展示的真实属性"})
    return notes


def _check_type(label) -> str | None:
    """`type` 必须是六个实体标签之一（空表示不限），否则 1002。"""
    if label is None or _s(label).strip() == "":
        return None
    text = _s(label).strip()
    if text not in ENTITY_LABELS:
        raise errors.ApiError(1002, detail="type=%r 不在 %s 之内"
                              % (label, "、".join(ENTITY_LABELS)))
    return text


def _check_relation(relation, required: bool = False) -> str | None:
    """`relation` 必须是 9 条核心关系之一（空表示不限），否则 1002。"""
    if relation is None or _s(relation).strip() == "":
        if required:
            raise errors.ApiError(1002, detail="缺少 relation（本模式必须给出）")
        return None
    text = _s(relation).strip()
    if text not in RELATIONS:
        raise errors.ApiError(1002, detail="relation=%r 不在 9 条核心关系之内（%s）"
                              % (relation, "、".join(RELATIONS)))
    return text


def _check_event_type(event_type) -> str | None:
    """`event_type` 必须是 8 类之一（空表示不限），否则 1002。"""
    if event_type is None or _s(event_type).strip() == "":
        return None
    text = _s(event_type).strip()
    if text not in EVENT_TYPES:
        raise errors.ApiError(1002, detail="event_type=%r 不在 8 类之内（%s）"
                              % (event_type, "、".join(EVENT_TYPES)))
    return text


def _check_direction(direction) -> str | None:
    """`direction` 只接受 `out`／`in`（空表示不限），否则 1002。"""
    if direction is None or _s(direction).strip() == "":
        return None
    text = _s(direction).strip().lower()
    if text not in ("out", "in"):
        raise errors.ApiError(1002, detail="direction=%r 只能是 out 或 in" % direction)
    return text


def _time_bound(raw, name: str, end: bool = False) -> str:
    """把时间参数归一成 `YYYY-MM-DDTHH:MM:SS`；空返回 ""，非法抛 `ApiError(1002)`。

    `end=True` 时，只给到「日」的取值补成当日 `23:59:59`（闭区间语义），
    只给到「分钟」的补 `:00`。这样 `start_time=2025-01-01` 与
    `event_time="2025-01-01"` 之间的比较就能按**定长字符串**逐位比，不必依赖解析。
    """
    if raw is None or _s(raw).strip() == "":
        return ""
    text = _s(raw).strip().replace(" ", "T")
    if text.endswith("Z"):
        text = text[:-1]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise errors.ApiError(1002, detail="%s 不是合法时间（%r）：应为 ISO 8601" % (name, raw))
    if len(text) <= 10:                      # 只给到「日」
        if end:
            parsed = parsed.replace(hour=23, minute=59, second=59)
    elif len(text) <= 16:                    # 只给到「分钟」
        parsed = parsed.replace(second=0)
    return parsed.replace(tzinfo=None).isoformat(timespec="seconds")


def _norm_event_time(value) -> str:
    """把 `event_time` 归一成同一种定长形式（解析不了就原样返回，供排序兜底）。"""
    text = _s(value).strip().replace(" ", "T")
    if not text:
        return ""
    if text.endswith("Z"):
        text = text[:-1]
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None).isoformat(timespec="seconds")
    except ValueError:
        return text


# --------------------------------------------------------------------------
# 3. 图谱后端的打开／关闭（不可用 → 3001，绝不降级）
# --------------------------------------------------------------------------
@contextmanager
def graph_access():
    """打开一个图谱查询后端；用完即关。**打不开一律 `ApiError(3001)`**。

    `graph_service.open_backend()` 在 Neo4j 连不上时抛的是 `SystemExit`（不是 `Exception`），
    故这里显式捕两类：`SystemExit` 与其余异常都收敛成 3001——否则 `SystemExit` 会穿过
    FastAPI 的 `except Exception` 处理器（`BaseException` 不被它接住）而掀翻工作进程。
    """
    graph = None
    try:
        graph, backend = gs.open_backend()
    except SystemExit as exc:
        logger.warning("图谱后端不可用（SystemExit）：%s", _s(exc).splitlines()[:1])
        raise errors.ApiError(3001, detail="图谱后端不可用：%s" % _s(exc).splitlines()[0])
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("图谱后端打开失败：%s", exc)
        raise errors.ApiError(3001, detail="图谱后端打开失败：%s: %s"
                              % (type(exc).__name__, exc))
    try:
        yield graph, backend
    finally:
        try:
            gs.close_backend(graph)
        except Exception:                                      # noqa: BLE001
            logger.warning("关闭图谱后端时出错（已忽略）", exc_info=True)


# --------------------------------------------------------------------------
# 4. GraphReader —— 表 4-13 里图谱侧未覆盖的三件事（实体检索／定关系多跳／全量事件）
# --------------------------------------------------------------------------
def _norm_contains_expr(var: str) -> str:
    """与 `_norm()` 等价的 Cypher 表达式（复用 `graph_service._norm_expr` 的同一实现）。"""
    return gs._norm_expr(var)                                  # noqa: SLF001（同包内复用）


class GraphReader:
    """按后端分派的三件补充查询；对端（G1／G3／G4／G5／G6／G7）直接调后端自身的方法。

    两个后端（`neo4j` 默认／`memory` 第 7 阶段内存版）在 `graph_service` 里是**同形**的：
    `g1_one_hop`／`g3_events_by_type`／`g4_company_events`／`g5_event_evidence`／
    `g6_time_filter`／`g7_paths`／`resolve_node` 六个方法两端都有，故本类只实现两端不一致的部分。
    """

    def __init__(self, graph, backend: str):
        self.graph = graph
        self.backend = backend

    # ------------------------------------------------------------ 基础取数
    def _run(self, cypher: str, **params) -> list:
        """Neo4j 后端执行一段 Cypher（异常 → 3001）。"""
        try:
            return self.graph._run(cypher, **params)           # noqa: SLF001
        except errors.ApiError:
            raise
        except Exception as exc:                               # noqa: BLE001
            logger.exception("图谱查询失败：%s", exc)
            raise errors.ApiError(3001, detail="图谱查询失败：%s: %s"
                                  % (type(exc).__name__, exc))

    def _raw_node(self, node_id: str) -> dict | None:
        """节点的**原始属性字典**（附 `label`）；不存在返回 None。

        注意：Neo4j 侧 `label` 是**节点标签**（`labels(n)[0]`）而不是属性——`nodes.csv`
        的 `label` 列由导入脚本落成节点标签，故这里显式把它并回属性字典，使两个后端的
        `_raw_node()` 同形。
        """
        nid = _s(node_id)
        if self.backend == "neo4j":
            rows = self._run("MATCH (n {node_id:$id}) RETURN labels(n)[0] AS label, "
                             "properties(n) AS p", id=nid)
            if not rows:
                return None
            props = dict(rows[0]["p"] or {})
            props["label"] = _s(rows[0]["label"])
            return props
        node = (self.graph.nodes or {}).get(nid)
        return dict(node) if node else None

    def label_of(self, node_id: str) -> str | None:
        node = self._raw_node(node_id)
        return _s(node.get("label")) or None if node else None

    def brief(self, node_id: str) -> dict:
        """节点简述 `{node_id, label, name, stock_code}`（与两个后端的 `_node_brief` 同形）。"""
        node = self._raw_node(node_id) or {}
        return {"node_id": _s(node_id), "label": _s(node.get("label")),
                "name": _s(node.get("name")), "stock_code": _s(node.get("stock_code"))}

    @staticmethod
    def entity_item(label: str, props: dict) -> dict:
        """`/api/graph/entities` 的条目：`node_id`／`label`／`name`／`stock_code`／`properties`。

        `properties` 与实体详情接口**同一口径**（去掉 `PROP_SKIP` 四个顶层字段、省略空值），
        统一走 `_properties_of()`，避免两处各写一份而漂移。
        """
        return {"node_id": _s((props or {}).get("node_id")), "label": _s(label),
                "name": _s((props or {}).get("name")),
                "stock_code": _s((props or {}).get("stock_code")),
                "properties": _properties_of(props)}

    # --------------------------------------------------- ① 实体检索（keyword／type）
    def search(self, keyword: str, label: str | None) -> list:
        """按 `keyword`（名称／简称／别名／代码，归一后包含匹配）＋ `label` 取实体，返回
        `[(label, props), …]`（**未分页**；排序与分页由调用方统一做）。

        `keyword` 归一后为空表示不限（此时按 `label` 列举）。
        """
        kw = _norm(keyword)
        if self.backend == "neo4j":
            alias_expr = ("any(_a IN split(coalesce(n.aliases, ''), '|') "
                          "WHERE %s CONTAINS $kw)" % _norm_contains_expr("_a"))
            cypher = (
                "MATCH (n) WHERE ($label IS NULL OR $label IN labels(n)) "
                "AND ($kw = '' OR %s CONTAINS $kw OR %s CONTAINS $kw OR %s "
                "     OR coalesce(n.node_id, '') CONTAINS $kw "
                "     OR coalesce(n.stock_code, '') CONTAINS $kw) "
                "RETURN labels(n)[0] AS label, properties(n) AS props"
                % (_norm_contains_expr("n.name"), _norm_contains_expr("n.short_name"),
                   alias_expr))
            rows = self._run(cypher, kw=kw, label=label, ws=gs._NORM_WS)   # noqa: SLF001
            return [(_s(r["label"]), dict(r["props"] or {})) for r in rows]
        out = []
        for nid, node in (self.graph.nodes or {}).items():
            if label and _s(node.get("label")) != label:
                continue
            if kw and not any(kw in _norm(node.get(f))
                              for f in ("name", "short_name", "aliases", "node_id", "stock_code")):
                continue
            out.append((_s(node.get("label")), dict(node, node_id=nid)))
        return out

    @staticmethod
    def search_rank(item: dict, keyword: str) -> int:
        """命中优先级：0 精确（名称／代码／编号），1 前缀，2 其余包含——精确的排前面。"""
        kw = _norm(keyword)
        if not kw:
            return 2
        names = {_norm(item["name"]), _norm(item["node_id"]), _norm(item["stock_code"])}
        if kw in names:
            return 0
        if any(x.startswith(kw) for x in names if x):
            return 1
        return 2

    # ------------------------------------------- ② 定关系多跳（from_node ＋ relation）
    def relation_paths(self, node_id: str, relation: str, hop: int) -> list:
        """`node_id -[relation]-> …` 的 1／2 跳路径（返回与 `graph_service._paths` 同形的结构）。"""
        if self.backend == "neo4j":
            rel_map = gs._rel_map("r")                          # noqa: SLF001
            tail = ("MATCH p = (a {node_id:$id})-[r]-(b) "
                    "WHERE type(r) = $rel "
                    "RETURN [n IN nodes(p) | n.node_id] AS node_ids, "
                    "[r IN relationships(p) | %s] AS rels" % rel_map)
            if hop == 2:
                tail = ("MATCH p = (a {node_id:$id})-[r]-(b)-[r2]-(c) "
                        "WHERE type(r) = $rel AND c.node_id <> a.node_id "
                        "RETURN [n IN nodes(p) | n.node_id] AS node_ids, "
                        "[r IN relationships(p) | %s] AS rels" % rel_map)
            return self.graph._paths(tail, id=_s(node_id), rel=relation)   # noqa: SLF001
        return self._memory_relation_paths(_s(node_id), relation, hop)

    def _memory_relation_paths(self, node_id: str, relation: str, hop: int) -> list:
        """内存后端的定关系多跳：直接走 `adj`／`edges` 两张表（与 neo4j 分支同语义）。"""
        def step(src: str, only_relation: str | None):
            out = []
            for rec in self.graph.adj.get(src, []):
                edge = self.graph.edges[rec["edge_id"]]
                if only_relation and edge["relation"] != only_relation:
                    continue
                out.append((rec, edge))
            return out

        paths = []
        for rec1, _edge1 in step(node_id, relation):
            if hop == 1:
                paths.append(self._memory_path([node_id, rec1["neighbor"]], [rec1["edge_id"]]))
                continue
            mid = rec1["neighbor"]
            for rec2, _edge2 in step(mid, None):
                if rec2["neighbor"] == node_id:            # 不走回起点（与 Cypher 分支同口径）
                    continue
                paths.append(self._memory_path([node_id, mid, rec2["neighbor"]],
                                               [rec1["edge_id"], rec2["edge_id"]]))
        return paths

    def _memory_path(self, node_ids: list, edge_ids: list) -> dict:
        """把节点／边序列还原成与 `graph_service._paths` 同形的路径项。"""
        relations = []
        for pos, edge_id in enumerate(edge_ids):
            edge = self.graph.edges[edge_id]
            direction = "out" if edge["head"] == node_ids[pos] else "in"
            relations.append({"edge_id": edge_id, "relation": edge["relation"],
                              "direction": direction, "neighbor": node_ids[pos + 1],
                              "role": _s(edge.get("role")),
                              "evidence": (dict(edge["evidence"]) if edge.get("evidence") else None)})
        return {"depth": len(node_ids) - 1, "start": node_ids[0], "end": node_ids[-1],
                "nodes": list(node_ids), "relations": relations}

    # ------------------------------------------------------ ③ 全量事件列举
    def all_events(self) -> list:
        """全部 Event 节点的六项核心属性视图（与 `g3_events_by_type` 的条目同形）。"""
        if self.backend == "neo4j":
            return [r["ev"] for r in self._run(
                "MATCH (e:Event) RETURN %s AS ev" % gs._event_view("e"))]   # noqa: SLF001
        return [self.graph._event_view(nid) for nid in self.graph.events]    # noqa: SLF001

    # ------------------------------------------------------ ④ 计数（一致性检查用）
    def counts(self) -> dict:
        """节点／关系的总数与按标签／按关系类型的分布。"""
        if self.backend == "neo4j":
            nodes = self._run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS c")
            edges = self._run("MATCH ()-[r]->() RETURN type(r) AS relation, count(*) AS c")
            return {
                "nodes_total": sum(int(r["c"]) for r in nodes),
                "nodes_by_label": {_s(r["label"]): int(r["c"]) for r in nodes},
                "edges_total": sum(int(r["c"]) for r in edges),
                "edges_by_relation": {_s(r["relation"]): int(r["c"]) for r in edges},
            }
        nodes, edges = self.graph.nodes or {}, self.graph.edges or {}
        by_label, by_relation = {}, {}
        for node in nodes.values():
            key = _s(node.get("label"))
            by_label[key] = by_label.get(key, 0) + 1
        for edge in edges:
            key = _s(edge.get("relation"))
            by_relation[key] = by_relation.get(key, 0) + 1
        return {"nodes_total": len(nodes), "nodes_by_label": by_label,
                "edges_total": len(edges), "edges_by_relation": by_relation}

    # ------------------------------------------- ⑤ 每个事件的证据文档数（后台抽取查询用）
    def evidence_doc_counts(self, event_ids: list) -> dict:
        """`{event_id: 证据文档数}`：语义边上的 `source_doc_id` 与 `EVIDENCED_BY` 指向的
        Document 节点，两者取并集后去重计数。"""
        ids = [_s(x) for x in event_ids]
        if not ids:
            return {}
        if self.backend == "neo4j":
            rows = self._run(
                "MATCH (e:Event) WHERE e.node_id IN $ids "
                "OPTIONAL MATCH (e)-[r]-(x) "
                "RETURN e.node_id AS id, "
                "       collect(DISTINCT r.source_doc_id) AS sds, "
                "       collect(DISTINCT CASE WHEN type(r) = 'EVIDENCED_BY' THEN x.node_id END) AS docs",
                ids=ids)
            out = {}
            for row in rows:
                docs = {_s(x) for x in (row["docs"] or []) if x not in (None, "")}
                docs |= {_s(x) for x in (row["sds"] or []) if x not in (None, "")}
                out[_s(row["id"])] = len(docs)
            return out
        out = {}
        for eid in ids:
            docs = set()
            for rec in self.graph.adj.get(eid, []):
                edge = self.graph.edges[rec["edge_id"]]
                if edge.get("relation") == EVIDENCED_BY:
                    docs.add(_s(rec["neighbor"]))
                elif edge.get("evidence", {}).get("source_doc_id") not in (None, ""):
                    docs.add(_s(edge["evidence"]["source_doc_id"]))
            out[eid] = len(docs)
        return out


@contextmanager
def reader():
    """`graph_access()` ＋ `GraphReader` 的组合（接口层统一入口）。"""
    with graph_access() as (graph, backend):
        yield GraphReader(graph, backend)


# --------------------------------------------------------------------------
# 5. 响应整形：关系项与路径项
# --------------------------------------------------------------------------
# 5.0 实体级证据：文档元数据的**批量**补全（第 9 阶段新增）
# --------------------------------------------------------------------------
# 设计要点（对应任务书「作者意见：每个实体展示的证据不够充足」）：
#   * 一次调用拿全实体的证据——N 条边只发 2 条 SQL（`document` 一条 IN、`document_chunk`
#     一条 IN），**不逐条查**，从根上消掉前端拼证据时的 N+1；
#   * 文档元数据只从 MySQL 六表取（`document`／`document_chunk`），图谱侧只出边与证据属性；
#   * **空值如实**：`document` 里没有对应行时条目仍在、字段为 `null` 且标 `missing=true`，
#     不丢条目、不编内容。
def _fetch_doc_meta(doc_ids) -> dict:
    """按 `doc_id` 批量取文档元数据（**一条 `IN (...)`**）：`{doc_id: {title, source, …}}`。

    没有对应行的 `doc_id` **不会**出现在返回值里——调用方据此标 `missing=true`。
    """
    ids = sorted({int(x) for x in doc_ids if x is not None})
    if not ids:
        return {}
    marks = ",".join(["%s"] * len(ids))
    out = {}
    for row in db.query(
            "SELECT doc_id, title, source, publish_time, url, category FROM document "
            "WHERE doc_id IN (%s)" % marks, tuple(ids)):
        out[_as_int(row["doc_id"])] = {
            "title": _s(row["title"]), "source": _s(row["source"]),
            "publish_time": _iso(row["publish_time"]), "url": row["url"],
            "category": _s(row["category"])}
    return out


def _fetch_chunk_meta(chunk_ids) -> dict:
    """按 `chunk_id` 批量取块序号（**一条 `IN (...)`**）：`{chunk_id: chunk_index}`。"""
    ids = sorted({int(x) for x in chunk_ids if x is not None})
    if not ids:
        return {}
    marks = ",".join(["%s"] * len(ids))
    return {_as_int(row["chunk_id"]): _as_int(row["chunk_index"])
            for row in db.query(
                "SELECT chunk_id, chunk_index FROM document_chunk "
                "WHERE chunk_id IN (%s)" % marks, tuple(ids))}


def _evidence_index(raw_items: list) -> tuple:
    """给一批关系项做**一次性**元数据补全，返回 `(doc_meta, chunk_meta)` 两个字典。

    只收集**带证据属性的边**（`evidence` 非空）的 `source_doc_id`／`source_chunk_id`；
    `EVIDENCED_BY` 这类不带证据属性的边不参与（它们走 `relations_without_evidence`／`note`）。
    """
    doc_ids, chunk_ids = set(), set()
    for item in raw_items:
        evidence = item.get("evidence") or {}
        d = _as_int(evidence.get("source_doc_id"))
        c = _as_int(evidence.get("source_chunk_id"))
        if d is not None:
            doc_ids.add(d)
        if c is not None:
            chunk_ids.add(c)
    return _fetch_doc_meta(doc_ids), _fetch_chunk_meta(chunk_ids)


def _evidence_obj(evidence: dict, doc_meta: dict, chunk_meta: dict) -> dict:
    """把一条边上的证据两项（`source_doc_id`／`source_chunk_id`）＋ 批量元数据，
    整形成 `{doc_id, chunk_id, title, source, publish_time, url, chunk_index, missing}`。

    `missing=true` 表示 `document` 表里没有该 `doc_id` 的行（此时 `title` 等为 `null`）。
    """
    doc_id = _as_int((evidence or {}).get("source_doc_id"))
    chunk_id = _as_int((evidence or {}).get("source_chunk_id"))
    meta = doc_meta.get(doc_id)
    return {"doc_id": doc_id, "chunk_id": chunk_id,
            "title": (meta or {}).get("title"),
            "source": (meta or {}).get("source"),
            "publish_time": (meta or {}).get("publish_time"),
            "url": (meta or {}).get("url"),
            "chunk_index": chunk_meta.get(chunk_id),
            "missing": meta is None}


NO_EVIDENCE_NOTE = "该关系类型不带证据属性"
"""不带证据属性的边（如 `EVIDENCED_BY`）在证据视图里的如实说明。"""


def _attach_edge_evidence(edge: dict, item: dict, doc_meta: dict, chunk_meta: dict) -> None:
    """**就地**给一条已整形的边**追加**证据对象（只在 `with_evidence=1` 时调用）。

    带证据属性 → 追加 `evidence`；不带（如 `EVIDENCED_BY`）→ `evidence: null` ＋ `note`。
    **不改动边已有的任何键**（`_relation_item` 的产物原样保留）。
    """
    evidence = item.get("evidence")
    if evidence:
        edge["evidence"] = _evidence_obj(evidence, doc_meta, chunk_meta)
    else:
        edge["evidence"] = None
        edge["note"] = NO_EVIDENCE_NOTE


def _relation_item(item: dict, neighbor_label: str) -> dict:
    """一条关系项：证据三项（`EVIDENCED_BY` 换成 `evidence_doc_id`）＋ 角色与对端。

    《10》第 4.7.3 节：**除 `EVIDENCED_BY` 外**返回 `source_doc_id`／`source_chunk_id`／
    `confidence`；路径上出现 `EVIDENCED_BY` 时其证据是所指向的 Document 节点，返回
    `evidence_doc_id` 而不返回上述三项。
    """
    relation = _s(item.get("relation"))
    row = {"relation": relation, "direction": _s(item.get("direction")),
           "neighbor": _s(item.get("neighbor")), "role": _s(item.get("role"))}
    evidence = item.get("evidence")
    if relation == EVIDENCED_BY:
        row["evidence_doc_id"] = _s(item.get("neighbor"))
        row["source_doc_id"] = None
        row["source_chunk_id"] = None
        row["confidence"] = None
    else:
        row["source_doc_id"] = _num((evidence or {}).get("source_doc_id"))
        row["source_chunk_id"] = _num((evidence or {}).get("source_chunk_id"))
        row["confidence"] = _float((evidence or {}).get("confidence"))
        row["evidence_doc_id"] = None
    row["neighbor_label"] = neighbor_label
    return row


def _num(value):
    """编号归一：全数字字符串转 int（图谱侧存的是字符串，MySQL／设计示例里是整数）。"""
    if value is None or value == "":
        return None
    text = _s(value).strip()
    return int(text) if text.isdigit() else value


def _float(value):
    """置信度归一：可解析的转 float，其余原样（图谱侧存的是字符串）。"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return value


def _edge_id(item: dict):
    return item.get("edge_id")


def _path_payload(reader_obj: GraphReader, path: dict, with_evidence: bool = False,
                  doc_meta: dict | None = None, chunk_meta: dict | None = None) -> dict:
    """把内部路径项整形为表 4-13／《10》4.7.3 的 `paths[i]`：

    `{start, end, depth, nodes:[{node_id,label,name}], edges:[…证据属性…]}`。

    `with_evidence=True` 时每条边**追加**一个 `evidence` 对象（元数据由调用方**批量**查库后
    经 `doc_meta`／`chunk_meta` 传入）；默认 False 时产物与既有版本逐字节一致。
    """
    node_ids = list(path.get("nodes") or [])
    briefs = [reader_obj.brief(nid) for nid in node_ids]
    edges = []
    for rel in path.get("relations") or []:
        neighbor = _s(rel.get("neighbor"))
        label = next((b["label"] for b in briefs if b["node_id"] == neighbor), "")
        edge = _relation_item(rel, label)
        if with_evidence:
            _attach_edge_evidence(edge, rel, doc_meta or {}, chunk_meta or {})
        edges.append(edge)
    return {"start": _s(path.get("start")), "end": _s(path.get("end")),
            "depth": int(path.get("depth") or 0), "nodes": briefs, "edges": edges,
            "node_ids": node_ids}


def _sort_paths(paths: list) -> list:
    """路径排序：深度 → 节点编号序列 → 关系名序列（与第 7 阶段 `GraphQuery._sort_paths` 同键）。

    整形后的 `nodes` 是节点简述（dict），不能直接参与比较，故按 `node_ids` 排序。
    """
    return sorted(paths, key=lambda p: (p.get("depth", 0),
                                        list(p.get("node_ids") or []),
                                        [_s(e.get("relation")) for e in (p.get("edges") or [])]))


def _dedup_paths(raw_paths: list) -> list:
    """按（节点序列 ＋ 边编号序列）去重，避免同一路径被多条起步边重复产出。"""
    seen, out = set(), []
    for path in raw_paths:
        key = (tuple(path.get("nodes") or []),
               tuple(_s(r.get("edge_id")) for r in (path.get("relations") or [])))
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


# --------------------------------------------------------------------------
# 6. 接口一：GET /api/graph/entities
# --------------------------------------------------------------------------
@router.get("/entities")
async def list_entities(keyword: str | None = None, type: str | None = None,   # noqa: A002
                        page: str | None = None, page_size: str | None = None):
    """按名称或代码查实体；`type` 限定六个实体标签之一；空结果 → HTTP 200 空列表。"""
    label = _check_type(type)
    page_no, size = _page_args(page, page_size)
    with reader() as rd:
        rows = rd.search(_s(keyword), label)
    items = [GraphReader.entity_item(lab, props) for lab, props in rows]
    items.sort(key=lambda it: (GraphReader.search_rank(it, _s(keyword)), it["label"], it["node_id"]))
    total = len(items)
    start = (page_no - 1) * size
    return errors.ok_page(total, items[start:start + size], page_no, size)


# --------------------------------------------------------------------------
# 7. 接口二：GET /api/graph/entities/{node_id}/neighbors
# --------------------------------------------------------------------------
@router.get("/entities/{node_id}/neighbors")
async def neighbors(node_id: str, relation: str | None = None, direction: str | None = None,
                    with_evidence: str | None = None, with_properties: str | None = None):
    """一跳邻居（走 `graph_service` 的 G1）；节点不存在 → 2001；无边 → HTTP 200 空结果。

    **可选开关 `with_evidence=1`**（第 9 阶段新增）：打开时每条边**追加**一个 `evidence`
    对象（`doc_id`／`chunk_id`／`title`／`source`／`publish_time`／`url`／`chunk_index`／
    `missing`，元数据经**一次 `IN (...)`** 批量查库）；不带证据属性的边给 `evidence: null`
    ＋ `note`。**默认关闭时响应逐字节与既有版本一致**（不加任何字段）。

    **可选开关 `with_properties=1`**（第 9 阶段新增）：打开时给中心节点的 `node` brief
    **追加** `properties`（与实体详情接口同口径的真实属性字典）；默认关闭时不加该键。
    """
    rel_filter = _check_relation(relation)
    dir_filter = _check_direction(direction)
    with_ev = _truthy(with_evidence)
    with_props = _truthy(with_properties)
    with reader() as rd:
        env = rd.graph.g1_one_hop(node_id)
        code = _s(env.get("code"))
        if code == gs.RC_NOT_FOUND:
            raise errors.ApiError(2001, detail="节点标识未匹配到任何实体：%s" % node_id)
        if code == gs.RC_INVALID_INPUT:
            raise errors.ApiError(1002, detail="节点标识非法：%s" % node_id)
        raw = _dedup_edges(env.get("results") or [])
        edges, node_index, pairs = [], {}, []
        for item in raw:
            if rel_filter and _s(item.get("relation")) != rel_filter:
                continue
            if dir_filter and _s(item.get("direction")) != dir_filter:
                continue
            neighbor = _s(item.get("neighbor"))
            brief = _brief_of(rd, item, neighbor)
            node_index[neighbor] = brief
            edge = _relation_item(item, brief["label"])
            edges.append(edge)
            pairs.append((edge, item))
        if with_ev:
            doc_meta, chunk_meta = _evidence_index([it for _, it in pairs])
            for edge, item in pairs:
                _attach_edge_evidence(edge, item, doc_meta, chunk_meta)
        nodes = [node_index[nid] for nid in sorted(node_index,
                                                  key=lambda x: (node_index[x]["label"], x))]
        edges.sort(key=lambda e: (e["relation"], e["direction"], e["neighbor"]))
        center = rd.brief(node_id)                    # 后端已关，必须在 with 内取
        if with_props:                                # 追加字段；关时不出现该键
            center["properties"] = _properties_ordered(rd._raw_node(node_id) or {})
    return errors.ok({"node": center, "nodes": nodes, "edges": edges,
                      "total": len(edges)})


def _dedup_edges(results: list) -> list:
    """同一 `edge_id` 只保留一条（G1 在两个后端上都可能对同一节点返回重复起步边）。"""
    seen, out = set(), []
    for item in results:
        key = _edge_id(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _brief_of(rd: GraphReader, item: dict, node_id: str) -> dict:
    """关系项的对端节点简述：优先用后端已经给出的 `neighbor_node`／`counterpart`。"""
    for key in ("neighbor_node", "counterpart"):
        if isinstance(item.get(key), dict):
            return item[key]
    return rd.brief(node_id)


# --------------------------------------------------------------------------
# 7.5 接口二之补：GET /api/graph/entities/{node_id}/evidence（第 9 阶段新增）
# --------------------------------------------------------------------------
def _entity_edges(rd: GraphReader, node_id: str, depth: int) -> list:
    """一个实体在 `depth` 跳内的**去重边**集合（走既有图谱查询层，不另写 Cypher）。

    * `depth=1` → G1（`g1_one_hop`）的边；
    * `depth=2` → G2（`g2_two_hop`）各路径上的边（G2 已含 1 跳，故是 1 跳的超集）。

    节点不存在 → 2001；节点标识非法 → 1002。返回边项（含 `evidence` 属性）的列表。
    """
    env = rd.graph.g2_two_hop(node_id) if depth == 2 else rd.graph.g1_one_hop(node_id)
    code = _s(env.get("code"))
    if code == gs.RC_NOT_FOUND:
        raise errors.ApiError(2001, detail="节点标识未匹配到任何实体：%s" % node_id)
    if code == gs.RC_INVALID_INPUT:
        raise errors.ApiError(1002, detail="节点标识非法：%s" % node_id)
    if depth == 2:
        raw = []
        for path in env.get("results") or []:
            raw += list(path.get("relations") or [])
    else:
        raw = env.get("results") or []
    return _dedup_edges(raw)                         # 按 edge_id 去重（两处同口径）


def _evidence_documents(edges: list) -> tuple:
    """把边集归并成**按文档去重**的证据列表 ＋ 不带证据属性的边清单。

    返回 `(documents, relations_without_evidence, chunk_total)`：
    * `documents`：`{doc_id, title, source, publish_time, url, category, support_relations,
      missing, chunks:[{chunk_id, chunk_index, relations:[{relation, neighbor, role,
      confidence}]}]}`——元数据来自**一次 `IN (...)`** 的 `document`／`document_chunk`；
      查无此文档的行仍出现并标 `missing=true`（字段为 `null`）；
    * `relations_without_evidence`：`EVIDENCED_BY` 这类**不带证据属性**的边，
      每项 `{relation, neighbor, note}`——**如实列出，不隐藏、不补造**；
    * `chunk_total`：去重后的块总数（分页前）。
    """
    raw_docs, chunk_ids = {}, set()
    without = []
    for item in edges:
        evidence = item.get("evidence")
        doc_id = _as_int((evidence or {}).get("source_doc_id")) if evidence else None
        if doc_id is None:                           # 不带证据属性（如 EVIDENCED_BY）
            without.append({"relation": _s(item.get("relation")),
                            "neighbor": _s(item.get("neighbor")),
                            "note": NO_EVIDENCE_NOTE})
            continue
        chunk_id = _as_int((evidence or {}).get("source_chunk_id"))
        row = raw_docs.setdefault(doc_id, {"doc_id": doc_id, "support_relations": 0,
                                           "chunks": {}})
        row["support_relations"] += 1
        if chunk_id is not None:
            chunk_ids.add(chunk_id)
            chunk = row["chunks"].setdefault(chunk_id, {"chunk_id": chunk_id, "relations": []})
            chunk["relations"].append({
                "relation": _s(item.get("relation")), "neighbor": _s(item.get("neighbor")),
                "role": _s(item.get("role")),
                "confidence": _float((evidence or {}).get("confidence"))})

    doc_meta = _fetch_doc_meta(list(raw_docs))       # 一条 IN
    chunk_meta = _fetch_chunk_meta(list(chunk_ids))  # 一条 IN

    documents = []
    for doc_id, row in raw_docs.items():
        meta = doc_meta.get(doc_id)
        chunks = []
        for chunk_id, chunk in row["chunks"].items():
            chunk["chunk_index"] = chunk_meta.get(chunk_id)
            chunk["relations"].sort(
                key=lambda r: (r["relation"], r["neighbor"], r["role"]))
            chunks.append(chunk)
        chunks.sort(key=lambda c: (c["chunk_index"] is None, c["chunk_index"] or 0,
                                   c["chunk_id"]))
        documents.append({
            "doc_id": doc_id,
            "title": (meta or {}).get("title"),
            "source": (meta or {}).get("source"),
            "publish_time": (meta or {}).get("publish_time"),
            "url": (meta or {}).get("url"),
            "category": (meta or {}).get("category"),
            "support_relations": row["support_relations"],
            "missing": meta is None,
            "chunks": chunks})
    # 排序：发布时间倒序（最新在前），缺发布时间的排在最后；同键按 doc_id 升序（两趟稳定排序）
    documents.sort(key=lambda d: d["doc_id"])
    documents.sort(key=lambda d: _s(d.get("publish_time")), reverse=True)
    chunk_total = sum(len(d["chunks"]) for d in documents)
    return documents, without, chunk_total


@router.get("/entities/{node_id}/evidence")
async def entity_evidence(node_id: str, depth: str | None = None,
                          page: str | None = None, page_size: str | None = None,
                          with_properties: str | None = None):
    """**一次调用拿全实体的证据**（第 9 阶段新增，表 4-13 之外的新增接口）。

    * `depth`：`1`（默认）走 G1 一跳边，`2` 走 G2 两跳边；其余 → 1002；
    * `page`／`page_size`：对 `documents[]` 分页（`1 ≤ page_size ≤ 200`）；
    * 节点不存在 → 2001；无证据 → HTTP 200 ＋ 空列表（**2002 的语义，用空数据表达**）；
    * **可选开关 `with_properties=1`**：打开时给 `node` brief **追加** `properties`
      （与实体详情接口同口径的真实属性字典）；默认关闭时不加该键，响应逐字段与旧版一致；
    * 返回键：`node`／`counts`／`documents`／`documents_total`／`chunks_total`／
      `relations_without_evidence`／`depth`／`params`／`scope`／`source`。
    """
    depth_no = _parse_int(depth, "depth", default=1)
    if depth_no not in (1, 2):
        raise errors.ApiError(1002, detail="depth 只能是 1 或 2：%r" % depth)
    page_no, size = _page_args(page, page_size)
    with_props = _truthy(with_properties)

    with reader() as rd:
        brief = rd.brief(node_id)
        if with_props:                                        # 追加字段；关时不出现该键
            brief["properties"] = _properties_ordered(rd._raw_node(node_id) or {})
        edges = _entity_edges(rd, node_id, depth_no)          # 节点不存在时在此抛 2001
    documents, without, chunk_total = _evidence_documents(edges)

    neighbors = {_s(e.get("neighbor")) for e in edges}
    total_docs = len(documents)
    start = (page_no - 1) * size
    return errors.ok({
        "node": brief,
        "counts": {"neighbors": len(neighbors), "relations": len(edges),
                   "documents": total_docs, "chunks": chunk_total},
        "documents": documents[start:start + size],
        "documents_total": total_docs,
        "chunks_total": chunk_total,
        "relations_without_evidence": without,
        "depth": depth_no,
        "params": {"depth": depth_no, "page": page_no, "page_size": size},
        "scope": "entity_evidence",
        "source": "图谱查询层（services.graph_service 的 G1／G2，本地 Neo4j 实例）"
                  "＋ MySQL 六表（document／document_chunk 元数据，各一次 IN 批量查）"})


# --------------------------------------------------------------------------
# 7.6 接口二之补：GET /api/graph/entities/{node_id}（实体详情，第 9 阶段新增）
# --------------------------------------------------------------------------
def _degree(rd: GraphReader, node_id: str) -> dict:
    """节点的入／出／总度数：`out` ＝以本节点为**起点**的边数，`in_` ＝以本节点为**终点**的边数。

    * **Neo4j 后端**：一条 Cypher 用 `OPTIONAL MATCH (n)-[r]-()` 双向取边，
      再按 `startNode(r) = n`／`endNode(r) = n` 分别计数（`MATCH` 命中节点即可，无边时和为 0）；
    * **内存后端**：直接数 `adj[node_id]` 里 `direction` 为 `out`／`in` 的入射项（两个后端同口径）；
    * **自环**（起点＝终点的边）在两个后端上都**同时计一出一入**（口径一致）；
    * 节点不存在（Neo4j 侧查询无行）→ 三项如实为 `null`（本接口在调用前已先判过存在性，
      正常不会走到这里）。
    """
    if rd.backend == "neo4j":
        rows = rd._run(                                        # noqa: SLF001（同包内复用）
            "MATCH (n {node_id:$id}) OPTIONAL MATCH (n)-[r]-() "
            "RETURN sum(CASE WHEN startNode(r) = n THEN 1 ELSE 0 END) AS out_deg, "
            "       sum(CASE WHEN endNode(r) = n THEN 1 ELSE 0 END) AS in_deg",
            id=_s(node_id))
        if not rows:
            return {"out": None, "in_": None, "total": None}
        out = int(rows[0]["out_deg"] or 0)
        inn = int(rows[0]["in_deg"] or 0)
        return {"out": out, "in_": inn, "total": out + inn}
    out = inn = 0
    for rec in (rd.graph.adj or {}).get(_s(node_id), []):
        if _s(rec.get("direction")) == "out":
            out += 1
        else:
            inn += 1
    return {"out": out, "in_": inn, "total": out + inn}


@router.get("/entities/{node_id}")
async def entity_detail(node_id: str):
    """**实体详情**（第 9 阶段新增，表 4-13 之外的新增接口）：返回单个实体在图谱里的真实属性。

    作者反馈「选中画布节点时属性不显示」的数据侧根因是：图谱里本就有节点属性，但**没有取单个
    实体属性的接口**（既有五条只给 `node` brief：`node_id`／`label`／`name`／`stock_code`）。
    本接口补上这一条，`data` 含：

    * `node`：`{node_id, label, name, stock_code}`（沿用既有 brief 形状）；
    * `properties`：该节点在**图谱里的真实属性字典**（原样取值，**不改名、不补造、不派生**）——
      例如 Company 给 `aliases/company_name/exchange/short_name`，Event 给
      `confidence/description/event_id/event_name/event_time/event_type`；空值如实省略；
    * `property_keys`：属性键的**有序列表**（升序，便于前端按固定顺序渲染，与 `properties` 同序）；
    * `property_notes`：空值／缺失属性的如实说明（正常节点通常为空表）；
    * `degree`：`{out, in_, total}`（入／出／总度数，走既有图谱查询层；两个后端同口径。
      本项目两个后端都能取到入度与出度，故本接口**不出现** `null`——万一后端查不到该节点，
      三项如实为 `null` 而不假装成 0）；
    * `counts`：`{neighbors, relations, documents, chunks}`——**复用上批口径**
      （`_entity_edges` 取一跳边 ＋ `_evidence_documents` 归并文档／块，不另写一套）；
    * `source`：本响应字段的**来源归属**（图谱侧／MySQL 六表）；
    * `params`／`scope`（`scope`＝`entity_detail`）。

    错误码：节点不存在 → **2001**（HTTP 404）；`node_id` 为空／超长 → **1002**；其余按既有约定。
    """
    nid = _node_id_arg(node_id)
    with reader() as rd:
        raw = rd._raw_node(nid)                               # noqa: SLF001（同包内复用）
        if raw is None:
            raise errors.ApiError(2001, detail="节点标识未匹配到任何实体：%s" % nid)
        label = _s(raw.get("label"))
        node = {"node_id": nid, "label": label,
                "name": _s(raw.get("name")), "stock_code": _s(raw.get("stock_code"))}
        props = _properties_ordered(raw)                      # 已按升序
        keys = list(props)                                    # 有序键表（与 properties 同序）
        notes = _property_notes(raw, props)
        degree = _degree(rd, nid)
        edges = _entity_edges(rd, nid, 1)                     # 复用：一跳边（同批口径）
    documents, _without, chunk_total = _evidence_documents(edges)     # 复用：文档／块归并
    neighbors = {_s(e.get("neighbor")) for e in edges}
    return errors.ok({
        "node": node,
        "properties": props,                                  # 已按 `property_keys` 同序排列
        "property_keys": keys,
        "property_notes": notes,
        "degree": degree,
        "counts": {"neighbors": len(neighbors), "relations": len(edges),
                   "documents": len(documents), "chunks": chunk_total},
        "params": {"node_id": nid},
        "scope": "entity_detail",
        "source": {
            "graph": ["node", "properties", "property_keys", "property_notes", "degree",
                      "counts.neighbors", "counts.relations",
                      "counts.documents", "counts.chunks"],
            "mysql": [],
            "note": "本响应全部字段取自图谱后端（本地 Neo4j 实例；内存后端同形）的只读查询；"
                    "counts 由 G1 一跳边（_entity_edges）＋ _evidence_documents 归并得到——"
                    "后者会只读访问 document／document_chunk 两张表补文档元数据，"
                    "但本接口只回文档／块**计数**，不回传其元数据字段。",
        },
    })


# --------------------------------------------------------------------------
# 8. 接口三：GET /api/graph/paths
# --------------------------------------------------------------------------
@router.get("/paths")
async def paths(from_node: str | None = None, to_node: str | None = None,
                relation: str | None = None, hop: str | None = None,
                start_time: str | None = None, end_time: str | None = None,
                with_evidence: str | None = None):
    """多跳路径查询：`from_node` ＋（`to_node` 或 `relation`），`hop` 只接受 1／2。

    两条模式：
    * **定点模式**（给了 `to_node`）：走 G7（`from_node` 到 `to_node`、最长 `hop` 跳）；
      同时给了 `relation` 时按「路径上至少有一条该关系」再筛一道。
    * **定关系模式**（只给 `relation`）：`from_node` 沿该关系走 `hop` 跳。

    时间窗按 **`event_time`** 过滤：路径上**含 Event 节点**时，要求至少一个 Event 节点的
    `event_time` 落在闭区间内（`event_time` 为空的 Event 不满足，即按空值策略剔除）；
    路径上没有任何 Event 节点时视为与时间无关，原样保留。

    **可选开关 `with_evidence=1`**（第 9 阶段新增）：打开时每条边的 `edges[i]` **追加**一个
    `evidence` 对象（元数据经**一次 `IN (...)`** 批量查库）；不带证据属性的边给 `evidence: null`
    ＋ `note`。默认关闭时响应逐字节与既有版本一致。
    """
    source = _s(from_node).strip()
    if not source:
        raise errors.ApiError(1002, detail="缺少 from_node")
    target = _s(to_node).strip() or None
    rel = _check_relation(relation)
    if not target and not rel:
        raise errors.ApiError(1002, detail="必须给出 to_node，或给出 relation（二者至少其一）")
    hop_no = _parse_int(hop, "hop", default=2)
    if hop_no not in (1, 2):
        raise errors.ApiError(1002, detail="hop 只能是 1 或 2：%r" % hop)
    lo = _time_bound(start_time, "start_time")
    hi = _time_bound(end_time, "end_time", end=True)
    if lo and hi and lo > hi:
        raise errors.ApiError(1002, detail="start_time 晚于 end_time：%s > %s" % (lo, hi))

    with reader() as rd:
        if target:
            env = rd.graph.g7_paths(source, target, max_depth=hop_no)
            if _s(env.get("code")) == gs.RC_NOT_FOUND:
                raw, node_ids = [], []
            else:
                raw, node_ids = env.get("results") or [], env.get("node_ids") or []
                if rel:
                    raw = [p for p in raw
                           if any(_s(r.get("relation")) == rel for r in (p.get("relations") or []))]
        else:
            res = rd.graph.resolve_node(source)
            if _s(res.get("code")) != gs.RC_OK:
                raw = []
            else:
                raw = []
                for nid in res["node_ids"]:
                    raw += rd.relation_paths(nid, rel, hop_no)
        raw = _dedup_paths(raw)
        if lo or hi:
            raw = [p for p in raw if _path_in_window(rd, p, lo, hi)]
        with_ev = _truthy(with_evidence)
        doc_meta = chunk_meta = None
        if with_ev:
            # 全部路径上的边一起收集 → 一次 IN 批量补元数据（不逐条查）
            all_raw = [rel for p in raw for rel in (p.get("relations") or [])]
            doc_meta, chunk_meta = _evidence_index(all_raw)
        payload = [_path_payload(rd, p, with_ev, doc_meta, chunk_meta) for p in raw]
        payload = _sort_paths(payload)
    return errors.ok({"paths": payload, "hop": hop_no,
                      "is_graph_extended": bool(payload),
                      "from_node": source, "to_node": target, "relation": rel,
                      "start_time": lo or None, "end_time": hi or None})


def _path_in_window(rd: GraphReader, path: dict, lo: str, hi: str) -> bool:
    """路径是否落在时间窗内（按路径上 Event 节点的 `event_time`；空值按策略剔除）。"""
    events = [nid for nid in (path.get("nodes") or []) if rd.label_of(nid) == "Event"]
    if not events:
        return True                                   # 与时间无关的路径原样保留
    for nid in events:
        node = rd._raw_node(nid) or {}                # noqa: SLF001
        et = _norm_event_time(node.get("event_time"))
        if not et:
            if NULL_TIME_POLICY == "keep":
                return True
            continue
        if (not lo or et >= lo) and (not hi or et <= hi):
            return True
    return False


# --------------------------------------------------------------------------
# 9. 接口四：GET /api/graph/events
# --------------------------------------------------------------------------
def _events_in_window(events: list, lo: str, hi: str) -> list:
    """按 `event_time` 过滤事件（闭区间；空值策略取自检索侧 config，当前 `exclude`）。"""
    if not lo and not hi:
        return list(events)
    out = []
    for ev in events:
        et = _norm_event_time(ev.get("event_time"))
        if not et:
            if NULL_TIME_POLICY == "keep":
                out.append(ev)
            continue
        if (not lo or et >= lo) and (not hi or et <= hi):
            out.append(ev)
    return out


def _event_item(view: dict) -> dict:
    """表 4-13 的事件条目：`event_id`／`event_type`／`event_name`／`event_time`／
    `description`／`confidence`（另带 `node_id` 供前端跳详情——本项目的补充字段）。"""
    return {"event_id": _s(view.get("event_id")) or _s(view.get("node_id")),
            "node_id": _s(view.get("node_id")),
            "event_type": _s(view.get("event_type")),
            "event_name": _s(view.get("event_name")),
            "event_time": _s(view.get("event_time")),
            "description": _s(view.get("description")),
            "confidence": _float(view.get("confidence"))}


@router.get("/events")
async def list_events(event_type: str | None = None, stock_code: str | None = None,
                      start_time: str | None = None, end_time: str | None = None,
                      page: str | None = None, page_size: str | None = None):
    """按条件查事件：`event_type`（8 类）／`stock_code`／时间窗／分页；空结果 → HTTP 200。"""
    etype = _check_event_type(event_type)
    code = _s(stock_code).strip()
    lo = _time_bound(start_time, "start_time")
    hi = _time_bound(end_time, "end_time", end=True)
    if lo and hi and lo > hi:
        raise errors.ApiError(1002, detail="start_time 晚于 end_time：%s > %s" % (lo, hi))
    page_no, size = _page_args(page, page_size)

    with reader() as rd:
        if code:
            env = rd.graph.g4_company_events(code)
            views = env.get("results") or []          # 公司未匹配到 → 空结果（表 4-13 只列 1002／2002）
        elif etype:
            env = rd.graph.g3_events_by_type(etype)
            views = env.get("results") or []
        else:
            views = rd.all_events()
        views = _events_in_window(views, lo, hi)
        views.sort(key=lambda e: (_s(e.get("event_time")), _s(e.get("node_id"))))
        items = [_event_item(v) for v in views]
    start = (page_no - 1) * size
    return errors.ok_page(len(items), items[start:start + size], page_no, size)


# --------------------------------------------------------------------------
# 10. 接口五：GET /api/graph/events/{event_id}
# --------------------------------------------------------------------------
@router.get("/events/{event_id}")
async def event_detail(event_id: str):
    """事件详情：六项核心属性 ＋ 参与方（含 role）＋ 发布方 ＋ 政策 ＋ 多来源证据。

    证据 `evidences` 按 `publish_time` **升序**、按（文档，文本块）**多来源去重**，
    最早的一条标 `is_primary=true`（主要来源）。事件不存在（或不是 Event 节点）→ 2001。
    """
    eid = _s(event_id).strip()
    with reader() as rd:
        label = rd.label_of(eid)
        if label is None:
            raise errors.ApiError(2001, detail="事件标识不存在：%s" % eid)
        if label != "Event":
            raise errors.ApiError(2001, detail="标识 %s 不是 Event 节点（label=%s）" % (eid, label))
        raw = rd._raw_node(eid) or {}                 # noqa: SLF001
        event = {"event_id": _s(raw.get("event_id")) or eid, "node_id": eid, "label": label,
                 "event_type": _s(raw.get("event_type")), "event_name": _s(raw.get("event_name")),
                 "event_time": _s(raw.get("event_time")),
                 "description": _s(raw.get("description")),
                 "confidence": _float(raw.get("confidence"))}
        env = rd.graph.g1_one_hop(eid)
        incident = _dedup_edges(env.get("results") or [])
        participants, issuers, policies = {}, {}, {}
        for item in incident:
            neighbor = _s(item.get("neighbor"))
            brief = _brief_of(rd, item, neighbor)
            rel = _s(item.get("relation"))
            evidence = item.get("evidence") or {}
            if rel in ("PARTICIPATES_IN", "ISSUED_BY"):
                bucket = participants if rel == "PARTICIPATES_IN" else issuers
                key = (neighbor, _s(item.get("role")))
                row = bucket.setdefault(key, {
                    "node_id": neighbor, "label": brief["label"], "name": brief["name"],
                    "role": _s(item.get("role")), "relation": rel,
                    "source_doc_ids": [], "source_chunk_ids": [], "confidence": None})
                for field, attr in (("source_doc_ids", "source_doc_id"),
                                    ("source_chunk_ids", "source_chunk_id")):
                    value = _num(evidence.get(attr))
                    if value is not None and value not in row[field]:
                        row[field].append(value)
                if row["confidence"] is None:
                    row["confidence"] = _float(evidence.get("confidence"))
            if brief["label"] == "Policy":
                policies.setdefault(neighbor, {"node_id": neighbor, "label": brief["label"],
                                               "name": brief["name"], "relation": rel})
        participant_rows = sorted(participants.values(), key=lambda r: (r["role"], r["node_id"]))
        issuer_rows = sorted(issuers.values(), key=lambda r: r["node_id"])
        policy_rows = [policies[k] for k in sorted(policies)]
        g5 = rd.graph.g5_event_evidence(eid)
        evidences = _event_evidences(rd, g5)
        primary = next((e for e in evidences if e["is_primary"]), None)
    return errors.ok({"event": event,
                      "participants": participant_rows,
                      "issuer": (issuer_rows[0] if issuer_rows else None), "issuers": issuer_rows,
                      "policies": policy_rows,
                      "evidences": evidences, "evidence_total": len(evidences),
                      "primary_evidence": primary,
                      "primary_source_doc_id": (primary or {}).get("doc_id")})


def _dedup_by(items: list, key: str) -> list:
    seen, out = set(), []
    for item in items:
        if item.get(key) in seen:
            continue
        seen.add(item.get(key))
        out.append(item)
    return out


def _event_evidences(rd: GraphReader, g5: dict) -> list:
    """把 G5 的两个结果（带 `source_chunk_id` 的语义边／`EVIDENCED_BY` 的文档）合成证据列表。

    * **文本块级**：`G5.chunks` 的 `evidence.source_doc_id` ＋ `source_chunk_id`；
    * **文档级**：`G5.document_refs`（`EVIDENCED_BY` 指向的 Document 节点，无文本块）；
      同一文档已有文本块级证据时不再单列（**多来源去重**）；
    * 元数据（标题／来源／发布时间／链接／序号）取自 MySQL `document`／`document_chunk`；
    * 排序：`publish_time` 升序（取不到的排最后，再按 `doc_id`／`chunk_id` 升序），
      最早一条 `is_primary=true`。
    """
    merged: dict = {}
    # G5 的信封里 `results` 就是**文本块级**候选（`chunks` 是同一份的别名，两个后端都写在 `results`）
    for item in (g5.get("results") or g5.get("chunks") or []):
        evidence = item.get("evidence") or {}
        doc_id, chunk_id = _as_int(evidence.get("source_doc_id")), _as_int(evidence.get("source_chunk_id"))
        if chunk_id is None:
            continue
        key = ("chunk", doc_id, chunk_id)
        row = merged.setdefault(key, {
            "doc_id": doc_id, "chunk_id": chunk_id, "evidence_type": "chunk",
            "confidence": _float(evidence.get("confidence")), "relations": [], "roles": [],
            "chunk_index": None, "title": "", "source": "", "publish_time": "", "url": None})
        rel, role = _s(item.get("relation")), _s(item.get("role"))
        if rel and rel not in row["relations"]:
            row["relations"].append(rel)
        if role and role not in row["roles"]:
            row["roles"].append(role)
        if row["confidence"] in (None, "") and evidence.get("confidence") not in (None, ""):
            row["confidence"] = _float(evidence.get("confidence"))
    for ref in g5.get("document_refs") or []:
        doc_id = _as_int(ref.get("document_id"))
        if doc_id is None or any(k[1] == doc_id for k in merged):
            continue                                     # 该文档已有文本块级证据 → 去重
        merged[("document", doc_id, None)] = {
            "doc_id": doc_id, "chunk_id": None, "evidence_type": "document",
            "confidence": None, "relations": [_s(ref.get("relation"))], "roles": [],
            "chunk_index": None, "title": "", "source": "", "publish_time": "", "url": None}

    rows = list(merged.values())
    _fill_document_meta(rows)
    rows.sort(key=lambda r: (_s(r["publish_time"]) or "9999-12-31T23:59:59",
                             _as_int(r["doc_id"]) or 0, _as_int(r["chunk_id"]) or 0))
    for pos, row in enumerate(rows):
        row["is_primary"] = (pos == 0)
    return rows


def _fill_document_meta(rows: list) -> None:
    """用 MySQL 的 `document`／`document_chunk` 补齐标题、来源、发布时间、链接与块序号。"""
    doc_ids = sorted({r["doc_id"] for r in rows if r["doc_id"] is not None})
    if doc_ids:
        marks = ",".join(["%s"] * len(doc_ids))
        for doc in db.query(
                "SELECT doc_id, title, source, publish_time, url FROM document "
                "WHERE doc_id IN (%s)" % marks, tuple(doc_ids)):
            for row in rows:
                if row["doc_id"] == _as_int(doc["doc_id"]):
                    row["title"] = _s(doc["title"])
                    row["source"] = _s(doc["source"])
                    row["publish_time"] = _iso(doc["publish_time"])
                    row["url"] = doc["url"]
    chunk_ids = sorted({r["chunk_id"] for r in rows if r["chunk_id"] is not None})
    if chunk_ids:
        marks = ",".join(["%s"] * len(chunk_ids))
        for chunk in db.query(
                "SELECT chunk_id, chunk_index, token_count FROM document_chunk "
                "WHERE chunk_id IN (%s)" % marks, tuple(chunk_ids)):
            for row in rows:
                if row["chunk_id"] == _as_int(chunk["chunk_id"]):
                    row["chunk_index"] = _as_int(chunk["chunk_index"])
                    row["token_count"] = _as_int(chunk["token_count"])
