# 全面审查 A：全项目 Python 代码缺陷审查

- 审查日期：2026-09-29
- 审查范围：`交付物/03-代码\检索\`、`交付物/03-代码\抽取与图谱\`、`交付物/03-代码\数据准备\`、`工具\` 四个目录下全部 `.py`
- 审查方式：逐行读码 ＋ 最小反例实跑（一律在 `%TEMP%` 副本/临时落点上，工作区只读）
- 纪律声明：本审查**未**改动工作区任何文件、**未**发起网络请求、**未**调用模型 API；全部实跑命令跑完 `git status --short` 均为空

---

## 一、结论摘要

### 1.1 各严重程度数量

| 严重度 | 数量 | 说明 |
|---|---|---|
| 高 | 4 | 均不污染**已封版**产物，但会造成「静默产出不可用数据」「就地覆盖交付层」「验收闸门静默放行」 |
| 中 | 16 | 多为「就地覆盖/截断正式产物」「复核器口径漂移」「空输入或网格越界先崩」「断言恒真」 |
| 低 | 25 | 死交付物/03-代码/死参数、`assert` 在 `-O` 下失效、未关闭句柄、未清理临时文件、docstring 与实现分歧、资源/计数卫生 |
| 提示 | 3 | 已声明行为或纯设计风险，仅登记 |

**未发现任何会污染「已封版 v2.1 数据集」「已交付《19》检索产出」「已入库证据」的确定性缺陷**——所有高危项的触发条件都是「重跑/子集跑/离线跑」这类非封版路径，或「验收脚本自身的记账」。

### 1.2 按文件分布（只列有缺陷的文件）

| 目录 | 文件 | 高 | 中 | 低 | 提示 |
|---|---|---|---|---|---|
| 交付物/03-代码\检索 | `graph_query.py` | | 1 | | |
| 交付物/03-代码\检索 | `pre_experiment.py` | | 1 | 1 | |
| 交付物/03-代码\检索 | `pipeline.py` | | | 1 | |
| 交付物/03-代码\检索 | `run_query.py` | | | 1 | |
| 交付物/03-代码\检索 | `metrics.py` | | | 1 | 1 |
| 交付物/03-代码\检索 | `build_questions.py` | | | 1 | |
| 交付物/03-代码\抽取与图谱 | `build_company_aliases.py` | 2 | | | |
| 交付物/03-代码\抽取与图谱 | `extract_event_time.py` | 1 | | | |
| 交付物/03-代码\抽取与图谱 | `extract.py` | | 2 | | |
| 交付物/03-代码\抽取与图谱 | `auto_annotate.py` | | 1 | 2 | |
| 交付物/03-代码\抽取与图谱 | `auto_annotate_lint.py` | | 2 | | |
| 交付物/03-代码\抽取与图谱 | `auto_annotate_compare.py` | | 1 | | |
| 交付物/03-代码\抽取与图谱 | `auto_annotate_repair.py` | | | 3 | |
| 交付物/03-代码\抽取与图谱 | `auto_annotate_verify.py` | | | 2 | |
| 交付物/03-代码\抽取与图谱 | `disambiguate.py` | | 1 | | |
| 交付物/03-代码\抽取与图谱 | `sample_eval_set.py` | | 1 | | |
| 交付物/03-代码\抽取与图谱 | `config.py` | | | 1 | |
| 交付物/03-代码\抽取与图谱 | `write_graph.py` | | | 1 | |
| 交付物/03-代码\抽取与图谱 | `run_all.py` | | | 1 | |
| 交付物/03-代码\数据准备 | `fetch.py` | | 1 | 3 | |
| 交付物/03-代码\数据准备 | `run_all.py` | | 1 | | |
| 交付物/03-代码\数据准备 | `chunk.py` | | | 1 | |
| 交付物/03-代码\数据准备 | `clean.py` / `check.py` | | | 1 | |
| 交付物/03-代码\数据准备 | `event_first.py` | | | 1 | |
| 交付物/03-代码\数据准备 | `config.py` | | | 1 | |
| 工具 | `验收第6阶段.py` | 1 | 1 | | |
| 工具 | `验收第5阶段数据.py` | | 3 | | |
| 工具 | `验收第7阶段.py` | | 1 | 2 | |
| 工具 | `验收第4阶段文档.py` | | | 1 | |
| 工具 | `标注助手.py` | | | 1 | |
| 工具 | `核验知网题录.py` | | | 1 | |
| 工具 | `执行助手.py` | | | 1 | |
| 工具 | `跨文档核验.py` | | | 2 | |

---

## 二、缺陷表（按严重度排序）

> 每条格式：`文件:行号` ｜ 问题 ｜ 最小复现（命令＋原始输出）｜ 影响面 ｜ 建议修法 ｜ 严重度
> 「复核」标明该条是否由我本人第一手复现（✅＝我实跑过；◎＝我静态核对了代码路径；○＝仅代理证据）

### 高

#### H-1 `交付物/03-代码\抽取与图谱\build_company_aliases.py:273`｜离线建档产出的「Python 模块」含 `null`，根本不能 import

- **问题**：`body = "REGISTERED_NAMES = " + json.dumps(table, ...)` 用 JSON 渲染 Python 模块，第 259 行的模块 docstring 还写「（JSON 是合法 Python 字面量）」。但 JSON 的 `null`/`true`/`false` 在 Python 里是未定义名——只要有一条 `source=unknown`，产出模块就无法导入。
- **最小复现**（落点仅写 `%TEMP%`，数据集只读）：
  ```bash
  python "交付物/03-代码/抽取与图谱/build_company_aliases.py" --no-network --out "%TEMP%/audit_s7/crn_offline.py"
  # 退出码=0（脚本自称成功）
  python -c "exec(compile(open(r'%TEMP%/audit_s7/crn_offline.py',encoding='utf-8').read(),'m','exec'),{})"
  ```
  原始输出：
  ```
  null 出现次数 = 83
  exec 失败: NameError name 'null' is not defined
  --- 对照：冻结模块可导入 ---
  SOURCE_COUNTS= {'cninfo_company_intro': 105} 条数 105
  ```
  （消费端实证：把 `config.DISAMBIG["registered_names_path"]` 指向该文件后 `disambiguate.load_registered_names()` 直接抛 `NameError: null`，T4 崩在 import 而非任何 `SystemExit` 分支。）
- **影响面**：**不污染已封版产物**（冻结模块 `company_registered_names.py` 是 105/105 `cninfo_company_intro`，可正常导入）。影响＝离线口径（`--no-network`，文档里的「离线复核」用法）产出的建档模块不可用，退出码却是 0——静默失败。
- **建议修法**：改用 `pprint.pformat`／自写 repr（输出 `None`/`True`/`False`）；或写盘前 `compile(text, path, "exec")` 自检，不过即非零退出。
- **严重度**：高 ｜ 复核：✅（实跑）

#### H-2 `交付物/03-代码\抽取与图谱\build_company_aliases.py:294`（＋58、296-297）｜默认落点就是被 git 跟踪的冻结模块，`--no-network` 会就地降级它

- **问题**：`path = os.path.abspath(args.out) if args.out else OUTPUT_MODULE`，`OUTPUT_MODULE` ＝ 脚本同目录的 `company_registered_names.py`（**git 跟踪**）；docstring 把「不给 `--out` 的 `--no-network`」写成常规用法，退出码仍为 0。
- **最小复现**：同上一次运行（不给 `--out` 时的落点即冻结模块）。证据：
  ```bash
  git ls-files --error-unmatch 交付物/03-代码/抽取与图谱/company_registered_names.py   # 命中（被跟踪）
  git check-ignore -v 交付物/03-代码/抽取与图谱/company_registered_names.py            # 退出码 1（未被忽略）
  ```
  离线口径实测 105 家里 **83 家**变 `unknown`；冻结模块为 105/105 `cninfo_company_intro`。
- **影响面**：一次误用即产生**源码树 diff** ＋ 别名表退化（消歧率下降、待消歧清单变长）。不污染数据集与《19》。
- **建议修法**：不给 `--out` 时要求显式确认，或默认写独立目录，或拒绝在 `unknown > 0` 时覆盖冻结模块。
- **严重度**：高 ｜ 复核：◎（代码路径核对；降级规模由 H-1 同次实跑佐证）

#### H-3 `交付物/03-代码\抽取与图谱\extract_event_time.py:841-842、982`｜`--limit`／`--docs` 把交付覆盖层截断且下游无守卫

- **问题**：`collect_cases` 先 `cases = cases[:int(limit)]`（`--docs` 同理由 830 行过滤），`finish()` 第 982 行**无条件** `dump_json(paths["overlay"], overlay)`，落点是固定的 `交付物/03-代码/抽取与图谱/_全量/v21_v1_2/event_time_backfill.json`（实测 717 条），**没有 `--out` 类参数**。
- **最小复现**：
  ```bash
  python -c "import sys;sys.path.insert(0,r'交付物/03-代码\抽取与图谱');import config;print(config.time_backfill_paths('v21_v1_2')['overlay'])"
  # 该覆盖层为交付文件，results=717、in_scope=717、events_total=1114
  ```
  `dedup_events.py:149-171` 只校验 `source.extract_records_sha256`，**不校验条数**。
- **影响面**：截断后覆盖层的 `extract_records_sha256` 不变 → `load_time_backfill` 静默放行 → T5/T6 产物 `event_time` 大面积回落为 null，**全程无人报错**。
- **建议修法**：`--limit/--docs` 时落点换名（如 `event_time_backfill.partial.json`），或在 `load_time_backfill` 里校验 `counts.events_null_in_scope` 与实际 null 数一致，不符即阻断。
- **严重度**：高 ｜ 复核：◎（代码路径核对）

#### H-4 `工具\验收第6阶段.py:1435-1447、2621、2639-2640、2655`｜镜像重跑失败或异常一律降级为 SKIP，SKIP 不影响退出码，结论仍写「验收通过」

- **问题**：`ensure_replay` 的 `except Exception` 只记 `REPLAY["error"]`（**无 error_kind**）；`replay_or_skip` 把 H/I/J/K/S/T 全组转 `skip()`；`X1` 断言体是 `chk(not fails, ...)`（自述「SKIP 不影响退出码」）；`sys.exit(1 if fails else 0)`——`skipped` 完全不参与。
- **最小复现**：
  ```bash
  cd C:\Users\15129\Desktop\毕业设计
  python 工具/验收第6阶段.py --no-replay
  ```
  原始输出（尾部）：
  ```
  [SKIP] H H1 消歧重跑退出码为 0  镜像重跑未执行：--no-replay：命令行显式跳过镜像重跑
  …（H/I/J/K/S/T 共 20 条）…
  检查项合计（A～W）：99 项，其中通过 79、失败 0、SKIP 20
  [OK  ] X1 全部检查项通过（任一失败即非零退出；SKIP 不影响退出码）  实测 失败 0 项：无
  最终：检查项 101 项，通过 81，失败 0
  另有 SKIP 20 项（pilot 模式下不适用或按命令行跳过；原因见各组 [SKIP] 行，不计入失败）
  结论：全部通过（通过 81 项／检查项 101 项，另有 SKIP 20 项）。第 6 阶段验收通过，退出码 0。
  EXIT=0
  ```
  异常通道（同一后果，触发者是脚本自身程序错误）：
  ```bash
  python 工具/验收第6阶段.py --export-dir "Z:/zz_nope"
  # → 20×[SKIP] … 「镜像重跑未执行：ValueError: path is on mount 'Z:', start on mount 'C:'」
  ```
- **影响面**：不污染任何交付产物（脚本只读）。但放行口径是「两脚本退出码均为 0」，因此 **20/101 条证据链（整条镜像重跑 H/I/J/K/S/T）可在从未执行的情况下满足放行条件**，日志末行仍写「验收通过」——放行闸门的静默失效。
- **建议修法**：给 `except` 补 `error_kind`（`--no-replay` 记「显式跳过」，其余记 `environment_chain` 并走非零通道——照 `工具\验收第7阶段.py:625-628` 的做法，那里两条 `except` 都标 `environment_chain`）；`X1` 断言改为 `not fails and (skipped == 0 or ARGS.no_replay)`。
- **严重度**：高 ｜ 复核：✅（实跑）

### 中

#### M-1 `交付物/03-代码\检索\graph_query.py:170-178、231、335`｜建名索引不去重 → `resolve_node` 返回重复 `node_ids`，污染交付 trace

- **问题**：`_load()` 对同一 `nid` 按 `name`／`short_name`／`aliases` 重复 `setdefault(...).append(nid)`，只 `lst.sort()` 不去重；`resolve_node` 原样返回该列表；`g2_two_hop`／`g7_paths` 逐节点起步形成重复计数。
- **最小复现**：
  ```bash
  cd 交付物/03-代码\检索
  python -c "import graph_query as gq;g=gq.default_graph();print(g.resolve_node('平安银行')['node_ids']);print('by_name 含重复键数=',sum(1 for v in g.by_name.values() if len(v)!=len(set(v))),'/',len(g.by_name))"
  ```
  原始输出：
  ```
  ['000001', '000001', '000001']
  by_name 含重复键数= 104 / 2845
  ```
- **影响面**：**污染已交付产物**——`检索产出/per_question_trace.jsonl` 中 **29/30 题**的 `segments.<段>.entity_resolution.matches[].node_ids` 含重复（如 PE-01 长城汽车 `['601633','601633','601633']`）。因下游 `seeds` 用集合去重，四项指标与最终证据集**不受影响**；但与 `g2_two_hop` docstring「与等效 Cypher 一致」矛盾，且交付文件里该字段是错的。
- **建议修法**：`_load()` 末尾 `lst[:] = sorted(set(lst))`。
- **严重度**：中 ｜ 复核：✅（实跑）

#### M-2 `交付物/03-代码\检索\pre_experiment.py:345-355`｜`pick_k` 饱和循环遍历 `candidates`（仅 gold 可行）而非 `feasible`（gold＋预算），可选出被预算排除的 K

- **问题**：第 345 行起点与第 346 行循环都用 `candidates`，而 `feasible`（同时满足 gold 与预算）才是「可行」定义；函数 docstring 自称「可行 + 饱和的最小 K」。
- **最小复现**（反例：K=15 中位占用 5000 > 预算 3600）：
  ```bash
  cd 交付物/03-代码\检索
  python - <<'PY'
  import sys; sys.argv=["pre_experiment.py"]
  import pre_experiment as pe
  N=20; BUDGET=3600
  def row(m,c): return {"occupancy":{"text_tokens":{"median":m}},"metrics":{"complete_evidence_recall_at_k":c,"recall_at_k":c,"precision_at_k":c,"mrr":c}}
  R={(5,N):{"row":row(900,.30)},(10,N):{"row":row(3400,.70)},(15,N):{"row":row(5000,.90)}}
  B={5:{"metrics":{"complete_evidence_recall_at_k":.30},"mean_evidence_size":5},
     10:{"metrics":{"complete_evidence_recall_at_k":.70},"mean_evidence_size":10},
     15:{"metrics":{"complete_evidence_recall_at_k":.90},"mean_evidence_size":15}}
  print(pe.pick_k([5,10,15],R,B,BUDGET,4,N))
  PY
  ```
  原始输出：
  ```
  pick_k 返回 K* = 15
  gold+预算 都可行的档 feasible = [5, 10]
    K= 5 gold_ok=True  budget_ok=True  selected=False  note=满足 gold 约束与预算
    K=10 gold_ok=True  budget_ok=True  selected=False  note=满足 gold 约束与预算
    K=15 gold_ok=True  budget_ok=False selected=True   note=被预算排除（文本块中位数占用 5000 > 预算 3600）
  >>> 选中的 K=15 的 budget_feasible=False（是否被预算排除=True）
  ```
- **影响面**：**真实数据未触发**（现行 Δ=CER@15−CER@10=0 → 选定 K=10），故交付未受污染。属潜伏缺陷：一旦 grid 上沿档位的 CER 增量 > 0 且该档被预算排除，就会选中一个越预算的 K。
- **建议修法**：循环改用 `feasible`（或起点 `feasible[0]` 并在 detail 里按 `feasible` 标 `selected`）。
- **严重度**：中 ｜ 复核：✅（实跑）

#### M-3 `交付物/03-代码\抽取与图谱\extract.py:1174-1175、1318-1319、1335、1246`｜`--limit`／`--docs` 就地覆盖默认口径 T3 全量产物

- **问题**：子集跑与全量跑共用同一批落点（`selection.json`/`coverage.json`/`extracted.jsonl`/`rejected.jsonl`/`manifest.sha256`/`verify.json`），无物理隔离。
- **最小复现**（交付产物自证）：`_全量/v2.1_v1_2/verify.json` 的 `reproducibility.documents = [3, 709, 709]`、`identical_across_runs = false`；`_全量/v2.1_v1_2/_冒烟3篇/运行日志_冒烟3篇.txt` 末行指向全量目录的 `verify.json`。
- **影响面**：`_全量/` 被 `.gitignore` 覆盖（非 git 交付），但它是 T4～T6 的输入与各报告 sha256 的比对基准；被 3 篇子集覆盖后需重跑全量才能恢复。
- **建议修法**：与 pilot 同样的物理隔离（子集落 `_冒烟N篇\` 或加后缀）。
- **严重度**：中 ｜ 复核：○（代理证据＋交付产物字段自证）

#### M-4 `交付物/03-代码\抽取与图谱\auto_annotate.py:973-974、1068-1069`｜`--limit 4`（docstring 明写的试跑用法）覆盖正式产物 `dev.auto.jsonl`

- **问题**：`records = records[:args.limit]` 后 `by_split` 只含 dev，遂只重写 `dev.auto.jsonl`（4 行），台账与报告同时被 4 条口径覆盖。
- **最小复现**：交付目录 `交付物/04-数据与知识图谱/数据准备\数据集\抽取评测集\v2.1\自动标注\` 中 `dev.auto.jsonl` 应为 60 行、`test.auto.jsonl` 为 200 行。
- **影响面**：正式评测集标注被小样本覆盖。
- **建议修法**：`--limit` 时改后缀，或禁止在已有正式产物目录内写。
- **严重度**：中 ｜ 复核：○（代理证据）

#### M-5 `交付物/03-代码\抽取与图谱\disambiguate.py:292、313、326`｜`in_doc_company_list` 恒为 `False`／`[]`

- **问题**：`doc_codes = {str(c) for c in (record.get("company_list") or [])}`，而 T3 抽取记录**没有 `company_list` 字段**（键是 `entity_id/name/quote/...`）。
- **最小复现**：`disambiguation.json` 中 `Company in_doc_company_list` 分布 `{'False': 755, 'None': 1070}`；`unresolved.jsonl` 1070 条全 `[]`；抽取记录里含 `company_list` 键的篇数 = 0。
- **影响面**：交付文件里该标注字段恒假；`grep -rn in_doc_company_list` 显示**无任何下游消费者**，不改图谱结论，但属「不可复核的假读数」。
- **建议修法**：改从 `config.DOCS_PATH`（documents.jsonl）取该 doc 的 `company_list`，或删掉该字段。
- **严重度**：中 ｜ 复核：○（代理证据）

#### M-6 `交付物/03-代码\抽取与图谱\sample_eval_set.py:578、584`｜交付评测集 12/260 条 `chunk_index` 与 `chunk_id` 自相矛盾

- **问题**：`chunk` 取自 `choose_chunk(unit)`，`chunk_index` 却取 `unit["chunk_index"]`（信号块），两者可不同。
- **最小复现**（用 `config.CHUNKS_PATH` 反查）：评测集 260 条中 **12 条**不一致，如 `DEV-044: chunk_index=2 但 chunk_id=1536006 的块 chunk_index=6`。
- **影响面**：`chunk_index` 只被 `工具\标注助手.py:410` 渲染进人工工作区 markdown（`chunk_id` 才是权威），不影响任何指标；但 `verify()`（1201-1257）不含该一致性，**自检永远发现不了**。
- **建议修法**：`"chunk_index": chunk["chunk_index"]`，并把该一致性加进 `verify()`。
- **严重度**：中 ｜ 复核：○（代理证据）

#### M-7 `交付物/03-代码\抽取与图谱\auto_annotate_lint.py:593-613`｜硬规则 R4「任一登记即整条豁免」→ 实测漏报 4 条

- **问题**：只要有**任意一条** `case_type=company_out_of_scope`，该条目所有名单外端点的 R4 命中全被吞掉，不逐公司比对。
- **最小复现**：对交付 `lint_命中` 输入跑规则函数，flash 版命中 11 条、其中 **4 条**登记未覆盖该端点（`TEST-005`/`TEST-181`/`TEST-183`），三条 R4 命中均为 False（pro 版 0 条）。
- **影响面**：交付的 `提准\lint报告.md` 写「`R4_out_of_scope_logged` 硬 0 命中」，该结论在实现口径下不成立。
- **建议修法**：按端点公司名逐个核对登记条目的 `summary/quote`，或要求 `case_id` 与端点对应。
- **严重度**：中 ｜ 复核：○（代理证据）

#### M-8 `交付物/03-代码\抽取与图谱\auto_annotate_lint.py:1092`、`auto_annotate_compare.py:510`｜`--out` 给裸文件名即崩

- **问题**：`os.makedirs(os.path.dirname(args.out), ...)`，`os.path.dirname("x.md") == ""` → `os.makedirs("")` 抛 `FileNotFoundError`。（对照：`auto_annotate.py:746` 用 `cache_path()` 返回绝对路径，安全。）
- **最小复现**（cwd 在 `%TEMP%` 空目录）：
  ```bash
  cd %TEMP%/audit_s7/cwd
  python "C:/Users/.../交付物/03-代码/抽取与图谱/auto_annotate_compare.py" --out "对照报告.md"
  ```
  原始输出：
  ```
  File "…\auto_annotate_compare.py", line 510, in main
    os.makedirs(os.path.dirname(path), exist_ok=True)
  FileNotFoundError: [WinError 3] 系统找不到指定的路径。: ''
  EXIT=1
  ```
- **影响面**：口径是「`--out` 可写 Markdown」，用相对裸名必崩（`--help` 未提示）。
- **建议修法**：`os.path.dirname(os.path.abspath(path))`。
- **严重度**：中 ｜ 复核：✅（实跑）

#### M-9 `交付物/03-代码\抽取与图谱\extract.py:1363、1444、1478`｜`verify.json` 自称「不写时间、参与逐字节比对」，实际内含运行读数

- **问题**：`reproducibility = {"api_calls":[3,749,31], "cache_hits":[...], "wall_clock_seconds":[52.78,12294.21,536.31], "documents":[3,709,709], "identical_across_runs":false, "manifest_sha256":[三次不同]}`；而 `write_manifest()`（1235-1249）**不含 `verify.json`**，故其「逐字节可复现」既无人校验也不成立。
- **影响面**：与任务书「时间戳/耗时字段单独成行、单独成文件」的纪律冲突。
- **建议修法**：把 `reproducibility` 拆到 `verify_run.json`（含时间戳），`verify.json` 只留时间无关字段。
- **严重度**：中 ｜ 复核：○（代理证据＋字段名自证）

#### M-10 `交付物/03-代码\数据准备\fetch.py:2518-2522、2397-2398、2552`｜空候选池早返回缺键 → 「已完成标记」永不写入，重跑重复站内检索

- **问题**：`plan_event_first_news()` 的两条早返回（2518 `if not pool:`；2397-2398 `return [], {}`）返回的 info **没有 `exhausted`/`stop_reason` 键**，而 `run_event_first_news()` 第 2552 行无条件读 `info.get("exhausted")`（→ `None`）与 `info.get("stop_reason")`（→ 打印 `None`）。连锁：完成标记不写进 `raw\_fetch_log.jsonl` → `news_supplement_done()` 永返 False → 每次重跑都重发全部站内检索并重抓正文。
- **最小复现**（打桩 HTTP 返回空候选，全离线）：
  ```bash
  python %TEMP%\dp_review\t5.py
  ```
  原始输出：
  ```
  返回值 info 的键 = ['candidates','dup_title','dup_url','fetched','outside_window','scope','scope_label','search_requests','skipped_by_cache','skipped_one_company']
  info.get('exhausted')   = None
  info.get('stop_reason') = None
  该行是否含已完成标记 = False
  桩 HTTP 收到请求次数 = 165
  ```
- **影响面**：**不污染已封版 v2.1**（实测 `v2.1/raw/_fetch_log.jsonl` 中标记出现 2 次，走的是正常分支）。影响＝重跑/pilot/网络受限时的运行成本与日志可读性（白跑 165 次检索，日志写「（None）」）。
- **建议修法**：空池分支补 `"exhausted": True, "stop_reason": "候选池为空（窗口内无候选）"`；2397-2398 一并补齐。
- **严重度**：中 ｜ 复核：◎（代码路径＋代理实跑输出核对）

#### M-11 `交付物/03-代码\数据准备\run_all.py:111`｜`type(ex)` 未定义名，把「子进程启动失败」处理分支变成崩溃

- **问题**：`except Exception as exc:` 块里写 `type(ex).__name__`（`ex` 是错误名）。子进程起不来时该行抛 `NameError`，第 112 行的 `code = 126`、结果登记、`return` 全部成死代码。
- **最小复现**（只打桩 `run_all.subprocess`）：
  ```bash
  python %TEMP%\dp_review\t4.py
  ```
  原始输出：
  ```
  File "…\run_all.py", line 111, in main
    print("[run_all] 环节 %s 启动失败：%s: %s" % (name, type(ex).__name__, exc))
  NameError: name 'ex' is not defined
  ```
- **影响面**：不影响数据集；影响编排层错误语义（失去受控退出码与失败汇总）。
- **建议修法**：`type(exc).__name__`。
- **严重度**：中 ｜ 复核：✅（代码行第一手确认）

#### M-12 `工具\验收第6阶段.py:1613`｜`chk(True, ...)`：一条恒真检查被计入通过项

- **问题**：`chk(True, "K3 重跑子进程显式摘掉 %s（…不可能静默调用模型）" % config.LLM["api_key_env"], "实测 本脚本用 env.pop(\"%s\") …")`——断言体写死为 `True`；真实证据 `REPLAY["run_all"]["key_removed"]`（:1345）被记录却从未被任何断言读取。
- **最小复现**：
  ```bash
  python -c "import io;s=io.open(r'工具/验收第6阶段.py',encoding='utf-8').read().split(chr(10));print(s[1612]);print([l for l in s if 'key_removed' in l])"
  ```
  原始输出：
  ```
      chk(True, "K3 重跑子进程显式摘掉 %s（缓存未命中即硬失败，不可能静默调用模型）"
  ['    env.pop(config.LLM["api_key_env"], None)', '            "key_removed": config.LLM["api_key_env"]}', '    REPLAY = {"error": None, "key_removed": config.LLM["api_key_env"]}']
  ```
- **影响面**：不污染产物；但「通过 81 项」里掺进一项永远绿的检查；若将来删掉 `:1338` 的 `env.pop`，这一项仍显示 `[OK ]`。
- **建议修法**：改判 `all(r.get("key_removed") == config.LLM["api_key_env"] for r in (R["run_all"], R["run_all_2"], R["from_run"], R["write_graph_again"]))`。
- **严重度**：中 ｜ 复核：✅（静态第一手确认）

#### M-13 `工具\验收第5阶段数据.py:1084`（＋104-106）｜「未执行」项不以未执行计数，且以 `[OK ]` 前缀呈现

- **问题**：`note()` 打印 `  [OK ] %s`。N5/N5a/N6/N7/N8（幂等真实重跑一组）默认不执行，却只以 `[OK ]` 行出现，**不进 `fails`、不进任何未执行计数**（与 `验收第7阶段.py` 的 `[UNRUN]`＋`unrun_count` 形成对照）。
- **最小复现**：
  ```bash
  python 工具/验收第5阶段数据.py
  ```
  原始输出（节选）：
  ```
  [OK ] N0 幂等检查模式  静态等价（默认模式，未执行真实重跑；加 --with-idempotence 可实跑）
  [OK ] N5 真实重跑未执行（静态等价模式）  如需真实重跑：python 工具\验收第5阶段数据.py --with-idempotence
  最终：检查项 99 项，通过 99，失败 0
  结论：全部通过（99/99 项）。第 5 阶段数据侧验收通过，退出码 0。
  ```
- **影响面**：不污染产物；但「99/99 通过」的分母里没有那 5 条未执行项，读者会读成「幂等性已被验证」。
- **建议修法**：照第 7 阶段三态记账——未执行项打 `[UNRUN]` 并计入结论行，默认模式退出码改 2 或结论行显式写明「未验证：幂等真实重跑」。
- **严重度**：中 ｜ 复核：○（代理证据）

#### M-14 `工具\验收第5阶段数据.py:280-283、288、1186-1189`｜被禁术语门禁的「否定语境」判定含裸「无」「未」「非」，门禁可被任意一行正文豁免

- **问题**：`neg_markers` 默认元组含裸单字 `无`/`未`/`非`；判定是「整行里出现任一标记即豁免」，而被扫描的含数据集 `clean\documents.jsonl`、`chunks\chunks.jsonl` 的**整篇正文行**（财经新闻几乎每行都有「未」「无」）。
- **最小复现**（用该脚本自身的 `neg_markers` 元组判定三行样本）：
  ```bash
  python -c "marks=('不引入','不采用','不使用','不进入','不按','排除','避免','严禁','禁止','不得','不再','无','未','非','之外','而不');[print(repr(l),'命中=',[m for m in marks if m in l]) for l in ['本系统以向量索引为主存储并对外提供查询。','集群规模已扩展，无需额外部署；本系统以向量索引为主存储。','非功能性需求之外，本系统以向量索引为主存储。']]"
  ```
  原始输出：
  ```
  '本系统以向量索引为主存储并对外提供查询。' 命中= []
  '集群规模已扩展，无需额外部署；本系统以向量索引为主存储。' 命中= ['无']
  '非功能性需求之外，本系统以向量索引为主存储。' 命中= ['非', '之外']
  ```
- **影响面**：**潜在**（当前工作区 P1 实测 0 命中）。但使「不许出现该四字连写词」这条硬约束在机器上失去可证伪性。
- **建议修法**：删掉裸单字标记，只保留多字否定词组；单字情形改局部窗口判定（连写词前后 ±10 字内含否定词才豁免）。
- **严重度**：中 ｜ 复核：✅（静态/函数逻辑第一手确认）

#### M-15 `工具\验收第5阶段数据.py:818-826、1231`｜零行数据集先崩在 `min()`，而 I1～I5 对「0 篇／0 块」一律判 `[OK ]`

- **问题**：J3 的明细串被**急切求值**（`min(t[2] for t in lens)`），空输入抛 `ValueError`；同时 I1～I5 因 `read_jsonl` 对空文件静默返回 `[]` 而在零样本时恒真。
- **最小复现**（在 `%TEMP%` 造「文件存在但零行」的数据集，不动工作区）：
  ```bash
  python 工具/验收第5阶段数据.py --dataset "%TEMP%/audit/empty_ds2"
  ```
  原始输出（尾部）：
  ```
  [OK ] I1 每篇文档至少 1 个文本块  实测 文档 0 篇、无块文档 0 篇
  …（I2～I5 全 [OK ]）…
  File "…\验收第5阶段数据.py", line 823, in <module>
    % (min(t[2] for t in lens), …)
  ValueError: min() iterable argument is empty
  EXIT=1
  ```
- **影响面**：不污染产物。两个独立问题：(a) 数据缺失时给 traceback 而非 `[FAIL] J3`，剩余 A～S 全部丢失；(b) I1～I5 在零样本时给出「通过」。
- **建议修法**：`:818` 前加 `if not lens: chk(False, 'J3 …', '实测 0 条文本块，无法判定')`；I 组前置 `chk(bool(doc_rows) and bool(chunk_rows), '数据集非空')`。
- **严重度**：中 ｜ 复核：○（代理证据）

#### M-16 `工具\验收第7阶段.py:1391、1396-1398、1403、1409`｜K 网格越界时 U 组先抛异常，本应由 Y1 报出的「gold 超过 K 上限」变成崩溃

- **问题**：五个取值点都假设「网格覆盖得住、R1 行齐全」；`max_gold > max(GATE_K_GRID)` 时 `min()` 抛 `ValueError`，`median_by_k[anchor_k]` 可能 `KeyError`，`feasible_ind[0]` 可能 `IndexError`。U 组排在 Y 组之前，而 Y1 正是断言 gold ≤ K 的那一项。
- **最小复现**：未构造（需篡改题集，超出只读范围）。**证据类型：代码路径核对，非实跑**。
- **影响面**：不污染产物。一个数据问题会以 traceback 吞掉整段 U/V/W/Y 检查。
- **建议修法**：`:1396` 前先判 `if max_gold > max(GATE_K_GRID): chk(False, …)`；`feasible_ind` 空时给 `chk(False, …)`。
- **严重度**：中 ｜ 复核：◎（代码路径核对）

### 低

| 编号 | 文件:行号 | 问题 | 最小复现 | 影响面 | 建议修法 | 严重度 | 复核 |
|---|---|---|---|---|---|---|---|
| L-1 | `交付物/03-代码\检索\pipeline.py:1146-1150` | `evidence_sort_factors` 的 `entity_match` 首分支与初值同为 0（冗余），且对**图侧块恒取 0**（不论其正文是否真含问题实体名） | `cd 交付物/03-代码\检索; python -c "import sys;sys.argv=['p'];import pipeline as P;..."`（见下「复现清单」§5.2）→ 图侧块无论正文是否含实体名，`entity_match` 均为 0 | 仅 E 组呈现顺序，不改集合、不改四项指标；交付 trace 是 C 组（`evidence_sort` 关），故只影响 `_工作底稿/pipeline_trace_E.jsonl` 类非交付产物 | 删冗余分支；若确需图侧优先，改名为「证据类型」并去掉伪装的「实体匹配度」 | 低 | ✅ |
| L-2 | `交付物/03-代码\检索\pre_experiment.py:249、582` | 全目录仅有的两处 `assert`，`python -O` 下守卫消失 | `python -O -c "print(__debug__)"` → `False`；`python -O` 下 `assert 5>=10` 被跳过 | 建议性守卫失效（非法 N<K 网格不再被拦）；与别处 `raise SystemExit` 风格不一致 | 改 `if …: raise SystemExit(...)` | 低 | ✅ |
| L-3 | `交付物/03-代码\检索\pipeline.py:230`、`run_query.py:131` | docstring 写「取值域 0…K」「0 ≤ g ≤ K」，与实现（`config.GRAPH_SHARE_FLOOR=1` 强制 `1 ≤ g ≤ K`）不一致 | `config.py:400-412` 显示 `if not (GRAPH_SHARE_FLOOR <= g <= k): raise ValueError` | 文档误导致用者以为 g=0 合法 | 改 docstring 为 `1 ≤ g ≤ K`（并注明 g=0 仅走显式退化通道） | 低 | ✅ |
| L-4 | `交付物/03-代码\检索\metrics.py:563-566` | `--from-trace <不存在>` 打印两次 `[SKIP]` 后 `return 0` | `python metrics.py --from-trace "…/does_not_exist.jsonl"` → 两行 `[SKIP]`，`EXIT=0`，不写输出 | 「未执行」被当成功（`--help` 已声明此行为，登记为设计风险） | 视需要改为返回非零或 `--allow-missing` 显式开关 | 低 | ✅ |
| L-5 | `交付物/03-代码\检索\metrics.py:702-710` | `--selftest` 把 `a.jsonl`/`b.jsonl` 写进 `_工作底稿/_metrics_selftest/` 且不清理（实测两文件各 2791 字节） | `ls 交付物/05-系统实现/RAG检索系统/_工作底稿/_metrics_selftest/` | 落在 `.gitignore:48` 覆盖的 `_工作底稿/` 内，不污染 git 索引，但留垃圾 | selftest 结束 `shutil.rmtree` | 低 | ✅ |
| L-6 | `交付物/03-代码\检索\build_questions.py`（`derive_candidate_chunks`） | `event_evidence`、`company_events` 两个分支在冻结表 `FROZEN_QUESTIONS` 中从未被使用 | 冻结表 30 题无一条命中这两条分支 | 死分支 | 删除或注明保留理由 | 低 | ◎ |
| L-7 | `交付物/03-代码\抽取与图谱\write_graph.py:60、219、1324` | `--force` 是死参数：全文件仅 3 处出现（docstring、提示语、argparse），`run()` 从不读它 | `grep -n -- "--force\|args.force"` 仅上述 3 处 | `run_all.py --force` 传下来的 `--force` 是空操作 | 实现或删 | 低 | ○ |
| L-8 | `交付物/03-代码\抽取与图谱\run_all.py:241-245`（对照 255-259） | 状态启发式把失败标成成功：`exit_code == 1 and "跳过" in stdout` → 记「成功（命中已有产物，跳过）」；而两个真正的跳过路径都 `return 0` | `extract.py` 的 `selection_assertion` 证明 `problems` 非空 ⟺ `note is None`，故「打印『跳过』」与「退出码 1」**不可能共存** → 该分支不可达 | 日志说谎（同段 `failures += 1` 并 break），产物无损 | 用显式跳过退出码替代字符串匹配 | 低 | ✅ |
| L-9 | `交付物/03-代码\抽取与图谱\auto_annotate_repair.py:456-461` | 缓存缺 `attempts_detail` 时 `first={}` → 跳过错配校验，静默沿用旧答案 | 手工造一条无 `attempts_detail` 的缓存，`process_item(...)` 返回 `{"note":"旧缓存里的答案"}`、`cache_hits=1`、不抛错 | 现网不可达（工具产出的缓存都带该键）；属防线缺口 | 缺 `attempts_detail` 直接判不可用 | 低 | ○ |
| L-10 | `交付物/03-代码\抽取与图谱\auto_annotate_verify.py:108、119-122` | `elif not u: no_usage.append(...)` 不可达，且 `no_usage` 全程未被读取 | `grep -n no_usage` 仅 108/122 两处 | 死代码 | 删 | 低 | ○ |
| L-11 | `交付物/03-代码\抽取与图谱\auto_annotate_verify.py:142`、`auto_annotate_repair.py:808`、`工具\标注助手.py:611、1933`、`工具\核验知网题录.py:1100-1101` | `open(...).read()` 未关闭句柄 | `python -c "…;print(s[610]);print(s[1932])"`（见复现清单） | CPython 引用计数即时回收，无可观测影响；大目录下随文件数累积 | 改 `with open(...)` | 低 | ✅ |
| L-12 | `交付物/03-代码\抽取与图谱\auto_annotate.py:417`（锁在 411-416） | `stats["api_calls"] += 1` 在 `_PACE_LOCK` 之外，默认 `--workers 4` 共享同一 `stats` → 读改写非原子，可能丢更新 | 静态论证（未构造：需联网实跑） | 该值写进 `自动标注台账.json` 与报告 | 计数移进锁内 | 低 | ○ |
| L-13 | `交付物/03-代码\抽取与图谱\auto_annotate.py:939、1062` | `assert` 守卫在 `python -O` 下消失 | 同 L-2 | 1062 行失效会把 `None` 标注写盘（当前不可达）；939 行失效后字节手术会切坏行 | 改 `if …: raise RuntimeError` | 低 | ✅ |
| L-14 | `交付物/03-代码\抽取与图谱\config.py:718` 对照 `disambiguate.py:270-278` | 注释口径「命中多个不同代码 → 待消歧」与实现（R1 唯一命中优先于多命中判定）分歧 | 全量实测 `ambiguous_alias` **0 例**（`unresolved.jsonl` 1070 = no_alias_match 1063 + distinct_entity_marker 7） | 潜在口径分歧，现网未触发 | 二者取一并对齐注释 | 低 | ○ |
| L-15 | `交付物/03-代码\数据准备\fetch.py:298、304` | 5xx/429 让 `request_count` 翻倍计数（try 内先加 1，except 里再加 1） | `python %TEMP%\dp_review\t6.py` → `HTTP 500 → request_count=2, error_count=1`（真实 1 次请求） | 落点：`fetch.summarize()` 的 `[合计] HTTP 请求 N 次`（stdout）与 `勘察/event_first_probe.json` 的 `request_count`；实测当前读数未被污染（`error_count=0`），仅限流时虚高 | 删 try 内那一次自增 | 低 | ✅ |
| L-16 | `交付物/03-代码\数据准备\chunk.py:154、178` | 空输入 `if n <= max_chars: return [text]` 返回 `['']`，绕过末尾「空块不得输出」守卫 | `python %TEMP%\dp_review\t6.py` → `chunk_document('') == ['']` | 管线内**不可达**（`clean.py:442` 已按 `MIN_DOC_CHARS=80` 拦住）；风险在独立复用 `chunk_document()` | `154` 行改 `return [text] if str(text).strip() else []` | 低 | ✅ |
| L-17 | `交付物/03-代码\数据准备\clean.py:173-179` 对照 `check.py:126-136` | 标题规范化口径分歧：clean **删除**全角空格，check **替换**为半角空格且不处理 `\u00a0`；check docstring 写「去除全角空格」而实现是替换 | `python %TEMP%\dp_review\t6.py`（B 段）→ `clean='关于全角空格的公告'` vs `check='关于 全角空格的公告'`（`相等? False`） | **当前不可达**（实测 709 篇标题含 U+3000/U+00A0 的为 0 篇）；属「复核器口径漂移」 | check 改按 config 语义删除，或抽成单一实现共用 | 低 | ✅ |
| L-18 | `交付物/03-代码\数据准备\event_first.py:327` | `time.strftime("%Y-%m-%dT%H:%M:%S+08:00")` 把硬编码 `+08:00` 贴在**本地时间**上 | `TZ=UTC python -c "import time;print(time.strftime('%Y-%m-%dT%H:%M:%S+08:00'))"` → 与真 `now(+8)` 差 8 小时 | `勘察/event_first_probe.json` 是**入库证据**；本机为 CST 时正确，换环境则时间整体错 8 小时且不留痕 | 用 `datetime.now(TZ)`（同仓 `fetch.py:99` 已有正确写法） | 低 | ✅ |
| L-19 | `交付物/03-代码\数据准备\fetch.py:901、943` | 公告路径 `json_body(resp)` 无守卫（无 `except FetchError`/`ValueError`），而新闻/政策/监管路径全都有（1158/1277/1381/1432/1525/…） | `python %TEMP%\dp_review\t7.py` → `cninfo_org_id`/`cninfo_announcements` 遇 FetchError 或非 JSON 响应即抛出 | 已封版数据不受影响（raw 落盘为 `tmp + os.replace` 原子写）；重跑时单家公司接口异常会中断整轮采集 | 两处包 `except (FetchError, ValueError)` 并登记 `ok=False` 后继续 | 低 | ◎ |
| L-20 | `交付物/03-代码\数据准备\config.py:546、562、634、307/403/620/630、588` | 死键与失实注释：`CLEAN["preserve_cjk_punctuation"]` 只被回显无人消费；`keep_line_patterns_after_drop` 全仓无人读；`INGEST_TIME=None` 注释称运行时写入但无人写；`TARGET_DOC_COUNT_V1=500` 无人消费且与《13》第107行记的 100 不一致 | 全仓 `grep` 各键只命中定义行 | 不参与计算；风险是后来者误以为开关生效 | 删除或注「未启用（占位）」；数字口径二者取一并注明 | 低 | ○ |
| L-21 | `工具\验收第4阶段文档.py:41、50-61` | 锚点失配静默产生错误结论：`re.search(...).group(1)` 漂移即 `AttributeError`（非 `[FAIL]`）；`find` 返回 `-1` 时切片是文件**尾部** 199 字，顺序核验基于错误内容 | 代码路径核对（当前《02》锚点在位，实跑退出码 0） | 文档一旦调整小标题，验收要么崩、要么基于尾部 200 字给出通过 | `m = re.search(...)`；`if not m: chk(False,…)`；`find` 为 `-1` 时判失败 | 低 | ○ |
| L-22 | `工具\验收第7阶段.py:1671-1674` | X3 声称扫描「参与比对的文件」，实际只看 `R["matrix"]`（`pre_experiment_matrix.jsonl`） | `R["matrix"]` 的来源在 `:597` 唯一赋值 | 断言名与断言体口径不一致，会让读者高估确定性证据覆盖面 | 对 `MIRROR_OUTPUTS` 逐文件扫描，或改标签为「矩阵文件不含…」 | 低 | ○ |
| L-23 | `工具\验收第7阶段.py:1940-1941、154` | 结论行的「未执行 0、SKIP 0」是**字面量**（同文件 `:1910-1914` 已算出 `unrun_count`/`skipped`）；`EXPECTED_STATIC_UNRUN=30` 定义后全文件未再引用 | `python -c "…;print([(i+1,l) for i,l in enumerate(s) if 'EXPECTED_STATIC_UNRUN' in l]);print(s[1939])"` | 目前该分支恰为 0（不致说谎），但新增一条可 SKIP 的检查后会自动撒谎 | 引用 `unrun_count`/`skipped` 变量；常量用于断言或删除 | 低 | ○ |
| L-24 | `工具\跨文档核验.py:308、455` | 白名单正则过宽，`(输入\|输出\|模板)\.` 前缀 token 一律跳过（用 `.search` 非 `.match`，不限定行首） | 见复现清单 §5.4 | 白名单本意是放过模板占位符，但「任何含『输入.』字样的 token」都免疫存在性检查 | 改 `WHITE.match(tok)` 并要求模板形态 `(输入\|输出\|模板)\.\{[^}]*\}` | 低 | ○ |
| L-25 | `工具\跨文档核验.py:276-283` | J 组正对照输入与断言由同一批常量构造，且无「对照未命中即抛异常」的硬守卫（相对 `执行助手.py:248-251` 的 `raise ControlFailed`） | 代码路径核对（当前实跑输出 `[OK ] J 组语境扫描器可用`） | 仅打印级断言；扫描器失效时不会被独立发现 | 正对照字符串改为独立常量并加硬守卫 | 低 | ○ |

### 提示（已声明行为或纯设计风险）

| 编号 | 文件:行号 | 说明 |
|---|---|---|
| N-1 | `交付物/03-代码\数据准备\check.py:139-145、614-615` | 检查 7 只判「存储字段」唯一，从不重算核对（`fingerprints_recomputed_here = 0`）。报告读数本身诚实（0 就是 0），但无法发现「指纹字段与正文不一致」。建议全量重算一次（709 次 sha256，耗时可忽略）。 |
| N-2 | `交付物/03-代码\数据准备\config.py:588` | `DEDUP["minhash_similarity_threshold"]=None` 是「第一版不做近似去重」的**已声明占位**，非缺陷，列此仅为清单完整。 |
| N-3 | `交付物/03-代码\检索\metrics.py:563-566` | 同 L-4，`--help` 已把「文件缺失时打印提示并跳过」写成契约，故按设计风险登记而非缺陷。 |

---

## 三、已验证为「无缺陷」的重点项（附证据，供下游免于重复检查）

### 3.1 字节级确定性（④：已交付《19》检索产出）

- 交付 6 文件的 sha256（本次现场重算）：
  ```
  input_manifest.json        7878B  59233ad0093b469f
  k_selection.json          28126B  ab62e0099a5878bc
  metrics_pre.jsonl         18086B  b33491f723cd33aa
  per_question_trace.jsonl 257253B  7839de9a1089404f
  pre_experiment_matrix.jsonl 18585B df9c05ad56b021df
  run_manifest.json         11832B  2dc3fd0acd065c44
  ```
- `per_question_trace.jsonl` 30 行，**无** `timestamp`/`elapsed`/`seconds`/`duration` 字段。
- 前次会话实测：`pipeline_trace_C.jsonl` 与 `_C_rerun.jsonl` sha256 完全相同（`789550341c88…`）；D（`2e8e811b6f2a…`）、E（`31396bf08174…`）同样两次运行逐字节一致。
- 本次 `pipeline.py --selftest` 复跑 10/10 通过，其中三条确定性自查全 `[OK ]`：
  ```
  [OK  ] 确定性：C 组两次运行 trace 逐字节一致  —— sha256 相同
  [OK  ] 确定性：D 组两次运行 trace 逐字节一致  —— sha256 相同
  [OK  ] 确定性：E 组两次运行 trace 逐字节一致  —— sha256 相同
  ```
- 阶段 6 侧：全部随机源定种/无随机——`write_graph.py:1005 rng = random.Random(int(spec["seed"]))`、`sample_eval_set.py` 用 `sha256(SEED:doc_id)` 破并列且自述「无随机数」；全仓无未定种 `random` 调用、无 `hash()` 依赖、无并发写同一文件。

### 3.2 无 BOM／换行正确（⑦）

- 14 个输入文件与 6 个交付产出全部 `BOM=False, CRLF=0`；所有 JSONL/JSON 落盘均为 `encoding="utf-8" + newline="\n"` 的 `tmp + os.replace` 原子写（CRLF 仅出现在二进制 FAISS 索引内，无关）。
- 阶段 5 交付数据目录内 `*.tmp`/`*.bak`/`__pycache__` **零残留**。

### 3.3 指标实现（⑥）

- `metrics.py` 四个指标函数都只吃 `chunk_id`；`evaluate_question_chunk_level` 四项同源于 `top = final[:k]`。
- `aggregate_chunk_level` 拒绝 `level != "chunk"`、`aggregate_doc_level_diagnostic` 拒绝 `level != "document"`——K 级与文档级**物理隔离**，不混算。
- 常态下无 `None` 行，故 `is not None` 过滤不会偷分母；`--selftest` 20/20 通过。
- 本次 `pipeline.py --selftest` 的契约断言全部 `[OK ]`：
  ```
  [OK  ] 断言 1：D 与 E 的最终证据集合逐题相等（成员与大小）  —— 不等题数 0
  [OK  ] 断言 3a：逐题 len(集合) == len(set(集合))  —— 证据与候选都不重复的题数 30／30
  [OK  ] 断言 3b：两路命中同一 chunk → 只出现一次且无额外加分  —— 命中条数=1、hit_by=['graph','vector']
  [OK  ] 断言 4：M < K 时题被保留、空缺记未命中、分母恒为 K  —— 收紧预算 360 → 题数 30（输入 30）
  [OK  ] 自查（g=0 退化）：分层键（g=0）与原字面口径的升序／降序／前 K 个逐题逐元素相同  —— 不一致题数 0
  [OK  ] 自查（B-16 g 边界）：g=0／g=-1／g=K+1 三个越界值在库入口一律抛错  —— 越界抛错 3／3
  自证结论：10／10 条通过
  ```

### 3.4 `g=0` 退化性（静态推理）

层级常量 `LAYER1_VECTOR_TIER=0 < LAYER3_VECTOR_FILL_TIER=2 < LEFTOVER_GRAPH_TIER=3`，与 `LEGACY_VECTOR_TIER=0 < LEGACY_GRAPH_TIER=1` 在升序/降序与前 K 截取上逐元素同序；由 §3.3 的「g=0 退化自查」实测确认。

### 3.5 范围内宽泛 `except` 全部非静默（①）

对四个目录逐条核对 32 处宽泛 `except`：全部有**登记/重抛/哨兵**语义，无一处「吞掉后继续」。典型：
- `工具\抽检助手.py:203`、`工具\标注助手.py:255`：`except BaseException: ...; raise`（清理后**重抛**）。
- `交付物/03-代码\数据准备\check.py:500`、`工具\验收第5阶段数据.py:775`：异常一律计入「不一致」（保守方向）。
- `交付物/03-代码\抽取与图谱\extract.py:634-636`：`_retryable` 分类（APIConnection/APITimeout/RateLimit 或 429/5xx 才重试），非可重试或超次即 `raise`；`extract.py:659` 的 `raise RuntimeError("不应到达")` 为真防御。
- 其余为 stdout 编码守卫或返回 `""`/`"unknown"` 哨兵。**无 `except: pass`**（仅 `阶段02` 两处，已超出本次范围）。

### 3.6 FAISS 索引加载（⑧）

`config.read_faiss_index` 独立重测成功，`ntotal=5018`。（首次 `pipeline.py --selftest` 因 `MemoryError: std::bad_alloc` 失败，系并发下的瞬时内存压力；其后台复跑 10/10 通过。）

### 3.7 阶段 6 抽取失败处理（①）

`extract.py` 逐篇失败记入 `失败 N 篇` 汇总（`main` 第 1746 行），非静默；`_invoke` 的退避重试有上限（`max_retries`）；缓存命中即不重算。`run_all.py:216-217` 阻断「`--force-extract` 未同时给 `--allow-api-calls`」。

### 3.8 只读性与写入边界（⑦⑧）

- `工具\` 下 `验收第4阶段文档.py`、`验收第5阶段数据.py`（默认档与 `--with-idempotence` 的镜像重跑）、`验收第6阶段.py`、`验收第7阶段.py`（static 档）、`跨文档核验.py` 实跑后工作区**零改动**（本次 `git status --short` 为空可证）。
- `验收第7阶段.py --profile static` 三态记账正确，且**明示不得宣称全部通过**（退出码 2）——与 H-4 形成鲜明对照。
- `抽检助手.py`：固定 `SEED`＋`sha256(种子:item_id)` 破并列；`strip_timestamps()` 在自检比对前剥掉时间戳键；`sys.addaudithook` 实审计对 `_全量`/`图谱导出` 的访问。
- `执行助手.py`：`scan()` 正对照机制正确（`control_hits == 0` 抛 `ControlFailed`）；`patch()` 逐锚点校验并在写入前整体中止。
- 全仓交付目录内**无**硬编码盘符写死路径（唯一一处是 `交付物/03-代码\数据准备\勘察\撤销中间轮次产出.py:19`，为一次性勘察脚本）。

### 3.9 阶段 5 编号体系与版本关系（只读实测）

- v2.0 的 456 篇在 v2.1 中**缺失 0 篇、正文指纹变化 0 篇**；新增 253 篇 `doc_id` 落 1139~2106；四类 `DOC_ID_BLOCK` 无越块；`chunk_id ↔ (doc_id, chunk_index)` 双射 `5018/5018`。
- v2.0 的 491 篇 raw **逐字节带入**（唯一差异是追加型日志 `_fetch_log.jsonl`）。
- v2.0→v2.1 的 456 篇 `ingest_time` 全部不同——**已排除为假阳性**（《13》第305行声明 `ingest_time` 是「按本轮运行写入的单一时间戳」）。

### 3.10 死代码标记（⑩）

全四个目录 grep `if False:`／`if 0:`／`# TODO|FIXME|XXX|HACK` **命中 0 处**。（死分支/死参数另见缺陷表 L-6、L-7、L-10、L-23。）

---

## 四、未覆盖范围

1. **未发任何 HTTP 请求、未调用任何模型 API**（按要求）。因此以下路径只做静态审查或打桩验证：
   - `交付物/03-代码\数据准备\fetch.py`（2769 行）四类来源的真实解析容错（HTML/PDF 结构变化、限流实测）、PDF 抽取细节；
   - `交付物/03-代码\抽取与图谱\extract.py`／`auto_annotate*.py` 的真实调用路径（真实编码、缓存重放）；
   - `工具\核验知网题录.py` 的采集与比对路径（只逐行阅读，无联网证据）。
2. **未在真实数据上重跑完整管线**（只读纪律），故「阶段 5 同一输入两次运行逐字节一致」未被本审查实测（仅阶段 6 与阶段 7 的自证覆盖了确定性）。
3. `交付物/03-代码\抽取与图谱\write_graph.py` 的 Neo4j 写入段（`replay.cypher` 之后的落库）无数据库可验证，只做静态审读。
4. **`auto_annotate.py:417` 的计数竞态未构造运行时演示**（需 4 线程实跑接口），仅代码路径级论证（L-12）。
5. **M-16（`验收第7阶段.py` K 网格越界）未构造复现**（需篡改题集，超出只读范围），仅代码路径证据；L-7、L-9、L-10、L-14、L-19、L-20、L-21、L-22、L-23、L-24、L-25 同为代码路径证据，未实跑触发。
6. `--profile pilot` 路径、`fetch.py --force` 全量重取未跑。
7. 本次审查的**分工**：`交付物/03-代码\检索\` 由我逐行审读并实跑取证；`交付物/03-代码\数据准备\`、`工具\`、`交付物/03-代码\抽取与图谱\` 由三条并行子审查线覆盖，其中全部「高」项与关键「中」项已由我第一手复核（见缺陷表「复核」列：✅ 实跑 / ◎ 静态核对 / ○ 代理证据）。

---

## 五、已执行的复现命令清单

> 全部命令跑完工作区 `git status --short` 均为空。完整日志留存在 `%TEMP%\audit_s7\`。

### 5.1 交付物/03-代码\检索

```bash
# M-1 建名索引重复
cd 交付物/03-代码\检索
python -c "import graph_query as gq;g=gq.default_graph();print(g.resolve_node('平安银行')['node_ids']);print('dup keys=',sum(1 for v in g.by_name.values() if len(v)!=len(set(v))),'/',len(g.by_name))"
# 交付 trace 重复统计（29/30 题）
python -c "import json;rows=[json.loads(l) for l in open(r'../交付物/05-系统实现/RAG检索系统/检索产出/per_question_trace.jsonl',encoding='utf-8')];…"   # 见日志 pickk.log 同目录

# M-2 pick_k 反例
python - <<'PY'
import sys; sys.argv=["pre_experiment.py"]; import pre_experiment as pe
…（见正文 M-2）
PY

# L-1 entity_match
python - <<'PY'
import sys; sys.argv=["p"]; import pipeline as P
class G: nodes={"000001":{"name":"平安银行"}}
docs={1:{"company_list":"平安银行","publish_time":"2026-05-01"}}; chunks={1:{"content":"本文讨论钢铁行业。"}}
print(P.evidence_sort_factors(G(),{"doc_id":1,"chunk_id":1,"graph_path_ordinals":[0],"graph_relations":["R"]},{"000001"},docs,chunks))
PY

# L-2 / L-13 -O 下 assert 消失
python -c "print(__debug__)"
python -O -c "print(__debug__)"
python -c "import os,re;d=r'交付物/03-代码\检索';[print(f,i) for f in os.listdir(d) if f.endswith('.py') for i,l in enumerate(open(os.path.join(d,f),encoding='utf-8').read().splitlines(),1) if re.match(r'\s*assert\b',l)]"

# L-4 metrics --from-trace 缺文件
python metrics.py --from-trace "C:/Users/15129/AppData/Local/Temp/audit_s7/does_not_exist.jsonl"; echo $?

# L-5 自测残留
python -c "import os;d=r'../交付物/05-系统实现/RAG检索系统/_工作底稿/_metrics_selftest';print(os.path.isdir(d), os.listdir(d) if os.path.isdir(d) else '')"
```

### 5.2 交付物/03-代码\抽取与图谱

```bash
# H-1/H-2 离线建档产出不可导入 + 默认落点为跟踪文件
python 交付物/03-代码/抽取与图谱/build_company_aliases.py --no-network --out "%TEMP%/audit_s7/crn_offline.py"
python -c "t=open(r'%TEMP%/audit_s7/crn_offline.py',encoding='utf-8').read();print('null 次数=',t.count('null'));exec(compile(t,'m','exec'),{})"
python -c "import sys;sys.path.insert(0,r'交付物/03-代码\抽取与图谱');import company_registered_names as m;print(dict(m.SOURCE_COUNTS),len(m.REGISTERED_NAMES))"
git ls-files --error-unmatch 交付物/03-代码/抽取与图谱/company_registered_names.py
git check-ignore 交付物/03-代码/抽取与图谱/company_registered_names.py; echo $?

# H-3 覆盖层落点
python -c "import sys;sys.path.insert(0,r'交付物/03-代码\抽取与图谱');import config;print(config.time_backfill_paths('v21_v1_2')['overlay'])"

# M-8 裸文件名 --out 崩溃
cd %TEMP%/audit_s7/cwd
python "C:/Users/15129/Desktop/毕业设计/交付物/03-代码/抽取与图谱/auto_annotate_compare.py" --out "对照报告.md"; echo $?
```

### 5.3 交付物/03-代码\数据准备

```bash
python %TEMP%\dp_review\t6.py     # L-15/16/17 汇总（请求计数、空块、标题口径）
python %TEMP%\dp_review\t5.py     # M-10 空池缺键（165 次站内检索）
python %TEMP%\dp_review\t4.py     # M-11 run_all NameError(ex)
TZ=UTC python -c "import time;print('strftime:',time.strftime('%Y-%m-%dT%H:%M:%S+08:00'))"   # L-18
python %TEMP%\dp_review\t7.py     # L-19 公告路径无守卫
python 交付物/03-代码\数据准备\run_all.py --only chunk --dir %TEMP%\dp_case   # 退出码透传（工作区只读）
```

### 5.4 工具

```bash
python 工具/验收第6阶段.py --no-replay                 # H-4：EXIT=0、SKIP 20、结论「验收通过」
python 工具/验收第6阶段.py --export-dir "Z:/zz_nope"    # H-4 异常通道
python -c "import io;s=io.open(r'工具/验收第6阶段.py',encoding='utf-8').read().split(chr(10));print(s[1612])"   # M-12
python 工具/验收第5阶段数据.py                          # M-13：99/99 通过（含 5 条未执行）
python -c "marks=('不引入','不采用','不使用','不进入','不按','排除','避免','严禁','禁止','不得','不再','无','未','非','之外','而不');[print(repr(l),'命中=',[m for m in marks if m in l]) for l in ['本系统以向量索引为主存储并对外提供查询。','集群规模已扩展，无需额外部署；本系统以向量索引为主存储。']]"   # M-14
python 工具/验收第5阶段数据.py --dataset "%TEMP%/audit/empty_ds2"   # M-15（需先造零行数据集）
python -c "import io;s=io.open(r'工具/验收第7阶段.py',encoding='utf-8').read().split(chr(10));print([(i+1,l) for i,l in enumerate(s) if 'EXPECTED_STATIC_UNRUN' in l]);print(s[1939])"   # L-23
python 工具/验收第7阶段.py --profile static             # 对照：EXIT=2、明示未执行 30
```

### 5.5 基线（本次实测，工作区零改动）

```bash
python 工具/跨文档核验.py        # 结论：全部通过   EXIT=0
python 工具/验收第4阶段文档.py    # 结论：全部通过   EXIT=0
python 工具/验收第5阶段数据.py    # 99/99 通过       EXIT=0
python 交付物/03-代码/检索/pipeline.py --selftest --trace-dir "%TEMP%/audit_s7"   # 10/10 条通过   EXIT=0
python 交付物/03-代码/检索/metrics.py --selftest                                   # 20/20 通过
git status --short               # （空）
```

---

## 六、总评

四个目录、313 个 `.py` 文件的审查未发现任何**污染已封版数据集 / 已交付《19》产物 / 已入库证据**的确定性缺陷；高危 4 项全部位于「重跑 / 子集跑 / 离线跑 / 验收记账」等非封版路径，其中最该优先修的是：

1. **H-4（`验收第6阶段.py`）**——放行闸门静默失效，且同一作者在 `验收第7阶段.py` 已用 `[ENV ]`/`[UNRUN]` 三态记账做对了，可直接照搬；
2. **H-1/H-2（`build_company_aliases.py`）**——离线口径产出不可用模块却退出 0，且默认落点是 git 跟踪的冻结数据模块；
3. **H-3（`extract_event_time.py`）**——覆盖层可被 `--limit` 静默截断且下游无守卫。

其次为 **M-1**（`graph_query.py` 建名索引不去重，已实际污染交付 trace 29/30 题）与 **M-2**（`pick_k` 可越预算，真实数据未触发但属潜伏缺陷）。
