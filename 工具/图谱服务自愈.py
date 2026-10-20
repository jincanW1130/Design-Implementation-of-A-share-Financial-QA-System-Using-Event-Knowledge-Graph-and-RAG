# -*- coding: utf-8 -*-
"""图谱服务自愈：检测 Neo4j bolt 可达性，不可达时按已知根因链自动修复。

背景（2026-10-20 实际排障登记于 过程记录/01-评审与审查/优化执行进展.md）：
Neo4j 跑在 WSL(Ubuntu) 的 Docker 容器 `ashare-neo4j` 内。WSL2 会因主机内存紧张被
强制关机（.wslconfig 自述该机制），容器随之停止；VM 重启后 Windows 侧 localhost 转发
可能失效——表现为 `127.0.0.1:7687` 连接被拒绝，而容器内直连 WSL IP 正常。
本脚本把当时的恢复套路固化为三步：查容器状态 → 按「容器停 / 转发失效」分别处置 →
等待就绪并复验计数。已知根因链之外的失败如实报告，不猜测、不乱修。

用法：
    python 工具/图谱服务自愈.py                 # 检测 + 自动修复 + 复验（默认）
    python 工具/图谱服务自愈.py --check         # 只检测，不做任何修复动作
    python 工具/图谱服务自愈.py --json          # 结果以 JSON 输出（供任务计划程序/巡检）
    python 工具/图谱服务自愈.py --wait 240      # 修复后等待就绪的上限秒数（默认 180）
    python 工具/图谱服务自愈.py --linger 300    # 修复成功后保活窗口秒数（默认 300，0 立即回收）

使用模型（重要）：本机 WSL2 因内存压力会被系统反复关闭，Neo4j 无法常驻，
本脚本定位是**按需恢复**——跑测试／启动后端之前先执行一次；修复成功后保留
一个限时保活会话（--linger，到期自灭），覆盖随后几分钟内的测试/联调窗口。
窗口结束后 VM 仍会被系统关闭，属预期行为；长期方案（Neo4j Windows 服务化或
WSL mirrored networking）见 过程记录/01-评审与审查/优化执行进展.md 2026-10-20 节。

退出码：0 = bolt 可达（计数与冻结基线一致或仅警告）；
        1 = 修复失败 / 环境不具备修复条件；
        2 = bolt 可达但图谱计数与冻结基线不符（图谱可能合法增减，需人工核对）。

冻结基线出处：《25-第9阶段产出文档》与《优化十三轮复验总报告（2026-10-19）》——
Neo4j 5.26.31，3607 节点／3614 关系。基线只做警告级比对，不做阻断。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = ROOT / "交付物" / "03-代码" / "后端"

BASELINE_NODES = 3607
BASELINE_RELS = 3614

# 默认部署形态：发行版与容器名（2026-09-29 起的实际环境）。
# 可用 --distro / --container 覆盖，避免环境迁移时改脚本。
DEFAULT_DISTRO = "Ubuntu"
DEFAULT_CONTAINER = "ashare-neo4j"

# 冷重启后给 systemd/docker daemon 与容器自启留出的保活窗口（秒）。
# 到期进程自动退出，不在 WSL 内留常驻孤儿。
WSL_KEEPALIVE_SECONDS = 600


def _report(steps: list, state: str, item: str, detail: str = "") -> None:
    steps.append({"state": state, "item": item, "detail": detail})
    print("[%s] %s%s" % (state, item, ("；" + detail) if detail else ""))


def _run(cmd: list, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """跑一条命令；不抛异常，把结果交给调用方判定。"""
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(cmd, 127, "", "%s: %s" % (type(exc).__name__, exc))


def _wsl_bash(distro: str, script: str, timeout: float = 60.0,
              user: str | None = None) -> subprocess.CompletedProcess:
    cmd = ["wsl", "-d", distro]
    if user:
        cmd += ["-u", user]
    cmd += ["-e", "bash", "-c", script]
    return _run(cmd, timeout=timeout)


def _bolt_probe() -> dict:
    """用后端同款配置探测 bolt；返回 {'ok', 'nodes', 'rels', 'error'}。"""
    # 后端 config 会校验自身的输入与配置文件，属只读导入。
    sys.path.insert(0, str(BACKEND_DIR))
    import config                                   # noqa: PLC0415
    from neo4j import GraphDatabase                 # noqa: PLC0415

    params = config.neo4j_params()
    driver = GraphDatabase.driver(params["uri"],
                                  auth=(params["user"], params["password"] or None),
                                  connection_timeout=3.0)
    try:
        driver.verify_connectivity()
        with driver.session() as session:
            nodes = session.run("MATCH (n) RETURN count(n) AS n").single()["n"]
            rels = session.run("MATCH ()-[r]->() RETURN count(r) AS n").single()["n"]
        return {"ok": True, "nodes": nodes, "rels": rels, "error": "", "uri": params["uri"]}
    finally:
        driver.close()


def _probe_with_retry(max_seconds: float, interval: float = 5.0) -> dict:
    """轮询等待 bolt 就绪（容器启动与数据库恢复需要时间）。"""
    deadline = time.monotonic() + max_seconds
    last = {"ok": False, "error": "未执行"}
    while time.monotonic() < deadline:
        try:
            last = _bolt_probe()
        except Exception as exc:                       # noqa: BLE001
            first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
            last = {"ok": False, "error": first}
        if last.get("ok"):
            return last
        time.sleep(interval)
    return last


def _container_state(distro: str, container: str) -> dict:
    """查容器状态；区分「daemon 未就绪」「容器不存在」「运行中／已停止」。

    注意：不能往 inspect 命令里加 `2>/dev/null`——WSL 冷启动后 docker daemon
    可能仍在引导，inspect 会 exit 非 0 且报「Cannot connect to the Docker
    daemon」，吞掉 stderr 会把它误判成别的失败（2026-10-20 实测踩坑）。
    返回 {'wsl_ok', 'found', 'running', 'daemon_ready', 'detail'}。
    """
    proc = _wsl_bash(distro,
                     "docker inspect %s --format '{{.State.Status}}'" % container,
                     timeout=120.0, user="root")
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        if "No such object" in err or "No such object" in out:
            return {"wsl_ok": True, "found": False, "running": False,
                    "daemon_ready": True, "detail": "容器 %s 不存在" % container}
        if "Cannot connect to the Docker daemon" in err:
            return {"wsl_ok": True, "found": False, "running": False,
                    "daemon_ready": False, "detail": "docker daemon 未就绪（WSL 可能刚冷启动）"}
        detail = err.splitlines()[0] if err else (
            out.splitlines()[0] if out else "wsl 调用失败（无输出，returncode=%d）" % proc.returncode)
        return {"wsl_ok": False, "found": False, "running": False,
                "daemon_ready": False, "detail": detail}
    status = out
    if not status:
        return {"wsl_ok": True, "found": False, "running": False,
                "daemon_ready": True, "detail": "容器 %s 不存在" % container}
    return {"wsl_ok": True, "found": True, "running": status == "running",
            "daemon_ready": True, "detail": "容器状态=%s" % status}


def _wait_daemon(distro: str, container: str, max_seconds: float) -> dict:
    """WSL 冷启动后 docker daemon 引导需要时间；轮询直到可查容器状态。"""
    deadline = time.monotonic() + max_seconds
    state = _container_state(distro, container)
    while not state.get("wsl_ok") or not state.get("daemon_ready"):
        if time.monotonic() >= deadline:
            return state
        time.sleep(5)
        state = _container_state(distro, container)
    return state


def _spawn_keeper(distro: str, seconds: float):
    """占住一个受管的 WSL 会话，防止等待轮询期间 VM 被系统再次关闭。

    2026-10-20 实测：`wsl --shutdown` 后若只有 nohup 后台进程而无活动 console
    会话，VM 会在修复轮询期间被再次关闭（容器 Started 8 秒后又被 SIGTERM）。
    会话由 Popen 管理：修复失败时调用方立即 terminate；成功后按 --linger
    保留自然到期（限时孤儿，覆盖随后的测试窗口），不做常驻。
    返回 Popen 或 None（启动失败不阻断修复，如实登记）。
    """
    try:
        return subprocess.Popen(
            ["wsl", "-d", distro, "-e", "bash", "-c", "sleep %d" % int(seconds)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        return None


def repair(distro: str, container: str, wait_seconds: float,
           linger_seconds: float) -> tuple:
    """按已知根因链修复；返回 (处理步骤, keeper 进程或 None)。

    keeper 在冷重启路径下创建；失败路径由调用方立即回收，
    成功路径保留 --linger 秒自然到期，覆盖随后的测试窗口。
    """
    steps: list = []
    keeper = None                      # 冷重启路径才需要受管会话
    state = _container_state(distro, container)
    if not state.get("wsl_ok"):
        _report(steps, "FAIL", "WSL/%s 可用性" % distro, state["detail"])
        return steps, None
    if not state.get("daemon_ready"):
        # WSL 冷启动后 docker daemon 还在引导：轮询等待，不立即判死。
        _report(steps, "DO", "等待 docker daemon 引导", state["detail"])
        state = _wait_daemon(distro, container, min(wait_seconds, 120.0))
        if not state.get("daemon_ready"):
            _report(steps, "FAIL", "docker daemon 引导超时", state["detail"])
            return steps, None
        _report(steps, "OK", "docker daemon 已就绪", state["detail"])
    if not state["found"]:
        _report(steps, "FAIL", "容器存在性", state["detail"])
        return steps, None

    if not state["running"]:
        # 根因 A：WSL VM 被关机时容器一并停止 → docker start 即可。
        _report(steps, "DO", "启动容器", "docker start %s" % container)
        proc = _wsl_bash(distro, "docker start %s" % container, timeout=120.0,
                         user="root")
        if proc.returncode != 0:
            _report(steps, "FAIL", "启动容器", (proc.stderr or proc.stdout).strip())
            return steps, None
    else:
        # 根因 B：容器在跑但 Windows 侧 bolt 不通 → WSL localhost 转发失效，
        # 冷重启重置网络栈（会中断该发行版内一切会话，含其他 WSL 工作负载）。
        _report(steps, "DO", "冷重启 WSL 重置 localhost 转发",
                "wsl --shutdown（中断 %s 内全部会话）" % distro)
        proc = _run(["wsl", "--shutdown"], timeout=60.0)
        if proc.returncode != 0:
            _report(steps, "FAIL", "wsl --shutdown", (proc.stderr or proc.stdout).strip())
            return steps, None
        time.sleep(5)
        # 受管会话占住 VM：等待与轮询期间没有活动会话时，VM 会被系统再次关闭。
        keeper = _spawn_keeper(distro, wait_seconds + linger_seconds + 90)
        _report(steps, "OK" if keeper else "WARN", "WSL 受管保活会话",
                "Popen sleep %.0f s（含 %.0f s 修复后窗口），到期自灭%s"
                % (wait_seconds + linger_seconds + 90, linger_seconds,
                   "" if keeper else "（启动失败，VM 可能再次关闭）"))
        # 留一个限时 nohup 兜底（到期自灭）：即使脚本被强杀也给 daemon 引导留窗口。
        _wsl_bash(distro, "nohup sleep %d >/dev/null 2>&1 & echo started" % WSL_KEEPALIVE_SECONDS,
                  timeout=60.0)

    _report(steps, "DO", "等待 bolt 就绪", "轮询上限 %.0f s" % wait_seconds)
    return steps, keeper


def main() -> int:
    parser = argparse.ArgumentParser(description="Neo4j 图谱服务检测与自愈")
    parser.add_argument("--check", action="store_true", help="只检测，不执行任何修复")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出结果")
    parser.add_argument("--wait", type=float, default=180.0,
                        help="修复后等待就绪的上限秒数（默认 180）")
    parser.add_argument("--linger", type=float, default=300.0,
                        help="修复成功后保活窗口秒数（默认 300；0 = 成功后立即回收会话）")
    parser.add_argument("--distro", default=DEFAULT_DISTRO, help="WSL 发行版名")
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help="Neo4j 容器名")
    args = parser.parse_args()

    steps: list = []
    result: dict = {"mode": "check" if args.check else "repair", "steps": steps}

    # ---- L1/L2：直接探测（可达即无需修复）----
    try:
        probe = _bolt_probe()
    except Exception as exc:                           # noqa: BLE001
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        probe = {"ok": False, "error": first}

    if probe.get("ok"):
        _report(steps, "OK", "bolt 可达", "%s；节点 %d，关系 %d"
                % (probe.get("uri", ""), probe["nodes"], probe["rels"]))
        nodes, rels = probe["nodes"], probe["rels"]
        if (nodes, rels) == (BASELINE_NODES, BASELINE_RELS):
            _report(steps, "OK", "计数与冻结基线一致", "%d/%d" % (nodes, rels))
        else:
            _report(steps, "WARN", "计数与冻结基线不符",
                    "实测 %d/%d，基线 %d/%d（图谱可能合法增减，请人工核对）"
                    % (nodes, rels, BASELINE_NODES, BASELINE_RELS))
            result["count_mismatch"] = True
        result["probe"] = {"ok": True, "nodes": nodes, "rels": rels}
        return _finish(result, 2 if result.get("count_mismatch") else 0, args.json)

    _report(steps, "FAIL", "bolt 可达性", probe.get("error", ""))
    if args.check:
        result["probe"] = {"ok": False, "error": probe.get("error", "")}
        return _finish(result, 1, args.json)

    # ---- 修复路径（keeper 为受管 WSL 会话：失败立即回收，成功保留 --linger 窗口）----
    keeper = None
    ok = False
    try:
        steps, keeper = repair(args.distro, args.container, args.wait, args.linger)
        if any(s["state"] == "FAIL" for s in steps):
            return _finish(result, 1, args.json)

        probe = _probe_with_retry(args.wait)
        if not probe.get("ok"):
            _report(steps, "FAIL", "修复后仍不可达", probe.get("error", ""))
            result["probe"] = {"ok": False}
            return _finish(result, 1, args.json)

        _report(steps, "OK", "修复后 bolt 可达",
                "节点 %d，关系 %d" % (probe["nodes"], probe["rels"]))
        result["probe"] = {"ok": True, "nodes": probe["nodes"], "rels": probe["rels"]}
        if (probe["nodes"], probe["rels"]) != (BASELINE_NODES, BASELINE_RELS):
            _report(steps, "WARN", "计数与冻结基线不符",
                    "实测 %d/%d，基线 %d/%d（请人工核对）"
                    % (probe["nodes"], probe["rels"], BASELINE_NODES, BASELINE_RELS))
            result["count_mismatch"] = True
            ok = True
            return _finish(result, 2, args.json)
        _report(steps, "OK", "计数与冻结基线一致",
                "%d/%d" % (probe["nodes"], probe["rels"]))
        ok = True
        return _finish(result, 0, args.json)
    finally:
        # 成功路径保留 keeper 自然到期（限时窗口，覆盖随后的测试/联调）；
        # 失败路径与 --linger 0 时立即回收。
        if keeper is not None and (not ok or args.linger <= 0):
            keeper.terminate()


def _finish(result: dict, code: int, as_json: bool) -> int:
    result["exit_code"] = code
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("结论：%s（退出码 %d）" % (
            {0: "图谱服务正常", 1: "图谱服务异常且未能自动恢复", 2: "图谱服务可达但计数需人工核对"}[code],
            code))
    return code


if __name__ == "__main__":
    sys.exit(main())
