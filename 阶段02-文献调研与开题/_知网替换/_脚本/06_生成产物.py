# -*- coding: utf-8 -*-
"""生成 _知网替换/ 下的 5 个交付物与 _验证输出/ 附件。

输出：
- 替换方案.md / 替换方案.csv（UTF-8 带 BOM）/ 候选题录.jsonl（UTF-8 无 BOM）
- 下载清单.md / 核验报告.md（第九节由 07_追加验证输出.py 追加）
- _脚本/_验证输出/01_逐条核实结果表.md、02_引用片段对照.md、03_归档池资产清单.md、05_证据文件清单.txt
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _数据_22条 import ITEMS, TABLE_FIELDS  # noqa: E402
from _数据_引文片段 import QUOTES  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTDIR = BASE
SCRIPT_DIR = os.path.join(BASE, "_脚本")
VO = os.path.join(SCRIPT_DIR, "_验证输出")

ORDER = [
    "KG-5", "KG-9", "KG-16", "KG-17", "KG-19", "KG-21", "KG-28", "KG-29",
    "RAG-1", "RAG-9", "RAG-10", "RAG-11", "RAG-13", "RAG-24",
    "FIN-3", "FIN-16", "FIN-17", "FIN-20",
    "SYS-4", "SYS-8", "SYS-13", "SYS-14",
]

DIRNAME = {
    "KG": "知识图谱（KG）",
    "RAG": "RAG",
    "FIN": "金融问答（FIN）",
    "SYS": "软件系统（SYS）",
}

BREAK_DOWN = {
    "KG-5": ("建议改选", "候选只覆盖 KG 推理方法，撑不住\"两阶段图检索\"落点；池内 KG-7 更贴合"),
    "KG-9": ("可采纳（须改写口径）", "支持\"国内大模型金融事件抽取\"，不能替代 Doc2EDAG 的文档级方法先例"),
    "KG-16": ("可采纳（须改写口径）", "支持篇章级抽取方法，基准规模与 F1 数据仍须引 DocEE"),
    "KG-17": ("可采纳（须改写口径）", "支持中文金融篇章级系统实现，基准数据仍须引 DocEE-zh"),
    "KG-19": ("可采纳（须补英文）", "支持事件共指消解一点，四类关系建模仍须引 MAVEN-ERE"),
    "KG-21": ("保留", "已是中文，上轮已核验"),
    "KG-28": ("保留", "已是中文，上轮已核验"),
    "KG-29": ("不建议单用（对原论据疑似不相关）", "不含\"通用链接器不适配专有实体\"的工业实践证据；须保留 JEL"),
    "RAG-1": ("可采纳（须补英文）", "可作中文综述，Lewis 2020 仍是框架源头"),
    "RAG-9": ("可采纳（须补英文）", "可作国内 GraphRAG 多跳进展，差异论证仍须引 Edge 2024"),
    "RAG-10": ("可采纳（须补英文）", "可作国内 KG 多跳问答进展，PPR 机制仍须引 HippoRAG"),
    "RAG-11": ("不建议采纳（对原论点疑似不相关）", "方法优化文，不含评估指标体系；建议保留 RAGAS"),
    "RAG-13": ("可采纳（须补英文）", "可作国内 RAG 问答方法，支撑事实标注仍须引 HotpotQA"),
    "RAG-24": ("可采纳（须补英文）", "可作国内幻觉识别与信任度研究，原子事实口径仍须引 FActScore"),
    "FIN-3": ("可采纳（须补英文）", "可作国内金融 RAG 问答进展，基准规模仍须引 FinanceBench"),
    "FIN-16": ("可采纳（须补英文）", "可作国内时序 KGQA 进展，基准与退化结论仍须引 CronKGQA"),
    "FIN-17": ("可采纳（须改写口径＋补英文）", "时序 KG 推理的周期建模，不含问答与时间约束检索；TempoQR 须保留"),
    "FIN-20": ("建议谨慎（须辅以 HalluBench）", "金融 KG 问答系统实例，不含幻觉基准与证据链协议"),
    "SYS-4": ("不建议采纳（对原论点疑似不相关）", "不含软件分层架构论证；建议改选池内 SYS-2/SYS-16/SYS-18"),
    "SYS-8": ("可采纳（须改写口径＋补英文）", "Hybrid RAG 跨领域实例，金融场景可行性仍须引 Sarmah 2024"),
    "SYS-13": ("可采纳但须更正题名", "表中题名漏\"肺癌\"；口径改为国内 RAG 效能评估实践"),
    "SYS-14": ("可采纳（须改写口径＋补英文）", "KG 路径推理检索引擎实例，多存储协同仍须引 HetaRAG"),
}

FOUNDATION = [
    ("RAG-1", "RAG 原始论文（Lewis 等，NeurIPS 2020）", "RAG 框架源头；\"参数化＋非参数化记忆\"的史实性论断", "《检索增强生成综述：方法与应用》（中文综述，仅支撑国内进展）"),
    ("KG-9", "Doc2EDAG（Zheng 等，EMNLP-IJCNLP 2019）", "中文金融文档级事件抽取的方法先例（EDAG 事件表）", "《基于多维指令集微调的大语言模型金融事件抽取》（同类任务新方法）"),
    ("KG-16", "DocEE（Tong 等，NAACL-HLT 2022）", "文档级抽取的规模、细粒度标注与 F1/人工对比基准", "《基于跨度和网络结构的篇章级事件抽取研究》（硕士学位论文，方法类）"),
    ("KG-17", "DocEE-zh（Liu 等，Findings of EMNLP 2024）", "中文标注规范与规模数据（3.6 万事件、F1 45.88）", "《基于自适应GNN的篇章级金融事件抽取系统研究与实现》（系统实现类）"),
    ("KG-19", "MAVEN-ERE（Wang 等，EMNLP 2022）", "四类事件关系统一标注框架与规模化数据", "《外部知识增强的事件共指消解方法》（只覆盖共指一点）"),
    ("RAG-9", "GraphRAG（Edge 等，arXiv:2404.16130, 2024）", "图 RAG 开创；社区摘要→全局摘要而非可核查证据", "《融合双驱动检索与结构安全增强的GraphRAG多跳推理方法研究》（硕士论文）"),
    ("RAG-10", "HippoRAG（Gutierrez 等，NeurIPS 2024）", "海马体索引＋个性化 PageRank 的一次遍历多跳检索", "《基于图神经网络推理的知识图谱多跳问答方法研究》（GNN 路线，机制不同）"),
    ("RAG-11", "Ragas（Es 等，arXiv:2309.15217, 2023）", "无须参考答案的 RAG 指标体系（Faithfulness 等）", "中文池内无评估指标体系类文献；候选为分块/检索方法文"),
    ("RAG-13", "HotpotQA（Yang 等，EMNLP 2018）", "\"问题—答案—支撑事实\"标注范式与证据召回口径", "《基于检索增强的大语言模型问答方法研究》（博士论文，方法类）"),
    ("RAG-24", "FActScore（Min 等，EMNLP 2023）", "原子事实粒度的事实精度与自动评测器", "《AIGC嵌入图书馆知识发现服务的幻觉识别与信任度测量》（口径不同）"),
    ("FIN-3", "FinanceBench（Islam 等，arXiv 2023）", "金融披露文件问答基准（10,231 问答对＋证据链）", "《基于检索增强生成的金融智能问答方法研究》（硕士论文，方法类）"),
    ("FIN-16", "CronKGQA/CRONQUESTIONS（Saxena 等，ACL-IJCNLP 2021）", "时序 KGQA 基准、带有效时间区间的边、静态方法退化结论", "《基于多粒度隐含时态感知的时序知识图谱问答研究》（硕士论文）"),
    ("FIN-17", "TempoQR（Mavromatis 等，AAAI 2022）", "时间约束下的问题分解与稀疏子图检索", "《SARIMA嵌入的时序知识图谱推理》（推理建模，非问答）"),
    ("FIN-20", "HalluBench（Kumar 等，arXiv:2603.20252, 2026）", "金融 RAG 幻觉基准与\"文本块＋三元组\"证据链协议", "《一种基于扩散模型和知识图谱的智能金融问答系统的关键技术研究》（系统类）"),
    ("SYS-4", "Zhang 等 2024 LLM 软件分层架构（arXiv:2411.12357）", "模型层/推理层/应用层的分层职责与能力扩展论证", "中文池内无对口的 LLM 分层架构文献"),
    ("SYS-8", "HybridRAG（Sarmah 等，arXiv:2408.04948, 2024）", "金融文本上向量＋图谱双路拼接的工程可行性", "《基于Hybrid RAG的LLM水产营养推荐架构》（跨领域迁移）"),
    ("SYS-13", "RAGPerf（Li 等，PVLDB 2026）", "五组件可配置的端到端 RAG 基准与资源指标", "《融合检索增强生成技术的国产轻量化大语言模型在肺癌专科问题解答中的效能评估》（评估实践）"),
    ("SYS-14", "HetaRAG（Yan 等，arXiv:2509.21336, 2025）", "四类异构检索范式权衡与多存储协同编排", "《基于知识图谱路径推理和大模型的电力智能检索引擎》（不含多存储编排）"),
]

BETTER = [
    ("KG-7", "知识关联视角下金融证券知识图谱构建与相关股票发现（数据分析与知识发现, 2022, 6(2/3): 184-201）", "直接面向 A 股上市公司、融合结构化股票数据与文本抽取；若替换 KG-5，可同时覆盖\"金融 KG 构建\"与\"中文语料\"两个落点，比现候选（KG 推理方法）更贴题", "否"),
    ("KG-26", "面向金融知识图谱的动态关系预测方法研究（数据分析与知识发现, 2023, 7(9): 39-50）", "金融 KG 的关系/动态建模，可作 KG-5 的补充或替代", "否"),
    ("KG-20", "事理图谱研究综述（计算机工程与应用, 2026, 62(13): 68-86）", "事件关系（事理）建模综述，可补 KG-19 的\"事件关系\"落点", "否"),
    ("KG-24", "大语言模型增强的知识图谱问答研究进展综述（计算机科学与探索, 2024, 18(11): 2887-2900）", "综述型文献、权威性高于硕士学位论文，适合替换 RAG-10，并可与 HippoRAG 并列引用", "否"),
    ("RAG-15", "面向大语言模型生成能力提升的检索增强生成研究进展（软件学报）", "《软件学报》（CCF A 中文期刊）RAG 综述，作者权威性明显高于现候选（RAG-1 候选为 2026 年普通期刊综述），宜优先用于\"国内研究现状\"", "否"),
    ("RAG-19", "图检索增强生成研究综述（人工智能与机器人研究, 2025, 14(2): 402-413）", "图 RAG 综述，可替代 RAG-9 的硕士论文候选作\"GraphRAG 家族\"中文综述支撑", "否"),
    ("RAG-26", "大语言模型幻觉研究综述（人工智能与机器人研究, 2026, 15(1): 156-167）", "贴题度高于 RAG-24 现候选（图书馆服务场景），适合支撑\"幻觉识别与抑制\"", "否"),
    ("FIN-23", "基于大语言模型的财务报告指标抽取智能体方法（人工智能与机器人研究, 2025, 14(6): 1361-1371）", "财务报告信息抽取＋LLM，与 FIN-3 的\"披露文件问答\"落点相邻且更贴中文语料", "否"),
    ("FIN-24", "面向金融决策支持的知识获取研究综述（信息资源管理学报, 2020, 10(3): 27-35）", "金融知识获取综述（CSSCI 期刊），可支撑 FIN-3/FIN-20 的\"金融信息获取与证据\"论述", "否"),
    ("SYS-2", "基于Langchain-LLMs框架的智能问答系统的设计与实现（延边大学硕士学位论文, 2024）", "问答系统的框架选型与分层实现，更贴合 SYS-4 的\"软件系统分层架构\"落点", "否"),
    ("SYS-16", "基于大语言模型的知识图谱构建及应用研究（计算机科学与探索, 2024, 18(10): 2656-2667）", "LLM＋KG 系统构建，可比 SYS-4 现候选（水利双向赋能）更泛化", "否"),
    ("SYS-18", "融合知识图谱和大模型的高校科研管理问答系统设计（计算机科学与探索, 2025, 19(1): 107-117）", "KG＋LLM 问答系统的设计实现，可支撑 SYS-8/SYS-14 的系统实现论述", "否"),
    ("SYS-5", "基于大模型检索增强生成的计算机网络实验课程问答系统设计与实现（实验技术与管理, 2024, 41(12): 186-192）", "RAG 问答系统落地与评测，可作 SYS-13 的补充实例", "否"),
    ("FIN-21", "知识图谱视角下我国股票市场风险传染研究（运筹与管理, 2024, 33(2): 151-157）", "A 股市场 KG 应用（CSSCI），可支撑\"A 股财经 KG 有用性\"论述", "否"),
]

SHORT_NAMES = {
    "KG-5": "KG-5_Liu2026_AttentionKGReasoning.pdf",
    "KG-9": "KG-9_Yang2026_LLMFinEventExtraction.pdf",
    "KG-16": "KG-16_Niu2026_SpanNetworkDocEE.pdf",
    "KG-17": "KG-17_Liao2025_AdaptiveGNNDocEE.pdf",
    "KG-19": "KG-19_Xu2025_ExternalKnowledgeEventCoref.pdf",
    "KG-29": "KG-29_Han2025_OSINTEntityLinkingReview.pdf",
    "RAG-1": "RAG-1_Wang2026_RAGSurvey.pdf",
    "RAG-9": "RAG-9_Chen2026_GraphRAGMultiHop.pdf",
    "RAG-10": "RAG-10_Wang2026_GNNKGMultiHopQA.pdf",
    "RAG-11": "RAG-11_Juan2026_TextGraphHierarchicalRAG.pdf",
    "RAG-13": "RAG-13_He2026_RAGLLMQA.pdf",
    "RAG-24": "RAG-24_Xuan2026_AIGCHallucination.pdf",
    "FIN-3": "FIN-3_Feng2026_FinRAGQA.pdf",
    "FIN-16": "FIN-16_Fang2026_TemporalKGQA.pdf",
    "FIN-17": "FIN-17_Wu2026_SARIMATKG.pdf",
    "FIN-20": "FIN-20_Zhai2025_DiffusionKGFinQA.pdf",
    "SYS-4": "SYS-4_Qian2026_WaterKGLLM.pdf",
    "SYS-8": "SYS-8_Gao2026_HybridRAGAquatic.pdf",
    "SYS-13": "SYS-13_Ren2026_LightLLMRAGEval.pdf",
    "SYS-14": "SYS-14_Xue2026_PowerKGRetrieval.pdf",
}

OLD_PDFS = [
    "KG-5_Li2026_FinKario.pdf", "KG-9_Zheng2019_Doc2EDAG.pdf", "KG-16_Tong2022_DocEE.pdf",
    "KG-17_Liu2024_DocEE-zh.pdf", "KG-19_Wang2022_MAVEN-ERE.pdf", "KG-29_Ding2021_JEL_EntityLinking.pdf",
    "RAG-1_Lewis2020_RAG.pdf", "RAG-9_Edge2024_GraphRAG.pdf", "RAG-10_Gutierrez2024_HippoRAG.pdf",
    "RAG-11_Es2023_RAGAS.pdf", "RAG-13_Yang2018_HotpotQA.pdf", "RAG-24_Min2023_FActScore.pdf",
    "FIN-3_Islam2023_FinanceBench.pdf", "FIN-16_Saxena2021_CronKGQA.pdf", "FIN-17_Mavromatis2022_TempoQR.pdf",
    "FIN-20_Kumar2026_HalluBench.pdf", "SYS-4_Zhang2024_LLM_LayeredArch.pdf", "SYS-8_Sarmah2024_HybridRAG.pdf",
    "SYS-13_Li2026_RAGPerf.pdf", "SYS-14_Yan2025_HetaRAG.pdf",
]
KEEP_PDFS = ["KG-21_Liu2022_FinancialEmergencyKG.pdf", "KG-28_Duan2021_EntityDisambiguationReview.pdf"]


def cand_cell(it: dict) -> str:
    if it["code"] in ("KG-21", "KG-28"):
        return "保留不动（已是中文）"
    return (
        f"题名：{it['cand_title']}；作者：{it['cand_authors']}；出处：{it['cand_source']}；"
        f"年/卷期页：{it['cand_volpage']}；知网标识：{it['cnki_id']}；URL：{it['cand_url']}"
    )


def md_escape(t: str) -> str:
    return t.replace("|", "｜").replace("\n", " ")


def sanitize(t: str) -> str:
    """术语纪律：不写出被禁用的四字连写（「向量」+「数据库」的连写）。"""
    return t.replace("向量" + "数据库", "向量〔数据库〕")


def parse_citation(c: str) -> tuple[str, str, str, str]:
    m = re.match(r"^(.*?)\.\s+(.*)$", c)
    authors, rest = (m.group(1), m.group(2)) if m else ("", c)
    idx = rest.rfind(". ")
    if idx > 0:
        title, src = rest[:idx], rest[idx + 2:]
    else:
        title, src = rest, ""
    year = ""
    ys = re.findall(r"(?:19|20)\d{2}", src)
    if ys:
        year = ys[0]
    return authors, title, src.strip("."), year


def main() -> None:
    os.makedirs(VO, exist_ok=True)
    by_code = {it["code"]: it for it in ITEMS}
    items = [by_code[c] for c in ORDER]
    quotes = {q["code"]: q for q in QUOTES}

    # ---------------- 替换方案.md ----------------
    L: list[str] = []
    L.append("# 精选文献库（22 篇）中文替换方案（核实版）")
    L.append("")
    L.append("> 生成时间：2026-09-28。本文件只落在 `阶段02-文献调研与开题/_知网替换/` 下，未改动《03》《04》《文献PDF》与任何阶段文档。")
    L.append("> 核实来源仅限：知网空间（cnki.com.cn）文章页、知网学位论文库公开页（cdmd.cnki.com.cn）、知网空间检索（search.cnki.com.cn）。")
    L.append("> 每条替换候选的判定都基于本轮抓取的原始页面证据；页面未提供的字段（如卷号、页码、学位论文导师）一律标注\"页面未提供\"，不作推断。")
    L.append("")
    L.append("## 一、主表（22 行）")
    L.append("")
    L.append("> 阅读提示：\"替换后那个论点是否仍被支撑\"写在每行的**建议采纳**列（含\"须改写论证口径／须保留英文原文／对原论点不成立\"等结论），\"奠基性说明\"列给出中文无等价替代的如实说明。")
    L.append("")
    L.append("| 原编号 | 原题录摘要 | 引用位置 | 引用目的 | 原中文/英文 | 替换候选（题名/作者/出处/年/卷期页/知网标识/文章页URL） | 核实判定 | 证据文件 | 全文可得性 | 奠基性说明 | 建议采纳 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for it in items:
        L.append(
            "| {code} | {orig} | {pos} | {purpose} | {lang} | {cand} | {verdict} | {ev} | {ft} | {found} | {rec} |".format(
                code=it["code"], orig=md_escape(it["orig"]), pos=md_escape(it["pos"]),
                purpose=md_escape(it["purpose"]), lang=it["lang"], cand=md_escape(cand_cell(it)),
                verdict=md_escape(it["verdict"] + "——" + it["verdict_note"]), ev=md_escape(it["evidence"]),
                ft=md_escape(it["fulltext"]), found=md_escape(it["found"]), rec=md_escape(it["recommend"]),
            )
        )
    L.append("")
    L.append("### 1.1 建议采纳分档（核实结论）")
    L.append("")
    L.append("| 原编号 | 分档 | 一句话理由 |")
    L.append("| --- | --- | --- |")
    for code in ORDER:
        if code in ("KG-21", "KG-28"):
            continue
        grade, why = BREAK_DOWN[code]
        L.append(f"| {code} | {grade} | {why} |")
    L.append("")
    L.append("> 其中\"不建议采纳／建议改选\"共 4 条：**KG-5、KG-29、RAG-11、SYS-4**；\"建议谨慎\"1 条：FIN-20；其余 15 条按\"可采纳\"处理，但多数需要同时补正论证口径并保留对应的英文奠基文献。")
    L.append("")
    L.append("## 二、核实未通过／存疑清单")
    L.append("")
    L.append("| 原编号 | 类别 | 明细 | 建议 |")
    L.append("| --- | --- | --- | --- |")
    L.append("| SYS-13 | 题录有出入（题名） | 表中所写\"融合检索增强生成技术的国产轻量化大语言模型在专科问题解答中的效能评估\"；页面实际\"……在肺癌专科问题解答中的效能评估\"，表中漏\"肺癌\"二字；作者表中\"任治臻等\"，页面 11 位作者全列；刊期一致 | 采纳前必须更正题名，正文引用按\"肺癌专科\"口径表述 |")
    L.append("| KG-5 | 题录通过、支撑关系存疑 | 候选（基于注意力机制的 KG 推理，宁夏大学硕士论文）与表中落点\"两阶段图检索\"不匹配 | 建议改选池内 KG-7 或 KG-26 |")
    L.append("| KG-29 | 题录通过、支撑关系疑似不相关 | 表中写\"支持'通用链接器不适配专有实体'论据\"，但《面向开源情报的实体链接技术研究综述》不含金融/企业专有实体的工业实践证据 | 保留 JEL 原文承担原论据；候选仅作国内综述引用 |")
    L.append("| RAG-11 | 题录通过、支撑关系疑似不相关 | 表中落点是\"评估指标/问答指标参考\"，候选是文本图结构化＋层次化检索的方法论文，不含评估指标体系 | 保留 RAGAS 原文；评估实践改由 SYS-13 候选承担 |")
    L.append("| SYS-4 | 题录通过、支撑关系疑似不相关 | 表中落点是\"分层职责论证\"，候选是水利 KG↔大模型双向赋能技术体系，不含软件分层架构 | 保留原英文架构文献；池内改选 SYS-2/SYS-16/SYS-18 |")
    L.append("| 9 条学位论文 | 页面未提供导师字段 | KG-5（赵军）、KG-16（廖涛）、KG-17（臧洁）、RAG-9（顾树俊）、RAG-10（卢玲）、RAG-13（凌震华）、FIN-3（杜方）、FIN-16（卢玲）、FIN-20（陈佃军）——9 条 cdmd 公开页全页无\"导师\"字样 | 表中导师字段本轮无法核实；如需写入论文，请以学校学位论文库或论文封面为准 |")
    L.append("| 11 条期刊候选 | 页面未提供卷号与页码 | 20 条替换候选中 11 条为期刊论文（另 9 条为学位论文：8 硕士＋1 博士），期刊公开页只给\"刊名＋年＋期\"，无卷号与起止页 | 引用时需按知网详情页/原刊目录补全卷号与页码 |")
    L.append("| 对照表第三节 | 类型分布口径不一致 | 原表写\"核心期刊 9＋普通期刊 3＋博士 1＋硕士 9\"（合 22），按页面核实：替换后应为**期刊 13 篇**（11 条替换候选＋2 条保留：KG-21、KG-28）＋**学位论文 9 篇**（8 硕士＋1 博士） | 建议第二步在《03》里按核实后的类型重算分布 |")
    L.append("")
    L.append("## 三、奠基性无等价替代清单")
    L.append("")
    L.append("下列 18 条原英文文献属**奠基性或开创性工作**，中文文献无等价替代；替换候选只能支撑\"国内进展／国内实例\"，原英文文献建议在引言或相关工作中**保留为国际前沿引用**，不应当作等价替换。")
    L.append("")
    L.append("| 原编号 | 原文献（奠基性工作） | 不可替代的核心内容 | 现替换候选只能支撑什么 |")
    L.append("| --- | --- | --- | --- |")
    for code, orig, core, cand in FOUNDATION:
        L.append(f"| {code} | {orig} | {core} | {cand} |")
    L.append("")
    L.append("> 另有 KG-5（FinKario, ACL 2026）虽非\"奠基性\"，但是与课题同构度最高的最新工作，中文池内无同口径替代；其\"事件增强金融 KG 自动构建＋两阶段图检索\"的落点建议保留英文原文。")
    L.append("")
    L.append("## 四、项目内可替换资产清单（归档池中文条目）")
    L.append("")
    L.append("扫描范围：`_归档_20260923_文献调研过程文件/` 的四方向文件＋四份 `_补充` 候选＋汇总文件；按题录去重后共 **31 条中文条目**，其中 **2 条**（KG-21、KG-28）已在 22 篇文献库中且全文在手，其余 29 条项目内均无全文 PDF。")
    L.append("")
    L.append("| 编号 | 题名 | 作者 | 出处 | 年 | 项目内全文 |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    pool = json.load(io.open(os.path.join(SCRIPT_DIR, "_归档池中文条目.json"), encoding="utf-8"))
    uniq: dict[str, dict] = {}
    for r in pool:
        if r["是否中文"]:
            uniq.setdefault(r["题录"], r)
    for r in sorted(uniq.values(), key=lambda x: (x["编号"][:3], int(re.findall(r"\d+", x["编号"])[-1]) if re.findall(r"\d+", x["编号"]) else 0)):
        a, t, s, y = parse_citation(r["题录"])
        L.append(f"| {r['编号']} | {md_escape(t)} | {md_escape(a)} | {md_escape(s)} | {y} | {'有：' + r['项目内PDF'] if r['项目内PDF'] else '否'} |")
    L.append("")
    L.append("> 说明：上述编号沿用归档池原编号；`方向一` 文件里的 `[6]/[7]/[14]/[15]` 即汇总文件里的 `KG-6/KG-7/KG-14/KG-15`，本表已统一为 KG- 前缀。归档池\"是否已有全文\"以当前 `文献PDF/` 目录实际存在的 PDF 为准（项目内仅 22 个 PDF）。")
    L.append("")
    L.append("## 五、比对照表更合适的池内候选（供作者选择）")
    L.append("")
    L.append("| 编号 | 题录 | 更合适的理由 | 项目内全文 |")
    L.append("| --- | --- | --- | --- |")
    for code, cite, why, ft in BETTER:
        L.append(f"| {code} | {md_escape(cite)} | {md_escape(why)} | {ft} |")
    L.append("")
    L.append("> 提示：上述候选的**全部 14 条项目内均无全文**，若作者改选，需要与 20 条替换候选一起下载全文（见《下载清单.md》）。")
    L.append("")
    with io.open(os.path.join(OUTDIR, "替换方案.md"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(L) + "\n"))

    # ---------------- 替换方案.csv ----------------
    header = ["原编号", "原题录摘要", "引用位置", "引用目的", "原中文/英文", "替换候选（题名/作者/出处/年/卷期页/知网标识/文章页URL）",
              "核实判定", "证据文件", "全文可得性", "奠基性说明", "建议采纳", "作者批注"]
    rows = []
    for it in items:
        rows.append([
            it["code"], it["orig"], it["pos"], it["purpose"], it["lang"], cand_cell(it),
            it["verdict"] + "——" + it["verdict_note"], it["evidence"], it["fulltext"],
            it["found"], it["recommend"], "",
        ])
    with io.open(os.path.join(OUTDIR, "替换方案.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow([sanitize(x) for x in header])
        w.writerows([[sanitize(x) for x in r] for r in rows])

    # ---------------- 候选题录.jsonl ----------------
    keys = ["原编号", "原题录", "引用位置", "引用目的", "原语种", "替换候选题名", "替换作者", "替换出处",
            "年", "卷期页", "知网标识", "文章页URL", "核实判定", "字段出入明细", "证据文件", "全文可得性",
            "奠基性说明", "建议采纳", "更优池内候选"]
    with io.open(os.path.join(OUTDIR, "候选题录.jsonl"), "w", encoding="utf-8") as fh:
        for it in items:
            year = it["cand_source"]
            m = re.search(r"(20\d{2})", year)
            rec = {
                "原编号": it["code"],
                "原题录": it["orig"],
                "引用位置": it["pos"],
                "引用目的": it["purpose"],
                "原语种": it["lang"],
                "替换候选题名": it["cand_title"] if it["code"] not in ("KG-21", "KG-28") else "保留不动",
                "替换作者": it["cand_authors"],
                "替换出处": it["cand_source"],
                "年": m.group(1) if m else "",
                "卷期页": it["cand_volpage"],
                "知网标识": it["cnki_id"],
                "文章页URL": it["cand_url"],
                "核实判定": it["verdict"],
                "字段出入明细": it["verdict_note"],
                "证据文件": it["evidence"],
                "全文可得性": it["fulltext"],
                "奠基性说明": it["found"],
                "建议采纳": it["recommend"],
                "更优池内候选": it["alt"],
            }
            line = json.dumps({k: rec[k] for k in keys}, ensure_ascii=False)
            fh.write(sanitize(line) + "\n")

    # ---------------- 下载清单.md ----------------
    D: list[str] = []
    D.append("# 替换后全文下载清单（给作者）")
    D.append("")
    D.append("> 本清单只给下载指引，**未下载任何全文**；所有链接都是知网公开文章页，正文页上的\"下载全文\"入口需要作者本人以机构账号在知网完成。")
    D.append("> 命名规范：`<编号>_<第一作者姓><年份>_<短标题>.pdf`，落盘到 `阶段02-文献调研与开题/文献PDF/`。")
    D.append("")
    D.append("## 一、仍有效的 2 个 PDF（保留不动）")
    D.append("")
    for n in KEEP_PDFS:
        D.append(f"- `{n}`")
    D.append("")
    D.append("## 二、将被替换的 20 个 PDF（替换后不再与题录对应）")
    D.append("")
    for n in OLD_PDFS:
        D.append(f"- `{n}`")
    D.append("")
    D.append("> 另有 10 个同名 `.docx`（文献PDF 目录）与 10 份《文献翻译》译文同属这 20 条原英文文献；第二步改文档时需一并决定保留或替换，本次未做任何改动。")
    D.append("")
    D.append("## 三、20 条替换候选逐条下载指引")
    D.append("")
    D.append("| 原编号 | 题名 | 出处 | 年卷期页 | 知网直达链接 | 建议文件名 |")
    D.append("| --- | --- | --- | --- | --- | --- |")
    for it in items:
        if it["code"] in ("KG-21", "KG-28"):
            continue
        D.append(
            f"| {it['code']} | {md_escape(it['cand_title'])} | {md_escape(it['cand_source'])} | {md_escape(it['cand_volpage'])} | {it['cand_url']} | `{SHORT_NAMES[it['code']]}` |"
        )
    D.append("")
    D.append("## 四、若采纳\"更优池内候选\"需追加下载的条目")
    D.append("")
    D.append("| 编号 | 题名（出处） | 知网/来源提示 |")
    D.append("| --- | --- | --- |")
    for code, cite, _why, _ft in BETTER:
        D.append(f"| {code} | {md_escape(cite)} | 需作者按题名在知网检索后下载；本次未逐条核实其文章页 |")
    D.append("")
    D.append("## 五、操作要点")
    D.append("")
    D.append("1. 知网全文下载需机构/个人账号与订阅权限，本任务全程未登录、未下载、未点击任何下载链接，因此下载环节必须由作者完成。")
    D.append("2. 期刊论文下载文件名按上表\"建议文件名\"；若作者对短标题命名有偏好，保持\"编号_第一作者姓年份_\"前缀不变即可，以免破坏《03》《04》与 `文献PDF/` 的编号对应关系。")
    D.append("3. KG-9、KG-17、KG-19 三条的候选与现有《_知网替换/证据》里的 `_1` 证据同源，可直接使用页面题录信息。")
    D.append("4. 下载完成后建议逐条核对：文件名前缀编号 ↔ 题名 ↔ 作者 ↔ 出处；任何一条对不上，都不要入库。")
    D.append("")
    with io.open(os.path.join(OUTDIR, "下载清单.md"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(D) + "\n"))

    # ---------------- 验证输出附件 ----------------
    V1 = ["# 验证 1：20 条逐条核实结果表（判定｜页面 URL｜证据文件名｜字段出入明细）", ""]
    V1.append("| 原编号 | 判定 | 页面 URL | 证据文件名 | 字段出入明细 |")
    V1.append("| --- | --- | --- | --- | --- |")
    for it in items:
        if it["code"] in ("KG-21", "KG-28"):
            continue
        V1.append(f"| {it['code']} | {it['verdict']} | {it['cand_url']} | {os.path.basename(it['evidence'].split(' / ')[0])} / {os.path.basename(it['evidence'].split(' / ')[1])} | {md_escape(it['verdict_note'])} |")
    with io.open(os.path.join(VO, "01_逐条核实结果表.md"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(V1) + "\n"))

    V2 = ["# 验证 2：22 条的引用位置与《04》原文片段", ""]
    for it in items:
        q = quotes[it["code"]]
        V2.append(f"## {it['code']}（参考文献{q['ref']}）")
        V2.append("")
        V2.append(f"- 位置：{q['pos']}")
        V2.append(f"- 表中行（替换候选）：{cand_cell(it)}")
        V2.append(f"- 原文：{q['quote']}")
        V2.append("")
    with io.open(os.path.join(VO, "02_引用片段对照.md"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(V2) + "\n"))

    V3 = ["# 验证 3：归档池\"项目内可替换资产\"清单（中文条目）", ""]
    V3.append(f"中文条目数（按题录去重）：{len(uniq)}；其中项目内已有全文：{sum(1 for r in uniq.values() if r['项目内PDF'])}")
    V3.append("")
    V3.append("| 编号 | 题名 | 作者 | 出处 | 年 | 项目内全文 |")
    V3.append("| --- | --- | --- | --- | --- | --- |")
    for r in sorted(uniq.values(), key=lambda x: (x["编号"][:3], int(re.findall(r"\d+", x["编号"])[-1]) if re.findall(r"\d+", x["编号"]) else 0)):
        a, t, s, y = parse_citation(r["题录"])
        V3.append(f"| {r['编号']} | {md_escape(t)} | {md_escape(a)} | {md_escape(s)} | {y} | {'有：' + r['项目内PDF'] if r['项目内PDF'] else '否'} |")
    with io.open(os.path.join(VO, "03_归档池资产清单.md"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(V3) + "\n"))

    # 证据文件清单（文件名＋字节数）
    E = ["# 验证 5：证据文件清单（文件名＋字节数）", ""]
    tot = 0
    ev_dir = os.path.join(BASE, "证据")
    for it in items:
        if it["code"] in ("KG-21", "KG-28"):
            continue
        for ext in ("html", "txt"):
            p = os.path.join(ev_dir, f"{it['code']}.{ext}")
            n = os.path.getsize(p) if os.path.exists(p) else -1
            tot += max(n, 0)
            E.append(f"{it['code']}.{ext}\t{n} 字节")
    E.append("")
    E.append(f"合计 40 个文件，{tot} 字节；另有 KG-21_1（沿用上轮）、KG-28（《_知网核验》目录）两条保留项的既有证据。")
    with io.open(os.path.join(VO, "05_证据文件清单.txt"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(E) + "\n"))

    # ---------------- 核验报告.md（第九节由 07 追加） ----------------
    R: list[str] = []
    R.append("# 精选文献库（22 篇）中文替换：核实与方案报告")
    R.append("")
    R.append("> 生成时间：2026-09-28。任务：核实既有对照表中的 20 条中文替换候选，并补齐引用目的、可替代性、项目内资产与下载清单。")
    R.append("> 本步只写 `阶段02-文献调研与开题/_知网替换/`；未改动《03-精选文献库（22篇）.md》《04-开题报告.md》《文献PDF/》《工具/》《代码/》与任何阶段文档。")
    R.append("")
    R.append("## 一、来源性质声明")
    R.append("")
    R.append("- 题录来源只写三种：**知网空间（cnki.com.cn）文章页**、**知网学位论文库公开页（cdmd.cnki.com.cn）**、**知网空间检索（search.cnki.com.cn）**。")
    R.append("- 全程**不登录**、不使用任何账号或密码、不提交任何凭据、不绕过验证；**不下载、不点击任何全文/CAJ/PDF 下载链接**（只在页面里登记 href，不跳转）。")
    R.append("- 请求节奏：本轮 20 条文章页抓取按 ≥2.5 秒/次间隔；上轮检索按 ≥2.5 秒/次。")
    R.append("- 未做任何模型调用（本轮全部工具只有 `requests`、`BeautifulSoup` 与本地 Python 解析）。")
    R.append("- 术语纪律：本目录所有产出不写出被禁用的四字连写；凡引用《04》原文或原始命令输出中出现该连写处，一律按纪律改排为「向量〔数据库〕」并在相应位置注明（原始证据 HTML／TXT 不改动）。")
    R.append("")
    R.append("## 二、方法与节奏")
    R.append("")
    R.append("| 脚本 | 作用 |")
    R.append("| --- | --- |")
    R.append("| `_脚本/03_核实文章页.py` | 本轮逐条抓取 20 条替换候选的文章页，产出 `证据/<编号>.html` 与 `证据/<编号>.txt`，登记 `_脚本/_请求清单_本轮.txt` |")
    R.append("| `_脚本/04_扫描归档池.py` | 扫描归档池四方向＋四补充＋汇总文件，产出 `_脚本/_归档池中文条目.json` |")
    R.append("| `_脚本/05_自证统计.py` | 统计请求域名命中与脚本账号字段，产出 `_脚本/_自证统计.txt` |")
    R.append("| `_脚本/06_生成产物.py` | 生成本报告与《替换方案》《下载清单》《候选题录》 |")
    R.append("| `_脚本/00_探测.py`、`01_检索.py`、`02_抓文章页.py` | 上一轮半成品脚本，本次**未运行**，其既有证据与请求清单原样保留 |")
    R.append("")
    R.append("字段抽取口径：`<title>` 尾部的\"刊名/单位＋年＋期/学位类型\"、`<h1>` 题名、作者链接、`【摘要】`、`【关键词】`、`【学位授予单位】/【学位级别】/【学位授予年份】`、页面\"下载\"入口 href、以及**页面是否出现\"导师\"字段**。")
    R.append("")
    R.append("## 三、20 条逐条核实结果表")
    R.append("")
    R.append("| 原编号 | 判定 | 页面 URL | 证据文件名 | 字段出入明细 |")
    R.append("| --- | --- | --- | --- | --- |")
    for it in items:
        if it["code"] in ("KG-21", "KG-28"):
            continue
        R.append(f"| {it['code']} | {it['verdict']} | {it['cand_url']} | {os.path.basename(it['evidence'].split(' / ')[0])} / {os.path.basename(it['evidence'].split(' / ')[1])} | {md_escape(it['verdict_note'])} |")
    R.append("")
    R.append("### 3.1 字段出入明细（表中所写 vs 页面实际）")
    R.append("")
    R.append("| 原编号 | 表中所写 | 页面实际 |")
    R.append("| --- | --- | --- |")
    for it in items:
        if it["code"] in ("KG-21", "KG-28"):
            continue
        tf = TABLE_FIELDS[it["code"]]
        R.append(f"| {it['code']} | {md_escape(tf['表中所写'])} | {md_escape(tf['页面实际'])} |")
    R.append("")
    R.append("## 四、完成数统计与四方向覆盖")
    R.append("")
    R.append("| 判定 | 条数 | 占比 |")
    R.append("| --- | --- | --- |")
    R.append("| 核实通过（题录一致） | 19 | 95% |")
    R.append("| 题录有出入（题名） | 1（SYS-13） | 5% |")
    R.append("| 找不到 | 0 | 0% |")
    R.append("| 疑似不相关（题录通过但对原论点不成立） | 4（KG-5、KG-29、RAG-11、SYS-4） | 20% |")
    R.append("")
    R.append("| 方向 | 替换条数 | 核实通过 | 题录有出入 | 找不到 | 疑似不相关（对原论点） |")
    R.append("| --- | --- | --- | --- | --- | --- |")
    R.append("| 知识图谱 KG | 6 | 6 | 0 | 0 | 2（KG-5、KG-29） |")
    R.append("| RAG | 6 | 6 | 0 | 0 | 1（RAG-11） |")
    R.append("| 金融问答 FIN | 4 | 4 | 0 | 0 | 0 |")
    R.append("| 软件系统 SYS | 4 | 3 | 1（SYS-13） | 0 | 1（SYS-4） |")
    R.append("| **合计** | **20** | **19** | **1** | **0** | **4** |")
    R.append("")
    R.append("> 口径说明：\"疑似不相关\"只针对**表中写明的支撑关系**，不代表题录有误；这 4 条题录本身已核实通过。")
    R.append("")
    R.append("## 五、奠基性无等价替代清单")
    R.append("")
    R.append("共 18 条（见《替换方案.md》第三节表）：RAG-1、KG-9、KG-16、KG-17、KG-19、RAG-9、RAG-10、RAG-11、RAG-13、RAG-24、FIN-3、FIN-16、FIN-17、FIN-20、SYS-4、SYS-8、SYS-13、SYS-14。")
    R.append("")
    R.append("如实说明：这些工作（RAG 原论文、GraphRAG、HippoRAG、HotpotQA、FActScore、FinanceBench、CronKGQA、TempoQR、HalluBench、RAGPerf、HetaRAG、DocEE 系列、MAVEN-ERE、HybridRAG、LLM 分层架构等）在中文文献中**没有等价替代**；现替换候选只能支撑\"国内进展／国内实例\"，英文奠基文献建议保留为国际前沿的简介引用，不要假装等价。")
    R.append("")
    R.append("## 六、项目内可替换资产与\"是否有更优候选\"")
    R.append("")
    R.append("- 归档池按题录去重后共 **31 条中文条目**（KG 13、RAG 6、FIN 4、SYS 8）；其中 **2 条**（KG-21、KG-28）已在 22 篇文献库中且全文在手；其余 **29 条项目内无全文**（当前 `文献PDF/` 只有 22 个 PDF）。")
    R.append("- 汇总文件《03-文献调研汇总.md》自称中文 35 篇（13/6/7/9），而四方向文件实际可检出 13/6/4/8＝31 条中文条目；FIN 与 SYS 两方向存在 4 条差额，属项目内文档统计口径不一致，本轮如实记录、不改动归档文件。")
    R.append("- **有更优候选**：14 条（见《替换方案.md》第五节），其中对现对照表影响最大的三条是：")
    R.append("  1. **RAG-1 → 建议优先用池内 RAG-15**（刘澳迪等，《软件学报》综述）而非现候选（《计算机科学》2026 综述）：中文 CCF-A 期刊、权威性更高。")
    R.append("  2. **KG-5 → 建议改用池内 KG-7**（刘政昊等，金融证券 KG 构建与相关股票发现）：直接面向 A 股、含中文文本抽取，比现候选（KG 推理方法）更贴\"金融 KG 构建\"落点。")
    R.append("  3. **SYS-4 → 建议改用池内 SYS-2/SYS-16/SYS-18**：现候选是水利 KG↔大模型双向赋能，不能承担\"软件分层架构\"论证。")
    R.append("- 这些更优候选**项目内均无全文**；若作者采纳，需与 20 条替换候选一并下载全文。")
    R.append("")
    R.append("## 七、下载清单要点")
    R.append("")
    R.append("- 现有 22 个 PDF 中，**2 个仍然有效**：`KG-21_Liu2022_FinancialEmergencyKG.pdf`、`KG-28_Duan2021_EntityDisambiguationReview.pdf`。")
    R.append("- 其余 **20 个 PDF 将被替换**（清单见《下载清单.md》第二节）；替换后这 20 篇的全文**不在手**，必须由作者按《下载清单.md》逐条下载（20 条候选中 11 条为期刊论文、9 条为学位论文：8 硕士＋1 博士）。")
    R.append("- 每条候选在页面上都只有\"下载全文\"入口（知网需登录/订阅），没有任何一条是页面即开放获取；因此下载是替换能否成立的关键前置步骤。")
    R.append("- 另需注意：20 条原英文文献还对应 10 个 `.docx` 与 10 份《文献翻译》译文，第二步改文档时需一并处置。")
    R.append("")
    R.append("## 八、无登录自证")
    R.append("")
    R.append("本轮 `_脚本/_请求清单_本轮.txt` 共 22 行（20 条 GET＋RUN_START/RUN_END），含 URL 的请求行 20 条，域名命中：`www.cnki.com.cn` 11、`cdmd.cnki.com.cn` 9；`kns.cnki.net` 命中 **0**，`pay.cnki.net` 命中 **0**，`mall.cnki.net` 命中 **0**，`card.cnki.net`／`vipcard.cnki.net`／`bank.cnki.net` 均命中 **0**。脚本账号字段扫描：全部命中均为\"不使用账号或密码\"之类的纪律声明行，**赋值/调用式账号字段命中 0**。完整输出见第九节验证 4。")
    R.append("")
    R.append("## 九、验证 1～7 原始输出")
    R.append("")
    R.append("（由 `_脚本/07_追加验证输出.py` 在命令执行后追加。）")
    R.append("")
    R.append("## 十、未做到与不确定")
    R.append("")
    R.append("1. **未做二次检索扩充**：本轮以核实既有 20 条候选为主；未在知网重新做全量检索（除既定 20 条文章页外没有新增检索请求）。因此\"是否存在更好的中文替代\"只在项目内归档池范围内回答。")
    R.append("2. **9 条学位论文的导师字段无法核实**：cdmd 公开页不提供导师信息；表中 9 处\"导师：××\"本轮一律标注\"页面未提供\"，未用其他来源补齐。")
    R.append("3. **卷号与页码缺失**：11 条期刊候选的公开页只给\"刊名＋年＋期\"，卷号与起止页页面未提供；GB/T 7714 引用格式所需的卷(期)与页码需要作者在知网详情页或原刊目录补齐。")
    R.append("4. **RAG-9 页面摘要为空**：该硕士论文公开页未公开摘要，本轮只能依据题名与题录判定，内容要点未逐句核对。")
    R.append("5. **支撑关系判定带主观性**：\"可替代性\"一列基于题名、摘要与落点文字的对照判断，未逐篇精读全文（全文不在手且不下载）；其中 KG-5、KG-29、RAG-11、SYS-4 判为对原论点不成立，\n   建议作者复核后在 CSV 的\"作者批注\"列逐行确认。")
    R.append("6. **归档池中文条目统计差异**：见第六节第 2 条；差额 4 条未定位到具体条目（方向文件与汇总文件均未逐条列全），未能消除该差异。")
    R.append("7. **未验证页面之外的渠道**：万方、维普、期刊官网均未访问（任务限定知网公开站点）；若某条候选在知网之外有更权威版本，本轮未覆盖。")
    R.append("8. **未改动任何阶段文档**：《03》《04》等保持原样，因此本报告中的题名更正值（SYS-13）尚未落到文档里，第二步执行。")
    R.append("9. **上轮遗留的证据文件未改写**：`_脚本/_检索结果.json`（上轮检索原始结果）中含第三方的检索摘要文本，其中可能出现被项目术语纪律禁用的四字连写；本轮未改写任何上轮证据文件（改写原始证据等于造假），仅在本轮新写的报告中按纪律改排。")
    R.append("")
    R.append("## 十一、结果文件清单")
    R.append("")
    for f in ["替换方案.md", "替换方案.csv", "候选题录.jsonl", "下载清单.md", "核验报告.md"]:
        R.append(f"- `_知网替换/{f}`")
    R.append("- `_知网替换/证据/<编号>.html`＋`<编号>.txt`（20 条替换候选，共 40 个文件）")
    R.append("- `_知网替换/_脚本/03_核实文章页.py`、`04_扫描归档池.py`、`05_自证统计.py`、`06_生成产物.py`、`_归档池中文条目.json`、`_请求清单_本轮.txt`、`_自证统计.txt`、`_验证输出/`")
    R.append("")
    R.append("## 十二、HEAD 变化观察")
    R.append("")
    R.append("- 本轮开始时：HEAD = `8f45ec92005c4095bcdf5aaa4d5090724c822a72`（`8f45ec9 前七阶段审查报告《20》并登记进《00》`）。")
    R.append("- 本轮未执行 `git add`／`git commit`／`git add -f`；观察到的工作区状态见第九节验证 7。")
    R.append("")
    with io.open(os.path.join(OUTDIR, "核验报告.md"), "w", encoding="utf-8") as fh:
        fh.write(sanitize("\n".join(R) + "\n"))

    print("生成完成：替换方案.md / 替换方案.csv / 候选题录.jsonl / 下载清单.md / 核验报告.md")
    print("验证附件：", VO)


if __name__ == "__main__":
    main()
