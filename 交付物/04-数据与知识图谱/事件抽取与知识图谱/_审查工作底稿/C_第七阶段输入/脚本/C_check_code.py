# -*- coding: utf-8 -*-
"""C 审查 —— 第 5 阶段代码里冻结参数的落地核对（只读，只写本产物目录）。

核对对象：交付物/03-代码/数据准备/config.py、embed.py、chunk.py
产出：原始输出/raw_代码冻结参数核对.txt
"""
from __future__ import annotations

import io
import os
import re

HERE = os.path.abspath(os.path.dirname(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "原始输出"))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))

FILES = [
    ("交付物/03-代码/数据准备/config.py", [
        "DATASET_VERSION", "DATA_CUTOFF_DATE", "DATA_CUTOFF_TIME", "WINDOW_START", "WINDOW_END",
        "BUCKET_RECENT", "BUCKET_EARLIER", "ANALYSIS_90_RANGE",
        "CHUNK", "EMBEDDING", "target_chars", "max_chars", "min_chars", "overlap_chars",
        "boundary_priority", "DOC_ID_STRIDE", "MIN_DOC_CHARS", "MAX_CHUNKS_PER_DOC_WARN",
        "MODEL_NAME", "REVISION", "DIM", "NORMALIZE", "POOLING", "INDEX_TYPE",
        "MAX_SEQ_LENGTH", "QUERY_INSTRUCTION", "faiss", "IndexFlatIP",
        "write_index", "read_index", "serialize_index", "deserialize_index",
        "chunk_id_for", "split_chunk_id", "subject_companies",
    ]),
    ("交付物/03-代码/数据准备/embed.py", [
        "write_index", "read_index", "serialize_index", "deserialize_index",
        "IndexFlatIP", "normalize", "faiss", "revision", "MAX_SEQ_LENGTH", "local_files_only",
        "vector_map", "build_meta", "np.save", "faiss.write", "faiss.read",
    ]),
    ("交付物/03-代码/数据准备/chunk.py", [
        "target_chars", "max_chars", "min_chars", "overlap", "DOC_ID_STRIDE", "chunk_id_for",
        "boundary", "strip_rules", "projection", "over_long",
    ]),
]


def main():
    os.makedirs(OUT, exist_ok=True)
    out = []
    for rel, kws in FILES:
        path = os.path.join(ROOT, rel.replace("/", os.sep))
        with io.open(path, encoding="utf-8") as fh:
            lines = fh.read().split("\n")
        out.append("=" * 100)
        out.append("文件：%s　（共 %d 行）" % (rel, len(lines)))
        out.append("=" * 100)
        hits = set()
        for idx, line in enumerate(lines, 1):
            for kw in kws:
                if kw in line:
                    hits.add(idx)
                    break
        prev = -3
        for idx in sorted(hits):
            if idx - prev > 1:
                out.append("")
            out.append("%5d | %s" % (idx, lines[idx - 1]))
            prev = idx
        out.append("")
    dst = os.path.join(OUT, "raw_代码冻结参数核对.txt")
    with io.open(dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out))
    print("[ok] %s" % os.path.relpath(dst, ROOT))


if __name__ == "__main__":
    main()
