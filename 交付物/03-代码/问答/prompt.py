# -*- coding: utf-8 -*-
"""代码\\问答\\prompt.py —— Prompt 模板 **v1.0** 的落地（模板与配置分离）。

模板来源：《10-系统总体设计（第四阶段）》第4.6.8节 表 4-12 的**七区块**（顺序固定、
不得增删）；《21-第8阶段任务书（智能问答系统）》第五节 硬约束 3／4／9～12、第六节
格式决策 2／3。本文件**只放模板与渲染**，不放任何配置项取值——K／N／预算／g／模型值
一律经 `config.py`（模板与配置分离：按实验组换配置不改模板）。

七区块（表 4-12 的顺序）：

1. 系统角色与任务边界      —— 面向 A 股财经信息；只依据给定证据作答；不作预测与投资建议
2. 数据版本与时间边界      —— 每次请求注入 dataset_version 与 data_cutoff_time
3. 问题                    —— 用户问题**原文**，不改写、不扩写
4. 文本证据                —— 按传入顺序逐条给编号／doc_id／chunk_id／来源类型／发布时间与正文
5. 图谱路径与事件三元组    —— `graph_used` 为假时**该区块整体缺省**（不输出空标题）
6. 相对时间判定说明        —— 判定区间与数据截止时间；「最新／最近／近期」按 event_time 判定
7. 输出格式要求            —— **只要求模型输出「回答」正文**、引用记法 `[证据n]`、模型分析的标注

区块的固定标题逐字固定（便于机检与第 9 阶段渲染），拼接顺序即表 4-12 的顺序。

**答案四段的分工（《21》v1.2 第五节 硬约束 7／8、第六节 格式决策 2）**：答案固定四段
`回答`／`证据来源`／`知识图谱路径`（或「本次回答未使用图谱扩展」）／`数据截至与判定区间`，
其中**只有「回答」正文由模型生成**；`证据来源`（本次证据集合 ＋ 语料元数据）、
`知识图谱路径`（直接取 `graph_payload`）、`数据截至与判定区间`（取 `dataset.json` 的
`dataset_version`／`data_cutoff_time`）三段由本文件的 `compose_answer()` **确定性拼装**。
理由：FR-05 要求证据列表来自 `answer_evidence`、图谱路径来自 `answer.graph_path`，交给模型
自述就不可核验——上一轮小样本试跑实测到有候选把**用了图谱扩展**的 PE-01 写成「本次回答未
使用图谱扩展」。
"""

from __future__ import annotations

import os
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

# --------------------------------------------------------------------------
# 版本常量（与模板文本绑定在同一文件；改措辞必须换版本号）
# --------------------------------------------------------------------------
PROMPT_VERSION = "v1.0"

# 答案形态的四个固定区块标题（《21》第六节 格式决策 2）——由 `compose_answer()` 拼装，
# 第 9 阶段渲染与后续机检都按这四段定位。
ANSWER_SECTIONS = ["回答", "证据来源", "知识图谱路径", "数据截至与判定区间"]
# 机检用标题行（标题本身逐字等于 ANSWER_SECTIONS，只加「【】」包裹便于切段）
SECTION_HEADERS = ["【%s】" % t for t in ANSWER_SECTIONS]
# 「回答」正文 = 模型生成的唯一一段；其余三段由代码拼装（v1.2 硬约束 7）
MODEL_BODY_SECTION = ANSWER_SECTIONS[0]
# `graph_used` 为假时的固定标注字样（《21》第五节 硬约束 8；《10》第4.6.9节）
NO_GRAPH_MARKER = "本次回答未使用图谱扩展"
# 开放式分析问题的固定标注（《21》第五节 硬约束 12；《10》表 4-12 第 7 区块）
MODEL_ANALYSIS_MARKER = "模型分析（非公开事实）"

# 引用记法（《21》第五节 硬约束 9、第六节 格式决策 3）
CITATION_TEMPLATE = "[证据n]"

# 证据「来源类型」的四类（《21》第五节 硬约束 15）；本文件是**归类的唯一实现**，
# 记录层（T7／history.py）的 `evidence_type` 直接调用本文件的 `source_type_label()`，
# 与 Prompt 第 4 区块的标签**同源**（硬约束 15：不得各写一套）。
#
# 映射表按数据集 v2.1 的真实词表**逐项写死**（《21》v1.4 硬约束 15）。键必须与
# `documents.jsonl` 的 `category` 取值**逐字对齐**——决策者 2026-09-29 实测全语料
# `category` 只有四种：公告 556／财经新闻 103／政策文件 30／监管公开信息 20。
#
# **反例（本次实测发现、已修，见《21》v1.4 修订记录）**：本映射原先把新闻类的键写成
# 「新闻」，而数据里的真实取值是「财经新闻」，键名对不上真实取值，于是**财经新闻类证据
# 全部落到兜底类「回答来源」、`新闻来源` 在本批 30 题证据上出现 0 次**（实测：证据 293 条
# ＝ 公告来源 234 ＋ 相关事件 53 ＋ 回答来源 6，那 6 条正是 `财经新闻` 被兜底）。
# 教训：类别键一律照数据真实取值写，不得凭常识改写成近义词。
SOURCE_TYPE_BY_CATEGORY = {
    "公告": "公告来源",            # 官方披露文本
    "政策文件": "公告来源",        # 官方全文发布，与「公告」同属官方发布文本
    "监管公开信息": "公告来源",    # 监管机构的公开信息，同为官方发布
    "财经新闻": "新闻来源",        # 新闻媒体文本（**键＝数据真实取值，不是「新闻」**）
}
SOURCE_TYPE_DEFAULT = "回答来源"   # 兜底类：category 缺失或不在上表
SOURCE_TYPE_GRAPH = "相关事件"     # 来自图谱侧新增块（`from_graph`）

# --------------------------------------------------------------------------
# 七区块模板（占位符用 str.format，模板键名固定）
# --------------------------------------------------------------------------
_BLOCK_ROLE = """【系统角色与任务边界】
你是面向 A 股财经信息的智能问答系统。你的回答**只依据下面给出的证据**（文本证据、
图谱路径与事件三元组），不作预测，不给出投资建议，不引入证据之外的事实。
无论本次实验属于哪一组，本区块的措辞与要求一律相同。"""

_BLOCK_DATA = """【数据版本与时间边界】
本次数据版本：{dataset_version}
数据截止时间：{data_cutoff_time}
你**不得**使用数据截止时间之后的信息；若给定证据不足以回答，**不得**用训练语料中的
信息（尤其是其中的时间信息）补全或推测，应当直接说明证据不足。"""

_BLOCK_QUESTION = """【问题】
{question}"""

_BLOCK_EVIDENCE = """【文本证据】
以下证据按呈现顺序编号，引用时请使用对应编号：
{evidence_lines}"""

_BLOCK_GRAPH = """【图谱路径与事件三元组】
{graph_lines}"""

_BLOCK_TIME = """【相对时间判定说明】
{time_note}"""

_BLOCK_OUTPUT = """【输出格式要求】
**只输出「回答」正文本身**：直接给出正文，**不要**输出任何区块标题、**不要**使用 Markdown
标题层级与序号小标题（「回答」「证据来源」「知识图谱路径」「数据截至与判定区间」这些字样
都不要出现）。
* 引用记法固定为 `[证据n]`，n 为上面文本证据里的呈现序号（从 1 起）；**不得**引用不存在的
  编号（n 不得大于证据条数）。
* 证据清单、知识图谱路径、数据截止时间与判定区间**由系统在本区块之外另行拼装**：你
  **不要**罗列证据清单、**不要**描述图谱路径与事件三元组、**不要**复述数据截止时间与判定区间，
  也不要声明本次是否使用了图谱扩展。
* 属于你自己的推断或开放分析的内容，必须显式标注「{model_analysis_marker}」，以示与公开事实的
  区分；公开事实则直接陈述，不必加该标注。
* 证据不足时直接说明证据不足，不得用证据之外的信息补全。"""

# 七区块：(键, 标题, 模板文本)。顺序即表 4-12 的顺序，不得增删或重排。
BLOCKS = [
    ("role_boundary", "系统角色与任务边界", _BLOCK_ROLE),
    ("data_boundary", "数据版本与时间边界", _BLOCK_DATA),
    ("question", "问题", _BLOCK_QUESTION),
    ("evidence", "文本证据", _BLOCK_EVIDENCE),
    ("graph", "图谱路径与事件三元组", _BLOCK_GRAPH),
    ("time_note", "相对时间判定说明", _BLOCK_TIME),
    ("output_format", "输出格式要求", _BLOCK_OUTPUT),
]
BLOCK_KEYS = [k for k, _, _ in BLOCKS]
BLOCK_TITLES = [t for _, t, _ in BLOCKS]


# --------------------------------------------------------------------------
# 渲染
# --------------------------------------------------------------------------
def source_type_label(evidence_item: dict) -> str:
    """证据的「来源类型」标签（四类之一；归类依据＝文档 category ＋ 是否来自图谱侧）。"""
    if evidence_item.get("from_graph"):
        return SOURCE_TYPE_GRAPH
    return SOURCE_TYPE_BY_CATEGORY.get(evidence_item.get("category"), SOURCE_TYPE_DEFAULT)


def render_evidence_block(evidence: list) -> str:
    """第 4 区块的正文：按传入顺序逐条给编号／doc_id／chunk_id／来源类型／发布时间与正文。

    **不在生成侧重排**（《21》第五节 硬约束 5）：逐位照传入顺序渲染。
    """
    lines = []
    for item in evidence:
        rank = item["rank"]
        lines.append(
            "[证据%d] doc_id=%s chunk_id=%s 来源类型=%s 发布时间=%s\n标题：%s\n正文：%s"
            % (rank, item["doc_id"], item["chunk_id"], source_type_label(item),
               item.get("publish_time") or "空", item.get("title") or "空",
               (item.get("text") or "").strip()))
    return "\n\n".join(lines)


def render_graph_block(graph_payload: dict) -> str:
    """第 5 区块的正文；`graph_used` 为假时返回空串（**整体缺省**，不输出空标题）。"""
    if not graph_payload or not graph_payload.get("graph_used"):
        return ""
    lines = ["depth=%s" % graph_payload.get("depth")]
    triples = graph_payload.get("event_triples") or []
    if triples:
        lines.append("事件三元组（event_id / event_type / event_time）：")
        for t in triples:
            lines.append("  " + " / ".join("空" if v in (None, "") else str(v) for v in t))
    paths = graph_payload.get("graph_path") or []
    if paths:
        lines.append("图谱路径（start —关系（role, confidence, source_doc_id, source_chunk_id）→ end）：")
        for p in paths:
            for rel in p.get("relations") or []:
                ev = rel.get("evidence") or {}
                lines.append(
                    "  %s -%s(role=%s, confidence=%s, source_doc_id=%s, source_chunk_id=%s)-> %s"
                    % (p.get("start"), rel.get("relation"), rel.get("role"),
                       ev.get("confidence"), ev.get("source_doc_id"),
                       ev.get("source_chunk_id"), p.get("end")))
    note = graph_payload.get("note")
    if note:
        lines.append("备注：%s" % note)
    return "\n".join(lines)


def render_time_block(time_note) -> str:
    """第 6 区块的正文。`time_note` 是装配层按题集与数据集属性生成的判定说明。

    允许传入字符串（装配层已渲染）或结构 dict（本函数按固定口径渲染）。
    """
    if isinstance(time_note, str):
        return time_note
    t = time_note or {}
    return (
        "数据截止时间：%s\n本题相对时间判定区间：%s\n"
        "判定基准：%s。「最新／最近／近期」一律按 event_time 判定，"
        "「最近」＝截止时间前 30 天、「近期」＝前 90 天。"
        % (t.get("data_cutoff_time") or config.DATA_CUTOFF_TIME,
           t.get("window_label") or "本题不含相对时间表述（无判定区间）",
           t.get("basis") or "event_time"))


# --------------------------------------------------------------------------
# 答案四段：只有「回答」由模型生成，其余三段由代码**确定性拼装**
# （《21》v1.2 第五节 硬约束 7／8、第六节 格式决策 2）
# --------------------------------------------------------------------------
def render_evidence_section(evidence: list) -> str:
    """`证据来源` 段：逐条含编号／`chunk_id`／`doc_id`／来源类型／发布时间／标题。

    不复制正文（正文在 Prompt 里已给模型；本段是**可回链**的证据清单，供 FR-05 追溯）。
    """
    lines = []
    for item in evidence:
        lines.append("[证据%d] chunk_id=%s doc_id=%s 来源类型=%s 发布时间=%s 标题：%s"
                     % (item["rank"], item["chunk_id"], item["doc_id"],
                        source_type_label(item), item.get("publish_time") or "空",
                        item.get("title") or "空"))
    return "\n".join(lines) if lines else "（本次无证据）"


def render_time_section(*, dataset_version: str, data_cutoff_time: str, time_note) -> str:
    """`数据截至与判定区间` 段：取 `dataset.json` 的版本级属性与本题的时间判定说明。"""
    t = time_note if isinstance(time_note, dict) else {}
    lines = ["数据版本：%s" % dataset_version,
             "数据截止时间：%s" % data_cutoff_time]
    if t.get("time_constraint") == "有":
        lines.append("本题相对时间判定区间：%s（%s 至 %s，基准 %s）"
                     % (t.get("window_label"), t.get("lo"), t.get("hi"),
                        t.get("basis") or "event_time"))
    else:
        lines.append("本题不含相对时间表述，无判定区间。")
    return "\n".join(lines)


def render_graph_section(graph_payload: dict) -> str:
    """`知识图谱路径` 段：`graph_used` 为真时取 `graph_payload` 的渲染结果，
    否则**只写固定标注**（《21》第五节 硬约束 8：不得留空、不得展示虚构路径）。
    """
    body = render_graph_block(graph_payload)
    return body if body else NO_GRAPH_MARKER


def compose_answer(*, body: str, evidence: list, graph_payload: dict,
                   dataset_version: str, data_cutoff_time: str, time_note) -> str:
    """把模型生成的「回答」正文与代码拼装的三段合成一条完整答案（确定性）。

    传入的 `body` 是**模型原始输出、不做任何改写**（《21》非目标 10：不做内容改写）。
    """
    sections = [
        (MODEL_BODY_SECTION, (body or "").strip()),
        (ANSWER_SECTIONS[1], render_evidence_section(evidence)),
        (ANSWER_SECTIONS[2], render_graph_section(graph_payload)),
        (ANSWER_SECTIONS[3], render_time_section(
            dataset_version=dataset_version, data_cutoff_time=data_cutoff_time,
            time_note=time_note)),
    ]
    return "\n\n".join("%s\n%s" % (SECTION_HEADERS[i], text)
                       for i, (_, text) in enumerate(sections))


def split_answer_sections(answer_text: str) -> dict:
    """按四个固定标题切段；返回 `{标题: 内容}`（标题不存在时该键缺席）。

    机检（D4／E2）按它取「知识图谱路径」段与「回答」段，不靠正则猜。
    """
    text = answer_text or ""
    positions = []
    for i, header in enumerate(SECTION_HEADERS):
        idx = text.find(header)
        if idx >= 0:
            positions.append((idx, header, ANSWER_SECTIONS[i]))
    positions.sort()
    out = {}
    for k, (idx, header, title) in enumerate(positions):
        start = idx + len(header)
        end = positions[k + 1][0] if k + 1 < len(positions) else len(text)
        out[title] = text[start:end].strip()
    return out


# --------------------------------------------------------------------------
# 组装
# --------------------------------------------------------------------------
def build_messages(*, question: str, dataset_version: str, data_cutoff_time: str,
                   evidence: list, graph_payload: dict, time_note) -> dict:
    """把七个区块渲染成一条请求的 system／user 两段 + 可逐字节比对的 Prompt 文本。

    * 第 1～2 区块 → `system`（与实验组无关的固定指令）；
    * 第 3～7 区块 → `user`（含本题的问题、证据、图谱载荷与时间说明）。
    * 第 5 区块在 `graph_used` 为假时**整体缺省**。
    """
    if PROMPT_VERSION != config.require_fixed("prompt_version"):
        raise SystemExit("Prompt 版本不一致：prompt.PROMPT_VERSION=%s，config 固定表=%s"
                         % (PROMPT_VERSION, config.require_fixed("prompt_version")))
    system = _BLOCK_ROLE + "\n\n" + _BLOCK_DATA.format(
        dataset_version=dataset_version, data_cutoff_time=data_cutoff_time)

    parts = [_BLOCK_QUESTION.format(question=question),
             _BLOCK_EVIDENCE.format(evidence_lines=render_evidence_block(evidence))]
    graph_body = render_graph_block(graph_payload)
    if graph_body:                                   # 假时不追加空标题
        parts.append(_BLOCK_GRAPH.format(graph_lines=graph_body))
    parts.append(_BLOCK_TIME.format(time_note=render_time_block(time_note)))
    parts.append(_BLOCK_OUTPUT.format(model_analysis_marker=MODEL_ANALYSIS_MARKER))
    user = "\n\n".join(parts)

    prompt_text = system + "\n\n" + user
    return {"system": system, "user": user,
            "prompt_text": prompt_text,
            "sha256": config.sha256_text(prompt_text),
            "graph_used": bool(graph_payload and graph_payload.get("graph_used"))}


def template_text() -> str:
    """模板整体的可逐字节比对文本（占位符保持原样，不含任何取值）。"""
    return "\n\n".join("[%d] %s\n%s" % (i + 1, title, body)
                       for i, (_, title, body) in enumerate(BLOCKS))


def snapshot() -> dict:
    """写 `问答产出\\prompt_snapshot.json` 所需的结构（《21》第4.3节）。"""
    text = template_text()
    return {
        "prompt_version": PROMPT_VERSION,
        "block_order": BLOCK_KEYS,
        "block_titles": BLOCK_TITLES,
        "blocks": [{"order": i + 1, "key": key, "title": title, "template": body}
                   for i, (key, title, body) in enumerate(BLOCKS)],
        "answer_sections": ANSWER_SECTIONS,
        "section_headers": SECTION_HEADERS,
        "model_generated_sections": [MODEL_BODY_SECTION],
        "code_assembled_sections": ANSWER_SECTIONS[1:],
        "no_graph_marker": NO_GRAPH_MARKER,
        "model_analysis_marker": MODEL_ANALYSIS_MARKER,
        "citation_template": CITATION_TEMPLATE,
        "template_sha256": config.sha256_text(text),
    }


def write_snapshot(path: str = None) -> str:
    path = path or config.PROMPT_SNAPSHOT_PATH
    config.write_json(path, snapshot())
    return path


# --------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------
def selftest() -> int:
    print("=" * 72)
    print("prompt.py 自检（Prompt 模板 %s）" % PROMPT_VERSION)
    print("=" * 72)
    assert PROMPT_VERSION == "v1.0", "PROMPT_VERSION 必须为 v1.0，实际 %r" % PROMPT_VERSION
    assert PROMPT_VERSION == config.require_fixed("prompt_version")
    print("断言 PROMPT_VERSION == 'v1.0' 通过；与 config 固定表一致。")
    print("\n--- 七区块顺序 ---")
    for i, (key, title, body) in enumerate(BLOCKS, 1):
        print("  %d. %-14s %-16s 模板 %d 字" % (i, key, title, len(body)))
    print("\n--- 模板整体 SHA-256 ---")
    print("  %s" % config.sha256_text(template_text()))
    print("\n--- 四段答案标题 / 固定标注（v1.2：只有「回答」由模型生成）---")
    print("  答案区块：%s" % "／".join(ANSWER_SECTIONS))
    print("  机检标题：%s" % "／".join(SECTION_HEADERS))
    print("  由模型生成：%s" % "／".join([MODEL_BODY_SECTION]))
    print("  由代码拼装：%s" % "／".join(ANSWER_SECTIONS[1:]))
    print("  未使用图谱扩展的固定字样：%s（只允许出现在系统拼装的图谱段）" % NO_GRAPH_MARKER)
    print("  开放式分析标注：%s" % MODEL_ANALYSIS_MARKER)

    print("\n--- 第 7 区块（输出格式要求）全文：只要求模型输出「回答」正文 ---")
    print(_BLOCK_OUTPUT.format(model_analysis_marker=MODEL_ANALYSIS_MARKER))
    print("\n  第 7 区块里出现「%s」= %s（必须为 False：该字样只能由系统图谱段写出）"
          % (NO_GRAPH_MARKER,
             NO_GRAPH_MARKER in _BLOCK_OUTPUT))

    print("\n--- 四段拼装自证（graph_used 真／假各一次，确定性）---")
    # 演示用的合成证据（取值一律从 config／本模块常量推出，不写死日期与类别）
    demo_ev = [{"rank": 1, "chunk_id": 1, "doc_id": 1, "from_graph": False,
                "category": sorted(SOURCE_TYPE_BY_CATEGORY)[0],
                "publish_time": config.DATA_CUTOFF_TIME[:10],
                "title": "示例标题", "text": "示例正文"}]
    for used in (True, False):
        gp = {"depth": 2, "graph_used": used, "event_triples": [], "graph_path": [],
              "note": "示例"} if used else {"depth": 0, "graph_used": False,
                                           "event_triples": [], "graph_path": [], "note": ""}
        a = compose_answer(body="示例回答 [证据1]", evidence=demo_ev, graph_payload=gp,
                           dataset_version=config.DATASET_VERSION,
                           data_cutoff_time=config.DATA_CUTOFF_TIME,
                           time_note={"time_constraint": "无"})
        b = compose_answer(body="示例回答 [证据1]", evidence=demo_ev, graph_payload=gp,
                           dataset_version=config.DATASET_VERSION,
                           data_cutoff_time=config.DATA_CUTOFF_TIME,
                           time_note={"time_constraint": "无"})
        sec = split_answer_sections(a)
        print("  graph_used=%-5s 两次拼装 SHA-256 相同=%s；图谱段＝%r"
              % (used, config.sha256_text(a) == config.sha256_text(b),
                 sec.get(ANSWER_SECTIONS[2])[:40]))
        assert a == b, "compose_answer 必须确定性（同一输入逐字节一致）"
    print("=" * 72)
    return 0


if __name__ == "__main__":
    # 直接运行本文件＝T3 的「模板落地」动作：先写冻结快照，再跑自检。
    # 快照路径取 config.PROMPT_SNAPSHOT_PATH（`问答产出\prompt_snapshot.json`），
    # 与 `run_answer.py --all` 里 `_write_outputs()` 写的是同一份（模板与版本绑定）。
    _snap = write_snapshot()
    print("已写 Prompt 快照：%s" % _snap)
    raise SystemExit(selftest())
