#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main entry point for ToolDowMp4 (Media Security Audit & Downloader).
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path when executed directly
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_app_logger
from app_gui import App


def main() -> None:
    """Khởi chạy ứng dụng Media Security Downloader GUI."""
    setup_app_logger()
    try:
        app = App()
        app.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
