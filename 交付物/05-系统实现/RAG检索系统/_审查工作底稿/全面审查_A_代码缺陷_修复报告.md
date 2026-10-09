# 全面审查 A（代码缺陷）—— 修复报告

- 审查输入：`交付物/05-系统实现/RAG检索系统\_审查工作底稿\全面审查_A_代码缺陷.md`
- 修复范围：该报告缺陷表中的**高（H-1～H-4）／中（M-1～M-12）／低（L-1～L-25）**，另含 3 处「提示（N-1～N-3）」的说明。
- 纪律约束（全程遵守）：不改 `交付物/04-数据与知识图谱/数据准备\数据集\v2.1\`、`图谱导出\v2.1_v1_2\`、`交付物/08-文献与开题/文献调研与开题\`、《19》《20》、`工具\` 下除 `验收第6阶段.py` 以外的脚本、`交付物/03-代码\抽取与图谱\config.local.json`；不发网络请求、不做模型调用；不用 PowerShell 解析 JSON／文本；不做任何 `git add`／`commit`。
- 日期：2026-09-29
- 未修改代码的「不修」项均给出理由；未能修改的项如实列出，不绕过。

---

## 一、高（H-1～H-4）

### H-1 `build_company_aliases.py` 用 `json.dumps` 渲染 Python 模块 → 产出含 `null`、不可 import、退出码却为 0

- **处置**：修。改用 `pprint.pformat(..., sort_dicts=True)` 渲染 Python 字面量；写盘前 `_selfcheck_module_text()` 先 `compile()` 再真跑一次 `exec()` 并逐键比对，任一环节不过即抛 `RenderSelfCheckError`，由 `main()` 转成**非零退出且不写盘**。
- **关键点**：单靠 `compile()` 拦不住 `null`／`true`／`false`——它们是合法 Python **标识符**，语法能过，要到 `exec` 才抛 `NameError`。故自检必须做 exec 往返。
- **修复前后（原始输出）**：

```
$ python -c "…; B._selfcheck_module_text('REGISTERED_NAMES = {\"000001\": null}\n', {'000001': {}})"
compile() 通过（说明单靠 compile 拦不住 null）
RenderSelfCheckError → 产出模块不可执行：NameError: name 'null' is not defined
```

- **合法落点实跑**（`--no-network`，不调接口；退出码 0、正常写盘）：

```
$ python 交付物/03-代码\抽取与图谱\build_company_aliases.py --no-network --out "$TEMP/l1_out/company_registered_names.py"
  688981 中芯国际     → （无）                      [unknown]
  920019 铜冠矿建     → （无）                      [unknown]
EXIT=0
```

### H-2 未提供 `--out` 时覆盖 git 跟踪的冻结模块

- **处置**：修。未提供 `--out` 时**拒绝写入并退出 2**；`--out` 指向冻结模块 `company_registered_names.py` 时必须再加 `--force-frozen`，否则同样退出 2。
- **修复前后（原始输出）**：

```
$ python 交付物/03-代码\抽取与图谱\build_company_aliases.py --no-network
[build_company_aliases] 拒绝写入：未提供 --out。
  默认落点 …\交付物/03-代码\抽取与图谱\company_registered_names.py 是被 git 跟踪的冻结数据模块，隐式覆盖会污染源码树。
  如确需重建该冻结模块，请显式指定：--out "…" --force-frozen
EXIT=2

$ python 交付物/03-代码\抽取与图谱\build_company_aliases.py --no-network --out "交付物/03-代码/抽取与图谱/company_registered_names.py"
[build_company_aliases] 拒绝写入：落点是被 git 跟踪的冻结数据模块 …\company_registered_names.py。
  确认要重建它时请加 --force-frozen（例如先看一眼来源分布是否有 unknown）。
EXIT=2
```

### H-3 `extract_event_time.py` 子集跑（`--limit`／`--docs`）静默截断交付覆盖层

- **处置**：修。子集跑默认把覆盖层／报告／度量三件套改写到独立落点 `*.partial.json`；确要写交付层需显式 `--allow-overlay`，而写前会校验「本次 cases 数 == 全量 null 事件数」，不符即**阻断并非零退出**。
- **落点解析（原始输出）**：

```
--limit=None  --docs=None     --allow-overlay=False → …\_全量\v2.1_v1_2\event_time_backfill.json
--limit=3     --docs=None     --allow-overlay=False → …\event_time_backfill.partial.json
--limit=None  --docs=12,34    --allow-overlay=False → …\event_time_backfill.partial.json
--limit=3     --docs=None     --allow-overlay=True  → …\event_time_backfill.json
```

- **阻断实跑（原始输出）**：

```
$ python 交付物/03-代码\抽取与图谱\extract_event_time.py --limit 3 --allow-overlay
[阻断] 拒绝写入交付覆盖层 event_time_backfill.json：本次 cases=3 条，而全量 null 事件为 717 条。
       子集跑（--limit／--docs）截断交付层后 extract_records_sha256 不变，下游 dedup_events.py 会静默放行。
       请去掉 --allow-overlay 让落点自动改为 *.partial.json，或跑全量。
EXIT=1
```

### H-4 `验收第6阶段.py` 镜像重放异常只记 `REPLAY["error"]`（无 `error_kind`）→ 20 项降级 `[SKIP]`、`--no-replay` 仍退出 0 并写「验收通过」

- **处置**：修。引入与 `验收第7阶段.py` 同形的三态记账：`[OK]/[FAIL]`（内容失败＝1）、`[ENV ]`（环境／链上失败＝1）、`[UNRUN]`（未执行＝2）；`REPLAY` 增记 `error_kind` 以区分「显式跳过（`explicit_skip`）」与「环境／链上失败（`environment_chain`）」；`X1` 改为 `not fails and not env_fails and unrun_count == 0 and (skipped == 0 or not no_replay)`，**不能静默通过**。
- **修复前后（原始输出）**：

```
$ python 工具\验收第6阶段.py --no-replay
  检查项合计（A～W）：100 项，其中通过 80、失败 0、SKIP 20、未执行 20、环境失败 0
  [FAIL] X1 全部检查项通过（…未执行任一非零即 FAIL；pilot 不适用项可 SKIP）
         实测 内容失败 0 项：无；环境／链上失败 0 项；未执行（--no-replay）20 项（H/I/J/K/S/T 组未验证）
  最终：检查项 102 项，通过 81，内容失败 0，环境／链上失败 0，未执行 20，SKIP 20
结论：**未执行 20 项**（H 组／I 组／J 组／K 组／S 组／T 组）——这 20 条证据链从未验证，
      不得宣称第 6 阶段验收通过；退出码 2。
EXIT=2
```

（修订前：末行写「验收通过」、`sys.exit` 为 0、实测 81/101。）

---

## 二、中（M-1～M-12）

| 编号 | 结论 | 最小修复 | 修复前 → 后（原始读数） |
|---|---|---|---|
| **M-1** | **修** | `graph_query.py` 名称／代码索引 `sorted(set(...))` 去重；重生成受影响产物 | `resolve_node("平安银行")`：`['000001','000001','000001']` → `['000001']`；受影响名称键 104 个 |
| **M-2** | **修** | `pre_experiment.py pick_k` 饱和遍历定义域由 `candidates` 改为 `feasible` | 合成网格（K=15 超预算）：修复前 K\*=15（违反预算）→ 修复后 K\*=10 |
| **M-3** | **修** | `extract.py` 新增 `subset_redirect_subdir()`／`redirect_output_files()`，子集跑改写入 `_冒烟N篇`／`_指定篇目N篇`；新增 `--allow-overwrite` | `--limit=5`→`_冒烟5篇`；`--docs=12,34`→`_指定篇目2篇`；全量→`''`（不动交付落点） |
| **M-4** | **修** | `auto_annotate.py` `--limit` 试跑改写入 `<out-dir>/_子集运行_limitN/`；新增 `--allow-overwrite` | 代码路径 + 提示语；正式产物目录不再被就地覆盖 |
| **M-5** | **修** | `disambiguate.py` 新增 `load_doc_company_lists()` 从权威来源 `documents.jsonl` 取 `doc_id→company_list` | 修复前：抽取记录含 `company_list` 键 **0/709**（谓词恒 False）→ 修复后：表 709 篇、公司代码 774 条（659 篇非空） |
| **M-6** | **修** | `sample_eval_set.py verify()` 增 `chunk_index` 与 `chunk_id` 自洽检查 | 修复前：不检查（矛盾永远发现不了）→ 修复后：**12** 条矛盾（DEV-044、TEST-089/134/137/159/162/166/167/173/181/182/183），`ok: False`；**如实报告，不静默改数据** |
| **M-7** | **修** | `auto_annotate_lint.py` R4 由「任何登记即豁免」收紧为「按端点公司逐个核对名面」 | flash **61 → 65**（+4，与审查报告「漏掉 4 项」一致）；flash.repaired 0 → 5；pro 60 → 60 |
| **M-8** | **修** | `auto_annotate_lint.py`／`auto_annotate_compare.py` 写盘前 `os.path.abspath(path)` | 裸文件名 `--out 报告.md`：`FileNotFoundError [WinError 3] …: ''` → 退出 0、文件落在 cwd |
| **M-9** | **修（如实自述）** | `extract.py build_verify_payload` 自述改为「含时间相关 `reproducibility` 块、不参与逐字节比对」 | 见下「M-9 补注」 |
| **M-10** | **修** | `fetch.py` 两处空池早返回补 `exhausted`／`stop_reason` | 缺键 `info.get("exhausted")=None`（falsy → 完成标记永不写入，165 次重复搜索）→ 现为 `True` |
| **M-11** | **修** | `交付物/03-代码\数据准备\run_all.py` `type(ex)` → `type(exc)` | 子进程起不来时：`NameError: name 'ex' is not defined`（`code=126` 死代码）→ `ValueError: boom` |
| **M-12** | **修** | `验收第6阶段.py` K3 由 `chk(True, …)` 改为读真实读数 | `chk(all(r.get("key_removed") == config.LLM["api_key_env"] for r in 四次重跑))` |

**M-9 补注**：审查建议把 `reproducibility` 块拆去 `verify_run.json`。经核查，`_全量/report_full_run.py`、`_全量/v2.1_v1_2/_对照报告.py` 与《16》都以既有字段名消费它，拆分将牵动**禁止修改**的产物文档；任务文本对该项允许「移出**或**如实修正自述」，故取后者——只在 docstring 里把事实写清（含时间字段、不参与比对），不改结构。

**M-12 附带**：同一脚本 N5 在「交集为空」分支原也写死 `chk(True, …)`，把登记读数 `document_overlap_size` 打印却从不判定。同类缺陷、同属允许修改的文件、且已核实登记值为 `0`，故一并收紧为读真实读数（实测 `0` 与登记 `0` 须同时成立）。改后该项仍 `[OK ]`、检查项数不变（102）。

---

## 三、低（L-1～L-25）

### 已修（14 项）

| 编号 | 位置 | 修法 |
|---|---|---|
| L-1 | `pipeline.py` `entity_match` | 保留行为，补注释记录「证据类型优先」的真实语义 |
| L-2 | `pre_experiment.py:249、582` | 两处 `assert` → `if int(n) < int(k): raise SystemExit(...)`（`python -O` 下不再被剥离） |
| L-3 | `pipeline.py:230`、`run_query.py:131` | docstring 由 `0 ≤ g ≤ K` 改为 `1 ≤ g ≤ K`，注明 `GRAPH_SHARE_FLOOR=1` 与 g=0 的显式退化通道 |
| L-5 | `metrics.py` 自测 | 结束 `shutil.rmtree(_metrics_selftest, ignore_errors=True)`；实测该目录已不再残留 |
| L-6 | `build_questions.py` | 为 `event_evidence`／`company_events` 死分支补注释，说明是保留的规则词汇，不删除 |
| L-7 | `write_graph.py:60、219、1324` | docstring 与 argparse 帮助把 `--force` 记为**当前无操作**，保留以兼容 `run_all` |
| L-8 | `交付物/03-代码\抽取与图谱\run_all.py:244` | 删除不可达的「exit_code==1 且 stdout 含『跳过』→ 记成功」分支（会让日志说谎），补注释 |
| L-9 | `auto_annotate_repair.py:456` | 缓存缺 `attempts_detail[0].input_sha256` 时**直接判不可用**（抛 `RuntimeError`），不再静默复用旧答案 |
| L-10 | `auto_annotate_verify.py:108、119-122` | 删除不可达的 `elif not u: no_usage.append(...)` 与无人读取的 `no_usage` 列表 |
| L-11 | `auto_annotate_verify.py:142`、`auto_annotate_repair.py:808` | `open(...).read()` → `with open(...)` |
| L-12 | `auto_annotate.py` | `stats["api_calls"] += 1` 移入 `with _PACE_LOCK:` |
| L-13 | `auto_annotate.py:939、1062` | 两处 `assert` → `raise RuntimeError` |
| L-15 | `fetch.py` `request()` | 请求计数移出 try，去掉 except 分支里的重复自增 |
| L-16 | `chunk.py:154、178` | 空／全空白输入返回 `[]`（原先返回 `['']`，绕过末尾「空块不得输出」守卫） |
| L-18 | `event_first.py:327` | `time.strftime("…+08:00")`（把硬编码 `+08:00` 贴在本地时间上）→ `datetime.now(TZ).isoformat(timespec="seconds")`（`TZ` 复用 `fetch.py`） |
| L-19 | `fetch.py:901、943` | 公告路径 `json_body` 包 `except (FetchError, ValueError)` 并登记 `ok=False` 后继续 |
| L-20 | `交付物/03-代码\数据准备\config.py` | 4 个死键／失实注释（`TARGET_DOC_COUNT_V1`、`preserve_cjk_punctuation`、`keep_line_patterns_after_drop`、`INGEST_TIME`）逐一注为「未启用（占位）」并写明实际决定量 |

### 不修（给理由）

- **L-4 ＝ N-3（`metrics.py` `--from-trace` 缺文件打印 `[SKIP]` 后 `return 0`）**：不修。`--help` 已把「文件缺失时打印提示并跳过」**写成契约**，属已声明的设计风险（N-3）。贸然改非零退出会破坏已声明的行为契约，且该通道不在交付链上。
- **L-14（`disambiguate.py:270-278` 与 `config.py:718` 注释口径分歧）**：不修。属「口径分歧」类，且全量实测 `ambiguous_alias` **0 例**（`unresolved.jsonl` 1070 ＝ no_alias_match 1063 ＋ distinct_entity_marker 7），现网未触发；无实例可证明哪一侧为真，改注释会制造未经证实的断言。
- **L-17（`clean.py` 与 `check.py` 标题规范化口径分歧）**：不修。同上「口径分歧」类，且**当前不可达**（实测 709 篇标题含 U+3000／U+00A0 的为 0 篇）。两侧取一需要裁定，非本次修复可单方决定。
- **L-21～L-25（`工具\验收第4阶段文档.py`、`验收第7阶段.py`、`跨文档核验.py`）**：不修。这些脚本在**禁止修改**清单内（`工具\` 下除 `验收第6阶段.py` 以外的脚本），且正由并行任务处理。
- **L-11 的剩余两处**：`工具\标注助手.py:611、1933`、`工具\核验知网题录.py:1100-1101` 同属禁止修改路径，跳过。

### 提示（N-1～N-3）

- **N-1**（`check.py` 检查 7 只判存储字段、不重算）：不改。报告本身已说明是「建议」，不是缺陷；重算需动 `交付物/03-代码\数据准备\check.py` 的检查口径，超出「最小修复」范围。
- **N-2**（`DEDUP["minhash_similarity_threshold"]=None` 已声明占位）：不改，非缺陷。
- **N-3**：同 L-4。

---

## 四、产物重生成与指标一致性（M-1 回归）

### 4.1 冻结顺序重生成

```
1) python 交付物/03-代码\检索\pipeline.py   --group C --out "交付物/05-系统实现/RAG检索系统\检索产出\per_question_trace.jsonl"
2) python 交付物/03-代码\检索\run_query.py  --run-manifest
3) python 交付物/03-代码\检索\metrics.py
```

### 4.2 四项指标**逐项与之前完全相同**

`metrics_pre.jsonl` 的 sha256 在 M-1 前后**逐字节不变**，即四项指标（`recall_at_k`／`precision_at_k`／`mrr`／`complete_evidence_recall_at_k`）**完全相同**：

```
K=10  n_q=30  recall_at_k=0.69230159  precision_at_k=0.15  mrr=0.65925926  complete_evidence_recall_at_k=0.56666667
sha256(metrics_pre.jsonl) = b33491f723cd33aa42b6cbe9cdd136e74c868b088e41103352aaff6fdedd9dd2
```

`run_manifest.json` 的 `determinism.files.metrics_pre.jsonl.matches_t11 = True`（与 T11 记录的基线 sha 相同），进一步证明「指标未变」。**git 亦佐证**：`git status` 只把 `per_question_trace.jsonl` 与 `run_manifest.json` 标为已修改，**`metrics_pre.jsonl` 未出现在改动列表中**。

### 4.3 两次运行逐字节相同（sha256）

| 产物 | run1 sha256 | run2 sha256 | workspace sha256 | matches_t11 |
|---|---|---|---|---|
| `per_question_trace.jsonl` | `2b1c0da1…29a72` | `2b1c0da1…29a72` | `2b1c0da1…29a72` | **False**（＝本次去重所致，见下） |
| `metrics_pre.jsonl` | `b33491f7…d9dd2` | `b33491f7…d9dd2` | `b33491f7…d9dd2` | True |
| `pre_experiment_matrix.jsonl` | `df9c05ad…21731` | `df9c05ad…21731` | `df9c05ad…21731` | True |
| `k_selection.json` | `ab62e009…0659d` | `ab62e009…0659d` | `ab62e009…0659d` | True |

`run_manifest.json` 自身：`00b06960d82770005a5e425285af3de3523591d0dbdaf8de9c4e67bfe7478622`。

### 4.4 trace 变化恰为「去重」

- `graph_audit` 的 `segments["① 两路取候选"].entity_resolution.matches[].node_ids` 共 **46** 个列表，**0** 个仍含重复。
- 30 行中有 29 行被修改，变化恰为 `sorted(set(old))`；`k_selection.json` 的 `selected` 仍为 `{K:10, N:20, context_token_budget:3600, g:2}`。

### 4.5 sha256 引用更新的**未达成项（如实报告）**

- `run_manifest.json` 内的 sha256 已随重生成更新；其中 `t11_recorded_run1_sha256`／`run2_sha256`（旧 `7839de9a…`）**有意保留**，它就是「T11 记录的基线」，`matches_t11=False` 正是本次去重的可见证据。
- `交付物/05-系统实现/RAG检索系统\19-第7阶段产出文档（RAG检索系统）.md`（约 L428）仍引用旧 trace 旧 sha，但《19》在**禁止修改**清单内（另一条任务在改），故**未改**。
- 名为 `_替换执行` 的目录只有 `交付物/08-文献与开题/文献调研与开题\_替换执行\` 一处，属**禁止修改**路径，且经检索其中**不含**本次涉及的 sha256，故**未改**。
- 审查工作底稿下的历史日志（`_审查工作底稿\...`）保留旧 sha 作为历史记录，**不改**。

---

## 五、验证原始输出

1. **编译**：`python -m compileall -q 交付物/03-代码/检索 交付物/03-代码/抽取与图谱 交付物/03-代码/数据准备 工具/验收第6阶段.py` → `EXIT=0`。
2. **模块自测（退出码 0）**：

```
pipeline --selftest        EXIT=0   自证结论：10／10 条通过
metrics --selftest         EXIT=0   自证：20／20 通过
graph_query --selftest     EXIT=0   自检项 14，通过 14，失败 0
vector_search --selftest   EXIT=0   自证结论：9/9 条通过
pre_experiment --selftest  EXIT=0   结论：全部通过（0 次大语言模型／外部接口调用）
auto_annotate_lint selftest EXIT=0   lint 自测：全部通过
auto_annotate_repair selftest EXIT=0 提准自测：全部通过
auto_annotate selftest     EXIT=0   缓存键自检：22／22 通过
```

（`build_company_aliases.py` 与两个 `run_all.py` **无** `--selftest` 子命令。）

3. **`07_文档自检.py`** → `EXIT=0`、`自检结论：全部通过（0 项失败）`。
4. **`git status --short`**：见 §六。

---

## 六、`git status --short`

本任务改动（全部落在允许路径）：

```
 M 交付物/03-代码\抽取与图谱\{auto_annotate,auto_annotate_compare,auto_annotate_lint,
                    auto_annotate_repair,auto_annotate_verify,build_company_aliases,
                    disambiguate,extract,extract_event_time,run_all,sample_eval_set,write_graph}.py
 M 交付物/03-代码\数据准备\{chunk,config,event_first,fetch,run_all}.py
 M 交付物/03-代码\检索\{build_questions,graph_query,metrics,pipeline,pre_experiment,run_query}.py
 M 工具\验收第6阶段.py
 M 交付物/05-系统实现/RAG检索系统\检索产出\per_question_trace.jsonl
 M 交付物/05-系统实现/RAG检索系统\检索产出\run_manifest.json
```

结论：新增/修改的产物恰为 M-1 预期的两件（trace、manifest）；`metrics_pre.jsonl` 未变，佐证指标不变。

**不属于本任务的改动（同仓并行任务）**，本任务未触碰：`.gitattributes`、`工具\核验知网题录.py`、`工具\跨文档核验.py`、`工具\验收第4阶段文档.py`、`工具\验收第5阶段数据.py`、`工具\验收第7阶段.py`、`交付物/04-数据与知识图谱/数据准备\13-…md`、`交付物/03-代码\检索\config.py`（该文件的 B-19 复核批注）。

未跟踪项：`_审查工作底稿\全面审查_A/B/C*.md`（审查报告，非本任务产物）与本报告文件。

---

## 七、未达成／不确定之处

1. **《19》与 `阶段02\_替换执行` 的 sha256 引用未更新**——两者都在禁止修改清单内（§四.5 已说明）。
2. **M-6 报告 `ok: False`**：交付评测集中**既有的 12 条 `chunk_index` 与 `chunk_id` 矛盾**。这是**如实报告**的结果，不是本次改动引入，也**未**修改数据来消除。
3. **M-4 与 M-3 的现场运行未做**：`--limit` 试跑的落点重定向已由函数级读数（M-3）与代码路径（M-4）证实，但因会触发模型调用／网络请求（本任务禁止），未做端到端实跑。
4. **L-14／L-17 两项口径分歧**：无实例可判定哪一侧为真，未单方裁定。
5. **M-9**：按「如实修正自述」处置，未做结构拆分（拆分将牵动禁止修改的产物文档）。
