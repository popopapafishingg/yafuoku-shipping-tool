# -*- coding: utf-8 -*-
"""佐川伝票: layout_offsets.json による欄別微調整（mm → pt）。"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from excel_writer import _templates_dir
from sagawa_fields import AbsBox

MM_TO_PT = 72.0 / 25.4


def _templates_config_dir() -> Path:
    p = _templates_dir().parent / "config"
    p.mkdir(parents=True, exist_ok=True)
    return p


def layout_offsets_path() -> Path:
    from settings_store import _settings_dir

    user = _settings_dir() / "layout_offsets.json"
    if user.is_file():
        return user
    shipped = _templates_config_dir() / "layout_offsets.json"
    if shipped.is_file():
        return shipped
    return user


def default_layout_offsets() -> dict[str, Any]:
    shipped = _templates_config_dir() / "layout_offsets.json"
    if shipped.is_file():
        try:
            data = json.loads(shipped.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError):
            pass
    return {
        "version": 1,
        "global": {"dx_mm": 0.0, "dy_mm": 0.0},
        "dest": {},
        "sender": {},
        "item": {},
        "drawing": {},
    }


def load_layout_offsets() -> dict[str, Any]:
    data = default_layout_offsets()
    path = layout_offsets_path()
    if path.is_file():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                merged = deepcopy(data)
                for key in ("global", "dest", "sender", "item", "drawing"):
                    if isinstance(user.get(key), dict):
                        base = merged.get(key, {})
                        if isinstance(base, dict):
                            base = dict(base)
                            base.update(user[key])
                            merged[key] = base
                merged["version"] = user.get("version", merged.get("version", 1))
                data = merged
        except (OSError, json.JSONDecodeError):
            pass
    return data


def mm_to_pt(mm: float) -> float:
    return round(float(mm) * MM_TO_PT, 2)


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    sec = data.get(name, {})
    return sec if isinstance(sec, dict) else {}


def _f(sec: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(sec.get(key, default))
    except (TypeError, ValueError):
        return default


def apply_global_offset(box: AbsBox, offsets: dict[str, Any]) -> AbsBox:
    g = _section(offsets, "global")
    return AbsBox(
        box.x + mm_to_pt(_f(g, "dx_mm")),
        box.y + mm_to_pt(_f(g, "dy_mm")),
        box.w,
        box.h,
    )


def apply_group_offset(box: AbsBox, offsets: dict[str, Any], group: str) -> AbsBox:
    b = apply_global_offset(box, offsets)
    sec = _section(offsets, group)
    return AbsBox(
        b.x + mm_to_pt(_f(sec, "dx_mm")),
        b.y + mm_to_pt(_f(sec, "dy_mm")),
        b.w,
        b.h,
    )


def resize_box(box: AbsBox, *, dw_pt: float = 0.0, dh_pt: float = 0.0) -> AbsBox:
    return AbsBox(box.x, box.y, max(1.0, box.w + dw_pt), max(1.0, box.h + dh_pt))


def apply_zip_cells(
    cells: tuple[AbsBox, ...],
    offsets: dict[str, Any],
    group: str,
) -> tuple[AbsBox, ...]:
    sec = _section(offsets, group)
    dx = mm_to_pt(_f(sec, "zip_dx_mm"))
    dy = mm_to_pt(_f(sec, "zip_dy_mm"))
    dw = mm_to_pt(_f(sec, "zip_cell_w_mm"))
    out: list[AbsBox] = []
    for b in cells:
        shifted = apply_group_offset(b, offsets, group)
        out.append(
            resize_box(
                AbsBox(shifted.x + dx, shifted.y + dy, shifted.w, shifted.h),
                dw_pt=dw,
            )
        )
    return tuple(out)


def apply_address_lines(
    lines: tuple[AbsBox, ...],
    offsets: dict[str, Any],
    group: str,
) -> tuple[AbsBox, ...]:
    sec = _section(offsets, group)
    dx = mm_to_pt(_f(sec, "address_dx_mm"))
    dy = mm_to_pt(_f(sec, "address_dy_mm"))
    dh = mm_to_pt(_f(sec, "address_line_h_mm"))
    out: list[AbsBox] = []
    for b in lines:
        shifted = apply_group_offset(b, offsets, group)
        out.append(resize_box(AbsBox(shifted.x + dx, shifted.y + dy, shifted.w, shifted.h), dh_pt=dh))
    return tuple(out)


def apply_item_boxes(
    item_id: AbsBox,
    item_lines: tuple[AbsBox, ...],
    offsets: dict[str, Any],
) -> tuple[AbsBox, tuple[AbsBox, ...]]:
    sec = _section(offsets, "item")
    base_dx = mm_to_pt(_f(sec, "dx_mm"))
    base_dy = mm_to_pt(_f(sec, "dy_mm"))
    id_box = resize_box(
        AbsBox(
            item_id.x + base_dx + mm_to_pt(_f(sec, "id_x_mm")),
            item_id.y + base_dy + mm_to_pt(_f(sec, "id_y_mm")),
            item_id.w,
            item_id.h,
        ),
        dw_pt=mm_to_pt(_f(sec, "id_w_mm")),
        dh_pt=mm_to_pt(_f(sec, "id_h_mm")),
    )
    line_h_delta = mm_to_pt(_f(sec, "name_line_h_mm"))
    line_gap = mm_to_pt(_f(sec, "name_line_gap_mm"))
    lines_out: list[AbsBox] = []
    for i, line in enumerate(item_lines):
        dy_extra = i * line_gap
        lines_out.append(
            resize_box(
                AbsBox(
                    line.x + base_dx + mm_to_pt(_f(sec, "name_x_mm")),
                    line.y + base_dy + mm_to_pt(_f(sec, "name_y_mm")) + dy_extra,
                    line.w,
                    line.h,
                ),
                dw_pt=mm_to_pt(_f(sec, "name_w_mm")),
                dh_pt=line_h_delta,
            )
        )
    return id_box, tuple(lines_out)


def drawing_ratios(offsets: dict[str, Any]) -> dict[str, float]:
    d = _section(offsets, "drawing")
    return {
        "zip": _f(d, "zip_baseline_ratio", 0.4),
        "address": _f(d, "address_baseline_ratio", 0.42),
        "phone": _f(d, "phone_baseline_ratio", 0.4),
        "name": _f(d, "name_baseline_ratio", 0.4),
        "item": _f(d, "item_baseline_ratio", 0.38),
    }


def ensure_layout_offsets_file() -> Path:
    path = layout_offsets_path()
    if not path.is_file():
        shipped = _templates_config_dir() / "layout_offsets.json"
        if shipped.is_file():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(shipped.read_text(encoding="utf-8"), encoding="utf-8")
    return path
