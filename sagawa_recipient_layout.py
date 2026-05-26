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

    def guide_rects(self) -> list[tuple[str, AbsBox]]:
        out: list[tuple[str, AbsBox]] = []
        for i, b in enumerate(self.zip_cells):
            out.append((f"宛先郵便番号{i + 1}", b))
        for i, b in enumerate(self.address_lines):
            out.append((f"宛先住所{i + 1}", b))
        out.append(("宛先会社名", self.company))
        out.append(("宛先氏名", self.name))
        out.append(("宛先電話番号", self.phone))
        return out


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
