# -*- coding: utf-8 -*-
r"""交付物/03-代码\测试\smoke\冒烟.py —— 独立冒烟层（2026-10-11，对应审查报告 S10）。

为什么要有这个文件（S10 的问题）
--------------------------------
`交付物/05-系统实现/前后端系统集成/集成产出/smoke_matrix.jsonl`（44 行）是第 11 阶段
验收时的一次性留痕：重放它必须整跑验收第 9 阶段 full 档（需要服务＋Neo4j＋Docker），
日常变更后没有 5 分钟级的 GO/NO-GO 手段。本脚本把 12 条**只读、无副作用**的探针
（health／qa／history／evidence／graph／config／前端探活）从该矩阵抽出固化，
**每条都带基线行追溯**（注明来自 smoke_matrix.jsonl 的哪一行读数或门禁哪一组），
变更后跑一遍即可判活。

使用
----
    python "交付物/03-代码\测试\smoke\冒烟.py"            # 后端 8000 ＋ 前端 5173
    python "交付物/03-代码\测试\smoke\冒烟.py" --backend http://127.0.0.1:8000 --frontend http://127.0.0.1:5173

* 全部通过 → 打印 GO，退出码 **0**；
* 任一失败 → 打印 NO-GO 与失败清单，退出码 **1**（kill MySQL／Neo4j／前端任一依赖，
  相应探针如实变红，整体 NO-GO——依赖故障不被放行）；
* 后端完全不可达 → 全部 NO-GO，并提示启动命令。

设计纪律
--------
* **只读**：12 条探针全部不写库、不触发问答链路、不写任何文件（qa 只打错误码探针，
  在校验层即被拒，不 fork 子进程）；admin 全部不进本层（写库／触发计费的探针属验收重武器）。
* **零第三方依赖**：只用标准库 urllib，任何装了 Python 的机器都能跑（运维手边工具）。
* **判据从宽**：只判「服务活着＋响应结构在」，不断言具体计数（历史条数等会随使用增长，
  精确对拍是验收第 9 阶段的职责）；每条的**首次基线读数**以注释形式逐条保留。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT_SECONDS = 10.0
"""单条探针的 HTTP 超时（秒）。"""

# --------------------------------------------------------------------------
# 探针：12 条只读探针，每条带基线追溯（baseline 注释 = smoke_matrix.jsonl 原始读数
# 或 验收第9阶段.py 对应组的判据），改动判据须同步更新基线说明。
# --------------------------------------------------------------------------
PROBES = [
    {
        "name": "01 health 就绪探针（status＋四依赖键）",
        "method": "GET", "path": "/api/health",
        "baseline": "基线：验收第9阶段 A5（门禁）；响应键恰为 {status, mysql, neo4j, "
                    "vector_index, model_config}，HTTP 恒 200",
        "check": lambda st, body: (
            st == 200
            and isinstance(body, dict)
            and set(body) >= {"status", "mysql", "neo4j", "vector_index", "model_config"}
            and body.get("status") in ("ok", "degraded")),
        "check_note": "HTTP 200 且五键齐、status ∈ {ok, degraded}",
    },
    {
        "name": "02 config/meta 只读口径",
        "method": "GET", "path": "/api/config/meta",
        "baseline": "基线：smoke_matrix 行「dataset=v2.1 K=10 N=20 模型=deepseek-flash」",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and body["data"].get("dataset_version") == "v2.1"
            and isinstance(body.get("meta"), dict)),
        "check_note": "HTTP 200、data.dataset_version=v2.1、meta 区块在",
    },
    {
        "name": "03 qa/answers 取回既有回答",
        "method": "GET", "path": "/api/qa/answers/1",
        "baseline": "基线：smoke_matrix 行「answer_id=1 证据=10 条」",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and int(body["data"].get("answer_id") or 0) == 1
            and isinstance(body["data"].get("evidence"), list)),
        "check_note": "HTTP 200、data.answer_id=1、evidence 为列表",
    },
    {
        "name": "04 qa/answers 不存在的资源 → 2001",
        "method": "GET", "path": "/api/qa/answers/999999",
        "baseline": "基线：smoke_matrix 错误码行「code=2001 message=资源不存在」",
        "check": lambda st, body: st == 404 and isinstance(body, dict) and body.get("code") == 2001,
        "check_note": "HTTP 404、code=2001、键集合恰 {code, message}",
    },
    {
        "name": "05 qa/ask 缺必填 → 1003（校验层即拒，不触发链路）",
        "method": "POST", "path": "/api/qa/ask", "payload": {"question": "冒烟探针"},
        "baseline": "基线：smoke_matrix 错误码行「缺 session_id code=1003」"
                    "（2026-10-11 S6 修复后「缺 question」同为 1003，本探针即覆盖该分叉）",
        "check": lambda st, body: st == 400 and isinstance(body, dict) and body.get("code") == 1003,
        "check_note": "HTTP 400、code=1003",
    },
    {
        "name": "06 history 按会话列表",
        "method": "GET", "path": "/api/history?session_id=S-001&page_size=5",
        "baseline": "基线：smoke_matrix 行「session=S-001 total=30」（计数随使用增长，"
                    "冒烟只判结构：HTTP 200 ＋ total 为非负整数）",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and isinstance(body["data"].get("total"), int)
            and body["data"]["total"] >= 0
            and isinstance(body["data"].get("items"), list)),
        "check_note": "HTTP 200、data.total 为非负整数、items 为列表",
    },
    {
        "name": "07 history 回看单条",
        "method": "GET", "path": "/api/history/1?session_id=S-001",
        "baseline": "基线：smoke_matrix 行「question_id=1 answer_id=1」",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and int(body["data"].get("question_id") or 0) == 1),
        "check_note": "HTTP 200、data.question_id=1",
    },
    {
        "name": "08 evidence 证据分组",
        "method": "GET", "path": "/api/evidence/1",
        "baseline": "基线：smoke_matrix 行「answer_id=1 分组={回答来源0,新闻来源0,公告来源8,"
                    "相关事件2} 条目=10」",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and "items" in body["data"]),
        "check_note": "HTTP 200、data 含 items（计数不精确对拍）",
    },
    {
        "name": "09 evidence 图谱路径载荷",
        "method": "GET", "path": "/api/evidence/1/graph-path",
        "baseline": "基线：smoke_matrix 行「answer_id=1 图谱扩展=1 路径数=4」",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and "is_graph_extended" in body["data"]),
        "check_note": "HTTP 200、data 含 is_graph_extended",
    },
    {
        "name": "10 graph/entities 实体检索",
        "method": "GET", "path": "/api/graph/entities?keyword=%E5%B9%B3%E5%AE%89&page_size=2",
        "baseline": "基线：smoke_matrix 行「total=21 首条 node_id=000001」（计数随图谱版本，"
                    "冒烟只判结构）",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)
            and isinstance(body["data"].get("total"), int)
            and body["data"]["total"] >= 0),
        "check_note": "HTTP 200、data.total 为非负整数",
    },
    {
        "name": "11 market/reports 语料内源（无外部网络依赖）",
        "method": "GET", "path": "/api/market/reports",
        "baseline": "新增探针（2026-10-11 S10）：实时区语料内源直查 document 表，"
                    "不依赖外部行情源，可作纯本机判活项",
        "check": lambda st, body: (
            st == 200 and isinstance(body, dict)
            and isinstance(body.get("data"), dict)),
        "check_note": "HTTP 200、data 为对象",
    },
    {
        "name": "12 前端 dev 探活",
        "method": "GET", "path": "/",
        "frontend": True,
        "baseline": "新增探针（2026-10-11 S10）：完整形态含前端（5173 dev server）；"
                    "该条失败说明前端未启动，整体 NO-GO",
        "check": lambda st, body: st == 200,
        "check_note": "HTTP 200（index.html）",
    },
]


def _request(base: str, method: str, path: str, payload=None):
    """发一次请求，返回 (http_status, 解析后的 body 或原文, 错误摘要或 None)。"""
    url = base.rstrip("/") + path
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as exc:                      # 4xx/5xx 也算「有响应」
        raw = exc.read().decode("utf-8", errors="replace")
        status = exc.code
    except Exception as exc:                                   # 连接拒绝／超时 → 无响应
        return None, None, "%s: %s" % (type(exc).__name__, exc)
    try:
        return status, json.loads(raw), None
    except ValueError:
        return status, raw, None                               # 非 JSON（前端 index.html）


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="独立冒烟：12 条只读探针（S10）")
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    parser.add_argument("--frontend", default="http://127.0.0.1:5173")
    args = parser.parse_args(argv)

    print("=" * 78)
    print("独立冒烟（S10）—— 12 条只读探针；GO/NO-GO 判活，不做精确对拍")
    print("后端 %s ｜ 前端 %s" % (args.backend, args.frontend))
    print("=" * 78)

    started = time.time()
    failed, backend_down, executed = [], False, 0
    for probe in PROBES:
        base = args.frontend if probe.get("frontend") else args.backend
        status, body, err = _request(base, probe["method"], probe["path"],
                                     probe.get("payload"))
        if status is None:
            if not probe.get("frontend"):
                backend_down = True
            ok, detail = False, "无响应（%s）" % err
        else:
            executed += 1                                  # N5（复评）：按实际执行计数
            try:
                ok = bool(probe["check"](status, body))
                detail = "HTTP %s" % status
            except Exception as exc:                       # 判据函数自身异常按失败计
                ok, detail = False, "判据异常 %s: %s" % (type(exc).__name__, exc)
        mark = "GO " if ok else "NO-GO"
        print("  [%s] %s（%s；%s）" % (mark, probe["name"], detail, probe["check_note"]))
        if not ok:
            failed.append(probe["name"])
        if backend_down:
            break                                          # 后端不可达，后续探针必然全红
    elapsed = time.time() - started

    print("-" * 78)
    if backend_down:
        print("NO-GO：后端 %s 不可达——先启动后端：" % args.backend)
        print("    python \"交付物/03-代码\\后端\\run.py\"    （前端：npm run dev）")
        print("（%d 条探针中已执行 %d 条，其余因后端不可达未执行）" % (len(PROBES), executed))
        return 1
    if failed:
        print("NO-GO：%d/%d 条探针失败——" % (len(failed), len(PROBES)))
        for name in failed:
            print("    - %s" % name)
        print("依赖排障顺序：MySQL（health.mysql）→ Neo4j（health.neo4j）→ 前端 dev server。")
        return 1
    print("GO：%d/%d 条探针全部通过（耗时 %.1fs）——服务判活。"
          % (len(PROBES), len(PROBES), elapsed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
