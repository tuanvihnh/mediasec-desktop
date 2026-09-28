#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Photo & Album Media Extractor (fbcdn.net resolution parsing).
"""

from __future__ import annotations

import re
import html
import hashlib
from pathlib import Path
from typing import Optional
import urllib.request

from utils.network import is_safe_remote_url


def resolve_facebook_photo(
    url: str,
    cookie_browser: Optional[str] = None,
    cookie_file: Optional[str] = None,
) -> Optional[dict]:
    """
    Trích xuất liên kết hình ảnh gốc chất lượng cao từ trang Facebook Photo:
    Hỗ trợ các link dạng:
    - https://www.facebook.com/photo/?fbid=122309558474022335&set=...
    - https://www.facebook.com/photo.php?fbid=...
    - https://www.facebook.com/photo?fbid=...
    - https://www.facebook.com/<user>/photos/...
    Bóc tách mã nguồn trang và giải mã URL CDN thực tế (fbcdn.net) chất lượng cao nhất.
    """
    if not is_safe_remote_url(url):
        return None

    m_fbid = re.search(r"[?&]fbid=(\d+)", url) or re.search(r"/photos/[^/]+/(\d+)", url) or re.search(r"/photos/(\d+)", url)
    fbid = m_fbid.group(1) if m_fbid else hashlib.md5(url.encode()).hexdigest()[:10]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
            "Gecko/20100101 Firefox/120.0"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
    }

    if cookie_file and Path(cookie_file).is_file():
        try:
            cookie_pairs = []
            with open(cookie_file, "r", encoding="utf-8", errors="ignore") as cf:
                for line in cf:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        cookie_pairs.append(f"{parts[5]}={parts[6]}")
            if cookie_pairs:
                headers["Cookie"] = "; ".join(cookie_pairs)
        except Exception:
            pass

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw_html = resp.read().decode("utf-8", errors="ignore")

        clean_text = raw_html.replace(r"\/", "/").replace("&amp;", "&")

        caption = ""
        m_og_desc = re.search(r'<meta\s+property=["\']og:description["\']\s+content=["\']([^\"\']+)["\']', clean_text)
        if m_og_desc:
            caption = html.unescape(m_og_desc.group(1)).strip()
        if not caption:
            m_title = re.search(r"<title>([^<]+)</title>", clean_text)
            if m_title:
                t = html.unescape(m_title.group(1)).strip()
                caption = t.split("|")[0].strip()

        matches = re.findall(r'https?://[a-zA-Z0-9.-]*fbcdn\.net/[^\s"\'\\<>]+', clean_text)

        album_photos: list[str] = []
        seen_paths: set[str] = set()
        for m in matches:
            u = html.unescape(m).rstrip("\\")
            if any(bad in u for bad in ["t1.30497-1", "p50x50", "p100x100", "s100x100", "profile", "emoji"]):
                continue
            if any(k in u for k in ["t39.30808-6", "t1.6435-9", "t31.180-8", "_n.jpg", "_o.jpg", "dst-jpg"]):
                path_part = u.split("?")[0]
                if path_part not in seen_paths:
                    seen_paths.add(path_part)
                    album_photos.append(u)

        best_candidate = None
        fbid_prefix = fbid[:8] if len(fbid) >= 8 else fbid

        for u in album_photos:
            if "t39.30808-6" in u and (fbid_prefix in u):
                best_candidate = u
                break

        if not best_candidate:
            for u in album_photos:
                if "t39.30808-6" in u and ("_n.jpg" in u or "_o.jpg" in u or "dst-jpg" in u):
                    best_candidate = u
                    break

        if not best_candidate and album_photos:
            best_candidate = album_photos[0]

        if not best_candidate and matches:
            for m in matches:
                u = html.unescape(m).rstrip("\\")
                if not any(bad in u for bad in ["t1.30497-1", "p50x50", "p100x100", "s100x100"]):
                    best_candidate = u
                    if best_candidate not in album_photos:
                        album_photos.append(best_candidate)
                    break

        if not best_candidate:
            return None

        if best_candidate in album_photos:
            album_photos.remove(best_candidate)
        album_photos.insert(0, best_candidate)

        title = caption[:80] if caption else f"Facebook Photo #{fbid}"
        is_album = len(album_photos) > 1
        return {
            "id": fbid,
            "title": title,
            "uploader": "Facebook Photo",
            "media_url": best_candidate,
            "images": album_photos,
            "media_type": "album" if is_album else "image",
            "thumbnail": best_candidate,
            "ext": "jpg",
            "fbid": fbid,
        }
    except Exception:
        return None
