# -*- coding: utf-8 -*-
"""工具\\校验compose.py —— 第二轮第 9 轮：`docker-compose.yml` 的结构门禁。

为什么需要它
------------
本机 WSL2 的 `docker.io` 包**不带 compose 插件**（`docker compose` → unknown command），
`up -d` 无法实跑。此前只做过一次人工 YAML 解析，Compose 清单的任何后续改动都没有门禁。
本脚本把「结构必须成立」的判据固化成可重复执行的检查，**不拉起任何容器**：

1. **服务数**：恰为 `mysql`／`neo4j`／`backend`／`frontend` 四个；
2. **必需卷**：五个命名卷在顶层声明，且分别挂到约定容器的约定路径；
3. **端口映射**：3306／7474／7687／8000／5173 与既有端口口径一致；
4. **依赖顺序**：backend 等 mysql／neo4j 健康，frontend 等 backend 启动；
5. **口令来源**：MySQL／Neo4j 口令只允许 `${...}` 插值（来自 `.env`），
   任何 `*PASSWORD*` 环境变量都不得出现字面量；`.env.example` 必须列出两个口令键；
6. **容器内地址**：backend 指向服务名 `mysql`／`neo4j`，日志目录落在 `backend-logs` 卷内。

用法
----
    python 工具\\校验compose.py
    python 工具\\校验compose.py --file 交付物/10-部署/docker-compose.yml

退出码：0 = 全部检查通过；1 = 有检查失败；2 = PyYAML 不可用或文件无法解析。
**只读**：不执行 docker，不创建／删除任何容器、卷或文件。
"""

from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_FILE = os.path.join(ROOT, "交付物", "10-部署", "docker-compose.yml")
ENV_EXAMPLE = os.path.join(ROOT, "交付物", "10-部署", ".env.example")

EXPECTED_SERVICES = ("mysql", "neo4j", "backend", "frontend")

# 命名卷 → (挂载它的服务, 容器内路径)
REQUIRED_VOLUMES = {
    "mysql-data": ("mysql", "/var/lib/mysql"),
    "neo4j-data": ("neo4j", "/data"),
    "neo4j-logs": ("neo4j", "/logs"),
    "backend-logs": ("backend", "/app/logs"),
    "backend-work": ("backend", "/app/交付物/05-系统实现/前后端系统集成/_工作底稿"),
}

EXPECTED_PORTS = {
    "mysql": ("3306:3306",),
    "neo4j": ("7474:7474", "7687:7687"),
    "backend": ("8000:8000",),
    "frontend": ("5173:80",),
}

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


def _environment(service: dict) -> dict:
    """把 Compose 的两种 environment 写法（映射／`KEY=VALUE` 列表）统一成 dict。"""
    raw = service.get("environment") or {}
    if isinstance(raw, list):
        out = {}
        for item in raw:
            key, _, value = str(item).partition("=")
            out[key.strip()] = value
        return out
    return {str(k): str(v) for k, v in raw.items()}


def _ports(service: dict) -> list:
    out = []
    for item in service.get("ports") or []:
        if isinstance(item, dict):
            published = item.get("published")
            target = item.get("target")
            out.append("%s:%s" % (published, target) if published else str(target))
        else:
            out.append(str(item))
    return out


def _mounts(service: dict) -> list:
    """返回 `(source, target)`；兼容短语法 `src:dst[:mode]` 与长语法映射。"""
    out = []
    for item in service.get("volumes") or []:
        if isinstance(item, dict):
            out.append((str(item.get("source", "")), str(item.get("target", ""))))
            continue
        parts = str(item).split(":")
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def _depends_condition(service: dict, dependency: str):
    """`depends_on` 的两种写法都归一成 condition（缺省 service_started）；未依赖返回 None。"""
    raw = service.get("depends_on") or {}
    if isinstance(raw, list):
        return "service_started" if dependency in raw else None
    if dependency not in raw:
        return None
    item = raw.get(dependency)
    if isinstance(item, dict):
        return item.get("condition", "service_started")
    return "service_started" if item is not None else None


def _env_refers_to(value, variable: str) -> bool:
    """值是否为 `${VARIABLE...}` 插值（允许 `:?提示`／`:-默认` 后缀）。"""
    text = str(value or "").strip()
    return text.startswith("${" + variable) and text.endswith("}")


def _check(rows: list, label: str, ok: bool, detail: str = "") -> None:
    rows.append((label, bool(ok), detail))


def validate(document: dict, env_example_text: str | None) -> list:
    rows: list = []
    if not isinstance(document, dict):
        _check(rows, "顶层是 YAML 映射", False, "实际类型 %s" % type(document).__name__)
        return rows
    _check(rows, "顶层是 YAML 映射", True)

    services = document.get("services")
    if not isinstance(services, dict):
        _check(rows, "services 区块存在", False)
        return rows
    _check(rows, "services 区块存在", True)

    # ---- 1. 服务集合 ----
    _check(rows, "服务数恰为 4（%s）" % "、".join(EXPECTED_SERVICES),
           set(services) == set(EXPECTED_SERVICES),
           "实际：%s" % "、".join(sorted(services)))
    missing = [name for name in EXPECTED_SERVICES if name not in services]
    if missing:
        return rows

    # ---- 2. 卷 ----
    declared = document.get("volumes") or {}
    declared_names = set(declared) if isinstance(declared, dict) else set()
    for volume, (service, target) in REQUIRED_VOLUMES.items():
        _check(rows, "卷 %s 已在顶层声明" % volume, volume in declared_names,
               "" if volume in declared_names else "顶层 volumes 缺该键")
        mounted = target in [dst for _src, dst in _mounts(services[service])]
        _check(rows, "卷 %s 挂到 %s:%s" % (volume, service, target), mounted,
               "" if mounted else "%s 的 volumes 未挂载 %s" % (service, target))

    # ---- 3. 端口 ----
    for service, expected in EXPECTED_PORTS.items():
        actual = _ports(services[service])
        for mapping in expected:
            _check(rows, "%s 端口 %s" % (service, mapping), mapping in actual,
                   "" if mapping in actual else "实际：%s" % ("、".join(actual) or "（无）"))

    # ---- 4. 依赖顺序 ----
    for dependency, condition in (("mysql", "service_healthy"), ("neo4j", "service_healthy")):
        actual = _depends_condition(services["backend"], dependency)
        _check(rows, "backend 等 %s（%s）" % (dependency, condition), actual == condition,
               "" if actual == condition else "实际：%r" % actual)
    actual = _depends_condition(services["frontend"], "backend")
    _check(rows, "frontend 等 backend（service_started）", actual == "service_started",
           "" if actual == "service_started" else "实际：%r" % actual)

    # ---- 5. 口令只来自 .env ----
    mysql_env = _environment(services["mysql"])
    neo4j_env = _environment(services["neo4j"])
    backend_env = _environment(services["backend"])

    _check(rows, "MySQL 口令来自 ${MYSQL_ROOT_PASSWORD}",
           _env_refers_to(mysql_env.get("MYSQL_ROOT_PASSWORD"), "MYSQL_ROOT_PASSWORD"),
           "实际：%r" % mysql_env.get("MYSQL_ROOT_PASSWORD"))
    _check(rows, "Neo4j 口令来自 ${NEO4J_PASSWORD}",
           str(neo4j_env.get("NEO4J_AUTH", "")).startswith("neo4j/${NEO4J_PASSWORD")
           and str(neo4j_env.get("NEO4J_AUTH", "")).endswith("}"),
           "实际：%r" % neo4j_env.get("NEO4J_AUTH"))
    _check(rows, "backend 的 MySQL 口令引用同一变量",
           _env_refers_to(backend_env.get("ASHARE_MYSQL_PASSWORD"), "MYSQL_ROOT_PASSWORD"),
           "实际：%r" % backend_env.get("ASHARE_MYSQL_PASSWORD"))
    _check(rows, "backend 的 Neo4j 口令引用同一变量",
           _env_refers_to(backend_env.get("ASHARE_NEO4J_PASSWORD"), "NEO4J_PASSWORD"),
           "实际：%r" % backend_env.get("ASHARE_NEO4J_PASSWORD"))

    literal = []
    for service_name, service in services.items():
        for key, value in _environment(service).items():
            if "PASSWORD" in key.upper() and "${" not in str(value):
                literal.append("%s.%s 为字面量" % (service_name, key))
    _check(rows, "没有硬编码口令（*PASSWORD* 全部为 ${...} 插值）", not literal,
           "；".join(literal))

    if env_example_text is None:
        _check(rows, ".env.example 存在且列出两个口令键", False, "文件不存在")
    else:
        has_mysql = re.search(r"(?m)^MYSQL_ROOT_PASSWORD\s*=", env_example_text) is not None
        has_neo4j = re.search(r"(?m)^NEO4J_PASSWORD\s*=", env_example_text) is not None
        _check(rows, ".env.example 列出 MYSQL_ROOT_PASSWORD／NEO4J_PASSWORD",
               has_mysql and has_neo4j,
               "" if has_mysql and has_neo4j else "缺 MYSQL_ROOT_PASSWORD 或 NEO4J_PASSWORD")

    # ---- 6. 容器内地址与日志卷 ----
    _check(rows, "backend 的 MySQL 主机为服务名 mysql",
           backend_env.get("ASHARE_MYSQL_HOST") == "mysql",
           "实际：%r" % backend_env.get("ASHARE_MYSQL_HOST"))
    _check(rows, "backend 的 Neo4j URI 指向服务名 neo4j",
           str(backend_env.get("ASHARE_NEO4J_URI", "")).startswith("bolt://neo4j:"),
           "实际：%r" % backend_env.get("ASHARE_NEO4J_URI"))
    log_path = str(backend_env.get("ASHARE_LOG_PATH", ""))
    _check(rows, "backend 日志路径落在 backend-logs 卷（/app/logs）内",
           log_path.startswith("/app/logs/"), "实际：%r" % log_path)

    return rows


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="校验 docker-compose.yml 的结构与口令来源")
    parser.add_argument("--file", default=DEFAULT_FILE, help="Compose 文件（默认 %s）" % DEFAULT_FILE)
    args = parser.parse_args(argv)

    print("=" * 78)
    print("Compose 结构校验：%s" % args.file)
    print("=" * 78)

    if not os.path.isfile(args.file):
        print("[FAIL] 文件不存在。")
        return 1
    try:
        import yaml
    except ImportError:
        print("[FAIL] 未安装 PyYAML（`pip install pyyaml`），无法解析 Compose 文件。")
        return 2
    try:
        with open(args.file, "r", encoding="utf-8") as handle:
            document = yaml.safe_load(handle)
    except Exception as exc:                              # noqa: BLE001
        print("[FAIL] YAML 解析失败：%s: %s" % (type(exc).__name__, exc))
        return 2

    env_example_text = None
    if os.path.isfile(ENV_EXAMPLE):
        with open(ENV_EXAMPLE, "r", encoding="utf-8") as handle:
            env_example_text = handle.read()

    rows = validate(document, env_example_text)
    failures = 0
    for label, ok, detail in rows:
        suffix = ("  ← %s" % detail) if (not ok and detail) else ""
        print("  [%s] %s%s" % ("OK " if ok else "FAIL", label, suffix))
        if not ok:
            failures += 1

    print("-" * 78)
    print("检查 %d 项：通过 %d，失败 %d。" % (len(rows), len(rows) - failures, failures))
    if failures:
        print("结论：Compose 清单不符合结构门禁。退出码 1。")
        return 1
    print("结论：4 服务／5 卷／端口／依赖顺序／口令来源全部符合。退出码 0。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
