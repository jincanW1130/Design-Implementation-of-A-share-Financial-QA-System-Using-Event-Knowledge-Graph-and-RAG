# -*- coding: utf-8 -*-
"""P 组 · txt／md 最小解析入口（第 10 轮新增）—— 被测文件：`代码\\增强\\parse_text.py`。

覆盖：编码回退（UTF-8 BOM／GB18030）、Markdown 标题、必填元信息不编造、
raw 字段与 `fetch.Doc.to_raw()` 对齐、`raw\\{doc_id}.json` 落盘与幂等拒绝覆盖。
全部用临时文件，不读真实数据集、不重跑数据准备。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

parse_text = _bootstrap.load_module("增强", "parse_text.py")
cfg = _bootstrap.component_config("增强")

RAW_KEYS = {"doc_id", "category", "source", "title", "company_list", "publish_time",
            "page_url", "content_url", "raw_text", "extract_method", "fetched_at",
            "http_status", "byte_size", "meta"}


def _write(tmp_path, name, text, encoding="utf-8"):
    path = tmp_path / name
    path.write_bytes(text.encode(encoding))
    return str(path)


def _parse(path, **overrides):
    kwargs = {"doc_id": 9001, "category": cfg.CATEGORIES[0], "source": "本地文件",
              "publish_time": "2026-09-01"}
    kwargs.update(overrides)
    return parse_text.parse_text_file(path, **kwargs)


def test_txt_utf8_bom_is_removed_and_raw_shape_matches_fetch(tmp_path):
    path = _write(tmp_path, "公告.txt", "﻿贵州茅台发布公告，内容为测试。")

    record = _parse(path, company_list=["600519", "  "])

    assert set(record) == RAW_KEYS, "raw 记录字段必须与 fetch.Doc.to_raw() 对齐"
    assert record["raw_text"] == "贵州茅台发布公告，内容为测试。", "BOM 必须去掉，正文不得改写"
    assert record["title"] == "公告", "txt 缺省标题取文件名（不含扩展名）"
    assert record["company_list"] == ["600519"], "公司代码去空白、丢空项"
    assert record["extract_method"] == "txt_plain"
    assert record["http_status"] is None and record["page_url"] == ""
    assert record["byte_size"] == len(record["raw_text"].encode("utf-8"))
    assert record["meta"]["text_encoding"] == "utf-8-sig"
    assert record["meta"]["source_file"] == "公告.txt"


def test_markdown_title_from_first_heading_and_content_preserved(tmp_path):
    path = _write(tmp_path, "通知.md",
                  "前言\n\n# 关于测试的通知\n\n正文保留 **Markdown** 标记。\n")

    record = _parse(path, title=None)

    assert record["title"] == "关于测试的通知"
    assert record["extract_method"] == "md_plain"
    assert "**Markdown**" in record["raw_text"], "不做 Markdown 清洗，原样保留"
    assert record["raw_text"].startswith("前言")


def test_gb18030_fallback(tmp_path):
    path = _write(tmp_path, "legacy.txt", "监管公开信息：测试", encoding="gb18030")

    text, encoding = parse_text.read_text(path)

    assert text == "监管公开信息：测试"
    assert encoding == "gb18030", "UTF-8 解码失败后应回退到 GB18030"
    assert _parse(path)["raw_text"] == "监管公开信息：测试"


def test_required_metadata_is_not_fabricated(tmp_path):
    path = _write(tmp_path, "a.txt", "正文")

    with pytest.raises(ValueError, match="category"):
        _parse(path, category="不存在的类别")
    with pytest.raises(ValueError, match="source"):
        _parse(path, source="  ")
    with pytest.raises(ValueError, match="publish_time"):
        _parse(path, publish_time="")
    with pytest.raises(ValueError, match="doc_id"):
        _parse(path, doc_id=0)
    with pytest.raises(ValueError, match="只支持"):
        _parse(_write(tmp_path, "a.json", "{}"))


def test_write_raw_document_is_fetch_compatible_and_refuses_overwrite(tmp_path):
    path = _write(tmp_path, "公告.txt", "正文")
    record = _parse(path, doc_id=9201)

    out = parse_text.write_raw_document(str(tmp_path), record)

    assert out == os.path.join(str(tmp_path), "raw", "9201.json")
    with open(out, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert set(loaded) == RAW_KEYS and loaded["doc_id"] == 9201
    with pytest.raises(FileExistsError):
        parse_text.write_raw_document(str(tmp_path), record)
    assert parse_text.write_raw_document(str(tmp_path), record, overwrite=True) == out


def test_cli_prints_json_without_writing_dataset(tmp_path, capsys):
    path = _write(tmp_path, "通知.md", "# 标题\n正文")
    code = parse_text.main(["--file", path, "--doc-id", "9301",
                            "--category", cfg.CATEGORIES[-1], "--source", "本地文件",
                            "--publish-time", "2026-09-02"])

    assert code == 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["doc_id"] == 9301 and payload["title"] == "标题"
    assert not (tmp_path / "raw").exists(), "未给 --out-root 时不得写盘"
