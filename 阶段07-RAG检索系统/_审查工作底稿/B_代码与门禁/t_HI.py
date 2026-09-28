import sys,os,re; sys.path.insert(0,r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *
IDX='# 00\n\n- 07-需求分析\n- 20-甲\n'
DOC07='# 07\n\n## 一、总则\n\n### 1.1 范围\n'
def mkh(txt,name='20-甲.md'):
    return build('h_'+str(abs(hash(txt))%99999),
      {'00-项目总览与索引.md':IDX,'07-需求分析.md':DOC07,name:'# 20\n\n'+txt+'\n'})
cases=[
 ('H-a 裸 Evidence Recall（对照）','本系统采用 Evidence Recall 作为指标。'),
 ('H-b 裸 Evidence Recall + 行内含"已于"','本系统已于 2026-09-27 定稿，采用 Evidence Recall 作为指标。'),
 ('H-c 裸 Evidence Recall + 行内含"原为"','采用 Evidence Recall 作为指标，原为 Complete Evidence Recall。'),
 ('I-a 每条关系 source_doc_id 未限定','每条关系都带 source_doc_id 与 source_chunk_id。'),
 ('I-b 同上但加了"除 EVIDENCED_BY"','每条关系都带 source_doc_id 与 source_chunk_id（除 EVIDENCED_BY 外）。'),
 ('I-c 9 条核心关系都…','9 条核心关系都带证据属性。'),
]
for tag,txt in cases:
    d=mkh(txt); rc,out=run(d)
    L=[l.strip() for l in out.split('\n') if ('Evidence Recall' in l and l.strip().startswith('[OK')) or l.strip().startswith('!! 20-') or '证据属性表述' in l]
    print('%-40s exit=%d  %s'%(tag,rc,' | '.join(L)))
print()
# J：非门禁
d=mkh('本项目不引入多模态，但仍需实现多模态检索与 Agent 调度。')
rc,out=run(d)
print('J 否定词在别处：exit=%d'%rc)
print('   J 段输出：',[l.strip() for l in out.split('\n') if l.strip().startswith('?')] or '（无 ? 行——整行含"不引入"被过滤）')
print('   结论行：',[l for l in out.split('\n') if l.startswith('结论')])
