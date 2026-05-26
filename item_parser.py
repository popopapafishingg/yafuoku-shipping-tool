# -*- coding: utf-8 -*-
"""オークションIDと商品名だけを抽出（落札価格などは無視）。"""
from __future__ import annotations

import re
import unicodedata

AUCTION_ID_RE = re.compile(
    r"^([a-zueoklbnsxjcrmwtdfhgp]\d{6,14})$",
    re.IGNORECASE,
)


def _normalize_match_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    return text


def _log_missing(field: str, reason: str) -> None:
    print(f"[extract] {field} missing: {reason}")

_SKIP_LINE_RE = re.compile(
    r"^(落札数量|落札価格|現在価格|入札件数|終了日時|終了時間|終了日|終了|送料|即決|"
    r"出品者|評価|支払|落札者|商品番号|管理番号|お支払|発送|取引ナビ|メッセージ|"
    r"配送方法|配送業者|配送会社|追跡番号|お問い合わせ番号|お届け先|お届け情報|"
    r"郵便番号|住所|氏名|電話|電話番号|TEL|携帯|購入者|個数)",
    re.I,
)

# 商品名文字列から除去するパターン
_JUNK_IN_TEXT_RE = re.compile(
    r"(落札数量|落札価格|現在価格|入札件数|終了日時|終了時間|終了日|"
    r"オークション\s*ID|商品番号|管理番号|送料|出品者|評価)"
    r"\s*[:：]?\s*[^\n]*",
    re.I,
)


def looks_like_auction_id(s: str) -> bool:
    s = s.strip()
    if not s:
        return False
    if AUCTION_ID_RE.match(s):
        return True
    return bool(re.match(r"^[a-z]\d{6,14}$", s, re.I))


def _is_skip_line(line: str) -> bool:
    line = line.strip()
    if not line:
        return True
    if _SKIP_LINE_RE.match(line):
        return True
    if re.search(r"オークション\s*ID", line, re.I):
        return True
    if re.search(r"^(落札|終了)", line, re.I):
        return True
    if re.match(r"^商品名\s*[:：]?\s*$", line, re.I):
        return True
    return False


def _clean_product_text(text: str, auction_id: str = "") -> str:
    if not text:
        return ""
    text = re.split(r"オークション\s*ID", text, maxsplit=1, flags=re.I)[0]
    text = re.sub(
        r"(?:時間|時間指定|希望時間帯|配達希望時間|配送希望時間)\s*[:：]?\s*"
        r"(?:午前中|\d{1,2}\s*時\s*[-〜~－]\s*\d{1,2}\s*時).*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\d{1,2}\s*時\s*[-〜~－]\s*\d{1,2}\s*時", "", text)
    text = _JUNK_IN_TEXT_RE.sub("", text)
    if auction_id:
        text = text.replace(auction_id, "")
    text = re.sub(r"\s+", " ", text).strip(" 　-－")
    return text


def _extract_auction_id(text: str) -> str:
    m = re.search(r"オークション\s*ID\s*[:：]\s*([a-z0-9]+)", text, re.I)
    if m:
        return m.group(1).strip()
    norm = _normalize_match_text(text)
    m = re.search(
        r"(?:オークション\s*ID|オークションID|商品\s*ID|管理\s*番号|落札\s*ID)"
        r"\s*[:：#No.\-]*\s*([a-z][0-9]{6,14})",
        norm,
        re.I,
    )
    if m:
        return m.group(1).strip()
    for line in text.splitlines():
        line = line.strip()
        if looks_like_auction_id(line):
            return line
        for p in re.split(r"[\t\s]+", line):
            if looks_like_auction_id(p):
                return p
    for p in re.split(r"[\t\s　]+", norm):
        if looks_like_auction_id(p):
            return p
    return ""


def _extract_product_name_jp(text: str, auction_id: str) -> str:
    norm = _normalize_match_text(text)
    lines = [ln.strip(" :：-‐ー・") for ln in norm.splitlines()]
    labels = (
        "商品名",
        "商品タイトル",
        "タイトル",
        "品名",
        "落札商品",
        "商品",
    )
    stops = re.compile(
        r"^(オークション|商品ID|管理番号|落札数量|数量|個数|配送|送料|支払|お届け|時間|保険|出品者|落札者|購入者|取引)"
    )
    for i, line in enumerate(lines):
        compact = re.sub(r"\s+", "", line)
        for label in labels:
            if compact.startswith(label):
                rest = compact[len(label):].lstrip(":：-‐ー・")
                if rest and not looks_like_auction_id(rest):
                    return _clean_product_text(rest, auction_id)
                parts: list[str] = []
                for nxt in lines[i + 1 : i + 4]:
                    ncompact = re.sub(r"\s+", "", nxt)
                    if not ncompact or stops.search(ncompact) or looks_like_auction_id(ncompact):
                        break
                    parts.append(nxt)
                if parts:
                    return _clean_product_text(_join_product(parts), auction_id)
    return ""


def _extract_product_name(text: str, auction_id: str) -> str:
    jp_product = _extract_product_name_jp(text, auction_id)
    if jp_product:
        return jp_product
    lines_out: list[str] = []

    m = re.search(
        r"(?:商品\s*タイトル|商品\s*名|タイトル|品名)\s*[:：]\s*(.*)",
        text,
        re.I | re.S,
    )
    if m:
        block = m.group(1)
        for ln in block.splitlines():
            ln = ln.strip()
            if not ln or _is_skip_line(ln):
                break
            if looks_like_auction_id(ln):
                break
            lines_out.append(ln)
        if lines_out:
            return _clean_product_text(_join_product(lines_out), auction_id)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    collecting = False
    for ln in lines:
        if re.match(r"^(?:商品\s*タイトル|商品\s*名|タイトル|品名)\s*[:：]", ln, re.I):
            rest = re.split(r"[:：]", ln, 1)[-1].strip()
            if rest and not _is_skip_line(rest) and not looks_like_auction_id(rest):
                lines_out.append(rest)
            collecting = True
            continue
        if _is_skip_line(ln) or looks_like_auction_id(ln):
            if collecting:
                break
            continue
        if ln == auction_id:
            continue
        if collecting:
            lines_out.append(ln)
        elif auction_id and ln != auction_id and not _is_skip_line(ln):
            if not looks_like_auction_id(ln):
                lines_out.append(ln)

    if not lines_out and len(lines) >= 2:
        if looks_like_auction_id(lines[0]):
            for ln in lines[1:]:
                if not _is_skip_line(ln) and not looks_like_auction_id(ln):
                    lines_out.append(ln)
                    if _is_skip_line(ln):
                        break

    if len(lines) == 1:
        one = lines[0]
        m2 = re.match(r"^[a-z]\d{6,14}\s+(.+)$", one, re.I)
        if m2:
            return _clean_product_text(m2.group(1).strip(), auction_id)

    product = _clean_product_text(_join_product(lines_out), auction_id)
    if product:
        return product
    return _extract_product_name_jp(text, auction_id)


def _join_product(parts: list[str]) -> str:
    return " ".join(p.strip() for p in parts if p.strip())


def extract_quantity(text: str) -> int:
    """落札数量などから個数を取得。無ければ 1。"""
    norm = _normalize_match_text(text)
    for pat in (
        r"(?:落札\s*数量|数量|個数|購入数|注文数)\s*[:：]?\s*(\d+)",
        r"(?:×|x|X)\s*(\d+)\s*(?:個|点|枚|本)?",
        r"(\d+)\s*(?:個|点|枚|本)\s*(?:落札|購入|注文)?",
    ):
        m = re.search(pat, norm, re.I)
        if m:
            return max(1, int(m.group(1)))
    for pat in (
        r"落札数量\s*[:：]?\s*(\d+)",
        r"数量\s*[:：]?\s*(\d+)",
        r"個数\s*[:：]?\s*(\d+)",
        r"個\s*数\s*[:：]?\s*(\d+)",
        r"落札数量\s*[:：]\s*(\d+)",
        r"数量\s*[:：]\s*(\d+)",
        r"(\d+)\s*個\s*$",
    ):
        m = re.search(pat, text, re.I | re.M)
        if m:
            return max(1, int(m.group(1)))
    _log_missing("個数", "落札数量/数量/個数/×2/2個 の表記がないため 1 として扱います")
    return 1


def extract_delivery_time(text: str) -> str:
    """取引情報から配送希望時間を取得。無指定なら空文字。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    norm = _normalize_match_text(text)
    jp_patterns = (
        r"(?:お届け|配達|配送)?\s*(?:希望)?\s*時間(?:帯|指定)?\s*[:：]?\s*([^\n\r]+)",
        r"(?:時間指定|希望時間帯|配達希望時間|お届け希望時間)\s*[:：]?\s*([^\n\r]+)",
    )
    for pat in jp_patterns:
        m = re.search(pat, norm, re.I)
        if not m:
            continue
        value = re.sub(r"\s+", " ", m.group(1)).strip(" :：-‐ー・")
        if value and not re.search(r"(指定なし|希望なし|なし|不要|無指定)", value):
            return value
        return ""
    patterns = (
        r"(?:配達|配送|お届け)\s*(?:希望)?\s*時間(?:帯|指定)?\s*[:：]\s*([^\n\r]+)",
        r"時間指定\s*[:：]\s*([^\n\r]+)",
        r"希望時間帯\s*[:：]\s*([^\n\r]+)",
    )
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        value = re.sub(r"\s+", " ", m.group(1)).strip()
        if value and not re.search(r"指定なし|希望なし|なし|不要|無指定", value):
            return value
        return ""
    m = re.search(r"(\d{1,2}\s*(?::\d{2}|時)?\s*[-〜~－]\s*\d{1,2}\s*(?::\d{2}|時))", norm)
    if m:
        return re.sub(r"\s+", "", m.group(1))
    _log_missing("時間指定", "時間指定/希望時間帯ラベル、または 18時-20時 形式がありません")
    return ""


def extract_insurance_requested(text: str) -> bool | None:
    norm = _normalize_match_text(text)
    m = re.search(r"(?:運送|配送|輸送)?\s*保険\s*[:：]?\s*([^\n\r]+)", norm, re.I)
    if m:
        value = m.group(1).strip()
        if re.search(r"(あり|有|希望|要|加入|付ける|つける|必要|yes|true)", value, re.I):
            return True
        if re.search(r"(なし|無|不要|未加入|希望しない|いらない|no|false)", value, re.I):
            return False
    """保険の有無が本文に明記されていれば返す。無ければ None。"""
    if re.search(r"(?:保険|運送保険|輸送保険)\s*[:：]?\s*(?:あり|有|要|必要|加入|希望)", text):
        return True
    if re.search(r"(?:保険|運送保険|輸送保険)\s*[:：]?\s*(?:なし|無|不要|未加入|希望なし)", text):
        return False
    _log_missing("保険", "保険/運送保険/輸送保険ラベルと、あり/なし等の値がありません")
    return None


def parse_auction_product(text: str) -> tuple[str, str, int]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return "", "", 1
    auction_id = _extract_auction_id(text)
    product_name = _extract_product_name(text, auction_id)
    quantity = extract_quantity(text)
    if not auction_id:
        _log_missing("オークションID", "オークションID/商品ID/管理番号ラベル、または a123456789 形式のIDがありません")
    if not product_name:
        _log_missing("商品名", "商品名/商品タイトル/タイトル/品名/落札商品ラベルがありません")
    return auction_id, product_name, quantity


def extract_item_from_delivery_text(text: str) -> tuple[str, str]:
    aid, prod, _qty = parse_auction_product(text)
    return aid, prod
