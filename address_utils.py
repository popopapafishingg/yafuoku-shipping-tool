# -*- coding: utf-8 -*-
"""住所と会社名を分離し、印刷用に行分割する。"""
from __future__ import annotations

import re
import textwrap
import unicodedata

COMPANY_MARKERS = (
    "有限会社",
    "株式会社",
    "合同会社",
    "合資会社",
    "合名会社",
    "一般社団法人",
    "公益社団法人",
    "（株）",
    "㈱",
    "(株)",
)


def _strip_phone_tail(text: str) -> str:
    """行末にくっついた携帯等（例: ステージ09012345678）を除去。"""
    t = text.strip()
    if not t:
        return ""
    t = re.sub(r"(?<=[^\d\s])0\d{9,11}\s*$", "", t)
    t = re.sub(r"\s+0\d{9,11}\s*$", "", t)
    return t.strip()


def is_phone_digit_fragment(text: str, phone: str = "") -> bool:
    """電話番号の断片（08 / 080 / 0 など）かどうか。"""
    s = unicodedata.normalize("NFKC", text or "").strip()
    if not s:
        return False
    if _looks_like_phone(s):
        return True
    digits = re.sub(r"\D", "", s)
    if not digits:
        return False
    if len(digits) <= 4 and digits.startswith("0"):
        return True
    phone_digits = re.sub(r"\D", "", phone or "")
    if phone_digits and phone_digits.startswith(digits) and len(digits) <= 4:
        return True
    return False


def sanitize_company_name(company: str, phone: str = "") -> str:
    """会社名欄用。電話断片・不明なら空。"""
    text = _strip_phone_tail((company or "").strip())
    if not text or is_phone_digit_fragment(text, phone) or _looks_like_phone(text):
        return ""
    return text


def split_person_company_line(line: str, phone: str = "") -> tuple[str, str]:
    """1行目が「株式会社…　氏名」のとき (氏名, 会社名) に分ける。"""
    line = unicodedata.normalize("NFKC", (line or "").strip())
    if not line:
        return "", ""
    for marker in COMPANY_MARKERS:
        if marker not in line:
            continue
        idx = line.find(marker)
        corp_block = line[idx:].strip()
        rest = corp_block[len(marker) :].strip()
        parts = re.split(r"[\s　]+", rest, maxsplit=1)
        company = marker + parts[0]
        person = parts[1].strip() if len(parts) > 1 else ""
        if not person and idx > 0:
            person = line[:idx].strip()
        return person, sanitize_company_name(company, phone)
    return line, ""


def _looks_like_phone(text: str) -> bool:
    s = unicodedata.normalize("NFKC", text or "").strip()
    digits = re.sub(r"\D", "", s)
    if len(digits) not in (10, 11) or not digits.startswith("0"):
        return False
    return bool(re.fullmatch(r"[\d\s\-()（）ー－]+", s))


def _remove_phone_lines(text: str) -> str:
    parts = []
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s or s in ("住所", "お届け先住所", "配送先住所", "送付先住所"):
            continue
        if _looks_like_phone(s):
            continue
        parts.append(s)
    return "\n".join(parts).strip()


def strip_trailing_phone_fragment(text: str, phone: str = "") -> str:
    """番地末尾に付いた電話断片（08 等）を除去。"""
    t = _strip_phone_tail((text or "").strip())
    phone_digits = re.sub(r"\D", "", phone or "")
    if not t or not phone_digits:
        return t
    for n in range(min(4, len(phone_digits)), 0, -1):
        frag = re.escape(phone_digits[:n])
        t = re.sub(rf"(?<=\d[-－]\d)\s+{frag}\s*$", "", t)
        t = re.sub(rf"(?<=\d)\s+{frag}\s*$", "", t)
        t = re.sub(rf"\s+{frag}\s*$", "", t)
    return t.strip()


def split_address_company(address: str, phone: str = "") -> tuple[str, str]:
    """住所文字列から会社名・法人名を分離する。"""
    address = _remove_phone_lines(address)
    if not address:
        return "", ""

    for marker in COMPANY_MARKERS:
        idx = address.find(marker)
        if idx > 0:
            left, right = address[:idx].strip(), address[idx:].strip()
            if _looks_like_phone(right) or is_phone_digit_fragment(right, phone):
                return strip_trailing_phone_fragment(_strip_phone_tail(left), phone), ""
            return strip_trailing_phone_fragment(
                _strip_phone_tail(left), phone
            ), sanitize_company_name(right, phone)
        if idx == 0:
            if _looks_like_phone(address):
                return "", ""
            person, company = split_person_company_line(address)
            return _strip_phone_tail(person) if person else "", company

    # 「…16-2 車屋 有限会社…」のように番地の後に屋号・会社名があるパターン
    m = re.search(
        r"^(.+?(?:\d+[-－]\d+|\d+番地?|\d+号))\s+(.+)$",
        address,
    )
    if m:
        left, right = m.group(1).strip(), m.group(2).strip()
        if _looks_like_phone(right) or is_phone_digit_fragment(right, phone):
            return strip_trailing_phone_fragment(_strip_phone_tail(left), phone), ""
        if any(k in right for k in COMPANY_MARKERS):
            return strip_trailing_phone_fragment(
                _strip_phone_tail(left), phone
            ), sanitize_company_name(right, phone)
        # 屋号のみ（短い）→ 住所は番地まで、屋号は会社欄へ（右カラムにはみ出し防止）
        if len(right) <= 12 and not re.search(r"\d{3,}", right):
            return strip_trailing_phone_fragment(
                _strip_phone_tail(left), phone
            ), sanitize_company_name(right, phone)

    return strip_trailing_phone_fragment(_strip_phone_tail(address), phone), ""


def wrap_for_print(text: str, width: int = 22) -> list[str]:
    """長い住所を印刷用に複数行へ分割。"""
    text = text.replace("\r", "").strip()
    if not text:
        return []
    lines: list[str] = []
    for part in text.split("\n"):
        part = part.strip()
        if not part:
            continue
        wrapped = textwrap.wrap(part, width=width)
        lines.extend(wrapped if wrapped else [part])
    return lines
