# -*- coding: utf-8 -*-
r"""临时工具：撤销中间轮次（预筛口径未修正的那一轮）写入的 raw 文件对应的日志行，
并把撤销动作本身登记成一行审计（用完删除）。

背景：第二轮运行时，候选阶段的判重预筛误把 v2.1 上一轮自己的产出当成"既有文档"，
于是为 44 家公司重新挑了一批**未选入过**的公告（id 1444、1594～1632），越过了
"每家新增公司最多 6 篇"的口径。这些文件已删除；此行把删除登记进 raw\\_fetch_log.jsonl，
使日志与 raw\\ 的文件集合保持一致（`v2.0` 的日志口径是"一行一次尝试"，故只删该轮的
成功行，首轮针对 1444 的失败行保留）。
"""
from __future__ import annotations

import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

RAW = os.path.join(r"C:\Users\15129\Desktop\毕业设计", "阶段05-数据准备", "数据集", "v2.1", "raw")
LOG = os.path.join(RAW, "_fetch_log.jsonl")
DROP = {1444} | set(range(1594, 1633))

kept, dropped = [], []
with open(LOG, "r", encoding="utf-8") as fh:
    for line in fh:
        if not line.strip():
            continue
        obj = json.loads(line)
        if (obj.get("doc_id") in DROP and obj.get("ok")
                and obj.get("category") == "公告"
                and (obj.get("fetched_at") or "") >= "2026-09-25T20:20"):
            dropped.append(obj)
            continue
        kept.append(line.rstrip("\n"))

note = ("v2.1 定向补样审计：撤销中间轮次的越界产出——第二轮运行时，候选阶段的判重预筛"
        "误把 v2.1 上一轮自己的产出当成既有文档，于是 44 家已选满的新增公司又被补选了一批"
        "未入池的公告（doc_id 1444、1594～1632），越过「每家新增公司最多 6 篇」的口径。"
        "该 39 个 raw 文件已删除，对应的 %d 行抓取成功记录也从本日志中撤下（保留首轮对 1444 "
        "的失败登记）；修正后的预筛只把**基座版本 v2.0** 的文档当作既有文档，v2.1 自身的"
        "产出照常参与重选、编号按 URL 复用——修正后重跑的选择结果与首轮逐篇一致。" % len(dropped))
kept.append(json.dumps({"doc_id": None, "category": "公告",
                        "source": "巨潮资讯网", "url": "https://www.cninfo.com.cn/",
                        "http_status": None, "ok": True, "chars": None, "byte_size": None,
                        "elapsed_ms": 0, "fetched_at": "2026-09-25T21:10:00+08:00",
                        "note": note}, ensure_ascii=False))

with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
    fh.write("\n".join(kept) + "\n")

files = {int(n[:-5]) for n in os.listdir(RAW) if n.endswith(".json") and not n.startswith("_")}
log_ids = {json.loads(x)["doc_id"] for x in open(LOG, encoding="utf-8") if x.strip()
           and json.loads(x).get("doc_id") is not None}
ok_ids = {json.loads(x)["doc_id"] for x in open(LOG, encoding="utf-8") if x.strip()
          and json.loads(x).get("ok") and json.loads(x).get("category") == "公告"
          and json.loads(x).get("doc_id") is not None}
print("撤下的日志行 %d 行；raw 文件 %d 个；日志行 %d 行（撤销后）"
      % (len(dropped), len(files), len(kept)))
print("raw 文件集合 ⊆ 日志 ok 公告 id 集合：%s；差集（应为空）=%s"
      % (files <= ok_ids, sorted(files - ok_ids)))
