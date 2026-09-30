# -*- coding: utf-8 -*-
"""代码\\后端\\services\\market_service.py —— 第 9 阶段「实时数据区」的取数服务。

**硬口径（务必先读这一节）**
--------------------------
本系统的问答答案锚定**冻结语料**（数据集 v2.1，数据截止 2026-09-25）。本模块取到的
**实时数据只作页面展示，绝不进入检索／问答证据链**——它不参与向量检索、不进图谱扩展、
不进最终证据集合，也不写入任何表；每个响应体都带 `"scope": "display_only"` 明示这一点，
页面必须把「实时区」与「问答答案（截至语料截止日）」**分开显示**。

第二条硬口径：**界面上不许编造数据**。任何外部源失败（超时／非 200／解析失败／网络不通）
都**不向接口层抛异常**，而是返回 `connected=False` ＋ 一句简短的 `reason` ＋ `items: []`，
由页面如实显示「未接入」；**绝不返回假价格、假涨跌幅、假新闻**。

四个源（三个外部 ＋ 一个语料内，URL 模板与超时／TTL／前缀规则**全部取自 config.py**）
--------------------------------------------------------------------------------
| 接口 | 源 | 说明 |
| --- | --- | --- |
| `quotes(codes)` | 东方财富 push2 行情 | `secids` 前缀：沪市 `1.`、深市 `0.` |
| `announcements(code, days)` | 东方财富 np-anotice 公告 | 详情页模板见 `config.MARKET_ZONE` |
| `news(keyword)` | 东方财富搜索 JSONP | 返回体需剥 `cb(...)` 外壳，**必须带 Referer** |
| `corpus_reports(days)` | **查库**（`document` 表） | **不依赖外部源**的降级形态：语料内近 N 天文档 |

依赖与实现取舍（**不新增依赖**）
------------------------------
只用标准库 `urllib.request` 取数，**不用 `httpx`**：三个源都是「一次 GET ＋ 读 JSON」，
`urllib` 足够，且后端服务进程少挂一个第三方库就少一处版本漂移面；`httpx` 虽已安装，
但其价值在连接池／HTTP2／异步，本模块（单机演示、进程内 60 s 缓存）用不到。
JSON 解析用标准库 `json`，正则清理 `<em>` 高亮标签用标准库 `re`。

缓存
----
进程内 `dict` ＋ TTL（默认 60 s，取自 `config.MARKET_ZONE["cache_ttl_seconds"]`），
键为「接口名 ＋ 参数」；命中时响应里标 `cached: true`，且 `updated_at` 保持不变
（即 `updated_at` 是**该次取数的时间**，不是本次请求的时间）。缓存是**进程内**的：
多进程／多实例部署下不共享（登记为已知限制，与限流同理）。

用法
----
    python 代码\\后端\\services\\market_service.py --selftest
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))              # 代码\后端\services
_BACKEND = os.path.dirname(_HERE)                               # 代码\后端
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402  （后端 config：实时区 URL 模板／超时／TTL／前缀规则）
import db      # noqa: E402  （只用于语料内源：查 document 表；**只读查询**）

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:                                        # noqa: BLE001
            pass

logger = logging.getLogger("ashare_qa.backend.market")

# 北京时间（+08:00）：一切时间字段为 ISO 8601，与 `data_cutoff_time` 的偏移口径一致
_CN_TZ = timezone(timedelta(hours=8))

# 实时区响应的固定声明：只作展示，不进证据链
SCOPE_DISPLAY_ONLY = "display_only"

# 语料内源固定附注（照《24》与作者口径；页面据此把实时区与答案口径分开）
CORPUS_NOTE = "语料内数据，不依赖外部源；语料截止后新发生的事不在其中"

# `<em>` 高亮标签（东方财富搜索结果里标题带的标记）：清掉，不留在展示文本里
_EM_TAG = re.compile(r"</?\s*em\s*>", re.IGNORECASE)


# ==========================================================================
# 1. 进程内缓存（键＝接口名＋参数；TTL 取自 config）
# ==========================================================================
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()


def _cache_ttl() -> float:
    return float(config.MARKET_ZONE["cache_ttl_seconds"])


def _cache_get(key):
    """取缓存；过期或不存在返回 None。"""
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if not hit:
        return None
    stamp, value = hit
    if time.monotonic() - stamp > _cache_ttl():
        with _CACHE_LOCK:
            _CACHE.pop(key, None)
        return None
    return value


def _cache_put(key, value) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.monotonic(), value)


def clear_cache() -> None:
    """清空进程内缓存（`--selftest` 与取证用）。"""
    with _CACHE_LOCK:
        _CACHE.clear()


# ==========================================================================
# 2. 统一的响应体与时间
# ==========================================================================
def _now_iso() -> str:
    """当前北京时间（ISO 8601，带 +08:00 偏移）。"""
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def _envelope(items, connected: bool, reason=None, source: str | None = None,
              extra: dict | None = None, cached: bool = False) -> dict:
    """实时区统一响应体。

    keys：`connected`／`updated_at`／`items`／`source`／`scope`／`reason`／`cached`
    （`extra` 里的键追加在后面）。`scope` 恒为 `display_only`——**实时数据只作展示，
    不进问答证据链**；`connected=False` 时 `items` 必为 `[]` 且 `reason` 非空。
    """
    payload = {
        "connected": bool(connected),
        "updated_at": _now_iso(),
        "items": list(items),
        "source": source or config.MARKET_ZONE["source_name"],
        "scope": SCOPE_DISPLAY_ONLY,
        "reason": reason,
        "cached": bool(cached),
    }
    if extra:
        payload.update(extra)
    return payload


def _failed(reason: str, source: str | None = None, extra: dict | None = None) -> dict:
    """降级响应：**未接入**（绝不含编造数据）。"""
    return _envelope([], False, reason=reason, source=source, extra=extra)


# ==========================================================================
# 3. 取数与解析的小工具
# ==========================================================================
def _headers(referer: str | None = None) -> dict:
    head = {"User-Agent": config.MARKET_ZONE["user_agent"],
            "Accept": "application/json, text/plain, */*"}
    if referer:
        head["Referer"] = referer
    return head


def _http_get(url: str, referer: str | None = None) -> str:
    """一次 GET，返回解码后的文本；非 200 或网络异常**抛异常**（由调用方降级）。"""
    req = urllib.request.Request(url, headers=_headers(referer))
    timeout = float(config.MARKET_ZONE["timeout_seconds"])
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status = getattr(resp, "status", 200)
        raw = resp.read()
    if status != 200:
        raise urllib.error.HTTPError(url, status, "HTTP %s" % status, None, None)
    return raw.decode("utf-8", "replace")


def _short_reason(exc: Exception) -> str:
    """把异常压成一句**简短**的未接入原因（不含口令、不含内网地址）。

    外部 URL 属公开接口，但原因里只给「类别 ＋ 异常名」，完整信息（含 URL）只进日志。
    """
    if isinstance(exc, urllib.error.HTTPError):
        return "外部数据源返回 HTTP %s" % exc.code
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "外部数据源请求超时"
    if isinstance(exc, urllib.error.URLError):
        return "外部数据源不可达"
    if isinstance(exc, (ValueError, KeyError, TypeError)):
        return "外部数据源返回体无法解析"
    return "外部数据源请求失败（%s）" % type(exc).__name__


def _num(value):
    """把源里的数值字段转成数字；`-`／空／不可解析一律 None（**不编造 0**）。"""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text in ("", "-", "--", "null", "None"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _strip_jsonp(text: str):
    """剥掉 JSONP 外壳（`cb(...)`／`(...)`），返回解析后的对象。

    东方财富搜索在 `cb=` 为空时直接返回 JSON，但**不保证**始终如此，故统一按
    「取第一个 `{` 到最后一个 `}`」解析，两种形态都能吃。
    """
    body = (text or "").strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("返回体不是 JSON／JSONP 对象")
    return json.loads(body[start:end + 1])


def _clean(text) -> str:
    """清掉 `<em>` 高亮标签并归一空白（搜索结果的标题会带这些标记）。"""
    return _EM_TAG.sub("", str(text or "")).strip()


def _secid_args(codes) -> tuple:
    """把代码列表归一化成 secids 串；`(secids, 非法项列表)`。

    非法项**不猜**：调用方据此返回未接入并将非法项写进 reason（接口层会先按 1002 拒）。
    """
    good, bad = [], []
    for code in codes or []:
        try:
            good.append(config.secid_of(code))
        except (ValueError, TypeError):
            bad.append(str(code))
    return ",".join(good), bad


# ==========================================================================
# 4. 对外函数：实时行情
# ==========================================================================
def quotes(codes) -> dict:
    """实时行情（东方财富 push2）。

    `codes` 支持 `600519`／`000001`／`sh600519`／`sz000001` 等写法（归一化见
    `config.secid_of`）。返回 `{connected, updated_at, items, source, scope, reason, cached}`，
    `items` 条目：`code`／`name`／`price`／`change_pct`／`change`／`amount`。

    **实时数据只作展示，不进问答证据链**；源不可达时 `connected=False` ＋ `reason`，
    `items` 为空，**不返回任何编造数字**。
    """
    code_list = list(codes or [])
    secids, bad = _secid_args(code_list)
    if bad:
        return _failed("证券代码格式不合法：%s" % "、".join(bad))
    if not secids:
        return _failed("未提供证券代码")

    key = ("quote", secids)
    hit = _cache_get(key)
    if hit is not None:
        out = copy.deepcopy(hit)
        out["cached"] = True
        return out

    url = config.MARKET_ZONE["quote_url"].format(secids=secids)
    try:
        body = _http_get(url)
        data = json.loads(body)
        diff = ((data or {}).get("data") or {}).get("diff") or []
        items = [item for item in (_quote_item(row) for row in diff) if item is not None]
    except Exception as exc:                                     # noqa: BLE001（降级不抛）
        logger.warning("实时行情取数失败：url=%s err=%s: %s",
                       url, type(exc).__name__, exc)
        return _failed(_short_reason(exc))

    out = _envelope(items, True)
    _cache_put(key, copy.deepcopy(out))
    return out


def _quote_item(row) -> dict | None:
    """把 push2 的一行 `diff[]` 映射成展示条目（字段名照 `f12/f14/f2/f3/f4/f6`）。"""
    if not isinstance(row, dict):
        return None
    code = str(row.get("f12") or "").strip()
    if not code:
        return None
    return {
        "code": code,
        "name": str(row.get("f14") or "").strip(),
        "price": _num(row.get("f2")),
        "change_pct": _num(row.get("f3")),
        "change": _num(row.get("f4")),
        "amount": _num(row.get("f6")),
    }


# ==========================================================================
# 5. 对外函数：个股公告
# ==========================================================================
def announcements(code, days: int = 7, page_size: int = 20) -> dict:
    """个股公告（东方财富 np-anotice），按 `notice_date` 过滤出近 `days` 天。

    `items` 条目：`title`／`date`／`url`／`type`。**只作展示，不进问答证据链**；
    源不可达时 `connected=False` ＋ `reason`，`items` 为空，不返回编造条目。
    """
    try:
        code6 = str(code).strip().lower()
        for prefix in config.MARKET_MARKET_PREFIX:               # 允许 `sz000001` 形式
            if code6.startswith(prefix):
                code6 = code6[len(prefix):]
                break
        if not (len(code6) == 6 and code6.isdigit()):
            return _failed("证券代码格式不合法：%r" % code)
        days = int(days)
        page_size = int(page_size)
    except (ValueError, TypeError):
        return _failed("参数不合法")

    key = ("announcements", code6, days, page_size)
    hit = _cache_get(key)
    if hit is not None:
        out = copy.deepcopy(hit)
        out["cached"] = True
        return out

    url = config.MARKET_ZONE["announcement_url"].format(page_size=page_size, code=code6)
    try:
        body = _http_get(url)
        data = json.loads(body)
        rows = ((data or {}).get("data") or {}).get("list") or []
        floor = (datetime.now(_CN_TZ).date() - timedelta(days=days)).isoformat()
        items = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            notice_date = str(row.get("notice_date") or "")
            if notice_date[:10] and notice_date[:10] < floor:     # 只要近 N 天
                continue
            art_code = str(row.get("art_code") or "").strip()
            columns = row.get("columns") or []
            ann_type = (str(columns[0].get("column_name") or "").strip()
                        if columns and isinstance(columns[0], dict) else "") or "公告"
            items.append({
                "title": _clean(row.get("title")),
                "date": notice_date,
                "url": (config.MARKET_ZONE["notice_detail_url"]
                        .format(code=code6, art_code=art_code) if art_code else None),
                "type": ann_type,
            })
        items.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
        items = items[:page_size]
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("个股公告取数失败：code=%s url=%s err=%s: %s",
                       code6, url, type(exc).__name__, exc)
        return _failed(_short_reason(exc), extra={"code": code6, "days": days})

    out = _envelope(items, True, extra={"code": code6, "days": days})
    _cache_put(key, copy.deepcopy(out))
    return out


# ==========================================================================
# 6. 对外函数：个股新闻
# ==========================================================================
def news(keyword, page_size: int = 20) -> dict:
    """个股新闻（东方财富搜索 JSONP），返回体剥壳后取 `result.cmsArticleWebOld[]`。

    `items` 条目：`title`（已清 `<em>`）／`time`／`url`／`media`。
    **只作展示，不进问答证据链**；源不可达时 `connected=False` ＋ `reason`。
    """
    text = str(keyword or "").strip()
    if not text:
        return _failed("未提供关键词")
    try:
        page_size = int(page_size)
    except (ValueError, TypeError):
        return _failed("参数不合法")

    key = ("news", text, page_size)
    hit = _cache_get(key)
    if hit is not None:
        out = copy.deepcopy(hit)
        out["cached"] = True
        return out

    param = {
        "uid": "", "keyword": text, "type": ["cmsArticleWebOld"],
        "client": "web", "clientType": "web",
        "param": {"cmsArticleWebOld": {
            "searchScope": "default", "sort": "default", "pageIndex": 1,
            "pageSize": page_size, "preTag": "", "postTag": ""}},
    }
    url = config.MARKET_ZONE["news_url"].format(
        param=urllib.parse.quote(json.dumps(param, ensure_ascii=False, separators=(",", ":"))))
    try:
        body = _http_get(url, referer=config.MARKET_ZONE["news_referer"])
        parsed = _strip_jsonp(body)
        rows = ((parsed or {}).get("result") or {}).get("cmsArticleWebOld") or []
        items = [{
            "title": _clean(row.get("title")),
            "time": str(row.get("date") or ""),
            "url": row.get("url") or None,
            "media": str(row.get("mediaName") or "").strip(),
        } for row in rows if isinstance(row, dict)]
        items = items[:page_size]
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("个股新闻取数失败：keyword=%s url=%s err=%s: %s",
                       text, url, type(exc).__name__, exc)
        return _failed(_short_reason(exc), extra={"keyword": text})

    out = _envelope(items, True, extra={"keyword": text})
    _cache_put(key, copy.deepcopy(out))
    return out


# ==========================================================================
# 7. 对外函数：语料内近一周（不依赖外部源的降级形态）
# ==========================================================================
def corpus_reports(days: int = 7, page_size: int = 20) -> dict:
    """**语料内**近 N 天文档：直接查库 `document` 表，**不依赖外部源**。

    时间窗为「语料截止日往前 `days` 天」到「语料截止日」闭区间（截止日取自
    `config.dataset_meta()` 的 `data_cutoff_time`，不写死日期）。`items` 条目：
    `title`／`source`／`publish_time`／`url`／`category`；响应另附 `corpus_cutoff`
    与 `note`。

    这是实时区的**降级形态**：外部源全部不可用时，页面仍能用它显示「语料内近一周的
    重要报告」。**它同样只作展示、不进问答证据链**——文档虽来自语料，但这里是按
    `publish_time` 直查列表，与问答链路的证据集合无关。
    """
    try:
        days = int(days)
        page_size = int(page_size)
    except (ValueError, TypeError):
        return _failed("参数不合法", source=config.MARKET_ZONE["corpus_source_name"])

    key = ("reports", days, page_size)
    hit = _cache_get(key)
    if hit is not None:
        out = copy.deepcopy(hit)
        out["cached"] = True
        return out

    cutoff_date = config.data_cutoff_date()                      # 如 "2026-09-25"
    extra = {"corpus_cutoff": cutoff_date, "days": days, "note": CORPUS_NOTE}
    source = config.MARKET_ZONE["corpus_source_name"]
    try:
        cutoff = date.fromisoformat(cutoff_date)
        start = (cutoff - timedelta(days=days)).isoformat()
        end = (cutoff + timedelta(days=1)).isoformat()
        rows = db.query(
            "SELECT title, source, publish_time, url, category FROM `document` "
            "WHERE publish_time >= %s AND publish_time < %s "
            "ORDER BY publish_time DESC, doc_id DESC LIMIT %s",
            (start + " 00:00:00", end + " 00:00:00", page_size))
        items = [{
            "title": str(row.get("title") or ""),
            "source": str(row.get("source") or ""),
            "publish_time": (row["publish_time"].isoformat(sep=" ")
                             if hasattr(row.get("publish_time"), "isoformat")
                             else str(row.get("publish_time") or "")),
            "url": row.get("url") or None,
            "category": row.get("category"),
        } for row in rows]
    except Exception as exc:                                     # noqa: BLE001
        logger.warning("语料内近一周查库失败：days=%s err=%s: %s",
                       days, type(exc).__name__, exc)
        return _failed(_short_reason(exc), source=source, extra=extra)

    out = _envelope(items, True, source=source, extra=extra)
    _cache_put(key, copy.deepcopy(out))
    return out


# ==========================================================================
# 8. 自检（`python 代码\后端\services\market_service.py --selftest`）
# ==========================================================================
def _print_block(title: str, resp: dict) -> None:
    print("--- %s ---" % title)
    print("  connected=%s  cached=%s  updated_at=%s  items=%d  reason=%s"
          % (resp.get("connected"), resp.get("cached"), resp.get("updated_at"),
             len(resp.get("items") or []), resp.get("reason")))
    for item in (resp.get("items") or [])[:3]:
        print("    %s" % json.dumps(item, ensure_ascii=False))
    for key in ("corpus_cutoff", "note", "code", "days", "keyword"):
        if key in resp:
            print("  %s = %s" % (key, resp[key]))
    print()


def selftest() -> int:
    line = "=" * 74
    print(line)
    print("market_service.py 自检（实时数据区：只作展示、不进问答证据链）")
    print(line)
    print("  scope 口径 = %s（每个响应体都带）" % SCOPE_DISPLAY_ONLY)
    print("  TTL=%ss  超时=%ss  默认股=%s"
          % (config.MARKET_ZONE["cache_ttl_seconds"],
             config.MARKET_ZONE["timeout_seconds"],
             "、".join(config.market_default_codes())))
    print()

    clear_cache()
    checks = []

    # 1) 实时行情
    q = quotes(config.market_default_codes())
    _print_block("1. 实时行情 quotes(%s)" % ",".join(config.market_default_codes()), q)
    checks.append(("行情源接入且有条目", q["connected"] and len(q["items"]) > 0))

    # 2) 个股公告
    a = announcements("000001", days=config.MARKET_ZONE["corpus_lookback_days"])
    _print_block("2. 个股公告 announcements('000001', days=7)", a)
    checks.append(("公告源接入且有条目", a["connected"] and len(a["items"]) > 0))

    # 3) 个股新闻
    n = news("平安银行")
    _print_block("3. 个股新闻 news('平安银行')", n)
    checks.append(("新闻源接入且有条目", n["connected"] and len(n["items"]) > 0))

    # 4) 语料内近一周（不依赖外部源）
    c = corpus_reports(config.MARKET_ZONE["corpus_lookback_days"])
    _print_block("4. 语料内近一周 corpus_reports(days=7)", c)
    checks.append(("语料内源接入且有条目", c["connected"] and len(c["items"]) > 0))

    # 5) 降级：把行情源 host 指向不可达域名（内存副本，不动 config 文件）
    clear_cache()
    saved = config.MARKET_ZONE["quote_url"]
    broken = saved.replace("push2.eastmoney.com", "unreachable.invalid.example")
    config.MARKET_ZONE["quote_url"] = broken
    try:
        d = quotes(["000001"])
    finally:
        config.MARKET_ZONE["quote_url"] = saved        # 复原（复核见下方断言）
    _print_block("5. 降级（行情源 host 指向不可达域名 unreachable.invalid.example）", d)
    no_fabrication = (d["connected"] is False and d["items"] == [] and bool(d["reason"]))
    checks.append(("降级返回 connected=False ＋ 空 items ＋ reason，无编造数字", no_fabrication))
    checks.append(("降级响应仍带 scope=display_only", d["scope"] == SCOPE_DISPLAY_ONLY))
    checks.append(("config 的行情源已复原",
                   config.MARKET_ZONE["quote_url"] == saved))

    # 6) 缓存生效：同参数连取两次，第二次 cached=true 且 updated_at 不变
    #    （用新闻源：它的可用性在三个外部源里最稳；行情源可能正被源侧限流）
    clear_cache()
    first = news("平安银行")
    second = news("平安银行")
    same_stamp = first["updated_at"] == second["updated_at"]
    _print_block("6. 缓存：第一次", first)
    _print_block("6. 缓存：第二次（应 cached=true）", second)
    checks.append(("第二次缓存命中（cached=true）", second["cached"] is True))
    checks.append(("缓存命中时 updated_at 不变", same_stamp and first["cached"] is False))

    print("--- 关键判据 ---")
    for label, good in checks:
        print("  [%s] %s" % ("OK " if good else "FAIL", label))
    print(line)
    return 0 if all(g for _, g in checks) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="实时数据区取数服务（只作展示、不进问答证据链）")
    parser.add_argument("--selftest", action="store_true", help="真连三个源各取一次并验证降级路径")
    args = parser.parse_args()
    if args.selftest:
        raise SystemExit(selftest())
    parser.print_help()
    raise SystemExit(0)
