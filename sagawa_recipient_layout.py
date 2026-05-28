# -*- coding: utf-8 -*-
"""佐川お届け先入力欄の幾何定義（スキャン構造から欄を再現）。"""
from __future__ import annotations

from dataclasses import dataclass

from sagawa_fields import AbsBox

# 伝票お届け先ブロックの行構成（上から）
RECIPIENT_ADDRESS_LINE_COUNT = 3
RECIPIENT_ZIP_DIGIT_COUNT = 7


@dataclass(frozen=True)
class DestInputFields:
    """お届け先の各入力欄＝赤枠＝描画領域（同一矩形）。"""

    zip_cells: tuple[AbsBox, ...]
    address_lines: tuple[AbsBox, ...]
    company: AbsBox
    name: AbsBox
    phone: AbsBox
    phone_cells: tuple[AbsBox, ...] = ()

    def guide_rects(self) -> list[tuple[str, AbsBox]]:
        out: list[tuple[str, AbsBox]] = []
        for i, b in enumerate(self.zip_cells):
            out.append((f"宛先郵便番号{i + 1}", b))
        for i, b in enumerate(self.address_lines):
            out.append((f"宛先住所{i + 1}", b))
        out.append(("宛先会社名", self.company))
        out.append(("宛先氏名", self.name))
        out.append(("宛先電話番号", self.phone))
        for i, b in enumerate(self.phone_cells):
            out.append((f"宛先TELマス{i + 1}", b))
        return out


def phone_cells_from_box(phone_box: AbsBox, slot_count: int = 13) -> tuple[AbsBox, ...]:
    """
    電話欄を等幅スロットに分割（1文字ずつ各マス中央へ印字）。
    ハイフン含む最大 slot_count 文字を想定。
    """
    n = max(1, int(slot_count))
    pad_x = 3.0
    usable_w = max(1.0, phone_box.w - pad_x * 2.0)
    cell_w = usable_w / float(n)
    return tuple(
        AbsBox(
            round(phone_box.x + pad_x + i * cell_w, 2),
            phone_box.y,
            round(cell_w, 2),
            phone_box.h,
        )
        for i in range(n)
    )


def normalize_zip_row_cells(cells: tuple[AbsBox, ...]) -> tuple[AbsBox, ...]:
    """
    郵便7マス: 検出セルを横一列にそろえ、7等分のマス矩形を生成する。
    各マス内で1文字中央描画する前提の欄形状。
    """
    if len(cells) != RECIPIENT_ZIP_DIGIT_COUNT:
        return cells
    y0 = min(b.y for b in cells)
    h = max(b.h for b in cells)
    x_left = min(b.x for b in cells)
    x_right = max(b.x + b.w for b in cells)
    cell_w = round(sum(b.w for b in cells) / len(cells), 2)
    span = x_right - x_left
    gap = (span - cell_w * RECIPIENT_ZIP_DIGIT_COUNT) / (RECIPIENT_ZIP_DIGIT_COUNT - 1)
    out: list[AbsBox] = []
    for i in range(RECIPIENT_ZIP_DIGIT_COUNT):
        x = round(x_left + i * (cell_w + gap), 1)
        out.append(AbsBox(x, y0, cell_w, h))
    return tuple(out)


def company_box_from_panel(
    address_lines: tuple[AbsBox, ...],
    name_box: AbsBox,
) -> AbsBox:
    """住所3行目と氏名行の間に会社名欄を置く（伝票レイアウト）。"""
    if not address_lines:
        return name_box
    addr_bottom = address_lines[-1]
    gap_mid = (addr_bottom.y + name_box.top) * 0.5
    line_h = addr_bottom.h
    return AbsBox(
        addr_bottom.x,
        round(gap_mid - line_h / 2.0, 1),
        addr_bottom.w,
        line_h,
    )
