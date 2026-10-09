import copy, importlib, json, os, sys, argparse, io, contextlib
REPO = r"C:\Users\15129\Desktop\毕业设计"
sys.path.insert(0, os.path.join(REPO, "交付物/03-代码", "检索"))
import config
T = os.path.join(os.environ['TEMP'], 're7_B', 'mut2'); os.makedirs(T, exist_ok=True)
MP=os.path.join(T,"pre_experiment_matrix.jsonl"); SP=os.path.join(T,"k_selection.json")
config.OUTPUT_FILES["pre_experiment_matrix"]=MP; config.OUTPUT_FILES["k_selection"]=SP
pe = importlib.import_module("pre_experiment")
BASE_S=json.load(open(os.path.join(REPO,"交付物/05-系统实现/RAG检索系统","检索产出","k_selection.json"),encoding='utf-8'))
BASE_M=[json.loads(l) for l in open(os.path.join(REPO,"交付物/05-系统实现/RAG检索系统","检索产出","pre_experiment_matrix.jsonl"),encoding='utf-8') if l.strip()]
def write(sel,mat):
    json.dump(sel,open(SP,'w',encoding='utf-8'),ensure_ascii=False,sort_keys=True,indent=2)
    with open(MP,'w',encoding='utf-8',newline='\n') as f:
        for r in mat: f.write(json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n")
def run():
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf): rc=pe.cmd_selftest(argparse.Namespace(quiet=True,profile='selftest',selftest=True))
    return rc,[l.split(']',1)[1].strip() for l in buf.getvalue().splitlines() if '[FAIL]' in l], buf.getvalue()
def case(name, gvalue, mutate):
    s=copy.deepcopy(BASE_S); m=copy.deepcopy(BASE_M); mutate(s,m)
    config.RETRIEVAL['graph_retention_share']=gvalue   # 同步改 config，模拟"回填被同步篡改"
    write(s,m); rc,failed,_=run()
    print('%-70s rc=%d 失败项=%s'%(name,rc,failed if failed else '（无 → 检查恒真，漏报）'))
    config.RETRIEVAL['graph_retention_share']=2
case('M3\" : selected.g/adopted_g=3，且 config 同步改成 3（g=3 的 CER 劣于 g=0）', 3,
     lambda s,m:(s['selected'].__setitem__('g',3), s['evidence']['g_curve'].__setitem__('adopted_g',3)))
case('M5\" : selected.g/adopted_g=5，且 config 同步改成 5', 5,
     lambda s,m:(s['selected'].__setitem__('g',5), s['evidence']['g_curve'].__setitem__('adopted_g',5)))
case('M8\" : selected.g/adopted_g=1，且 config 同步改成 1', 1,
     lambda s,m:(s['selected'].__setitem__('g',1), s['evidence']['g_curve'].__setitem__('adopted_g',1)))
