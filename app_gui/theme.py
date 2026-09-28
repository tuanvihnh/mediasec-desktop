#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Theme and styling engine for ToolDowMp4 (Modern Dark & Light Mode).
Configures ttk.Style and native Tkinter widgets with high-contrast, accessible color palettes.
"""

from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import ttk
from typing import Any

DARK_PALETTE = {
    "name": "dark",
    "bg": "#1e1e2e",           # Nền chính (Deep Charcoal)
    "card_bg": "#252636",      # Nền khung LabelFrame / Card
    "fg": "#cdd6f4",           # Màu chữ chính
    "fg_sub": "#a6adc8",       # Màu chữ phụ / chú thích
    "accent": "#89b4fa",       # Xanh dương điểm nhấn
    "accent_text": "#11111b",  # Chữ trên nền điểm nhấn
    "btn_bg": "#313244",       # Nền nút bấm
    "btn_fg": "#f5f5f5",       # Chữ nút bấm
    "btn_active": "#45475a",   # Nền nút khi hover / click
    "entry_bg": "#181825",     # Nền ô nhập
    "entry_fg": "#ffffff",     # Chữ ô nhập
    "select_bg": "#45475a",    # Vùng chọn
    "select_fg": "#ffffff",
    "border": "#313244",       # Viền
    "success": "#a6e3a1",      # Xanh lá thông báo
    "warning": "#f9e2af",      # Vàng cảnh báo
    "error": "#f38ba8",        # Đỏ lỗi
    "log_bg": "#11111b",       # Nền console log
    "log_fg": "#a6e3a1",       # Chữ console log
}

LIGHT_PALETTE = {
    "name": "light",
    "bg": "#f5f5f7",           # Nền chính sáng
    "card_bg": "#ffffff",      # Nền khung trắng
    "fg": "#1c1c1e",           # Chữ đen đậm
    "fg_sub": "#636366",       # Chữ xám
    "accent": "#007aff",       # Xanh dương tiêu chuẩn
    "accent_text": "#ffffff",
    "btn_bg": "#e5e5ea",
    "btn_fg": "#000000",
    "btn_active": "#d1d1d6",
    "entry_bg": "#ffffff",
    "entry_fg": "#000000",
    "select_bg": "#007aff",
    "select_fg": "#ffffff",
    "border": "#d1d1d6",
    "success": "#34c759",
    "warning": "#ff9500",
    "error": "#ff3b30",
    "log_bg": "#1c1c1e",
    "log_fg": "#30d158",
}


def detect_system_theme() -> str:
    """Tự động phát hiện chế độ Dark/Light của hệ thống Linux qua gsettings."""
    try:
        res = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if "dark" in res.stdout.lower():
            return "dark"
    except Exception:
        pass
    return "dark"  # Mặc định tối ưu cho giao diện media/lab


def apply_theme(root: tk.Tk, theme_mode: str = "dark") -> dict[str, Any]:
    """
    Áp dụng bảng màu theme (Dark / Light) lên toàn bộ cây widget của ứng dụng Tkinter/ttk.
    Trả về từ điển palette để cập nhật các thành phần thuần Tk (Canvas, Text, Scrollbar).
    """
    mode = theme_mode.lower()
    if mode == "system":
        mode = detect_system_theme()

    palette = DARK_PALETTE if mode == "dark" else LIGHT_PALETTE
    style = ttk.Style(root)

    # Sử dụng base clam để có toàn quyền tùy biến màu sắc
    try:
        style.theme_use("clam")
    except Exception:
        pass

    bg = palette["bg"]
    card_bg = palette["card_bg"]
    fg = palette["fg"]
    btn_bg = palette["btn_bg"]
    btn_fg = palette["btn_fg"]
    btn_active = palette["btn_active"]
    entry_bg = palette["entry_bg"]
    entry_fg = palette["entry_fg"]
    border = palette["border"]
    select_bg = palette["select_bg"]
    select_fg = palette["select_fg"]

    # Cấu hình cửa sổ gốc
    root.configure(background=bg)

    # 1. TFrame
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=card_bg)

    # 2. TLabel
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("Card.TLabel", background=card_bg, foreground=fg)
    style.configure("Header.TLabel", background=bg, foreground=fg, font=("Sans", 13, "bold"))
    style.configure("Sub.TLabel", background=bg, foreground=palette["fg_sub"], font=("Sans", 9))

    # 3. TLabelframe
    style.configure(
        "TLabelframe",
        background=card_bg,
        bordercolor=border,
        relief="groove",
    )
    style.configure(
        "TLabelframe.Label",
        background=card_bg,
        foreground=palette["accent"],
        font=("Sans", 10, "bold"),
    )

    # 4. TButton
    style.configure(
        "TButton",
        background=btn_bg,
        foreground=btn_fg,
        bordercolor=border,
        darkcolor=btn_bg,
        lightcolor=btn_bg,
        focuscolor=palette["accent"],
        padding=4,
    )
    style.map(
        "TButton",
        background=[("active", btn_active), ("disabled", border)],
        foreground=[("disabled", palette["fg_sub"])],
    )

    # 5. Accent TButton (Nút nổi bật Tải xuống)
    style.configure(
        "Accent.TButton",
        background=palette["accent"],
        foreground=palette["accent_text"],
        font=("Sans", 10, "bold"),
        padding=6,
    )
    style.map(
        "Accent.TButton",
        background=[("active", palette["accent_text"]), ("disabled", border)],
        foreground=[("active", palette["accent"]), ("disabled", palette["fg_sub"])],
    )

    # 6. TCheckbutton & TRadiobutton
    style.configure("TCheckbutton", background=card_bg, foreground=fg)
    style.map("TCheckbutton", background=[("active", card_bg)])
    style.configure("TRadiobutton", background=card_bg, foreground=fg)
    style.map("TRadiobutton", background=[("active", card_bg)])

    # 7. TEntry & TCombobox
    style.configure(
        "TEntry",
        fieldbackground=entry_bg,
        foreground=entry_fg,
        insertcolor=fg,
        bordercolor=border,
    )
    style.configure(
        "TCombobox",
        fieldbackground=entry_bg,
        foreground=entry_fg,
        background=btn_bg,
        bordercolor=border,
        arrowcolor=fg,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", entry_bg)],
        selectbackground=[("readonly", select_bg)],
        selectforeground=[("readonly", select_fg)],
    )

    # 8. Treeview (Hàng đợi Queue)
    style.configure(
        "Treeview",
        background=entry_bg,
        foreground=entry_fg,
        fieldbackground=entry_bg,
        bordercolor=border,
    )
    style.configure(
        "Treeview.Heading",
        background=btn_bg,
        foreground=btn_fg,
        bordercolor=border,
        font=("Sans", 9, "bold"),
    )
    style.map(
        "Treeview",
        background=[("selected", select_bg)],
        foreground=[("selected", select_fg)],
    )

    # 9. TProgressbar
    style.configure(
        "Horizontal.TProgressbar",
        troughcolor=btn_bg,
        background=palette["accent"],
        bordercolor=border,
    )

    return palette
