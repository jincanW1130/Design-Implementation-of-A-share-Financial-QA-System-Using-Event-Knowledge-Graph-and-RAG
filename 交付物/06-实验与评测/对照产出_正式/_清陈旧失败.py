# -*- coding: utf-8 -*-
r"""清理陈旧失败留痕。

背景：`跑正式对照.py` 的 `run_one()` 在调用前只清"桥接记录"（`_clear_bridge`），
**不清 `error_contract.json`**。于是「先失败、后重跑成功」的题目目录里会同时存在
有效的 `qa_records.jsonl` 与一份**陈旧的失败契约**——产物自相矛盾，读者无法判断该题
到底成没成。

本脚本**只删**满足「同目录下 `qa_records.jsonl` 存在且非空」的 `error_contract.json`
（即"该题最终是成功的，那份失败留痕是历史"）。**绝不删**没有有效答案的目录里的失败契约
（那是真实的终局失败，必须留档）。

删除清单逐条落 `_陈旧失败留痕清理台账.json`（含删除前的错误码与 reason），可审计、可回溯。
"""
import io
import json
import os

ROOT = r"C:\Users\15129\Desktop\毕业设计"
OUT = os.path.join(ROOT, "交付物/06-实验与评测", "对照产出_正式")
GROUPS = ["A", "B", "C", "D", "E", "B1"]
LEDGER = os.path.join(OUT, "_陈旧失败留痕清理台账.json")


def main():
    removed, kept = [], []
    for g in GROUPS:
        gd = os.path.join(OUT, "逐题", g)
        if not os.path.isdir(gd):
            continue
        for q in sorted(os.listdir(gd)):
            sub = os.path.join(gd, q)
            err = os.path.join(sub, "error_contract.json")
            qa = os.path.join(sub, "qa_records.jsonl")
            if not os.path.isfile(err):
                continue
            has_answer = os.path.isfile(qa) and os.path.getsize(qa) > 0
            try:
                payload = json.load(io.open(err, encoding="utf-8"))
            except Exception:                                   # noqa: BLE001
                payload = {}
            if has_answer:
                os.remove(err)
                removed.append({"group": g, "qid": q,
                                "stale_error_code": payload.get("error_code"),
                                "stale_reason": payload.get("reason"),
                                "kept_because": "同目录 qa_records.jsonl 有效"})
            else:
                kept.append({"group": g, "qid": q,
                             "error_code": payload.get("error_code"),
                             "reason": payload.get("reason"),
                             "failed_qids_extra": payload.get("extra")})

    io.open(LEDGER, "w", encoding="utf-8", newline="\n").write(
        json.dumps({
            "schema": "stage10-stale-error-contract-cleanup-1.0",
            "note": ("仅删除「同目录 qa_records.jsonl 有效」的陈旧失败契约；"
                     "无有效答案的失败契约一律保留（那是真实终局失败）。"),
            "script": "交付物/06-实验与评测/对照产出_正式/_清陈旧失败.py",
            "removed_count": len(removed), "removed": removed,
            "kept_count": len(kept), "kept": kept,
        }, ensure_ascii=False, indent=2) + "\n")

    print("删除（陈旧）：%d 条" % len(removed))
    print("保留（真实终局失败）：%d 条" % len(kept))
    for row in kept:
        print("  %-3s %-9s code=%s reason=%s"
              % (row["group"], row["qid"], row["error_code"], row["reason"]))
    print("台账：%s" % os.path.relpath(LEDGER, ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
