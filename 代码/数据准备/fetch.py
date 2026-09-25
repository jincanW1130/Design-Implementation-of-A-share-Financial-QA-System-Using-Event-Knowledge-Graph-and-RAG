# -*- coding: utf-8 -*-
"""fetch.py —— 第 5 阶段（数据准备）采集层：T1 / T2 / T3。

职责（《代码\\数据准备\\README.md》§一、§三、§四）：
  T1 数据源确认与合规核查 → meta\\sources.csv
  T2 公司与时间窗确定     → 直接读 config.py（本阶段已冻结，脚本不重新选取）
  T3 采集与原始数据落盘   → raw\\{doc_id}.json、raw\\_fetch_log.jsonl

本脚本的四条纪律：
  1. 参数一律来自 config.py；README §四 只记接口形状，端点按其冻结的 URL 形状拼装。
  2. 真实数据：标题／时间／URL／正文全部来自来源站点，抓不到就记 ok:false 跳过并计数。
  3. 只写 dataset_dir(profile) 下的 meta\\sources.csv 与 raw\\*（不写 clean\\chunks\\index\\reports\\）。
  4. 幂等 + 可续跑：raw\\{doc_id}.json 已存在则默认跳过（--force 才重取）；
     同一 URL 复用既有 doc_id，新候选按 (publish_time 降序, url 升序) 领取块内最小空闲序号。

用法：
    python 代码\\数据准备\\fetch.py --profile pilot
    python 代码\\数据准备\\fetch.py --profile v1
    python 代码\\数据准备\\fetch.py --profile pilot --dir <临时目录>   # 仅供自测
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# 控制台为 GBK，中文输出必须先切到 UTF-8（README §六）
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import config  # noqa: E402  （本文件与 config.py 同目录）


# ==========================================================================
# 0. 接口常量
# --------------------------------------------------------------------------
# config.py 冻结了来源站点（SOURCES）、公司、时间窗、配额、编号方案与已实测端点
# （ENDPOINTS）；接口路径形状由 README.md §四 冻结。端点一律取 config.ENDPOINTS，
# 本文件不再重复写 URL 字面量（各键含意见 README §四）。
# ==========================================================================
CNINFO_HOME = config.SOURCES["公告"]["home"]
CNINFO_TOPSEARCH_URL = config.ENDPOINTS["cninfo_topsearch"]
CNINFO_QUERY_URL = config.ENDPOINTS["cninfo_query"]
CNINFO_DETAIL_URL = CNINFO_HOME + "/new/disclosure/detail"
CNINFO_STATIC_HOST = config.ENDPOINTS["cninfo_static"]      # README §4.1 第 3 条
# 列表接口单次条数（非配额）。2026-09-25 实测：该接口**每页最多只回 30 条**，
# pageSize 传 50/100/200 同样只回 30，因此整个时间窗必须靠翻页取（见 cninfo_announcements）。
CNINFO_PAGE_SIZE = 30

# 公告标题排除审计（config.EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_* 的落点）：
# 每个模式最多记几条示例标题，示例标题截断到约 40 字符（见 README §4.1）。
EXCLUDE_TITLE_EXAMPLE_MAX = 3
EXCLUDE_TITLE_EXAMPLE_CHARS = 40

# 正文长度上限过滤审计（config.MAX_DOC_CHARS_FOR_INCLUSION 的落点）：
# 每类别最多记几条示例标题，标题截断口径与标题排除审计一致（见 README §4.5）。
LENGTH_EXAMPLE_MAX = EXCLUDE_TITLE_EXAMPLE_MAX

CSRC_HOME = config.SOURCES["监管公开信息"]["home"]
CSRC_SEARCH_URL = config.ENDPOINTS["csrc_search"]           # README §4.2；形如 .../searchList/{channel}
CSRC_PAGE_SIZE = 20                                         # 实测上限（_pageSize 更大仍返回 20）
# 已实测 channelGuid（config.ENDPOINTS["csrc_channels"]）：主来源行政处罚，备用来源市场禁入
CSRC_CHANNELS = [{"name": name, "guid": guid}
                 for name, guid in config.ENDPOINTS["csrc_channels"].items()]

GOV_HOME = config.SOURCES["政策文件"]["home"]
GOV_SEARCH_URL = config.ENDPOINTS["gov_policy_search"]      # README §4.3
GOV_LIB_TYPES = list(config.ENDPOINTS["gov_policy_types"])   # 国务院文件 / 部门文件
GOV_PAGE_SIZE = 20

# 财经新闻：三家站点自带的站内检索（同一站点的检索结果页/接口），用于把"提到本公司"的文章找出来
PEOPLE_SEARCH_URL = "http://search.people.cn/search-platform/front/search"
CS_SEARCH_URL = config.SOURCES["财经新闻"]["home"].split(";")[1].strip() + "/mi4-web/tv_news/search_articles"
ZQRB_SEARCH_URL = re.sub(r"//www\.", "//search.", config.NEWS_SITES["证券日报网"]["entry"]).rstrip("/") + "/search.php"
NEWS_SEARCH_LIMIT = 20      # 每个检索请求取回条数
NEWS_SEARCH_PAGES = {       # 每家公司每个站点的检索翻页上限
    "人民网财经": 2,
    "中证网": 2,
    "证券日报网": 1,
}


# ==========================================================================
# 1. 时间与文本工具
# ==========================================================================
TZ = timezone(timedelta(hours=8))

_RE_TAGS = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"[ \t\r\f\v]+")
_RE_DATE = re.compile(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})")
_RE_DATE_TIME = re.compile(r"(20\d{2})[-./年](\d{1,2})[-./月](\d{1,2})[日]?\s+\d{1,2}:\d{2}")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def strip_tags(value) -> str:
    if value is None:
        return ""
    return _RE_TAGS.sub("", str(value)).replace("\u00a0", " ").strip()


def norm_space(text: str) -> str:
    cleaned = str(text).replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    return _RE_WS.sub(" ", cleaned).strip()


def parse_date(value) -> str | None:
    """把来源给出的日期（含中文/点号分隔）归一成 YYYY-MM-DD。"""
    if value is None:
        return None
    m = _RE_DATE.search(str(value))
    if not m:
        return None
    year, month, day = (int(x) for x in m.groups())
    try:
        return datetime(year, month, day).date().isoformat()
    except ValueError:
        return None


def ms_to_date(ms) -> str | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000.0, TZ).date().isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def in_window(date_str: str | None) -> bool:
    return date_str is not None and config.WINDOW_START <= date_str <= config.WINDOW_END


def bucket_of(date_str: str | None) -> str | None:
    """返回 'recent' / 'earlier'；不在两个相对时间桶内返回 None。"""
    if date_str is None:
        return None
    if config.BUCKET_RECENT[0] <= date_str <= config.BUCKET_RECENT[1]:
        return "recent"
    if config.BUCKET_EARLIER[0] <= date_str <= config.BUCKET_EARLIER[1]:
        return "earlier"
    return None


def decode_html(resp: requests.Response) -> str:
    """按 声明/Header → 网页 meta → chardet 猜测 → utf-8 的顺序解码 HTML。"""
    raw = resp.content
    enc = None
    m = re.search(r"charset=([\w\-]+)", resp.headers.get("content-type", ""), re.I)
    if m:
        enc = m.group(1)
    if not enc:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w\-]+)", raw[:4096], re.I)
        if m:
            enc = m.group(1).decode("ascii", "ignore")
    for candidate in (enc, resp.apparent_encoding, "utf-8"):
        if not candidate:
            continue
        try:
            return raw.decode(candidate, errors="replace")
        except LookupError:
            continue
    return raw.decode("utf-8", errors="replace")


def json_body(resp: requests.Response):
    return json.loads(resp.content.decode("utf-8", "replace"))


def make_soup(html: str) -> BeautifulSoup:
    """lxml 解析最快，但对个别站点（实测：gov.cn 政策正文页）的畸形 HTML 会整段丢正文；
    若 lxml 结果的可读文本异常少而 HTML 本身不小，则退回 html.parser 重解并取文本更多者。"""
    soup = BeautifulSoup(html, "lxml")
    text_len = len(soup.get_text(" ", strip=True))
    if text_len < 500 and len(html) > 5000:
        try:
            fallback = BeautifulSoup(html, "html.parser")
        except Exception:
            return soup
        if len(fallback.get_text(" ", strip=True)) > text_len:
            return fallback
    return soup


def pick_text(node) -> str:
    """优先用 <p> 段落拼正文；没有 <p> 时退回整块文本。"""
    if node is None:
        return ""
    paragraphs = [norm_space(p.get_text(" ", strip=True)) for p in node.find_all("p")]
    paragraphs = [p for p in paragraphs if len(p) >= 15]
    if paragraphs:
        return "\n".join(paragraphs)
    return norm_space(node.get_text("\n", strip=True))


def extract_body(soup: BeautifulSoup, selectors) -> str:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            text = pick_text(node)
            if len(text) >= config.MIN_DOC_CHARS:
                return text
    best = ""
    for node in soup.find_all(["div", "article", "section"]):
        text = pick_text(node)
        if len(text) > len(best):
            best = text
    return best


def extract_pdf_text(blob: bytes) -> str:
    import fitz  # PyMuPDF：只在真正解析 PDF 时导入

    doc = fitz.open(stream=blob, filetype="pdf")
    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()
    return norm_space(text)


def company_aliases(company: dict) -> list:
    """名称匹配别名：全称 + 去掉尾部 A/B 股后缀的简称（如 万科A → 万科）。"""
    names = [company["name"]]
    short = re.sub(r"[A-Za-z]$", "", company["name"])
    if short and short != company["name"] and len(short) >= 2:
        names.append(short)
    return names


def match_companies(text: str, companies) -> list:
    """按公司名或 6 位代码匹配，返回命中的股票代码（升序去重）。"""
    hits = []
    for company in companies:
        code = company["code"]
        for name in company_aliases(company):
            if name in text:
                hits.append(code)
                break
        else:
            if re.search(r"(?<!\d)" + re.escape(code) + r"(?!\d)", text):
                hits.append(code)
    return sorted(set(hits))


# ==========================================================================
# 2. HTTP 客户端：限流 + 重试（README §五 第 4 条）
# ==========================================================================
class FetchError(Exception):
    pass


class HttpClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": config.HTTP["user_agent"],
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        self.min_interval = float(config.HTTP["min_interval_seconds"])
        self.timeout = float(config.HTTP["timeout_seconds"])
        self.max_retries = int(config.HTTP["max_retries"])
        self.backoff = float(config.HTTP["backoff_seconds"])
        self._last_request_at = 0.0
        self.request_count = 0
        self.error_count = 0

    def _throttle(self):
        delta = time.monotonic() - self._last_request_at
        if delta < self.min_interval:
            time.sleep(self.min_interval - delta)

    def request(self, method: str, url: str, *, headers=None, data=None, params=None,
                timeout=None) -> requests.Response:
        """按 min_interval 限流；失败按 backoff_seconds 指数退避，最多 1 + max_retries 次尝试。"""
        last_exc = None
        attempts = 1 + max(0, self.max_retries)
        for attempt in range(attempts):
            self._throttle()
            try:
                resp = self.session.request(method, url, headers=headers, data=data,
                                            params=params, timeout=timeout or self.timeout)
                self._last_request_at = time.monotonic()
                self.request_count += 1
                if resp.status_code >= 500 or resp.status_code == 429:
                    raise FetchError("HTTP %d" % resp.status_code)
                return resp
            except Exception as exc:  # 网络异常与 5xx/429 都重试
                self._last_request_at = time.monotonic()
                self.request_count += 1
                self.error_count += 1
                last_exc = exc
                if attempt + 1 < attempts:
                    time.sleep(self.backoff * (2 ** attempt))
        raise FetchError("%s %s 失败：%r" % (method, url, last_exc))

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)


# ==========================================================================
# 3. 候选与文档
# ==========================================================================
@dataclass
class Cand:
    category: str
    source: str
    page_url: str
    content_url: str = ""
    title_hint: str = ""
    publish_time: str | None = None
    company_list: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    kind: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Doc:
    doc_id: int
    category: str
    source: str
    title: str
    company_list: list
    publish_time: str
    page_url: str
    content_url: str
    raw_text: str
    extract_method: str
    fetched_at: str
    http_status: int | None
    byte_size: int | None
    meta: dict

    def to_raw(self) -> dict:
        return {
            "doc_id": self.doc_id,
            "category": self.category,
            "source": self.source,
            "title": self.title,
            "company_list": list(self.company_list),
            "publish_time": self.publish_time,
            "page_url": self.page_url,
            "content_url": self.content_url,
            "raw_text": self.raw_text,
            "extract_method": self.extract_method,
            "fetched_at": self.fetched_at,
            "http_status": self.http_status,
            "byte_size": self.byte_size,
            "meta": self.meta if isinstance(self.meta, dict) else {},
        }


def doc_pub(doc):
    return doc["publish_time"] if isinstance(doc, dict) else doc.publish_time


def doc_url(doc):
    return doc["page_url"] if isinstance(doc, dict) else doc.page_url


def newest_first(cands):
    """候选统一排序：publish_time 降序、同日期按 url（与既有 pick_* 的排序键逐字一致）。"""
    return sorted(cands, key=lambda c: (doc_pub(c) or "", doc_url(c)), reverse=True)


# ==========================================================================
# 4. 运行上下文：目录、日志、既有产物索引、doc_id 分配
# ==========================================================================
class Context:
    def __init__(self, profile: str, out_dir: str, force: bool):
        self.profile = profile
        self.settings = config.profile_settings(profile)
        self.companies = self.settings["companies"]
        self.quota = self.settings["quota"]
        self.ann_per_company = self.settings["announcement_per_company"]
        self.ann_strata = self.settings["announcement_strata"]   # 公告时段分层（config 唯一来源）
        # 公告标题排除模式（config.profile_settings 唯一来源）：在候选收集阶段生效，
        # 先于 level 1 配额与 level 2 铺开，保证分层只从存活候选里抽（README §4.1）。
        self.exclude_patterns = [str(p) for p in
                                 (self.settings.get("exclude_announcement_title_patterns") or [])]
        self.out_dir = os.path.abspath(out_dir)
        self.meta_dir = os.path.join(self.out_dir, "meta")
        self.raw_dir = os.path.join(self.out_dir, "raw")
        self.force = force
        self.http = HttpClient()
        os.makedirs(self.meta_dir, exist_ok=True)
        os.makedirs(self.raw_dir, exist_ok=True)
        self.log_fh = open(os.path.join(self.raw_dir, "_fetch_log.jsonl"), "a",
                           encoding="utf-8", newline="\n")
        self.deferred_logs = []          # 抓取成功但 doc_id 待分配的行（新闻类别用）
        self.existing = self._load_existing()
        self.stats = {c: {"new": 0, "reused": 0, "skipped": 0, "failed": 0,
                          "prefiltered": 0, "pages": 0, "elapsed": 0.0}
                      for c in config.CATEGORIES}
        # 标题排除审计：category -> {"examined": 检查条数, "excluded": 排除条数,
        #   "by_pattern": {pattern: {"count": 条数, "examples": [截断后的标题]}}}
        self.exclusion_audit = {c: {"examined": 0, "excluded": 0, "by_pattern": {}}
                                for c in config.CATEGORIES}
        # 正文长度上限（config.MAX_DOC_CHARS_FOR_INCLUSION）：
        #   text_cache  : 内容 URL -> 正文条目（候选阶段探测到的正文，正式落盘时直接复用，
        #                 因此同一篇候选在一次运行里最多下载一次）；
        #   length_audit: category -> {阈值, 已探测正文的候选数, 超长丢弃数, 示例标题,
        #                 内部去重集合}，落点是 raw\_fetch_log.jsonl 的类别审计行（README §4.5）。
        self.text_cache = {}
        self.length_audit = {c: new_length_audit() for c in config.CATEGORIES}

    # ---- 既有产物：raw\*.json → page_url 索引（幂等与编号复用的依据） ----
    def _load_existing(self) -> dict:
        index = {}
        if not os.path.isdir(self.raw_dir):
            return index
        for name in os.listdir(self.raw_dir):
            if not re.fullmatch(r"\d+\.json", name):
                continue
            try:
                with open(os.path.join(self.raw_dir, name), "r", encoding="utf-8") as fh:
                    rec = json.load(fh)
            except (OSError, ValueError):
                continue
            if isinstance(rec, dict) and rec.get("page_url"):
                index[rec["page_url"]] = rec
        return index

    def existing_doc(self, url: str):
        return self.existing.get(url)

    def used_ids(self, category: str) -> set:
        return {rec.get("doc_id") for rec in self.existing.values()
                if rec.get("category") == category}

    def assign_ids(self, category: str, cands) -> dict:
        """候选（已按 publish_time 降序、url 升序排好）→ doc_id。

        同一 URL 复用既有 doc_id（编号不漂移）；新候选按顺序领取块内最小空闲序号。
        干净目录下第一轮即 1..N，满足 config.DOC_ID_BLOCK 与 README §二 的编号口径。
        """
        block = config.DOC_ID_BLOCK[category]
        used = self.used_ids(category)
        mapping = {}
        for cand in cands:
            rec = self.existing.get(cand.page_url)
            if rec is not None and rec.get("category") == category:
                mapping[cand.page_url] = rec["doc_id"]
                continue
            seq = 1
            while (block + seq) in used or (block + seq) in mapping.values():
                seq += 1
            mapping[cand.page_url] = block + seq
        return mapping

    # ---- 日志：一行一次尝试，增量写入（可续跑的审计依据） ----
    def log(self, *, doc_id, category, source, url, http_status, ok, chars,
            byte_size, elapsed_ms, note=""):
        line = {
            "doc_id": doc_id,
            "category": category,
            "source": source,
            "url": url,
            "http_status": http_status,
            "ok": bool(ok),
            "chars": chars,
            "byte_size": byte_size,
            "elapsed_ms": elapsed_ms,
            "fetched_at": now_iso(),
            "note": note,
        }
        self.log_fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.log_fh.flush()

    def log_deferred(self, line: dict):
        """抓取成功但 doc_id 尚未分配时先缓存，分配后统一补 doc_id 落盘。"""
        self.deferred_logs.append(line)

    def flush_deferred(self, mapping: dict):
        for line in self.deferred_logs:
            doc_id = mapping.get(line.get("url"))
            if doc_id is None:
                line["note"] = (line.get("note", "") + "；已抓取但未进入本轮配额选择集").strip("；")
            else:
                line["doc_id"] = doc_id
            self.log_fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        self.log_fh.flush()
        self.deferred_logs = []

    def write_raw(self, doc: Doc):
        path = os.path.join(self.raw_dir, "%d.json" % doc.doc_id)
        tmp = path + ".tmp"
        rec = doc.to_raw()
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        self.existing[doc.page_url] = rec

    def close(self):
        try:
            self.log_fh.close()
        except OSError:
            pass


# --------------------------------------------------------------------------
# 4.5 候选选择：level 1（时段分层／配额）+ level 2（区间内按等间距目标日期铺开）
# --------------------------------------------------------------------------
def bucket_range(name: str):
    """两个相对时间桶在 config 里冻结的日期区间；level 2 的 [S, E] 即该区间。"""
    return tuple(config.BUCKET_RECENT) if name == "recent" else tuple(config.BUCKET_EARLIER)


def spread_targets(start: str, end: str, k: int):
    """level 2 的目标日期：在 [start, end] 上等间距取 k 个，**必含区间两端**。

    * k == 1：唯一目标取区间中点 start + round((end - start) / 2)；
    * k >= 2：t_i = start + round(i * (end - start) / (k - 1))，i = 0 … k−1，
      故 t_0 = start、t_{k−1} = end（两端都被照顾）。

    目标只由 (start, end, k) 决定，round 为 Python 的确定性取整，不依赖任何遍历顺序，可复现。
    """
    if k <= 0:
        return []
    start_d = datetime.strptime(start, "%Y-%m-%d").date()
    end_d = datetime.strptime(end, "%Y-%m-%d").date()
    span = (end_d - start_d).days
    if k == 1:
        return [start_d + timedelta(days=round(span / 2))]
    return [start_d + timedelta(days=round(i * span / (k - 1))) for i in range(k)]


def pick_spread(cands, k: int, start: str, end: str):
    """level 2：在日期区间 [S, E] 内取 k 篇，按**等间距目标日期**铺开，两端必被照顾。

    规则（2026-09-25 修正，替代原"每个等长子区间各取最新"口径）：
      * 目标日期由 spread_targets 给出：k == 1 取区间中点；k >= 2 时 t_0 = S、t_{k-1} = E；
      * 对每个目标 t_i 依次选取**尚未取用**、publish_time 距 t_i 最近的候选；
        距离相同时取较晚的日期（再并列时按 pool 的既有顺序，即 url 降序，保证可复现）；
      * 某个目标已无候选可取 -> 该槽位留空，最后从**同区间**剩余候选按最新优先回填；
      * 区间内候选 n < k -> 全部取走，由调用方按 level 1 既有口径从另一时段补足。

    返回 (picked, info)：picked 按最新优先排好；info 记录 range／targets／k／n／空槽数／
    回填篇数（n < k 时另记 shortfall）。空槽只可能出现在 n >= k 的情形，即需要登记的场景。

    起因（2026-09-25 实测）：原"每段取最新"永远不会选中区间内**最早**的候选，区间下界
    （earlier 桶左端＝WINDOW_START）因此没有文档，cutoff − publish_time_min 掉到 86 天、
    卡在 check.py #13 的 90 天门槛外。改成含两端的目标日期后，区间两端的候选都会被选到。
    """
    if k <= 0:
        return [], None
    pool = newest_first([c for c in cands if start <= (doc_pub(c) or "") <= end])
    n = len(pool)
    targets = spread_targets(start, end, k)
    info = {"range": [start, end], "targets": [t.isoformat() for t in targets],
            "k": k, "n": n, "empty_slots": 0, "backfilled": 0, "shortfall": max(0, k - n)}
    if n < k:
        return pool, info
    taken = [False] * n
    picked = []
    for target in targets:
        best_idx, best_key = None, None
        for i, cand in enumerate(pool):       # pool 为最新优先：完全并列时取先遇到者，可复现
            if taken[i]:
                continue
            try:
                pub_d = datetime.strptime((doc_pub(cand) or "")[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            key = (abs((pub_d - target).days), -pub_d.toordinal())   # 同距离 -> 偏好较晚日期
            if best_key is None or key < best_key:
                best_idx, best_key = i, key
        if best_idx is None:                  # 该目标已无候选可取：槽位留空，稍后同区间回填
            info["empty_slots"] += 1
            continue
        taken[best_idx] = True
        picked.append(pool[best_idx])
    for i, cand in enumerate(pool):          # 空槽：同区间剩余候选，最新优先
        if len(picked) >= k:
            break
        if not taken[i]:
            taken[i] = True
            picked.append(cand)
            info["backfilled"] += 1
    return newest_first(picked), info


def spread_note_text(category: str, info: dict, subject: str = "") -> str:
    """level 2 空槽回填的登记文本（写进 raw\\_fetch_log.jsonl 的 note，ok=true）。"""
    return ("时间铺开（level 2）空槽回填：类别=%s%s；区间=[%s, %s]；"
            "目标日期（等间距、含两端）=%s；k=%d；n=%d；"
            "空槽 %d 个；已按同区间剩余候选最新优先回填 %d 篇"
            % (category, "，公司=%s" % subject if subject else "",
               info["range"][0], info["range"][1], "、".join(info.get("targets") or []),
               info["k"], info["n"], info["empty_slots"], info["backfilled"]))


def log_spread_notes(ctx: Context, category: str, notes) -> None:
    """把 level 2 的空槽回填登记为 raw\\_fetch_log.jsonl 的 ok=true 行。"""
    for note in notes or []:
        ctx.log(doc_id=None, category=category,
                source=config.SOURCES[category]["source"],
                url=config.SOURCES[category]["home"], http_status=None, ok=True,
                chars=None, byte_size=None, elapsed_ms=0, note=note)


# --------------------------------------------------------------------------
# 4.6 公告标题排除规则（config：定期报告全文不收录）
# --------------------------------------------------------------------------
def truncate_title_for_note(title: str, limit: int = EXCLUDE_TITLE_EXAMPLE_CHARS) -> str:
    """审计行里的示例标题：超过 limit 字符即截断并加省略号（需求口径"约 40 字符"）。"""
    text = norm_space(title)
    return text if len(text) <= limit else text[:limit] + "…"


def excluded_by_title_pattern(ctx: Context, title: str, category: str) -> list:
    """候选标题是否命中排除模式；命中则登记审计计数并返回命中的模式列表。

    只在**候选收集阶段**调用（cninfo_announcements 内）：返回非空即表示该候选被丢弃，
    不会进入 level 1 时段分层配额，也不会进入 level 2 时间铺开。模式一律取自
    config.profile_settings(profile)["exclude_announcement_title_patterns"]，本文件不复制字面量。
    """
    title = title or ""
    audit = ctx.exclusion_audit.setdefault(
        category, {"examined": 0, "excluded": 0, "by_pattern": {}})
    audit["examined"] += 1
    hits = [p for p in ctx.exclude_patterns if re.search(p, title)]
    if not hits:
        return []
    audit["excluded"] += 1
    ctx.stats.setdefault(category, {}).setdefault("prefiltered", 0)
    ctx.stats[category]["prefiltered"] += 1
    example = truncate_title_for_note(title)
    for pattern in hits:
        slot = audit["by_pattern"].setdefault(pattern, {"count": 0, "examples": []})
        slot["count"] += 1
        if len(slot["examples"]) < EXCLUDE_TITLE_EXAMPLE_MAX and example not in slot["examples"]:
            slot["examples"].append(example)
    return hits


def exclusion_summary_note(ctx: Context, category: str) -> str:
    """排除审计的 note 文本：逐模式条数 + 若干示例标题 + 正文长度上限过滤结果（零也照写）。"""
    audit = ctx.exclusion_audit.get(category) or {"examined": 0, "excluded": 0, "by_pattern": {}}
    per_pattern = []
    for pattern in ctx.exclude_patterns:
        slot = audit["by_pattern"].get(pattern) or {"count": 0, "examples": []}
        text = "r'%s' 排除 %d 条" % (pattern, slot["count"])
        if slot["examples"]:
            text += "（示例：%s）" % "；".join(slot["examples"])
        per_pattern.append(text)
    if category == "公告":
        head = ("公告标题排除规则审计：候选池内检查公告标题 %d 条，排除 %d 条；"
                "同一标题命中多个模式时按各自模式分别计数，故分模式条数之和可能大于排除条数"
                % (audit["examined"], audit["excluded"]))
    else:
        head = ("公告标题排除规则审计：category=%s 不含 announcementTitle 候选，检查 0 条、"
                "排除 0 条（该规则只作用于公告候选池）" % category)
    return ("%s；按模式：%s；%s；模式 %d 条，来源=config.profile_settings('%s')"
            "['exclude_announcement_title_patterns']"
            % (head, "；".join(per_pattern) or "（模式列表为空，本次未过滤）",
               length_filter_note_text(ctx, category),
               len(ctx.exclude_patterns), ctx.profile))


def log_exclusion_summary(ctx: Context) -> None:
    """每个类别追加一行 ok=true 的排除审计（即使零排除也写，证明过滤确实执行过）。"""
    for category in config.CATEGORIES:
        ctx.log(doc_id=None, category=category,
                source=config.SOURCES[category]["source"],
                url=config.SOURCES[category]["home"], http_status=None, ok=True,
                chars=None, byte_size=None, elapsed_ms=0,
                note=exclusion_summary_note(ctx, category))


# --------------------------------------------------------------------------
# 4.7 正文长度上限过滤（config.MAX_DOC_CHARS_FOR_INCLUSION，四类来源统一口径）
# --------------------------------------------------------------------------
# 口径（README §4.5）：候选的正文一经抽取，即与 config.MAX_DOC_CHARS_FOR_INCLUSION 比对；
# 超过上限的候选**整篇丢弃**，且必须发生在 level 1（时段分层／配额）与 level 2（时间铺开）
# 之前——被丢弃者由次优候选顶替，因此每公司／每类别配额不会被抽空。一律**不截断**正文
# （截断等于改写证据，《10》§4.4.6；《12》§七）。丢弃明细（条数 + 最多 3 条示例标题与实测
# 字符数）登记在 raw\_fetch_log.jsonl 的类别审计行里。
# 实现要点：探测与正式落盘共用 ctx.text_cache，同一篇候选一次运行只下载一次正文；
# 已有 raw\<doc_id>.json 的候选直接复用其正文长度（--force 时除外）。
def length_cap() -> int:
    """正文长度上限（唯一来源 config.MAX_DOC_CHARS_FOR_INCLUSION，不写死）。"""
    return int(config.MAX_DOC_CHARS_FOR_INCLUSION)


def new_length_audit() -> dict:
    """一个类别的长度上限审计槽（"probed"/"dropped" 只对**不同 URL** 计数）。"""
    return {"threshold": length_cap(), "probed": 0, "dropped": 0, "examples": [],
            "probed_urls": set(), "dropped_urls": set()}


def length_audit_of(ctx: Context, category: str) -> dict:
    return ctx.length_audit.setdefault(category, new_length_audit())


def note_probed(ctx: Context, category: str, key: str) -> None:
    """登记“该候选的正文已被探测”（同一 URL 只计一次，重选轮次不重复计数）。"""
    audit = length_audit_of(ctx, category)
    if key and key not in audit["probed_urls"]:
        audit["probed_urls"].add(key)
        audit["probed"] += 1


def note_length_drop(ctx: Context, category: str, key: str, title, chars: int) -> None:
    """登记一条“超过长度上限、整篇丢弃”（同一 URL 只计一次）。"""
    audit = length_audit_of(ctx, category)
    if key and key in audit["dropped_urls"]:
        return
    if key:
        audit["dropped_urls"].add(key)
    audit["dropped"] += 1
    audit["examples"].append({"title": truncate_title_for_note(str(title or "")),
                              "chars": int(chars)})


def length_filter_note_text(ctx: Context, category: str) -> str:
    """长度上限审计的 note 文本：阈值、已探测候选数、超长丢弃数、最多 3 条示例。"""
    audit = length_audit_of(ctx, category)
    examples = sorted(audit["examples"],
                      key=lambda e: (-e["chars"], e["title"]))[:LENGTH_EXAMPLE_MAX]
    text = ("正文长度上限过滤审计：上限 config.MAX_DOC_CHARS_FOR_INCLUSION=%d 字符；"
            "本轮已探测正文的候选 %d 篇，其中超过上限、**整篇丢弃**（绝不截断）%d 篇"
            % (audit["threshold"], audit["probed"], audit["dropped"]))
    if examples:
        text += ("；示例：" + "；".join("《%s》（%d 字符）" % (e["title"], e["chars"])
                                    for e in examples))
    return text


def reused_raw_entry(ctx: Context, cand: Cand):
    """候选已有 raw\\<doc_id>.json 时复用其正文（不再重复下载）；--force 时不复用。"""
    if ctx.force:
        return None
    rec = ctx.existing_doc(cand.page_url)
    if rec is None or rec.get("category") != cand.category:
        return None
    if not isinstance(rec.get("raw_text"), str):
        return None
    return {
        "text": rec["raw_text"], "ok": True, "chars": None,
        "http_status": rec.get("http_status"), "byte_size": rec.get("byte_size"),
        "extract_method": rec.get("extract_method") or "raw_reuse", "elapsed_ms": 0,
        "note": "复用已有 raw\\%s.json 的正文（本次未重复下载）" % rec.get("doc_id"),
    }


def cache_text_entry(ctx: Context, key: str, entry: dict) -> dict:
    if key:
        ctx.text_cache[key] = entry
    return entry


def fetch_candidate_text(ctx: Context, category: str, cand: Cand):
    """按类别抽取候选正文（带缓存）。公告=PDF；监管公开信息／政策文件=HTML（含同源回退）。

    返回 entry：{"text", "ok", "chars", "http_status", "byte_size", "extract_method",
    "elapsed_ms", "note"}。ok=False 表示这次抽取没拿到可用正文，note 写明原因——探测阶段
    只丢长度超限的候选，抽取失败的候选仍留在池里，交由正式 materialize 按既有口径登记失败。
    """
    if category == "公告":
        return fetch_announcement_text(ctx, cand)
    if category == "监管公开信息":
        return fetch_csrc_body(ctx, cand)
    if category == "政策文件":
        return fetch_gov_body(ctx, cand)
    raise ValueError("正文长度上限过滤不支持该类别：%r" % category)


def probe_overlong_candidates(ctx: Context, category: str, cands) -> list:
    """在**选入之前**按 config.MAX_DOC_CHARS_FOR_INCLUSION 过滤候选：返回超长的候选列表。

    调用方把返回值从候选池里剔除后按同一口径（level 1 分层／配额 + level 2 时间铺开）重选，
    因此被丢弃的候选由次优候选顶替，配额不会被抽空。正文只读长度、绝不修改或截断。
    """
    cap = length_cap()
    over = []
    for cand in cands:
        entry = fetch_candidate_text(ctx, category, cand)
        key = cand.content_url or cand.page_url
        if not entry or not entry.get("ok"):
            continue                      # 抽取失败：不算超长，交由正式 materialize 登记失败
        note_probed(ctx, category, key)
        chars = len(entry.get("text") or "")
        if chars > cap:
            note_length_drop(ctx, category, key, cand.title_hint, chars)
            over.append(cand)
    return over


def pick_balanced(cands, quota: int, category: str = ""):
    """全局类别（监管／政策／新闻）按两个相对时间桶各约一半挑候选；某桶不足由其余候选补足。

    level 1（口径不变）：recent 目标 (quota+1)//2 篇、earlier 目标其余，缺口按最新优先补足；
    level 2：每个桶在自己的 [S, E] 内按 pick_spread 的等间距目标日期（含两端）铺开。
    返回 (picked, notes)：picked 按最新优先排好；notes 为发生空槽回填的区间说明。
    """
    if quota is None:
        quota = len(cands)
    pool = {name: newest_first([c for c in cands if bucket_of(doc_pub(c)) == name])
            for name in ("recent", "earlier")}
    other = newest_first([c for c in cands if bucket_of(doc_pub(c)) is None])
    target_recent = (quota + 1) // 2
    target_earlier = quota - target_recent
    picked, notes = [], []
    for name, target in (("recent", target_recent), ("earlier", target_earlier)):
        start, end = bucket_range(name)
        got, info = pick_spread(pool[name], min(target, len(pool[name])), start, end)
        picked.extend(got)
        if info and info["empty_slots"]:
            notes.append(spread_note_text(category, info))
    picked_ids = {id(c) for c in picked}
    if len(picked) < quota:
        rest = newest_first([c for c in pool["recent"] + pool["earlier"] + other
                             if id(c) not in picked_ids])
        picked += rest[:quota - len(picked)]
    return newest_first(picked), notes


def pick_balanced_with_length_cap(ctx: Context, category: str, cands, quota: int):
    """全局类别（监管／政策／新闻）的选择：按既有 pick_balanced 口径选，并在**选入之前**
    按 config.MAX_DOC_CHARS_FOR_INCLUSION 过滤超长候选（整篇丢弃后从池里剔除再重选，
    由次优候选顶替；绝不截断）。返回 (picked, notes)。
    """
    pool = list(cands)
    while True:
        picked, notes = pick_balanced(pool, quota, category=category)
        over = probe_overlong_candidates(ctx, category, picked)
        if not over:
            return picked, notes
        over_ids = {id(c) for c in over}
        pool = [c for c in pool if id(c) not in over_ids]


def pick_stratified(cands, strata: dict, category: str = "", subject: str = ""):
    """公告按公司做**时段分层抽取**（level 1）+ 时段内**时间铺开**（level 2）。

    level 1（口径不变）：先各取 strata["recent"] / strata["earlier"] 篇，
    某一时段候选不足时，由另一时段尚未取走的部分补足（config.ANNOUNCEMENT_STRATA_*）；
    level 2：每个时段在自己的 [S, E] 上按 pick_spread 的等间距目标日期（含两端）铺开，
    空槽回填同区间候选。
    返回 (picked, drawn, notes)：picked 按最新优先排好；drawn = {"recent": 实际取到篇数,
    "earlier": 实际取到篇数}（level 1 口径，供既有的分时段登记沿用）；notes 为回填说明。
    """
    need = {"recent": max(0, int(strata.get("recent") or 0)),
            "earlier": max(0, int(strata.get("earlier") or 0))}
    pool = {"recent": newest_first([c for c in cands if bucket_of(doc_pub(c)) == "recent"]),
            "earlier": newest_first([c for c in cands if bucket_of(doc_pub(c)) == "earlier"])}
    drawn = {name: min(need[name], len(pool[name])) for name in ("recent", "earlier")}
    for name in ("recent", "earlier"):
        other = "earlier" if name == "recent" else "recent"
        shortfall = need[name] - drawn[name]
        if shortfall > 0:
            drawn[other] += min(shortfall, len(pool[other]) - drawn[other])
    picked, notes = [], []
    for name in ("recent", "earlier"):
        start, end = bucket_range(name)
        got, info = pick_spread(pool[name], drawn[name], start, end)
        picked.extend(got)
        if info and info["empty_slots"]:
            notes.append(spread_note_text(category, info, subject))
    picked_ids = {id(c) for c in picked}
    total_need = drawn["recent"] + drawn["earlier"]
    if len(picked) < total_need:            # 兜底：理论上不会走到（k <= len(pool) 已保证）
        rest = newest_first([c for c in pool["recent"] + pool["earlier"]
                             if id(c) not in picked_ids])
        picked += rest[:total_need - len(picked)]
    return newest_first(picked), drawn, notes


# ==========================================================================
# 5. 采集器一：公告（巨潮资讯网）
# ==========================================================================
def cninfo_org_id(ctx: Context, company: dict):
    """代码 → orgId（README §4.1 第 1 条）。返回 (orgId, zwjc) 或 (None, None)。"""
    resp = ctx.http.post(
        CNINFO_TOPSEARCH_URL,
        data={"keyWord": company["code"], "maxNum": 10},
        headers={"Referer": CNINFO_HOME + "/"},
    )
    if resp.status_code != 200:
        return None, None
    data = json_body(resp)
    if not isinstance(data, list):
        return None, None
    for item in data:
        if str(item.get("code")) == company["code"] and item.get("orgId"):
            return item["orgId"], item.get("zwjc") or company["name"]
    for item in data:
        if item.get("orgId"):
            return item["orgId"], item.get("zwjc") or company["name"]
    return None, None


def cninfo_announcements(ctx: Context, company: dict, org_id: str):
    """窗口内的公告候选：按 config.CNINFO_MAX_PAGES 逐页取列表接口后合并去重。

    巨潮 hisAnnouncement/query **每页最多只返回 30 条**（2026-09-25 实测：pageSize 传
    30/50/100/200 均只回 30），只请求第 1 页时高公告量公司的候选池回不到窗口左端——
    实测中国石化 100 天窗口内 85 篇，第 1 页只覆盖 2026-08-24 之后，earlier 时段几乎
    没有候选，分层抽取只能跨段回填。此处逐页请求并合并：
      * 去重键＝announcementId（该字段缺失时退回 adjunctUrl），同一篇公告绝不重复入池；
      * 某页返回 0 条即停（已到列表末尾）；
      * 该页最旧一条的 announcementTime 早于 WINDOW_START 即停（再往前翻只会更旧）；
      * 每次列表页请求都走 ctx.http，config.HTTP["min_interval_seconds"] 限流照旧生效。
    返回口径与修复前逐字一致：窗口过滤 + 必须带附件 → 标题排除 → 降序排序。
    """
    seen_keys = set()
    out = []
    for page in range(1, max(1, int(config.CNINFO_MAX_PAGES)) + 1):
        form = {
            "pageNum": page,
            "pageSize": CNINFO_PAGE_SIZE,
            "column": company["cninfo_column"],
            "tabName": "fulltext",
            "stock": "%s,%s" % (company["code"], org_id),
            "seDate": "%s~%s" % (config.WINDOW_START, config.WINDOW_END),
            "isHLtitle": "true",
        }
        ctx.stats["公告"]["pages"] += 1        # 实际发出的列表页请求数（stdout 摘要用）
        resp = ctx.http.post(CNINFO_QUERY_URL, data=form,
                             headers={"Referer": CNINFO_HOME + "/"})
        if resp.status_code != 200:
            break
        items = json_body(resp).get("announcements") or []
        if not items:
            break
        oldest = None                      # 本页最旧一条（含被后续过滤丢弃的条目）
        for item in items:
            ms = item.get("announcementTime")
            pub = ms_to_date(ms)
            if pub is not None and (oldest is None or pub < oldest):
                oldest = pub
            adjunct = (item.get("adjunctUrl") or "").strip()
            aid = item.get("announcementId")
            key = (str(aid) if aid not in (None, "")
                   else ("adjunct:" + adjunct if adjunct else None))
            if key is None or key in seen_keys:
                continue                   # 已进入过候选池（跨页重复）或无可去重依据
            seen_keys.add(key)
            if not in_window(pub):
                continue
            if not adjunct:
                continue
            title = strip_tags(item.get("announcementTitle"))
            # 定期报告类公告在**候选收集阶段**即被丢弃：先于 level 1 配额与 level 2 铺开，
            # 因此分层抽取只从存活候选里取（口径见 config.EXCLUDE_ANNOUNCEMENT_TITLE_PATTERNS_*）。
            if excluded_by_title_pattern(ctx, title, "公告"):
                continue
            content_url = (adjunct if adjunct.startswith("http")
                           else CNINFO_STATIC_HOST + adjunct.lstrip("/"))
            page_url = "%s?stockCode=%s&announcementId=%s&orgId=%s&announcementTime=%s" % (
                CNINFO_DETAIL_URL, company["code"], item.get("announcementId"), org_id, ms)
            out.append(Cand(
                category="公告",
                source=config.SOURCES["公告"]["source"],
                page_url=page_url,
                content_url=content_url,
                title_hint=title,
                publish_time=pub,
                company_list=[company["code"]],
                meta={
                    "announcementId": item.get("announcementId"),
                    "orgId": org_id,
                    "secCode": item.get("secCode"),
                    "secName": item.get("secName"),
                    "adjunctType": item.get("adjunctType"),
                    "announcementTimeMs": ms,
                },
                kind="cninfo_pdf",
            ))
        if oldest is not None and oldest < config.WINDOW_START:
            break                          # 本页已越过窗口下界，无需再往前翻
    out.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return out


def discover_announcements(ctx: Context):
    """每家公司（不足时启用 config 预批准的替代公司）在窗口内的公告候选。"""
    per_company = []
    notes = []
    for company in ctx.companies:
        org_id, _ = cninfo_org_id(ctx, company)
        if not org_id:
            note = "topSearch 未解析到 orgId：%s %s" % (company["code"], company["name"])
            notes.append(note)
            ctx.stats["公告"]["failed"] += 1
            ctx.log(doc_id=None, category="公告", source=config.SOURCES["公告"]["source"],
                    url=CNINFO_TOPSEARCH_URL, http_status=None, ok=False, chars=None,
                    byte_size=None, elapsed_ms=0, note=note)
            continue
        per_company.append([company, cninfo_announcements(ctx, company, org_id), ""])

    need = ctx.ann_per_company
    for row in per_company:
        company, cands = row[0], row[1]
        if len(cands) >= need or not company.get("subs"):
            continue
        sub, sub_cands = fetch_sub_candidates(ctx, company)
        extra = sub_cands[:need - len(cands)]
        if extra:
            note = ("主选公司 %s %s 窗口内公告 %d 篇，低于每公司配额 %d；"
                    "按 config.subs 启用预批准替代公司 %s %s 补 %d 篇"
                    % (company["code"], company["name"], len(cands), need,
                       sub["code"], sub["name"], len(extra)))
            notes.append(note)
            ctx.log(doc_id=None, category="公告", source=config.SOURCES["公告"]["source"],
                    url=CNINFO_QUERY_URL, http_status=None, ok=False, chars=None,
                    byte_size=None, elapsed_ms=0, note=note)
            row[1] = cands + extra
            row[2] = note
    return per_company, notes


def fetch_sub_candidates(ctx: Context, company: dict):
    """按 config.subs 取**预先批准**的替代公司在窗口内的公告候选（主选公司候选不足时启用）。

    返回 (sub_company, cands)；没有替代公司或解析不到 orgId 时返回 (sub|None, [])。
    只读 config 里预先批准的公司，不自行另选。
    """
    if not company.get("subs"):
        return None, []
    sub_code, sub_name = company["subs"][0]
    sub = {"code": sub_code, "name": sub_name,
           "cninfo_column": company["cninfo_column"], "subs": []}
    org_id, _ = cninfo_org_id(ctx, sub)
    if not org_id:
        return sub, []
    return sub, cninfo_announcements(ctx, sub, org_id)


def fetch_announcement_text(ctx: Context, cand: Cand):
    """下载 PDF 并用 PyMuPDF 抽取正文（必须带浏览器 UA 与 cninfo Referer），按内容 URL 缓存。

    缓存使"候选阶段的长度探测"与"正式落盘"共用同一次下载（README §4.5），
    ctx.force 时仍走缓存（--force 的语义是忽略已存在的 raw 文件，不是重复下载同一篇）。
    """
    key = cand.content_url or cand.page_url
    if key in ctx.text_cache:
        return ctx.text_cache[key]
    reused = reused_raw_entry(ctx, cand)
    if reused is not None:
        return cache_text_entry(ctx, key, reused)
    entry = {"text": "", "ok": False, "chars": None, "http_status": None, "byte_size": None,
             "extract_method": "pdf_pymupdf", "elapsed_ms": 0, "note": ""}
    if not re.search(r"\.pdf($|\?)", cand.content_url, re.I):
        entry["note"] = ("附件非 PDF（adjunctType=%s），本轮只采集 PDF 正文"
                         % cand.meta.get("adjunctType"))
        return cache_text_entry(ctx, key, entry)
    started = time.monotonic()
    try:
        resp = ctx.http.get(cand.content_url, headers={"Referer": CNINFO_HOME + "/"})
    except FetchError as exc:
        entry["elapsed_ms"] = int((time.monotonic() - started) * 1000)
        entry["note"] = "PDF 下载失败：%s" % exc
        return cache_text_entry(ctx, key, entry)
    entry["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    entry["http_status"] = resp.status_code
    entry["byte_size"] = len(resp.content)
    if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
        entry["note"] = ("PDF 响应异常（status=%s, 前缀=%r）"
                         % (resp.status_code, resp.content[:8]))
        return cache_text_entry(ctx, key, entry)
    try:
        text = extract_pdf_text(resp.content)
    except Exception as exc:  # PyMuPDF 解析失败
        entry["note"] = "PyMuPDF 解析失败：%r" % (exc,)
        return cache_text_entry(ctx, key, entry)
    entry["text"] = text
    entry["chars"] = len(text)
    if len(text) < config.MIN_DOC_CHARS:
        entry["note"] = "PDF 抽出的正文短于 MIN_DOC_CHARS=%d" % config.MIN_DOC_CHARS
        return cache_text_entry(ctx, key, entry)
    entry["ok"] = True
    entry["note"] = "extract_method=pdf_pymupdf"
    return cache_text_entry(ctx, key, entry)


def materialize_announcement(ctx: Context, cand: Cand, doc_id: int):
    """把 fetch_announcement_text 的结果按既有口径登记并生成 raw 记录（正文只下载一次）。"""
    entry = fetch_announcement_text(ctx, cand)
    if not entry.get("ok"):
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source,
                url=cand.content_url, http_status=entry.get("http_status"), ok=False,
                chars=entry.get("chars") or None, byte_size=entry.get("byte_size"),
                elapsed_ms=entry.get("elapsed_ms") or 0, note=entry.get("note") or "")
        return None
    text = entry["text"]
    ctx.log(doc_id=doc_id, category=cand.category, source=cand.source,
            url=cand.content_url, http_status=entry.get("http_status"), ok=True,
            chars=len(text), byte_size=entry.get("byte_size"),
            elapsed_ms=entry.get("elapsed_ms") or 0, note=entry.get("note") or "")
    return Doc(doc_id=doc_id, category=cand.category, source=cand.source,
               title=cand.title_hint, company_list=list(cand.company_list),
               publish_time=cand.publish_time, page_url=cand.page_url,
               content_url=cand.content_url, raw_text=text,
               extract_method="pdf_pymupdf", fetched_at=now_iso(),
               http_status=entry.get("http_status"), byte_size=entry.get("byte_size"),
               meta=dict(cand.meta))


# ==========================================================================
# 6. 采集器二：监管公开信息（中国证监会）
# ==========================================================================
def csrc_page(ctx: Context, guid: str, page: int):
    params = {
        "_isAgg": "true",
        "_isJson": "true",
        "_pageSize": CSRC_PAGE_SIZE,
        "_template": "index",
        "page": page,
    }
    resp = ctx.http.get(CSRC_SEARCH_URL.format(channel=guid), params=params,
                        headers={"Referer": CSRC_HOME + "/"})
    if resp.status_code != 200:
        return None
    try:
        payload = json_body(resp)
    except ValueError:
        return None
    return (payload.get("data") or {}).get("results") or []


def csrc_meta(item: dict) -> dict:
    meta = {}
    for group in item.get("domainMetaList") or []:
        for entry in group.get("resultList") or []:
            key = entry.get("key")
            if key in ("syh", "fwrq", "wh", "fwdw", "fbjg", "section") and entry.get("value"):
                meta[key] = entry["value"]
    return meta


def scan_csrc_channel(ctx: Context, channel: dict, quota: int, max_pages: int):
    """扫一个栏目的若干页，返回窗口内候选（降序）。"""
    found = []
    for page in range(1, max_pages + 1):
        try:
            results = csrc_page(ctx, channel["guid"], page)
        except FetchError as exc:
            ctx.log(doc_id=None, category="监管公开信息",
                    source=config.SOURCES["监管公开信息"]["source"],
                    url=CSRC_SEARCH_URL.format(channel=channel["guid"]),
                    http_status=None, ok=False, chars=None, byte_size=None, elapsed_ms=0,
                    note="[%s] 第 %d 页失败：%s" % (channel["name"], page, exc))
            break
        if not results:
            break
        oldest = None
        for item in results:
            pub = parse_date(item.get("publishedTimeStr")) or ms_to_date(item.get("publishedTime"))
            oldest = pub if oldest is None else min(oldest, pub or oldest)
            if not in_window(pub):
                continue
            url = (item.get("url") or "").strip()
            if url.startswith("//"):
                url = "https:" + url
            if not url:
                continue
            found.append(Cand(
                category="监管公开信息",
                source=config.SOURCES["监管公开信息"]["source"],
                page_url=url,
                content_url=url,
                title_hint=strip_tags(item.get("title")),
                publish_time=pub,
                company_list=[],
                meta=dict(csrc_meta(item), channel=channel["name"],
                          channelGuid=channel["guid"]),
                kind="csrc_html",
                extra={"api_content": norm_space(item.get("content") or "")},
            ))
        recent = sum(1 for c in found if bucket_of(c.publish_time) == "recent")
        earlier = sum(1 for c in found if bucket_of(c.publish_time) == "earlier")
        if recent >= (quota + 1) // 2 and earlier >= quota - (quota + 1) // 2:
            break
        if oldest is not None and oldest < config.WINDOW_START:
            break
    found.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return found


def discover_csrc(ctx: Context):
    """主来源行政处罚；不足时启用市场禁入（README §4.2）。"""
    quota = ctx.quota["监管公开信息"]
    notes = []
    primary_channel, secondary_channel = CSRC_CHANNELS[0], CSRC_CHANNELS[1]
    primary = scan_csrc_channel(ctx, primary_channel, quota, max_pages=10)
    secondary = []
    secondary_pages = 10 if len(primary) < quota else 1
    secondary = scan_csrc_channel(ctx, secondary_channel, quota, max_pages=secondary_pages)
    if len(primary) < quota:
        notes.append("主来源[%s]窗口内仅 %d 篇（配额 %d），启用备用来源[%s]"
                     % (primary_channel["name"], len(primary), quota, secondary_channel["name"]))
    if not secondary:
        note = ("备用来源[%s]窗口内 0 篇（该栏目最新发文早于窗口下界 %s），未贡献文档"
                % (secondary_channel["name"], config.WINDOW_START))
        notes.append(note)
        ctx.log(doc_id=None, category="监管公开信息",
                source=config.SOURCES["监管公开信息"]["source"],
                url=CSRC_SEARCH_URL.format(channel=secondary_channel["guid"]),
                http_status=200, ok=False, chars=None, byte_size=None, elapsed_ms=0, note=note)
    merged = primary + secondary
    merged.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return merged, notes


def extract_parties(body: str) -> list:
    """从来源文件正文里取 当事人（只读原文，不臆造）。

    只认结构化写法"当事人:"/"当事人："（正文里"向当事人告知…"一类的行文不算），
    因此正文页缺少当事人抬头时返回空列表，由调用方退回同源接口正文再试。
    """
    match = re.search(r"当事人\s*[:：]", body)
    if not match:
        return []
    tail = body[match.end():].lstrip("　 ")
    cut = len(tail)
    for keyword in ["依据", "根据", "经查", "我会", "本案", "上述", "一、"]:
        pos = tail.find(keyword)
        if pos > 0:
            cut = min(cut, pos)
    tail = tail[:min(cut, 400)]
    names = []
    for segment in re.split(r"[。；;\n]", tail):
        segment = segment.strip()
        if not segment:
            continue
        name = re.split(r"[，,、（(]", segment)[0].strip()
        name = re.sub(r"^(姓名|当事人)\s*[:：]?\s*", "", name)
        if 2 <= len(name) <= 40 and re.search(r"[\u4e00-\u9fff]", name) and name not in names:
            names.append(name)
    return names


def fetch_csrc_body(ctx: Context, cand: Cand):
    """抓监管正文页（不可用时退回 searchList 接口自带正文），按 URL 缓存正文与状态。"""
    key = cand.page_url or cand.content_url
    if key in ctx.text_cache:
        return ctx.text_cache[key]
    reused = reused_raw_entry(ctx, cand)
    if reused is not None:
        return cache_text_entry(ctx, key, reused)
    started = time.monotonic()
    status = None
    byte_size = None
    body = ""
    method = "html_bs4"
    note = ""
    try:
        resp = ctx.http.get(cand.page_url, headers={"Referer": CSRC_HOME + "/"})
        status = resp.status_code
        byte_size = len(resp.content)
        if resp.status_code == 200:
            soup = make_soup(decode_html(resp))
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            body = extract_body(soup, ["div.detail-news", "div.content", "div#UCAP-CONTENT"])
    except FetchError as exc:
        note = "监管正文页抓取失败：%s" % exc
    if len(body) < config.MIN_DOC_CHARS:
        api_body = norm_space(cand.extra.get("api_content") or "")
        if len(api_body) >= config.MIN_DOC_CHARS:
            body = api_body
            method = "api_json"
            note = (note + "；正文页不可用，改用 searchList 接口自带正文").strip("；")
    elapsed = int((time.monotonic() - started) * 1000)
    if len(body) < config.MIN_DOC_CHARS:
        return cache_text_entry(ctx, key, {
            "text": body, "ok": False, "chars": len(body), "http_status": status,
            "byte_size": byte_size, "extract_method": method, "elapsed_ms": elapsed,
            "note": note or "正文过短（< MIN_DOC_CHARS=%d）" % config.MIN_DOC_CHARS,
        })
    return cache_text_entry(ctx, key, {
        "text": body, "ok": True, "chars": len(body), "http_status": status,
        "byte_size": byte_size, "extract_method": method, "elapsed_ms": elapsed, "note": note,
    })


def materialize_csrc(ctx: Context, cand: Cand, doc_id: int):
    """把 fetch_csrc_body 的正文按既有口径构造标题（当事人／文号）并生成 raw 记录。"""
    entry = fetch_csrc_body(ctx, cand)
    status = entry.get("http_status")
    byte_size = entry.get("byte_size")
    body = entry.get("text") or ""
    method = entry.get("extract_method") or "html_bs4"
    note = entry.get("note") or ""
    if not entry.get("ok"):
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source,
                url=cand.page_url, http_status=status, ok=False, chars=len(body),
                byte_size=byte_size, elapsed_ms=entry.get("elapsed_ms") or 0,
                note=note or "正文过短（< MIN_DOC_CHARS=%d）" % config.MIN_DOC_CHARS)
        return None
    title = cand.title_hint
    parties = extract_parties(body)
    party_source = "正文页"
    if not parties:
        # 正文页可能不含"当事人:"抬头（实测证监会页面把抬头放在另一块里），
        # 退回同一篇文档在 searchList 接口里的正文，仍然只读来源原文。
        api_body = norm_space(cand.extra.get("api_content") or "")
        parties = extract_parties(api_body)
        if parties:
            party_source = "同源接口正文"
    if parties:
        shown = "、".join(parties[:3]) + ("等" if len(parties) > 3 else "")
        if shown not in title:
            title = "%s（%s）" % (title, shown)
    ctx.log(doc_id=doc_id, category=cand.category, source=cand.source,
            url=cand.page_url, http_status=status, ok=True, chars=len(body),
            byte_size=byte_size, elapsed_ms=entry.get("elapsed_ms") or 0,
            note=(note + "；" if note else "")
                 + "extract_method=%s；当事人=%s（来源：%s）"
                 % (method, "/".join(parties) or "未识别", party_source if parties else "-"))
    meta = dict(cand.meta)
    if parties:
        meta["当事人"] = parties
        meta["当事人来源"] = party_source
    return Doc(doc_id=doc_id, category=cand.category, source=cand.source, title=title,
               company_list=[], publish_time=cand.publish_time, page_url=cand.page_url,
               content_url=cand.content_url, raw_text=body, extract_method=method,
               fetched_at=now_iso(), http_status=status, byte_size=byte_size, meta=meta)


# ==========================================================================
# 7. 采集器三：政策文件（中国政府网政策文件库）
# ==========================================================================
def gov_search_page(ctx: Context, lib_type: str, page: int):
    params = {
        "t": lib_type,
        "q": "",                     # 空关键词＝按发布时间浏览政策文件库（sort=pubtime）
        "timetype": "timeqb",
        "sort": "pubtime",
        "sortType": "1",
        "p": page,
        "n": GOV_PAGE_SIZE,
        "type": "gwyzcwjk",
    }
    resp = ctx.http.get(GOV_SEARCH_URL, params=params, headers={"Referer": GOV_HOME + "/"})
    if resp.status_code != 200:
        return None
    try:
        payload = json_body(resp)
    except ValueError:
        return None
    return ((payload.get("searchVO") or {}).get("listVO")) or []


def discover_gov(ctx: Context):
    """国务院文件 + 部门文件两个库按发布时间倒序翻页，取窗口内候选。"""
    quota = ctx.quota["政策文件"]
    target_recent = (quota + 1) // 2
    target_earlier = quota - target_recent
    found = []
    seen_urls = set()
    max_pages = 12
    for lib_type in GOV_LIB_TYPES:
        if (sum(1 for c in found if bucket_of(c.publish_time) == "recent") >= target_recent
                and sum(1 for c in found if bucket_of(c.publish_time) == "earlier") >= target_earlier):
            break
        for page in range(1, max_pages + 1):
            try:
                items = gov_search_page(ctx, lib_type, page)
            except FetchError as exc:
                ctx.log(doc_id=None, category="政策文件",
                        source=config.SOURCES["政策文件"]["source"],
                        url=GOV_SEARCH_URL, http_status=None, ok=False, chars=None,
                        byte_size=None, elapsed_ms=0,
                        note="政策文件库 %s 第 %d 页失败：%s" % (lib_type, page, exc))
                break
            if not items:
                break
            oldest = None
            for item in items:
                pub = parse_date(item.get("pubtimeStr"))
                oldest = pub if oldest is None else min(oldest, pub or oldest)
                url = (item.get("url") or "").strip()
                if not url or not in_window(pub) or url in seen_urls:
                    continue
                seen_urls.add(url)
                found.append(Cand(
                    category="政策文件",
                    source=config.SOURCES["政策文件"]["source"],
                    page_url=url,
                    content_url=url,
                    title_hint=strip_tags(item.get("title")),
                    publish_time=pub,
                    company_list=[],
                    meta={"puborg": item.get("puborg"), "wenhao": item.get("wenhao"),
                          "pcode": item.get("pcode"), "libtype": lib_type,
                          "summary": item.get("summary")},
                    kind="gov_html",
                ))
            recent = sum(1 for c in found if bucket_of(c.publish_time) == "recent")
            earlier = sum(1 for c in found if bucket_of(c.publish_time) == "earlier")
            if recent >= target_recent and earlier >= target_earlier:
                break
            if oldest is not None and oldest < config.WINDOW_START:
                break
    found.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return found, []


def fetch_gov_body(ctx: Context, cand: Cand):
    """抓政策正文页并抽取正文，按 URL 缓存正文与状态（候选阶段的长度探测共用）。"""
    key = cand.page_url or cand.content_url
    if key in ctx.text_cache:
        return ctx.text_cache[key]
    reused = reused_raw_entry(ctx, cand)
    if reused is not None:
        return cache_text_entry(ctx, key, reused)
    started = time.monotonic()
    try:
        resp = ctx.http.get(cand.page_url, headers={"Referer": GOV_HOME + "/"})
    except FetchError as exc:
        return cache_text_entry(ctx, key, {
            "text": "", "ok": False, "chars": None, "http_status": None, "byte_size": None,
            "extract_method": "html_bs4",
            "elapsed_ms": int((time.monotonic() - started) * 1000),
            "note": "政策正文页抓取失败：%s" % exc,
        })
    elapsed = int((time.monotonic() - started) * 1000)
    if resp.status_code != 200:
        return cache_text_entry(ctx, key, {
            "text": "", "ok": False, "chars": None, "http_status": resp.status_code,
            "byte_size": len(resp.content), "extract_method": "html_bs4", "elapsed_ms": elapsed,
            "note": "政策正文页状态异常",
        })
    soup = make_soup(decode_html(resp))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = extract_body(soup, ["div#UCAP-CONTENT", "div.pages_content", "div.trs_editor_view"])
    if len(body) < config.MIN_DOC_CHARS:
        return cache_text_entry(ctx, key, {
            "text": body, "ok": False, "chars": len(body), "http_status": resp.status_code,
            "byte_size": len(resp.content), "extract_method": "html_bs4", "elapsed_ms": elapsed,
            "note": "政策正文过短（< MIN_DOC_CHARS=%d）" % config.MIN_DOC_CHARS,
        })
    return cache_text_entry(ctx, key, {
        "text": body, "ok": True, "chars": len(body), "http_status": resp.status_code,
        "byte_size": len(resp.content), "extract_method": "html_bs4", "elapsed_ms": elapsed,
        "note": "extract_method=html_bs4（div#UCAP-CONTENT）",
    })


def materialize_gov(ctx: Context, cand: Cand, doc_id: int):
    """把 fetch_gov_body 的结果按既有口径登记并生成 raw 记录（正文只下载一次）。"""
    entry = fetch_gov_body(ctx, cand)
    if not entry.get("ok"):
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source,
                url=cand.page_url, http_status=entry.get("http_status"), ok=False,
                chars=entry.get("chars"), byte_size=entry.get("byte_size"),
                elapsed_ms=entry.get("elapsed_ms") or 0, note=entry.get("note") or "")
        return None
    body = entry["text"]
    ctx.log(doc_id=doc_id, category=cand.category, source=cand.source,
            url=cand.page_url, http_status=entry.get("http_status"), ok=True, chars=len(body),
            byte_size=entry.get("byte_size"), elapsed_ms=entry.get("elapsed_ms") or 0,
            note=entry.get("note") or "")
    return Doc(doc_id=doc_id, category=cand.category, source=cand.source,
               title=cand.title_hint, company_list=[], publish_time=cand.publish_time,
               page_url=cand.page_url, content_url=cand.content_url, raw_text=body,
               extract_method="html_bs4", fetched_at=now_iso(),
               http_status=entry.get("http_status"), byte_size=entry.get("byte_size"),
               meta=dict(cand.meta))


# ==========================================================================
# 8. 采集器四：财经新闻（人民网财经／中证网／证券日报网）
# ==========================================================================
def date_from_url(url: str) -> str | None:
    m = re.search(r"/(20\d{2})/(\d{2})(\d{2})/", url)                 # 人民网 n1/2026/0925/
    if m:
        year, month, day = m.group(1), m.group(2), m.group(3)
    else:
        m = re.search(r"/(20\d{2})[/-](\d{2})[/-](\d{2})(?:/|$)", url)  # cs /2026/09/25/、zqrb /2026-09-24/
        if not m:
            return None
        year, month, day = m.group(1), m.group(2), m.group(3)
    try:
        return datetime(int(year), int(month), int(day)).date().isoformat()
    except ValueError:
        return None


def is_listing_link(url: str, host: str) -> bool:
    if host not in url:
        return False
    return bool(re.search(r"(index(_p\d+)?|page\d+|list_\d+)\.html$", url))


def news_listing_candidates(ctx: Context, site: str, site_cfg: dict, page_budget: int):
    """栏目页静态 HTML → 正文页链接（config.NEWS_SITES 的 article_pattern），并顺带翻页。"""
    pattern = re.compile(site_cfg["article_pattern"])
    entry = site_cfg["entry"]
    host = re.sub(r"^https?://", "", entry).split("/")[0]
    todo = [entry]
    seen_pages = set()
    seen_articles = set()
    cands = []
    while todo and len(seen_pages) < page_budget:
        page_url = todo.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)
        try:
            resp = ctx.http.get(page_url, headers={"Referer": entry})
        except FetchError:
            continue
        if resp.status_code != 200:
            continue
        soup = make_soup(decode_html(resp))
        for anchor in soup.find_all("a", href=True):
            href = urljoin(page_url, anchor["href"])
            if pattern.search(href):
                if href in seen_articles:
                    continue
                seen_articles.add(href)
                date_hint = date_from_url(href)
                if date_hint and not in_window(date_hint):
                    ctx.stats["财经新闻"]["prefiltered"] += 1
                    continue
                cands.append(Cand(
                    category="财经新闻", source=site, page_url=href, content_url=href,
                    title_hint=norm_space(anchor.get_text(" ", strip=True)),
                    publish_time=date_hint, kind="news_html",
                    extra={"discovery": page_url},
                ))
            elif is_listing_link(href, host) and href not in seen_pages and len(todo) < page_budget * 2:
                todo.append(href)
    return cands


def news_search_candidates(ctx: Context, site: str, name: str, page: int):
    """站点自带站内检索（同一站点的检索结果页/接口）：把"提到该公司"的文章找出来。"""
    out = []
    pattern = re.compile(config.NEWS_SITES[site]["article_pattern"])
    if site == "人民网财经":
        payload = {"key": name, "page": page, "limit": NEWS_SEARCH_LIMIT,
                   "hasTitle": True, "hasContent": True, "isFuzzy": False,
                   "type": 0, "sortType": 0, "startTime": 0, "endTime": 0}
        try:
            resp = ctx.http.post(PEOPLE_SEARCH_URL,
                                 data=json.dumps(payload, ensure_ascii=False),
                                 headers={"Content-Type": "application/json",
                                          "Referer": "http://search.people.cn/"})
        except FetchError:
            return out
        if resp.status_code != 200:
            return out
        try:
            records = ((json_body(resp).get("data") or {}).get("records")) or []
        except ValueError:
            return out
        for record in records:
            url = (record.get("url") or "").strip()
            if not url or not pattern.search(url):
                continue
            out.append(Cand(category="财经新闻", source=site, page_url=url, content_url=url,
                            title_hint=strip_tags(record.get("title")),
                            publish_time=ms_to_date(record.get("displayTime")), kind="news_html",
                            extra={"discovery": "site_search:people"}))
    elif site == "中证网":
        params = {"wbId": "1", "page": page, "limit": NEWS_SEARCH_LIMIT,
                  "miContent": name, "field": "", "sort": "pubDate", "pubDateRange": ""}
        try:
            resp = ctx.http.get(CS_SEARCH_URL, params=params,
                                headers={"Referer": "https://www.cs.com.cn/searchlist.html"})
        except FetchError:
            return out
        if resp.status_code != 200:
            return out
        try:
            items = ((json_body(resp).get("page") or {}).get("list")) or []
        except ValueError:
            return out
        for item in items:
            url = (item.get("mmInfo_web_url") or "").strip()
            if not url or not pattern.search(url):
                continue
            out.append(Cand(category="财经新闻", source=site, page_url=url, content_url=url,
                            title_hint=strip_tags(item.get("miLtitle")),
                            publish_time=parse_date(item.get("pubDate")), kind="news_html",
                            extra={"discovery": "site_search:cs"}))
    elif site == "证券日报网":
        params = {"src": "all", "q": name, "f": "_all", "s": "newsdate_DESC"}
        try:
            resp = ctx.http.get(ZQRB_SEARCH_URL, params=params,
                                headers={"Referer": config.NEWS_SITES[site]["entry"]})
        except FetchError:
            return out
        if resp.status_code != 200:
            return out
        soup = make_soup(decode_html(resp))
        for anchor in soup.find_all("a", href=True):
            href = urljoin(ZQRB_SEARCH_URL, anchor["href"])
            if not pattern.search(href):
                continue
            date_hint = date_from_url(href)
            if date_hint and not in_window(date_hint):
                ctx.stats["财经新闻"]["prefiltered"] += 1
                continue
            out.append(Cand(category="财经新闻", source=site, page_url=href, content_url=href,
                            title_hint=norm_space(anchor.get_text(" ", strip=True)),
                            publish_time=date_hint, kind="news_html",
                            extra={"discovery": "site_search:zqrb"}))
    return out


def discover_news(ctx: Context):
    """按 README §4.4 抓栏目页，再用同一站点的站内检索补充公司相关文章（见交付说明）。"""
    quota = ctx.quota["财经新闻"]
    n_sites = max(1, len(config.NEWS_SITES))
    page_budget = min(8, 2 + max(1, quota // n_sites))
    per_site = {}
    for site, site_cfg in config.NEWS_SITES.items():
        merged = []
        seen = set()
        for cand in news_listing_candidates(ctx, site, site_cfg, page_budget):
            if cand.page_url not in seen:
                seen.add(cand.page_url)
                merged.append(cand)
        for company in ctx.companies:
            for name in company_aliases(company):
                for page in range(1, NEWS_SEARCH_PAGES.get(site, 1) + 1):
                    for cand in news_search_candidates(ctx, site, name, page):
                        if cand.page_url not in seen:
                            seen.add(cand.page_url)
                            merged.append(cand)
        merged.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
        per_site[site] = merged
    return per_site


NEWS_SELECTORS = {
    "人民网财经": ["div.rm_txt_con", "div.rm_txt_zw", "div#rwb_zw"],
    "中证网": ["div.cont_article", "div.box_l1", "div.box_ch"],
    "证券日报网": ["div.content-lcq", "div.news_content", "div.nr"],
}

# 发布时间的"正文开头"来源：中证网/证券日报网的日期在署名行里（不在 <p> 正文中）
NEWS_DATE_SELECTORS = {
    "人民网财经": ["div.rm_txt_con", "div.rm_txt_zw"],
    "中证网": ["div.box_l1", "div.box_ch", "div.cont_article"],
    "证券日报网": ["div.nr", "div.news_content", "div.content-lcq"],
}


def news_title(soup: BeautifulSoup) -> str:
    meta = (soup.find("meta", attrs={"property": "og:title"})
            or soup.find("meta", attrs={"name": "og:title"}))
    if meta and meta.get("content"):
        return strip_tags(meta["content"])
    h1 = soup.find("h1")
    if h1 and norm_space(h1.get_text(" ", strip=True)):
        return norm_space(h1.get_text(" ", strip=True))
    if soup.title:
        title = norm_space(soup.title.get_text(" ", strip=True))
        for suffix in ["-证券日报网", "--经济·科技--人民网", "_中国证券报·中证网", "-中证网"]:
            if title.endswith(suffix):
                title = title[: -len(suffix)]
        return norm_space(title)
    return ""


def news_publish_date(soup: BeautifulSoup, date_text: str, body: str, site_cfg: dict) -> str | None:
    """先 <meta name="publishdate">，再正文开头里的日期；都取不到返回 None（按纪律丢弃）。"""
    meta = soup.find("meta", attrs={"name": site_cfg["date_meta"]})
    if meta and meta.get("content"):
        pub = parse_date(meta["content"])
        if pub:
            return pub
    for head in (date_text[:800], body[:600]):
        for pattern in (_RE_DATE_TIME, _RE_DATE):
            m = pattern.search(head)
            if m:
                pub = parse_date(m.group(0))
                if pub:
                    return pub
    return None


def _log_line(cand: Cand, doc_id, status, ok, chars, byte_size, elapsed_ms, note) -> dict:
    return {
        "doc_id": doc_id,
        "category": cand.category,
        "source": cand.source,
        "url": cand.page_url,
        "http_status": status,
        "ok": bool(ok),
        "chars": chars,
        "byte_size": byte_size,
        "elapsed_ms": elapsed_ms,
        "fetched_at": now_iso(),
        "note": note,
    }


def materialize_news(ctx: Context, cand: Cand, doc_id=None):
    """抓正文页 → 标题／发布时间／公司提及过滤。成功时日志延后到 doc_id 分配后写。"""
    cfg = config.NEWS_SITES[cand.source]
    started = time.monotonic()
    try:
        resp = ctx.http.get(cand.page_url, headers={"Referer": cfg["entry"]})
    except FetchError as exc:
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=None, ok=False, chars=None, byte_size=None,
                elapsed_ms=int((time.monotonic() - started) * 1000),
                note="新闻正文页抓取失败：%s" % exc)
        return None
    elapsed = int((time.monotonic() - started) * 1000)
    if resp.status_code != 200:
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=resp.status_code, ok=False, chars=None, byte_size=len(resp.content),
                elapsed_ms=elapsed, note="新闻正文页状态异常")
        return None
    soup = make_soup(decode_html(resp))
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = extract_body(soup, NEWS_SELECTORS.get(cand.source, []))
    if len(body) < config.MIN_DOC_CHARS:
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=resp.status_code, ok=False, chars=len(body),
                byte_size=len(resp.content), elapsed_ms=elapsed, note="新闻正文过短或未抽取到正文")
        return None
    note_probed(ctx, cand.category, cand.page_url)      # 正文已抽取：计入长度上限审计
    date_text = ""
    for selector in NEWS_DATE_SELECTORS.get(cand.source, []):
        node = soup.select_one(selector)
        if node:
            date_text = norm_space(node.get_text(" ", strip=True))
            if date_text:
                break
    pub = news_publish_date(soup, date_text, body, cfg)
    if not pub:
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=resp.status_code, ok=False, chars=len(body),
                byte_size=len(resp.content), elapsed_ms=elapsed,
                note="抽不到发布时间（meta publishdate 与正文日期均缺失），按纪律丢弃，不以抓取日代替")
        return None
    if not in_window(pub):
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=resp.status_code, ok=False, chars=len(body),
                byte_size=len(resp.content), elapsed_ms=elapsed,
                note="发布时间 %s 落在数据时间窗外 [%s, %s]"
                     % (pub, config.WINDOW_START, config.WINDOW_END))
        return None
    company_list = match_companies(body, ctx.companies)
    if not company_list:
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=resp.status_code, ok=False, chars=len(body),
                byte_size=len(resp.content), elapsed_ms=elapsed,
                note="正文未提及 config 配置的公司（名称或 6 位代码），按纪律丢弃")
        return None
    # 正文长度上限（config.MAX_DOC_CHARS_FOR_INCLUSION）：整篇丢弃、绝不截断；对本类别而言
    # 这一步发生在 pick_balanced（level 1 分桶 + level 2 时间铺开）之前，因此被丢弃者不计入
    # 配额，抓取循环会继续取后续候选顶替（README §4.5）。
    if len(body) > length_cap():
        note_length_drop(ctx, cand.category, cand.page_url,
                         news_title(soup) or cand.title_hint, len(body))
        ctx.log(doc_id=doc_id, category=cand.category, source=cand.source, url=cand.page_url,
                http_status=resp.status_code, ok=False, chars=len(body),
                byte_size=len(resp.content), elapsed_ms=elapsed,
                note=("正文 %d 字符超过 config.MAX_DOC_CHARS_FOR_INCLUSION=%d，"
                      "按长度上限**整篇丢弃**（绝不截断）" % (len(body), length_cap())))
        return None
    title = news_title(soup) or cand.title_hint
    note = ("extract_method=html_bs4；company_list=%s；discovery=%s"
            % (",".join(company_list), cand.extra.get("discovery", "")))
    line = _log_line(cand, doc_id, resp.status_code, True, len(body), len(resp.content), elapsed, note)
    if doc_id is None:
        ctx.log_deferred(line)
    else:
        ctx.log_fh.write(json.dumps(line, ensure_ascii=False) + "\n")
        ctx.log_fh.flush()
    return Doc(doc_id=doc_id if doc_id is not None else -1, category=cand.category,
               source=cand.source, title=title, company_list=company_list, publish_time=pub,
               page_url=cand.page_url, content_url=cand.content_url, raw_text=body,
               extract_method="html_bs4", fetched_at=now_iso(),
               http_status=resp.status_code, byte_size=len(resp.content),
               meta={"discovery": cand.extra.get("discovery", ""), "site_entry": cfg["entry"]})


# ==========================================================================
# 9. 各类别执行流程
# ==========================================================================
def plan_announcements(ctx: Context):
    per_company, _notes = discover_announcements(ctx)
    selected = []
    for company, cands, sub_note in per_company:
        need_recent = max(0, int(ctx.ann_strata.get("recent") or 0))
        need_earlier = max(0, int(ctx.ann_strata.get("earlier") or 0))
        picked, drawn, spread_notes, dropped = select_announcements_for_company(ctx, company, cands)
        # 正文长度上限过滤后仍不足配额、且本轮尚未启用替代公司：按 config.subs 的既有口径补足
        # （候选数够、可用候选被长度上限过滤掉的情形；补足同样先过长度上限，绝不截断）。
        # dropped 本身只作审计留痕（明细已由 probe_overlong_candidates 记入 ctx.length_audit），
        # 这里在启用替代公司补足时把替代公司的丢弃也并入同一清单。
        if len(picked) < ctx.ann_per_company and not sub_note:
            sub, sub_cands = fetch_sub_candidates(ctx, company)
            if sub is not None and sub_cands:
                sub_picked, _sub_drawn, _sub_notes, sub_dropped = \
                    select_announcements_for_company(ctx, sub, sub_cands)
                dropped.extend(sub_dropped)
                fill = sub_picked[:ctx.ann_per_company - len(picked)]
                if fill:
                    note = ("主选公司 %s %s 经正文长度上限（config.MAX_DOC_CHARS_FOR_INCLUSION="
                            "%d 字符）过滤后仅剩 %d 篇（每公司配额 %d）；按 config.subs 启用"
                            "预批准替代公司 %s %s 补 %d 篇"
                            % (company["code"], company["name"], length_cap(), len(picked),
                               ctx.ann_per_company, sub["code"], sub["name"], len(fill)))
                    ctx.log(doc_id=None, category="公告", source=config.SOURCES["公告"]["source"],
                            url=CNINFO_QUERY_URL, http_status=None, ok=False, chars=None,
                            byte_size=None, elapsed_ms=0, note=note)
                    picked = newest_first(picked + fill)
        log_spread_notes(ctx, "公告", spread_notes)
        if drawn["recent"] < need_recent or drawn["earlier"] < need_earlier:
            # 某一时段候选不足、由另一时段补足：按约定登记到 raw\_fetch_log.jsonl（ok: true）
            ctx.log(doc_id=None, category="公告", source=config.SOURCES["公告"]["source"],
                    url=CNINFO_QUERY_URL, http_status=None, ok=True, chars=None,
                    byte_size=None, elapsed_ms=0,
                    note=("公告分时段抽取：公司 %s 需要 recent %d 篇 + earlier %d 篇，"
                          "实际 recent %d 篇 + earlier %d 篇"
                          "（recent 缺 %d 篇、earlier 缺 %d 篇，缺口按 config 口径由另一时段补足）"
                          % (company["code"], need_recent, need_earlier,
                             drawn["recent"], drawn["earlier"],
                             max(0, need_recent - drawn["recent"]),
                             max(0, need_earlier - drawn["earlier"]))))
        if len(picked) < ctx.ann_per_company:
            ctx.log(doc_id=None, category="公告", source=config.SOURCES["公告"]["source"],
                    url=CNINFO_QUERY_URL, http_status=None, ok=False, chars=None,
                    byte_size=None, elapsed_ms=0,
                    note="%s %s 窗口内可用公告 %d 篇，低于每公司配额 %d"
                         % (company["code"], company["name"], len(picked), ctx.ann_per_company))
        selected.extend(picked)
    selected.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return selected, materialize_announcement


def select_announcements_for_company(ctx: Context, company: dict, cands):
    """公司内候选 → 公告选择（level 1 时段分层 + level 2 时间铺开），并在**选入之前**过滤超长。

    过滤口径（README §4.5）：每一轮先按既有口径选一轮，逐篇探测正文长度；正文超过
    config.MAX_DOC_CHARS_FOR_INCLUSION 的候选**整篇丢弃**（绝不截断），从候选池剔除后按同一
    口径重选——被丢弃者由次优候选顶替，每公司配额不会因过滤而被抽空。
    返回 (picked, drawn, notes, dropped)。
    """
    pool = list(cands)
    dropped = []
    while True:
        picked, drawn, notes = pick_stratified(pool, ctx.ann_strata,
                                               category="公告", subject=company["code"])
        over = probe_overlong_candidates(ctx, "公告", picked)
        if not over:
            return picked, drawn, notes, dropped
        dropped.extend(over)
        over_ids = {id(c) for c in over}
        pool = [c for c in pool if id(c) not in over_ids]


def plan_csrc(ctx: Context):
    cands, _notes = discover_csrc(ctx)
    selected, spread_notes = pick_balanced_with_length_cap(
        ctx, "监管公开信息", cands, ctx.quota["监管公开信息"])
    log_spread_notes(ctx, "监管公开信息", spread_notes)
    selected.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return selected, materialize_csrc


def plan_gov(ctx: Context):
    cands, _notes = discover_gov(ctx)
    selected, spread_notes = pick_balanced_with_length_cap(
        ctx, "政策文件", cands, ctx.quota["政策文件"])
    log_spread_notes(ctx, "政策文件", spread_notes)
    selected.sort(key=lambda c: (c.publish_time or "", c.page_url), reverse=True)
    return selected, materialize_gov


def resolve_regulator_titles(docs):
    """监管文档标题冲突时用来源文档自带的 索引号（domainMetaList key=syh）消歧。"""
    seen = {}
    for doc in docs:
        title = doc.title
        if title in seen:
            syh = (doc.meta or {}).get("syh", "")
            if syh and "（索引号" not in title:
                doc.title = "%s（索引号 %s）" % (title, syh)
        seen[title] = True
        seen[doc.title] = True
    return docs


def run_simple_category(ctx: Context, category: str, planner):
    """公告／监管／政策：先按候选元数据分配编号（既有 URL 复用），再抓取、落盘。"""
    started = time.monotonic()
    selected, materialize = planner(ctx)
    mapping = ctx.assign_ids(category, selected)
    written_docs = []
    for cand in selected:
        doc_id = mapping[cand.page_url]
        existing = ctx.existing_doc(cand.page_url)
        if existing is not None and existing.get("category") == category and not ctx.force:
            ctx.stats[category]["reused"] += 1
            continue
        doc = materialize(ctx, cand, doc_id)
        if doc is None:
            ctx.stats[category]["skipped"] += 1
            continue
        written_docs.append(doc)
        if category != "监管公开信息":      # 监管标题需在全部抓到后统一消歧，其余立即落盘
            ctx.write_raw(doc)
            ctx.stats[category]["new"] += 1
    if category == "监管公开信息":
        resolve_regulator_titles(written_docs)
        for doc in written_docs:
            ctx.write_raw(doc)
            ctx.stats[category]["new"] += 1
    ctx.stats[category]["elapsed"] = time.monotonic() - started
    return len(written_docs)


def run_news_category(ctx: Context):
    """新闻要抓正文才能判定公司提及与发布时间，因此先抓后选（带预算与提前停止）。"""
    started = time.monotonic()
    quota = ctx.quota["财经新闻"]
    per_site = discover_news(ctx)
    target_recent = (quota + 1) // 2
    target_earlier = quota - target_recent

    have = []
    seen = set()
    for _site, cands in per_site.items():
        for cand in cands:
            if cand.page_url in seen:
                continue
            seen.add(cand.page_url)
            rec = ctx.existing_doc(cand.page_url)
            if rec is not None and rec.get("category") == "财经新闻" and not ctx.force:
                # 旧构建遗留在 raw\ 的超长文档不再参与配额（clean.py 另有 too_long 兜底跳过），
                # 否则配额会被一篇必然被跳过、且会撑爆 chunk.py 的文档占掉。
                raw_text = rec.get("raw_text")
                if isinstance(raw_text, str) and len(raw_text) > length_cap():
                    note_probed(ctx, "财经新闻", cand.page_url)
                    note_length_drop(ctx, "财经新闻", cand.page_url,
                                     rec.get("title") or cand.title_hint, len(raw_text))
                    continue
                have.append(rec)

    recent_have = sum(1 for d in have if bucket_of(doc_pub(d)) == "recent")
    earlier_have = sum(1 for d in have if bucket_of(doc_pub(d)) == "earlier")
    short_bucket = "earlier" if earlier_have < target_earlier else "recent"
    have_urls = {doc_url(d) for d in have}

    order = []
    for _site, cands in per_site.items():
        for cand in cands:
            if cand.page_url not in have_urls:
                order.append(cand)
    # 站内检索命中的候选优先（命中的正文更可能真的提到该公司），同组内按"缺口桶优先"排序
    order.sort(key=lambda c: (0 if str(c.extra.get("discovery", "")).startswith("site_search") else 1,
                              0 if bucket_of(c.publish_time) == short_bucket else 1,
                              -(1 if bucket_of(c.publish_time) == "recent" else 0),
                              c.publish_time or "", c.page_url))

    budget = max(15, 4 * quota)
    fresh = []
    # 每个时间桶的抓取上限：避免"某一桶的候选连续不合格"把预算耗光而另一桶始终没机会
    bucket_cap = {"recent": max(3, 3 * target_recent),
                  "earlier": max(3, 3 * target_earlier), None: 6}
    bucket_used = {"recent": 0, "earlier": 0, None: 0}
    for index, cand in enumerate(order):
        total = len(have) + len(fresh)
        recent_now = recent_have + sum(1 for d in fresh if bucket_of(doc_pub(d)) == "recent")
        earlier_now = earlier_have + sum(1 for d in fresh if bucket_of(doc_pub(d)) == "earlier")
        # 还需要继续抓的条件：某个时间桶没达标，且后面还有该桶的候选（按候选自带日期提示判断）
        rest = order[index:]
        still_missing = ((recent_now < target_recent
                          and any(bucket_of(c.publish_time) == "recent" for c in rest))
                         or (earlier_now < target_earlier
                             and any(bucket_of(c.publish_time) == "earlier" for c in rest)))
        if total >= quota and not still_missing:
            break
        if budget <= 0:
            break
        bucket = bucket_of(cand.publish_time)
        if bucket_used[bucket] >= bucket_cap[bucket]:
            continue
        bucket_used[bucket] += 1
        budget -= 1
        doc = materialize_news(ctx, cand)
        if doc is not None:
            fresh.append(doc)

    docs = list(have) + fresh
    if not docs:
        ctx.stats["财经新闻"]["elapsed"] = time.monotonic() - started
        ctx.flush_deferred({})
        return 0
    # 新闻正文在抓取时就已抽取，长度上限过滤因此在 materialize_news 内完成（超长整篇丢弃、
    # 不计入配额，抓取循环会继续取后续候选顶替，见 README §4.5）；此处按既有口径
    # （level 1 分桶 + level 2 时间铺开）只在**已通过长度上限**的文档上选择。
    picked, spread_notes = pick_balanced(docs, quota, category="财经新闻")
    log_spread_notes(ctx, "财经新闻", spread_notes)
    ordered = sorted(picked, key=lambda d: (doc_pub(d) or "", doc_url(d)), reverse=True)
    id_cands = [Cand(category="财经新闻",
                     source=(d.get("source") if isinstance(d, dict) else d.source),
                     page_url=doc_url(d), publish_time=doc_pub(d))
                for d in ordered]
    mapping = ctx.assign_ids("财经新闻", id_cands)
    for doc in ordered:
        if isinstance(doc, dict):
            ctx.stats["财经新闻"]["reused"] += 1
            continue
        doc.doc_id = mapping[doc.page_url]
        ctx.write_raw(doc)
        ctx.stats["财经新闻"]["new"] += 1
    ctx.flush_deferred(mapping)
    ctx.stats["财经新闻"]["elapsed"] = time.monotonic() - started
    return len(picked)


# ==========================================================================
# 10. meta\sources.csv（T1 来源清单）
# ==========================================================================
def source_rows() -> list:
    rows = [
        {
            "name": config.SOURCES["公告"]["source"],
            "category": "公告",
            "home": config.SOURCES["公告"]["home"],
            "url_template": "POST /new/information/topSearch/query + POST /new/hisAnnouncement/query"
                            " + GET https://static.cninfo.com.cn/{adjunctUrl}",
            "access_note": config.SOURCES["公告"]["access_note"],
            "rate_limit_seconds": config.SOURCES["公告"]["rate_limit_seconds"],
            "notes": "已实测可用（2026-09-25）。PDF 下载必须带浏览器 UA 与 "
                     "Referer: https://www.cninfo.com.cn/；正文用 PyMuPDF 抽取。",
        },
        {
            "name": config.SOURCES["监管公开信息"]["source"],
            "category": "监管公开信息",
            "home": config.SOURCES["监管公开信息"]["home"],
            "url_template": "GET /searchList/{channelGuid}?_isAgg=true&_isJson=true"
                            "&_pageSize=20&_template=index&page={p}",
            "access_note": config.SOURCES["监管公开信息"]["access_note"],
            "rate_limit_seconds": config.SOURCES["监管公开信息"]["rate_limit_seconds"],
            "notes": "主来源行政处罚 17d5ff2fe43e488dba825807ae40d63f；备用来源市场禁入 "
                     "3795869930ca4b70bf55469270a6e641（实测窗口内无发文）。"
                     "标题按《12》§八 修订口径构造成 原标题（当事人），冲突时用索引号消歧。",
        },
        {
            "name": config.SOURCES["政策文件"]["source"],
            "category": "政策文件",
            "home": config.SOURCES["政策文件"]["home"],
            "url_template": "GET https://sousuo.www.gov.cn/search-gov/data?t=zhengcelibrary_gw"
                            "|zhengcelibrary_bm&sort=pubtime&sortType=1&p={p}&n=20&type=gwyzcwjk",
            "access_note": config.SOURCES["政策文件"]["access_note"],
            "rate_limit_seconds": config.SOURCES["政策文件"]["rate_limit_seconds"],
            "notes": "正文页容器 div#UCAP-CONTENT（回退 div.pages_content）。"
                     "空关键词 + sort=pubtime 即政策文件库按发布时间倒序列表。",
        },
    ]
    for site, cfg in config.NEWS_SITES.items():
        rows.append({
            "name": site,
            "category": "财经新闻",
            "home": cfg["entry"],
            "url_template": cfg["article_pattern"],
            "access_note": config.SOURCES["财经新闻"]["access_note"],
            "rate_limit_seconds": config.SOURCES["财经新闻"]["rate_limit_seconds"],
            "notes": "正文页先取 <meta name=publishdate>，缺失时回退正文开头日期；"
                     "两处都取不到即丢弃（不用抓取日代替）。栏目页之外，另用同一站点自带的"
                     "站内检索补充提及本公司（名称或 6 位代码）的文章。",
        })
    return rows


def write_sources_csv(ctx: Context) -> str:
    import csv

    path = os.path.join(ctx.meta_dir, "sources.csv")
    tmp = path + ".tmp"
    fields = ["name", "category", "home", "url_template", "access_note",
              "rate_limit_seconds", "notes"]
    with open(tmp, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in source_rows():
            writer.writerow(row)
    os.replace(tmp, path)
    return path


# ==========================================================================
# 11. 主流程
# ==========================================================================
def summarize(ctx: Context):
    lines = []
    total_files = 0
    for category in config.CATEGORIES:
        files = sum(1 for rec in ctx.existing.values() if rec.get("category") == category)
        total_files += files
        s = ctx.stats[category]
        pages_note = " 公告列表页请求 %d 次" % s.get("pages", 0) if category == "公告" else ""
        audit = length_audit_of(ctx, category)
        lines.append("[%s] raw 文件 %d（本轮新增 %d / 复用 %d） 跳过 %d 失败 %d 预过滤 %d "
                     "超长丢弃 %d（上限 %d 字符，已探测 %d 篇）%s 用时 %.1fs"
                     % (category, files, s["new"], s["reused"], s["skipped"], s["failed"],
                        s["prefiltered"], audit["dropped"], audit["threshold"], audit["probed"],
                        pages_note, s["elapsed"]))
    lines.append("[合计] raw 文件 %d 个；HTTP 请求 %d 次（含重试/异常 %d 次）；输出目录 %s"
                 % (total_files, ctx.http.request_count, ctx.http.error_count, ctx.out_dir))
    return lines, total_files


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="第 5 阶段采集层（T1/T2/T3）：四类来源 → meta/sources.csv + raw/*.json")
    parser.add_argument("--profile", choices=["v1", "pilot"], default="v1")
    parser.add_argument("--dir", default=None, help="仅供自测：覆盖输出根目录")
    parser.add_argument("--force", action="store_true", help="忽略已存在的 raw 文件，强制重取")
    args = parser.parse_args(argv)

    settings = config.profile_settings(args.profile)
    out_dir = args.dir if args.dir else settings["dir"]
    ctx = Context(args.profile, out_dir, args.force)
    started = time.monotonic()
    print("=== fetch.py profile=%s force=%s ===" % (args.profile, args.force))
    print("输出目录：%s" % ctx.out_dir)
    print("公司 %d 家；时间窗 %s ~ %s；配额 %s；公告每公司 %d 篇"
          % (len(ctx.companies), config.WINDOW_START, config.WINDOW_END,
             ctx.quota, ctx.ann_per_company))
    try:
        print("sources.csv → %s" % write_sources_csv(ctx))
        run_simple_category(ctx, "公告", plan_announcements)
        run_simple_category(ctx, "监管公开信息", plan_csrc)
        run_simple_category(ctx, "政策文件", plan_gov)
        run_news_category(ctx)
        log_exclusion_summary(ctx)      # 每个类别一行 ok=true 的排除审计（零排除也写）
        lines, _total = summarize(ctx)
        for line in lines:
            print(line)
        print("[总用时] %.1fs" % (time.monotonic() - started))
    finally:
        ctx.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
