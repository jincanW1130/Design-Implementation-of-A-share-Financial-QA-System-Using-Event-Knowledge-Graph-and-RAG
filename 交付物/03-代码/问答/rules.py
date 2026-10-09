# -*- coding: utf-8 -*-
"""代码\\问答\\rules.py —— 第 8 阶段的**判据单一来源**：日期来源可核 ＋ 禁词表。

本文件只放**判据**（"什么算越界"），不放任何配置取值——日期基准 `data_cutoff_time`、窗口规则
与四项定值一律经 `config.py` 读取（`config.py` 又从 `代码\\检索\\config.py` 导入），脚本内
不写死日期、周天数或阈值（《21》第五节 硬约束 1／10／11）。

**为什么要单独一个文件（《21》T5／T6 的执行要求）**：答案侧（`answer.py` 的机检门禁）与选型侧
（`model_selection.py` 的机检读数）必须用**同一套**判据，否则同一份模型输出在两处会有两套口径
（"答案侧说越界、选型侧说不越界"）。故本文件是唯一实现，`model_selection.py` 已改为 import 本
文件、删除自己的重复实现；抽取前后 `--recheck` 的产出**逐字节不变**（报告里给出前后 SHA-256）。

---

一、日期来源可核（《21》v1.2 第五节 硬约束 10／11；验收 E1）

答案中出现的任何年月日，必须满足**至少一条**来源：

1. 在本题证据集合的正文里**字面出现**（证据正文／该证据条的语料元数据：标题、发布时间），
   或出现在本题的**图谱载荷** `graph_payload` 里（它是本题证据集合的一部分，《21》第三节 第 1 项）；
2. 等于 `data_cutoff_time` 的日期部分；
3. 是由 `data_cutoff_time` 按窗口规则**确定性推出**的判定区间端点（`config.window_endpoint_dates()`：
   「最近」＝截止前 30 天、「近期」＝前 90 天、「最新」＝基准日当天），或题集 `time_window`
   明确给出的 `lo`／`hi`（它由 Prompt 第 6 区块注入，同样是确定性取值）。

三条都不满足即为**越界**（`date_unverifiable`，0 次是门禁）。

**证据正文中明写的、晚于 `data_cutoff_time` 的日期不算越界**——例如公告原文写明的
「行权期有效期为2026年9月11日-2027年1月25日」，它是公开事实的原文，不得要求模型隐瞒、
也不得判为幻觉。这类日期单列 `dates_beyond_cutoff`，**只统计、不计入失败**（《21》v1.2 修订
记录 ①）。机器只核**日期来源**；"不得据此推断截止之后新发生的事"是论文层面的表述纪律。

---

二、禁词表（《21》第五节 硬约束 19／验收 E3：预测／投资建议类，固定常量）

`FORBIDDEN_TERMS` 是**固定常量**，按"预测或投资建议"的**成词短语**列举，命中即判失败。
词表的取舍口径（**事先写明**，避免看到生成结果再定）：只收**推荐／评级／价格判断／买卖动作**
一类**成词短语**，**不收**在冻结证据正文里本就字面出现的**事实性叙述词**——实测（2026-09-29，
开工时对 30 题的最终证据集合正文扫描）：`预计` 30 处、`减持` 13 处、`风险提示` 11 处、
`增持` 4 处、`预测` 2 处、`上涨` 1 处。这些词出现在答案里多半是**正确引用公告原文**，
把它们收进词表会把"正确引用证据"判成违规，与硬约束 10 在同一次修订（v1.2）里确立的
"证据里明写的不算越界"是同一个道理。故本表**不收** `预测`／`预计`／`增持`／`减持`／
`上涨`／`风险提示` 这类单词，只收无歧义的**建议／评级／荐股／涨跌断言**短语。
该取舍如实登记进产出文档的"已知限制"（词表是**有限枚举**，不是语义判别器）。
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import date

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: E402

# --------------------------------------------------------------------------
# 一、日期
# --------------------------------------------------------------------------
# 年月日（四种常见写法）。**容忍空白与全角**：证据正文里有按显示宽度断行／加空格的写法
# （实测：「2025 年10 月10 日」「行权期有效期为2026年9月11日-2027年1月25日」），按字面子串
# 比对会漏，必须先归一化再比对（《21》第五节 硬约束 10 的「互相归一后比对」）。
DATE_RES = [
    re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"),
    re.compile(r"(\d{4})\s*-\s*(\d{1,2})\s*-\s*(\d{1,2})"),
    re.compile(r"(\d{4})\s*/\s*(\d{1,2})\s*/\s*(\d{1,2})"),
    re.compile(r"(\d{4})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})"),
]
# 全角数字／连字符／斜杠／点号 → 半角（归一化用）
_FW_TRANS = str.maketrans("０１２３４５６７８９－／．", "0123456789-./")

# 《21》第五节 硬约束 11 的三条窗口规则名（用于说明；取值一律取 config）
WINDOW_RULE_NOTE = "「最新」＝基准日当天、「最近」＝截止前 30 天、「近期」＝截止前 90 天"


def cutoff_date() -> date:
    """数据截止时间的日期部分（经 config 读，**不写死日期**）。"""
    return config.cutoff_date()


def extract_dates(text) -> set:
    """文本里的年月日，归一化为 `datetime.date` 集合（容忍空白／全角写法）。

    非法的年月日（例如 2026年13月40日）不是日期，忽略。
    """
    out = set()
    for rx in DATE_RES:
        for y, m, d in rx.findall((text or "").translate(_FW_TRANS)):
            try:
                out.add(date(int(y), int(m), int(d)))
            except ValueError:
                continue
    return out


def allowed_dates(case: dict) -> set:
    """《21》v1.2 硬约束 10 的三条**日期来源**并成的可核集合（日期门禁的比较基准）。

    * ① 本题证据集合：每条证据的**正文**／**标题**／**发布时间**字面出现的日期；
      以及本题**图谱载荷** `graph_payload` 里的日期（`event_triples` 的 `event_time` 等）——
      图谱载荷是本题证据集合的一部分（《21》第三节 第 1 项），并由代码渲染进「知识图谱路径」段；
    * ② `data_cutoff_time` 的日期部分；
    * ③ 由窗口规则**确定性推出**的判定区间端点（`config.window_endpoint_dates()`）＋ 题集
      `time_window` 明确给出的 `lo`／`hi`（`case["time_note"]`，同样是确定性取值）。
    """
    allowed = set(config.window_endpoint_dates())
    allowed.add(cutoff_date())
    for ev in case["evidence"]:
        allowed |= extract_dates(ev.get("text"))
        allowed |= extract_dates(ev.get("title"))
        allowed |= extract_dates(str(ev.get("publish_time") or ""))
    allowed |= extract_dates(json.dumps(case.get("graph_payload") or {}, ensure_ascii=False))
    tn = case.get("time_note") or {}
    if tn.get("time_constraint") == "有":
        for key in ("lo", "hi"):
            allowed |= extract_dates(str(tn.get(key) or ""))
    return allowed


def date_gate(text, case: dict) -> dict:
    """日期来源可核的机检读数（**答案全文**口径，验收 E1 的字面「答案中每个年月日」）。

    * `date_unverifiable` —— 三条来源都不满足的日期，**这才是越界**，0 次是门禁；
    * `dates_beyond_cutoff` —— 晚于 `data_cutoff_time` 的日期，**只统计、不计入失败**。
    """
    allowed = allowed_dates(case)
    cutoff = cutoff_date()
    mentioned = extract_dates(text)
    unver = sorted(d for d in mentioned if d not in allowed)
    beyond = sorted(d for d in mentioned if d > cutoff)

    def _iso(ds):
        return [d.isoformat() for d in ds]

    return {
        "dates_mentioned": _iso(sorted(mentioned)),
        "dates_mentioned_count": len(mentioned),
        "date_unverifiable": _iso(unver),
        "date_unverifiable_count": len(unver),
        "dates_beyond_cutoff": _iso(beyond),
        "dates_beyond_cutoff_count": len(beyond),
        "date_cutoff_part": cutoff.isoformat(),
        "allowed_source_note": ("允许来源＝证据正文／证据标题／证据发布时间／图谱载荷 ＋ "
                                "data_cutoff_time 的日期部分 ＋ 窗口规则推出的判定区间端点"
                                "（%s）＋ 题集 time_window 的 lo／hi" % WINDOW_RULE_NOTE),
    }


# --------------------------------------------------------------------------
# 二、禁词表（固定常量；口径见模块 docstring 第二节）
# --------------------------------------------------------------------------
FORBIDDEN_TERMS = (
    # 投资建议／评级类
    "投资建议", "建议买入", "建议卖出", "建议增持", "建议减持", "建议持有", "建议投资",
    "买入评级", "卖出评级", "增持评级", "减持评级", "强烈推荐", "推荐买入", "推荐卖出",
    "操作建议", "建议关注", "荐股",
    # 价格／涨跌断言类（预测）
    "目标价", "股价预测", "走势预测", "目标涨幅", "上涨空间", "下跌空间",
    "预计上涨", "预计下跌", "有望上涨", "有望下跌", "有望突破", "必涨", "必跌", "稳赚",
    # 交易动作类
    "建仓", "加仓", "减仓", "抄底", "止损", "止盈", "看多", "看空", "后市",
)

# 明确**不收**的事实性叙述词：它们在冻结证据正文里字面出现（实测计数见 docstring），
# 收录会把「正确引用公告原文」判成违规。本常量只作留痕与自检用，不参与判定。
FORBIDDEN_EXCLUDED_CORPUS_WORDS = (
    "预测",      # 证据正文 2 处
    "预计",      # 证据正文 30 处
    "增持",      # 证据正文 4 处
    "减持",      # 证据正文 13 处
    "上涨",      # 证据正文 1 处
    "风险提示",  # 证据正文 11 处
)


def forbidden_terms() -> tuple:
    """禁词表的只读视图（固定常量；不随运行环境变化）。"""
    return FORBIDDEN_TERMS


def forbidden_gate(text) -> dict:
    """禁词机检：返回命中清单与**命中上下文**（命中 0 次是门禁，验收 E3）。

    `forbidden_hit_contexts` 只用于**事后核对命中的是什么**（模型在给建议，还是在写
    「本回答不构成投资建议」这类自我免责的元话语）——判定仍按字面命中，不因上下文放宽。
    """
    body = text or ""
    hits, contexts = [], []
    for word in FORBIDDEN_TERMS:
        start = 0
        while True:
            i = body.find(word, start)
            if i < 0:
                break
            hits.append(word)
            contexts.append({"term": word,
                             "excerpt": body[max(0, i - 60):i + len(word) + 60]})
            start = i + len(word)
    return {
        "forbidden_hits": hits,
        "forbidden_hit_count": len(hits),
        "forbidden_hit_contexts": contexts,
        "forbidden_terms_size": len(FORBIDDEN_TERMS),
    }


# --------------------------------------------------------------------------
# 三、引用编号（《21》第五节 硬约束 9、第六节 格式决策 3）
# --------------------------------------------------------------------------
# 引用记法固定为 `[证据n]`，n 为本次证据集合中按呈现顺序的序号（1 起）。同一份正则同时供
# 答案侧门禁（`answer.py`）与选型侧读数（`model_selection.py`）使用，避免两套解析口径。
CITATION_RE = re.compile(r"\[证据\s*(\d+)\]")


def citation_marks(text) -> list:
    """按出现顺序解析 `[证据n]`，返回 n 的列表（**不做去重、不排序**）。"""
    return [int(n) for n in CITATION_RE.findall(text or "")]


def citation_gate(text, evidence_count: int) -> dict:
    """引用编号机检：`[证据n]` 的 n ∉ 1..m（m ＝ 本题证据条数）即越界（0 次是门禁）。"""
    marks = citation_marks(text)
    oob = sorted({n for n in marks if n < 1 or n > evidence_count})
    return {
        "citation_marks": marks,
        "citation_count": len(marks),
        "citation_out_of_range": oob,
        "citation_out_of_range_count": len(oob),
        "cited_ranks": sorted({n for n in marks if 1 <= n <= evidence_count}),
        "evidence_count": evidence_count,
    }


# --------------------------------------------------------------------------
# 四、自检
# --------------------------------------------------------------------------
def selftest() -> int:
    print("=" * 72)
    print("rules.py 自检（判据单一来源：日期来源可核 ＋ 禁词表）")
    print("=" * 72)
    print("数据截止时间的日期部分（经 config 读） = %s" % cutoff_date().isoformat())
    print("窗口规则推出的判定区间端点             = %s"
          % "、".join(sorted(d.isoformat() for d in config.window_endpoint_dates())))
    print("日期正则写法数 = %d（中文年月日／短横线／斜杠／点号）" % len(DATE_RES))

    print("\n--- 归一化与容忍性自证 ---")
    probe = "行权期有效期为2026年9月11日-2027年1月25日；另见 2026 09 25 与 ２０２６／９／２５"
    ds = sorted(extract_dates(probe))
    for d in ds:
        print("  解析出 %s" % d.isoformat())
    assert date(2026, 9, 11) in ds and date(2027, 1, 25) in ds, "中文年月日写法未解析"
    assert date(2026, 9, 25) in ds, "全角／斜杠写法未解析"
    print("  断言：中文年月日、全角与斜杠写法都能解析 → 通过")

    print("\n--- 禁词表（固定常量，%d 条）---" % len(FORBIDDEN_TERMS))
    print("  %s" % "、".join(FORBIDDEN_TERMS))
    print("  明确不收的事实性叙述词（证据正文里字面出现）：%s"
          % "、".join(FORBIDDEN_EXCLUDED_CORPUS_WORDS))
    print("  自证：不收的词与收的词不重叠 = %s"
          % (not (set(FORBIDDEN_EXCLUDED_CORPUS_WORDS) & set(FORBIDDEN_TERMS))))
    assert not (set(FORBIDDEN_EXCLUDED_CORPUS_WORDS) & set(FORBIDDEN_TERMS))
    cg = citation_gate("结论见 [证据2] 与 [证据10]；另见 [证据99]。", 10)
    print("\n--- 引用编号自证 ---")
    print("  n 序列 = %s；越界 = %s（应为 [99]）"
          % (cg["citation_marks"], cg["citation_out_of_range"]))
    assert cg["citation_marks"] == [2, 10, 99] and cg["citation_out_of_range"] == [99]
    assert cg["cited_ranks"] == [2, 10]

    g = forbidden_gate("本回答不构成投资建议，也不给出任何目标价。")
    print("  探针文本命中 = %s（应为 ['投资建议', '目标价']）" % g["forbidden_hits"])
    assert g["forbidden_hits"] == ["投资建议", "目标价"], g["forbidden_hits"]
    print("  探针文本（引用公告原文「本次减持…风险提示…」）命中 = %s（应为空）"
          % forbidden_gate("公告中提及股东减持与风险提示，本次预计不产生影响。")["forbidden_hits"])
    assert forbidden_gate("公告中提及股东减持与风险提示，本次预计不产生影响。")["forbidden_hits"] == []
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(selftest())
