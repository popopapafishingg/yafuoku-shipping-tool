# -*- coding: utf-8 -*-
"""佐川送り状の項目別固定枠（絶対座標）。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AbsBox:
    x: float
    y: float
    w: float
    h: float

    @property
    def top(self) -> float:
        return self.y + self.h

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)


@dataclass(frozen=True)
class SagawaFields:
    """プレビュー赤枠・印刷位置の基準（各項目独立）。"""

    to_zip_cells: tuple[AbsBox, ...]
    to_zip_group3: AbsBox
    to_zip_group4: AbsBox
    to_addr_lines: tuple[AbsBox, ...]
    to_company: AbsBox
    to_name: AbsBox
    to_phone: AbsBox
    from_zip_cells: tuple[AbsBox, ...]
    from_zip_group3: AbsBox
    from_zip_group4: AbsBox
    from_addr_lines: tuple[AbsBox, ...]
    from_name: AbsBox
    from_phone: AbsBox
    quantity: AbsBox
    insurance_check: AbsBox
    insurance_amount: AbsBox
    item_auction: AbsBox
    item_lines: tuple[AbsBox, ...]

    def all_preview_rects(self) -> list[tuple[str, float, float, float, float]]:
        out: list[tuple[str, float, float, float, float]] = []
        for i, b in enumerate(self.to_zip_cells):
            out.append((f"届け先・郵便マス{i + 1}", *b.as_tuple()))
        for i, b in enumerate(self.to_addr_lines):
            out.append((f"届け先・住所{i + 1}行", *b.as_tuple()))
        out.append(("届け先・会社名", *self.to_company.as_tuple()))
        out.append(("届け先・宛名", *self.to_name.as_tuple()))
        out.append(("届け先・電話", *self.to_phone.as_tuple()))
        for i, b in enumerate(self.from_zip_cells):
            out.append((f"依頼主・郵便マス{i + 1}", *b.as_tuple()))
        for i, b in enumerate(self.from_addr_lines):
            out.append((f"依頼主・住所{i + 1}行", *b.as_tuple()))
        out.append(("依頼主・名前", *self.from_name.as_tuple()))
        out.append(("依頼主・電話", *self.from_phone.as_tuple()))
        out.append(("個数", *self.quantity.as_tuple()))
        out.append(("保険・チェック", *self.insurance_check.as_tuple()))
        out.append(("保険・金額", *self.insurance_amount.as_tuple()))
        out.append(("品名・オークションID", *self.item_auction.as_tuple()))
        for i, b in enumerate(self.item_lines):
            out.append((f"品名・本文{i + 1}行", *b.as_tuple()))
        return out


def _union_boxes(boxes: list[AbsBox], *, pad: float = 1.0) -> AbsBox:
    if not boxes:
        return AbsBox(0, 0, 1, 1)
    x0 = min(b.x for b in boxes) - pad
    y0 = min(b.y for b in boxes) - pad
    x1 = max(b.x + b.w for b in boxes) + pad
    y1 = max(b.y + b.h for b in boxes) + pad
    return AbsBox(x0, y0, x1 - x0, y1 - y0)


def _split_item_box(box: tuple[float, float, float, float]) -> tuple[AbsBox, tuple[AbsBox, ...]]:
    x, y, w, h = box
    h1 = h * 0.28
    hline = (h - h1) / 3.0
    auction = AbsBox(x, y + h - h1, w, h1)
    lines: list[AbsBox] = []
    for i in range(3):
        y_top = y + h - h1 - i * hline
        lines.append(AbsBox(x, y_top - hline, w, hline))
    return auction, tuple(lines)


def baseline_in_box(box: AbsBox, font_size: int) -> float:
    return round(box.y + box.h * 0.38 - font_size * 0.05, 1)


def zip_center_xs(cells: tuple[AbsBox, ...]) -> tuple[float, ...]:
    return tuple(round(b.x + b.w * 0.5, 1) for b in cells)


def zip_baseline_y(cells: tuple[AbsBox, ...], font_size: int) -> float:
    if not cells:
        return 0.0
    return baseline_in_box(cells[0], font_size)


def build_fields_from_scan() -> SagawaFields:
    from tools.auto_calibrate_sagawa import _analyze_scan_layout, load_scan

    img, iw, ih = load_scan()
    lay = _analyze_scan_layout(img, iw, ih)

    to_cells = tuple(AbsBox(*c) for c in lay["recv_cells"][:7])
    from_cells = tuple(AbsBox(*c) for c in lay["snd_cells"][:7])
    rt = lay["recv_text"]
    st = lay["snd_text"]
    to_addr = tuple(AbsBox(*t) for t in rt["addr"])
    to_name = AbsBox(*rt["name"])
    to_phone = AbsBox(*rt["phone"])
    to_company = AbsBox(*rt.get("company", rt["name"]))
    if "company" not in rt:
        from sagawa_recipient_layout import company_box_from_panel

        to_company = company_box_from_panel(to_addr, to_name)
    from_addr = tuple(AbsBox(*t) for t in st["addr"])
    from_name = AbsBox(*st["name"])
    from_phone = AbsBox(*st["phone"])

    qty = lay["qty"]
    quantity = AbsBox(*qty)
    ins = lay["ins_rects"]
    insurance_check = AbsBox(*ins[0])
    insurance_amount = AbsBox(*ins[1])

    item_x = lay["item_x"]
    item_top = lay["item_top_y"]
    item_w = float(lay.get("item_w", 168.0))
    item_box = (item_x, item_top - 68, item_w, 72.0)
    item_auction, item_lines = _split_item_box(item_box)

    return SagawaFields(
        to_zip_cells=to_cells,
        to_zip_group3=_union_boxes(list(to_cells[:3])),
        to_zip_group4=_union_boxes(list(to_cells[3:7])),
        to_addr_lines=to_addr,
        to_company=to_company,
        to_name=to_name,
        to_phone=to_phone,
        from_zip_cells=from_cells,
        from_zip_group3=_union_boxes(list(from_cells[:3])),
        from_zip_group4=_union_boxes(list(from_cells[3:7])),
        from_addr_lines=from_addr,
        from_name=from_name,
        from_phone=from_phone,
        quantity=quantity,
        insurance_check=insurance_check,
        insurance_amount=insurance_amount,
        item_auction=item_auction,
        item_lines=item_lines,
    )


def fields_to_calibration_dict(fields: SagawaFields) -> dict:
    to_zip_x = zip_center_xs(fields.to_zip_cells)
    from_zip_x = zip_center_xs(fields.from_zip_cells)
    return {
        "to_box": list(fields.to_addr_lines[0].as_tuple()),
        "from_box": list(fields.from_name.as_tuple()),
        "zip_digit_x": to_zip_x,
        "zip_digit_y": zip_baseline_y(fields.to_zip_cells, 7),
        "sender_zip_digit_x": from_zip_x,
        "sender_zip_y": zip_baseline_y(fields.from_zip_cells, 7),
        "to_x": round(fields.to_addr_lines[0].x + 3, 1),
        "to_addr_y": tuple(baseline_in_box(b, 11) for b in fields.to_addr_lines),
        "to_name_y": baseline_in_box(fields.to_name, 13),
        "to_phone_y": baseline_in_box(fields.to_phone, 9),
        "from_x": round(fields.from_addr_lines[0].x + 3, 1),
        "from_addr_y": tuple(baseline_in_box(b, 9) for b in fields.from_addr_lines),
        "from_name_y": baseline_in_box(fields.from_name, 9),
        "from_phone_y": baseline_in_box(fields.from_phone, 9),
        "quantity_x": round(fields.quantity.x + fields.quantity.w * 0.35, 1),
        "quantity_y": baseline_in_box(fields.quantity, 9),
        "item_box": list(_union_boxes([fields.item_auction, *fields.item_lines]).as_tuple()),
        "item_x": round(fields.item_auction.x + 2, 1),
        "item_auction_y": baseline_in_box(fields.item_auction, 8),
        "item_line_y": tuple(baseline_in_box(b, 8) for b in fields.item_lines),
        "insurance_check_x": fields.insurance_check.x + 2,
        "insurance_check_y": baseline_in_box(fields.insurance_check, 8),
        "insurance_amount_x": fields.insurance_amount.x + 2,
        "insurance_amount_y": baseline_in_box(fields.insurance_amount, 8),
        "left_x": round(fields.to_addr_lines[0].x + 3, 1),
        "addr_start_y": baseline_in_box(fields.to_addr_lines[0], 11),
        "sender_x": round(fields.from_addr_lines[0].x + 3, 1),
        "sender_zip_y_cap": zip_baseline_y(fields.from_zip_cells, 7),
        "right_x": round(fields.item_auction.x + 2, 1),
        "item_top_y": baseline_in_box(fields.item_auction, 8),
    }
