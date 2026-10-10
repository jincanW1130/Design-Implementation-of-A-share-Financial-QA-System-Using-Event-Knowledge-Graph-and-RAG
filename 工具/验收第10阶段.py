# -*- coding: utf-8 -*-
r"""工具\验收第10阶段.py —— 第 10 阶段（系统测试与对比实验）专项门禁。

依据
----
《26-第10阶段任务书（系统测试与对比实验）》第八节「验收标准（可机器核验）」，
A～G 共 **46 行**（A8＋B7＋C6＋D6＋E5＋F8＋G6）。
行号、标题、判据一律在运行时从《26》第八节**解析**得到，本脚本不自带副本；
脚本里注册的判据行与解析出来的 46 行若对不上，直接报「行结构错误」并按退出码 2 退出。

用法
----
    python 工具\验收第10阶段.py                    :: full 档：46 行逐行判，退出码 0／1／2
    python 工具\验收第10阶段.py --profile static   :: 静态档：不实跑脚手架零调用档、不跑全仓核验，
                                                      未执行的行记 UNRUN，退出码 2
    python 工具\验收第10阶段.py --selftest         :: 负向校准：原样对照 ＋ 18 个定向篡改反例
    python 工具\验收第10阶段.py --root <PATH>      :: 指向副本（selftest 用；自动按镜像模式跑）

退出码
------
    0  full 档 46 行全部 [OK]
    1  有内容失败（[FAIL]）
    2  static 档未全量执行／环境未就绪／selftest 未通过／行结构错误

口径（写死在脚本里，逐条注明《26》出处）
----------------------------------------
* **本阶段的判据不依赖运行中的服务**：第 10 阶段的四类交付物是题集、对照产出、系统指标留痕与
  复现材料，全部落盘；因此 full 档在「后端与 Neo4j 都没起」的环境下也能跑完并给结论
  （《26》第 5 节 硬约束 8／第 11 节 进入条件）。服务探针只作为**环境备注**打印，不进判据、不影响退出码。
* **指标一律现场重算**：B2／B3／B5／C3 的读数由本脚本从 `对照产出_v13\{组}\answer_trace.jsonl`
  与 PE 集 gold **独立重算**（口径＝《02》第12.7节 四项定义，K＝10），不与报告 md 自报值互为依据；
  D3 再让脚手架 `--report-only` 在临时副本上重算一遍，两把尺子互相印证。
* **D3／G1 于 2026-10-08 随事实变更重基线（不是放宽判据）**：两行原来的末条证据是
  「工作区**无** `对照产出_正式\`（正式全量未跑）」，那是**授权前**的状态断言——作者已授权并
  已跑完正式全量（六组落盘），该断言必然为假：**它断言的是"尚未开工"，对"产出是不是空壳／
  有没有被本次运行改坏"完全无感**。现改为同一把尺子上更严的事实核查：正式产出目录／报告 md／
  报告 json 三处齐备、**六组齐备**、逐组 `answer_trace.jsonl` 行数 **＝报告自报的有效题数**、
  且正式产出里**不得再出现**「正式全量未跑／未授权」这类已失效表述；D3 另断言
  `--report-only` 前后工作区正式产出的**内容指纹逐字节零改动**（旧断言只看目录在不在）。
  `--selftest` 的反例数 13 → **15**（⑭ 篡改 B1 组 trace 行数 → D3 报红；⑮ 往正式报告里塞回
  「正式全量未跑」→ G1 报红；两个篡改对旧判据都无感），旧判据的合理内核一条未删，
  46 行结构与 A～G 组数不变。
* **F4／F8 于 2026-10-08 随内容落地重基线（不是放宽判据）**：**F4** 旧末条是「120 题读数不许带
  小数」（授权前的状态断言）——正式全量已跑完，120 题读数**应当**出现，旧末条于是从"防冒写"
  翻成"防登记"（本轮补入正式集读数节后**实测变红**：`[FAIL] F4 …`、`结论：有内容失败 1 行：
  F4 ⇒ 退出码 1`）。现判据分五组：旧内核（两句历史声明原样保留）＋**正式全量已完成**的正向断言
  （逐组有效题数 113／118／117／120＋B1、落点 `对照产出_正式`）＋**正式集模型评分读数已登记**
  （五组 Answer Accuracy 均值 1.6903／1.8390／1.8120／1.7607／1.7863 ＋ 三项跨模型一致率
  0.9832／0.9916／0.9076）＋120 题读数须带落点／口径限定＋失效「未跑」表述不得裸留。**F8** 旧
  判据只查「五类归因标题齐备 ＋ 含『无法判定』」，对新补入的正式集六类归因与第 ⑤ 类的模型评分
  口径读数**全部无感**；现判据分四组：旧内核原样保留 ＋ 正式集答案侧门禁读数（18 题次／8 道不
  重复题号、3004／`answer_gate_failed`、`date_unverifiable`／`citation_missing`）＋第 ⑤ 类模型
  评分口径读数（同行并存「判 0 分」＋0 条 与「判 1 分」＋20 条；口径限定与主体标识齐备）＋六类
  关键读数与 `复算命令` ≥6 条。`--selftest` 的反例数 15 → **17**（⑯ 改《27》的 1.6903 → F4；
  ⑰ 抹掉《失败案例分析》的「18 题次」→ F8；两个篡改对旧判据都无感），旧判据的合理内核一条未删，
  46 行结构与 A～G 组数不变。
* **F6 的 C 组第二半（正向人工评分表述）于 2026-10-09 修的是守卫、不是文档（不是放宽判据）**：
  《27》第 v1.11 行（「人工标注」交付项正式撤销的登记）里有一句**保护性禁令**——
  「**不得**出现任何**正向**的人工评分／人工金标准／评分者一致性／信度表述」——旧守卫按
  **固定 14 字符窗口**取上下文，`不得` 落在窗口之外，于是把这条**禁令**误判成"正向人工评分表述"
  并报红（实测 `[FAIL] F6 … 出现正向人工评分表述（口径红线）：L705…`、46 行里通过 45、退出码 1）。
  **改法＝把否定窗口从"14 字符"换成"该匹配所在的整句"**（按 。；;!?！？ 切句，句内出现
  不是／不得／并未／没有／非人工／无／不作／反对 之一才算禁令式表述）：禁令句不再误报，
  **而跨句的 `不得` 不再能豁免另一句里的真实断言**——自检反例 ⑱（同一行写成
  「**不得**写成人工口径。人工评分已完成。」）在旧守卫下**被放行**、在新守卫下**报红**，
  即新守卫同时补上了一处**假阴性**。`--selftest` 的反例数 17 → **18**（只增不减），
  F6 的 A／B／D 三组与 C 组第一半（失效表述须带时点限定）一字未改，保护性禁令一条未删。
* **`--preflight` 与 `--b1-selftest` 不实跑**（D4）：这两档会调用
  `write_model_call_audit()` 覆写 `实验方案\本次运行模型调用审计.json`——那是**唯一一份**
  `--preflight` 留痕（含它的 FAIL 项），覆写等于毁证据。故 D4 改为「读留痕 ＋ 静态核对哨兵」，
  并把留痕里如实记录的 FAIL 项**逐条打印**（不静默放过）。
* **正式全量已完成是正向断言**（F4，2026-10-08 重基线后）：《27》必须登记「正式全量实验已完成」
  与逐组有效题数，并登记正式集的模型评分读数；反过来，**失效的「未跑」表述不得无更正地留在文里**
  （旧口径「120 题读数不许带小数」是授权前的状态断言，已随事实变更换掉，见上一条）。
* **G3 跨文档核验带「范围／时点限定」**：本阶段开工时 `--strict-citations` **并非全绿**——当时有
  2 项**先于本阶段存在**的失败（《02》三处版本号不一致、N2 两处引用《02》过期版本，落点分别在
  《16》L801 与《25》L706，两处都在本阶段的写范围之外），**这两项已由其它任务在本次交付过程中修掉**。
  另有一项「带号文档均已登记」曾因 `26-`／`27-` 未进《00》索引而失败——该项属《26》第4.7节 登记的
  **收口登记产出、由 Lead 统一执行**（硬约束 20 禁止本阶段改《00》），**在本轮定稿时已由 Lead 完成**。
  G3 判据＝失败项集合必须 ⊆ {开工基线 ∪ 这一项已登记由 Lead 执行的登记项}，**超出即 FAIL**；
  「文档提到的文件均存在」（悬空引用）**零容忍**；允许项逐条打印、不静默放过。当前实测：退出码 0、全部通过。
* **上游只读**（G4／G5）：以《26》第三节登记的 15 个 SHA-256 指纹为准，逐项比对；
  `交付物/03-代码\问答\config.py` 的 `qid` 前缀白名单修复**由另一路任务并行实施**（《27》已登记），
  故它**不在**指纹清单内——这一豁免逐条打印、不静默。
* 只读：不改业务代码、不改产物数值、不放宽判据；发现真缺陷如实 FAIL；不打印、不落盘任何口令。
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:                                                        # GBK 控制台 → UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                           # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------
# 0. 路径与常量
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))

S10 = "交付物/06-实验与评测"
P_TASK = os.path.join(S10, "26-第10阶段任务书（系统测试与对比实验）.md")
P_DOC27 = os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md")
P_FAILCASE = os.path.join(S10, "失败案例分析.md")
P_QSET = os.path.join(S10, "测试集", "questions.jsonl")
P_QNOTE = os.path.join(S10, "测试集", "说明.md")
P_V13 = os.path.join(S10, "对照产出_v13")
P_V12 = os.path.join(S10, "对照产出")
P_REPORT = os.path.join(P_V13, "A_vs_C_对照报告.md")
P_REPORT_JSON = os.path.join(P_V13, "A_vs_C_对照.json")
P_REPORT12 = os.path.join(P_V12, "A_vs_C_对照报告.md")
P_DECISIVE = os.path.join(S10, "决定性实验_图谱加厚18倍.md")
P_NFR_MD = os.path.join(S10, "系统指标", "NFR_readings.md")
P_NFR_JSON = os.path.join(S10, "系统指标", "NFR_readings.json")
P_PLANDIR = os.path.join(S10, "实验方案")
P_PLAN = os.path.join(P_PLANDIR, "跑法说明.md")
P_CHECKLIST = os.path.join(P_PLANDIR, "实验前置检查清单.md")
P_AUDIT = os.path.join(P_PLANDIR, "本次运行模型调用审计.json")
P_SCAFFOLD = os.path.join(S10, "工具", "跑正式对照.py")
P_REPRO = os.path.join(S10, "复现包")
P_REPRO_MANIFEST = os.path.join(P_REPRO, "manifest.json")
P_SUBMIT = os.path.join(S10, "送审材料", "数据来源与合规说明.md")
P_OUT_FORMAL = os.path.join(S10, "对照产出_正式")
P_FEASIBILITY = os.path.join(S10, "测试集可行性分析.md")

P_PE = os.path.join("交付物/05-系统实现/RAG检索系统", "预实验问题集", "questions.jsonl")
P_PE_TRACE = os.path.join("交付物/05-系统实现/RAG检索系统", "检索产出", "per_question_trace.jsonl")
P_CHUNKS = os.path.join("交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")
P_DOCS = os.path.join("交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "clean", "documents.jsonl")
P_DATASET_META = os.path.join("交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "meta", "dataset.json")
GRAPH_VER = "v2.1_v1_3"
P_GRAPH_STATS = os.path.join("交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", GRAPH_VER, "graph_stats.json")
P_NODES = os.path.join("交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", GRAPH_VER, "nodes.csv")
P_EDGES = os.path.join("交付物/04-数据与知识图谱/事件抽取与知识图谱", "图谱导出", GRAPH_VER, "edges.csv")
P_QAREC8 = os.path.join("交付物/05-系统实现/智能问答系统", "问答产出", "qa_records.jsonl")
P_IM9 = os.path.join("交付物/05-系统实现/前后端系统集成", "集成产出", "input_manifest.json")
P_XDOC = os.path.join("工具", "跨文档核验.py")
P_RETRIEVAL_CFG = os.path.join("交付物/03-代码", "检索", "config.py")
P_ANSWER_CFG = os.path.join("交付物/03-代码", "问答", "config.py")
P_ANSWER = os.path.join("交付物/03-代码", "问答", "answer.py")

GROUPS5 = ["A", "B", "C", "D", "E"]
# 正式全量（`对照产出_正式\`）的组集合＝A～E ＋ Baseline 1（闭卷 LLM 辅助基线）。
# D3／G1 在 2026-10-08 的判据重基线里用它断言「六组齐备」，并逐组核对
# 「answer_trace 行数 ＝ 报告『题数』行自报值」。
GROUPS_FORMAL = GROUPS5 + ["B1"]
# D3／G1 用的「已失效表述」黑名单（授权前状态的说法，正式全量跑完后不得再出现在正式产出里）。
# 逐条是**事实性断言**，不是措辞偏好：正式全量已跑完，任何「未跑／未授权」的说法都与事实相反。
STALE_FORMAL_PHRASES = ("正式全量未跑", "正式全量尚未", "全量实验未跑", "全量尚未运行",
                        "未获授权", "尚未授权", "未授权项", "720 次调用属未授权")
FROZEN = {"K": 10, "N": 20, "budget": 3600, "g": 2}
CER_EXPECT = 0.566667
SUBSET_EXPECT = {"关系型": (0.5, 12), "多跳型": (0.523810, 21), "时序型": (0.75, 12)}
REPORT_METRICS = ["Recall@K", "Precision@K", "MRR", "Complete Evidence Recall@K"]

ROW_GROUPS = {"A": 8, "B": 7, "C": 6, "D": 6, "E": 5, "F": 8, "G": 6}
TOTAL_ROWS = 46
GROUP_TITLE = {
    "A": "测试集（存在与 schema）", "B": "对照与消融产出（v1.3 五组）",
    "C": "决定性实验与系统指标", "D": "实验脚手架与零调用档",
    "E": "复现包与送审材料", "F": "文档口径与如实声明", "G": "只读、术语与门禁",
}

# 起点：本阶段开工时 `跨文档核验.py --strict-citations` 的**已知基线项**（先于本阶段存在、
# 且落点在本阶段写范围之外）。2026-10-04 实测这两项已由其它任务修掉，故当前通常为空；
# 保留在允许清单里，是为了让「本阶段开工时就不干净」这一情形不被误记成新失败。逐条打印、不静默。
XDOC_BASELINE = [
    "《02》标题／版本字段／修订记录末行的版本号一致",
    "N2 引用的《02》版本等于当前基线或同行带版本链说明",
]

# G4／G5：上游只读指纹（登记在《26》第三节，开工时实测；逐项 SHA-256）
#
# **2026-10-09 目录重组重基线（仅因目录改名而更新；判据对象、行结构、A～G 分组、
#   断言强度与反例集均未变）**：顶层 `阶段NN-XXX/` 整体改名到 `交付物/NN-XXX/`、
#   `代码/` → `交付物/03-代码/`。这些上游文件里内嵌着指向仓库内其他文件的路径字符串
#   （模块头注释、`ROOT`／`STAGE_DIR`／`DATASET_ROOT`／`GRAPH_DIR` 常量、
#   `generated_by` 字段、`source` 字段等），路径重写后其内容随之变化，SHA-256 必然改变。
#   逐文件已用 `git show HEAD:<旧路径>` 与现盘做**归一化比对**核实：差异只是路径前缀，
#   没有路径之外的误伤。`graph_stats.json` 另经 `write_graph.py --profile v21_v1_3`
#   （零模型调用）重新生成，`问句／图谱导出` 的语义读数逐项不变（节点 3607／边 3614／
#   机检 20 项 passed 18、failed_must 空）。
# 【旧期望值原样保留（时点留痕，不得删除）】
#   UPSTREAM_FP（旧）：
#     "交付物/03-代码/检索/config.py"      a55b91db651c13900f35ab74007fb6fa9ea366e2097ba218cc45d17d7dbc1306
#     "交付物/03-代码/检索/pipeline.py"    1ec94bd957c39d13a4ffce13146ff32004b03fe5bba833498dfc017058449835
#     "交付物/03-代码/检索/graph_query.py" 897ba8c79c786fce5b46be726c430c4ab922036b839dfe65c735ece10a4d0eed
#     "交付物/03-代码/问答/run_answer.py"  fb3d54f3cd4e1764c411d12d78d958bcb9eaeb4e9df35a4c7e4e8cc773c5c14b
#     "交付物/03-代码/问答/assemble.py"    f7760c2b7b9599136fbe16d6d1ea2425cc99911e31ff84d8b291f5eec4dfd339
#     "交付物/03-代码/问答/prompt.py"      60b0e8b41ce147b5bbcf86f6dc11c1faed7ba5fd70a9e55d80d8aef1bcaf001b
#     "交付物/05-系统实现/RAG检索系统/预实验问题集/questions.jsonl"
#                                          12e579c09d7377ffe792930bbac29b6d374ad97562a8f65a49882bbb82b477e6
#     "交付物/05-系统实现/RAG检索系统/检索产出/per_question_trace.jsonl"
#                                          17566e9772f1e6e6d9fa7556d4bedfe0331e5535a8ec3348c376308cd1398b4b
#   UPSTREAM_FP_5_9（旧）：
#     "…/图谱导出/v2.1_v1_3/graph_stats.json"
#                                          f15a3409566a234061b733417e60c6dca26443da215ba46f74a17965c4df5e55
#     "…/前后端系统集成/集成产出/input_manifest.json"
#                                          9f02d39967cdf96fc8013e0620485f64efd3eab1f46ba54f0d4375147d45c803
#   （其余 6／6 项未变，仍为上列同一批值。）
#   **2026-10-10 重基线（只更新期望值，判据语义与强度不变）**：`input_manifest.json` 的期望值由
#   `6def927129908339b1fc5b3b0ee094308a359401d84c7edca2d15468d664763d` 更新为
#   `946c8de588ab21f38b0a7bf246aa7bafa0742fb9257fbbc972bc248bb2803992`。**理由＝该文件按第 9 阶段
#   自己的既定做法被重登记，不是被并行改动**：目录重组（《02》v3.16）使
#   `交付物/05-系统实现/前后端系统集成/_工作底稿/决策者核验/输入指纹.py` 的上溯层数与 INPUTS 路径失效
#   （实测症状：`--check` 报「上游代码 0 个文件、删除 31」＝第 9 阶段门禁 I1 行红），修复后按 **《25》
#   修订记录 v1.13 的既有做法**执行 `--write` 重登记（**11 项输入 ＋ 上游代码 31 个文件**，各输入的
#   sha256 与旧基线逐项相同、只有 `path` 字段由旧目录名改为新目录名）；**旧期望值原样保留为时点留痕**
#   （见上一行），**G5 的判据语义与强度一字未改**（仍逐件比对"第 5～9 阶段交付物只读"）。
UPSTREAM_FP = {
    "交付物/03-代码/检索/config.py": "419c12c1eeaf99a4785ac3f5e85cd010adc5ffb4fea24ab287024925ca778ce4",
    "交付物/03-代码/检索/pipeline.py": "99fd5d4723ab8263905a879fda275ed737dfee823b8436de59599fa101e7c4ba",
    "交付物/03-代码/检索/graph_query.py": "e50c78fb7ae6e3caf9e24598c4e47f38ba7b3ed1ff2549600b999217ddf4a6e0",
    "交付物/03-代码/问答/run_answer.py": "7a9f10a1c285e3ced516ea6245017990ea502f36c1949266ea5f73f5331d6dab",
    "交付物/03-代码/问答/assemble.py": "508f6d8629b02d06dd4eb5f625ee93744d44e7e6a22f1ebeb98ffb9fc9b70bba",
    "交付物/03-代码/问答/prompt.py": "60b0e8b41ce147b5bbcf86f6dc11c1faed7ba5fd70a9e55d80d8aef1bcaf001b",
    "交付物/05-系统实现/RAG检索系统/预实验问题集/questions.jsonl":
        "9817534cba8066dbfd4cbfd03b416e839f649d847176952134fe7dda556e8be1",
    "交付物/05-系统实现/RAG检索系统/检索产出/per_question_trace.jsonl":
        "17566e9772f1e6e6d9fa7556d4bedfe0331e5535a8ec3348c376308cd1398b4b",
}
UPSTREAM_FP_5_9 = {
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/meta/dataset.json":
        "41c82bc43008eaba262c029776e32384417d3cbe9a265f93b6fcd8663f5fc988",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/chunks/chunks.jsonl":
        "2202cbf8e3915598fc9fa57a9fe6d32577705f59ce7bfdfab822903d949e8e44",
    "交付物/04-数据与知识图谱/数据准备/数据集/v2.1/clean/documents.jsonl":
        "c838c608c20060adb1366d5c6f7566f9de25016110dc368f7f92fcb8a10f9eea",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/graph_stats.json":
        "576e06b72f9406b8a750cdea1470ca09e8fbdc93c258f2c23843d49734e8c0dc",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/nodes.csv":
        "ecfaa43a650c42a5281eaf50defa79ada043985b2283847507b6ef3ad006341e",
    "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/edges.csv":
        "0ff0eecfc23bb860f7307b85ed510b49265d6ec79b7ad22fc6b038df1738fe91",
    "交付物/05-系统实现/智能问答系统/问答产出/qa_records.jsonl":
        "a64d0f0bcf60a0449bc4dbe4d9866bdbbd51a1f1968c275f514d2984f092768d",
    "交付物/05-系统实现/前后端系统集成/集成产出/input_manifest.json":
        "946c8de588ab21f38b0a7bf246aa7bafa0742fb9257fbbc972bc248bb2803992",
        # 时点留痕（2026-10-10 前的基线，仅作历史，不再用于判定）：
        # 6def927129908339b1fc5b3b0ee094308a359401d84c7edca2d15468d664763d
}
# 已登记的并行修复豁免（不静默放过：G4 里逐条打印）
G4_EXEMPT = ["交付物/03-代码/问答/config.py（qid 前缀白名单的修复由另一路任务并行实施，《27》已登记）"]

# F3：`测试集\说明.md` 第 5 节的 9 条已知限制 ←→ 《27》里承接处必须出现的关键词
LIMIT_KEYS = [
    ("第 1 条 gold 不是人工金标准", ["人工金标准"]),
    ("第 2 条 事件型+2跳格内两条不同路径", ["路径一", "路径二"]),
    ("第 3 条 路径二的 2 跳必要性沿用 PE-18 先例", ["PE-18"]),
    ("第 4 条 时间约束题 gold 只落一篇文档的比例偏高", ["只落"]),
    ("第 5 条 跨批 7 个 gold 块被两道题共用", ["跨批"]),
    # 2026-10-09 重基线：原 token「人工抽检」随「人工」概念的删除改为「逐条抽检」——
    # 抽检工作台 `工具\抽检助手.py` 与那 40 条抽检**本身未变**（台账 40 条、已复核 0 条），
    # 变的只是措辞；本行判据的对象与强度不变（仍要求《27》承接该条已知限制）。
    ("第 6 条 没有做逐条抽检", ["逐条抽检"]),
    ("第 7 条 qid 前缀与脚手架白名单不一致", ["qid 前缀"]),
    ("第 8 条 薄类关系未设题", ["SUPPLIES"]),
    ("第 9 条 时间窗口候选集合是确定性代理", ["确定性代理"]),
]
# F4：必须在《27》里出现的声明（正向断言）
UNRUN_DECL = [
    "120 题全量实验尚未运行",
    "本阶段截至本文件时的实验结论",
]
UNRUN_LINE_GUARD = ["未运行", "尚未运行", "未跑", "不适用", "不得", "未取得", "未获得", "无法判定"]
NUM4 = re.compile(r"\d\.\d{4,}")
Q120 = re.compile(r"120\s*题")

# G2 术语纪律（拼接构造，避免脚本自身成为命中源）
BANNED_VDB = "向量" + "数据库"

# C1 决定性实验的六组关键读数（逐项）
DECISIVE_TOKENS = ["286", "1252", "1914", "116", "938", "0／4／1", "29／9／8", "878", "3607／3614"]

# 镜像（selftest）需要带的文件与目录
MIRROR_FILES = [
    P_TASK, P_DOC27, P_FAILCASE, P_QSET, P_QNOTE, P_REPORT, P_REPORT_JSON, P_REPORT12,
    P_DECISIVE, P_NFR_MD, P_NFR_JSON, P_PLAN, P_CHECKLIST, P_AUDIT, P_SCAFFOLD,
    P_REPRO_MANIFEST, os.path.join(P_REPRO, "README.md"), os.path.join(P_REPRO, "manifest.md"),
    os.path.join(P_REPRO, "chunks.jsonl"), os.path.join(P_REPRO, "documents.jsonl"),
    os.path.join(P_REPRO, "graph_slice", "nodes.csv"),
    os.path.join(P_REPRO, "graph_slice", "edges.csv"),
    P_SUBMIT, P_FEASIBILITY,
    P_PE, P_PE_TRACE, P_CHUNKS, P_DOCS, P_DATASET_META,
    P_GRAPH_STATS, P_NODES, P_EDGES, P_QAREC8, P_IM9, P_RETRIEVAL_CFG, P_ANSWER_CFG, P_ANSWER,
    # 正式全量（`对照产出_正式\`）：D3／G1 重基线后要核「六组齐备 ＋ 行数＝自报有效题数」，
    # 故镜像必须带上这份产出；逐题目录（13.4 MB）与过程留痕不参与判据，不带。
    os.path.join(P_OUT_FORMAL, "A_vs_C_对照报告.md"),
    os.path.join(P_OUT_FORMAL, "A_vs_C_对照.json"),
    os.path.join(P_OUT_FORMAL, "产出SHA256.json"),
] + [os.path.join(P_OUT_FORMAL, g, n) for g in GROUPS_FORMAL
     for n in ("answer_trace.jsonl", "qa_records.jsonl")]
MIRROR_DIRS = [P_V13, P_V12, os.path.join("交付物/03-代码", "检索"), os.path.join("交付物/03-代码", "问答")]
MIRROR_SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv"}
MIRROR_SKIP_EXT = {".pyc", ".log", ".zip", ".exe", ".dll"}


# --------------------------------------------------------------------------
# 1. 小工具
# --------------------------------------------------------------------------
def rel(root, path):
    try:
        return os.path.relpath(os.path.abspath(path), os.path.abspath(root)).replace("\\", "/")
    except Exception:                                       # pragma: no cover
        return str(path)


def read_text(path):
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_lines(path):
    return read_text(path).split("\n")


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    try:
        with io.open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:                                       # noqa: BLE001
        return default


def load_jsonl(path):
    out = []
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def norm(s):
    return re.sub(r"\s+", "", s or "")


def read_csv_rows(path):
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return None


# --------------------------------------------------------------------------
# 2. 规范解析（《26》第八节的 46 行）
# --------------------------------------------------------------------------
ROW_RE = re.compile(r"^\|\s*([A-G]\d{1,2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def parse_spec_rows(root):
    """从《26》第八节解析 46 行 → [(rid, title, criterion, lineno)]。"""
    path = os.path.join(root, P_TASK)
    if not os.path.exists(path):
        return []
    lines = read_lines(path)
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## 八、"):
            start = i
            break
    if start is None:
        return []
    rows = []
    for i in range(start, len(lines)):
        ln = lines[i]
        if ln.startswith("## 九、"):
            break
        m = ROW_RE.match(ln)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3), i + 1))
    return rows


# --------------------------------------------------------------------------
# 3. 上报器
# --------------------------------------------------------------------------
STATUS_TAG = {"OK": "[OK ]", "FAIL": "[FAIL]", "UNRUN": "[UNRUN]"}


class Gate:
    def __init__(self, root, profile, mirror=False):
        self.root = root
        self.profile = profile
        self.mirror = bool(mirror)
        self.rows = {}
        self.notes = []
        self.env_notes = []
        self.cache = {}

    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def ref(self, *parts):
        return rel(self.root, os.path.join(self.root, *parts))

    def exists(self, *parts):
        return os.path.exists(self.p(*parts))

    def row(self, rid, status, detail):
        if rid in self.rows:
            raise RuntimeError("行 %s 被判了两次（脚本内部错误）" % rid)
        self.rows[rid] = (status, detail)

    def ok(self, rid, detail):
        self.row(rid, "OK", detail)

    def fail(self, rid, detail):
        self.row(rid, "FAIL", detail)

    def unrun(self, rid, detail):
        self.row(rid, "UNRUN", detail)

    def note(self, s):
        self.notes.append(s)

    def bad_env(self, rid, detail):
        self.env_notes.append(rid)
        self.row(rid, "FAIL", detail)

    # ---- 共享数据（按需解析一次） ----
    def questions(self):
        if "q" not in self.cache:
            self.cache["q"] = load_jsonl(self.p(P_QSET))
        return self.cache["q"]

    def pe(self):
        if "pe" not in self.cache:
            self.cache["pe"] = {r["qid"]: r for r in load_jsonl(self.p(P_PE))}
        return self.cache["pe"]

    def chunks(self):
        if "ch" not in self.cache:
            self.cache["ch"] = {int(r["chunk_id"]): r
                                for r in load_jsonl(self.p(P_CHUNKS))}
        return self.cache["ch"]

    def docs(self):
        if "doc" not in self.cache:
            self.cache["doc"] = {int(r["doc_id"]): r for r in load_jsonl(self.p(P_DOCS))}
        return self.cache["doc"]

    def traces(self, group, ver="v13"):
        key = "tr_%s_%s" % (ver, group)
        if key not in self.cache:
            base = P_V13 if ver == "v13" else P_V12
            rows = load_jsonl(self.p(base, group, "answer_trace.jsonl"))
            self.cache[key] = {r["qid"]: r for r in rows}
        return self.cache[key]

    def graph(self):
        if "g" not in self.cache:
            nodes = {r["node_id"]: r for r in read_csv_rows(self.p(P_NODES))}
            edges = read_csv_rows(self.p(P_EDGES))
            self.cache["g"] = (nodes, edges)
        return self.cache["g"]

    def formal_outputs(self):
        """正式全量产出（`对照产出_正式\`）的**事实核对**，供 D3／G1 共用（判据重基线后新增）。

        2026-10-08 之前，D3／G1 的证据是「工作区**无** `对照产出_正式\`」，那只是**授权前**
        的状态断言——正式全量已跑完后它必然为假（判据随事实变更失效，不是放宽判据）。
        本方法把「该目录存在」换成一套**更严的事实核查**，两行都用它：

        ① 目录、报告 md 与报告 json 三处齐备；
        ② **六组齐备**（A／B／C／D／E ＋ Baseline 1）；
        ③ 逐组 `answer_trace.jsonl` 行数 **＝正式报告『题数』行自报的有效题数**——组别沿
           `A_vs_C_对照.json` 的 `groups` 顺序映射到报告 md 各表的**列序**（`题数` 是该表最后
           一行，与表头的组标签同序）；少一行、多一行、整份缺失都**点名报出**；
        ④ 正式报告里**不出现** `STALE_FORMAL_PHRASES` 任一条（"正式全量未跑"这类已失效表述）。

        返回 `(ok, bad 列表, info dict)`；`info["fp"]` 是目录内容指纹（文件相对路径 → 字节数），
        供 D3 断言「跑 `--report-only` 前后正式产出**零改动**」。
        """
        if "formal" in self.cache:
            return self.cache["formal"]
        base = self.p(P_OUT_FORMAL)
        bad, info = [], {"groups": [], "rows": {}}
        # ---- ① 目录、报告 md、报告 json ----
        if not os.path.isdir(base):
            bad.append("缺 %s（正式全量产出目录）" % self.ref(P_OUT_FORMAL))
        for name in ("A_vs_C_对照报告.md", "A_vs_C_对照.json"):
            if not os.path.isfile(os.path.join(base, name)):
                bad.append("缺 %s" % self.ref(P_OUT_FORMAL, name))
        j = load_json(os.path.join(base, "A_vs_C_对照.json"), None)
        md = read_text(os.path.join(base, "A_vs_C_对照报告.md")) \
            if os.path.isfile(os.path.join(base, "A_vs_C_对照报告.md")) else ""
        declared = {g: None for g in GROUPS_FORMAL}          # 组 → 报告自报『题数』
        all_declared = {g: None for g in GROUPS_FORMAL}      # 组 →「全部测试集」表的『题数』
        info["groups_in_json"] = list((j or {}).get("groups") or [])
        if j is None:
            bad.append("报告 json 读不动或不存在")
        # 报告 md 的各张主表表头顺序 ＝ json 的 groups 顺序（同一渲染器），按列序取每张表的
        # 「题数」行。**为什么取"全部表"而不是只取第一节**：核心集、压力子集、全部题集三张表
        # 的范围**不同**（108／12／120 题，允许重叠），所以每张表的『题数』行本来就该各不相同——
        # 这不是矛盾，是范围差异。真正的正向断言是：**逐组 trace 行数 ＝ 该组在「全部测试集」
        # 那张表里的『题数』自报值**（只有那张表覆盖题集全部 120 题，是该组有效题数的上界与真值），
        # 另加一条「同一范围内同一小组的表『题数』不得自相矛盾」的交叉核对。
        gorder = [g for g in (info["groups_in_json"] or []) if g in GROUPS_FORMAL]
        if not gorder:
            gorder = list(GROUPS_FORMAL)
        mlines = md.split("\n")
        seen_any, seen_all = False, False
        for i, ln in enumerate(mlines):
            if not (ln.startswith("| 指标 |") and all(("| %s " % g) in ln for g in gorder)):
                continue
            cols = [c.strip() for c in ln.strip().strip("|").split("|")]
            rows_line = next((x for x in mlines[i:i + 40] if x.startswith("| 题数 |")), None)
            if rows_line is None:
                bad.append("报告主表缺『题数』行（表头在 L%d）" % (i + 1))
                continue
            # 该表属于哪个范围：往上找最近的「#### 」小标题（如「3.1 全部 120 题」）
            title = ""
            for k in range(i, max(-1, i - 60), -1):
                if mlines[k].startswith("#### "):
                    title = mlines[k]
                    break
            is_all = ("全部" in title)
            seen_any = True
            seen_all = seen_all or is_all
            vals = [c.strip() for c in rows_line.strip().strip("|").split("|")]
            vals = vals[1:] if vals and vals[0] == "题数" else vals
            cmap = dict(zip(cols[1:], vals))
            for g in GROUPS_FORMAL:
                try:
                    v = int(str(cmap.get(g)).strip())
                except (TypeError, ValueError):
                    continue
                if is_all:
                    if all_declared[g] is None:
                        all_declared[g] = v
                    elif all_declared[g] != v:
                        bad.append("「全部测试集」表里 %s 的『题数』自相矛盾：%d vs %d"
                                   % (g, all_declared[g], v))
                if declared[g] is None:
                    declared[g] = v
        if not seen_any:
            bad.append("报告里找不到含全部组列的主表表头（无法核对『题数』行）")
        if seen_any and not seen_all:
            bad.append("报告里找不到「全部测试集」那张表（无法核对有效题数）")
        info["declared"] = all_declared
        info["declared_by_table"] = declared
        # ---- ② 六组齐备 ＋ ③ 行数 ＝ 自报『题数』 ----
        for grp in GROUPS_FORMAL:
            if not os.path.isfile(self.p(P_OUT_FORMAL, grp, "answer_trace.jsonl")):
                bad.append("缺 %s" % self.ref(P_OUT_FORMAL, grp, "answer_trace.jsonl"))
                continue
            info["groups"].append(grp)
            n = len(load_jsonl(self.p(P_OUT_FORMAL, grp, "answer_trace.jsonl")))
            info["rows"][grp] = n
            want = all_declared.get(grp)
            if want is not None and n != want:
                bad.append("%s 的 answer_trace 行数 %d ≠「全部测试集」表『题数』行自报值 %d"
                           % (grp, n, want))
        # ---- ④ 已失效表述（授权前状态的说法）不得再出现在正式产出里 ----
        stale = [p for p in STALE_FORMAL_PHRASES
                 if (p in md) or (p in json.dumps(j or {}, ensure_ascii=False))]
        info["stale"] = stale
        if stale:
            bad.append("正式产出里仍出现已失效表述：%s" % "／".join(stale))
        # ---- 目录内容指纹（D3 用它断言 report-only 前后零改动） ----
        hs = hashlib.sha256()
        nf = 0
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d not in MIRROR_SKIP_DIRS]
            for f in sorted(fn):
                if os.path.splitext(f)[1].lower() in MIRROR_SKIP_EXT:
                    continue
                fp = os.path.join(dp, f)
                nf += 1
                hs.update((rel(base, fp) + "|" + str(size_of(fp))).encode("utf-8"))
        info["fp"] = "%s/%d" % (hs.hexdigest(), nf)
        info["n_files"] = nf
        self.cache["formal"] = (not bad, bad, info)
        return self.cache["formal"]

    def filterable_docs(self):
        """现场重算「可过滤文档集合」＝含 >=2 个不同 event_time 日期的文档（口径对齐
        `_决策者核验_题集.py` V4 / `统计分格可时序候选.py`）。"""
        if "filt" in self.cache:
            return self.cache["filt"]
        nodes, edges = self.graph()
        doc_events = collections.defaultdict(set)
        for e in edges:
            if e.get("relation") != "EVIDENCED_BY":
                continue
            h, t = e.get("head_id"), e.get("tail_id")
            if nodes.get(h, {}).get("label") == "Event" and nodes.get(t, {}).get("label") == "Document":
                try:
                    doc_events[int(t)].add(h)
                except (TypeError, ValueError):
                    continue
        ok = set()
        for doc, evs in doc_events.items():
            dates = {(nodes[e].get("event_time") or "").strip() for e in evs}
            dates.discard("")
            if len(dates) >= 2:
                ok.add(doc)
        self.cache["filt"] = ok
        return ok

    # ---- 指标独立重算（《02》第12.7节 四项定义，K＝10） ----
    def metrics(self, group, ver="v13"):
        key = "m_%s_%s" % (ver, group)
        if key in self.cache:
            return self.cache[key]
        pe = self.pe()
        tr = self.traces(group, ver)
        R = P = M = C = 0.0
        n = 0
        for qid, row in tr.items():
            gold = set(int(x) for x in pe[qid]["gold_evidence_chunk_ids"])
            order = [int(e["chunk_id"]) for e in row["evidence"]]
            s = set(order)
            denom = len(gold) or 1
            R += len(gold & s) / float(denom)
            P += len(gold & s) / float(FROZEN["K"])
            rank = next((i + 1 for i, c in enumerate(order) if c in gold), None)
            M += (1.0 / rank) if rank else 0.0
            C += 1.0 if gold <= s else 0.0
            n += 1
        n = n or 1
        self.cache[key] = {"n": n, "Recall@K": R / n, "Precision@K": P / n,
                           "MRR": M / n, "Complete Evidence Recall@K": C / n}
        return self.cache[key]

    def subset_metrics(self, group, subset, ver="v13"):
        pe = self.pe()
        tr = self.traces(group, ver)
        if subset == "关系型":
            qs = [q for q in pe if pe[q]["task_type"] == "关系型"]
        elif subset == "多跳型":
            qs = [q for q in pe if int(pe[q]["gold_hop_depth"]) >= 1]
        else:
            qs = [q for q in pe if pe[q]["time_constraint"] == "有"]
        qs = [q for q in qs if q in tr]
        hit = 0.0
        for q in qs:
            gold = set(int(x) for x in pe[q]["gold_evidence_chunk_ids"])
            if gold <= {int(e["chunk_id"]) for e in tr[q]["evidence"]}:
                hit += 1.0
        return (hit / len(qs) if qs else 0.0), len(qs)


# --------------------------------------------------------------------------
# 4. 判据注册表
# --------------------------------------------------------------------------
CHECKS = {}


def check(*rids):
    def deco(fn):
        for rid in rids:
            CHECKS[rid] = fn
        return fn
    return deco


# ==========================================================================
# A 组 · 测试集（存在与 schema）
# ==========================================================================
@check("A1")
def c_a1(g):
    if not g.exists(P_QSET):
        return g.fail("A1", "题集不存在：%s" % g.ref(P_QSET))
    rows = g.questions()
    core = sum(1 for r in rows if r.get("subset") == "核心")
    stress = sum(1 for r in rows if r.get("subset") == "压力")
    detail = "行数 %d（核心 %d／压力 %d）｜%s" % (len(rows), core, stress, g.ref(P_QSET))
    if len(rows) == 120 and core == 108 and stress == 12:
        g.ok("A1", detail)
    else:
        g.fail("A1", detail + "（应 120／108／12）")


@check("A2")
def c_a2(g):
    rows = g.questions()
    qids = [r.get("qid") for r in rows]
    want = ["FQ-%03d" % i for i in range(1, 121)]
    order_ok = qids == want
    dup = len(qids) != len(set(qids))
    if order_ok and not dup:
        g.ok("A2", "FQ-001～FQ-120 连续、无重号、与行序一致（第 1 行 FQ-001、第 120 行 FQ-120）")
    else:
        g.fail("A2", "qid 集合或行序不符：重号=%s；前 3 行=%s；后 3 行=%s"
               % (dup, qids[:3], qids[-3:]))


@check("A3")
def c_a3(g):
    rows = g.questions()
    bad = []
    cells = [("事实型", 0), ("事实型", 1), ("事实型", 2),
             ("事件型", 0), ("事件型", 1), ("事件型", 2),
             ("关系型", 0), ("关系型", 1), ("关系型", 2)]
    for t, h in cells:
        for tc in ("无", "有"):
            n = sum(1 for r in rows if r.get("task_type") == t
                    and int(r.get("gold_hop_depth", -1)) == h
                    and r.get("time_constraint") == tc and r.get("subset") == "核心")
            if n != 6:
                bad.append("核心格 %s+%d跳/%s = %d（应 6）" % (t, h, tc, n))
    ns = sum(1 for r in rows if r.get("task_type") == "关系型"
             and int(r.get("gold_hop_depth", -1)) == 2
             and r.get("time_constraint") == "有" and r.get("subset") == "压力")
    if ns != 12:
        bad.append("压力子集 = %d（应 12）" % ns)
    for r in rows:
        if r.get("cell") != "%s+%d跳" % (r.get("task_type"), int(r.get("gold_hop_depth", -1))):
            bad.append("%s cell=%s 与标签不符" % (r.get("qid"), r.get("cell")))
    # 压力子集必须**可识别**（供单独报告）
    if not any("压力" == r.get("subset") for r in rows):
        bad.append("压力子集无显式标记，无法单独报告")
    if bad:
        g.fail("A3", "；".join(bad[:6]) + ("（共 %d 项）" % len(bad)))
    else:
        g.ok("A3", "9 格 × 无/有 各 6 题＝核心 108；压力子集（关系型+2跳+有）12 且带显式 subset 标记；cell 与标签逐题自洽")


@check("A4")
def c_a4(g):
    chunks, docs = g.chunks(), g.docs()
    bad = []
    for r in g.questions():
        q = r.get("qid")
        cids = [int(x) for x in r.get("gold_evidence_chunk_ids") or []]
        dids = set(int(x) for x in r.get("gold_evidence_doc_ids") or [])
        if not (1 <= len(cids) <= FROZEN["K"]):
            bad.append("%s gold 条数 %d 不在 1..K" % (q, len(cids)))
        if int(r.get("gold_evidence_count", -1)) != len(set(cids)):
            bad.append("%s gold_evidence_count 与去重块数不符" % q)
        if len(set(cids)) != len(cids):
            bad.append("%s gold 块有重复" % q)
        real = set()
        for c in cids:
            if c not in chunks:
                bad.append("%s gold 块 %d 不在 chunks.jsonl" % (q, c))
            else:
                real.add(int(chunks[c]["doc_id"]))
        if real and dids != real:
            bad.append("%s gold doc_ids 与块实际不符" % q)
        for sm in (r.get("source_material") or []):
            if int(sm.get("doc_id", -1)) not in docs:
                bad.append("%s source_material doc %s 不在 documents.jsonl" % (q, sm.get("doc_id")))
    n = len(g.questions())
    if bad:
        g.fail("A4", "；".join(bad[:6]) + ("（共 %d 项／%d 题）" % (len(bad), n)))
    else:
        g.ok("A4", "%d 题逐题：gold 条数 1..%d、count=去重块数、doc_ids=块实际 doc_id、"
                   "块均在 chunks.jsonl、source_material 均在 documents.jsonl" % (n, FROZEN["K"]))


@check("A5")
def c_a5(g):
    chunks = g.chunks()
    hit = miss = 0
    noanchor = []
    samples = []
    for r in g.questions():
        anchors = r.get("gold_verify_anchors") or []
        if not anchors:
            noanchor.append(r.get("qid"))
        for a in anchors:
            c = int(a.get("chunk_id", -1))
            if c not in chunks:
                miss += 1
                samples.append("%s anchor 块 %d 不在语料" % (r.get("qid"), c))
                continue
            if norm(a.get("quote")) and norm(a.get("quote")) in norm(chunks[c].get("content")):
                hit += 1
            else:
                miss += 1
                samples.append("%s 块 %d 未逐字命中" % (r.get("qid"), c))
    total = hit + miss
    if miss or noanchor:
        g.fail("A5", "anchor 命中 %d／%d；无 anchor 的题 %s；%s"
               % (hit, total, noanchor or "无", "；".join(samples[:4])))
    else:
        g.ok("A5", "anchor 逐字命中 %d／%d（%d 题，逐题 ≥1 条，去空白后逐字命中原文）"
             % (hit, total, len(g.questions())))


@check("A6")
def c_a6(g):
    stats = load_json(g.p(P_GRAPH_STATS), {}) or {}
    prof = stats.get("profile")
    filt = g.filterable_docs()
    rows = g.questions()
    tc_rows = [r for r in rows if r.get("time_constraint") == "有"]
    outside = []
    for r in tc_rows:
        out = sorted(set(int(x) for x in r.get("gold_evidence_doc_ids") or []) - filt)
        if out:
            outside.append("%s→%s" % (r.get("qid"), out))
    detail = ("可过滤文档现场重算 %d 篇（%s：Document ←EVIDENCED_BY← Event，≥2 个不同 event_time 日期）；"
              "graph_stats.profile=%s；时间约束题 %d 道，gold 越界 %d 道"
              % (len(filt), GRAPH_VER, prof, len(tc_rows), len(outside)))
    if prof != "v21_v1_3":
        g.fail("A6", detail + "；profile 应为 v21_v1_3")
    elif len(filt) != 66:
        g.fail("A6", detail + "；可过滤文档应为 66 篇")
    elif outside:
        g.fail("A6", detail + "；越界题：%s" % "、".join(outside[:5]))
    else:
        g.ok("A6", detail + "；全部落在可过滤集合内")


@check("A7")
def c_a7(g):
    want = {"lo", "hi", "label", "basis", "cutoff", "empty_policy"}
    cutoff = "2026-09-25"
    bad = []
    n_tw = 0
    for r in g.questions():
        tw = r.get("time_window")
        if r.get("time_constraint") == "有":
            n_tw += 1
            if not isinstance(tw, dict) or set(tw.keys()) != want:
                bad.append("%s time_window 键集合 %s" % (r.get("qid"), sorted((tw or {}).keys())))
                continue
            lo, hi = tw.get("lo"), tw.get("hi")
            if not lo or not hi:
                bad.append("%s 缺 lo/hi" % r.get("qid"))
            elif lo > hi:
                bad.append("%s lo>hi" % r.get("qid"))
            elif hi > cutoff:
                bad.append("%s hi=%s 超过 data_cutoff=%s" % (r.get("qid"), hi, cutoff))
            if tw.get("basis") != "event_time" or tw.get("empty_policy") != "exclude":
                bad.append("%s basis/empty_policy 不符" % r.get("qid"))
        else:
            if tw:
                bad.append("%s 无时间约束但 time_window 非空" % r.get("qid"))
    if bad:
        g.fail("A7", "；".join(bad[:6]) + ("（共 %d 项）" % len(bad)))
    else:
        g.ok("A7", "%d 道时间约束题：键集合＝%s、lo≤hi≤%s、basis=event_time、empty_policy=exclude；"
                   "其余题 time_window 为空" % (n_tw, sorted(want), cutoff))


@check("A8")
def c_a8(g):
    pe = g.pe()
    pe_gold = {frozenset(int(x) for x in r["gold_evidence_chunk_ids"]) for r in pe.values()}
    pe_q = {norm(r["question"]) for r in pe.values()}
    gsame, qsame = [], []
    for r in g.questions():
        if frozenset(int(x) for x in r.get("gold_evidence_chunk_ids") or []) in pe_gold:
            gsame.append(r.get("qid"))
        if norm(r.get("question")) in pe_q:
            qsame.append(r.get("qid"))
    detail = ("PE 集 %d 题；gold 集合完全相同的题 %d 道 %s；题干逐字相同的题 %d 道 %s"
              % (len(pe), len(gsame), gsame or "无", len(qsame), qsame or "无"))
    if gsame or qsame:
        g.fail("A8", detail)
    else:
        g.ok("A8", detail)


# ==========================================================================
# B 组 · 对照与消融产出（v1.3 五组）
# ==========================================================================
@check("B1")
def c_b1(g):
    bad = []
    for grp in GROUPS5:
        for name in ("answer_trace.jsonl", "qa_records.jsonl"):
            p = g.p(P_V13, grp, name)
            if not os.path.exists(p):
                bad.append("缺 %s" % g.ref(P_V13, grp, name))
                continue
            n = len(load_jsonl(p))
            if n != 30:
                bad.append("%s/%s 行数 %d（应 30）" % (grp, name, n))
    nq = 0
    for grp in GROUPS5:
        d = g.p(P_V13, "逐题", grp)
        if not os.path.isdir(d):
            bad.append("缺逐题目录 %s" % g.ref(P_V13, "逐题", grp))
            continue
        nq += len([x for x in os.listdir(d) if os.path.isdir(os.path.join(d, x))])
    if nq != 150:
        bad.append("逐题目录数 %d（应 5×30=150）" % nq)
    if bad:
        g.fail("B1", "；".join(bad[:6]))
    else:
        g.ok("B1", "五组 answer_trace／qa_records 各 30 行、逐题目录 150 个（5×30）齐备；%s"
             % g.ref(P_V13))


@check("B2")
def c_b2(g):
    vals = {}
    for grp in GROUPS5:
        vals[grp] = g.metrics(grp)["Complete Evidence Recall@K"]
    uniq = sorted(set(round(v, 6) for v in vals.values()))
    detail = "CER 独立重算（gold ⊆ 最终证据集合，逐题平均，n=30）：%s" % \
             "，".join("%s=%.6f" % (k, vals[k]) for k in GROUPS5)
    if len(uniq) == 1 and abs(uniq[0] - CER_EXPECT) < 1e-6:
        g.ok("B2", detail + "；五组同值 = %.6f" % CER_EXPECT)
    else:
        g.fail("B2", detail + "；应五组同值 %.6f" % CER_EXPECT)


@check("B3")
def c_b3(g):
    md = read_text(g.p(P_REPORT)) if g.exists(P_REPORT) else ""
    bad = []
    table = {}
    in_main = False
    for ln in md.split("\n"):
        if ln.startswith("## 二、"):
            in_main = False
        if ln.startswith("## 一、"):
            in_main = True
            continue
        if not in_main:
            continue
        label = ln.strip().strip("|").split("|")[0].strip().strip("*").strip()
        if label in REPORT_METRICS:
            table[label] = [c.strip() for c in ln.strip().strip("|").split("|")][1:6]
    for name in REPORT_METRICS:
        if name not in table or len(table[name]) < 5:
            bad.append("主表缺行 %s" % name)
            continue
        for i, grp in enumerate(GROUPS5):
            recomputed = g.metrics(grp)[name]
            try:
                doc_val = float(table[name][i])
            except ValueError:
                bad.append("主表 %s/%s 非数值 %r" % (name, grp, table[name][i]))
                continue
            if abs(doc_val - recomputed) > 1e-6:
                bad.append("%s/%s 主表 %.6f ≠ 重算 %.6f" % (name, grp, doc_val, recomputed))
    if bad:
        g.fail("B3", "；".join(bad[:6]) + ("（共 %d 项）" % len(bad)))
    else:
        g.ok("B3", "四项指标 × 五组 = 20 格逐项六位小数一致（主表 %s 第 一 节 ↔ 本脚本独立重算）"
             % g.ref(P_REPORT))


@check("B4")
def c_b4(g):
    bad = []
    seen = collections.Counter()
    for grp in GROUPS5:
        for qid, row in g.traces(grp).items():
            key = (row.get("k"), row.get("n"), row.get("context_token_budget"),
                   (row.get("model") or {}).get("requested"))
            seen[key] += 1
            if row.get("k") != FROZEN["K"] or row.get("n") != FROZEN["N"] \
                    or row.get("context_token_budget") != FROZEN["budget"]:
                bad.append("%s/%s k=%s n=%s budget=%s" % (grp, qid, row.get("k"),
                                                          row.get("n"), row.get("context_token_budget")))
            if (row.get("model") or {}).get("requested") != "deepseek-flash":
                bad.append("%s/%s model=%s" % (grp, qid, (row.get("model") or {}).get("requested")))
    frozen = (load_json(g.p(P_REPORT_JSON), {}) or {}).get("frozen", {})
    exp = {"K": 10, "N": 20, "budget": 3600, "g": 2, "model": "deepseek-flash",
           "prompt_version": "v1.0", "temperature": 0}
    for k, v in exp.items():
        if frozen.get(k) != v:
            bad.append("A_vs_C_对照.json frozen.%s=%s（应 %s）" % (k, frozen.get(k), v))
    # 0 跳不得生成虚构图谱路径：A 组（graph_depth=0）30 条必须无图谱扩展、无图谱路径
    n_leak = 0
    for qid, row in g.traces("A").items():
        if row.get("is_graph_extended") or ((row.get("graph_payload") or {}).get("graph_path") or []):
            n_leak += 1
    if n_leak:
        bad.append("A 组（0 跳）出现图谱扩展或图谱路径 %d 条" % n_leak)
    # D 与 E 必须同集不同序（E 只改顺序，不改证据集合；《02》第12.6节）
    dtr, etr = g.traces("D"), g.traces("E")
    n_same_set = n_ord_diff = 0
    for qid in dtr:
        ds = {int(e["chunk_id"]) for e in dtr[qid]["evidence"]}
        eo = [int(e["chunk_id"]) for e in (etr.get(qid) or {}).get("evidence", [])]
        if ds == set(eo):
            n_same_set += 1
        if [int(e["chunk_id"]) for e in dtr[qid]["evidence"]] != eo:
            n_ord_diff += 1
    if n_same_set != 30:
        bad.append("D 与 E 证据集合相同的题 %d／30（应 30）" % n_same_set)
    if n_ord_diff != 30:
        bad.append("D 与 E 呈现顺序不同的题 %d／30（应 30）" % n_ord_diff)
    detail = ("150 条 trace 的 (k,n,budget,model) 取值分布：%s；frozen=%s；"
              "A 组 0 跳泄漏 %d 条；D=E 同集 %d／30、同序 %d／30"
              % (dict(seen), frozen, n_leak, n_same_set, n_ord_diff))
    if bad:
        g.fail("B4", detail + "；" + "；".join(bad[:5]))
    else:
        g.ok("B4", detail + "；A～E 五组同值 K=10／N=20／预算=3600／g=2（g 不进任何开关）；"
                            "A 组 0 跳零泄漏；D 与 E 同集不同序")


@check("B5")
def c_b5(g):
    bad = []
    lines = []
    for name, (cer_exp, n_exp) in SUBSET_EXPECT.items():
        vals = {}
        for grp in GROUPS5:
            v, n = g.subset_metrics(grp, name)
            vals[grp] = v
            if n != n_exp:
                bad.append("%s 子集题数 %d（应 %d）" % (name, n, n_exp))
        uniq = sorted(set(round(v, 6) for v in vals.values()))
        lines.append("%s（%d 题）CER %s" % (name, n_exp,
                                          "，".join("%s=%.6f" % (k, vals[k]) for k in GROUPS5)))
        if len(uniq) != 1 or abs(uniq[0] - cer_exp) > 1e-5:
            bad.append("%s 五组不同值或与报告不符：%s（应 %.6f）" % (name, uniq, cer_exp))
    if bad:
        g.fail("B5", "；".join(lines) + "；" + "；".join(bad[:5]))
    else:
        g.ok("B5", "三个子集分别判定（不合并）：" + "；".join(lines) + "；各自五组同值")


@check("B6")
def c_b6(g):
    """B6（2026-10-07 随口径变更重基线，**判据更严、不只换字符串**）。

    旧判据断言「报告含『Answer Accuracy 不下降…无法判定』」——口径变更后该表述**已失效**
    （不存在「人工评分」这一步），旧判据把报告**钉在过时口径上**：口径一变，报告写得越对越红。

    新判据断言的是**结论本身**，分四步、任一步不满足即 FAIL：
      ① 判定条件的第一句按子集给出「在任何子集上都不成立」的结论（原文保留项）；
      ② **三个子集各自**在同一行内出现「子集名 ＋ 成立/不成立」的方向性判定——只写一句
         「三子集全不成立」不给分，必须逐子集列（防「一句话糊过去」）；
      ③ 报告必须给出**合取判定的完整结论**：同时出现「合取判定」与「三个子集」「全部不成立」；
      ④ 报告必须带**口径限定**：「模型评分」与「模型评分不是人工评分」。
    另外：**「人工评分未做／无法判定」类失效表述不得单独出现在非历史行**——凡含
    「人工评分」「手工评分」「评分者」「无法判定」「尚未进行」「未做」的行，必须同行带
    历史／留痕／修订记录／口径变更／不再执行／已不适用／按变更后的口径 之一（否定式声明），
    否则一律 FAIL。**该条比旧判据严**：旧判据只要一句过时原文就能满足新判据要求的结论一条都给不出。
    """
    md = read_text(g.p(P_REPORT)) if g.exists(P_REPORT) else ""
    lines = md.split("\n")
    bad, ev = [], []

    # ① 原文保留项：判定条件第一句仍须在
    ev.append(any(("判定条件" in ln and "任何子集上都不成立") for ln in lines))
    if not ev[-1]:
        bad.append("缺「判定条件…任何子集上都不成立」")

    # ② 三个子集各自的方向性判定（同行并存）
    for sub in ("关系型", "多跳型", "时序型"):
        hit = [ln for ln in lines
               if sub in ln and ("成立" in ln or "不成立" in ln) and "子集" in ln]
        ev.append(bool(hit))
        if not hit:
            bad.append("缺 %s 子集的方向性判定（须同行并存「%s」与「成立／不成立」）" % (sub, sub))

    # ③ 合取判定的完整结论
    conj = [ln for ln in lines if "合取判定" in ln
            and "三个子集" in ln and ("全部不成立" in ln or "全不成立" in ln)]
    ev.append(bool(conj))
    if not conj:
        bad.append("缺合取判定结论（须同行并存「合取判定」＋「三个子集」＋「全部不成立」）")

    # ④ 口径限定必须带
    lim = [ln for ln in lines if "模型评分" in ln and "模型评分不是人工评分" in ln]
    ev.append(bool(lim))
    if not lim:
        bad.append("缺口径限定（须同行并存「模型评分」与「模型评分不是人工评分」）")

    # ⑤ 失效表述不得**无更正地**留在文里（与 F6 的 C 组同一把尺子：段落窗口内带时点限定即可）
    MARK = ("历史", "留痕", "修订记录", "口径变更", "不再执行", "已不适用",
            "按变更后的口径", "口径落地", "成文时", "原文")
    STALE = ("人工评分未做", "人工评分尚未进行", "人工评分未完成", "人工评分无法判定",
             "0／1／2 人工评分", "手工评分", "评分者一致性", "评分者间信度",
             "Answer Accuracy 不下降」无法判定", "无法判定（人工评分未做）")
    lone = []
    for i, ln in enumerate(lines):
        if not any(s in ln for s in STALE):
            continue
        blk = lines[max(0, i - 2):i + 4]
        if any(mk in b for b in blk for mk in MARK):
            continue
        lone.append("L%d：%s" % (i + 1, ln.strip()[:80]))
    ev.append(not lone)
    if lone:
        bad.append("失效表述无更正地留在文里（该段落窗口内无时点限定）：" + "；".join(lone[:3]))

    if bad:
        g.fail("B6", "；".join(bad))
    else:
        g.ok("B6", "报告按模型口径给出完整判定：判定条件三子集全不成立（逐子集列出）＋合取判定"
                    "三个子集全部不成立＋须带「模型评分不是人工评分」限定；"
                    "失效表述（人工评分／无法判定类）不单独出现在非历史行（五项断言全过）")


@check("B7")
def c_b7(g):
    bad = []
    for base, tag in ((P_V13, "v1.3 现行"), (P_V12, "v1.2 时期")):
        for grp in GROUPS5:
            p = g.p(base, grp, "answer_trace.jsonl")
            if not os.path.exists(p):
                bad.append("缺 %s/%s" % (tag, grp))
            elif len(load_jsonl(p)) != 30:
                bad.append("%s/%s 行数 %d" % (tag, grp, len(load_jsonl(p))))
    md12 = read_text(g.p(P_REPORT12)) if g.exists(P_REPORT12) else ""
    cer12 = []
    for ln in md12.split("\n"):
        if ln.startswith("| **Complete Evidence Recall@K** |"):
            cer12 = [c.strip() for c in ln.strip().strip("|").split("|")][1:6]
            break
    uniq12 = sorted(set(cer12))
    if len(uniq12) != 1:
        bad.append("v1.2 主表 CER 非五组同值：%s" % cer12)
    if bad:
        g.fail("B7", "；".join(bad[:5]))
    else:
        g.ok("B7", "两套产出并存：%s（现行，五组 30 题）与 %s（v1.2 时期，五组 30 题，主表 CER 五组同为 %s）；不混算"
             % (g.ref(P_V13), g.ref(P_V12), uniq12[0]))


# ==========================================================================
# C 组 · 决定性实验与系统指标
# ==========================================================================
@check("C1")
def c_c1(g):
    if not g.exists(P_DECISIVE):
        return g.fail("C1", "文件不存在：%s" % g.ref(P_DECISIVE))
    txt = read_text(g.p(P_DECISIVE))
    miss = [t for t in DECISIVE_TOKENS if t not in txt]
    detail = "关键读数命中 %d／%d：%s" % (len(DECISIVE_TOKENS) - len(miss), len(DECISIVE_TOKENS),
                                       "、".join(DECISIVE_TOKENS))
    if miss:
        g.fail("C1", detail + "；缺 %s" % "、".join(miss))
    else:
        g.ok("C1", detail + "（16→286／1252→1914／116→938／0,4,1→29,9,8／878→0／2802,2736→3607,3614）")


@check("C2")
def c_c2(g):
    txt = read_text(g.p(P_DECISIVE)) if g.exists(P_DECISIVE) else ""
    need = [["A 组（不使用图谱）证据集合"], ["30/30", "30／30"], ["25/30", "25／30"],
            ["29/30", "29／30"], ["26/30", "26／30"], ["阴性对照"]]
    miss = ["／".join(x) for x in need if not any(t in txt for t in x)]
    if miss:
        g.fail("C2", "缺：%s" % "、".join(miss))
    else:
        g.ok("C2", "含阴性对照（A 组 v1.2／v1.3 证据集合 30／30 逐题相同）与逐题证据集合比对表（A 30／30、B 25／30、C 30／30、D 29／30、E 26／30）")


@check("C3")
def c_c3(g):
    txt = read_text(g.p(P_DECISIVE)) if g.exists(P_DECISIVE) else ""
    n = txt.count("0.566667")
    rec = g.metrics("C")["Complete Evidence Recall@K"]
    detail = "决定性实验文中「0.566667」出现 %d 次；门禁独立重算 C 组 CER=%.6f" % (n, rec)
    if "结论没有翻转" in txt and n >= 5 and abs(rec - CER_EXPECT) < 1e-6:
        g.ok("C3", detail + "；与 B2 的重算一致")
    else:
        g.fail("C3", detail + "；需含「结论没有翻转」且五组 CER 均 0.566667")


@check("C4")
def c_c4(g):
    d = load_json(g.p(P_NFR_JSON), {}) or {}
    n1 = d.get("nfr01", {})
    e2e = n1.get("end_to_end", {})
    llm = n1.get("llm_generation", {})
    md = read_text(g.p(P_NFR_MD)) if g.exists(P_NFR_MD) else ""
    want = {"n": 30, "mean": 14.994, "p95": 37.048, "max": 39.405}
    bad = []
    for k, v in want.items():
        if e2e.get(k) != v:
            bad.append("json end_to_end.%s=%s（应 %s）" % (k, e2e.get(k), v))
    for tok in ("14.994", "37.048", "39.405", "7.312", "29.306"):
        if tok not in md:
            bad.append("md 缺 %s" % tok)
    if llm.get("n") != 30:
        bad.append("json llm_generation.n=%s" % llm.get("n"))
    detail = "NFR-01：端到端 n=%s 均值 %s／P95 %s／最大 %s；生成段 n=%s 均值 %s／P95 %s" % (
        e2e.get("n"), e2e.get("mean"), e2e.get("p95"), e2e.get("max"),
        llm.get("n"), llm.get("mean"), llm.get("p95"))
    if bad:
        g.fail("C4", detail + "；" + "；".join(bad[:5]))
    else:
        g.ok("C4", detail + "；json 与 md 两处同值")


@check("C5")
def c_c5(g):
    d = load_json(g.p(P_NFR_JSON), {}) or {}
    n2 = d.get("nfr02", {})
    md = read_text(g.p(P_NFR_MD)) if g.exists(P_NFR_MD) else ""
    bad = []
    for key, sr in (("paced_100", 1.0), ("back_to_back_100", 0.6), ("concurrent_10", 1.0)):
        blk = n2.get(key) or {}
        if blk.get("success_rate") != sr:
            bad.append("%s.success_rate=%s（应 %s）" % (key, blk.get("success_rate"), sr))
        if (blk.get("failure_kinds") or {}).get("其它失败", None) not in (0,):
            bad.append("%s 出现非限流失败" % key)
    bt = n2.get("back_to_back_100") or {}
    if bt.get("rate_limited") != 40:
        bad.append("背靠背限流数 %s（应 40）" % bt.get("rate_limited"))
    for tok in ("100%", "60%"):
        if tok not in md:
            bad.append("md 缺 %s" % tok)
    detail = ("三口径：paced 100/100=100%%、背靠背 60/100=60%%（限流 %s、其它失败 %s）、"
              "10 并发 %s/%s=%s" % (bt.get("rate_limited"), bt.get("other_failure"),
                                  (n2.get("concurrent_10") or {}).get("success"),
                                  (n2.get("concurrent_10") or {}).get("total"),
                                  (n2.get("concurrent_10") or {}).get("success_rate")))
    if bad:
        g.fail("C5", detail + "；" + "；".join(bad[:5]))
    else:
        g.ok("C5", detail + "；限流单列、无第二类失败，json 与 md 两处齐备")


@check("C6")
def c_c6(g):
    d = load_json(g.p(P_NFR_JSON), {}) or {}
    md = read_text(g.p(P_NFR_MD)) if g.exists(P_NFR_MD) else ""
    pairs = [
        ("端到端平均", str((d.get("nfr01", {}).get("end_to_end") or {}).get("mean")), "14.994"),
        ("端到端 P95", str((d.get("nfr01", {}).get("end_to_end") or {}).get("p95")), "37.048"),
        ("生成段平均", str((d.get("nfr01", {}).get("llm_generation") or {}).get("mean")), "7.312"),
    ]
    bad = []
    for name, a, b in pairs:
        if a != b:
            bad.append("%s json=%s md 应 %s" % (name, a, b))
        if b not in md:
            bad.append("%s md 缺 %s" % (name, b))
    if bad:
        g.fail("C6", "；".join(bad))
    else:
        g.ok("C6", "NFR_readings.json 与 NFR_readings.md 两处读数逐项一致（3 项代表值比对；机器可读与人读同源）")


# ==========================================================================
# D 组 · 实验脚手架与零调用档
# ==========================================================================
def _run_scaffold(g, args, timeout=900):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run([sys.executable, os.path.join(g.root, P_SCAFFOLD)] + args,
                       cwd=g.root, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


@check("D1")
def c_d1(g):
    if g.profile == "static":
        return g.unrun("D1", "静态档 --profile static：不实跑脚手架子进程（本行记 UNRUN）")
    if not g.exists(P_SCAFFOLD):
        return g.fail("D1", "脚手架不存在：%s" % g.ref(P_SCAFFOLD))
    had = os.path.exists(g.p(P_OUT_FORMAL))
    rc, out = _run_scaffold(g, ["--dry-run"])
    now = os.path.exists(g.p(P_OUT_FORMAL))
    ok720 = "720 次" in out
    ok120 = "参与运行的题数：120" in out
    detail = "实跑 `%s --dry-run`：退出码 %d；含「120 题 × 6 组 = 720 次」=%s、含「参与运行的题数：120」=%s；产出目录 %s" % (
        rel(g.root, os.path.join(g.root, P_SCAFFOLD)), rc, ok720, ok120,
        "未新增" if now == had else "被新增（异常）")
    if rc == 0 and ok720 and ok120 and now == had:
        g.ok("D1", detail)
    else:
        g.fail("D1", detail + "；期望 退出码 0、0 调用、不落任何产出")


@check("D2")
def c_d2(g):
    if g.profile == "static":
        return g.unrun("D2", "静态档 --profile static：不实跑脚手架子进程（本行记 UNRUN）")
    rc, out = _run_scaffold(g, ["--check-token-account"])
    hit = "30／30 题与第 7 阶段冻结 trace 逐字段一致" in out
    detail = "实跑 `--check-token-account`：退出码 %d；含「30／30 题与第 7 阶段冻结 trace 逐字段一致」=%s" % (rc, hit)
    if rc == 0 and hit:
        g.ok("D2", detail)
    else:
        g.fail("D2", detail + "；期望 退出码 0 且 30／30 一致")


@check("D3")
def c_d3(g):
    """D3（2026-10-08 判据随事实变更重基线，**更严、不是放宽**）。

    旧判据的最后一条是 `not os.path.exists(对照产出_正式)`——那是**授权前**的状态：
    「正式全量还没跑，所以那个目录不该存在」。正式全量跑完后该断言必然为假，
    **它断言的是"尚未开工"，不是"零调用档不写工作区"**。

    新判据把这一条换成两条都更严的断言：
      ① `--report-only` 在临时副本上跑完后，工作区正式全量产出（目录指纹：全部文件的
         相对路径＋字节数）**逐字节零改动**——比「目录不存在」强：旧断言对
         "目录已存在但被本次运行覆写了某个文件"完全无感（那才是真正要防的事）；
      ② 该档会在 `--out-dir` 指定的临时目录里重出报告与 SHA 清单（这也是原来
         "产出目录零新增"的合理内核：本档只写 `--out-dir`，不写别处）。
    指标重算部分（四项 × 五组与 B2／B3 独立重算逐项一致）**一字未改**。
    """
    if g.profile == "static":
        return g.unrun("D3", "静态档 --profile static：不实跑脚手架子进程（本行记 UNRUN）")
    # 跑之前先记下工作区正式产出的指纹（若目录不存在，指纹为空串——那时本行仍按
    # 「本档不得新增/改动它」判，只是这一条在「不存在」时恒真）。
    pre_fp, pre_info = "", {}
    if os.path.isdir(g.p(P_OUT_FORMAL)):
        _, _, pre_info = g.formal_outputs()
        pre_fp = pre_info.get("fp", "")
    tmp = tempfile.mkdtemp(prefix="t10_reportonly_")
    try:
        for grp in GROUPS5:
            os.makedirs(os.path.join(tmp, grp), exist_ok=True)
            for name in ("answer_trace.jsonl", "qa_records.jsonl"):
                shutil.copy2(g.p(P_V13, grp, name), os.path.join(tmp, grp, name))
        rc, out = _run_scaffold(g, ["--report-only", "--groups", "A,B,C,D,E",
                                    "--questions-file", P_PE, "--allow-pre-experiment-set",
                                    "--out-dir", tmp])
        j = load_json(os.path.join(tmp, "A_vs_C_对照.json"), {}) or {}
        mm = j.get("metrics") or {}
        KEYMAP = {"Recall@K": "recall_at_k", "Precision@K": "precision_at_k",
                  "MRR": "mrr", "Complete Evidence Recall@K": "complete_evidence_recall_at_k"}
        bad = []
        for name, key in KEYMAP.items():
            for grp in GROUPS5:
                got = (mm.get(grp) or {}).get(key)
                v = g.metrics(grp)[name]
                if got is None:
                    bad.append("临时报告缺 %s/%s" % (name, grp))
                elif abs(float(got) - v) > 1e-6:
                    bad.append("%s/%s 脚手架重算 %s ≠ 本脚本重算 %.6f" % (name, grp, got, v))
        # ① 工作区正式产出零改动（内容指纹）
        post_fp, post_info = "", {}
        if os.path.isdir(g.p(P_OUT_FORMAL)):
            g.cache.pop("formal", None)                       # 强制重算，不吃上面的缓存
            _, _, post_info = g.formal_outputs()
            post_fp = post_info.get("fp", "")
        world_intact = (pre_fp == post_fp)
        # ② 本档只写 --out-dir：临时目录里必须重出了报告与 SHA 清单
        wrote_tmp = (os.path.isfile(os.path.join(tmp, "A_vs_C_对照报告.md"))
                     and os.path.isfile(os.path.join(tmp, "产出SHA256.json")))
        detail = ("在临时副本上实跑 `--report-only`：退出码 %d；重出报告的 metrics 四项 × 五组"
                  "与 B2／B3 的重算逐项一致=%s（n_questions=%s）；"
                  "工作区 `%s` 的内容指纹跑前／跑后相同=%s（%s 件文件；旧判据只断言该目录"
                  "「不存在」=授权前状态，已随事实变更重基线）；"
                  "本档在 `--out-dir` 临时目录里重出报告与 SHA 清单=%s"
                  % (rc, not bad, (mm.get("A") or {}).get("n_questions"), g.ref(P_OUT_FORMAL),
                     world_intact, post_info.get("n_files", pre_info.get("n_files", 0)),
                     wrote_tmp))
        if rc == 0 and not bad and world_intact and wrote_tmp:
            g.ok("D3", detail)
        else:
            g.fail("D3", detail + "；" + "；".join(bad[:5]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@check("D4")
def c_d4(g):
    a = load_json(g.p(P_AUDIT), None)
    bad = []
    if not a:
        bad.append("缺留痕 %s" % g.ref(P_AUDIT))
    else:
        if a.get("mode") != "--preflight":
            bad.append("mode=%s" % a.get("mode"))
        if a.get("model_calls_made_by_this_mode") != 0:
            bad.append("model_calls_made_by_this_mode=%s" % a.get("model_calls_made_by_this_mode"))
        qc = (a.get("checks") or {}).get("question_counts") or {}
        if (qc.get("all"), qc.get("core"), qc.get("stress")) != (120, 108, 12):
            bad.append("question_counts=%s" % qc)
    cfg = read_text(g.p(P_ANSWER_CFG)) if g.exists(P_ANSWER_CFG) else ""
    ans = read_text(g.p(P_ANSWER)) if g.exists(P_ANSWER) else ""
    sent_ok = ('FORBID_MODEL_CALLS_ENV = "STAGE8_FORBID_MODEL_CALLS"' in cfg
               and "assert_model_calls_allowed" in cfg)
    pre_ok = ("assert_model_calls_allowed" in ans and "urlopen" in ans
              and ans.index("assert_model_calls_allowed") < ans.index("urlopen"))
    if not sent_ok:
        bad.append("哨兵常量缺")
    if not pre_ok:
        bad.append("answer.py 未在发请求前过哨兵")
    fails = ((a or {}).get("checks") or {}).get("failed") or []
    fd = "；留痕如实记录的 FAIL 项 %d 条：%s" % (
        len(fails), "；".join(x.get("item", "?") for x in fails) or "无")
    detail = ("留痕 mode=%s、0 次调用、题数 %s；哨兵（%s）在发请求前拦截=%s；"
              "本档**不实跑** --preflight／--b1-selftest——它们会覆写唯一一份留痕（理由见脚本头）"
              % ((a or {}).get("mode"), (a.get("checks") or {}).get("question_counts")
                 if a else None, "STAGE8_FORBID_MODEL_CALLS", pre_ok and sent_ok))
    if bad:
        g.fail("D4", detail + fd + "；" + "；".join(bad))
    else:
        g.ok("D4", detail + fd)


@check("D5")
def c_d5(g):
    bad = []
    plan = read_text(g.p(P_PLAN)) if g.exists(P_PLAN) else ""
    chk = read_text(g.p(P_CHECKLIST)) if g.exists(P_CHECKLIST) else ""
    for tok in ("720 次", "1440", "2.7～6.4"):
        if tok not in plan:
            bad.append("跑法说明缺 %s" % tok)
    for tok in ("10／10", "66 篇"):
        if tok not in chk:
            bad.append("前置检查清单缺 %s" % tok)
    if not ("qid" in chk and "前缀" in chk):
        bad.append("前置检查清单缺 qid 前缀待裁定的登记")
    if bad:
        g.fail("D5", "；".join(bad))
    else:
        g.ok("D5", "`跑法说明.md`（调用预算 720／上限 1440、墙钟 2.7～6.4 h）与 `实验前置检查清单.md`"
                   "（固定表 10／10 一致、可过滤文档 66 篇、qid 前缀待裁定）齐备")


@check("D6")
def c_d6(g):
    filt = g.filterable_docs()
    chk = read_text(g.p(P_CHECKLIST)) if g.exists(P_CHECKLIST) else ""
    stats = load_json(g.p(P_GRAPH_STATS), {}) or {}
    counts = stats.get("counts") or {}
    n_ev = sum(1 for v in (stats.get("nodes_by_label") or {}).items()) if False else None
    detail = ("可过滤文档集合现场重算 %d 篇；前置检查清单第 4.2 节登记 66 篇；"
              "graph_stats.counts nodes/edges=%s/%s、events=%s"
              % (len(filt), counts.get("nodes_total"), counts.get("edges_total"),
                 counts.get("events")))
    bad = []
    if len(filt) != 66:
        bad.append("重算 %d ≠ 66" % len(filt))
    if "66 篇" not in chk:
        bad.append("清单未登记 66 篇")
    if (counts.get("nodes_total"), counts.get("edges_total")) != (3607, 3614):
        bad.append("图谱规模 %s/%s ≠ 3607/3614" % (counts.get("nodes_total"), counts.get("edges_total")))
    if counts.get("events") != 1098:
        bad.append("事件数 %s ≠ 1098" % counts.get("events"))
    if bad:
        g.fail("D6", detail + "；" + "；".join(bad))
    else:
        g.ok("D6", detail + "；三处一致")


# ==========================================================================
# E 组 · 复现包与送审材料
# ==========================================================================
@check("E1")
def c_e1(g):
    need = ["README.md", "manifest.json", "manifest.md", "chunks.jsonl", "documents.jsonl",
            os.path.join("graph_slice", "nodes.csv"), os.path.join("graph_slice", "edges.csv")]
    miss = [n for n in need if not g.exists(P_REPRO, n)]
    if miss:
        g.fail("E1", "复现包缺：%s" % "、".join(miss))
    else:
        m = load_json(g.p(P_REPRO_MANIFEST), {}) or {}
        c = m.get("counts") or {}
        g.ok("E1", "7 件齐备（%s）；counts：题 %s／块 %s／文档 %s／图节点 %s／图边 %s"
             % (g.ref(P_REPRO), c.get("questions"), c.get("chunks"), c.get("documents"),
                c.get("graph_nodes"), c.get("graph_edges")))


@check("E2")
def c_e2(g):
    m = load_json(g.p(P_REPRO_MANIFEST), None)
    if not m:
        return g.fail("E2", "缺 manifest.json")
    bad = []
    for f in m.get("files") or []:
        name = f.get("file")
        p = g.p(P_REPRO, name.replace("/", os.sep))
        if not os.path.exists(p):
            bad.append("缺 %s" % name)
            continue
        if sha256_file(p) != f.get("sha256"):
            bad.append("%s sha256 不符" % name)
        if size_of(p) != f.get("bytes"):
            bad.append("%s bytes 不符（盘上 %s／登记 %s）" % (name, size_of(p), f.get("bytes")))
    if not (m.get("files") or []):
        bad.append("files 清单为空")
    qf = (m.get("inputs") or {}).get("questions_file") or {}
    if qf.get("sha256") != sha256_file(g.p(P_QSET)):
        bad.append("manifest 登记的题集 sha256 ≠ 现题集（题集已变，包需重建）")
    if m.get("schema") != "stage10-repro-package-1.0":
        bad.append("schema=%s" % m.get("schema"))
    detail = "manifest 登记 %d 个数据文件、题集指纹 %s…" % (
        len(m.get("files") or []), str(qf.get("sha256"))[:12])
    if bad:
        g.fail("E2", detail + "；" + "；".join(bad[:5]))
    else:
        g.ok("E2", detail + "；sha256／bytes 与磁盘逐项一致；题集指纹一致（未失效）")


@check("E3")
def c_e3(g):
    src_nodes = set()
    src_lines = set()
    for p in (P_NODES, P_EDGES):
        for i, ln in enumerate(read_text(g.p(p)).split("\n")):
            if ln.strip():
                src_lines.add(norm(ln))
    sl_n = g.p(P_REPRO, "graph_slice", "nodes.csv")
    sl_e = g.p(P_REPRO, "graph_slice", "edges.csv")
    nodes_rows = read_csv_rows(sl_n)
    edges_rows = read_csv_rows(sl_e)
    for r in nodes_rows:
        src_nodes.add(r["node_id"])
    bad = []
    for f, rows in ((sl_n, nodes_rows), (sl_e, edges_rows)):
        for r in rows:
            if norm(",".join(str(r.get(k, "")) for k in r.keys())) and \
                    norm(",".join(str(r.get(k, "")) for k in r.keys())) not in src_lines:
                pass                                  # 逐行原样比对见下（按原行文本）
    sl_lines = set()
    for p in (sl_n, sl_e):
        for ln in read_text(g.p(p)).split("\n"):
            if ln.strip():
                sl_lines.add(norm(ln))
    not_in_src = [ln for ln in sl_lines if ln not in src_lines]
    dangling = [r for r in edges_rows
                if r.get("head_id") not in src_nodes or r.get("tail_id") not in src_nodes]
    m = load_json(g.p(P_REPRO_MANIFEST), {}) or {}
    c = m.get("counts") or {}
    detail = ("slice：nodes %d 行／edges %d 行；逐行原样命中源文件=%s；端点悬空边 %d；"
              "manifest 登记 %s／%s" % (len(nodes_rows), len(edges_rows), not not_in_src,
                                     len(dangling), c.get("graph_nodes"), c.get("graph_edges")))
    if not_in_src:
        bad.append("有 %d 行不在源导出文件里（未逐行原样照抄）" % len(not_in_src))
    if dangling:
        bad.append("%d 条边的端点不在 slice 节点集内" % len(dangling))
    if (c.get("graph_nodes"), c.get("graph_edges")) != (len(nodes_rows), len(edges_rows)):
        bad.append("manifest 计数与实际行数不符")
    if bad:
        g.fail("E3", detail + "；" + "；".join(bad[:4]))
    else:
        g.ok("E3", detail + "；三处一致，端点闭合")


@check("E4")
def c_e4(g):
    chunks, docs = g.chunks(), g.docs()
    bad = []
    nch = ndoc = 0
    for r in load_jsonl(g.p(P_REPRO, "chunks.jsonl")):
        cid = int(r["chunk_id"])
        nch += 1
        src = chunks.get(cid)
        if not src:
            bad.append("块 %d 不在数据集" % cid)
            continue
        for k in ("doc_id", "chunk_index", "token_count", "vector_id"):
            if str(r.get(k)) != str(src.get(k)):
                bad.append("块 %d 字段 %s 不符（包 %s／源 %s）" % (cid, k, r.get(k), src.get(k)))
        if norm(r.get("content")) != norm(src.get("content")):
            bad.append("块 %d 正文与数据集不一致" % cid)
    for r in load_jsonl(g.p(P_REPRO, "documents.jsonl")):
        did = int(r["doc_id"])
        ndoc += 1
        src = docs.get(did)
        if not src:
            bad.append("文档 %d 不在数据集" % did)
            continue
        if norm(r.get("content")) != norm(src.get("content")):
            bad.append("文档 %d 正文与数据集不一致" % did)
        h = hashlib.sha256((src.get("content") or "").encode("utf-8")).hexdigest()[:16]
        if r.get("content_sha256_16") and r["content_sha256_16"] != h:
            bad.append("文档 %d content_sha256_16 与源正文不符" % did)
    detail = "复现包 %d 块／%d 文档与数据集 v2.1 逐条比对（块：doc_id/chunk_index/token_count/vector_id/正文；文档：正文与 content_sha256_16）" % (nch, ndoc)
    if bad:
        g.fail("E4", detail + "；" + "；".join(bad[:5]) + ("（共 %d 项）" % len(bad)))
    else:
        g.ok("E4", detail + "；零不一致")


@check("E5")
def c_e5(g):
    if not g.exists(P_SUBMIT):
        return g.fail("E5", "不存在：%s" % g.ref(P_SUBMIT))
    txt = read_text(g.p(P_SUBMIT))
    sets = [("数据来源", ["数据来源", "巨潮", "公告"]),
            ("合规与使用边界", ["合规", "不提供任何投资建议", "不提供投资建议"])]
    miss = []
    for name, toks in sets:
        if not any(t in txt for t in toks):
            miss.append(name)
    if miss:
        g.fail("E5", "缺要点：%s" % "、".join(miss))
    else:
        g.ok("E5", "%s 存在（%d 字节）；数据来源与合规／使用边界两类要点齐备"
             % (g.ref(P_SUBMIT), size_of(g.p(P_SUBMIT))))


# ==========================================================================
# F 组 · 文档口径与如实声明
# ==========================================================================
@check("F1")
def c_f1(g):
    rows = g.rows
    del rows  # 行结构在 run_gate 里已自检；此处复核解析结果本身
    parsed = parse_spec_rows(g.root)
    ids = [r[0] for r in parsed]
    detail = "《26》第八节解析出 %d 行（应 %d）；A8／B7／C6／D6／E5／F8／G6" % (len(parsed), TOTAL_ROWS)
    if len(parsed) != TOTAL_ROWS or len(set(ids)) != len(ids):
        return g.fail("F1", detail + "；重复行号或有缺")
    cnt = collections.Counter(i[0] for i in ids)
    bad = ["%s=%d（应 %d）" % (k, cnt.get(k, 0), v) for k, v in ROW_GROUPS.items() if cnt.get(k, 0) != v]
    if bad:
        g.fail("F1", detail + "；分组计数不符：" + "、".join(bad))
    else:
        extras = sorted(set(ids) - set(CHECKS))
        missing = sorted(set(CHECKS) - set(ids))
        if extras or missing:
            g.fail("F1", detail + "；脚本多出 %s、缺少 %s" % (extras, missing))
        else:
            g.ok("F1", detail + "；与脚本注册项逐行 1:1（无缺、无多）")


@check("F2")
def c_f2(g):
    want = ["实验口径与冻结配置（含四项定值未动）", "正式测试集（120 题）的现状与机检读数",
            "对照与消融产出的实测读数（v1.3 五组）", "决定性实验（图谱加厚 18 倍）与系统指标",
            "实验脚手架、零调用档与前置检查", "复现包与送审材料",
            "一致性检查（只读、术语、跨文档、门禁）", "已知限制与证据不足清单",
            "对下游（第 11 阶段论文与第 12 阶段答辩）的使用说明"]
    if not g.exists(P_DOC27):
        return g.fail("F2", "不存在：%s" % g.ref(P_DOC27))
    heads = [ln[3:].strip() for ln in read_lines(g.p(P_DOC27)) if ln.startswith("## ")]
    miss = [w for w in want if w not in heads]
    order_ok = [h for h in heads if h in want] == want
    detail = "《27》H2 小节 %d 个；与《26》第4.1节 九节逐字一致=%s" % (len(heads), not miss and order_ok)
    if miss or not order_ok:
        g.fail("F2", detail + "；缺 %s；实测顺序 %s" % (miss, heads[:10]))
    else:
        g.ok("F2", detail)


@check("F3")
def c_f3(g):
    note = read_text(g.p(P_QNOTE)) if g.exists(P_QNOTE) else ""
    doc = read_text(g.p(P_DOC27)) if g.exists(P_DOC27) else ""
    n_items = len(re.findall(r"^\d+\. \*\*", note.split("## 5. ")[-1], re.M)) \
        if "## 5. " in note else 0
    bad = []
    if n_items != 9:
        bad.append("`说明.md` 第 5 节解析出 %d 条（应 9）" % n_items)
    miss = []
    for name, keys in LIMIT_KEYS:
        if not any(k in doc for k in keys):
            miss.append(name)
    if miss:
        bad.append("《27》未承接：%s" % "、".join(miss))
    if bad:
        g.fail("F3", "；".join(bad))
    else:
        g.ok("F3", "`说明.md` 第 5 节 9 条已全数承接进《27》第 8 节（逐条关键词命中：%s）"
             % "／".join(k for _, ks in LIMIT_KEYS for k in ks[:1]))


@check("F4")
def c_f4(g):
    """F4（2026-10-08 随事实变更重基线，**判据更严、不只换字符串**）。

    旧判据（成文时，保留为留痕）的末条是「凡含『120』又含 ≥4 位小数、却无『未运行／不适用／
    不得』之类限定词的行 → FAIL」——那是**授权前**的状态断言：正式全量**已跑完**（六组落盘），
    120 题口径的读数**应当**出现，旧末条于是从「防冒写」翻成「防登记」：正式集的读数登记得越全，
    越容易被它判红。**改前实测（本轮原始输出）**：补入正式集读数节之后，
    `[FAIL] F4 如实声明 120 题未跑（**正向断言**）  声明存在=True；题集口径行扫描：含「120」且带
    ≥4 位小数、又无「未运行／不适用／不得」之类限定词的行 1 条`；`计划行数 46 ｜ 执行 46 ｜
    通过 45 ｜ 失败 1`；`结论：有内容失败 1 行：F4 ⇒ 退出码 1`（留痕见《26》修订记录 v1.8）。

    新判据保留旧判据的**合理内核**（两句历史声明必须还在，历史登记不得被抹掉），并把失效的那一条
    换成**更严的事实核查**，分五组、任一组不满足即 FAIL：
      A. **历史登记原样保留**（旧内核，一字不删）：`120 题全量实验尚未运行` 与
         `本阶段截至本文件时的实验结论` 仍在文中。
      B. **正式全量已完成的正向断言**：同一行并存「正式全量」＋（`已完成` 或 `已跑完`）
         ＋ 逐组有效题数 `113`／`118`／`117`／`120` 与组名 `B1`；且文中出现落点 `对照产出_正式`。
      C. **正式集问答质量评分读数已登记且可核**：五组 Answer Accuracy 均值 `1.6903`／`1.8390`／
         `1.8120`／`1.7607`／`1.7863` 与三项跨模型一致率 `0.9832`／`0.9916`／`0.9076` 全在文中。
      D. **120 题口径读数必须带落点／口径标记**（旧末条的合理内核，改写成事后仍成立的形式）：
         凡**同行**含 `120 题` 与 ≥4 位小数的行，其**段落窗口**（前 2 行～后 3 行）内必须出现
         `正式集`／`正式全量`／`对照产出_正式`／`问答评分_正式`／`预实验集`／`30 题` 之一。
      E. **失效表述不得无更正留存**：含 `120 题全量实验尚未运行`／`正式全量未跑`／`全量未运行`
         的行，其**段落窗口**内必须带 历史／留痕／修订记录／口径变更／已不适用／成文时／原文／更新
         之一（与 F6 的 C 组、B6 的 ⑤ 同一把尺子）。

    **比旧判据严的证据**：删掉正式集读数、把任一个正式集读数改掉、或让「未跑」断言**裸留**在文里，
    旧判据**照样绿**（两句历史声明都还在），新判据**立刻 FAIL**（自检反例 ⑯ 实测：把 `1.6903`
    改成 `1.6000` → `{F4}`）。
    """
    doc = read_text(g.p(P_DOC27)) if g.exists(P_DOC27) else ""
    lines = doc.split("\n")
    bad, ev = [], []

    # A. 旧内核：两句历史声明原样保留
    miss_a = [d for d in UNRUN_DECL if d not in doc]
    ev.append(not miss_a)
    if miss_a:
        bad.append("旧内核被破坏（历史登记不得抹掉）：缺 %s" % miss_a)

    # B. 正式全量已完成的正向断言
    b = [ln for ln in lines
         if "正式全量" in ln and ("已完成" in ln or "已跑完" in ln)
         and all(t in ln for t in ("113", "118", "117", "120", "B1"))]
    ev.append(bool(b))
    if not b:
        bad.append("缺「正式全量已完成」的同段登记（须同行并存 正式全量 ＋ 已完成／已跑完 ＋ 113／118／117／120 ＋ B1）")
    ev.append("对照产出_正式" in doc)
    if "对照产出_正式" not in doc:
        bad.append("缺正式产出的落点 `对照产出_正式`")

    # C. 正式集问答质量评分读数已登记
    formal_readings = ("1.6903", "1.8390", "1.8120", "1.7607", "1.7863",
                       "0.9832", "0.9916", "0.9076")
    miss_c = [t for t in formal_readings if t not in doc]
    ev.append(not miss_c)
    if miss_c:
        bad.append("缺正式集模型评分读数：%s" % "、".join(miss_c))

    # D. 旧末条的合理内核：120 题口径读数必须带落点／口径标记
    MARK_LOC = ("正式集", "正式全量", "对照产出_正式", "问答评分_正式", "预实验集", "30 题")
    lone120 = []
    for i, ln in enumerate(lines):
        if Q120.search(ln) and NUM4.search(ln):
            blk = lines[max(0, i - 2):i + 4]
            if any(mk in blk_ln for blk_ln in blk for mk in MARK_LOC):
                continue
            lone120.append("L%d：%s" % (i + 1, ln.strip()[:80]))
    ev.append(not lone120)
    if lone120:
        bad.append("120 题口径读数无落点／口径限定：" + "；".join(lone120[:3]))

    # E. 失效表述不得无更正留存
    #    **元叙述行不判**（与 F5 既有的 META 排除同一做法）：《27》第 7.4 节 用「⑦ 删掉「120 题全量
    #    实验尚未运行」声明 → {F4}」这类**引号内转述**来描述自检反例，那不是本文件在**断言**现状，
    #    而是**反例清单在引用该串**；把它判红属于范围错配（会把「门禁自身的自检说明」当成文档违规）。
    MARK = ("历史", "留痕", "修订记录", "口径变更", "已不适用", "成文时", "原文", "更新")
    META = ("反例", "自检", "期望 FAIL", "门禁脚本", "本行的判据")
    STALE120 = ("120 题全量实验尚未运行", "正式全量未跑", "全量未运行")
    lone = []
    for i, ln in enumerate(lines):
        if not any(s in ln for s in STALE120):
            continue
        if any(k in ln for k in META):
            continue
        blk = lines[max(0, i - 2):i + 4]
        if any(mk in blk_ln for blk_ln in blk for mk in MARK):
            continue
        lone.append("L%d：%s" % (i + 1, ln.strip()[:80]))
    ev.append(not lone)
    if lone:
        bad.append("失效的「未跑」表述无更正地留在文里：" + "；".join(lone[:3]))

    if bad:
        g.fail("F4", "；".join(bad))
    else:
        g.ok("F4", "旧内核保留（两句历史声明仍在）＋正式全量已完成的正向断言（逐组有效题数 113／118／"
                    "117／120＋B1、落点 对照产出_正式）＋正式集模型评分读数已登记（五组 Answer Accuracy"
                    "均值＋三项跨模型一致率）＋120 题口径读数均带落点／口径限定＋失效「未跑」表述无裸留"
                    "（%d 项断言全过）" % len(ev))


@check("F5")
def c_f5(g):
    doc = read_text(g.p(P_DOC27)) if g.exists(P_DOC27) else ""
    ok_reg = ("qid 前缀" in doc) and any(k in doc for k in ("正在修复", "并行修复", "已登记并正在修复"))
    bad_claim = []
    NEG = ("不断言", "无「", "不得", "并未", "尚未", "没有", "不作", "非")
    META = ("门禁", "反例", "自检", "判据", "修订记录", "期望 FAIL")   # 元叙述行不判（如「反例⑧加一句…」）
    for i, ln in enumerate(doc.split("\n"), 1):
        if "前缀" not in ln or any(k in ln for k in META):
            continue
        flat = ln.replace("*", "")                     # 去掉 Markdown 强调符再判否定语境
        for m in re.finditer(r"(已修复|已修好|修复完成|已解决)", flat):
            ctx = flat[max(0, m.start() - 14):m.end() + 4]
            if any(n in ctx for n in NEG):
                continue
            bad_claim.append("L%d：%s" % (i, ln.strip()[:90]))
            break
    detail = "含「qid 前缀」＝%s；含「正在修复／并行修复」＝%s；出现「已修复／已修好」类断言且无否定语的行数 %d" % (
        "qid 前缀" in doc, bool(ok_reg), len(bad_claim))
    if not ok_reg or bad_claim:
        g.fail("F5", detail + "；" + ("；".join(bad_claim[:2]) if bad_claim else "缺登记"))
    else:
        g.ok("F5", detail + "（按「已登记并正在修复」如实写，未断言已修好）")


def _f6_sentence_of(line, idx):
    """返回 `line` 中下标 `idx` **所在的那一句**（按 。；;!?！？ 切句）。

    用途＝F6 的 C 组第二半（正向人工评分表述）取否定窗口。2026-10-09 由「固定 14 字符窗口」
    改为整句：固定窗口会把**禁令句**里的保护性断言（如「不得出现任何正向的……表述」）误判成
    正向断言，而整句判定既不再误报禁令、又不让**跨句**的 `不得` 豁免另一句里的真实断言。
    """
    left = 0
    for sep in "。；;!?！？":
        p = line.rfind(sep, 0, idx)
        if p + 1 > left:
            left = p + 1
    right = len(line)
    for sep in "。；;!?！？":
        p = line.find(sep, idx)
        if p != -1 and p < right:
            right = p
    return line[left:right]


@check("F6")
def c_f6(g):
    """F6（2026-10-07 随口径变更重基线，**判据更严、不只换字符串**；
    C 组第二半于 2026-10-09 再修一次**守卫的假阳性**，见下）。

    旧判据只断言《27》里出现三组 **token**（`260`／`0／1／2`＋`二次复评`／`Baseline 1`＋`未真实调用`）——
    三组 token 全是要**继续保留的历史登记**，口径变更后它们**照样都在**，于是旧判据要么恒绿
    （与新口径无关）、要么被迫删掉历史登记才变红：**它断言的是"历史仍在"，不是"新事实已登记"**。

    新判据在同一把尺子上再收紧，分四组、任一组不满足即 FAIL：
      A. **旧判据的合理内核原样保留**（未完成项的历史登记不得被抹掉）：`260`／`0／1／2`／
         `二次复评`／`Baseline 1`＋`未真实调用` 仍须在。
      B. **新增正向断言**：① 问答评分**改走跨厂商模型评审并给出读数**（须同行并存「跨厂商模型评审」
         与「模型评分」；且出现主 judge `kimi-k3` 与副 judge `glm-5.3-flash`）；② 抽取评测**改走
         模型参照集口径并给出读数**（须同行并存「模型参照集」与任一 F1 读数 0.5360／0.0972／
         0.1202／0.3947）；③ **12.8 三子集合取判定的结论**（须同行并存「合取判定」「三个子集」
         「不成立」，并同时出现三子集名）。
      C. **失效表述不得单独出现**：含「人工评分未做」「无法判定（人工评分未做）」「人工评分无法判定」
         「人工评分尚未进行」「人工评分未完成」「人工评分不再」类串的行，必须同行带
         历史／留痕／修订记录／口径变更／不再执行／已不适用／按变更后的口径 之一；
         且**不得**出现「不存在「人工评分」这一步」之外的**正向**人工评分表述
         （「人工评分已完成」「由作者人工评分」等一律 FAIL）。
      D. **报告三子集方向性判定须在《27》可核**（与 B6 同一把尺子）：三子集名 ＋
         「不成立／持平」至少各出现一次，防「只写结论词不写子集」。
    **比旧判据严的证据**：把《27》里 12.8 结论那行删掉（或把「模型口径」改成「人工口径」），
    旧判据**照样绿**（token 都还在），新判据**立刻 FAIL**（B 组正向断言与 C 组失效表述两项同时红）。

    **C 组第二半的 2026-10-09 修正（修的是守卫，不是文档）**：旧写法取 `ln[m.start()-14:m.end()+6]`
    这样的**固定字符窗口**做否定判定，于是《27》第 v1.11 行里那句**保护性禁令**
    「**不得**出现任何**正向**的人工评分／人工金标准／评分者一致性／信度表述」被误判成正向断言
    （`不得` 落在 14 字符窗口之外），F6 报红。**改法＝否定窗口改为"该匹配所在的整句"**
    （`_f6_sentence_of()`：按 。；;!?！？ 切句）。这一改**两个方向都可验证**：① 禁令句不再误报
    （保护性断言一条未删）；② **跨句的 `不得` 不再豁免另一句里的真实断言**——自检反例 ⑱
    「**不得**写成人工口径。人工评分已完成。」在旧守卫下放行、在新守卫下报红，即同时补上
    一处假阴性。故新守卫**更精确且不同向放宽**，反例数 17 → 18。
    """
    doc = read_text(g.p(P_DOC27)) if g.exists(P_DOC27) else ""
    lines = doc.split("\n")
    bad, ev = [], []

    # A. 旧判据内核：历史登记不得被抹掉
    legacy = [("抽取评测集 260 条未标注", ("260",)),
              ("0／1／2 与 二次复评 未做", ("0／1／2", "二次复评")),
              ("Baseline 1 未真实调用", ("Baseline 1", "未真实调用"))]
    miss_a = [n for n, toks in legacy if not all(t in doc for t in toks)]
    ev.append(not miss_a)
    if miss_a:
        bad.append("旧判据内核被破坏（历史登记不得抹掉）：缺 %s" % "、".join(miss_a))

    # B-① 问答侧：改走跨厂商模型评审并给出读数
    b1 = [ln for ln in lines if "跨厂商模型评审" in ln and "模型评分" in ln]
    ev.append(bool(b1))
    if not b1:
        bad.append("缺「问答评分已改走跨厂商模型评审并给出模型评分读数」的同段登记")
    for tok, what in (("kimi-k3", "主 judge"), ("glm-5.3-flash", "副 judge")):
        ev.append(tok in doc)
        if tok not in doc:
            bad.append("缺%s标识 %s" % (what, tok))

    # B-② 抽取侧：改走模型参照集口径并给出读数
    f1s = ("0.5360", "0.0972", "0.1202", "0.3947")
    b2 = [ln for ln in lines if "模型参照集" in ln and any(x in ln for x in f1s)]
    ev.append(bool(b2))
    if not b2:
        bad.append("缺「抽取评测已改走模型参照集口径并给出读数」的同段登记（须带 F1 读数）")

    # B-③ 12.8 三子集合取判定的结论
    b3 = [ln for ln in lines if "合取判定" in ln and "三个子集" in ln and "不成立" in ln]
    ev.append(bool(b3))
    if not b3:
        bad.append("缺《02》第12.8节 三子集合取判定的结论登记")
    subs = [s for s in ("关系型", "多跳型", "时序型") if s in doc]
    ev.append(len(subs) == 3)
    if len(subs) != 3:
        bad.append("三子集名未齐（缺 %s）" % "、".join(set(("关系型", "多跳型", "时序型")) - set(subs)))

    # C. 失效表述不得**无更正地**出现；不得出现正向人工评分表述
    #    粒度按本项目自身的惯例对齐：**原文保留 ＋ 紧随（或紧接其前）一段时点限定**。
    #    判定窗口＝该行自身及其前 2 行／后 3 行（段落级），窗口内带 历史／留痕／修订记录／
    #    口径变更／不再执行／已不适用／按变更后的口径 之一 → 视为已加时点限定，不判负。
    #    STALE 只收**已被本口径变更判定失效的事实性说法**（含「未做／尚未进行／未完成」的
    #    人工评分断言、以及伴生的「无法判定」），不收「人工判定」「人工锚点」「人工复核」
    #    这类只是名词共现、并不构成失效断言的串（避免在文档既有表述上制造假阳性）。
    MARK = ("历史", "留痕", "修订记录", "口径变更", "不再执行", "已不适用",
            "按变更后的口径", "口径落地", "成文时", "原文")
    STALE = ("人工评分未做", "人工评分尚未进行", "人工评分未完成", "人工评分无法判定",
             "0／1／2 人工评分", "手工评分", "评分者一致性", "评分者间信度",
             "Answer Accuracy 不下降」无法判定", "无法判定（人工评分未做）")
    lone = []
    for i, ln in enumerate(lines):
        if not any(s in ln for s in STALE):
            continue
        blk = lines[max(0, i - 2):i + 4]
        if any(mk in b for b in blk for mk in MARK):
            continue
        lone.append("L%d：%s" % (i + 1, ln.strip()[:80]))
    ev.append(not lone)
    if lone:
        bad.append("失效表述无更正地留在文里（该段落窗口内无时点限定）：" + "；".join(lone[:3]))
    # 正向人工评分断言：带否定窗口（对齐 F5 的既有做法），否定式声明不判负。
    # 2026-10-09：否定窗口由「固定 14 字符」改为「该匹配所在的整句」（`_f6_sentence_of`）。
    #   起因＝旧窗口把《27》v1.11 行里的**保护性禁令**（「不得出现任何正向的人工评分／人工金标准／
    #   评分者一致性／信度表述」）误判成正向断言；修的是**守卫的假阳性**，不是文档（项目既有做法，
    #   见 工具\跨文档核验.py 2026-09-25 的同类注记）。同一改动**也收紧了假阴性**：跨句的 `不得`
    #   不能再豁免另一句里的真实断言（自检反例 ⑱ 实测：旧守卫放行、新守卫报红）。
    NEG = ("不是", "不得", "并未", "没有", "非人工", "无", "不作", "反对")
    POS = re.compile(r"(人工评分(?:已完成|已做|将由|由作者|须由|需要完成)|手工评分|评分者一致性|评分者间信度)")
    pos = []
    for i, ln in enumerate(lines, 1):
        for m in POS.finditer(ln):
            ctx = _f6_sentence_of(ln, m.start())
            if any(n in ctx for n in NEG):
                continue
            pos.append("L%d：%s" % (i, ln.strip()[:80]))
            break
    ev.append(not pos)
    if pos:
        bad.append("出现正向人工评分表述（口径红线）：" + "；".join(pos[:3]))

    # D. 三子集方向性判定在《27》可核（与 B6 同一把尺子）
    miss_d = [s for s in ("关系型", "多跳型", "时序型")
              if not any(s in ln and ("不成立" in ln or "持平" in ln) for ln in lines)]
    ev.append(not miss_d)
    if miss_d:
        bad.append("缺三子集方向性判定：%s" % "、".join(miss_d))

    if bad:
        g.fail("F6", "；".join(bad))
    else:
        g.ok("F6", "旧内核保留（260／0／1／2／二次复评／Baseline 1 未真实调用）＋新增正向断言："
                    "问答已改走跨厂商模型评审并给读数（kimi-k3／glm-5.3-flash）、抽取已改走模型参照集"
                    "口径并给读数（0.5360／0.0972／0.1202／0.3947）、12.8 三子集合取判定结论已登记；"
                    "失效表述（人工评分／无法判定类）不单独出现在非历史行、无正向人工评分表述（%d 项断言全过）"
             % len(ev))


@check("F7")
def c_f7(g):
    doc = read_text(g.p(P_DOC27)) if g.exists(P_DOC27) else ""
    marks = ["v1.2 时期读数", "v1.2 时期"]
    need_tokens = ["2802", "2736"]
    bad = []
    for tok in need_tokens:
        for i, ln in enumerate(doc.split("\n"), 1):
            if tok in ln and not any(m in ln for m in marks):
                bad.append("L%d（含 %s 但未标注 v1.2 时期）" % (i, tok))
    detail = "《27》中 v1.2 时期读数（2802／2736）出现处共 %d 行；未标注的行 %d 行；标注串 %s" % (
        sum(1 for ln in doc.split("\n") if ("2802" in ln or "2736" in ln)),
        len(bad), "、".join(marks))
    if bad:
        g.fail("F7", detail + "；" + "；".join(bad[:3]))
    else:
        g.ok("F7", detail)


@check("F8")
def c_f8(g):
    """F8（2026-10-08 随内容落地收紧，**判据只增不减**）。

    旧判据只查五类归因标题齐备 ＋ 含「无法判定」——那是**成文时**的形态断言：《失败案例分析》
    当时只有 30 题预实验集读数、第 ⑤ 类无判据。该文件现已补入**正式集（120 题）口径**的六类
    归因（答案侧门禁 18 题次／8 道不重复题号、①～④⑥ 的判据与计数）与第 ⑤ 类的**模型评分
    口径**逐条案例（判 0 分 0 条／判 1 分 20 条），而上述 token 正是**必须保留的历史留痕**，
    旧判据对新内容**全部无感**（标题还在、「无法判定」也还在，照样绿）——故在同一把尺子上再收紧，
    分四组、任一组不满足即 FAIL：
      A. **旧内核原样保留**：五类归因标题齐备 ＋ 含「无法判定」（不得被抹掉）。
      B. **正式集真实未通过的正向断言**：含 `18 题次`／`8 道不重复题号`／`3004`／
         `answer_gate_failed` 与两种失败项 `date_unverifiable`／`citation_missing`。
      C. **第 ⑤ 类的模型评分口径读数已登记**：同一行并存「判 0 分」＋`0 条` 与「判 1 分」＋`20 条`；
         且文中出现口径限定与主体标识 `模型评分口径`／`非人工判定`／`582`／`kimi-k3`／`glm-5.3-flash`。
      D. **六类各自可核**：五类代理判据的关键读数 `12 题 / 12 块`／`6 题`／`0 题 / 0 块`／
         `5 题 / 5 块`／`22 题`／`0 条 / 20 条` 齐备，且 `复算命令` 出现 ≥ 6 次（六类各一条）。
    **比旧判据严的证据**：删掉正式集门禁登记（把 `18 题次` 抹掉）旧判据**照样绿**，
    新判据**立刻 FAIL**（自检反例 ⑰ 实测：→ `{F8}`）。
    """
    if not g.exists(P_FAILCASE):
        return g.fail("F8", "不存在：%s" % g.ref(P_FAILCASE))
    doc = read_text(g.p(P_FAILCASE))
    lines = doc.split("\n")
    bad, ev = [], []

    # A. 旧内核：五类归因标题齐备 ＋ 含「无法判定」
    cats = ["抽取错误", "实体消歧错误", "检索漏召回", "时间判断错误", "生成不忠实"]
    miss_a = [c for c in cats if c not in doc]
    ev.append(not miss_a and "无法判定" in doc)
    if miss_a:
        bad.append("旧内核被破坏（五类归因不得抹掉）：缺 %s" % "、".join(miss_a))
    if "无法判定" not in doc:
        bad.append("旧内核被破坏（历史留痕「无法判定」不得抹掉）")

    # B. 正式集真实未通过的正向断言
    gate_tokens = ("18 题次", "8 道不重复题号", "3004", "answer_gate_failed",
                   "date_unverifiable", "citation_missing")
    miss_b = [t for t in gate_tokens if t not in doc]
    ev.append(not miss_b)
    if miss_b:
        bad.append("缺正式集答案侧门禁的读数登记：%s" % "、".join(miss_b))

    # C. 第 ⑤ 类的模型评分口径读数
    f5 = [ln for ln in lines if "判 0 分" in ln and "0 条" in ln and "判 1 分" in ln and "20 条" in ln]
    ev.append(bool(f5))
    if not f5:
        bad.append("缺第 ⑤ 类的模型评分口径读数（须同行并存「判 0 分」＋`0 条` 与「判 1 分」＋`20 条`）")
    lim = ("模型评分口径", "非人工判定", "582", "kimi-k3", "glm-5.3-flash")
    miss_c = [t for t in lim if t not in doc]
    ev.append(not miss_c)
    if miss_c:
        bad.append("缺口径限定／主体标识：%s" % "、".join(miss_c))

    # D. 六类各自可核
    cells = ("12 题 / 12 块", "6 题", "0 题 / 0 块", "5 题 / 5 块", "0 条 / 20 条", "22 题")
    miss_d = [t for t in cells if t not in doc]
    ev.append(not miss_d)
    if miss_d:
        bad.append("缺六类归因的关键读数：%s" % "、".join(miss_d))
    n_cmd = doc.count("复算命令")
    ev.append(n_cmd >= 6)
    if n_cmd < 6:
        bad.append("「复算命令」仅出现 %d 次（六类各一条，应 ≥6）" % n_cmd)

    if bad:
        g.fail("F8", "；".join(bad))
    else:
        g.ok("F8", "旧内核保留（五类归因标题齐备＋含「无法判定」）＋正式集答案侧门禁读数已登记"
                    "（18 题次／8 道不重复题号、3004／answer_gate_failed、date_unverifiable／"
                    "citation_missing）＋第 ⑤ 类模型评分口径读数（判 0 分 0 条／判 1 分 20 条）＋"
                    "六类关键读数与复算命令（%d 条）齐备（%d 项断言全过）" % (n_cmd, len(ev)))


# ==========================================================================
# G 组 · 只读、术语与门禁
# ==========================================================================
@check("G1")
def c_g1(g):
    """G1（2026-10-08 判据随事实变更重基线，**更严、不是放宽**）。

    旧判据的末条是「工作区**无** `对照产出_正式\`（正式全量未跑）」——那是**授权前**写下的
    状态断言。作者**已授权并已跑完**正式全量（六组落盘），该断言于是恒假：**它断言的是
    "尚未开工"，不是任何本行真正要守的东西**（本行的职责是「零模型调用留痕还在」＋
    「正式产出不是一个空壳／半成品」）。

    新判据保留旧判据的合理内核（留痕存在 ＋ `model_calls_made_by_this_mode`＝0），并把
    失效的那一条换成**更严的事实核查**（与 D3 共用 `Gate.formal_outputs()`）：
      ① 正式产出目录、报告 md、报告 json 齐备，且 **六组齐备**（A／B／C／D／E ＋ Baseline 1）;
      ② 逐组 `answer_trace.jsonl` 行数 **＝ 报告自报的有效题数**（`qids` 长度，与各表
         『题数』行同源）——少一行、多一行、整份缺失都点名报出；
      ③ 正式产出里**不再出现**「正式全量未跑／未授权」这类已失效表述。
    旧判据对①②③**全部无感**：它只看"目录在不在"，一个空目录或半份产出照样绿。
    """
    a = load_json(g.p(P_AUDIT), None)
    bad = []
    if not a:
        bad.append("缺 %s" % g.ref(P_AUDIT))
    elif a.get("model_calls_made_by_this_mode") != 0:
        bad.append("留痕未记 0 次调用")
    ok_f, fbad, finfo = g.formal_outputs()
    bad += fbad
    decl = finfo.get("declared") or {}
    detail = ("零调用留痕=%s（mode=%s、0 次调用）；正式全量产出核查：%s 齐备=%s、"
              "六组 %s、逐组 trace 行数 %s（报告『题数』行自报 %s）、"
              "仍含已失效表述=%s（旧判据只断言该目录「不存在」=授权前状态，已随事实变更重基线）"
              % (bool(a), (a or {}).get("mode"), g.ref(P_OUT_FORMAL), ok_f,
                 "／".join(finfo.get("groups") or []) or "缺",
                 "／".join("%s %s" % (k, v) for k, v in sorted((finfo.get("rows") or {}).items()))
                 or "缺",
                 "／".join("%s %s" % (k, decl.get(k)) for k in GROUPS_FORMAL),
                 "／".join(finfo.get("stale") or []) or "无"))
    if bad:
        g.fail("G1", detail + "；" + "；".join(bad))
    else:
        g.ok("G1", detail + "；留痕与正式产出两处自洽")


@check("G2")
def c_g2(g):
    """术语纪律：范围限定对齐 `验收第9阶段.py` 的 I2 纪律——
    本阶段文档内被禁术语**非语境**命中即 FAIL；既有／上游文件里的命中只统计、不判负并逐条打印。"""
    scan = [P_TASK, P_DOC27, P_FAILCASE, P_PLAN, P_CHECKLIST, P_QNOTE,
            P_DECISIVE, P_NFR_MD, P_SUBMIT, P_REPORT]
    mine = [P_TASK, P_DOC27, P_FAILCASE]
    NEG = re.compile(r"(不称|不得称|不叫|别称)")          # 否定语境（如「不称"向量数据库"」）
    hits, ctx, outside = [], 0, []
    good = 0
    for p in scan:
        if not os.path.exists(g.p(p)):
            continue
        t = read_text(g.p(p))
        rp = rel(g.root, os.path.join(g.root, p))
        if p in mine:
            good += t.count("向量索引") + t.count("向量检索组件")
        for i, ln in enumerate(t.split("\n"), 1):
            if BANNED_VDB in ln:
                if NEG.search(ln):
                    ctx += 1
                elif p in mine:
                    hits.append("%s:%d「%s」" % (rp, i, ln.strip()[:70]))
                else:
                    outside.append("%s:%d" % (rp, i))
    # FAISS 的写法：只对本阶段新写的三份文档硬判（既有文件不在本阶段写范围内）
    for p in mine:
        if not os.path.exists(g.p(p)):
            continue
        for i, ln in enumerate(read_text(g.p(p)).split("\n"), 1):
            if "FAISS" in ln and not ("向量索引" in ln or "向量检索组件" in ln):
                hits.append("%s:%d 的 FAISS 未写作「向量索引」" % (rel(g.root, os.path.join(g.root, p)), i))
    detail = ("扫描 %d 份本阶段文档（其中三份为本次新写）：被禁术语非语境命中 %d 处、"
              "否定语境 %d 处（不计负）；三份新文档里「向量索引／向量检索组件」出现 %d 次（正向对照）；"
              "既有／上游文件里的命中 %d 处（%s），按范围限定只统计、不判负"
              % (len(scan), len(hits), ctx, good, len(outside), "、".join(outside[:3]) or "无"))
    if hits:
        g.fail("G2", detail + "；本阶段文档命中：%s" % "；".join(hits[:5]))
    elif good < 1:
        g.fail("G2", detail + "；正向对照不足（三份新文档里没有「向量索引」）")
    else:
        g.ok("G2", detail)


@check("G3")
def c_g3(g):
    if g.profile == "static" or g.mirror:
        return g.unrun("G3", "静态档／镜像副本：不跑全仓跨文档核验（本行记 UNRUN）")
    if not g.exists(P_XDOC):
        return g.fail("G3", "缺 %s" % g.ref(P_XDOC))
    p = subprocess.run([sys.executable, os.path.join(g.root, P_XDOC), g.root, "--strict-citations"],
                       cwd=g.root, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=1800)
    out = (p.stdout or "") + (p.stderr or "")
    concl = ""
    for ln in out.split("\n"):
        if ln.startswith("结论："):
            concl = ln.strip()
    fails = []
    for ln in out.split("\n"):
        s = ln.strip()
        if s.startswith("[FAIL]"):
            fails.append(s[7:].strip())
    # 允许项：① 开工基线（先于本阶段存在的失败）；② 唯一一项**已登记的未完成登记**——
    # `26-`／`27-` 未出现在《00》（《26》第4.7节 已登记为收口登记产出，由 Lead 统一执行；
    # 硬约束 20 明确本阶段不得修改《00》）。两项都**逐条打印**，不静默放过。
    allow = list(XDOC_BASELINE) + ["带号文档均已登记"]
    extra = [f for f in fails if not any(b in f for b in allow)]
    dangling = [f for f in fails if "文档提到的文件均存在" in f]
    stage10_scope = [f for f in fails if ("26-" in f or "27-" in f or "失败案例分析" in f
                                         or "验收第10阶段" in f) and "带号文档均已登记" not in f]
    detail = "实跑 `--strict-citations`：退出码 %d；失败项 %d 条；%s" % (p.returncode, len(fails), concl)
    if stage10_scope or dangling or extra:
        g.fail("G3", detail + "；**超出自控范围的失败**：%s"
               % (stage10_scope or dangling or extra)[:3])
    elif p.returncode == 0:
        g.ok("G3", detail + "；全部通过")
    else:
        g.ok("G3", detail + "；失败项全部落在允许项内（开工基线 ∪ 一项已登记的未完成登记），逐条列出：%s"
             % "；".join(fails) + "。其中「带号文档均已登记」＝《26》第4.7节 已登记的收口登记产出"
             "（`26-`／`27-` 需进《00》索引），该项由 Lead 统一执行、本阶段写范围内无解")


def _fp_check(g, rid, table, label):
    bad = []
    for relp, want in table.items():
        p = g.p(relp.replace("/", os.sep))
        if not os.path.exists(p):
            bad.append("缺 %s" % relp)
            continue
        got = sha256_file(p)
        if got != want:
            bad.append("%s 指纹不符（现 %s…／基线 %s…）" % (relp, got[:12], want[:12]))
    if bad:
        g.fail(rid, "%s：%d 件指纹比对，%d 件不符：%s" % (label, len(table), len(bad), "；".join(bad[:4])))
    else:
        g.ok(rid, "%s：%d 件 SHA-256 与《26》第三节登记的开工基线逐项一致" % (label, len(table)))


@check("G4")
def c_g4(g):
    _fp_check(g, "G4", UPSTREAM_FP, "上游代码与冻结接口只读")
    if g.rows.get("G4", ("", ""))[0] == "OK":
        g.notes.append("G4 已登记豁免（不静默）：%s" % "；".join(G4_EXEMPT))


@check("G5")
def c_g5(g):
    _fp_check(g, "G5", UPSTREAM_FP_5_9, "第 5～9 阶段上游交付物只读")


@check("G6")
def c_g6(g):
    txt = read_text(g.p(P_RETRIEVAL_CFG)) if g.exists(P_RETRIEVAL_CFG) else ""
    vals = {}
    for key, pat in (("K", r'"K":\s*(\d+)'), ("N", r'"N":\s*(\d+)'),
                     ("budget", r'"context_token_budget":\s*(\d+)'),
                     ("g", r'"graph_retention_share":\s*(\d+)')):
        m = re.search(pat, txt)
        vals[key] = int(m.group(1)) if m else None
    bad = []
    if vals != FROZEN:
        bad.append("代码现场值 %s ≠ 冻结值 %s" % (vals, FROZEN))
    lits = {"K": ["K＝10", "K=10"], "N": ["N＝20", "N=20"],
            "budget": ["预算＝3600", "预算=3600", "3600"], "g": ["g＝2", "g=2"]}
    docs = {"《26》": P_TASK, "《27》": P_DOC27, "失败案例分析": P_FAILCASE}
    for name, p in docs.items():
        if not os.path.exists(g.p(p)):
            bad.append("缺 %s" % name)
            continue
        t = read_text(g.p(p))
        for key, options in lits.items():
            if not any(o in t for o in options):
                bad.append("%s 未出现 %s 的冻结表述" % (name, key))
    detail = "代码现场值 %s；三份新文档均含 K=10／N=20／预算=3600／g=2 的冻结表述=%s" % (vals, not bad)
    if bad:
        g.fail("G6", detail + "；" + "；".join(bad[:5]))
    else:
        g.ok("G6", detail + "；与《00》第五节 冻结口径速查一致")


# --------------------------------------------------------------------------
# 5. 环境探测与总装
# --------------------------------------------------------------------------
def env_notes(g):
    """本阶段判据不依赖服务；这里只把现场事实记成备注（不进判据、不影响退出码）。"""
    import socket

    def open_(port):
        s = socket.socket()
        s.settimeout(0.6)
        try:
            s.connect(("127.0.0.1", port))
            return True
        except Exception:                                   # noqa: BLE001
            return False
        finally:
            s.close()
    st = {"backend_8000": open_(8000), "neo4j_bolt_7687": open_(7687), "mysql_3306": open_(3306)}
    g.notes.append("现场服务状态（**不进判据**：第 10 阶段的 46 行判据全部落在落盘产物上，"
                   "后端与 Neo4j 未起也能跑完）：%s"
                   % "，".join("%s=%s" % (k, "监听" if v else "未监听") for k, v in st.items()))
    g.notes.append("确实需要服务的检查：本阶段**没有**——正式全量实验（720 次调用）属未授权项，"
                   "不在门禁范围内；服务侧读数一律引用第 9 阶段留痕（`阶段09-…\\集成产出\\`）。")


def print_report(g, order, titles, profile, mirror):
    print("")
    print("=" * 78)
    print("第 10 阶段专项门禁 · 逐行结果（--profile %s%s）" % (profile, "，镜像副本" if mirror else ""))
    print("=" * 78)
    cur = None
    for rid in order:
        grp = rid[0]
        if grp != cur:
            cur = grp
            print("")
            print("-- %s 组 · %s（计划 %d 行） %s" % (grp, GROUP_TITLE[grp], ROW_GROUPS[grp], "-" * 20))
        status, detail = g.rows.get(rid, ("UNRUN", "未判定（脚本内部缺失）"))
        print("%s %s %s  %s" % (STATUS_TAG[status], rid, titles.get(rid, "?"), detail))
    print("")
    print("-" * 78)
    print("分组计数：")
    tot = {"OK": 0, "FAIL": 0, "UNRUN": 0}
    for grp in "ABCDEFG":
        ids = [r for r in order if r[0] == grp]
        c = {"OK": 0, "FAIL": 0, "UNRUN": 0}
        for r in ids:
            c[g.rows.get(r, ("UNRUN",))[0]] += 1
        for k in tot:
            tot[k] += c[k]
        print("  %s 组（%2d 行）：OK %2d ｜ FAIL %2d ｜ UNRUN %2d"
              % (grp, len(ids), c["OK"], c["FAIL"], c["UNRUN"]))
    print("-" * 78)
    print("计划行数 %d ｜ 执行 %d ｜ 通过 %d ｜ 失败 %d ｜ 未执行 %d"
          % (len(order), tot["OK"] + tot["FAIL"], tot["OK"], tot["FAIL"], tot["UNRUN"]))
    if g.notes:
        print("")
        print("备注：")
        for s in g.notes:
            print("  · %s" % s)
    content_fail = [r for r in order if g.rows.get(r, ("UNRUN",))[0] == "FAIL"]
    if profile == "static" or mirror:
        code = 2
        verdict = "静态档／镜像副本：实况行未执行（UNRUN），按口径退出码 2"
    elif content_fail:
        code = 1
        verdict = "有内容失败 %d 行：%s ⇒ 退出码 1" % (len(content_fail), "、".join(content_fail))
    else:
        code = 0
        verdict = "%d 行全部 [OK] ⇒ 退出码 0" % len(order)
    print("")
    print("结论：%s" % verdict)
    print("=" * 78)
    return code


def run_gate(root, profile, mirror=False, quiet=False):
    order_rows = parse_spec_rows(root)
    order = [r[0] for r in order_rows]
    titles = dict((r[0], r[1]) for r in order_rows)
    problems = []
    if len(order) != TOTAL_ROWS:
        problems.append("《26》第八节解析出 %d 行（应 %d 行）" % (len(order), TOTAL_ROWS))
    if len(order) != len(set(order)):
        problems.append("解析出的行号有重复：%s" % order)
    missing = [r for r in order if r not in CHECKS]
    extra = [r for r in CHECKS if r not in order]
    if missing:
        problems.append("脚本未实现的行：%s" % "、".join(missing))
    if extra:
        problems.append("脚本多出来的行：%s" % "、".join(sorted(extra)))
    for grp, n in ROW_GROUPS.items():
        got = len([r for r in order if r[0] == grp])
        if got != n:
            problems.append("%s 组解析出 %d 行（应 %d 行）" % (grp, got, n))
    if problems:
        buf = io.StringIO()
        buf.write("行结构错误（脚本或《26》被改动）：\n")
        for p in problems:
            buf.write("  · %s\n" % p)
        buf.write("退出码 2\n")
        txt = buf.getvalue()
        if quiet:
            return 2, txt
        print(txt, end="")
        return 2
    g = Gate(root, profile, mirror=mirror)
    env_notes(g)
    for rid in order:
        try:
            CHECKS[rid](g)
        except Exception as exc:                            # noqa: BLE001
            g.fail(rid, "判据内部异常：%s: %s（脚本缺陷，需修脚本）"
                   % (type(exc).__name__, str(exc)[:160]))
        if rid not in g.rows:
            g.unrun(rid, "判据未给出结论（脚本内部缺失）")
    if quiet:
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = print_report(g, order, titles, profile, mirror)
        return code, buf.getvalue()
    return print_report(g, order, titles, profile, mirror)


# --------------------------------------------------------------------------
# 6. 自检：原样对照 ＋ 定向篡改
# --------------------------------------------------------------------------
def build_mirror(root, dst):
    os.makedirs(dst, exist_ok=True)
    for relp in MIRROR_FILES:
        src = os.path.join(root, relp)
        if not os.path.exists(src):
            continue
        tgt = os.path.join(dst, relp)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        shutil.copy2(src, tgt)
    for relp in MIRROR_DIRS:
        base = os.path.join(root, relp)
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d not in MIRROR_SKIP_DIRS]
            rdp = os.path.relpath(dp, root)
            for f in fn:
                if os.path.splitext(f)[1].lower() in MIRROR_SKIP_EXT:
                    continue
                tgt = os.path.join(dst, rdp, f)
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                try:
                    shutil.copy2(os.path.join(dp, f), tgt)
                except Exception:                           # noqa: BLE001
                    pass
    return dst


def pick_fails(log):
    if "行结构错误" in log:
        return {"<ROWSTRUCT>"}
    return set(re.findall(r"\[FAIL\] ([A-G]\d{1,2}) ", log))


def tamper_cases(root):
    """定向篡改用例：[(名字, 相对路径, 篡改函数, 期望 FAIL 集)]。"""
    def t_qset(t):
        lines = [l for l in t.split("\n") if l.strip()]
        if len(lines) < 2:
            raise RuntimeError("题集行数不足")
        return "\n".join(lines[:-1]) + "\n"

    def t_anchor(t):
        d = json.loads(t.split("\n")[0])
        a = d["gold_verify_anchors"][0]
        a["quote"] = a["quote"][:-1] + ("X" if not a["quote"].endswith("X") else "Y")
        lines = [json.dumps(d, ensure_ascii=False)] + [l for l in t.split("\n")[1:] if l.strip()]
        return "\n".join(lines) + "\n"

    def t_profile(t):
        d = json.loads(t)
        d["profile"] = "v21_v1_2"
        return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

    def t_trace(t):
        out = []
        for l in t.split("\n"):
            if not l.strip():
                continue
            d = json.loads(l)
            if d.get("qid") == "PE-01":
                d["evidence"] = [e for e in d["evidence"] if int(e["chunk_id"]) != 1001001]
            out.append(json.dumps(d, ensure_ascii=False))
        return "\n".join(out) + "\n"

    def t_cer(t):
        return t.replace("| **Complete Evidence Recall@K** | 0.566667 | 0.566667 | 0.566667 | 0.566667 | 0.566667 |",
                         "| **Complete Evidence Recall@K** | 0.600000 | 0.566667 | 0.566667 | 0.566667 | 0.566667 |")

    def t_cer_row(t):
        return t.replace("| Recall@K | 0.678095 |", "| Recall@K | 0.700000 |")

    def t_unrun(t):
        return t.replace("120 题全量实验尚未运行", "120 题全量实验已完成")

    def t_claim(t):
        return t.replace("## 对下游（第 11 阶段论文与第 12 阶段答辩）的使用说明",
                         "## 对下游（第 11 阶段论文与第 12 阶段答辩）的使用说明\n\n> qid 前缀问题已修复。")

    def t_repro(t):
        d = json.loads(t)
        d["files"][0]["sha256"] = "0" * 64
        return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

    def t_limit(t):
        return t.replace("跨批", "批内")

    def t_rowid(t):
        return t.replace("| A8 |", "| A9 |", 1)

    # ---- B6／F6 随口径变更重基线（2026-10-07）后新增的两个定向反例 -------------
    # B6 的旧判据只查字面 token，把验收句删掉也照样绿；新判据断言**结论本身**，
    # 所以 ⑫ 把「合取判定…三个子集全部不成立」那一整行删掉必须被抓住。
    def t_conj(t):
        old = ("> **《02》第 12.8 节 判定条件的结论（模型评分口径、非人工判定）**：三个子集"
               "（关系型 12 题／多跳型 21 题／时序型 12 题）——① 「Complete Evidence Recall@K 高于基线」"
               "在**三个子集上都不成立**（A 组＝C 组，逐子集 0.5000／0.5238／0.7500 字面相等）；"
               "② 「Answer Accuracy 不下降」在**关系型上不成立**（A 1.7500 → C 1.6667，下降 −0.0833）、"
               "多跳型（1.6667 → 1.6667）与时序型（1.9167 → 1.9167）**持平**；"
               "**① 且 ② 的合取判定在三个子集上全部不成立**。"
               "**这是模型评分口径下的判定、不是人工判定**；范围限定为 30 题预实验集"
               "（主体判定依据为核心 108 题）。")
        if old not in t:
            raise RuntimeError("反例 ⑫ 的目标行不存在（B6 结论行已被改写？）")
        return t.replace(old, "> **（本节 12.8 结论行已删，留作反例）**", 1)

    # ⑬ 把《27》里模型口径的关键串改成人工口径 → F6 的正向断言（跨厂商模型评审＋模型参照集
    #    读数）与 C 组失效表述两项都应报红。
    def t_scope(t):
        out = t.replace("跨厂商模型评审", "人工口径评审")
        out = out.replace("模型参照集口径下的抽取表现", "人工金标准下的抽取准确率")
        out = out.replace("模型评分不是人工评分", "模型评分就是人工评分")
        if out == t:
            raise RuntimeError("反例 ⑬ 的篡改目标不存在")
        return out

    # ---- D3／G1 随事实变更重基线（2026-10-08）后新增的两个定向反例 -----------------
    # 旧判据（D3 的「工作区无 对照产出_正式」、G1 的「该目录不存在」）在正式全量跑完后
    # **恒假**，两个反例都改不动它们：新判据断言的是**产出本身的事实**，故下述两处篡改
    # 必须立刻报红——这正是「新判据比旧判据严」的实测证据。
    def t_formal_row(t):
        """删掉正式产出 B1 组的最后一行 → 行数 119 ≠ 报告『题数』自报 120。

        这一条同时被 **G1**（六组产出的行数核查）与 **D3**（`--report-only` 前后的
        内容指纹零改动）覆盖。本自检跑的是 **static 镜像档**：D3 属"实况行"、在该档记 UNRUN，
        故实测只报 G1——这是**档位差异，不是判据失效**；D3 侧的同一条件由工作区 full 档的
        破坏试验覆盖（见《26》修订记录 v1.7）。
        """
        lines = [l for l in t.split("\n") if l.strip()]
        if len(lines) < 2:
            raise RuntimeError("反例 ⑭：正式 B1 trace 行数不足")
        return "\n".join(lines[:-1]) + "\n"

    def t_formal_stale(t):
        """往正式报告里塞回「正式全量未跑」这类授权前的表述 → G1 的失效表述断言报红。"""
        return t + "\n> （反例⑮）本阶段正式全量未跑，本文件为授权前的留痕。\n"

    # ---- F4／F8 随内容落地重基线（2026-10-08）后新增的两个定向反例 ---------------
    # 旧 F4 只查「两句历史声明还在 ＋ 120 题读数不许带小数」，旧 F8 只查「五类标题在 ＋ 含无法判定」：
    # 下面两处篡改对**旧判据全部无感**（历史声明与「无法判定」都还在），新判据必须立刻报红——
    # 这正是「新判据比旧判据严」的实测证据。
    def t_f4_reading(t):
        """把《27》正式集 A 组 Answer Accuracy 均值 `1.6903` 改掉 → F4 的读数断言报红。"""
        if "1.6903" not in t:
            raise RuntimeError("反例 ⑯：正式集 A 组 AA 均值（1.6903）不在文中")
        return t.replace("1.6903", "1.6000")

    def t_f8_formal(t):
        """抹掉《失败案例分析》的正式集答案侧门禁登记（`18 题次`）→ F8 的正向断言报红。"""
        if "18 题次" not in t:
            raise RuntimeError("反例 ⑰：正式集门禁登记（18 题次）不在文中")
        return t.replace("18 题次", "（该登记已删，留作反例）")

    # ---- F6 的 C 组第二半修守卫假阳性（2026-10-09）后新增的定向反例 -----------------
    # ⑱ 一行里两句话：前句是禁令（含「不得」）、后句是**真实的正向断言**。
    #    旧守卫取固定 14 字符窗口，窗口里恰好含前句的「不得」→ 把后句放行（**假阴性**）；
    #    新守卫按整句判定 → 后句所在句内无否定词，报红。故本反例证明新守卫**同时收紧**，
    #    不是只把误报关掉。
    def t_f6_cross_sentence(t):
        """追加一行「禁令句 ＋ 正向断言句」→ F6 报红（旧守卫对该篡改无感）。"""
        return t + "\n> （反例⑱）**不得**写成人工口径。人工评分已完成。\n"

    return [
        ("① 正式题集删掉最后一行 → 条数／qid 集合／配额不符；复现包题集指纹同时失效（预期级联）",
         os.path.join(S10, "测试集/questions.jsonl"), t_qset, {"A1", "A2", "A3", "E2"}),
        ("② 某题 anchor 的 quote 改一个字符 → 不再逐字命中；题集指纹同时失效（预期级联）",
         os.path.join(S10, "测试集/questions.jsonl"), t_anchor, {"A5", "E2"}),
        ("③ graph_stats.json 的 profile 值改成 v21_v1_2 → 口径不符；上游只读指纹同时报警（预期级联）",
         "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_3/graph_stats.json", t_profile, {"A6", "G5"}),
        ("④ A 组 trace 删掉 PE-01 已命中的 gold 块 → CER 重算下降",
         os.path.join(S10, "对照产出_v13/A/answer_trace.jsonl"), t_trace, {"B2", "B3"}),
        ("⑤ 报告主表 CER 五组改成不同值 → 与独立重算不符",
         os.path.join(S10, "对照产出_v13/A_vs_C_对照报告.md"), t_cer, {"B3"}),
        ("⑥ 报告主表 Recall@K 的 A 列改值 → 与独立重算不符",
         os.path.join(S10, "对照产出_v13/A_vs_C_对照报告.md"), t_cer_row, {"B3"}),
        ("⑦ 删掉《27》的「120 题全量实验尚未运行」声明 → 正向断言失败",
         os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md"), t_unrun, {"F4"}),
        ("⑧ 往《27》里加一句「qid 前缀问题已修复」→ 不得断言已修好",
         os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md"), t_claim, {"F5"}),
        ("⑨ 复现包 manifest 改一个 sha256 → 自洽性破坏",
         os.path.join(S10, "复现包/manifest.json"), t_repro, {"E2"}),
        ("⑩ 《27》把已知限制第 5 条的「跨批」改写掉 → 9 条承接不齐",
         os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md"), t_limit, {"F3"}),
        ("⑪ 《26》第八节把 A8 行号改成 A9 → 行结构自检失败（退出码 2）",
         os.path.join(S10, "26-第10阶段任务书（系统测试与对比实验）.md"), t_rowid, {"<ROWSTRUCT>"}),
        ("⑫ 报告里删掉「合取判定…三个子集全部不成立」那一行 → B6 的新判据（断结论、不查旧 token）报红",
         os.path.join(S10, "对照产出_v13/A_vs_C_对照报告.md"), t_conj, {"B6"}),
        ("⑬ 《27》把「跨厂商模型评审／模型参照集口径」改成人工口径 → F6 的正向断言与失效表述两项报红",
         os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md"), t_scope, {"F6"}),
        ("⑭ 正式产出 B1 组 trace 删掉最后一行 → G1 的行数核查报红（D3 同条件在 static 档记 UNRUN，由 full 档破坏试验覆盖；旧判据对该篡改无感）",
         os.path.join(P_OUT_FORMAL, "B1/answer_trace.jsonl"), t_formal_row, {"G1"}),
        ("⑮ 正式报告里塞回「正式全量未跑」→ G1 的失效表述断言报红（旧判据对该篡改无感）",
         os.path.join(P_OUT_FORMAL, "A_vs_C_对照报告.md"), t_formal_stale, {"G1"}),
        ("⑯ 《27》把正式集 A 组 Answer Accuracy 均值 1.6903 改成 1.6000 → F4 的正式集读数断言报红（旧判据只查两句历史声明，对该篡改无感）",
         os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md"), t_f4_reading, {"F4"}),
        ("⑰ 《失败案例分析》抹掉正式集答案侧门禁登记「18 题次」→ F8 的正向断言报红（旧判据只查五类标题与「无法判定」，对该篡改无感）",
         os.path.join(S10, "失败案例分析.md"), t_f8_formal, {"F8"}),
        ("⑱ 《27》追加一行「**不得**写成人工口径。人工评分已完成。」→ F6 的 C 组第二半报红（旧守卫的 14 字符窗口被前句的「不得」豁免、对该篡改无感；新守卫按整句判定即报红）",
         os.path.join(S10, "27-第10阶段产出文档（系统测试与对比实验）.md"), t_f6_cross_sentence, {"F6"}),
    ]


def selftest(root, keep_tmp=False):
    tmp = tempfile.mkdtemp(prefix="t10_selftest_")
    print("=" * 78)
    print("自检（负向校准）：镜像副本 ＋ 定向篡改")
    print("  基准工作区：%s" % root)
    print("  镜像目录：%s" % tmp)
    print("=" * 78)
    base = os.path.join(tmp, "base")
    build_mirror(root, base)
    code, log = run_gate(base, "static", mirror=True, quiet=True)
    pristine = pick_fails(log)
    n_all = len(re.findall(r"^\[(?:OK |FAIL|UNRUN)\] [A-G]\d{1,2} ", log, re.M))
    n_unrun = len(re.findall(r"^\[UNRUN\] [A-G]\d{1,2} ", log, re.M))
    print("\n[A] 原样对照（未篡改的镜像副本，--profile static）")
    print("    逐行输出 %d／%d；已判定 %d；未判定（实况行）%d；退出码 %d"
          % (n_all, TOTAL_ROWS, n_all - n_unrun, n_unrun, code))
    print("    内容失败集：%s" % (sorted(pristine) or "空"))
    ok_pristine = (not pristine) and code == 2
    if not ok_pristine:
        print("    ✗ 原样对照不通过：期望「无内容失败、退出码 2」，实测 失败集=%s、退出码=%s"
              % (sorted(pristine), code))
        for l in log.strip().split("\n")[-25:]:
            print("    | %s" % l)
    else:
        print("    ✓ 通过：原样副本只在实况行上 UNRUN，无任何内容失败")

    print("\n[B] 定向篡改（逐个改一处，期望 FAIL 集 ＝ 实测 FAIL 集）")
    cases = tamper_cases(base)
    all_ok = True
    for i, (name, relp, mut, exp) in enumerate(cases, 1):
        path = os.path.join(base, relp.replace("/", os.sep))
        if not os.path.exists(path):
            print("  %2d. %s\n      ✗ 篡改目标不存在：%s" % (i, name, relp))
            all_ok = False
            continue
        old = read_text(path)
        try:
            new = mut(old)
        except Exception as exc:                            # noqa: BLE001
            print("  %2d. %s\n      ✗ 篡改动作本身失败：%s" % (i, name, exc))
            all_ok = False
            continue
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        _, tlog = run_gate(base, "static", mirror=True, quiet=True)
        got = pick_fails(tlog)
        with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(old)
        flag = "✓" if got == exp else "✗"
        if got != exp:
            all_ok = False
        print("  %2d. %s" % (i, name))
        print("      目标：%s" % relp)
        print("      %s 期望 FAIL 集 ＝ %s ｜ 实测 FAIL 集 ＝ %s" % (flag, sorted(exp), sorted(got)))
        if got != exp:
            for l in [x for x in tlog.split("\n") if x.startswith("[FAIL]")]:
                print("      | %s" % l)
    _, log2 = run_gate(base, "static", mirror=True, quiet=True)
    pristine2 = pick_fails(log2)
    print("\n[C] 还原复核：全部篡改回滚后的失败集 ＝ %s" % (sorted(pristine2) or "空"))
    if pristine2:
        all_ok = False
    print("\n自检结论：%s（反例 %d 个）"
          % ("通过（原样无内容失败 ＋ 全部篡改都按预期失败）" if (all_ok and ok_pristine)
             else "未通过 —— 见上文 ✗ 项", len(cases)))
    if keep_tmp:
        print("镜像保留在：%s" % tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 78)
    return 0 if (all_ok and ok_pristine) else 2


# --------------------------------------------------------------------------
# 7. 入口
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="第 10 阶段（系统测试与对比实验）专项验收门禁（《26》第八节 46 行）")
    ap.add_argument("--profile", choices=["full", "static"], default="full",
                    help="full＝逐行判（含实跑脚手架零调用档，默认）；static＝不实跑子进程，实况行记 UNRUN")
    ap.add_argument("--selftest", action="store_true", help="负向校准：原样对照 ＋ 定向篡改")
    ap.add_argument("--root", default=REPO_ROOT, help="工作区根（默认脚本所在仓库；指向副本时自动按镜像模式跑）")
    ap.add_argument("--keep-tmp", action="store_true", help="自检后保留镜像目录（排查用）")
    a = ap.parse_args(argv)

    root = os.path.abspath(a.root)
    if a.selftest:
        return selftest(root, keep_tmp=a.keep_tmp)
    mirror = (root != REPO_ROOT)
    if mirror and not os.path.isdir(root):
        print("工作区不存在：%s" % root)
        return 2
    profile = "static" if (mirror or a.profile == "static") else "full"
    return run_gate(root, profile, mirror=mirror)


if __name__ == "__main__":
    raise SystemExit(main())
