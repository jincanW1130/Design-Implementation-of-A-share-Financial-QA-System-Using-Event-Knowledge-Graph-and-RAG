# -*- coding: utf-8 -*-
r"""F6 破坏试验：把 `图谱导出\v2.1_v1_2\` 整个复制到系统临时目录，并删掉 edges.csv 的最后一行。

只在临时副本上动手；工作区的导出物一个字节都不改。副本目录由参数给出（便于「改前／改后」
两次验收指向同一份副本）。

用法：python ...\建删边副本.py <副本目录>
"""
import os
import shutil
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".git")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)
SRC = os.path.join(ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2")


def main(argv):
    if len(argv) != 2:
        print(__doc__)
        return 2
    dst = os.path.abspath(argv[1])
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst)
    edges = os.path.join(dst, "edges.csv")
    with open(edges, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    print("源目录 = %s" % SRC)
    print("副本目录 = %s" % dst)
    print("复制文件 = %s" % sorted(os.listdir(dst)))
    print("原 edges.csv 行数（含表头）= %d" % len(lines))
    removed = lines[-1]
    with open(edges, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines[:-1]) + "\n")
    with open(edges, encoding="utf-8") as fh:
        after = fh.read().splitlines()
    print("已删除最后一行：%s" % removed)
    print("删后行数（含表头）= %d" % len(after))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
