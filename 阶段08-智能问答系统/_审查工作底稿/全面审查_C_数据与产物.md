# 第 8 阶段（智能问答系统） 全面审查 · C 线（数据与产物）复核报告

- 复核线：**C（数据与产物）**
- 复核对象：`阶段08-智能问答系统\问答产出\`（`answer_trace.jsonl`／`qa_records.jsonl`／`prompt_snapshot.json`／`input_manifest.json`／`selection_matrix.jsonl`／`selection_decision.json`／`run_manifest.json`）与 `工具\验收第8阶段.py`
- 复核纪律：**只读**（未修改任何被审查对象；破坏试验只在系统临时目录的镜像副本上做，做完即删）；**不调用任何大模型接口**；每条发现均附复算命令与实测输出；凡「一致／0 处不一致」结论均先造必然不一致样本做**正对照**。
- 证据落盘：`阶段08-智能问答系统\_审查工作底稿\C_数据与产物\`（`01…08` 脚本与 `.out.txt` 原始输出）
- 日期：2026-09-29

---

## 一、复核方法与范围

复算全部用 Python 3.12 脚本完成（控制台 GBK，脚本内 `sys.stdout.reconfigure(encoding="utf-8")`；文件读写显式 `encoding="utf-8"`；JSON/JSONL 一律交 Python 解析，不用 PowerShell）。被审查对象仅被读取。

| 项 | 脚本 | 复算什么 | 正对照（自证比对器有效） |
| --- | --- | --- | --- |
| 1 输入指纹 | `01_输入指纹对拍.py` | 《21》第三节 8 项 10 个文件的 SHA-256／字节数，与 `问答产出\input_manifest.json`（P8）、`检索产出\input_manifest.json`（P7）三方对拍 | 植入 `bytes+1`、植入 SHA 篡改 → 均报「不符」PASS |
| 2 装配层重算 | `02_装配层重算.py` | 用 `代码\问答\assemble.py` 独立重算 30 题：证据顺序 vs `final_evidence_chunk_ids` 逐位；`total_tokens ≤ 3600`；`text_tokens == Σtoken_count`；两次装配 Prompt SHA 相同；与 trace 登记 `prompt_sha256` 比对 | 颠倒 PE-01 证据顺序 → `order_matches_trace=False` PASS |
| 3 答案门禁重算 | `03_答案产出重算判据.py` | **不读产出 `gates`**，从 `body_text`／`answer_text` 经 `rules.py` 重算 19 项判据（引用越界／日期可核／未来日期／禁词／图谱三方／标记泄漏／小标题），再与登记 `gates` 逐题逐字段比对 | 植入 `[证据99]`（m=10）→ `citation_out_of_range=[99]` PASS |
| 4 记录层对拍 | `04_记录层对拍.py` | `qa_records` 30 ↔ `answer_trace` 30 一一对应；三表字段名 vs《10》表 4-6 逐字；`(answer_id,chunk_id)` 唯一、`rank` 1..m 连续；`evidence_type` 四类 + **写死的** category 映射；`graph_path` 原样 JSON 文本 | 植入表外 `evidence_type="其它来源"` → 越四类报出 PASS |
| 5 选型产物重算 | `05_选型产物重算.py` | 从 `selection_matrix.jsonl` 90 行重算 `selection_decision.json` 30 列；`model_requested` vs `model_returned`；三候选 Prompt 指纹 | 植入 `dates_beyond_cutoff_total+1` → 报「不一致」PASS |
| 6 run_manifest | `06_run_manifest核验.py` | 6 个 `artifacts_sha256` 现算；10 个 `input_fingerprints` 复算；`model_calls` 自洽；`assembly_determinism` 独立复现；`model_output_repeatability` 可核性；`config_snapshot` vs `config.py` | 篡改 answer_trace 登记 SHA 末位 → 报「不符」PASS |
| 7 阶段交叉对拍 | `07_阶段交叉对拍.py` | `prompt_snapshot.json` vs `prompt.py`（含 `template_sha256` 现算）；30 题 k/n/budget vs `检索\config.py`；`from_graph` 计数 vs 第 7 阶段 `k_selection.json` C 组 g=2 | 植入 `k=9` → 报「不一致」PASS |
| 8 破坏试验 | `08_破坏试验.py` | 在系统临时目录建镜像根，构造 5 个反例，逐个跑 `工具\验收第8阶段.py --root <镜像> --profile full --emit-json`，读实测 FAIL 集 | 两个原样副本 FAIL 集相同（基线可重现）PASS |

**范围外（未验证）**：`--selftest`／`--all`／`--run-manifest`／`model_selection.py` 等会触发模型调用的命令**一律未执行**（纪律要求）；`history.py --selftest` 的会话隔离（F3）等构造类检查未独立复算（见第五节）。

**《21》第三节 8 项输入的登记键与本线覆盖**：P8 登记 10 键、P7 登记 11 键（多 `build_meta`／`faiss_index`／`human_confirmation`／`replay_cypher`／`vector_map` 等第 7 阶段自有项，不含本阶段 8 项输入中的 stage7 两项与 questions），本线对**本阶段实际使用的 10 个文件**逐一现算——30/10 项列已在报告口径内，未见漏项。

---

## 二、发现汇总表

| 编号 | 位置 | 问题 | 严重度 | 结论 |
| --- | --- | --- | --- | --- |
| **C-01** | `qa_records.jsonl` 的 `question`／`history.py:45`／《21》硬约束 13 | 记录层 `question` 缺 `user_id` 字段，与《10》表 4-6（8 字段，含 `user_id` 可空外键 `fk_question_user`）不符 | **P1** | 成立。根因是《21》硬约束 13 自称「以表 4-6 为准」却漏列 `user_id`（自相矛盾），代码与门禁都跟了《21》的 7 字段 |
| **C-02** | `22-...md:258`（5.3 节） | 《22》称 `answer.graph_path` 元素键为 `depth/end/nodes/relations`，**漏列实际存在的 `start`** | **P2** | 成立。实测元素键 5 个含 `start` |
| **C-03** | `model_selection.py:500`／《22》第 7 节「中位时延」 | 「中位时延」登记值取的是**上中位** `sorted[n//2]`（n=30 偶数时应取中间两值平均），《22》未注明口径 | **P2** | 成立。登记值可由代码约定复现，但按常用中位数定义应为 3.938／15.431／40.046，与登记的 4.005／16.627／44.071 不同 |
| **C-04** | `selection_matrix.jsonl`／`model_selection.py:613` | 90 行矩阵**无逐行 `prompt_sha256`**，「只换模型」无法从矩阵原样独立证明，只能由 `decision.prompt_sha256_by_qid`（单份）+ 共享装配代码佐证 | **P2** | 成立（可验证性限制）。装配层重算的 Prompt 指纹与 `prompt_sha256_by_qid` 30/30 一致，故结论未被推翻 |
| **C-05** | `工具\验收第8阶段.py:104`／《21》第八节 F1 | **门禁盲区**：`evidence_type` 的**取值与 category 映射（硬约束 15）无任何验收行校验**（F1 只查字段名；E5 只查 chunk_id/doc_id 回链）。生成期即错的表外 `evidence_type` 可让整轮门禁**静默通过** | **P0** | 成立（真门禁假阴性）。破坏试验 case5 复现：改表外取值后除「SHA 变动」外无行命中 |
| **C-06** | `工具\验收第8阶段.py:404,874`／`assemble.py:34` | **行级假阴性**：C4「预算不突破」只校验**现场重算**值（源＝第 7 阶段 `per_question_trace.jsonl`），不校验 `answer_trace` 的登记值。改某题登记 `total_tokens=3601` 时 C4 报 OK（仅 G4 命中） | **P1** | 成立。按题面「期望行仍报 OK 即假阴性」计入；但整体 `exit=1`（G4 捕获），**非静默通过**，且正常生成路径不可能产出该值，故不升 P0 |

**无发现项**：输入指纹三方对拍（项 1）、装配层重算（项 2）、答案门禁重算（项 3）、run_manifest 声明核验（项 6）、阶段交叉对拍（项 7）**逐条一致，0 处不一致**。记录层除 C-01／C-02 外**逐条一致**（项 4）；选型产物除 C-03／C-04 外**逐列一致**（项 5）。

---

## 三、逐条明细

### 项 1 · 输入只读与指纹三方对拍 —— 一致（0 处）

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\01_输入指纹对拍.py`
实测（`01_输入指纹对拍.out.txt`）：10 个文件全部 `OK`，逐项「不一致数 = 0」。

| 文件（键） | 字节 | SHA-256（实算） | P8 | P7 |
| --- | --- | --- | --- | --- |
| per_question_trace | 256704 | `2b1c0da1…a29a72` | 一致 | — |
| stage7_input_manifest | 7878 | `59233ad0…53770e5` | 一致 | — |
| stage7_run_manifest | 11834 | `0e59c0df…be8241ec` | 一致 | — |
| documents | 4496547 | `c838c608…10f9eea` | 一致 | 一致 |
| chunks | 5322875 | `2202cbf8…49e8e44` | 一致 | 一致 |
| dataset_meta | 3108 | `41c82bc4…63f5fc988` | 一致 | 一致 |
| nodes_csv | 708043 | `04f2ac22…6c8cb524` | 一致 | 一致 |
| edges_csv | 131275 | `e86f86d9…252b3f0` | 一致 | 一致 |
| graph_stats | 24818 | `443f437a…5ac2b4a` | 一致 | 一致 |
| questions | 101879 | `12e579c0…82b477e6` | 一致 | — |

正对照：`bytes+1` → 报「不符」PASS；SHA 篡改 → 报「不符」PASS。

### 项 2 · 装配层重算 —— 一致（0 处）

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\02_装配层重算.py`
实测（`02_装配层重算.out.txt`）：

- **`total_tokens` 范围 = 2978 ～ 3599**（预算 3600，逐题 ≤ 3600，超预算 0 题）；
- `text_tokens == Σtoken_count` 不符 0 题（且 `token_count` 与 `chunks.jsonl` 字段值一致，未重算）；
- 证据顺序与 `final_evidence_chunk_ids` 逐位一致，不符 0 题；
- 同一输入两次装配 Prompt SHA-256 逐题相同，不符 0 题；
- 与 `answer_trace` 登记 `prompt_sha256` 比对，不符 0 题；
- **`from_graph` 块合计 = 53**；证据条数分布 = `{8:1, 9:5, 10:24}`。

正对照：颠倒 PE-01 顺序 → `order_matches_trace=False` PASS。

### 项 3 · 答案产出重算判据 —— 一致（0 处）

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\03_答案产出重算判据.py`
实测（`03_答案产出重算判据.out.txt`）：**逐字段不一致题数 = 0**（19 项判据，30/30 题），重算合计：

- 引用记法出现 **181** 次；**引用越界 = 0**；
- **`date_unverifiable` = 0**；**`dates_beyond_cutoff` = 14**（PE-01:2 / PE-11,12,13,14,20,28,30:各 1 / PE-29:5）；
- **禁词命中 = 0**；图谱段三方一致题数 30/30；正文图谱标记泄漏 0；正文小标题泄漏 0；
- 产出登记 `passed=True` = 30/30，与重算一致。

正对照：植入 `[证据99]`（m=10）→ `citation_out_of_range=[99]` PASS。

### 项 4 · 记录层对拍 —— 除 C-01／C-02 外一致

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\04_记录层对拍.py`
实测（`04_记录层对拍.out.txt`）：

| 对拍项 | 结果 |
| --- | --- |
| `qa_records` 30 ↔ `answer_trace` 30 一一对应 | 缺失 0、多余 0、`answer_text` 不符 0 |
| `answer` 字段名 vs 表 4-6 | 8/8 逐字一致（缺 0 多 0） |
| `answer_evidence` 字段名 vs 表 4-6 | 5/5 逐字一致 |
| `(answer_id, chunk_id)` 唯一 / `rank` 1..m 连续 / 归属 | 重复 0、不连续 0、归属不符 0 |
| `evidence_type` 四类 + 映射自洽（映射写死） | 映射不符/表外 **0** 条；计数 = `{公告来源:234, 相关事件:53, 新闻来源:6}`；全语料 category = `{公告:556, 财经新闻:103, 政策文件:30, 监管公开信息:20}` |
| `graph_path` 原样 JSON 文本 / 可 `json.loads` / `graph_used=0` 为 null | `graph_used=1` 30 题（可 loads 30）；`graph_used=0` 0 题 |
| **`question` 字段名 vs 表 4-6** | **实际 7 个、表 4-6 为 8 个，缺 `user_id`** ← **C-01** |

- **C-01 证据**：`阶段04-系统总体设计\10-系统总体设计（第四阶段）.md` 4.4.1 节 表 4-6 的 `question` 行为
  `| question | user_id | BIGINT | 是 | 外键 fk_question_user → user.user_id（置空） | 提问用户；登录未启用时为空 |`，且表前明写「**字段名与字段职责以《02》第9.1节 为准**，本表不新增字段」；`代码\问答\history.py:45` 的 `QUESTION_FIELDS` 仅 7 个（无 `user_id`）；《21》硬约束 13 逐字列表亦为 7 个，却在同句声明「**以《10》第4.4.1节 表 4-6 为准**……不新增字段、不改字段名」。三者中表 4-6 为准绳，实现与门禁均按其上一层的 7 字段执行，故**漏字段成立而实现自洽**。
- **C-02 证据**：实测首条非空 `graph_path` 元素 0 键 = `['depth','end','nodes','relations','start']`（5 个），`relations[0]` 键 = `['direction','evidence','neighbor','relation','role']`，`relations[0].evidence` 键 = `['confidence','source_chunk_id','source_doc_id']`；而《22》`22-...md:258` 仅列「键为 `depth`／`end`／`nodes`／`relations`」，**漏 `start`**。

### 项 5 · 选型产物重算 —— 除 C-03／C-04 外逐列一致

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\05_选型产物重算.py`
实测（`05_选型产物重算.out.txt`）：每候选 30 行（合计 90）；30 列中仅 `median_seconds` 一项 3 处不符，其余全部一致。

| 候选 | 重算中位（`statistics.median`） | 登记中位（`sorted[n//2]`） |
| --- | --- | --- |
| deepseek-flash | 3.938 | **4.005** |
| deepseek-v4-pro | 15.431 | **16.627** |
| glm-5.3-flash | 40.046 | **44.071** |

- **C-03 证据**：`代码\问答\model_selection.py:500`
  `"median_seconds": (round(seconds_sorted[len(seconds_sorted) // 2], 3) if seconds_sorted else None),`
  —— 对 n=30 取 `sorted[15]`（上中位）。登记值与该约定完全吻合，故非「读数与产物不符」；但《22》第 7 节以「**中位时延（秒）**」列示而未注明口径。
- 其余列一致：`mean_seconds` 6.165 / 24.499 / 55.134；`max_seconds`；各 rate 全 0；`dates_beyond_cutoff_total` 17/12/16；`finish_reason` 分布；`total_calls=90`；`verdict='维持 deepseek-flash'`、`triggered_rules=[]`；`model_requested == model_returned`（90/90）。
- **C-04 证据**：`model_selection.py:613` 是全脚本唯一写 Prompt 指纹处（`"prompt_sha256_by_qid": {c["qid"]: c["prompt"]["sha256"] for c in cases}`），位于 **decision**；实测「矩阵行内是否含 `prompt_sha256` 字段 = False」。装配层重算 vs `decision.prompt_sha256_by_qid` 不一致 **0/30**，且 `only_thing_changed` 登记为「仅模型；装配结果、Prompt 文本、temperature、max_tokens 三候选全同」。

正对照：植入 `dates_beyond_cutoff_total+1` → 报「不一致」PASS。

### 项 6 · `run_manifest.json` 声明核验 —— 一致（0 处）

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\06_run_manifest核验.py`
实测（`06_run_manifest核验.out.txt`）：

| 声明 | 复算结果 |
| --- | --- |
| `artifacts_sha256`（6 项） | 现算 SHA／字节 6/6 一致（`answer_trace` `dbbd7dfc…c92480`、`qa_records` `e0d3cf03…a553bfb2`、`prompt_snapshot` `702a23c6…f8b0bd5d`、`input_manifest` `e9e155e8…2208a7a`、`selection_matrix` `118dfe69…c7e811e`、`selection_decision` `896d0ebf…148c0bf0`） |
| `input_fingerprints`（10 项） | 现算 10/10 一致；`recomputed_mismatched=[]` 属实；`count=10` 自洽 |
| `model_calls`（total=60／retries=0） | `total==cycle_1+cycle_2==60` 成立；`cycle_1==answer_trace 行数==30`；`retries==0` 且 trace 逐行 `attempts` 合计 30、`retried` 行数 0；**注意**：第 2 次运行的 30 次调用不落盘，无法从产物点数（已在报告第五节列为不可核项） |
| `assembly_determinism`（30/30，0 调用） | 现场连装两次 30/30 一致；与登记 `prompt_sha256_by_qid` 30/30 一致；`model_calls=0` 属实 |
| `model_output_repeatability`（0/30） | 内部自洽（`rate==identical/questions==0.0`，`differing∪identical==30`）；`differing_qids` 30、`identical_qids` 0 → **重复一致率本身不可独立复算**（第 2 次 `body_text` 未落盘） |
| `config_snapshot` | 12 项逐项与 `代码\问答\config.py`／`检索\config.py` 现取一致（`K=10/N=20/预算=3600/g=2`、`deepseek-flash`、`https://api.deepseek.com/v1`、`temperature=0`、`max_tokens=16384`、`prompt_version=v1.0`、`dataset_version=v2.1`、`data_cutoff_time=2026-09-25T23:59:59+08:00`） |

正对照：篡改 `answer_trace` 登记 SHA 末位 → 报「不符」PASS。

### 项 7 · 与第 5／6／7 阶段交叉对拍 —— 一致（0 处）

复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\07_阶段交叉对拍.py`
实测（`07_阶段交叉对拍.out.txt`）：

- `prompt_snapshot.json` 与 `prompt.py::snapshot()` **逐字节一致**；`template_text()` 现算
  `sha256 = c4c351d0dd38f4e96a96a6fb35816e959489d8077edf709995264c79e0cff3f0`，与《22》声称值一致；`prompt_version=v1.0`，`block_order` 七区块顺序正确。
- 30 题 `k/n/context_token_budget` 与 `检索\config.py` 冻结值（K=10／N=20／3600）不符 0；`evidence_size` 分布 `{10:24, 9:5, 8:1}`，`max=10 ≤ K`。
- **图谱侧块合计 = 53**，含图谱题数 = 29，与 `k_selection.json` **C 组 g=2** 的 `graph_evidence_in_final_total=53`／`graph_evidence_in_final_questions=29` 完全一致；逐题与第 7 阶段 `graph_evidence_in_final_count` 不符 0；逐题 `graph_payload` 与第 7 阶段不符 0；**PE-16 `from_graph=0`**（与《22》一致）；单题图谱块最大值 = 2（= g）。

正对照：植入 `k=9` → 报「不一致」PASS。

---

## 四、破坏试验结果表

镜像根建在**系统临时目录**（复用门禁脚本自带的最小文件清单 `MIRROR_FILES`，34 文件，含 git 初始化；不改工作区），每个反例跑一次
`python 工具\验收第8阶段.py --root <镜像根> --profile full --emit-json …`。
基线（原样副本）FAIL 集 = `{H1, H2, H3, G6}`、未执行 = `{G5}`（镜像不含《22》与 `工具\跨文档核验.py`，属如实现状）。
复算命令：`python 阶段08-智能问答系统\_审查工作底稿\C_数据与产物\08_破坏试验.py`（输出 `08_破坏试验.out.txt`）。

| 反例 | 构造（对镜像副本的改动） | 期望新增 FAIL 行 | 实测新增 FAIL 行 | 判定 |
| --- | --- | --- | --- | --- |
| case1 | PE-02 正文 `[证据1]`→`[证据99]`（越界） | D2、E4、G4 | **D2、E4、G4** | 被捕获 ✓ |
| case2 | PE-01 的 `evidence` 数组顺序反转 | C3、G4 | **C3、G4** | 被捕获 ✓ |
| case3 | PE-03 图谱段→`本次回答未使用图谱扩展`（`graph_used` 仍真） | D4、E2、G4 | **D4、E2、G4** | 被捕获 ✓ |
| case4 | PE-04 `token_account.total_tokens`→3601 | C4、G4 | **G4**（**C4 = OK**） | C4 **未命中**（C-06，行级假阴性）；整体仍捕获 |
| case5 | 第 1 条 `answer_evidence[0].evidence_type`→`其它来源` | （无行覆盖）G4 | **G4**（无字段值校验行） | **门禁盲区**（C-05，P0）；生成期即错可**静默通过** |

关键行状态（`08_破坏试验.out.txt`「关键行状态明细」）：

- case4：`C4 = OK`、`G4 = FAIL` —— C4 重算的预算来自第 7 阶段 trace（`assemble.load_trace()` → `config.TRACE_PATH`），登记值改动不影响重算，故 C4 不敏感。
- case5：除 `G4 = FAIL` 外无其它行命中；F1 仅比字段**名**，E5 仅比 `chunk_id/doc_id` 回链。
- 正对照：两个原样副本 FAIL 集相同（`{H1,H2,H3,G6}`），基线可重现 PASS。

**说明（C-05 为何是 P0）**：case5 中 `G4` 之所以失败，仅因我在**产物已生成后**改写文件、与 `run_manifest` 登记的 SHA 不再匹配。若生成期即产出表外 `evidence_type` 并同步登记其 SHA，则 F1／F2／E5／G4 全过，**整轮门禁 39 行会静默通过**——《21》硬约束 15（`evidence_type` 取四类之一 + category 映射写死）在验收行里**没有任何落点**。这是一处真实的门禁假阴性，而非仅「期望行错配」。

---

## 五、无法判定与未验证事项

1. **`model_output_repeatability` 的 0/30 不可独立复算**：`_repeat_rate` 依赖第 1／2 次运行的 `body_text`，但第 2 次运行**不落盘**，产物中只剩 `{questions, identical, rate, identical_qids, differing_qids}`。本线只能核其**内部自洽**（`rate==identical/questions`，`differing∪identical==30`，`differing_qids` 覆盖全部 30 题），**无法**重跑模型比对（纪律禁止模型调用）。同时 G3 明确「只登记数值、不作判据」，故不影响收口。
2. **`model_calls` 的第 2 次运行 30 次调用无产物可点**：`{cycle_1=30, cycle_2=30, total=60, retries=0}` 中 `cycle_1` 可由 `answer_trace` 30 行 × `attempts` 印证，`cycle_2` 仅能自洽校验。
3. **选型「只换模型」不可从矩阵原样证明**（C-04）：矩阵行无 Prompt 指纹；只能由「单份 `prompt_sha256_by_qid` + 共享 `assemble.py` + `only_thing_changed` 声明」佐证，无法独立排除「三候选各自装配了不同 Prompt 但指纹未逐行留痕」这一理论可能。
4. **F3 会话隔离、F4 回看不重渲染、H1～H4 文档类检查未由本线独立复算**：属构造/文档层，超出「数据与产物」复算范围；`--selftest`／G5（`工具\跨文档核验.py`）等需子进程项在镜像里记为未执行，本线未在工作区运行（避免触发模型调用与写盘）。
5. **C-01 的「正确形态」需决策者裁定**：若以《10》表 4-6 为准，应补 `user_id`（可空）并同步改 `history.py:45`、`工具\验收第8阶段.py:104`、以及《21》硬约束 13；若以《21》硬约束 13 为准，则应改《10》表 4-6 或《21》的引述。**本线只指出冲突，不代为选择口径。**

---

## 附：复核产出清单

`阶段08-智能问答系统\_审查工作底稿\C_数据与产物\`

| 文件 | 内容 |
| --- | --- |
| `01_输入指纹对拍.py` / `.out.txt` | 项 1 |
| `02_装配层重算.py` / `.out.txt` | 项 2 |
| `03_答案产出重算判据.py` / `.out.txt` | 项 3 |
| `04_记录层对拍.py` / `.out.txt` | 项 4 |
| `05_选型产物重算.py` / `.out.txt` | 项 5 |
| `06_run_manifest核验.py` / `.out.txt` | 项 6 |
| `07_阶段交叉对拍.py` / `.out.txt` | 项 7 |
| `08_破坏试验.py` / `.out.txt` | 项 8（镜像临时目录已删） |
