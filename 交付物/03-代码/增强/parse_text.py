# -*- coding: utf-8 -*-
"""代码\\数据准备\\parse_text.py —— txt／md 最小解析入口（第 10 轮新增）。

为什么需要
----------
现有抓取管线（`fetch.py`）面向网页／PDF：raw 记录由 `Doc.to_raw()` 产出，`raw_text` 是
抽取出的正文。纯文本（.txt）与 Markdown（.md）此前**没有独立入口**——它们可以走管理端
JSON 正文导入，但本地文件无法直接落成 `raw\\{doc_id}.json`。本模块补上这一最小入口：

    .txt / .md 文件 → read_text()（UTF-8/GBK 回退）→ parse_text_file()（raw 记录）
                    → write_raw_document()（可选，落成 raw\\{doc_id}.json）

纪律
----
* **不跑数据集、不重建索引**：本模块只解析单个文件；是否入库由调用方决定。
* **不编造**：`publish_time`／`category`／`source`／`doc_id` 必须由调用方显式给出；
  文件里没有的信息一律留空（`page_url`／`content_url` 为空串，`http_status` 为 None）。
* **正文不改写**：只去掉 UTF-8 BOM；Markdown 标记、换行与空白保持原样（与既有兼容性
  口径一致：现有管线能读纯文本，但不做 Markdown → HTML／纯文本转换）。
* 输出字段与 `fetch.Doc.to_raw()` 逐键对齐，可直接被 `clean.py` 消费。
* `extract_method` 固定为 `txt_plain`／`md_plain`，与既有 `pdf_pymupdf`／`html_bs4`／
  `api_json` 区分，便于审计来源。

用法::

    python 代码\\数据准备\\parse_text.py --file 通知.md --doc-id 9001 \\
        --category 政策文件 --source 本地文件 --publish-time 2026-09-01
    python 代码\\数据准备\\parse_text.py --file 通知.txt ... --out-root <临时目录>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  唯一参数来源（类别枚举等），不写死

SUPPORTED_SUFFIXES = (".txt", ".md")
# 编码回退顺序：UTF-8（含 BOM）→ GB18030（GBK 的超集，覆盖中文 Windows 常见文本）
ENCODING_FALLBACK = ("utf-8-sig", "utf-8", "gb18030")

_CN_TZ = timezone(timedelta(hours=8))


def read_text(path: str, encoding: str | None = None) -> tuple:
    """读纯文本文件，返回 `(text, used_encoding)`；BOM 已去除。

    * 不给 `encoding`：按 `ENCODING_FALLBACK` 依次尝试，全部失败抛 `ValueError`；
    * 给了 `encoding`：严格按它解码（失败即 `ValueError`），不做静默回退。
    """
    with open(path, "rb") as f:
        data = f.read()
    candidates = (encoding,) if encoding else ENCODING_FALLBACK
    last_error = None
    for enc in candidates:
        try:
            text = data.decode(enc)
        except (UnicodeDecodeError, LookupError) as exc:
            last_error = exc
            continue
        if text.startswith("﻿"):
            text = text[1:]
        return text, enc
    raise ValueError("无法按 %s 解码文件 %s：%s"
                     % ("／".join(candidates), path, last_error))


def _markdown_title(text: str) -> str:
    """取 Markdown 第一个 ATX 一级／任意级标题作默认标题（去掉 `#` 与首尾空白）。"""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title
    return ""


def _default_title(path: str, text: str, is_markdown: bool) -> str:
    if is_markdown:
        title = _markdown_title(text)
        if title:
            return title
    return os.path.splitext(os.path.basename(path))[0]


def _now_iso() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def parse_text_file(path: str, *, doc_id: int, category: str, source: str,
                    publish_time: str, title: str | None = None,
                    company_list=(), page_url: str = "", content_url: str = "",
                    meta: dict | None = None, fetched_at: str | None = None,
                    encoding: str | None = None) -> dict:
    """把一个 .txt／.md 文件解析成与 `raw\\{doc_id}.json` 同形的记录。

    必填项（`doc_id`／`category`／`source`／`publish_time`）不设默认值——文件本身不含
    这些元信息，默认值等于编造。`company_list` 统一存成字符串数组（可为空，但非 None）。
    """
    suffix = os.path.splitext(path)[1].lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError("只支持 %s，收到 %r" % ("／".join(SUPPORTED_SUFFIXES), path))
    if not isinstance(doc_id, int) or isinstance(doc_id, bool) or doc_id <= 0:
        raise ValueError("doc_id 必须是正整数，收到 %r" % (doc_id,))
    if category not in config.CATEGORIES:
        raise ValueError("category 必须是 %s 之一，收到 %r"
                         % (config.CATEGORIES, category))
    if not str(source or "").strip():
        raise ValueError("source 不能为空")
    if not str(publish_time or "").strip():
        raise ValueError("publish_time 不能为空（文件里没有日期时请由调用方给出）")

    text, used_encoding = read_text(path, encoding=encoding)
    is_markdown = suffix == ".md"
    resolved_title = (str(title).strip() if title is not None and str(title).strip()
                      else _default_title(path, text, is_markdown))
    companies = [str(item).strip() for item in (company_list or []) if str(item).strip()]
    doc_meta = dict(meta) if isinstance(meta, dict) else {}
    doc_meta.setdefault("source_file", os.path.basename(path))
    doc_meta.setdefault("text_encoding", used_encoding)
    return {
        "doc_id": int(doc_id),
        "category": category,
        "source": str(source).strip(),
        "title": resolved_title,
        "company_list": companies,
        "publish_time": str(publish_time).strip(),
        "page_url": str(page_url or ""),
        "content_url": str(content_url or ""),
        "raw_text": text,
        "extract_method": "md_plain" if is_markdown else "txt_plain",
        "fetched_at": fetched_at or _now_iso(),
        "http_status": None,
        "byte_size": len(text.encode("utf-8")),
        "meta": doc_meta,
    }


def write_raw_document(root_dir: str, record: dict, overwrite: bool = False) -> str:
    """把记录写成 `root_dir/raw/{doc_id}.json`（UTF-8、LF、原子替换）；默认不覆盖。

    与 `fetch.py` 的幂等口径一致：已存在的 `raw\\{doc_id}.json` 默认拒绝覆盖，
    需要覆盖时显式传 `overwrite=True`。本函数只写调用方指定的目录，不触碰正式数据集。
    """
    if not isinstance(record, dict) or "doc_id" not in record:
        raise ValueError("record 必须是含 doc_id 的字典")
    raw_dir = os.path.join(os.path.abspath(root_dir), "raw")
    os.makedirs(raw_dir, exist_ok=True)
    path = os.path.join(raw_dir, "%d.json" % int(record["doc_id"]))
    if os.path.exists(path) and not overwrite:
        raise FileExistsError("raw 文件已存在（如需覆盖请显式 overwrite=True）：%s" % path)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="txt／md 最小解析入口：文件 → raw 记录（可选落成 raw/{doc_id}.json）")
    parser.add_argument("--file", required=True, help=".txt 或 .md 文件路径")
    parser.add_argument("--doc-id", type=int, required=True)
    parser.add_argument("--category", required=True,
                        help="四类之一：%s" % "／".join(config.CATEGORIES))
    parser.add_argument("--source", required=True)
    parser.add_argument("--publish-time", required=True, help="YYYY-MM-DD")
    parser.add_argument("--title", default=None)
    parser.add_argument("--company", action="append", default=[],
                        help="股票代码，可重复传入")
    parser.add_argument("--page-url", default="")
    parser.add_argument("--content-url", default="")
    parser.add_argument("--out-root", default=None,
                        help="给出时写入 <out-root>/raw/{doc_id}.json；缺省只打印 JSON")
    parser.add_argument("--encoding", default=None, help="显式编码（缺省自动回退）")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        record = parse_text_file(
            args.file, doc_id=args.doc_id, category=args.category, source=args.source,
            publish_time=args.publish_time, title=args.title,
            company_list=args.company, page_url=args.page_url,
            content_url=args.content_url, encoding=args.encoding)
        output = json.dumps(record, ensure_ascii=False, indent=2)
        if args.out_root:
            path = write_raw_document(args.out_root, record)
            print("[parse_text] 已写入：%s" % path)
        else:
            print(output)
    except (OSError, ValueError) as exc:
        print("[parse_text] 失败：%s" % exc)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
