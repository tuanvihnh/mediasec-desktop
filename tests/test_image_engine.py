#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for image_engine package.
"""

import os
import tempfile
import unittest

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from image_engine.metadata import (
    lossless_strip_jpeg_metadata,
    lossless_strip_png_metadata,
    lossless_strip_image_file_metadata,
)
from image_engine.color_restore import (
    restore_image_color_and_sharpness,
)
from image_engine.ai_upscaler import (
    detect_ai_upscale_engine,
)
from image_engine.processor import (
    process_downloaded_image,
)


class TestImageEngine(unittest.TestCase):
    """Test image enhancement and metadata stripping routines."""

    def test_restore_image_color_and_sharpness(self):
        if not HAS_PIL:
            self.skipTest("PIL/Pillow not installed")

        # Create a small RGB image
        img = Image.new("RGB", (64, 64), color=(100, 150, 200))
        enhanced = restore_image_color_and_sharpness(img)
        self.assertIsNotNone(enhanced)
        self.assertEqual(enhanced.size, (64, 64))
        self.assertEqual(enhanced.mode, "RGB")

        # Create an RGBA image
        img_rgba = Image.new("RGBA", (64, 64), color=(100, 150, 200, 128))
        enhanced_rgba = restore_image_color_and_sharpness(img_rgba)
        self.assertIsNotNone(enhanced_rgba)
        self.assertEqual(enhanced_rgba.size, (64, 64))

    def test_detect_ai_upscale_engine(self):
        engine_type, path = detect_ai_upscale_engine()
        # Should return a tuple (type, path_or_name)
        self.assertIn(engine_type, ("realesrgan-ncnn-vulkan", "realesrgan_ncnn", "waifu2x_ncnn", "onnxruntime", "lanczos_fallback", "none"))

    def test_lossless_strip_png_metadata(self):
        if not HAS_PIL:
            self.skipTest("PIL/Pillow not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            test_png = os.path.join(tmpdir, "test.png")
            img = Image.new("RGB", (32, 32), color=(255, 0, 0))
            img.save(test_png, format="PNG")

            # Test byte-level function
            with open(test_png, "rb") as f:
                raw_bytes = f.read()
            stripped_bytes = lossless_strip_png_metadata(raw_bytes)
            self.assertIsInstance(stripped_bytes, bytes)
            self.assertTrue(stripped_bytes.startswith(b"\x89PNG\r\n\x1a\n"))

            # Test file-level function
            ok = lossless_strip_image_file_metadata(test_png)
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(test_png))

    def test_process_downloaded_image_format_conversion(self):
        if not HAS_PIL:
            self.skipTest("PIL/Pillow not installed")

        with tempfile.TemporaryDirectory() as tmpdir:
            src_png = os.path.join(tmpdir, "sample.png")
            img = Image.new("RGB", (100, 100), color=(50, 100, 150))
            img.save(src_png, "PNG")

            # Transcode PNG -> JPG
            ok, res_path, artifacts = process_downloaded_image(
                source_path=src_png,
                transcode_format="JPG / JPEG (.jpg)",
                resolution_mode="Gốc / Master (Original 100%)",
                compress_quality="100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)",
                strip_exif=True,
                optimize_palette=False,
                frame_grabber="Tắt (Giữ nguyên toàn bộ tệp)",
                create_thumb=False,
                hd_sharpness=True,
                ai_upscale=False,
            )
            self.assertTrue(ok)
            self.assertTrue(os.path.exists(res_path))
            self.assertTrue(res_path.lower().endswith(".jpg"))


if __name__ == "__main__":
    unittest.main()
