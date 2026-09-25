# -*- coding: utf-8 -*-
r"""T5 切分与 token 统计（第 5 阶段数据准备管线）。

契约（`代码\数据准备\README.md` 一、二、三.3.4／三.3.7；《12-第5阶段任务书》§五 硬约束 5／7／8、§八）：

    输入  clean\documents.jsonl
    输出  chunks\chunks.jsonl        每行一个文本块：chunk_id、doc_id、chunk_index、content、
                                     token_count、vector_id（本环节一律为 null）
          reports\chunk_stats.json   条数、分类别条数、长度与 token 的 min/mean/max、单块文档数

切分参数全部取自 config.CHUNK（目标 400／上限 512／下限 128／重叠 50／boundary_priority）；
chunk_id 由 config.chunk_id_for 生成（= doc_id * DOC_ID_STRIDE + chunk_index）。

另按要求输出单文档文本块数告警清单 chunk_stats.json["over_long_documents"]（阈值
config.MAX_CHUNKS_PER_DOC_WARN）：列出超阈值文档的 doc_id／title／chunk_count／doc_chars／
share_of_chunks，并在 stdout 打印一行点名最严重者。**只报告，绝不截断、绝不丢弃文档**
（截断等于改写证据，违反《10》§4.4.6）。

另有一条**切分前的编号步长预检**（README §3.4）：逐篇计算投影文本块数，只要有一篇超过
config.DOC_ID_STRIDE，就打印点名 doc_id／标题／字符数／投影块数的可行动错误（并指出该文档
本应被 config.MAX_DOC_CHARS_FOR_INCLUSION 在采集候选阶段排除）后**以非零码退出**，
不再进入切分与落盘。这样同类问题不会再以 config.chunk_id_for 的裸 ValueError 形式出现。

三条硬约束（《12》§五 硬约束 8、§八）：
    1) 每篇文档至少 1 个文本块；chunk_index 在文档内从 0 连续递增、无缺口、无重复；
    2) 任何文本块不超过 max_chars；除"整篇正文短于 target_chars"的文档外，任何文本块不低于 min_chars；
    3) 重叠只用于衔接上下文：overlap_chars(50) < min_chars(128)，重叠区永远不足以在相邻文本块里
       各自构成一个完整证据（《12》§五 硬约束 5、《02》§12.7 第二步"一个文本块只算一个证据"）。

token_count 用 Embedding 模型自带 tokenizer 统计（transformers.AutoTokenizer，不含特殊标记）；
tokenizer 无法加载时回退为"非空白字符数"，并在 reports\chunk_stats.json 与终端明确标注，
绝不静默替换。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

# 控制台为 GBK，必须重设编码后再输出中文（stderr 用于编号步长预检的可行动错误，
# 与 check.py 的处理一致，避免错误信息在中英文混排时乱码）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  唯一参数来源，不得写死任何参数

TOKEN_METHOD_MODEL = "transformers.AutoTokenizer(add_special_tokens=False)"
TOKEN_METHOD_FALLBACK = "non_whitespace_chars"


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=r"第 5 阶段 T5：切分 clean\documents.jsonl → chunks\chunks.jsonl（含 token_count）"
    )
    parser.add_argument("--profile", choices=["v1", "pilot"], default="v1",
                        help="数据集形态：v1（默认）或 pilot")
    parser.add_argument("--dir", dest="dir_override", default=None,
                        help="仅供自测：把数据集根目录改到任意临时目录")
    parser.add_argument("--force", action="store_true",
                        help="忽略已完成标记，强制重跑本环节")
    return parser.parse_args(argv)


def resolve_root(args) -> str:
    if args.dir_override:
        return os.path.abspath(args.dir_override)
    return os.path.abspath(config.dataset_dir(args.profile))


def load_documents(path: str):
    docs = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            docs.append(json.loads(line))
    docs.sort(key=lambda d: int(d["doc_id"]))
    return docs


def is_up_to_date(outputs, inputs) -> bool:
    if not all(os.path.exists(p) for p in outputs):
        return False
    if not inputs:
        return True
    return min(os.path.getmtime(p) for p in outputs) >= max(os.path.getmtime(p) for p in inputs)


# --------------------------------------------------------------------------
# 切分
# --------------------------------------------------------------------------
def _cut_positions(text: str, start: int, hi: int, boundary: str):
    """boundary 在 [start, hi] 内可用的切分位置（= 前一块的结束下标）。

    换行类边界把切点放在换行符之前（前一块不留尾部空白，后一块不留前导空白）；
    句末标点类边界把切点放在标点之后（标点留在前一块）。
    """
    positions = []
    idx = text.find(boundary, start)
    while idx != -1:
        cut = idx if boundary.startswith("\n") else idx + len(boundary)
        if cut > hi:
            break
        if cut >= start:
            positions.append(cut)
        idx = text.find(boundary, idx + 1)
    return positions


def _choose_cut(text: str, start: int, lo: int, target: int, hi: int, boundaries):
    """按 boundary_priority 从高到低找切点；同一优先级内取不超过 target 的最晚位置。"""
    for boundary in boundaries:
        positions = [c for c in _cut_positions(text, start, hi, boundary) if lo <= c <= hi]
        if not positions:
            continue
        before_target = [c for c in positions if c <= target]
        return max(before_target) if before_target else min(positions)
    return None


def _skip_leading_blank(text: str, start: int, end: int) -> int:
    while start < end and text[start] in " \t\r\n\u3000":
        start += 1
    return start


def chunk_document(content, params=None):
    """按 config.CHUNK 切分单篇正文，返回文本块字符串列表（至少 1 块）。"""
    p = params if params is not None else config.CHUNK
    target = int(p["target_chars"])
    max_chars = int(p["max_chars"])
    min_chars = int(p["min_chars"])
    overlap = int(p["overlap_chars"])
    boundaries = list(p["boundary_priority"])

    text = "" if content is None else str(content)
    if p.get("strip_rules"):
        text = text.strip()
    n = len(text)
    if n <= max_chars:
        return [text]

    chunks = []
    start = 0
    while True:
        untrimmed = start
        start = _skip_leading_blank(text, start, n)
        remaining = n - start
        if remaining <= max_chars:
            # 末块：若前导空白把长度压到 min_chars 以下，则不裁剪空白（前提是不超上限）
            if chunks and remaining < min_chars and min_chars <= n - untrimmed <= max_chars:
                start = untrimmed
            chunks.append(text[start:n])
            break
        lo = start + min_chars
        hi = min(start + max_chars, n - (min_chars - overlap))
        if hi < lo:
            hi = min(start + max_chars, n)
        cut = _choose_cut(text, start, lo, start + target, hi, boundaries)
        if cut is None:
            cut = max(lo, min(start + target, hi))
        chunks.append(text[start:cut])
        start = cut - overlap
    return [c for c in chunks if c != ""] or [text]


# --------------------------------------------------------------------------
# token_count：Embedding 模型自带 tokenizer，不含特殊标记
# --------------------------------------------------------------------------
def load_tokenizer():
    """返回 (tokenizer, method, note)；加载失败则回退为非空白字符计数并说明原因。"""
    model_name = config.EMBEDDING["model_name"]
    try:
        from transformers import AutoTokenizer
    except Exception as exc:                                    # pragma: no cover
        return None, TOKEN_METHOD_FALLBACK, "无法导入 transformers：%s: %s" % (type(exc).__name__, exc)
    try:
        tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        return tokenizer, TOKEN_METHOD_MODEL, "local_files_only=True"
    except Exception as local_exc:
        try:
            tokenizer = AutoTokenizer.from_pretrained(model_name)
            return tokenizer, TOKEN_METHOD_MODEL, "本地缓存失败后在线加载成功"
        except Exception as exc:
            return None, TOKEN_METHOD_FALLBACK, (
                "tokenizer 加载失败，已回退为非空白字符计数：本地缓存失败(%s: %s)；在线加载失败(%s: %s)"
                % (type(local_exc).__name__, local_exc, type(exc).__name__, exc)
            )


def count_tokens(tokenizer, texts, fallback: bool):
    if fallback or tokenizer is None:
        return [sum(1 for ch in t if not ch.isspace()) for t in texts]
    encoded = tokenizer(list(texts), add_special_tokens=False)
    return [len(ids) for ids in encoded["input_ids"]]


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------
def write_jsonl(path: str, records) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=False) + "\n")
    os.replace(tmp, path)


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
    os.replace(tmp, path)


def _stats(values):
    if not values:
        return {"min": 0, "mean": 0.0, "max": 0}
    return {"min": min(values), "mean": round(sum(values) / len(values), 2), "max": max(values)}


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    t0 = time.perf_counter()
    args = parse_args(argv)
    root = resolve_root(args)
    documents_path = os.path.join(root, "clean", "documents.jsonl")
    chunks_path = os.path.join(root, "chunks", "chunks.jsonl")
    stats_path = os.path.join(root, "reports", "chunk_stats.json")

    if not os.path.exists(documents_path):
        print("[chunk] 错误：找不到 %s，请先运行 clean.py" % documents_path, file=sys.stderr)
        return 2
    documents = load_documents(documents_path)
    if not documents:
        print("[chunk] 错误：%s 内没有文档" % documents_path, file=sys.stderr)
        return 2

    if not args.force and is_up_to_date([chunks_path, stats_path], [documents_path]):
        print("[chunk] 已完成，跳过（--force 可强制重跑）：%s" % chunks_path)
        return 0

    params = config.CHUNK
    max_chars = int(params["max_chars"])
    min_chars = int(params["min_chars"])
    target_chars = int(params["target_chars"])
    overlap = int(params["overlap_chars"])
    id_stride = int(config.DOC_ID_STRIDE)
    max_doc_chars = int(config.MAX_DOC_CHARS_FOR_INCLUSION)

    # ---- 切分前的编号步长预检（README §3.4）：投影文本块数必须装得进 chunk_id 的步长 ----
    # 目的：让"某一篇文档大到 chunk_id = doc_id * DOC_ID_STRIDE + chunk_index 越界"这件事
    # 以**点名到具体文档、并给出处置线索**的错误暴露出来，而不是 config.chunk_id_for 的裸
    # ValueError。预检只读、只报告：既不改写正文，也不截断、不丢弃文档——命中即整轮中止
    # （退出码非 0），由上游用 config.MAX_DOC_CHARS_FOR_INCLUSION 在候选阶段把这些文档挡掉。
    # 投影与实际切分共用同一实现与同一组参数，故投影块数就是随后会落盘的块数。
    pieces_by_doc = {}
    over_stride = []
    for doc in documents:
        doc_id = int(doc["doc_id"])
        content = str(doc.get("content") or "")
        pieces = chunk_document(content, params)
        pieces_by_doc[doc_id] = pieces
        if len(pieces) > id_stride:
            over_stride.append({
                "doc_id": doc_id,
                "title": str(doc.get("title") or ""),
                "chars": len(content),
                "projected_chunk_count": len(pieces),
            })
    if over_stride:
        over_stride.sort(key=lambda r: (-r["projected_chunk_count"], r["doc_id"]))
        print("[chunk] 错误：有 %d 篇文档的投影文本块数超过编号步长 DOC_ID_STRIDE=%d，"
              "chunk_id = doc_id * DOC_ID_STRIDE + chunk_index 会越界，本环节中止："
              % (len(over_stride), id_stride), file=sys.stderr)
        for rec in over_stride:
            print("[chunk]   doc_id=%d《%s》正文 %d 字符，投影 %d 个文本块（单篇上限 %d 块）"
                  % (rec["doc_id"], rec["title"], rec["chars"],
                     rec["projected_chunk_count"], id_stride), file=sys.stderr)
        print("[chunk] 该文档本应被 config.MAX_DOC_CHARS_FOR_INCLUSION=%d 字符的长度上限在 "
              "fetch.py 的候选阶段整篇排除（不是截断）；请检查 fetch.py 的长度过滤是否生效，"
              "或该文档是否为旧构建遗留在 raw\\ 中、未经 clean.py 的 too_long 兜底跳过。"
              "本环节只报告、只退出，绝不截断正文。" % max_doc_chars, file=sys.stderr)
        return 2

    tokenizer, token_method, token_note = load_tokenizer()
    fallback = token_method != TOKEN_METHOD_MODEL
    if fallback:
        print("[chunk] 警告：tokenizer 未能加载，token_count 回退为“非空白字符数”。原因：%s" % token_note,
              file=sys.stderr)

    records = []
    per_category_chunks = {cat: 0 for cat in config.CATEGORIES}
    per_category_docs = {cat: 0 for cat in config.CATEGORIES}
    chunks_per_doc = {}
    doc_chars, doc_titles = {}, {}
    min_chars_exemptions = []
    violations = []

    for doc in documents:
        doc_id = int(doc["doc_id"])
        category = str(doc.get("category") or "")
        content = str(doc.get("content") or "")
        doc_chars[doc_id] = len(content)
        doc_titles[doc_id] = str(doc.get("title") or "")
        pieces = pieces_by_doc[doc_id]     # 预检已算好，投影＝实际落盘（同一实现、同一参数）
        tokens = count_tokens(tokenizer, pieces, fallback)
        for index, (piece, token_count) in enumerate(zip(pieces, tokens)):
            records.append({
                "chunk_id": config.chunk_id_for(doc_id, index),
                "doc_id": doc_id,
                "chunk_index": index,
                "content": piece,
                "token_count": int(token_count),
                "vector_id": None,
            })
            if len(piece) > max_chars:
                violations.append({"doc_id": doc_id, "chunk_index": index,
                                   "chars": len(piece), "reason": "over_max_chars"})
            if len(piece) < min_chars:
                if len(pieces) == 1 and len(content) < target_chars:
                    min_chars_exemptions.append({"doc_id": doc_id, "chunk_index": index,
                                                 "chars": len(piece), "doc_chars": len(content),
                                                 "reason": "整篇正文短于 target_chars"})
                else:
                    violations.append({"doc_id": doc_id, "chunk_index": index,
                                       "chars": len(piece), "reason": "under_min_chars"})
        chunks_per_doc[doc_id] = len(pieces)
        per_category_chunks[category] = per_category_chunks.get(category, 0) + len(pieces)
        per_category_docs[category] = per_category_docs.get(category, 0) + 1

    chunk_chars = [len(r["content"]) for r in records]
    token_values = [int(r["token_count"]) for r in records]
    chunk_ids = [r["chunk_id"] for r in records]
    contiguous = all(
        sorted(r["chunk_index"] for r in records if r["doc_id"] == doc_id) == list(range(count))
        for doc_id, count in chunks_per_doc.items()
    )
    over_seq = [r["chunk_id"] for r in records
                if int(r["token_count"]) > int(config.EMBEDDING["max_seq_length"])]

    # 单文档文本块数告警清单（只报告，绝不截断、绝不丢弃；《10》§4.4.6 证据按原文展示）。
    # 阈值来自 config.MAX_CHUNKS_PER_DOC_WARN，本文件不写死。
    warn_threshold = int(config.MAX_CHUNKS_PER_DOC_WARN)
    total_chunks = len(records)
    over_long_documents = []
    for doc_id, chunk_count in chunks_per_doc.items():
        if chunk_count <= warn_threshold:
            continue
        over_long_documents.append({
            "doc_id": doc_id,
            "title": doc_titles.get(doc_id, ""),
            "chunk_count": chunk_count,
            "doc_chars": doc_chars.get(doc_id, 0),
            "share_of_chunks": round(chunk_count / total_chunks, 4) if total_chunks else 0.0,
        })
    over_long_documents.sort(key=lambda r: (-r["chunk_count"], r["doc_id"]))

    stats_obj = {
        "params": {
            "target_chars": target_chars,
            "max_chars": max_chars,
            "min_chars": min_chars,
            "overlap_chars": overlap,
            "boundary_priority": list(params["boundary_priority"]),
            "strip_rules": bool(params.get("strip_rules")),
            "doc_id_stride": int(config.DOC_ID_STRIDE),
            "max_chunks_per_doc_warn": warn_threshold,
            "max_doc_chars_for_inclusion": max_doc_chars,
            "chunk_id_rule": "chunk_id = doc_id * DOC_ID_STRIDE + chunk_index (config.chunk_id_for)",
            "id_stride_precheck": ("切分前逐篇投影文本块数；只要有一篇超过 doc_id_stride 就点名"
                                   "doc_id／标题／字符数／投影块数并以非零码中止（绝不截断）"),
        },
        "documents": len(documents),
        "chunks": len(records),
        "documents_with_exactly_1_chunk": sum(1 for c in chunks_per_doc.values() if c == 1),
        "over_long_documents": over_long_documents,
        "per_category_chunks": per_category_chunks,
        "per_category_documents": per_category_docs,
        "chunk_chars": _stats(chunk_chars),
        "token_count": _stats(token_values),
        "tokenizer": {
            "model_name": str(config.EMBEDDING["model_name"]),
            "revision": str(config.EMBEDDING.get("revision", "")),
            "method": token_method,
            "add_special_tokens": False,
            "fallback_used": fallback,
            "note": token_note,
        },
        "overlap_note": ("overlap_chars(%d) < min_chars(%d)：重叠区只用于衔接上下文，"
                         "不足以在相邻文本块里各自构成完整证据" % (overlap, min_chars)),
        "checks": {
            "every_document_has_chunk": all(c >= 1 for c in chunks_per_doc.values()),
            "chunk_index_contiguous_from_0": contiguous,
            "no_chunk_over_max_chars": not any(v["reason"] == "over_max_chars" for v in violations),
            "no_chunk_under_min_chars_except_short_docs": not any(
                v["reason"] == "under_min_chars" for v in violations),
            "min_chars_exempt_chunks": len(min_chars_exemptions),
            "no_duplicate_chunk_id": len(chunk_ids) == len(set(chunk_ids)),
            "vector_id_all_null": all(r["vector_id"] is None for r in records),
            "chunks_over_embedding_max_seq_length": over_seq,
        },
        "chunks_per_doc": {str(k): v for k, v in sorted(chunks_per_doc.items())},
        "min_chars_exemptions": min_chars_exemptions,
        "violations": violations,
    }

    write_jsonl(chunks_path, records)
    write_json(stats_path, stats_obj)

    print("[chunk] profile=%s dir=%s 文档=%d，文本块=%d，单块文档=%d，chars=%d/%s/%d，"
          "token=%d/%s/%d，tokenizer=%s%s，耗时=%.2fs"
          % (args.profile, root, len(documents), len(records),
             stats_obj["documents_with_exactly_1_chunk"],
             stats_obj["chunk_chars"]["min"], stats_obj["chunk_chars"]["mean"],
             stats_obj["chunk_chars"]["max"],
             stats_obj["token_count"]["min"], stats_obj["token_count"]["mean"],
             stats_obj["token_count"]["max"],
             token_method, "（回退）" if fallback else "",
             time.perf_counter() - t0))
    # 单文档超长告警：一行，点名最严重的一篇（只报告，不截断、不丢弃）。
    if over_long_documents:
        worst = over_long_documents[0]
        print("[chunk] 警告：chunk_count 超过 max_chunks_per_doc_warn=%d 的文档 %d 篇；"
              "最严重 doc_id=%d《%s》%d 块，占全部 %d 个文本块的 %.1f%%——"
              "只报告，绝不截断、绝不丢弃（《10》§4.4.6 证据按原文展示）"
              % (warn_threshold, len(over_long_documents), worst["doc_id"], worst["title"],
                 worst["chunk_count"], total_chunks, worst["share_of_chunks"] * 100))
    else:
        print("[chunk] 单文档超长检查（阈值 max_chunks_per_doc_warn=%d）：未发现超长文档"
              % warn_threshold)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
