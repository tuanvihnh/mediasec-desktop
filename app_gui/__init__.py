#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
App GUI package for ToolDowMp4.
Contains Native Tkinter Application GUI and Theming Engine.
"""

from app_gui.app import App
from app_gui.theme import apply_theme, detect_system_theme, DARK_PALETTE, LIGHT_PALETTE

__all__ = ["App", "apply_theme", "detect_system_theme", "DARK_PALETTE", "LIGHT_PALETTE"]
