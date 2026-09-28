#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Playlist & Album Extraction Engine (YouTube, Spotify, Zing MP3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None  # type: ignore[assignment,misc]

from utils.constants import MAX_PLAYLIST_ITEMS
from extractors.spotify import resolve_spotify_playlist_or_album


def is_playlist_url(url: str) -> tuple[bool, str]:
    """
    Xác định URL có phải là Playlist / Album hay không.
    Trả về (is_playlist, platform_code).
    """
    if not url or not isinstance(url, str):
        return False, ""

    url = url.strip()
    if ("youtube.com" in url or "music.youtube.com" in url) and (
        "playlist?list=" in url or "&list=" in url or "?list=" in url
    ):
        return True, "youtube"

    if "spotify.com" in url and ("/playlist/" in url or "/album/" in url):
        return True, "spotify"

    if "zingmp3.vn" in url and ("/album/" in url or "/playlist/" in url):
        return True, "zingmp3"

    return False, ""


def extract_youtube_playlist(
    url: str,
    max_items: int = MAX_PLAYLIST_ITEMS,
    cookie_browser: Optional[str] = None,
    cookie_file: Optional[str] = None,
) -> tuple[dict, list[dict]]:
    """Trích xuất danh sách video từ Playlist YouTube mà không tải dữ liệu."""
    if YoutubeDL is None:
        return {}, []
    opts: dict = {
        "extract_flat": True,
        "quiet": True,
        "noplaylist": False,
        "playlist_items": f"1:{max_items}",
        "socket_timeout": 15,
        "ignoreerrors": True,
    }
    if cookie_browser:
        opts["cookiesfrombrowser"] = (cookie_browser,)
    elif cookie_file and Path(cookie_file).is_file():
        opts["cookiefile"] = str(cookie_file)

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {}, []

        playlist_title = info.get("title") or "YouTube Playlist"
        playlist_author = info.get("uploader") or info.get("channel") or "Không rõ"
        entries = []
        raw_entries = info.get("entries") or []
        for e in raw_entries:
            if not e:
                continue
            vid_id = e.get("id")
            vid_url = e.get("url") or (f"https://www.youtube.com/watch?v={vid_id}" if vid_id else "")
            if not vid_url:
                continue
            entries.append({
                "id": vid_id or "",
                "url": vid_url,
                "title": e.get("title") or f"Video {vid_id}",
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or playlist_author,
                "platform": "YouTube",
                "target": "youtube",
            })
        meta = {
            "title": playlist_title,
            "author": playlist_author,
            "total": len(entries),
            "thumbnail": info.get("thumbnail"),
        }
        return meta, entries
    except Exception:
        return {}, []


def extract_zingmp3_playlist(
    url: str,
    max_items: int = MAX_PLAYLIST_ITEMS,
) -> tuple[dict, list[dict]]:
    """Trích xuất danh sách bài hát từ Zing MP3 Album / Playlist."""
    if YoutubeDL is None:
        return {}, []
    opts = {
        "extract_flat": True,
        "quiet": True,
        "noplaylist": False,
        "playlist_items": f"1:{max_items}",
        "socket_timeout": 15,
        "ignoreerrors": True,
    }
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {}, []
        playlist_title = info.get("title") or "Zing MP3 Album"
        playlist_author = info.get("uploader") or info.get("artist") or "Không rõ"
        entries = []
        for e in (info.get("entries") or []):
            if not e:
                continue
            vid_url = e.get("url") or e.get("webpage_url") or ""
            if not vid_url:
                continue
            entries.append({
                "id": e.get("id") or "",
                "url": vid_url,
                "title": e.get("title") or "Bài hát Zing MP3",
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or playlist_author,
                "platform": "Zing MP3",
                "target": "zingmp3",
            })
        meta = {
            "title": playlist_title,
            "author": playlist_author,
            "total": len(entries),
            "thumbnail": info.get("thumbnail"),
        }
        return meta, entries
    except Exception:
        return {}, []


def extract_playlist_items(
    url: str,
    target: str,
    max_items: int = MAX_PLAYLIST_ITEMS,
    cookie_browser: Optional[str] = None,
    cookie_file: Optional[str] = None,
) -> tuple[dict, list[dict]]:
    """Hàm điều phối trích xuất playlist theo nền tảng mục tiêu."""
    if target == "youtube" or "youtube.com" in url or "youtu.be" in url:
        return extract_youtube_playlist(url, max_items, cookie_browser, cookie_file)
    elif target == "spotify" or "spotify.com" in url:
        return resolve_spotify_playlist_or_album(url, max_items)
    elif target == "zingmp3" or "zingmp3.vn" in url:
        return extract_zingmp3_playlist(url, max_items)
    return {}, []
