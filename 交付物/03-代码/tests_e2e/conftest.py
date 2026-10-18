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
import time
import urllib.request

import pytest

pytest.importorskip("playwright", reason="UNRUN：未安装 playwright（pip install playwright && playwright install chromium）")

BACKEND = os.environ.get("E2E_BACKEND", "http://127.0.0.1:8000")
FRONTEND = os.environ.get("E2E_FRONTEND", "http://127.0.0.1:5173")
@pytest.fixture(scope="session", autouse=True)
def _rate_window_guard():
    """**限流窗口守卫**（2026-10-18 第二轮第 8 轮补）。

    2026-10-18 实测：把 `E2E_PACE_MS` 调到 500～1500 跑快档时，一个 60 秒窗口内
    的请求数会超过后端默认的 60 次上限，`POST /api/qa/ask` 拿到 **429/1004**；
    前端会按 `Retry-After` 自动重试并等待，于是 `test_e2e_01` 等到 120 秒超时——
    **看起来像功能坏了，实际是限流**。

    这里在整轮用例开始前探一次：若窗口已满（`/api/config/meta` 返回 429），
    先睡过一个窗口再跑，并在终端说明原因。真正断言限流行为的用例仍由
    `验收第9阶段.py`（C9）负责，本守卫不改变任何功能判据。
    """
    import time, urllib.error, urllib.request
    backend = BACKEND
    def _hit():
        try:
            with urllib.request.urlopen(backend + "/api/config/meta", timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:
            return None
    if _hit() == 429:
        print("\n[E2E] 限流窗口已满（429），等待 61 秒后继续；如需跑快档请先放宽 "
              "ASHARE_RATE_LIMIT_MAX 或提高 E2E_PACE_MS。", flush=True)
        time.sleep(61)
        if _hit() == 429:
            pytest.skip("UNRUN：限流窗口持续满载，判定环境未就绪（非功能失败）")


SKIP_CHAIN = os.environ.get("E2E_SKIP_CHAIN", "") not in ("", "0", "false", "False")
"""跳过真实链路用例：设环境变量 E2E_SKIP_CHAIN=1（不用命令行选项——pytest 只允许
rootdir 的 conftest 定义选项，本目录在主套件下是子目录，命令行参数会破坏主套件收集）。"""

# ---------------------------------------------------------------------------
# 用例间隔（2026-10-18 新增，与 UAT 装置 `--pace` 同口径）
#
# 为什么要有：每个用例都会新开浏览器上下文并整页加载，单页约 13～20 次 `/api/*`；
# 10 个用例连着跑，60 秒窗口内就会逼近后端「60 次／60 秒／来源 IP」的上限，于是后段用例
# 会拿到 429，页面显示「读取失败[1004]」，断言随之失败——那测的是装置的爆发速度，
# 不是页面正确性（实测复现过：同一套用例单跑 10/10，紧接另一轮跑则出现 429 连带失败）。
#
# 默认 15000 ms（≈10 个用例 × 15 s，把整轮摊到约 2.5 分钟，折合每分钟约 50 次请求）；
# 设 `E2E_PACE_MS=0` 可关掉配速、按原样复现「密集爆发」。
# ---------------------------------------------------------------------------
try:
    PACE_MS = int(os.environ.get("E2E_PACE_MS", "15000"))
except ValueError:
    PACE_MS = 15000

_LAST_END = {"t": 0.0}


def pytest_runtest_setup(item):
    """兜住用例之间的间隔：距上一个用例结束不足 PACE_MS 就补足。"""
    if PACE_MS <= 0 or not _LAST_END["t"]:
        return
    gap_ms = (time.monotonic() - _LAST_END["t"]) * 1000.0
    if gap_ms < PACE_MS:
        time.sleep((PACE_MS - gap_ms) / 1000.0)


def pytest_runtest_teardown(item, nextitem):
    _LAST_END["t"] = time.monotonic()


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
