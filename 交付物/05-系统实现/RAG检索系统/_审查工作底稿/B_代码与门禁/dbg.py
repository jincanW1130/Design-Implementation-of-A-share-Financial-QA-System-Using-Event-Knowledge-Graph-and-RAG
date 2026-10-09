import re
p=r'C:\Users\15129\AppData\Local\Temp\re7_B\ws\n_3418\交付物/07-设计与需求/需求分析\07-需求分析.md'
t=open(p,encoding='utf-8').read()
print('CRLF?', '\r\n' in t)
print('has 7.2:', '### 7.2 需求追溯矩阵' in t)
print('mat:', bool(re.search(r'### 7\.2 需求追溯矩阵(.*?)\n## 八、',t,re.S)))
print('mat2(\r?\n):', bool(re.search(r'### 7\.2 需求追溯矩阵(.*?)\r?\n## 八、',t,re.S)))
print('s38:', bool(re.search(r'### 3\.8 功能需求汇总表(.*?)\n---',t,re.S)))
# 真实工作区的 07
p2=r'C:\Users\15129\Desktop\毕业设计\交付物/07-设计与需求/需求分析\07-需求分析（第三阶段）.md'
t2=open(p2,encoding='utf-8').read()
print('real CRLF?', '\r\n' in t2, 'real mat:', bool(re.search(r'### 7\.2 需求追溯矩阵(.*?)\n## 八、',t2,re.S)), 'real s38:', bool(re.search(r'### 3\.8 功能需求汇总表(.*?)\n---',t2,re.S)))
print('real 7.2 line:', [L for L in t2.split('\n') if L.startswith('### 7.2')][:2])
print('real 3.8 line:', [L for L in t2.split('\n') if L.startswith('### 3.8')][:2])
