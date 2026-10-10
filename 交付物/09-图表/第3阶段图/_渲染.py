# -*- coding: utf-8 -*-
"""渲染 `图3-1-系统用例图.svg` → `图3-1-系统用例图.png`（可复现；本目录内一条命令）。

口径（与 `交付物/09-图表/第4阶段图/README.md` 的渲染通道一致）：
  * 本机 Python playwright（msedge 通道、无头）＋ 系统字体（Microsoft YaHei）；
  * 画布＝SVG 自然尺寸（1240 × 1170 css px），deviceScaleFactor = 3.5；
  * 白底不透明；图题已绘在 SVG 内（PNG 自带图题）；
  * 渲染过程**不联网、不起本地服务**（file:// 与内联内容均不使用外部资源）。

用法：
    python "交付物/09-图表/第3阶段图/_渲染.py"
退出码 0 ＝ 已写出 PNG；非 0 ＝ 失败（不写盘）。
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SVG = HERE / "图3-1-系统用例图.svg"
PNG = HERE / "图3-1-系统用例图.png"

WIDTH, HEIGHT = 1240, 1170          # 与 SVG 的 width/height 属性一致
SCALE = 3.5                         # 与第 4 阶段 8 张图的统一 DPR 一致


def main() -> int:
    if not SVG.is_file():
        print("缺少 SVG 源文件：%s" % SVG)
        return 2
    svg_text = SVG.read_text(encoding="utf-8")
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#ffffff}</style>"
        "</head><body>" + svg_text + "</body></html>"
    )
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        print("playwright 不可用：%r" % exc)
        return 3

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        context = browser.new_context(
            viewport={"width": WIDTH, "height": HEIGHT},
            device_scale_factor=SCALE,
        )
        page = context.new_page()
        page.set_content(html, wait_until="load")
        page.wait_for_timeout(400)          # 等字体就绪后再截图
        page.screenshot(path=str(PNG), full_page=False)
        browser.close()

    print("已写出：%s（%d 字节）" % (PNG, os.path.getsize(PNG)))
    print("预期像素：%d × %d（css %d × %d，DPR %s）"
          % (WIDTH * SCALE, HEIGHT * SCALE, WIDTH, HEIGHT, SCALE))
    return 0


if __name__ == "__main__":
    sys.exit(main())