# -*- coding: utf-8 -*-
"""破坏试验 ③：把 `图谱导出\v2.1_v1_2\edges.csv` 删掉一行（只改**临时副本**）。

目标守卫：`工具\验收第6阶段.py` 的 B11／L／M 组（导出物覆盖与自洽）——用 `--export-dir` 指向副本。
"""
import io
import os
import shutil
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..'))
SRC = os.path.join(ROOT, '阶段06-事件抽取与知识图谱', '图谱导出', 'v2.1_v1_2')


def main():
    t = tempfile.mkdtemp(prefix='B_tamper_export_')
    dst = os.path.join(t, 'v2.1_v1_2')
    shutil.copytree(SRC, dst)
    p = os.path.join(dst, 'edges.csv')
    lines = io.open(p, encoding='utf-8').read().splitlines()
    print('副本 =', dst)
    print('原 edges.csv 行数（含表头）=', len(lines))
    removed = lines[-1]
    io.open(p, 'w', encoding='utf-8', newline='').write('\n'.join(lines[:-1]) + '\n')
    print('已删除最后一行：', removed)
    print('删后行数 =', len(io.open(p, encoding='utf-8').read().splitlines()))
    print('其余 4 个文件已原样复制（nodes.csv／graph_stats.json／replay.cypher／人工确认清单.json）')


if __name__ == '__main__':
    main()
