#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lossless Image Metadata Stripping (JPEG, PNG, WebP) without re-encoding bitstreams.
"""

from __future__ import annotations

import os
import shutil
import struct

from utils.security import harden_file_permissions


def lossless_strip_jpeg_metadata(data: bytes) -> bytes:
    """Loại bỏ siêu dữ liệu nhạy cảm EXIF / XMP / IPTC khỏi tệp JPEG mà không decode/re-encode (giữ nguyên 100% DCT pixel)."""
    if not data.startswith(b"\xff\xd8"):
        return data
    out = bytearray(b"\xff\xd8")
    pos = 2
    l = len(data)
    while pos < l:
        if data[pos] != 0xFF:
            out.extend(data[pos:])
            break
        while pos < l and data[pos] == 0xFF:
            pos += 1
        if pos >= l:
            break
        marker = data[pos]
        pos += 1
        if marker in (0xD8, 0xD9, 0x00) or (0xD0 <= marker <= 0xD7):
            out.extend(bytes([0xFF, marker]))
            continue
        if pos + 2 > l:
            break
        length = (data[pos] << 8) | data[pos + 1]
        chunk = data[pos - 2 : pos + length]
        if marker in (0xE1, 0xED):
            pass
        else:
            out.extend(chunk)
        pos += length
    return bytes(out)


def lossless_strip_png_metadata(data: bytes) -> bytes:
    """Loại bỏ chunk metadata (eXIf, tEXt, zTXt, iTXt) khỏi tệp PNG mà không giải nén/nén lại IDAT."""
    png_sig = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(png_sig):
        return data
    out = bytearray(png_sig)
    pos = 8
    l = len(data)
    skip_types = {b"eXIf", b"tEXt", b"zTXt", b"iTXt"}
    while pos + 8 <= l:
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        chunk_type = data[pos + 4 : pos + 8]
        chunk_total = 12 + length
        if pos + chunk_total > l:
            out.extend(data[pos:])
            break
        if chunk_type not in skip_types:
            out.extend(data[pos : pos + chunk_total])
        pos += chunk_total
    return bytes(out)


def lossless_strip_webp_metadata(data: bytes) -> bytes:
    """Loại bỏ EXIF/XMP khỏi container WebP RIFF mà không chạm vào bitstream VP8/VP8L."""
    if not (data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP"):
        return data
    pos = 12
    l = len(data)
    out_chunks = bytearray()
    skip_chunks = {b"EXIF", b"XMP "}
    has_stripped = False

    while pos + 8 <= l:
        fourcc = data[pos : pos + 4]
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        pad = size % 2
        chunk_len = 8 + size + pad
        if pos + chunk_len > l:
            out_chunks.extend(data[pos:])
            break
        if fourcc in skip_chunks:
            has_stripped = True
        elif fourcc == b"VP8X" and size >= 10:
            flags = data[pos + 8]
            flags = flags & ~0x08
            flags = flags & ~0x04
            vp8x_chunk = bytearray(data[pos : pos + chunk_len])
            vp8x_chunk[8] = flags
            out_chunks.extend(vp8x_chunk)
        else:
            out_chunks.extend(data[pos : pos + chunk_len])
        pos += chunk_len

    if not has_stripped:
        return data

    new_riff_size = 4 + len(out_chunks)
    out = bytearray(b"RIFF")
    out.extend(struct.pack("<I", new_riff_size))
    out.extend(b"WEBP")
    out.extend(out_chunks)
    return bytes(out)


def lossless_strip_image_file_metadata(file_path: str) -> bool:
    """Thực hiện xóa siêu dữ liệu an toàn losslessly trực tiếp trên file đĩa."""
    try:
        with open(file_path, "rb") as f_in:
            data = f_in.read()
        ext = os.path.splitext(file_path)[1].lower()
        if ext in (".jpg", ".jpeg"):
            cleaned = lossless_strip_jpeg_metadata(data)
        elif ext == ".png":
            cleaned = lossless_strip_png_metadata(data)
        elif ext == ".webp":
            cleaned = lossless_strip_webp_metadata(data)
        else:
            return True

        if cleaned and len(cleaned) > 0 and len(cleaned) != len(data):
            tmp_p = file_path + ".tmp_clean"
            with open(tmp_p, "wb") as f_out:
                f_out.write(cleaned)
            shutil.move(tmp_p, file_path)
            harden_file_permissions(file_path)
        return True
    except Exception:
        return False
