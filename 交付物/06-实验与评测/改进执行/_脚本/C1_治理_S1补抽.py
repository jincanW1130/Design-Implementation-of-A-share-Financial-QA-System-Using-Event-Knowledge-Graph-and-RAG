# -*- coding: utf-8 -*-
"""C-1 空值治理 · S1 补抽裁定（模型调用：deepseek-flash，56 条 L1+L2 空值事件）

对文本含日期候选（L1 绝对日期 13 条 / L2 部分日期 43 条）的空值事件，
把事件名＋描述＋源文档全文交给模型，裁定"该事件的发生时间"：
  输出 JSON：{"event_time": "YYYY-MM-DD" 或 null, "granularity": "day|month|none",
              "evidence_quote": "...", "reason": "..."}
纪律：文本不足以确定到日**必须**给 null（延续"不猜测"纪律）；裁定结果标注
time_source=explicit_adjudicated（模型口径），入库前须人工复核。

产出（只写 改进执行/C1_事件时间空值治理/）：
  补全数据_S1.jsonl · S1_裁定台账.json · 治理读数_S1.json
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = r'C:\Users\15129\Desktop\毕业设计'
GRAPH = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '事件抽取与知识图谱', '图谱导出', 'v2.1_v1_3')
CHUNKS = os.path.join(ROOT, '交付物', '04-数据与知识图谱', '数据准备', '数据集', 'v2.1', 'chunks', 'chunks.jsonl')
LAYERS = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', 'C1_事件时间空值分层')
OUT = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', 'C1_事件时间空值治理')
CFG = os.path.join(ROOT, '交付物', '03-代码', '抽取与图谱', 'config.local.json')

MODEL = 'deepseek-flash'
TEMP = 0
MAX_TOKENS = 2048
WORKERS = 4
SEED_NOTE = 'C-1 S1 补抽裁定（2026-10-11）'


def log(m):
    print('[%s] %s' % (dt.datetime.now().strftime('%H:%M:%S'), m), flush=True)


SYSTEM = (
    "你是 A 股财经公告的**时间裁定员**。给你一个事件（名称＋描述）与其来源文档全文。"
    "请裁定该事件的**发生时间**。\n"
    "纪律：\n"
    "1. 只输出一个 JSON 对象：{\"event_time\": \"YYYY-MM-DD\" 或 \"YYYY-MM\" 或 null, "
    "\"evidence_quote\": \"原文逐字引用（12~120 字）\", \"reason\": \"一句话依据\"}。\n"
    "2. 能确定到日才给 YYYY-MM-DD；只能确定到月给 YYYY-MM 并在 reason 注明；"
    "文本不足以裁定（多个候选日无法区分、日期属于其他事件）时 event_time 给 null 并说明。\n"
    "3. 绝不猜测、不得用文档发布时间顶替事件时间、不得输出 JSON 之外的任何内容。"
)

USER_TMPL = """【事件名称】{name}
【事件描述】{desc}
【当前状态】该事件时间在抽取时为空（文本含日期候选但未能裁定），请重新裁定。

【来源文档全文（仅为上下文；事件时间应能在其中找到依据）】
{doc_text}

请按纪律输出 JSON。"""


def extract_json(text):
    raw = (text or '').strip()
    raw = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)
    try:
        return json.loads(raw)
    except ValueError:
        s, e = raw.find('{'), raw.rfind('}')
        if s >= 0 and e > s:
            try:
                return json.loads(raw[s:e + 1])
            except ValueError:
                return None
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    cfg = json.load(io.open(CFG, encoding='utf-8'))

    # 源文本：doc_id → 全文（按 chunk_index 拼接 content）
    doc_text = {}
    per_doc = {}
    with io.open(CHUNKS, encoding='utf-8') as fh:
        for line in fh:
            if line.strip():
                r = json.loads(line)
                per_doc.setdefault(str(r['doc_id']), []).append(r)
    for did, rs in per_doc.items():
        rs.sort(key=lambda r: int(r.get('chunk_index') or 0))
        doc_text[did] = '\n'.join(r.get('content') or '' for r in rs)

    nodes = {r['node_id']: r for r in csv.DictReader(io.open(os.path.join(GRAPH, 'nodes.csv'), encoding='utf-8'))}
    ev_docs = {}
    for r in csv.DictReader(io.open(os.path.join(GRAPH, 'edges.csv'), encoding='utf-8')):
        if r['relation'] == 'EVIDENCED_BY':
            ev_docs.setdefault(r['head_id'], []).append(r['tail_id'])

    detail = [json.loads(l) for l in io.open(os.path.join(LAYERS, '空值事件分层明细.jsonl'), encoding='utf-8') if l.strip()]
    todo = [d for d in detail if d['layer'] in ('L1_绝对日期', 'L2_部分日期')]
    log('S1 待裁定: %d 条' % len(todo))

    out_path = os.path.join(OUT, '补全数据_S1.jsonl')
    done = {}
    if os.path.isfile(out_path):
        for l in io.open(out_path, encoding='utf-8'):
            if l.strip():
                r = json.loads(l)
                done[r['event_id']] = r
    log('已有缓存: %d 条（断点续跑）' % len(done))

    from openai import OpenAI
    client = OpenAI(api_key=cfg['api_key'],
                    base_url=cfg.get('deepseek_base_url') or 'https://api.deepseek.com/v1',
                    timeout=240, max_retries=2)
    lock = threading.Lock()
    ledger = []

    def work(d):
        eid = d['event_id']
        if eid in done:
            return eid, done[eid], True
        node = nodes.get(eid, {})
        docs = ev_docs.get(eid, [])
        text = '\n'.join(doc_text.get(x, '') for x in docs)[:12000]
        if not text:
            return eid, {'event_id': eid, 'error': 'no doc text'}, False
        user = USER_TMPL.format(name=node.get('event_name') or node.get('name') or '',
                                desc=(node.get('description') or '')[:600], doc_text=text)
        attempts = []
        ok = False
        parsed = None
        for attempt in range(1, 4):
            t0 = time.time()
            row = {'event_id': eid, 'attempt': attempt, 'ts': dt.datetime.now().isoformat(timespec='seconds'),
                   'latency_s': None, 'ok': False, 'error': None, 'usage': {}}
            try:
                resp = client.chat.completions.create(
                    model=MODEL, temperature=TEMP, max_tokens=MAX_TOKENS,
                    response_format={'type': 'json_object'},
                    messages=[{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}])
                row['latency_s'] = round(time.time() - t0, 2)
                u = getattr(resp, 'usage', None)
                row['usage'] = {'prompt': getattr(u, 'prompt_tokens', 0) or 0,
                                'completion': getattr(u, 'completion_tokens', 0) or 0}
                fr = resp.choices[0].finish_reason
                parsed = extract_json(resp.choices[0].message.content)
                row['finish_reason'] = fr
                row['ok'] = bool(parsed) and fr == 'stop'
                if parsed and fr != 'stop':
                    row['error'] = 'truncated'
                ok = row['ok']
            except Exception as exc:  # noqa: BLE001
                row['latency_s'] = round(time.time() - t0, 2)
                row['error'] = str(exc)[:200]
            attempts.append(row)
            if ok:
                break
            time.sleep(2 * attempt)
        rec = {'event_id': eid, 'layer': d['layer'], 'model': MODEL, 'temperature': TEMP,
               'attempts': attempts, 'parsed': parsed,
               'time_source': 'explicit_adjudicated' if ok and (parsed or {}).get('event_time') else None,
               'ok': ok}
        with lock:
            ledger.extend(attempts)
        return eid, rec, ok

    results = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(work, d) for d in todo]
        n = 0
        for fut in as_completed(futs):
            eid, rec, ok = fut.result()
            results[eid] = rec
            n += 1
            if n % 10 == 0 or n == len(todo):
                log('进度 %d/%d' % (n, len(todo)))

    # 落盘
    ok_n = sum(1 for r in results.values() if r.get('ok') and (r.get('parsed') or {}).get('event_time'))
    with io.open(out_path, 'w', encoding='utf-8', newline='\n') as fh:
        for eid in sorted(results):
            r = results[eid]
            parsed = r.get('parsed') or {}
            fh.write(json.dumps({'event_id': eid, 'layer': r.get('layer'),
                                 'proposed_event_time': parsed.get('event_time'),
                                 'granularity_note': (parsed.get('reason') or '')[:120],
                                 'evidence_quote': (parsed.get('evidence_quote') or '')[:160],
                                 'time_source': r.get('time_source'),
                                 'ok': r.get('ok')}, ensure_ascii=False, sort_keys=True) + '\n')
    io.open(os.path.join(OUT, 'S1_裁定台账.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps({'ledger': ledger, 'note': SEED_NOTE}, ensure_ascii=False, indent=1))

    # 治理读数
    n_null_time = 544
    granted = sum(1 for r in results.values()
                  if (r.get('parsed') or {}).get('event_time'))
    read = {'S1_待裁定': len(todo), 'S1_成功裁定': granted, 'S1_裁定失败或 null': len(todo) - granted,
            '治理后事件时间空值（严格显式口径）': n_null_time - granted,
            '对应空值率': '%.1f%%' % (100.0 * (n_null_time - granted) / 1098),
            '说明': 'S2 规则换算实测仅 1 条可机械映射（近日/年内等不可确定到日，按不猜测纪律不硬填）；'
                    'S3 文档信号 544/544 全覆盖（不改 event_time 本体，作 D 组可过滤时间）。'
                    '裁定结果为模型口径（explicit_adjudicated），入库前须人工逐条复核。'}
    io.open(os.path.join(OUT, '治理读数_S1.json'), 'w', encoding='utf-8', newline='\n').write(
        json.dumps(read, ensure_ascii=False, indent=1))
    log('S1 完成: 成功裁定 %d/%d → 治理后空值 %d/1098（%s）' % (
        granted, len(todo), n_null_time - granted, read['对应空值率']))
    return 0


if __name__ == '__main__':
    sys.exit(main())