#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Media Extractor (Videos, Photos, Albums via Web Embed widget).
"""

from __future__ import annotations

import re
import hashlib
from typing import Optional
import urllib.request

from utils.network import is_safe_remote_url


def resolve_telegram_media(url: str) -> Optional[dict]:
    """
    Trích xuất media (Video hoặc Hình ảnh) từ liên kết Telegram (t.me).
    Sử dụng Web Embed Widget chính thức của Telegram (https://t.me/<channel>/<id>?embed=1).
    """
    if not is_safe_remote_url(url):
        return None
    try:
        clean_url = url.split("?")[0].rstrip("/")
        embed_url = clean_url + "?embed=1"
        m = re.search(r"t\.me/(?:c/\d+/|)([^/]+)/(\d+)", clean_url)
        channel = m.group(1) if m else "Telegram"
        post_id = m.group(2) if m else hashlib.md5(url.encode()).hexdigest()[:6]

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
                "Gecko/20100101 Firefox/120.0"
            )
        }
        req = urllib.request.Request(embed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        m_vid = re.search(r'<video[^>]+src=["\']([^"\']+)["\']', html)
        media_url = ""
        media_type = "image"
        ext = "jpg"
        if m_vid:
            media_url = m_vid.group(1)
            media_type = "video"
            ext = "mp4"

        all_photos: list[str] = []
        if not media_url:
            m_photos = re.findall(r"background-image:url\(['\"]?([^'\"]+)['\"]?\)", html)
            for photo in m_photos:
                if ("telegram" in photo or "telesco.pe" in photo or "cdn" in photo) and "avatar" not in photo.lower():
                    if photo not in all_photos:
                        all_photos.append(photo)
            if all_photos:
                media_url = all_photos[0]
            elif m_photos:
                media_url = m_photos[0]
                all_photos = [media_url]

        caption = ""
        m_txt = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
        if m_txt:
            caption = re.sub(r"<[^>]+>", "", m_txt.group(1)).strip()

        author = channel
        m_auth = re.search(r'<div class="tgme_widget_message_owner_name"[^>]*>(.*?)</div>', html, re.DOTALL)
        if m_auth:
            author = re.sub(r"<[^>]+>", "", m_auth.group(1)).strip() or channel

        if not media_url:
            return None

        title = caption[:70] if caption else f"Telegram @{channel} #{post_id}"
        is_album = len(all_photos) > 1 and media_type == "image"

        return {
            "id": f"{channel}_{post_id}",
            "title": title,
            "uploader": f"Telegram @{author}",
            "media_url": media_url,
            "images": all_photos if media_type == "image" else [],
            "media_type": "album" if is_album else media_type,
            "thumbnail": media_url if media_type == "image" else None,
            "ext": ext,
            "caption": caption,
        }
    except Exception:
        return None
