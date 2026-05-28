# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import json
import os
import re
import tempfile
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from address_utils import wrap_for_print
from sagawa_box_resolver import (
    SagawaPrintBoxes,
    iter_input_guide_rects,
    resolve_print_boxes,
)
from sagawa_field_draw import (
    AddressFieldStyle,
    CompanyFieldStyle,
    NameFieldStyle,
    PhoneFieldStyle,
    ZipFieldStyle,
    draw_dest_input_fields,
    normalize_sender_fields,
    normalize_recipient_fields,
)
from item_parser import parse_auction_product
from label_layout import SagawaLayout, absolute_field_rects, get_sagawa_layout
from models import LabelPrintData, SenderInfo
from parser import ShippingInfo
from sagawa_fields import AbsBox, baseline_in_box
from sagawa_page import (
    SAGAWA_PAGE_H,
    SAGAWA_PAGE_HEIGHT_MM,
    SAGAWA_PAGE_SIZE,
    SAGAWA_PAGE_W,
    SAGAWA_PAGE_WIDTH_MM,
    mm_to_pt,
    sagawa_scan_pdf_path,
)
from sagawa_print_config import (
    adjustment_summary,
    cfg_box,
    cfg_cells,
    cfg_line_boxes,
    cfg_number,
    load_print_config,
    shifted_box,
    shifted_boxes,
)

CARRIER_TITLES = {
    "sagawa": "佐川",
    "seino": "西濃",
}

PRINT_MODE_PREVIEW_LAYOUT = "PREVIEW_LAYOUT"
PRINT_MODE_REAL_SAGAWA_OVERLAY = "REAL_SAGAWA_OVERLAY"
FORBIDDEN_PRINT_NAME_PARTS = (
    "preview_layout",
    "sagawa_preview_layout_latest",
    "print_scale_test",
)

_PREVIEW_UNDERLAY_ATTR = "_yafuoku_preview_underlay"


def _set_preview_underlay(c, on: bool) -> None:
    setattr(c, _PREVIEW_UNDERLAY_ATTR, on)


def _preview_underlay_enabled(c) -> bool:
    return bool(getattr(c, _PREVIEW_UNDERLAY_ATTR, False))


def _register_japanese_font() -> str:
    candidates = [
        (r"C:\Windows\Fonts\msgothic.ttc", 0, "MSGothic"),
        (r"C:\Windows\Fonts\meiryo.ttc", 0, "Meiryo"),
        (r"C:\Windows\Fonts\YuGothM.ttc", 0, "YuGothic"),
    ]
    for path, subfont, name in candidates:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path, subfontIndex=subfont))
                return name
            except Exception:
                continue
    return "Helvetica"


def _label_draw_string(c, font: str, size: int, x: float, y: float, text: str) -> None:
    if not text:
        return
    c.setFont(font, size)
    c.drawString(x, y, text)


def _fit_font_size(c, font: str, text: str, box: AbsBox, size: int, *, min_size: int = 5) -> int:
    size = int(size)
    while size > min_size and c.stringWidth(text, font, size) > max(1.0, box.w - 4):
        size -= 1
    return size


_HYPHENATED_NUMBER = re.compile(r"\d+[-－]\d+")


def _tokenize_wrap_units(text: str) -> list[str]:
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


def _wrap_by_width(
    c,
    font: str,
    text: str,
    box: AbsBox,
    size: int,
    max_lines: int,
) -> list[str]:
    units = _tokenize_wrap_units(text)
    if not units:
        return []
    max_width = max(1.0, box.w - 4)
    lines: list[str] = []
    current = ""
    for unit in units:
        sep = "" if not current else " "
        cand = f"{current}{sep}{unit}" if current else unit
        if current and c.stringWidth(cand, font, size) > max_width:
            lines.append(current)
            current = unit
            if len(lines) >= max_lines:
                return lines[:max_lines]
        else:
            current = cand
    if current and len(lines) < max_lines:
        lines.append(current)
    return lines


def _layout_address_lines(
    c,
    font: str,
    address: str,
    company: str,
    boxes: tuple[AbsBox, ...],
    size: int,
) -> list[str]:
    """住所行ボックスへ住所+会社名を割り当て（番地の -8 は分割しない）。"""
    n = len(boxes)
    if n <= 0:
        return []
    company = (company or "").strip()
    address = (address or "").strip()
    max_addr = n - (1 if company else 0)
    if max_addr <= 0:
        return [company][:n]
    addr_lines = _wrap_by_width(c, font, address, boxes[0], size, max_addr)
    while len(addr_lines) < max_addr:
        addr_lines.append("")
    if company:
        lines = addr_lines + [company]
    else:
        lines = addr_lines
    while len(lines) < n:
        lines.append("")
    return lines[:n]


def _draw_single_line_in_box(
    c,
    font: str,
    text: str,
    box: AbsBox,
    size: int,
    *,
    align: str = "left",
    min_size: int = 5,
) -> None:
    """1行テキストを枠内に収める（再折り返ししない）。"""
    text = (text or "").strip()
    if not text:
        return
    draw_size = int(size)
    while draw_size > min_size and c.stringWidth(text, font, draw_size) > max(1.0, box.w - 4):
        draw_size -= 1
    y = baseline_in_box(box, draw_size)
    width = c.stringWidth(text, font, draw_size)
    if align == "right":
        x = box.x + box.w - width - 2
    elif align == "center":
        x = box.x + (box.w - width) / 2.0
    else:
        x = box.x + 2
    _label_draw_string(c, font, draw_size, x, y, text)


def _zip_digits(zip_code: str) -> str:
    z = (zip_code or "").replace("-", "").replace("－", "").strip()
    digits = "".join(ch for ch in z if ch.isdigit())
    return digits[:7] if len(digits) >= 7 else digits


def _draw_zip_in_cells(
    c,
    font: str,
    zip_code: str,
    cells: tuple[AbsBox, ...],
    size: int,
    spacing: float = 0.0,
) -> None:
    z = _zip_digits(zip_code)
    if len(z) != 7 or not cells:
        return
    for i, ch in enumerate(z):
        if i >= len(cells):
            break
        box = cells[i]
        y = baseline_in_box(box, size)
        w = c.stringWidth(ch, font, size)
        x = box.x + (box.w - w) / 2.0
        _label_draw_string(c, font, size, x, y, ch)


def _draw_text_in_box(
    c,
    font: str,
    text: str,
    box: AbsBox,
    size: int,
    *,
    wrap: int = 22,
    max_lines: int = 1,
    line_gap: float = 1.0,
    align: str = "left",
    min_size: int = 5,
) -> None:
    text = (text or "").strip()
    if not text:
        return
    draw_size = int(size)
    lines = _wrap_by_width(c, font, text, box, draw_size, max_lines)
    while draw_size > min_size:
        line_h = draw_size + line_gap
        if len(lines) * line_h <= box.h + 1 and all(
            c.stringWidth(line, font, draw_size) <= box.w - 4 for line in lines
        ):
            break
        draw_size -= 1
        lines = _wrap_by_width(c, font, text, box, draw_size, max_lines)
    line_h = draw_size + line_gap
    top = box.y + box.h
    for i, line in enumerate(lines):
        if max_lines == 1 and len(lines) == 1:
            y = box.y + (box.h - draw_size) / 2.0 + draw_size * 0.28
        else:
            y = baseline_in_box(AbsBox(box.x, top - (i + 1) * line_h, box.w, line_h), draw_size)
        width = c.stringWidth(line, font, draw_size)
        if align == "right":
            x = box.x + box.w - width - 2
        elif align == "center":
            x = box.x + (box.w - width) / 2.0
        else:
            x = box.x + 2
        _label_draw_string(c, font, draw_size, x, y, line)


def _draw_single_line_by_field_name(
    c,
    font: str,
    text: str,
    fields: dict[str, AbsBox],
    field_name: str,
    size: int,
    *,
    align: str = "left",
) -> None:
    box = fields.get(field_name)
    if box is None:
        return
    _draw_single_line_in_box(c, font, text, box, size, align=align)


def _format_phone(phone: str) -> str:
    p = (phone or "").strip()
    if not p:
        return ""
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) == 11 and digits.startswith(("090", "080", "070")):
        return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
    if len(digits) == 10 and digits.startswith("0"):
        return f"{digits[:2]}-{digits[2:6]}-{digits[6:]}"
    return p


def _format_insurance_yen(amount: int) -> str:
    try:
        n = int(amount)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        return ""
    return f"\uffe5{n:,}"


def _compact_product_lines(product: str, wrap: int, max_lines: int) -> list[str]:
    product = (product or "").strip()
    if not product:
        return []
    return wrap_for_print(product, width=wrap)[:max_lines]


def _draw_quantity(c, font: str, quantity: int, layout: SagawaLayout, cfg: dict) -> None:
    if quantity < 1:
        return
    box = shifted_box(cfg, cfg_box(cfg, "QUANTITY", layout.fields.quantity), "PRICE")
    text = str(int(quantity))
    size = int(cfg.get("FONT_SIZE_QUANTITY", layout.quantity_size))
    y = baseline_in_box(box, size)
    w = c.stringWidth(text, font, size)
    x = box.x + (box.w - w) / 2.0
    _label_draw_string(c, font, size, x, y, text)


def _draw_insurance(c, font: str, data: LabelPrintData, layout: SagawaLayout, cfg: dict) -> None:
    if not data.insurance_enabled:
        return
    chk = shifted_box(cfg, cfg_box(cfg, "INSURANCE_CHECK", layout.fields.insurance_check), "PRICE")
    amt = shifted_box(cfg, cfg_box(cfg, "INSURANCE_AMOUNT", layout.fields.insurance_amount), "PRICE")
    cx = chk.x + chk.w * 0.35
    cy = chk.y + chk.h * 0.35
    c.setLineWidth(1.2)
    c.line(cx, cy, cx + chk.w * 0.45, cy + chk.h * 0.45)
    c.line(cx + chk.w * 0.45, cy, cx, cy + chk.h * 0.45)
    text = _format_insurance_yen(data.insurance_amount)
    print(f"insurance_amount = {int(data.insurance_amount or 0)}")
    print(f"formatted_insurance_amount = {text}")
    if text:
        _draw_text_in_box(
            c,
            font,
            text,
            amt,
            int(cfg.get("FONT_SIZE_INSURANCE", layout.insurance_amount_size)),
            wrap=16,
            max_lines=1,
            align="right",
        )


def _normalize_time_slot(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = re.sub(r"\s+", "", text.strip())
    if not text:
        return ""
    if "午前" in text or re.search(r"\b(?:am|morning)\b", text, re.I):
        return "MORNING"
    m = re.search(r"(\d{1,2})(?::00)?[^\d]{0,8}(\d{1,2})(?::00)?", text)
    if m:
        pair = f"{int(m.group(1))}_{int(m.group(2))}"
        if pair in {"12_14", "14_16", "16_18", "18_20", "19_21"}:
            return pair
    return ""


def _draw_check_mark(c, x: float, y: float, size: float) -> None:
    c.saveState()
    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(2.4)
    c.line(x, y, x + size, y + size)
    c.line(x + size, y, x, y + size)
    c.restoreState()


def _draw_time_slot(c, data: LabelPrintData, cfg: dict) -> None:
    delivery_time = getattr(data, "delivery_time", "")
    slot = _normalize_time_slot(delivery_time)
    if not slot and bool(cfg.get("DEBUG_TIME_CHECK_FORCE", False)):
        slot = "18_20"
        if not delivery_time:
            delivery_time = "(DEBUG_TIME_CHECK_FORCE)"
    print(f"delivery_time = {delivery_time}")
    print(f"normalized_time_slot = {slot or '(none)'}")
    if not slot:
        return
    x_key = f"TIME_CHECK_{slot}_X"
    y_key = f"TIME_CHECK_{slot}_Y"
    x = cfg_number(cfg, x_key) + cfg_number(cfg, "OFFSET_X") + cfg_number(cfg, "TIME_OFFSET_X")
    y = cfg_number(cfg, y_key) + cfg_number(cfg, "OFFSET_Y") + cfg_number(cfg, "TIME_OFFSET_Y")
    size = cfg_number(cfg, "TIME_CHECK_MARK_SIZE", 8.0)
    print(f"draw time check slot = {slot}")
    print(f"draw time check: slot={slot} x={x:g} y={y:g} size={size:g}")
    _draw_check_mark(c, x, y, size)


def _draw_item_block_absolute(
    c,
    font: str,
    data: LabelPrintData,
    layout: SagawaLayout,
    cfg: dict,
    boxes: SagawaPrintBoxes,
) -> None:
    item_id_box = boxes.item_id
    item_lines = boxes.item_lines
    aid = (data.auction_id or "").strip()
    if aid:
        _draw_single_line_in_box(
            c,
            font,
            f"ID:{aid}",
            item_id_box,
            int(cfg.get("FONT_SIZE_ITEM_ID", layout.item_id_size)),
        )

    product = re.sub(
        r"(?:時間|時間指定|希望時間帯|配達希望時間|配送希望時間)\s*[:：]?\s*"
        r"(?:午前中|\d{1,2}\s*時\s*[-〜~－]\s*\d{1,2}\s*時).*",
        "",
        (data.product_name or "").strip(),
    )
    product = re.sub(r"\d{1,2}\s*時\s*[-〜~－]\s*\d{1,2}\s*時", "", product).strip()
    if aid and not product:
        _, product, _q = parse_auction_product(f"{aid} {product}")
    item_size = int(cfg.get("FONT_SIZE_ITEM", layout.item_text_size))
    lines = _wrap_by_width(
        c,
        font,
        product,
        item_lines[0],
        item_size,
        min(2, len(item_lines)),
    )
    for box, line in zip(item_lines, lines):
        _draw_single_line_in_box(c, font, line, box, item_size)


def _draw_recipient_absolute(
    c,
    font: str,
    data: LabelPrintData,
    layout: SagawaLayout,
    cfg: dict,
    boxes: SagawaPrintBoxes,
) -> None:
    info = data.recipient
    fields = normalize_recipient_fields(
        name=info.name,
        zip_code=info.zip_code,
        address=info.address,
        phone=info.phone,
        company=getattr(info, "company", "") or "",
    )
    draw_dest_input_fields(
        c,
        font,
        fields,
        boxes.dest,
        zip_style=ZipFieldStyle(
            font_size=int(cfg.get("FONT_SIZE_ZIP", layout.zip_digit_size)),
            baseline_ratio=float(cfg.get("BASELINE_RATIO_ZIP", 0.4)),
        ),
        addr_style=AddressFieldStyle(
            font_size=int(cfg.get("FONT_SIZE_ADDRESS", layout.addr_size)),
            baseline_ratio=float(cfg.get("BASELINE_RATIO_ADDRESS", 0.42)),
        ),
        company_style=CompanyFieldStyle(
            font_size=int(cfg.get("FONT_SIZE_ADDRESS", layout.addr_size)),
        ),
        name_style=NameFieldStyle(
            font_size=int(cfg.get("FONT_SIZE_NAME", layout.name_size)),
            baseline_ratio=float(cfg.get("BASELINE_RATIO_NAME", 0.4)),
        ),
        phone_style=PhoneFieldStyle(
            font_size=int(cfg.get("FONT_SIZE_PHONE", layout.recipient_phone_size)),
            baseline_ratio=float(cfg.get("BASELINE_RATIO_PHONE", 0.4)),
        ),
    )


def _draw_sender_absolute(
    c,
    font: str,
    data: LabelPrintData,
    layout: SagawaLayout,
    cfg: dict,
    boxes: SagawaPrintBoxes,
) -> None:
    if not data.print_sender:
        return
    # sender は app.py で優先順位解決済みデータを使用する（recipientと完全分離）。
    s = data.sender
    sender_data = normalize_sender_fields(
        name=s.name,
        zip_code=s.zip_code,
        address=s.address,
        phone=s.phone,
    )
    size = int(cfg.get("FONT_SIZE_SENDER", layout.sender_line_size))
    from sagawa_recipient_layout import normalize_zip_row_cells

    sender_zip = normalize_zip_row_cells(boxes.sender_zip)
    semantic = boxes.semantic_fields().as_dict()
    _draw_zip_in_cells(
        c,
        font,
        sender_data.zip_code,
        tuple(
            semantic.get(f"sender_zip_{i + 1}", b) for i, b in enumerate(sender_zip)
        ),
        int(cfg.get("FONT_SIZE_ZIP", layout.sender_zip_digit_size)),
        cfg_number(cfg, "ZIP_SPACING"),
    )
    if sender_data.address:
        for box, line in zip(
            tuple(
                semantic.get(f"sender_address_{i + 1}", b)
                for i, b in enumerate(boxes.sender_addr)
            ),
            wrap_for_print(sender_data.address.strip(), width=layout.sender_wrap)[: len(boxes.sender_addr)],
        ):
            _draw_single_line_in_box(c, font, line, box, size)
    if sender_data.name:
        _draw_single_line_by_field_name(
            c,
            font,
            sender_data.name.strip(),
            semantic,
            "sender_name",
            size,
        )
    phone = _format_phone(sender_data.phone)
    if phone:
        _draw_single_line_by_field_name(
            c,
            font,
            phone,
            semantic,
            "sender_phone",
            size,
        )


def _draw_sagawa_absolute(
    c,
    font: str,
    data: LabelPrintData,
    layout: SagawaLayout,
    cfg: dict,
    boxes: SagawaPrintBoxes,
) -> None:
    # recipient/sender と、保険・時間指定・個数は独立描画（相互に上書きしない）。
    _draw_recipient_absolute(c, font, data, layout, cfg, boxes)
    _draw_sender_absolute(c, font, data, layout, cfg, boxes)
    _draw_quantity(c, font, data.quantity, layout, cfg)
    _draw_insurance(c, font, data, layout, cfg)
    _draw_time_slot(c, data, cfg)
    _draw_item_block_absolute(c, font, data, layout, cfg, boxes)


def _set_no_print_scaling(c) -> None:
    try:
        c.setViewerPreference("PrintScaling", "None")
    except Exception:
        pass


def _log_page_size(prefix: str = "") -> None:
    print(f"{prefix}PAGE_WIDTH_MM = {SAGAWA_PAGE_WIDTH_MM:g}")
    print(f"{prefix}PAGE_HEIGHT_MM = {SAGAWA_PAGE_HEIGHT_MM:g}")
    print(f"{prefix}PAGE_WIDTH_PT = {SAGAWA_PAGE_W:.2f}")
    print(f"{prefix}PAGE_HEIGHT_PT = {SAGAWA_PAGE_H:.2f}")


def _log_print_job(
    *,
    mode: str,
    output_pdf: Path | str,
    printer: str = "",
    auto_print: bool = False,
    result: str = "",
) -> None:
    print(f"PRINT_MODE = {mode}")
    print(f"OUTPUT_PDF = {output_pdf}")
    print(f"PRINTER = {printer or '(none)'}")
    print(f"AUTO_PRINT = {str(bool(auto_print)).lower()}")
    print(f"RESULT = {result or '(pending)'}")


def _sagawa_calibration_rotation() -> str:
    try:
        from excel_writer import _templates_dir

        p = _templates_dir() / "sagawa_calibration.json"
        if p.is_file():
            rot = json.loads(p.read_text(encoding="utf-8")).get("rotation", "")
            if isinstance(rot, str):
                return rot.strip().lower()
    except Exception:
        pass
    return "raw"


def _sagawa_scan_image_bytes() -> bytes | None:
    scan = sagawa_scan_pdf_path()
    if not scan:
        return None
    try:
        import fitz
    except ImportError:
        return None
    try:
        doc = fitz.open(scan)
        page = doc[0]
        rot = _sagawa_calibration_rotation()
        mat = fitz.Matrix(2.0, 2.0)
        if rot == "cw":
            mat = fitz.Matrix(2.0, 2.0).prerotate(90)
        elif rot == "ccw":
            mat = fitz.Matrix(2.0, 2.0).prerotate(-90)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        doc.close()
        return pix.tobytes("png")
    except Exception:
        return None


def _draw_sagawa_scan_background(c) -> None:
    img_bytes = _sagawa_scan_image_bytes()
    if not img_bytes:
        return
    c.drawImage(
        ImageReader(io.BytesIO(img_bytes)),
        0,
        0,
        width=SAGAWA_PAGE_W,
        height=SAGAWA_PAGE_H,
    )


def _filter_preview_rects(
    rects: list[tuple[str, float, float, float, float]],
) -> list[tuple[str, float, float, float, float]]:
    out: list[tuple[str, float, float, float, float]] = []
    for name, x, y, w, h in rects:
        if w < 0.5 or h < 0.5:
            continue
        cx, cy = x + w / 2.0, y + h / 2.0
        # 右上（問合せTEL・33308 付近）
        if cx > 470 and cy > 710:
            continue
        # 上端の集荷TEL付近（個数以外）
        if cy > 812 and "個数" not in name:
            continue
        # 依頼主郵便が右端（印字333-0831側）に飛ぶ誤枠
        if "依頼主・郵便" in name and cx > 320:
            continue
        # 届け先郵便が右側にある誤枠
        if "届け先・郵便" in name and cx > 280:
            continue
        # 集荷TEL付近の空枠
        if 450 < cx < 540 and cy > 800:
            continue
        if "品名" in name and cx > 400:
            continue
        # 右余白の細長枠・品名のはみ出し
        if cx > 420 and ("品名" in name or w < 35):
            continue
        # 下端バーコード付近
        if cy < 95:
            continue
        # 郵便マスが極小（誤検出）
        if "郵便マス" in name and (w < 8 or h < 8):
            continue
        out.append((name, x, y, w, h))
    return out


def _draw_sagawa_scan_field_borders(
    c,
    boxes: SagawaPrintBoxes,
    *,
    labels: bool = False,
    guides: bool = False,
) -> None:
    c.saveState()
    if guides:
        c.setStrokeColorRGB(0.4, 0.4, 0.4)
        c.setLineWidth(0.25)
        c.setDash(1, 4)
        step = 20
        x = 0
        while x <= SAGAWA_PAGE_W:
            c.line(x, 0, x, SAGAWA_PAGE_H)
            x += step
        y = 0
        while y <= SAGAWA_PAGE_H:
            c.line(0, y, SAGAWA_PAGE_W, y)
            y += step
    c.setStrokeColorRGB(1, 0, 0)
    c.setLineWidth(0.8)
    c.setDash(3, 2)
    for name, box in iter_input_guide_rects(boxes):
        c.rect(box.x, box.y, box.w, box.h, stroke=1, fill=0)
        if labels:
            c.setFillColorRGB(0.0, 0.1, 0.8)
            c.setFont("Helvetica", 5)
            c.drawString(box.x + 1, box.y + box.h + 1, name)
            c.setFillColorRGB(0, 0, 0)
    c.restoreState()


def _draw_sagawa_preview_underlay(
    c,
    boxes: SagawaPrintBoxes,
    *,
    underlay: bool = True,
    borders: bool = True,
    labels: bool = False,
    guides: bool = False,
) -> None:
    if underlay:
        _draw_sagawa_scan_background(c)
    if borders or labels or guides:
        _draw_sagawa_scan_field_borders(c, boxes, labels=labels, guides=guides)


def _draw_seino_simple(c, font: str, data: LabelPrintData) -> None:
    c.setFont(font, 14)
    c.drawString(40, 800, CARRIER_TITLES["seino"])
    info = data.recipient
    y = 760
    for line in [
        info.zip_code,
        info.address,
        info.name,
        _format_phone(info.phone),
        data.product_name,
    ]:
        if line:
            c.drawString(40, y, str(line)[:80])
            y -= 18


def _make_pdf(
    path: Path,
    data: LabelPrintData,
    carrier_key: str,
    *,
    preview_underlay: bool = False,
    debug_guides: bool = False,
    debug_borders: bool = False,
    debug_labels: bool = False,
    layout: SagawaLayout | None = None,
) -> None:
    if carrier_key == "sagawa":
        lay = layout or get_sagawa_layout()
        cfg, boxes = resolve_print_boxes(lay)
        pagesize = SAGAWA_PAGE_SIZE
        _log_page_size()
        _log_sagawa_print_data(data)
    else:
        pagesize = A4
        cfg = {}
        boxes = None

    c = canvas.Canvas(str(path), pagesize=pagesize)
    _set_no_print_scaling(c)
    font = _register_japanese_font()

    if carrier_key == "sagawa":
        assert boxes is not None
        debug_underlay = bool(cfg.get("DEBUG_UNDERLAY", False))
        debug_borders = debug_borders or bool(cfg.get("DEBUG_BORDERS", False))
        debug_labels = debug_labels or bool(cfg.get("DEBUG_LABELS", False))
        debug_guides = debug_guides or bool(cfg.get("DEBUG_GUIDES", False))
        if preview_underlay or debug_underlay or debug_borders or debug_labels or debug_guides:
            _set_preview_underlay(c, True)
            _draw_sagawa_preview_underlay(
                c,
                boxes,
                underlay=preview_underlay or debug_underlay,
                borders=debug_borders or preview_underlay,
                labels=debug_labels,
                guides=debug_guides,
            )
        _draw_sagawa_absolute(c, font, data, lay, cfg, boxes)
    elif carrier_key == "seino":
        _draw_seino_simple(c, font, data)
    else:
        raise ValueError(f"不明な carrier: {carrier_key}")

    c.save()


def _split_recipient_address_for_log(address: str) -> tuple[str, str]:
    lines = [ln.strip() for ln in re.split(r"[\r\n]+", address or "") if ln.strip()]
    if not lines:
        return "", ""
    if len(lines) == 1:
        return lines[0], ""
    return lines[0], " ".join(lines[1:])


def _log_sagawa_print_data(data: LabelPrintData) -> None:
    r = data.recipient
    s = data.sender
    addr, building = _split_recipient_address_for_log(r.address)
    print("=== SAGAWA PRINT DATA ===")
    print(f"recipient_name={r.name}")
    print(f"recipient_zip={r.zip_code}")
    print(f"recipient_address={addr}")
    print(f"recipient_building={building}")
    print(f"recipient_phone={r.phone}")
    print(f"sender_name={s.name}")
    print(f"sender_zip={s.zip_code}")
    print(f"sender_address={s.address}")
    print(f"sender_phone={s.phone}")
    print(f"item_name={data.product_name}")
    print(f"item_id={data.auction_id}")
    print(f"insurance_amount={data.insurance_amount}")
    print("=========================")


def default_preview_label_data() -> LabelPrintData:
    return LabelPrintData(
        recipient=ShippingInfo(
            name="山田太郎",
            zip_code="8891403",
            address="宮崎県児湯郡新富町上富田7478-3 切通宿舎D棟108号",
            phone="080-3943-1932",
        ),
        auction_id="sample123456",
        product_name="テスト商品名",
        quantity=1,
        sender=SenderInfo(
            zip_code="5580053",
            address="大阪府大阪市住吉区帝塚山東3-16-14",
            name="出品者名",
            phone="06-0000-0000",
        ),
        print_sender=True,
        insurance_enabled=True,
        insurance_amount=50000,
    )


def _verify_sagawa_preview_pdf(path: Path, *, expect_name: str = "山田太郎") -> None:
    try:
        import fitz
    except ImportError:
        return

    doc = fitz.open(path)
    try:
        page = doc[0]
        rot = int(page.rotation or 0) % 360
        if rot != 0:
            raise RuntimeError(f"プレビューPDFが {rot}° 回転しています")
        h = float(page.rect.height)
        name_y: float | None = None
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if expect_name in span.get("text", ""):
                        name_y = float(span["origin"][1])
                        break
        # fitz のテキスト座標は左上原点（Y↓）。氏名は用紙上半分（y < 約45%）にある想定
        if name_y is not None and name_y > h * 0.55:
            raise RuntimeError(
                f"プレビューが上下逆の可能性があります（氏名Y={name_y:.0f}, 高さ={h:.0f}）"
            )
    finally:
        doc.close()


def write_sagawa_layout_preview_pdf(
    path: Path,
    layout: SagawaLayout,
    data: LabelPrintData | None = None,
) -> Path:
    if path.name != "sagawa_preview_layout_latest.pdf":
        path = path.with_name("sagawa_preview_layout_latest.pdf")
    path.parent.mkdir(parents=True, exist_ok=True)
    d = data or default_preview_label_data()
    _make_pdf(path, d, "sagawa", preview_underlay=True, layout=layout)
    rname = (d.recipient.name or "山田太郎").strip()
    _verify_sagawa_preview_pdf(
        path, expect_name=rname[:2] if len(rname) >= 2 else rname
    )
    _log_print_job(
        mode=PRINT_MODE_PREVIEW_LAYOUT,
        output_pdf=path.resolve(),
        printer="",
        auto_print=False,
        result="PDF生成のみ・印刷禁止",
    )
    return path


def write_sagawa_overlay_debug_png(
    path: Path,
    data: LabelPrintData | None = None,
    layout: SagawaLayout | None = None,
) -> Path:
    """スキャン画像に印字位置・枠・項目名・ガイド線を重ねたPNGを出力する。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lay = layout or get_sagawa_layout()
    d = data or default_preview_label_data()
    pdf_path = path.with_suffix(".overlay_debug.pdf")
    _make_pdf(
        pdf_path,
        d,
        "sagawa",
        preview_underlay=True,
        debug_guides=True,
        debug_borders=True,
        debug_labels=True,
        layout=lay,
    )
    try:
        import fitz
    except ImportError:
        return pdf_path
    doc = fitz.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        pix.save(path)
    finally:
        doc.close()
    return path


def write_sagawa_real_overlay_pdf(
    path: Path | None,
    data: LabelPrintData,
    layout: SagawaLayout | None = None,
) -> Path:
    from excel_writer import _output_dir

    out_path = path or (_output_dir() / "sagawa_real_overlay_latest.pdf")
    if out_path.name != "sagawa_real_overlay_latest.pdf":
        out_path = out_path.with_name("sagawa_real_overlay_latest.pdf")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _make_pdf(
        out_path,
        data,
        "sagawa",
        preview_underlay=False,
        debug_guides=False,
        debug_borders=False,
        debug_labels=False,
        layout=layout or get_sagawa_layout(),
    )
    _log_print_job(
        mode=PRINT_MODE_REAL_SAGAWA_OVERLAY,
        output_pdf=out_path.resolve(),
        printer="",
        auto_print=False,
        result="real overlay PDF生成",
    )
    return out_path.resolve()


def write_print_scale_test_pdf(path: Path | None = None) -> Path:
    """100%印刷の実寸確認用PDFを作る。ページサイズは佐川伝票実寸。"""
    if path is None:
        from excel_writer import _output_dir

        path = _output_dir() / "print_scale_test.pdf"
    path.parent.mkdir(parents=True, exist_ok=True)
    _log_page_size()
    c = canvas.Canvas(str(path), pagesize=SAGAWA_PAGE_SIZE)
    _set_no_print_scaling(c)
    font = _register_japanese_font()

    w, h = SAGAWA_PAGE_SIZE
    c.setLineWidth(0.3)
    c.setStrokeColorRGB(0.75, 0.75, 0.75)
    x = 0.0
    while x <= w + 0.01:
        c.line(x, 0, x, h)
        x += mm_to_pt(10)
    y = 0.0
    while y <= h + 0.01:
        c.line(0, y, w, y)
        y += mm_to_pt(10)

    c.setStrokeColorRGB(0, 0, 0)
    c.setLineWidth(1.2)
    margin = mm_to_pt(10)
    mark = mm_to_pt(6)
    for x0, y0, sx, sy in (
        (0, 0, 1, 1),
        (w, 0, -1, 1),
        (0, h, 1, -1),
        (w, h, -1, -1),
    ):
        c.line(x0, y0, x0 + sx * mark, y0)
        c.line(x0, y0, x0, y0 + sy * mark)

    c.setLineWidth(2.0)
    base_x = margin
    base_y = h - mm_to_pt(35)
    c.line(base_x, base_y, base_x + mm_to_pt(100), base_y)
    c.line(base_x, base_y - mm_to_pt(5), base_x, base_y + mm_to_pt(5))
    c.line(base_x + mm_to_pt(100), base_y - mm_to_pt(5), base_x + mm_to_pt(100), base_y + mm_to_pt(5))

    vx = margin
    vy = h - mm_to_pt(55)
    c.line(vx, vy, vx, vy - mm_to_pt(50))
    c.line(vx - mm_to_pt(5), vy, vx + mm_to_pt(5), vy)
    c.line(vx - mm_to_pt(5), vy - mm_to_pt(50), vx + mm_to_pt(5), vy - mm_to_pt(50))

    c.setFont(font, 9)
    c.drawString(base_x, base_y + mm_to_pt(4), "100mm")
    c.drawString(vx + mm_to_pt(4), vy - mm_to_pt(25), "50mm")
    c.setFont(font, 8)
    c.drawString(margin, margin + mm_to_pt(18), "印刷設定: 実際のサイズ / 100%")
    c.drawString(margin, margin + mm_to_pt(12), "禁止: ページに合わせる / 用紙に合わせる / 余白付き印刷")
    c.drawString(margin, margin + mm_to_pt(6), f"PAGE {SAGAWA_PAGE_WIDTH_MM:g}mm x {SAGAWA_PAGE_HEIGHT_MM:g}mm")
    c.save()
    print(f"print_scale_test.pdf出力パス: {path.resolve()}")
    return path.resolve()


def export_shipping_label_pdfs(data: LabelPrintData, carriers: list[str]) -> dict[str, str]:
    """本番印刷用PDFを output に生成する。Excelは確認用なので印刷には使わない。"""
    if not carriers:
        raise ValueError("送付状の種類を選んでください。")
    from excel_writer import _output_dir

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out: dict[str, str] = {}
    for carrier_key in carriers:
        pdf_path = _output_dir() / f"print_{carrier_key}_{ts}.pdf"
        _make_pdf(pdf_path, data, carrier_key)
        if not pdf_path.is_file() or pdf_path.stat().st_size <= 0:
            raise FileNotFoundError(f"PDF出力ファイルが見つかりません: {pdf_path}")
        out[carrier_key] = str(pdf_path.resolve())
    return out


def print_shipping_labels(data: LabelPrintData, carriers: list[str]) -> str | None:
    if not carriers:
        raise ValueError("送付状の種類を選んでください。")
    tmpdir = Path(tempfile.mkdtemp(prefix="yafuoku_print_"))
    fix_msg: str | None = None
    for carrier_key in carriers:
        pdf_path = tmpdir / f"label_{carrier_key}.pdf"
        _make_pdf(pdf_path, data, carrier_key)
        from print_support import get_default_printer_name, open_print_dialog, save_print_copy

        saved = save_print_copy(pdf_path, carrier_key)
        if not saved.is_file():
            raise FileNotFoundError(f"PDF出力ファイルが見つかりません: {saved}")
        lower_name = saved.name.lower()
        if any(part in lower_name for part in FORBIDDEN_PRINT_NAME_PARTS):
            raise RuntimeError(f"確認用PDFは印刷できません: {saved.name}")
        printer = get_default_printer_name() or "(default printer not found)"
        _log_print_job(
            mode=PRINT_MODE_REAL_SAGAWA_OVERLAY,
            output_pdf=saved.resolve(),
            printer=printer,
            auto_print=False,
            result="印刷ダイアログを開く",
        )
        msg = open_print_dialog(saved)
        if msg:
            fix_msg = msg
            _log_print_job(
                mode=PRINT_MODE_REAL_SAGAWA_OVERLAY,
                output_pdf=saved.resolve(),
                printer=printer,
                auto_print=False,
                result=f"警告: {msg}",
            )
        else:
            _log_print_job(
                mode=PRINT_MODE_REAL_SAGAWA_OVERLAY,
                output_pdf=saved.resolve(),
                printer=printer,
                auto_print=False,
                result="印刷ダイアログ起動済み",
            )
        time.sleep(0.3)
    return fix_msg
