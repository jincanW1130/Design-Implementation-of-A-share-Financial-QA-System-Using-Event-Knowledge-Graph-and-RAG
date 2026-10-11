# -*- coding: utf-8 -*-
"""三模型标注 · 单模型包装器（复用冻结 auto_annotate.py 的全部机制）

用途：对 260 条抽取评测块（dev 60 + test 200），用 kimi-k2.7-code / glm-5.3-flash
（deepseek-flash 成员复用既有主参照集，不重跑）独立标注，供"三模型综合=金标准"合成。

复用：auto_annotate.py 的 SYSTEM_PROMPT／schema 渲染／校验／定向修复／台账／缓存；
仅覆盖三处（全部通过其既有 CLI／模块级参数实现）：
  · 模型与 Prompt 版本：--model / --prompt-version（换模型必须换版本号，遵循其纪律）
  · 端点与密钥：环境变量 LLM_API_KEY / LLM_BASE_URL（config.api_key()/base_url() 优先读 env）
  · temperature：kimi 端点拒收 0（实测 only 1 is allowed）→ 模块级补丁 TEMPERATURE=1 并如实登记

输出（只写新目录，不碰任何冻结件）：
  改进执行/三模型金标准/标注_<vendor>/{dev,test}.auto.jsonl · 台账 · 报告 · _缓存

用法：
  python 三模型标注_单模型.py --vendor kimi [--split dev] [--limit 2] [--workers 4] [--force]
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys

ROOT = r'C:\Users\15129\Desktop\毕业设计'
EXTRACT_DIR = os.path.join(ROOT, '交付物', '03-代码', '抽取与图谱')
CFG_PATH = os.path.join(EXTRACT_DIR, 'config.local.json')
OUT_BASE = os.path.join(ROOT, '交付物', '06-实验与评测', '改进执行', '三模型金标准')

VENDORS = {
    'kimi': {
        'model': 'kimi-k2.7-code',
        'prompt_version': 'stage6-auto-annotate-v1.0-kimi',
        'env_key_field': 'kimi_api_key',
        'env_base_field': 'kimi_base_url',
        'temperature': 1,   # 端点只允许 1（实测：temp=0 → 400 invalid temperature）
    },
    'glm': {
        'model': 'glm-5.3-flash',
        'prompt_version': 'stage6-auto-annotate-v1.0-glm',
        'env_key_field': 'zhipu_api_key',
        'env_base_field': 'zhipu_base_url',
        'temperature': 0,   # 端点接受 0（实测）
    },
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--vendor', required=True, choices=sorted(VENDORS))
    ap.add_argument('--split', default='all', choices=['all', 'dev', 'test'])
    ap.add_argument('--limit', type=int, default=0, help='0 = 全部（试跑用 N）')
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--timeout', type=float, default=600.0,
                    help='单次请求超时秒（默认 600；冻结配置为 180，实测 glm 大标注调用会超过 180 被误杀）')
    ap.add_argument('--max-tokens', type=int, default=0,
                    help='覆盖 max_tokens（0=不改，用冻结值 16384；实测 glm 推理会吃满 16384 致正文为空，需更大）')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    v = VENDORS[args.vendor]
    cfg = json.load(io.open(CFG_PATH, encoding='utf-8'))
    key = str(cfg.get(v['env_key_field']) or '').strip()
    base = str(cfg.get(v['env_base_field']) or '').strip()
    if not key or not base:
        print('缺少密钥或端点字段:', v['env_key_field'], v['env_base_field'])
        return 2

    # 端点路由：走 auto_annotate 的 env 优先机制
    os.environ['LLM_API_KEY'] = key
    os.environ['LLM_BASE_URL'] = base
    os.environ.pop('STAGE6_FORBID_MODEL_CALLS', None)   # 允许真实调用

    if EXTRACT_DIR not in sys.path:
        sys.path.insert(0, EXTRACT_DIR)
    import config as extract_config  # noqa: E402  — 与 auto_annotate 同一模块实例
    extract_config.LLM['timeout_seconds'] = float(args.timeout)   # 实测 glm 大调用 >180s，按需放宽

    # ⚠️ auto_annotate 的客户端超时走 `handann._load_config()`（**每次另行 importlib 载入
    # 独立 config 实例**，见 工具/标注结构校验.py:90），上面对 extract_config 的补丁盖不到它。
    # 故在 openai 客户端层兜底：凡是 timeout=180 的构建，一律替换为本批指定值。
    import openai as _oai
    _orig_openai_cls = _oai.OpenAI
    _timeout_target = float(args.timeout)

    class _PatchedOpenAI(_orig_openai_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *a, **kw):
            t = kw.get('timeout')
            if isinstance(t, (int, float)) and abs(float(t) - 180.0) < 1e-6:
                kw['timeout'] = _timeout_target
            super().__init__(*a, **kw)

    _oai.OpenAI = _PatchedOpenAI

    spec = importlib.util.spec_from_file_location('auto_annotate', os.path.join(EXTRACT_DIR, 'auto_annotate.py'))
    aa = importlib.util.module_from_spec(spec)
    sys.modules['auto_annotate'] = aa
    spec.loader.exec_module(aa)

    # 模块级补丁：温度与默认模型名（CLI 会再覆盖 model/version）
    aa.TEMPERATURE = v['temperature']
    aa.ANNOTATE_MODEL = v['model']
    aa.PROMPT_VERSION = v['prompt_version']
    if args.max_tokens:
        aa.MAX_TOKENS = int(args.max_tokens)

    # 补丁 write_auto_jsonl：现行 dev/test.jsonl 已按作者决定删除 annotation 占位字段
    # （冻结脚本的"字节手术"依赖 `, "annotation": ` 标记，直接跑会 ValueError），
    # 此处兼容"无标记"情形：在行尾 } 前追加 annotation 字段。
    def _patched_write_auto_jsonl(rows, out_path):
        marker = ', "annotation": '
        lines = []
        for rec, orig_line, annotation in rows:
            line = orig_line.rstrip('\n')
            ann_json = json.dumps(annotation, ensure_ascii=False)
            if marker in line:
                pos = line.rindex(marker)
                head = line[:pos + len(marker)]
                tail = line[pos + len(marker):]
                if not tail.endswith('}'):
                    raise RuntimeError('原始行不以 annotation 结尾，手术式重写不适用')
                lines.append(head + ann_json + '}\n')
            else:
                if not line.endswith('}'):
                    raise RuntimeError('原始行不以 } 结尾，无法追加 annotation')
                lines.append(line[:-1] + marker + ann_json + '}\n')
        text = ''.join(lines)
        aa.write_text_atomic(out_path, text)
        return text

    aa.write_auto_jsonl = _patched_write_auto_jsonl

    out_dir = os.path.join(OUT_BASE, '标注_%s' % args.vendor)
    cache_dir = os.path.join(out_dir, '_缓存')
    os.makedirs(out_dir, exist_ok=True)

    argv = ['run',
            '--model', v['model'],
            '--prompt-version', v['prompt_version'],
            '--out-dir', out_dir,
            '--cache-dir', cache_dir,
            '--workers', str(args.workers),
            '--split', args.split]
    if args.limit:
        argv += ['--limit', str(args.limit)]
    if args.force:
        argv += ['--force']

    print('[wrapper] vendor=%s model=%s temp=%s prompt=%s' % (args.vendor, v['model'], v['temperature'], v['prompt_version']))
    print('[wrapper] out=%s' % out_dir)
    return aa.main(argv)


if __name__ == '__main__':
    sys.exit(main())
