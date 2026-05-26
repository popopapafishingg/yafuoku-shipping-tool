# -*- coding: utf-8 -*-
"""佐川: 欄幾何の解決（赤枠＝描画＝伝票入力欄）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from label_layout import SagawaLayout
from sagawa_fields import AbsBox
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
)


@dataclass(frozen=True)
class SagawaPrintBoxes:
    """印刷プレビュー用の欄矩形（お届け先は DestInputFields に集約）。"""

    dest: DestInputFields
    sender_zip: tuple[AbsBox, ...]
    sender_addr: tuple[AbsBox, ...]
    sender_name: AbsBox
    sender_phone: AbsBox
    item_id: AbsBox
    item_lines: tuple[AbsBox, ...]


def build_dest_input_fields(layout: SagawaLayout, cfg: dict[str, Any]) -> DestInputFields:
    f = layout.fields
    raw_zip = shifted_boxes(
        cfg, cfg_cells(cfg, "DEST_ZIP_CELLS", f.to_zip_cells), "DEST"
    )
    zip_cells = normalize_zip_row_cells(raw_zip)
    address_lines = shifted_boxes(
        cfg, cfg_line_boxes(cfg, "DEST_ADDRESS_LINES", f.to_addr_lines), "DEST"
    )
    company = shifted_box(cfg, cfg_box(cfg, "DEST_COMPANY", f.to_company), "DEST")
    name = shifted_box(cfg, cfg_box(cfg, "DEST_NAME", f.to_name), "DEST")
    phone = shifted_box(cfg, cfg_box(cfg, "DEST_PHONE", f.to_phone), "DEST")
    return DestInputFields(
        zip_cells=zip_cells,
        address_lines=address_lines,
        company=company,
        name=name,
        phone=phone,
    )


def resolve_print_boxes(
    layout: SagawaLayout,
    cfg: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], SagawaPrintBoxes]:
    if cfg is None:
        cfg = load_print_config(layout)
    f = layout.fields
    dest = build_dest_input_fields(layout, cfg)
    boxes = SagawaPrintBoxes(
        dest=dest,
        sender_zip=shifted_boxes(
            cfg, cfg_cells(cfg, "SENDER_ZIP_CELLS", f.from_zip_cells), "SENDER"
        ),
        sender_addr=shifted_boxes(
            cfg,
            cfg_line_boxes(cfg, "SENDER_ADDRESS_LINES", f.from_addr_lines),
            "SENDER",
        ),
        sender_name=shifted_box(cfg, cfg_box(cfg, "SENDER_NAME", f.from_name), "SENDER"),
        sender_phone=shifted_box(
            cfg, cfg_box(cfg, "SENDER_PHONE", f.from_phone), "SENDER"
        ),
        item_id=shifted_box(cfg, cfg_box(cfg, "ITEM_ID", f.item_auction), "ITEM"),
        item_lines=shifted_boxes(
            cfg, cfg_line_boxes(cfg, "ITEM_NAME_LINES", f.item_lines[:2]), "ITEM"
        ),
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
    out.append(("オークションID", boxes.item_id))
    for i, b in enumerate(boxes.item_lines):
        out.append((f"商品名{i + 1}", b))
    return out
