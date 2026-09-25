# 方向二：RAG（检索增强生成）文献调研

> 课题：基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现
> 检索时间：2026-09-22
> 文献总量：15篇（英文13篇，中文2篇；另有 2026-09 补充文献 12 篇，见文末"补充文献"章节，合计 27 篇）
> 核验方式：通过 arXiv、Semantic Scholar、ACL Anthology、NeurIPS Proceedings、IEEE Xplore、软件学报官网等多源交叉核验标题+作者+年份+出处一致性

---

## 一、RAG基础与经典方法

### [1] Patrick Lewis, Ethan Perez, Aleksandra Piktus, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS 2020.
- URL: https://arxiv.org/abs/2005.11401
- NeurIPS: https://papers.neurips.cc/paper/2020/hash/6b493230205f780e1bc26945df7481e5-Abstract.html
- 相关性：RAG原始奠基论文，提出参数化记忆（seq2seq）+非参数化记忆（稠密向量索引）的通用框架。本课题普通向量RAG baseline（文本切分→Embedding→FAISS→LLM生成）的理论源头，必须在开题报告"国内外研究现状"中引用。
- 优先级：★★★
- 核验状态：已通过arXiv摘要页、NeurIPS Proceedings官方页面、Semantic Scholar三源交叉核验，作者列表、年份、会议均一致。

### [2] Akari Asai, Zeqiu Wu, Yizhong Wang, Avirup Sil, Hannaneh Hajishirzi. Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection. ICLR 2024.
- URL: https://arxiv.org/abs/2310.11511
- 相关性：提出"反思token"机制，使LLM按需自适应检索并对生成结果做相关性/支持性/完整性评判。为本课题的Faithfulness评估和证据融合排序环节提供设计参考——检索结果质量可被显式评估后再决定是否采纳。
- 优先级：★★
- 核验状态：已通过arXiv PDF原文、Semantic Scholar（标注ICLR 2024）、selfrag.github.io项目主页三源核验。

### [3] Shi-Qi Yan, Jia-Chen Gu, Yun Zhu, Zhen-Hua Ling. Corrective Retrieval Augmented Generation. arXiv:2401.15884, 2024.
- URL: https://arxiv.org/abs/2401.15884
- 相关性：提出轻量级检索评估器（retrieval evaluator）对检索文档质量打分，触发Correct/Incorrect/Ambiguous三种纠正动作。本课题在KG增强混合检索中引入"证据融合排序"与检索质量过滤，可借鉴其置信度判定思路。
- 优先级：★★
- 核验状态：已通过arXiv PDF原文、Semantic Scholar（DOI: 10.48550/arXiv.2401.15884）、OpenReview三源核验，作者为USTC+UCLA+Google Research团队。

### [4] Yunfan Gao, Yun Xiong, Xinyu Gao, et al. Retrieval-Augmented Generation for Large Language Models: A Survey. arXiv:2312.10997, 2023.
- URL: https://arxiv.org/abs/2312.10997
- 相关性：RAG领域高引用综述，系统梳理Naive RAG→Advanced RAG→Modular RAG演进脉络，涵盖检索器、生成器、查询改写、重排序等模块。适合作为开题报告"RAG技术发展脉络"的框架性引用。
- 优先级：★★
- 核验状态：已通过arXiv摘要页及多篇引用文献交叉确认作者为Gao et al.，arXiv编号2312.10997无误。

---

## 二、向量检索与稠密检索

### [5] Vladimir Karpukhin, Barlas Oğuz, Sewon Min, Patrick Lewis, et al. Dense Passage Retrieval for Open-Domain Question Answering. EMNLP 2020.
- URL: https://arxiv.org/abs/2004.04906
- 相关性：DPR经典论文，提出双编码器（bi-encoder）架构分别编码问题和文档，是稠密向量检索的里程碑。本课题Embedding模型选型与向量检索baseline的直接方法依据。
- 优先级：★★★
- 核验状态：已通过arXiv摘要页、Semantic Scholar（EMNLP 2020）、NASA ADS三源核验，作者列表及年份一致。

### [6] Nils Reimers, Iryna Gurevych. Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks. EMNLP-IJCNLP 2019, pp. 3982-3992.
- URL: https://arxiv.org/abs/1908.10084
- 相关性：提出句向量表示双塔结构，是当前RAG系统中Embedding模型（all-MiniLM、BGE等系列）的技术源头。本课题文本切分后做Embedding向量化的直接参考。
- 优先级：★★
- 核验状态：已通过EMNLP-IJCNLP 2019论文集页码（3982-3992）及SCIRP参考文献条目核验。

### [7] Jeff Johnson, Matthijs Douze, Hervé Jégou. Billion-scale similarity search with GPUs. IEEE Transactions on Big Data, 7(3): 535-547, 2021.
- URL: https://arxiv.org/abs/1702.08734
- DOI: 10.1109/TBDATA.2019.2921572
- 相关性：FAISS库原始论文，提出IVF/PQ等百亿级向量近似最近邻索引算法。本课题使用FAISS做向量检索的直接技术依据，需在系统实现章节引用。
- 优先级：★★★
- 核验状态：已通过IEEE Xplore（文档号8733051，7卷3期535-547页）、FAISS官网文档、PyPI faiss-cpu引用条目三源核验。

---

## 三、混合检索

### [8] Gordon V. Cormack, Charles L. A. Clarke, Stefan Büttcher. Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods. SIGIR 2009, pp. 758-759.
- DOI: 10.1145/1571941.1572114
- URL: https://dl.acm.org/doi/pdf/10.1145/1571941.1572114
- 相关性：提出RRF（倒数秩融合）算法，仅依赖排名位置即可融合多路检索结果，是当前BM25+向量混合检索的事实标准融合方法。本课题"向量检索+知识图谱检索"的证据融合排序可直接借鉴RRF公式。
- 优先级：★★
- 核验状态：已通过ACM Digital Library原文PDF、Google Scholar（Clarke个人主页引用，被引1729次）、TREC技术报告引用三源核验。

---

## 四、GraphRAG与知识图谱增强RAG

### [9] Darren Edge, Ha Trinh, Newman Cheng, et al. From Local to Global: A Graph RAG Approach to Query-Focused Summarization. arXiv:2404.16130, 2024.
- URL: https://arxiv.org/abs/2404.16130
- 相关性：微软GraphRAG开创性论文，提出从文本构建实体知识图谱→社区检测→社区摘要→全局查询回答的两阶段pipeline。本课题"KG增强混合检索"的核心对标方法，需在国内外研究现状中详细对比。
- 优先级：★★★
- 核验状态：已通过arXiv PDF原文、graphrag.com官方项目站、NASA ADS三源核验，作者为Microsoft Research团队（8人）。

### [10] Bernal Jimenez Gutierrez, Yiheng Shu, Yu Gu, Michihiro Yasunaga, Yu Su. HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language Models. NeurIPS 2024.
- URL: https://arxiv.org/abs/2405.14831
- 相关性：受海马体索引理论启发，将LLM+知识图谱+Personalized PageRank结合，在单步检索中实现多跳推理。本课题设计"0跳/1跳/2跳/时间过滤"四级图检索策略，HippoRAG的PPRank图遍历思路是直接方法参考。
- 优先级：★★★
- 核验状态：已通过arXiv PDF原文（2405.14831）、NeurIPS 2024论文集（vol.37, pp.59532-59569）、AWS技术博客三源核验。

---

## 五、RAG评价方法与框架

### [11] Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert. Ragas: Automated Evaluation of Retrieval Augmented Generation. arXiv:2309.15217, 2023.
- URL: https://arxiv.org/abs/2309.15217
- 相关性：RAGAS框架提出无参考（reference-free）评估指标体系：Context Precision（检索精确率）、Context Recall（证据召回率）、Faithfulness（忠实度）、Answer Relevance。本课题检索指标（Recall@K/Evidence Recall）与问答指标（Faithfulness）的设计直接对标RAGAS。
- 优先级：★★★
- 核验状态：已通过arXiv摘要页（作者：Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert）、arXiv HTML全文、多篇后续RAG评估论文引用交叉核验。

### [12] Jon Saad-Falcon, Omar Khattab, Christopher Potts, Matei Zaharia. ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems. arXiv:2311.09476, 2023.
- URL: https://arxiv.org/abs/2311.09476
- 相关性：ARES框架提出基于PPI（隐变量模型）的RAG系统自动评估方法，在Context Relevance和Answer Relevance排序上优于RAGAS。为本课题实验部分选择评估框架提供备选参考。
- 优先级：★★
- 核验状态：已通过arXiv PDF原文（Stanford+Databricks团队，四位作者姓名及邮箱可见）、多篇引用文献交叉核验。

---

## 六、多跳问答与证据检索

### [13] Zhilin Yang, Peng Qi, Saizheng Zhang, Yoshua Bengio, William W. Cohen, Ruslan Salakhutdinov, Christopher D. Manning. HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering. EMNLP 2018.
- URL: https://arxiv.org/abs/1809.09600
- 相关性：多跳问答领域最经典基准数据集，11.3万Wikipedia问答对，提供支撑句（supporting facts）标注。本课题设计2跳/多跳财经问题及Evidence Recall指标的设计范式直接参考HotpotQA的支撑事实标注方式。
- 优先级：★★★
- 核验状态：已通过arXiv PDF原文、hotpotqa.github.io官方项目站（CMU+Stanford+Université de Montréal）、EMNLP 2018论文集三源核验。

### [14] Harsh Trivedi, Niranjan Balasubramanian, Tushar Khot, Ashish Sabharwal. MuSiQue: Multihop Questions via Single-hop Question Composition. TACL 2022.
- URL: https://arxiv.org/abs/2108.00573
- ACL Anthology: https://aclanthology.org/2022.tacl-1.31/
- 相关性：提出2-4跳多跳问答数据集，通过组合单跳问题构造，消除shortcut作弊路径。本课题消融实验中测试"逐跳增加图检索"效果，可借鉴MuSiQue的跳数控制与支撑段落标注方法。
- 优先级：★★
- 核验状态：已通过ACL Anthology官方页面（2022.tacl-1.31）、TACL期刊官网、Google Scholar（Trivedi个人主页）三源核验。

---

## 七、中文综述

### [15] 刘澳迪, 奚雪峰, 周国栋. 面向大语言模型生成能力提升的检索增强生成研究进展. 软件学报.
- URL: https://www.jos.org.cn/jos/article/abstract/7684
- DOI: 10.13328/j.cnki.jos.007684
- 相关性：《软件学报》（CCF A类中文期刊）RAG综述，系统分类检索方法与增强生成技术路径，涵盖外部知识库、提示工程等方向。适合作为开题报告中文文献支撑，体现对国内研究现状的把握。
- 优先级：★★★
- 核验状态：已通过软件学报官网（jos.org.cn）文章摘要页核验，作者单位为苏州科技大学+苏州大学，基金号（国家自然科学基金62376178等）可见。

---

## 阅读顺序建议

### 第一阶段：建立RAG全局认知（约1周）
1. **[4] Gao et al. RAG Survey** — 先读综述，建立Naive→Advanced→Modular RAG的演进框架
2. **[15] 刘澳迪等. 软件学报综述** — 中文视角补充，了解国内分类体系
3. **[1] Lewis et al. RAG原始论文** — 精读RAG开山之作，理解参数化+非参数化记忆的核心思想

### 第二阶段：掌握检索技术细节（约1周）
4. **[5] Karpukhin et al. DPR** — 理解双编码器稠密检索原理
5. **[6] Reimers & Gurevych. Sentence-BERT** — 理解句向量Embedding技术
6. **[7] Johnson et al. FAISS** — 掌握向量索引与近似最近邻算法
7. **[8] Cormack et al. RRF** — 掌握多路结果融合的经典方法

### 第三阶段：深入GraphRAG与多跳推理（约1周）
8. **[9] Edge et al. GraphRAG（微软）** — 精读核心对标方法，理解实体KG+社区摘要pipeline
9. **[10] Gutierrez et al. HippoRAG** — 理解KG+Personalized PageRank多跳检索
10. **[13] Yang et al. HotpotQA** — 理解多跳问答任务定义与支撑事实标注
11. **[14] Trivedi et al. MuSiQue** — 理解跳数可控的多跳数据构造方法

### 第四阶段：掌握评估方法与改进范式（约3-5天）
12. **[11] Es et al. RAGAS** — 精读指标定义（Context Precision/Recall/Faithfulness），直接用于实验设计
13. **[12] Saad-Falcon et al. ARES** — 了解备选评估框架
14. **[2] Asai et al. Self-RAG** — 理解检索质量自适应评估思路
15. **[3] Yan et al. CRAG** — 理解检索纠错机制设计

---

## 最值得写入开题报告"国内外研究现状"的核心文献清单（★★★）

| 序号 | 文献 | 对应课题环节 |
|------|------|-------------|
| [1] | Lewis et al. RAG (NeurIPS 2020) | RAG理论源头，baseline框架 |
| [5] | Karpukhin et al. DPR (EMNLP 2020) | 稠密向量检索方法依据 |
| [7] | Johnson et al. FAISS (IEEE TBD 2021) | FAISS向量检索技术依据 |
| [9] | Edge et al. GraphRAG (arXiv 2024) | KG增强RAG核心对标方法 |
| [10] | Gutierrez et al. HippoRAG (NeurIPS 2024) | 图遍历多跳检索方法参考 |
| [11] | Es et al. RAGAS (arXiv 2023) | RAG评估指标体系直接对标 |
| [13] | Yang et al. HotpotQA (EMNLP 2018) | 多跳问答任务与证据标注范式 |
| [15] | 刘澳迪等. 软件学报综述 | 国内研究现状中文支撑 |

> 以上8篇★★★文献建议在开题报告"国内外研究现状"章节中逐一引用并展开论述，其余★★/★文献可在相关段落作为补充引用。

---

## 补充文献（2026-09 扩充，RAG-16 ～ RAG-27）

本次扩充的原因有四：① 原池 2025 年文献只有 1 篇，年份断档；② A股/中文金融专属文献仅 1 篇，方向过薄；③ 课题新增的两项决策缺少文献支撑——200 条抽取评测集缺 DocEE 系列/MAVEN-ERE 的标注体系、时序检索缺 CronKGQA/TempoQR 类基准；④ GraphRAG 家族与忠实度评测缺位。新条目同样经过多源交叉核验：40 条新增文献中 38 条已获取全文，2 条（RAG-22、FIN-25）因付费墙或官方下载接口限制仅有题录。本方向新增 12 条（RAG-16 ～ RAG-27），其中 11 条已获取全文，RAG-22 未获取全文（期刊官网 PDF 下载接口返回 403）。

### [RAG-16] Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, Chao Huang. LightRAG: Simple and Fast Retrieval-Augmented Generation. arXiv:2410.05779, 2024.
- URL: https://arxiv.org/abs/2410.05779
- 相关性：提出"双层图索引（低层实体与关系细节 + 高层主题关键词）+ 关键字与向量双路检索"的轻量图结构 RAG 框架，以增量更新替代微软 GraphRAG 的社区全量重建，构建与检索开销显著更低。本课题的 A 股公告/新闻需按日增量入库，LightRAG 代表"轻量图索引 + 双路检索"路线：它不构建事件本体、不显式建模时间语义，也不做图谱路径与文本证据的联合追溯，因此是说明本课题"事件中心化 + 四类时间 + 0/1/2 跳图检索"差异的主要对照之一。
- 优先级：★★
- 核验状态：已通过 arXiv 官方 API 与 arXiv 摘要页（arXiv:2410.05779，5 位作者，2024-10-08 首次提交）、DataCite DOI 注册记录（10.48550/arXiv.2410.05779，题名/作者/年份一致）、OpenReview 官方条目（CoRR 2024 记录 id iwZQkMk3r2，另有 ACL ARR 2024 December Submission 记录）三源交叉核验，截至核验日未见正式会议或期刊收录记录。全文已下载（arXiv 开放版，16 页，1,123,301 字节，文件头 %PDF- 校验通过）。

### [RAG-17] Shengjie Ma, Chengjin Xu, Xuhui Jiang, Muzhi Li, Huaren Qu, Cehao Yang, Jiaxin Mao, Jian Guo. Think-on-Graph 2.0: Deep and Faithful Large Language Model Reasoning with Knowledge-guided Retrieval Augmented Generation. ICLR 2025 (Poster); arXiv:2407.10805, 2024.
- URL: https://arxiv.org/abs/2407.10805
- 相关性：把"知识图谱上的实体探索"与"文档段落检索"编织为统一过程，用超链接把图上的关系推理结果与原文段落对齐，兼顾深层多跳推理与证据可追溯，缓解纯图检索的"事实粒度损失"。其"图遍历 + 原文证据绑定"与本课题"图谱路径 + 文本证据联合追溯"的输出设计直接相关；但该工作面向通用百科多跳问答，不含 A 股事件类型体系与时间过滤约束，可作为说明本课题差异的技术对照。
- 优先级：★★
- 核验状态：已通过 arXiv 官方 API 与 arXiv 摘要页（arXiv:2407.10805，8 位作者，2024-07-15 首次提交）、DataCite DOI 注册记录（10.48550/arXiv.2407.10805，题名/作者/年份一致）、OpenReview 官方页面（ICLR 2025 Poster，forum id oFBu7qaZpS）三源交叉核验；论文 PDF 首页页眉标注 "Published as a conference paper at ICLR 2025"，与 OpenReview 记录一致。全文已下载（arXiv 开放版，25 页，2,301,111 字节，文件头 %PDF- 校验通过）。

### [RAG-18] Boci Peng, Yun Zhu, Yongchao Liu, Xiaohe Bo, Haizhou Shi, Chuntao Hong, Yan Zhang, Siliang Tang. Graph Retrieval-Augmented Generation: A Survey. arXiv:2408.08921, 2024.
- URL: https://arxiv.org/abs/2408.08921
- 相关性：目前体系化程度较高的图检索增强生成综述，提出"图索引构建 → 图引导检索 → 图增强生成"三阶段框架，并按图类型、检索粒度与增强方式对 GraphRAG 家族（微软 GraphRAG、HippoRAG、LightRAG、Think-on-Graph 等）做统一分类。可在开题报告"国内外研究现状"中一次性交代图谱增强 RAG 的技术谱系与各家差异，进而精确定位本课题"事件驱动、时间约束、证据可追溯"三点的差异与贡献。
- 优先级：★★★
- 核验状态：已通过 arXiv 官方 API 与 arXiv 摘要页（arXiv:2408.08921，8 位作者，2024-08-15 首次提交）、DataCite DOI 注册记录（10.48550/arXiv.2408.08921）、OpenReview 官方条目（CoRR 2024 记录 id 9ldXNHQFMl）三源交叉核验，作者列表（Boci Peng, Yun Zhu, Yongchao Liu, Xiaohe Bo, Haizhou Shi, Chuntao Hong, Yan Zhang, Siliang Tang）与题名一致，另以论文 PDF 首页作者与单位行复核一致。全文已下载（arXiv 开放版，41 页，1,725,790 字节，文件头 %PDF- 校验通过）。

### [RAG-19] 周俭航, 肖诗斌. 图检索增强生成研究综述. 人工智能与机器人研究, 2025, 14(2): 402-413.
- URL: https://www.hanspub.org/journal/paperinformation?paperid=110077
- 相关性：中文图检索增强生成综述，围绕 GraphRAG 的知识组织、图检索与生成环节梳理代表性工作与技术路线，可作为开题报告中文文献层面对"图谱增强 RAG 家族"的补充说明，与 RAG-18（英文综述）形成中英对照引用。
- 优先级：★★
- 核验状态：已通过汉斯出版社官网文章页（paperid=110077，页面载明"文章引用：周俭航, 肖诗斌. 图检索增强生成研究综述[J]. 人工智能与机器人研究, 2025, 14(2): 402-413"与 DOI 10.12677/airr.2025.142040）、Crossref DOI 元数据记录（登记题名 Review of Graph Retrieval-Augmented Generation Research、期刊 Artificial Intelligence and Robotics Research、卷 14 期 02、页码 402-413、出版年 2025）双源交叉核验，作者名单另由期刊官网页面与论文 PDF 首页共同确认。全文已下载（期刊开放获取版，12 页，3,104,466 字节，文件头 %PDF- 校验通过）。

### [RAG-20] 李子骏, 肖辉, 李雪峰. 面向知识密集型任务的检索增强生成技术综述. 微电子学与计算机, 2025, 42(10): 48-65.
- URL: https://mc.spacejournal.cn/article/doi/10.19304/J.ISSN1000-7180.2025.0652
- 相关性：面向知识密集型任务的中文 RAG 技术综述，按"检索器—生成器—检索与生成协同机制"三层拆解关键组件，并把 GraphRAG、工具增强型语言模型、检索增强指令微调并列为 RAG 变体，同时归纳应用场景与评估要点。其组件化拆解口径可直接支撑本课题"向量检索 + 图谱检索 + 证据融合"模块的技术叙述，评估部分的归纳亦为第 12 章指标设计提供中文对照。
- 优先级：★★
- 核验状态：已通过《微电子学与计算机》期刊官网文章页（citation_title=面向知识密集型任务的检索增强生成技术综述，citation_author=李子骏/肖辉/李雪峰，citation_volume=42，citation_issue=10，citation_firstpage=48，citation_lastpage=65，citation_doi=10.19304/J.ISSN1000-7180.2025.0652，citation_year=2025）、中国 DOI 注册解析页（chndoi.org 显示题名、作者"李子骏;肖辉;李雪峰"、DOI 与注册机构同方知网）、中国知网文献页（kns.cnki.net 文章页题名与章节结构一致）三源交叉核验，另以论文 PDF 首页"引用格式"复核一致。全文已下载（期刊官网开放获取版，18 页，777,718 字节，文件头 %PDF- 校验通过）。

### [RAG-21] 田永林, 王雨桐, 王兴霞, 杨静, 沈甜雨, 王建功, 范丽丽, 郭超, 王寿文, 赵勇, 武万森, 王飞跃. 从RAG到SAGE: 现状与展望. 自动化学报, 2025, 51(6): 1145-1169.
- URL: https://www.aas.net.cn/cn/article/doi/10.16383/j.aas.c240163
- 相关性：《自动化学报》RAG 综述，除梳理 RAG 基本原理、发展现状与医疗/法律/金融等典型应用外，进一步提出结合搜索模块与多级缓存管理的扩展框架 SAGE，指向"灵活高效的大模型知识外挂工具链"。可用于论证本课题服务层"向量检索 + 图谱检索 + 结果缓存"的工程化趋势，并为第 12 章讨论检索延迟与成本提供中文文献支撑。
- 优先级：★★
- 核验状态：已通过《自动化学报》官网文章页（aas.net.cn 文章页题名"从RAG到SAGE: 现状与展望"）、中国科技期刊平台（sciengine.com）官方 PDF 首页"引用格式"（田永林等. 从RAG 到SAGE: 现状与展望. 自动化学报, 2025, 51(6): 1145−1169，DOI 10.16383/j.aas.c240163）、中国 DOI 解析链路（chndoi.org，DOI 10.16383/j.aas.c240163）三源交叉核验，12 位作者名单、卷期与页码一致。全文已下载（sciengine 官方 PDF，25 页，2,699,006 字节，文件头 %PDF- 校验通过）。

### [RAG-22] 刘雪颖, 云静, 李博, 史晓国, 张钰莹. 基于大型语言模型的检索增强生成综述. 计算机工程与应用, 2025, 61(13): 1-25.
- URL: http://cea.ceaj.org/CN/10.3778/j.issn.1002-8331.2410-0088
- 相关性：以智能体范式为视角组织的中文 RAG 综述，阐述 RAG 基本概念与工作流程，归纳检索与生成技术现状，梳理评估指标、数据集与基准，并讨论 GraphRAG 等变体与未来挑战。适合作为本课题"相关工作 + 评价指标"两部分的中文支撑，与 RAG-15、RAG-19～RAG-21 共同构成国内研究现状的引用面。
- 优先级：★★
- 核验状态：已通过《计算机工程与应用》期刊官网文章页（cea.ceaj.org，含 citation_volume=61、citation_issue=13、页码 1-25、DOI 10.3778/j.issn.1002-8331.2410-0088 与官方"引用本文"格式）、该刊官网 2025 年第 61 卷第 13 期目录页、中国知网"知网空间"文章页（cnki.com.cn/Article/CJFDTotal-JSGG202513001.htm，题名与刊物年期一致）三源交叉核验，5 位作者（刘雪颖, 云静, 李博, 史晓国, 张钰莹）一致。未获取全文（期刊官网 PDF 下载接口 downloadArticleFile.do 在本环境返回 403 禁止访问，且无其他开放版本；该刊为开放获取，建议在校内网络环境或浏览器中直接下载）。

### [RAG-23] Tianyu Gao, Howard Yen, Jiatong Yu, Danqi Chen. Enabling Large Language Models to Generate Text with Citations. EMNLP 2023, pp. 6465-6488.
- URL: https://aclanthology.org/2023.emnlp-main.398/
- 相关性：提出"带引文生成"的任务设定与 ALCE 自动评测基准（ASQA、QAMPARI、ELI5 三个数据集），用 Fluency、Correctness、Citation Precision/Recall 四类自动指标同时度量答案质量与引用质量，并给出自动评测器。本课题第 12.7 节采用人工 0/1/2 的 Faithfulness 评分，ALCE 的引文精确率/召回率定义可作为"答案句是否被检索证据支持"的自动化交叉验证口径，直接服务于本课题"答案 + 文本证据 + 图谱路径"的证据可追溯目标。
- 优先级：★★
- 核验状态：已通过 ACL Anthology 官方页面（aclanthology.org/2023.emnlp-main.398，含 citation_title、4 位 citation_author、citation_pages=6465–6488、citation_doi=10.18653/v1/2023.emnlp-main.398）、ACL Anthology EMNLP 2023 主会卷目录页（题名与作者一致）、arXiv 摘要页（arXiv:2305.14627，注释标明 "Accepted by EMNLP 2023"）三源交叉核验，题名、作者（Tianyu Gao, Howard Yen, Jiatong Yu, Danqi Chen）、会议与页码一致。全文已下载（ACL Anthology 开放版，24 页，481,920 字节，文件头 %PDF- 校验通过）。

### [RAG-24] Sewon Min, Kalpesh Krishna, Xinxi Lyu, Mike Lewis, Wen-tau Yih, Pang Wei Koh, Mohit Iyyer, Luke Zettlemoyer, Hannaneh Hajishirzi. FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation. EMNLP 2023, pp. 12076-12100.
- URL: https://aclanthology.org/2023.emnlp-main.741/
- 相关性：把长文本生成拆解为原子事实并逐条核验，以"被知识源支持的原子事实比例"（FActScore）度量事实精度，同时给出可复现的自动评测器与人物传记评测集，揭示当时最优模型的事实精度仍显著低于人类。其"细粒度、逐条可核验"的评测粒度与本课题第 12.7 节人工 0/1/2 Faithfulness 评分最接近，可用于交叉验证人工评分的一致性，并为"答案句—证据来源"对齐的评测设计提供直接参照。
- 优先级：★★★
- 核验状态：已通过 ACL Anthology 官方页面（aclanthology.org/2023.emnlp-main.741，含 citation_title、9 位 citation_author、citation_pages=12076–12100、citation_doi=10.18653/v1/2023.emnlp-main.741）、ACL Anthology EMNLP 2023 主会卷目录页（该页题名含固定大小写标记，与页面标题一致）、arXiv 摘要页（arXiv:2305.14251，注释标明 "Published as a main conference paper at EMNLP 2023"）三源交叉核验，题名、作者列表、会议与页码一致。全文已下载（ACL Anthology 开放版，25 页，2,409,424 字节，文件头 %PDF- 校验通过）。

### [RAG-25] Xiao Yang, Kai Sun, Hao Xin, Yushi Sun, Nikita Bhalla, Xiangsen Chen, et al. CRAG - Comprehensive RAG Benchmark. NeurIPS 2024 (Datasets and Benchmarks Track).
- URL: https://proceedings.neurips.cc/paper_files/paper/2024/hash/1435d2d0fca85a84d83ddcb754f58c29-Abstract-Datasets_and_Benchmarks_Track.html
- 相关性：面向真实问答多样性与动态性的综合 RAG 基准，含 4,409 组问答与模拟 Web / 知识图谱检索的 mock API，按五个领域、八类问题、实体热度与时效动态性（数年跨度到秒级）分层评测；结果显示主流 LLM 准确率不超过 34%，朴素接入 RAG 仅提升至 44%，且时效性越高、热度越低、复杂度越高则准确率越低。本课题 A 股问答同样具有强时效性（公告与政策的当日生效），可直接借鉴其"按时效动态性分层 + 检索与生成联合评测"的设计，用于构造 RQ2/RQ3 的分层测试集与消融方案。
- 优先级：★★
- 核验状态：已通过 NeurIPS 官方论文集页面（proceedings.neurips.cc 2024 Datasets and Benchmarks Track 摘要页，标注 Advances in Neural Information Processing Systems 37 (NeurIPS 2024)、Datasets and Benchmarks Track 与 DOI 10.52202/079017-0335）、arXiv 摘要页（arXiv:2406.04744，注释标明 "NeurIPS 2024 Datasets and Benchmarks Track"）与官方论文 PDF 首页（27 位作者列表，Xiao Yang, Kai Sun, …, Xin Luna Dong）三源交叉核验；已确认该条与 RAG-3（Yan et al. 的 Corrective Retrieval Augmented Generation，arXiv:2401.15884）为不同文献（作者、题名、出处、年份均不同）。全文已下载（NeurIPS 官方 PDF，21 页，884,186 字节，文件头 %PDF- 校验通过）。

### [RAG-26] 何金骍, 王洪俊. 大语言模型幻觉研究综述. 人工智能与机器人研究, 2026, 15(1): 156-167.
- URL: https://www.hanspub.org/journal/paperinformation?paperid=132765
- 相关性：中文幻觉研究综述，梳理大语言模型幻觉的定义、成因分类、检测与缓解方法，其中检索增强（RAG）与图结构增强（GraphRAG）在缓解幻觉上的作用与局限、以及知识库增量更新的讨论，与课题动机直接相关。可用于论证"检索增强能降低但无法消除幻觉"，从而说明本课题在生成端仍保留人工 Faithfulness 评分与证据追溯机制的必要性。
- 优先级：★★
- 核验状态：已通过汉斯出版社官网文章页（paperid=132765，页面载明"文章引用：何金骍, 王洪俊. 大语言模型幻觉研究综述[J]. 人工智能与机器人研究, 2026, 15(1): 156-167"与 DOI 10.12677/airr.2026.151016）、Crossref DOI 元数据记录（登记题名 A Survey of Hallucination in Large Language Models、期刊 Artificial Intelligence and Robotics Research、卷 15 期 01、页码 156-167、出版年 2026）双源交叉核验，作者名单另由期刊官网页面与论文 PDF 首页共同确认。全文已下载（期刊开放获取版，12 页，701,917 字节，文件头 %PDF- 校验通过）。

### [RAG-27] Siyuan Chen, Huaye Tan, You Li, Jiajun Liang. HC-RAG: Evidence-Centric Retrieval-Augmented Generation over Heterogeneous Financial Filings. arXiv:2608.12335, 2026.
- URL: https://arxiv.org/abs/2608.12335
- 相关性：面向财报长文档的证据中心 RAG 框架，把申报文件组织为含文档、章节、文本单元、表格单元与元数据节点的"类型化金融证据图"，沿"文档—章节—单元"路径检索证据，在共享检索空间中对齐文本与表格证据，并按计算/趋势/事实/对比四类语义意图路由证据；同时发布 Multi-Doc-2025 基准（179 份 SEC 10-K、87 家标普 500 公司、2,327 组人工核验问答）。与本课题"公告长文档证据检索 + 图表/文本混合 + 多跳与时序问答"最为接近，其证据定位评测口径可直接对照本课题的 Evidence Recall 与图谱路径命中率设计，是 RQ2/RQ3 的重要对标工作。
- 优先级：★★★
- 核验状态：已通过 arXiv 官方 API 与 arXiv 摘要页（arXiv:2608.12335，4 位作者，2026-06-03 首次提交）、DataCite DOI 注册记录（10.48550/arXiv.2608.12335，题名/作者/年份一致）、论文 PDF 首页作者与单位信息三源交叉核验，题名与作者（Siyuan Chen, Huaye Tan, You Li, Jiajun Liang）完全一致。全文已下载（arXiv 开放版，16 页，1,230,566 字节，文件头 %PDF- 校验通过）。
