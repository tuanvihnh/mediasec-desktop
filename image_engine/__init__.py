#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Image Processing Engine: Metadata, Color Restoration, AI Upscaling & Main Processing Pipeline.
"""

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
