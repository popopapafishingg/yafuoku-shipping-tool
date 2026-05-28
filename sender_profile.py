# -*- coding: utf-8 -*-
"""発送元の固定プロフィール読込（config/sender_profile.json 優先）。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from address_utils import strip_trailing_phone_fragment
from models import SenderInfo
from settings_store import _settings_dir


def _templates_config_dir() -> Path:
    return Path(__file__).resolve().parent / "config"


def _profile_paths() -> tuple[Path, Path]:
    user = _settings_dir() / "sender_profile.json"
    shipped = _templates_config_dir() / "sender_profile.json"
    return user, shipped


def _load_raw_profile() -> dict[str, Any] | None:
    user, shipped = _profile_paths()
    path: Path | None
    if user.is_file():
        path = user
    elif shipped.is_file():
        path = shipped
    else:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_sender_profile() -> SenderInfo | None:
    """sender_profile.json から SenderInfo を構築（なければ None）。"""
    data = _load_raw_profile()
    if not data:
        return None
    zip_code = str(
        data.get("sender_zip")
        or data.get("zip")
        or data.get("zip_code")
        or ""
    ).replace("-", "")
    phone = str(data.get("sender_phone") or data.get("phone") or "")
    name = str(data.get("sender_name") or data.get("name") or "")
    address = str(data.get("sender_address") or data.get("address") or "")
    # sender は固定プロファイルが唯一の入力源。電話断片混入を事前に除去する。
    name = strip_trailing_phone_fragment(name, phone)
    address = strip_trailing_phone_fragment(address, phone)
    return SenderInfo(
        zip_code=zip_code,
        address=address,
        name=name,
        phone=phone,
    )

