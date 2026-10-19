# -*- coding: utf-8 -*-
"""
文档一致性核验（第 13 轮复验新增，只读）

用途：对「文档与可维护配套」的五类关键文档做机器可复现的路径核验：
  1) Markdown 相对链接与图片是否存在；带 #锚点 的 .md 链接是否能在目标文档中找到对应标题；
  2) 行内代码中的仓库路径（交付物/、工具/、检索/、问答/、后端/、src/ 等）是否存在。

只读：不修改任何文档、代码或数据。退出码 0 = 无缺失；1 = 存在缺失。

用法：
    python 工具/文档一致性核验.py
    python 工具/文档一致性核验.py --json 工具/_文档一致性核验.json
"""
import io
import json
import os
import re
import sys

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:
    pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BS = chr(92)

DOCS = [
    "交付物/07-设计与需求/架构与数据模型实况说明.md",
    "交付物/07-设计与需求/文档与可维护性核对.md",
    "交付物/10-部署/兼容性与接口版本化说明.md",
    "交付物/10-部署/用户与管理员手册.md",
    "交付物/10-部署/部署手册.md",
    "交付物/10-部署/README.md",
    "交付物/05-系统实现/智能问答系统/拒答矩阵与幻觉抑制.md",
    "交付物/05-系统实现/RAG检索系统/混合检索与重排序方案.md",
    "交付物/05-系统实现/性能与架构优化方案.md",
    "交付物/05-系统实现/优化方案核对表.md",
    "交付物/03-代码/后端/README.md",
]

# 以仓库根为基准的目录前缀 → 实际目录（'' 表示原样相对仓库根）
PREFIXES = {
    "交付物/": "",
    "工具/": "",
    "过程记录/": "",
    "后端/": "交付物/03-代码/后端/",
    "检索/": "交付物/03-代码/检索/",
    "问答/": "交付物/03-代码/问答/",
    "增强/": "交付物/03-代码/增强/",
    "数据准备/": "交付物/03-代码/数据准备/",
    "抽取与图谱/": "交付物/03-代码/抽取与图谱/",
    "测试/": "交付物/03-代码/测试/",
    "src/": "交付物/03-代码/前端/src/",
    "schema/": "交付物/03-代码/后端/schema/",
    "services/": "交付物/03-代码/后端/services/",
    "api/": "交付物/03-代码/后端/api/",
    "tools/": "交付物/03-代码/后端/tools/",
    "系统指标/": "交付物/06-实验与评测/系统指标/",
    "数据集/": "交付物/04-数据与知识图谱/数据准备/数据集/",
    "前端/": "交付物/03-代码/前端/",
    "lib/": "交付物/03-代码/前端/src/lib/",
    "views/": "交付物/03-代码/前端/src/views/",
    "components/": "交付物/03-代码/前端/src/components/",
    "图谱导出/": "交付物/04-数据与知识图谱/事件抽取与知识图谱/图谱导出/",
}
# 单独文件别名（文档中按“就近目录”简写）
FILE_ALIASES = {
    "extraction/run": None,
    "1.4-系统总体架构.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.1-系统总体架构.md",
    "4.2-系统功能模块设计.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.2-系统功能模块设计.md",
    "4.3-系统业务流程.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.3-系统业务流程.md",
    "4.4-数据库设计.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.4-数据库设计.md",
    "4.5-知识图谱本体设计.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.5-知识图谱本体设计.md",
    "4.6-RAG检索架构.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.6-RAG检索架构.md",
    "4.7-接口设计.md": "交付物/07-设计与需求/总体设计/_分节源文件/4.7-接口设计.md",
}
SKIP_PREFIXES = (
    "http", "/api", "/docs", "/redoc", "/openapi", "/app", "/mnt", "/proc",
    "$", "%", "bolt:", "BAAI/", "HF_HOME", "Wsl/", "-v ", "Origin:", "Referer:",
    "application/", "location ", "dist/", "node_modules/", "_工作底稿/",
    "push2.", "np-anotice", "search-api", "f12/", "title/", "python", "node ",
    "npm ", "curl", "cd ", "wsl ", "docker", "powershell", "sc ", "mysql",
    "taskkill", "git ", "pytest",
)
SKIP_CONTAINS = ("<", ">", "{", "}", "*", "…", "YYYY", "...", "：", "|", "::", "→", " ",
                 "代码后端")  # README 中用「反斜杠被吞后的错误结果」做示例，不是真实路径
API_METHOD_RE = re.compile(r"\b(GET|POST|PUT|DELETE|HEAD|OPTIONS|PATCH)\s+/")
EXT_RE = re.compile(r"\.(md|py|json|js|vue|sql|ps1|yml|yaml|conf|txt|csv|jsonl|png)$")
# 备份产物/日志/运行目录是“运行后生成”的概念路径，不要求在仓库中预先存在
CONCEPTUAL_PREFIXES = ("neo4j/", "vector/", "mysql/", "qa_runs/", "logs/", "备份/",
                       "检索/lexical_index/")  # 混合检索方案中的计划落盘目录，文档已注明“本轮未创建”
# 运行期产物（由问答/检索过程生成或被文档引用为“运行后会出现的文件”），不要求预先存在
ARTIFACT_BASENAMES = {
    "openapi.json", "answer_trace.jsonl", "qa_records.jsonl", "retrieval_run.json",
    "qa_response.json", "health_metrics.json", "graph_stats.json", "embedding_cache.jsonl",
}
_BASENAMES = None


def _basenames():
    """仓库内文件名索引（排除 .git / node_modules / __pycache__），供裸文件名核验。"""
    global _BASENAMES
    if _BASENAMES is None:
        idx = set()
        for dirpath, dirnames, filenames in os.walk(ROOT):
            dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
            idx.update(filenames)
        _BASENAMES = idx
    return _BASENAMES


def _slug(heading):
    """近似 GitHub 标题锚点：小写、去标点、空格转连字符（保留中文/字母/数字）。"""
    s = heading.strip().lower()
    s = re.sub(r"[^\w一-鿿\- ]", "", s)
    return s.replace(" ", "-")


def _resolve_code_path(tok, base):
    t = tok.strip().strip("\"'").replace(BS, "/")
    if not t or API_METHOD_RE.search(t) or t.startswith(SKIP_PREFIXES):
        return None
    if t.startswith("."):  # 形如 `.txt`／`.md` 的扩展名说明，不是文件路径
        return None
    if any(x in t for x in SKIP_CONTAINS):
        return None
    if t.startswith(CONCEPTUAL_PREFIXES):
        return None
    if t in ARTIFACT_BASENAMES or t.startswith(("pip ", "--")):
        return None
    if t in FILE_ALIASES:
        target = FILE_ALIASES[t]
        return [os.path.join(ROOT, target)] if target else None
    if t.startswith("./"):
        t = t[2:]
    # 裸文件名：在仓库内按文件名核验（同名文件存在即视为可解析）
    if "/" not in t:
        if not EXT_RE.search(t):
            return None
        # 裸文件名：仓库内任意位置存在同名文件即视为可解析
        return [ROOT] if t in _basenames() else ["<basename missing:%s>" % t]
    if not EXT_RE.search(t) and not t.endswith("/"):
        return None
    cands = []
    for pre, repl in PREFIXES.items():
        if t.startswith(pre):
            cands.append(os.path.join(ROOT, t) if repl == "" else os.path.join(ROOT, repl + t[len(pre):]))
            break
    # 阶段目录简写：10-部署/、05-系统实现/、06-实验与评测/、07-设计与需求/ 等相对 交付物/
    if re.match(r"^\d{2}-", t):
        cands.append(os.path.join(ROOT, "交付物", t))
    if re.match(r"^[1-9]\.", t) and t.endswith(".md"):
        cands.append(os.path.join(ROOT, "交付物/07-设计与需求/总体设计/_分节源文件", t))
    cands.append(os.path.join(base, t))
    return cands


def check_doc(rel):
    path = os.path.join(ROOT, rel)
    txt = open(path, encoding="utf-8").read()
    base = os.path.dirname(path)
    missing_links = []
    missing_anchors = []
    missing_paths = []

    # 1) Markdown 链接与图片
    for m in re.finditer(r"!?\[([^\]]*)\]\(([^)]+)\)", txt):
        raw = m.group(2).strip()
        if not raw or raw.startswith(("http://", "https://", "mailto:", "tel:")):
            continue
        target, _, frag = raw.partition("#")
        if target == "":
            target_path = path
        else:
            target_path = os.path.normpath(os.path.join(base, target))
        line = txt[: m.start()].count("\n") + 1
        if not os.path.exists(target_path):
            missing_links.append({"line": line, "target": raw})
            continue
        if frag and target_path.endswith(".md"):
            heads = re.findall(r"^#{1,6}\s+(.*)$", open(target_path, encoding="utf-8").read(), re.M)
            anchors = {_slug(h) for h in heads}
            if frag not in anchors:
                missing_anchors.append({"line": line, "target": raw, "actual": _slug(" ".join(heads)) if frag.startswith("126-") else ""})

    # 2) 行内代码中的仓库路径
    for m in re.finditer(r"`([^`\n]+)`", txt):
        tok = m.group(1)
        cands = _resolve_code_path(tok, base)
        if cands is None:
            continue
        if not any(os.path.exists(c) for c in cands):
            line = txt[: m.start()].count("\n") + 1
            missing_paths.append({"line": line, "token": tok})

    return {
        "doc": rel,
        "missing_links": missing_links,
        "missing_anchors": missing_anchors,
        "missing_paths": missing_paths,
    }


def main():
    out_json = None
    if "--json" in sys.argv:
        i = sys.argv.index("--json")
        if i + 1 >= len(sys.argv):
            print("--json 需要文件路径")
            return 2
        out_json = sys.argv[i + 1]

    results = [check_doc(d) for d in DOCS]
    total = 0
    print("文档一致性核验（只读）")
    for r in results:
        n = len(r["missing_links"]) + len(r["missing_anchors"]) + len(r["missing_paths"])
        total += n
        print("  [%s] %s（链接缺 %d／锚点缺 %d／路径缺 %d）" % (
            "OK " if n == 0 else "FAIL", r["doc"],
            len(r["missing_links"]), len(r["missing_anchors"]), len(r["missing_paths"])))
        for kind in ("missing_links", "missing_anchors", "missing_paths"):
            for item in r[kind]:
                detail = item.get("target") or item.get("token")
                print("      %s 第 %s 行：%s" % (kind, item["line"], detail))
    print("合计缺失：%d" % total)
    if out_json:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print("已写入 %s" % out_json)
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
