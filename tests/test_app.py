#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for App GUI and entry point compatibility.
"""

import os
import unittest

from app_gui.app import App
import main
import media_security_downloader


class TestApp(unittest.TestCase):
    """Test App GUI instantiation and backwards compatibility."""

    def test_app_instantiation(self):
        if not os.environ.get("DISPLAY"):
            self.skipTest("No DISPLAY available for Tkinter GUI test")

        app = App()
        try:
            self.assertIsNotNone(app)
            self.assertTrue(hasattr(app, "_build_ui"))
            self.assertTrue(hasattr(app, "btn_start"))
            self.assertTrue(hasattr(app, "btn_analyze"))
            self.assertTrue(hasattr(app, "btn_add_queue"))
            self.assertTrue(hasattr(app, "btn_pause"))
            self.assertTrue(hasattr(app, "btn_cancel"))
            self.assertTrue(hasattr(app, "btn_install_ai"))
            self.assertTrue(hasattr(app, "_download_queue"))
        finally:
            app.destroy()

    def test_main_entrypoint(self):
        self.assertTrue(hasattr(main, "main"))
        self.assertTrue(callable(main.main))

    def test_backward_compatibility_facade(self):
        # Verify that all expected public symbols are exported by media_security_downloader
        expected_symbols = [
            "App",
            "AuditEngine",
            "DownloadQueueManager",
            "main",
            "parse_time_to_seconds",
            "format_duration",
            "format_bytes",
            "auto_detect_platform",
            "is_safe_remote_url",
            "validate_file_integrity",
            "upgrade_twitter_image_url",
            "upgrade_pinimg_url",
            "is_playlist_url",
            "restore_image_color_and_sharpness",
            "detect_ai_upscale_engine",
            "process_downloaded_image",
            "APP_TITLE",
            "APP_VERSION",
        ]
        for sym in expected_symbols:
            self.assertTrue(
                hasattr(media_security_downloader, sym),
                f"Missing expected symbol in facade: {sym}",
            )


if __name__ == "__main__":
    unittest.main()
