# -*- coding: utf-8 -*-
"""佐川スキャンひな形（578×824pt）と座標系。"""
from __future__ import annotations

from pathlib import Path

MM_TO_PT = 72.0 / 25.4

# 実物佐川伝票のページサイズ。ReportLab にはこの mm 値から換算した pt を渡す。
SAGAWA_PAGE_WIDTH_MM = 204.0
SAGAWA_PAGE_HEIGHT_MM = 291.0
SAGAWA_PAGE_W = SAGAWA_PAGE_WIDTH_MM * MM_TO_PT
SAGAWA_PAGE_H = SAGAWA_PAGE_HEIGHT_MM * MM_TO_PT
SAGAWA_PAGE_SIZE = (SAGAWA_PAGE_W, SAGAWA_PAGE_H)


def mm_to_pt(value_mm: float) -> float:
    return float(value_mm) * MM_TO_PT


def pt_to_mm(value_pt: float) -> float:
    return float(value_pt) / MM_TO_PT


def sagawa_scan_pdf_path() -> Path | None:
    from excel_writer import _templates_dir

    for name in (
        "sagawa_form_scan.pdf",
        "CCF20260521_0001.pdf",
        "CCF20260521.pdf",
    ):
        p = _templates_dir() / name
        if p.is_file():
            return p
    for name in ("CCF20260521_0001.pdf", "CCF20260521.pdf"):
        fallback = Path(r"c:\Users\b-s\Downloads") / name
        if fallback.is_file():
            return fallback
    return None


def sagawa_underlay_png_path() -> Path | None:
    from excel_writer import _templates_dir

    for name in ("sagawa_underlay.png", "sagawa_underlay.jpg"):
        p = _templates_dir() / name
        if p.is_file():
            return p
    return None
