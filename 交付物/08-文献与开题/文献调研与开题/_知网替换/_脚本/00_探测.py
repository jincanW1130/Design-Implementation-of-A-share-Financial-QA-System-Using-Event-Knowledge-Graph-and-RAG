# -*- coding: utf-8 -*-
"""探测：用 Playwright 无头浏览器渲染知网空间检索结果页，确认结果条目可读。

不使用任何账号、不提交任何凭据、不点击下载链接。
"""
from __future__ import annotations

import sys
import time
from urllib.parse import quote

from playwright.sync_api import sync_playwright

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

QUERY = "金融事件抽取"
URL = "https://search.cnki.com.cn/Search/Result?content=" + quote(QUERY)


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            )
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(6000)
        html = page.content()
        print("URL:", URL)
        print("HTML_LEN:", len(html))
        # 结果条目选择器探测
        for sel in [".list-item", "div.list-item", "p.tit", ".resultlist", "#listresult"]:
            try:
                n = page.locator(sel).count()
            except Exception as exc:  # noqa: BLE001
                n = f"ERR {exc}"
            print("selector", sel, "->", n)
        try:
            txt = page.locator(".list-item").first.inner_text()
            print("FIRST_ITEM_TEXT:\n", txt[:800])
        except Exception as exc:  # noqa: BLE001
            print("first item error:", exc)
        import re

        m = re.search(r"共找到[约]?\s*([\d,]+)\s*条", html)
        print("TOTAL:", m.group(1) if m else "N/A")
        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
