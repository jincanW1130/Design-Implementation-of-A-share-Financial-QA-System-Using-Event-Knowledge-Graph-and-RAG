# -*- coding: utf-8 -*-
"""工具\标注结构校验.py —— 第 6 阶段抽取评测集的**标注结构校验内核**。

本模块是**校验内核**，不是工作台。原「人工标注工作台」的工具名、子命令与槽位填充流程，
已随「人工标注」这一参照概念的删除一并撤销（**本课题不存在「人工」这个参照概念**）。
它只保留两类东西：

1. **公开校验入口** `validate_annotation(record, cfg=None, path=None)`——函数名、参数、
   返回结构与**错误码与撤销前逐字一致**（`工具\抽检助手.py` 的打印文案引用了它）。
   返回问题列表（每项含 `kind`／`file`／`item_id`／`field`／`value`／`message`），空列表即通过。
2. **解析／摘要小工具与 schema 常量**：`parse_item_file`（解析条目文件的三个锚点块）、
   `render_item`（渲染条目文件的非标注部分）、`norm_ws`／`text_digest`／`sha256_hex`、
   `ITEM_SCHEMA`／`CASE_TYPES`／`ENTITY_PER_TYPE_FIELDS` 等。
   `交付物/03-代码\抽取与图谱\auto_annotate*.py` 与 `工具\抽检助手.py` 共用这一份，不另立第二套。

**评测口径（本文件所在的唯一口径）**
------------------------------------
本课题的评测**一律为模型口径**：**抽取以模型参照集为参照物、问答以跨厂商模型评审为口径**。

* **模型参照集是参照物，不是金标准**；指标一律写「**模型参照集口径下的抽取表现**」，
  **不得**写成「准确率」「标准答案」「ground truth」。
* 参照集与抽取器**同端点同模型家族** ⇒ 同源自证风险被降低但**没有消除**，
  两者一致**不构成独立验证**。
* 因此本内核把 `status` 收成**唯一一个合法取值** `auto_annotated`，并要求它带 `provenance`
  （model／prompt_version／temperature）自证产者与提示词版本——这是「**不得把模型产物写成
  金标准**」这道保护性断言的机器实现。交付的 `dev.jsonl`／`test.jsonl` **不带任何标注字段**。

零联网、零模型调用：`config.py` 只 import hashlib／json／os，模块级不联网、不读密钥。
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import sys
import tempfile
from collections import Counter, OrderedDict


# ==========================================================================
# 0. 常量与路径
# ==========================================================================
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_THIS_DIR)

CONFIG_PATH = os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "config.py")
KERNEL_RELPATH = "工具\标注结构校验.py"

# `status` 的**唯一**合法取值：模型参照集。
# 本课题不存在其它来源的抽取参照物——没有「待人工标注」这一状态，交付的
# `dev.jsonl`／`test.jsonl` 不带任何标注字段（260 条只有抽样字段），
# 参照物一律由模型产出、并靠 provenance 自证产者与提示词版本。
AUTO_STATUS = "auto_annotated"
AUTO_PROVENANCE_REQUIRED = ("model", "prompt_version", "temperature")

# `ontology_boundary_log[].case_type` 的建议取值：**config.py 里没有这个枚举**，
# 值域登记在 `分层统计.json` → `annotation_schema.ontology_boundary_log`，
# 故在此处登记来源、不当作本体常量使用。
CASE_TYPES = [
    "event_type_boundary", "relation_boundary", "role_boundary", "company_out_of_scope",
    "relation_insufficient", "time_ambiguous", "chunk_boundary",
]
CASE_TYPES_SOURCE = "分层统计.json 的 annotation_schema.ontology_boundary_log"

# 各类实体的必填属性：**config.py 没有这个表**（它只有 GRAPH["node_columns"] 那个扁平列清单），
# 来源是 `分层统计.json` → `annotation_schema.entities.per_type_fields`。
# 通用字段 `entity_type`／`entity_ref`／`quote`／`chunk_id` 不在本表里，单独判。
ENTITY_PER_TYPE_FIELDS = {
    "Company": ["stock_code", "company_name", "short_name", "aliases", "exchange"],
    "Person": ["person_id", "person_name", "aliases", "role_title"],
    "Industry": ["industry_code", "industry_name", "level"],
    "Institution": ["institution_id", "institution_name", "institution_type"],
    "Policy": ["policy_id", "policy_name", "issuer", "publish_date"],
}
ENTITY_COMMON_FIELDS = ["entity_type", "entity_ref", "quote", "chunk_id"]

# 机器读锚点。**不得改动**：磁盘上的模型参照集工作区按这套锚点解析，改了就读不出来。
META_RE = re.compile(r"<!--\s*HANDANN-META:\s*(\{.*?\})\s*-->", re.S)
MARK_TEXT_BEGIN, MARK_TEXT_END = "<!-- HANDANN:TEXT:BEGIN -->", "<!-- HANDANN:TEXT:END -->"
MARK_ANN_BEGIN, MARK_ANN_END = "<!-- HANDANN:ANNOTATION:BEGIN -->", "<!-- HANDANN:ANNOTATION:END -->"

ITEM_SCHEMA = "stage6-handann-item-1.0"

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
    """标注块的**键序骨架**（键序与模型参照集产物一致）。"""
    return OrderedDict([
        ("status", AUTO_STATUS),
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
        "- `status`：一律 `%s`（模型参照集口径：本课题的抽取参照物一律由模型产出）；必须带 `provenance` 块的 `model`／`prompt_version`／`temperature` 三项，自证产者与提示词版本。" % AUTO_STATUS,
        "- `entities`（数组）：`entity_type` 取 `%s`（共 5 类，本体共 6 类：`%s`）——**`Event` 不写进"
        "这里**，事件一律写 `events[]`；**不新增 Product（产品）／Location（地点）**。每条另填 "
        "`entity_ref`（本条内编号 `E1`／`E2`…，从 1 开始）、`quote`（%d～%d 字符，须逐字出现在下面"
        "「一、」的块里）、`chunk_id`（默认等于本条 chunk_id）。按 `entity_type` 另填必填属性"
        "（见 `分层统计.json` 的 `annotation_schema.entities.per_type_fields`）。" % (etypes, etypes_all, qmin, qmax),
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
        "<!-- 本文件由 %s 渲染生成。**只修改「三、标注槽位」的那个 json 块**。\n"
        "     上面 17 项与下面两段文本都是抽取评测集抽样时写下的字段，改了就和 dev.jsonl／test.jsonl "
        "对不上（结构校验会报）。 -->" % KERNEL_RELPATH
    )
    pointer = (
        "> 规则：标注结构与字段枚举的落点是 `%s\\分层统计.json` 的 `annotation_schema`"
        "（entities／events／relations／times／ontology_boundary_log／notes，与 `代码\\抽取与图谱\\config.py` 同源）。\n"
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
    """槽位是否仍与空骨架逐键相等（即模型尚未写入）。"""
    if not isinstance(annotation, dict):
        return False
    skel = empty_annotation()
    if list(annotation.keys()) != list(skel.keys()):
        return False
    return json.loads(json.dumps(annotation, ensure_ascii=False)) == json.loads(
        json.dumps(skel, ensure_ascii=False))
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
                             "Event 不写进 entities[]，事件一律写 events[]（分层统计.json 的 annotation_schema.entities）")
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
                             "分层统计.json 的 annotation_schema.entities.per_type_fields：`%s` 的必填属性" % et)
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
                             "分层统计.json 的 annotation_schema.events：每条事件必填")
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
                         "（分层统计.json 的 annotation_schema.relations、config.RELATION_SCHEMA）")
            continue
        for key in ("from_label", "from_ref", "to_label", "to_ref"):
            if key not in rel or rel.get(key) in (None, ""):
                problems.add("relation_field_missing", path, iid, f + "." + key, rel.get(key),
                             "分层统计.json 的 annotation_schema.relations：每条关系填 from_label／from_ref／to_label／to_ref")
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
                         "time_type 取 %s（分层统计.json 的 annotation_schema.times）" % "／".join(legal))
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
                             "分层统计.json 的 annotation_schema.ontology_boundary_log：每条登记填 case_id／case_type／summary／quote／"
                             "chunk_id／suggested_handling")
        for hit in _looks_like_inventing(entry):
            problems.add("ontology_invention", path, iid, f, hit,
                         "协议第八节：归不进本体的情形**只登记、不新增**——不得新增／改名／合并实体类型、"
                         "事件类型、关系类型，不得复活 INVOLVES，不得引入 Product 与 Location")
        _check_chunk_id(problems, path, iid, f + ".chunk_id", entry, chunk_id)
        _check_quote(problems, "quote_not_in_text", path, iid, f + ".quote", entry.get("quote"),
                     text_norm, qmin, qmax)


def _annotation_status(annotation) -> dict:
    """一条标注的**事实分类**（不含任何问题）：`工具\抽检助手.py` 的计数与 `validate_annotation` 的判据共用这一份。

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

    这条守卫的唯一目的是**防止模型参照集被当成非模型来源的参照物**：本课题的抽取参照物
    一律由模型产出，`status = auto_annotated` 与其它任何来源在结构上无法区分，只能靠
    因此这里判的是「键缺失／是 None／是空串」，不是真值。
    """
    prov = annotation.get("provenance")
    if not isinstance(prov, dict):
        problems.add("auto_provenance_missing", path, item_id, "provenance", prov,
                     "status=%s 必须带 provenance（%s）——缺了它，模型参照集就无法自证产者与提示词版本"
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
    """`status` 与槽位的一致性。

    现行口径下 `status` **只有唯一一个合法取值** `auto_annotated`：本课题的抽取参照物一律
    由模型产出（模型参照集），不存在其它来源的参照物。因此：

    * `auto_annotated` → 另加 `_check_auto_provenance` 的产者自证守卫，并要求非空（或
      `notes` 写明 `empty_but_checked: true`）；
    * **其它任何 status**（无论叫什么）→ 一律 `status_unknown` 判负。

    **这一改只收紧不放宽**：旧实现接受三个 status、且允许「未填写」状态带着空槽位通过；
    现在这类输入一律 FAIL，`auto_annotated` 空块也一律 FAIL。
    """
    status = info["status"]
    if status == AUTO_STATUS:
        _check_auto_provenance(problems, path, item_id, annotation)
        if not info["non_empty"] and not info["has_note"]:
            problems.add("status_completed_but_empty", path, item_id, "status", status,
                         "status=%s 说已完成，但 entities／events／relations／times／"
                         "ontology_boundary_log 全空、notes 也空；本块确实没有可标事实时，"
                         "四个槽位留空并在 notes 写 `empty_but_checked: true` 加理由" % AUTO_STATUS)
    else:
        problems.add("status_unknown", path, item_id, "status", status,
                     "status 只能是 %s（模型参照集口径：本课题的抽取参照物一律由模型产出，"
                     "不存在其它来源的参照物）" % AUTO_STATUS)




def validate_annotation(record, cfg=None, path=None):
    """**公开校验入口**：对一条**内存里**的标注记录跑与 `工具\抽检助手.py check` 完全相同的槽位校验。

    `record` 需要：`item_id`、`chunk_id`、`doc_id`、`text`、`annotation`（`annotation` 必须是 dict）。
    返回问题列表（每项含 `kind`／`file`／`item_id`／`field`／`value`／`message`），空列表即通过。

    **边界**：只判「标注本身」是否合口径。文件级的问题（文件名与 `item_id` 不一致、split 不符、
    `item_id` 重复或不在 jsonl 里、抽样字段被改、META 的 `text_digest` 不符）属于**工作区文件**，
    由 `工具\抽检助手.py` 负责——该工具与 `代码\\抽取与图谱\\auto_annotate.py` 共用本函数这一份校验源，
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
