import sys,os,re; sys.path.insert(0,r'C:\Users\15129\AppData\Local\Temp\re7_B')
from wsgen import *
DOC02=('# 项目执行总控文档 v3.2\n\n| 项 | 值 |\n|---|---|\n| 版本 | v3.2 |\n\n'
 '## 一、总则\n\n### 1.2 修订记录\n\n| 版本 | 日期 | 说明 |\n|---|---|---|\n| v3.2 | 2026-09-27 | 新 |\n\n'
 '## 五、边界\n\n### 5.1 边界一\n\n正文。\n\n### 5.2 边界二\n\n正文。\n')
def doc07(src):
    s='# 07-需求分析\n\n## 一、总则\n\n### 1.3 需求来源清单\n\n| 序号 | 来源 | 说明 |\n|---|---|---|\n| 1 | %s | x |\n\n---\n\n'%src
    s+='## 三、功能需求\n\n'
    for i in range(1,7): s+='### 3.%d 条目%d（FR-%02d）\n\n- 来源追溯：%s\n\n'%(i,i,i,src)
    s+='### 3.8 功能需求汇总表\n\n| 编号 | 名称 | 优先级 | 备注 | 来源依据 |\n|---|---|---|---|---|\n'
    for i in range(1,7): s+='| FR-%02d | a | 高 | x | %s |\n'%(i,src)
    s+='\n---\n\n## 七、追溯\n\n### 7.2 需求追溯矩阵\n\n| 编号 | 名称 | 来源依据 | 验收 | 备注 |\n|---|---|---|---|---|\n'
    for i in range(1,7): s+='| FR-%02d | a | %s | y | z |\n'%(i,src)
    for i in range(1,8): s+='| UC-%02d | a | %s | y | z |\n'%(i,src)
    for i in range(1,7): s+='| NFR-%02d | a | %s | y | z |\n'%(i,src)
    return s+'\n## 八、附\n\n结束。\n'
def mkd(src,extra=''):
    files={'02-项目执行总控文档.md':DOC02,'交付物/07-设计与需求/需求分析/07-需求分析.md':doc07(src),
      '00-项目总览与索引.md':'# 00\n\n- 02-项目执行总控文档\n- 07-需求分析\n'}
    for s in ['交付物/08-文献与开题/选题与项目规划','交付物/08-文献与开题/文献调研与开题','交付物/07-设计与需求/需求分析','交付物/07-设计与需求/总体设计','交付物/04-数据与知识图谱/数据准备']:
        files[s+'/x.md']='# x\n'
    files['交付物/07-设计与需求/总体设计/_分节源文件/x.md']='# x\n'
    return build('d_'+str(abs(hash(src))%99999),files)
for tag,src in [('基线：全部指向《02》第5.1节','《02》第5.1节'),
                ('只改《07》、四处同改为《02》第5.2节','《02》第5.2节'),
                ('只改《07》、四处同改为不存在的《02》第9.9节','《02》第9.9节'),
                ('只改《07》、四处同改为《01》第5.1节（张冠李戴但存在）','《01》第5.1节')]:
    d=mkd(src); rc,out=run(d)
    L=[l.strip() for l in out.split('\n') if re.match(r'\s*(\[OK |\[FAIL|\[WARN)',l.strip()) and ('来源' in l or '节' in l or '覆盖' in l)]
    print('== %s == exit=%d'%(tag,rc))
    for l in L: print('    ',l)
    print()
