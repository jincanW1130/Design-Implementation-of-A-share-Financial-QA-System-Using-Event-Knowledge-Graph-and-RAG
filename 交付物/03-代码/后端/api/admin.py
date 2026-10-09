# -*- coding: utf-8 -*-
"""代码\\后端\\api\\admin.py —— 第 9 阶段后台能力接口（表 4-13 的十二条）。

| 方法 | 路径 | 用途 | 错误码 |
| --- | --- | --- | --- |
| POST | `/api/admin/documents` | 导入财经文本并切分 | 1002／1003 |
| GET | `/api/admin/documents` | 查询已入库文档 | 1002 |
| PUT | `/api/admin/documents/{doc_id}` | 修改文档并触发重新处理 | 1003／2001／2003 |
| DELETE | `/api/admin/documents/{doc_id}` | 删除文档并触发重新处理 | 2001／2003 |
| POST | `/api/admin/reprocess` | 触发一次重新处理流程 | 1002／2001 |
| GET | `/api/admin/consistency-check` | 运行一致性检查 | 3001／3003 |
| POST | `/api/admin/extraction/run` | 触发一次抽取任务 | 1002／1003／2001 |
| GET | `/api/admin/extraction/tasks/{task_id}` | 查询抽取任务状态与统计 | 2001 |
| GET | `/api/admin/extraction/events` | 按条件查询抽取到的事件 | 1002 |
| GET | `/api/admin/extraction/disambiguation` | 查询待消歧列表 | 1002 |
| POST | `/api/admin/extraction/disambiguation/{item_id}` | 人工确认消歧结果 | 1002／2001 |
| POST | `/api/admin/experiment/ask` | 按指定组别运行一次问答（受控实验入口） | 1001／1002／3002 |

本条路径下另有**一条兜底路由** `ANY /api/admin/{rest:path}`：未登记的 `/api/admin/*`
（路径拼错、前端误点）不回「未找到」这种容易与前缀混淆的响应，而是①普通用户一律
**4002**、②普通请求按**2001**（资源不存在）如实拒——这样「后台前缀不对普通用户开放」
这句话在整个前缀上都成立，而不只在我明确登记的那 12 条上成立（见第 2 节）。

十条纪律
--------
1. **4002 的落点**（《24》硬约束与表 4-13「后台一栏不对普通用户开放」）：本项目第一版
   **不启用登录**，故按**路径前缀**实现，且**不改 `main.py`**——守卫做成挂在
   `router` 上的路由级依赖 `require_admin`（`api\\admin.py` 内的 `router` 由
   `main.register_optional_routers` 以 `/api/admin` 前缀挂载，依赖随路由生效，
   连兜底路由与 `experiment/ask` 一并覆盖）。
   判「普通用户」的依据是**浏览器来源标记**：请求带 `Origin` 且落在 `config.CORS_ORIGINS`
   内（即来自前端 5173 页面），或 `Referer` 指向该来源，或显式带 `X-Client-Role: user`。
   裸 `curl`（无这些头）视为运维／实验通道，照常放行——**校验清单里的 curl 因此可用**，
   而前端页面发起的调用一律 403。**已知局限（如实登记）**：无登录 ⇒ 这些头可伪造，
   4002 只能挡住「前端普通用户通道」，挡不住有意伪造头的人；真正的鉴权要等启用登录
   （`user` 表与 4001 一并启用）之后才成立。
2. **2003 的响应体是本项目唯一的例外**：《10》第 4.7.3 节逐字要求「响应同时返回
   `retained_for_history = true`」，而表 4-13 又把 `retained_for_history（布尔）` 列为
   PUT／DELETE 的响应字段。故 2003 的响应体是 `{code, message, retained_for_history}`
   ——比「错误响应键集合恰为 `{code, message}`」（硬约束 7）多一个**被设计文档明确要求**
   的布尔字段，且**只此一处**；其余错误一律严守 `{code, message}`。以
   `starlette.responses.JSONResponse` 直接构造，不改 `errors.py`。
3. **上游只读**：切分**直接复用**第 5 阶段的 `代码\\数据准备\\chunk.py`
   （`chunk_document()`）与 `代码\\数据准备\\config.py` 的 `CHUNK` 参数
   （target 400／max 512／min 128／overlap 50／boundary_priority），**一字不改、不抄参数**；
   `chunk.py` 顶部有 `import config`，故加载时把第 5 阶段的 config 临时装进
   `sys.modules["config"]`（用完立刻还原，`sys.path` 同样还原）——与
   `services\\graph_service.py` 加载检索侧 config 用的是同一套「换名装载」手法。
   文本块编号同样走第 5 阶段的 `config.chunk_id_for(doc_id, i) = doc_id*1000 + i`。
4. **任务只登记、不假装跑过**：`reprocess`／`extraction/run` 需要模型调用与向量索引重建，
   属第 5／6 阶段能力，本阶段**不实际重跑**。两个接口按「任务记录」实现：写一条台账
   （落 `config.WORK_DIR`，与 `qa_runs` 同属运行留痕、不入库）＋ 返回 `accepted` ＋ 一句
   明确的 `note`（说明没有真跑、真跑该走哪条命令），**不谎报 running／不编造统计数字**。
5. **一致性检查的读数是实读**：`chunk_count` 实查 MySQL，`vector_count` 取
   `build_meta.json` 的 `vector_count` **并**实点 `vector_map.jsonl` 行数（两者不一致也如实
   报出），图谱计数走 `graph_service` 的后端（不可用 → 3001）。`diff` 里逐项给出**差值**，
   `is_consistent` 只在全部差值为 0 时为 true；上游 `graph_stats.json` 只作**旁证**列出，
   不用它替代实测。
6. **待消歧与跳过边的数量来自实际数据**（不写死）：待消歧列表读第 6 阶段落盘的
   `消歧\\unresolved.jsonl`（逐行），跳过边与已确认数读 `graph_stats.json` 的
   `unresolved`／`human_confirmation` 小节，并在响应里带上**出处路径**与其 `sha256`／行数。
   **口径必须与现行图谱一致**（2026-10-05 修补）：v1.3 起消歧产物落 `图谱管线_v1_3\\` 而非
   `图谱管线\\`，故「现行口径的待消歧清单在哪」**按第 6 阶段 `GRAPH_PIPELINE` 的
   `profile_roots` 映射推导**，不在本文件写死目录名（见 `_pipeline_map()`）。降级链保留
   （环境变量 → 现行 profile → 按目录名直拼 → 其余 profile／缓存目录），但**降级不再静默**：
   落到非现行口径时响应体里给出 `degraded`／`degraded_reason`／`source_version`／
   `expected_source`，调用方一眼看得见用的是哪一版的数据（此前只写日志，调用方看不到）。
7. **人工确认不回写上游**：`POST /api/admin/extraction/disambiguation/{item_id}` 只往
   本项目自己的台账追加一条确认记录并返回新状态；**不改** `unresolved.jsonl`、不改
   `人工确认清单.json`、不重建图谱（重建要走第 6 阶段 `write_graph.py`，本阶段不动上游）。
8. **`POST /api/admin/experiment/ask` 是唯一的 A～E 组入口**（《10》4.7.1 末段：分组切换
   能力只存在于受控实验入口）。它复用 `qa_service.ask(question, session_id, group)`，
   返回与 `/api/qa/ask` **同一形状**的载荷，另加 `experiment_group` 与**配置快照**；
   `/api/qa/ask` 的「不许出现分组字段」规矩（硬约束 9）在那边依旧有效，两者互不影响。
9. **不新增依赖、不用 ORM、`rank` 加反引号**：全部显式 SQL（`rank` 在本文件里只出现在
   `SELECT COUNT(*)` 里、不裸写列名，仍按 `\\`rank\\`` 的规矩处理）；不引第三方库。
10. **响应体纪律**：成功一律 `errors.ok(...)`／`errors.ok_page(...)` 信封（表 4-13 的
    示例给的是 `data` 内的字段，信封由本项目既定约定统一加，与既有三条接口一致）；
    错误体恰为 `{code, message}`（2003 见第 2 条）。`detail` 只进日志。
"""

from __future__ import annotations

import asyncio
import csv
import importlib.util
import json
import os
import sys
import threading
from datetime import datetime

from fastapi import APIRouter, Body, Depends, Request
from starlette.responses import JSONResponse

import config
import db
import errors
from api import graph as graph_api
from services import graph_service as gs

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

logger = errors.logger

# --------------------------------------------------------------------------
# 0. 复用图谱接口层的既有工具（校验／分页／时间归一／事件整形／图谱后端）
#    —— 同一套口径只写一遍：参数怎么算非法、时间怎么归一、事件条目有哪些字段，
#       在 `/api/graph/*` 与 `/api/admin/*` 上必须一模一样。
# --------------------------------------------------------------------------
_s = graph_api._s                                    # noqa: SLF001（同包内复用）
_parse_int = graph_api._parse_int                    # noqa: SLF001
_page_args = graph_api._page_args                    # noqa: SLF001
_time_bound = graph_api._time_bound                  # noqa: SLF001
_check_event_type = graph_api._check_event_type      # noqa: SLF001
_event_item = graph_api._event_item                  # noqa: SLF001
_events_in_window = graph_api._events_in_window      # noqa: SLF001
reader = graph_api.reader
GraphReader = graph_api.GraphReader

PAGE_SIZE_MAX = graph_api.PAGE_SIZE_MAX              # 200
DEFAULT_PAGE_SIZE = graph_api.DEFAULT_PAGE_SIZE      # 20

# --------------------------------------------------------------------------
# 1. 常量：取值全部有出处，不写死
# --------------------------------------------------------------------------
CATEGORIES = None
"""第 5 阶段的四类 `category`（**只用于审计告警**，不用于拒收，理由见下）。"""

SCOPES = ("document", "chunk", "all")
"""`scope` 的合法取值（表 4-13 的 `document／chunk／all`）。"""

TASK_KINDS = ("doc_ingest", "reprocess", "extraction")
"""三类后台任务：导入即触发重处理／手工触发重处理／抽取。"""

TASK_PREFIX = {"doc_ingest": "RP", "reprocess": "RP", "extraction": "EX"}
"""台账编号前缀（与《10》4.7.3 示例的 `RP-…`／`EX-…` 同形）。"""

DOC_REQUIRED = ("title", "content", "source", "publish_time")
DOC_OPTIONAL = ("url", "category", "company_list")
DOC_ALLOWED = frozenset(DOC_REQUIRED + DOC_OPTIONAL)

DOC_TITLE_MAX = 512                # document.title VARCHAR(512)
DOC_SOURCE_MAX = 128               # document.source VARCHAR(128)
DOC_URL_MAX = 1024                 # document.url VARCHAR(1024)
DOC_CATEGORY_MAX = 64              # document.category VARCHAR(64)
DOC_COMPANY_LIST_MAX = 512         # document.company_list VARCHAR(512)

TASK_LEDGER = os.path.join(config.WORK_DIR, "后台任务台账.jsonl")
"""任务台账（`reprocess`／`extraction/run`／导入触发的重处理）。落 `_工作底稿` 而非
`集成产出`：它是**运行留痕**（与 `qa_runs` 同性质），不是本阶段的交付物。"""

DISAMBIG_LEDGER = os.path.join(config.WORK_DIR, "消歧人工确认台账.jsonl")
"""人工确认台账（只记确认动作，不回写上游；见第 7 条纪律）。"""

_UNRESOLVED_PATH = None
"""待消歧原始清单（第 6 阶段落盘物），惰性定位并在响应里报出实际路径。"""

_UNRESOLVED_STATE: dict = {}
"""上一次定位的**如实状态**（来源 profile／版本／是否降级／降级原因）。

与 `_UNRESOLVED_PATH` 同时写入，并由 `/api/admin/extraction/disambiguation` **整块回给
调用方**。此前降级只写 `logger.warning`：调用方看不到日志，等于被静默换掉了数据源
（旧版本照样返回 200 与一份看起来正常的列表），故这一块是修补的重点。
"""


# --------------------------------------------------------------------------
# 1.1 现行口径的图谱管线工作目录：**取第 6 阶段的 profile → 目录映射**，不写死目录名
# --------------------------------------------------------------------------
_STAGE6_DIR = os.path.join(config.CODE_DIR, "抽取与图谱")
_STAGE6_CACHE: dict = {}
_STAGE6_LOCK = threading.Lock()


def _stage6_config():
    """按**文件路径**装载第 6 阶段的 `config.py`，取其目录常量；取不到返回 None。

    **为什么不 `import config`**：`代码\\检索\\`／`代码\\问答\\`／第 5 阶段／本后端**各有
    一个 `config.py`**，而这些模块内部一律写 `import config`（靠 `sys.path` 解析）——究竟
    哪一个生效取决于导入顺序与 `sys.modules` 的既存项，`代码\\问答\\run_answer.py` 开头
    第 29～33 行已把这个坑记在案。故这里沿用本文件 `_stage5_config()` 的同一套「换名装载」
    手法：按**文件路径**装载、注册成唯一模块名 `_stage9_stage6_config`，期间不动 `sys.path`、
    不碰 `sys.modules["config"]`。第 6 阶段的 `config.py` 顶部只 import 标准库
    （`hashlib`／`json`／`os`／`re`），装载它既不顶掉后端自己的 `config`，也不产生文件或
    网络副作用（已核：装载前后该目录文件清单不变、`sys.modules` 里不出现裸名 `config`）。
    取不到时**不猜**：返回 `None`，调用方按老路走并在响应里如实标注。
    """
    with _STAGE6_LOCK:
        if _STAGE6_CACHE.get("loaded"):
            return _STAGE6_CACHE.get("cfg")
        _STAGE6_CACHE["loaded"] = True
        cfg_path = os.path.join(_STAGE6_DIR, "config.py")
        if not os.path.isfile(cfg_path):
            logger.warning("第 6 阶段参数文件缺失，图谱管线目录映射不可用：%s", cfg_path)
        else:
            try:
                _STAGE6_CACHE["cfg"] = _load_file_module("_stage9_stage6_config", cfg_path)
            except Exception as exc:                            # noqa: BLE001
                logger.warning("装载第 6 阶段 config.py 失败（待消歧清单改按目录名直拼）：%s: %s",
                               type(exc).__name__, exc)
        return _STAGE6_CACHE.get("cfg")


def _pipeline_map() -> tuple:
    """返回 `(现行 profile, {profile: 图谱管线工作目录}, {profile: 图谱版本口径})`。

    第 6 阶段常量取不到时返回 `("", {}, {})`——调用方走老路并在响应里标注。

    **现行 profile 的判定不是猜**：在 `export_roots`（profile → 图谱导出目录）里找
    「目录名恰好等于后端 `config.GRAPH_VERSION`」的那一项——`v21_v1_3` 的导出目录是
    `图谱导出\\v2.1_v1_3`，目录名正是 `v2.1_v1_3`。于是两份常量一旦分叉（例如版本升到
    v1.4），本函数**跟着变**，不需要在这里改一个字；万一没有唯一命中，再按 profile 名的
    确定性折算（`v2.1_v1_3` → `v21_v1_3`，只去点）补一次；仍不唯一就返回空 profile。
    """
    cfg6 = _stage6_config()
    if cfg6 is None:
        return "", {}, {}
    pipeline = getattr(cfg6, "GRAPH_PIPELINE", None) or {}
    roots = {k: v for k, v in (pipeline.get("profile_roots") or {}).items() if _s(v).strip()}
    versions = {k: os.path.basename(v)
                for k, v in (pipeline.get("export_roots") or {}).items() if _s(v).strip()}
    want = _s(config.GRAPH_VERSION).strip()
    hit = sorted(k for k, label in versions.items() if want and label == want)
    if len(hit) != 1:
        folded = want.replace(".", "")
        hit = sorted(k for k in roots if folded and k.replace(".", "") == folded)
    return (hit[0] if len(hit) == 1 else ""), roots, versions


def _cache_rel(path: str, cache_root: str) -> str:
    """`_抽取缓存` 下的相对落点（如 `v2.1_v1_2\\图谱管线_v1_3`）；不在其下则原样返回。"""
    try:
        rel = os.path.relpath(path, cache_root)
    except ValueError:                                          # 跨盘符等（本工程不会走到）
        return path
    return path if rel.startswith("..") else rel


def _unresolved_candidates(cache_root: str) -> list:
    """按优先级列出待消歧清单的候选，每项 `{path, kind, profile, version, pipeline}`。

    * `kind="env"`     —— 环境变量 `ASHARE_UNRESOLVED` 显式指定（运维通道，最高优先）；
    * `kind="current"` —— **现行 profile 的图谱管线工作目录**（由第 6 阶段映射给出，
      `v21_v1_3` → `_抽取缓存\\v2.1_v1_2\\图谱管线_v1_3`；v1.3 起消歧产物不再落
      `图谱管线\\`，而与 v1.2 的那一套物理分开）；
    * `kind="by_name"` —— 老口径的 `_抽取缓存\\<GRAPH_VERSION>\\图谱管线\\` 按目录名直拼
      （映射取不到时它就是正路；映射取得到时它是同一条路的等价写法）；
    * `kind="sibling"` —— 其余 `_抽取缓存\\*` 下的同名文件（**降级档**，逐级回落）。
      **扫描范围与原实现一致**：只在缓存根下扫；`pilot` 那一套试跑目录
      （`阶段06-…\\_试跑_图谱管线`）**不进来**——试跑产物不是任何一版交付口径，
      把它当降级来源等于凭空多出一档数据源（本函数初版补给 `sibling` 时曾误纳，
      由 `决策者核验\\核验_消歧降级可见性.py` 的第 ④ 项核出）。

    降级链**保留**原样，只是每回落一档都会在响应里被标出来（见 `_unresolved_state_of`）。
    目录名一个都没有写死：`图谱管线_v1_3` 这一档来自第 6 阶段的 `GRAPH_PIPELINE`。
    `version` 只在**能从既有常量或路径如实推出**时才给（映射反查命中 → 该 profile 的导出
    目录名；否则 `图谱管线\\` 这一档取数据集目录名），推不出就留空——`source_pipeline`
    无论如何都给出真实落点，不靠猜。
    """
    env = os.environ.get("ASHARE_UNRESOLVED") or ""
    profile, roots, versions = _pipeline_map()
    root_by_dir = {os.path.normcase(os.path.abspath(v)): k for k, v in roots.items()}
    out, seen = [], set()

    def add(path, kind, prof, version):
        if not path:
            return
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            return
        seen.add(key)
        out.append({"path": path, "kind": kind, "profile": prof, "version": version or "",
                    "pipeline": _cache_rel(os.path.dirname(os.path.dirname(path)), cache_root)})

    def label(pipeline_dir):
        """该管线目录的版本口径标签：先反查第 6 阶段映射，再按目录名如实取。"""
        prof = root_by_dir.get(os.path.normcase(os.path.abspath(pipeline_dir)), "")
        if prof:
            return prof, versions.get(prof) or ""
        sub = os.path.basename(pipeline_dir)
        if sub == "图谱管线":                       # `<数据集版本目录>\图谱管线\` 的老口径
            return "", os.path.basename(os.path.dirname(pipeline_dir))
        return "", ""

    _p, _v = label(os.path.dirname(os.path.dirname(env))) if env else ("", "")
    add(env, "env", _p, _v)
    if profile and roots.get(profile):
        add(os.path.join(roots[profile], "消歧", "unresolved.jsonl"), "current", profile,
            versions.get(profile))
    by_name_dir = os.path.join(cache_root, config.GRAPH_VERSION, "图谱管线")
    _p, _v = label(by_name_dir)
    add(os.path.join(by_name_dir, "消歧", "unresolved.jsonl"), "by_name", _p, _v)
    if os.path.isdir(cache_root):
        for name in sorted(os.listdir(cache_root)):
            base = os.path.join(cache_root, name)
            if not os.path.isdir(base):
                continue
            for sub in sorted(os.listdir(base)):
                if sub == "图谱管线" or sub.startswith("图谱管线"):
                    pipeline_dir = os.path.join(base, sub)
                    _p, _v = label(pipeline_dir)
                    add(os.path.join(pipeline_dir, "消歧", "unresolved.jsonl"), "sibling",
                        _p, _v)
    return out


def _unresolved_state_of(hit: dict, candidates: list) -> dict:
    """把「命中的是谁、现行该是谁、有没有降级、为什么」如实算出来（只**新增**字段）。"""
    profile, _roots, versions = _pipeline_map()
    expected = (next((c for c in candidates if c["kind"] == "current"), None)
                or next((c for c in candidates if c["kind"] == "by_name"), None))
    expected_source = (expected or {}).get("path")
    same = bool(expected_source) and (os.path.normcase(os.path.abspath(hit["path"]))
                                      == os.path.normcase(os.path.abspath(expected_source)))
    degraded = not same
    reason = None
    if degraded:
        bits = []
        if expected_source:
            bits.append("现行口径（profile=%s／图谱版本=%s）的待消歧清单不在位：%s"
                        % (profile or "第 6 阶段目录映射未取到", config.GRAPH_VERSION,
                           expected_source))
        else:
            bits.append("现行口径（图谱版本=%s）的目录映射未取到，按既有降级链回落"
                        % config.GRAPH_VERSION)
        if hit["kind"] == "env":
            bits.append("实际来源由环境变量 ASHARE_UNRESOLVED 指定（运维通道，可能不是现行口径）")
        else:
            bits.append("已回落至 %s（kind=%s，来源落点 %s）"
                        % (hit["path"], hit["kind"], hit["pipeline"] or "未知"))
        bits.append("不同口径的待消歧条数、跳过边数、已确认边数都不同，本次读数**不代表现行口径**")
        reason = "；".join(bits)
    return {
        "source_profile": hit.get("profile") or None,
        "source_version": hit.get("version") or None,
        "source_pipeline": hit.get("pipeline") or None,
        "expected_profile": profile or None,
        "expected_version": versions.get(profile) or None,
        "expected_source": expected_source,
        "degraded": degraded,
        "degraded_reason": reason,
    }


def _unresolved_source() -> dict:
    """`_UNRESOLVED_STATE` 的只读副本（先确保已定位过，再取）。"""
    _unresolved_path()
    return dict(_UNRESOLVED_STATE)


def _unresolved_path() -> str:
    """定位第 6 阶段落盘的待消歧清单；取不到时按 3003（索引／数据不可用）如实报。

    **目录名不写死**：现行口径的图谱管线工作目录取第 6 阶段 `config.GRAPH_PIPELINE` 的
    `profile_roots` 映射推导（见 `_pipeline_map()`）。找到即用，并把**实际路径**与**来源
    口径**一起回给调用方（响应里带 `source`／`source_version`／`source_pipeline`）。

    优先级（降级链，逐级回落）：环境变量 `ASHARE_UNRESOLVED` → 现行 profile 的图谱管线目录
    → 按 `<config.GRAPH_VERSION>\\图谱管线\\` 直拼 → 其余 `_抽取缓存\\*` 下的同名文件。

    **降级可见**：落到非现行口径时，`_UNRESOLVED_STATE` 给出 `degraded=true` 与
    `degraded_reason`（含现行口径应有的路径），响应体一并带回，不再只写日志——调用方看不到
    日志，静默降级的后果就是「拿旧版本的数据冒充当期数据」，这正是本函数此前的问题。
    候选全都探不到就报错，而不是回一个空列表——「查不到文件」与「没有待消歧项」是两件事。
    """
    global _UNRESOLVED_PATH                                    # noqa: PLW0603
    if _UNRESOLVED_PATH:
        return _UNRESOLVED_PATH
    cache_root = os.path.join(config.ROOT, "交付物/04-数据与知识图谱/数据准备", "数据集", "_抽取缓存")
    candidates = _unresolved_candidates(cache_root)
    hit = next((c for c in candidates if os.path.isfile(c["path"])), None)
    if hit is None:
        raise errors.ApiError(3003, detail="待消歧清单 unresolved.jsonl 未找到（候选 %d 处，"
                              "可用环境变量 ASHARE_UNRESOLVED 指定）" % len(candidates))
    _UNRESOLVED_PATH = hit["path"]
    _UNRESOLVED_STATE.clear()
    _UNRESOLVED_STATE.update(_unresolved_state_of(hit, candidates))
    if hit["kind"] == "env":
        logger.info("待消歧清单由环境变量 ASHARE_UNRESOLVED 指定：%s", hit["path"])
    elif _UNRESOLVED_STATE["degraded"]:
        logger.warning("未找到与图谱口径（%s）同批的待消歧清单 %s，降级使用 %s"
                       "（来源口径 %s）——不同口径的待消歧条数不同，请核对",
                       config.GRAPH_VERSION, _UNRESOLVED_STATE["expected_source"], hit["path"],
                       _UNRESOLVED_STATE["source_version"]
                       or _UNRESOLVED_STATE["source_pipeline"])
    return hit["path"]


def _graph_stats() -> tuple:
    """读上游 `graph_stats.json`（**只读旁证**），返回 `(数据, 路径)`。"""
    path = config.GRAPH_STATS_PATH
    if not os.path.isfile(path):
        raise errors.ApiError(3001, detail="图谱统计文件不存在：%s" % path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh), path
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("graph_stats.json 解析失败：%s", exc)
        raise errors.ApiError(3001, detail="图谱统计文件不可解析：%s: %s"
                              % (type(exc).__name__, exc))


# --------------------------------------------------------------------------
# 2. 4002 守卫：后台前缀不对普通用户开放（本项目第一版不启用登录，按路径前缀实现）
# --------------------------------------------------------------------------
CLIENT_ROLE_HEADER = "x-client-role"
"""显式声明身份的请求头（前端普通用户通道会带上；运维／实验脚本不带）。"""

USER_ROLES = frozenset({"user", "anonymous", "guest", "visitor", "public", "normal",
                        "普通用户", "用户"})
"""`X-Client-Role` 里表示「普通用户」的取值（大小写不敏感）。"""


def _ordinary_user_reason(request: Request) -> str | None:
    """判断是否来自「普通用户通道」；是则给出可写进日志的理由，否则 None。

    三条依据（任一命中即普通用户）：
      1. `X-Client-Role` 是 `user` 一类取值；
      2. `Origin` 落在 `config.CORS_ORIGINS` 内（前端页面跨域调用必经此关）；
      3. `Referer` 以某个允许来源开头（同源部署时浏览器不给 `Origin`，给 `Referer`）。
    """
    role = _s(request.headers.get(CLIENT_ROLE_HEADER)).strip().lower()
    if role in USER_ROLES:
        return "请求头 %s: %s" % (CLIENT_ROLE_HEADER, role)
    origins = [o.rstrip("/") for o in config.CORS_ORIGINS]
    origin = _s(request.headers.get("origin")).strip().rstrip("/")
    if origin and origin in origins:
        return "来源页 %s（前端普通用户通道）" % origin
    referer = _s(request.headers.get("referer")).strip()
    if referer:
        for allowed in origins:
            if referer == allowed or referer.startswith(allowed + "/"):
                return "来源页 %s（前端普通用户通道）" % referer
    return None


async def require_admin(request: Request) -> None:
    """路由级依赖：普通用户访问 `/api/admin/*` 一律 **4002**（HTTP 403）。

    `detail` 只进日志（硬约束 7）；响应体由 `errors.install_exception_handlers`
    统一成 `{code: 4002, message: "无操作权限"}`。
    """
    reason = _ordinary_user_reason(request)
    if reason:
        logger.warning("后台接口拒绝普通用户：path=%s %s（第一版无登录，按来源标记判定）",
                       request.url.path, reason)
        raise errors.ApiError(4002, detail="普通用户通道访问后台接口：%s" % reason)


router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])
"""全部后台路由都挂 `require_admin`（含下方兜底路由与 `experiment/ask`）。"""

# 本模块没有跨前缀的接口：`/api/config/meta` 归 `api\\qa.py`、`/api/documents/…` 归
# `api\\evidence.py`。此处显式给出空元组，便于 `main.register_optional_routers` 统一取用。
extra_routers = ()


# 兜底路由 `/{rest:path}` 定义在**模块末尾**（见文件最后）：Starlette 按注册顺序
# 首个匹配即命中，若把它写在具体路由之前会把 12 条接口全部吞掉（本模块初版即踩过此坑）。


# --------------------------------------------------------------------------
# 3. 小工具：时间、校验、台账
# --------------------------------------------------------------------------
def _now() -> datetime:
    """当前本地时间（秒级）。"""
    return datetime.now()


def _now_iso() -> str:
    return _now().isoformat(timespec="seconds")


def _parse_dt(raw, name: str, required: bool = True):
    """时间参数 → `datetime`；缺失按 `required` 决定是否 1003，非法一律 1002。

    接受 `2025-03-05T18:30:00`／`2025-03-05 18:30:00`／`2025-03-05` 三种写法
    （与《10》4.7.3 示例的 ISO 8601 一致，空格分隔也容忍）。
    """
    text = _s(raw).strip()
    if not text:
        if required:
            raise errors.ApiError(1003, detail="必填字段 %s 缺失或为空" % name)
        return None
    norm = text.replace(" ", "T")
    if norm.endswith("Z"):
        norm = norm[:-1]
    try:
        parsed = datetime.fromisoformat(norm)
    except ValueError:
        raise errors.ApiError(1002, detail="%s 不是合法时间（%r）：应为 ISO 8601（如 2025-03-05T18:30:00）"
                              % (name, raw))
    return parsed.replace(tzinfo=None)


def _check_text(raw, name: str, max_chars: int) -> str:
    """取一个受长度上限约束的字符串字段：空 → 1003；超长 → 1002（列宽即上限）。"""
    text = _s(raw).strip()
    if not text:
        raise errors.ApiError(1003, detail="必填字段 %s 缺失或为空" % name)
    if len(text) > max_chars:
        raise errors.ApiError(1002, detail="%s 长度 %d 超过列宽上限 %d"
                              % (name, len(text), max_chars))
    return text


def _check_scope(raw, required: bool = True) -> str | None:
    """`scope` 必须是 `document／chunk／all`；缺失按 `required` 决定是否 1002。"""
    text = _s(raw).strip()
    if not text:
        if required:
            raise errors.ApiError(1002, detail="缺少 scope（或为空）：只能是 %s"
                                  % "／".join(SCOPES))
        return None
    if text not in SCOPES:
        raise errors.ApiError(1002, detail="scope=%r 不在 %s 之内"
                              % (raw, "／".join(SCOPES)))
    return text


def _col(name: str, alias: str | None = None) -> str:
    """拼一个**带反引号**的列名（`alias` 非空则加表别名）。

    本项目要求 SQL 里的保留字／关键字一律反引号包裹（`rank`、`user`；见
    `schema\\六张表.sql` 的落盘约定），故所有列名统一走这里拼，不靠手写——
    `rank` 这类列名一旦裸写就是语法错误。
    """
    return "%s.`%s`" % (alias, name) if alias else "`%s`" % name


def _check_doc_ids(raw) -> list:
    """`doc_ids`（可选）：必须是整数数组；元素非法 → 1002，不存在 → 2001。"""
    if raw is None or raw == "":
        return []
    if not isinstance(raw, (list, tuple)):
        raise errors.ApiError(1002, detail="doc_ids 必须是整数数组，收到 %s"
                              % type(raw).__name__)
    ids = []
    for item in raw:
        try:
            ids.append(int(item))
        except (TypeError, ValueError):
            raise errors.ApiError(1002, detail="doc_ids 含非整数元素：%r" % (item,))
    known = {int(r["doc_id"]) for r in db.query("SELECT doc_id FROM document")}
    unknown = sorted(set(ids) - known)
    if unknown:
        raise errors.ApiError(2001, detail="doc_ids 含不存在的文档：%s"
                              % "、".join(str(x) for x in unknown))
    return ids


def _read_ledger(path: str) -> list:
    """读台账（JSONL）；坏行只记日志、不抛（台账是留痕，不是权威数据源）。"""
    if not os.path.isfile(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except Exception:                                  # noqa: BLE001
                logger.warning("台账第 %d 行不是合法 JSON，已跳过：%s", line_no, path)
    return rows


_LEDGER_LOCK = threading.Lock()


def _append_ledger(path: str, record: dict) -> None:
    """追加一条台账记录（`encoding="utf-8"`、`newline="\\n"`、写完 flush）。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with _LEDGER_LOCK:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=False) + "\n")
            fh.flush()


def _next_task_id(kind: str) -> str:
    """当日流水号：`RP-YYYYMMDD-0001` 起（台账里同日同前缀的记录数 + 1）。"""
    prefix = TASK_PREFIX.get(kind, "TK")
    today = _now().strftime("%Y%m%d")
    head = "%s-%s-" % (prefix, today)
    used = sum(1 for r in _read_ledger(TASK_LEDGER)
               if _s(r.get("task_id")).startswith(head))
    return "%s%04d" % (head, used + 1)


def _record_task(kind: str, *, scope=None, doc_ids=None, prompt_version=None,
                 doc_id=None, note="", counters=None) -> dict:
    """写一条任务台账并返回该记录（**只登记，不执行**；见纪律 4）。"""
    task_id = _next_task_id(kind)
    record = {
        "task_id": task_id,
        "kind": kind,
        "status": "accepted",
        "created_at": _now_iso(),
        "scope": scope,
        "doc_ids": list(doc_ids or []),
        "doc_id": doc_id,
        "prompt_version": prompt_version,
        "processed_chunks": 0,
        "entity_count": 0,
        "event_count": 0,
        "relation_count": 0,
        "merge_log_count": 0,
        "executed": False,
        "note": note or NOT_RUN_NOTE,
    }
    if counters:
        record.update(counters)
    _append_ledger(TASK_LEDGER, record)
    logger.info("后台任务已登记：%s kind=%s scope=%s doc_ids=%s（第一版只登记、不执行）",
                task_id, kind, scope, record["doc_ids"])
    return record


NOT_RUN_NOTE = ("第一版：本接口只登记任务记录，不实际重新运行抽取与向量化"
                "（重跑需要模型调用与向量索引重建，属第 5／6 阶段能力，本阶段对上游只读）。"
                "台账落盘于 交付物/05-系统实现/前后端系统集成\\_工作底稿\\后台任务台账.jsonl。")


# --------------------------------------------------------------------------
# 4. 第 5 阶段切分能力的只读复用（chunk.py ＋ config.py）
# --------------------------------------------------------------------------
_STAGE5_DIR = os.path.join(config.CODE_DIR, "数据准备")
_STAGE5_CACHE: dict = {}
_STAGE5_LOCK = threading.Lock()


def _load_file_module(mod_name: str, path: str):
    """按文件路径装载一个模块（不写 `sys.path`、不改上游文件）。"""
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError("无法为 %s 建立装载器" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def _stage5_config():
    """只装载第 5 阶段的 `config.py`（**纯参数、无副作用**，导入期即可用）。"""
    with _STAGE5_LOCK:
        if _STAGE5_CACHE.get("cfg") is None:
            cfg_path = os.path.join(_STAGE5_DIR, "config.py")
            if not os.path.isfile(cfg_path):
                raise errors.ApiError(9999, detail="第 5 阶段参数文件缺失：%s" % cfg_path)
            _STAGE5_CACHE["cfg"] = _load_file_module("_stage9_stage5_config", cfg_path)
        return _STAGE5_CACHE["cfg"]


def _stage5():
    """惰性装载第 5 阶段的 `chunk.py`，返回 `(cfg, chunk_mod, tokenizer, 计数口径说明)`。

    `chunk.py` 顶部有 `import config`（它只认「名为 config 的那个模块」），故装载期间
    把第 5 阶段的 config 临时放进 `sys.modules["config"]`，装完立刻还原——否则后端自己的
    `config` 会被顶掉。`sys.path` 的临时插入同样还原。

    **只在真正要切分时（POST／PUT 文档）才调用**：`load_tokenizer()` 会 import
    `transformers`（数秒），不该拖慢服务启动，故不在导入期调用。
    """
    cfg = _stage5_config()
    with _STAGE5_LOCK:
        if _STAGE5_CACHE.get("chunk") is not None:
            return (cfg, _STAGE5_CACHE["chunk"], _STAGE5_CACHE["tokenizer"],
                    _STAGE5_CACHE["token_note"])
        chunk_path = os.path.join(_STAGE5_DIR, "chunk.py")
        if not os.path.isfile(chunk_path):
            raise errors.ApiError(9999, detail="第 5 阶段切分实现缺失：%s" % chunk_path)
        saved_config = sys.modules.get("config")
        saved_path = list(sys.path)
        try:
            sys.modules["config"] = cfg
            sys.path.insert(0, _STAGE5_DIR)
            chunk_mod = _load_file_module("_stage9_stage5_chunk", chunk_path)
        except Exception as exc:                                # noqa: BLE001
            logger.exception("装载第 5 阶段 chunk.py 失败：%s", exc)
            raise errors.ApiError(9999, detail="装载第 5 阶段切分实现失败：%s: %s"
                                  % (type(exc).__name__, exc))
        finally:
            sys.path[:] = saved_path
            if saved_config is not None:
                sys.modules["config"] = saved_config
            else:
                sys.modules.pop("config", None)
        tokenizer, method, note = chunk_mod.load_tokenizer()
        _STAGE5_CACHE.update({"chunk": chunk_mod, "tokenizer": tokenizer,
                              "token_note": "%s（%s）" % (method, note)})
        logger.info("已复用第 5 阶段切分实现：%s；token 计数口径=%s", chunk_path,
                    _STAGE5_CACHE["token_note"])
        return (cfg, chunk_mod, tokenizer, _STAGE5_CACHE["token_note"])


def chunk_params() -> dict:
    """第 5 阶段 `config.CHUNK` 的**原样**副本（不复制数值、不设默认值）。"""
    return dict(_stage5_config().CHUNK)


def _chunk_text(content: str) -> tuple:
    """切分 + 计数，返回 `(块文本列表, token 数列表, 参数, 计数口径说明)`。

    * 切分：`chunk.py` 的 `chunk_document(content, params)`（与第 5 阶段同函数、同参数）；
    * 编号：`cfg.chunk_id_for(doc_id, i)`（调用方拼）；
    * 计数：`chunk.py` 的 `count_tokens()`（tokenizer 加载失败时它自己回退为
      「非空白字符数」，回退原因随 `token_note` 一并返回，不掩盖）。
    """
    cfg, chunk_mod, tokenizer, token_note = _stage5()
    params = dict(cfg.CHUNK)
    chunks = chunk_mod.chunk_document(content, params)
    counts = chunk_mod.count_tokens(tokenizer, chunks, tokenizer is None)
    return chunks, counts, params, token_note


# --------------------------------------------------------------------------
# 5. 前台可见的文档读写（POST／GET／PUT／DELETE /api/admin/documents）
# --------------------------------------------------------------------------
def _check_document_payload(payload) -> dict:
    """校验导入／修改的请求体，返回规范化后的字段字典。

    * 非对象 → 1003；含未登记字段 → 1002；缺必填 → **1003**（不是 1002：1003 就是
      「必填字段缺失」，表 4-13 对 POST／PUT 两条都列了 1003）；
    * 长度超列宽 → 1002（`title` 512／`source` 128／`url` 1024／`category` 64／
      `company_list` 512，逐项对齐 `schema\\六张表.sql`）；
    * `category` **不限定**在第 5 阶段的四类之内：依据是《10》4.7.3 的示例值「监管处罚」
      并不在四类里，且检索侧不按 `category` 过滤；不在四类内时**记一条告警**（可审计），
      不拒收；
    * `publish_time`／`ingest_time` 由服务端定：前者取请求值，后者取当前时间。
    """
    if not isinstance(payload, dict):
        raise errors.ApiError(1003, detail="请求体必须是 JSON 对象，收到 %s"
                              % type(payload).__name__)
    unknown = sorted(k for k in payload if k not in DOC_ALLOWED)
    if unknown:
        raise errors.ApiError(1002, detail="请求体含未登记字段 %s（本接口只接受 %s）"
                              % ("、".join(unknown), "、".join(sorted(DOC_ALLOWED))))

    row = {
        "title": _check_text(payload.get("title"), "title", DOC_TITLE_MAX),
        "content": _check_text(payload.get("content"), "content", 16 * 1024 * 1024),
        "source": _check_text(payload.get("source"), "source", DOC_SOURCE_MAX),
        "publish_time": _parse_dt(payload.get("publish_time"), "publish_time"),
    }
    url = _s(payload.get("url")).strip()
    if url:
        if len(url) > DOC_URL_MAX:
            raise errors.ApiError(1002, detail="url 长度 %d 超过列宽上限 %d"
                                  % (len(url), DOC_URL_MAX))
        row["url"] = url
    else:
        row["url"] = None
    category = _s(payload.get("category")).strip()
    if category:
        if len(category) > DOC_CATEGORY_MAX:
            raise errors.ApiError(1002, detail="category 长度 %d 超过列宽上限 %d"
                                  % (len(category), DOC_CATEGORY_MAX))
        if CATEGORIES and category not in CATEGORIES:
            logger.warning("category=%r 不在第 5 阶段的四类 %s 之内——照收（检索侧不按 "
                           "category 过滤），此告警仅作审计留痕", category, list(CATEGORIES))
        row["category"] = category
    else:
        row["category"] = None
    raw_list = payload.get("company_list")
    company_list = None
    if isinstance(raw_list, (list, tuple)):
        parts = [_s(x).strip() for x in raw_list if _s(x).strip()]
        company_list = ",".join(parts) if parts else None
    elif _s(raw_list).strip():
        company_list = ",".join(p.strip() for p in _s(raw_list).split(",") if p.strip())
    if company_list and len(company_list) > DOC_COMPANY_LIST_MAX:
        raise errors.ApiError(1002, detail="company_list 长度 %d 超过列宽上限 %d"
                              % (len(company_list), DOC_COMPANY_LIST_MAX))
    row["company_list"] = company_list
    return row


_DOC_LOCK = threading.RLock()


def _next_doc_id(cur) -> int:
    """下一个 `doc_id`：`MAX(doc_id) + 1`（第一版单进程演示；见下方锁）。"""
    cur.execute("SELECT COALESCE(MAX(`doc_id`), 0) + 1 AS nid FROM `document`")
    return int(cur.fetchone()["nid"])


def _new_version(row: dict) -> dict:
    """把一份已校验的字段写成一版新文档（`document` ＋ `document_chunk`），返回读数。

    * `chunk_count` 为切分后的**实际**块数（空正文会被 `chunk_document` 判为空 → 0 块，
      这里事先已按 1003 拦住，不会走到 0）；
    * `vector_id` 一律写 `NULL`：向量化属第 5 阶段能力，本阶段**不重跑**（不假装已向量化）；
    * `create_time`／`ingest_time` 都取当前时间。
    """
    content = row["content"]
    chunks, counts, params, token_note = _chunk_text(content)
    if not chunks:
        raise errors.ApiError(1003, detail="content 去空白后为空，无文本块可入库")
    cfg, _chunk, _tk, _note = _stage5()
    now = _now().replace(microsecond=0)
    with _DOC_LOCK:
        with db.cursor(commit=True) as cur:
            doc_id = _next_doc_id(cur)
            cur.execute(
                "INSERT INTO `document` (`doc_id`, `title`, `content`, `source`, `url`, "
                "`publish_time`, `ingest_time`, `category`, `company_list`, `create_time`) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (doc_id, row["title"], content, row["source"], row["url"],
                 row["publish_time"], now, row["category"], row["company_list"], now))
            payload = []
            for index, text in enumerate(chunks):
                payload.append((int(cfg.chunk_id_for(doc_id, index)), doc_id, index, text,
                                int(counts[index]), None))
            cur.executemany(
                "INSERT INTO `document_chunk` (`chunk_id`, `doc_id`, `chunk_index`, "
                "`content`, `token_count`, `vector_id`) VALUES (%s, %s, %s, %s, %s, %s)",
                payload)
    logger.info("导入文档：doc_id=%s 块数=%d（参数 %s；token 口径 %s）",
                doc_id, len(chunks), params, token_note)
    return {"doc_id": doc_id, "chunk_count": len(chunks), "ingest_time": _iso_local(now),
            "params": params, "token_note": token_note}


def _iso_local(value: datetime) -> str:
    """`datetime` → `YYYY-MM-DDTHH:MM:SS`（表 4-13 的示例写法）。"""
    return value.isoformat(timespec="seconds")


def _doc_row(doc_id: int):
    return db.query_one(
        "SELECT `doc_id`, `title`, `source`, `publish_time`, `ingest_time` "
        "FROM `document` WHERE `doc_id` = %s", (doc_id,))


def _doc_reference_count(doc_id: int) -> int:
    """该文档被多少条历史证据引用（`answer_evidence.doc_id`；B7 的 RESTRICT 同源）。"""
    row = db.query_one("SELECT COUNT(*) AS c FROM `answer_evidence` WHERE `doc_id` = %s",
                       (doc_id,))
    return int(row["c"]) if row else 0


def _retained_for_history(doc_id: int, action: str):
    """2003 的唯一响应形态（**本项目唯一的错误体例外**，见模块头第 2 条纪律）。

    依据：《10》4.7.3「响应同时返回 `retained_for_history = true`，并说明该文档（删除
    请求）或该文档的旧版本（修改请求）已进入『不可再用于新检索』的处理状态」。
    故响应体 = `{code, message, retained_for_history}`（HTTP 409）。
    """
    if action == "delete":
        message = ("文档 %s 已被历史回答引用，不执行物理删除；该文档已进入"
                   "『不可再用于新检索』的处理状态，历史回答继续指向生成它的原始字节" % doc_id)
    else:
        message = ("文档 %s 已被历史回答引用，不执行原地修改；请以新 doc_id 重新导入新版本，"
                   "旧版本已进入『不可再用于新检索』的处理状态" % doc_id)
    logger.warning("拒绝%s：doc_id=%s 已被历史回答引用（2003）", action, doc_id)
    return JSONResponse(status_code=errors.http_status_of(2003),
                        content={"code": 2003, "message": message,
                                 "retained_for_history": True})


@router.post("/documents")
async def create_document(payload: dict | None = Body(default=None)):
    """导入财经文本并切分：写 `document` ＋ 按第 5 阶段参数切分写 `document_chunk`。

    返回 `doc_id`／`chunk_count`／`ingest_time`／`reprocess_task_id`／`status`
    （表 4-13 五项，另附 `params`／`token_note`／`note` 供审计与复现）。
    """
    row = _check_document_payload(payload)
    made = _new_version(row)
    task = _record_task("doc_ingest", doc_id=made["doc_id"],
                        doc_ids=[made["doc_id"]],
                        note=NOT_RUN_NOTE + "导入动作本身已真实写库（document 与 "
                             "document_chunk 均已落盘）。")
    return errors.ok({
        "doc_id": made["doc_id"],
        "chunk_count": made["chunk_count"],
        "ingest_time": made["ingest_time"],
        "reprocess_task_id": task["task_id"],
        "status": task["status"],
        "title": row["title"],
        "vectorized": False,
        "chunk_params": made["params"],
        "token_count_method": made["token_note"],
        "note": "第一版：向量化属第 5 阶段能力，本接口只入库文本与文本块"
                "（vector_id 一律为空），不重建向量索引。",
    })


@router.get("/documents")
async def list_documents(source: str | None = None, category: str | None = None,
                         start_time: str | None = None, end_time: str | None = None,
                         page: str | None = None, page_size: str | None = None):
    """查询已入库文档（`publish_time` 倒序）；时间窗按 `publish_time` 闭区间。

    `items` 每项：`doc_id`／`title`／`source`／`publish_time`／`ingest_time`／
    `chunk_count`（表 4-13 的六项，另附 `category`）。
    """
    page_no, size = _page_args(page, page_size)
    lo = _time_bound(start_time, "start_time")
    hi = _time_bound(end_time, "end_time", end=True)
    if lo and hi and lo > hi:
        raise errors.ApiError(1002, detail="start_time 晚于 end_time：%s > %s" % (lo, hi))
    conds, args = [], []
    if _s(source).strip():
        text = _s(source).strip()
        if len(text) > DOC_SOURCE_MAX:
            raise errors.ApiError(1002, detail="source 长度 %d 超过列宽上限 %d"
                                  % (len(text), DOC_SOURCE_MAX))
        conds.append("%s = %%s" % _col("source", alias=None))
        args.append(text)
    if _s(category).strip():
        conds.append("%s = %%s" % _col("category", alias=None))
        args.append(_s(category).strip())
    if lo:
        conds.append("%s >= %%s" % _col("publish_time", alias=None))
        args.append(lo.replace("T", " "))
    if hi:
        conds.append("%s <= %%s" % _col("publish_time", alias=None))
        args.append(hi.replace("T", " "))
    where = (" WHERE " + " AND ".join(conds)) if conds else ""
    total = int(db.scalar("SELECT COUNT(*) AS c FROM `document`" + where, tuple(args)) or 0)
    # 同一条 WHERE 换个表别名再拼一次（列名已带反引号，替换的是「`列`」→「d.`列`」）
    retarget = [(_col("source", None), _col("source", "d")),
                (_col("category", None), _col("category", "d")),
                (_col("publish_time", None), _col("publish_time", "d"))]
    parts = []
    for cond in conds:
        text = cond
        for bare, aliased in retarget:
            text = text.replace(bare, aliased)
        parts.append(text)
    where_d = (" WHERE " + " AND ".join(parts)) if parts else ""
    rows = db.query(
        "SELECT d.`doc_id`, d.`title`, d.`source`, d.`publish_time`, d.`ingest_time`, "
        "       d.`category`, "
        "       (SELECT COUNT(*) FROM `document_chunk` c WHERE c.`doc_id` = d.`doc_id`) "
        "       AS `chunk_count` "
        "FROM `document` d" + where_d +
        " ORDER BY d.`publish_time` DESC, d.`doc_id` DESC LIMIT %s OFFSET %s",
        tuple(args) + (size, (page_no - 1) * size))
    items = [{"doc_id": int(r["doc_id"]), "title": _s(r["title"]), "source": _s(r["source"]),
              "publish_time": graph_api._iso(r["publish_time"]),               # noqa: SLF001
              "ingest_time": graph_api._iso(r["ingest_time"]),                 # noqa: SLF001
              "category": _s(r["category"]), "chunk_count": int(r["chunk_count"] or 0)}
             for r in rows]
    return errors.ok_page(total, items, page_no, size)


@router.put("/documents/{doc_id}")
async def update_document(doc_id: int, payload: dict | None = Body(default=None)):
    """修改文档并触发重新处理。

    * 文档不存在 → **2001**；
    * 已被 `answer_evidence` 引用 → **2003**（HTTP 409，体含 `retained_for_history`），
      **不执行原地修改**，按《10》4.4.2 规则 3 提示「以新 doc_id 重新导入新版本」；
    * 未被引用 → 写一版**新文档**（新 `doc_id`），并把旧版本的 `vector_id` 全部置空
      （旧记录「不可再用于新检索」的落库标记），返回新／旧 `doc_id` 与任务号。
    """
    row = _check_document_payload(payload)
    if _doc_row(doc_id) is None:
        raise errors.ApiError(2001, detail="文档不存在：doc_id=%s" % doc_id)
    if _doc_reference_count(doc_id) > 0:
        return _retained_for_history(doc_id, "update")

    made = _new_version(row)
    with db.cursor(commit=True) as cur:
        cur.execute("UPDATE `document_chunk` SET `vector_id` = NULL WHERE `doc_id` = %s",
                    (doc_id,))
    task = _record_task("reprocess", doc_id=made["doc_id"], doc_ids=[doc_id, made["doc_id"]],
                        note=NOT_RUN_NOTE + "本次为「修改 → 新版本」：旧 doc_id=%s 的文本块已"
                             "置为不可再用于新检索（vector_id 置空），新内容以 doc_id=%s 落盘。"
                             % (doc_id, made["doc_id"]))
    return errors.ok({
        "doc_id": made["doc_id"],
        "old_doc_id": doc_id,
        "new_doc_id": made["doc_id"],
        "chunk_count": made["chunk_count"],
        "ingest_time": made["ingest_time"],
        "reprocess_task_id": task["task_id"],
        "status": task["status"],
        "retained_for_history": False,
        "note": "旧版本未物理删除（历史回答仍指向它），但已置为不可再用于新检索；"
                "检索侧第一版读的是第 5 阶段冻结的向量索引文件，故该状态以落库标记 ＋ "
                "任务台账记录，不重建索引（重建属第 5 阶段）。",
    })


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    """删除文档并触发重新处理。

    * 文档不存在 → **2001**；
    * 已被 `answer_evidence` 引用 → **2003**（HTTP 409，体含 `retained_for_history`），
      **不执行物理删除**（数据库层还有 `ON DELETE RESTRICT` 兜底，见 B7）；
    * 未被引用 → 物理删除（`document_chunk` 随 `fk_chunk_doc` 级联删除），返回读数。
    """
    if _doc_row(doc_id) is None:
        raise errors.ApiError(2001, detail="文档不存在：doc_id=%s" % doc_id)
    references = _doc_reference_count(doc_id)
    if references > 0:
        return _retained_for_history(doc_id, "delete")

    chunks = int(db.scalar("SELECT COUNT(*) AS c FROM `document_chunk` WHERE `doc_id` = %s",
                           (doc_id,)) or 0)
    with db.cursor(commit=True) as cur:
        cur.execute("DELETE FROM `document` WHERE `doc_id` = %s", (doc_id,))
    task = _record_task("reprocess", doc_id=doc_id, doc_ids=[doc_id],
                        note=NOT_RUN_NOTE + "本次为删除：doc_id=%s 及其 %d 个文本块已物理删除"
                             "（外键 fk_chunk_doc 级联）。" % (doc_id, chunks))
    return errors.ok({"doc_id": doc_id, "chunk_count_deleted": chunks,
                      "reprocess_task_id": task["task_id"], "status": task["status"],
                      "retained_for_history": False, "reference_count": 0,
                      "note": "文档未被任何历史回答引用，已物理删除（含其文本块）。"})


# --------------------------------------------------------------------------
# 6. POST /api/admin/reprocess —— 只登记任务
# --------------------------------------------------------------------------
@router.post("/reprocess")
async def reprocess(payload: dict | None = Body(default=None)):
    """触发一次重新处理流程（**第一版：只登记任务台账，不实际重跑**，见纪律 4）。

    表 4-13 对本接口只列了 1002／2001，故**请求体缺失或不是对象也按 1002 拒**
    （不用 1003：1003 不在本接口的错误码清单里）。
    """
    if not isinstance(payload, dict):
        raise errors.ApiError(1002, detail="请求体必须是 JSON 对象，收到 %s"
                              % type(payload).__name__)
    unknown = sorted(k for k in payload if k not in ("scope", "doc_ids"))
    if unknown:
        raise errors.ApiError(1002, detail="请求体含未登记字段 %s（本接口只接受 scope、doc_ids）"
                              % "、".join(unknown))
    scope = _check_scope(payload.get("scope"))
    doc_ids = _check_doc_ids(payload.get("doc_ids"))
    if scope in ("document", "chunk") and not doc_ids:
        raise errors.ApiError(1002, detail="scope=%s 时必须给出 doc_ids（否则不知重处理谁）"
                              % scope)
    task = _record_task("reprocess", scope=scope, doc_ids=doc_ids,
                        note=NOT_RUN_NOTE + "scope=%s doc_ids=%s。" % (scope, doc_ids or "全量"))
    return errors.ok({"task_id": task["task_id"], "status": task["status"], "scope": scope,
                      "doc_ids": doc_ids, "executed": False, "note": task["note"],
                      "ledger": TASK_LEDGER})


# --------------------------------------------------------------------------
# 7. GET /api/admin/consistency-check —— 一致性检查（读数为实读）
# --------------------------------------------------------------------------
@router.get("/consistency-check")
async def consistency_check():
    """比对文本块／向量／图谱三方计数（`chunk_count`／`vector_count`／`graph_node_counts`／
    `is_consistent`／`diff`）。

    * `chunk_count`：MySQL `document_chunk` 实查；
    * `vector_count`：`build_meta.json` 的 `vector_count`（构建时自报）＋ `vector_map.jsonl`
      **实点行数**，两者都给出（不一致也照报）；文件缺失 → **3003**；
    * `graph_node_counts`：图谱后端实查（`GraphReader.counts()`）；不可用 → **3001**；
    * `diff`：逐项差值 ＋ 上游 `graph_stats.json` 的旁证读数（只列不改判）；
    * `is_consistent`：**全部差值为 0** 才为 true。
    """
    # --- 文本块 ---
    chunk_count = int(db.scalar("SELECT COUNT(*) AS c FROM `document_chunk`") or 0)
    doc_count = int(db.scalar("SELECT COUNT(*) AS c FROM `document`") or 0)

    # --- 向量（索引三件缺一不可 → 3003） ---
    missing = [name for name, path in (("索引文件", config.VECTOR_INDEX_PATH),
                                      ("映射文件", config.VECTOR_MAP_PATH),
                                      ("构建元信息", config.BUILD_META_PATH))
               if not os.path.isfile(path)]
    if missing:
        raise errors.ApiError(3003, detail="向量索引不齐备，缺：%s" % "、".join(missing))
    try:
        build_meta = config.read_json(config.BUILD_META_PATH)
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("build_meta.json 解析失败：%s", exc)
        raise errors.ApiError(3003, detail="构建元信息不可解析：%s: %s"
                              % (type(exc).__name__, exc))
    vector_count = int(build_meta.get("vector_count") or 0)
    map_lines = config.count_jsonl(config.VECTOR_MAP_PATH)

    # --- 图谱（不可用 → 3001；不做降级） ---
    with reader() as rd:
        graph = rd.counts()
        backend = rd.backend                      # `neo4j`（默认）或 `memory`，如实报出

    # --- 上游旁证（只读；取不到不阻断本接口，只在 diff 里标注） ---
    stats, stats_note = None, ""
    try:
        stats, stats_path = _graph_stats()
        stats_note = stats_path
    except errors.ApiError as exc:
        stats, stats_note = None, "上游 graph_stats.json 不可用：%s" % exc.message

    deltas = {
        "document_chunk_vs_vector_count": chunk_count - vector_count,
        "document_chunk_vs_vector_map_lines": chunk_count - map_lines,
        "vector_map_lines_vs_build_meta": map_lines - vector_count,
    }
    if stats:
        upstream_nodes = int(stats.get("counts", {}).get("nodes_total") or 0)
        upstream_edges = int(stats.get("counts", {}).get("edges_total") or 0)
        deltas["graph_nodes_total_vs_upstream"] = graph["nodes_total"] - upstream_nodes
        deltas["graph_edges_total_vs_upstream"] = graph["edges_total"] - upstream_edges
    is_consistent = all(int(v) == 0 for v in deltas.values())

    items = [
        "文本块（MySQL document_chunk）%d 条 vs 向量（build_meta.vector_count）%d 条：%+d"
        % (chunk_count, vector_count, deltas["document_chunk_vs_vector_count"]),
        "文本块 %d 条 vs 向量映射实点 %d 行：%+d"
        % (chunk_count, map_lines, deltas["document_chunk_vs_vector_map_lines"]),
        "向量映射 %d 行 vs build_meta 自报 %d 条：%+d"
        % (map_lines, vector_count, deltas["vector_map_lines_vs_build_meta"]),
        "图谱节点 %d 个、关系 %d 条（实查）" % (graph["nodes_total"], graph["edges_total"]),
    ]
    if stats:
        items.append("上游旁证（%s）：节点 %s、关系 %s"
                     % (stats_note, stats["counts"]["nodes_total"],
                        stats["counts"]["edges_total"]))
    else:
        items.append(stats_note)

    return errors.ok({
        "chunk_count": chunk_count,
        "vector_count": vector_count,
        "graph_node_counts": graph["nodes_by_label"],
        "is_consistent": is_consistent,
        "diff": {"deltas": deltas, "items": items,
                 "document_count": doc_count,
                 "vector_map_lines": map_lines,
                 "vector_count_from_build_meta": vector_count,
                 "graph_nodes_total": graph["nodes_total"],
                 "graph_edges_total": graph["edges_total"],
                 "graph_edges_by_relation": graph["edges_by_relation"],
                 "expected_counts": dict(config.EXPECTED_COUNTS or {}),
                 "upstream_graph_stats": stats_note},
        "sources": {"mysql": config.db_database(),
                    "build_meta": config.BUILD_META_PATH,
                    "vector_map": config.VECTOR_MAP_PATH,
                    "graph_backend": backend},
    })


# --------------------------------------------------------------------------
# 8. 抽取相关（run／tasks／events／disambiguation）
# --------------------------------------------------------------------------
@router.post("/extraction/run")
async def extraction_run(payload: dict | None = Body(default=None)):
    """触发一次抽取任务（**第一版：只登记任务台账，不实际重跑**，见纪律 4）。

    响应与《10》4.7.3 的示例同形：`task_id`／`status` ＋ 五项统计（未真跑，全为 0）。
    """
    if not isinstance(payload, dict):
        raise errors.ApiError(1003, detail="请求体必须是 JSON 对象，收到 %s"
                              % type(payload).__name__)
    unknown = sorted(k for k in payload if k not in ("scope", "doc_ids", "prompt_version"))
    if unknown:
        raise errors.ApiError(1002, detail="请求体含未登记字段 %s（本接口只接受 scope、"
                              "doc_ids、prompt_version）" % "、".join(unknown))
    if not _s(payload.get("scope")).strip():
        raise errors.ApiError(1003, detail="必填字段 scope 缺失或为空（%s）" % "／".join(SCOPES))
    scope = _check_scope(payload.get("scope"))
    doc_ids = _check_doc_ids(payload.get("doc_ids"))
    prompt_version = _s(payload.get("prompt_version")).strip() or config.PROMPT_VERSION
    if len(prompt_version) > 64:
        raise errors.ApiError(1002, detail="prompt_version 长度 %d 超过 64" % len(prompt_version))
    task = _record_task("extraction", scope=scope, doc_ids=doc_ids,
                        prompt_version=prompt_version,
                        note=NOT_RUN_NOTE + "scope=%s doc_ids=%s prompt_version=%s。"
                             % (scope, doc_ids or "全量", prompt_version))
    return errors.ok({"task_id": task["task_id"], "status": task["status"],
                      "processed_chunks": 0, "entity_count": 0, "event_count": 0,
                      "relation_count": 0, "merge_log_count": 0,
                      "scope": scope, "doc_ids": doc_ids, "prompt_version": prompt_version,
                      "executed": False, "note": task["note"], "ledger": TASK_LEDGER})


@router.get("/extraction/tasks/{task_id}")
async def extraction_task(task_id: str):
    """查询抽取（或重处理）任务状态与统计；台账里没有这个号 → **2001**。"""
    want = _s(task_id).strip()
    for record in reversed(_read_ledger(TASK_LEDGER)):
        if _s(record.get("task_id")) == want:
            return errors.ok({
                "task_id": record["task_id"], "status": record.get("status"),
                "kind": record.get("kind"),
                "processed_chunks": int(record.get("processed_chunks") or 0),
                "entity_count": int(record.get("entity_count") or 0),
                "event_count": int(record.get("event_count") or 0),
                "relation_count": int(record.get("relation_count") or 0),
                "merge_log_count": int(record.get("merge_log_count") or 0),
                "scope": record.get("scope"), "doc_ids": record.get("doc_ids") or [],
                "doc_id": record.get("doc_id"), "prompt_version": record.get("prompt_version"),
                "created_at": record.get("created_at"), "executed": record.get("executed"),
                "note": record.get("note"),
            })
    raise errors.ApiError(2001, detail="任务号不存在：%s（台账 %s）" % (want, TASK_LEDGER))


@router.get("/extraction/events")
async def extraction_events(event_type: str | None = None, start_time: str | None = None,
                            end_time: str | None = None, confidence_min: str | None = None,
                            page: str | None = None, page_size: str | None = None):
    """按条件查询抽取到的事件：`items` 每项 `event_id`／`event_type`／`event_name`／
    `event_time`／`confidence`／`evidence_doc_count`（表 4-13 六项）。

    `evidence_doc_count` 由图谱后端**实算**（语义边上的 `source_doc_id` 与 `EVIDENCED_BY`
    指向的 Document 取并集去重），不是写死的数字。
    """
    etype = _check_event_type(event_type)
    cmin = None
    if _s(confidence_min).strip():
        try:
            cmin = float(_s(confidence_min).strip())
        except ValueError:
            raise errors.ApiError(1002, detail="confidence_min 不是数值：%r" % confidence_min)
        if cmin < 0 or cmin > 1:
            raise errors.ApiError(1002, detail="confidence_min 必须在 0～1 之间：%r"
                                  % confidence_min)
    lo = _time_bound(start_time, "start_time")
    hi = _time_bound(end_time, "end_time", end=True)
    if lo and hi and lo > hi:
        raise errors.ApiError(1002, detail="start_time 晚于 end_time：%s > %s" % (lo, hi))
    page_no, size = _page_args(page, page_size)

    with reader() as rd:
        views = rd.graph.g3_events_by_type(etype).get("results") or [] if etype \
            else rd.all_events()
        views = _events_in_window(views, lo, hi)
        views.sort(key=lambda e: (graph_api._s(e.get("event_time")),               # noqa: SLF001
                                  graph_api._s(e.get("node_id"))))                 # noqa: SLF001
        items = [_event_item(v) for v in views]
        if cmin is not None:
            items = [it for it in items
                     if isinstance(it.get("confidence"), float) and it["confidence"] >= cmin]
        # 证据文档数按**节点编号**实算（`evidence_doc_counts` 查的是 `e.node_id`；
        # 本项目 event_id 与 node_id 同值，但仍按 node_id 取键，避免将来分叉时错配）
        keys = [(it["node_id"] or it["event_id"]) for it in items]
        counts = rd.evidence_doc_counts(keys)
    for item in items:
        item["evidence_doc_count"] = int(counts.get(item["node_id"] or item["event_id"], 0))
    start = (page_no - 1) * size
    return errors.ok_page(len(items), items[start:start + size], page_no, size)


def _disambig_rows() -> tuple:
    """读待消歧原始清单，返回 `(行列表, 路径, 文件 sha256)`。"""
    path = _unresolved_path()
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, 1):
            text = line.strip()
            if not text:
                continue
            try:
                rows.append(json.loads(text))
            except Exception:                                  # noqa: BLE001
                logger.warning("待消歧清单第 %d 行不是合法 JSON，已跳过：%s", line_no, path)
    return rows, path, config.sha256_file(path)


def _confirmations() -> dict:
    """人工确认台账 → `{item_id: 最新一条}`（后写的覆盖先写的）。"""
    latest = {}
    for record in _read_ledger(DISAMBIG_LEDGER):
        key = _s(record.get("item_id"))
        if key:
            latest[key] = record
    return latest


@router.get("/extraction/disambiguation")
async def disambiguation_list(page: str | None = None, page_size: str | None = None):
    """待消歧列表：`items` 每项 `item_id`／`raw_name`／`matched_candidates`／`stock_code`／
    `status`（表 4-13 五项，另附 `label`／`doc_id`／`reason`）。

    * 数据**实读**第 6 阶段落盘的 `unresolved.jsonl`（路径与 sha256 一并返回）；
    * `status`：`pending`（默认）／`confirmed`／`rejected`，取自本项目的人工确认台账
      （第 6 阶段的原始清单**不被本接口改动**）；
    * `stock_code`：确认后为目标代码，未确认为 `null`；
    * 另附 `skipped_relations`／`human_confirmation` 两个实读小节（来源 `graph_stats.json`），
      供后台核对「跳过边」与「已人工确认」的规模。
    """
    page_no, size = _page_args(page, page_size)
    rows, path, digest = _disambig_rows()
    src = _unresolved_source()
    latest = _confirmations()
    items = []
    for row in rows:
        item_id = _s(row.get("entity_id")) or _s(row.get("item_id"))
        record = latest.get(item_id) or {}
        status = _s(record.get("status")) or "pending"
        stock_code = record.get("stock_code") if status == "confirmed" else None
        items.append({
            "item_id": item_id,
            "raw_name": _s(row.get("name")),
            "matched_candidates": list(row.get("matched_codes") or []),
            "stock_code": stock_code,
            "status": status,
            "label": _s(row.get("label")),
            "doc_id": graph_api._as_int(row.get("doc_id")),                        # noqa: SLF001
            "reason": _s(row.get("reason")),
            "normalized_name": _s(row.get("normalized_name")),
        })
    items.sort(key=lambda it: (it["status"] != "pending", it["doc_id"] or 0, it["item_id"]))
    pending = sum(1 for it in items if it["status"] == "pending")

    stats, stats_note = None, ""
    try:
        stats, stats_path = _graph_stats()
        stats_note = stats_path
    except errors.ApiError as exc:
        stats_note = "上游 graph_stats.json 不可用：%s" % exc.message
    unresolved = (stats or {}).get("unresolved", {})
    human = (stats or {}).get("human_confirmation", {})
    start = (page_no - 1) * size
    return errors.ok_page(
        len(items), items[start:start + size], page_no, size,
        meta={"disambiguation": {
            "source": path, "source_sha256": digest, "source_lines": len(rows),
            "pending": pending, "confirmed": len(items) - pending,
            "skipped_relations": {
                "total": unresolved.get("relations_skipped"),
                "by_reason": unresolved.get("relations_skipped_by_reason"),
                "by_relation": unresolved.get("relations_skipped_by_relation"),
            } if unresolved else None,
            "human_confirmation": {
                "entries_total": human.get("entries_total"),
                "entries_confirmed": human.get("entries_confirmed"),
                "entries_unconfirmed": human.get("entries_unconfirmed"),
                "nodes_added": human.get("nodes_added"),
                "edges_added": human.get("edges_added"),
            } if human else None,
            "stats_source": stats_note,
            "ledger": DISAMBIG_LEDGER,
            "note": "数量均实读上游落盘物，未写死；本接口不改上游清单。",
            # ---- 以下 8 项为 2026-10-05 修补**新增**（既有键名与语义一个都没动）----
            # 用途：把「这份列表来自哪一版口径、有没有降级、现行口径该在哪」摊开给调用方。
            # 此前 v1.3 起消歧产物落 `图谱管线_v1_3\`，而本函数按 `图谱管线\` 找，
            # 于是逐级降级到 v1.1 的旧清单并**静默**返回，调用方看不出数据源已被换掉。
            "source_profile": src.get("source_profile"),
            "source_version": src.get("source_version"),
            "source_pipeline": src.get("source_pipeline"),
            "expected_profile": src.get("expected_profile"),
            "expected_version": src.get("expected_version"),
            "expected_source": src.get("expected_source"),
            "degraded": src.get("degraded"),
            "degraded_reason": src.get("degraded_reason"),
        }})


@router.post("/extraction/disambiguation/{item_id}")
async def disambiguation_confirm(item_id: str, payload: dict | None = Body(default=None)):
    """人工确认消歧结果：给 `stock_code` 或 `reject=true`（表 4-13 的请求字段）。

    * `item_id` 不在待消歧清单里 → **2001**；
    * 既没给 `stock_code` 也没给 `reject` → **1002**；`stock_code` 非 6 位数字 → **1002**；
    * `stock_code` 不在图谱里的 Company 节点代码中 → **1002**（人工确认要落到已配置的公司上）；
    * 只往本项目台账追加一条确认记录并返回新状态，**不回写上游图谱文件、不重建图谱**
      （见纪律 7；重建要走第 6 阶段的 `write_graph.py`）。
    """
    target = _s(item_id).strip()
    rows, path, _digest = _disambig_rows()
    hit = next((r for r in rows if (_s(r.get("entity_id")) or _s(r.get("item_id"))) == target),
               None)
    if hit is None:
        raise errors.ApiError(2001, detail="待消歧项不存在：item_id=%s（清单 %s）" % (target, path))
    if not isinstance(payload, dict):
        raise errors.ApiError(1002, detail="请求体必须是 JSON 对象，收到 %s"
                              % type(payload).__name__)
    unknown = sorted(k for k in payload if k not in ("stock_code", "reject"))
    if unknown:
        raise errors.ApiError(1002, detail="请求体含未登记字段 %s（本接口只接受 stock_code、reject）"
                              % "、".join(unknown))
    has_code = bool(_s(payload.get("stock_code")).strip())
    reject = payload.get("reject") is True
    if not has_code and not reject:
        raise errors.ApiError(1002, detail="必须给出 stock_code 或 reject=true（表 4-13 的请求字段）")
    if has_code and reject:
        raise errors.ApiError(1002, detail="stock_code 与 reject=true 不能同时给出")

    if reject:
        stock_code, status = None, "rejected"
    else:
        stock_code, status = _s(payload.get("stock_code")).strip(), "confirmed"
        if not (len(stock_code) == 6 and stock_code.isdigit()):
            raise errors.ApiError(1002, detail="stock_code 必须是 6 位数字：%r" % stock_code)
        known = _company_stock_codes()
        if stock_code not in known:
            raise errors.ApiError(1002, detail="stock_code=%s 不在图谱的 Company 节点代码中"
                                  "（共 %d 个）" % (stock_code, len(known)))
    record = {"item_id": target, "raw_name": _s(hit.get("name")), "stock_code": stock_code,
              "status": status, "recorded_at": _now_iso(), "doc_id": hit.get("doc_id"),
              "source": path,
              "note": "只记入本项目人工确认台账；未回写上游消歧清单与图谱文件。"
                      "回写图谱请在第 6 阶段跑 write_graph.py。"}
    _append_ledger(DISAMBIG_LEDGER, record)
    logger.info("人工确认消歧：item_id=%s status=%s stock_code=%s（未回写上游）",
                target, status, stock_code)
    return errors.ok({"item_id": target, "stock_code": stock_code, "status": status,
                      "raw_name": record["raw_name"], "recorded_at": record["recorded_at"],
                      "ledger": DISAMBIG_LEDGER, "note": record["note"]})


_COMPANY_CODES: dict = {}
_COMPANY_LOCK = threading.Lock()


def _company_stock_codes() -> set:
    """图谱里 Company 节点的 `stock_code` 集合（读第 6 阶段的 `nodes.csv`，只读缓存）。"""
    with _COMPANY_LOCK:
        if _COMPANY_CODES.get("codes") is not None:
            return _COMPANY_CODES["codes"]
        path = config.NODES_CSV
        if not os.path.isfile(path):
            raise errors.ApiError(3001, detail="图谱节点文件不存在：%s" % path)
        codes = set()
        try:
            with open(path, encoding="utf-8", newline="") as fh:
                for row in csv.DictReader(fh):
                    if _s(row.get("label")) != "Company":
                        continue
                    code = _s(row.get("stock_code")).strip()
                    if code:
                        codes.add(code)
        except Exception as exc:                               # noqa: BLE001
            logger.exception("读取 nodes.csv 失败：%s", exc)
            raise errors.ApiError(3001, detail="读取 %s 失败：%s: %s"
                                  % (path, type(exc).__name__, exc))
        _COMPANY_CODES["codes"] = codes
        logger.info("已载入图谱 Company 节点代码 %d 个（来源 %s）", len(codes), path)
        return codes


# --------------------------------------------------------------------------
# 9. POST /api/admin/experiment/ask —— 受控实验入口（A～E 组）
# --------------------------------------------------------------------------
EXPERIMENT_GROUPS = None
"""A～E 的合法取值（取自检索侧 config 的 `GROUPS`，不写死）。"""


def _check_group(raw) -> str:
    """`experiment_group` 必须是 `A`～`E` 之一（缺失或非法 → 1002）。"""
    text = _s(raw).strip().upper()
    if not text:
        raise errors.ApiError(1002, detail="缺少 experiment_group（A／B／C／D／E）")
    if EXPERIMENT_GROUPS and text not in EXPERIMENT_GROUPS:
        raise errors.ApiError(1002, detail="experiment_group=%r 不在 A～E 之内（%s）"
                              % (raw, "、".join(sorted(EXPERIMENT_GROUPS))))
    return text


def _config_snapshot(group: str) -> dict:
    """该组别的配置快照（供实验期间核对配置有没有被改动）。"""
    settings = (config.GROUPS or {}).get(group) or {}
    meta = config.dataset_meta()
    return {
        "experiment_group": group,
        "group_settings": dict(settings),
        "k": config.K, "n": config.N,
        "context_token_budget": config.CONTEXT_TOKEN_BUDGET,
        "graph_retention_share": config.G,
        "model_name": config.ANSWER_MODEL,
        "model_version": config.ANSWER_MODEL_VERSION,
        "prompt_version": config.PROMPT_VERSION,
        "answer_temperature": config.ANSWER_TEMPERATURE,
        "answer_max_tokens": config.ANSWER_MAX_TOKENS,
        "dataset_version": meta["dataset_version"],
        "data_cutoff_time": meta["data_cutoff_time"],
        "default_group": config.DEFAULT_GROUP,
    }


@router.post("/experiment/ask")
async def experiment_ask(payload: dict | None = Body(default=None)):
    """按指定组别运行一次问答（受控实验入口；《10》4.7.1 末段：分组切换只存在于此处）。

    请求字段：`question`／`session_id`／`experiment_group`（A／B／C／D／E）／`run_id`（可选）。
    响应：与 `/api/qa/ask` **同一形状**的载荷（`errors.ok` 信封内），另加
    `experiment_group`／`run_id`／`experiment_config`（配置快照）／`elapsed_seconds`。

    链路是同步阻塞调用（10～30 s），用 `asyncio.to_thread` 放到工作线程，不堵事件循环；
    超时／依赖不可用由链路自身按 3002／3001／3003 上报（`qa_service` 的口径）。
    """
    if not isinstance(payload, dict):
        raise errors.ApiError(1002, detail="请求体必须是 JSON 对象，收到 %s"
                              % type(payload).__name__)
    unknown = sorted(k for k in payload
                     if k not in ("question", "session_id", "experiment_group", "run_id"))
    if unknown:
        raise errors.ApiError(1002, detail="请求体含未登记字段 %s（本接口只接受 question、"
                              "session_id、experiment_group、run_id）" % "、".join(unknown))

    import main as backend_main                                # noqa: PLC0415（延迟导入，避免装配期循环）
    question = backend_main.validate_question(payload.get("question"))     # 空／超长 → 1001
    session_id = _s(payload.get("session_id")).strip()
    if not session_id:                                          # 输入为空 → 1001（表 4-13 列了 1001）
        raise errors.ApiError(1001, detail="session_id 缺失或为空")
    if len(session_id) > 36:                                    # question.session_id CHAR(36)
        raise errors.ApiError(1002, detail="session_id 长度 %d 超过 36（应为 UUID）"
                              % len(session_id))
    group = _check_group(payload.get("experiment_group"))
    run_id = _s(payload.get("run_id")).strip() or None

    from services import qa_service
    data = await asyncio.to_thread(qa_service.ask, question, session_id, group)
    data = dict(data)
    data.update({"experiment_group": group, "run_id": run_id,
                 "experiment_config": _config_snapshot(group),
                 "note": "本接口是唯一的 A～E 组入口（后台能力）；/api/qa/ask 固定 C 组，"
                         "请求体出现分组字段会被 1002 拒。"})
    return errors.ok(data)


# --------------------------------------------------------------------------
# 9.5 兜底路由（**必须放在本模块最后一条路由**）
# --------------------------------------------------------------------------
@router.api_route("/{rest:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
                  include_in_schema=False)
async def admin_fallback(rest: str):
    """未登记的 `/api/admin/*`：普通用户已被 `require_admin` 拦成 4002，其余按 2001 拒。

    Starlette 按**注册顺序**匹配、首个命中即返回，所以本路由必须定义在全部具体路由
    之后；写在前面会把 `/documents`、`/consistency-check` 等 12 条全吞掉（本模块
    初版即踩过此坑：13 条接口一律 404「未登记的后台接口」）。
    """
    raise errors.ApiError(2001, detail="未登记的后台接口：/api/admin/%s" % _s(rest))


# --------------------------------------------------------------------------
# 10. 常量补全（放在使用点之后，避免循环导入；取值仍全部来自既有出处）
# --------------------------------------------------------------------------
def _bootstrap() -> None:
    """把「来自既有出处」的两个运行期常量补齐（**不写死任何数值**）。

    两处都只读第 5 阶段／检索侧的配置，取不到时**降级但不改口径**：
    `CATEGORIES` 取不到只是不做 category 审计告警（仍照收），`EXPERIMENT_GROUPS`
    取不到则任何组别都拒（1002），而不是自己编一套 A～E。
    """
    global CATEGORIES, EXPERIMENT_GROUPS                          # noqa: PLW0603
    if CATEGORIES is None:
        try:
            CATEGORIES = tuple(getattr(_stage5_config(), "CATEGORIES", ()) or ())
        except errors.ApiError as exc:
            CATEGORIES = ()
            logger.warning("第 5 阶段 CATEGORIES 不可用（category 将不做审计告警）：%s",
                           exc.message)
    if EXPERIMENT_GROUPS is None:
        EXPERIMENT_GROUPS = tuple(sorted((config.GROUPS or {}).keys()))
        if not EXPERIMENT_GROUPS:
            logger.error("检索侧 config.GROUPS 缺失——/api/admin/experiment/ask 将拒绝全部"
                         "组别（不用自编的组名兜底）")


_bootstrap()
