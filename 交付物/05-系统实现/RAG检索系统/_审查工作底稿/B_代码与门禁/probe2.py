import os,re,glob
ROOT=r'C:\Users\15129\Desktop\毕业设计'
STAGES=[d for d in sorted(glob.glob(os.path.join(ROOT,'阶段*'))) if os.path.isdir(d)]
paths=sorted(glob.glob(os.path.join(ROOT,'*.md')))
for sd in STAGES: paths+=sorted(glob.glob(os.path.join(sd,'*.md')))
D={os.path.basename(p):open(p,encoding='utf-8').read() for p in paths}
out=[]
out.append('== 提到《02》且带 vX.Y 的行，但该行不含 依据/上游/需求来源（N2 完全不审计）==')
CID=re.compile(r'《02[^》]*》[^《]{0,30}?(v\d+\.\d+)')
DECL=re.compile(r'依据|上游|需求来源')
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        if CID.search(L) and not DECL.search(L):
            out.append('  %s:%d  %s'%(n,i,L.strip()[:110]))
out.append('')
out.append('== 同上但含依据/上游/需求来源（N2 会审计）==')
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        if CID.search(L) and DECL.search(L):
            out.append('  %s:%d  %s'%(n,i,L.strip()[:130]))
out.append('')
out.append('== N2 的 CITE_SKIP 排除名单命中情况（含《02》vX.Y 的依据声明行所属文件）==')
from collections import Counter
c=Counter()
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        if CID.search(L) and DECL.search(L): c[n]+=1
out.append(str(dict(c)))
open(r'C:\Users\15129\AppData\Local\Temp\re7_B\probe2.txt','w',encoding='utf-8').write('\n'.join(out))
print('done')
