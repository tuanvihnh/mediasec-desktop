#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logging module for ToolDowMp4.
Provides persistent rotating file logs compliant with XDG Data Home (~/.local/share/tooldowmp4/app.log)
plus synchronized terminal console logging.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
from typing import Optional

_LOGGER: Optional[logging.Logger] = None


def get_data_dir() -> Path:
    """Trả về thư mục lưu dữ liệu ứng dụng theo chuẩn XDG Data Home."""
    xdg_data = os.environ.get("XDG_DATA_HOME")
    if xdg_data and os.path.isabs(xdg_data):
        base_dir = Path(xdg_data)
    else:
        base_dir = Path.home() / ".local" / "share"
    data_dir = base_dir / "tooldowmp4"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def get_log_file_path() -> Path:
    """Trả về đường dẫn tệp app.log."""
    return get_data_dir() / "app.log"


def setup_app_logger(level: int = logging.INFO) -> logging.Logger:
    """
    Khởi tạo và cấu hình Logger với RotatingFileHandler (tối đa 5MB, lưu 3 bản sao).
    """
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("tooldowmp4")
    logger.setLevel(level)
    logger.propagate = False

    # Định dạng log thống nhất
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(filename)s:%(lineno)d]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Rotating File Handler (Ghi vào ~/.local/share/tooldowmp4/app.log)
    try:
        log_file = get_log_file_path()
        file_handler = RotatingFileHandler(
            str(log_file),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as exc:
        print(f"[WARN] Không thể khởi tạo FileHandler cho app.log: {exc}")

    # 2. Console Handler (In ra terminal)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    _LOGGER = logger
    return logger


def get_logger() -> logging.Logger:
    """Lấy logger hiện hành hoặc tự động khởi tạo nếu chưa có."""
    global _LOGGER
    if _LOGGER is None:
        _LOGGER = setup_app_logger()
    return _LOGGER
