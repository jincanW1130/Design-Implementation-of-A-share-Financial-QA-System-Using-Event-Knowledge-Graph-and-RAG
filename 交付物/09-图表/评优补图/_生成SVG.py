# -*- coding: utf-8 -*-
"""生成「评优补图」5 张自包含 SVG（不联网、零外链）。

图号与数据出处（逐项可回查，生成脚本内不重算任何指标）：
  图 4-9   核心类图（后端服务与检索组件）—— 类名/方法名取自
           `交付物/03-代码/后端/{services/qa_service.py,cache.py,errors.py,observability.py}`、
           `交付物/03-代码/检索/{pipeline.py,vector_search.py}`、
           `交付物/03-代码/增强/{lexical_search.py,hybrid_retrieval.py,reranker.py}`
  图 4-10  提问到答案的核心时序图 —— 调用链取自 `api/qa.py`、`services/qa_service.py`、
           `问答/run_answer.py`、`检索/run_query.py`、`检索/pipeline.py`、`问答/assemble.py`、
           `问答/answer.py`
  图 6-1   核心 108 题五组四项指标 —— 第六章表 6-7（核心 108 题四项检索指标）
  图 6-2   逐子集完整证据召回 —— 第六章表 6-11／6-12／6-13 的 Complete Evidence Recall@K 行
  图 6-3   问答链路耗时分解 —— 第六章表 6-4（问答响应时间分段，n＝30）

用法：python "交付物/09-图表/评优补图/_生成SVG.py"
输出：同目录 5 个 .svg（UTF-8、LF、自包含）。
"""

from pathlib import Path

HERE = Path(__file__).resolve().parent
FONT = "Microsoft YaHei, PingFang SC, sans-serif"

INK = "#263238"
INK2 = "#37474F"
MUTED = "#607D8B"
LINE = "#78909C"
BOX = "#FAFBFC"
EDGE = "#546E7A"
BROWN = "#8D6E63"
WARN_FILL = "#FFFDE7"
WARN_EDGE = "#BCAAA4"


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def svg_open(w, h):
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="%s">\n'
        '<rect x="0" y="0" width="%d" height="%d" fill="#FFFFFF"/>\n'
        % (w, h, w, h, FONT, w, h)
    )


def svg_close():
    return "</svg>\n"


def text(x, y, s, size=13, anchor="start", weight="normal", fill=INK,
         rotate=None, italic=False, opacity=None):
    extra = ""
    if rotate is not None:
        extra += ' transform="rotate(%s %s %s)"' % (rotate, x, y)
    if italic:
        extra += ' font-style="italic"'
    if opacity is not None:
        extra += ' opacity="%s"' % opacity
    return (
        '<text x="%s" y="%s" text-anchor="%s" font-size="%s" font-weight="%s" '
        'fill="%s"%s>%s</text>\n'
        % (x, y, anchor, size, weight, fill, extra, esc(s))
    )


def rect(x, y, w, h, fill="none", stroke=LINE, sw=1.4, rx=0, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    return (
        '<rect x="%s" y="%s" width="%s" height="%s" rx="%s" fill="%s" '
        'stroke="%s" stroke-width="%s"%s/>\n'
        % (x, y, w, h, rx, fill, stroke, sw, d)
    )


def line(x1, y1, x2, y2, stroke=EDGE, sw=1.4, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    return (
        '<line x1="%s" y1="%s" x2="%s" y2="%s" stroke="%s" stroke-width="%s"%s/>\n'
        % (x1, y1, x2, y2, stroke, sw, d)
    )


def poly(points, fill="none", stroke=EDGE, sw=1.4, dash=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    pts = " ".join("%s,%s" % (p[0], p[1]) for p in points)
    return (
        '<polyline points="%s" fill="%s" stroke="%s" stroke-width="%s"%s/>\n'
        % (pts, fill, stroke, sw, d)
    )


def _unit(x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    n = (dx * dx + dy * dy) ** 0.5
    if n == 0:
        return 0.0, 0.0
    return dx / n, dy / n


def _perp(ux, uy):
    return -uy, ux


def arrow_head(x1, y1, x2, y2, color=EDGE, size=10, filled=True, open_triangle=False):
    """在 (x2,y2) 处画箭头；filled=False 为返回用开放箭头。"""
    ux, uy = _unit(x1, y1, x2, y2)
    px, py = _perp(ux, uy)
    bx, by = x2 - ux * size, y2 - uy * size
    lx, ly = bx + px * size * 0.46, by + py * size * 0.46
    rx, ry = bx - px * size * 0.46, by - py * size * 0.46
    if open_triangle:
        pts = "%s,%s %s,%s %s,%s" % (x2, y2, lx, ly, rx, ry)
        return ('<polygon points="%s" fill="#FFFFFF" stroke="%s" stroke-width="1.3"/>\n'
                % (pts, color))
    fill = color if filled else "#FFFFFF"
    return ('<polygon points="%s,%s %s,%s %s,%s" fill="%s" stroke="%s" '
            'stroke-width="1.2"/>\n' % (x2, y2, lx, ly, rx, ry, fill, color))


def arrow(x1, y1, x2, y2, dashed=False, color=EDGE, sw=1.4, filled=True,
          open_triangle=False, label=None, lx=None, ly=None, lsize=11,
          lanchor="middle", lrotate=None, lfill=INK2):
    dash = "7,5" if dashed else None
    out = line(x1, y1, x2, y2, stroke=color, sw=sw, dash=dash)
    out += arrow_head(x1, y1, x2, y2, color=color, filled=filled,
                      open_triangle=open_triangle)
    if label:
        if lx is None:
            lx = (x1 + x2) / 2
        if ly is None:
            ly = (y1 + y2) / 2 - 6
        out += text(lx, ly, label, size=lsize, anchor=lanchor, fill=lfill,
                    rotate=lrotate)
    return out


def ortho_arrow(points, dashed=True, color=EDGE, sw=1.4, label=None,
                lx=None, ly=None, lsize=10.5, lanchor="middle", lrotate=None,
                lfill=INK2):
    dash = "7,5" if dashed else None
    out = poly(points, fill="none", stroke=color, sw=sw, dash=dash)
    (x1, y1) = points[-2]
    (x2, y2) = points[-1]
    out += arrow_head(x1, y1, x2, y2, color=color, filled=True)
    if label:
        out += text(lx, ly, label, size=lsize, anchor=lanchor, fill=lfill,
                    rotate=lrotate)
    return out


# =====================================================================
# 图 6-1　核心 108 题五组四项指标对比
# =====================================================================

def fig_6_1():
    W, H = 1280, 820
    groups = ["A", "B", "C", "D", "E"]
    recall = [0.776144, 0.877358, 0.873016, 0.847619, 0.847619]
    complete = [0.715686, 0.820755, 0.809524, 0.790476, 0.790476]
    mrr = [0.585224, 0.611253, 0.607551, 0.604588, 0.547653]
    precision = [0.106863, 0.121698, 0.120000, 0.118095, 0.118095]
    c_r, c_c, c_m, c_p = "#4E79A7", "#76A7C8", "#A9C6DB", BROWN

    out = svg_open(W, H)
    out += text(W / 2, 78,
                "核心 108 题；K＝10；分母为各组有效题数 102／106／105／105／105",
                size=13, anchor="middle", fill=MUTED)
    out += text(95, 112,
                "注：表 6-7 未给 Hit@1；本图第四项取表中的 Precision@K。四项指标均为 0～1 的无量纲比值。",
                size=11.5, fill=MUTED)

    # ---- 左栏：R@10 / Complete@10 / MRR
    ax1, ay0, ay1 = 95, 650, 170
    out += line(ax1, ay0, ax1, ay1, stroke=INK2, sw=1.2)
    out += line(ax1, ay0, 760, ay0, stroke=INK2, sw=1.2)
    for i in range(6):
        v = i / 5
        y = ay0 - v * (ay0 - ay1)
        out += line(ax1 - 5, y, ax1, y, stroke=INK2, sw=1.2)
        out += text(ax1 - 10, y + 4, "%.1f" % v, size=11.5, anchor="end", fill=INK2)
    out += text(38, (ay0 + ay1) / 2, "指标取值（0～1）", size=12, anchor="middle",
                fill=INK2, rotate=-90)
    out += text(95, 136, "(a) Recall@10、Complete@10 与 MRR", size=14,
                weight="bold", fill=INK2)

    # 图例
    lx = 430
    for color, label in ((c_r, "Recall@10"), (c_c, "Complete@10"), (c_m, "MRR")):
        out += rect(lx, 147, 13, 13, fill=color, stroke=color, sw=0.8)
        out += text(lx + 18, 158, label, size=11.5, fill=INK2)
        lx += 110

    centers1 = [161.5, 294.5, 427.5, 560.5, 693.5]
    series = [(recall, c_r), (complete, c_c), (mrr, c_m)]
    for gi, cx in enumerate(centers1):
        for si, (vals, color) in enumerate(series):
            v = vals[gi]
            x = cx - 51 + si * 36
            y = ay0 - v * (ay0 - ay1)
            out += rect(x, y, 30, ay0 - y, fill=color, stroke=color, sw=0.8)
            out += text(x + 15, y - 6, "%.6f" % v, size=9.2, anchor="start",
                        fill=INK, rotate=-90)
        out += text(cx, 674, groups[gi], size=14, anchor="middle", weight="bold",
                    fill=INK2)

    # ---- 右栏：Precision@10（量级较小，单独一栏）
    ax2, px1 = 850, 1180
    out += line(ax2, ay0, ax2, ay1, stroke=INK2, sw=1.2)
    out += line(ax2, ay0, px1, ay0, stroke=INK2, sw=1.2)
    for i in range(4):
        v = i * 0.05
        y = ay0 - (v / 0.15) * (ay0 - ay1)
        out += line(ax2 - 5, y, ax2, y, stroke=INK2, sw=1.2)
        out += text(ax2 - 10, y + 4, "%.2f" % v, size=11.5, anchor="end", fill=INK2)
    out += text(800, (ay0 + ay1) / 2, "指标取值（0～1）", size=12, anchor="middle",
                fill=INK2, rotate=-90)
    out += text(850, 136, "(b) Precision@10", size=14, weight="bold", fill=INK2)
    out += rect(1010, 147, 13, 13, fill=c_p, stroke=c_p, sw=0.8)
    out += text(1028, 158, "Precision@10", size=11.5, fill=INK2)

    centers2 = [883, 949, 1015, 1081, 1147]
    for gi, cx in enumerate(centers2):
        v = precision[gi]
        x = cx - 17
        y = ay0 - (v / 0.15) * (ay0 - ay1)
        out += rect(x, y, 34, ay0 - y, fill=c_p, stroke=c_p, sw=0.8)
        out += text(cx, y - 6, "%.6f" % v, size=9.2, anchor="start",
                    fill=INK, rotate=-90)
        out += text(cx, 674, groups[gi], size=14, anchor="middle", weight="bold",
                    fill=INK2)

    out += text(95, 720, "数据来源：第六章表 6-7（核心 108 题的四项检索指标，主结果）。",
                size=11.5, fill=MUTED)
    out += text(95, 740,
                "读法：Complete@10 即 Complete Evidence Recall@K；各组分母不同，跨组比较按表中有效题数读。",
                size=11.5, fill=MUTED)
    out += text(W / 2, 790, "图 6-1　核心 108 题五组四项指标对比", size=20,
                anchor="middle", weight="bold", fill=INK)
    out += svg_close()
    return out


# =====================================================================
# 图 6-2　逐子集完整证据召回（A/B/C × 关系型/多跳型/时序型）
# =====================================================================

def fig_6_2():
    W, H = 1280, 770
    subsets = ["关系型", "多跳型", "时序型"]
    denom = ["n＝36／35／35", "n＝67／71／70", "n＝49／52／51"]
    vals = {
        "A": [0.638889, 0.641791, 0.653061],
        "B": [0.771429, 0.774648, 0.826923],
        "C": [0.742857, 0.757143, 0.823529],
    }
    colors = {"A": "#4E79A7", "B": "#76A7C8", "C": BROWN}

    out = svg_open(W, H)
    out += text(W / 2, 78,
                "Complete Evidence Recall@10（K＝10）；子集在核心 108 题内统计且允许重叠",
                size=13.5, anchor="middle", fill=MUTED)

    ax, ay0, ay1 = 100, 620, 170
    out += line(ax, ay0, ax, ay1, stroke=INK2, sw=1.2)
    out += line(ax, ay0, 1200, ay0, stroke=INK2, sw=1.2)
    for i in range(6):
        v = i / 5
        y = ay0 - v * (ay0 - ay1)
        out += line(ax - 5, y, ax, y, stroke=INK2, sw=1.2)
        out += text(ax - 10, y + 4, "%.1f" % v, size=12, anchor="end", fill=INK2)
    out += text(38, (ay0 + ay1) / 2, "指标取值（0～1）", size=12, anchor="middle",
                fill=INK2, rotate=-90)

    # 图例
    lx = 850
    for g in ("A", "B", "C"):
        out += rect(lx, 112, 14, 14, fill=colors[g], stroke=colors[g], sw=0.8)
        out += text(lx + 20, 124, "%s 组" % g, size=12.5, fill=INK2)
        lx += 105

    centers = [283, 650, 1017]
    for gi, cx in enumerate(centers):
        for si, g in enumerate(("A", "B", "C")):
            v = vals[g][gi]
            x = cx - 140 + si * 100
            y = ay0 - v * (ay0 - ay1)
            out += rect(x, y, 80, ay0 - y, fill=colors[g], stroke=colors[g], sw=0.8)
            out += text(x + 40, y - 8, "%.6f" % v, size=12, anchor="middle",
                        fill=INK)
        out += text(cx, 655, subsets[gi], size=15, anchor="middle", weight="bold",
                    fill=INK)
        out += text(cx, 679, denom[gi], size=12, anchor="middle", fill=MUTED)

    out += text(100, 720,
                "数据来源：第六章表 6-11／6-12／6-13 的 Complete Evidence Recall@K 行；分母为该子集内 A/B/C 的有效题数。",
                size=11.5, fill=MUTED)
    out += text(W / 2, 752, "图 6-2　逐子集完整证据召回（A/B/C × 关系型／多跳型／时序型）",
                size=20, anchor="middle", weight="bold", fill=INK)
    out += svg_close()
    return out


# =====================================================================
# 图 6-3　问答链路耗时分解（只画表 6-4 真实存在的分段）
# =====================================================================

def fig_6_3():
    W, H = 1280, 690
    # 表 6-4：平均 / P95（秒）。其余部分无最大值读数（—），故不画最大值。
    rows = [
        ("端到端（客户端墙钟）", 14.994, 37.048),
        ("大模型生成（与运行留痕同源）", 7.312, 29.306),
        ("其余部分（派生量）", 7.683, 8.091),
    ]
    c_mean, c_p95 = "#4E79A7", "#A9C6DB"
    out = svg_open(W, H)
    out += text(W / 2, 78, "单位：秒；P95 采用最近秩法，样本量 30 时 P95 接近最大值",
                size=13, anchor="middle", fill=MUTED)

    ax0, ax1, ay = 430, 1180, 510
    out += line(ax0, ay, ax1, ay, stroke=INK2, sw=1.2)
    for i in range(5):
        v = i * 10
        x = ax0 + (v / 40.0) * (ax1 - ax0)
        out += line(x, ay, x, ay + 5, stroke=INK2, sw=1.2)
        out += text(x, ay + 22, "%d" % v, size=12, anchor="middle", fill=INK2)
    out += text((ax0 + ax1) / 2, ay + 46, "耗时（秒）", size=12.5, anchor="middle",
                fill=INK2)

    # 图例
    lx = 900
    for color, label in ((c_mean, "平均"), (c_p95, "P95")):
        out += rect(lx, 112, 14, 14, fill=color, stroke=color, sw=0.8)
        out += text(lx + 20, 124, label, size=12.5, fill=INK2)
        lx += 90

    centers = [205, 335, 465]
    for i, (name, mean, p95) in enumerate(rows):
        cy = centers[i]
        # 两行类别标签
        parts = name.split("（")
        if len(parts) == 2:
            l1, l2 = parts[0], "（" + parts[1]
        else:
            l1, l2 = name, ""
        out += text(415, cy - 4, l1, size=13, anchor="end", fill=INK)
        if l2:
            out += text(415, cy + 15, l2, size=12, anchor="end", fill=MUTED)
        for j, (v, color) in enumerate(((mean, c_mean), (p95, c_p95))):
            y = cy - 35 + j * 40
            x2 = ax0 + (v / 40.0) * (ax1 - ax0)
            out += rect(ax0, y, x2 - ax0, 30, fill=color, stroke=color, sw=0.8)
            out += text(x2 + 8, y + 20, "%.3f" % v, size=12.5, fill=INK)

    out += text(60, 585,
                "注：其余部分＝端到端−大模型生成，是派生量，不是纯检索耗时。表 6-4 未给出向量检索、",
                size=11.5, fill=MUTED)
    out += text(60, 605,
                "图谱查询、预算裁剪与呈现的精确分段，本图不绘制这些分段；最大值读数见原表。",
                size=11.5, fill=MUTED)
    out += text(60, 630, "数据来源：第六章表 6-4（问答响应时间分段，n＝30）。",
                size=11.5, fill=MUTED)
    out += text(W / 2, 672, "图 6-3　问答链路耗时分解（n＝30，平均与 P95）", size=20,
                anchor="middle", weight="bold", fill=INK)
    out += svg_close()
    return out


# =====================================================================
# 类图辅助
# =====================================================================

def class_box(x, y, w, stereo, name, fileline, attrs, methods, header_fill="#ECEFF1"):
    head_h = 56
    attr_h = (len(attrs) * 19 + 10) if attrs else 8
    method_h = len(methods) * 19 + 12
    h = head_h + attr_h + method_h
    out = rect(x, y, w, h, fill=BOX, stroke=EDGE, sw=1.5)
    out += rect(x, y, w, head_h, fill=header_fill, stroke=EDGE, sw=1.5)
    out += line(x, y + head_h, x + w, y + head_h, stroke=EDGE, sw=1.2)
    if stereo:
        out += text(x + 10, y + 16, stereo, size=10.5, italic=True, fill=MUTED)
    out += text(x + 10, y + 35, name, size=14, weight="bold", fill=INK)
    out += text(x + 10, y + 50, fileline, size=10, fill=MUTED)
    yy = y + head_h + 8
    for a in attrs:
        out += text(x + 12, yy + 12, a, size=11.5, fill=INK2)
        yy += 19
    if attrs:
        out += line(x, y + head_h + attr_h, x + w, y + head_h + attr_h,
                    stroke=EDGE, sw=1.0)
    yy = y + head_h + attr_h + 8
    for m in methods:
        out += text(x + 12, yy + 12, m, size=11.5, fill=INK2)
        yy += 19
    return out, h


def package_box(x, y, w, h, title):
    out = rect(x, y, w, h, fill="none", stroke="#90A4AE", sw=1.6, rx=6)
    tab_w = min(w - 10, 420)
    out += rect(x, y, tab_w, 32, fill="#ECEFF1", stroke="#90A4AE", sw=1.4, rx=4)
    out += text(x + 12, y + 21, title, size=12.5, weight="bold", fill=INK2)
    return out


# =====================================================================
# 图 4-9　核心类图
# =====================================================================

def fig_4_9():
    W, H = 1560, 1240
    out = svg_open(W, H)
    out += text(W / 2, 70,
                "只用真实存在的类／模块；«module» 表示 Python 模块级函数，不虚构类；方法名逐条取自代码",
                size=12, anchor="middle", fill=MUTED)

    out += package_box(35, 95, 740, 950, "后端服务层（交付物/03-代码/后端）")
    out += package_box(805, 95, 720, 950, "检索与融合层（交付物/03-代码/检索、增强）")

    # ---- 后端类/模块
    b1, _ = class_box(60, 150, 300, "«module»", "api_qa", "api/qa.py", [],
                      ["ask()", "get_answer()", "config_meta()"])
    out += b1
    b2, _ = class_box(430, 150, 310, "«module»", "qa_service", "services/qa_service.py", [],
                      ["ask()", "_run_chain()", "_persist()", "get_answer()",
                       "evidence_of_answer()", "history_list()"])
    out += b2
    b3, _ = class_box(60, 390, 300, "", "TTLCache", "cache.py",
                      ["name", "ttl_seconds", "max_entries"],
                      ["get()", "set()", "get_or_load()", "invalidate()", "snapshot()"])
    out += b3
    b4, _ = class_box(430, 390, 310, "", "ApiError", "errors.py",
                      ["code", "message", "http_status", "detail"], ["payload()"])
    out += b4
    b5, _ = class_box(60, 660, 300, "", "MetricsRegistry", "observability.py", [],
                      ["record_request()", "record_qa_retrieval()",
                       "record_llm_attempts()", "snapshot()"])
    out += b5

    # 后端关系
    out += arrow(360, 205, 430, 205, dashed=True, label="«use»", lx=395, ly=197,
                 lsize=10.5)
    out += arrow(150, 281, 150, 390, dashed=True, label="«use»", lx=195, ly=340,
                 lsize=10.5)
    out += arrow(300, 281, 480, 390, dashed=True, label="«raise»", lx=365, ly=345,
                 lsize=10.5)
    out += arrow(520, 338, 520, 390, dashed=True, label="«raise»", lx=565, ly=368,
                 lsize=10.5)
    out += ortho_arrow([(470, 338), (390, 338), (390, 735), (360, 735)],
                       dashed=True, label="«record»", lx=402, ly=612, lsize=10.5,
                       lanchor="start")

    # 跨层调用说明（真实调用链，避免用虚构箭头连接两个包）
    out += rect(60, 850, 680, 165, fill=WARN_FILL, stroke=WARN_EDGE, sw=1.3)
    out += text(75, 875, "跨层调用（真实调用链，与图 4-10 一致）", size=12.5,
                weight="bold", fill="#4E342E")
    for i, s in enumerate([
        "api/qa.ask() → qa_service.ask() → _run_chain()",
        "_run_chain() → run_answer.py cmd_run()（子进程）",
        "cmd_run() → load_case_via_retrieval() → run_query.py（子进程）",
        "run_query.py → PipelineRunner.run() → pipeline.run_question()",
        "证据装配与生成在 run_answer.py（assemble.py／answer.py），见图 4-10",
    ]):
        out += text(75, 900 + i * 21, "· " + s, size=10.8, fill="#4E342E")

    # ---- 检索类/模块
    r1, _ = class_box(830, 150, 300, "«module»", "pipeline", "检索/pipeline.py", [],
                      ["run_question()", "collect_vector_candidates()",
                       "collect_hybrid_vector_candidates()", "collect_graph_candidates()",
                       "merge_candidates()", "trim_to_budget()", "keep_top_k()",
                       "order_evidence()"])
    out += r1
    r2, _ = class_box(1170, 150, 300, "«interface»", "VectorSearcherLike",
                      "hybrid_retrieval.py", [], ["search(question, n)"],
                      header_fill="#F3E5F5")
    out += r2
    r3, _ = class_box(1170, 290, 300, "", "VectorSearcher", "检索/vector_search.py",
                      ["index", "forward", "backward"], ["search(question, n)"])
    out += r3
    r4, _ = class_box(830, 500, 300, "«interface»", "LexicalIndexLike",
                      "hybrid_retrieval.py", [], ["search(question, n)"],
                      header_fill="#F3E5F5")
    out += r4
    r5, _ = class_box(830, 650, 300, "", "LexicalIndex", "增强/lexical_search.py",
                      ["postings", "chunk_ids", "doc_ids", "lengths"],
                      ["build(chunks)", "search(question, n)"])
    out += r5
    r6, _ = class_box(1170, 480, 320, "«module»", "hybrid_retrieval",
                      "增强/hybrid_retrieval.py", [],
                      ["vector_scores()", "lexical_scores()", "score_fusion()",
                       "hybrid_search()"])
    out += r6
    r7, _ = class_box(1170, 700, 300, "«interface»", "Reranker", "增强/reranker.py",
                      [], ["rerank(question, records)"], header_fill="#F3E5F5")
    out += r7
    r8, _ = class_box(1150, 850, 340, "", "RerankedRunner", "增强/reranker.py",
                      ["runner", "reranker"], ["run(questions, switches, n, k, budget, g)"])
    out += r8

    # 实现（虚线＋空心三角）
    out += line(1320, 290, 1320, 243, stroke=EDGE, sw=1.4, dash="7,5")
    out += arrow_head(1320, 290, 1320, 243, color=EDGE, size=13, open_triangle=True)
    out += text(1330, 270, "实现", size=10.5, fill=MUTED)
    out += line(980, 650, 980, 593, stroke=EDGE, sw=1.4, dash="7,5")
    out += arrow_head(980, 650, 980, 593, color=EDGE, size=13, open_triangle=True)
    out += text(990, 625, "实现", size=10.5, fill=MUTED)

    # 依赖
    out += arrow(1130, 240, 1170, 360, dashed=True,
                 label="collect_vector_candidates()", lx=1145, ly=235,
                 lsize=10.2, lanchor="middle", lrotate=-90)
    out += ortho_arrow([(1130, 330), (1150, 330), (1150, 540), (1170, 540)],
                       dashed=True, label="collect_hybrid_vector_candidates()",
                       lx=1160, ly=465, lsize=10.2, lanchor="middle", lrotate=-90)
    out += ortho_arrow([(1490, 480), (1490, 210), (1470, 210)], dashed=True,
                       label="vector_scores()", lx=1502, ly=345, lsize=10.2,
                       lanchor="middle", lrotate=-90)
    out += arrow(1170, 570, 1130, 570, dashed=True, label="search()",
                 lx=1150, ly=590, lsize=10.2)

    # 聚合：RerankedRunner 持有注入的 Reranker
    out += line(1320, 850, 1320, 793, stroke=EDGE, sw=1.5)
    out += ('<polygon points="1320,850 1312,840 1320,830 1328,840" fill="#FFFFFF" '
            'stroke="%s" stroke-width="1.3"/>\n' % EDGE)
    out += text(1332, 825, "聚合（注入）", size=10.5, fill=MUTED)

    # 检索侧说明
    out += rect(830, 860, 300, 155, fill=WARN_FILL, stroke=WARN_EDGE, sw=1.3)
    out += text(845, 885, "重排接口（默认关闭）", size=12.5, weight="bold",
                fill="#4E342E")
    for i, s in enumerate([
        "RerankedRunner 是 PipelineRunner 的透明包装；",
        "reranker=None 时原样返回同一对象。",
        "启用时只改变证据顺序与呈现顺序，",
        "集合、计数与其他字段不变。",
    ]):
        out += text(845, 910 + i * 21, s, size=10.8, fill="#4E342E")

    # ---- 图例
    lx, ly = 60, 1090
    out += text(lx, ly, "图例：", size=12, weight="bold", fill=INK2)
    out += line(lx + 55, ly - 4, lx + 120, ly - 4, stroke=EDGE, sw=1.3, dash="7,5")
    out += arrow_head(lx + 55, ly - 4, lx + 120, ly - 4, color=EDGE, size=9)
    out += text(lx + 130, ly, "依赖", size=11.5, fill=INK2)
    out += line(lx + 210, ly - 4, lx + 275, ly - 4, stroke=EDGE, sw=1.3, dash="7,5")
    out += arrow_head(lx + 210, ly - 4, lx + 275, ly - 4, color=EDGE, size=12,
                      open_triangle=True)
    out += text(lx + 285, ly, "实现", size=11.5, fill=INK2)
    out += line(lx + 365, ly - 4, lx + 430, ly - 4, stroke=EDGE, sw=1.4)
    out += ('<polygon points="%d,%d %d,%d %d,%d %d,%d" fill="#FFFFFF" stroke="%s" '
            'stroke-width="1.2"/>\n'
            % (lx + 365, ly - 4, lx + 372, ly - 9, lx + 379, ly - 4,
               lx + 372, ly + 1, EDGE))
    out += text(lx + 440, ly, "聚合（空心菱形在整体端）", size=11.5, fill=INK2)

    out += text(W / 2, 1210, "图 4-9　核心类图（后端服务与检索组件）", size=20,
                anchor="middle", weight="bold", fill=INK)
    out += svg_close()
    return out


# =====================================================================
# 图 4-10　提问到答案的核心时序图
# =====================================================================

def fig_4_10():
    W, H = 1600, 1485
    lanes = [
        ("前端", "Web UI", 100),
        ("后端 API", "api/qa.py", 330),
        ("问答编排", "qa_service.py／run_answer.py", 560),
        ("检索管线", "run_query.py / pipeline.py", 790),
        ("图谱查询", "graph_query.GraphQuery", 1020),
        ("证据装配", "assemble.py／answer.py", 1250),
        ("大模型", "answer.call_model()", 1480),
    ]
    out = svg_open(W, H)
    out += text(W / 2, 54,
                "实线＝请求／调用；虚线＝返回；竖向虚线为生命线。消息名取自代码调用链，不变式见图下",
                size=12.5, anchor="middle", fill=MUTED)

    top, bottom = 110, 1250
    for name, sub, x in lanes:
        out += rect(x - 95, top, 190, 58, fill="#ECEFF1", stroke=EDGE, sw=1.5, rx=4)
        out += text(x, top + 24, name, size=15, anchor="middle", weight="bold",
                    fill=INK)
        out += text(x, top + 45, sub, size=10.3, anchor="middle", fill=MUTED)
        out += line(x, top + 58, x, bottom, stroke="#B0BEC5", sw=1.2, dash="6,6")

    def msg(y, src, dst, label, dashed=False, lsize=12.2):
        x1 = [x for _n, _s, x in lanes if _n == src][0]
        x2 = [x for _n, _s, x in lanes if _n == dst][0]
        if dashed:
            out = line(x1, y, x2, y, stroke=LINE, sw=1.4, dash="7,5")
            out += arrow_head(x1, y, x2, y, color=LINE, size=10, filled=False)
        else:
            out = line(x1, y, x2, y, stroke=EDGE, sw=1.5)
            out += arrow_head(x1, y, x2, y, color=EDGE, size=10, filled=True)
        out += text((x1 + x2) / 2, y - 7, label, size=lsize, anchor="middle",
                    fill=INK2)
        return out

    def selfmsg(y, lane, label, lsize=11.4, loop_h=20):
        x = [x for _n, _s, x in lanes if _n == lane][0]
        out = poly([(x, y), (x + 34, y), (x + 34, y + loop_h), (x + 4, y + loop_h)],
                   fill="none", stroke=EDGE, sw=1.4)
        out += arrow_head(x + 34, y + loop_h, x + 4, y + loop_h, color=EDGE, size=9)
        lines = label.split("
")
        for i, s in enumerate(lines):
            out += text(x + 42, y + 6 + i * 16, s, size=lsize, fill=INK2)
        return out

    # 主干
    out += msg(200, "前端", "后端 API", "POST /api/qa/ask（question、session_id）")
    out += msg(248, "后端 API", "问答编排",
               "qa_service.ask(question, session_id, group, reuse=True)")
    out += text(445, 278, "（asyncio.to_thread；接口层只做校验与业务异常封装）",
                size=10.8, anchor="middle", fill=MUTED)
    out += selfmsg(295, "问答编排", "_reuse_existing_answer()：命中则直接返回")

    out += selfmsg(345, "问答编排",
                   "_run_chain()（子进程）
→ run_answer.cmd_run()", 11.2)
    out += msg(400, "问答编排", "检索管线",
               "load_case_via_retrieval() → run_query.py（子进程）", lsize=11.6)
    out += selfmsg(450, "检索管线", "PipelineRunner.run() → run_question()", 11.2)
    out += selfmsg(505, "检索管线",
                   "collect_hybrid_vector_candidates()
"
                   "→ hybrid_search()：vector_scores／lexical_scores", 10.9)

    out += msg(560, "检索管线", "图谱查询",
               "collect_graph_candidates() → g1_one_hop()／g2_two_hop()",
               lsize=11.5)
    out += text(905, 592,
                "D/E 组另调 g6_time_filter()；A/B/C 组走 keep_all_graph_candidates()",
                size=10.5, anchor="middle", fill=INK2)
    out += msg(630, "图谱查询", "检索管线", "路径、事件与 source_chunk_id", dashed=True,
               lsize=11.5)

    out += selfmsg(680, "检索管线", "apply_time_filter()（仅 D/E 组）", 11.2)
    out += selfmsg(735, "检索管线",
                   "② merge_candidates() → ③ trim_to_budget()
"
                   "④ keep_top_k() → ⑤ order_evidence()", 10.9)

    out += msg(795, "检索管线", "问答编排",
               "案例：final_evidence_chunk_ids＋graph_payload＋trace",
               dashed=True, lsize=11.0)
    out += msg(845, "问答编排", "证据装配",
               "assemble_case()：按 final_evidence_chunk_ids 冻结顺序装配",
               lsize=11.2)
    out += selfmsg(895, "证据装配", "build_messages()：七区块 Prompt（sha256 固定）",
                   10.9)
    out += msg(950, "证据装配", "大模型",
               "answer_case() → call_model(prompt, temperature＝0)", lsize=11.6)
    out += msg(990, "大模型", "证据装配", "body_text（模型原始输出，不改写）",
               dashed=True, lsize=11.5)
    out += selfmsg(1035, "证据装配",
                   "compose_answer()；gate()：四段合成＋答案侧门禁", 10.9)

    # 回程
    out += msg(1090, "证据装配", "问答编排", "合成答案／answer_trace.jsonl",
               dashed=True, lsize=11.2)
    out += selfmsg(1135, "问答编排", "_next_ids() → _persist()：同一 _DB_LOCK 内",
                   10.9)
    out += msg(1175, "问答编排", "后端 API",
               "九项载荷（answer_id、evidence、graph_path…）",
               dashed=True, lsize=11.2)
    out += msg(1215, "后端 API", "前端", "200 {data, meta}（errors.ok）",
               dashed=True, lsize=11.5)

    # 不变式区
    out += rect(60, 1290, 1480, 120, fill=WARN_FILL, stroke=WARN_EDGE, sw=1.3)
    out += text(78, 1316, "关键不变式", size=13, weight="bold", fill="#4E342E")
    inv = [
        ("① 五步契约不可重排：", "① 两路取候选 → ② 合并去重 → ③ 预算裁剪 → ④ 保留 K → ⑤ 呈现顺序＋图谱载荷（pipeline.FIVE_STEPS；D/E 组的时间过滤在第①步内）。"),
        ("② 证据集合冻结：", "assemble_case() 断言证据 chunk_id 顺序与 trace 的 final_evidence_chunk_ids 一致；生成侧不得重排、不得截断。"),
        ("③ 落库原子性：", "_next_ids() 与 _persist() 在同一 _DB_LOCK 内；answer_evidence 按 answer_id 先删旧再插新（同一事务）。"),
    ]
    for i, (head, body) in enumerate(inv):
        out += text(90, 1342 + i * 22, head, size=11.2, weight="bold", fill="#4E342E")
        out += text(235, 1342 + i * 22, body, size=10.8, fill="#4E342E")

    out += text(W / 2, 1455, "图 4-10　提问到答案的核心时序图", size=20,
                anchor="middle", weight="bold", fill=INK)
    out += svg_close()
    return out


def main():
    outputs = {
        "图6-1-核心108题五组四项指标对比.svg": fig_6_1(),
        "图6-2-逐子集完整证据召回.svg": fig_6_2(),
        "图6-3-问答链路耗时分解.svg": fig_6_3(),
        "图4-9-核心类图.svg": fig_4_9(),
        "图4-10-提问到答案核心时序图.svg": fig_4_10(),
    }
    for name, content in outputs.items():
        path = HERE / name
        path.write_text(content, encoding="utf-8", newline="\n")
        print("已写出：%s（%d 字节）" % (name, path.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
