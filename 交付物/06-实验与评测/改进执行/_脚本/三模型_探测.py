# -*- coding: utf-8 -*-
"""三模型端点探测：deepseek-flash / kimi-k2.7-code / glm-5.3-flash。
只读 config.local.json 取密钥；输出不含任何凭据。"""
import io, json, os, sys, time
from openai import OpenAI

ROOT = r'C:/Users/15129/Desktop/毕业设计'
CFG = os.path.join(ROOT, '交付物/03-代码/抽取与图谱/config.local.json')
OUT = os.path.join(ROOT, '交付物/06-实验与评测/改进执行/三模型金标准/probe记录.json')

cfg = json.load(io.open(CFG, encoding='utf-8'))
TARGETS = [
    ('deepseek', 'deepseek-flash', cfg.get('api_key'), cfg.get('deepseek_base_url') or 'https://api.deepseek.com/v1'),
    ('kimi', 'kimi-k2.7-code', cfg.get('kimi_api_key'), cfg.get('kimi_base_url')),
    ('zhipu', 'glm-5.3-flash', cfg.get('zhipu_api_key'), cfg.get('zhipu_base_url')),
]

results = []
for name, model, key, base in TARGETS:
    rec = {'vendor': name, 'model_requested': model, 'base_host': (base or '').split('/')[2] if base else None,
           'has_key': bool(key), 'ok': False, 'model_resolved': None,
           'temperature_tried': None, 'error': None, 'latency_s': None, 'raw_excerpt': None}
    if not key or not base:
        rec['error'] = 'missing key or base'
        results.append(rec); print(rec); continue
    client = OpenAI(api_key=key, base_url=base, timeout=60)
    for temp in (0.0, 1.0):
        t0 = time.time()
        try:
            r = client.chat.completions.create(
                model=model, temperature=temp, max_tokens=8,
                messages=[{'role': 'user', 'content': '回复数字 1'}])
            rec.update({'ok': True, 'model_resolved': getattr(r, 'model', None),
                        'temperature_tried': temp, 'latency_s': round(time.time() - t0, 2),
                        'raw_excerpt': (r.choices[0].message.content or '')[:30],
                        'usage': {'p': getattr(r.usage, 'prompt_tokens', None) if r.usage else None}})
            break
        except Exception as e:
            rec.update({'temperature_tried': temp, 'latency_s': round(time.time() - t0, 2),
                        'error': 'temp=%s: %s' % (temp, str(e)[:200])})
    results.append(rec)
    print(json.dumps(rec, ensure_ascii=False))

os.makedirs(os.path.dirname(OUT), exist_ok=True)
io.open(OUT, 'w', encoding='utf-8', newline='\n').write(json.dumps(
    {'generated_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'results': results},
    ensure_ascii=False, indent=1))
print('probe written:', OUT)
