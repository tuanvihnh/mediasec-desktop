#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direct Image Media Extractor (Dimensions, Metadata, Probing).
"""

from __future__ import annotations

import io
import re
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import urllib.request

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from utils.constants import SUPPORTED_IMAGE_EXTS
from utils.network import is_safe_remote_url
from extractors.pinterest import upgrade_pinimg_url
from extractors.twitter import upgrade_twitter_image_url


def resolve_direct_image_info(url: str) -> Optional[dict]:
    """
    Trích xuất thông tin ảnh trực tiếp (PNG, JPG, GIF, WebP, JNG, BMP, SVG...):
    - Đọc dung lượng (Content-Length)
    - Đọc metadata & dimensions ảnh qua Pillow (PIL)
    - Trả về metadata an toàn
    """
    if not is_safe_remote_url(url):
        return None
    try:
        if "i.pinimg.com" in url:
            up_url, up_ext, up_sz = upgrade_pinimg_url(url)
            if up_url != url:
                url = up_url
        elif "pbs.twimg.com/media/" in url:
            up_url = upgrade_twitter_image_url(url, prefer_png=True)
            if up_url != url:
                url = up_url

        parsed = urlparse(url)
        path = parsed.path
        raw_name = Path(path).name or "image"
        ext = ""
        for possible_ext in SUPPORTED_IMAGE_EXTS:
            if path.lower().endswith(f".{possible_ext}"):
                ext = possible_ext
                break
        if not ext:
            m = re.search(r"[?&](?:format|ext|f)=([a-zA-Z0-9]+)", parsed.query, re.IGNORECASE)
            if m and m.group(1).lower() in SUPPORTED_IMAGE_EXTS:
                ext = m.group(1).lower()
            else:
                ext = "png"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        }
        total_size = 0
        img_w, img_h = 0, 0
        img_format = ext.upper()
        chunk = b""

        if HAS_REQUESTS:
            try:
                with requests.get(url, headers=headers, stream=True, timeout=10) as resp:
                    if resp.status_code == 200:
                        cl = resp.headers.get("content-length")
                        if cl and cl.isdigit():
                            total_size = int(cl)
                        chunk = resp.raw.read(65536)
            except Exception:
                chunk = b""

        if not chunk:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                cl = resp.headers.get("Content-Length")
                if cl and cl.isdigit():
                    total_size = int(cl)
                chunk = resp.read(65536)

        if HAS_PIL and chunk:
            try:
                with Image.open(io.BytesIO(chunk)) as img:
                    img_w, img_h = img.size
                    img_format = img.format or ext.upper()
            except Exception:
                pass

        dim_str = f"{img_w}x{img_h} px" if img_w and img_h else ""
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        title = f"{raw_name}" if raw_name and len(raw_name) < 80 else f"image_{url_hash}.{ext}"

        return {
            "title": title,
            "uploader": parsed.netloc,
            "filesize": total_size,
            "dimensions": dim_str,
            "format": img_format,
            "ext": ext,
            "thumbnail": url,
            "url": url,
        }
    except Exception:
        return None
