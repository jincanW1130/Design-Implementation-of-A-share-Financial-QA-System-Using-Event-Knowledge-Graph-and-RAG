import json, io, re
ROOT=r"C:\Users\15129\Desktop\毕业设计"
led=json.load(io.open(ROOT+r"\交付物/05-系统实现/RAG检索系统\预实验问题集\第三方复核台账.json",encoding="utf-8"))
per=led["cross_vendor"]["per_question_verdicts"]           # 确认口径 kimi/zhipu
src=io.open(ROOT+r"\交付物/03-代码\检索\build_questions.py",encoding="utf-8").read()
m=re.search(r"THIRD_PARTY_VERDICTS = \{(.*?)\n\}", src, re.S)
tbl={}
for line in m.group(1).split("\n"):
    mm=re.match(r'\s*"(PE-\d+)": \{(.*)\},\s*$', line)
    if not mm: continue
    q=mm.group(1); body=mm.group(2)
    d={}
    for k,vt,ab in re.findall(r'"(\w+)": \("([^"]+)", (True|False)\)', body):
        d[k]=(vt, ab=="True")
    tbl[q]=d
bad=[]
for q in sorted(tbl):
    hc={k:v[0] for k,v in tbl[q].items() if k in ("kimi","zhipu")}
    lg=per.get(q) or {}
    if hc!=lg: bad.append((q,hc,lg))
out=[]
out.append("硬编码表题数=%d；台账确认口径题数=%d" % (len(tbl), len(per)))
out.append("不一致题=%s" % (bad or "无（30 题逐题一致）"))
out.append("含 qianfan 的题=%d" % sum(1 for q in tbl if "qianfan" in tbl[q]))
io.open("xcheck.txt","w",encoding="utf-8").write("\n".join(map(str,out)))
print("ok")
