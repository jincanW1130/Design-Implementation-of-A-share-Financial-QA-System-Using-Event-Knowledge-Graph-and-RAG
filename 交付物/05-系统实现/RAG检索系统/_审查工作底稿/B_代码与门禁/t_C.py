import sys; sys.path.insert(0,r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *
IDX='# 00\n\n- 07-需求分析\n- 20-甲\n- 21-乙\n- 22-丙\n'
DOC07='# 07-需求分析\n\n## 一、总则\n\n### 1.1 范围\n\n### 3.1 需求\n\n### 3.2 另一条\n'
# T1：引用根本不存在的文档号 《99》
d=build('c1',{'00-项目总览与索引.md':IDX,'07-需求分析.md':DOC07,
  '20-甲.md':'# 20\n\n本项目依据《99》第1.1节 的规定。\n'})
rc,out=run(d); print('T1《99》第1.1节（文档号不存在）  exit=%d'%rc); show('C 段',out,['所有《0N》第x.y节','!!'])
# T2：引用存在文档号、但不存在的节号（对照）
d=build('c2',{'00-项目总览与索引.md':IDX,'07-需求分析.md':DOC07,
  '21-乙.md':'# 21\n\n本项目依据《07》第9.9节 的规定。\n'})
rc,out=run(d); print('\nT2《07》第9.9节（节号不存在，对照）  exit=%d'%rc); show('C 段',out,['所有《0N》第x.y节','!!'])
# T3：链式引用，只校验首节号
d=build('c3',{'00-项目总览与索引.md':IDX,'07-需求分析.md':DOC07,
  '22-丙.md':'# 22\n\n本项目依据《07》第3.1节、第9.9节 的规定。\n'})
rc,out=run(d); print('\nT3《07》第3.1节、第9.9节（链式，后者不存在）  exit=%d'%rc); show('C 段',out,['所有《0N》第x.y节','!!'])
