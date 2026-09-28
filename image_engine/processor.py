#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Main Image Processing Pipeline: Transcoding, Compression, Master Pass-Through, Frame Grabber, Thumbnails.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Optional

try:
    from PIL import Image, ImageSequence, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from utils.security import harden_file_permissions
from image_engine.metadata import lossless_strip_image_file_metadata
from image_engine.color_restore import restore_image_color_and_sharpness
from image_engine.ai_upscaler import run_ai_super_resolution


def process_downloaded_image(
    source_path: str,
    transcode_format: str = "Gốc (Giữ nguyên định dạng gốc)",
    resolution_mode: str = "Gốc / Master (Original 100%)",
    compress_quality: str = "100% (Gốc / Bit-Exact 99-100% - Khuyến nghị)",
    strip_exif: bool = True,
    optimize_palette: bool = True,
    frame_grabber: str = "Tắt (Giữ nguyên toàn bộ tệp)",
    create_thumb: bool = False,
    hd_sharpness: bool = False,
    ai_upscale: bool = False,
    on_status: Optional[callable] = None,
) -> tuple[bool, str, list[str]]:
    """
    Xử lý hậu kỳ hình ảnh an toàn và chuyên sâu qua thư viện Pillow (PIL):
    - Format Transcoding: Chuyển đổi định dạng (.png, .jpg, .webp, .gif, .bmp, .ico, .tiff).
    - Original/Master Resolution: Giữ nguyên, phóng to 2x/4x (Super-Res), thu nhỏ 50%, hoặc chuẩn 4K/2K/FHD/HD.
    - Image Compression: Mức nén chất lượng (100% Lossless, 92%, 85%, 75%, 60%).
    - Frame Grabber / Snapshot: Trích xuất Frame đầu tiên (Poster Snapshot) hoặc bóc tách toàn bộ frame (Burst Extract).
    - Privacy Clean: Loại bỏ siêu dữ liệu EXIF/GPS nhưng BẢO TOÀN ICC COLOR PROFILE nguyên gốc.
    - Color & Contrast Restoration: Tự động convert RGBA/CMYK sang sRGB chuẩn bảo toàn màu, áp dụng autocontrast và unsharp mask nhẹ.
    - AI Super-Resolution: Tự động upscale x2/x4 detail (GPU Vulkan / High-Fidelity Lanczos).
    - Web Palette Optimize: Tối ưu hóa bảng màu giảm dung lượng.
    - Thumbnail: Tự động sinh file thumbnail ảnh thu nhỏ (.thumb.jpg).
    """
    if not HAS_PIL:
        return True, source_path, []

    if not os.path.isfile(source_path):
        return False, "Tệp nguồn không tồn tại.", []

    extra_artifacts: list[str] = []
    src_dir = os.path.dirname(source_path)
    src_filename = os.path.basename(source_path)
    base_name, orig_ext = os.path.splitext(src_filename)
    orig_ext = orig_ext.lower()

    try:
        im = Image.open(source_path)
    except Exception as exc:
        if orig_ext == ".svg":
            return True, source_path, []
        try:
            with open(source_path, "rb") as f_chk:
                hdr = f_chk.read(512).lower()
            if b"<!doctype html" in hdr or b"<html" in hdr:
                return False, "Tệp tải về không phải ảnh hợp lệ (chứa mã nguồn HTML trang web). Có thể bài viết bị giới hạn quyền riêng tư hoặc cần đăng nhập.", []
        except Exception:
            pass
        return False, f"Không thể mở tệp hình ảnh qua Pillow (File bị lỗi hoặc định dạng không hỗ trợ): {exc}", []

    orig_w, orig_h = im.size
    is_animated = bool(getattr(im, "is_animated", False) and getattr(im, "n_frames", 1) > 1)

    # 1. Frame Grabber / Snapshot
    is_burst = "bóc tách toàn bộ" in frame_grabber.lower() or "burst" in frame_grabber.lower()
    is_poster = "frame đầu tiên" in frame_grabber.lower() or "poster" in frame_grabber.lower()

    if is_burst and is_animated:
        if on_status:
            on_status("📸 Đang bóc tách từng khung hình (Burst Extraction)…")
        burst_dir = os.path.join(src_dir, f"{base_name}_frames")
        os.makedirs(burst_dir, exist_ok=True)
        for idx, fr in enumerate(ImageSequence.Iterator(im)):
            fr_copy = fr.copy()
            if fr_copy.mode in ("P", "RGBA", "LA"):
                fr_copy = fr_copy.convert("RGBA")
            else:
                fr_copy = fr_copy.convert("RGB")
            fr_path = os.path.join(burst_dir, f"frame_{idx+1:04d}.png")
            fr_copy.save(fr_path, format="PNG", optimize=optimize_palette)
            harden_file_permissions(fr_path)
            extra_artifacts.append(fr_path)

    if is_poster and is_animated:
        im.seek(0)
        im = im.copy()
        is_animated = False

    # 2. Quality parsing
    q_match = re.search(r"(\d+)", compress_quality)
    quality = int(q_match.group(1)) if q_match else 100
    quality = max(1, min(100, quality))

    # 3. Transcode Format
    fmt_str = transcode_format.upper()
    if "PNG" in fmt_str:
        out_fmt = "PNG"
        out_ext = ".png"
    elif "JPEG" in fmt_str or "JPG" in fmt_str:
        out_fmt = "JPEG"
        out_ext = ".jpg"
    elif "WEBP" in fmt_str:
        out_fmt = "WEBP"
        out_ext = ".webp"
    elif "GIF" in fmt_str:
        out_fmt = "GIF"
        out_ext = ".gif"
    elif "BMP" in fmt_str:
        out_fmt = "BMP"
        out_ext = ".bmp"
    elif "ICO" in fmt_str:
        out_fmt = "ICO"
        out_ext = ".ico"
    elif "TIFF" in fmt_str:
        out_fmt = "TIFF"
        out_ext = ".tiff"
    else:
        out_fmt = (im.format or "PNG").upper()
        out_ext = orig_ext if orig_ext else f".{out_fmt.lower()}"

    # 4. Target Resolution (Scale / Fit)
    res_lower = resolution_mode.lower()
    apply_hd_sharpness = bool(hd_sharpness or "hd sharpness" in res_lower or "tối ưu hóa ảnh" in res_lower)
    apply_ai_upscale = bool(ai_upscale or "ai super-resolution" in res_lower)

    new_w, new_h = orig_w, orig_h
    if "2x" in res_lower and not apply_ai_upscale:
        new_w, new_h = orig_w * 2, orig_h * 2
    elif "50%" in res_lower:
        new_w, new_h = max(1, orig_w // 2), max(1, orig_h // 2)
    elif "4k" in res_lower and not apply_ai_upscale:
        box = (3840, 2160)
        if orig_w > box[0] or orig_h > box[1]:
            r = min(box[0] / orig_w, box[1] / orig_h)
            new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))
    elif "2k" in res_lower and not apply_ai_upscale:
        box = (2560, 1440)
        if orig_w > box[0] or orig_h > box[1]:
            r = min(box[0] / orig_w, box[1] / orig_h)
            new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))
    elif "full hd" in res_lower:
        box = (1920, 1080)
        if orig_w > box[0] or orig_h > box[1]:
            r = min(box[0] / orig_w, box[1] / orig_h)
            new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))
    elif "chuẩn hd" in res_lower:
        box = (1280, 720)
        if orig_w > box[0] or orig_h > box[1]:
            r = min(box[0] / orig_w, box[1] / orig_h)
            new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))
    elif "avatar" in res_lower:
        box = (512, 512)
        r = min(box[0] / orig_w, box[1] / orig_h)
        new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))
    elif "banner" in res_lower:
        box = (1200, 630)
        r = min(box[0] / orig_w, box[1] / orig_h)
        new_w, new_h = max(1, int(orig_w * r)), max(1, int(orig_h * r))

    resize_needed = (new_w, new_h) != (orig_w, orig_h)

    # 5. Bit-Exact Master Pass-Through Mode (Đạt chuẩn 99-100% chất lượng gốc)
    format_unchanged = ("GỐC" in transcode_format.upper()) or (out_ext.lower() == orig_ext.lower())
    is_passthrough = (
        format_unchanged
        and not resize_needed
        and quality == 100
        and not is_poster
        and not is_burst
        and not apply_hd_sharpness
        and not apply_ai_upscale
    )

    if is_passthrough:
        if on_status:
            on_status("🛡️ Áp dụng chế độ Bit-Exact Master 100% (Bảo toàn tuyệt đối độ sắc nét gốc)…")
        if strip_exif:
            lossless_strip_image_file_metadata(source_path)

        if create_thumb:
            thumb_path = os.path.join(src_dir, f"{base_name}.thumb.jpg")
            im_th = im.copy()
            if im_th.mode in ("RGBA", "LA") or (im_th.mode == "P" and "transparency" in im_th.info):
                bg = Image.new("RGB", im_th.size, (255, 255, 255))
                bg.paste(im_th, mask=im_th.split()[-1])
                im_th = bg
            elif im_th.mode != "RGB":
                im_th = im_th.convert("RGB")
            im_th.thumbnail((320, 320), Image.Resampling.LANCZOS)
            im_th.save(thumb_path, "JPEG", quality=90, subsampling=0, optimize=True)
            harden_file_permissions(thumb_path)
            extra_artifacts.append(thumb_path)

        return True, source_path, extra_artifacts

    # 6. Process and Re-encode khi người dùng yêu cầu biến đổi định dạng, kích thước, khôi phục màu hoặc upscale
    if is_poster:
        dest_filename = f"{base_name}_poster{out_ext}"
    elif out_ext != orig_ext or resize_needed or quality != 100 or is_burst or apply_ai_upscale or apply_hd_sharpness:
        dest_filename = f"{base_name}{out_ext}"
    else:
        dest_filename = src_filename

    target_path = os.path.join(src_dir, dest_filename)
    tmp_out = target_path + ".tmp_proc"

    try:
        # Xóa EXIF / Metadata nhạy cảm nếu được yêu cầu nhưng BẢO TOÀN ICC COLOR PROFILE
        icc_profile = im.info.get("icc_profile")
        if strip_exif:
            im.info.pop("exif", None)

        if is_animated and out_fmt in ("GIF", "WEBP") and not is_poster:
            frames_out = []
            for fr in ImageSequence.Iterator(im):
                f = fr.copy()
                if resize_needed:
                    f = f.resize((new_w, new_h), Image.Resampling.LANCZOS)
                if out_fmt == "WEBP" and f.mode not in ("RGB", "RGBA"):
                    f = f.convert("RGBA")
                frames_out.append(f)

            save_kw = {
                "save_all": True,
                "append_images": frames_out[1:],
                "duration": im.info.get("duration", 100),
                "loop": im.info.get("loop", 0),
            }
            if icc_profile:
                save_kw["icc_profile"] = icc_profile
            if out_fmt == "WEBP":
                if quality == 100:
                    save_kw["lossless"] = True
                else:
                    save_kw["quality"] = quality
                save_kw["method"] = 6
            frames_out[0].save(tmp_out, format=out_fmt, **save_kw)
        else:
            if resize_needed:
                im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
                if "2x" in res_lower and not apply_hd_sharpness:
                    im = im.filter(ImageFilter.UnsharpMask(radius=1.0, percent=35, threshold=2))

            im = restore_image_color_and_sharpness(
                im,
                apply_hd_sharpness=apply_hd_sharpness,
                apply_srgb_convert=True,
            )

            if out_fmt in ("JPEG", "JPG"):
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    bg = Image.new("RGB", im.size, (255, 255, 255))
                    bg.paste(im, mask=im.split()[-1])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")
            elif out_fmt == "BMP":
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")
            elif out_fmt == "ICO":
                if max(im.size) > 256:
                    im = im.resize((256, 256), Image.Resampling.LANCZOS)
                if im.mode != "RGBA":
                    im = im.convert("RGBA")
            elif out_fmt == "WEBP":
                if im.mode not in ("RGB", "RGBA"):
                    im = im.convert("RGBA")
            elif out_fmt == "PNG":
                if im.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    im = im.convert("RGBA")

            save_kw = {}
            if icc_profile:
                save_kw["icc_profile"] = icc_profile

            if out_fmt in ("JPEG", "JPG"):
                save_kw["quality"] = quality
                save_kw["subsampling"] = 0
                save_kw["optimize"] = optimize_palette
                save_kw["keep_rgb"] = True
            elif out_fmt == "WEBP":
                if quality == 100:
                    save_kw["lossless"] = True
                else:
                    save_kw["quality"] = quality
                save_kw["method"] = 6
            elif out_fmt == "PNG":
                save_kw["optimize"] = optimize_palette
            elif out_fmt == "ICO":
                save_kw["sizes"] = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

            im.save(tmp_out, format=out_fmt, **save_kw)

        # 7. AI Super-Resolution (x2 / x4 Detail lên chuẩn 2K/4K)
        if apply_ai_upscale and not is_animated:
            target_scale = 4 if ("4k" in res_lower or "x4" in res_lower) else 2
            ai_tmp = tmp_out + ".ai.png"
            ok_ai, ai_path = run_ai_super_resolution(
                source_path=tmp_out,
                target_path=ai_tmp,
                scale=target_scale,
                target_max_dim=3840 if target_scale == 4 else 2560,
                on_status=on_status,
            )
            if ok_ai and os.path.isfile(ai_path):
                if out_fmt != "PNG":
                    with Image.open(ai_path) as im_ai:
                        if out_fmt in ("JPEG", "JPG") and im_ai.mode != "RGB":
                            im_ai = im_ai.convert("RGB")
                        im_ai.save(tmp_out, format=out_fmt, **save_kw)
                    try:
                        os.remove(ai_path)
                    except OSError:
                        pass
                else:
                    if os.path.exists(tmp_out):
                        os.remove(tmp_out)
                    shutil.move(ai_path, tmp_out)

        if os.path.exists(target_path):
            os.remove(target_path)
        shutil.move(tmp_out, target_path)
        harden_file_permissions(target_path)

        if target_path != source_path and os.path.exists(source_path):
            try:
                os.remove(source_path)
            except OSError:
                pass

        # 8. Thumbnail riêng (.thumb.jpg)
        if create_thumb:
            thumb_path = os.path.join(src_dir, f"{base_name}.thumb.jpg")
            im_th = im.copy()
            if im_th.mode in ("RGBA", "LA") or (im_th.mode == "P" and "transparency" in im_th.info):
                bg = Image.new("RGB", im_th.size, (255, 255, 255))
                bg.paste(im_th, mask=im_th.split()[-1])
                im_th = bg
            elif im_th.mode != "RGB":
                im_th = im_th.convert("RGB")
            im_th.thumbnail((320, 320), Image.Resampling.LANCZOS)
            im_th.save(thumb_path, "JPEG", quality=90, subsampling=0, optimize=True)
            harden_file_permissions(thumb_path)
            extra_artifacts.append(thumb_path)

        return True, target_path, extra_artifacts

    except Exception as exc:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
        return False, f"Lỗi xử lý hình ảnh qua Pillow: {exc}", extra_artifacts
