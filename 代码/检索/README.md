# 代码\检索\ —— 第 7 阶段（RAG 检索系统）的检索组件

> **一句话**：把"问题 → 两路候选（向量检索 ＋ 图谱查询层）→ 时间过滤（按组）→ 合并去重
> → 裁剪到 Context Token Budget → 保留 K 个 → 分组排序 → 四项指标"做成一条**确定性**的
> 检索管线；关掉图谱即可作为 Baseline 2／A 组运行，打开图谱即可作为 B～E 组运行。
>
> 依据：`阶段06-事件抽取与知识图谱\18-第7阶段任务书（RAG检索系统）.md`（第八节 28 行验收、
> 第九节 T1～T12、第五节 22 条硬约束）；可执行规格为《10-系统总体设计（第四阶段）》第4.6节。

## 一、目录与文件

| 文件 | 环节 | 对应子任务 | 状态 |
| --- | --- | --- | --- |
| `config.py` | 唯一参数来源（路径、Embedding 口径、K／N／预算／g、三个开关的合法域；含镜像重跑期的「拒绝网络／凭据路径」硬守卫 `STAGE7_FORBID_MODEL_CALLS`） | — | 已产出 |
| `check_inputs.py` | 输入校验与**输入指纹清单**（T1） | T1 | 已产出 |
| `vector_search.py` | 向量检索：问题编码、索引检索、N 个候选与**原始排名** | T2 | 已产出 |
| `graph_query.py` | 图谱查询层：七个接口 ＋ 与 Cypher 一一对应 | T3 | 已产出 |
| `pipeline.py` | Top-K 五步契约的端到端（合并去重／时间过滤／裁剪／保留 K／分组排序）；同时是**端到端入口**：`--group A|B|C|D|E --out …` 串起向量检索 → 图谱查询 → 五步契约并落逐题 trace | T4～T7 | 已产出 |
| `metrics.py` | 四项检索指标（chunk 级：Recall@K／Precision@K／MRR／Complete Evidence Recall@K） | T10 | 已产出 |
| `pre_experiment.py` | 预实验 9 格网格与 K／N／预算定值（含 g 曲线与预算敏感性） | T8 | 已产出 |
| `build_questions.py` | 预实验问题集的确定性构建（candidates／freeze／verify） | T9 | 已产出 |
| `third_party_review.py` | 第三方模型盲标复核（**链外工具**，唯一会调用外部接口的脚本；不属检索链路，产物与定性见《19》的「已知限制与证据不足清单」第 9 条） | T9 收口 | 已产出 |
| `run_query.py` | 《18》第4.2节 的独立入口：`--question`／`--group A..E`（默认 C）／`--k/--n/--budget`／`--out` 串起 `vector_search → graph_query → pipeline → metrics` 的单题完整运行（运行记录默认落 `_工作底稿\`，不写 `检索产出\`）；`--selftest` 跑通 A 与 C 两组各一题；`--run-manifest` 一键复跑生成 `检索产出\run_manifest.json` | T12 收口 | 已产出 |

产出物落点：`阶段07-RAG检索系统\检索产出\`（结构化 JSONL／CSV）与
`阶段07-RAG检索系统\预实验问题集\`（题集四件）；中间产物写 `阶段07-RAG检索系统\_工作底稿\`。

## 二、约定（与 `代码\数据准备\`、`代码\抽取与图谱\` 同一套做法）

1. **参数一律取 `config.py`**：脚本内不得写死模型名、路径、阈值、K／N／预算、日期。
   `K`／`N`／`context_token_budget` 在 T8 之前是 `None`（TBD）——读到 `None` 必须**报错退出**，
   不得用默认值兜底（否则预实验的"饱和"会漂移）。
2. **命令行**沿用 `--profile` 形式；每个脚本**可单独执行**。
3. **结构化产出一行一条**（JSONL／CSV，UTF-8，不带 BOM）；参与逐字节比对的文件按
   **固定键序与固定排序**写，**不得写入运行时间戳或耗时**（时间戳与耗时只打印到 stdout）。
4. **索引读写走字节流封装**：用 `config.read_faiss_index()`（＝
   `np.frombuffer(bytearray(raw), dtype=np.uint8)` ＋ `faiss.deserialize_index`）。
   **不得**对含中文的路径调用 `faiss.read_index`／`write_index`——它们走 C++ 的 `fopen`，
   会因 ANSI 代码页失败。封装来源：`代码\数据准备\embed.py` 第 127～155 行。
5. **对输入只读**：`阶段05-数据准备\数据集\v2.1\` 与
   `阶段06-事件抽取与知识图谱\图谱导出\v2.1_v1_2\` 一个字节都不写（T1 记指纹、T11 比对）。
6. **零大语言模型调用**：第 7 阶段的链路里没有答案生成模型，也不需要密钥——
   `config.py` **刻意不提供** `api_key()` 一类读取方式。问题侧向量化是**本地 Embedding 前向**，
   与索引同模型同 revision、不联网；按《18》第2.5节 的口径不计入"模型调用"，
   但文档里必须写明这一区分，不得写成"全程未跑模型"。
7. **术语**：凡指代处一律写「向量索引」或「向量检索组件」；被禁用的四字连写术语出现 0 次。

## 三、图谱侧的消费口径（**最小但最关键的几条**）

1. **图谱侧候选的唯一入池依据是关系上的 `source_chunk_id`**——不是 `event_id`、不是 `doc_id`。
2. `EVIDENCED_BY`（1111 条）指向 Document、**不带** `source_chunk_id`，只用于展示来源文档，
   **不产生文本块级候选**。
3. 公司标识支持 `node_id`／`stock_code`／名称（含 `short_name` 与 `aliases`）三种匹配；
   **不得假设每家公司都有 `stock_code`**——人工确认写入的 12 个 `HCONF-` 节点只有名称。
4. `event_time` 为空的候选在 D／E 组**一并剔除**；空值策略是**显式配置项**
   （`config.RETRIEVAL["time_filter_null_policy"]`），不得写成隐式跳过。
5. 实现形态是「**图谱查询层**」＋内存图，接口与 Cypher 一一对应、`replay.cypher` 作为
   可物化脚本保留。**不得**声称已部署 Neo4j 服务，**不得**写任何连接串或服务地址。

## 四、五步契约（实现成一条不可重排的调用链）

```
① 两路取候选（D／E 组先做时间过滤，剔除 event_time 为空者）
② 按 chunk_id 合并去重（集合并集，不重复计数、不加分）
③ 裁剪到 Context Token Budget（先裁与问题实体无关的远端图谱路径，再按分层保留顺序从尾部往前裁）
④ 保留 K 个文本块（**先于**分组排序）
⑤ 该集合同时喂四项指标与 Prompt（第 8 阶段消费）
```

第③步与第④步共用同一条**「分层保留顺序」**（2026-09-27 甲案裁定；《02》第12.4节 与 第12.7节
第三／第四步；《10》第4.6.4节～第4.6.6节；《18》第2.3节 与 硬约束 10），三层定义如下：

1. **第一层**：向量侧候选按**向量检索的原始排名升序**取前 **(K−g)** 个；
2. **第二层**：**图谱侧新增块**（没有向量排名的那些）按**对问题的向量相似度降序**
   （**并列按 `chunk_id` 升序**，否则相似度打平时顺序不确定、做不到逐字节可复现）
   **至多取 g 个**；
3. **第三层**：前两层不足 K 个（或预算未用尽）时，按向量原始排名升序用**向量侧剩余候选**回填；
   尾部＝未被第二层取到的图谱侧新增块（按原路径出现顺序）。

裁剪从该顺序的**尾部往前**裁，截取取**前 K 个**，D 组的呈现顺序也是它。**g 的定位与定值**：
`g` 是**全局固化量**（A～E 五组同值、不进任何开关、不随组变化；取值来源＝
`config.RETRIEVAL["graph_retention_share"]`，现行 **g = 2**，选择规则含下限 **g ≥ 1**——
下限 1 保证图谱侧证据在每道题上至少有一个名额、维持 H1／H2 的可检验性）；`g = 0` 退化为原字面
口径（向量侧在前、图谱侧新增块追加在后），只用于对照与回归。定值过程、`g` 曲线与预算余量敏感性
见 `阶段07-RAG检索系统\检索产出\k_selection.json` 与《19》第3.3节。

只有第④步之后的**分组排序**（E 组单变量）允许改变顺序；因此 **D 与 E 的最终证据集合必然相同**。
四条可执行断言的判据见《18》表 18-E，实现在 `pipeline.py` 里，不成立即整体失败退出。

## 五、常用命令

```bat
python 代码\检索\check_inputs.py                     :: T1 输入校验 ＋ 写输入指纹清单
python 代码\检索\vector_search.py --selftest          :: T2 自证（Embedding 口径复现等）
python 代码\检索\graph_query.py --selftest            :: T3 自证（七接口与三条断言）
python 代码\检索\pipeline.py --selftest               :: T4～T7 自证（四条断言）
python 代码\检索\pre_experiment.py                    :: T8 预实验（9 格 ＋ 第二轮，落盘两个产出）
python 代码\检索\metrics.py                           :: T10 四项指标（落盘 metrics_pre.jsonl）
python 代码\检索\pipeline.py --group C --out 阶段07-RAG检索系统\检索产出\per_question_trace.jsonl
                                                      :: T7 端到端入口（30 题逐题 trace）
python 代码\检索\run_query.py --question "……" --group C
                                                      :: 《18》第4.2节 单题完整运行（默认落 _工作底稿\run_query_C_<题号>.json）
python 代码\检索\run_query.py --selftest            :: A 与 C 两组各一题的自证（含同题两次运行比对）
python 代码\检索\run_query.py --run-manifest        :: 一键复跑：11 条输入指纹 ＋ 四个产物两次运行 SHA-256 → 检索产出\run_manifest.json
```

门禁：每次产出一律先跑 `python 工具\跨文档核验.py`；阶段收口以
`python 工具\跨文档核验.py --strict-citations` 与 `python 工具\验收第7阶段.py` 的退出码为准
（两者都为 0 才算通过）。
