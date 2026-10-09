# -*- coding: utf-8 -*-
"""C 组修复·等价性自证（a）：`pipeline.py` 自有 CLI 复跑预实验集 C 组 vs 冻结 trace。

用法：
    python "交付物/06-实验与评测\\对照产出_正式\\_等价性自证_C组.py" <新trace> <冻结trace> <输出JSON>

判据（**先定判据、再看读数**，不改判据）：
  1. 题号集合必须逐题对齐（30／30，且顺序一致）；
  2. 逐题 **`final_evidence_chunk_ids`（呈现顺序，含次序）必须逐位相同**——这是 C 组
     "读到哪 10 条证据"的唯一口径；
  3. 顶层字段（除登记为"允许不同"的键之外）逐字段深比较，统计逐字段一致率；
  4. 允许不同的键**先声明后核对**：本脚本不预设，改为**实测列出所有不同的字段**，
     人工据读数判定（不许把"不同"事后说成"允许"）。
"""

import io
import json
import os
import sys


def load(path):
    rows = []
    with io.open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def first_diff(old, new, path="$"):
    """返回第一处不同的路径与两侧取值（深比较；类型不同即不同）。"""
    if type(old) is not type(new) and not (isinstance(old, (int, float))
                                           and isinstance(new, (int, float))):
        return path, old, new
    if isinstance(old, dict):
        keys = sorted(set(old) | set(new))
        for key in keys:
            if key not in old:
                return "%s.%s" % (path, key), "<缺失>", new[key]
            if key not in new:
                return "%s.%s" % (path, key), old[key], "<缺失>"
            got = first_diff(old[key], new[key], "%s.%s" % (path, key))
            if got:
                return got
        return None
    if isinstance(old, list):
        if len(old) != len(new):
            return path + ".长度", len(old), len(new)
        for idx, (a, b) in enumerate(zip(old, new)):
            got = first_diff(a, b, "%s[%d]" % (path, idx))
            if got:
                return got
        return None
    if old != new:
        return path, old, new
    return None


def main(argv):
    if len(argv) != 4:
        raise SystemExit(__doc__)
    new_rows, old_rows = load(argv[1]), load(argv[2])
    report = {
        "schema": "stage10-c-trace-equivalence-1.0",
        "new_trace": os.path.abspath(argv[1]),
        "frozen_trace": os.path.abspath(argv[2]),
        "new_rows": len(new_rows),
        "frozen_rows": len(old_rows),
        "new_schema": sorted({r.get("schema") for r in new_rows}),
        "frozen_schema": sorted({r.get("schema") for r in old_rows}),
        "new_key_count": sorted({len(r) for r in new_rows}),
        "frozen_key_count": sorted({len(r) for r in old_rows}),
    }
    by_old = {r["qid"]: r for r in old_rows}
    by_new = {r["qid"]: r for r in new_rows}
    report["qid_order_identical"] = [r["qid"] for r in new_rows] == [r["qid"] for r in old_rows]
    report["qid_sets_identical"] = sorted(by_old) == sorted(by_new)

    per_question, field_stats = [], {}
    evidence_same, evidence_set_same, fully_identical = 0, 0, 0
    for qid in [r["qid"] for r in old_rows]:
        old, new = by_old[qid], by_new.get(qid)
        row = {"qid": qid}
        if new is None:
            row["missing_in_new"] = True
            per_question.append(row)
            continue
        ev_old = list(old.get("final_evidence_chunk_ids") or [])
        ev_new = list(new.get("final_evidence_chunk_ids") or [])
        row["evidence_order_identical"] = ev_old == ev_new
        row["evidence_set_identical"] = sorted(ev_old) == sorted(ev_new)
        row["evidence_len_old"] = len(ev_old)
        row["evidence_len_new"] = len(ev_new)
        if row["evidence_order_identical"]:
            evidence_same += 1
        if row["evidence_set_identical"]:
            evidence_set_same += 1
        diff_fields, diffs = [], {}
        for key in sorted(set(old) | set(new)):
            got = first_diff(old.get(key, "<缺失>"), new.get(key, "<缺失>"), key)
            field_stats.setdefault(key, {"same": 0, "diff": 0})
            if got:
                field_stats[key]["diff"] += 1
                diff_fields.append(key)
                diffs[key] = {"path": got[0], "frozen": got[1], "new": got[2]}
            else:
                field_stats[key]["same"] += 1
        row["differing_fields"] = diff_fields
        row["diffs"] = diffs
        if not diff_fields:
            fully_identical += 1
        per_question.append(row)

    report["per_question"] = per_question
    report["field_stats"] = field_stats
    report["summary"] = {
        "questions": len(per_question),
        "evidence_order_identical": evidence_same,
        "evidence_order_identical_rate": round(evidence_same / float(len(per_question)), 4),
        "evidence_set_identical": evidence_set_same,
        "rows_identical_on_all_fields": fully_identical,
    }
    with io.open(argv[3], "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True))
    print(json.dumps(report["summary"], ensure_ascii=False))
    print("字段级：")
    for key in sorted(field_stats):
        stat = field_stats[key]
        print("  %-28s 同 %2d / 异 %2d" % (key, stat["same"], stat["diff"]))
    print("逐题差异字段：")
    for row in per_question:
        if row.get("missing_in_new"):
            print("  %s  **新 trace 缺本题**" % row["qid"])
        elif row["differing_fields"]:
            print("  %s  异：%s" % (row["qid"], "、".join(row["differing_fields"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
