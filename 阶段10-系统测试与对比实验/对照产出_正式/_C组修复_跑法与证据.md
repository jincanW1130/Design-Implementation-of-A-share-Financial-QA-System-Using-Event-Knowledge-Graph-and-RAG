# C 组修复：正式集 trace 生成、注入与补跑（跑法与证据）

> 本文件是**证据与跑法登记**，不是正式交付报告。正式报告是同目录的 `A_vs_C_对照报告.md`／`A_vs_C_对照.json`。

## 0. 结论摘要

| 项 | 读数 |
| --- | --- |
| C 组有效题数（正式集 120 题） | **117**（首轮 115 ＋ 补跑转正 2） |
| C 组未通过题 | 3 题：FQ-022、FQ-093、FQ-115（均 `3004 / answer_gate_failed / date_unverifiable`） |
| 报告里 C 列 | 已全部落地（核心集 105 题、压力子集 12 题、全量 117 题） |
| 模型调用 | 成功题 117 次（逐题 attempts 均为 1）＋ 失败题 15 次（各 ≥1 次，不落 trace 行）≥ **132 次**（授权上限 140 次内） |
| 冻结区改动 | **0**：`代码\`（1145 文件）、`工具\`（16 文件）、`阶段07\检索产出\`、正式题集、`对照产出_v13\`（462 文件）逐文件 sha256 前后一致 |

## 1. 根因（自行复读确认，非照抄）

`代码\问答\run_answer.py:516` 把 C 组特例化：`if args.question or (args.group and args.group != "C")` ——
非 C 组走检索桥接，C 组改走 `load_cases_from_trace()` → `代码\问答\config.py:56` 的 `TRACE_PATH`
＝ `阶段07-RAG检索系统\检索产出\per_question_trace.jsonl`（30 行预实验集冻结 trace，`schema=stage7-pipeline-trace-1.0`）。
正式题号 `FQ-*` 不在其中 ⇒ 每题在 `run_answer.py:522` 登记 `error_code=1002 / reason="no_runnable_case"` 后退出。
修复前 120 题的失败留痕已归档为 `_C组修复_修复前失败留痕.json`（120 条，全部 1002／no_runnable_case）。

## 2. 生成正式集 C 组 trace（零模型调用）

```powershell
python 代码\检索\pipeline.py --profile run `
  --questions 阶段10-系统测试与对比实验\测试集\questions.jsonl `
  --group C --out 阶段10-系统测试与对比实验\对照产出_正式\_正式集trace_C.jsonl
```

* 退出码 **0**；**120 行**；`schema=stage7-pipeline-trace-1.0`；每行 32 键（含 `structural_note` 的为 33 键）；
  `group=C`、`switches={graph_depth:2, time_filter:false, evidence_sort:false}`、`K/N/预算=10/20/3600`、`g=2`；
  `total_tokens ≤ 3600` 全部成立；112／120 题使用图谱扩展；图谱侧新增块入集 147 个。
* sha256 = `1dfebd5880f09e7a050506d5b676fae0e6baa0d790bf29165d3720a269523ec0`（947,598 字节）。
* **零模型调用**：该路径只用本地向量检索组件（`BAAI/bge-small-zh-v1.5`，`local_files_only=True`、
  `HF_HUB_OFFLINE=1`，见运行日志 `%TEMP%\formal_C_stdout.txt` 第 5～7 行）与本地图谱查询；
  CLI 自己在结尾打印「0 次大语言模型／外部接口调用」。
* **不需要 adapter**：正式题集字段是预实验集的超集（`time_window`／`gold_evidence_chunk_ids`／`task_type`／
  `gold_hop_depth` 都在），`pipeline.load_questions()` → `normalize_question_row()` 直接吃下，
  未对 `代码\检索\` 做任何改动。

## 3. 等价性自证

### (a) 同 CLI 复跑预实验集 vs 冻结 trace —— 逐字节相同

```powershell
python 代码\检索\pipeline.py --profile run `
  --questions 阶段07-RAG检索系统\预实验问题集\questions.jsonl --group C --out %TEMP%\pre_C_trace.jsonl
python 阶段10-系统测试与对比实验\对照产出_正式\_等价性自证_C组.py `
  %TEMP%\pre_C_trace.jsonl 阶段07-RAG检索系统\检索产出\per_question_trace.jsonl `
  阶段10-系统测试与对比实验\对照产出_正式\_等价性自证_C组_预实验比对.json
```

| 读数 | 值 |
| --- | --- |
| 冻结 trace sha256 | `17566e9772f1e6e6d9fa7556d4bedfe0331e5535a8ec3348c376308cd1398b4b`（260,054 字节） |
| 复跑 trace sha256 | 同上，**byte_identical = True** |
| 逐题逐字段 | 30／30 题**全部字段相同**（`rows_identical_on_all_fields=30`） |
| `final_evidence_chunk_ids` 逐位一致率 | **1.0（30／30）** |
| 字段级 | 33 个顶层字段**无一字段出现差异**；题号顺序一致、题号集合一致 |

即：这条 CLI 与冻结 trace 是**同一口径**，不是"看上去像"。

### (b) 正式集抽 5 题现场复跑 vs 新 trace

`_等价性自证_C组_b.py`：抽样规则先定死（120 题按 1 起等距取 FQ-001／030／060／090／120），
用 `代码\检索\run_query.py --qid <FQ> --group C --questions <正式集>`（退出码均 0）现场跑：

**5／5 题的「呈现顺序」与新 trace 的 `final_evidence_chunk_ids` 逐位相同。**

```
FQ-001 [1007000,1007002,1007001,1094000,1282000,2019000,1176003,2019004,1183002,2020000]
FQ-030 [1320001,1320000,1364007,1244000,1294000,1294001,1244001,1149020,1112000,1112001]
FQ-060 [1027002,1339011,1054001,1228000,1347000,1228001,1239000,1027000,1239001,1104011]
FQ-090 [1118000,1128002,1128000,1016000,1128001,1290000,1192003,1377088,1016004]
FQ-120 [1592008,1592000,1450001,1450000,1592011,1480001,1450002,1436001,1501000,1418002]
```

## 4. 让 C 组读到这份 trace：注入方式

`跑正式对照.py` 的重写点：`injected_questions()`（第 511～536 行）在 **spawn 每一题之前**用内嵌
`_SHIM_TEMPLATE` 重写 `工具\_正式对照_shim\sitecustomize.py` ⇒ 对该文件的手工扩展会在第一个子进程之前被覆盖。
该脚本又在"不得修改"范围内，故改用**同一机制的第二个标准启动钩子**：

* 新增 `对照产出_正式\_正式集C_shim\usercustomize.py`（CPython `site.execusercustomize()` 在
  `execsitecustomize()` **之后**按 PYTHONPATH 搜索 `usercustomize`，与 sitecustomize 叠加）；
* 它把已导入的 `sitecustomize._patch_answer()` 包一层——**不复制任何逻辑**——先跑原函数
  （正式题集路径 ＋ `FQ-` 解析照旧生效），再追加 `module.TRACE_PATH = <正式集 C 组 trace>`；
* 开关与目标同为一个环境变量 `STAGE10_FORMAL_C_TRACE`；门闸＝该变量存在 **且** `sys.argv[0]`
  的 basename 是 `run_answer.py`。

跑法（`$root` = 仓库根）：

```powershell
$env:PYTHONPATH = "$root\阶段10-系统测试与对比实验\工具\_正式对照_shim;$root\阶段10-系统测试与对比实验\对照产出_正式\_正式集C_shim"
$env:STAGE10_FORMAL_C_TRACE = "$root\阶段10-系统测试与对比实验\对照产出_正式\_正式集trace_C.jsonl"
python 阶段10-系统测试与对比实验\工具\跑正式对照.py --groups C
```

### 有／无注入对照（均 0 次模型调用）

| 情形 | 命令 | 退出码 | 读数 |
| --- | --- | --- | --- |
| **无**注入 | `run_answer.py --qid FQ-001 --group C --dry-run` | **1** | `[失败契约] error_code=1002 reason=no_runnable_case` |
| **有**注入 | 同一命令 | **0** | 「装配完成：1 题／FQ-001 组=C 证据 10 条 total_tokens=3474／3600／模型调用次数 = 0」 |
| 门闸范围 | 主脚本名非 `run_answer.py`（父进程／`python -c` 探针） | 0 | `TRACE_PATH` **仍是冻结的 30 题那份**；只有 `QUESTIONS_PATH`／`identifiers_for` 生效 |
| self-report | 同 `run_answer.py` 名的探针 | 0 | `STAGE10_SHIM.patched=[QUESTIONS_PATH, identifiers_for, TRACE_PATH]`，含 `trace_path_was/now/by` |

## 5. 补跑与最终读数

`--groups C` 首轮：退出码 **1**（有失败题即非零，且失败题不入产出），115／120 成功。
按 `--only-qids` 补跑 3 轮：FQ-036（第 1 轮）、FQ-023（第 2 轮）转正，第 3 轮无新增。

| 轮次 | 命令 | 退出码 | 参与 | 结果 |
| --- | --- | --- | --- | --- |
| 首轮 | `--groups C` | 1 | 120 | 115 成功／5 失败 |
| 补跑 1 | `--groups C --only-qids FQ-022,FQ-023,FQ-036,FQ-093,FQ-115` | 1 | 5 | FQ-036 转正；剩 4 |
| 补跑 2 | `--groups C --only-qids FQ-022,FQ-023,FQ-093,FQ-115` | 1 | 4 | FQ-023 转正；剩 3 |
| 补跑 3 | `--groups C --only-qids FQ-022,FQ-093,FQ-115` | 1 | 3 | 无转正；**最终 117／120** |

未通过的 3 题（逐题错误码与 reason，取自 `<逐题目录>\error_contract.json`）：

| 题号 | error_code | reason | 门禁失败项 |
| --- | --- | --- | --- |
| FQ-022 | 3004 | answer_gate_failed | `date_unverifiable` |
| FQ-093 | 3004 | answer_gate_failed | `date_unverifiable` |
| FQ-115 | 3004 | answer_gate_failed | `date_unverifiable` |

这三题在 A／B／D／E 四组里**同样**未通过（FQ-022 四组全败；FQ-093 在 A／D／E 败；FQ-115 在 B／D／E 败），
属答案侧冻结门禁的**共性**现象，不是 C 组或本次注入引入的。

## 6. 报告与核验

* `--report-only`（默认六组、0 次模型调用）→ 退出码 **0**；读入 A 113／B 118／C 117／D 117／E 117／B1 120 行。
* 报告里 C 列已全部落地（见下表），不再是 "—"。
* `python 工具\跨文档核验.py --strict-citations` → 退出码 **0**，结论「全部通过」。
* `python -m pytest 代码\测试 -q` → **121 passed**。
* 冻结区前后指纹比对：`代码\` 1145 文件、`工具\` 16 文件、`阶段07\检索产出\` 6 文件、正式题集 1 文件、
  `对照产出_v13\` 462 文件 —— **改 0／删 0／增 0**；A／B／B1／D／E 的组级产出 mtime 均早于本次作业
  （23:55～00:08，本次作业 00:18 起）。

## 7. 如实登记的边界

1. **注入没落在 `sitecustomize.py` 上**：该文件每次 spawn 前被 `跑正式对照.py` 重写（见第 4 节），
   手改必被覆盖；改用 `usercustomize`（同一 PYTHONPATH 启动钩子机制，非冻结区，可复现、可证伪）。
2. **报告「七、失败清单」显示"无"是 `--report-only` 的既有行为**（该模式只从已聚合文件重算，不重新收集
   failures），五组的真实有效题数看各表「题数」行：A 113／B 118／C 117／D 117／E 117／B1 120。
   这一点对 A～E 六列一视同仁，非本次引入。
3. **模型调用次数**：成功题 117 次（`attempts` 逐题均为 1，实测）＋ 失败题 15 次（失败题不落 trace 行，
   故按每次 ≥1 计）≥ 132 次；未超过授权的 140 次，但**失败题的实际请求数没有权威台账**，
   此处只给下限，不外推成一个精确值。
4. **人工评分未做**：Accuracy／Completeness／Faithfulness 的 0／1／2 评分与 ≥20% 二次复评未进行，
   故《02》第12.8节「Answer Accuracy 不下降」一项仍无法判定（报告中原本就如此登记）。
5. **另发现一处与本任务无关的既有瑕疵**（未修，B1 产物只读）：`跑正式对照.py` 的 `run_b1_one()`
   在 `injected_questions()` **之外**起子进程，B1 子进程拿不到 `FQ-` 标识解析，于是 120 题的
   `answer_id` 全退化成 `A-CUSTOM`；按 `answer_id` 聚合的 `对照产出_正式\B1\qa_records.jsonl`
   因此只剩 **1 行**（逐题目录里的 120 份 `qa_records.jsonl` 各自完整）。B1 不参与四项检索指标，
   影响限于问答记录表的聚合完整性。

## 8. 复现命令（一条龙）

```powershell
$root = "C:\Users\15129\Desktop\毕业设计"
# ① trace（0 次模型调用）
python "$root\代码\检索\pipeline.py" --profile run --questions "$root\阶段10-系统测试与对比实验\测试集\questions.jsonl" --group C --out "$root\阶段10-系统测试与对比实验\对照产出_正式\_正式集trace_C.jsonl"
# ② 等价性自证
python "$root\阶段10-系统测试与对比实验\对照产出_正式\_等价性自证_C组.py" "$env:TEMP\pre_C_trace.jsonl" "$root\阶段07-RAG检索系统\检索产出\per_question_trace.jsonl" "$root\阶段10-系统测试与对比实验\对照产出_正式\_等价性自证_C组_预实验比对.json"
python "$root\阶段10-系统测试与对比实验\对照产出_正式\_等价性自证_C组_b.py"
# ③ 注入 + 跑 C 组（120 次模型调用上限内）
$env:PYTHONPATH = "$root\阶段10-系统测试与对比实验\工具\_正式对照_shim;$root\阶段10-系统测试与对比实验\对照产出_正式\_正式集C_shim"
$env:STAGE10_FORMAL_C_TRACE = "$root\阶段10-系统测试与对比实验\对照产出_正式\_正式集trace_C.jsonl"
python "$root\阶段10-系统测试与对比实验\工具\跑正式对照.py" --groups C
# ④ 报告（0 次模型调用）
python "$root\阶段10-系统测试与对比实验\工具\跑正式对照.py" --report-only
```
