#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Constants & Whitelists for Media Security Downloader.
"""

from __future__ import annotations

import re

APP_TITLE = "Media Security Audit & Downloader"
APP_VERSION = "3.9.0"
MAX_FILESIZE_BYTES = 500 * 1024 * 1024  # 500 MB
MIN_FREE_DISK_BYTES = 100 * 1024 * 1024  # 100 MB – tối thiểu còn trống
MAX_FILE_SIZE_BYTES = MAX_FILESIZE_BYTES
MIN_DISK_FREE_BYTES = MIN_FREE_DISK_BYTES

# Filename template chống Path Traversal – dùng ID định danh, không dùng
# metadata không kiểm soát từ server
SAFE_OUTTMPL = "%(extractor)s_%(id)s.%(ext)s"

# ── Regex Whitelist cho Input Validation & Auto-Detection ─────────────────────
RE_TWITTER = re.compile(
    r"^https?://(?:(?:www\.|mobile\.)?(?:twitter\.com|x\.com))/(?:[a-zA-Z0-9_]+/status/|i/status/)(\d+)(?:\?.*)?$"
)
# Hỗ trợ video đơn, shorts, live, embed VÀ danh sách phát (Playlist)
RE_YOUTUBE = re.compile(
    r"^https?://(?:(?:www|m|music)\.)?(?:"
    r"youtube\.com/(?:watch\?(?:[^#\s]*&)?(?:v=[a-zA-Z0-9_-]{11}|list=[a-zA-Z0-9_-]+)|shorts/[a-zA-Z0-9_-]{11}|live/[a-zA-Z0-9_-]{11}|embed/[a-zA-Z0-9_-]{11}|playlist\?(?:[^#\s]*&)?list=[a-zA-Z0-9_-]+)|"
    r"youtu\.be/([a-zA-Z0-9_-]{11})"
    r")(?:[&?#].*)?$"
)
RE_YOUTUBE_PLAYLIST = re.compile(
    r"^https?://(?:(?:www|m|music)\.)?youtube\.com/(?:playlist\?(?:[^#\s]*&)?list=|watch\?(?:[^#\s]*&)?list=)([a-zA-Z0-9_-]+)(?:[&?#].*)?$"
)
RE_FACEBOOK = re.compile(
    r"^https?://(?:(?:www|m|web|mbasic|vi-vn|en-gb|[a-z]{2}-[a-z]{2})\.)?"
    r"(?:facebook\.com|fb\.watch|fb\.com)"
    r"/(?:"
    r"(?:[a-zA-Z0-9.]+/(?:videos|posts|photos)/[a-zA-Z0-9._/?&=-]+)"
    r"|(?:photo(?:\.php|/)?)"
    r"|(?:watch/?\?v=\d+)"
    r"|(?:reel/\d+)"
    r"|(?:share/[vr]/[a-zA-Z0-9_-]+)"
    r"|(?:video\.php\?v=\d+)"
    r"|(?:story\.php\?story_fbid=\d+)"
    r"|(?:\d+/videos/\d+)"
    r")"
    r"(?:[?&/#].*)?$",
    re.IGNORECASE,
)
RE_TIKTOK = re.compile(
    r"^https?://(?:(?:www|m|vt|vm)\.)?tiktok\.com/(?:@[^/]+/video/\d+|v/\d+|t/\w+|[\w-]+)(?:[?&/#].*)?$",
    re.IGNORECASE,
)
RE_INSTAGRAM = re.compile(
    r"^https?://(?:www\.)?(?:instagram\.com|instagr\.am)/(?:p|reel|tv)/[a-zA-Z0-9_-]+(?:[?&/#].*)?$",
    re.IGNORECASE,
)
RE_REDDIT = re.compile(
    r"^https?://(?:(?:www|old|new|v)\.)?(?:reddit\.com/r/[^/]+/comments/\w+|redd\.it/\w+|v\.redd\.it/\w+)(?:[?&/#].*)?$",
    re.IGNORECASE,
)
RE_BILIBILI = re.compile(
    r"^https?://(?:(?:www\.)?bilibili\.com/(?:video/(?:BV|av)[a-zA-Z0-9]+|bangumi/play/\w+)|b23\.tv/[a-zA-Z0-9]+)(?:[?&/#].*)?$",
    re.IGNORECASE,
)
RE_ZINGMP3 = re.compile(
    r"^https?://(?:(?:www|mp3)\.)?(?:zingmp3\.vn|zingmp3\.com)"
    r"/(?:bai-hat|video-clip|album|playlist|embed)"
    r"/[a-zA-Z0-9._-]+"
    r"/[a-zA-Z0-9]+\.html"
    r"(?:[?&#].*)?$"
)
RE_SPOTIFY = re.compile(
    r"^https?://(?:open\.)?spotify\.com"
    r"/(?:intl-[a-z]{2}/)?"
    r"(?:track|album|playlist|episode|show)"
    r"/[a-zA-Z0-9]+"
    r"(?:[?&#].*)?$"
)
RE_IWARA = re.compile(
    r"^https?://(?:(?:www|ecchi)\.)?iwara\.tv/(?:video|videos|playlist|profile)/[a-zA-Z0-9_-]+(?:/.*)?$",
    re.IGNORECASE,
)
RE_RULE34 = re.compile(
    r"^https?://(?:(?:www|api|wimg|us|api-cdn)\.)?(?:rule34\.xxx|rule34video\.com|rule34\.paheal\.net)"
    r"/(?:index\.php\?page=post&s=view&id=\d+|videos?/\d+|post/view/\d+|images/|thumbnails/).*$",
    re.IGNORECASE,
)
RE_BOORU_OTHER = re.compile(
    r"^https?://(?:(?:www|safebooru|gelbooru|danbooru)\.)?(?:gelbooru\.com|danbooru\.donmai\.us|safebooru\.org|yande\.re|konachan\.com|e-shuushuu\.net)"
    r"/(?:index\.php\?page=post&s=view&id=\d+|posts/\d+|post/show/\d+|images/|data/).*$",
    re.IGNORECASE,
)
RE_TELEGRAM = re.compile(
    r"^https?://(?:(?:www\.)?(?:t\.me|telegram\.me|telegram\.dog)/[a-zA-Z0-9_+/-]+(?:\?.*)?|telesco\.pe/[a-zA-Z0-9_-]+)",
    re.IGNORECASE,
)
RE_PINTEREST = re.compile(
    r"^https?://(?:(?:www|[a-z]{2})\.)?pinterest\.(?:com|co\.[a-z]+|[a-z]{2})/(?:pin/\d+|[\w-]+/[\w-]+)|^https?://pin\.it/[a-zA-Z0-9]+|^https?://i\.pinimg\.com/[^/]+/.+",
    re.IGNORECASE,
)
RE_LOCAL_STREAM = re.compile(
    r"^https?://(?:localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|[a-zA-Z0-9.-]+)"
    r"(?::\d+)?/.*?\.(m3u8|mpd)(?:\?.*)?$"
)

# Danh sách phần mở rộng hình ảnh & media hợp lệ
SUPPORTED_IMAGE_EXTS = (
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "svg", "ico", "jfif", "jng", "tiff", "tif"
)
SUPPORTED_MEDIA_EXTS = (
    "mp4", "webm", "mkv", "mov", "avi", "flv", "ts", "m4v",
    "mp3", "m4a", "wav", "aac", "flac", "opus", "ogg"
)

# ── DRM UUIDs (MPEG-DASH ContentProtection) ──────────────────────────────────
DRM_UUIDS = {
    "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed": "Widevine",
    "9a04f079-9840-4286-ab92-e65be0885f95": "PlayReady",
    "e2719d58-a985-b3c9-781a-b030af78d30e": "ClearKey (W3C)",
    "1077efec-c0b2-4d02-ace3-3c1e52e2fb4b": "ClearKey (cenc)",
    "94ce86fb-07ff-4f43-adb8-93d2fa968ca2": "FairPlay",
}

# ── Cookie / Browser support ──────────────────────────────────────────────────
SUPPORTED_BROWSERS = ["firefox", "chrome", "chromium", "edge", "opera", "brave", "vivaldi", "safari"]

# ── UX & Automation Constants ─────────────────────────────────────────────────
MAX_QUEUE_SIZE = 50                    # Giới hạn hàng đợi chống DoS
MAX_PLAYLIST_ITEMS = 50                # Giới hạn tối đa bài hát/video trong playlist chống DoS
CLIPBOARD_CHECK_INTERVAL_MS = 1500     # Tần suất kiểm tra clipboard (ms)
MAX_CLIPBOARD_LENGTH = 2048            # Giới hạn độ dài clipboard chống buffer overflow
PAUSE_TIMEOUT_SECONDS = 1800           # 30 phút auto-cancel khi tạm dừng

# ── Safe File Extensions Whitelist (chống mã độc) ────────────────────────────
SAFE_EXTENSIONS = frozenset({
    "mp4", "mkv", "webm", "mov", "avi", "flv", "ts", "m4v",  # Video
    "mp3", "m4a", "wav", "flac", "opus", "ogg", "aac",        # Audio
    "srt", "vtt", "ass",                                       # Subtitles
    "jpg", "jpeg", "png", "webp", "gif", "bmp", "svg", "ico",  # Images
    "jfif", "jng", "tiff", "tif",                              # Images (kèm jng)
    "part", "temp", "ytdl",                                    # yt-dlp temp files
})

# ── Dangerous Magic Headers (Chữ ký thực thi nhị phân cần chặn) ───────────────
DANGEROUS_MAGIC_HEADERS = [
    (b"\x7fELF", "Linux ELF Binary / Executable"),
    (b"MZ", "Windows PE Executable (.exe / .dll)"),
    (b"\xca\xfe\xba\xbe", "Compiled Java Class Bytecode"),
    (b"\xfe\xed\xfa\xce", "Mach-O Binary Executable (32-bit)"),
    (b"\xcf\xfa\xed\xfe", "Mach-O Binary Executable (64-bit)"),
    (b"#!", "Shell Script / Shebang Executable"),
]

# ── Magic Bytes Signatures (File Integrity Validation) ────────────────────────
MAGIC_BYTES_MAP: dict[str, list[bytes]] = {
    "mp4":  [b"\x00\x00\x00", b"ftyp"],  # ftyp box tại offset 4
    "m4a":  [b"\x00\x00\x00", b"ftyp"],
    "mkv":  [b"\x1a\x45\xdf\xa3"],        # EBML header
    "webm": [b"\x1a\x45\xdf\xa3"],
    "mov":  [b"\x00\x00\x00", b"moov", b"mdat", b"wide"],
    "avi":  [b"RIFF"],
    "flv":  [b"FLV"],
    "ts":   [b"\x47"],
    "mp3":  [b"\xff\xfb", b"\xff\xf3", b"\xff\xf2", b"ID3"],
    "wav":  [b"RIFF"],
    "flac": [b"fLaC"],
    "opus": [b"OggS"],
    "ogg":  [b"OggS"],
    "jpg":  [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "jfif": [b"\xff\xd8\xff"],
    "png":  [b"\x89PNG"],
    "jng":  [b"\x8bJNG"],                 # JNG magic header
    "gif":  [b"GIF87a", b"GIF89a"],       # GIF magic header
    "webp": [b"RIFF"],                    # RIFF....WEBP
    "bmp":  [b"BM"],                      # BMP magic header
    "ico":  [b"\x00\x00\x01\x00"],        # ICO magic header
    "tiff": [b"II*\x00", b"MM\x00*"],
    "tif":  [b"II*\x00", b"MM\x00*"],
}
MAGIC_BYTES = MAGIC_BYTES_MAP

# ── Post-Download Action Options ──────────────────────────────────────────────
POST_ACTIONS = [
    "Không làm gì (Mặc định)",
    "📂 Mở thư mục chứa file",
    "▶️ Mở file bằng trình phát mặc định",
    "🔔 Gửi thông báo hệ thống (notify-send)",
    "📂 Mở thư mục + 🔔 Thông báo",
]

# ── Download Queue Item States ────────────────────────────────────────────────
QUEUE_WAITING     = "⏳ Chờ"
QUEUE_DOWNLOADING = "⬇ Tải"
QUEUE_COMPLETED   = "✅ Xong"
QUEUE_ERROR       = "❌ Lỗi"
QUEUE_PAUSED      = "⏸ Dừng"
QUEUE_CANCELLED   = "🚫 Hủy"

# Trạng thái giao diện
STATUS_READY = "Sẵn sàng"
STATUS_CONNECTING = "Đang kết nối…"
STATUS_AUDITING = "Đang kiểm thử…"
STATUS_DRM = "⚠ DRM Protected"
STATUS_DENIED = "⛔ Access Denied"
STATUS_COMPLETED = "✅ Hoàn tất"
STATUS_ERROR = "❌ Lỗi"
