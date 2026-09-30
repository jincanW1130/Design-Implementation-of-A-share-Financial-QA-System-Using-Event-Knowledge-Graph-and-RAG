# 代码\后端 —— 第 9 阶段（前后端系统集成）后端

本目录是第 9 阶段后端的**骨架**（《24-第9阶段任务书》第七节 T4）。本批已落位
T2（数据库落地）与 T4（后端骨架）两件；表 4-13 的 27 个业务接口留待后续批次。

唯一规格：`阶段09-前后端系统集成\24-第9阶段任务书（前后端系统集成）.md`；
表结构逐字对齐 `阶段04-系统总体设计\10-系统总体设计（第四阶段）.md` 第 4.4.1 节 表 4-6。

---

## 1. 组成

| 文件 | 职责 |
| --- | --- |
| `config.py` | **唯一参数来源**：路径、输入清单、上游定值（K／N／预算／g、模型与 Prompt 版本）、本机连接参数、接口门槛参数 |
| `config.local.json` | 本机取值（含口令）。**不入公开仓库**（`.gitignore` 覆盖 `*.local.json`） |
| `config.local.json.example` | 模板；复制成 `config.local.json` 后填值 |
| `schema\六张表.sql` | 六张表的 DDL（唯一 schema 出处）；**不含库名**，库由脚本按配置建 |
| `db.py` | MySQL 访问层：**PyMySQL ＋ 显式 SQL、不用 ORM**；连接、事务、建库建表、元数据查询 |
| `errors.py` | 错误码表、`ApiError`、统一成功／失败响应封装、FastAPI 异常处理装配 |
| `main.py` | FastAPI 装配：CORS、统一异常处理、请求体大小与问题长度校验、按来源 IP 限流、`GET /api/health` |
| `run.py` | 启动入口（uvicorn；主机固定 `127.0.0.1`、端口取 `config.local.json`） |
| `tools\import_data.py` | 数据集与问答记录导入六张表（**幂等**；`--dry-run`／`--reset`／`--limit N`） |
| `tools\import_graph.py` | 图谱导出物导入 **Neo4j**（**幂等**；`--dry-run`／`--reset`／`--verify-only`；计数对拍 2802／2736） |
| `services\graph_service.py` | 图谱查询服务：`neo4j`（默认）／`memory` **两个可切换后端**，同一套 G1～G7 语义；`--selftest`／`--parity-check` |
| `services\market_service.py` | **实时数据区**取数服务（三个外部源 ＋ 一个语料内源）；进程内 60 s 缓存；源失败降级为「未接入」；`--selftest`。见 §3.2 |
| `api\market.py` | 实时数据区四条只读接口 `/api/market/{quote,announcements,news,reports}`（**只作展示、不进证据链**）。见 §3.2 |

## 2. 约定（后续批次请照此对齐）

### 2.1 参数只从 `config.py` 取

脚本与接口里**不写死**库名、连接串、端口、路径、K／N／预算／g、模型名与版本、日期。
检索侧四项定值与生成侧配置是**从上游 `代码\检索\config.py`／`代码\问答\config.py`
按文件路径 import 进来的**（不是本目录再抄一份字面量），上游为 `None`／缺失即报错退出。

### 2.2 口令纪律

`mysql_password` 只从 `config.local.json` 读：不写死、不回显、不落盘、不进日志、
不进前端构建产物。`config.py` 的自检只打印「已配置／未配置」。

`mysql_password` 为空或仍是模板占位串时：**导入期不退出**（`MYSQL_PASSWORD_READY=False`），
真正要连库时由 `config.db_params()` 抛 `SystemExit`，提示里含
「请检查 `代码\后端\config.local.json`」。因此 `--dry-run` 在凭据未填时仍能跑通。

### 2.3 响应格式

* 成功：`{"data": …, "meta": {"dataset_version": …, "data_cutoff_time": …}}`
* 分页：`data` 内为 `{"total": …, "items": […], "page": …, "page_size": …}`
* 失败：**响应体键集合恰为 `{code, message}`**；`detail` 只进后端日志，绝不进响应体
* `2002`（查询结果为空）是**正常业务状态**：HTTP 200 ＋ 空结果，不是错误
* 未捕获异常：HTTP 500 ＋ code `9999`，堆栈只进日志

### 2.4 错误码

见 `errors.py` 的 `CODES`。其中 **`1004`（HTTP 429，请求频率超出限制）是第 9 阶段新增**
（表 4-13 与《10》第 4.7.1 节均无此码），**须在《25》登记为新增**。

### 2.5 中间件里不能靠异常处理器

中间件在 `ExceptionMiddleware` **之外**，在里面抛 `ApiError` 不会被
`@app.exception_handler` 接住。中间件里出错误一律用
`errors.error_response(...)` **直接返回 `JSONResponse`**。

### 2.6 术语

FAISS 一律写「**向量索引**」；表数量恒为六张；不改上游字段名。

## 3. 常用命令

> Windows 的 Git Bash 会把反斜杠当转义，**路径必须加引号**，否则 `代码\后端\config.py`
> 会被解析成 `代码后端config.py`。

```bash
# 依赖自检
python -c "import fastapi,uvicorn,pymysql,neo4j;print('deps ok')"

# 参数自检（打印路径、上游定值、门禁参数；口令只报「已配置／未配置」）
python "代码\后端\config.py"

# 数据库访问层自检（凭据未填时以「配置问题」退出码 3 报出，原因明确）
python "代码\后端\db.py"

# 错误码自检（逐码打印 HTTP 状态与响应体键集合）
python "代码\后端\errors.py"

# 导入：先只解析（不连库）→ 小样本 → 全量
python "代码\后端\tools\import_data.py" --dry-run
python "代码\后端\tools\import_data.py" --limit 100 --dry-run
python "代码\后端\tools\import_data.py" --limit 100
python "代码\后端\tools\import_data.py"              # 全量 upsert（幂等）
python "代码\后端\tools\import_data.py" --reset      # 清空五表后全量重导

# 实时数据区取数服务自检（真连三个源各一次 ＋ 降级路径 ＋ 缓存）
python "代码\后端\services\market_service.py" --selftest

# 起服务（后台）→ 探活 → 停服务
python "代码\后端\run.py" &
curl -s http://127.0.0.1:8000/api/health
curl -s "http://127.0.0.1:8000/api/market/quote?codes=000001,600519"
curl -s "http://127.0.0.1:8000/api/market/announcements?code=000001&days=7"
curl -s "http://127.0.0.1:8000/api/market/news?keyword=%E5%B9%B3%E5%AE%89%E9%93%B6%E8%A1%8C"
curl -s "http://127.0.0.1:8000/api/market/reports?days=7"
taskkill //F //PID <pid>

# 跨文档核验
python "工具\跨文档核验.py"
```

## 3.1 图谱服务化（第 9 阶段 T3）

图谱侧有两个**可切换**的后端，**语义相同**（同一套 G1～G7、同一套返回码与排序键）。

| 后端名 | 实现 | 默认 |
| --- | --- | --- |
| `neo4j` | `services\graph_service.py` 的 `Neo4jGraphQuery`：G1～G7 逐条写成 Cypher，跑在本机真实 Neo4j 上 | ✅ 默认 |
| `memory` | 直接包装第 7 阶段 `代码\检索\graph_query.py` 的 `GraphQuery`（内存图），**该文件一个字节都没改** | 备用 |

切换方式（优先级从高到低）：命令行 `--backend neo4j|memory` → 环境变量
`GRAPH_BACKEND` → 后端 `config.py` 的同名开关（若日后加上）→ 缺省 `neo4j`。

**本机 Neo4j 的如实说明**：Neo4j 以**容器方式运行在 WSL2（Ubuntu 发行版）内**，
镜像 `neo4j:5-community`、容器名 `ashare-neo4j`，端口映射 `7474／7687` →
Windows 侧 `bolt://127.0.0.1:7687`。**未安装 Docker Desktop、未注册 Windows 服务**：
WSL2 的 `docker.service` 随发行版启动拉起容器。这是**本地单实例**，既不是集群、
也不是高可用、更不是生产部署。若 7687 不通，先唤醒：

```bash
wsl -d Ubuntu -u root -- docker start ashare-neo4j
```

```bash
# 图谱导入：先只解析（不连库）→ 清库全量导入 → 幂等复跑
python "代码\后端\tools\import_graph.py" --dry-run       # 只读 CSV 与 graph_stats，两方对拍
python "代码\后端\tools\import_graph.py" --reset         # MATCH (n) DETACH DELETE n 后全量导入
python "代码\后端\tools\import_graph.py"                 # 幂等复跑（MERGE），计数不变
python "代码\后端\tools\import_graph.py" --verify-only   # 只对拍库内计数，不写库

# 图谱查询服务的两个入口
python "代码\后端\services\graph_service.py" --selftest        # 七个接口与边界各跑通一次（默认 neo4j 后端）
python "代码\后端\services\graph_service.py" --backend memory --selftest
python "代码\后端\services\graph_service.py" --parity-check    # 两个后端逐项对拍（验收 E5）
python "代码\后端\services\graph_service.py" --cypher-table    # G1～G7 的等效 Cypher 与 Neo4j 端实际执行的 Cypher
GRAPH_BACKEND=memory python "代码\后端\services\graph_service.py" --selftest   # 用环境变量切后端
```

### 计数对拍（硬约束 16：不一致即失败）

`import_graph.py` 结束时打印**三方对拍表**（CSV／Neo4j／`graph_stats.json`）：
总节点 **2802**、总关系 **2736**、**逐标签**（7 类）与**逐关系**（9 类）逐项比对，
**任何一项不一致即非零退出**，并把 `阶段09-前后端系统集成\集成产出\graph_counts.json`
落盘（`--dry-run` 不写）。第 9 条关系 `SUPPLIES` 本批 0 条——上游即为 0，是数据事实。

**一处必须如实登记的事**（不是「调整统计口径」，基准仍是 2802／2736）：`edges.csv` 里
有 **5 组共 10 行**「端点＋关系类型＋证据三项」相同、但 `role` 不同的平行边
（全部是 `PARTICIPATES_IN`，如 `主体`／`涉及方`）。若严格只用题述的证据三项作 `MERGE`
匹配键，这 10 行会被并成 5 条，库内关系数将变成 **2731 ≠ 2736**。因此匹配键取
「端点＋类型＋证据三项＋**role**」——实测「9 列（含 role）全同」的重复组为 **0**，
该键在整份 `edges.csv` 上唯一，既完整保留 2736 条、又满足幂等。导入前脚本会**断言**
该键唯一，不唯一即报错退出；`graph_counts.json` 的 `merge_key_note`／`dup_key_audit`
两个字段留了这份审计的原始读数。

### `--parity-check`（验收 E5）

对**同一组确定的查询**分别跑两个后端，逐项比对**关键字段**：整个结果载荷、
**排序键序列**、**节点集合**、**关系集合（`edge_id`）**、**chunk_id 集合**，
以及 envelope 里其余全部字段（`node_ids`／`one_hop_count`／`document_refs`／`graph_path`／
G6 的九组集合…）。当前覆盖 **17 组**：3 家公司的 G1 与 G2（各 3 组）、3 个事件类型的 G3、
2 家公司的 G4、3 个事件的 G5、2 组 G7 路径、1 组 G6 时间过滤。**任一项不一致即非零退出**
并打印不一致字段的两端取值。

### 两个后端的一致性边界（如实登记）

* **已做到**：全部 17 组查询在关键字段上逐项一致，且在**整个结果载荷**上深度相等
  （不只是结构一致）。
* **口径差异的来处**（本批数据上均**实测无影响**，登记为边界）：
  * 归一化（剔除空白＋转小写）：Cypher 侧用 `reduce`＋`replace` 删掉 Python
    `str.split()` 认的全部空白字符再 `toLower`；二者在 ASCII 与中日韩字符上等价，
    但在 `İ`／`ß` 这类字符上 Python `str.lower()` 与 Java `toLower()` 会分叉
    ——本批 `name`／`short_name`／`aliases` 不含此类字符。
  * 字符串排序：Python 按码位，Neo4j 按 UTF-16 代码单元——本批数据全在 BMP 内。
  * `_s()`（Python `strip()`）在 Cypher 侧用 `trim()` 近似——本批 CSV **没有任何列
    存在两端空白**（导入前已实测）。
* **往返次数**：Neo4j 后端在 G6 上**逐事件**取 `chunk_id`（与第 7 阶段内存后端同样的
  N 次调用）。这是「行为一致优先」，登记为已知限制。
* **不开的开关**：本阶段不交付编排文件（无 compose／K8s），不引入容器编排（硬约束 18）。

## 3.2 实时数据区（作者新增意见：实时数据再完善一些）

> **口径（先读这一条）**：问答答案锚定**冻结语料**（数据集 v2.1，**数据截止 2026-09-25**）。
> 实时区取到的数据**只作页面展示，绝不进入检索／问答证据链**——不参与向量检索、不进图谱
> 扩展、不进最终证据集合、不写任何表；每个响应体都带 **`"scope": "display_only"`**。
> 页面上「实时区」与「问答答案（截至语料截止日）」**必须分开显示**。

### 四个接口（`api\market.py`，全部只读）

| 方法 | 路径 | 参数 | 错误码 | 取数源 |
| --- | --- | --- | --- | --- |
| GET | `/api/market/quote` | `codes`（逗号分隔，缺省取 `config` 默认股列表） | 1002 | 外部①实时行情 |
| GET | `/api/market/announcements` | `code`（必填）、`days`（1～30，默认 7）、`page_size`（1～50，默认 20） | 1002／1003 | 外部②个股公告 |
| GET | `/api/market/news` | `keyword`（必填）、`page_size` | 1002／1003 | 外部③个股新闻 |
| GET | `/api/market/reports` | `days`（1～30，默认 7）、`page_size` | 1002 | **语料内④查 `document` 表** |

### 三个外部源 ＋ 一个语料内源（URL 模板、超时、TTL、`secids` 前缀规则**全在 `config.MARKET_ZONE`**）

| 源 | 主机（公开接口，无需 key） | 关键点 |
| --- | --- | --- |
| ① 实时行情 | `push2.eastmoney.com/api/qt/ulist.np/get` | `secids` 前缀：**沪市 `1.`、深市 `0.`**；取 `data.diff[]` 的 `f12/f14/f2/f3/f4/f6` |
| ② 个股公告 | `np-anotice-stock.eastmoney.com/api/security/ann` | 取 `data.list[]` 的 `title/notice_date/art_code`；详情页模板见 `notice_detail_url` |
| ③ 个股新闻 | `search-api-web.eastmoney.com/search/jsonp` | 返回是 **JSONP**（剥 `cb(...)` 外壳）；标题含 `<em>` 需清掉；**必须带 `Referer: https://so.eastmoney.com/`** |
| ④ 语料内近一周 | **查库 `document` 表** | **不依赖外部源**；窗口＝「语料截止日往前 N 天」到截止日（`publish_time`），响应附 `corpus_cutoff` 与 `note` |

### 缓存

进程内 `dict` ＋ TTL（默认 **60 s**，取 `config.MARKET_ZONE["cache_ttl_seconds"]`），
键为「接口名 ＋ 参数」；命中时响应标 `cached: true`，且 **`updated_at` 保持不变**
（`updated_at` 是「该次取数的时间」）。缓存是**进程内**的：多进程／多实例不共享（已知限制）。
**失败结果不入缓存**，源恢复后下一次请求即可拿到数据。

### 降级行为（**界面上不许编造数据**）

任何外部源失败（超时／非 200／解析失败／网络不通）都**不向接口层抛异常**，而是返回
`connected: false` ＋ 一句简短 `reason` ＋ `items: []`；`reason` 只给「类别 ＋ 异常名」
（完整信息含 URL 只进后端日志，**不含口令、不含内网地址**）。

**「未接入」不是错误**：`connected: false` 仍走 `errors.ok(...)` 信封、**HTTP 200**——
与错误码 **2002**（查询结果为空是**正常业务状态**）同一语义，不用 4xx／5xx 表达。
页面据 `connected` 如实显示「未接入」，**绝不显示假价格、假涨跌幅、假新闻**。
外部源全部不可用时，④「语料内近一周」仍可用——这是**不依赖外部源**的降级形态。

### 新增登记

四条 `/api/market/*` 接口**不在表 4-13 的 27 个之内**（作者新增意见下的新增接口），
连同 `/api/health` 一并**须在《25》登记为新增**。

### 与「答案口径」的边界（如实登记）

* 实时区是**展示层**数据，**不参与**任何问答判定；问答的「数据截至」始终是
  `data_cutoff_time`（**2026-09-25**），与实时区的时间戳是两套口径，页面分开显示。
* ④ 的「近一周」是**语料内**发布时间的近一周（如 2026-09-18～2026-09-25），
  与 ② 的「实时公告近一周」（以**当天**为基准）**不是同一时间基准**，两者不可混用比较。
* 外部源字段可能随上游调整而变；字段名一旦变化，本层按「解析失败」降级为「未接入」，
  **不会返回半真半假的数据**。

## 4. 已知限制（第一版）

1. **MySQL 连接不池化**：单进程内单例连接，`ping()` 掉线重连。单机演示够用。
2. **限流是单进程内计数**：多进程／多实例部署下不共享窗口计数。
3. **分块传输（无 `Content-Length`）不做中间件层预判**：此类请求的大小限制由下游读取兜住。
4. **`document.create_time` 取 `ingest_time`**：上游无该字段（表 4-6 要求 NOT NULL），
   以入库时间作为记录创建时间，理由见 `tools\import_data.py` 头部。
5. **凭据待填**：`config.local.json` 的 `mysql_password` 由作者填入；未填时真写库必然
   以明确的凭据错误退出，`--dry-run` 不受影响。
6. **实时区外部源有频率限制、且字段可能变**：三个东方财富源均为公开接口、**无 SLA**。
   实测在短时间内连续探测后，行情源会**临时拒绝**本机请求（同一时刻 `curl` 与 Python
   都收不到响应），隔一段时间自行恢复。故本层默认 60 s 缓存、失败不写缓存，并把此类
   情况如实降级为「未接入」；**不重试、不绕过、不编造**。字段名如随上游调整，按解析
   失败降级（见 §3.2）。
7. **实时区数据不进证据链**：它只服务页面展示；问答判定用的一律是冻结语料
   （`data_cutoff_time`），两者页面分开显示（见 §3.2）。
