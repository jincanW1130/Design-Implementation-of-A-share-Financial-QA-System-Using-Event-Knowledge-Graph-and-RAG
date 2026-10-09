# -*- coding: utf-8 -*-
r"""检查整改报告里以反引号引用的本目录文件是否都存在（只读）。

用法：python ...\查报告引用.py
"""
import os
import re
import sys
import glob

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
REPORT = os.path.join(BASE, "整改报告.md")


def main():
    text = open(REPORT, encoding="utf-8").read()
    refs = set(re.findall(r"`((?:0[1-5]_[^`]*|_工具\\[^`]*)\.(?:txt|json|py))`", text))
    missing = []
    for ref in sorted(refs):
        path = os.path.join(BASE, ref.replace("/", os.sep))
        ok = os.path.exists(path) or bool(glob.glob(path))
        print("%s  %s" % ("存在" if ok else "缺失", ref))
        if not ok:
            missing.append(ref)
    print("共引用 %d 个本目录文件，缺失 %d 个" % (len(refs), len(missing)))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
