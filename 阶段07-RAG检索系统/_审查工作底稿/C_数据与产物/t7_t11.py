# -*- coding: utf-8 -*-
"""C 线：T11 三项声称的独立复核（0 次模型调用 / 11 指纹 / 四产物双跑一致）"""
import io, json, os, re

ROOT = r"C:\Users\15129\Desktop\毕业设计"
CODE = os.path.join(ROOT, "代码", "检索")
T11 = os.path.join(ROOT, "阶段07-RAG检索系统", "_工作底稿", "_T11")

CHAIN = ["check_inputs.py", "vector_search.py", "graph_query.py", "pipeline.py",
         "pre_experiment.py", "metrics.py"]
CONTROL = "third_party_review.py"

PAT_EKEY = re.compile(r"(api[_-]?key|secret|access[_-]?token|auth[_-]?token)", re.I)
PAT_NET = re.compile(
    r"(requests\.|urllib\.request|socket\.|http://|https://|openai|anthropic|"
    r"dashscope|moonshot|zhipu|bigmodel)", re.I)


def scan(name):
    p = os.path.join(CODE, name)
    s = io.open(p, encoding="utf-8").read()
    hits = []
    for i, line in enumerate(s.split("\n"), 1):
        if PAT_EKEY.search(line) or PAT_NET.search(line):
            hits.append((i, line.strip()[:110]))
    return hits


print("== T11 声称①：链上脚本 0 处密钥／网络字样（含正对照）==")
for n in CHAIN:
    h = scan(n)
    print("%-22s hits=%d %s" % (n, len(h), h[:3] if h else ""))
hc = scan(CONTROL)
print("%-22s hits=%d（正对照；T11 记录 9）" % (CONTROL, len(hc)))

print()
print("== config.MODEL_CALLS_ALLOWED ==")
cfg = io.open(os.path.join(CODE, "config.py"), encoding="utf-8").read()
for m in re.finditer(r"MODEL_CALLS_ALLOWED\s*=\s*(\S+)", cfg):
    print("  config.py:", m.group(0))

print()
print("== T11 摘要（原文抽样）==")
summ = json.load(io.open(os.path.join(T11, "T11_summary.json"), encoding="utf-8"))
print("summary schema:", summ["schema"], "seconds:", summ["seconds"])
print("step1_input_fingerprint_ok:", summ["step1_input_fingerprint_ok"],
      "inputs:", summ["step1_inputs"])
print("step2_zero_calls_ok:", summ["step2_zero_calls_ok"],
      "chain forbidden:", summ.get("step2_chain_forbidden_hits"))
print("step2_control_hits:", summ.get("step2_control_hits"))
print("step2_removed_env_names:", summ.get("step2_removed_env_names"))
print("step3_double_run_identical:", summ["step3_double_run_identical"])
print("run1 sha:", json.dumps(summ["step3_sha256_run1"], ensure_ascii=False, indent=1))

print()
print("== 链上六步日志 vs 摘要 ==")
for step in summ["step2_chain"]:
    print("%-24s code=%s seconds=%s log_exists=%s" % (
        step["name"], step["code"], step["seconds"],
        os.path.exists(os.path.join(ROOT, step["log"]))))

print()
print("== run1/run2 日志尾部 ==")
LOGS = ["t11_run1_pipeline.log", "t11_run2_pipeline.log", "t11_run1_pre_experiment.log",
        "t11_run2_pre_experiment.log", "t11_run1_metrics.log", "t11_run2_metrics.log"]
for tag in LOGS:
    p = os.path.join(T11, "logs", tag)
    if not os.path.exists(p):
        print(tag, "缺失")
        continue
    s = io.open(p, encoding="utf-8", errors="replace").read()
    lines = [l for l in s.strip().split("\n") if l.strip()]
    print("---", tag, "(%d 行)" % len(s.split("\n")))
    for l in lines[-3:]:
        print("    ", l[:200])
