# -*- coding: utf-8 -*-
"""C 线复核 · 项6：run_manifest.json 的声明核验。

只读。逐项：
  1) artifacts_sha256 里每个文件现算 SHA-256 / bytes 是否与登记一致
  2) input_fingerprints 是否可复算（现算 10 个文件 SHA，与登记比对；并核 recomputed_mismatched）
  3) model_calls（total=60／retries=0）与 answer_trace 的调用痕迹是否自洽
  4) assembly_determinism 的 30/30 是否可独立复现（0 调用；现场连装两次比 Prompt SHA）
  5) model_output_repeatability 的 0/30 是否可核（看 differing_qids；盘面自洽性）
  6) config_snapshot 与 交付物/03-代码\问答\config.py / 交付物/03-代码\检索\config.py 的实际取值是否一致

正对照：把 answer_trace 的登记 SHA 篡改一位，比对器必须报不符。
"""
import hashlib
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "交付物/03-代码", "问答"))
sys.path.insert(1, os.path.join(ROOT, "交付物/03-代码", "检索"))
import config  # noqa
import run_answer as ra  # noqa


def sha_bytes(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest(), os.path.getsize(path)


def load_jsonl(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def main():
    man = config.read_json(os.path.join(ROOT, "交付物/05-系统实现/智能问答系统", "问答产出", "run_manifest.json"))
    fails = 0

    print("=" * 100)
    print("项6  run_manifest.json 声明核验")
    print("=" * 100)

    # ---- 1) artifacts_sha256 ----
    print("\n[1] artifacts_sha256 现算复核")
    n_bad = 0
    for name, rec in sorted(man["artifacts_sha256"].items()):
        path = rec["path"]
        if not os.path.isfile(path):
            print("   %-18s 文件不存在：%s" % (name, path))
            n_bad += 1
            fails += 1
            continue
        sha, n = sha_bytes(path)
        ok = (sha == rec["sha256"] and n == rec["bytes"])
        n_bad += 0 if ok else 1
        print("   %-18s bytes=%s sha=%s %s" % (name, n, sha[:16], "OK" if ok else "FAIL"))
        if not ok:
            print("      登记 bytes=%s sha=%s" % (rec["bytes"], rec["sha256"]))
    print("   artifacts 不符数 = %d / %d" % (n_bad, len(man["artifacts_sha256"])))
    fails += n_bad

    # ---- 2) input_fingerprints ----
    print("\n[2] input_fingerprints 可复算性")
    inf = man["input_fingerprints"]
    n_bad = 0
    for f in inf["files"]:
        path = f["path"]
        if not os.path.isfile(path):
            print("   %-22s 不存在" % f["key"])
            n_bad += 1
            continue
        sha, n = sha_bytes(path)
        ok = (sha == f["sha256"] and n == f["bytes"])
        n_bad += 0 if ok else 1
        print("   item%-2s %-22s bytes=%-9s %s" % (f["item"], f["key"], n, "OK" if ok else "FAIL"))
    print("   登记 count=%s；现场不符 = %d；登记 recomputed_mismatched = %s（应为空）"
          % (inf["count"], n_bad, inf["recomputed_mismatched"]))
    if inf["count"] != len(inf["files"]) or len(inf["files"]) != 10:
        print("   !! count 与 files 数不符")
        n_bad += 1
    fails += n_bad

    # ---- 3) model_calls 自洽 ----
    print("\n[3] model_calls 自洽（total=60／retries=0）")
    mc = man["model_calls"]
    atrace = load_jsonl(config.ANSWER_TRACE_PATH)
    n_attempts = sum(len(r.get("attempts") or []) for r in atrace)
    n_retried = sum(1 for r in atrace if r.get("retried"))
    print("   登记 total=%s cycle_1=%s cycle_2=%s retries=%s"
          % (mc["total"], mc["cycle_1"], mc["cycle_2"], mc["retries"]))
    print("   answer_trace 行数=%d；逐行 attempts 合计=%d；retried 行数=%d"
          % (len(atrace), n_attempts, n_retried))
    ok_total = (mc["total"] == mc["cycle_1"] + mc["cycle_2"] == 60)
    ok_cycle = (mc["cycle_1"] == len(atrace) == 30 and mc["cycle_2"] == 30)
    ok_retry = (mc["retries"] == n_retried == 0)
    print("   total==cycle_1+cycle_2==60: %s；cycle_1==trace行数==30: %s；retries==0 且 trace 无重试: %s"
          % (ok_total, ok_cycle, ok_retry))
    if not (ok_total and ok_cycle and ok_retry):
        fails += 1
    print("   注：第1次运行写出的 answer_trace 只落 30 行；第2次运行不写盘，故其 30 次调用无法从产物点数。")

    # ---- 4) assembly_determinism 独立复现 ----
    print("\n[4] assembly_determinism 独立复现（0 调用）")
    ad = man["assembly_determinism"]
    a = {c["qid"]: c["prompt"]["sha256"] for c in ra.load_cases_from_trace()}
    b = {c["qid"]: c["prompt"]["sha256"] for c in ra.load_cases_from_trace()}
    same = [q for q in a if a[q] == b[q]]
    reg_sha = ad["prompt_sha256_by_qid"]
    reg_match = sum(1 for q in a if reg_sha.get(q) == a[q])
    print("   登记 repeats=%s questions=%s identical=%s all_identical=%s model_calls=%s"
          % (ad["repeats"], ad["questions"], ad["identical"], ad["all_identical"], ad["model_calls"]))
    print("   现场连装两次一致 = %d/%d；与登记 prompt_sha256_by_qid 一致 = %d/%d"
          % (len(same), len(a), reg_match, len(a)))
    ok_ad = (ad["questions"] == 30 and ad["identical"] == 30 and ad["all_identical"]
             and ad["model_calls"] == 0 and len(same) == 30 and reg_match == 30)
    print("   结论 = %s" % ("OK" if ok_ad else "FAIL"))
    if not ok_ad:
        fails += 1

    # ---- 5) model_output_repeatability ----
    print("\n[5] model_output_repeatability 可核性（0/30）")
    mor = man["model_output_repeatability"]
    diff = mor.get("differing_qids") or []
    ident = mor.get("identical_qids") or []
    ok_rate = (mor["questions"] == 30 and mor["identical"] == 0 and mor["rate"] == 0.0
               and len(diff) == 30 and len(ident) == 0 and set(diff) == set(a))
    print("   登记 questions=%s identical=%s rate=%s differing=%d identical_qids=%d"
          % (mor["questions"], mor["identical"], mor["rate"], len(diff), len(ident)))
    print("   盘面自洽（rate==identical/questions，diff∪ident==30）= %s" % ok_rate)
    print("   !! 第2次运行的 body_text 未落盘：本项只可核「内部自洽」，无法独立复算重复一致率本身。")
    if not ok_rate:
        fails += 1

    # ---- 6) config_snapshot ----
    print("\n[6] config_snapshot vs 代码实际取值")
    cs = man["config_snapshot"]
    checks = {
        "model_name": config.require_fixed("model_name"),
        "model_version": config.require_fixed("model_version"),
        "endpoint": config.require_fixed("endpoint"),
        "temperature": config.require_fixed("temperature"),
        "max_tokens": config.require_fixed("max_tokens"),
        "prompt_version": config.require_fixed("prompt_version"),
        "K": config.K, "N": config.N, "context_token_budget": config.CONTEXT_TOKEN_BUDGET,
        "g": config.G, "dataset_version": config.require_fixed("dataset_version"),
        "data_cutoff_time": config.require_fixed("data_cutoff_time"),
    }
    n_bad = 0
    for k, v in checks.items():
        rv = cs.get(k)
        ok = (rv == v)
        n_bad += 0 if ok else 1
        print("   %-22s 登记=%-26r 现取=%r %s" % (k, rv, v, "OK" if ok else "FAIL"))
    print("   config_snapshot 不符 = %d" % n_bad)
    fails += n_bad

    # ---- 正对照 ----
    print("\n--- 正对照（产物 SHA 比对器有效性）---")
    rec = man["artifacts_sha256"]["answer_trace"]
    tampered = rec["sha256"][:-1] + ("0" if rec["sha256"][-1] != "0" else "1")
    sha, n = sha_bytes(rec["path"])
    verdict = "一致" if sha == tampered else "不符"
    print("  篡改 answer_trace 登记 SHA 末位 → 比对结论 = %s（必须=不符）→ %s"
          % (verdict, "PASS" if verdict == "不符" else "对照失效"))

    print("\n结论：run_manifest 声明不符项合计 = %d" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
