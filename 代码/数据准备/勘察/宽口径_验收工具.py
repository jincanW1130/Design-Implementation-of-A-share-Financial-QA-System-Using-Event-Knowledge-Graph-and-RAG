# -*- coding: utf-8 -*-
"""宽口径新闻补充重建的只读验收工具（2026-09-25）。

只读：不写数据集目录，只按需写出调用方指定的 JSON。

两个子命令：
  manifest：对数据集目录做逐文件 SHA-256 清单 + 合并哈希；默认把 raw\\_fetch_log.jsonl
            排除在合并哈希之外（该文件是**追加式**审计日志，复跑会追加审计行），
            并单独记它的 sha256／字节数，便于核验"复跑只追加、不改旧行"。
            另给出"数据文件"（raw\\*.json + clean\\documents.jsonl + chunks\\chunks.jsonl
            + index\\*）的合并哈希 combined_data：这是复跑应逐字节一致的部分
            （meta\\dataset.json 与 reports\\* 记录 check 的生成时间，复跑会刷新该字段）。
  metrics ：从 clean\\documents.jsonl 与 chunks\\chunks.jsonl 重算规模、类目、逐月、
            两个时间桶，以及 company_list≥2／subject_companies≥2 两个关系指标。
  logcheck：核验两个版本的 raw\\_fetch_log.jsonl 是否"旧内容逐字节前缀 + 仅追加"。

用途示例：
  python 代码\\数据准备\\勘察\\宽口径_验收工具.py manifest --dataset 阶段05-数据准备\\数据集\\v2.1 --out 代码\\数据准备\\勘察\\manifest_x.json
  python 代码\\数据准备\\勘察\\宽口径_验收工具.py metrics --dataset 阶段05-数据准备\\数据集\\v2.0
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

AUDIT_LOG = os.path.join("raw", "_fetch_log.jsonl")
DATA_ONLY = (
    "clean/documents.jsonl",
    "chunks/chunks.jsonl",
)


def is_data_file(rel: str) -> bool:
    """复跑必须逐字节一致的"数据文件"：raw 文档、clean、chunks、index（不含审计日志）。"""
    if rel == AUDIT_LOG.replace("\\", "/"):
        return False
    if rel.startswith("raw/"):
        return rel.endswith(".json")
    if rel.startswith("index/"):
        return True
    return rel in DATA_ONLY


def combined_hash(entries: dict) -> str:
    h = hashlib.sha256()
    for rel in sorted(entries):
        h.update(("%s  %s\n" % (entries[rel], rel)).encode("utf-8"))
    return h.hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rel_files(root: str):
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, root).replace("\\", "/"), full


def manifest(root: str, note: str = "") -> dict:
    entries = {}
    for rel, full in rel_files(root):
        entries[rel] = sha256_file(full)
    log_rel = AUDIT_LOG.replace("\\", "/")
    plain = {k: v for k, v in entries.items() if k != log_rel}
    data = {k: v for k, v in plain.items() if is_data_file(k)}
    log_path = os.path.join(root, AUDIT_LOG)
    return {
        "root": os.path.abspath(root),
        "note": note,
        "files": len(entries),
        "files_excluding_fetch_log": len(plain),
        "files_data_only": len(data),
        "combined_data": combined_hash(data),
        "combined_excluding_fetch_log": combined_hash(plain),
        "fetch_log": {
            "sha256": entries.get(log_rel),
            "bytes": os.path.getsize(log_path) if os.path.isfile(log_path) else None,
        },
        "entries": entries,
    }


def load_jsonl(path: str) -> list:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def metrics(root: str) -> dict:
    docs = load_jsonl(os.path.join(root, "clean", "documents.jsonl"))
    chunks_path = os.path.join(root, "chunks", "chunks.jsonl")
    chunks = load_jsonl(chunks_path) if os.path.isfile(chunks_path) else []
    companies = set()
    for d in docs:
        companies.update(str(c) for c in (d.get("company_list") or []))
    months = Counter(str(d.get("publish_time") or "")[:7] for d in docs)
    buckets = {"recent": 0, "earlier": 0, "outside": 0}
    for d in docs:
        day = str(d.get("publish_time") or "")[:10]
        if "2026-08-27" <= day <= "2026-09-25":
            buckets["recent"] += 1
        elif "2026-06-17" <= day <= "2026-08-26":
            buckets["earlier"] += 1
        else:
            buckets["outside"] += 1
    return {
        "root": os.path.abspath(root),
        "doc_count": len(docs),
        "chunk_count": len(chunks),
        "company_count": len(companies),
        "category_counts": dict(Counter(str(d.get("category")) for d in docs)),
        "per_month": dict(sorted(months.items())),
        "buckets": buckets,
        "company_list_ge2": sum(1 for d in docs if len(d.get("company_list") or []) >= 2),
        "subject_companies_ge2": sum(
            1 for d in docs if len(d.get("subject_companies") or []) >= 2),
    }


def print_metrics(m: dict) -> None:
    print("数据集：%s" % m["root"])
    print("  文档 %d；文本块 %d；公司 %d" % (m["doc_count"], m["chunk_count"], m["company_count"]))
    print("  类目：%s" % json.dumps(m["category_counts"], ensure_ascii=False))
    print("  逐月：%s" % json.dumps(m["per_month"], ensure_ascii=False))
    print("  时间桶：%s" % json.dumps(m["buckets"], ensure_ascii=False))
    print("  company_list≥2：%d；subject_companies≥2：%d"
          % (m["company_list_ge2"], m["subject_companies_ge2"]))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="宽口径新闻补充重建：只读验收工具")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("manifest", help="逐文件 SHA-256 清单 + 合并哈希")
    pm.add_argument("--dataset", required=True)
    pm.add_argument("--out", default=None, help="把清单写到该 JSON（不写则只打印摘要）")
    pm.add_argument("--note", default="")

    pt = sub.add_parser("metrics", help="从 clean/chunks 重算规模与关系指标")
    pt.add_argument("--dataset", required=True)
    pt.add_argument("--out", default=None)

    pl = sub.add_parser("logcheck", help="核验审计日志是否只追加（旧内容为前缀）")
    pl.add_argument("--old", required=True)
    pl.add_argument("--new", required=True)

    args = p.parse_args(argv)
    if args.cmd == "manifest":
        m = manifest(args.dataset, args.note)
        print("文件 %d 个（其中排除追加式审计日志后 %d 个）；其中数据文件 %d 个"
              % (m["files"], m["files_excluding_fetch_log"], m["files_data_only"]))
        print("数据文件合并哈希 combined_data = %s" % m["combined_data"])
        print("全部非日志文件合并哈希          = %s" % m["combined_excluding_fetch_log"])
        print("raw/_fetch_log.jsonl：sha256 %s；%s 字节"
              % (m["fetch_log"]["sha256"], m["fetch_log"]["bytes"]))
        if args.out:
            with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(m, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
            print("清单已写出：%s" % args.out)
        return 0
    if args.cmd == "logcheck":
        with open(args.old, "rb") as fh:
            old = fh.read()
        with open(args.new, "rb") as fh:
            new = fh.read()
        ok = new.startswith(old)
        print("旧日志 %d 字节；新日志 %d 字节；旧内容是逐字节前缀：%s"
              % (len(old), len(new), ok))
        if ok:
            added = new[len(old):]
            print("纯追加 %d 字节、%d 行（%d 个换行）"
                  % (len(added), len(added.splitlines()), added.count(b"\n")))
        else:
            i = next((k for k, (a, b) in enumerate(zip(old, new)) if a != b), min(len(old), len(new)))
            print("首个不一致字节偏移：%d" % i)
        return 0 if ok else 1
    m = metrics(args.dataset)
    print_metrics(m)
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(m, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print("指标已写出：%s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
