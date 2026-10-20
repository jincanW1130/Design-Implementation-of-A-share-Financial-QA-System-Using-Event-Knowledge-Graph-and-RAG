# -*- coding: utf-8 -*-
"""把本目录全部 SVG 渲染为 PNG。

管线与既有图一致：手写 SVG → Playwright（msedge 无头）→ PNG；
白底、device_scale_factor＝3.5、Microsoft YaHei、不联网、不起本地服务。

用法：python "交付物/09-图表/评优补图/_渲染.py"
"""

import re
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SCALE = 3.5
SIZE_RE = re.compile(r'<svg[^>]*width="(\d+)"[^>]*height="(\d+)"')


def render(png_path, svg_path, width, height):
    svg_text = svg_path.read_text(encoding="utf-8")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#ffffff}</style>"
        "</head><body>" + svg_text + "</body></html>"
    )
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            device_scale_factor=SCALE,
        )
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(400)
        page.screenshot(path=str(png_path), full_page=False)
        browser.close()


def main():
    svgs = sorted(HERE.glob("*.svg"))
    if not svgs:
        raise SystemExit("目录中没有 SVG：%s" % HERE)
    for svg_path in svgs:
        m = SIZE_RE.search(svg_path.read_text(encoding="utf-8"))
        if not m:
            raise SystemExit("SVG 缺少 width/height：%s" % svg_path.name)
        width, height = int(m.group(1)), int(m.group(2))
        png_path = svg_path.with_suffix(".png")
        render(png_path, svg_path, width, height)
        print("已渲染：%s  (%dx%d @%.1fx → %dx%d)" % (
            png_path.name, width, height, SCALE,
            round(width * SCALE), round(height * SCALE)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
