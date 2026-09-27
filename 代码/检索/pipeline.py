# -*- coding: utf-8 -*-
"""代码\\检索\\pipeline.py —— T4～T7：Top-K 五步契约的端到端实现。

依据：`阶段06-事件抽取与知识图谱\\18-第7阶段任务书（RAG检索系统）.md` 第九节 T4～T7、
第2.3节（五步契约与时间过滤位置）、第五节 硬约束 1～9／11～17、表 18-E（四条可执行断言）、
第八节 第 11～17 行；《10-系统总体设计（第四阶段）》第4.6.4节～第4.6.6节、第4.6.9节；
《02-项目执行总控文档》第12.7节（五步契约）、第11.3节（时间过滤位置与空值语义）。

**不可重排的调用链**（每一步都是一个可单独调用、可在 trace 里观测的段落）::

    ① 两路取候选：向量侧 N 条（VectorSearcher）＋ 图谱侧按检索深度 0／1／2
       （0 跳＝不取图谱侧；1／2 跳经 G1～G5 汇总语义边上的 source_chunk_id）
       —— D／E 组在这一步**先做时间过滤**（调 G6），空值一并剔除；
          A／B／C 组走"保留图谱侧全部候选"的分支（不调用 G6，不是"过滤参数为空"）
    ② 按 chunk_id 合并去重（集合并集；一个文本块只算一个证据，不重复计数、不加分）
    ③ 裁剪到 Context Token Budget（先裁与问题实体无关的远端图谱路径，
       再按「分层保留顺序」从尾部往前裁文本块；**不使用**排序结果）
    ④ 保留 K 个文本块（**先于** D／E 分组排序；候选不足 K 也不删题）
    ⑤ 最终证据集合（≤K）＋ 呈现顺序 ＋ 图谱路径载荷 ＋ 过滤前后候选差集 ＋ 断言结果

**分层保留顺序（2026-09-27 作者裁定「甲案」；第③步裁剪与第④步保留 K 共用同一条顺序）**::

    第一层  向量侧候选按**向量检索的原始排名**升序，取前 (K − g) 个；
    第二层  **图谱侧新增块**（没有向量排名的那些）按**对问题的向量相似度**降序
            （并列按 chunk_id 升序），**至多取 g 个**；
    第三层  前两层不足 K 个（或预算未用尽）时，按向量原始排名升序用**向量侧剩余候选**回填；
    尾部    图谱侧新增块里没有被第二层取到的那些（按原路径出现顺序）——只有在候选总数
            不超过 K、或预算裁剪把排在它们之前的成员全部裁掉之后才会被取到。

    g ＝ **全局固化量**：A～E 五组取同一值、**不进任何开关**、不随组变化，因此不破坏
    "三开关只差一个变量"的单变量归因；由 T8 预实验按「**在不劣于 g=0 的四项指标的前提下，
    让图谱侧证据进入最终集合的最大 g**」定值，定值后回《02》第12.7节 第一步与 第12.4节
    登记并冻结。**g = 0 时退化为原字面口径**（向量侧按原始排名在前、图谱侧新增块按其在
    路径上的出现顺序追加在后），用于对照与回归。图谱侧块参与排序用的是**索引里已有的
    对问题相似度**（对同一问题取一次全池分数并缓存复用），不新增模型、不新增外部调用。

**三个开关完全独立**（硬约束 9）：`graph_depth`（0／1／2）、`time_filter`（开／关）、
`evidence_sort`（开／关），取值域见 `config.SWITCH_DOMAINS`；A～E 只是三开关的一组预设
（`config.GROUPS`），代码里保存与判断的始终是三个独立变量，不合成模式字符串，
也不引入第四个可变参数、权重或阈值。

`g` 不是第四个开关：它不进 `config.GROUPS`、不进 `config.SWITCH_DOMAINS`，A～E 五组同值，
只决定第③／④步的"第二层"名额。

**K／N／Context Token Budget／g 一律经 `config.require_fixed(...)` 取**：预实验固化前读到 TBD
即报错退出，不用默认值兜底。`--selftest` 的数值同样从命令行参数（`--k`／`--n`／`--budget`／
`--graph-share`）取，缺省时才回落到 `config.require_fixed(...)`。

**四条可执行断言**（表 18-E，全部在 `--selftest` 里真跑，任一不成立即整体失败退出）：

1. D 与 E 的最终证据集合逐题相等（成员与大小）；
2. C 与 D 的最终证据集合可以不同：逐题打印双向差集与条数，差集为空标记"在该题上不可测"；
3. 同一 `chunk_id` 只算一个证据：`len(集合) == len(set(集合))`，并构造一题让两路命中同一
   文本块，断言它只出现一次、且没有额外加分；
4. `Precision@K` 的分母恒为 K：构造一题实际候选 M < K，断言题被保留、空缺记未命中、
   分母是 K，且**不实现"运行时候选不足就删题"**。
5. `g = 0` 退化为原字面口径：对同一批**真实候选集合**，用 g=0 的分层键排序的结果与
   「原字面口径」的排序键（`legacy_priority_key`）逐题、逐元素相同，取前 K 个也相同。

**三条实现裁定（《19》与 T4～T7 交付报告必须一并登记）**：

1. **深度口径**：深度 d ＝"从问题实体出发最多走 d 条关系边"；`G5` 取跳数 ≤ d−1 的事件的
   证据块（事件本身可被问题点名，或经 `G4`／`G3` 发现）。改判点是 `collect_graph_candidates()`。
2. **时间过滤的空值口径**：D／E 组的 `exclude` 策略不仅剔除 `event_time` 为空的事件路径，
   也剔除**支撑路径上没有任何事件**的候选（v2.9 裁定 ①："无法判定是否落在时间窗口内的成员
   不得视为通过过滤"）。改判点是 `apply_time_filter()`。
3. **第③／④步共用的"分层保留顺序"**（2026-09-27 作者裁定「甲案」，替代原来的"固定原始
   顺序"）：第一层＝向量侧按原始排名升序取前 (K − g) 个；第二层＝图谱侧新增块按**对问题的
   向量相似度**降序（并列按 `chunk_id` 升序）至多 g 个；第三层＝向量侧剩余候选按原始排名
   升序回填；尾部＝未被第二层取到的图谱侧新增块（按原路径出现顺序）。裁剪从尾部往前、第④步
   取前 K 个、D 组的呈现顺序都用这一顺序。改判点是 `evidence_priority_key()` 一处（第二层名额
   由 `plan_graph_layer()` 给出，全池相似度由 `full_pool_similarities()` 取一次并缓存）；
   `legacy_priority_key()` 逐字保留原口径的排序键，**只用于自查与回归比对**（g = 0 时新键与
   它同序）。P0 由此修复：图谱侧新增块可以进入最终证据集合。

纪律：输入只读（数据集 v2.1 与图谱导出物一个字节都不写）；参数只取同目录 `config.py`；
本链路 0 次大语言模型／外部接口调用（问题侧向量化是本地 Embedding 前向，按《18》第2.5节
不计入"模型调用"）；参与比对的 trace **不写时间戳与耗时**（耗时只打印到 stdout）。
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import time

# 控制台按 UTF-8 输出（中文 Windows 的 GBK 代码页会把中文与数学符号写坏）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:                                     # 极少见的非文本流 stdout
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config                                              # noqa: E402（唯一参数来源）
from graph_query import (GraphQuery, RC_EMPTY, RC_INVALID_INPUT,      # noqa: E402
                         RC_NOT_FOUND, RC_OK, default_graph)
from vector_search import VectorSearcher, load_pool        # noqa: E402

if os.path.dirname(os.path.abspath(config.__file__)) != _HERE:
    raise SystemExit("导入到的 config.py 不在本脚本同目录，拒绝继续：%s" % config.__file__)


# ---------------------------------------------------------------------------
# 0. 固定口径（不是可调参数；可调参数一律来自 config）
# ---------------------------------------------------------------------------
SCHEMA = "stage7-pipeline-trace-1.0"

# 三个开关的字段名（顺序即 trace 里的记录顺序；硬约束 9：三个独立变量）
SWITCH_NAMES = ("graph_depth", "time_filter", "evidence_sort")

FIVE_STEPS = (
    "① 两路取候选（D／E 组先做时间过滤）",
    "② 按 chunk_id 合并去重（集合并集，不重复计数、不加分）",
    "③ 裁剪到 Context Token Budget（先远端无关图谱路径，再按分层保留顺序从尾部往前）",
    "④ 保留 K 个文本块（先于 D／E 分组排序；候选不足 K 不删题）",
    "⑤ 最终证据集合＋呈现顺序＋图谱路径载荷＋差集＋断言结果",
)

# 第③步裁剪、第④步截取、第⑤步呈现**共用同一个**"分层保留顺序"（《10》第4.6.4节 第四步、
# 第4.6.5节、第4.6.6节；2026-09-27 作者裁定「甲案」）：
#   第一层＝向量侧按向量检索的原始排名升序取前 (K − g) 个；
#   第二层＝图谱侧新增块按**对问题的向量相似度**降序（并列按 chunk_id 升序）至多 g 个；
#   第三层＝前两层不足 K 个时按向量原始排名升序用向量侧剩余候选回填；
#   尾部＝未被第二层取到的图谱侧新增块（按原路径出现顺序）。
# 三者用同一把尺子，避免"裁剪说一种、截取说另一种"的自相矛盾；g 是全局固化量、不是第四个
# 可变参数（不进 config.GROUPS、不进 config.SWITCH_DOMAINS，A～E 五组同值）。
LEGACY_PRIORITY_RULE = ("固定原始顺序＝《10》第4.6.6节：向量检索的原始排名在前（按排名升序），"
                        "图谱侧新引入的文本块按其在路径上的出现顺序追加在后；"
                        "第③步的文本块裁剪与第④步的保留 K 都用这一顺序（裁剪从尾部往前，"
                        "截取取前 K 个），第⑤步 D 组的呈现顺序也是它")

# 「原字面口径」的两档标号（只用于 `legacy_priority_key` 与 g=0 的回归自查）：
# 0＝向量侧（在前），1＝图谱侧新增块（追加在后）。
LEGACY_VECTOR_TIER = 0
LEGACY_GRAPH_TIER = 1

# 「分层保留顺序」的四档标号（顺序不可颠倒——颠倒就等于把尾部块排到第一层之前）：
# 0＝第一层（向量侧前 K−g 个）／1＝第二层（图谱侧新增块前 g 个）／
# 2＝第三层（向量侧剩余候选回填）／3＝尾部（未被第二层取到的图谱侧新增块）。
LAYER1_VECTOR_TIER = 0
LAYER2_GRAPH_TIER = 1
LAYER3_VECTOR_FILL_TIER = 2
LEFTOVER_GRAPH_TIER = 3

# 事件类型词的匹配方式：整串子串匹配（不引入分词依赖；《18》第2.5节）
_CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")
_ASCII_RUN_RE = re.compile(r"[A-Za-z0-9_]+")
_CODE_RE = re.compile(r"(?<!\d)\d{6}(?!\d)")


def priority_rule_text(k: int, g: int) -> str:
    """本次运行的**有效保留顺序**口径文字（落进 trace 的 `priority_rule` 字段）。

    * `g = 0`：逐字返回**原字面口径**（`LEGACY_PRIORITY_RULE`）——此时分层保留顺序与它同序，
      该文字既如实、又保证"g=0 与修订前逐字节一致"的回归可比；
    * `g > 0`：返回分层保留顺序的口径文字，并把本次的 `g` 写进文字（trace 自描述）。
    """
    if int(g) <= 0:
        return LEGACY_PRIORITY_RULE
    return ("分层保留顺序＝《10》第4.6.4节 第四步／第4.6.6节（2026-09-27 裁定）：第一层＝向量侧"
            "候选按向量检索的原始排名升序取前 (K−g) 个；第二层＝图谱侧新增块（没有向量排名的那些）"
            "按对问题的向量相似度降序（并列按 chunk_id 升序）至多取 g 个；第三层＝前两层不足 K 个时"
            "按向量原始排名升序用向量侧剩余候选回填（尾部＝未被第二层取到的图谱侧新增块）。"
            "g=%d 为全局固化量（A～E 同值、不进任何开关，由 T8 预实验定值）；第③步的文本块裁剪与"
            "第④步的保留 K 都用这一顺序（裁剪从尾部往前，截取取前 K 个），第⑤步 D 组的呈现顺序也是它"
            % int(g))


# ---------------------------------------------------------------------------
# 一、开关与口径校验
# ---------------------------------------------------------------------------
def _parse_switch_bool(text, name: str) -> bool:
    """命令行上的开／关取值（只接受明确写法；不引入第三种取值域）。"""
    value = str(text).strip().lower()
    if value in ("on", "true", "1", "yes"):
        return True
    if value in ("off", "false", "0", "no"):
        return False
    raise SystemExit("[pipeline] 失败：%s 只能是 on／off，收到 %r" % (name, text))


def normalize_switches(group=None, graph_depth=None, time_filter=None,
                       evidence_sort=None) -> dict:
    """把"组预设 ＋ 逐项覆盖"归一成**三个独立开关**（硬约束 9）。

    * `group` 只是 `config.GROUPS` 里的一组预设值；不传时取 `config.DEFAULT_GROUP`；
    * 三个开关各自可单独覆盖；覆盖后的取值必须落在 `config.SWITCH_DOMAINS` 内；
    * 返回 `{"group": 组名, "switches": {三个开关}}`，代码其余部分只读 switches。
    """
    name = group if group is not None else config.DEFAULT_GROUP
    if name not in config.GROUPS:
        raise SystemExit("[pipeline] 失败：未知的分组预设 %r（合法值 %s）"
                         % (group, sorted(config.GROUPS)))
    switches = dict(config.GROUPS[name])
    if graph_depth is not None:
        switches["graph_depth"] = int(graph_depth)
    if time_filter is not None:
        switches["time_filter"] = _parse_switch_bool(time_filter, "time_filter")
    if evidence_sort is not None:
        switches["evidence_sort"] = _parse_switch_bool(evidence_sort, "evidence_sort")
    for key in SWITCH_NAMES:
        if switches[key] not in config.SWITCH_DOMAINS[key]:
            raise SystemExit("[pipeline] 失败：开关 %s=%r 不在 config.SWITCH_DOMAINS %s 内"
                             % (key, switches[key], config.SWITCH_DOMAINS[key]))
    return {"group": name, "switches": {key: switches[key] for key in SWITCH_NAMES}}


def resolve_k_n_budget(args) -> dict:
    """K／N／Context Token Budget／g：命令行优先，缺省回落 `config.require_fixed(...)`。

    硬约束 10／22：四项在 T8 固化前是 TBD，读到即报错退出，**不用默认值兜底**。
    `g` 是**全局固化量**（A～E 五组同值、不进任何开关），由 T8 预实验按「在不劣于 g=0 的
    四项指标的前提下，让图谱侧证据进入最终集合的最大 g」定值；取值域为 0…K（`g = K`
    即"图谱侧优先"的极端口径，须由预实验裁定后才能使用）。
    """
    k = int(args.k) if args.k is not None else int(config.require_fixed("K"))
    n = int(args.n) if args.n is not None else int(config.require_fixed("N"))
    budget = int(args.budget) if args.budget is not None else int(
        config.require_fixed("context_token_budget"))
    if k <= 0 or n <= 0 or budget <= 0:
        raise SystemExit("[pipeline] 失败：K／N／Context Token Budget 必须为正整数"
                         "（收到 K=%d N=%d budget=%d）" % (k, n, budget))
    if n < k:
        raise SystemExit("[pipeline] 失败：必须 N ≥ K（收到 N=%d K=%d）；"
                         "预实验网格的口径见《02》第12.7节 第一步" % (n, k))
    g = (int(args.graph_share) if getattr(args, "graph_share", None) is not None
         else int(config.require_fixed("graph_retention_share")))
    if g < 0 or g > k:
        raise SystemExit("[pipeline] 失败：g（图谱侧保留份额）必须落在 0…K 之间"
                         "（收到 g=%d K=%d）；g=K 即\"图谱侧优先\"的极端口径，"
                         "须由 T8 预实验裁定后才能使用" % (g, k))
    return {"k": k, "n": n, "budget": budget, "g": g}


# ---------------------------------------------------------------------------
# 二、输入加载（**只读**；不写输入文件）
# ---------------------------------------------------------------------------
def load_chunks(path: str | None = None) -> dict:
    """读 `chunks.jsonl`：`chunk_id → 行`（预算分账用它的 `token_count`）。"""
    rows = {}
    for row in config.iter_jsonl(path or config.CHUNKS_PATH):
        rows[int(row["chunk_id"])] = row
    return rows


def load_documents(path: str | None = None) -> dict:
    """读 `documents.jsonl`：`doc_id → 行`（E 组排序用 `publish_time`；只读）。"""
    rows = {}
    for row in config.iter_jsonl(path or config.DOCS_PATH):
        rows[int(row["doc_id"])] = row
    return rows


def load_questions(path: str) -> list:
    """读题集：一行一题；`qid`／`question` 必填，`time_window`／gold 字段可缺省。

    **不解析成别的格式、不改写题集**；缺 `qid` 时按行号补 `Q<行号>`（仅用于自定义输入）。
    """
    if not os.path.isfile(path):
        raise SystemExit("[pipeline] 失败：题集不存在：%s" % path)
    rows = []
    for index, row in enumerate(config.iter_jsonl(path), 1):
        if "question" not in row or not str(row["question"]).strip():
            raise SystemExit("[pipeline] 失败：第 %d 行缺 question 字段" % index)
        rows.append(normalize_question_row(row, default_qid="Q%02d" % index))
    if not rows:
        raise SystemExit("[pipeline] 失败：题集为空：%s" % path)
    return rows


def normalize_question_row(row: dict, default_qid: str = "Q01",
                           time_lo: str | None = None, time_hi: str | None = None) -> dict:
    """把一行题归一成流水线要用的形状（只做搬运与校验，不改题干）。"""
    window = row.get("time_window")
    if isinstance(window, dict) and window.get("lo") and window.get("hi"):
        window = {"lo": str(window["lo"]), "hi": str(window["hi"]),
                  "label": str(window.get("label") or ""),
                  "basis": str(window.get("basis") or ""),
                  "empty_policy": str(window.get("empty_policy")
                                      or config.RETRIEVAL["time_filter_null_policy"]),
                  "source": "题集 time_window"}
    elif time_lo and time_hi:
        window = {"lo": str(time_lo), "hi": str(time_hi), "label": "命令行区间",
                  "basis": "命令行 --time-lo／--time-hi",
                  "empty_policy": config.RETRIEVAL["time_filter_null_policy"],
                  "source": "命令行"}
    else:
        window = None
    gold = [int(x) for x in (row.get("gold_evidence_chunk_ids") or [])]
    return {
        "qid": str(row.get("qid") or default_qid),
        "question": str(row["question"]).strip(),
        "time_window": window,
        "gold_evidence_chunk_ids": gold,
        "task_type": str(row.get("task_type") or ""),
        "gold_hop_depth": row.get("gold_hop_depth"),
    }


# ---------------------------------------------------------------------------
# 三、问题侧：实体匹配与事件类型（确定性，不引入分词依赖）
# ---------------------------------------------------------------------------
def _norm_text(text) -> str:
    """标识归一化：剔除全部空白、转小写（与图谱查询层同一口径）。"""
    return "".join(str(text).split()).lower()


def resolve_question_entities(graph, question: str, min_key_len: int = 2) -> dict:
    """确定性地把问题里的实体提及匹配到图节点（最长匹配优先、非重叠）。

    * 匹配键：节点的 `name`／`short_name`／`aliases`（经图谱查询层已建好的索引）；
      以及 6 位 `stock_code`（数字边界独立匹配）；
    * 命中多个节点（重名／多别名）时全部保留（图谱查询层对多命中取并集）；
    * `Document` 标签的节点不参与（它的边只有 EVIDENCED_BY，不产生文本块级候选）；
    * **不猜、不模糊匹配**：只做精确的子串匹配，并把命中明细写进 trace。
    """
    text = _norm_text(question)
    taken = [False] * len(text)
    matches, seeds, excluded_documents = [], set(), 0
    for key in sorted(graph.by_name.keys(), key=lambda k: (-len(k), k)):
        if len(key) < int(min_key_len):
            continue
        start = 0
        while True:
            pos = text.find(key, start)
            if pos < 0:
                break
            if not any(taken[pos:pos + len(key)]):
                node_ids = []
                for nid in graph.by_name[key]:
                    if str(graph.nodes.get(nid, {}).get("label") or "") == "Document":
                        excluded_documents += 1
                        continue
                    node_ids.append(nid)
                    seeds.add(nid)
                for offset in range(pos, pos + len(key)):
                    taken[offset] = True
                matches.append({"key": key, "start": pos, "matched_by": "name",
                                "node_ids": sorted(node_ids)})
            start = pos + 1
    for hit in _CODE_RE.finditer(text):
        code = hit.group(0)
        node_ids = sorted(graph.by_code.get(code) or [])
        if node_ids:
            matches.append({"key": code, "start": hit.start(), "matched_by": "stock_code",
                            "node_ids": node_ids})
            seeds.update(node_ids)
    matches.sort(key=lambda m: (m["start"], -len(m["key"]), m["key"]))
    by_label = {}
    for nid in sorted(seeds):
        label = str(graph.nodes.get(nid, {}).get("label") or "")
        by_label.setdefault(label, []).append(nid)
    return {"seeds": sorted(seeds), "matches": matches, "by_label": by_label,
            "excluded_document_matches": excluded_documents}


def question_event_types(question: str) -> list:
    """问题里点名的事件类型（按 `config.EVENT_TYPES` 的固定顺序做子串匹配）。"""
    return [t for t in config.EVENT_TYPES if t and t in question]


# ---------------------------------------------------------------------------
# 四、第①步：两路取候选（含 D／E 组的时间过滤）
# ---------------------------------------------------------------------------
def collect_vector_candidates(searcher: VectorSearcher, question: str, n: int) -> dict:
    """第①步·向量侧：N 条候选与向量检索的原始排名（复用 T2，不重写检索）。"""
    rows, timing = searcher.search(question, n)
    return {"rows": rows, "timing": timing, "n": int(n)}


def full_pool_similarities(searcher: VectorSearcher, question: str, cache: dict) -> dict:
    """对同一问题取**全池**（`config.CORPUS["vectors"]` 条）相似度，按 `chunk_id` 建索引并缓存复用。

    **只用于第二层（图谱侧新增块）的排序**，不改变向量侧候选池仍是 N 条这一语义：全池分数
    不进入候选集合、不改写任何候选的 `similarity`／`vector_rank`，也不新增模型与外部调用。
    相似度由 `VectorSearcher.search()` 按固定精度（8 位小数）给出，排序用它的原值。
    """
    key = str(question)
    if key not in cache:
        rows, _timing = searcher.search(key, int(config.CORPUS["vectors"]))
        cache[key] = {int(row["chunk_id"]): float(row["similarity"]) for row in rows}
    return cache[key]


def attach_question_similarity(records, similarities: dict) -> None:
    """把全池相似度挂到**图谱侧新增块**上（向量侧块保留它自己的 N 内相似度，不改写、不参与）。"""
    for record in records:
        if record.get("vector_rank") is None:
            record["question_similarity"] = similarities.get(int(record["chunk_id"]))


def _node_label(graph, node_id: str) -> str:
    return str(graph.nodes.get(node_id, {}).get("label") or "")


def _reachable(graph, seeds, depth: int) -> dict:
    """从种子出发做**确定性**广度优先，返回 `node_id → 跳数`（跳数 ≤ depth）。"""
    dist = {seed: 0 for seed in sorted(seeds)}
    frontier = sorted(dist)
    for hop in range(1, int(depth) + 1):
        next_frontier = []
        for node in frontier:
            for rec in graph.adj.get(node, []):
                neighbor = rec["neighbor"]
                if neighbor not in dist:
                    dist[neighbor] = hop
                    next_frontier.append(neighbor)
        frontier = sorted(next_frontier)
    return dist


def collect_graph_candidates(graph, seeds, event_types, depth: int, chunks: dict) -> dict:
    """第①步·图谱侧：按检索深度 0／1／2 汇总**语义边上的 source_chunk_id**。

    深度口径（实现裁定 ①，见文末）：深度 d 表示"从问题实体出发最多走 d 条关系边"。

    * `G1`：对每个种子取一跳邻居上的关系项（入池依据是关系上的 `source_chunk_id`）；
    * `G2`：深度 ≥ 2 时对每个种子取两跳路径（结果包含一跳，2 跳 ⊇ 1 跳）；
    * `G4`：公司种子 → 该公司参与的事件（`PARTICIPATES_IN`，方向 Company → Event）；
    * `G3`：问题里点名的事件类型 → 该类型的事件（**只在它与问题实体 ≤ depth 跳，
      或问题里根本没有可匹配实体时**入池，避免把同类型的全量事件倒进候选）；
    * `G5`：对跳数 ≤ depth−1 的事件（含点名事件）取事件证据块。

    **G5 边界（硬约束 14）**：入池只认带 `source_chunk_id` 的 8 条语义边；`EVIDENCED_BY`
    不带 `source_chunk_id`、不产生文本块级候选。每个入池的 `chunk_id` 必须在 v2.1 的
    `chunks.jsonl` 里存在，且其 `doc_id` 与该边的 `source_doc_id` 一致——不一致的候选
    **剔除并计数**（不是静默跳过）。
    """
    calls = {key: 0 for key in ("G1", "G2", "G3", "G4", "G5")}
    codes = {key: {} for key in calls}
    audit = {"chunk_refs": 0, "invalid_not_in_chunks": 0, "invalid_doc_mismatch": 0,
             "invalid_detail": [], "excluded_evidenced_by": 0, "excluded_no_chunk_id": 0}

    def note(interface, code):
        codes[interface][code] = codes[interface].get(code, 0) + 1

    empty = {"depth": int(depth), "seeds": sorted(seeds), "calls": calls, "codes": codes,
             "reach": {"hop1": 0, "hop2": 0}, "events": [], "paths": [], "candidates": {},
             "audit": audit, "graph_used": False,
             "note": "检索深度 0：不取图谱侧候选（第一步的图谱侧为空集）"}
    if int(depth) <= 0:
        return empty

    dist = _reachable(graph, seeds, depth)
    # --- 事件集合：先收"可达事件"，再补 G4（公司参与事件）与 G3（点名类型的事件）
    events = {}
    for nid in sorted(dist):
        if _node_label(graph, nid) == "Event":
            events[nid] = {"event_id": nid, "distance": dist[nid], "via": "reach"}
    for seed in sorted(seeds):
        if _node_label(graph, seed) != "Company":
            continue
        res = graph.g4_company_events(seed)
        calls["G4"] += 1
        note("G4", res["code"])
        for item in res["results"]:
            eid = item["node_id"]
            if eid not in events:
                events[eid] = {"event_id": eid, "distance": dist.get(eid, 1), "via": "G4"}
    g3_excluded = 0
    for event_type in event_types:
        res = graph.g3_events_by_type(event_type)
        calls["G3"] += 1
        note("G3", res["code"])
        for item in res["results"]:
            eid = item["node_id"]
            if seeds and dist.get(eid, 10 ** 6) > int(depth):
                g3_excluded += 1
                continue
            events.setdefault(eid, {"event_id": eid, "distance": dist.get(eid, 0),
                                    "via": "G3"})

    # --- 路径收集（确定性顺序：G1 → G2 → G5；同一组内按图谱查询层给定的排序键）
    paths, seen_paths = [], set()

    def add_path(source, start, nodes, relations):
        key = (tuple(r["edge_id"] for r in relations),
               tuple(r["direction"] for r in relations))
        if key in seen_paths:
            return
        seen_paths.add(key)
        events_on_path = sorted({n for n in nodes if _node_label(graph, n) == "Event"})
        paths.append({"ordinal": len(paths), "source": source, "start": start,
                      "end": nodes[-1], "depth": len(relations), "nodes": list(nodes),
                      "relations": [dict(r) for r in relations],
                      "anchor_distance": dist.get(start, 0),
                      "events": events_on_path})

    def usable(relation_item) -> bool:
        """入池判据：8 条语义边 ＋ 带 source_chunk_id（EVIDENCED_BY 天然被排除）。"""
        if relation_item["relation"] not in config.SEMANTIC_RELATIONS:
            return False
        evidence = relation_item.get("evidence") or {}
        if not evidence.get("source_chunk_id"):
            return False
        return True

    for seed in sorted(seeds):
        res = graph.g1_one_hop(seed)
        calls["G1"] += 1
        note("G1", res["code"])
        for item in res["results"]:
            if item["relation"] == config.EVIDENCED_BY:
                audit["excluded_evidenced_by"] += 1
                continue
            if not usable(item):
                audit["excluded_no_chunk_id"] += 1
                continue
            add_path("G1", seed, [seed, item["neighbor"]], [item])

    if int(depth) >= 2:
        for seed in sorted(seeds):
            res = graph.g2_two_hop(seed)
            calls["G2"] += 1
            note("G2", res["code"])
            for path in res["results"]:
                if path["depth"] < 2:                    # 一跳层已由 G1 收过，避免重复
                    continue
                if not all(usable(item) for item in path["relations"]):
                    continue
                add_path("G2", path["start"], path["nodes"], path["relations"])

    for eid in sorted(events):
        if events[eid]["distance"] > int(depth) - 1 and events[eid]["via"] != "G3":
            continue
        res = graph.g5_event_evidence(eid)
        calls["G5"] += 1
        note("G5", res["code"])
        for item in res["results"]:
            if not usable(item):
                continue
            add_path("G5", eid, [eid, item["neighbor"]], [item])

    # --- 候选块：每个入池 chunk_id 都做存在性与 doc_id 一致性核验（硬约束 14）
    candidates = {}
    for path in paths:
        for index, item in enumerate(path["relations"]):
            evidence = item["evidence"]
            audit["chunk_refs"] += 1
            raw = str(evidence["source_chunk_id"]).strip()
            if not raw.isdigit():
                audit["invalid_not_in_chunks"] += 1
                audit["invalid_detail"].append({"chunk_id": raw, "reason": "非数字 chunk_id"})
                continue
            cid = int(raw)
            row = chunks.get(cid)
            if row is None:
                audit["invalid_not_in_chunks"] += 1
                audit["invalid_detail"].append({"chunk_id": raw, "reason": "chunks.jsonl 里不存在"})
                continue
            source_doc = str(evidence.get("source_doc_id") or "").strip()
            if source_doc and int(row["doc_id"]) != int(source_doc):
                audit["invalid_doc_mismatch"] += 1
                audit["invalid_detail"].append(
                    {"chunk_id": raw, "reason": "doc_id 与 source_doc_id 不一致",
                     "chunk_doc_id": int(row["doc_id"]), "source_doc_id": source_doc})
                continue
            rec = candidates.setdefault(cid, {
                "chunk_id": cid, "doc_id": int(row["doc_id"]),
                "path_ordinals": [], "path_relation_index": {}, "events": [],
                "relations": [], "sources": [], "anchor_min": 10 ** 6})
            if path["ordinal"] in rec["path_relation_index"]:
                rec["path_relation_index"][path["ordinal"]].append(index)
            else:
                rec["path_relation_index"][path["ordinal"]] = [index]
            if path["ordinal"] not in rec["path_ordinals"]:
                rec["path_ordinals"].append(path["ordinal"])
                rec["sources"].append(path["source"])
            rec["events"] = sorted(set(rec["events"]) | set(path["events"]))
            rec["relations"] = sorted(set(rec["relations"]) | {item["relation"]})
            rec["anchor_min"] = min(rec["anchor_min"], int(path["anchor_distance"]))
    for rec in candidates.values():
        rec["path_ordinals"].sort()
        rec["sources"] = sorted(set(rec["sources"]))
        rec["first_key"] = (min(rec["path_ordinals"]),
                            min(rec["path_relation_index"][min(rec["path_ordinals"])]))

    hop1 = sum(1 for nid in dist if dist[nid] == 1)
    hop2 = sum(1 for nid in dist if dist[nid] == 2)
    return {
        "depth": int(depth), "seeds": sorted(seeds), "calls": calls, "codes": codes,
        "reach": {"hop1": hop1, "hop2": hop2,
                  "nodes": len(dist), "hop1_nodes": sorted(n for n in dist if dist[n] == 1)[:50]},
        "events": sorted(events.values(), key=lambda e: (e["event_id"])),
        "events_excluded_by_distance": g3_excluded,
        "paths": paths,
        "candidates": candidates,
        "audit": audit,
        "graph_used": bool(candidates) or bool(paths),
    }


def resolve_time_window(question_row: dict, event_ids, graph) -> dict:
    """解析 D／E 组要用的时间闭区间 `[lo, hi]`（一律按 `event_time`，硬约束 21）。

    * 题集给了 `time_window` 就用它（相对时间已由上游解析成闭区间）；
    * 题**没有**时间约束时，用"本小题在范围内的非空 `event_time` 的极值区间"——
      该区间由运行期数据导出，不写死任何日期；此时过滤器只起"空值剔除"的作用；
    * 极端情形（候选里一个非空 `event_time` 都没有）退化为 `data_cutoff_time` 的日期宽度
      为 0 的闭区间（取 `config.DATA_CUTOFF_TIME` 的日期部分，仍不写死日期）。
    """
    window = question_row.get("time_window")
    if window:
        return {"lo": window["lo"], "hi": window["hi"], "label": window.get("label") or "",
                "basis": window.get("basis") or "题集 time_window",
                "source": window.get("source") or "题集"}
    nonempty = sorted({str(graph.nodes.get(eid, {}).get("event_time") or "").strip()
                       for eid in event_ids} - {""})
    if nonempty:
        lo, hi = nonempty[0], nonempty[-1]
    else:
        cutoff_date = str(config.DATA_CUTOFF_TIME)[:10]
        lo, hi = cutoff_date, cutoff_date
    return {"lo": lo, "hi": hi, "label": "无时间约束（取候选事件非空 event_time 的极值区间）",
            "basis": "题集未给时间约束 → 运行期由候选事件的 event_time 极值导出，只做空值剔除",
            "source": "运行期导出"}


def keep_all_graph_candidates(graph_side: dict) -> dict:
    """A／B／C 组的分支：**保留图谱侧全部候选**（硬约束 2）。

    这个分支**不调用 G6**，也不是"过滤参数为空"——trace 里 `branch` 字段写明
    `keep_all_graph`（与 D／E 的 `time_filter` 分支可区分）。
    """
    kept = sorted(graph_side["candidates"])
    return {
        "branch": "keep_all_graph",
        "enabled": False,
        "g6_called": False,
        "window": None,
        "g6": None,
        "kept_chunk_ids": kept,
        "removed_chunk_ids": [],
        "removed_by_reason": {"null_time_event": [], "out_of_range_event": [],
                              "no_event_time": []},
        "note": "A／B／C 组保留图谱侧全部候选（未调用 G6；不是过滤参数为空）",
    }


def apply_time_filter(graph, graph_side: dict, question_row: dict, chunks: dict) -> dict:
    """D／E 组的分支：调 G6 做时间过滤（空值一并剔除），**在合并去重之前**。

    逐候选的判定（空值策略取显式的 `config.RETRIEVAL["time_filter_null_policy"]`）：

    * 候选的支撑路径上有**通过过滤的事件** → 保留；
    * 有事件但全部被剔除（`event_time` 为空或落在窗口外） → 剔除；
    * 支撑路径上**没有事件**（无从判定是否落在窗口内） → 按空值策略一并剔除
      （v2.9 裁定 ①："一个无法判定是否落在时间窗口内的成员不得视为通过过滤"）。
    """
    policy = str(config.RETRIEVAL["time_filter_null_policy"])
    candidates = graph_side["candidates"]
    event_ids = sorted({eid for rec in candidates.values() for eid in rec["events"]})
    window = resolve_time_window(question_row, event_ids, graph)
    g6 = graph.g6_time_filter(event_ids, window["lo"], window["hi"], null_policy=policy)
    passed = set(g6.get("passed_ids") or [])
    removed_null = set(g6.get("removed_null_ids") or [])
    removed_range = set(g6.get("removed_out_of_range_ids") or [])

    kept, removed = [], []
    by_reason = {"null_time_event": [], "out_of_range_event": [], "no_event_time": []}
    for cid in sorted(candidates):
        rec = candidates[cid]
        events = set(rec["events"])
        if not events:
            by_reason["no_event_time"].append(cid)
            removed.append(cid)
            continue
        if events & passed:
            kept.append(cid)
            continue
        if events & removed_null:
            by_reason["null_time_event"].append(cid)
        elif events & removed_range:
            by_reason["out_of_range_event"].append(cid)
        else:                                          # G6 未覆盖到的（理论上不出现）
            by_reason["out_of_range_event"].append(cid)
        removed.append(cid)
    return {
        "branch": "time_filter",
        "enabled": True,
        "g6_called": True,
        "window": window,
        "g6": {"code": g6.get("code"), "query_key": g6.get("query_key"),
               "cypher": g6.get("cypher"), "sort_key": g6.get("sort_key"),
               "passed_ids": list(g6.get("passed_ids") or []),
               "removed_ids": list(g6.get("removed_ids") or []),
               "removed_null_ids": sorted(removed_null),
               "removed_out_of_range_ids": sorted(removed_range),
               "null_policy": g6.get("null_policy"),
               "chunk_ids_survived": list(g6.get("chunk_ids_survived") or []),
               "chunk_ids_removed": list(g6.get("chunk_ids_removed") or []),
               "chunk_id_diff": list(g6.get("chunk_id_diff") or []),
               "chunk_id_diff_reverse": list(g6.get("chunk_id_diff_reverse") or [])},
        "kept_chunk_ids": kept,
        "removed_chunk_ids": removed,
        "removed_by_reason": {key: sorted(value) for key, value in by_reason.items()},
        "note": "D／E 组：空值（含无事件可判定的路径）一并剔除；过滤发生在合并去重之前",
    }


def graph_candidates_after_filter(graph_side: dict, filter_record: dict) -> dict:
    """按过滤记录筛掉图谱侧候选（只筛图谱侧；向量侧不受影响，硬约束 2）。"""
    kept = set(filter_record["kept_chunk_ids"])
    return {cid: rec for cid, rec in graph_side["candidates"].items() if cid in kept}


# ---------------------------------------------------------------------------
# 五、第②步：按 chunk_id 合并去重（集合并集，不重复计数、不加分）
# ---------------------------------------------------------------------------
def merge_candidates(vector_rows, graph_candidates: dict, chunks: dict) -> dict:
    """集合并集：两路候选统一映射到 chunk_id，一个文本块只算一个证据。

    * 向量侧在前：按 `vector_rank` 升序（原始排名，不再重算相似度）；
    * 图谱侧新增块在后：按**路径出现顺序**（首条支撑路径的序号 → 该路径上的关系序号 →
      `chunk_id`）——这就是 D 组的"固定原始顺序"（《10》第4.6.6节）；
    * 两路同时命中 → 只保留一条，`hit_by = ["vector","graph"]`，**不加分、不合并加权**
      （`similarity`／`vector_rank` 原样来自向量侧）。
    """
    merged, order = {}, []
    for row in sorted(vector_rows, key=lambda r: (int(r["vector_rank"]), int(r["chunk_id"]))):
        cid = int(row["chunk_id"])
        if cid in merged:                              # 理论上不会出现（向量候选本身不重复）
            continue
        merged[cid] = {
            "chunk_id": cid, "doc_id": int(row["doc_id"]),
            "vector_id": int(row["vector_id"]), "vector_rank": int(row["vector_rank"]),
            "similarity": float(row["similarity"]),
            "hit_by": ["vector"], "graph_path_ordinals": [], "graph_events": [],
            "graph_relations": [], "graph_sources": [], "first_path_key": None,
            "graph_anchor_min": None,
            "token_count": int(chunks[cid]["token_count"]),
        }
        order.append(cid)
    graph_only = sorted((rec for cid, rec in graph_candidates.items() if cid not in merged),
                        key=lambda rec: (rec["first_key"], rec["chunk_id"]))
    for rec in graph_only:
        cid = rec["chunk_id"]
        merged[cid] = {
            "chunk_id": cid, "doc_id": int(rec["doc_id"]),
            "vector_id": None, "vector_rank": None, "similarity": None,
            "hit_by": ["graph"], "graph_path_ordinals": list(rec["path_ordinals"]),
            "graph_events": list(rec["events"]), "graph_relations": list(rec["relations"]),
            "graph_sources": list(rec["sources"]), "first_path_key": rec["first_key"],
            "graph_anchor_min": int(rec.get("anchor_min", 0)),
            "token_count": int(chunks[cid]["token_count"]),
        }
        order.append(cid)
    for cid, rec in graph_candidates.items():          # 两路同时命中：补上图谱侧信息
        if cid not in merged:
            continue
        target = merged[cid]
        if target["vector_rank"] is None:
            continue
        if "graph" in target["hit_by"]:
            continue
        target["hit_by"] = ["vector", "graph"]
        target["graph_path_ordinals"] = list(rec["path_ordinals"])
        target["graph_events"] = list(rec["events"])
        target["graph_relations"] = list(rec["relations"])
        target["graph_sources"] = list(rec["sources"])
        target["first_path_key"] = rec["first_key"]
        target["graph_anchor_min"] = int(rec.get("anchor_min", 0))
    records = [merged[cid] for cid in order]
    for rec in records:
        rec["hit_by"] = sorted(rec["hit_by"])
    return {"records": records, "order": order,
            "counts": {"vector": len(vector_rows), "graph": len(graph_candidates),
                       "union": len(records),
                       "dual_hit": sum(1 for rec in records if len(rec["hit_by"]) == 2),
                       "graph_only": sum(1 for rec in records if rec["vector_rank"] is None)}}


# ---------------------------------------------------------------------------
# 六、第③步：裁剪到 Context Token Budget（不使用排序结果）
# ---------------------------------------------------------------------------
def estimate_tokens(text) -> int:
    """图谱路径与事件三元组的**估算** token（可解释、确定性；不是分词器读数）。

    口径：中日韩字符 1 字符记 1 token；连续的 ASCII 字母／数字串每个记 1 token；
    其余标点与空白不计。文本块一律用 `chunks.jsonl` 的 `token_count` 实测值，不用本估算。
    """
    value = str(text)
    return len(_CJK_RE.findall(value)) + len(_ASCII_RUN_RE.findall(value))


def event_triple(graph, event_id: str) -> list:
    """事件三元组 `(event_id, event_type, event_time)`——字段形态见 `config.EVENT_TRIPLE_FIELDS`。"""
    node = graph.nodes.get(event_id) or {}
    return [str(node.get(field) or "") for field in config.EVENT_TRIPLE_FIELDS]


def retained_path_records(records, path_records) -> list:
    """当前证据集合用得上的图谱路径（按路径序号升序）。

    只保留**极小路径**：若一条路径是另一条更短路径的延长（前提边序列相同），它不重复计入
    预算、也不重复出现在 `answer.graph_path` 里——同一条关系边经一跳路径与两跳路径各出现
    一次属于重复展示（同一份证据只算一次；`EVIDENCED_BY` 之外的三项证据属性也随之只算一次）。
    """
    by_ordinal = {path["ordinal"]: path for path in path_records}
    seen = {}
    for rec in records:
        for ordinal in sorted(set(rec.get("graph_path_ordinals") or [])):
            path = by_ordinal.get(ordinal)
            if path is not None:
                seen[ordinal] = path
    relevant = [seen[ordinal] for ordinal in sorted(seen)]
    edges = [tuple(item["edge_id"] for item in path["relations"]) for path in relevant]
    kept = []
    for index, path in enumerate(relevant):
        mine = edges[index]
        if any(other != index and len(edges[other]) < len(mine)
               and mine[:len(edges[other])] == edges[other]
               for other in range(len(relevant))):
            continue
        kept.append(path)
    return kept


def account_tokens(records, path_records, graph, chunks) -> dict:
    """Context Token Budget 的分账：文本块（实测 token_count）＋ 图谱路径与事件三元组（估算）。

    事件三元组按**去重后**的事件计一次（格式决策 3：字段已在路径展示里出现的不重复计）。
    """
    kept_paths = retained_path_records(records, path_records)
    text_tokens = sum(int(chunks[rec["chunk_id"]]["token_count"]) for rec in records)
    path_tokens = 0
    event_ids = set()
    for path in kept_paths:
        payload = graph.graph_path_payload(path)
        path_tokens += estimate_tokens(config.stable_json(payload))
        event_ids.update(path["events"])
    triples = [event_triple(graph, eid) for eid in sorted(event_ids)]
    triple_tokens = sum(estimate_tokens("|".join(triple)) for triple in triples)
    return {
        "estimate_note": "文本块＝chunks.jsonl 的 token_count 实测；图谱路径与事件三元组＝估算 token",
        "text_chunks": len(records), "text_tokens": text_tokens,
        "paths": len(kept_paths), "path_tokens": path_tokens,
        "event_triples": len(triples), "event_triple_tokens": triple_tokens,
        "graph_tokens": path_tokens + triple_tokens,
        "total_tokens": text_tokens + path_tokens + triple_tokens,
    }


def path_trim_key(path: dict) -> tuple:
    """预算裁剪时图谱路径的"先裁"顺序：**起点离问题实体更远、路径更长、出现更靠后**先裁。"""
    return (-int(path["anchor_distance"]), -int(path["depth"]), -int(path["ordinal"]))


def is_remote_path(path: dict) -> bool:
    """"与问题实体无关的远端图谱路径"的可执行判据：**起点不是问题实体本身**的路径。

    起点就是问题实体的路径（`anchor_distance == 0`，即从问题实体直接出发的一跳／两跳路径）
    属于"与问题实体相关"的路径，不进入第一轮裁剪，只在预算装不下时作为最后手段处理。
    """
    return int(path["anchor_distance"]) > 0


def trim_rule_text(g: int) -> str:
    """本次运行的**裁剪规则**文字（`g = 0` 时逐字返回原口径，保证回归逐字节一致）。"""
    if int(g) <= 0:
        return ("先裁与问题实体无关的远端图谱路径 → 再按向量检索的原始排名从后往前裁文本块"
                "（裁剪先于证据排序，不使用排序结果）")
    return ("先裁与问题实体无关的远端图谱路径 → 再按分层保留顺序从尾部往前裁文本块"
            "（裁剪先于证据排序，不使用排序结果；g=%d）" % int(g))


def trim_to_budget(records, path_records, graph, chunks, budget: int, g: int,
                   order_key=None) -> dict:
    """第③步：把候选裁到 Context Token Budget 之内（**先裁远端无关图谱路径，再裁文本块**）。

    * 裁剪**先于**证据排序，依据只有"路径的疏远程度"与**分层保留顺序**（`order_key`＝第④步
      保留 K 用的同一个键，见 `evidence_priority_key`）——不使用任何重排结果（硬约束 16）；
    * 第一轮裁**与问题实体无关的远端图谱路径**（起点不是问题实体的路径，最远的先裁）；
      路径被裁掉后，只由这些路径支撑的图谱侧新增块随之出局；
    * 第二轮按**分层保留顺序**（见 `evidence_priority_key`）从尾部往前裁文本块；
    * 第三轮（前两轮仍装不下时的最后手段）才裁"从问题实体直接出发"的路径；
    * 至少保留 1 个文本块（预算再紧也不清空，并在 trace 里如实打印 `budget_floor_applied`）。
    """
    if order_key is None:
        order_key = retention_key(0, 0)
    kept = {rec["chunk_id"]: rec for rec in records}
    alive_paths = {path["ordinal"]: path for path in path_records}

    def recompute():
        current = [rec for rec in records if rec["chunk_id"] in kept]
        return account_tokens(current, [p for p in alive_paths.values()], graph, chunks)

    initial = recompute()
    before = initial
    dropped_paths, dropped_chunks = [], []
    floor_applied = False
    remote = sorted([p for p in path_records if is_remote_path(p)], key=path_trim_key)
    anchored = sorted([p for p in path_records if not is_remote_path(p)], key=path_trim_key)
    drops = [("path", p["ordinal"]) for p in remote]
    drops += [("chunk", rec["chunk_id"]) for rec in
              sorted(records, key=order_key, reverse=True)]
    drops += [("path", p["ordinal"]) for p in anchored]
    index = 0
    while before["total_tokens"] > int(budget) and index < len(drops):
        kind, key = drops[index]
        index += 1
        if kind == "path":
            if key not in alive_paths:
                continue
            alive_paths.pop(key)
            dropped_paths.append(key)
            for cid, rec in list(kept.items()):
                ordinals = [o for o in (rec["graph_path_ordinals"] or []) if o in alive_paths]
                if rec["vector_rank"] is None and not ordinals:
                    kept.pop(cid)
                    dropped_chunks.append({"chunk_id": cid, "reason": "支撑路径被裁（远端无关图谱路径）"})
        else:
            if key not in kept:
                continue
            if len(kept) <= 1:
                floor_applied = True
                break
            kept.pop(key)
            dropped_chunks.append({"chunk_id": key, "reason": "按证据优先级从后往前裁文本块"})
        before = recompute()
    if before["total_tokens"] > int(budget) and len(kept) <= 1:
        floor_applied = True
    after = recompute()
    # 归位：把已被裁掉的路径序号从存活记录里剔除（只影响图谱路径载荷与分账，
    # 不影响证据集合本身——被裁路径只由其支撑的图谱侧新增块已在上面出局）
    for cid, rec in kept.items():
        rec["graph_path_ordinals"] = [o for o in (rec["graph_path_ordinals"] or [])
                                      if o in alive_paths]
        if not rec["graph_path_ordinals"]:
            rec["first_path_key"] = None
    return {
        "budget": int(budget),
        "before": initial,
        "before_last_step": before,
        "after": after,
        "dropped_paths": dropped_paths,
        "dropped_chunks": dropped_chunks,
        "records": [rec for rec in records if rec["chunk_id"] in kept],
        "paths": [alive_paths[o] for o in sorted(alive_paths)],
        "budget_exceeded": bool(after["total_tokens"] > int(budget)),
        "budget_floor_applied": floor_applied,
        "rule": trim_rule_text(g),
    }


# ---------------------------------------------------------------------------
# 七、第④步：保留 K 个文本块（先于 D／E 分组排序）
# ---------------------------------------------------------------------------
def evidence_priority_key(record, k: int, g: int, layer2_positions=None) -> tuple:
    """"分层保留顺序"的排序键（第③步裁剪、第④步截取、第⑤步呈现共用；2026-09-27 裁定）。

    四档（数值即先后；`k`＝保留上限 K，`g`＝图谱侧保留份额，`layer2_positions`＝第二层成员的
    `chunk_id → 位次` 映射，由 `plan_graph_layer()` 算一次后传入）：

    * 第一层（`LAYER1_VECTOR_TIER`）：向量侧块且 `vector_rank ≤ K − g`，按原始排名升序；
    * 第二层（`LAYER2_GRAPH_TIER`）：图谱侧新增块（没有向量排名）中按**对问题的向量相似度**
      降序、并列按 `chunk_id` 升序取前 `g` 个，按取中的位次排序；
    * 第三层（`LAYER3_VECTOR_FILL_TIER`）：向量侧块且 `vector_rank > K − g`，按原始排名升序回填；
    * 尾部（`LEFTOVER_GRAPH_TIER`）：未被第二层取到的图谱侧新增块，按原路径出现顺序。

    **g = 0 的退化行为**：`K − g = K`、第二层名额为 0，于是向量侧全部按原始排名升序在前、
    图谱侧新增块按原路径出现顺序追加在后——与**原字面口径**（`legacy_priority_key`，2026-09-27
    修订前的实现）逐题同序；这是"g=0 退化为原口径"这一自查的依据。裁剪从尾部往前、
    第④步取前 K 个、第⑤步 D 组的呈现顺序都用本键。
    """
    g = max(0, int(g))
    cut = int(k) - g
    rank = record.get("vector_rank")
    if rank is not None:
        rank = int(rank)
        if cut > 0 and rank <= cut:
            return (LAYER1_VECTOR_TIER, rank, 0, int(record["chunk_id"]))
        return (LAYER3_VECTOR_FILL_TIER, rank, 0, int(record["chunk_id"]))
    position = (layer2_positions or {}).get(int(record["chunk_id"]))
    if position is not None:
        return (LAYER2_GRAPH_TIER, int(position), 0, int(record["chunk_id"]))
    first = record.get("first_path_key") or (10 ** 9, 0)
    return (LEFTOVER_GRAPH_TIER, int(first[0]), int(first[1]), int(record["chunk_id"]))


def legacy_priority_key(record) -> tuple:
    """**原字面口径**的排序键（2026-09-27 修订前的实现，逐字保留原样）。

    向量侧在前（按原始排名升序、并列按 `chunk_id`），图谱侧新引入的文本块按其在路径上的
    出现顺序（首条支撑路径的序号 → 该路径上的关系序号 → `chunk_id`）追加在后。

    本函数**不参与任何实际排序**：只在 `--selftest` 的自查「g = 0 退化为原口径」与修订前后的
    回归比对里作为参照实现（对照 `evidence_priority_key(..., g=0)`）。
    """
    if record.get("vector_rank") is None:
        first = record.get("first_path_key") or (10 ** 9, 0)
        return (LEGACY_GRAPH_TIER, int(first[0]), int(first[1]), int(record["chunk_id"]))
    return (LEGACY_VECTOR_TIER, int(record["vector_rank"]), 0, int(record["chunk_id"]))


def plan_graph_layer(records, k: int, g: int) -> dict:
    """"第二层"名额（第③／④／⑤步共用的同一份映射）：图谱侧新增块按**对问题的向量相似度**
    降序、并列按 `chunk_id` 升序，**至多取 g 个**。

    相似度是索引里已有的对问题相似度（`question_similarity`，由 `full_pool_similarities()` 挂上），
    不新增模型、不新增外部调用；取不到分数的块按确定性规则排到最后（理论上不会出现——检索池
    与文本块表同为 5018 条）。
    """
    g = max(0, int(g))
    graph_only = [rec for rec in records if rec.get("vector_rank") is None]

    def order_of(rec):
        similarity = rec.get("question_similarity")
        if similarity is None:
            return (1, 0.0, int(rec["chunk_id"]))
        return (0, -float(similarity), int(rec["chunk_id"]))

    ordered = sorted(graph_only, key=order_of)
    layer2 = ordered[:g] if g > 0 else []
    return {"k": int(k), "g": g, "cut": int(k) - g, "graph_only_count": len(graph_only),
            "layer2_ids": [int(rec["chunk_id"]) for rec in layer2],
            "layer2_positions": {int(rec["chunk_id"]): index
                                 for index, rec in enumerate(layer2)}}


def retention_key(k: int, g: int, layer2_positions=None):
    """第③／④／⑤步共用的**同一个**排序键（绑定 K／g 与第二层名额后的可调用对象）。"""
    return functools.partial(evidence_priority_key, k=int(k), g=int(g),
                             layer2_positions=layer2_positions or {})


def retention_breakdown(evidence, plan: dict, by_id) -> dict:
    """最终证据集合按分层的逐条归属（内部字段，只供 `--selftest` 打印；落盘前剔除）。"""
    layer2 = set(plan["layer2_ids"])
    cut = int(plan["cut"])
    layers = {"layer1_vector_top": [], "layer2_graph_new": [],
              "layer3_vector_fill": [], "leftover_graph": []}
    for chunk_id in evidence:
        record = by_id[int(chunk_id)]
        if record.get("vector_rank") is None:
            key = "layer2_graph_new" if int(chunk_id) in layer2 else "leftover_graph"
            layers[key].append(int(chunk_id))
        elif cut > 0 and int(record["vector_rank"]) <= cut:
            layers["layer1_vector_top"].append(int(chunk_id))
        else:
            layers["layer3_vector_fill"].append(int(chunk_id))
    return {"k": int(plan["k"]), "g": int(plan["g"]), "cut": int(plan["cut"]),
            "layer2_candidates": list(plan["layer2_ids"]), **layers}


def keep_top_k(trimmed: dict, k: int, g: int, layer2_positions=None) -> dict:
    """第④步：按**分层保留顺序**保留 K 个文本块（**必须在 D／E 分组排序之前**；候选不足 K 也不删题）。

    返回里同时给出"空缺记未命中"的账：`precision_denominator = K`、`vacant = K − M`。
    排序键与第③步裁剪、第⑤步呈现共用（见 `evidence_priority_key`）；`g = 0` 时键与
    `legacy_priority_key` 同序，即退化为"按固定原始顺序取前 K 个"的原口径。
    """
    records = list(trimmed["records"])
    if len(records) <= int(k):
        return {"records": records, "dropped": [],
                "candidates": len(records), "kept": len(records), "k": int(k),
                "precision_fill": {"denominator": int(k), "candidates": len(records),
                                   "vacant": int(k) - len(records),
                                   "note": "候选不足 K：空缺位置记未命中，题目保留"},
                "note": "候选数不超过 K：全部保留（不因候选少而删题）"}
    ordered = sorted(records, key=retention_key(k, g, layer2_positions))
    kept, dropped = ordered[:int(k)], ordered[int(k):]
    return {"records": kept, "dropped": [rec["chunk_id"] for rec in dropped],
            "candidates": len(records), "kept": len(kept), "k": int(k),
            "precision_fill": {"denominator": int(k), "candidates": len(kept),
                               "vacant": 0,
                               "note": "候选数不少于 K：分母恒为 K（检索指标在 metrics.py 计算）"},
            "note": ("按固定原始顺序取前 K 个（截取先于分组排序）" if int(g) <= 0 else
                     "按分层保留顺序取前 K 个（第一层向量侧前 K−g 个 → 第二层图谱侧新增块"
                     "至多 g 个 → 第三层向量侧剩余候选回填；截取先于分组排序；g=%d）" % int(g))}


# ---------------------------------------------------------------------------
# 八、第⑤步：呈现顺序、图谱路径载荷、逐题编排
# ---------------------------------------------------------------------------
def fixed_original_order(records, path_records, k: int, g: int, layer2_positions=None) -> list:
    """D 组的固定顺序＝**分层保留顺序**（与第③步裁剪、第④步截取用的是同一个排序键）。

    第一层向量侧按原始排名升序在前，第二层图谱侧新增块按对问题的向量相似度降序居中
    （至多 g 个），第三层向量侧剩余候选按原始排名升序回填，尾部为未被第二层取到的图谱侧
    新增块；`g = 0` 时退化为"向量侧在前、图谱侧新增块按路径出现顺序追加在后"的原口径。
    （`path_records` 只作签名一致之用。）
    """
    return sorted(records, key=retention_key(k, g, layer2_positions))


def evidence_sort_factors(graph, record, seeds, documents, chunks) -> dict:
    """E 组排序的四个可解释因素（取值域＝`config.EVIDENCE_SORT_KEYS`，硬约束 9／非目标 9）。"""
    seed_names = set()
    for nid in seeds:
        node = graph.nodes.get(nid) or {}
        for field in ("stock_code", "name", "short_name", "aliases"):
            value = str(node.get(field) or "").strip()
            if not value:
                continue
            for token in value.split("|"):
                token = token.strip()
                if token:
                    seed_names.add(token)
    doc = documents.get(int(record["doc_id"])) or {}
    company_text = "%s %s" % (doc.get("company_list") or "", doc.get("subject_companies") or "")
    chunk_text = str((chunks.get(record["chunk_id"]) or {}).get("content") or "")
    entity_match = 0
    if record.get("graph_path_ordinals"):
        entity_match = 0
    elif any(name and (name in company_text or name in chunk_text) for name in seed_names):
        entity_match = 0
    else:
        entity_match = 1
    evidence_type = 0 if record.get("graph_path_ordinals") else 1
    publish = str(doc.get("publish_time") or "").strip()
    publish_rank = -int(publish.replace("-", "")) if publish[:4].isdigit() else 0
    relation = (record.get("graph_relations") or [""])[0]
    return {"entity_match": entity_match, "evidence_type": evidence_type,
            "source_publish_time": publish, "graph_relation_type": relation,
            "publish_rank": publish_rank}


def order_evidence(graph, records, path_records, enabled: bool, seeds, documents,
                   chunks, k: int, g: int, layer2_positions=None) -> dict:
    """第⑤步的呈现顺序：D 组固定原始顺序；E 组**只读集合、只改顺序**（单变量）。

    E 组的排序键依次取 `config.EVIDENCE_SORT_KEYS` 的四个因素（实体匹配度 → 证据类型 →
    来源发布时间 → 图谱关系类型），最后用 `chunk_id` 升序破并列；不使用任何学习型排序器、
    外部模型、权重或阈值。
    """
    base = fixed_original_order(records, path_records, k, g, layer2_positions)
    if not enabled:
        return {"order": [rec["chunk_id"] for rec in base], "records": base,
                "rule": ("D 组固定原始顺序（向量原始排名升序在前，图谱侧新增块按路径出现顺序追加在后）"
                         if int(g) <= 0 else
                         "D 组分层保留顺序（向量侧前 K−g 个 → 图谱侧新增块按对问题的向量相似度"
                         "降序至多 g 个 → 向量侧剩余候选回填；g=%d）" % int(g)),
                "factors": None}
    decorated = []
    for record in base:
        factors = evidence_sort_factors(graph, record, seeds, documents, chunks)
        decorated.append((factors["entity_match"], factors["evidence_type"],
                          factors["publish_rank"], factors["graph_relation_type"],
                          int(record["chunk_id"]), record, factors))
    decorated.sort(key=lambda item: item[:5])
    ordered = [item[5] for item in decorated]
    return {"order": [rec["chunk_id"] for rec in ordered], "records": ordered,
            "rule": "E 组只读集合、只改顺序（四个可解释因素）",
            "factors": [{"chunk_id": item[5]["chunk_id"], **item[6]} for item in decorated],
            "keys": list(config.EVIDENCE_SORT_KEYS)}


def build_answer_graph_payload(graph, records, path_records, depth: int) -> dict:
    """返回能**原样塞进 `answer.graph_path`** 的载荷（硬约束 19；《10》第4.6.9节）。

    * 使用了图谱扩展（1／2 跳，即 B～E 组）但**没有任何路径进最终证据集合**时，
      按"未使用图谱扩展"处理并给显式标记（不编造路径）；
    * 载荷＝路径列表（每条关系给出 `relation`／`direction`／对端节点标识，以及除
      `EVIDENCED_BY` 外的三项证据属性）＋ 事件三元组（去重后各计一次）。
    """
    kept_paths = retained_path_records(records, path_records)
    if int(depth) <= 0 or not kept_paths:
        marker = GraphQuery.not_used_graph_marker()
        return {"graph_used": False, "graph_path": marker["graph_path"], "event_triples": [],
                "note": marker["note"], "reason": ("检索深度为 0" if int(depth) <= 0
                                                   else "图谱侧没有路径进入最终证据集合")}
    payloads = [graph.graph_path_payload(path) for path in kept_paths]
    event_ids = sorted({eid for path in kept_paths for eid in path["events"]})
    return {"graph_used": True, "depth": int(depth), "graph_path": payloads,
            "event_triples": [event_triple(graph, eid) for eid in event_ids],
            "note": "路径列表与事件三元组计入 Context Token Budget，不计入 K"}


def run_question(question_row, switches, graph, searcher, chunks, documents,
                 n: int, k: int, budget: int, g: int, vector_cache: dict,
                 graph_cache: dict | None = None, full_pool_cache: dict | None = None) -> dict:
    """跑完五步契约的一题（返回一条 trace 记录；耗时只回传、不落盘）。"""
    if graph_cache is None:
        graph_cache = {}
    if full_pool_cache is None:
        full_pool_cache = {}
    g = int(g)
    timings = {}
    cid = question_row["qid"]
    # ---- ① 两路取候选
    t0 = time.time()
    cache_key = (cid, int(n))
    if cache_key not in vector_cache:
        vector_cache[cache_key] = collect_vector_candidates(searcher, question_row["question"], n)
    vector_side = vector_cache[cache_key]
    timings["vector_seconds"] = time.time() - t0

    entities = resolve_question_entities(graph, question_row["question"])
    types = question_event_types(question_row["question"])
    t1 = time.time()
    graph_key = (cid, int(switches["graph_depth"]), tuple(types), tuple(entities["seeds"]))
    if graph_key not in graph_cache:
        graph_cache[graph_key] = collect_graph_candidates(
            graph, entities["seeds"], types, switches["graph_depth"], chunks)
    graph_side = graph_cache[graph_key]
    timings["graph_seconds"] = time.time() - t1

    t2 = time.time()
    if switches["time_filter"]:
        filter_record = apply_time_filter(graph, graph_side, question_row, chunks)
    else:
        filter_record = keep_all_graph_candidates(graph_side)
    timings["filter_seconds"] = time.time() - t2
    filtered_graph = graph_candidates_after_filter(graph_side, filter_record)

    # ---- ② 合并去重（未过滤与过滤后各算一次：逐题差集的来源）
    t3 = time.time()
    merged_all = merge_candidates(vector_side["rows"], graph_side["candidates"], chunks)
    merged = merge_candidates(vector_side["rows"], filtered_graph, chunks)
    timings["merge_seconds"] = time.time() - t3

    unfiltered_ids = sorted(merged_all["order"])
    filtered_ids = sorted(merged["order"])
    diff_removed = sorted(set(unfiltered_ids) - set(filtered_ids))
    diff_added = sorted(set(filtered_ids) - set(unfiltered_ids))

    # ---- ③ 裁剪到预算（不使用排序结果）
    # 只把"过滤后仍在候选集合里的块"所引用的路径交给裁剪：被时间过滤掉的路径不参与分账，
    # 也不会出现在 trace 的丢路径清单里（它们不是被预算裁掉的）。
    referenced = {o for rec in merged["records"] for o in (rec["graph_path_ordinals"] or [])}
    relevant_paths = [p for p in graph_side["paths"] if p["ordinal"] in referenced]

    # 第③／④／⑤步共用的「分层保留顺序」：第二层名额只在本题的**过滤后合并候选**上算一次。
    # g=0 时不算第二层、也不取全池分数（与修订前的调用行为一致）。
    if g > 0:
        graph_only_records = [rec for rec in merged["records"] if rec["vector_rank"] is None]
        if graph_only_records:
            attach_question_similarity(
                graph_only_records,
                full_pool_similarities(searcher, question_row["question"], full_pool_cache))
    plan = plan_graph_layer(merged["records"], k, g)
    order_key = retention_key(k, g, plan["layer2_positions"])
    t4 = time.time()
    trimmed = trim_to_budget(merged["records"], relevant_paths, graph, chunks, budget, g, order_key)
    timings["trim_seconds"] = time.time() - t4

    # ---- ④ 保留 K（先于分组排序）
    t5 = time.time()
    kept = keep_top_k(trimmed, k, g, plan["layer2_positions"])
    timings["keep_k_seconds"] = time.time() - t5

    # ---- ⑤ 呈现顺序、图谱路径载荷
    t6 = time.time()
    ordered = order_evidence(graph, kept["records"], trimmed["paths"],
                             switches["evidence_sort"], entities["seeds"], documents, chunks,
                             k, g, plan["layer2_positions"])
    payload = build_answer_graph_payload(graph, kept["records"], trimmed["paths"],
                                         switches["graph_depth"])
    token_account = account_tokens(kept["records"], trimmed["paths"], graph, chunks)
    timings["order_seconds"] = time.time() - t6

    evidence = [int(c) for c in ordered["order"]]
    final_by_id = {rec["chunk_id"]: rec for rec in kept["records"]}
    graph_in_final = sorted(cid for cid in evidence
                            if final_by_id[cid]["vector_rank"] is None)
    dual_in_final = sorted(cid for cid in evidence
                           if len(final_by_id[cid]["hit_by"]) == 2)
    record = {
        "schema": SCHEMA,
        "qid": cid, "question": question_row["question"],
        "group": switches["_group"], "switches": {key: switches[key] for key in SWITCH_NAMES},
        "n": int(n), "k": int(k), "context_token_budget": int(budget),
        "priority_rule": priority_rule_text(k, g),
        # 内部字段：本条最终证据集合按分层的逐条归属（只供 --selftest 打印；落盘前剔除）
        "_retention": retention_breakdown(evidence, plan, final_by_id),
        "segments": {
            "① 两路取候选": {
                "vector": {"input_questions": 1, "n": int(n),
                           "output_candidates": len(vector_side["rows"]),
                           "rank_range": [1, len(vector_side["rows"])] if vector_side["rows"] else []},
                "graph": {"input_seeds": len(entities["seeds"]),
                          "input_event_types": types,
                          "output_paths": len(graph_side["paths"]),
                          "output_candidates": len(graph_side["candidates"]),
                          "g_calls": graph_side["calls"], "g_codes": graph_side["codes"]},
                "entity_resolution": {"seeds": entities["seeds"],
                                      "by_label": entities["by_label"],
                                      "matches": entities["matches"],
                                      "excluded_document_matches":
                                          entities["excluded_document_matches"],
                                      "event_types": types},
                "time_filter": {key: filter_record[key] for key in
                                ("branch", "enabled", "g6_called", "window", "note")},
            },
            "② 合并去重": {"input_vector": merged["counts"]["vector"],
                           "input_graph": merged["counts"]["graph"],
                           "output_union": merged["counts"]["union"],
                           "dual_hit": merged["counts"]["dual_hit"],
                           "graph_only": merged["counts"]["graph_only"],
                           "rule": "集合并集：一个文本块只算一个证据，不重复计数、不加分"},
            "③ 裁剪到预算": {"input": trimmed["before"]["text_chunks"],
                             "output": trimmed["after"]["text_chunks"],
                             "dropped_paths": len(trimmed["dropped_paths"]),
                             "dropped_chunks": len(trimmed["dropped_chunks"]),
                             "token_account": {"before": trimmed["before"],
                                               "after": trimmed["after"]},
                             "budget_exceeded": trimmed["budget_exceeded"],
                             "budget_floor_applied": trimmed["budget_floor_applied"],
                             "rule": trimmed["rule"]},
            "④ 保留 K": {"input": kept["candidates"], "output": kept["kept"], "k": int(k),
                         "dropped_by_k": kept["dropped"], "note": kept["note"]},
            "⑤ 最终证据集合": {"output": len(evidence), "order": evidence,
                                "graph_payload_used": payload["graph_used"],
                                "presentation_rule": ordered["rule"]},
        },
        "graph_calls": graph_side["calls"],
        "graph_audit": graph_side["audit"],
        "graph_events": graph_side["events"],
        "graph_path_count": len(graph_side["paths"]),
        "time_filter": filter_record,
        "g6_chunk_id_diff": (filter_record["g6"]["chunk_id_diff"]
                             if filter_record["g6"] else []),
        "candidates_unfiltered": unfiltered_ids,
        "candidates_filtered": filtered_ids,
        "candidate_diff_removed": diff_removed,
        "candidate_diff_added": diff_added,
        "candidate_diff_counts": {"removed": len(diff_removed), "added": len(diff_added)},
        "candidate_diff_measurable": bool(diff_removed or diff_added),
        "evidence": evidence,
        # 与 T10 的 metrics.py 对接的同一份集合（该模块按 `final_evidence_chunk_ids` 等
        # 字段名读取逐题留痕；这里给出一份显式别名，避免两边字段名对不上）
        "final_evidence_chunk_ids": evidence,
        "evidence_size": len(evidence),
        "graph_evidence_in_final": graph_in_final,
        "graph_evidence_in_final_count": len(graph_in_final),
        "dual_hit_in_final": dual_in_final,
        "graph_payload": payload,
        "token_account": token_account,
        "precision_fill": {**kept["precision_fill"], "k": int(k),
                           "evidence_size": len(evidence)},
        "checks": {"evidence_unique": len(evidence) == len(set(evidence)),
                   "candidates_unique": len(filtered_ids) == len(set(filtered_ids)),
                   "within_budget": not trimmed["budget_exceeded"],
                   "kept_le_k": len(evidence) <= int(k)},
        "timings": timings,                       # 只回传；落盘前剔除（trace 不含耗时）
    }
    if switches["graph_depth"] > 0 and not graph_in_final:
        record["structural_note"] = (
            "本题最终证据集合中没有『图谱侧新增块』：在 N ≥ K 且预算至少能容纳 K 个文本块时，"
            "固定原始顺序的前 K 个位置由向量侧占满（已知结构性口径，见《19》与交付报告的登记项）"
            if int(g) <= 0 else
            "本题最终证据集合中没有『图谱侧新增块』：本题图谱侧新增候选为空，或第二层（至多 g 个）"
            "在预算裁剪中被先裁掉（分层保留顺序见《10》第4.6.4节～第4.6.6节；g=%d）" % int(g))
    return record


def strip_timings(record: dict) -> dict:
    """落盘前剔除耗时与内部字段（参与逐字节比对的文件不得含耗时与时间戳）。

    内部字段指以 `_` 开头的键（如 `_retention`：分层逐条归属，只在 `--selftest` 里打印）。
    `g = 0` 时 trace 的记录内容与修订前逐字节一致——这正是"退化"的判据之一。
    """
    return {key: value for key, value in record.items()
            if key != "timings" and not key.startswith("_")}


# ---------------------------------------------------------------------------
# 九、逐题编排
# ---------------------------------------------------------------------------
class PipelineRunner:
    """五步契约的执行器：一次加载（向量检索组件 ＋ 内存图 ＋ 三张表），多次逐题运行。"""

    def __init__(self, graph=None, searcher=None, chunks=None, documents=None,
                 verbose=True):
        self.verbose = bool(verbose)
        self.graph = graph if graph is not None else default_graph()
        self.chunks = chunks if chunks is not None else load_chunks()
        self.documents = documents if documents is not None else load_documents()
        self.searcher = searcher
        self.vector_cache = {}
        self.graph_cache = {}
        self.full_pool_cache = {}          # 第二层排序用的全池相似度（按问题缓存复用）
        self.load_seconds = {"graph": 0.0, "vector": 0.0}

    def ensure_searcher(self):
        if self.searcher is None:
            t0 = time.time()
            self.searcher = VectorSearcher(verbose=self.verbose)
            self.load_seconds["vector"] = time.time() - t0
        return self.searcher

    def run(self, questions, switches, n: int, k: int, budget: int, g: int) -> dict:
        self.ensure_searcher()
        switch_values = dict(switches["switches"])
        switch_values["_group"] = switches["group"]
        records = []
        t0 = time.time()
        for row in questions:
            records.append(run_question(row, switch_values, self.graph, self.searcher,
                                        self.chunks, self.documents, n, k, budget, g,
                                        self.vector_cache, self.graph_cache,
                                        self.full_pool_cache))
        return {"records": records, "switches": switches, "n": int(n), "k": int(k),
                "budget": int(budget), "g": int(g), "seconds": time.time() - t0}


def summarize(records) -> dict:
    """汇总：每题最终集合大小、预算占用、是否可测（差集非空）。"""
    rows = []
    for rec in records:
        rows.append({
            "qid": rec["qid"], "evidence_size": rec["evidence_size"],
            "k": rec["k"], "candidates_filtered": len(rec["candidates_filtered"]),
            "tokens": rec["token_account"]["total_tokens"],
            "budget": rec["context_token_budget"],
            "within_budget": rec["checks"]["within_budget"],
            "measurable": rec["candidate_diff_measurable"],
            "diff_removed": rec["candidate_diff_counts"]["removed"],
            "diff_added": rec["candidate_diff_counts"]["added"],
        })
    measurable = sum(1 for row in rows if row["measurable"])
    return {"per_question": rows, "questions": len(rows),
            "measurable_questions": measurable,
            "not_measurable_questions": [row["qid"] for row in rows if not row["measurable"]],
            "graph_evidence_questions": sum(1 for rec in records
                                            if rec["graph_evidence_in_final_count"] > 0),
            "graph_evidence_total": sum(rec["graph_evidence_in_final_count"] for rec in records),
            "mean_evidence_size": (sum(row["evidence_size"] for row in rows) / len(rows)
                                   if rows else 0.0)}


# ---------------------------------------------------------------------------
# 十、四条可执行断言（表 18-E；`--selftest` 真跑）
# ---------------------------------------------------------------------------
def assert_dedup(records) -> dict:
    """断言 3：同一 `chunk_id` 只算一个证据（`len(集合) == len(set(集合))`）。"""
    per_question, ok = [], True
    for rec in records:
        evidence = list(rec["evidence"])
        candidates = list(rec["candidates_filtered"])
        unique = len(evidence) == len(set(evidence))
        candidates_unique = len(candidates) == len(set(candidates))
        ok = ok and unique and candidates_unique
        per_question.append({"qid": rec["qid"], "evidence_size": len(evidence),
                             "evidence_unique": unique,
                             "candidates_size": len(candidates),
                             "candidates_unique": candidates_unique,
                             "evidence": evidence})
    return {"ok": bool(ok), "per_question": per_question,
            "rule": "对任一输出断言 len(集合) == len(set(集合))"}


def construct_dual_hit_case(runner, questions, switches, n: int, k: int, budget: int) -> dict:
    """断言 3 的**有意构造**：让两路命中同一个文本块，断言它只出现一次且无额外加分。

    构造方式（确定性）：取第一题跑出的图谱侧候选里排在最前的一个 `chunk_id`，把它**注入**
    一条假的向量候选（`vector_rank = 1`、`similarity = 0.5`），再走一遍合并去重；断言
    该 `chunk_id` 在合并结果里只出现一次、`hit_by = ["graph","vector"]`，且 `similarity`
    与 `vector_rank` 与注入值**逐位相同**（没有额外加分、也没有被改写）。
    """
    depth = int(switches["switches"]["graph_depth"])
    detail = {"constructed": False, "depth": depth}
    if depth <= 0:
        detail["note"] = "构造用分组的图谱深度为 0，本题型不产生图谱侧候选"
        return {"ok": False, "detail": detail,
                "rule": "两路命中同一 chunk：只保留一条、不重复计数、不加分"}
    picked = None
    for row in questions:
        entities = resolve_question_entities(runner.graph, row["question"])
        types = question_event_types(row["question"])
        side = collect_graph_candidates(runner.graph, entities["seeds"], types, depth,
                                        runner.chunks)
        if side["candidates"]:
            picked = (row, side)
            break
    if picked is None:
        detail["note"] = "题集里没有图谱侧候选，构造失败"
        return {"ok": False, "detail": detail,
                "rule": "两路命中同一 chunk：只保留一条、不重复计数、不加分"}
    row, side = picked
    target = sorted(side["candidates"],
                    key=lambda cid: (side["candidates"][cid]["first_key"], cid))[0]
    detail.update({"qid": row["qid"], "constructed": True, "chunk_id": int(target),
                   "graph_candidate_count": len(side["candidates"])})
    fake_vector_row = {"vector_id": -1, "similarity": 0.5, "chunk_id": int(target),
                       "doc_id": int(side["candidates"][target]["doc_id"]),
                       "vector_rank": 1}
    merged = merge_candidates([fake_vector_row], side["candidates"], runner.chunks)
    hits = [rec for rec in merged["records"] if int(rec["chunk_id"]) == int(target)]
    extra = sorted(field for field in (hits[0] if hits else {})
                   if field in ("score", "boost", "weight", "adjusted_similarity"))
    ok = (len(hits) == 1 and hits[0]["hit_by"] == ["graph", "vector"]
          and float(hits[0]["similarity"]) == 0.5
          and int(hits[0]["vector_rank"]) == 1
          and merged["counts"]["union"] == len({rec["chunk_id"] for rec in merged["records"]})
          and not extra)
    detail.update({"entry_count": len(hits),
                   "hit_by": hits[0]["hit_by"] if hits else None,
                   "similarity": hits[0]["similarity"] if hits else None,
                   "vector_rank": hits[0]["vector_rank"] if hits else None,
                   "union_size": merged["counts"]["union"],
                   "dual_hit": merged["counts"]["dual_hit"],
                   "extra_score_fields": extra})
    return {"ok": bool(ok), "detail": detail,
            "rule": "两路命中同一 chunk：只保留一条、不重复计数、不加分"}


def assert_precision_denominator(runner, questions, switches, n: int, k: int,
                                 budget: int, g: int) -> dict:
    """断言 4：`Precision@K` 的分母恒为 K（构造 M < K 的用例；**不删题**）。

    构造方式（确定性、不改单题口径）：把 Context Token Budget 按 `budget // 10` 收紧，
    使实际候选 M 被裁到 K 以下；断言题被保留、`分母 = K`、`空缺 = K − M ≥ 1`。
    """
    small_budget = max(1, int(budget) // 10)
    run = runner.run(questions, switches, n, k, small_budget, g)
    records = run["records"]
    kept_questions = len(records) == len(questions)
    per_question = []
    ok = kept_questions
    for rec in records:
        fill = rec["precision_fill"]
        size = rec["evidence_size"]
        row_ok = (size < int(k) and fill["denominator"] == int(k)
                  and fill["vacant"] == int(k) - size and fill["vacant"] >= 1)
        per_question.append({"qid": rec["qid"], "m_candidates": size, "k": int(k),
                             "denominator": fill["denominator"],
                             "vacant": fill["vacant"], "vacant_ok": row_ok,
                             "question_kept": True})
        ok = ok and row_ok
    return {"ok": bool(ok), "small_budget": small_budget,
            "questions_in": len(questions), "questions_out": len(records),
            "per_question": per_question,
            "rule": "候选不足 K：题目保留、空缺记未命中、Precision@K 的分母恒为 K"}


def assert_c_vs_d(records_c, records_d) -> dict:
    """断言 2：C 与 D 的最终证据集合**可以不同**——逐题打印双向差集与条数。"""
    by_qid_d = {rec["qid"]: rec for rec in records_d}
    per_question, measurable = [], 0
    for rec_c in records_c:
        rec_d = by_qid_d.get(rec_c["qid"])
        if rec_d is None:
            per_question.append({"qid": rec_c["qid"], "error": "D 组缺少该题"})
            continue
        set_c = set(rec_c["candidates_filtered"])
        set_d = set(rec_d["candidates_filtered"])
        removed = sorted(set_c - set_d)
        added = sorted(set_d - set_c)
        is_measurable = bool(removed or added)
        measurable += 1 if is_measurable else 0
        per_question.append({"qid": rec_c["qid"],
                             "unfiltered_minus_filtered": removed,
                             "filtered_minus_unfiltered": added,
                             "count_removed": len(removed), "count_added": len(added),
                             "measurable": is_measurable,
                             "note": "" if is_measurable else "在该题上不可测"})
    return {"ok": measurable >= 1, "measurable_questions": measurable,
            "total_questions": len(per_question), "per_question": per_question,
            "rule": "进入后续对比统计的题必须至少有一个差集非空；差集为空标记为"
                    "「在该题上不可测」"}


def assert_d_equals_e(records_d, records_e) -> dict:
    """断言 1：D 与 E 的最终证据集合逐题相等（成员与大小）——不等即整体失败退出。"""
    by_qid_e = {rec["qid"]: rec for rec in records_e}
    per_question, ok = [], True
    for rec_d in records_d:
        rec_e = by_qid_e.get(rec_d["qid"])
        if rec_e is None:
            per_question.append({"qid": rec_d["qid"], "error": "E 组缺少该题"})
            ok = False
            continue
        set_d, set_e = set(rec_d["evidence"]), set(rec_e["evidence"])
        equal = set_d == set_e and len(rec_d["evidence"]) == len(rec_e["evidence"])
        ok = ok and equal
        per_question.append({"qid": rec_d["qid"], "equal": equal,
                             "size_d": len(rec_d["evidence"]), "size_e": len(rec_e["evidence"]),
                             "set_d": sorted(set_d), "set_e": sorted(set_e),
                             "missing_in_e": sorted(set_d - set_e),
                             "extra_in_e": sorted(set_e - set_d),
                             "order_d": rec_d["evidence"], "order_e": rec_e["evidence"],
                             "order_differs": rec_d["evidence"] != rec_e["evidence"]})
    return {"ok": bool(ok), "per_question": per_question,
            "rule": "对同一输入分别跑 D 组与 E 组，逐题断言 set(D.证据) == set(E.证据) "
                    "且 len(D.证据) == len(E.证据)；任一题不等即整体失败退出"}


def merged_records_for_question(runner, question_row, switches, n: int) -> list:
    """重建某一题的**过滤后**合并候选（只读、复用 runner 的缓存，不改动任何状态）。

    与 `run_question()` 第①②步的取法逐行一致（同一套缓存键、同一个分支判断），因此自查与
    逐层统计看到的就是实际运行看到的那一批候选；本函数不参与任何产出。
    `switches` 既接受 `normalize_switches()` 的返回（`{"group", "switches"}`），也接受
    `run_question()` 用的扁平三开关字典。
    """
    if "switches" in switches:
        switches = dict(switches["switches"])
    searcher = runner.ensure_searcher()
    qid = question_row["qid"]
    cache_key = (qid, int(n))
    if cache_key not in runner.vector_cache:
        runner.vector_cache[cache_key] = collect_vector_candidates(
            searcher, question_row["question"], int(n))
    vector_side = runner.vector_cache[cache_key]
    entities = resolve_question_entities(runner.graph, question_row["question"])
    types = question_event_types(question_row["question"])
    graph_key = (qid, int(switches["graph_depth"]), tuple(types), tuple(entities["seeds"]))
    if graph_key not in runner.graph_cache:
        runner.graph_cache[graph_key] = collect_graph_candidates(
            runner.graph, entities["seeds"], types, switches["graph_depth"], runner.chunks)
    graph_side = runner.graph_cache[graph_key]
    if switches["time_filter"]:
        filter_record = apply_time_filter(runner.graph, graph_side, question_row, runner.chunks)
    else:
        filter_record = keep_all_graph_candidates(graph_side)
    filtered = graph_candidates_after_filter(graph_side, filter_record)
    return merge_candidates(vector_side["rows"], filtered, runner.chunks)["records"]


def assert_g0_degenerates(runner, questions, switches, n: int, k: int) -> dict:
    """自查 5：`g = 0` 时「分层保留顺序」退化为**原字面口径**（`legacy_priority_key`）。

    判据（逐题、用**真实候选集合**，不改单题口径）：

    1. 升序：`sorted(records, key=分层键(g=0))` 与 `sorted(records, key=原字面键)` 的
       `chunk_id` 序列逐元素相同（第④步"取前 K 个"与第⑤步 D 组呈现顺序都用它）；
    2. 降序：两者的**逆序**（第③步裁剪从尾部往前的那个序列）逐元素相同；
    3. 保留 K：两者各自的前 K 个 `chunk_id` 逐元素相同。

    另报告"g=0 时最终保留里有没有图谱侧新增块"这一结构性读数（原口径下应为 0），
    作为"已退化回修订前行为"的正面证据，不参与 ok 判定。
    """
    per_question, ok = [], True
    for row in questions:
        records = merged_records_for_question(runner, row, switches, n)
        new_asc = [rec["chunk_id"] for rec in sorted(records, key=retention_key(k, 0))]
        legacy_asc = [rec["chunk_id"] for rec in sorted(records, key=legacy_priority_key)]
        new_desc = [rec["chunk_id"] for rec in
                    sorted(records, key=retention_key(k, 0), reverse=True)]
        legacy_desc = [rec["chunk_id"] for rec in
                       sorted(records, key=legacy_priority_key, reverse=True)]
        asc_equal = new_asc == legacy_asc
        desc_equal = new_desc == legacy_desc
        keep_equal = new_asc[:int(k)] == legacy_asc[:int(k)]
        graph_only = {rec["chunk_id"] for rec in records if rec["vector_rank"] is None}
        graph_in_keep = sorted(cid for cid in legacy_asc[:int(k)] if cid in graph_only)
        row_ok = bool(asc_equal and desc_equal and keep_equal)
        ok = ok and row_ok
        per_question.append({"qid": row["qid"], "candidates": len(records),
                             "graph_only_candidates": len(graph_only),
                             "asc_equal": asc_equal, "desc_equal": desc_equal,
                             "keep_equal": keep_equal,
                             "graph_only_in_legacy_keep": graph_in_keep,
                             "ok": row_ok})
    return {"ok": bool(ok), "per_question": per_question,
            "rule": "对同一批真实候选集合，分层键（g=0）与原字面键的升序、降序与前 K 个"
                    "逐题逐元素相同——即 g=0 退化为修订前的「固定原始顺序」"}


# ---------------------------------------------------------------------------
# 十一、trace 落盘（固定键序、无时间戳与耗时）
# ---------------------------------------------------------------------------
def write_trace(path: str, records) -> str:
    """写逐题 trace（一行一条、UTF-8 无 BOM、原子替换）；返回文件 SHA-256。"""
    rows = [strip_timings(rec) for rec in records]
    config.write_jsonl(path, rows)
    return config.sha256_file(path)


def trace_path(trace_dir: str, group: str, suffix: str = "") -> str:
    name = "pipeline_trace_%s%s.jsonl" % (group, suffix)
    return os.path.join(trace_dir, name)


def default_out_path() -> str:
    return os.path.join(config.DOCS_DIR, "pipeline_trace.jsonl")


# ---------------------------------------------------------------------------
# 十二、命令行与自证
# ---------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="T4～T7：Top-K 五步契约的端到端实现（两路候选 → 合并去重 → 预算裁剪 → "
                    "保留 K → 呈现顺序与返回载荷）")
    parser.add_argument("--profile", choices=("run", "selftest"), default="run",
                        help="run＝跑题集并落 trace；selftest＝四条断言的逐条自证")
    parser.add_argument("--selftest", action="store_true", help="等价于 --profile selftest")
    parser.add_argument("--question", default=None, help="单题文本（与 --questions 互斥）")
    parser.add_argument("--questions", default=config.QUESTION_FILES["questions"],
                        help="题集 JSONL 路径（默认取 config.QUESTION_FILES['questions']）")
    parser.add_argument("--group", choices=tuple(sorted(config.GROUPS)), default=None,
                        help="A～E 的开关预设（三个开关仍各自独立，可用下面三项单独覆盖）")
    parser.add_argument("--graph-depth", type=int, default=None,
                        choices=config.SWITCH_DOMAINS["graph_depth"],
                        help="图谱扩展深度 0／1／2（独立开关 1／3）")
    parser.add_argument("--time-filter", default=None,
                        help="时间过滤 on／off（独立开关 2／3；D／E 组为 on）")
    parser.add_argument("--evidence-sort", default=None,
                        help="证据排序 on／off（独立开关 3／3；E 组为 on）")
    parser.add_argument("--k", type=int, default=None,
                        help="最终证据集合的文本块上限；缺省取 config.require_fixed('K')")
    parser.add_argument("--n", type=int, default=None,
                        help="向量检索候选数量；缺省取 config.require_fixed('N')")
    parser.add_argument("--budget", type=int, default=None,
                        help="Context Token Budget；缺省取 config.require_fixed("
                             "'context_token_budget')")
    parser.add_argument("--graph-share", type=int, default=None,
                        help="g：图谱侧新增块在最终证据集合中的全局固化份额（0 ≤ g ≤ K；"
                             "与三个开关无关、A～E 五组同值）；缺省取 "
                             "config.require_fixed('graph_retention_share')")
    parser.add_argument("--time-lo", default=None, help="单题的时间闭区间下界（可选）")
    parser.add_argument("--time-hi", default=None, help="单题的时间闭区间上界（可选）")
    parser.add_argument("--limit", type=int, default=None,
                        help="只跑题集前 M 题（小规模先行用；不改变单题口径与结果）")
    parser.add_argument("--out", default=None, help="trace 落点（默认 _工作底稿\\pipeline_trace.jsonl）")
    parser.add_argument("--trace-dir", default=config.DOCS_DIR,
                        help="--selftest 的 trace 落点目录（默认阶段 7 自己的 _工作底稿\\）")
    parser.add_argument("--quiet", action="store_true", help="少打印（仍打印断言与汇总）")
    args = parser.parse_args(argv)
    if args.selftest:
        args.profile = "selftest"
    return args


def _print_segments(record, header=True):
    """打印六段的输入输出条数（小规模先行的对账表）。"""
    seg = record["segments"]
    graph = seg["① 两路取候选"]["graph"]
    filt = seg["① 两路取候选"]["time_filter"]
    merge = seg["② 合并去重"]
    trim = seg["③ 裁剪到预算"]
    keep = seg["④ 保留 K"]
    evidence = seg["⑤ 最终证据集合"]
    if header:
        print("  段次            输入 → 输出")
    print("    ① 向量检索     1 个问题 → %d 条候选（N=%d，排名 1..%d）"
          % (merge["input_vector"], record["n"], merge["input_vector"]))
    print("    ① 图谱查询     %d 个种子 → %d 条路径 / %d 个候选块（G1=%d G2=%d G3=%d G4=%d G5=%d）"
          % (graph["input_seeds"], graph["output_paths"], graph["output_candidates"],
             graph["g_calls"]["G1"], graph["g_calls"]["G2"], graph["g_calls"]["G3"],
             graph["g_calls"]["G4"], graph["g_calls"]["G5"]))
    if filt["enabled"]:
        counts = record["time_filter"]
        print("    └ 时间过滤     图谱 %d → %d（剔除 %d：空值事件 %d／窗口外 %d／无事件可判定 %d）"
              % (graph["output_candidates"], len(counts["kept_chunk_ids"]),
                 len(counts["removed_chunk_ids"]),
                 len(counts["removed_by_reason"]["null_time_event"]),
                 len(counts["removed_by_reason"]["out_of_range_event"]),
                 len(counts["removed_by_reason"]["no_event_time"])))
    else:
        print("    └ 时间过滤     未启用（A／B／C：保留图谱侧全部候选，未调用 G6）")
    print("    ② 合并去重     向量 %d ＋ 图谱 %d → 并集 %d（两路同命中 %d，图谱侧新增 %d）"
          % (merge["input_vector"], merge["input_graph"], merge["output_union"],
             merge["dual_hit"], merge["graph_only"]))
    print("    ③ 裁剪到预算   %d 块 → %d 块（丢路径 %d 条、丢文本块 %d 个；"
          "token %d → %d／预算 %d）"
          % (trim["input"], trim["output"], trim["dropped_paths"], trim["dropped_chunks"],
             trim["token_account"]["before"]["total_tokens"],
             trim["token_account"]["after"]["total_tokens"], record["context_token_budget"]))
    print("    ④ 保留 K       %d 块 → %d 块（K=%d，超出被裁 %d 个）"
          % (keep["input"], keep["output"], keep["k"], len(keep["dropped_by_k"])))
    print("    ⑤ 最终证据     %d 块（呈现顺序 %s）"
          % (evidence["output"], evidence["order"]))


def cmd_run(args) -> int:
    switches = normalize_switches(args.group, args.graph_depth, args.time_filter,
                                  args.evidence_sort)
    sizes = resolve_k_n_budget(args)
    if args.question:
        questions = [normalize_question_row({"qid": "Q01", "question": args.question},
                                            time_lo=args.time_lo, time_hi=args.time_hi)]
    else:
        questions = load_questions(args.questions)
        if args.limit is not None:
            questions = questions[:int(args.limit)]
    runner = PipelineRunner(verbose=not args.quiet)
    t0 = time.time()
    run = runner.run(questions, switches, sizes["n"], sizes["k"], sizes["budget"], sizes["g"])
    summary = summarize(run["records"])
    out_path = args.out or default_out_path()
    sha = write_trace(out_path, run["records"])

    print("=" * 78)
    print("T4～T7 五步契约：%d 题 × 三开关 %s（分组预设 %s）"
          % (len(questions), switches["switches"], switches["group"]))
    print("K=%d  N=%d  Context Token Budget=%d  g=%d（全局固化量）  保留顺序口径：%s"
          % (sizes["k"], sizes["n"], sizes["budget"], sizes["g"],
             priority_rule_text(sizes["k"], sizes["g"])))
    print("=" * 78)
    for record in run["records"]:
        print("\n[%s] %s" % (record["qid"], record["question"]))
        _print_segments(record)
        print("       预算分账：文本块 %d token ＋ 图谱路径 %d ＋ 事件三元组 %d ＝ %d／%d"
              % (record["token_account"]["text_tokens"], record["token_account"]["path_tokens"],
                 record["token_account"]["event_triple_tokens"],
                 record["token_account"]["total_tokens"], record["context_token_budget"]))
        print("       候选差集：未过滤 − 过滤后 %d 个、反向 %d 个 → %s"
              % (record["candidate_diff_counts"]["removed"],
                 record["candidate_diff_counts"]["added"],
                 "可测" if record["candidate_diff_measurable"] else "在该题上不可测"))
        print("       图谱载荷：%s（路径 %d 条、事件三元组 %d 个）"
              % ("已使用" if record["graph_payload"]["graph_used"] else "未使用图谱扩展",
                 len(record["graph_payload"].get("graph_path") or []),
                 len(record["graph_payload"].get("event_triples") or [])))
        print("       图谱侧新增块进入最终集合：%d 个%s"
              % (record["graph_evidence_in_final_count"],
                 "（两路同命中入集 %d 个，不计图谱侧新增）" % len(record["dual_hit_in_final"])
                 if record["dual_hit_in_final"] else ""))
    print("\n汇总：题数 %d、可测 %d、不可测 %s、平均集合大小 %.2f"
          % (summary["questions"], summary["measurable_questions"],
             ",".join(summary["not_measurable_questions"]) or "无",
             summary["mean_evidence_size"]))
    print("      图谱侧新增块进入最终证据集合：%d 个（涉及 %d／%d 题）"
          % (summary["graph_evidence_total"], summary["graph_evidence_questions"],
             summary["questions"]))
    print("trace 落盘：%s（sha256=%s）" % (os.path.abspath(out_path), sha))
    print("耗时（只打印，不落盘）：总 %.2fs（向量加载 %.2fs、图谱加载 %.2fs）；"
          "0 次大语言模型／外部接口调用"
          % (time.time() - t0, runner.load_seconds["vector"], runner.load_seconds["graph"]))
    return 0


def cmd_selftest(args) -> int:
    """四条断言逐条真跑；任一不成立即返回 1（整体失败退出）。"""
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print("  [%s] %s%s" % ("OK  " if ok else "FAIL", name,
                               ("  —— " + detail) if detail else ""))
        return bool(ok)

    sizes = resolve_k_n_budget(args)
    if args.question:
        questions = [normalize_question_row({"qid": "Q01", "question": args.question},
                                            time_lo=args.time_lo, time_hi=args.time_hi)]
    else:
        questions = load_questions(args.questions)
        if args.limit is not None:
            questions = questions[:int(args.limit)]
    switches_c = normalize_switches("C")
    switches_d = normalize_switches("D")
    switches_e = normalize_switches("E")

    print("=" * 78)
    print("T4～T7 Top-K 五步契约自证：%d 题；K=%d  N=%d  Context Token Budget=%d  g=%d"
          % (len(questions), sizes["k"], sizes["n"], sizes["budget"], sizes["g"]))
    print("三个独立开关：graph_depth 0／1／2、time_filter 开／关、evidence_sort 开／关"
          "（不合并成模式字符串；A～E 只是三开关的预设）")
    print("g 是全局固化量（A～E 同值、不进任何开关）：第一层向量侧前 K−g 个 → "
          "第二层图谱侧新增块按对问题的向量相似度降序至多 g 个 → 第三层向量侧剩余候选回填")
    print("=" * 78)

    t_all = time.time()
    runner = PipelineRunner(verbose=not args.quiet)
    runner._case_questions = questions
    runner.ensure_searcher()
    print("\n〇、加载（只读输入）")
    print("  [OK  ] 图谱查询层：%d 节点 / %d 边（图谱导出物 %s）"
          % (len(runner.graph.nodes), len(runner.graph.edges), config.GRAPH_VERSION))
    print("  [OK  ] 文本块表：%d 行（预算分账用 token_count 实测值）" % len(runner.chunks))
    print("  [OK  ] 文档表：%d 行（E 组排序用 publish_time）" % len(runner.documents))

    # ---- 小规模／全集运行：C、D、E 三组（A／B 只用于对照打印）
    print("\n一、五组开关各跑一遍（同一套脚本与参数；向量侧跨组复用同一份候选）")
    runs = {}
    for name, switches in (("A", normalize_switches("A")), ("B", normalize_switches("B")),
                           ("C", switches_c), ("D", switches_d), ("E", switches_e)):
        runs[name] = runner.run(questions, switches, sizes["n"], sizes["k"], sizes["budget"],
                                sizes["g"])
        summary = summarize(runs[name]["records"])
        print("  [OK  ] %s 组 %s：%d 题，最终集合大小 %s，可测 %d／%d"
              % (name, switches["switches"], len(runs[name]["records"]),
                 [row["evidence_size"] for row in summary["per_question"]],
                 summary["measurable_questions"], summary["questions"]))

    print("\n一之补、第一题的六段输入输出条数（小规模先行用的对账口径）")
    _print_segments(runs["D"]["records"][0])

    # ---- 断言 1：D ≡ E
    print("\n二、断言 1：D 与 E 的最终证据集合逐题相等（成员与大小）")
    a1 = assert_d_equals_e(runs["D"]["records"], runs["E"]["records"])
    for row in a1["per_question"]:
        print("      %s  D=%d 块 %s｜E=%d 块 %s｜集合相等=%s｜顺序改变=%s"
              % (row["qid"], row["size_d"], row["set_d"], row["size_e"], row["set_e"],
                 row["equal"], row["order_differs"]))
    check("断言 1：D 与 E 的最终证据集合逐题相等（成员与大小）", a1["ok"],
          "不等题数 %d" % sum(1 for row in a1["per_question"] if not row.get("equal", False)))

    # ---- 断言 2：C 与 D 可以不同（逐题双向差集）
    print("\n三、断言 2：C 与 D 的最终证据集合可以不同（逐题双向差集与条数）")
    a2 = assert_c_vs_d(runs["C"]["records"], runs["D"]["records"])
    for row in a2["per_question"]:
        print("      %s  未过滤−过滤后 %d 个 %s ｜ 过滤后−未过滤 %d 个 %s ｜ %s"
              % (row["qid"], row["count_removed"], row["unfiltered_minus_filtered"],
                 row["count_added"], row["filtered_minus_unfiltered"],
                 "可测" if row["measurable"] else "在该题上不可测"))
    check("断言 2：至少 1 道题差集非空且逐题留痕", a2["ok"],
          "可测 %d／%d 题" % (a2["measurable_questions"], a2["total_questions"]))

    # ---- 断言 3：同一 chunk_id 只算一个证据（含有意构造）
    print("\n四、断言 3：同一 chunk_id 只算一个证据（len(集合) == len(set(集合))）")
    a3 = assert_dedup(runs["D"]["records"])
    for row in a3["per_question"]:
        print("      %s  最终证据 %d 个（唯一=%s）｜过滤后候选 %d 个（唯一=%s）"
              % (row["qid"], row["evidence_size"], row["evidence_unique"],
                 row["candidates_size"], row["candidates_unique"]))
    check("断言 3a：逐题 len(集合) == len(set(集合))", a3["ok"],
          "证据与候选都不重复的题数 %d／%d"
          % (sum(1 for row in a3["per_question"] if row["evidence_unique"]
                 and row["candidates_unique"]), len(a3["per_question"])))
    a3b = construct_dual_hit_case(runner, questions, switches_d, sizes["n"], sizes["k"],
                                  sizes["budget"])
    print("      构造用例：%s" % json.dumps(a3b["detail"], ensure_ascii=False))
    check("断言 3b：两路命中同一 chunk → 只出现一次且无额外加分", a3b["ok"],
          "命中条数=%s、hit_by=%s、similarity=%s、vector_rank=%s"
          % (a3b["detail"].get("entry_count"), a3b["detail"].get("hit_by"),
             a3b["detail"].get("similarity"), a3b["detail"].get("vector_rank")))

    # ---- 断言 4：Precision@K 的分母恒为 K（构造 M < K）
    print("\n五、断言 4：Precision@K 的分母恒为 K（构造 M < K 的用例，题目不删）")
    a4 = assert_precision_denominator(runner, questions, switches_d, sizes["n"], sizes["k"],
                                      sizes["budget"], sizes["g"])
    for row in a4["per_question"]:
        print("      %s  M=%d < K=%d｜分母=%d｜空缺=%d｜题目保留=%s"
              % (row["qid"], row["m_candidates"], row["k"], row["denominator"],
                 row["vacant"], row["question_kept"]))
    check("断言 4：M < K 时题被保留、空缺记未命中、分母恒为 K", a4["ok"],
          "收紧预算 %d → 题数 %d（输入 %d）" % (a4["small_budget"], a4["questions_out"],
                                                a4["questions_in"]))

    # ---- 附加：确定性与 trace 落盘
    print("\n六、附加检查：确定性（同一输入两次运行，trace 逐字节一致）与落盘")
    hashes = {}
    for name in ("C", "D", "E"):
        again = runner.run(questions, normalize_switches(name), sizes["n"], sizes["k"],
                           sizes["budget"], sizes["g"])
        path_a = trace_path(args.trace_dir, name)
        path_b = trace_path(args.trace_dir, name + "_rerun")
        sha_a = write_trace(path_a, runs[name]["records"])
        sha_b = write_trace(path_b, again["records"])
        hashes[name] = {"trace": os.path.relpath(path_a, config.ROOT).replace("\\", "/"),
                        "sha256": sha_a, "rerun_sha256": sha_b, "identical": sha_a == sha_b}
        print("      %s 组：%s\n        sha256=%s\n        重跑 sha256=%s（逐字节一致=%s）"
              % (name, hashes[name]["trace"], sha_a, sha_b, hashes[name]["identical"]))
        check("确定性：%s 组两次运行 trace 逐字节一致" % name, sha_a == sha_b,
              "sha256 %s" % ("相同" if sha_a == sha_b else "不同"))

    # ---- 四条断言的原始输出留痕（确定性：不含耗时与时间戳，可逐字节复跑比对）
    # ---- 附加：分层保留顺序的正面证据（图谱侧新增块确实进入了最终证据集合）
    print("\n七、分层保留顺序的正面证据（g=%d）：最终证据集合按层次的条数" % sizes["g"])
    layer_totals = {}
    for name in ("C", "D"):
        totals = {"layer1_vector_top": 0, "layer2_graph_new": 0,
                  "layer3_vector_fill": 0, "leftover_graph": 0}
        for rec in runs[name]["records"]:
            row = rec["_retention"]
            for key in totals:
                totals[key] += len(row[key])
            print("      %s·%s  第一层（向量侧前 K−g=%d 个）%d 条 ｜ 第二层（图谱侧新增，"
                  "至多 g=%d 个）%d 条%s ｜ 第三层（向量侧回填）%d 条 ｜ 尾部（图谱侧剩余）%d 条"
                  % (name, rec["qid"], row["cut"], len(row["layer1_vector_top"]),
                     row["g"], len(row["layer2_graph_new"]),
                     ("（候选：%s）" % row["layer2_candidates"][:4]
                      if row["layer2_candidates"] else "（本题无图谱侧新增候选）"),
                     len(row["layer3_vector_fill"]), len(row["leftover_graph"])))
        layer_totals[name] = totals
        print("      %s 组合计：第一层 %d 条 ｜ **第二层（图谱侧新增块）%d 条** ｜ 第三层 %d 条 ｜ "
              "尾部 %d 条（%d 题）"
              % (name, totals["layer1_vector_top"], totals["layer2_graph_new"],
                 totals["layer3_vector_fill"], totals["leftover_graph"], len(runs[name]["records"])))
    positive = layer_totals["D"]["layer2_graph_new"] > 0
    print("      正面证据：g=%d 时图谱侧新增块进入最终证据集合 %d 条（C 组 %d 条、D 组 %d 条）→ %s"
          % (sizes["g"], max(layer_totals["C"]["layer2_graph_new"],
                             layer_totals["D"]["layer2_graph_new"]),
             layer_totals["C"]["layer2_graph_new"], layer_totals["D"]["layer2_graph_new"],
             "成立" if positive else "不成立（本题集上没有图谱侧新增候选进入）"))

    # ---- 自查 5：g = 0 退化为原字面口径（分层键 vs 原字面键，逐题三个方向）
    print("\n八、自查：g = 0 退化为原字面口径（分层键 vs 原字面键）")
    a5 = assert_g0_degenerates(runner, questions, switches_d, sizes["n"], sizes["k"])
    for row in a5["per_question"]:
        print("      %s  候选 %d 个（其中图谱侧新增 %d 个）｜升序相同=%s｜降序相同=%s｜"
              "前 K 个相同=%s｜原口径保留里的图谱侧新增 %d 个"
              % (row["qid"], row["candidates"], row["graph_only_candidates"],
                 row["asc_equal"], row["desc_equal"], row["keep_equal"],
                 len(row["graph_only_in_legacy_keep"])))
    check("自查（g=0 退化）：分层键（g=0）与原字面口径的升序／降序／前 K 个逐题逐元素相同",
          a5["ok"], "不一致题数 %d" % sum(1 for row in a5["per_question"] if not row["ok"]))
    g0_run = runner.run(questions, switches_d, sizes["n"], sizes["k"], sizes["budget"], 0)
    g0_summary = summarize(g0_run["records"])
    print("      g=0 实跑（D 组，与修订前同口径）：图谱侧新增块进入最终证据集合 %d 个"
          "（涉及 %d／%d 题）；四项指标与修订前的逐字节比对见交付报告"
          % (g0_summary["graph_evidence_total"], g0_summary["graph_evidence_questions"],
             g0_summary["questions"]))

    # ---- 四条断言的原始输出留痕（确定性：不含耗时与时间戳，可逐字节复跑比对）
    report = {
        "schema": "stage7-pipeline-assertions-1.0",
        "generated_by": "代码/检索/pipeline.py --selftest",
        "questions": [row["qid"] for row in questions],
        "k": sizes["k"], "n": sizes["n"], "context_token_budget": sizes["budget"],
        "graph_retention_share": sizes["g"],
        "priority_rule": priority_rule_text(sizes["k"], sizes["g"]),
        "assertion_1_d_equals_e": a1,
        "assertion_2_c_vs_d_diff": a2,
        "assertion_3a_unique_chunk": a3,
        "assertion_3b_constructed_dual_hit": a3b,
        "assertion_4_precision_denominator": a4,
        "assertion_5_g0_degenerates": a5,
        "retention_layers": {"g": sizes["g"], "totals": layer_totals,
                             "per_question_D": [rec["_retention"] for rec in runs["D"]["records"]],
                             "g0_run_graph_evidence_total": g0_summary["graph_evidence_total"]},
        "group_summaries": {
            name: summarize(runs[name]["records"]) for name in ("A", "B", "C", "D", "E")},
        "trace_sha256": hashes,
    }
    report_path = os.path.join(args.trace_dir, "pipeline_assertions.json")
    config.write_json(report_path, report)
    print("\n断言原始输出留痕：%s（sha256=%s）"
          % (os.path.relpath(report_path, config.ROOT).replace("\\", "/"),
             config.sha256_file(report_path)))

    print("\n" + "=" * 78)
    passed = sum(1 for item in checks if item["ok"])
    print("自证结论：%d／%d 条通过（耗时 %.1fs，只打印到 stdout，产物只落 _工作底稿\\）"
          % (passed, len(checks), time.time() - t_all))
    print("实现裁定：① 深度＝从问题实体出发的最大关系边数；"
          "② D／E 的空值口径含「无事件可判定」的路径一并剔除；③ %s"
          % priority_rule_text(sizes["k"], sizes["g"]))
    print("=" * 78)
    return 0 if passed == len(checks) else 1


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.profile == "selftest":
        return cmd_selftest(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
