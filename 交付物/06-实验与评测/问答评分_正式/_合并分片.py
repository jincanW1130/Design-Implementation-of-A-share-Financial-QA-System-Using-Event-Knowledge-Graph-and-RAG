# -*- coding: utf-8 -*-
r"""把并行分片 B 的缓存与台账**合并**回主目录，供 `--adjudicate` / `--report` 使用。

为什么需要合并：`--report` 只从**一个**输出目录的缓存重出记录，分片各写各的目录，
不合并就只看到一半读数。

**合并规则（按分片归属取权威值，不按"先到先得"）**：
- 分片前那次**串行**运行是按题号顺序跑的，它越过 FQ-072 分界线，在**主目录**里对约
  20 条属于 B 片的答案留下了格子；而 `kimi-k3` 的 `temperature` 实测为 1.0（端点拒收 0），
  **同一格两次评分不保证相同**。因此对「B 片范围内的 answer_key」一律用 **B 目录**的格子
  覆盖主目录的同名文件——保证每条答案的分数来自**它所属分片**的那一次运行。
- A 片范围内的 answer_key 一律保留主目录原值（B 目录本来也没有它们）。
- 台账：两个进程的尝试记录互不重叠，按 (timestamp, judge, answer_key, dimension, attempt) 排序后
  取并集；totals 由并集**重算**，不沿用任一侧的自报值。
- **不含凭据**：台账本来就不记 key 取值，合并脚本也不读任何 key。

只读两个分片目录，只写主目录；不触碰任何答案产物。
"""
import io
import json
import os
import shutil

ROOT = r"C:\Users\15129\Desktop\毕业设计"
S = os.path.join(ROOT, "交付物/06-实验与评测")
MAIN = os.path.join(S, "问答评分_正式")
SHARD = os.path.join(S, "问答评分_正式_B")
SHARD_B_QIDS = os.path.join(MAIN, "_分片_B_qids.txt")


def main():
    b_qids = {q.strip() for q in io.open(SHARD_B_QIDS, encoding="utf-8").read().split(",") if q.strip()}
    print("B 片题号数 =", len(b_qids))

    # 1) 用模块 API 拿 answer_key -> qid 的权威映射（与评分脚本同一份装配逻辑）
    import importlib.util
    spec = importlib.util.spec_from_file_location("sc", os.path.join(S, "工具", "评分脚本.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.apply_dataset("formal")
    items = m.load_all_answers(m.load_questions())
    key2qid = {it["answer_key"]: it["qid"] for it in items}
    b_keys = {k for k, q in key2qid.items() if q in b_qids}
    print("B 片 answer_key 数 =", len(b_keys))

    # 2) 拷贝 B 的缓存：只覆盖 B 片范围内的格子
    copied = kept = 0
    for judge in ("kimi", "zhipu"):
        src_root = os.path.join(SHARD, "_judge原始返回", judge)
        dst_root = os.path.join(MAIN, "_judge原始返回", judge)
        if not os.path.isdir(src_root):
            continue
        for dp, dn, fn in os.walk(src_root):
            for f in fn:
                if not f.endswith(".json"):
                    continue
                rel = os.path.relpath(os.path.join(dp, f), src_root)
                key = f.split("__")[0] + "__" + f.split("__")[1] if "__" in f else ""
                dst = os.path.join(dst_root, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if f.startswith("_") or key in b_keys:      # 探针文件与 B 片格子：一律以 B 为准
                    shutil.copy2(os.path.join(dp, f), dst)
                    copied += 1
                else:
                    kept += 1
    print("缓存：以 B 片为准覆盖 %d 个；未覆盖 %d 个（不属于 B 片范围）" % (copied, kept))

    # 3) 台账并集 + 重算 totals
    def load(p):
        return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else {}

    la, lb = load(os.path.join(MAIN, "调用台账.json")), load(os.path.join(SHARD, "调用台账.json"))
    calls = (la.get("calls") or []) + (lb.get("calls") or [])
    seen, uniq = set(), []
    for c in calls:
        sig = (c.get("timestamp"), c.get("judge"), c.get("answer_key"),
               c.get("dimension"), c.get("attempt"))
        if sig in seen:
            continue
        seen.add(sig)
        uniq.append(c)
    uniq.sort(key=lambda c: (str(c.get("timestamp")), str(c.get("judge")),
                             str(c.get("answer_key")), str(c.get("dimension")),
                             str(c.get("attempt"))))
    totals = {
        "attempts": len(uniq),
        "ok": sum(1 for c in uniq if c.get("ok")),
        "failed": sum(1 for c in uniq if not c.get("ok")),
        "retries": sum(1 for c in uniq if str(c.get("attempt")) not in ("1", "1.0")),
        "prompt_tokens": sum(int(c.get("prompt_tokens") or 0) for c in uniq),
        "completion_tokens": sum(int(c.get("completion_tokens") or 0) for c in uniq),
        "total_tokens": sum(int(c.get("total_tokens") or 0) for c in uniq),
        "cache_hits": sum(int(c.get("cache_hits") or 0) for c in uniq),
    }
    out = dict(la)
    out["calls"] = uniq
    out["totals"] = totals
    out["merged_from_shard"] = {
        "shard_dir": os.path.relpath(SHARD, ROOT).replace("\\", "/"),
        "shard_b_qids": len(b_qids),
        "shard_attempts": len(lb.get("calls") or []),
        "main_attempts": len(la.get("calls") or []),
        "note": ("并行分片合并：B 片 answer_key 的缓存以 B 目录为准；台账为两侧并集并重算 totals。"
                 "同一格不重复计分（分片按题号互斥）。"),
        "rule": "按分片归属取权威值（B 片范围的 answer_key 用 B 目录覆盖主目录）",
    }
    with io.open(os.path.join(MAIN, "调用台账.json"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print("台账：主 %d + 分片 %d → 并集 %d 条；成功 %d／失败 %d；token %d"
          % (len(la.get("calls") or []), len(lb.get("calls") or []), totals["attempts"],
             totals["ok"], totals["failed"], totals["total_tokens"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
