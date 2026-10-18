# -*- coding: utf-8 -*-
"""M 组 · 日志落盘与轮转（第二轮第 9 轮：11.4 的可验证落地）。

覆盖三件事（全部离线、只写 `tmp_path`，不碰真实日志路径）：

1. **不设 `LOG_PATH` 时行为完全不变**：`errors.setup_logging()` 只挂一个
   `StreamHandler(stderr)`，**一个文件 handler 都不挂**、不创建任何文件；
2. **设了 `LOG_PATH` 就写文件**：额外挂 `RotatingFileHandler`，目录不存在会自动创建，
   `maxBytes`／`backupCount` 取自 `config.LOG_ROTATION`；
3. **轮转生效**：把 `max_bytes` 调小后连续写日志，出现 `backend.log.1`／`.2`，
   且历史文件数不超过 `backup_count`（不会无限增长）。

每个用例结束都恢复全局 logging 状态与 `config.LOG_PATH`／`LOG_ROTATION`，
避免污染同进程内其它测试（pytest 与 uvicorn 的日志配置不受影响）。
"""

from __future__ import annotations

import glob
import logging
import logging.handlers
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import _bootstrap  # noqa: E402

config_mod = _bootstrap.load_backend("config")
errors_mod = _bootstrap.load_backend("errors")

_ROOT_NAME = "ashare_qa"


def _root_logger() -> logging.Logger:
    return logging.getLogger(_ROOT_NAME)


def _file_handlers() -> list:
    return [h for h in _root_logger().handlers if isinstance(h, logging.FileHandler)]


def _emit(*messages: str) -> None:
    """写几条日志并 flush（`RotatingFileHandler(delay=True)` 在首条日志时才建文件）。"""
    log = logging.getLogger("ashare_qa.test")
    for message in messages:
        log.info(message)
    for handler in _root_logger().handlers:
        handler.flush()


@pytest.fixture(autouse=True)
def _restore_logging_state():
    """保存／恢复 `ashare_qa` logger 与 config 的日志参数（用例之间互不串状态）。"""
    root = _root_logger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_propagate = root.propagate
    saved_path = getattr(config_mod, "LOG_PATH", None)
    saved_rotation = dict(getattr(config_mod, "LOG_ROTATION", {}) or {})
    try:
        yield
    finally:
        for handler in root.handlers:
            if handler not in saved_handlers:
                try:
                    handler.close()
                except Exception:
                    pass
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        root.propagate = saved_propagate
        config_mod.LOG_PATH = saved_path
        config_mod.LOG_ROTATION.clear()
        config_mod.LOG_ROTATION.update(saved_rotation)


def test_without_log_path_only_stderr(tmp_path):
    """未配置路径：只出 stderr，不挂 FileHandler，也不创建文件。"""
    config_mod.LOG_PATH = None
    errors_mod.setup_logging()

    handlers = _root_logger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0], logging.StreamHandler)
    assert not isinstance(handlers[0], logging.FileHandler)
    assert handlers[0].stream is sys.stderr
    assert _file_handlers() == []
    # 目录里不应凭空多出任何日志文件
    assert list(tmp_path.iterdir()) == []


def test_log_path_writes_file_and_creates_directory(tmp_path):
    """配置路径：文件被真实写入（中文 UTF-8），目录自动创建，轮转参数取自 config。"""
    log_path = tmp_path / "nested" / "logs" / "backend.log"
    assert not log_path.parent.exists()

    config_mod.LOG_PATH = str(log_path)
    config_mod.LOG_ROTATION.update(
        {"max_bytes": 10 * 1024 * 1024, "backup_count": 5, "encoding": "utf-8"})
    errors_mod.setup_logging()

    _emit("落盘验证：中文日志一号", "落盘验证：中文日志二号")

    assert log_path.is_file()
    text = log_path.read_text(encoding="utf-8")
    assert "落盘验证：中文日志一号" in text
    assert "落盘验证：中文日志二号" in text

    file_handlers = _file_handlers()
    assert len(file_handlers) == 1
    assert isinstance(file_handlers[0], logging.handlers.RotatingFileHandler)
    assert file_handlers[0].maxBytes == 10 * 1024 * 1024
    assert file_handlers[0].backupCount == 5
    # stderr handler 始终保留（容器形态靠 stdout／stderr 采集）
    stream_handlers = [h for h in _root_logger().handlers
                       if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, logging.FileHandler)]
    assert len(stream_handlers) == 1


def test_rotating_file_handler_rotates_and_caps_backups(tmp_path):
    """轮转生效：超过 max_bytes 后出现 .1／.2，且历史文件数不超过 backup_count。"""
    log_path = tmp_path / "backend.log"
    config_mod.LOG_PATH = str(log_path)
    config_mod.LOG_ROTATION.update(
        {"max_bytes": 512, "backup_count": 2, "encoding": "utf-8"})
    errors_mod.setup_logging()

    _emit(*["轮转压力行 %02d " % i + "X" * 80 for i in range(40)])

    assert log_path.is_file()
    backups = sorted(glob.glob(str(log_path) + ".*"))
    assert backups, "写入量已超过 max_bytes，但没有发生轮转"
    assert len(backups) <= 2, "历史文件数超过 backup_count：%s" % backups
    assert not os.path.exists(str(log_path) + ".3")
    # 轮转后当前文件仍在，且可继续读（未被轮转逻辑截断为空壳之外）
    assert log_path.stat().st_size > 0


def test_unwritable_log_path_keeps_service_alive(tmp_path):
    """路径不可用（父路径是普通文件）时：只记 WARNING、不挂文件 handler、不抛异常。"""
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    config_mod.LOG_PATH = str(blocker / "backend.log")   # makedirs 会因父路径是文件而失败
    errors_mod.setup_logging()

    assert _file_handlers() == []
    stream_handlers = [h for h in _root_logger().handlers
                       if isinstance(h, logging.StreamHandler)
                       and not isinstance(h, logging.FileHandler)]
    assert len(stream_handlers) == 1
