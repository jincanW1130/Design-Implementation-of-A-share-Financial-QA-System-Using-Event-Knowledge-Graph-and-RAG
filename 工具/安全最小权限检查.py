# -*- coding: utf-8 -*-
"""工具\\安全最小权限检查.py —— 安全加固与最小权限的**只读审计**（第三轮 6.3/6.4）。

做什么
------
按《安全加固与最小权限清单》逐项采集当前事实，输出 JSON 报告与终端摘要：

1. 配置与凭据：`config.local.json` 是否存在/被 git 忽略、密钥是否已配置、长度是否达标、
   ACL 是否过宽；**绝不打印任何口令或令牌取值**。
2. MySQL：当前账号、授权、`bind_address`、版本；识别 root/ALL PRIVILEGES/GRANT OPTION。
3. Neo4j：版本/edition、当前账号；说明 Community 版无细粒度 RBAC。
4. 网络暴露：3306/33060/7474/7687/8000/5173 的监听地址。
5. HTTP 面：健康检查、后台缺令牌 4001、前端来源 4002（只发不带令牌的探测请求）。
6. 泄露扫描：用本地配置中的密钥取值去扫描 git 已跟踪文本文件，**只报文件路径与数量**。

边界
----
* **只读**：不创建/删除账号，不修改口令、授权、配置、防火墙，不写数据库。
* 不做端口扫描、不访问外网；HTTP 探测只打本机 8000。
* 报告默认写到 `交付物/06-实验与评测/系统指标/安全最小权限检查_第三轮.json`。
* 退出码：默认 0（审计完成即可）；`--strict` 时存在 high/critical 项返回 1。

用法
----
    python 工具\\安全最小权限检查.py
    python 工具\\安全最小权限检查.py --skip-live --skip-secret-scan
    python 工具\\安全最小权限检查.py --strict
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

import config  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

DEFAULT_OUT = os.path.join(
    ROOT, "交付物", "06-实验与评测", "系统指标", "安全最小权限检查_第三轮.json")
CONFIG_LOCAL = os.path.join(BACKEND, "config.local.json")

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
FINDINGS: list[dict] = []


def finding(severity: str, area: str, title: str, detail: str, advice: str) -> None:
    """登记一项审计发现。detail／advice 不得包含任何密钥取值。"""
    FINDINGS.append({"severity": severity, "area": area, "title": title,
                     "detail": detail, "advice": advice})


def run(cmd: list[str], timeout: int = 20) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        return p.returncode, p.stdout or "", p.stderr or ""
    except Exception as exc:
        return 127, "", "%s: %s" % (type(exc).__name__, exc)


# --------------------------------------------------------------------------
# 1. 配置与凭据
# --------------------------------------------------------------------------
def check_config() -> dict:
    info: dict = {"config_local": CONFIG_LOCAL, "exists": os.path.isfile(CONFIG_LOCAL)}
    if not info["exists"]:
        finding("critical", "config", "config.local.json 不存在",
                "后端无法读取 MySQL/Neo4j 凭据。",
                "按 config.local.json.example 创建本地配置，并确保不入库。")
        return info

    code, out, _ = run(["git", "-C", ROOT, "check-ignore", "-v", CONFIG_LOCAL])
    info["git_ignored"] = (code == 0)
    if code != 0:
        finding("critical", "config", "config.local.json 未被 git 忽略",
                "凭据文件可能被提交到仓库。",
                "在 .gitignore 中登记 config.local.json，并检查历史提交。")
    else:
        finding("info", "config", "config.local.json 已被 git 忽略", out.strip()[:300],
                "保持现状。")

    code, out, _ = run(["git", "-C", ROOT, "ls-files", "--error-unmatch",
                        os.path.relpath(CONFIG_LOCAL, ROOT)])
    info["git_tracked"] = (code == 0)
    if info["git_tracked"]:
        finding("critical", "config", "config.local.json 已被 git 跟踪",
                "凭据文件进入了版本库。",
                "git rm --cached 后轮换全部凭据，并清理历史。")

    token = getattr(config, "ADMIN_TOKEN", None)
    info["admin_token_configured"] = bool(token)
    info["admin_token_length"] = len(token) if token else 0
    if not token:
        finding("high", "config", "admin_token 未配置",
                "后台接口当前 fail closed（全部 4001），但运维/实验通道不可用。",
                "生成至少 32 字符的随机令牌，写入本地配置或环境变量后重启后端。")
    elif len(token) < 24:
        finding("high", "config", "admin_token 长度偏短",
                "实测长度 %d（不显示取值）。" % len(token),
                "至少 32 字符的密码学随机串；轮换后同步更新运维脚本的密钥来源。")
    else:
        finding("info", "config", "admin_token 已配置且长度达标",
                "实测长度 %d（不显示取值）。" % len(token),
                "定期轮换；不要写入文档、脚本或日志。")

    info["mysql_password_configured"] = bool(getattr(config, "MYSQL_PASSWORD_READY", False))
    info["neo4j_password_configured"] = bool(getattr(config, "NEO4J_PASSWORD_READY", False))
    if not info["mysql_password_configured"]:
        finding("high", "config", "MySQL 口令未配置",
                "config.MYSQL_PASSWORD_READY 为 False。", "在本地配置中填写口令。")
    if not info["neo4j_password_configured"]:
        finding("medium", "config", "Neo4j 口令为空/占位",
                "本机 Neo4j 可能未启用认证。", "设置强口令并确认认证已启用。")

    # ACL：只报告“除系统/当前用户外仍可读”的主体，不展示 ACL 中的敏感信息（ACL 本身不含口令）
    code, out, _ = run(["icacls", CONFIG_LOCAL])
    info["acl_raw"] = out.strip()[:1000] if code == 0 else "icacls 不可用"
    if code == 0:
        suspicious = []
        for line in out.splitlines():
            low = line.lower()
            if any(x in low for x in ("everyone", "authenticated users", "users:",
                                      "codexsandboxusers")):
                suspicious.append(line.strip())
        info["acl_broad_principals"] = suspicious
        if suspicious:
            finding("medium", "config", "config.local.json ACL 含较宽主体",
                    "；".join(suspicious)[:500],
                    "仅保留当前用户、SYSTEM、Administrators 的完全控制；移除其他主体的读取权限。")
        else:
            finding("info", "config", "config.local.json ACL 未发现宽主体",
                    "未匹配 Everyone/Authenticated Users/Users 等常见宽主体。", "定期复核。")

    origins = list(getattr(config, "CORS_ORIGINS", []) or [])
    info["cors_origins"] = origins
    if "*" in origins:
        finding("high", "config", "CORS 允许任意来源", "CORS_ORIGINS 含 *。",
                "改为明确的前端来源列表。")
    else:
        finding("info", "config", "CORS 为白名单", "、".join(origins) or "（空）",
                "生产环境只保留实际域名。")

    rate = dict(getattr(config, "RATE_LIMIT", {}) or {})
    info["rate_limit"] = rate
    finding("info", "config", "限流参数", "window=%s s，max=%s 次"
            % (rate.get("window_seconds"), rate.get("max_requests")),
            "生产环境按容量复核；压测时才临时放宽。")
    return info


# --------------------------------------------------------------------------
# 2. MySQL
# --------------------------------------------------------------------------
def check_mysql() -> dict:
    info: dict = {}
    try:
        import db
    except Exception as exc:
        finding("high", "mysql", "无法导入后端 db 模块", "%s: %s" % (type(exc).__name__, exc),
                "检查后端依赖与路径。")
        return {"status": "unavailable"}

    try:
        row = db.query_one(
            "SELECT CURRENT_USER() AS cu, @@version AS version, "
            "@@bind_address AS bind_address, @@port AS port")
    except Exception as exc:
        finding("high", "mysql", "MySQL 不可达", "%s: %s" % (type(exc).__name__, exc),
                "确认服务运行与凭据有效。")
        return {"status": "unavailable"}

    info.update({"status": "checked", **{k: str(v) for k, v in row.items()}})
    user = str(row.get("cu") or "")
    bind = str(row.get("bind_address") or "")
    if user.startswith("root@"):
        finding("high", "mysql", "应用使用 root 账号",
                "CURRENT_USER()=%s。应用拥有建库/授权/关闭服务等全部权限。" % user,
                "为运行期创建 DML-only 账号；root 仅用于一次性建表/导入/运维。")
    if bind in ("*", "0.0.0.0", "::"):
        finding("high", "mysql", "MySQL 监听所有网卡",
                "@@bind_address=%r，端口 %s。" % (bind, row.get("port")),
                "仅在需要远程访问时开放；单机部署改为 127.0.0.1 并配置防火墙。")

    grants: list[str] = []
    try:
        for r in db.query("SHOW GRANTS FOR CURRENT_USER()"):
            grants.extend(str(v) for v in r.values())
    except Exception as exc:
        finding("medium", "mysql", "无法读取授权", "%s: %s" % (type(exc).__name__, exc),
                "用具备相应权限的账号人工核对 SHOW GRANTS。")
    info["grants"] = grants
    joined = "\n".join(grants)
    if "ALL PRIVILEGES" in joined or "WITH GRANT OPTION" in joined:
        finding("high", "mysql", "应用账号权限过大",
                "授权含 ALL PRIVILEGES 或 GRANT OPTION（详见报告 grants 字段）。",
                "运行期账号只保留 SELECT/INSERT/UPDATE/DELETE ON ashare_qa.*。")
    if "CREATE USER" in joined or "DROP ROLE" in joined:
        finding("high", "mysql", "应用账号可管理账号/角色",
                "授权含 CREATE USER／CREATE ROLE／DROP ROLE。",
                "账号管理只留给独立 DBA 账号。")
    return info


# --------------------------------------------------------------------------
# 3. Neo4j
# --------------------------------------------------------------------------
def check_neo4j() -> dict:
    info: dict = {"status": "unavailable"}
    try:
        from neo4j import GraphDatabase, basic_auth
        params = config.neo4j_params()
        driver = GraphDatabase.driver(params["uri"],
                                      auth=basic_auth(params["user"], params["password"]),
                                      connection_timeout=5)
        with driver.session() as s:
            comp = s.run("CALL dbms.components() YIELD name, versions, edition "
                         "RETURN name, versions, edition").single()
            cur = s.run("SHOW CURRENT USER").single()
        driver.close()
        info = {"status": "checked",
                "component": dict(comp) if comp else {},
                "current_user": dict(cur) if cur else {}}
    except Exception as exc:
        finding("high", "neo4j", "Neo4j 不可达或认证失败",
                "%s: %s" % (type(exc).__name__, exc), "确认服务与凭据。")
        return info

    comp = info["component"]
    edition = str(comp.get("edition") or "").lower()
    user = str((info.get("current_user") or {}).get("user") or "")
    if edition == "community":
        finding("medium", "neo4j", "Community Edition 无细粒度 RBAC",
                "实测 edition=community，SHOW ROLES 不受支持；无法按标签/属性授权。",
                "用独立实例+127.0.0.1 绑定+防火墙隔离；需要细粒度角色时升级 Enterprise。")
    if user == "neo4j":
        finding("medium", "neo4j", "使用默认管理员账号 neo4j",
                "当前账号为 neo4j（内置管理员）。",
                "如版本支持，创建专用应用账号；否则用网络隔离与独立实例限制影响面。")
    return info


# --------------------------------------------------------------------------
# 4. 网络监听
# --------------------------------------------------------------------------
def check_listeners() -> dict:
    ports = {3306, 33060, 7474, 7687, 8000, 5173}
    out_info: dict = {}
    if os.name != "nt":
        return {"status": "skipped", "reason": "非 Windows，请自行核对 ss/netstat"}
    code, out, err = run(["netstat", "-ano", "-p", "TCP"])
    if code != 0:
        return {"status": "unavailable", "error": (err or out)[:300]}
    listeners = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4 or "LISTEN" not in line.upper():
            continue
        local = parts[1]
        try:
            port = int(local.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            continue
        if port in ports:
            listeners.append({"local": local, "port": port})
    out_info = {"status": "checked", "listeners": listeners}
    exposed = {x["port"] for x in listeners
               if x["local"].startswith(("0.0.0.0", "[::]", ":::"))}
    if 3306 in exposed:
        finding("high", "network", "MySQL 对非本机开放", "3306 监听 0.0.0.0/::。",
                "单机部署改为 bind-address=127.0.0.1，或限制防火墙来源。")
    if 33060 in exposed:
        finding("medium", "network", "MySQL X Protocol 对非本机开放", "33060 监听所有网卡。",
                "不需要 X Protocol 时关闭；需要时限制来源。")
    if 7474 in exposed or 7687 in exposed:
        finding("high", "network", "Neo4j 对非本机开放", "7474/7687 监听所有网卡。",
                "绑定 127.0.0.1 并配置防火墙。")
    if 8000 in exposed:
        finding("medium", "network", "后端对非本机开放", "8000 监听所有网卡。",
                "生产环境置于 Nginx 之后，uvicorn 绑定 127.0.0.1。")
    if 5173 in exposed:
        finding("medium", "network", "Vite 开发服务器对非本机开放", "5173 监听所有网卡。",
                "仅开发期使用；生产用构建产物 + Nginx 静态服务。")
    if not exposed:
        finding("info", "network", "目标端口未监听在通配地址", "仅本机或未监听。", "保持。")
    return out_info


# --------------------------------------------------------------------------
# 5. HTTP 面（只发不带令牌的只读探测）
# --------------------------------------------------------------------------
def _http(method: str, path: str, headers: dict | None = None) -> dict:
    url = "http://127.0.0.1:8000" + path
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return {"http": r.status, "body": json.loads(r.read().decode("utf-8")),
                    "request_id": dict(r.headers).get("x-request-id")}
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except Exception:
            body = None
        return {"http": e.code, "body": body,
                "request_id": dict(e.headers).get("x-request-id")}
    except Exception as exc:
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def check_http() -> dict:
    health = _http("GET", "/api/health")
    admin = _http("GET", "/api/admin/consistency-check")
    admin_origin = _http("GET", "/api/admin/consistency-check",
                         {"Origin": "http://127.0.0.1:5173"})
    info = {"health": health, "admin_without_token": admin,
            "admin_with_frontend_origin": admin_origin}
    if health.get("http") == 200:
        finding("info", "http", "健康检查可用",
                "status=%s" % (health.get("body") or {}).get("status"),
                "保持。")
    else:
        finding("high", "http", "健康检查不可用", json.dumps(health, ensure_ascii=False)[:300],
                "确认后端已启动。")
    if admin.get("http") == 401 and (admin.get("body") or {}).get("code") == 4001:
        finding("info", "http", "后台缺令牌正确返回 4001",
                "HTTP 401，响应体 {code, message}。", "保持 fail closed。")
    else:
        finding("critical", "http", "后台缺令牌未按 4001 拒绝",
                json.dumps(admin, ensure_ascii=False)[:400],
                "检查 require_admin 依赖与 admin_token 配置。")
    if admin_origin.get("http") == 403 and (admin_origin.get("body") or {}).get("code") == 4002:
        finding("info", "http", "前端来源访问后台正确返回 4002",
                "HTTP 403。", "保持。")
    else:
        finding("high", "http", "前端来源访问后台未按 4002 拒绝",
                json.dumps(admin_origin, ensure_ascii=False)[:400],
                "检查普通用户通道判定。")
    return info


# --------------------------------------------------------------------------
# 6. 密钥泄露扫描
# --------------------------------------------------------------------------
TEXT_EXTS = {
    ".py", ".js", ".mjs", ".ts", ".vue", ".md", ".txt", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".conf", ".ps1", ".sh", ".bat", ".sql", ".html",
    ".css", ".example", ".env",
}
SKIP_PATH_PARTS = (".git/", "node_modules/", "__pycache__/", "交付物/01-论文/",
                   "交付物/02-答辩/", "交付物/03-代码/前端/dist/")


def check_secret_leaks() -> dict:
    secrets = {}
    if getattr(config, "ADMIN_TOKEN", None):
        secrets["admin_token"] = str(config.ADMIN_TOKEN)
    try:
        dbp = config.db_params()
        if dbp.get("password"):
            secrets["mysql_password"] = str(dbp["password"])
    except SystemExit:
        pass
    try:
        np = config.neo4j_params()
        if np.get("password"):
            secrets["neo4j_password"] = str(np["password"])
    except Exception:
        pass

    # 短口令（<8 字符）在源码中极易与普通单词/标识符子串碰撞，不能作为“泄露”证据；
    # 单列为风险项，只对长度 >= 8 的密钥做精确实例扫描。
    short = sorted(k for k, v in secrets.items() if len(v) < 8)
    secrets = {k: v for k, v in secrets.items() if len(v) >= 8}
    info = {"status": "checked", "scanned_files": 0, "secret_kinds": sorted(secrets),
            "short_secrets_excluded": short, "hits": []}
    if short:
        finding("medium", "secret_scan", "存在短口令，未纳入精确泄露扫描",
                "长度 <8 的密钥：%s（长度过短本身也是风险；不显示取值）。"
                % "、".join(short),
                "改为至少 12 字符的随机口令；轮换后重新运行本脚本。")
    if not secrets:
        info["status"] = "no_scannable_secrets"
        finding("info", "secret_scan", "没有可用于精确扫描的密钥",
                "全部密钥长度 <8，已跳过子串扫描。", "先按清单轮换为强口令。")
        return info

    code, out, err = run(["git", "-C", ROOT, "ls-files", "-z"])
    if code != 0:
        info["status"] = "unavailable"
        info["error"] = (err or out)[:300]
        finding("medium", "secret_scan", "无法列出 git 跟踪文件", info["error"],
                "在仓库根目录执行，或手工扫描。")
        return info

    rel_config = os.path.relpath(CONFIG_LOCAL, ROOT).replace("\\", "/")
    paths = [p for p in out.split("\0") if p]
    for rel in paths:
        norm = rel.replace("\\", "/")
        if norm == rel_config or any(part in norm for part in SKIP_PATH_PARTS):
            continue
        ext = os.path.splitext(norm)[1].lower()
        if ext not in TEXT_EXTS:
            continue
        abs_path = os.path.join(ROOT, norm)
        try:
            if os.path.getsize(abs_path) > 2 * 1024 * 1024:
                continue
            with open(abs_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            continue
        info["scanned_files"] += 1
        for kind, value in secrets.items():
            if value and value in text:
                info["hits"].append({"kind": kind, "file": norm, "count": text.count(value)})

    if info["hits"]:
        finding("critical", "secret_scan", "已跟踪文件中出现真实密钥",
                "命中 %d 处（只显示路径与数量，不显示取值）：%s"
                % (len(info["hits"]),
                   "；".join("%s@%s×%d" % (h["kind"], h["file"], h["count"])
                            for h in info["hits"][:10])),
                "立即轮换对应密钥，改用环境变量/密钥管理，并清理文件与 git 历史。")
    else:
        finding("info", "secret_scan", "已跟踪文本文件未发现真实密钥",
                "扫描 %d 个文件，密钥种类：%s" % (info["scanned_files"], "、".join(secrets)),
                "继续保持；注意报告/截图也可能泄露。")
    return info


# --------------------------------------------------------------------------
# 7. 主流程
# --------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="安全加固与最小权限只读审计")
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--skip-live", action="store_true", help="跳过 MySQL/Neo4j/HTTP 探测")
    parser.add_argument("--skip-secret-scan", action="store_true", help="跳过密钥泄露扫描")
    parser.add_argument("--strict", action="store_true", help="存在 high/critical 时返回 1")
    args = parser.parse_args(argv)

    findings_before = len(FINDINGS)
    report = {
        "tool": "工具/安全最小权限检查.py",
        "generated_at": _dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "read-only/audit",
        "config": check_config(),
        "mysql": {"status": "skipped"} if args.skip_live else check_mysql(),
        "neo4j": {"status": "skipped"} if args.skip_live else check_neo4j(),
        "listeners": {"status": "skipped"} if args.skip_live else check_listeners(),
        "http": {"status": "skipped"} if args.skip_live else check_http(),
        "secret_scan": ({"status": "skipped"} if args.skip_secret_scan
                        else check_secret_leaks()),
    }
    findings = FINDINGS[findings_before:]
    report["findings"] = findings
    report["summary"] = {
        sev: sum(1 for f in findings if f["severity"] == sev)
        for sev in ("critical", "high", "medium", "low", "info")
    }
    report["note"] = ("只读审计：未修改口令/账号/授权/配置/防火墙，未写数据库。"
                      "所有 detail 均不含密钥取值。")

    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("=" * 76)
    print("安全加固与最小权限 · 只读审计")
    print("=" * 76)
    print("  严重度汇总：" + "；".join("%s=%d" % (k, report["summary"][k])
                                 for k in ("critical", "high", "medium", "low", "info")))
    for item in sorted(findings, key=lambda x: SEVERITY_ORDER[x["severity"]]):
        print("  [%-8s] %-10s %s" % (item["severity"], item["area"], item["title"]))
        print("             %s" % item["detail"][:300])
    print("  报告 = %s" % out)
    print("=" * 76)
    print("说明：本轮只审计、不改口令/账号；整改步骤见《安全加固与最小权限清单》。")

    if args.strict and (report["summary"]["critical"] or report["summary"]["high"]):
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已中断（未修改任何配置）。", file=sys.stderr)
        raise SystemExit(130)
