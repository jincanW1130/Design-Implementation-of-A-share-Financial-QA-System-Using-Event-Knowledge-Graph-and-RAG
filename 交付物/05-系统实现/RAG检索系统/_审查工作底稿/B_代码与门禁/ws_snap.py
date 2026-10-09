# -*- coding: utf-8 -*-
"""把工作区（排除 .git 与 __pycache__）逐文件 SHA-256 落成 JSON。只读。"""
import hashlib
import json
import os
import sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
OUT = sys.argv[2]


def snap(root):
    out = {}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in ('.git', '__pycache__')]
        for f in fn:
            p = os.path.join(dp, f)
            rp = os.path.relpath(p, root).replace(os.sep, '/')
            try:
                with open(p, 'rb') as fh:
                    out[rp] = hashlib.sha256(fh.read()).hexdigest()
            except OSError as e:
                out[rp] = 'ERR:' + type(e).__name__
    return out


data = snap(ROOT)
with open(OUT, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, ensure_ascii=False, sort_keys=True, indent=0)
print('files=%d -> %s' % (len(data), OUT))
