# -*- coding: utf-8 -*-
"""生成 22 条题录指纹（只读《03》《04》，只写 `22条题录指纹.json`）。

用途：给《03》第二节总表 22 行、《03》第十节 引用编号对照、《04》参考文献表 22 行
      与《04》正文引用编号留一份**外部金标准**，供 `工具\跨文档核验.py` 的 O 项比对：
      题名改一字、编号错一位、总表「全文」列被改，都应判 FAIL。

口径（逐项写进指纹文件的"口径"字段，避免读者猜）：
  题名/作者/出处/年/卷期页 —— 取自《03》各条目的**题录行**（`- `SLOT` … — 题录`）。
  全文                     —— 取自《03》第二节总表「全文」列括号内的文件名。
  引用编号                 —— 取自《03》第十节「开题报告序号 ↔ 池内编号」对照表。
  正文引用次数             —— 《04》正文（参考文献表之前）中 `[n]` 的出现次数。
  sha256                   —— 对 "槽位|题名|作者|出处|年|卷期页|全文|引用编号" 的
                              UTF-8 字节串取 sha256（小写十六进制）。
  总sha256                 —— 对 22 条 sha256 按槽位顺序以 "\n" 连接后的 UTF-8 字节串取 sha256。

用法：python 11_生成题录指纹.py
产出：22条题录指纹.json（本脚本所在目录）
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # 交付物/08-文献与开题/文献调研与开题
F03 = os.path.join(BASE, "03-精选文献库（22篇）.md")
F04 = os.path.join(BASE, "04-开题报告.md")
OUT = os.path.join(BASE, "_替换执行", "22条题录指纹.json")

SLOTS = ["KG-5", "KG-9", "KG-16", "KG-17", "KG-19", "KG-21", "KG-28", "KG-29",
         "RAG-1", "RAG-9", "RAG-10", "RAG-11", "RAG-13", "RAG-24",
         "FIN-3", "FIN-16", "FIN-17", "FIN-20", "SYS-4", "SYS-8", "SYS-13", "SYS-14"]


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def main() -> None:
    t03 = io.open(F03, encoding="utf-8").read()
    t04 = io.open(F04, encoding="utf-8").read()

    # ---- 《03》第二节 总表：槽位 / 题名 / 年 / 全文列文件名 ----
    m2 = re.search(r"## 二、文献库总表(.*?)\n---\n", t03, re.S)
    if not m2:
        raise SystemExit("未找到《03》第二节总表")
    tbl = {}
    for mm in re.finditer(r"^\| ((?:KG|RAG|FIN|SYS)-\d+) \| ([^|]+?) \| ([^|]+?) \| ([^|]+?) \| "
                          r"([^|]+?) \| ([^|]+?) \| ([^|]+?) \|", m2.group(1), re.M):
        slot, title, _dir, year, _pri, full, _land = [x.strip() for x in mm.groups()]
        fm = re.search(r"（([^）]+)）", full)
        tbl[slot] = {"题名": title, "年": year, "全文": (fm.group(1).strip() if fm else full)}

    # ---- 《03》分节题录行：作者. 题名. 出处, 年 … （卷号页码…）----
    ent = {}
    for mm in re.finditer(r"^- `((?:KG|RAG|FIN|SYS)-\d+)`[^\n]*?—\s*([^\n]+)$", t03, re.M):
        ent[mm.group(1)] = mm.group(2).strip()

    # ---- 《03》第十节 对照表：引用编号 ----
    cite_no = {}
    for mm in re.finditer(r"^\| \[(\d+)\] \| ((?:KG|RAG|FIN|SYS)-\d+) \|", t03, re.M):
        cite_no[mm.group(2)] = int(mm.group(1))

    # ---- 《04》参考文献表 与 正文引用次数 ----
    i11 = t04.index("## 十一、参考文献")
    body = t04[:i11]
    counts = {}
    for no in re.findall(r"\[(\d+)\]", body):
        counts[int(no)] = counts.get(int(no), 0) + 1

    rows = []
    for slot in SLOTS:
        rec = ent.get(slot, "")
        # 题名以《03》总表为准（总表题名是干净的一列，且 22/22 均为题录行的子串）；
        # 据此把题录行切成「作者串 / 题名 / 出处」，避免英文作者名的 "P. Lewis" 里的 ". " 被误切。
        title = tbl.get(slot, {}).get("题名", "")
        assert title and title in rec, "题名不是题录行子串：%s" % slot
        author = rec.split(title, 1)[0].strip().rstrip(".").strip()
        source = rec.split(title, 1)[1].strip().lstrip(".").strip()
        full = tbl.get(slot, {}).get("全文", "")
        # 卷期页口径：题录行里若含「卷号与页码」括注，取整段口径；否则从出处串里取年
        vm = re.search(r"（([^）]*卷号与页码[^）]*)）", rec)
        volpage = vm.group(1).strip() if vm else "（题录行未含卷号页码括注，以出处串为准）"
        year = tbl.get(slot, {}).get("年", "")
        ci = cite_no.get(slot, 0)
        canon = "|".join([slot, title, author, source, year, volpage, full, str(ci)])
        rows.append({
            "槽位": slot,
            "引用编号": ci,
            "题名": title,
            "作者": author,
            "出处": source,
            "年": year,
            "卷期页": volpage,
            "全文": full,
            "正文引用次数": counts.get(ci, 0),
            "sha256": sha(canon),
        })

    total = sha("\n".join(r["sha256"] for r in rows))
    doc = {
        "名称": "《03》22 条题录指纹（外部金标准）",
        "生成脚本": "_替换执行/11_生成题录指纹.py",
        "生成日期": "2026-09-28",
        "用途": "供 工具\\跨文档核验.py 的 O 项比对：《03》总表 22 行题录、总表「全文」列文件名、"
                "《04》参考文献表 22 行与正文引用编号；题名改一字／编号错一位／总表单元格被改均应 FAIL。",
        "口径": {
            "题名/作者/出处/年/卷期页": "取自《03》各条目的题录行",
            "全文": "取自《03》第二节总表「全文」列括号内的文件名",
            "引用编号": "取自《03》第十节 开题报告序号 ↔ 池内编号 对照表",
            "正文引用次数": "《04》正文（参考文献表之前）中 [n] 的出现次数",
            "sha256": "对 槽位|题名|作者|出处|年|卷期页|全文|引用编号 的 UTF-8 字节串取 sha256",
            "总sha256": "22 条 sha256 按槽位顺序以换行连接后取 sha256",
        },
        "总sha256": total,
        "条目": rows,
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
    print("已写出 %s（%d 条，总sha256=%s）" % (os.path.relpath(OUT, BASE), len(rows), total))
    for r in rows:
        print("  [%2d] %-7s %-6s %s" % (r["引用编号"], r["槽位"], r["年"], r["题名"][:44]))


if __name__ == "__main__":
    main()
