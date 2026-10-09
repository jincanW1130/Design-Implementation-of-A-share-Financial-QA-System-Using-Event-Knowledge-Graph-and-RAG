# -*- coding: utf-8 -*-
"""B-25 正对照：在系统临时目录里造一个**合成工作区**，逐类验证整改后的 K 组是否仍有牙：

  ① 真悬空（含 `.json`／`.jsonl`／`.txt`／`.cypher` 四种新白名单扩展名）→ 必须判 FAIL；
  ② 通配写法匹配不到任何文件 → 必须判 FAIL；
  ③ 深路径（`数据集\\v2.1\\chunks\\chunks.jsonl` 这类三层路径）真实存在 → 必须判 OK；
  ④ 占位符／缩略／工作区外写法 → 不判悬空（逐条列出）。

合成工作区落在 %TEMP% 下，工作区本身只读。用法：
    python 交付物/05-系统实现/RAG检索系统\\_审查工作底稿\\_第二轮整改\\b25_正对照.py
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
except Exception:                                            # noqa: BLE001
    pass

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
TOOL = os.path.join(ROOT, "工具", "跨文档核验.py")

DOC = """# 合成工作区（B-25 正对照）

依据《02-项目执行总控文档.md》（合成：本文件不存在，用于让 N2 只报告）。

## 一、样本

* 真悬空（新白名单扩展名）：`检索产出\\不存在的产物.json`、`检索产出\\不存在的明细.jsonl`、
  `检索产出\\不存在的说明.txt`、`检索产出\\不存在的脚本.cypher`。
* 通配写法无命中：`不存在的前缀_*.jsonl`。
* 深路径真存在：`交付物/04-数据与知识图谱/数据准备\\数据集\\v2.1\\chunks\\chunks.jsonl`。
* 裸文件名真存在：`chunks.jsonl`。
* 缩略写法：`...\\raw\\gate_x.txt`。
* 占位符写法：`raw\\{doc_id}.json`。
* 工作区外写法：`%TEMP%\\stage7audit\\01_x.txt`。
"""


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="b25_ctrl_")
    try:
        os.makedirs(os.path.join(tmp, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "chunks"))
        with open(os.path.join(tmp, "交付物/04-数据与知识图谱/数据准备", "数据集", "v2.1", "chunks", "chunks.jsonl"),
                  "w", encoding="utf-8", newline="\n") as f:
            f.write('{"chunk_id": 1}\n')
        os.makedirs(os.path.join(tmp, "交付物/05-系统实现/RAG检索系统"))
        with open(os.path.join(tmp, "交付物/05-系统实现/RAG检索系统", "99-合成样本.md"),
                  "w", encoding="utf-8", newline="\n") as f:
            f.write(DOC)
        proc = subprocess.run([sys.executable, TOOL, tmp], cwd=ROOT, capture_output=True,
                              text=True, encoding="utf-8", errors="replace")
        out = proc.stdout or ""
        lines = out.split("\n")
        try:
            start = next(i for i, l in enumerate(lines) if l.startswith("K 文档内提到的文件路径是否存在"))
        except StopIteration:
            start = 0
        print("=" * 78)
        print("B-25 正对照（合成工作区 %s）" % tmp)
        print("=" * 78)
        print("\n".join(lines[start:start + 30]))
        print("-" * 78)
        print("退出码=%d（期望 1：① 与 ② 必须判悬空）" % proc.returncode)
        checks = {
            "① 真悬空 .json 被抓住": "不存在的产物.json" in out,
            "① 真悬空 .jsonl 被抓住": "不存在的明细.jsonl" in out,
            "① 真悬空 .txt 被抓住": "不存在的说明.txt" in out,
            "① 真悬空 .cypher 被抓住": "不存在的脚本.cypher" in out,
            "② 通配无命中被抓住": "通配写法，匹配不到任何文件" in out,
            "③ 深路径判存在（未进悬空清单）": "交付物/04-数据与知识图谱/数据准备\\数据集\\v2.1\\chunks\\chunks.jsonl" not in out,
            "③ 裸文件名判存在": "  提到  chunks.jsonl" not in out,
            "④ 缩略写法不进悬空": "  提到  ...\\raw\\gate_x.txt" not in out,
            "④ 占位符写法不进悬空": "  提到  raw\\{doc_id}.json" not in out,
            "④ 工作区外写法不进悬空": "  提到  %TEMP%\\stage7audit\\01_x.txt" not in out,
            "退出码为 1（K 组仍有牙）": proc.returncode == 1,
        }
        for k, v in checks.items():
            print("  [%s] %s" % ("OK  " if v else "FAIL", k))
        return 0 if all(checks.values()) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
