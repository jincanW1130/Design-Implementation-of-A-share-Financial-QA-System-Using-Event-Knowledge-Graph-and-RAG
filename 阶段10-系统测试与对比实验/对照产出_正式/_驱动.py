# -*- coding: utf-8 -*-
r"""正式全量对照的驱动脚本（Lead 接管用）。

用途：串行跑 A/B/C/D/E/B1 六组 → 解析 stdout 找出 `[!! ]` 失败题 →
用 `--only-qids` 按组补跑（`merge_jsonl` 会把补跑结果并回同组的 answer_trace.jsonl，
故补跑不会丢已成功的题）→ 最多 3 轮 → 最后 `--report-only` 出报告。

不做任何输出格式加工：全部指标与报告仍由 `跑正式对照.py` 自己产出。
"""
import io
import os
import re
import subprocess
import sys
import time

ROOT = r"C:\Users\15129\Desktop\毕业设计"
OUT = os.path.join(ROOT, "阶段10-系统测试与对比实验", "对照产出_正式")
SCRIPT = os.path.join(ROOT, "阶段10-系统测试与对比实验", "工具", "跑正式对照.py")
GROUPS = ["A", "B", "C", "D", "E", "B1"]
LOG = os.path.join(OUT, "_驱动_log.txt")


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with io.open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def run(args, tag):
    cmd = [sys.executable, SCRIPT] + args
    log("RUN %s :: %s" % (tag, " ".join(args)))
    started = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    secs = time.time() - started
    out = proc.stdout or ""
    with io.open(os.path.join(OUT, "_驱动_%s_stdout.txt" % tag), "w",
                 encoding="utf-8", newline="\n") as fh:
        fh.write(out)
    log("%s 退出码=%s 用时=%.1fs 失败标记=%d"
        % (tag, proc.returncode, secs, out.count("[!! ]")))
    return proc.returncode, out


PENDING = re.compile(r"\[!! \]\s+\d+/\d+\s+(FQ-\d+)")


def failed_by_group(out):
    """本组 stdout 里 `[!! ]` 的题号（单组调用时同一文件内不会有跨组歧义）。"""
    return sorted(set(PENDING.findall(out)))


def main():
    io.open(LOG, "w", encoding="utf-8").close()
    log("驱动开始；先跑六组全量")
    last = {}
    for g in GROUPS:
        # 每组单独调用，便于把失败题归属到组
        rc, out = run(["--groups", g], "pass1_%s" % g)
        last[g] = out
        time.sleep(3)

    for rnd in (1, 2, 3):
        todo = {}
        for g in GROUPS:
            q = failed_by_group(last.get(g, ""))
            if q:
                todo[g] = q
        if not todo:
            log("第 %d 轮：无失败题，收工" % rnd)
            break
        log("第 %d 轮补跑：%s" % (rnd, {g: len(v) for g, v in todo.items()}))
        for g, qids in todo.items():
            rc, out = run(["--groups", g, "--only-qids", ",".join(qids)],
                          "retry%d_%s" % (rnd, g))
            last[g] = out
            time.sleep(3)

    log("出报告（--report-only，零调用）")
    rc, out = run(["--report-only"], "report")
    log("驱动结束，report 退出码=%s" % rc)
    return 0


if __name__ == "__main__":
    sys.exit(main())
