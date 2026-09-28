#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download Queue & Task Management for Media Security Downloader.
"""

from __future__ import annotations

from typing import Optional

from utils.constants import (
    MAX_QUEUE_SIZE,
    QUEUE_WAITING,
    QUEUE_DOWNLOADING,
    QUEUE_COMPLETED,
    QUEUE_ERROR,
    QUEUE_PAUSED,
    QUEUE_CANCELLED,
)


class DownloadQueueManager:
    """Quản lý danh sách hàng đợi tải xuống an toàn, chống DoS và hỗ trợ trạng thái."""

    def __init__(self, max_size: int = MAX_QUEUE_SIZE) -> None:
        self.max_size = max_size
        self._items: list[dict] = []
        self._current_index: int = -1
        self._is_processing: bool = False

    @property
    def items(self) -> list[dict]:
        return self._items

    @property
    def is_processing(self) -> bool:
        return self._is_processing

    @is_processing.setter
    def is_processing(self, val: bool) -> None:
        self._is_processing = val

    @property
    def current_index(self) -> int:
        return self._current_index

    @current_index.setter
    def current_index(self, val: int) -> None:
        self._current_index = val

    def is_full(self) -> bool:
        return len(self._items) >= self.max_size

    def has_url(self, url: str) -> bool:
        return any(item.get("url") == url for item in self._items)

    def add(
        self,
        url: str,
        target: str,
        platform: str,
        title: str = "Media",
        duration: str = "-",
        clip_start: str = "",
        clip_end: str = "",
    ) -> tuple[bool, str]:
        """Thêm mục mới vào hàng đợi."""
        if self.is_full():
            return False, f"Hàng đợi đã đạt giới hạn tối đa ({self.max_size} mục)."
        if self.has_url(url):
            return False, "URL này đã có trong hàng đợi."

        item = {
            "url": url,
            "target": target,
            "platform": platform,
            "title": title,
            "duration": duration,
            "status": QUEUE_WAITING,
            "error": "",
            "clip_start": clip_start,
            "clip_end": clip_end,
        }
        self._items.append(item)
        return True, "Đã thêm vào hàng đợi."

    def remove(self, index: int) -> Optional[dict]:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def clear(self) -> None:
        self._items.clear()
        self._current_index = -1
        self._is_processing = False

    def get_next_pending_index(self) -> int:
        for idx, item in enumerate(self._items):
            if item.get("status") == QUEUE_WAITING:
                return idx
        return -1

    def move_up(self, index: int) -> bool:
        if 1 <= index < len(self._items):
            self._items[index - 1], self._items[index] = self._items[index], self._items[index - 1]
            return True
        return False

    def move_down(self, index: int) -> bool:
        if 0 <= index < len(self._items) - 1:
            self._items[index], self._items[index + 1] = self._items[index + 1], self._items[index]
            return True
        return False

    def get_summary(self) -> tuple[int, int, int]:
        """Trả về (completed, errors, pending)."""
        completed = sum(1 for item in self._items if item.get("status") == QUEUE_COMPLETED)
        errors = sum(1 for item in self._items if item.get("status") == QUEUE_ERROR)
        pending = sum(1 for item in self._items if item.get("status") == QUEUE_WAITING)
        return completed, errors, pending
