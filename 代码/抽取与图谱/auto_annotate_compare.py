# -*- coding: utf-8 -*-
r"""auto_annotate_compare.py —— 两版自动标注（pro 版 vs flash 版）的**离线**对照。

只读产物：`自动标注\{dev,test}.auto.jsonl`（pro 版，deepseek-v4-pro）、
`自动标注_flash\{dev,test}.auto.jsonl`（flash 版，deepseek-flash）、`{dev,test}.jsonl` 原文，
以及 `自动标注\提准\lint_命中_{pro,flash}.json`（可选；有就出逐规则对照表）。
**不调模型、不改任何产物**。

产出 `自动标注\提准\两版对照报告.md`：
1. 逐规则命中数对照（读 lint 命中清单；同一把尺子）；
2. 集合级对照（实体／事件／关系／times 条数、8 类事件分布、9 类关系分布、
   `event_time` 非空率、`quote` 逐字可定位率）；
3. 同条目逐字段一致率（实体＝类型＋规范化名字；事件＝`event_type`＋规范化 `event_name`；
   关系＝两端；`times`＝`value`）＋不一致明细；
4. 结论建议（**不替作者做最终裁定**）。

## 一致率口径（先声明，避免事后挑口径）
* 「严格一致条目」＝该字段的键集合两版**完全相同**；一致率＝严格一致条目 ÷ 共同条目数。
* 「平均 Jaccard」＝逐条目 `|交集|／|并集|` 的平均（两版都为空集的条目按 1 计）。
* 名字规范化＝`工具\标注助手.py` 的 `norm_ws`（只去空白）＋ `config.normalize_entity_name`
  （去空白＋剥最外层包裹字符），**不做**简繁折叠、不做模糊匹配。

用法：
```powershell
python 代码\抽取与图谱\auto_annotate_compare.py            # 写 自动标注\提准\两版对照报告.md
python 代码\抽取与图谱\auto_annotate_compare.py --stdout   # 只打印，不写盘
```
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib.util
import json
import os
import sys
from collections import Counter, OrderedDict

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402

ROOT = config.ROOT
HANDANN_PATH = os.path.join(ROOT, "工具", "标注助手.py")
EVAL_SUBDIR = "抽取评测集"
OUT_DIR_DEFAULT = os.path.join("自动标注", "提准")
REPORT_NAME = "两版对照报告.md"

VERSIONS = OrderedDict([
    ("pro", OrderedDict([("dirname", "自动标注"), ("model", "deepseek-v4-pro"),
                         ("prompt_version", "stage6-auto-annotate-v1.0"),
                         ("desc", "异模型对照（与抽取器不同模型）")])),
    ("flash", OrderedDict([("dirname", "自动标注_flash"), ("model", "deepseek-flash"),
                           ("prompt_version", "stage6-auto-annotate-v1.0-flash"),
                           ("desc", "与抽取器同模型（衡量同模型下的口径差距）")])),
])

NAME_FIELDS = OrderedDict([
    ("Company", ["company_name", "short_name"]),
    ("Person", ["person_name"]),
    ("Industry", ["industry_name"]),
    ("Institution", ["institution_name"]),
    ("Policy", ["policy_name"]),
])

EVENT_TYPES_ORDER = list(config.EVENT_TYPES)
RELATION_ORDER = list(config.RELATIONS)


def _load_module(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


handann = _load_module(HANDANN_PATH, "stage6_handann_compare")


def eval_dir() -> str:
    return os.path.join(config.DATASET_ROOT, EVAL_SUBDIR, config.DATASET_VERSION)


def version_dir(label: str) -> str:
    return os.path.join(eval_dir(), VERSIONS[label]["dirname"])


def out_dir() -> str:
    return os.path.join(eval_dir(), OUT_DIR_DEFAULT)


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def read_jsonl(path: str) -> list:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def norm_name(value) -> str:
    return config.normalize_entity_name(handann.norm_ws(str(value or "")))


def dicts(seq):
    return [x for x in (seq or []) if isinstance(x, dict)]


def load_version(label: str) -> dict:
    out = OrderedDict()
    for split in ("dev", "test"):
        path = os.path.join(version_dir(label), "%s.auto.jsonl" % split)
        if not os.path.isfile(path):
            continue
        for rec in read_jsonl(path):
            out[rec.get("item_id")] = rec
    return out


def load_truth() -> dict:
    truth = {}
    for split in ("dev", "test"):
        for rec in read_jsonl(os.path.join(eval_dir(), "%s.jsonl" % split)):
            truth[rec["item_id"]] = rec
    return truth


def entity_key(ent: dict, by_ref: dict) -> str:
    et = ent.get("entity_type")
    for field in NAME_FIELDS.get(et) or []:
        v = ent.get(field)
        if isinstance(v, str) and v.strip():
            return "%s|%s" % (et, norm_name(v))
    for v in (ent.get("aliases") or []):
        if isinstance(v, str) and v.strip():
            return "%s|%s" % (et, norm_name(v))
    return "%s|ref=%s" % (et, ent.get("entity_ref"))


def event_key(ev: dict) -> str:
    return "%s|%s" % (ev.get("event_type"), norm_name(ev.get("event_name")))


def time_key(t: dict) -> str:
    return str(t.get("value") or "")


def relation_key(rel: dict, by_ref: dict) -> str:
    def side(prefix):
        ent = by_ref.get(rel.get(prefix + "_ref"))
        if isinstance(ent, dict):
            return entity_key(ent, by_ref)
        return str(rel.get(prefix + "_label") or rel.get(prefix + "_ref") or "")
    return "%s|%s|%s" % (rel.get("relation"), side("from"), side("to"))


def key_sets(ann: dict) -> dict:
    ents = dicts(ann.get("entities"))
    by_ref = {e.get("entity_ref"): e for e in ents if isinstance(e.get("entity_ref"), str)}
    return OrderedDict([
        ("entities", Counter(entity_key(e, by_ref) for e in ents)),
        ("events", Counter(event_key(e) for e in dicts(ann.get("events")))),
        ("relations", Counter(relation_key(r, by_ref) for r in dicts(ann.get("relations")))),
        ("times", Counter(time_key(t) for t in dicts(ann.get("times")))),
    ])


def quote_objects(ann: dict) -> list:
    out = []
    for slot in ("entities", "events", "relations", "times", "ontology_boundary_log"):
        for x in dicts(ann.get(slot)):
            if isinstance(x.get("quote"), str) and x["quote"]:
                out.append((slot, x["quote"]))
    return out


def collection_stats(anns: dict, truth: dict) -> dict:
    st = {
        "items": 0, "entities": 0, "events": 0, "relations": 0, "times": 0,
        "event_time_nonempty": 0, "quotes": 0, "quotes_located": 0,
        "event_types": Counter(), "relation_types": Counter(),
    }
    for iid, rec in anns.items():
        ann = rec.get("annotation") or {}
        text = str((truth.get(iid) or {}).get("text") or "")
        st["items"] += 1
        st["entities"] += len(dicts(ann.get("entities")))
        events = dicts(ann.get("events"))
        st["events"] += len(events)
        st["event_types"].update(str(e.get("event_type")) for e in events)
        for e in events:
            if str(e.get("event_time") or "").strip():
                st["event_time_nonempty"] += 1
        rels = dicts(ann.get("relations"))
        st["relations"] += len(rels)
        st["relation_types"].update(str(r.get("relation")) for r in rels)
        st["times"] += len(dicts(ann.get("times")))
        for _slot, q in quote_objects(ann):
            st["quotes"] += 1
            if q in text:
                st["quotes_located"] += 1
    return st


def agreement(pro_anns: dict, flash_anns: dict) -> dict:
    res = OrderedDict()
    common = [iid for iid in pro_anns if iid in flash_anns]
    for slot in ("entities", "events", "relations", "times"):
        strict = 0
        jac_sum = 0.0
        diffs = []
        for iid in common:
            a = key_sets(pro_anns[iid].get("annotation") or {})[slot]
            b = key_sets(flash_anns[iid].get("annotation") or {})[slot]
            inter = sum((a & b).values())
            union = sum((a | b).values())
            if a == b:
                strict += 1
            jac_sum += 1.0 if union == 0 else inter / union
            if a != b:
                diffs.append((iid, sorted((a - b).elements()), sorted((b - a).elements())))
        n = len(common)
        res[slot] = OrderedDict([("items", n), ("strict", strict),
                                 ("strict_rate", strict / n if n else 0.0),
                                 ("mean_jaccard", jac_sum / n if n else 0.0),
                                 ("diffs", diffs)])
    return res


def _rate(a: int, b: int) -> str:
    return "%.1f%%（%d／%d）" % (100.0 * a / b, a, b) if b else "—（0／0）"


def _cleaner(a: int, b: int) -> str:
    if a < b:
        return "pro 更干净"
    if b < a:
        return "flash 更干净"
    return "两版相同"


def _load_lint(label: str) -> dict:
    path = os.path.join(out_dir(), "lint_命中_%s.json" % label)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def lint_split_readings(payload: dict, split: str) -> dict:
    """从命中清单里读某一 split 的读数：有硬命中的条目数、硬命中处数。"""
    if not payload:
        return {}
    items = hits = 0
    for _iid, res in (payload.get("items") or {}).items():
        if res.get("split") != split:
            continue
        n = sum(len(v) for v in (res.get("hard") or {}).values())
        hits += n
        items += 1 if n else 0
    return {"items_with_hard_hits": items, "hard_hits": hits}


def ledger_readings(label: str) -> dict:
    """读某一版的台账：per-split 与合计 usage_total（读不到就返回空）。"""
    path = os.path.join(version_dir(label), "自动标注台账.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        led = json.load(fh)
    rows = led.get("items") or []
    if not isinstance(rows, list):
        rows = list(rows.values())
    out = {"total": 0, "dev": 0, "test": 0, "n_total": 0, "n_dev": 0, "n_test": 0}
    for r in rows:
        n = int((r.get("usage") or {}).get("total_tokens") or 0)
        sp = r.get("split")
        out["total"] += n
        out["n_total"] += 1
        if sp in ("dev", "test"):
            out[sp] += n
            out["n_" + sp] += 1
    if not rows:
        out["total"] = int((led.get("counts") or {}).get("usage_total", {}).get("total_tokens") or 0)
    return out


def build_report(pro_anns, flash_anns, truth) -> str:
    pro_st = collection_stats(pro_anns, truth)
    fl_st = collection_stats(flash_anns, truth)
    agree = agreement(pro_anns, flash_anns)
    lp, lf = _load_lint("pro"), _load_lint("flash")
    L = []
    add = L.append
    add("# 两版自动标注对照报告（pro 版 vs flash 版，各 260 条）")
    add("")
    add("> 工具：`代码\\抽取与图谱\\auto_annotate_compare.py`（**离线**，不调模型、不改产物）。")
    add("> 两版都**不是**人工金标准、**都未**逐条人工复核；本报告只描述两个模型版本的口径差异，")
    add("> 不代表「哪一版是对的」。哪一版作第 10 阶段参照集**由作者裁定**。")
    add("> **作者裁定（2026-09-27）**：第 10 阶段参照集定为 flash 版经定向修复后的")
    add("> `自动标注\\提准\\{dev,test}.auto.repaired.jsonl`；pro 版＝异模型对照、flash 原版＝提准前对照，")
    add("> **三集合都保留、都不修改、都可重放**；三集合**都仍不是人工金标准**。")
    add("> 裁定原文与三集合读数见 `标注说明.md` 第 15.7 节、`16-事件抽取与知识图谱（第六阶段）.md`")
    add("> 第 8.9.1 节 与 `lint报告.md` 第零／一节。")
    add("")
    add("| 版本 | 目录 | 标注模型 | Prompt 版本 | 定位 |")
    add("| --- | --- | --- | --- | --- |")
    for label, anns in (("pro", pro_anns), ("flash", flash_anns)):
        add("| %s | `%s` | `%s` | `%s` | %s |"
            % (label, os.path.relpath(version_dir(label), ROOT), VERSIONS[label]["model"],
               VERSIONS[label]["prompt_version"], VERSIONS[label]["desc"]))
    add("")
    add("扫描范围：pro %d 条／flash %d 条（应为各 260 条＝dev 60＋test 200）。"
        % (len(pro_anns), len(flash_anns)))
    add("")
    add("## 一、逐规则命中数对照（同一把 lint 尺子）")
    add("")
    if lp and lf:
        hard_rules = [x[0] for x in lp["rules"]["hard"]]
        soft_rules = [x[0] for x in lp["rules"]["soft"]]
        add("| 规则 | 类型 | pro 命中处数／条目数 | flash 命中处数／条目数 | 哪一版更干净 |")
        add("| --- | --- | --- | --- | --- |")
        for rule in hard_rules + soft_rules:
            a, b = lp["counts"][rule], lf["counts"][rule]
            add("| `%s` | %s | %d／%d | %d／%d | %s |"
                % (rule, "硬" if rule in hard_rules else "软",
                   a["hits"], a["items"], b["hits"], b["items"], _cleaner(a["hits"], b["hits"])))
        hb = sum(lp["counts"][r]["hits"] for r in hard_rules)
        ha = sum(lf["counts"][r]["hits"] for r in hard_rules)
        sb = sum(lp["counts"][r]["hits"] for r in soft_rules)
        sa = sum(lf["counts"][r]["hits"] for r in soft_rules)
        add("")
        add("合计：**硬命中** pro %d 处（%d 条有命中）／flash %d 处（%d 条有命中）→ %s；"
            "**软提示** pro %d 处／flash %d 处。"
            % (hb, lp["items_with_hard_hits"], ha, lf["items_with_hard_hits"], _cleaner(hb, ha), sb, sa))
        add("")
        add("> 逐条命中（含每规则例子与 R7a 两层判定依据）见 `lint报告.md`；"
            "R2 的简繁书写面登记也见该报告「一之三」。")
    else:
        add("* 缺少 lint 命中清单（`lint_命中_pro.json`／`lint_命中_flash.json`），"
            "先跑 `auto_annotate_lint.py lint --version all`。")
    add("")
    add("## 二、集合级对照")
    add("")
    add("### 2.1 规模")
    add("")
    add("| 项 | pro | flash | flash − pro |")
    add("| --- | --- | --- | --- |")
    for key, title in (("entities", "实体"), ("events", "事件"), ("relations", "关系"), ("times", "times")):
        add("| %s 条数 | %d | %d | %+d |" % (title, pro_st[key], fl_st[key], fl_st[key] - pro_st[key]))
    add("")
    add("### 2.2 事件类型分布（8 类）")
    add("")
    add("| event_type | pro | flash | flash − pro |")
    add("| --- | --- | --- | --- |")
    for et in EVENT_TYPES_ORDER:
        a, b = pro_st["event_types"].get(et, 0), fl_st["event_types"].get(et, 0)
        add("| %s | %d | %d | %+d |" % (et, a, b, b - a))
    add("")
    add("### 2.3 关系分布（9 类）")
    add("")
    add("| relation | pro | flash | flash − pro |")
    add("| --- | --- | --- | --- |")
    for rel in RELATION_ORDER:
        a, b = pro_st["relation_types"].get(rel, 0), fl_st["relation_types"].get(rel, 0)
        add("| `%s` | %d | %d | %+d |" % (rel, a, b, b - a))
    add("")
    add("### 2.4 时间与 quote 可定位率")
    add("")
    add("| 指标 | pro | flash |")
    add("| --- | --- | --- |")
    add("| `event_time` 非空率 | %s | %s |"
        % (_rate(pro_st["event_time_nonempty"], pro_st["events"]),
           _rate(fl_st["event_time_nonempty"], fl_st["events"])))
    add("| `quote` 逐字可定位率（quote ⊂ 本块 text） | %s | %s |"
        % (_rate(pro_st["quotes_located"], pro_st["quotes"]),
           _rate(fl_st["quotes_located"], fl_st["quotes"])))
    add("")
    add("## 三、两版同条目逐字段一致率")
    add("")
    add("标题口径：实体＝`entity_type`＋规范化名字（名字取该类型的名字键，缺则取别名／ref）；"
        "事件＝`event_type`＋规范化 `event_name`；关系＝`relation`＋两端（端点按 `*_ref` 解到实体，"
        "解不到则退回 label）；`times`＝`value`。名字规范化只去空白与最外层包裹字符，不做简繁折叠。")
    add("")
    add("| 字段 | 共同条目 | 严格一致条目 | 严格一致率 | 平均 Jaccard |")
    add("| --- | --- | --- | --- | --- |")
    for slot, title in (("entities", "实体"), ("events", "事件"),
                        ("relations", "关系"), ("times", "times")):
        a = agree[slot]
        add("| %s | %d | %d | %.1f%% | %.3f |"
            % (title, a["items"], a["strict"], 100.0 * a["strict_rate"], a["mean_jaccard"]))
    add("")
    add("### 3.1 不一致明细（每字段取差异最大的若干条）")
    add("")
    shown = 0
    for slot, title in (("entities", "实体"), ("events", "事件"),
                        ("relations", "关系"), ("times", "times")):
        diffs = sorted(agree[slot]["diffs"],
                       key=lambda x: -(len(x[1]) + len(x[2])))
        add("#### %s（不一致 %d 条）" % (title, len(diffs)))
        add("")
        if not diffs:
            add("* 无不一致。")
            add("")
            continue
        add("| item_id | 只 pro 有 | 只 flash 有 |")
        add("| --- | --- | --- |")
        for iid, only_pro, only_flash in diffs[:12]:
            add("| `%s` | %s | %s |"
                % (iid, "；".join(only_pro)[:400] or "（无）",
                   "；".join(only_flash)[:400] or "（无）"))
            shown += 1
        add("")
    add("（明细共 %d 行。）" % shown)
    add("")
    add("## 四、结论与建议（**不替作者做最终裁定**）")
    add("")
    add("1. **同一把 lint 尺子下**：见第一节的逐规则读数——谁更干净按表读，不做加权、不做合并总分。")
    add("2. **集合级**：全量 260 上 flash 产出更多**事件／关系／times**（实体反而少 22 条，见 2.1），"
        "但「多」不等于「对」——两版都未人工复核，无法用条数判优劣。")
    add("3. **逐字段一致率**：见第三节。一致率低说明两版口径差异大，"
        "并不说明哪一版错；一致的部分也不能当成「已互证」（两个模型同源误差可能同向）。")
    lr_pro, lr_fl = lint_split_readings(lp, "dev"), lint_split_readings(lf, "dev")
    led_pro, led_fl = ledger_readings("pro"), ledger_readings("flash")
    add("4. **作者在同一批 dev 60 上的独立实测（必须与本节一并阅读）**：")
    add("   * 作者自己的尺度量出：pro **7 条**／flash **6 条**命中硬规则（条目数）；")
    add("   * flash 产出更多：实体 **151 vs 137**、关系 **137 vs 115**；")
    add("   * 而 flash 的 dev 60 token **811,158 > pro 的 774,572**。")
    add("   * 结论事实：**换 flash 不更便宜、也不明显更准**；它的价值在于**与抽取器同模型**"
        "（衡量同模型下的口径差距），pro 版是**异模型**对照。")
    add("")
    add("   **上面这条是 dev 60 上的事实；本报告另外给出全量 260 与本工具 lint 尺度的读数**"
        "（两者不要混读）：")
    add("")
    add("   | 读数 | pro | flash | 说明 |")
    add("   | --- | --- | --- | --- |")
    add("   | 作者独立尺度：dev 60 硬规则命中条目 | 7 | 6 | 作者提供，本文工具复算不出这个数（尺子不同） |")
    add("   | 本工具 lint：dev 60 有硬命中的条目 | %s | %s | 规则 v1.2（10 硬＋5 软；R3 已降级为软） |"
        % (lr_pro.get("items_with_hard_hits", "—"), lr_fl.get("items_with_hard_hits", "—")))
    add("   | 本工具 lint：dev 60 硬命中处数 | %s | %s | 同上 |"
        % (lr_pro.get("hard_hits", "—"), lr_fl.get("hard_hits", "—")))
    add("   | dev 60 token（台账逐条求和） | %s | %s | 与作者数字一致即互证 |"
        % (("{:,}".format(led_pro.get("dev", 0)) if led_pro else "—"),
           ("{:,}".format(led_fl.get("dev", 0)) if led_fl else "—")))
    add("   | **全量 260 token**（台账逐条求和） | %s | %s | flash 仍然**更贵**（+%.1f%%） |"
        % (("{:,}".format(led_pro.get("total", 0)) if led_pro else "—"),
           ("{:,}".format(led_fl.get("total", 0)) if led_fl else "—"),
           100.0 * (led_fl.get("total", 0) - led_pro.get("total", 0)) / led_pro["total"]
           if led_pro.get("total") and led_fl.get("total") else 0.0))
    add("   | 全量 260 实体／关系条数 | %d／%d | %d／%d | **实体条数的方向在 260 条上翻过来了**"
        "（dev 60 上 flash 更多，260 条上 pro 更多） |"
        % (pro_st["entities"], pro_st["relations"], fl_st["entities"], fl_st["relations"]))
    add("")
    add("   ⇒ 引用「flash 产出更多」时必须带 **dev 60** 这个范围限定；全量 260 上"
        "flash 更多的是**事件／关系／times**，实体反而比 pro 少（631 vs 653）。")
    add("5. **两版都留怎么分工（建议，供裁定）**：")
    add("   * 若第 10 阶段要衡量「抽取器在自家模型口径下的表现」，flash 版是**同模型参照**；"
        "pro 版留作**异模型对照**（同源自证风险更低，但风格差异更大）。")
    add("   * 两版都可以留作**互补的人工复核队列**：先看两版一致的条目（分歧最小的部分），"
        "再重点审两版不一致的条目；这比先挑一版当权威更省人工。")
    add("   * 若要指定唯一参照集，建议按作者自己的硬规则尺度在同一 60 条 dev 上的读数 + 人工抽检决定；"
        "本报告与 `lint报告.md` 只提供读数，**不替代裁定**。")
    add("   * **作者已裁定（2026-09-27）**：第 10 阶段参照集＝flash 版经定向修复后的 "
        "`自动标注\\提准\\{dev,test}.auto.repaired.jsonl`；pro 版与 flash 原版保留为对照，三者都不修改、"
        "都可重放，且**都不是人工金标准**（引用纪律见《标注说明》15.7 与《16》8.9.1）。")
    add("")
    add("---")
    add("")
    add("生成时间：%s｜工具：`代码\\抽取与图谱\\auto_annotate_compare.py`（离线）" % now_iso())
    add("")
    return "\n".join(L)


def build_parser():
    p = argparse.ArgumentParser(
        prog="auto_annotate_compare.py",
        description="两版自动标注（pro vs flash）的离线对照报告，不调模型、不改产物。")
    p.add_argument("--out", default=None, help="报告落点（默认 %s）" % os.path.join(OUT_DIR_DEFAULT, REPORT_NAME))
    p.add_argument("--stdout", action="store_true", help="只打印，不写盘")
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
    truth = load_truth()
    pro_anns, flash_anns = load_version("pro"), load_version("flash")
    if not pro_anns or not flash_anns:
        raise SystemExit("缺少某一版产物：pro %d 条／flash %d 条" % (len(pro_anns), len(flash_anns)))
    report = build_report(pro_anns, flash_anns, truth)
    if args.stdout:
        print(report)
        return 0
    path = args.out or os.path.join(out_dir(), REPORT_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handann.write_text_atomic(path, report)
    print("两版对照报告：%s（pro %d 条／flash %d 条）" % (path, len(pro_anns), len(flash_anns)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
