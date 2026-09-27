# -*- coding: utf-8 -*-
"""破坏试验 ①：把《13》里一个冻结口径数字改错（只改**临时副本**，工作区不动）。

目标守卫：`工具\验收第5阶段数据.py` 的 J2「《13》声明的切分参数 == config.CHUNK」。
"""
import io
import os
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..'))
SRC = os.path.join(ROOT, '阶段05-数据准备', '13-数据准备（第五阶段）.md')


def main():
    s = io.open(SRC, encoding='utf-8').read()
    old = '| `target_chars` | 400 |'
    new = '| `target_chars` | 401 |'
    n = s.count(old)
    print('原文中该行出现次数 =', n)
    assert n == 1, n
    t = tempfile.mkdtemp(prefix='B_tamper13_')
    p = os.path.join(t, '13-数据准备（第五阶段）.md')
    io.open(p, 'w', encoding='utf-8').write(s.replace(old, new))
    print('临时《13》副本 =', p)
    print('改动：target_chars 400 → 401')


if __name__ == '__main__':
    main()
