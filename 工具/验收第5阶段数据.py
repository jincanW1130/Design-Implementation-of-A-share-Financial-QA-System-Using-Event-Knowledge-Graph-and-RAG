#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""《13-数据准备（第五阶段）》与数据集 v1.0 的阶段级验收（《12》§八 验收标准逐行落地）。

与另外两个脚本的分工（不重复实现）：
  * `工具\跨文档核验.py` —— 全工作区 Markdown 的通用一致性（检查 A～N，含索引登记、禁用词与《02》引用版本审计）；
  * `代码\数据准备\check.py` —— 数据集自身的条数与编号一致性（管线内部一致性，14 项）；
  * 本脚本 —— 第 5 阶段的**验收闸门**：把《12》§八 的 19 行验收标准逐行实现为 A～S 共 19 组
    检查（S 组是索引集中度与跨公司同名标题两条守卫），全部数值从数据集文件与《13》重新推导，
    再与 `代码\数据准备\config.py` 的冻结参数比对。

用法：

    python 工具\验收第5阶段数据.py
    python 工具\验收第5阶段数据.py --dataset <数据集根目录> --doc <《13》路径>
    python 工具\验收第5阶段数据.py --with-idempotence    # 真实重跑幂等检查（默认只做静态等价检查）

退出码：0 = 全部检查通过；1 = 存在失败项或输入缺失。

纪律：
  * 本脚本对封版数据集**只读**；唯一的写动作在 `--with-idempotence` 下发生——把 `raw\` 复制到
    系统临时目录里复跑 T4a→T5，**绝不写入 `--dataset` 指向的目录**（《12》§4.2 版本目录不可变）；
  * 阈值一律来自 `代码\数据准备\config.py`（日期、条数、模型名、切分参数都不在脚本里写死）；唯一例外是
    S 组的两条集中度守卫阈值：它们是本验收工具自带的模块级常量，刻意不读已冻结的 config（理由见该组注释）；
  * 术语：FAISS 一律称“向量索引／向量检索组件”；本脚本源码内不出现「向量」与「数据库」的连写
    （禁用词按 P 组以拼接方式构造，免得本脚本自己被术语检查命中）；
  * 不 import pandas；只用标准库 + 已安装的 faiss／numpy（读索引条数，读不到则退回文件头部解析）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta

# 控制台为 GBK，先把标准输出重设成 UTF-8 再打印中文。
try:
    sys.stdout.reconfigure(encoding="utf-8")
except AttributeError:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE = os.path.join(ROOT, '阶段05-数据准备')
CODE_DIR = os.path.join(ROOT, '代码', '数据准备')
sys.path.insert(0, CODE_DIR)

import config  # noqa: E402  第 5 阶段唯一参数来源（日期、条数、模型名、切分参数都在这里）

DEFAULT_DOC = os.path.join(STAGE, '13-数据准备（第五阶段）.md')
DEFAULT_DATASET = config.dataset_dir('v1')
P12 = os.path.join(STAGE, '12-第5阶段任务书（数据准备）.md')
P10 = os.path.join(ROOT, '阶段04-系统总体设计', '10-系统总体设计（第四阶段）.md')
P00 = os.path.join(ROOT, '00-项目总览与索引.md')
CROSS_DOC = os.path.join(ROOT, '工具', '跨文档核验.py')

_ap = argparse.ArgumentParser(description='第 5 阶段数据准备：阶段级验收（《12》§八 逐行）')
_ap.add_argument('--dataset', default=None, help='数据集根目录（默认 %s）' % DEFAULT_DATASET)
_ap.add_argument('--doc', default=None, help='《13》路径（默认 %s）' % DEFAULT_DOC)
_ap.add_argument('--with-idempotence', action='store_true',
                 help='额外做真实重跑幂等检查：在系统临时目录复跑 T4a→T5，不触碰封版数据集')
ARGS = _ap.parse_args()

DATASET = os.path.abspath(ARGS.dataset) if ARGS.dataset else DEFAULT_DATASET
DOC = os.path.abspath(ARGS.doc) if ARGS.doc else DEFAULT_DOC


# --------------------------------------------------------------------------
# S 组守卫阈值（本验收工具自带，刻意不从 `代码\数据准备\config.py` 读取——那个文件已冻结）
# --------------------------------------------------------------------------
# 理由：config 管的是管线参数，「合法的均值／上限块长」这类取值天然属于管线；而「一篇文档吞掉
# 整个索引」是数据集缺陷，不是可调参数——将来数据集若再出现一篇文档占据索引大部分，本验收必须
# 失败。所以集中度阈值属于本验收闸门自身，而不是冻结的 config。
MAX_TOP1_CHUNK_SHARE = 0.25     # 守卫阈值：单篇文档块数占全库块数的上限（超过即 S1 失败）
MAX_TOP5_CHUNK_SHARE = 0.60     # 守卫阈值：前 5 篇文档块数合计占比的上限（超过即 S1 失败）


# --------------------------------------------------------------------------
# 报告器：沿用《验收第4阶段文档.py》的 [OK ] / [FAIL] 逐项 + 末尾结论布局
# --------------------------------------------------------------------------
results = []          # [(ok, label, detail)]
fails = []            # [label]
fail_evidence = []    # [(label, detail)]


def chk(ok, label, detail=''):
    print('  [%s] %s%s' % ('OK ' if ok else 'FAIL', label, ('  ' + detail) if detail else ''))
    results.append((bool(ok), label, detail))
    if not ok:
        fails.append(label)
        fail_evidence.append((label, detail))


def note(label, detail=''):
    """只打印证据行（不计入通过／失败项数）。"""
    print('  [OK ] %s%s' % (label, ('  ' + detail) if detail else ''))


def br(seq, limit=4):
    """把序列压成一行：最多列 limit 项，超出只报总数。"""
    seq = list(seq)
    head = '、'.join(str(x) for x in seq[:limit])
    return head + ('…（共 %d 个）' % len(seq) if len(seq) > limit else '')


# --------------------------------------------------------------------------
# 通用读取与小工具
# --------------------------------------------------------------------------
def read_text(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def read_json(path):
    with open(path, 'r', encoding='utf-8') as fh:
        return json.load(fh)


def read_jsonl(path):
    """返回 [(行号, 对象)]；坏行抛出 ValueError（含文件名与行号），便于定位。"""
    rows = []
    with open(path, 'r', encoding='utf-8') as fh:
        for i, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append((i, json.loads(line)))
            except json.JSONDecodeError as exc:
                raise ValueError('%s 第 %d 行不是合法 JSON：%s' % (path, i, exc)) from exc
    return rows


def safe_jsonl(path):
    try:
        return read_jsonl(path)
    except (OSError, ValueError) as exc:
        print('  [FAIL] 报告读取失败：%s' % exc)
        return []


def parse_date(value):
    """'YYYY-MM-DD'（允许带 ISO8601 时间部分）-> date；不可解析返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    try:
        return datetime.strptime(s[:10], '%Y-%m-%d').date()
    except ValueError:
        try:
            return datetime.fromisoformat(s).date()
        except ValueError:
            return None


def parse_dt(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return datetime.fromisoformat(value.strip())
    except ValueError:
        return None


def normalize_title(title):
    """按 config.DEDUP['title_normalize'] 的口径规范化标题（规则字面量不写死在脚本里）。"""
    s = '' if title is None else str(title)
    rules = config.DEDUP.get('title_normalize') or []
    if '去除全角空格' in rules:
        for sp in ('\u3000', '\u00a0'):
            s = s.replace(sp, ' ')
    if '合并连续空白' in rules:
        s = re.sub(r'\s+', ' ', s)
    if '去除首尾空白' in rules:
        s = s.strip()
    return s


_FP_ALGO, _, _FP_HEX = str(config.DEDUP['content_fingerprint']).partition('_')
_FP_HEX = int(_FP_HEX)


def fingerprint(text):
    """正文指纹：sha256 十六进制前 _FP_HEX 位（算法与位数取自 config.DEDUP）。"""
    if _FP_ALGO != 'sha256':
        raise ValueError('config.DEDUP["content_fingerprint"] 只实现了 sha256，当前为 %r' % _FP_ALGO)
    return hashlib.sha256(str(text).encode('utf-8')).hexdigest()[:_FP_HEX]


def dup_groups(values):
    return {k: n for k, n in Counter(values).items() if n > 1}


def month_histogram(dates):
    """逐月文档数，覆盖最早与最晚之间的每一个自然月（无文档月份显式记 0）。"""
    if not dates:
        return {}
    counts = Counter(d.strftime('%Y-%m') for d in dates)
    cur, last = min(dates).replace(day=1), max(dates).replace(day=1)
    out = {}
    while cur <= last:
        key = cur.strftime('%Y-%m')
        out[key] = counts.get(key, 0)
        cur = (cur + timedelta(days=32)).replace(day=1)
    return out


def iter_files(dirpath):
    for dp, _dn, fn in os.walk(dirpath):
        for f in sorted(fn):
            yield os.path.join(dp, f)


def index_size(path):
    """读向量索引的 (ntotal, dim)。优先 faiss，失败则按文件头部字段解析。"""
    try:
        import faiss
        import numpy as np
        with open(path, 'rb') as fh:
            raw = fh.read()
        idx = faiss.deserialize_index(np.frombuffer(bytearray(raw), dtype=np.uint8))
        return int(idx.ntotal), int(idx.d), 'faiss.deserialize_index'
    except Exception as exc:                      # faiss 不可用：退回头部字段
        with open(path, 'rb') as fh:
            _magic, dim, ntotal = struct.unpack('<iiq', fh.read(16))
        return int(ntotal), int(dim), '索引文件头部字段（faiss 不可用：%s: %s）' % (type(exc).__name__, exc)


def structural_targets():
    """判定用的文本范围 =《13》+ 数据集的结构化文件（**不含**语料正文）。

    这是本脚本的口径声明：表格／术语／型号类检查只看“人写进去的东西”；语料正文是原文引用，
    单独统计（O 组会打印其计数），不当作“写死型号”或“引入技术”。
    """
    out = [('《13》', DOC)]
    for sub in ('meta', 'index', 'reports'):
        d = os.path.join(DATASET, sub)
        if not os.path.isdir(d):
            continue
        for p in iter_files(d):
            if os.path.basename(p) == config.FAISS['index_file']:      # 二进制索引
                continue
            out.append((os.path.relpath(p, DATASET), p))
    log = os.path.join(DATASET, 'raw', '_fetch_log.jsonl')
    if os.path.isfile(log):
        out.append((os.path.relpath(log, DATASET), log))
    return out


def all_dataset_targets():
    """《13》+ 数据集内的全部文件（去掉二进制索引）：供“不许出现的词”类检查使用。"""
    out = [('《13》', DOC)]
    if os.path.isdir(DATASET):
        for p in iter_files(DATASET):
            if os.path.basename(p) == config.FAISS['index_file']:
                continue
            out.append((os.path.relpath(p, DATASET), p))
    return out


def corpus_targets():
    """语料正文（原文引用）：只作报告项，不计入判定。"""
    out = []
    for sub, name in (('clean', 'documents.jsonl'), ('chunks', 'chunks.jsonl')):
        p = os.path.join(DATASET, sub, name)
        if os.path.isfile(p):
            out.append((os.path.relpath(p, DATASET), p, 'content'))
    return out


def scan_term(term, targets, neg_markers=None):
    """在文本范围里逐行找 term；返回 [(标签, 行号, 行内容, 是否否定语境)]。"""
    neg_markers = neg_markers or ('不引入', '不采用', '不使用', '不进入', '不按', '排除', '避免',
                                  '严禁', '禁止', '不得', '不再', '无', '未', '非', '之外', '而不')
    hits = []
    for label, path in targets:
        if not os.path.isfile(path):
            continue
        try:
            text = read_text(path)
        except OSError:
            continue
        for i, line in enumerate(text.split('\n'), 1):
            if term in line:
                hits.append((label, i, line.strip(), any(m in line for m in neg_markers)))
    return hits


# --------------------------------------------------------------------------
# 输入
# --------------------------------------------------------------------------
print('=' * 78)
print('第 5 阶段（数据准备）阶段级验收：《13》与数据集（《12》§八 逐行）')
print('=' * 78)
print('  数据集根目录：%s%s' % (DATASET, '（--dataset 覆盖）' if ARGS.dataset else '（默认 v1.0）'))
print('  说明文档：    %s%s' % (DOC, '（--doc 覆盖）' if ARGS.doc else '（默认《13》）'))
print('  冻结参数来源：%s' % os.path.join(CODE_DIR, 'config.py'))
print('  幂等检查模式：%s' % ('真实重跑（--with-idempotence，在系统临时目录复跑 T4a→T5）'
                             if ARGS.with_idempotence else
                             '静态等价（默认；真实重跑需加 --with-idempotence）'))
print()

_missing = [p for p in (DOC, P12, P10, P00) if not os.path.isfile(p)]
if not os.path.isdir(DATASET):
    _missing.append(DATASET)
if _missing:
    for _p in _missing:
        print('缺少输入文件：%s' % _p)
    sys.exit(1)

t13 = read_text(DOC)
t12 = read_text(P12)
t10 = read_text(P10)
t00 = read_text(P00)

DOCS_P = os.path.join(DATASET, 'clean', 'documents.jsonl')
CHUNKS_P = os.path.join(DATASET, 'chunks', 'chunks.jsonl')
try:
    doc_rows = read_jsonl(DOCS_P)
    chunk_rows = read_jsonl(CHUNKS_P)
except (OSError, ValueError) as exc:
    print('  [FAIL] 读取数据集失败：%s' % exc)
    sys.exit(1)

docs = [r for _, r in doc_rows]
chunks = [r for _, r in chunk_rows]
n_docs, n_chunks = len(docs), len(chunks)

DREG = os.path.join(DATASET, 'reports')
raw_dir = os.path.join(DATASET, 'raw')
raw_doc_files = [p for p in iter_files(raw_dir)
                 if p.lower().endswith('.json') and not os.path.basename(p).startswith('_')] \
    if os.path.isdir(raw_dir) else []
raw_log = os.path.join(raw_dir, '_fetch_log.jsonl')
cstats = read_json(os.path.join(DREG, 'chunk_stats.json')) \
    if os.path.isfile(os.path.join(DREG, 'chunk_stats.json')) else {}
skipped_rows = safe_jsonl(os.path.join(DREG, 'skipped.jsonl')) \
    if os.path.isfile(os.path.join(DREG, 'skipped.jsonl')) else []
dedup_rows = safe_jsonl(os.path.join(DREG, 'dedup_log.jsonl')) \
    if os.path.isfile(os.path.join(DREG, 'dedup_log.jsonl')) else []

# 公用推导量：时间、桶、逐月直方图、公司覆盖
cutoff = parse_date(config.DATA_CUTOFF_DATE)
date_list = [parse_date(d.get('publish_time')) for d in docs]
date_ok = [x for x in date_list if x]
pmin = min(date_ok) if date_ok else None
pmax = max(date_ok) if date_ok else None
hist = month_histogram(date_ok)
_r0, _r1 = (parse_date(x) for x in config.BUCKET_RECENT)
_e0, _e1 = (parse_date(x) for x in config.BUCKET_EARLIER)
recent = [d for _, d in doc_rows
          if (x := parse_date(d.get('publish_time'))) and _r0 <= x <= _r1]
earlier = [d for _, d in doc_rows
           if (x := parse_date(d.get('publish_time'))) and _e0 <= x <= _e1]
covered = set()
for _, d in doc_rows:
    cl = d.get('company_list')
    if isinstance(cl, list):
        covered.update(str(x) for x in cl)


# ==========================================================================
print(); print('=' * 78)
print('A、《13》文档结构（《12》§八 第 1 行：7 个必备小节 + 2 个附加小节）')
print('=' * 78)

h2 = [(i, L[3:].strip()) for i, L in enumerate(t13.split('\n'), 1) if L.startswith('## ')]


def find_h2(name):
    for ln, title in h2:
        if title.endswith(name):
            return ln, title
    return None, None


m_req = re.search(r'(\d+)\s*个必备小节[^：:]*[：:]([^|\n]+)', t12)
req_sections = [s.strip() for s in m_req.group(2).split('／') if s.strip()] if m_req else []
chk(m_req is not None and len(req_sections) > 0,
    'A1 从《12》§八 解析出必备小节清单（不写死小节名）',
    '实测 解析 %d 个：%s' % (len(req_sections), '／'.join(req_sections) or '无'))
if m_req:
    chk(len(req_sections) == int(m_req.group(1)),
        'A2 必备小节数与《12》§八 声明的数量一致',
        '《12》声明 %s 个、解析得 %d 个' % (m_req.group(1), len(req_sections)))
sec_pos, sec_miss = [], []
for name in req_sections:
    ln, title = find_h2(name)
    if ln is None:
        sec_miss.append(name)
    else:
        sec_pos.append((ln, name))
chk(not sec_miss, 'A3 7 个必备小节按小节名齐全（二级标题逐名命中）',
    '实测 %d/%d 命中；缺失 %s' % (len(req_sections) - len(sec_miss), len(req_sections),
                                   '、'.join(sec_miss) or '无'))

row41 = next((L for L in t12.split('\n') if '13-数据准备（第五阶段）.md' in L and '数据字典' in L), '')
extra_sections = [s for s in ('失败与跳过记录', '对下游阶段的使用说明') if s in row41]
chk(len(extra_sections) == 2, 'A4 从《12》§4.1 产出清单解析两个附加小节',
    '实测 解析 %d/2：%s' % (len(extra_sections), '、'.join(extra_sections) or '无'))
extra_miss = []
for name in extra_sections:
    ln, title = find_h2(name)
    if ln is None:
        extra_miss.append(name)
    else:
        sec_pos.append((ln, name))
chk(not extra_miss, 'A5 附加小节齐全（失败与跳过记录／对下游阶段的使用说明）',
    '实测 缺失 %s' % ('、'.join(extra_miss) or '无'))
exp_n = len(req_sections) + len(extra_sections)
pos = [ln for ln, _ in sec_pos]
chk(len(pos) == exp_n and pos == sorted(pos),
    'A6 小节顺序与《12》清单一致（按《13》行号递增）',
    '实测 命中 %d/%d；命中行号 %s' % (len(pos), exp_n, pos))
chk(len(h2) >= exp_n, 'A7 《13》二级标题数与结构相称',
    '实测 H2 标题 %d 个：%s' % (len(h2), '；'.join('%s@第%d行' % (t, ln) for ln, t in h2)))


# ==========================================================================
print(); print('=' * 78)
print('B、数据集目录结构（《12》§八 第 2 行／§4.2：6 个一级子目录、自包含）')
print('=' * 78)

miss_dirs = [d for d in config.SUBDIRS if not os.path.isdir(os.path.join(DATASET, d))]
chk(not miss_dirs, 'B1 六个一级子目录齐全（config.SUBDIRS）',
    '实测 %d/%d 存在；缺失 %s' % (len(config.SUBDIRS) - len(miss_dirs), len(config.SUBDIRS),
                                  '、'.join(miss_dirs) or '无'))

REQUIRED_FILES = [
    ('meta', 'dataset.json'), ('meta', 'sources.csv'),
    ('clean', 'documents.jsonl'), ('chunks', 'chunks.jsonl'),
    ('index', config.FAISS['index_file']), ('index', config.FAISS['map_file']),
    ('index', config.FAISS['meta_file']),
    ('reports', 'consistency_report.json'), ('reports', 'consistency_report.md'),
    ('reports', 'clean_stats.json'), ('reports', 'dedup_log.jsonl'), ('reports', 'skipped.jsonl'),
]
miss_files = ['%s\\%s' % (a, b) for a, b in REQUIRED_FILES
              if not os.path.isfile(os.path.join(DATASET, a, b))]
chk(not miss_files, 'B2 自包含：meta／clean／chunks／index／reports 的必需文件齐全',
    '实测 %d/%d 存在；缺失 %s' % (len(REQUIRED_FILES) - len(miss_files), len(REQUIRED_FILES),
                                  '、'.join(miss_files) or '无'))
chk(len(raw_doc_files) > 0 and os.path.isfile(raw_log),
    'B3 raw\\ 含原始文档文件与抓取日志（采集侧可回溯）',
    '实测 raw\\*.json %d 个、_fetch_log.jsonl %s'
    % (len(raw_doc_files), '存在' if os.path.isfile(raw_log) else '缺失'))
top_entries = sorted(os.listdir(DATASET))
extra_top = [x for x in top_entries if x not in config.SUBDIRS]
chk(not extra_top, 'B4 一级条目均属于六个子目录（自包含，不外溢）',
    '实测 一级条目 %d 个：%s；越界 %s'
    % (len(top_entries), '、'.join(top_entries), '、'.join(extra_top) or '无'))


# ==========================================================================
print(); print('=' * 78)
print('C、meta\\dataset.json 的字段与取值（《12》§八 第 3 行；逐项由数据集文件重新推导后比对）')
print('=' * 78)

META_P = os.path.join(DATASET, 'meta', 'dataset.json')
BM_P = os.path.join(DATASET, 'index', config.FAISS['meta_file'])
REP_P = os.path.join(DREG, 'consistency_report.json')
dmeta = read_json(META_P) if os.path.isfile(META_P) else {}
bmeta = read_json(BM_P) if os.path.isfile(BM_P) else {}
crep = read_json(REP_P) if os.path.isfile(REP_P) else {}      # 读报告：仅用于比对生成时间
chk(bool(dmeta), 'C1 meta\\dataset.json 可读且非空',
    '实测 %s（字段 %d 个：%s）' % (META_P, len(dmeta), '、'.join(sorted(dmeta))))


def cmp_item(label, actual, expected, source):
    chk(actual == expected, label,
        '实测 %s；期望 %s（来源：%s）' % (json.dumps(actual, ensure_ascii=False),
                                          json.dumps(expected, ensure_ascii=False), source))


cmp_item('C2 dataset_version == config.DATASET_VERSION', dmeta.get('dataset_version'),
         config.DATASET_VERSION, 'config.py')
cmp_item('C3 pipeline_version == config.PIPELINE_VERSION', dmeta.get('pipeline_version'),
         config.PIPELINE_VERSION, 'config.py')
cmp_item('C4 data_cutoff_time == config.DATA_CUTOFF_TIME', dmeta.get('data_cutoff_time'),
         config.DATA_CUTOFF_TIME, 'config.py')
cmp_item('C5 data_cutoff_date == config.DATA_CUTOFF_DATE', dmeta.get('data_cutoff_date'),
         config.DATA_CUTOFF_DATE, 'config.py')

scale = dmeta.get('scale') or {}
cmp_item('C6 scale.doc_count == clean\\documents.jsonl 实测行数（重算）', scale.get('doc_count'),
         n_docs, 'documents.jsonl')
cmp_item('C7 scale.chunk_count == chunks\\chunks.jsonl 实测行数（重算）', scale.get('chunk_count'),
         n_chunks, 'chunks.jsonl')
cmp_item('C8 scale.company_count == company_list 并集实测家数（重算）', scale.get('company_count'),
         len(covered), 'documents.jsonl 的 company_list 并集')
cmp_item('C9 scale.configured_company_count == config.COMPANIES 家数',
         scale.get('configured_company_count'), len(config.COMPANIES), 'config.py')

tr = dmeta.get('time_range') or {}
cmp_item('C10 time_range.publish_time_min == 实测最早 publish_time', tr.get('publish_time_min'),
         pmin.isoformat() if pmin else None, 'documents.jsonl')
cmp_item('C11 time_range.publish_time_max == 实测最晚 publish_time', tr.get('publish_time_max'),
         pmax.isoformat() if pmax else None, 'documents.jsonl')
cmp_item('C12 time_range.span_days_between_min_and_max == 实测跨度（天）',
         tr.get('span_days_between_min_and_max'),
         (pmax - pmin).days if pmin and pmax else None, 'documents.jsonl')
cmp_item('C13 time_range.cutoff_minus_earliest_days == cutoff − 实测最早（天）',
         tr.get('cutoff_minus_earliest_days'), (cutoff - pmin).days if pmin else None,
         'documents.jsonl + config.DATA_CUTOFF_DATE')
cmp_item('C14 time_range.window_start／end／days == config.WINDOW_*（采集窗）',
         [tr.get('window_start'), tr.get('window_end'), tr.get('window_days')],
         [config.WINDOW_START, config.WINDOW_END, config.WINDOW_DAYS], 'config.py')
buckets = tr.get('buckets') or {}
cmp_item('C15 buckets.recent 的区间与篇数（重算）',
         [(buckets.get('recent') or {}).get('range'), (buckets.get('recent') or {}).get('doc_count')],
         [list(config.BUCKET_RECENT), len(recent)], 'config.BUCKET_RECENT + documents.jsonl')
cmp_item('C16 buckets.earlier 的区间与篇数（重算）',
         [(buckets.get('earlier') or {}).get('range'), (buckets.get('earlier') or {}).get('doc_count')],
         [list(config.BUCKET_EARLIER), len(earlier)], 'config.BUCKET_EARLIER + documents.jsonl')
cmp_item('C17 per_month_histogram == 逐月重算（含无文档月份显式记 0）',
         tr.get('per_month_histogram'), hist, 'documents.jsonl 的 publish_time')
cmp_item('C18 months_with_zero_documents == 重算的零值月份',
         tr.get('months_with_zero_documents'), [m for m, c in hist.items() if c == 0],
         'documents.jsonl 的 publish_time')

emb = dmeta.get('embedding') or {}
cmp_item('C19 embedding.model_name == config.EMBEDDING["model_name"]', emb.get('model_name'),
         config.EMBEDDING['model_name'], 'config.py')
cmp_item('C20 embedding.model_version == config.EMBEDDING["revision"]', emb.get('model_version'),
         config.EMBEDDING['revision'], 'config.py')
cmp_item('C21 embedding.resolved_snapshot == config.EMBEDDING["revision"]',
         emb.get('resolved_snapshot'), config.EMBEDDING['revision'], 'config.py')
cmp_item('C22 embedding.dim == config.EMBEDDING["dim"]', emb.get('dim'),
         config.EMBEDDING['dim'], 'config.py')
cmp_item('C23 embedding.vector_count == 文本块条数（重算）', emb.get('vector_count'), n_chunks,
         'chunks.jsonl')
cmp_item('C24 index\\build_meta.json 的模型／版本／维度与 config.EMBEDDING 一致',
         [bmeta.get('model_name'), bmeta.get('model_revision'), bmeta.get('dim')],
         [config.EMBEDDING['model_name'], config.EMBEDDING['revision'], config.EMBEDDING['dim']],
         'index\\build_meta.json + config.py')
cmp_item('C25 index\\build_meta.json 的 doc／chunk／vector 条数与实测一致',
         [bmeta.get('doc_count'), bmeta.get('chunk_count'), bmeta.get('vector_count')],
         [n_docs, n_chunks, n_chunks], 'index\\build_meta.json + 数据集文件')

ck = dmeta.get('chunking') or {}
cmp_item('C26 chunking.target／max／min／overlap == config.CHUNK（重算比对）',
         [ck.get('target_chars'), ck.get('max_chars'), ck.get('min_chars'), ck.get('overlap_chars')],
         [config.CHUNK['target_chars'], config.CHUNK['max_chars'], config.CHUNK['min_chars'],
          config.CHUNK['overlap_chars']], 'config.CHUNK')
cmp_item('C27 chunking.boundary_priority／strip_rules == config.CHUNK',
         [ck.get('boundary_priority'), ck.get('strip_rules')],
         [list(config.CHUNK['boundary_priority']), config.CHUNK['strip_rules']], 'config.CHUNK')
cmp_item('C28 chunking.min_doc_chars == config.MIN_DOC_CHARS', ck.get('min_doc_chars'),
         config.MIN_DOC_CHARS, 'config.py')
cmp_item('C29 chunking.chunk_id_stride == config.DOC_ID_STRIDE', ck.get('chunk_id_stride'),
         config.DOC_ID_STRIDE, 'config.py')

ga = parse_dt(dmeta.get('generated_at'))
chk(ga is not None, 'C30 generated_at 存在且可按 ISO8601 解析',
    '实测 %r' % dmeta.get('generated_at'))
chk(bool(crep) and crep.get('generated_at') == dmeta.get('generated_at'),
    'C31 generated_at 与 reports\\consistency_report.json 一致（读报告比对，不当作独立证据）',
    '数据集元信息 %r；报告 %r' % (dmeta.get('generated_at'), crep.get('generated_at')))
bdt = parse_dt(bmeta.get('build_time'))
chk(ga is not None and bdt is not None and ga >= bdt,
    'C32 生成时间不早于向量索引构建时间（build_meta.json）',
    '实测 generated_at=%s ≥ build_time=%s' % (dmeta.get('generated_at'), bmeta.get('build_time')))


# ==========================================================================
print(); print('=' * 78)
print('D、document 必需字段无空值（《12》§八 第 4 行；逐行检查）')
print('=' * 78)

REQUIRED_DOC_FIELDS = ('title', 'content', 'source', 'category', 'publish_time', 'ingest_time')
missing_by_field = Counter()
d_offenders = []
for ln, d in doc_rows:
    bad = [f for f in REQUIRED_DOC_FIELDS
           if d.get(f) is None or (isinstance(d.get(f), str) and not d.get(f).strip())]
    for f in bad:
        missing_by_field[f] += 1
    if bad:
        d_offenders.append('doc_id=%s（第%d行）缺 %s' % (d.get('doc_id'), ln, '／'.join(bad)))
chk(not d_offenders, 'D1 六个必需字段逐行非空（%s）' % '／'.join(REQUIRED_DOC_FIELDS),
    '实测 缺失计数 %s；涉及 %d 篇%s'
    % (' '.join('%s=%d' % (f, missing_by_field.get(f, 0)) for f in REQUIRED_DOC_FIELDS),
       len(d_offenders), '：' + br(d_offenders) if d_offenders else ''))


# ==========================================================================
print(); print('=' * 78)
print('E、三个判重键唯一（《12》§八 第 5 行；url／规范化 title／正文 SHA-256 前 16 位）')
print('=' * 78)

url_vals = [(d.get('url') or '').strip() for _, d in doc_rows if isinstance(d.get('url'), str)]
blank_urls = ['doc_id=%s（第%d行）' % (d.get('doc_id'), ln) for ln, d in doc_rows
              if not (isinstance(d.get('url'), str) and d.get('url').strip())]
norm_titles = [normalize_title(d.get('title')) for _, d in doc_rows]
title_dups = dup_groups([t for t in norm_titles if t])
url_dups = dup_groups([u for u in url_vals if u])
stored_fp = [d.get('content_sha256_16') for _, d in doc_rows]
calc_fp = [fingerprint(d.get('content') or '') for _, d in doc_rows]
fp_mismatch = ['doc_id=%s（第%d行）存 %r／重算 %s' % (d.get('doc_id'), ln, s, c)
               for (ln, d), s, c in zip(doc_rows, stored_fp, calc_fp)
               if str(s or '').strip() != c]
fp_dups = dup_groups(calc_fp)
chk(not url_dups, 'E1 url 唯一（同源同链接只入一次）',
    '实测 非空 url %d 个、去重后 %d 个、重复组 %d%s；空 url %d 篇%s'
    % (len(url_vals), len(set(url_vals)), len(url_dups),
       '：' + br(sorted(url_dups)) if url_dups else '', len(blank_urls),
       '：' + br(blank_urls) if blank_urls else ''))
chk(not title_dups, 'E2 规范化 title 唯一（规则取自 config.DEDUP["title_normalize"]）',
    '实测 非空标题 %d 个、规范化去重后 %d 个、重复组 %d%s'
    % (sum(1 for t in norm_titles if t), len(set(t for t in norm_titles if t)),
       len(title_dups), '：' + br(sorted(title_dups)) if title_dups else ''))
chk(not fp_mismatch, 'E3 存储的 content_sha256_16 与正文重算值一致（sha256 前 %d 位）' % _FP_HEX,
    '实测 %d 篇逐篇重算；不一致 %d 篇%s'
    % (n_docs, len(fp_mismatch), '：' + br(fp_mismatch) if fp_mismatch else ''))
chk(not fp_dups, 'E4 正文指纹（%s）全数据集唯一' % config.DEDUP['content_fingerprint'],
    '实测 指纹 %d 个、去重后 %d 个、重复组 %d%s'
    % (len(calc_fp), len(set(calc_fp)), len(fp_dups),
       '：' + br(sorted(fp_dups)) if fp_dups else ''))
chk((not blank_urls) or ('为空' in t13 and 'url' in t13),
    'E5 空 url 的口径已在《13》说明（硬约束 3 允许访问受限时为空）',
    '实测 空 url %d 篇；《13》中出现“为空” %d 处、提到 url %d 处'
    % (len(blank_urls), t13.count('为空'), t13.count('url')))


# ==========================================================================
print(); print('=' * 78)
print('F、监管公开信息标题规则（《12》§八 第 6 行 + v1.1 修订：原标题（当事人）、不臆造、不机器生成）')
print('=' * 78)

reg_rows = [(ln, d) for ln, d in doc_rows if d.get('category') == '监管公开信息']
chk(bool(reg_rows), 'F1 监管公开信息类别非空（标题规则的作用面）',
    '实测 %d 篇' % len(reg_rows))

PLACEHOLDER = ('未知', '无', '待补充', '待定', '占位', 'placeholder', 'untitled', '未命名',
               'null', 'None', 'TBD', '当事人', '（略）')
MACHINE_MARKERS = ('未知', '无标题', '待补充', '待定', '占位', 'placeholder', 'untitled',
                   '未命名', 'TBD', '示例标题', '测试标题', '正文缺失', '内容缺失', '（略）')
bad_form, bad_placeholder, bad_raw = [], [], []


def norm_ws(s):
    return re.sub(r'\s+', '', str(s or ''))


for ln, d in reg_rows:
    title = str(d.get('title') or '')
    m = re.search(r'（([^（）]*)）\s*$', title)
    if not m or not m.group(1).strip():
        bad_form.append('doc_id=%s（第%d行）%r' % (d.get('doc_id'), ln, title))
        continue
    parts = [p.strip() for p in re.split(r'[、,，;；]', m.group(1).strip()) if p.strip()]
    parts = [(re.sub(r'等\d*人?$', '', p).strip() or p) for p in parts]
    hit = [p for p in parts if p in PLACEHOLDER]
    if hit:
        bad_placeholder.append('doc_id=%s 当事人段为占位词：%s' % (d.get('doc_id'), '、'.join(hit)))
    raw_p = os.path.join(raw_dir, '%s.json' % d.get('doc_id'))
    if not os.path.isfile(raw_p):
        bad_raw.append('doc_id=%s 缺 raw 文件：%s' % (d.get('doc_id'), raw_p))
        continue
    raw_txt = norm_ws((read_json(raw_p) or {}).get('raw_text'))
    miss = [p for p in parts if norm_ws(p) not in raw_txt]
    if miss:
        bad_raw.append('doc_id=%s 当事人段未在来源正文中找到：%s' % (d.get('doc_id'), '、'.join(miss)))
chk(not bad_form, 'F2 监管公开信息标题均为“原标题（当事人）”构造（全角括号＋非空当事人）',
    '实测 %d/%d 篇符合结尾“（当事人）”形态%s'
    % (len(reg_rows) - len(bad_form), len(reg_rows), '；不符合：' + br(bad_form) if bad_form else ''))
chk(not bad_placeholder, 'F3 当事人段不是占位词（未臆造标题）',
    '实测 占位词命中 %d 篇%s'
    % (len(bad_placeholder), '：' + br(bad_placeholder) if bad_placeholder else ''))
chk(not bad_raw, 'F4 当事人逐段可在来源正文（raw\\）中找到（当事人来自来源，可复核）',
    '实测 %d 篇逐段比对；不符 %d 篇%s'
    % (len(reg_rows), len(bad_raw), '：' + br(bad_raw) if bad_raw else ''))
reg_dups = dup_groups([normalize_title(d.get('title')) for _, d in reg_rows])
chk(not reg_dups, 'F5 监管公开信息构造后标题唯一',
    '实测 %d 篇、去重后 %d 个、重复组 %d%s'
    % (len(reg_rows), len(set(normalize_title(d.get('title')) for _, d in reg_rows)),
       len(reg_dups), '：' + br(sorted(reg_dups)) if reg_dups else ''))
machine_hits = []
for ln, d in doc_rows:
    title = str(d.get('title') or '')
    why = [mk for mk in MACHINE_MARKERS if mk in title]
    if str(d.get('doc_id')) in title:
        why.append('含 doc_id 数字 %s' % d.get('doc_id'))
    if sum(1 for ch in title if '\u4e00' <= ch <= '\u9fff') < 4:
        why.append('汉字不足 4 个')
    if title != title.strip() or not title.strip():
        why.append('首尾空白')
    if why:
        machine_hits.append('doc_id=%s（第%d行）：%s' % (d.get('doc_id'), ln, '、'.join(why)))
chk(not machine_hits, 'F6 全库标题无机器生成痕迹（占位词／doc_id 数字／汉字过短／首尾空白）',
    '实测 标题 %d 个；命中 %d 个%s'
    % (len(docs), len(machine_hits), '：' + br(machine_hits) if machine_hits else ''))


# ==========================================================================
print(); print('=' * 78)
print('G、company_list 取值规则（《12》§八 第 7 行 + v1.1 修订：公告／财经新闻非空；其余允许空数组但不得 null）')
print('=' * 78)

null_cl, nonlist_cl, empty_required = [], [], []
empty_by_cat = Counter()
allow_empty = [c for c in config.CATEGORIES if c not in config.CATEGORIES_REQUIRING_COMPANY]
for ln, d in doc_rows:
    cl = d.get('company_list', '__MISSING__')
    if cl == '__MISSING__' or cl is None:
        null_cl.append('doc_id=%s（第%d行）' % (d.get('doc_id'), ln))
        continue
    if not isinstance(cl, list):
        nonlist_cl.append('doc_id=%s（第%d行）类型 %s' % (d.get('doc_id'), ln, type(cl).__name__))
        continue
    if not cl:
        empty_by_cat[d.get('category')] += 1
        if d.get('category') in config.CATEGORIES_REQUIRING_COMPANY:
            empty_required.append('doc_id=%s（%s）' % (d.get('doc_id'), d.get('category')))
chk(not null_cl, 'G1 company_list 不得为 null／缺失',
    '实测 null／缺失 %d 篇%s' % (len(null_cl), '：' + br(null_cl) if null_cl else ''))
chk(not nonlist_cl, 'G2 company_list 类型为数组',
    '实测 非数组 %d 篇%s' % (len(nonlist_cl), '：' + br(nonlist_cl) if nonlist_cl else ''))
chk(not empty_required, 'G3 公告与财经新闻的 company_list 非空（config.CATEGORIES_REQUIRING_COMPANY）',
    '实测 要求非空的类别 %s；空数组违规 %d 篇%s'
    % ('／'.join(config.CATEGORIES_REQUIRING_COMPANY), len(empty_required),
       '：' + br(empty_required) if empty_required else ''))
chk(all(c in allow_empty for c in empty_by_cat),
    'G4 空数组只出现在允许为空的类别（政策文件／监管公开信息）',
    '实测 空数组 %d 篇，分布 %s；允许为空的类别 %s'
    % (sum(empty_by_cat.values()), dict(empty_by_cat) or '无', '／'.join(allow_empty)))


# ==========================================================================
print(); print('=' * 78)
print('H、覆盖公司集合（《12》§八 第 8 行：恰好等于 T2 选定的公司，取自 config.COMPANIES）')
print('=' * 78)

cfg_codes = sorted(c['code'] for c in config.COMPANIES)
missing_codes = sorted(set(cfg_codes) - covered)
extra_codes = sorted(covered - set(cfg_codes))
chk(not missing_codes and not extra_codes,
    'H1 company_list 并集 == config.COMPANIES（%d 家）' % len(cfg_codes),
    '实测 覆盖 %d 家／配置 %d 家；缺失 %s；多出 %s；覆盖集合 %s'
    % (len(covered), len(cfg_codes), '、'.join(missing_codes) or '无',
       '、'.join(extra_codes) or '无', '、'.join(sorted(covered))))


# ==========================================================================
print(); print('=' * 78)
print('I、切分编号规则（《12》§八 第 9 行：每篇 ≥1 块、chunk_index 从 0 连续无重复、chunk_id 公式）')
print('=' * 78)

by_doc = defaultdict(list)
for ln, c in chunk_rows:
    by_doc[c.get('doc_id')].append((ln, c))
doc_ids_all = [d.get('doc_id') for _, d in doc_rows]
zero_chunk_docs = [did for did in doc_ids_all if did not in by_doc]
gap_docs, dup_index_docs = [], []
for did, cs in by_doc.items():
    idxs = [c.get('chunk_index') for _, c in cs]
    if len(set(idxs)) != len(idxs):
        dup_index_docs.append('doc_id=%s（块数 %d）' % (did, len(cs)))
    ints = sorted(x for x in idxs if isinstance(x, int) and not isinstance(x, bool))
    if len(ints) != len(cs) or ints != list(range(len(cs))):
        gap_docs.append('doc_id=%s（块数 %d，chunk_index=%s）' % (did, len(cs), sorted(map(str, idxs))[:6]))
bad_formula = []
for ln, c in chunk_rows:
    try:
        ok = (isinstance(c.get('chunk_id'), int)
              and config.chunk_id_for(int(c.get('doc_id')), int(c.get('chunk_index'))) == c.get('chunk_id'))
    except Exception:
        ok = False
    if not ok:
        bad_formula.append('第%d行 chunk_id=%s doc_id=%s chunk_index=%s'
                           % (ln, c.get('chunk_id'), c.get('doc_id'), c.get('chunk_index')))
chk(not zero_chunk_docs, 'I1 每篇文档至少 1 个文本块',
    '实测 文档 %d 篇、无块文档 %d 篇%s'
    % (n_docs, len(zero_chunk_docs), '：' + br(zero_chunk_docs) if zero_chunk_docs else ''))
chk(not gap_docs, 'I2 chunk_index 在文档内从 0 连续递增',
    '实测 涉及文档 %d 篇、不连续 %d 篇%s'
    % (len(by_doc), len(gap_docs), '：' + br(gap_docs) if gap_docs else ''))
chk(not dup_index_docs, 'I3 同一文档内 chunk_index 不重复',
    '实测 重复 %d 篇%s' % (len(dup_index_docs), '：' + br(dup_index_docs) if dup_index_docs else ''))
chk(not bad_formula, 'I4 chunk_id == doc_id * DOC_ID_STRIDE + chunk_index（config.chunk_id_for）',
    '实测 %d 条文本块、公式不符 %d 条%s；步长 config.DOC_ID_STRIDE=%d'
    % (n_chunks, len(bad_formula), '：' + br(bad_formula) if bad_formula else '',
       config.DOC_ID_STRIDE))
per_doc_n = [len(cs) for cs in by_doc.values()]
note('I5 每篇块数分布（证据项，不计入判定）',
     '实测 每篇 %d～%d 块、均值 %.2f、恰好 1 块的文档 %d 篇、块数最多的文档 %s'
     % (min(per_doc_n or [0]), max(per_doc_n or [0]), (n_chunks / n_docs) if n_docs else 0,
        sum(1 for x in per_doc_n if x == 1),
        max(by_doc.items(), key=lambda kv: len(kv[1]))[0] if by_doc else '无'))


# ==========================================================================
print(); print('=' * 78)
print('J、文本块长度与重叠（《12》§八 第 10 行：落在《13》固定区间内、重叠不超过声明上限）')
print('=' * 78)


def declared_param(key):
    m = re.search(r'\|\s*`%s`\s*\|\s*(\d+)\s*\|' % re.escape(key), t13)
    return int(m.group(1)) if m else None


declared = {k: declared_param(k) for k in ('target_chars', 'max_chars', 'min_chars', 'overlap_chars')}
chk(all(v is not None for v in declared.values()), 'J1 《13》§3.1 声明了四个切分参数（不写死数值）',
    '实测 解析 %s' % declared)
chk(all(declared[k] == config.CHUNK[k] for k in declared if declared[k] is not None),
    'J2 《13》声明的切分参数 == config.CHUNK（封版后不得更改）',
    '实测 《13》 %s；config %s' % (declared, {k: config.CHUNK[k] for k in declared}))

lens = [(ln, c, len(str(c.get('content') or ''))) for ln, c in chunk_rows]
over = [t for t in lens if t[2] > config.CHUNK['max_chars']]
under = [t for t in lens if t[2] < config.CHUNK['min_chars']]
chk(not over, 'J3 无文本块超过 max_chars=%d' % config.CHUNK['max_chars'],
    '实测 字符 min／mean／max = %d／%.2f／%d；超上限 %d 块%s'
    % (min(t[2] for t in lens), sum(t[2] for t in lens) / len(lens), max(t[2] for t in lens),
       len(over),
       '：' + br(['chunk_id=%s 字符=%d' % (c.get('chunk_id'), n) for _, c, n in over]) if over else ''))
exempt = {(e.get('doc_id'), e.get('chunk_index'))
          for e in (cstats.get('min_chars_exemptions') or []) if isinstance(e, dict)}
doc_len = {d.get('doc_id'): len(str(d.get('content') or '')) for _, d in doc_rows}
bad_under = []
for ln, c, n in under:
    key = (c.get('doc_id'), c.get('chunk_index'))
    if key not in exempt or doc_len.get(c.get('doc_id'), 0) >= config.CHUNK['target_chars']:
        bad_under.append('chunk_id=%s doc_id=%s（第%d行）字符 %d'
                         % (c.get('chunk_id'), c.get('doc_id'), ln, n))
chk(not bad_under,
    'J4 低于 min_chars 的块均为“整篇正文短于 target_chars”的豁免（读 reports\\chunk_stats.json 核对）',
    '实测 低于下限 %d 块%s；报告登记豁免 %d 条%s；不满足豁免条件或未登记 %d 块%s'
    % (len(under),
       '：' + br(['chunk_id=%s 字符=%d' % (c.get('chunk_id'), n) for _, c, n in under]) if under else '',
       len(exempt), '：' + br(sorted(exempt)) if exempt else '', len(bad_under),
       '：' + br(bad_under) if bad_under else ''))
max_ov, ov_at = 0, None
for did, cs in by_doc.items():
    cs_sorted = sorted(cs, key=lambda t: t[1].get('chunk_index'))
    for (_, a), (_, b) in zip(cs_sorted, cs_sorted[1:]):
        A, B = str(a.get('content') or ''), str(b.get('content') or '')
        best = 0
        for k in range(min(len(A), len(B)), 0, -1):
            if A[-k:] == B[:k]:
                best = k
                break
        if best > max_ov:
            max_ov, ov_at = best, (did, a.get('chunk_index'), b.get('chunk_index'))
chk(max_ov <= config.CHUNK['overlap_chars'] and max_ov <= (declared['overlap_chars'] or 0),
    'J5 相邻文本块重叠不超过声明上限',
    '实测 最大重叠 %d 字符（doc_id=%s 的第 %s／%s 块）；config.CHUNK.overlap_chars=%d；《13》声明 %s'
    % (max_ov, ov_at[0] if ov_at else '无', ov_at[1] if ov_at else '-', ov_at[2] if ov_at else '-',
       config.CHUNK['overlap_chars'], declared['overlap_chars']))


# ==========================================================================
print(); print('=' * 78)
print('K、向量条数与编号（《12》§八 第 11 行：向量条数 = 文本块条数、无空 vector_id、取值 0..N-1）')
print('=' * 78)

vids = [c.get('vector_id') for _, c in chunk_rows]
null_vid = ['chunk_id=%s（第%d行）' % (c.get('chunk_id'), ln)
            for ln, c in chunk_rows if c.get('vector_id') is None]
nonint_vid = ['chunk_id=%s vector_id=%r' % (c.get('chunk_id'), c.get('vector_id'))
              for _, c in chunk_rows if c.get('vector_id') is not None
              and not isinstance(c.get('vector_id'), int)]
present_vids = [v for v in vids if isinstance(v, int) and not isinstance(v, bool)]
expected_vids = list(range(n_chunks))
missing_vids = [v for v in expected_vids if v not in set(present_vids)]
oor_vids = sorted({v for v in present_vids if v < 0 or v >= n_chunks})
vid_dups = dup_groups(present_vids)
chk(not null_vid and not nonint_vid, 'K1 无空 vector_id（且类型均为整数）',
    '实测 文本块 %d 个；空 vector_id %d 个%s；非整数 %d 个%s'
    % (n_chunks, len(null_vid), '：' + br(null_vid) if null_vid else '',
       len(nonint_vid), '：' + br(nonint_vid) if nonint_vid else ''))
chk(not missing_vids and not oor_vids and not vid_dups and len(present_vids) == n_chunks,
    'K2 vector_id 取值恰为 0..%d（无缺号／越界／重复）' % (n_chunks - 1),
    '实测 distinct=%d、min=%s、max=%s；缺号 %d 个%s；越界 %d 个%s；重复组 %d%s'
    % (len(set(present_vids)), min(present_vids) if present_vids else None,
       max(present_vids) if present_vids else None, len(missing_vids),
       '：' + br(missing_vids) if missing_vids else '', len(oor_vids),
       '：' + br(oor_vids) if oor_vids else '', len(vid_dups),
       '：' + br(sorted(vid_dups)) if vid_dups else ''))

MAP_P = os.path.join(DATASET, 'index', config.FAISS['map_file'])
map_rows = safe_jsonl(MAP_P) if os.path.isfile(MAP_P) else []
map_vids = sorted(r.get('vector_id') for _, r in map_rows if isinstance(r.get('vector_id'), int))
chk(len(map_rows) == n_chunks and map_vids == expected_vids,
    'K3 index\\vector_map.jsonl 行数与 vector_id 集合恰为 0..%d（读文件重算）' % (n_chunks - 1),
    '实测 映射 %d 行、distinct %d；与 chunks.jsonl 的 vector_id 集合一致：%s'
    % (len(map_rows), len(set(map_vids)), sorted(set(map_vids)) == sorted(set(present_vids))))

IDX_P = os.path.join(DATASET, 'index', config.FAISS['index_file'])
if os.path.isfile(IDX_P):
    ntotal, dim, how = index_size(IDX_P)
    chk(ntotal == n_chunks, 'K4 向量条数（索引 ntotal）== 文本块条数 == 映射行数',
        '实测 ntotal=%s、dim=%s、chunks=%d、映射行数=%d、build_meta.vector_count=%s（读法：%s）'
        % (ntotal, dim, n_chunks, len(map_rows), bmeta.get('vector_count'), how))
    chk(dim == config.EMBEDDING['dim'], 'K5 索引维度 == config.EMBEDDING["dim"]',
        '实测 dim=%s；config=%d' % (dim, config.EMBEDDING['dim']))
else:
    chk(False, 'K4 向量条数（索引 ntotal）== 文本块条数 == 映射行数',
        '实测 索引文件缺失：%s' % IDX_P)


# ==========================================================================
print(); print('=' * 78)
print('L、时间口径（《12》§八 第 12、13 行：≤ cutoff、覆盖 ≥90 天、两个时间桶均非空）')
print('=' * 78)

unparsable = ['doc_id=%s（第%d行）' % (d.get('doc_id'), ln)
              for ln, d in doc_rows if parse_date(d.get('publish_time')) is None]
after_cutoff = ['doc_id=%s（第%d行）publish_time=%s' % (d.get('doc_id'), ln, d.get('publish_time'))
                for ln, d in doc_rows
                if (x := parse_date(d.get('publish_time'))) and x > cutoff]
chk(not unparsable and not after_cutoff, 'L1 全部 publish_time ≤ data_cutoff_time',
    '实测 cutoff=%s；publish_time 实测 %s～%s；晚于 cutoff %d 篇%s；不可解析 %d 篇%s'
    % (config.DATA_CUTOFF_DATE, pmin, pmax, len(after_cutoff),
       '：' + br(after_cutoff) if after_cutoff else '',
       len(unparsable), '：' + br(unparsable) if unparsable else ''))
need_days = (cutoff - parse_date(config.ANALYSIS_90_RANGE[0])).days   # 门槛由 config 推出，不写死 90
span = (cutoff - pmin).days if pmin else None
chk(span is not None and span >= need_days,
    'L2 时间覆盖 ≥ %d 天（cutoff − publish_time_min）' % need_days,
    '实测 cutoff − 最早 = %s 天（门槛 %d，由 config.ANALYSIS_90_RANGE 推出）；采集窗 %s～%s（%d 天）'
    % (span, need_days, config.WINDOW_START, config.WINDOW_END, config.WINDOW_DAYS))
chk(len(recent) >= config.MIN_DOCS_PER_TIME_BUCKET,
    'L3 recent 桶非空且 ≥ config.MIN_DOCS_PER_TIME_BUCKET',
    '实测 recent %s～%s = %d 篇（下限 %d）'
    % (config.BUCKET_RECENT[0], config.BUCKET_RECENT[1], len(recent),
       config.MIN_DOCS_PER_TIME_BUCKET))
chk(len(earlier) >= config.MIN_DOCS_PER_TIME_BUCKET,
    'L4 earlier 桶非空且 ≥ config.MIN_DOCS_PER_TIME_BUCKET',
    '实测 earlier %s～%s = %d 篇（下限 %d）'
    % (config.BUCKET_EARLIER[0], config.BUCKET_EARLIER[1], len(earlier),
       config.MIN_DOCS_PER_TIME_BUCKET))
outside = n_docs - len(recent) - len(earlier)
chk(outside == 0, 'L5 全部文档落在两个相对时间桶内（两桶合起来覆盖采集窗）',
    '实测 两桶之外 %d 篇；逐月直方图（含无文档月份，v1.2 报告要求）%s；无文档月份 %s'
    % (outside, '、'.join('%s=%d' % (m, c) for m, c in hist.items()),
       [m for m, c in hist.items() if c == 0] or '无'))


# ==========================================================================
print(); print('=' * 78)
print('M、类目与来源（《12》§八 第 14 行：只用四类 category、无股吧来源；§五 硬约束 12）')
print('=' * 78)

cats = [d.get('category') for d in docs]
cat_counts = Counter(cats)
invalid_cats = sorted({c for c in cats if c not in config.CATEGORIES})
chk(not invalid_cats, 'M1 category 只取 config.CATEGORIES 四类',
    '实测 取值 %s；非法取值 %d 个%s'
    % (dict(cat_counts), len(invalid_cats), '：' + br(invalid_cats) if invalid_cats else ''))
srcs = [d.get('source') for d in docs]
expected_src = set(spec['source'] for spec in config.SOURCES.values())
expected_src.update(config.NEWS_SITES.keys())
invalid_src = sorted({s for s in srcs if s not in expected_src})
guba_src = sorted({s for s in srcs if isinstance(s, str) and '股吧' in s})
chk(not invalid_src and not guba_src, 'M2 source 取值均来自 config（四类来源），无股吧来源',
    '实测 %d 个 source 取值 %s；越界 %d 个 %s；含“股吧”的 source %d 个 %s'
    % (len(set(srcs)), dict(Counter(srcs)), len(invalid_src), br(invalid_src),
       len(guba_src), br(guba_src)))
guba_hits = scan_term('股吧', all_dataset_targets())
guba_bad = [h for h in guba_hits if not h[3]]
chk(not guba_bad, 'M3 《13》与数据集内无股吧来源（排除“不进入／无股吧”一类否定语境）',
    '实测 命中 %d 处（否定语境 %d 处、需处置 %d 处）%s'
    % (len(guba_hits), len(guba_hits) - len(guba_bad), len(guba_bad),
       '：' + br(['%s 第%d行：%s' % (a, b, c[:60]) for a, b, c, _ in guba_bad]) if guba_bad else ''))


# ==========================================================================
print(); print('=' * 78)
print('N、幂等（《12》§八 第 15 行：重复执行不产生重复 doc_id）')
print('=' * 78)

note('N0 幂等检查模式',
     '真实重跑（--with-idempotence：在系统临时目录复跑 T4a→T5，不写入封版数据集）'
     if ARGS.with_idempotence else
     '静态等价（默认模式，未执行真实重跑；加 --with-idempotence 可实跑）')

clean_ids = [d.get('doc_id') for _, d in doc_rows]
clean_dups = dup_groups(clean_ids)
chk(not clean_dups, 'N1 clean\\documents.jsonl 的 doc_id 唯一（数据集内无重复编号）',
    '实测 文档 %d 篇、distinct %d、重复编号 %d 组%s'
    % (n_docs, len(set(clean_ids)), len(clean_dups),
       '：' + br(sorted(clean_dups)) if clean_dups else ''))
raw_ids, raw_bad = [], []
for p in raw_doc_files:
    try:
        obj = read_json(p)
    except Exception as exc:
        raw_bad.append('%s 不可读：%s' % (p, exc))
        continue
    raw_ids.append(obj.get('doc_id'))
    if str(obj.get('doc_id')) != os.path.splitext(os.path.basename(p))[0]:
        raw_bad.append('%s 的文件名与 doc_id=%s 不一致' % (p, obj.get('doc_id')))
raw_dups = dup_groups(raw_ids)
chk(not raw_dups and not raw_bad, 'N2 raw\\ 的 doc_id 唯一且与文件名一致（重跑采集不会新增编号）',
    '实测 raw 文档 %d 个、distinct %d、重复 %d 组%s；文件名／字段不符 %d 个%s'
    % (len(raw_ids), len(set(raw_ids)), len(raw_dups),
       '：' + br(sorted(raw_dups)) if raw_dups else '', len(raw_bad),
       '：' + br(raw_bad) if raw_bad else ''))
dedup_dropped = sorted({w for _, r in dedup_rows for w in (r.get('dropped') or [])})
skipped_ids = sorted({r.get('doc_id') for _, r in skipped_rows if r.get('doc_id') is not None})
expected_clean = sorted(set(raw_ids) - set(dedup_dropped) - set(skipped_ids))
chk(sorted(clean_ids) == expected_clean,
    'N3 重复执行的静态等价：clean 的 doc_id 集合 == raw − 去重淘汰 − 跳过'
    '（读 reports\\dedup_log.jsonl／skipped.jsonl）',
    '实测 raw %d 个 − 去重淘汰 %d 个%s − 跳过 %d 个%s = %d 个；clean 实测 %d 个；差集 %s'
    % (len(set(raw_ids)), len(dedup_dropped), br(dedup_dropped), len(skipped_ids),
       br(skipped_ids), len(expected_clean), len(set(clean_ids)),
       br(sorted(set(expected_clean) ^ set(clean_ids))) or '无'))
chunk_ids = [c.get('chunk_id') for _, c in chunk_rows]
chunk_dups = dup_groups(chunk_ids)
chk(not chunk_dups, 'N4 chunks\\chunks.jsonl 的 chunk_id 唯一（重跑切分不产生重复记录）',
    '实测 文本块 %d 个、distinct %d、重复 %d 组%s'
    % (n_chunks, len(set(chunk_ids)), len(chunk_dups),
       '：' + br(sorted(chunk_dups)) if chunk_dups else ''))

if ARGS.with_idempotence:
    tmp_root = tempfile.mkdtemp(prefix='stage5_idem_')
    try:
        shutil.copytree(raw_dir, os.path.join(tmp_root, 'raw'))
        note('N5 真实重跑准备完成（只用复制件，不写入封版数据集）',
             '临时目录：%s（raw 复制 %d 个文件）' % (tmp_root, len(raw_doc_files)))
        ran = []
        for script in ('dedup.py', 'clean.py', 'chunk.py'):
            cmd = [sys.executable, os.path.join(CODE_DIR, script), '--profile', 'v1', '--dir', tmp_root]
            t0 = time.time()
            try:
                proc = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                                      encoding='utf-8', errors='replace', timeout=900)
                rc = proc.returncode
                out = (proc.stdout or '').strip().split('\n')
                tail = out[-1] if out and out[-1] else ''
                err = (proc.stderr or '').strip().split('\n')
                if rc != 0 and err:
                    tail = tail + ' ／ stderr: ' + err[-1]
            except Exception as exc:
                rc, tail = 127, '%s: %s' % (type(exc).__name__, exc)
            ran.append((script, rc, time.time() - t0, tail))
            note('N5 %s --profile v1 --dir <临时目录>  退出码 %d（%.2fs）'
                 % (script, rc, ran[-1][2]), tail)
        bad_rc = [r for r in ran if r[1] != 0]
        chk(not bad_rc, 'N5a 真实重跑：dedup／clean／chunk 三个环节退出码均为 0',
            '实测 %s' % '；'.join('%s 退出码 %d' % (r[0], r[1]) for r in ran))
        tmp_docs_p = os.path.join(tmp_root, 'clean', 'documents.jsonl')
        rows_a = read_jsonl(tmp_docs_p)
        ids_a = [r.get('doc_id') for _, r in rows_a]
        cmd = [sys.executable, os.path.join(CODE_DIR, 'clean.py'), '--profile', 'v1', '--dir', tmp_root]
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                              encoding='utf-8', errors='replace', timeout=900)
        rows_b = read_jsonl(tmp_docs_p)
        ids_b = [r.get('doc_id') for _, r in rows_b]
        tmp_dup_a, tmp_dup_b = dup_groups(ids_a), dup_groups(ids_b)
        chk(not tmp_dup_a and not tmp_dup_b and len(rows_a) == len(rows_b) and ids_a == ids_b,
            'N6 真实重跑：clean.py 连跑两次不产生重复记录（行数与 doc_id 序列不变）',
            '实测 第一次 %d 行（重复 %d 组）、第二次 %d 行（重复 %d 组，退出码 %d）；'
            '两次 doc_id 序列相同：%s'
            % (len(rows_a), len(tmp_dup_a), len(rows_b), len(tmp_dup_b), proc.returncode,
               ids_a == ids_b))
        chk(sorted(ids_b) == sorted(clean_ids),
            'N7 真实重跑：重跑得到的 doc_id 集合与封版数据集一致',
            '实测 重跑 %d 个／封版 %d 个；差集 %s'
            % (len(set(ids_b)), len(set(clean_ids)),
               br(sorted(set(ids_b) ^ set(clean_ids))) or '无'))
        tmp_chunks_p = os.path.join(tmp_root, 'chunks', 'chunks.jsonl')
        tmp_chunks = read_jsonl(tmp_chunks_p) if os.path.isfile(tmp_chunks_p) else []
        tmp_cids = [c.get('chunk_id') for _, c in tmp_chunks]
        chk(len(tmp_chunks) == n_chunks and sorted(tmp_cids) == sorted(chunk_ids),
            'N8 真实重跑：chunk.py 产出的文本块条数与 chunk_id 集合与封版一致',
            '实测 重跑 %d 块／封版 %d 块；chunk_id 集合一致：%s'
            % (len(tmp_chunks), n_chunks, sorted(tmp_cids) == sorted(chunk_ids)))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        note('N9 临时目录已清理', tmp_root)
else:
    note('N5 真实重跑未执行（静态等价模式）',
         '如需真实重跑：python 工具\\验收第5阶段数据.py --with-idempotence')


# ==========================================================================
print(); print('=' * 78)
print('O、越界排除（《12》§八 第 16 行：不引入六张表以外的表、不写死大语言模型型号）')
print('=' * 78)

m6 = re.search(r'恒为六张\**——\s*([^，。；]+)', t10)
six_tables = [s.strip() for s in m6.group(1).split('、')] if m6 else []
chk(len(six_tables) == 6, 'O1 从《10》§4.4 解析六张表清单（不写死表名）',
    '实测 %d 张：%s（来源：%s）' % (len(six_tables), '、'.join(six_tables), os.path.basename(P10)))
cand_tables = defaultdict(list)
ddl_hits = []
for label, path in structural_targets():
    text = read_text(path)
    for i, line in enumerate(text.split('\n'), 1):
        for mm in re.finditer(r'\x60([a-z][a-z0-9_]*)\x60\s*表', line):
            cand_tables[mm.group(1)].append((label, i, line.strip()))
        if re.search(r'CREATE\s+TABLE|建表语句|\bDDL\b', line, re.I):
            ddl_hits.append((label, i, line.strip(),
                             any(m in line for m in ('不写', '不产出', '不做', '禁止'))))
bad_extra = []
for name, occ in cand_tables.items():
    if name in six_tables:
        continue
    for label, i, line in occ:
        if not any(m in line for m in ('已删除', '不复活', '不新增', '之外', '不构成', '保持为空', '不入库')):
            bad_extra.append('%s 第%d行 提到表名 %s：%s' % (label, i, name, line[:80]))
chk(not bad_extra, 'O2 未引入六张表以外的表（表名候选 + 否定语境判定）',
    '实测 表名候选 %d 个：%s；六表内 %d 个；越界且无否定语境 %d 处%s'
    % (len(cand_tables), '、'.join(sorted(cand_tables)),
       len([k for k in cand_tables if k in six_tables]), len(bad_extra),
       '：' + br(bad_extra) if bad_extra else ''))
sql_files = [p for p in iter_files(DATASET) if p.lower().endswith('.sql')] if os.path.isdir(DATASET) else []
bad_ddl = [h for h in ddl_hits if not h[3]]
chk(not bad_ddl and not sql_files, 'O3 无建表语句／DDL 痕迹／.sql 文件（本阶段不产出 DDL）',
    '实测 DDL 痕迹 %d 处（否定语境 %d 处、需处置 %d 处）；.sql 文件 %d 个%s'
    % (len(ddl_hits), len(ddl_hits) - len(bad_ddl), len(bad_ddl), len(sql_files),
       '：' + br(['%s 第%d行：%s' % (a, b, c[:60]) for a, b, c, _ in bad_ddl]) if bad_ddl else ''))

llm_hits = scan_term('大语言模型', structural_targets(),
                     neg_markers=('TBD', '不选型', '不写死', '登记', '第 8 阶段', '未选', '保持'))
llm_bad = [h for h in llm_hits if not h[3]]
chk(not llm_bad, 'O4 「大语言模型」的每一处出现都在 TBD／登记语境（本阶段未选型、未写死型号）',
    '实测 出现 %d 处，其中 TBD／登记语境 %d 处、需处置 %d 处%s'
    % (len(llm_hits), len(llm_hits) - len(llm_bad), len(llm_bad),
       '：' + br(['%s 第%d行：%s' % (a, b, c[:60]) for a, b, c, _ in llm_bad]) if llm_bad else ''))

cfg_src = read_text(os.path.join(CODE_DIR, 'config.py'))
TOKEN_RE = r'[A-Za-z][A-Za-z0-9._/\-]*\d[A-Za-z0-9._/\-]*'


def token_reason(tok):
    """把“含字母且含数字”的标识符归到可解释的来源；判断不了就返回 None（可疑）。"""
    if tok in cfg_src:
        return 'config'
    if re.match(r'^[a-z][a-z0-9_]*$', tok):
        return '形状：小写键名／字段名（config 键、报告键、数据字典字段）'
    if re.match(r'^[A-Z]{2,}-\d+$', tok):
        return '形状：算法名／需求编号'
    if re.match(r'^T\d+[a-z]?$', tok):
        return '形状：任务编号'
    if re.match(r'^v\d+(\.\d+)*$', tok):
        return '形状：版本号'
    if re.match(r'^[A-Za-z]-\d+$', tok):
        return '形状：数学记号'
    if re.match(r'^[0-9a-f]{8,}$', tok):
        return '形状：哈希／索引号'
    if '/' in tok and '.' in tok:
        return '形状：URL／路径'
    return None


tok_where = defaultdict(list)
for label, path in structural_targets():
    for i, line in enumerate(read_text(path).split('\n'), 1):
        for tok in re.findall(TOKEN_RE, line):
            tok_where[tok].append((label, i))
reasons = {t: token_reason(t) for t in tok_where}
suspect = {t: v for t, v in reasons.items() if v is None}
corpus_toks = Counter()
for _label, path, field in corpus_targets():
    for _, obj in read_jsonl(path):
        corpus_toks.update(re.findall(TOKEN_RE, str(obj.get(field) or '')))
chk(not suspect, 'O5 结构化文本中的“含字母且含数字”标识符均可由 config.py、编号／版本／哈希形状'
                 '或小写键名解释（未写死大语言模型型号；Embedding 模型名来自 config.EMBEDDING）',
    '实测 标识符 %d 个；可解释 %d（config %d／形状 %d）；可疑 %d %s；'
    '另有语料正文同类标识符 %d 个（%d 次），属原文引用、不计入判定'
    % (len(tok_where), len(tok_where) - len(suspect),
       sum(1 for v in reasons.values() if v == 'config'),
       sum(1 for v in reasons.values() if v and v != 'config'), len(suspect),
       br(['%s（%s 第%d行）' % (t, tok_where[t][0][0], tok_where[t][0][1]) for t in sorted(suspect)]),
       len(corpus_toks), sum(corpus_toks.values())))


# ==========================================================================
print(); print('=' * 78)
print('P、禁用术语（《12》§八 第 17 行：不出现「向量」与「数据库」的连写，否定语境除外）')
print('=' * 78)

BANNED = '向量' + '数据库'      # 拼接构造：本脚本源码内不出现该连写，供 grep 复核
term_hits = scan_term(BANNED, all_dataset_targets())
term_bad = [h for h in term_hits if not h[3]]
chk(not term_bad, 'P1 《13》与数据集内不出现该连写（否定语境除外）',
    '实测 命中 %d 处（否定语境 %d 处、需处置 %d 处）%s；'
    '允许术语“向量索引”出现 %d 处、“向量检索组件”出现 %d 处'
    % (len(term_hits), len(term_hits) - len(term_bad), len(term_bad),
       '：' + br(['%s 第%d行：%s' % (a, b, c[:60]) for a, b, c, _ in term_bad]) if term_bad else '',
       t13.count('向量索引'), t13.count('向量检索组件')))
self_src = read_text(os.path.abspath(__file__))
chk(BANNED not in self_src, 'P2 本脚本源码内不出现该连写（以拼接方式构造）',
    '实测 出现 %d 处（源码 %d 字节、%d 行）'
    % (self_src.count(BANNED), len(self_src.encode('utf-8')), len(self_src.splitlines())))


# ==========================================================================
print(); print('=' * 78)
print('Q、《13》在《00-项目总览与索引》中的登记（《12》§八 第 18 行）')
print('=' * 78)

DOC_NAME = '13-数据准备（第五阶段）'
q_hits = [(i, L.strip()) for i, L in enumerate(t00.split('\n'), 1) if DOC_NAME in L]
chk(bool(q_hits), 'Q1 《13-数据准备（第五阶段）.md》已登记在《00-项目总览与索引.md》',
    '实测 命中 %d 行：%s（登记检查针对工作区《00》，与 --doc 覆盖无关）'
    % (len(q_hits), br(['第%d行' % i for i, _ in q_hits])))
q_status = [(i, L) for i, L in q_hits if ('已产出' in L or '已完成' in L or '第 5 阶段产出' in L)]
chk(bool(q_status), 'Q2 登记行带状态（已产出／已完成／第 5 阶段产出）',
    '实测 带状态 %d 行%s'
    % (len(q_status), '：' + br(['第%d行' % i for i, _ in q_status]) if q_status else ''))


# ==========================================================================
print(); print('=' * 78)
print('S、索引集中度与跨公司同名标题（守卫项：单篇不得独占索引、同一标题不得跨公司复用）')
print('=' * 78)

chunks_per_doc = Counter(c.get('doc_id') for _, c in chunk_rows)
doc_by_id = {d.get('doc_id'): d for _, d in doc_rows}
ranked_docs = chunks_per_doc.most_common()          # [(doc_id, 块数)]，按块数降序


def doc_title(doc_id):
    return str((doc_by_id.get(doc_id) or {}).get('title') or '')


if not ranked_docs or not n_chunks:
    chk(False, 'S1 索引集中度：单篇 ≤ %.0f%%、前 5 篇合计 ≤ %.0f%%'
        % (100 * MAX_TOP1_CHUNK_SHARE, 100 * MAX_TOP5_CHUNK_SHARE),
        '实测 chunks\\chunks.jsonl 无文本块，集中度无法计算')
else:
    top1_id, top1_n = ranked_docs[0]
    top1_share = top1_n / n_chunks
    top5 = ranked_docs[:5]
    top5_share = sum(k for _, k in top5) / n_chunks
    offenders = []
    if top1_share > MAX_TOP1_CHUNK_SHARE:
        offenders.append('单篇占比超限：doc_id=%s《%s》%d 块（%.2f%% > %.0f%%）'
                         % (top1_id, doc_title(top1_id), top1_n, 100 * top1_share,
                            100 * MAX_TOP1_CHUNK_SHARE))
    if top5_share > MAX_TOP5_CHUNK_SHARE:
        offenders.append('前 5 篇合计超限：%.2f%% > %.0f%%；明细 %s'
                         % (100 * top5_share, 100 * MAX_TOP5_CHUNK_SHARE,
                            '、'.join('doc_id=%s《%s》%d 块' % (did, doc_title(did), k)
                                      for did, k in top5)))
    for _x in offenders:
        print('    !! %s' % _x)
    chk(not offenders,
        'S1 索引集中度：单篇 ≤ %.0f%%、前 5 篇合计 ≤ %.0f%%（守卫阈值，非 config）'
        % (100 * MAX_TOP1_CHUNK_SHARE, 100 * MAX_TOP5_CHUNK_SHARE),
        '实测 单篇最大 %.2f%%（doc_id=%s《%s》%d/%d 块）、前 5 篇合计 %.2f%%；超限 %d 项'
        % (100 * top1_share, top1_id, doc_title(top1_id), top1_n, n_chunks,
           100 * top5_share, len(offenders)))

by_title = defaultdict(list)
for _, d in doc_rows:
    t = normalize_title(d.get('title'))
    if t:
        by_title[t].append(d)
name_groups = {t: ds for t, ds in by_title.items() if len(ds) > 1}
collisions = []
for t, ds in name_groups.items():
    comp_sets = {frozenset(str(x) for x in (d.get('company_list') or [])) for d in ds}
    if len(comp_sets) > 1:
        collisions.append((t, ds))
collisions.sort(key=lambda item: item[0])
for t, ds in collisions:
    print('    !! 标题《%s》被不同公司集合的文档共用：%s'
          % (t, '、'.join('doc_id=%s（公司 %s）'
                          % (d.get('doc_id'),
                             '／'.join(sorted(str(x) for x in (d.get('company_list') or []))) or '空')
                          for d in sorted(ds, key=lambda x: str(x.get('doc_id'))))))
chk(not collisions, 'S2 同一规范化标题不跨公司复用（company_list 集合相同才允许同名）',
    '实测 非空标题 %d 个、同名组 %d 组、跨公司同名 %d 组%s'
    % (len(by_title), len(name_groups), len(collisions),
       '：' + br([t for t, _ in collisions]) if collisions else ''))

per_doc_counts = [chunks_per_doc.get(d.get('doc_id'), 0) for _, d in doc_rows]
median_chunks = statistics.median(per_doc_counts) if per_doc_counts else 0
if ranked_docs:
    top1_id, top1_n = ranked_docs[0]
    top1_chars = len(str((doc_by_id.get(top1_id) or {}).get('content') or ''))
    note('S3 集中度证据（只报告，不计入判定）',
         '实测 top-1 占比 %.2f%%、top-5 合计占比 %.2f%%；最大文档 doc_id=%s《%s》%d 块／%d 字符；'
         '每篇块数中位数 %.1f 块（文档 %d 篇、文本块 %d 个）'
         % (100 * top1_share, 100 * top5_share, top1_id, doc_title(top1_id), top1_n, top1_chars,
            median_chunks, n_docs, n_chunks))
else:
    note('S3 集中度证据（只报告，不计入判定）', '实测无文本块记录，集中度证据不可用')


# ==========================================================================
print(); print('=' * 78)
print('R、汇总与收口（《12》§八 末行：全套检查通过才放行）')
print('=' * 78)

_passed_before = sum(1 for ok, _, _ in results if ok)
print('  检查项合计（A～S）：%d 项，其中通过 %d、失败 %d'
      % (len(results), _passed_before, len(fails)))
chk(not fails, 'R1 全部检查项通过（任一失败即非零退出）',
    '实测 失败 %d 项：%s' % (len(fails), br(fails, limit=30) if fails else '无'))
chk(os.path.isfile(CROSS_DOC), 'R2 工作区跨文档核验脚本存在（本脚本不调用它，供操作者另行运行）',
    '实测 %s：%s；操作者应另行运行：python 工具\\跨文档核验.py'
    % (CROSS_DOC, '存在' if os.path.isfile(CROSS_DOC) else '缺失'))
print()
print('  最终：检查项 %d 项，通过 %d，失败 %d'
      % (len(results), sum(1 for ok, _, _ in results if ok), len(fails)))

print('=' * 78)
if not fails:
    print('结论：全部通过（%d/%d 项）。第 5 阶段数据侧验收通过，退出码 0。'
          % (len(results), len(results)))
else:
    print('结论：存在 %d 项失败（通过 %d/%d 项）：'
          % (len(fails), len(results) - len(fails), len(results)))
    for _lab, _det in fail_evidence:
        print('  - %s  %s' % (_lab, _det))
print('=' * 78)
sys.exit(1 if fails else 0)
