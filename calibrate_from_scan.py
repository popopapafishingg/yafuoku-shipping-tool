# -*- coding: utf-8 -*-
"""CCF20260521.pdf スキャンから佐川レイアウト座標を推定（開発用）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import fitz
import numpy as np

SCAN_PDF = Path(r"c:\Users\b-s\Downloads\CCF20260521.pdf")
OUT_PNG = Path(__file__).resolve().parent / "templates" / "sagawa_underlay.png"
A4_W, A4_H = 595.28, 841.89
SCAN_W_PT, SCAN_H_PT = 578.16, 824.40


def render_scan_png() -> tuple[np.ndarray, int, int]:
    doc = fitz.open(SCAN_PDF)
    page = doc[0]
    mat = fitz.Matrix(200 / 72, 200 / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    doc.close()
    return img, pix.width, pix.height


def find_digit_boxes(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, 40, 120)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if not (14 <= w <= 55 and 14 <= h <= 55):
            continue
        ar = w / float(h)
        if not (0.7 <= ar <= 1.3):
            continue
        area = w * h
        if not (200 <= area <= 2800):
            continue
        boxes.append((x, y, w, h))
    return boxes


def cluster_zip_row(boxes: list[tuple[int, int, int, int]], min_count: int = 6) -> list[tuple[float, float]]:
    """横一列に並ぶマスの中心 X を返す（7個想定）。"""
    if len(boxes) < min_count:
        return []
    centers = [(x + w / 2, y + h / 2) for x, y, w, h in boxes]
    centers.sort(key=lambda p: p[1])
    # Y でクラスタ（行）
    rows: list[list[tuple[float, float]]] = []
    for cx, cy in centers:
        placed = False
        for row in rows:
            if abs(row[0][1] - cy) < 35:
                row.append((cx, cy))
                placed = True
                break
        if not placed:
            rows.append([(cx, cy)])
    rows.sort(key=lambda r: sum(p[1] for p in r) / len(r))
    best = max(rows, key=len)
    if len(best) < min_count:
        return []
    best.sort(key=lambda p: p[0])
    # 7 に絞る: 最も等間隔に並ぶ連続7個
    if len(best) > 7:
        xs = [p[0] for p in best]
        best_run = best[:7]
        best_score = 1e9
        for i in range(len(best) - 6):
            run = best[i : i + 7]
            gaps = [run[j + 1][0] - run[j][0] for j in range(6)]
            score = max(gaps) - min(gaps)
            if score < best_score:
                best_score = score
                best_run = run
        best = best_run
    return best


def px_to_pt(x_px: float, y_px: float, img_w: int, img_h: int) -> tuple[float, float]:
    """画像左上原点 → ReportLab 左下原点（佐川スキャン 578×824pt に直接マップ）。"""
    x_pt = x_px / img_w * SCAN_W_PT
    y_pt = (1.0 - y_px / img_h) * SCAN_H_PT
    return x_pt, y_pt


def main() -> int:
    img, iw, ih = render_scan_png()
    best: dict | None = None
    for rot_name, rotated in [
        ("cw", cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)),
        ("ccw", cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)),
        ("raw", img),
    ]:
        rh, rw = rotated.shape[:2]
        boxes = find_digit_boxes(rotated)
        row = cluster_zip_row(boxes)
        if len(row) >= 6:
            ys = [p[1] for p in row]
            best = {
                "rot": rot_name,
                "img": rotated,
                "rw": rw,
                "rh": rh,
                "row": row,
                "y_spread": max(ys) - min(ys),
            }
            if len(row) >= 7:
                break

    if not best:
        print("zip row not found", file=sys.stderr)
        return 1

    rotated = best["img"]
    rw, rh = best["rw"], best["rh"]
    row = best["row"]
    zip_xs: list[float] = []
    zip_y_vals: list[float] = []
    for cx, cy in row:
        x_pt, y_pt = px_to_pt(cx, cy, rw, rh)
        zip_xs.append(round(x_pt, 1))
        zip_y_vals.append(y_pt)
    zip_y = round(sum(zip_y_vals) / len(zip_y_vals), 1)

    # 2行目（依頼主）を探す: 1行目より下（画像では y が大きい）
    boxes = find_digit_boxes(rotated)
    centers = [(x + w / 2, y + h / 2, x, y, w, h) for x, y, w, h in boxes]
    row1_y = sum(p[1] for p in row) / len(row)
    lower = [(cx, cy) for cx, cy, *_ in centers if cy > row1_y + 80]
    sender_row = cluster_zip_row(
        [
            (int(x), int(y), int(w), int(h))
            for cx, cy, x, y, w, h in centers
            if cy > row1_y + 80
        ]
        if lower
        else [],
        min_count=5,
    )

    sender_zip_xs: list[float] = []
    sender_zip_y = zip_y
    if len(sender_row) >= 5:
        for cx, cy in sender_row[:7]:
            x_pt, y_pt = px_to_pt(cx, cy, rw, rh)
            sender_zip_xs.append(round(x_pt, 1))
        sender_zip_y = round(
            sum(px_to_pt(cx, cy, rw, rh)[1] for cx, cy in sender_row[:7])
            / min(7, len(sender_row)),
            1,
        )

    # 保存用 PNG（A4 縦向き）
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(OUT_PNG), rotated)

    # 既存レイアウトとの差分を出力
    cal = {
        "rotation": best["rot"],
        "recipient_zip_digit_x": zip_xs,
        "recipient_zip_digit_y": zip_y,
        "sender_zip_digit_x": sender_zip_xs or zip_xs,
        "sender_zip_y_estimate": sender_zip_y,
        "left_x": round(zip_xs[0] - 2, 1) if zip_xs else 52.0,
    }
    out_json = OUT_PNG.parent / "sagawa_calibration.json"
    out_json.write_text(json.dumps(cal, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(cal, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
