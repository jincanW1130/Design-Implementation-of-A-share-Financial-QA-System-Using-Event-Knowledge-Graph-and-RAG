# -*- coding: utf-8 -*-
"""代码\\后端\\run.py —— 第 9 阶段后端服务的**启动入口**（uvicorn）。

用法
----
    python 代码\\后端\\run.py                # 开发/演示：单进程，不开热重载
    python 代码\\后端\\run.py --reload       # 开发期热重载（**只在开发期用**）
    python 代码\\后端\\run.py --port 8001    # 临时改端口（默认取 config.local.json）

三条固定口径
------------
* **主机默认 `127.0.0.1`**（《24》第七节 T4）：第一版是单机演示，本机形态下**不对外监听**。
  `--host` 开关是**为容器形态加的**（容器内必须监听 `0.0.0.0` 才能被宿主访问）——默认值不变，
  对外暴露与否由调用方显式决定。**该开关的由来**：`部署\\Dockerfile` 的 CMD 写了
  `--host 0.0.0.0`，而早期版本的 argparse 不认它，容器一起就以 `Exited (2)` 退出
  （`unrecognized arguments: --host 0.0.0.0`）——由第 9 阶段门禁 H3 实测抓出后补上。
* **端口取自 `config.local.json`**（`config.BACKEND_PORT`），脚本里不写死 8000。
* **`--reload` 只在开发期用**：热重载会常驻一个监视进程，实验运行与交付演示一律不带它
  （《24》的实验运行纪律）。开启时只监视 `代码\\后端` 目录。

日志
----
`uvicorn` 的日志与后端自身的日志（`errors.setup_logging()`，stderr、UTF-8）分开：
前者是访问日志，后者是应用日志（`detail` 与未捕获异常堆栈只落后者）。
"""

from __future__ import annotations

import argparse
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# 控制台默认 GBK：先切 UTF-8，再让 uvicorn／config 打印中文（否则报错信息会乱码）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

import config  # noqa: E402

HOST = "127.0.0.1"          # 本机形态的默认监听地址：不对外监听


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="第 9 阶段后端服务启动入口（uvicorn）")
    parser.add_argument("--reload", action="store_true",
                        help="开发期热重载（只在开发期用；实验运行与演示不要带）")
    parser.add_argument("--port", type=int, default=None,
                        help="临时覆盖端口（默认取 config.local.json 的 backend_port）")
    # `--host` 是**容器形态**必需的：容器里必须监听 0.0.0.0 才能被宿主访问，
    # 而本机形态的默认值仍是 127.0.0.1（对外暴露与否由调用方显式决定）。
    # 加这个开关的起因：`交付物/10-部署\Dockerfile` 的 CMD 写了 `--host 0.0.0.0`，而早期版本的
    # argparse 不认这个参数 —— 容器一起就以 `Exited (2)` 退出、日志报
    # `unrecognized arguments: --host 0.0.0.0`（由第 9 阶段门禁 H3 实测抓出）。
    parser.add_argument("--host", default=HOST,
                        help="监听地址（默认 127.0.0.1；容器形态用 0.0.0.0）")
    parser.add_argument("--log-level", default="info",
                        choices=["critical", "error", "warning", "info", "debug", "trace"])
    args = parser.parse_args(argv)

    port = int(args.port if args.port is not None else config.BACKEND_PORT)
    host = str(args.host or HOST)

    # 切到 交付物/03-代码\后端：uvicorn 用 import 字符串加载应用（"main:app"），
    # 热重载会在子进程里重新解析它，把工作目录钉在这里最稳（config 内全是绝对路径）。
    os.chdir(BACKEND_DIR)

    print("=" * 74)
    print("启动 A 股财经文本问答系统 · 第 9 阶段后端（前后端系统集成）")
    print("=" * 74)
    print("  监听地址   = http://%s:%d" % (host, port))
    print("  就绪探针   = http://%s:%d/api/health" % (host, port))
    print("  接口文档   = http://%s:%d/docs" % (host, port))
    print("  允许来源   = %s" % "、".join(config.CORS_ORIGINS))
    print("  热重载     = %s" % ("开（开发期）" if args.reload else "关"))
    print("  定值       = K=%s N=%s 预算=%s g=%s 模型=%s Prompt=%s"
          % (config.K, config.N, config.CONTEXT_TOKEN_BUDGET, config.G,
             config.ANSWER_MODEL, config.PROMPT_VERSION))
    print("=" * 74)

    import uvicorn
    uvicorn.run("main:app", host=host, port=port, reload=bool(args.reload),
                reload_dirs=[BACKEND_DIR] if args.reload else None,
                log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
