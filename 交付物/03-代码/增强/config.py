# -*- coding: utf-8 -*-
"""代码\\增强\\config.py —— 增强层的**兼容配置入口**（不复制任何字面量）。

`增强/parse_text.py` 原本位于 `数据准备/`，内部写的是 `import config`（裸名），
依赖同目录的 `数据准备/config.py`（类别枚举等唯一参数来源）。移入增强层后，
本文件按**文件路径**加载 `数据准备/config.py` 并把其公开属性原样转发，
使 `parse_text.py` 的**内容一个字节都不用改**，同时不出现第二份参数取值。

纪律
----
* 只读：不写 `数据准备/`，只 import；
* 不复制：所有取值都来自 `数据准备/config.py`，缺失即导入失败（不兜底）；
* 仅工程增强层使用，不参与 A～E 实验口径。
"""

from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_DATA_PREP_CONFIG = os.path.join(os.path.dirname(_HERE), "数据准备", "config.py")

if not os.path.isfile(_DATA_PREP_CONFIG):
    raise ImportError("增强层依赖的上游配置不存在：%s" % _DATA_PREP_CONFIG)

_spec = importlib.util.spec_from_file_location(
    "_enhancement_data_prep_config", _DATA_PREP_CONFIG)
if _spec is None or _spec.loader is None:                 # pragma: no cover - 极罕见
    raise ImportError("无法按路径构造配置模块规格：%s" % _DATA_PREP_CONFIG)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

# 公开属性原样转发（不复制、不改写；私有名与模块对象本身不转发）
for _name in dir(_module):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_module, _name)
del _name

# 保留 stdout/stderr 的 UTF-8 切换（与上游 config 的导入期行为一致）
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
