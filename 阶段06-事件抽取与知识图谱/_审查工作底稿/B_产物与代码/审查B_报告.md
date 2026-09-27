# 审查 B：数据与产物真实性 ＋ 代码与可复现性（只读审查报告）

审查对象：第 5 阶段数据集 `阶段05-数据准备\数据集\v2.1\`（709 篇／5018 块）与评测集
`抽取评测集\v2.1\`；第 6 阶段产物 `代码\抽取与图谱\_全量\v2.1_v1_2\`、
`阶段05-数据准备\数据集\_抽取缓存\v2.1_v1_2\`、`阶段06-事件抽取与知识图谱\图谱导出\v2.1_v1_2\`
与归档版 `v2.1` 三处；代码 `代码\数据准备\*.py`、`代码\抽取与图谱\*.py`、`工具\*.py`；
断言文档《13》第 5／6.7／6.8 节、《16》第 3／6／7／8 节、
`_全量\v2.1_v1_2\对照报告.md`、`_默认口径切换\` 两份报告。

审查方式：**全部数值从产物重算**，不照抄文档；所有门禁脚本真跑并留原始输出；
三条关键守卫做**故意破坏试验**（一律在系统临时目录，工作区一个字节未改）。
除本产物目录外，未写工作区任何文件；未 `git add`／未 `git commit`；未调用任何模型
（`STAGE6_FORBID_MODEL_CALLS` 语义的守卫在 `config.api_key()` 与 `auto_annotate*.py` 中保持有效，
验收脚本的镜像重跑自行摘掉 `LLM_API_KEY`，K1 实测 api_calls_total=0）。

环境：仓库 HEAD `d3b722fc17a2037dbd5feb2070c245a522e7c9cb`（2026-09-27 19:56:16 +0800，
“登记三个第三方模型的独立复核结论（40 条抽检样本）”）；`git status --short` 只有本审查目录未跟踪（第⑧节原文）。

---

## ① 执行摘要（最要紧的 10 条）

1. **第 5 阶段数据侧：全部可算量与《13》一致。** 文档 709、文本块 5018、类目 556／103／30／20、
   公司并集 105、行业 45、逐月 104／157／254／194、两个时间桶 275／434、
   `cutoff_minus_earliest_days = 100`、`doc_id` 四段分块与 `chunk_id = doc_id×1000 + chunk_index`
   逐条成立（mismatched 0／709 篇无缺块）、四要素 400／512／128／50 与 `config.CHUNK` 一致、
   产物侧无超 512 的块、相邻块最大重叠恰为 50、低于 128 的 7 块全部满足“整篇短于 target_chars”的豁免。
2. **索引集中度守卫仍然通过**：单篇最大 3.0092%（doc 1377，151 块）、前 5 篇合计 11.1598%、
   同名标题跨公司复用 0 组、规范化重名标题 0 组。三项阈值（25%／60%／0 组）均有大幅余量。
3. **第 6 阶段产物侧：第③节表里 40 余项声明值的重算结果全部一致**（实体 3293、事件 1114、语义关系 2506、
   证据项 6913／6913 可定位、节点 2802、边 2736、HCONF 12 节点与 29 条确认边、
   `issuer_participation_dropped = 1`、机检 18／0／2、三条可过滤性 66／49／40 等，逐条见第③节表）。
4. **唯一实质性的“登记 vs 产物”不符（I-1，中高）**：`verify.json` 的
   `reproducibility.identical_across_runs = false` 的实际含义**不是**《16》§1.3／§3.1／§8.7 登记的
   “比较首跑 680 篇与补齐轮 709 篇两条 709 篇记录”。产物里的 `runs = 2`、`documents = [3, 709]`、
   `compared_runs = [2]`（**只有一条**）、`compared_manifest_sha256` 只有 1 个值 ——
   真实情形是：写 `verify.json` 的时刻 `run_history.jsonl` 里只有“3 篇冒烟”与“首跑 709 篇”两条，
   同文档规模（709）的只有 1 条，**根本没有发生任何比较**，因此返回 false。
5. **`对照报告.md`／`对照指标.json` 是修复前的快照（I-2，中）**：两者记
   v1.2 图谱为 `edges_total = 2737`／`PARTICIPATES_IN = 1253`／机检 `passed = 17` 且
   `failed_must = ["issuer_not_also_participant"]`，`对照报告.md` §八.1 甚至写“当前 v1.2 导出物因此
   **不能直接作为交付物**”。现行交付（`图谱导出\v2.1_v1_2\`）已是 2736／1252／18／0，
   《16》v1.7 修订记录也按 2736 登记 —— 两份登记文件未随修复重生成（其 `generated_at` 为 17:38，
   修复发生在 18:56）。
6. **成本台账自洽（无发现）**：`run_history.jsonl` 三条记录（冒烟 3 篇／首跑 709 篇失败 29／
   补齐轮 709 篇失败 0）与《16》§1.6、“对照指标.json”的三组数字逐项对得上：
   直耗 6,588,261 ＝ 冒烟 26,321 ＋ 首跑 6,296,815 ＋ 补齐轮 265,125；缓存口径 6,576,654
   ＝ 补齐轮记录的 `total_tokens`（含 680 篇缓存命中用量）；v1.1 归档 5,148,432；
   第 10 阶段常引的“本轮 7.83 M”＝上一行 6,588,261 ＋ T3.5 补抽 1,237,878 ＝ 7,826,139（**推导值**，
   文档里只登记了两个加数，没有登记这个和）。
7. **B3：图谱导出两代（v2.1 六件、v2.1_v1_2 五件）与 `git show HEAD:` 逐字节一致**；
   v1.1 的另两处落点（`_全量\v2.1\`、`_抽取缓存\v2.1\`）**没有入库**，
   `git ls-files` 里 0 个文件，因此“与提交版逐字节一致”对这两处**不可验证**（只能做整树摘要留档）。
8. **B4：全套门禁真跑全绿** —— `跨文档核验`（含 `--strict-citations`）、`验收第4阶段文档`、
   `验收第5阶段数据` 99／99（`--with-idempotence` 103／103）、`验收第6阶段` 默认 v1.2 101／101 与
   `--profile v21` 101／101、四个自检（执行助手／标注助手／抽检助手／lint）与
   `sample_eval_set --verify-only` 全部退出码 0。原始输出见 `raw\gate_*.txt`。
9. **守卫不是“绿而无用”：三条故意破坏试验全部变红** ——
   ①改《13》的 `target_chars` 400→401 → J2 FAIL、退出码 1；
   ②篡改 `_抽取缓存\v2.1_v1_2\1001.json` 的 `input_sha256` → 13 项 FAIL、退出码 1、K2 显示
   cache_hits 由 709 掉到 708、K1 仍为 0 次模型调用；
   ③删掉导出物 `edges.csv` 一行 → 仅 J3 FAIL（原 5a7d4500… vs 重跑 e86f86d9…）、退出码 1。
10. **B5 代码层缺陷 6 条**（第⑥节，均给文件＋行号＋原文＋触发条件＋后果），其中两条会导致
    **静默错误**：`verify.json` 的复现性块在 `append_run_history` 之前写出（I-1 的根因），
    以及 `graph_stats.isolated_nodes.count` 实际是 **435 个 id 的列表**而非整数（I-3）。

**本报告与任务书要点的对应**：②B1／③B2／④B3／⑤B4／⑥B5 逐节；
⑦ 为不一致清单（按严重度）；**守卫有效性结论在 ⑤-B4 的 5.2**（三条破坏试验的“怎么破坏／破坏后输出／是否变红”逐条成表）；
⑧ 干净区域；⑨ 未验证；⑩ 产物清单；⑪ `git status --short` 原文。

---

## ② B1：第 5 阶段数据真实性（全部从 `documents.jsonl`／`chunks.jsonl` 重算）

原始输出：`raw\B1_重算.txt`（脚本 `recompute\recompute_B1.py`）。

| 声明项（《13》） | 声明值 | 我重算的值 | 是否一致 |
| --- | --- | --- | --- |
| 文档数 | 709 | documents.jsonl 709 行、distinct doc_id 709 | 一致 |
| 文本块数 | 5018 | chunks.jsonl 5018 行、distinct chunk_id 5018 | 一致 |
| 类目分布 | 公告 556／财经新闻 103／政策文件 30／监管公开信息 20 | 556／103／30／20 | 一致 |
| 类目的块分布 | 4042／563／284／129（《16》7.4 表 15-E） | 4042／563／284／129 | 一致 |
| 公司数 | 105（company_list 并集 = config.COMPANIES） | company_list 并集 105、subject_companies 并集 105、config.COMPANIES 105 条且代码唯一 | 一致 |
| 行业数 | 45 | 对 config.COMPANIES 的 industry 去重 = 45 | 一致 |
| 每公司文档数 | min 1／中位 7／max 22；74／105 家 ≥5 篇 | min 1／中位 7／max 22；≥5 篇 74 家 | 一致 |
| 时间覆盖 | 2026-06-17 ～ 2026-09-25，跨度 100 天，`cutoff_minus_earliest_days = 100` | 完全一致；later_than_cutoff = 0；blank publish_time = 0 | 一致 |
| `data_cutoff_time` | 2026-09-25T23:59:59+08:00 | meta 与 config 同值；最晚发布时间 2026-09-25 ＝ cutoff 日期，未越过 | 一致 |
| 两个时间桶 | recent 275／earlier 434 | 275／434，桶外 0 | 一致 |
| 逐月分布 | 2026-06 104／07 157／08 254／09 194 | 104／157／254／194，无空月 | 一致 |
| 切分四要素 | 400／512／128／50 | 与 `config.CHUNK` 同值；产物侧无超 512 的块、低于 128 的 7 块全部登记豁免（整篇 122／83／110／112／125／106／110 均 < 400 且篇内仅 1 块） | 一致 |
| 重叠上限 50 | 相邻块重叠 ≤ 50 | 4309 对相邻块中 4102 对恰为 50、其余更小、最大 50，无 >50 | 一致 |
| `doc_id` 分块 1000／2000／3000／4000 | 四段 | 公告 1001-1593（556）、财经 2001-2106（103）、政策 3001-3030（30）、监管 4001-4020（20）；越界 0 | 一致 |
| `chunk_id = doc_id×1000 + chunk_index` | 逐条成立 | 5018 条全部成立（mismatched 0）；每篇 chunk_index 从 0 连续无缺（异常 0 篇）；无未知 doc_id 的块 | 一致 |
| 向量条数 | 5018（`ntotal`、映射 5018 行、域 0..5017） | `build_meta.vector_count` 5018；把 `faiss.index` 复制到 ASCII 临时路径读出 `ntotal = 5018`、`dim = 512`、`IndexFlatIP`；映射文件 5018 行；`vector_id` 域 0..5017 无缺号 | 一致 |
| 一致性检查 14／14 | 14／14 通过 | 报告 `checks_total 14／passed 14／failed 0`；门禁实跑 99／99（含 `--with-idempotence` 103／103） | 一致 |
| 三个判重键 | url／规范化标题／正文指纹各 709 distinct | url 709／blank 0；标题 709／重名 0 组；指纹 709／现场 SHA-256 前 16 位重算不一致 0 篇 | 一致 |
| `company_list` 口径 | 公告与财经新闻非空；政策与监管允许 []（30＋20 篇） | 空数组恰为政策文件 30 ＋ 监管公开信息 20；null／非列表 0；subject_companies 未越出 company_list（0 篇） | 一致 |
| 动机指标 | company_list ≥2 为 66 篇、subject_companies ≥2 为 9 篇 | 66／9 | 一致 |
| 索引集中度守卫（S 组） | 单篇 ≤25%、前 5 合计 ≤60%、同名不跨公司 | 单篇最大 3.0092%（doc 1377／151 块）、前 5 合计 11.1598%、跨公司同名 0 组 | 一致（余量很大） |
| v2.1 定向补样关键词计数（《13》6.8（3）） | 重大合同组 215／126、115／66、9／8、82／72、5／4、8／7、590／456，合并去重 903、过正则 521、命中公司 324／新增 322；产品组 210／82、307／142、121／46、227／99、34／20、56／37、77／45、1／1、42／19、1／1、18／8、280／127，合并 857、过正则 716、命中 246／新增 245、污染排除 1；两组各取 35／20 家 | 与 `代码\数据准备\勘察\event_first_probe.json` 的 `keyword_stats`／`collected_before_regex`／`matched_announcements`／`distinct_companies`／`new_candidate_companies`／`target_new_companies` **逐项相同** | 一致（与产物一致；产物本身需联网重跑巨潮检索才能复现，见第⑦节） |

**B1 补充（我对“市场级检索固定 `column = szse` 是否会丢掉沪市公告”这一风险点的独立检查）**：
`event_first_probe.json` 的 `ranking_all_new` 里，重大合同组 322 家新增候选中有 **141 家 6 开头（沪市）**、
产品组 245 家里有 **121 家**；即 `column = szse` 的返回确实包含沪市公司，
《13》6.8（3）第 1 步“实测与 `column = sse` 返回同一页”的说法在产物侧有旁证。

---

## ③ B2：第 6 阶段产物真实性（逐条“声明值 vs 重算值 vs 是否一致”）

原始输出：`raw\B2_重算.txt`、`raw\B2b_表15CDE重算.txt`、`raw\B2c_消歧与跳过重算.txt`、
`raw\B2d_零碎核对.txt`（脚本 `recompute\recompute_B2*.py`）。

### 3.1 抽取层（`_全量\v2.1_v1_2\extracted.jsonl`）

| 项（声明出处） | 声明值 | 我重算的值 | 是否一致 |
| --- | --- | --- | --- |
| 抽取记录数（§3.1） | 709 行 | 709 行、distinct doc_id 709 | 一致 |
| 实体提及（§3.1／3.2） | 3293 | 3293：Company 1825／Institution 744／Person 508／Policy 126／Industry 90 | 一致 |
| 事件（§3.1／3.3） | 1114 | 1114：股权 233／重大经营 218／业绩 169／产品 168／重大合同 145／政策 76／监管 54／投资并购 51 | 一致 |
| 语义关系 8 条之和（§3.1／3.6） | 2506 | 2506：PARTICIPATES_IN 1917／HAS_EXECUTIVE 278／ISSUED_BY 124／RELATED_TO 87／BELONGS_TO 54／SUPPLIES 29／CUSTOMER_OF 9／COMPETES_WITH 8 | 一致 |
| EVIDENCED_BY（§3.1 抽取层口径） | 1114 | `evidenced_by` 数组合计 1114（relations 数组里 0 条，程序生成） | 一致 |
| EVIDENCED_BY（§3.4／6.2 导出物口径） | 1111 | edges.csv 的 EVIDENCED_BY 1111（1089 个事件各 1 条 ＋ 11 个事件各 2 条，1089＋22＝1111） | 一致（两层口径不同，文档已分层标注） |
| 证据项合计（§3.1） | 6913 | 3293＋1114＋2506 ＝ 6913 | 一致 |
| 证据可定位（§3.1／7.4之六） | 6913／6913 可定位、坏项 0 | 我按“source_chunk_id 存在 ＋ 其 doc_id 等于 source_doc_id ＋ quote 折空白后在块内”逐条重算：checked 6913、ok 6913、bad 0 | 一致 |
| 三项证据属性（§3.1） | 2506／2506 带齐、缺失 0 | 2506 条关系全部带 source_doc_id／source_chunk_id／confidence | 一致 |
| 拒绝（§3.1／8.5） | 82，九类原因 | `counts.rejected` 求和 82；`verify.rejected.by_reason` 合计 82（domain/range 21、引文定位不到 18、事件引用 16、实体引用 8、confidence 6、ISSUED_BY 类型 5、端点类型 4、实体名非书写面 2、引文跨块 2） | 一致 |
| 警告（§3.1） | 456 | `warnings` 逐条计数 456 | 一致 |
| role 分布（§3.5，抽取层 1917） | 主体 1107／涉及方 574／合作方 228／受影响方 7／监管方 1 | 完全相同 | 一致 |
| BELONGS_TO 有效期（§3.6／8.3） | 抽取 54 条、带有效期 0 条 | 54 条、带 valid_from／valid_to 的 0 条（字段存在但全为 null） | 一致 |
| 无参与主体的事件（§3.6） | 254（`merge_summary.counts.events_without_participants`） | `events_merged.jsonl` 里 participants 为空的事件 = 254 | 一致（**口径提示**：这是“无**已消歧**参与方”的读数；仅看抽取层“完全没有 PARTICIPATES_IN 关系”的是 41 条，两个数不是同一口径） |
| 无 PARTICIPATES_IN 的事件（对照报告§一／§三(c)） | 41（v1.2）、裸事件 8 | 无 PARTICIPATES_IN 的 41 条；其中既无 PARTICIPATES_IN 又无 ISSUED_BY 的 8 条 | 一致 |
| event_time 三分（§1.6 抽取层表） | stated 507／year_from_publish 63／null 544，非空 570 | `event_time_backfill.json` 的 `counts.events_by_basis_after` 与 `时间覆盖_度量.json` 的 `extraction_layer_after_backfill` 同值；**注意**：`extracted.jsonl` 本身仍是 T3 原值（空 717／非空 397），三分只能由覆盖层重算 | 一致（产物可重算，但必须带覆盖层） |
| 补抽（§1.7） | 范围 717、接受 173（stated 110＋year 63）、复核后仍空 544（494／48／2） | `event_time_backfill_report.json` 的 `counts` 完全一致；`event_time_backfill.json` 无时间戳字段 | 一致 |

### 3.2 图谱导出层（`图谱导出\v2.1_v1_2\`）

| 项（声明出处） | 声明值 | 我重算的值 | 是否一致 |
| --- | --- | --- | --- |
| 节点（§6.1） | 2802：Company 116／Event 1100／Document 692／Person 403／Institution 316／Policy 102／Industry 73 | nodes.csv 2802 行、33 列、node_id 唯一；按 label 计数完全相同；Company 116 里含 12 个 `HCONF-####`（全部无 stock_code） | 一致 |
| Document 节点（§6.1） | 692 ＝ 709 − 17 篇无事件文档 | 无事件文档重算恰为声明的 17 个 doc_id；EVIDENCED_BY 终点全部是 Document 节点 | 一致 |
| 边（§6.2） | 2736：EVIDENCED_BY 1111／PARTICIPATES_IN 1252／ISSUED_BY 124／HAS_EXECUTIVE 143／RELATED_TO 87／BELONGS_TO 14／CUSTOMER_OF 4／SUPPLIES 0／COMPETES_WITH 1 | edges.csv 2736 行、9 列；按关系计数完全相同 | 一致 |
| 语义边（8 条） | 1625，证据属性缺失 0 | 1625 条、缺失 0 | 一致 |
| role（导出层，§3.5） | 主体 752／涉及方 431／合作方 62／监管方 1／受影响方 6 | 完全相同 | 一致 |
| BELONGS_TO 有效期（§8.3） | 14／14 为空 | 14 条、带有效期 0 条 | 一致 |
| ISSUED_BY 只出现在政策／监管事件（§6.2 机检） | 124 条、违规 0 | 124 条；按 Event 节点的 event_type 复核，非政策／监管的 0 条 | 一致 |
| 发布方不同时又是参与方（§6.2） | 写出的边上 0 例外 | 以（事件，机构）为对做交集：0 | 一致 |
| `issuer_participation_dropped`（§6.2） | count 1：EVT-1036／INST-0126／doc 3007／chunk 3007000／role 主体 | graph_stats 同值；导出边里确无 `INST-0126 → PARTICIPATES_IN → EVT-1036`，但保留 `EVT-1036 → ISSUED_BY → INST-0126` | 一致 |
| 重复边（§6.2） | 去掉 2 条 | `edge_dedup.duplicate_rows_removed = 2` | 一致 |
| 跳过边（§6.2／8.4） | 878：PARTICIPATES_IN 662／HAS_EXECUTIVE 135／BELONGS_TO 40／SUPPLIES 29／COMPETES_WITH 7／CUSTOMER_OF 5 | 我从 extracted.jsonl ＋ `entity_map` 重算“端点未消歧”→ **907**；再减去人工确认恢复的 29 条（PARTICIPATES_IN 18／HAS_EXECUTIVE 7／CUSTOMER_OF 4）→ 662／135／40／29／7／5，合计 878 | 一致（907→878 的差额被 29 条确认边完全解释） |
| 合并（§3.7／6.2） | 1114 − 14 ＝ 1100；单例 1086 | graph_stats 的 merged_events 14／singleton_events 1086；Event 节点 1100 | 一致 |
| 孤立节点（§6.2） | 435：Person 209／Institution 125／Industry 63／Policy 34／Company 2（002090、300351）／HCONF 2（0010、0011） | 用 nodes×edges 重算 435，按 label 分解完全相同 | 一致 |
| 消歧（§8.4） | 公司提及 755／1825 消歧（41.4%） | 重算 755／1825 ＝ 41.37%；Institution／Person／Policy／Industry 全部 resolved | 一致 |
| 待消歧构成（§4.4） | 1070 ＝ no_alias_match 1063 ＋ distinct_entity_marker 7 | unresolved.jsonl 1070 条，reason 分布完全相同 | 一致 |
| 公司身份数（§4.3） | 104 | entity_map 里 Company 的数字代码身份 104 | 一致 |
| 人工确认（§6.6） | 候选 13／确认 12／保持未确认 1（豪威集成电路（集团）股份有限公司）；新增 12 节点、29 条边（PARTICIPATES_IN 18／HAS_EXECUTIVE 7／CUSTOMER_OF 4）；命中配置公司被拒 0 | 确认文件 13 条、confirmed 12；nodes.csv 里 HCONF-0001..0012 共 12 个；以 HCONF 为端点的导出边 29 条，按关系 18／7／4 | 一致 |
| 机检（§6.2） | 20 项：通过 18、硬约束不通过 0、已知缺口 2（`event_time_nonempty`、`belongs_to_carries_validity_columns`） | `graph_check.json` 与 `graph_stats.graph_check` 同值：checks 20／passed 18／failed_must []／known_gaps 2 | 一致 |
| 导出物文件级（§6.3） | nodes.csv 2802 行／33 列／708043 B／sha256 04f2ac22…；edges.csv 2736 行／9 列／131275 B／e86f86d9…；replay.cypher 727503 B／8cdb68d0…；人工确认清单.json 6428 B／a17268f8… | 我重算的字节数与 sha256 完全相同（并另行确认两代目录与 HEAD 逐字节一致，见第④节） | 一致 |
| 事件时间依据（§3.6／8.1 图谱层） | stated 494／year_from_publish 62／null 544（1100） | graph_stats 同值；Event 节点 event_time 为空的 544 条 | 一致 |
| 三条可过滤性读数（§1.7／9.4） | 66／49／40 篇 | 从 nodes.csv＋edges.csv 重算：含 ≥2 个不同 event_time 日期的文档 66、跨 ≥2 自然月 49、同文档日期跨度 ≥31 天 40（与 1100 节点／544 空值口径自洽） | 一致 |
| 评测集（§7.1–7.4） | 260 ＝ Dev 60 ＋ Test 200；chunk 交集 0、文档交集 0；类目 209／29／15／7；容差 3.0 pp；最大偏差 0.1654／0.7931／1.2963 pp；公司维度最差 5 家 −1.2963／−0.9421／−0.8119／＋0.8047／−0.7798；表 15-C 66／9；表 15-D 21／1／46／1／100／102／45／60 与 32／88／9；表 15-E 4042／563／284／129 与逐月 1226／937／1620／1235 | 逐项重算一致（含从 `achieved_vs_target` 的逐键 `delta_pp` 自己取最大值：类目 0.1654／月份 0.7931／公司 1.2963，最差 5 家与 §7.4 末条完全相同）；`sampler.tolerance` 三个维度均 3.0；题量与 Dev／Test 类目分布由 `dev.jsonl`／`test.jsonl` 现场计数复核 | 一致 |
| 三组对账恒等式（§3.7） | 实体侧 3293−1070 → 998＋12＋692＋1100 ＝ 2802；事件侧 1114−14 ＝ 1100；关系侧 2506−878−1−2 ＝ 1625，＋1111 ＝ 2736 | 三条恒等式的每一项都能从产物重算并相等 | 一致 |

### 3.3 成本台账（`run_history.jsonl` vs《16》§1.6 与对照报告§七）

| 项 | 文档声明 | 我重算 | 是否一致 |
| --- | --- | --- | --- |
| 记录条数 | “留有三条记录（3 篇冒烟／680 篇首跑／709 篇补齐轮）” | run_history.jsonl 3 条：run_index 1（3 篇、api 3、失败 0）／2（709 篇、api 749、失败 29、缓存命中 3、新取 679）／3（709 篇、api 31、失败 0、缓存命中 680、新取 29） | 一致（“680”是首跑**成功**篇数，记录里的 documents 字段是 709） |
| 直耗合计 6,588,261 | 冒烟 26,321 ＋ 首跑 6,296,815 ＋ 补齐轮 265,125 | 三条记录的 `total_tokens` 是 26,321／6,323,136／6,576,654；其中后两条的“实际花费”（`from_cache=false` 的逐篇 usage 之和）＝ 6,296,815／265,125（差值恰为各自缓存命中的用量：26,321／6,311,529） | 一致 |
| 缓存口径合计 6,576,654 | prompt 3,415,225 ＋ completion 3,161,429，其中推理 2,720,877 | 等于补齐轮记录的 `prompt_tokens`／`completion_tokens`／`total_tokens`（该轮覆盖全部 709 篇、680 篇走缓存）；`对照指标.json.cost_cache` 同值，另有 api_calls 781 ＝ 749＋31＋1（含冒烟） | 一致 |
| v1.1 归档 5,148,432 | `对照指标.json.v1_1.cost_cache.total_tokens` | 同值（prompt 2,091,704 ＋ completion 3,056,728） | 一致 |
| “本轮 7.83 M” | 用户任务书里的口径；文档中没有这个和 | 6,588,261 ＋ 1,237,878（T3.5 补抽）= 7,826,139 | 推导值，与两个加数一致（**不是**文档的登记值） |
| 墙钟 | 冒烟 52.78＋首跑 12,294.21＋补齐轮 536.31 ＝ 12,883.30 秒 | run_history 三条 `wall_clock_seconds` 完全相同 | 一致 |

### 3.4 `verify.json.reproducibility` 的真实含义（B2 里唯一实质性不符）

产物原文（`_全量\v2.1_v1_2\verify.json`，`reproducibility`）：
`runs = 2`、`documents = [3, 709]`、`api_calls = [3, 749]`、`cache_hits = [0, 3]`、
`fetched = [3, 679]`、`manifest_sha256 = [0bd5de5e…, e2d8efc6…]`、
`compared_runs = [2]`、`compared_manifest_sha256 = [e2d8efc6…]`、`identical_across_runs = false`。

代码逻辑（`代码\抽取与图谱\extract.py` L1514–1535）：先按 `documents == runs[-1].documents`（＝709）
过滤出 `same_scope`，再取末两条 `tail`，`identical_across_runs` 要求 `len(tail) >= 2` 且清单哈希相同。
产物里 `compared_runs` 只有 `[2]`，说明**过滤后只剩一条 709 篇记录**，`len(tail) < 2` 直接判 false。
这与 `runs = 2`、`documents = [3, 709]` 完全吻合：写出该 `verify.json` 的时刻，
`run_history.jsonl` 里只有“3 篇冒烟”和“首跑 709 篇”两条，补齐轮的记录还没落盘。
根因见第⑥节缺陷 1（`dump_json(verify)` 在 `append_run_history(stats)` 之前）。

我对现有三条记录**在内存里复算**了同一函数：现在会得到 `compared_runs = [2, 3]`、
两条清单哈希 `e2d8efc6…` 与 `ed5b048b…` 不等 → 仍然 false。

结论：《16》§1.3／§3.1／§8.7 三处登记的“比较的是首跑与补齐轮两条 709 篇记录的清单哈希，
产物不完整所致”**与随产物交付的 `verify.json` 不符**：交付件里那两条记录是
“3 篇冒烟”与“首跑 709 篇”，且**实际参与比较的只有 1 条**（等于没有比较）。
“false”这个值本身没错，“原因登记”错了。

---

## ④ B3：归档 v1.1 的完整性

原始输出：`raw\B3_git比对.txt`、`raw\B3_git比对_收工复跑.txt`（脚本 `recompute\check_B3_git.py`，
所有 git 调用带 `-c core.quotepath=false`，中文路径不做存在性过滤）。

### 4.1 与提交版逐字节比对（`git show HEAD:<path>`）

| 落点 | 入库文件数 | 比对结果 |
| --- | --- | --- |
| `阶段06-事件抽取与知识图谱\图谱导出\v2.1\` | 6（nodes.csv／edges.csv／graph_stats.json／replay.cypher／人工确认清单.json／待人工确认清单.md） | **6／6 与 HEAD 逐字节一致**（71da0bb3…／590ba206…／9e87886e…／7bd0fd9a…／a17268f8…／94deb449…） |
| `代码\抽取与图谱\_全量\v2.1\` | **0** | 未入库（`.gitignore:32 代码/抽取与图谱/_全量/`），**没有提交版可比** |
| `阶段05-数据准备\数据集\_抽取缓存\v2.1\` | **0** | 未入库（`.gitignore:19 阶段05-数据准备/数据集/`），**没有提交版可比** |
| （对照）`阶段06-事件抽取与知识图谱\图谱导出\v2.1_v1_2\` | 5 | 5／5 与 HEAD 逐字节一致（04f2ac22…／e86f86d9…／63394794…／8cdb68d0…／a17268f8…） |

结论：**“三处落点都与提交版逐字节一致”这句话只有一处可验证**。
`图谱导出\v2.1\` 可验证且通过；另两处（`_全量\v2.1\`、`_抽取缓存\v2.1\`）在现行 `.gitignore`
下根本不入仓库，只能用“整树摘要前后未变”（第二步报告 §D4：`_全量` 29→29 文件、组合摘要
`7cd9106edc851349` 未变）作为间接证据。这是**范围性限制**，不是篡改证据。
顺带留档：`_全量\v2.1\extracted.jsonl` sha256 `4cd9bcce…`、`verify.json` `933a293b…`、
`run_history.jsonl` `62295e71…`、`event_time_backfill.json` `52c308a0…`；
`_全量\v2.1\` 里**没有** `对照报告.md`／`对照指标.json`（这两件只存在于 v1.2 目录）。

### 4.2 v1.1 是否仍可 `--profile v21` 复现

`python 工具\验收第6阶段.py --profile v21` **真跑通过：101／101、失败 0、SKIP 0、退出码 0**
（原始输出 `raw\gate_验收第6阶段_v21.txt`）。该 profile 的 H／I／J／K／S 组会在临时目录
镜像重跑并逐字节比对导出物，因此“可复现”有机械证据，不只是文件还在。
默认 profile（v1.2）同样 101／101（`raw\gate_验收第6阶段_默认v1_2.txt`）。

---

## ⑤ B4：代码与可复现性（门禁、守卫有效性、缓存纪律、密钥与忽略）

### 5.1 全套门禁与自检（逐条真跑，原始输出与退出码）

| 命令 | 退出码 | 结论行（原文摘录） | 原始输出 |
| --- | --- | --- | --- |
| `python 工具\跨文档核验.py` | 0 | 结论：全部通过（N1 三处版本号均为 v2.8；N2 依据声明 21 处、过期 0 处） | `raw\gate_跨文档核验.txt` |
| `python 工具\跨文档核验.py --strict-citations` | 0 | 结论：全部通过（--strict-citations 计入门禁） | `raw\gate_跨文档核验_strict.txt` |
| `python 工具\验收第4阶段文档.py` | 0 | 结论：全部通过 | `raw\gate_验收第4阶段文档.txt` |
| `python 工具\验收第5阶段数据.py` | 0 | 最终：检查项 99 项，通过 99，失败 0 | `raw\gate_验收第5阶段数据.txt` |
| `python 工具\验收第5阶段数据.py --with-idempotence` | 0 | 最终：检查项 103 项，通过 103，失败 0 | `raw\gate_验收第5阶段数据_with_idempotence.txt` |
| `python 工具\验收第6阶段.py`（默认 v21_v1_2） | 0 | 最终：检查项 101 项，通过 101，失败 0；SKIP 0（X3：镜像 1548 个文件、未写工作区、摘掉密钥、零模型调用） | `raw\gate_验收第6阶段_默认v1_2.txt` |
| `python 工具\验收第6阶段.py --profile v21` | 0 | 最终：检查项 101 项，通过 101，失败 0；SKIP 0（镜像 1757 个文件） | `raw\gate_验收第6阶段_v21.txt` |
| `python 工具\执行助手.py selftest` | 0 | 结论：全部通过（8 项） | `raw\gate_执行助手_selftest.txt` |
| `python 工具\标注助手.py selftest` | 0 | 自检**全部通过**（含 `merge_refuses_auto` 硬守卫、真实 dev／test 未被触碰） | `raw\gate_标注助手_selftest.txt` |
| `python 工具\抽检助手.py selftest` | 0 | selftest 通过（含“抽样不读 `_全量`／`图谱导出`”的 846 次文件访问审计） | `raw\gate_抽检助手_selftest.txt` |
| `python 代码\抽取与图谱\auto_annotate_lint.py selftest` | 0 | lint 自测：全部通过 | `raw\gate_auto_annotate_lint_selftest.txt` |
| `python 代码\抽取与图谱\sample_eval_set.py --verify-only` | 0 | `ok: true`（dev 60／test 200、类目与分层统计一致、chunk→doc 链接 0 违规） | `raw\gate_sample_eval_set_verify_only.txt` |

补充：验收第 6 阶段与第 5 阶段的输出里没有任何 `[FAIL]`；第 6 阶段的 SKIP 为 0（默认与归档两个 profile）。
退出码逐条汇总另见 `raw\gate_退出码汇总.txt`（12 条门禁／自检全部 0；3 条故意破坏试验全部 1）。

### 5.2 守卫有效性抽查（3 条故意破坏试验，全在临时目录）

| 编号 | 怎么破坏 | 破坏后输出（原文摘录） | 是否变红 |
| --- | --- | --- | --- |
| ① | 把《13》第 3.1 节 `target_chars 400` 改成 `401`（**临时副本**），其余不动，跑 `验收第5阶段数据.py --doc <临时副本>` | `[FAIL] J2 《13》声明的切分参数 == config.CHUNK`：实测《13》{'target_chars': 401,…}；config {'target_chars': 400,…}；`最终：检查项 99 项，通过 97，失败 2` | **变红（退出码 1）** |
| ② | 把临时根里 `_抽取缓存\v2.1_v1_2\1001.json` 的 `input_sha256` 改成 64 个 0（**只在临时根的整棵副本里**），跑 `验收第6阶段.py`（默认 profile，含镜像重跑） | 13 项 FAIL：`K2 缓存命中覆盖全部文档 实测 cache_hits=708、documents=709、fetched=0`；`J1 …重跑退出码=1、整链 run_all 退出码=2`；`I1 …退出码=1：…覆盖层记的是 bae28dc7…，当前是 9f3ec443…`；`T2 extract 退出码=2`；`K1 api_calls_total=0 ≤ 上限 0` | **变红（退出码 1）**，且**没有**降级调用模型 |
| ③ | 把临时根里 `图谱导出\v2.1_v1_2\edges.csv` 删掉最后一行（`PER-0400,PARTICIPATES_IN,EVT-0098,1076,1076000,0.7,涉及方,,`），跑 `验收第6阶段.py` | 唯一失败项：`[FAIL] J3 edges.csv 逐字节一致（sha256 比对） 实测 原 5a7d4500211a2ba5 vs 重跑 e86f86d99bb1b227；字节数 131212`；J2／J4／J5 仍 OK（同一轮里 nodes.csv／replay.cypher／graph_stats 都逐字节一致） | **变红（退出码 1）**，且定位精确到被改的那个文件 |

三条试验的对照（“正对照”）与构造脚本：
`raw\破坏2_对照_临时根_修root后.txt`（干净临时根 101／101）、`raw\破坏3b_临时根删边后_验收第6阶段.txt`、
`raw\破坏1_验收第5阶段_改后.txt`、`raw\破坏2_篡改缓存指纹后_验收第6阶段.txt`、
`raw\破坏3_验收第6阶段_删边后_含重跑.txt`、`raw\破坏3_验收第6阶段_删边后.txt`，
脚本在 `破坏试验\破坏1_改冻结口径数字.py`、`破坏3_删导出边.py`。

**两条顺带得到的守卫边界（不是缺陷，但必须知道）**：

- 破坏 ③ 在 `--no-replay` 下**不会变红**（B11 只看“关系／事件类型是否有覆盖”，不看条数：
  它如实打印“关系 2735 条、PARTICIPATES_IN=1251”，仍判 OK）。删行只能由 J3 这类逐字节比对抓到，
  所以**默认（带镜像重跑）才会拦住它**，`--no-replay` 属于“静态预检”口径。
- 破坏 ② 的链条很长（extract → dedup → write_graph 连环失败），说明缓存指纹是**上游单点**，
  它一变就会把 T4／T5／T6 一起带红 —— 这正是设计意图（宁可硬失败，不静默重问模型）。

### 5.3 缓存纪律

| 检查 | 实测 |
| --- | --- |
| `_抽取缓存\v2.1_v1_2\` 文件数 | **1466**：主缓存 709 ＋ `时间补抽\` 717 ＋ `图谱管线\` 10（graph_check.json／manifest.sha256／人工确认清单.json ＋ 去重 4 ＋ 消歧 3） ＋ `_29篇_旧缓存备份_20260927\` 30 |
| `_抽取缓存\v2.1\`（v1.1 归档） | 1710（主 709 ＋ 时间补抽 989 ＋ 图谱管线 12），两代**物理隔离** |
| 指纹键是否含 Prompt 版本 | 含：`input_sha256` 的载荷里有 `prompt_version` 与 `prompt_template_sha256`（`extract.py` L549–583） |
| 指纹键是否含本体定义摘要 | **含**：v1.2 变体开启时追加 `ontology_definitions_digest`（`extract.py` L575–582），并附了“不追加就会静默复用旧缓存”的历史教训注释 |
| v1.1／v1.2 缓存是否互不污染 | 抽 200 篇同名缓存比对：`input_sha256` **相同 0 篇**；709 篇 v1.1 缓存的 `prompt_version` 全为 `stage6-extract-v1.1`、709 篇 v1.2 全为 `stage6-extract-v1.2`；两套模板 sha256 分别为 `13b4522b…`／`7db7a091…` |
| `_29篇_旧缓存备份_20260927\` 是否只是留痕 | 30 个文件＝29 个 json ＋ `_说明.txt`；全仓库 `.py`／`.md` 检索 **0 处引用**；说明文件逐条登记了 27 篇 `cache_input_mismatch` 与 2 篇 `bad_json` 及其 sha256。**是留痕，不参与任何读取链** |
| 时间补抽缓存隔离 | v1.1 `_抽取缓存\v2.1\时间补抽\` 989 个；v1.2 `_抽取缓存\v2.1_v1_2\时间补抽\` 717 个；两目录同名文件 597 个（同一事件编号出现在两代，但文件各自独立） |

### 5.4 密钥与忽略（全仓库扫描）

| 项 | 结果 |
| --- | --- |
| 扫描范围 | `git ls-files -co --exclude-standard` 的真值：**170 个文件**（113 个已跟踪 ＋ 57 个未忽略的新文件，全部落在 `_审查工作底稿\` 下；中文路径直接按 git 的输出读，不做 `os.path.exists` 预过滤） |
| 模式 `sk-` | 命中 5 处，全部可解释：**4 处在我自己的扫描脚本里**（模式字面量与命令行参数），**1 处在 `工具\验收第6阶段.py` 的正则/负对照字符串**（`KEY_RE = re.compile(r"(?:sk-[A-Za-z0-9_\-]{16,}…` 与 `KEY_RE.search("sk-" + "A" * 24)`）；**无真实密钥** |
| 模式 `bce-v3/` | 命中 4 处，全部在我的扫描脚本里；仓库文件 0 处 |
| 形如 `id.secret` 的 32＋ 位十六进制点分串（`\b[0-9a-fA-F]{32}\.[0-9a-fA-F]{32}\b`） | **0 处**（另测冒号分隔形态也 0 处） |
| 其它形态（Bearer、`api_key = "…"` 字面量） | 0 处 |
| 历史检索 | `git log --all -Ssk-` 命中 1 个提交（`a8555be`，即验收脚本自带正则与负对照，见上）；`-Sbce-v3/` 0 个；`-G` 点分十六进制 0 个；`git log --all -- .env` 与 `-- 代码/抽取与图谱/config.local.json` **均无输出**（从未入库） |
| 断言 | **仓库与历史均 0 处真实命中**（唯一需要解释的是验收脚本自身的检测模式字符串，见上） |
| `.gitignore` 覆盖（《00》第八节规则 7） | 文献 PDF（第10行）、文献译文（第11行）、数据集（第19行）、`.idea/`（第2行）、`config.local.*`（第47行）、`.env`（第44行）全部命中；上述五类路径 `git ls-files --error-unmatch` 全部返回“未入库” |
| 该忽略而没忽略？ | 对 8 个可疑落点逐一 `git check-ignore -v`：`_试跑*`／`_全量`／`_试跑`／评测集／`__pycache__` 均被覆盖；**未覆盖且未跟踪的只有 `_审查工作底稿\`（57 个文件）**，即本审查与并行审查的工作目录本身 —— 是否需要忽略属作者裁定，我没有改动 |
| `git add -f` 痕迹 | `git log --all --diff-filter=A --name-only` 的 113 条新增文件里，属《00》规则 7 应排除范围（数据集／文献PDF／译文／.idea／.env／*.local.json）的路径数 = **0** |

---

## ⑥ B5：代码层缺陷（只报实际看到的）

> 说明：以下每条都给“文件＋行号＋原文片段＋触发条件＋后果”。行号为当前工作区（HEAD 同版）行号。

**缺陷 1（中高，会导致静默错误）：`verify.json` 的复现性块在 `append_run_history` 之前写出。**
`代码\抽取与图谱\extract.py` L1285–1298：

```python
    dump_jsonl(OUT["extracted"], records)
    dump_jsonl(OUT["rejected"], rejects_all)
    dump_json(OUT["verify"],
              build_verify_payload(docs, chunks, records, rejects_all, selection))
    manifest = write_manifest(selection)
    ...
    append_run_history(stats)
```

触发条件：任何一次正常抽取（`run_extraction`）。后果：写进 `verify.json` 的
`reproducibility` 永远看不到**本次**运行记录 —— 单次运行时会得到 `runs=1`，
两次运行时第二条是**上一次**；本批的实际表现就是 `runs=2` 而 `compared_runs=[2]`（只有一条），
`identical_across_runs` 在“根本没比较”的情况下返回 false（见第③节 3.4）。
这一条直接导致《16》三处把 false 的原因登记错（I-1）。修法（本审查不实施）：
把 `append_run_history(stats)` 提到 `dump_json(OUT["verify"], …)` 之前，或在算复现性时把当前 stats 追加进列表。

**缺陷 2（中，会导致静默错误／字段类型撒谎）：`graph_stats.json` 的 `isolated_nodes.count` 是列表不是整数。**
`代码\抽取与图谱\write_graph.py` L1087–1090 与 L1165–1170：

```python
        "isolated_nodes": {
            "count": _isolated(nodes, edges),
            "note": "无边节点：实体抽到了但语料没给出关系；如实保留，不删（不是遗漏）",
        },
...
def _isolated(nodes, edges):
    touched = set()
    for edge in edges:
        touched.add(str(edge["head_id"]))
        touched.add(str(edge["tail_id"]))
    return [n["node_id"] for n in nodes if str(n["node_id"]) not in touched]
```

触发条件：任何一次导出。后果：下游若按名字取数（`graph_stats["isolated_nodes"]["count"] == 435`
或参与算术），拿到的是 **435 个 id 的列表**；L1235–1237 的控制台行还会把整张列表打进日志
（现行 `运行日志_S4_图谱导出.txt` 那一行 5412 字符）。《16》§6.2 的“孤立节点 435”是 `len()` 的读法，
文档没错、字段名错。

**缺陷 3（中，口径不一致）：同一条管线里两套时间戳时区。**
`代码\抽取与图谱\extract.py` L251–252 与 `disambiguate.py` L81–82 用机器本地时区：

```python
def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")
```

而 `run_all.py` L59–61、`write_graph.py` L92–94、`extract_event_time.py` L76–78 固定 +08:00：

```python
def now_iso() -> str:
    tz = _dt.timezone(_dt.timedelta(hours=8))
    return _dt.datetime.now(tz).isoformat(timespec="seconds")
```

触发条件：在系统时区不是 +08:00 的机器上复跑（本项目自己声明 `TIMEZONE = "+08:00"`，
第 5 阶段 `clean.py` L289 也显式带 tz）。后果：同一次运行的 `run_history.started_at`
（extract 写）与 `graph_stats.generated_at`（write_graph 写）会带**不同的 UTC 偏移**，
相差可到十几小时；审计者把两条时间戳并排读会误判“这是两次不同时间的运行”，
文档里登记的那批 +08:00 时间戳也无法在异地复现。

**缺陷 4（中，守卫开口）：`--docs` 会静默绕开 pilot 选样断言。**
`代码\抽取与图谱\extract.py` L1231–1232 与 L1683–1685（同一表达式写了两遍）：

```python
    problems = check_selection(selection) if (args.profile == "pilot"
                                              and not args.docs) else []
```

触发条件：`python 代码\抽取与图谱\extract.py --profile pilot --docs 1001`。
后果：`check_selection`（《12》要求的小规模试跑样本构成断言）被整段跳过，退出码仍是 0，
产物落在 pilot 落点。也就是说“pilot 样本合规”这个结论在带 `--docs` 的运行里**没有守卫**，
而脚本不会提示这一点；同一判断写了两处，也容易在后续改动里漂移。

**缺陷 5（低，审计样本会指向不存在的编号）：写边前丢弃样本里的 `or 0` 兜底。**
`代码\抽取与图谱\write_graph.py` L627–633：

```python
            dropped.append({
                "event": str(row["tail_id"]), "institution": str(row["head_id"]),
                "role": str(row.get("role") or ""),
                "source_doc_id": int(row.get("source_doc_id") or 0),
                "source_chunk_id": int(row.get("source_chunk_id") or 0),
                "reason": ISSUER_PARTICIPATION_RULE,
            })
```

触发条件：参与方边的 `source_doc_id`／`source_chunk_id` 缺失或为空（程序生成的边、
或上游字段缺失时）。“或 0”把缺失**静默**变成 `doc_id = 0 / chunk_id = 0`。
后果：`graph_stats.issuer_participation_dropped.sample` 里会出现一个并不存在的证据落点，
按这条样本回原文核对会“查不到”，而日志与机检都不会报错。本批该样本的取值是真实的
（3007／3007000），所以只是**潜在**缺陷。

**缺陷 6（低，同一字段两种写法）：`issuer_participation_dropped` 的读法在
`_dropped_from_stats` 里与 `graph_stats` 的写出口径不一致的风险。**
`代码\抽取与图谱\write_graph.py` L1194–1197：

```python
    except (ValueError, OSError):
        return 0
    block = (data or {}).get("issuer_participation_dropped") or {}
    return int(block.get("count") or 0)
```

触发条件：`--verify-only` 在 `graph_stats.json` 缺字段或被截断时读回 0。
后果：`--verify-only` 于是用“丢弃 0 条”的口径去核 `issuer_not_also_participant`，
而在“本应丢弃 >0 条却读不到计数”的场景下会**把失败读成通过**（本次实测 count=1，
`--verify-only` 重写 `graph_check.json` 后 sha256 不变，属正常路径）。
这一条的严重度取决于 `--verify-only` 是否被视为放行口径；作为“读不到就按 0 处理”的兜底，
它至少应当把“读不到”显式记进 detail。

**工具层（不在 `代码\` 下，但属可复现性范围，按同样格式登记）：**

**缺陷 7（中，环境依赖 → 假红）：R1 的基线只在原绝对路径下可用。**
`工具\验收第6阶段.py` L2197–2200：

```python
    root_decl = str(payload.get("root") or "").rstrip("\\/")
    if root_decl and os.path.normcase(os.path.abspath(root_decl)) != os.path.normcase(
            os.path.abspath(config.DATASET_DIR)):
        continue
```

`代码\数据准备\勘察\manifest_宽口径_最终.json` 的 `root` 记的是
`C:\Users\15129\Desktop\毕业设计\阶段05-数据准备\数据集\v2.1`（绝对路径）。
触发条件：工作区被移动／复制到别的路径，或放进 CI。
后果：我实测（干净临时根）`[FAIL] R1 v2.1 目录指纹与开工基线一致（找不到基线，无法比对）`
—— “数据集只读”这条硬门禁在异地**必然报红**，报的是“找不到基线”，不是“数据被改”，
既会产生假警报，也让该门禁在异地等于失效。

**缺陷 8（低，环境依赖 → 假红）：U1 在 git 不可用时把被忽略的本地配置判成失败。**
`工具\验收第6阶段.py` L2452–2455 与 L2491–2494：

```python
if committable_set is None:
    # 降级：git 不可用 → 沿用旧口径（目录排除启发式），并在证据行把降级说出来，不静默改行为。
    repo_targets, info_targets = list(walk_targets), []
...
    else:
        # 既不在 git 的可提交集合、又拿不到忽略规则：不放过（按失败记账）。
        hard_hits.extend(hits_here)
```

触发条件：在非 git 目录（或 git 不可用）下跑验收。后果：实测
`[FAIL] U1 …命中 2 处：代码/抽取与图谱/config.local.json 第3行、第4行` —— 这个文件
是被 `config.local.*` 正常忽略的合法本地配置。证据行已声明“git 不可用”的降级，
但判定结果仍是 FAIL，读者容易把它读成“仓库里有密钥”。

---

## ⑦ 不一致清单（按严重度）

| 级别 | 编号 | 问题 | 位置 | 证据 |
| --- | --- | --- | --- | --- |
| 中高 | I-1 | `verify.json` 的 `identical_across_runs=false` 被登记为“首跑 680 篇 vs 补齐轮 709 篇的比较”，产物实为 `runs=2`、`documents=[3,709]`、`compared_runs=[2]`（只有一个运行在比较集里，等于没比较） | 《16》§1.3／§3.1／§8.7 与 `_全量\v2.1_v1_2\verify.json`；根因见缺陷 1 | `raw\B2_重算.txt` 第 B2-14 段、第③节 3.4 的内存复算 |
| 中 | I-2 | `对照报告.md`／`对照指标.json` 仍是**修复前**快照：`edges_total 2737`／`PARTICIPATES_IN 1253`／机检 `passed 17`＋`failed_must ["issuer_not_also_participant"]`，并写“不能直接作为交付物”；现行交付是 2736／1252／18／0 | `_全量\v2.1_v1_2\对照指标.json` 的 `v1_2.graph`、`对照报告.md` §八.1／§十 | 生成时间 17:38，修复与重导出在 18:56；`raw\B2_重算.txt` B2-08／B2-10 |
| 中 | I-3 | `graph_stats.isolated_nodes.count` 是 435 个 id 的列表，字段名却是 `count`；《16》§6.2 按“435 个”叙述 | `write_graph.py` L1087、L1165；`graph_stats.json` | `raw\B2d_零碎核对.txt` 末段（类型=list、长度=435） |
| 低 | I-4 | `_默认口径切换\本任务报告.md`（第一步）说 `图谱导出\v2.1_v1_2\` 在 .gitignore 覆盖内、不入仓库；实际第二步已删除该规则并把 v1.2 导出物入库（5 个文件） | 第一步报告 §⑥ 与现 `.gitignore`／`git ls-files` | `raw\B3_git比对.txt`（v2.1_v1_2 入库 5 个） |
| 低 | I-5 | 《16》§3.6 把 254 条解释成“抽到了事件但正文没写出公司主体”，该读数的实际口径是“**没有已消歧参与方**的记录”（仅看完全没有 PARTICIPATES_IN 的是 41 条） | 《16》§3.6 与 `merge_summary.counts.events_without_participants` | `raw\B2_重算.txt` B2-05／B2-12b |
| 低 | I-6 | B4 的两条门禁在异地环境会假红（R1 靠绝对路径、U1 靠 git 可用性） | `工具\验收第6阶段.py` L2197／L2452；`manifest_宽口径_最终.json` | `raw\破坏2_对照_干净临时根_验收第6阶段.txt`（R1／U1 FAIL）与 `raw\破坏2_对照_临时根_修root后.txt`（修 root＋补 .git 后 101／101） |

**口径提示（不算不一致，但下游必须分清）**：EVIDENCED_BY 在《16》里有两个数 —— 抽取层 1114
（§3.1／§3.7）与导出物 1111（§3.4／§6.2／§6.3），两者都被文档分层标注，我重算后分别成立。

---

## ⑧ 干净区域（重算后未发现问题的部分）

1. **第 5 阶段数据集本体**：709／5018、四类目分布、105 家公司、45 个行业、逐月与两桶分布、
   四段 `doc_id`、`chunk_id` 公式、重叠上限、指纹可复算、判重键唯一、`company_list` 口径、
   14 项一致性检查、S 组集中度三条 —— 全部与《13》一致。
2. **第 6 阶段抽取层的规模与分布**：3293／1114／2506／1114／6913、8 类事件、9 条关系、
   role 两层分布、82 条拒绝的九类分布、456 条警告、BELONGS_TO 有效期 0。
3. **证据可定位**：我用自己写的“source_chunk_id 存在＋doc_id 一致＋quote 折空白后落在块内”
   逐条复核 6913 条，全部通过；负对照（同一脚本的 `negative_controls`）全部按预期拒绝。
4. **图谱导出物**：2802 节点／2736 边的各项分解、悬空边 0、孤立节点 435 的按类分解、
   写出的边上 `issuer_not_also_participant` 0 例外、`ISSUED_BY` 类型限制 0 违规、
   禁字段不在表头、正文子串 200 块×3 段×100 字符 0 命中（M2 实跑）、两代目录与 HEAD 逐字节一致。
5. **人工确认链**：确认文件 13 条／12 确认／1 未确认、12 个 HCONF 节点（无 stock_code）、
   29 条确认边（18／7／4）、跳过边由 907 降到 878 的差额被完全解释。
6. **评测集**：260 条、Dev 60／Test 200、chunk 与文档交集 0、类目分布 209／29／15／7、
   容差 3.0 pp、表 15-C／15-D／15-E 全部重算一致（含全类目命中篇 27／22／50／3／103／102／73／62）。
7. **成本与运行结构**：三条 run_history 记录、直耗／缓存口径／v1.1 归档三组 token 与墙钟全部自洽。
8. **缓存纪律**：1466／1710 个文件的物理隔离、指纹含 Prompt 版本与本体定义摘要、
   200 篇抽样零同值、29 篇旧缓存备份确为纯留痕。
9. **密钥与忽略**：可提交文件集 170 个文件、11,412,772 字节扫描，真实密钥命中 0；
   历史检索 0 真实命中；`.gitignore` 覆盖《00》规则 7 的全部五类；历史新增文件 0 条越界。
10. **门禁与守卫**：8 个脚本/自检全部退出码 0（101／101、103／103、99／99）；3 条破坏试验全部变红。

---

## ⑨ 未验证

1. **归档 v1.1 两处落点的“与提交版逐字节一致”无法验证** —— `_全量\v2.1\` 与 `_抽取缓存\v2.1\`
   没有入库（`git ls-files` 0 个文件），只能给整树摘要与关键文件 sha256 留档（见第④节）。
2. **联网复现类内容未做**：巨潮／证监会／政策库／新闻站点的**重新抓取**一律未做（会改外部状态、
   且窗口内容每日可变）。因此《13》6.8（3）的逐关键词计数只在“与勘察产物 `event_first_probe.json`
   逐项一致”这一层被验证，**没有独立重跑检索接口**。
3. **模型调用与语义质量未评估**：未调用任何模型（硬约束）；v1.2 事件的语义正确性、
   `event_time_basis` 的 stated／year_from_publish 逐条正确性、v1.1→v1.2 的 396 条漏抽候选、
   20 条拆条候选，均沿用《对照报告.md》“未验证清单”的登记，我没有复核——
   这类结论只能靠人工标注或独立模型复核。
4. **`时间覆盖_度量.json` 的“抽取层”不等于 `extracted.jsonl` 的现场读数**：
   文档里的 stated 507／63／544 必须叠加 `event_time_backfill.json` 覆盖层才能重算；
   我按覆盖层重算一致，但**没有**逐条核对补抽结果与原文日期的一致性（那需要人读 717 段引文）。
5. **`--with-idempotence` 的“真实重跑”只覆盖 T4a→T5**（dedup→clean→chunk），不含采集（T3）；
   采集侧幂等只有《13》6.8（8）声明的 752 个文件逐字节一致这一条历史留档。
6. **`_试跑_图谱管线`、`_试跑\v1_2\` 等试跑目录未逐字节复核**（本审查范围外，
   `.gitignore` 已覆盖且报告已声明“不入仓库”）。
7. **未评估 `.idea\` 与 `config.local.json` 的实际内容是否含敏感信息**：
   它们被 `.gitignore` 正常排除、且从未入库；我只核了“git 会不会提交它”的真值，没有读其内容判敏感度
   （按任务书要求，密钥扫描只覆盖可提交文件集）。

---

## ⑩ 产物清单（本审查的全部落盘文件）

目录：`阶段06-事件抽取与知识图谱\_审查工作底稿\B_产物与代码\`

| 子目录／文件 | 内容 |
| --- | --- |
| `审查B_报告.md` | 本报告 |
| `recompute\recompute_B1.py` | 第 5 阶段数据的全量重算脚本 |
| `recompute\recompute_B2.py` | 第 6 阶段抽取层＋导出层重算脚本 |
| `recompute\recompute_B2b_15CDE.py` | 表 15-C／15-D／15-E 独立重算（只读 config 正则） |
| `recompute\recompute_B2c_消歧与跳过.py` | 消歧率／待消歧构成／跳过边重算 |
| `recompute\recompute_B2d_零碎核对.py` | 豁免块、无事件文档、缓存文件数、字段类型 |
| `recompute\check_B3_git.py` | 归档 v1.1／v1.2 与 HEAD 的逐字节比对 |
| `recompute\scan_B4_secrets.py` | 可提交文件集密钥扫描＋历史检索＋.gitignore 核查 |
| `破坏试验\破坏1_改冻结口径数字.py`、`破坏试验\破坏3_删导出边.py` | 两条破坏试验的构造脚本（只在临时目录动手） |
| `raw\B1_重算.txt` | B1 原始输出 |
| `raw\B2_重算.txt` | B2 原始输出（抽取层＋导出层＋成本台账＋复现性） |
| `raw\B2b_表15CDE重算.txt` | 表 15-C／15-D／15-E 原始输出 |
| `raw\B2c_消歧与跳过重算.txt` | 消歧／跳过原始输出 |
| `raw\B2d_零碎核对.txt` | 零碎核对原始输出 |
| `raw\B3_git比对.txt`、`raw\B3_git比对_收工复跑.txt` | B3 原始输出（开工一次、收工复跑一次） |
| `raw\B4_密钥与忽略扫描.txt` | 密钥／忽略／历史扫描原始输出 |
| `raw\gate_跨文档核验.txt`、`raw\gate_跨文档核验_strict.txt` | 门禁 1、2 |
| `raw\gate_验收第4阶段文档.txt` | 门禁 3 |
| `raw\gate_验收第5阶段数据.txt`、`raw\gate_验收第5阶段数据_with_idempotence.txt` | 门禁 4、5 |
| `raw\gate_验收第6阶段_默认v1_2.txt`、`raw\gate_验收第6阶段_v21.txt` | 门禁 6、7 |
| `raw\gate_执行助手_selftest.txt`、`raw\gate_标注助手_selftest.txt`、`raw\gate_抽检助手_selftest.txt`、`raw\gate_auto_annotate_lint_selftest.txt`、`raw\gate_sample_eval_set_verify_only.txt` | 自检 8～12 |
| `raw\gate_退出码汇总.txt` | 上表 12 条命令与 3 条破坏试验的退出码一览 |
| `raw\破坏1_建副本.txt`、`raw\破坏1_验收第5阶段_改后.txt` | 破坏试验 ①（构造＋红） |
| `raw\破坏2_对照_干净临时根_验收第6阶段.txt`、`raw\破坏2_对照_临时根_修root后.txt`、`raw\破坏2_篡改缓存指纹后_验收第6阶段.txt` | 破坏试验 ②（未修前对照／正对照／红） |
| `raw\破坏3_建副本.txt`、`raw\破坏3_验收第6阶段_删边后_含重跑.txt`、`raw\破坏3_验收第6阶段_删边后.txt`、`raw\破坏3b_临时根删边后_验收第6阶段.txt` | 破坏试验 ③（含 `--no-replay` 的边界读数与隔离定位的那一轮） |

**编码说明**：所有 `raw\*.txt` 与报告正文一律 **UTF-8**。PowerShell 的 `>` 重定向默认写出 UTF-16LE，
收工后已用 python（`encoding='utf-8'`）统一转码；`B3_git比对.txt` 另用 python 直接捕获 stdout 重落一次，
以保证末行完整（29 个文件曾为 UTF-16，已全部转换；逐文件核对过末行未截断）。

临时目录（**都在系统 `%TEMP%` 下、不在工作区**）：`%TEMP%\B_fullcopy_jg98q3dy\root`（整棵工作区副本，
复制耗时 3.5 秒／7263 个文件／556.7 MB）、`%TEMP%\B_tamper13_ost8i7vd`、`%TEMP%\B_tamper_export_2o1dw95l`。
审查收工后这**三个临时目录已由我删除**（合计约 563.6 MB；`.git` 的只读对象先清属性再删），
证据保留在上面 `raw\` 的原始输出里。**工作区从未被这些试验写入**：
第⑪节的 `git status --short` 与第④节的逐字节比对（收工复跑）为证。

---

## ⑪ `git status --short` 原文（证明工作区未被改动）

```
$ git status --short
?? "阶段06-事件抽取与知识图谱/_审查工作底稿/"
```

（上面是本报告写作时刻的**原文**：只有审查工作底稿目录本身未跟踪，`??` 之外没有任何 ` M `／`A `／`D ` 行。
写作前的同一条命令输出相同；两次 `check_B3_git.py` 也都在比对后给出“图谱导出两代目录全部与 HEAD 逐字节一致”。）
