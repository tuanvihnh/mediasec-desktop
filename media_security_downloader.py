#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Media Security Audit & Downloader
===================================
Facade entrypoint maintained for backward compatibility.
Modularized architecture:
  ├── app_gui/       # Tkinter GUI, components, event handlers
  ├── core/          # AuditEngine, Security scanner, Queue manager
  ├── extractors/    # Twitter, Pinterest, Facebook, Booru, Spotify, Playlists...
  ├── image_engine/  # Master Resolution, Color Restore, AI Upscale
  ├── utils/         # Helpers: Network, Magic bytes, System permissions
  └── main.py        # Primary entry point
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Re-exports from utils ─────────────────────────────────────────────────────
from utils.constants import (
    APP_TITLE,
    APP_VERSION,
    STATUS_READY,
    STATUS_CONNECTING,
    STATUS_AUDITING,
    STATUS_DRM,
    STATUS_COMPLETED,
    STATUS_ERROR,
    STATUS_DENIED,
    MAGIC_BYTES,
    SAFE_EXTENSIONS,
    MAX_FILESIZE_BYTES,
    MIN_FREE_DISK_BYTES,
    MAX_FILE_SIZE_BYTES,
    MIN_DISK_FREE_BYTES,
    RE_TWITTER,
    RE_TIKTOK,
    RE_INSTAGRAM,
    RE_BILIBILI,
    RE_REDDIT,
    RE_YOUTUBE,
    RE_FACEBOOK,
    RE_LOCAL_STREAM,
    RE_SPOTIFY,
    RE_ZINGMP3,
    SUPPORTED_BROWSERS,
    CLIPBOARD_CHECK_INTERVAL_MS,
    MAX_CLIPBOARD_LENGTH,
    MAX_QUEUE_SIZE,
    MAX_PLAYLIST_ITEMS,
    PAUSE_TIMEOUT_SECONDS,
    POST_ACTIONS,
    QUEUE_WAITING,
    QUEUE_DOWNLOADING,
    QUEUE_COMPLETED,
    QUEUE_ERROR,
    QUEUE_CANCELLED,
)

from utils.helpers import (
    format_duration,
    parse_time_to_seconds,
    format_bytes,
    clean_ansi_escape,
    create_placeholder_thumbnail,
    load_thumbnail_pil,
    safe_open_path,
    safe_notify,
    log_info,
    log_warn,
    log_err,
)

from utils.security import (
    preflight_disk_check,
    harden_file_permissions,
    compute_file_sha256,
    cleanup_temp_files,
    validate_file_integrity,
    validate_downloaded_files,
    detect_drm_mpd,
    detect_drm_hls,
    check_cleartext_warning,
)

from utils.network import (
    is_safe_remote_url,
    is_direct_image_url,
    is_direct_media_url,
    is_rule34_url,
    is_iwara_url,
    is_telegram_url,
    is_pinterest_url,
    auto_detect_platform,
    fetch_manifest,
    download_direct_file,
)

# ── PIL / Pillow Re-exports ───────────────────────────────────────────────────
try:
    from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageSequence, ImageFilter, ImageOps, ImageCms
    HAS_PIL = True
    HAS_IMAGETK = True
except ImportError:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageSequence, ImageFilter, ImageOps, ImageCms
        HAS_PIL = True
        HAS_IMAGETK = False
        ImageTk = None
    except ImportError:
        HAS_PIL = False
        HAS_IMAGETK = False
        Image = None
        ImageTk = None

# ── Re-exports from image_engine ──────────────────────────────────────────────
from image_engine.metadata import (
    lossless_strip_jpeg_metadata,
    lossless_strip_png_metadata,
    lossless_strip_webp_metadata,
    lossless_strip_image_file_metadata,
)

from image_engine.color_restore import (
    restore_image_color_and_sharpness,
)

from image_engine.ai_upscaler import (
    detect_ai_upscale_engine,
    install_realesrgan_engine,
    run_ai_super_resolution,
)

from image_engine.processor import (
    process_downloaded_image,
)

# ── Re-exports from extractors ────────────────────────────────────────────────
from extractors.subtitles import (
    parse_sub_content,
    translate_texts_batch,
    translate_subtitles_file,
)

from extractors.twitter import (
    upgrade_twitter_image_url,
    extract_twitter_fallback,
)

from extractors.spotify import (
    resolve_spotify_track,
    resolve_spotify_playlist_or_album,
)

from extractors.playlist import (
    is_playlist_url,
    extract_youtube_playlist,
    extract_zingmp3_playlist,
    extract_playlist_items,
)

from extractors.pinterest import (
    upgrade_pinimg_url,
    resolve_pinterest_media,
)

from extractors.direct import (
    resolve_direct_image_info,
)

from extractors.booru import (
    resolve_rule34_post,
)

from extractors.telegram import (
    resolve_telegram_media,
)

from extractors.facebook import (
    resolve_facebook_photo,
)

# ── Re-exports from core & app_gui ────────────────────────────────────────────
from core.audit_engine import AuditEngine
from core.queue_manager import DownloadQueueManager
from app_gui.app import App


def main() -> None:
    """Khởi chạy ứng dụng Media Security Downloader GUI."""
    try:
        app = App()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
