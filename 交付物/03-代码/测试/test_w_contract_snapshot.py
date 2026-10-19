# -*- coding: utf-8 -*-
"""W 组 · 契约快照操作级负向标定（独立审查 2026-10-19 P2-8）。

直接对**已登记快照**的内存副本注入变化，断言 `diff_contract()` 能检出：
查询参数改名、请求体 schema 变化、schema 必填变化、security 声明删除、2xx 状态码删除。
不装配应用、不联网、不修改快照文件。
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "contract_snapshot", ROOT / "工具" / "契约快照.py")
SNAP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SNAP)

SNAPSHOT_PATH = ROOT / "交付物" / "03-代码" / "后端" / "_契约快照.json"


def _load() -> dict:
    with open(SNAPSHOT_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _mutated() -> dict:
    return copy.deepcopy(_load())


def test_snapshot_is_operation_level_and_compact():
    snap = _load()
    assert snap["snapshot_level"] == "operation"
    assert snap["operation_contract"]
    assert SNAPSHOT_PATH.stat().st_size < 1024 * 1024


def test_unchanged_snapshot_has_no_diff():
    snap = _load()
    assert SNAP.diff_contract(snap, _mutated()) == []


def test_query_parameter_rename_is_detected():
    old = _load()
    new = _mutated()
    params = new["operation_contract"]["GET /api/search/keywords"]["parameters"]
    target = next(item for item in params if item["name"] == "q")
    target["name"] = "query_text"

    diffs = SNAP.diff_contract(old, new)
    assert diffs
    assert any("GET /api/search/keywords" in line and "parameters" in line for line in diffs)


def test_request_body_schema_change_is_detected():
    old = _load()
    new = _mutated()
    body = new["operation_contract"]["POST /api/qa/ask"]["request_body"]
    assert body is not None and body["content"]["application/json"]
    body["content"]["application/json"] = {"type": "string"}

    diffs = SNAP.diff_contract(old, new)
    assert diffs
    assert any("POST /api/qa/ask" in line and "request_body" in line for line in diffs)


def test_schema_required_change_is_detected():
    old = _load()
    new = _mutated()
    new["schema_fields"]["ValidationError"]["required"].append("__probe__")

    diffs = SNAP.diff_contract(old, new)
    assert diffs
    assert any("schema_fields.ValidationError" in line for line in diffs)


def test_security_removal_is_detected():
    old = _load()
    new = _mutated()
    new["operation_contract"]["POST /api/admin/documents"]["security"] = []

    diffs = SNAP.diff_contract(old, new)
    assert diffs
    assert any("POST /api/admin/documents" in line and "security" in line for line in diffs)


def test_success_status_removal_is_detected():
    old = _load()
    new = _mutated()
    success = new["operation_contract"]["GET /api/health"]["success_responses"]
    assert "200" in success["responses"]
    del success["responses"]["200"]
    success["statuses"] = sorted(success["responses"])
    success["present"] = bool(success["responses"])

    diffs = SNAP.diff_contract(old, new)
    assert diffs
    assert any("GET /api/health" in line and "success_responses" in line for line in diffs)
