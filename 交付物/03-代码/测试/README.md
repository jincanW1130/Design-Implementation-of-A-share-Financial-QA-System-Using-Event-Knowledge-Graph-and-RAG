# 交付物/03-代码\测试\ —— 单元测试（pytest，离线）

> **一句话**：本目录是本项目**唯一的单元测试**入口，测的是**系统行为**（五步契约、四项检索
> 指标、答案三段拼装、错误码映射这些纯函数与纯逻辑），**不是**"文档—产物一致性"。
> 与 `工具\` 下的验收脚本**分工不重叠**，两者都要跑。

对应外部评审 **P1-12**（"全仓库无任何单元/集成测试、无 pytest；验收脚本测的是文档—产物一致性，
不测系统行为"）与评审建议的四组覆盖面（K/N/g 选取、evidence 裁剪五步契约、assemble 三段拼装、
错误码映射）；同时直接支撑论文 **6.4 功能测试**一节的材料。

---

## 一、怎么跑

```powershell
# 全量（一次进程里加载检索／问答／后端三套同日名模块）
python -m pytest 交付物/03-代码\测试 -q

# 逐文件（分开跑也必须全过——这是对"四个同名 config.py 串味"的实测防线）
python -m pytest 交付物/03-代码\测试\test_0_module_isolation.py -q
python -m pytest 交付物/03-代码\测试\test_a_five_step_contract.py -q
python -m pytest 交付物/03-代码\测试\test_b_retrieval_metrics.py -q
python -m pytest 交付物/03-代码\测试\test_c_answer_assembly.py -q
python -m pytest 交付物/03-代码\测试\test_d_backend_errors.py -q

# 一键跑上面 5 条并汇总退出码
powershell -File 交付物/03-代码\测试\运行测试.ps1
```

* 中文输出在 GBK 控制台会乱码，**不是失败**：跑之前设 `$env:PYTHONIOENCODING='utf-8'`
  （`运行测试.ps1` 已设好；该脚本带 UTF-8 BOM，PS 5.1 下才能正确解析中文注释）。
* 依赖：`pytest==9.1.1`（本机实测版本，已登记进根 `requirements.txt`）。
* 测试**完全离线**：不联网、不调大模型、不连 MySQL／Neo4j、不起后端、不写数据集；
  只有两条用例**只读**取 `交付物/04-数据与知识图谱/数据准备\数据集\v2.1\` 的语料（文件缺失时 `pytest.skip`）。
  "离线"不是声明而是**硬保证**：`conftest.py` 的会话级 `forbid_network` 夹具装了审计钩子，
  任何 socket 连接／域名解析／HTTP 请求当场抛错（守卫自身也有负向标定用例
  `test_network_guard_is_armed`）。
* 对产品目录**一个字节都不写**：`conftest.py` 设 `sys.dont_write_bytecode = True`，
  按文件路径加载产品模块时连 `__pycache__` 都不落（同《检索 README》第二条"对输入只读"）。
  实测：跑完一轮 `交付物/03-代码\检索\`／`交付物/03-代码\问答\`／`交付物/03-代码\后端\` 下被写过的 `.pyc` 数为 **0**。
* `交付物/03-代码\测试\pytest.ini` 里带 `-p no:cacheprovider`，跑完不往工作区落 `.pytest_cache\`
  （实测：`rootdir` 与 `configfile` 都定在 `交付物/03-代码\测试`，`交付物/03-代码\测试\` 下无 `.pytest_cache`）。

### 本机实测读数（2026-10-05 实跑）

| 运行方式 | 结果 |
| --- | --- |
| `python -m pytest 交付物/03-代码\测试 -q` | **121 passed**（通过 121／失败 0／跳过 0／xfail 0） |
| 逐文件 5 次 | 11 ＋ 15 ＋ 22 ＋ 15 ＋ 58 ＝ 121 passed，退出码全为 0 |
| `交付物/03-代码\测试\运行测试.ps1`（1 次全量 ＋ 5 次逐文件） | 6 次运行的退出码全为 0 |
| 逆序一次性跑（d→c→b→a→0） | 121 passed |
| 从别的工作目录用绝对路径跑 | 121 passed |

---

## 二、目录与文件

| 文件 | 作用 |
| --- | --- |
| `_bootstrap.py` | **测试专用模块加载器**：按文件路径加载产品模块并给唯一模块名，加载期把 `sys.modules["config"]` 显式指向本组件那一份，加载完原样恢复（见第三节） |
| `conftest.py` | 夹具：`synthetic_graph`（真实 `GraphQuery` ＋ 临时目录里的合成 `nodes.csv`／`edges.csv`）、`fake_searcher`（向量检索的进程内替身）、`retrieval_mod`／`retrieval_cfg` |
| `pytest.ini` | 测试自己的运行约定（根目录定为 `交付物/03-代码\测试`；不写缓存；`xfail_strict=false`） |
| `test_0_module_isolation.py` | 第 0 组（11 例）：**测试自身的隔离机制**——各组件绑定的 `config` 就是它自己那一份、加载后不残留、"离线守卫"确实会拦下网络事件，以及一条**负向标定**（隔离一失效，`pipeline.py` 会拒绝加载） |
| `test_a_five_step_contract.py` | A 组（15 例）：Top-K 五步契约与分层保留顺序 |
| `test_b_retrieval_metrics.py` | B 组（22 例）：四项检索指标的边界 |
| `test_c_answer_assembly.py` | C 组（15 例）：答案三段确定性拼装、0 跳标注、引用越界、token 账 |
| `test_d_backend_errors.py` | D 组（58 例）：14 个错误码与 `_classify_failure` 的措辞映射 |
| `运行测试.ps1` | 一键入口（全量 ＋ 逐文件，汇总退出码） |

---

## 三、为什么不串味（四个同名 `config.py`）

`交付物/03-代码\检索\config.py`、`交付物/03-代码\问答\config.py`、`交付物/03-代码\数据准备\config.py`、
`交付物/03-代码\抽取与图谱\config.py` 是**四个同名模块**；这四个目录下的产品代码内部一律写
`import config`（裸名），靠"自己所在目录排在 `sys.path` 最前"解析到**自己那一份**。
`交付物/03-代码\问答\run_answer.py` 开头第 21～22 行 **已记载**这个陷阱，并因此对检索侧一律走
**子进程桥接**。

**本目录采用的做法：按文件路径加载 ＋ 唯一模块名 ＋ 显式管住 `sys.modules["config"]`。**

1. `_bootstrap.load_module("检索", "pipeline.py")` 用
   `importlib.util.spec_from_file_location` 按**文件路径**执行产品模块，模块名是唯一的
   `_dsh_检索_pipeline` 这类名字——**不占用任何裸名**，因此"检索的 `metrics` 与问答的
   `check_inputs` 同名"这类碰撞不可能发生；
2. 执行期间把 `sys.modules["config"]` 置为**本组件自己的 `config` 模块**（同样是按路径加载
   的 `_dsh_检索_config`），于是产品代码内部的 `import config` **必然**命中本组件那一份；
   同时把本组件目录插到 `sys.path[0]`，让产品代码内部的同目录导入
   （`pipeline.py` 的 `from graph_query import …`、`assemble.py` 的 `import prompt as prompt_mod`）
   命中本组件；
3. 执行结束**原样恢复** `sys.path` 与 `sys.modules["config"]`，不污染后续加载；
4. 后端按**常规模块名**导入（`errors`／`services.qa_service`，`services\` 是命名空间包），
   这样 `services.qa_service` 里的 `import errors` 与测试拿到的 `errors` 是**同一份实例**；
   `db`／`errors`／`services` 刻意留在 `sys.modules`（另两个组件没有同名模块），裸名 `config`
   仍然还原。

**为什么这样能避免串味**：产品模块在**导入期**就把 `config` 绑进了自己的模块全局
（全仓库已确认没有函数级的 `import config`），所以"导入之后 `sys.modules["config"]` 是谁"
不影响已加载的模块；而每次加载时它**被显式指定**，解析结果与"先加载谁、后加载谁"无关。
第 0 组把这条理由落成了断言：每个产品模块的 `module.config.__file__` 必须等于它自己目录下的
`config.py`（`pytest` 里分开跑、一起跑、逆序跑都是同一读数）。

**负向标定**（第 0 组的 `test_pipeline_refuses_a_foreign_config`）：故意把
`sys.modules["config"]` 换成问答侧那一份，`交付物/03-代码\检索\pipeline.py` 第 107～108 行的守卫
（"导入到的 config.py 不在本脚本同目录，拒绝继续"）会立刻以 `SystemExit` 暴露——
即"隔离如果失效，本套测试会硬失败而不是悄悄换掉参数来源"。

---

## 四、覆盖了什么

### 第 0 组 · 测试自身的隔离机制（10 例）

四个同名 `config.py` 互不相同、产品模块绑定的就是自己那一份、`_Isolated` 退出后
`sys.path`／`sys.modules["config"]` 原样恢复、后端 `qa_service.errors is errors`
（不出现两份实例）、以及上面那条负向标定。

### A 组 · Top-K 五步契约与分层保留顺序（15 例，`交付物/03-代码\检索\pipeline.py`）

| 用例 | 断的是什么 |
| --- | --- |
| `test_merge_dedup_counts_once_and_adds_no_score` | 两路命中同一 `chunk_id` 只算一个证据、`hit_by=[graph, vector]`、`similarity`／`vector_rank` 原样、**不加分**（无 score／boost／weight 字段） |
| `test_time_filter_happens_before_merge` | 用合成图构造"先过滤／后过滤结果不同"的用例（105 号块：图谱侧被剔除、向量侧仍命中）——**这是对判据的标定**（它只调原语，不经过 `run_question`），实现顺序的防线在下一条 |
| `test_run_question_end_to_end` | 端到端一题（合成图 ＋ 检索替身）看 trace 段落读数：图谱侧 5 个候选 → 合并只吃**过滤后**的 2 个（同时给出"先合并"会得到的读数 5，证明判据能区分两种实现）；`dual_hit=1`；`candidate_diff_removed=[102,103]`（105 不在差集里＝向量侧不受图谱侧过滤影响）；最终集合 `[105,101,999,104]`、`graph_evidence_in_final=[104]`、`≤K`、预算内 |
| `test_run_question_D_and_E_share_the_same_evidence_set` | 《02》第12.6节／《18》表 18-E 的硬断言：D 与 E 的最终证据集合**必然相同**（且本用例的顺序确实不同，非空断言） |
| `test_trim_drops_remote_paths_first` | 预算超限时**先裁与问题实体无关的远端图谱路径**（`anchor_distance=2` 的在前）；只由被裁路径支撑的图谱侧新增块随之出局；从问题实体直接出发的路径是最后手段 |
| `test_trim_drops_chunks_from_tail_in_layered_order` | 再按**分层保留顺序从尾部往前**裁文本块（裁 `22→5→4→21`、留 `[1,2,3,20]`）；并给出**负向标定**：换回"原字面口径"的排序键会裁掉 `[22,21,20,5]`、把图谱侧块挤出集合 |
| `test_layered_retention_order_and_tie_break` | 三层定义 ＋ 第二层**相似度并列按 `chunk_id` 升序**（刻意逆序输入）＋ 四档标号顺序不可颠倒 ＋ 输入顺序不影响结果 |
| `test_keep_top_k_takes_the_first_k_of_the_layered_order` | 第④步取分层顺序的前 K 个 |
| `test_keep_top_k_keeps_questions_whose_candidates_are_fewer_than_k` | 候选不足 K：题目保留、空缺记未命中（分母恒为 K） |
| `test_keep_k_precedes_group_sort_and_D_equals_E` | 第④步**先于**第⑤步；D＝分层顺序、E 只改顺序，**集合相同、顺序不同** |
| `test_g0_degenerates_to_legacy_key` | `g=0` 时分层键与 `legacy_priority_key` **升序／降序／前 K 个**逐元素同序 |
| `test_low_level_g_out_of_range_raises` / `test_run_entry_g_lower_bound_is_one` | 越界 g 一律抛错、不静默夹取（B-16）；运行入口的合法域 `1 ≤ g ≤ K` |

### B 组 · 四项检索指标（22 例，`交付物/03-代码\检索\metrics.py`）

完全命中／部分命中；**空 gold**（分母为 0 → 记 0 且不抛异常）；**空 final**；
**gold 全不在 Top-K**；**gold 恰好在第 K 位**（算命中）与**第 K+1 位**（不算）；
**gold 数 > K**（Recall 分母是 gold 总数）；**重复 `chunk_id`**（集合语义，含整型／字符串
视为同一块，以及"集合输入没有顺序、MRR 因此只能取到两个值"的口径说明）；
`Precision@K` **分母恒为 K**（M<K 时空缺记未命中、不删题）；
**`|final| > K` 时四项指标都只看前 K 个**（B-15 回归 ＋ 一条把 `mrr` 钉成旧读数的负向标定）；
逐题行可独立重算 ＋ 固定 8 位精度；非法 K 抛错；
**文档级诊断与 chunk 级不得混算**（两级聚合互相拒绝对方的行、键集不相交）；
按题取算术平均。

### C 组 · 答案三段拼装与 token 账（15 例，`交付物/03-代码\问答\`）

| 用例 | 断的是什么 |
| --- | --- |
| `test_compose_answer_is_byte_identical_across_two_calls` | 四段结构（`回答`／`证据来源`／`知识图谱路径`／`数据截至与判定区间`）、**同样输入两次拼装逐字节一致**、段头各出现一次、来源类型标签正确 |
| `test_compose_answer_does_not_rewrite_the_model_body` | 装配层不改写模型正文 |
| `test_zero_hop_uses_the_fixed_marker_and_invents_no_path` | 0 跳必须出现固定标注「本次回答未使用图谱扩展」，段落正文**恰为**该标注，`graph_path` 为空、无 `depth=`、无 `->` ——**不得生成虚构图谱路径** |
| `test_graph_used_renders_the_path_and_omits_the_marker` | 用了图谱扩展时渲染路径与三元组，且不出现"未使用"标注 |
| `test_prompt_blocks_omit_the_graph_block_when_not_used` | Prompt 第 5 区块在 `graph_used` 为假时**整体缺省**（不留空标题） |
| `test_citation_gate_flags_out_of_range_marks` | `[证据n]` 越界（含 `n=0`）判定 |
| `test_gate_fails_on_out_of_range_citation` | 用**真实语料**前两块组装一题：正文引用 `[证据3]`（m=2）→ `failures` 含 `citation_out_of_range`、`passed=False`；引用 `[证据1][证据2]` 则不失败 |
| `test_source_type_mapping_covers_every_real_category` | 来源类型映射表的键**必须等于语料里的真实 `category` 取值**（2026-09-29 同类缺陷：把「财经新闻」写成近义词「新闻」，整类证据静默落到兜底类） |
| `test_final_set_token_account_follows_the_final_evidence_set` | token 账按**最终证据集合（保留 K 之后）**复算，且与 `budget_trim.after`（保留 K 之前）**可区分** |
| `test_record_to_trace_row_never_falls_back_to_budget_trim` | **P0-新① 回归防线**：`record_to_trace_row()` 不得再用 `budget_trim.after` |
| `test_record_to_trace_row_refuses_to_guess_without_chunks` | 没有 chunks 可复算时**报错退出**，不猜 |
| `test_assemble_case_is_deterministic_and_guards_the_token_account` | 两次装配 `prompt.sha256` 相同、证据不重排；**把账换成"保留 K 之前"的口径 → 装配账目守卫 `SystemExit`**（就是 3004 的现场） |
| `test_assemble_case_rejects_evidence_beyond_k_or_out_of_corpus` | 证据条数 > K、证据块不在语料里 → 报错退出 |
| `test_date_gate_accepts_allowed_sources_and_flags_the_rest` | 日期来源可核（证据正文／标题／发布时间／图谱载荷／截止日／窗口端点）；晚于截止时间的日期**只统计、不计失败** |
| `test_forbidden_terms_are_a_fixed_constant` | 禁词表是固定常量；"明确不收"的事实性叙述词与禁词表不重叠 |

### D 组 · 后端错误码映射（58 例，`交付物/03-代码\后端\errors.py` ＋ `services\qa_service.py`）

* **14 个错误码**逐码检查：message 非空且**互不重复**（语义单一）、HTTP 状态与登记值一致、
  码段语义（1xxx 输入／2xxx 资源／3xxx 依赖与上游／4xxx 凭据权限）；
* **只有 2002 是"不是错误的正常业务状态"**（HTTP 200）；
* 响应体键集合**恰为** `{code, message}`（14 个码逐码参数化），`detail` **只进日志**，
  连异常字符串里都不带 detail；
* 未知码／非数值码一律兜底到 9999 的 message 与 HTTP 状态，响应体仍回原码；
* `HTTP_STATUS_TO_CODE` 的取值必须在码表内、且**往返一致**；
* `_classify_failure` 的四档措辞逐条参数化钉住（守卫 3 条／索引 7 条／图谱 7 条／模型 7 条／
  未归类 3 条）＋ **判定优先级**（守卫 → 索引 → 图谱 → 模型）＋ 返回值必在码表内；
* **2026-10-04 修掉的真缺陷**：含裸词「图谱」的日志（如 `图谱段BAD`）**不得**被判成 3001、
  且带真实图谱标识时仍判 3001。

---

## 五、没覆盖什么（如实登记）

| 没覆盖的部分 | 为什么没覆盖 |
| --- | --- |
| **需要起服务的集成路径**：25 个业务接口、六张表导入、问答接口的错误码端到端、限流、CORS、`/api/health` | 要 MySQL／Neo4j／后端进程，属**第 9 阶段门禁**（`工具\验收第9阶段.py`，58 行验收标准；服务未启动时判"环境未就绪"、退出码 2）。单元测试保持离线才能随时复现 |
| **FastAPI 异常处理器装配**（`errors.install_exception_handlers`：`ApiError`／请求校验／`HTTPException`／未捕获异常四条路径） | 需要建应用或走 TestClient（另有依赖），属上一条的覆盖面；本文件只测**纯逻辑**（码表、映射、响应体构造） |
| **真实向量检索链路**（FAISS 索引 ＋ 本地 Embedding 前向）与真实图谱导出物上的 30 题端到端 | 要加载 ~5018 条索引与模型快照，属第 7 阶段门禁（`工具\验收第7阶段.py` 的只读镜像重跑）。A 组用"合成图 ＋ 检索替身"把**契约**测掉，替身只回确定性读数 |
| **大模型调用与答案生成质量**（`answer.call_model`、门禁的整体通过率、重复一致率） | 要联网调模型；判据（门禁函数）本身已由 C 组覆盖，模型侧读数归第 8／10 阶段（`工具\验收第8阶段.py`、`阶段10-测试与对比实验\工具\`） |
| **前端（Vue）单测** | 本任务范围是 Python pytest；评审 B-06 建议的 vitest 用例（`api.js` 的 `ApiError` 分支）**未做**，如实登记为待办 |
| **数据准备／抽取与图谱两个组件的纯函数** | 本次按评审 P1-12 点名的四组覆盖面做（检索／问答／后端）；数据库准备侧的 `chunk.py`／`dedup.py` 等尚未纳入 |
| 端到端"文档—产物一致性" | 那是 `工具\` 下验收脚本的职责，两者**分工不重叠**、都要跑 |

---

## 六、已观察、但**未**判为缺陷的几处（留痕）

1. **`pipeline.keep_top_k()` 在"候选数 ≤ K"分支里按输入顺序返回**，而不是分层保留顺序；
   第⑤步 `order_evidence()` 会再排一次，D 组的呈现顺序与最终证据集合都观测不到差异
   （A 组端到端用例断言 `evidence == [105,101,999,104]` 仍成立）。属**潜在不一致**，
   本次按纪律**不改产品代码**，在此登记由决策者处置。
2. **`_classify_failure` 依赖中文措辞**（评审 **P1-9**）：同义但换了措辞的日志会落到 9999
   未归类。这不是"错"，源码 docstring 明确写了兜底取 9999（判不出类别就如实说"不知道"）；
   D 组的 `test_classify_failure_depends_on_chinese_wordings_a_known_debt` 把它落成**可执行
   读数**：测试在这里的作用是**防止措辞与优先级静默漂移**，不是证明归类正确。
3. **仓库根目录的 `.pytest_cache\`**（`C:\Users\15129\Desktop\毕业设计\.pytest_cache\`）：
   创建时间 2026-10-04 22:21，`v\cache\nodeids` 内容为 **`[]`（空）**——本套测试任何一次运行
   都会收集 121 条，且 `pytest.ini` 关了缓存插件；实测跑一轮后该文件的 `LastWriteTime`
   **未变**，故它**不是本套测试产生的**（`交付物/03-代码\测试\` 下没有 `.pytest_cache`）。
   它不出现在 `git status` 里，是因为 pytest 自带的 `.gitignore`（内容 `*`）把它自忽略了。
   本目录按纪律**不删别人可能正在用的东西**，在此登记，由决策者决定是否清理。
4. **一条测试职责边界的自我更正**（由独立复核发现，已改）：A 组的
   `test_time_filter_happens_before_merge` 原先的措辞声称"断言实现取的是先过滤"，但它只调用
   原语、不经过 `run_question`，因此它对**实现顺序**没有约束力（把 `run_question` 改坏它仍绿）。
   现已改成"对判据的**标定**"，并在 `test_run_question_end_to_end` 里补上"先合并会得到的读数 5"
   与 trace 实测值 2 的对照，使**实现顺序**这条纪律有真正的防线。

**本次 xfail 数：0。** 即：按 P1-12 点名的四组契约写下来的断言里，**没有一条**落在
"实现与冻结口径不符"上；三条历史真缺陷（B-15 的 MRR 截断、P0-新① 的 token 账口径、
2026-10-04 的错误码误标）都已修复，本次把它们各自固化成**回归防线**（含负向标定）。
若日后有人改回旧实现，对应用例会立即变红。

---

## 七、给论文 6.4「功能测试」的用法

* 一张表：**用例组 → 被测文件 → 覆盖的契约 → 用例数 → 结果**（本文件第四节的表可直接引用）。
* 三条可写进正文的**取证方式**：
  1. **确定性**：同一输入两次装配的 Prompt `sha256` 相同、答案三段逐字节一致；
  2. **契约可区分**：每条关键断言都附了"换回旧口径/错误顺序就会不同"的**负向标定**
     （A 组的时间过滤先后、裁剪顺序、D=E 集合；B 组的 MRR 截断；C 组的 token 账口径；
     D 组的裸词「图谱」），说明这些用例不是恒真的空断言；
  3. **隔离可证**：第 0 组用"产品模块绑定的 `config.__file__`"与一条负向标定，
     证明"分开跑与一起跑"读到的是同一份参数来源。
* 边界口径（空 gold、gold 在第 K 位、M<K 的分母、`|final|>K`）可直接作为 6.4 的**边界测试**
  小节素材。
