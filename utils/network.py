#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Network Utility Functions (URL verification, Platform auto-detection, Direct file downloader).
"""

from __future__ import annotations

import os
import re
import time
import shutil
import threading
from typing import Optional
from urllib.parse import urlparse
import urllib.request
import urllib.parse
import urllib.error

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from utils.constants import (
    MAX_FILESIZE_BYTES,
    MAX_CLIPBOARD_LENGTH,
    SUPPORTED_IMAGE_EXTS,
    SUPPORTED_MEDIA_EXTS,
    SAFE_EXTENSIONS,
    RE_TWITTER,
    RE_YOUTUBE,
    RE_FACEBOOK,
    RE_TIKTOK,
    RE_INSTAGRAM,
    RE_REDDIT,
    RE_BILIBILI,
    RE_ZINGMP3,
    RE_SPOTIFY,
    RE_IWARA,
    RE_RULE34,
    RE_BOORU_OTHER,
    RE_TELEGRAM,
    RE_PINTEREST,
    RE_LOCAL_STREAM,
)
from utils.helpers import format_bytes
from utils.security import harden_file_permissions


def is_safe_remote_url(url: str, allow_private: bool = False) -> bool:
    """
    Kiểm tra URL an toàn:
    - Scheme phải là http hoặc https
    - Chống SSRF: Chặn loopback, private IP (127.0.0.1, 10.x, 192.168.x...) trừ khi allow_private=True
    - Chống Command Injection & ký tự điều khiển
    """
    if not url or not isinstance(url, str):
        return False
    url = url.strip()
    if len(url) > MAX_CLIPBOARD_LENGTH:
        return False
    if any(c in url for c in ['\x00', '\r', '\n', '`', '$', '|', '<', '>', '"', '{', '}']):
        return False
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = (parsed.hostname or "").lower()
        if not hostname:
            return False
        if not allow_private:
            if hostname in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
                return False
            if hostname.endswith((".local", ".localhost", ".internal", ".lan")):
                return False
            import ipaddress
            try:
                ip = ipaddress.ip_address(hostname)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                    return False
            except ValueError:
                pass
        return True
    except Exception:
        return False


def is_direct_image_url(url: str) -> bool:
    """Kiểm tra URL có phải là liên kết hình ảnh trực tiếp (PNG, JPG, GIF, WebP, JNG, BMP...)."""
    if not url or not isinstance(url, str):
        return False
    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
        if parsed.scheme not in ("http", "https"):
            return False
        path = parsed.path.lower()
        if any(path.endswith(f".{ext}") for ext in SUPPORTED_IMAGE_EXTS):
            return True
        if re.search(r"[?&](?:format|ext|f)=([a-zA-Z0-9]+)", parsed.query, re.IGNORECASE):
            m = re.search(r"[?&](?:format|ext|f)=([a-zA-Z0-9]+)", parsed.query, re.IGNORECASE)
            if m and m.group(1).lower() in SUPPORTED_IMAGE_EXTS:
                return True
        if "pbs.twimg.com/media/" in url_clean.lower():
            return True
        if re.search(r"\.(png|jpe?g|gif|webp|bmp|svg|ico|jfif|jng)\b", url_clean, re.IGNORECASE):
            return True
        return False
    except Exception:
        return False


def is_direct_media_url(url: str) -> bool:
    """Kiểm tra URL có phải là liên kết Video hoặc Audio trực tiếp (MP4, WebM, MP3...)."""
    if not url or not isinstance(url, str):
        return False
    url_clean = url.strip()
    try:
        parsed = urlparse(url_clean)
        if parsed.scheme not in ("http", "https"):
            return False
        path = parsed.path.lower()
        return any(path.endswith(f".{ext}") for ext in SUPPORTED_MEDIA_EXTS)
    except Exception:
        return False


def is_rule34_url(url: str) -> bool:
    """Kiểm tra URL từ Rule34 hoặc các trang Booru phổ biến (rule34.xxx, rule34video, gelbooru...)."""
    if not url or not isinstance(url, str):
        return False
    url_l = url.strip().lower()
    return bool(
        "rule34.xxx" in url_l
        or "rule34video.com" in url_l
        or "rule34.paheal.net" in url_l
        or "gelbooru.com" in url_l
        or "danbooru.donmai.us" in url_l
        or "safebooru.org" in url_l
        or "yande.re" in url_l
        or "konachan.com" in url_l
        or "e-shuushuu.net" in url_l
        or RE_RULE34.match(url)
        or RE_BOORU_OTHER.match(url)
    )


def is_iwara_url(url: str) -> bool:
    """Kiểm tra URL từ Iwara (iwara.tv)."""
    if not url or not isinstance(url, str):
        return False
    url_l = url.strip().lower()
    return "iwara.tv" in url_l or bool(RE_IWARA.match(url))


def is_telegram_url(url: str) -> bool:
    """Kiểm tra URL từ Telegram (t.me, telegram.me, telesco.pe)."""
    if not url or not isinstance(url, str):
        return False
    url_l = url.strip().lower()
    return bool(
        "t.me/" in url_l
        or "telegram.me/" in url_l
        or "telesco.pe/" in url_l
        or RE_TELEGRAM.match(url)
    )


def is_pinterest_url(url: str) -> bool:
    """Kiểm tra URL có thuộc nền tảng Pinterest (pinterest.com, pin.it, i.pinimg.com...)."""
    if not url or not isinstance(url, str):
        return False
    url_l = url.strip().lower()
    return bool(
        "pinterest." in url_l
        or "pin.it/" in url_l
        or "pinimg.com" in url_l
        or RE_PINTEREST.match(url)
    )


def auto_detect_platform(url: str) -> Optional[str]:
    """
    Tự động nhận diện nền tảng từ URL.
    Trả về tên nền tảng hiển thị (dùng cho combobox) hoặc None nếu không nhận diện được.
    """
    if not url or not isinstance(url, str):
        return None

    url = url.strip()
    if len(url) > MAX_CLIPBOARD_LENGTH:
        return None

    if is_rule34_url(url):
        return "Rule34 / Booru (Image & Video)"

    if is_pinterest_url(url):
        return "Pinterest (Pin & Image)"

    if is_direct_image_url(url):
        return "Hình ảnh trực tiếp (PNG/JPG/GIF...)"

    if is_iwara_url(url):
        return "Iwara (iwara.tv)"

    if is_telegram_url(url):
        return "Telegram (t.me)"

    if RE_YOUTUBE.match(url):
        return "YouTube"
    if RE_TWITTER.match(url):
        return "Twitter / X"
    if RE_FACEBOOK.match(url):
        return "Facebook"
    if RE_TIKTOK.match(url):
        return "TikTok"
    if RE_INSTAGRAM.match(url):
        return "Instagram"
    if RE_REDDIT.match(url):
        return "Reddit"
    if RE_BILIBILI.match(url):
        return "Bilibili"
    if RE_ZINGMP3.match(url):
        return "Zing MP3"
    if RE_SPOTIFY.match(url):
        return "Spotify"
    if RE_LOCAL_STREAM.match(url):
        return "Local Lab / Custom Stream (HLS/DASH)"

    if is_direct_media_url(url):
        return "Media trực tiếp (MP4/WebM/MP3...)"

    if re.match(
        r"^https?://(?:(?:www|m|music)\.)?youtube\.com/(?:playlist\?|watch\?.*list=)",
        url,
    ):
        return "YouTube"

    if is_safe_remote_url(url):
        return "Nền tảng khác / Universal (yt-dlp)"

    return None


def fetch_manifest(url: str, timeout: int = 10) -> Optional[str]:
    """Tải nội dung manifest (.mpd hoặc .m3u8) phục vụ phân tích DRM & cleartext."""
    try:
        if HAS_REQUESTS:
            resp = requests.get(
                url,
                timeout=timeout,
                headers={"User-Agent": "AuditTool/1.0"},
                verify=True,
            )
            return resp.text if resp.status_code == 200 else None
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "AuditTool/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def download_direct_file(
    url: str,
    save_path: str,
    max_bytes: int = MAX_FILESIZE_BYTES,
    headers: Optional[dict] = None,
    on_progress: Optional[callable] = None,
    on_status: Optional[callable] = None,
    pause_event: Optional[threading.Event] = None,
    cancel_event: Optional[threading.Event] = None,
) -> tuple[bool, str]:
    """
    Tải file trực tiếp qua HTTP/HTTPS streaming an toàn:
    - BẢO MẬT: Kiểm tra SSRF, chống DoS bằng kiểm soát max_bytes từng chunk.
    - An toàn đĩa: Ghi vào file .part trước khi atomic move sang file đích.
    - Hỗ trợ Pause / Resume và Cancel ngay lập tức.
    """
    if not is_safe_remote_url(url):
        return False, "URL không an toàn hoặc vi phạm chính sách bảo mật mạng (chống SSRF)."

    default_headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
            "Gecko/20100101 Firefox/120.0"
        ),
        "Accept": "*/*",
    }
    if headers:
        default_headers.update(headers)

    part_path = save_path + ".part"
    downloaded_bytes = 0
    start_time = time.time()

    try:
        req = urllib.request.Request(url, headers=default_headers)
        with urllib.request.urlopen(req, timeout=25) as resp:
            content_len_header = resp.headers.get("Content-Length")
            total_size = int(content_len_header) if content_len_header and content_len_header.isdigit() else 0
            content_type = resp.headers.get("Content-Type", "").lower()
            save_ext = os.path.splitext(save_path)[1].lower().lstrip(".")

            if save_ext in SAFE_EXTENSIONS and any(h in content_type for h in ["text/html", "text/plain"]):
                return False, f"Máy chủ trả về trang web HTML ({content_type}) thay vì tệp media hình ảnh/video thực tế. Bài viết có thể bị giới hạn hoặc yêu cầu đăng nhập."

            if total_size > max_bytes:
                return False, f"Dung lượng file ({format_bytes(total_size)}) vượt quá giới hạn an toàn ({format_bytes(max_bytes)})."

            chunk_size = 64 * 1024  # 64 KB
            with open(part_path, "wb") as f_out:
                while True:
                    if cancel_event and cancel_event.is_set():
                        f_out.close()
                        if os.path.exists(part_path):
                            os.remove(part_path)
                        return False, "Người dùng đã hủy tải xuống."

                    if pause_event and not pause_event.is_set():
                        if on_status:
                            on_status("⏸️ Tạm dừng – Nhấn ▶️ Tiếp tục để tiếp tục tải…")
                        pause_event.wait()
                        if cancel_event and cancel_event.is_set():
                            f_out.close()
                            if os.path.exists(part_path):
                                os.remove(part_path)
                            return False, "Người dùng đã hủy tải xuống."
                        if on_status:
                            on_status("▶️ Đã tiếp tục tải…")

                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break

                    if downloaded_bytes == 0 and save_ext in SAFE_EXTENSIONS:
                        first_bytes = chunk[:64].lower()
                        if b"<!doctype html" in first_bytes or b"<html" in first_bytes:
                            f_out.close()
                            if os.path.exists(part_path):
                                os.remove(part_path)
                            return False, "Nội dung nhận được từ máy chủ là trang web HTML thay vì dữ liệu media nhị phân. Vui lòng kiểm tra quyền riêng tư của liên kết."

                    f_out.write(chunk)
                    downloaded_bytes += len(chunk)

                    if downloaded_bytes > max_bytes:
                        f_out.close()
                        if os.path.exists(part_path):
                            os.remove(part_path)
                        return False, f"Dung lượng tải về vượt quá giới hạn an toàn ({format_bytes(max_bytes)})."

                    if total_size > 0 and on_progress:
                        pct = (downloaded_bytes / total_size) * 100
                        on_progress(pct)
                    elapsed = max(time.time() - start_time, 0.1)
                    speed = downloaded_bytes / elapsed
                    speed_str = f" – {speed / 1024:.0f} KB/s" if speed > 0 else ""
                    if on_status:
                        if total_size > 0:
                            on_status(f"Đang tải: {(downloaded_bytes / total_size) * 100:.1f}%{speed_str}")
                        else:
                            on_status(f"Đang tải: {downloaded_bytes / 1024:.0f} KB{speed_str}")

        if os.path.exists(save_path):
            os.remove(save_path)
        shutil.move(part_path, save_path)
        harden_file_permissions(save_path)
        if on_progress:
            on_progress(100.0)
        return True, save_path

    except Exception as exc:
        if os.path.exists(part_path):
            try:
                os.remove(part_path)
            except OSError:
                pass
        return False, f"Lỗi tải trực tiếp: {exc}"
