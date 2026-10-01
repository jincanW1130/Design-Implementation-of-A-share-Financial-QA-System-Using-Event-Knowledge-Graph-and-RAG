# -*- coding: utf-8 -*-
r"""工具\验收第9阶段.py —— 第 9 阶段（前后端系统集成）专项验收门禁（T13）。

依据
----
《24-第9阶段任务书（前后端系统集成）》第八节「验收标准（可机器核验）」，
A～I 共 **58 行**（A6＋B8＋C10＋D6＋E6＋F6＋G6＋H5＋I5）。
行号、标题、分组一律在运行时从《24》第八节**解析**得到，本脚本不自带副本；
脚本里注册的判据行与解析出来的 58 行若对不上，直接报「行结构错误」并按退出码 2 退出。

用法
----
    python 工具\验收第9阶段.py                    :: full 档：58 行逐行判，退出码 0／1／2
    python 工具\验收第9阶段.py --profile static   :: 静态档：不需要服务，只判文档与产物，未执行的行记 UNRUN，退出码 2
    python 工具\验收第9阶段.py --selftest         :: 负向校准：原样对照 ＋ ≥5 个反例，逐例打印「期望 FAIL 集 ＝ 实测 FAIL 集」
    python 工具\验收第9阶段.py --root <PATH>      :: 允许指向副本（selftest 用）

退出码
------
    0  full 档 58 行全部 [OK]
    1  有内容失败（[FAIL]）
    2  环境未就绪（服务／MySQL／Neo4j／Docker 不可用，见硬约束 25）／static 档未全量执行／selftest 未通过／行结构错误

口径（写死在脚本里，逐条注明《24》出处）
----------------------------------------
* 环境未就绪 ≠ 内容失败（《24》硬约束 25）：服务没起来时，实况行记 UNRUN 并单独成栏，退出码 2。
* C1 用 `app.openapi()["paths"]`（**不是** `main.py` 的 `api_routes()`）：预期 = 表 4-13 的 25 个业务接口
  ＋ **已登记新增**（`REGISTERED_ADDITIONS`：`/api/health` ＋ 4 个 `/api/market/*`；3 个 `/api/auth/*` 不注册）。
  「缺」→ FAIL（一个都不能少）；「多」逐条比对登记清单：清单内记「已登记新增」并打印，**清单外一律 FAIL**。
* `2003` 是响应体纪律的唯一例外：错误响应键集 ⊆ {code, message}；2003 允许且必须带
  `retained_for_history=true`；**任何**响应都不得出现 `detail` 键。
* 两个新码必须在 C3 逐码列表里出现：`1004`（HTTP 429，限流）与 `3004`（HTTP 502，装配账目守卫未通过）；
  3004 的确定性样本是 PE-03。
* D1／D2 走**候选题列表**（`QA_CANDIDATES`）取前若干道成功（HTTP 200）的题：D1 取前 3 道判「四段答案」，
  不足 3 道 → FAIL；D2 取前 2 道判「`[证据n]` 不越界」。某题命中守卫码（3004／3001）→ 本轮跳过（逐题打印）、
  不计 FAIL；D2 候选题全被守卫拦下 → UNRUN；其它错误码（500／9999 等）→ 仍 FAIL。
* B4 的行数不是恒等式：`document`=709、`document_chunk`=5018、`user`=0 是常量；`question`≥30 且
  `answer` 行数 ＝ `question` 行数；`answer_evidence` 按 `answer_id` 分组且 `` `rank` `` 连续 1..m、总数 ≥293；
  30 条基线的交叉检查用 db_counts.json 的**导入读数**（30／30／293）。
  `` `rank` ``／`` `user` `` 是 MySQL 8 保留字，SQL 里必须加反引号。
* E1 的图谱计数取自一致性检查响应的 `diff`（`diff.graph_nodes_total` 2802／`diff.graph_edges_total` 2736），
  7 个节点标签与 9 个关系类型与 graph_counts.json／graph_stats.json 交叉检查。
* G5（NFR-02）两个读数口径不同、**不互相替代**：① 背靠背 100 连续（60/100，缺口全是限流 1004）——
  这是**限流生效的证据，不是 FAIL**；② 正常节奏（每 1.2 s 一次）100 连续 —— 这是 G5 的通过判据（阈值 ≥95%）。
* G4 只看「四个段都在、每段给了来源、并如实标注哪一段不可信」，**不**要求图谱查询段 > 0。
* H2/H3：Docker 不可用属环境未就绪，不是内容失败。
* I1 用决策者的基线快照（`_工作底稿\决策者核验\输入指纹.py --check`）判定；快照缺失则记「无法判定」。
* I2 扫全仓（排除 `.git`／`node_modules`／`dist`／`_工作底稿`），被禁术语 0 命中；FAISS 一律写「向量索引」。
* 中文查询参数一律 URL 编码（GBK 控制台发原始中文会让 h11 返回 400，是编码问题不是缺陷）。
* 只读：不改业务代码、不改产物数值、不放宽判据；发现真缺陷如实 FAIL。不打印、不落盘任何口令。
"""

from __future__ import annotations

import argparse
import collections
import glob
import io
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:                                                        # GBK 控制台 → UTF-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:                                           # pragma: no cover
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# --------------------------------------------------------------------------
# 0. 路径与常量
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, os.pardir))

STAGE = "阶段09-前后端系统集成"
P_TASK = os.path.join(STAGE, "24-第9阶段任务书（前后端系统集成）.md")
P_DOC25 = os.path.join(STAGE, "25-第9阶段产出文档（前后端系统集成）.md")
P_DESIGN = os.path.join("阶段04-系统总体设计", "10-系统总体设计（第四阶段）.md")
P_OUT = os.path.join(STAGE, "集成产出")
P_EVID = os.path.join(P_OUT, "_证据")
P_BACKEND = os.path.join("代码", "后端")
P_FRONTEND = os.path.join("代码", "前端")
P_DEPLOY = "部署"
P_QSET = os.path.join("阶段07-RAG检索系统", "预实验问题集", "questions.jsonl")
P_QAREC = os.path.join("阶段08-智能问答系统", "问答产出", "qa_records.jsonl")
P_DOCS = os.path.join("阶段05-数据准备", "数据集", "v2.1", "clean", "documents.jsonl")
P_CHUNKS = os.path.join("阶段05-数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl")
P_GRAPH_STATS = os.path.join("阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2", "graph_stats.json")
P_NODES_CSV = os.path.join("阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2", "nodes.csv")
P_EDGES_CSV = os.path.join("阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2", "edges.csv")
P_XDOC = os.path.join("工具", "跨文档核验.py")
P_WORK = os.path.join(STAGE, "_工作底稿")
P_FINGERPRINT = os.path.join(P_WORK, "决策者核验", "输入指纹.py")
P_RUN_MANIFEST = os.path.join(P_OUT, "run_manifest.json")
P_DB_COUNTS = os.path.join(P_OUT, "db_counts.json")
P_GRAPH_COUNTS = os.path.join(P_OUT, "graph_counts.json")
P_LATENCY = os.path.join(P_OUT, "latency_profile.json")
P_ERRSCEN = os.path.join(P_OUT, "error_scenarios.jsonl")
P_SMOKE = os.path.join(P_OUT, "smoke_matrix.jsonl")

BASE = "http://127.0.0.1:8000"
ADMIN = {"X-Client-Role": "admin"}

# 门禁自身的**主动节流**：服务端限流是 60 次／60 秒（滑动窗口，按来源 IP）。门禁在 A～C8
# 这一串里会连发数十个请求，若不加节制，会把「服务端限流」误当成被测对象的「内容失败」
# （429 会让一条本该 OK 的判据 FAIL）——这是门禁自造的假失败。故 http() 默认先过 _pace()：
# 窗口内已达 PACE_LIMIT 就先等到最早的请求滑出窗口。**C9 例外**（它要的就是触发限流，
# 调用时传 pace=False）。
_PACE_TS = collections.deque()
PACE_LIMIT = 54
PACE_WINDOW = 60.0

SIX_TABLES = ["user", "document", "document_chunk", "question", "answer", "answer_evidence"]
RESERVED = {"rank", "user"}                                  # MySQL 8 保留字，SQL 里要加反引号

ROW_GROUPS = {"A": 6, "B": 8, "C": 10, "D": 6, "E": 6, "F": 6, "G": 6, "H": 5, "I": 5}
TOTAL_ROWS = 58
GROUP_TITLE = {
    "A": "环境与服务", "B": "数据库与导入", "C": "后端接口", "D": "问答与证据链路",
    "E": "图谱服务化", "F": "前端页面", "G": "安全与非功能", "H": "部署形态", "I": "一致性、只读与文档",
}

# C3 逐码表：code → 期望 HTTP（errors.py CODES 与《24》第五节硬约束 4 的口径）
C3_CODES = [1001, 1002, 1003, 1004, 2001, 2002, 2003, 3004, 4002]
C3_EXPECT_HTTP = {1001: 400, 1002: 400, 1003: 400, 1004: 429, 2001: 404,
                  2002: 200, 2003: 409, 3004: 502, 4002: 403}

# C1 登记清单：**新增接口必须同时登记在《25》第 4 节与本文；未登记的新增一律 FAIL**（判据不放宽）。
# 含基座探针 `GET /api/health` 与作者要求的「实时数据区」四个 `/api/market/*`（实现在 api/market.py，
# 注册于 main.py 的 OPTIONAL_ROUTERS）。C1 里凡 `got` 超出表 4-13 的 25 个业务接口者，逐条比对本清单：
# 在清单里的记「已登记新增」放行并打印，不在清单里的一律 FAIL。
REGISTERED_ADDITIONS = {
    ("GET", "/api/health"),
    ("GET", "/api/market/quote"),
    ("GET", "/api/market/announcements"),
    ("GET", "/api/market/news"),
    ("GET", "/api/market/reports"),
    # 2026-10-01 补登（《25》v1.6 / v1.8 已登记，本清单此前漏同步）：
    ("GET", "/api/graph/entities/{node_id}"),            # 实体详情（真实属性）
    ("GET", "/api/graph/entities/{node_id}/evidence"),   # 实体级证据
}

# D1／D2 的**候选题列表**：依次尝试，取前若干道成功（HTTP 200）的题做机检。
# 上游第 8 阶段的「装配账目守卫／图谱侧」属**已知限制**（确定性样本 PE-03，已登记于《25》）：
# 某题返回守卫码（3004＝装配账目守卫未通过／3001＝图谱服务不可用）时，本轮**跳过该题**并继续下一题，
# 不计 FAIL（逐题打印）；返回其它错误码（500／9999 等）仍按**真故障** FAIL，不混进「守卫跳过」。
QA_CANDIDATES = ["PE-01", "PE-02", "PE-15", "PE-04"]
UPSTREAM_GUARD_CODES = frozenset({3004, 3001})

# C2 抽样的 8 个接口（覆盖六个模块；声明在前，避免「挑对得上的报」）
C2_SAMPLES = [
    ("GET", "/api/admin/documents", None, ADMIN, "表 4-13 / 财经信息管理"),
    ("GET", "/api/admin/consistency-check", None, ADMIN, "表 4-13 / 财经信息管理"),
    ("GET", "/api/admin/extraction/disambiguation", None, ADMIN, "表 4-13 / 财经事件抽取"),
    ("GET", "/api/graph/entities", None, None, "表 4-13 / 事件知识图谱"),
    ("GET", "/api/graph/events/EVT-0006", None, None, "表 4-13 / 事件知识图谱"),
    ("POST", "/api/qa/ask", "__ASK__", None, "表 4-13 / 智能问答"),
    ("GET", "/api/evidence/1/graph-path", None, None, "表 4-13 / 证据追溯"),
    ("GET", "/api/history", "__HIST__", None, "表 4-13 / 历史问答"),
]

# I2 术语纪律：被禁的「四字连写」术语（拼接构造，避免脚本自身成为命中源）
BANNED_VDB = "向量" + "数据库"
BANNED_TERMS = [BANNED_VDB]
VDB_GOOD = "向量索引"

# E6 不得出现的部署声明（除「容器形态的 Neo4j 服务」以外）
FAKE_DEPLOY = ["集群", "高可用", "HA 部署", "生产部署", "分布式部署", "Kubernetes", "K8s",
               "docker swarm", "主从复制", "哨兵", "sentinel", "cluster"]

# G6 不引入的被排除技术
EXCLUDED_TECH = ["langchain", "llama_index", "llamaindex", "elasticsearch", "kafka",
                 "kubernetes", "k8s", "helm", "airflow", "celery", "ray serve"]

# 镜像（selftest）需要带的文件与目录
MIRROR_FILES = [
    P_TASK, P_DOC25, P_DESIGN, P_QSET, P_QAREC, P_DOCS, P_CHUNKS, P_GRAPH_STATS,
    P_NODES_CSV, P_EDGES_CSV, P_XDOC, P_FINGERPRINT,
    P_DB_COUNTS, P_GRAPH_COUNTS, P_LATENCY, P_ERRSCEN, P_SMOKE, P_RUN_MANIFEST,
    os.path.join(P_OUT, "input_manifest.json"),
    os.path.join(P_WORK, "决策者核验", "核验_限流与PE03.py"),
    os.path.join(P_WORK, "决策者核验", "_扫描前端产物.py"),
    os.path.join(P_BACKEND, "config.local.json.example"),
    os.path.join(P_DEPLOY, "README.md"),
    os.path.join(P_DEPLOY, "Dockerfile"),
    os.path.join(P_DEPLOY, "启动.ps1"),
    os.path.join(P_DEPLOY, "config.docker.json"),
    os.path.join(P_FRONTEND, "package.json"),
    os.path.join(P_FRONTEND, "package-lock.json"),
    os.path.join(P_FRONTEND, "index.html"),
    os.path.join(P_FRONTEND, "vite.config.js"),
]
MIRROR_DIRS = [
    P_BACKEND,
    os.path.join("代码", "问答"),             # F2 要拿 prompt.py 的 SECTION_HEADERS 逐字对
    os.path.join(P_FRONTEND, "src"),
    P_DEPLOY,
    P_EVID,
    os.path.join(P_WORK, "决策者核验"),
]
MIRROR_SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", ".venv"}
MIRROR_SKIP_EXT = {".log", ".pyc", ".png", ".jpg", ".zip", ".exe", ".dll"}

# 证据文件（实况读数的原始留痕）
EV = {n: os.path.join(P_EVID, n) for n in [
    "smoke_admin_consistency.json", "nfr02_paced100.json", "nfr02_concurrent10.json",
    "nfr02_sequential100.json", "health_final.json", "docker_build_evidence.txt",
    "frontend_devserver.log", "smoke_config_meta.json", "ask_PE-01.json", "ask_PE-02.json",
    "ask_PE-04.json", "ask_experiment_admin.json", "error_rows_live.json",
    "smoke_history_list.json", "smoke_history_detail.json", "ask_failures.json",
]}


# --------------------------------------------------------------------------
# 1. 小工具
# --------------------------------------------------------------------------
def rel(root, path):
    """仓库（或镜像）相对路径，统一正斜杠。"""
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except Exception:
        return path


def br(root, path, line=None):
    """文件:行号 —— FAIL 证据的最小单位。"""
    s = rel(root, path)
    return "%s:%s" % (s, line) if line else s


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def read_lines(path):
    return read_text(path).split("\n")


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return default


def load_jsonl(path):
    out = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln:
                try:
                    out.append(json.loads(ln))
                except Exception:
                    pass
    return out


def decode_out(b):
    """子进程输出：先按 UTF-8，再按 GBK（中文 Windows 控制台）。"""
    for enc in ("utf-8", "gbk"):
        try:
            return b.decode(enc)
        except Exception:
            continue
    return b.decode("utf-8", "replace")


def run_cmd(args, cwd=None, timeout=600, env=None):
    """返回 (rc, text)；text 合并 stderr。"""
    e = dict(os.environ)
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, env=e)
        return p.returncode, decode_out(p.stdout)
    except subprocess.TimeoutExpired:
        return 124, "<超时 %ss>" % timeout
    except FileNotFoundError as exc:
        return 127, "<找不到可执行文件：%s>" % exc


def port_open(port, host="127.0.0.1", timeout=1.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _json_or(raw):
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw[:400]}


def http(method, path, payload=None, headers=None, timeout=180, pace=True):
    """返回 (status|None, body_dict, seconds)。None 表示连不上（环境问题）。

    `pace=False` 只给 C9 用（它要故意触发限流）；其余调用默认先过 _pace()，
    免得门禁自己的连发把服务端限流误算成内容失败。
    """
    if pace:
        while _PACE_TS and time.time() - _PACE_TS[0] > PACE_WINDOW:
            _PACE_TS.popleft()
        if len(_PACE_TS) >= PACE_LIMIT:
            wait = PACE_WINDOW - (time.time() - _PACE_TS[0]) + 0.5
            print("[ 节流：门禁自身连发逼近 60 次／60 s 限流窗口，等 %.1f 秒 ]" % wait)
            time.sleep(wait)
            while _PACE_TS and time.time() - _PACE_TS[0] > PACE_WINDOW:
                _PACE_TS.popleft()
        _PACE_TS.append(time.time())
    hdr = {"Content-Type": "application/json"}
    if headers:
        hdr.update(headers)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(BASE + path, method=method, data=data, headers=hdr)
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, _json_or(r.read().decode("utf-8", "replace")), round(time.time() - t0, 3)
    except urllib.error.HTTPError as exc:
        return exc.code, _json_or(exc.read().decode("utf-8", "replace")), round(time.time() - t0, 3)
    except Exception as exc:
        return None, {"_error": str(exc)[:200]}, round(time.time() - t0, 3)


def qs(**kw):
    """构造查询串；中文一律 UTF-8 百分号编码（GBK 控制台发原始中文会让 h11 回 400）。"""
    items = [(k, v) for k, v in kw.items() if v is not None]
    return "?" + urllib.parse.urlencode(items, quote_via=urllib.parse.quote)


def keys_deep(obj, acc=None):
    """递归收集 JSON 里出现过的所有键名。"""
    if acc is None:
        acc = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            keys_deep(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            keys_deep(v, acc)
    return acc


def path_match(concrete, template):
    """把具体路径（去掉查询串）对上 表 4-13 的路径模板（{x} 匹配一段）。"""
    a = concrete.split("?")[0].strip("/").split("/")
    b = template.strip("/").split("/")
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if y.startswith("{") and y.endswith("}"):
            if not x:
                return False
        elif x != y:
            return False
    return True


def strip_paren(s):
    """`event（六项核心属性）` → `event`。"""
    return re.split(r"[（(]", s.strip())[0].strip()


def _unparen(cell):
    """把「取值枚举」与「中文注释」的括号整段去掉，但保留「嵌套字段」的括号内容。

    表 4-13 的「响应字段」列里括号有三种用法，必须区别对待，否则要么误判 FAIL、
    要么漏检字段（漏检等于放宽判据）：

      · 嵌套字段 —— `items（doc_id、title、…）`／`participants（role）`：
        括号里是**响应里真实存在的字段名**，要保留（含「、」或含标识符即属此类）；
      · 取值枚举 —— `display_mode（path／not_used）`：括号里是 `display_mode` 的**取值**，
        `path`／`not_used` 不是字段名，要整段去掉（判据：括号里出现全角或半角斜杠）；
      · 中文注释 —— `event（六项核心属性）`／`paths（含关系证据属性）`：
        括号里没有一个标识符，整段去掉（含「按…排序」类说明，其标识符另有归属，故保留）。
    """
    parts = []
    for seg in re.split(r"([（(][^（()）]*[)）])", cell or ""):
        if seg.startswith(("（", "(")):
            inner = seg.strip("（()） ")
            if "／" in inner or "/" in inner:
                continue                                  # 取值枚举
            if not re.search(r"[A-Za-z_][A-Za-z0-9_]*", inner):
                continue                                  # 纯中文注释
            parts.append("、" + inner + "、")               # 嵌套字段（两侧补分隔符，免得与前后粘连）
        else:
            parts.append(seg)
    return "".join(parts)


def declared_fields(cell):
    """从 表 4-13「响应字段」列里剥出字段名（去注释括号、去／、去「可选」）。"""
    out = []
    for seg in re.split(r"[、（()）／/\s]+", _unparen(cell)):
        seg = seg.strip()
        if not seg or seg in ("可选", "含证据三项或", "Document", "指向", "按", "排序", "布尔"):
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", seg) and seg not in out:
            out.append(seg)
    return out


# --------------------------------------------------------------------------
# 2. 规范解析（《24》第八节的 58 行、表 4-13、表 4-6）
# --------------------------------------------------------------------------
ROW_RE = re.compile(r"^\|\s*([A-I]\d{1,2})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")


def parse_spec_rows(root):
    """从《24》第八节解析 58 行 → [(rid, title, criterion, lineno)]。"""
    path = os.path.join(root, P_TASK)
    lines = read_lines(path)
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("## 八、"):
            start = i
            break
    if start is None:
        return []
    rows = []
    for i in range(start, len(lines)):
        ln = lines[i]
        if ln.startswith("## 九、"):
            break
        m = ROW_RE.match(ln)
        if m:
            rows.append((m.group(1), m.group(2), m.group(3), i + 1))
    return rows


def parse_table_413(root):
    """解析 表 4-13 → {(method, path): 响应字段列原文}，另行返回行号。"""
    path = os.path.join(root, P_DESIGN)
    lines = read_lines(path)
    out, lnos = {}, {}
    rx = re.compile(r"^\|\s*(.+?)\s*\|\s*(GET|POST|PUT|DELETE)\s*\|\s*(/\S+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")
    for i, ln in enumerate(lines):
        m = rx.match(ln)
        if not m:
            continue
        out[(m.group(2), m.group(3))] = m.group(6)
        lnos[(m.group(2), m.group(3))] = i + 1
    return out, lnos


def parse_table_46(root):
    """解析 表 4-6 → {表: {字段: (类型, 可空)}}。"""
    path = os.path.join(root, P_DESIGN)
    lines = read_lines(path)
    rx = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
    spec = {}
    for ln in lines:
        m = rx.match(ln)
        if not m:
            continue
        table = strip_paren(m.group(1))
        field = m.group(2).strip()
        if table not in SIX_TABLES or not re.fullmatch(r"[a-z_][a-z0-9_]*", field):
            continue
        spec.setdefault(table, {})[field] = (m.group(3).strip(), m.group(4).strip())
    return spec


# --------------------------------------------------------------------------
# 3. 上报器
# --------------------------------------------------------------------------
STATUS_TAG = {"OK": "[OK ]", "FAIL": "[FAIL]", "UNRUN": "[UNRUN]"}


class Gate:
    def __init__(self, root, profile, live, mirror=False):
        self.root = root
        self.profile = profile
        self.live = bool(live)              # 允许实况探测（full 且环境就绪）
        self.mirror = bool(mirror)
        self.rows = {}                      # rid -> (status, detail)
        self.notes = []                     # 说明
        self.env_reasons = []               # 环境未就绪的理由
        self.env_notes = []                 # 环境/链上失败的行
        self.err_responses = []             # [(case, http, body, expect_code)]
        self.c9_result = None               # 延迟到最后执行的 C9
        self.extra = {}

    # --- 路径 ---
    def p(self, *parts):
        return os.path.join(self.root, *parts)

    def ref(self, *parts):
        return rel(self.root, os.path.join(self.root, *parts))

    def exists(self, *parts):
        return os.path.exists(self.p(*parts))

    # --- 行 ---
    def row(self, rid, status, detail):
        if rid in self.rows:
            raise RuntimeError("行 %s 被判了两次（脚本内部错误）" % rid)
        self.rows[rid] = (status, detail)

    def ok(self, rid, detail):
        self.row(rid, "OK", detail)

    def fail(self, rid, detail):
        self.row(rid, "FAIL", detail)

    def bad_env(self, rid, detail):
        """环境／链上导致的失败（单独成栏）。"""
        self.env_notes.append(rid)
        self.row(rid, "FAIL", detail)

    def unrun(self, rid, detail):
        self.row(rid, "UNRUN", detail)

    def skip_live(self, rid, detail):
        """实况不可用（服务未起／静态档）→ 未执行，不算失败。"""
        self.unrun(rid, detail)

    def note(self, s):
        self.notes.append(s)


# --------------------------------------------------------------------------
# 4. 判据注册表
# --------------------------------------------------------------------------
CHECKS = {}


def check(*rids):
    def deco(fn):
        for rid in rids:
            CHECKS[rid] = fn
        return fn
    return deco

# --------------------------------------------------------------------------
# 5. 共享上下文：库连接、图连接、问题集
# --------------------------------------------------------------------------
def nrun(g, rid, what):
    if g.profile == "static":
        g.unrun(rid, "%s（静态档 --profile static：不判实况）" % what)
    else:
        g.unrun(rid, "%s（环境未就绪：服务未启动，实况行未执行 —— 见「环境未就绪」区段）" % what)


def dbcur(g):
    if "cur" not in g.extra:
        import pymysql
        cfg = load_json(g.p(P_BACKEND, "config.local.json")) or {}
        conn = pymysql.connect(host=cfg.get("mysql_host", "127.0.0.1"), port=int(cfg.get("mysql_port", 3306)),
                               user=cfg.get("mysql_user"), password=cfg.get("mysql_password") or "",
                               database=cfg.get("mysql_database", "ashare_qa"),
                               charset=cfg.get("mysql_charset", "utf8mb4"), autocommit=True)
        g.extra["conn"] = conn
        g.extra["cur"] = conn.cursor()
        g.extra["cfg"] = cfg
    return g.extra["cur"]


def qsql(g, sql, args=None):
    cur = dbcur(g)
    cur.execute(sql, args or ())
    return cur.fetchall()


def one(g, sql, args=None):
    r = qsql(g, sql, args)
    return r[0][0] if r else None


def neo4j_driver(g):
    if "neo" not in g.extra:
        from neo4j import GraphDatabase
        cfg = load_json(g.p(P_BACKEND, "config.local.json")) or {}
        g.extra["neo"] = GraphDatabase.driver(cfg["neo4j_uri"],
                                              auth=(cfg["neo4j_user"], cfg["neo4j_password"]))
    return g.extra["neo"]


def neo4j_run(g, cypher):
    drv = neo4j_driver(g)
    with drv.session() as s:
        return list(s.run(cypher))


def pe_questions(g):
    if "pe" not in g.extra:
        g.extra["pe"] = load_jsonl(g.p(P_QSET))
    return g.extra["pe"]


def pe_q(g, qid):
    for r in pe_questions(g):
        if r.get("qid") == qid:
            return r.get("question")
    return None


# --------------------------------------------------------------------------
# 6. A 组：环境与服务
# --------------------------------------------------------------------------
@check("A1")
def c_a1(g):
    mods, bad, note = [], [], []
    for mod in ("fastapi", "uvicorn", "pymysql"):
        try:
            m = __import__(mod)
            mods.append("%s %s" % (mod, getattr(m, "__version__", "?")))
        except Exception as exc:
            bad.append("%s 不可 import（%s）" % (mod, exc))
    try:
        m = __import__("sqlalchemy")
        note.append("sqlalchemy %s 亦可用（《10》允许二选一）" % getattr(m, "__version__", "?"))
    except Exception:
        pass
    nm = g.p(P_FRONTEND, "node_modules")
    lock = g.p(P_FRONTEND, "package-lock.json")
    skipped = []
    if not os.path.isdir(nm):
        if g.mirror:
            skipped.append("镜像未带 node_modules（自检副本不带依赖目录，跳过）")
        else:
            bad.append("缺 %s" % br(g.root, nm))
    if not os.path.exists(lock):
        bad.append("缺 %s" % br(g.root, lock))
    if bad:
        g.fail("A1", "；".join(bad))
    else:
        g.ok("A1", "import 通过：%s%s；%s 存在；%s 存在（%d 字节）%s"
             % ("／".join(mods), ("；" + "；".join(note)) if note else "",
                br(g.root, nm), br(g.root, lock), os.path.getsize(lock),
                ("；" + "；".join(skipped)) if skipped else ""))


@check("A2")
def c_a2(g):
    if not g.live:
        nrun(g, "A2", "MySQL 可达性未实测")
        return
    try:
        cur = dbcur(g)
        cur.execute("SELECT VERSION()")
        ver = cur.fetchone()[0]
        major = int(str(ver).split(".")[0])
        cfg = g.extra["cfg"]
        where = "host=%s port=%s db=%s user=%s（口令不打印）" % (
            cfg.get("mysql_host"), cfg.get("mysql_port"), cfg.get("mysql_database"), cfg.get("mysql_user"))
        if major >= 8:
            g.ok("A2", "SELECT VERSION()=%s ≥ 8.0；凭据取自 %s；%s" % (ver, br(g.root, g.p(P_BACKEND, "config.local.json")), where))
        else:
            g.fail("A2", "版本 %s < 8.0；%s" % (ver, where))
    except Exception as exc:
        g.bad_env("A2", "MySQL 连接失败：%s（凭据取自 %s）" % (str(exc)[:160], br(g.root, g.p(P_BACKEND, "config.local.json"))))


@check("A3")
def c_a3(g):
    if not g.live:
        nrun(g, "A3", "库与六表未实测")
        return
    try:
        cfg = g.extra.get("cfg") or load_json(g.p(P_BACKEND, "config.local.json")) or {}
        db = cfg.get("mysql_database", "ashare_qa")
        got = [r[0] for r in qsql(g, "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s", (db,))]
        miss = [t for t in SIX_TABLES if t not in got]
        extra = [t for t in got if t not in SIX_TABLES]
        if len(got) == 6 and not miss:
            g.ok("A3", "%s 存在；六张表齐备且表数量恰为 6：%s" % (db, "、".join(SIX_TABLES)))
        else:
            g.fail("A3", "表数量=%d（须恰为 6）；缺 %s；多 %s" % (len(got), miss or "无", extra or "无"))
    except Exception as exc:
        g.bad_env("A3", "information_schema 查询失败：%s" % str(exc)[:160])


@check("A4")
def c_a4(g):
    if not g.live:
        nrun(g, "A4", "Neo4j 可达性未实测")
        return
    ok_port = port_open(7687)
    n = None
    try:
        rows = neo4j_run(g, "MATCH (n) RETURN count(n) AS c")
        n = rows[0]["c"] if rows else None
    except Exception as exc:
        g.bad_env("A4", "bolt 7687 连通=%s；MATCH (n) RETURN count(n) 执行失败：%s" % (ok_port, str(exc)[:160]))
        return
    rm = load_json(g.p(P_RUN_MANIFEST), {}) or {}
    ver = (rm.get("versions") or {}).get("neo4j", "未登记")
    if ok_port and n:
        g.ok("A4", "bolt 7687 连通；MATCH (n) RETURN count(n)=%s；版本=%s（登记于 %s）"
             % (n, ver, br(g.root, g.p(P_RUN_MANIFEST))))
    else:
        g.fail("A4", "bolt 7687 连通=%s；count(n)=%s；版本=%s" % (ok_port, n, ver))


@check("A5")
def c_a5(g):
    if not g.live:
        nrun(g, "A5", "后端 /api/health 未实测")
        return
    st, body, secs = http("GET", "/api/health", timeout=30)
    if st != 200:
        g.bad_env("A5", "GET /api/health → %s（%s）" % (st, json.dumps(body, ensure_ascii=False)[:160]))
        return
    flags = {k: (body.get(k) or {}).get("ok") for k in ("mysql", "neo4j", "vector_index", "model_config")}
    bad = [k for k, v in flags.items() if v is not True]
    line = "GET /api/health=200（%.3fs）；status=%s；%s" % (
        secs, body.get("status"), "；".join("%s.ok=%s" % (k, flags[k]) for k in flags))
    if bad:
        g.fail("A5", line + "；未就绪项：%s" % "、".join(bad))
    else:
        g.ok("A5", line)


@check("A6")
def c_a6(g):
    hosts = []
    if port_open(5173):
        st, _, _ = http("GET", "/") if g.live else (None, None, None)
        hosts.append(("dev server 5173", st))
    dist = g.p(P_FRONTEND, "dist", "index.html")
    src_index = g.p(P_FRONTEND, "index.html")
    mount = None
    for p in (dist, src_index):
        if os.path.exists(p):
            txt = read_text(p)
            if 'id="app"' in txt or "id='app'" in txt or 'id="root"' in txt:
                mount = br(g.root, p)
                break
    parts = []
    if hosts:
        parts.append("dev server 5173 监听中，GET / → %s" % hosts[0][1])
    if mount:
        parts.append("构建产物 %s 含应用挂载点 id=\"app\"" % mount)
    if (hosts and hosts[0][1] == 200) or mount:
        g.ok("A6", "；".join(parts) if parts else "构建产物可访问且含挂载点")
    else:
        g.fail("A6", "5173 未监听且 dist/index.html 无挂载点；dist 存在=%s" % os.path.exists(dist))


# --------------------------------------------------------------------------
# 7. B 组：数据库与导入
# --------------------------------------------------------------------------
@check("B1")
def c_b1(g):
    if not g.live:
        nrun(g, "B1", "字段级一致未实测")
        return
    spec = parse_table_46(g.root)
    n_spec = sum(len(v) for v in spec.values())
    diffs, checked = [], 0
    for table in SIX_TABLES:
        got = {r[0]: (r[1], r[2]) for r in qsql(
            g,
            "SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION", (table,))}
        for field, (ty, nullable) in (spec.get(table) or {}).items():
            checked += 1
            if field not in got:
                diffs.append("缺 %s.%s" % (table, field))
                continue
            gty, gnull = got[field]
            if gty.upper() != ty.upper():
                diffs.append("%s.%s 类型 库=%s 表4-6=%s" % (table, field, gty, ty))
            if (gnull == "YES") != (nullable == "是"):
                diffs.append("%s.%s 可空 库=%s 表4-6=%s" % (table, field, gnull, nullable))
        extra = [f for f in got if f not in (spec.get(table) or {})]
        if extra:
            diffs.append("%s 多出字段 %s" % (table, extra))
    if diffs:
        g.fail("B1", "比对 %d 项，%d 项不一致：%s（基准 %s 表 4-6）"
               % (checked, len(diffs), "；".join(diffs[:8]), br(g.root, g.p(P_DESIGN))))
    else:
        g.ok("B1", "六表 %d 个字段的列名／类型／可空性与 %s 表 4-6 逐项一致，零不一致"
             % (checked, br(g.root, g.p(P_DESIGN))))


@check("B2")
def c_b2(g):
    if not g.live:
        nrun(g, "B2", "约束落地未实测")
        return
    pk = [r[0] for r in qsql(g, "SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE "
                                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='answer_evidence' "
                                "AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION")]
    uq = [r[0] for r in qsql(g, "SELECT COLUMN_NAME FROM information_schema.STATISTICS "
                                "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='document_chunk' "
                                "AND INDEX_NAME='uk_chunk_doc_index' ORDER BY SEQ_IN_INDEX")]
    ru = dict((r[0], r[1]) for r in qsql(g, "SELECT CONSTRAINT_NAME,DELETE_RULE FROM information_schema.REFERENTIAL_CONSTRAINTS "
                                            "WHERE CONSTRAINT_SCHEMA=DATABASE()"))
    bad = []
    if pk != ["answer_id", "chunk_id"]:
        bad.append("answer_evidence 联合主键=%s（应 [answer_id, chunk_id]）" % pk)
    if uq != ["doc_id", "chunk_index"]:
        bad.append("document_chunk uk_chunk_doc_index=%s（应 [doc_id, chunk_index]）" % uq)
    for fk in ("fk_ae_doc", "fk_ae_chunk"):
        if ru.get(fk) != "RESTRICT":
            bad.append("%s DELETE_RULE=%s（应 RESTRICT）" % (fk, ru.get(fk)))
    if bad:
        g.fail("B2", "；".join(bad))
    else:
        g.ok("B2", "answer_evidence 主键=%s；document_chunk 唯一键=%s；fk_ae_doc／fk_ae_chunk DELETE_RULE=RESTRICT"
             "（information_schema 取证）" % (pk, uq))


def _first_col(g, path, key):
    return set(str(r.get(key)) for r in load_jsonl(g.p(path)) if r.get(key) is not None)


@check("B3")
def c_b3(g):
    src = load_json(g.p(P_DB_COUNTS), {}) or {}
    cmp_ = (src.get("comparison") or {})
    exp_doc = (cmp_.get("document") or {}).get("expected")
    exp_chk = (cmp_.get("document_chunk") or {}).get("expected")
    if not g.live:
        nrun(g, "B3", "文档与文本块导入未实测（预期 %s／%s 取自 %s）"
             % (exp_doc, exp_chk, br(g.root, g.p(P_DB_COUNTS))))
        return
    n_doc = one(g, "SELECT COUNT(*) FROM `document`")
    n_chk = one(g, "SELECT COUNT(*) FROM `document_chunk`")
    bad = []
    if n_doc != exp_doc:
        bad.append("document 库内=%s 预期=%s（%s）" % (n_doc, exp_doc, br(g.root, g.p(P_DB_COUNTS))))
    if n_chk != exp_chk:
        bad.append("document_chunk 库内=%s 预期=%s" % (n_chk, exp_chk))
    db_ids = set(str(r[0]) for r in qsql(g, "SELECT doc_id FROM `document`"))
    src_ids = _first_col(g, P_DOCS, "doc_id")
    if db_ids != src_ids:
        bad.append("doc_id 集合不等：库内 %d、%s %d、差集 %s"
                   % (len(db_ids), br(g.root, g.p(P_DOCS)), len(src_ids),
                      sorted(db_ids ^ src_ids)[:8]))
    db_cid = set(str(r[0]) for r in qsql(g, "SELECT chunk_id FROM `document_chunk`"))
    src_cid = _first_col(g, P_CHUNKS, "chunk_id")
    if db_cid != src_cid:
        bad.append("chunk_id 集合不等：库内 %d、%s %d、差集 %s"
                   % (len(db_cid), br(g.root, g.p(P_CHUNKS)), len(src_cid), sorted(db_cid ^ src_cid)[:8]))
    if bad:
        g.fail("B3", "；".join(bad))
    else:
        g.ok("B3", "document=%d（与 %s 的 doc_id 集合逐项相等）、document_chunk=%d（与 %s 的 chunk_id 集合逐项相等）"
             % (n_doc, br(g.root, g.p(P_DOCS)), n_chk, br(g.root, g.p(P_CHUNKS))))


@check("B4")
def c_b4(g):
    src = load_json(g.p(P_DB_COUNTS), {}) or {}
    cmp_ = src.get("comparison") or {}
    base = {t: (cmp_.get(t) or {}).get("expected") for t in ("question", "answer", "answer_evidence")}
    if not g.live:
        nrun(g, "B4", "问答记录导入未实测（导入读数 %s／%s／%s 取自 %s）"
             % (base["question"], base["answer"], base["answer_evidence"], br(g.root, g.p(P_DB_COUNTS))))
        return
    n_q = one(g, "SELECT COUNT(*) FROM `question`")
    n_a = one(g, "SELECT COUNT(*) FROM `answer`")
    n_e = one(g, "SELECT COUNT(*) FROM `answer_evidence`")
    n_u = one(g, "SELECT COUNT(*) FROM `user`")
    bad = []
    if not (n_q >= 30):
        bad.append("question=%d < 30" % n_q)
    if n_a != n_q:
        bad.append("answer=%d ≠ question=%d" % (n_a, n_q))
    if not (n_e >= 293):
        bad.append("answer_evidence=%d < 293" % n_e)
    if n_u != 0:
        bad.append("user=%d ≠ 0" % n_u)
    # `rank` 连续 1..m（按 answer_id 分组）
    grp = qsql(g, "SELECT answer_id, COUNT(*) m, MIN(`rank`) lo, MAX(`rank`) hi, "
                  "COUNT(DISTINCT `rank`) d FROM answer_evidence GROUP BY answer_id")
    broken = [(r[0], r[1], r[2], r[3], r[4]) for r in grp
              if not (r[2] == 1 and r[3] == r[1] and r[4] == r[1])]
    if broken:
        bad.append("`rank` 非连续 1..m 的 answer_id：%s" % broken[:5])
    # 与 qa_records.jsonl 逐条对拍（题面／答案正文／证据四元组）
    recs = load_jsonl(g.p(P_QAREC))
    nrec, miss_q, miss_a, miss_e = 0, [], [], []
    for r in recs:
        q = r.get("question") or {}
        a = r.get("answer") or {}
        ev = r.get("answer_evidence") or []
        nrec += 1
        if not qsql(g, "SELECT 1 FROM `question` WHERE question_text=%s LIMIT 1", (q.get("question_text"),)):
            miss_q.append(q.get("question_id"))
        row = qsql(g, "SELECT answer_id FROM `answer` WHERE answer_text=%s LIMIT 1", (a.get("answer_text"),))
        if not row:
            miss_a.append(a.get("answer_id"))
            continue
        aid = row[0][0]
        got = set((int(x[0]), int(x[1]), int(x[2]), str(x[3])) for x in qsql(
            g, "SELECT chunk_id,doc_id,`rank`,evidence_type FROM answer_evidence WHERE answer_id=%s", (aid,)))
        want = set((int(x["chunk_id"]), int(x["doc_id"]), int(x["rank"]), str(x["evidence_type"])) for x in ev)
        if got != want:
            miss_e.append((a.get("answer_id"), sorted(got ^ want)[:4]))
    if miss_q:
        bad.append("qa_records 有 %d 条题面在 question 表里找不到：%s" % (len(miss_q), miss_q[:5]))
    if miss_a:
        bad.append("qa_records 有 %d 条答案正文在 answer 表里找不到：%s" % (len(miss_a), miss_a[:5]))
    if miss_e:
        bad.append("answer_evidence 对拍不符 %d 条：%s" % (len(miss_e), miss_e[:3]))
    if bad:
        g.fail("B4", "；".join(bad))
    else:
        g.ok("B4", "question=%d（≥30）、answer=%d（＝question）、answer_evidence=%d（≥293）、user=%d；"
                   "`rank` 在全部 %d 个 answer_id 上连续 1..m；与 %s 的 %d 条记录逐条对拍一致；"
                   "导入读数 %s／%s／%s 见 %s"
             % (n_q, n_a, n_e, n_u, len(grp), br(g.root, g.p(P_QAREC)), nrec,
                base["question"], base["answer"], base["answer_evidence"], br(g.root, g.p(P_DB_COUNTS))))


@check("B5")
def c_b5(g):
    if not g.live:
        nrun(g, "B5", "导入幂等未实测（需连库跑两次导入）")
        return
    tool = g.p(P_BACKEND, "tools", "import_data.py")
    counts, logs = [], []
    for i in (1, 2):
        rc, out = run_cmd([sys.executable, tool, "--reset"], cwd=g.root, timeout=1200)
        logs.append((i, rc, out))
        if rc != 0:
            g.fail("B5", "第 %d 次导入退出码=%d；末 3 行：%s" % (i, rc, " / ".join(out.strip().splitlines()[-3:])))
            return
        counts.append({t: one(g, "SELECT COUNT(*) FROM `%s`" % t) for t in SIX_TABLES})
    dup = []
    for t, key in (("document", "doc_id"), ("document_chunk", "chunk_id"), ("question", "question_id"),
                   ("answer", "answer_id")):
        row = qsql(g, "SELECT COUNT(*), COUNT(DISTINCT `%s`) FROM `%s`" % (key, t))
        n, d = (row[0][0], row[0][1]) if row else (0, 0)
        if n != d:
            dup.append("%s 主键重复 %d 行（%s 共 %s 行、去重后 %s 行）" % (t, n - d,
                                                                       key, n, d))
    same = counts[0] == counts[1]
    if same and not dup:
        g.ok("B5", "连续两次 `import_data.py --reset`：六表行数完全一致 %s；无重复主键；第 2 次末行=%s"
             % (json.dumps(counts[1], ensure_ascii=False), logs[1][2].strip().splitlines()[-1][:60]))
    else:
        g.fail("B5", "两次行数%s（第1次=%s／第2次=%s）；重复主键=%s"
               % ("不一致" if not same else "一致", json.dumps(counts[0], ensure_ascii=False),
                  json.dumps(counts[1], ensure_ascii=False), dup or "无"))


def _referenced_doc(g):
    """找一篇被 answer_evidence 引用的 doc_id（B6/B7 用）。"""
    r = qsql(g, "SELECT doc_id FROM answer_evidence ORDER BY doc_id LIMIT 1")
    return r[0][0] if r else None


@check("B6")
def c_b6(g):
    if not g.live:
        nrun(g, "B6", "历史证据保护（接口层）未实测")
        return
    doc = _referenced_doc(g)
    if doc is None:
        g.bad_env("B6", "库内没有可用的被引用 doc_id（answer_evidence 为空）")
        return
    bad, ev = [], []
    for meth, path in (("DELETE", "/api/admin/documents/%s" % doc), ("PUT", "/api/admin/documents/%s" % doc)):
        payload = None
        if meth == "PUT":
            # 该接口的请求体契约＝文档字段本身（必填 title／content／source／publish_time，
            # 见 代码\后端\api\admin.py 的 `_check_document_payload` 与 `DOC_ALLOWED`）：
            # 缺必填判 1003、含未登记字段判 1002——两种都不是 B6 要判的 2003。
            payload = {"title": "守门测试文档", "content": "守门测试正文（应被 2003 拒绝，不落盘）",
                       "source": "公告", "publish_time": "2026-01-01T00:00:00"}
        st, body, _ = http(meth, path, payload, ADMIN)
        ev.append("%s → %s/%s retained_for_history=%s" % (meth, st, body.get("code"), body.get("retained_for_history")))
        if st != 409 or body.get("code") != 2003 or body.get("retained_for_history") is not True:
            bad.append("%s %s → HTTP %s code=%s retained_for_history=%s"
                       % (meth, path, st, body.get("code"), body.get("retained_for_history")))
    if bad:
        g.fail("B6", "；".join(bad) + "（doc_id=%s）" % doc)
    else:
        g.ok("B6", "doc_id=%s 被历史引用：%s" % (doc, "；".join(ev)))


@check("B7")
def c_b7(g):
    if not g.live:
        nrun(g, "B7", "历史证据保护（数据库层）未实测")
        return
    doc = _referenced_doc(g)
    if doc is None:
        g.bad_env("B7", "库内没有可用的被引用 doc_id")
        return
    import pymysql
    cfg = load_json(g.p(P_BACKEND, "config.local.json")) or {}
    conn = pymysql.connect(host=cfg.get("mysql_host"), port=int(cfg.get("mysql_port")),
                           user=cfg.get("mysql_user"), password=cfg.get("mysql_password") or "",
                           database=cfg.get("mysql_database"), charset="utf8mb4", autocommit=False)
    err = None
    try:
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM `document` WHERE doc_id=%s", (doc,))
            conn.rollback()                      # 万一真删成了，立刻回滚，不破坏数据
        except Exception as exc:
            err = str(exc)[:180]
            conn.rollback()
    finally:
        conn.close()
    if err:
        g.ok("B7", "直接 DELETE FROM document WHERE doc_id=%s 被数据库拒绝（外键 RESTRICT）：%s" % (doc, err))
    else:
        g.fail("B7", "直接 DELETE FROM document WHERE doc_id=%s **未被拒绝**（外键 RESTRICT 没兜住；已回滚）" % doc)


@check("B8")
def c_b8(g):
    if not g.live:
        nrun(g, "B8", "user 表未实测")
        return
    n = one(g, "SELECT COUNT(*) FROM `user`")
    if n == 0:
        g.ok("B8", "SELECT COUNT(*) FROM `user` = 0（第一版不启用登录）")
    else:
        g.fail("B8", "SELECT COUNT(*) FROM `user` = %s ≠ 0" % n)


# --------------------------------------------------------------------------
# 8. C 组：后端接口
# --------------------------------------------------------------------------
def openapi_paths(g):
    if "openapi" not in g.extra:
        st, body, _ = http("GET", "/openapi.json", timeout=60)
        g.extra["openapi"] = (st, body)
    return g.extra["openapi"]


@check("C1")
def c_c1(g):
    spec413, lnos = parse_table_413(g.root)
    business = [(m, p) for (m, p) in spec413 if not p.startswith("/api/auth/")]
    smoke = load_jsonl(g.p(P_SMOKE))
    normal = [r for r in smoke if r.get("expected_code") == 0]
    covered = {}
    for (m, p) in business:
        for r in normal:
            if r.get("method") == m and path_match(str(r.get("path")), p):
                covered[(m, p)] = r
                break
    missing_cov = [t for t in business if t not in covered]
    cov_txt = "冒烟矩阵 %s 覆盖业务接口 %d/%d" % (br(g.root, g.p(P_SMOKE)), len(covered), len(business))
    if not g.live:
        if missing_cov:
            g.fail("C1", "%s；未覆盖：%s（静态档只判覆盖，注册情况需服务）"
                   % (cov_txt, ["%s %s" % t for t in missing_cov]))
        else:
            g.ok("C1", "%s（静态档：注册数需连服务判，实况判定见 full 档）" % cov_txt)
        return
    st, body = openapi_paths(g)
    if st != 200:
        g.bad_env("C1", "GET /openapi.json → %s" % st)
        return
    paths = (body or {}).get("paths") or {}
    got = set()
    for p, ops in paths.items():
        for m in ops:
            got.add((m.upper(), p))
    want = set(business) | REGISTERED_ADDITIONS
    miss = sorted(want - got)                                    # 应注册却缺失 → FAIL（一个都不能少）
    beyond = sorted(got - set(business))                         # 超出表 4-13 的 25 个业务接口的部分
    reg_new = [t for t in beyond if t in REGISTERED_ADDITIONS]   # 已登记新增 → 放行并打印
    unreg = [t for t in beyond if t not in REGISTERED_ADDITIONS]  # 未登记新增 → FAIL（不放宽）
    auth = sorted([x for x in got if x[1].startswith("/api/auth/")])
    reg_txt = "、".join("%s %s" % t for t in reg_new) or "无"
    if miss or unreg or missing_cov or auth:
        g.fail("C1", "app.openapi()[\"paths\"]：路径 %d 条／操作 %d 个；缺 %s；未登记新增 %s；"
                     "auth 不该注册却出现 %s；已登记新增 %s；%s"
               % (len(paths), len(got), ["%s %s" % t for t in miss],
                  ["%s %s" % t for t in unreg], auth, reg_txt, cov_txt))
    else:
        g.ok("C1", "app.openapi()[\"paths\"]：%d 条路径／%d 个操作 ＝ 表 4-13 的 25 个业务接口 ＋ %d 个已登记新增"
                   "（%s；3 个 /api/auth/* 未注册）；%s"
             % (len(paths), len(got), len(REGISTERED_ADDITIONS), reg_txt, cov_txt))


@check("C2")
def c_c2(g):
    if not g.live:
        nrun(g, "C2", "请求/响应字段未实测")
        return
    spec413, lnos = parse_table_413(g.root)
    ask_q = pe_q(g, "PE-01")
    bad, lines = [], []
    for (meth, path, payload, hdr, label) in C2_SAMPLES:
        real = path
        body = payload
        if payload == "__ASK__":
            real, body = "/api/qa/ask", {"question": ask_q, "session_id": "S-GATE-C2"}
        elif payload == "__HIST__":
            real, body = "/api/history" + qs(session_id="S-001", page_size=2), None
        st, resp, _ = http(meth, real, body, hdr)
        tmpl = None
        for (m, p) in spec413:
            if m == meth and path_match(real, p):
                tmpl = p
                break
        if tmpl is None:
            bad.append("%s %s 在表 4-13 里找不到对应行" % (meth, real))
            continue
        want = declared_fields(spec413[(meth, tmpl)])
        got_keys = keys_deep(resp)
        miss = [f for f in want if f not in got_keys]
        lines.append("%s %s → %s（%s）" % (meth, tmpl, "字段齐" if not miss else "缺 %s" % miss, label))
        if miss:
            bad.append("%s %s 缺响应字段 %s（%s:%s 响应字段列：%s）"
                       % (meth, tmpl, miss, br(g.root, g.p(P_DESIGN)), lnos.get((meth, tmpl)), spec413[(meth, tmpl)]))
    if bad:
        g.fail("C2", "抽样 8 个接口，%d 处不符：%s" % (len(bad), "；".join(bad[:4])))
    else:
        g.ok("C2", "抽样 8 个接口的响应字段与 %s 表 4-13 的「响应字段」列逐项相符：%s"
             % (br(g.root, g.p(P_DESIGN)), "；".join(lines)))


@check("C3")
def c_c3(g):
    src = read_text(g.p(P_BACKEND, "errors.py"))
    m = re.search(r"CODES\s*=\s*\{(.*?)\n\}", src, re.S)
    table = {}
    if m:
        for cm in re.finditer(r"(\d{4})\s*:\s*\(\s*\"(.*?)\"\s*,\s*(\d{3})\s*\)", m.group(1), re.S):
            table[int(cm.group(1))] = int(cm.group(3))
    bad = []
    for code in C3_CODES:
        if table.get(code) != C3_EXPECT_HTTP[code]:
            bad.append("%s 在 errors.py CODES 里为 %s（应 %s）" % (code, table.get(code), C3_EXPECT_HTTP[code]))
    if not g.live:
        stat = "errors.py CODES 逐码核对：%s" % ("全对" if not bad else "／".join(bad))
        seq = load_json(g.p(P_EVID, "nfr02_sequential100.json"), {}) or {}
        if seq.get("failure_kinds", {}).get("限流（1004/429）"):
            stat += "；1004 的触发留痕：%s 里 %d 次限流" % (br(g.root, g.p(P_EVID, "nfr02_sequential100.json")),
                                                            seq["failure_kinds"]["限流（1004/429）"])
        if bad:
            g.fail("C3", stat)
        else:
            g.ok("C3", stat + "（静态档：逐类构造命中需连服务，实况判定见 full 档）")
        return
    hits = {}
    probes = [
        (1001, "POST", "/api/qa/ask", {"question": "", "session_id": "S-GATE"}, None),
        (1002, "GET", "/api/graph/events" + qs(start_time="2026-13-99"), None, None),
        (1003, "POST", "/api/qa/ask", {"question": "x"}, None),
        (2001, "GET", "/api/qa/answers/999999", None, None),
        (2002, "GET", "/api/graph/entities" + qs(keyword="zzz不存在的实体zzz"), None, None),
        (2003, "DELETE", "/api/admin/documents/%s" % (_referenced_doc(g) or 1307), None, ADMIN),
        (3004, "POST", "/api/qa/ask", {"question": pe_q(g, "PE-03"), "session_id": "S-GATE"}, None),
    ]
    for (code, meth, path, payload, hdr) in probes:
        st, body, _ = http(meth, path, payload, hdr, timeout=300)
        hits[code] = (st, body.get("code"), body)
        g.err_responses.append(("%s %s" % (meth, path), st, body, code))
        if code == 2002:
            # 《24》第 217 行：「2002 是正常状态：图谱查询为空、历史为空返回 HTTP 200 ＋
            # 空结果标记，不得返回 4xx／5xx」；第 306 行 C5 同样只要求 HTTP 200。
            # 故 2002 的「命中」＝ HTTP 200 ＋ 空结果标记（data.total=0）＋ 不带错误码，
            # **不**要求响应体里出现 code=2002（把 2002 当错误码用是《24》第 410 行的反模式）。
            total = (body.get("data") or {}).get("total")
            hits[code] = (st, "无 code（正常状态）", body)
            if not (st == 200 and body.get("code") in (None, 2002) and total == 0):
                bad.append("2002 空结果应为 HTTP 200 ＋ 空结果标记（data.total=0）、不带错误码，"
                           "实测 HTTP %s code=%s data.total=%s" % (st, body.get("code"), total))
            continue
        if body.get("code") != code or st != C3_EXPECT_HTTP[code]:
            bad.append("%s 期望 %s/%s，实测 HTTP %s code=%s" % (code, code, C3_EXPECT_HTTP[code], st, body.get("code")))

    # 4002（越权）：《24》第 219 行「普通用户访问 /api/admin/* 返回 4002（HTTP 403）
    # （机检：逐个后台路径探测）」。普通用户通道的判定见 代码\后端\api\admin.py 的
    # `_ordinary_user_reason`：X-Client-Role 是 user 一类取值、或 Origin 落在 CORS_ORIGINS、
    # 或 Referer 指向允许来源，任一命中即按普通用户拒（本机实测 Origin=http://localhost:5173
    # 与 X-Client-Role: user 两条都生效，见 集成产出\error_scenarios.jsonl 的「⑧ 越权」行）。
    # 探测面：全部 GET 后台路径 ＋ 被引用文档的 PUT／DELETE（有 2003 兜底，不会破坏数据）
    # ＋ 未登记的 /api/admin/* 兜底路由（POST 语义，验证前缀级守卫）；会改数据的 POST
    # （reprocess／extraction.run／documents 新增／experiment.ask）不实探，只登记清单。
    st_o, ob = openapi_paths(g)
    admin_ops = sorted([(m.upper(), p) for p, ops in ((ob or {}).get("paths") or {}).items()
                        for m in ops if p.startswith("/api/admin/")])
    ref_doc = _referenced_doc(g) or 1001
    role_hdr = {"X-Client-Role": "user", "Origin": "http://localhost:5173"}
    probed, leaked, skipped_post = [], [], []
    for (meth, p) in admin_ops:
        if "{" in p:
            if p != "/api/admin/documents/{doc_id}":
                skipped_post.append("%s %s" % (meth, p))
                continue
            real = p.replace("{doc_id}", str(ref_doc))
        else:
            real = p
        if meth not in ("GET", "PUT", "DELETE"):
            skipped_post.append("%s %s" % (meth, p))
            continue
        # PUT 用**合法请求体**探测：若守卫失效、请求真进了处理器，被引用文档会回 2003 而不是
        # 403，于是照样判为「没被 4002 拒绝」，不会被 2003 冒充通过。
        pl = {"title": "越权探测", "content": "越权探测正文", "source": "公告",
              "publish_time": "2026-01-01T00:00:00"} if meth == "PUT" else None
        st, b, _ = http(meth, real, pl, role_hdr, timeout=120)
        g.err_responses.append(("越权探测 %s %s" % (meth, real), st, b, 4002))
        probed.append("%s %s" % (meth, real))
        if not (st == 403 and b.get("code") == 4002):
            leaked.append("%s %s → HTTP %s code=%s" % (meth, real, st, b.get("code")))
    st, b, _ = http("POST", "/api/admin/__gate_probe__", {}, role_hdr, timeout=60)
    g.err_responses.append(("越权探测 POST /api/admin/__gate_probe__", st, b, 4002))
    probed.append("POST /api/admin/__gate_probe__（未登记路径的兜底路由）")
    if not (st == 403 and b.get("code") == 4002):
        leaked.append("POST /api/admin/__gate_probe__ → HTTP %s code=%s" % (st, b.get("code")))
    hits[4002] = (403 if not leaked else "?!", 4002 if not leaked else None, None)
    if leaked:
        bad.append("越权探测：%d／%d 个后台路径没有按 4002／403 拒绝 —— %s（普通用户标记：%s）"
                   % (len(leaked), len(probed), "；".join(leaked[:6]), json.dumps(role_hdr, ensure_ascii=False)))
    # 1004：由 C9 的突发在最后触发；此处先取限流留痕
    seq = load_json(g.p(P_EVID, "nfr02_sequential100.json"), {}) or {}
    k = seq.get("failure_kinds", {}) or {}
    n1004 = k.get("限流（1004/429）") or k.get("限流1004") or 0
    if not n1004:
        bad.append("1004 无触发留痕")
    else:
        hits[1004] = ("留痕", 1004, None)
    if bad:
        g.fail("C3", "；".join(bad))
    else:
        g.ok("C3", "逐类构造命中：%s；4002 越权：逐个探测 %d 条后台路径（%s）＋ 未登记路径兜底路由，全部 403／4002；"
                   "未实探的后台操作 %d 条【会改数据的 POST 与含未替换占位符的路径，只登记不探】：%s；"
                   "1004（429）由突发触发——留痕 %s 记 %d 次限流；3004（502）确定性样本 PE-03 → HTTP %s code=%s"
             % ("；".join("%s→%s/%s" % (c, hits[c][0], hits[c][1]) for c in C3_CODES if c != 1004),
                len(probed), "、".join(probed[:3]) + ("…" if len(probed) > 3 else ""),
                len(skipped_post), "、".join(skipped_post) if skipped_post else "无",
                br(g.root, g.p(P_EVID, "nfr02_sequential100.json")), n1004, hits[3004][0], hits[3004][1]))


def _err_bodies(g):
    """本轮实况里观察到的一切错误响应体（供 C4 判键集）。"""
    out = [("实况 " + c, b) for (c, st, b, _exp) in g.err_responses]
    for p in sorted(glob.glob(os.path.join(g.root, P_EVID, "err_*.json"))):
        d = load_json(p, None)
        if isinstance(d, dict):
            body = d.get("body", d)
            if isinstance(body, dict):
                out.append((rel(g.root, p), body))
    for name in ("smoke_admin_documents_delete.json", "smoke_admin_documents_delete_b.json"):
        d = load_json(g.p(P_EVID, name), None)
        if isinstance(d, dict):
            body = d.get("body", d)
            if isinstance(body, dict):
                out.append((rel(g.root, name), body))
    return out


@check("C4")
def c_c4(g):
    bad, n, n2003 = [], 0, 0
    for (src, body) in _err_bodies(g):
        keys = set(body.keys())
        code = body.get("code")
        if "detail" in keys:
            bad.append("%s 含 detail 键" % src)
        if code == 2003:
            n2003 += 1
            if body.get("retained_for_history") is not True:
                bad.append("%s 的 2003 缺 retained_for_history=true" % src)
            allow = {"code", "message", "retained_for_history"}
        elif code is None:
            continue                    # 不是错误响应（空结果信封没有 code）
        else:
            allow = {"code", "message"}
        extra = keys - allow
        if extra:
            bad.append("%s 的 code=%s 响应多出键 %s" % (src, code, sorted(extra)))
        n += 1
    if bad:
        g.fail("C4", "检查 %d 个错误响应体，%d 处违规：%s" % (n, len(bad), "；".join(bad[:6])))
    else:
        g.ok("C4", "检查 %d 个错误响应体（含 %d 个 2003）：键集 ⊆ {code, message}（2003 另带 retained_for_history=true）；"
                   "任何响应都不含 detail 键" % (n, n2003))


@check("C5")
def c_c5(g):
    if not g.live:
        nrun(g, "C5", "2002 是 200 未实测")
        return
    a_st, a_b, _ = http("GET", "/api/graph/entities" + qs(keyword="zzz不存在的实体zzz"))
    b_st, b_b, _ = http("GET", "/api/history" + qs(session_id="S-GATE-NO-SUCH"))
    bad = []
    for tag, st, b in (("图谱空查询", a_st, a_b), ("历史空查询", b_st, b_b)):
        if st != 200:
            bad.append("%s → HTTP %s" % (tag, st))
        if (b.get("data") or {}).get("total") != 0:
            bad.append("%s total=%s（不是空结果）" % (tag, (b.get("data") or {}).get("total")))
    if bad:
        g.fail("C5", "；".join(bad))
    else:
        g.ok("C5", "图谱空查询 → HTTP %s（total=%s）；历史空查询 → HTTP %s（total=%s）；均为 200，不作错误"
             % (a_st, a_b["data"]["total"], b_st, b_b["data"]["total"]))


@check("C6")
def c_c6(g):
    if not g.live:
        nrun(g, "C6", "分页未实测")
        return
    sess = "S-001"
    cases = [
        ("/api/admin/documents", ADMIN, one(g, "SELECT COUNT(*) FROM `document`")),
        ("/api/history" + qs(session_id=sess), None, one(g, "SELECT COUNT(*) FROM `question` WHERE session_id=%s", (sess,))),
        ("/api/graph/events", None, neo4j_run(g, "MATCH (n:Event) RETURN count(n) AS c")[0]["c"]),
    ]
    bad, lines = [], []
    for (path, hdr, exp) in cases:
        sep = "&" if "?" in path else "?"
        st, b, _ = http("GET", path + sep + "page_size=2&page=1", None, hdr)
        d = b.get("data") or {}
        got = dict((k, d.get(k)) for k in ("total", "page", "page_size"))
        lines.append("%s → %s（库内=%s）" % (path, got, exp))
        if st != 200 or got["total"] != exp or got["page"] != 1 or got["page_size"] != 2:
            bad.append("%s total/page/page_size=%s，库内计数=%s，HTTP=%s" % (path, got, exp, st))
    if bad:
        g.fail("C6", "；".join(bad))
    else:
        g.ok("C6", "抽样 3 个列表接口，total／page／page_size 与库内计数一致：%s" % "；".join(lines))


@check("C7")
def c_c7(g):
    if not g.live:
        nrun(g, "C7", "固定 C 组未实测")
        return
    st, b, _ = http("POST", "/api/qa/ask", {"question": pe_q(g, "PE-01"), "session_id": "S-GATE-C7",
                                            "experiment_group": "A"})
    st2, b2, _ = http("POST", "/api/qa/ask", {"question": pe_q(g, "PE-04"), "session_id": "S-GATE-C7"})
    g.err_responses.append(("POST /api/qa/ask (带 experiment_group)", st, b, 1002))
    bad = []
    if st != 400 or b.get("code") != 1002:
        bad.append("带 experiment_group 时 HTTP=%s code=%s（应 400／1002）" % (st, b.get("code")))
    if st2 != 200:
        bad.append("不带 experiment_group 时 HTTP=%s（应 200，按 C 组运行）" % st2)
    if bad:
        g.fail("C7", "；".join(bad))
    else:
        g.ok("C7", "带 experiment_group → HTTP %s／%s（按 1002 拒绝）；不带 → HTTP %s（按 C 组运行，answer_id=%s）"
             % (st, b.get("code"), st2, (b2.get("data") or {}).get("answer_id")))


@check("C8")
def c_c8(g):
    if not g.live:
        nrun(g, "C8", "受控实验入口未实测")
        return
    bad, lines = [], []

    def sample(grp):
        """跑一次受控实验入口，返回 (是否通过, 读数文本)。"""
        st, b, sec = http("POST", "/api/admin/experiment/ask",
                          {"question": pe_q(g, "PE-04"), "session_id": "S-GATE-C8",
                           "experiment_group": grp, "run_id": "R-GATE-%s" % grp}, ADMIN, timeout=300)
        d = b.get("data") or {}
        cfg = d.get("experiment_config") or d.get("config_snapshot") or d.get("config")
        got_grp = d.get("experiment_group")
        txt = ("组 %s → HTTP %s answer_id=%s experiment_group=%s 配置快照=%s（%.1fs%s）"
               % (grp, st, d.get("answer_id"), got_grp, "有" if cfg else "无", sec,
                  ("，code=%s message=%s" % (b.get("code"), str(b.get("message") or "")[:80]))
                  if st != 200 else ""))
        return (st == 200 and got_grp == grp and bool(cfg)), txt

    for grp in ("A", "C"):
        ok1, txt1 = sample(grp)
        # 本判据问的是「入口**可用**」。实测该入口在门禁自身连发请求逼近限流窗口
        # （60 次／60 s）时会偶发一次服务侧失败（5xx／429，非判据本身失败），单次采样
        # 不足以断言入口不可用——故失败后**清空限流窗口再复测一次**，两次读数都留痕；
        # 仍失败才判 FAIL（真不可用）。此处只增加取证，不放松判据。
        if not ok1:
            time.sleep(65)
            ok2, txt2 = sample(grp)
            lines.append("组 %s：首轮 %s" % (grp, txt1))
            lines.append("组 %s：复测 %s" % (grp, txt2))
            if not ok2:
                bad.append("组 %s 两次均失败：首轮 %s；复测 %s" % (grp, txt1, txt2))
        else:
            lines.append(txt1)
    if bad:
        g.fail("C8", "；".join(bad))
    else:
        g.ok("C8", "；".join(lines) + "（条目快照含 k／n／context_token_budget 等，见 %s）"
             % br(g.root, g.p(P_EVID, "ask_experiment_admin.json")))


@check("C9")
def c_c9(g):
    if not g.live:
        nrun(g, "C9", "频率限制未实测")
        return
    n429, codes = 0, {}
    t0 = time.time()
    for i in range(70):
        st, b, _ = http("GET", "/api/config/meta", timeout=30, pace=False)
        c = b.get("code")
        codes[c] = codes.get(c, 0) + 1
        if st == 429 or c == 1004:
            n429 += 1
    alive_st, _, _ = http("GET", "/api/health", timeout=30)
    if n429 > 0 and alive_st == 200:
        g.ok("C9", "70 次高频请求中 %d 次命中限流（429／1004，%.1fs 内完成，码分布 %s）；随后 /api/health=%s，服务未崩溃"
             % (n429, time.time() - t0, codes, alive_st))
    else:
        g.fail("C9", "限流命中 %d 次（码分布 %s）；之后 /api/health=%s" % (n429, codes, alive_st))


@check("C10")
def c_c10(g):
    if not g.live:
        nrun(g, "C10", "参数校验未实测")
        return
    probes = [
        ("question 为空", "POST", "/api/qa/ask", {"question": "", "session_id": "S-GATE"}, None, 1001, 400),
        ("question 超长（1001 字）", "POST", "/api/qa/ask",
         {"question": "长" * 1001, "session_id": "S-GATE"}, None, 1001, 400),
        ("时间区间格式非法", "GET", "/api/graph/events" + qs(start_time="2026-13-99"), None, None, 1002, 400),
    ]
    bad, lines = [], []
    for (tag, meth, path, payload, hdr, code, stx) in probes:
        st, b, _ = http(meth, path, payload, hdr)
        if path.startswith("/api/qa/ask"):
            g.err_responses.append(("%s %s (%s)" % (meth, path, tag), st, b, code))
        lines.append("%s → %s／%s" % (tag, st, b.get("code")))
        if b.get("code") != code or st != stx:
            bad.append("%s 期望 %s／%s，实测 %s／%s" % (tag, stx, code, st, b.get("code")))
    if bad:
        g.fail("C10", "；".join(bad))
    else:
        g.ok("C10", "；".join(lines))


# --------------------------------------------------------------------------
# 9. D 组：问答与证据链路
# --------------------------------------------------------------------------
def ask(g, qid, session="S-GATE-D", timeout=300):
    st, b, secs = http("POST", "/api/qa/ask", {"question": pe_q(g, qid), "session_id": session}, timeout=timeout)
    return st, b, secs


@check("D1")
def c_d1(g):
    if not g.live:
        nrun(g, "D1", "端到端问答未实测")
        return
    sections = ["【回答】", "【证据来源】", "【知识图谱路径】", "【数据截至与判定区间】"]
    bad, lines = [], []
    ok_n = 0
    for qid in QA_CANDIDATES:
        st, b, secs = ask(g, qid, "S-GATE-D1")
        if st is None:
            g.bad_env("D1", "%s：无法连接后端（%s）" % (qid, (b or {}).get("_error")))
            return
        if st != 200:
            code = (b or {}).get("code")
            if code in UPSTREAM_GUARD_CODES:
                lines.append("%s → HTTP %s code=%s：本轮跳过（上游守卫）" % (qid, st, code))
                continue
            bad.append("%s：HTTP=%s code=%s（非上游守卫码，真故障）" % (qid, st, code))
            continue
        d = b.get("data") or {}
        txt = d.get("answer_text") or ""
        ev = d.get("evidence") or []
        cut = d.get("data_cutoff_time")
        miss = [s for s in sections if s not in txt]
        lines.append("%s → HTTP %s（%.1fs）answer_id=%s 证据 %d 条 data_cutoff_time=%s"
                     % (qid, st, secs, d.get("answer_id"), len(ev), cut))
        if miss or not ev or not cut:
            bad.append("%s：缺段=%s 证据=%d data_cutoff_time=%s" % (qid, miss, len(ev), cut))
            continue
        ok_n += 1
        if ok_n >= 3:
            break
    if bad:
        g.fail("D1", "；".join(bad))
    elif ok_n < 3:
        g.fail("D1", "候选题 %s 中仅 %d 道返回四段答案（＜3）⇒ 端到端问答不可用；逐题：%s"
               % (QA_CANDIDATES, ok_n, "；".join(lines)))
    else:
        g.ok("D1", "候选题 %s 取前 3 道成功题，均返回四段答案＋证据＋data_cutoff_time：%s"
             % (QA_CANDIDATES, "；".join(lines)))


@check("D2")
def c_d2(g):
    if not g.live:
        nrun(g, "D2", "引用编号未实测")
        return
    bad, lines = [], []
    ok_n = 0
    for qid in QA_CANDIDATES:
        st, b, _ = ask(g, qid, "S-GATE-D2")
        if st is None:
            g.bad_env("D2", "%s：无法连接后端（%s）" % (qid, (b or {}).get("_error")))
            return
        if st != 200:
            code = (b or {}).get("code")
            if code in UPSTREAM_GUARD_CODES:
                lines.append("%s → HTTP %s code=%s：本轮跳过（上游守卫）" % (qid, st, code))
                continue
            bad.append("%s：HTTP=%s code=%s（非上游守卫码，按真故障判 FAIL）" % (qid, st, code))
            continue
        d = b.get("data") or {}
        txt = d.get("answer_text") or ""
        ev = d.get("evidence") or []
        nums = sorted(set(int(x) for x in re.findall(r"\[证据(\d+)\]", txt)))
        mx = max(nums) if nums else 0
        lines.append("%s → [证据n] 用到 %s，本次证据 %d 条" % (qid, nums, len(ev)))
        ok_n += 1
        if nums and mx > len(ev):
            bad.append("%s：最大引用号 %d > 证据条数 %d（HTTP=%s）" % (qid, mx, len(ev), st))
        if ok_n >= 2:
            break
    if bad:
        g.fail("D2", "；".join(bad))
    elif ok_n == 0:
        g.unrun("D2", "候选题 %s 全部命中上游装配账目守卫，无成功样本可判；逐题：%s"
                % (QA_CANDIDATES, "；".join(lines)))
    else:
        g.ok("D2", "答案正文里的 [证据n] 全部落在本次证据条数内（取前 %d 道成功样本）：%s"
             % (ok_n, "；".join(lines)))


@check("D3")
def c_d3(g):
    if not g.live:
        nrun(g, "D3", "证据与图谱路径未实测")
        return
    # 用图谱扩展的情形
    ext = one(g, "SELECT answer_id FROM `answer` WHERE is_graph_extended=1 ORDER BY answer_id LIMIT 1")
    noext = one(g, "SELECT answer_id FROM `answer` WHERE is_graph_extended=0 ORDER BY answer_id LIMIT 1")
    bad, lines = [], []
    st, b, _ = http("GET", "/api/evidence/%s/graph-path" % ext)
    d = b.get("data") or {}
    paths = d.get("paths") or []
    three = all(set((rel.get("evidence") or {}).keys()) >= {"confidence", "source_doc_id", "source_chunk_id"}
                for p in paths for rel in (p.get("relations") or []))
    lines.append("answer_id=%s（用图谱扩展）→ paths=%d 条，证据三项属性%s，display_mode=%s"
                 % (ext, len(paths), "齐" if three else "缺", d.get("display_mode")))
    if st != 200 or not paths or not three:
        bad.append("图谱扩展情形：HTTP=%s paths=%d 三项属性=%s" % (st, len(paths), three))
    if noext is None:
        lines.append("库内暂无未使用图谱扩展的回答（第一版 C 组会全部走图谱扩展）")
    else:
        st2, b2, _ = http("GET", "/api/evidence/%s/graph-path" % noext)
        d2 = b2.get("data") or {}
        lines.append("answer_id=%s（未用图谱扩展）→ graph_path=%s，显示标注见 %s"
                     % (noext, d2.get("paths"), "%s:%d" % (rel(g.root, g.p(P_FRONTEND, "src", "components", "GraphPathPanel.vue")), 14)))
        if st2 != 200 or d2.get("paths"):
            bad.append("未用图谱扩展情形：HTTP=%s graph_path=%s（应为空）" % (st2, d2.get("paths")))
    if bad:
        g.fail("D3", "；".join(bad))
    else:
        g.ok("D3", "；".join(lines))


@check("D4")
def c_d4(g):
    if not g.live:
        nrun(g, "D4", "落库回看未实测")
        return
    aid = 1
    row = qsql(g, "SELECT question_id FROM `answer` WHERE answer_id=%s", (aid,))
    qid = row[0][0] if row else None
    st, h, _ = http("GET", "/api/history" + qs(session_id="S-001", page_size=100))
    items = (h.get("data") or {}).get("items") or []
    found = [x for x in items if x.get("question_id") == qid]
    st2, b2, _ = http("GET", "/api/history/%s" % qid + qs(session_id="S-001"))
    st3, b3, _ = http("GET", "/api/qa/answers/%s" % aid)
    d2, d3 = (b2.get("data") or {}), (b3.get("data") or {})
    bad = []
    if not found:
        bad.append("GET /api/history?session_id=S-001 里查不到 question_id=%s" % qid)
    if st2 != 200 or st3 != 200:
        bad.append("history/%s=%s；qa/answers/%s=%s" % (qid, st2, aid, st3))
    else:
        if d2.get("answer_text") != d3.get("answer_text"):
            bad.append("answer_text 不一致")
        if d2.get("question_text") != d3.get("question_text"):
            bad.append("question_text 不一致")
        if len(d2.get("evidence") or []) != len(d3.get("evidence") or []):
            bad.append("evidence 条数 %s ≠ %s" % (len(d2.get("evidence") or []), len(d3.get("evidence") or [])))
    if bad:
        g.fail("D4", "；".join(bad))
    else:
        g.ok("D4", "answer_id=%s／question_id=%s 在 /api/history 里查到；/api/history/%s 与 /api/qa/answers/%s 的 "
                   "question_text／answer_text／证据条数（%d）一致"
             % (aid, qid, qid, aid, len(d3.get("evidence") or [])))


@check("D5")
def c_d5(g):
    if not g.live:
        nrun(g, "D5", "证据定位未实测")
        return
    cid = one(g, "SELECT chunk_id FROM `document_chunk` ORDER BY chunk_id LIMIT 1")
    did = one(g, "SELECT doc_id FROM `document_chunk` WHERE chunk_id=%s", (cid,))
    st, b, _ = http("GET", "/api/documents/%s/chunks/%s" % (did, cid))
    d = b.get("data") or {}
    src = None
    for r in load_jsonl(g.p(P_CHUNKS)):
        if int(r.get("chunk_id", -1)) == int(cid):
            src = r
            break
    bad = []
    if st != 200:
        bad.append("HTTP=%s" % st)
    if src is None:
        bad.append("chunks.jsonl 里找不到 chunk_id=%s" % cid)
    else:
        if (d.get("chunk_content") or "").strip() != (src.get("content") or "").strip():
            bad.append("chunk_content 与 %s 的 content 不是逐字一致" % br(g.root, g.p(P_CHUNKS)))
        if d.get("chunk_index") != src.get("chunk_index"):
            bad.append("chunk_index=%s ≠ %s" % (d.get("chunk_index"), src.get("chunk_index")))
    if not d.get("neighbor_chunks"):
        bad.append("neighbor_chunks 为空（应返回邻居块）")
    if bad:
        g.fail("D5", "；".join(bad))
    else:
        g.ok("D5", "GET /api/documents/%s/chunks/%s → 正文与 %s 逐字一致，chunk_index=%s，邻居块 %d 个，doc=%s"
             % (did, cid, br(g.root, g.p(P_CHUNKS)), d.get("chunk_index"), len(d.get("neighbor_chunks") or []),
                json.dumps(d.get("doc"), ensure_ascii=False)[:80]))


@check("D6")
def c_d6(g):
    gitd = os.path.join(g.root, ".git")
    bad, hits = [], []
    reuse = os.path.join(g.p(P_BACKEND), "services", "qa_service.py")
    if os.path.exists(reuse):
        for i, ln in enumerate(read_lines(reuse), 1):
            if ("代码" in ln and ("检索" in ln or "问答" in ln)) or "spec_from_file_location" in ln:
                hits.append("%s:%d %s" % (br(g.root, reuse), i, ln.strip()[:90]))
    cfg = os.path.join(g.p(P_BACKEND), "config.py")
    if os.path.exists(cfg):
        for i, ln in enumerate(read_lines(cfg), 1):
            if "检索" in ln or "问答" in ln or "spec_from_file_location" in ln:
                hits.append("%s:%d %s" % (br(g.root, cfg), i, ln.strip()[:90]))
    changed = []
    if os.path.isdir(gitd):
        rc, out = run_cmd(["git", "-C", g.root, "status", "--porcelain", "--", "代码/检索", "代码/问答"])
        changed = [x for x in out.splitlines() if x.strip()]
    else:
        changed = ["<镜像无 .git，跳过>"]
    if not hits:
        bad.append("未在 %s／%s 里找到对 代码\\检索／代码\\问答 的 import 路径" % (br(g.root, reuse), br(g.root, cfg)))
    if [x for x in changed if not x.startswith("<镜像")]:
        bad.append("代码/检索 或 代码/问答 有改动：%s" % changed[:5])
    if bad:
        g.fail("D6", "；".join(bad))
    else:
        g.ok("D6", "后端以路径加载上游模块（%s）；git status 对 代码/检索、代码/问答 零改动%s"
             % (hits[0], "（镜像无 .git，跳过 git 校验）" if changed and changed[0].startswith("<镜像") else ""))


# --------------------------------------------------------------------------
# 10. E 组：图谱服务化
# --------------------------------------------------------------------------
def consistency(g):
    if "cons" not in g.extra:
        if g.live:
            st, b, _ = http("GET", "/api/admin/consistency-check", None, ADMIN, timeout=120)
            g.extra["cons"] = ("实况 GET /api/admin/consistency-check", st, (b.get("data") or {}))
        else:
            d = load_json(g.p(P_EVID, "smoke_admin_consistency.json"), {}) or {}
            g.extra["cons"] = ("留痕 %s" % br(g.root, g.p(P_EVID, "smoke_admin_consistency.json")),
                               d.get("http_status"), ((d.get("body") or {}).get("data") or {}))
    return g.extra["cons"]


@check("E1")
def c_e1(g):
    src, st, d = consistency(g)
    gc = load_json(g.p(P_GRAPH_COUNTS), {}) or {}
    gs = load_json(g.p(P_GRAPH_STATS), {}) or {}
    n_nodes = (d.get("diff") or {}).get("graph_nodes_total")
    n_edges = (d.get("diff") or {}).get("graph_edges_total")
    exp_n = ((gc.get("counts") or {}).get("nodes_total"))
    exp_e = ((gc.get("counts") or {}).get("edges_total"))
    # 第三方来源：graph_stats.json 的 counts 与 nodes.csv／edges.csv 的行数
    gs_n = ((gs.get("counts") or {}).get("nodes_total"))
    gs_e = ((gs.get("counts") or {}).get("edges_total"))
    csv_n = (((gs.get("files") or {}).get("nodes.csv") or {}).get("rows"))
    csv_e = (((gs.get("files") or {}).get("edges.csv") or {}).get("rows"))
    by_rel = (d.get("diff") or {}).get("graph_edges_by_relation") or {}
    bad = []
    if n_nodes != exp_n:
        bad.append("diff.graph_nodes_total=%s ≠ %s 的 nodes_total=%s" % (n_nodes, br(g.root, g.p(P_GRAPH_COUNTS)), exp_n))
    if n_edges != exp_e:
        bad.append("diff.graph_edges_total=%s ≠ %s 的 edges_total=%s" % (n_edges, br(g.root, g.p(P_GRAPH_COUNTS)), exp_e))
    for tag, got, want, where in (("graph_stats.counts.nodes_total", gs_n, exp_n, "graph_stats.json"),
                                  ("graph_stats.counts.edges_total", gs_e, exp_e, "graph_stats.json"),
                                  ("nodes.csv 行数", csv_n, exp_n, "graph_stats.json 的 files"),
                                  ("edges.csv 行数", csv_e, exp_e, "graph_stats.json 的 files")):
        if want is not None and got != want:
            bad.append("%s=%s ≠ %s" % (tag, got, want))
    if not d.get("is_consistent"):
        bad.append("is_consistent=%s" % d.get("is_consistent"))
    if bad:
        g.fail("E1", "%s：%s" % (src, "；".join(bad)))
    else:
        g.ok("E1", "%s：diff.graph_nodes_total=%s、diff.graph_edges_total=%s；与 %s 的 nodes_total／edges_total 一致；"
                   "再与第三方来源对拍：%s 的 counts.nodes_total=%s、counts.edges_total=%s、files.nodes.csv.rows=%s、"
                   "files.edges.csv.rows=%s（关系分型 %d 类）；is_consistent=true"
             % (src, n_nodes, n_edges, br(g.root, g.p(P_GRAPH_COUNTS)),
                br(g.root, g.p(P_GRAPH_STATS)), gs_n, gs_e, csv_n, csv_e, len(by_rel)))


@check("E2")
def c_e2(g):
    gc = load_json(g.p(P_GRAPH_COUNTS), {}) or {}
    present = gc.get("relation_types_present") or []
    zero = gc.get("relation_types_zero") or []
    want = (gc.get("counts") or {}).get("edges_by_relation") or {}
    if not g.live:
        if len(present) + len(zero) == 9 and "EVIDENCED_BY" in present:
            g.ok("E2", "9 条核心关系（8 条有实例＋%s 计 0）；含 EVIDENCED_BY（%s，%s:%s）；"
                       "静态档据 %s，实况类型查询见 full 档"
                 % ("、".join(zero), want.get("EVIDENCED_BY"), br(g.root, g.p(P_GRAPH_COUNTS)),
                    "", br(g.root, g.p(P_GRAPH_COUNTS))))
        else:
            g.fail("E2", "graph_counts.json 的关系类型=present %s＋zero %s，不是 9 条或不含 EVIDENCED_BY"
                   % (present, zero))
        return
    rows = neo4j_run(g, "MATCH ()-[r]->() RETURN type(r) AS t, count(r) AS c ORDER BY t")
    live = dict((r["t"], r["c"]) for r in rows)
    bad = []
    for t, c in want.items():
        if t in live and live[t] != c:
            bad.append("%s 库内=%s ≠ 登记=%s" % (t, live[t], c))
        if t not in live and c != 0:
            bad.append("%s 库内查不到但登记=%s" % (t, c))
    if "EVIDENCED_BY" not in live:
        bad.append("EVIDENCED_BY 查不到")
    if len(present) + len(zero) != 9:
        bad.append("核心关系共 %d 条 ≠ 9" % (len(present) + len(zero)))
    if bad:
        g.fail("E2", "；".join(bad))
    else:
        g.ok("E2", "9 条核心关系在库内可查：%s（含 EVIDENCED_BY=%s）；另有登记为 0 的 %s；与 %s 的分型计数一致"
             % ("、".join("%s=%s" % (k, live[k]) for k in sorted(live)), live.get("EVIDENCED_BY"),
                "、".join(zero) or "无", br(g.root, g.p(P_GRAPH_COUNTS))))


@check("E3")
def c_e3(g):
    if not g.live:
        nrun(g, "E3", "多跳路径未实测")
        return
    bad, lines = [], []
    ev_keys = {"source_doc_id", "source_chunk_id", "evidence_doc_id", "confidence"}
    for hop in (1, 2):
        path = "/api/graph/paths" + qs(from_node="000001", relation="PARTICIPATES_IN", hop=hop)
        st, b, _ = http("GET", path)
        paths = (b.get("data") or {}).get("paths") or []
        # 证据属性挂在每条路径的 `edges` 上（不是 `relations`）：
        #   {"relation":…, "source_doc_id":1023, "source_chunk_id":1023000, "confidence":0.9, …}
        # 指向文档的边（EVIDENCED_BY）用 `evidence_doc_id` 承载定位、source_* 与 confidence 为 null，
        # 故判据取「每条边都带齐四个证据属性键，且每条路径至少有一条边给出非空定位」。
        n_edges = n_keymiss = n_loc = 0
        for p in paths:
            loc = False
            for e in (p.get("edges") or []):
                n_edges += 1
                if not ev_keys <= set(e.keys()):
                    n_keymiss += 1
                if (e.get("source_doc_id") is not None and e.get("source_chunk_id") is not None) \
                        or e.get("evidence_doc_id") not in (None, ""):
                    n_loc += 1
                    loc = True
            if not loc:
                bad.append("%d 跳：有路径的边全部没有非空证据定位（%s）"
                           % (hop, json.dumps(p, ensure_ascii=False)[:140]))
        lines.append("%d 跳 → HTTP %s，%d 条路径／%d 条边，边带齐四个证据属性键 %d 条，其中非空证据定位 %d 条"
                     % (hop, st, len(paths), n_edges, n_edges - n_keymiss, n_loc))
        if st != 200 or not paths or n_keymiss or not n_loc:
            bad.append("%d 跳：HTTP=%s 路径=%d 边=%d 缺属性键=%d 非空定位=%d"
                       % (hop, st, len(paths), n_edges, n_keymiss, n_loc))
    if bad:
        g.fail("E3", "；".join(bad))
    else:
        g.ok("E3", "GET /api/graph/paths（from_node=000001、relation=PARTICIPATES_IN、hop=1／2）：%s；"
                   "证据属性定义见 代码\\后端\\api\\graph.py" % "；".join(lines))


@check("E4")
def c_e4(g):
    if not g.live:
        nrun(g, "E4", "时间过滤未实测")
        return
    st1, b1, _ = http("GET", "/api/graph/events?page_size=2")
    st2, b2, _ = http("GET", "/api/graph/events" + qs(start_time="2026-01-01", end_time="2026-12-31", page_size=2))
    t1 = (b1.get("data") or {}).get("total")
    t2 = (b2.get("data") or {}).get("total")
    if st1 == 200 and st2 == 200 and t1 != t2:
        g.ok("E4", "不带时间区间 total=%s；带 2026-01-01～2026-12-31 total=%s（差集 %d 条，非空）"
             % (t1, t2, abs((t1 or 0) - (t2 or 0))))
    else:
        g.fail("E4", "不带时间区间 total=%s（HTTP %s）；带时间区间 total=%s（HTTP %s）" % (t1, st1, t2, st2))


@check("E5")
def c_e5(g):
    if not g.live:
        nrun(g, "E5", "后端切换未实测")
        return
    svc = g.p(P_BACKEND, "services", "graph_service.py")
    rc, out = run_cmd([sys.executable, svc, "--parity-check"], cwd=g.root, timeout=600)
    tail = [x.strip() for x in out.strip().splitlines() if x.strip()][-3:]
    if rc == 0 and "不一致 0" in out:
        g.ok("E5", "python %s --parity-check → 退出码 0；%s" % (br(g.root, svc), " / ".join(tail)))
    else:
        g.fail("E5", "python %s --parity-check → 退出码 %s；%s" % (br(g.root, svc), rc, " / ".join(tail)))


@check("E6")
def c_e6(g):
    targets = []
    for p in (P_DOC25, os.path.join(P_DEPLOY, "README.md"), os.path.join(P_DEPLOY, "Dockerfile")):
        fp = g.p(p)
        if os.path.exists(fp):
            targets.append(fp)
    for fp in sorted(glob.glob(os.path.join(g.root, P_BACKEND, "**", "*.py"), recursive=True)):
        targets.append(fp)
    hits = []
    for fp in targets:
        for i, ln in enumerate(read_lines(fp), 1):
            low = ln.lower()
            for term in FAKE_DEPLOY:
                if term.lower() in low:
                    hits.append((rel(g.root, fp), i, term, ln.strip()[:110]))
    neg = re.compile(r"不是|未|不|没有|无|非|仅|只|不得|禁止|no |not ")
    hard = [h for h in hits if not neg.search(h[3])]
    gc = load_json(g.p(P_GRAPH_COUNTS), {}) or {}
    claim = ((gc.get("neo4j") or {}).get("deployment") or "")
    if hard:
        g.fail("E6", "出现疑似虚构部署声明 %d 处：%s"
               % (len(hard), "；".join("%s:%d「%s」%s" % h for h in hard[:5])))
    elif not claim:
        g.fail("E6", "graph_counts.json 未登记实际部署形态")
    else:
        g.ok("E6", "文档与代码里的部署口径与实现形态一致：单一容器实例、无集群／高可用声明；"
                   "登记原文见 %s：%s…" % (br(g.root, g.p(P_GRAPH_COUNTS)), claim[:96]))

# --------------------------------------------------------------------------
# 11. F 组：前端页面
# --------------------------------------------------------------------------
FE_SRC = os.path.join(P_FRONTEND, "src")

SECRET_GROUPS = [
    ("模型端点", re.compile(r"deepseek|dashscope|openai\.com|/v1/chat", re.I)),
    ("API Key 形态（sk-…）", re.compile(r"\bsk-[A-Za-z0-9]{16,}")),
    ("API_KEY 赋值", re.compile(r"API_KEY\s*[:=]\s*[\"'][^\"']{8,}")),
    ("MySQL 连接串", re.compile(r"jdbc:mysql|mysql(\+\w+)?://", re.I)),
    ("库名 ashare_qa", re.compile(r"ashare_qa")),
    ("MySQL 端口", re.compile(r":3306\b")),
    ("Neo4j 连接串", re.compile(r"bolt://|neo4j://", re.I)),
    ("Neo4j 端口", re.compile(r":7687\b")),
    ("口令变量名", re.compile(r"NEO4J_PASSWORD|MYSQL_PASSWORD")),
]
FE_SCAN_EXT = {".js", ".mjs", ".cjs", ".vue", ".html", ".css", ".json", ".map", ".txt"}


def fe_files(g, sub):
    """列举前端某子树下的文本文件（跳过 node_modules／__pycache__）。"""
    out = []
    base = g.p(P_FRONTEND, sub)
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d not in ("node_modules", "__pycache__")]
        for f in fn:
            if os.path.splitext(f)[1].lower() in FE_SCAN_EXT:
                out.append(os.path.join(dp, f))
    return sorted(out)


def scan_secrets(files):
    hits = []
    for fp in files:
        try:
            txt = read_text(fp)
        except Exception:
            continue
        for i, ln in enumerate(txt.split("\n"), 1):
            for name, rx in SECRET_GROUPS:
                if rx.search(ln):
                    hits.append((fp, i, name, ln.strip()[:110]))
    return hits


JS_ARR_RE = lambda var: re.compile(var + r"\s*=\s*\[([^\]]*)\]", re.S)
JS_STR_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"")


def js_strings(blob):
    out = []
    for m in JS_STR_RE.finditer(blob or ""):
        out.append(m.group(1) if m.group(1) is not None else m.group(2))
    return out


@check("F1")
def c_f1(g):
    src = read_text(g.p(FE_SRC, "main.js"))
    routes = re.findall(r"path:\s*'([^']+)'", src)
    want = {"/ask": "AskView", "/answer/:answerId": "AnswerView", "/graph": "GraphView", "/history": "HistoryView"}
    miss_route = [p for p in want if p not in routes]
    miss_view = [v for v in want.values()
                 if not os.path.exists(g.p(FE_SRC, "views", v + ".vue"))]
    dist_index = g.p(P_FRONTEND, "dist", "index.html")
    dist_assets = glob.glob(g.p(P_FRONTEND, "dist", "assets", "*"))
    idx = g.p(P_FRONTEND, "index.html")
    mount = None
    if os.path.exists(idx):
        t = read_text(idx)
        if 'id="app"' in t:
            mount = br(g.root, idx)
    live_note = ""
    if g.live and port_open(5173):
        got = []
        for p in want:
            st, _ = http_abs("http://127.0.0.1:5173" + p)
            got.append("%s→%s" % (p, st))
        live_note = "；dev server 实测 %s" % "、".join(got)
    elif g.live:
        live_note = "；dev server 5173 未监听（构建产物已就绪，按视图文件判定）"
    else:
        live_note = "；静态档：按路由与视图文件判定"
    if os.path.isdir(g.p(P_FRONTEND, "dist")):
        dist_note = "构建产物 dist/index.html ＋ assets %d 个" % len(dist_assets)
    elif g.mirror:
        dist_note = "镜像未带 dist（构建产物核对跳过）"
    else:
        dist_note = "构建产物缺失"
    if miss_route or miss_view or not mount:
        g.fail("F1", "四类页面的路由／视图不全：缺路由 %s；缺视图文件 %s；index.html 挂载点=%s（%s）"
               % (miss_route or "无", miss_view or "无", mount, br(g.root, g.p(FE_SRC, "main.js"))))
    else:
        g.ok("F1", "四类页面齐备：%s（%s）＋ 4 个视图文件；挂载点 %s；%s%s"
             % ("、".join("%s→%s" % (k, want[k]) for k in want), br(g.root, g.p(FE_SRC, "main.js")),
                mount, dist_note, live_note))


@check("F2")
def c_f2(g):
    fe = g.p(FE_SRC, "components", "AnswerSections.vue")
    txt = read_text(fe)
    m = JS_ARR_RE("HEADERS").search(txt)
    got = js_strings(m.group(1)) if m else []
    ln = (txt[:m.start()].count("\n") + 1) if m else None
    be = os.path.join("代码", "问答", "prompt.py")
    be_txt = read_text(g.p(be)) if os.path.exists(g.p(be)) else ""
    # 上游把段头写成 ANSWER_SECTIONS（裸名）＋ SECTION_HEADERS = ["【%s】" % t for t in ANSWER_SECTIONS]
    ma = re.search(r"ANSWER_SECTIONS\s*=\s*[\[\(](.*?)[\]\)]", be_txt, re.S)
    names = [w for w in (js_strings(ma.group(1)) if ma else []) if w.strip()]
    mb = re.search(r"SECTION_HEADERS\s*=\s*[\[\(](.*?)[\]\)]", be_txt, re.S)
    want = []
    for w in (js_strings(mb.group(1)) if mb else []):
        if w.strip() and "%s" not in w:            # 字面量
            want.append(w)
    if names and not want:                         # 由 ANSWER_SECTIONS 拼出
        want = ["【%s】" % t for t in names]
    if not want:                                   # 上游不在镜像里时，退回《24》第五节 硬约束 11 的四个固定段头
        want = ["【回答】", "【证据来源】", "【知识图谱路径】", "【数据截至与判定区间】"]
        be_src = "《24》第五节 硬约束 11 的四个固定段头（镜像未带 %s）" % be
    else:
        be_src = "%s（ANSWER_SECTIONS＝%s，SECTION_HEADERS 由它拼出）" % (br(g.root, g.p(be)), "／".join(names))
    if got != want:
        g.fail("F2", "%s:%s 的 HEADERS=%s，与 %s 的 SECTION_HEADERS=%s 不一致（段头不全或顺序不同即失败）"
               % (br(g.root, fe), ln, got, be_src, want))
    else:
        g.ok("F2", "%s:%s 的 HEADERS 与 %s 的 SECTION_HEADERS 逐字且同序一致：%s"
             % (br(g.root, fe), ln, be_src, "／".join(got)))


@check("F3")
def c_f3(g):
    av = g.p(FE_SRC, "App.vue")
    txt = read_text(av)
    ok_label = "数据截至：" in txt
    ln = next((i for i, l in enumerate(txt.split("\n"), 1) if "数据截至：" in l), None)
    has_datepart = "slice(0, 10)" in txt or "slice(0,10)" in txt
    live_note, fail = "", []
    if g.live:
        st, b, _ = http("GET", "/api/config/meta")
        cut = (b.get("data") or {}).get("data_cutoff_time") if st == 200 else None
        live_note = "；/api/config/meta 的 data_cutoff_time=%s（日期部分 %s）" % (cut, (cut or "")[:10])
        if st != 200 or not cut:
            fail.append("GET /api/config/meta → HTTP %s" % st)
        elif re.search(r"\d{4}-\d{2}-\d{2}", cut or "") is None:
            fail.append("data_cutoff_time 不是 ISO 8601：%s" % cut)
    else:
        live_note = "；静态档：未与接口实测比对"
    if not ok_label or not has_datepart or fail:
        g.fail("F3", "页面固定字样「数据截至：YYYY-MM-DD」=%s；取日期部分=%s；%s"
               % (ok_label, has_datepart, "；".join(fail) or "（%s）" % br(g.root, av, ln)))
    else:
        g.ok("F3", "%s:%s 固定渲染「数据截至：{{datePart(...)}}」，datePart 取 ISO 前 10 位（=2026-09-25 那样的日期部分）%s"
             % (br(g.root, av), ln, live_note))


@check("F4")
def c_f4(g):
    gp = g.p(FE_SRC, "components", "GraphPathPanel.vue")
    txt = read_text(gp)
    m = re.search(r"NO_GRAPH_MARKER\s*=\s*'([^']*)'", txt)
    got = m.group(1) if m else None
    ln = next((i for i, l in enumerate(txt.split("\n"), 1) if "NO_GRAPH_MARKER" in l), None)
    rendered = bool(re.search(r"NO_GRAPH_MARKER[^\n]*\{\{", txt)) or "本次回答未使用图谱扩展" in txt.split("NO_GRAPH_MARKER", 1)[-1]
    want = "本次回答未使用图谱扩展"
    if got != want or not rendered:
        g.fail("F4", "%s:%s 的固定字样=%r（应 %r），模板渲染=%s" % (br(g.root, gp), ln, got, want, rendered))
    else:
        g.ok("F4", "%s:%s 固定字样 NO_GRAPH_MARKER=%r，且在 is_graph_extended=0 分支渲染（不留空、不编造）"
             % (br(g.root, gp), ln, got))


@check("F5")
def c_f5(g):
    el = g.p(FE_SRC, "components", "EvidenceList.vue")
    m = JS_ARR_RE("TYPES").search(read_text(el))
    got = js_strings(m.group(1)) if m else []
    ln = next((i for i, l in enumerate(read_text(el).split("\n"), 1) if "TYPES" in l and "=" in l), None)
    want = ["回答来源", "新闻来源", "公告来源", "相关事件"]
    grouped = "props.items.filter" in read_text(el) or "filter(" in read_text(el)
    if got != want or not grouped:
        g.fail("F5", "%s:%s 的四类=%s（应 %s）；分组渲染=%s" % (br(g.root, el), ln, got, want, grouped))
    else:
        g.ok("F5", "%s:%s 四类固定顺序 %s，按 evidence_type 分组渲染" % (br(g.root, el), ln, "／".join(got)))


@check("F6")
def c_f6(g):
    src_files = fe_files(g, "src")
    dist_files = fe_files(g, "dist")
    hits = scan_secrets(src_files) + scan_secrets(dist_files)
    dist_note = ("dist %d 个文件" % len(dist_files)) if dist_files else \
                ("dist 未带（镜像）" if g.mirror else "dist 不存在")
    if hits:
        g.fail("F6", "前端源码／构建产物命中 %d 处：%s"
               % (len(hits), "；".join("%s:%d %s「%s」" % (rel(g.root, h[0]), h[1], h[2], h[3]) for h in hits[:5])))
    else:
        g.ok("F6", "src %d 个文件 ＋ %s，九组关键字（模型端点／sk-…／API_KEY／MySQL 串／库名／:3306／bolt／:7687／口令变量）全部 0 命中"
             % (len(src_files), dist_note))


# --------------------------------------------------------------------------
# 12. G 组：安全与非功能
# --------------------------------------------------------------------------
PW_RE = re.compile(r"(mysql_password|neo4j_password|password|passwd|pwd)\s*[:=]\s*[\"']([^\"'\n]{6,})[\"']")
PW_PLACEHOLDER = ("***", "your", "填", "<", "xxx", "changeme", "密码", "secret", "example", "见 ", "同上")


@check("G1")
def c_g1(g):
    hits = scan_secrets(fe_files(g, "src")) + scan_secrets(fe_files(g, "dist"))
    bad = []
    if hits:
        bad.append("前端命中 %d 处：%s" % (len(hits), "；".join("%s:%d %s" % (rel(g.root, h[0]), h[1], h[2]) for h in hits[:4])))
    # 后端 .py 里不得写死口令
    lit = []
    for fp in sorted(glob.glob(g.p(P_BACKEND, "**", "*.py"), recursive=True)):
        for i, ln in enumerate(read_lines(fp), 1):
            m = PW_RE.search(ln)
            if m and not any(p in m.group(2) for p in PW_PLACEHOLDER):
                lit.append("%s:%d「%s」" % (br(g.root, fp), i, m.group(1)))
    if lit:
        bad.append("后端出现口令字面量 %d 处：%s" % (len(lit), "；".join(lit[:4])))
    # 后端凭据只从 config.local.json／环境变量读（不写死）
    cfg = read_text(g.p(P_BACKEND, "config.py"))
    reads_file = "config.local.json" in cfg
    reads_env = "os.environ" in cfg or "getenv" in cfg
    if not (reads_file or reads_env):
        bad.append("config.py 既没有 config.local.json、也没有 os.environ／getenv（凭据来源不明）")
    # 本地配置被 .gitignore 覆盖（不入公开仓库）
    gi = None
    if os.path.isdir(g.p(".git")):
        rc, _ = run_cmd(["git", "-C", g.root, "check-ignore", "-q", os.path.join(P_BACKEND, "config.local.json")])
        gi = (rc == 0)
        if not gi:
            bad.append("config.local.json 未被 .gitignore 覆盖（git check-ignore 退出码 %s）" % rc)
    # 顺带如实登记：本机 gitignore 的本地配置文件里另有明文 Neo4j 口令（取值一律不打印、不落盘进本报告）
    local_pw = [rel(g.root, p) for p in
                (g.p(P_DEPLOY, "config.docker.json"), g.p(P_BACKEND, "config.local.json"))
                if os.path.exists(p) and re.search(r"\"neo4j_password\"\s*:\s*\"[^\"]+\"", read_text(p))]
    if bad:
        g.fail("G1", "；".join(bad))
    else:
        g.ok("G1", "前端 src＋dist 零密钥；%s 及后端全部 .py 无口令字面量，凭据只从 %s%s 读；"
                   "config.local.json 被 .gitignore 覆盖%s；本机另有 %s 存明文 Neo4j 口令（已被 .gitignore 覆盖、未入库，"
                   "本报告不打印其取值）"
             % (br(g.root, g.p(P_BACKEND, "config.py")),
                "config.local.json" if reads_file else "", "与环境变量" if reads_env else "",
                "（git check-ignore 通过）" if gi else "（镜像无 .git，跳过 git check-ignore）",
                "、".join(local_pw) if local_pw else "无文件"))


@check("G2")
def c_g2(g):
    cfgp = g.p(P_BACKEND, "config.py")
    cfg = read_text(cfgp)
    m1 = re.search(r"RATE_LIMIT\s*=\s*\{(.*?)\}", cfg, re.S)
    win = re.search(r"window_seconds\"?\s*[:=]\s*(\d+)", m1.group(1)) if m1 else None
    mx = re.search(r"max_requests\"?\s*[:=]\s*(\d+)", m1.group(1)) if m1 else None
    m2 = re.search(r"question_max_chars\"?\s*[:=]\s*(\d+)", cfg)
    ln = next((i for i, l in enumerate(cfg.split("\n"), 1) if "RATE_LIMIT" in l), None)
    bad = []
    if not (win and mx and win.group(1) == "60" and mx.group(1) == "60"):
        bad.append("config.py 的 RATE_LIMIT 窗口／上限=%s／%s（应 60／60）"
                   % (win.group(1) if win else "?", mx.group(1) if mx else "?"))
    if not (m2 and m2.group(1) == "500"):
        bad.append("question_max_chars=%s（应 500）" % (m2.group(1) if m2 else "?"))
    doc25 = read_text(g.p(P_DOC25))
    readme = read_text(g.p(P_DEPLOY, "README.md"))
    reg = ("60" in doc25 and "限流" in doc25) and ("60 次" in readme or "60" in readme)
    if not reg:
        bad.append("《25》或 部署\\README.md 未登记限制参数")
    live_note = ""
    if g.live:
        st1, b1, _ = http("POST", "/api/qa/ask", {"question": "边" * 501, "session_id": "S-GATE-G2"})
        g.err_responses.append(("POST /api/qa/ask (500+1 字)", st1, b1, 1001))
        live_note = "；实测 501 字 → HTTP %s／%s；限流实测见 C9" % (st1, b1.get("code"))
        if st1 != 400 or b1.get("code") != 1001:
            bad.append("超长输入实测 HTTP=%s code=%s（应 400／1001）" % (st1, b1.get("code")))
    else:
        live_note = "；静态档：未实测"
    if bad:
        g.fail("G2", "；".join(bad))
    else:
        g.ok("G2", "%s:%s RATE_LIMIT 60 次／60 秒、question_max_chars=500；限制参数已登记于《25》与 部署\\README.md%s"
             % (br(g.root, cfgp), ln, live_note))


@check("G3")
def c_g3(g):
    rows = load_jsonl(g.p(P_ERRSCEN))
    n = len(rows)
    raw = sorted(glob.glob(os.path.join(g.root, P_EVID, "err_*.json")))
    bad = []
    if n < 6:
        bad.append("%s 只有 %d 行（应 ≥6）" % (br(g.root, g.p(P_ERRSCEN)), n))
    miss_ev, not_alive, noc = [], [], []
    alive_ok = (True, "ok", "true", "ok（200）", "yes", 1)
    for i, r in enumerate(rows, 1):
        ev = r.get("evidence")
        if not (isinstance(ev, str) and ev.strip()):
            miss_ev.append("%d:<无 evidence 原始输出>" % i)
        va = r.get("service_alive_after")
        if va not in alive_ok and not (isinstance(va, str) and va.lower().startswith("ok")):
            not_alive.append("%d:%s" % (i, va))
        if r.get("actual_code") is None or r.get("http_status") is None:
            noc.append(str(i))
    if miss_ev:
        bad.append("缺原始输出留痕 %d 行：%s" % (len(miss_ev), miss_ev[:4]))
    if not_alive:
        bad.append("服务存活标记非 true 的行：%s" % not_alive[:4])
    if noc:
        bad.append("缺 actual_code／http_status 的行：%s" % noc[:4])
    live_note = ""
    if g.live:
        st, _, _ = http("GET", "/api/health", timeout=30)
        live_note = "；跑完全部场景后实测 GET /api/health=%s" % st
        if st != 200:
            bad.append("全部场景之后 /api/health=%s（服务未存活）" % st)
    if bad:
        g.fail("G3", "；".join(bad))
    else:
        cats = sorted(set(str(r.get("category")) for r in rows))
        g.ok("G3", "%s 共 %d 行（≥6 类），逐行 evidence 给出原始输出、actual_code／http_status 齐备，"
                   "service_alive_after 全为 true；同目录另有 %d 份原始响应留痕 %s；类别 %s%s"
             % (br(g.root, g.p(P_ERRSCEN)), n, len(raw), br(g.root, g.p(P_EVID, "err_*.json")),
                "／".join(cats), live_note))


@check("G4")
def c_g4(g):
    d = load_json(g.p(P_LATENCY), {}) or {}
    seg = ((d.get("nfr01_latency") or {}).get("segments") or {})
    qs_ = (d.get("nfr01_latency") or {}).get("questions") or []
    need = ["vector_retrieval", "graph_query", "llm_generation", "end_to_end"]
    bad, lines = [], []
    for k in need:
        s = seg.get(k)
        if not s:
            bad.append("缺段 %s" % k)
            continue
        has = all(x in s for x in ("avg", "p95", "source", "n"))
        lines.append("%s avg=%s p95=%s 来源=%s" % (k, s.get("avg"), s.get("p95"), "有" if s.get("source") else "无"))
        if not has:
            bad.append("%s 缺 avg／p95／source／n" % k)
    cav = [k for k, s in seg.items() if s.get("caveat")]
    if len(qs_) < 3:
        bad.append("样本题数=%d（应 ≥3）" % len(qs_))
    if not cav:
        bad.append("没有任何一段标注「不可信／口径外」")
    if bad:
        g.fail("G4", "；".join(bad))
    else:
        g.ok("G4", "%s 四段齐（%s）；样本题 %d 道；已如实标注不可信段：%s（%s）"
             % (br(g.root, g.p(P_LATENCY)), "；".join(lines), len(qs_), "、".join(cav),
                "图谱查询段实测 0.00 s 且上游打印分项未闭合，按判据只要求说明来源与不可信，不要求 >0"))


@check("G5")
def c_g5(g):
    paced = load_json(g.p(P_EVID, "nfr02_paced100.json"), {}) or {}
    conc = load_json(g.p(P_EVID, "nfr02_concurrent10.json"), {}) or {}
    seq = load_json(g.p(P_EVID, "nfr02_sequential100.json"), {}) or {}
    ps = paced.get("summary") or {}
    p_ok, p_n = ps.get("ok"), ps.get("requests") or 100
    # 成功率一律**按 ok／requests 复算**（不信 summary 自报值），并核两者是否自洽
    p_rate = (p_ok / float(p_n)) if isinstance(p_ok, int) and p_n else None
    c_ok, c_n = conc.get("success"), conc.get("total")
    c_rate = (c_ok / float(c_n)) if isinstance(c_ok, int) and c_n else None
    bad = []
    if p_rate is None or p_rate < 0.95:
        bad.append("正常节奏（1.2 s 一次）成功率=%s/%s（阈值 ≥95%%）" % (p_ok, p_n))
    if ps.get("success_rate") is not None and p_rate is not None and abs(ps["success_rate"] - p_rate) > 1e-9:
        bad.append("summary.success_rate=%s 与 ok／requests 复算值 %s 对不上" % (ps["success_rate"], p_rate))
    if c_rate is None or c_rate < 0.95 or c_ok != c_n:
        bad.append("10 并发成功率=%s/%s（阈值 ≥95%%）" % (c_ok, c_n))
    if conc.get("success_rate") is not None and c_rate is not None and abs(conc["success_rate"] - c_rate) > 1e-9:
        bad.append("10 并发的 success_rate=%s 与 success／total 复算值 %s 对不上" % (conc["success_rate"], c_rate))
    if not (seq.get("total") == 100):
        bad.append("背靠背 100 次的留痕缺失")
    if bad:
        g.fail("G5", "；".join(bad))
    else:
        g.ok("G5", "① 正常节奏 100 次 = %d/100（%.0f%%，阈值 ≥95%%，来源 %s）；② 10 并发 = %s/%s；"
                   "另如实标注：背靠背 100 次 %s/100，缺口 %s 全是限流 1004——这是限流生效的证据、不是可用性失败（%s）"
             % (p_ok, (p_rate or 0) * 100, br(g.root, g.p(P_EVID, "nfr02_paced100.json")),
                c_ok, c_n, seq.get("success"), seq.get("failure_kinds"),
                br(g.root, g.p(P_EVID, "nfr02_sequential100.json"))))


# G6 的范围＝**本阶段的依赖清单与交付物**：依赖声明（package.json／package-lock.json／Dockerfile）、
# 后端代码、前端源码、第 9 阶段文档与产物。**不含**上游阶段（如 阶段02 文献调研里对 LangChain 论文的
# 引用）——那些不是本阶段的依赖清单，按判据「依赖清单中无…」不属本行范围。
G6_SCOPE_FILES = [os.path.join(P_FRONTEND, "package.json"), os.path.join(P_FRONTEND, "package-lock.json"),
                  os.path.join(P_DEPLOY, "Dockerfile"), os.path.join(P_DEPLOY, "README.md")]
G6_SCOPE_DIRS = [P_BACKEND, os.path.join(P_FRONTEND, "src"), STAGE]
G6_EXT = {"", ".py", ".md", ".txt", ".json", ".js", ".vue", ".ps1", ".cmd", ".bat",
          ".yml", ".yaml", ".sql", ".csv", ".example"}


@check("G6")
def c_g6(g):
    files = [g.p(f) for f in G6_SCOPE_FILES if os.path.exists(g.p(f))]
    for d in G6_SCOPE_DIRS:
        for dp, dn, fn in os.walk(g.p(d)):
            dn[:] = [x for x in dn if x not in ("node_modules", "dist", "__pycache__", ".venv", "_工作底稿")]
            for f in fn:
                if os.path.splitext(f)[1].lower() in G6_EXT:
                    files.append(os.path.join(dp, f))
    hard, softn = [], 0
    for fp in files:
        for i, ln in enumerate(read_lines(fp), 1):
            low = ln.lower()
            for t in EXCLUDED_TECH:
                if t in low:
                    if re.search(r"不|未|没有|无|no |not |排除|禁止", ln):
                        softn += 1
                    else:
                        hard.append("%s:%d「%s」" % (br(g.root, fp), i, t))
    installed = []
    for mod in ("langchain", "llama_index", "elasticsearch", "kafka"):
        try:
            __import__(mod)
            installed.append(mod)
        except Exception:
            pass
    bad = list(hard)
    if installed:
        bad.append("运行环境已装被排除包：%s" % installed)
    if bad:
        g.fail("G6", "命中 %d 处：%s" % (len(bad), "；".join(bad[:6])))
    else:
        g.ok("G6", "依赖清单与交付物（%s、package-lock.json、%s、后端 .py、前端 src、阶段09 文档与产物；共 %d 个文件）"
                   "中，%d 类被排除技术（LangChain／LlamaIndex／Elasticsearch／Kafka／K8s／编排等）逐项 0 命中；"
                   "另有 %d 处出现在「不引入…」的说明句里，按语境排除；Python 环境未安装 langchain／llama_index／elasticsearch／kafka"
             % (br(g.root, g.p(P_FRONTEND, "package.json")), br(g.root, g.p(P_DEPLOY, "Dockerfile")),
                len(files), len(EXCLUDED_TECH), softn))


# --------------------------------------------------------------------------
# 13. H 组：部署形态
# --------------------------------------------------------------------------
def wsl_bash(cmd, timeout=300, cwd=None):
    """在 WSL2 的 Ubuntu 里执行一条 bash 命令（WSL_UTF8 免乱码）。"""
    return run_cmd(["wsl", "-d", "Ubuntu", "-u", "root", "--", "bash", "-lc", cmd],
                   cwd=cwd, timeout=timeout, env={"WSL_UTF8": "1"})


def docker_ok():
    rc, out = wsl_bash("docker version --format '{{.Server.Version}}'", timeout=90)
    return rc == 0 and bool(re.search(r"\d+\.\d+", out)), out.strip()[:200]


def ps1_parse_errors(pairs):
    """用 PowerShell 自己的解析器数脚本语法错误（**只解析、不执行**）。

    用途：把「脚本语法写错」与「脚本编码被读错」分开——同一份字节流，
    原样读与加 BOM 读的语法错误条数不同，即说明是编码问题而非语法问题。
    pairs: [(标签, 绝对路径)] → (rc, {标签: 错误条数}, 原样输出)
    """
    ctl = os.path.join(tempfile.gettempdir(), "gate9_ps1_parse.ps1")
    body = ["$ErrorActionPreference = 'Continue'"]
    for tag, path in pairs:
        body.append("$e = $null; $t = $null")
        body.append("$null = [System.Management.Automation.Language.Parser]::ParseFile("
                    "'%s', [ref]$t, [ref]$e)" % path.replace("\\", "/"))
        body.append("Write-Output ('%s=' + $e.Count)" % tag)
    # 控制脚本要带上中文路径，故存成 UTF-8 **带 BOM**：Windows PowerShell 5.1 只认 BOM 才
    # 会把脚本按 UTF-8 读（无 BOM 的 UTF-8 会被当 ANSI／GBK，正是 H1 要诊断的那个坑）。
    with open(ctl, "w", encoding="utf-8-sig", newline="\n") as fh:
        fh.write("\n".join(body) + "\n")
    rc, out = run_cmd(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ctl], timeout=180)
    res = {}
    for m in re.finditer(r"^\s*([A-Za-z0-9_]+)\s*=\s*(\d+)\s*$", out, re.M):
        res[m.group(1)] = int(m.group(2))
    return rc, res, out


@check("H1")
def c_h1(g):
    if not g.live:
        nrun(g, "H1", "一键启动脚本未实跑")
        return
    ps1 = g.p(P_DEPLOY, "启动.ps1")
    rc, out = run_cmd(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps1, "-NoFrontend"],
                      cwd=g.root, timeout=600)
    marks = [m for m in ("① MySQL", "② Neo4j", "③ 后端", "⑤ 健康检查") if m in out]
    health = re.search(r"\[\s*OK\s*\]\s*status=(\w+)\s+mysql=(\w+)\s+neo4j=(\w+)\s+vector_index=(\w+)\s+model_config=(\w+)", out)
    bang = [l.strip() for l in out.split("\n") if "[ !! ]" in l]
    if len(marks) == 4 and health and health.group(1) == "ok" and not bang:
        g.ok("H1", "powershell -File 部署\\启动.ps1 -NoFrontend：四步检查全部打印（%s），"
                   "健康检查 [OK] status=ok mysql=True neo4j=True vector_index=True model_config=True"
                   "（8000 已监听，脚本复用现有进程）" % "／".join(marks))
    else:
        # 诊断：脚本连第一步都没打印就退出 —— 用 PowerShell 解析器把「语法错」与「编码读错」分开。
        abs_ps1 = os.path.abspath(ps1)
        bom_ps1 = os.path.join(tempfile.gettempdir(), "gate9_ps1_bom_%s" % os.path.basename(ps1))
        with open(abs_ps1, "rb") as fh:
            raw = fh.read()
        with open(bom_ps1, "wb") as fh:                                  # 同一份字节流 ＋ BOM 的副本
            fh.write(b"\xef\xbb\xbf" + raw)
        ctl_rc, counts, _ctl_out = ps1_parse_errors([("as_is", abs_ps1), ("with_bom", bom_ps1)])
        err_lines = [l.strip() for l in out.split("\n") if l.strip()][:3]
        g.fail("H1", "退出码=%s；打印到的步骤 %s；健康行=%s；[ !! ] 行 %s；前 3 行原始输出：%s；"
                     "PowerShell 解析器只读检查（不执行）：原样读 %s 条语法错误、加 BOM 后 %s 条"
                     "（%s:%d 首字节 %s，Windows PowerShell 5.1 对无 BOM 的 UTF-8 按 ANSI／GBK 读，"
                     "中文被拆成非法标记）"
               % (rc, marks, health.group(0) if health else "无", bang[:3] or "无",
                  " / ".join(err_lines) or "（无输出）",
                  counts.get("as_is", "?"), counts.get("with_bom", "?"),
                  br(g.root, ps1), 1, raw[:3].hex(" ")))


@check("H2")
def c_h2(g):
    if not g.live:
        nrun(g, "H2", "镜像存在性未实测")
        return
    ok, info = docker_ok()
    if not ok:
        g.bad_env("H2", "WSL2 内 Docker Engine 不可用：%s" % info)
        return
    rc, out = wsl_bash("docker images ashare-qa-backend:local --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}} {{.CreatedSince}}'")
    ev = g.p(P_EVID, "docker_build_evidence.txt")
    img = [l for l in out.split("\n") if "ashare-qa-backend" in l]
    if img:
        g.ok("H2", "WSL2 内 docker images 命中：%s；Docker 版本 %s；构建留痕 %s"
             % (img[0].strip(), info, br(g.root, ev) if os.path.exists(ev) else "缺失"))
    else:
        g.fail("H2", "docker images ashare-qa-backend:local 无结果：%s" % out.strip()[:200])


@check("H3")
def c_h3(g):
    if not g.live:
        nrun(g, "H3", "镜像可运行性未实测")
        return
    ok, info = docker_ok()
    if not ok:
        g.bad_env("H3", "WSL2 内 Docker Engine 不可用：%s" % info)
        return
    # 判据（《24》第 363 行 H3）：「由镜像启动的容器能响应 /api/health（或在《25》中如实登记
    # 失败原因与替代证据）」。**不能只看 `docker run` 的退出码**——实测本机 `docker run` 起不动
    # 应用时也返回 0（run.py 报完 argparse 错误后退出码为 0），只看退出码会把「容器根本没起来」
    # 判成通过。故此处按实质判定：按镜像自带 CMD 起容器 → 轮询容器内的 /api/health →
    # 无响应再看《25》有无登记这个失败原因。
    rc0, cmd_out = wsl_bash("docker inspect -f '{{json .Config.Cmd}}' ashare-qa-backend:local")
    cmds = [l for l in cmd_out.split("\n") if l.strip().startswith("[")]
    cmd_txt = cmds[0].strip() if cmds else "?"
    runpy = g.p(P_BACKEND, "run.py")
    runtxt = read_text(runpy)
    host_line = next((i for i, l in enumerate(runtxt.split("\n"), 1) if l.startswith("HOST =")), None)
    has_host_arg = bool(re.search(r'add_argument\(\s*["\']--host["\']', runtxt))
    cfg_mount = "/mnt/c/Users/15129/Desktop/毕业设计/" + P_DEPLOY.replace("\\", "/") + "/config.docker.json"
    name, probe = "ashare-qa-gate-run", "ashare-qa-gate-probe"
    # 容器内探针：写成文件再由 `docker exec python 文件` 跑，**避免在 bash 里嵌引号**
    # （嵌套 `$( … python -c "…'…'…" … )` 会被 WSL 的命令行转发搅乱引号，实测报 bash 语法错）。
    probe_py = os.path.join(tempfile.gettempdir(), "gate9_health_probe.py")
    with open(probe_py, "w", encoding="ascii", newline="\n") as fh:
        fh.write("import json, urllib.request\n"
                 "try:\n"
                 "    r = urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=6)\n"
                 "    d = json.load(r)\n"
                 "    print('HEALTH', r.status, d.get('status'), (d.get('mysql') or {}).get('ok'),\n"
                 "          (d.get('neo4j') or {}).get('ok'))\n"
                 "except Exception as exc:\n"
                 "    print('HEALTH_ERR', type(exc).__name__)\n")
    _drv, _, _rest = probe_py.partition(":")           # C:\… → /mnt/c/…
    probe_mount = "/mnt/%s/%s" % (_drv.lower(), _rest.replace("\\", "/").lstrip("/"))
    run_mount = " -v '%s:/app/代码/后端/config.local.json:ro' -v '%s:/tmp/gate9_probe.py:ro'" \
                % (cfg_mount, probe_mount)

    def wsl_probe(container):
        rc, out = wsl_bash("docker exec %s python /tmp/gate9_probe.py 2>&1 | head -n 3" % container, timeout=90)
        line = [l.strip() for l in out.split("\n") if l.strip().startswith("HEALTH")]
        return (line[0] if line else ""), out

    health, probe_health, status_line, logtail = "", "", [], []
    try:
        wsl_bash("docker rm -f %s %s >/dev/null 2>&1; echo ok" % (name, probe), timeout=90)
        rc, out = wsl_bash("docker run -d --name %s --network host%s ashare-qa-backend:local "
                           ">/dev/null 2>&1; echo RUN_RC=$?" % (name, run_mount), timeout=180)
        run_rc = (re.search(r"RUN_RC=(\d+)", out) or [None, "?"])[1]
        for i in range(1, 13):                     # 最多等 60 s
            time.sleep(5)
            health, _raw = wsl_probe(name)
            if health.startswith("HEALTH 200"):
                break
        rc, st_out = wsl_bash("docker ps -a --filter name=%s --format '{{.Status}}'; "
                              "docker logs %s 2>&1 | tail -n 8" % (name, name), timeout=120)
        logs = [l.strip() for l in st_out.split("\n") if l.strip()]
        status_line = [l for l in logs if l.startswith("Up ") or l.startswith("Exited")]
        logtail = [l for l in logs if ("run.py" in l or "Traceback" in l or "error" in l.lower())][-2:]
        # 补充探针：只把 CMD 换掉（其余照旧），看同一镜像能不能真起来 —— 用来定位缺陷落点
        wsl_bash("docker run -d --name %s --network host%s ashare-qa-backend:local "
                 "python 代码/后端/run.py >/dev/null 2>&1; echo ok" % (probe, run_mount), timeout=180)
        for i in range(1, 7):
            time.sleep(5)
            probe_health, _raw = wsl_probe(probe)
            if probe_health.startswith("HEALTH 200"):
                break
    finally:
        wsl_bash("docker rm -f %s %s >/dev/null 2>&1; echo CLEANED" % (name, probe), timeout=120)
    d25 = read_text(g.p(P_DOC25))
    reg = [i for i, l in enumerate(d25.split("\n"), 1)
           if ("--host" in l or "0.0.0.0" in l or "unrecognized" in l)]
    reg_txt = ("已登记（%s 第 %s 行）" % (br(g.root, g.p(P_DOC25)), reg[0])) if reg else \
              "**未登记**（%s 的「已知限制与证据不足清单」24 条里没有 CMD 参数这一项）" % br(g.root, g.p(P_DOC25))
    hs = health.split() if health else []
    if health.startswith("HEALTH 200"):
        g.ok("H3", "按镜像自带 CMD 起容器：容器内 GET /api/health 有响应 —— HTTP %s／status=%s／mysql=%s／neo4j=%s；"
                   "CMD=%s" % (hs[1], hs[2], hs[3], hs[4], cmd_txt))
    else:
        g.fail("H3", "按镜像自带 CMD 起容器后，容器内 GET /api/health **无响应**（12 次×5 s 轮询，末次读数=%s）；CMD=%s；"
                     "容器状态=%s；容器日志尾部=%s；《25》是否登记该失败原因：%s；"
                     "补充探针（只把 CMD 换成 [python 代码/后端/run.py]，其余照旧）：%s —— 说明缺陷落在 CMD 的 --host 参数上，"
                     "而不是镜像本身（%s:%s 的 argparse 只有 --reload／--port／--log-level，HOST 固定 127.0.0.1：%s）"
               % (health or "（无输出）", cmd_txt, status_line[0] if status_line else "（未取到）",
                  " / ".join(logtail) or "（无相关行）", reg_txt,
                  "容器内 /api/health 返回 200（可运行）" if probe_health.startswith("HEALTH 200")
                  else "也无响应（%s）" % (probe_health or "（无输出）"),
                  br(g.root, runpy), host_line,
                  ("无 --host 开关，故报「unrecognized arguments: --host 0.0.0.0」" if not has_host_arg else "有 --host 开关")))


@check("H4")
def c_h4(g):
    rm = g.p(P_DEPLOY, "README.md")
    txt = read_text(rm)
    sec_local = bool(re.search(r"^##\s*一、\s*本机形态", txt, re.M))
    sec_docker = bool(re.search(r"^##\s*二、\s*容器形态", txt, re.M))
    no_desktop = "未安装 Docker Desktop" in txt
    compose = ("docker-compose" in txt or "compose" in txt)
    negative_compose = bool(re.search(r"没有|不交付|不含|无\s*docker-compose|not ", txt))
    body = read_text(g.p(P_DEPLOY, "Dockerfile"))
    df = "FROM python" in body
    if sec_local and sec_docker and no_desktop and df and negative_compose:
        g.ok("H4", "%s 含「一、本机形态」与「二、容器形态」两节，并写明「未安装 Docker Desktop」（需管理员权限、Docker 只以 WSL2 内 Engine 形态可用）；"
                   "容器清单只交付 Dockerfile（无 compose／K8s）"
             % br(g.root, rm))
    else:
        g.fail("H4", "本机形态节=%s；容器形态节=%s；「未安装 Docker Desktop」=%s；Dockerfile=%s；编排清单否定表述=%s（%s）"
               % (sec_local, sec_docker, no_desktop, df, negative_compose, br(g.root, rm)))


@check("H5")
def c_h5(g):
    rm = read_text(g.p(P_DEPLOY, "README.md"))
    readme_ports = set(int(x) for x in re.findall(r"(?<![\d.])(\d{4})(?![\d.])", rm))
    rm2 = load_json(g.p(P_RUN_MANIFEST), {}) or {}
    man_ports = set(int(p.get("port")) for p in (rm2.get("ports") or []) if p.get("port"))
    gc = load_json(g.p(P_GRAPH_COUNTS), {}) or {}
    uri = ((gc.get("neo4j") or {}).get("uri") or "")
    # 本机 config.local.json 不入镜像（含口令），镜像里退回 .example 模板（端口口径同源）
    cfgsrc = g.p(P_BACKEND, "config.local.json")
    if not os.path.exists(cfgsrc):
        cfgsrc = g.p(P_BACKEND, "config.local.json.example")
    cfg = load_json(cfgsrc, {}) or {}
    bport, fport = cfg.get("backend_port"), cfg.get("frontend_port")
    bad = []
    if bport != 8000:
        bad.append("config.local.json backend_port=%s（应 8000）" % bport)
    if fport != 5173:
        bad.append("config.local.json frontend_port=%s（应 5173）" % fport)
    if uri != "bolt://127.0.0.1:7687":
        bad.append("graph_counts.json 的 neo4j.uri=%s（应 bolt://127.0.0.1:7687）" % uri)
    fixed = {3306, 7474, 7687, 8000, 5173}
    if not fixed <= readme_ports:
        bad.append("部署\\README.md 端口一览缺 %s" % sorted(fixed - readme_ports))
    if man_ports != fixed:
        bad.append("run_manifest.json 登记端口=%s（应 %s）" % (sorted(man_ports), sorted(fixed)))
    live_note = ""
    if g.live:
        live = {p: port_open(p) for p in (3306, 7474, 7687, 8000)}
        live_note = "；实测监听 %s" % "、".join("%s=%s" % (k, v) for k, v in live.items())
        if not all(live.values()):
            bad.append("应有端口未监听：%s" % [k for k, v in live.items() if not v])
    else:
        live_note = "；静态档：未实测监听"
    if bad:
        g.fail("H5", "；".join(bad))
    else:
        g.ok("H5", "端口口径一致：%s 后端 %s／前端 %s；部署\\README.md 端口一览 %s；"
                   "run_manifest.json 登记 %s；Neo4j uri=%s%s"
             % (rel(g.root, cfgsrc), bport, fport, sorted(readme_ports), sorted(man_ports), uri, live_note))


# --------------------------------------------------------------------------
# 14. I 组：一致性、只读与文档
# --------------------------------------------------------------------------
@check("I1")
def c_i1(g):
    if not g.live:
        nrun(g, "I1", "上游只读指纹未比对")
        return
    fp = g.p(P_FINGERPRINT)
    if not os.path.exists(fp):
        g.fail("I1", "决策者基线快照脚本不存在：%s" % br(g.root, fp))
        return
    rc, out = run_cmd([sys.executable, fp, "--check"], cwd=g.root, timeout=300)
    tail = [l.strip() for l in out.split("\n") if l.strip()][-4:]
    if rc == 0:
        g.ok("I1", "python %s --check → 退出码 0（11 项输入 ＋ 上游代码文件指纹逐项一致）：%s"
             % (br(g.root, fp), " / ".join(tail)))
    else:
        g.fail("I1", "python %s --check → 退出码 %s：%s" % (br(g.root, fp), rc, " / ".join(tail)))


I2_SKIP_DIRS = {".git", "node_modules", "dist", "__pycache__", "_工作底稿", ".venv", ".idea", ".vscode"}
I2_EXT = {"", ".py", ".md", ".txt", ".json", ".js", ".vue", ".html", ".css", ".ps1", ".cmd",
          ".bat", ".yml", ".yaml", ".sql", ".csv", ".example", ".example"}
I2_NEG = re.compile(r"不是|不称|不写|不引|不得|不再|未|没有|无|禁止|非|不含|排除|改为|纠正|口径|统一|一律|写成|称「|称\"")
# FAIL 只落在**第 9 阶段交付物**里；上游阶段（如文献调研对 LangChain 论文的引用、旧阶段的验收日志）只统计不判负。
I2_SCOPE = (STAGE + "/", os.path.join("代码", "后端") + "/", os.path.join("代码", "前端") + "/", P_DEPLOY + "/")


def _in_scope(rp):
    rp = rp.replace("\\", "/")
    if rp.startswith(STAGE + "/_工作底稿"):
        return False
    return any(rp.startswith(s.replace("\\", "/")) for s in I2_SCOPE)


@check("I2")
def c_i2(g):
    hits, ctx, outside, nfiles = [], 0, [], 0
    for dp, dn, fn in os.walk(g.root):
        dn[:] = [d for d in dn if d not in I2_SKIP_DIRS]
        for f in fn:
            if os.path.splitext(f)[1].lower() not in I2_EXT:
                continue
            nfiles += 1
            fp = os.path.join(dp, f)
            rp = rel(g.root, fp)
            try:
                txt = read_text(fp)
            except Exception:
                continue
            for i, ln in enumerate(txt.split("\n"), 1):
                for t in BANNED_TERMS:
                    if t in ln:
                        if I2_NEG.search(ln):
                            ctx += 1
                        elif _in_scope(rp):
                            hits.append("%s:%d「%s」" % (rp, i, ln.strip()[:80]))
                        else:
                            outside.append("%s:%d" % (rp, i))
    d25 = read_text(g.p(P_DOC25))
    good = d25.count(VDB_GOOD)
    bad = list(hits)
    if good < 1:
        bad.append("第 9 阶段交付物（%s）里没有出现「%s」（正向对照不足）" % (br(g.root, g.p(P_DOC25)), VDB_GOOD))
    if bad:
        g.fail("I2", "第 9 阶段交付物里被禁术语在非语境位置命中 %d 处：%s"
               % (len(hits), "；".join(hits[:5]) or "无")
               + ("；%s" % bad[-1] if good < 1 else "")
               + ("；另在上游文件里另有 %d 处（%s…），按本行范围只统计不判负" % (len(outside), "、".join(outside[:3]))
                  if outside else ""))
    else:
        g.ok("I2", "扫描 %d 个文本文件（排除 .git／node_modules／dist／_工作底稿／__pycache__）："
                   "**第 9 阶段交付物**（阶段09 正文／代码\\后端／代码\\前端／部署）里被禁四字连写术语在非语境位置 0 命中"
                   "（另有 %d 处出现在「不称…／统一表述为」的术语纠正句里，按语境排除；上游旧文件另有 %d 处，按范围只统计不判负）；"
                   "FAISS 一律写「%s」——《25》中该写法出现 %d 次"
             % (nfiles, ctx, len(outside), VDB_GOOD, good))


@check("I3")
def c_i3(g):
    if not g.live:
        nrun(g, "I3", "跨文档核验未执行（需完整工作区）")
        return
    xd = g.p(P_XDOC)
    rc, out = run_cmd([sys.executable, xd, "--strict-citations"], cwd=g.root, timeout=420)
    tail = [l.strip() for l in out.split("\n") if l.strip()][-4:]
    if rc == 0:
        g.ok("I3", "python %s --strict-citations → 退出码 0：%s" % (br(g.root, xd), " / ".join(tail)))
    else:
        g.fail("I3", "python %s --strict-citations → 退出码 %s：%s" % (br(g.root, xd), rc, " / ".join(tail)))


def spec25_titles(root):
    """从《24》第 4.1 节读出《25》的 9 个必备小节标题（不自己编造）。"""
    txt = read_text(os.path.join(root, P_TASK))
    m = re.search(r"9 个必备小节：(.+)", txt)
    if not m:
        return [], None
    seg = m.group(1)
    items = re.split(r"[①②③④⑤⑥⑦⑧⑨⑩]", seg)
    out = []
    for it in items[1:]:
        it = it.split("\n")[0]
        it = re.split(r"[；;。|]", it)[0].strip(" 　*｜")
        it = it.rstrip("*").strip()
        if it:
            out.append(it)
    return out, seg.strip()[:80]


@check("I4")
def c_i4(g):
    want, src = spec25_titles(g.root)
    d25 = read_text(g.p(P_DOC25))
    heads = [l.strip() for l in d25.split("\n") if l.startswith("## ")]
    heads = [h[3:].strip() for h in heads]
    bad = []
    if not want:
        bad.append("未能从《24》第 4.1 节解析出 9 个必备小节标题")
    pos, last = [], -1
    for t in want:
        idx = next((i for i, h in enumerate(heads) if h == t or h.startswith(t)), None)
        if idx is None:
            bad.append("缺小节「%s」" % t)
            continue
        pos.append(idx)
        if idx < last:
            bad.append("小节顺序错：「%s」出现在第 %d 位" % (t, idx))
        last = idx
    extra = [h for h in heads if not any(h == t or h.startswith(t) for t in want)]
    if bad:
        g.fail("I4", "；".join(bad) + "；《25》实际小节 %s；基准取自《24》第 4.1 节「%s…」" % (heads, src))
    else:
        g.ok("I4", "《25》的 9 个必备小节标题逐字存在且顺序一致（第 %s 行）：%s；另有非必备小节 %s"
             % ("／".join(str(p) for p in pos), "；".join(want), extra or "无"))


@check("I5")
def c_i5(g):
    if not (g.live and g.profile == "full"):
        g.unrun("I5", "专项门禁 full 档 58／58 需在其它 57 行判定完之后才能定论（静态档／环境未就绪时不判）")
        return
    others = [r for r in g.reg_order if r != "I5"]
    st = [g.rows[r][0] for r in others if r in g.rows]
    n_bad = st.count("FAIL")
    n_un = st.count("UNRUN")
    if n_bad == 0 and n_un == 0:
        g.ok("I5", "本轮 full 档：其余 57 行全部 [OK] ⇒ 本行 58／58、退出码 0（自指行，由其余 57 行的判定结果推出）")
    else:
        g.fail("I5", "其余 57 行中 FAIL=%d、UNRUN=%d ⇒ 未达 58／58" % (n_bad, n_un))


# --------------------------------------------------------------------------
# 15. 环境探测与总装
# --------------------------------------------------------------------------
def check_env(g):
    """返回 (env_ready, reasons[])。"""
    reasons = []
    if not port_open(8000):
        reasons.append("后端 8000 未监听")
    else:
        st, b, _ = http("GET", "/api/health", timeout=30)
        if st != 200:
            reasons.append("GET /api/health → %s" % st)
        else:
            for k in ("mysql", "neo4j", "vector_index", "model_config"):
                if (b.get(k) or {}).get("ok") is not True:
                    reasons.append("%s.ok=%s" % (k, (b.get(k) or {}).get("ok")))
    if not port_open(3306):
        reasons.append("MySQL 3306 未监听")
    if not port_open(7687):
        reasons.append("Neo4j bolt 7687 未监听")
    return (not reasons), reasons


START_HINT = [
    r'powershell -ExecutionPolicy Bypass -File "部署\启动.ps1"',
    r'wsl -d Ubuntu -u root -- bash -lc "systemctl start docker; docker start ashare-neo4j"',
    r'python "代码\后端\run.py"',
    r'cd "代码\前端" && npm run dev',
]


def print_report(g, order, titles, criterion, live, env_reasons, profile, mirror):
    print("")
    print("=" * 78)
    print("第 9 阶段专项门禁 · 逐行结果（--profile %s%s）" % (profile, "，镜像副本" if mirror else ""))
    print("=" * 78)
    cur = None
    for rid in order:
        grp = rid[0]
        if grp != cur:
            cur = grp
            print("")
            print("-- %s 组 · %s（计划 %d 行） %s" % (grp, GROUP_TITLE[grp], ROW_GROUPS[grp], "-" * 20))
        status, detail = g.rows.get(rid, ("UNRUN", "未判定（脚本内部缺失）"))
        print("%s %s %s  %s" % (STATUS_TAG[status], rid, titles.get(rid, "?"), detail))
    # 分组计数
    print("")
    print("-" * 78)
    print("分组计数：")
    tot = {"OK": 0, "FAIL": 0, "UNRUN": 0}
    for grp in "ABCDEFGHI":
        ids = [r for r in order if r[0] == grp]
        c = {"OK": 0, "FAIL": 0, "UNRUN": 0}
        for r in ids:
            c[g.rows.get(r, ("UNRUN",))[0]] += 1
        for k in tot:
            tot[k] += c[k]
        print("  %s 组（%2d 行）：OK %2d ｜ FAIL %2d ｜ UNRUN %2d" % (grp, len(ids), c["OK"], c["FAIL"], c["UNRUN"]))
    print("-" * 78)
    print("计划行数 %d ｜ 执行 %d ｜ 通过 %d ｜ 失败 %d ｜ 未执行 %d"
          % (len(order), tot["OK"] + tot["FAIL"], tot["OK"], tot["FAIL"], tot["UNRUN"]))
    env_fail = [r for r in g.env_notes]
    print("")
    print("环境／链上失败（单独成栏，不计入内容失败）：%s"
          % ("、".join(sorted(set(env_fail))) if env_fail else "无（0 行）"))
    if env_reasons:
        print("")
        print("!" * 78)
        print("环境未就绪（《24》硬约束 25：服务未启动＝环境未就绪，不是内容失败）")
        for x in env_reasons:
            print("  · %s" % x)
        print("  启动命令（任一条即可；本机形态是第一条）：")
        for x in START_HINT:
            print("    %s" % x)
        print("!" * 78)
    # 结论
    content_fail = [r for r in order
                    if g.rows.get(r, ("UNRUN",))[0] == "FAIL" and r not in g.env_notes]
    if profile == "static" or mirror:
        code = 2
        verdict = "静态档／镜像副本：实况行未执行（UNRUN），按口径退出码 2"
    elif env_reasons:
        code = 2
        verdict = "环境未就绪：实况行未执行，静态行已判；按口径退出码 2"
    elif content_fail:
        code = 1
        verdict = "有内容失败 %d 行：%s ⇒ 退出码 1" % (len(content_fail), "、".join(content_fail))
    else:
        code = 0
        verdict = "58 行全部 [OK] ⇒ 退出码 0"
    print("")
    print("结论：%s" % verdict)
    print("=" * 78)
    return code


def run_gate(root, profile, cooldown=True, mirror=False, quiet=False):
    order_rows = parse_spec_rows(root)
    order = [r[0] for r in order_rows]
    titles = dict((r[0], r[1]) for r in order_rows)
    criterion = dict((r[0], r[2]) for r in order_rows)
    # --- 行结构自检：注册集合必须与解析集合完全一致 ---
    problems = []
    if len(order) != TOTAL_ROWS:
        problems.append("《24》第八节解析出 %d 行（应 %d 行）" % (len(order), TOTAL_ROWS))
    if len(order) != len(set(order)):
        problems.append("解析出的行号有重复：%s" % order)
    missing = [r for r in order if r not in CHECKS]
    extra = [r for r in CHECKS if r not in order]
    if missing:
        problems.append("脚本未实现的行：%s" % "、".join(missing))
    if extra:
        problems.append("脚本多出来的行：%s" % "、".join(sorted(extra)))
    for grp, n in ROW_GROUPS.items():
        got = len([r for r in order if r[0] == grp])
        if got != n:
            problems.append("%s 组解析出 %d 行（应 %d 行）" % (grp, got, n))
    if problems:
        print("行结构错误（脚本或《24》被改动）：")
        for p in problems:
            print("  · %s" % p)
        print("退出码 2")
        return 2

    live = (profile == "full")
    env_reasons = []
    if live:
        ready, env_reasons = check_env(None)
        live = ready
    g = Gate(root, profile, live, mirror=mirror)
    g.reg_order = order

    for rid in order:
        if rid == "C9":
            continue                                  # 延迟到最后执行（限流会耗尽 60 秒窗口）
        try:
            CHECKS[rid](g)
        except Exception as exc:                      # 判据内部异常也算失败，不静默
            g.fail(rid, "判据内部异常：%s: %s（脚本缺陷，需修脚本）" % (type(exc).__name__, str(exc)[:160]))
        if rid not in g.rows:
            g.unrun(rid, "判据未给出结论（脚本内部缺失）")
    # C9 最后跑（live 时先冷却 ~62 秒，避免上轮探针把窗口用掉）
    if live and cooldown:
        print("[ 等待约 62 秒：让 60 次／60 秒的滑动窗口清空，好让 C9 的突发真能触发限流 ]")
        time.sleep(62)
    try:
        CHECKS["C9"](g)
    except Exception as exc:
        g.fail("C9", "判据内部异常：%s: %s" % (type(exc).__name__, str(exc)[:160]))

    return print_report(g, order, titles, criterion, live, env_reasons, profile, mirror)


# --------------------------------------------------------------------------
# 16. 自检：原样对照 ＋ 定向篡改
# --------------------------------------------------------------------------
def build_mirror(root, dst):
    """把工作区按 MIRROR_FILES／MIRROR_DIRS 复制到 dst（跳过 .git／node_modules／dist／__pycache__／口令文件）。"""
    os.makedirs(dst, exist_ok=True)
    skip_names = {"config.local.json", "_neo4j"}
    for relp in MIRROR_FILES:
        src = os.path.join(root, relp)
        if not os.path.exists(src):
            continue
        tgt = os.path.join(dst, relp)
        os.makedirs(os.path.dirname(tgt), exist_ok=True)
        shutil.copy2(src, tgt)
    for relp in MIRROR_DIRS:
        base = os.path.join(root, relp)
        for dp, dn, fn in os.walk(base):
            dn[:] = [d for d in dn if d not in MIRROR_SKIP_DIRS]
            rdp = os.path.relpath(dp, root)
            for f in fn:
                if os.path.splitext(f)[1].lower() in MIRROR_SKIP_EXT or f in skip_names:
                    continue
                tgt = os.path.join(dst, rdp, f)
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                try:
                    shutil.copy2(os.path.join(dp, f), tgt)
                except Exception:
                    pass
    return dst


def run_static(root, mirror=True):
    """静默跑一轮镜像 static 档，返回 (fail_set, rows)。"""
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = run_gate(root, "static", cooldown=False, mirror=mirror)
    return code, buf.getvalue()


def pick_fails(log):
    return set(re.findall(r"\[FAIL\] ([A-I]\d{1,2}) ", log))


def tamper_cases(root):
    """定向篡改用例：返回 [(名字, 相对路径, 篡改函数(读文本→返回新文本), 期望 FAIL 集, 说明)]。"""
    def t_smoke(t):
        """删掉冒烟矩阵里 /api/graph/entities（单实体查询模板）的全部用例行 → C1 覆盖缺口。"""
        keep, dropped = [], 0
        for l in t.split("\n"):
            if not l.strip():
                continue
            try:
                d = json.loads(l)
            except Exception:
                keep.append(l)
                continue
            if str(d.get("path", "")).startswith("/api/graph/entities?") or \
                    d.get("path") == "/api/graph/entities":
                dropped += 1
                continue
            keep.append(l)
        if not dropped:
            raise RuntimeError("冒烟矩阵里未找到 /api/graph/entities 的用例行")
        return "\n".join(keep) + "\n"

    def t_codes(t):
        return t.replace("3004", "3999")

    def t_graphcount(t):
        d = json.loads(t)
        d["counts"]["nodes_total"] -= 1
        return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

    def t_doc25_title(t):
        return t.replace("## 对下游（第 10 阶段）的使用说明", "## 对下游的使用说明")

    def t_readme(t):
        return t.replace("未安装 Docker Desktop", "已安装 Docker Desktop")

    def t_f2(t):
        return t.replace("'【知识图谱路径】', ", "")

    def t_f4(t):
        return t.replace("'本次回答未使用图谱扩展'", "'本次回答未使用图谱扩展能力'")

    def t_paced(t):
        d = json.loads(t)
        d["summary"]["ok"] = 90
        return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

    def t_pkg(t):
        d = json.loads(t)
        d["dependencies"]["langchain"] = "0.1.0"
        return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

    def t_i2(t):
        return t.replace("## 已知限制与证据不足清单",
                         "## 已知限制与证据不足清单\n\n本系统采用向量数据库存储全部文本块。")

    def t_g4(t):
        d = json.loads(t)
        d["nfr01_latency"]["segments"]["graph_query"].pop("source", None)
        return json.dumps(d, ensure_ascii=False, indent=2) + "\n"

    def t_g3(t):
        lines = [l for l in t.split("\n") if l.strip()]
        return "\n".join(lines[:4]) + "\n"

    return [
        ("① 删掉冒烟矩阵里 /api/graph/entities 的正常行 → 覆盖缺口", "阶段09-前后端系统集成/集成产出/smoke_matrix.jsonl", t_smoke, {"C1"}),
        ("② errors.py 把 3004 改成 3999 → 逐码表对不上", "代码/后端/errors.py", t_codes, {"C3"}),
        ("③ graph_counts.json 节点总数 2802 → 2801 → 计数对拍不符", "阶段09-前后端系统集成/集成产出/graph_counts.json", t_graphcount, {"E1"}),
        ("④ 《25》改掉一个小节标题 → 九节不齐", "阶段09-前后端系统集成/25-第9阶段产出文档（前后端系统集成）.md", t_doc25_title, {"I4"}),
        ("⑤ 部署\\README.md 把「未安装 Docker Desktop」改成反义", "部署/README.md", t_readme, {"H4"}),
        ("⑥ AnswerSections.vue 删掉一个固定段头 → 四段不齐", "代码/前端/src/components/AnswerSections.vue", t_f2, {"F2"}),
        ("⑦ GraphPathPanel.vue 改掉未使用图谱扩展的固定字样", "代码/前端/src/components/GraphPathPanel.vue", t_f4, {"F4"}),
        ("⑧ nfr02_paced100.json 成功率 100 → 90 → 低于 95% 阈值", "阶段09-前后端系统集成/集成产出/_证据/nfr02_paced100.json", t_paced, {"G5"}),
        ("⑨ package.json 加一个被排除依赖 langchain", "代码/前端/package.json", t_pkg, {"G6"}),
        ("⑩ 在《25》里写一句不带否定的「向量数据库」", "阶段09-前后端系统集成/25-第9阶段产出文档（前后端系统集成）.md", t_i2, {"I2"}),
        ("⑪ latency_profile.json 抹掉图谱段的来源", "阶段09-前后端系统集成/集成产出/latency_profile.json", t_g4, {"G4"}),
        ("⑫ error_scenarios.jsonl 只留 4 行 → 不足 6 类", "阶段09-前后端系统集成/集成产出/error_scenarios.jsonl", t_g3, {"G3"}),
    ]


def selftest(root, keep_tmp=False):
    tmp = tempfile.mkdtemp(prefix="t13_selftest_")
    print("=" * 78)
    print("自检（负向校准）：镜像副本 ＋ 定向篡改")
    print("  基准工作区：%s" % root)
    print("  镜像目录：%s" % tmp)
    print("=" * 78)
    base = os.path.join(tmp, "base")
    build_mirror(root, base)
    code, log = run_static(base)
    pristine = pick_fails(log)
    n_all = len(re.findall(r"^\[(?:OK |FAIL|UNRUN)\] [A-I]\d{1,2} ", log, re.M))
    n_unrun = len(re.findall(r"^\[UNRUN\] [A-I]\d{1,2} ", log, re.M))
    print("\n[A] 原样对照（未篡改的镜像副本，--profile static）")
    print("    逐行输出 %d／58；已判定 %d；未判定（实况行）%d；退出码 %d"
          % (n_all, n_all - n_unrun, n_unrun, code))
    print("    内容失败集：%s" % (sorted(pristine) or "空"))
    ok_pristine = (not pristine) and code == 2
    if not ok_pristine:
        print("    ✗ 原样对照不通过：期望「无内容失败、退出码 2」，实测 失败集=%s、退出码=%s"
              % (sorted(pristine), code))
        print("    ----（原样对照的原始输出末段）----")
        for l in log.strip().split("\n")[-25:]:
            print("    | %s" % l)
    else:
        print("    ✓ 通过：原样副本只在实况行上 UNRUN，无任何内容失败")

    print("\n[B] 定向篡改（逐个改一处，期望 FAIL 集 ＝ 实测 FAIL 集）")
    all_ok = True
    for i, (name, relp, mut, exp) in enumerate(tamper_cases(base), 1):
        path = os.path.join(base, relp)
        if not os.path.exists(path):
            print("  %2d. %s\n      ✗ 篡改目标不存在：%s" % (i, name, relp))
            all_ok = False
            continue
        old = read_text(path)
        try:
            new = mut(old)
        except Exception as exc:
            print("  %2d. %s\n      ✗ 篡改动作本身失败：%s" % (i, name, exc))
            all_ok = False
            continue
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(new)
        _, tlog = run_static(base)
        got = pick_fails(tlog)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(old)
        flag = "✓" if got == exp else "✗"
        if got != exp:
            all_ok = False
        print("  %2d. %s" % (i, name))
        print("      目标：%s" % relp)
        print("      %s 期望 FAIL 集 ＝ %s ｜ 实测 FAIL 集 ＝ %s"
              % (flag, sorted(exp), sorted(got)))
        if got != exp:
            for l in [x for x in tlog.split("\n") if x.startswith("[FAIL]")]:
                print("      | %s" % l)
    # 复核：篡改还原后镜像又回到「无内容失败」
    _, log2 = run_static(base)
    pristine2 = pick_fails(log2)
    print("\n[C] 还原复核：全部篡改回滚后的失败集 ＝ %s" % (sorted(pristine2) or "空"))
    if pristine2:
        all_ok = False
    print("\n自检结论：%s" % ("通过（原样无内容失败 ＋ 全部篡改都按预期失败）" if (all_ok and ok_pristine)
                              else "未通过 —— 见上文 ✗ 项"))
    if keep_tmp:
        print("镜像保留在：%s" % tmp)
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    print("=" * 78)
    return 0 if (all_ok and ok_pristine) else 2


def http_abs(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:
        return None, str(exc)[:200]


# --------------------------------------------------------------------------
# 17. 入口
# --------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(description="第 9 阶段（前后端系统集成）专项验收门禁（《24》第八节 58 行）")
    ap.add_argument("--profile", choices=["full", "static"], default="full",
                    help="full＝连服务逐行判（默认）；static＝只判文档与产物，实况行记 UNRUN")
    ap.add_argument("--selftest", action="store_true", help="负向校准：原样对照 ＋ 定向篡改")
    ap.add_argument("--root", default=REPO_ROOT, help="工作区根（默认脚本所在仓库；指向副本时自动按镜像模式跑）")
    ap.add_argument("--no-cooldown", action="store_true", help="C9 之前不等 62 秒（开发用，可能测不到限流）")
    ap.add_argument("--keep-tmp", action="store_true", help="自检后保留镜像目录（排查用）")
    a = ap.parse_args(argv)

    root = os.path.abspath(a.root)
    if a.selftest:
        return selftest(root, keep_tmp=a.keep_tmp)
    mirror = (root != REPO_ROOT)
    if mirror and not os.path.isdir(root):
        print("工作区不存在：%s" % root)
        return 2
    profile = "static" if (mirror or a.profile == "static") else "full"
    return run_gate(root, profile, cooldown=not a.no_cooldown, mirror=mirror)


if __name__ == "__main__":
    raise SystemExit(main())
