# -*- coding: utf-8 -*-
"""C 组修复·等价性自证（b）：对正式集抽 5 题，用 `run_query.py --group C` 现场跑，
把它的「呈现顺序」与新 trace 的 `final_evidence_chunk_ids` 逐位比对。

抽样规则**先定死、不挑题**：正式题集 120 题里等距取 5 个序号（1／30／60／90／120）。

用法：
    python "阶段10-系统测试与对比实验\\对照产出_正式\\_等价性自证_C组_b.py"

判据：5／5 题的呈现顺序与 trace 的 `final_evidence_chunk_ids` **逐位相同**；
任何一题不同 → 本脚本以非零退出，不做"解释性放行"。
"""

import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STAGE10 = os.path.dirname(HERE)
ROOT = os.path.dirname(STAGE10)
RUN_QUERY = os.path.join(ROOT, "代码", "检索", "run_query.py")
FORMAL_QUESTIONS = os.path.join(STAGE10, "测试集", "questions.jsonl")
TRACE = os.path.join(HERE, "_正式集trace_C.jsonl")
OUT_JSON = os.path.join(HERE, "_等价性自证_C组_抽5题.json")
TMP_DIR = os.path.join(os.environ.get("TEMP", "."), "c_equiv_b")
SAMPLE_INDEX = (1, 30, 60, 90, 120)          # 1 起，等距，先定后跑


def load_trace():
    rows = {}
    with io.open(TRACE, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                row = json.loads(line)
                rows[row["qid"]] = row
    return rows


def main():
    os.makedirs(TMP_DIR, exist_ok=True)
    all_qids = []
    with io.open(FORMAL_QUESTIONS, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                all_qids.append(json.loads(line)["qid"])
    trace = load_trace()
    picked = [all_qids[i - 1] for i in SAMPLE_INDEX]

    results, ok_count = [], 0
    for qid in picked:
        out_path = os.path.join(TMP_DIR, "run_query_C_%s.json" % qid)
        if os.path.isfile(out_path):
            os.remove(out_path)
        cmd = [sys.executable, RUN_QUERY, "--qid", qid, "--group", "C",
               "--questions", FORMAL_QUESTIONS, "--out", out_path, "--quiet"]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=3600)
        item = {"qid": qid, "exit_code": proc.returncode}
        if proc.returncode != 0 or not os.path.isfile(out_path):
            item["error"] = (proc.stderr or proc.stdout or "")[-500:]
            results.append(item)
            continue
        with io.open(out_path, "r", encoding="utf-8") as fh:
            record = json.load(fh)
        live_order = [int(c) for c in record["final_evidence"]["presentation_order"]]
        trace_order = [int(c) for c in trace[qid]["final_evidence_chunk_ids"]]
        item["run_query_schema"] = record.get("schema")
        item["run_query_group"] = record.get("group")
        item["live_order"] = live_order
        item["trace_order"] = trace_order
        item["order_identical"] = live_order == trace_order
        item["set_identical"] = sorted(live_order) == sorted(trace_order)
        item["printed_presentation_line"] = next(
            (ln.strip() for ln in (proc.stdout or "").splitlines() if "呈现顺序" in ln), None)
        if item["order_identical"]:
            ok_count += 1
        results.append(item)

    payload = {
        "schema": "stage10-c-trace-cross-check-1.0",
        "method": "run_query.py --group C（第 7 阶段既有入口，只读） vs 新生成的正式集 trace",
        "sample_rule": "正式题集 120 题按 1 起等距取序号 %s" % (list(SAMPLE_INDEX),),
        "trace": os.path.abspath(TRACE),
        "questions_file": os.path.abspath(FORMAL_QUESTIONS),
        "picked": picked,
        "order_identical_count": ok_count,
        "picked_count": len(picked),
        "all_identical": ok_count == len(picked),
        "per_question": results,
    }
    with io.open(OUT_JSON, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True))
    for item in results:
        print("%s  exit=%s  逐位相同=%s" % (item["qid"], item.get("exit_code"),
                                            item.get("order_identical")))
        if item.get("order_identical"):
            print("   run_query 呈现顺序 = %s" % (item["live_order"],))
        elif "error" in item:
            print("   错误：%s" % item["error"][-300:])
    print("合计：%d／%d 逐位相同" % (ok_count, len(picked)))
    return 0 if ok_count == len(picked) else 1


if __name__ == "__main__":
    raise SystemExit(main())
