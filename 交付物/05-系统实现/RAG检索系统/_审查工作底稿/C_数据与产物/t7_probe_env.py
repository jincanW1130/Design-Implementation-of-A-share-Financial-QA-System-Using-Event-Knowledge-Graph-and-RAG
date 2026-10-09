# -*- coding: utf-8 -*-
"""C 线：判定 W2 失败是环境（内存）还是工具环境变量所致"""
import os, re, subprocess, sys, time

MIRROR = r"C:\Users\15129\AppData\Local\Temp\stage7_accept_4odd_i5d"
PY = sys.executable
PRE = os.path.join(MIRROR, "交付物/03-代码", "检索", "pre_experiment.py")

print("mirror exists:", os.path.isdir(MIRROR))

pat = re.compile(r"(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|"
                 r"ZHIPU|OPENAI|DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)", re.I)
removed = sorted(n for n in os.environ if pat.search(n))
print("按验收工具的规则会被摘除的环境变量个数 =", len(removed))
print("示例：", removed[:12])

def run(env_mode):
    env = dict(os.environ)
    if env_mode == "stripped":
        for n in removed:
            env.pop(n, None)
        env["PYTHONIOENCODING"] = "utf-8"
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"
    t0 = time.time()
    p = subprocess.run([PY, "-X", "utf8", PRE, "--quiet"], cwd=MIRROR,
                       capture_output=True, env=env)
    tail = p.stderr.decode("utf-8", "replace").strip().split("\n")[-2:]
    print("[%s] rc=%d %.1fs stderr_tail=%s" % (env_mode, p.returncode, time.time() - t0, tail))
    return p.returncode

print("== 现场重跑 pre_experiment（正常环境）==")
run("normal")
print("== 现场重跑 pre_experiment（验收工具的摘除环境）==")
run("stripped")
