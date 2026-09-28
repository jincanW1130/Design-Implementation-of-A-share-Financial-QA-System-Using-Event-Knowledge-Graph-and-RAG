import hashlib, importlib, os, sys, argparse
REPO = r"C:\Users\15129\Desktop\毕业设计"
HERE = os.path.join(REPO, "代码", "检索")
sys.path.insert(0, HERE)
import config
OUT = os.path.join(os.environ['TEMP'], 're7_B', 'runout')
config.OUTPUT_FILES["pre_experiment_matrix"] = os.path.join(OUT, "pre_experiment_matrix.jsonl")
config.OUTPUT_FILES["k_selection"] = os.path.join(OUT, "k_selection.json")
pe = importlib.import_module("pre_experiment")
def sha(p): return hashlib.sha256(open(p,'rb').read()).hexdigest()
res = {}
for i in (1, 2):
    rc = pe.run_once(argparse.Namespace(quiet=True, profile="run", selftest=False))
    res[i] = (rc, sha(config.OUTPUT_FILES["pre_experiment_matrix"]),
                 sha(config.OUTPUT_FILES["k_selection"]))
print("RUN1", res[1], file=sys.stderr)
print("RUN2", res[2], file=sys.stderr)
print("MATRIX byte-identical across runs:", res[1][1] == res[2][1], file=sys.stderr)
print("SELECTION byte-identical across runs:", res[1][2] == res[2][2], file=sys.stderr)
# 与仓库内已落盘产物逐字节比对
import filecmp
repo_m = os.path.join(REPO, "阶段07-RAG检索系统", "检索产出", "pre_experiment_matrix.jsonl")
repo_s = os.path.join(REPO, "阶段07-RAG检索系统", "检索产出", "k_selection.json")
print("MATRIX == repo artifact:", sha(repo_m) == res[1][1], file=sys.stderr)
print("SELECTION == repo artifact:", sha(repo_s) == res[1][2], file=sys.stderr)
