# -*- coding: utf-8 -*-
import io
import sys

sys.stdout.reconfigure(encoding="utf-8")
BS = chr(92)  # backslash


def unesc(line):
    n = 0
    i = 0
    while i < len(line):
        if line[i] == BS:
            i += 2
            continue
        if line[i] == "|":
            n += 1
        i += 1
    return n


lines = io.open("B_代码与门禁复核.md", encoding="utf-8").read().split("\n")
blk = []
start = 0


def check(block, s):
    if len(block) < 2:
        return
    cnt = [unesc(x) for x in block]
    if len(set(cnt)) > 1:
        print("!! @行%d: %s" % (s, cnt))
        for i, x in enumerate(block):
            if cnt[i] != cnt[0]:
                print("   行%d n=%d %s" % (s + i, cnt[i], x[:130]))


for i, l in enumerate(lines, 1):
    if l.lstrip().startswith("|"):
        if not blk:
            start = i
        blk.append(l)
    else:
        check(blk, start)
        blk = []
check(blk, start)
print("done")
