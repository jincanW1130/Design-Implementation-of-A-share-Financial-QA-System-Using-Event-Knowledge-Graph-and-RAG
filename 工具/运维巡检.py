# -*- coding: utf-8 -*-
"""工具\\运维巡检.py —— 第 4 轮（11.3／11.4）资源巡检与日志轮转体检。

一次采集（默认单次；`--interval`／`--count` 可做轻量循环）：

* **磁盘**：仓库所在分区的已用／可用空间；
* **内存**：Windows 走 `GlobalMemoryStatusEx`，Linux 走 `/proc/meminfo`（无第三方依赖）；
* **CPU**：Windows 用两次 `GetSystemTimes` 采一个短窗口；其它平台读 `/proc/stat`；
* **端口**：MySQL 3306、Neo4j 7687、后端 8000、前端 5173 的 TCP 可达性；
* **健康**：`GET /api/health` 的 `status`、四项探针与 `metrics` 摘要（QPS／错误率／问答成功失败／限流命中）；
* **日志**：`config.LOG_PATH` 是否启用、当前文件大小、已有轮转文件数与上限
  （后端用 `RotatingFileHandler`：单文件 10 MiB、保留 5 个历史文件）。

`--strict`：健康不可达／degraded、磁盘可用 < 5 GiB 或内存可用 < 10% 时退出码 1，
可用于计划任务或人工值守；缺省只报告、退出码 0。**只读，不删日志、不清理文件。**

用法
----
    python 工具\\运维巡检.py                 # 单次体检
    python 工具\\运维巡检.py --strict        # 体检并在异常时返回 1
    python 工具\\运维巡检.py --interval 60 --count 10   # 每 60 秒一次，共 10 次
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import shutil
import socket
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(ROOT, "交付物", "03-代码", "后端")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

GIB = 1024.0 * 1024.0 * 1024.0


def _memory():
    try:
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
        return {"total": st.ullTotalPhys, "available": st.ullAvailPhys}
    except Exception:
        pass
    try:
        info = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0]) * 1024
        return {"total": info.get("MemTotal"), "available": info.get("MemAvailable")}
    except Exception:
        return None


def _cpu_percent():
    try:
        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", ctypes.c_ulong),
                        ("dwHighDateTime", ctypes.c_ulong)]

        def _ft(v):
            return (v.dwHighDateTime << 32) + v.dwLowDateTime

        idle1, kernel1, user1 = FILETIME(), FILETIME(), FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle1), ctypes.byref(kernel1), ctypes.byref(user1)):
            return None
        time.sleep(0.25)
        idle2, kernel2, user2 = FILETIME(), FILETIME(), FILETIME()
        if not ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle2), ctypes.byref(kernel2), ctypes.byref(user2)):
            return None
        idle = _ft(idle2) - _ft(idle1)
        total = (_ft(kernel2) - _ft(kernel1)) + (_ft(user2) - _ft(user1))
        return round(100.0 * (total - idle) / total, 1) if total > 0 else None
    except Exception:
        pass
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            fields = [int(x) for x in f.readline().split()[1:]]
        idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
        total = sum(fields)
        return round(100.0 * (total - idle) / total, 1) if total else None
    except Exception:
        return None


def _port_open(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.8)
        return sock.connect_ex(("127.0.0.1", port)) == 0
    finally:
        sock.close()


def _health(port: int):
    url = "http://127.0.0.1:%d/api/health" % port
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:                               # noqa: BLE001
        return {"_error": "%s: %s" % (type(exc).__name__, exc)}


def _log_status(config):
    log_path = getattr(config, "LOG_PATH", None)
    rotation = getattr(config, "LOG_ROTATION", {}) or {}
    if not log_path:
        return {"enabled": False,
                "info": "未配置 log_path：日志只出 stderr",
                "rejected": config.LOG_PATH_REJECTED}
    out = {"enabled": True, "path": log_path,
           "max_bytes": rotation.get("max_bytes"),
           "backup_count": rotation.get("backup_count"),
           "rotated": 0, "current_bytes": 0}
    if os.path.isfile(log_path):
        out["current_bytes"] = os.path.getsize(log_path)
    for i in range(1, int(rotation.get("backup_count") or 0) + 1):
        if os.path.isfile(log_path + ".%d" % i):
            out["rotated"] += 1
    return out


def one_tick(config, strict: bool) -> bool:
    problems = []
    print("-" * 78)
    print("巡检时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("-" * 78)

    usage = shutil.disk_usage(ROOT)
    free_ratio = usage.free / usage.total if usage.total else 0.0
    print("  磁盘：总 %.1f GB／可用 %.1f GB（%.1f%%）"
          % (usage.total / GIB, usage.free / GIB, 100.0 * free_ratio))
    if usage.free < 5 * GIB or free_ratio < 0.10:
        problems.append("磁盘可用不足")

    mem = _memory()
    if mem and mem.get("total"):
        ratio = mem["available"] / mem["total"]
        print("  内存：总 %.1f GB／可用 %.1f GB（%.1f%%）"
              % (mem["total"] / GIB, mem["available"] / GIB, 100.0 * ratio))
        if ratio < 0.10:
            problems.append("内存可用不足 10%")
    else:
        print("  内存：读取失败（跳过）")

    cpu = _cpu_percent()
    print("  CPU ：%s" % ("%.1f%%（0.25s 采样）" % cpu if cpu is not None else "读取失败（跳过）"))

    ports = [("MySQL", 3306), ("Neo4j", 7687),
             ("后端", getattr(config, "BACKEND_PORT", 8000)),
             ("前端", getattr(config, "FRONTEND_PORT", 5173))]
    state = []
    for name, port in ports:
        ok = _port_open(port)
        state.append("%s:%d=%s" % (name, port, "通" if ok else "断"))
        if not ok and name in ("MySQL", "Neo4j"):
            problems.append("%s 端口 %d 不可达" % (name, port))
    print("  端口：%s" % "，".join(state))

    health = _health(getattr(config, "BACKEND_PORT", 8000))
    if "_error" in health:
        print("  健康：不可达（%s）" % health["_error"])
        problems.append("后端 /api/health 不可达")
    else:
        probes = {k: health.get(k, {}).get("ok") for k in
                  ("mysql", "neo4j", "vector_index", "model_config")}
        print("  健康：status=%s；探针 %s"
              % (health.get("status"), json.dumps(probes, ensure_ascii=False)))
        metrics = health.get("metrics") or {}
        req = metrics.get("requests") or {}
        qa = metrics.get("qa") or {}
        print("  指标：QPS=%.2f，窗口错误率=%.2f%%，问答成功=%s／失败=%s，限流命中=%s"
              % (req.get("qps", 0.0), 100.0 * req.get("error_rate", 0.0),
                 qa.get("success", 0), qa.get("failure", 0),
                 (metrics.get("rate_limit") or {}).get("hits", 0)))
        if health.get("status") != "ok":
            problems.append("健康状态非 ok")

    log = _log_status(config)
    if not log.get("enabled"):
        print("  日志：%s" % log.get("info"))
        if log.get("rejected"):
            print("        提示：log_path 被拒绝 %s" % log["rejected"])
    else:
        pct = (100.0 * log["current_bytes"] / log["max_bytes"]
               if log.get("max_bytes") else 0.0)
        print("  日志：%s（%.2f MB，占单文件上限 %.0f%%；已有轮转文件 %d／%s）"
              % (log["path"], log["current_bytes"] / 1024.0 / 1024.0, pct,
                 log["rotated"], log.get("backup_count")))
        if pct >= 90:
            print("        提示：接近 10 MiB 轮转阈值，下一次写入即轮转（属正常机制）")

    if problems:
        print("  异常：%s" % "；".join(problems))
    else:
        print("  异常：无")
    return not problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="资源巡检与日志轮转体检（只读）")
    ap.add_argument("--interval", type=int, default=0, help="循环间隔秒数（默认 0＝单次）")
    ap.add_argument("--count", type=int, default=1, help="循环次数（默认 1）")
    ap.add_argument("--strict", action="store_true", help="发现异常时退出码 1")
    args = ap.parse_args(argv)

    try:
        import config
    except SystemExit as exc:
        print("[FAIL] 后端配置不可加载：%s" % str(exc).splitlines()[0])
        return 1

    print("=" * 78)
    print("运维巡检（只读）")
    print("=" * 78)
    failures = 0
    for index in range(max(1, args.count)):
        if index and args.interval > 0:
            time.sleep(args.interval)
        ok = one_tick(config, args.strict)
        if not ok:
            failures += 1
    print("=" * 78)
    print("巡检完成：%d 次，异常 %d 次" % (max(1, args.count), failures))
    if args.strict and failures:
        print("严格模式：退出码 1。")
        return 1
    print("退出码 0。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
