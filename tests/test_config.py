#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for configuration persistence, logger, cleanup, and theming.
"""

import os
import tempfile
import unittest
from pathlib import Path

from utils.config import (
    DEFAULT_CONFIG,
    load_config,
    save_config,
    get_config_dir,
    get_config_file_path,
)
from utils.logger import setup_app_logger, get_logger, get_log_file_path
from utils.cleanup import cleanup_stale_artifacts
from app_gui.theme import DARK_PALETTE, LIGHT_PALETTE, detect_system_theme


class TestConfigAndSystem(unittest.TestCase):
    """Test configuration persistence, logger, cleanup, and theme engines."""

    def test_default_config_keys(self):
        self.assertIn("save_dir", DEFAULT_CONFIG)
        self.assertIn("target", DEFAULT_CONFIG)
        self.assertIn("theme_mode", DEFAULT_CONFIG)
        self.assertIn("media_mode", DEFAULT_CONFIG)
        self.assertIn("video_format", DEFAULT_CONFIG)

    def test_config_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp_xdg:
            orig_xdg = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = tmp_xdg
            try:
                # Initial load should return default config
                cfg = load_config()
                self.assertEqual(cfg["target"], "YouTube")

                # Modify and save
                cfg["target"] = "Twitter / X"
                cfg["theme_mode"] = "light"
                cfg["save_dir"] = "/tmp/my_downloads"
                ok = save_config(cfg)
                self.assertTrue(ok)

                # Re-load
                reloaded = load_config()
                self.assertEqual(reloaded["target"], "Twitter / X")
                self.assertEqual(reloaded["theme_mode"], "light")
                self.assertEqual(reloaded["save_dir"], "/tmp/my_downloads")
            finally:
                if orig_xdg is not None:
                    os.environ["XDG_CONFIG_HOME"] = orig_xdg
                else:
                    os.environ.pop("XDG_CONFIG_HOME", None)

    def test_logger_setup(self):
        logger = get_logger()
        self.assertIsNotNone(logger)
        self.assertEqual(logger.name, "tooldowmp4")
        log_file = get_log_file_path()
        self.assertTrue(str(log_file).endswith("app.log"))

    def test_cleanup_stale_artifacts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create a .tmp_clean file (should be deleted)
            stale_clean = tmp_path / "photo.jpg.tmp_clean"
            stale_clean.write_text("temporary data")

            # Create a cfg_*.tmp file (should be deleted)
            stale_cfg = tmp_path / "cfg_12345.tmp"
            stale_cfg.write_text("temporary config")

            # Create a regular media file (must NOT be deleted)
            regular_file = tmp_path / "video.mp4"
            regular_file.write_text("video content")

            # Run cleanup
            cleaned = cleanup_stale_artifacts([tmpdir], max_age_hours=0.0)
            self.assertGreaterEqual(cleaned, 2)
            self.assertFalse(stale_clean.exists())
            self.assertFalse(stale_cfg.exists())
            self.assertTrue(regular_file.exists())

    def test_theme_palettes(self):
        self.assertEqual(DARK_PALETTE["name"], "dark")
        self.assertEqual(LIGHT_PALETTE["name"], "light")
        self.assertIn("bg", DARK_PALETTE)
        self.assertIn("fg", DARK_PALETTE)
        self.assertIn("accent", DARK_PALETTE)

        sys_theme = detect_system_theme()
        self.assertIn(sys_theme, ("dark", "light"))


if __name__ == "__main__":
    unittest.main()
