import sys,os,re; sys.path.insert(0,r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *
SRC=r'C:\Users\15129\Desktop\毕业设计\工具\跨文档核验.py'
CPY=r'C:\Users\15129\AppData\Local\Temp\re7_B\checker_planned.py'
txt=open(SRC,encoding='utf-8').read()
assert 'PLANNED = set()' in txt
open(CPY,'w',encoding='utf-8').write(txt.replace('PLANNED = set()',"PLANNED = {'不存在文件.md'}"))
d=build('p1',{'00-项目总览与索引.md':'# 00\n\n- 07-需求分析\n- 20-甲\n',
  '07-需求分析.md':'# 07\n\n## 一、总则\n\n### 1.1 范围\n',
  '20-甲.md':'# 20\n\n见 `不存在文件.md` 与 `另一个不存在.md` 两处。\n'})
for tag,chk in [('原脚本（PLANNED 空）',SRC),('副本（登记 不存在文件.md 为计划产出）',CPY)]:
    rc,out=run(d,check=chk)
    L=[l.strip() for l in out.split('\n') if '文档提到的文件' in l or (l.strip().startswith('!! 20-甲')) or '计划产出登记' in l]
    print('== %s == exit=%d'%(tag,rc))
    for l in L: print('    ',l)
    print()
