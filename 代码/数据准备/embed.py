# -*- coding: utf-8 -*-
"""T6 向量化与映射落盘（第 5 阶段数据准备）。

输入：<root>\\chunks\\chunks.jsonl
输出：<root>\\index\\faiss.index        —— FAISS 向量索引（IndexFlatIP，向量已 L2 归一化）
      <root>\\index\\vector_map.jsonl   —— 一行一条 {"vector_id","chunk_id","doc_id"}
      <root>\\index\\build_meta.json    —— 模型名与 revision、维度、条数、索引类型、度量、归一化标志、构建时间
      <root>\\chunks\\chunks.jsonl      —— 原地回填 vector_id（原子替换：先写 .tmp 再 replace）

口径（《12》第2.3节、第5节 硬约束 6/9/10/11；《代码\\数据准备\\README.md》第3.4节、第3.5节）：
  * Embedding 模型由 config.EMBEDDING 固化，本脚本不写死任何模型名／路径／批大小；
  * vector_id 等于**向量索引中的行号**，行号按 chunk_id 升序分配，因此 vector_id→chunk_id
    与 chunk_id→vector_id 双向可查（三级映射链路：vector_id → chunk_id → doc_id）；
  * 向量条数必须等于文本块条数，且不允许存在 vector_id 为空的文本块；
  * 术语纪律：FAISS 一律称"向量索引"或"向量检索组件"（《12》第五节 硬约束 11），
    不用任何其它称呼；本文件全文遵守该口径。

本脚本只做编码与落盘，**不做任何检索、排序、相似度查询或指标评估**（《12》第七节 非目标 7）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

# 控制台为 GBK，必须重设编码后再输出中文。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # 极少见的非文本流 stdout，重设失败不致命
    pass

# config.py 与本脚本同目录，显式加入 sys.path，保证任意工作目录下都能导入。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402  唯一参数来源，不得绕过

# 模型已在本机 HuggingFace 缓存中离线可用，禁止联网下载（《12》第五节 硬约束 10）。
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

CST = timezone(timedelta(hours=8))


def resolve_cache_snapshot(repo_id: str) -> str:
    """离线读取 HuggingFace 缓存中 refs/main 指向的快照哈希。

    用途：核对"实际会被加载的快照"是否就是 config.EMBEDDING['revision'] 固化的那一个。
    模型名固定、缓存离线，因此 refs/main 就是 SentenceTransformer(name) 会解析到的快照。
    读不到时返回空串，不影响流程（只影响元信息里的一个说明字段）。
    """
    try:
        from huggingface_hub.constants import HF_HUB_CACHE

        ref = os.path.join(HF_HUB_CACHE, "models--" + repo_id.replace("/", "--"), "refs", "main")
        with open(ref, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""


def pinned_revision_is_cached(repo_id: str, revision: str) -> str:
    """检查 config 固化的 revision 是否在本机缓存中：返回 'yes' / 'no' / 'unknown'。"""
    try:
        from huggingface_hub import try_to_load_from_cache

        p = try_to_load_from_cache(repo_id, "config.json", revision=revision)
        return "yes" if isinstance(p, str) else ("no" if p is not None else "unknown")
    except Exception:
        return "unknown"


# --------------------------------------------------------------------------
# 通用小工具（本阶段限定只产出三个脚本，故不引入公共模块）
# --------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(CST).isoformat(timespec="seconds")


def read_jsonl(path: str):
    """逐行读 JSONL，返回 (行列表, 行号列表)。空行跳过，解析失败立即报错。"""
    rows, lines = [], []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError("%s 第 %d 行不是合法 JSON：%s" % (path, lineno, exc)) from exc
            lines.append(lineno)
    return rows, lines


def write_jsonl_atomic(path: str, rows) -> None:
    """原子写 JSONL：先写同目录 .tmp，再 os.replace 覆盖（UTF-8、无 BOM、LF 换行）。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_json_atomic(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_faiss_index(index, path: str) -> None:
    """把 FAISS 向量索引写盘。

    不用 faiss.write_index/read_index：它们走 C++ 的 fopen，在含中文的路径（本项目数据集
    路径就含中文）下会因 ANSI 代码页而报 "could not open ... for writing"。改用
    faiss.serialize_index 取出字节流、由 Python 自己写文件——序列化格式与 write_index
    完全一致（已实测逐字节相同），因此产出的仍是标准 FAISS 索引文件，
    faiss.read_index 在 ASCII 路径下可直接读取。
    """
    import faiss

    buf = faiss.serialize_index(index)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(buf.tobytes())
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def read_faiss_index(path: str):
    """按上述同一格式读回 FAISS 向量索引（同样绕开 CJK 路径问题）。"""
    import faiss
    import numpy as np

    with open(path, "rb") as f:
        raw = f.read()
    arr = np.frombuffer(bytearray(raw), dtype=np.uint8)
    return faiss.deserialize_index(arr)


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="T6 向量化：文本块 -> 向量索引 + 三级映射（第 5 阶段数据准备）"
    )
    p.add_argument("--profile", choices=["v1", "pilot"], default="v1",
                   help="v1（默认）写入正式数据集目录；pilot 写入 _试跑\\")
    p.add_argument("--dir", default=None,
                   help="仅供自测：覆盖输出根目录（正式封版不得使用）")
    p.add_argument("--force", action="store_true",
                   help="忽略已完成标记，强制重建向量索引")
    return p.parse_args(argv)


def resolve_root(args) -> str:
    return os.path.abspath(args.dir) if args.dir else config.dataset_dir(args.profile)


# --------------------------------------------------------------------------
# 幂等：判断本环节是否已完成
# --------------------------------------------------------------------------
def already_built(root: str, chunks) -> tuple:
    """已完成的条件（全部满足才跳过）：

    1. index\\faiss.index、index\\vector_map.jsonl、index\\build_meta.json 三个文件都在；
    2. build_meta 记录的模型名与 config 一致、vector_count == 文本块数；
    3. 每个文本块都有非空 vector_id；
    4. vector_map 里的 chunk_id 集合与 chunks.jsonl 的完全一致（防止 chunk.py 重跑后条数相同
       但内容已变——那种情况下必须重建）。
    """
    idx_p = os.path.join(root, "index", config.FAISS["index_file"])
    map_p = os.path.join(root, "index", config.FAISS["map_file"])
    meta_p = os.path.join(root, "index", config.FAISS["meta_file"])
    for p in (idx_p, map_p, meta_p):
        if not os.path.isfile(p):
            return False, "缺少 %s" % os.path.basename(p)
    try:
        meta = read_json(meta_p)
    except Exception as exc:  # 损坏即视为未完成
        return False, "build_meta.json 不可读：%s" % exc
    if meta.get("model_name") != config.EMBEDDING["model_name"]:
        return False, "已建索引的模型 %r 与 config 的 %r 不一致" % (
            meta.get("model_name"), config.EMBEDDING["model_name"])
    if meta.get("vector_count") != len(chunks):
        return False, "已建索引条数 %r != 文本块数 %d" % (meta.get("vector_count"), len(chunks))
    if any(c.get("vector_id") is None for c in chunks):
        return False, "仍有文本块的 vector_id 为空"
    try:
        mapped, _ = read_jsonl(map_p)
    except Exception as exc:
        return False, "vector_map.jsonl 不可读：%s" % exc
    if sorted(r.get("chunk_id") for r in mapped) != sorted(c["chunk_id"] for c in chunks):
        return False, "vector_map 的 chunk_id 集合与 chunks.jsonl 不一致"
    return True, "已完成"


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    args = parse_args(argv)
    t_all = time.time()
    root = resolve_root(args)
    chunks_p = os.path.join(root, "chunks", "chunks.jsonl")
    index_dir = os.path.join(root, "index")
    idx_p = os.path.join(index_dir, config.FAISS["index_file"])
    map_p = os.path.join(index_dir, config.FAISS["map_file"])
    meta_p = os.path.join(index_dir, config.FAISS["meta_file"])

    print("[embed] profile=%s  root=%s" % (args.profile, root))
    if args.dir:
        print("[embed] 注意：--dir 仅供自测，不产出正式交付物")

    if not os.path.isfile(chunks_p):
        print("[embed] 失败：找不到输入 %s（请先运行 chunk.py）" % chunks_p)
        return 2

    chunks, _ = read_jsonl(chunks_p)
    n_chunks = len(chunks)
    if n_chunks == 0:
        print("[embed] 失败：%s 为空，无可向量化的文本块" % chunks_p)
        return 2

    # 输入自检：chunk_id 唯一、content 非空。
    ids = [c.get("chunk_id") for c in chunks]
    if any(i is None for i in ids):
        print("[embed] 失败：存在 chunk_id 为空的文本块")
        return 2
    dup = sorted(k for k, n in Counter(ids).items() if n > 1)
    if dup:
        print("[embed] 失败：chunk_id 重复 %d 个，样例 %s" % (len(dup), dup[:5]))
        return 2
    blank = [c.get("chunk_id") for c in chunks if not str(c.get("content") or "").strip()]
    if blank:
        print("[embed] 失败：%d 个文本块 content 为空，样例 %s" % (len(blank), blank[:5]))
        return 2

    if not args.force:
        done, why = already_built(root, chunks)
        if done:
            print("[embed] 跳过：%s（加 --force 可强制重建）" % why)
            print("[embed] 完成（跳过）  文本块=%d  耗时=%.2fs" % (n_chunks, time.time() - t_all))
            return 0

    os.makedirs(index_dir, exist_ok=True)

    # --- 1) 载入 Embedding 模型（离线；模型与 revision 由 config 固化） ---
    import numpy as np  # 局部导入，便于 --help 时不加载重依赖

    t0 = time.time()
    from sentence_transformers import SentenceTransformer

    print("[embed] 载入 Embedding 模型 %s（device=%s，离线）..."
          % (config.EMBEDDING["model_name"], config.EMBEDDING["device"]))
    model = SentenceTransformer(
        config.EMBEDDING["model_name"],
        device=config.EMBEDDING["device"],
    )
    model.max_seq_length = config.EMBEDDING["max_seq_length"]
    load_seconds = time.time() - t0
    # 新版本 sentence-transformers 把 get_sentence_embedding_dimension 改名为
    # get_embedding_dimension（旧名会触发 FutureWarning），优先用新名。
    dim_getter = getattr(model, "get_embedding_dimension", None) or \
        model.get_sentence_embedding_dimension
    dim = int(dim_getter())
    if dim != config.EMBEDDING["dim"]:
        print("[embed] 失败：加载出的模型维度 %d != config.EMBEDDING['dim']=%d"
              % (dim, config.EMBEDDING["dim"]))
        return 3
    print("[embed] 模型就绪  维度=%d  载入耗时=%.2fs" % (dim, load_seconds))

    # 核对"实际加载的快照"是否就是 config 固化的 revision（《12》第五节 硬约束 10）
    resolved = resolve_cache_snapshot(config.EMBEDDING["model_name"])
    pinned_cached = pinned_revision_is_cached(
        config.EMBEDDING["model_name"], config.EMBEDDING["revision"])

    # --- 2) 按 chunk_id 升序编码：vector_id == 向量索引中的行号 ---
    ordered = sorted(chunks, key=lambda c: c["chunk_id"])
    texts = [c["content"] for c in ordered]

    t0 = time.time()
    print("[embed] 编码 %d 个文本块（batch_size=%d，normalize=%s）..."
          % (n_chunks, config.EMBEDDING["batch_size"], config.EMBEDDING["normalize"]))
    emb = model.encode(
        texts,
        batch_size=config.EMBEDDING["batch_size"],
        normalize_embeddings=bool(config.EMBEDDING["normalize"]),
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    encode_seconds = time.time() - t0
    emb = np.ascontiguousarray(np.asarray(emb, dtype="float32"))
    if emb.shape != (n_chunks, dim):
        print("[embed] 失败：编码结果形状 %s != (%d, %d)" % (emb.shape, n_chunks, dim))
        return 3

    # --- 3) 建 FAISS 向量索引（IndexFlatIP；归一化后内积＝余弦相似度） ---
    import faiss

    index_type = config.FAISS["index_type"]
    if index_type != "IndexFlatIP":
        print("[embed] 失败：本脚本只按 config.FAISS['index_type']=IndexFlatIP 建索引，"
              "当前为 %r" % index_type)
        return 3
    index = faiss.IndexFlatIP(dim)
    index.add(emb)
    if index.metric_type != faiss.METRIC_INNER_PRODUCT:
        print("[embed] 失败：索引度量类型 %d != METRIC_INNER_PRODUCT(%d)"
              % (index.metric_type, faiss.METRIC_INNER_PRODUCT))
        return 3
    if index.ntotal != n_chunks:
        print("[embed] 失败：索引条数 %d != 文本块数 %d" % (index.ntotal, n_chunks))
        return 3
    print("[embed] 向量索引 %s 已建立  条数=%d  维度=%d  度量=%s"
          % (index_type, index.ntotal, index.d, config.FAISS["metric"]))

    # --- 4) 落盘：向量索引 / 映射 / 元信息 ---
    write_faiss_index(index, idx_p)
    vector_map = [
        {"vector_id": vid, "chunk_id": c["chunk_id"], "doc_id": c["doc_id"]}
        for vid, c in enumerate(ordered)
    ]
    write_jsonl_atomic(map_p, vector_map)

    doc_ids = {c["doc_id"] for c in ordered}
    meta = {
        "dataset_version": config.DATASET_VERSION,
        "pipeline_version": config.PIPELINE_VERSION,
        "profile": args.profile,
        "model_name": config.EMBEDDING["model_name"],
        "model_revision": config.EMBEDDING["revision"],
        "resolved_snapshot": resolved,
        "revision_matches_config": (resolved == config.EMBEDDING["revision"]) if resolved else None,
        "pinned_revision_in_cache": pinned_cached,
        "dim": dim,
        "vector_count": int(index.ntotal),
        "chunk_count": n_chunks,
        "doc_count": len(doc_ids),
        "index_type": index_type,
        "metric": config.FAISS["metric"],
        "similarity": config.EMBEDDING["similarity"],
        "normalize_embeddings": bool(config.EMBEDDING["normalize"]),
        "pooling": config.EMBEDDING["pooling"],
        "query_instruction": config.EMBEDDING["query_instruction"],
        "max_seq_length": config.EMBEDDING["max_seq_length"],
        "device": config.EMBEDDING["device"],
        "batch_size": config.EMBEDDING["batch_size"],
        "index_file": config.FAISS["index_file"],
        "map_file": config.FAISS["map_file"],
        "id_order": "chunk_id 升序 -> vector_id = 向量索引行号",
        "build_time": now_iso(),
        "build_seconds": round(encode_seconds + load_seconds, 3),
        "model_load_seconds": round(load_seconds, 3),
        "encode_seconds": round(encode_seconds, 3),
        "faiss_version": getattr(faiss, "__version__", "unknown"),
        "numpy_version": np.__version__,
    }
    write_json_atomic(meta_p, meta)

    print("[embed] 模型版本核对：缓存 refs/main=%s  config.EMBEDDING['revision']=%s  一致=%s"
          % (resolved or "(读不到)", config.EMBEDDING["revision"],
             (resolved == config.EMBEDDING["revision"]) if resolved else "未知"))
    if resolved and resolved != config.EMBEDDING["revision"]:
        print("[embed] 警告：实际加载的模型快照 %r 与 config.EMBEDDING['revision']=%r 不一致，"
              "已如实记入 build_meta.json（未改 config；按《12》第五节 硬约束 10 报告，不静默）"
              % (resolved, config.EMBEDDING["revision"]))
    if pinned_cached == "no":
        print("[embed] 警告：config 固化的 revision %s 不在本机缓存中，实际加载的可能不是该版本"
              % config.EMBEDDING["revision"])

    # --- 5) 回填 vector_id（先写 .tmp 再原子替换，保持原行序） ---
    vid_of = {c["chunk_id"]: vid for vid, c in enumerate(ordered)}
    for c in chunks:
        c["vector_id"] = vid_of[c["chunk_id"]]
    write_jsonl_atomic(chunks_p, chunks)

    # --- 6) 落盘后读回校验（不做任何检索） ---
    back = read_faiss_index(idx_p)
    if back.ntotal != n_chunks or back.d != dim:
        print("[embed] 失败：读回向量索引 ntotal=%d d=%d，期望 %d/%d"
              % (back.ntotal, back.d, n_chunks, dim))
        return 3
    probe_rows = sorted({0, n_chunks // 2, n_chunks - 1})
    recon = back.reconstruct_n(0, min(n_chunks, max(probe_rows) + 1))
    for r in probe_rows:
        if not np.allclose(recon[r], emb[r], atol=1e-6):
            print("[embed] 失败：读回的向量第 %d 行与编码结果不一致" % r)
            return 3

    chunks_after, _ = read_jsonl(chunks_p)
    mapped_after, _ = read_jsonl(map_p)

    # --- 7) 收尾断言（《12》第五节 硬约束 9） ---
    problems = []
    if back.ntotal != len(chunks_after):
        problems.append("向量条数 %d != 文本块条数 %d" % (back.ntotal, len(chunks_after)))
    if len(mapped_after) != len(chunks_after):
        problems.append("映射条数 %d != 文本块条数 %d" % (len(mapped_after), len(chunks_after)))
    nulls = [c["chunk_id"] for c in chunks_after if c.get("vector_id") is None]
    if nulls:
        problems.append("仍有 %d 个文本块 vector_id 为空，样例 %s" % (len(nulls), nulls[:5]))
    if problems:
        for p in problems:
            print("[embed] 失败：%s" % p)
        return 4

    vids = sorted(c["vector_id"] for c in chunks_after)
    if vids != list(range(len(chunks_after))):
        print("[embed] 失败：vector_id 不是 0..%d-1 的排列" % len(chunks_after))
        return 4

    print("[embed] 完成  文本块=%d  向量=%d  文档=%d  耗时=%.2fs（模型载入 %.2fs + 编码 %.2fs）"
          % (n_chunks, index.ntotal, len(doc_ids), time.time() - t_all,
             load_seconds, encode_seconds))
    print("[embed] 写出：%s / %s / %s" % (idx_p, map_p, meta_p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
