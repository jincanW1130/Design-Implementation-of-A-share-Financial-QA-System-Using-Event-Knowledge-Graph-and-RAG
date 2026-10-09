# -*- coding: utf-8 -*-
r"""按关键字读取整改后的关键产物读数（只读，不改盘）。

用法：python ...\看读数.py
"""
import json
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".git")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)


def main():
    report = os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "_全量", "v2.1_v1_2", "对照报告.md")
    text = open(report, encoding="utf-8").read()
    print("对照报告.md 字符数 = %d" % len(text))
    for kw in ("不能直接作为交付物", "2737", "1253", "passed\": 17", "未修复，等待作者裁定",
               "已被取代"):
        print("  %-24s 命中 %d 处" % (kw, len(re.findall(re.escape(kw), text))))

    metrics = json.load(open(os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "_全量", "v2.1_v1_2",
                                          "对照指标.json"), encoding="utf-8"))
    graph = metrics["v1_2"]["graph"]
    print("对照指标.json 的 v1_2.graph：")
    print("  nodes_total = %s；edges_total = %s；PARTICIPATES_IN = %s"
          % (graph["nodes_total"], graph["edges_total"],
             graph["edges_by_relation"]["PARTICIPATES_IN"]))
    print("  graph_check = %s" % json.dumps(graph["graph_check"], ensure_ascii=False))
    print("  event_time_null_count = %s" % graph["event_time_null_count"])
    print("对照指标.json 的时间覆盖（三层的两个口径）：")
    for layer, block in metrics["v1_2"]["time"].items():
        if not isinstance(block, dict):
            print("  %s = %r" % (layer, block))
            continue
        print("  %s：%s" % (layer, {k: v for k, v in block.items()
                                    if k.startswith("docs_")}))

    stats = json.load(open(os.path.join(ROOT, "交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出",
                                        "v2.1_v1_2", "graph_stats.json"), encoding="utf-8"))
    print("graph_stats.json：isolated_nodes.count=%r（%s）、ids 长度=%d；generated_at=%s"
          % (stats["isolated_nodes"]["count"], type(stats["isolated_nodes"]["count"]).__name__,
             len(stats["isolated_nodes"]["ids"]), stats["generated_at"]))

    verify = json.load(open(os.path.join(ROOT, "交付物/03-代码", "抽取与图谱", "_全量", "v2.1_v1_2",
                                         "verify.json"), encoding="utf-8"))
    repro = verify["reproducibility"]
    print("verify.json 复现性：runs=%s；documents=%s；compared_runs=%s；"
          "identical_across_runs=%s" % (repro["runs"], repro["documents"],
                                        repro["compared_runs"],
                                        repro["identical_across_runs"]))
    print("  compared_manifest_sha256=%s" % [h[:16] for h in repro["compared_manifest_sha256"]])
    return 0


if __name__ == "__main__":
    sys.exit(main())
