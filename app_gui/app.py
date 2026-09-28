#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App GUI Module for ToolDowMp4
Tkinter Native GUI implementation.
"""

from __future__ import annotations

import io
import os
import queue
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Third-party (yt-dlp Python API)
try:
    from yt_dlp import YoutubeDL
except ImportError:
    YoutubeDL = None  # type: ignore[assignment,misc]

# PIL / Pillow
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
    HAS_IMAGETK = True
except ImportError:
    try:
        from PIL import Image
        HAS_PIL = True
        HAS_IMAGETK = False
        ImageTk = None
    except ImportError:
        HAS_PIL = False
        HAS_IMAGETK = False
        Image = None
        ImageTk = None

# Modular imports
from utils.constants import (
    APP_TITLE,
    APP_VERSION,
    CLIPBOARD_CHECK_INTERVAL_MS,
    MAX_CLIPBOARD_LENGTH,
    MAX_PLAYLIST_ITEMS,
    MAX_QUEUE_SIZE,
    PAUSE_TIMEOUT_SECONDS,
    POST_ACTIONS,
    QUEUE_CANCELLED,
    QUEUE_COMPLETED,
    QUEUE_DOWNLOADING,
    QUEUE_ERROR,
    QUEUE_WAITING,
    RE_BILIBILI,
    RE_FACEBOOK,
    RE_INSTAGRAM,
    RE_LOCAL_STREAM,
    RE_REDDIT,
    RE_SPOTIFY,
    RE_TIKTOK,
    RE_TWITTER,
    RE_YOUTUBE,
    RE_ZINGMP3,
    SAFE_EXTENSIONS,
    STATUS_AUDITING,
    STATUS_COMPLETED,
    STATUS_CONNECTING,
    STATUS_DENIED,
    STATUS_DRM,
    STATUS_ERROR,
    STATUS_READY,
    SUPPORTED_BROWSERS,
)
from utils.helpers import (
    clean_ansi_escape,
    create_placeholder_thumbnail,
    format_bytes,
    format_duration,
    load_thumbnail_pil,
    safe_notify,
    safe_open_path,
)
from utils.security import (
    cleanup_temp_files,
    compute_file_sha256,
    preflight_disk_check,
    validate_downloaded_files,
)
from utils.network import (
    auto_detect_platform,
    is_direct_image_url,
    is_direct_media_url,
    is_iwara_url,
    is_pinterest_url,
    is_rule34_url,
    is_safe_remote_url,
    is_telegram_url,
)
from extractors import (
    extract_playlist_items,
    extract_twitter_fallback,
    is_playlist_url,
    resolve_direct_image_info,
    resolve_facebook_photo,
    resolve_pinterest_media,
    resolve_rule34_post,
    resolve_spotify_playlist_or_album,
    resolve_spotify_track,
    resolve_telegram_media,
)
from image_engine import (
    detect_ai_upscale_engine,
    install_realesrgan_engine,
)
from core import AuditEngine
import tempfile
from utils.config import load_config, save_config
from utils.logger import get_logger
from utils.cleanup import cleanup_stale_artifacts
from app_gui.theme import apply_theme, detect_system_theme


class App(tk.Tk):
    """Giao diện chính Native GUI của Media Security Downloader."""

    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} v{APP_VERSION}")
        self.geometry("860x920")
        self.minsize(780, 720)
        self.resizable(True, True)

        # ── Cấu hình & Logging & Dọn dẹp khởi động ────────────────────────
        self._config = load_config()
        self.logger = get_logger()
        self.logger.info("Khởi động ToolDowMp4 v%s", APP_VERSION)

        # Dọn dẹp tệp tạm mồ côi ngầm không chặn giao diện
        threading.Thread(
            target=cleanup_stale_artifacts,
            args=([self._config.get("save_dir", ""), tempfile.gettempdir()],),
            daemon=True,
        ).start()

        # Biến trạng thái
        self._running = False
        self._analyzing = False
        self._current_info: Optional[dict] = None
        self._photo_ref: Optional[tk.PhotoImage] = None

        # ── UX & Automation: State Variables ──────────────────────────────
        # Clipboard Monitor
        self._clipboard_monitoring = False
        self._last_clipboard: str = ""
        self._clipboard_after_id: Optional[str] = None

        # Download Queue
        self._download_queue: list[dict] = []  # [{url, target, status, title}]
        self._queue_processing = False
        self._current_queue_index: int = -1

        # Pause / Resume / Cancel
        self._pause_event = threading.Event()
        self._pause_event.set()  # Mặc định: đang chạy (not paused)
        self._cancel_event = threading.Event()
        self._pause_start_time: Optional[float] = None
        self._pause_timeout_after_id: Optional[str] = None

        # Post-download tracking
        self._last_downloaded_dir: Optional[str] = None
        self._last_downloaded_prefix: Optional[str] = None

        # Thread-safe UI dispatch queue (tương thích hoàn hảo Python 3.14+)
        self._ui_queue: queue.Queue = queue.Queue()
        self._process_ui_queue()

        # Khởi tạo Theme
        self.var_theme = tk.StringVar(value=self._config.get("theme_mode", "dark"))
        self._palette = apply_theme(self, self.var_theme.get())

        self._build_ui()

        # Đồng bộ màu Canvas sau khi xây dựng UI
        self.canvas.configure(background=self._palette["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_window_close)

    def _process_ui_queue(self) -> None:
        """Xử lý các tác vụ UI được gửi từ worker thread lên Main loop."""
        while not self._ui_queue.empty():
            try:
                fn, args, kwargs = self._ui_queue.get_nowait()
                fn(*args, **kwargs)
            except queue.Empty:
                break
            except Exception:
                pass
        self.after(35, self._process_ui_queue)

    def ui_dispatch(self, fn: callable, *args, **kwargs) -> None:  # type: ignore[type-arg]
        """Đưa callback vào hàng đợi an toàn để thực thi trên luồng giao diện chính."""
        self._ui_queue.put((fn, args, kwargs))

    def _build_ui(self) -> None:
        # Wrapper Canvas với thanh cuộn dọc chống tràn trên mọi độ phân giải màn hình
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll_content = ttk.Frame(self.canvas)

        self.scroll_content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window(
            (0, 0), window=self.scroll_content, anchor="nw"
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Căn chỉnh chiều rộng của scroll_content theo canvas khi resize
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width),
        )

        # Mousewheel binding
        def _on_mousewheel(event):
            if event.num == 4:
                self.canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self.canvas.yview_scroll(1, "units")
            else:
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        self.bind_all("<Button-4>", _on_mousewheel)
        self.bind_all("<Button-5>", _on_mousewheel)
        self.bind_all("<MouseWheel>", _on_mousewheel)

        pad = {"padx": 12, "pady": 5}

        # ── 1. Header ─────────────────────────────────────────────────────
        hdr = ttk.Frame(self.scroll_content)
        hdr.pack(fill="x", **pad)
        ttk.Label(
            hdr,
            text=f"🔒 {APP_TITLE}",
            font=("Sans", 14, "bold"),
        ).pack(side="left")

        # Nút chuyển đổi Theme (Sáng / Tối)
        self.btn_theme = ttk.Button(
            hdr,
            text="🌙 Tối" if self.var_theme.get() == "dark" else "☀️ Sáng",
            width=7,
            command=self._toggle_theme,
        )
        self.btn_theme.pack(side="right", padx=(8, 0))

        # Clipboard Monitor Toggle (mặc định từ cấu hình)
        self.var_clipboard_monitor = tk.BooleanVar(value=self._config.get("clipboard_monitor", False))
        self.chk_clipboard = ttk.Checkbutton(
            hdr,
            text="📋 Clipboard Monitor",
            variable=self.var_clipboard_monitor,
            command=self._toggle_clipboard_monitor,
        )
        self.chk_clipboard.pack(side="right", padx=(8, 0))

        # Tự động nạp vào hàng đợi khi copy link
        self.var_auto_queue = tk.BooleanVar(value=self._config.get("auto_queue", False))
        self.chk_auto_queue = ttk.Checkbutton(
            hdr,
            text="⚡ Auto-Queue",
            variable=self.var_auto_queue,
        )
        self.chk_auto_queue.pack(side="right", padx=(8, 0))

        ttk.Label(
            hdr,
            text=f"v{APP_VERSION} (Multi-Image & AI Core)",
            font=("Sans", 9),
            foreground="#666",
        ).pack(side="right")

        ttk.Separator(self.scroll_content, orient="horizontal").pack(fill="x", padx=12)

        # ── 2. Target & URL Frame ─────────────────────────────────────────
        frm_url = ttk.LabelFrame(self.scroll_content, text="Liên kết & Nền tảng", padding=8)
        frm_url.pack(fill="x", **pad)

        ttk.Label(frm_url, text="Mục tiêu:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.var_target = tk.StringVar(value=self._config.get("target", "YouTube"))
        self.cmb_target = ttk.Combobox(
            frm_url,
            textvariable=self.var_target,
            values=[
                "YouTube",
                "Twitter / X",
                "Facebook",
                "TikTok",
                "Instagram",
                "Reddit",
                "Bilibili",
                "Pinterest (Pin & Image)",
                "Rule34 / Booru (Image & Video)",
                "Iwara (iwara.tv)",
                "Telegram (t.me)",
                "Zing MP3",
                "Spotify",
                "Hình ảnh trực tiếp (PNG/JPG/GIF...)",
                "Media trực tiếp (MP4/WebM/MP3...)",
                "Local Lab / Custom Stream (HLS/DASH)",
                "Nền tảng khác / Universal (yt-dlp)",
            ],
            state="readonly",
            width=38,
        )
        self.cmb_target.grid(row=0, column=1, sticky="w", pady=(0, 6))
        self.cmb_target.bind("<<ComboboxSelected>>", self._on_target_changed)

        ttk.Label(frm_url, text="URL Media:").grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.var_url = tk.StringVar()
        self.ent_url = ttk.Entry(frm_url, textvariable=self.var_url, width=42)
        self.ent_url.grid(row=1, column=1, sticky="ew", padx=(0, 6))
        self.ent_url.bind("<Return>", lambda e: self._on_analyze())

        # ── Auto-detect URL: Gắn sự kiện thay đổi nội dung URL ──────────
        self.var_url.trace_add("write", self._on_url_changed)

        # Hàng nút điều khiển cạnh URL
        btn_bar = ttk.Frame(frm_url)
        btn_bar.grid(row=1, column=2, sticky="e")

        btn_paste = ttk.Button(btn_bar, text="📋 Dán", width=7, command=self._paste_url)
        btn_paste.pack(side="left", padx=2)

        self.btn_analyze = ttk.Button(
            btn_bar, text="🔍 Phân tích Video", width=16, command=self._on_analyze
        )
        self.btn_analyze.pack(side="left", padx=2)

        btn_clear = ttk.Button(
            btn_bar, text="✕ Xóa", width=6, command=self._on_clear_url
        )
        btn_clear.pack(side="left", padx=2)

        frm_url.columnconfigure(1, weight=1)

        self.lbl_url_hint = ttk.Label(
            frm_url, text="", foreground="#666", font=("Sans", 8)
        )
        self.lbl_url_hint.grid(row=2, column=1, columnspan=2, sticky="w", pady=(3, 0))

        # ── 3. Media Info & Thumbnail Preview Frame ────────────────────────
        self.frm_info = ttk.LabelFrame(
            self.scroll_content, text="ℹ️ Thông tin Media & Xem trước Ảnh bìa (Thumbnail)", padding=8
        )
        self.frm_info.pack(fill="x", **pad)

        # Cột ảnh thumbnail (160x90 px cố định)
        self.lbl_thumb_preview = tk.Label(
            self.frm_info,
            bg="#222222",
            relief="solid",
            borderwidth=1,
        )
        self.lbl_thumb_preview.grid(row=0, column=0, rowspan=5, padx=(0, 12), sticky="n")
        # Khởi tạo ngay với thumbnail placeholder (160x90)
        self._display_thumbnail(None, fallback_text="No Thumbnail")

        # Cột thông tin chi tiết
        self.lbl_info_title = ttk.Label(
            self.frm_info, text="📌 Tiêu đề: (Chưa phân tích)", font=("Sans", 9, "bold"), wraplength=540
        )
        self.lbl_info_title.grid(row=0, column=1, sticky="w", pady=1)

        self.lbl_info_author = ttk.Label(
            self.frm_info, text="👤 Tác giả / Kênh: -", font=("Sans", 9)
        )
        self.lbl_info_author.grid(row=1, column=1, sticky="w", pady=1)

        self.lbl_info_duration = ttk.Label(
            self.frm_info, text="⏱️ Thời lượng: -", font=("Sans", 9)
        )
        self.lbl_info_duration.grid(row=2, column=1, sticky="w", pady=1)

        self.lbl_info_subs = ttk.Label(
            self.frm_info, text="💬 Phụ đề phát hiện: -", font=("Sans", 9), foreground="#1565c0"
        )
        self.lbl_info_subs.grid(row=3, column=1, sticky="w", pady=1)

        self.lbl_info_status = ttk.Label(
            self.frm_info,
            text="💡 Nhập URL và bấm 'Phân tích Video' để nhận diện chi tiết.",
            font=("Sans", 8),
            foreground="#555",
            wraplength=540,
        )
        self.lbl_info_status.grid(row=4, column=1, sticky="w", pady=1)

        self.frm_info.columnconfigure(1, weight=1)

        # ── 4. Main Configuration Control (2 Columns Grid) ────────────────
        frm_configs = ttk.Frame(self.scroll_content)
        frm_configs.pack(fill="x", **pad)

        # ── Cột Trái: Quality & Format Control ────────────────────────────
        self.frm_quality = ttk.LabelFrame(
            frm_configs, text="🎛️ Chất lượng & Định dạng (Quality & Format)", padding=8
        )
        self.frm_quality.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # Hàng 0: Chế độ Video vs Audio vs Image
        ttk.Label(self.frm_quality, text="Chế độ tải:").grid(row=0, column=0, sticky="w", pady=3)
        self.var_media_mode = tk.StringVar(value=self._config.get("media_mode", "video"))
        frm_mode = ttk.Frame(self.frm_quality)
        frm_mode.grid(row=0, column=1, sticky="w", pady=3)
        ttk.Radiobutton(
            frm_mode, text="🎬 Video", value="video", variable=self.var_media_mode, command=self._update_mode_ui
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            frm_mode, text="🎵 Audio", value="audio", variable=self.var_media_mode, command=self._update_mode_ui
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            frm_mode, text="🖼️ Hình ảnh", value="image", variable=self.var_media_mode, command=self._update_mode_ui
        ).pack(side="left")

        # ── Sub-frame: Video / Audio Configuration ────────────────────────
        self.frm_quality_video = ttk.Frame(self.frm_quality)
        self.frm_quality_video.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(3, 0))
        self.frm_quality_video.columnconfigure(1, weight=1)

        # Video Hàng 0: Định dạng xuất (Container)
        self.lbl_container = ttk.Label(self.frm_quality_video, text="Định dạng xuất:")
        self.lbl_container.grid(row=0, column=0, sticky="w", pady=3)
        self.var_container = tk.StringVar(value=self._config.get("video_format", "MP4 (.mp4 - Chuẩn)"))
        self.cmb_container = ttk.Combobox(
            self.frm_quality_video,
            textvariable=self.var_container,
            values=["MP4 (.mp4 - Chuẩn)", "MKV (.mkv - Đa phụ đề)", "WEBM (.webm)"],
            state="readonly",
            width=24,
        )
        self.cmb_container.grid(row=0, column=1, sticky="ew", pady=3)

        # Video Hàng 1: Tùy chọn Độ phân giải chi tiết
        self.lbl_res = ttk.Label(self.frm_quality_video, text="Độ phân giải:")
        self.lbl_res.grid(row=1, column=0, sticky="w", pady=3)
        self.var_video_res = tk.StringVar(value=self._config.get("video_resolution", "Tốt nhất / Tự động (Cao nhất)"))
        self.cmb_video_res = ttk.Combobox(
            self.frm_quality_video,
            textvariable=self.var_video_res,
            values=[
                "Tốt nhất / Tự động (Cao nhất)",
                "2160p (4K UHD)",
                "1440p (2K QHD)",
                "1080p (Full HD)",
                "720p (HD)",
                "480p (SD)",
                "360p (Tiết kiệm dung lượng)",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_video_res.grid(row=1, column=1, sticky="ew", pady=3)

        # Video Hàng 2: Audio Bitrate
        self.lbl_bitrate = ttk.Label(self.frm_quality_video, text="Audio Bitrate:")
        self.lbl_bitrate.grid(row=2, column=0, sticky="w", pady=3)
        self.var_audio_bitrate = tk.StringVar(value=self._config.get("audio_bitrate", "192 kbps (Tiêu chuẩn cao)"))
        self.cmb_audio_bitrate = ttk.Combobox(
            self.frm_quality_video,
            textvariable=self.var_audio_bitrate,
            values=[
                "320 kbps (Cực cao - Studio)",
                "256 kbps (Rất cao)",
                "192 kbps (Tiêu chuẩn cao)",
                "128 kbps (Phổ thông)",
                "96 kbps (Tiết kiệm dung lượng)",
                "Tự động (Best Stream)",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_audio_bitrate.grid(row=2, column=1, sticky="ew", pady=3)

        # Video / Audio Hàng 3: Cắt đoạn (Time Range Clip Grabber)
        self.lbl_clip_trim = ttk.Label(self.frm_quality_video, text="Cắt đoạn (Trim):")
        self.lbl_clip_trim.grid(row=3, column=0, sticky="w", pady=3)
        self.frm_trim = ttk.Frame(self.frm_quality_video)
        self.frm_trim.grid(row=3, column=1, sticky="w", pady=3)

        ttk.Label(self.frm_trim, text="Từ:").pack(side="left")
        self.var_clip_start = tk.StringVar(value="")
        self.ent_clip_start = ttk.Entry(self.frm_trim, textvariable=self.var_clip_start, width=9)
        self.ent_clip_start.pack(side="left", padx=(3, 8))

        ttk.Label(self.frm_trim, text="Đến:").pack(side="left")
        self.var_clip_end = tk.StringVar(value="")
        self.ent_clip_end = ttk.Entry(self.frm_trim, textvariable=self.var_clip_end, width=9)
        self.ent_clip_end.pack(side="left", padx=(3, 8))

        self.lbl_trim_hint = ttk.Label(
            self.frm_trim,
            text="(vd: 01:30 - 02:45 hoặc 45s)",
            foreground="#666",
            font=("Sans", 8),
        )
        self.lbl_trim_hint.pack(side="left")

        def _clear_trim():
            self.var_clip_start.set("")
            self.var_clip_end.set("")

        self.btn_clear_trim = ttk.Button(
            self.frm_trim,
            text="✖",
            width=2,
            command=_clear_trim,
        )
        self.btn_clear_trim.pack(side="left", padx=(6, 0))

        self.lbl_quality_note = ttk.Label(
            self.frm_quality_video,
            text="💡 Để trống ô Cắt đoạn để tải toàn bộ. Danh sách độ phân giải sẽ tự động nạp chính xác.",
            foreground="#666",
            font=("Sans", 8),
        )
        self.lbl_quality_note.grid(row=4, column=0, columnspan=2, sticky="w", pady=(4, 0))

        # ── Sub-frame: Image Configuration (Chuyên sâu Pillow) ─────────────
        self.frm_quality_image = ttk.Frame(self.frm_quality)
        self.frm_quality_image.columnconfigure(1, weight=1)

        # Image Hàng 0: Original/Master Resolution
        self.lbl_img_res = ttk.Label(self.frm_quality_image, text="Độ phân giải:")
        self.lbl_img_res.grid(row=0, column=0, sticky="w", pady=3)
        self.var_img_res = tk.StringVar(value=self._config.get("img_res", "Gốc / Master (Original 100%)"))
        self.cmb_img_res = ttk.Combobox(
            self.frm_quality_image,
            textvariable=self.var_img_res,
            values=[
                "Gốc / Master (Original 100%)",
                "Tối ưu hóa ảnh (HD Sharpness)",
                "AI Super-Resolution (x2 / 2K)",
                "AI Super-Resolution (x4 / 4K)",
                "Phóng to 2x (Lanczos Super-Res)",
                "Thu nhỏ 50% (Tiết kiệm bộ nhớ)",
                "Chuẩn 4K UHD (Tối đa 3840x2160)",
                "Chuẩn 2K QHD (Tối đa 2560x1440)",
                "Chuẩn Full HD (Tối đa 1920x1080)",
                "Chuẩn HD (Tối đa 1280x720)",
                "Ảnh đại diện / Avatar (512x512)",
                "Ảnh bìa Banner (1200x630)",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_img_res.grid(row=0, column=1, sticky="ew", pady=3)

        # Image Hàng 1: Format Transcoding via Pillow
        self.lbl_img_transcode = ttk.Label(self.frm_quality_image, text="Định dạng xuất:")
        self.lbl_img_transcode.grid(row=1, column=0, sticky="w", pady=3)
        self.var_img_transcode = tk.StringVar(value=self._config.get("img_transcode", "Gốc (Giữ nguyên định dạng gốc)"))
        self.cmb_img_transcode = ttk.Combobox(
            self.frm_quality_image,
            textvariable=self.var_img_transcode,
            values=[
                "Gốc (Giữ nguyên định dạng gốc)",
                "PNG (.png - Không nén Lossless)",
                "JPEG (.jpg - Phổ biến & Nhẹ)",
                "WEBP (.webp - Siêu tối ưu Web)",
                "GIF (.gif - Động / Tĩnh)",
                "BMP (.bmp - Bitmap không nén)",
                "ICO (.ico - Biểu tượng Icon)",
                "TIFF (.tiff - Chất lượng in ấn)",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_img_transcode.grid(row=1, column=1, sticky="ew", pady=3)

        # Image Hàng 2: Image Compression
        self.lbl_img_compress = ttk.Label(self.frm_quality_image, text="Chất lượng nén:")
        self.lbl_img_compress.grid(row=2, column=0, sticky="w", pady=3)
        self.var_img_compress = tk.StringVar(value=self._config.get("img_compress", "100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)"))
        self.cmb_img_compress = ttk.Combobox(
            self.frm_quality_image,
            textvariable=self.var_img_compress,
            values=[
                "100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)",
                "92% (Chất lượng rất cao - Giảm nhẹ dung lượng)",
                "85% (Tiêu chuẩn cân bằng)",
                "75% (Tối ưu dung lượng Web)",
                "60% (Dung lượng siêu nhẹ)",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_img_compress.grid(row=2, column=1, sticky="ew", pady=3)

        self.lbl_img_quality_note = ttk.Label(
            self.frm_quality_image,
            text="💡 Chuẩn Bit-Exact 100%: Bảo toàn 99-100% độ sắc nét gốc máy chủ (Zero Generational Loss).",
            foreground="#2e7d32",
            font=("Sans", 8),
        )
        self.lbl_img_quality_note.grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.frm_quality.columnconfigure(1, weight=1)

        # ── Cột Phải: Subtitles & Thumbnail Control ───────────────────────
        self.frm_sub_thumb = ttk.LabelFrame(
            frm_configs, text="💬 Phụ đề & 🖼️ Ảnh bìa (Subtitles & Thumbnail)", padding=8
        )
        self.frm_sub_thumb.pack(side="right", fill="both", expand=True, padx=(6, 0))

        # ── Sub-frame: Video Subtitles & Thumbnail ────────────────────────
        self.frm_subs_video = ttk.Frame(self.frm_sub_thumb)
        self.frm_subs_video.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.frm_subs_video.columnconfigure(1, weight=1)

        # Checkbox Tải phụ đề
        self.var_enable_subs = tk.BooleanVar(value=True)
        self.chk_enable_subs = ttk.Checkbutton(
            self.frm_subs_video,
            text="Tải phụ đề kèm theo (Subtitles)",
            variable=self.var_enable_subs,
            command=self._update_subs_ui,
        )
        self.chk_enable_subs.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 3))

        # Ngôn ngữ phụ đề / Dịch
        self.lbl_sub_lang = ttk.Label(self.frm_subs_video, text="Dịch / Ngôn ngữ:")
        self.lbl_sub_lang.grid(row=1, column=0, sticky="w", pady=3)
        self.var_sub_lang = tk.StringVar(value="🇻🇳 Dịch sang Tiếng Việt (Vietnamese)")
        self.cmb_sub_lang = ttk.Combobox(
            self.frm_subs_video,
            textvariable=self.var_sub_lang,
            values=[
                "🇻🇳 Dịch sang Tiếng Việt (Vietnamese)",
                "🇬🇧 Dịch sang Tiếng Anh (English)",
                "🇻🇳🇬🇧 Cả Tiếng Việt & Tiếng Anh (2 file .srt)",
                "Gốc (Nguyên bản phụ đề của video)",
                "Tất cả các ngôn ngữ có sẵn",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_sub_lang.grid(row=1, column=1, sticky="ew", pady=3)

        # Checkbox Nhúng phụ đề vào video
        self.var_embed_subs = tk.BooleanVar(value=False)
        self.chk_embed_subs = ttk.Checkbutton(
            self.frm_subs_video,
            text="Nhúng phụ đề trực tiếp vào video (Embed Subtitle)",
            variable=self.var_embed_subs,
        )
        self.chk_embed_subs.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 6))

        ttk.Separator(self.frm_subs_video, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=4
        )

        # Checkbox Thumbnail
        self.var_enable_thumb = tk.BooleanVar(value=True)
        self.chk_enable_thumb = ttk.Checkbutton(
            self.frm_subs_video,
            text="Tải và lưu file ảnh bìa (Thumbnail: .jpg)",
            variable=self.var_enable_thumb,
        )
        self.chk_enable_thumb.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)

        self.var_embed_thumb = tk.BooleanVar(value=True)
        self.chk_embed_thumb = ttk.Checkbutton(
            self.frm_subs_video,
            text="Nhúng ảnh bìa vào file media (Cover Art)",
            variable=self.var_embed_thumb,
        )
        self.chk_embed_thumb.grid(row=5, column=0, columnspan=2, sticky="w", pady=2)

        # ── Sub-frame: Image Tools & Snapshot ─────────────────────────────
        self.frm_subs_image = ttk.Frame(self.frm_sub_thumb)
        self.frm_subs_image.columnconfigure(1, weight=1)

        # Hàng 0: Frame Grabber / Snapshot
        self.lbl_img_frame_grabber = ttk.Label(self.frm_subs_image, text="Frame Grabber:")
        self.lbl_img_frame_grabber.grid(row=0, column=0, sticky="w", pady=3)
        self.var_img_frame_grabber = tk.StringVar(value="Tắt (Giữ nguyên toàn bộ tệp)")
        self.cmb_img_frame_grabber = ttk.Combobox(
            self.frm_subs_image,
            textvariable=self.var_img_frame_grabber,
            values=[
                "Tắt (Giữ nguyên toàn bộ tệp)",
                "Trích xuất Frame đầu tiên (Poster Snapshot)",
                "Bóc tách toàn bộ khung hình (Burst Extract all frames)",
            ],
            state="readonly",
            width=24,
        )
        self.cmb_img_frame_grabber.grid(row=0, column=1, sticky="ew", pady=3)

        # Hàng 1: HD Sharpness & Color Restoration
        self.var_img_hd_sharpness = tk.BooleanVar(value=self._config.get("img_hd_sharpness", True))
        self.chk_img_hd_sharpness = ttk.Checkbutton(
            self.frm_subs_image,
            text="✨ Tối ưu hóa ảnh (HD Sharpness & Khôi phục màu sắc)",
            variable=self.var_img_hd_sharpness,
        )
        self.chk_img_hd_sharpness.grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 2))

        # Hàng 2: AI Super-Resolution (x2/x4 Detail)
        self.var_img_ai_upscale = tk.BooleanVar(value=self._config.get("img_ai_upscale", False))
        self.chk_img_ai_upscale = ttk.Checkbutton(
            self.frm_subs_image,
            text="🚀 Bật AI Super-Resolution (x2/x4 Detail)",
            variable=self.var_img_ai_upscale,
            command=self._on_ai_upscale_toggled,
        )
        self.chk_img_ai_upscale.grid(row=2, column=0, columnspan=2, sticky="w", pady=2)

        # Hàng 3: Engine status & 1-Click Installer
        self.frm_ai_engine = ttk.Frame(self.frm_subs_image)
        self.frm_ai_engine.grid(row=3, column=0, columnspan=2, sticky="ew", padx=(20, 0), pady=(0, 2))

        self.lbl_ai_engine_status = ttk.Label(
            self.frm_ai_engine,
            text="",
            foreground="#2e7d32",
            font=("Sans", 8),
        )
        self.lbl_ai_engine_status.pack(side="left", fill="x", expand=True)

        self.btn_install_ai = ttk.Button(
            self.frm_ai_engine,
            text="📥 Tải Real-ESRGAN GPU (~45MB)",
            command=self._on_install_ai_engine,
        )
        self.btn_install_ai.pack(side="right", padx=(4, 0))

        # Hàng 4: Xóa siêu dữ liệu riêng tư (EXIF / GPS) nhưng BẢO TOÀN ICC
        self.var_img_strip_exif = tk.BooleanVar(value=self._config.get("img_strip_exif", True))
        self.chk_img_strip_exif = ttk.Checkbutton(
            self.frm_subs_image,
            text="🛡️ Bảo mật: Xóa siêu dữ liệu EXIF / GPS (Bảo toàn ICC)",
            variable=self.var_img_strip_exif,
        )
        self.chk_img_strip_exif.grid(row=4, column=0, columnspan=2, sticky="w", pady=2)

        # Hàng 5: Tối ưu hóa bảng màu (Palette Optimization)
        self.var_img_palette_opt = tk.BooleanVar(value=self._config.get("img_palette_opt", True))
        self.chk_img_palette_opt = ttk.Checkbutton(
            self.frm_subs_image,
            text="⚡ Tối ưu hóa dung lượng (Palette Optimize)",
            variable=self.var_img_palette_opt,
        )
        self.chk_img_palette_opt.grid(row=5, column=0, columnspan=2, sticky="w", pady=2)

        # Hàng 6: Tạo ảnh thu nhỏ riêng lẻ
        self.var_img_create_thumb = tk.BooleanVar(value=self._config.get("img_create_thumb", False))
        self.chk_img_create_thumb = ttk.Checkbutton(
            self.frm_subs_image,
            text="🖼️ Tạo ảnh thu nhỏ riêng lẻ (Thumbnail .thumb.jpg)",
            variable=self.var_img_create_thumb,
        )
        self.chk_img_create_thumb.grid(row=6, column=0, columnspan=2, sticky="w", pady=2)

        # Hàng 7: Tải trọn bộ Album / Carousel ảnh (Twitter, Telegram, Facebook)
        self.var_img_download_all = tk.BooleanVar(value=self._config.get("img_download_all", True))
        self.chk_img_download_all = ttk.Checkbutton(
            self.frm_subs_image,
            text="📚 Tải trọn bộ Album / Carousel ảnh (Twitter, Telegram, Facebook)",
            variable=self.var_img_download_all,
        )
        self.chk_img_download_all.grid(row=7, column=0, columnspan=2, sticky="w", pady=2)

        # Hàng 8: Ghi chú
        ttk.Label(
            self.frm_subs_image,
            text="💡 Tự động nâng cấp ảnh gốc Master Twitter/Pinterest & khôi phục màu sắc.",
            foreground="#1565c0",
            font=("Sans", 8),
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.frm_sub_thumb.columnconfigure(1, weight=1)

        # ── 5. Cookie Authentication (Collapsible) ────────────────────────
        self.frm_cookie = ttk.LabelFrame(
            self.scroll_content, text="🍪 Tùy chọn Cookie / Xác thực", padding=8
        )
        self.frm_cookie.pack(fill="x", **pad)

        ttk.Label(self.frm_cookie, text="Phương thức:").grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.var_cookie_method = tk.StringVar(value="Không dùng (Mặc định)")
        self.cmb_cookie_method = ttk.Combobox(
            self.frm_cookie,
            textvariable=self.var_cookie_method,
            values=["Không dùng (Mặc định)", "Từ trình duyệt (Browser)", "Từ file cookies.txt"],
            state="readonly",
            width=22,
        )
        self.cmb_cookie_method.grid(row=0, column=1, sticky="w")
        self.cmb_cookie_method.bind("<<ComboboxSelected>>", self._update_cookie_ui)

        self.lbl_cookie_browser = ttk.Label(self.frm_cookie, text="Trình duyệt:")
        self.lbl_cookie_browser.grid(row=0, column=2, sticky="w", padx=(15, 5))
        self.var_cookie_browser = tk.StringVar(value="firefox")
        self.cmb_cookie_browser = ttk.Combobox(
            self.frm_cookie,
            textvariable=self.var_cookie_browser,
            values=SUPPORTED_BROWSERS,
            state="readonly",
            width=12,
        )
        self.cmb_cookie_browser.grid(row=0, column=3, sticky="w")

        self.var_cookie_file = tk.StringVar()
        self.ent_cookie_file = ttk.Entry(
            self.frm_cookie, textvariable=self.var_cookie_file, width=38
        )
        self.btn_cookie_browse = ttk.Button(
            self.frm_cookie, text="📄 Chọn file", width=12, command=self._browse_cookie_file
        )
        self.ent_cookie_file.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(5, 0))
        self.btn_cookie_browse.grid(row=1, column=3, sticky="w", padx=(5, 0), pady=(5, 0))

        self.lbl_cookie_hint = ttk.Label(
            self.frm_cookie,
            text="Tải công khai qua Guest API (không cần tài khoản, phù hợp video công khai)",
            foreground="#666",
            font=("Sans", 8),
        )
        self.lbl_cookie_hint.grid(row=2, column=0, columnspan=4, sticky="w", pady=(4, 0))

        self.lbl_cookie_browser.grid_remove()
        self.cmb_cookie_browser.grid_remove()
        self.ent_cookie_file.grid_remove()
        self.btn_cookie_browse.grid_remove()

        self.frm_cookie.columnconfigure(1, weight=1)

        # ── 6. Save Directory ─────────────────────────────────────────────
        frm_save = ttk.LabelFrame(self.scroll_content, text="Thư mục lưu trữ", padding=8)
        frm_save.pack(fill="x", **pad)

        saved_dir = self._config.get("save_dir")
        if saved_dir and Path(saved_dir).is_dir():
            default_save = saved_dir
        else:
            default_save = str(Path.home() / "Downloads")
            if not Path(default_save).is_dir():
                default_save = str(Path.home())
        self.var_save = tk.StringVar(value=default_save)

        self.ent_save = ttk.Entry(frm_save, textvariable=self.var_save, width=55)
        self.ent_save.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        btn_browse = ttk.Button(
            frm_save, text="📁 Chọn thư mục", width=14, command=self._browse_dir
        )
        btn_browse.grid(row=0, column=1)

        self.lbl_disk = ttk.Label(frm_save, text="", foreground="#555", font=("Sans", 8))
        self.lbl_disk.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))
        self._update_disk_info()
        self.var_save.trace_add("write", lambda *_: self._update_disk_info())

        frm_save.columnconfigure(0, weight=1)

        # ── 7. Post-Download Actions ──────────────────────────────────────
        frm_post = ttk.LabelFrame(
            self.scroll_content, text="🎬 Hành động sau khi tải xong (Post-Download)", padding=8
        )
        frm_post.pack(fill="x", **pad)

        ttk.Label(frm_post, text="Hành động:").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.var_post_action = tk.StringVar(value=self._config.get("post_action", POST_ACTIONS[0]))
        self.cmb_post_action = ttk.Combobox(
            frm_post,
            textvariable=self.var_post_action,
            values=POST_ACTIONS,
            state="readonly",
            width=38,
        )
        self.cmb_post_action.grid(row=0, column=1, sticky="ew", padx=(0, 6))

        # Checkbox quét bảo mật sau tải
        self.var_security_scan = tk.BooleanVar(value=True)
        self.chk_security_scan = ttk.Checkbutton(
            frm_post,
            text="🛡️ Quét bảo mật file sau tải (Magic Bytes & Extension Check)",
            variable=self.var_security_scan,
        )
        self.chk_security_scan.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))

        frm_post.columnconfigure(1, weight=1)

        # ── 8. Download Queue ─────────────────────────────────────────────
        frm_queue = ttk.LabelFrame(
            self.scroll_content, text=f"📥 Hàng đợi & Danh sách phát (Download Queue – Tối đa {MAX_QUEUE_SIZE})", padding=8
        )
        frm_queue.pack(fill="x", **pad)

        # Treeview hiển thị hàng đợi chi tiết
        q_cols = ("stt", "title", "platform", "duration", "status")
        self.tree_queue = ttk.Treeview(
            frm_queue, columns=q_cols, show="headings", height=5, selectmode="browse"
        )
        self.tree_queue.heading("stt", text="#")
        self.tree_queue.heading("title", text="Tiêu đề / Tên bài hát")
        self.tree_queue.heading("platform", text="Nền tảng")
        self.tree_queue.heading("duration", text="Thời lượng")
        self.tree_queue.heading("status", text="Trạng thái")
        self.tree_queue.column("stt", width=35, anchor="center", stretch=False)
        self.tree_queue.column("title", width=330, anchor="w")
        self.tree_queue.column("platform", width=95, anchor="center")
        self.tree_queue.column("duration", width=75, anchor="center")
        self.tree_queue.column("status", width=85, anchor="center")
        self.tree_queue.pack(fill="x", pady=(0, 5))

        # Hàng nút 1: Quản lý thêm mục vào hàng đợi
        frm_queue_btns1 = ttk.Frame(frm_queue)
        frm_queue_btns1.pack(fill="x", pady=(0, 3))

        self.btn_add_queue = ttk.Button(
            frm_queue_btns1, text="➕ Thêm URL", width=14, command=self._add_to_queue
        )
        self.btn_add_queue.pack(side="left", padx=(0, 4))

        self.btn_add_playlist = ttk.Button(
            frm_queue_btns1, text="📋 Nhập Playlist", width=15, command=self._add_playlist_to_queue
        )
        self.btn_add_playlist.pack(side="left", padx=(0, 4))

        self.btn_import_file = ttk.Button(
            frm_queue_btns1, text="📁 Nhập File .txt", width=15, command=self._import_urls_from_file
        )
        self.btn_import_file.pack(side="left", padx=(0, 4))

        self.btn_retry_failed = ttk.Button(
            frm_queue_btns1, text="🔄 Thử lại lỗi", width=13, command=self._retry_failed_queue
        )
        self.btn_retry_failed.pack(side="left", padx=(0, 4))

        self.lbl_queue_info = ttk.Label(
            frm_queue_btns1, text="0 mục", foreground="#666", font=("Sans", 8)
        )
        self.lbl_queue_info.pack(side="right")

        # Hàng nút 2: Điều chỉnh thứ tự & dọn dẹp hàng đợi
        frm_queue_btns2 = ttk.Frame(frm_queue)
        frm_queue_btns2.pack(fill="x")

        self.btn_queue_up = ttk.Button(
            frm_queue_btns2, text="🔼 Lên", width=7, command=lambda: self._move_queue_item(-1)
        )
        self.btn_queue_up.pack(side="left", padx=(0, 4))

        self.btn_queue_down = ttk.Button(
            frm_queue_btns2, text="🔽 Xuống", width=8, command=lambda: self._move_queue_item(1)
        )
        self.btn_queue_down.pack(side="left", padx=(0, 4))

        self.btn_remove_queue = ttk.Button(
            frm_queue_btns2, text="➖ Xóa mục", width=11, command=self._remove_from_queue
        )
        self.btn_remove_queue.pack(side="left", padx=(0, 4))

        self.btn_clean_done = ttk.Button(
            frm_queue_btns2, text="🧹 Dọn xong", width=11, command=self._clean_completed_queue
        )
        self.btn_clean_done.pack(side="left", padx=(0, 4))

        self.btn_clear_queue = ttk.Button(
            frm_queue_btns2, text="🗑️ Xóa tất cả", width=11, command=self._clear_queue
        )
        self.btn_clear_queue.pack(side="left", padx=(0, 4))

        # ── 9. Progress & Action ──────────────────────────────────────────
        frm_prog = ttk.LabelFrame(self.scroll_content, text="Tiến trình & Trạng thái", padding=8)
        frm_prog.pack(fill="x", **pad)

        self.progress = ttk.Progressbar(frm_prog, mode="indeterminate", length=400)
        self.progress.pack(fill="x")

        self.lbl_status = ttk.Label(
            frm_prog,
            text=STATUS_READY,
            font=("Sans", 10, "bold"),
            foreground="#2e7d32",
        )
        self.lbl_status.pack(pady=(4, 0))

        # ── Nút điều khiển: Bắt đầu / Tạm dừng / Hủy ────────────────────
        frm_btn = ttk.Frame(self.scroll_content)
        frm_btn.pack(fill="x", **pad)

        self.btn_start = ttk.Button(
            frm_btn,
            text="🚀 BẮT ĐẦU TẢI VỀ",
            command=self._on_start,
            style="Accent.TButton",
        )
        self.btn_start.pack(side="left", fill="x", expand=True, ipady=7, padx=(0, 4))

        self.btn_start_queue = ttk.Button(
            frm_btn,
            text="📥 TẢI HÀNG ĐỢI",
            command=self._start_queue_processing,
            style="Queue.TButton",
        )
        self.btn_start_queue.pack(side="left", ipady=7, padx=(0, 4))

        self.btn_pause = ttk.Button(
            frm_btn,
            text="⏸️ Tạm dừng",
            command=self._on_pause_resume,
            state="disabled",
            width=12,
        )
        self.btn_pause.pack(side="left", ipady=7, padx=(0, 4))

        self.btn_cancel = ttk.Button(
            frm_btn,
            text="🚫 Hủy",
            command=self._on_cancel_download,
            state="disabled",
            width=10,
        )
        self.btn_cancel.pack(side="left", ipady=7)

        # Style nút
        style = ttk.Style()
        style.configure(
            "Accent.TButton",
            font=("Sans", 11, "bold"),
            foreground="#ffffff",
            background="#1565c0",
        )
        style.map(
            "Accent.TButton",
            background=[("active", "#0d47a1"), ("disabled", "#90a4ae")],
        )
        style.configure(
            "Queue.TButton",
            font=("Sans", 10, "bold"),
            foreground="#ffffff",
            background="#2e7d32",
        )
        style.map(
            "Queue.TButton",
            background=[("active", "#1b5e20"), ("disabled", "#90a4ae")],
        )

        # Footer
        ttk.Separator(self.scroll_content, orient="horizontal").pack(fill="x", padx=12, pady=(6, 2))
        ttk.Label(
            self.scroll_content,
            text="⚠ Chỉ sử dụng cho mục đích kiểm thử an toàn luồng truyền thông hợp pháp hoặc lưu trữ nội dung công khai cá nhân.",
            font=("Sans", 8),
            foreground="#b71c1c",
            wraplength=760,
        ).pack(padx=12, pady=(2, 10))

        self._on_target_changed()
        self._update_mode_ui()
        self._update_subs_ui()
        self._update_ai_engine_status_display()

    # ── UI State Updates ──────────────────────────────────────────────────
    def _update_mode_ui(self) -> None:
        """Cập nhật giao diện khi chuyển đổi giữa Video, Audio và Hình ảnh."""
        mode = self.var_media_mode.get()
        if mode == "image":
            # Chuyển đổi khung Quality sang Image Quality & Transcoding
            self.frm_quality.config(text="🖼️ Xử lý & Định dạng Ảnh (Image Quality & Transcoding)")
            self.frm_quality_video.grid_remove()
            self.frm_quality_image.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(3, 0))

            # Chuyển đổi khung Subtitles sang Image Tools & Snapshot
            self.frm_sub_thumb.config(text="📸 Công cụ & Trích xuất Ảnh (Image Tools & Snapshot)")
            self.frm_subs_video.grid_remove()
            self.frm_subs_image.grid(row=0, column=0, columnspan=2, sticky="nsew")

            self._update_ai_engine_status_display()

            if hasattr(self, "btn_analyze") and not self._analyzing:
                self.btn_analyze.config(text="🔍 Phân tích Ảnh")
            if hasattr(self, "btn_start") and not self._running:
                self.btn_start.config(text="🚀 BẮT ĐẦU TẢI VỀ")

        elif mode == "video":
            # Khôi phục khung Quality video
            self.frm_quality.config(text="🎛️ Chất lượng & Định dạng (Quality & Format)")
            self.frm_quality_image.grid_remove()
            self.frm_quality_video.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(3, 0))

            # Khôi phục khung Subtitles video
            self.frm_sub_thumb.config(text="💬 Phụ đề & 🖼️ Ảnh bìa (Subtitles & Thumbnail)")
            self.frm_subs_image.grid_remove()
            self.frm_subs_video.grid(row=0, column=0, columnspan=2, sticky="nsew")

            self.lbl_container.config(text="Định dạng xuất:")
            self.cmb_container["values"] = [
                "MP4 (.mp4 - Chuẩn)",
                "MKV (.mkv - Đa phụ đề)",
                "WEBM (.webm)",
            ]
            self.var_container.set("MP4 (.mp4 - Chuẩn)")
            self.lbl_res.config(state="normal")
            self.cmb_video_res.config(state="readonly")
            self.lbl_bitrate.config(state="normal")
            self.chk_embed_subs.config(state="normal" if self.var_enable_subs.get() else "disabled")

            if hasattr(self, "btn_analyze") and not self._analyzing:
                self.btn_analyze.config(text="🔍 Phân tích Video")

        else:  # "audio"
            # Khôi phục khung Quality audio
            self.frm_quality.config(text="🎛️ Chất lượng & Định dạng (Quality & Format)")
            self.frm_quality_image.grid_remove()
            self.frm_quality_video.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(3, 0))

            # Khôi phục khung Subtitles video (ẩn phụ đề)
            self.frm_sub_thumb.config(text="💬 Phụ đề & 🖼️ Ảnh bìa (Subtitles & Thumbnail)")
            self.frm_subs_image.grid_remove()
            self.frm_subs_video.grid(row=0, column=0, columnspan=2, sticky="nsew")

            self.lbl_container.config(text="Định dạng âm thanh:")
            self.cmb_container["values"] = [
                "MP3 (.mp3 - Phổ biến)",
                "M4A (.m4a - Chuẩn Apple/AAC)",
                "WAV (.wav - Không nén)",
                "FLAC (.flac - Lossless)",
                "OPUS (.opus - Tiết kiệm)",
            ]
            self.var_container.set("MP3 (.mp3 - Phổ biến)")
            self.lbl_res.config(state="disabled")
            self.cmb_video_res.config(state="disabled")
            self.lbl_bitrate.config(state="normal")
            self.chk_embed_subs.config(state="disabled")

            if hasattr(self, "btn_analyze") and not self._analyzing:
                self.btn_analyze.config(text="🔍 Phân tích Audio")

    def _update_subs_ui(self) -> None:
        """Kích hoạt/vô hiệu hóa các điều khiển phụ đề."""
        enabled = self.var_enable_subs.get()
        if enabled:
            self.lbl_sub_lang.config(state="normal")
            self.cmb_sub_lang.config(state="readonly")
            if self.var_media_mode.get() == "video":
                self.chk_embed_subs.config(state="normal")
        else:
            self.lbl_sub_lang.config(state="disabled")
            self.cmb_sub_lang.config(state="disabled")
            self.chk_embed_subs.config(state="disabled")

    def _update_ai_engine_status_display(self) -> None:
        """Cập nhật hiển thị trạng thái và nút cài đặt Engine AI."""
        if not hasattr(self, "lbl_ai_engine_status") or not hasattr(self, "btn_install_ai"):
            return
        eng_type, eng_bin = detect_ai_upscale_engine()
        is_checked = self.var_img_ai_upscale.get()
        if eng_type == "realesrgan-ncnn-vulkan":
            bin_name = os.path.basename(eng_bin) if eng_bin else "GPU"
            if is_checked:
                self.lbl_ai_engine_status.config(
                    text=f"⚡ Vulkan GPU ({bin_name})",
                    foreground="#2e7d32",
                )
            else:
                self.lbl_ai_engine_status.config(
                    text="⚡ Real-ESRGAN GPU sẵn sàng",
                    foreground="#2e7d32",
                )
            self.btn_install_ai.config(text="🔄 Cài lại GPU", state="normal")
        elif eng_type == "onnxruntime":
            self.lbl_ai_engine_status.config(
                text="⚡ Engine: ONNX Neural Engine",
                foreground="#2e7d32",
            )
            self.btn_install_ai.config(text="📥 Tải GPU (~45MB)", state="normal")
        else:
            if is_checked:
                self.lbl_ai_engine_status.config(
                    text="⚡ Lanczos 4K Fallback",
                    foreground="#e65100",
                )
            else:
                self.lbl_ai_engine_status.config(
                    text="💡 Gợi ý: Cài GPU Engine x4 Detail",
                    foreground="#666",
                )
            self.btn_install_ai.config(text="📥 Tải GPU (~45MB)", state="normal")

    def _on_ai_upscale_toggled(self) -> None:
        """Cập nhật hiển thị trạng thái Engine AI khi bật/tắt checkbox AI Super-Resolution."""
        self._update_ai_engine_status_display()

    def _on_install_ai_engine(self) -> None:
        """Thực thi cài đặt tự động (1-Click) Real-ESRGAN Vulkan GPU trong background thread."""
        self.btn_install_ai.config(state="disabled")
        self.lbl_ai_engine_status.config(
            text="⏳ Đang kết nối tải Real-ESRGAN Vulkan GPU…",
            foreground="#1565c0",
        )

        def _worker():
            def _progress(pct: int):
                self.ui_dispatch(lambda: self.lbl_ai_engine_status.config(
                    text=f"⏳ Đang tải Real-ESRGAN GPU ({pct}%)…"
                ))

            def _status(msg: str):
                self.ui_dispatch(lambda: self.lbl_ai_engine_status.config(text=msg[:45]))

            ok, msg = install_realesrgan_engine(on_status=_status, on_progress=_progress)

            def _done():
                self._update_ai_engine_status_display()
                if ok:
                    self.var_img_ai_upscale.set(True)
                    self._update_ai_engine_status_display()
                    messagebox.showinfo(
                        "Cài đặt thành công",
                        f"{msg}\n\nĐã tự động kích hoạt tính năng AI Super-Resolution (x2/x4 Detail)!",
                    )
                else:
                    messagebox.showerror("Lỗi cài đặt", msg)

            self.ui_dispatch(_done)

        threading.Thread(target=_worker, daemon=True).start()

    # ══════════════════════════════════════════════════════════════════════
    # AUTO-DETECT URL
    # ══════════════════════════════════════════════════════════════════════

    def _on_url_changed(self, *_args) -> None:
        """
        Callback khi nội dung URL entry thay đổi.
        Tự động nhận diện nền tảng và phát hiện danh sách phát (Playlist).
        """
        url = self.var_url.get().strip()
        if not url:
            return

        is_pl, pl_target = is_playlist_url(url)
        detected = auto_detect_platform(url)
        if detected:
            current = self.var_target.get()
            if current != detected:
                self.var_target.set(detected)
                self._on_target_changed()

            # Tự động nhận diện chuyển đổi chế độ UI
            if (
                detected in ("Hình ảnh trực tiếp (PNG/JPG/GIF...)", "Pinterest (Pin & Image)")
                or is_direct_image_url(url)
                or is_pinterest_url(url)
                or (detected == "Facebook" and any(k in url.lower() for k in ["/photo", "fbid=", "/photos/"]))
            ):
                if self.var_media_mode.get() != "image":
                    self.var_media_mode.set("image")
                    self._update_mode_ui()
            elif detected in ("Spotify", "Zing MP3"):
                if self.var_media_mode.get() != "audio":
                    self.var_media_mode.set("audio")
                    self._update_mode_ui()
            elif detected in ("YouTube", "TikTok", "Twitter / X", "Instagram", "Reddit", "Bilibili", "Iwara (iwara.tv)"):
                if self.var_media_mode.get() == "image":
                    self.var_media_mode.set("video")
                    self._update_mode_ui()

            if is_pl:
                self.lbl_url_hint.config(
                    text=f"🔗 Phát hiện Danh sách phát (Playlist: {detected}) – Bấm '📋 Nhập Playlist' để nạp toàn bộ vào hàng đợi",
                    foreground="#1565c0",
                )
            else:
                self.lbl_url_hint.config(
                    text=f"🔗 Tự nhận diện: {detected}",
                    foreground="#2e7d32",
                )

    # ══════════════════════════════════════════════════════════════════════
    # THEME ENGINE & CONFIG PERSISTENCE
    # ══════════════════════════════════════════════════════════════════════

    def _toggle_theme(self) -> None:
        """Chuyển đổi chế độ giao diện Sáng / Tối."""
        new_theme = "light" if self.var_theme.get() == "dark" else "dark"
        self.var_theme.set(new_theme)
        self.btn_theme.config(text="🌙 Tối" if new_theme == "dark" else "☀️ Sáng")
        self._palette = apply_theme(self, new_theme)
        self.canvas.configure(background=self._palette["bg"])
        self._save_current_settings()

    def _save_current_settings(self) -> None:
        """Lưu lại trạng thái cấu hình hiện tại vào settings.json."""
        try:
            cfg = {
                "save_dir": self.var_save.get().strip() if hasattr(self, "var_save") else "",
                "target": self.var_target.get() if hasattr(self, "var_target") else "YouTube",
                "media_mode": self.var_media_mode.get() if hasattr(self, "var_media_mode") else "video",
                "video_format": self.var_container.get() if hasattr(self, "var_container") else "MP4 (.mp4 - Chuẩn)",
                "video_resolution": self.var_video_res.get() if hasattr(self, "var_video_res") else "Tốt nhất / Tự động (Cao nhất)",
                "audio_bitrate": self.var_audio_bitrate.get() if hasattr(self, "var_audio_bitrate") else "192 kbps (Tiêu chuẩn cao)",
                "clipboard_monitor": self.var_clipboard_monitor.get() if hasattr(self, "var_clipboard_monitor") else False,
                "auto_queue": self.var_auto_queue.get() if hasattr(self, "var_auto_queue") else False,
                "post_action": self.var_post_action.get() if hasattr(self, "var_post_action") else POST_ACTIONS[0],
                "img_res": self.var_img_res.get() if hasattr(self, "var_img_res") else "Gốc / Master (Original 100%)",
                "img_transcode": self.var_img_transcode.get() if hasattr(self, "var_img_transcode") else "Gốc (Giữ nguyên định dạng gốc)",
                "img_compress": self.var_img_compress.get() if hasattr(self, "var_img_compress") else "100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)",
                "img_strip_exif": self.var_img_strip_exif.get() if hasattr(self, "var_img_strip_exif") else True,
                "img_palette_opt": self.var_img_palette_opt.get() if hasattr(self, "var_img_palette_opt") else True,
                "img_hd_sharpness": self.var_img_hd_sharpness.get() if hasattr(self, "var_img_hd_sharpness") else True,
                "img_ai_upscale": self.var_img_ai_upscale.get() if hasattr(self, "var_img_ai_upscale") else False,
                "img_download_all": self.var_img_download_all.get() if hasattr(self, "var_img_download_all") else True,
                "cookie_browser": self.var_cookie_browser.get() if hasattr(self, "var_cookie_browser") else "None",
                "theme_mode": self.var_theme.get() if hasattr(self, "var_theme") else "dark",
            }
            save_config(cfg)
        except Exception:
            pass

    def _on_window_close(self) -> None:
        """Xử lý dọn dẹp và lưu cấu hình khi đóng ứng dụng."""
        self._save_current_settings()
        if self._running:
            self._on_cancel_download()
        self.destroy()

    # ══════════════════════════════════════════════════════════════════════
    # CLIPBOARD MONITOR & AUTO-QUEUE
    # ══════════════════════════════════════════════════════════════════════

    def _toggle_clipboard_monitor(self) -> None:
        """Bật/tắt clipboard monitor."""
        if self.var_clipboard_monitor.get():
            self._clipboard_monitoring = True
            try:
                self._last_clipboard = self.clipboard_get().strip()
            except tk.TclError:
                self._last_clipboard = ""
            self._check_clipboard()
            self._set_status("📋 Clipboard Monitor: BẬT")
        else:
            self._clipboard_monitoring = False
            if self._clipboard_after_id:
                self.after_cancel(self._clipboard_after_id)
                self._clipboard_after_id = None
            self._set_status("📋 Clipboard Monitor: TẮT")

    def _check_clipboard(self) -> None:
        """
        Kiểm tra clipboard định kỳ. Nếu phát hiện URL media hợp lệ mới,
        tự động điền vào ô URL hoặc tự động thêm vào hàng đợi (Auto-Queue).

        BẢO MẬT:
        - Giới hạn độ dài clipboard (MAX_CLIPBOARD_LENGTH)
        - Chỉ xử lý URL khớp regex whitelist
        - Không lưu trữ nội dung clipboard ngoài biến tạm
        """
        if not self._clipboard_monitoring:
            return

        try:
            content = self.clipboard_get().strip()
        except tk.TclError:
            content = ""

        # Giới hạn độ dài chống buffer overflow
        if len(content) > MAX_CLIPBOARD_LENGTH:
            self._clipboard_after_id = self.after(
                CLIPBOARD_CHECK_INTERVAL_MS, self._check_clipboard
            )
            return

        # Chỉ xử lý nếu clipboard thay đổi và là URL hợp lệ
        if content and content != self._last_clipboard:
            self._last_clipboard = content
            detected = auto_detect_platform(content)
            if detected:
                valid, result = self._validate_url(content, detected)
                if valid:
                    # Nếu bật chế độ Auto-Queue: tự động thêm vào hàng đợi
                    if self.var_auto_queue.get():
                        is_dup = any(item["url"] == content for item in self._download_queue)
                        if not is_dup and len(self._download_queue) < MAX_QUEUE_SIZE:
                            is_pl, _ = is_playlist_url(content)
                            if is_pl:
                                # Nạp playlist tự động
                                self._add_playlist_to_queue(url_override=content, prompt=False)
                            else:
                                queue_item = {
                                    "url": content,
                                    "target": result,
                                    "platform": detected,
                                    "title": f"Media ({detected})",
                                    "duration": "-",
                                    "status": QUEUE_WAITING,
                                    "error": "",
                                }
                                self._download_queue.append(queue_item)
                                self._refresh_queue_ui()
                                self._set_status(f"⚡ Auto-Queue: Đã thêm URL {detected} vào hàng đợi!")
                    else:
                        # Tự động điền URL và nhận diện nền tảng
                        current_url = self.var_url.get().strip()
                        if content != current_url:
                            self.var_url.set(content)
                            self._set_status(f"📋 Phát hiện URL {detected} từ clipboard!")

        self._clipboard_after_id = self.after(
            CLIPBOARD_CHECK_INTERVAL_MS, self._check_clipboard
        )

    # ══════════════════════════════════════════════════════════════════════
    # DOWNLOAD QUEUE & PLAYLIST MANAGEMENT
    # ══════════════════════════════════════════════════════════════════════

    def _add_to_queue(self) -> None:
        """
        Thêm URL hiện tại vào hàng đợi tải xuống.
        BẢO MẬT: Validate URL trước khi thêm, giới hạn kích thước queue.
        """
        if len(self._download_queue) >= MAX_QUEUE_SIZE:
            messagebox.showwarning(
                "Hàng đợi đầy",
                f"Hàng đợi đã đạt giới hạn tối đa ({MAX_QUEUE_SIZE} mục).\n"
                "Vui lòng xóa bớt hoặc tải trước khi thêm mới.",
            )
            return

        url = self.var_url.get().strip()
        target = self.var_target.get()
        valid, result = self._validate_url(url, target)
        if not valid:
            messagebox.showwarning("URL không hợp lệ", result)
            return

        # Kiểm tra nếu là Playlist
        is_pl, _ = is_playlist_url(url)
        if is_pl:
            res = messagebox.askyesno(
                "Phát hiện Danh sách phát",
                f"URL này là một Danh sách phát ({target}).\n"
                "Bạn có muốn nạp toàn bộ các bài hát/video vào hàng đợi không?\n\n"
                "• Chọn 'Yes' để nạp toàn bộ danh sách phát\n"
                "• Chọn 'No' để chỉ thêm 1 mục URL này vào hàng đợi",
            )
            if res:
                self._add_playlist_to_queue(url_override=url)
                return

        # Kiểm tra trùng lặp
        for item in self._download_queue:
            if item["url"] == url:
                messagebox.showinfo("Đã có", "URL này đã có trong hàng đợi.")
                return

        title_str = "Media"
        dur_str = "-"
        if self._current_info and self.var_url.get().strip() == url:
            title_str = self._current_info.get("title") or title_str
            dur_str = format_duration(self._current_info.get("duration"))
        else:
            title_str = f"{target} ({url[-18:]})"

        clip_s = self.var_clip_start.get().strip() if hasattr(self, "var_clip_start") else ""
        clip_e = self.var_clip_end.get().strip() if hasattr(self, "var_clip_end") else ""

        # Thêm vào queue
        queue_item = {
            "url": url,
            "target": result,  # "youtube", "twitter", etc.
            "platform": target,  # Display name
            "title": title_str,
            "duration": dur_str,
            "status": QUEUE_WAITING,
            "error": "",
            "clip_start": clip_s,
            "clip_end": clip_e,
        }
        self._download_queue.append(queue_item)
        self._refresh_queue_ui()

        # Xóa URL và thời gian cắt hiện tại để sẵn sàng nhập URL mới
        self.var_url.set("")
        if hasattr(self, "var_clip_start"):
            self.var_clip_start.set("")
        if hasattr(self, "var_clip_end"):
            self.var_clip_end.set("")
        self._set_status(f"➕ Đã thêm vào hàng đợi ({len(self._download_queue)} mục)")

    def _add_playlist_to_queue(self, url_override: Optional[str] = None, prompt: bool = True) -> None:
        """
        Trích xuất và nạp các bài hát/video trong Playlist vào hàng đợi.
        BẢO MẬT: Giới hạn tối đa MAX_PLAYLIST_ITEMS, ngăn chặn DoS.
        """
        url = (url_override or self.var_url.get()).strip()
        if not url:
            messagebox.showwarning("Thiếu URL", "Vui lòng dán liên kết Playlist vào ô URL Media.")
            return

        is_pl, pl_target = is_playlist_url(url)
        if not is_pl:
            detected = auto_detect_platform(url)
            if not detected:
                messagebox.showwarning("Không phải Playlist", "URL không thuộc danh sách phát được hỗ trợ (YouTube, Spotify, Zing MP3).")
                return
            target_code = detected.lower()
        else:
            target_code = pl_target or self.var_target.get().lower()

        # Lấy cookies nếu có
        cookie_browser = None
        cookie_file = None
        method = self.var_cookie_method.get()
        if "trình duyệt" in method.lower() or method == "browser":
            cookie_browser = self.var_cookie_browser.get().strip() or None
        elif "file" in method.lower():
            cookie_file = self.var_cookie_file.get().strip() or None

        self._set_status("⏳ Đang trích xuất danh sách bài trong Playlist…")
        self.progress.config(mode="indeterminate")
        self.progress.start(15)

        def _worker():
            try:
                meta, entries = extract_playlist_items(
                    url=url,
                    target=target_code,
                    max_items=MAX_PLAYLIST_ITEMS,
                    cookie_browser=cookie_browser,
                    cookie_file=cookie_file,
                )
                if not entries:
                    self.ui_dispatch(
                        lambda: messagebox.showerror(
                            "Không tìm thấy mục",
                            "Không thể trích xuất các bài trong Playlist này hoặc Playlist rỗng."
                        )
                    )
                    return

                def _apply():
                    added_count = 0
                    existing_urls = {item["url"] for item in self._download_queue}
                    for e in entries:
                        if len(self._download_queue) >= MAX_QUEUE_SIZE:
                            break
                        if e["url"] in existing_urls:
                            continue
                        self._download_queue.append({
                            "url": e["url"],
                            "target": e["target"],
                            "platform": e["platform"],
                            "title": e.get("title") or "Video",
                            "duration": format_duration(e.get("duration")),
                            "status": QUEUE_WAITING,
                            "error": "",
                        })
                        existing_urls.add(e["url"])
                        added_count += 1

                    self._refresh_queue_ui()
                    self.var_url.set("")
                    pl_title = meta.get("title", "Playlist")
                    msg = (
                        f"✅ Đã nạp {added_count} bài từ '{pl_title}' vào hàng đợi!\n\n"
                        f"🔢 Tổng số mục trong hàng đợi: {len(self._download_queue)}"
                    )
                    self._set_status(f"📋 Đã nạp Playlist: {added_count} mục")
                    if prompt:
                        messagebox.showinfo("Nạp Playlist thành công", msg)

                self.ui_dispatch(_apply)
            except Exception as exc:
                self.ui_dispatch(
                    lambda: messagebox.showerror("Lỗi trích xuất Playlist", f"Không thể lấy thông tin Playlist:\n{exc}")
                )
            finally:
                self.ui_dispatch(lambda: self.progress.stop())

        threading.Thread(target=_worker, daemon=True).start()

    def _import_urls_from_file(self) -> None:
        """
        Nhập danh sách URL an toàn từ file text (.txt).
        Mỗi dòng là 1 URL. BẢO MẬT: Xác thực regex nghiêm ngặt cho từng dòng.
        """
        filepath = filedialog.askopenfilename(
            title="Chọn file text chứa danh sách URL",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception as exc:
            messagebox.showerror("Lỗi đọc file", f"Không thể đọc file text:\n{exc}")
            return

        added = 0
        skipped = 0
        existing = {item["url"] for item in self._download_queue}

        for line in lines:
            u = line.strip()
            if not u or u.startswith("#"):
                continue
            if len(u) > MAX_CLIPBOARD_LENGTH or len(self._download_queue) >= MAX_QUEUE_SIZE:
                skipped += 1
                continue
            if u in existing:
                skipped += 1
                continue

            detected = auto_detect_platform(u)
            if not detected:
                skipped += 1
                continue

            valid, result = self._validate_url(u, detected)
            if not valid:
                skipped += 1
                continue

            self._download_queue.append({
                "url": u,
                "target": result,
                "platform": detected,
                "title": f"{detected} ({u[-18:]})",
                "duration": "-",
                "status": QUEUE_WAITING,
                "error": "",
            })
            existing.add(u)
            added += 1

        self._refresh_queue_ui()
        self._set_status(f"📁 Đã nhập {added} URL từ file ({skipped} bỏ qua)")
        messagebox.showinfo(
            "Kết quả nhập URL",
            f"Đã nhập thành công {added} URL hợp lệ vào hàng đợi.\n"
            f"Bỏ qua: {skipped} dòng (trùng lặp, sai định dạng hoặc vượt quá giới hạn {MAX_QUEUE_SIZE} mục)."
        )

    def _move_queue_item(self, direction: int) -> None:
        """Di chuyển mục được chọn lên (-1) hoặc xuống (+1) trong hàng đợi."""
        selected = self.tree_queue.selection()
        if not selected:
            return
        item_id = selected[0]
        children = self.tree_queue.get_children()
        idx = list(children).index(item_id)
        new_idx = idx + direction
        if 0 <= new_idx < len(self._download_queue):
            # Không di chuyển mục đang tải
            if (
                self._download_queue[idx]["status"] == QUEUE_DOWNLOADING
                or self._download_queue[new_idx]["status"] == QUEUE_DOWNLOADING
            ):
                return
            self._download_queue[idx], self._download_queue[new_idx] = (
                self._download_queue[new_idx],
                self._download_queue[idx],
            )
            self._refresh_queue_ui()
            # Khôi phục lựa chọn
            new_children = self.tree_queue.get_children()
            self.tree_queue.selection_set(new_children[new_idx])

    def _retry_failed_queue(self) -> None:
        """Đặt lại trạng thái của các mục lỗi / bị hủy về 'Chờ' để tải lại."""
        reset_count = 0
        for item in self._download_queue:
            if item["status"] in (QUEUE_ERROR, QUEUE_CANCELLED):
                item["status"] = QUEUE_WAITING
                item["error"] = ""
                reset_count += 1
        if reset_count > 0:
            self._refresh_queue_ui()
            self._set_status(f"🔄 Đã đặt lại {reset_count} mục lỗi về trạng thái Chờ")
        else:
            messagebox.showinfo("Thông báo", "Không có mục lỗi nào trong hàng đợi.")

    def _clean_completed_queue(self) -> None:
        """Xóa các mục đã tải xong khỏi hàng đợi."""
        before = len(self._download_queue)
        self._download_queue = [
            item for item in self._download_queue
            if item["status"] != QUEUE_COMPLETED
        ]
        cleaned = before - len(self._download_queue)
        self._refresh_queue_ui()
        self._set_status(f"🧹 Đã dọn {cleaned} mục đã hoàn tất")

    def _remove_from_queue(self) -> None:
        """Xóa mục được chọn khỏi hàng đợi."""
        selected = self.tree_queue.selection()
        if not selected:
            messagebox.showinfo("Chọn mục", "Vui lòng chọn một mục trong hàng đợi để xóa.")
            return

        item_id = selected[0]
        children = self.tree_queue.get_children()
        idx = list(children).index(item_id)

        if idx < len(self._download_queue):
            # Không xóa mục đang tải
            if self._download_queue[idx]["status"] == QUEUE_DOWNLOADING:
                messagebox.showwarning("Không thể xóa", "Không thể xóa mục đang tải. Hãy hủy trước.")
                return
            self._download_queue.pop(idx)
            self._refresh_queue_ui()

    def _clear_queue(self) -> None:
        """Xóa toàn bộ hàng đợi (trừ mục đang tải)."""
        if not self._download_queue:
            return

        if self._queue_processing:
            # Giữ lại mục đang tải
            self._download_queue = [
                item for item in self._download_queue
                if item["status"] == QUEUE_DOWNLOADING
            ]
        else:
            self._download_queue.clear()

        self._refresh_queue_ui()
        self._set_status("🗑️ Đã xóa hàng đợi")

    def _refresh_queue_ui(self) -> None:
        """Cập nhật Treeview hiển thị hàng đợi chi tiết với tiêu đề và thời lượng."""
        # Xóa tất cả rows hiện tại
        for item in self.tree_queue.get_children():
            self.tree_queue.delete(item)

        # Thêm lại từ dữ liệu
        for i, q_item in enumerate(self._download_queue, 1):
            title = q_item.get("title") or q_item["url"]
            if len(title) > 48:
                title = title[:45] + "…"
            dur = q_item.get("duration") or "-"
            self.tree_queue.insert(
                "", "end",
                values=(i, title, q_item["platform"], dur, q_item["status"]),
            )

        self.lbl_queue_info.config(text=f"{len(self._download_queue)} mục")

    def _start_queue_processing(self) -> None:
        """Bắt đầu tải lần lượt các mục trong hàng đợi."""
        if self._running or self._analyzing:
            messagebox.showinfo("Đang bận", "Đang có tác vụ đang chạy. Vui lòng đợi hoàn tất.")
            return

        # Lọc các mục chưa tải
        pending = [i for i, item in enumerate(self._download_queue) if item["status"] == QUEUE_WAITING]
        if not pending:
            messagebox.showinfo("Hàng đợi trống", "Không có mục nào đang chờ tải trong hàng đợi.")
            return

        self._queue_processing = True
        self._current_queue_index = pending[0]
        self._process_next_queue_item()

    def _process_next_queue_item(self) -> None:
        """Xử lý mục tiếp theo trong hàng đợi."""
        if not self._queue_processing:
            return

        # Tìm mục tiếp theo đang chờ
        pending = [
            i for i, item in enumerate(self._download_queue)
            if item["status"] == QUEUE_WAITING
        ]

        if not pending:
            # Hoàn tất toàn bộ hàng đợi
            self._queue_processing = False
            self._current_queue_index = -1
            completed = sum(1 for item in self._download_queue if item["status"] == QUEUE_COMPLETED)
            errors = sum(1 for item in self._download_queue if item["status"] == QUEUE_ERROR)
            self._set_status(f"📥 Hàng đợi hoàn tất: {completed} thành công, {errors} lỗi")
            # Post-download action cho toàn bộ queue
            self._execute_post_download_action()
            return

        idx = pending[0]
        self._current_queue_index = idx
        q_item = self._download_queue[idx]

        # Cập nhật trạng thái
        q_item["status"] = QUEUE_DOWNLOADING
        self._refresh_queue_ui()

        # Điền URL vào giao diện và bắt đầu tải
        self.var_url.set(q_item["url"])

        # Tìm platform display name cho target
        target_map = {
            "youtube": "YouTube",
            "twitter": "Twitter / X",
            "facebook": "Facebook",
            "tiktok": "TikTok",
            "instagram": "Instagram",
            "reddit": "Reddit",
            "bilibili": "Bilibili",
            "pinterest": "Pinterest (Pin & Image)",
            "rule34": "Rule34 / Booru (Image & Video)",
            "iwara": "Iwara (iwara.tv)",
            "telegram": "Telegram (t.me)",
            "zingmp3": "Zing MP3",
            "spotify": "Spotify",
            "direct_image": "Hình ảnh trực tiếp (PNG/JPG/GIF...)",
            "direct_media": "Media trực tiếp (MP4/WebM/MP3...)",
            "locallab": "Local Lab / Custom Stream (HLS/DASH)",
            "universal": "Nền tảng khác / Universal (yt-dlp)",
        }
        platform = target_map.get(q_item["target"], "YouTube")
        self.var_target.set(platform)
        self._on_target_changed()

        if hasattr(self, "var_clip_start"):
            self.var_clip_start.set(q_item.get("clip_start", ""))
        if hasattr(self, "var_clip_end"):
            self.var_clip_end.set(q_item.get("clip_end", ""))

        # Bắt đầu tải
        self._on_start(_from_queue=True)

    # ══════════════════════════════════════════════════════════════════════
    # PAUSE / RESUME / CANCEL
    # ══════════════════════════════════════════════════════════════════════

    def _on_pause_resume(self) -> None:
        """Chuyển đổi trạng thái Tạm dừng / Tiếp tục."""
        if not self._running:
            return

        if self._pause_event.is_set():
            # Hiện đang chạy → Tạm dừng
            self._pause_event.clear()
            self._pause_start_time = time.time()
            self.btn_pause.config(text="▶️ Tiếp tục")
            self._set_status("⏸️ Đã tạm dừng")

            # Thiết lập auto-cancel timeout (30 phút)
            self._pause_timeout_after_id = self.after(
                PAUSE_TIMEOUT_SECONDS * 1000, self._pause_timeout_handler
            )
        else:
            # Hiện đang dừng → Tiếp tục
            self._pause_event.set()
            self._pause_start_time = None
            self.btn_pause.config(text="⏸️ Tạm dừng")

            # Hủy timeout timer
            if self._pause_timeout_after_id:
                self.after_cancel(self._pause_timeout_after_id)
                self._pause_timeout_after_id = None

    def _pause_timeout_handler(self) -> None:
        """Auto-cancel khi tạm dừng quá lâu (bảo mật: tránh file tạm treo)."""
        if not self._pause_event.is_set() and self._running:
            self._set_status(f"⏱️ Auto-cancel: Tạm dừng quá {PAUSE_TIMEOUT_SECONDS // 60} phút")
            self._on_cancel_download()

    def _on_cancel_download(self) -> None:
        """Hủy tải xuống hiện tại và dọn dẹp file tạm dở dang."""
        if not self._running:
            return

        self._cancel_event.set()
        # Nếu đang pause, resume để thread có thể thoát
        if not self._pause_event.is_set():
            self._pause_event.set()

        self.btn_pause.config(text="⏸️ Tạm dừng", state="disabled")
        self.btn_cancel.config(state="disabled")
        self._set_status("🚫 Đang hủy tải…")

        # Cập nhật queue item nếu đang xử lý queue
        if self._queue_processing and 0 <= self._current_queue_index < len(self._download_queue):
            self._download_queue[self._current_queue_index]["status"] = QUEUE_CANCELLED
            self._refresh_queue_ui()

        # Dọn dẹp file tạm dở dang
        if self._last_downloaded_dir:
            cleaned = cleanup_temp_files(self._last_downloaded_dir, self._last_downloaded_prefix or "")
            if cleaned > 0:
                self._set_status(f"🧹 Đã hủy & dọn dẹp {cleaned} file tạm dở dang")

    # ══════════════════════════════════════════════════════════════════════
    # POST-DOWNLOAD ACTIONS & FILE SECURITY
    # ══════════════════════════════════════════════════════════════════════

    def _execute_post_download_action(self) -> None:
        """Thực thi hành động sau khi tải xong."""
        action = self.var_post_action.get()
        save_dir = self._last_downloaded_dir or self.var_save.get().strip()

        if "Mở thư mục" in action:
            safe_open_path(save_dir, open_file=False)

        if "Mở file" in action:
            # Tìm file mới nhất trong thư mục với prefix
            if self._last_downloaded_prefix and save_dir:
                p_dir = Path(save_dir)
                matching = sorted(
                    [f for f in p_dir.iterdir()
                     if f.is_file() and f.name.startswith(self._last_downloaded_prefix)
                     and f.suffix.lstrip(".").lower() in SAFE_EXTENSIONS
                     and f.suffix.lstrip(".").lower() not in ("srt", "vtt", "jpg", "jpeg", "png")],
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                if matching:
                    safe_open_path(str(matching[0]), open_file=True)

        if "Thông báo" in action or "notify" in action.lower():
            safe_notify(
                "✅ Tải xong – Media Downloader",
                f"Đã tải thành công vào: {save_dir}",
            )

    def _run_security_scan(self, save_dir: str, prefix: str) -> Optional[str]:
        """
        Chạy quét bảo mật file sau tải.
        Kiểm tra tính toàn vẹn (Magic Bytes, Extension, Chữ ký thực thi) và tính SHA-256.
        """
        if not self.var_security_scan.get():
            return None

        all_safe, warnings = validate_downloaded_files(save_dir, prefix)

        # Tính SHA-256 cho các file đã tải
        sha256_reports: list[str] = []
        try:
            p_dir = Path(save_dir)
            if p_dir.is_dir():
                for f in sorted(p_dir.iterdir()):
                    if f.is_file() and f.name.startswith(prefix) and f.suffix.lstrip(".").lower() in SAFE_EXTENSIONS:
                        h = compute_file_sha256(str(f))
                        if h:
                            sha256_reports.append(f"• {f.name}\n  SHA-256: {h}")
        except Exception:
            pass

        sha_text = ("\n\n🔒 BẢNG MÃ BĂM TOÀN VẸN (SHA-256):\n" + "\n".join(sha256_reports[:3])) if sha256_reports else ""

        if warnings:
            warning_text = "\n".join(warnings)
            if not all_safe:
                return (
                    "🚨 CẢNH BÁO BẢO MẬT – Phát hiện dấu hiệu ĐỘC HẠI:\n\n"
                    f"{warning_text}\n\n"
                    "Khuyến nghị: Không mở file này và xóa ngay!"
                    + sha_text
                )
            else:
                return f"⚠ Lưu ý bảo mật:\n\n{warning_text}" + sha_text

        if sha_text:
            return "✅ File an toàn (Đã quét Extension, Magic Bytes & Chữ ký thực thi)" + sha_text

        return None

    def _on_target_changed(self, _event=None) -> None:
        """Thay đổi gợi ý và hiển thị cookie theo mục tiêu."""
        self._update_hint()
        target = self.var_target.get()
        cookie_platforms = {
            "Twitter / X": "Twitter/X",
            "Facebook": "Facebook",
            "Zing MP3": "Zing MP3 (cần VIP để tải nhiều bài)",
            "Spotify": "Spotify",
        }
        if target in cookie_platforms:
            platform_label = cookie_platforms[target]
            self.frm_cookie.config(text=f"🍪 Tùy chọn Cookie / Xác thực ({platform_label})")
            self.frm_cookie.pack(fill="x", padx=12, pady=5, before=self.ent_save.master)
        else:
            self.frm_cookie.pack_forget()

        # Nếu chọn Hình ảnh trực tiếp, tự động chuyển chế độ Hình ảnh
        if target == "Hình ảnh trực tiếp (PNG/JPG/GIF...)":
            self.var_media_mode.set("image")
            self._update_mode_ui()
        elif target in ("Spotify", "Zing MP3"):
            self.var_media_mode.set("audio")
            self._update_mode_ui()

    def _update_cookie_ui(self, _event=None) -> None:
        method = self.var_cookie_method.get()
        if "trình duyệt" in method.lower() or method == "browser":
            self.lbl_cookie_browser.grid()
            self.cmb_cookie_browser.grid()
            self.ent_cookie_file.grid_remove()
            self.btn_cookie_browse.grid_remove()
            self.lbl_cookie_hint.config(
                text="Tự động lấy cookies từ trình duyệt đã đăng nhập (Firefox, Chrome...)"
            )
        elif "file" in method.lower():
            self.lbl_cookie_browser.grid_remove()
            self.cmb_cookie_browser.grid_remove()
            self.ent_cookie_file.grid()
            self.btn_cookie_browse.grid()
            self.lbl_cookie_hint.config(
                text="Chọn file cookies.txt (Netscape format) export từ trình duyệt"
            )
        else:
            self.lbl_cookie_browser.grid_remove()
            self.cmb_cookie_browser.grid_remove()
            self.ent_cookie_file.grid_remove()
            self.btn_cookie_browse.grid_remove()
            self.lbl_cookie_hint.config(
                text="Tải công khai qua Guest API (không cần tài khoản, phù hợp video công khai)"
            )

    def _update_hint(self) -> None:
        target = self.var_target.get()
        hints = {
            "Twitter / X": "Ví dụ: https://x.com/user/status/1234567890",
            "YouTube": "Ví dụ: https://www.youtube.com/watch?v=dQw4w9WgXcQ (hỗ trợ Shorts, Music, Playlist)",
            "Facebook": "Ví dụ: https://www.facebook.com/user/videos/123456789 hoặc fb.watch/xxx",
            "TikTok": "Ví dụ: https://www.tiktok.com/@user/video/123456789",
            "Instagram": "Ví dụ: https://www.instagram.com/reel/Cxxxxxx hoặc /p/Cxxxxxx",
            "Reddit": "Ví dụ: https://www.reddit.com/r/videos/comments/xxxxxx/ hoặc https://redd.it/xxxx",
            "Bilibili": "Ví dụ: https://www.bilibili.com/video/BV1xx411c7mD hoặc https://b23.tv/xxxx",
            "Pinterest (Pin & Image)": "Ví dụ: https://www.pinterest.com/pin/123456789/ hoặc pin.it/xxx, i.pinimg.com (tự động tối ưu Master 100%)",
            "Rule34 / Booru (Image & Video)": "Ví dụ: https://rule34.xxx/index.php?page=post&s=view&id=... hoặc rule34video.com, booru",
            "Iwara (iwara.tv)": "Ví dụ: https://www.iwara.tv/video/XXXXX hoặc https://ecchi.iwara.tv/...",
            "Telegram (t.me)": "Ví dụ: https://t.me/channel_name/1234 (hỗ trợ video, ảnh & album từ bài đăng)",
            "Zing MP3": "Ví dụ: https://zingmp3.vn/bai-hat/Ten-Bai-Hat/ZWZABC.html",
            "Spotify": "Ví dụ: https://open.spotify.com/track/4iV5W9uYEdYUVa79Axb7Rh",
            "Hình ảnh trực tiếp (PNG/JPG/GIF...)": "Ví dụ: https://example.com/image.png (hỗ trợ PNG, JPG, GIF, WebP, JNG, BMP, SVG...)",
            "Media trực tiếp (MP4/WebM/MP3...)": "Ví dụ: https://example.com/video.mp4 hoặc audio.mp3",
            "Local Lab / Custom Stream (HLS/DASH)": "Ví dụ: http://localhost:8080/stream/playlist.m3u8",
            "Nền tảng khác / Universal (yt-dlp)": "Hỗ trợ hơn 1700 trang web video/audio công khai (Vimeo, Dailymotion, Twitch, Pinterest...)",
        }
        self.lbl_url_hint.config(text=hints.get(target, ""))

    def _update_disk_info(self) -> None:
        save_dir = self.var_save.get()
        try:
            if Path(save_dir).is_dir():
                usage = shutil.disk_usage(save_dir)
                free_gb = usage.free / (1024**3)
                self.lbl_disk.config(
                    text=f"💾 Dung lượng trống: {free_gb:.1f} GB",
                    foreground="#2e7d32" if free_gb > 0.5 else "#b71c1c",
                )
            else:
                self.lbl_disk.config(text="⚠ Thư mục không tồn tại", foreground="#b71c1c")
        except Exception:
            self.lbl_disk.config(text="", foreground="#555")

    def _paste_url(self) -> None:
        try:
            text = self.clipboard_get().strip()
            if text:
                self.var_url.set(text)
                self._on_analyze()
        except tk.TclError:
            messagebox.showwarning("Clipboard", "Không thể đọc nội dung từ clipboard.")

    def _display_thumbnail(self, pil_img: Optional[Image.Image], fallback_text: str = "No Thumbnail") -> None:
        """
        Hiển thị ảnh thumbnail lên lbl_thumb_preview:
        - Đảm bảo sử dụng thư viện PIL (Pillow) với ImageTk.PhotoImage.
        - Tải và resize thumbnail tối ưu kích thước cố định khoảng 160x90 px.
        - Lưu tham chiếu ảnh vào thuộc tính widget (self.lbl_thumb_preview.image = photo)
          và self._photo_ref để tránh bị Garbage Collector xóa mất hình.
        - Thêm cơ chế Fallback: Nếu không lấy được thumbnail từ URL hoặc URL rỗng,
          hiển thị một ảnh placeholder (khung xám ghi chữ 'No Thumbnail') thay vì ô đen lỗi.
        """
        if not HAS_PIL:
            self.lbl_thumb_preview.config(image="", text=f"[{fallback_text}]", width=22, height=6)
            return

        final_img = pil_img or create_placeholder_thumbnail(size=(160, 90), text=fallback_text)
        try:
            if HAS_IMAGETK:
                photo = ImageTk.PhotoImage(final_img)
            else:
                buf = io.BytesIO()
                final_img.save(buf, format="PNG")
                photo = tk.PhotoImage(data=buf.getvalue())

            # Lưu tham chiếu vào thuộc tính widget & biến instance để tránh Python GC thu hồi
            self.lbl_thumb_preview.image = photo
            self._photo_ref = photo
            self.lbl_thumb_preview.config(image=photo, text="", width=0, height=0)
        except Exception:
            self.lbl_thumb_preview.config(image="", text=f"[{fallback_text}]", width=22, height=6)

    def _on_clear_url(self) -> None:
        self.var_url.set("")
        self._current_info = None
        self._display_thumbnail(None, fallback_text="No Thumbnail")
        self.lbl_info_title.config(text="📌 Tiêu đề: (Chưa phân tích)")
        self.lbl_info_author.config(text="👤 Tác giả / Kênh: -")
        self.lbl_info_duration.config(text="⏱️ Thời lượng: -")
        self.lbl_info_subs.config(text="💬 Phụ đề phát hiện: -")
        self.lbl_info_status.config(text="💡 Nhập URL và bấm 'Phân tích Video' để nhận diện chi tiết.")

    def _browse_dir(self) -> None:
        d = filedialog.askdirectory(title="Chọn thư mục lưu trữ", initialdir=self.var_save.get())
        if d:
            self.var_save.set(d)

    def _browse_cookie_file(self) -> None:
        f = filedialog.askopenfilename(
            title="Chọn file cookies.txt",
            filetypes=[("Cookie files", "*.txt"), ("All files", "*.*")],
        )
        if f:
            self.var_cookie_file.set(f)

    def _set_status(self, text: str) -> None:
        if hasattr(self, "logger"):
            self.logger.info("Trạng thái: %s", text)
        color_map = {
            STATUS_READY: "#2e7d32",
            STATUS_COMPLETED: "#2e7d32",
            STATUS_DRM: "#e65100",
            STATUS_DENIED: "#b71c1c",
            STATUS_ERROR: "#b71c1c",
            STATUS_CONNECTING: "#1565c0",
            STATUS_AUDITING: "#1565c0",
        }
        color = "#1565c0"
        for key, c in color_map.items():
            if key in text or text == key:
                color = c
                break
        self.ui_dispatch(lambda: self.lbl_status.config(text=text, foreground=color))

    def _set_progress(self, pct: float) -> None:
        def _update():
            if self.progress["mode"] != "determinate":
                self.progress.stop()
                self.progress.config(mode="determinate")
            self.progress["value"] = pct
        self.ui_dispatch(_update)

    def _on_finish(self, success: bool, message: str) -> None:
        if hasattr(self, "logger"):
            if success:
                self.logger.info("Hoàn tất: %s", message[:200])
            else:
                self.logger.error("Lỗi: %s", message[:200])

        def _do():
            self._running = False
            self.btn_start.config(state="normal")
            self.btn_start_queue.config(state="normal")
            self.btn_analyze.config(state="normal")
            self.btn_pause.config(state="disabled", text="⏸️ Tạm dừng")
            self.btn_cancel.config(state="disabled")
            self.progress.stop()

            # Reset pause state
            self._pause_event.set()
            if self._pause_timeout_after_id:
                self.after_cancel(self._pause_timeout_after_id)
                self._pause_timeout_after_id = None

            # ── Quét bảo mật file sau tải ─────────────────────────────────
            security_msg = ""
            if success and self._last_downloaded_dir and self._last_downloaded_prefix:
                scan_result = self._run_security_scan(
                    self._last_downloaded_dir, self._last_downloaded_prefix
                )
                if scan_result:
                    security_msg = f"\n\n{'─' * 40}\n🛡️ KẾT QUẢ QUÉT BẢO MẬT:\n{scan_result}"

            # ── Cập nhật queue status ─────────────────────────────────────
            if self._queue_processing and 0 <= self._current_queue_index < len(self._download_queue):
                if success:
                    self._download_queue[self._current_queue_index]["status"] = QUEUE_COMPLETED
                elif self._cancel_event.is_set():
                    self._download_queue[self._current_queue_index]["status"] = QUEUE_CANCELLED
                else:
                    self._download_queue[self._current_queue_index]["status"] = QUEUE_ERROR
                    self._download_queue[self._current_queue_index]["error"] = message[:100]
                self._refresh_queue_ui()

            if success:
                self.progress.config(mode="determinate")
                self.progress["value"] = 100
                full_msg = message + security_msg
                messagebox.showinfo("Hoàn tất", full_msg)

                # ── Thực thi hành động sau tải (chỉ khi không đang xử lý queue) ──
                if not self._queue_processing:
                    self._execute_post_download_action()
            else:
                self.progress.config(mode="determinate")
                self.progress["value"] = 0
                if self._cancel_event.is_set():
                    messagebox.showinfo("Đã hủy", "Tải xuống đã bị hủy bởi người dùng.")
                elif "DRM" in message:
                    messagebox.showwarning("DRM Protected", message)
                elif "401" in message or "403" in message:
                    messagebox.showwarning("Access Denied", message)
                else:
                    messagebox.showerror("Lỗi", message)

            # ── Tiếp tục xử lý queue nếu còn mục ─────────────────────────
            if self._queue_processing and not self._cancel_event.is_set():
                self.after(1000, self._process_next_queue_item)
            elif self._queue_processing and self._cancel_event.is_set():
                # Cancel → dừng toàn bộ queue
                self._queue_processing = False
                self._current_queue_index = -1
                self._set_status("🚫 Đã hủy hàng đợi")

        self.ui_dispatch(_do)

    # ── URL Validation ────────────────────────────────────────────────────
    def _validate_url(self, url: str, target: str) -> tuple[bool, str]:
        if not url:
            return False, "Vui lòng nhập URL."

        if target == "Twitter / X":
            if RE_TWITTER.match(url):
                return True, "twitter"
            return False, "URL Twitter/X không hợp lệ.\nĐịnh dạng: https://x.com/user/status/1234567890"

        if target == "YouTube":
            if RE_YOUTUBE.match(url) or "youtube.com" in url or "youtu.be" in url:
                return True, "youtube"
            return False, (
                "URL YouTube không hợp lệ.\nĐịnh dạng hỗ trợ:\n"
                "• https://www.youtube.com/watch?v=VIDEO_ID\n"
                "• https://youtu.be/VIDEO_ID\n"
                "• https://www.youtube.com/shorts/VIDEO_ID"
            )

        if target == "Facebook":
            if RE_FACEBOOK.match(url) or "facebook.com" in url or "fb.watch" in url:
                return True, "facebook"
            return False, "URL Facebook không hợp lệ.\nĐịnh dạng hỗ trợ: /videos/, /watch?v=, /reel/, fb.watch/..."

        if target == "TikTok":
            if RE_TIKTOK.match(url) or "tiktok.com" in url:
                return True, "tiktok"
            return False, "URL TikTok không hợp lệ.\nĐịnh dạng: https://www.tiktok.com/@user/video/..."

        if target == "Instagram":
            if RE_INSTAGRAM.match(url) or "instagram.com" in url or "instagr.am" in url:
                return True, "instagram"
            return False, "URL Instagram không hợp lệ.\nĐịnh dạng: https://www.instagram.com/reel/... hoặc /p/..."

        if target == "Reddit":
            if RE_REDDIT.match(url) or "reddit.com" in url or "redd.it" in url or "v.redd.it" in url:
                return True, "reddit"
            return False, "URL Reddit không hợp lệ.\nĐịnh dạng: https://www.reddit.com/r/.../comments/... hoặc https://redd.it/..."

        if target == "Bilibili":
            if RE_BILIBILI.match(url) or "bilibili.com" in url or "b23.tv" in url:
                return True, "bilibili"
            return False, "URL Bilibili không hợp lệ.\nĐịnh dạng: https://www.bilibili.com/video/BV... hoặc b23.tv/..."

        if target == "Pinterest (Pin & Image)":
            if is_pinterest_url(url) or is_direct_image_url(url):
                return True, "pinterest"
            return False, "URL Pinterest không hợp lệ.\nĐịnh dạng hỗ trợ: https://www.pinterest.com/pin/... hoặc pin.it/... hoặc i.pinimg.com/..."

        if target == "Rule34 / Booru (Image & Video)":
            if is_rule34_url(url) or is_direct_image_url(url):
                return True, "rule34"
            return False, "URL Rule34 / Booru không hợp lệ.\nĐịnh dạng hỗ trợ: rule34.xxx, rule34video.com, rule34.paheal.net, gelbooru..."

        if target == "Iwara (iwara.tv)":
            if is_iwara_url(url):
                return True, "iwara"
            return False, "URL Iwara không hợp lệ.\nĐịnh dạng hỗ trợ: https://www.iwara.tv/video/... hoặc https://ecchi.iwara.tv/..."

        if target == "Telegram (t.me)":
            if is_telegram_url(url):
                return True, "telegram"
            return False, "URL Telegram không hợp lệ.\nĐịnh dạng hỗ trợ: https://t.me/channel_name/1234 hoặc https://telegram.me/..."

        if target == "Zing MP3":
            if RE_ZINGMP3.match(url) or "zingmp3.vn" in url:
                return True, "zingmp3"
            return False, "URL Zing MP3 không hợp lệ.\nĐịnh dạng: https://zingmp3.vn/bai-hat/Ten-Bai/ZWZABC.html"

        if target == "Spotify":
            if RE_SPOTIFY.match(url) or "spotify.com" in url:
                return True, "spotify"
            return False, "URL Spotify không hợp lệ.\nĐịnh dạng: https://open.spotify.com/track/ID... hoặc /playlist/ID"

        if target == "Hình ảnh trực tiếp (PNG/JPG/GIF...)":
            if is_direct_image_url(url) or is_safe_remote_url(url):
                return True, "direct_image"
            return False, "URL Hình ảnh không hợp lệ.\nĐịnh dạng hỗ trợ: PNG, JPG, JPEG, GIF, WEBP, JNG, BMP, SVG..."

        if target == "Media trực tiếp (MP4/WebM/MP3...)":
            if is_direct_media_url(url) or is_safe_remote_url(url):
                return True, "direct_media"
            return False, "URL Media trực tiếp không hợp lệ.\nĐịnh dạng hỗ trợ: .mp4, .webm, .mkv, .mp3, .m4a, .wav..."

        if target == "Local Lab / Custom Stream (HLS/DASH)":
            if RE_LOCAL_STREAM.match(url) or is_safe_remote_url(url, allow_private=True):
                return True, "locallab"
            return False, "URL Stream không hợp lệ.\nĐịnh dạng: http(s)://host:port/...m3u8 hoặc ...mpd"

        if target == "Nền tảng khác / Universal (yt-dlp)":
            if is_safe_remote_url(url):
                return True, "universal"
            return False, "URL không hợp lệ hoặc vi phạm chính sách bảo mật mạng (chống SSRF)."

        # Fallback tự động nhận diện nếu người dùng chọn mục tiêu khác
        detected = auto_detect_platform(url)
        if detected and is_safe_remote_url(url):
            return True, "universal"

        return False, "Mục tiêu không xác định."

    # ── Analyze Video & Populate Detailed Formats & Thumbnail ─────────────
    def _on_analyze(self) -> None:
        """Phân tích link video để lấy danh sách độ phân giải thực tế & ảnh thumbnail."""
        if self._running or self._analyzing:
            return

        url = self.var_url.get().strip()
        target = self.var_target.get()
        valid, result = self._validate_url(url, target)
        if not valid:
            messagebox.showwarning("URL không hợp lệ", result)
            return

        self._analyzing = True
        self._current_info = None
        self.btn_analyze.config(state="disabled", text="⏳ Đang phân tích…")
        self.lbl_info_title.config(text="📌 Tiêu đề: Đang phân tích…")
        self.lbl_info_author.config(text="👤 Tác giả / Kênh: -")
        self.lbl_info_duration.config(text="⏱️ Thời lượng: -")
        self.lbl_info_subs.config(text="💬 Phụ đề: Đang kiểm tra…")
        self.lbl_info_status.config(text="⏳ Đang kết nối máy chủ & trích xuất định dạng…")
        self._set_status("🔍 Đang phân tích thông tin & định dạng video…")
        self.progress.config(mode="indeterminate")
        self.progress.start(15)

        cookie_browser = None
        cookie_file = None
        if result in ("twitter", "facebook", "zingmp3", "spotify"):
            method = self.var_cookie_method.get()
            if "trình duyệt" in method.lower() or method == "browser":
                cookie_browser = self.var_cookie_browser.get().strip() or None
            elif "file" in method.lower():
                cookie_file = self.var_cookie_file.get().strip() or None

        def _worker():
            try:
                is_pl, pl_target = is_playlist_url(url)

                # Xử lý Spotify riêng (hỗ trợ cả Track đơn và Playlist/Album)
                if result == "spotify":
                    if is_pl:
                        meta, entries = resolve_spotify_playlist_or_album(url)
                        if meta:
                            pil_img = load_thumbnail_pil(meta["thumbnail"]) if meta.get("thumbnail") else None

                            def _update_spotify_pl():
                                self._current_info = meta
                                self._display_thumbnail(pil_img, fallback_text="Spotify Playlist")
                                self.lbl_info_title.config(text=f"📌 Danh sách phát: {meta.get('title')}")
                                self.lbl_info_author.config(text=f"👤 Nghệ sĩ/Người tạo: {meta.get('author')}")
                                self.lbl_info_duration.config(text=f"🔢 Số lượng: {meta.get('total')} bài hát")
                                self.lbl_info_subs.config(text="💬 Phụ đề: Không áp dụng cho Spotify Audio")
                                self.lbl_info_status.config(
                                    text=f"✅ Đã nhận diện Spotify Playlist ({meta.get('total')} bài)! Bấm '📋 Nhập Playlist' để nạp vào hàng đợi."
                                )
                                self.var_media_mode.set("audio")
                                self._update_mode_ui()
                                self._set_status(STATUS_READY)

                            self.ui_dispatch(_update_spotify_pl)
                            return
                        else:
                            self.ui_dispatch(
                                lambda: self.lbl_info_status.config(
                                    text="❌ Không thể lấy danh sách bài từ Spotify Playlist."
                                )
                            )
                            return

                    track_info = resolve_spotify_track(url)
                    if track_info:
                        pil_img = load_thumbnail_pil(track_info["thumbnail"]) if track_info.get("thumbnail") else None

                        def _update_spotify():
                            self._current_info = track_info
                            self._display_thumbnail(pil_img, fallback_text="Spotify Track")
                            self.lbl_info_title.config(text=f"📌 Tiêu đề: {track_info['title']}")
                            artists = ", ".join(track_info.get("artists", [])) or "Không rõ"
                            self.lbl_info_author.config(text=f"👤 Nghệ sĩ: {artists}")
                            dur_str = format_duration(track_info.get("duration"))
                            self.lbl_info_duration.config(text=f"⏱️ Thời lượng: {dur_str}")
                            self.lbl_info_subs.config(text="💬 Phụ đề: Không áp dụng cho Spotify Audio")
                            self.lbl_info_status.config(
                                text="✅ Đã nhận diện Spotify Track! Đã chuyển sang chế độ Audio."
                            )
                            self.var_media_mode.set("audio")
                            self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_update_spotify)
                    else:
                        self.ui_dispatch(
                            lambda: self.lbl_info_status.config(
                                text="❌ Không thể lấy metadata bài hát từ Spotify."
                            )
                        )
                    return

                # ── 1. Xử lý Direct Image (PNG, JPG, GIF, WebP, JNG, BMP...) ──
                if result == "direct_image" or is_direct_image_url(url):
                    img_info = resolve_direct_image_info(url)
                    if img_info:
                        pil_img = load_thumbnail_pil(url)

                        def _update_img_ui():
                            self._current_info = img_info
                            self._display_thumbnail(pil_img, fallback_text="Image Preview")
                            self.lbl_info_title.config(text=f"📌 Hình ảnh: {img_info.get('title')}")
                            self.lbl_info_author.config(text=f"👤 Nguồn: {img_info.get('uploader')}")
                            dim = img_info.get("dimensions") or "Không rõ"
                            fsize = format_bytes(img_info.get("filesize")) or "Không rõ"
                            self.lbl_info_duration.config(text=f"📐 Kích thước: {dim} | Dung lượng: {fsize}")
                            self.lbl_info_subs.config(text=f"💬 Định dạng: {img_info.get('format')} (Ảnh trực tiếp)")
                            self.lbl_info_status.config(
                                text=f"✅ Đã nhận diện hình ảnh trực tiếp ({img_info.get('format')})! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu."
                            )
                            self.var_media_mode.set("image")
                            self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_update_img_ui)
                        return
                    else:
                        self.ui_dispatch(
                            lambda: self.lbl_info_status.config(
                                text="❌ Không thể kết nối hoặc đọc thông tin hình ảnh từ URL này."
                            )
                        )
                        return

                # ── 2. Xử lý Pinterest (Pin & Image / Video) ─────────────────
                if result == "pinterest" or is_pinterest_url(url):
                    pin_info = resolve_pinterest_media(url, cookie_browser, cookie_file)
                    if pin_info and pin_info.get("media_url"):
                        pil_img = load_thumbnail_pil(pin_info.get("thumbnail") or pin_info.get("media_url"))

                        def _update_pin_ui():
                            self._current_info = pin_info
                            self._display_thumbnail(pil_img, fallback_text="Pinterest Media")
                            self.lbl_info_title.config(text=f"📌 {pin_info.get('title')}")
                            self.lbl_info_author.config(text=f"👤 Nguồn: {pin_info.get('uploader')}")
                            fsize = format_bytes(pin_info.get("filesize")) if pin_info.get("filesize") else "Master Tier"
                            self.lbl_info_duration.config(text=f"📐 ID: {pin_info.get('id')} | Dung lượng: {fsize}")
                            m_type = pin_info.get("media_type", "image").upper()
                            ext = pin_info.get("ext", "jpg").upper()
                            self.lbl_info_subs.config(text=f"💬 Định dạng: {ext} (Pinterest Master {m_type})")
                            self.lbl_info_status.config(
                                text=f"✅ Đã trích xuất Pinterest Master ({m_type} {ext}) chất lượng cao nhất! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu."
                            )
                            if m_type == "IMAGE":
                                self.var_media_mode.set("image")
                                self._update_mode_ui()
                            elif m_type == "VIDEO":
                                self.var_media_mode.set("video")
                                self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_update_pin_ui)
                        return

                # ── 3. Xử lý Rule34 / Booru (Image & Video) ───────────────────
                if result == "rule34" and not ("rule34video.com" in url.lower() and "/videos/" in url.lower()):
                    r34_info = resolve_rule34_post(url)
                    if r34_info and r34_info.get("media_url"):
                        thumb_to_load = r34_info.get("thumbnail") or r34_info.get("media_url")
                        pil_img = load_thumbnail_pil(thumb_to_load) if thumb_to_load else None

                        def _update_r34_ui():
                            self._current_info = r34_info
                            self._display_thumbnail(pil_img, fallback_text="Rule34 Media")
                            self.lbl_info_title.config(text=f"📌 {r34_info.get('title')}")
                            self.lbl_info_author.config(text=f"👤 Tác giả / Nguồn: {r34_info.get('uploader')}")
                            tags_str = ", ".join(r34_info.get("tags", [])) or "-"
                            self.lbl_info_duration.config(text=f"🏷️ Thẻ: {tags_str}")
                            m_type = r34_info.get("media_type", "image").upper()
                            ext = r34_info.get("ext", "jpg").upper()
                            self.lbl_info_subs.config(text=f"💬 Phụ đề: Không áp dụng ({m_type} {ext})")
                            self.lbl_info_status.config(
                                text=f"✅ Đã trích xuất nội dung Rule34 ({m_type} {ext})! Sẵn sàng tải về."
                            )
                            if m_type == "IMAGE":
                                self.var_media_mode.set("image")
                                self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_update_r34_ui)
                        return

                # ── 3. Xử lý Facebook Photo (Ảnh bài viết /photo/?fbid=...) ───
                if (result == "facebook" or "facebook.com" in url.lower() or "fb.com" in url.lower()) and (
                    any(k in url.lower() for k in ["/photo", "fbid=", "/photos/"])
                ):
                    fb_photo_info = resolve_facebook_photo(url, cookie_browser, cookie_file)
                    if fb_photo_info and fb_photo_info.get("media_url"):
                        pil_img = load_thumbnail_pil(fb_photo_info["media_url"])

                        def _update_fb_photo_ui():
                            self._current_info = fb_photo_info
                            self._display_thumbnail(pil_img, fallback_text="Facebook Photo")
                            self.lbl_info_title.config(text=f"📌 {fb_photo_info.get('title')}")
                            self.lbl_info_author.config(text=f"👤 Nguồn: {fb_photo_info.get('uploader')}")
                            self.lbl_info_duration.config(text=f"📐 ID Ảnh: {fb_photo_info.get('id')}")
                            img_count = len(fb_photo_info.get("images", []))
                            if img_count > 1:
                                self.lbl_info_subs.config(text=f"💬 Định dạng: JPEG (Album {img_count} ảnh)")
                                self.lbl_info_status.config(
                                    text=f"✅ Đã trích xuất Album Facebook ({img_count} ảnh) thành công! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu trọn bộ."
                                )
                            else:
                                self.lbl_info_subs.config(text="💬 Định dạng: JPEG (Hình ảnh Facebook)")
                                self.lbl_info_status.config(
                                    text="✅ Đã trích xuất hình ảnh Facebook Photo thành công! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu."
                                )
                            self.var_media_mode.set("image")
                            self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_update_fb_photo_ui)
                        return

                # Các nền tảng còn lại qua yt-dlp API
                opts = {
                    "skip_download": True,
                    "quiet": True,
                    "noplaylist": not is_pl,
                    "extract_flat": True if is_pl else False,
                    "playlist_items": f"1:{MAX_PLAYLIST_ITEMS}" if is_pl else None,
                }
                if cookie_browser:
                    opts["cookiesfrombrowser"] = (cookie_browser,)
                elif cookie_file and Path(cookie_file).is_file():
                    opts["cookiefile"] = str(cookie_file)

                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)

                if not info:
                    self.ui_dispatch(
                        lambda: self.lbl_info_status.config(
                            text="❌ Không thể lấy thông tin từ URL này."
                        )
                    )
                    return

                # Xử lý nếu là Playlist (YouTube, Zing MP3)
                if info.get("_type") == "playlist" or is_pl:
                    pl_title = info.get("title") or "Danh sách phát"
                    uploader = info.get("uploader") or info.get("channel") or info.get("artist") or "Không rõ"
                    entries = [e for e in (info.get("entries") or []) if e]
                    entries_count = len(entries)
                    thumb_url = info.get("thumbnail")
                    pil_img = load_thumbnail_pil(thumb_url) if thumb_url else None

                    def _update_pl_ui():
                        self._current_info = info
                        self._display_thumbnail(pil_img, fallback_text="Playlist")
                        self.lbl_info_title.config(text=f"📌 Danh sách phát: {pl_title}")
                        self.lbl_info_author.config(text=f"👤 Kênh / Tác giả: {uploader}")
                        self.lbl_info_duration.config(text=f"🔢 Số lượng: {entries_count} mục")
                        self.lbl_info_subs.config(text="💬 Phụ đề: Sẽ tải theo cài đặt của từng video")
                        self.lbl_info_status.config(
                            text=f"✅ Đã nhận diện Playlist ({entries_count} mục)! Bấm '📋 Nhập Playlist' để nạp vào hàng đợi."
                        )
                        self._set_status(STATUS_READY)

                    self.ui_dispatch(_update_pl_ui)
                    return

                # Trích xuất dữ liệu video đơn
                title = info.get("title") or "Không có tiêu đề"
                uploader = info.get("uploader") or info.get("channel") or info.get("artist") or "Không rõ"
                duration_sec = info.get("duration")
                duration_str = format_duration(duration_sec)
                thumb_url = info.get("thumbnail")

                # Tải thumbnail xem trước dạng PIL Image (160x90)
                pil_img = load_thumbnail_pil(thumb_url) if thumb_url else None

                # Phân tích danh sách độ phân giải có sẵn từ formats
                formats = info.get("formats", [])
                res_map: dict[int, dict] = {}
                for f in formats:
                    h = f.get("height")
                    if not h or not isinstance(h, int) or h <= 0:
                        continue
                    vcodec = f.get("vcodec")
                    if vcodec == "none":
                        continue
                    fps = f.get("fps")
                    filesize = f.get("filesize") or f.get("filesize_approx")
                    if h not in res_map:
                        res_map[h] = {"fps": fps, "filesize": filesize}
                    else:
                        cur = res_map[h]
                        if (fps and (not cur.get("fps") or fps > cur["fps"])) or (
                            filesize and not cur.get("filesize")
                        ):
                            cur["fps"] = fps or cur.get("fps")
                            cur["filesize"] = filesize or cur.get("filesize")

                sorted_heights = sorted(res_map.keys(), reverse=True)
                res_items: list[str] = []

                if sorted_heights:
                    max_h = sorted_heights[0]
                    res_items.append(f"Tốt nhất / Tự động (Cao nhất: {max_h}p)")
                    for h in sorted_heights:
                        item = res_map[h]
                        if h >= 2160:
                            tag = "4K UHD"
                        elif h >= 1440:
                            tag = "2K QHD"
                        elif h >= 1080:
                            tag = "Full HD"
                        elif h >= 720:
                            tag = "HD"
                        elif h >= 480:
                            tag = "SD"
                        else:
                            tag = "Thấp"

                        fps_str = (
                            f" - {int(item['fps'])}fps"
                            if item.get("fps") and item["fps"] > 30
                            else ""
                        )
                        size_str = (
                            f" (~{format_bytes(item['filesize'])})"
                            if item.get("filesize")
                            else ""
                        )
                        res_items.append(f"{h}p ({tag}){fps_str}{size_str}")
                else:
                    res_items = [
                        "Tốt nhất / Tự động (Cao nhất)",
                        "1080p (Full HD)",
                        "720p (HD)",
                        "480p (SD)",
                        "360p",
                    ]

                # Phân tích danh sách phụ đề có sẵn (an toàn tránh TypeError/AttributeError)
                sub_dict = info.get("subtitles")
                auto_sub_dict = info.get("automatic_captions")
                if not isinstance(sub_dict, dict):
                    sub_dict = {}
                if not isinstance(auto_sub_dict, dict):
                    auto_sub_dict = {}
                all_subs = set(list(sub_dict.keys()) + list(auto_sub_dict.keys()))

                sub_labels = []
                if any(isinstance(s, str) and s.startswith("vi") for s in all_subs):
                    sub_labels.append("Tiếng Việt (vi)")
                if any(isinstance(s, str) and s.startswith("en") for s in all_subs):
                    sub_labels.append("Tiếng Anh (en)")
                for s in sorted(all_subs):
                    if isinstance(s, str) and not s.startswith("vi") and not s.startswith("en") and len(sub_labels) < 4:
                        sub_labels.append(s)

                if sub_labels:
                    subs_str = ", ".join(sub_labels)
                    if len(all_subs) > len(sub_labels):
                        subs_str += f" (+{len(all_subs) - len(sub_labels)} ngôn ngữ khác)"
                else:
                    subs_str = "Không có phụ đề gốc"

                def _apply_ui():
                    self._current_info = info
                    self._display_thumbnail(pil_img, fallback_text="No Thumbnail")

                    # Cập nhật thông tin text
                    title_clean = title if len(title) <= 85 else title[:82] + "…"
                    self.lbl_info_title.config(text=f"📌 Tiêu đề: {title_clean}")
                    self.lbl_info_author.config(text=f"👤 Tác giả / Kênh: {uploader}")
                    self.lbl_info_duration.config(text=f"⏱️ Thời lượng: {duration_str}")
                    self.lbl_info_subs.config(text=f"💬 Phụ đề: {subs_str}")

                    # Cập nhật danh sách combobox độ phân giải
                    self.cmb_video_res["values"] = res_items
                    if res_items:
                        self.var_video_res.set(res_items[0])

                    if hasattr(self, "lbl_trim_hint"):
                        if duration_str and duration_str != "Không rõ":
                            self.lbl_trim_hint.config(text=f"(Tổng: {duration_str}, vd: 00:30)")
                        else:
                            self.lbl_trim_hint.config(text="(vd: 01:30 - 02:45)")

                    self.lbl_info_status.config(
                        text=f"✅ Đã tải thông tin thành công! Tìm thấy {len(sorted_heights)} độ phân giải khả dụng."
                    )
                    self._set_status(STATUS_READY)

                self.ui_dispatch(_apply_ui)

            except Exception as e:
                raw_err = str(e)
                err_text = clean_ansi_escape(raw_err)

                # Fallback cho Twitter nếu gặp lỗi No video could be found
                if result == "twitter" and ("No video could be found" in err_text or "No media found" in err_text):
                    fallback_info = extract_twitter_fallback(url)
                    if fallback_info:
                        if fallback_info.get("media_type") in ("image", "album") or fallback_info.get("images"):
                            info = fallback_info
                            fb_thumb = info.get("thumbnail") or info.get("media_url")
                            fb_img = load_thumbnail_pil(fb_thumb) if fb_thumb else None

                            def _apply_tw_photo_ui():
                                self._current_info = info
                                self._display_thumbnail(fb_img, fallback_text="Twitter Photo")
                                fb_title = info.get("title") or "Twitter Photo"
                                fb_title_clean = fb_title if len(fb_title) <= 85 else fb_title[:82] + "…"
                                fb_uploader = info.get("uploader") or "Twitter"
                                img_count = len(info.get("images", []))
                                self.lbl_info_title.config(text=f"📌 Tiêu đề: {fb_title_clean}")
                                self.lbl_info_author.config(text=f"👤 Tác giả: {fb_uploader}")
                                if img_count > 1:
                                    self.lbl_info_duration.config(text=f"⏱️ Media: ALBUM ({img_count} ảnh)")
                                    self.lbl_info_subs.config(text=f"💬 Định dạng: {info.get('ext', 'png').upper()} (Twitter Carousel)")
                                    self.lbl_info_status.config(
                                        text=f"✅ Đã trích xuất trọn bộ {img_count} ảnh Twitter Master! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu."
                                    )
                                else:
                                    self.lbl_info_duration.config(text="⏱️ Media: HÌNH ẢNH")
                                    self.lbl_info_subs.config(text=f"💬 Định dạng: {info.get('ext', 'png').upper()} (Twitter Master)")
                                    self.lbl_info_status.config(
                                        text="✅ Đã trích xuất ảnh Twitter Master thành công! Sẵn sàng tải về."
                                    )
                                self.var_media_mode.set("image")
                                self._update_mode_ui()
                                self._set_status(STATUS_READY)

                            self.ui_dispatch(_apply_tw_photo_ui)
                            return
                        elif fallback_info.get("formats"):
                            info = fallback_info
                            fb_thumb = info.get("thumbnail")
                            fb_img = load_thumbnail_pil(fb_thumb) if fb_thumb else None

                            def _apply_fallback_ui():
                                self._current_info = info
                                self._display_thumbnail(fb_img, fallback_text="No Thumbnail")

                                fb_title = info.get("title") or "Twitter Video"
                                fb_title_clean = fb_title if len(fb_title) <= 85 else fb_title[:82] + "…"
                                fb_uploader = info.get("uploader") or "Twitter"
                                fb_dur_str = format_duration(info.get("duration"))

                                self.lbl_info_title.config(text=f"📌 Tiêu đề: {fb_title_clean}")
                                self.lbl_info_author.config(text=f"👤 Tác giả / Kênh: {fb_uploader}")
                                self.lbl_info_duration.config(text=f"⏱️ Thời lượng: {fb_dur_str}")
                                self.lbl_info_subs.config(text="💬 Phụ đề: Không có phụ đề gốc")

                                res_items = ["Tốt nhất / Tự động (Cao nhất)"]
                                for f in info.get("formats", []):
                                    h = f.get("height")
                                    if h:
                                        res_items.append(f"{h}p (Gốc)")
                                self.cmb_video_res["values"] = res_items
                                self.var_video_res.set(res_items[0])

                                self.lbl_info_status.config(
                                    text="✅ Đã trích xuất thông tin video Twitter thành công qua luồng dự phòng!"
                                )
                                self._set_status(STATUS_READY)

                            self.ui_dispatch(_apply_fallback_ui)
                            return

                # Fallback cho Telegram nếu yt-dlp không trích xuất được (do bài viết chứa hình ảnh/album)
                if result == "telegram" or is_telegram_url(url):
                    tg_info = resolve_telegram_media(url)
                    if tg_info and tg_info.get("media_url"):
                        info = tg_info
                        tg_thumb = info.get("thumbnail") or info.get("media_url")
                        tg_img = load_thumbnail_pil(tg_thumb) if tg_thumb else None

                        def _apply_tg_fallback_ui():
                            self._current_info = info
                            self._display_thumbnail(tg_img, fallback_text="Telegram")

                            tg_title = info.get("title") or "Telegram Post"
                            tg_uploader = info.get("uploader") or "Telegram"
                            m_type = info.get("media_type", "image").upper()
                            img_count = len(info.get("images", []))

                            self.lbl_info_title.config(text=f"📌 Tiêu đề: {tg_title}")
                            self.lbl_info_author.config(text=f"👤 {tg_uploader}")
                            if img_count > 1:
                                self.lbl_info_duration.config(text=f"⏱️ Media: ALBUM ({img_count} ảnh)")
                                self.lbl_info_subs.config(text="💬 Định dạng: JPEG (Telegram Carousel)")
                                self.lbl_info_status.config(
                                    text=f"✅ Đã trích xuất Album Telegram ({img_count} ảnh) thành công! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu trọn bộ."
                                )
                            else:
                                self.lbl_info_duration.config(text=f"⏱️ Media: {m_type}")
                                self.lbl_info_subs.config(text="💬 Phụ đề: Không áp dụng")
                                self.lbl_info_status.config(
                                    text=f"✅ Đã trích xuất {m_type} Telegram thành công! Sẵn sàng tải về."
                                )

                            if m_type in ("IMAGE", "ALBUM"):
                                self.var_media_mode.set("image")
                                self._update_mode_ui()

                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_apply_tg_fallback_ui)
                        return

                # Fallback cho Facebook nếu là bài viết chứa ảnh
                if result == "facebook" or "facebook.com" in url.lower() or "fb.com" in url.lower():
                    fb_photo_info = resolve_facebook_photo(url, cookie_browser, cookie_file)
                    if fb_photo_info and fb_photo_info.get("media_url"):
                        pil_img = load_thumbnail_pil(fb_photo_info["media_url"])

                        def _apply_fb_fallback_ui():
                            self._current_info = fb_photo_info
                            self._display_thumbnail(pil_img, fallback_text="Facebook Photo")
                            self.lbl_info_title.config(text=f"📌 {fb_photo_info.get('title')}")
                            self.lbl_info_author.config(text=f"👤 Nguồn: {fb_photo_info.get('uploader')}")
                            self.lbl_info_duration.config(text=f"📐 ID Ảnh: {fb_photo_info.get('id')}")
                            img_count = len(fb_photo_info.get("images", []))
                            if img_count > 1:
                                self.lbl_info_subs.config(text=f"💬 Định dạng: JPEG (Album {img_count} ảnh)")
                                self.lbl_info_status.config(
                                    text=f"✅ Đã trích xuất Album Facebook ({img_count} ảnh) thành công! Bấm '🚀 BẮT ĐẦU TẢI VỀ' để lưu trọn bộ."
                                )
                            else:
                                self.lbl_info_subs.config(text="💬 Định dạng: JPEG (Hình ảnh Facebook)")
                                self.lbl_info_status.config(
                                    text="✅ Đã trích xuất hình ảnh Facebook Photo thành công qua luồng dự phòng!"
                                )
                            self.var_media_mode.set("image")
                            self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_apply_fb_fallback_ui)
                        return

                # Fallback cho Pinterest nếu yt-dlp báo lỗi
                if result == "pinterest" or is_pinterest_url(url):
                    pin_fallback = resolve_pinterest_media(url, cookie_browser, cookie_file)
                    if pin_fallback and pin_fallback.get("media_url"):
                        pil_img = load_thumbnail_pil(pin_fallback.get("thumbnail") or pin_fallback.get("media_url"))

                        def _apply_pin_fallback_ui():
                            self._current_info = pin_fallback
                            self._display_thumbnail(pil_img, fallback_text="Pinterest Media")
                            self.lbl_info_title.config(text=f"📌 {pin_fallback.get('title')}")
                            self.lbl_info_author.config(text=f"👤 Nguồn: {pin_fallback.get('uploader')}")
                            fsize = format_bytes(pin_fallback.get("filesize")) if pin_fallback.get("filesize") else "Master Tier"
                            self.lbl_info_duration.config(text=f"📐 ID: {pin_fallback.get('id')} | Dung lượng: {fsize}")
                            m_type = pin_fallback.get("media_type", "image").upper()
                            ext = pin_fallback.get("ext", "jpg").upper()
                            self.lbl_info_subs.config(text=f"💬 Định dạng: {ext} (Pinterest Master {m_type})")
                            self.lbl_info_status.config(
                                text=f"✅ Đã trích xuất Pinterest Master ({m_type} {ext}) thành công qua luồng tối ưu!"
                            )
                            if m_type == "IMAGE":
                                self.var_media_mode.set("image")
                                self._update_mode_ui()
                            elif m_type == "VIDEO":
                                self.var_media_mode.set("video")
                                self._update_mode_ui()
                            self._set_status(STATUS_READY)

                        self.ui_dispatch(_apply_pin_fallback_ui)
                        return

                # Nếu lỗi khác hoặc không thể fallback
                self._current_info = None
                if "No video could be found" in err_text or "No media found" in err_text:
                    user_msg = "Bài viết không chứa luồng video hợp lệ (có thể là ảnh tĩnh hoặc bài viết bị giới hạn độ tuổi/NSFW cần đăng nhập)"
                else:
                    cleaned_err = re.sub(r"^(?:ERROR:\s*)?(?:\[[^\]]+\]\s*)?", "", err_text).strip()
                    user_msg = cleaned_err or err_text

                def _apply_err_ui():
                    self._display_thumbnail(None, fallback_text="No Thumbnail")
                    self.lbl_info_title.config(text="📌 Tiêu đề: (Không thể phân tích)")
                    self.lbl_info_author.config(text="👤 Tác giả / Kênh: -")
                    self.lbl_info_duration.config(text="⏱️ Thời lượng: -")
                    self.lbl_info_subs.config(text="💬 Phụ đề: -")
                    self.lbl_info_status.config(
                        text=f"❌ Không thể phân tích: {user_msg}"
                    )
                    self._set_status(STATUS_ERROR)

                self.ui_dispatch(_apply_err_ui)
            finally:
                def _reset_btn():
                    self._analyzing = False
                    self.btn_analyze.config(state="normal", text="🔍 Phân tích Video")
                    self.progress.stop()
                self.ui_dispatch(_reset_btn)

        threading.Thread(target=_worker, daemon=True).start()

    # ── Start Download Execution ──────────────────────────────────────────
    def _on_start(self, _from_queue: bool = False) -> None:
        if self._running or self._analyzing:
            return

        url = self.var_url.get().strip()
        target = self.var_target.get()
        save_dir = self.var_save.get().strip()

        # Validate URL
        valid, result = self._validate_url(url, target)
        if not valid:
            messagebox.showwarning("URL không hợp lệ", result)
            if _from_queue and self._queue_processing:
                # Đánh dấu lỗi trong queue và tiếp tục
                if 0 <= self._current_queue_index < len(self._download_queue):
                    self._download_queue[self._current_queue_index]["status"] = QUEUE_ERROR
                    self._download_queue[self._current_queue_index]["error"] = result
                    self._refresh_queue_ui()
                self.after(500, self._process_next_queue_item)
            return

        # Validate Save Dir
        if not save_dir:
            messagebox.showwarning("Thư mục", "Vui lòng chọn thư mục lưu trữ.")
            return

        ok, msg = preflight_disk_check(save_dir)
        if not ok:
            messagebox.showerror("Lỗi ổ đĩa", msg)
            if _from_queue and self._queue_processing:
                self._queue_processing = False
            return

        # Nếu là playlist và nhấn 'Bắt đầu tải về' trực tiếp (không qua hàng đợi)
        if not _from_queue:
            is_pl, pl_target = is_playlist_url(url)
            if is_pl:
                ans = messagebox.askyesnocancel(
                    "Phát hiện Danh sách phát (Playlist)",
                    f"Liên kết này chứa nhiều video / bài hát trong Danh sách phát ({target}).\n\n"
                    "• [Yes]: Nạp toàn bộ vào Hàng đợi và bắt đầu tải lần lượt (Khuyến nghị)\n"
                    "• [No]: Chỉ tải video/bài hát đầu tiên\n"
                    "• [Cancel]: Hủy bỏ thao tác",
                )
                if ans is None:
                    return
                elif ans is True:
                    self._add_playlist_to_queue(url_override=url, prompt=False)
                    self.after(500, self._start_queue_processing)
                    return

        # Lấy tham số cấu hình
        media_mode = self.var_media_mode.get()  # "video" | "audio"

        # Container
        container_raw = self.var_container.get()
        if "mp4" in container_raw.lower():
            video_format = "mp4"
            audio_codec = "mp3"
        elif "mkv" in container_raw.lower():
            video_format = "mkv"
            audio_codec = "mp3"
        elif "webm" in container_raw.lower():
            video_format = "webm"
            audio_codec = "opus"
        elif "m4a" in container_raw.lower():
            video_format = "mp4"
            audio_codec = "m4a"
        elif "wav" in container_raw.lower():
            video_format = "mp4"
            audio_codec = "wav"
        elif "flac" in container_raw.lower():
            video_format = "mkv"
            audio_codec = "flac"
        elif "opus" in container_raw.lower():
            video_format = "webm"
            audio_codec = "opus"
        else:
            video_format = "mp4"
            audio_codec = "mp3"

        # Độ phân giải
        video_resolution = self.var_video_res.get()

        # Audio bitrate
        audio_bitrate = self.var_audio_bitrate.get()

        # Phụ đề
        enable_subtitles = self.var_enable_subs.get()
        sub_lang_raw = self.var_sub_lang.get()
        if "Việt" in sub_lang_raw and "Anh" in sub_lang_raw:
            sub_lang = "both"
        elif "Việt" in sub_lang_raw:
            sub_lang = "vi"
        elif "Anh" in sub_lang_raw:
            sub_lang = "en"
        elif "Gốc" in sub_lang_raw:
            sub_lang = "orig"
        else:
            sub_lang = "all"

        embed_subtitles = self.var_embed_subs.get()

        # Thumbnail
        enable_thumbnail = self.var_enable_thumb.get()
        embed_thumbnail = self.var_embed_thumb.get()

        # Image processing parameters
        img_transcode = self.var_img_transcode.get()
        img_res = self.var_img_res.get()
        img_compress = self.var_img_compress.get()
        img_frame_grabber = self.var_img_frame_grabber.get()
        img_strip_exif = self.var_img_strip_exif.get()
        img_palette_opt = self.var_img_palette_opt.get()
        img_create_thumb = self.var_img_create_thumb.get()
        img_hd_sharpness = self.var_img_hd_sharpness.get()
        img_ai_upscale = self.var_img_ai_upscale.get()
        img_download_all = self.var_img_download_all.get()

        # Cookies
        cookie_browser = None
        cookie_file = None
        if result in ("twitter", "facebook", "zingmp3", "spotify", "tiktok", "instagram", "reddit", "bilibili", "iwara", "pinterest"):
            method = self.var_cookie_method.get()
            if "trình duyệt" in method.lower() or method == "browser":
                cookie_browser = self.var_cookie_browser.get().strip() or None
            elif "file" in method.lower():
                cookie_file = self.var_cookie_file.get().strip() or None

        # ── Reset pause/cancel events ─────────────────────────────────────
        self._pause_event.set()       # Không tạm dừng
        self._cancel_event.clear()    # Không hủy
        self._pause_start_time = None
        if self._pause_timeout_after_id:
            self.after_cancel(self._pause_timeout_after_id)
            self._pause_timeout_after_id = None

        # Lưu thông tin cho post-download action & security scan
        self._last_downloaded_dir = save_dir
        # Tính prefix dựa trên target
        _prefix_map = {
            "youtube": "youtube_",
            "twitter": "twitter_",
            "facebook": "facebook_",
            "tiktok": "tiktok_",
            "instagram": "instagram_",
            "reddit": "reddit_",
            "bilibili": "bilibili_",
            "pinterest": "pinterest_",
            "rule34": "rule34_",
            "iwara": "iwara_",
            "telegram": "telegram_",
            "zingmp3": "zingmp3_",
            "spotify": "spotify_",
            "direct_image": "image_",
            "direct_media": "media_",
            "locallab": "",
            "universal": "media_",
        }
        self._last_downloaded_prefix = _prefix_map.get(result, "")

        # Video / Audio Clip Trimming
        clip_start = self.var_clip_start.get().strip() if hasattr(self, "var_clip_start") else ""
        clip_end = self.var_clip_end.get().strip() if hasattr(self, "var_clip_end") else ""

        # Lock UI & Enable controls
        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_start_queue.config(state="disabled")
        self.btn_analyze.config(state="disabled")
        self.btn_pause.config(state="normal", text="⏸️ Tạm dừng")
        self.btn_cancel.config(state="normal")
        self.progress.config(mode="indeterminate")
        self.progress.start(15)

        engine = AuditEngine(
            url=url,
            save_dir=save_dir,
            target=result,
            media_mode=media_mode,
            video_format=video_format,
            video_resolution=video_resolution,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            enable_subtitles=enable_subtitles,
            subtitle_lang=sub_lang,
            embed_subtitles=embed_subtitles,
            enable_thumbnail=enable_thumbnail,
            embed_thumbnail=embed_thumbnail,
            clip_start=clip_start,
            clip_end=clip_end,
            img_transcode=img_transcode,
            img_res=img_res,
            img_compress=img_compress,
            img_frame_grabber=img_frame_grabber,
            img_strip_exif=img_strip_exif,
            img_palette_opt=img_palette_opt,
            img_create_thumb=img_create_thumb,
            img_hd_sharpness=img_hd_sharpness,
            img_ai_upscale=img_ai_upscale,
            img_download_all=img_download_all,
            on_status=self._set_status,
            on_progress=self._set_progress,
            on_finish=self._on_finish,
            cookie_browser=cookie_browser,
            cookie_file=cookie_file,
            pause_event=self._pause_event,
            cancel_event=self._cancel_event,
        )

        threading.Thread(target=engine.run, daemon=True).start()

