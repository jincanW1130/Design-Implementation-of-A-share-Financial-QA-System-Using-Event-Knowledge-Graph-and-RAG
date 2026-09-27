# -*- coding: utf-8 -*-
"""T9 只读勘察脚本 08：按 chunk_id 或 doc_id 打印原文（核验 gold 用）。

用法：
  python 勘察_08_看块.py chunk 1001000 1001001
  python 勘察_08_看块.py doc 1001
  python 勘察_08_看块.py doc 1001 --head 120
  python 勘察_08_看块.py search 关键词
"""

import io
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = r"C:\Users\15129\Desktop\毕业设计"
DATA = os.path.join(ROOT, "阶段05-数据准备", "数据集", "v2.1")


def iter_jsonl(path):
    with io.open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


DOCS = {d["doc_id"]: d for d in iter_jsonl(os.path.join(DATA, "clean", "documents.jsonl"))}
CHUNKS = list(iter_jsonl(os.path.join(DATA, "chunks", "chunks.jsonl")))
BY_ID = {c["chunk_id"]: c for c in CHUNKS}


def show_chunk(c, head=None):
    d = DOCS[c["doc_id"]]
    body = c["content"]
    if head:
        body = body[:head]
    print("=" * 96)
    print("chunk_id=%d doc_id=%d idx=%d token=%d" % (
        c["chunk_id"], c["doc_id"], c["chunk_index"], c["token_count"]))
    print("doc_title=%s" % d["title"])
    print("source=%s url=%s publish=%s" % (d["source"], d["url"], d["publish_time"]))
    print("-" * 96)
    print(body)


def main(argv):
    if not argv:
        print(__doc__)
        return
    mode = argv[0]
    if mode == "chunk":
        for cid in argv[1:]:
            c = BY_ID.get(int(cid))
            if c is None:
                print("NOT FOUND", cid)
            else:
                show_chunk(c)
    elif mode == "doc":
        docid = int(argv[1])
        head = None
        if "--head" in argv:
            head = int(argv[argv.index("--head") + 1])
        cs = sorted([c for c in CHUNKS if c["doc_id"] == docid], key=lambda x: x["chunk_index"])
        print("DOC %d | %s | chunks=%d" % (docid, DOCS[docid]["title"], len(cs)))
        for c in cs:
            show_chunk(c, head)
    elif mode == "search":
        kw = argv[1]
        for c in CHUNKS:
            if kw in c["content"]:
                print("chunk_id=%d doc=%d idx=%d | %s | %s" % (
                    c["chunk_id"], c["doc_id"], c["chunk_index"],
                    DOCS[c["doc_id"]]["title"][:40], c["content"].replace("\n", " ")[:90]))
    else:
        print("unknown mode", mode)


main(sys.argv[1:])
