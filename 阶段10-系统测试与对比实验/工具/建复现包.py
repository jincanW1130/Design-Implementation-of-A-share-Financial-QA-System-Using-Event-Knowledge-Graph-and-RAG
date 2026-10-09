# -*- coding: utf-8 -*-
"""第 10 阶段（系统测试）——P2-11「最小可复现包」的确定性重建脚本。

## 这个脚本解决什么问题

外部评审 P2-11 指出：`.gitignore` 第 19 行把 `阶段05-数据准备/数据集/` 整体排除，
公开仓库 clone 下来**没有任何数据集正文**，于是门禁脚本与对照实验的读数在换机后
无法复现（《19》第8.11节、《22》第8.8节已自述）。

评审给的两条出路，本仓库**两条都做**：

1. **随送审材料附一个最小可复现子集**——即本脚本产出的 `复现包\\`：只含正式测试集
   的 gold 引用到的文本块、对应文档行与图谱子图切片。
2. **把"可复现性"限定为"脚本可重放、正文受版权限制"**——见
   `阶段10-系统测试与对比实验\\送审材料\\数据来源与合规说明.md` 第 6 节。

## 关键约束（照做，不得放宽）

* **复现包含第三方正文，绝不进公开仓库**：`复现包\\` 已在根 `.gitignore` 里显式排除。
  本脚本只在本地写盘，**不做任何 git 操作**。
* **确定性**：同一份输入 → 同一批字节。所有 jsonl 行按编号升序、所有 csv 行按原表头
  与原排序规则（nodes 按 node_id、edges 按 (关系类型, 起点, 终点, source_chunk_id)）
  输出；`manifest.json` 里除 `generated_at` 外不含任何时间戳。默认 `--generated-at`
  取固定常量，因此**原样重跑两次产出逐字节一致**。
* **只读上游**：只读 `chunks.jsonl`／`documents.jsonl`／`图谱导出\\<profile>\\` 与题集，
  一个字节都不改写。**零大模型调用、零联网抓取**。
* **字段与原件逐字段一致**：`chunks.jsonl` 的字段与 `数据集\\v2.1\\chunks\\chunks.jsonl`
  相同且顺序相同；`documents.jsonl` 与 `数据集\\v2.1\\clean\\documents.jsonl` 相同；
  `graph_slice\\nodes.csv`／`edges.csv` 的表头与 `图谱导出\\<profile>\\` 同名文件
  **逐字相同**。

## 用法

    # 正式口径（题集条数**以 测试集\\questions.jsonl 实际条数为准，现行 120 题**；
    # 显式给 --min-questions 120，题集被改动到不足 120 题时会退出码 2 而不是悄悄按新条数重建）
    python "阶段10-系统测试与对比实验\\工具\\建复现包.py" --min-questions 120

    # 只核算不写盘
    python "阶段10-系统测试与对比实验\\工具\\建复现包.py" --dry-run --min-questions 120

    # 只读某一批的题集把管线跑通一次（自证；批A／批B 的题集在 测试集\\_批A／_批B 下，
    # 条数同样以该文件实际条数为准——批B 现行 36 题，不是 PE 集的 30 题）
    python "阶段10-系统测试与对比实验\\工具\\建复现包.py" ^
        --questions-file "阶段10-系统测试与对比实验\\测试集\\_批B\\questions_B.jsonl"

## 退出码

    0  成功（含 --dry-run）
    2  输入缺失：题集文件不存在／题集内没有任何 gold 引用
    3  数据不一致：gold 引用的 doc_id／chunk_id 在数据集里查不到
    1  其他未预期错误
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

QUESTIONS_DEFAULT = os.path.join(
    ROOT, "阶段10-系统测试与对比实验", "测试集", "questions.jsonl")
CHUNKS_SRC = os.path.join(
    ROOT, "阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")
DOCS_SRC = os.path.join(
    ROOT, "阶段05-数据准备", "数据集", "v2.1", "clean", "documents.jsonl")
GRAPH_DEFAULT = os.path.join(
    ROOT, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_3")
OUT_DEFAULT = os.path.join(ROOT, "阶段10-系统测试与对比实验", "复现包")

# 固定生成时刻：默认值写死，保证原样重跑逐字节一致。
GENERATED_AT_DEFAULT = "2026-10-04T22:45:00+08:00"

# 复现包里由本脚本管理的文件（--force 只允许覆盖这几个；README.md 由人工撰写，不在其列）
MANAGED = (
    "manifest.json",
    "manifest.md",
    "chunks.jsonl",
    "documents.jsonl",
    "graph_slice/nodes.csv",
    "graph_slice/edges.csv",
)


class InputMissing(Exception):
    """输入缺失（退出码 2）。"""


class Inconsistent(Exception):
    """数据不一致（退出码 3）。"""


def log(msg: str) -> None:
    print(msg, flush=True)


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for blk in iter(lambda: fp.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def size_of(path: str) -> int:
    return os.path.getsize(path)


def read_jsonl(path: str) -> list:
    """读 jsonl。空行跳过；坏行直接抛错（不静默丢数据）。"""
    rows = []
    with io.open(path, "r", encoding="utf-8") as fp:
        for lineno, line in enumerate(fp, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise Inconsistent("jsonl 第 %d 行不是合法 JSON：%s（%s）"
                                   % (lineno, exc, path)) from exc
    return rows


def canonical_line(obj: dict) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=False, separators=(", ", ": "))


def pad_line(s: str, width: int) -> str:
    """按显示宽度右填充（中文按 2 列计），仅用于 manifest.md 的表格对齐。"""
    w = sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)
    return s + " " * max(0, width - w)


# --------------------------------------------------------------------------- #
# 一、读题集，收集 gold 引用
# --------------------------------------------------------------------------- #
def collect_gold(questions: list) -> dict:
    doc_ids, chunk_ids = set(), set()
    qid_of_doc, qid_of_chunk = {}, {}
    src_material_docs = set()
    n_with_chunk = 0
    for q in questions:
        qid = q.get("qid")
        if not qid:
            raise Inconsistent("题集里有一条记录没有 qid 字段")
        got_chunk = False
        for cid in q.get("gold_evidence_chunk_ids") or []:
            cid = int(cid)
            chunk_ids.add(cid)
            qid_of_chunk.setdefault(cid, []).append(qid)
            got_chunk = True
        for did in q.get("gold_evidence_doc_ids") or []:
            did = int(did)
            doc_ids.add(did)
            qid_of_doc.setdefault(did, []).append(qid)
        # source_material 是逐题登记的证据来源（含 URL 与发布时间），据此补文档集合。
        for item in q.get("source_material") or []:
            if isinstance(item, dict) and item.get("doc_id") is not None:
                src_material_docs.add(int(item["doc_id"]))
        if got_chunk:
            n_with_chunk += 1
    return {
        "doc_ids": doc_ids,
        "chunk_ids": chunk_ids,
        "qid_of_doc": qid_of_doc,
        "qid_of_chunk": qid_of_chunk,
        "source_material_doc_ids": src_material_docs,
        "questions_with_chunk_gold": n_with_chunk,
    }


# --------------------------------------------------------------------------- #
# 二、读数据集侧三个源文件
# --------------------------------------------------------------------------- #
def load_chunks(path: str) -> tuple:
    rows, order = {}, []
    for obj in read_jsonl(path):
        cid = int(obj["chunk_id"])
        if cid in rows:
            raise Inconsistent("chunks.jsonl 里 chunk_id=%d 出现两次" % cid)
        rows[cid] = obj
        order.append(cid)
    return rows, order


def load_documents(path: str) -> tuple:
    rows, order = {}, []
    for obj in read_jsonl(path):
        did = int(obj["doc_id"])
        if did in rows:
            raise Inconsistent("documents.jsonl 里 doc_id=%d 出现两次" % did)
        rows[did] = obj
        order.append(did)
    return rows, order


def read_csv_rows(path: str) -> tuple:
    """逐行原样读 csv：返回 (表头行, 数据行列表)。不解析字段、不改一个字符。"""
    with io.open(path, "r", encoding="utf-8", newline="") as fp:
        raw = fp.read()
    if raw == "":
        raise Inconsistent("csv 是空文件：%s" % path)
    lines = raw.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    header = lines[0]
    rest = [ln for ln in lines[1:] if ln != ""]
    return header, rest


def col_index(header: str, name: str) -> int:
    cols = header.split(",")
    if name not in cols:
        raise Inconsistent("csv 表头里找不到列 %s：%s" % (name, header))
    return cols.index(name)


def field_of(line: str, idx: int) -> str:
    """取第 idx 列（0 起）。本导出为逐行等列数的净化 csv，直接 split 取值。"""
    parts = line.split(",")
    if len(parts) <= idx:
        raise Inconsistent("csv 行列数不足（需要第 %d 列，实际 %d 列）：%s"
                           % (idx, len(parts), line[:120]))
    return parts[idx]


# --------------------------------------------------------------------------- #
# 三、组装图谱子图切片
# --------------------------------------------------------------------------- #
def build_graph_slice(graph_dir: str, ref_doc_ids: set, ref_chunk_ids: set) -> dict:
    """子图 = 闭包种子 ＋ 两端都在子图内的边。

    种子集合（只含"被引用"三类的节点）：
      ① Document 节点：node_id == 被引用文档的 doc_id；
      ② Event 节点：其 doc_id 列落在被引用文档集合内；
      ③ 上述种子在原始边集里的**直接邻居**（含 EVIDENCED_BY 指向的 Document、
         以及事件的主体／机构／关系路径上的实体）——保留 1 跳是为了让多跳题在
         子图上仍可走通，边界在 manifest 里如实登记。

    边的准入规则：起点与终点都在节点集合内。**不按 source_doc_id 过滤**——
    EVIDENCED_BY 边记录的正是"节点由哪篇文档证明"，按文档过滤会把 Document 节点
    的入边全部删掉、把图谱证据链剪断。与《15》第五节的节点／边准入口径同源。

    **实现的纪律**：导出物是"逐行净化"的 csv，实体 `name` 里仍可能带未转义逗号
    （实测 nodes.csv 有 262 行的列数大于表头的 33 列），因此**不按列号取 `doc_id`**，
    改为**按取值识别**（该行是否存在某一列恰好等于被引用文档号，且等于表头所指列
    的取值之一）。所有输出行**原样照抄源行**，不重排字段、不补引号。
    """
    npath = os.path.join(graph_dir, "nodes.csv")
    epath = os.path.join(graph_dir, "edges.csv")
    for p in (npath, epath):
        if not os.path.isfile(p):
            raise InputMissing("图谱导出文件不存在：%s" % p)

    n_header, n_rows = read_csv_rows(npath)
    e_header, e_rows = read_csv_rows(epath)

    n_label = col_index(n_header, "label")
    n_docid = col_index(n_header, "doc_id")
    e_head = col_index(e_header, "head_id")
    e_tail = col_index(e_header, "tail_id")

    wanted = {str(int(d)) for d in ref_doc_ids}

    seed = set()
    doc_node_ids = set()
    ambiguous = []
    for ln in n_rows:
        parts = ln.split(",")
        if len(parts) <= n_docid:
            raise Inconsistent("nodes.csv 行短于 doc_id 列：%s" % ln[:120])
        if parts[n_label] == "Document":
            doc_node_ids.add(parts[0])
            if parts[0] in wanted:
                seed.add(parts[0])
            continue
        if parts[n_label] != "Event":
            continue
        # 按取值识别 doc_id：优先表头所指列；该列不命中时在其余列里找唯一命中。
        hits = [i for i, v in enumerate(parts) if v in wanted]
        if n_docid in hits:
            seed.add(parts[0])
        elif hits:
            seed.add(parts[0])
            ambiguous.append((parts[0], [parts[i] for i in hits]))
    known_doc_nodes = doc_node_ids

    # ③ 1 跳邻居
    neighbors = set()
    for ln in e_rows:
        h, t = field_of(ln, e_head), field_of(ln, e_tail)
        if h in seed:
            neighbors.add(t)
        if t in seed:
            neighbors.add(h)
    node_set = seed | neighbors

    kept_nodes = [ln for ln in n_rows if ln.split(",")[0] in node_set]
    kept_edges = [ln for ln in e_rows
                  if field_of(ln, e_head) in node_set and field_of(ln, e_tail) in node_set]

    node_id_set = {ln.split(",")[0] for ln in kept_nodes}
    dangling = [ln for ln in kept_edges
                if field_of(ln, e_head) not in node_id_set
                or field_of(ln, e_tail) not in node_id_set]

    label_count = {}
    for ln in kept_nodes:
        lab = field_of(ln, n_label)
        label_count[lab] = label_count.get(lab, 0) + 1

    irregular = sum(1 for ln in n_rows if len(ln.split(",")) != len(n_header.split(",")))

    return {
        "node_header": n_header,
        "node_lines": kept_nodes,
        "edge_header": e_header,
        "edge_lines": kept_edges,
        "stats": {
            "seed_nodes": len(seed),
            "seed_document_nodes": len(seed & known_doc_nodes),
            "seed_event_nodes": len(seed - known_doc_nodes),
            "neighbor_nodes": len(node_set - seed),
            "nodes": len(kept_nodes),
            "edges": len(kept_edges),
            "nodes_by_label": dict(sorted(label_count.items())),
            "dangling_edges": len(dangling),
            "source_node_rows_total": len(n_rows),
            "source_node_rows_irregular": irregular,
            "doc_id_matched_outside_header_column": len(ambiguous),
            "referred_docs_without_document_node": sorted(
                int(d) for d in ref_doc_ids if str(int(d)) not in known_doc_nodes),
            "referred_docs_without_document_node_count": len(
                [d for d in ref_doc_ids if str(int(d)) not in known_doc_nodes]),
        },
    }


# --------------------------------------------------------------------------- #
# 四、主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(
        description="P2-11 最小可复现包：确定性重建（只读上游、零模型调用、零联网）")
    ap.add_argument("--questions-file", default=QUESTIONS_DEFAULT,
                    help="正式测试集 jsonl；缺省 %s" % os.path.relpath(QUESTIONS_DEFAULT, ROOT))
    ap.add_argument("--graph-dir", default=GRAPH_DEFAULT,
                    help="图谱导出目录；缺省现行口径 %s" % os.path.relpath(GRAPH_DEFAULT, ROOT))
    ap.add_argument("--out-dir", default=OUT_DEFAULT,
                    help="复现包输出目录；缺省 %s" % os.path.relpath(OUT_DEFAULT, ROOT))
    ap.add_argument("--chunks-file", default=CHUNKS_SRC, help="文本块源文件")
    ap.add_argument("--documents-file", default=DOCS_SRC, help="文档行源文件")
    ap.add_argument("--generated-at", default=GENERATED_AT_DEFAULT,
                    help="写进 manifest 的生成时刻（固定值，保证确定性）")
    ap.add_argument("--min-questions", type=int, default=1,
                    help="题集至少多少题才继续（正式口径为 120）")
    ap.add_argument("--dry-run", action="store_true", help="只核算与打印，不写盘")
    ap.add_argument("--force", action="store_true",
                    help="允许覆盖复现包目录下由本脚本管理的既有文件")
    args = ap.parse_args()

    # ---- 输入存在性（缺失即报错 + 退出码 2） --------------------------------
    qpath = args.questions_file
    if not os.path.isabs(qpath):
        qpath = os.path.join(ROOT, qpath)
    gdir = args.graph_dir
    if not os.path.isabs(gdir):
        gdir = os.path.join(ROOT, gdir)

    if not os.path.isfile(qpath):
        log("[错误] 题集文件不存在：%s" % qpath)
        log("       正式测试集此刻可能尚未落盘（由另一路任务构建）。")
        log("       可先用只读的某一批题集把管线跑通自证（条数以该文件实际条数为准）：")
        log('         --questions-file "阶段10-系统测试与对比实验\\测试集\\_批B\\questions_B.jsonl"')
        return 2
    for p in (args.chunks_file, args.documents_file):
        if not os.path.isfile(p):
            log("[错误] 上游文件不存在：%s" % p)
            log("       数据集正文在本地工作区才有（公开仓库按 .gitignore 的「数据集」规则排除）。")
            return 2

    questions = read_jsonl(qpath)
    if len(questions) < args.min_questions:
        log("[错误] 题集只有 %d 题，少于 --min-questions=%d"
            % (len(questions), args.min_questions))
        return 2

    gold = collect_gold(questions)
    if not gold["chunk_ids"]:
        log("[错误] 题集里没有任何 gold_evidence_chunk_ids，无法界定最小子集：%s" % qpath)
        return 2

    log("[1/5] 题集 %s：%d 题（含 gold 文本块引用的 %d 题）"
        % (os.path.relpath(qpath, ROOT), len(questions), gold["questions_with_chunk_gold"]))
    log("      gold 文档 %d 个／gold 文本块 %d 个"
        % (len(gold["doc_ids"]), len(gold["chunk_ids"])))

    # ---- 数据集侧 ---------------------------------------------------------
    chunks, _ = load_chunks(args.chunks_file)
    docs, _ = load_documents(args.documents_file)

    missing_chunks = sorted(c for c in gold["chunk_ids"] if c not in chunks)
    if missing_chunks:
        log("[错误] 以下 gold 文本块在 chunks.jsonl 里查不到：%s"
            % ", ".join(str(c) for c in missing_chunks[:20]))
        return 3
    chunk_doc_ids = {int(chunks[c]["doc_id"]) for c in gold["chunk_ids"]}
    ref_doc_ids = set(gold["doc_ids"]) | chunk_doc_ids | set(gold["source_material_doc_ids"])
    missing_docs = sorted(d for d in ref_doc_ids if d not in docs)
    if missing_docs:
        log("[错误] 以下被引用文档在 documents.jsonl 里查不到：%s"
            % ", ".join(str(d) for d in missing_docs[:20]))
        return 3
    orphan = sorted(gold["chunk_ids"] - {
        c for c in gold["chunk_ids"] if int(chunks[c]["doc_id"]) in ref_doc_ids})
    if orphan:
        log("[错误] 以下 gold 文本块所属文档不在被引用文档集合内：%s"
            % ", ".join(str(c) for c in orphan[:20]))
        return 3

    out_chunks = [chunks[c] for c in sorted(gold["chunk_ids"])]
    out_docs = [docs[d] for d in sorted(ref_doc_ids)]
    log("[2/5] 数据集侧：文本块 %d 行／文档 %d 行（gold 文档 %d ＋ 由文本块补齐 %d ＋ 来源登记补齐 %d）"
        % (len(out_chunks), len(out_docs), len(gold["doc_ids"]),
           len(chunk_doc_ids - set(gold["doc_ids"])),
           len(set(gold["source_material_doc_ids"]) - set(gold["doc_ids"]) - chunk_doc_ids)))

    # ---- 图谱侧 -----------------------------------------------------------
    gs = build_graph_slice(gdir, ref_doc_ids, gold["chunk_ids"])
    log("[3/5] 图谱切片（%s）：种子 %d ＋ 邻居 %d → 节点 %d／边 %d；悬空边 %d"
        % (os.path.relpath(gdir, ROOT), gs["stats"]["seed_nodes"],
           gs["stats"]["neighbor_nodes"], gs["stats"]["nodes"],
           gs["stats"]["edges"], gs["stats"]["dangling_edges"]))
    log("      源 nodes.csv %d 行，其中 %d 行列数多于表头 33 列（实体名带未转义逗号，"
        "输出逐行原样照抄、不重排字段）；doc_id 按取值识别而非列号命中 %d 条"
        % (gs["stats"]["source_node_rows_total"],
           gs["stats"]["source_node_rows_irregular"],
           gs["stats"]["doc_id_matched_outside_header_column"]))
    if gs["stats"]["referred_docs_without_document_node_count"]:
        log("      如实登记：被引用文档中有 %d 篇在图谱里没有 Document 节点（%s）"
            % (gs["stats"]["referred_docs_without_document_node_count"],
               ", ".join(str(d) for d in
                         gs["stats"]["referred_docs_without_document_node"][:10])))
    if gs["stats"]["dangling_edges"]:
        log("[错误] 子图里有悬空边：%d 条" % gs["stats"]["dangling_edges"])
        return 3

    # ---- 落盘 -------------------------------------------------------------
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)
    graph_out = os.path.join(out_dir, "graph_slice")

    existing = [rel for rel in MANAGED
                if os.path.exists(os.path.join(out_dir, rel.replace("/", os.sep)))]
    if existing and not (args.force or args.dry_run):
        log("[错误] 复现包目录下已有本脚本管理的 %d 个文件，未加 --force：%s"
            % (len(existing), ", ".join(existing)))
        return 1

    write_targets = {}
    write_targets["chunks.jsonl"] = "\n".join(
        canonical_line(o) for o in out_chunks) + "\n"
    write_targets["documents.jsonl"] = "\n".join(
        canonical_line(o) for o in out_docs) + "\n"
    write_targets["graph_slice/nodes.csv"] = (
        gs["node_header"] + "\n" + "\n".join(gs["node_lines"]) + "\n")
    write_targets["graph_slice/edges.csv"] = (
        gs["edge_header"] + "\n" + "\n".join(gs["edge_lines"]) + "\n")

    if not args.dry_run:
        os.makedirs(graph_out, exist_ok=True)
        for rel, text in write_targets.items():
            p = os.path.join(out_dir, rel.replace("/", os.sep))
            with io.open(p, "w", encoding="utf-8", newline="") as fp:
                fp.write(text)

    # ---- manifest ---------------------------------------------------------
    def entry(rel: str) -> dict:
        """文件指纹。dry-run 下用**内存字节**算，保证读数与实际写盘一致。"""
        if args.dry_run:
            blob = write_targets[rel].encode("utf-8")
            return {"file": rel, "bytes": len(blob),
                    "sha256": hashlib.sha256(blob).hexdigest()}
        p = os.path.join(out_dir, rel.replace("/", os.sep))
        return {"file": rel, "bytes": size_of(p), "sha256": sha256_of(p)}

    files = [entry("chunks.jsonl"), entry("documents.jsonl"),
             entry("graph_slice/nodes.csv"), entry("graph_slice/edges.csv")]

    total_bytes = sum(f["bytes"] for f in files)

    doc_manifest = []
    for d in sorted(ref_doc_ids):
        row = docs[d]
        cites = sorted(set(gold["qid_of_doc"].get(d, [])))
        origins = []
        if d in gold["doc_ids"]:
            origins.append("gold_evidence_doc_ids")
        if d in chunk_doc_ids:
            origins.append("gold_evidence_chunk_ids")
        if d in set(gold["source_material_doc_ids"]):
            origins.append("source_material")
        doc_manifest.append({
            "doc_id": d,
            "title": row.get("title"),
            "category": row.get("category"),
            "source": row.get("source"),
            "publish_time": row.get("publish_time"),
            "url": row.get("url"),
            "content_sha256_16": row.get("content_sha256_16"),
            "chunk_ids": sorted(c for c in gold["chunk_ids"]
                                if int(chunks[c]["doc_id"]) == d),
            "cited_by": cites,
            "origin": origins or ["推导"],
        })
    chunk_manifest = []
    for c in sorted(gold["chunk_ids"]):
        row = chunks[c]
        chunk_manifest.append({
            "chunk_id": c,
            "doc_id": int(row["doc_id"]),
            "chunk_index": row.get("chunk_index"),
            "token_count": row.get("token_count"),
            "vector_id": row.get("vector_id"),
            "cited_by": sorted(set(gold["qid_of_chunk"].get(c, []))),
        })

    manifest = {
        "schema": "stage10-repro-package-1.0",
        "generated_at": args.generated_at,
        "generated_by": "阶段10-系统测试与对比实验\\工具\\建复现包.py",
        "purpose": ("外部评审 P2-11：公开仓库按 .gitignore 排除数据集正文，换机 clone 后"
                    "门禁与实验读数无法复现。本包只含正式测试集 gold 引用到的正文与图谱子图，"
                    "**不入公开仓库**，按本脚本可确定性重建。"),
        "not_in_public_repo": True,
        "inputs": {
            "questions_file": {
                "path": os.path.relpath(qpath, ROOT),
                "questions": len(questions),
                "sha256": sha256_of(qpath),
            },
            "chunks_source": {
                "path": os.path.relpath(args.chunks_file, ROOT),
                "rows_total": len(chunks),
                "sha256": sha256_of(args.chunks_file),
            },
            "documents_source": {
                "path": os.path.relpath(args.documents_file, ROOT),
                "rows_total": len(docs),
                "sha256": sha256_of(args.documents_file),
            },
            "graph_dir": {
                "path": os.path.relpath(gdir, ROOT),
                "nodes_sha256": sha256_of(os.path.join(gdir, "nodes.csv")),
                "edges_sha256": sha256_of(os.path.join(gdir, "edges.csv")),
            },
        },
        "counts": {
            "questions": len(questions),
            "questions_with_chunk_gold": gold["questions_with_chunk_gold"],
            "chunks": len(out_chunks),
            "documents": len(out_docs),
            "graph_nodes": gs["stats"]["nodes"],
            "graph_edges": gs["stats"]["edges"],
            "graph_seed_nodes": gs["stats"]["seed_nodes"],
            "graph_neighbor_nodes": gs["stats"]["neighbor_nodes"],
            "graph_nodes_by_label": gs["stats"]["nodes_by_label"],
            "graph_dangling_edges": gs["stats"]["dangling_edges"],
            "total_bytes": total_bytes,
        },
        "graph_slice_rule": {
            "seed": ("Document 节点（node_id == 被引用 doc_id）＋ doc_id 落在被引用文档集合内的"
                     " Event 节点"),
            "closure": "上述种子在原始边集里的直接邻居（1 跳）",
            "edge_rule": "起点与终点都在节点集合内；**不**按 source_doc_id 过滤，以保住 EVIDENCED_BY 证据链",
            "header": "nodes.csv／edges.csv 的表头与源文件逐字相同",
            "line_fidelity": ("数据行**逐行原样照抄**源导出文件，不重排字段、不补引号；"
                              "源 nodes.csv 有 %d 行的实体名含未转义逗号（列数多于表头 33 列），"
                              "这些行在切片里同样保持原样。字段解析按取值识别而非列号。"
                              % gs["stats"]["source_node_rows_irregular"]),
            "known_gaps": {
                "referred_docs_without_document_node":
                    gs["stats"]["referred_docs_without_document_node"],
                "note": "被引用文档中在图谱里没有 Document 节点的（抽取阶段未产出／被去重合并），如实登记，不臆造",
            },
        },
        "files": files,
        "documents": doc_manifest,
        "chunks": chunk_manifest,
        "usage_limit": ("仅用于本次本科毕业设计的学术研究与论文送审复核；第三方正文不再分发；"
                        "本目录不入公开仓库。"),
    }

    if not args.dry_run:
        mpath = os.path.join(out_dir, "manifest.json")
        with io.open(mpath, "w", encoding="utf-8", newline="") as fp:
            fp.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
        with io.open(os.path.join(out_dir, "manifest.md"), "w",
                     encoding="utf-8", newline="") as fp:
            fp.write(render_manifest_md(manifest, files))

    log("[4/5] 产物：%s" % os.path.relpath(out_dir, ROOT))
    for f in files:
        log("      %-24s %9d B  %s" % (f["file"], f["bytes"], f["sha256"][:16] + "…"))
    log("      合计 %d B（%.2f MiB）" % (total_bytes, total_bytes / 1048576.0))
    log("[5/5] %s；退出码 0" % ("--dry-run 已核算，未写盘" if args.dry_run else "已写盘"))
    return 0


def render_manifest_md(manifest: dict, files: list) -> str:
    c = manifest["counts"]
    g = manifest["graph_slice_rule"]
    L = []
    L.append("# 最小可复现包 · 清单（manifest.md）")
    L.append("")
    L.append("> 由 `阶段10-系统测试与对比实验\\工具\\建复现包.py` 生成；对应机读件 `manifest.json`。")
    L.append("> **本目录不入公开仓库**（根 `.gitignore` 有显式规则），按脚本可确定性重建。")
    L.append("> 生成时刻：%s（`--generated-at` 固定值，原样重跑产出逐字节一致）。" % manifest["generated_at"])
    L.append("")
    L.append("## 一、包内文件与指纹")
    L.append("")
    L.append("| 文件 | 字节 | sha256 |")
    L.append("| --- | ---: | --- |")
    for f in files:
        L.append("| `%s` | %d | `%s` |" % (f["file"], f["bytes"], f["sha256"]))
    L.append("| `manifest.json` | — | 见文件本身（自指摘要不写入） |")
    L.append("")
    L.append("合计 **%d B**（%.2f MiB）。" % (c["total_bytes"], c["total_bytes"] / 1048576.0))
    L.append("")
    L.append("## 二、规模")
    L.append("")
    L.append("| 项 | 读数 |")
    L.append("| --- | ---: |")
    L.append("| 题集 | `%s`，共 %d 题（其中 %d 题带 gold 文本块引用） |"
             % (manifest["inputs"]["questions_file"]["path"], c["questions"],
                c["questions_with_chunk_gold"]))
    L.append("| 文本块（`chunks.jsonl`） | %d |" % c["chunks"])
    L.append("| 文档（`documents.jsonl`） | %d |" % c["documents"])
    L.append("| 图谱节点（`graph_slice\\nodes.csv`） | %d（种子 %d ＋ 邻居 %d） |"
             % (c["graph_nodes"], c["graph_seed_nodes"], c["graph_neighbor_nodes"]))
    L.append("| 图谱边（`graph_slice\\edges.csv`） | %d |" % c["graph_edges"])
    L.append("| 节点按标签 | %s |"
             % "；".join("%s %d" % (k, v) for k, v in c["graph_nodes_by_label"].items()))
    L.append("| 悬空边 | %d |" % c["graph_dangling_edges"])
    L.append("")
    L.append("## 三、子图切片口径")
    L.append("")
    L.append("* **种子**：%s。" % g["seed"])
    L.append("* **闭包**：%s。" % g["closure"])
    L.append("* **边准入**：%s。" % g["edge_rule"])
    L.append("* **表头**：%s。" % g["header"])
    gaps = g["known_gaps"]["referred_docs_without_document_node"]
    L.append("* **已知缺口（如实登记）**：%s" %
             ("无。" if not gaps else
              "被引用文档中 %d 篇在图谱里没有 Document 节点（%s）。"
              % (len(gaps), ", ".join(str(x) for x in gaps))))
    L.append("")
    L.append("## 四、逐文档清单（doc_id／来源／发布时间／原始 URL／被哪些题引用）")
    L.append("")
    L.append("| doc_id | 类别 | 来源 | publish_time | 块数 | 被引用题 | 原始 URL |")
    L.append("| ---: | --- | --- | --- | ---: | --- | --- |")
    for d in manifest["documents"]:
        L.append("| %d | %s | %s | %s | %d | %s | %s |"
                 % (d["doc_id"], d["category"], d["source"], d["publish_time"],
                    len(d["chunk_ids"]),
                    ", ".join(d["cited_by"]) if d["cited_by"] else "—",
                    d["url"]))
    L.append("")
    L.append("## 五、逐文本块清单（chunk_id／doc_id／块内序号／token／被哪些题引用）")
    L.append("")
    L.append("| chunk_id | doc_id | chunk_index | token_count | 被引用题 |")
    L.append("| ---: | ---: | ---: | ---: | --- |")
    for k in manifest["chunks"]:
        L.append("| %d | %d | %s | %s | %s |"
                 % (k["chunk_id"], k["doc_id"], k["chunk_index"], k["token_count"],
                    ", ".join(k["cited_by"]) if k["cited_by"] else "—"))
    L.append("")
    L.append("## 六、使用范围")
    L.append("")
    L.append("* %s" % manifest["usage_limit"])
    L.append("* 「脚本可重放、正文受版权限制」的完整声明见 "
             "`阶段10-系统测试与对比实验\\送审材料\\数据来源与合规说明.md` 第 6 节。")
    L.append("")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    try:
        sys.exit(main())
    except InputMissing as exc:
        log("[错误] %s" % exc)
        sys.exit(2)
    except Inconsistent as exc:
        log("[错误] %s" % exc)
        sys.exit(3)
