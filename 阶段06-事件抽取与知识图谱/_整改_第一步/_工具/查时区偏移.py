# -*- coding: utf-8 -*-
r"""F5 取证：a) 演示 now_iso 在非 +08:00 机器时区下的行为；b) 扫现行 v1.2 产物里
形如 `YYYY-MM-DDTHH:MM:SS±HH:MM` 的时间戳，报告 UTC 偏移不是 +08:00 的条目（只读）。

用法：python ...\查时区偏移.py
"""
import datetime as _dt
import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE
while not os.path.exists(os.path.join(ROOT, ".git")) and os.path.dirname(ROOT) != ROOT:
    ROOT = os.path.dirname(ROOT)

TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2})")
TREES = [
    os.path.join("代码", "抽取与图谱", "_全量", "v2.1_v1_2"),
    os.path.join("阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2"),
    os.path.join("阶段05-数据准备", "数据集", "_抽取缓存", "v2.1_v1_2"),
    os.path.join("阶段05-数据准备", "数据集", "抽取评测集", "v2.1"),
]


def old_now_iso():
    """改前的实现（审查 B 的缺陷 3）：机器本地时区。"""
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def new_now_iso():
    """改后的实现：固定 +08:00（与 run_all.py／write_graph.py 同一口径）。"""
    tz = _dt.timezone(_dt.timedelta(hours=8))
    return _dt.datetime.now(tz).isoformat(timespec="seconds")


def main():
    print("机器本地时区 = %s" % _dt.datetime.now().astimezone().tzinfo)
    print("改前 now_iso（astimezone）   = %s" % old_now_iso())
    print("改后 now_iso（固定 +08:00）  = %s" % new_now_iso())
    print("os.environ['TZ'] = %r（本脚本由 TZ=UTC 启动时可对比「异地」行为；Windows 下"
          "Python 的 astimezone 是否读 TZ 取决于 C 运行时，下面照实打印）"
          % os.environ.get("TZ"))
    bad, total, files = [], 0, 0
    for tree in TREES:
        tree_abs = os.path.join(ROOT, tree)
        for dirpath, _dirs, names in os.walk(tree_abs):
            for name in sorted(names):
                path = os.path.join(dirpath, name)
                files += 1
                try:
                    text = open(path, encoding="utf-8", errors="ignore").read()
                except OSError:
                    continue
                for m in TS.finditer(text):
                    total += 1
                    if m.group(1) != "+08:00":
                        bad.append("%s  %s" % (os.path.relpath(path, ROOT).replace("\\", "/"),
                                               m.group(0)))
    print("扫描 %d 个文件、%d 个时间戳；UTC 偏移不是 +08:00 的 %d 处" % (files, total, len(bad)))
    for row in bad[:20]:
        print("  !! %s" % row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
