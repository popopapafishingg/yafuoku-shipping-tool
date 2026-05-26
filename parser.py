# -*- coding: utf-8 -*-
"""ヤフオク取引情報の貼り付けテキストから氏名・郵便番号・住所を抽出する。"""
import re
import unicodedata
from dataclasses import dataclass

from address_utils import is_phone_digit_fragment, split_person_company_line


@dataclass
class ShippingInfo:
    name: str
    zip_code: str
    address: str
    phone: str = ""
    company: str = ""

    @property
    def zip_left(self) -> str:
        return self.zip_code[:3] if len(self.zip_code) >= 3 else self.zip_code

    @property
    def zip_right(self) -> str:
        return self.zip_code[3:7] if len(self.zip_code) >= 7 else ""


ZIP_PATTERN = re.compile(r"〒?\s*(\d{3})\s*[-－]?\s*(\d{4})|\b(\d{7})\b")
PHONE_PATTERN = re.compile(
    r"(?:電話番号|電話|携帯|TEL|tel|お届け先電話|お届け先\s*電話)\s*[:：]?\s*([\d\-()（）\s　]{8,22})",
    re.I,
)
# 日本の電話番号（ハイフンあり／なし）
JP_PHONE_INLINE = re.compile(
    r"(?<!\d)(0\d{1,4}[-－]?\d{1,4}[-－]?\d{3,4})(?!\d)",
)


def _normalize_match_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return text


def _log_missing(field: str, reason: str) -> None:
    print(f"[extract] {field} missing: {reason}")


def _label_line_value(line: str, labels: tuple[str, ...]) -> str | None:
    joined = re.sub(r"\s+", "", line)
    for label in labels:
        if joined.startswith(label):
            rest = joined[len(label):].lstrip(":：-‐ー・")
            return rest or ""
    return None


def _extract_zip(text: str) -> str:
    m = ZIP_PATTERN.search(text.replace("〒", ""))
    if not m:
        return ""
    if m.group(3):
        return m.group(3)
    return m.group(1) + m.group(2)


def _clean_name(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip())


def _normalize_phone(s: str) -> str:
    s = re.sub(r"[\s　]+", "", s.strip())
    return s.strip()


def _looks_like_phone(s: str) -> bool:
    d = re.sub(r"\D", "", s)
    if len(d) < 10 or len(d) > 11:
        return False
    if d.startswith("0"):
        return True
    return False


def _is_standalone_phone_line(line: str) -> bool:
    """行全体が電話番号だけ（住所・会社名と混ざらない）。"""
    s = line.strip()
    if not s:
        return False
    if re.search(r"[都道府県市区町村番地号ー-]", s):
        return False
    d = re.sub(r"\D", "", s)
    if len(d) not in (10, 11) or not d.startswith("0"):
        return False
    # 数字とハイフンのみ（ハイフンなしOK）
    return bool(re.fullmatch(r"[\d\-()（）\s]+", s))


def _strip_trailing_phone_token(text: str) -> str:
    """行末にくっついた電話（例: 有限会社ステージ09083865707）を除去。"""
    t = text.strip()
    t = re.sub(r"(?<=[^\d\s])0\d{9,11}\s*$", "", t)
    t = re.sub(r"\s+0\d{9,11}\s*$", "", t)
    return t.strip()


def _extract_phone_from_lines(lines: list[str]) -> str:
    """「電話番号」単独行の次の行など。"""
    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue
        if re.match(
            r"^(電話番号|電話|携帯|TEL|お届け先電話番号|お届け先\s*電話番号)\s*$",
            s,
            re.I,
        ):
            for j in range(i + 1, min(i + 4, len(lines))):
                cand = lines[j].strip()
                if not cand or re.match(r"^(配送|追跡|商品|オークション|送料)", cand):
                    break
                if _looks_like_phone(cand) or re.search(r"[-－()（）]", cand):
                    return _normalize_phone(cand)
            continue
        if re.match(r"^(電話番号|電話|携帯|TEL)\s*[:：]\s*.+", s, re.I):
            rest = re.split(r"[:：]", s, 1)[1].strip()
            if rest and _looks_like_phone(rest):
                return _normalize_phone(rest)
    return ""


def _extract_phone_inline(text: str) -> str:
    """本文中の電話番号形式（追跡番号の長数字は除外）。"""
    for m in JP_PHONE_INLINE.finditer(text):
        cand = m.group(1)
        if _looks_like_phone(cand):
            return _normalize_phone(cand)
    return ""


def _extract_phone(text: str) -> str:
    if "\t" in text:
        for line in text.splitlines():
            cols = [c.strip() for c in re.split(r"\t+", line) if c.strip()]
            if len(cols) >= 2 and cols[0] in (
                "電話",
                "電話番号",
                "TEL",
                "携帯",
                "携帯電話",
                "お届け先電話番号",
            ):
                return _normalize_phone(cols[1])
    for line in text.splitlines():
        line = line.strip()
        m = re.match(r"^(?:電話番号|電話|携帯|TEL)\s*[:：]\s*(.+)$", line, re.I)
        if m:
            return _normalize_phone(m.group(1))
    m = PHONE_PATTERN.search(text)
    if m:
        return _normalize_phone(m.group(1))
    p = _extract_phone_from_lines([ln.rstrip() for ln in text.splitlines()])
    if p:
        return p
    return _extract_phone_inline(text)


def extract_phone_any(text: str) -> str:
    """貼り付けテキストから電話番号だけ確実に取り出す。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    p = _extract_phone(text)
    if p:
        return p
    lines = [ln.strip() for ln in text.splitlines()]
    p = _extract_phone_from_lines(lines)
    if p:
        return p
    return _extract_phone_inline(text) or ""


def _clean_address_block(block: str) -> str:
    lines = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("〒"):
            continue
        if line in ("住所", "お届け先住所", "配送先住所", "送付先住所"):
            continue
        if re.fullmatch(r"\d{3}-?\d{4}", line.replace("〒", "")):
            continue
        if re.match(r"^\d{7}$", re.sub(r"\D", "", line)):
            continue
        if _is_standalone_phone_line(line) or _looks_like_phone(line):
            continue
        line = _strip_trailing_phone_token(line)
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


_PREFECTURE_RE = re.compile(
    r"(?:北海道|青森県|岩手県|宮城県|秋田県|山形県|福島県|茨城県|栃木県|群馬県|"
    r"埼玉県|千葉県|東京都|神奈川県|新潟県|富山県|石川県|福井県|山梨県|長野県|"
    r"岐阜県|静岡県|愛知県|三重県|滋賀県|京都府|大阪府|兵庫県|奈良県|和歌山県|"
    r"鳥取県|島根県|岡山県|広島県|山口県|徳島県|香川県|愛媛県|高知県|福岡県|"
    r"佐賀県|長崎県|熊本県|大分県|宮崎県|鹿児島県|沖縄県)"
)

_BLOCK_HEADER_RE = re.compile(
    r"^(お届け先|お届け\s*情報|送付先|宛先|宛\s*名|お届け先住所)\s*[:：]?\s*$"
)

_BLOCK_STOP_RE = re.compile(
    r"^(購入者に連絡|配送方法|配送業者|配送会社|追跡番号|お問い合わせ番号|"
    r"商品情報|オークションID|商品名|商品タイトル|落札数量|落札価格|"
    r"終了日時|終了時間|終了|送料|出品者|評価|支払|お支払)"
)


def _split_address_into_lines(s: str) -> list[str]:
    s = re.sub(r"\s+", " ", s.strip())
    if not s:
        return []
    return [s]


def _parse_no_label_block(text: str) -> ShippingInfo | None:
    """お届け先ブロック形式（ラベル無し・順序: 郵便→住所→名前→電話）。"""
    lines = [ln.strip() for ln in text.split("\n")]
    # 先頭を「お届け先」ヘッダ以降に揃える
    start = 0
    for i, ln in enumerate(lines):
        if _BLOCK_HEADER_RE.match(ln):
            start = i + 1
            break
    body_all = lines[start:]
    # 「購入者に連絡」等で打ち切り（電話: の直前ヘッダなら残してもOK）
    body: list[str] = []
    for ln in body_all:
        if ln in ("購入者に連絡:", "購入者に連絡"):
            continue
        if _BLOCK_STOP_RE.match(ln):
            break
        body.append(ln)
    body = [ln for ln in body if ln]
    if not body:
        return None

    zip_code = ""
    addr_parts: list[str] = []
    name = ""
    phone = ""

    for ln in body:
        ln_clean = ln.replace("〒", "").strip()
        if not ln_clean:
            continue
        if ln_clean in ("住所", "お届け先住所", "配送先住所", "送付先住所"):
            continue
        # 電話: プレフィックス付き
        m_ph = re.match(
            r"^(?:電話番号|電話|TEL|tel|携帯|お届け先電話|お届け先電話番号)"
            r"\s*[:：]?\s*(.+)$",
            ln_clean,
            re.I,
        )
        if m_ph:
            cand = m_ph.group(1).strip()
            digits = re.sub(r"\D", "", cand)
            if 10 <= len(digits) <= 11 and digits.startswith("0"):
                if not phone:
                    phone = digits
                continue
        # 単独電話行
        if _is_standalone_phone_line(ln_clean):
            if not phone:
                phone = re.sub(r"\D", "", ln_clean)
            continue
        if _looks_like_phone(ln_clean):
            if not phone:
                phone = re.sub(r"\D", "", ln_clean)
            continue
        # 郵便番号（XXX-XXXX または 7桁）
        if not zip_code:
            zm = re.fullmatch(r"\d{3}\s*[-－]?\s*\d{4}", ln_clean)
            if zm:
                zip_code = re.sub(r"\D", "", ln_clean)
                continue
            zm2 = re.fullmatch(r"\d{7}", ln_clean)
            if zm2:
                zip_code = ln_clean
                continue
        # それ以外は住所候補
        addr_parts.append(ln_clean)

    def _looks_address(s: str) -> bool:
        return bool(
            _PREFECTURE_RE.search(s)
            or re.search(r"[市区町村郡丁目番地号]", s)
            or re.search(r"\d", s)
        )

    # 末尾が氏名らしき行（都道府県・市区町村・郡・番地を含まない）なら氏名へ
    if addr_parts and not name:
        last = addr_parts[-1]
        if not _looks_address(last):
            name = _clean_name(last)
            addr_parts = addr_parts[:-1]

    # 先頭が氏名らしき行（住所要素を含まない・かつ後続に住所がある）なら氏名へ
    if addr_parts and not name:
        first = addr_parts[0]
        rest_has_address = any(_looks_address(p) for p in addr_parts[1:])
        if not _looks_address(first) and rest_has_address:
            name = _clean_name(first)
            addr_parts = addr_parts[1:]

    address = " ".join(p for p in addr_parts if p).strip()
    address = _strip_trailing_phone_token(address)

    if not (name or address or zip_code):
        return None
    return ShippingInfo(name=name, zip_code=zip_code, address=address, phone=phone)


_JP_DEST_HEADER_RE = re.compile(
    r"(お\s*届\s*け\s*先|お\s*届\s*け\s*先\s*情\s*報|お\s*届\s*け\s*情\s*報|配送\s*先|送付\s*先|宛\s*先)"
)
_JP_DEST_STOP_RE = re.compile(
    r"^(購入者|落札者|支払|お支払|配送方法|発送|商品|オークション|取引|問い合わせ|出品者|評価|Yahoo|ヤフオク)"
)
_JP_NAME_LABELS = ("氏名", "名前", "お名前", "宛名", "受取人", "受取人氏名")
_JP_ADDR_LABELS = ("住所", "お届け先住所", "配送先住所", "送付先住所")


def _looks_like_jp_address(s: str) -> bool:
    return bool(
        re.search(r"(都|道|府|県|市|区|町|村|郡|丁目|番地|号|〒|\d)", s)
    )


def _parse_japanese_shipping_block(text: str) -> ShippingInfo | None:
    norm = _normalize_match_text(text)
    lines = [ln.strip() for ln in norm.splitlines()]
    lines = [ln for ln in lines if ln]
    if not lines:
        return None

    start = 0
    for i, line in enumerate(lines):
        if _JP_DEST_HEADER_RE.search(line):
            start = i + 1
            break

    block: list[str] = []
    for line in lines[start:]:
        compact = re.sub(r"\s+", "", line)
        if block and _JP_DEST_STOP_RE.search(compact):
            break
        if _JP_DEST_HEADER_RE.search(line):
            rest = _JP_DEST_HEADER_RE.sub("", line).strip(" :：-‐ー・")
            if rest:
                block.append(rest)
            continue
        block.append(line)

    zip_code = _extract_zip(norm)
    phone = _extract_phone(norm)
    name = ""
    address_parts: list[str] = []

    for line in block:
        clean = line.strip(" :：-‐ー・")
        if not clean:
            continue
        name_value = _label_line_value(clean, _JP_NAME_LABELS)
        if name_value is not None:
            if name_value:
                name = _clean_name(name_value)
            continue
        addr_value = _label_line_value(clean, _JP_ADDR_LABELS)
        if addr_value is not None:
            if addr_value:
                address_parts.append(addr_value)
            continue
        if re.fullmatch(r"〒?\s*\d{3}\s*[-－]?\s*\d{4}", clean):
            if not zip_code:
                zip_code = re.sub(r"\D", "", clean)
            continue
        if _is_standalone_phone_line(clean) or _looks_like_phone(clean):
            if not phone:
                phone = _normalize_phone(clean)
            continue
        if _looks_like_jp_address(clean):
            address_parts.append(clean)
        elif not _looks_like_jp_address(clean) and not is_phone_digit_fragment(clean, phone):
            person, company = split_person_company_line(clean, phone)
            if person:
                name = person
            if company:
                address_parts.append(company)
        elif not name:
            name = _clean_name(re.sub(r"(様|さん)$", "", clean))

    if not name and address_parts:
        last = address_parts[-1]
        if not _looks_like_jp_address(last):
            name = _clean_name(last)
            address_parts = address_parts[:-1]

    address = _clean_address_block("\n".join(address_parts))
    if not (name or address or zip_code or phone):
        return None
    return ShippingInfo(name=name, zip_code=zip_code, address=address, phone=phone)


def _parse_yahoo_delivery_block(text: str) -> ShippingInfo | None:
    """
    氏名/会社行 → 「住所」 → 郵便 → 住所行 → 電話行 のヤフオク貼り付け形式。
    会社名は address に含めず、後段の split_address_company で分離する。
    """
    lines = [
        unicodedata.normalize("NFKC", ln.strip())
        for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if ln.strip()
    ]
    if len(lines) < 3:
        return None
    try:
        addr_idx = next(
            i for i, ln in enumerate(lines) if ln in ("住所", "お届け先住所", "配送先住所")
        )
    except StopIteration:
        return None

    phone = _extract_phone(text)
    name = ""
    company = ""
    if addr_idx > 0:
        first = lines[0]
        if not _looks_like_phone(first) and not is_phone_digit_fragment(first, phone):
            name, company = split_person_company_line(first, phone)

    zip_code = ""
    address_parts: list[str] = []
    for ln in lines[addr_idx + 1 :]:
        if _BLOCK_STOP_RE.match(ln) or _JP_DEST_STOP_RE.search(ln):
            break
        if ln in ("住所", "お届け先住所", "配送先住所", "送付先住所"):
            continue
        if _is_standalone_phone_line(ln) or _looks_like_phone(ln):
            if not phone:
                phone = _normalize_phone(ln)
            continue
        clean = ln.replace("〒", "").strip()
        if not zip_code:
            zm = re.fullmatch(r"\d{3}\s*[-－]?\s*\d{4}", clean)
            if zm:
                zip_code = re.sub(r"\D", "", clean)
                continue
            if re.fullmatch(r"\d{7}", clean):
                zip_code = clean
                continue
        if _looks_like_jp_address(ln) or re.search(r"\d", ln):
            address_parts.append(ln)

    address = _clean_address_block("\n".join(address_parts))

    if not (name or address or zip_code or phone or company):
        return None
    return ShippingInfo(
        name=name,
        zip_code=zip_code,
        address=address,
        phone=phone,
        company=company,
    )


def parse_shipping_text(text: str) -> ShippingInfo:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise ValueError("貼り付けテキストが空です。")

    name = ""
    address = ""
    zip_code = _extract_zip(text)
    phone = _extract_phone(text)

    # 「奥田 雅紀」改行「住所」形式（氏名ラベルなし）
    raw_lines = [ln.strip() for ln in text.split("\n")]
    non_empty = [ln for ln in raw_lines if ln]
    if (
        len(non_empty) >= 2
        and non_empty[1] in ("住所",)
        and not re.match(r"^(氏名|住所|〒)", non_empty[0])
    ):
        person, company = split_person_company_line(non_empty[0], phone)
        name = person or _clean_name(non_empty[0])

    yahoo = _parse_yahoo_delivery_block(text)
    if yahoo and (yahoo.name or yahoo.address or yahoo.zip_code):
        return yahoo

    # タブ区切り（ヤフオクの表コピー）
    if "\t" in text:
        for line in text.splitlines():
            cols = [c.strip() for c in re.split(r"\t+", line) if c.strip()]
            if len(cols) >= 2:
                if cols[0] in ("氏名", "お名前") and not name:
                    name = _clean_name(cols[1])
                if cols[0] == "住所" and not address:
                    block = " ".join(cols[1:])
                    if not zip_code:
                        zip_code = _extract_zip(block)
                    address = _clean_address_block(block)
                if cols[0] in (
                    "電話",
                    "電話番号",
                    "TEL",
                    "携帯",
                    "携帯電話",
                    "お届け先電話番号",
                ) and not phone:
                    phone = _normalize_phone(cols[1])

    if re.search(r"氏名\s*[:：]", text):
        m_name = re.search(r"氏名\s*[:：]\s*(.+?)(?:\n|\t|$)", text)
        if m_name:
            name = _clean_name(m_name.group(1))
        m_addr = re.search(
            r"住所\s*[:：]\s*([\s\S]+?)(?=\n(?:配送|追跡|お届け|電話|携帯|TEL|商品|オークション|$))",
            text,
        )
        if m_addr:
            block = m_addr.group(1).strip()
            if not zip_code:
                zip_code = _extract_zip(block)
            address = _clean_address_block(block)
        if not phone:
            phone = _extract_phone_from_lines(
                [ln.strip() for ln in text.splitlines()]
            ) or _extract_phone_inline(text)
        if name or address:
            address = _strip_trailing_phone_token(address)
            return ShippingInfo(name=name, zip_code=zip_code, address=address, phone=phone)

    lines = [ln.strip() for ln in text.split("\n")]
    addr_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^氏名\s*[:：]?\s*$", line) and i + 1 < len(lines):
            name = _clean_name(lines[i + 1])
            i += 2
            continue
        if re.match(r"^住所\s*[:：]?\s*$", line):
            i += 1
            while i < len(lines):
                nxt = lines[i]
                if re.match(
                    r"^(配送|追跡|お届け|電話|携帯|TEL|氏名|商品|オークション)",
                    nxt,
                ):
                    break
                if _is_standalone_phone_line(nxt):
                    if not phone:
                        phone = _normalize_phone(nxt)
                    i += 1
                    break
                if nxt:
                    addr_lines.append(nxt)
                i += 1
            continue
        if line.startswith("氏名") and ("：" in line or ":" in line):
            name = _clean_name(re.split(r"[:：]", line, 1)[1])
        elif line.startswith("住所") and ("：" in line or ":" in line):
            rest = re.split(r"[:：]", line, 1)[1].strip()
            if rest:
                addr_lines.append(rest)
        i += 1

    if not phone:
        phone = _extract_phone_from_lines(lines)
    if not phone:
        phone = _extract_phone_inline(text)

    if addr_lines:
        block = "\n".join(addr_lines)
        if not zip_code:
            zip_code = _extract_zip(block)
        address = _clean_address_block(block)
        if not phone:
            for ln in addr_lines:
                if _is_standalone_phone_line(ln):
                    phone = _normalize_phone(ln)
                    break

    if not name:
        m = re.search(r"氏名\s*[:：]\s*(.+)", text)
        if m:
            name = _clean_name(m.group(1).split("\n")[0].split("\t")[0])

    if not zip_code:
        zip_code = _extract_zip(text)

    jp_fallback = _parse_japanese_shipping_block(text)
    if jp_fallback:
        if not name:
            name = jp_fallback.name
        if not address:
            address = jp_fallback.address
        if not zip_code:
            zip_code = jp_fallback.zip_code
        if not phone:
            phone = jp_fallback.phone

    if not name and not address:
        # 「お届け先」ブロック形式（ラベル無し）にフォールバック
        fallback = _parse_no_label_block(text)
        if fallback and (fallback.name or fallback.address or fallback.zip_code):
            return fallback
        _log_missing("お届け先", "お届け先/配送先/送付先ブロック、氏名、住所ラベルを検出できません")
        raise ValueError(
            "氏名・住所を読み取れませんでした。\n"
            "ヤフオクの「お届け情報」をそのまま貼り付けてください。"
        )

    digits = re.sub(r"\D", "", zip_code)
    if digits and len(digits) != 7:
        raise ValueError(f"郵便番号が7桁ではありません: {zip_code}")
    if digits:
        zip_code = digits

    if not phone:
        phone = _extract_phone(text)
    address = _strip_trailing_phone_token(address)
    if not name:
        _log_missing("お届け先 氏名", "氏名/名前/お名前ラベル、または住所ブロック末尾の氏名候補がありません")
    if not address:
        _log_missing("お届け先 住所", "住所/お届け先住所ラベル、または都道府県・市区町村を含む行がありません")
    if not zip_code:
        _log_missing("お届け先 郵便番号", "〒123-4567 または 1234567 形式がありません")
    if not phone:
        _log_missing("お届け先 電話番号", "電話/TEL/携帯ラベル、または0から始まる10-11桁の番号がありません")
    return ShippingInfo(name=name, zip_code=zip_code, address=address, phone=phone)
