# -*- coding: utf-8 -*-
r"""对给定文件／目录逐个打印 `sha256  字节数  相对路径`（相对仓库根；只读）。

用法：python ...\文件摘要.py <路径> [<路径> ...]
"""
import hashlib
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".git")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def iter_files(target):
    if os.path.isfile(target):
        yield target
        return
    for dirpath, _dirs, names in os.walk(target):
        for name in sorted(names):
            yield os.path.join(dirpath, name)


def main(argv):
    rows = []
    for target in argv[1:]:
        target = os.path.abspath(target)
        for path in iter_files(target):
            rows.append((os.path.relpath(path, ROOT).replace("\\", "/"),
                         sha256_file(path), os.path.getsize(path)))
    for rel, digest, size in sorted(rows):
        print("%s  %d  %s" % (digest, size, rel))
    print("（共 %d 个文件）" % len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
