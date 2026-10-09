import copy, importlib, json, os, sys, argparse, io, contextlib
REPO = r"C:\Users\15129\Desktop\毕业设计"
sys.path.insert(0, os.path.join(REPO, "交付物/03-代码", "检索"))
import config
T = os.path.join(os.environ['TEMP'], 're7_B', 'mut')
os.makedirs(T, exist_ok=True)
MP = os.path.join(T, "pre_experiment_matrix.jsonl")
SP = os.path.join(T, "k_selection.json")
config.OUTPUT_FILES["pre_experiment_matrix"] = MP
config.OUTPUT_FILES["k_selection"] = SP
pe = importlib.import_module("pre_experiment")
BASE_S = json.load(open(os.path.join(REPO,"交付物/05-系统实现/RAG检索系统","检索产出","k_selection.json"),encoding='utf-8'))
BASE_M = [json.loads(l) for l in open(os.path.join(REPO,"交付物/05-系统实现/RAG检索系统","检索产出","pre_experiment_matrix.jsonl"),encoding='utf-8') if l.strip()]

def write(sel, mat):
    json.dump(sel, open(SP,'w',encoding='utf-8'), ensure_ascii=False, sort_keys=True, indent=2)
    with open(MP,'w',encoding='utf-8',newline='\n') as f:
        for r in mat: f.write(json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",",":"))+"\n")

def run():
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pe.cmd_selftest(argparse.Namespace(quiet=True, profile='selftest', selftest=True))
    failed=[l.split(']',1)[1].strip() for l in buf.getvalue().splitlines() if '[FAIL]' in l]
    return rc, failed

def case(name, mutate):
    s=copy.deepcopy(BASE_S); m=copy.deepcopy(BASE_M)
    mutate(s,m)
    write(s,m)
    rc, failed = run()
    print('%-64s selftest_rc=%d  捕获到的失败项=%s' % (name, rc, failed if failed else '（无 → 漏报）'))

case('基线（未篡改）', lambda s,m: None)
case('M1 selected.K 10→15（K=15 被预算排除，违反规则3(b)）', lambda s,m: s['selected'].__setitem__('K',15))
case('M2 selected.N 20→100（违反规则4「取最小 N」）', lambda s,m: s['selected'].__setitem__('N',100))
case('M3 selected.g 2→3（g=3 的 CER 0.5333 劣于 g=0，违反规则5）', lambda s,m: s['selected'].__setitem__('g',3))
case('M4 selected.context_token_budget 3600→9999', lambda s,m: s['selected'].__setitem__('context_token_budget',9999))
case('M5 删掉整个 evidence.saturation_under_budget', lambda s,m: s['evidence'].pop('saturation_under_budget'))
case('M6 删掉整个 evidence.budget_sensitivity', lambda s,m: s['evidence'].pop('budget_sensitivity'))
case('M7 删掉 evidence.round1_cer_curve', lambda s,m: s['evidence'].pop('round1_cer_curve'))
case('M8 g_curve.adopted_g 与 selected.g 都改成 1（内部自洽但非最大）', lambda s,m: (s['evidence']['g_curve'].__setitem__('adopted_g',1), s['selected'].__setitem__('g',1)))
case('M9 g=1 行的 not_worse_than_g0 改成 False（与 vs_g0_flags 自相矛盾）', lambda s,m: s['evidence']['g_curve']['primary_rows'][1].__setitem__('not_worse_than_g0',False))
case('M10 vs_g0_flags 全改成 "-"（与 metrics 矛盾）', lambda s,m: s['evidence']['g_curve']['primary_rows'][2].__setitem__('vs_g0_flags',{k:'-' for k in ['recall_at_k','precision_at_k','mrr','complete_evidence_recall_at_k']}))
case('M11 saturation rows 的 gold_feasible 全部改成 True', lambda s,m: [r.__setitem__('gold_feasible',True) for r in s['evidence']['saturation_under_budget']['rows']])
case('M12 N_curve 的 selected 挪到 N=100', lambda s,m: [r.__setitem__('selected', r['N']==100) for r in s['evidence']['N_curve']])
case('M13 矩阵某个四项指标值 +0.0001', lambda s,m: m[0]['metrics'].__setitem__('recall_at_k', m[0]['metrics']['recall_at_k']+0.0001))
case('M14 矩阵某行 K 改成 999', lambda s,m: m[0].__setitem__('K',999))
case('M15 矩阵删掉一行（9→8 格）', lambda s,m: m.pop(0))
case('M16 矩阵写入 timestamp 键', lambda s,m: m[0].__setitem__('timestamp','2026-09-28'))
case('M17 矩阵写入 elapsed 键', lambda s,m: m[0].__setitem__('elapsed',1.23))
case('M18 selected.g 2→5，adopted_g 也改 5', lambda s,m: (s['evidence']['g_curve'].__setitem__('adopted_g',5), s['selected'].__setitem__('g',5)))
