#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subtitle Engine & Translation (Vietnamese / English automatic translation).
"""

from __future__ import annotations

import re
import json
from typing import Optional
import urllib.request
import urllib.parse


def parse_sub_content(content: str) -> list[tuple[str, str]]:
    """
    Phân tích nội dung file phụ đề (SRT hoặc WebVTT) thành danh sách các block:
    [(khoảng_thời_gian_srt, nội_dung_thoại)].
    Loại bỏ các thẻ HTML / VTT định dạng.
    """
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.split("\n")
    blocks: list[tuple[str, str]] = []
    current_time: Optional[str] = None
    current_text: list[str] = []

    time_pattern = re.compile(
        r"(\d{1,2}:(?:\d{2}:)?\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:(?:\d{2}:)?\d{2}[.,]\d{3})"
    )

    for line in lines:
        line_clean = line.strip()
        m = time_pattern.search(line_clean)
        if m:
            if current_time and current_text:
                blocks.append((current_time, " ".join(current_text).strip()))
            start_t, end_t = m.group(1), m.group(2)
            if start_t.count(":") == 1:
                start_t = "00:" + start_t
            if end_t.count(":") == 1:
                end_t = "00:" + end_t
            current_time = f"{start_t.replace('.', ',')} --> {end_t.replace('.', ',')}"
            current_text = []
        elif current_time is not None:
            if not line_clean:
                if current_time and current_text:
                    blocks.append((current_time, " ".join(current_text).strip()))
                    current_time = None
                    current_text = []
            elif not (line_clean.isdigit() and len(current_text) == 0):
                clean_text = re.sub(r"<[^>]+>", "", line_clean).strip()
                if clean_text:
                    current_text.append(clean_text)

    if current_time and current_text:
        blocks.append((current_time, " ".join(current_text).strip()))

    return blocks


def translate_texts_batch(texts: list[str], target_lang: str = "vi") -> list[str]:
    """
    Dịch hàng loạt các đoạn phụ đề sang ngôn ngữ đích (vi hoặc en)
    sử dụng endpoint dịch nhanh an toàn, tự động gom nhóm để tăng tốc.
    """
    if not texts:
        return []

    sep = "\n<<<SEG>>>\n"
    combined = sep.join(texts)
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="
            + target_lang
            + "&dt=t&q="
            + urllib.parse.quote(combined)
        )
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated_combined = "".join([item[0] for item in data[0] if item[0]])
            parts = [p.strip() for p in translated_combined.split("<<<SEG>>>")]
            if len(parts) == len(texts):
                return parts
    except Exception:
        pass

    results = []
    for t in texts:
        if not t.strip():
            results.append("")
            continue
        try:
            url = (
                "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl="
                + target_lang
                + "&dt=t&q="
                + urllib.parse.quote(t)
            )
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                results.append("".join([item[0] for item in data[0] if item[0]]).strip())
        except Exception:
            results.append(t)
    return results


def translate_subtitles_file(
    source_file: str,
    target_file: str,
    target_lang: str = "vi",
    on_progress: Optional[callable] = None,
) -> bool:
    """
    Đọc file phụ đề gốc (SRT hoặc VTT), dịch toàn bộ nội dung thoại sang target_lang
    (tiếng Việt 'vi' hoặc tiếng Anh 'en') và ghi ra file chuẩn .srt.
    """
    try:
        with open(source_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        blocks = parse_sub_content(content)
        if not blocks:
            return False

        batch_size = 25
        translated_texts: list[str] = []
        total_blocks = len(blocks)

        for i in range(0, total_blocks, batch_size):
            chunk = [b[1] for b in blocks[i : i + batch_size]]
            translated_chunk = translate_texts_batch(chunk, target_lang=target_lang)
            translated_texts.extend(translated_chunk)
            if on_progress:
                on_progress(min(100.0, (i + len(chunk)) / total_blocks * 100))

        with open(target_file, "w", encoding="utf-8") as f:
            for idx, (t_range, trans_txt) in enumerate(
                zip([b[0] for b in blocks], translated_texts), 1
            ):
                f.write(f"{idx}\n{t_range}\n{trans_txt}\n\n")

        return True
    except Exception:
        return False
