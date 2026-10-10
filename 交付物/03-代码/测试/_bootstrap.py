# -*- coding: utf-8 -*-
"""代码\\测试\\_bootstrap.py —— 测试专用的**模块加载器**（避开四个同名 `config.py` 的串味）。

为什么需要它（先读懂再动手）
------------------------------
`代码\\检索\\config.py`、`代码\\问答\\config.py`、`代码\\数据准备\\config.py`、
`代码\\抽取与图谱\\config.py` 是**四个同名模块**；而这四个目录下的产品代码内部一律写
`import config`（裸名），靠"自己所在目录排在 `sys.path` 最前"解析到**自己那一份**。
`代码\\问答\\run_answer.py` 开头第 21～22 行**已记载**这个陷阱。

因此，"把多个组件目录一起插进 `sys.path`"的写法会让 `import config` 解析到哪一份**取决于
导入顺序与 `sys.modules` 的既存项**——这是能悄悄换掉参数来源的坑。本加载器的做法：

1. **按文件路径加载**（`importlib.util.spec_from_file_location`）＋给每个产品模块一个
   **唯一模块名**（`_dsh_<组件>_<文件名>`），不进 `sys.path` 的**裸名空间**；
2. 在 `exec_module` 的**整个期间**把 `sys.modules["config"]` 显式置为**本组件自己的
   `config` 模块**（该 config 也是按文件路径加载的，模块名 `_dsh_<组件>_config`），
   于是产品代码内部的 `import config` 必然命中本组件那一份；
3. 同时把本组件目录插到 `sys.path[0]`，让产品代码内部的**同目录**导入
   （`检索\\pipeline.py` 的 `from graph_query import …`、`问答\\assemble.py` 的
   `import prompt as prompt_mod`）命中本组件；
4. 加载结束后**原样恢复** `sys.path` 与 `sys.modules` 中被改动的那几个键。

这样，"同一进程里先加载检索、再加载问答"与"只加载其中一个"看到的是**同一份模块**，
不会因为运行顺序不同而串味——`代码\\测试\\README.md` 第一节 写了这条理由与实测防线。

第 4 条为什么成立：产品模块在**导入期**就把 `config` 绑到了自己的模块全局里（已确认全仓库
没有函数级的 `import config`），导入之后 `sys.modules["config"]` 是谁都不再影响它们。

用法（测试文件里）::

    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # 只为 import 到本文件
    import _bootstrap
    pipe = _bootstrap.load_module("检索", "pipeline.py")            # 代码\\检索\\pipeline.py
    errs = _bootstrap.load_backend("errors")                        # 代码\\后端\\errors.py

**本模块只读**：不写任何产品目录、不改任何产品文件；它只影响本测试进程的导入行为。
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))          # 交付物/03-代码\测试
CODE_DIR = os.path.dirname(_HERE)                           # 交付物/03-代码
ROOT = os.path.dirname(os.path.dirname(CODE_DIR))           # 仓库根（…\毕业设计）

# 被测组件目录。"数据准备"／"抽取与图谱" 是 P1-12 补测（E／F 组）新增：
# 它们与被覆盖的四组一样，各自有一份**同名** `config.py`，同样靠 `_Isolated` 隔离。
COMPONENT_DIRS = {
    "检索": os.path.join(CODE_DIR, "检索"),
    "问答": os.path.join(CODE_DIR, "问答"),
    "后端": os.path.join(CODE_DIR, "后端"),
    "数据准备": os.path.join(CODE_DIR, "数据准备"),
    "抽取与图谱": os.path.join(CODE_DIR, "抽取与图谱"),
}

# 恢复时要还原的 `sys.modules` 键（产品代码内部的裸名导入）
#
# 检索／问答按**文件路径**加载，只有裸名 `config` 需要在加载期被顶替，退出时还原。
# 后端按**常规模块名**导入（`errors`／`services.qa_service` 是它自己的包结构），
# 这些名字在另外两个组件里不存在同名模块，故**刻意留在 `sys.modules` 里不还原**——
# 还原会让 `services.qa_service` 里的 `import errors` 重新执行一次 `errors.py`，
# 于是同一个文件出现**两个模块实例**（`qa_service.errors is not errors`）。
# 仍然还原裸名 `config`：它是四个组件共用的名字，留着会污染后续加载。
_TOUCHED_KEYS = {
    "检索": ("config",),
    "问答": ("config",),
    "后端": ("config",),
    # 数据准备／抽取与图谱的产品代码内部一律 `import config`（裸名）；加载期顶替、退出还原。
    # 这两个目录下的产品模块之间是**同目录导入**（如 chunk.py 的 `import config`、
    # dedup.py 的 `from clean import …`），所以 `_Isolated` 同时把本组件目录插到 sys.path[0]。
    "数据准备": ("config",),
    "抽取与图谱": ("config",),
}

_MISSING = object()
_MODULE_CACHE: dict = {}
_CONFIG_CACHE: dict = {}


def _exec_by_path(module_name: str, path: str):
    """按**文件路径**执行一个模块，并给它一个**唯一模块名**（不占用裸名空间）。"""
    if not os.path.isfile(path):
        raise FileNotFoundError("被测模块不存在：%s" % path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:                 # pragma: no cover - 极罕见
        raise ImportError("无法按路径构造模块规格：%s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class _Isolated:
    """加载期间的隔离上下文：管住 `sys.modules["config"]` 与 `sys.path`。"""

    def __init__(self, component: str):
        if component not in COMPONENT_DIRS:
            raise KeyError("未知组件 %r（合法值 %s）" % (component, sorted(COMPONENT_DIRS)))
        self.component = component
        self.directory = COMPONENT_DIRS[component]

    def __enter__(self):
        # 先把本组件的 config 拿到手（这一步失败时还不该改动任何全局状态）
        cfg = component_config(self.component)
        self._saved_path = list(sys.path)
        self._saved = {}
        for key in _TOUCHED_KEYS[self.component]:
            self._saved[key] = sys.modules.get(key, _MISSING)
        # ① 本组件的 config 变成裸名 `config` 的唯一解析结果
        sys.modules["config"] = cfg
        # ② 本组件目录排在 sys.path 最前（产品代码内部的同目录导入靠它）
        sys.path.insert(0, self.directory)
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.path[:] = self._saved_path
        for key, value in self._saved.items():
            if value is _MISSING:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
        return False


def component_config(component: str):
    """该组件自己的 `config` 模块（按文件路径加载，模块名唯一；只加载一次）。"""
    if component not in _CONFIG_CACHE:
        path = os.path.join(COMPONENT_DIRS[component], "config.py")
        _CONFIG_CACHE[component] = _exec_by_path("_dsh_%s_config" % component, path)
    return _CONFIG_CACHE[component]


def load_module(component: str, filename: str):
    """加载 `代码\\<组件>\\<filename>`（唯一模块名；同一 (组件,文件名) 只执行一次）。

    返回模块对象。加载期内的 `import config` 一定解析到**本组件**的 `config`。
    """
    key = (component, filename)
    if key not in _MODULE_CACHE:
        name = "_dsh_%s_%s" % (component, os.path.splitext(filename)[0])
        with _Isolated(component):
            _MODULE_CACHE[key] = _exec_by_path(name, os.path.join(COMPONENT_DIRS[component],
                                                                  filename))
    return _MODULE_CACHE[key]


def load_backend(dotted: str):
    """加载 `代码\\后端\\<dotted>`（`后端` 是包目录：`errors`／`config`／`services.qa_service`）。

    **后端按常规模块名导入**（而不是按文件路径）：`api\\qa.py` 本身就是
    `import services.qa_service as qa_service`，且 `services\\` 下没有 `__init__.py`
    （命名空间包）。按同一个方式导入，`services.qa_service` 里的 `import db`／
    `import errors`／`import config` 才会命中**同一份**后端模块，不产生两份实例。
    """
    key = ("后端", dotted)
    if key not in _MODULE_CACHE:
        with _Isolated("后端"):
            _MODULE_CACHE[key] = importlib.import_module(dotted)
    return _MODULE_CACHE[key]


def dataset_path(component: str, attr: str) -> str:
    """取该组件 config 里的一个路径常量（不写死路径；缺失即抛错，不兜底）。"""
    cfg = component_config(component)
    if not hasattr(cfg, attr):
        raise AttributeError("%s 的 config 里没有 %s" % (component, attr))
    return getattr(cfg, attr)


def describe() -> dict:
    """自描述（README 与排障用）：本加载器认得的组件目录与根目录。"""
    return {"root": ROOT, "code_dir": CODE_DIR, "test_dir": _HERE,
            "components": dict(COMPONENT_DIRS)}
