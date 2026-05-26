# -*- coding: utf-8 -*-
"""発送元などの設定を保存・読み込み（AppDataに保存して起動ごとに維持）。"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from models import SenderInfo


def _settings_dir() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home())))
    d = base / "YafuokuShippingTool"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _settings_path() -> Path:
    return _settings_dir() / "settings.json"


def layout_preview_pdf_path() -> Path:
    """送り状位置のプレビューPDF。設定と同じ AppData に置き、exe 横の output と取り違えない。"""
    return _settings_dir() / "sagawa_preview_layout_latest.pdf"


def _migrate_legacy_settings() -> None:
    dest = _settings_path()
    if dest.is_file():
        return
    legacy: list[Path] = []
    if getattr(sys, "frozen", False):
        legacy.append(Path(sys.executable).resolve().parent / "settings.json")
    legacy.append(Path(__file__).resolve().parent / "settings.json")
    for src in legacy:
        if src.is_file():
            shutil.copy2(src, dest)
            return


def load_settings() -> dict:
    _migrate_legacy_settings()
    path = _settings_path()
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(data: dict) -> None:
    path = _settings_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sender() -> SenderInfo:
    d = load_settings().get("sender", {})
    return SenderInfo(
        zip_code=d.get("zip_code", ""),
        address=d.get("address", ""),
        name=d.get("name", ""),
        phone=d.get("phone", ""),
    )


def save_sender(sender: SenderInfo, print_sender: bool) -> None:
    data = load_settings()
    data["sender"] = {
        "zip_code": sender.zip_code,
        "address": sender.address,
        "name": sender.name,
        "phone": sender.phone,
    }
    data["print_sender"] = print_sender
    save_settings(data)


def load_print_sender_default() -> bool:
    return bool(load_settings().get("print_sender", False))


def load_carrier() -> str:
    c = load_settings().get("carrier", "sagawa")
    if c in ("sagawa", "seino", "both"):
        return c
    return "sagawa"


def save_carrier(carrier: str) -> None:
    if carrier not in ("sagawa", "seino", "both"):
        return
    data = load_settings()
    data["carrier"] = carrier
    save_settings(data)


def load_insurance_enabled() -> bool:
    return bool(load_settings().get("insurance_enabled", True))


def load_insurance_amount() -> int:
    try:
        return int(load_settings().get("insurance_amount", 50000))
    except (TypeError, ValueError):
        return 50000


def save_insurance(enabled: bool, amount: int) -> None:
    data = load_settings()
    data["insurance_enabled"] = enabled
    data["insurance_amount"] = max(0, int(amount))
    save_settings(data)


def clear_sagawa_layout_overrides() -> None:
    data = load_settings()
    data.pop("sagawa_layout", None)
    save_settings(data)


def load_sagawa_layout_overrides() -> dict:
    """手動上書きは無効。座標は label_layout.py（自動校正済み）のみ。"""
    return {}


def save_sagawa_layout_overrides(values: dict) -> None:
    data = load_settings()
    data["sagawa_layout"] = values
    save_settings(data)
