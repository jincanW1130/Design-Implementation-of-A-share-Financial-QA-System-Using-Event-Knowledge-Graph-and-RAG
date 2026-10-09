# C 线：数据与产物的对抗性复核（第 7 阶段前七阶段交付复审）

> 复核对象：`交付物/05-系统实现/RAG检索系统\检索产出\`（6 件）、`交付物/05-系统实现/RAG检索系统\预实验问题集\`（6 件）、
> `交付物/05-系统实现/RAG检索系统\_工作底稿\`（只读留痕）；上游只读输入：`交付物/04-数据与知识图谱/数据准备\数据集\v2.1\`
> 与 `交付物/04-数据与知识图谱/事件抽取与知识图谱\图谱导出\v2.1_v1_2\`。
> 复核纪律：项目树**零写入**（`git status --porcelain` 复核为 0 行）；一切读写用 Python（`encoding='utf-8'`）；
> **未调用任何模型 API**（未重放第三方通道、未新调接口；千帆／智谱／Kimi 的缓存只读）。
> 唯一可写目录：`C:\Users\15129\AppData\Local\Temp\re7_C\`（本报告与全部复核脚本、日志均在此）。
> 术语纪律：全文不写出被禁用的四字连写术语（一律写「向量索引」或「向量检索组件」）。
> 复核时间：2026-09-28（本机时区 Asia/Shanghai）。

---

## 结论摘要

**确认缺陷 6 项；驳回（假阳性）6 项；无法判定 4 项。**

一句话答案：**第 7 阶段的那些数字，绝大多数能被独立重算出来，而且是逐字节重算出来的**——
11 个输入指纹、4 个产物的两次重跑（`run1 == run2 == 工作区`）、四项指标的 30 个逐题值与 4 个平均值、
9 格网格的文本块中位数与四项指标、预算 3600 的推导、K=5 的 gold 排除、K=15 的预算排除与饱和 Δ=0、
g∈{0,1,2,3,5} 五点曲线、第三方复核的一致率与 usage、上游 11 项读数——**全部一致，0 处数值不符**。
缺陷集中在**文档与字段的口径滞后**、**一个题集字段名与内容的错位**、**验收工具明细里一处数字含义错误**、
以及**验收日志与现场输出不一致**（本机重跑 full 出现 W2 失败，直接原因是 OpenBLAS 内存分配失败）。
评测参照集（30 题 gold）的**硬度**：抽 15 题回原文，15 题都能支撑参考答案；gold 块 100% 在 `chunks.jsonl`
内且 doc 一致；81 条锚点 100% 逐字命中；12 道时间题 100% 落在现场重算的 66 篇时间子集内。
需要挑刺的地方是：**gold 的"多余块"两处**（PE-13、PE-22，抬高 Recall 分母）、
**`gold_evidence_rule` 字段写的是候选口径而不是 gold 口径**（15/16 题的 gold 是"文档内全部文本块"的真子集）、
**`说明.md`／`题目模板.md` 两处记载与题集实际字段不一致**，以及**没有人工抽检**（题集自己已如实登记，但
《18》非目标 7 的原文写的是"检索 gold 必须由人工构造"）。

---

## 一、确认缺陷表

| 编号 | 严重度 | 落点（文件:行/字段） | 问题 |
| --- | --- | --- | --- |
| D1 | 中 | `预实验问题集\说明.md` 第二节；`预实验问题集\题目模板.md` 第三节 4 | gold 条数分布写成"2 条 11 题、4 条 1 题"，与 `questions.jsonl` 实际的"2 条 10 题、4 条 2 题"不符（PE-26 补块后未同步） |
| D2 | 中 | `预实验问题集\说明.md` 第四节；`题目模板.md` 第五节 | 两文档仍写 `gold_verified_by=decision_maker_ai_verify_v1`、`gold_review_status="待作者逐题确认"`；30 题实际字段已是 `third_party_model_review_v1` 与新状态串 |
| D3 | 低 | `questions.jsonl` 字段 `gold_evidence_rule` | 16 题写"文档内全部文本块"，其中 15 题的 gold 是该文档全部块的**真子集**（PE-12 为 2/29）——该字段实际是"候选抽取口径"，字段名会被读成"gold 生成规则" |
| D4 | 中 | `工具\验收第7阶段.py`（`REPLAY["env_removed"]`，W2 与 AB2 明细行） | "摘除的凭据类环境变量 N 个"报的是**环境变量总数**而不是摘除数：`REPLAY["env_removed"], _ = stripped_env()` 取到的是 env dict，removed 被丢弃 |
| D5 | 中 | `_工作底稿\_T12\验收第7阶段_full_stdout.txt`（与 `_static_`、`_keep-tmp_`） | 记录与现场输出不一致：A2 行《19》字数行数变了（28095 字符/562 行 → 28882/573，《19》mtime 晚于日志）；W2 在记录里是"退出码全 0=True"，现场三次重跑 full 均失败（见 D6／K1） |
| D6 | 低 | `预实验问题集\questions.jsonl` 的 PE-13、PE-22 的 gold 列表 | 两处含"同一事件的另一篇公告重复表述"块（PE-13 的 1279000 与 1207001 同属 7-27 回购方案；PE-22 的 1274001 四个姓名职务已被 1337000 覆盖），按 `题目模板.md` 第三节 3 的自我口径属可删块——使 Recall 分母偏大（保守方向） |

### D1 复现命令与原始输出

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_docs.py
```

```text
questions.jsonl 实际 gold 条数分布 = {1: 10, 2: 10, 3: 3, 4: 2, 5: 2, 6: 1, 7: 2}
[说明.md]      gold 证据条数 1～8 的范围内，本集取到 **1 条 10 题、2 条 11 题、3 条 3 题、4 条 1 题、5 条 2 题、6 条 1 题、7 条 2 题**
[题目模板.md]  本集 30 题的条数分布为 1 条 ×10、2 条 ×11、3 条 ×3、4 条 ×1、5 条 ×2、6 条 ×1、7 条 ×2
```

旁证（改动来源与时间顺序，`Get-Item | % LastWriteTime` 等价物由 Python 取 mtime）：

```text
2026-09-27 21:56:32 说明.md
2026-09-27 21:56:24 题目模板.md
2026-09-27 23:58:33 questions.jsonl      ← PE-26 gold 2 块→4 块发生在此之前（收口报告）
```

建议修法：把两处分布改成实际的 `1 条 ×10、2 条 ×10、3 条 ×3、4 条 ×2、5 条 ×2、6 条 ×1、7 条 ×2`，
并加一句"PE-26 补块后由 11/1 变为 10/2"的变化说明。

### D2 复现命令与原始输出

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_docs.py
```

```text
questions.jsonl 实际 gold_verified_by 取值 = {'third_party_model_review_v1'}
questions.jsonl 实际 gold_review_status 取值 = {'经两家第三方模型盲标复核（kimi＋zhipu）＋决策者回原文裁定；非人工逐题确认，人工抽检未做，复核结论不等于事实'}
[说明.md]     每题 `gold_verified_by` 写 `decision_maker_ai_verify_v1`，`gold_review_status` 写"待作者逐题确认…"
[题目模板.md]  每题的 `gold_verified_by` 一律写 `decision_maker_ai_verify_v1`，`gold_review_status` 写"待作者逐题确认"
```

建议修法：按 `收口报告（千帆剥离与T8重绑）.md` 已登记的字段口径改这两段，或明确标注"本段为收口前口径，
现行字段见 `questions.jsonl`（`prior_verified_by` 保留了原值）"。

### D3 复现命令与原始输出

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_gold.py
```

```text
B. gold_evidence_rule 与 gold 的自洽（16 题写「文档内全部文本块」）
PE-01  doc=1001  gold块=1   该文档总块=2   缺=1 ['1001000'] <-- rule 与 gold 不一致
PE-12  doc=1082  gold块=2   该文档总块=29  缺=27 ... <-- rule 与 gold 不一致
PE-19  doc=1533  gold块=1   该文档总块=15  缺=14 ... <-- rule 与 gold 不一致
PE-10  doc=1127  gold块=3   该文档总块=3   缺=0
（16 题中 15 题 gold ⊊ 该文档全部块；唯一相符的是 PE-10）
```

旁证（该字符串的真实含义）：

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 -c "import io;s=io.open(r'交付物/03-代码\检索\build_questions.py',encoding='utf-8').read();i=s.find('def derive_candidate_chunks');print(s[i:i+380])"
  → if kind == "doc_chunks": ... return out, "文档内全部文本块"（候选集合，人工核验前）
```

建议修法：字段改名为 `gold_candidate_rule`，或把值写成"候选＝文档内全部文本块；gold＝经回原文核验的子集"。

### D4 复现命令与原始输出

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 -c "import os,re;pat=re.compile(r'(API[_-]?KEY|SECRET|ACCESS[_-]?TOKEN|AUTH[_-]?TOKEN|MOONSHOT|DASHSCOPE|ZHIPU|OPENAI|DEEPSEEK|QIANFAN|KIMI|GLM|BAIDU|ERNIE|ANTHROPIC|GEMINI)',re.I);m=sorted(n for n in os.environ if pat.search(n));print('env count',len(os.environ));print('matched',len(m))"
```

```text
env count 81
matched 0
```

而现场重跑 `工具\验收第7阶段.py` 的明细行是：

```text
[FAIL] W2 镜像里摘除密钥后全链路（六步 ＋ 两次三轮）退出码全 0，运行记录打印 0 次调用
       实测 退出码全 0=False（10 条命令）；打印 0 次调用 2 处；摘除的凭据类环境变量 84 个
```

81（本机环境变量）+ 3（`stripped_env` 追加的 `PYTHONIOENCODING`／`HF_HUB_OFFLINE`／
`TRANSFORMERS_OFFLINE`）= 84，与"摘除 84 个凭据类变量"的字面含义不符；记录日志里的 85 同理。
源码证据：

```text
REPLAY["env_removed"], _ = stripped_env()        # ← 第一个返回值是 env（dict），removed 被丢弃
... len(R.get("env_removed") or [])              # ← 明细里按「摘除数」打印
```

建议修法：写成 `REPLAY["env_removed_names"], REPLAY["env"] = stripped_env()`，明细打印
`len(R["env_removed_names"])`。

### D5 复现命令与原始输出

现场重跑（两次捕获＋一次带内存采样），命令：

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t7_capture.py
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t7_diff.py
```

```text
验收第7阶段_full_stdout.txt（记录 174 行） vs t7_full_mine.txt（现场 178 行）：差异行 14
    -  [OK  ] A2 《19》非空且含实质内容  实测 28095 字符、562 行
    +  [OK  ] A2 《19》非空且含实质内容  实测 28882 字符、573 行
    -  [OK  ] W2 …退出码全 0=True（10 条命令）；打印 0 次调用 2 处；摘除的凭据类环境变量 85 个
    +  [FAIL] W2 …退出码全 0=False（10 条命令）；打印 0 次调用 1 处；摘除的凭据类环境变量 84 个
    -  最终：检查项 72 项，通过 72，失败 0
    +  最终：检查项 72 项，通过 70，失败 2
```

文件时间顺序（说明 A2 差异的来源）：

```text
2026-09-28 00:49:39  19-第7阶段产出文档（RAG检索系统）.md   ← 晚于下面两份日志
2026-09-28 00:33:22  _工作底稿\_T12\验收第7阶段_full_stdout.txt
2026-09-28 00:35:53  _工作底稿\_T12\验收第7阶段_static_stdout.txt
```

建议修法：把 full 日志重新生成一次（`--keep-tmp` 留痕），或者在日志开头写明"本日志对应《19》的哪一版
SHA-256"；W2 的复现问题见 D6／K1。

### D6 复现命令与原始输出

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_review.py PE-13 PE-22
```

```text
PE-13 gold: [1025002, 1100002, 1207001, 1207002, 1279000]
  chunk 1207001（doc 1207）: 2026 年7 月27 日召开第四届董事会第二次会议，审议通过了《关于以集中竞价交易方式回购公司股份的议案》…不低于10 亿元…不超过20亿元…不超过103元/股
  chunk 1279000（doc 1279）: 《…回购报告书》…回购股份金额：不低于10 亿元（含），不超过20 亿元（含）…回购股份价格：不超过103 元/股
PE-22 gold: [1200000, 1231000, 1274001, 1337000, 1355000]
  chunk 1337000（doc 1337）: 董事长谢永林，董事冀光恒、郭晓涛、付欣、蔡方方、项有志、杨志群…共12人
  chunk 1274001（doc 1274）: 董事长谢永林、董事郭晓涛、付欣和蔡方方回避表决   ← 四人及其职务已被 1337000 覆盖
```

判定：PE-13 的 1279000 与 PE-22 的 1274001 属"同一事件／同一批人名的另一篇公告重复表述"，
删去后参考答案仍被完整支撑；按 `题目模板.md` 第三节 3「同一事件在两篇公告里的重复表述只保留真正被引用的块」
可再收紧。**不影响四项指标的算法正确性**，只影响 gold 大小与 Recall 分母（方向是偏保守）。
建议修法：由作者裁定是否删块；若保留，在 `gold_verify_note` 里写明"保留另一篇公告块的理由"。

---

## 二、独立重算对照表

全部读数为**我现场重算**；命令见第三节对应小节（脚本在 `…\Temp\re7_C\`，日志在 `…\re7_C\logs\`）。

| 读数 | 产物值 | 我的重算值 | 一致？ |
| --- | --- | --- | --- |
| `input_manifest.json` 11 个输入 sha256／字节数 | 11/11 记录 | 11/11 现场重算相同 | ✓ |
| `input_manifest.json` 自身 sha256 | 59233ad0…（`run_manifest`） | 59233ad0… | ✓ |
| `run_manifest` 四产物 run1/run2/workspace sha256 | 4 条各 3 值 | 现场逐条相同；run1==run2==工作区 | ✓ |
| 四产物两次重跑（pipeline→pre_experiment→metrics ×2） | 4 个文件 | 逐字节相同 | ✓ |
| 四项指标平均值 Recall／Precision／MRR／CER | 0.69230159／0.15／0.65925926／0.56666667 | 完全相同 | ✓ |
| 四项指标 30 个逐题值 | 30 行 | 30 行全等（含 n_gold／n_final／n_hit） | ✓ |
| 网格 K×N 文本块中位数（6 格抽查） | 1603.5／3191.5／3219.5／3218.5／4826／4788.5 | 同 | ✓ |
| 预算基准中位数 → B | 3191.5 → 3600 | ceil100(1.10×3191.5)=3600 | ✓ |
| 9 格＋选定格行数 | 10 行 | 10 行（9 格 round1 ＋ 1 行 round2） | ✓ |
| 每格 N ≥ K | 全部 True | 20/50/100 ≥ 5/10/15 | ✓ |
| K=5 被 gold 约束排除 | 最大 gold 7 | 现场统计 30 题最大 gold = 7 | ✓ |
| K=15 被预算排除（第一轮中位数） | 4826 > 3600 | 现场重跑 K=15/N=20 非约束中位数 = 4826 | ✓ |
| 饱和判定 Δ（K10→K15，B=3600） | 0.0 | 0.56666667−0.56666667 = 0 | ✓ |
| g 曲线 g∈{0,1,2,3,5} 四项 | 5 档 | 5 档逐项全等（g=3 起 CER 掉到 0.5333/0.5） | ✓ |
| 30 题 gold 块在 `chunks.jsonl`、doc 一致 | — | 0 异常（70 块全部命中） | ✓ |
| 每题 gold 数 ≤ 选定 K=10 | — | 最大 7 ≤ 10 | ✓ |
| 81 条 `gold_verify_anchors` | — | 81/81 在 gold 内且引文逐字命中 | ✓ |
| 12 道时间题 gold 文档 ∈ 66 篇 | 12/12 | 12/12（现场由 nodes/edges 重算 66 篇） | ✓ |
| 标签覆盖 3 类 × 3 档 × 时间有无 | 18 格 | 18 格全 ≥1（关系型×2×有 = 4 题） | ✓ |
| `EVIDENCED_BY` 条数 | 1111 | 1111 | ✓ |
| 语义边（非 EVIDENCED_BY） | 1625 且全带 source_chunk_id | 1625／1625 | ✓ |
| 第三方跨厂商一致率（kimi＋zhipu） | 29/30 = 0.9667，分歧 PE-29 | 29/30，分歧 `['PE-29']` | ✓ |
| 三线留痕一致率 | 28/30 = 0.9333，分歧 PE-06、PE-29 | 28/30，分歧 `['PE-06','PE-29']` | ✓ |
| 用量 usage（确认口径／留痕口径） | 63,602／109,977／173,579；60,073；233,652 | 逐家重算完全相同 | ✓ |
| 台账／报告里 9 个 sha256 | 9 条 | 9/9 现场一致 | ✓ |
| `questions.jsonl` 复核字段 ↔ 缓存／台账 | — | 0 异常（verdict／answer_supported／model／consistent／confirmed_lines／excluded） | ✓ |
| T11 链上六脚本"密钥／网络字样 0 处" | 6/6 = 0 | 6/6 = 0（正对照 > 0） | ✓ |
| 上游 2802 节点／2736 边 | 2802／2736 | 2802／2736 | ✓ |
| 事件 1100／无时间 544 | 1100／544 | 1100／544（49.5%） | ✓ |
| ≥2 日期的文档 | 66 篇 | 66 篇 | ✓ |
| 孤立节点 | 435 | 度=0 的节点 435 | ✓ |
| 待消歧提及 | 1070（1063＋7） | `unresolved.jsonl` 1070，reason 分布相同 | ✓ |
| HCONF 公司节点 | 12 | 12（全部无 stock_code） | ✓ |
| `BELONGS_TO` 有效期全空 | 14/14 | 14/14 | ✓ |
| `工具\验收第7阶段.py` full 结果 | 72/72 通过、退出码 0 | 现场 61～70/72，W2 失败、退出码 1 | ✗（见 K1） |

---

## 三、八件事的逐项命令与原始输出

### 1）输入只读：11 个指纹 ＋ `run_manifest` ＋ 入库纪律

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t1_hashes.py
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t1b_workspace_sha.py
```

```text
documents            bytes=4496547/4496547 ok=True sha=c838c608c20060ad ok=True
chunks               bytes=5322875/5322875 ok=True sha=2202cbf8e3915598 ok=True
faiss_index          bytes=10276909/10276909 ok=True sha=4052ed9a251eb0c8 ok=True
vector_map           bytes=284916/284916 ok=True sha=e11569c8ba67e63d ok=True
build_meta           bytes=964/964 ok=True sha=5d886d080d103088 ok=True
dataset_meta         bytes=3108/3108 ok=True sha=41c82bc43008eaba ok=True
nodes_csv            bytes=708043/708043 ok=True sha=04f2ac227e9595e2 ok=True
edges_csv            bytes=131275/131275 ok=True sha=e86f86d99bb1b227 ok=True
replay_cypher        bytes=727503/727503 ok=True sha=8cdb68d0782b04a8 ok=True
graph_stats          bytes=24818/24818 ok=True sha=443f437aa3f164ab ok=True
human_confirmation   bytes=6428/6428 ok=True sha=a17268f8c0694e6b ok=True
input_manifest all_ok field = True ; recomputed mismatches = 0
recorded: 59233ad0093b469f41a2323aa5ffcbb3e335ba339d7b6d44c26707cfa53770e5
actual  : 59233ad0093b469f41a2323aa5ffcbb3e335ba339d7b6d44c26707cfa53770e5  match=True
k_selection.json  ws_recorded=ab62e0099a5878bc actual=ab62e0099a5878bc match=True
metrics_pre.jsonl ws_recorded=b33491f723cd33aa actual=b33491f723cd33aa match=True
per_question_trace.jsonl ws_recorded=7839de9a1089404f actual=7839de9a1089404f match=True
pre_experiment_matrix.jsonl ws_recorded=df9c05ad56b021df actual=df9c05ad56b021df match=True
```

入库纪律（`git check-ignore` ＋ `git ls-files`，PowerShell 只做 git 调用、不解析 JSON/文本）：

```text
$ git check-ignore -v "交付物/03-代码/抽取与图谱/config.local.json" "交付物/05-系统实现/RAG检索系统/_工作底稿"
.gitignore:47:config.local.*	"交付物/03-代码/抽取与图谱/config.local.json"
.gitignore:48:交付物/05-系统实现/RAG检索系统/_工作底稿/	"交付物/05-系统实现/RAG检索系统/_工作底稿"
$ git ls-files "交付物/03-代码/抽取与图谱/config.local.json"     → 0 行
$ git ls-files "交付物/05-系统实现/RAG检索系统/_工作底稿" | Measure-Object -Line  → Lines 0
$ git status --porcelain | Measure-Object -Line        → Lines 0（项目树零改动）
$ git ls-files "交付物/05-系统实现/RAG检索系统/检索产出"           → 6 件（全部入库，未被忽略；check-ignore 退出码 1）
$ git ls-files | Measure-Object -Line                  → 303
```

### 2）确定性：四个产物各重生一遍 ×2

```
# 先把项目树镜像到临时根（只读复制），再照 交付物/03-代码\检索\ 的既有入口跑两轮
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\mirror.py
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t2_rerun.py
```

```text
== run run1 ==
  [pipeline.py] rc=0 8.65s   [pre_experiment.py] rc=0 22.53s   [metrics.py] rc=0 0.06s
== run run2 ==
  [pipeline.py] rc=0 9.08s   [pre_experiment.py] rc=0 23.76s   [metrics.py] rc=0 0.07s

file                         ws       run1     run2     r1==r2==ws
per_question_trace.jsonl     7839de9a 7839de9a 7839de9a True
pre_experiment_matrix.jsonl  df9c05ad df9c05ad df9c05ad True
k_selection.json             ab62e009 ab62e009 ab62e009 True
metrics_pre.jsonl            b33491f7 b33491f7 b33491f7 True
结论：四个产物两次运行互相一致，且与工作区交付件逐字节一致。
```

参数来源：`k_selection.json` 的 `selected = {"K":10,"N":20,"context_token_budget":3600,"g":2,"group":"C"}`；
`pipeline` 缺省即经 `config.require_fixed(...)` 读 `config.RETRIEVAL`，与 `k_selection` 的选定值一致
（`pre_experiment` 会在漂移时直接报错退出）。差异位置：**无差异**（逐字节相同）。

### 3）四项指标：自己实现、逐题对拍（不 import `metrics`）

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t3_metrics.py
```

```text
K in metrics meta = 10 ; k_selection K = 10
qid    recall    precision mrr       complete
PE-01  1.0       0.1       1.0       1.0
PE-04  0.28571429 0.2     1.0       0.0
PE-11  0.0       0.0       0.0       0.0
PE-16  0.5       0.1       0.16666667 0.0
PE-26  0.25      0.1       0.11111111 0.0
…（30 题逐题打印，mismatches: 0）
== 平均值对拍 ==
recall_at_k                 0.69230159  0.69230159  True
precision_at_k              0.15        0.15        True
mrr                         0.65925926  0.65925926  True
complete_evidence_recall_at_k 0.56666667 0.56666667 True
== 边界与分母体检 ==
empty gold in questions: 0 ; empty final in trace: 0
final set sizes (min..max): 8 .. 10 | <K count: 6
precision identity check: file precision == n_hit/K for all rows: True
avg precision == mean(n_hit/K): 0.15
```

**Precision@K 的分母恒为 K**：6 题最终集合只有 8～9 块（M<K），文件里这 6 题的 `precision_at_k`
仍等于 `n_hit/10`（例：PE-26 `n_final=9, n_hit=1, precision=0.1`），我按 `hits/K` 重算逐题相同。
**空 gold／空 final**：本题集 0 题空 gold、trace 0 题空 final；现成实现对两者的口径是"四项一律记 0、
不抛异常、不补位"，我用 `metrics.py --selftest` 复核了这一分支：

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 交付物/03-代码\检索\metrics.py --selftest
  [OK  ] M<K 分母：Precision@K == 0.1（分母是 10 不是 2）   → M=2  K=10  命中=1  Precision@K=0.1
  [OK  ] 空 gold／空 final：四项一律返回 0 且不抛异常   → 空gold=(0.0, 0.0, 0.0, 0.0)  空final=(0.0, 0.0, 0.0, 0.0)
  自证：18／18 通过 → 全部通过
```

### 4）9 格网格与定值推理

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t4_grid.py
```

```text
== 独立重跑：网格读数（C 组）==
case             K    N     median_txt  mean_ev      CER         metrics
r1_K5_N20        5    20    1603.5      5.0          0.4         {"recall_at_k":0.58730159,"precision_at_k":0.24,"mrr":0.65833333,"complete_evidence_recall_at_k":0.4}
r1_K10_N20       10   20    3191.5      10.0         0.56666667  {"recall_at_k":0.69230159,"precision_at_k":0.15,"mrr":0.65925926,...}
r1_K10_N50       10   50    3219.5      10.0         0.56666667
r1_K10_N100      10   100   3218.5      10.0         0.56666667
r1_K15_N20       15   20    4826.0      15.0         0.63333333
r1_K15_N50       15   50    4788.5      15.0         0.63333333
B3600_K15_N20    15   20    3268.0      10.23333333  0.56666667  {"recall_at_k":0.67809524,"precision_at_k":0.09333333,...}
g0               10   20    3134.0      9.76666667   0.56666667  {"recall_at_k":0.66142857,"precision_at_k":0.13666667,"mrr":0.65555556,...}
g1               10   20    3088.0      9.73333333   0.56666667  {"recall_at_k":0.68563492,"precision_at_k":0.14666667,"mrr":0.65888889,...}
g2               10   20    3102.5      9.76666667   0.56666667  {"recall_at_k":0.69230159,"precision_at_k":0.15,"mrr":0.65925926,...}
g3               10   20    3098.5      9.63333333   0.53333333  {"recall_at_k":0.67563492,"precision_at_k":0.14333333,"mrr":0.65972222,...}
g5               10   20    3100.5      9.5          0.5         {"recall_at_k":0.62896825,"precision_at_k":0.13,"mrr":0.65555556,...}

== 对照产物 ==
matrix K=5  N=20  median=1603.5   mean_ev=5.0    CER=0.4
matrix K=10 N=20  median=3191.5   mean_ev=10.0   CER=0.56666667
matrix K=10 N=50  median=3219.5   mean_ev=10.0   CER=0.56666667
matrix K=10 N=100 median=3218.5   mean_ev=10.0   CER=0.56666667
matrix K=15 N=20  median=4826     mean_ev=15.0   CER=0.63333333
matrix K=15 N=50  median=4788.5   mean_ev=15.0   CER=0.63333333
budget_rule median_text=3191.5 raw=3510.65 B=3600
saturation scan 15 : {"K":15,"N":20,"context_token_budget":3600,"g":2,"mean_evidence_size":10.23333333,
                      "median_text_tokens":3268,"metrics":{...,"complete_evidence_recall_at_k":0.56666667,...},
                      "questions_holding_K_blocks":0}
g_curve primary rows:
  g=0 flags={'complete_evidence_recall_at_k': '=', 'mrr': '=', 'precision_at_k': '=', 'recall_at_k': '='}
  g=1 flags={...'mrr': '+', 'precision_at_k': '+', 'recall_at_k': '+'}
  g=2 flags={...'mrr': '+', 'precision_at_k': '+', 'recall_at_k': '+'}   ← 采纳值
  g=3 flags={'complete_evidence_recall_at_k': '-', ...}  ← CER 掉到 0.53333333，判劣
  g=5 flags={'complete_evidence_recall_at_k': '-', 'mrr': '=', 'precision_at_k': '-', 'recall_at_k': '-'}
```

判定：

- **10 行**：`pre_experiment_matrix.jsonl` 恰 10 行 = 9 格（K∈{5,10,15}×N∈{20,50,100}，`round1_nonbinding`）
  ＋ 1 行选定格（K=10／N=20／B=3600，`round2_selected`）；每格 `N_geq_K=True`。
- **K=5 被 gold 约束排除**：本题集最大 gold 数 = 7（现场统计，见第四节的逐题数），`gold_constraint.K_covers_all_gold=false`，
  `n_questions_gold_leq_K=27`（3 题 gold > 5）。
- **K=15 装不进预算**：排除依据是**第一轮非约束预算**下 K=15／N=20 的文本块中位数 4826 > 3600（我独立重跑同为 4826）；
  第二轮把 K=15 放进 B=3600 跑出来的 3268 是**被裁剪后**的占用，不是判据——两者不矛盾。
- **饱和 Δ≤0**：同预算 B=3600 下 K=10 的 CER 0.56666667 与 K=15 的 0.56666667 之差 = 0.0（我独立重跑两格都复现），
  K=10 即"满足预算前提下饱和的最小 K"。
- **预算规则**：`ceil100(1.10 × 3191.5) = ceil100(3510.65) = 3600` ✓（基准格＝满足 gold 约束的最小 K=10 与其最小可行 N=20）。
- **g 曲线**：g∈{0,1,2,3,5} 五点四项全部复现；"四项不劣于 g=0"在 g=1／g=2 成立、g=3／g=5 因 CER 下降不成立，
  取最大且 ≥1 → g=2，与 `k_selection.selected.g` 一致。

### 5）题集与 gold 的硬度

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_gold.py
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_review.py PE-01 PE-04 PE-06 PE-10 PE-11 PE-12 PE-13 PE-14 PE-19 PE-20 PE-22 PE-24 PE-26 PE-29 PE-30
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t5_260b.py
```

```text
A. gold 证据块 存在性 / doc 一致性 / 数量
问题数: 30 | 异常条目: 0
逐题 gold 数: {PE-01:1, PE-02:1, PE-03:1, PE-04:7, PE-05:2, PE-06:4, PE-07:2, PE-08:2, PE-09:1, PE-10:3,
              PE-11:7, PE-12:2, PE-13:5, PE-14:6, PE-15:3, PE-16:2, PE-17:2, PE-18:1, PE-19:1, PE-20:1,
              PE-21:1, PE-22:5, PE-23:2, PE-24:2, PE-25:1, PE-26:4, PE-27:2, PE-28:1, PE-29:2, PE-30:3}
最大 gold 数: 7 | 声明 gold_evidence_count 与列表长度一致: True

C. gold_verify_anchors：锚点块是否在 gold 内 + 引文是否能在该块原文中逐字命中
锚点总数: 81 | 异常: 0

D. 时间约束 12 题：gold 文档是否都落在「≥2 个不同 event_time 日期」的文档集合
EVIDENCED_BY 边数: 1111
事件数: 1100 | 有 event_time 但无 EVIDENCED_BY 文档: 0
≥2 日期文档数: 66
PE-03 … PE-30 共 12 题：all_in_ge2=True（12/12）
```

标签覆盖（现场统计，来自 `questions.jsonl`）：

```text
task_type: {'关系型': 12, '事实型': 9, '事件型': 9}
gold_hop_depth: {2: 12, 0: 9, 1: 9}
time_constraint: {'无': 18, '有': 12}
3×3×时间有无 = 18 格全部 ≥1（关系型×2 跳×有 = 4 题，其余 17 格各 1～2 题）
```

**抽 15 题回原文的逐题判定（依据片段见 `t5_review.py` 的原始输出）**：

| 题号 | 判定 | 关键依据（原文片段） |
| --- | --- | --- |
| PE-01 | 成立 | 1001001「行权期有效期为2026年9月11日-2027年1月25日，2026年9月11日开始行权」 |
| PE-04 | 成立 | 1339008～1339012 五段候选人简历（郑弘孟／黄德才／杨秋瑾／许兴仁／丁肇邦）＋1279014／1279015（许兴仁、林奂汝、张瑞雄、白家南） |
| PE-06 | 成立 | 1163001「第六期…发行总额为人民币70亿元」＋1021001「第七期…45亿元」 |
| PE-10 | 成立 | 1127000～1127002 五项议案的名称与表决情况逐项列出 |
| PE-11 | 成立 | 1193000～1193006 被担保人基本情况表序号 1～10 的公司名逐块出现 |
| PE-12 | 成立 | 1082002「于2026年9月7日签订了持续关联交易第八补充协议…期限至2027年12月31日止」 |
| PE-13 | 成立（1 块可视为多余） | 1207001 给出 7-27 方案要素、1207002 首次回购、1100002 八月累计、1025002 实施完毕；1279000 与 1207001 同属方案事件的另一篇公告 |
| PE-14 | 成立 | 1244002（7 月累计 200.13 万股）、1294001（40.00→39.74 元／股）、1294002（7-17 首次 25.30 万股）、1320005、1364000、1364002 |
| PE-19 | 成立 | 1533005「中国电信集团有限公司、中国电信股份有限公司与公司…不存在关联关系…是公司的长期客户」 |
| PE-20 | 成立 | 1082021「持有本公司69.95%股份（含间接持股）的股东，与其联系人构成本公司的关联人」 |
| PE-22 | 成立（1 块可视为多余） | 1337000 十二人名单（含谢永林、冀光恒、郭晓涛、付欣、蔡方方、项有志）、1200000（高鹏）、1355000（吴雷鸣）、1231000（冀光恒＝行长）；1274001 的四人已被 1337000 覆盖 |
| PE-24 | 成立 | 1257009「回购价格上限由573元/股调整为571.60元/股…自2026年8月10日」＋1257010 计算式收尾 |
| PE-26 | 成立 | 1502001／1533001 给出两份框架协议全称，1502005／1533005 给出买卖双方与签署时间（8-3／7-13） |
| PE-29 | 成立 | 1001000（政策依据）＋1001001（两个行权期均自 2026-9-11 起行权） |
| PE-30 | 成立 | 1106000（政策依据）、1106001（专户开立与过户登记）、1106002（15,772,385 股、0.21%、锁定期 2026-9-3～2028-9-2） |

**"不足／多余"结论**：**0 题"不足"**（15 题都能从 gold 原文片段直接得到参考答案要素）；
**2 题各 1 块可视为"多余"**（PE-13 的 1279000、PE-22 的 1274001），见 D6——方向是抬高 gold 分母，
不会把不成立说成成立。

**有没有把第 6 阶段 260 条抽取参照集当成检索测试集或出题素材**：

```text
参照集条目 = 260（不同块 260、来自 260 篇不同文档）
30 题 gold 块 = 70 ｜ gold 文档 = 38 ｜ 题面文档 = 38
gold 块 ∩ 参照集块 = 8 [1050006, 1106000, 1127000, 1163000, 1183000, 1193000, 1207002, 1355000]
题目文档 ∩ 参照集文档 = 16（260/709 的基线是 36.7%，题集 38 篇里 16 篇 = 42%）
检索最终证据（30 题并集 239 块）∩ 参照集块 = 20
```

判定：**没有当检索测试集**（测试集是 `questions.jsonl`，与 260 条无同源关系）；
**无法证明把它当出题素材**——gold 块与参照集的交集 8/70（11.4%）低于"按 260 条块数占比 5.2%"的两倍，
题集侧也没有任何引用 260 条的字段；《18》非目标 7 的原文是"**可以作出题素材**，引用时保持'模型参照集'定性；
检索 gold 必须由人工构造"，`说明.md` 第三节 3 的表述与之一致。
唯一需要作者注意的仍是 **"检索 gold 必须由人工构造"** 与题集自述"AI 构造＋两家模型盲标复核、人工抽检未做"
之间的落差（题集已如实登记，见 K2）。

### 6）第三方复核的可复现与性质

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t6_review.py
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t6_wording.py
```

```text
A. 逐家 verdict 分布 / usage / attempts
kimi    n=30 verdicts={'成立': 29, '部分成立': 1} attempts=30 usage total_tokens=63602
zhipu   n=30 verdicts={'成立': 28, '部分成立': 2} attempts=32 usage total_tokens=109977
qianfan n=30 verdicts={'成立': 27, '部分成立': 3} attempts=30 usage total_tokens=60073
两家合计(确认):total_tokens=173579 | 三家合计(留痕)=233652
台账 usage_totals 一致: True ; usage_totals_all_lines_trace 一致: True

B. 跨厂商一致率
确认口径(kimi+zhipu): 29/30 = 0.9667 ; 分歧=['PE-29']
留痕口径(三家): 28/30 = 0.9333 ; 分歧=['PE-06', 'PE-29']

C. questions.jsonl 的 third_party_review 字段 ↔ review.jsonl / 台账
逐题字段异常条数: 0

D. 报告/台账里与复核相关的 sha256 与现场是否一致
kimi/review.jsonl 报告=660bb66b003c 现场=660bb66b003c 一致
zhipu/review.jsonl 报告=1359c5cdc800 现场=1359c5cdc800 一致
kimi/summary.json、zhipu/summary.json、cross_vendor.json、cross_vendor_all_lines_trace.json、
第三方复核台账.json、qianfan/review.jsonl、qianfan/summary.json … 8 条全部一致（共 9 条）

E. 现场 cross_vendor.json ↔ 我的重算
cross_vendor.json 头: {"comparable_questions":30,"consistency_rate":0.9667,"consistent_questions":29,
                       "note":"…它是**模型间一致率**，不是人工一致率、不是金标准。","scope":["kimi","zhipu"]}
cross_vendor per_question 与我的重算不一致: []
all_lines per_question 与我的重算不一致: []
```

口径确认：**确认口径 = kimi ＋ zhipu 两家**；千帆按作者指示剥离，逐题保留 verdict／模型名并标
`excluded_per_author: true`／`excluded: true` 与剥离原因，`usage` 只在"留痕口径"并列登记——
与 `第三方复核报告.md` 的线数说明、台账的双口径字段完全对上。

**"模型复核有没有被写成人工确认／金标准"逐字查（含否定语境判断）**：

```text
第三方复核报告.md  人工确认×3／人工一致率×3／人工复核×1／金标准×4
   → 全部落在否定语境（"不是人工抽检、不是金标准""不是人工一致率""不得被表述成人工复核或人工确认"）
     或自检禁用词清单（FORBIDDEN_IN_PROMPT 里的 `人工确认` 字样）
第三方复核台账.json 人工确认×1／金标准×1 → note："…也不是人工确认、不是金标准。人工抽检未做。"（否定语境）
questions.jsonl     人工确认×2 → PE-17／PE-26 的 gold_verify_note："人工确认写入的 HCONF 公司节点"
   （指图谱节点的写入方式，不是 gold 复核；收口报告 ⑤-8 已如实登记这两处残余）
```

结论：**未发现把模型复核写成人工确认或金标准的表述**；两处残余的具体语境可辩、且已被作者向文档登记。

### 7）`_工作底稿\` 的留痕与 `_T11`／`_T12` 原始日志

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t7_t11.py
```

```text
== T11 声称①：链上脚本 0 处密钥／网络字样（含正对照）==
check_inputs.py    hits=0    vector_search.py hits=0    graph_query.py hits=0
pipeline.py        hits=0    pre_experiment.py hits=0    metrics.py    hits=0
third_party_review.py hits=21（正对照；T11 记录 9——我的正则更宽，正对照 > 0 成立）
config.MODEL_CALLS_ALLOWED = 0

== T11 摘要 ==
step1_input_fingerprint_ok: True inputs: 11
step2_zero_calls_ok: True chain forbidden: {'check_inputs.py':0,'graph_query.py':0,'metrics.py':0,
                                            'pipeline.py':0,'pre_experiment.py':0,'vector_search.py':0}
step2_control_hits: {'third_party_review.py': 9}
step3_double_run_identical: True
run1 sha: {k_selection.json:ab62e009…, metrics_pre.jsonl:b33491f7…, per_question_trace.jsonl:7839de9a…,
           pre_experiment_matrix.jsonl:df9c05ad…}

== 链上六步日志 vs 摘要 ==
check_inputs code=0 0.323s ｜ vector_search_selftest code=0 7.223s ｜ graph_query_selftest code=0 0.082s
pipeline_selftest code=0 10.431s ｜ pre_experiment code=0 19.899s ｜ metrics code=0 0.068s（log_exists 全 True）

== run1/run2 日志尾部 ==
t11_run1_pipeline.log … exit_code = 0 / 8.860s    t11_run2_pipeline.log … exit_code = 0 / 8.579s
t11_run1_pre_experiment.log … exit_code = 0 / 19.757s  t11_run2_pre_experiment.log … exit_code = 0 / 19.723s
t11_run1_metrics.log … exit_code = 0 / 0.056s      t11_run2_metrics.log … exit_code = 0 / 0.054s
```

T11 三项声称的独立结论：**"11 个输入指纹一致" 成立**（第 1 节的现场重算）；
**"四个产物两次运行一致" 成立**（第 2 节的现场重跑，`run1==run2==工作区`）；
**"链上 0 次大语言模型／外部接口调用" 成立**（六个链上脚本的密钥／网络字样 0 处＋正对照 > 0＋
`MODEL_CALLS_ALLOWED=0`；我的两次全链路重跑也是在 `HF_HUB_OFFLINE=1` 下跑通、产物逐字节相同）。
注意口径：**问题侧本地 Embedding 前向确实跑了**（不是"全程未跑模型"），这与 T11 与 `run_manifest` 的
`local_embedding.note` 一致。

T12 的原始日志与现场重跑（命令 `python 工具\验收第7阶段.py [--profile static]`）：

```text
static：记录 57 项（44 通过／13 SKIP）＝现场 57 项（44 通过／13 SKIP），退出码 0；
        规范化比对只有 4 行差异：我加的"$ python …"命令行回显／"--- stderr ---"分隔行，以及 A2 的
        "28095 字符、562 行"→"28882 字符、573 行"（《19》在日志之后又改过）
full  ：记录 72 项（72 通过、退出码 0）；现场 三次重跑分别 72 项（70 通过／2 失败）、（70／2）、（61／11），退出码 1
        三次失败都含 W2；镜像内两次 pre_experiment 子进程 stderr：
        OpenBLAS error: Memory allocation still failed after 10 retries, giving up.  → exit_code = 1
        本机内存采样：16 GB 总量、可用物理最低 6.4 GB、**可用提交内存最低 6 MB**
仅把同样 10 条命令按同一顺序单独重跑一次（不经过验收工具的父进程）：10/10 退出码 0
```

判定：T12 **full 日志与现场输出不一致**（D5）；W2 失败的**归因**无法在本机分离（见 K1）。

### 8）与上游的一致性（回到上游产物重算）

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 C:\Users\15129\AppData\Local\Temp\re7_C\t8_upstream.py
```

```text
== 基本规模 ==
nodes.csv 行数 = 2802（声称 2802）
edges.csv 行数 = 2736（声称 2736）
关系分布 = {'BELONGS_TO':14,'COMPETES_WITH':1,'CUSTOMER_OF':4,'EVIDENCED_BY':1111,
            'HAS_EXECUTIVE':143,'ISSUED_BY':124,'PARTICIPATES_IN':1252,'RELATED_TO':87}
EVIDENCED_BY = 1111（声称 1111）
语义边（非 EVIDENCED_BY）= 1625（声称 1625）；带 source_chunk_id = 1625（声称 1625）
BELONGS_TO=14；其中 valid_from/valid_to 均为空 = 14/14（声称 14/14 全空）
标签分布 = {'Company':116,'Document':692,'Event':1100,'Industry':73,'Institution':316,'Person':403,'Policy':102}
Event 节点 = 1100（声称 1100）；event_time 空 = 544（声称 544，49.5%）

== 孤立节点（自己从 nodes+edges 重算）==
度数为 0 的节点数 = 435（声称 435）

== graph_stats.json 读数 ==
isolated_nodes = {"count":435,"ids":[...]}
unresolved = {"policy":"pending_confirmation_exclude_from_graph","relations_skipped":878,
              "relations_skipped_by_reason":{"unresolved_entity":878},...}
graph_check = {"checks":20,"failed":["belongs_to_carries_validity_columns","event_time_nonempty"],
               "failed_must":[],"known_gaps":[...],"passed":18}
event_core_attributes = {"event_time_null_count":544,"events":1100,...}

== 人工确认清单 / HCONF ==
节点表里 HCONF 节点 = 12；HCONF 且 Company 标签 = 12；HCONF 无 stock_code = 12
Company 节点 = 116（声称 116）；其中无 stock_code = 12（声称 12）
```

"1070 待消歧"来自上游消歧缓存（不在图谱导出目录内，属第 6 阶段链路产物）：

```
$env:PYTHONIOENCODING='utf-8'; python -X utf8 -c "import io,json,collections;p=r'交付物/04-数据与知识图谱/数据准备\数据集\_抽取缓存\v2.1_v1_2\图谱管线\消歧\unresolved.jsonl';rows=[json.loads(l) for l in io.open(p,encoding='utf-8') if l.strip()];print('unresolved.jsonl 行数 =',len(rows));print('reason 分布',collections.Counter(r.get('reason') for r in rows))"
```

```text
unresolved.jsonl 行数 = 1070
reason 分布 Counter({'no_alias_match': 1063, 'distinct_entity_marker': 7})
disambiguation.json → counts: entities=3293, resolved=2223, unresolved=1070, company_identities=104,
                      by_label.Company={'resolved':755,'total':1825,'unresolved':1070}
```

逐条判定：**2802／2736／1625／1111／544／1100／66／1070／435／12／14-14 全部一致**（11/11）。
唯一需要说明的是"1070"的**落点**：它不在 `graph_stats.json` 的机器可读字段里（那里是
`relations_skipped=878`），要从 `_抽取缓存\v2.1_v1_2\图谱管线\消歧\unresolved.jsonl` 现场重算；
《19》的"已知限制"一节已把出处写成《16》第8.4节（1070 ＝ 1063＋7），与现场重算吻合。

---

## 四、被驳回的疑似缺陷（假阳性，6 项）

| 编号 | 疑似问题 | 驳回依据 |
| --- | --- | --- |
| M1 | "gold 块都不在 `chunks.jsonl` 里"（我第一版自查脚本报了 107 条 NOT_IN_CHUNKS） | 我自己的脚本把 `chunk_id`（int）与 str 混用导致的假阳性；修好后 **异常 0 条**（A 节）。产物无此问题 |
| M2 | 报告与台账里出现千帆，"三家确认"会不会被误当成确认口径 | 报告文首与台账 `line_scope_note` 明确"确认口径＝两家（kimi＋zhipu）"，千帆逐题标 `excluded_per_author`；我按两家重算一致率 = 0.9667，与记录一致 |
| M3 | `k_selection` 里 K=15 的 `median_text_tokens=3268 ≤ 3600`，与"K=15 装不进预算"矛盾 | 预算排除用的是**第一轮非约束**中位数 4826；3268 是 B=3600 下被裁剪后的读数。两者我都独立复现（t4_grid） |
| M4 | 6 题最终集合不足 K，`precision_at_k` 仍按 10 算，疑似分母错误 | 这正是《02》第12.7节／硬约束 8 的"分母恒为 K、空缺记未命中"；逐题重算一致，`metrics.py --selftest` 也有专项用例 |
| M5 | T11 记录正对照 9 命中，我扫到 21 命中 | 正则范围不同（我多含 `http(s)://`／厂商名等）；两者都 > 0，"正对照必须命中"成立，不构成矛盾 |
| M6 | 12 道时间题的 `time_window` 里有 2012 年窗口，"最近30天"却用 2026-08-26～09-25，疑似混用 | 三个标签与 `time_window` 逐题自洽：`有` 的题都带可机读闭区间；PE-18 的窗口就是 2012-04-01～2012-04-30（题面问 2012 年的事件），与 `data_cutoff_time` 只用于"最近 N 天"的口径不冲突 |

---

## 五、无法判定的项（4 项）

| 编号 | 项 | 说明与已掌握的证据 |
| --- | --- | --- |
| K1 | 验收 full 的"72/72、退出码 0"能否在别的机器复现 | 本机三次重跑分别 2／2／11 项失败（全含 W2），直接原因是镜像内 `pre_experiment` 子进程 OpenBLAS 内存分配失败；本机 16 GB、采样时可用提交内存最低 6 MB，而把同样 10 条命令单独重跑为 10/10 退出码 0。**无法区分"工具脆弱"与"本机资源不足"**；但"日志＝现场"这一条已可判为不成立（D5） |
| K2 | 题集 gold 是否满足《18》非目标 7 的"检索 gold 必须由人工构造" | 题集自述：脚本构造候选＋决策者（AI）回原文核验＋两家第三方模型盲标复核＋作者裁定，`gold_verified_by=third_party_model_review_v1`、`gold_review_status` 明写"非人工逐题确认、人工抽检未做、复核结论不等于事实"。是否满足任务书要求属作者裁定范围；**本线只确认登记是诚实的、且没有把它写成人工金标准**（第 6 节） |
| K3 | gold 集合是否"唯一且最简" | 我抽 15 题回原文：0 题"不足"、2 题各 1 块可视为"多余"（D6）。"最简"取决于作者对"必需"的裁定，本线只能给出可复核的依据片段 |
| K4 | 千帆线 30 条原始返回是否真由该通道产出 | 按作者指示未重放、未新调接口；我只验证了缓存与台账／报告在 verdict、模型名、usage、sha256 上自洽（60,073 token、27/3/0），无法验证通道真实性 |

---

## 六、未覆盖范围

1. **未做任何模型调用**（含第三方复核通道的 `--profile replay` 重放）：三家的 `review.jsonl` 与
   `cache\*.json` 只做只读重算；"首次调用真实性"不在本线能力范围内（见 K4）。
2. **未验证第 8／10 阶段**（答案生成、正式测试集 120 题）与论文正文；也不对本阶段的 H1／H2 结论做判断。
3. **未逐字复核《19》全文 28882 字符**：只核了它被验收工具检查的行（小节齐全、四个取值、六张表表述、
   术语与边界）；`工具\跨文档核验.py --strict-citations` 的退出码 0 是在验收工具内部间接取得的。
4. **未评估第 6 阶段 260 条参照集本身的抽样偏倚**：只做了与 30 题的块／文档交集统计（第 5 节）。
5. **未做人工抽检**：本报告的一切"成立"判定都是"我按原文片段重算后成立"，不等价于人工抽检结论。
6. 时间戳判断依赖文件系统 mtime（本机时区），未使用仓库提交历史（`git` 只用于 check-ignore／ls-files／status）。

---

## 附：本线全部可复现命令与脚本落点

所有脚本与日志都在 `C:\Users\15129\AppData\Local\Temp\re7_C\`（项目树零写入）：

| 脚本 | 作用 |
| --- | --- |
| `mirror.py` | 把项目树所需部分镜像到 `…\Temp\re7_C\mirror\`（只读复制） |
| `t1_hashes.py` / `t1b_workspace_sha.py` | 11 个输入指纹、`input_manifest` 自身 sha、四产物 sha |
| `t2_rerun.py` | 镜像内 pipeline → pre_experiment → metrics 各跑两轮并逐字节比对 |
| `t3_metrics.py` | 自实现的四项指标逐题／均值对拍、分母与空值体检 |
| `t4_grid.py` | 网格中位数、预算规则、饱和、g 曲线的独立重跑 |
| `t5_gold.py` / `t5_review.py` / `t5_docs.py` / `t5_260b.py` | gold 存在性／锚点／时间子集／15 题回原文／文档字段一致性／260 条交集 |
| `t6_review.py` / `t6_wording.py` | 第三方复核的一致率、usage、字段、sha256、措辞语境 |
| `t7_t11.py` / `t7_capture.py` / `t7_keep.py` / `t7_again.py` / `t7_diff.py` / `t7_seq.py` | T11 三项声称、验收工具现场重跑、日志对比、失败定位与 10 条命令复现 |
| `t8_upstream.py` | 上游 2802／2736／1625／1111／544／1100／66／435／12／14-14 重算 |
| `logs\*` | 以上每一步的原始输出（UTF-8） |
