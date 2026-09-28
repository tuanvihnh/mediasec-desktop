#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for core package.
"""

import threading
import unittest

from core.queue_manager import DownloadQueueManager
from core.audit_engine import AuditEngine
from utils.constants import (
    QUEUE_WAITING,
    QUEUE_COMPLETED,
    QUEUE_ERROR,
)


class TestCore(unittest.TestCase):
    """Test core business logic: Queue manager and AuditEngine setup."""

    def test_queue_manager_crud(self):
        qm = DownloadQueueManager(max_size=3)
        self.assertEqual(len(qm.items), 0)
        self.assertFalse(qm.is_full())

        # Add item 1
        ok, msg = qm.add("https://youtube.com/watch?v=11111111111", "YouTube", "YouTube", "Title 1")
        self.assertTrue(ok)
        self.assertEqual(len(qm.items), 1)

        # Add duplicate
        ok, msg = qm.add("https://youtube.com/watch?v=11111111111", "YouTube", "YouTube", "Title 1")
        self.assertFalse(ok)
        self.assertIn("đã có", msg)

        # Add item 2 and 3
        qm.add("https://youtube.com/watch?v=22222222222", "YouTube", "YouTube", "Title 2")
        qm.add("https://youtube.com/watch?v=33333333333", "YouTube", "YouTube", "Title 3")
        self.assertTrue(qm.is_full())

        # Over limit
        ok, msg = qm.add("https://youtube.com/watch?v=44444444444", "YouTube", "YouTube", "Title 4")
        self.assertFalse(ok)

        # Move item
        self.assertEqual(qm.items[0]["title"], "Title 1")
        self.assertEqual(qm.items[1]["title"], "Title 2")
        moved = qm.move_down(0)
        self.assertTrue(moved)
        self.assertEqual(qm.items[0]["title"], "Title 2")
        self.assertEqual(qm.items[1]["title"], "Title 1")

        moved_up = qm.move_up(1)
        self.assertTrue(moved_up)
        self.assertEqual(qm.items[0]["title"], "Title 1")

        # Summary
        qm.items[0]["status"] = QUEUE_COMPLETED
        qm.items[1]["status"] = QUEUE_ERROR
        completed, errors, pending = qm.get_summary()
        self.assertEqual(completed, 1)
        self.assertEqual(errors, 1)
        self.assertEqual(pending, 1)

        # Remove
        removed = qm.remove(0)
        self.assertEqual(removed["title"], "Title 1")
        self.assertEqual(len(qm.items), 2)

        # Clear
        qm.clear()
        self.assertEqual(len(qm.items), 0)

    def test_audit_engine_init(self):
        pause_event = threading.Event()
        cancel_event = threading.Event()

        engine = AuditEngine(
            url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            save_dir="/tmp",
            target="YouTube",
            media_mode="video",
            video_format="mp4",
            video_resolution="1080p",
            audio_codec="aac",
            audio_bitrate="192 kbps",
            enable_subtitles=False,
            subtitle_lang="None",
            embed_subtitles=False,
            enable_thumbnail=False,
            embed_thumbnail=False,
            clip_start="",
            clip_end="",
            img_transcode="Gốc (Giữ nguyên định dạng gốc)",
            img_res="Gốc / Master (Original 100%)",
            img_compress="100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)",
            img_frame_grabber="Tắt (Giữ nguyên toàn bộ tệp)",
            img_strip_exif=True,
            img_palette_opt=True,
            img_create_thumb=False,
            img_hd_sharpness=False,
            img_ai_upscale=False,
            img_download_all=False,
            on_status=lambda s: None,
            on_progress=lambda p: None,
            on_finish=lambda ok, msg: None,
            cookie_browser="None",
            cookie_file="",
            pause_event=pause_event,
            cancel_event=cancel_event,
        )

        self.assertEqual(engine.url, "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertEqual(engine.media_mode, "video")
        self.assertEqual(engine.video_format, "mp4")
        self.assertEqual(engine.target, "YouTube")
        self.assertFalse(engine.cancel_event.is_set())

    def test_audit_engine_ydl_opts(self):
        engine = AuditEngine(
            url="https://x.com/user/status/123456",
            save_dir="/tmp",
            target="twitter",
            media_mode="video",
            video_format="mp4",
            video_resolution="1080",
            audio_codec="mp3",
            audio_bitrate="192",
            enable_subtitles=False,
            subtitle_lang="vi",
            embed_subtitles=False,
            enable_thumbnail=False,
            embed_thumbnail=False,
            on_status=lambda s: None,
            on_progress=lambda p: None,
            on_finish=lambda ok, msg: None,
            clip_start="0.01",
            clip_end="0.04",
        )
        opts = engine._build_ydl_opts()
        self.assertFalse(opts["ignoreerrors"], "ignoreerrors MUST be False to prevent silent download failures")
        self.assertIn("postprocessor_hooks", opts)
        self.assertIn("download_ranges", opts)

    def test_find_downloaded_file(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = AuditEngine(
                url="https://x.com/user/status/123456",
                save_dir=tmpdir,
                target="twitter",
                media_mode="video",
                video_format="mp4",
                video_resolution="1080",
                audio_codec="mp3",
                audio_bitrate="192",
                enable_subtitles=False,
                subtitle_lang="vi",
                embed_subtitles=False,
                enable_thumbnail=False,
                embed_thumbnail=False,
                on_status=lambda s: None,
                on_progress=lambda p: None,
                on_finish=lambda ok, msg: None,
            )
            # Empty folder -> None
            self.assertIsNone(engine._find_downloaded_file("123456"))

            # Create an incomplete .part file -> Should still be None
            part_file = Path(tmpdir) / "twitter_123456.mp4.part"
            part_file.write_bytes(b"test data")
            self.assertIsNone(engine._find_downloaded_file("123456"))

            # Create valid file -> Should find it
            valid_file = Path(tmpdir) / "twitter_123456.mp4"
            valid_file.write_bytes(b"test data complete")
            found = engine._find_downloaded_file("123456")
            self.assertIsNotNone(found)
            self.assertEqual(found, valid_file)


if __name__ == "__main__":
    unittest.main()

