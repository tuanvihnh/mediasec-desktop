#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unit tests for extractors package.
"""

import unittest

from extractors.twitter import upgrade_twitter_image_url
from extractors.pinterest import upgrade_pinimg_url
from extractors.playlist import is_playlist_url
from extractors.subtitles import parse_sub_content


class TestExtractors(unittest.TestCase):
    """Test platform extractors, URL upgrading and subtitle parsers."""

    def test_upgrade_twitter_image_url(self):
        url = "https://pbs.twimg.com/media/Gabcdefg?format=jpg&name=small"
        
        # Test with prefer_png=True, probe_head=False
        orig_png = upgrade_twitter_image_url(url, prefer_png=True, probe_head=False)
        self.assertIn("name=orig", orig_png)
        self.assertIn("format=png", orig_png)

        # Test with prefer_png=False, probe_head=False
        orig_jpg = upgrade_twitter_image_url(url, prefer_png=False, probe_head=False)
        self.assertIn("name=orig", orig_jpg)
        self.assertIn("format=jpg", orig_jpg)

    def test_upgrade_pinimg_url_structure(self):
        url = "https://i.pinimg.com/236x/12/34/56/123456abcdef.jpg"
        best_url, ext, size = upgrade_pinimg_url(url)
        self.assertIsInstance(best_url, str)
        self.assertIsInstance(ext, str)
        self.assertIsInstance(size, int)

    def test_is_playlist_url(self):
        # YouTube playlist
        is_pl, plat = is_playlist_url("https://www.youtube.com/playlist?list=PL1234567890abcdef")
        self.assertTrue(is_pl)
        self.assertEqual(plat, "youtube")

        # Single YouTube video
        is_pl, plat = is_playlist_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        self.assertFalse(is_pl)

        # Spotify playlist / album
        is_pl, plat = is_playlist_url("https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M")
        self.assertTrue(is_pl)
        self.assertEqual(plat, "spotify")

        is_pl, plat = is_playlist_url("https://open.spotify.com/album/4aawyAB9vmqN3uQ7FjRGTy")
        self.assertTrue(is_pl)

        is_pl, plat = is_playlist_url("https://open.spotify.com/track/1234567890")
        self.assertFalse(is_pl)

        # Zing MP3 album / playlist
        is_pl, plat = is_playlist_url("https://zingmp3.vn/album/Top-100-Bai-Hat-Nhac-Tre-Hay-Nhat/ZWZB969E.html")
        self.assertTrue(is_pl)
        self.assertEqual(plat, "zingmp3")

        is_pl, plat = is_playlist_url("https://zingmp3.vn/bai-hat/Song/ZWZB008I.html")
        self.assertFalse(is_pl)

    def test_parse_sub_content_srt(self):
        srt_text = """1
00:00:01,000 --> 00:00:04,000
Hello world!

2
00:00:05,000 --> 00:00:08,000
Welcome to ToolDowMp4.
"""
        items = parse_sub_content(srt_text)
        self.assertEqual(len(items), 2)
        # items: [(time_str, text)]
        self.assertEqual(items[0][1], "Hello world!")
        self.assertEqual(items[1][1], "Welcome to ToolDowMp4.")

    def test_parse_sub_content_vtt(self):
        vtt_text = """WEBVTT

00:00:01.000 --> 00:00:04.000
Testing WebVTT format.
"""
        items = parse_sub_content(vtt_text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][1], "Testing WebVTT format.")


if __name__ == "__main__":
    unittest.main()
