import os,re,glob
ROOT=r'C:\Users\15129\Desktop\毕业设计'
STAGES=[d for d in sorted(glob.glob(os.path.join(ROOT,'阶段*'))) if os.path.isdir(d)]
paths=sorted(glob.glob(os.path.join(ROOT,'*.md')))
for sd in STAGES: paths+=sorted(glob.glob(os.path.join(sd,'*.md')))
D={os.path.basename(p):open(p,encoding='utf-8').read() for p in paths}
out=[]
# 1) 同一行里，《NN》之后还有哪些 第x.y节 未被 C 校验
SEC=re.compile(r'第(\d+(?:\.\d+)*)节')
C=re.compile(r'《(\d\d)》第(\d+(?:\.\d+)*)节')
tot_unchecked=0; ex=[]
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        ms=list(C.finditer(L))
        if not ms: continue
        last=ms[-1].end()
        tail=L[last:]
        # 同一行、最后一段里的其它 第x.y节（C 不查）
        for mm in SEC.finditer(tail):
            tot_unchecked+=1
            if len(ex)<25: ex.append('%s:%d  %s'%(n,i,mm.group(0)))
out.append('《NN》第x.y节 之后同行还出现的 第x.y节（C 全部不校验）：%d 处'%tot_unchecked)
for e in ex: out.append('  '+e)
out.append('')
out.append('== 每条链被 C 漏掉的实例（原文片段）==')
c2=0
for n in sorted(D):
    for i,L in enumerate(D[n].split('\n'),1):
        ms=list(C.finditer(L))
        if not ms: continue
        for m in ms:
            tail=L[m.end():]
            if SEC.search(tail):
                c2+=1
                if c2<=12: out.append('  %s:%d  ...%s'%(n,i,L[max(0,m.start()-20):m.end()+40]))
out.append('  合计 %d 处链式引用只校验了首节号'%c2)
out.append('')
# 2) 表格行：朴素列数 vs 去掉行内代码后的列数
def naive(s): return len(s.strip('|').split('|'))
def aware(s):
    t=re.sub(r'`[^`]*`','X',s)
    return len(t.strip('|').split('|'))
bad=0
for n in sorted(D):
    cur=[]; fence=False
    for i,L in enumerate(D[n].split('\n'),1):
        if L.strip().startswith('```'): fence=not fence; continue
        if fence: continue
        s=L.strip()
        if s.startswith('|') and s.endswith('|') and naive(s)!=aware(s):
            bad+=1
            if bad<=10: out.append('  %s:%d  朴素=%d 去代码=%d  %s'%(n,i,naive(s),aware(s),s[:90]))
out.append('表格行内代码含竖线导致列数可能误判的行数：%d'%bad)
open(r'C:\Users\15129\AppData\Local\Temp\re7_B\probe4.txt','w',encoding='utf-8').write('\n'.join(out))
print('done')
