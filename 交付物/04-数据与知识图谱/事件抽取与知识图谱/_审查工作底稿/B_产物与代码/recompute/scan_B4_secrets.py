# -*- coding: utf-8 -*-
"""B4：全仓库（可提交文件集）密钥扫描 + .gitignore 覆盖核查 + git add -f 痕迹抽查。

只读。所有 git 调用带 -c core.quotepath=false。
"""
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..', '..', '..'))


def git(*args, binary=False):
    cmd = ['git', '-c', 'core.quotepath=false'] + list(args)
    p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if binary:
        return p.returncode, p.stdout, p.stderr
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


PATTERNS = [
    ('sk-', re.compile(r'sk-')),
    ('bce-v3/', re.compile(r'bce-v3/')),
    ('id.secret(32+hex.32+hex)', re.compile(r'\b[0-9a-fA-F]{32}\.[0-9a-fA-F]{32}\b')),
    ('id.secret(32+hex:32+hex)', re.compile(r'\b[0-9a-fA-F]{32}:[0-9a-fA-F]{32}\b')),
    ('bearer_token', re.compile(r'(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}')),
    ('api_key_literal', re.compile(r'(?i)api[_-]?key\s*[:=]\s*["\'][^"\']{16,}["\']')),
]


def main():
    rc, out, err = git('ls-files', '-co', '--exclude-standard')
    assert rc == 0, err
    files = [l for l in out.splitlines() if l.strip()]
    print('#### B4-01 扫描目标集合')
    print('$ git ls-files -co --exclude-standard  →  %d 个文件' % len(files))
    print('（含已跟踪文件与未忽略的新文件；被 .gitignore 排除的文件不在其中）')

    print()
    print('#### B4-02 密钥模式扫描（逐文件、按 utf-8 容错读）')
    hits = []
    unreadable = []
    nbytes = 0
    for f in files:
        p = os.path.join(ROOT, f.replace('/', os.sep))
        if not os.path.exists(p):
            print('  [缺失] %s' % f)
            continue
        try:
            raw = open(p, 'rb').read()
        except Exception as e:
            unreadable.append((f, repr(e)))
            continue
        nbytes += len(raw)
        txt = raw.decode('utf-8', 'replace')
        for name, rx in PATTERNS:
            for m in rx.finditer(txt):
                s = max(0, m.start() - 60)
                hits.append((f, name, m.group(0)[:80], txt[s:m.end() + 60].replace('\n', '\\n')))
    print('已扫描文件 %d 个／%d 字节；不可读 %d 个' % (len(files) - len(unreadable), nbytes, len(unreadable)))
    for f, e in unreadable:
        print('  不可读：%s %s' % (f, e))
    print('命中总数 = %d' % len(hits))
    for f, name, frag, ctx in hits:
        print('  HIT [%s] %s :: %s' % (name, f, ctx))
        print('      匹配片段=%s' % frag)

    print()
    print('#### B4-03 逐模式命中计数')
    for name, rx in PATTERNS:
        n = sum(1 for f, n2, _, _ in hits if n2 == name)
        print('  %-28s %d' % (name, n))

    print()
    print('#### B4-04 历史检索 git log --all -S/-G')
    for frag in ('sk-', 'bce-v3/', 'DEEPSEEK_API_KEY', 'LLM_API_KEY'):
        rc, out, err = git('log', '--all', '--oneline', '-S' + frag)
        lines = [l for l in out.splitlines() if l.strip()]
        print('  -S%-16s 命中提交 %d 个：%s' % (frag, len(lines), '；'.join(lines[:5]) or '无'))
    for pat in (r'[0-9a-fA-F]{32}\.[0-9a-fA-F]{32}', r'bce-v3/'):
        rc, out, err = git('log', '--all', '--oneline', '-G' + pat)
        lines = [l for l in out.splitlines() if l.strip()]
        print('  -G%-32s 命中提交 %d 个：%s' % (pat, len(lines), '；'.join(lines[:5]) or '无'))
    for f in ('.env', '交付物/03-代码/抽取与图谱/config.local.json'):
        rc, out, err = git('log', '--all', '--oneline', '--', f)
        print('  历史中是否出现 %-34s → %s' % (f, out.strip() or '无'))

    print()
    print('#### B4-05 .gitignore 覆盖核查（《00》第八节规则 7 的三类＋密钥／本地配置）')
    rc, out, err = git('check-ignore', '-v',
                       '交付物/08-文献与开题/文献调研与开题/文献PDF/FIN-16_Saxena2021_CronKGQA.pdf',
                       '交付物/08-文献与开题/文献调研与开题/文献翻译/RAG-1_Lewis2020_RAG_译文.docx',
                       '交付物/04-数据与知识图谱/数据准备/数据集/v2.1/clean/documents.jsonl',
                       '.idea/workspace.xml',
                       '交付物/03-代码/抽取与图谱/config.local.json',
                       '.env')
    for line in out.splitlines():
        print('  %s' % line)
    print('  退出码 =', rc)
    # 反查：这些路径是否被跟踪
    for f in ('交付物/08-文献与开题/文献调研与开题/文献PDF/FIN-16_Saxena2021_CronKGQA.pdf',
              '交付物/04-数据与知识图谱/数据准备/数据集/v2.1/clean/documents.jsonl',
              '.idea/workspace.xml',
              '交付物/03-代码/抽取与图谱/config.local.json'):
        rc2, out2, _ = git('ls-files', '--error-unmatch', f)
        print('  %-58s 已入库=%s' % (f, rc2 == 0))

    print()
    print('#### B4-06 是否有 .gitignore 未覆盖但明显该忽略的落点')
    cands = [
        '交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/v2.1_v1_2/nodes.csv',
        '交付物/04-数据与知识图谱/事件抽取与知识图谱/_试跑_图谱管线/运行日志_首跑.txt',
        '交付物/03-代码/抽取与图谱/_试跑/v1_2/定向对照报告.md',
        '交付物/03-代码/抽取与图谱/_全量/v2.1_v1_2/对照报告.md',
        '交付物/04-数据与知识图谱/数据准备/数据集/抽取评测集/v2.1/自动标注/自动标注报告.md',
        '交付物/04-数据与知识图谱/事件抽取与知识图谱/_审查工作底稿/A_文档与口径/raw_跨文档核验.txt',
        '工具/__pycache__/执行助手.cpython-312.pyc',
        '交付物/03-代码/抽取与图谱/__pycache__/config.cpython-312.pyc',
    ]
    for c in cands:
        rc, out, err = git('check-ignore', '-v', c)
        print('  %-70s 忽略=%s %s' % (c, rc == 0, out.strip() or ''))

    print()
    print('#### B4-07 历史提交中的新增文件（git log --diff-filter=A --stat 抽查）')
    rc, out, err = git('log', '--all', '--diff-filter=A', '--name-only', '--format=@@%h %s')
    lines = out.splitlines()
    cur = None
    cnt = 0
    addcount = {}
    for l in lines:
        if l.startswith('@@'):
            cur = l[2:]
        elif l.strip():
            cnt += 1
            addcount[cur] = addcount.get(cur, 0) + 1
    print('  历史新增文件条目总数 = %d（按提交）' % cnt)
    for k, v in list(addcount.items()):
        print('   %-70s 新增 %d' % (k[:70], v))
    # 是否出现过被忽略的文件被强行入库：检查历史里是否出现过数据集/文献PDF/.idea 下的路径
    suspicious = [l for l in lines if l.strip() and not l.startswith('@@') and (
        l.startswith('交付物/04-数据与知识图谱/数据准备/数据集/') or l.startswith('交付物/08-文献与开题/文献调研与开题/文献PDF/')
        or l.startswith('交付物/08-文献与开题/文献调研与开题/文献翻译/') or l.startswith('.idea/')
        or l.endswith('.local.json') or l == '.env')]
    print('  历史中曾入库、且属《00》规则 7 应排除范围的路径数 = %d' % len(suspicious))
    for s in suspicious[:40]:
        print('    !! %s' % s)

    print()
    print('#### B4-08 当前入库文件总览（按顶层目录）')
    from collections import Counter
    rc, out, err = git('ls-files')
    c = Counter(l.split('/')[0] for l in out.splitlines() if l.strip())
    for k, v in sorted(c.items()):
        print('  %-40s %d' % (k, v))


if __name__ == '__main__':
    main()
