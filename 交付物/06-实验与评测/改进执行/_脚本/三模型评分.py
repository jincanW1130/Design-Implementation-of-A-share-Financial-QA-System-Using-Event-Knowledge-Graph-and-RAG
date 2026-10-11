# -*- coding: utf-8 -*-
"""三模型评分运行器（三模型金标准 · 问答侧）

对正式集 582 条有效答案，用三模型独立评分：
  deepseek-flash（新跑全量）＋ kimi-k2.7-code（新跑全量）＋ glm-5.3-flash（复用既有缓存 + 补跑）
Prompt／量表／缓存与台账格式**逐字复用**冻结《评分脚本.py》（stage10-qa-judge-v1.0）。

复用方式：importlib 加载冻结脚本为模块，apply_dataset("formal") 后：
  · 重定向全部输出路径到 改进执行/三模型金标准/评分/（不碰冻结目录）
  · 补丁 VENDORS：kimi 模型换 kimi-k2.7-code；新增 deepseek 评委
  · 温度：kimi=1.0（端点只允许 1，实测）、deepseek/zhipu=0.0
  · 并行：ThreadPoolExecutor（冻结脚本为串行节奏；本运行器仅并行化调度，逐次调用逻辑不变）
  · 台账：FastLedger（加锁 + 批量落盘，schema 与冻结脚本一致）

用法：
  python 三模型评分.py --pilot 6        # 抽样 6 条 × 3 评委 试跑
  python 三模型评分.py --run            # 全量 582 条 × 3 评委（缓存命中即复用）
  python 三模型评分.py --rebuild        # 零调用：从缓存重出三家评分记录
  python 三模型评分.py --status         # 零调用：看缓存现状
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = r'C:\Users\15129\Desktop\毕业设计'
BASE = os.path.join(ROOT, '交付物', '06-实验与评测')
SCORE_SCRIPT = os.path.join(BASE, '工具', '评分脚本.py')
FROZEN_OUT = os.path.join(BASE, '问答评分_正式')
OUT_DIR = os.path.join(BASE, '改进执行', '三模型金标准', '评分')
CACHE_DIR = os.path.join(OUT_DIR, '_judge原始返回')
LOG_PATH = os.path.join(OUT_DIR, '_运行日志.txt')

JUDGES = ('deepseek', 'kimi', 'zhipu')
MAX_CALLS_TOTAL = 12000
DEFAULT_WORKERS = 6


def log(msg: str) -> None:
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    try:
        with io.open(LOG_PATH, 'a', encoding='utf-8') as fh:
            fh.write(line + '\n')
    except OSError:
        pass


def load_module():
    spec = importlib.util.spec_from_file_location('score_script', SCORE_SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules['score_script'] = m
    spec.loader.exec_module(m)
    return m


def setup_module(m, dataset='formal'):
    m.apply_dataset(dataset)
    # —— 重定向输出路径（不碰冻结目录）——
    os.makedirs(OUT_DIR, exist_ok=True)
    m.OUT_DIR = OUT_DIR
    m.CACHE_DIR = CACHE_DIR
    m.RECORDS_PATH = os.path.join(OUT_DIR, '评分记录.jsonl')
    m.SUMMARY_PATH = os.path.join(OUT_DIR, '评分汇总.json')
    m.REPORT_PATH = os.path.join(OUT_DIR, '问答评分报告.md')
    m.LEDGER_PATH = os.path.join(OUT_DIR, '调用台账.json')
    m.JUDGE_CFG_PATH = os.path.join(OUT_DIR, '_judge配置.json')
    # —— 补丁评委定义 ——
    m.VENDORS['kimi']['model'] = 'kimi-k2.7-code'
    m.VENDORS['kimi']['model_source'] = '三模型金标准套餐（2026-10-10 作者指定）'
    m.VENDORS['deepseek'] = {
        'key': 'deepseek', 'label': 'DeepSeek', 'model': 'deepseek-flash',
        'base_field': 'deepseek_base_url', 'key_field': 'api_key',
        'env_key': 'DEEPSEEK_API_KEY', 'env_base': 'DEEPSEEK_BASE_URL',
        'temperature_fallback': 1.0,
        'model_source': '三模型金标准套餐（2026-10-10 作者指定）',
    }
    m.MAX_TOKENS['deepseek'] = 4000
    return m


def apply_pr_paths(m):
    """pr 档（30 题预实验集 150 条）：输出重定向到 评分_预实验/，其余与 formal 相同。"""
    global OUT_DIR, CACHE_DIR, LOG_PATH
    OUT_DIR = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', '三模型金标准', '评分_预实验')
    CACHE_DIR = os.path.join(OUT_DIR, '_judge原始返回')
    m.OUT_DIR = OUT_DIR
    m.CACHE_DIR = CACHE_DIR
    m.RECORDS_PATH = os.path.join(OUT_DIR, '评分记录.jsonl')
    m.SUMMARY_PATH = os.path.join(OUT_DIR, '评分汇总.json')
    m.REPORT_PATH = os.path.join(OUT_DIR, '问答评分报告.md')
    m.LEDGER_PATH = os.path.join(OUT_DIR, '调用台账.json')
    m.JUDGE_CFG_PATH = os.path.join(OUT_DIR, '_judge配置.json')
    os.makedirs(OUT_DIR, exist_ok=True)
    return m


def copy_reusable_zhipu_cache(m, pr=False):
    """复用既有 glm-5.3-flash 缓存（同一模型、同一 Prompt 版本、同一输入口径）。

    formal 档源＝问答评分_正式；pr 档源＝问答评分（30 题预实验，zhipu 交叉 90 格）。
    """
    frozen = (os.path.join(ROOT, '交付物', '06-实验与评测', '问答评分') if pr else FROZEN_OUT)
    src = os.path.join(frozen, '_judge原始返回', 'zhipu', m.PROMPT_VERSION)
    dst = os.path.join(CACHE_DIR, 'zhipu', m.PROMPT_VERSION)
    os.makedirs(dst, exist_ok=True)
    n = 0
    if os.path.isdir(src):
        for f in os.listdir(src):
            if f.endswith('.json'):
                dp = os.path.join(dst, f)
                if not os.path.exists(dp):
                    shutil.copy2(os.path.join(src, f), dp)
                    n += 1
    return n


def resolve_vendors(m):
    local = m.read_local_config()
    # 强制使用作者提供的密钥：实测本机环境变量里存在同名旧密钥（env≠config），
    # credential() 默认 env 优先——此处按作者指定覆盖为本项目 config.local 的取值。
    if local.get('kimi_api_key'):
        os.environ['KIMI_API_KEY'] = str(local['kimi_api_key'])
    if local.get('zhipu_api_key'):
        os.environ['ZHIPU_API_KEY'] = str(local['zhipu_api_key'])
    out = {}
    for j in JUDGES:
        v = m.resolve_vendor(m.VENDORS[j], local)
        v['temperature'] = 1.0 if j == 'kimi' else 0.0
        if not (v.get('has_key') and v.get('has_base')):
            raise RuntimeError('评委 %s 缺少密钥或端点' % j)
        out[j] = v
    return out


def make_ledger(m):
    lock = threading.Lock()

    class FastLedger(m.Ledger):
        def __init__(self, path, max_calls, flush_every=20):
            super().__init__(path, max_calls)
            self._lock = lock
            self._every = flush_every
            self._dirty = 0

        def append(self, row):
            with self._lock:
                self.seq += 1
                row = dict(row)
                row['seq'] = self.seq
                self.calls.append(row)
                self._dirty += 1
                if self._dirty >= self._every:
                    m.Ledger.flush(self)
                    self._dirty = 0

        def mark_cache_hit(self, row):
            with self._lock:
                self.cache_hits.append(dict(row))
                self._dirty += 1
                if self._dirty >= self._every:
                    m.Ledger.flush(self)
                    self._dirty = 0

        def flush(self):
            with self._lock:
                m.Ledger.flush(self)
                self._dirty = 0

    return FastLedger(m.LEDGER_PATH, MAX_CALLS_TOTAL)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--pilot', type=int, default=0, help='抽样 N 条 × 3 评委')
    ap.add_argument('--run', action='store_true')
    ap.add_argument('--rebuild', action='store_true')
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--workers', type=int, default=DEFAULT_WORKERS)
    ap.add_argument('--judge', default='', help='只跑指定评委（逗号分隔）')
    ap.add_argument('--dataset', default='formal', choices=['formal', 'pr'], help='formal=正式集582 / pr=30题预实验集150条')
    args = ap.parse_args()

    m = setup_module(load_module(), dataset=args.dataset)
    global DATASET_NAME
    DATASET_NAME = args.dataset
    if args.dataset == 'pr':
        apply_pr_paths(m)
    os.makedirs(OUT_DIR, exist_ok=True)

    items = m.load_all_answers(m.load_questions())
    log('items=%d（正式集 582 条口径）' % len(items))

    judges = [j for j in JUDGES if (not args.judge or j in args.judge.split(','))]

    if args.status:
        for j in judges:
            d = os.path.join(CACHE_DIR, j, m.PROMPT_VERSION)
            n = len([f for f in os.listdir(d)]) if os.path.isdir(d) else 0
            log('cache %s: %d files' % (j, n))
        return 0

    if args.rebuild:
        for j in judges:
            recs = m.build_records_from_cache(j, items)
            p = os.path.join(OUT_DIR, '评分记录_%s%s.jsonl' % (j, '' if DATASET_NAME == 'formal' else '_pr'))
            with io.open(p, 'w', encoding='utf-8', newline='\n') as fh:
                for r in recs:
                    fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
            log('rebuild %s -> %d records -> %s' % (j, len(recs), p))
        return 0

    if not (args.pilot or args.run):
        ap.print_help()
        return 0

    copied = copy_reusable_zhipu_cache(m, pr=(args.dataset == 'pr'))
    log('复用 glm 既有缓存：copy %d 个文件' % copied)
    vendors = resolve_vendors(m)
    for j in judges:
        v = vendors[j]
        log('judge %s: model=%s temp=%s base=%s key_src=%s' % (j, v['model'], v['temperature'], v['base_source'], v['key_source']))

    if args.pilot:
        step = max(1, len(items) // max(args.pilot, 1))
        sel = items[::step][:args.pilot]
    else:
        sel = items
    log('目标：%d 条 × %d 评委 = %d 个评分任务' % (len(sel), len(judges), len(sel) * len(judges)))

    chunks = m.load_chunks_cached()
    log('chunks loaded: %d' % len(chunks))
    ledger = make_ledger(m)

    tasks = [(j, it) for j in judges for it in sel]
    counter = {'done': 0, 'ok_dims': 0, 'fail_dims': 0}
    lock = threading.Lock()
    t0 = time.time()

    def work(task):
        j, it = task
        rec = m.score_answer(vendors[j], it, chunks, ledger, MAX_CALLS_TOTAL)
        return j, it['answer_key'], rec

    results = {}
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, t) for t in tasks]
        for fut in as_completed(futs):
            try:
                j, key, rec = fut.result()
                results[(j, key)] = rec
                with lock:
                    counter['done'] += 1
                    nf = len(rec.get('judge_failed') or [])
                    counter['fail_dims'] += nf
                    counter['ok_dims'] += (len(rec.get('scores') or {}) - nf)
                    if counter['done'] % 20 == 0 or counter['done'] == len(tasks):
                        el = time.time() - t0
                        log('进度 %d/%d | 失败维 %d | %.1f min | 调用数 %d'
                            % (counter['done'], len(tasks), counter['fail_dims'], el / 60, ledger.attempts_total()))
            except Exception as e:  # noqa: BLE001
                with lock:
                    counter['done'] += 1
                    counter['fail_dims'] += 3
                log('任务异常: %s' % str(e)[:200])

    ledger.flush()
    log('全部任务结束：%d 个 | 失败维 %d | 总调用（含重试）%d | 用时 %.1f min'
        % (counter['done'], counter['fail_dims'], ledger.attempts_total(), (time.time() - t0) / 60))

    # —— 从缓存重出三家记录 ——
    for j in judges:
        recs = m.build_records_from_cache(j, sel)
        p = os.path.join(OUT_DIR, '评分记录_%s%s.jsonl' % (j, '_pilot' if args.pilot else ''))
        with io.open(p, 'w', encoding='utf-8', newline='\n') as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + '\n')
        log('记录 %s -> %d 条 -> %s' % (j, len(recs), p))
    return 0


if __name__ == '__main__':
    sys.exit(main())
