# -*- coding: utf-8 -*-
r"""比对两份「整树摘要」日志里同一棵树的 文件数／字节／整树 sha256 是否逐项相同。

用法：python ...\比对两份摘要.py <开工前日志> <收工后日志>
"""
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LINE = re.compile(r"^(?P<path>\S.*)$")
SUM = re.compile(r"^\s*文件 (?P<n>\d+)／字节 (?P<bytes>\d+)／整树 sha256 (?P<sha>[0-9a-f]{64})\s*$")


def parse(path):
    out, current = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if line.startswith("#"):
            continue
        m = SUM.match(line)
        if m and current:
            out[current] = (int(m.group("n")), int(m.group("bytes")), m.group("sha"))
            continue
        if line and not line.startswith(" ") and "/" in line:
            current = line.strip()
    return out


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    before, after = parse(argv[1]), parse(argv[2])
    trees = sorted(set(before) | set(after))
    same = True
    for tree in trees:
        a, b = before.get(tree), after.get(tree)
        ok = a == b
        same = same and ok
        print("%s  %s" % ("一致" if ok else "不一致", tree))
        print("    开工前：%s" % (a,))
        print("    收工后：%s" % (b,))
    print("结论：%s" % ("四处落点逐文件摘要完全一致" if same else "存在变化，见上"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
