# -*- coding: utf-8 -*-
r"""交付物/03-代码\测试\bdd\runner.py —— BDD 试点的**零依赖轻量执行器**（2026-10-11）。

审查报告「BDD 规格」维度的试点落点：解析同目录 `错误码契约.feature`（Gherkin 中文场景），
把 Scenario 的 When／Then 映射到既有实现（TestClient 进程内请求——与 test_g 同一套离线
纪律），逐场景断言并输出读数。**不引入 pytest-bdd**：试点目的是证明形态可行，避免为
试点引入新依赖；场景扩写时在 `STEPS` 表登记映射即可。

用法：python 交付物/03-代码\测试\bdd\runner.py     # 退出码 0＝全部场景通过
"""

from __future__ import annotations

import json
import os
import re
import sys

from fastapi.testclient import TestClient

BACKEND = r"C:\Users\15129\Desktop\毕业设计\交付物\03-代码\后端"
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
sys.dont_write_bytecode = True

import main as main_mod  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_feature(path):
    """极简 Gherkin 解析：Scenario 名 → [(When 行, Then 行), …]（本试点每个场景恰一对）。"""
    scenarios, cur, last_when, last_then = [], None, None, None
    for raw in open(path, "r", encoding="utf-8"):
        line = raw.strip()
        if line.startswith("Scenario:"):
            if cur and last_when and last_then:
                scenarios.append((cur, last_when, last_then))
            cur, last_when, last_then = line.split(":", 1)[1].strip(), None, None
        elif line.startswith("When "):
            last_when = line[5:].strip()
        elif line.startswith("Then "):
            last_then = line[5:].strip()
    if cur and last_when and last_then:
        scenarios.append((cur, last_when, last_then))
    return scenarios


def main() -> int:
    client = TestClient(main_mod.app)
    feature = os.path.join(HERE, "错误码契约.feature")
    scenarios = parse_feature(feature)
    print("=" * 78)
    print("BDD 试点：错误码契约（%d 个场景，TestClient 进程内执行）" % len(scenarios))
    print("=" * 78)
    failed = []
    for name, when, then in scenarios:
        # When 映射（STEPS 表：中文描述 → (方法, 路径, 载荷)）
        if "question 为空串" in when:
            method, path, payload, raw = "POST", "/api/qa/ask", {"question": "", "session_id": "S-BDD"}, None
        elif "不是合法 JSON" in when:
            method, path, payload, raw = "POST", "/api/qa/ask", None, b"{not-json"
        elif "缺 question 键" in when:
            method, path, payload, raw = "POST", "/api/qa/ask", {"session_id": "S-BDD"}, None
        elif "answer_id 999999" in when:
            method, path, payload, raw = "GET", "/api/qa/answers/999999", None, None
        elif "无记录的会话查询历史" in when:
            # 2026-10-11：原场景用「图谱空查」，但其依赖 Neo4j 运行（离线即 3001）——
            # 改用「历史空会话」（MySQL 依赖，空结果 2002 语义同等可验证）。
            method, path, payload, raw = "GET", "/api/history?session_id=S-BDD-NO-RECORD", None, None
        else:
            failed.append(name)
            print("  [?? ] %s —— When 未映射：%r" % (name, when))
            continue

        if raw is not None:
            r = client.post(path, content=raw, headers={"Content-Type": "application/json"})
        else:
            r = client.request(method, path, json=payload) if payload is not None \
                else client.get(path)

        # Then 映射：响应码 N ＋ HTTP 状态 M ／ 200 且不出现错误码
        m = re.search(r"响应码为 (\d+) 且 HTTP 状态为 (\d+)", then)
        if m:
            want_code, want_http = int(m.group(1)), int(m.group(2))
            ok = (r.status_code == want_http
                  and r.json().get("code") == want_code
                  and set(r.json().keys()) == {"code", "message"})
            detail = "HTTP %d code=%s" % (r.status_code, r.json().get("code"))
        elif "不出现错误码" in then:
            ok = r.status_code == 200 and "code" not in r.json()
            detail = "HTTP %d code%s" % (r.status_code, "在" if "code" in r.json() else "不在")
        else:
            ok, detail = False, "Then 未映射：%r" % then
        print("  [%s] %s（%s）" % ("OK " if ok else "FAIL", name, detail))
        if not ok:
            failed.append(name)

    print("-" * 78)
    if failed:
        print("结论：FAIL %d 场景——%s" % (len(failed), "；".join(failed)))
        return 1
    print("结论：%d 场景全部通过——BDD 试点闭环（形态可行，扩写见 README）。" % len(scenarios))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
