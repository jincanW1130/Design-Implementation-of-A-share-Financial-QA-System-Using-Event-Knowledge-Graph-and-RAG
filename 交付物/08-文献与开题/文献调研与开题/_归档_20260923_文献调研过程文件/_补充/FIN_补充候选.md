# 金融问答方向补充文献候选（FIN-16 ～ FIN-25）

> 课题：基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现
> 补充日期：2026-09-23
> 补充规模：10 条（FIN-16 ～ FIN-25）
> 文件状态：本条目的收录与否待主控核验后合并入方向三文档（`文献调研/方向三_金融问答文献.md`）

**本次扩充的目的。** 方向三现有 FIN-1～FIN-15 以"金融问答数据集—财经文本处理—金融大模型"为主，存在四类明显缺口，本次按四类缺口定向补齐：①**时序问答基准**——研究假设 H3（加入时间约束后时序问题中的无关证据是否减少）与 RQ3 中"时间过滤"检索子集直接依赖可对标的时序问答任务定义与评测范式；②**金融长文档与推理基准**——补充长上下文推理、跨信号推理以及"检索增益在哪些问题上成立"的基准证据；③**A股与中文金融**——现有英文基准（FinQA、TAT-QA、FinanceBench）几乎全部面向美股或通用财报，A股与中文公告/新闻场景的支撑文献极薄；④**最新（2025—2026）金融 KG 问答**——用于说明本课题与最新进展的关系与定位。

**核验方法。** 每条新增文献均遵循"题录逐字取自核验到的真实页面"的原则，至少用 **2 个相互独立的来源**交叉确认作者列表、题名、出处与年份，来源范围包括：arXiv API 与 arXiv abs 页、ACL Anthology 官方页、AAAI/Crossref DOI 记录、会议官网、期刊官网、Semantic Scholar、OpenAlex、超星发现等；中文文献优先在知网/万方/期刊官网之一可查，本次实际以期刊官网 + 独立数据库（超星发现、Crossref DOI 记录）完成交叉核验。全文下载后统一校验：文件必须以 `%PDF-` 开头且字节数大于 20000，不合格文件已删除且不计入；不下载非官方来源的中文全文。核验中若发现线索与真实出处不一致（本次为 FIN-16、FIN-17 的会议与年份线索），一律**以核验到的真实出处书写题录**，并在该条"核验状态"中保留线索偏差说明。

**去重与边界说明。** 10 条均与现有 56 条（KG-1～15、RAG-1～15、FIN-1～15、SYS-1～11）逐条比对，无重复；特别地，FIN-18（Reddy et al., DocFinQA, ACL 2024 短论文）与 FIN-1（Chen et al., FinQA, EMNLP 2021）为不同文献；FIN-16、FIN-17 虽非金融专属，按任务要求作为"时序问答基准"归入本方向。本次未收录股票涨跌预测、投资建议或量化交易类文献，也未收录归属其他方向的条目。

---

## 一、时序问答基准（FIN-16 ～ FIN-17）

### [FIN-16] Apoorv Saxena, Soumen Chakrabarti, Partha Talukdar. Question Answering Over Temporal Knowledge Graphs. Proceedings of the 59th Annual Meeting of the Association for Computational Linguistics and the 11th International Joint Conference on Natural Language Processing (Volume 1: Long Papers), 2021: 6663-6676.
- URL: https://aclanthology.org/2021.acl-long.520/
- 相关性：该文同时提出时序知识图谱问答基准 **CRONQUESTIONS**（按结构复杂度分层的最大规模时序 KGQA 数据集，规模为此前唯一同类数据集的 340 倍）与基于时序 KG 嵌入的 Transformer 模型 **CRONKGQA**。本课题 H3（时序问题中加入时间约束是否减少无关证据）与 RQ3 的"时间过滤"子集需要一套可复用的时序问题定义、时间区间建模与分层评测范式，该文的"时序 KG 边带有效时间区间（start/end time）+ 按结构复杂度分层统计"正是这一范式的来源，可直接指导本课题时序子集的构建与指标分组方式；其"仅靠静态 KGQA 方法在时序问题上大幅退化"的结论，也构成本课题引入时间过滤（消融实验 D 组）的立论依据。
- 优先级：★★★
- 核验状态：核验来源（1）ACL Anthology 官方页 `2021.acl-long.520`（题名、三位作者 Apoorv Saxena / Soumen Chakrabarti / Partha Talukdar、会议全称、页码 6663–6676、DOI 10.18653/v1/2021.acl-long.520）；（2）arXiv:2106.01515（2021-06-03，comment 字段标注 ACL 2021，作者与题名一致）；（3）OpenAlex（DOI 10.18653/v1/2021.acl-long.520 记录，作者、年份、出处一致）。全文已下载（ACL Anthology 官方 PDF，`文献PDF/FIN-16_Saxena2021_CronKGQA.pdf`，499,925 字节，文件头 `%PDF-`）。**线索偏差说明**：任务线索给出的"EMNLP 2021 左右"不准确，经核验该文正式出处为 ACL-IJCNLP 2021 长文（EMNLP 2021 无此文），题录与文件名按核验结果书写。

### [FIN-17] Costas Mavromatis, Prasanna Lakkur Subramanyam, Vassilis N. Ioannidis, Soji Adeshina, Phillip R. Howard, Tetiana Grinberg, Nagib Hakim, George Karypis. TempoQR: Temporal Question Reasoning over Knowledge Graphs. Proceedings of the AAAI Conference on Artificial Intelligence, 2022, 36(5): 5825-5833.
- URL: https://doi.org/10.1609/aaai.v36i5.20526
- 相关性：TempoQR 面向时序知识图谱上的复杂（多跳）问题，把问题编码为"实体、时间、上下文"三类表征，据此在时序子图上做稀疏检索与联合推理，并显式处理问题中隐含的时间约束。本课题的时间型问题（"某事件发生前后/期间"类提问）需要在图谱中同时约束关系路径与时间窗口，TempoQR 的"时间感知问题编码 + 时间上下文子图检索"可作为 RQ3 中时间过滤策略与跳数策略组合的对照方法与设计参考；它同时说明了"时序推理需要专门的问题分解与检索，而非仅依赖文本相似度"，与 H3 的提问方式一致。
- 优先级：★★★
- 核验状态：核验来源（1）arXiv:2112.05785（题名、8 位作者、2021-12-10，comment 字段标注 AAAI 2022）；（2）Crossref DOI 记录 10.1609/aaai.v36i5.20526（Proceedings of the AAAI Conference on Artificial Intelligence，卷 36、期 5、页 5825–5833，2022-06-28，出版商 AAAI）；（3）OpenAlex（AAAI Publications 与 Proceedings of the AAAI Conference on Artificial Intelligence 两条记录，DOI、卷期页码一致）。全文已下载（arXiv 官方 PDF，`文献PDF/FIN-17_Mavromatis2022_TempoQR.pdf`，225,194 字节，文件头 `%PDF-`）。**线索偏差说明**：任务线索给出的"ACL 2023 左右"不准确，经核验该文正式出处为 AAAI-22（2022），题录与文件名年份均按核验结果取 2022。

---

## 二、金融长文档与推理基准（FIN-18 ～ FIN-20）

### [FIN-18] Varshini Reddy, Rik Koncel-Kedziorski, Viet Dac Lai, Michael Krumdick, Charles Lovering, Chris Tanner. DocFinQA: A Long-Context Financial Reasoning Dataset. Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 2: Short Papers), 2024: 445-458.
- URL: https://aclanthology.org/2024.acl-short.42/
- 相关性：DocFinQA 把金融问答从"单页证据"推进到**长文档检索—推理**设定：以 FinQA 的既有问答对为起点，将证据页扩展为整份公司年报等长文档，使模型必须在数万 token 的上下文中定位证据再做数值推理，并揭示了长上下文模型与检索式方法在该设定下的性能落差。本课题的 A股公告/年报多为数十页的长文本，"先把长文档切块检索、再做多跳与数值推理"是核心流程；该文可直接作为"长文档金融问答基准"的对标对象，并为 RQ2 中"证据召回是否充分"的评价指标（Evidence Recall）与失败案例分析提供可对照的任务设定。
- 优先级：★★
- 核验状态：核验来源（1）ACL Anthology 官方页 `2024.acl-short.42`（题名、6 位作者、会议全称、页码 445–458、DOI 10.18653/v1/2024.acl-short.42）；（2）Crossref DOI 记录 10.18653/v1/2024.acl-short.42（Proceedings of the 62nd Annual Meeting of the ACL, Volume 2: Short Papers，页 445–458，2024）；（3）arXiv:2401.06915（题名与作者一致）。全文已下载（ACL Anthology 官方 PDF，`文献PDF/FIN-18_Reddy2024_DocFinQA.pdf`，2,047,669 字节，文件头 `%PDF-`）。**去重说明**：本条与 FIN-1（Zhiyu Chen 等, FinQA, EMNLP 2021）为不同文献，作者、出处、任务设定均不同，引用时须区分。

### [FIN-19] Yogesh Agrawal, Aniruddha Dutta, Md Mahadi Hasan, Santu Karmaker, Aritra Dutta. FinTradeBench: A Financial Reasoning Benchmark for LLMs. arXiv:2603.19225, 2026.
- URL: https://arxiv.org/abs/2603.19225
- 相关性：FinTradeBench 包含 1,400 道以 NASDAQ-100 公司十年历史窗口为基础的问题，分为"公司基本面（源自监管文件）/市场交易信号/需要跨信号推理的混合问题"三类，并在零样本提示与检索增强两种设置下评测 14 个大模型。对本课题最有价值的不是其数据域，而是其**实验设计结论**：检索增强对"文本型基本面推理"改善明显，对"数值与时序信号推理"帮助有限——这正是 RQ2/H1 需要检验的"检索（图谱）增强在哪些问题类型上有效、在哪些类型上作用有限"的同类证据与分组统计范式。**边界说明**：该基准含"交易信号"类问题，本课题只借鉴其基准构建与分组评测方法，不涉及涨跌预测、投资建议或交易策略研究。
- 优先级：★★
- 核验状态：核验来源（1）arXiv abs 页 `2603.19225`（题名、5 位作者、提交日期 2026-03-19、v1–v5 版本信息与摘要）；（2）arXiv API 元数据（题名、作者列表、published/updated 时间一致）；（3）OpenAlex（题为 FinTradeBench: A Financial Reasoning Benchmark for LLMs，2026-03-19，作者 Yogesh C. Agrawal / Aniruddha Dutta / Md Mahadi Hasan / Santu Karmaker / Aritra Dutta，DOI 10.48550/arXiv.2603.19225）。全文已下载（arXiv 官方 PDF，`文献PDF/FIN-19_Agrawal2026_FinTradeBench.pdf`，2,328,400 字节，文件头 `%PDF-`）。

### [FIN-20] Mahesh Kumar, Bhaskarjit Sarmah, Stefano Pasquali. FinReflectKG -- HalluBench: GraphRAG Hallucination Benchmark for Financial Question Answering Systems. arXiv:2603.20252, 2026.
- URL: https://arxiv.org/abs/2603.20252
- 相关性：**本方向补充清单中最相关的一条**。该文提出 FinBench-QA-Hallucination：在 SEC 10-K 语料上构建 755 条标注样本（覆盖 300 页），每条样本按"必须同时得到文本块与抽取三元组支持"的保守证据链协议标注 groundedness；随后在"有/无 KG 三元组"两种条件下比较六类检测方法（LLM 评审、微调分类器、NLI、span 检测与向量方法）。结论显示：干净条件下 LLM 评审与向量方法 F1 达 0.82–0.86，而一旦引入噪声三元组，多数方法 MCC 下降 44%–84%，向量方法仅下降 9%。该文直接对应本课题 RQ2 与 Faithfulness 指标：①它给出了"KG 增强金融问答的忠实度/幻觉"评测协议与标注规范，可支撑本课题"答案 + 文本证据 + 图谱路径"联合追溯的度量设计；②它量化提示了"图谱抽取噪声会显著削弱评测可靠性"，对应本课题风险三失败案例分析中的"抽取错误/生成不忠实"归因；③其"文本块 + 三元组双证据"标注思想与本课题的证据链追溯设计一致。
- 优先级：★★★
- 核验状态：核验来源（1）arXiv abs 页 `2603.20252`（题名、三位作者 Mahesh Kumar / Bhaskarjit Sarmah / Stefano Pasquali、提交日期 2026-03-11 与摘要）；（2）Semantic Scholar 检索记录（题名、作者、年份 2026、载体 arXiv.org、编号 2603.20252）；（3）OpenAlex（2026-03-11，作者与题名逐字一致，DOI 10.48550/arXiv.2603.20252）。全文已下载（arXiv 官方 PDF，`文献PDF/FIN-20_Kumar2026_HalluBench.pdf`，1,205,856 字节，文件头 `%PDF-`）。

---

## 三、A股与中文金融（FIN-21 ～ FIN-24）

### [FIN-21] 贺毅岳, 戴欣远, 高妮. 知识图谱视角下我国股票市场风险传染研究. 运筹与管理, 2024, 33(2): 151-157.
- URL: http://www.jorms.net/CN/10.12005/orms.2024.0057
- 相关性：**A股专属**工作。该文以我国 A股上市公司大数据为基础，通过爬虫采集多维度关联数据、经实体消歧与实体统一后构建上市公司关联知识图谱（约 15 万个节点、18 万条关系，覆盖董监高任职、持股、借贷等多层关联），再将其转化为风险传染图谱，用个性化 PageRank 随机游走对突发风险事件的传染过程做可视化模拟与预测，系统支持可视化查询与智能推理。本方向现有英文基准几乎全部面向美股与通用财报，A股图谱文献极薄；该文补齐了"中文 A股上市公司图谱的实体与关系体系如何设计"这一块，可作为 RQ1 中"A股实体/关系建模合理性"的中文论据，其图谱规模与关系类型统计也为本课题抽取评测集的目标规模提供参照。需要说明：该文属风险传染模拟研究而非问答系统，收录理由是其中的 A股知识图谱建模方法与检索能力。
- 优先级：★★
- 核验状态：核验来源（1）《运筹与管理》期刊官网文章页（中文题名"知识图谱视角下我国股票市场风险传染研究"、英文题名"Risk Contagion in Stock Market from the Perspective of Knowledge Graph"、作者贺毅岳/戴欣远/高妮、2024 年第 33 卷第 2 期 151–157、DOI 10.12005/orms.2024.0057、ISSN 1007-3221）；（2）超星发现学术期刊条目（题名、作者贺毅岳/戴欣远/高妮、《运筹与管理》2024 年第 2 期）；（3）期刊官网 2024 年第 2 期目次页（该文条目与前一条目连续编号，卷期页码一致）。全文已下载（期刊官网 PDF，`文献PDF/FIN-21_He2024_StockRiskContagionKG.pdf`，1,608,422 字节，文件头 `%PDF-`）。该刊为 CSSCI/CSCD 来源期刊、中文核心期刊。

### [FIN-22] 任秋宇, 刘佳芮. 一种基于FinBERT-CRF命名实体识别模型的证券领域知识图谱构建框架. 数据挖掘, 2021, 11(3): 135-149.
- URL: https://www.hanspub.org/journal/paperinformation?paperID=42665
- 相关性：面向证券领域新闻文本，提出"实时定向爬虫获取新闻语料 → 基于 FinBERT-CRF 的命名实体识别 → 结合市场基本面构建面向情感分类的证券领域知识图谱"的完整框架，目标是把证券领域企业实体之间的情感影响关系可视化。本课题 RQ1 的"财经实体识别"环节需要中文证券领域的 NER 方案，该文的 FinBERT（金融领域预训练）+ CRF（标签转移约束）组合、以及"新闻→实体→图谱"的流水线，可作为中文财经实体抽取模块的选型与对照基线；其以新闻为唯一语料来源的做法，也对应本课题公告/新闻多源文本的实体抽取需求。
- 优先级：★★
- 核验状态：核验来源（1）汉斯出版社（Hans Publishers）《数据挖掘》期刊官网文章页（中文题名、作者任秋宇/刘佳芮、同济大学、2021 年 11 卷第 3 期 135–149、DOI 10.12677/HJDM.2021.113113013、ISSN 2163-145X/2163-1468、中英文摘要）；（2）Crossref DOI 记录 10.12677/HJDM.2021.113113013（英文题名 Knowledge Graph Construction Framework in the Securities Domain Based on FinBERT-CRF Named Entity Recognition Model，期刊 Hans Journal of Data Mining，卷 11、期 3、页 135–149，出版商 Hans Publishers）。全文已下载（期刊官方 PDF，`文献PDF/FIN-22_Ren2021_SecuritiesKG_FinBERT-CRF.pdf`，1,700,070 字节，文件头 `%PDF-`）。说明：该刊为开放获取中文期刊（非核心期刊），题录逐字取自期刊官网页面。

### [FIN-23] 张亚豪, 施水才, 王洪俊, 秦疆. 基于大语言模型的财务报告指标抽取智能体方法. 人工智能与机器人研究, 2025, 14(6): 1361-1371.
- URL: https://www.hanspub.org/journal/paperinformation?paperid=127738
- 相关性：针对财务年报"PDF 版式复杂 + 超长上下文"导致传统 RAG 的"单步、静态检索"在初始查询与文档表述不匹配时容易失败的问题，提出多智能体协作框架 **LedgerLens**：核心研究员智能体（Researcher Agent）以"检索—分析—精炼"迭代循环自主重构查询并多轮尝试，直至定位目标信息；在自建银行年报问答数据集 BAR-QA 上，指标抽取任务取得 94.1% F1。本课题 RQ1 的事件/指标抽取环节与 RQ2 的"检索失败"问题与其高度同构：一方面可借鉴其"LLM 抽取 + 结构化问答"的抽取式评测思路，另一方面其"检索脆弱性"诊断对应本课题失败案例归因中的"检索漏召回"一类。
- 优先级：★★
- 核验状态：核验来源（1）汉斯出版社《人工智能与机器人研究》期刊官网文章页（中文题名、作者张亚豪/施水才/王洪俊/秦疆、北京信息科技大学、2025 年 14 卷第 6 期 1361–1371、DOI 10.12677/airr.2025.146127、中英文摘要与关键词）；（2）Crossref DOI 记录 10.12677/airr.2025.146127（英文题名 Agent-Based Financial Report Indicator Extraction with Large Language Models、原始中文题名、卷 14、期 06、页 1361–1371，出版商 Hans Publishers）；（3）期刊官方全文 PDF 首页（出版信息、DOI、卷期页码一致）。全文已下载（期刊官方 PDF，`文献PDF/FIN-23_Zhang2025_FinancialReportIndicatorAgent.pdf`，873,927 字节，文件头 `%PDF-`）。

### [FIN-24] 唐晓波, 谭明亮, 胡潇然, 石文萱, 周巧. 面向金融决策支持的知识获取研究综述. 信息资源管理学报, 2020, 10(3): 27-35.
- URL: https://jirm.whu.edu.cn/jwk3/xxzyglxb/CN/10.13365/j.jirm.2020.03.027
- 相关性：中文综述，系统梳理面向金融决策支持的知识获取研究：数据源与获取方式、抽取与融合方法、知识组织与知识服务路线。本方向原有中文文献仅有 3 篇且集中在模型与评测，缺少"金融知识获取"的方法论综述；该文可补齐"国内外研究现状"中的中文引用与分类框架，用于说明本课题从多源财经文本到结构化知识的获取流程在既有研究脉络中的位置。属背景性支撑文献，不直接提供问答系统的技术方案。
- 优先级：★
- 核验状态：核验来源（1）《信息资源管理学报》期刊官网文章页（中文题名"面向金融决策支持的知识获取研究综述"、英文题名 A Review of Financial Decision-making Support-oriented Knowledge Acquisition、作者唐晓波/谭明亮/胡潇然/石文萱/周巧、2020 年第 10 卷第 3 期 27–35、DOI 10.13365/j.jirm.2020.03.027、ISSN 2095-2171、武汉大学主办）；（2）超星发现学术期刊条目（题名、《信息资源管理学报》、作者列表一致）；（3）期刊官网 PDF 下载链接（citation_pdf_url 指向该刊官方下载接口，已据此取得全文）。全文已下载（期刊官网 PDF，`文献PDF/FIN-24_Tang2020_FinanceKnowledgeAcquisitionReview.pdf`，800,606 字节，文件头 `%PDF-`）。

---

## 四、最新金融 KG 问答（FIN-25）

### [FIN-25] Haitao Cheng, Ke Wang, Qi Wang, Tao Liu, Kai Sheng. A Chinese financial event knowledge graph-based retrieval-augmented generation framework for financial question answering. Engineering Applications of Artificial Intelligence, 2026, 175: 114670.
- URL: https://doi.org/10.1016/j.engappai.2026.114670
- 相关性：与本课题同构度最高的最新工作。该框架面向中文金融领域问答，针对"专业术语复杂 + 多机构异构研报整合"的痛点，构建**中文金融事件知识图谱驱动的 RAG 框架**：①用语义感知切块 + 大模型驱动的三元组抽取构建结构化索引，并加入"生成—验证"机制保证抽取与检索的可靠性；②针对中文问句"表述隐含、词边界不清"导致的查询含糊，设计基于强化学习的**查询改写**模块生成领域化表述；③设计**双层检索**：先用语义相似度定位核心实体，再沿知识图谱做邻居扩展以展开事件链。实验在单跳、多跳、开放式三类问题与"全面性/多样性/赋能性/整体表现"四个维度上均优于基线。**为什么选它（补上了哪块空白）**：现有 FIN-15（Tao et al. 的 FinQA KGQA）面向通用金融图谱查询且以 NL2GQL 为主，FIN-KG 方向缺少"中文事件知识图谱 + 检索增强生成 + 多跳问答"三位一体的最新工作；该文正好补上"事件级图谱构建与图检索如何直接服务于中文金融问答"这一块，其双层检索（实体相似度 + 事件链邻居扩展）与本课题"0/1/2 跳 + 时间过滤"的检索策略、查询改写与证据融合设计可直接对照，故列为 FIN-25。
- 优先级：★★★
- 核验状态：核验来源（1）Crossref DOI 记录 10.1016/j.engappai.2026.114670（题名、5 位作者 Haitao Cheng / Ke Wang / Qi Wang / Tao Liu / Kai Sheng、期刊 Engineering Applications of Artificial Intelligence、卷 175、文章号 114670、2026 年 7 月、ISSN 0952-1976、出版商 Elsevier BV）；（2）OpenAlex（同 DOI，2026-03-31 上线、卷 175 页 114670，作者与题名一致，并给出摘要全文）；（3）Semantic Scholar（同 DOI 记录，2026-07-01、期刊同名，并给出 DBLP 键 journals/eaai/ChengWWLS26）。**全文获取状态：未获取全文（Elsevier 订阅付费墙；ScienceDirect 文章页返回反自动化验证页，未取得可核验的官方 PDF，故未下载、也不使用任何非官方来源版本）。** 注：OpenAlex 将第 4 作者写作 "Taowei Liu"，Crossref 与 Semantic Scholar 均写作 "Tao Liu"，题录按出版方登记的 Crossref 记录书写。

---

## 五、汇总表

| 编号 | 年份 | 出处 | 全文是否已下载 | 与本课题哪一部分对应 |
|------|------|------|---------------|---------------------|
| FIN-16 | 2021 | ACL-IJCNLP 2021（Volume 1: Long Papers），pp. 6663-6676，DOI 10.18653/v1/2021.acl-long.520 | 是（499,925 字节，`%PDF-` 校验通过） | H3、RQ3（时间过滤子集）、时序问答评测范式与指标分组 |
| FIN-17 | 2022 | AAAI-22, Proceedings of the AAAI Conference on Artificial Intelligence, 36(5): 5825-5833，DOI 10.1609/aaai.v36i5.20526 | 是（225,194 字节，`%PDF-` 校验通过） | H3、RQ3（时间感知子图检索）、相关工作（时序推理方法） |
| FIN-18 | 2024 | ACL 2024（Volume 2: Short Papers），pp. 445-458，DOI 10.18653/v1/2024.acl-short.42 | 是（2,047,669 字节，`%PDF-` 校验通过） | 相关工作（长文档金融问答）、评价指标（证据召回/长上下文推理） |
| FIN-19 | 2026 | arXiv:2603.19225，DOI 10.48550/arXiv.2603.19225 | 是（2,328,400 字节，`%PDF-` 校验通过） | 相关工作、RQ2/H1 的"零样本 vs 检索增强"分组对照设计、评价指标 |
| FIN-20 | 2026 | arXiv:2603.20252，DOI 10.48550/arXiv.2603.20252 | 是（1,205,856 字节，`%PDF-` 校验通过） | RQ2、评价指标（Faithfulness / 幻觉与忠实度评测）、风险三失败案例分析 |
| FIN-21 | 2024 | 运筹与管理, 33(2): 151-157，DOI 10.12005/orms.2024.0057 | 是（1,608,422 字节，`%PDF-` 校验通过） | 相关工作、RQ1（A股上市公司实体/关系建模） |
| FIN-22 | 2021 | 数据挖掘, 11(3): 135-149，DOI 10.12677/HJDM.2021.113113013 | 是（1,700,070 字节，`%PDF-` 校验通过） | RQ1（中文证券实体识别）、相关工作 |
| FIN-23 | 2025 | 人工智能与机器人研究, 14(6): 1361-1371，DOI 10.12677/airr.2025.146127 | 是（873,927 字节，`%PDF-` 校验通过） | RQ1（LLM 抽取与指标抽取评测）、相关工作（检索脆弱性归因） |
| FIN-24 | 2020 | 信息资源管理学报, 10(3): 27-35，DOI 10.13365/j.jirm.2020.03.027 | 是（800,606 字节，`%PDF-` 校验通过） | 相关工作（中文金融知识获取综述） |
| FIN-25 | 2026 | Engineering Applications of Artificial Intelligence, 175: 114670，DOI 10.1016/j.engappai.2026.114670 | 否（Elsevier 订阅付费墙，未取得官方全文） | RQ2（KG 增强检索增益）、RQ3（双层图检索策略）、相关工作（最新中文金融事件 KG 问答） |

---

## 六、核验失败条目

本次 10 条线索（FIN-16 ～ FIN-25）**全部核验成功，无核验失败条目**，因此不占用任何编号占位。仅以下两项需要在合并时注意，均不属于核验失败：

1. **FIN-16 的线索会议信息有误**：线索写"CronKGQA（Saxena et al., EMNLP 2021 左右）"，实际该文以 "Question Answering Over Temporal Knowledge Graphs" 为题发表于 **ACL-IJCNLP 2021** 长文（pp. 6663-6676），其中提出 CRONQUESTIONS 基准与 CRONKGQA 模型；文献真实存在且可核验，题录已按 ACL Anthology 官方页书写。
2. **FIN-17 的线索会议与年份有误**：线索写"TempoQR（Mavromatis & Karypis, ACL 2023 左右）"，实际发表于 **AAAI-22（2022）**，作者共 8 位（含 George Karypis），题录与文件名年份已按 Crossref/OpenAlex 核验结果取 2022。
3. **FIN-25 未取得全文**：该文为 Elsevier 期刊论文，属订阅付费墙且 ScienceDirect 文章页触发反自动化验证，未下载任何非官方来源版本；题录本身已由 Crossref、OpenAlex 与 Semantic Scholar 三源交叉核验。
