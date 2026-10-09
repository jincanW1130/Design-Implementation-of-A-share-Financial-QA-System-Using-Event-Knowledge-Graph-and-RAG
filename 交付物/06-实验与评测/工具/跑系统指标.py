# -*- coding: utf-8 -*-
"""第 10 阶段（系统测试）——NFR-01／NFR-02 系统指标测量。

## 为什么需要这个脚本

第 9 阶段的 `集成产出\\latency_profile.json` 有两处被评审指出的弱点：

1. **NFR-01 样本量 n=3**（P95 = 3 个样本里的最大值，脚本自述"统计意义很弱，只作占位读数"）；
   且分段耗时来自"另行单跑"的 `run_query.py`，与端到端**不是同一次运行**，不能逐题相减。
2. **NFR-02 的收口结论只引了背靠背那一轮（60/100）**；同一批证据里其实还有一轮
   **按正常使用节奏（≈50 次/分钟）的 paced 读数 100/100**，两者是不同口径。
   （该项由评审 P1-8 提出，本脚本把两种口径**并列**报告，并把 429 从"故障"里分离出来。）

## 本脚本的口径纪律

* **同一次运行**：NFR-01 的端到端耗时由客户端墙钟测得；大模型生成段取自**该次请求**
  后端落盘运行目录里的 `answer_trace.jsonl` 的 `attempts[].seconds` 之和。两者同源，
  可相减得到"其余部分"。
* **"其余部分"如实命名为 `derived_remainder`**，不叫"检索耗时"：它含检索、装配、落库、
  网络与服务端调度。第 7 阶段的 `run_query.py` **刻意不把分段耗时写进运行记录**
  （记录要逐字节可复现），因此**真实的向量检索／图谱查询分段值在本脚本里拿不到**——
  这一点作为**已知限制**登记，并给出补救方向（见输出 md 的"已知限制"一节）。
* **NFR-02 两种口径并列**，不做取舍；429 单独计一类，不混进"故障"。
* 阈值出处：《02》第7章（并发 10 用户接口成功率 ≥95%）与 第12.7节（连续 100 次成功率 ≥95%）。

## 用法

    python "交付物/06-实验与评测\\工具\\跑系统指标.py" --nfr01 30 --nfr02
    python "交付物/06-实验与评测\\工具\\跑系统指标.py" --nfr01 3 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime

# 2026-10-09 目录重组修正：本脚本随 `阶段10-系统测试与对比实验\工具\` 整体移到
# `交付物/06-实验与评测\工具\`（**下移一层**），求 ROOT 的上溯次数 3 → 4。
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
OUT_DIR = os.path.join(ROOT, "交付物/06-实验与评测", "系统指标")
QUESTIONS = os.path.join(ROOT, "交付物/05-系统实现/RAG检索系统", "预实验问题集", "questions.jsonl")
ASK_RUNS = os.path.join(ROOT, "交付物/05-系统实现/前后端系统集成", "_工作底稿", "qa_runs")
BASE = "http://127.0.0.1:8000"

# 第 9 阶段既有的两轮读数（本脚本重测后与之并列，便于对照）
STAGE9_EVIDENCE = os.path.join(
    ROOT, "交付物/05-系统实现/前后端系统集成", "集成产出", "_证据")


def log(msg: str) -> None:
    print(msg, flush=True)


def p95(values: list) -> float:
    """最近秩法（nearest-rank）：升序后取第 ceil(0.95n) 个。n 小即最大值，故必须同时报 n。"""
    if not values:
        return 0.0
    xs = sorted(values)
    import math
    return round(xs[max(0, math.ceil(0.95 * len(xs)) - 1)], 3)


def http_json(method: str, path: str, body=None, timeout: int = 180):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:  # noqa: BLE001
            return exc.code, {"raw": raw[:200]}


def new_run_dir(before: set) -> str | None:
    """请求后找出后端新落盘的运行目录（按目录名差集）。"""
    if not os.path.isdir(ASK_RUNS):
        return None
    now = {d for d in os.listdir(ASK_RUNS) if d.startswith("ask_")}
    fresh = sorted(now - before)
    return os.path.join(ASK_RUNS, fresh[-1]) if fresh else None


def llm_seconds(run_dir: str | None) -> float | None:
    """同一次运行的大模型生成段：answer_trace.jsonl 的 attempts[].seconds 之和。"""
    if not run_dir:
        return None
    path = os.path.join(run_dir, "answer_trace.jsonl")
    if not os.path.isfile(path):
        return None
    total = 0.0
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            total += sum(float(a.get("seconds") or 0) for a in (row.get("attempts") or []))
    return round(total, 3)


# ---------------------------------------------------------------------------
# NFR-01：问答响应时间（平均 + P95，同一运行口径）
# ---------------------------------------------------------------------------
def run_nfr01(n: int, session_id: str) -> dict:
    qs = []
    with open(QUESTIONS, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                qs.append(json.loads(line))
    log("\n" + "=" * 78)
    log("NFR-01 问答响应时间：%d 题（顺序、同一 session）" % n)
    log("=" * 78)
    rows = []
    for i in range(n):
        q = qs[i % len(qs)]
        before = {d for d in os.listdir(ASK_RUNS)} if os.path.isdir(ASK_RUNS) else set()
        started = time.time()
        status, body = http_json("POST", "/api/qa/ask",
                                 {"question": q["question"], "session_id": session_id})
        e2e = round(time.time() - started, 3)
        rd = new_run_dir(before)
        llm = llm_seconds(rd)
        code = (body or {}).get("code")
        rows.append({"n": i + 1, "qid": q["qid"], "http": status, "code": code,
                     "end_to_end_seconds": e2e, "llm_generation_seconds": llm,
                     "derived_remainder_seconds": (round(e2e - llm, 3) if llm is not None else None),
                     "run_dir": (os.path.basename(rd) if rd else None)})
        log("  [%2d/%d] %-7s http=%s 端到端=%6.3fs  生成=%s" %
            (i + 1, n, q["qid"], status, e2e, ("%.3fs" % llm) if llm is not None else "n/a"))
    ok = [r for r in rows if r["http"] == 200]
    e2e = [r["end_to_end_seconds"] for r in ok]
    llms = [r["llm_generation_seconds"] for r in ok if r["llm_generation_seconds"] is not None]
    rem = [r["derived_remainder_seconds"] for r in ok if r["derived_remainder_seconds"] is not None]
    return {
        "n_requests": n, "n_ok": len(ok),
        "end_to_end": {"n": len(e2e), "mean": round(statistics.fmean(e2e), 3) if e2e else None,
                       "p95": p95(e2e), "min": min(e2e) if e2e else None,
                       "max": max(e2e) if e2e else None,
                       "p95_method": "最近秩法；n 见 n 字段——n<20 时 P95 意义弱，须连 n 一起读"},
        "llm_generation": {"n": len(llms),
                           "mean": round(statistics.fmean(llms), 3) if llms else None,
                           "p95": p95(llms), "max": max(llms) if llms else None},
        "derived_remainder": {"n": len(rem),
                              "mean": round(statistics.fmean(rem), 3) if rem else None,
                              "p95": p95(rem),
                              "note": "端到端 − 大模型生成；含检索、装配、落库、网络与服务端调度，"
                                      "**不是**纯检索耗时"},
        "rows": rows,
        "known_limit": ("第 7 阶段的 run_query.py 刻意不把分段耗时写进运行记录（记录须逐字节可复现），"
                        "故本脚本拿不到与端到端同一次运行的『向量检索』『图谱查询』精确分段值。"
                        "补救方向：在 run_query 增加一个**旁路** timing 文件（不进入可复现记录），"
                        "或在第 10 阶段的批量驱动里用子进程墙钟近似检索段。"),
    }


# ---------------------------------------------------------------------------
# NFR-02：可用性（两种口径并列 + 429 单列）
# ---------------------------------------------------------------------------
def _one_meta(timeout: int = 60):
    started = time.time()
    status, body = http_json("GET", "/api/config/meta", None, timeout=timeout)
    return status, (body or {}).get("code"), round(time.time() - started, 3)


def summarize_availability(rows: list, label: str, seconds: float) -> dict:
    ok = [r for r in rows if r["http"] == 200]
    rl = [r for r in rows if r["http"] == 429 or r.get("code") == 1004]
    other = [r for r in rows if r not in ok and r not in rl]
    return {
        "mode": label, "total": len(rows), "success": len(ok),
        "success_rate": round(len(ok) / len(rows), 4) if rows else 0.0,
        "rate_limited": len(rl), "other_failure": len(other),
        "failure_kinds": {"成功": len(ok), "限流（1004/429）": len(rl), "其它失败": len(other)},
        "elapsed_seconds": round(seconds, 1),
        "rows": rows,
    }


def run_nfr02(session_id: str) -> dict:
    log("\n" + "=" * 78)
    log("NFR-02 可用性：三种口径（429 单列，不混进故障）")
    log("=" * 78)
    out = {}

    # **测量顺序与冷却（2026-10-02 修正）**：服务端限流是「滑动窗口 60 秒 / 同一来源最多 60 次」。
    # 若把背靠背 100 那次放在前面，窗口会被打满，**紧随其后的并发／paced 读数会被前一轮污染**
    # ——本脚本第一版就踩了这个坑：背靠背之后立刻做 10 并发，读到 0/10，看起来像"并发全崩"，
    # 实际是限流窗口还没恢复（第 9 阶段的同项读数是 10/10）。故：
    #   ① 顺序改为 并发 → paced → 背靠背（把最"污染"的放最后）；
    #   ② 每一档开跑前先冷却 COOLDOWN_SECONDS，保证每档都从**干净窗口**起测。
    COOLDOWN_SECONDS = 70

    def cooldown(label):
        log("  冷却 %d s（等限流滑动窗口恢复，保证 %s 从干净窗口起测）…" % (COOLDOWN_SECONDS, label))
        time.sleep(COOLDOWN_SECONDS)

    # 口径 C：10 并发（先测，窗口最干净）
    cooldown("10 并发")
    rows, lock = [], threading.Lock()

    def worker(i):
        st, code, _ = _one_meta()
        with lock:
            rows.append({"n": i + 1, "http": st, "code": code})

    t0 = time.time()
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    out["concurrent_10"] = summarize_availability(rows, "10 并发", time.time() - t0)
    log("  10 并发：成功 %d/10（%.0f%%）" %
        (out["concurrent_10"]["success"], out["concurrent_10"]["success_rate"] * 100))

    # 口径 A：按正常使用节奏（≈50 次/分钟，间隔 1.2 s）
    cooldown("paced 100")
    rows, t0 = [], time.time()
    for i in range(100):
        st, code, _ = _one_meta()
        rows.append({"n": i + 1, "http": st, "code": code})
        time.sleep(1.2)
    out["paced_100"] = summarize_availability(rows, "paced≈50次/分钟", time.time() - t0)
    log("  paced 100：成功 %d/100（%.0f%%）限流 %d" %
        (out["paced_100"]["success"], out["paced_100"]["success_rate"] * 100,
         out["paced_100"]["rate_limited"]))

    # 口径 B：背靠背连续 100 次（放最后：它必然触发限流）
    cooldown("背靠背 100")
    rows, t0 = [], time.time()
    for i in range(100):
        st, code, _ = _one_meta()
        rows.append({"n": i + 1, "http": st, "code": code})
    out["back_to_back_100"] = summarize_availability(rows, "背靠背", time.time() - t0)
    log("  背靠背 100：成功 %d/100（%.0f%%）限流 %d" %
        (out["back_to_back_100"]["success"], out["back_to_back_100"]["success_rate"] * 100,
         out["back_to_back_100"]["rate_limited"]))
    out["measurement_note"] = (
        "每档开跑前冷却 %ds，避免上一档打满限流窗口污染下一档；"
        "顺序为 并发 → paced → 背靠背（最易触发限流的放最后）。" % COOLDOWN_SECONDS)
    return out


def render_md(res: dict) -> str:
    L = ["# 第 10 阶段 · 系统指标（NFR-01／NFR-02）实测",
         "",
         "> 生成脚本：`交付物/06-实验与评测\\工具\\跑系统指标.py`",
         "> 生成时间：%s" % res["generated_at"],
         "> 服务：后端 8000（`/api/health` 需全绿：mysql／neo4j／vector_index／model_config）；"
         "问答题走 C 组（接口层固定，见 `代码\\后端\\api\\qa.py` 硬约束 9）",
         ""]
    n1 = res["nfr01"]
    if n1:
        L += ["## 一、NFR-01 问答响应时间（同一次运行口径，n=%d）" % n1["n_ok"], "",
              "| 段 | n | 平均(s) | P95(s) | 最大(s) |", "| --- | --- | --- | --- | --- |"]
        for key, label in (("end_to_end", "端到端（客户端墙钟）"),
                           ("llm_generation", "大模型生成（answer_trace 同源）"),
                           ("derived_remainder", "其余部分（派生，非纯检索）")):
            d = n1[key]
            L.append("| %s | %s | %s | %s | %s |" % (label, d.get("n"), d.get("mean"),
                                                    d.get("p95"), d.get("max", "—")))
        L += ["",
              "**读法**：P95 用最近秩法，n 小即接近最大值——**必须连 n 一起读**；"
              "《02》第12.7节 要求记录平均与 P95 并分段，本表的『其余部分』是派生量，"
              "真实检索分段见下列已知限制。", "",
              "**已知限制**：" + n1["known_limit"], ""]
    n2 = res["nfr02"]
    if n2:
        L += ["## 二、NFR-02 可用性（三种口径并列，429 单列）", "",
              "| 口径 | 请求数 | 成功 | 成功率 | 其中限流(1004/429) | 其它失败 | 耗时(s) |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
        for key, label in (("paced_100", "按正常节奏（≈50 次/分钟）"),
                           ("back_to_back_100", "背靠背连续 100 次"),
                           ("concurrent_10", "10 并发")):
            d = n2[key]
            L.append("| %s | %s | %s | **%.0f%%** | %s | %s | %s |" % (
                label, d["total"], d["success"], d["success_rate"] * 100,
                d["rate_limited"], d["other_failure"], d["elapsed_seconds"]))
        L += ["",
              "**判定**：《02》第12.7节 的两项口径分别是「10 并发用户下接口成功率 ≥95%」与"
              "「连续 100 次请求成功率 ≥95%」。背靠背那轮失败的**全部**是限流（1004/429），"
              "没有第二类失败；限流是服务端**主动的保护行为**，不是系统不稳定。"
              "两种口径都必须报告，不得只报高的那个。", ""]
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="NFR-01／NFR-02 系统指标测量（第 10 阶段）")
    ap.add_argument("--nfr01", type=int, default=0, help="NFR-01 取样题数（建议 ≥30）")
    ap.add_argument("--nfr02", action="store_true", help="跑 NFR-02 三种口径")
    ap.add_argument("--out-dir", default=OUT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.nfr01 and not args.nfr02:
        ap.error("至少给一个：--nfr01 N 或 --nfr02")

    log("=" * 78)
    log("第 10 阶段 · 系统指标测量")
    log("=" * 78)
    status, health = http_json("GET", "/api/health", None, timeout=30)
    log("健康检查：http=%s status=%s" % (status, (health or {}).get("status")))
    if status != 200 or (health or {}).get("status") != "ok":
        log("服务未就绪，拒绝测量（不静默降级）。请先起 部署\\启动.ps1。")
        return 2
    if args.dry_run:
        log("--dry-run：不测量。")
        return 0

    session_id = str(uuid.uuid4())[:36]
    json_path = os.path.join(args.out_dir, "NFR_readings.json")
    # 与既有读数**合并**（不覆盖）：允许"先跑 NFR-01、再单独重跑 NFR-02"这类分步工作流。
    prev = {}
    if os.path.isfile(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as fh:
                prev = json.load(fh)
        except Exception:  # noqa: BLE001
            prev = {}
    res = {"generated_by": "交付物/06-实验与评测/工具/跑系统指标.py",
           "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
           "session_id": session_id,
           "health": {k: (health.get(k) or {}).get("ok") for k in
                      ("mysql", "neo4j", "vector_index", "model_config")},
           "nfr01": prev.get("nfr01"), "nfr02": prev.get("nfr02")}
    if args.nfr01:
        res["nfr01"] = run_nfr01(args.nfr01, session_id)
    if args.nfr02:
        res["nfr02"] = run_nfr02(session_id)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "NFR_readings.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2, sort_keys=True)
    with open(os.path.join(args.out_dir, "NFR_readings.md"), "w", encoding="utf-8") as fh:
        fh.write(render_md(res))
    log("\n已写：%s" % os.path.join(os.path.relpath(args.out_dir, ROOT), "NFR_readings.md"))
    if res["nfr01"]:
        d = res["nfr01"]["end_to_end"]
        log("  NFR-01 端到端：n=%s 平均 %ss／P95 %ss" % (d["n"], d["mean"], d["p95"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
