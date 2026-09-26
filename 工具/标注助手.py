# -*- coding: utf-8 -*-
"""工具\\标注助手.py —— 第 6 阶段抽取评测集（v2.1）的人工标注工作台。

**它只做四件事，且一件标签都不产生**（离线；不调模型；不预填、不建议、不猜测任何取值）：

| 子命令 | 作用 |
| --- | --- |
| `export` | 把 `dev.jsonl`／`test.jsonl` 展开成**一条一个 `.md` 文件**的标注工作区（`标注工作区\\dev\\DEV-001.md`）。可重复执行，不覆盖已填写的条目 |
| `check`  | 逐条校验已填写的标注，**每个问题都打印证据行**（文件、item_id、字段、值）。有问题时退出码非 0 |
| `merge`  | 把填好的标注写回 `dev.jsonl`／`test.jsonl`（先备份原件；只改 `annotation`，其余字段与字段顺序逐字保留；`status` 改为 `human_annotated`） |
| `stats`  | 按 split 统计覆盖率与各类实体／事件／关系的条数，用来在冻结前看薄类覆盖 |
| `selftest` | 自检（独立复现用）：在**系统临时目录**里走一遍 导出→校验→往返→负向用例，不碰真实文件 |

用法：

```powershell
python 工具\\标注助手.py export
python 工具\\标注助手.py check
python 工具\\标注助手.py stats
python 工具\\标注助手.py merge                 # check 有问题时拒绝写盘，--force 可强写
python 工具\\标注助手.py selftest
```

默认落点（均可用 `--eval-dir`／`--workspace`／`--split` 覆盖）：

* 评测集目录 `--eval-dir`：`阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\`
  （路径由 `代码\\抽取与图谱\\config.py` 的 `DATASET_ROOT` ＋ `DATASET_VERSION` 推出，不写死）。
* 工作区 `--workspace`：上者之下的 `标注工作区\\`，内含 `dev\\`、`test\\`、`_备份\\`。
  该目录整体落在 `.gitignore` 已排除的 `阶段05-数据准备/数据集/` 之下，不入公开仓库
  （见 `标注说明.md` 第一节 的口径）。

## 工作区文件格式（为什么是 `.md` 而不是 `.json`）

一个条目一个 `.md`：**人读的部分是 Markdown，机器读的部分是文件里唯一的 `json` 代码块**。
理由：① 标注是一个「读上下文 → 填结构化槽位」的动作，把 17 个抽样字段与 1.5～5 万字符的
`doc_text` 一起塞进 `.json` 会重演 `.jsonl` 的问题（大、不能折叠、逗号与引号易错）；
② 槽位本身是嵌套结构（`events[].participants[]`），Markdown 表格表达不了，硬塞会造出更难解析的
格式；③ 单一文件即单一事实来源，不存在「`.json` 与渲染 `.md` 谁为准」的同步问题。
因此人读上下文用 Markdown，待填槽位用一个 `json` 块，解析只认这个块（靠 HTML 注释标记定位，
不靠正则猜），也便于 `check` 在写盘前挡住语法错误。

文件结构（`<!-- HANDANN:… -->` 是机器读的锚点，标注时不要删）：

```text
<!-- HANDANN-META: {"schema":…, "item_id":…, "chunk_id":…, "doc_id":…, "text_digest":…} -->
# DEV-001
| 字段 | 值 |            ← item_id／category／publish_time／title／source／url／chunk_id／doc_id／…
---
## 一、待标注文本块（`text`，标注对象）                     ← HANDANN:TEXT 标记包住，quote 只能取自这里
## 二、文档全文（`doc_text`，仅上下文，不是标注对象）
## 三、标注槽位（只改下面这个代码块）                        ← 逐字段的允许值提醒 ＋ 一个 json 块
<!-- HANDANN:ANNOTATION:BEGIN -->
{ "status": "pending_human_annotation", "entities": [], … }   ← 人工只改这里
<!-- HANDANN:ANNOTATION:END -->
```

## 口径来源（只引用、不新立）

* 标注口径：`阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\标注说明.md`（第3节 字段结构、第4节
  「什么算一条」、第5节 8 种事件类型、第6节 9 条关系与 role、第7节 三条公司间关系、第8节 本体边界）。
* 枚举与 schema：`代码\\抽取与图谱\\config.py` 的 `ENTITY_TYPES_FROM_MODEL`／`EVENT_TYPES`／
  `RELATIONS`／`RELATION_SCHEMA`／`ROLES`／`EVIDENCE`／`ISSUED_BY_EVENT_TYPES`／`CONFIDENCE_MIN`／
  `CONFIDENCE_MAX`。**本文件一处枚举都不重抄**（唯一例外：`ontology_boundary_log` 的 `case_type`
  建议取值，config 里没有，只有 `标注说明.md` 第八节 给了，来源在常量处注明）。
* 字段清单：`分层统计.json` → `annotation_schema`（与 `config.py` 同源）。

## `check` 的检查项

任务要求的那几条（前 7 条）＋ 依据协议定义补的 8 条（后者标「协议附加」）：

1. 空 `item_id`／工作区内 `item_id` 重复／文件名与 `item_id` 不一致／`item_id` 不在 jsonl 里。
2. `status` 仍为 `pending_human_annotation` 但槽位非空；或反之（标为完成却四个列表槽位全空、
   `notes` 也没有 `empty_but_checked: true`）。`status` 只认三个值：
   `pending_human_annotation`（未标注）／`human_annotated`（人工标注完成）／
   `auto_annotated`（**模型自动标注**，第 10 阶段的模型参照集）。**`status = auto_annotated`
   时必须带 `provenance`**：缺 `model`／`prompt_version`／`temperature` 任一项即报
   `auto_provenance_missing`——这条守卫的目的是**防止自动标注被当成人工标注**。
3. `entity_type` 不在 5 类里（`Event` 写进 `entities[]` 单独报，见 `标注说明.md` 第3.1节）。
4. `event_type` 不在 8 种里；`relation` 不在 9 条里；`role` 不在 5 个里。
5. 关系（除 `EVIDENCED_BY` 外）缺 `source_doc_id`／`source_chunk_id`／`confidence` 任一
   （键缺失／值为空报 `relation_evidence_missing`，只报这一条）；且 `source_chunk_id`
   必须等于本条自己的 `chunk_id`（一条 = 一个文本块）、`source_doc_id` 必须等于本条
   自己的 `doc_id`（不符报 `relation_doc_mismatch`）。`confidence` 的**取值**与
   `events[].confidence` 复用同一个 `_check_confidence`（单一口径，不再各判一套）：
   `float()` 能解析且在 0.0～1.0 内即通过（`"0.9"` 这类数字字符串照样通过）、非数值或
   越界报 `confidence_range`；`events[].confidence` 的键缺失／空值报 `confidence_empty`。
6. `quote` 去空白后必须是本条 `text` 的**精确子串**（不做模糊匹配、不做编辑距离），
   长度 12～200 字符（`config.EVIDENCE`）。
7. `ontology_boundary_log` 里**把新本体当成「已生效」**的条目（自造关系名／自造实体类型／
   断言「已新增……关系（或实体类型／事件类型／属性）」／复活 `INVOLVES`）——协议要求这类情形
   **只登记、不新增本体**。**只在断言已生效时拒绝**：出现「建议／疑似／待／拟／希望／考虑／
   提请／是否」这类建议或未定语境的同形句一律放行（第八节 允许在 `suggested_handling` 里
   提建议）；「记录／备注」**不算**建议语境——它们只说明「把这个动作登记下来」，
   不能把「已新增……关系，并写入图谱」这类**已生效**断言变成建议。
8. 协议附加：条目必填字段缺失（`annotation_schema` 的字段清单）；`chunk_id` 字段与本条不一致；
   `META` 里的 `text_digest` 与工作区文本块重算的摘要不符（`text_digest_mismatch`；与
   `sampled_field_changed`／`text_changed` 分开：那两条管「文本或抽样字段被改」，这条专管
   「META 摘要被改」）；`confidence` 越界；`event_time`／`times[].value` 不是 `YYYY-MM-DD`
   或 `null`；`entity_ref`／`event_ref` 重复或 `participants[].entity_ref` 悬空；关系端点类型
   不符合 `RELATION_SCHEMA` 的 domain／range；关系端点声明的 `from_label`／`to_label` 必须等于
   该端点实际类型（指向 `entities[]` 时等于该实体的 `entity_type`、指向 `events[]` 时等于
   `Event`，不符报 `relation_label_mismatch`）；`BELONGS_TO` 的 `valid_from`／`valid_to` 允许
   `null`／省略（正文没有日期时视为未知、不许编日期），给了值就必须是 `YYYY-MM-DD`
   （格式非法报 `relation_validity_format`）；`ISSUED_BY` 出现在非政策／监管事件上；
   标注里出现 `data_cutoff_time`（版本级属性，不落任何节点与关系）。

`merge` 会先跑一遍 `check`：有问题就拒绝写盘（`--force` 可越过，但会把问题一并打印）。
**`merge` 拒绝把 `auto_annotated` 写回 `dev.jsonl`／`test.jsonl`**（`merge_refuses_auto`）：
第 6 阶段交付文件的槽位必须保持为空（《15》第八节 的冻结契约），自动标注落在独立产物里
（`阶段05-数据准备\数据集\抽取评测集\v2.1\自动标注\`）。这一条是**硬守卫，`--force` 不放行**，
且不影响 `merge` 的其它行为。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, OrderedDict


# ==========================================================================
# 0. 常量与路径
# ==========================================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_THIS_DIR)

CONFIG_PATH = os.path.join(ROOT, "代码", "抽取与图谱", "config.py")
TOOL_RELPATH = "工具\\标注助手.py"

# 评测集目录：`<数据集根>\抽取评测集\<数据集版本>\`（与 `数据集\v2.1\` 同级；标注说明.md 第一节）。
EVAL_SUBDIR = "抽取评测集"
WORKSPACE_DIRNAME = "标注工作区"
BACKUP_DIRNAME = "_备份"
LEDGER_NAME = "_导出台账.json"
GUIDE_NAME = "说明.md"

PENDING_STATUS = "pending_human_annotation"
# 完成标记。协议只规定了未标注状态（`标注说明.md` 第3节），完成标记本工具定一个并在此登记：
# 全项目现有的消费者（`验收第6阶段.py` 只统计状态分布、`sample_eval_set.py --verify-only` 只断言
# 「恒为 pending」）都不会因它而误判；`sample_eval_set.py --verify-only` 会因此失败——那是**标注已
# 开始的正常后果**，其第五节 第 4 项检查本就只适用于「标注尚未开始」的状态。
COMPLETED_STATUS = "human_annotated"
# 第三个合法 status：**模型自动标注**（第 10 阶段的模型参照集，不是人工金标准）。
# 它与 COMPLETED_STATUS 的区别就是「谁产的」——因此**必须**带 provenance 块；
# `check` 的 `_check_auto_provenance` 就是防「自动标注被当成人工标注」的那道守卫。
# `merge` 另有一条守卫：**拒绝**把 auto_annotated 写回 dev.jsonl／test.jsonl
# （第 6 阶段交付文件的槽位必须保持为空，《15》第八节 的冻结契约）。
AUTO_STATUS = "auto_annotated"
AUTO_PROVENANCE_REQUIRED = ("model", "prompt_version", "temperature")

# `ontology_boundary_log[].case_type` 的建议取值：**config.py 里没有这个枚举**，
# 只有 `标注说明.md` 第八节 给了这一串，故在此处登记来源、不当作本体常量使用。
CASE_TYPES = [
    "event_type_boundary", "relation_boundary", "role_boundary", "company_out_of_scope",
    "relation_insufficient", "time_ambiguous", "chunk_boundary",
]
CASE_TYPES_SOURCE = "标注说明.md 第八节"

# 各类实体的必填属性：**config.py 没有这个表**（它只有 GRAPH["node_columns"] 那个扁平列清单），
# 来源是 `分层统计.json` → `annotation_schema.entities.per_type_fields`＝`标注说明.md` 第3.1节 的表。
# 通用字段 `entity_type`／`entity_ref`／`quote`／`chunk_id` 不在本表里，单独判。
ENTITY_PER_TYPE_FIELDS = {
    "Company": ["stock_code", "company_name", "short_name", "aliases", "exchange"],
    "Person": ["person_id", "person_name", "aliases", "role_title"],
    "Industry": ["industry_code", "industry_name", "level"],
    "Institution": ["institution_id", "institution_name", "institution_type"],
    "Policy": ["policy_id", "policy_name", "issuer", "publish_date"],
}
ENTITY_COMMON_FIELDS = ["entity_type", "entity_ref", "quote", "chunk_id"]

# 机器读锚点（标注时不要删）
META_RE = re.compile(r"<!--\s*HANDANN-META:\s*(\{.*?\})\s*-->", re.S)
MARK_TEXT_BEGIN, MARK_TEXT_END = "<!-- HANDANN:TEXT:BEGIN -->", "<!-- HANDANN:TEXT:END -->"
MARK_ANN_BEGIN, MARK_ANN_END = "<!-- HANDANN:ANNOTATION:BEGIN -->", "<!-- HANDANN:ANNOTATION:END -->"

ITEM_SCHEMA = "stage6-handann-item-1.0"
LEDGER_SCHEMA = "stage6-handann-ledger-1.0"
MERGE_SCHEMA = "stage6-handann-merge-1.0"

TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
WS_RE = re.compile(r"[\s　]+")


def _load_config():
    """按路径载入 `代码\\抽取与图谱\\config.py`（目录名不是合法标识符，故用 spec 载入）。

    config 只 import hashlib／json／os，模块级不联网、不读密钥（`api_key()` 是函数，不在这里调用），
    因此本工具**离线**运行。
    """
    if not os.path.isfile(CONFIG_PATH):
        raise SystemExit("找不到本体参数来源：%s" % CONFIG_PATH)
    spec = importlib.util.spec_from_file_location("stage6_extract_config", CONFIG_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def default_eval_dir(cfg) -> str:
    """评测集目录由 config 的数据集根与版本推出，不在本脚本里写死版本号。"""
    return os.path.join(cfg.DATASET_ROOT, EVAL_SUBDIR, cfg.DATASET_VERSION)


def default_workspace(eval_dir: str) -> str:
    return os.path.join(eval_dir, WORKSPACE_DIRNAME)


# ==========================================================================
# 1. 小工具
# ==========================================================================
def norm_ws(text) -> str:
    """去掉全部空白（含全角空格）。与 `config.EVIDENCE["normalize"]` 同一口径。"""
    return WS_RE.sub("", str(text or ""))


def sha256_hex(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text_digest(text) -> str:
    """文本块的去空白摘要：用来确认工作区里的块与 jsonl 里的块是同一段（抽样字段不许改）。"""
    return sha256_hex(norm_ws(text))


def read_jsonl(path: str):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line, object_pairs_hook=OrderedDict))
    return rows


def dump_line(obj) -> str:
    """与 `sample_eval_set.py` 写盘时的序列化完全一致（默认分隔符、不转义中文）。"""
    return json.dumps(obj, ensure_ascii=False)


def write_text_atomic(path: str, text: str) -> None:
    """原子写：先写同目录临时文件再 os.replace，避免半截文件。"""
    d = os.path.dirname(path)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".handann-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def sget(obj, key, default=None):
    return obj.get(key, default) if isinstance(obj, dict) else default


def show_path(path: str) -> str:
    """证据行里的路径：工作区内的显示相对路径，工作区外的（临时副本）显示绝对路径。"""
    if not path:
        return "（无）"
    try:
        rel = os.path.relpath(path, ROOT)
    except ValueError:
        return path
    return path if rel.startswith("..") else rel


def brief(value, limit: int = 120) -> str:
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    s = s.replace("\n", "\\n").replace("|", "\\|")
    return s if len(s) <= limit else s[:limit] + "…"


def md_cell(value) -> str:
    """表格单元格：竖线转义、换行折成空格（工具\\README.md 编写约定 8：单元格里不要有裸竖线）。"""
    s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return s.replace("\n", " ").replace("|", "\\|").strip() or "（空）"


def fence(text: str, lang: str = "text") -> str:
    """动态围栏长度：正文里若含反引号，围栏加长到比它最长的一串多一个。"""
    n = 3
    for m in re.finditer(r"`+", text or ""):
        n = max(n, len(m.group(0)) + 1)
    f = "`" * n
    return "%s%s\n%s\n%s" % (f, lang, (text or "").rstrip("\n"), f)


def block_between(text: str, begin: str, end: str):
    i = text.find(begin)
    if i < 0:
        return None
    i += len(begin)
    j = text.find(end, i)
    if j < 0:
        return None
    return text[i:j]


def strip_fence(raw: str) -> str:
    lines = raw.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if lines and lines[0].lstrip().startswith("```"):
        lines.pop(0)
    if lines and lines[-1].strip().startswith("```"):
        lines.pop()
    return "\n".join(lines)


# ==========================================================================
# 2. 槽位骨架与逐字段提醒
# ==========================================================================
def empty_annotation() -> OrderedDict:
    """与 jsonl 里 `annotation` 的键序一致的空槽位。"""
    return OrderedDict([
        ("status", PENDING_STATUS),
        ("entities", []),
        ("events", []),
        ("relations", []),
        ("times", []),
        ("ontology_boundary_log", []),
        ("notes", ""),
    ])


def skeleton_json() -> str:
    return json.dumps(empty_annotation(), ensure_ascii=False, indent=2)


def reminders(cfg) -> str:
    """逐字段的允许值提醒。**枚举全部来自 config**，不手抄；也不给任何示例取值。"""
    etypes = "／".join(cfg.ENTITY_TYPES_FROM_MODEL)
    etypes_all = "／".join(cfg.ENTITY_TYPES)
    evtypes = "／".join(cfg.EVENT_TYPES)
    rels = "／".join(cfg.RELATIONS)
    roles = "／".join(cfg.ROLES)
    ev_attrs = "／".join(cfg.EVIDENCE_ATTRS)
    qmin = cfg.EVIDENCE["quote_min_chars"]
    qmax = cfg.EVIDENCE["quote_max_chars"]
    lines = [
        "- `status`：**没填完就别动**（保持 `%s`）；本条填完后改成 `%s`。" % (PENDING_STATUS, COMPLETED_STATUS),
        "- `entities`（数组）：`entity_type` 取 `%s`（共 5 类，本体共 6 类：`%s`）——**`Event` 不写进"
        "这里**，事件一律写 `events[]`；**不新增 Product（产品）／Location（地点）**。每条另填 "
        "`entity_ref`（本条内编号 `E1`／`E2`…，从 1 开始）、`quote`（%d～%d 字符，须逐字出现在下面"
        "「一、」的块里）、`chunk_id`（默认等于本条 chunk_id）。按 `entity_type` 另填必填属性"
        "（见 `标注说明.md` 第3.1节 的表）。" % (etypes, etypes_all, qmin, qmax),
        "- `events`（数组）：`event_type` 取 `%s`（共 8 种，不多不少、不改名、不合并）；填 "
        "`event_ref`（`V1`／`V2`…）、`event_name`、`event_time`（`YYYY-MM-DD`；**正文不能确定到日"
        "就写 `null`，绝不猜测**）、`description`、`confidence`（0.0～1.0）、`participants`"
        "（每项 `{entity_ref, role}`，`role` 取 `%s`；发布／作出方只写 ISSUED_BY 关系，不再写 "
        "PARTICIPATES_IN）、`quote`、`chunk_id`；`event_id` 条目内写 `EVT-<本文件 item_id>-<n>`。"
        "`trigger` 是可选调试字段。" % (evtypes, roles),
        "- `relations`（数组）：`relation` 取 `%s`（共 9 条，方向即语义、不得反向写）；填 `from_label`／"
        "`from_ref`／`to_label`／`to_ref`；**除 `EVIDENCED_BY` 外**必须带 `%s` 三项，且 "
        "`source_chunk_id` 必须等于本条自己的 chunk_id（一条 = 一个文本块），并填 `quote`；"
        "`BELONGS_TO` 另填 `valid_from`／`valid_to`，`PARTICIPATES_IN` 另填 `role`。"
        "**`EVIDENCED_BY` 不标注**（由程序按 doc_id 生成，不携带证据三项）。" % (rels, ev_attrs),
        "- `times`（数组）：`time_type` 取 `event_time`／`valid_from`／`valid_to`；填 `value`"
        "（`YYYY-MM-DD`）与 `quote`。`publish_time` 数据集已给、**不重复标注**；`data_cutoff_time` "
        "是版本级属性、**标注里不得出现**。",
        "- `ontology_boundary_log`（数组）：归不进 8 类事件或 9 条关系时，**只登记、不改本体**。每条填 "
        "`case_id`（`OB-<本文件 item_id>-<n>`）、`case_type`（建议取值见 %s：%s）、`summary`、`quote`、"
        "`chunk_id`、`suggested_handling`（可以写「疑似需要第 10 条关系：……」这类**建议**，但不得把"
        "新关系／新实体类型真的写进 `entities`／`relations`，也不得复活 `INVOLVES`）。"
        % (CASE_TYPES_SOURCE, "／".join(CASE_TYPES)),
        "- `notes`（字符串）：自由文本。本块确实没有任何可标事实时，四个列表槽位保持空列表并在 "
        "`notes` 写 `empty_but_checked: true` 加理由（合法结果，不许为了填满而编造）；跨块证据写 "
        "`cross_chunk_evidence: <chunk_id>`。",
    ]
    return "\n".join(lines)


# ==========================================================================
# 3. 渲染一个条目文件
# ==========================================================================
def render_item(rec, cfg, eval_relpath: str) -> str:
    item_id = rec["item_id"]
    meta = OrderedDict([
        ("schema", ITEM_SCHEMA),
        ("item_id", item_id),
        ("split", rec.get("split")),
        ("chunk_id", rec.get("chunk_id")),
        ("doc_id", rec.get("doc_id")),
        ("text_digest", text_digest(rec.get("text"))),
    ])
    sampling = rec.get("sampling") or {}
    tags = sampling.get("coverage_tags") or []
    rows = [
        ("item_id", rec.get("item_id")),
        ("split", rec.get("split")),
        ("category", rec.get("category")),
        ("publish_time", rec.get("publish_time")),
        ("month", rec.get("month")),
        ("title", rec.get("title")),
        ("source", rec.get("source")),
        ("url", rec.get("url")),
        ("chunk_id", rec.get("chunk_id")),
        ("doc_id", rec.get("doc_id")),
        ("chunk_index", rec.get("chunk_index")),
        ("chunk_count_in_doc", rec.get("chunk_count_in_doc")),
        ("token_count", rec.get("token_count")),
        ("company_list", rec.get("company_list")),
        ("subject_companies", rec.get("subject_companies")),
        ("覆盖标签（抽样，不是标注）", "、".join(tags) if tags else "（无）"),
        ("选块信号分（抽样，不是标注）", sampling.get("chunk_signal_score")),
    ]
    table = "\n".join("| %s | %s |" % (k, md_cell(v)) for k, v in rows)

    note = (
        "<!-- 本文件由 %s export 生成。**只修改「三、标注槽位」的那个 json 块**。\n"
        "     上面 17 项与下面两段文本都是抽取评测集抽样时写下的字段，改了就和 dev.jsonl／test.jsonl "
        "对不上（check 会报）。 -->" % TOOL_RELPATH
    )
    pointer = (
        "> 规则：`%s\\标注说明.md` —— 第3节 字段结构、第4节 什么算一条、第5节 8 种事件类型、"
        "第6节 9 条关系与 role、第7节 三条公司间关系、第8节 本体边界（只登记不新增）。\n"
        "> 单位：**一条 = 一个文本块**；`quote` 只能取自下面「一、」的块，"
        "事实判定可参考「二、」的全文，但证据不许落在别的块上（那种情况写进 `notes`）。"
        % eval_relpath
    )
    return "\n".join([
        "<!-- HANDANN-META: %s -->" % json.dumps(meta, ensure_ascii=False),
        note,
        "",
        "# %s" % item_id,
        "",
        "| 字段 | 值 |",
        "| --- | --- |",
        table,
        "",
        "---",
        "",
        pointer,
        "",
        "---",
        "",
        "## 一、待标注文本块（`text`，**标注对象**；`quote` 只能取自本段）",
        "",
        MARK_TEXT_BEGIN,
        fence(rec.get("text") or ""),
        MARK_TEXT_END,
        "",
        "## 二、文档全文（`doc_text`，**仅作上下文**，不是标注对象）",
        "",
        fence(rec.get("doc_text") or ""),
        "",
        "## 三、标注槽位（只改下面这个代码块）",
        "",
        "允许值提醒（枚举与 `代码\\抽取与图谱\\config.py` 同源）：",
        "",
        reminders(cfg),
        "",
        MARK_ANN_BEGIN,
        "```json",
        skeleton_json(),
        "```",
        MARK_ANN_END,
        "",
    ])


# ==========================================================================
# 4. 解析一个条目文件
# ==========================================================================
def parse_item_file(path: str):
    """返回 (meta, text, annotation, errors)。任一项解析不出来就进 errors。"""
    errors = []
    with open(path, encoding="utf-8") as fh:
        raw = fh.read()

    m = META_RE.search(raw)
    if not m:
        errors.append("缺 HANDANN-META 锚点")
        meta = None
    else:
        try:
            meta = json.loads(m.group(1))
        except ValueError as exc:
            errors.append("HANDANN-META 不是合法 JSON：%s" % exc)
            meta = None

    text_raw = block_between(raw, MARK_TEXT_BEGIN, MARK_TEXT_END)
    text = None if text_raw is None else strip_fence(text_raw)
    if text_raw is None:
        errors.append("缺 HANDANN:TEXT 锚点")

    ann_raw = block_between(raw, MARK_ANN_BEGIN, MARK_ANN_END)
    annotation = None
    if ann_raw is None:
        errors.append("缺 HANDANN:ANNOTATION 锚点")
    else:
        body = strip_fence(ann_raw)
        try:
            annotation = json.loads(body, object_pairs_hook=OrderedDict)
        except ValueError as exc:
            errors.append("标注块的 json 不合法：%s" % exc)
    if annotation is not None and not isinstance(annotation, dict):
        errors.append("标注块必须是 JSON 对象（现在解析成 %s）" % type(annotation).__name__)
        annotation = None
    return meta, text, annotation, errors


def is_untouched(annotation) -> bool:
    """槽位是否仍与空骨架逐键相等（即「还没填」）。"""
    if not isinstance(annotation, dict):
        return False
    skel = empty_annotation()
    if list(annotation.keys()) != list(skel.keys()):
        return False
    return json.loads(json.dumps(annotation, ensure_ascii=False)) == json.loads(
        json.dumps(skel, ensure_ascii=False))


# ==========================================================================
# 5. export
# ==========================================================================
def cmd_export(args) -> int:
    cfg = _load_config()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    ws = os.path.abspath(args.workspace or default_workspace(eval_dir))
    splits = pick_splits(args.split)
    eval_relpath = os.path.relpath(eval_dir, ROOT)

    created, skipped_empty, skipped_filled, refreshed, backed_up = [], [], [], [], []
    for split in splits:
        src = os.path.join(eval_dir, "%s.jsonl" % split)
        rows = read_jsonl(src)
        out_dir = os.path.join(ws, split)
        os.makedirs(out_dir, exist_ok=True)
        for rec in rows:
            path = os.path.join(out_dir, "%s.md" % rec["item_id"])
            content = render_item(rec, cfg, eval_relpath)
            if not os.path.exists(path):
                write_text_atomic(path, content)
                created.append(os.path.relpath(path, ws))
                continue
            _, _, annotation, errs = parse_item_file(path)
            untouched = (not errs) and is_untouched(annotation)
            if untouched and args.refresh:
                write_text_atomic(path, content)
                refreshed.append(os.path.relpath(path, ws))
            elif untouched:
                skipped_empty.append(os.path.relpath(path, ws))
            elif args.overwrite:
                bak = backup_file(path, ws)
                write_text_atomic(path, content)
                backed_up.append((os.path.relpath(path, ws), bak))
            else:
                skipped_filled.append(os.path.relpath(path, ws))

    write_text_atomic(os.path.join(ws, GUIDE_NAME), render_guide(cfg, eval_dir))
    write_text_atomic(os.path.join(ws, LEDGER_NAME), json.dumps(OrderedDict([
        ("schema", LEDGER_SCHEMA),
        ("eval_dir", eval_dir),
        ("workspace", ws),
        ("tool", TOOL_RELPATH),
        ("splits", splits),
        ("counts", OrderedDict([
            ("created", len(created)),
            ("refreshed", len(refreshed)),
            ("skipped_untouched", len(skipped_empty)),
            ("skipped_filled", len(skipped_filled)),
            ("overwritten_with_backup", len(backed_up)),
        ])),
        ("note", "本台账只记导出动作，不记任何标签；标签订在各自的条目文件里。"),
    ]), ensure_ascii=False, indent=2) + "\n")

    print("export 完成")
    print("  评测集目录：%s" % eval_dir)
    print("  工作区：    %s" % ws)
    for split in splits:
        n_src = len(read_jsonl(os.path.join(eval_dir, "%s.jsonl" % split)))
        n_out = len([f for f in os.listdir(os.path.join(ws, split)) if f.endswith(".md")])
        print("  %-5s 条目 %3d 条，工作区现有 %3d 个 .md" % (split, n_src, n_out))
    print("  新建 %d｜刷新空模板 %d｜跳过（未填、未动）%d｜跳过（**已填写，不覆盖**）%d｜覆盖并备份 %d"
          % (len(created), len(refreshed), len(skipped_empty), len(skipped_filled), len(backed_up)))
    if skipped_filled:
        print("  未覆盖的已填写条目（前 5 个）：%s" % "、".join(sorted(skipped_filled)[:5]))
    if backed_up:
        for rel, bak in backed_up[:5]:
            print("  已备份：%s → %s" % (rel, bak))
    print("  工作区入口：%s" % os.path.join(ws, GUIDE_NAME))
    print("  说明：默认**跳过**已存在的文件（不覆盖任何已填写的标注）；`--refresh` 只重写仍是空模板的"
          "条目；`--overwrite` 才会重写已填写的条目，且先把原文件备份到 `_备份\\`。")
    return 0


def pick_splits(value: str):
    value = (value or "all").lower()
    if value == "all":
        return ["dev", "test"]
    if value not in ("dev", "test"):
        raise SystemExit("--split 只接受 dev／test／all")
    return [value]


def backup_file(path: str, ws: str) -> str:
    """把单个文件备份到工作区 `_备份\\`；同名备份已存在则不重复写。"""
    d = os.path.dirname(path)
    digest = sha256_hex(open(path, "rb").read().decode("utf-8"))[:8]
    bak_dir = os.path.join(ws, BACKUP_DIRNAME, os.path.basename(d))
    os.makedirs(bak_dir, exist_ok=True)
    bak = os.path.join(bak_dir, "%s.%s.bak" % (os.path.basename(path), digest))
    if not os.path.exists(bak):
        shutil.copyfile(path, bak)
    return os.path.relpath(bak, ws)


def render_guide(cfg, eval_dir: str) -> str:
    ev = "／".join(cfg.EVENT_TYPES)
    rel = "／".join(r for r in cfg.RELATIONS)
    roles = "／".join(cfg.ROLES)
    return "\n".join([
        "# 标注工作区（由 `%s export` 生成）" % TOOL_RELPATH,
        "",
        "一个条目一个 `.md`：`dev\\DEV-001.md`、`test\\TEST-001.md`。**只改每个文件里"
        "「三、标注槽位」的那个 `json` 块**，其余部分（含 `<!-- HANDANN:… -->` 锚点）不要动。",
        "",
        "## 三个子命令",
        "",
        "```powershell",
        "python %s export --refresh     # 重新展开工作区（不覆盖已填写的条目）" % TOOL_RELPATH,
        "python %s check                # 校验已填写的标注，逐条打印证据；有问题退出码 1" % TOOL_RELPATH,
        "python %s stats                # 覆盖率与各类实体／事件／关系的条数" % TOOL_RELPATH,
        "python %s merge                # 写回 dev.jsonl／test.jsonl（先备份；check 不过则拒绝）" % TOOL_RELPATH,
        "```",
        "",
        "## 提醒（完整口径见 `%s\\标注说明.md`）" % os.path.relpath(eval_dir, ROOT),
        "",
        "* 单位：**一条 = 一个文本块**。`quote` 必须是本条 `text` 里真实出现的原文片段，",
        "  去空白后精确匹配，长度 12～200 字符；引用不到本块的证据写进 `notes`，不要抄别块的原文。",
        "* 8 种事件类型：%s。" % ev,
        "* 9 条关系（方向即语义）：%s。**`EVIDENCED_BY` 不标注**。" % rel,
        "* `role` 取 5 个值：%s。" % roles,
        "* 本块确实没有可标事实时：四个列表槽位留空，`notes` 写 `empty_but_checked: true` 加理由。",
        "* 填完一条就把该条的 `status` 改成 `%s`；没填完保持 `%s`。" % (COMPLETED_STATUS, PENDING_STATUS),
        "* 归不进本体的问题**只登记、不新增**：写进 `ontology_boundary_log`，不要自造关系或实体类型。",
        "",
        "## 备份与台账",
        "",
        "* `%s\\`：`export --overwrite` 与 `merge` 写盘前把被覆盖的文件复制到这里（同名同内容不重复）。"
        % BACKUP_DIRNAME,
        "* `%s`：上一次 `export` 的动作计数（新建／刷新／跳过／覆盖），不含任何标签。" % LEDGER_NAME,
        "",
    ])


# ==========================================================================
# 6. check
# ==========================================================================
class Problems(list):
    def add(self, kind, path, item_id, field, value, message):
        self.append({"kind": kind, "file": os.path.abspath(path) if path else "",
                     "item_id": item_id, "field": field, "value": brief(value), "message": message})


def _req(problems, kind, path, item_id, field, container, name):
    """必填字段存在且非空（空列表／空串算缺）。"""
    if name not in container:
        problems.add(kind, path, item_id, "%s.%s" % (field, name), "（缺该键）", "必填字段缺失")
        return False
    val = container[name]
    if val is None or (isinstance(val, (str, list, dict)) and len(val) == 0):
        problems.add(kind, path, item_id, "%s.%s" % (field, name), val, "必填字段为空")
        return False
    return True


def _check_quote(problems, kind, path, item_id, field, quote, text_norm, qmin, qmax):
    if quote is None:
        problems.add(kind, path, item_id, field, "（缺该键）", "缺 quote（协议第3.5节 要求给原文片段）")
        return
    if not isinstance(quote, str) or not quote.strip():
        problems.add(kind, path, item_id, field, quote, "quote 为空")
        return
    if not (qmin <= len(quote) <= qmax):
        problems.add(kind, path, item_id, field, quote,
                     "quote 长度须 %d～%d 字符（config.EVIDENCE），实测 %d" % (qmin, qmax, len(quote)))
    if norm_ws(quote) not in text_norm:
        problems.add(kind, path, item_id, field, quote,
                     "quote 去空白后不是本条 text 的精确子串（不做模糊匹配；"
                     "证据要落在本块，别块原文不要抄进来）")


def _check_chunk_id(problems, path, item_id, field, value, item_chunk_id):
    val = (value or {}).get("chunk_id", None)
    if val in (None, ""):
        problems.add(kind_of_missing(field), path, item_id, field, "（缺该键）",
                     "缺 chunk_id（证据落点，默认等于本条 chunk_id=%s）" % item_chunk_id)
        return False
    if val != item_chunk_id:
        problems.add(kind_of_missing(field), path, item_id, field, val,
                     "证据落点必须是本条自己的 chunk_id=%s（一条 = 一个文本块）" % item_chunk_id)
        return False
    return True


def kind_of_missing(field: str) -> str:
    """`<槽位>[i].chunk_id` → `<槽位>_chunk_id_mismatch`（证据行里看得见是哪个槽位）。"""
    return "%s_chunk_id_mismatch" % field.split("[")[0].split(".")[0]


def _check_evidence_attrs(problems, kind, path, item_id, idx, rel, chunk_id, doc_id, cfg):
    """除 EVIDENCED_BY 外，三项证据属性必需，且 source_doc_id／source_chunk_id 必须等于本条。"""
    for attr in ("source_doc_id", "source_chunk_id", "confidence"):
        if attr not in rel:
            problems.add(kind, path, item_id, "relations[%d].%s" % (idx, attr), "（缺该键）",
                         "`%s` 必须携带三项证据属性（除 EVIDENCED_BY 外三项必需）" % rel.get("relation"))
        elif rel.get(attr) is None or rel.get(attr) == "":
            problems.add(kind, path, item_id, "relations[%d].%s" % (idx, attr), rel.get(attr),
                         "证据属性为空（三项必需）")
    if rel.get("source_chunk_id") not in (None, "") and rel.get("source_chunk_id") != chunk_id:
        problems.add(kind, path, item_id, "relations[%d].source_chunk_id" % idx, rel.get("source_chunk_id"),
                     "source_chunk_id 必须等于本条 chunk_id=%s" % chunk_id)
    if rel.get("source_doc_id") not in (None, "") and rel.get("source_doc_id") != doc_id:
        problems.add("relation_doc_mismatch", path, item_id, "relations[%d].source_doc_id" % idx,
                     rel.get("source_doc_id"),
                     "source_doc_id 必须等于本条 doc_id=%s（不许指向别的文档）" % doc_id)
    # confidence 的**取值**复用与 events[].confidence 同一个 `_check_confidence`（单一口径）；
    # 键缺失／值为空已由上面的三项检查报成 `relation_evidence_missing`，这里跳过、不重复报。
    if rel.get("confidence") not in (None, ""):
        _check_confidence(problems, path, item_id, "relations[%d].confidence" % idx,
                          rel.get("confidence"), cfg)


# 本体边界登记的「生效口径」判据（协议第八节：只登记、不新增）：
# 建议／未定语境的同形句必须放行（如 suggested_handling 写「建议新增第 10 条关系：……」），
# 只有**断言已生效**才拒绝。动词在前（新增第 10 条关系）与名词在前（关系已新增）两种语序都要看。
_INVENT_VERBS = "新增|加入|采用|启用|写入|并入|扩展|复活|增加|引入"
_INVENT_NOUNS = "关系|实体类型|事件类型|属性"
_INVENT_FWD_RE = re.compile(
    r"(?P<verb>%s)(?P<tail>了)?(第)?\s*\d*\s*条?\s*(?P<noun>%s)" % (_INVENT_VERBS, _INVENT_NOUNS))
_INVENT_REV_RE = re.compile(
    r"(?P<noun>%s)\s*(?P<mark>已|已经|业已|现已|了)\s*(?P<verb>%s)" % (_INVENT_NOUNS, _INVENT_VERBS))
# 建议／未定语境提示词：出现在生效动词附近（前后各 12 字）时放过。
# 「记录」「备注」**不在**此列：它们说的是「把这个动作登记下来」，不是「还没做」——
# 放进来的话，「记录：已新增第 10 条关系，并写入图谱。」这种已生效断言会被误放行。
_SUGGESTION_CUES = ("建议", "疑似", "待", "拟", "希望", "考虑", "提请",
                    "尚未", "未定", "是否", "可否", "可能", "需要")
# 断言已生效的提示词：附近必须有其中一个（「已新增第 10 条关系」「并写入图谱」……）。
_EFFECTIVE_CUES = ("已", "了", "写入", "落库", "生效", "上线", "执行")
# 这些动词本身就读作「已经做了」（不是「建议做」），单独出现即可判生效；
# 提案型动词（新增／增加／引入……）则必须另有上表的生效提示词才判生效。
_COMPLETIVE_VERBS = ("采用", "启用", "写入", "并入", "复活")
_EFFECTIVE_WINDOW = 12


def _effective_claims(blob: str) -> list:
    """返回 blob 里「把新本体当成已生效」的断言片段；建议／未定语境的同形句不算。"""
    found = []
    for m in list(_INVENT_FWD_RE.finditer(blob)) + list(_INVENT_REV_RE.finditer(blob)):
        pre = blob[max(0, m.start() - _EFFECTIVE_WINDOW):m.start()]
        post = blob[m.end():m.end() + _EFFECTIVE_WINDOW]
        near = pre + post
        if any(cue in near for cue in _SUGGESTION_CUES):
            continue                      # 「建议新增……」「疑似……」「待……」：允许
        if (m.re is _INVENT_REV_RE or m.group("verb") in _COMPLETIVE_VERBS
                or m.groupdict().get("tail") == "了"
                or any(cue in near for cue in _EFFECTIVE_CUES)):
            found.append(m.group(0))      # 只有断言已生效才记
    return found


def _looks_like_inventing(entry) -> list:
    """`ontology_boundary_log` 里像「解决」而不是「记录」的痕迹（协议第八节：只登记、不新增）。"""
    hits = []
    if not isinstance(entry, dict):
        return hits
    # 1) 直接把自造的关系／实体类型／事件类型写成生效值
    for key in ("relation", "new_relation", "entity_type", "new_entity_type",
                "event_type", "new_event_type", "adopted_relation", "resolved_as"):
        if key in entry and entry[key]:
            hits.append("带生效口径的键 `%s`=%s" % (key, brief(entry[key], 60)))
    # 2) 声明性生效词（「建议／记录」允许，「把新本体当成已生效」不允许）
    blob = json.dumps(entry, ensure_ascii=False)
    claims = _effective_claims(blob)
    if claims:
        hits.append("文本断言「%s」这类**已生效**口径（协议第八节：只在 suggested_handling 里提"
                    "**建议**，不许把新本体当已生效）" % brief(claims[0], 60))
    if re.search(r"\bINVOLVES\b", blob):
        hits.append("出现已删除的关系 `INVOLVES`（协议第六节：不得复活）")
    # 3) 自造实体类型：Product／Location（协议第八节：禁止引入）
    m = re.search(r"\b(Product|Location)\b", blob)
    if m and re.search(r"新增|引入|加入|增加|扩展|类型", blob):
        hits.append("提到把 `%s` 作为新实体类型引入（协议第八节：禁止引入 Product 与 Location）" % m.group(1))
    # 4) case_type 不是协议建议的取值
    ct = entry.get("case_type")
    if ct not in CASE_TYPES:
        hits.append("`case_type`=%s 不在协议建议取值里（%s）" % (brief(ct, 40), CASE_TYPES_SOURCE))
    return hits


def run_check(ws: str, eval_dir: str, splits, cfg, verbose: bool = True):
    """返回 (problems, summary)。summary[split] = dict(items, files, filled, pending, empty_checked)。"""
    problems = Problems()
    summary = OrderedDict()

    truth = {}
    item_order = OrderedDict()
    dup_in_jsonl = []
    for split in ("dev", "test"):
        path = os.path.join(eval_dir, "%s.jsonl" % split)
        rows = read_jsonl(path)
        for rec in rows:
            iid = rec.get("item_id")
            if not isinstance(iid, str) or not iid.strip():
                problems.add("item_id_blank", path, repr(iid), "item_id", iid, "jsonl 里 item_id 为空")
                continue
            if iid in truth:
                dup_in_jsonl.append(iid)
                problems.add("item_id_duplicate", path, iid, "item_id", iid,
                             "jsonl 里 item_id 重复（另一处在 %s）" % truth[iid]["_src"])
            rec["_src"] = path
            truth[iid] = rec
            item_order[iid] = rec

    seen_files = OrderedDict()
    for split in splits:
        out_dir = os.path.join(ws, split)
        files = sorted(f for f in os.listdir(out_dir) if f.endswith(".md")) if os.path.isdir(out_dir) else []
        filled = pending = empty_checked = 0
        for fname in files:
            path = os.path.join(out_dir, fname)
            meta, text, annotation, errs = parse_item_file(path)
            for e in errs:
                problems.add("parse_error", path, (meta or {}).get("item_id", "?"), "文件结构", fname, e)
            if meta is None:
                continue
            iid = meta.get("item_id")

            # 文件名 / split / 重复
            if fname != "%s.md" % iid:
                problems.add("filename_mismatch", path, iid, "文件名", fname,
                             "文件名应与 item_id 一致（%s.md）" % iid)
            if meta.get("split") != split:
                problems.add("split_mismatch", path, iid, "split", meta.get("split"),
                             "文件在 `%s\\` 下，但 meta.split=%s" % (split, meta.get("split")))
            if iid in seen_files:
                problems.add("item_id_duplicate", path, iid, "item_id", iid,
                             "item_id 在 %d 个文件里重复（另一处 %s）" % (2, seen_files[iid]))
            else:
                seen_files[iid] = os.path.relpath(path, ws)

            rec = truth.get(iid)
            if rec is None:
                problems.add("item_id_unknown", path, iid, "item_id", iid,
                             "item_id 不在 dev.jsonl／test.jsonl 里（不许新增或改名条目）")
            else:
                for k in ("chunk_id", "doc_id"):
                    if meta.get(k) != rec.get(k):
                        problems.add("sampled_field_changed", path, iid, "meta.%s" % k, meta.get(k),
                                     "抽样字段不许改：jsonl 里 %s=%s" % (k, rec.get(k)))
                if text is None or text_digest(text) != text_digest(rec.get("text")):
                    problems.add("text_changed", path, iid, "text", text_digest(text or ""),
                                 "工作区里的文本块与 jsonl 里的不是同一段（抽样字段不许改）")

            # META 里的 text_digest 必须与工作区文本块**重算**的摘要一致：抽样字段被改由
            # text_changed／sampled_field_changed 报，这条专管「META 摘要本身被改」。
            if text is not None:
                recomputed = text_digest(text)
                if meta.get("text_digest") != recomputed:
                    problems.add("text_digest_mismatch", path, iid, "meta.text_digest",
                                 meta.get("text_digest"),
                                 "META 里的 text_digest 与本条文本块重算的摘要不符"
                                 "（按本条 text 重算应为 %s…）——META 摘要与抽样字段一样不许改"
                                 % recomputed[:16])

            if annotation is None:
                continue

            # 状态计数（与判据共用 `_annotation_status`，不另写一套；逐槽位校验走公开入口）。
            info = _annotation_status(annotation)
            if info["status"] == PENDING_STATUS:
                pending += 1
            elif info["status"] in (COMPLETED_STATUS, AUTO_STATUS):
                filled += 1
                if not info["non_empty"] and info["has_note"] and info["empty_checked"]:
                    empty_checked += 1

            for p in validate_annotation({"item_id": iid, "chunk_id": (rec or meta).get("chunk_id"),
                                          "doc_id": (rec or meta).get("doc_id"),
                                          "text": text, "annotation": annotation}, cfg, path):
                problems.append(p)

        summary[split] = {
            "files": len(files), "items": len([r for r in item_order.values()
                                               if r.get("split") == split]),
            "filled": filled, "pending": pending, "empty_checked": empty_checked,
            "no_file": len([r for r in item_order.values() if r.get("split") == split
                            and r.get("item_id") not in seen_files]),
        }

    if verbose:
        print("check：工作区 %s" % ws)
        for split, s in summary.items():
            print("  %-5s jsonl %3d 条｜工作区文件 %3d｜已标注 %3d｜待标注 %3d｜空块已核对 %3d｜无文件 %3d"
                  % (split, s["items"], s["files"], s["filled"], s["pending"],
                     s["empty_checked"], s["no_file"]))
        if dup_in_jsonl:
            print("  jsonl 内 item_id 重复：%s" % "、".join(sorted(set(dup_in_jsonl))))
        if not problems:
            print("  **0 个问题**：已填写的条目全部通过。")
        else:
            print("  %d 个问题：" % len(problems))
            for p in problems:
                print("    [%s] 文件=%s | item_id=%s | 字段=%s | 值=%s | %s"
                      % (p["kind"], show_path(p["file"]), p["item_id"], p["field"],
                         p["value"], p["message"]))
    return problems, summary


def _collect_refs(problems, path, iid, annotation, cfg):
    refs = {"entities": set(), "events": set(), "entity_type_by_ref": {}}
    for i, ent in enumerate(annotation.get("entities") or []):
        if isinstance(ent, dict) and ent.get("entity_ref"):
            refs["entities"].add(ent["entity_ref"])
            refs["entity_type_by_ref"][ent["entity_ref"]] = ent.get("entity_type")
    for i, ev in enumerate(annotation.get("events") or []):
        if isinstance(ev, dict) and ev.get("event_ref"):
            refs["events"].add(ev["event_ref"])
    return refs


def _check_entities(problems, path, iid, annotation, text_norm, chunk_id, cfg, qmin, qmax):
    entities = annotation.get("entities")
    if not isinstance(entities, list):
        problems.add("slot_type_error", path, iid, "entities", entities, "entities 必须是数组")
        return
    legal = set(cfg.ENTITY_TYPES_FROM_MODEL)
    all_types = set(cfg.ENTITY_TYPES)
    seen_ref = set()
    for i, ent in enumerate(entities):
        f = "entities[%d]" % i
        if not isinstance(ent, dict):
            problems.add("entity_not_object", path, iid, f, ent, "每个实体必须是 JSON 对象")
            continue
        et = ent.get("entity_type")
        if et not in legal:
            if et == "Event":
                problems.add("entity_type_illegal", path, iid, f + ".entity_type", et,
                             "Event 不写进 entities[]，事件一律写 events[]（标注说明.md 第3.1节）")
            elif et in all_types:
                problems.add("entity_type_illegal", path, iid, f + ".entity_type", et,
                             "entity_type 取 %s（config.ENTITY_TYPES_FROM_MODEL）" % "／".join(
                                 cfg.ENTITY_TYPES_FROM_MODEL))
            else:
                problems.add("entity_type_illegal", path, iid, f + ".entity_type", et,
                             "不在本体的 6 类实体里（%s）——不许新增实体类型"
                             % "／".join(cfg.ENTITY_TYPES))
        ref = ent.get("entity_ref")
        if not ref:
            problems.add("entity_ref_missing", path, iid, f + ".entity_ref", ref, "缺 entity_ref（E1／E2…）")
        elif ref in seen_ref:
            problems.add("entity_ref_duplicate", path, iid, f + ".entity_ref", ref, "本条内 entity_ref 重复")
        else:
            seen_ref.add(ref)
        # 必填属性（通用 ＋ 按类型）
        per = ENTITY_PER_TYPE_FIELDS.get(et) or []
        for name in ENTITY_COMMON_FIELDS + per:
            if name in ("quote", "chunk_id"):
                continue
            if name not in ent:
                problems.add("entity_field_missing", path, iid, f + "." + name, "（缺该键）",
                             "标注说明.md 第3.1节 的表：`%s` 的必填属性" % et)
        _check_chunk_id(problems, path, iid, f + ".chunk_id", ent, chunk_id)
        _check_quote(problems, "quote_not_in_text", path, iid, f + ".quote", ent.get("quote"),
                     text_norm, qmin, qmax)


def _check_events(problems, path, iid, annotation, text_norm, chunk_id, cfg, refs, qmin, qmax):
    events = annotation.get("events")
    if not isinstance(events, list):
        problems.add("slot_type_error", path, iid, "events", events, "events 必须是数组")
        return
    legal = set(cfg.EVENT_TYPES)
    seen_ref, type_by_ref = set(), {}
    for i, ev in enumerate(events):
        f = "events[%d]" % i
        if not isinstance(ev, dict):
            problems.add("event_not_object", path, iid, f, ev, "每条事件必须是 JSON 对象")
            continue
        et = ev.get("event_type")
        if et not in legal:
            problems.add("event_type_illegal", path, iid, f + ".event_type", et,
                         "event_type 取 8 种之一（%s）——不改名、不合并、不新增" % "／".join(cfg.EVENT_TYPES))
        ref = ev.get("event_ref")
        if not ref:
            problems.add("event_ref_missing", path, iid, f + ".event_ref", ref, "缺 event_ref（V1／V2…）")
        elif ref in seen_ref:
            problems.add("event_ref_duplicate", path, iid, f + ".event_ref", ref, "本条内 event_ref 重复")
        else:
            seen_ref.add(ref)
        type_by_ref[ref] = et
        for name in list(cfg.EVENT_CORE_ATTRS) + ["event_ref", "participants", "quote", "chunk_id"]:
            if name in ("quote", "chunk_id", "event_time", "confidence"):
                continue
            if name not in ev:
                problems.add("event_field_missing", path, iid, f + "." + name, "（缺该键）",
                             "标注说明.md 第3.2节：每条事件必填")
        etime = ev.get("event_time", None)
        if "event_time" in ev and etime not in (None, "") and not TIME_RE.match(str(etime)):
            problems.add("event_time_format", path, iid, f + ".event_time", etime,
                         "event_time 须为 YYYY-MM-DD；正文不能确定到日时写 null，绝不猜测")
        # confidence 是事件必填属性（config.EVENT_CORE_ATTRS）：键缺失／值为空同样交给
        # `_check_confidence` 判（报 `confidence_empty`），与 relations 路径是同一个口径。
        _check_confidence(problems, path, iid, f + ".confidence", ev.get("confidence"), cfg)
        parts = ev.get("participants")
        if parts is not None and not isinstance(parts, list):
            problems.add("participants_type", path, iid, f + ".participants", parts, "participants 必须是数组")
        else:
            for j, p in enumerate(parts or []):
                pf = "%s.participants[%d]" % (f, j)
                if not isinstance(p, dict):
                    problems.add("participant_not_object", path, iid, pf, p, "participants 的每一项应是 {entity_ref, role}")
                    continue
                if p.get("role") not in cfg.ROLES:
                    problems.add("role_illegal", path, iid, pf + ".role", p.get("role"),
                                 "role 只取 5 个值（%s）；取不到合适 role 时写进 ontology_boundary_log"
                                 "（case_type=role_boundary），不要自造第 6 个" % "／".join(cfg.ROLES))
                er = p.get("entity_ref")
                if not er:
                    problems.add("participant_ref_missing", path, iid, pf + ".entity_ref", er,
                                 "participants 每项要指向 entities[] 的 entity_ref")
                elif er not in refs["entities"]:
                    problems.add("participant_ref_dangling", path, iid, pf + ".entity_ref", er,
                                 "entity_ref=%s 在 entities[] 里不存在（悬空引用）" % brief(er, 30))
        _check_chunk_id(problems, path, iid, f + ".chunk_id", ev, chunk_id)
        _check_quote(problems, "quote_not_in_text", path, iid, f + ".quote", ev.get("quote"),
                     text_norm, qmin, qmax)
    refs["event_type_by_ref"] = type_by_ref


def _check_confidence(problems, path, iid, field, value, cfg):
    if value in (None, ""):
        problems.add("confidence_empty", path, iid, field, value, "confidence 是必需属性（三项证据属性之一）")
        return
    try:
        num = float(value)
    except (TypeError, ValueError):
        problems.add("confidence_range", path, iid, field, value, "confidence 必须是 %s～%s 的数值"
                     % (cfg.CONFIDENCE_MIN, cfg.CONFIDENCE_MAX))
        return
    if not (cfg.CONFIDENCE_MIN <= num <= cfg.CONFIDENCE_MAX):
        problems.add("confidence_range", path, iid, field, value, "confidence 越界（应在 %s～%s）"
                     % (cfg.CONFIDENCE_MIN, cfg.CONFIDENCE_MAX))


def _check_relations(problems, path, iid, annotation, text_norm, chunk_id, doc_id, cfg, refs, qmin, qmax):
    relations = annotation.get("relations")
    if not isinstance(relations, list):
        problems.add("slot_type_error", path, iid, "relations", relations, "relations 必须是数组")
        return
    legal = set(cfg.RELATIONS)
    for i, rel in enumerate(relations):
        f = "relations[%d]" % i
        if not isinstance(rel, dict):
            problems.add("relation_not_object", path, iid, f, rel, "每条关系必须是 JSON 对象")
            continue
        name = rel.get("relation")
        if name not in legal:
            problems.add("relation_illegal", path, iid, f + ".relation", name,
                         "relation 取 9 条之一（%s）——归不进 9 条时写进 ontology_boundary_log，"
                         "记录而不新增" % "／".join(cfg.RELATIONS))
            continue
        if name == "EVIDENCED_BY":
            problems.add("evidenced_by_annotated", path, iid, f + ".relation", name,
                         "EVIDENCED_BY 不标注：它由程序按 doc_id 生成，不携带证据三项"
                         "（标注说明.md 第3.3节、config.RELATION_SCHEMA）")
            continue
        for key in ("from_label", "from_ref", "to_label", "to_ref"):
            if key not in rel or rel.get(key) in (None, ""):
                problems.add("relation_field_missing", path, iid, f + "." + key, rel.get(key),
                             "标注说明.md 第3.3节：每条关系填 from_label／from_ref／to_label／to_ref")
        schema = cfg.RELATION_SCHEMA.get(name) or {}
        if rel.get("from_label") not in (schema.get("domain") or []):
            problems.add("relation_endpoint_type", path, iid, f + ".from_label", rel.get("from_label"),
                         "%s 的起点应为 %s（config.RELATION_SCHEMA）" % (name, "／".join(schema.get("domain") or [])))
        if rel.get("to_label") not in (schema.get("range") or []):
            problems.add("relation_endpoint_type", path, iid, f + ".to_label", rel.get("to_label"),
                         "%s 的终点应为 %s（config.RELATION_SCHEMA）" % (name, "／".join(schema.get("range") or [])))
        # 端点引用必须落在本条的 entities[]／events[] 里（Event 端指向 events[]，其余指向 entities[]）
        for side in ("from", "to"):
            label, ref = rel.get(side + "_label"), rel.get(side + "_ref")
            if label in (None, "") or ref in (None, ""):
                continue
            pool = refs["events"] if label == "Event" else refs["entities"]
            if ref not in pool:
                problems.add("relation_ref_dangling", path, iid, "%s.%s_ref" % (f, side), ref,
                             "%s_ref=%s 在 %s[] 里不存在（悬空引用；端点须是本条标注过的实体／事件）"
                             % (side, brief(ref, 30), "events" if label == "Event" else "entities"))
                continue
            # 端点实际类型必须与声明的 label 一致（指向 events[] 即 Event；指向 entities[] 取该实体类型）
            actual = "Event" if label == "Event" else refs["entity_type_by_ref"].get(ref)
            if actual not in (None, "") and label != actual:
                problems.add("relation_label_mismatch", path, iid, "%s.%s_label" % (f, side), label,
                             "%s_label 写的是 %s，但 %s_ref=%s 的实际类型是 %s（声明必须等于端点实际类型）"
                             % (side, brief(label, 30), side, brief(ref, 30), actual))
        for extra in schema.get("extra_attrs") or []:
            if extra in ("valid_from", "valid_to"):
                # BELONGS_TO 的有效期：正文没给日期时写 null 或省略，都视为「未知」——
                # config.GRAPH.belongs_to_validity_fallback=None（不用发布时间兜底），
                # 也不许为了过 check 编一个日期；给了值就必须是 YYYY-MM-DD，格式非法照样报。
                val = rel.get(extra)
                if val in (None, ""):
                    continue
                if not isinstance(val, str) or not TIME_RE.match(val):
                    problems.add("relation_validity_format", path, iid, f + "." + extra, val,
                                 "%s 的 `%s` 只能是 YYYY-MM-DD；正文没有日期时写 null 或省略"
                                 "（视为未知，不许编日期）" % (name, extra))
                continue
            if extra not in rel or rel.get(extra) in (None, ""):
                problems.add("relation_extra_missing", path, iid, f + "." + extra, rel.get(extra),
                             "%s 另需 `%s`（config.RELATION_SCHEMA.extra_attrs）" % (name, extra))
        if name == "PARTICIPATES_IN" and rel.get("role") not in cfg.ROLES:
            problems.add("role_illegal", path, iid, f + ".role", rel.get("role"),
                         "PARTICIPATES_IN 的 role 只取 5 个值（%s）" % "／".join(cfg.ROLES))
        if name == "ISSUED_BY":
            etype = (refs.get("event_type_by_ref") or {}).get(rel.get("from_ref"))
            if etype is not None and etype not in cfg.ISSUED_BY_EVENT_TYPES:
                problems.add("issued_by_wrong_event_type", path, iid, f + ".from_ref", rel.get("from_ref"),
                             "ISSUED_BY 只出现在政策事件与监管事件上（config.ISSUED_BY_EVENT_TYPES）；"
                             "from_ref 指向的事件类型是 %s" % etype)
        if name == "RELATED_TO" and "因果关系" in json.dumps(rel, ensure_ascii=False):
            problems.add("related_to_causal", path, iid, f, rel.get("quote"),
                         "RELATED_TO 只表公开信息中出现的关联，不得表述为因果关系")
        _check_evidence_attrs(problems, "relation_evidence_missing", path, iid, i, rel,
                              chunk_id, doc_id, cfg)
        _check_quote(problems, "quote_not_in_text", path, iid, f + ".quote", rel.get("quote"),
                     text_norm, qmin, qmax)


def _check_times(problems, path, iid, annotation, text_norm, qmin, qmax, cfg):
    times = annotation.get("times")
    if not isinstance(times, list):
        problems.add("slot_type_error", path, iid, "times", times, "times 必须是数组")
        return
    legal = ["event_time", "valid_from", "valid_to"]
    for i, t in enumerate(times):
        f = "times[%d]" % i
        if not isinstance(t, dict):
            problems.add("time_not_object", path, iid, f, t, "每条时间必须是 JSON 对象")
            continue
        if t.get("time_type") not in legal:
            problems.add("time_type_illegal", path, iid, f + ".time_type", t.get("time_type"),
                         "time_type 取 %s（标注说明.md 第3.4节）" % "／".join(legal))
        if not TIME_RE.match(str(t.get("value") or "")):
            problems.add("time_value_format", path, iid, f + ".value", t.get("value"),
                         "value 须为 YYYY-MM-DD")
        _check_quote(problems, "quote_not_in_text", path, iid, f + ".quote", t.get("quote"),
                     text_norm, qmin, qmax)


def _check_oblog(problems, path, iid, annotation, text_norm, chunk_id, qmin, qmax):
    log = annotation.get("ontology_boundary_log")
    if not isinstance(log, list):
        problems.add("slot_type_error", path, iid, "ontology_boundary_log", log,
                     "ontology_boundary_log 必须是数组")
        return
    for i, entry in enumerate(log):
        f = "ontology_boundary_log[%d]" % i
        if not isinstance(entry, dict):
            problems.add("oblog_not_object", path, iid, f, entry, "每条登记必须是 JSON 对象")
            continue
        for name in ("case_id", "case_type", "summary", "quote", "chunk_id", "suggested_handling"):
            if name in ("quote", "chunk_id"):
                continue
            if name not in entry or entry.get(name) in (None, ""):
                problems.add("oblog_field_missing", path, iid, f + "." + name, entry.get(name),
                             "标注说明.md 第八节：每条登记填 case_id／case_type／summary／quote／"
                             "chunk_id／suggested_handling")
        for hit in _looks_like_inventing(entry):
            problems.add("ontology_invention", path, iid, f, hit,
                         "协议第八节：归不进本体的情形**只登记、不新增**——不得新增／改名／合并实体类型、"
                         "事件类型、关系类型，不得复活 INVOLVES，不得引入 Product 与 Location")
        _check_chunk_id(problems, path, iid, f + ".chunk_id", entry, chunk_id)
        _check_quote(problems, "quote_not_in_text", path, iid, f + ".quote", entry.get("quote"),
                     text_norm, qmin, qmax)


def _annotation_status(annotation) -> dict:
    """一条标注的**事实分类**（不含任何问题）：`check` 的计数与 `validate_annotation` 的判据共用这一份。

    把「status 与槽位是否自洽」所需的原始事实算一次、用两处，避免计数与判据各写一套而漂移。
    """
    slots = ["entities", "events", "relations", "times", "ontology_boundary_log"]
    notes = annotation.get("notes")
    notes_str = notes if isinstance(notes, str) else ""
    return {
        "status": annotation.get("status"),
        "slots": slots,
        "empty": is_untouched(annotation),
        "non_empty": any(isinstance(annotation.get(s), list) and annotation.get(s) for s in slots),
        "has_note": bool(notes_str.strip()),
        "notes_str": notes_str,
        "empty_checked": "empty_but_checked" in notes_str,
    }


def _check_auto_provenance(problems, path, item_id, annotation):
    """`status = auto_annotated` 必须带 provenance：缺 `model`／`prompt_version`／`temperature` 即报。

    这条守卫的唯一目的是**防止自动标注被当成人工标注**：自动标注与人工标注在结构上无法区分，
    只能靠「有没有如实登记谁产的、用什么产的」。`temperature = 0` 是合法取值（0 不是「空」），
    因此这里判的是「键缺失／是 None／是空串」，不是真值。
    """
    prov = annotation.get("provenance")
    if not isinstance(prov, dict):
        problems.add("auto_provenance_missing", path, item_id, "provenance", prov,
                     "status=%s 必须带 provenance（%s）——缺了它，自动标注就可能被当成人工标注"
                     % (AUTO_STATUS, "／".join(AUTO_PROVENANCE_REQUIRED)))
        return
    for name in AUTO_PROVENANCE_REQUIRED:
        value = prov.get(name)
        if name not in prov or value is None or value == "":
            problems.add("auto_provenance_missing", path, item_id, "provenance.%s" % name, value,
                         "status=%s 的 provenance 缺必填项 `%s`（%s 三项都必须有；"
                         "temperature=0 是合法取值，不允许用空值代替）"
                         % (AUTO_STATUS, name, "／".join(AUTO_PROVENANCE_REQUIRED)))


def _check_status(problems, path, item_id, annotation, info):
    """`status` 与槽位的一致性；`auto_annotated` 另加 provenance 守卫。"""
    status = info["status"]
    if status == PENDING_STATUS:
        if info["non_empty"] or info["has_note"]:
            problems.add("status_pending_but_filled", path, item_id, "status", status,
                         "status 仍是 %s，但槽位已有内容（%s）——填完了就把 status 改成 %s 或 %s"
                         % (PENDING_STATUS,
                            "、".join(s for s in info["slots"] if annotation.get(s)) or "notes",
                            COMPLETED_STATUS, AUTO_STATUS))
    elif status == AUTO_STATUS:
        _check_auto_provenance(problems, path, item_id, annotation)
        if not info["non_empty"] and not info["has_note"]:
            problems.add("status_completed_but_empty", path, item_id, "status", status,
                         "status=%s 说已完成，但 entities／events／relations／times／"
                         "ontology_boundary_log 全空、notes 也空；本块确实没有可标事实时，"
                         "四个槽位留空并在 notes 写 `empty_but_checked: true` 加理由" % AUTO_STATUS)
    elif status == COMPLETED_STATUS:
        if not info["non_empty"] and not info["has_note"]:
            problems.add("status_completed_but_empty", path, item_id, "status", status,
                         "status 说已完成，但 entities／events／relations／times／"
                         "ontology_boundary_log 全空、notes 也空；本块确实没有可标事实时，"
                         "四个槽位留空并在 notes 写 `empty_but_checked: true` 加理由")
    else:
        problems.add("status_unknown", path, item_id, "status", status,
                     "status 只能是 %s／%s／%s"
                     % (PENDING_STATUS, COMPLETED_STATUS, AUTO_STATUS))


def validate_annotation(record, cfg=None, path=None):
    """**公开校验入口**：对一条**内存里**的标注记录跑与 `check` 完全相同的槽位校验。

    `record` 需要：`item_id`、`chunk_id`、`doc_id`、`text`、`annotation`（`annotation` 必须是 dict）。
    返回问题列表（每项含 `kind`／`file`／`item_id`／`field`／`value`／`message`），空列表即通过。

    **边界**：只判「标注本身」是否合口径。文件级的问题（文件名与 `item_id` 不一致、split 不符、
    `item_id` 重复或不在 jsonl 里、抽样字段被改、META 的 `text_digest` 不符）属于**工作区文件**，
    由 `run_check` 负责——`check` 与 `代码\\抽取与图谱\\auto_annotate.py` 共用本函数这一份校验源，
    所以不存在「第二套校验」。
    """
    if cfg is None:
        cfg = _load_config()
    problems = Problems()
    item_id = record.get("item_id")
    annotation = record.get("annotation")
    if not isinstance(annotation, dict):
        problems.add("slot_type_error", path, item_id, "annotation", annotation,
                     "annotation 必须是 JSON 对象")
        return problems

    info = _annotation_status(annotation)
    _check_status(problems, path, item_id, annotation, info)

    # 版本级属性不得出现在标注里
    if "data_cutoff_time" in json.dumps(annotation, ensure_ascii=False):
        problems.add("data_cutoff_time_present", path, item_id, "annotation", "data_cutoff_time",
                     "data_cutoff_time 是数据集版本级属性，不落任何节点或关系，标注里不得出现")

    if info["empty"] and not info["non_empty"]:
        return problems

    # ---------------- 逐槽位 ----------------
    text_norm = norm_ws(record.get("text") or "")
    chunk_id = record.get("chunk_id")
    doc_id = record.get("doc_id")
    qmin, qmax = cfg.EVIDENCE["quote_min_chars"], cfg.EVIDENCE["quote_max_chars"]

    _check_entities(problems, path, item_id, annotation, text_norm, chunk_id, cfg, qmin, qmax)
    refs = _collect_refs(problems, path, item_id, annotation, cfg)
    _check_events(problems, path, item_id, annotation, text_norm, chunk_id, cfg, refs, qmin, qmax)
    _check_relations(problems, path, item_id, annotation, text_norm, chunk_id, doc_id, cfg, refs,
                     qmin, qmax)
    _check_times(problems, path, item_id, annotation, text_norm, qmin, qmax, cfg)
    _check_oblog(problems, path, item_id, annotation, text_norm, chunk_id, qmin, qmax)
    return problems


def cmd_check(args) -> int:
    cfg = _load_config()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    ws = os.path.abspath(args.workspace or default_workspace(eval_dir))
    problems, _ = run_check(ws, eval_dir, pick_splits(args.split), cfg)
    if problems:
        print("check 失败：%d 个问题（退出码 1）" % len(problems))
        return 1
    print("check 通过（退出码 0）")
    return 0


# ==========================================================================
# 7. merge
# ==========================================================================
MERGE_REFUSES_AUTO_MSG = (
    "第 6 阶段交付文件的槽位必须保持为空（《15》第八节 的冻结契约），自动标注落在独立产物里"
    "（`阶段05-数据准备\\数据集\\抽取评测集\\v2.1\\自动标注\\`）。本守卫为硬守卫，`--force` 不放行。"
)


def scan_auto_annotated(ws: str, splits) -> list:
    """扫出工作区里 `status = auto_annotated` 的条目，返回 [(路径, item_id), …]。

    `merge` 用它决定是否拒绝写盘；`check` 不看它（`check` 的职责是判「标注本身合不合口径」，
    自动标注在它眼里是**合法**的第三个状态）。
    """
    hits = []
    for split in splits:
        out_dir = os.path.join(ws, split)
        for fname in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
            if not fname.endswith(".md"):
                continue
            path = os.path.join(out_dir, fname)
            _, _, annotation, errs = parse_item_file(path)
            if annotation is None or errs:
                continue
            if annotation.get("status") == AUTO_STATUS:
                hits.append((path, fname[:-3]))
    return hits


def cmd_merge(args) -> int:
    cfg = _load_config()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    ws = os.path.abspath(args.workspace or default_workspace(eval_dir))
    splits = pick_splits(args.split)

    # 守卫（先于 check，且不受 --force 影响）：`auto_annotated` 一律不许写回交付文件。
    # 理由：第 6 阶段交付文件的槽位必须保持为空（《15》第八节 的冻结契约），
    # 自动标注是**另一件产物**（模型参照集），写回会把「交付文件没有标签」这条契约破坏掉。
    auto_hits = scan_auto_annotated(ws, splits)
    if auto_hits:
        print("merge 拒绝写盘：发现 %d 条 `%s`（merge_refuses_auto）。" % (len(auto_hits), AUTO_STATUS))
        for path, iid in auto_hits[:10]:
            print("    [merge_refuses_auto] 文件=%s | item_id=%s | 字段=status | 值=%s | %s"
                  % (show_path(path), iid, AUTO_STATUS, MERGE_REFUSES_AUTO_MSG))
        if len(auto_hits) > 10:
            print("    （另有 %d 条同类，不逐一列出）" % (len(auto_hits) - 10))
        return 1

    problems, _ = run_check(ws, eval_dir, splits, cfg)
    if problems and not args.force:
        print("merge 拒绝写盘：check 报了 %d 个问题（先修，或用 --force 越过）。" % len(problems))
        return 1
    if problems:
        print("警告：--force 越过 %d 个 check 问题，仍按工作区内容写盘。" % len(problems))

    record = OrderedDict([("schema", MERGE_SCHEMA), ("tool", TOOL_RELPATH), ("splits", OrderedDict())])
    for split in splits:
        src = os.path.join(eval_dir, "%s.jsonl" % split)
        rows = read_jsonl(src)
        out_dir = os.path.join(ws, split)
        annotations = {}
        for fname in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
            if not fname.endswith(".md"):
                continue
            _, _, annotation, errs = parse_item_file(os.path.join(out_dir, fname))
            if annotation is None or errs:
                continue
            if is_untouched(annotation):
                continue
            ann = OrderedDict((k, annotation.get(k)) for k in empty_annotation().keys())
            ann["status"] = COMPLETED_STATUS   # merge 的职责之一：未标注 → 完成标记
            annotations[fname[:-3]] = ann

        merged = 0
        for rec in rows:
            ann = annotations.get(rec.get("item_id"))
            if ann is None:
                continue
            merged += 1
            rec["annotation"] = OrderedDict((k, ann[k]) for k in empty_annotation().keys())
        new_text = "".join(dump_line(rec) + "\n" for rec in rows)

        old_text = open(src, encoding="utf-8").read()
        entry = OrderedDict([("annotated_in_workspace", len(annotations)),
                             ("merged_items", merged), ("changed", new_text != old_text)])
        if new_text == old_text:
            entry["backup"] = None
            entry["note"] = "内容与现有文件逐字节一致，未改动、未备份（幂等）"
            print("merge %-5s：已是最新状态，未改动（幂等）" % split)
        else:
            bak = backup_jsonl(src, ws)
            write_text_atomic(src, new_text)
            entry["backup"] = os.path.relpath(bak, ws) if bak else None
            entry["out_sha256"] = sha256_hex(new_text)
            print("merge %-5s：写回 %d 条，status → %s；原件已备份到 %s"
                  % (split, merged, COMPLETED_STATUS, entry["backup"]))
            print("              输出 SHA-256 %s" % entry["out_sha256"])
        record["splits"][split] = entry

    write_text_atomic(os.path.join(ws, "_合并记录.json"),
                      json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    print("merge 完成。记录：%s" % os.path.join(ws, "_合并记录.json"))
    print("只改了 annotation（status → %s），其余字段与字段顺序逐字保留；重跑本命令不会二次改动。" % COMPLETED_STATUS)
    return 0


def backup_jsonl(src: str, ws: str) -> str:
    """备份 jsonl 原件到工作区 `_备份\\`；同内容已备份过就不再重复。"""
    raw = open(src, "rb").read()
    digest = sha256_hex(raw.decode("utf-8"))[:8]
    bak_dir = os.path.join(ws, BACKUP_DIRNAME)
    os.makedirs(bak_dir, exist_ok=True)
    bak = os.path.join(bak_dir, "%s.%s.bak" % (os.path.basename(src), digest))
    if not os.path.exists(bak):
        with open(bak, "wb") as fh:
            fh.write(raw)
    return bak


# ==========================================================================
# 8. stats
# ==========================================================================
def cmd_stats(args) -> int:
    cfg = _load_config()
    eval_dir = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    ws = os.path.abspath(args.workspace or default_workspace(eval_dir))
    splits = pick_splits(args.split)

    print("stats：工作区 %s" % ws)
    grand = {"filled": 0, "pending": 0, "items": 0}
    for split in splits:
        rows = read_jsonl(os.path.join(eval_dir, "%s.jsonl" % split))
        out_dir = os.path.join(ws, split)
        ent_type, ev_type, rel_type = Counter(), Counter(), Counter()
        filled = empty_checked = 0
        n_time = n_ob = 0
        for fname in sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []:
            if not fname.endswith(".md"):
                continue
            _, _, ann, errs = parse_item_file(os.path.join(out_dir, fname))
            if ann is None:
                print("  [警告] %s 解析失败：%s" % (fname, "；".join(errs)))
                continue
            if is_untouched(ann):
                continue
            filled += 1
            if not any(ann.get(s) for s in ("entities", "events", "relations", "times",
                                            "ontology_boundary_log")) \
                    and "empty_but_checked" in str(ann.get("notes") or ""):
                empty_checked += 1
            for e in ann.get("entities") or []:
                ent_type[sget(e, "entity_type")] += 1
            for v in ann.get("events") or []:
                ev_type[sget(v, "event_type")] += 1
            for r in ann.get("relations") or []:
                rel_type[sget(r, "relation")] += 1
            n_time += len(ann.get("times") or [])
            n_ob += len(ann.get("ontology_boundary_log") or [])
        print("")
        print("== %s ==（jsonl %d 条）" % (split, len(rows)))
        print("  已标注 %d｜待标注 %d｜其中空块已核对（notes 含 empty_but_checked）%d"
              % (filled, len(rows) - filled, empty_checked))
        _row("实体类型", cfg.ENTITY_TYPES_FROM_MODEL, ent_type)
        _row("事件类型", cfg.EVENT_TYPES, ev_type)
        _row("关系", cfg.RELATIONS, rel_type)
        zero_ev = [t for t in cfg.EVENT_TYPES if not ev_type.get(t)]
        zero_rel = [r for r in cfg.RELATIONS if not rel_type.get(r)]
        print("  时间条目 %d｜本体边界登记 %d" % (n_time, n_ob))
        if zero_ev:
            print("  **零覆盖事件类型**：%s —— 冻结前若仍为 0，须按《标注说明.md》第11节／《16》"
                  "「已知限制与证据不足清单」显式登记为证据不足" % "、".join(zero_ev))
        if zero_rel:
            print("  **零覆盖关系**：%s —— 同上（EVIDENCED_BY 本就不标注，恒为 0 属正常）"
                  % "、".join(zero_rel))
        grand["filled"] += filled
        grand["pending"] += len(rows) - filled
        grand["items"] += len(rows)
    if len(splits) > 1:
        print("")
        print("== 合计 ==（jsonl %d 条）" % grand["items"])
        print("  已标注 %d｜待标注 %d" % (grand["filled"], grand["pending"]))
    return 0


def _row(label, order, counter):
    parts = []
    for name in order:
        parts.append("%s %d" % (name, counter.get(name, 0)))
    print("  %s（%d 类）：%s" % (label, len(order), "｜".join(parts)))


# ==========================================================================
# 9. selftest —— 独立复现用：全程在系统临时目录，不碰真实文件
# ==========================================================================
def cmd_selftest(args) -> int:
    cfg = _load_config()
    real_eval = os.path.abspath(args.eval_dir or default_eval_dir(cfg))
    ok = True
    tmp = tempfile.mkdtemp(prefix="handann-selftest-")
    try:
        eval_dir = os.path.join(tmp, EVAL_SUBDIR, cfg.DATASET_VERSION)
        os.makedirs(eval_dir, exist_ok=True)
        for name in ("dev.jsonl", "test.jsonl"):
            shutil.copyfile(os.path.join(real_eval, name), os.path.join(eval_dir, name))
        before = {n: sha256_hex(open(os.path.join(eval_dir, n), "rb").read().decode("utf-8"))
                  for n in ("dev.jsonl", "test.jsonl")}
        ws = default_workspace(eval_dir)

        print("selftest 临时目录：%s" % tmp)
        print("-" * 72)
        print("[1] export 两次 → 幂等")
        ns = argparse.Namespace(eval_dir=eval_dir, workspace=ws, split="all",
                                refresh=False, overwrite=False)
        cmd_export(ns)
        dig1 = _ws_digest(ws)
        cmd_export(ns)
        dig2 = _ws_digest(ws)
        ok &= _assert(dig1 == dig2, "工作区两次导出的摘要一致（幂等）", dig1[:16] + " vs " + dig2[:16])

        print("-" * 72)
        print("[2] 全新工作区 check → 全 pending、0 问题")
        probs, summary = run_check(ws, eval_dir, ["dev", "test"], cfg, verbose=False)
        ok &= _assert(not probs, "刚导出时 0 问题", "实测 %d 个" % len(probs))
        ok &= _assert(summary["dev"]["filled"] == 0 and summary["dev"]["pending"] == 60
                      and summary["test"]["pending"] == 200, "全 260 条均为待标注",
                      "dev filled=%d pending=%d；test pending=%d"
                      % (summary["dev"]["filled"], summary["dev"]["pending"], summary["test"]["pending"]))
        print("-" * 72)
        print("[3] stats（全空工作区）")
        cmd_stats(argparse.Namespace(eval_dir=eval_dir, workspace=ws, split="all"))

        print("-" * 72)
        print("[4] 往返：给 dev 的 1 条填一个**合成假标签**，check 应通过，merge 只改 annotation")
        target = "DEV-001"
        tpath = os.path.join(ws, "dev", "%s.md" % target)
        rec = [r for r in read_jsonl(os.path.join(eval_dir, "dev.jsonl"))
               if r["item_id"] == target][0]
        quote = _fake_quote(rec["text"])
        _fill_annotation(tpath, _fake_annotation(target, rec["chunk_id"], rec["doc_id"], quote))
        probs, _ = run_check(ws, eval_dir, ["dev"], cfg, verbose=False)
        kinds = sorted({p["kind"] for p in probs})
        ok &= _assert(not probs, "合成标签（结构合法）下 check 通过", "实测问题 %s" % kinds)
        ns_merge = argparse.Namespace(eval_dir=eval_dir, workspace=ws, split="dev", force=False)
        cmd_merge(ns_merge)
        merged_line, orig_line = _line_of(eval_dir, "dev.jsonl", target), _orig_line(real_eval, "dev.jsonl", target)
        diff = _annotation_only_diff(orig_line, merged_line)
        ok &= _assert(diff == "", "合并后的行与原件**只在 annotation 上不同**", diff or "只有 annotation 变化")
        ok &= _assert(json.loads(merged_line)["annotation"]["status"] == COMPLETED_STATUS,
                      "status 已切到完成标记 %s" % COMPLETED_STATUS,
                      json.loads(merged_line)["annotation"]["status"])
        before_merge = open(os.path.join(eval_dir, "dev.jsonl"), encoding="utf-8").read()
        cmd_merge(ns_merge)
        ok &= _assert(before_merge == open(os.path.join(eval_dir, "dev.jsonl"), encoding="utf-8").read(),
                      "merge 重跑不二次改动（幂等）", "两次写盘逐字节一致")

        print("-" * 72)
        print("[5] 负向自测：6 个不同的错，check 必须逐条报出正确的证据行")
        faults = [
            ("DEV-002", "entity_type_illegal", lambda a, r: a["entities"].append(
                {"entity_type": "Product", "entity_ref": "E1", "quote": _fake_quote(r["text"]),
                 "chunk_id": r["chunk_id"], "product_name": "合成产品"})),
            ("DEV-003", "role_illegal", lambda a, r: a["events"].append(
                {"event_ref": "V1", "event_type": "业绩", "event_name": "合成事件", "event_time": None,
                 "description": "合成", "confidence": 0.5, "chunk_id": r["chunk_id"],
                 "quote": _fake_quote(r["text"]),
                 "participants": [{"entity_ref": "E1", "role": "第六个角色"}]})),
            ("DEV-004", "quote_not_in_text", lambda a, r: a["times"].append(
                {"time_type": "event_time", "value": "2026-09-23", "quote": "这段文字绝对不在本块的原文里出现过"})),
            ("DEV-005", "relation_evidence_missing", lambda a, r: a["relations"].append(
                {"relation": "PARTICIPATES_IN", "from_label": "Company", "from_ref": "E1",
                 "to_label": "Event", "to_ref": "V1", "quote": _fake_quote(r["text"]),
                 "source_doc_id": r["doc_id"], "confidence": 0.5})),
            ("DEV-006", "relation_evidence_missing", lambda a, r: a["relations"].append(
                {"relation": "BELONGS_TO", "from_label": "Company", "from_ref": "E1",
                 "to_label": "Industry", "to_ref": "E2", "quote": _fake_quote(r["text"]),
                 "source_doc_id": r["doc_id"], "source_chunk_id": 999999, "confidence": 0.5})),
            ("DEV-007", "ontology_invention", lambda a, r: a["ontology_boundary_log"].append(
                {"case_id": "OB-DEV-007-1", "case_type": "relation_boundary", "summary": "合成",
                 "quote": _fake_quote(r["text"]), "chunk_id": r["chunk_id"],
                 "suggested_handling": "已新增第 10 条关系 INVOLVES 并写入图谱"})),
        ]
        for iid, _, mutate in faults:
            p = os.path.join(ws, "dev", "%s.md" % iid)
            rr = [r for r in read_jsonl(os.path.join(eval_dir, "dev.jsonl")) if r["item_id"] == iid][0]
            a = empty_annotation()
            a["status"] = COMPLETED_STATUS
            mutate(a, rr)
            _write_annotation(p, a)
            probs, _ = run_check(ws, eval_dir, ["dev"], cfg, verbose=False)
            hit = [x for x in probs if x["item_id"] == iid]
            kinds = sorted({x["kind"] for x in hit})
            expect = faults[[f[0] for f in faults].index(iid)][1]
            ok &= _assert(expect in kinds, "%s：check 报出 `%s`" % (iid, expect), "实测 %s" % (kinds or "无"))
            for x in hit:
                if x["kind"] == expect:
                    print("        证据行 → 文件=%s | item_id=%s | 字段=%s | 值=%s"
                          % (os.path.relpath(x["file"], tmp), x["item_id"], x["field"], x["value"]))
                    break
            _write_annotation(p, empty_annotation())

        print("-" * 72)
        print("[6] F1～F6 回归：六项「修前会误判」的缺陷，逐条断言（含「仍须拒绝」的对照）")
        dev_rows = {r["item_id"]: r for r in read_jsonl(os.path.join(eval_dir, "dev.jsonl"))}
        _OMIT = object()

        def _case(iid, mutate):
            """在 DEV-0NN 上写入变异后的**合成**标注并跑 check，返回 (路径, 该条问题)；跑完复位。"""
            p = os.path.join(ws, "dev", "%s.md" % iid)
            rr = dev_rows[iid]
            a = _fake_annotation(iid, rr["chunk_id"], rr["doc_id"], _fake_quote(rr["text"]))
            mutate(a, rr)
            _write_annotation(p, a)
            probs, _ = run_check(ws, eval_dir, ["dev"], cfg, verbose=False)
            hit = [x for x in probs if x["item_id"] == iid]
            _write_annotation(p, empty_annotation())
            return p, hit

        def _expect_kind(label, iid, mutate, kind):
            p, hit = _case(iid, mutate)
            kinds = sorted({x["kind"] for x in hit})
            good = _assert(kind in kinds, "%s：check 报出 `%s`" % (label, kind),
                           "实测 %s" % (kinds or "无"))
            for x in hit:
                if x["kind"] == kind:
                    print("        证据行 → 文件=%s | item_id=%s | 字段=%s | 值=%s"
                          % (os.path.relpath(x["file"], tmp), x["item_id"], x["field"], x["value"]))
                    break
            return good

        def _expect_pass(label, iid, mutate):
            p, hit = _case(iid, mutate)
            kinds = sorted({x["kind"] for x in hit})
            return _assert(not hit, "%s：check 必须通过（不许误拒）" % label,
                           "实测 %s" % (kinds or "0 个问题"))

        def _belongs_to(a, r, valid_from=_OMIT, valid_to=_OMIT):
            a["entities"].append({"entity_type": "Industry", "entity_ref": "E2",
                                  "industry_code": "", "industry_name": "【合成行业】", "level": 1,
                                  "quote": _fake_quote(r["text"]), "chunk_id": r["chunk_id"]})
            rel = {"relation": "BELONGS_TO", "from_label": "Company", "from_ref": "E1",
                   "to_label": "Industry", "to_ref": "E2", "quote": _fake_quote(r["text"]),
                   "source_doc_id": r["doc_id"], "source_chunk_id": r["chunk_id"],
                   "confidence": 0.5}
            if valid_from is not _OMIT:
                rel["valid_from"] = valid_from
            if valid_to is not _OMIT:
                rel["valid_to"] = valid_to
            a["relations"] = [rel]

        # 修前：F1～F4 漏检（check 放行）、F5～F6 误拒（check 拒绝合法写法）。
        ok &= _expect_kind("F1a 关系 confidence=1.5 越界", "DEV-009",
                           lambda a, r: a["relations"][0].update(confidence=1.5), "confidence_range")
        ok &= _expect_kind("F1b 关系 confidence=\"abc\" 非数值（与 events 同码 confidence_range）",
                           "DEV-010",
                           lambda a, r: a["relations"][0].update(confidence="abc"),
                           "confidence_range")
        ok &= _expect_kind("F2 source_doc_id 与本条 doc_id 不符", "DEV-011",
                           lambda a, r: a["relations"][0].update(source_doc_id="999999"),
                           "relation_doc_mismatch")
        ok &= _expect_kind("F3 from_label 与端点实际类型不符", "DEV-012",
                           lambda a, r: a["relations"][0].update(from_label="Person"),
                           "relation_label_mismatch")
        ok &= _expect_kind("F5b BELONGS_TO 有效期格式非法（乱填照样报）", "DEV-015",
                           lambda a, r: _belongs_to(a, r, valid_from="2020-11-03",
                                                    valid_to="2020年1月"),
                           "relation_validity_format")
        ok &= _expect_kind("F6b 本体边界写「已新增……关系」（生效口径）", "DEV-017",
                           lambda a, r: a["ontology_boundary_log"].append(
                               {"case_id": "OB-DEV-017-1", "case_type": "relation_boundary",
                                "summary": "已新增第 10 条关系：委托关系，并写入图谱。",
                                "quote": _fake_quote(r["text"]), "chunk_id": r["chunk_id"],
                                "suggested_handling": "无"}),
                           "ontology_invention")
        ok &= _expect_pass("F5a BELONGS_TO 有效期写 null（正文无日期，视为未知）", "DEV-014",
                           lambda a, r: _belongs_to(a, r, valid_from=None, valid_to=None))
        ok &= _expect_pass("F5a2 BELONGS_TO 省略 valid_from／valid_to（同上）", "DEV-020",
                           _belongs_to)
        ok &= _expect_pass("F6a 本体边界写「建议新增……」（建议口径）", "DEV-016",
                           lambda a, r: a["ontology_boundary_log"].append(
                               {"case_id": "OB-DEV-016-1", "case_type": "relation_boundary",
                                "summary": "正文出现代销安排，9 条关系里没有对应项。",
                                "quote": _fake_quote(r["text"]), "chunk_id": r["chunk_id"],
                                "suggested_handling":
                                    "建议新增第 10 条关系：公司与代销机构之间的委托关系。"}))
        ok &= _expect_pass("F6c 本体边界写「待／记录」未定语境（同上放行）", "DEV-021",
                           lambda a, r: a["ontology_boundary_log"].append(
                               {"case_id": "OB-DEV-021-1", "case_type": "relation_boundary",
                                "summary": "待确认的事项。", "quote": _fake_quote(r["text"]),
                                "chunk_id": r["chunk_id"],
                                "suggested_handling": "记录：待确认是否新增第 10 条关系。"}))
        # F4 走 META 文本篡改（不走 json 槽位），单独一条路径。
        p = os.path.join(ws, "dev", "DEV-013.md")
        rr = dev_rows["DEV-013"]
        _write_annotation(p, _fake_annotation("DEV-013", rr["chunk_id"], rr["doc_id"],
                                              _fake_quote(rr["text"])))
        raw013 = open(p, encoding="utf-8").read()
        tampered = raw013.replace('"text_digest": "', '"text_digest": "0', 1)
        assert tampered != raw013, "META text_digest 替换失败"
        write_text_atomic(p, tampered)
        probs, _ = run_check(ws, eval_dir, ["dev"], cfg, verbose=False)
        hit = [x for x in probs if x["item_id"] == "DEV-013" and x["kind"] == "text_digest_mismatch"]
        ok &= _assert(bool(hit), "F4 META 的 text_digest 被改：check 报出 `text_digest_mismatch`",
                      hit[0]["field"] + "=" + hit[0]["value"] if hit else "未报出")
        write_text_atomic(p, raw013)
        _write_annotation(p, empty_annotation())
        # 对照组：这三条修前就拒、修后仍必须拒（防止改出新的漏检）。
        ok &= _expect_kind("对照 T8 to_ref 悬空仍拒", "DEV-018",
                           lambda a, r: a["relations"][0].update(to_ref="V9"),
                           "relation_ref_dangling")
        ok &= _expect_kind("对照 T9 quote 取自别块仍拒", "DEV-019",
                           lambda a, r: [d.update(quote="别块原文示例：这段文字不在本条目文本块里出现")
                                         for d in (a["entities"][0], a["events"][0],
                                                   a["relations"][0], a["times"][0])],
                           "quote_not_in_text")
        ok &= _expect_kind("对照 T10 事件 confidence=2.0 仍拒", "DEV-022",
                           lambda a, r: a["events"][0].update(confidence=2.0),
                           "confidence_range")

        print("-" * 72)
        print("[7] G1 一致性对照：同一个 confidence 取值，events[]／relations[] 必须同一口径")

        def _conf_case(slot, value):
            """把同一个 confidence 取值放进 events[]／relations[]，返回该条的问题列表。"""
            def mutate(a, r, slot=slot, value=value):
                if value is _OMIT:
                    a[slot][0].pop("confidence")
                else:
                    a[slot][0]["confidence"] = value
            return _case("DEV-024", mutate)[1]

        # 两条路径共用 `_check_confidence`：数值／数字字符串通过，非数值／越界都报 `confidence_range`。
        for _label, _value, _want in (("0.9（数值）", 0.9, []),
                                      ("\"0.9\"（数字字符串）", "0.9", []),
                                      ("\"abc\"（非数值）", "abc", ["confidence_range"]),
                                      ("2.0（越界）", 2.0, ["confidence_range"])):
            _ev = sorted({x["kind"] for x in _conf_case("events", _value)})
            _rel = sorted({x["kind"] for x in _conf_case("relations", _value)})
            ok &= _assert(_ev == _rel == _want,
                          "G1 confidence=%s → 两条路径错误码完全相同（%s）"
                          % (_label, "、".join(_want) if _want else "都通过"),
                          "events=%s；relations=%s" % (_ev or "[]", _rel or "[]"))
        # 「缺失」一档：relations 侧由证据三项检查报 `relation_evidence_missing`（只报这一条，
        # 不再补一条 confidence_*）；events 侧没有「证据三项」这一层，由 `_check_confidence`
        # 报 `confidence_empty`。两条路径都必须拒绝。
        _ev = sorted({x["kind"] for x in _conf_case("events", _OMIT)})
        _rel = sorted({x["kind"] for x in _conf_case("relations", _OMIT)})
        ok &= _assert(_ev == ["confidence_empty"] and _rel == ["relation_evidence_missing"],
                      "G1 confidence 键缺失 → 两条路径都拒绝，各报一条、不重复",
                      "events=%s；relations=%s" % (_ev or "[]（放行）", _rel or "[]（放行）"))

        print("-" * 72)
        print("[8] G2 本体边界「建议语境」：记录／备注不再是免罪符（只有真没断言已生效才放行）")

        def _oblog(text):
            def mutate(a, r, text=text):
                a["ontology_boundary_log"].append(
                    {"case_id": "OB-DEV-025-1", "case_type": "relation_boundary",
                     "summary": "合成：本体边界语境对照。", "quote": _fake_quote(r["text"]),
                     "chunk_id": r["chunk_id"], "suggested_handling": text})
            return mutate

        for _label, _text, _allow in (
                ("G2a「建议新增第 10 条关系：公司与代销机构之间的委托关系。」",
                 "建议新增第 10 条关系：公司与代销机构之间的委托关系。", True),
                ("G2b「疑似需要第 10 条关系。」", "疑似需要第 10 条关系。", True),
                ("G2c「记录：疑似需要第 10 条关系。」", "记录：疑似需要第 10 条关系。", True),
                ("G2d「记录：已新增第 10 条关系，并写入图谱。」",
                 "记录：已新增第 10 条关系，并写入图谱。", False),
                ("G2e「已新增第 10 条关系：委托关系，并写入图谱。」",
                 "已新增第 10 条关系：委托关系，并写入图谱。", False)):
            if _allow:
                ok &= _expect_pass(_label + "：建议／疑似语境，必须通过", "DEV-025", _oblog(_text))
            else:
                ok &= _expect_kind(_label + "：已生效口径，必须拒绝", "DEV-025", _oblog(_text),
                                   "ontology_invention")

        print("-" * 72)
        print("[9] G3 to_label 与端点实际类型不符 → `relation_label_mismatch`（补上 to 侧缺口）")

        def _to_label_bad(a, r):
            _belongs_to(a, r)                       # 端点 E2 的实际类型是 Industry
            a["relations"][0]["to_label"] = "Company"

        _p, _hit = _case("DEV-023", _to_label_bad)
        _lm = [x for x in _hit if x["kind"] == "relation_label_mismatch"]
        ok &= _assert(bool(_lm),
                      "G3 to_label=\"Company\" 而 to_ref=E2 实际是 Industry：报出 `relation_label_mismatch`",
                      "实测 %s" % (sorted({x["kind"] for x in _hit}) or "无"))
        ok &= _assert(bool(_lm) and _lm[0]["field"] == "relations[0].to_label",
                      "G3 这条问题落在 `relations[0].to_label`（确实是 to 侧被判定）",
                      ("证据行 → 文件=%s | item_id=%s | 字段=%s | 值=%s"
                       % (os.path.relpath(_lm[0]["file"], tmp), _lm[0]["item_id"],
                          _lm[0]["field"], _lm[0]["value"])) if _lm else "未报出")

        print("-" * 72)
        print("[10] 空槽位但 status 说完成 → check 必须拒绝")
        p = os.path.join(ws, "dev", "DEV-008.md")
        _write_annotation(p, _with_status(empty_annotation(), COMPLETED_STATUS))
        probs, _ = run_check(ws, eval_dir, ["dev"], cfg, verbose=False)
        hit = [x for x in probs if x["item_id"] == "DEV-008" and x["kind"] == "status_completed_but_empty"]
        ok &= _assert(bool(hit), "check 拒绝「status 完成但槽位全空」",
                      hit[0]["message"] if hit else "未报出")
        _write_annotation(p, empty_annotation())

        print("-" * 72)
        print("[11] H1 status=auto_annotated 必须带 provenance（防「自动标注被当成人工标注」）")

        def _auto_prov(prov=_OMIT):
            def mutate(a, r, prov=prov):
                a["status"] = AUTO_STATUS
                a["notes"] = "自检用的合成自动标注，不是真实标注。"
                if prov is not _OMIT:
                    a["provenance"] = prov
            return mutate

        _FULL_PROV = {"annotator": "llm", "model": "合成模型",
                      "prompt_version": "stage6-auto-annotate-v1.0", "temperature": 0}
        ok &= _expect_pass("H1a 带齐 model／prompt_version／temperature（temperature=0 合法）",
                           "DEV-026", _auto_prov(dict(_FULL_PROV)))
        ok &= _expect_kind("H1b 整个 provenance 缺失", "DEV-027", _auto_prov(),
                           "auto_provenance_missing")
        ok &= _expect_kind("H1c provenance 缺 temperature", "DEV-028",
                           _auto_prov({"annotator": "llm", "model": "合成模型",
                                       "prompt_version": "stage6-auto-annotate-v1.0"}),
                           "auto_provenance_missing")
        ok &= _expect_kind("H1d provenance 缺 prompt_version", "DEV-029",
                           _auto_prov({"annotator": "llm", "model": "合成模型", "temperature": 0}),
                           "auto_provenance_missing")
        ok &= _expect_kind("H1e provenance 缺 model", "DEV-030",
                           _auto_prov({"annotator": "llm",
                                       "prompt_version": "stage6-auto-annotate-v1.0",
                                       "temperature": 0}),
                           "auto_provenance_missing")
        # 对照：同一条内容换成 human_annotated 且不带 provenance —— 正是「人工标注」的合法写法，
        # 不许报 auto_provenance_missing（守卫只盯 auto_annotated，不能误伤人工标注）。
        ok &= _expect_pass("H1f 对照：human_annotated 不带 provenance 照样通过（守卫不误伤人工）",
                           "DEV-032", lambda a, r: None)
        # 对照：status 仍是三个合法值之外 → 必须仍报 status_unknown
        ok &= _expect_kind("H1g 对照：status=\"machine_annotated\" 仍报 status_unknown", "DEV-033",
                           lambda a, r: a.update(status="machine_annotated"), "status_unknown")

        print("-" * 72)
        print("[12] H2 merge 拒绝把 auto_annotated 写回交付文件（`merge_refuses_auto`）")
        _ap = os.path.join(ws, "dev", "DEV-031.md")
        _arr = dev_rows["DEV-031"]
        _aann = _fake_annotation("DEV-031", _arr["chunk_id"], _arr["doc_id"],
                                 _fake_quote(_arr["text"]))
        _aann["status"] = AUTO_STATUS
        _aann["provenance"] = dict(_FULL_PROV)
        _write_annotation(_ap, _aann)
        _before_auto = open(os.path.join(eval_dir, "dev.jsonl"), encoding="utf-8").read()
        _rc_auto = cmd_merge(argparse.Namespace(eval_dir=eval_dir, workspace=ws, split="dev",
                                                force=False))
        _after_auto = open(os.path.join(eval_dir, "dev.jsonl"), encoding="utf-8").read()
        ok &= _assert(_rc_auto != 0, "merge 返回非零（拒绝写盘）", "退出码 %s" % _rc_auto)
        ok &= _assert(_before_auto == _after_auto,
                      "dev.jsonl 逐字节未动（交付文件槽位冻结契约）", "写盘前后 SHA-256 一致")
        _rc_auto_f = cmd_merge(argparse.Namespace(eval_dir=eval_dir, workspace=ws, split="dev",
                                                  force=True))
        ok &= _assert(_rc_auto_f != 0
                      and open(os.path.join(eval_dir, "dev.jsonl"), encoding="utf-8").read()
                      == _before_auto,
                      "`--force` 也不放行（冻结契约是硬守卫，不是可越过的 check 问题）",
                      "退出码 %s" % _rc_auto_f)
        # 对照：把同一条改成 human_annotated 后 merge 必须正常写盘（守卫不误伤人工标注路径）。
        _aann["status"] = COMPLETED_STATUS
        _aann.pop("provenance")
        _write_annotation(_ap, _aann)
        _rc_human = cmd_merge(argparse.Namespace(eval_dir=eval_dir, workspace=ws, split="dev",
                                                 force=False))
        ok &= _assert(_rc_human == 0
                      and json.loads(_line_of(eval_dir, "dev.jsonl", "DEV-031"))["annotation"]["status"]
                      == COMPLETED_STATUS,
                      "对照：同一条改成 human_annotated 后 merge 正常写回（守卫不误伤）",
                      "退出码 %s" % _rc_human)
        _write_annotation(_ap, empty_annotation())

        print("-" * 72)
        print("[13] 真实 dev.jsonl／test.jsonl 全程未被触碰")
        after = {n: sha256_hex(open(os.path.join(real_eval, n), "rb").read().decode("utf-8"))
                 for n in ("dev.jsonl", "test.jsonl")}
        ok &= _assert(before == after, "真实 jsonl 字节未变（SHA-256）",
                      "  ".join("%s=%s…" % (k, v[:12]) for k, v in after.items()))
        print("-" * 72)
        print("自检%s" % ("**全部通过**" if ok else "**存在失败项**"))
        return 0 if ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _assert(cond, label, evidence) -> bool:
    print("  [%s] %s —— %s" % ("OK" if cond else "FAIL", label, evidence))
    return bool(cond)


def _ws_digest(ws: str) -> str:
    """工作区内容摘要（幂等比对用）。

    **排除两张「动作台账」**（`_导出台账.json`／`_合并记录.json`）与 `_备份\\`：台账记的是
    「这一次跑了什么」（新建几条／跳过几条），按定义就会随动作变化，不是条目内容。
    条目本身（`<split>\\*.md`）与 `说明.md` 都在摘要里。
    """
    skip_files = {LEDGER_NAME, "_合并记录.json"}
    parts = []
    for root, _dirs, files in os.walk(ws):
        if BACKUP_DIRNAME in root.split(os.sep):
            continue
        for f in sorted(files):
            if f in skip_files:
                continue
            p = os.path.join(root, f)
            parts.append(os.path.relpath(p, ws) + ":" + sha256_hex(open(p, "rb").read().decode("utf-8")))
    return sha256_hex("\n".join(sorted(parts)))


def _fake_quote(text: str) -> str:
    """合成测试用的引用：取本块去掉空白后的前 24 个字符（**只在自检的临时副本里用**）。"""
    s = norm_ws(text)
    return s[:24] if len(s) >= 12 else (s + "0123456789")[:12]


def _fake_annotation(item_id, chunk_id, doc_id, quote):
    """**合成**的、结构合法的假标签：名字里带「合成」，只为自检，绝不写进任何真实条目。"""
    a = empty_annotation()
    a["status"] = COMPLETED_STATUS
    a["entities"] = [{"entity_type": "Company", "entity_ref": "E1", "quote": quote,
                      "chunk_id": chunk_id, "stock_code": "000000",
                      "company_name": "【合成测试公司】", "short_name": "合成测试",
                      "aliases": [], "exchange": "上交所"}]
    a["events"] = [{"event_ref": "V1", "event_id": "EVT-%s-1" % item_id, "event_type": "业绩",
                    "event_name": "【合成测试事件】", "event_time": None,
                    "description": "自检用合成事件，不是标注", "confidence": 0.5,
                    "participants": [{"entity_ref": "E1", "role": "主体"}],
                    "quote": quote, "chunk_id": chunk_id}]
    a["relations"] = [{"relation": "PARTICIPATES_IN", "from_label": "Company", "from_ref": "E1",
                       "to_label": "Event", "to_ref": "V1", "role": "主体",
                       "source_doc_id": doc_id, "source_chunk_id": chunk_id, "confidence": 0.5,
                       "quote": quote}]
    a["times"] = [{"time_type": "event_time", "value": "2026-09-23", "quote": quote}]
    a["ontology_boundary_log"] = []
    a["notes"] = "自检用的合成标签，不是真实标注。"
    return a


def _write_annotation(path: str, annotation) -> None:
    raw = open(path, encoding="utf-8").read()
    i = raw.find(MARK_ANN_BEGIN) + len(MARK_ANN_BEGIN)
    j = raw.find(MARK_ANN_END)
    body = "\n```json\n%s\n```\n" % json.dumps(annotation, ensure_ascii=False, indent=2)
    write_text_atomic(path, raw[:i] + body + raw[j:])


def _fill_annotation(path: str, annotation) -> None:
    _write_annotation(path, annotation)


def _with_status(annotation, status):
    ann = OrderedDict(annotation)
    ann["status"] = status
    return ann


def _line_of(eval_dir, name, item_id):
    for line in open(os.path.join(eval_dir, name), encoding="utf-8"):
        if line.strip() and json.loads(line)["item_id"] == item_id:
            return line.rstrip("\n")
    return ""


def _orig_line(real_eval, name, item_id):
    return _line_of(real_eval, name, item_id)


def _annotation_only_diff(orig_line, new_line):
    """逐字节比较两行，返回差异描述；若只有 annotation 不同则返回空串。"""
    a, b = json.loads(orig_line, object_pairs_hook=OrderedDict), json.loads(new_line, object_pairs_hook=OrderedDict)
    if list(a.keys()) != list(b.keys()):
        return "字段顺序或字段集合变了：%s vs %s" % (list(a.keys()), list(b.keys()))
    bad = [k for k in a if k != "annotation" and a[k] != b[k]]
    if bad:
        return "除 annotation 外还有字段变化：%s" % "、".join(bad)
    return ""


# ==========================================================================
# 10. CLI
# ==========================================================================
def build_parser():
    p = argparse.ArgumentParser(
        prog="标注助手.py",
        description="第 6 阶段抽取评测集（v2.1）的人工标注工作台：导出工作区、校验、写回、统计。"
                    "离线运行，不调模型，不产生任何标签。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--eval-dir", default=None,
                        help="评测集目录，默认由 config 推出：阶段05-数据准备\\数据集\\抽取评测集\\v2.1")
        sp.add_argument("--workspace", default=None, help="工作区目录，默认 <评测集目录>\\标注工作区")
        sp.add_argument("--split", default="all", choices=["all", "dev", "test"], help="只处理某个 split")

    sp = sub.add_parser("export", help="展开/刷新标注工作区（不覆盖已填写的条目）")
    common(sp)
    sp.add_argument("--refresh", action="store_true", help="重写仍是空模板的条目（已填写的一律不碰）")
    sp.add_argument("--overwrite", action="store_true",
                    help="重写**已填写**的条目（先备份到 _备份\\）；慎用")
    sp.set_defaults(func=cmd_export)

    sp = sub.add_parser("check", help="校验已填写的标注，逐条打印证据；有问题退出码 1")
    common(sp)
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("merge", help="写回 dev.jsonl／test.jsonl（先备份；check 不过则拒绝）")
    common(sp)
    sp.add_argument("--force", action="store_true", help="check 有问题时也写盘")
    sp.set_defaults(func=cmd_merge)

    sp = sub.add_parser("stats", help="按 split 统计覆盖率与各类实体／事件／关系条数")
    common(sp)
    sp.set_defaults(func=cmd_stats)

    sp = sub.add_parser("selftest", help="自检：临时目录里走一遍导出→校验→往返→负向用例")
    sp.add_argument("--eval-dir", default=None, help="只读用的真实评测集目录（默认同上）")
    sp.set_defaults(func=cmd_selftest)
    return p


def setup_console() -> None:
    """控制台默认 GBK，中文与项目里的中文路径会乱码（工具\\README.md 作业纪律一）。

    只改本进程的标准输出编码，不动系统设置。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
