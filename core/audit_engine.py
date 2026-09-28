#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Core Download & Security Audit Engine: Multi-threaded yt-dlp API runner, Direct file grabber, DRM auditor.
"""

from __future__ import annotations

import os
import re
import time
import hashlib
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
import urllib.request
import urllib.error

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError, ExtractorError
except ImportError:
    YoutubeDL = None  # type: ignore[assignment,misc]
    DownloadError = Exception  # type: ignore[assignment,misc]
    ExtractorError = Exception  # type: ignore[assignment,misc]

from utils.constants import (
    SAFE_OUTTMPL,
    SAFE_EXTENSIONS,
    MAX_FILESIZE_BYTES,
    STATUS_READY,
    STATUS_CONNECTING,
    STATUS_AUDITING,
    STATUS_DRM,
    STATUS_DENIED,
    STATUS_COMPLETED,
    STATUS_ERROR,
    RE_TWITTER,
)
from utils.helpers import (
    clean_ansi_escape,
    format_bytes,
    parse_time_to_seconds,
    log_warn,
)
from utils.security import (
    preflight_disk_check,
    detect_drm_mpd,
    detect_drm_hls,
    check_cleartext_warning,
)
from utils.network import (
    download_direct_file,
    is_safe_remote_url,
    is_direct_image_url,
    is_rule34_url,
    is_telegram_url,
    is_pinterest_url,
)
from extractors.subtitles import translate_subtitles_file
from extractors.twitter import extract_twitter_fallback
from extractors.spotify import resolve_spotify_track
from extractors.pinterest import resolve_pinterest_media
from extractors.direct import resolve_direct_image_info
from extractors.booru import resolve_rule34_post
from extractors.telegram import resolve_telegram_media
from extractors.facebook import resolve_facebook_photo
from image_engine.processor import process_downloaded_image


class AuditEngine:
    """Thực thi kiểm thử và tải media an toàn qua yt-dlp Python API."""

    def __init__(
        self,
        url: str,
        save_dir: str,
        target: str,
        media_mode: str,          # "video" | "audio" | "image"
        video_format: str,        # "mp4" | "mkv" | "webm"
        video_resolution: str,    # e.g. "1080", "720", "best", etc.
        audio_codec: str,         # "mp3" | "m4a" | "wav" | "flac" | "opus"
        audio_bitrate: str,       # "320" | "256" | "192" | "128" | "96" | "auto"
        enable_subtitles: bool,   # True / False
        subtitle_lang: str,       # "vi" | "en" | "both" | "orig" | "all"
        embed_subtitles: bool,    # True / False
        enable_thumbnail: bool,   # True / False (lưu file .jpg)
        embed_thumbnail: bool,    # True / False (nhúng vào file media)
        on_status: callable,      # type: ignore[type-arg]
        on_progress: callable,    # type: ignore[type-arg]
        on_finish: callable,      # type: ignore[type-arg]
        cookie_browser: Optional[str] = None,
        cookie_file: Optional[str] = None,
        pause_event: Optional[threading.Event] = None,
        cancel_event: Optional[threading.Event] = None,
        img_transcode: str = "Gốc (Giữ nguyên định dạng gốc)",
        img_res: str = "Gốc / Master (Original 100%)",
        img_compress: str = "92% (Chất lượng rất cao - Khuyến nghị)",
        img_frame_grabber: str = "Tắt (Giữ nguyên toàn bộ tệp)",
        img_strip_exif: bool = True,
        img_palette_opt: bool = True,
        img_create_thumb: bool = False,
        img_hd_sharpness: bool = False,
        img_ai_upscale: bool = False,
        img_download_all: bool = True,
        clip_start: Optional[str] = None,
        clip_end: Optional[str] = None,
    ) -> None:
        self.url = url
        self.save_dir = save_dir
        self.target = target
        self.media_mode = media_mode
        self.video_format = video_format.lower()
        self.video_resolution = video_resolution
        self.audio_codec = audio_codec.lower()
        self.audio_bitrate = audio_bitrate
        self.enable_subtitles = enable_subtitles
        self.subtitle_lang = subtitle_lang
        self.embed_subtitles = embed_subtitles
        self.enable_thumbnail = enable_thumbnail
        self.embed_thumbnail = embed_thumbnail
        self.clip_start = clip_start.strip() if (clip_start and clip_start.strip()) else None
        self.clip_end = clip_end.strip() if (clip_end and clip_end.strip()) else None
        self._on_status = on_status
        self._on_progress = on_progress
        self._on_finish = on_finish
        self.cookie_browser = cookie_browser
        self.cookie_file = cookie_file
        # Cấu hình xử lý hình ảnh qua Pillow
        self.img_transcode = img_transcode
        self.img_res = img_res
        self.img_compress = img_compress
        self.img_frame_grabber = img_frame_grabber
        self.img_strip_exif = img_strip_exif
        self.img_palette_opt = img_palette_opt
        self.img_create_thumb = img_create_thumb
        self.img_hd_sharpness = img_hd_sharpness
        self.img_ai_upscale = img_ai_upscale
        self.img_download_all = img_download_all
        # Pause/Resume: event.is_set() = đang chạy; event.clear() = tạm dừng
        self.pause_event = pause_event or threading.Event()
        if not self.pause_event.is_set():
            self.pause_event.set()  # Mặc định: đang chạy
        # Cancel: event.is_set() = đã hủy
        self.cancel_event = cancel_event or threading.Event()
        self._downloaded_files: list[str] = []

    def _apply_image_processing(
        self,
        dest_file: str,
        title: str = "",
        extra_info: Optional[dict] = None,
    ) -> None:
        """Thực thi pipeline xử lý ảnh hậu kỳ (Scale, Transcode, Compress, Strip EXIF, HD Sharpness, AI Upscale, Frame Grabber)."""
        extra_info = extra_info or {}
        self._on_status("⚙️ Đang xử lý hậu kỳ hình ảnh (Pillow Pipeline)…")
        ok_proc, final_path, extra_artifacts = process_downloaded_image(
            source_path=dest_file,
            transcode_format=self.img_transcode,
            resolution_mode=self.img_res,
            compress_quality=self.img_compress,
            strip_exif=self.img_strip_exif,
            optimize_palette=self.img_palette_opt,
            frame_grabber=self.img_frame_grabber,
            create_thumb=self.img_create_thumb,
            hd_sharpness=self.img_hd_sharpness,
            ai_upscale=self.img_ai_upscale,
            on_status=self._on_status,
        )
        if not ok_proc:
            self._on_status(STATUS_ERROR)
            self._on_finish(False, f"Lỗi xử lý hình ảnh: {final_path}")
            return

        self._on_status(STATUS_COMPLETED)
        self._on_progress(100)

        # Trích xuất thông tin ảnh cuối cùng
        final_ext = os.path.splitext(final_path)[1].lstrip(".").upper()
        file_sz = os.path.getsize(final_path)
        dim_str = ""
        if HAS_PIL:
            try:
                with Image.open(final_path) as im:
                    dim_str = f"{im.size[0]}x{im.size[1]}"
            except Exception:
                pass

        details = [
            "Tải và xử lý hình ảnh hoàn tất thành công!",
            "",
            f"📌 Tiêu đề: {title or os.path.basename(final_path)}",
            f"🖼️ Định dạng xuất: {final_ext}" + (f" ({dim_str})" if dim_str else ""),
            f"📁 Đã lưu: {final_path}",
            f"💾 Dung lượng: {format_bytes(file_sz)}",
        ]
        if self.img_res and "Gốc" not in self.img_res:
            details.append(f"📐 Chế độ phân giải: {self.img_res}")
        if self.img_compress:
            details.append(f"🗜️ Mức nén: {self.img_compress}")
        if self.img_hd_sharpness or "HD Sharpness" in self.img_res:
            details.append("✨ Tối ưu hóa nét & Màu sắc: Đã áp dụng (HD Sharpness)")
        if self.img_ai_upscale or "AI Super-Resolution" in self.img_res:
            details.append("🚀 AI Super-Resolution: Đã kích hoạt (x2/x4 Detail)")
        if self.img_strip_exif:
            details.append("🛡️ Siêu dữ liệu EXIF/GPS: Đã loại bỏ an toàn (Bảo toàn ICC)")
        if extra_artifacts:
            details.append(f"📦 Tệp phụ kèm theo: {len(extra_artifacts)} tệp")
            for art in extra_artifacts[:5]:
                details.append(f"   • {os.path.basename(art)}")
            if len(extra_artifacts) > 5:
                details.append(f"   ... và {len(extra_artifacts) - 5} tệp khác")

        finish_msg = "\n".join(details)
        self._on_finish(True, finish_msg)

    def _apply_multi_image_download_and_processing(
        self,
        image_urls: list[str],
        base_prefix: str,
        title: str = "",
        extra_info: Optional[dict] = None,
    ) -> None:
        """
        Tải và xử lý hàng loạt toàn bộ ảnh trong một Album / Carousel (Twitter, Telegram, Facebook).
        """
        extra_info = extra_info or {}
        unique_urls: list[str] = []
        for u in image_urls:
            if u and u not in unique_urls:
                unique_urls.append(u)

        total = len(unique_urls)
        if total == 0:
            self._on_status(STATUS_ERROR)
            self._on_finish(False, "Không tìm thấy URL hình ảnh hợp lệ trong album.")
            return

        if total == 1 or not self.img_download_all:
            first_url = unique_urls[0]
            ext = "png" if "format=png" in first_url else "jpg"
            dest_file = os.path.join(self.save_dir, f"{base_prefix}.{ext}")
            self._on_status("🖼️ Đang tải hình ảnh…")
            ok, res_path = download_direct_file(
                url=first_url,
                save_path=dest_file,
                max_bytes=MAX_FILESIZE_BYTES,
                on_progress=self._on_progress,
                on_status=self._on_status,
                pause_event=self.pause_event,
                cancel_event=self.cancel_event,
            )
            if not ok:
                self._on_status(STATUS_ERROR)
                self._on_finish(False, res_path)
                return
            self._apply_image_processing(dest_file, title=title, extra_info=extra_info)
            return

        self._on_status(f"📚 Phát hiện Album / Carousel gồm {total} hình ảnh. Bắt đầu tải trọn bộ…")
        processed_files: list[str] = []
        all_artifacts: list[str] = []
        failed_count = 0

        for idx, img_url in enumerate(unique_urls, 1):
            if self.cancel_event.is_set():
                self._on_status("❌ Đã hủy tải Album.")
                self._on_finish(False, "Người dùng đã hủy quá trình tải Album.")
                return

            ext = "png" if "format=png" in img_url else "jpg"
            filename = f"{base_prefix}_{idx:02d}.{ext}"
            dest_file = os.path.join(self.save_dir, filename)

            self._on_status(f"🖼️ [{idx}/{total}] Đang tải ảnh ({idx}/{total})…")

            def _sub_progress(chunk_pct: float, current_idx=idx, total_imgs=total):
                base_pct = ((current_idx - 1) / total_imgs) * 100.0
                curr_img_pct = (chunk_pct / total_imgs)
                overall = min(100, int(base_pct + curr_img_pct))
                self._on_progress(overall)

            ok, res_path = download_direct_file(
                url=img_url,
                save_path=dest_file,
                max_bytes=MAX_FILESIZE_BYTES,
                on_progress=_sub_progress,
                on_status=self._on_status,
                pause_event=self.pause_event,
                cancel_event=self.cancel_event,
            )
            if not ok:
                failed_count += 1
                self._on_status(f"⚠️ Không tải được ảnh {idx}/{total}: {res_path}")
                continue

            self._on_status(f"⚙️ [{idx}/{total}] Đang xử lý hậu kỳ ảnh {idx}/{total}…")
            ok_proc, final_path, extra_artifacts = process_downloaded_image(
                source_path=dest_file,
                transcode_format=self.img_transcode,
                resolution_mode=self.img_res,
                compress_quality=self.img_compress,
                strip_exif=self.img_strip_exif,
                optimize_palette=self.img_palette_opt,
                frame_grabber=self.img_frame_grabber,
                create_thumb=self.img_create_thumb,
                hd_sharpness=self.img_hd_sharpness,
                ai_upscale=self.img_ai_upscale,
                on_status=self._on_status,
            )
            if ok_proc:
                processed_files.append(final_path)
                if extra_artifacts:
                    all_artifacts.extend(extra_artifacts)
            else:
                processed_files.append(dest_file)

        if not processed_files:
            self._on_status(STATUS_ERROR)
            self._on_finish(False, "Tất cả các ảnh trong album đều tải thất bại.")
            return

        self._on_status(STATUS_COMPLETED)
        self._on_progress(100)

        details = [
            f"🎉 Tải trọn bộ Album ({len(processed_files)}/{total} ảnh) hoàn tất thành công!",
            "",
            f"📌 Tiêu đề: {title or base_prefix}",
            f"📁 Thư mục lưu: {self.save_dir}",
            f"📚 Số lượng ảnh: {len(processed_files)}/{total} ảnh",
        ]
        if failed_count > 0:
            details.append(f"⚠️ Số ảnh lỗi không tải được: {failed_count}")
        if self.img_transcode and "Gốc" not in self.img_transcode:
            details.append(f"🖼️ Định dạng xuất: {self.img_transcode}")
        if self.img_res and "Gốc" not in self.img_res:
            details.append(f"📐 Chế độ phân giải: {self.img_res}")
        if self.img_compress:
            details.append(f"🗜️ Mức nén: {self.img_compress}")
        if self.img_hd_sharpness:
            details.append("✨ Tối ưu hóa nét & Màu sắc: Đã áp dụng (HD Sharpness)")
        if self.img_ai_upscale:
            details.append("🚀 AI Super-Resolution: Đã kích hoạt (x2/x4 Detail)")
        if self.img_strip_exif:
            details.append("🛡️ Siêu dữ liệu EXIF/GPS: Đã loại bỏ an toàn (Bảo toàn ICC)")

        details.append("")
        details.append("📋 Danh sách tệp đã lưu:")
        for pf in processed_files[:10]:
            details.append(f"   • {os.path.basename(pf)}")
        if len(processed_files) > 10:
            details.append(f"   ... và {len(processed_files) - 10} ảnh khác")

        if all_artifacts:
            details.append(f"📦 Tệp phụ kèm theo (Thumbs/Frames): {len(all_artifacts)} tệp")

        finish_msg = "\n".join(details)
        self._on_finish(True, finish_msg)

    def _progress_hook(self, d: dict) -> None:
        if self.cancel_event.is_set():
            raise DownloadError("Người dùng đã hủy tải xuống.")

        if not self.pause_event.is_set():
            self._on_status("⏸️ Tạm dừng – Nhấn ▶️ Tiếp tục để tiếp tục tải…")
            self.pause_event.wait()
            if self.cancel_event.is_set():
                raise DownloadError("Người dùng đã hủy tải xuống.")
            self._on_status("▶️ Đã tiếp tục tải…")

        status = d.get("status", "")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = downloaded / total * 100
                self._on_progress(pct)
                speed = d.get("speed")
                speed_str = f" – {speed / 1024:.0f} KB/s" if speed else ""
                self._on_status(f"Đang tải: {pct:.1f}%{speed_str}")
            else:
                self._on_status(f"Đang tải: {downloaded / 1024:.0f} KB")
        elif status == "finished":
            fn = d.get("filename")
            if fn and fn not in self._downloaded_files:
                self._downloaded_files.append(fn)
            self._on_progress(100)
            self._on_status("Đang hoàn thiện file & xử lý hậu kỳ…")

    def _postprocessor_hook(self, d: dict) -> None:
        """Ghi nhận tên file hoàn thiện sau khi FFmpeg postprocessor chạy xong."""
        if d.get("status") == "finished":
            info = d.get("info_dict") or {}
            fn = info.get("_filename") or info.get("filepath")
            if fn and fn not in self._downloaded_files:
                self._downloaded_files.append(fn)

    def _build_ydl_opts(self) -> dict:
        outtmpl = os.path.join(self.save_dir, SAFE_OUTTMPL)
        opts: dict = {
            "outtmpl": outtmpl,
            "progress_hooks": [self._progress_hook],
            "postprocessor_hooks": [self._postprocessor_hook],
            "max_filesize": MAX_FILESIZE_BYTES,
            "noplaylist": True,
            "continuedl": True,
            "part": True,
            "quiet": True,
            "no_warnings": False,
            "socket_timeout": 30,
            "retries": 3,
            "restrictfilenames": True,
            "ignoreerrors": False,
            "postprocessors": [],
        }

        if self.cookie_browser:
            opts["cookiesfrombrowser"] = (self.cookie_browser,)
        elif self.cookie_file:
            cookie_path = Path(self.cookie_file)
            if cookie_path.is_file():
                opts["cookiefile"] = str(cookie_path)

        effective_mode = "audio" if self.target == "spotify" else self.media_mode

        if effective_mode == "audio":
            opts["format"] = "bestaudio/best"
            pp_audio = {
                "key": "FFmpegExtractAudio",
                "preferredcodec": self.audio_codec or "mp3",
            }
            m_bitrate = re.search(r"(\d{2,3})", str(self.audio_bitrate))
            if m_bitrate:
                pp_audio["preferredquality"] = m_bitrate.group(1)
            elif self.audio_bitrate and self.audio_bitrate != "auto":
                pp_audio["preferredquality"] = str(self.audio_bitrate)
            opts["postprocessors"].append(pp_audio)
        else:
            m_h = re.search(r"(\d{3,4})", str(self.video_resolution))
            h = int(m_h.group(1)) if m_h else None
            container = self.video_format if self.video_format in ("mp4", "mkv", "webm") else "mp4"

            if h:
                if container == "mp4":
                    opts["format"] = (
                        f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]/"
                        f"bestvideo[height<={h}]+bestaudio/"
                        f"best[height<={h}][ext=mp4]/best[height<={h}]/best"
                    )
                elif container == "webm":
                    opts["format"] = (
                        f"bestvideo[height<={h}][ext=webm]+bestaudio[ext=webm]/"
                        f"bestvideo[height<={h}]+bestaudio/"
                        f"best[height<={h}]/best"
                    )
                else:
                    opts["format"] = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            else:
                if container == "mp4":
                    opts["format"] = (
                        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                        "bestvideo[ext=mp4]+bestaudio/bestvideo+bestaudio/best[ext=mp4]/best"
                    )
                elif container == "webm":
                    opts["format"] = (
                        "bestvideo[ext=webm]+bestaudio[ext=webm]/bestvideo+bestaudio/best"
                    )
                else:
                    opts["format"] = "bestvideo+bestaudio/best"

            opts["merge_output_format"] = container

        if self.enable_subtitles:
            opts["writesubtitles"] = True
            opts["writeautomaticsub"] = True
            opts["subtitlesformat"] = "srt"

            if self.subtitle_lang == "vi":
                opts["subtitleslangs"] = ["vi.*", "vi", "en.*", "en"]
            elif self.subtitle_lang == "en":
                opts["subtitleslangs"] = ["en.*", "en", "vi.*", "vi"]
            elif self.subtitle_lang == "both":
                opts["subtitleslangs"] = ["vi.*", "vi", "en.*", "en"]
            elif self.subtitle_lang == "all":
                opts["allsubtitles"] = True
            else:
                opts["subtitleslangs"] = ["all"]

            opts["postprocessors"].append({"key": "FFmpegSubtitlesConvertor", "format": "srt"})

            if effective_mode == "video" and self.embed_subtitles:
                opts["postprocessors"].append({"key": "FFmpegEmbedSubtitle"})

        if self.enable_thumbnail or self.embed_thumbnail:
            opts["writethumbnail"] = True
            opts["postprocessors"].append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})

            if self.embed_thumbnail:
                opts["postprocessors"].append({
                    "key": "EmbedThumbnail",
                    "already_have_thumbnail": bool(self.enable_thumbnail),
                })

        s_sec = parse_time_to_seconds(self.clip_start)
        e_sec = parse_time_to_seconds(self.clip_end)
        if s_sec is not None or e_sec is not None:
            s_time = s_sec if s_sec is not None else 0.0
            e_time = e_sec if e_sec is not None else float("inf")
            if e_time > s_time:
                try:
                    from yt_dlp.utils import download_range_func
                    opts["download_ranges"] = download_range_func(None, [(s_time, e_time)])
                    opts["force_keyframes_at_cuts"] = True
                except Exception as ex:
                    log_warn(f"Không thể kích hoạt download_ranges của yt-dlp: {ex}")

        return opts

    def _find_downloaded_file(self, target_id: str = "") -> Optional[Path]:
        """Kiểm tra và tìm file media đã tải thực tế trên đĩa."""
        p_dir = Path(self.save_dir)
        if not p_dir.is_dir():
            return None

        # 1. Kiểm tra các file đã ghi nhận từ yt-dlp hooks
        for fn in reversed(self._downloaded_files):
            p = Path(fn)
            if p.is_file() and p.stat().st_size > 0:
                return p
            # Postprocessors có thể đã đổi đuôi mở rộng
            parent_dir = p.parent
            base_stem = p.stem
            for sibling in parent_dir.glob(f"{base_stem}.*"):
                if sibling.is_file() and sibling.stat().st_size > 0 and not sibling.name.endswith((".part", ".ytdl", ".temp")):
                    return sibling

        # 2. Quét thư mục save_dir theo target_id nếu có
        if target_id:
            for p in p_dir.iterdir():
                if p.is_file() and target_id in p.name:
                    if not p.name.endswith((".part", ".ytdl", ".temp")):
                        try:
                            if p.stat().st_size > 0:
                                return p
                        except OSError:
                            pass

        # 3. Quét các file media vừa được ghi nhận trong 120 giây gần nhất
        now = time.time()
        for p in p_dir.iterdir():
            if p.is_file() and not p.name.endswith((".part", ".ytdl", ".temp")):
                ext = p.suffix.lstrip(".").lower()
                if ext in SAFE_EXTENSIONS:
                    try:
                        mtime = p.stat().st_mtime
                        if (now - mtime) < 120 and p.stat().st_size > 0:
                            return p
                    except OSError:
                        pass

        return None

    def _try_fallbacks(self, err_str: str) -> bool:
        """Thử kích hoạt fallback resolvers (Twitter, Facebook, v.v.) khi yt-dlp gặp lỗi."""
        # 1. Twitter / X fallback
        if self.target == "twitter" or RE_TWITTER.match(self.url) or "twitter.com" in self.url.lower() or "x.com" in self.url.lower():
            try:
                self._on_status("🔄 Đang thử trích xuất qua luồng Twitter dự phòng…")
                fb = extract_twitter_fallback(self.url)
            except Exception as ex:
                log_warn(f"Lỗi gọi extract_twitter_fallback: {ex}")
                fb = None

            if fb:
                if (fb.get("media_type") in ("image", "album") or fb.get("images")) and (fb.get("media_url") or fb.get("images")):
                    try:
                        images = fb.get("images") or [fb["media_url"]]
                        self._apply_multi_image_download_and_processing(
                            image_urls=images,
                            base_prefix=f"twitter_{fb['id']}",
                            title=fb.get("title", f"Twitter Photo #{fb['id']}"),
                            extra_info=fb,
                        )
                        return True
                    except Exception as ex:
                        log_warn(f"Lỗi tải ảnh Twitter fallback: {ex}")
                elif fb.get("url"):
                    try:
                        self._on_status("🔄 Đang thử tải qua luồng media Twitter dự phòng…")
                        direct_url = fb["url"]
                        opts = self._build_ydl_opts()
                        safe_tw_filename = f"twitter_{fb['id']}.%(ext)s"
                        opts["outtmpl"] = os.path.join(self.save_dir, safe_tw_filename)
                        opts["ignoreerrors"] = False
                        with YoutubeDL(opts) as ydl:
                            ret = ydl.download([direct_url])
                            if ret != 0:
                                raise DownloadError(f"yt-dlp fallback trả về mã lỗi: {ret}")

                        downloaded_file = self._find_downloaded_file(str(fb.get("id") or ""))
                        if not downloaded_file:
                            raise DownloadError(f"Không tìm thấy file tải về dự phòng cho tweet {fb['id']}")

                        self._on_status(STATUS_COMPLETED)
                        self._on_progress(100)
                        details = [
                            f"🎬 Tiêu đề: {fb.get('title')}",
                            f"👤 Tác giả: {fb.get('uploader')}",
                            f"📁 Thư mục lưu: {self.save_dir}",
                        ]
                        if self.media_mode == "video":
                            details.append(f"🎬 Định dạng: Video {self.video_format.upper()} (Độ phân giải: {self.video_resolution})")
                        else:
                            details.append(f"🎧 Định dạng: Audio {self.audio_codec.upper()} (Chất lượng: {self.audio_bitrate})")
                        if self.clip_start or self.clip_end:
                            trim_info = f"Từ {self.clip_start or '00:00'} đến {self.clip_end or 'hết'}"
                            details.append(f"✂️ Cắt đoạn (Trim): {trim_info}")

                        finish_msg = "Kiểm thử và tải về hoàn tất thành công (qua luồng dự phòng)!\n\n" + "\n".join(details)
                        self._on_finish(True, finish_msg)
                        return True
                    except Exception as ex:
                        log_warn(f"Lỗi tải video Twitter fallback: {ex}")

        # 2. Facebook photo fallback
        if self.target == "facebook" or "facebook.com" in self.url.lower() or "fb.com" in self.url.lower() or "fb.watch" in self.url.lower():
            fb_photo = resolve_facebook_photo(self.url, self.cookie_browser, self.cookie_file)
            if fb_photo and (fb_photo.get("media_url") or fb_photo.get("images")):
                try:
                    images = fb_photo.get("images") or [fb_photo["media_url"]]
                    self._apply_multi_image_download_and_processing(
                        image_urls=images,
                        base_prefix=f"facebook_{fb_photo['id']}",
                        title=fb_photo.get("title", f"Facebook Photo #{fb_photo['id']}"),
                        extra_info=fb_photo,
                    )
                    return True
                except Exception as ex:
                    log_warn(f"Lỗi tải Facebook photo fallback: {ex}")

        return False

    def _handle_subtitles_postprocess(self, info: dict) -> list[str]:
        results: list[str] = []
        if not self.enable_subtitles or self.subtitle_lang not in ("vi", "en", "both"):
            return results

        extractor = (info.get("extractor") or "media").lower()
        vid = info.get("id") or ""
        prefix = f"{extractor}_{vid}"

        p_dir = Path(self.save_dir)
        sub_files = list(p_dir.glob(f"{prefix}*.srt")) + list(p_dir.glob(f"{prefix}*.vtt"))

        vi_subs = [f for f in sub_files if ".vi." in f.name]
        en_subs = [f for f in sub_files if ".en." in f.name]

        if self.subtitle_lang == "vi":
            if vi_subs:
                results.append("Đã tải phụ đề gốc Tiếng Việt (.srt)")
            elif sub_files:
                src = sub_files[0]
                target_vi = str(p_dir / f"{prefix}.vi.srt")
                self._on_status(f"🌐 Đang dịch phụ đề ({src.name}) sang Tiếng Việt…")
                ok = translate_subtitles_file(
                    str(src),
                    target_vi,
                    target_lang="vi",
                    on_progress=lambda p: self._on_status(f"🌐 Đang dịch phụ đề Tiếng Việt: {p:.0f}%"),
                )
                if ok:
                    results.append("Đã dịch tự động sang phụ đề Tiếng Việt (.vi.srt)")
            else:
                results.append("Không tìm thấy luồng phụ đề gốc trên máy chủ để dịch")

        elif self.subtitle_lang == "en":
            if en_subs:
                results.append("Đã tải phụ đề gốc Tiếng Anh (.srt)")
            elif sub_files:
                src = sub_files[0]
                target_en = str(p_dir / f"{prefix}.en.srt")
                self._on_status(f"🌐 Đang dịch phụ đề ({src.name}) sang Tiếng Anh…")
                ok = translate_subtitles_file(
                    str(src),
                    target_en,
                    target_lang="en",
                    on_progress=lambda p: self._on_status(f"🌐 Đang dịch phụ đề Tiếng Anh: {p:.0f}%"),
                )
                if ok:
                    results.append("Đã dịch tự động sang phụ đề Tiếng Anh (.en.srt)")
            else:
                results.append("Không tìm thấy luồng phụ đề gốc trên máy chủ để dịch")

        elif self.subtitle_lang == "both":
            if vi_subs:
                results.append("Đã có phụ đề Tiếng Việt gốc")
            elif sub_files:
                src = en_subs[0] if en_subs else sub_files[0]
                target_vi = str(p_dir / f"{prefix}.vi.srt")
                self._on_status("🌐 Đang dịch phụ đề sang Tiếng Việt…")
                if translate_subtitles_file(str(src), target_vi, target_lang="vi"):
                    results.append("Đã tạo phụ đề Tiếng Việt (.vi.srt)")

            sub_files_updated = list(p_dir.glob(f"{prefix}*.srt")) + list(p_dir.glob(f"{prefix}*.vtt"))
            en_subs_updated = [f for f in sub_files_updated if ".en." in f.name]
            vi_subs_updated = [f for f in sub_files_updated if ".vi." in f.name]

            if en_subs_updated:
                results.append("Đã có phụ đề Tiếng Anh gốc")
            elif vi_subs_updated:
                target_en = str(p_dir / f"{prefix}.en.srt")
                self._on_status("🌐 Đang dịch phụ đề sang Tiếng Anh…")
                if translate_subtitles_file(str(vi_subs_updated[0]), target_en, target_lang="en"):
                    results.append("Đã tạo phụ đề Tiếng Anh (.en.srt)")

        return results

    def _audit_local_stream(self) -> tuple[bool, str]:
        self._on_status(STATUS_CONNECTING)
        parsed = urlparse(self.url)
        is_mpd = parsed.path.lower().endswith(".mpd")

        try:
            if HAS_REQUESTS:
                resp = requests.get(
                    self.url, timeout=15, allow_redirects=True, headers={"User-Agent": "AuditTool/1.0"}
                )
                status_code = resp.status_code
                if status_code == 401:
                    return False, f"HTTP 401 Unauthorized – Token không hợp lệ.\nURL: {self.url}"
                if status_code == 403:
                    return False, f"HTTP 403 Forbidden – Truy cập bị từ chối.\nURL: {self.url}"
                if status_code >= 400:
                    return False, f"HTTP {status_code} – Lỗi kết nối luồng."
                manifest_text = resp.text
            else:
                req = urllib.request.Request(self.url, headers={"User-Agent": "AuditTool/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    manifest_text = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as he:
            return False, f"HTTP {he.code} – {he.reason}"
        except Exception as exc:
            return False, f"Lỗi kết nối: {exc}"

        self._on_status(STATUS_AUDITING)

        drm_list = detect_drm_mpd(manifest_text) if is_mpd else detect_drm_hls(manifest_text)
        real_drm = [d for d in drm_list if "AES-128" not in d and "ClearKey" not in d]

        if real_drm:
            drm_names = ", ".join(real_drm)
            return False, f"Phát hiện nội dung bảo vệ bởi DRM [{drm_names}].\nTừ chối xử lý."

        cleartext_warning = ""
        if check_cleartext_warning(manifest_text, is_mpd):
            self._on_status("⚠ Cảnh báo Cleartext")
            cleartext_warning = "Cảnh báo: Luồng phát ở dạng Cleartext, có nguy cơ rò rỉ dữ liệu."

        audit_parts = ["Manifest hợp lệ – cho phép tải."]
        if cleartext_warning:
            audit_parts.append(cleartext_warning)
        if drm_list:
            audit_parts.append(f"Encryption info: {', '.join(drm_list)}")

        return True, "\n".join(audit_parts)

    def run(self) -> None:
        try:
            if YoutubeDL is None:
                self._on_finish(False, "yt-dlp chưa được cài đặt.\nChạy: pip install yt-dlp")
                return

            ok, msg = preflight_disk_check(self.save_dir)
            if not ok:
                self._on_finish(False, msg)
                return

            if self.clip_start or self.clip_end:
                s_sec = parse_time_to_seconds(self.clip_start) if self.clip_start else 0.0
                e_sec = parse_time_to_seconds(self.clip_end) if self.clip_end else float("inf")
                if self.clip_start and parse_time_to_seconds(self.clip_start) is None:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(
                        False,
                        f"Thời gian bắt đầu cắt không đúng định dạng: '{self.clip_start}'.\n"
                        "Ví dụ định dạng hợp lệ: 45 (giây), 01:30 (1 phút 30s), 00:02:15."
                    )
                    return
                if self.clip_end and parse_time_to_seconds(self.clip_end) is None:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(
                        False,
                        f"Thời gian kết thúc cắt không đúng định dạng: '{self.clip_end}'.\n"
                        "Ví dụ định dạng hợp lệ: 45 (giây), 01:30 (1 phút 30s), 00:02:15."
                    )
                    return
                if s_sec is not None and e_sec is not None and s_sec >= e_sec:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(
                        False,
                        f"Thời gian cắt không hợp lệ: Thời gian bắt đầu ({self.clip_start}) "
                        f"phải nhỏ hơn thời gian kết thúc ({self.clip_end})."
                    )
                    return

            audit_msg = ""
            if self.target == "locallab":
                can_go, audit_msg = self._audit_local_stream()
                if not can_go:
                    if "DRM" in audit_msg:
                        self._on_status(STATUS_DRM)
                    elif "401" in audit_msg or "403" in audit_msg:
                        self._on_status(STATUS_DENIED)
                    else:
                        self._on_status(STATUS_ERROR)
                    self._on_finish(False, audit_msg)
                    return

            if self.target == "spotify":
                if "/track/" not in self.url:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(
                        False,
                        "Tính năng tải Spotify hỗ trợ từng bài hát cụ thể (Track).\n\n"
                        "Vui lòng dán link bài hát: https://open.spotify.com/track/ID",
                    )
                    return

                self._on_status("🎵 Đang giải mã metadata bài hát Spotify…")
                track_info = resolve_spotify_track(self.url)
                if not track_info:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(False, "Không thể trích xuất thông tin bài hát từ link Spotify này.")
                    return

                track_title = track_info["title"]
                artists = track_info.get("artists", [])
                artist_str = " ".join(artists) if artists else ""
                search_query = f"ytsearch1:{artist_str} {track_title}".strip()

                self._on_status(f"🔍 Đã nhận diện: {track_title} – Đang tìm stream audio…")

                opts = self._build_ydl_opts()
                safe_spotify_filename = f"spotify_{track_info['id']}.%(ext)s"
                opts["outtmpl"] = os.path.join(self.save_dir, safe_spotify_filename)

                with YoutubeDL(opts) as ydl:
                    self._on_status(f"Đang tải audio ({self.audio_codec.upper()}): {track_title}…")
                    ydl.download([search_query])

                self._on_status(STATUS_COMPLETED)
                self._on_progress(100)

                artist_display = ", ".join(artists) if artists else "Không rõ"
                finish_msg = (
                    f"Tải bài hát Spotify hoàn tất!\n\n"
                    f"🎵 Bài hát: {track_title}\n"
                    f"🎤 Nghệ sĩ: {artist_display}\n"
                    f"🎧 Định dạng: {self.audio_codec.upper()} ({self.audio_bitrate})\n"
                    f"📁 Đã lưu: {self.save_dir}/spotify_{track_info['id']}.{self.audio_codec}\n"
                )
                self._on_finish(True, finish_msg)
                return

            if (self.target == "facebook" or "facebook.com" in self.url.lower() or "fb.com" in self.url.lower()) and (
                any(k in self.url.lower() for k in ["/photo", "fbid=", "/photos/"])
            ):
                self._on_status("📸 Đang trích xuất ảnh Facebook Photo…")
                fb_info = resolve_facebook_photo(self.url, self.cookie_browser, self.cookie_file)
                if fb_info and (fb_info.get("media_url") or fb_info.get("images")):
                    images = fb_info.get("images") or [fb_info["media_url"]]
                    fbid = fb_info.get("id", "fb")
                    self._apply_multi_image_download_and_processing(
                        image_urls=images,
                        base_prefix=f"facebook_{fbid}",
                        title=fb_info.get("title", f"Facebook Photo #{fbid}"),
                        extra_info=fb_info,
                    )
                    return
                else:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(
                        False,
                        "Không thể trích xuất link hình ảnh gốc từ Facebook Photo này.\n\n"
                        "💡 NGUYÊN NHÂN & GỢI Ý:\n"
                        "• Bài viết có thể ở chế độ Riêng tư (Private), Chỉ bạn bè, hoặc Nhóm kín (Private Group).\n"
                        "• Vui lòng mở rộng phần '🍪 Tùy chọn Cookie / Xác thực' bên dưới và chọn Cookie Browser (hoặc file cookies.txt) để xác thực và tải ảnh.",
                    )
                    return

            if self.target == "pinterest" or is_pinterest_url(self.url):
                self._on_status("📌 Đang trích xuất nội dung Pinterest chất lượng gốc…")
                pin_info = resolve_pinterest_media(self.url, self.cookie_browser, self.cookie_file)
                if pin_info and pin_info.get("media_url"):
                    media_url = pin_info["media_url"]
                    media_type = pin_info.get("media_type", "image")
                    ext = pin_info.get("ext", "jpg")
                    pin_id = pin_info.get("id", "pin")

                    if media_type == "image":
                        self._on_status(f"🖼️ Đang tải ảnh Pinterest Master #{pin_id}…")
                        dest_file = os.path.join(self.save_dir, f"pinterest_{pin_id}.{ext}")
                        ok, res_path = download_direct_file(
                            url=media_url,
                            save_path=dest_file,
                            max_bytes=MAX_FILESIZE_BYTES,
                            on_progress=self._on_progress,
                            on_status=self._on_status,
                            pause_event=self.pause_event,
                            cancel_event=self.cancel_event,
                        )
                        if not ok:
                            self._on_status(STATUS_ERROR)
                            self._on_finish(False, res_path)
                            return

                        self._apply_image_processing(
                            dest_file,
                            title=pin_info.get("title", f"Pinterest Pin #{pin_id}"),
                            extra_info=pin_info,
                        )
                        return
                    else:
                        self.url = media_url

            if self.target == "rule34" or is_rule34_url(self.url):
                self._on_status("🔍 Đang trích xuất nội dung Rule34 / Booru…")
                r34_info = resolve_rule34_post(self.url)
                if r34_info and r34_info.get("media_url"):
                    media_url = r34_info["media_url"]
                    media_type = r34_info.get("media_type", "image")
                    ext = r34_info.get("ext", "jpg")
                    post_id = r34_info.get("id", "media")

                    if media_type == "image":
                        self._on_status(f"🖼️ Đang tải ảnh/GIF Rule34 #{post_id}…")
                        dest_file = os.path.join(self.save_dir, f"rule34_{post_id}.{ext}")
                        ok, res_path = download_direct_file(
                            url=media_url,
                            save_path=dest_file,
                            max_bytes=MAX_FILESIZE_BYTES,
                            on_progress=self._on_progress,
                            on_status=self._on_status,
                            pause_event=self.pause_event,
                            cancel_event=self.cancel_event,
                        )
                        if not ok:
                            self._on_status(STATUS_ERROR)
                            self._on_finish(False, res_path)
                            return

                        self._apply_image_processing(
                            dest_file,
                            title=r34_info.get("title", f"Rule34 #{post_id}"),
                            extra_info=r34_info,
                        )
                        return
                    else:
                        self.url = media_url

            if self.target == "telegram" or is_telegram_url(self.url):
                self._on_status("📱 Đang trích xuất media Telegram…")
                tg_info = resolve_telegram_media(self.url)
                if tg_info and tg_info.get("media_url"):
                    if tg_info.get("media_type") in ("image", "album"):
                        images = tg_info.get("images") or [tg_info["media_url"]]
                        post_id = tg_info.get("id", "tg")
                        self._apply_multi_image_download_and_processing(
                            image_urls=images,
                            base_prefix=f"telegram_{post_id}",
                            title=tg_info.get("title", f"Telegram #{post_id}"),
                            extra_info=tg_info,
                        )
                        return
                    elif tg_info.get("media_type") == "video":
                        self.url = tg_info["media_url"]

            if (self.target == "twitter" or RE_TWITTER.match(self.url)) and self.media_mode == "image":
                self._on_status("🐦 Đang trích xuất ảnh Twitter Master…")
                tw_info = extract_twitter_fallback(self.url)
                if tw_info and (tw_info.get("media_type") in ("image", "album") or tw_info.get("images")):
                    images = tw_info.get("images") or [tw_info["media_url"]]
                    self._apply_multi_image_download_and_processing(
                        image_urls=images,
                        base_prefix=f"twitter_{tw_info['id']}",
                        title=tw_info.get("title", f"Twitter Photo #{tw_info['id']}"),
                        extra_info=tw_info,
                    )
                    return

            if self.target == "direct_image" or is_direct_image_url(self.url):
                self._on_status("🖼️ Đang chuẩn bị tải hình ảnh trực tiếp…")
                img_info = resolve_direct_image_info(self.url)
                download_url = (img_info.get("url") if img_info else None) or self.url
                ext = img_info.get("ext", "png") if img_info else "png"
                url_hash = hashlib.md5(download_url.encode()).hexdigest()[:10]
                clean_filename = f"image_{url_hash}.{ext}"
                dest_file = os.path.join(self.save_dir, clean_filename)

                self._on_status(f"Đang tải hình ảnh ({ext.upper()})…")
                ok, res_path = download_direct_file(
                    url=download_url,
                    save_path=dest_file,
                    max_bytes=MAX_FILESIZE_BYTES,
                    on_progress=self._on_progress,
                    on_status=self._on_status,
                    pause_event=self.pause_event,
                    cancel_event=self.cancel_event,
                )
                if not ok:
                    self._on_status(STATUS_ERROR)
                    self._on_finish(False, res_path)
                    return

                self._apply_image_processing(
                    dest_file,
                    title=img_info.get("title") if img_info else "Hình ảnh trực tiếp",
                    extra_info=img_info,
                )
                return

            self._on_status(STATUS_CONNECTING)
            opts = self._build_ydl_opts()

            with YoutubeDL(opts) as ydl:
                self._on_status(STATUS_AUDITING)
                info = ydl.extract_info(self.url, download=False)
                if not info:
                    raise DownloadError(f"Không thể trích xuất metadata từ {self.url}")

                if info.get("_has_drm"):
                    self._on_status(STATUS_DRM)
                    self._on_finish(
                        False, "Phát hiện nội dung được bảo vệ bởi DRM (yt-dlp report). Từ chối xử lý."
                    )
                    return

                self._on_status("Đang tải dữ liệu media…")
                dl_ret = ydl.download([self.url])
                if dl_ret != 0:
                    raise DownloadError(f"Quá trình tải về thất bại với mã lỗi: {dl_ret}")

            # Kiểm tra xác thực file media thực tế đã được lưu vào đĩa (chống báo thành công ảo)
            target_id = str(info.get("id") or "")
            downloaded_file = self._find_downloaded_file(target_id)
            if not downloaded_file:
                raise DownloadError(
                    f"Quá trình tải về không tạo ra file media hợp lệ trong thư mục {self.save_dir}."
                )

            sub_results = self._handle_subtitles_postprocess(info or {})

            self._on_status(STATUS_COMPLETED)
            self._on_progress(100)

            details = [f"📁 Thư mục lưu: {self.save_dir}"]
            if self.media_mode == "video":
                details.append(
                    f"🎬 Định dạng: Video {self.video_format.upper()} (Độ phân giải: {self.video_resolution})"
                )
            else:
                details.append(
                    f"🎧 Định dạng: Audio {self.audio_codec.upper()} (Chất lượng: {self.audio_bitrate})"
                )

            if self.clip_start or self.clip_end:
                trim_info = f"Từ {self.clip_start or '00:00'} đến {self.clip_end or 'hết'}"
                details.append(f"✂️ Cắt đoạn (Trim): {trim_info}")

            if self.enable_subtitles:
                sub_detail_str = "; ".join(sub_results) if sub_results else self.subtitle_lang
                details.append(f"💬 Phụ đề: {sub_detail_str}")

            if self.enable_thumbnail or self.embed_thumbnail:
                t_actions = []
                if self.enable_thumbnail:
                    t_actions.append("Lưu file ảnh bìa .jpg")
                if self.embed_thumbnail:
                    t_actions.append("Nhúng ảnh bìa vào file media")
                details.append(f"🖼️ Ảnh bìa: {', '.join(t_actions)}")

            finish_msg = "Kiểm thử và tải về hoàn tất thành công!\n\n" + "\n".join(details)
            if audit_msg and "Cảnh báo" in audit_msg:
                finish_msg += f"\n\n⚠ Kết quả Audit:\n{audit_msg}"

            self._on_finish(True, finish_msg)

        except DownloadError as exc:
            err_str = clean_ansi_escape(str(exc))
            if self._try_fallbacks(err_str):
                return

            if "No video could be found" in err_str or "No media found" in err_str:
                msg = (
                    "Bài viết không chứa luồng video hợp lệ "
                    "(có thể là ảnh tĩnh hoặc bài viết bị giới hạn độ tuổi/NSFW cần đăng nhập)."
                )
                if self.target in ("twitter", "facebook") and not self.cookie_browser and not self.cookie_file:
                    msg += (
                        "\n\n💡 GỢI Ý: Nếu bài viết nhạy cảm hoặc cần đăng nhập, "
                        "hãy chọn Cookie Browser hoặc nạp cookies.txt."
                    )
                self._on_status(STATUS_ERROR)
                self._on_finish(False, f"Không tìm thấy media.\n\nChi tiết: {msg}")
            elif "login" in err_str.lower() or "log in" in err_str.lower():
                self._on_status(STATUS_DENIED)
                self._on_finish(False, f"Nền tảng yêu cầu đăng nhập.\n\nChi tiết: {err_str}")
            elif "DRM" in err_str.upper():
                self._on_status(STATUS_DRM)
                self._on_finish(False, f"Phát hiện DRM – Luồng được bảo vệ.\n\n{err_str}")
            elif re.search(r"HTTP\s*(?:Error\s*)?40[13]\b", err_str, re.IGNORECASE):
                self._on_status(STATUS_DENIED)
                self._on_finish(False, f"HTTP Access Denied.\n\nChi tiết: {err_str}")
            else:
                self._on_status(STATUS_ERROR)
                self._on_finish(False, f"Lỗi tải:\n{err_str}")

        except ExtractorError as exc:
            err_str = clean_ansi_escape(str(exc))
            if self._try_fallbacks(err_str):
                return
            if "No video could be found" in err_str or "No media found" in err_str:
                msg = (
                    "Bài viết không chứa luồng video hợp lệ "
                    "(có thể là ảnh tĩnh hoặc bài viết bị giới hạn độ tuổi/NSFW cần đăng nhập)."
                )
                self._on_status(STATUS_ERROR)
                self._on_finish(False, f"Không tìm thấy media.\n\nChi tiết: {msg}")
            else:
                self._on_status(STATUS_ERROR)
                self._on_finish(False, f"Lỗi trích xuất:\n{err_str}")

        except Exception as exc:
            err_str = clean_ansi_escape(str(exc))
            if self._try_fallbacks(err_str):
                return
            self._on_status(STATUS_ERROR)
            self._on_finish(False, f"Lỗi không xác định:\n{err_str}")
