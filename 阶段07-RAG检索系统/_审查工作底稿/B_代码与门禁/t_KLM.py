import sys,os; sys.path.insert(0,r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *
IDX='# 00\n\n- 07-需求分析\n- 20-甲\n'
DOC07='# 07-需求分析\n\n## 一、总则\n\n### 1.1 范围\n'
def mkW(txt,name='20-甲.md',idx=IDX):
    return build('k_'+str(abs(hash(txt+name+idx))%99999),
      {'00-项目总览与索引.md':idx,'07-需求分析.md':DOC07,name:'# 20\n\n'+txt+'\n'})
cases=[
 ('K-a 反引号 .md 不存在（对照）','见 `不存在文件.md` 一节'),
 ('K-b 反引号 .json 不存在','见 `不存在文件.json` 一节'),
 ('K-c 反引号 .jsonl 不存在','见 `不存在文件.jsonl` 一节'),
 ('K-d 反引号 .txt 不存在','见 `不存在文件.txt` 一节'),
 ('K-e 反引号 .cypher 不存在','见 `不存在文件.cypher` 一节'),
 ('K-f 反引号 .csv 不存在（对照）','见 `不存在文件.csv` 一节'),
 ('K-g 不加反引号的不存在文件','见 不存在文件.md 一节'),
]
for tag,txt in cases:
    d=mkW(txt); rc,out=run(d)
    L=[l.strip() for l in out.split('\n') if '文档提到的文件' in l or l.strip().startswith('!! 20-甲')]
    print('%-34s exit=%d  %s'%(tag,rc,' | '.join(L)))
print()
# L：只查子串
d=mkW('内容无关','20-甲.md','# 00\n\n- 07-需求分析\n\n（本节为废弃清单，曾用编号 20-甲，已作废）\n')
rc,out=run(d)
print('L 只查子串（20-甲 出现在"废弃清单"句中） exit=%d  %s'%(rc,[l.strip() for l in out.split('\n') if '带号文档均已登记' in l]))
d=mkW('内容无关','20-甲.md','# 00\n\n- 07-需求分析\n')
rc,out=run(d)
print('L 对照（完全不提 20-甲）             exit=%d  %s'%(rc,[l.strip() for l in out.split('\n') if '带号文档均已登记' in l]))
print()
# M：没有 06/07 阶段目录
d=mkW('内容无关')
rc,out=run(d)
ms=[l.strip() for l in out.split('\n') if '阶段目录存在' in l]
print('M 在完全无阶段目录的合成工作区：')
for l in ms: print('   ',l)
