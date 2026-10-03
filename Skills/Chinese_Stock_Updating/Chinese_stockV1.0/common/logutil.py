#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一日志工具。

设计取舍：这套系统跑在 cron 里，调度方会从 stdout 抓内容（例如飞书卡片 JSON），
所以这里刻意**保持原有的输出格式** `[YYYY-MM-DD HH:MM:SS] 消息`，
只是把散落在各脚本里的 3 份 log()/log_error() 实现收拢到一处。

    log, log_error = make_log_functions(LOG_FILE)
    log("开始扫描")                 # -> stdout + 文件
    log_error("推送失败")           # -> stderr(带 traceback) + 文件
"""
from __future__ import annotations

import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable, Tuple


class FileLogger:
    """按 `[时间] 消息` 格式同时输出到控制台与日志文件的极简 logger。"""

    def __init__(self, log_file, echo: bool = True):
        self.log_file = Path(log_file)
        self.echo = echo

    def _write(self, line: str, stream) -> None:
        if self.echo:
            print(line, file=stream)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        self._write(line, sys.stdout)

    def error(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [ERROR] {msg}\n{traceback.format_exc()}"
        self._write(line, sys.stderr)


def make_log_functions(log_file, echo: bool = True) -> Tuple[Callable[[str], None], Callable[[str], None]]:
    """返回 (log, log_error) 两个函数，可直接替换脚本里的同名局部实现。"""
    logger = FileLogger(log_file, echo=echo)
    return logger.log, logger.error
