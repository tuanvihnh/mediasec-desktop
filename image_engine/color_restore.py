#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Color & Contrast Restoration Engine (sRGB Preservation, HD UnsharpMask, Autocontrast).
"""

from __future__ import annotations

import io

try:
    from PIL import Image, ImageOps, ImageFilter, ImageCms
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def restore_image_color_and_sharpness(
    im: Image.Image,
    apply_hd_sharpness: bool = True,
    apply_srgb_convert: bool = True,
) -> Image.Image:
    """
    Module Xử lý & Khôi phục Màu sắc (Color & Contrast Restoration Engine):
    - Tự động convert không gian màu RGBA/CMYK sang sRGB chuẩn bảo toàn màu để ảnh không bị bợt màu trên màn hình Linux.
    - Sử dụng PIL.ImageOps.autocontrast và bộ lọc làm nét nhẹ ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3)
      khi người dùng chọn tùy chọn 'Tối ưu hóa ảnh (HD Sharpness)'.
    - Bảo toàn ICC profile và màu sắc nguyên bản.
    """
    if not HAS_PIL or im is None:
        return im

    result = im

    # 1. Chuẩn hóa không gian màu sang sRGB chuẩn bảo toàn màu (chống bợt màu trên Linux/X11/Wayland)
    if apply_srgb_convert:
        if result.mode == "CMYK":
            try:
                if HAS_PIL and hasattr(ImageCms, "createProfile"):
                    icc_bytes = result.info.get("icc_profile")
                    if icc_bytes:
                        src_profile = ImageCms.getOpenProfile(io.BytesIO(icc_bytes))
                    else:
                        src_profile = ImageCms.createProfile("sRGB")
                    dst_profile = ImageCms.createProfile("sRGB")
                    result = ImageCms.profileToProfile(result, src_profile, dst_profile, outputMode="RGB")
                else:
                    result = result.convert("RGB")
            except Exception:
                result = result.convert("RGB")
        elif result.mode in ("P", "LA"):
            if "transparency" in result.info or result.mode == "LA":
                result = result.convert("RGBA")
            else:
                result = result.convert("RGB")

    # 2. Áp dụng Autocontrast và UnsharpMask nhẹ (HD Sharpness)
    if apply_hd_sharpness:
        try:
            if result.mode == "RGBA":
                r, g, b, a = result.split()
                rgb = Image.merge("RGB", (r, g, b))
                rgb = ImageOps.autocontrast(rgb, cutoff=0.5)
                rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
                r2, g2, b2 = rgb.split()
                result = Image.merge("RGBA", (r2, g2, b2, a))
            elif result.mode == "RGB":
                result = ImageOps.autocontrast(result, cutoff=0.5)
                result = result.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
            elif result.mode == "L":
                result = ImageOps.autocontrast(result, cutoff=0.5)
                result = result.filter(ImageFilter.UnsharpMask(radius=1.5, percent=120, threshold=3))
        except Exception:
            pass

    return result
