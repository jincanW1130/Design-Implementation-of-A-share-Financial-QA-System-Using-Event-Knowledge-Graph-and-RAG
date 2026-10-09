# -*- coding: utf-8 -*-
r"""比对两份 `文件摘要.py` 输出：打印「变化／新增／删除／未变」四组（只读）。

用法：python ...\比对文件摘要.py <改前摘要> <改后摘要>
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def parse(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        parts = line.rstrip("\n").split("  ", 2)
        if len(parts) == 3 and len(parts[0]) == 64:
            out[parts[2]] = (parts[0], int(parts[1]))
    return out


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 2
    before, after = parse(argv[1]), parse(argv[2])
    changed = sorted(p for p in set(before) & set(after) if before[p][0] != after[p][0])
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    same = sorted(p for p in set(before) & set(after) if before[p][0] == after[p][0])
    print("== 内容变化（%d）==" % len(changed))
    for p in changed:
        print("  %s\n      改前 %s  %d 字节\n      改后 %s  %d 字节"
              % (p, before[p][0][:16], before[p][1], after[p][0][:16], after[p][1]))
    print("== 新增（%d）==" % len(added))
    for p in added:
        print("  %s  %s  %d 字节" % (p, after[p][0][:16], after[p][1]))
    print("== 删除（%d）==" % len(removed))
    for p in removed:
        print("  %s" % p)
    print("== 未变（%d）==" % len(same))
    for p in same:
        print("  %s  %s" % (p, after[p][0][:16]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
