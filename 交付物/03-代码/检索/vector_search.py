# -*- coding: utf-8 -*-
"""代码\\检索\\vector_search.py —— T2：向量检索实现（第 7 阶段 RAG 检索系统）。

职责（《18》第九节 T2；对应《18》第八节 第 4／5／6 行）：

1. **问题编码**：用 `config.EMBEDDING` 固化的口径在本地编码问题文本——
   `BAAI/bge-small-zh-v1.5`、revision `7999e1d3359715c523056ef9478215996d62a620`、
   512 维、L2 归一化、查询侧不加指令前缀（`query_instruction` 为空串）、
   `max_length = 512`；走本地 `transformers` ＋ `torch` 前向，**不联网下载**。
2. **索引加载**：只走 `config.read_faiss_index()`（内部是 `faiss.deserialize_index`
   ＋ `np.frombuffer` 的字节流反序列化）。中文路径下**绝不**调用向量索引库自带的
   读／写函数（它们走 C++ 的 fopen，会因 ANSI 代码页失败）；检索池是全集 5018 个
   文本块，不建任何子集索引。
3. **返回候选**：给定问题与 N，按相似度降序返回 N 条，每条固定五键——
   `vector_id`、`similarity`（round 到 8 位固定精度）、`chunk_id`、`doc_id`、
   `vector_rank`（1 起算的向量检索原始排名）。`chunk_id`／`doc_id` 一律经
   `交付物/04-数据与知识图谱/数据准备\\数据集\\v2.1\\index\\vector_map.jsonl` 反查，不自行推算。
4. **确定性**：同一输入两次运行的输出**逐字节一致**；相似度并列按 `vector_id`
   升序打破；键序由 `FIELD_ORDER` 固定；输出文件内不写运行时间戳与耗时
   （耗时只打印到 stdout）。
5. **命令行**：`--question "..."`、`--n N`、`--out 路径`，以及 `--selftest` 自证。

纪律：

* 唯一参数来源是 `代码\\检索\\config.py`；本文件不写死模型名、路径、维度、阈值
  （上文提到的取值只为说明口径，运行期一律经 config 读取）。
  **K／N 的默认值不写死**——`--n` 缺省时走 `config.require_fixed("N")`，该项在
  预实验固化前为 TBD，读到即报错退出，不用默认值兜底。
* 本文件只读输入（数据集 v2.1 与图谱导出物一个字节都不写），临时产物只落
  `config.DOCS_DIR`（阶段 7 自己的 `_工作底稿\\`）。
* 本链路 **0 次外部接口调用**：不读任何密钥、不发起任何网络请求；问题侧向量化
  是本地 Embedding 前向（与建索引同模型、同 revision、同归一化、同前缀口径），
  按《18》第2.5节 的口径不计入「模型调用」，但自证里如实打印这一区分。

用法::

    python 代码\\检索\\vector_search.py --question "某公司2026年上半年营业收入是多少？" --n 20 --out 交付物/05-系统实现/RAG检索系统\\_工作底稿\\q1.jsonl
    python 代码\\检索\\vector_search.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

try:  # 控制台为 GBK 时也要能输出中文
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:  # 极少见的非文本流 stdout，重设失败不致命
    pass

# config.py 与本脚本同目录，显式加入 sys.path，保证任意工作目录下都能导入。
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import numpy as np  # noqa: E402

import config  # noqa: E402  唯一参数来源，不得绕过

# 模型只从本机缓存离线加载：先把离线开关置位，再导入 transformers（禁止联网下载）。
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# --------------------------------------------------------------------------
# 固定口径（不是可调参数；可调参数一律来自 config）
# --------------------------------------------------------------------------
SIMILARITY_DECIMALS = 8          # 相似度固定精度：round 到 8 位，保证可复现
FIELD_ORDER = ("vector_id", "similarity", "chunk_id", "doc_id", "vector_rank")

# 自证用例的固定取值（**不是**检索参数 K／N 的默认值；N 的默认值只在 config.RETRIEVAL）
SELFTEST_N = 20
SELFTEST_QUESTION = "某上市公司2026年上半年的营业收入和净利润分别是多少？"
SELFTEST_VECTOR_IDS = (0, 2509, 5017)   # 由 load_pool() 复核为池内合法 vector_id
SELFTEST_MIN_COSINE = 0.999


# --------------------------------------------------------------------------
# 一、输入加载与口径复核（只读）
# --------------------------------------------------------------------------
def load_vector_map():
    """读三级映射，返回 (vector_id → (chunk_id, doc_id), chunk_id → vector_id)。"""
    forward, backward = {}, {}
    for row in config.iter_jsonl(config.VECTOR_MAP_PATH):
        vid = int(row["vector_id"])
        cid = int(row["chunk_id"])
        did = int(row["doc_id"])
        forward[vid] = (cid, did)
        backward[cid] = vid
    return forward, backward


def load_chunks():
    """读文本块表，返回 chunk_id → 行（含 doc_id 与正文）。"""
    chunks = {}
    for row in config.iter_jsonl(config.CHUNKS_PATH):
        chunks[int(row["chunk_id"])] = row
    return chunks


def load_pool():
    """加载向量索引与两张反查表，并做一次口径复核（不一致即报错退出）。

    复核项：向量条数 = `config.CORPUS["vectors"]`、维度 = `config.EMBEDDING["dim"]`、
    度量为内积、`vector_id` 域恰为 0..N-1、每个 `vector_id` 都能查到文本块与文档。
    """
    index = config.read_faiss_index(config.INDEX_PATH)   # 字节流反序列化，绕开中文路径坑
    if int(index.ntotal) != int(config.CORPUS["vectors"]):
        raise SystemExit("[vector_search] 失败：向量条数 %d != config.CORPUS['vectors']=%d"
                         % (int(index.ntotal), int(config.CORPUS["vectors"])))
    if int(index.d) != int(config.EMBEDDING["dim"]):
        raise SystemExit("[vector_search] 失败：索引维度 %d != config.EMBEDDING['dim']=%d"
                         % (int(index.d), int(config.EMBEDDING["dim"])))
    import faiss
    if int(index.metric_type) != int(faiss.METRIC_INNER_PRODUCT):
        raise SystemExit("[vector_search] 失败：索引度量 %d != 内积(%d)"
                         % (int(index.metric_type), int(faiss.METRIC_INNER_PRODUCT)))

    forward, backward = load_vector_map()
    chunks = load_chunks()
    if len(forward) != int(config.CORPUS["vectors"]):
        raise SystemExit("[vector_search] 失败：三级映射 %d 行 != %d"
                         % (len(forward), int(config.CORPUS["vectors"])))
    if sorted(forward) != list(range(int(config.CORPUS["vectors"]))):
        raise SystemExit("[vector_search] 失败：vector_id 域不是 0..%d"
                         % (int(config.CORPUS["vectors"]) - 1))
    for vid, (cid, did) in forward.items():
        row = chunks.get(cid)
        if row is None:
            raise SystemExit("[vector_search] 失败：vector_id=%d 的 chunk_id=%d 不在文本块表里"
                             % (vid, cid))
        if int(row["doc_id"]) != did:
            raise SystemExit("[vector_search] 失败：chunk_id=%d 的 doc_id=%d 与映射的 %d 不一致"
                             % (cid, int(row["doc_id"]), did))
    return index, forward, backward, chunks


def resolve_snapshot_dir(model_name: str, revision: str) -> str:
    """离线解析本机缓存中**固化 revision 的那一份快照目录**。

    找不到即报错并打印已查路径：**不联网下载、不静默换模型**（《18》第五节 硬约束 12）。
    """
    from huggingface_hub.constants import HF_HUB_CACHE

    repo_dir = os.path.join(HF_HUB_CACHE, "models--" + model_name.replace("/", "--"))
    snapshot = os.path.join(repo_dir, "snapshots", revision)
    if not os.path.isdir(snapshot):
        raise SystemExit(
            "[vector_search] 失败：本机缓存里找不到固化 revision 的快照。\n"
            "  模型：%s\n  revision：%s\n  已查路径：%s\n"
            "  处置：补齐本机缓存后重跑；本脚本不联网下载、也不换模型。"
            % (model_name, revision, snapshot))
    missing = [n for n in ("config.json", "tokenizer.json", "sentence_bert_config.json")
               if not os.path.isfile(os.path.join(snapshot, n))]
    if not (os.path.isfile(os.path.join(snapshot, "model.safetensors"))
            or os.path.isfile(os.path.join(snapshot, "pytorch_model.bin"))):
        missing.append("model.safetensors | pytorch_model.bin")
    if missing:
        raise SystemExit("[vector_search] 失败：快照目录 %s 缺文件：%s"
                         % (snapshot, "、".join(missing)))
    return snapshot


# --------------------------------------------------------------------------
# 二、问题编码（本地、离线、与建索引同口径）
# --------------------------------------------------------------------------
def _normalizer_has_lowercase(normalizer) -> bool:
    """判断分词器后端的 normalizer 链里是否已经包含 Lowercase。"""
    from tokenizers.normalizers import Lowercase, Sequence

    if normalizer is None:
        return False
    if isinstance(normalizer, Lowercase):
        return True
    if isinstance(normalizer, Sequence):
        return any(isinstance(n, Lowercase) for n in normalizer)
    return False


def apply_do_lower_case(tokenizer, do_lower_case: bool) -> None:
    """按建索引时 sentence-transformers 的同一做法落地 `do_lower_case`。

    建索引用的是「快照 `sentence_bert_config.json` 的 `do_lower_case=true`」＋
    sentence-transformers 的处理方式：**把 `Lowercase()` 插到既有 normalizer 链的最前面**
    （`Sequence([Lowercase(), 原有 normalizer…])`）。这条链与「先整串 `str.lower()`
    再分词」等价，但比直接传 `do_lower_case=True` 更接近建索引的实际路径——
    后者会让分词器重建 BertNormalizer 并连带启用 strip_accents，已实测与索引口径不符
    （少数含兼容汉字的文本块余弦只有 0.960，属"静默换口径"，必须避免）。
    """
    if not do_lower_case:
        return
    from tokenizers.normalizers import Lowercase, Sequence

    backend = tokenizer.backend_tokenizer
    normalizer = backend.normalizer
    if _normalizer_has_lowercase(normalizer):
        return
    new_normalizers = [Lowercase()]
    if isinstance(normalizer, Sequence):
        new_normalizers += list(normalizer)
    elif normalizer is not None:
        new_normalizers.append(normalizer)
    backend.normalizer = Sequence(new_normalizers)


class LocalEmbedder:
    """本地 Embedding 前向：transformers ＋ torch 直连，全程离线。

    编码口径与建索引一致：CLS 池化 → L2 归一化（`config.EMBEDDING["normalize"]`）、
    `max_length` 与分词器大小写口径取自快照自带的 `sentence_bert_config.json`，
    并按建索引时 sentence-transformers 的同一做法落地 `do_lower_case`（详见
    `apply_do_lower_case()`；等价写法是先把整串文本 `str.lower()`，但这里直接改
    分词器后端的 normalizer 链，保证与建索引逐字同路），
    查询侧不加任何指令前缀（`config.EMBEDDING["query_instruction"]` 为空串）。
    """

    def __init__(self, verbose: bool = True, batch_size: int = 32):
        import torch
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self.batch_size = int(batch_size)
        torch.set_num_threads(1)          # 单线程前向：同一机器两次运行的数值逐位一致

        self.model_name = config.EMBEDDING["model_name"]
        self.revision = config.EMBEDDING["revision"]
        self.max_length = int(config.EMBEDDING["max_length"])
        self.query_instruction = str(config.EMBEDDING["query_instruction"])
        self.normalize = bool(config.EMBEDDING["normalize"])

        self.snapshot_dir = resolve_snapshot_dir(self.model_name, self.revision)
        st_path = os.path.join(self.snapshot_dir, "sentence_bert_config.json")
        with open(st_path, "r", encoding="utf-8") as f:
            st_cfg = json.load(f)
        self.do_lower_case = bool(st_cfg.get("do_lower_case", False))
        if int(st_cfg.get("max_seq_length", -1)) != self.max_length:
            raise SystemExit("[vector_search] 失败：快照 max_seq_length=%r != config 的 %d"
                             % (st_cfg.get("max_seq_length"), self.max_length))

        t0 = time.time()
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.snapshot_dir, local_files_only=True, do_lower_case=False)
        apply_do_lower_case(self.tokenizer, self.do_lower_case)
        self.model = AutoModel.from_pretrained(self.snapshot_dir, local_files_only=True)
        self.model.eval()
        self.load_seconds = time.time() - t0

        dim = int(self.model.config.hidden_size)
        if dim != int(config.EMBEDDING["dim"]):
            raise SystemExit("[vector_search] 失败：模型维度 %d != config.EMBEDDING['dim']=%d"
                             % (dim, int(config.EMBEDDING["dim"])))
        if verbose:
            print("[vector_search] 本地模型就绪：%s @ %s" % (self.model_name, self.revision))
            print("[vector_search]   快照目录 = %s" % self.snapshot_dir)
            print("[vector_search]   维度=%d  do_lower_case=%s  max_length=%d  L2归一化=%s"
                  % (dim, self.do_lower_case, self.max_length, self.normalize))
            print("[vector_search]   分词器 normalizer 链含 Lowercase=%s（与建索引同路）"
                  % _normalizer_has_lowercase(self.tokenizer.backend_tokenizer.normalizer))
            print("[vector_search]   查询侧指令前缀 = %r（空串＝不加前缀）" % self.query_instruction)
            print("[vector_search]   离线加载：local_files_only=True，HF_HUB_OFFLINE=%s，"
                  "TRANSFORMERS_OFFLINE=%s"
                  % (os.environ.get("HF_HUB_OFFLINE"), os.environ.get("TRANSFORMERS_OFFLINE")))

    def encode(self, texts) -> np.ndarray:
        """把一组文本编码成 (n, dim) 的 float32 矩阵，行已按 config 口径归一化。"""
        items = [str(t) for t in texts]
        if not items:
            raise ValueError("encode() 收到空列表")
        torch = self._torch
        parts = []
        for start in range(0, len(items), self.batch_size):
            batch = items[start:start + self.batch_size]
            enc = self.tokenizer(batch, padding=True, truncation=True,
                                 max_length=self.max_length, return_tensors="pt")
            with torch.no_grad():
                out = self.model(**enc)
            cls = out.last_hidden_state[:, 0, :]      # CLS 池化，与建索引一致
            if self.normalize:
                cls = torch.nn.functional.normalize(cls, p=2, dim=1)
            parts.append(cls.cpu().numpy().astype("float32"))
        vec = np.ascontiguousarray(np.concatenate(parts, axis=0), dtype="float32")
        if vec.shape[1] != int(config.EMBEDDING["dim"]):
            raise SystemExit("[vector_search] 失败：编码结果维度 %d != %d"
                             % (vec.shape[1], int(config.EMBEDDING["dim"])))
        return vec

    def encode_query(self, question: str) -> np.ndarray:
        """编码单个问题：整串编码（不切词），按固化口径加前缀（当前为空串）。"""
        text = str(question).strip()
        if not text:
            raise SystemExit("[vector_search] 失败：问题文本为空")
        return self.encode([self.query_instruction + text])[0]


# --------------------------------------------------------------------------
# 三、检索与排名（确定性）
# --------------------------------------------------------------------------
def rank_pairs(index, query_vec, pool_size: int):
    """在全集上做一次精确检索，返回按 (相似度降序, vector_id 升序) 排好的 (vector_id, 相似度)。

    * 一次取 `k = ntotal`：等价于对全集逐条打分，**并列不会在截断处被随机丢弃**；
    * 相似度先 round 到固定精度再排序，使「输出里看到的并列」与「打破并列的规则」完全一致。
    """
    scores, ids = index.search(np.ascontiguousarray(query_vec.reshape(1, -1)), int(pool_size))
    pairs = []
    for sim, vid in zip(scores[0], ids[0]):
        vid = int(vid)
        if vid < 0:                      # 理论上不会出现（k = ntotal）
            continue
        pairs.append((vid, float(round(float(sim), SIMILARITY_DECIMALS))))
    pairs.sort(key=lambda p: (-p[1], p[0]))
    return pairs


class VectorSearcher:
    """向量检索组件的对外入口：一次加载，多次检索。"""

    def __init__(self, verbose: bool = True, index=None, forward=None, backward=None,
                 chunks=None, embedder=None):
        t0 = time.time()
        if index is None or forward is None or chunks is None:
            index, forward, backward, chunks = load_pool()
        self.index = index
        self.forward = forward                    # vector_id → (chunk_id, doc_id)
        self.backward = backward                  # chunk_id → vector_id
        self.chunks = chunks
        self.pool_seconds = time.time() - t0
        self.embedder = embedder if embedder is not None else LocalEmbedder(verbose=verbose)

    def search(self, question: str, n: int):
        """返回 (N 条候选, 耗时字典)；候选固定五键、固定键序、固定精度。"""
        n = int(n)
        if n <= 0:
            raise SystemExit("[vector_search] 失败：N 必须为正整数，收到 %d" % n)
        if n > int(self.index.ntotal):
            raise SystemExit("[vector_search] 失败：N=%d 超过检索池 %d 个文本块"
                             % (n, int(self.index.ntotal)))

        t_enc = time.time()
        query_vec = self.embedder.encode_query(question)
        encode_seconds = time.time() - t_enc

        t_search = time.time()
        pairs = rank_pairs(self.index, query_vec, int(self.index.ntotal))[:n]
        search_seconds = time.time() - t_search

        rows = []
        for rank, (vid, sim) in enumerate(pairs, 1):
            cid, did = self.forward[vid]
            values = {"vector_id": vid, "similarity": sim, "chunk_id": cid,
                      "doc_id": did, "vector_rank": rank}
            rows.append({key: values[key] for key in FIELD_ORDER})   # 键序由 FIELD_ORDER 固定
        return rows, {"encode_seconds": encode_seconds, "search_seconds": search_seconds}


# --------------------------------------------------------------------------
# 四、落盘（UTF-8 无 BOM、LF、原子替换、逐字节可复现）
# --------------------------------------------------------------------------
def write_jsonl(path: str, rows) -> None:
    """按 FIELD_ORDER 固定键序写 JSONL；不写时间戳与耗时、无 BOM、LF、原子替换。"""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            ordered = {key: row[key] for key in FIELD_ORDER}
            f.write(json.dumps(ordered, ensure_ascii=False, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def format_rows(rows) -> str:
    """把候选格式化成可读多行（只打印到 stdout，不落任何比对文件）。"""
    return "\n".join(
        "  rank=%2d  sim=%.8f  chunk_id=%d  doc_id=%d  vector_id=%d"
        % (row["vector_rank"], row["similarity"], row["chunk_id"], row["doc_id"], row["vector_id"])
        for row in rows)


# --------------------------------------------------------------------------
# 五、命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="T2 向量检索：问题整串编码 → 全集向量索引精确检索 → N 条候选（含原始排名）")
    p.add_argument("--question", default=None, help="待检索的问题文本（--selftest 时可省略）")
    p.add_argument("--n", type=int, default=None,
                   help="候选条数；缺省时取 config.RETRIEVAL['N']（TBD 时按硬约束报错退出）")
    p.add_argument("--out", default=os.path.join(config.DOCS_DIR, "vector_search_result.jsonl"),
                   help="输出 JSONL 路径（默认落阶段 7 自己的 _工作底稿\\）")
    p.add_argument("--selftest", action="store_true",
                   help="跑五条自证：编码口径复现／N 正确／映射正确／确定性／零模型调用")
    return p.parse_args(argv)


def cmd_search(args) -> int:
    if not args.question or not str(args.question).strip():
        print("[vector_search] 失败：普通检索必须给 --question（或用 --selftest）")
        return 2
    n = args.n if args.n is not None else config.require_fixed("N")

    t_all = time.time()
    searcher = VectorSearcher(verbose=True)
    print("[vector_search] 索引：ntotal=%d  d=%d  度量=内积(%d)  池加载=%.2fs"
          % (int(searcher.index.ntotal), int(searcher.index.d),
             int(searcher.index.metric_type), searcher.pool_seconds))
    rows, timing = searcher.search(args.question, n)
    write_jsonl(args.out, rows)
    total_seconds = time.time() - t_all

    print("[vector_search] 问题：%s" % str(args.question).strip())
    print("[vector_search] N=%d，返回 %d 条（按相似度降序，并列按 vector_id 升序）："
          % (n, len(rows)))
    print(format_rows(rows))
    print("[vector_search] 落盘：%s" % os.path.abspath(args.out))
    print("[vector_search] 耗时（只打印，不进比对文件）：问题编码=%.3fs  检索排名=%.3fs  "
          "模型载入=%.2fs  总耗时=%.3fs"
          % (timing["encode_seconds"], timing["search_seconds"],
             searcher.embedder.load_seconds, total_seconds))
    return 0


def _cosine(a, b) -> float:
    a = np.asarray(a, dtype="float64")
    b = np.asarray(b, dtype="float64")
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def _self_source_scan() -> list:
    """扫本文件源码，统计「密钥读取／网络调用」字面量命中数（拼串构造，避免自我命中）。

    这是「零外部请求」的机器可核验证据之一：全部命中数应为 0。
    """
    patterns = ["api" + "_key", "API" + "_KEY", "access" + "_token", "sec" + "ret",
                "requests" + ".", "urllib" + ".request", "socket" + ".",
                "http" + "://", "https" + "://"]
    with open(os.path.abspath(__file__), "r", encoding="utf-8") as f:
        source = f.read()
    return [(p, source.count(p)) for p in patterns]


def cmd_selftest(args) -> int:
    """五条自证，逐条打印 [OK ]／[FAIL]；全过返回 0，否则 1。"""
    results = []

    def check(name, ok, detail=""):
        results.append(bool(ok))
        print("  [%s] %s%s" % ("OK  " if ok else "FAIL", name,
                               ("  —— " + detail) if detail else ""))
        return bool(ok)

    print("=" * 78)
    print("T2 向量检索自证：数据集 %s（只读输入，不写输入）" % config.DATASET_VERSION)
    print("=" * 78)

    t_all = time.time()
    index, forward, backward, chunks = load_pool()
    print("\n〇、加载（口径复核）")
    print("  [OK  ] 向量索引：ntotal=%d  d=%d  度量=内积(%d)  读法=config.read_faiss_index()"
          "（字节流反序列化；不用向量索引库自带的读函数）"
          % (int(index.ntotal), int(index.d), int(index.metric_type)))
    print("  [OK  ] 三级映射：%d 行，vector_id 域 0..%d，逐条可反查文本块与文档"
          % (len(forward), max(forward)))
    embedder = LocalEmbedder(verbose=True)
    print("  [OK  ] 本地模型路径：%s（目录名＝固化 revision）" % embedder.snapshot_dir)

    question = SELFTEST_QUESTION
    n_selftest = SELFTEST_N

    # --- 1 编码口径复现 ---
    print("\n一、Embedding 口径复现：索引内 reconstruct 的存量向量 vs 同一编码路径重编码")
    sims = []
    for vid in SELFTEST_VECTOR_IDS:
        cid, _ = forward[vid]
        text = chunks[cid]["content"]
        stored = np.asarray(index.reconstruct(int(vid)), dtype="float32")
        fresh = embedder.encode([text])[0]
        cos = _cosine(stored, fresh)
        sims.append(cos)
        print("      vector_id=%4d  chunk_id=%d  正文长度=%d  余弦相似度=%.10f"
              % (vid, cid, len(text), cos))
    check("口径复现：3 条余弦相似度均 >= %.3f" % SELFTEST_MIN_COSINE,
          all(s >= SELFTEST_MIN_COSINE for s in sims),
          "最小值=%.10f" % min(sims))

    # --- 2 N 正确 ---
    print("\n二、N 正确：任取一题、N=%d" % n_selftest)
    searcher = VectorSearcher(verbose=False, index=index, forward=forward,
                              backward=backward, chunks=chunks, embedder=embedder)
    rows, timing = searcher.search(question, n_selftest)
    sim_values = [r["similarity"] for r in rows]
    ranks = [r["vector_rank"] for r in rows]
    monotone = all(sim_values[i] >= sim_values[i + 1] for i in range(len(sim_values) - 1))
    print("      问题：%s" % question)
    print("      返回条数=%d  相似度区间=%.8f～%.8f  首条 vector_rank=%d  末条=%d"
          % (len(rows), sim_values[0], sim_values[-1], ranks[0], ranks[-1]))
    check("返回恰好 %d 条" % n_selftest, len(rows) == n_selftest, "实测 %d" % len(rows))
    check("相似度单调不增", monotone, "降序判定通过" if monotone else "存在回升")
    check("vector_rank 为 1..%d" % n_selftest, ranks == list(range(1, n_selftest + 1)),
          "实测 %d..%d 连续" % (ranks[0], ranks[-1]))

    # --- 3 映射正确 ---
    print("\n三、映射正确：返回的 chunk_id 都在文本块表里，doc_id 与三级映射一致")
    ok_map, detail_map = True, []
    for r in rows:
        cid, did_map = forward[r["vector_id"]]
        cid_bad = (r["chunk_id"] != cid) or (cid not in chunks)
        doc_bad = (r["doc_id"] != did_map) or (int(chunks[r["chunk_id"]]["doc_id"]) != r["doc_id"])
        if cid_bad or doc_bad:
            ok_map = False
            detail_map.append("vector_id=%d 反查失败" % r["vector_id"])
    check("逐条反查通过（%d/%d）" % (len(rows), len(rows)), ok_map,
          "；".join(detail_map[:3]) if detail_map else "chunk_id 全部存在、doc_id 全部一致")
    distinct_chunks = len({r["chunk_id"] for r in rows})
    print("      说明：%d 条候选落在 %d 个不同 chunk_id 上（%s）"
          % (len(rows), distinct_chunks,
             "无重复" if distinct_chunks == len(rows) else "有重复，下游须按 chunk_id 去重"))
    check("全集映射自洽：%d 行三级映射与 %d 行文本块逐条对齐"
          % (int(config.CORPUS["vectors"]), int(config.CORPUS["chunks"])),
          len(forward) == int(config.CORPUS["vectors"]) and len(chunks) == int(config.CORPUS["chunks"]),
          "映射 %d 行、文本块 %d 行" % (len(forward), len(chunks)))

    # --- 4 确定性 ---
    print("\n四、确定性：同一题连跑两次，两次落盘文件逐字节一致")
    path_a = os.path.join(config.DOCS_DIR, "t2_selftest_det_a.jsonl")
    path_b = os.path.join(config.DOCS_DIR, "t2_selftest_det_b.jsonl")
    rows_a, _ = searcher.search(question, n_selftest)
    write_jsonl(path_a, rows_a)
    rows_b, _ = searcher.search(question, n_selftest)
    write_jsonl(path_b, rows_b)
    sha_a, sha_b = config.sha256_file(path_a), config.sha256_file(path_b)
    with open(path_a, "rb") as fa, open(path_b, "rb") as fb:
        same_bytes = fa.read() == fb.read()
    print("      文件 A：%s" % path_a)
    print("        sha256 = %s" % sha_a)
    print("      文件 B：%s" % path_b)
    print("        sha256 = %s" % sha_b)
    check("两次运行输出逐字节一致", same_bytes and sha_a == sha_b,
          "sha256 %s" % ("相同" if sha_a == sha_b else "不同"))

    # --- 5 零模型调用 ---
    print("\n五、零模型调用：无密钥读取、无外部请求")
    print("      本地模型目录 = %s" % embedder.snapshot_dir)
    print("      加载用法：from_pretrained(<该目录>, local_files_only=True)；进程环境 "
          "HF_HUB_OFFLINE=%s，TRANSFORMERS_OFFLINE=%s"
          % (os.environ.get("HF_HUB_OFFLINE"), os.environ.get("TRANSFORMERS_OFFLINE")))
    print("      口径区分：问题侧向量化是本地 Embedding 前向（与建索引同模型同 revision），"
          "按《18》第2.5节 不计入「模型调用」")
    print("      config.MODEL_CALLS_ALLOWED = %s（第 7 阶段不做任何大语言模型调用）"
          % config.MODEL_CALLS_ALLOWED)
    hits = _self_source_scan()
    print("      源码扫描（本文件内字面量命中数）：%s"
          % "，".join("%s=%d" % (p, c) for p, c in hits))
    check("无密钥读取、无网络调用字面量", all(c == 0 for _, c in hits),
          "命中合计 %d" % sum(c for _, c in hits))
    check("config 侧开关：MODEL_CALLS_ALLOWED == 0", config.MODEL_CALLS_ALLOWED == 0,
          "实测 %r" % config.MODEL_CALLS_ALLOWED)

    print("\n" + "=" * 78)
    passed = sum(1 for r in results if r)
    print("自证结论：%d/%d 条通过（耗时 %.1fs，只打印到 stdout，不写入任何产出文件）"
          % (passed, len(results), time.time() - t_all))
    print("=" * 78)
    return 0 if passed == len(results) else 1


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.selftest:
        return cmd_selftest(args)
    return cmd_search(args)


if __name__ == "__main__":
    sys.exit(main())
