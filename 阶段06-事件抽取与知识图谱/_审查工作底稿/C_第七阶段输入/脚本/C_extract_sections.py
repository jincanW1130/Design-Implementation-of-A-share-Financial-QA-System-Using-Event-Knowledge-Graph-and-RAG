# -*- coding: utf-8 -*-
"""C 审查（第 7 阶段设计输入侦察）—— 文档分节原文提取脚本。

只读既有文档，只写本产物目录下的 原始输出\\ 子目录。
按 Markdown 标题层级切节，逐节落盘为 UTF-8 文本，供逐字摘录与出处核对。
"""
from __future__ import annotations

import io
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "原始输出"))

TARGETS = [
    # (源文件相对路径, 输出名, 允许的标题前缀列表)
    ("02-项目执行总控文档.md", "02_总控", [
        "## 九、数据设计概要", "### 9.3 向量索引",
        "## 十、时间维度设计", "### 10.1 四种时间及其归属层级",
        "### 10.2 时间线示例与时间约束检索", "### 10.3 数据截止时间 data_cutoff_time",
        "## 十一、技术路线", "### 11.1 普通 RAG 流程", "### 11.2 KG-RAG 流程",
        "### 11.3 一次用户提问的完整执行流程", "### 11.4 整体技术路线",
        "### 11.5 开发纪律：必须先跑通普通 RAG，再加知识图谱",
        "## 十二、混合检索策略与实验方案", "### 12.1 检索策略分级", "### 12.2 测试集（多标签）",
        "### 12.3 抽取评测集", "### 12.4 实验配置固定表", "### 12.5 实验设置",
        "### 12.6 消融实验", "### 12.7 评价指标与定义", "### 12.8 图谱增强效果的判定规则",
        "### 12.9 定量实验问题与开放性问题的区分",
        "## 十三、最终回答形态与证据追溯",
        "## 十六、进度安排", "### 16.1 十二阶段总流程", "### 16.4 项目依赖顺序",
        "## 十七、数据\"先小后大\"推进策略",
        "## 二十、下一阶段待办",
    ]),
    ("阶段03-需求分析/07-需求分析（第三阶段）.md", "07_需求分析", [
        "### 1.3 需求来源清单",
        "### 3.1 编写口径与本体口径",
        "### 3.5 智能问答（FR-04）", "### 3.6 证据追溯（FR-05）", "### 3.7 历史问答（FR-06）",
        "### 3.8 功能需求汇总表",
        "#### UC-01 提交问题并获取答案", "#### UC-02 查看答案与证据来源",
        "#### UC-03 查看图谱（含多跳路径查询）",
        "### 5.7 非功能需求与论文第 6 章测试类型的对应关系",
        "### 7.2 需求追溯矩阵",
    ]),
    ("阶段04-系统总体设计/10-系统总体设计（第四阶段）.md", "10_总体设计", [
        "### 4.1 系统总体架构", "#### 4.1.1 六层架构图与部署形态",
        "#### 4.1.2 各层职责与层间调用关系", "#### 4.1.3 技术栈",
        "#### 4.1.4 架构对非功能需求的支撑",
        "#### 4.2.3 各模块的边界与不做的事",
        "### 4.4 数据库设计", "#### 4.4.1 字段级设计",
        "#### 4.4.2 历史证据保护与关键约束", "#### 4.4.5 四种时间的落点与相对时间判定",
        "#### 4.4.6 向量—原文三级映射链路", "#### 4.4.7 answer.graph_path 的存储形式与局限",
        "### 4.6 RAG 检索架构", "#### 4.6.1 检索管线的组件与数据流",
        "#### 4.6.2 Method 的配置", "#### 4.6.3 四级检索策略与预算相关的三个量",
        "#### 4.6.4 Top-K 证据集合的五步契约", "#### 4.6.5 上下文预算与固定裁剪规则的执行位置",
        "#### 4.6.6 证据融合与排序", "#### 4.6.7 A～E 五组的配置开关",
        "#### 4.6.8 Prompt 结构与版本管理", "#### 4.6.9 图谱路径的输出条件",
    ]),
    ("阶段05-数据准备/13-数据准备（第五阶段）.md", "13_数据准备", [
        "## 三、切分口径与参数", "### 3.1 固化参数（`config.CHUNK`，本阶段固化的 TBD 之二）",
        "### 3.2 编号规则（《12》第五节 硬约束 6、7、8）",
        "### 3.3 实测切分结果与长度分布",
        "## 四、向量化口径", "### 4.1 Embedding 模型与版本（本阶段固化的 TBD 之一）",
        "### 4.2 向量索引与三级映射链路", "### 4.3 本阶段向量化的边界",
        "## 五、数据字典", "### 5.1 `clean\\documents.jsonl`（一行一篇）→ `document` 表",
        "### 5.2 `chunks\\chunks.jsonl`（一行一个文本块）→ `document_chunk` 表",
        "### 5.3 数据集内部辅助文件（同样不入库）",
        "### 5.4 `company_list` 允许为空的类别与原因", "### 5.5 `url` 的取值与为空口径",
        "### 6.4 本阶段固化的三项 TBD 与保持 TBD 的四项",
        "### 6.5 版本不可变与升版规则", "### 6.8 数据集 v2.1（定向补样）",
        "## 九、对下游阶段的使用说明", "### 9.1 给第 6 阶段（事件抽取与知识图谱）",
        "### 9.1.1 语料对本体的覆盖性实测（补做《12》第三节 的检查项）",
        "### 9.2 给第 7 阶段（向量检索）", "### 9.3 给第 10 阶段（测试集与实验）",
        "### 9.4 各阶段通用纪律",
    ]),
    ("阶段06-事件抽取与知识图谱/16-事件抽取与知识图谱（第六阶段）.md", "16_事件抽取与知识图谱", [
        "### 1.4 与《02》第12.4节「实验配置固定表」的关系（边界说明）",
        "### 1.6 抽取规模、成本与异常读数",
        "### 3.4 核心关系分布（9 条，导出物口径）",
        "### 3.6 抽取层口径（含未写入图谱的条目）",
        "### 3.7 从抽取层到导出层的三条对账恒等式",
        "### 4.4 待消歧清单的构成（1070 条）",
        "### 5.4 去重的边界（如实登记）",
        "### 6.1 节点与编号", "### 6.2 边与证据属性", "### 6.3 四件导出物",
        "### 6.4 时间属性的落点（《10》第4.5.6节）", "### 6.5 重放与核对命令",
        "### 6.6 人工确认的实体写入图谱（HCONF-####）",
        "## 七、评测集构成与分层依据", "### 7.1 规模与两段式", "### 7.2 分层配额（类目 × 月份 × 公司）",
        "### 7.3 分层容差与逐项差异登记", "### 7.6 标注状态（交付池子 ＋ 独立自动标注产物）",
        "### 7.7 已登记的八项偏离",
        "## 八、已知限制与证据不足清单", "### 8.1 event_time 空值 544／1100（49.5%）：T3 的 717 条里 173 条已由 T3.5 补出日期",
        "### 8.2 CUSTOMER_OF 已由人工确认写入 10 条（曾经为 0 条），仍属很薄的关系",
        "### 8.3 BELONGS_TO 的 valid_from／valid_to 14／14 全为空",
        "### 8.4 公司提及消歧率 41.4%（自动匹配）、跳过 878 条边、435 个孤立节点、1070 条待消歧",
        "### 8.5 拒绝 82 条的分布与含义",
        "### 8.6 SUPPLIES 0／COMPETES_WITH 1／CUSTOMER_OF 4 仍然很薄",
        "### 8.7 其他如实登记的边界", "### 8.8 证据不足登记（评测集口径：8 种事件类型 ＋ 9 条核心关系）",
        "### 8.9 模型自动标注（模型参照集）：不是金标准，未人工复核",
        "### 8.10 三个第三方模型的独立复核（40 条抽检样本）——2026-09-27 增补（v1.8）",
        "## 九、对下游的使用说明", "### 9.1 给第 7 阶段（向量检索与图谱查询）",
        "### 9.2 给第 10 阶段（抽取评测集与实验）", "### 9.3 通用纪律",
        "### 9.4 第 10 阶段时间过滤组（D／E）的可测性前置条件",
    ]),
]


def split_sections(text: str):
    lines = text.split("\n")
    heads = []
    for idx, line in enumerate(lines):
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            title = line.strip()
            heads.append((idx, level, title))
    return lines, heads


def extract(path: str, prefixes):
    with io.open(path, encoding="utf-8") as fh:
        text = fh.read()
    lines, heads = split_sections(text)
    out = []
    for idx, level, title in heads:
        if any(title.startswith(p) or p.startswith(title) for p in prefixes):
            end = len(lines)
            for jdx, jlevel, jtitle in heads:
                if jdx > idx and jlevel <= level:
                    end = jdx
                    break
            body = "\n".join(lines[idx:end]).rstrip()
            out.append((title, body, idx + 1, end))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    index_lines = []
    for rel, tag, prefixes in TARGETS:
        src = os.path.join(ROOT, rel.replace("/", os.sep))
        sections = extract(src, prefixes)
        chunks = []
        chunks.append("# 源文件：%s" % rel)
        chunks.append("# 提取方式：按 Markdown 标题匹配（整节含子节，至同级或更高级标题为止）")
        chunks.append("")
        for title, body, l0, l1 in sections:
            chunks.append("=" * 100)
            chunks.append("## 节标题：%s" % title)
            chunks.append("## 原文行号：第 %d 行 至 第 %d 行" % (l0, l1))
            chunks.append("=" * 100)
            chunks.append(body)
            chunks.append("")
            index_lines.append("%s\t%s\t%d-%d" % (rel, title, l0, l1))
        dst = os.path.join(OUT, "raw_%s.md" % tag)
        with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(chunks))
        print("[ok] %s -> %s   节数=%d" % (rel, os.path.relpath(dst, ROOT), len(sections)))
    with io.open(os.path.join(OUT, "索引_已提取节清单.tsv"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("源文件\t节标题\t原文行号\n")
        fh.write("\n".join(index_lines))
        fh.write("\n")
    print("[ok] 索引_已提取节清单.tsv 条数=%d" % len(index_lines))


if __name__ == "__main__":
    main()
