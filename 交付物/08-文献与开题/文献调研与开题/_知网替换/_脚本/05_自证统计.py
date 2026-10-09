# -*- coding: utf-8 -*-
"""无登录自证：统计本轮请求 URL 清单的域名命中，并扫描本轮脚本的账号字段。

只读 _脚本/ 下文件，输出到 _脚本/_自证统计.txt（同时打印）。
"""
from __future__ import annotations

import io
import os
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_DIR = os.path.join(BASE, "_脚本")
REQ_LOG = os.path.join(SCRIPT_DIR, "_请求清单_本轮.txt")
OUT = os.path.join(SCRIPT_DIR, "_自证统计.txt")

SCRIPTS = ["00_探测.py", "01_检索.py", "02_抓文章页.py", "03_核实文章页.py", "04_扫描归档池.py",
           "05_自证统计.py", "06_生成产物.py", "07_追加验证输出.py"]

# 禁止命中：主库域名与付费下载域名
FORBIDDEN = ["kns.cnki.net", "pay.cnki.net", "mall.cnki.net", "card.cnki.net", "vipcard.cnki.net", "bank.cnki.net"]
# 账号类字段关键词
ACCOUNT_WORDS = ["账号", "帐号", "密码", "用户名", "password", "passwd", "username", "user_name", "login", "signin", "cookie", "token="]


def main() -> None:
    lines: list[str] = []
    raw = io.open(REQ_LOG, encoding="utf-8").read().splitlines() if os.path.exists(REQ_LOG) else []
    urls = []
    hosts: Counter[str] = Counter()
    for l in raw:
        parts = l.split("\t")
        if len(parts) >= 5 and parts[4].startswith("http"):
            urls.append(parts[4])
            m = re.match(r"https?://([^/]+)", parts[4])
            hosts[m.group(1)] += 1

    lines.append("# 无登录自证统计")
    lines.append(f"请求清单文件：{os.path.basename(REQ_LOG)}")
    lines.append(f"清单行数：{len(raw)}；其中含 URL 的请求行：{len(urls)}（含 RUN_START／RUN_END 两行无 URL 登记）")
    lines.append("")
    lines.append("## 一、域名命中统计")
    for h, n in hosts.most_common():
        lines.append(f"{h}\t{n}")
    lines.append("")
    lines.append("## 二、禁用域名命中")
    for d in FORBIDDEN:
        hit = sum(1 for u in urls if d in u)
        lines.append(f"{d}\t命中 {hit}")
    lines.append("")
    lines.append("## 三、本轮脚本账号字段扫描")
    risky_pat = re.compile(
        r"(账号|帐号|用户名|密码|password|passwd|username|user_name|login|signin|cookie)\s*[=:（(]",
        re.I,
    )
    for name in SCRIPTS:
        p = os.path.join(SCRIPT_DIR, name)
        if not os.path.exists(p):
            continue
        text = io.open(p, encoding="utf-8").read()
        hits = []
        for w in ACCOUNT_WORDS:
            n = len(re.findall(re.escape(w), text, re.I))
            if n:
                hits.append(f"{w}×{n}")
        lines.append(f"{name}\t{'、'.join(hits) if hits else '无账号类字段命中'}")
        ctx = []
        for i, l in enumerate(text.splitlines(), 1):
            if any(re.search(re.escape(w), l, re.I) for w in ACCOUNT_WORDS):
                s = re.sub(r"\s+", " ", l.strip())
                ctx.append(f"    L{i}: {s[:150]}")
        for c in ctx[:6]:
            lines.append(c)
        risky = [f"L{i}: {re.sub(r'\\s+', ' ', l.strip())[:120]}"
                 for i, l in enumerate(text.splitlines(), 1) if risky_pat.search(l)]
        lines.append(f"    → 赋值／调用式账号字段命中：{len(risky)}"
                     + ("；" + "；".join(risky) if risky else ""))
    lines.append("")
    lines.append("## 四、本轮全部请求 URL")
    for u in urls:
        lines.append(u)

    text = "\n".join(lines) + "\n"
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
