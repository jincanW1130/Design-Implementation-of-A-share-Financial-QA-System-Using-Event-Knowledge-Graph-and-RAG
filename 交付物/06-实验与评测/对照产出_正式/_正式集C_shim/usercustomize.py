# -*- coding: utf-8 -*-
"""第 10 阶段·正式对照：给 **C 组答案侧子进程**补一处只读内存注入（`config.TRACE_PATH`）。

背景（如实登记）
----------------
`代码\\问答\\run_answer.py` 第 516 行把 C 组**特例化**：C 组不走检索桥接，
改读 `代码\\问答\\config.py` 的 `TRACE_PATH`——那是第 7 阶段 **30 题预实验集**的冻结
trace（`交付物/05-系统实现/RAG检索系统\\检索产出\\per_question_trace.jsonl`）。正式题集的题号是
`FQ-*`，不在那份 30 行 trace 里，于是 120 题全部以
`error_code=1002 / reason="no_runnable_case"` 失败。

`工具\\跑正式对照.py` 已有「PYTHONPATH 前置一次性 shim」的只读内存注入机制
（`工具\\_正式对照_shim\\sitecustomize.py`）：检索侧注入 `QUESTION_FILES['questions']`，
答案侧注入 `QUESTIONS_PATH` 与 `identifiers_for()` 的 `FQ-<数字>` 解析。
本文件**照同一机制**再补一处：把答案侧的 `TRACE_PATH` 指向本次生成的
`对照产出_正式\\_正式集trace_C.jsonl`。

为什么不是直接改 `sitecustomize.py`
-----------------------------------
`工具\\跑正式对照.py` 的 `injected_questions()` 在 **spawn 每一题之前**都用它自己那份
`_SHIM_TEMPLATE` 重写 `工具\\_正式对照_shim\\sitecustomize.py`（模板写死在该脚本里，
第 395～508 行），所以对那份文件的手工扩展会在第一个子进程之前被覆盖掉；而除 shim 之外的
`工具\\` 脚本属"不得修改"范围。于是改走**同一机制的第二个标准启动钩子**：CPython 的
`site` 模块在 `execsitecustomize()` **之后**还会执行 `execusercustomize()`（即
`import usercustomize`），文件名不同、搜索路径同样来自 PYTHONPATH，因此不会被那次重写碰到，
且与 `sitecustomize.py` 的注入**叠加**而不是替换。

注入方式（可证伪）
------------------
* **开关**：环境变量 `STAGE10_FORMAL_C_TRACE` 既当开关、又当目标路径。
  它不存在 → 本文件什么都不做（"无钩子"分支）。
* **范围**：仅当本次进程的主脚本 basename 是 `run_answer.py` 时才动手。父进程
  `跑正式对照.py`、`run_query.py` 子进程、以及脚本自己用 `python -c` 起的探针
  （`load_answer_config_subprocess()` 等）都**不受影响**——它们读到的 `TRACE_PATH`
  仍是冻结值，报告里的"冻结配置"读数因此不会被本注入污染。
* **手段**：不复制任何逻辑。把**已被导入的** `sitecustomize`（＝跑正式对照.py 刚生成的
  那一份）里的 `_patch_answer()` 包一层：先调用原函数（正式题集路径 ＋ `FQ-` 解析照旧生效），
  再追加 `module.TRACE_PATH = <正式集 C 组 trace>`。
  `_ConfigPatchFinder.find_spec()` 是在**调用时**按模块全局名取 `_patch_answer`，
  所以这层包装对已安装的查找器立即生效。
* **对照实测**：`PYTHONPATH` 挂上本目录 → C 组读到 120 行正式 trace；
  不挂 → 仍读 30 行预实验 trace 并报 1002。两种情形都在交付报告里给了实测读数。

冻结区一个字节都不动：本文件不 import、不修改 `代码\\` 下任何模块，只在被 PYTHONPATH
挂上的**子进程内存里**改一个常量。
"""

import os as _os
import sys as _sys

#: 开关 ＋ 目标路径（同一个环境变量；未设置即整份文件不生效）
ENV_GATE = "STAGE10_FORMAL_C_TRACE"
#: 只在答案侧入口被 spawn 的那一层动手
GATE_ARGV0 = "run_answer.py"


def _enabled() -> bool:
    """是否注入：开关在 ＋ 主脚本是 `run_answer.py`。"""
    target = _os.environ.get(ENV_GATE)
    if not target:
        return False
    argv0 = ""
    argv = getattr(_sys, "argv", None)
    if argv:
        argv0 = str(argv[0] or "")
    return _os.path.basename(argv0.replace("\\", "/")).lower() == GATE_ARGV0


def _note(message: str) -> None:
    """注入痕迹只写 stderr（不写任何文件；父进程只截取 stderr 尾部，不会污染产出）。"""
    _sys.stderr.write("[阶段10 C 组 trace 注入] %s\n" % message)


def _install(formal_trace: str) -> str:
    """包装 sitecustomize 的 `_patch_answer`，追加 TRACE_PATH 一处。返回结果说明。"""
    try:
        import sitecustomize as _shim            # 跑正式对照.py 刚生成的那一份
    except Exception as exc:                      # noqa: BLE001
        return "未生效：找不到 sitecustomize（PYTHONPATH 是否前置了 工具\\_正式对照_shim？）：%r" % exc
    original = getattr(_shim, "_patch_answer", None)
    if original is None:
        return "未生效：sitecustomize 里没有 _patch_answer（模板变了吗？）"

    def _patch_answer(module):
        original(module)                          # 题集路径 ＋ FQ- 解析照旧
        _was = getattr(module, "TRACE_PATH", None)
        module.TRACE_PATH = formal_trace
        registry = getattr(module, "STAGE10_SHIM", None)
        if isinstance(registry, dict):            # 把这一处也登记进 self-report
            patched = registry.get("patched")
            if isinstance(patched, list):
                if "TRACE_PATH" not in patched:
                    patched.append("TRACE_PATH")
            elif isinstance(patched, str):
                registry["patched"] = [patched, "TRACE_PATH"]
            registry["trace_path_was"] = _was
            registry["trace_path_now"] = formal_trace
            registry["trace_path_by"] = (
                "交付物/06-实验与评测/对照产出_正式/_正式集C_shim/usercustomize.py")

    _patch_answer.__doc__ = ("usercustomize 包装版：先跑真 sitecustomize._patch_answer()，"
                             "再追加 config.TRACE_PATH → 正式集 C 组 trace。")
    _patch_answer.__wrapped__ = original
    _shim._patch_answer = _patch_answer
    return "已装载：答案侧 config.TRACE_PATH → %s" % formal_trace


if _enabled():
    _note(_install(_os.environ[ENV_GATE]))
