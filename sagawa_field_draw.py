# -*- coding: utf-8 -*-
"""佐川伝票・欄専用描画ルール（赤枠は欄幾何の表示であり、文字は欄ルールで描く）。"""
from __future__ import annotations

import re
from dataclasses import dataclass

from address_utils import (
    COMPANY_MARKERS,
    sanitize_company_name,
    split_address_company,
    split_person_company_line,
    strip_trailing_phone_fragment,
)
from sagawa_fields import AbsBox, baseline_in_box
from sagawa_recipient_layout import (
    RECIPIENT_ADDRESS_LINE_COUNT,
    RECIPIENT_ZIP_DIGIT_COUNT,
    DestInputFields,
)

_HYPHENATED_NUMBER = re.compile(r"\d+[-－]\d+")


@dataclass(frozen=True)
class ZipFieldStyle:
    font_size: int = 7
    min_font_size: int = 6


@dataclass(frozen=True)
class AddressFieldStyle:
    font_size: int = 11
    min_font_size: int = 7
    padding_x: float = 2.0


@dataclass(frozen=True)
class CompanyFieldStyle:
    font_size: int = 11
    min_font_size: int = 7
    padding_x: float = 2.0


@dataclass(frozen=True)
class NameFieldStyle:
    font_size: int = 13
    min_font_size: int = 8


@dataclass(frozen=True)
class PhoneFieldStyle:
    font_size: int = 9
    min_font_size: int = 7
    padding_x: float = 2.0


def _tokenize_units(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if not text:
        return []
    units: list[str] = []
    i = 0
    while i < len(text):
        m = _HYPHENATED_NUMBER.match(text, i)
        if m:
            units.append(m.group(0))
            i = m.end()
        elif text[i].isspace():
            i += 1
        else:
            m2 = re.match(r"\S+", text[i:])
            if not m2:
                break
            units.append(m2.group(0))
            i += len(m2.group(0))
    return units


def _wrap_to_lines(
    c,
    font: str,
    text: str,
    box: AbsBox,
    font_size: int,
    max_lines: int,
) -> list[str]:
    units = _tokenize_units(text)
    if not units:
        return [""] * max_lines
    max_w = max(1.0, box.w - 4)
    lines: list[str] = []
    current = ""
    for unit in units:
        sep = "" if not current else " "
        cand = f"{current}{sep}{unit}" if current else unit
        if current and c.stringWidth(cand, font, font_size) > max_w:
            lines.append(current)
            current = unit
            if len(lines) >= max_lines:
                break
        else:
            current = cand
    if current and len(lines) < max_lines:
        lines.append(current)
    while len(lines) < max_lines:
        lines.append("")
    return lines[:max_lines]


def _fit_font_single_line(
    c,
    font: str,
    text: str,
    box: AbsBox,
    font_size: int,
    min_size: int,
) -> int:
    size = int(font_size)
    while size > min_size and c.stringWidth(text, font, size) > max(1.0, box.w - 4):
        size -= 1
    return size


def _draw_string(
    c,
    font: str,
    size: int,
    x: float,
    y: float,
    text: str,
) -> None:
    if not text:
        return
    c.setFont(font, size)
    c.drawString(x, y, text)


def draw_zip_field(
    c,
    font: str,
    zip_code: str,
    fields: DestInputFields,
    style: ZipFieldStyle,
) -> None:
    """郵便番号欄: 7マス・1文字ずつ各マス中央・横均等配置済みマスへ描画。"""
    digits = "".join(ch for ch in (zip_code or "") if ch.isdigit())[:RECIPIENT_ZIP_DIGIT_COUNT]
    if len(digits) != RECIPIENT_ZIP_DIGIT_COUNT:
        return
    cells = fields.zip_cells
    if len(cells) != RECIPIENT_ZIP_DIGIT_COUNT:
        return
    size = style.font_size
    y_ref = baseline_in_box(cells[0], size)
    for ch, box in zip(digits, cells):
        draw_size = _fit_font_single_line(c, font, ch, box, size, style.min_font_size)
        y = baseline_in_box(box, draw_size)
        # 同一行の baseline を揃える
        y = y_ref if draw_size == size else y
        w = c.stringWidth(ch, font, draw_size)
        x = box.x + (box.w - w) / 2.0
        _draw_string(c, font, draw_size, x, y, ch)


def draw_address_field(
    c,
    font: str,
    address: str,
    phone: str,
    fields: DestInputFields,
    style: AddressFieldStyle,
) -> None:
    """
    住所欄: 行数固定・行ごと固定 baseline・番地ハイフン分割禁止。
    枠幅超過時のみ全体フォント縮小。
    """
    text = strip_trailing_phone_fragment((address or "").strip(), phone)
    lines_boxes = fields.address_lines
    n = min(RECIPIENT_ADDRESS_LINE_COUNT, len(lines_boxes))
    if n <= 0 or not text:
        return

    size = style.font_size
    while size >= style.min_font_size:
        lines = _wrap_to_lines(c, font, text, lines_boxes[0], size, n)
        ok = all(
            not line or c.stringWidth(line, font, size) <= lines_boxes[0].w - 4
            for line in lines
        )
        if ok:
            break
        size -= 1

    for box, line in zip(lines_boxes[:n], lines):
        if not line:
            continue
        y = baseline_in_box(box, size)
        _draw_string(c, font, size, box.x + style.padding_x, y, line)


def draw_company_field(
    c,
    font: str,
    company: str,
    phone: str,
    fields: DestInputFields,
    style: CompanyFieldStyle,
) -> None:
    """会社名欄: 電話断片禁止・空欄優先。"""
    text = sanitize_company_name((company or "").strip(), phone)
    if not text:
        return
    box = fields.company
    size = _fit_font_single_line(c, font, text, box, style.font_size, style.min_font_size)
    y = baseline_in_box(box, size)
    _draw_string(c, font, size, box.x + style.padding_x, y, text)


def draw_name_field(
    c,
    font: str,
    name: str,
    phone: str,
    fields: DestInputFields,
    style: NameFieldStyle,
) -> None:
    """氏名欄: 氏名のみ・1行中央・会社名は混入させない。"""
    raw = (name or "").strip()
    if not raw:
        return
    person, corp = split_person_company_line(raw, phone)
    text = person or raw
    if any(m in text for m in COMPANY_MARKERS):
        person2, _ = split_person_company_line(text, phone)
        text = person2 or text
    if not text or is_phone_fragment_name(text, phone):
        return
    box = fields.name
    size = _fit_font_single_line(c, font, text, box, style.font_size, style.min_font_size)
    y = baseline_in_box(box, size)
    w = c.stringWidth(text, font, size)
    x = box.x + (box.w - w) / 2.0
    _draw_string(c, font, size, x, y, text)


def is_phone_fragment_name(text: str, phone: str) -> bool:
    from address_utils import is_phone_digit_fragment

    return is_phone_digit_fragment(text, phone)


def format_phone_field(phone: str) -> str:
    p = (phone or "").strip()
    if not p:
        return ""
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) == 11 and digits.startswith(("090", "080", "070")):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10 and digits.startswith("0"):
        return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
    return p


def draw_phone_field(
    c,
    font: str,
    phone: str,
    fields: DestInputFields,
    style: PhoneFieldStyle,
) -> None:
    """電話番号欄: ハイフン整形・固定 baseline・左寄せ。"""
    text = format_phone_field(phone)
    if not text:
        return
    box = fields.phone
    size = _fit_font_single_line(c, font, text, box, style.font_size, style.min_font_size)
    y = baseline_in_box(box, size)
    _draw_string(c, font, size, box.x + style.padding_x, y, text)


@dataclass(frozen=True)
class RecipientPrintFields:
    zip_code: str
    address: str
    company: str
    name: str
    phone: str


def normalize_recipient_fields(
    *,
    name: str,
    zip_code: str,
    address: str,
    phone: str,
    company: str = "",
) -> RecipientPrintFields:
    """GUI/PDF共通の欄別データ正規化。"""
    phone = (phone or "").strip()
    company = sanitize_company_name((company or "").strip(), phone)
    addr = strip_trailing_phone_fragment((address or "").strip(), phone)

    addr_only, comp_from_addr = split_address_company(addr, phone)
    if comp_from_addr and not company:
        company = sanitize_company_name(comp_from_addr, phone)
    addr = strip_trailing_phone_fragment(addr_only, phone)

    person, comp_from_name = split_person_company_line((name or "").strip(), phone)
    if comp_from_name and not company:
        company = sanitize_company_name(comp_from_name, phone)
    name_text = person or (name or "").strip()
    if any(m in name_text for m in COMPANY_MARKERS):
        person2, comp2 = split_person_company_line(name_text, phone)
        if comp2 and not company:
            company = sanitize_company_name(comp2, phone)
        name_text = person2 or name_text

    if company and name_text == company:
        name_text = person or ""

    return RecipientPrintFields(
        zip_code=(zip_code or "").replace("-", "").replace("－", "")[:7],
        address=addr,
        company=company,
        name=name_text,
        phone=phone,
    )


def draw_dest_input_fields(
    c,
    font: str,
    data: RecipientPrintFields,
    fields: DestInputFields,
    *,
    zip_style: ZipFieldStyle | None = None,
    addr_style: AddressFieldStyle | None = None,
    company_style: CompanyFieldStyle | None = None,
    name_style: NameFieldStyle | None = None,
    phone_style: PhoneFieldStyle | None = None,
) -> None:
    """お届け先5欄を専用ルールで描画。"""
    draw_zip_field(c, font, data.zip_code, fields, zip_style or ZipFieldStyle())
    draw_address_field(
        c,
        font,
        data.address,
        data.phone,
        fields,
        addr_style or AddressFieldStyle(),
    )
    draw_company_field(
        c, font, data.company, data.phone, fields, company_style or CompanyFieldStyle()
    )
    draw_name_field(c, font, data.name, data.phone, fields, name_style or NameFieldStyle())
    draw_phone_field(c, font, data.phone, fields, phone_style or PhoneFieldStyle())
