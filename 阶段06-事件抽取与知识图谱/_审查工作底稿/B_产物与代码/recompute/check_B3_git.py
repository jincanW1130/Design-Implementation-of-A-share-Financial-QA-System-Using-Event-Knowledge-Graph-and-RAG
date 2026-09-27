# -*- coding: utf-8 -*-
"""B3：v1.1 三处落点与提交版（HEAD）逐字节比对 + 入库/忽略状态。

只读。所有 git 调用带 -c core.quotepath=false，逐条用 python 子进程执行。
"""
import hashlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))


def git(*args, binary=False):
    cmd = ['git', '-c', 'core.quotepath=false'] + list(args)
    p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if binary:
        return p.returncode, p.stdout, p.stderr
    return p.returncode, p.stdout.decode('utf-8', 'replace'), p.stderr.decode('utf-8', 'replace')


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(p):
    h = hashlib.sha256()
    with io.open(p, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def tracked_files():
    rc, out, err = git('ls-files')
    assert rc == 0, err
    return [l for l in out.splitlines() if l.strip()]


def main():
    print('#### B3-01 HEAD 与工作区状态')
    for args in (('rev-parse', '--short', 'HEAD'), ('log', '-1', '--format=%H %ci %s'),
                 ('status', '--short')):
        rc, out, err = git(*args)
        print('$ git %s  (rc=%d)' % (' '.join(args), rc))
        print(out.rstrip() or '(空)')

    files = tracked_files()
    print('HEAD 跟踪文件数 =', len(files))

    print()
    print('#### B3-02 v1.1 三处落点在 git 里的状态')
    for prefix in ('代码/抽取与图谱/_全量/v2.1/',
                   '阶段05-数据准备/数据集/_抽取缓存/v2.1/',
                   '阶段06-事件抽取与知识图谱/图谱导出/v2.1/'):
        hit = [f for f in files if f.startswith(prefix)]
        print('%-46s 入库文件数=%d' % (prefix, len(hit)))
        for f in hit:
            rc, out, err = git('check-ignore', '-v', f)
            print('     %s   check-ignore rc=%d %s' % (f, rc, out.strip() or '(无输出=未忽略)'))
    for prefix in ('阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/',
                   '代码/抽取与图谱/_全量/v2.1_v1_2/'):
        hit = [f for f in files if f.startswith(prefix)]
        print('%-46s 入库文件数=%d' % (prefix, len(hit)))

    print()
    print('#### B3-03 逐字节比对：工作区 vs git show HEAD:<path>')
    targets = [f for f in files if f.startswith('阶段06-事件抽取与知识图谱/图谱导出/v2.1/')]
    targets += [f for f in files if f.startswith('阶段06-事件抽取与知识图谱/图谱导出/v2.1_v1_2/')]
    all_ok = True
    for f in sorted(targets):
        wp = os.path.join(ROOT, f.replace('/', os.sep))
        if not os.path.exists(wp):
            print('MISSING  %s' % f)
            all_ok = False
            continue
        rc, blob, err = git('show', 'HEAD:' + f, binary=True)
        if rc != 0:
            print('GIT-ERR  %s  %s' % (f, err.decode('utf-8', 'replace')[:120]))
            all_ok = False
            continue
        a, b = sha256_file(wp), sha256_bytes(blob)
        size_a, size_b = os.path.getsize(wp), len(blob)
        same = (a == b) and (size_a == size_b)
        all_ok &= same
        print('%s  %-72s 工作区 %s (%d B) vs HEAD %s (%d B)' %
              ('OK     ' if same else 'DIFF   ', f, a[:16], size_a, b[:16], size_b))
    print('结论：图谱导出两代目录 %s' % ('全部与 HEAD 逐字节一致' if all_ok else '存在差异'))

    print()
    print('#### B3-04 v1.1 未入库落点的键文件 sha256（无提交版可比，仅留档）')
    for f in ('代码/抽取与图谱/_全量/v2.1/extracted.jsonl',
              '代码/抽取与图谱/_全量/v2.1/verify.json',
              '代码/抽取与图谱/_全量/v2.1/run_history.jsonl',
              '代码/抽取与图谱/_全量/v2.1/event_time_backfill.json',
              '代码/抽取与图谱/_全量/v2.1/对照报告.md',
              '代码/抽取与图谱/_全量/v2.1/对照指标.json'):
        wp = os.path.join(ROOT, f.replace('/', os.sep))
        ex = os.path.exists(wp)
        rc, out, err = git('check-ignore', '-v', f)
        print('%-70s exists=%s ignore=%s' % (f, ex, out.strip() or '(未忽略)'))
        if ex:
            print('      sha256=%s  bytes=%d' % (sha256_file(wp), os.path.getsize(wp)))


if __name__ == '__main__':
    main()
