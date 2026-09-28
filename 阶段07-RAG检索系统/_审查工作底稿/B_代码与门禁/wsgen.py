import os,shutil,subprocess,sys
BASE=r'C:\Users\15129\AppData\Local\Temp\re7_B\ws'
CHECK=r'C:\Users\15129\Desktop\毕业设计\工具\跨文档核验.py'
def build(name,files):
    d=os.path.join(BASE,name)
    if os.path.isdir(d): shutil.rmtree(d)
    os.makedirs(d)
    for rel,content in files.items():
        p=os.path.join(d,rel)
        os.makedirs(os.path.dirname(p),exist_ok=True) if os.path.dirname(p)!=d else None
        open(p,'w',encoding='utf-8').write(content)
    return d
def run(d,strict=False,check=CHECK):
    env=dict(os.environ); env['PYTHONIOENCODING']='utf-8'
    args=[sys.executable,check,d]+(['--strict-citations'] if strict else [])
    r=subprocess.run(args,capture_output=True,text=True,encoding='utf-8',env=env)
    return r.returncode, r.stdout+r.stderr
def show(tag,out,keys):
    print('---- %s ----'%tag)
    for L in out.split('\n'):
        if any(k in L for k in keys): print('   ',L.strip())
