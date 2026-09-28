#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for utils package.
"""

import os
import tempfile
import unittest

from utils.constants import MAGIC_BYTES
from utils.helpers import (
    clean_ansi_escape,
    format_bytes,
    format_duration,
    parse_time_to_seconds,
)
from utils.network import (
    auto_detect_platform,
    is_direct_image_url,
    is_safe_remote_url,
)
from utils.security import (
    compute_file_sha256,
    validate_file_integrity,
)


class TestUtils(unittest.TestCase):
    """Test utility functions in utils package."""

    def test_parse_time_to_seconds(self):
        self.assertEqual(parse_time_to_seconds("00:01:23"), 83.0)
        self.assertEqual(parse_time_to_seconds("1:23"), 83.0)
        self.assertEqual(parse_time_to_seconds("45"), 45.0)
        self.assertEqual(parse_time_to_seconds("45s"), 45.0)
        self.assertEqual(parse_time_to_seconds("0.01"), 1.0)
        self.assertEqual(parse_time_to_seconds("0.04"), 4.0)
        self.assertEqual(parse_time_to_seconds("1.30"), 90.0)
        self.assertEqual(parse_time_to_seconds("10.5"), 10.5)
        self.assertEqual(parse_time_to_seconds("00:00:00"), 0.0)
        self.assertEqual(parse_time_to_seconds("01:02:03"), 3723.0)
        self.assertIsNone(parse_time_to_seconds(""))
        self.assertIsNone(parse_time_to_seconds("   "))
        self.assertIsNone(parse_time_to_seconds("invalid"))
        self.assertEqual(parse_time_to_seconds("-10"), 0.0)

    def test_format_duration(self):
        self.assertEqual(format_duration(0), "Không rõ")
        self.assertEqual(format_duration(83), "01:23")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500.0 B")
        self.assertEqual(format_bytes(1024), "1.0 KB")
        self.assertEqual(format_bytes(1048576), "1.0 MB")
        self.assertEqual(format_bytes(1073741824), "1.0 GB")

    def test_clean_ansi_escape(self):
        text_with_ansi = "\033[31mError message\033[0m"
        self.assertEqual(clean_ansi_escape(text_with_ansi), "Error message")

    def test_is_safe_remote_url(self):
        # SSRF checks
        self.assertFalse(is_safe_remote_url("http://127.0.0.1/test"))
        self.assertFalse(is_safe_remote_url("http://localhost:8080"))
        self.assertFalse(is_safe_remote_url("http://10.0.0.1/admin"))
        self.assertFalse(is_safe_remote_url("http://192.168.1.1/secret"))
        self.assertFalse(is_safe_remote_url("ftp://example.com/file"))
        self.assertFalse(is_safe_remote_url("file:///etc/passwd"))

        # Safe URLs
        self.assertTrue(is_safe_remote_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(is_safe_remote_url("https://pbs.twimg.com/media/abc.jpg"))

    def test_auto_detect_platform(self):
        self.assertEqual(auto_detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ"), "YouTube")
        self.assertEqual(auto_detect_platform("https://youtu.be/dQw4w9WgXcQ"), "YouTube")
        self.assertEqual(auto_detect_platform("https://twitter.com/user/status/1234567890"), "Twitter / X")
        self.assertEqual(auto_detect_platform("https://x.com/user/status/1234567890"), "Twitter / X")
        self.assertEqual(auto_detect_platform("https://www.tiktok.com/@user/video/1234567890"), "TikTok")
        self.assertEqual(auto_detect_platform("https://open.spotify.com/track/123"), "Spotify")
        self.assertEqual(auto_detect_platform("https://zingmp3.vn/bai-hat/Song-Title/ZWZB008I.html"), "Zing MP3")
        self.assertEqual(auto_detect_platform("https://example.com/pic.png"), "Hình ảnh trực tiếp (PNG/JPG/GIF...)")

    def test_is_direct_image_url(self):
        self.assertTrue(is_direct_image_url("https://example.com/photo.png"))
        self.assertTrue(is_direct_image_url("https://example.com/photo.jpg?size=large"))
        self.assertTrue(is_direct_image_url("https://example.com/photo.webp"))
        self.assertFalse(is_direct_image_url("https://example.com/video.mp4"))

    def test_validate_file_integrity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Valid PNG
            png_file = os.path.join(tmpdir, "test.png")
            with open(png_file, "wb") as f:
                f.write(MAGIC_BYTES["png"][0] + b"\x00" * 20)
            valid, msg = validate_file_integrity(png_file)
            self.assertTrue(valid)

            # Valid JPEG
            jpg_file = os.path.join(tmpdir, "test.jpg")
            with open(jpg_file, "wb") as f:
                f.write(MAGIC_BYTES["jpg"][0] + b"\x00" * 20)
            valid, msg = validate_file_integrity(jpg_file)
            self.assertTrue(valid)

            # Corrupted / Spoofed file (executable disguised as mp4)
            fake_mp4 = os.path.join(tmpdir, "malicious.mp4")
            with open(fake_mp4, "wb") as f:
                f.write(b"MZ\x90\x00" + b"\x00" * 20)
            valid, msg = validate_file_integrity(fake_mp4)
            self.assertFalse(valid)
            self.assertTrue(any("NGUY HIỂM" in m or "Magic bytes" in m for m in msg))

    def test_compute_file_sha256(self):
        with tempfile.NamedTemporaryFile("wb", delete=False) as f:
            f.write(b"hello world")
            path = f.name
        try:
            # sha256 of b"hello world"
            expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
            self.assertEqual(compute_file_sha256(path), expected)
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
