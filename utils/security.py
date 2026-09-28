#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Security Auditing, Permissions, DRM Analysis & File Integrity Modules.
"""

from __future__ import annotations

import os
import shutil
import hashlib
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from utils.constants import (
    MIN_FREE_DISK_BYTES,
    MAX_FILESIZE_BYTES,
    SAFE_EXTENSIONS,
    DANGEROUS_MAGIC_HEADERS,
    MAGIC_BYTES_MAP,
    DRM_UUIDS,
)
from utils.helpers import format_bytes


def preflight_disk_check(save_dir: str) -> tuple[bool, str]:
    """Kiểm tra quyền ghi và dung lượng trống trước khi tải."""
    path = Path(save_dir)
    if not path.is_dir():
        return False, f"Thư mục không tồn tại: {save_dir}"
    if not os.access(save_dir, os.W_OK):
        return False, f"Không có quyền ghi vào: {save_dir}"

    usage = shutil.disk_usage(save_dir)
    free_mb = usage.free / (1024 * 1024)
    if usage.free < MIN_FREE_DISK_BYTES:
        return False, (
            f"Dung lượng trống không đủ: {free_mb:.0f} MB "
            f"(cần tối thiểu {MIN_FREE_DISK_BYTES // (1024*1024)} MB)"
        )
    return True, f"OK – Còn trống {free_mb:.0f} MB"


def harden_file_permissions(filepath: str) -> bool:
    """
    Bảo mật Linux: Bỏ toàn bộ quyền thực thi (chmod 0644: -rw-r--r--).
    Đảm bảo file tải về không thể bị thực thi trực tiếp, chống mã độc.
    """
    try:
        os.chmod(filepath, 0o644)
        return True
    except OSError:
        return False


def compute_file_sha256(filepath: str) -> Optional[str]:
    """Tính mã băm SHA-256 để kiểm định tính toàn vẹn và đối chiếu mẫu mã độc."""
    try:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def cleanup_temp_files(save_dir: str, prefix: str = "") -> int:
    """Dọn dẹp các file tạm .part, .ytdl dở dang khi bị hủy hoặc gặp lỗi."""
    cleaned = 0
    try:
        p_dir = Path(save_dir)
        if p_dir.is_dir():
            for f in p_dir.iterdir():
                if f.is_file() and (f.suffix in (".part", ".ytdl", ".temp")):
                    if not prefix or f.name.startswith(prefix):
                        try:
                            f.unlink()
                            cleaned += 1
                        except OSError:
                            pass
    except Exception:
        pass
    return cleaned


def validate_file_integrity(filepath: str) -> tuple[bool, list[str]]:
    """
    Kiểm tra tính toàn vẹn file sau khi tải về và tăng cường bảo mật.

    1. Tự động thu hồi quyền thực thi (chmod 0644)
    2. Chặn ký tự ẩn RLO (Right-to-Left Override) đánh tráo tên file
    3. Extension whitelist check
    4. Quét chữ ký nhị phân thực thi (ELF, PE exe, Shebang, Java bytecode)
    5. Double extension detection (e.g. video.mp4.exe)
    6. Magic bytes (file signature) validation
    7. File size anomaly check

    Returns: (is_safe, list_of_warnings)
    """
    warnings: list[str] = []
    p = Path(filepath)

    if not p.is_file():
        return True, []  # File không tồn tại (có thể là temp), bỏ qua

    # 1. Tự động thu hồi quyền thực thi (chống nguy cơ thực thi file)
    harden_file_permissions(filepath)

    # 2. Phát hiện ký tự RLO (Right-to-Left Override) độc hại
    if "\u202e" in p.name:
        warnings.append(
            f"🚨 NGUY HIỂM: Phát hiện ký tự RLO (Right-to-Left Override) ẩn nhằm đánh tráo đuôi file: {repr(p.name)}"
        )

    # 3. Extension whitelist check
    ext = p.suffix.lstrip(".").lower()
    if ext and ext not in SAFE_EXTENSIONS:
        warnings.append(
            f"⚠ Extension không nằm trong whitelist: .{ext} "
            f"(File: {p.name})"
        )

    # 4. Double extension detection (chống file giả mạo như video.mp4.exe)
    name_parts = p.name.rsplit(".", maxsplit=3)
    if len(name_parts) >= 3:
        suspicious_exts = {"exe", "bat", "cmd", "sh", "ps1", "vbs", "js",
                           "msi", "dll", "scr", "com", "pif", "hta", "desktop"}
        for part in name_parts[1:]:
            if part.lower() in suspicious_exts:
                warnings.append(
                    f"🚨 NGUY HIỂM: Phát hiện double extension đáng ngờ: {p.name}"
                )
                break

    # Đọc header kiểm tra chữ ký nhị phân
    header = b""
    try:
        with open(filepath, "rb") as f:
            header = f.read(32)  # Đọc 32 bytes đầu
    except (OSError, PermissionError):
        pass

    # 5. Quét chữ ký nhị phân thực thi độc hại (Executable Header Injection)
    for bad_sig, desc in DANGEROUS_MAGIC_HEADERS:
        if header.startswith(bad_sig):
            warnings.append(
                f"🚨 NGUY HIỂM TỐI CAO: File chứa chữ ký thực thi nhị phân ({desc}) giả mạo media! (File: {p.name})"
            )
            break

    # 6. Magic bytes validation
    if ext in MAGIC_BYTES_MAP and header:
        expected_sigs = MAGIC_BYTES_MAP[ext]
        matched = False
        for sig in expected_sigs:
            if sig in header[:16]:
                matched = True
                break

        if not matched and len(header) >= 4:
            # Đặc biệt cho MP4/M4A: kiểm tra 'ftyp' tại offset 4
            if ext in ("mp4", "m4a") and b"ftyp" in header[:12]:
                matched = True

        if not matched and len(header) >= 4:
            warnings.append(
                f"⚠ Magic bytes không khớp extension .{ext}: "
                f"File có thể bị giả mạo hoặc hỏng (File: {p.name})"
            )

    # 7. File size anomaly check
    try:
        file_size = p.stat().st_size
        if file_size == 0:
            warnings.append(f"⚠ File rỗng (0 bytes): {p.name}")
        elif file_size > MAX_FILESIZE_BYTES:
            warnings.append(
                f"⚠ File vượt giới hạn dung lượng ({format_bytes(file_size)}): {p.name}"
            )
    except OSError:
        pass

    is_safe = not any("🚨" in w for w in warnings)
    return is_safe, warnings


def validate_downloaded_files(save_dir: str, prefix: str) -> tuple[bool, list[str]]:
    """
    Quét toàn bộ file mới tải trong thư mục save_dir có prefix phù hợp.
    Trả về (all_safe, combined_warnings).
    """
    all_warnings: list[str] = []
    all_safe = True

    p_dir = Path(save_dir)
    if not p_dir.is_dir():
        return True, []

    for f in p_dir.iterdir():
        if f.is_file() and f.name.startswith(prefix):
            safe, warnings = validate_file_integrity(str(f))
            all_warnings.extend(warnings)
            if not safe:
                all_safe = False

    return all_safe, all_warnings


def detect_drm_mpd(manifest_text: str) -> list[str]:
    """Phát hiện DRM trong file DASH .mpd – quét thẻ <ContentProtection>."""
    found: list[str] = []
    try:
        root = ET.fromstring(manifest_text)
    except ET.ParseError:
        return found

    for elem in root.iter():
        tag_local = elem.tag.rsplit("}", 1)[-1] if "}" in elem.tag else elem.tag
        if tag_local == "ContentProtection":
            scheme = (elem.get("schemeIdUri") or "").lower()
            for uuid, name in DRM_UUIDS.items():
                if uuid in scheme:
                    found.append(name)
                    break
            else:
                value = elem.get("value") or elem.get("schemeIdUri") or "Unknown"
                if value.lower() not in ("cenc",):
                    found.append(f"ContentProtection({value})")
    return list(dict.fromkeys(found))


def detect_drm_hls(manifest_text: str) -> list[str]:
    """Phát hiện DRM / mã hóa trong file HLS .m3u8."""
    found: list[str] = []
    for line in manifest_text.splitlines():
        line_s = line.strip()
        if line_s.startswith("#EXT-X-KEY:"):
            attrs = line_s[len("#EXT-X-KEY:") :]
            if "METHOD=SAMPLE-AES" in attrs.upper():
                found.append("HLS SAMPLE-AES (FairPlay/DRM)")
            elif "METHOD=AES-128" in attrs.upper():
                found.append("HLS AES-128 Encryption")
        if line_s.startswith("#EXT-X-SESSION-KEY:"):
            found.append("HLS Session Key (có thể DRM)")
    return list(dict.fromkeys(found))


def check_cleartext_warning(manifest_text: str, is_mpd: bool) -> bool:
    """Trả về True nếu manifest KHÔNG có bất kỳ mã hóa nào → cleartext."""
    if is_mpd:
        return len(detect_drm_mpd(manifest_text)) == 0
    else:
        for line in manifest_text.splitlines():
            ls = line.strip()
            if ls.startswith("#EXT-X-KEY:") and "METHOD=NONE" not in ls.upper():
                return False
        return True
