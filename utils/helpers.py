#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
General Helper Functions (Time formatting, Byte formatting, Thumbnails, Shell-safe execution).
"""

from __future__ import annotations

import io
import re
import sys
import subprocess
from pathlib import Path
from typing import Optional
import urllib.request
import urllib.parse
import urllib.error

# PIL/Pillow check
try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from utils.constants import SAFE_EXTENSIONS


def log_info(msg: str) -> None:
    print(f"[INFO] {msg}", file=sys.stdout)


def log_warn(msg: str) -> None:
    print(f"[WARN] {msg}", file=sys.stderr)


def log_err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)


def format_duration(seconds: Optional[float | int]) -> str:
    """Định dạng số giây thành chuỗi thời lượng trực quan mm:ss hoặc hh:mm:ss."""
    if not seconds or seconds <= 0:
        return "Không rõ"
    sec = int(seconds)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def parse_time_to_seconds(time_str: Optional[str]) -> Optional[float]:
    """
    Chuyển đổi chuỗi thời gian người dùng nhập thành số giây (float).
    Hỗ trợ các định dạng:
    - "SS" hoặc "SSs" / "SSsec" (ví dụ: "45", "45s", "90.5")
    - "MM:SS" (ví dụ: "01:30" -> 90.0, "0:04" -> 4.0)
    - "MM.SS" khi người dùng nhập dấu chấm thay vì hai chấm (ví dụ: "0.01" -> 1.0, "0.04" -> 4.0, "1.30" -> 90.0)
    - "HH:MM:SS" (ví dụ: "01:15:30" -> 4530.0)
    - "HH:MM:SS.mmm" (ví dụ: "00:01:30.500" -> 90.5)
    Trả về số giây hoặc None nếu không hợp lệ hoặc để trống.
    """
    if not time_str or not isinstance(time_str, str):
        return None
    s = time_str.strip()
    if not s:
        return None

    # Hỗ trợ bỏ hậu tố 's' hoặc 'sec' nếu người dùng nhập ví dụ '45s', '90sec'
    s = re.sub(r"(?i)\s*(?:sec|s)$", "", s).strip()
    s = s.replace(",", ".")

    # 1. Định dạng có dấu hai chấm (HH:MM:SS hoặc MM:SS hoặc MM:SS.xxx)
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return max(0.0, float(parts[0]) * 60 + float(parts[1]))
            elif len(parts) == 3:
                return max(0.0, float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2]))
        except ValueError:
            return None

    # 2. Định dạng MM.SS (người dùng nhập số phút.giây dùng dấu chấm thay vì hai chấm)
    # Ví dụ: "0.01" -> 1s, "0.04" -> 4s, "1.30" -> 90s, "01.45" -> 105s
    m_dot = re.match(r"^(\d+)\.([0-5]\d)$", s)
    if m_dot:
        m_val = int(m_dot.group(1))
        s_val = int(m_dot.group(2))
        return max(0.0, float(m_val * 60 + s_val))

    # 3. Số giây thuần túy (nguyên hoặc thập phân: "45", "90.5", "0.5")
    try:
        val = float(s)
        return max(0.0, val)
    except ValueError:
        return None


def format_bytes(bytes_count: Optional[float | int]) -> str:
    """Định dạng dung lượng bytes sang KB, MB, GB."""
    if not bytes_count or bytes_count <= 0:
        return ""
    b = float(bytes_count)
    for unit in ["B", "KB", "MB", "GB"]:
        if b < 1024.0:
            return f"{b:.1f} {unit}"
        b /= 1024.0
    return f"{b:.1f} TB"


def clean_ansi_escape(text: str) -> str:
    """Loại bỏ các ký tự mã màu ANSI escape sequences (như \x1b[0;31m)."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = re.sub(r"\x1b\[[0-9;]*m", "", text)
    cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", cleaned)
    return cleaned.strip()


def create_placeholder_thumbnail(
    size: tuple[int, int] = (160, 90),
    text: str = "No Thumbnail",
    bg_color: str = "#242424",
    fg_color: str = "#888888",
) -> Optional[Image.Image]:
    """Tạo ảnh placeholder cố định 160x90 px khi không có thumbnail hoặc tải lỗi."""
    if not HAS_PIL:
        return None
    try:
        img = Image.new("RGB", size, color=bg_color)
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, size[0] - 1, size[1] - 1], outline="#3e3e3e", width=1)
        font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x = (size[0] - tw) // 2
        y = (size[1] - th) // 2
        draw.text((x, y), text, fill=fg_color, font=font)
        return img
    except Exception:
        return None


def load_thumbnail_pil(
    thumbnail_url: str,
    size: tuple[int, int] = (160, 90),
) -> Optional[Image.Image]:
    """
    Tải và resize ảnh thumbnail bằng PIL/Pillow thành đối tượng Image.Image
    với kích thước cố định khoảng 160x90 px (canh giữa trên nền tối).
    """
    if not HAS_PIL or not thumbnail_url:
        return None
    try:
        req = urllib.request.Request(
            thumbnail_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = resp.read()

        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")

        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        img.thumbnail(size, resample_filter)

        bg = Image.new("RGB", size, (25, 25, 25))
        offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
        bg.paste(img, offset)
        return bg
    except Exception:
        return None


def load_thumbnail_png_bytes(thumbnail_url: str, size: tuple[int, int] = (160, 90)) -> Optional[bytes]:
    """Tương thích ngược: tải và trả về PNG bytes."""
    img = load_thumbnail_pil(thumbnail_url, size)
    if not img:
        return None
    try:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


def safe_open_path(path: str, open_file: bool = False) -> bool:
    """
    Mở thư mục hoặc file bằng xdg-open trên Linux.

    BẢO MẬT:
    - Dùng subprocess.Popen với shell=False (KHÔNG shell injection)
    - Validate path tồn tại trước khi mở
    - Chỉ cho phép mở file với extension nằm trong SAFE_EXTENSIONS
    - Không thực thi file, chỉ mở bằng ứng dụng mặc định
    """
    p = Path(path)

    if open_file:
        if not p.is_file():
            return False
        ext = p.suffix.lstrip(".").lower()
        if ext not in SAFE_EXTENSIONS:
            return False
        target = str(p.resolve())
    else:
        if p.is_file():
            target = str(p.parent.resolve())
        elif p.is_dir():
            target = str(p.resolve())
        else:
            return False

    try:
        subprocess.Popen(
            ["xdg-open", target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (FileNotFoundError, OSError):
        return False


def safe_notify(title: str, message: str) -> bool:
    """
    Gửi thông báo hệ thống qua notify-send (Linux Desktop Notification).
    BẢO MẬT: shell=False, sanitize input text.
    """
    safe_title = re.sub(r"[<>&;|`$]", "", title)[:100]
    safe_msg = re.sub(r"[<>&;|`$]", "", message)[:300]
    try:
        subprocess.Popen(
            ["notify-send", "--app-name=MediaDownloader", safe_title, safe_msg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True
    except (FileNotFoundError, OSError):
        return False
