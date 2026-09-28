# -*- coding: utf-8 -*-
"""对抗实验：C 组（输入只读）是否自指。

步骤（全部在 re7_B/mirror 内，工作区只读）：
  1. 记下镜像 input_manifest.json 与某输入文件的 SHA-256；
  2. 改动该输入文件的**一个字节**（追加一个空格）；
  3. 在镜像里重跑 check_inputs.py（= 门禁镜像重跑的第一步）；
  4. 用门禁 C2 的**同一段逻辑**（重算 11 个输入的 sha256 与字节数，与清单比对）判定。
预期：第 3 步把清单重写成了"改动后"的指纹，故第 4 步仍然全对 —— 即 C2 证明不了
"与 T1 开工指纹一致"。另附：同一逻辑若拿**改动前**的清单来比对，会报不一致（正对照）。
"""
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys

MIR = r"C:\Users\15129\AppData\Local\Temp\re7_B\mirror"
CODE = os.path.join(MIR, "代码", "检索")
MANIFEST = os.path.join(MIR, "阶段07-RAG检索系统", "检索产出", "input_manifest.json")
TARGET = os.path.join(MIR, "阶段06-事件抽取与知识图谱", "图谱导出", "v2.1_v1_2",
                      "graph_stats.json")


def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def c2_logic(manifest_path, root):
    """门禁 C 组的判定逻辑（简化）：逐条重算 sha256 与字节数，与清单记录比对。"""
    man = json.load(io.open(manifest_path, encoding="utf-8"))
    bad = []
    for row in man.get("files") or []:
        p = os.path.join(root, row["path"].replace("/", os.sep))
        if not os.path.isfile(p) or sha(p) != row["sha256"] \
                or os.path.getsize(p) != row["bytes"]:
            bad.append(row["key"])
    return bad, man.get("all_ok")


print("TARGET =", TARGET)
print("改动前 target sha256 =", sha(TARGET))
print("改动前 manifest[graph_stats] =",
      next(r["sha256"] for r in json.load(io.open(MANIFEST, encoding="utf-8"))["files"]
           if r["key"] == "graph_stats"))

# 保留一份"改动前的清单"作为正对照
shutil.copy2(MANIFEST, MANIFEST + ".before")

# 正对照：改动输入但**不**重跑 check_inputs，直接用旧清单比对
with open(TARGET, "ab") as fh:
    fh.write(b" ")          # 追加一个空格，字节数 +1、sha256 必变
bad, allok = c2_logic(MANIFEST + ".before", MIR)
print("\n[正对照] 用**改动前**的清单比对改动后的输入 -> 不一致=%r（应非空）" % (bad,))
print("         all_ok(清单自称)=%r" % (allok,))

# 实验组：重跑 check_inputs.py（门禁镜像重跑的第一步），它会把清单重写成"改动后"的指纹
print("\n[实验组] 在镜像里重跑 check_inputs.py ...")
proc = subprocess.run([sys.executable, os.path.join(CODE, "check_inputs.py")],
                      cwd=MIR, capture_output=True, text=True,
                      encoding="utf-8", errors="replace",
                      env={**os.environ, "PYTHONIOENCODING": "utf-8",
                           "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
print("  exit_code =", proc.returncode)
tail = (proc.stdout or "").strip().split("\n")
print("  stdout 末 3 行:", tail[-3:])

print("  重跑后 target sha256 =", sha(TARGET))
print("  重跑后 manifest[graph_stats] =",
      next(r["sha256"] for r in json.load(io.open(MANIFEST, encoding="utf-8"))["files"]
           if r["key"] == "graph_stats"))
bad2, allok2 = c2_logic(MANIFEST, MIR)
print("  用**重跑后**的清单比对 -> 不一致=%r（应为空）" % (bad2,))
print("  all_ok=%r" % (allok2,))
print("\n结论：改动输入后重跑 check_inputs.py，C2 式比对仍然全对 —— C2 是自指的。")
print("目标文件已被改动：", TARGET)
