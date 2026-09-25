# -*- coding: utf-8 -*-
r"""T4b 清洗与结构化落盘（第 5 阶段数据准备管线）。

契约（`代码\数据准备\README.md` 一、二、三.3.3／三.3.7；《12-第5阶段任务书》第五节、第八节）：

    输入  raw\{doc_id}.json          只读
          reports\dedup_log.jsonl    T4a 的去重结论（被淘汰的 doc_id 在此排除）
    输出  clean\documents.jsonl      每行一篇，字段逐字对齐 README 第3.3节（=《10》第4.4.1节 document 表）；
                                     subject_companies 与 content_sha256_16 是**数据集内部字段**（不入库）
          reports\clean_stats.json   分类别 before/after 计数、删除字符数、跳过原因
          reports\skipped.jsonl      每条跳过一行（含原因）

清洗口径全部取自 config.CLEAN（不写死）：全角 ASCII 区定向归一（不做整段 NFKC）、
去控制字符、折叠空行、逐行匹配 drop_line_patterns（这些模式是 `^...$` 锚定的正则）。

跳过口径（优先级：去重淘汰 → 正文过短 → 正文超长 → 公告/财经新闻 company_list 为空）：
    1) 被 dedup 淘汰（reports\dedup_log.jsonl 中 dropped 的 doc_id）
    2) 清洗后正文短于 config.MIN_DOC_CHARS
    3) 清洗后正文**超过** config.MAX_DOC_CHARS_FOR_INCLUSION（reason=too_long）
    4) category 属公告/财经新闻但 company_list 为空

第 3 条是**兜底守卫**（README 第3.7节）：正文长度上限在正常流程里由 fetch.py 的候选阶段过滤
（整篇丢弃、绝不截断）保证，clean.py 这一步只是"未来来源变化／旧构建遗留 raw 文件"的防线——
正常一轮运行里它应当始终为 0 条。命中即整篇跳过并登记实测字符数，绝不放行到 chunk.py
（单篇超过 DOC_ID_STRIDE 个文本块会让 chunk_id = doc_id * DOC_ID_STRIDE + chunk_index 越界）。

本模块同时对外提供三个纯函数，供 dedup.py 复用，避免同一规则两处实现漂移：
    clean_body(raw_text)        清洗正文（内容等价于落盘的 content）
    normalize_title(title)      标题规范化（config.DEDUP["title_normalize"] 的三条）
    content_fingerprint(text)   正文指纹（config.DEDUP["content_fingerprint"]：sha256 前 16 位）
因为 dedup.py 的正文判重键由 clean_body + content_fingerprint 生成，
clean\documents.jsonl 中 content_sha256_16 的唯一性由构造保证。

另有两条 第八节 修订后的取值口径：
    * 公告与财经新闻的 company_list 必须非空；政策文件与监管公开信息允许空数组（不得为 null）；
    * 监管公开信息的同题文档只在"原标题（当事人）"构造后判重，仍冲突时只允许用来源自带的
      文号／索引号消歧（source_disambiguator / disambiguated_title，绝不臆造当事人）。

另有一个**只增不改**的严格口径（README 第3.3节、第5.3节；《14-前五阶段审核报告》第3.4节）：
    * subject_companies：从 company_list 里再筛一层"文档**关于**的公司"（阈值取自
      config.SUBJECT_MENTION_MIN，不写死）。company_list 的口径（"文档涉及的公司"，
      检索仍用它）**一个字都不改**；本字段只是新增，且必须落在 company_list 之内。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
import unicodedata

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import config  # noqa: E402  唯一参数来源，不得写死任何参数

# 全角空格（含不换行空格）：对应 config.DEDUP["title_normalize"] 的"去除全角空格"
_FULLWIDTH_SPACES = ("\u3000", "\u00a0")
_DROP_LINE_RES = [re.compile(p) for p in config.CLEAN["drop_line_patterns"]]
_CONTROL_CATEGORIES = ("Cc", "Cf")          # 控制字符与格式字符（\n 保留）

# 全角 → 半角（config.CLEAN["normalize_fullwidth_ascii"]）：**只**折算全角 ASCII 区——
# U+FF10–U+FF19 数字、U+FF21–U+FF3A／U+FF41–U+FF5A 字母、U+3000 表意空格；
# 中文标点（U+FF0C 全角逗号、U+3002 句号、U+FF1A 冒号、U+FF08/FF09 括号、
# U+201C/U+201D/U+2018/U+2019 引号等）一律不在表内，按 config.CLEAN
# ["preserve_cjk_punctuation"] 逐字保留，绝不折成 ASCII ","／"()" 等。
_FULLWIDTH_ASCII_MAP = dict(
    [(c, c - 0xFEE0) for c in range(0xFF10, 0xFF1A)]     # ０-９ → 0-9
    + [(c, c - 0xFEE0) for c in range(0xFF21, 0xFF3B)]   # Ａ-Ｚ → A-Z
    + [(c, c - 0xFEE0) for c in range(0xFF41, 0xFF5B)]   # ａ-ｚ → a-z
    + [(0x3000, 0x20)]                                   # 表意空格 → ASCII 空格
)

# 正文指纹规则：从 config.DEDUP["content_fingerprint"]（形如 "sha256_16"）解析，不写死长度
_FP_ALGO, _, _FP_HEX_LEN = str(config.DEDUP["content_fingerprint"]).partition("_")
_FP_HEX_LEN = int(_FP_HEX_LEN)

# 《12》第八节 修订后：监管公开信息（行政处罚决定书等）同题文档天然存在多条，标题须先按
# "原标题（当事人）"构造后才允许判重；若仍冲突，只允许用来源文档自身已有的文号／索引号消歧，
# 不得臆造标题。本脚本只做后一半：用来源自带的文号／索引号消歧，绝不生成当事人名。
REGULATOR_CATEGORY = "监管公开信息"
_DISAMBIGUATOR_META_KEYS = ("索引号", "syh", "文号", "wenhao", "公告编号", "announcementId",
                            "index_no", "case_no")

SKIP_DEDUP_DROPPED = "dedup_dropped"
SKIP_TOO_SHORT = "too_short"
SKIP_TOO_LONG = "too_long"
SKIP_EMPTY_COMPANY = "empty_company_list"


def max_doc_chars_for_inclusion() -> int:
    """正文长度上限（唯一来源 config.MAX_DOC_CHARS_FOR_INCLUSION，不写死）。"""
    return int(config.MAX_DOC_CHARS_FOR_INCLUSION)


SKIP_PRIORITY = [SKIP_DEDUP_DROPPED, SKIP_TOO_SHORT, SKIP_TOO_LONG, SKIP_EMPTY_COMPANY]


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=r"第 5 阶段 T4b：清洗 raw\ 并落盘 clean\documents.jsonl（含跳过清单）"
    )
    parser.add_argument("--profile", choices=["v1", "pilot"], default="v1",
                        help="数据集形态：v1（默认）或 pilot")
    parser.add_argument("--dir", dest="dir_override", default=None,
                        help="仅供自测：把数据集根目录改到任意临时目录")
    parser.add_argument("--force", action="store_true",
                        help="忽略已完成标记，强制重跑本环节")
    return parser.parse_args(argv)


def resolve_root(args) -> str:
    if args.dir_override:
        return os.path.abspath(args.dir_override)
    return os.path.abspath(config.dataset_dir(args.profile))


# --------------------------------------------------------------------------
# 纯函数：正文清洗 / 标题规范化 / 正文指纹（dedup.py 复用）
# --------------------------------------------------------------------------
def clean_body(raw_text) -> str:
    """按 config.CLEAN 清洗正文；只做文本规范化，不做分词与抽取（《12》第七节）。"""
    text = "" if raw_text is None else str(raw_text)

    if config.CLEAN.get("normalize_unicode_nfkc"):
        text = unicodedata.normalize("NFKC", text)

    if config.CLEAN.get("normalize_fullwidth_ascii"):
        text = text.translate(_FULLWIDTH_ASCII_MAP)

    if config.CLEAN.get("strip_control_chars"):
        text = "".join(
            ch for ch in text
            if ch == "\n" or unicodedata.category(ch) not in _CONTROL_CATEGORIES
        )

    lines = text.split("\n")

    if config.CLEAN.get("collapse_blank_lines"):
        collapsed = []
        blank_run = 0
        for line in lines:
            if line.strip() == "":
                blank_run += 1
                if blank_run > 1:
                    continue
            else:
                blank_run = 0
            collapsed.append(line)
        lines = collapsed

    kept = []
    for line in lines:
        stripped = line.strip()
        if any(rx.match(stripped) for rx in _DROP_LINE_RES):
            continue
        kept.append(stripped)
    return "\n".join(kept).strip()


def normalize_title(title) -> str:
    """标题规范化：去全角空格 → 合并连续空白 → 去首尾空白（config.DEDUP["title_normalize"]）。"""
    text = "" if title is None else str(title)
    for space in _FULLWIDTH_SPACES:
        text = text.replace(space, "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def content_fingerprint(text: str) -> str:
    """正文指纹：sha256 十六进制前 _FP_HEX_LEN 位（长度取自 config.DEDUP）。"""
    if _FP_ALGO != "sha256":
        raise ValueError("config.DEDUP['content_fingerprint'] 只实现了 sha256，当前为 %r" % _FP_ALGO)
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()[:_FP_HEX_LEN]


def source_disambiguator(raw_doc) -> str:
    """取来源文档自身已有的文号／索引号（用于监管公开信息的同题消歧）；没有则返回空串。

    只读来源字段，不从正文推断、不臆造（《12》第八节）。dedup.py 复用同一实现作为判重键的扩展。
    """
    if not config.DEDUP.get("regulator_title_disambiguation"):
        return ""
    if str(raw_doc.get("category") or "") != REGULATOR_CATEGORY:
        return ""
    meta = raw_doc.get("meta")
    if isinstance(meta, dict):
        for key in _DISAMBIGUATOR_META_KEYS:
            value = meta.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    for key in _DISAMBIGUATOR_META_KEYS:
        value = raw_doc.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def disambiguated_title(title: str, raw_doc) -> str:
    """监管公开信息：把来源自带的文号／索引号并入标题（"原标题（文号）"），其余类别原样返回。"""
    tag = source_disambiguator(raw_doc)
    if not tag or tag in title:
        return title
    return "%s（%s）" % (title, tag)


def normalize_company_list(value):
    """company_list 一律返回 list（可能为空），永不为 None；元素为非空字符串、去重保序。"""
    if value is None:
        return []
    if isinstance(value, str):
        parts = re.split(r"[,，;；\s]+", value)
    elif isinstance(value, (list, tuple, set)):
        parts = [str(item) for item in value]
    else:
        parts = [str(value)]
    return list(dict.fromkeys(p.strip() for p in parts if p and p.strip()))


# --------------------------------------------------------------------------
# subject_companies（数据集内部字段，不入库）：文档**关于**的公司
# --------------------------------------------------------------------------
# 规则（阈值唯一来源 config.SUBJECT_MENTION_MIN，脚本内不写死）：公司在 company_list 内，
# 且满足其一即计入——① 其名称或 6 位代码出现在 title 中；② 其名称出现次数 ＋ 代码出现次数
# 在 content 中 ≥ SUBJECT_MENTION_MIN。只在 company_list 内部判定，绝不引入 company_list
# 之外的公司；company_list 本身保持"文档涉及的公司"口径不变（它是检索用的字段）。
# 名称与代码以 config.COMPANIES 为准（代码→名称；company_list 里的代码不在 config 时
# 只按代码本身计数，不臆造名称）。
_COMPANY_NAME_BY_CODE = {str(c["code"]): str(c["name"]) for c in config.COMPANIES}


def mention_count(text: str, needle: str) -> int:
    """needle 在 text 中的出现次数（按字面计数；needle 为空串时记 0）。"""
    if not needle:
        return 0
    return str(text).count(str(needle))


def subject_companies_of(title, content, company_list, category="") -> list:
    """按 config.SUBJECT_MENTION_MIN 从 company_list 中筛出文档主题公司（保序、去重）。

    两条例外（v1.1 首轮实测后补，见《14-前五阶段审核报告》第9.3节）：

    ① **公告不做文本判定**。公告的主体就是发布它的公司——`company_list` 取自交易所接口的
       `secCode`，整篇公告天然是关于这家公司的。首轮实测的假阴性正出在这里：万科A 的 5 篇
       自家公告因标题写"万科"而非"万科A"被判为空，那是规则错，不是数据错。
    ② **名称补 A／B 别名**。配置里的名称可能带 A／B 后缀（如"万科A"），而正文通常只写
       "万科"；去掉尾部单个 A／B 后一并计数，避免同一家公司被自己的简称判掉。
    """
    minimum = int(config.SUBJECT_MENTION_MIN)
    title = "" if title is None else str(title)
    content = "" if content is None else str(content)
    codes = normalize_company_list(company_list)
    if category == "公告":
        return list(dict.fromkeys(codes))
    subjects = []
    for code in codes:
        name = _COMPANY_NAME_BY_CODE.get(code, "")
        alias = re.sub(r"[ABab]$", "", name) if name else ""
        if (name and name in title) or (alias and alias in title) or code in title:
            subjects.append(code)
            continue
        hits = mention_count(content, name) + mention_count(content, code)
        if alias and alias != name:
            hits += mention_count(content, alias)
        if hits >= minimum:
            subjects.append(code)
    return list(dict.fromkeys(subjects))


def run_timestamp() -> str:
    """本次运行的单一 ingest_time（ISO8601，时区取自 config.TIMEZONE）。"""
    offset = str(config.TIMEZONE)
    sign = -1 if offset.startswith("-") else 1
    hh, mm = offset.lstrip("+-").split(":")
    tz = _dt.timezone(sign * _dt.timedelta(hours=int(hh), minutes=int(mm)))
    return _dt.datetime.now(tz).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------
# 读入
# --------------------------------------------------------------------------
def collect_raw_paths(raw_dir: str):
    names = sorted(n for n in os.listdir(raw_dir)
                   if n.endswith(".json") and not n.startswith("_"))
    return [os.path.join(raw_dir, n) for n in names]


def load_raw_docs(raw_dir: str):
    docs = []
    seen = set()
    for path in collect_raw_paths(raw_dir):
        with open(path, "r", encoding="utf-8") as fh:
            obj = json.load(fh)
        if not isinstance(obj, dict) or "doc_id" not in obj:
            raise ValueError("raw 文件缺少 doc_id 字段：%s" % path)
        doc_id = int(obj["doc_id"])
        if doc_id in seen:
            raise ValueError("raw 目录内 doc_id 重复：%d" % doc_id)
        seen.add(doc_id)
        docs.append(obj)
    docs.sort(key=lambda d: int(d["doc_id"]))
    return docs


def load_dedup_drops(log_path: str):
    """读 T4a 结论：返回 {doc_id: 命中该 doc_id 的裁决记录}。"""
    drops = {}
    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            for doc_id in rec.get("dropped", []):
                drops[int(doc_id)] = rec
    return drops


def is_up_to_date(outputs, inputs) -> bool:
    if not all(os.path.exists(p) for p in outputs):
        return False
    if not inputs:
        return True
    return min(os.path.getmtime(p) for p in outputs) >= max(os.path.getmtime(p) for p in inputs)


# --------------------------------------------------------------------------
# 落盘
# --------------------------------------------------------------------------
def write_jsonl(path: str, records) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False, sort_keys=False) + "\n")
    os.replace(tmp, path)


def write_json(path: str, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False) + "\n")
    os.replace(tmp, path)


def empty_category_stats():
    return {"raw_docs": 0, "dedup_dropped": 0, "cleaned": 0, "emitted": 0,
            "chars_before": 0, "chars_after": 0, "chars_removed": 0,
            "skipped": {reason: 0 for reason in SKIP_PRIORITY}}


# --------------------------------------------------------------------------
def main(argv=None) -> int:
    t0 = time.perf_counter()
    args = parse_args(argv)
    root = resolve_root(args)
    raw_dir = os.path.join(root, "raw")
    clean_dir = os.path.join(root, "clean")
    reports_dir = os.path.join(root, "reports")
    dedup_log = os.path.join(reports_dir, "dedup_log.jsonl")
    documents_path = os.path.join(clean_dir, "documents.jsonl")
    stats_path = os.path.join(reports_dir, "clean_stats.json")
    skipped_path = os.path.join(reports_dir, "skipped.jsonl")

    if not os.path.isdir(raw_dir):
        print("[clean] 错误：找不到 raw\\ 目录：%s" % raw_dir, file=sys.stderr)
        return 2
    if not os.path.exists(dedup_log):
        print("[clean] 错误：找不到去重结论 %s，请先运行 dedup.py" % dedup_log, file=sys.stderr)
        return 2

    raw_paths = collect_raw_paths(raw_dir)
    docs = load_raw_docs(raw_dir)
    if not docs:
        print("[clean] 错误：raw\\ 目录内没有 {doc_id}.json：%s" % raw_dir, file=sys.stderr)
        return 2
    drops = load_dedup_drops(dedup_log)

    if not args.force and is_up_to_date([documents_path, stats_path, skipped_path],
                                        raw_paths + [dedup_log]):
        print("[clean] 已完成，跳过（--force 可强制重跑）：%s" % documents_path)
        return 0

    ingest_time = run_timestamp()
    documents = []
    skipped = []
    per_category = {cat: empty_category_stats() for cat in config.CATEGORIES}
    skip_reasons = {reason: 0 for reason in SKIP_PRIORITY}
    unexpected_categories = []
    url_fallback_doc_ids = []
    empty_company_emitted = {}
    disambiguators = {}

    for doc in docs:
        doc_id = int(doc["doc_id"])
        category = str(doc.get("category") or "")
        stats = per_category.setdefault(category, empty_category_stats())
        stats["raw_docs"] += 1
        if category not in config.CATEGORIES and category not in unexpected_categories:
            unexpected_categories.append(category)

        # 1) 去重淘汰：不参与清洗（raw\ 不修改，结论来自 dedup_log.jsonl）
        if doc_id in drops:
            decision = drops[doc_id]
            stats["dedup_dropped"] += 1
            skip_reasons[SKIP_DEDUP_DROPPED] += 1
            stats["skipped"][SKIP_DEDUP_DROPPED] += 1
            skipped.append({
                "doc_id": doc_id,
                "category": category,
                "source": str(doc.get("source") or ""),
                "reason": SKIP_DEDUP_DROPPED,
                "detail": "与 doc_id=%s 冲突（rule=%s，保留方 publish_time=%s）"
                          % (decision.get("winner"), decision.get("rule"),
                             decision.get("winner_publish_time", "")),
                "rule": decision.get("rule"),
                "winner": decision.get("winner"),
            })
            continue

        raw_text = doc.get("raw_text")
        content = clean_body(raw_text)
        stats["cleaned"] += 1
        stats["chars_before"] += len("" if raw_text is None else str(raw_text))
        stats["chars_after"] += len(content)

        # 2) 正文过短
        if len(content) < int(config.MIN_DOC_CHARS):
            stats["skipped"][SKIP_TOO_SHORT] += 1
            skip_reasons[SKIP_TOO_SHORT] += 1
            skipped.append({
                "doc_id": doc_id,
                "category": category,
                "source": str(doc.get("source") or ""),
                "reason": SKIP_TOO_SHORT,
                "detail": "清洗后正文 %d 字符 < MIN_DOC_CHARS=%d"
                          % (len(content), int(config.MIN_DOC_CHARS)),
            })
            continue

        # 3) 正文超长兜底守卫（README 第3.7节）：长度上限的**正常**落点是 fetch.py 的候选阶段
        #    过滤（整篇丢弃，绝不截断），本步只为"未来来源变化／旧构建遗留 raw 文件"兜底。
        #    正常一轮运行里这里应当始终为 0 条；命中即整篇跳过并登记实测字符数，绝不放行到
        #    chunk.py（单篇超过 DOC_ID_STRIDE 个文本块会让 chunk_id 越界）。
        if len(content) > max_doc_chars_for_inclusion():
            stats["skipped"][SKIP_TOO_LONG] += 1
            skip_reasons[SKIP_TOO_LONG] += 1
            skipped.append({
                "doc_id": doc_id,
                "category": category,
                "source": str(doc.get("source") or ""),
                "reason": SKIP_TOO_LONG,
                "chars": len(content),
                "detail": "清洗后正文 %d 字符 > MAX_DOC_CHARS_FOR_INCLUSION=%d"
                          "（长度上限的正常落点是 fetch.py 的候选阶段过滤，此处为兜底守卫）"
                          % (len(content), max_doc_chars_for_inclusion()),
            })
            continue

        # 4) 公告与财经新闻的 company_list 必须非空（政策文件与监管公开信息允许空数组）
        #    需非空的类别取自 config.CATEGORIES_REQUIRING_COMPANY（不复制字面量）
        company_list = normalize_company_list(doc.get("company_list"))
        if category in config.CATEGORIES_REQUIRING_COMPANY and not company_list:
            stats["skipped"][SKIP_EMPTY_COMPANY] += 1
            skip_reasons[SKIP_EMPTY_COMPANY] += 1
            skipped.append({
                "doc_id": doc_id,
                "category": category,
                "source": str(doc.get("source") or ""),
                "reason": SKIP_EMPTY_COMPANY,
                "detail": "%s 的 company_list 为空（《12》第八节 修订后要求非空）" % category,
            })
            continue

        if not company_list:
            empty_company_emitted[category] = empty_company_emitted.get(category, 0) + 1

        content_url = str(doc.get("content_url") or "").strip()
        page_url = str(doc.get("page_url") or "").strip()
        url = content_url or page_url
        if not content_url and page_url:
            url_fallback_doc_ids.append(doc_id)

        title = normalize_title(doc.get("title"))
        documents.append({
            "doc_id": doc_id,
            "title": title,
            "content": content,
            "source": str(doc.get("source") or ""),
            "category": category,
            "url": url,
            "publish_time": str(doc.get("publish_time") or ""),
            "ingest_time": ingest_time,
            "company_list": company_list,
            "content_sha256_16": content_fingerprint(content),
        })
        disambiguators[doc_id] = source_disambiguator(doc)
        stats["emitted"] += 1

    for stats in per_category.values():
        stats["chars_removed"] = stats["chars_before"] - stats["chars_after"]

    documents.sort(key=lambda d: d["doc_id"])
    skipped.sort(key=lambda s: s["doc_id"])

    # 监管公开信息同题标题：用来源自带的文号／索引号消歧（《12》第八节 修订后；不臆造当事人）。
    # 消歧键与 dedup.py 的 title 判重键一致，因此 dedup 保留的同题文档在这里一定拿到不同标题。
    title_groups = {}
    for rec in documents:
        title_groups.setdefault(rec["title"], []).append(rec["doc_id"])
    by_doc_id = {rec["doc_id"]: rec for rec in documents}
    raw_doc_by_id = {int(d["doc_id"]): d for d in docs}
    disambiguation = {"applied": False, "groups": 0, "by_doc_id": {}}
    for title in sorted(title_groups):
        group = title_groups[title]
        if len(group) < 2:
            continue
        disambiguation["groups"] += 1
        for one in group:
            tag = disambiguators.get(one) or ""
            if not tag:
                continue
            by_doc_id[one]["title"] = disambiguated_title(by_doc_id[one]["title"], raw_doc_by_id[one])
            disambiguation["by_doc_id"][str(one)] = tag
            disambiguation["applied"] = True
    final_titles = {}
    for rec in documents:
        final_titles.setdefault(rec["title"], []).append(rec["doc_id"])
    residual_duplicate_titles = {t: ids for t, ids in final_titles.items() if len(ids) > 1}

    # subject_companies（数据集内部字段，不入库）：在标题消歧**之后**计算，保证与落盘的
    # title／content 逐字一致；只在 company_list 内部筛（阈值 config.SUBJECT_MENTION_MIN），
    # company_list 本身不动（README 第3.3节、第5.3节；《14》第3.4节）。
    for rec in documents:
        rec["subject_companies"] = subject_companies_of(rec["title"], rec["content"], rec["company_list"],
                                                          rec.get("category", ""))

    totals = {
        "raw_docs": sum(s["raw_docs"] for s in per_category.values()),
        "dedup_dropped": sum(s["dedup_dropped"] for s in per_category.values()),
        "cleaned": sum(s["cleaned"] for s in per_category.values()),
        "emitted": len(documents),
        "skipped": len(skipped),
        "chars_before": sum(s["chars_before"] for s in per_category.values()),
        "chars_after": sum(s["chars_after"] for s in per_category.values()),
    }
    totals["chars_removed"] = totals["chars_before"] - totals["chars_after"]

    stats_obj = {
        "note": ("chars_before/chars_after 只统计进入清洗的文档（被去重淘汰的文档不清洗）；"
                 "chars_removed = chars_before - chars_after；"
                 "url 取 content_url，缺失时回退 page_url；"
                 "只做全角 ASCII 区定向归一（不做整段 NFKC），中文标点逐字保留；"
                 "config.CLEAN['drop_line_patterns'] 不含 ^\\s*$，空行由 collapse_blank_lines "
                 "折叠成单个空行，段落边界 \\n\\n 得以保留。"),
        "params": {
            "min_doc_chars": int(config.MIN_DOC_CHARS),
            "max_doc_chars_for_inclusion": max_doc_chars_for_inclusion(),
            "max_doc_chars_for_inclusion_role": ("兜底守卫（reason=too_long）；长度上限的"
                                                 "正常落点是 fetch.py 的候选阶段过滤"),
            "normalize_fullwidth_ascii": bool(config.CLEAN.get("normalize_fullwidth_ascii")),
            "normalize_unicode_nfkc": bool(config.CLEAN.get("normalize_unicode_nfkc")),
            "preserve_cjk_punctuation": bool(config.CLEAN.get("preserve_cjk_punctuation")),
            "collapse_blank_lines": bool(config.CLEAN.get("collapse_blank_lines")),
            "strip_control_chars": bool(config.CLEAN.get("strip_control_chars")),
            "drop_line_patterns": list(config.CLEAN["drop_line_patterns"]),
            "content_fingerprint": str(config.DEDUP["content_fingerprint"]),
            "categories": list(config.CATEGORIES),
            "categories_requiring_company_list": list(config.CATEGORIES_REQUIRING_COMPANY),
        },
        "skip_priority": list(SKIP_PRIORITY),
        "totals": totals,
        "per_category": per_category,
        "skip_reasons": skip_reasons,
        "unexpected_categories": unexpected_categories,
        "url_fallback_to_page_url_doc_ids": sorted(url_fallback_doc_ids),
        "empty_company_list_emitted": empty_company_emitted,
        "regulator_title_disambiguation": disambiguation,
        "residual_duplicate_titles": residual_duplicate_titles,
    }

    write_jsonl(documents_path, documents)
    write_jsonl(skipped_path, skipped)
    write_json(stats_path, stats_obj)
    if residual_duplicate_titles:
        print("[clean] 警告：仍有重复标题（无来源文号／索引号可消歧）：%s"
              % sorted(residual_duplicate_titles), file=sys.stderr)

    print("[clean] profile=%s dir=%s 输入=%d 条，输出=%d 条，跳过=%d 条（%s），删字符=%d，"
          "ingest_time=%s，耗时=%.2fs"
          % (args.profile, root, len(docs), len(documents), len(skipped),
             "，".join("%s:%d" % (k, v) for k, v in skip_reasons.items() if v),
             totals["chars_removed"], ingest_time, time.perf_counter() - t0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
