# -*- coding: utf-8 -*-
"""実データで佐川プレビュー/本番PDFと実測ログを生成（印刷なし）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from label_layout import get_sagawa_layout
from models import LabelPrintData
from parser import ShippingInfo, parse_shipping_text
from sagawa_field_draw import normalize_recipient_fields
from pdf_print import _make_pdf, write_sagawa_layout_preview_pdf
from sagawa_print_config import load_print_config

SAMPLE = """株式会社ビッグエー　吉田豊
住所
〒2240011
神奈川県 横浜市都筑区 牛久保町1697-8
08055555555"""


def main() -> int:
    info = parse_shipping_text(SAMPLE)
    norm = normalize_recipient_fields(
        name=info.name,
        zip_code=info.zip_code,
        address=info.address,
        phone=info.phone,
        company=info.company,
    )
    recipient = ShippingInfo(
        name=norm.name,
        zip_code=norm.zip_code,
        address=norm.address,
        phone=norm.phone,
        company=norm.company,
    )
    data = LabelPrintData(recipient=recipient)
    lay = get_sagawa_layout()
    out = ROOT / "output"
    out.mkdir(parents=True, exist_ok=True)

    preview_pdf = write_sagawa_layout_preview_pdf(out / "x.pdf", lay, data)
    prod_pdf = out / "sagawa_production_big-e.pdf"
    _make_pdf(prod_pdf, data, "sagawa", preview_underlay=False, layout=lay)

    import fitz

    png = out / "layout_preview_big-e.png"
    doc = fitz.open(preview_pdf)
    doc[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).save(str(png))
    doc.close()

    prod_doc = fitz.open(prod_pdf)
    red = sum(
        1
        for path in prod_doc[0].get_drawings()
        if (col := path.get("color"))
        and len(col) >= 3
        and col[0] > 0.9
        and col[1] < 0.15
        and col[2] < 0.15
    )
    prod_doc.close()

    cfg = load_print_config(lay)
    log = [
        "=== parse (実データ) ===",
        f"name={norm.name!r}",
        f"company={norm.company!r}",
        f"zip={norm.zip_code!r}",
        f"addr={norm.address!r}",
        f"phone={norm.phone!r}",
        f"company_is_phone_fragment={norm.company in ('08', '0', '080')}",
        "=== プレビュー ===",
        "PRINT_MODE=PREVIEW_LAYOUT preview_underlay=True 赤枠あり",
        f"OUTPUT_PDF={preview_pdf}",
        f"OUTPUT_PNG={png}",
        "=== 本番PDF ===",
        "PRINT_MODE=PRODUCTION preview_underlay=False",
        f"red_strokes={red}",
        f"OUTPUT_PDF={prod_pdf}",
        "=== 座標サマリ (DEST) ===",
        f"DEST_ZIP_CELLS[0]={cfg['DEST_ZIP_CELLS'][0]}",
        f"DEST_ADDRESS_LINES[0]={cfg['DEST_ADDRESS_LINES'][0]}",
        (
            "DEST_COMPANY="
            f"({cfg['DEST_COMPANY_X']}, {cfg['DEST_COMPANY_Y']}, "
            f"{cfg['DEST_COMPANY_W']}, {cfg['DEST_COMPANY_H']})"
        ),
        (
            "DEST_NAME="
            f"({cfg['DEST_NAME_X']}, {cfg['DEST_NAME_Y']}, "
            f"{cfg['DEST_NAME_W']}, {cfg['DEST_NAME_H']})"
        ),
        (
            "DEST_PHONE="
            f"({cfg['DEST_PHONE_X']}, {cfg['DEST_PHONE_Y']}, "
            f"{cfg['DEST_PHONE_W']}, {cfg['DEST_PHONE_H']})"
        ),
    ]
    log_path = out / "measurement_log.txt"
    log_path.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
