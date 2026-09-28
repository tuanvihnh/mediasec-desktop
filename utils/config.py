#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration persistence module for ToolDowMp4.
Compliant with XDG Base Directory specification (~/.config/tooldowmp4/settings.json).
Provides atomic writes to avoid file corruption.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

# Default configuration settings
DEFAULT_CONFIG: dict[str, Any] = {
    "save_dir": "",
    "target": "YouTube",
    "media_mode": "video",
    "video_format": "mp4",
    "video_resolution": "1080p (Full HD - Khuyến nghị)",
    "audio_codec": "mp3",
    "audio_bitrate": "320 kbps (Chất lượng cao nhất)",
    "enable_subtitles": False,
    "subtitle_lang": "Tiếng Việt (vi - Dịch tự động)",
    "embed_subtitles": False,
    "enable_thumbnail": True,
    "embed_thumbnail": False,
    "img_transcode": "Gốc (Giữ nguyên định dạng gốc)",
    "img_res": "Gốc / Master (Original 100%)",
    "img_compress": "100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)",
    "img_frame_grabber": "Tắt (Giữ nguyên toàn bộ tệp)",
    "img_strip_exif": True,
    "img_palette_opt": True,
    "img_create_thumb": False,
    "img_hd_sharpness": True,
    "img_ai_upscale": False,
    "img_download_all": False,
    "cookie_browser": "None",
    "cookie_file": "",
    "clipboard_monitor": False,
    "auto_queue": False,
    "post_action": "Không làm gì (Mặc định)",
    "theme_mode": "dark",
}


def get_config_dir() -> Path:
    """Trả về thư mục cấu hình theo chuẩn XDG Base Directory."""
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config and os.path.isabs(xdg_config):
        base_dir = Path(xdg_config)
    else:
        base_dir = Path.home() / ".config"
    config_dir = base_dir / "tooldowmp4"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_file_path() -> Path:
    """Trả về đường dẫn tệp settings.json."""
    return get_config_dir() / "settings.json"


def load_config() -> dict[str, Any]:
    """
    Nạp cấu hình từ tệp settings.json.
    Tự động kết hợp với giá trị mặc định để đảm bảo không thiếu trường.
    """
    config = dict(DEFAULT_CONFIG)
    config_path = get_config_file_path()

    if not config_path.is_file():
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            user_data = json.load(f)
            if isinstance(user_data, dict):
                config.update(user_data)
    except Exception:
        # Nếu file hỏng, giữ nguyên giá trị mặc định an toàn
        pass

    return config


def save_config(config_data: dict[str, Any]) -> bool:
    """
    Lưu cấu hình ra đĩa an toàn theo cơ chế Atomic Write (ghi tệp tạm rồi đổi tên).
    """
    config_dir = get_config_dir()
    target_file = config_dir / "settings.json"

    # Hợp nhất với cấu hình mặc định để đảm bảo tính toàn vẹn
    final_data = dict(DEFAULT_CONFIG)
    final_data.update(config_data)

    try:
        # Ghi vào tệp tạm cùng thư mục để đảm bảo cùng filesystem khi đổi tên (atomic rename)
        fd, tmp_path = tempfile.mkstemp(dir=str(config_dir), prefix="cfg_", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(final_data, f, ensure_ascii=False, indent=2)

        # Đổi tên nguyên tử
        shutil.move(tmp_path, str(target_file))
        return True
    except Exception:
        if "tmp_path" in locals() and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return False
