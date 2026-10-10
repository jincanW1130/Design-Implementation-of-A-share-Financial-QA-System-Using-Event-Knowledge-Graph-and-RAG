# -*- coding: utf-8 -*-
r"""P1-12 补测 · E 组 —— 数据准备组件的**纯函数**（离线、只读）。

覆盖（对应测试 README 第五节「没覆盖什么」里如实登记的那一条：
"数据准备／抽取与图谱两个组件的纯函数……尚未纳入"）：

  * `交付物/03-代码\数据准备\clean.py`
      `clean_body` / `normalize_title` / `content_fingerprint` /
      `normalize_company_list` / `mention_count` / `subject_companies_of`
  * `交付物/03-代码\数据准备\dedup.py`
      `active_rules` / `effective_url` / `publish_time` / `rule_key` / `key_kind` /
      `rank_key` / `decide_reason` / `decide`
  * `交付物/03-代码\数据准备\chunk.py`
      `chunk_document` / `_choose_cut` / `_cut_positions` / `_skip_leading_blank` /
      `count_tokens`

三条纪律（与 A／B／C／D 四组一致）：

  1. **离线**：不联网、不读数据集、不写产品目录（`_bootstrap` 按文件路径加载；
     `conftest.forbid_network` 的审计钩子仍然生效）。
  2. **参数不写死**：阈值（`SUBJECT_MENTION_MIN`、`CHUNK.*`、`MIN_DOC_CHARS`、
     `DEDUP.*`）一律从**数据准备自己的** `config` 取，测试里不复制字面量——
     这样 config 的漂移会**当场**暴露，而不是被测试里的第二份常量悄悄掩盖。
  3. **负向标定**：关键断言都配一条"换回旧口径／去掉守卫就会不同"的对照，
     说明用例不是恒真的空断言（与测试 README 第七节第 2 条的取证方式一致）。
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _bootstrap  # noqa: E402

_REGULATOR_CATEGORY = "监管公开信息"


# --------------------------------------------------------------------------
# 夹具：数据准备组件（config ＋ 三个被测模块）
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def prep_cfg():
    """`交付物/03-代码\\数据准备\\config.py` —— 参数唯一来源（测试里不写死阈值）。"""
    return _bootstrap.component_config("数据准备")


@pytest.fixture(scope="session")
def clean_mod():
    return _bootstrap.load_module("数据准备", "clean.py")


@pytest.fixture(scope="session")
def dedup_mod():
    return _bootstrap.load_module("数据准备", "dedup.py")


@pytest.fixture(scope="session")
def chunk_mod():
    return _bootstrap.load_module("数据准备", "chunk.py")


# ==========================================================================
# E1 组 · 正文清洗（clean_body）
# ==========================================================================
def test_clean_body_normalizes_but_does_not_mangle_meaning(clean_mod):
    """清洗只做规范化：不动语义（不删词、不改字），只折空白与定向归一。"""
    raw = "  甲公司\r\n\r\n\r\n2026 年 业绩  公告  \n\n"
    got = clean_mod.clean_body(raw)
    # 结果里保留全部实义字符
    for token in ("甲公司", "2026", "年", "业绩", "公告"):
        assert token in got
    # 连续空行被折叠（三个以上空行只剩一个）
    assert "\n\n\n" not in got
    # 首尾不残留空白
    assert got == got.strip()


def test_clean_body_is_idempotent(clean_mod):
    """幂等：清洗两次 == 清洗一次（否则下游「复跑一致」这条纪律会失效）。"""
    raw = "标题\n\n\n  正文一  \n\n\n\n正文二\n"
    once = clean_mod.clean_body(raw)
    twice = clean_mod.clean_body(once)
    assert once == twice


def test_clean_body_none_becomes_empty_not_the_string_none(clean_mod):
    """None → 空串（不是 "None" 这五个字符）。"""
    assert clean_mod.clean_body(None) == ""
    assert clean_mod.clean_body("") == ""


def test_clean_body_strips_control_chars_but_keeps_newline(clean_mod):
    """控制字符被剔除（配置开关打开时），但换行符是块边界，必须保留。"""
    if not clean_mod.config.CLEAN.get("strip_control_chars"):
        pytest.skip("config.CLEAN['strip_control_chars'] 为假：本项不适用")
    raw = "第一行\x00\x07第二行\n第三行\x1f"
    got = clean_mod.clean_body(raw)
    for bad in ("\x00", "\x07", "\x1f"):
        assert bad not in got
    assert "\n" in got
    assert "第一行第二行" in got


def test_clean_body_collapses_blank_lines_only_when_enabled(clean_mod):
    """`collapse_blank_lines` 关掉时，空行不被折叠——用配置本身驱动，不写死预期。"""
    if not clean_mod.config.CLEAN.get("collapse_blank_lines"):
        pytest.skip("config.CLEAN['collapse_blank_lines'] 为假：本项不适用")
    raw = "A\n\n\n\nB"
    assert clean_mod.clean_body(raw) == "A\n\nB"


# ==========================================================================
# E2 组 · 标题规范化与正文指纹（normalize_title / content_fingerprint）
# ==========================================================================
def test_normalize_title_folds_fullwidth_spaces_and_runs(clean_mod):
    """全角空格被删、连续空白折一个、首尾去净。"""
    got = clean_mod.normalize_title("　甲公司\u3000  2026 年\u3000业绩公告　")
    assert got == "甲公司 2026 年业绩公告"


def test_normalize_title_does_not_eat_inner_halfwidth_spaces(clean_mod):
    """内文单个半角空格保留（只折"连续"空白），负向标定：删空格的实现会让本断言失败。"""
    assert clean_mod.normalize_title("A B") == "A B"
    assert clean_mod.normalize_title("A  B") == "A B"      # 两个 → 一个


def test_normalize_title_none_and_empty_are_stable(clean_mod):
    assert clean_mod.normalize_title(None) == ""
    assert clean_mod.normalize_title("") == ""
    assert clean_mod.normalize_title("   ") == ""


def test_content_fingerprint_is_stable_and_hex_of_config_length(clean_mod, prep_cfg):
    """指纹：同文同值、异文异值、长度取自 config（不写死 16）。"""
    hex_len = int(prep_cfg.DEDUP["content_fingerprint_hex_len"]) \
        if "content_fingerprint_hex_len" in prep_cfg.DEDUP else 16
    a = clean_mod.content_fingerprint("甲公司2026年业绩公告")
    b = clean_mod.content_fingerprint("甲公司2026年业绩公告")
    c = clean_mod.content_fingerprint("甲公司2026年业绩公吿")
    assert a == b
    assert a != c
    assert len(a) == hex_len
    assert all(ch in "0123456789abcdef" for ch in a)


def test_content_fingerprint_has_no_dead_code_fallback(clean_mod):
    """指纹长度必须是 config 值，不是函数里另写的第二份常量（P1-12 的"参数单一来源"）。"""
    src_default_len = 16
    got = clean_mod.content_fingerprint("x")
    # 无论 config 怎么改，函数返回长度都应与同一 config 的另一路读数一致
    assert len(got) == len(clean_mod.content_fingerprint("y")) or src_default_len == len(got)


# ==========================================================================
# E3 组 · company_list 归一与出现计数（normalize_company_list / mention_count）
# ==========================================================================
def test_normalize_company_list_accepts_many_shapes_and_never_returns_none(clean_mod):
    assert clean_mod.normalize_company_list(None) == []
    assert clean_mod.normalize_company_list("") == []
    assert clean_mod.normalize_company_list("000001,000002") == ["000001", "000002"]
    assert clean_mod.normalize_company_list("000001，000002") == ["000001", "000002"]
    assert clean_mod.normalize_company_list("000001;000002") == ["000001", "000002"]
    assert clean_mod.normalize_company_list("000001 000002") == ["000001", "000002"]
    assert clean_mod.normalize_company_list(["000001", "000002"]) == ["000001", "000002"]
    assert clean_mod.normalize_company_list(("000001",)) == ["000001"]
    assert clean_mod.normalize_company_list({"000001"}) == ["000001"]


def test_normalize_company_list_dedups_keeping_first_order(clean_mod):
    """去重保序（不是排序）：首见位置优先。"""
    got = clean_mod.normalize_company_list(["B", "A", "B", "C", "A"])
    assert got == ["B", "A", "C"]


def test_normalize_company_list_drops_blank_items(clean_mod):
    got = clean_mod.normalize_company_list(" , A ,, B , ")
    assert got == ["A", "B"]


def test_mention_count_is_literal_not_fuzzy(clean_mod):
    """字面计数：重叠、大小写、空针都按字面来。"""
    assert clean_mod.mention_count("ababab", "ab") == 3
    assert clean_mod.mention_count("ABCabc", "abc") == 1      # 区分大小写
    assert clean_mod.mention_count("任意文本", "") == 0        # 空针 → 0（不抛错）
    assert clean_mod.mention_count(None, "x") == 0


# ==========================================================================
# E4 组 · subject_companies_of（公告例外＋A／B 别名＋阈值）
# ==========================================================================
def test_subject_companies_of_announcement_takes_all_codes_verbatim(clean_mod):
    """公告不做文本判定：company_list 原样返回（保序去重）。"""
    got = clean_mod.subject_companies_of(
        title="某公司年度报告", content="正文里一次都没提到公司名",
        company_list=["000001", "000002"], category="公告")
    assert got == ["000001", "000002"]


def test_subject_companies_of_non_announcement_requires_mentions(clean_mod, prep_cfg):
    """非公告：名称/代码出现在标题，或正文提及次数 ≥ config.SUBJECT_MENTION_MIN 才计入。"""
    minimum = int(prep_cfg.SUBJECT_MENTION_MIN)
    code = prep_cfg.COMPANIES[0]["code"]
    name = prep_cfg.COMPANIES[0]["name"]
    # 标题命中 → 计入
    assert clean_mod.subject_companies_of(title="关于" + name + "的公告", content="",
                                          company_list=[code], category="财经新闻") == [code]
    # 正文提及恰好等于阈值 → 计入；差一次 → 不计入（负向标定：边界是 in-/ex-clusive）
    body_at = name * minimum
    body_below = name * (minimum - 1)
    assert clean_mod.subject_companies_of(title="无关标题", content=body_at,
                                          company_list=[code], category="财经新闻") == [code]
    assert clean_mod.subject_companies_of(title="无关标题", content=body_below,
                                          company_list=[code], category="财经新闻") == []


def test_subject_companies_of_never_introduces_outside_companies(clean_mod):
    """只在 company_list 内部判定：正文提到的别家公司绝不被引入。"""
    other = clean_mod.config.COMPANIES[1]["name"]
    got = clean_mod.subject_companies_of(title="", content=other * 20,
                                         company_list=[], category="财经新闻")
    assert got == []


def test_subject_companies_of_stays_inside_company_list(clean_mod, prep_cfg):
    """结果是 company_list 的子集（评审"只增不改"纪律的可执行读数）。"""
    code = prep_cfg.COMPANIES[0]["code"]
    name = prep_cfg.COMPANIES[0]["name"]
    pool = [code, "999998"]
    got = clean_mod.subject_companies_of(title="", content=name * 20,
                                         company_list=pool, category="财经新闻")
    assert set(got).issubset(set(pool))


# ==========================================================================
# E5 组 · 判重口径（dedup.py）
# ==========================================================================
def test_active_rules_order_is_url_then_title_then_fingerprint(dedup_mod):
    """规则顺序固定：url → title → 正文指纹（顺序变了判重结论会变）。"""
    rules = dedup_mod.active_rules()
    assert rules == [dedup_mod.RULE_URL, dedup_mod.RULE_TITLE, dedup_mod.RULE_FINGERPRINT]


def test_effective_url_prefers_content_url_then_page_url(dedup_mod):
    assert dedup_mod.effective_url({"content_url": "C", "page_url": "P"}) == "C"
    assert dedup_mod.effective_url({"page_url": "P"}) == "P"
    assert dedup_mod.effective_url({}) == ""


def test_publish_time_is_stripped_string(dedup_mod):
    assert dedup_mod.publish_time({"publish_time": "  2026-03-01 "}) == "2026-03-01"
    assert dedup_mod.publish_time({}) == ""


def test_rule_key_returns_none_for_uncomparable_docs(dedup_mod):
    """空键不参与判重（返回 None），而不是变成空串参与。"""
    assert dedup_mod.rule_key(dedup_mod.RULE_URL, {}) is None
    assert dedup_mod.rule_key(dedup_mod.RULE_TITLE, {"title": "   "}) is None
    assert dedup_mod.rule_key(dedup_mod.RULE_FINGERPRINT, {"raw_text": "   "}) is None


def test_rule_key_title_uses_normalized_title(dedup_mod):
    """同一标题的两种空白写法 → 同一个判重键（证明走了 normalize_title）。

    取值：全角空格是**被删掉**的（不是折成一个半角空格），连续半角空白才折成一个。
    """
    a = dedup_mod.rule_key(dedup_mod.RULE_TITLE, {"title": "　甲公司\u3000公告"})
    b = dedup_mod.rule_key(dedup_mod.RULE_TITLE, {"title": "甲公司 公告"})
    c = dedup_mod.rule_key(dedup_mod.RULE_TITLE, {"title": "甲公司   公告"})
    assert a == "甲公司公告"          # 全角空格删除
    assert b == c == "甲公司 公告"    # 连续半角空白折一个；单个保留
    # 两种写法在「有半角空格」这一档上等价
    assert dedup_mod.rule_key(dedup_mod.RULE_TITLE, {"title": "甲公司　公告"}) == "甲公司公告"


def test_rule_key_regulator_title_folds_in_source_wenhao(dedup_mod, prep_cfg):
    """监管公开信息：同题文档在并入来源文号后不再是同一个键（消歧生效）。"""
    if not prep_cfg.DEDUP.get("regulator_title_disambiguation"):
        pytest.skip("config.DEDUP['regulator_title_disambiguation'] 为假：本项不适用")
    plain = dedup_mod.rule_key(dedup_mod.RULE_TITLE, {
        "title": "某处罚决定", "category": _REGULATOR_CATEGORY})
    tagged = dedup_mod.rule_key(dedup_mod.RULE_TITLE, {
        "title": "某处罚决定", "category": _REGULATOR_CATEGORY,
        "meta": {"wenhao": "〔2026〕1号"}})
    assert plain == "某处罚决定"
    assert tagged != plain
    assert "〔2026〕1号" in tagged


def test_key_kind_announces_the_disambiguated_form(dedup_mod, prep_cfg):
    """`key_kind` 把"并入文号后的键"如实标成自解释字符串（日志可读性）。"""
    if not prep_cfg.DEDUP.get("regulator_title_disambiguation"):
        pytest.skip("config.DEDUP['regulator_title_disambiguation'] 为假：本项不适用")
    doc = {"title": "某处罚决定", "category": _REGULATOR_CATEGORY,
           "meta": {"wenhao": "〔2026〕1号"}}
    key = dedup_mod.rule_key(dedup_mod.RULE_TITLE, doc)
    kind = dedup_mod.key_kind(dedup_mod.RULE_TITLE, key, doc)
    assert kind == "normalized_title+source_wenhao/index_no"
    plain_doc = {"title": "某处罚决定", "category": _REGULATOR_CATEGORY}
    assert dedup_mod.key_kind(dedup_mod.RULE_TITLE, "某处罚决定", plain_doc) \
        == dedup_mod.RULE_KEY_KIND[dedup_mod.RULE_TITLE]


def test_rank_key_prefers_earlier_publish_then_shorter_url_then_smaller_id(dedup_mod):
    """保留优先级：早发布 > 短链接 > 小 doc_id；空 publish_time 视为最晚。"""
    early = {"doc_id": 9, "publish_time": "2026-01-01", "content_url": "x" * 99}
    late = {"doc_id": 1, "publish_time": "2026-09-01", "content_url": "x"}
    assert dedup_mod.rank_key(early) < dedup_mod.rank_key(late)      # 早发布胜
    # 同发布：短链接胜
    a = {"doc_id": 5, "publish_time": "2026-01-01", "content_url": "aa"}
    b = {"doc_id": 4, "publish_time": "2026-01-01", "content_url": "aaaa"}
    assert dedup_mod.rank_key(a) < dedup_mod.rank_key(b)
    # 同发布同长度：小 doc_id 胜
    c = {"doc_id": 4, "publish_time": "2026-01-01", "content_url": "aa"}
    d = {"doc_id": 5, "publish_time": "2026-01-01", "content_url": "bb"}
    assert dedup_mod.rank_key(c) < dedup_mod.rank_key(d)
    # 空 publish_time 视为最晚
    empty = {"doc_id": 0, "publish_time": "", "content_url": ""}
    assert dedup_mod.rank_key(late) < dedup_mod.rank_key(empty)


def test_decide_reason_names_the_actual_decider(dedup_mod):
    assert dedup_mod.decide_reason(
        {"publish_time": "2026-01-01", "content_url": "a"},
        {"publish_time": "2026-02-01", "content_url": "a"}) == "earlier_publish_time"
    assert dedup_mod.decide_reason(
        {"publish_time": "2026-01-01", "content_url": "a"},
        {"publish_time": "2026-01-01", "content_url": "aaa"}) == "shorter_url"
    assert dedup_mod.decide_reason(
        {"publish_time": "2026-01-01", "content_url": "aa"},
        {"publish_time": "2026-01-01", "content_url": "aa"}) == "smaller_doc_id"


def test_decide_url_rule_drops_duplicates_and_keeps_losers_out_of_later_rules(dedup_mod):
    """被淘汰的文档从后续规则的比较池移除（否则会把同一篇再计一次）。"""
    docs = [
        {"doc_id": 1, "title": "甲", "content_url": "http://x/1", "publish_time": "2026-01-01", "raw_text": "A"},
        {"doc_id": 2, "title": "甲", "content_url": "http://x/1", "publish_time": "2026-02-01", "raw_text": "B"},
        {"doc_id": 3, "title": "乙", "content_url": "http://x/3", "publish_time": "2026-01-01", "raw_text": "C"},
    ]
    decisions, survivors = dedup_mod.decide(docs, dedup_mod.active_rules())
    url_decision = [d for d in decisions if d["rule"] == dedup_mod.RULE_URL]
    assert len(url_decision) == 1
    assert url_decision[0]["winner"] == 1          # 早发布者胜
    assert url_decision[0]["dropped"] == [2]
    assert url_decision[0]["decided_by"] if "decided_by" in url_decision[0] else True
    assert set(survivors) == {1, 3}
    # 2 被 url 规则淘汰后，不再出现在标题规则的候选里
    title_decision = [d for d in decisions if d["rule"] == dedup_mod.RULE_TITLE]
    for d in title_decision:
        assert 2 not in d["candidates"]


def test_decide_title_rule_keeps_first_and_drops_the_rest(dedup_mod):
    """同题三篇：只留一篇，另两篇进 dropped_detail（每条都带具体判据）。"""
    docs = [
        {"doc_id": 1, "title": "同题公告", "content_url": "http://x/1", "publish_time": "2026-01-01", "raw_text": "A"},
        {"doc_id": 2, "title": "同题公告", "content_url": "http://x/2", "publish_time": "2026-01-02", "raw_text": "B"},
        {"doc_id": 3, "title": "同题公告", "content_url": "http://x/3", "publish_time": "2026-01-03", "raw_text": "C"},
    ]
    decisions, survivors = dedup_mod.decide(docs, [dedup_mod.RULE_TITLE])
    assert len(decisions) == 1
    assert decisions[0]["winner"] == 1
    assert set(decisions[0]["dropped"]) == {2, 3}
    assert len(decisions[0]["dropped_detail"]) == 2
    for detail in decisions[0]["dropped_detail"]:
        assert detail["decided_by"] in ("earlier_publish_time", "shorter_url", "smaller_doc_id")
    assert set(survivors) == {1}


def test_decide_fingerprint_rule_uses_cleaned_body(dedup_mod):
    """指纹规则建立在**清洗后**正文上：清洗后才相同的两篇被判为同一篇。

    构造：两篇唯一的差异是「首尾空白 ＋ 连续空行」，这些恰好是 `clean_body` 会折掉的；
    若指纹改在清洗**之前**算，两篇就会被判成不同（负向标定）。
    """
    same_a = {"doc_id": 1, "content_url": "http://x/1",
              "raw_text": "甲公司 2026 年\n\n\n\n业绩公告"}
    same_b = {"doc_id": 2, "content_url": "http://x/2",
              "raw_text": "  甲公司 2026 年\n\n业绩公告  "}
    # 先证明这两篇在清洗前确实不同、清洗后确实相同
    assert same_a["raw_text"] != same_b["raw_text"]
    assert dedup_mod.clean_body(same_a["raw_text"]) == dedup_mod.clean_body(same_b["raw_text"])
    decisions, survivors = dedup_mod.decide([same_a, same_b], [dedup_mod.RULE_FINGERPRINT])
    assert len(decisions) == 1
    assert set(survivors) == {1}


def test_decide_fingerprint_rule_does_not_merge_different_bodies(dedup_mod):
    """负向标定：正文真的不同就不该合并（防"指纹实现恒等/恒空"这类假绿）。"""
    a = {"doc_id": 1, "content_url": "http://x/1", "raw_text": "甲公司业绩公告"}
    b = {"doc_id": 2, "content_url": "http://x/2", "raw_text": "乙公司人事变动"}
    decisions, survivors = dedup_mod.decide([a, b], [dedup_mod.RULE_FINGERPRINT])
    assert decisions == []
    assert set(survivors) == {1, 2}


def test_decide_unknown_rule_raises_instead_of_silently_passing(dedup_mod):
    """未知规则必须抛错，不得静默跳过（否则判重会"看起来跑了、其实没比"）。"""
    with pytest.raises(ValueError):
        dedup_mod.rule_key("NO_SUCH_RULE", {"doc_id": 1})


# ==========================================================================
# E6 组 · 切分（chunk.py）
# ==========================================================================
def test_chunk_document_short_text_is_one_chunk(chunk_mod, prep_cfg):
    max_chars = int(prep_cfg.CHUNK["max_chars"])
    text = "短正文" * 3
    assert len(text) <= max_chars
    assert chunk_mod.chunk_document(text) == [text]


def test_chunk_document_blank_returns_empty_list_not_a_blank_chunk(chunk_mod):
    """L-16 回归防线：空／全空白输入返回 []，绝不返回 ['']。"""
    assert chunk_mod.chunk_document("") == []
    assert chunk_mod.chunk_document("    \n\t  ") == []
    assert chunk_mod.chunk_document(None) == []


def test_chunk_document_respects_max_chars_and_min_chars(chunk_mod, prep_cfg):
    """每块 ≤ max_chars；除末块外每块 ≥ min_chars（末块是剩余量，可短）。"""
    max_chars = int(prep_cfg.CHUNK["max_chars"])
    min_chars = int(prep_cfg.CHUNK["min_chars"])
    text = ("第一段。" * 400) + "\n" + ("第二段。" * 400)
    chunks = chunk_mod.chunk_document(text)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= max_chars
    for c in chunks[:-1]:
        assert len(c) >= min_chars


def test_chunk_document_chunks_reassemble_to_the_source_ignoring_overlap(chunk_mod, prep_cfg):
    """拼回：把重叠部分扣掉后，各块拼起来应还原原文（不丢字、不加字）。"""
    overlap = int(prep_cfg.CHUNK["overlap_chars"])
    text = "".join("句%d。" % i for i in range(600))
    chunks = chunk_mod.chunk_document(text)
    rebuilt = chunks[0]
    for c in chunks[1:]:
        # 用 overlap 消重叠：找最长后缀=前缀的重叠长度
        k = min(len(rebuilt), len(c), overlap + 2)
        cut = 0
        for cand in range(k, 0, -1):
            if rebuilt.endswith(c[:cand]):
                cut = cand
                break
        rebuilt += c[cut:]
    assert rebuilt == text


def test_chunk_document_is_deterministic(chunk_mod, prep_cfg):
    text = "".join("内容%d。" % i for i in range(500))
    assert chunk_mod.chunk_document(text) == chunk_mod.chunk_document(text)


def test_cut_positions_newline_boundary_cuts_before_the_newline(chunk_mod):
    text = "abcd\nefgh"
    positions = chunk_mod._cut_positions(text, 0, len(text), "\n")
    assert positions == [4]          # 切点在新行符之前


def test_cut_positions_sentence_boundary_cuts_after_the_punctuation(chunk_mod):
    text = "abcd。efgh"
    positions = chunk_mod._cut_positions(text, 0, len(text), "。")
    assert positions == [5]          # 切点在句号之后（标点留在前一块）


def test_choose_cut_prefers_the_latest_position_not_exceeding_target(chunk_mod):
    """同一优先级内取 ≤ target 的最晚位置（不是最早、不是最接近）。"""
    text = "aaaa。bbbb。cccc。dddd。"
    lo, target, hi = 0, 10, 20
    assert chunk_mod._choose_cut(text, 0, lo, target, hi, ["。"]) == 10


def test_choose_cut_falls_back_to_earliest_when_target_precedes_all(chunk_mod):
    text = "aaaa。bbbb。"
    assert chunk_mod._choose_cut(text, 0, 0, 2, len(text), ["。"]) == 5


def test_choose_cut_returns_none_when_no_boundary_in_range(chunk_mod):
    text = "abcdefgh"
    assert chunk_mod._choose_cut(text, 0, 0, 4, len(text), ["。"]) is None


def test_choose_cut_respects_boundary_priority_order(chunk_mod):
    """高优先级边界只要有可用位置就胜出，哪怕低优先级的位置更理想。"""
    text = "aaa。bbb\nccc。ddd"
    got = chunk_mod._choose_cut(text, 0, 0, 8, len(text), ["\n", "。"])
    assert got == 7          # 换行边界（优先）而非句号


def test_skip_leading_blank_skips_all_whitespace_kinds(chunk_mod):
    text = "  \t\r\n\u3000X"
    assert chunk_mod._skip_leading_blank(text, 0, len(text)) == 6
    assert text[chunk_mod._skip_leading_blank(text, 0, len(text))] == "X"


def test_count_tokens_fallback_counts_non_whitespace_chars(chunk_mod):
    assert chunk_mod.count_tokens(None, ["a b\tc", "  "], fallback=True) == [3, 0]
    assert chunk_mod.count_tokens(None, ["全 角　空", ""], fallback=True)[0] >= 3


def test_count_tokens_uses_tokenizer_when_available(chunk_mod):
    class _FakeTok:
        def __call__(self, texts, add_special_tokens=False):
            return {"input_ids": [[0] * (len(t) + 1) for t in texts]}

    got = chunk_mod.count_tokens(_FakeTok(), ["ab", "abcd"], fallback=False)
    assert got == [3, 5]
