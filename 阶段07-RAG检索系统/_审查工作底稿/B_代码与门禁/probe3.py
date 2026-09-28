import os,re,glob
ROOT=r'C:\Users\15129\Desktop\毕业设计'
STAGES=[d for d in sorted(glob.glob(os.path.join(ROOT,'阶段*'))) if os.path.isdir(d)]
paths=sorted(glob.glob(os.path.join(ROOT,'*.md')))
for sd in STAGES: paths+=sorted(glob.glob(os.path.join(sd,'*.md')))
D={os.path.basename(p):open(p,encoding='utf-8').read() for p in paths}
out=[]
C_PAT=re.compile(r'《(\d\d)》第(\d+(?:\.\d+)*)节')
# 所有 第x.y节 出现次数
allsec=0; matched=0; alt=[]
for n in D:
    for mm in re.finditer(r'第\s*\d+(?:\.\d+)*\s*节',D[n]):
        allsec+=1
    matched+=len(C_PAT.findall(D[n]))
out.append('全工作区 「第x.y节」出现 %d 次；C 的正则能匹配的 %d 次'%(allsec,matched))
out.append('')
out.append('== C 正则匹配不到、但明显是跨文档节号引用的写法（抽样）==')
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        # 带空格的
        for mm in re.finditer(r'《(\d\d)》第\s+\d+(?:\.\d+)*\s*节',L):
            alt.append('%s:%d  空格写法  %s'%(n,i,mm.group(0)))
        # 无「第」字的
        for mm in re.finditer(r'《(\d\d)》\s*(\d+\.\d+(?:\.\d+)*)\s*(?![节\d.])',L):
            alt.append('%s:%d  无「节」  %s'%(n,i,mm.group(0)))
        # 《NN》的x.y节
        for mm in re.finditer(r'《(\d\d)》的\s*\d+\.\d+',L):
            alt.append('%s:%d  「的」写法  %s'%(n,i,mm.group(0)))
for a in alt[:60]: out.append('  '+a)
out.append('  合计 %d 条'%len(alt))
out.append('')
out.append('== 表格行里出现反引号内含竖线 或 转义竖线 \| ==')
cnt=0
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        s=L.strip()
        if s.startswith('|') and s.endswith('|'):
            if re.search(r'`[^`]*\|[^`]*`',s) or '\|' in s:
                out.append('  %s:%d  %s'%(n,i,s[:100])); cnt+=1
out.append('  合计 %d 行'%cnt)
open(r'C:\Users\15129\AppData\Local\Temp\re7_B\probe3.txt','w',encoding='utf-8').write('\n'.join(out))
print('done')
