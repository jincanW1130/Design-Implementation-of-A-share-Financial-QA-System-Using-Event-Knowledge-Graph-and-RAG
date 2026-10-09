# -*- coding: utf-8 -*-
"""第 0 组 · 测试自身的隔离机制（对"四个同名 `config.py` 串味"的正面与**负向**标定）。

本文件不测产品行为，测的是**本套测试的导入纪律**——它必须先过硬，否则 A～D 四组的读数
都可能是"另一份 config"给出来的：

* 四个同名模块：`代码\\检索\\config.py`／`代码\\问答\\config.py`／`代码\\数据准备\\config.py`／
  `代码\\抽取与图谱\\config.py`，各自内部一律写 `import config`（裸名）。
* 本套的做法（见 `_bootstrap.py`）：**按文件路径加载 ＋ 唯一模块名**，并在加载期把
  `sys.modules["config"]` 显式指向**本组件的 config 模块**，加载完原样恢复。

三条正面断言（各自的 config 就是各自那一份、互不相同、加载后不残留）＋
一条**负向断言**（隔离一旦失效，产品代码会立刻拒绝加载而不是悄悄换掉参数来源）。

顺带说明：`代码\\问答\\run_answer.py` 开头第 21～22 行 记载了这个陷阱，并因此对检索侧
一律走**子进程桥接**；本文件验证的是测试侧的同一条纪律。
"""

from __future__ import annotations

import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

RETRIEVAL_DIR = _bootstrap.COMPONENT_DIRS["检索"]
ANSWER_DIR = _bootstrap.COMPONENT_DIRS["问答"]
BACKEND_DIR = _bootstrap.COMPONENT_DIRS["后端"]

# 四组被测模块 → 它内部的 `import config` **必须**解析到哪一个目录
MODULES = [
    ("检索", "pipeline.py", RETRIEVAL_DIR),
    ("检索", "metrics.py", RETRIEVAL_DIR),
    ("问答", "assemble.py", ANSWER_DIR),
    ("问答", "prompt.py", ANSWER_DIR),
    ("问答", "rules.py", ANSWER_DIR),
    ("问答", "run_answer.py", ANSWER_DIR),
]


def test_four_same_named_configs_are_distinct_files():
    """四个同名 `config.py` 确实各在一处；本套只加载其中三个组件的那三份。"""
    paths = {}
    for component in ("检索", "问答", "后端"):
        module = _bootstrap.component_config(component)
        paths[component] = os.path.abspath(module.__file__)
        assert paths[component].endswith(os.path.join("代码", component, "config.py"))
    assert len(set(paths.values())) == 3, "三个组件的 config 必须是三个不同的文件"
    for component in ("数据准备", "抽取与图谱"):
        other = os.path.join(_bootstrap.CODE_DIR, component, "config.py")
        assert other not in paths.values()
    names = {_bootstrap.component_config(c).__name__ for c in ("检索", "问答", "后端")}
    assert len(names) == 3, "每个 config 的模块名也必须是唯一的（%s）" % sorted(names)


@pytest.mark.parametrize("component,filename,expected_dir", MODULES,
                         ids=["retrieval-pipeline", "retrieval-metrics",
                              "answer-assemble", "answer-prompt", "answer-rules",
                              "answer-run_answer"])
def test_product_module_is_bound_to_its_own_config(component, filename, expected_dir):
    module = _bootstrap.load_module(component, filename)
    bound = os.path.abspath(module.config.__file__)
    assert os.path.dirname(bound) == os.path.abspath(expected_dir), \
        "%s 里的 import config 解析到了 %s（串味）" % (filename, bound)


def test_backend_modules_are_bound_to_the_backend_config():
    errors = _bootstrap.load_backend("errors")
    qa_service = _bootstrap.load_backend("services.qa_service")
    assert os.path.dirname(os.path.abspath(errors.config.__file__)) == BACKEND_DIR
    assert os.path.dirname(os.path.abspath(qa_service.config.__file__)) == BACKEND_DIR
    assert qa_service.errors is errors, "同一份 errors 模块，不得出现两份实例"


def test_isolation_context_restores_sys_path_and_sys_modules():
    """隔离上下文退出后，`sys.path` 与 `sys.modules["config"]` 必须原样恢复。"""
    saved_path = list(sys.path)
    saved_config = sys.modules.get("config", None)
    with _bootstrap._Isolated("检索"):
        assert sys.modules["config"] is _bootstrap.component_config("检索")
        assert sys.path[0] == RETRIEVAL_DIR
    assert sys.path == saved_path
    assert sys.modules.get("config", None) is saved_config


def test_network_guard_is_armed():
    """**负向标定**：`conftest.forbid_network` 的审计钩子真的会拦下网络事件。

    没有这条用例，"本套测试离线"只是 README 里的一句话；有了它，守卫本身也被校准过
    （审计事件在真正发起调用之前抛出，因此这条用例不会产生任何真实网络流量）。
    """
    import socket
    with pytest.raises(RuntimeError, match="单元测试必须离线"):
        socket.getaddrinfo("example.com", 80)
    with pytest.raises(RuntimeError, match="单元测试必须离线"):
        socket.create_connection(("127.0.0.1", 9), timeout=0.01)


def test_pipeline_refuses_a_foreign_config():
    """**负向标定**：把 `sys.modules["config"]` 故意换成问答侧那一份，pipeline 必须拒绝加载。

    `pipeline.py` 第 107～108 行的守卫（"导入到的 config.py 不在本脚本同目录，拒绝继续"）
    正是这一串味的现场探测器。本用例证明"测试的隔离不是空话"：隔离一失效就会硬失败。
    """
    saved_path = list(sys.path)
    saved = sys.modules.get("config", None)
    sys.modules["config"] = _bootstrap.component_config("问答")
    try:
        with pytest.raises(SystemExit) as excinfo:
            _bootstrap._exec_by_path(
                "_dsh_negative_control_pipeline",
                os.path.join(RETRIEVAL_DIR, "pipeline.py"))
        assert "不在本脚本同目录" in str(excinfo.value)
    finally:
        sys.modules.pop("_dsh_negative_control_pipeline", None)
        sys.path[:] = saved_path
        if saved is None:
            sys.modules.pop("config", None)
        else:
            sys.modules["config"] = saved
