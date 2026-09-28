import os,re,glob,json
ROOT=r'C:\Users\15129\Desktop\毕业设计'
STAGES=[d for d in sorted(glob.glob(os.path.join(ROOT,'阶段*'))) if os.path.isdir(d)]
paths=sorted(glob.glob(os.path.join(ROOT,'*.md')))
for sd in STAGES: paths+=sorted(glob.glob(os.path.join(sd,'*.md')))
D={os.path.basename(p):open(p,encoding='utf-8').read() for p in paths}
out=[]
# 1) 引用不存在文档号的 《NN》第x.y节
bynum={}
for n in D:
    m=re.match(r'^(\d\d)-',n)
    if m: bynum[m.group(1)]=n
out.append('== 引用《NN》第x.y节，其中 NN 不在 bynum 中（C 直接 continue 跳过）==')
for n in D:
    for mm in re.finditer(r'《(\d\d)》第(\d+(?:\.\d+)*)节',D[n]):
        if mm.group(1) not in bynum:
            out.append('  %s: %s'%(n,mm.group(0)))
out.append('bynum keys=%s'%sorted(bynum))
# 2) 反引号内路径扩展名统计
out.append('')
out.append('== 反引号内带扩展名的 token，按扩展名 ==')
from collections import Counter
c=Counter()
for n in D:
    for tok in re.findall(r'`([^`\n]+\.([A-Za-z0-9]+))`',D[n]):
        c[tok[1]]+=1
for k,v in c.most_common(): out.append('  .%s : %d'%(k,v))
out.append('  检查器覆盖: md,py,html,csv,docx,pdf,png,svg')
# 3) 反引号内出现的 json/jsonl/txt/yaml 实例
out.append('')
out.append('== 反引号内 .json/.jsonl/.txt/.yaml 实例（K 不检查）==')
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        for tok in re.findall(r'`([^`\n]+\.(?:json|jsonl|txt|ya?ml|log|parquet|db))`',L):
            out.append('  %s:%d  %s'%(n,i,tok))
open(r'C:\Users\15129\AppData\Local\Temp\re7_B\probe1.txt','w',encoding='utf-8').write('\n'.join(out))
print('done', len(out))
