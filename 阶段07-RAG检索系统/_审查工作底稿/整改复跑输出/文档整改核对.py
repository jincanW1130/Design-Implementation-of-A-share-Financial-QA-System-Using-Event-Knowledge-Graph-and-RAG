# -*- coding: utf-8 -*-
"""生成 A／C 线文档整改的只读核对摘要。"""

from __future__ import annotations

import collections
import datetime
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent / "文档整改核对.txt"


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def line_numbers(rel: str, needle: str):
    return [i for i, line in enumerate(read(rel).splitlines(), 1) if needle in line]


def section(rel: str, start: str, end: str) -> str:
    text = read(rel)
    a = text.index(start)
    b = text.index(end, a)
    return text[a:b]


def main() -> int:
    rows = []
    add = rows.append
    add("文档整改核对（只读生成，%s）" % datetime.datetime.now().isoformat())
    add("=" * 78)

    src = "阶段04-系统总体设计/_分节源文件/4.6-RAG检索架构.md"
    doc10 = "阶段04-系统总体设计/10-系统总体设计（第四阶段）.md"
    add("[A-01] 源文件 g≥1／可检验性／PE-26 行号=%s／%s／%s；《10》=%s／%s／%s；"
        "《10》SHA256=%s"
        % (line_numbers(src, "g ≥ 1"), line_numbers(src, "可检验性属设计约束"),
           line_numbers(src, "PE-26 gold"), line_numbers(doc10, "g ≥ 1"),
           line_numbers(doc10, "可检验性属设计约束"), line_numbers(doc10, "PE-26 gold"),
           hashlib.sha256((ROOT / doc10).read_bytes()).hexdigest()))
    add("[A-02] 04开题 v3.2 行号=%s"
        % line_numbers("阶段02-文献调研与开题/04-开题报告.md", "《02》第12.7节 **v3.2**"))
    add("[A-03] 18 版本链 v3.2 行号=%s；07 版本链 v3.2 行号=%s"
        % (line_numbers("阶段06-事件抽取与知识图谱/18-第7阶段任务书（RAG检索系统）.md",
                        "v3.2 为 g 的选择规则加下限 1"),
           line_numbers("阶段03-需求分析/07-需求分析（第三阶段）.md",
                        "v3.2 为 g 的选择规则加下限 1")))
    add("[A-04] README 三层行号=%s／%s／%s；g=2／g≥1 行号=%s／%s"
        % (line_numbers("代码/检索/README.md", "**第一层**"),
           line_numbers("代码/检索/README.md", "**第二层**"),
           line_numbers("代码/检索/README.md", "**第三层**"),
           line_numbers("代码/检索/README.md", "现行 **g = 2**"),
           line_numbers("代码/检索/README.md", "选择规则含下限 **g ≥ 1**")))
    add("[A-05] 第二层并列规则行号：README=%s、config=%s、18=%s"
        % (line_numbers("代码/检索/README.md", "并列按"),
           line_numbers("代码/检索/config.py", "并列按 chunk_id 升序"),
           line_numbers("阶段06-事件抽取与知识图谱/18-第7阶段任务书（RAG检索系统）.md",
                        "并列按")))
    t18 = read("阶段06-事件抽取与知识图谱/18-第7阶段任务书（RAG检索系统）.md")
    sec42 = section("阶段06-事件抽取与知识图谱/18-第7阶段任务书（RAG检索系统）.md",
                    "### 4.2 代码产出", "### 4.3 检索产出与预实验记录")
    sec43 = section("阶段06-事件抽取与知识图谱/18-第7阶段任务书（RAG检索系统）.md",
                    "### 4.3 检索产出与预实验记录", "### 4.4 预实验问题集")
    add("[A-06] 4.2 代码产出表行数=%d（目标 11）；4.3 产出表行数=%d（目标 6）；"
        "check_inputs／third_party_review／input_manifest 全文存在=%s／%s／%s"
        % (sum(1 for line in sec42.splitlines()
               if line.startswith("| 代码\\检索\\")),
           sum(1 for line in sec43.splitlines()
               if line.startswith("| ") and any(
                   name in line for name in ("input_manifest", "pre_experiment_matrix",
                                             "k_selection", "per_question_trace",
                                             "metrics_pre", "run_manifest"))),
           "check_inputs.py" in t18, "third_party_review.py" in t18,
           "input_manifest.json" in t18))
    add("[A-07] 门禁扫描范围、六张表白名单、正对照与 static 未执行计数见 full/static 原始输出。")
    add("[A-08] 19 限制索引行号=%s"
        % line_numbers("阶段07-RAG检索系统/19-第7阶段产出文档（RAG检索系统）.md",
                       "继承第 8 节第 1～9 条限制"))
    add("[A-09] 19 限定语行号=%s；02 补注行号=%s"
        % (line_numbers("阶段07-RAG检索系统/19-第7阶段产出文档（RAG检索系统）.md",
                        "第一轮非约束预算下的读数"),
           line_numbers("02-项目执行总控文档.md", "读数口径补注（2026-09-28 整改登记")))
    add("[A-10] 19 镜像数行号=%s"
        % line_numbers("阶段07-RAG检索系统/19-第7阶段产出文档（RAG检索系统）.md",
                       "镜像根目录含 **54 个文件**"))
    add("-" * 78)

    qs = [json.loads(line) for line in
          read("阶段07-RAG检索系统/预实验问题集/questions.jsonl").splitlines()
          if line.strip()]
    dist = collections.Counter(len(q["gold_evidence_chunk_ids"]) for q in qs)
    add("[C-D1] 实际 gold 分布=%s；说明已同步=%s；模板已同步=%s"
        % (dict(sorted(dist.items())),
           "2 条 10 题、3 条 3 题、4 条 2 题"
           in read("阶段07-RAG检索系统/预实验问题集/说明.md"),
           "2 条 ×10、3 条 ×3、4 条 ×2"
           in read("阶段07-RAG检索系统/预实验问题集/题目模板.md")))
    add("[C-D2] 说明现行复核字段=%s；模板现行复核字段=%s"
        % ("third_party_model_review_v1"
           in read("阶段07-RAG检索系统/预实验问题集/说明.md"),
           "third_party_model_review_v1"
           in read("阶段07-RAG检索系统/预实验问题集/题目模板.md")))
    add("[C-D3] 说明明示候选口径=%s；模板明示候选口径=%s；字段样例=%r"
        % ("`gold_evidence_rule` 字段的口径"
           in read("阶段07-RAG检索系统/预实验问题集/说明.md"),
           "记的是候选抽取口径"
           in read("阶段07-RAG检索系统/预实验问题集/题目模板.md"),
           qs[0].get("gold_evidence_rule")))
    t12 = ROOT / "阶段07-RAG检索系统/_工作底稿/_T12"
    add("[C-D5] full/static/keep-tmp 日志存在=%s／%s／%s"
        % ((t12 / "验收第7阶段_full_stdout.txt").exists(),
           (t12 / "验收第7阶段_static_stdout.txt").exists(),
           (t12 / "验收第7阶段_keep-tmp_stdout.txt").exists()))
    pe13 = next(q for q in qs if q["qid"] == "PE-13")["gold_evidence_chunk_ids"]
    pe22 = next(q for q in qs if q["qid"] == "PE-22")["gold_evidence_chunk_ids"]
    add("[C-D6] PE-13／PE-22 保留依据=%s；gold 仍含 1279000／1274001=%s／%s"
        % ("PE-13" in read("阶段07-RAG检索系统/预实验问题集/说明.md")
           and "PE-22" in read("阶段07-RAG检索系统/预实验问题集/说明.md"),
           1279000 in pe13, 1274001 in pe22))

    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print("\n".join(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
