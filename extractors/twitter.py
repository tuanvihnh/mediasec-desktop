#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X Media Resolvers: Master Resolution Extractor and Fallback API.
"""

from __future__ import annotations

import re
import json
from typing import Optional
from urllib.parse import urlparse, parse_qs
import urllib.request

from utils.constants import RE_TWITTER


def upgrade_twitter_image_url(url: str, prefer_png: bool = True, probe_head: bool = True) -> str:
    """
    Bộ chuẩn hóa URL lấy ảnh gốc tối đa (Master Resolution Extractor):
    - Đối với URL ảnh từ Twitter/X (pbs.twimg.com/media/...): Tự động dùng regex tách các tham số query
      và thay thế bằng format=png (hoặc định dạng gốc) kèm name=orig để tải chất lượng cao nhất của tác giả,
      loại bỏ phiên bản nén của Twitter (small, 900x900, large...).
    - Giữ nguyên metadata và bảo toàn ICC Color Profile khi lưu file bằng Pillow.
    """
    if not url or "pbs.twimg.com/media/" not in url:
        return url

    m = re.search(r"https?://pbs\.twimg\.com/media/([a-zA-Z0-9_-]+)(?:\.([a-zA-Z0-9]+))?", url)
    if not m:
        return url

    media_id = m.group(1)
    ext_in_path = m.group(2)

    parsed = urlparse(url)
    q_params = parse_qs(parsed.query)
    current_fmt = (q_params.get("format", [None])[0] or ext_in_path or "jpg").lower()
    if ":" in current_fmt:
        current_fmt = current_fmt.split(":")[0]

    if current_fmt == "png":
        candidates = ["png", "jpg"]
    else:
        candidates = ["png", current_fmt] if prefer_png else [current_fmt, "png"]

    if probe_head:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Referer": "https://twitter.com/",
        }
        for c_fmt in candidates:
            cand_url = f"https://pbs.twimg.com/media/{media_id}?format={c_fmt}&name=orig"
            try:
                req = urllib.request.Request(cand_url, headers=headers, method="HEAD")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    if resp.status == 200:
                        return cand_url
            except Exception:
                continue

    target_fmt = candidates[0] if prefer_png else current_fmt
    return f"https://pbs.twimg.com/media/{media_id}?format={target_fmt}&name=orig"


def extract_twitter_fallback(url: str) -> Optional[dict]:
    """
    Cơ chế dự phòng trích xuất media Twitter/X qua vxtwitter / fxtwitter API
    khi yt-dlp gặp lỗi 'No video could be found' do giới hạn guest token với bài NSFW/nhạy cảm
    hoặc khi bài đăng là bài chứa hình ảnh tĩnh / album ảnh.
    """
    m = RE_TWITTER.match(url)
    if not m:
        return None
    tweet_id = m.group(1)

    api_endpoints = [
        f"https://api.vxtwitter.com/Twitter/status/{tweet_id}",
        f"https://api.fxtwitter.com/Twitter/status/{tweet_id}",
    ]
    headers = {"User-Agent": "TelegramBot (like TwitterBot)"}

    for api_url in api_endpoints:
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    raw_data = resp.read()
                    data = json.loads(raw_data.decode("utf-8", errors="ignore"))
                    media_list = data.get("media_extended") or []
                    video_media = [
                        item for item in media_list if item.get("type") in ("video", "gif")
                    ]
                    if not video_media and data.get("mediaURLs"):
                        mp4_urls = [u for u in data["mediaURLs"] if ".mp4" in u.lower()]
                        if mp4_urls:
                            video_media = [{"url": mp4_urls[0], "type": "video"}]

                    if video_media:
                        vm = video_media[0]
                        direct_url = vm.get("url")
                        if not direct_url:
                            continue
                        thumb = vm.get("thumbnail_url") or data.get("user_profile_image_url")
                        dur_sec = (vm.get("duration_millis") or 0) / 1000.0 if vm.get("duration_millis") else None
                        w = vm.get("size", {}).get("width")
                        h = vm.get("size", {}).get("height")

                        formats = [{
                            "url": direct_url,
                            "ext": "mp4",
                            "width": w,
                            "height": h,
                            "vcodec": "h264",
                            "acodec": "aac",
                            "format_id": "direct_http",
                        }]

                        uploader = (
                            data.get("user_name")
                            or data.get("user_screen_name")
                            or "Twitter"
                        )
                        return {
                            "id": tweet_id,
                            "title": data.get("text") or f"Tweet {tweet_id}",
                            "uploader": uploader,
                            "channel": data.get("user_screen_name"),
                            "duration": dur_sec,
                            "thumbnail": thumb,
                            "formats": formats,
                            "url": direct_url,
                            "extractor": "twitter",
                            "subtitles": {},
                            "automatic_captions": {},
                            "_is_fallback": True,
                        }

                    image_media = [
                        item for item in media_list if item.get("type") == "image"
                    ]
                    if not image_media and data.get("mediaURLs"):
                        image_media = [{"url": u, "type": "image"} for u in data["mediaURLs"] if not (".mp4" in u.lower())]

                    if image_media:
                        all_img_urls: list[str] = []
                        for im in image_media:
                            raw_u = im.get("url")
                            if raw_u:
                                upgraded = upgrade_twitter_image_url(raw_u, prefer_png=True)
                                if upgraded not in all_img_urls:
                                    all_img_urls.append(upgraded)

                        if all_img_urls:
                            best_img_url = all_img_urls[0]
                            uploader = (
                                data.get("user_name")
                                or data.get("user_screen_name")
                                or "Twitter"
                            )
                            img_ext = "png" if "format=png" in best_img_url else "jpg"
                            is_album = len(all_img_urls) > 1
                            return {
                                "id": tweet_id,
                                "title": data.get("text") or f"Twitter Photo {tweet_id}",
                                "uploader": uploader,
                                "channel": data.get("user_screen_name"),
                                "media_type": "album" if is_album else "image",
                                "media_url": best_img_url,
                                "images": all_img_urls,
                                "thumbnail": best_img_url,
                                "ext": img_ext,
                                "extractor": "twitter",
                                "_is_fallback": True,
                            }
        except Exception:
            continue
    return None
