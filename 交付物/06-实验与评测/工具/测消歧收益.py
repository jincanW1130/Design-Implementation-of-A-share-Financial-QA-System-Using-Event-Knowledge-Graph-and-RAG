# -*- coding: utf-8 -*-
"""A 步（精度无损的别名／归一化扩展）收益测量 —— 只读、不落图谱产物。

## 背景

路线 ③ 的量化结论：**多公司共同参与事件的瓶颈不在语料，在实体消歧**——
抽取层（`extracted.jsonl`，不做名单过滤）有 **309** 个事件含 ≥2 个公司参与方，
而现行图谱导出物（v1.2）里只有 **16** 个；抽取层 `PARTICIPATES_IN` 边 1917 条，
图谱里只有 1252 条，**665 条因端点未消歧被丢**。

本项目自己登记过一处典型失败（《16》第4.5节）：公司 **603501 豪威集成电路** 的注册全称
在配置里是**半角括号** `豪威集成电路(集团)股份有限公司`，而语料里 7 处提及是**全角括号**
`豪威集成电路（集团）股份有限公司`（另有 1 处繁体），于是该公司的提及**全部留在待消歧**。
根因是 `config.normalize_entity_name()` 只做「去空白 ＋ 剥最外层包裹字符」，
**不做宽度折叠、也不做简繁折叠**（该函数 docstring 明写这是有意的口径）。

## 本脚本做什么

对同一份抽取产物，用**两个归一化口径**各跑一遍真实的 `disambiguate.disambiguate_records()`，
对比消歧收益：

* `baseline`：现行 `config.normalize_entity_name`（去空白 ＋ 剥壳）
* `variant` ：在 baseline 的结果之上再叠 `auto_annotate_lint.fold_simp()`
  （`NFKC` 全角→半角 ＋ 常用简繁／异体**单字**折叠）——**复用项目既有的、作者已裁定过的折叠表**，
  不另造轮子。该表在 `auto_annotate_lint.py` 里就地维护，并明确排除了多义映射
  （後→后、臺→台、覆→复 之类一律不进表），故属**精度无损的规范化**。

**只读保证**：不写任何图谱产物、不改任何冻结文件；`disambiguate_records()` 是纯函数。

## 用法

    python "交付物/06-实验与评测\\工具\\测消歧收益.py"
    python "交付物/06-实验与评测\\工具\\测消歧收益.py" --show-samples
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import unicodedata

CODE_RE = re.compile(r"^Company:\d{6}$")
"""「已命中配置公司」的身份键形态（以 stock_code 为锚，《10》第4.5.4节）。"""

# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\工具\` 整体移到
# `交付物/06-实验与评测\工具\`（**下移一层**），求 ROOT 的上溯次数 3 → 4。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
G = os.path.join(ROOT, "交付物/03-代码", "抽取与图谱")
# **导入顺序有讲究**：`交付物/03-代码\数据准备\config.py` 与 `交付物/03-代码\抽取与图谱\config.py` **同名**，
# 后插者排在前、胜出。本脚本要的是**抽取与图谱**那一份（它才有 `normalize_entity_name`），
# 故先插数据准备、再插抽取与图谱。（这正是 `交付物/03-代码\问答\run_answer.py` 开头记载的路径解析陷阱。）
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "数据准备"))
sys.path.insert(0, G)

EXTRACT = os.path.join(G, "_全量", "v2.1_v1_2", "extracted.jsonl")
OUT_DIR = os.path.join(ROOT, "交付物/06-实验与评测", "消歧扩样")


def log(msg: str) -> None:
    print(msg, flush=True)


def load_records() -> list:
    rows = []
    with open(EXTRACT, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def make_variant_normalizer(base):
    """baseline 之上叠 fold_simp（NFKC ＋ 简繁／异体单字折叠）。

    顺序：先跑**原口径**（去空白＋剥壳），再折叠——这样既不改动既有规则的语义，
    又保证「书写面」与「提及」两侧走同一条管道（比对才一致）。

    **2026-10-02**：折叠表已由 `auto_annotate_lint.py` 迁到**无对外依赖**的同目录模块
    `fold_variants.py`（原模块跨目录 `import 工具\\标注结构校验.py`，会让只想要折叠表的调用方
    被连带拖进 `工具\\`，第 6 阶段门禁的镜像不复制 `工具\\`、镜像内因此导入失败）。
    本函数随之改指新模块。
    """
    import fold_variants as fv

    def norm(name):
        return fv.fold_simp(base(name))

    return norm


def company_metrics(records: list) -> dict:
    """公司提及的消歧口径统计（与《16》第8.4节 同口径：按实体提及计）。"""
    total = resolved = 0
    by_doc = collections.defaultdict(int)
    for r in records:
        for e in r.get("entities") or []:
            if e.get("type") != "Company":
                continue
            total += 1
            by_doc[int(r["doc_id"])] += 1
    return {"company_mentions": total, "docs_with_company_mention": len(by_doc)}


def run_once(records: list, alias_table: dict, label: str) -> dict:
    import disambiguate as dis

    entity_map, unresolved, companies_seen = dis.disambiguate_records(records, alias_table)
    # `identity_key` 形如 `Company:601633`（**以 stock_code 为锚**，《10》第4.5.4节）。
    # 只有 6 位数字代码才算**命中配置公司**；`Company:<归一化名>` 是自成一体的其它主体。
    resolved_company_mentions = 0
    company_identities, other_identities = set(), set()
    for info in (entity_map or {}).values():
        if not isinstance(info, dict) or info.get("label") != "Company":
            continue
        ik = str(info.get("identity_key") or "")
        if CODE_RE.match(ik):
            resolved_company_mentions += 1
            company_identities.add(ik)
        else:
            other_identities.add(ik)
    return {
        "label": label,
        "entity_map_size": len(entity_map or {}),
        "unresolved_mentions": len(unresolved or []),
        "resolved_company_mentions": resolved_company_mentions,
        "company_identity_nodes_configured": len(company_identities),
        "company_identity_nodes_other": len(other_identities),
        "_entity_map": entity_map,
        "_unresolved": unresolved,
    }


def identity_index(entity_map: dict, unresolved: list) -> dict:
    """把 `entity_map` 与 `unresolved` 合成一张 `local_id → 身份键` 的表。

    **关键**：未消歧的提及**不在 `entity_map` 里**，它们只出现在 `unresolved` 列表里
    （实测：entity_map 3293 条＝已消歧条目；unresolved 1070 条＝待消歧提及）。
    所以「放宽入图策略」（B 步）的收益**必须**从 unresolved 侧去量，否则会得到
    「B 与 A 一样、收益为 0」的假读数。
    """
    idx = {}
    for local_id, info in (entity_map or {}).items():
        if isinstance(info, dict):
            idx[str(local_id)] = str(info.get("identity_key") or "")
    for item in unresolved or []:
        if not isinstance(item, dict):
            continue
        eid = str(item.get("entity_id") or "")
        if not eid:
            continue
        label = str(item.get("label") or "")
        name = str(item.get("normalized_name") or item.get("name") or "")
        idx[eid] = "%s:%s" % (label, name)
    return idx


def multi_company_events(records: list, idx: dict, require_configured: bool = True) -> dict:
    """按已消歧结果统计「含 ≥2 个公司参与方」的事件数（与图谱写入同口径）。

    `require_configured=True`（A 步口径）只认 `Company:<6位代码>`——两端都要落到
    105 家配置公司上，与 `write_graph.py` 的「端点未消歧 → 跳过」是同一把尺子。
    `False`（B 步探测口径）**接受任何 Company 身份**（含名单外主体，身份键为归一化名），
    用来量化「放宽入图策略」能换来多少多公司事件。
    """
    ev_comp = collections.defaultdict(set)
    for r in records:
        doc_id = int(r["doc_id"])
        for rel in r.get("relations") or []:
            if rel.get("relation") != "PARTICIPATES_IN":
                continue
            head, tail = rel.get("head_id"), rel.get("tail_id")
            for pid, ptype, other in ((head, rel.get("head_type"), tail),
                                      (tail, rel.get("tail_type"), head)):
                if ptype != "Company" or not pid:
                    continue
                ik = idx.get(str(pid)) or ""
                if not ik.startswith("Company:"):
                    continue
                if require_configured and not CODE_RE.match(ik):
                    continue
                ev_comp[(doc_id, str(other))].add(ik)
    multi = {k: v for k, v in ev_comp.items() if len(v) >= 2}
    dist = collections.Counter(len(v) for v in multi.values())
    return {"events_with_ge2_companies": len(multi),
            "participant_count_dist": dict(sorted(dist.items())),
            "_sample": sorted(multi)[:5]}


def main() -> int:
    ap = argparse.ArgumentParser(description="A 步消歧收益测量（只读）")
    ap.add_argument("--show-samples", action="store_true")
    args = ap.parse_args()

    import config
    import disambiguate as dis

    records = load_records()
    log("=" * 78)
    log("A 步 · 消歧归一化扩展收益测量（只读，不落图谱产物）")
    log("=" * 78)
    log("抽取产物：%s（%d 个文档块）" % (os.path.relpath(EXTRACT, ROOT), len(records)))
    log("公司提及口径：%s" % json.dumps(company_metrics(records), ensure_ascii=False))
    log("")

    base_norm = config.normalize_entity_name
    results = {}
    for label, normalizer in (("baseline", base_norm), ("variant", make_variant_normalizer(base_norm))):
        config.normalize_entity_name = normalizer
        dis.config.normalize_entity_name = normalizer      # disambiguate 里是 `config.xxx` 调用，同一模块对象
        alias_table = dis.build_alias_table()
        res = run_once(records, alias_table, label)
        res["alias_surfaces"] = sum(len(v.get("normalized_alias_surfaces") or [])
                                    for v in alias_table.values())
        idx = identity_index(res["_entity_map"], res["_unresolved"])
        res["multi"] = multi_company_events(records, idx, require_configured=True)
        # B 步探测：放宽入图策略（接受名单外主体为 Company 节点）能换来多少多公司事件
        res["multi_B"] = multi_company_events(records, idx, require_configured=False)
        results[label] = res
        log("[%s] 实体条目=%d 待消歧提及=%d 命中配置公司提及=%d 公司身份节点=%d"
            % (label, res["entity_map_size"], res["unresolved_mentions"],
               res["resolved_company_mentions"], res["company_identity_nodes_configured"]))
        log("        A 口径（只认 105 家）含≥2公司事件=%d %s"
            % (res["multi"]["events_with_ge2_companies"],
               json.dumps(res["multi"]["participant_count_dist"], ensure_ascii=False)))
        log("        B 探测（接受名单外主体）含≥2公司事件=%d %s"
            % (res["multi_B"]["events_with_ge2_companies"],
               json.dumps(res["multi_B"]["participant_count_dist"], ensure_ascii=False)))
    config.normalize_entity_name = base_norm
    dis.config.normalize_entity_name = base_norm

    b, v = results["baseline"], results["variant"]
    log("")
    log("-" * 78)
    log("对照（variant − baseline）")
    log("-" * 78)
    log("  实体条目          %6d → %6d  (%+d)" % (b["entity_map_size"], v["entity_map_size"],
                                                v["entity_map_size"] - b["entity_map_size"]))
    log("  待消歧提及        %6d → %6d  (%+d)" % (b["unresolved_mentions"], v["unresolved_mentions"],
                                                v["unresolved_mentions"] - b["unresolved_mentions"]))
    log("  命中配置公司提及  %6d → %6d  (%+d)" % (
        b["resolved_company_mentions"], v["resolved_company_mentions"],
        v["resolved_company_mentions"] - b["resolved_company_mentions"]))
    log("  公司身份节点      %6d → %6d  (%+d)" % (
        b["company_identity_nodes_configured"], v["company_identity_nodes_configured"],
        v["company_identity_nodes_configured"] - b["company_identity_nodes_configured"]))
    log("  A 口径 含≥2公司事件 %6d → %6d  (%+d)" % (
        b["multi"]["events_with_ge2_companies"], v["multi"]["events_with_ge2_companies"],
        v["multi"]["events_with_ge2_companies"] - b["multi"]["events_with_ge2_companies"]))
    log("  B 探测 含≥2公司事件 %6d → %6d  (%+d)   ← 放宽入图后（识别名单外主体）"
        % (b["multi_B"]["events_with_ge2_companies"], v["multi_B"]["events_with_ge2_companies"],
           v["multi_B"]["events_with_ge2_companies"] - b["multi_B"]["events_with_ge2_companies"]))

    if args.show_samples:
        regressions = set()
        for code, info in (v["_entity_map"] or {}).items():
            if code not in (b["_entity_map"] or {}):
                regressions.add(code)
        log("\n  variant 新增的实体身份数 = %d" % len(regressions))

    os.makedirs(OUT_DIR, exist_ok=True)
    payload = {k: {kk: vv for kk, vv in val.items() if not kk.startswith("_")}
               for k, val in results.items()}
    with open(os.path.join(OUT_DIR, "消歧收益.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
    log("\n已写：%s" % os.path.relpath(os.path.join(OUT_DIR, "消歧收益.json"), ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
