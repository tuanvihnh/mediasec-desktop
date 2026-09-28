#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Super-Resolution Engine: Real-ESRGAN Vulkan GPU native runner & installer with Lanczos 4K fallback.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional
import urllib.request

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

from utils.helpers import format_bytes
from utils.security import harden_file_permissions
from image_engine.color_restore import restore_image_color_and_sharpness


def detect_ai_upscale_engine() -> tuple[str, Optional[str]]:
    """
    Phát hiện engine AI Super-Resolution khả dụng trong hệ thống Linux:
    1. realesrgan-ncnn-vulkan (CLI native Linux x86_64 / GPU Vulkan)
    2. onnxruntime (Neural Network ONNX Engine)
    3. Fallback: High-Fidelity Lanczos Resampling kết hợp Unsharp Masking 4K
    Trả về tuple: (engine_type, path_or_info)
    """
    candidates = [
        os.path.expanduser("~/.local/share/media-downloader/bin/realesrgan-ncnn-vulkan"),
        os.path.expanduser("~/.local/bin/realesrgan-ncnn-vulkan"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "realesrgan-ncnn-vulkan"),
        shutil.which("realesrgan-ncnn-vulkan"),
        shutil.which("realesrgan"),
        "/usr/local/bin/realesrgan-ncnn-vulkan",
        "/usr/bin/realesrgan-ncnn-vulkan",
        "/opt/realesrgan/realesrgan-ncnn-vulkan",
    ]
    for p in candidates:
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return "realesrgan-ncnn-vulkan", p

    try:
        import onnxruntime  # noqa: F401
        return "onnxruntime", None
    except ImportError:
        pass

    return "lanczos_fallback", None


REALESRGAN_RELEASE_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
    "realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
)


def install_realesrgan_engine(
    on_status: Optional[callable] = None,
    on_progress: Optional[callable] = None,
) -> tuple[bool, str]:
    """
    Tải và cài đặt tự động (1-Click) Real-ESRGAN Vulkan GPU Native Engine cho Linux x86_64:
    - Điểm đến: ~/.local/share/media-downloader/bin/
    - Tải file zip chính thức từ GitHub releases
    - Giải nén an toàn (chống Zip Slip)
    - Phân quyền thực thi 0755
    - Tự động liên kết mềm vào ~/.local/bin nếu thư mục tồn tại
    - Kiểm tra thực thi (Verification run)
    """
    install_dir = os.path.expanduser("~/.local/share/media-downloader/bin")
    os.makedirs(install_dir, exist_ok=True)

    bin_path = os.path.join(install_dir, "realesrgan-ncnn-vulkan")
    zip_part = os.path.join(install_dir, "realesrgan_download.zip.part")
    zip_final = os.path.join(install_dir, "realesrgan_download.zip")

    if on_status:
        on_status("🌐 Đang kết nối tải Real-ESRGAN Vulkan GPU Release…")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) "
            "Gecko/20100101 Firefox/120.0"
        ),
        "Accept": "*/*",
    }

    try:
        req = urllib.request.Request(REALESRGAN_RELEASE_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            total_size = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            chunk_size = 64 * 1024

            with open(zip_part, "wb") as f_out:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f_out.write(chunk)
                    downloaded += len(chunk)
                    if total_size > 0 and on_progress:
                        pct = min(100, int((downloaded / total_size) * 100))
                        on_progress(pct)
                    if on_status and total_size > 0:
                        on_status(f"📥 Đang tải Real-ESRGAN GPU ({format_bytes(downloaded)} / {format_bytes(total_size)})…")

        if os.path.exists(zip_final):
            os.remove(zip_final)
        os.rename(zip_part, zip_final)

        if on_status:
            on_status("📦 Đang giải nén mô hình và binary AI GPU Engine…")

        import zipfile
        with zipfile.ZipFile(zip_final, "r") as zf:
            for member in zf.infolist():
                target_path = os.path.abspath(os.path.join(install_dir, member.filename))
                if not target_path.startswith(os.path.abspath(install_dir)):
                    continue
                zf.extract(member, install_dir)

        if os.path.exists(zip_final):
            try:
                os.remove(zip_final)
            except OSError:
                pass

        if not os.path.isfile(bin_path):
            return False, f"Không tìm thấy tệp thực thi sau giải nén: {bin_path}"

        os.chmod(bin_path, 0o755)

        local_bin_dir = os.path.expanduser("~/.local/bin")
        if os.path.isdir(local_bin_dir):
            symlink_path = os.path.join(local_bin_dir, "realesrgan-ncnn-vulkan")
            try:
                if os.path.islink(symlink_path) or os.path.exists(symlink_path):
                    os.remove(symlink_path)
                os.symlink(bin_path, symlink_path)
            except Exception:
                pass

        if on_status:
            on_status("🧪 Đang kiểm tra tương thích Vulkan GPU…")

        res = subprocess.run([bin_path, "-h"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        help_output = (res.stdout + res.stderr).decode("utf-8", errors="ignore")
        if "realesrgan-ncnn-vulkan" in help_output or "Usage" in help_output or res.returncode in (0, 255):
            return True, f"Cài đặt thành công Real-ESRGAN Vulkan GPU Engine tại: {bin_path}"
        else:
            return True, f"Đã cài đặt Real-ESRGAN tại {bin_path}. Kiểm tra Vulkan trả về mã {res.returncode}."

    except Exception as e:
        if os.path.exists(zip_part):
            try:
                os.remove(zip_part)
            except OSError:
                pass
        return False, f"Lỗi trong quá trình tải / cài đặt: {e}"


def run_ai_super_resolution(
    source_path: str,
    target_path: str,
    scale: int = 2,
    target_max_dim: int = 3840,
    on_status: Optional[callable] = None,
) -> tuple[bool, str]:
    """
    Thực thi AI Super-Resolution:
    - Nếu có realesrgan-ncnn-vulkan: gọi engine native GPU để upscale x2/x4 chi tiết vượt trội.
    - Nếu không có: tự động fallback sang High-Fidelity Lanczos Resampling 2K/4K kết hợp UnsharpMask
      và phục hồi màu sắc sRGB.
    Trả về (success, target_path_or_err).
    """
    if not HAS_PIL:
        return False, "Cần thư viện Pillow để xử lý ảnh."

    if not os.path.isfile(source_path):
        return False, f"Tệp nguồn không tồn tại: {source_path}"

    engine_type, engine_bin = detect_ai_upscale_engine()
    scale = max(2, min(4, scale))

    # 1. Nếu có realesrgan-ncnn-vulkan binary
    if engine_type == "realesrgan-ncnn-vulkan" and engine_bin:
        real_bin = os.path.realpath(engine_bin)
        bin_dir = os.path.dirname(real_bin)
        models_dir = os.path.join(bin_dir, "models")

        # Quét các mô hình thực sự tồn tại trong thư mục models/
        available_models: list[str] = []
        if os.path.isdir(models_dir):
            for f in os.listdir(models_dir):
                if f.endswith(".param"):
                    m_base = f[:-6]
                    if os.path.isfile(os.path.join(models_dir, f"{m_base}.bin")):
                        available_models.append(m_base)

        # Chọn mô hình khả dụng tốt nhất:
        # realesrgan-x4plus là mô hình chuẩn cho ảnh thực tế, chi tiết sắc nét nhất, hỗ trợ mọi tỷ lệ scale (2, 3, 4).
        # Không dùng realesrnet-x4plus vì bản phân phối Ubuntu release chính thức không đi kèm file mô hình này.
        if "realesrgan-x4plus" in available_models:
            model_name = "realesrgan-x4plus"
        elif "realesrgan-x4plus-anime" in available_models:
            model_name = "realesrgan-x4plus-anime"
        elif available_models:
            model_name = available_models[0]
        else:
            model_name = "realesrgan-x4plus"

        if on_status:
            on_status(f"🚀 Đang chạy Real-ESRGAN Vulkan GPU (x{scale} Detail - {model_name})…")

        tmp_ai = target_path + ".ai_gpu.png"
        native_model_scale = 4 if "x4" in model_name else scale
        cmd = [
            real_bin,
            "-i", source_path,
            "-o", tmp_ai,
            "-s", str(native_model_scale),
            "-n", model_name,
            "-g", "0",
        ]
        if os.path.isdir(models_dir):
            cmd.extend(["-m", models_dir])

        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
            stderr_text = res.stderr.decode("utf-8", errors="ignore")
            if "failed" in stderr_text.lower() and ("fopen" in stderr_text.lower() or "find_blob" in stderr_text.lower()):
                raise RuntimeError(f"Lỗi nạp mô hình Real-ESRGAN: {stderr_text[:200]}")

            if res.returncode == 0 and os.path.isfile(tmp_ai) and os.path.getsize(tmp_ai) > 0:
                # Kiểm tra tính toàn vẹn của ảnh xuất ra (chống xuất ảnh đen do lỗi nạp mô hình / GPU driver)
                with Image.open(tmp_ai) as chk_im:
                    extrema = chk_im.getextrema()
                    is_all_black = False
                    if isinstance(extrema, tuple):
                        if len(extrema) > 0 and isinstance(extrema[0], tuple):
                            # RGB / RGBA: ((r_min, r_max), (g_min, g_max), (b_min, b_max)...)
                            is_all_black = all(e[1] == 0 for e in extrema[:3])
                        elif len(extrema) == 2 and isinstance(extrema[0], (int, float)):
                            # Grayscale: (min, max)
                            is_all_black = (extrema[1] == 0)
                    if is_all_black:
                        raise RuntimeError("Ảnh xuất ra từ Vulkan GPU bị đen hoàn toàn (mọi pixel = 0).")

                # Nếu native scale (4x) lớn hơn requested scale (vd: 2x) hoặc vượt target_max_dim:
                # Thu nhỏ bằng thuật toán Lanczos để đạt chất lượng khử răng cưa siêu mịn (SSAA)
                with Image.open(source_path) as orig_im:
                    orig_w, orig_h = orig_im.size

                target_w = orig_w * scale
                target_h = orig_h * scale
                if target_max_dim and (target_w > target_max_dim or target_h > target_max_dim):
                    ratio = min(target_max_dim / target_w, target_max_dim / target_h)
                    target_w = max(1, int(target_w * ratio))
                    target_h = max(1, int(target_h * ratio))

                if chk_im.size != (target_w, target_h):
                    chk_im_resized = chk_im.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    chk_im_resized.save(target_path)
                else:
                    if os.path.exists(target_path):
                        os.remove(target_path)
                    shutil.move(tmp_ai, target_path)

                harden_file_permissions(target_path)
                return True, target_path
            else:
                raise RuntimeError(f"Real-ESRGAN exit code: {res.returncode}. Stderr: {stderr_text[:200]}")
        except Exception:
            if on_status:
                on_status("⚠️ Real-ESRGAN GPU gặp sự cố, tự động chuyển sang Lanczos Super-Resolution…")
        finally:
            if os.path.exists(tmp_ai):
                try:
                    os.remove(tmp_ai)
                except OSError:
                    pass

    # 2. Fallback: High-Fidelity Lanczos Resampling kết hợp phục hồi màu sắc & chi tiết
    if on_status:
        on_status(f"⚡ Đang áp dụng High-Definition Super-Resolution x{scale}…")
    try:
        tmp_lanczos = target_path + ".ai_lanczos"
        with Image.open(source_path) as im:
            icc_prof = im.info.get("icc_profile")
            w, h = im.size
            new_w, new_h = w * scale, h * scale

            if target_max_dim and (new_w > target_max_dim or new_h > target_max_dim):
                ratio = min(target_max_dim / new_w, target_max_dim / new_h)
                new_w = max(1, int(new_w * ratio))
                new_h = max(1, int(new_h * ratio))

            im_up = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
            im_up = restore_image_color_and_sharpness(
                im_up,
                apply_hd_sharpness=True,
                apply_srgb_convert=True,
            )

            out_ext = os.path.splitext(target_path)[1].lower()
            save_kw: dict = {}
            if icc_prof:
                save_kw["icc_profile"] = icc_prof

            if out_ext in (".jpg", ".jpeg"):
                if im_up.mode != "RGB":
                    if im_up.mode in ("RGBA", "LA") or (im_up.mode == "P" and "transparency" in im_up.info):
                        bg = Image.new("RGB", im_up.size, (255, 255, 255))
                        bg.paste(im_up, mask=im_up.split()[-1])
                        im_up = bg
                    else:
                        im_up = im_up.convert("RGB")
                save_kw["quality"] = 98
                save_kw["subsampling"] = 0
                save_kw["keep_rgb"] = True
                save_kw["optimize"] = True
                im_up.save(tmp_lanczos, format="JPEG", **save_kw)
            elif out_ext == ".webp":
                save_kw["quality"] = 98
                save_kw["method"] = 6
                im_up.save(tmp_lanczos, format="WEBP", **save_kw)
            elif out_ext == ".png":
                save_kw["optimize"] = True
                im_up.save(tmp_lanczos, format="PNG", **save_kw)
            else:
                im_up.save(tmp_lanczos, **save_kw)

        if os.path.exists(target_path):
            os.remove(target_path)
        shutil.move(tmp_lanczos, target_path)
        harden_file_permissions(target_path)
        return True, target_path
    except Exception as exc:
        if os.path.exists(tmp_lanczos):
            try:
                os.remove(tmp_lanczos)
            except OSError:
                pass
        return False, f"Lỗi Super-Resolution: {exc}"
