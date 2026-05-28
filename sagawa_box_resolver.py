# -*- coding: utf-8 -*-
"""佐川: 欄幾何の解決（赤枠＝描画＝伝票入力欄）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from label_layout import SagawaLayout
from sagawa_fields import AbsBox
from sagawa_layout_offsets import (
    apply_address_lines,
    apply_group_offset,
    apply_item_boxes,
    apply_zip_cells,
    load_layout_offsets,
)
from sagawa_print_config import (
    cfg_box,
    cfg_cells,
    cfg_line_boxes,
    load_print_config,
    shifted_box,
    shifted_boxes,
)
from sagawa_recipient_layout import (
    DestInputFields,
    normalize_zip_row_cells,
    phone_cells_from_box,
)


@dataclass(frozen=True)
class SagawaPrintBoxes:
    """印刷プレビュー用の欄矩形（お届け先は DestInputFields に集約）。"""

    dest: DestInputFields
    sender_zip: tuple[AbsBox, ...]
    sender_addr: tuple[AbsBox, ...]
    sender_name: AbsBox
    sender_phone: AbsBox
    sender_phone_cells: tuple[AbsBox, ...]
    item_id: AbsBox
    item_lines: tuple[AbsBox, ...]


def _phone_slots(offsets: dict[str, Any], group: str) -> int:
    sec = offsets.get(group, {})
    if isinstance(sec, dict):
        try:
            return max(1, int(sec.get("phone_slot_count", 13)))
        except (TypeError, ValueError):
            pass
    return 13


def build_dest_input_fields(
    layout: SagawaLayout,
    cfg: dict[str, Any],
    offsets: dict[str, Any],
) -> DestInputFields:
    f = layout.fields
    raw_zip = shifted_boxes(
        cfg, cfg_cells(cfg, "DEST_ZIP_CELLS", f.to_zip_cells), "DEST"
    )
    zip_cells = normalize_zip_row_cells(apply_zip_cells(raw_zip, offsets, "dest"))
    address_lines = apply_address_lines(
        shifted_boxes(
            cfg, cfg_line_boxes(cfg, "DEST_ADDRESS_LINES", f.to_addr_lines), "DEST"
        ),
        offsets,
        "dest",
    )
    company = apply_group_offset(
        shifted_box(cfg, cfg_box(cfg, "DEST_COMPANY", f.to_company), "DEST"),
        offsets,
        "dest",
    )
    name = apply_group_offset(
        shifted_box(cfg, cfg_box(cfg, "DEST_NAME", f.to_name), "DEST"),
        offsets,
        "dest",
    )
    phone = apply_group_offset(
        shifted_box(cfg, cfg_box(cfg, "DEST_PHONE", f.to_phone), "DEST"),
        offsets,
        "dest",
    )
    phone_cells = phone_cells_from_box(phone, _phone_slots(offsets, "dest"))
    return DestInputFields(
        zip_cells=zip_cells,
        address_lines=address_lines,
        company=company,
        name=name,
        phone=phone,
        phone_cells=phone_cells,
    )


def resolve_print_boxes(
    layout: SagawaLayout,
    cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], SagawaPrintBoxes]:
    if cfg is None:
        cfg = load_print_config(layout)
    offsets = load_layout_offsets()
    f = layout.fields
    dest = build_dest_input_fields(layout, cfg, offsets)

    sender_zip_raw = shifted_boxes(
        cfg, cfg_cells(cfg, "SENDER_ZIP_CELLS", f.from_zip_cells), "SENDER"
    )
    sender_zip = normalize_zip_row_cells(apply_zip_cells(sender_zip_raw, offsets, "sender"))

    sender_addr = apply_address_lines(
        shifted_boxes(
            cfg,
            cfg_line_boxes(cfg, "SENDER_ADDRESS_LINES", f.from_addr_lines),
            "SENDER",
        ),
        offsets,
        "sender",
    )
    sender_name = apply_group_offset(
        shifted_box(cfg, cfg_box(cfg, "SENDER_NAME", f.from_name), "SENDER"),
        offsets,
        "sender",
    )
    sender_phone = apply_group_offset(
        shifted_box(cfg, cfg_box(cfg, "SENDER_PHONE", f.from_phone), "SENDER"),
        offsets,
        "sender",
    )
    sender_phone_cells = phone_cells_from_box(sender_phone, _phone_slots(offsets, "sender"))

    item_id_raw = shifted_box(cfg, cfg_box(cfg, "ITEM_ID", f.item_auction), "ITEM")
    item_lines_raw = shifted_boxes(
        cfg, cfg_line_boxes(cfg, "ITEM_NAME_LINES", f.item_lines[:2]), "ITEM"
    )
    item_id, item_lines = apply_item_boxes(item_id_raw, item_lines_raw, offsets)

    boxes = SagawaPrintBoxes(
        dest=dest,
        sender_zip=sender_zip,
        sender_addr=sender_addr,
        sender_name=sender_name,
        sender_phone=sender_phone,
        sender_phone_cells=sender_phone_cells,
        item_id=item_id,
        item_lines=item_lines,
    )
    return cfg, boxes


def iter_input_guide_rects(boxes: SagawaPrintBoxes) -> list[tuple[str, AbsBox]]:
    out = list(boxes.dest.guide_rects())
    for i, b in enumerate(boxes.sender_zip):
        out.append((f"依頼主郵便番号{i + 1}", b))
    for i, b in enumerate(boxes.sender_addr):
        out.append((f"依頼主住所{i + 1}", b))
    out.append(("依頼主名", boxes.sender_name))
    out.append(("依頼主電話番号", boxes.sender_phone))
    for i, b in enumerate(boxes.sender_phone_cells):
        out.append((f"依頼主TELマス{i + 1}", b))
    out.append(("オークションID", boxes.item_id))
    for i, b in enumerate(boxes.item_lines):
        out.append((f"商品名{i + 1}", b))
    return out
