# -*- coding: utf-8 -*-
"""「混合替换」执行后的文档自检（只读，不修改任何文件）。

验证项（对应交付要求的 1／3／4／5）：
  A《03》总表 22 行 与 分节 22 条 的槽位顺序、题名一致性
  B《04》正文引用标记数、编号连续性、按首次出现顺序、与参考文献表 22 条一一对应
  C 去虚构自检：把《03》《04》里每条新题录的「题名＋作者串」在 _知网替换/证据 中做全文检索
  D 字段取值来源：卷号页码「—」与导师字段「不写」的写法清单
产出：_替换执行/_验证输出/06_文档自检_混合替换后.txt
"""
from __future__ import annotations

import glob
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F03 = os.path.join(BASE, "03-精选文献库（22篇）.md")
F04 = os.path.join(BASE, "04-开题报告.md")
EVID = os.path.join(BASE, "_知网替换", "证据")
OUTDIR = os.path.join(BASE, "_替换执行", "_验证输出")
os.makedirs(OUTDIR, exist_ok=True)
OUT = []
FAILS = []


def w(line: str = "") -> None:
    print(line)
    OUT.append(line)


def chk(ok: bool, label: str, detail: str = "") -> bool:
    """门禁项：不通过即记入 FAILS，并打印 FAIL 明细。"""
    if not ok:
        FAILS.append(label)
    w("[%s] %s%s" % ("OK " if ok else "FAIL", label, ("  " + detail) if detail else ""))
    return ok


SLOTS = ["KG-5", "KG-9", "KG-16", "KG-17", "KG-19", "KG-21", "KG-28", "KG-29",
         "RAG-1", "RAG-9", "RAG-10", "RAG-11", "RAG-13", "RAG-24",
         "FIN-3", "FIN-16", "FIN-17", "FIN-20", "SYS-4", "SYS-8", "SYS-13", "SYS-14"]

# 14 条替换件的「关键实词」：方法名／指标名／数字类断言，必须在该条**全文 PDF** 中命中。
# 列表取自《04》正文对该条的断言；任一词在 PDF 中查不到即判 FAIL——这就是补 2.1 A1 那类
# "把别的论文的方法词搬到本条名下"的机器判据（原脚本只核题录能否在证据里检索到，核不到这个）。
ANCHOR = {
    "KG-5": ["FinBERT", "种子知识图谱", "相关股票"],
    "KG-9": ["指令", "触发词", "论元", "结构化"],
    "KG-16": ["跨度", "网络结构", "篇章级"],
    "KG-17": ["自适应", "图神经网络", "篇章级", "金融事件"],
    "KG-19": ["外部知识", "大语言模型", "共指"],
    "KG-29": ["开源情报", "实体链接", "运行流程", "发展脉络"],
    "RAG-10": ["图神经网络", "多跳问答", "推理路径", "噪声"],
    "RAG-24": ["事实性", "溯源性", "逻辑性", "428", "PLS-SEM", "语义一致性", "溯源核验", "逻辑结构"],
    "FIN-16": ["时序知识图谱", "四元组", "多粒度", "时态"],
    "FIN-17": ["非季节性", "季节性", "随机残差", "时序知识图谱"],
    "FIN-20": ["扩散模型", "图神经网络", "数据稀缺", "隐私"],
    "SYS-4": ["科研", "意图分类", "实体提取", "多任务"],
    "SYS-8": ["水产", "营养", "向量", "图谱", "60"],
    "SYS-14": ["电力", "路径推理", "对齐", "瓶颈", "跨主题"],
}

# 「异源词」：**不属于该条**的其他工作的方法词。若在《04》正文中与本条的指称关键词同现
# （同一行），说明旧工作的方法词又被搬到了本条名下——判 FAIL（带否定豁免：词前 12 字符内
# 出现 不/未/无/否/非 时不判，避免"并未提供原子事实核验"这类否定叙述被误伤）。
FOREIGN = {
    "KG-5": ["FinKario", "30万"],
    "FIN-16": ["CRONKGQA", "340倍"],
    "RAG-24": ["FActScore", "原子事实", "逐条"],
}

# 14 条替换件的 槽位 → 《04》参考文献编号（取自《03》第十节对照表，在此固化以免漂移）。
NO_BY_SLOT = {"KG-5": 3, "KG-9": 4, "KG-16": 5, "KG-17": 6, "KG-19": 7, "KG-29": 9,
              "RAG-10": 11, "SYS-8": 12, "RAG-24": 15, "FIN-16": 17, "FIN-17": 18,
              "FIN-20": 19, "SYS-4": 20, "SYS-14": 21}


def norm(s: str) -> str:
    """归一化：全角英数转半角、去空白。用于在 PDF 文本里做子串命中。"""
    out = []
    for ch in s:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E:
            ch = chr(o - 0xFEE0)
        elif o == 0x3000:
            ch = " "
        out.append(ch)
    return re.sub(r"\s+", "", "".join(out))


def block_cols(t: str):
    res, cur, fence = [], [], False
    for L in t.split("\n"):
        if L.strip().startswith("```"):
            fence = not fence
            continue
        if fence:
            continue
        s = L.strip()
        if s.startswith("|") and s.endswith("|"):
            cur.append(s.strip("|").split("|"))
        else:
            if len(cur) >= 2:
                res.append([len(c) for c in cur])
            cur = []
    if len(cur) >= 2:
        res.append([len(c) for c in cur])
    return res


def main() -> None:
    t03 = io.open(F03, encoding="utf-8").read()
    t04 = io.open(F04, encoding="utf-8").read()

    # ---------- A《03》总表 vs 分节 ----------
    w("=" * 78)
    w("A 《03》总表的 22 行与分节的 22 条：槽位顺序与题名一致性")
    w("=" * 78)
    m2 = re.search(r"## 二、文献库总表(.*?)\n---\n", t03, re.S)
    tbl = m2.group(1) if m2 else ""
    total_rows = re.findall(r"^\| ((?:KG|RAG|FIN|SYS)-\d+) \| ([^|]+?) \|", tbl, re.M)
    w("总表行数：%d" % len(total_rows))
    w("总表槽位顺序：%s" % "、".join(s for s, _ in total_rows))
    w("总表顺序与既定 22 槽位一致：%s" % ([s for s, _ in total_rows] == SLOTS))
    blocks = re.split(r"^### ", t03, flags=re.M)[1:]
    sec_order, sec = [], {}
    for b in blocks:
        m = re.match(r"([0-9.]+) ((?:KG|RAG|FIN|SYS)-\d+)", b)
        if not m:
            continue
        slot = m.group(2)
        sec_order.append(slot)
        mm = re.search(r"^- `%s`[^\n]*?—\s*([^\n]+)$" % re.escape(slot), b, re.M)
        sec[slot] = (mm.group(1).strip() if mm else "")
    w("分节条数：%d" % len(sec_order))
    w("分节槽位顺序：%s" % "、".join(sec_order))
    w("分节顺序与总表一致：%s" % (sec_order == [s for s, _ in total_rows]))
    w("")
    w("%-8s %-6s %s" % ("槽位", "一致", "题名（总表｜分节题录）"))
    all_ok = True
    for slot, title in total_rows:
        sec_title = sec.get(slot, "")
        ok = bool(sec_title) and (title.strip() in sec_title)
        all_ok = all_ok and ok
        w("%-8s %-6s %s" % (slot, "OK" if ok else "FAIL", "%s ｜ %s" % (title.strip(), sec_title[:70])))
    w("总表与分节题名全部一致：%s" % all_ok)
    chk([s for s, _ in total_rows] == SLOTS, "A1《03》总表槽位顺序为既定 22 槽位")
    chk(sec_order == [s for s, _ in total_rows], "A2《03》分节槽位顺序与总表一致")
    chk(all_ok, "A3《03》总表与分节题名逐条一致", "不一致项见上表 FAIL 行")
    cols = block_cols(t03)
    w("《03》表格块数 = %d；列数不一致的块 = %d" % (len(cols), sum(1 for c in cols if len(set(c)) > 1)))

    # ---------- B《04》引用与参考文献表 ----------
    w("")
    w("=" * 78)
    w("B 《04》正文引用标记 与 参考文献表 22 条")
    w("=" * 78)
    i11 = t04.index("## 十一、参考文献")
    body, refs = t04[:i11], t04[i11:]
    seq = []
    for no, line in enumerate(body.split("\n"), 1):
        for m in re.finditer(r"\[(\d+)\]", line):
            seq.append((no, int(m.group(1))))
    w("正文引用标记总数：%d" % len(seq))
    nums = [n for _, n in seq]
    first = {}
    for no, n in seq:
        first.setdefault(n, no)
    w("出现过的编号：%s" % sorted(set(nums)))
    w("编号覆盖 [1]～[22] 且无缺号：%s" % (sorted(set(nums)) == list(range(1, 23))))
    order = [x[0] for x in sorted(first.items(), key=lambda kv: (kv[1], kv[0]))]
    w("首次出现顺序：%s" % order)
    w("按首次出现顺序递增（无跳号/重号）：%s" % (order == list(range(1, 23))))
    ref_lines = re.findall(r"^\[(\d+)\] (.+)$", refs, re.M)
    w("参考文献表条数：%d" % len(ref_lines))
    w("编号一致：%s" % ([int(a) for a, _ in ref_lines] == list(range(1, 23))))
    w("每条引用次数：%s" % dict(sorted({n: nums.count(n) for n in sorted(set(nums))}.items())))
    chk(sorted(set(nums)) == list(range(1, 23)), "B1《04》正文引用编号集合 = [1]～[22]")
    chk(order == list(range(1, 23)), "B2《04》正文引用编号按首次出现顺序严格递增")
    chk(len(ref_lines) == 22 and [int(a) for a, _ in ref_lines] == list(range(1, 23)),
        "B3《04》参考文献表 22 条且编号 1～22 连续")
    w("")
    w("正文/参考文献表逐条对拍（编号｜正文首现行｜参考文献题名首 60 字）：")
    for no, txt in ref_lines:
        w("  [%s] 首现行 %-4s %s" % (no, first.get(int(no), "-"), txt[:60]))
    w("")
    w("参考文献表中包含竖线 | 的行数：%d（要求 0）"
      % sum(1 for a, b in ref_lines if "|" in b))
    w("")
    w("正文与参考文献表逐条对拍（该条在正文中的指称关键词是否出现；同一关键词可对应多条）：")
    KEY = {
        1: "Lewis", 2: "刘政昊", 3: "刘政昊", 4: "杨维", 5: "牛冰宇", 6: "廖慧之",
        7: "徐昇", 8: "实体消歧综述", 9: "韩雪", 10: "GraphRAG", 11: "图神经网络",
        12: "高佳", 13: "RAGAS", 14: "HotpotQA", 15: "禤德信", 16: "FinanceBench",
        17: "方纪祥", 18: "吴钰", 19: "翟源昊", 20: "王永", 21: "薛子强", 22: "RAGPerf",
    }
    KEY_BY_SLOT = {s: KEY[n] for s, n in NO_BY_SLOT.items()}
    okn = 0
    for no, txt in ref_lines:
        kw = KEY[int(no)]
        hit = kw in body
        okn += 1 if hit else 0
        w("  [%2s] 正文关键词「%s」命中=%s ｜ 参考文献「%s」" % (no, kw, hit, txt[:34]))
    w("正文关键词命中：%d/22（关键词是该条在正文中的指称，逐条对拍用）" % okn)

    # ---------- C 去虚构自检 ----------
    w("")
    w("=" * 78)
    w("C 去虚构自检：新题录的题名与作者串必须在 _知网替换/证据 中命中")
    w("=" * 78)
    evid_text = []
    for p in sorted(glob.glob(os.path.join(EVID, "**", "*.txt"), recursive=True)) + \
             sorted(glob.glob(os.path.join(EVID, "**", "*.html"), recursive=True)):
        evid_text.append(io.open(p, encoding="utf-8", errors="ignore").read())
    blob = "\n".join(evid_text)
    new_entries = {
        "KG-5": ("知识关联视角下金融证券知识图谱构建与相关股票发现", "刘政昊"),
        "KG-9": ("基于多维指令集微调的大语言模型金融事件抽取", "杨维"),
        "KG-16": ("基于跨度和网络结构的篇章级事件抽取研究", "牛冰宇"),
        "KG-17": ("基于自适应GNN的篇章级金融事件抽取系统研究与实现", "廖慧之"),
        "KG-19": ("外部知识增强的事件共指消解方法", "徐昇"),
        "KG-29": ("面向开源情报的实体链接技术研究综述", "韩雪"),
        "RAG-10": ("基于图神经网络推理的知识图谱多跳问答方法研究", "王东际"),
        "RAG-24": ("AIGC嵌入图书馆知识发现服务的幻觉识别与信任度测量", "禤德信"),
        "FIN-16": ("基于多粒度隐含时态感知的时序知识图谱问答研究", "方纪祥"),
        "FIN-17": ("SARIMA嵌入的时序知识图谱推理", "吴钰"),
        "FIN-20": ("一种基于扩散模型和知识图谱的智能金融问答系统的关键技术研究", "翟源昊"),
        "SYS-4": ("融合知识图谱和大模型的高校科研管理问答系统设计", "王永"),
        "SYS-8": ("基于Hybrid RAG的LLM水产营养推荐架构", "高佳"),
        "SYS-14": ("基于知识图谱路径推理和大模型的电力智能检索引擎", "薛子强"),
    }
    hit = miss = 0
    for slot, (title, author) in new_entries.items():
        in03, in04 = title in t03, title in t04
        t_hit, a_hit = title in blob, author in blob
        ok = in03 and in04 and t_hit and a_hit
        hit += 1 if ok else 0
        miss += 0 if ok else 1
        w("%-8s 03=%s 04=%s 证据-题名=%s 证据-作者=%s  %s"
          % (slot, in03, in04, t_hit, a_hit, "OK" if ok else "FAIL"))
    w("命中率：%d/%d = %.0f%%（要求 100%%）" % (hit, hit + miss, 100.0 * hit / (hit + miss)))
    chk(miss == 0, "C1 14 条替换题录（题名＋作者）在 _知网替换/证据 中全部可溯源",
        "未命中 %d 条" % miss)
    w("")

    # ---------- C2 关键实词必须在对应全文 PDF 中命中 ----------
    w("=" * 78)
    w("C2 关键实词锚定：14 条替换件的 方法名／指标名／数字 必须在该条全文 PDF 中命中")
    w("=" * 78)
    PDFDIR = os.path.join(BASE, "文献PDF")
    # 该条全文 PDF 的文件名：从《03》第二节总表「全文」列取（不依赖反引号）。
    new_entries_pdf = {}
    for _mm in re.finditer(r"^\| ((?:KG|RAG|FIN|SYS)-\d+) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| "
                           r"([^|]+?) \| ([^|]+?) \| ([^|]+?) \|", tbl, re.M):
        _s, _fu = _mm.group(1), _mm.group(6).strip()
        _fm = re.search(r"（([^）]+)）", _fu)
        new_entries_pdf[_s] = (_fm.group(1).strip() if _fm else _fu)
    try:
        import fitz  # PyMuPDF
        _fitz_ok = True
    except Exception as _e:
        _fitz_ok = False
        w("!! 未能导入 PyMuPDF（fitz）：%s" % _e)
    chk(_fitz_ok, "C2.0 PyMuPDF 可导入（否则关键实词锚定无法执行）")
    if _fitz_ok:
        _cache = {}

        def pdf_norm(slot: str):
            if slot not in _cache:
                fn = new_entries_pdf[slot]
                p = os.path.join(PDFDIR, fn)
                if not os.path.exists(p):
                    _cache[slot] = None
                else:
                    d = fitz.open(p)
                    _cache[slot] = norm("\n".join(d[i].get_text() for i in range(d.page_count)))
            return _cache[slot]

        bad_total = 0
        for slot, words in ANCHOR.items():
            txt = pdf_norm(slot)
            if txt is None:
                chk(False, "C2 %s 全文 PDF 存在" % slot, new_entries_pdf[slot])
                bad_total += 1
                continue
            miss_w = [x for x in words if norm(x) not in txt]
            bad_total += 1 if miss_w else 0
            w("  %-7s 命中 %d/%d %s" % (slot, len(words) - len(miss_w), len(words),
                                        "OK" if not miss_w else "未命中：%s" % miss_w))
        chk(bad_total == 0, "C2 14 条替换件关键实词在该条全文 PDF 中全部命中",
            "%d 条有未命中词" % bad_total)

        # C2b 锚定表必须与正文接地：ANCHOR 的词应当真的是《04》对该条的断言词，
        # 否则锚定表会与正文脱节、变成"只查 PDF 不查文档"。任一词不在该条正文行里即 FAIL。
        _off = []
        for slot, words in ANCHOR.items():
            kw = KEY_BY_SLOT[slot]
            lines = [L for L in body.split("\n") if kw in L]
            miss_d = [x for x in words if not any(x in L for L in lines)]
            if miss_d:
                _off.append("%s：%s 不在该条正文行内" % (slot, miss_d))
        for _x in _off:
            w("  !! %s" % _x)
        chk(not _off, "C2b ANCHOR 关键实词均出现在《04》对应该条的正文行内", "%d 条脱节" % len(_off))

    # ---------- C3 异源词不得与本条同现（直接针对 A1 那类搬运）----------
    w("")
    w("=" * 78)
    w("C3 异源词拦截：不属于该条的方法词不得与该条的正文指称同现（带否定豁免）")
    w("=" * 78)
    fbad = 0
    for slot, words in FOREIGN.items():
        kw = KEY_BY_SLOT[slot]
        hit_lines = [L for L in body.split("\n") if kw in L]
        for wd in words:
            for L in hit_lines:
                i = L.find(wd)
                while i >= 0:
                    win = L[max(0, i - 12):i]
                    if not any(c in win for c in "不未无否非"):
                        w("  !! %s 行内出现异源词「%s」：%s" % (slot, wd, L.strip()[:80]))
                        fbad += 1
                    i = L.find(wd, i + 1)
    w("异源词同现处数：%d" % fbad)
    chk(fbad == 0, "C3 异源词未与该条正文指称同现", "%d 处" % fbad)
    w("")
    w("保留英文条目的题名在《03》《04》中仍可检索到（保留＝照旧）：")
    for slot, title in [("RAG-1", "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks"),
                        ("RAG-9", "From Local to Global"),
                        ("RAG-11", "Ragas"),
                        ("RAG-13", "HotpotQA"),
                        ("FIN-3", "FinanceBench"),
                        ("SYS-13", "RAGPerf")]:
        w("  %-8s 03=%s 04=%s" % (slot, title in t03, title in t04))

    # ---------- D 字段写法 ----------
    w("")
    w("=" * 78)
    w("D 卷号页码与导师字段的实际写法（《03》各条目题录行）")
    w("=" * 78)
    for slot in SLOTS:
        m = re.search(r"^- `%s`[^\n]*?—\s*([^\n]+)$" % re.escape(slot), t03, re.M)
        w("%-8s %s" % (slot, (m.group(1).strip()[:120] if m else "(保留条目，题录照旧)")))
    w("")
    w("《03》中「卷号与页码：知网公开页未提供，记\"—\"」出现次数：%d" % t03.count("卷号与页码：知网公开页未提供"))
    w("《03》中「导师：知网学位论文库公开页不提供，不写」出现次数：%d" % t03.count("导师：知网学位论文库公开页不提供，不写"))
    w("《04》参考文献表中「记\"—\"」出现次数：%d" % refs.count("记\"—\""))
    w("《04》参考文献表中「导师：知网学位论文库公开页不提供，不写」出现次数：%d"
      % refs.count("导师：知网学位论文库公开页不提供，不写"))

    io.open(os.path.join(OUTDIR, "06_文档自检_混合替换后.txt"), "w", encoding="utf-8").write("\n".join(OUT) + "\n")
    print("saved -> _验证输出/06_文档自检_混合替换后.txt")

    # ---------- 门禁退出码 ----------
    # 2026-09-28 依《文献替换独立核验》缺口 G2 新增：原脚本无 sys.exit、恒以 0 退出，
    # A/B/C 的红灯不影响任何退出码、也不在 09_跑验证.py 的流水线内，等于不构成门禁。
    print()
    print("=" * 78)
    if FAILS:
        print("自检结论：存在 %d 项失败：%s" % (len(FAILS), "；".join(FAILS)))
        print("=" * 78)
        sys.exit(1)
    print("自检结论：全部通过（0 项失败）")
    print("=" * 78)
    sys.exit(0)


if __name__ == "__main__":
    main()
