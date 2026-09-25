# 代码\数据准备 —— 第 5 阶段数据管线

本目录是第 5 阶段（数据准备）的实现工作区。**接口冻结文档**：所有模块必须按本文件定义的
输入输出与命令行契约实现，不得自行更改字段名、编号方案或参数来源。

参数一律来自 [config.py](config.py)，脚本内**不得写死**任何模型名、日期、路径或阈值。

## 一、模块与职责

| 模块 | 子任务 | 输入 | 输出 |
| --- | --- | --- | --- |
| `config.py` | — | — | 全部冻结参数（已写好，**不要改**） |
| `fetch.py` | T1、T2、T3 | 网络 | `meta\sources.csv`、`raw\{doc_id}.json`、`raw\_fetch_log.jsonl` |
| `dedup.py` | T4a | `raw\` | `reports\dedup_log.jsonl`；对 `raw\` 打重复标记 |
| `clean.py` | T4b | `raw\` + 去重结论 | `clean\documents.jsonl`、`reports\clean_stats.json`、`reports\skipped.jsonl` |
| `chunk.py` | T5 | `clean\documents.jsonl` | `chunks\chunks.jsonl`、`reports\chunk_stats.json` |
| `embed.py` | T6 | `chunks\chunks.jsonl` | `index\faiss.index`、`index\vector_map.jsonl`、`index\build_meta.json`；回填 `chunks\chunks.jsonl` 的 `vector_id` |
| `check.py` | T8 | 上述全部 | `reports\consistency_report.json`、`reports\consistency_report.md`、`reports\time_coverage.json`、`reports\company_coverage.json`，并写出 `meta\dataset.json`（《12》§八 第 3 行要求的版本级元信息，由实测数据与 config 生成） |
| `run_all.py` | 入口 | — | 按顺序串起 fetch → dedup → clean → chunk → embed → check |

## 二、命令行契约

每个脚本都必须支持：

```bat
python 代码\数据准备\fetch.py   --profile v1
python 代码\数据准备\dedup.py   --profile v1
python 代码\数据准备\clean.py   --profile v1
python 代码\数据准备\chunk.py   --profile v1
python 代码\数据准备\embed.py   --profile v1
python 代码\数据准备\check.py   --profile v1
python 代码\数据准备\run_all.py --profile v1
```

* `--profile v1`（默认）：写入 `阶段05-数据准备\数据集\v1.0\`。
* `--profile pilot`：写入 `阶段05-数据准备\_试跑\`，用 3 家公司／20 篇做小规模验证
  （《12》§九"小规模先行的纪律"）。**试跑目录不是交付物，不得与 v1.0 混用。**
* `--dir <路径>`：**仅供自测**，把输出根目录改到任意临时目录。正式封版一律用
  `--profile v1`，不得用 `--dir` 指向正式数据集以外的位置产出交付物。
* `--force`：忽略已完成标记，强制重跑本环节。
* **幂等**（《12》§5、§八）：同一输入重复运行不得产生重复 `doc_id`；已存在的
  `raw\{doc_id}.json` 默认跳过，除非 `--force`。中断后可从任意环节续跑。

所有脚本：`sys.stdout.reconfigure(encoding="utf-8")`，退出码 0 表示成功。

## 三、数据格式（逐字冻结，下游按此消费）

### 3.1 `raw\{doc_id}.json` —— 一篇文档一个文件，采集后不再修改

```json
{
  "doc_id": 1001,
  "category": "公告",
  "source": "巨潮资讯网",
  "title": "关于2026年金融债券（第一期）发行完毕的公告",
  "company_list": ["000001"],
  "publish_time": "2026-09-22",
  "page_url": "https://www.cninfo.com.cn/new/disclosure/detail?...",
  "content_url": "https://static.cninfo.com.cn/finalpage/2026-09-22/1225574840.PDF",
  "raw_text": "……抽取到的完整正文（未清洗）……",
  "extract_method": "pdf_pymupdf | html_bs4 | api_json",
  "fetched_at": "2026-09-25T14:00:00+08:00",
  "http_status": 200,
  "byte_size": 110749,
  "meta": {}
}
```

* `category` 只能取 `config.CATEGORIES` 四个值之一。
* `publish_time` 为 `YYYY-MM-DD`，**不晚于** `config.DATA_CUTOFF_DATE`，且落在
  `[WINDOW_START, WINDOW_END]` 内。
* `company_list` 为**股票代码字符串数组**；公告与财经新闻必须非空；政策文件与监管
  公开信息允许为 `[]`，**不得为 null**。
* `meta` 放来源特有字段（如巨潮的 `announcementId`、证监会的 `索引号`），结构自由，
  但必须是 JSON 对象。

### 3.2 `raw\_fetch_log.jsonl` —— 抓取记录，一行一次尝试

```json
{"doc_id": 1001, "category": "公告", "source": "巨潮资讯网", "url": "...",
 "http_status": 200, "ok": true, "chars": 436, "byte_size": 110749,
 "elapsed_ms": 812, "fetched_at": "...", "note": ""}
```
失败的尝试也写入（`ok:false`、`note` 写原因），并跟进 `reports\skipped.jsonl`。

### 3.3 `clean\documents.jsonl` —— 一行一篇（对应 document 表）

```json
{"doc_id": 1001, "title": "...", "content": "...", "source": "巨潮资讯网",
 "category": "公告", "url": "https://static.cninfo.com.cn/...",
 "publish_time": "2026-09-22", "ingest_time": "2026-09-25T14:00:00+08:00",
 "company_list": ["000001"], "content_sha256_16": "a1b2c3d4e5f60718"}
```

字段名与《10》§4.4.1 的 document 表一致。`content_sha256_16` 是数据集内部字段，
用于去重核验（不入库；《10》规定 document 表不新增字段）。

### 3.4 `chunks\chunks.jsonl` —— 一行一个文本块（对应 document_chunk 表）

```json
{"chunk_id": 1001000, "doc_id": 1001, "chunk_index": 0, "content": "...",
 "token_count": 412, "vector_id": 0}
```

* `chunk_id = doc_id * 1000 + chunk_index`（由 `config.chunk_id_for` 生成）。
  例：doc_id 1001 的第 0 块是 1001000、第 1 块是 1001001。
* **切分前的编号步长预检**：`chunk.py` 在写盘前先逐篇投影文本块数，只要有一篇超过
  `config.DOC_ID_STRIDE`（＝单篇 1000 块），就点名 `doc_id`／标题／字符数／投影块数，
  并指出该文档本应被 `config.MAX_DOC_CHARS_FOR_INCLUSION` 在采集候选阶段排除，随后
  **以非零码退出**（不再落到 `config.chunk_id_for` 的裸 `ValueError`）。预检只报告，
  绝不截断正文、绝不丢弃文档；投影与实际切分共用同一实现，故投影块数即落盘块数。
* `chunk_index` 在文档内从 0 连续递增、不重复（对应 `uk_chunk_doc_index`）。
* 每篇文档至少 1 个文本块。
* `token_count` 用 **Embedding 模型自带的 tokenizer** 统计（不含特殊标记）。
* `vector_id` 在 `embed.py` 之前为 `null`，之后回填为整数。

### 3.5 `index\`

* `faiss.index`：`IndexFlatIP`，向量已 L2 归一化（内积＝余弦相似度）。
* `vector_map.jsonl`：一行一条 `{"vector_id": 0, "chunk_id": 1001000, "doc_id": 1001}`，
  **双向可查**（vector_id→chunk_id→doc_id，且 chunk_id→vector_id 由 `chunks.jsonl` 给出）。
* `build_meta.json`：模型名与 revision、维度、条数、构建时间、索引类型。

### 3.6 `meta\`

* `dataset.json`：见《12》§八第 3 行要求的全部字段。
* `sources.csv`：`name,category,home,url_template,access_note,rate_limit_seconds,notes`。

### 3.7 `reports\`

`dedup_log.jsonl`、`clean_stats.json`、`skipped.jsonl`、`chunk_stats.json`、
`consistency_report.json` + `.md`、`time_coverage.json`、`company_coverage.json`。

`skipped.jsonl`（由 `clean.py` 写）每行一篇被跳过的文档，`reason` 取值与判定优先级为
`dedup_dropped`（被 T4a 淘汰）→ `too_short`（清洗后正文 < `config.MIN_DOC_CHARS`）→
`too_long` → `empty_company_list`（公告／财经新闻的 `company_list` 为空）。其中：

* **`too_long`**：清洗后正文**超过** `config.MAX_DOC_CHARS_FOR_INCLUSION`（默认 60000 字符）
  的文档整篇跳过，行内另带实测长度 `chars` 与说明 `detail`。这是**兜底守卫**——正文长度上限
  的正常落点是 §4.5 的采集候选阶段过滤（在选入之前整篇丢弃、绝不截断），因此**正常一轮运行
  里 `too_long` 应当始终为 0 条**；它存在的意义是：即便未来来源形态变化、或 `raw\` 里残留了
  旧构建写入的超长文档，`clean.py` 也会把它挡在 `chunk.py` 之外，避免单篇正文撑爆
  `chunk_id = doc_id * 1000 + chunk_index` 的编号步长。命中条数同样计入
  `clean_stats.json` 的 `per_category[].skipped.too_long` / `skip_reasons.too_long`，
  并写入 `params.max_doc_chars_for_inclusion` 供核对。

`chunk_stats.json` 除既有字段外新增 `over_long_documents`（**报告项：只报告，绝不截断、
绝不丢弃文档**）：列出 `chunk_count > params.max_chunks_per_doc_warn`
（＝`config.MAX_CHUNKS_PER_DOC_WARN`，默认 120）的每篇文档，每项含 `doc_id`、`title`、
`chunk_count`、`doc_chars`（切分输入正文的字符数）、`share_of_chunks`
（该文档文本块数 ÷ 全部文本块数，四舍五入到 4 位小数），按块数降序排列；
`chunk.py` 另在 stdout 打印一行告警点名最严重的一篇。截断正文等于改写证据
（《10》§4.4.6 要求证据按原文展示），故本项只让"某一篇把索引吃掉"这类问题在报告里显形。

`time_coverage.json`（连同 `consistency_report.md` 的"时间覆盖明细"一节、`meta\dataset.json`
的 `time_range`）必须带齐以下实测字段，供《12》v1.2 的"逐月可见"要求核对：

* `window_start` / `window_end` / `window_days`：采集窗口（`config.WINDOW_START` /
  `WINDOW_END` / `WINDOW_DAYS`＝100 天），直接来自 `config`；
* `publish_time_min` / `publish_time_max` / `span_days` / `cutoff_minus_earliest_days`
  与通过门槛 `coverage_required_days`（check #13 判定 `cutoff − publish_time_min ≥ 90` 天）；
* `per_month_histogram`：最早与最晚文档之间**每一个自然月**的文档数，无文档的月份
  **显式记 0**（另见 `months_with_zero_documents`），使窗口内部的整月空洞看得见；
* `analysis_90_range`：`config.ANALYSIS_90_RANGE`（＝`[cutoff−90d, cutoff]`）的文档数
  ——**报告项，不参与 check #13 的通过判定**；
* `earlier_halves`：`config.BUCKET_EARLIER` 按天数平均分成的前后两半各自的文档数
  ——同样是**报告项**，用于把窗口正中间整月没有文档的情形直接显示出来；
* `buckets`：`recent` / `earlier` 两个时间桶的区间、篇数、下限与 doc_id 清单
  （check #13 的判定依据）。

## 四、已勘察确认的取数端点（2026-09-25 实测可用）

参数与来源清单以 `config.py` 为准，这里只记**接口形状**，实现不得改用其它站点。

### 4.1 公告（巨潮资讯网）

1. 代码 → orgId：`POST https://www.cninfo.com.cn/new/information/topSearch/query`，表单
   `keyWord=000001&maxNum=10` → `[{"code","orgId":"gssz0000001","zwjc":"平安银行",...}]`
2. 公告列表：`POST https://www.cninfo.com.cn/new/hisAnnouncement/query`，表单
   `pageNum,pageSize,column(=szse|sse),tabName=fulltext,stock="{code},{orgId}",`
   `seDate="{start}~{end}",isHLtitle=true`
   → `announcements[]` 每项含 `secCode,secName,announcementTitle,announcementTime(毫秒),`
   `adjunctUrl,adjunctType,announcementId`
   **该接口每页最多只返回 30 条**（2026-09-25 实测：`pageSize` 传 30/50/100/200 均只回
   30 条），故 `pageSize` 固定为 30，要覆盖整个时间窗必须翻页（见第 5 条）。
3. 正文：`GET https://static.cninfo.com.cn/{adjunctUrl}`（PDF）→ PyMuPDF `fitz` 抽取文字。
   必须带 `Referer: https://www.cninfo.com.cn/` 与浏览器 UA。
   `page_url` 用 `https://www.cninfo.com.cn/new/disclosure/detail?stockCode={code}&announcementId={id}&orgId={orgId}&announcementTime={ms}`。
4. **定期报告类公告不进候选池**（2026-09-25 增设；参数唯一来源仍是 `config.py`）：
   标题命中 `config.profile_settings(profile)["exclude_announcement_title_patterns"]`
   （＝`EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_V1`）中任一 `re.search` 模式的公告，
   在**候选收集阶段**即被丢弃——先于 level-1 时段分层配额与 level-2 时间铺开，
   因此分层只从存活候选里抽；某时段／子区间因排除而不够时，由既有补足口径
   （另一时段补足、同区间剩余候选最新优先回填）处理，不设特殊分支。
   每次运行按类别向 `raw\_fetch_log.jsonl` 追加一行 `ok:true` 审计行，逐模式给出
   排除条数与被截断到约 40 字符的示例标题；某类别零排除也照写，作为"过滤已执行"的凭据。
   理由见 `config.py`：定期报告正文极大（试跑实测《贵州茅台2026年半年度报告》
   11.8 万字符／364 个文本块＝521 块的 70%，会让单篇吃掉索引），且《02》§9.2 的
   8 种事件类型不含"发布定期报告"，业绩信息由业绩预告／业绩快报类公告承载。
   **只排除整篇、不截断正文**：截断等于改写证据（《10》§4.4.6）。
5. **列表接口翻页**（2026-09-25 增设；参数唯一来源仍是 `config.py`）：
   `cninfo_announcements()` 从 `pageNum=1` 起，按 `config.CNINFO_MAX_PAGES`
   （v1＝4 页＝每家公司最多 120 条候选）逐页请求 `hisAnnouncement/query`，再把各页合并成
   一个候选池，**按 `announcementId` 去重**——同一篇公告即使跨页重复出现也只入池一次
   （该字段缺失时退回 `adjunctUrl` 作去重键）。两个提前停止条件：某页返回 0 条
   （已到列表末尾），或该页**最旧**一条 `announcementTime` 已早于 `config.WINDOW_START`
   （再往前翻只会更旧）。每次列表页请求都走模块既有的 HTTP 助手，因此
   `config.HTTP["min_interval_seconds"]` 的限流对翻页照常生效，不会形成请求突发。
   翻页只扩大候选池的覆盖范围，**下游口径一律不变**：标题排除、level-1 时段分层配额、
   level-2 时间铺开、确定性排序、doc_id 分配与幂等续跑（同一 URL 复用既有 doc_id）全部沿用；
   `fetch.py` 的 stdout 摘要在 `[公告]` 行额外给出本次实际发出的列表页请求数
   （`公告列表页请求 N 次`）。起因：中国石化在 100 天窗口内有 85 篇公告，只取第 1 页时
   最早的候选只到 2026-08-24，earlier 时段（`[2026-06-17, 2026-08-26]`）几乎没有候选，
   分层抽取只能跨段回填，v1 实测每公司公告数为 5,5,5,4,2,5,5,5,3,5（中国石化只填到 2/5）。

### 4.2 监管公开信息（中国证监会）

`GET https://www.csrc.gov.cn/searchList/{channelGuid}?_isAgg=true&_isJson=true&_pageSize={n}&_template=index&page={p}`

已实测的 channelGuid：

| 栏目 | channelGuid | 记录数 |
| --- | --- | --- |
| 行政处罚 | `17d5ff2fe43e488dba825807ae40d63f` | 2042 |
| 市场禁入 | `3795869930ca4b70bf55469270a6e641` | 366 |

返回 `data.results[]`，每项含 `title, url（协议相对，形如 //www.csrc.gov.cn/csrc/.../content.shtml）,
publishedTime, publishedTimeStr, content, contentHtml, domainMetaList`。
`domainMetaList` 里有 **索引号**（`key:"syh"`）与 **发文日期**（`key:"fwrq"`）。

> **同题标题问题**：行政处罚决定书在列表中标题完全相同（均为"中国证券监督管理委员会
> 行政处罚决定书"）。标题必须按 `《12》§八 修订后` 的口径构造为
> `原标题（当事人）`，当事人取自**来源文档自身正文**（正文首行／首位当事人），
> 不得臆造。若仍冲突，用 `索引号` 消歧，并登记到 `reports\dedup_log.jsonl`。

### 4.3 政策文件（中国政府网政策文件库）

`GET https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary_gw|zhengcelibrary_bm&q={kw}&timetype=timeqb&sort=pubtime&sortType=1&p=1&n=20&type=gwyzcwjk`

`searchVO.listVO[]` 每项含 `title（含 <em> 高亮，需去标签）, url, pubtimeStr(YYYY.MM.DD),
puborg, wenhao, summary`。正文抓 `url` 对应页面（静态 HTML，`div#UCAP-CONTENT` / `div.pages_content`）。

### 4.4 财经新闻（人民网财经／中证网／证券日报网）

栏目页静态 HTML，正则抽正文页链接（见 `config.NEWS_SITES` 的 `article_pattern`），
再抓正文。发布时间优先取 `<meta name="publishdate">`，缺失时回退到正文中的
`YYYY年MM月DD日` / `YYYY-MM-DD`。**抽不到发布时间的文章直接丢弃并登记**，
不得用抓取当天充当发布时间。

### 4.5 正文长度上限（四类来源统一口径，2026-09-25 增设）

参数唯一来源：`config.MAX_DOC_CHARS_FOR_INCLUSION`（默认 60000 字符）。口径是**整篇排除**，
**不是截断**——截断等于改写证据（《10》§4.4.6 要求证据按原文展示，《12》§七 非目标）。

* **作用位置**：候选的正文**一经抽取**就与上限比对，且必须发生在 level 1（时段分层／配额）
  与 level 2（时间铺开）**之前**。因此被丢弃的候选会由下一条合规候选顶替，
  每公司／每类别配额不会被抽空；若过滤后窗口内**确实**凑不够，沿用既有短缺口径
  （取现有篇数并登记到 `raw\_fetch_log.jsonl`），不臆造文档。
* **公告**（§4.1）：`select_announcements_for_company()` 每轮先按既有口径选一轮，逐篇探测
  正文长度；超长候选整篇丢弃并从候选池剔除后重选，直到选出的候选全部合规。探测与正式落盘
  共用同一次下载（缓存按内容 URL），故同一篇公告一轮运行最多下载一次。
* **监管公开信息／政策文件**（§4.2／§4.3）：`pick_balanced_with_length_cap()` 在
  `pick_balanced` 选入之前做同一件事（监管正文页不可用时按既有口径退回同源接口正文后测长度）。
* **财经新闻**（§4.4）：正文在抓取时就已抽取，过滤在 `materialize_news()` 内完成——超长文章
  整篇丢弃、不计入配额，抓取循环继续取后续候选顶替，随后才做 level 1 + level 2 选择。
* **审计**：每个类别向 `raw\_fetch_log.jsonl` 追加的 `ok:true` 审计行里增加
  `正文长度上限过滤审计：上限 config.MAX_DOC_CHARS_FOR_INCLUSION=… 字符；本轮已探测正文的
  候选 N 篇，其中超过上限、整篇丢弃 M 篇；示例：《标题》（字符数）…`（最多 3 条示例），
  零丢弃也照写，作为"过滤已执行"的凭据。
* **兜底**：`clean.py` 另有 `too_long` 跳过守卫（§3.7），`chunk.py` 另有切分前的编号步长
  预检（§3.4）；三者是同一口径在采集、清洗、切分三处的落点。
* **起因**：v1 实测一篇 397454 字符的《2025年可持续发展报告（英文版）》占全库 51.72%
  的字符、单篇约 1135 个文本块，直接撑爆 `DOC_ID_STRIDE=1000` 的编号步长并让 `chunk.py`
  中止；另有两篇 81880／81448 字符的长文各占 10% 以上。

## 五、必须遵守的纪律

1. **只写 `dataset_dir(profile)` 之下**：不得写 `阶段05-数据准备\数据集\v1.0\` 以外的
   正式数据集路径；试跑只写 `_试跑\`。
2. **不越界**（《12》§五 硬约束 14、§七）：不写抽取规则、不做实体消歧、不写 Cypher、
   不做标注、不建测试集、不写 DDL、不接大模型。只做采集→去重→清洗→切分→向量化→检查。
3. **不引入**（《02》§8.4）：LangChain、LlamaIndex、独立向量数据库、Elasticsearch、
   Kafka、微服务、K8s。FAISS 一律称"向量索引／向量检索组件"，**不得写"向量数据库"**。
4. **控制抓取频率**：每次 HTTP 请求之间至少 `HTTP.min_interval_seconds` 秒，
   失败重试按 `max_retries` 指数退避。这是来源网站访问规范的要求（《12》§五 硬约束 12）。
5. **真实数据，不得编造**：标题、时间、URL、正文全部来自来源网站；抓不到就登记跳过，
   **绝不允许用生成文本、占位文本或改写的文本充数**。
6. **不做"取所有文档最晚时间"的推导**：`data_cutoff_time` 只来自 `config`。
7. 每个脚本跑完打印一行统计摘要（条数、跳过数、耗时）。

## 六、运行环境

* Python 3.12；依赖：`requests`、`beautifulsoup4`、`lxml`、`PyMuPDF`、`numpy`、
  `faiss-cpu`、`sentence-transformers`（均已安装）。
* Embedding 模型 `BAAI/bge-small-zh-v1.5` 已下载至 HuggingFace 缓存
  `D:\Cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5`，**离线可加载**。
* 控制台为 GBK：脚本内必须 `sys.stdout.reconfigure(encoding="utf-8")`，否则中文输出乱码。
* **不使用 Playwright**：四类来源均已用 HTTP 接口或静态 HTML 解决，无需无头浏览器。
