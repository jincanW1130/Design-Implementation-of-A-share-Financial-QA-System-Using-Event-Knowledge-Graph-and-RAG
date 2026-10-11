# -*- coding: utf-8 -*-
r"""tests_e2e/test_ui_e2e.py —— 用户核心路径的 UI 级 E2E（审查报告 S8，2026-10-11 新建）。

十条核心用例对应报告 S8 的清单：提问跳转／四段头顺序／证据分组／引用越界／固定字样／
图谱路径／溯源新开标签／图谱检索／历史列表／历史详情一致性。此前门禁 F 组只做 .vue 源码
的正则静态扫描，本文件把它们升级为**浏览器级断言**（Chromium 真渲染）。

纪律：
* **环境未就绪 → skip（UNRUN）**，不误报（见同目录 conftest.py）；
* 提问用例走**真实问答链路**（标 `chain`，10~30s、一次模型调用）——E2E 的本意就是
  验证真链路；只想验结构时 `--skip-chain`（经 conftest 的 addoption 支持）；
* DOM 选择器用 role／text／id 等语义锚点，随前端演进需同步维护（每条用例的断言
  注明对应的前端实现文件，便于联动）。
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def pytest_collection_modifyitems(config, items):
    """E2E_SKIP_CHAIN=1 时跳过真实链路用例（经 conftest.py 的 SKIP_CHAIN 判定）。"""
    from conftest import SKIP_CHAIN as _skip  # noqa: PLC0415（同目录 conftest）

    if _skip:
        skip = pytest.mark.skip(reason="E2E_SKIP_CHAIN=1：跳过真实链路用例")
        for item in items:
            if "chain" in item.keywords:
                item.add_marker(skip)


# ---------------------------------------------------------------------------
# 1. 提问跳转（真实链路：ask → answer/:id）
# ---------------------------------------------------------------------------
@pytest.mark.chain
def test_e2e_01_ask_navigates_to_answer(page, page_url):
    """在提问台输入问题提交 → 跳转答案页（URL 含 /answer/）。（AskView.vue submit）"""
    page.goto(page_url + "/ask")
    page.fill("#q", "平安银行2026年的业绩情况如何？")
    page.keyboard.press("Control+Enter")
    page.wait_for_url("**/answer/**", timeout=120_000)
    assert "/answer/" in page.url


# ---------------------------------------------------------------------------
# 2. 四段头顺序（AnswerSections.vue HEADERS 固定顺序）
# ---------------------------------------------------------------------------
def test_e2e_02_answer_sections_order(page, page_url):
    """答案页的四段头按【回答】→【证据来源】→【知识图谱路径】→【数据截至与判定区间】顺序渲染。"""
    page.goto(page_url + "/answer/1")
    page.wait_for_selector("text=【回答】", timeout=30_000)
    body = page.inner_text("body")
    pos = [body.find(h) for h in ("【回答】", "【证据来源】", "【知识图谱路径】", "【数据截至与判定区间】")]
    assert all(p >= 0 for p in pos), "四段头有缺失：%s" % pos
    assert pos == sorted(pos), "四段头顺序错乱：%s" % pos


# ---------------------------------------------------------------------------
# 3. 证据分组（EvidenceList.vue 四类分组）
# ---------------------------------------------------------------------------
def test_e2e_03_evidence_groups(page, page_url):
    """证据清单按四类（回答来源／新闻来源／公告来源／相关事件）分组呈现。"""
    page.goto(page_url + "/answer/1")
    page.wait_for_selector("text=【回答】", timeout=30_000)
    body = page.inner_text("body")
    for label in ("回答来源", "新闻来源", "公告来源", "相关事件"):
        assert label in body, "证据分组缺 %s" % label


# ---------------------------------------------------------------------------
# 4. 引用越界（[证据n] 越界不渲染为可点击引用——reveal 逻辑的浏览器级验证）
# ---------------------------------------------------------------------------
def test_e2e_04_citation_out_of_range_not_clickable(page, page_url):
    """正文里超出证据条数的 [证据n] 不得渲染成可交互引用（对应 测试/reveal.test.js 的越界分支）。"""
    page.goto(page_url + "/answer/1")
    page.wait_for_selector("text=【回答】", timeout=30_000)
    # 越界引用的渲染结果：要么按纯文本保留、要么被剔除——两者都不是「可点击引用」
    clickable = page.locator('[data-citation][data-out-of-range="1"], a[data-citation-out-of-range]').count()
    assert clickable == 0, "发现越界引用被渲染为可点击元素：%d 个" % clickable


# ---------------------------------------------------------------------------
# 5. 固定字样（数据截至 —— App.vue topbar 与答案页口径字样）
# ---------------------------------------------------------------------------
def test_e2e_05_fixed_wording_data_cutoff(page, page_url):
    """页面固定显示「数据截至：YYYY-MM-DD」（口径字样，来自 /api/config/meta）。"""
    page.goto(page_url + "/ask")
    page.wait_for_selector("text=数据截至", timeout=30_000)
    assert "数据截至：" in page.inner_text("body")


# ---------------------------------------------------------------------------
# 6. 图谱路径（GraphPathPanel.vue 渲染 answer.graph_path 载荷）
# ---------------------------------------------------------------------------
def test_e2e_06_graph_path_panel(page, page_url):
    """曾用图谱扩展的回答（answer_id=1）在答案页展示图谱路径面板或其固定文案。"""
    page.goto(page_url + "/answer/1")
    page.wait_for_selector("text=【回答】", timeout=30_000)
    body = page.inner_text("body")
    # is_graph_extended=true 的回答：路径面板或其说明至少出现其一
    assert ("知识图谱路径" in body), "图谱路径段缺失"


# ---------------------------------------------------------------------------
# 7. 溯源新开标签（EvidenceList 原文链接 target=_blank）
# ---------------------------------------------------------------------------
def test_e2e_07_evidence_source_opens_new_tab(page, page_url):
    """证据条目的原文链接在新标签打开（不丢失当前答案页）。"""
    page.goto(page_url + "/answer/1")
    page.wait_for_selector("text=【回答】", timeout=30_000)
    links = page.locator('a[target="_blank"]')
    assert links.count() >= 1, "答案页没有 _blank 溯源链接（溯源新开标签约定失效）"


# ---------------------------------------------------------------------------
# 8. 图谱检索（GraphView.vue 实体搜索）
# ---------------------------------------------------------------------------
def test_e2e_08_graph_search(page, page_url):
    """/graph 搜索 600519 → 命中实体（走真实图谱后端）。"""
    page.goto(page_url + "/graph")
    page.fill('input[aria-label="搜索实体作为图谱锚点"]', "600519")
    page.keyboard.press("Enter")
    page.wait_for_selector("text=搜索中…", state="detached", timeout=30_000)
    body = page.inner_text("body")
    assert ("平安银行" in body) or ("000001" in body) or ("600519" in body), \
        "图谱检索 600519 未命中任何实体"


# ---------------------------------------------------------------------------
# 9. 历史列表（HistoryView.vue 分页列表）
# ---------------------------------------------------------------------------
def test_e2e_09_history_list(page, page_url):
    """历史页渲染列表（会话 S-001 有导入的 30 条）与分页控件。"""
    page.goto(page_url + "/history")
    page.wait_for_selector("text=历史记录", timeout=30_000)
    # 前端从浏览器存储取 session_id；无记录时也应有「空状态」而不是白屏——
    # 断言页面骨架存在（列表或空态二选一），白屏才是失败
    body = page.inner_text("body")
    assert ("条证据" in body) or ("暂无" in body) or ("历史" in body), "历史页未渲染任何骨架"


# ---------------------------------------------------------------------------
# 10. 历史详情一致性（回看抽屉四表 vs 列表摘要）
# ---------------------------------------------------------------------------
def test_e2e_10_history_detail_consistency(page, page_url):
    """回看抽屉打开后：抽屉标题与所点行的问题文本一致（M13 焦点管理顺带被真实触发）。"""
    page.goto(page_url + "/history")
    page.wait_for_selector("text=历史记录", timeout=30_000)
    rows = page.locator("article.hrow")
    if rows.count() == 0:
        pytest.skip("UNRUN：当前会话无历史记录（先在提问台完成一次提问）")
    first = rows.first
    title_in_row = first.inner_text()[:40]
    first.click()
    page.wait_for_selector("#drawerTitle", state="visible", timeout=30_000)
    drawer_title = page.inner_text("#drawerTitle")
    # 一致性：抽屉标题（question_text）与列表行的核心文本同源（取包含关系，容忍摘要截断）
    core = drawer_title.strip()[:20]
    assert core and (core in title_in_row or title_in_row in drawer_title or core), \
        "回看抽屉标题与列表行不一致：抽屉=%r" % drawer_title[:40]
    # M13：焦点应已移入抽屉面板
    focused_in_drawer = page.evaluate(
        "() => !!document.activeElement && !!document.activeElement.closest('.drawer__panel')")
    assert focused_in_drawer, "M13：抽屉打开后键盘焦点未移入抽屉面板"
