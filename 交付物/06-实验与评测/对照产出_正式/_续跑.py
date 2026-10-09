# -*- coding: utf-8 -*-
r"""正式全量对照 —— **续跑**驱动（Lead 用；上一轮驱动被外部中止）。

1. A／B：组级产物已在，只补跑 pass1 stdout 里 `[!! ]` 的题（`--only-qids`，merge 回原文件）。
2. D：组级产物缺失（进程被中止）。用 `跑正式对照.py` 自己的 `collect_rows`／`merge_jsonl`
   把已完成的逐题产物聚合成组级文件，再只补跑缺的题——不自创聚合格式。
   若模块导入失败，**降级为整组重跑**（宁可多花调用，不要产出格式不对的数据）。
3. E／B1：整组跑。  4. C：跳过（正式题集上 C 组结构性不可用，另有线在诊断）。
5. 最后按组补跑最多 3 轮 `[!! ]`，再 `--report-only`。

只调用 `跑正式对照.py`；不写除 `对照产出_正式\` 以外的路径。
"""
import io
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

ROOT = r"C:\Users\15129\Desktop\毕业设计"
OUT = os.path.join(ROOT, "交付物/06-实验与评测", "对照产出_正式")
SCRIPT = os.path.join(ROOT, "交付物/06-实验与评测", "工具", "跑正式对照.py")
LOG = os.path.join(OUT, "_续跑_log.txt")
PENDING = re.compile(r"\[!! \]\s+\d+/\d+\s+(FQ-\d+)")
RUN_GROUPS = ("A", "B", "D", "E", "B1")


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run(args, tag):
    log("RUN %s :: %s" % (tag, " ".join(args)))
    t0 = time.time()
    p = subprocess.run([sys.executable, SCRIPT] + args, cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    out = p.stdout or ""
    with io.open(os.path.join(OUT, "_续跑_%s_stdout.txt" % tag), "w",
                 encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    log("%s 退出码=%s 用时=%.1fs 失败标记=%d"
        % (tag, p.returncode, time.time() - t0, out.count("[!! ]")))
    return out


def all_qids():
    qf = os.path.join(ROOT, "交付物/06-实验与评测", "测试集", "questions.jsonl")
    return [json.loads(l)["qid"] for l in io.open(qf, encoding="utf-8") if l.strip()]


def good_qids(group):
    """逐题产物有效＝有非空 qa_records.jsonl 且无 error_contract.json。"""
    d = os.path.join(OUT, "逐题", group)
    good = []
    if not os.path.isdir(d):
        return good
    for name in sorted(os.listdir(d)):
        sub = os.path.join(d, name)
        if not os.path.isdir(sub) or not name.startswith("FQ-"):
            continue
        qa = os.path.join(sub, "qa_records.jsonl")
        if os.path.exists(qa) and os.path.getsize(qa) > 0 \
                and not os.path.exists(os.path.join(sub, "error_contract.json")):
            good.append(name)
    return good


def load_pass1(tag):
    p = os.path.join(OUT, "_驱动_pass1_%s_stdout.txt" % tag)
    return io.open(p, encoding="utf-8").read() if os.path.exists(p) else ""


def try_seed_D(qids):
    """用脚本自身的聚合函数预置 D 组级产物；失败返回 False。"""
    try:
        spec = importlib.util.spec_from_file_location("_paozhengshi", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rows, qa = [], []
        for q in qids:
            sub = os.path.join(OUT, "逐题", "D", q)
            rows += mod.collect_rows(os.path.join(sub, "answer_trace.jsonl"))
            qa += mod.collect_rows(os.path.join(sub, "qa_records.jsonl"))
        rows.sort(key=lambda r: r["qid"])
        mod.merge_jsonl(os.path.join(OUT, "D", "answer_trace.jsonl"), rows,
                        key=lambda r: r["qid"])
        mod.merge_jsonl(os.path.join(OUT, "D", "qa_records.jsonl"), qa,
                        key=lambda r: mod._answer_id_of(r.get("answer")))
        log("D 组：已用脚本自身 collect_rows/merge_jsonl 预置 %d 题" % len(rows))
        return True
    except Exception as exc:                      # noqa: BLE001
        log("D 组预置失败（%s: %s）→ 降级为整组重跑" % (type(exc).__name__, exc))
        return False


def main():
    io.open(LOG, "w", encoding="utf-8").close()
    log("续跑开始")
    qs = all_qids()
    last = {}

    # 1) A / B：只补 pass1 里失败的
    for g in ("A", "B"):
        txt1 = load_pass1(g)
        last[g] = txt1
        bad = sorted(set(PENDING.findall(txt1)))
        log("%s 组：pass1 失败 %d 题；逐题产物有效 %d 题" % (g, len(bad), len(good_qids(g))))
        if bad:
            last[g] = run(["--groups", g, "--only-qids", ",".join(bad)], "fix1_%s" % g)
            time.sleep(3)

    # 2) D：预置 + 补缺
    done = good_qids("D")
    missing = [q for q in qs if q not in set(done)]
    log("D 组：已完成 %d 题，缺 %d 题" % (len(done), len(missing)))
    seeded = try_seed_D(done) if done else True
    if seeded and missing:
        last["D"] = run(["--groups", "D", "--only-qids", ",".join(missing)], "fix1_D")
    elif not seeded:
        last["D"] = run(["--groups", "D"], "full_D")
    else:
        last["D"] = ""
    time.sleep(3)

    # 3) E / B1：整组
    for g in ("E", "B1"):
        last[g] = run(["--groups", g], "pass_%s" % g)
        time.sleep(3)

    # 4) 补跑轮
    for rnd in (1, 2, 3):
        todo = {}
        for g in RUN_GROUPS:
            q = sorted(set(PENDING.findall(last.get(g, ""))))
            if q:
                todo[g] = q
        if not todo:
            log("第 %d 轮：无失败题，收工" % rnd)
            break
        log("第 %d 轮补跑：%s" % (rnd, {g: len(v) for g, v in todo.items()}))
        for g, ql in todo.items():
            last[g] = run(["--groups", g, "--only-qids", ",".join(ql)],
                          "retry%d_%s" % (rnd, g))
            time.sleep(3)

    log("出报告（--report-only，零调用）")
    run(["--report-only"], "report")
    log("续跑结束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
