# -*- coding: utf-8 -*-
"""sagawa_form_scan.pdf から印刷座標を自動推定（届け先=上段・依頼主=下段）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import fitz
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sagawa_page import SAGAWA_PAGE_H, SAGAWA_PAGE_W, sagawa_scan_pdf_path

SCALE = 4.0
LINE_H = 11.5


def px_to_pt(x: float, y: float, iw: int, ih: int) -> tuple[float, float]:
    return x / iw * SAGAWA_PAGE_W, (1.0 - y / ih) * SAGAWA_PAGE_H


def load_scan() -> tuple[np.ndarray, int, int]:
    p = sagawa_scan_pdf_path()
    if not p:
        raise FileNotFoundError("sagawa_form_scan.pdf がありません")
    doc = fitz.open(p)
    page = doc[0]
    sx = SCALE * SAGAWA_PAGE_W / page.rect.width
    sy = SCALE * SAGAWA_PAGE_H / page.rect.height
    pix = page.get_pixmap(matrix=fitz.Matrix(sx, sy), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    doc.close()
    return img, pix.width, pix.height


def form_bbox(img: np.ndarray) -> tuple[int, int, int, int, float, float]:
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (90, 25, 70), (140, 255, 255))
    pts = cv2.findNonZero(mask)
    if pts is None:
        raise RuntimeError("フォーム色が検出できません")
    x0, y0, fw, fh = cv2.boundingRect(pts)
    ih, iw = img.shape[:2]
    top_pt = (1.0 - y0 / ih) * SAGAWA_PAGE_H
    bot_pt = (1.0 - (y0 + fh) / ih) * SAGAWA_PAGE_H
    return x0, y0, fw, fh, top_pt, bot_pt


def find_zip_rows(img: np.ndarray, form: tuple[int, int, int, int]) -> list[dict]:
    x0, y0, fw, fh = form
    ih, iw = img.shape[:2]
    roi = img[y0 : y0 + fh, x0 : x0 + fw]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    inv = 255 - bw
    cnts, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[float, float]] = []
    for c in cnts:
        bx, by, bw2, bh2 = cv2.boundingRect(c)
        if not (10 <= bw2 <= 60 and 10 <= bh2 <= 60):
            continue
        ar = bw2 / float(bh2)
        if not (0.6 <= ar <= 1.5) or not (150 <= bw2 * bh2 <= 4000):
            continue
        cx = x0 + bx + bw2 / 2.0
        cy = y0 + by + bh2 / 2.0
        boxes.append(px_to_pt(cx, cy, iw, ih))

    rows: list[list[tuple[float, float]]] = []
    for xpt, ypt in boxes:
        for row in rows:
            if abs(row[0][1] - ypt) < 55:
                row.append((xpt, ypt))
                break
        else:
            rows.append([(xpt, ypt)])

    out: list[dict] = []
    for row in rows:
        if len(row) < 6:
            continue
        row.sort(key=lambda p: p[0])
        if len(row) > 7:
            best = row[:7]
            best_score = 1e9
            for i in range(len(row) - 6):
                run = row[i : i + 7]
                gaps = [run[j + 1][0] - run[j][0] for j in range(6)]
                score = max(gaps) - min(gaps)
                if score < best_score:
                    best_score = score
                    best = run
            row = best
        xs = [round(p[0], 1) for p in row[:7]]
        ys = [p[1] for p in row[:7]]
        out.append({"xs": xs, "y": round(sum(ys) / len(ys), 1), "x0": float(xs[0])})
    out.sort(key=lambda r: r["y"], reverse=True)
    return out


def _zip_row_spread(row: dict) -> float:
    xs = [float(x) for x in row.get("xs", [])[:7]]
    return max(xs) - min(xs) if xs else 0.0


def _is_good_zip_row(row: dict) -> bool:
    return len(row.get("xs", [])) >= 7 and _zip_row_spread(row) >= 24.0


def _recipient_zip_row_from_panel(
    panel: tuple[float, float, float, float],
) -> dict:
    """お届け先パネル左上の青い7マス（印字333-0831ではなくその上）。"""
    x, y, w, h = panel
    top = y + h
    zip_y = round(top + 10.0, 1)
    x0 = round(x + 48.0, 1)
    pitch = 15.2
    gap = 11.0
    xs = [round(x0 + pitch * i, 1) for i in range(3)]
    xs += [round(xs[2] + gap + pitch * i, 1) for i in range(1, 5)]
    return {"xs": xs, "y": zip_y, "x0": xs[0]}


def _sender_zip_row_from_panel(
    panel: tuple[float, float, float, float],
) -> dict:
    """ご依頼主欄・左の〒7マス（右端の印字333-0831とは別）。"""
    x, y, _w, h = panel
    zip_y = round(y + h * 0.72, 1)
    x0 = round(x + 12.0, 1)
    pitch = 15.2
    gap = 11.0
    xs = [round(x0 + pitch * i, 1) for i in range(3)]
    xs += [round(xs[2] + gap + pitch * i, 1) for i in range(1, 5)]
    return {"xs": xs, "y": zip_y, "x0": xs[0]}


def pick_recipient_sender(
    rows: list[dict],
    snd_panel: tuple[float, float, float, float] | None = None,
) -> tuple[dict, dict]:
    good = [r for r in rows if _is_good_zip_row(r)]
    good.sort(key=lambda r: r["y"], reverse=True)
    recipient = good[0] if good else max(rows, key=lambda r: r["y"])

    snd_rows = [
        r
        for r in rows
        if recipient["y"] - 220 < r["y"] < recipient["y"] - 120
        and _zip_row_spread(r) >= 18.0
    ]
    if snd_rows:
        sender = max(snd_rows, key=lambda r: r["y"])
    elif snd_panel is not None:
        sender = _sender_zip_row_from_panel(snd_panel)
    elif len(good) >= 2:
        sender = good[-1]
    else:
        sender = min(rows, key=lambda r: r["y"])
    return recipient, sender


def _px_rect_to_pt(
    x: float, y: float, w: float, h: float, iw: int, ih: int
) -> tuple[float, float, float, float]:
    x_pt = x / iw * SAGAWA_PAGE_W
    w_pt = w / iw * SAGAWA_PAGE_W
    y_pt = (1.0 - (y + h) / ih) * SAGAWA_PAGE_H
    h_pt = h / ih * SAGAWA_PAGE_H
    return x_pt, y_pt, w_pt, h_pt


def _synthesize_zip_cells_pt(
    row: dict,
    *,
    cell_w: float = 15.0,
    cell_h: float = 12.0,
    gap_after_3: float = 11.0,
) -> list[tuple[float, float, float, float]]:
    xs = [float(x) for x in row["xs"][:7]]
    spread = _zip_row_spread(row)
    if spread < 24.0:
        pitch = 15.2
        x0 = float(row.get("x0", xs[0] if xs else 400.0))
        if spread < 8.0:
            x0 = x0 - pitch * 3.0
        xs = [x0 + pitch * i for i in range(3)]
        xs += [xs[2] + gap_after_3 + pitch * i for i in range(1, 5)]
    y = float(row["y"])
    y_bot = round(y - cell_h * 0.48, 1)
    out: list[tuple[float, float, float, float]] = []
    for cx in xs[:7]:
        out.append((round(cx - cell_w / 2.0, 1), y_bot, cell_w, cell_h))
    return out


def _zip_row_cell_rects_pt(
    img: np.ndarray,
    iw: int,
    ih: int,
    form: tuple[int, int, int, int],
    row: dict,
) -> list[tuple[float, float, float, float]]:
    row_y = float(row["y"])
    xs = [float(x) for x in row["xs"][:7]]
    x_min, x_max = min(xs) - 14.0, max(xs) + 14.0
    x0, y0, fw, fh = form
    roi = img[y0 : y0 + fh, x0 : x0 + fw]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    inv = 255 - bw
    cnts, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    raw: list[tuple[float, float, float, float]] = []
    for c in cnts:
        bx, by, bw2, bh2 = cv2.boundingRect(c)
        if not (10 <= bw2 <= 60 and 10 <= bh2 <= 60):
            continue
        ar = bw2 / float(bh2)
        if not (0.6 <= ar <= 1.5):
            continue
        cx = x0 + bx + bw2 / 2.0
        cy = y0 + by + bh2 / 2.0
        _, ypt = px_to_pt(cx, cy, iw, ih)
        if abs(ypt - row_y) > 40:
            continue
        raw.append(_px_rect_to_pt(x0 + bx, y0 + by, bw2, bh2, iw, ih))
    matched: list[tuple[float, float, float, float]] = []
    used: set[int] = set()
    for tx in xs:
        best_i = -1
        best_dx = 1e9
        for i, (x, y, w, h) in enumerate(raw):
            if i in used:
                continue
            cx = x + w / 2.0
            if cx < x_min or cx > x_max:
                continue
            dx = abs(cx - tx)
            if dx < best_dx and dx <= 20:
                best_dx = dx
                best_i = i
        if best_i >= 0:
            used.add(best_i)
            matched.append(raw[best_i])
    matched.sort(key=lambda r: r[0])
    if len(matched) >= 7:
        good = [r for r in matched[:7] if r[2] >= 10.0 and r[3] >= 10.0]
        if len(good) >= 7:
            ys = [r[1] + r[3] * 0.5 for r in good]
            xs_c = [r[0] + r[2] * 0.5 for r in good]
            if max(ys) - min(ys) <= 6.0 and max(xs_c) - min(xs_c) >= 70.0:
                return good[:7]
    return _synthesize_zip_cells_pt(row)


def _panel_top(rect: tuple[float, float, float, float]) -> float:
    return rect[1] + rect[3]


def _scan_white_rects(
    img: np.ndarray, iw: int, ih: int, form: tuple[int, int, int, int]
) -> list[tuple[float, float, float, float]]:
    x0, y0, fw, fh = form
    roi = img[y0 : y0 + fh, x0 : x0 + fw]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 235, 255, cv2.THRESH_BINARY)
    cnts, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    form_area = float(fw * fh)
    out: list[tuple[float, float, float, float, float]] = []
    for c in cnts:
        bx, by, bw2, bh2 = cv2.boundingRect(c)
        area = float(bw2 * bh2)
        if area < 8000 or bw2 < 40 or bh2 < 12:
            continue
        if area > form_area * 0.45:
            continue
        rect = _px_rect_to_pt(x0 + bx, y0 + by, bw2, bh2, iw, ih)
        out.append((*rect, area))
    return [r[:4] for r in out]


def _pick_left_panels(
    rects: list[tuple[float, float, float, float]],
) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    panels = [
        r
        for r in rects
        if r[0] < 130
        and 120 <= r[2] <= 230
        and 55 <= r[3] <= 140
        and r[1] > 80
    ]
    if len(panels) < 2:
        raise RuntimeError("お届け先/ご依頼主の白枠を検出できません")
    recv_panel = max(panels, key=lambda r: r[1])
    snd_panel = min(panels, key=lambda r: r[1])
    return recv_panel, snd_panel


def _line_box(panel: tuple[float, float, float, float], y_center: float) -> tuple[float, float, float, float]:
    x, _y, w, _h = panel
    return (round(x + 2, 1), round(y_center - LINE_H / 2, 1), round(w - 4, 1), LINE_H)


def _recv_text_boxes(panel: tuple[float, float, float, float]) -> dict:
    """お届け先: 白枠内の住所3・名前・電話（郵便7マスは別行）。"""
    _x, y, _w, h = panel
    top = y + h
    return {
        "addr": (
            _line_box(panel, top - 56),
            _line_box(panel, top - 68),
            _line_box(panel, top - 80),
        ),
        "company": _line_box(panel, top - 88),
        "name": _line_box(panel, top - 101),
        "phone": _shift_box(_line_box(panel, top - 115), dx=20.0),
    }


def _shift_box(
    box: tuple[float, float, float, float], *, dx: float = 0.0, dy: float = 0.0
) -> tuple[float, float, float, float]:
    x, y, w, h = box
    return (round(x + dx, 1), round(y + dy, 1), w, h)


def _snd_text_boxes(panel: tuple[float, float, float, float]) -> dict:
    """ご依頼主: 白枠内の住所3・名前・電話。"""
    _x, y, _w, h = panel
    top = y + h
    return {
        "addr": (
            _line_box(panel, top - 46),
            _line_box(panel, top - 58),
            _line_box(panel, top - 70),
        ),
        "name": _line_box(panel, top - 88),
        "phone": _shift_box(_line_box(panel, top - 102), dx=16.0),
    }


def _quantity_box_pt(img: np.ndarray, iw: int, ih: int) -> tuple[float, float, float, float]:
    """送り状番号 1860-… の直左の個数マス。"""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, bw = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    inv = 255 - bw
    cnts, _ = cv2.findContours(inv, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best: tuple[float, float, float, float, float] | None = None
    for c in cnts:
        bx, by, bw2, bh2 = cv2.boundingRect(c)
        if not (18 <= bw2 <= 36 and 18 <= bh2 <= 36):
            continue
        rect = _px_rect_to_pt(bx, by, bw2, bh2, iw, ih)
        x, y, w, h = rect
        cy = y + h * 0.5
        if not (288 <= x <= 318 and 798 <= cy <= 808):
            continue
        score = -(x - 302) ** 2 - (cy - 803) ** 2
        if best is None or score > best[4]:
            best = (*rect, score)
    if best and best[2] >= 18.0 and best[3] >= 18.0:
        return best[:4]
    return (272.0, 799.0, 30.0, 26.0)


def _insurance_rects_pt(
    recv_panel: tuple[float, float, float, float],
    snd_panel: tuple[float, float, float, float],
) -> list[tuple[float, float, float, float]]:
    recv_bot = recv_panel[1]
    snd_top = snd_panel[1] + snd_panel[3]
    y = round((recv_bot + snd_top) * 0.5 - 6.0, 1)
    return [
        (336.0, y + 1.0, 16.0, 16.0),
        (430.0, y + 2.0, 86.0, 17.0),
    ]


def _analyze_scan_layout(img: np.ndarray, iw: int, ih: int) -> dict:
    form = form_bbox(img)
    form4 = form[:4]
    rows = find_zip_rows(img, form4)
    if len(rows) < 2:
        raise RuntimeError("郵便マス行が不足")
    recv_panel, snd_panel = _pick_left_panels(_scan_white_rects(img, iw, ih, form4))
    recipient = _recipient_zip_row_from_panel(recv_panel)
    sender = _sender_zip_row_from_panel(snd_panel)
    recv_cells = _zip_row_cell_rects_pt(img, iw, ih, form4, recipient)
    snd_cells = _zip_row_cell_rects_pt(img, iw, ih, form4, sender)
    recv_text = _recv_text_boxes(recv_panel)
    snd_text = _snd_text_boxes(snd_panel)
    rp_x, _rp_y, rp_w, _rp_h = recv_panel
    item_x = round(rp_x + rp_w + 12.0, 1)
    item_top = round(_panel_top(recv_panel) - 32.0, 1)
    qty = _quantity_box_pt(img, iw, ih)
    ins_rects = _insurance_rects_pt(recv_panel, snd_panel)

    return {
        "form4": form4,
        "recipient": recipient,
        "sender": sender,
        "recv_panel": recv_panel,
        "snd_panel": snd_panel,
        "recv_cells": recv_cells,
        "snd_cells": snd_cells,
        "recv_text": recv_text,
        "snd_text": snd_text,
        "qty": qty,
        "ins_rects": ins_rects,
        "item_x": item_x,
        "item_top_y": item_top,
        "item_w": 168.0,
    }


def calibrate() -> dict:
    from sagawa_fields import build_fields_from_scan, fields_to_calibration_dict

    fields = build_fields_from_scan()
    cal = fields_to_calibration_dict(fields)
    cal["zip_digit_x"] = list(cal["zip_digit_x"])
    cal["sender_zip_digit_x"] = list(cal["sender_zip_digit_x"])
    cal["to_addr_y"] = list(cal["to_addr_y"])
    cal["from_addr_y"] = list(cal["from_addr_y"])
    cal["item_line_y"] = list(cal["item_line_y"])
    return cal


def main() -> int:
    cal = calibrate()
    out = ROOT / "templates" / "sagawa_calibration.json"
    save = {**cal, "rotation": "raw"}
    out.write_text(json.dumps(save, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(cal, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
