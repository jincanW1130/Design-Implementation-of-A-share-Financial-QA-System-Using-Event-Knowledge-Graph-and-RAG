# -*- coding: utf-8 -*-
"""门禁计数的负向标定（独立审查 2026-10-19）。

原实现只从 pytest/Vitest 输出里抓 `N passed`，不看 skipped；当真实服务不可达时
`test_t_real_services_readonly.py` 会跳过，530 passed + 6 skipped 仍被判定为门禁通过。
本文件直接测计数解析与门禁判定函数，复现并钉住该假绿路径。
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("oneclick_gate", ROOT / "工具" / "一键构建.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)


def test_pytest_counts_parsed_from_realistic_lines():
    counts = GATE.parse_pytest_counts(
        "536 passed, 2 warnings in 181.42s (0:03:01)\n")
    assert counts == {"passed": 536, "skipped": 0, "failed": 0, "errors": 0}

    counts = GATE.parse_pytest_counts("1 failed, 535 passed, 6 skipped in 12.00s\n")
    assert counts["passed"] == 535
    assert counts["failed"] == 1
    assert counts["skipped"] == 6


def test_negative_calibration_530_passed_6_skipped_must_not_pass():
    """复现修复前的假绿：达到旧阈值 530 但存在 6 个 skip。"""
    counts = GATE.parse_pytest_counts("530 passed, 6 skipped in 9.00s\n")
    problem = GATE.backend_gate_error(counts)
    assert problem is not None
    assert "skipped" in problem


def test_backend_gate_enforces_new_threshold_and_zero_skip():
    assert GATE.backend_gate_error({"passed": 536, "skipped": 0, "failed": 0, "errors": 0}) is None
    assert GATE.backend_gate_error({"passed": 535, "skipped": 0, "failed": 0, "errors": 0}) is not None
    assert GATE.backend_gate_error({"passed": 900, "skipped": 1, "failed": 0, "errors": 0}) is not None
    assert GATE.backend_gate_error({"passed": 0, "skipped": 0, "failed": 0, "errors": 2}) is not None


def test_vitest_counts_parsed_and_skip_is_rejected():
    counts = GATE.parse_vitest_counts(
        " Test Files  5 passed (5)\n      Tests  81 passed (81)\n")
    assert counts == {"passed": 81, "skipped": 0, "failed": 0}
    assert GATE.frontend_gate_error(counts) is None

    skipped = GATE.parse_vitest_counts(
        " Test Files  5 passed (5)\n      Tests  80 passed | 1 skipped (81)\n")
    assert skipped["passed"] == 80
    assert skipped["skipped"] == 1
    assert GATE.frontend_gate_error(skipped) is not None

    below = GATE.parse_vitest_counts("      Tests  74 passed (74)\n")
    assert GATE.frontend_gate_error(below) is not None
