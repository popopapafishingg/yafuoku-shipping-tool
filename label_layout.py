# -*- coding: utf-8 -*-
"""
佐川複写送り状 578×824pt。ReportLab: 原点=左下、+Y=上。
座標は sagawa_form_scan から自動校正（sagawa_fields）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sagawa_fields import (
    AbsBox,
    SagawaFields,
    build_fields_from_scan,
    fields_to_calibration_dict,
)

_CALIB_PATH = Path(__file__).resolve().parent / "templates" / "sagawa_calibration.json"


@dataclass(frozen=True)
class SagawaLayout:
    fields: SagawaFields

    zip_digit_x: tuple[float, ...]
    zip_digit_y: float
    sender_zip_digit_x: tuple[float, ...]
    sender_zip_y: float
    zip_digit_size: int = 7
    sender_zip_digit_size: int = 7

    to_x: float = 63.0
    to_addr_y: tuple[float, ...] = (763.9, 750.9, 737.9)
    to_name_y: float = 728.9
    to_phone_y: float = 712.9
    addr_size: int = 11
    name_size: int = 13
    recipient_phone_size: int = 9
    addr_wrap: int = 14

    from_x: float = 61.5
    from_addr_y: tuple[float, ...] = (635.2, 624.2, 613.2)
    from_name_y: float = 608.2
    from_phone_y: float = 594.2
    sender_line_size: int = 9
    sender_wrap: int = 22

    quantity_x: float = 223.0
    quantity_y: float = 815.9
    quantity_size: int = 9

    item_x: float = 256.4
    item_auction_y: float = 760.9
    item_line_y: tuple[float, ...] = (740.9, 730.9, 720.9)
    item_id_size: int = 8
    item_text_size: int = 8
    item_wrap: int = 26
    item_max_lines: int = 3

    insurance_check_x: float = 318.0
    insurance_check_y: float = 644.7
    insurance_amount_x: float = 358.5
    insurance_amount_y: float = 644.7
    insurance_amount_size: int = 8
    insurance_amount_char_extra: float = 1.2

    left_x: float = 63.0
    addr_start_y: float = 763.9
    sender_x: float = 61.5
    sender_zip_y_cap: float = 602.5
    right_x: float = 256.4
    item_top_y: float = 760.9

    to_box: AbsBox = AbsBox(59, 684.9, 196, 96)
    from_box: AbsBox = AbsBox(57.5, 579.9, 197, 86)
    item_box: AbsBox = AbsBox(254.4, 690.9, 310, 76)


def _layout_from_cal_and_fields(cal: dict, fields: SagawaFields) -> SagawaLayout:
    return SagawaLayout(
        fields=fields,
        zip_digit_x=tuple(float(x) for x in cal["zip_digit_x"]),
        zip_digit_y=float(cal["zip_digit_y"]),
        sender_zip_digit_x=tuple(float(x) for x in cal["sender_zip_digit_x"]),
        sender_zip_y=float(cal["sender_zip_y"]),
        to_x=float(cal.get("to_x", 63)),
        to_addr_y=tuple(float(y) for y in cal["to_addr_y"]),
        to_name_y=float(cal["to_name_y"]),
        to_phone_y=float(cal["to_phone_y"]),
        from_x=float(cal.get("from_x", 61.5)),
        from_addr_y=tuple(float(y) for y in cal["from_addr_y"]),
        from_name_y=float(cal["from_name_y"]),
        from_phone_y=float(cal["from_phone_y"]),
        quantity_x=float(cal["quantity_x"]),
        quantity_y=float(cal["quantity_y"]),
        item_x=float(cal["item_x"]),
        item_auction_y=float(cal["item_auction_y"]),
        item_line_y=tuple(float(y) for y in cal["item_line_y"]),
        insurance_check_x=float(cal["insurance_check_x"]),
        insurance_check_y=float(cal["insurance_check_y"]),
        insurance_amount_x=float(cal["insurance_amount_x"]),
        insurance_amount_y=float(cal["insurance_amount_y"]),
        left_x=float(cal.get("left_x", 63)),
        addr_start_y=float(cal.get("addr_start_y", 763.9)),
        sender_x=float(cal.get("sender_x", 61.5)),
        sender_zip_y_cap=float(cal.get("sender_zip_y_cap", cal["sender_zip_y"])),
        right_x=float(cal.get("right_x", 256.4)),
        item_top_y=float(cal.get("item_top_y", 760.9)),
        to_box=AbsBox(*cal["to_box"]) if "to_box" in cal else fields.to_addr_lines[0],
        from_box=AbsBox(*cal["from_box"]) if "from_box" in cal else fields.from_name,
        item_box=AbsBox(*cal["item_box"])
        if "item_box" in cal
        else fields.item_auction,
    )


def _default_layout() -> SagawaLayout:
    fields = build_fields_from_scan()
    cal = fields_to_calibration_dict(fields)
    return _layout_from_cal_and_fields(cal, fields)


def merge_sagawa_layout(overrides: dict | None) -> SagawaLayout:
    if not overrides:
        return SAGAWA_DEFAULT
    cal = fields_to_calibration_dict(SAGAWA_DEFAULT.fields)
    cal.update(overrides)
    return _layout_from_cal_and_fields(cal, SAGAWA_DEFAULT.fields)


def _load_calibration_file() -> dict | None:
    if not _CALIB_PATH.is_file():
        return None
    try:
        data = json.loads(_CALIB_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def get_sagawa_layout() -> SagawaLayout:
    from settings_store import load_sagawa_layout_overrides

    try:
        fields = build_fields_from_scan()
    except Exception:
        fields = SAGAWA_DEFAULT.fields

    cal = _load_calibration_file()
    if cal:
        base = _layout_from_cal_and_fields(cal, fields)
    else:
        base = _layout_from_cal_and_fields(fields_to_calibration_dict(fields), fields)

    ov = load_sagawa_layout_overrides()
    if not ov:
        return base
    cal2 = fields_to_calibration_dict(base.fields)
    cal2.update(ov)
    return _layout_from_cal_and_fields(cal2, fields)


def absolute_field_rects(layout: SagawaLayout | None = None) -> list[tuple[str, float, float, float, float]]:
    lay = layout or get_sagawa_layout()
    return lay.fields.all_preview_rects()


try:
    SAGAWA_DEFAULT = _default_layout()
except Exception:
    f = SagawaFields(
        to_zip_cells=tuple(AbsBox(400 + i * 9, 795, 9, 9) for i in range(7)),
        to_zip_group3=AbsBox(400, 795, 28, 9),
        to_zip_group4=AbsBox(430, 795, 38, 9),
        to_addr_lines=(
            AbsBox(59, 760, 196, 12),
            AbsBox(59, 748, 196, 12),
            AbsBox(59, 736, 196, 12),
        ),
        to_company=AbsBox(59, 712, 196, 12),
        to_name=AbsBox(59, 700, 196, 12),
        to_phone=AbsBox(59, 685, 196, 12),
        from_zip_cells=tuple(AbsBox(420 + i * 9, 595, 9, 9) for i in range(7)),
        from_zip_group3=AbsBox(420, 595, 28, 9),
        from_zip_group4=AbsBox(450, 595, 38, 9),
        from_addr_lines=(
            AbsBox(57, 630, 197, 12),
            AbsBox(57, 618, 197, 12),
            AbsBox(57, 606, 197, 12),
        ),
        from_name=AbsBox(57, 590, 197, 12),
        from_phone=AbsBox(57, 575, 197, 12),
        quantity=AbsBox(292, 793, 26, 22),
        insurance_check=AbsBox(322, 670, 18, 18),
        insurance_amount=AbsBox(408, 670, 88, 18),
        item_auction=AbsBox(254, 752, 310, 20),
        item_lines=(
            AbsBox(254, 732, 310, 18),
            AbsBox(254, 714, 310, 18),
            AbsBox(254, 696, 310, 18),
        ),
    )
    SAGAWA_DEFAULT = _layout_from_cal_and_fields(fields_to_calibration_dict(f), f)

SAGAWA = SAGAWA_DEFAULT
