# -*- coding: utf-8 -*-
"""T8 数据一致性检查（第 5 阶段数据准备）。

依据：《02-项目执行总控文档》§9.3、《12-第 5 阶段任务书》§五 硬约束 4/6/7/8/9/11/12/13 与 §八
验收标准、`代码\\数据准备\\README.md` §3。

读入：clean\\documents.jsonl、chunks\\chunks.jsonl、index\\vector_map.jsonl、
      index\\build_meta.json、index\\faiss.index
写出：reports\\consistency_report.json、reports\\consistency_report.md、
      reports\\time_coverage.json、reports\\company_coverage.json、
      meta\\dataset.json（《12》§八 第 3 行要求的版本级元信息，由实测数据与 config 生成）

纪律：
  * 每一项检查都记录**实测数值**（条数、编号区间、重复组数……），不得只写"检查通过"
    （《12》§五 硬约束 9）；
  * 术语纪律：FAISS 一律称"向量索引"或"向量检索组件"（《12》§五 硬约束 11）；
  * 本脚本**只做条数与编号一致性核验**，不做检索、排序、相似度查询或任何指标评估
    （《12》§七 非目标 7；任务约定 "check.py only verifies counts and ID consistency"）。

退出码：全部检查通过 -> 0；任一检查不通过 -> 1；输入缺失／不可读 -> 2。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# 控制台为 GBK，必须重设编码后再输出中文。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402  唯一参数来源

CST = timezone(timedelta(hours=8))

# 文档侧必需字段（《12》§八 第 4 行）
REQUIRED_DOC_FIELDS = ("title", "content", "source", "category", "publish_time", "ingest_time")


# --------------------------------------------------------------------------
# 通用小工具
# --------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def read_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("%s 第 %d 行不是合法 JSON：%s" % (path, lineno, exc)) from exc
    return rows


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json_atomic(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_text_atomic(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="T8 数据一致性检查：条数、编号、时间与来源分布（第 5 阶段数据准备）")
    p.add_argument("--profile", choices=["v1", "pilot"], default="v1",
                   help="v1（默认）检查正式数据集目录；pilot 检查 _试跑\\")
    p.add_argument("--dir", default=None,
                   help="仅供自测：覆盖被检查的数据集根目录（正式封版不得使用）")
    p.add_argument("--force", action="store_true",
                   help="忽略已完成标记，强制重算（本脚本每次运行都全量重算，此参数只为满足统一契约）")
    return p.parse_args(argv)


def resolve_root(args) -> str:
    return os.path.abspath(args.dir) if args.dir else config.dataset_dir(args.profile)


def parse_date(value):
    """'YYYY-MM-DD'（允许带 ISO8601 时间部分的写法）-> date；无法解析返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            return None


def normalize_title(title: str) -> str:
    """按 config.DEDUP['title_normalize'] 的口径规范化标题：
    去除首尾空白 -> 去除全角空格 -> 合并连续空白。"""
    s = "" if title is None else str(title)
    if "去除全角空格" in config.DEDUP["title_normalize"]:
        s = s.replace("　", " ")
    if "合并连续空白" in config.DEDUP["title_normalize"]:
        s = re.sub(r"\s+", " ", s)
    if "去除首尾空白" in config.DEDUP["title_normalize"]:
        s = s.strip()
    return s


def fingerprint_of(doc):
    """返回 (指纹, 是否由本脚本按正文重算)。字段缺失时用 sha256(content) 前 16 位兜底，
    以便检查仍可执行（并在报告里如实标出重算条数）。"""
    v = doc.get("content_sha256_16")
    if isinstance(v, str) and v.strip():
        return v.strip(), False
    return hashlib.sha256(str(doc.get("content") or "").encode("utf-8")).hexdigest()[:16], True


def read_index_ntotal(path: str):
    """读回向量索引的条数与维度。

    不用 faiss.read_index：它走 C++ 的 fopen，在含中文的路径下会失败（本项目数据集路径含中文）。
    改用 Python 读字节 + faiss.deserialize_index，格式与 faiss.read_index 完全一致。
    """
    import faiss
    import numpy as np

    with open(path, "rb") as f:
        raw = f.read()
    idx = faiss.deserialize_index(np.frombuffer(bytearray(raw), dtype=np.uint8))
    return int(idx.ntotal), int(idx.d)


def dup_groups(values):
    """返回 {值: 出现次数} 里出现次数 > 1 的部分（跳过 None/空串由调用方决定）。"""
    c = Counter(values)
    return {k: n for k, n in c.items() if n > 1}


def brief(seq, limit=5):
    seq = list(seq)
    return seq[:limit]


def month_range_histogram(date_list):
    """逐月文档数，覆盖**最早与最晚文档之间的每一个自然月**（含无文档的月份，显式记 0）。

    《12》v1.2 修订的报告要求：区间统计量（最早／最晚／跨度）看不出"窗口内部整月为空"，
    因此月度直方图必须对空月显式记 0，不得省略键。
    """
    if not date_list:
        return {}
    counts = Counter(dt.strftime("%Y-%m") for dt in date_list)
    cur = min(date_list).replace(day=1)
    last = max(date_list).replace(day=1)
    out = {}
    while cur <= last:
        key = cur.strftime("%Y-%m")
        out[key] = counts.get(key, 0)
        cur = (cur + timedelta(days=32)).replace(day=1)
    return out


def render_measured(measured) -> str:
    """把 measured 字典压成一行 key=value 的紧凑描述，供 Markdown 报告使用。"""
    parts = []
    for k, v in measured.items():
        if isinstance(v, (list, dict)) and not v:
            v = "空"
        elif isinstance(v, float):
            v = round(v, 4)
        parts.append("%s=%s" % (k, v))
    return "；".join(parts)


# --------------------------------------------------------------------------
# 检查项
# --------------------------------------------------------------------------
class Report:
    def __init__(self, profile: str, root: str):
        self.profile = profile
        self.root = root
        self.checks = []

    def add(self, cid, name, basis, passed, measured, detail=""):
        self.checks.append({
            "id": cid,
            "name": name,
            "basis": basis,
            "pass": bool(passed),
            "measured": measured,
            "detail": detail,
        })
        return bool(passed)

    @property
    def failed(self):
        return [c for c in self.checks if not c["pass"]]

    @property
    def ok(self):
        return not self.failed


def build_dataset_meta(*, profile, root, docs, chunks, index_meta, covered_codes,
                       configured_codes, date_list, month_hist, recent_docs, earlier_docs,
                       analysis_docs, summary, generated_at):
    """汇总 meta\\dataset.json 的内容（《12》§八 第 3 行）。

    全部数值都来自**实测的数据集内容**（documents.jsonl／chunks.jsonl／
    index\\build_meta.json）与 config.py，不在本函数里写死任何规模、时间或模型参数：
      dataset_version、data_cutoff_time、规模（公司数／文档数／文本块数）、时间范围、
      Embedding 模型与版本、切分参数、生成时间。
    模型与版本优先取 index\\build_meta.json（实际建索引时落盘的记录），缺失字段回退 config。
    """
    emb_cfg = config.EMBEDDING
    idx_meta = index_meta if isinstance(index_meta, dict) else {}
    model_name = idx_meta.get("model_name") or emb_cfg["model_name"]
    model_version = idx_meta.get("model_revision") or emb_cfg["revision"]
    emb_from_index = bool(idx_meta.get("model_name") and idx_meta.get("model_revision"))
    n_docs, n_chunks = len(docs), len(chunks)
    cutoff = parse_date(config.DATA_CUTOFF_DATE)
    return {
        "dataset_version": config.DATASET_VERSION,
        "pipeline_version": config.PIPELINE_VERSION,
        "data_cutoff_time": config.DATA_CUTOFF_TIME,
        "data_cutoff_date": config.DATA_CUTOFF_DATE,
        "scale": {
            "company_count": len(covered_codes),
            "configured_company_count": len(configured_codes),
            "doc_count": n_docs,
            "chunk_count": n_chunks,
            "company_count_basis": "documents.jsonl 中 company_list 的并集（实测）",
        },
        "time_range": {
            "publish_time_min": min(date_list).isoformat() if date_list else None,
            "publish_time_max": max(date_list).isoformat() if date_list else None,
            "span_days_between_min_and_max": (max(date_list) - min(date_list)).days if date_list else None,
            "cutoff_minus_earliest_days": (cutoff - min(date_list)).days if date_list else None,
            "window_start": config.WINDOW_START,
            "window_end": config.WINDOW_END,
            "window_days": config.WINDOW_DAYS,
            "buckets": {
                "recent": {"range": list(config.BUCKET_RECENT), "doc_count": len(recent_docs)},
                "earlier": {"range": list(config.BUCKET_EARLIER), "doc_count": len(earlier_docs)},
            },
            "analysis_90_range": {
                "range": list(config.ANALYSIS_90_RANGE),
                "doc_count": len(analysis_docs),
                "gate": False,
                "note": "报告项，不参与 check #13 的通过判定",
            },
            "per_month_histogram": month_hist,
            "per_month_histogram_basis": ("覆盖最早与最晚文档之间的每一个自然月；无文档的月份"
                                          "显式记 0，不得省略键（《12》v1.2 修订）"),
            "months_with_zero_documents": [m for m, c in month_hist.items() if c == 0],
            "basis": "documents.jsonl 的 publish_time（实测）",
        },
        "embedding": {
            "model_name": model_name,
            "model_version": model_version,
            "resolved_snapshot": idx_meta.get("resolved_snapshot") or emb_cfg["revision"],
            "dim": idx_meta.get("dim") or emb_cfg["dim"],
            "pooling": idx_meta.get("pooling") or emb_cfg["pooling"],
            "similarity": idx_meta.get("similarity") or emb_cfg["similarity"],
            "normalize_embeddings": idx_meta.get("normalize_embeddings", emb_cfg["normalize"]),
            "max_seq_length": idx_meta.get("max_seq_length") or emb_cfg["max_seq_length"],
            "device": idx_meta.get("device") or emb_cfg["device"],
            "query_instruction": idx_meta.get("query_instruction", emb_cfg["query_instruction"]),
            "vector_count": idx_meta.get("vector_count", n_chunks),
            "revision_matches_config": model_version == emb_cfg["revision"],
            "basis": ("index\\build_meta.json（实际建索引记录）" if emb_from_index
                      else "config.EMBEDDING（index\\build_meta.json 缺失或字段不全时回退）"),
        },
        "chunking": {
            "unit": "字符（中文按字符计，config.CHUNK 口径）",
            "target_chars": config.CHUNK["target_chars"],
            "max_chars": config.CHUNK["max_chars"],
            "min_chars": config.CHUNK["min_chars"],
            "overlap_chars": config.CHUNK["overlap_chars"],
            "boundary_priority": list(config.CHUNK["boundary_priority"]),
            "strip_rules": config.CHUNK["strip_rules"],
            "min_doc_chars": config.MIN_DOC_CHARS,
            "chunk_id_stride": config.DOC_ID_STRIDE,
            "chunk_id_rule": "chunk_id = doc_id * DOC_ID_STRIDE + chunk_index（config.chunk_id_for）",
            "basis": "config.CHUNK（封版后不得更改）",
        },
        "generated_at": generated_at,
        "generated_by": "check.py（T8 一致性检查，随报告一并重建）",
        "profile": profile,
        "root": root,
        "category_counts": dict(Counter(d.get("category") for d in docs)),
        "consistency": dict(summary),
    }


def main(argv=None) -> int:
    t_all = time.time()
    args = parse_args(argv)
    root = resolve_root(args)
    docs_p = os.path.join(root, "clean", "documents.jsonl")
    chunks_p = os.path.join(root, "chunks", "chunks.jsonl")
    index_dir = os.path.join(root, "index")
    map_p = os.path.join(index_dir, config.FAISS["map_file"])
    meta_p = os.path.join(index_dir, config.FAISS["meta_file"])
    idx_p = os.path.join(index_dir, config.FAISS["index_file"])
    reports_dir = os.path.join(root, "reports")

    print("[check] profile=%s  root=%s" % (args.profile, root))
    if args.dir:
        print("[check] 注意：--dir 仅供自测，不产出正式交付物")

    missing = [p for p in (docs_p, chunks_p) if not os.path.isfile(p)]
    if missing:
        for p in missing:
            print("[check] 失败：找不到输入 %s" % p)
        return 2

    docs = read_jsonl(docs_p)
    chunks = read_jsonl(chunks_p)
    vmap = read_jsonl(map_p) if os.path.isfile(map_p) else []
    meta = read_json(meta_p) if os.path.isfile(meta_p) else {}

    idx_ntotal, idx_dim = None, None
    idx_error = ""
    if os.path.isfile(idx_p):
        try:
            idx_ntotal, idx_dim = read_index_ntotal(idx_p)
        except Exception as exc:
            idx_error = "%s: %s" % (type(exc).__name__, exc)
    else:
        idx_error = "文件不存在"

    rep = Report(args.profile, root)
    n_docs, n_chunks = len(docs), len(chunks)
    if n_docs == 0 or n_chunks == 0:
        # 空输入不允许"全部通过"——那会把"没数据"报成"数据一致"。
        print("[check] 失败：输入为空（文档 %d 篇／文本块 %d 个），无法进行一致性检查；"
              "该数据集不构成可交付的数据集" % (n_docs, n_chunks))
        return 2

    doc_by_id = {}
    dup_doc_ids = []
    for d in docs:
        did = d.get("doc_id")
        if did in doc_by_id:
            dup_doc_ids.append(did)
        else:
            doc_by_id[did] = d

    category_counts = dict(Counter(d.get("category") for d in docs))
    source_counts = dict(Counter(d.get("source") for d in docs))

    # ---- 检查 1：向量条数 == 文本块条数；无空 vector_id；vector_id 恰为 0..N-1 ----
    vector_ids = [c.get("vector_id") for c in chunks]
    null_vid = [c.get("chunk_id") for c in chunks if c.get("vector_id") is None]
    non_int_vid = [c.get("chunk_id") for c in chunks
                   if c.get("vector_id") is not None and not isinstance(c.get("vector_id"), int)]
    present_vids = [v for v in vector_ids if isinstance(v, int) and not isinstance(v, bool)]
    vid_dups = dup_groups(present_vids)
    expected = list(range(n_chunks))
    missing_ids = [v for v in expected if v not in set(present_vids)]
    out_of_range = sorted({v for v in present_vids if v < 0 or v >= n_chunks})
    map_vids = sorted(r.get("vector_id") for r in vmap if isinstance(r.get("vector_id"), int))
    measured_1 = {
        "documents": n_docs,
        "chunks": n_chunks,
        "chunks_with_null_vector_id": len(null_vid),
        "chunks_with_non_int_vector_id": len(non_int_vid),
        "distinct_vector_ids": len(set(present_vids)),
        "duplicate_vector_id_count": len(vid_dups),
        "vector_id_min": min(present_vids) if present_vids else None,
        "vector_id_max": max(present_vids) if present_vids else None,
        "expected_range": "0..%d" % (n_chunks - 1) if n_chunks else "0..-1",
        "missing_vector_ids": len(missing_ids),
        "out_of_range_vector_ids": len(out_of_range),
        "vector_map_rows": len(vmap),
        "faiss_index_ntotal": idx_ntotal,
        "faiss_index_dim": idx_dim,
        "faiss_index_read_error": idx_error,
        "build_meta_vector_count": meta.get("vector_count"),
        "null_vector_id_samples": brief(null_vid),
        "duplicate_vector_id_samples": brief(sorted(vid_dups)),
    }
    pass_1 = (
        not idx_error
        and idx_ntotal == n_chunks
        and len(vmap) == n_chunks
        and map_vids == expected
        and len(null_vid) == 0
        and len(non_int_vid) == 0
        and not vid_dups
        and not missing_ids
        and not out_of_range
        and meta.get("vector_count") == n_chunks
    )
    rep.add(1, "vector_count_equals_chunk_count",
            "《12》§五 硬约束 9、§八；《02》§9.3（向量条数 = 文本块条数，无空 vector_id）",
            pass_1, measured_1,
            "向量索引 faiss.index 的 ntotal、vector_map.jsonl 行数、chunks.jsonl 条数三者必须都为 %d，"
            "且 vector_id 恰为 0..%d-1" % (n_chunks, n_chunks - 1))

    # ---- 检查 2：每个 chunk 的 doc_id 都能在 documents.jsonl 中找到 ----
    unknown = [c.get("chunk_id") for c in chunks if c.get("doc_id") not in doc_by_id]
    chunk_doc_ids = {c.get("doc_id") for c in chunks}
    docs_without_chunk = [d.get("doc_id") for d in docs if d.get("doc_id") not in chunk_doc_ids]
    measured_2 = {
        "documents": n_docs,
        "distinct_doc_ids_in_documents": len(doc_by_id),
        "duplicate_doc_id_in_documents": len(dup_doc_ids),
        "chunks": n_chunks,
        "distinct_doc_ids_in_chunks": len(chunk_doc_ids),
        "chunks_with_unknown_doc_id": len(unknown),
        "documents_without_any_chunk": len(docs_without_chunk),
        "unknown_doc_id_samples": brief(unknown),
        "documents_without_chunk_samples": brief(docs_without_chunk),
    }
    pass_2 = len(unknown) == 0 and len(dup_doc_ids) == 0
    rep.add(2, "chunk_doc_id_exists_in_documents",
            "《10》§4.4 外键 document_chunk.doc_id -> document.doc_id；三级映射链路",
            pass_2, measured_2,
            "chunks 里每个 doc_id 必须是 documents.jsonl 中存在的 doc_id；documents 内 doc_id 不得重复")

    # ---- 检查 3：每篇文档 >=1 个文本块；chunk_index 文档内从 0 连续递增且不重复 ----
    by_doc = defaultdict(list)
    for c in chunks:
        by_doc[c.get("doc_id")].append(c)
    gap_docs, dup_index_docs = [], []
    max_chunks_in_doc = 0
    for did, cs in by_doc.items():
        max_chunks_in_doc = max(max_chunks_in_doc, len(cs))
        idxs = [c.get("chunk_index") for c in cs]
        if len(set(idxs)) != len(idxs):
            dup_index_docs.append(did)
        ints = sorted(x for x in idxs if isinstance(x, int))
        if ints != list(range(len(cs))):
            # 非整数 chunk_index 或存在缺号/不连续
            gap_docs.append(did)
    zero_chunk_docs = list(docs_without_chunk)
    measured_3 = {
        "documents": n_docs,
        "chunks": n_chunks,
        "documents_with_zero_chunks": len(zero_chunk_docs),
        "documents_with_index_gap_or_nonint": len(gap_docs),
        "documents_with_duplicate_chunk_index": len(dup_index_docs),
        "min_chunks_per_document": min((len(c) for c in by_doc.values()), default=0),
        "max_chunks_per_document": max_chunks_in_doc,
        "avg_chunks_per_document": round(n_chunks / n_docs, 2) if n_docs else 0,
        "zero_chunk_document_samples": brief(zero_chunk_docs),
        "gap_document_samples": brief(gap_docs),
        "duplicate_index_document_samples": brief(dup_index_docs),
    }
    pass_3 = not zero_chunk_docs and not gap_docs and not dup_index_docs
    rep.add(3, "document_chunk_index_contiguous",
            "《12》§五 硬约束 8、§八；uk_chunk_doc_index（文档内 chunk_index 从 0 连续无重复）",
            pass_3, measured_3,
            "每篇文档至少 1 个文本块；同一文档内 chunk_index 必须恰好是 0..k-1")

    # ---- 检查 4：chunk_id == doc_id * 1000 + chunk_index（用 config.split_chunk_id 反查） ----
    bad_formula = []
    for c in chunks:
        cid, did, cix = c.get("chunk_id"), c.get("doc_id"), c.get("chunk_index")
        if not all(isinstance(x, int) for x in (cid, did, cix)):
            bad_formula.append(cid)
            continue
        try:
            if config.split_chunk_id(cid) != (did, cix):
                bad_formula.append(cid)
            elif config.chunk_id_for(did, cix) != cid:
                bad_formula.append(cid)
        except Exception:
            # chunk_index 越界（>= DOC_ID_STRIDE）等非法取值一律计为不一致
            bad_formula.append(cid)
    measured_4 = {
        "chunks": n_chunks,
        "chunk_id_stride": config.DOC_ID_STRIDE,
        "formula": "chunk_id = doc_id * %d + chunk_index" % config.DOC_ID_STRIDE,
        "mismatched": len(bad_formula),
        "mismatch_samples": brief(bad_formula),
        "split_chunk_id_roundtrip_ok": n_chunks - len(bad_formula),
    }
    rep.add(4, "chunk_id_formula",
            "《12》§五 硬约束 7；config.chunk_id_for / split_chunk_id（双射可反查）",
            len(bad_formula) == 0, measured_4,
            "每个 chunk 的 chunk_id 必须能由 config.split_chunk_id 反查出 (doc_id, chunk_index) 且与行内字段一致")

    # ---- 检查 5：三级映射双向可查 ----
    map_by_vid = {}
    dup_map_vid = []
    for r in vmap:
        vid = r.get("vector_id")
        if vid in map_by_vid:
            dup_map_vid.append(vid)
        else:
            map_by_vid[vid] = r
    resolve_fail, map_chunk_mismatch, map_doc_mismatch, chunk_without_entry = [], [], [], []
    for vid in expected:
        row = map_by_vid.get(vid)
        if row is None:
            resolve_fail.append(vid)
    for c in chunks:
        vid = c.get("vector_id")
        if not isinstance(vid, int):
            chunk_without_entry.append(c.get("chunk_id"))
            continue
        row = map_by_vid.get(vid)
        if row is None:
            chunk_without_entry.append(c.get("chunk_id"))
            continue
        if row.get("chunk_id") != c.get("chunk_id"):
            map_chunk_mismatch.append({"vector_id": vid, "map_chunk_id": row.get("chunk_id"),
                                       "chunks_jsonl_chunk_id": c.get("chunk_id")})
        if row.get("doc_id") != c.get("doc_id"):
            map_doc_mismatch.append({"vector_id": vid, "map_doc_id": row.get("doc_id"),
                                     "chunks_jsonl_doc_id": c.get("doc_id")})
    measured_5 = {
        "vector_map_rows": len(vmap),
        "distinct_vector_ids_in_map": len(map_by_vid),
        "duplicate_vector_id_in_map": len(dup_map_vid),
        "vector_ids_unresolvable": len(resolve_fail),
        "chunks_without_map_entry": len(chunk_without_entry),
        "chunks_whose_map_chunk_id_differs": len(map_chunk_mismatch),
        "chunks_whose_map_doc_id_differs": len(map_doc_mismatch),
        "resolution_rate": "%d/%d" % (len(vmap) - len(resolve_fail), n_chunks) if n_chunks else "0/0",
        "unresolvable_samples": brief(resolve_fail),
        "chunk_id_mismatch_samples": map_chunk_mismatch[:3],
        "doc_id_mismatch_samples": map_doc_mismatch[:3],
    }
    pass_5 = (not dup_map_vid and not resolve_fail and not chunk_without_entry
              and not map_chunk_mismatch and not map_doc_mismatch and len(vmap) == n_chunks)
    rep.add(5, "mapping_bidirectional",
            "《12》§五 硬约束 6；《02》§9.3；README §3.5（vector_id -> chunk_id -> doc_id 双向可查）",
            pass_5, measured_5,
            "vector_map 的每个 vector_id 都要解到 chunk_id，且该 chunk 在 chunks.jsonl 中回指的 vector_id 相同；反向亦须成立")

    # ---- 检查 6：publish_time 不晚于 data_cutoff，且落在 [WINDOW_START, WINDOW_END] ----
    cutoff = parse_date(config.DATA_CUTOFF_DATE)
    w_start = parse_date(config.WINDOW_START)
    w_end = parse_date(config.WINDOW_END)
    after_cutoff, before_start, after_end, unparsable = [], [], [], []
    date_list = []
    for d in docs:
        dt = parse_date(d.get("publish_time"))
        if dt is None:
            unparsable.append(d.get("doc_id"))
            continue
        date_list.append(dt)
        if dt > cutoff:
            after_cutoff.append({"doc_id": d.get("doc_id"), "publish_time": d.get("publish_time")})
        if dt < w_start:
            before_start.append({"doc_id": d.get("doc_id"), "publish_time": d.get("publish_time")})
        if dt > w_end:
            after_end.append({"doc_id": d.get("doc_id"), "publish_time": d.get("publish_time")})
    measured_6 = {
        "documents": n_docs,
        "data_cutoff_date": config.DATA_CUTOFF_DATE,
        "window_start": config.WINDOW_START,
        "window_end": config.WINDOW_END,
        "publish_time_min": min(date_list).isoformat() if date_list else None,
        "publish_time_max": max(date_list).isoformat() if date_list else None,
        "later_than_cutoff": len(after_cutoff),
        "earlier_than_window_start": len(before_start),
        "later_than_window_end": len(after_end),
        "unparsable_publish_time": len(unparsable),
        "cutoff_minus_max_days": (cutoff - max(date_list)).days if date_list else None,
        "violation_samples": brief(after_cutoff + before_start + after_end),
    }
    pass_6 = not (after_cutoff or before_start or after_end or unparsable)
    rep.add(6, "publish_time_within_window",
            "《12》§五 硬约束 4、§八；《02》§10.1（publish_time <= data_cutoff_time，且落在数据时间窗内）",
            pass_6, measured_6,
            "全部 publish_time 必须 <= %s 且落在 [%s, %s] 内"
            % (config.DATA_CUTOFF_DATE, config.WINDOW_START, config.WINDOW_END))

    # ---- 检查 7：url 唯一；规范化 title 唯一；content_sha256_16 唯一 ----
    urls, norm_titles, fps = [], [], []
    url_missing, fp_recomputed = 0, 0
    for d in docs:
        u = d.get("url")
        if isinstance(u, str) and u.strip():
            urls.append(u.strip())
        else:
            url_missing += 1
        norm_titles.append(normalize_title(d.get("title")))
        fp, recomputed = fingerprint_of(d)
        fp_recomputed += int(recomputed)
        fps.append(fp)
    url_dups = dup_groups(urls)
    title_dups = dup_groups([t for t in norm_titles if t])
    fp_dups = dup_groups([f for f in fps if f])
    measured_7 = {
        "documents": n_docs,
        "urls_non_empty": len(urls),
        "urls_blank": url_missing,
        "distinct_urls": len(set(urls)),
        "duplicate_url_groups": len(url_dups),
        "distinct_normalized_titles": len(set(t for t in norm_titles if t)),
        "duplicate_title_groups": len(title_dups),
        "blank_titles": sum(1 for t in norm_titles if not t),
        "distinct_content_fingerprints": len(set(f for f in fps if f)),
        "duplicate_fingerprint_groups": len(fp_dups),
        "fingerprints_recomputed_here": fp_recomputed,
        "duplicate_url_samples": brief(sorted(url_dups)),
        "duplicate_title_samples": brief(sorted(title_dups)),
        "duplicate_fingerprint_samples": brief(sorted(fp_dups)),
    }
    pass_7 = (not url_dups and not title_dups and not fp_dups)
    rep.add(7, "dedup_keys_unique",
            "《12》§八（url 唯一；title 规范化后唯一；正文 SHA-256 前 16 位唯一）",
            pass_7, measured_7,
            "url 唯一（空 url 按《12》§五 硬约束 3 允许存在、不计入重复）；title 规范化后唯一；"
            "content_sha256_16 唯一。监管公开信息同题标题按'原标题（当事人）'构造后再判重（构造在 clean.py）")

    # ---- 检查 8：company_list 取值规范 ----
    null_cl, non_list_cl = [], []
    empty_by_cat = Counter()
    empty_required = []
    for d in docs:
        cl = d.get("company_list", "__MISSING__")
        if cl is None or cl == "__MISSING__":
            null_cl.append(d.get("doc_id"))
            continue
        if not isinstance(cl, list):
            non_list_cl.append(d.get("doc_id"))
            continue
        if len(cl) == 0:
            empty_by_cat[d.get("category")] += 1
            if d.get("category") in config.CATEGORIES_REQUIRING_COMPANY:
                empty_required.append({"doc_id": d.get("doc_id"), "category": d.get("category")})
    measured_8 = {
        "documents": n_docs,
        "null_or_missing_company_list": len(null_cl),
        "non_list_company_list": len(non_list_cl),
        "empty_company_list_total": sum(empty_by_cat.values()),
        "empty_company_list_by_category": dict(empty_by_cat),
        "empty_but_required": len(empty_required),
        "categories_requiring_non_empty": list(config.CATEGORIES_REQUIRING_COMPANY),
        "null_samples": brief(null_cl),
        "non_list_samples": brief(non_list_cl),
        "empty_required_samples": empty_required[:5],
    }
    pass_8 = not null_cl and not non_list_cl and not empty_required
    rep.add(8, "company_list_presence",
            "《12》§八 修订后验收项（公告与财经新闻 company_list 非空；政策文件与监管公开信息允许空数组但不得为 null）",
            pass_8, measured_8,
            "任何文档的 company_list 都不得为 null；%s 的 company_list 必须非空（允许空数组的是政策文件与监管公开信息）"
            % "/".join(config.CATEGORIES_REQUIRING_COMPANY))

    # ---- 检查 9：category 只取 config.CATEGORIES ----
    cats = [d.get("category") for d in docs]
    invalid_cats = sorted({c for c in cats if c not in config.CATEGORIES})
    measured_9 = {
        "documents": n_docs,
        "allowed_categories": list(config.CATEGORIES),
        "distinct_categories": sorted({c for c in cats if c is not None}),
        "distinct_category_count": len({c for c in cats if c is not None}),
        "invalid_category_count": len(invalid_cats),
        "invalid_categories": invalid_cats,
        "category_counts": category_counts,
        "source_counts": source_counts,
    }
    pass_9 = not invalid_cats and len(category_counts) > 0
    rep.add(9, "category_values",
            "《12》§五 硬约束 12、§八（来源只出现四类 category；无股吧来源）",
            pass_9, measured_9,
            "category 只能取 %s" % "/".join(config.CATEGORIES))

    # ---- 检查 10：文档必需字段无空值 ----
    missing_by_field = Counter()
    docs_with_missing = []
    for d in docs:
        bad = []
        for f in REQUIRED_DOC_FIELDS:
            v = d.get(f)
            if v is None or (isinstance(v, str) and not v.strip()):
                missing_by_field[f] += 1
                bad.append(f)
        if bad:
            docs_with_missing.append({"doc_id": d.get("doc_id"), "missing": bad})
    measured_10 = {
        "documents": n_docs,
        "required_fields": list(REQUIRED_DOC_FIELDS),
        "missing_count_by_field": {f: missing_by_field.get(f, 0) for f in REQUIRED_DOC_FIELDS},
        "documents_with_any_missing": len(docs_with_missing),
        "documents_without_any_missing": n_docs - len(docs_with_missing),
        "missing_samples": docs_with_missing[:5],
    }
    pass_10 = not docs_with_missing
    rep.add(10, "required_fields_present",
            "《12》§八 第 4 行、§五 硬约束 3（title/content/source/category/publish_time/ingest_time 无空值）",
            pass_10, measured_10,
            "逐行检查 %s 六个字段均非空" % "/".join(REQUIRED_DOC_FIELDS))

    # ---- 检查 11：编号稳定性——doc_id 落在 config.DOC_ID_BLOCK 规定的块内 ----
    blocks = {}
    out_of_block = []
    for d in docs:
        cat, did = d.get("category"), d.get("doc_id")
        blk = config.DOC_ID_BLOCK.get(cat)
        if blk is None or not isinstance(did, int):
            out_of_block.append({"doc_id": did, "category": cat})
            continue
        seq = did - blk
        entry = blocks.setdefault(cat, {"expected_block": blk, "count": 0,
                                        "min_doc_id": did, "max_doc_id": did,
                                        "min_seq": seq, "max_seq": seq})
        entry["count"] += 1
        entry["min_doc_id"] = min(entry["min_doc_id"], did)
        entry["max_doc_id"] = max(entry["max_doc_id"], did)
        entry["min_seq"] = min(entry["min_seq"], seq)
        entry["max_seq"] = max(entry["max_seq"], seq)
        if not (1 <= seq < config.DOC_ID_STRIDE):
            out_of_block.append({"doc_id": did, "category": cat, "seq": seq})
    for cat, entry in blocks.items():
        entry["seq_range"] = "1..%d" % (config.DOC_ID_STRIDE - 1)
    for cat in config.CATEGORIES:
        blocks.setdefault(cat, {"expected_block": config.DOC_ID_BLOCK.get(cat), "count": 0,
                                "min_doc_id": None, "max_doc_id": None,
                                "min_seq": None, "max_seq": None,
                                "seq_range": "1..%d" % (config.DOC_ID_STRIDE - 1)})
    # 块内序号在**同一 category 内**必须唯一；不同类别各自从 1 开始，跨类别重复是正常的。
    seq_all = []
    for d in docs:
        blk = config.DOC_ID_BLOCK.get(d.get("category"))
        if blk is not None and isinstance(d.get("doc_id"), int):
            seq_all.append((d.get("category"), d["doc_id"] - blk))
    dup_seq = dup_groups(seq_all)
    measured_11 = {
        "documents": n_docs,
        "duplicate_doc_ids": len(dup_doc_ids),
        "doc_id_blocks": blocks,
        "out_of_block_count": len(out_of_block),
        "duplicate_seq_within_category": len(dup_seq),
        "blocks_configured": config.DOC_ID_BLOCK,
        "out_of_block_samples": out_of_block[:5],
        "duplicate_doc_id_samples": brief(dup_doc_ids),
    }
    pass_11 = not out_of_block and not dup_doc_ids and not dup_seq
    rep.add(11, "doc_id_block_matches",
            "《12》§五 硬约束 7；config.DOC_ID_BLOCK / doc_id_for（编号显式分配、稳定、不依赖自增）",
            pass_11, measured_11,
            "每篇文档的 doc_id 必须落在其 category 对应的块内（块号 < doc_id <= 块号+%d），块内序号唯一"
            % (config.DOC_ID_STRIDE - 1))

    # ---- 检查 12（附加）：文本块正文非空、token_count 为正整数 ----
    empty_content, bad_tok = [], []
    for c in chunks:
        if not str(c.get("content") or "").strip():
            empty_content.append(c.get("chunk_id"))
        tc = c.get("token_count")
        if not (isinstance(tc, int) and not isinstance(tc, bool) and tc > 0):
            bad_tok.append({"chunk_id": c.get("chunk_id"), "token_count": tc})
    tok_vals = [c.get("token_count") for c in chunks
                if isinstance(c.get("token_count"), int) and not isinstance(c.get("token_count"), bool)]
    measured_12 = {
        "chunks": n_chunks,
        "empty_content_chunks": len(empty_content),
        "invalid_token_count_chunks": len(bad_tok),
        "token_count_min": min(tok_vals) if tok_vals else None,
        "token_count_max": max(tok_vals) if tok_vals else None,
        "token_count_sum": sum(tok_vals),
        "token_count_avg": round(sum(tok_vals) / len(tok_vals), 2) if tok_vals else 0,
        "empty_content_samples": brief(empty_content),
        "invalid_token_count_samples": bad_tok[:5],
    }
    pass_12 = not empty_content and not bad_tok
    rep.add(12, "chunk_content_and_token_count",
            "《12》§九 T5（chunks 含 token_count）；README §3.4（token_count 由 Embedding tokenizer 统计）",
            pass_12, measured_12,
            "每个文本块 content 非空、token_count 为正整数（附加检查，非 §八 明列项）")

    # ---- 检查 13（附加）：时间覆盖——两个相对时间桶都非空且各 >= MIN_DOCS_PER_TIME_BUCKET，
    #      且 cutoff − publish_time_min >= 90 天；另**报告**（不判定）90 天区间与 earlier 桶两半
    r0, r1 = parse_date(config.BUCKET_RECENT[0]), parse_date(config.BUCKET_RECENT[1])
    e0, e1 = parse_date(config.BUCKET_EARLIER[0]), parse_date(config.BUCKET_EARLIER[1])
    a0, a1 = parse_date(config.ANALYSIS_90_RANGE[0]), parse_date(config.ANALYSIS_90_RANGE[1])
    recent_docs = [d for d in docs if (dt := parse_date(d.get("publish_time"))) and r0 <= dt <= r1]
    earlier_docs = [d for d in docs if (dt := parse_date(d.get("publish_time"))) and e0 <= dt <= e1]
    analysis_docs = [d for d in docs if (dt := parse_date(d.get("publish_time"))) and a0 <= dt <= a1]
    span_days = (max(date_list) - min(date_list)).days if date_list else 0
    cutoff_span_days = (cutoff - min(date_list)).days if date_list else 0
    # 门槛天数由 config 推出（ANALYSIS_90_RANGE 左端 = cutoff − 90d），脚本内不写死 90。
    # 采集窗下界取 cutoff − 100 天（config.WINDOW_DAYS），让完整的 [cutoff−90d, cutoff] 落在
    # 数据集内部；因此覆盖判定用 90 天门槛，而不是 100 天的窗口长度。
    coverage_required_days = (cutoff - a0).days
    # earlier 桶两半（各约一半天数、首尾相接），只为把"窗口正中间整月没有文档"报出来：
    # 该桶 [2026-06-17, 2026-08-26] 共 71 天 -> 前半 [06-17, 07-21]、后半 [07-22, 08-26]。
    half_len = ((e1 - e0).days + 1) // 2
    half_cut = e0 + timedelta(days=half_len - 1)
    earlier_first_half = [d for d in earlier_docs
                          if (dt := parse_date(d.get("publish_time"))) and dt <= half_cut]
    earlier_second_half = [d for d in earlier_docs
                           if (dt := parse_date(d.get("publish_time"))) and dt > half_cut]
    measured_13 = {
        "documents": n_docs,
        "bucket_recent": "%s ~ %s" % config.BUCKET_RECENT,
        "bucket_earlier": "%s ~ %s" % config.BUCKET_EARLIER,
        "bucket_recent_count": len(recent_docs),
        "bucket_earlier_count": len(earlier_docs),
        "min_docs_per_time_bucket": config.MIN_DOCS_PER_TIME_BUCKET,
        "span_days_between_min_and_max": span_days,
        "cutoff_minus_earliest_days": cutoff_span_days,
        "coverage_required_days": coverage_required_days,
        "window_days": config.WINDOW_DAYS,
        "analysis_90_range": "%s ~ %s" % config.ANALYSIS_90_RANGE,
        "analysis_90_count": len(analysis_docs),
        "earlier_first_half": "%s ~ %s" % (config.BUCKET_EARLIER[0], half_cut.isoformat()),
        "earlier_first_half_count": len(earlier_first_half),
        "earlier_second_half": "%s ~ %s" % ((half_cut + timedelta(days=1)).isoformat(),
                                             config.BUCKET_EARLIER[1]),
        "earlier_second_half_count": len(earlier_second_half),
        "documents_outside_both_buckets": n_docs - len(recent_docs) - len(earlier_docs),
    }
    pass_13 = (len(recent_docs) >= config.MIN_DOCS_PER_TIME_BUCKET
               and len(earlier_docs) >= config.MIN_DOCS_PER_TIME_BUCKET
               and cutoff_span_days >= coverage_required_days)
    rep.add(13, "time_coverage",
            "《12》§五 硬约束 13、§八（≥90 天，且两个相对时间区间内内容非空）；《12》v1.2 报告要求",
            pass_13, measured_13,
            "两个时间桶都必须非空且各至少 %d 篇；最早 publish_time 距 data_cutoff 至少 %d 天"
            % (config.MIN_DOCS_PER_TIME_BUCKET, coverage_required_days))

    # ---- 检查 14（附加）：覆盖的公司集合恰好等于 config 选定的公司 ----
    configured = config.profile_settings(args.profile)["companies"]
    cfg_codes = [c["code"] for c in configured]
    covered = set()
    for d in docs:
        cl = d.get("company_list")
        if isinstance(cl, list):
            covered.update(str(x) for x in cl)
    missing_codes = sorted(set(cfg_codes) - covered)
    extra_codes = sorted(covered - set(cfg_codes))
    measured_14 = {
        "profile": args.profile,
        "configured_company_count": len(cfg_codes),
        "covered_company_count": len(covered),
        "covered_codes": sorted(covered),
        "configured_codes": sorted(cfg_codes),
        "missing_codes": missing_codes,
        "extra_codes": extra_codes,
        "equals_configured_set": (not missing_codes and not extra_codes),
    }
    pass_14 = not missing_codes and not extra_codes
    rep.add(14, "company_set_equals_configured",
            "《12》§八（数据集覆盖的公司集合恰好等于 T2 选定的 10 家）、config.COMPANIES",
            pass_14, measured_14,
            "全部文档 company_list 的并集必须恰好等于 profile=%s 选定的 %d 家公司代码"
            % (args.profile, len(cfg_codes)))

    # ---------------------------------------------------------------------
    # 报告落盘
    # ---------------------------------------------------------------------
    os.makedirs(reports_dir, exist_ok=True)

    summary = {
        "checks_total": len(rep.checks),
        "checks_passed": len(rep.checks) - len(rep.failed),
        "checks_failed": len(rep.failed),
        "pass": rep.ok,
        "failed_checks": [{"id": c["id"], "name": c["name"]} for c in rep.failed],
    }
    report = {
        "report": "consistency_report",
        "generated_at": now_iso(),
        "profile": args.profile,
        "root": root,
        "dataset_version": config.DATASET_VERSION,
        "pipeline_version": config.PIPELINE_VERSION,
        "data_cutoff_date": config.DATA_CUTOFF_DATE,
        "counts": {
            "documents": n_docs,
            "chunks": n_chunks,
            "vectors_index_ntotal": idx_ntotal,
            "vector_map_rows": len(vmap),
            "category_counts": category_counts,
            "source_counts": source_counts,
        },
        "checks": rep.checks,
        "summary": summary,
        "informational": {
            "index_build_meta_present": bool(meta),
            "build_meta": {k: meta.get(k) for k in
                           ("model_name", "model_revision", "resolved_snapshot", "dim",
                            "vector_count", "index_type", "metric", "normalize_embeddings",
                            "build_time")} if meta else None,
            "index_dir": index_dir,
            "note": "本报告只核验条数与编号一致性，不含任何检索或效果评估（《12》§七 非目标 7）",
        },
    }
    write_json_atomic(os.path.join(reports_dir, "consistency_report.json"), report)

    # ---- time_coverage.json（check #13 的实测数值 + 《12》v1.2 要求的补充报告项）----
    # 逐月直方图覆盖最早与最晚文档之间的**每一个自然月**：窗口内部整月为空时必须显式为 0，
    # 否则"区间统计量全都正常、中间却缺一个月"这种问题在读报告时看不出来。
    month_hist = month_range_histogram(date_list)
    time_cov = {
        "report": "time_coverage",
        "generated_at": report["generated_at"],
        "profile": args.profile,
        "root": root,
        "documents": n_docs,
        "publish_time_min": min(date_list).isoformat() if date_list else None,
        "publish_time_max": max(date_list).isoformat() if date_list else None,
        "span_days": span_days,
        "data_cutoff_date": config.DATA_CUTOFF_DATE,
        "window_start": config.WINDOW_START,
        "window_end": config.WINDOW_END,
        "window_days": config.WINDOW_DAYS,
        "cutoff_minus_earliest_days": cutoff_span_days,
        "coverage_required_days": coverage_required_days,
        "months_covered": len(month_hist),
        "per_month_histogram": month_hist,
        "months_with_zero_documents": [m for m, c in month_hist.items() if c == 0],
        "analysis_90_range": {
            "range": list(config.ANALYSIS_90_RANGE),
            "doc_count": len(analysis_docs),
            "doc_ids": sorted(d.get("doc_id") for d in analysis_docs),
            "gate": False,
            "note": "报告项（不参与 check #13 的通过判定）：[cutoff−90d, cutoff] 内的文档数",
        },
        "buckets": {
            "recent": {
                "range": list(config.BUCKET_RECENT),
                "count": len(recent_docs),
                "min_docs_required": config.MIN_DOCS_PER_TIME_BUCKET,
                "pass": len(recent_docs) >= config.MIN_DOCS_PER_TIME_BUCKET,
                "doc_ids": sorted(d.get("doc_id") for d in recent_docs),
            },
            "earlier": {
                "range": list(config.BUCKET_EARLIER),
                "count": len(earlier_docs),
                "min_docs_required": config.MIN_DOCS_PER_TIME_BUCKET,
                "pass": len(earlier_docs) >= config.MIN_DOCS_PER_TIME_BUCKET,
                "doc_ids": sorted(d.get("doc_id") for d in earlier_docs),
            },
        },
        "earlier_halves": {
            "first": {
                "range": [config.BUCKET_EARLIER[0], half_cut.isoformat()],
                "count": len(earlier_first_half),
                "doc_ids": sorted(d.get("doc_id") for d in earlier_first_half),
            },
            "second": {
                "range": [(half_cut + timedelta(days=1)).isoformat(), config.BUCKET_EARLIER[1]],
                "count": len(earlier_second_half),
                "doc_ids": sorted(d.get("doc_id") for d in earlier_second_half),
            },
            "gate": False,
            "note": ("报告项（不参与判定）：把 earlier 桶按天数平均分成两半分别报数，"
                     "窗口正中间整月没有文档时，两半的对比会直接显形"),
        },
        "documents_outside_both_buckets": n_docs - len(recent_docs) - len(earlier_docs),
        "span_covers_required_window": cutoff_span_days >= coverage_required_days,
        "pass": pass_13,
        "criteria": ("两个时间桶都非空且各 >= %d 篇；且最早 publish_time 距 data_cutoff >= %d 天"
                     % (config.MIN_DOCS_PER_TIME_BUCKET, coverage_required_days)),
        "note": ("时间桶口径来自 config.BUCKET_RECENT / config.BUCKET_EARLIER；"
                 "采集窗口下界为 config.WINDOW_START（cutoff − %d 天），覆盖门槛为 %d 天；"
                 "不得用'至今''实时'一类表述（《12》§五 硬约束 4）"
                 % (config.WINDOW_DAYS, coverage_required_days)),
    }
    write_json_atomic(os.path.join(reports_dir, "time_coverage.json"), time_cov)

    md = []
    md.append("# 数据一致性检查报告（T8）")
    md.append("")
    md.append("- 生成时间：%s" % report["generated_at"])
    md.append("- profile：`%s`　数据集根目录：`%s`" % (args.profile, root))
    md.append("- dataset_version：`%s`　data_cutoff_date：`%s`"
              % (config.DATASET_VERSION, config.DATA_CUTOFF_DATE))
    md.append("- 规模：文档 %d 篇／文本块 %d 个／向量索引 ntotal %s／映射 %d 行"
              % (n_docs, n_chunks, idx_ntotal, len(vmap)))
    md.append("- 元信息（随本报告一并重建）：`meta\\dataset.json`——dataset_version、"
              "data_cutoff_time、规模、时间范围、Embedding 模型与版本、切分参数、生成时间"
              "（《12》§八 第 3 行）")
    md.append("- 结论：**%s**（%d/%d 项检查通过）"
              % ("全部通过" if rep.ok else "存在不通过项",
                 summary["checks_passed"], summary["checks_total"]))
    md.append("")
    md.append("| # | 检查项 | 依据 | 实测 | 结果 |")
    md.append("| --- | --- | --- | --- | --- |")
    for c in rep.checks:
        md.append("| %d | `%s` | %s | %s | %s |"
                  % (c["id"], c["name"], c["basis"], render_measured(c["measured"]),
                     "通过" if c["pass"] else "**不通过**"))
    md.append("")
    if rep.ok:
        md.append("未发现不一致：上述各项的实测数值均满足《12》§五 硬约束与 §八 验收标准。")
    else:
        md.append("## 不通过的检查项")
        md.append("")
        for c in rep.failed:
            md.append("- **#%d `%s`**：%s" % (c["id"], c["name"], c["detail"]))
            md.append("  - 实测：%s" % render_measured(c["measured"]))
    md.append("")
    md.append("## 时间覆盖明细（`reports\\time_coverage.json`）")
    md.append("")
    md.append("| 项 | 数值 |")
    md.append("| --- | --- |")
    md.append("| 采集窗口（config.WINDOW_START ~ WINDOW_END） | `%s` ~ `%s`（%d 天） |"
              % (time_cov["window_start"], time_cov["window_end"], config.WINDOW_DAYS))
    md.append("| publish_time 实测范围 | `%s` ~ `%s`（跨度 %d 天） |"
              % (time_cov["publish_time_min"], time_cov["publish_time_max"],
                 time_cov["span_days"]))
    md.append("| cutoff − publish_time_min | **%d 天**（门槛 %d 天） |"
              % (time_cov["cutoff_minus_earliest_days"], time_cov["coverage_required_days"]))
    md.append("| 时间桶 recent（%s ~ %s） | %d 篇（需 >= %d 篇） |"
              % (config.BUCKET_RECENT[0], config.BUCKET_RECENT[1],
                 time_cov["buckets"]["recent"]["count"], config.MIN_DOCS_PER_TIME_BUCKET))
    md.append("| 时间桶 earlier（%s ~ %s） | %d 篇（需 >= %d 篇） |"
              % (config.BUCKET_EARLIER[0], config.BUCKET_EARLIER[1],
                 time_cov["buckets"]["earlier"]["count"], config.MIN_DOCS_PER_TIME_BUCKET))
    md.append("| `ANALYSIS_90_RANGE`（%s ~ %s）文档数 | **%d 篇**（报告项，不参与判定） |"
              % (config.ANALYSIS_90_RANGE[0], config.ANALYSIS_90_RANGE[1],
                 time_cov["analysis_90_range"]["doc_count"]))
    md.append("| earlier 桶前半（%s ~ %s） | %d 篇 |"
              % (time_cov["earlier_halves"]["first"]["range"][0],
                 time_cov["earlier_halves"]["first"]["range"][1],
                 time_cov["earlier_halves"]["first"]["count"]))
    md.append("| earlier 桶后半（%s ~ %s） | %d 篇 |"
              % (time_cov["earlier_halves"]["second"]["range"][0],
                 time_cov["earlier_halves"]["second"]["range"][1],
                 time_cov["earlier_halves"]["second"]["count"]))
    md.append("| 逐月文档数（含无文档月份，缺失月显式为 0） | %s |"
              % "；".join("%s=%d" % (m, c) for m, c in time_cov["per_month_histogram"].items()))
    md.append("")
    md.append("earlier 桶两半与 `ANALYSIS_90_RANGE` 均为**报告项**：它们不参与 check #13 的"
              "通过判定，只用于把\"窗口正中间整月没有文档\"这类问题直接显示出来"
              "（这一轮实测出现过 7 月整月为空）。")
    md.append("")
    md.append("> 本报告只核验条数与编号一致性，不做检索、排序与任何指标评估（《12》§七 非目标 7）。")
    md.append("> FAISS 在本项目中称“向量索引／向量检索组件”。")
    md.append("")
    write_text_atomic(os.path.join(reports_dir, "consistency_report.md"), "\n".join(md))

    # ---- company_coverage.json ----
    per_company = []
    for comp in configured:
        code = comp["code"]
        ann = sum(1 for d in docs if d.get("category") == "公告"
                  and isinstance(d.get("company_list"), list) and code in d["company_list"])
        news = sum(1 for d in docs if d.get("category") == "财经新闻"
                   and isinstance(d.get("company_list"), list) and code in d["company_list"])
        other = sum(1 for d in docs if d.get("category") not in config.CATEGORIES_REQUIRING_COMPANY
                    and isinstance(d.get("company_list"), list) and code in d["company_list"])
        per_company.append({
            "code": code, "name": comp["name"], "industry": comp["industry"],
            "board": comp.get("board"),
            "announcement_count": ann, "news_count": news, "total": ann + news,
            "other_category_count": other, "documents_total": ann + news + other,
        })
    company_cov = {
        "report": "company_coverage",
        "generated_at": report["generated_at"],
        "profile": args.profile,
        "root": root,
        "configured_company_count": len(cfg_codes),
        "covered_company_count": len(covered),
        "equals_configured_set": not missing_codes and not extra_codes,
        "missing_codes": missing_codes,
        "extra_codes": extra_codes,
        "covered_codes": sorted(covered),
        "companies": per_company,
        "totals": {
            "documents": n_docs,
            "announcement_documents": category_counts.get("公告", 0),
            "news_documents": category_counts.get("财经新闻", 0),
            "policy_documents": category_counts.get("政策文件", 0),
            "regulator_documents": category_counts.get("监管公开信息", 0),
            "documents_with_non_empty_company_list": sum(
                1 for d in docs if isinstance(d.get("company_list"), list) and d["company_list"]),
            "documents_with_empty_company_list": sum(
                1 for d in docs if isinstance(d.get("company_list"), list) and not d["company_list"]),
        },
        "pass": pass_14,
        "note": ("公司集合口径为全部文档 company_list 的并集；"
                 "公告与财经新闻必须非空，政策文件与监管公开信息允许空数组（《12》§八）"),
    }
    write_json_atomic(os.path.join(reports_dir, "company_coverage.json"), company_cov)

    # ---- meta\dataset.json（《12》§八 第 3 行：数据集版本级元信息）----
    # 与 reports\ 同级、写在**本脚本检查的同一个根目录**下；数值全部来自实测数据与 config。
    meta_dir = os.path.join(root, "meta")
    os.makedirs(meta_dir, exist_ok=True)
    dataset_meta_path = os.path.join(meta_dir, "dataset.json")
    dataset_meta = build_dataset_meta(
        profile=args.profile, root=root, docs=docs, chunks=chunks, index_meta=meta,
        covered_codes=covered, configured_codes=cfg_codes, date_list=date_list,
        month_hist=month_hist, recent_docs=recent_docs, earlier_docs=earlier_docs,
        analysis_docs=analysis_docs, summary=summary, generated_at=report["generated_at"])
    write_json_atomic(dataset_meta_path, dataset_meta)

    # ---------------------------------------------------------------------
    # 控制台摘要
    # ---------------------------------------------------------------------
    print("[check] 文档=%d  文本块=%d  向量索引条数=%s  映射=%d" % (n_docs, n_chunks, idx_ntotal, len(vmap)))
    print("[check] 分类计数：%s" % category_counts)
    print("[check] 时间覆盖：桶 recent=%d 篇 / 桶 earlier=%d 篇（下限 %d）"
          % (len(recent_docs), len(earlier_docs), config.MIN_DOCS_PER_TIME_BUCKET))
    print("[check] 时间覆盖明细：cutoff − publish_time_min=%d 天（门槛 %d）；"
          "ANALYSIS_90_RANGE %s~%s=%d 篇；earlier 两半=%d/%d 篇；逐月=%s"
          % (cutoff_span_days, coverage_required_days,
             config.ANALYSIS_90_RANGE[0], config.ANALYSIS_90_RANGE[1], len(analysis_docs),
             len(earlier_first_half), len(earlier_second_half),
             "、".join("%s:%d" % (m, c) for m, c in month_hist.items())))
    print("[check] 公司覆盖：%d/%d 家，缺失 %s，多出 %s"
          % (len(covered), len(cfg_codes), missing_codes or "无", extra_codes or "无"))
    for c in rep.checks:
        flag = "通过" if c["pass"] else "不通过"
        print("[check] %2d. %-38s %s" % (c["id"], c["name"], flag))
    print("[check] 报告已写入：%s" % reports_dir)
    print("[check] 元信息已写入：%s（公司 %d 家／文档 %d 篇／文本块 %d 个；dataset_version=%s）"
          % (dataset_meta_path, dataset_meta["scale"]["company_count"], n_docs, n_chunks,
             dataset_meta["dataset_version"]))
    if rep.ok:
        print("[check] 全部通过  %d/%d  耗时=%.2fs"
              % (summary["checks_passed"], summary["checks_total"], time.time() - t_all))
        return 0
    print("[check] 存在不通过项  %d/%d  失败检查：%s  耗时=%.2fs"
          % (summary["checks_failed"], summary["checks_total"],
             ", ".join("#%d %s" % (c["id"], c["name"]) for c in rep.failed), time.time() - t_all))
    return 1


if __name__ == "__main__":
    sys.exit(main())
