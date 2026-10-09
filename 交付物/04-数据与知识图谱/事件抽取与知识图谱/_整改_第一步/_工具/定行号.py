# -*- coding: utf-8 -*-
r"""按「纯文本子串」在一组文件里定位行号并打印（只读，供报告引用行号）。

用法：python ...\定行号.py <文件> -- <子串1> <子串2> ...        （每个文件一段，可重复多段）
每个 `--` 之前是文件；之后的子串全部属于该文件。
"""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main(argv):
    blocks, current = [], None
    for item in argv[1:]:
        if item == "--":
            current = None
            continue
        if current is None:
            current = (item, [])
            blocks.append(current)
        else:
            current[1].append(item)
    for path, needles in blocks:
        print("===== %s" % path)
        lines = open(path, encoding="utf-8").read().split("\n")
        for i, line in enumerate(lines, 1):
            for needle in needles:
                if needle in line:
                    print("  %4d  %s" % (i, line.strip()[:118]))
                    break
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
