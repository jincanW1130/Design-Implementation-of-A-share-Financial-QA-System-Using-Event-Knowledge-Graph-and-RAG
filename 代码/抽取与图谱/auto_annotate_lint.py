# -*- coding: utf-8 -*-
r"""auto_annotate_lint.py —— 自动标注（模型参照集）的**离线 lint**：只读产物，不调模型。

## 它是干什么的

对「自动标注」的**三套参照集**（`自动标注\`＝pro 版、`自动标注_flash\`＝flash 原版、
`自动标注\提准\`＝flash 提准后）逐条扫规则，输出**命中清单**（每条命中都带 `item_id`／定位／
原文片段），供定向修复与三集合对照使用。
本工具**不改任何标注**、不调任何模型、不写回数据集。

## 规则（硬规则＝定义性违规；软规则＝提示性，由修复阶段裁决）

硬（10 条）：`R1_code_format`／`R2_code_source`／`R4_out_of_scope_logged`／
`R5_participants_relation_mirror`／`R6_times_event_mirror`／
`R7a_quote_fabricated`／`R8_issued_by_role_conflict`／`R9_event_without_participant`／
`R10_duplicate_event_in_item`／`R11_boundary_case_type`。
软（5 条）：`R3_relation_endpoints_in_scope`（**2026-09-27 由硬降级为软**）／
`S1_quote_not_supporting_name`／`S2_procedural_event_name`／`S3_time_not_in_text`／
`S4_no_subject_role`（细分 a 强提示＝无 `ISSUED_BY`；b 弱提示＝有 `ISSUED_BY`）。

规则 v1.2（2026-09-27，作者对 5 处 `disputed` 的裁定）——三处判据修正，不改任何标注内容；
三处都是**作者的规则缺陷**，由被测模型在 `disputed` 里指出（不是「模型不配合」）：

* `R9_event_without_participant` 加 **`ISSUED_BY` 豁免**：事件只要有 `ISSUED_BY` 边（不问事件类型），
  `participants` 为空即**不判违规**——依据《10》第4.5.2节 与《标注说明》第6.2节
  「发布／作出方只写 ISSUED_BY，不再写 PARTICIPATES_IN」。只在「既无 `participants`、又无
  `ISSUED_BY`」时命中。适用于 DEV-057／TEST-041／TEST-184。
* `R6_times_event_mirror` **收窄**：只在两种情形命中——(a) `events[]` 为空而 `times[]` 含
  `time_type=event_time` 的项；(b) 某事件 `event_time` 非空、而 `times[]` 里没有同值项。
  「`times[]` 记录多个彼此独立的日期、事件 `event_time` 为 null」是**多日期安排型公告的正确写法**，
  不再判违规。适用于 TEST-017。
* `R3_relation_endpoints_in_scope` **降级为软提示**：公司间关系与 `BELONGS_TO` 的端点不在 105 家名单内
  只提示、不判硬违规——名单约束是**图谱写入层**的约束（写图时跳过并计数），标注层的事实仍由
  原文逐字证据支撑；该情形已由 `R4_out_of_scope_logged`（`company_out_of_scope` 登记）覆盖。
  适用于 TEST-167。

作者本轮三处裁定（2026-09-27，规则升级 v1.1，前三条是**改判据**，不改任何标注内容）：

* `R2_code_source`：在 105 家名单／注册全称表之上补一层 **NFKC ＋ 常用简繁／异体单字折叠**
  （只做同义单字映射，**不动数字与括号语义**）。繁体书写面折叠后能核到该代码即**不再命中 R2**；
  但这类条目**逐条登记**进 `简繁书写面登记`（item_id／书写面／折叠后／条目填的代码／折叠后能核到的代码），
  因为「代码正确、书写面是繁体」对下游消歧仍有意义。**港股代码（如 `01211, 81211`／`3288`）继续命中
  R1／R2**——那是真违规（本项目 A 股口径）。
* `R4_out_of_scope_logged`：**收窄到图谱端点**——只看 `relations[]` 的 `from_ref`／`to_ref` 两端
  （端点进图谱、必须有节点）。不再把「任何实体」都算；名单内公司但 `stock_code` 留空**不算**名单外。
* `R7a_quote_fabricated`：两层判据，同一把尺子（**只去空白**，不做 NFKC 宽度折叠，避免把
  「（特殊普通合伙）」与「(特殊普通合伙)」这类**书写面差异**抹平）：
  A 层＝实体的**类型名键**（`company_name`／`person_name`／`industry_name`／`institution_name`／
  `policy_name`）在本块 `text` 与全篇 `doc_text` 里都不是连续书写面（**指代性别名**如「公司」「发行人」
  「本公司」只能登记、不能救它）；B 层＝名字键**与全部别名**都不可定位。两层取并集，命中里标明层号。
  作者独立尺度在 pro 版 260 条里命中的 TEST-047／TEST-185／TEST-199 正是这个并集（见 `lint报告.md`
  「R7a 逐条判定依据」）。

规则依据：`阶段05-数据准备\数据集\抽取评测集\v2.1\标注说明.md` 第五节（事件必须有参与主体）、
第 6.2 节（`ISSUED_BY` 与 `监管方` 不并写）、第 7 节第 4 条（三条公司间关系两端必须是 105 家名单内公司）、
第八节（`case_type` 建议枚举）；公司代码与名称的核对表来自 `代码\数据准备\config.py` 的 105 家
`COMPANIES` 与 `代码\抽取与图谱\company_registered_names.py` 的注册全称（均由
`build_company_aliases.py` 用实据建档）——**A 股口径，港股代码一律违规**。

## 用法

```powershell
python 代码\抽取与图谱\auto_annotate_lint.py lint --version pro     # 扫 pro 版
python 代码\抽取与图谱\auto_annotate_lint.py lint --version flash   # 扫 flash 版
python 代码\抽取与图谱\auto_annotate_lint.py lint --version flash.repaired  # 扫 flash 提准后
python 代码\抽取与图谱\auto_annotate_lint.py report                  # 三集合并列对照，写 lint报告.md
python 代码\抽取与图谱\auto_annotate_lint.py selftest                # 每条规则正反自测（退出码 0／1）
```

落点：默认 `阶段05-数据准备\数据集\抽取评测集\v2.1\自动标注\提准\`（可用 `--out-dir` 覆盖），
写 `lint_命中_<pro|flash|flash.repaired>.json`（逐条命中）与 `lint报告.md`（规则修正记录、
三集合同规则对照、集合级统计、按 split 分布、每规则 2～3 个例子）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import re
import sys
import unicodedata
from collections import Counter, OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  （代码\抽取与图谱\config.py）

ROOT = config.ROOT
HANDANN_PATH = os.path.join(ROOT, "工具", "标注助手.py")
EVAL_SUBDIR = "抽取评测集"
OUT_DIR_DEFAULT = os.path.join("自动标注", "提准")
LINT_SCHEMA = "stage6-auto-annotate-lint-1.0"

VERSIONS = OrderedDict([
    ("pro", OrderedDict([("dirname", "自动标注"), ("model", "deepseek-v4-pro"),
                         ("suffix", ".auto"),
                         ("prompt_version", "stage6-auto-annotate-v1.0"),
                         ("desc", "deepseek-v4-pro（异模型，pro 版）")])),
    ("flash", OrderedDict([("dirname", "自动标注_flash"), ("model", "deepseek-flash"),
                           ("suffix", ".auto"),
                           ("prompt_version", "stage6-auto-annotate-v1.0-flash"),
                           ("desc", "deepseek-flash（与抽取器同模型，flash 原版）")])),
    ("flash.repaired", OrderedDict([
        ("dirname", os.path.join("自动标注", "提准")), ("model", "deepseek-flash"),
        ("suffix", ".auto.repaired"),
        ("prompt_version", "stage6-auto-annotate-flash-repair-v1.0（命中条目）＋"
                           "stage6-auto-annotate-v1.0-flash（其余条目）"),
        ("desc", "flash 版经定向修复后（提准产物；与 flash 同模型，2026-09-27 参照集候选）")])),
])


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handann = _load_module(HANDANN_PATH, "stage6_handann_lint")   # norm_ws／CASE_TYPES 的唯一来源

CASE_TYPES = list(handann.CASE_TYPES)

HARD_RULES = [
    ("R1_code_format", "Company 的 `stock_code` 非空时必须是 6 位数字（`^\\d{6}$`）；港股代码一律违规（A 股口径）"),
    ("R2_code_source", "`stock_code` 非空时，公司名（含注册全称／简称／别名，**简繁／异体折叠后**）必须能在 105 家名单或别名表里核到该代码"),
    ("R4_out_of_scope_logged", "**图谱端点**（`relations[].from_ref`／`to_ref` 指向的公司）里出现名单外公司时，必须在 `ontology_boundary_log` 里登记 `case_type=company_out_of_scope`（只管端点，不再管「任何实体」）"),
    ("R5_participants_relation_mirror", "`events[].participants[]` 与 `relations[]` 的 `PARTICIPATES_IN` 必须一一对应、同一 `(entity_ref, event_ref)` 的 `role` 相同"),
    ("R6_times_event_mirror", "只在两种情形命中：(a) `events[]` 为空而 `times[]` 含 `time_type=event_time` 的项；(b) 某事件 `event_time` 非空、而 `times[]` 里没有同值项（多日期安排型公告——有事件、`event_time=null`、`times[]` 记多个彼此独立的日期——**不命中**）"),
    ("R7a_quote_fabricated", "两层（取并集）：A＝类型名键不是本块／全篇的连续书写面（指代性别名救不了）；B＝名字键与全部别名都不可定位"),
    ("R8_issued_by_role_conflict", "某机构既是同一事件的 `ISSUED_BY` 终点、又出现在该事件的 `PARTICIPATES_IN`（或 `role=监管方`）"),
    ("R9_event_without_participant", "事件**既**没有 `participants`、**又没有** `ISSUED_BY` 边（发布／作出方只写 `ISSUED_BY`、不再写 `PARTICIPATES_IN`——《10》4.5.2／《标注说明》6.2）"),
    ("R10_duplicate_event_in_item", "同一条目内出现 `event_type`＋规范化 `event_name` 完全相同的事件"),
    ("R11_boundary_case_type", "`ontology_boundary_log[].case_type` 不在《标注说明》第八节的建议枚举内"),
]

SOFT_RULES = [
    ("R3_relation_endpoints_in_scope", "**（2026-09-27 由硬降级为软）**`SUPPLIES`／`CUSTOMER_OF`／`COMPETES_WITH`／`BELONGS_TO` 的两端不是名单内公司时只提示——名单约束属**图谱写入层**（写图时跳过并计数），标注层的事实由原文逐字证据支撑；该情形另由 `R4_out_of_scope_logged` 要求登记 `company_out_of_scope`"),
    ("S1_quote_not_supporting_name", "实体名字键（含别名）不在本块、但在全篇 → 提示换 quote 或补跨块说明"),
    ("S2_procedural_event_name", "事件名呈程序／元事件式（「…议案获…审议通过」「…公告」「…进展」「…通知」）→ 按 `EVENT_NOT_EVENT_RULES` 复核"),
    ("S3_time_not_in_text", "事件 `event_time` 非空，但本块与全篇都找不到该日期的书写形态"),
    ("S4_no_subject_role", "某事件的参与方里没有 `role=主体`（a 强提示＝无 `ISSUED_BY`；b 弱提示＝有 `ISSUED_BY`）"),
]

ALL_RULES = [r for r, _ in HARD_RULES] + [r for r, _ in SOFT_RULES]
HARD_RULE_IDS = {r for r, _ in HARD_RULES}


def is_hard_rule(rule) -> bool:
    """硬／软由规则清单决定，**不看名字前缀**（`R3_*` 已降级为软提示）。"""
    return rule in HARD_RULE_IDS


# --------------------------------------------------------------------------
# 路径与读写
# --------------------------------------------------------------------------
def eval_dir() -> str:
    return os.path.join(config.DATASET_ROOT, EVAL_SUBDIR, config.DATASET_VERSION)


def version_dir(label: str) -> str:
    return os.path.join(eval_dir(), VERSIONS[label]["dirname"])


def default_out_dir() -> str:
    return os.path.join(eval_dir(), OUT_DIR_DEFAULT)


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def norm_ws(text) -> str:
    return handann.norm_ws(text)


def _fold(text) -> str:
    """文本比对用的折叠：`NFKC`（全角→半角）＋ 去空白。只用于**命中/不命中**的判定，
    不改任何标注内容。"""
    return norm_ws(unicodedata.normalize("NFKC", str(text or "")))


# --------------------------------------------------------------------------
# 简繁／异体折叠：**表已迁到同目录的 `fold_variants.py`**（2026-10-02，理由见该模块 docstring）。
# 本文件原先把表内联在这里，但本文件跨目录 `import 工具\标注助手.py`，导致
# `config.normalize_entity_name()` 惰性导入本模块时会连带依赖 `工具\`，
# 而第 6 阶段门禁的镜像不复制 `工具\` ⇒ 镜像内导入失败。
# 迁移后本文件改为**从同目录模块导入并把原名再导出**，本文件内既有引用（fold_simp／S2T_MAP）
# 一行都不需要改。
# --------------------------------------------------------------------------
from fold_variants import (  # noqa: E402,F401
    S2T_MAP, _S2T_PAIRS_TEXT, _build_s2t_map, fold_simp,
)



def write_text_atomic(path: str, text: str) -> None:
    # M-8：裸文件名（dirname == ""）会让下游 helper 的 os.makedirs 抛
    # FileNotFoundError；在本函数统一转绝对路径，三个调用点一并安全。
    handann.write_text_atomic(os.path.abspath(path), text)


def read_jsonl(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line.strip():
                rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------------
# 公司核对表：105 家名单（代码\数据准备\config.py）＋ 注册全称（company_registered_names.py）
# --------------------------------------------------------------------------
def _name_surfaces_of_company_entry(entry) -> set:
    out = set()
    for key in ("name", "short_name", "registered_name", "company_name"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
    return out


def build_company_table() -> dict:
    """code → {"names": set(归一化后的书写面), "raw": set(原始书写面), "sources": set(来源)}。"""
    dp = _load_module(os.path.join(ROOT, "代码", "数据准备", "config.py"), "stage5_dataprep_config_lint")
    crn = _load_module(os.path.join(_HERE, "company_registered_names.py"), "stage6_registered_names_lint")
    table = OrderedDict()

    def _add(code, names, source):
        code = str(code or "").strip()
        if not code:
            return
        slot = table.setdefault(code, {"names": set(), "raw": set(), "sources": set()})
        slot["sources"].add(source)
        for n in names:
            if isinstance(n, str) and n.strip():
                slot["raw"].add(n.strip())
                slot["names"].add(config.normalize_entity_name(n))

    for c in getattr(dp, "COMPANIES", []):
        _add(c.get("code"), _name_surfaces_of_company_entry(c), "105家名单")
    for code, entry in (getattr(crn, "REGISTERED_NAMES", {}) or {}).items():
        _add(code, _name_surfaces_of_company_entry(entry), "注册全称表")
    return table


COMPANY_TABLE = None   # 懒加载（selftest 里也要用）


def company_table() -> dict:
    global COMPANY_TABLE
    if COMPANY_TABLE is None:
        COMPANY_TABLE = build_company_table()
    return COMPANY_TABLE


def norm_name(value) -> str:
    """公司名比对用的归一化：先 `NFKC`（全角→半角、兼容字符），再按 `config.normalize_entity_name`
    去空白与最外层包裹字符。

    **这一层是 lint 自己加的**：`config.normalize_entity_name` 只去空白与外壳，不做全角折叠，
    因此「豪威集成电路（集团）股份有限公司」（全角括号）会与表里的
    「豪威集成电路(集团)股份有限公司」核不上——那是**书写宽度差异，不是臆造**，
    在本工具里按同一名字处理（否则 R2 会误报）。繁体写法不做简繁折叠：核不上就如实报命中。
    """
    try:
        folded = unicodedata.normalize("NFKC", str(value or ""))
    except TypeError:
        folded = str(value or "")
    return config.normalize_entity_name(folded)


NAME_INDEX = None   # 归一化名字 → 代码集合
NAME_INDEX_SIMP = None   # 「NFKC＋简繁折叠」后的归一化名字 → 代码集合


def name_index() -> dict:
    global NAME_INDEX
    if NAME_INDEX is None:
        idx = {}
        for code, slot in company_table().items():
            for n in slot["names"]:
                idx.setdefault(norm_name(n), set()).add(code)
        NAME_INDEX = idx
    return NAME_INDEX


def norm_name_simp(value) -> str:
    """R2 的核对名：`NFKC` ＋ 常用简繁／异体单字折叠 ＋ `config.normalize_entity_name`。"""
    return config.normalize_entity_name(fold_simp(value))


def name_index_simp() -> dict:
    global NAME_INDEX_SIMP
    if NAME_INDEX_SIMP is None:
        idx = {}
        for code, slot in company_table().items():
            for n in slot["names"]:
                idx.setdefault(norm_name_simp(n), set()).add(code)
        NAME_INDEX_SIMP = idx
    return NAME_INDEX_SIMP


def codes_by_simp_name(value) -> set:
    """一个书写面在「简繁折叠后」能核到的代码集合（空集＝表里没有这个名字）。"""
    return set(name_index_simp().get(norm_name_simp(value)) or ())


def in_scope_code(code) -> bool:
    return str(code or "").strip() in company_table()


def entity_scope(ent: dict) -> tuple:
    """返回 (是否名单内, 理由)。名单内＝代码在表里，**或**名字能在表里核到某个代码。

    「代码留空但名字就是 105 家里的某家」属名单内（只是没填代码），
    不属于 R4 要的 `company_out_of_scope`（名单外）。
    """
    code = str(ent.get("stock_code") or "").strip()
    if code in company_table():
        return True, "code=%s" % code
    for _f, v in entity_name_surfaces(ent):
        codes = name_index().get(norm_name(v))
        if codes:
            return True, "name=%s→%s" % (v, "、".join(sorted(codes)))
    return False, "code=%s、name=%s" % (
        code or "空",
        ent.get("company_name") or ent.get("short_name") or "（无名字键）")


NAME_FIELDS_BY_TYPE = OrderedDict([
    ("Company", ["company_name", "short_name"]),
    ("Person", ["person_name"]),
    ("Industry", ["industry_name"]),
    ("Institution", ["institution_name"]),
    ("Policy", ["policy_name"]),
])


def entity_name_surfaces(ent: dict) -> list:
    """返回 [(字段名, 取值), …]：各类实体的「名字键」＋ `aliases`（如果有）。"""
    out = []
    et = ent.get("entity_type")
    for field in (NAME_FIELDS_BY_TYPE.get(et) or []):
        value = ent.get(field)
        if isinstance(value, str) and value.strip():
            out.append((field, value.strip()))
    aliases = ent.get("aliases")
    if isinstance(aliases, list):
        for i, a in enumerate(aliases):
            if isinstance(a, str) and a.strip():
                out.append(("aliases[%d]" % i, a.strip()))
    return out


# --------------------------------------------------------------------------
# 单条 lint
# --------------------------------------------------------------------------
def _mk(rule, rec, location, detail, snippet="", evidence=None):
    out = OrderedDict([
        ("rule", rule),
        ("item_id", rec.get("item_id")),
        ("split", rec.get("split")),
        ("chunk_id", rec.get("chunk_id")),
        ("location", location),
        ("detail", detail),
        ("snippet", (snippet or "")[:200]),
    ])
    if evidence is not None:
        out["evidence"] = evidence
    return out


def _dicts(seq):
    return [x for x in (seq or []) if isinstance(x, dict)]


def entities_by_ref(ann) -> dict:
    return {e.get("entity_ref"): e for e in _dicts(ann.get("entities"))
            if isinstance(e.get("entity_ref"), str) and e.get("entity_ref")}


def _joined_quotes(ann) -> str:
    parts = []
    for slot in ("entities", "events", "relations", "times", "ontology_boundary_log"):
        for x in _dicts(ann.get(slot)):
            if isinstance(x.get("quote"), str):
                parts.append(x["quote"])
    return " / ".join(parts)


def rule_r1_code_format(rec, ann):
    hits = []
    for i, ent in enumerate(_dicts(ann.get("entities"))):
        if ent.get("entity_type") != "Company":
            continue
        code = ent.get("stock_code")
        code_s = "" if code is None else str(code).strip()
        if not code_s:
            continue
        if re.match(r"^\d{6}$", code_s):
            continue
        hk = bool(re.match(r"^\d{1,5}(\s*,\s*\d+)*$", code_s))
        hits.append(_mk("R1_code_format", rec, "entities[%d].stock_code" % i,
                        "%s：`%s`（要求 6 位数字；%s）"
                        % ("港股代码形态（A 股口径下违规）" if hk else "不是 6 位数字",
                           code_s, "本项目是 A 股口径" if hk else "不许臆造代码形态"),
                        _joined_quotes(ann)))
    return hits


def rule_r2_code_source(rec, ann):
    """代码与名字必须互相核得上（名字比对走 `NFKC ＋ 简繁折叠`）。

    三条出口（作者 2026-09-27 裁定）：
    1. 代码不在名单里 → **命中**（含港股代码 `01211, 81211`／`3288`——A 股口径下是真违规）；
    2. 代码在名单里，名字（简体或繁体书写面）折叠后核到该代码 → 不命中（繁体的那几条另登记）；
    3. 代码在名单里，但名字折叠后也核不到该代码 → **命中**（并报出折叠后实际对应哪些代码）。
    """
    hits = []
    table = company_table()
    for i, ent in enumerate(_dicts(ann.get("entities"))):
        if ent.get("entity_type") != "Company":
            continue
        code = ent.get("stock_code")
        code_s = "" if code is None else str(code).strip()
        if not code_s:
            continue
        surfaces = entity_name_surfaces(ent)
        named = "、".join("%s=%s" % (f, v) for f, v in surfaces) or "（无名字键）"
        if code_s not in table:
            other = sorted({c for _f, v in surfaces for c in codes_by_simp_name(v)})
            hits.append(_mk("R2_code_source", rec, "entities[%d].stock_code" % i,
                            "代码 `%s` 不在 105 家名单／注册全称表里（%s%s）"
                            % (code_s, named,
                               ("；该名字（简繁折叠后）在表里对应 %s" % "、".join(other))
                               if other else ""),
                            _joined_quotes(ann)))
            continue
        matched_exact = [f for f, v in surfaces if norm_name(v) in table[code_s]["names"]]
        matched_simp = [f for f, v in surfaces if code_s in codes_by_simp_name(v)]
        if not matched_exact and not matched_simp:
            other = sorted({c for _f, v in surfaces for c in codes_by_simp_name(v)})
            hits.append(_mk("R2_code_source", rec, "entities[%d]" % i,
                            "公司名与代码核不到：代码 `%s` 在名单里，但 %s 都不是该代码的书写面"
                            "（含简繁折叠后；%s；名单书写面：%s）"
                            % (code_s, named if surfaces else "（该实体没有名字键，无法核对）",
                               ("折叠后能核到的是 %s" % "、".join(other)) if other else "折叠后表里没有这个名字",
                               "／".join(sorted(table[code_s]["raw"]))),
                            _joined_quotes(ann)))
    return hits


def traditional_surface_notes(rec, ann) -> list:
    """「简繁书写面登记」：书写面含繁体／异体字、折叠后能核到名单里某个代码的公司名。

    这类条目**不命中 R2**（代码有可能是对的），但必须单独登记——它们是下游消歧的线索
    （例如同一家公司出现了两种书写面，或名字指向的代码与条目里填的代码不同）。
    """
    out = []
    for i, ent in enumerate(_dicts(ann.get("entities"))):
        if ent.get("entity_type") != "Company":
            continue
        code = ent.get("stock_code")
        code_s = "" if code is None else str(code).strip()
        for f, v in entity_name_surfaces(ent):
            folded = fold_simp(v)
            if folded == str(v or ""):
                continue          # 书写面本来就是简体，不算「繁体登记」
            codes = sorted(codes_by_simp_name(v))
            if not codes:
                continue          # 折叠后表里也没有这个名字：交给 R7a／R2 自己去报
            kind = ("简繁／异体" if any(ch in S2T_MAP for ch in str(v))
                    else "全半角／兼容字符（NFKC）")
            out.append(OrderedDict([
                ("item_id", rec.get("item_id")), ("split", rec.get("split")),
                ("location", "entities[%d].%s" % (i, f)),
                ("written", v), ("folded", folded), ("stock_code", code_s),
                ("codes_after_fold", codes), ("code_matches", code_s in codes),
                ("kind", kind),
                ("note", "%s书写面：折叠后能核到代码 %s；条目里填的是 `%s`"
                         % (kind, "、".join(codes), code_s or "（空）")),
            ]))
    return out


def rule_r3_relation_endpoints_in_scope(rec, ann):
    """**2026-09-27 作者裁定：由硬规则降级为软提示。**

    公司间关系与 `BELONGS_TO` 的端点不在 105 家名单内 → 只提示、不判硬违规。
    理由：名单约束是**图谱写入层**的约束（写图时跳过并计数），标注层的事实仍由原文逐字证据支撑；
    该情形已由 `R4_out_of_scope_logged`（`company_out_of_scope` 登记）覆盖。
    命中照常逐条列出，供人工看；不再计入硬命中、不触发定向修复。
    """
    hits = []
    ents = entities_by_ref(ann)
    for i, rel in enumerate(_dicts(ann.get("relations"))):
        name = rel.get("relation")
        if name not in ("SUPPLIES", "CUSTOMER_OF", "COMPETES_WITH", "BELONGS_TO"):
            continue
        want = {"from": "Company", "to": "Industry" if name == "BELONGS_TO" else "Company"}
        for side in ("from", "to"):
            ref = rel.get(side + "_ref")
            label = rel.get(side + "_label")
            ent = ents.get(ref)
            where = "relations[%d].%s_ref" % (i, side)
            if ent is None:
                hits.append(_mk("R3_relation_endpoints_in_scope", rec, where,
                                "`%s` 的 %s 端点 ref=%s 在 entities[] 里不存在（无法证明是名单内公司）"
                                % (name, side, ref), _joined_quotes(ann)))
                continue
            etype = ent.get("entity_type")
            if etype != want[side]:
                hits.append(_mk("R3_relation_endpoints_in_scope", rec, where,
                                "`%s` 的 %s 端点应是 %s，实为 %s（label=%s）"
                                % (name, side, want[side], etype, label), _joined_quotes(ann)))
                continue
            if want[side] != "Company":
                continue
            in_scope, why = entity_scope(ent)
            if not in_scope:
                hits.append(_mk("R3_relation_endpoints_in_scope", rec, where,
                                "`%s` 的 %s 端点是名单外公司（%s）" % (name, side, why),
                                _joined_quotes(ann)))
    return hits


def rule_r4_out_of_scope_logged(rec, ann):
    """收窄到**图谱端点**（作者 2026-09-27 裁定）：只看 `relations[]` 的 `from_ref`／`to_ref`。

    端点进图谱、必须有节点，所以「名单外公司当了端点却没登记」才是定义性违规；
    只在 `entities[]` 里出现、没进任何关系的名单外公司**不再由本规则管**（登记与否交人工判）。
    「名单内公司但 `stock_code` 留空」按 `entity_scope` 仍算名单内，不触发本规则。
    """
    ents = entities_by_ref(ann)
    outside = []                                   # [(端点描述, [端点公司的名面…])]
    for i, rel in enumerate(_dicts(ann.get("relations"))):
        for side in ("from", "to"):
            ref = rel.get(side + "_ref")
            ent = ents.get(ref)
            if not isinstance(ent, dict) or ent.get("entity_type") != "Company":
                continue
            in_scope, why = entity_scope(ent)
            if not in_scope:
                # 注意名字键是 company_name／short_name／aliases（**没有** `name` 键，
                # 见 NAME_FIELDS_BY_TYPE）；用 entity_name_surfaces 取全部名面。
                names = [v for _f, v in entity_name_surfaces(ent)]
                outside.append(("relations[%d].%s_ref=%s（%s）" % (i, side, ref, why), names))
    if not outside:
        return []
    logged = [e for e in _dicts(ann.get("ontology_boundary_log"))
              if str(e.get("case_type") or "").strip() == "company_out_of_scope"]
    # M-7：登记必须**覆盖到具体端点公司**。原实现是「只要有任意一条 company_out_of_scope
    # 登记，整条记录的所有名单外端点一律豁免」，于是登记了 A 公司就顺手放过了 B 公司
    # （交付实测漏报 4 条）。改为按端点公司逐个核对：端点的**任一名面**出现在登记条目的
    # summary／quote／suggested_handling／note 文本里即算覆盖。
    logged_text = " ".join(
        str(e.get(key) or "")
        for e in logged for key in ("summary", "quote", "suggested_handling", "note"))
    uncovered = [desc for desc, names in outside
                 if not names or not any(n in logged_text for n in names)]
    if not uncovered and logged:
        return []
    return [_mk("R4_out_of_scope_logged", rec, "relations[].{from,to}_ref",
                "图谱端点里出现名单外公司但没有覆盖到它的 `case_type=company_out_of_scope` 登记"
                "（%s）" % "；".join(uncovered[:4] or [d for d, _ in outside[:4]]),
                _joined_quotes(ann))]


def rule_r5_participants_relation_mirror(rec, ann):
    hits = []
    part = Counter()
    for ev in _dicts(ann.get("events")):
        for p in _dicts(ev.get("participants")):
            part[(p.get("entity_ref"), ev.get("event_ref"), p.get("role"))] += 1
    rel = Counter()
    for r in _dicts(ann.get("relations")):
        if r.get("relation") != "PARTICIPATES_IN":
            continue
        rel[(r.get("from_ref"), r.get("to_ref"), r.get("role"))] += 1
    for key, n in (part - rel).items():
        hits.append(_mk("R5_participants_relation_mirror", rec, "events[].participants",
                        "participants 有 `%s` 而 relations 里缺同键的 PARTICIPATES_IN（%d 处）"
                        % ("|".join(str(x) for x in key), n), _joined_quotes(ann)))
    for key, n in (rel - part).items():
        hits.append(_mk("R5_participants_relation_mirror", rec, "relations[].PARTICIPATES_IN",
                        "PARTICIPATES_IN 有 `%s` 而 events[].participants 里缺同键项（%d 处）"
                        % ("|".join(str(x) for x in key), n), _joined_quotes(ann)))
    roles_part, roles_rel = {}, {}
    for (er, ev, role), _n in part.items():
        roles_part.setdefault((er, ev), set()).add(role)
    for (er, ev, role), _n in rel.items():
        roles_rel.setdefault((er, ev), set()).add(role)
    for key in sorted(set(roles_part) & set(roles_rel), key=lambda x: (str(x[0]), str(x[1]))):
        if roles_part[key] != roles_rel[key]:
            hits.append(_mk("R5_participants_relation_mirror", rec,
                            "events[].participants / relations[].PARTICIPATES_IN",
                            "同一 (entity_ref=%s, event_ref=%s) 的 role 不一致：participants=%s；relations=%s"
                            % (key[0], key[1], "／".join(sorted(roles_part[key])),
                               "／".join(sorted(roles_rel[key]))), _joined_quotes(ann)))
    return hits


def rule_r6_times_event_mirror(rec, ann):
    """**2026-09-27 作者裁定：收窄到两种情形。**

    (a) `events[]` 为空而 `times[]` 含 `time_type=event_time` 的项 → 命中；
    (b) 某事件 `event_time` 非空、而 `times[]` 里没有同值项 → 命中。
    「`times[]` 记录多个彼此独立的日期、事件 `event_time` 为 null」是**多日期安排型公告**的正确写法
    （一事只写一条、不能确定到日写 null），**不再判违规**。适用于 TEST-017。
    """
    hits = []
    ev_times = []
    events = _dicts(ann.get("events"))
    for i, ev in enumerate(events):
        v = ev.get("event_time")
        if v not in (None, ""):
            ev_times.append((str(v).strip(), i))
    t_vals = []
    for i, t in enumerate(_dicts(ann.get("times"))):
        if t.get("time_type") != "event_time":
            continue
        v = t.get("value")
        t_vals.append(("" if v is None else str(v).strip(), i))
    t_set = {v for v, _i in t_vals}
    if not events and t_vals:
        hits.append(_mk("R6_times_event_mirror", rec, "times[] / events[]",
                        "`events[]` 为空，但 `times[]` 里有 %d 条 `time_type=event_time` 的项（%s）"
                        "——没有事件就不该有事件时间"
                        % (len(t_vals), "、".join(v for v, _i in t_vals[:6])), _joined_quotes(ann)))
        return hits
    for v, i in ev_times:
        if v not in t_set:
            hits.append(_mk("R6_times_event_mirror", rec, "events[%d].event_time" % i,
                            "事件 event_time=`%s` 在 times[] 里没有同一 value 的项" % v,
                            _joined_quotes(ann)))
    return hits


def rule_r7a_quote_fabricated(rec, ann):
    """两层判据（作者 2026-09-27 裁定），取并集；匹配只用**去空白**（不做 NFKC 宽度折叠）：

    * A 层：实体的类型名键（`company_name`／`person_name`／`industry_name`／`institution_name`／
      `policy_name`）在本块 `text` 与全篇 `doc_text` 里都**不是连续书写面**。指代性别名
      （「公司」「发行人」「本公司」…）只能作为证据登记，**不能救 A 层**——它证明的是「文里有这个角色」，
      不是「这个名字被写过」。作者独立尺度命中的 pro 版 TEST-047 就是这一类。
    * B 层：名字键**连同全部别名**都不可定位（含没有类型名键值的实体）。

    宽度差异（「（特殊普通合伙）」vs「(特殊普通合伙)」）算**书写面不同**：A 层照报——
    作者独立尺度命中的 TEST-199 就靠这一条（lint 之前用 NFKC 折叠把这条洗掉了）。
    """
    hits = []
    text_ws = norm_ws(str(rec.get("text") or ""))
    doc_ws = norm_ws(str(rec.get("doc_text") or ""))
    hay = text_ws + "\n" + (doc_ws or "")
    for i, ent in enumerate(_dicts(ann.get("entities"))):
        surfaces = entity_name_surfaces(ent)
        if not surfaces:
            continue
        et = ent.get("entity_type")
        primary_fields = [f for f in (NAME_FIELDS_BY_TYPE.get(et) or [])[:1]]
        primary = [(f, v) for f, v in surfaces if f in primary_fields]
        located = [("%s=%s" % (f, v)) for f, v in surfaces if norm_ws(v) and norm_ws(v) in hay]
        if primary:
            primary_located = [v for _f, v in primary if norm_ws(v) and norm_ws(v) in hay]
            if primary_located:
                continue
            rescue = [x for x in located]
            # 复核线索：如果**折叠宽度**（NFKC）之后名键能定位，说明命中的成因是「全半角／兼容字符」
            # 这类书写面形态差异，而不是正文里根本没有这个名字。
            nfkc_located = [v for _f, v in primary
                            if _fold(v) and (_fold(v) in _fold(rec.get("text") or "")
                                             or _fold(v) in _fold(rec.get("doc_text") or ""))]
            detail = ("[A 层·名字键不可定位] 类型名键 %s 在本块与全篇都不是连续书写面；%s"
                      % ("、".join("%s=%s" % (f, v) for f, v in primary),
                         ("能定位的只有别名／简称（指代性，不救 A 层）：%s" % "、".join(rescue))
                         if rescue else "且全部别名也不可定位（同时构成 B 层）"))
            hits.append(_mk("R7a_quote_fabricated", rec, "entities[%d].[%s]" % (i, primary_fields[0]),
                            detail, _joined_quotes(ann),
                            evidence=OrderedDict([
                                ("tier", "A" if rescue else "A+B"),
                                ("primary_surfaces", [v for _f, v in primary]),
                                ("located_surfaces", located),
                                ("nfkc_located_primary", nfkc_located),
                                ("text_hit", any(norm_ws(v) in text_ws for _f, v in surfaces)),
                                ("doc_hit", any(norm_ws(v) in doc_ws for _f, v in surfaces)),
                            ])))
            continue
        if not located:
            hits.append(_mk("R7a_quote_fabricated", rec, "entities[%d]" % i,
                            "[B 层·名字键与全部别名都不可定位] 实体（entity_type=%s，无类型名键值）"
                            "的名字键/别名在本块与全篇都找不到：%s"
                            % (et, "、".join("%s=%s" % (f, v) for f, v in surfaces)),
                            _joined_quotes(ann),
                            evidence=OrderedDict([
                                ("tier", "B"), ("primary_surfaces", []),
                                ("located_surfaces", []),
                                ("text_hit", False), ("doc_hit", False),
                            ])))
    return hits


def rule_r8_issued_by_role_conflict(rec, ann):
    hits = []
    issued_targets = set()
    for r in _dicts(ann.get("relations")):
        if r.get("relation") == "ISSUED_BY":
            issued_targets.add((r.get("from_ref"), r.get("to_ref")))
    by_event = {ev.get("event_ref"): ev for ev in _dicts(ann.get("events"))}
    for i, r in enumerate(_dicts(ann.get("relations"))):
        if r.get("relation") != "ISSUED_BY":
            continue
        ev_ref, inst_ref = r.get("from_ref"), r.get("to_ref")
        ev = by_event.get(ev_ref)
        if ev is None:
            continue
        for j, p in enumerate(_dicts(ev.get("participants"))):
            if p.get("entity_ref") == inst_ref:
                hits.append(_mk("R8_issued_by_role_conflict", rec,
                                "relations[%d] / events[%s].participants[%d]" % (i, ev_ref, j),
                                "机构 `%s` 既是该事件 ISSUED_BY 终点、又在 participants（role=%s）里"
                                % (inst_ref, p.get("role")), _joined_quotes(ann)))
            elif p.get("role") == "监管方" and (ev_ref, p.get("entity_ref")) in issued_targets:
                hits.append(_mk("R8_issued_by_role_conflict", rec,
                                "events[%s].participants[%d]" % (ev_ref, j),
                                "同一（事件 `%s`、机构 `%s`）既写 ISSUED_BY 又把机构写进 "
                                "PARTICIPATES_IN（role=监管方）" % (ev_ref, p.get("entity_ref")),
                                _joined_quotes(ann)))
    return hits


def rule_r9_event_without_participant(rec, ann):
    """**2026-09-27 作者裁定：加 `ISSUED_BY` 豁免。**

    事件只要有 `ISSUED_BY` 边（不问事件类型、两端都算），`participants` 为空即**不判违规**——
    依据《10》第4.5.2节 与《标注说明》第6.2节：「发布／作出方只写 ISSUED_BY，不再写 PARTICIPATES_IN」。
    只在「既无 `participants`、又无 `ISSUED_BY`」时命中。适用于 DEV-057／TEST-041／TEST-184。
    """
    hits = []
    issued_by_events = set()
    for r in _dicts(ann.get("relations")):
        if r.get("relation") != "ISSUED_BY":
            continue
        for side in ("from_ref", "to_ref"):
            ref = r.get(side)
            if isinstance(ref, str) and ref:
                issued_by_events.add(ref)
    for i, ev in enumerate(_dicts(ann.get("events"))):
        if _dicts(ev.get("participants")):
            continue
        if ev.get("event_ref") in issued_by_events:
            continue          # 有 ISSUED_BY 边：发布／作出方已由该边表达，不判违规
        hits.append(_mk("R9_event_without_participant", rec, "events[%d].participants" % i,
                        "事件 `%s`（%s）既没有 participants、也没有 ISSUED_BY 边"
                        "——每个事件至少要有一个参与主体，或一条表达发布／作出方的 ISSUED_BY"
                        % (ev.get("event_name"), ev.get("event_type")), _joined_quotes(ann)))
    return hits


def _norm_event_name(name) -> str:
    s = norm_ws(str(name or ""))
    return re.sub(r"[\s，。；、,.!?！？：:；;\"'“”‘’（）()\[\]【】《》<>—\-]+$", "", s)


def rule_r10_duplicate_event_in_item(rec, ann):
    hits = []
    seen = {}
    for i, ev in enumerate(_dicts(ann.get("events"))):
        key = (ev.get("event_type"), _norm_event_name(ev.get("event_name")))
        if key in seen:
            hits.append(_mk("R10_duplicate_event_in_item", rec, "events[%d]" % i,
                            "与 events[%d] 重复（event_type=%s，规范化 event_name=`%s`）"
                            % (seen[key], key[0], key[1]), _joined_quotes(ann)))
        else:
            seen[key] = i
    return hits


def rule_r11_boundary_case_type(rec, ann):
    hits = []
    for i, e in enumerate(_dicts(ann.get("ontology_boundary_log"))):
        ct = e.get("case_type")
        ct_s = "" if ct is None else str(ct).strip()
        if ct_s in CASE_TYPES:
            continue
        hits.append(_mk("R11_boundary_case_type", rec, "ontology_boundary_log[%d].case_type" % i,
                        "%s：`%s`（建议枚举：%s）"
                        % ("case_type 缺失/为空" if not ct_s else "不在建议枚举内",
                           ct_s, "／".join(CASE_TYPES)), _joined_quotes(ann)))
    return hits


def rule_s1_quote_not_supporting_name(rec, ann):
    hits = []
    text_ws = _fold(rec.get("text") or "")
    doc_ws = _fold(rec.get("doc_text") or "")
    for i, ent in enumerate(_dicts(ann.get("entities"))):
        surfaces = entity_name_surfaces(ent)
        if not surfaces:
            continue
        if any(_fold(v) in text_ws for _f, v in surfaces):
            continue
        only_doc = [v for _f, v in surfaces if _fold(v) in doc_ws]
        if only_doc:
            hits.append(_mk("S1_quote_not_supporting_name", rec, "entities[%d]" % i,
                            "名字键只在本块之外的全篇里出现（%s）→ 换 quote 或补跨块说明"
                            % "、".join(only_doc), _joined_quotes(ann)))
    return hits


S2_PATTERNS = [
    r"议案.*(审议|通过|获批)",
    r"审议通过",
    r"公告$",
    r"的公告",
    r"(进展|进度)($|公告)",
    r"(通知|告知)($|公告)",
    r"(披露|发布|刊登)",
]


def rule_s2_procedural_event_name(rec, ann):
    hits = []
    for i, ev in enumerate(_dicts(ann.get("events"))):
        name = str(ev.get("event_name") or "")
        for pat in S2_PATTERNS:
            if re.search(pat, name):
                hits.append(_mk("S2_procedural_event_name", rec, "events[%d].event_name" % i,
                                "事件名呈程序／元事件式（命中 `%s`）：`%s` → 按 EVENT_NOT_EVENT_RULES 复核"
                                % (pat, name), _joined_quotes(ann)))
                break
    return hits


def _date_forms(value: str) -> list:
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", str(value or "").strip())
    if not m:
        return [str(value or "").strip()]
    y, mo, d = m.group(1), m.group(2), m.group(3)
    forms = ["%s-%s-%s" % (y, mo, d), "%s-%d-%d" % (int(y), int(mo), int(d)),
             "%s年%s月%s日" % (y, mo, d), "%s年%d月%d日" % (int(y), int(mo), int(d)),
             "%s年%s月%s" % (y, mo, d)]
    return sorted(set(forms), key=len, reverse=True)


def rule_s3_time_not_in_text(rec, ann):
    hits = []
    text_ws = _fold(rec.get("text") or "")
    doc_ws = _fold(rec.get("doc_text") or "")
    for i, ev in enumerate(_dicts(ann.get("events"))):
        v = ev.get("event_time")
        if v in (None, ""):
            continue
        forms = _date_forms(str(v).strip())
        if any(_fold(f) in text_ws or _fold(f) in doc_ws for f in forms):
            continue
        hits.append(_mk("S3_time_not_in_text", rec, "events[%d].event_time" % i,
                        "event_time=`%s` 的书写形态（%s）在本块与全篇都找不到"
                        % (v, "／".join(forms[:3])), _joined_quotes(ann)))
    return hits


def rule_s4_no_subject_role(rec, ann):
    hits = []
    issued_by_events = {r.get("from_ref") for r in _dicts(ann.get("relations"))
                        if r.get("relation") == "ISSUED_BY"}
    for i, ev in enumerate(_dicts(ann.get("events"))):
        parts = _dicts(ev.get("participants"))
        if any(p.get("role") == "主体" for p in parts):
            continue
        ev_ref = ev.get("event_ref")
        strong = ev_ref not in issued_by_events
        hits.append(_mk("S4_no_subject_role", rec, "events[%d].participants" % i,
                        "%s：事件 `%s`（%s）的参与方里没有 role=主体（现有 role：%s）"
                        % ("强提示（该事件没有 ISSUED_BY，行为人或被处置对象该是主体）" if strong
                           else "弱提示（该事件有 ISSUED_BY，作出方已由 ISSUED_BY 表达，仅供人工看）",
                           ev.get("event_name"), ev.get("event_type"),
                           "／".join(str(p.get("role")) for p in parts) or "无"),
                        _joined_quotes(ann)))
    return hits


RULE_FUNCS = OrderedDict([
    ("R1_code_format", rule_r1_code_format),
    ("R2_code_source", rule_r2_code_source),
    ("R3_relation_endpoints_in_scope", rule_r3_relation_endpoints_in_scope),
    ("R4_out_of_scope_logged", rule_r4_out_of_scope_logged),
    ("R5_participants_relation_mirror", rule_r5_participants_relation_mirror),
    ("R6_times_event_mirror", rule_r6_times_event_mirror),
    ("R7a_quote_fabricated", rule_r7a_quote_fabricated),
    ("R8_issued_by_role_conflict", rule_r8_issued_by_role_conflict),
    ("R9_event_without_participant", rule_r9_event_without_participant),
    ("R10_duplicate_event_in_item", rule_r10_duplicate_event_in_item),
    ("R11_boundary_case_type", rule_r11_boundary_case_type),
    ("S1_quote_not_supporting_name", rule_s1_quote_not_supporting_name),
    ("S2_procedural_event_name", rule_s2_procedural_event_name),
    ("S3_time_not_in_text", rule_s3_time_not_in_text),
    ("S4_no_subject_role", rule_s4_no_subject_role),
])


def lint_record(rec) -> dict:
    ann = rec.get("annotation") or {}
    out = OrderedDict([("item_id", rec.get("item_id")), ("split", rec.get("split")),
                       ("hard", OrderedDict()), ("soft", OrderedDict()),
                       ("notes", OrderedDict([("traditional_name_surfaces",
                                               traditional_surface_notes(rec, ann))]))])
    for rule, fn in RULE_FUNCS.items():
        bucket = out["hard"] if is_hard_rule(rule) else out["soft"]
        bucket[rule] = fn(rec, ann)
    return out


def lint_version(label: str, input_dir: str = None, suffix: str = None) -> dict:
    v = VERSIONS[label]
    vd = input_dir or version_dir(label)
    sfx = suffix or v.get("suffix") or ".auto"
    truth = {}
    for split in ("dev", "test"):
        for rec in read_jsonl(os.path.join(eval_dir(), "%s.jsonl" % split)):
            truth[rec["item_id"]] = rec
    items = OrderedDict()
    per_rule = OrderedDict((r, OrderedDict([("hits", 0), ("items", 0),
                                            ("by_split", {"dev": 0, "test": 0})]))
                           for r in ALL_RULES)
    per_rule_items = OrderedDict((r, set()) for r in ALL_RULES)
    n_hard_items = 0
    splits_present = []
    trad_notes = []
    for split in ("dev", "test"):
        path = os.path.join(vd, "%s%s.jsonl" % (split, sfx))
        if not os.path.isfile(path):
            # 成本闸门停在 dev 时 test 尚未产出：如实登记缺哪个 split，不假装扫过。
            continue
        splits_present.append(split)
        for rec in read_jsonl(path):
            rec = OrderedDict(rec)
            src = truth.get(rec.get("item_id"))
            if src is None:
                raise SystemExit("item_id=%s 不在 %s.jsonl 里" % (rec.get("item_id"), split))
            # text／doc_text 用**交付文件**的原文（标注产物本身与它逐字节同源）
            rec["text"] = src.get("text")
            rec["doc_text"] = src.get("doc_text")
            res = lint_record(rec)
            items[rec["item_id"]] = res
            trad_notes.extend((res.get("notes") or {}).get("traditional_name_surfaces") or [])
            hard_n = sum(len(x) for x in res["hard"].values())
            n_hard_items += 1 if hard_n else 0
            for rule in ALL_RULES:
                bucket = res["hard"] if is_hard_rule(rule) else res["soft"]
                n = len(bucket.get(rule) or [])
                if n:
                    per_rule[rule]["hits"] += n
                    if rec["item_id"] not in per_rule_items[rule]:
                        per_rule[rule]["items"] += 1
                        per_rule_items[rule].add(rec["item_id"])
                    per_rule[rule]["by_split"][split] += n
    payload = OrderedDict([
        ("schema", LINT_SCHEMA),
        ("tool", "代码\\抽取与图谱\\auto_annotate_lint.py"),
        ("version", label),
        ("version_desc", v["desc"]),
        ("input_dir", vd),
        ("input_suffix", sfx),
        ("splits_present", splits_present),
        ("splits_declared", ["dev", "test"]),
        ("generated_at", now_iso()),
        ("rules", OrderedDict([("hard", HARD_RULES), ("soft", SOFT_RULES),
                               ("case_types", CASE_TYPES)])),
        ("counts", per_rule),
        ("items_with_hard_hits", n_hard_items),
        ("traditional_name_surfaces", trad_notes),
        ("traditional_name_surface_count",
         sum(1 for n in trad_notes if n.get("kind") == "简繁／异体")),
        ("fold_width_surface_count",
         sum(1 for n in trad_notes if n.get("kind") != "简繁／异体")),
        ("item_count", len(items)),
        ("items", items),
    ])
    return payload


def cmd_lint(args) -> int:
    out_dir = args.out_dir or default_out_dir()
    os.makedirs(out_dir, exist_ok=True)
    input_dir = getattr(args, "input_dir", None)
    suffix = getattr(args, "suffix", None)          # None＝按版本自己的后缀（提准＝.auto.repaired）
    tag = getattr(args, "tag", None)
    name_tag = ("." + tag) if tag else ""
    labels = list(VERSIONS) if getattr(args, "version", "flash") == "all" else [args.version]
    for label in labels:
        payload = lint_version(label, input_dir=input_dir, suffix=suffix)
        if tag:
            payload["备注"] = "扫描范围：%s（后缀 %s）" % (
                input_dir or version_dir(label), suffix or VERSIONS[label].get("suffix"))
        path = os.path.join(out_dir, "lint_命中_%s%s.json" % (label, name_tag))
        write_text_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        hard = sum(payload["counts"][r]["hits"] for r, _t in HARD_RULES)
        soft = sum(payload["counts"][r]["hits"] for r, _t in SOFT_RULES)
        print("lint %s：%d 条（扫描范围 %s）｜硬命中 %d 处、软提示 %d 处｜有硬命中的条目 %d"
              "｜书写面登记 %d 处（简繁／异体 %d＋全半角 %d）｜%s"
              % (label, payload["item_count"], "＋".join(payload["splits_present"]) or "无",
                 hard, soft, payload["items_with_hard_hits"],
                 len(payload.get("traditional_name_surfaces") or []),
                 payload.get("traditional_name_surface_count", 0),
                 payload.get("fold_width_surface_count", 0), path))
        for rule, _t in HARD_RULES + SOFT_RULES:
            c = payload["counts"][rule]
            if c["hits"]:
                print("    %-34s 命中 %3d 处 / %3d 条（dev %d／test %d）"
                      % (rule, c["hits"], c["items"], c["by_split"]["dev"], c["by_split"]["test"]))
    return 0


def cmd_diff(args) -> int:
    """修复前后（或任意两份命中清单）**逐规则命中数对照**：只读命中清单，不调模型。"""
    before = _load_hits_by_path(args.before)
    after = _load_hits_by_path(args.after)
    L = ["# 逐规则命中数对照（%s）" % (args.label or "修复前后"), "",
         "> 输入：`%s`（前）→ `%s`（后）。两边的扫描范围见各自 `splits_present`。"
         % (os.path.relpath(args.before, ROOT), os.path.relpath(args.after, ROOT)), "",
         "> 规则口径：v1.2（2026-09-27 三处裁定：`R9` 加 `ISSUED_BY` 豁免／`R6` 收窄／"
         "`R3` 由硬降级为软提示）。下表把**硬与软都计入合计**；**硬命中条目数**与集合级读数见 "
         "`lint报告.md` 第零／一节。", "",
         "| 规则 | 前：命中处数／条目数 | 后：命中处数／条目数 | 变化（处） |", "| --- | --- | --- | --- |"]
    tot_b = tot_a = 0
    for rule, _t in HARD_RULES + SOFT_RULES:
        b, a = before["counts"][rule], after["counts"][rule]
        tot_b += b["hits"]
        tot_a += a["hits"]
        L.append("| `%s` | %d／%d | %d／%d | %s |"
                 % (rule, b["hits"], b["items"], a["hits"], a["items"],
                    ("%+d" % (a["hits"] - b["hits"])) if a["hits"] != b["hits"] else "0"))
    L += ["| **合计** | **%d** | **%d** | **%+d** |" % (tot_b, tot_a, tot_a - tot_b), "",
          "前：%s｜后：%s"
          % ("＋".join(before.get("splits_present") or []) or "无",
             "＋".join(after.get("splits_present") or []) or "无"),
          "", "生成时间：%s" % now_iso()]
    if args.out:
        # M-8：裸文件名（如 --out 报告.md）时 os.path.dirname 返回 ""，os.makedirs("") 会抛
        # FileNotFoundError；先转绝对路径再取目录名。
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        write_text_atomic(args.out, "\n".join(L) + "\n")
        print("对照表：%s（前 %d 处 → 后 %d 处）" % (args.out, tot_b, tot_a))
    else:
        print("\n".join(L))
    return 0


def _load_hits_by_path(path: str) -> dict:
    if not os.path.isfile(path):
        raise SystemExit("缺少命中清单：%s" % path)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# 报告：三集合并列（含规则修正记录与集合级统计）
# --------------------------------------------------------------------------
def _load_hits(out_dir: str, label: str) -> dict:
    path = os.path.join(out_dir, "lint_命中_%s.json" % label)
    if not os.path.isfile(path):
        raise SystemExit("缺少 %s（先跑 `lint --version %s`）" % (path, label))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _examples(payload: dict, rule: str, k: int = 3) -> list:
    out = []
    for _iid, res in payload["items"].items():
        bucket = res["hard"] if is_hard_rule(rule) else res["soft"]
        for h in bucket.get(rule) or []:
            out.append(h)
            break
        if len(out) >= k:
            break
    return out


def _cleaner(a: int, b: int) -> str:
    if a < b:
        return "pro 更干净"
    if b < a:
        return "flash 更干净"
    return "两版相同"


def flash_gate_line() -> str:
    """从 flash 台账读实测读数，给出闸门口径的一句话（读不到就返回空串）。"""
    path = os.path.join(version_dir("flash"), "自动标注台账.json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, encoding="utf-8") as fh:
            led = json.load(fh)
        counts = led.get("counts") or {}
        n = int(counts.get("items") or 0)
        total = int((counts.get("usage_total") or {}).get("total_tokens") or 0)
        if not n or not total:
            return ""
        return ("dev %d 条实测 total %s token、墙钟 %s 秒；按条目数线性外推 260 条 ＝ %s token，"
                "当时超过 300 万 token 闸门，停在 dev 并报告（该闸门已由作者 2026-09-27 提高到 450 万"
                "并放行全量，flash 版据此续跑 test 200）"
                % (n, "{:,}".format(total), counts.get("wall_seconds"),
                   "{:,}".format(int(total / n * 260))))
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def _load_json_or_none(path: str):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def collection_stats(dirname: str, suffix: str) -> dict:
    """集合级统计（只读产物）：规模／8 类事件分布／`event_time` 非空率／`quote` 逐字可定位率。

    `quote` 可定位口径与 `auto_annotate_compare.py` 一致：**严格子串**（`quote in text`，不去空白、
    不做 NFKC），text 取**交付文件**（`dev.jsonl`／`test.jsonl`）的本块原文。
    """
    truth = {}
    for split in ("dev", "test"):
        for rec in read_jsonl(os.path.join(eval_dir(), "%s.jsonl" % split)):
            truth[rec["item_id"]] = rec
    st = {"items": 0, "entities": 0, "events": 0, "relations": 0, "times": 0,
          "event_time_nonempty": 0, "quotes": 0, "quotes_located": 0,
          "event_types": Counter()}
    vd = os.path.join(eval_dir(), dirname)
    for split in ("dev", "test"):
        path = os.path.join(vd, "%s%s.jsonl" % (split, suffix))
        if not os.path.isfile(path):
            continue
        for rec in read_jsonl(path):
            ann = rec.get("annotation") or {}
            text = str((truth.get(rec.get("item_id")) or {}).get("text") or "")
            st["items"] += 1
            st["entities"] += len(_dicts(ann.get("entities")))
            events = _dicts(ann.get("events"))
            st["events"] += len(events)
            st["event_types"].update(str(e.get("event_type")) for e in events)
            for e in events:
                if str(e.get("event_time") or "").strip():
                    st["event_time_nonempty"] += 1
            st["relations"] += len(_dicts(ann.get("relations")))
            st["times"] += len(_dicts(ann.get("times")))
            for slot in ("entities", "events", "relations", "times", "ontology_boundary_log"):
                for x in _dicts(ann.get(slot)):
                    q = x.get("quote")
                    if isinstance(q, str) and q:
                        st["quotes"] += 1
                        if q in text:
                            st["quotes_located"] += 1
    return st


def _rate(a: int, b: int) -> str:
    return "%.1f%%（%d／%d）" % (100.0 * a / b, a, b) if b else "—（0／0）"


def disputed_reasons(out_dir: str) -> dict:
    """从提准台账里读 `disputed` 的原话（首轮 `items` ＋ 第二轮 `第二轮.items`）。"""
    led = _load_json_or_none(os.path.join(out_dir, "提准台账.json"))
    if not isinstance(led, dict):
        return {}
    out = OrderedDict()
    buckets = [("首轮", led.get("items") or {})]
    buckets.append(("第二轮", (led.get("第二轮") or {}).get("items") or {}))
    for round_name, rows in buckets:
        for iid, row in (rows or {}).items():
            for d in (row.get("disputed") or []):
                rule = d.get("rule")
                if not rule:
                    continue
                out.setdefault(rule, []).append(
                    OrderedDict([("round", round_name), ("item_id", iid),
                                 ("reason", str(d.get("reason") or "").strip())]))
    return out


def _short(text: str, n: int = 150) -> str:
    s = re.sub(r"\s+", " ", str(text or "")).strip()
    return s if len(s) <= n else s[:n] + "……"


def _before_after_table(L, out_dir, labels, names=None) -> None:
    """三处裁定：修正前（留档 `*.裁定前.json`）→ 修正后的逐规则命中变化。"""
    names = names or {}
    L += ["", "### 0.4 修正前后命中数变化（同一把尺子；留档 `*.裁定前.json`）", "",
          "| 规则 | " + " | ".join("%s 前→后（处／条）" % names.get(lb, lb) for lb in labels) + " |",
          "| --- | " + " | ".join("---" for _ in labels) + " |"]
    focus = ["R3_relation_endpoints_in_scope", "R6_times_event_mirror",
             "R9_event_without_participant"]
    for rule in focus:
        cells = []
        for lb in labels:
            before = _load_json_or_none(os.path.join(out_dir, "lint_命中_%s.裁定前.json" % lb))
            after = _load_json_or_none(os.path.join(out_dir, "lint_命中_%s.json" % lb))
            if not before or not after:
                cells.append("（无留档）")
                continue
            b, a = before["counts"][rule], after["counts"][rule]
            cells.append("%d／%d → %d／%d（%+d 处）"
                         % (b["hits"], b["items"], a["hits"], a["items"], a["hits"] - b["hits"]))
        L.append("| `%s` | %s |" % (rule, " | ".join(cells)))
    cells = []
    for lb in labels:
        before = _load_json_or_none(os.path.join(out_dir, "lint_命中_%s.裁定前.json" % lb))
        after = _load_json_or_none(os.path.join(out_dir, "lint_命中_%s.json" % lb))
        if not before or not after:
            cells.append("（无留档）")
            continue
        # 「前」「后」各按**当时的**硬规则清单求和（R3 修正前是硬、修正后是软）
        b_rules = [r for r, _t in (before.get("rules") or {}).get("hard") or HARD_RULES]
        a_rules = [r for r, _t in (after.get("rules") or {}).get("hard") or HARD_RULES]
        bh = sum(before["counts"][r]["hits"] for r in b_rules)
        ah = sum(after["counts"][r]["hits"] for r in a_rules)
        cells.append("**%d → %d（%+d 处）**｜硬命中条目 %d → %d"
                     % (bh, ah, ah - bh, before["items_with_hard_hits"], after["items_with_hard_hits"]))
    L.append("| **硬合计** | %s |" % " | ".join(cells))
    L += ["", "* 修正前＝规则 v1.1（11 硬＋4 软）的读数；修正后＝规则 v1.2（10 硬＋5 软）。"
              "`flash 提准后` 列的「后」还包含**第二轮定向修复**（见 `提准报告.md`）；"
              "pro／flash 两列的「后」只是规则 v1.2 重扫，没有再修任何标注。",
          "* `R3_relation_endpoints_in_scope` 的命中处数不变，性质由硬命中改为软提示（不再计入硬合计）。"]


def cmd_report(args) -> int:
    out_dir = args.out_dir or default_out_dir()
    labels = ["pro", "flash", "flash.repaired"]
    names = {"pro": "pro 版", "flash": "flash 版", "flash.repaired": "flash 提准后"}
    hits = OrderedDict((lb, _load_hits(out_dir, lb)) for lb in labels)
    pro, flash, rep = hits["pro"], hits["flash"], hits["flash.repaired"]
    L = []
    add = L.append
    add("# 自动标注 lint 报告（规则 v1.2：pro 版／flash 版／flash 提准后 三集合并列）")
    add("")
    add("> 工具：`代码\\抽取与图谱\\auto_annotate_lint.py`（**离线**，不调模型）。")
    add("> 命中清单逐条落在同目录 `lint_命中_pro.json`／`lint_命中_flash.json`／"
        "`lint_命中_flash.repaired.json`。")
    add("> 硬规则＝定义性违规；软规则＝提示性，由定向修复阶段裁决（不计入硬命中）。")
    add("> 口径：命中数＝**命中处数**（同一条目内同一规则多处命中算多处）；条目数＝**去重后的条目数**。")
    add("> **规则 v1.2（2026-09-27 作者裁定）**：`R9` 加 `ISSUED_BY` 豁免、`R6` 收窄、`R3` 由硬降级为软——"
        "见第零节「规则修正记录」（含被测模型在 `disputed` 里的原话与修正前后命中变化）。")
    add("")
    add("三集合参数：")
    add("")
    add("| 版本 | 目录 | 标注模型 | Prompt 版本 | 扫描范围 |")
    add("| --- | --- | --- | --- | --- |")
    for label in labels:
        p = hits[label]
        add("| %s | `%s` | `%s` | `%s` | %s |"
            % (names[label], os.path.relpath(p["input_dir"], ROOT),
               VERSIONS[label]["model"], VERSIONS[label]["prompt_version"],
               "＋".join(p.get("splits_present") or []) or "无"))
    if len({tuple(p.get("splits_present") or []) for p in hits.values()}) > 1:
        add("")
        add("> **扫描范围不一致（不能直接横向比总数）**：%s。"
            % "；".join("%s 为 %s" % (names[lb], "＋".join(hits[lb].get("splits_present") or []) or "无")
                        for lb in labels))
        gate = flash_gate_line()
        if gate:
            add("> flash 版的范围由**成本闸门**决定：%s（见 `自动标注_flash\\成本闸门报告.md`）。" % gate)
    add("")

    # ---- 零、规则修正记录（作者裁定 + 模型 disputed 原话 + 修正前后） ----
    add("## 零、规则修正记录（2026-09-27 作者裁定；规则 v1.1 → v1.2）")
    add("")
    add("> 本节登记的三处都是**作者的规则缺陷**，由被测模型在提准的 `disputed` 里指出"
        "（原话摘要引自 `提准台账.json`）——**不是**「模型不配合」。裁定不改任何标注内容。")
    add("")
    reasons = disputed_reasons(out_dir)

    def _reasons_md(rule):
        rows = reasons.get(rule) or []
        if not rows:
            return ["* （台账里没有该规则的 `disputed` 记录）"]
        out = []
        for row in rows:
            out.append("* `%s`（%s）：\"%s\"" % (row["item_id"], row["round"], _short(row["reason"])))
        return out

    add("### 0.1 `R9_event_without_participant` 加 `ISSUED_BY` 豁免")
    add("")
    add("* **裁定**：事件只要有 `ISSUED_BY` 边（不问事件类型），`participants` 为空即**不判违规**；"
        "R9 只在「既无 `participants`、又无 `ISSUED_BY`」时命中。依据《10》第4.5.2节 与"
        "《标注说明》第6.2节：「发布／作出方只写 `ISSUED_BY`，不再写 `PARTICIPATES_IN`」。"
        "适用于 DEV-057／TEST-041／TEST-184。")
    add("* **落法（diff）**：`rule_r9_event_without_participant` 先收 `relations[].relation == \"ISSUED_BY\"` "
        "两端的 `*_ref` 成集合；`if _dicts(ev.get(\"participants\")): continue` 之后新增 "
        "`if ev.get(\"event_ref\") in issued_by_events: continue`，命中文案改为「既没有 participants、"
        "也没有 ISSUED_BY 边」。")
    add("* **模型原话（摘要引用）**：")
    L += _reasons_md("R9_event_without_participant")
    add("")
    add("### 0.2 `R6_times_event_mirror` 收窄")
    add("")
    add("* **裁定**：只在两种情形命中——**(a)** `events[]` 为空而 `times[]` 含 `time_type=event_time` 的项；"
        "**(b)** 某事件 `event_time` 非空、而 `times[]` 里没有同值项。**不再**把「`times[]` 记录多个彼此"
        "独立的日期而事件的 `event_time` 为 `null`」判为违规——那是「一事只写一条、不能确定到日写 null」"
        "的正确写法（多日期安排型公告）。适用于 TEST-017。")
    add("* **落法（diff）**：删除「`times[]` 的 `event_time` 项必须能在 `events[].event_time` 找到同值项」"
        "这一向；`events[]` 为空且有 `event_time` 型 `times` 项时给一条集合级命中；"
        "`event_time=null` 的事件不再参与比较。")
    add("* **模型原话（摘要引用）**：")
    L += _reasons_md("R6_times_event_mirror")
    add("")
    add("### 0.3 `R3_relation_endpoints_in_scope` 降级为软提示")
    add("")
    add("* **裁定**：公司间关系与 `BELONGS_TO` 的端点不在 105 家名单内 → **只提示、不判硬违规**。"
        "理由：那是**图谱写入层**的约束（写图时跳过并计数），标注层的事实仍由原文逐字证据支撑；"
        "该情形已由 `R4_out_of_scope_logged`（`company_out_of_scope` 登记）覆盖。适用于 TEST-167。")
    add("* **落法（diff）**：`R3_relation_endpoints_in_scope` 从 `HARD_RULES` 移入 `SOFT_RULES`"
        "（规则 id 保留、不改名），新增 `is_hard_rule()`，硬／软判定改看清单而**不看名字前缀**"
        "（`R3_*` 不再落进硬桶、不触发定向修复）；selftest 增加「R3 只出软提示」断言。")
    add("* **模型原话（摘要引用）**：")
    L += _reasons_md("R3_relation_endpoints_in_scope")
    _before_after_table(L, out_dir, labels, names=names)
    add("")
    add("## 一、三集合同规则命中对照（同一把尺子）")
    add("")
    add("| 规则 | 类型 | pro 处数 | pro 条目 | flash 处数 | flash 条目 | 提准后 处数 | 提准后 条目 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for rule, _t in HARD_RULES + SOFT_RULES:
        a, b, c = (pro["counts"][rule], flash["counts"][rule], rep["counts"][rule])
        add("| `%s` | %s | %d | %d | %d | %d | %d | %d |"
            % (rule, "硬" if is_hard_rule(rule) else "软",
               a["hits"], a["items"], b["hits"], b["items"], c["hits"], c["items"]))
    add("")
    add("合计：**硬命中** pro %d 处（%d 条有命中）／flash %d 处（%d 条有命中）／"
        "flash 提准后 %d 处（%d 条有命中）；**软提示** pro %d 处／flash %d 处／提准后 %d 处。"
        % (sum(pro["counts"][r]["hits"] for r, _t in HARD_RULES), pro["items_with_hard_hits"],
           sum(flash["counts"][r]["hits"] for r, _t in HARD_RULES), flash["items_with_hard_hits"],
           sum(rep["counts"][r]["hits"] for r, _t in HARD_RULES), rep["items_with_hard_hits"],
           sum(pro["counts"][r]["hits"] for r, _t in SOFT_RULES),
           sum(flash["counts"][r]["hits"] for r, _t in SOFT_RULES),
           sum(rep["counts"][r]["hits"] for r, _t in SOFT_RULES)))
    add("")

    # ---- 一之二、集合级统计（三集合） ----
    add("## 一之二、集合级统计（三集合）")
    add("")
    add("> `quote` 逐字可定位率＝严格子串（`quote in 本块 text`，不去空白、不做 NFKC），"
        "与本目录 `两版对照报告.md` 同一口径。")
    add("")
    st = OrderedDict((lb, collection_stats(VERSIONS[lb]["dirname"], VERSIONS[lb]["suffix"]))
                     for lb in labels)
    add("### 规模")
    add("")
    add("| 项 | pro | flash | flash 提准后 |")
    add("| --- | --- | --- | --- |")
    for key, title in (("items", "条目"), ("entities", "实体 条数"), ("events", "事件 条数"),
                       ("relations", "关系 条数"), ("times", "times 条数")):
        add("| %s | %d | %d | %d |" % (title, st["pro"][key], st["flash"][key], st["flash.repaired"][key]))
    add("")
    add("### 8 类事件分布")
    add("")
    add("| event_type | pro | flash | flash 提准后 |")
    add("| --- | --- | --- | --- |")
    for et in list(config.EVENT_TYPES):
        add("| %s | %d | %d | %d |"
            % (et, st["pro"]["event_types"].get(et, 0), st["flash"]["event_types"].get(et, 0),
               st["flash.repaired"]["event_types"].get(et, 0)))
    add("")
    add("### 时间与 quote")
    add("")
    add("| 指标 | pro | flash | flash 提准后 |")
    add("| --- | --- | --- | --- |")
    add("| `event_time` 非空率 | %s | %s | %s |"
        % (_rate(st["pro"]["event_time_nonempty"], st["pro"]["events"]),
           _rate(st["flash"]["event_time_nonempty"], st["flash"]["events"]),
           _rate(st["flash.repaired"]["event_time_nonempty"], st["flash.repaired"]["events"])))
    add("| `quote` 逐字可定位率（quote ⊂ 本块 text） | %s | %s | %s |"
        % (_rate(st["pro"]["quotes_located"], st["pro"]["quotes"]),
           _rate(st["flash"]["quotes_located"], st["flash"]["quotes"]),
           _rate(st["flash.repaired"]["quotes_located"], st["flash.repaired"]["quotes"])))
    add("")
    add("## 一之三、R2 简繁书写面登记（折叠后核到代码、**不再命中 R2** 的条目）")
    add("")
    add("> 规则 v1.1 起，`R2_code_source` 的名字比对走 `NFKC ＋ 常用简繁／异体单字折叠`"
        "（只动单字，不动数字与括号）。下列条目「代码正确、书写面是繁体／异体」，折叠后能核到代码，"
        "因此**不再算 R2 违规**；但逐条登记在此，供下游消歧（同一家公司两种书写面／名字指向的代码"
        "与条目填的代码不一致）。**港股代码**（`01211, 81211`／`3288`）不在此列——它们代码本身就违规，"
        "继续命中 R1／R2。")
    add("")
    trad_rows = []
    for _label in labels:
        _p = hits[_label]
        for _n in (_p.get("traditional_name_surfaces") or []):
            trad_rows.append((names[_label], _n))
    if not trad_rows:
        add("* 三集合均无此类登记。")
    else:
        add("| 版本 | item_id | 定位 | 类别 | 书写面 | 折叠后 | 条目填的代码 | 折叠后能核到的代码 | 代码一致 |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for _label, _n in trad_rows:
            add("| %s | `%s` | `%s` | %s | %s | %s | `%s` | %s | %s |"
                % (_label, _n.get("item_id"), _n.get("location"), _n.get("kind") or "？",
                   _n.get("written"), _n.get("folded"),
                   _n.get("stock_code") or "（空）",
                   "、".join(_n.get("codes_after_fold") or []),
                   "是" if _n.get("code_matches") else "**否**"))
    add("")
    add("## 二、逐规则按 split 分布（命中处数）")
    add("")
    add("| 规则 | pro dev | pro test | flash dev | flash test | 提准后 dev | 提准后 test |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for rule, _t in HARD_RULES + SOFT_RULES:
        a, b, c = pro["counts"][rule], flash["counts"][rule], rep["counts"][rule]
        add("| `%s` | %d | %d | %d | %d | %d | %d |"
            % (rule, a["by_split"]["dev"], a["by_split"]["test"],
               b["by_split"]["dev"], b["by_split"]["test"],
               c["by_split"]["dev"], c["by_split"]["test"]))
    add("")
    add("## 三、每规则例子（含 item_id 与原文片段）")
    add("")
    for rule, title in HARD_RULES + SOFT_RULES:
        add("### `%s` — %s" % (rule, title))
        add("")
        any_hit = False
        for label in labels:
            p = hits[label]
            exs = _examples(p, rule, 3)
            if not exs:
                add("* %s：0 处命中。" % names[label])
                continue
            any_hit = True
            for h in exs:
                add("* %s｜`%s`｜%s｜%s" % (names[label], h["item_id"], h["location"], h["detail"]))
                add("  * 片段：`%s`" % (h.get("snippet") or "").replace("\n", " ")[:160])
        if not any_hit:
            add("* 三集合均 0 处命中。")
        add("")
    add("## 四、R7a 逐条判定依据（两层判据，对齐作者独立复算）")
    add("")
    add("口径（作者 2026-09-27 裁定）：")
    add("")
    add("* **A 层**＝实体的类型名键（`company_name`／`person_name`／`industry_name`／"
        "`institution_name`／`policy_name`）在本块 `text` 与全篇 `doc_text` 里都**不是连续书写面**。"
        "匹配只去空白，**不做 NFKC 宽度折叠**（「（特殊普通合伙）」≠「(特殊普通合伙)」）。"
        "「公司」「发行人」「本公司」这类**指代性别名**只作为证据登记，**不救 A 层**。")
    add("* **B 层**＝名字键**连同全部别名**都不可定位（含没有类型名键值的实体）。")
    add("* 两层取并集；命中里给出层号与「哪些书写面能定位」。")
    add("")
    add("> 差异说明（为什么旧版 lint 只报 1 条）：旧版 R7a 用 `NFKC＋去空白` 定位 ——（1）NFKC 把"
        "TEST-199 的「中汇会计师事务所（特殊普通合伙）」（全角括号）与全文里的"
        "「中汇会计师事务所(特殊普通合伙)」（半角括号）折叠成同一个书写面，于是漏报；"
        "（2）把「发行人」这类**指代性**别名也算作名字键的可定位证据，于是 TEST-047 被救掉。"
        "新版按作者判据改成「只去空白」＋「指代性别名不救 A 层」，pro 版 260 条上命中数与作者独立复算"
        "一致（3 条：TEST-047／TEST-185／TEST-199）。")
    add("")
    _r7a_any = False
    for label in labels:
        p = hits[label]
        rows = [(iid, h) for iid, res in p["items"].items()
                for h in (res["hard"].get("R7a_quote_fabricated") or [])]
        add("### %s（%d 条命中）" % (names[label], len(rows)))
        add("")
        if not rows:
            add("* 无命中。")
            add("")
            continue
        _r7a_any = True
        add("| item_id | 层 | 定位 | 判定依据 | 本块/全篇能定位的书写面 | 复核线索（NFKC 后能定位的名键） |")
        add("| --- | --- | --- | --- | --- | --- |")
        for iid, h in rows:
            ev = h.get("evidence") or {}
            add("| `%s` | %s | `%s` | %s | %s | %s |"
                % (iid, ev.get("tier") or "？", h.get("location"), h.get("detail"),
                   "、".join(ev.get("located_surfaces") or []) or "（无）",
                   ("、".join(ev.get("nfkc_located_primary") or [])
                    + "（宽度／兼容字符差异，正文里其实是这个名字）")
                   if ev.get("nfkc_located_primary")
                   else "—（NFKC 后也定位不到）"))
        add("")
    if not _r7a_any:
        add("* 三集合均 0 处命中。")
        add("")
    add("**复核意见（工具的证据读法，不代替作者裁定）**：三处命中按作者判据都成立，但性质不同——"
        "「复核线索」列里凡是 NFKC 后能定位的名键，命中的成因是**全半角／兼容字符的书写面形态**"
        "（如 TEST-199 的「（特殊普通合伙）」在正文里写作半角「(特殊普通合伙)」），"
        "不是「正文里根本没有这个名字」；「能定位的书写面」列只有指代性别名（如 TEST-047 的「发行人」）"
        "而名键本身是**拼合书写面**（英文全称＋中文全称），说明正文写了组成部分、没写整体；"
        "两列都是「—／（无）」的（如 TEST-185）才是**正文里没有的名字**。"
        "下游消歧可据此区分「形态差异／拼合」与「真编造」，处置方式不应一样。")
    add("")
    add("---")
    add("")
    add("生成时间：%s｜%s"
        % (now_iso(), "｜".join("%s 扫描于 %s" % (names[lb], hits[lb]["generated_at"])
                                for lb in labels)))
    add("")
    path = os.path.join(out_dir, "lint报告.md")
    write_text_atomic(path, "\n".join(L))
    print("lint 报告：%s" % path)
    return 0


# --------------------------------------------------------------------------
# 自测：每条规则正反用例（合成条目，不读真实产物）
# --------------------------------------------------------------------------
def _rec(item_id, text, doc_text, ann) -> OrderedDict:
    return OrderedDict([("item_id", item_id), ("split", "dev"), ("chunk_id", 9990001),
                        ("doc_id", 999), ("text", text), ("doc_text", doc_text),
                        ("annotation", ann)])


def _ann(entities=(), events=(), relations=(), times=(), oblog=(), notes="") -> OrderedDict:
    return OrderedDict([("status", "auto_annotated"), ("entities", list(entities)),
                        ("events", list(events)), ("relations", list(relations)),
                        ("times", list(times)), ("ontology_boundary_log", list(oblog)),
                        ("notes", notes)])


def _company(ref, code, name, short, quote, aliases=()):
    return OrderedDict([("entity_type", "Company"), ("entity_ref", ref), ("quote", quote),
                        ("chunk_id", 9990001), ("stock_code", code), ("company_name", name),
                        ("short_name", short), ("aliases", list(aliases)),
                        ("exchange", "深圳证券交易所")])


def _industry(ref, name, quote):
    return OrderedDict([("entity_type", "Industry"), ("entity_ref", ref), ("quote", quote),
                        ("chunk_id", 9990001), ("industry_code", "I01"),
                        ("industry_name", name), ("level", "一级")])


def _institution(ref, name, quote):
    return OrderedDict([("entity_type", "Institution"), ("entity_ref", ref), ("quote", quote),
                        ("chunk_id", 9990001), ("institution_id", "INS-1"),
                        ("institution_name", name), ("institution_type", "监管机构")])


def _event(ref, etype, name, quote, participants, event_time=None):
    return OrderedDict([("event_ref", ref), ("event_type", etype), ("event_name", name),
                        ("event_time", event_time), ("description", name),
                        ("confidence", 0.9), ("participants", list(participants)),
                        ("quote", quote), ("chunk_id", 9990001)])


def _part(ref, role):
    return OrderedDict([("entity_ref", ref), ("role", role)])


def _rel(name, fl, fr, tl, tr, quote, role=None):
    out = OrderedDict([("relation", name), ("from_label", fl), ("from_ref", fr),
                       ("to_label", tl), ("to_ref", tr), ("quote", quote),
                       ("source_doc_id", 999), ("source_chunk_id", 9990001),
                       ("confidence", 0.9)])
    if role is not None:
        out["role"] = role
    return out


SELFTEST_TEXT = "平安银行于2026年3月5日与万科A签署重大合同，合同金额一亿元，深圳证券交易所对本次交易出具监管函。"
SELFTEST_DOC = SELFTEST_TEXT + "公司代码 000001、000002。"
_Q = "平安银行于2026年3月5日与万科A签署重大合同"


def _clean_annotation() -> OrderedDict:
    return _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行"),
                  _company("E2", "000002", "万科A", "万科A", "万科A"),
                  _industry("E3", "银行", "银行")],
        events=[_event("V1", "重大合同", "平安银行与万科A签署重大合同", _Q,
                       [_part("E1", "主体"), _part("E2", "合作方")], "2026-03-05")],
        relations=[
            _rel("PARTICIPATES_IN", "Company", "E1", "Event", "V1", _Q, role="主体"),
            _rel("PARTICIPATES_IN", "Company", "E2", "Event", "V1", _Q, role="合作方"),
            _rel("BELONGS_TO", "Company", "E1", "Industry", "E3", "银行"),
        ],
        times=[OrderedDict([("time_type", "event_time"), ("value", "2026-03-05"),
                            ("quote", "平安银行于2026年3月5日")])],
    )


def selftest_cases() -> list:
    """返回 [(规则, 期望命中数>0?, 用例名, rec), …]：每条规则正例＋反例，另加全清白条目。"""
    cases = []
    clean = _rec("ST-CLEAN", SELFTEST_TEXT, SELFTEST_DOC, _clean_annotation())
    cases.append(("_clean", False, "全清白条目（所有规则都要 0 命中）", clean))

    good_r1 = _rec("ST-R1N", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行")]))
    bad_r1 = _rec("ST-R1", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "01211", "平安银行", "平安银行", "平安银行")]))
    cases.append(("R1_code_format", True, "5 位港股代码 01211", bad_r1))
    cases.append(("R1_code_format", False, "6 位 A 股代码 000001", good_r1))

    bad_r2 = _rec("ST-R2", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000002", "平安银行", "平安银行", "平安银行")]))
    cases.append(("R2_code_source", True, "代码 000002 配名字「平安银行」", bad_r2))
    cases.append(("R2_code_source", False, "代码 000001 配名字「平安银行」", good_r1))

    # 简繁折叠（作者 2026-09-27 裁定）：繁体书写面折叠后能核到代码 → 不算 R2 命中，但要登记
    trad_ok = _rec("ST-R2T", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安銀行股份有限公司", "平安銀行", "平安銀行")]))
    cases.append(("R2_code_source", False, "繁体书写面「平安銀行股份有限公司」＋正确代码（折叠后核到，不命中）",
                  trad_ok))
    trad_bad = _rec("ST-R2TB", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "3288", "平安銀行股份有限公司", "平安銀行", "平安銀行")]))
    cases.append(("R2_code_source", True, "繁体书写面＋港股代码 3288（代码本身违规，仍命中）", trad_bad))

    bad_r3 = _rec("ST-R3", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行"),
                  _company("E2", "", "某外部公司", "某外部公司", "某外部公司")],
        relations=[_rel("COMPETES_WITH", "Company", "E1", "Company", "E2", "平安银行")]))
    endpoints_ok = _rec("ST-R3N2", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行"),
                  _company("E2", "", "某外部公司", "某外部公司", "某外部公司")]))
    good_r3 = _rec("ST-R3N", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行")],
        relations=[_rel("SUPPLIES", "Company", "E1", "Company", "E1", "平安银行")]))
    # 作者 2026-09-27 裁定：R3 降级为**软提示**（命中照出，但不进硬桶、不触发修复）
    cases.append(("R3_relation_endpoints_in_scope", True,
                  "COMPETES_WITH 端点是名单外公司（只出软提示）", bad_r3))
    cases.append(("R3_relation_endpoints_in_scope", False, "两端都在名单内", good_r3))

    cases.append(("R4_out_of_scope_logged", True, "图谱端点是名单外公司、未登记", bad_r3))
    cases.append(("R4_out_of_scope_logged", False,
                  "名单外公司只作实体、没进任何关系（规则 v1.1 收窄到端点后不再命中）", endpoints_ok))
    logged = _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行"),
                  _company("E2", "", "某外部公司", "某外部公司", "某外部公司")],
        relations=[_rel("SUPPLIES", "Company", "E1", "Company", "E2", "某外部公司")],
                  oblog=[OrderedDict([("case_id", "OB-ST-R4N-1"),
                                      ("case_type", "company_out_of_scope"),
                                      ("summary", "名单外公司"), ("quote", "某外部公司"),
                                      ("chunk_id", 9990001), ("suggested_handling", "只登记")])])
    cases.append(("R4_out_of_scope_logged", False, "图谱端点是名单外公司、已登记 company_out_of_scope",
                  _rec("ST-R4N", SELFTEST_TEXT, SELFTEST_DOC, logged)))

    bad_r5 = _rec("ST-R5", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行")],
        events=[_event("V1", "重大合同", "平安银行签署重大合同", _Q,
                       [_part("E1", "主体")], "2026-03-05")]))
    cases.append(("R5_participants_relation_mirror", True, "participants 有而 relations 缺", bad_r5))
    cases.append(("R5_participants_relation_mirror", False, "participants 与 PARTICIPATES_IN 一一对应", clean))

    bad_r6 = _rec("ST-R6", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        events=[_event("V1", "重大合同", "签署重大合同", _Q,
                       [_part("E1", "主体")], "2026-03-05")],
        times=[OrderedDict([("time_type", "event_time"), ("value", "2026-03-06"),
                            ("quote", "平安银行")])]))
    cases.append(("R6_times_event_mirror", True, "事件 event_time=2026-03-05、times 里没有同值项", bad_r6))
    cases.append(("R6_times_event_mirror", False, "times 与事件 event_time 一致", clean))
    # 作者 2026-09-27 裁定：收窄到两种情形（events 为空有 times 项命中；多日期＋event_time=null 不命中）
    r6_no_events = _rec("ST-R6NE", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        times=[OrderedDict([("time_type", "event_time"), ("value", "2026-03-05"),
                            ("quote", "平安银行于2026年3月5日")])]))
    cases.append(("R6_times_event_mirror", True, "events[] 为空而 times[] 有 event_time 项", r6_no_events))
    r6_multi_dates = _rec("ST-R6MD", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行")],
        events=[_event("V1", "股权", "平安银行实施利润分配", _Q, [_part("E1", "主体")], None)],
        times=[OrderedDict([("time_type", "event_time"), ("value", d), ("quote", "平安银行")])
               for d in ("2026-09-25", "2026-09-30", "2026-10-08")],
        relations=[_rel("PARTICIPATES_IN", "Company", "E1", "Event", "V1", _Q, role="主体")]))
    cases.append(("R6_times_event_mirror", False,
                  "多日期安排型（有事件、event_time=null、times 记多个独立日期）——不再命中", r6_multi_dates))

    bad_r7 = _rec("ST-R7", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "某编造公司", "某编造公司", "某编造公司")]))
    cases.append(("R7a_quote_fabricated", True, "名字键「某编造公司」正文里没有（A＋B 层）", bad_r7))
    cases.append(("R7a_quote_fabricated", False, "名字键在正文里", clean))
    # 作者 2026-09-27 裁定后的两层判据：只去空白、不做 NFKC 宽度折叠
    r7a_alias_only = _rec(
        "ST-R7A",
        "本行设立境外子公司 SHANGHAI ELECTRIC GLOBAL CAPITAL LIMITED（上海电\n"
        "气环球资本有限公司，以下简称“发行人”），由发行人作为发行主体发行境外债券。",
        SELFTEST_DOC,
        _ann(entities=[OrderedDict([
            ("entity_type", "Company"), ("entity_ref", "E1"), ("quote", "发行人"),
            ("chunk_id", 9990001), ("stock_code", ""),
            ("company_name",
             "SHANGHAI ELECTRIC GLOBAL CAPITAL LIMITED（上海电气环球资本有限公司）"),
            ("short_name", "发行人"), ("aliases", ["发行人", "上海电气环球资本有限公司"]),
            ("exchange", "")])]))
    cases.append(("R7a_quote_fabricated", True,
                  "A 层：名字键是拼合书写面（正文只有组成部分、只有指代性别名能定位）", r7a_alias_only))
    r7a_doc_only = _rec(
        "ST-R7AN", "中汇所未能了解和测试被审计单位的内部控制。",
        "中汇所未能了解和测试江苏吴中医药发展股份有限公司的内部控制。",
        _ann(entities=[OrderedDict([
            ("entity_type", "Company"), ("entity_ref", "E1"), ("quote", "江苏吴中"),
            ("chunk_id", 9990001), ("stock_code", ""),
            ("company_name", "江苏吴中医药发展股份有限公司"), ("short_name", "江苏吴中"),
            ("aliases", ["江苏吴中"]), ("exchange", "")])]))
    cases.append(("R7a_quote_fabricated", False,
                  "名字键在全篇里能定位（只在本块之外）→ 不命中（那是 S1 的提示）", r7a_doc_only))
    r7a_width = _rec(
        "ST-R7W", "审计机构为中汇会计师事务所(特殊普通合伙)。", SELFTEST_DOC,
        _ann(entities=[_institution("E1", "中汇会计师事务所（特殊普通合伙）", "中汇会计师事务所")]))
    cases.append(("R7a_quote_fabricated", True,
                  "全角／半角括号书写面不同（不做 NFKC 折叠）→ 命中 A 层", r7a_width))

    bad_r8 = _rec("ST-R8", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_institution("E1", "深圳证券交易所", "深圳证券交易所")],
        events=[_event("V1", "监管", "深圳证券交易所出具监管函",
                       "深圳证券交易所对本次交易出具监管函", [_part("E1", "监管方")])],
        relations=[_rel("ISSUED_BY", "Event", "V1", "Institution", "E1",
                        "深圳证券交易所对本次交易出具监管函")]))
    good_r8 = _rec("ST-R8N", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_institution("E1", "深圳证券交易所", "深圳证券交易所")],
        events=[_event("V1", "监管", "深圳证券交易所出具监管函",
                       "深圳证券交易所对本次交易出具监管函", [])],
        relations=[_rel("ISSUED_BY", "Event", "V1", "Institution", "E1",
                        "深圳证券交易所对本次交易出具监管函")]))
    cases.append(("R8_issued_by_role_conflict", True, "ISSUED_BY 终点又写进 participants", bad_r8))
    cases.append(("R8_issued_by_role_conflict", False, "只写 ISSUED_BY、participants 为空", good_r8))

    # 作者 2026-09-27 裁定：有 ISSUED_BY 边的事件 participants 为空**不命中**；两者都没有才命中
    no_issued = _rec("ST-R9", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_institution("E1", "深圳证券交易所", "深圳证券交易所")],
        events=[_event("V1", "监管", "深圳证券交易所出具监管函",
                       "深圳证券交易所对本次交易出具监管函", [])]))
    cases.append(("R9_event_without_participant", True, "既无 participants、又无 ISSUED_BY 边", no_issued))
    cases.append(("R9_event_without_participant", False, "有 ISSUED_BY 边、participants 为空（豁免）", good_r8))
    cases.append(("R9_event_without_participant", False, "事件有参与主体", clean))

    bad_r10 = _rec("ST-R10", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        events=[_event("V1", "重大合同", "签署重大合同", _Q, [_part("E1", "主体")], "2026-03-05"),
                _event("V2", "重大合同", "签署重大合同 ", _Q, [_part("E1", "主体")], "2026-03-05")]))
    cases.append(("R10_duplicate_event_in_item", True, "同类型同名字（含空白差异）", bad_r10))
    cases.append(("R10_duplicate_event_in_item", False, "事件名各不相同", clean))

    bad_r11 = _rec("ST-R11", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        oblog=[OrderedDict([("case_id", "OB-1"), ("case_type", "made_up_type"),
                            ("summary", "x"), ("quote", "某外部公司"),
                            ("chunk_id", 9990001), ("suggested_handling", "只登记")])]))
    cases.append(("R11_boundary_case_type", True, "自造 case_type", bad_r11))
    cases.append(("R11_boundary_case_type", False, "case_type=company_out_of_scope",
                  _rec("ST-R11N", SELFTEST_TEXT, SELFTEST_DOC, logged)))

    text_s1 = "公司于2026年3月5日与万科A签署重大合同。"
    doc_s1 = "平安银行公告：" + text_s1
    cases.append(("S1_quote_not_supporting_name", True, "名字只出现在全篇",
                  _rec("ST-S1", text_s1, doc_s1, _ann(
                      entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行")]))))
    cases.append(("S1_quote_not_supporting_name", False, "名字在本块", clean))

    bad_s2 = _rec("ST-S2", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        events=[_event("V1", "股权", "关于发行可转债的议案获股东大会审议通过", _Q,
                       [_part("E1", "主体")], "2026-03-05")]))
    cases.append(("S2_procedural_event_name", True, "「…议案获…审议通过」", bad_s2))
    cases.append(("S2_procedural_event_name", False, "实体事项式事件名", clean))

    bad_s3 = _rec("ST-S3", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        events=[_event("V1", "重大合同", "签署重大合同", _Q,
                       [_part("E1", "主体")], "2026-04-09")]))
    cases.append(("S3_time_not_in_text", True, "event_time=2026-04-09 正文没有", bad_s3))
    cases.append(("S3_time_not_in_text", False, "event_time 在正文里", clean))

    bad_s4 = _rec("ST-S4", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安银行", "平安银行", "平安银行")],
        events=[_event("V1", "重大合同", "签署重大合同", _Q,
                       [_part("E1", "合作方")], "2026-03-05")]))
    cases.append(("S4_no_subject_role", True, "无主体、无 ISSUED_BY（强提示）", bad_s4))
    cases.append(("S4_no_subject_role", True, "无主体、有 ISSUED_BY（弱提示）", bad_r8))
    cases.append(("S4_no_subject_role", False, "有 role=主体", clean))
    return cases


def cmd_selftest(args) -> int:
    cases = selftest_cases()
    failed = 0
    by_rule = OrderedDict((r, {"pos": 0, "neg": 0, "fail": []}) for r in ALL_RULES)
    print("lint 规则正反自测（离线，不读真实产物、不调模型）：")
    for rule, expect, name, rec in cases:
        res = lint_record(rec)
        if rule == "_clean":
            hits = sum(len(v) for v in res["hard"].values()) + sum(len(v) for v in res["soft"].values())
            ok = hits == 0
        else:
            bucket = res["hard"] if is_hard_rule(rule) else res["soft"]
            hits = len(bucket.get(rule) or [])
            ok = (hits > 0) if expect else (hits == 0)
            if rule in by_rule:
                by_rule[rule]["pos" if expect else "neg"] += 1
        if not ok:
            failed += 1
            if rule in by_rule:
                by_rule[rule]["fail"].append(name)
        print("  [%s] %-34s 期望命中=%s 实际命中=%d｜%s"
              % ("OK" if ok else "FAIL", rule, int(bool(expect)), hits, name))
    for rule, _t in HARD_RULES + SOFT_RULES:
        s = by_rule.get(rule) or {}
        ok = s.get("pos", 0) >= 1 and s.get("neg", 0) >= 1 and not s.get("fail")
        if not ok:
            failed += 1
        print("  [%s] %-34s 正例 %d 条／反例 %d 条%s"
              % ("OK" if ok else "FAIL", rule, s.get("pos", 0), s.get("neg", 0),
                 ("；失败用例：%s" % "；".join(s.get("fail") or [])) if s.get("fail") else ""))
    # 附加断言：简繁折叠与 R7a 两层的**结构性**口径（不只数命中条数）
    extra = []
    extra.append(("简繁折叠不动数字与括号",
                  fold_simp("01211, 81211（集团）") == "01211, 81211(集团)"))
    extra.append(("简繁折叠把繁体公司名折到简体",
                  fold_simp("豪威集成電路（集團）股份有限公司") == "豪威集成电路(集团)股份有限公司"))
    trad_rec = _rec("ST-S2T", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "平安銀行股份有限公司", "平安銀行", "平安銀行")]))
    notes = traditional_surface_notes(trad_rec, trad_rec["annotation"])
    extra.append(("繁体书写面进「简繁书写面登记」（折叠后可核到 000001）",
                  bool(notes) and notes[0]["folded"] == "平安银行股份有限公司"
                  and notes[0]["codes_after_fold"] == ["000001"] and notes[0]["code_matches"]))
    r7ab = lint_record(_rec("ST-R7X", SELFTEST_TEXT, SELFTEST_DOC, _ann(
        entities=[_company("E1", "000001", "某编造公司", "某编造公司", "某编造公司")])))
    extra.append(("R7a 命中标 A+B 层",
                  bool(r7ab["hard"]["R7a_quote_fabricated"])
                  and (r7ab["hard"]["R7a_quote_fabricated"][0].get("evidence") or {}).get("tier") == "A+B"))
    r7a_case = [c for c in cases if c[2].startswith("A 层：名字键是拼合书写面")][0]
    r7a_res = lint_record(r7a_case[3])
    extra.append(("R7a 命中标 A 层（指代性别名可定位）",
                  bool(r7a_res["hard"]["R7a_quote_fabricated"])
                  and (r7a_res["hard"]["R7a_quote_fabricated"][0].get("evidence") or {}).get("tier") == "A"))
    # 2026-09-27 三处裁定：R3 只出软提示、R9 有 ISSUED_BY 豁免、R6 多日期（event_time=null）不命中
    r3_case = [c for c in cases if c[2].startswith("COMPETES_WITH 端点是名单外公司")][0]
    r3_soft = lint_record(r3_case[3])
    extra.append(("R3 只出软提示（硬桶为空、软桶有命中）",
                  not r3_soft["hard"].get("R3_relation_endpoints_in_scope")
                  and bool(r3_soft["soft"].get("R3_relation_endpoints_in_scope"))
                  and "R3_relation_endpoints_in_scope" in [r for r, _t in SOFT_RULES]
                  and "R3_relation_endpoints_in_scope" not in [r for r, _t in HARD_RULES]))
    r9_exempt = [c for c in cases if c[2].startswith("有 ISSUED_BY 边、participants 为空")][0]
    r9_res = lint_record(r9_exempt[3])
    extra.append(("R9 有 ISSUED_BY 边、participants 为空 → 不命中",
                  not r9_res["hard"].get("R9_event_without_participant")))
    r9_miss = [c for c in cases if c[2].startswith("既无 participants")][0]
    r9_miss_res = lint_record(r9_miss[3])
    extra.append(("R9 既无 participants、又无 ISSUED_BY 边 → 命中",
                  bool(r9_miss_res["hard"].get("R9_event_without_participant"))))
    r6_multi = [c for c in cases if c[2].startswith("多日期安排型")][0]
    r6_multi_res = lint_record(r6_multi[3])
    extra.append(("R6 多日期安排型（event_time=null）→ 不命中",
                  not r6_multi_res["hard"].get("R6_times_event_mirror")))
    r6_no_ev = [c for c in cases if c[2].startswith("events[] 为空而 times[] 有")][0]
    r6_no_ev_res = lint_record(r6_no_ev[3])
    extra.append(("R6 events[] 为空而 times[] 有 event_time 项 → 命中",
                  bool(r6_no_ev_res["hard"].get("R6_times_event_mirror"))))
    for name, ok in extra:
        failed += 0 if ok else 1
        print("  [%s] %s" % ("OK" if ok else "FAIL", name))
    print("lint 自测：%s（退出码 %d）"
          % ("全部通过" if not failed else "%d 项失败" % failed, 1 if failed else 0))
    return 1 if failed else 0


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="auto_annotate_lint.py",
        description="自动标注（模型参照集）的离线 lint：逐条扫规则、输出命中清单，不调模型。",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command")
    pl = sub.add_parser("lint", help="扫某一版（或 all）")
    pl.add_argument("--version", default="flash", choices=list(VERSIONS) + ["all"],
                    help="pro／flash／flash.repaired（提准产物）／all")
    pl.add_argument("--out-dir", default=None, help="落点（默认 %s）" % OUT_DIR_DEFAULT)
    pl.add_argument("--input-dir", default=None,
                    help="改扫别的产物目录（如 `自动标注\\提准`），默认各版自己的目录")
    pl.add_argument("--suffix", default=None,
                    help="产物文件名后缀：`<split><suffix>.jsonl`（默认按版本：pro／flash＝.auto，"
                         "flash.repaired＝.auto.repaired）")
    pl.add_argument("--tag", default=None,
                    help="输出文件名加后缀：`lint_命中_<version>.<tag>.json`（默认不加）")
    pr = sub.add_parser("report", help="三集合并列对照，写 lint报告.md")
    pr.add_argument("--out-dir", default=None)
    pd = sub.add_parser("diff", help="两份命中清单的逐规则对照（修复前后），不调模型")
    pd.add_argument("--before", required=True)
    pd.add_argument("--after", required=True)
    pd.add_argument("--label", default="修复前后")
    pd.add_argument("--out", default=None, help="写 Markdown 对照表；不给就打印")
    sub.add_parser("selftest", help="每条规则正反自测（退出码 0／1）")
    return p


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    setup_console()
    args = build_parser().parse_args(argv)
    cmd = args.command or "lint"
    if cmd == "selftest":
        return cmd_selftest(args)
    if cmd == "report":
        return cmd_report(args)
    if cmd == "diff":
        return cmd_diff(args)
    if not getattr(args, "version", None):
        args.version = "flash"
    return cmd_lint(args)


if __name__ == "__main__":
    sys.exit(main())
