#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rule34 & Booru Media Resolvers (Posts, Images, Videos, Tags).
"""

from __future__ import annotations

import re
import hashlib
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import urllib.request

from utils.network import is_safe_remote_url


def resolve_rule34_post(url: str) -> Optional[dict]:
    """
    Trích xuất bài đăng từ Rule34 hoặc các Booru tương tự (rule34.xxx, rule34.paheal.net, gelbooru, etc.).
    Hỗ trợ cả link post view lẫn link file ảnh/video trực tiếp (wimg.rule34.xxx/images/...).
    """
    if not is_safe_remote_url(url):
        return None
    url_l = url.lower()
    if any(f".{ext}" in url_l for ext in ("jpg", "jpeg", "png", "gif", "mp4", "webm")) and (
        "rule34" in url_l or "booru" in url_l
    ):
        ext = "mp4" if (".mp4" in url_l or ".webm" in url_l) else "jpg"
        for e in ("png", "gif", "jpeg", "jpg", "webm", "mp4"):
            if f".{e}" in url_l:
                ext = e
                break
        is_video = ext in ("mp4", "webm")
        return {
            "id": hashlib.md5(url.encode()).hexdigest()[:10],
            "title": f"Rule34 Media ({Path(urlparse(url).path).name})",
            "uploader": "Rule34 CDN",
            "media_url": url,
            "media_type": "video" if is_video else "image",
            "thumbnail": url if not is_video else None,
            "ext": ext,
            "tags": [],
        }

    m_id = re.search(r"[?&]id=(\d+)", url) or re.search(r"/view/(\d+)", url) or re.search(r"/posts?/(\d+)", url)
    post_id = m_id.group(1) if m_id else "unknown"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
            "Gecko/20100101 Firefox/120.0"
        )
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        media_url = ""
        m_orig = re.search(
            r'<a[^>]+href=["\'](https?://[^"\']+\.(?:jpg|jpeg|png|gif|mp4|webm)[^"\']*)["\'][^>]*>\s*Original image',
            html,
            re.IGNORECASE,
        )
        if m_orig:
            media_url = m_orig.group(1)

        if not media_url:
            m_og = re.search(
                r'<meta\s+property=["\']og:image["\']\s+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if m_og and not m_og.group(1).endswith("favicon.ico"):
                media_url = m_og.group(1)

        if not media_url:
            m_vid = re.search(
                r'<video[^>]*>.*?<source[^>]+src=["\']([^"\']+)["\']',
                html,
                re.DOTALL | re.IGNORECASE,
            )
            if m_vid:
                media_url = m_vid.group(1)

        if not media_url:
            m_img = re.search(
                r'<img[^>]+id=["\']image["\'][^>]+src=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if m_img:
                media_url = m_img.group(1)

        if not media_url:
            m_js = re.search(
                r"image\s*=\s*\{[^}]*['\"]domain['\"]\s*:\s*['\"]([^'\"]+)['\"][^}]*['\"]dir['\"]\s*:\s*(\d+)[^}]*['\"]img['\"]\s*:\s*['\"]([^'\"]+)['\"]",
                html,
            )
            if m_js:
                domain, directory, img_name = m_js.groups()
                domain = domain.rstrip("/")
                media_url = f"{domain}//images/{directory}/{img_name}"

        if not media_url:
            found_urls = re.findall(
                r'https?://[^\s"\'<>]+\.(?:jpg|jpeg|png|gif|mp4|webm)(?:\?[^\s"\'<>]*)?',
                html,
                re.IGNORECASE,
            )
            for u in found_urls:
                if "images" in u or "sample" in u or "thumbnails" in u:
                    media_url = u
                    break

        if not media_url:
            return None

        if media_url.startswith("//"):
            media_url = "https:" + media_url

        ext = "jpg"
        for e in ("png", "gif", "jpeg", "jpg", "webm", "mp4"):
            if f".{e}" in media_url.lower():
                ext = e
                break

        is_video = ext in ("mp4", "webm")

        tags = re.findall(r'<li class=["\']tag-type-[^"\']*["\'][^>]*>.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
        clean_tags = [t.strip() for t in tags if t.strip() and t.strip() != "?"]

        return {
            "id": post_id,
            "title": f"Rule34 Post #{post_id}",
            "uploader": "Rule34" if "rule34" in url_l else "Booru",
            "media_url": media_url,
            "media_type": "video" if is_video else "image",
            "thumbnail": media_url if not is_video else None,
            "ext": ext,
            "tags": clean_tags[:8],
        }
    except Exception:
        return None
