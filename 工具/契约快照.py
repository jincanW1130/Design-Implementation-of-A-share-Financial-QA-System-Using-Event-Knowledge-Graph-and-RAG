# -*- coding: utf-8 -*-
"""工具\\契约快照.py —— 后端 OpenAPI 契约的**快照门禁**（第二轮第 7 轮新增）。

做什么
------
1. `--write`：在**不启动服务**的前提下装配后端应用（`后端/main.py` 的 `create_app()`），
   读取 `app.openapi()`，把「路径集合＋每路径方法集＋关键 schema 名称」写到
   `交付物/03-代码/后端/_契约快照.json`（**入库**，不是 gitignore 产物）。
2. 默认模式：重新生成当前契约并与快照逐项比对；任何差异（路径增删、方法增删、
   schema 增删、OpenAPI 版本变化）都打印出来并以**退出码 1** 结束，便于并入 `--gate`。

为什么要快照
------------
路由数量（30 paths／33 ops）只是计数，计数不变也可能「换了路径」「把 GET 改成 POST」。
快照门禁盯的是**集合本身**：任何接口契约变动都必须显式 `--write` 重登记，评审时
diff 一眼可见。快照只记录契约骨架，不记录响应体样例，也不改任何运行时行为。

用法
----
    python 工具\\契约快照.py            # 比对当前契约与快照（退出码 0/1）
    python 工具\\契约快照.py --write    # 重新生成快照（显式登记契约变更）

边界
----
* 只读：装配应用不会访问 MySQL／Neo4j／模型，也不会写库；
* 不新增依赖：只用标准库 + FastAPI 自带的 `app.openapi()`；
* schema 名单只收 `components.schemas` 的**名字**（不含字段细节），避免把自动生成的
  Pydantic 组件结构差异误报成契约破坏。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "交付物", "03-代码", "后端")
SNAPSHOT = os.path.join(BACKEND, "_契约快照.json")

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def current_contract() -> dict:
    """装配后端应用并抽取契约骨架（与是否已启动 :8000 无关）。"""
    if BACKEND not in sys.path:
        sys.path.insert(0, BACKEND)
    logging.disable(logging.CRITICAL)          # 静默装配日志；契约输出保持干净
    warnings.filterwarnings("ignore")          # HEAD/GET 同函数会产生重复 operationId 警告
    import main                                # noqa: PLC0415（需先注入 sys.path）

    spec = main.app.openapi()
    paths = {}
    for path in sorted(spec.get("paths", {})):
        methods = sorted(m.upper() for m in spec["paths"][path])
        paths[path] = methods
    operations = sorted("%s %s" % (method, path)
                        for path, methods in paths.items() for method in methods)
    schemas = sorted((spec.get("components") or {}).get("schemas") or {})
    return {
        "generated_by": "工具/契约快照.py",
        "openapi_version": str(spec.get("openapi", "")),
        "path_count": len(paths),
        "operation_count": len(operations),
        "paths": paths,
        "operations": operations,
        "schemas": schemas,
    }


def load_snapshot() -> dict | None:
    if not os.path.isfile(SNAPSHOT):
        return None
    with open(SNAPSHOT, "r", encoding="utf-8") as fh:
        return json.load(fh)


def write_snapshot(contract: dict) -> None:
    with open(SNAPSHOT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(contract, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def diff_contract(old: dict, new: dict) -> list[str]:
    """返回人类可读的差异行（空列表＝一致）。"""
    diffs: list[str] = []

    old_paths = old.get("paths") or {}
    new_paths = new.get("paths") or {}
    for path in sorted(set(new_paths) - set(old_paths)):
        diffs.append("新增路径：%s（%s）" % (path, "、".join(new_paths[path])))
    for path in sorted(set(old_paths) - set(new_paths)):
        diffs.append("删除路径：%s（原 %s）" % (path, "、".join(old_paths[path])))
    for path in sorted(set(old_paths) & set(new_paths)):
        added = sorted(set(new_paths[path]) - set(old_paths[path]))
        removed = sorted(set(old_paths[path]) - set(new_paths[path]))
        if added:
            diffs.append("方法新增：%s ＋%s" % (path, "、".join(added)))
        if removed:
            diffs.append("方法删除：%s －%s" % (path, "、".join(removed)))

    old_schemas = set(old.get("schemas") or [])
    new_schemas = set(new.get("schemas") or [])
    for name in sorted(new_schemas - old_schemas):
        diffs.append("新增 schema：%s" % name)
    for name in sorted(old_schemas - new_schemas):
        diffs.append("删除 schema：%s" % name)

    if str(old.get("openapi_version", "")) != str(new.get("openapi_version", "")):
        diffs.append("OpenAPI 版本变化：%s → %s"
                     % (old.get("openapi_version"), new.get("openapi_version")))
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="后端 OpenAPI 契约快照：生成或比对")
    ap.add_argument("--write", action="store_true", help="生成/覆盖 _契约快照.json")
    args = ap.parse_args(argv)

    contract = current_contract()
    print("=" * 78)
    print("OpenAPI 契约快照（%s）" % SNAPSHOT)
    print("实测：OpenAPI %s；%d 条路径／%d 个操作；schema %d 个"
          % (contract["openapi_version"], contract["path_count"],
             contract["operation_count"], len(contract["schemas"])))
    print("=" * 78)

    if args.write:
        write_snapshot(contract)
        print("已写入快照：%s" % SNAPSHOT)
        for path, methods in contract["paths"].items():
            print("  %-52s %s" % (path, "、".join(methods)))
        return 0

    old = load_snapshot()
    if old is None:
        print("FAIL：快照不存在。首次使用请执行：python 工具\\契约快照.py --write")
        return 1

    diffs = diff_contract(old, contract)
    if diffs:
        print("FAIL：当前契约与快照不一致（%d 处）：" % len(diffs))
        for line in diffs:
            print("  - %s" % line)
        print("\n若变更属预期，请复核后用 `--write` 重登记快照并随代码一起提交。")
        return 1

    print("OK：契约与快照一致（%d 条路径／%d 个操作／%d 个 schema）。"
          % (contract["path_count"], contract["operation_count"], len(contract["schemas"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
