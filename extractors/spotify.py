#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify Metadata Extractor (Tracks, Albums, Playlists via public embed API).
"""

from __future__ import annotations

import re
import json
from typing import Optional
import urllib.request

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from utils.constants import MAX_PLAYLIST_ITEMS


def resolve_spotify_track(url: str) -> Optional[dict]:
    """
    Trích xuất metadata bài hát Spotify (Tên bài, Ca sĩ, Thời lượng, Thumbnail).
    Sử dụng kỹ thuật spotDL: Lấy thông tin từ Spotify Embed công khai,
    không cần tài khoản Premium, không cần API Key.
    """
    m = re.search(r"spotify\.com/(?:intl-[a-z]{2}/)?track/([a-zA-Z0-9]+)", url)
    if not m:
        return None
    track_id = m.group(1)

    embed_url = f"https://open.spotify.com/embed/track/{track_id}"
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            )
        }
        if HAS_REQUESTS:
            resp = requests.get(embed_url, timeout=10, headers=headers)
            html = resp.text
        else:
            req = urllib.request.Request(embed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read().decode("utf-8", errors="ignore")

        m_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if m_data:
            data = json.loads(m_data.group(1))
            entity = (
                data.get("props", {})
                .get("pageProps", {})
                .get("state", {})
                .get("data", {})
                .get("entity", {})
            )
            title = entity.get("name") or entity.get("title")
            artists = [a.get("name") for a in entity.get("artists", []) if a.get("name")]
            duration = (entity.get("duration") or 0) / 1000.0 if entity.get("duration") else None
            cover_art = entity.get("visualIdentity", {}).get("image", [{}])
            thumbnail = cover_art[0].get("url") if cover_art else None
            if title:
                return {
                    "id": track_id,
                    "title": title,
                    "artists": artists,
                    "duration": duration,
                    "thumbnail": thumbnail,
                }
    except Exception:
        pass

    try:
        oembed_url = f"https://open.spotify.com/oembed?url=https://open.spotify.com/track/{track_id}"
        if HAS_REQUESTS:
            r = requests.get(oembed_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                data = r.json()
                title = data.get("title")
                thumbnail = data.get("thumbnail_url")
                if title:
                    return {
                        "id": track_id,
                        "title": title,
                        "artists": [],
                        "duration": None,
                        "thumbnail": thumbnail,
                    }
        else:
            req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode("utf-8"))
                title = data.get("title")
                thumbnail = data.get("thumbnail_url")
                if title:
                    return {
                        "id": track_id,
                        "title": title,
                        "artists": [],
                        "duration": None,
                        "thumbnail": thumbnail,
                    }
    except Exception:
        pass

    return None


def resolve_spotify_playlist_or_album(
    url: str,
    max_items: int = MAX_PLAYLIST_ITEMS,
) -> tuple[dict, list[dict]]:
    """Trích xuất danh sách bài hát từ Spotify Playlist hoặc Album qua Embed JSON."""
    m = re.search(r"spotify\.com/(?:intl-[a-z]{2}/)?(playlist|album)/([a-zA-Z0-9]+)", url)
    if not m:
        return {}, []
    p_type, p_id = m.group(1), m.group(2)
    embed_url = f"https://open.spotify.com/embed/{p_type}/{p_id}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
    }
    try:
        if HAS_REQUESTS:
            resp = requests.get(embed_url, timeout=10, headers=headers)
            html = resp.text
        else:
            req = urllib.request.Request(embed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as r:
                html = r.read().decode("utf-8", errors="ignore")

        m_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
        if not m_data:
            return {}, []

        data = json.loads(m_data.group(1))
        entity = (
            data.get("props", {})
            .get("pageProps", {})
            .get("state", {})
            .get("data", {})
            .get("entity", {})
        )
        title = entity.get("name") or entity.get("title") or f"Spotify {p_type.capitalize()}"
        subtitle = entity.get("subtitle") or entity.get("type", "Spotify")
        cover_art = entity.get("visualIdentity", {}).get("image", [{}])
        thumbnail = cover_art[0].get("url") if cover_art else None

        track_list = entity.get("trackList", [])
        entries = []
        for t in track_list[:max_items]:
            uri = t.get("uri") or ""
            t_id = uri.split(":")[-1] if ":" in uri else ""
            t_url = f"https://open.spotify.com/track/{t_id}" if t_id else ""
            t_title = t.get("title") or "Unknown Track"
            t_artist = t.get("subtitle") or subtitle
            dur = (t.get("duration") or 0) / 1000.0 if t.get("duration") else None
            if t_url:
                entries.append({
                    "id": t_id,
                    "url": t_url,
                    "title": f"{t_artist} - {t_title}" if t_artist else t_title,
                    "duration": dur,
                    "uploader": t_artist,
                    "platform": "Spotify",
                    "target": "spotify",
                })
        meta = {
            "title": title,
            "author": subtitle,
            "thumbnail": thumbnail,
            "total": len(entries),
        }
        return meta, entries
    except Exception:
        return {}, []
