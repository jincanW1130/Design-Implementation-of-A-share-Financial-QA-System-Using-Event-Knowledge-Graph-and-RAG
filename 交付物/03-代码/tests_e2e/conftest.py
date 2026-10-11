# -*- coding: utf-8 -*-
r"""tests_e2e/conftest.py —— UI 级 E2E 的环境门与 UNRUN 语义（审查报告 S8，2026-10-11 新建）。

三条环境纪律：

1. **未安装 Playwright → 全部 skip（不误报失败）**：模块收集期 `pytest.importorskip`，
   主套件（运行测试.ps1）照常全绿——E2E 是独立资产，不绑架 283 例主回归。
2. **服务未就绪 → skip 并注明 UNRUN**：与门禁 UNRUN 语义一致（环境未就绪≠内容失败）：
   后端 /api/health 不可达、前端 dev server 不可达，一律 skip 而非 FAIL。
3. **真实链路用例单独标记**：提问走真实问答链路（10~30s、消耗一次模型调用），标
   `@pytest.mark.chain`；默认全跑，只想跑结构用例时 `--skip-chain`。

运行（独立于主套件）::

    pip install playwright && playwright install chromium     # 一次性环境准备
    python -m pytest 交付物/03-代码/测试/tests_e2e -q          # 后端 8000 ＋ 前端 5173 需在跑

闭环标准（报告 S8）：全绿环境（MySQL＋Neo4j＋后端＋前端）**10/10 通过**；
环境未就绪按 UNRUN 语义 skip、不误报。
"""

from __future__ import annotations

import os
import urllib.request

import pytest

pytest.importorskip("playwright", reason="UNRUN：未安装 playwright（pip install playwright && playwright install chromium）")

BACKEND = os.environ.get("E2E_BACKEND", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("E2E_FRONTEND", "http://127.0.0.1:5173")
SKIP_CHAIN = os.environ.get("E2E_SKIP_CHAIN", "") not in ("", "0", "false", "False")
"""跳过真实链路用例：设环境变量 E2E_SKIP_CHAIN=1（不用命令行选项——pytest 只允许
rootdir 的 conftest 定义选项，本目录在主套件下是子目录，命令行参数会破坏主套件收集）。"""


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: UI 级端到端用例（tests_e2e 专用标记）")
    config.addinivalue_line("markers", "chain: 走真实问答链路的用例（E2E_SKIP_CHAIN=1 可跳过）")


def _alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return resp.status < 500
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    """服务探活：后端或前端不可达 → 全部用例 skip（UNRUN 语义，不误报）。"""
    if not items:
        return
    if not _alive(BACKEND + "/api/health"):
        skip = pytest.mark.skip(reason="UNRUN：后端 %s 不可达（python 交付物/03-代码/后端/run.py）" % BACKEND)
        for item in items:
            item.add_marker(skip)
        return
    if not _alive(FRONTEND):
        skip = pytest.mark.skip(reason="UNRUN：前端 %s 不可达（npm run dev）" % FRONTEND)
        for item in items:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def page_url():
    """前端基地址。"""
    return FRONTEND


@pytest.fixture()
def page(page_url):
    """每个用例一个独立页面（Chromium；无头）。"""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.set_default_timeout(15000)
        yield page
        context.close()
        browser.close()
