# -*- coding: utf-8 -*-
r"""F8-a 取证：`--docs` 不再静默绕开 pilot 选样断言（只读；不写任何产物、不调模型）。

做三件事（全部在内存里）：
  1. pilot 完整选样 → 断言照跑（problems 为空、无 skip 提示）；
  2. pilot ＋ `--docs 1001` → 断言对子集**不适用**，但必须给出显式 skip 提示（改后行为）；
  3. 负对照：把子集直接喂给 `check_selection` → 断言必然不通过，证明「旧代码的静默跳过」
     不是「子集天然合规」，而是守卫被绕开。
"""
import os
import sys
from types import SimpleNamespace

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".git")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "代码", "抽取与图谱"))

import extract  # noqa: E402


def main():
    docs, _chunks, _by_doc = extract.load_docs_and_chunks()

    args_full = SimpleNamespace(profile="pilot", docs=None, limit=None)
    selection_full = extract.pick_docs(args_full, docs)
    problems, note = extract.selection_assertion(args_full, selection_full)
    print("① pilot 完整选样：%d 篇；断言 problems=%d 条；skip 提示=%r"
          % (len(selection_full), len(problems), note))

    args_docs = SimpleNamespace(profile="pilot", docs="1001", limit=None)
    selection_docs = extract.pick_docs(args_docs, docs)
    problems_docs, note_docs = extract.selection_assertion(args_docs, selection_docs)
    print("② pilot ＋ --docs 1001：%d 篇；断言 problems=%d 条；skip 提示=%r"
          % (len(selection_docs), len(problems_docs), note_docs))

    raw_problems = extract.check_selection(selection_docs)
    print("③ 负对照：把同一子集直接喂给 check_selection → problems=%d 条（前两条：%s）"
          % (len(raw_problems), raw_problems[:2]))
    print("结论：改后 --docs 运行会打印 [选样断言已跳过] 并把原因写进 selection.json 的"
          " assertion_skipped；改前该分支返回空列表且不打任何提示（静默绕过）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
