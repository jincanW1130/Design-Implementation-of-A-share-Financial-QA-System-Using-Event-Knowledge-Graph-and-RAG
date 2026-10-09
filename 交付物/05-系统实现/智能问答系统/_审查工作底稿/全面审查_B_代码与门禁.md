# 全面审查 · 复核线 B（代码与门禁）

- 复核对象：第 8 阶段（智能问答系统）前八阶段的**代码与门禁**部分
- 复核范围：`交付物/03-代码\问答\` 十个文件、`工具\验收第8阶段.py`、本轮 `工具\跨文档核验.py` 的改动、以及 `交付物/05-系统实现/智能问答系统\问答产出\` 的判据字段是否真由代码产出
- 判据来源：`交付物/05-系统实现/智能问答系统\21-第8阶段任务书（智能问答系统）.md`（v1.5）§五 22 条硬约束、§六 8 条格式决策、§八 39 行验收标准
- 工作底稿：`交付物/05-系统实现/智能问答系统\_审查工作底稿\B_代码与门禁\`
- 复核日期：2026-09-29

---

## 一、复核方法与范围

### 1.1 只读证据（本线的写动作清单）

本线**只读**被审查对象，未修改 `交付物/03-代码\`／`工具\`／`00-`／`02-`／`阶段0N-…` 任何文件。
按纪律只写两处：

| 写入位置 | 内容 |
| --- | --- |
| `交付物/05-系统实现/智能问答系统\_审查工作底稿\B_代码与门禁\` | `B_篡改测试.py`、`B_篡改测试_output.txt`、`篡改运行日志\_log_*.txt`（11 份）、`run_验收8_full.log`、`run_跨文档核验_strict.log` |
| `交付物/05-系统实现/智能问答系统\_审查工作底稿\全面审查_B_代码与门禁.md` | 本报告 |

所有篡改试验均发生在 `tempfile.mkdtemp()` 建的**系统临时目录镜像**里，试验后删除。实测：脚本内的 `shutil.rmtree(ignore_errors=True)` 在 Windows 下**未能删净**（镜像被初始化成 git 仓库，`.git/objects` 只读），已用带 `os.chmod` 的 `rmtree(onerror=…)` 二次清理，并由 `ls -d /tmp/B_mirror_*` 复核**已无残留**（`现存 B_mirror 目录: 无`）。

### 1.2 零模型调用证据

- 本线**未调用任何大模型接口**：未发请求、未用密钥、未跑 `--all`／`--run-manifest`／`model_selection.py`（其 `run()` 在 `STAGE8_FORBID_MODEL_CALLS=1` 下直接拒绝）。
- 允许并已执行的命令只有零调用档：`--profile full`（收口判定）、`--profile static`、`--dry-run`、`--selftest`、`工具\跨文档核验.py --strict-citations`。
- 门禁 `full` 档零调用的**代码路径证据**（不采信其自述）：`工具\验收第8阶段.py` 全程只起两个子进程 ——
  - `G1`：`交付物/03-代码\问答\run_answer.py --dry-run --out-dir <tmp>`，且按 `CRED_PAT`（`工具\验收第8阶段.py:133,1396`）**剔除凭据类环境变量**、置 `STAGE8_FORBID_MODEL_CALLS=1`；该行自核「退出码 0、自报调用次数 0、临时产物 0 个」；
  - `G5`：`工具\跨文档核验.py --strict-citations`（纯 Markdown 静态核验，无网络）。
  实测 G1 输出：`[OK] G1 零调用跑通（--dry-run，退出码 0、调用计数 0）`。
- `answer.py:118` 在 `call_model()` 发请求**之前**先 `config.assert_model_calls_allowed("answer.call_model")`，即令误触也在发请求前抛错。

### 1.3 两条允许命令的实测退出码

| 命令 | 退出码 | 输出摘要 |
| --- | --- | --- |
| `python 工具\验收第8阶段.py` | **0** | `最终：计划行 39 行；已执行 39／39、通过 39、失败 0、未执行 0、SKIP 0`；`结论：39 行全部通过…第 8 阶段专项验收通过，退出码 0。`（A 4/4、B 4/4、C 6/6、D 6/6、E 5/5、F 4/4、G 6/6、H 4/4） |
| `python 工具\跨文档核验.py --strict-citations` | **0** | 末行 `[OK ] O5 正文每条引用出现次数与指纹一致 0 条不一致`；`结论：全部通过` |

日志：`B_代码与门禁\run_验收8_full.log`、`B_代码与门禁\run_跨文档核验_strict.log`。

> 注：本线新建的 `_审查工作底稿\` 目录使 `git status --porcelain` 多出 1 条未跟踪项（`.gitignore` 只忽略 `_工作底稿\`，未忽略 `_审查工作底稿\`）。该条目不在 `交付物/03-代码\检索\`／`检索产出\`／`阶段09-` 范围内，故 **A3、H4 判定不受影响**（实测二者均 `[OK]`，全档退出码 0）。

### 1.4 复核方法

1. **判据单源核验**：`rules.py` 的日期／禁词／引用判据是否唯一实现（`model_selection.py`／`answer.py`／门禁有无第二实现）。
2. **硬约束逐条落地核对**：22 条对代码，给 `文件:行号`，分「真实现／注释承诺／未实现」。
3. **缺陷级代码审查**：静默兜底、错误路径不退出、编码、路径、导入副作用、死代码、注释与实现矛盾。
4. **门禁假阴性测试（重点）**：自建镜像 ＋ 8 个反例 ＋ 2 个「聪明篡改」变体，逐例打印「期望 FAIL ／ 实测」。
5. **门禁假阳性风险评估**：绝对路径、`git status` 格式、`--root` 重定位边界、执行顺序。
6. **第 8 阶段是否动过第 7 阶段**：`git log`／`git show --stat` 核对 `82f48f7`、`dc88c53`。
7. **判据字段是否真由代码产出**：`evidence_type`／`total_tokens`／`is_graph_extended`／`gates`／`prompt_sha256` 逐个追到产出源码行。

---

## 二、发现汇总表

| 编号 | 严重度 | 位置 | 一句话结论 |
| --- | --- | --- | --- |
| **B-01** | **P0** | `工具\验收第8阶段.py:683-729`（B2） | B2 只比 `config.RETRIEVAL` 与期望值，**不核对 `config.K/N/CONTEXT_TOKEN_BUDGET/G` 与检索侧一致**，且 AST 字面量扫描 `continue` 跳过 `config.py`；在 `交付物/03-代码\问答\config.py` 写死 `K = 8` 后 B2 仍判 `[OK]`（输出自证矛盾）——B2 对其自身声明「参数无第二份字面量」存在**假阴性**。 |
| **B-02** | **P0** | 门禁 C4 用重算值、产物无校验（`工具\验收第8阶段.py:878-886`） | 产物 `answer_trace.jsonl` 的 `token_account.total_tokens` **无任何语义校验**；把某题改成 3601 仅由 G4 的 SHA 捕获，**同步改写 `run_manifest.artifacts_sha256` 后新增失败为空**（真实工作区将 39/39 通过）。 |
| **B-03** | **P0** | 门禁 `ROW13_FIELDS`（`工具\验收第8阶段.py:104`）只列字段名 | 产物 `qa_records.jsonl` 的 `evidence_type` **只校字段名、不校取值**；改成表外取值后仅由 G4 的 SHA 捕获，同步改写 SHA 后逃逸。硬约束 15「四类取值」在门禁侧无取值校验。 |
| **B-04** | **P0** | `工具\验收第8阶段.py:611,619-620` | `max_tokens` 从《21》解析进 `frozen` 后**从未参与任何比较**（`bad3` 只含 model_name/model_version/temperature，加 endpoint）；硬约束 2 的冻结值 16384 在**全档 39 行中无一处校验**。**实测**：改成 8192 后新增失败为空、B1 仍 `[OK]`。 |
| **B-05** | P2 | `工具\验收第8阶段.py:1074` | `cutoff = cutoff or (r.get("token_account") and None) or …`：`… and None` 恒为 `None`，读起来像取产物 `token_account`，实际**从不取**，属死代码／与注释不符。 |
| **B-06** | P2 | `交付物/03-代码\问答\README.md:17`（及文件头版本号） | 文档写「Prompt 模板（**6 区块**）」，与实现及《21》要求的**七区块**（`prompt.py:126` `BLOCKS`）矛盾；README 头引 v1.3 而《21》为 v1.5。 |
| **B-07** | P2 | `交付物/05-系统实现/智能问答系统\问答产出\run_manifest.json` | `artifacts_sha256`／`input_fingerprints` 内嵌**机器绝对路径**（`C:\Users\15129\Desktop\毕业设计\…`）；仅靠 `resolve_under_root()`（`工具\验收第8阶段.py:214-235`）的后缀重定位兜住。本次实测重定位有效（非 P1），但属可移植性缺陷。 |
| **B-08** | P2 | `交付物/03-代码\问答\model_selection.py`（`machine_check`） | 日期／禁词／引用已单源到 `rules`，但 `machine_check` 仍**自留** graph/leak/empty 判定（与 `answer.gate` 同式、独立实现），存在口径分叉的**残余风险**（单列，见 §五）。 |
| **B-09** | P2 | `工具\验收第8阶段.py:selftest`（`base_fail={"H1","H2","H3","G6"}`） | 门禁自带正对照偏弱：`MIRROR_FILES` 故意不含《22》，使 H1/H2/H3/G6 在镜像里**只走 FAIL 路径**；内建三例均只改 `answer_trace.jsonl`，G4 的 SHA 承担了主要捕捉责任，反例多样性不足（本线 8 例已补足）。 |

**分级统计：P0 4 条（B-01、B-02、B-03、B-04）；P1 0 条；P2 5 条（B-05…B-09）。**
（分级口径按任务约定：「门禁假阴性」一律 P0。B-04 的影响面窄于 B-01／B-02／B-03，但同属该口径。）

---

## 三、逐条明细

### 3.0 检查 #6：第 8 阶段有没有动过第 7 阶段 —— **未动**（通过）

复现：`git show --stat 82f48f7`、`git show --stat dc88c53`。

- `82f48f7` 触及：`.gitignore`、`00-`、`02-`、`交付物/03-代码/README.md`、`交付物/03-代码/问答/*`（10 个）、`工具/README.md`、`工具/跨文档核验.py`、`工具/验收第8阶段.py`、`交付物/05-系统实现/智能问答系统/21-·22-·问答产出/**`。
- `dc88c53` 仅触及 `00-`（2 行）。
- **两个提交都未触及** `交付物/03-代码\检索\`、`交付物/05-系统实现/RAG检索系统\检索产出\`，也未触及第 05／06 阶段只读输入。
- `工具\跨文档核验.py` 的改动**限于**：`PLANNED` 上方新增说明注释（`PLANNED = set()` 本体为上下文行、未改）、`WANT_STAGES` 增加 `'交付物/05-系统实现/智能问答系统'`。与任务书要求一致。

### 3.1 检查 #5：判据单一来源 —— **日期／禁词／引用已单源到 `rules.py`**（通过，残余见 B-08）

- `model_selection.py` 通过别名引用 `rules`（`CITATION_RE = rules.CITATION_RE`、`extract_dates = rules.extract_dates`、`allowed_dates`、`_cutoff_date = rules.cutoff_date`、`_cite_marks = rules.citation_marks`），并**删除了自带的重复实现**。
- `answer.py` 的 `gate()` 与 `工具\验收第8阶段.py` 的 E1/E2/E3/E4 均调用 `rules.date_gate`／`rules.forbidden_gate`／`rules.citation_gate` —— 门禁**不采信产物自检**，用同一套 `rules` 现场重算后比对。
- 残余：`model_selection.machine_check` 保留自研的图谱段／泄漏／空答案判定（B-08）。

### 3.2 检查 #7 补充：判据字段确由代码产出（通过）

| 字段 | 产出源码行 | 备注 |
| --- | --- | --- |
| `evidence_type` | `history.py:117` `"evidence_type": prompt_mod.source_type_label(item)` | 与 `prompt.SOURCE_TYPE_BY_CATEGORY` 同源（含 v1.4「财经新闻→新闻来源」修正） |
| `is_graph_extended` | `answer.py:244` / `history.py:100` `1 if graph_used else 0` | 记录层 0／1 口径 |
| `token_account` | `run_answer.py:153` `rec["budget_trim"]["after"]`（与 trace 同源、不重算） | 分账键：`text_tokens`／`graph_tokens`／`path_tokens`／`event_triple_tokens`／`total_tokens` |
| `gates` | `answer.py:405` `gate(case, …)` → `run_answer.py:243` 落 trace | 四类门禁结果字典 |
| `prompt_sha256` | `answer.py:374` / `run_manifest` `prompt_sha256_by_qid` | 由 `prompt.py` 渲染文本算出 |
| `artifacts_sha256` | `run_answer.py cmd_run_manifest:616` | 6 个产物 SHA-256 ＋ 字节数 |

即：产物里的判据字段**确由脚本产出**，非人工填写。

### 3.3 检查 #1：22 条硬约束落地核对

| # | 硬约束 | 落地 | 证据 |
| --- | --- | --- | --- |
| 1 | 参数全来自 `config.py`（四项定值导入、不复制字面量） | **真实现**（但门禁校验有假阴性 B-01） | `交付物/03-代码\问答\config.py:233-241`（`_RET = _load_retrieval_config()`；`_need()` 读 `RETRIEVAL`，读不到即 `SystemExit`，不兜底）、`:250-253`（`K/N/CONTEXT_TOKEN_BUDGET/G`） |
| 2 | model/version/temperature/endpoint/max_tokens 冻结 | 代码侧真实现；**门禁只核 3 值＋endpoint**（B-04） | `config.py:308-322` `FIXED`；门禁 `工具\验收第8阶段.py:628-631` |
| 3 | `PROMPT_VERSION="v1.0"` | **真实现** | `prompt.py:46`；`:359-360` 断言 `== config.require_fixed("prompt_version")` |
| 4 | 七区块固定顺序 | **真实现** | `prompt.py:126` `BLOCKS`（7 个 `_BLOCK_*`）；`:290` `build_messages`；门禁 C1 与《10》表 4-12 逐字比对 |
| 5 | 证据顺序不重排 | **真实现（报错退出）** | `assemble.py:186` `SystemExit("…证据顺序与 final_evidence_chunk_ids 不一致（生成侧不得重排）")` |
| 6 | 预算不突破→**报错退出**（非静默截断） | **真实现** | `assemble.py:189-191` `SystemExit("…total_tokens=%d 超过 Context Token Budget=%d")` |
| 7 | 图谱载荷原样透传；仅「回答」由模型产出 | **真实现** | `assemble.py:203` `"graph_payload_passthrough": graph_payload == trace_row["graph_payload"]`；`prompt.render_graph_block` 为空则整块省略；`compose_answer` 仅正文段用模型文本 |
| 8 | 未用图谱时的固定标注 | **真实现** | `prompt.py:56` `NO_GRAPH_MARKER = "本次回答未使用图谱扩展"` |
| 9 | `[证据n]`，1≤n≤\|E\| | **真实现** | `prompt.py:61` `CITATION_TEMPLATE="[证据n]"`；`rules.citation_gate`；门禁 D2（反例② 实测捕获） |
| 10 | 日期来源可核 | **真实现** | `rules.allowed_dates`／`rules.date_gate`；门禁 E1 现场重算 |
| 11 | 最新／最近／近期 按 `event_time` vs `data_cutoff_time` | **真实现** | `config.py:266` `RELATIVE_TIME_WINDOWS`（导入自检索侧）；`config.window_endpoint_dates():277`；门禁 D5 |
| 12 | 开放式分析标记并排除指标 | **真实现** | `answer.gate` 的 `open_ended_task_type`／`not_applicable` 分支；门禁 D6 |
| 13 | 记录层字段名对齐《10》表 4-6 | **真实现** | `history.py:45`（question）、`:48`（answer）、`:49`（answer_evidence）；门禁 F1 比对（`ROW13_FIELDS:104`） |
| 14 | `(answer_id, chunk_id)` 联合唯一 | **真实现（报错退出）** | `history.py:108-109` `SystemExit("…chunk_id=%r 重复（联合唯一约束）")`；门禁 F2 |
| 15 | `evidence_type` 四类（v1.4 财经新闻→新闻来源） | 代码侧真实现；**门禁无取值校验（B-03）** | `prompt.SOURCE_TYPE_BY_CATEGORY`；`history.py:117` 同源 |
| 16 | 会话隔离；回看不重渲染图谱路径 | **真实现** | `history.py:159-164` `query_history` 按 `session_id` 过滤；`review()` 只回 `found/question/answer/answer_evidence`；门禁 F3／F4 |
| 17 | 装配字节确定；模型输出不可确定 | **真实现** | `config.write_json/write_jsonl`（`sort_keys=True`、`newline="\n"`、tmp+`os.replace`）；门禁 C6／G2 |
| 18 | 调用计数；`STAGE8_FORBID_MODEL_CALLS=1` ⇒ 0 | **真实现** | `config.py:339,347` `assert_model_calls_allowed`；`answer.py:118` 发请求前先断言；门禁 B4／G1 |
| 19 | 密钥不硬编码、不回显 | **代码侧真实现；门禁无专项行** | `config.api_key:386`（从 `交付物/03-代码\抽取与图谱\config.local.json` 读，缺失即报错）；`answer._one_attempt` 的 `HTTPError/Exception` 分支不回显密钥。门禁侧仅 `CRED_PAT:133,1396` 用于 G1 **剔除凭据环境变量**，未见对源码硬编码密钥的扫描行 —— 记为覆盖观察，不单列缺陷 |
| 20 | 术语口径 | **注释承诺 + 部分门禁** | 门禁 `term_discipline` 非行级 note；未见逐术语硬判 |
| 21 | 不新增实验变量 | **真实现** | 第 8 阶段未引入检索侧变量；`_frozen_params` 拒绝非冻结 `--k/--n/--budget`（`run_answer.py`） |
| 22 | 只读输入 | **真实现** | 门禁 A1 指纹复核；本线 §3.0 git 范围核对 |

### 3.4 检查 #2：缺陷级代码审查（逐条）

- **B-01（P0）门禁 B2 假阴性。** 复现：`B_篡改测试.py` case7。实测 B2 输出原文：
  `[OK  ] B2 参数无第二份字面量（四项由 交付物/03-代码\检索\config.py 导入）  检索侧四项实测 K=10、N=20、budget=3600、g=2；config 导入 K=8／N=20／budget=3600／g=2；…`
  —— 一行之内同时打印「检索侧 K=10」与「config 导入 K=8」却判 `[OK]`。成因：`工具\验收第8阶段.py:668` `fixed_bad` 只比 `config.RETRIEVAL`（其值来自检索侧，恒为 10）与 `EXPECT_FIXED`；`:683-685` 的 AST 扫描 `if not name.endswith(".py") or name == "config.py": continue` **跳过 `config.py`**；`:669-675` 只判 `config.K` 等**非 None**、不与 `RETRIEVAL` 比对。故「第二份字面量」恰恰可藏在其声称要设防的 `config.py` 里。
- **B-02（P0）产物 `total_tokens` 无语义校验。** 复现：case4 与 smart4。实测 C4 仍 `[OK] …30 题 total_tokens 最大值=3599`（因 `:878` 的 `for qid in sorted(cases)` 用的是 `cases_by_qid()` **重算**结果，从不读产物 `answer_trace`）。单独篡改时 `[FAIL] G4 …artifacts_sha256 现场重算不一致 1 个：answer_trace 登记 dbbd7dfc…／重算 c70f9389…`；smart4（连带改写清单里的 `sha256`/`bytes`）后，全档仅剩 `G6`（其失败唯一原因是镜像缺 `阶段02-` 使 `G5` 为 UNRUN），**新增失败为空**。
- **B-03（P0）产物 `evidence_type` 无取值校验。** 复现：case5 与 smart5。`evidence_type` 在门禁源码里**只出现一次**（`:104` 的 `ROW13_FIELDS` 字段名元组）。实测 F1／F2 均 `[OK]`；单独篡改由 `[FAIL] G4 …qa_records 登记 e0d3cf03…／重算 a23be177…` 捕获；smart5 后新增失败为空。
- **B-04（P0）`max_tokens` 死值 ＋ 全档无校验。** `工具\验收第8阶段.py:611,619-620` 把《21》的 `max_tokens` 解析进 `frozen["max_tokens"]`，但 `:628-631` 的判定 `bad3` 只含 `model_name/model_version/temperature` 加 `endpoint`；`:640-653` 的登记比对也不含 `max_tokens`。**`frozen["max_tokens"]` 赋值后从未被读取**（全文检索 `frozen[` 仅出现在 618/620/623 赋值与 629/640/642/648/651 读取三值＋版本，无 620 的读取）。**实测（`B_补测_max_tokens.py`，输出 `B_补测_max_tokens_output.txt`）**：镜像里把 `config.ANSWER["max_tokens"]` 由 16384 改为 8192 后，`期望 FAIL = B1` → `实测 退出码=1 FAIL=['G6'] 新增失败=∅`，B1 行原文 `[OK ] B1 模型三值一致（…硬约束 2 ＋《02》第12.4节 登记） model_name=deepseek-flash／…／temperature=0／endpoint=…` —— **判定：★漏判（假阴性）★**。
- **B-05（P2）`and None` 死代码。** `:1074`。复现：`grep -n "and None" 工具\验收第8阶段.py`。
- **B-06（P2）文档不一致。** `交付物/03-代码\问答\README.md:17` 复现：`grep -n "区块" 交付物/03-代码\问答\README.md`。
- **B-07（P2）清单内嵌绝对路径。** 复现：`python -c "import json;print(json.load(open('交付物/05-系统实现/智能问答系统/问答产出/run_manifest.json',encoding='utf-8'))['artifacts_sha256']['answer_trace']['path'])"` → `C:\Users\15129\Desktop\毕业设计\阶段08-…\answer_trace.jsonl`。
- **B-09（P2）门禁自带正对照偏弱。** 见 §四 末「与门禁自带 `--selftest` 的差异」。

未发现：`except: pass` 静默兜底、导入期发请求、随机数、时间戳参与字节比较、中文路径/BOM 导致的读写异常（全部文件读写均显式 `encoding="utf-8"`，`write_jsonl` 用 `newline="\n"`，路径用 `os.path.join`）。错误路径均 `SystemExit`／非零退出，未见「出错仍写正式产出」—— `run_answer.cmd_run` 在门禁失败且未写产出时非零退出（门禁 E4 现场重算 `passed_all` 佐证）。

### 3.5 检查 #4：门禁假阳性风险 —— **未观测到误判**（低风险）

| 风险点 | 结论 | 证据 |
| --- | --- | --- |
| 绝对路径依赖 | **已消解** | `resolve_under_root():214-235` 按「从某存在顶层目录起」的后缀在 `--root` 下重定位；本次 10 个镜像（`--root` 指向临时目录）A1／G4 均实测通过 |
| `git status` 格式 | **已消解** | `git -c core.quotepath=false status --porcelain`（`:419,428`），中文路径不被转义；A3 按相对路径**子串**定范围（`:537-549`），不依赖列宽/顺序 |
| 本地 tmp 路径 | **无依赖** | 门禁只在系统临时目录建镜像，产物路径均经 `--root` 解析 |
| 执行顺序 | **自洽或有守卫** | `finish()` 行序自检（`行序＝A1…H4 逐位一致`）；`atexit _exit_guard:2011-2019` 在异常中断时补打 `[FAIL]`，不静默 |
| `--root` 重定位边界 | **显式降级为 UNRUN 而非误判** | 镜像缺 `阶段02-` 时 G5 记 `[UNRUN] …本项在镜像里不成立`（而非 FAIL），设计正确 |

唯一行为性影响：门禁 A3／H4 依赖调用时工作树干净；若复核者在 `交付物/03-代码\检索\`／`阶段09-` 留有未提交改动，A3／H4 会按设计 FAIL —— 属**预期行为**，非假阳性。

---

## 四、假阴性测试结果表

脚本：`B_代码与门禁\B_篡改测试.py`（自建镜像，不复用 `--selftest`）；原始输出：`B_代码与门禁\B_篡改测试_output.txt`；逐例日志：`B_代码与门禁\篡改运行日志\_log_*.txt`。
镜像文件集为门禁 `MIRROR_FILES` 的**超集**（补入 `22-第8阶段产出文档（智能问答系统）.md`，使 H1/H2/H3 可走「通过」路径）。
基线（原样副本）实测：`FAIL=['G6'] UNRUN=['G5'] 退出码=1` —— `G5` 在镜像里 UNRUN（缺 `阶段02-`），`G6` 因此 FAIL。故下表以**「相对基线的新增失败」**为判据。

| 反例 | 篡改内容 | 期望 FAIL | 实测（新增失败） | 判定 |
| --- | --- | --- | --- | --- |
| ① 证据顺序颠倒 | 颠倒 `answer_trace.jsonl` 中 PE-01 的 `evidence` 数组 | C3 | **C3**、G4 | ✅ 抓到（`C3 …PE-01 呈现序 … ≠ trace …`） |
| ② 引用编号越界 | PE-02 正文 `[证据1]`→`[证据99]` | D2、E4 | **D2**、**E4**、G4 | ✅ 抓到（`D2 …PE-02 越界 n=99（m=9）`） |
| ③ 图谱段与标注不一致 | PE-03 图谱段换成固定标注，`graph_used` 仍为真 | D4、E2 | **D4**、**E2**、G4 | ✅ 抓到（`D4 …PE-03 graph_used=1 但系统段=本次回答未使用图谱扩展`） |
| ④ `total_tokens`→3601 | `answer_trace.jsonl` PE-01 `token_account.total_tokens=3601` | C4 | **仅 G4**（C4 仍 `[OK] 最大值=3599`） | ❌ **漏判**（见 B-02） |
| ⑤ `evidence_type`→表外取值 | `qa_records.jsonl` A-001 的 `evidence_type="表外取值"` | F1 | **仅 G4**（F1/F2 仍 `[OK]`） | ❌ **漏判**（见 B-03） |
| ⑥ `temperature`→0.7 | `交付物/03-代码\问答\config.py` `ANSWER["temperature"]=0.7` | B1 | **B1** | ✅ 抓到（`B1 …temperature=0.7…《02》12.4 已登记行 temperature='0'`） |
| ⑦ `K`→字面量 8 | `交付物/03-代码\问答\config.py` `K = _need("K")`→`K = 8` | B2 | **B2 判 [OK]**；连带 C5、E1、F3、G1、G2 FAIL ＋ C2/C4/C6/assemble_all 记 ENV | ❌ **B2 漏判**（见 B-01；`assemble.py:183` 的 `SystemExit：证据条数 10 超过 K=8` 间接暴露） |
| ⑧ `model_calls.total`→999 | `run_manifest.json` `model_calls.total=999` | B4 | **B4**（G4 仍 `[OK]`） | ✅ 抓到（`B4 …total=999…现场重算…30`） |
| ⑨（补测）`max_tokens`→8192 | `交付物/03-代码\问答\config.py` `ANSWER["max_tokens"]=8192` | B1 | **新增失败 = ∅**（B1 仍 `[OK]`） | ❌ **漏判**（见 B-04；脚本 `B_补测_max_tokens.py`） |
| **smart④**（聪明篡改） | ④ ＋ 同步改写 `run_manifest.artifacts_sha256` | C4 | **新增失败 = ∅**；全档仅剩 G6（镜像缺 `阶段02-` 所致） | ❌ **完全逃逸**（见 B-02） |
| **smart⑤**（聪明篡改） | ⑤ ＋ 同步改写 `run_manifest.artifacts_sha256` | F1 | **新增失败 = ∅**；全档仅剩 G6 | ❌ **完全逃逸**（见 B-03） |

**与门禁自带 `--selftest` 的差异**：门禁自带三例的正对照 `base_fail={"H1","H2","H3","G6"}`，源于 `MIRROR_FILES` **故意不含《22》**，使 H1/H2/H3/G6 在镜像里只走 FAIL 路径；且三例**均只改 `answer_trace.jsonl`**，G4 的 SHA 承担了主要捕捉责任。本线自建的 8 例（＋ 1 例补测＝9 例）覆盖了 `qa_records.jsonl`、`config.py`、`run_manifest.json` 三类**未被自带 selftest 触及**的篡改面，并额外做了「同步改写 SHA」的逃逸验证 —— 这正是 B-01／B-02／B-03／B-04 四条 P0 得以显形的条件。

---

## 五、无法判定与未验证事项

1. **B-08 口径分叉的残余风险（单列，不判缺陷）**：`model_selection.machine_check` 自留的 graph／leak／empty 判定与 `answer.gate` 同式但独立实现。日期／禁词／引用三口径已单源，**未发现实际分歧**，但两处实现若日后单侧修改即会产生分叉；本次**未能构造出可复现的分歧样本**，故单列而不判失败。
2. **硬约束 19（密钥）门禁侧无专项行**：仅核实了代码侧不硬编码、不回显，且 G1 剔除凭据环境变量；**未见门禁扫描源码硬编码密钥的行**，无法据此判定「密钥不出现在任何产物」已被门禁覆盖。
3. **硬约束 20（术语）**：门禁只有 `term_discipline` 非行级 note，**未见逐术语硬判**，无法给出「术语口径已被硬约束覆盖」的证据。
4. **门禁 `full` 档零调用的间接性**：本线据「唯一两个子进程 ＋ G1 自核 0 调用 ＋ `assert_model_calls_allowed` 前置」推断零调用；**未用网络抓包或密钥吊销做外部验证**。
5. **镜像与真实工作区的等价性**：镜像不含 `阶段02-`，`G5` 恒为 UNRUN、`G6` 恒 FAIL，故 §四 采用「新增失败」判据；**未能构造「G5 亦通过」的完整镜像**（需复制全工作区含文献 PDF），因此「smart④/⑤ 在真实工作区将 39/39 通过」系**由代码路径推断**，非直接观测。
6. **`工具\跨文档核验.py` 本轮改动的功能影响**：改动仅注释 ＋ `WANT_STAGES` 增项，已核对 diff；但**未逐项验证新增 `阶段08-` 登记后各检查项的输出变化**（不在本线范围）。

---

## 附：三条最需决策者亲自复核的事项

1. **B-01**：`工具\验收第8阶段.py` 的 B2 行 —— 「四项定值由检索侧导入、无第二份字面量」这一声明，**恰恰在它跳过的 `config.py` 里失效**。建议决策者亲自在 `交付物/03-代码\问答\config.py` 写一行 `K = 8` 跑一次门禁，确认 B2 仍报 `[OK]`。
2. **B-02 / B-03**：产物 `answer_trace.jsonl` 的 `total_tokens` 与 `qa_records.jsonl` 的 `evidence_type` **没有语义校验，只有 G4 的 SHA**。建议决策者确认：这两项是否应由门禁**逐值重算**（而非依赖产物新鲜度），以及「同步改写 SHA 即逃逸」是否可接受。
3. **B-04**：`max_tokens`（硬约束 2 的冻结值 16384）在门禁里**从未被比较**。建议决策者确认这是有意从简，还是遗漏。
