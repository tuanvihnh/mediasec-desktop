#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pinterest Media Extractor (Pin & CDN images/videos at Master resolution).
"""

from __future__ import annotations

import re
import json
import hashlib
from typing import Optional
import urllib.request

from utils.network import is_safe_remote_url


def upgrade_pinimg_url(url: str) -> tuple[str, str, int]:
    """
    Nâng cấp URL ảnh Pinterest (i.pinimg.com) từ thumbnail/preview thu nhỏ (236x, 474x, 564x, 736x, 1200x)
    lên chất lượng Master nguyên bản (originals) đạt độ phân giải và sắc nét 99-100% tối đa.
    Trả về (best_url, ext, filesize).
    """
    m = re.match(r"https?://i\.pinimg\.com/([^/]+)/(.+?)\.([a-zA-Z0-9]+)(?:\?.*)?$", url)
    if not m:
        return url, "jpg", 0
    size_part, rel_path, ext = m.groups()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": "https://www.pinterest.com/",
    }
    candidates = [
        f"https://i.pinimg.com/originals/{rel_path}.webp",
        f"https://i.pinimg.com/originals/{rel_path}.png",
        f"https://i.pinimg.com/originals/{rel_path}.jpg",
        f"https://i.pinimg.com/originals/{rel_path}.{ext}",
        f"https://i.pinimg.com/1200x/{rel_path}.{ext}",
        f"https://i.pinimg.com/736x/{rel_path}.{ext}",
        url,
    ]
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        try:
            req = urllib.request.Request(cand, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    cl = int(resp.headers.get("Content-Length", 0))
                    c_ext = cand.split("?")[0].split(".")[-1].lower()
                    return cand, c_ext, cl
        except Exception:
            continue
    return url, ext.lower(), 0


def resolve_pinterest_media(
    url: str,
    cookie_browser: Optional[str] = None,
    cookie_file: Optional[str] = None,
) -> Optional[dict]:
    """
    Trích xuất hình ảnh hoặc video gốc chất lượng cao nhất từ Pinterest (Pin & CDN):
    - Hỗ trợ các link dạng:
      • https://www.pinterest.com/pin/1146166174086802345/
      • https://pin.it/XXXXXX (tự động giải phóng link rút gọn)
      • https://i.pinimg.com/... (tự động nâng cấp lên Originals WebP/PNG/JPG Master)
    - Tự động dò tìm phân giải cao nhất (Originals / 1200x), loại bỏ giới hạn preview.
    - Đạt chuẩn sắc nét ~99-100% so với ảnh hiển thị trên Web.
    """
    if not is_safe_remote_url(url):
        return None

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "vi,en-US;q=0.9,en;q=0.8",
        "Referer": "https://www.pinterest.com/",
    }

    if "pin.it/" in url:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                url = resp.geturl()
        except Exception:
            pass

    if "i.pinimg.com" in url:
        best_url, ext, content_len = upgrade_pinimg_url(url)
        path_hash = hashlib.md5(url.encode()).hexdigest()[:10]
        m_part = re.search(r"i\.pinimg\.com/[^/]+/(.+?)\.[a-zA-Z0-9]+", url)
        raw_id = m_part.group(1).replace("/", "_") if m_part else path_hash
        return {
            "id": raw_id,
            "title": f"Pinterest Master Image #{raw_id.split('_')[-1]}",
            "media_url": best_url,
            "media_type": "image",
            "ext": ext,
            "filesize": content_len,
            "thumbnail": best_url,
            "uploader": "Pinterest CDN",
        }

    pin_id_match = re.search(r"/pin/(\d+)", url)
    pin_id = pin_id_match.group(1) if pin_id_match else hashlib.md5(url.encode()).hexdigest()[:10]

    html = ""
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        pass

    if not html:
        return None

    title = f"Pinterest Pin #{pin_id}"
    t_match = re.search(r"<title>([^<]+)</title>", html)
    if t_match:
        t = t_match.group(1).split("|")[0].strip()
        if t and "pinterest" not in t.lower():
            title = t
    meta_title = re.search(r'<meta[^>]+property=[\"\']og:title[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html)
    if meta_title and meta_title.group(1).strip():
        title = meta_title.group(1).strip()

    video_matches = re.findall(r'https?://v\.pinimg\.com/videos/[^\s\"\'<>]+\.mp4', html)
    if not video_matches:
        video_matches = re.findall(r'https?://[^\s\"\'<>]+\.mp4', html)
    if video_matches:
        best_vid = video_matches[0]
        for v in video_matches:
            if "1080p" in v.lower() or "720p" in v.lower() or "exp7" in v.lower():
                best_vid = v
                break
        return {
            "id": pin_id,
            "title": title,
            "media_url": best_vid,
            "media_type": "video",
            "ext": "mp4",
            "filesize": 0,
            "thumbnail": "",
            "uploader": "Pinterest Video",
        }

    pin_img = None
    json_ld_matches = re.findall(r'<script[^>]+type=[\"\']application/ld\+json[\"\'][^>]*>(.*?)</script>', html, re.DOTALL)
    for j in json_ld_matches:
        try:
            data = json.loads(j)
            img = data.get("image")
            if img and isinstance(img, str) and "pinimg.com" in img:
                pin_img = img
                break
        except Exception:
            pass

    if not pin_img:
        preload_matches = re.findall(r'<link[^>]+rel=[\"\']preload[\"\'][^>]+href=[\"\'](https://i\.pinimg\.com/[^\"\']+)[\"\']', html)
        if preload_matches:
            pin_img = preload_matches[0]
        else:
            og_imgs = re.findall(r'<meta[^>]+property=[\"\']og:image[\"\'][^>]+content=[\"\']([^\"\']+)[\"\']', html)
            if og_imgs:
                pin_img = og_imgs[0]

    if pin_img:
        best_url, best_ext, best_len = upgrade_pinimg_url(pin_img)
        return {
            "id": pin_id,
            "title": title,
            "media_url": best_url,
            "media_type": "image",
            "ext": best_ext,
            "filesize": best_len,
            "thumbnail": best_url,
            "uploader": "Pinterest",
        }

    orig_matches = re.findall(r'https://i\.pinimg\.com/originals/[a-zA-Z0-9/_.-]+\.(?:webp|jpg|jpeg|png)', html)
    x1200_matches = re.findall(r'https://i\.pinimg\.com/1200x/[a-zA-Z0-9/_.-]+\.(?:webp|jpg|jpeg|png)', html)
    x736_matches = re.findall(r'https://i\.pinimg\.com/736x/[a-zA-Z0-9/_.-]+\.(?:webp|jpg|jpeg|png)', html)

    raw_candidates = orig_matches + x1200_matches + x736_matches
    expanded_candidates = []
    for cand in raw_candidates:
        cand_clean = cand.split("?")[0].strip()
        if any(bad in cand_clean for bad in ["_RS", "board_thumbnail", "avatar", "icon"]):
            continue
        if "i.pinimg.com" in cand_clean:
            m = re.match(r"https?://i\.pinimg\.com/([^/]+)/(.+?)\.([a-zA-Z0-9]+)", cand_clean)
            if m:
                _, rel_p, orig_e = m.groups()
                expanded_candidates.append(f"https://i.pinimg.com/originals/{rel_p}.webp")
                expanded_candidates.append(f"https://i.pinimg.com/originals/{rel_p}.png")
                expanded_candidates.append(f"https://i.pinimg.com/originals/{rel_p}.jpg")
                expanded_candidates.append(f"https://i.pinimg.com/originals/{rel_p}.{orig_e}")
                expanded_candidates.append(f"https://i.pinimg.com/1200x/{rel_p}.{orig_e}")
                expanded_candidates.append(f"https://i.pinimg.com/736x/{rel_p}.{orig_e}")
        expanded_candidates.append(cand_clean)

    seen = set()
    cands_to_probe = []
    for c in expanded_candidates:
        if c not in seen and c.startswith("http"):
            seen.add(c)
            cands_to_probe.append(c)

    best_url = None
    best_len = 0
    best_ext = "jpg"

    for cand in cands_to_probe:
        try:
            req = urllib.request.Request(cand, headers=headers, method="HEAD")
            with urllib.request.urlopen(req, timeout=4) as resp:
                if resp.status == 200:
                    cl = int(resp.headers.get("Content-Length", 0))
                    best_url = cand
                    best_len = cl
                    best_ext = cand.split("?")[0].split(".")[-1].lower()
                    break
        except Exception:
            continue

    if not best_url and cands_to_probe:
        best_url = cands_to_probe[0]
        best_ext = best_url.split("?")[0].split(".")[-1].lower()

    if best_url:
        return {
            "id": pin_id,
            "title": title,
            "media_url": best_url,
            "media_type": "image",
            "ext": best_ext,
            "filesize": best_len,
            "thumbnail": best_url,
            "uploader": "Pinterest",
        }
    return None
