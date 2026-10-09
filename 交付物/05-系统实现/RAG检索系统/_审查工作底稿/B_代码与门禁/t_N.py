import sys,os; sys.path.insert(0,r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *
DOC02 = ('# 项目执行总控文档 v3.2\n\n'
  '| 项 | 值 |\n|---|---|\n| 版本 | v3.2 |\n| 日期 | 2026-09-27 |\n\n'
  '## 一、总则\n\n### 1.2 修订记录\n\n'
  '| 版本 | 日期 | 说明 |\n|---|---|---|\n| v3.1 | 2026-09-27 | 旧 |\n| v3.2 | 2026-09-27 | 新 |\n\n'
  '## 五、边界\n\n### 5.1 边界一\n\n正文。\n')
def frs():
    s='## 三、功能需求\n\n'
    for i in range(1,7):
        s+='### 3.%d 条目%d（FR-%02d）\n\n- 来源追溯：《02》第5.1节\n\n'%(i,i,i)
    s+='### 3.8 功能需求汇总表\n\n| 编号 | 名称 | 优先级 | 备注 | 来源依据 |\n|---|---|---|---|---|\n'
    for i in range(1,7): s+='| FR-%02d | a | 高 | x | 《02》第5.1节 |\n'%i
    s+='\n---\n\n## 七、追溯\n\n### 7.2 需求追溯矩阵\n\n| 编号 | 名称 | 来源依据 | 验收 |\n|---|---|---|---|\n'
    for i in range(1,7): s+='| FR-%02d | a | 《02》第5.1节 | y |\n'%i
    for i in range(1,8): s+='| UC-%02d | a | 《02》第5.1节 | y |\n'%i
    for i in range(1,7): s+='| NFR-%02d | a | 《02》第5.1节 | y |\n'%i
    s+='\n## 八、附\n\n结束。\n'
    return s
DOC07=('# 07-需求分析\n\n## 一、总则\n\n### 1.3 需求来源清单\n\n'
  '| 序号 | 来源 | 说明 |\n|---|---|---|\n| 1 | 《02》第5.1节 | x |\n\n---\n\n')+frs()
def mk(cite_line,fn='09-下游文档.md'):
    files={'02-项目执行总控文档.md':DOC02,
           '交付物/07-设计与需求/需求分析/07-需求分析.md':DOC07,
           '交付物/07-设计与需求/需求分析/'+fn:cite_line}
    for s in ['交付物/08-文献与开题/选题与项目规划','交付物/08-文献与开题/文献调研与开题','交付物/07-设计与需求/需求分析','交付物/07-设计与需求/总体设计','交付物/04-数据与知识图谱/数据准备']:
        files[s+'/README.md']='# r\n'
    files['交付物/07-设计与需求/总体设计/_分节源文件/x.md']='# x\n'
    names=['02-项目执行总控文档','07-需求分析',fn[:-3]]
    files['00-项目总览与索引.md']='# 00 索引\n\n- '+' \n- '.join(names)+'\n'
    return build('n_'+str(abs(hash(cite_line))%99999),files)
def go(tag,line):
    d=mk(line)
    rc0,o0=run(d,False); rc1,o1=run(d,True)
    n2_0=[L.strip() for L in o0.split('\n') if 'N2 ' in L or '过期' in L or ('依据《02》' in L)]
    n2_1=[L.strip() for L in o1.split('\n') if 'N2 ' in L or '过期' in L or ('依据《02》' in L)]
    c0=[L for L in o0.split('\n') if L.startswith('结论')]
    c1=[L for L in o1.split('\n') if L.startswith('结论')]
    print('==== %s ===='%tag)
    print('  引用行：%s'%line.strip()[:110])
    print('  默认 exit=%d  %s'%(rc0,c0))
    print('  strict exit=%d  %s'%(rc1,c1))
    print('  N2（默认）：'); [print('     '+x) for x in n2_0]
    print('  N2（strict）：'); [print('     '+x) for x in n2_1]
    print()
go('H1 依据行只写旧版本','> 编制日期：2026-09-27　依据：《02-项目执行总控文档》（v2.0）第5.1节\n')
go('H2 依据行写旧版本、同行另提当前版本','> 编制日期：2026-09-27　依据：《02-项目执行总控文档》（v2.0），另见数据集 v3.2\n')
go('H3 引用旧版本但行内无 依据/上游/需求来源','> 编制日期：2026-09-27　参照《02-项目执行总控文档》（v2.0）第5.1节\n')
