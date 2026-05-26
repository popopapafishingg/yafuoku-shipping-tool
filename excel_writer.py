# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

import xlwt

from models import LabelPrintData
from parser import ShippingInfo

CONFIRMATION_NOTICE = "印刷はPDFを使用。Excelは確認用"

CONFIRMATION_HEADERS = [
    "宛先郵便番号",
    "宛先住所",
    "宛先氏名",
    "電話番号",
    "商品名",
    "オークションID",
    "個数",
    "時間指定",
    "保険有無",
    "保険金額",
    "依頼主情報",
    "PDF出力パス",
]


def _app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _templates_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        p = Path(bundled) / "templates"
        if p.is_dir():
            return p
    return _app_dir() / "templates"


def _output_dir() -> Path:
    d = _app_dir() / "output"
    d.mkdir(exist_ok=True)
    return d


def _format_insurance_yen(amount: int) -> str:
    n = max(0, int(amount))
    return f"\uffe5{n:,}" if n > 0 else ""


def _sender_summary(data: LabelPrintData) -> str:
    if not data.print_sender:
        return "印刷しない"
    s = data.sender
    return "\n".join(part for part in [s.zip_code, s.address, s.name, s.phone] if str(part).strip())


def _row_values(data: LabelPrintData, pdf_path: str = "") -> list[str | int]:
    info = data.recipient
    return [
        info.zip_code,
        info.address,
        info.name,
        info.phone,
        data.product_name,
        data.auction_id,
        int(data.quantity or 0),
        data.delivery_time,
        "あり" if data.insurance_enabled else "なし",
        _format_insurance_yen(data.insurance_amount) if data.insurance_enabled else "",
        _sender_summary(data),
        pdf_path,
    ]


def _drop_phone_fragment(text: str, phone: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").strip()
    phone_digits = re.sub(r"\D", "", phone or "")
    if not s or not phone_digits:
        return s
    digits = re.sub(r"\D", "", s)
    if digits and phone_digits.startswith(digits) and re.fullmatch(r"[\d\s\-()（）ー－]+", s):
        return ""
    for n in range(min(4, len(phone_digits)), 0, -1):
        frag = re.escape(phone_digits[:n])
        s = re.sub(rf"(?<!\d)\s+{frag}$", "", s).strip()
    return s


def _confirmation_text_rows(data: LabelPrintData) -> list[tuple[str, str | int]]:
    recipient = data.recipient
    sender = data.sender
    return [
        ("宛先氏名", recipient.name),
        ("宛先郵便番号", recipient.zip_code),
        ("宛先住所", _drop_phone_fragment(recipient.address, recipient.phone)),
        ("宛先電話番号", recipient.phone),
        ("商品名", data.product_name),
        ("オークションID", data.auction_id),
        ("個数", int(data.quantity or 0)),
        ("時間指定", data.delivery_time),
        ("保険有無", "あり" if data.insurance_enabled else "なし"),
        ("保険金額", _format_insurance_yen(data.insurance_amount) if data.insurance_enabled else ""),
        ("依頼主郵便番号", sender.zip_code if data.print_sender else ""),
        ("依頼主住所", sender.address if data.print_sender else ""),
        ("依頼主名", sender.name if data.print_sender else ""),
        ("依頼主電話番号", sender.phone if data.print_sender else ""),
    ]


def write_confirmation_excel(
    rows: list[tuple[LabelPrintData, str]],
    dest: Path | None = None,
) -> Path:
    """確認用一覧Excelを作る。本番印刷はPDFだけを使う。"""
    if not rows:
        raise ValueError("確認用Excelに出力するデータがありません")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if dest is None:
        first_name = rows[0][0].recipient.name or "宛先"
        dest = _output_dir() / f"確認用_佐川データ一覧_{first_name}_{ts}.xls"
    dest.parent.mkdir(parents=True, exist_ok=True)

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("確認用一覧")

    title_style = xlwt.easyxf(
        "font: bold on, height 240; align: horiz left; pattern: pattern solid, fore_colour light_yellow;"
    )
    header_style = xlwt.easyxf(
        "font: bold on; align: horiz center, vert center; borders: bottom thin; "
        "pattern: pattern solid, fore_colour pale_blue;"
    )
    body_style = xlwt.easyxf("align: vert top, wrap on;")
    amount_style = xlwt.easyxf("align: horiz right, vert top;")

    ws.write_merge(0, 0, 0, len(CONFIRMATION_HEADERS) - 1, CONFIRMATION_NOTICE, title_style)
    ws.write_merge(
        1,
        1,
        0,
        len(CONFIRMATION_HEADERS) - 1,
        "このExcelは伝票印刷用ではありません。佐川伝票の本番印刷はPDFを使用してください。",
        body_style,
    )

    for col, header in enumerate(CONFIRMATION_HEADERS):
        ws.write(3, col, header, header_style)

    for row_index, (data, pdf_path) in enumerate(rows, start=4):
        for col, value in enumerate(_row_values(data, pdf_path)):
            style = amount_style if CONFIRMATION_HEADERS[col] == "保険金額" else body_style
            ws.write(row_index, col, value, style)

    widths = [14, 38, 18, 18, 36, 18, 8, 14, 10, 14, 36, 70]
    for col, width in enumerate(widths):
        ws.col(col).width = width * 256
    ws.panes_frozen = True
    ws.horz_split_pos = 4

    wb.save(str(dest))
    print(CONFIRMATION_NOTICE)
    print(f"確認用Excel出力パス: {dest.resolve()}")
    return dest.resolve()


def write_confirmation_text(
    data: LabelPrintData | ShippingInfo,
    dest: Path | None = None,
) -> Path:
    """Excelがない環境向けの抽出結果確認用テキストを作る。印刷には使わない。"""
    if not isinstance(data, LabelPrintData):
        data = LabelPrintData(recipient=data)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if dest is None:
        first_name = data.recipient.name or "お届け先"
        dest = _output_dir() / f"確認用_抽出結果_{first_name}_{ts}.txt"
    dest.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        CONFIRMATION_NOTICE,
        "このテキストは抽出内容確認用です。印刷位置確認用ではありません。",
        "伝票印刷には使いません。",
        "",
    ]
    for header, value in _confirmation_text_rows(data):
        lines.append(f"{header}: {value}")

    dest.write_text("\n".join(str(line) for line in lines) + "\n", encoding="utf-8-sig")
    print(CONFIRMATION_NOTICE)
    print(f"確認用テキスト出力パス: {dest.resolve()}")
    return dest.resolve()


def fill_labels(
    data: LabelPrintData | ShippingInfo,
    carrier: str = "sagawa",
    custom_sagawa: str | None = None,
    custom_seino: str | None = None,
    pdf_paths: dict[str, str] | None = None,
) -> dict[str, str]:
    """互換名。現在は伝票テンプレートではなく、確認用一覧Excelだけを作る。"""
    if not isinstance(data, LabelPrintData):
        data = LabelPrintData(recipient=data)
    pdf_path = ""
    if pdf_paths:
        pdf_path = pdf_paths.get("sagawa") or next(iter(pdf_paths.values()), "")
    dest = write_confirmation_excel([(data, pdf_path)])
    return {"confirmation": str(dest)}


def open_output_folder() -> None:
    os.startfile(str(_output_dir()))  # type: ignore[attr-defined]
