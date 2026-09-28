# -*- coding: utf-8 -*-
"""把表格单元里未转义的竖线转义为 \| （仅动我自己那份报告）。"""
import io

P = "B_代码与门禁复核.md"
t = io.open(P, encoding="utf-8").read()
orig = t

BS = chr(92)
repl = [
    ("`|final|>K`", "`" + BS + "|final" + BS + "|>K`"),
    ("split('|')", "split('" + BS + "|')"),
    (
        "(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|ZHIPU|"
        "OPENAI|DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)",
        "(API[_-]?KEY" + (BS + "|") + "SECRET" + (BS + "|") + "ACCESS[_-]?TOKEN" + (BS + "|")
        + "AUTH[_-]?TOKEN" + (BS + "|") + "MOONSHOT" + (BS + "|") + "DASHSCOPE" + (BS + "|")
        + "ZHIPU" + (BS + "|") + "OPENAI" + (BS + "|") + "DEEPSEEK" + (BS + "|") + "QIANFAN"
        + (BS + "|") + "KIMI" + (BS + "|") + "GLM" + (BS + "|") + "BAIDU" + (BS + "|") + "ERNIE"
        + (BS + "|") + "ANTHROPIC" + (BS + "|") + "GEMINI)",
    ),
]
for a, b in repl:
    print("count(%s) = %d" % (a[:24], t.count(a)))
    t = t.replace(a, b)

if t != orig:
    io.open(P, "w", encoding="utf-8", newline="").write(t)
    print("written")
else:
    print("no change")
