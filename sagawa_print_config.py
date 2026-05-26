# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from excel_writer import _templates_dir
from label_layout import SagawaLayout
from sagawa_fields import AbsBox
from sagawa_page import SAGAWA_PAGE_H, SAGAWA_PAGE_HEIGHT_MM, SAGAWA_PAGE_W, SAGAWA_PAGE_WIDTH_MM


CONFIG_NAME = "sagawa_position_config.json"
LEGACY_CONFIG_NAME = "sagawa_print_config.json"
MARGIN_CONFIG_NAME = "sagawa_margin_config.json"
SEINO_CONFIG_NAME = "seino_position_config.json"
SEINO_MARGIN_CONFIG_NAME = "seino_margin_config.json"
POSITION_GUIDE_VERSION = 2


def _box_dict(box: AbsBox) -> dict[str, float]:
    return {"x": box.x, "y": box.y, "w": box.w, "h": box.h}


def _box_from(data: dict[str, Any], prefix: str, fallback: AbsBox) -> AbsBox:
    return AbsBox(
        float(data.get(f"{prefix}_X", fallback.x)),
        float(data.get(f"{prefix}_Y", fallback.y)),
        float(data.get(f"{prefix}_W", fallback.w)),
        float(data.get(f"{prefix}_H", fallback.h)),
    )


def _cells_from(data: dict[str, Any], prefix: str, fallback: tuple[AbsBox, ...]) -> tuple[AbsBox, ...]:
    cells = data.get(prefix)
    if isinstance(cells, list) and cells:
        out: list[AbsBox] = []
        for item in cells:
            if isinstance(item, dict):
                out.append(
                    AbsBox(
                        float(item.get("x", 0)),
                        float(item.get("y", 0)),
                        float(item.get("w", 0)),
                        float(item.get("h", 0)),
                    )
                )
        if out:
            return tuple(out)
    return fallback


def default_config(layout: SagawaLayout) -> dict[str, Any]:
    f = layout.fields
    return {
        "POSITION_GUIDE_VERSION": POSITION_GUIDE_VERSION,
        "PAGE_WIDTH_PT": SAGAWA_PAGE_W,
        "PAGE_HEIGHT_PT": SAGAWA_PAGE_H,
        "PAGE_WIDTH_MM": SAGAWA_PAGE_WIDTH_MM,
        "PAGE_HEIGHT_MM": SAGAWA_PAGE_HEIGHT_MM,
        "DEBUG_GUIDES": False,
        "DEBUG_BORDERS": False,
        "DEBUG_LABELS": False,
        "DEBUG_UNDERLAY": False,
        "DEBUG_TIME_CHECK_FORCE": False,
        "OFFSET_X": 0.0,
        "OFFSET_Y": 0.0,
        "DEST_OFFSET_X": 0.0,
        "DEST_OFFSET_Y": 0.0,
        "SENDER_OFFSET_X": 0.0,
        "SENDER_OFFSET_Y": 0.0,
        "ITEM_OFFSET_X": 0.0,
        "ITEM_OFFSET_Y": 0.0,
        "PRICE_OFFSET_X": 0.0,
        "PRICE_OFFSET_Y": 0.0,
        "TIME_OFFSET_X": 0.0,
        "TIME_OFFSET_Y": 0.0,
        "ZIP_SPACING": 0.0,
        "FONT_SIZE_ZIP": layout.zip_digit_size,
        "FONT_SIZE_ADDRESS": layout.addr_size,
        "FONT_SIZE_NAME": layout.name_size,
        "FONT_SIZE_PHONE": layout.recipient_phone_size,
        "FONT_SIZE_SENDER": layout.sender_line_size,
        "FONT_SIZE_ITEM_ID": layout.item_id_size,
        "FONT_SIZE_ITEM": layout.item_text_size,
        "FONT_SIZE_QUANTITY": layout.quantity_size,
        "FONT_SIZE_INSURANCE": layout.insurance_amount_size,
        "ADDRESS_LINE_GAP_PT": 1.0,
        "ITEM_LINE_GAP_PT": 1.0,
        "DEST_ZIP_CELLS": [_box_dict(b) for b in f.to_zip_cells],
        "DEST_ADDRESS_LINES": [_box_dict(b) for b in f.to_addr_lines],
        "DEST_COMPANY_X": f.to_company.x,
        "DEST_COMPANY_Y": f.to_company.y,
        "DEST_COMPANY_W": f.to_company.w,
        "DEST_COMPANY_H": f.to_company.h,
        "DEST_NAME_X": f.to_name.x,
        "DEST_NAME_Y": f.to_name.y,
        "DEST_NAME_W": f.to_name.w,
        "DEST_NAME_H": f.to_name.h,
        "DEST_PHONE_X": f.to_phone.x,
        "DEST_PHONE_Y": f.to_phone.y,
        "DEST_PHONE_W": f.to_phone.w,
        "DEST_PHONE_H": f.to_phone.h,
        "SENDER_ZIP_CELLS": [_box_dict(b) for b in f.from_zip_cells],
        "SENDER_ADDRESS_LINES": [_box_dict(b) for b in f.from_addr_lines],
        "SENDER_NAME_X": f.from_name.x,
        "SENDER_NAME_Y": f.from_name.y,
        "SENDER_NAME_W": f.from_name.w,
        "SENDER_NAME_H": f.from_name.h,
        "SENDER_PHONE_X": f.from_phone.x,
        "SENDER_PHONE_Y": f.from_phone.y,
        "SENDER_PHONE_W": f.from_phone.w,
        "SENDER_PHONE_H": f.from_phone.h,
        "ITEM_ID_X": f.item_auction.x,
        "ITEM_ID_Y": f.item_auction.y,
        "ITEM_ID_W": f.item_auction.w,
        "ITEM_ID_H": f.item_auction.h,
        "ITEM_NAME_LINES": [_box_dict(b) for b in f.item_lines[:2]],
        "QUANTITY_X": f.quantity.x,
        "QUANTITY_Y": f.quantity.y,
        "QUANTITY_W": f.quantity.w,
        "QUANTITY_H": f.quantity.h,
        "INSURANCE_CHECK_X": f.insurance_check.x,
        "INSURANCE_CHECK_Y": f.insurance_check.y,
        "INSURANCE_CHECK_W": f.insurance_check.w,
        "INSURANCE_CHECK_H": f.insurance_check.h,
        "INSURANCE_AMOUNT_X": f.insurance_amount.x,
        "INSURANCE_AMOUNT_Y": f.insurance_amount.y,
        "INSURANCE_AMOUNT_W": f.insurance_amount.w,
        "INSURANCE_AMOUNT_H": f.insurance_amount.h,
        "TIME_CHECK_MARK_SIZE": 9.0,
        "TIME_CHECK_MORNING_X": 276.0,
        "TIME_CHECK_MORNING_Y": 653.0,
        "TIME_CHECK_12_14_X": 302.0,
        "TIME_CHECK_12_14_Y": 653.0,
        "TIME_CHECK_14_16_X": 328.0,
        "TIME_CHECK_14_16_Y": 653.0,
        "TIME_CHECK_16_18_X": 354.0,
        "TIME_CHECK_16_18_Y": 653.0,
        "TIME_CHECK_18_20_X": 380.0,
        "TIME_CHECK_18_20_Y": 653.0,
        "TIME_CHECK_19_21_X": 406.0,
        "TIME_CHECK_19_21_Y": 653.0,
    }


def config_path() -> Path:
    from settings_store import _settings_dir

    return _settings_dir() / CONFIG_NAME


def legacy_config_path() -> Path:
    return _templates_dir() / LEGACY_CONFIG_NAME


def margin_config_path() -> Path:
    from settings_store import _settings_dir

    return _settings_dir() / MARGIN_CONFIG_NAME


def seino_config_path() -> Path:
    from settings_store import _settings_dir

    return _settings_dir() / SEINO_CONFIG_NAME


def seino_margin_config_path() -> Path:
    from settings_store import _settings_dir

    return _settings_dir() / SEINO_MARGIN_CONFIG_NAME


def default_margin_config() -> dict[str, Any]:
    return {
        "horizontal_offset_pt": 0.0,
        "vertical_offset_pt": 0.0,
        "note": "horizontal_offset_pt: 右へ + / 左へ -, vertical_offset_pt: 下へ + / 上へ -",
    }


def ensure_config_file(layout: SagawaLayout) -> Path:
    path = config_path()
    if not path.is_file():
        path.write_text(
            json.dumps(default_config(layout), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    else:
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            current = {}
        if not isinstance(current, dict) or current.get("POSITION_GUIDE_VERSION") != POSITION_GUIDE_VERSION:
            try:
                path.with_suffix(path.suffix + ".bak").write_text(
                    json.dumps(current, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except OSError:
                pass
            path.write_text(
                json.dumps(default_config(layout), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    return path


def ensure_margin_config_file() -> Path:
    path = margin_config_path()
    if not path.is_file():
        path.write_text(
            json.dumps(default_margin_config(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return path


def ensure_seino_placeholder_files() -> tuple[Path, Path]:
    position = seino_config_path()
    margin = seino_margin_config_path()
    if not position.is_file():
        position.write_text(
            json.dumps(
                {
                    "carrier": "seino",
                    "status": "placeholder",
                    "note": "西濃の背景つき座標調整用。描画実装は今後追加。",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    if not margin.is_file():
        margin.write_text(
            json.dumps(default_margin_config(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return position, margin


def load_margin_config() -> dict[str, Any]:
    path = ensure_margin_config_file()
    data = default_margin_config()
    try:
        user_data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(user_data, dict):
            data.update(user_data)
    except (OSError, json.JSONDecodeError):
        pass
    return data


def save_margin_config(values: dict[str, Any]) -> Path:
    path = margin_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = default_margin_config()
    data.update(values)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_position_config(layout: SagawaLayout) -> dict[str, Any]:
    data = default_config(layout)
    path = ensure_config_file(layout)
    legacy_path = legacy_config_path()
    if legacy_path.is_file():
        try:
            legacy_data = json.loads(legacy_path.read_text(encoding="utf-8"))
            if isinstance(legacy_data, dict):
                data.update(legacy_data)
        except (OSError, json.JSONDecodeError):
            pass
    try:
        user_data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(user_data, dict):
            data.update(user_data)
    except (OSError, json.JSONDecodeError):
        pass
    return data


def load_print_config(layout: SagawaLayout) -> dict[str, Any]:
    data = load_position_config(layout)
    margin = load_margin_config()
    try:
        data["OFFSET_X"] = float(data.get("OFFSET_X", 0.0)) + float(
            margin.get("horizontal_offset_pt", 0.0)
        )
        data["OFFSET_Y"] = float(data.get("OFFSET_Y", 0.0)) - float(
            margin.get("vertical_offset_pt", 0.0)
        )
    except (TypeError, ValueError):
        pass
    return data


def save_print_config(values: dict[str, Any]) -> Path:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def cfg_box(cfg: dict[str, Any], prefix: str, fallback: AbsBox) -> AbsBox:
    return _box_from(cfg, prefix, fallback)


def cfg_cells(cfg: dict[str, Any], prefix: str, fallback: tuple[AbsBox, ...]) -> tuple[AbsBox, ...]:
    return _cells_from(cfg, prefix, fallback)


def cfg_line_boxes(cfg: dict[str, Any], key: str, fallback: tuple[AbsBox, ...]) -> tuple[AbsBox, ...]:
    return _cells_from(cfg, key, fallback)


def cfg_number(cfg: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


def shifted_box(cfg: dict[str, Any], box: AbsBox, group: str | None = None) -> AbsBox:
    dx = cfg_number(cfg, "OFFSET_X")
    dy = cfg_number(cfg, "OFFSET_Y")
    if group:
        dx += cfg_number(cfg, f"{group}_OFFSET_X")
        dy += cfg_number(cfg, f"{group}_OFFSET_Y")
    return AbsBox(box.x + dx, box.y + dy, box.w, box.h)


def shifted_boxes(cfg: dict[str, Any], boxes: tuple[AbsBox, ...], group: str | None = None) -> tuple[AbsBox, ...]:
    return tuple(shifted_box(cfg, box, group) for box in boxes)


def adjustment_summary(cfg: dict[str, Any]) -> str:
    keys = (
        "OFFSET_X",
        "OFFSET_Y",
        "DEST_OFFSET_X",
        "DEST_OFFSET_Y",
        "SENDER_OFFSET_X",
        "SENDER_OFFSET_Y",
        "ITEM_OFFSET_X",
        "ITEM_OFFSET_Y",
        "PRICE_OFFSET_X",
        "PRICE_OFFSET_Y",
        "TIME_OFFSET_X",
        "TIME_OFFSET_Y",
        "ZIP_SPACING",
    )
    lines = ["現在の調整値:"]
    lines.extend(f"{key} = {cfg_number(cfg, key):g}" for key in keys)
    lines.extend(
        [
            "",
            "使い方説明:",
            "右に2mm動かす -> OFFSET_X を +5.67",
            "左に2mm動かす -> OFFSET_X を -5.67",
            "上に2mm動かす -> OFFSET_Y を +5.67",
            "下に2mm動かす -> OFFSET_Y を -5.67",
            "PDF座標は左下が原点です。Xは右がプラス、Yは上がプラスです。",
            "1mm = 2.83465pt なので、2mm = 5.67pt です。",
        ]
    )
    return "\n".join(lines)
