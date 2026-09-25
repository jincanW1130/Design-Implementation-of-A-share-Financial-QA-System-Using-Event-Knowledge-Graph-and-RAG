# RAG 方向补充文献候选（RAG-16 ～ RAG-27）

> 课题：基于事件知识图谱与RAG的A股财经信息智能问答系统设计与实现
> 补充日期：2026-09-23
> 编号范围：RAG-16 ～ RAG-27（共 12 条）

本文件为 RAG 方向（方向二）的**补充候选条目**，用于补齐现有 RAG-1～RAG-15 的三类缺口：

1. **图谱增强 RAG 家族**（RAG-16～RAG-18）：现有池中仅有 RAG-9（微软 GraphRAG）与 RAG-10（HippoRAG），不足以支撑开题报告中"本课题与 GraphRAG 家族的区别"这一论证；本次补齐轻量图索引路线（LightRAG）、图与文档证据交织推理路线（Think-on-Graph 2.0）以及该家族的系统性综述，使技术谱系完整。
2. **中文综述与 2025–2026 最新进展**（RAG-19～RAG-22）：在 RAG-15（软件学报综述）之外，补充 2025 年发表的图检索增强生成综述、知识密集型任务 RAG 综述、"从 RAG 到 SAGE"趋势综述与大型语言模型 RAG 综述，强化开题报告中文文献支撑与国内研究现状叙述。
3. **忠实度与引文评测**（RAG-23～RAG-25）：补充带引文生成的自动评测基准（ALCE）、长文本事实精度细粒度评测（FActScore）与综合 RAG 基准（CRAG），用于与论文第 12.7 节人工 0/1/2 的 Faithfulness 评分做交叉验证，并为检索与生成的分层评测提供外部参照。另收录 2026 年幻觉研究综述（RAG-26）与面向金融长文档的证据中心 RAG 工作（RAG-27），分别对应"幻觉抑制"论证与"证据检索"最接近的对标系统。

**核验方法**：每条文献均采用**至少 2 个相互独立来源**交叉核验作者列表、题名、出处、年份，来源包括 arXiv 官方 API 与摘要页、ACL Anthology 官方页面与卷目录、NeurIPS 官方论文集、OpenReview 官方页面、DataCite DOI 注册记录、Crossref DOI 元数据、期刊官网文章页与卷期目录、中国 DOI 注册解析页（chndoi.org）、中国知网文献页等；题录文字逐字取自核验到的真实页面，未做推断性补全。可开放获取的全文已下载至 `文献调研/文献PDF/`，文件名遵循 `{编号}_{第一作者姓}{年份}_{短标题}.pdf` 规范，并逐条按"以 `%PDF-` 开头且字节数 > 20000"校验，且以 PDF 首页文本复核文献身份。

按任务约定，检索表第 4 行的 `Towards Faithful Industrial RAG: A Reinforced Co-adaptation Framework for Advertising QA` 归其他协作者，本文件未收录；DocEE、事理图谱综述、HalluBench、DocFinQA 等其他方向条目亦未收录。

> **本条目的收录与否待主控核验后合并入方向二文档。** 本文件仅为补充候选，未修改 `方向二_RAG文献.md` 及任何既有文件；编号 RAG-16～RAG-27 连续，与现有 56 条（KG-1～15、RAG-1～15、FIN-1～15、SYS-1～11）逐一去重后无重复。

---

## 一、图谱增强 RAG 家族（RAG-16 ～ RAG-18）

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

---

## 二、中文综述与 2025–2026 最新进展（RAG-19 ～ RAG-22）

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

---

## 三、忠实度、引文与检索评测（RAG-23 ～ RAG-25）

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

---

## 四、幻觉与金融长文档证据检索（RAG-26 ～ RAG-27）

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

---

## 五、汇总表

| 编号 | 年份 | 出处 | 全文是否已下载 | PDF 文件（`文献调研/文献PDF/`） | 与本课题哪一部分对应 |
|------|------|------|----------------|------------------------------|----------------------|
| RAG-16 | 2024 | arXiv:2410.05779（LightRAG） | 已下载并校验通过（1123301 字节） | RAG-16_Guo2024_LightRAG.pdf | 相关工作（图谱增强 RAG 家族对比，说明本课题差异） |
| RAG-17 | 2024（ICLR 2025 Poster） | ICLR 2025；arXiv:2407.10805（Think-on-Graph 2.0） | 已下载并校验通过（2301111 字节） | RAG-17_Ma2024_ToG2.pdf | 相关工作（图遍历 + 原文证据绑定路线对照） |
| RAG-18 | 2024 | arXiv:2408.08921（Graph RAG 综述） | 已下载并校验通过（1725790 字节） | RAG-18_Peng2024_GraphRAG_Survey.pdf | 相关工作（图谱增强 RAG 技术谱系与分类框架） |
| RAG-19 | 2025 | 人工智能与机器人研究, 2025, 14(2): 402-413 | 已下载并校验通过（3104466 字节） | RAG-19_Zhou2025_GraphRAG_Survey.pdf | 相关工作（中文 GraphRAG 综述） |
| RAG-20 | 2025 | 微电子学与计算机, 2025, 42(10): 48-65 | 已下载并校验通过（777718 字节） | RAG-20_Li2025_Knowledge_Intensive_RAG.pdf | 相关工作（RAG 组件化拆解，支撑混合检索模块叙述） |
| RAG-21 | 2025 | 自动化学报, 2025, 51(6): 1145-1169 | 已下载并校验通过（2699006 字节） | RAG-21_Tian2025_RAG_to_SAGE.pdf | 相关工作（RAG→SAGE 工程化趋势，服务层与缓存设计） |
| RAG-22 | 2025 | 计算机工程与应用, 2025, 61(13): 1-25 | 未获取全文（官网 PDF 接口 403 禁止访问） | —（未生成文件） | 相关工作 + 评价指标（中文综述，含基准与指标梳理） |
| RAG-23 | 2023 | EMNLP 2023, pp. 6465-6488（ALCE） | 已下载并校验通过（481920 字节） | RAG-23_Gao2023_ALCE.pdf | 评价指标（引文精确率/召回率，与 12.7 节 Faithfulness 交叉验证） |
| RAG-24 | 2023 | EMNLP 2023, pp. 12076-12100（FActScore） | 已下载并校验通过（2409424 字节） | RAG-24_Min2023_FActScore.pdf | 评价指标（细粒度事实精度，与 12.7 节人工 0/1/2 评分交叉验证） |
| RAG-25 | 2024 | NeurIPS 2024 Datasets and Benchmarks Track（CRAG） | 已下载并校验通过（884186 字节） | RAG-25_Yang2024_CRAG.pdf | 评价指标 + RQ2/RQ3（按时效动态性分层的检索与生成联合评测） |
| RAG-26 | 2026 | 人工智能与机器人研究, 2026, 15(1): 156-167 | 已下载并校验通过（701917 字节） | RAG-26_He2026_Hallucination_Survey.pdf | 相关工作（幻觉成因与缓解，支撑 Faithfulness 评测必要性） |
| RAG-27 | 2026 | arXiv:2608.12335（HC-RAG） | 已下载并校验通过（1230566 字节） | RAG-27_Chen2026_HC-RAG.pdf | RQ2/RQ3（金融长文档证据检索与证据定位评测的直接对标） |

---

## 核验失败条目

无。本次 12 条线索（RAG-16 ～ RAG-27）全部检索到真实文献，并通过至少 2 个相互独立来源完成题名、作者、出处、年份的交叉核验，无核验失败条目、无占位编号。其中 1 条（RAG-22）因期刊官网 PDF 下载接口返回 403 禁止访问而未能取得全文，但题录信息已由期刊官网文章页、官网卷期目录与中国知网文献页三源确认，不属于核验失败。
