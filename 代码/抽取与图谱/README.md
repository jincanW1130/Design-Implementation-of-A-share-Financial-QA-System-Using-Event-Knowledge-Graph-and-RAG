# 代码\抽取与图谱 —— 第 6 阶段事件抽取与知识图谱

本目录是第 6 阶段（事件抽取与知识图谱）的实现工作区。**接口冻结文档**：所有模块必须按本文件
定义的输入输出与命令行契约实现，不得自行更改字段名、枚举取值、编号方案或参数来源。

参数一律来自 [config.py](config.py)，脚本内**不得写死**任何模型名、日期、路径或阈值。
密钥只写**读取方式**（`config.api_key()` 从环境变量 `LLM_API_KEY` 读），取值不入仓库、
不落盘、不进日志。

## 一、模块与职责

| 模块 | 子任务 | 输入 | 输出 |
| --- | --- | --- | --- |
| `config.py` | — | — | 全部冻结参数：模型与版本、Prompt 版本、temperature、路径、节奏与重试、本体枚举、试跑选样规则、覆盖性重算的对照值 |
| `extract.py` | T1／T3 | v2.1 的 `clean\documents.jsonl` 与 `chunks\chunks.jsonl` | `阶段05-数据准备\数据集\_抽取缓存\v2.1\{doc_id}.json`；试跑产物落 `_试跑\` |
| `extract_event_time.py` | T3.5（2026-09-26 追加） | 上述缓存（只读）＋ v2.1 的 `chunks\chunks.jsonl` | `_抽取缓存\v2.1\时间补抽\{event_id}.json`（**独立缓存**）＋ 覆盖层 `_全量\v2.1\event_time_backfill.json`／报告／度量（见第十一节） |
| `disambiguate.py` | T4（已落地） | 上述缓存 | `消歧\alias_table.json`、`消歧\disambiguation.json`、`消歧\unresolved.jsonl` |
| `dedup_events.py` | T5（已落地） | 上述缓存 ＋ T4 的消歧产物 ＋ T3.5 覆盖层（只读） | `去重\merge_log.jsonl`、`去重\events_merged.jsonl`、`去重\merge_summary.json`、`去重\dedup_self_test.json` |
| `write_graph.py` | T6（已落地） | 缓存（只读） ＋ T4／T5 产物 ＋ **人工确认文件**（只读） | 图谱导出物四件套 ＋ `graph_check.json`／`manifest.sha256` |
| `run_all.py` | T7（已落地） | — | 按 extract → disambiguate → dedup_events → write_graph 串联 |
| `build_company_aliases.py` | T4 的**离线建档工具**（不属于管线，`run_all.py` 不调用） | 第 5 阶段 `COMPANIES` ＋ 巨潮公司概况接口（`cninfo_company_intro`）／v2.1 公告标题 | `company_registered_names.py`：105 家配置公司的注册全称，逐家带来源与证据 |
| `company_registered_names.py` | T4 的**冻结别名数据**（由上一行的工具生成，不手改） | — | `REGISTERED_NAMES`：`disambiguate.py` 只读加载，把注册全称并入别名表 |

**四个脚本都已落地**（2026-09-25：`config.py` 追加第 9 节给 T4～T7 的参数，第 1～7 节的既有键
一个都没改）。接口与试跑实测见第十节。
本阶段的两个全局约束在这里重申：**六张表恒为六张**（本目录不写 DDL、不新增表）；
FAISS 一律写「向量索引」或「向量检索组件」。

## 二、命令行契约

```bat
python 代码\抽取与图谱\extract.py --select-only        :: 只算选样与覆盖性重算，不调模型
python 代码\抽取与图谱\extract.py                     :: T1：试跑 12 篇（默认 --profile pilot）
python 代码\抽取与图谱\extract.py --limit 3           :: 只跑选样结果的前 3 篇
python 代码\抽取与图谱\extract.py --docs 1026,1018    :: 只跑指定 doc_id（逗号或空格分隔）
python 代码\抽取与图谱\extract.py --force             :: 忽略已有缓存，重新调用并重写缓存
python 代码\抽取与图谱\extract.py --verify            :: 独立核对既有产物，不调模型
python 代码\抽取与图谱\extract.py --profile v21       :: 全量 709 篇（T3 的口径，T1 不执行）

python 代码\抽取与图谱\extract_event_time.py --profile v21             :: T3.5 定向时间补抽（只补 event_time 为 null 的事件）
python 代码\抽取与图谱\extract_event_time.py --profile v21 --limit 3   :: 联机自检：只跑前 3 条
python 代码\抽取与图谱\extract_event_time.py --profile v21 --verify    :: 按缓存重算复核并与覆盖层逐字节比对（零调用、零写入）
python 代码\抽取与图谱\extract_event_time.py --profile v21 --measure   :: 时间覆盖／可过滤性指标（补抽前／后，零调用）
python 代码\抽取与图谱\extract_event_time.py --profile v21 --force     :: 忽略补抽缓存重调（会花钱）
```

* `--profile pilot`（默认）：`config.PILOT` 的确定性选样，**12 篇**覆盖 8 种事件类型与 4 个类目。
* `--profile v21`：全量 709 篇，属 T3 的放量口径；T1 只跑 pilot。
  全量产物**不与试跑混放**：`--profile v21` 落 `config.FULL_OUTPUT_FILES`＝
  `代码\抽取与图谱\_全量\v2.1\`（见 3.5 节），`_试跑\` 只留 T1 的 12 篇记录。
* `--limit N` 与 `--docs <ids>` 可叠加，先按 `--docs` 取子集再截前 N 篇；`--docs` 允许指向
  选样结果之外的 doc_id（会记为「显式指定」）。
* `--force` 覆盖缓存；缓存命中时**不调用模型**，产物由缓存确定性重算。
* `--select-only` 与 `--verify` 都不调用模型，可离线执行。
* 幂等：同一输入重复运行不新增缓存文件、不产生重复记录；中断后可续跑（已命中的缓存跳过）。
* 退出码：`0` 成功；`1` 选样断言不成立；`2` 有文档失败。密钥未就位、缓存与当前输入不一致
  （且未 `--force`）一律非零退出，不静默降级（《15-第6阶段任务书》第十一节 的阻断项）。
* 全部脚本 `sys.stdout.reconfigure(encoding="utf-8")`。

## 三、数据格式（逐字冻结，下游按此消费）

### 3.1 `阶段05-数据准备\数据集\_抽取缓存\v2.1\{doc_id}.json` —— 一篇一个文件

```json
{
  "cache_schema": "stage6-extract-cache-1.0",
  "doc_id": 1018,
  "dataset_version": "v2.1",
  "model_requested": "deepseek-v4-flash",
  "model_resolved": "deepseek-flash",
  "model_pinned": "deepseek-flash",
  "model_pinning_state": "ok",
  "model_version": null,
  "prompt_version": "stage6-extract-v1.1",
  "prompt_template_sha256": "……",
  "input_sha256": "……",
  "temperature": 0,
  "max_tokens": 8192,
  "response_format": "json_object",
  "created_at": "……",
  "elapsed_ms": 22636,
  "attempts": 1,
  "attempts_detail": [{"compact": false, "max_tokens": 8192, "reasoning_effort": null,
                       "input_sha256": "……", "elapsed_ms": 22636, "transport_attempts": 1,
                       "usage": {"prompt_tokens": 2443, "completion_tokens": 6129,
                                 "completion_tokens_details": {"reasoning_tokens": 5371}},
                       "finish_reason": "stop", "model_resolved": "deepseek-flash",
                       "response_text": "……模型原始返回，逐字留档……"}],
  "usage": {"prompt_tokens": 2443, "completion_tokens": 6129},
  "usage_total": {"prompt_tokens": 2443, "completion_tokens": 6129, "total_tokens": 8572},
  "finish_reason": "stop",
  "response_text": "……最终采用的那一次原始返回……"
}
```

* `attempts_detail` 保留**每一次**调用的原始返回（正常只有 1 次；主尝试被输出上限截断时会有
  第 2 次的压缩重试）。`response_text` 是最终采用的那一次，解析只用它。
* `usage_total` 是各次尝试的合计，**成本按它计**（压缩重试的 token 不会漏记）。
* `input_sha256` 覆盖文档字段、提示词、Prompt 版本、模型与调用参数；缓存与当前输入不一致时，
  程序**拒绝复用**并要求 `--force`，不做静默覆盖。
* 缓存条目只有在 `finish_reason != "length"` 时才算稳态；被截断的条目下一次运行会自动补齐。
* 缓存与数据集版本绑定（`_抽取缓存\<dataset_version>\`），含第三方正文，**不入公开仓库**
  （已被 `.gitignore` 的 `阶段05-数据准备/数据集/` 一行整体覆盖）。

### 3.2 `_试跑\extracted.jsonl` —— 一行一篇，解析后的抽取结果

字段名与《10》第4.5节 的节点／关系一一对应，另有试跑审计字段（`*_id` 为局部编号、
`quote*` 为证据原文与命中块数）：

```json
{"record_schema": "stage6-pilot-record-1.0", "doc_id": 1018, "category": "公告",
 "title": "……", "source": "巨潮资讯网", "publish_time": "2026-09-22",
 "content_sha256_16": "……", "model_resolved": "deepseek-flash",
 "prompt_version": "stage6-extract-v1.1", "input_sha256": "……",
 "temperature": 0, "finish_reason": "stop",
 "entities": [{"entity_id": "ENT-1018-001", "name": "……", "type": "Company",
               "source_doc_id": 1018, "source_chunk_id": 1018000,
               "quote": "……", "quote_match_count": 1}],
 "events": [{"event_id": "EVT-1018-01", "event_type": "股权", "event_name": "……",
             "event_time": "2026-09-29", "description": "……", "confidence": 0.9,
             "source_doc_id": 1018, "source_chunk_id": 1018000, "quote": "……",
             "quote_match_count": 1, "local_ref": "E1"}],
 "relations": [{"relation_id": "REL-1018-001", "relation": "PARTICIPATES_IN",
                "head_id": "ENT-1018-001", "head_name": "……", "head_type": "Company",
                "tail_id": "EVT-1018-01", "tail_name": "……", "tail_type": "Event",
                "role": "主体", "source_doc_id": 1018, "source_chunk_id": 1018000,
                "confidence": 0.9, "quote": "……", "quote_match_count": 1}],
 "evidenced_by": [{"relation_id": "EVD-1018-01", "relation": "EVIDENCED_BY",
                   "head_id": "EVT-1018-01", "head_type": "Event",
                   "tail_id": "DOC-1018", "tail_type": "Document", "note": "……"}],
 "counts": {"entities": 3, "events": 4, "relations": 5, "evidenced_by": 4,
            "rejected": 0, "warnings": 0},
 "warnings": []}
```

四点口径：

* **`Event` 不要求模型在 `entities[]` 里重复输出**：事件由 `events[]` 物化为 Event 节点，
  参与主体由 `PARTICIPATES_IN`／`ISSUED_BY` 关系表达（《10》第4.5.1节：participants
  不作为事件属性存储）。因此 6 类实体的计数＝`entities[]` 的 5 类 ＋ `events[]`。
* 事件六项核心属性齐备：`event_id`、`event_type`、`event_name`、`event_time`、`description`、
  `confidence`。`event_time` 允许为 `null`（正文无法确定到日时**不猜**）。
* `relations` 里只有 8 条语义关系；`EVIDENCED_BY` 由程序按 `doc_id` 生成、放在
  `evidenced_by` 数组里，**不携带** source_doc_id／source_chunk_id／confidence。
  除 EVIDENCED_BY 外的 8 条关系一律带齐 source_doc_id、source_chunk_id、confidence 三项。
* `source_chunk_id` 落在 Event 上也只作**试跑审计**：图谱侧 Event 节点的核心属性就是那六项，
  事件与文档的关联由 EVIDENCED_BY 承担（见第七节 的待办）。

### 3.3 `_试跑\rejected.jsonl` —— 一行一条被丢弃的条目

```json
{"doc_id": 1030, "item_index": 0, "kind": "entity",
 "reason": "quote_not_in_document", "payload": {"name": "……", "type": "Company", "quote": "……"}}
```

`kind` 取 `document`／`entities`／`events`／`relations`／`entity`／`event`／`relation`；
`reason` 的取值见第四节。**被丢弃的条目一律留原文与理由**，不做静默丢弃。

### 3.4 `_试跑\` 的其余产物

| 文件 | 内容 |
| --- | --- |
| `selection.json` | 试跑选样的 12 篇与**逐篇入选理由**、类目配额、事件类型覆盖、选样断言结果 |
| `coverage.json` | 表 15-C／15-D／15-E 的**脚本重算值**与《15》声明值的逐项比对（声明值只作对照） |
| `run_history.jsonl` | 一行一次运行：API 调用数、缓存命中数、token、墙钟、逐篇用量、清单哈希 |
| `verify.json` | 独立核对结果：本体枚举计数、证据可回溯、证据属性完整性、负对照、可重放比对 |
| `manifest.sha256` | 确定性产物的 `sha256  路径` 清单（缓存 ＋ 解析输出 ＋ 选样 ＋ 覆盖性） |
| `运行日志_首跑.txt`、`运行日志_复跑.txt`、`运行日志_核对.txt` | 三次运行的完整控制台输出 |

`manifest.sha256` **不含**运行日志、`run_history.jsonl` 与 `verify.json`（它们含时间或随运行变化），
因此「清单哈希在两次运行间一致」就等价于「缓存与解析输出逐字节一致」。

### 3.5 `_全量\<数据集版本>\` —— T3 全量抽取的产物（与 `_试跑\` 物理隔离）

`--profile v21` 的产物落点由 `config.FULL_OUTPUT_FILES` 决定（`config.py` 第 8 节；该节只新增
键，既有取值未改动）。文件名与 `_试跑\` 完全一致——`selection.json`、`coverage.json`、
`extracted.jsonl`、`rejected.jsonl`、`run_history.jsonl`、`verify.json`、`manifest.sha256`——
只是落在 `代码\抽取与图谱\_全量\v2.1\`，逐字冻结的 schema 仍是第三节 的那一套。
全量运行的完整控制台输出与汇总报告也落该目录（日志由启动命令重定向 stdout／stderr 生成，
脚本本身不写日志；汇总报告由 `_全量\report_full_run.py` 只读重算）。
该目录**不是交付物、不入仓库**（`.gitignore` 覆盖 `代码/抽取与图谱/_全量/`）。

## 四、证据解析规则（模型只给引用，编号由代码定）

1. 模型对每一条实体、事件、关系都必须给 `quote`；代码在该文档的**文本块序列**里按
   `chunk_index` 升序查找。
2. 归一化**只动空白**：比对前把引用与文本块的空白（含全角空格）**全部去掉**，其余字符
   原样比对（精确子串，不做模糊匹配、不做编辑距离、不做大小写折叠）。取「去掉全部空白」
   而不是「折成单空格」，是因为来源 PDF 抽出的正文存在词内空格（doc_id 1018 写作「公 司将」），
   折成单空格会把合法引用误判为无法定位（2026-09-25 的守卫校准）。
3. 命中多块时取 `chunk_index` 最小的一块，并记录 `quote_match_count`；重叠区命中多块是正常
   现象（切分重叠 50 字符）。
4. 定位失败分两种，必须分开登记：
   * `quote_spans_chunk_boundary`：正文里有，但没有一个文本块完整包含它（机械边界问题，
     切分重叠只有 50 字符，长引用更易命中）；
   * `quote_not_in_document`：正文里根本没有（改写或编造）。
5. 另外三道代码侧的门：
   * 实体 `name` 必须原样出现在正文里（`entity_name_not_in_document` 直接丢弃）；
   * `event_time`／`valid_from`／`valid_to` 只接受 `YYYY-MM-DD` 及其等价写法，且该日期必须在
     正文里真实出现（否则置 `null` 并记 `event_time_unverified`，**绝不猜测**）；
   * 关系端点必须能解析到本篇已通过的实体或事件引用（`entity_ref_unresolved`／
     `event_ref_unresolved`），且端点类型、`role`、`ISSUED_BY` 的事件类型都符合本体。
6. `EVIDENCED_BY` 不由模型输出（`relation_not_allowed`），由程序按 `doc_id` 生成。
7. 同一机构既是发布／作出方又参与该事件时**只保留 ISSUED_BY**，重复的那条 PARTICIPATES_IN
   按 `issued_by_duplicate` 登记后丢弃（《10》第4.5.2节）。
8. 负对照随 `--verify` 一起跑并对 `verify.json` 留痕：把一条**已通过**的引用做三处改写
   （前插／后插／中间插入正文不存在的标记）必须全部被拒；再把本体之外的类型（Product）与
   关系（INVOLVES）喂进同一条解析路径，必须得到 `entity_type_illegal`、
   `event_type_illegal`、`relation_not_allowed`。负对照不通过即为缺陷。

## 五、本体口径（引用《10》第4.5节，不新增、不改名、不合并）

* 实体 6 类：`Company`、`Person`、`Industry`、`Institution`、`Event`、`Policy`；
  `Document` 是证据文档标签，**不是第七类实体**，不参与实体识别与消歧。不引入 Product 与 Location。
* 事件 8 种：`业绩`、`监管`、`股权`、`投资并购`、`重大合同`、`产品`、`政策`、`重大经营`。
* 关系 9 条：`BELONGS_TO`、`SUPPLIES`、`CUSTOMER_OF`、`COMPETES_WITH`、`HAS_EXECUTIVE`、
  `PARTICIPATES_IN`、`ISSUED_BY`、`RELATED_TO`、`EVIDENCED_BY`；已删除的 `INVOLVES` 不复活。
* `role` 只取 {主体, 合作方, 涉及方, 监管方, 受影响方}；`ISSUED_BY` 只出现在政策事件与监管事件上。
* `BELONGS_TO` 另带 `valid_from`、`valid_to`；两者只在正文给出明确日期时填写，否则为 `null`
  （是否用发布时间兜底属 T6 的口径，本组件不替它决定）。
* 编号：试跑用 `ENT-{doc_id}-{序号}`／`EVT-{doc_id}-{序号}`／`REL-{doc_id}-{序号}` 的
  **局部编号**（可回溯、可复算）；全局编号（`EVT-0001`、`policy_id`、`institution_id`、
  `person_id`）由 T6 的 `write_graph.py` 一次性分配并固化进导出物。
* 全部枚举、关系的端点类型与额外属性写在 `config.py` 的 `ENTITY_TYPES`／`EVENT_TYPES`／
  `RELATIONS`／`RELATION_SCHEMA`／`ROLES` 里，是**唯一的取值来源**；脚本与提示词都从那里注入。

## 六、模型与可重放口径

| 项 | 取值 | 说明 |
| --- | --- | --- |
| 请求模型 | 环境变量 `LLM_MODEL`，缺省 `deepseek-v4-flash` | 2026-09-25 实测：该别名**不在** `/models` 列表里，但可调用，响应体 `model` 解析为 `deepseek-flash`，故 `model_pinned` 记为 `deepseek-flash`，逐篇把 `model_resolved` 写进缓存 |
| 模型版本 | `null` | 端点不返回版本／revision（与 `代码\数据准备\config.py` 的 `EMBEDDING` 双钉不同），**可重放性由缓存承担** |
| temperature | 0 | 固定 |
| max_tokens | 8192 | 实测 4096 会把长文档返回截断，端点接受 8192 与 16384 |
| 输出格式 | `json_object` | 端点要求提示词里出现 `json` 字样，提示词已满足 |
| 压缩重试 | 仅当 `finish_reason == "length"` | 同文档重试一次：收紧输出契约（≤2 事件／≤8 实体／≤6 关系、引用 12～60 字）并设 `reasoning_effort="none"`；两次原始返回都进缓存 |
| Prompt 版本 | `stage6-extract-v1.1` | v1.0 → v1.1：新增压缩重试变体（仅截断时使用）；提示词模板另以 `prompt_template_sha256` 逐篇留痕，改了模板必须升版本 |
| 节奏 | 两次调用至少间隔 1 秒 | 传输层失败按 2、4、8……秒指数退避，最多 4 次；4xx（除 429）不重试 |

**可重放的定义**：给定同一份缓存，`extract.py` 重跑必须产出逐字节一致的
`extracted.jsonl`／`rejected.jsonl`／`selection.json`／`coverage.json`，且模型调用次数为 0。
做法是——产物里不写任何时间戳与随机值；排序一律显式（文档按 `doc_id`、拒绝条目按
`doc_id + kind + item_index + reason`、清单条目按路径）；浮点置信度统一四舍五入到 3 位小数；
JSON 序列化固定 `ensure_ascii=False + sort_keys=True`。

## 七、与下游的接口与待办

* **T4（`disambiguate.py`，已落地，见第十节）**：以 `extracted.jsonl` 的 `entities[]` 为输入，
  按 `stock_code` 锚点做消歧；`subject_companies` 只作候选池，不作为「公司参与该事件」的依据
  （《13》第9.1.1节 末段、《15》硬约束 16）。试跑局部编号需在 T4 之前映射为全局编号，
  或在 T4／T6 里保留 `doc_id` 溯源列。
* **T5（`dedup_events.py`，已落地，见第十节）**：按 event_type ＋ 参与主体 ＋ 时间窗口 ＋
  触发词相似度四条件合并；本组件已把 `event_time`、参与主体与 `confidence` 落齐，
  触发词只作调试字段。
* **T6（`write_graph.py`，已落地，见第十节）**：只读缓存；导出物按《15》第4.3节 的四件套落
  `阶段06-事件抽取与知识图谱\图谱导出\v2.1\`，**只含编号、类型、名称、证据编号与置信度，
  不复制正文**；Event 节点的 `source_chunk_id` 不写进节点（事件级证据由 EVIDENCED_BY 承担）。
* **T3 放量前的待办**：`--profile v21` 未执行过；放量前先用 `--limit`／`--docs` 抽查，
  并据 `run_history.jsonl` 的实测均值外推成本（试跑实测见下）。

## 八、运行环境与依赖

* Python 3.12；依赖：`openai`（2.44.0，OpenAI 兼容客户端）、标准库 `json`／`re`／`hashlib`／
  `datetime`。**不引入** LangChain、LlamaIndex、独立向量数据库、Elasticsearch、Kafka、
  微服务、K8s（《02》第8.4节）。
* 端点与模型：`LLM_BASE_URL`（缺省 `https://api.deepseek.com/v1`）、`LLM_MODEL`；
  密钥 `LLM_API_KEY` 只从环境变量读。
* 控制台为 GBK：脚本内已 `sys.stdout.reconfigure(encoding="utf-8")`。
* 参数唯一来源是本目录的 `config.py`：模型名、路径、阈值、事件类型正则、节奏参数都不得写进脚本。
  `extract.py` 里唯一的日期字面量出现在**提示词的格式示例**中（「YYYY-MM-DD 或按正文中文
  日期照抄」那句的举例），不参与任何判定与筛选；脚本中没有写死的模型名、路径或阈值。

## 九、T1 试跑实测（2026-09-25，12 篇／30,396 字符／98 个文本块）

* 规模：实体 55（Company 29／Person 9／Institution 9／Industry 2／Policy 6）、事件 32（8 类全覆盖）、
  语义关系 57（7 类有值，`SUPPLIES` 与 `COMPETES_WITH` 为 0）、`EVIDENCED_BY` 32。
* 证据：144 条带块级证据的条目**全部**通过「块存在 ＋ 同文档 ＋ 引用在该块内」；
  被拒条目 0 条；负对照 4 例全部被正确拒绝。
* 成本：prompt 41,479 ＋ completion 51,591 ＝ **93,070 token**（其中推理 42,411 token，
  占完成量的 82%；prompt 侧命中缓存 39,168 token）；首跑 13 次调用（12 篇 ＋ 1 次压缩重试）、
  墙钟 **211.3 秒**。
* 外推（709 篇）：按篇均 7,756 token／篇 ≈ **5.50 M token**（prompt ≈ 2.45 M、
  completion ≈ 3.05 M）；墙钟 ≈ 17.6 秒／篇 ≈ **3.5 小时**。按正文长度加权的线性拟合给出
  5.24 M token，与篇均外推相差约 5%。
* 可重放：复跑 0 次调用、12 篇全部命中缓存、清单哈希与首跑一致（`291e361c596f3772…`）。

## 十、T4～T7 落地接口与试跑实测（2026-09-25）

四个脚本已落地；参数全部来自 `config.py` **第 9 节**（该节是追加，第 1～7 节的既有键未改动，
第 8 节是并行会话同日追加的 T3 全量产物落点）。四者统一 `--profile pilot|v21` 与 `--force`，
一律 `sys.stdout.reconfigure(encoding="utf-8")`；**T4～T6 不调用模型**，T7 只在缓存不齐时经
`extract.py` 调用（复跑上限 `config.RUN_ALL["max_api_calls_on_replay"]=0`）。
退出码：`0` 成功；`1` 前置／参数问题（未跑上游、指纹不一致）；`2` 数据异常或机检不通过。

### 10.1 落点（`config.GRAPH_PIPELINE`）

| 阶段 | pilot（试跑留痕） | v21（交付物） |
| --- | --- | --- |
| T4 消歧 | `阶段06-事件抽取与知识图谱\_试跑_图谱管线\消歧\` | `阶段05-数据准备\数据集\_抽取缓存\v2.1\图谱管线\消歧\` |
| T5 去重 | `阶段06-事件抽取与知识图谱\_试跑_图谱管线\去重\` | `…\_抽取缓存\v2.1\图谱管线\去重\` |
| T6 导出 | `阶段06-事件抽取与知识图谱\_试跑_图谱管线\图谱导出\` | `阶段06-事件抽取与知识图谱\图谱导出\v2.1\` |

T6 另在**工作目录**（不是导出目录）写 `graph_check.json`（第八节逐行机检）与
`manifest.sha256`（校验和索引，含 `graph_stats.json` 一行，故它本身随运行变化）。

### 10.2 产物字段

* **T4**：`alias_table.json` 只读第 5 阶段冻结的 105 家公司配置（`code／name／industry／board`）；
  另只读 `company_registered_names.py` 的注册全称（**数据扩展，规则未改**；2026-09-26 建档：
  语料写工商登记全称而配置里只有市场简称，简称不是全称的子串 → R2 永不触发；补上注册全称后
  公司提及消歧率 32.7% → 39.9%、配置公司覆盖 90／105 → 104／105）。每个 code 的
  `normalized_alias_surfaces` ＝ 归一化简称 ∪ 归一化注册全称，两条规则对其中每个书写面求值；
  `disambiguation.json` 的 `entity_map` 把局部编号映射为身份键 `<标签>:<身份>`
  （公司＝`Company:<stock_code>`，其余＝`<标签>:<归一化名>`，归一化只去空白与最外层包裹字符）；
  `companies` 块用**表 4-8 字段口径**（`company_name` 取语料中出现过的最长书写面、`short_name`／
  `exchange`／`industry` 取自冻结配置、`aliases` 取其余书写面、另留 `observed_surfaces` 溯源）；
  `unresolved.jsonl` 是待消歧清单（含 `reason`、`matched_codes`、`blocked_by_marker`）。未消歧公司的
  `identity_key` 为 `null`。
* **T5**：`merge_log.jsonl` 逐对候选给**四条件逐条读数 ＋ 判定**（`merged`／`not_merged` 与
  `first_failed_condition`）；`events_merged.jsonl` 是合并后的事件集合（`merged_event_key`、
  `members`、`evidence_doc_ids` 并集、`participants`／`issued_by`／`related_to` 的全部证据行）；
  `merge_summary.json` 汇总计数；`dedup_self_test.json` 是自检（见 10.4），不是交付物。
* **T6**：四件套按《15》第4.3节。`nodes.csv` 33 列（`config.GRAPH["node_columns"]`，逐字取自表 4-8）、
  `edges.csv` 9 列（含 `role`／`valid_from`／`valid_to`）。编号显式分配：Company＝`stock_code`、
  Document＝`doc_id`，其余按确定性排序分配 `PER／INST／POL／IND／EVT-####`（宽度 4），
  不使用自增。`replay.cypher` 含《10》第4.5.3节 的 7 条唯一性约束 ＋ 3 条索引与逐节点、逐边重放语句。
* **T7**：`--only <阶段>`／`--from <阶段>` 支持续跑；`--force` 只重算 T4～T6，**不会**让 extract
  重新调用模型（要重跑抽取用 `--force-extract --allow-api-calls`）；日志写
  `运行日志_首跑.txt`／`运行日志_复跑.txt`，含每阶段命令行、退出码、耗时、关键读数与产物 sha256。

### 10.3 口径补充（本文件第三节 未覆盖的）

* `Event.event_time` 允许为空且**计数上报**（`graph_stats.json` 的
  `event_core_attributes.event_time_null_count`）：T3 的口径是「不能确定到日写 null，绝不猜测」，
  与《15》第八节「六项核心属性齐全且非空」的差异如实上报，不编日期凑齐。
* `BELONGS_TO.valid_from／valid_to` **不用发布时间兜底**（本文件第五节的悬置项在这里定为「留空」），
  空值条数计入机检读数。
* 未消歧实体**不写进图谱**（`config.GRAPH["include_unresolved_entities"]=False`：人工确认后再写入），
  引用它们的关系边跳过并逐条计数（`graph_stats.json.unresolved`）。
* T5 的「参与主体」＝`PARTICIPATES_IN` 起点 ∪ `ISSUED_BY` 终点（身份键**集合相等**）；任一端点
  未消歧即本条件不成立。「触发词相似度」取 `event_name` 的字符二元组 Jaccard（T3 未产出 trigger）。
* 逐字节可复现：`nodes.csv`／`edges.csv`／`replay.cypher`／`graph_check.json` 两次运行完全一致；
  `graph_stats.json` 只有 `generated_at`（与缓存指纹字段）每次不同，两者单独成行，比对时排除。

### 10.4 T4～T7 试跑实测（12 篇，`extracted.jsonl` sha256 `0df3bc008b6495c5…`）

* **T4**：实体 55 → 已消歧 34／待消歧 21（`no_alias_match` 20、`distinct_entity_marker` 1）；
  公司身份 8 个（002051、600048、600089、600276、600309、600406、601727、603288）。
  `万华化学集团股份有限公司` 等全称经 R2 归并；`上海电气控股集团有限公司` 因残余含「控股」
  判为另一主体，进待消歧清单。
* **T5**：事件 32，类型相同的候选对 57，四条件同时满足 **0** 对 → **无合并**；首个不成立条件的
  分布 `{participants: 47, time_window: 9, trigger_similarity: 1}`。自检 `passed=true`：
  把 doc 1018 原样复制成合成文档后合并成组，合并后事件的证据文档为 `[1018, 901018]`（并集）。
* **T6**：节点 76（Event 32／Document 12／Person 9／Company 8／Institution 7／Policy 6／
  Industry 2），边 74（EVIDENCED_BY 32／PARTICIPATES_IN 27／RELATED_TO 5／ISSUED_BY 5／
  HAS_EXECUTIVE 4／BELONGS_TO 1）；未消歧端点跳过 15 条边，无边节点 8 个；机检 17 项通过 15，
  两项已知缺口即 `event_time` 空值 19 条与 `BELONGS_TO` 有效期留空。
* **T7**：整链复跑 2 次，`extract.py` 12 篇全部命中缓存、**模型调用 0 次**，各产物逐字节一致
  （`graph_stats.json` 剔除上述两个字段后一致）。

## 十一、T3.5 定向时间补抽 与 人工确认的实体写入图谱（2026-09-26 追加）

本节是 2026-09-26 两项修复的接口口径：**只新增**（新脚本、新缓存目录、新覆盖层、新确认文件），
`extract.py`、主抽取缓存 `_抽取缓存\v2.1\{doc_id}.json`、第 1～9 节既有参数取值一律未改。

### 11.1 T3.5 定向时间补抽（`extract_event_time.py`）

* **只处理 null 事件**：T3 实测 989／1649 条事件的 `event_time` 为 null；补抽只为这些事件建
  一个小提示词（事件类型／事件名称／证据引文／引文周围的**有界窗口**／文档 `publish_time`），
  非空事件一个字节都不改。
* **窗口大小（本节定义，脚本与 config 同步登记）**：以证据引文在**证据块**里的匹配位置为中心，
  前后各取 `EVENT_TIME_BACKFILL["window_chars"]=500` 个字符；窗口贴到该证据块边界时，允许把
  同文档前／后各一块最多 `neighbor_chars=300` 个字符补进来。窗口因此**有界**：
  ≤ 2×500 ＋ 引文长度 ＋ 2×300（实测典型 700～1900 字符，约合全量的 1/4 文档长度）。
  选择 500／300 的理由（实测）：把它放大到 900／600 只多出 59 条「窗口里有完整日期」的候选，
  而「≥2 条带日期事件」的可过滤性指标在两种窗口下的上界完全相同（163 篇），故取更小更便宜的一档。
* **日期书写形式**：`2026 年8 月27 日`（数字与 CJK 之间夹空格，语料实测写法）与
  `2026年8月27日`／`2026-08-27`／`2026/8/27`／`2026.8.27` 等价；提示词里写明，复核在**去掉
  全部空白**的窗口副本上比对。**日期可以出现在窗口的任何位置**（不必落在证据引文内），
  但模型必须把承载日期的那一句逐字抄进 `evidence_quote`（≤200 字）。
* **年份锚定规则（确定性、不猜）**：窗口只给「月日」时，年份由 `publish_time` 锚定——
  **月 ≤ 发布月 → 发布年；否则 发布年 − 1**；记 `event_time_basis="year_from_publish"`
  （**绝不**记成 `stated`），且月日必须在窗口里**独立出现**（前不带年份、后不带数字）才认定。
* **`event_time_basis` 三值**：`stated`（正文明确写出年月日，且复核得到）／`year_from_publish`
  （月日 ＋ 锚定年份）／`null`（窗口内确实没有可归属的日期）。复核不过一律回到 `null`，
  并在结果里写 `reject_reason`（如 `stated_date_not_in_window`／`anchored_year_mismatch`），
  **绝不编日期**。
* **缓存（独立，与主抽取缓存物理分开）**：`_抽取缓存\v2.1\时间补抽\{event_id}.json`，只存
  **原始返回 ＋ 模型 ＋ prompt 版本 ＋ 输入 sha256 ＋ 窗口 sha256**；解析与复核每次重算，
  所以改复核规则不需要重调模型。缓存命中即**零模型调用**（不需要密钥、不需要网络）；
  缓存与当前输入不一致且未 `--force` 时阻断。
* **覆盖层（`dedup_events.py` 的唯一新增输入）**：`_全量\v2.1\event_time_backfill.json`
  （pilot 落 `_试跑\`），**不含任何时间戳**，逐字节可重放；`dedup_events.py` 把它应用在事件
  视图上——补出来的日期**同样参与**时间窗条件，合并后事件的 `event_time_basis` 取提供最早
  非空日期的那位成员。产物里记 `time_backfill_sha256`，`write_graph.py` 校验它与盘上覆盖层一致。
* **审计产物**：`event_time_backfill_report.json`（调用次数／token／墙钟／依据分布／复核拒绝
  原因／抽样）、`时间覆盖_度量.json`（`--measure`：抽取层与图谱层的覆盖与可过滤性读数）。

### 11.2 人工确认的实体写入图谱（`write_graph.py`）

* **确认是数据**：人可编辑的 `阶段06-事件抽取与知识图谱\图谱导出\v2.1\人工确认清单.json`
  （`config.HUMAN_CONFIRMATION`、`config.human_confirmation_path()`），由
  `待人工确认清单.md` 播种；每条带 `confirmed` 字段，`true` 即确认。脚本只读它，不做判定、
  不设默认值。
* **写入口径**：`confirmed: true` 的条目各建**一个**自己的节点（节点名＝`name` 书写面，
  **不填 stock_code**——没有解析出代码，也不猜），编号按归一化名称确定性分配 `HCONF-####`；
  同名只产生一个节点。**确认名称命中配置公司书写面时拒绝建节点并计数上报**（绝不把确认名称
  并进配置公司）。`confirmed: false` 或缺失的条目继续按原口径排除。
* **可审计**：`graph_stats.json` 的 `human_confirmation` 段记确认文件路径／sha256／确认与未确认
  条目数／新增节点数与编号／据此写入的边数与按关系分布／被拒绝的条；`graph_check.json` 另加
  三条机检（无 stock_code、同名唯一、与确认文件的条目数一致）。`manifest.sha256` 追加一行
  确认文件的校验和。
