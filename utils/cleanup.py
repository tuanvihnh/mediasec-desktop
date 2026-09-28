#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garbage collection and stale artifact cleaner for ToolDowMp4.
Detects and cleans up orphaned .tmp_clean, .ytdl, and .part files older than a specified threshold.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Sequence

from utils.logger import get_logger


def cleanup_stale_artifacts(
    directories: Sequence[str | Path],
    max_age_hours: float = 24.0,
) -> int:
    """
    Quét và dọn dẹp các tệp tạm mồ côi (stale temporary files):
    - Tệp trung gian metadata: .tmp_clean
    - Tệp tạm cấu hình: cfg_*.tmp
    - Tệp tải dở dang mồ côi (.part, .ytdl) đã tồn tại lâu hơn max_age_hours.
    Trả về số lượng tệp đã được xóa an toàn.
    """
    logger = get_logger()
    cleaned_count = 0
    now = time.time()
    max_age_seconds = max_age_hours * 3600.0

    stale_extensions = {".tmp_clean"}
    partial_extensions = {".part", ".ytdl"}

    for d in directories:
        if not d:
            continue
        target_dir = Path(d).expanduser().resolve()
        if not target_dir.is_dir():
            continue

        try:
            for entry in target_dir.iterdir():
                if not entry.is_file():
                    continue

                filename = entry.name
                ext = entry.suffix.lower()

                should_delete = False

                # 1. Các tệp .tmp_clean từ xử lý metadata ảnh
                if ext in stale_extensions or filename.endswith(".tmp_clean"):
                    should_delete = True

                # 2. Các tệp cfg_*.tmp trong thư mục cấu hình
                elif filename.startswith("cfg_") and ext == ".tmp":
                    should_delete = True

                # 3. Các tệp .part/.ytdl mồ côi quá hạn (mất kết nối hoặc app bị kill đột ngột)
                elif ext in partial_extensions:
                    try:
                        mtime = entry.stat().st_mtime
                        if (now - mtime) > max_age_seconds:
                            should_delete = True
                    except OSError:
                        pass

                if should_delete:
                    try:
                        entry.unlink()
                        cleaned_count += 1
                        logger.info("Đã dọn dẹp tệp tạm mồ côi: %s", entry)
                    except OSError as err:
                        logger.warning("Không thể xóa tệp tạm %s: %s", entry, err)

        except Exception as exc:
            logger.debug("Lỗi khi quét thư mục %s: %s", target_dir, exc)

    return cleaned_count
