#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utils package for Media Security Downloader.
"""

from utils.constants import *
from utils.helpers import (
    log_info,
    log_warn,
    log_err,
    format_duration,
    parse_time_to_seconds,
    format_bytes,
    clean_ansi_escape,
    create_placeholder_thumbnail,
    load_thumbnail_pil,
    load_thumbnail_png_bytes,
    safe_open_path,
    safe_notify,
)
from utils.security import (
    preflight_disk_check,
    harden_file_permissions,
    compute_file_sha256,
    cleanup_temp_files,
    validate_file_integrity,
    validate_downloaded_files,
    detect_drm_mpd,
    detect_drm_hls,
    check_cleartext_warning,
)
from utils.network import (
    is_safe_remote_url,
    is_direct_image_url,
    is_direct_media_url,
    is_rule34_url,
    is_iwara_url,
    is_telegram_url,
    is_pinterest_url,
    auto_detect_platform,
    fetch_manifest,
    download_direct_file,
)
from utils.config import (
    load_config,
    save_config,
    get_config_dir,
    get_config_file_path,
    DEFAULT_CONFIG,
)
from utils.logger import (
    setup_app_logger,
    get_logger,
    get_data_dir,
    get_log_file_path,
)
from utils.cleanup import (
    cleanup_stale_artifacts,
)
