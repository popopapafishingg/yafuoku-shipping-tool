# -*- coding: utf-8 -*-
"""
佐川送り状: スキャン再検出 vs 現在レイアウトのずれを自動検証。

- 人がスクショしなくても、OpenCV で検出した枠（正）と
  sagawa_calibration.json / get_sagawa_layout() の枠（実装）を比較する。
- デバッグ画像 output/alignment_debug.png（緑=検出、赤=設定、黄線=大きいずれ）
- エージェントはこの PNG を Read ツールで直接確認できる。

使い方:
  python tools/verify_sagawa_alignment.py
  python tools/verify_sagawa_alignment.py --fix   # ずれ時に再校正して JSON 更新
  python tools/verify_sagawa_alignment.py --preview-png  # プレビューを PNG 化（AI/目視用）

エージェント向け: output/layout_preview_review.png を Read すれば、
赤破線と用紙マスの重なりをこちらで確認できる（ユーザーのスクショ不要）。
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sagawa_page import SAGAWA_PAGE_H, SAGAWA_PAGE_W
from tools.auto_calibrate_sagawa import _analyze_scan_layout, load_scan

# 中心ずれの許容（pt）。超えたら NG
THRESHOLDS_PT: dict[str, float] = {
    "zip": 10.0,
    "text": 14.0,
    "qty": 18.0,
    "insurance": 16.0,
    "item": 20.0,
}
PT_TO_MM = 25.4 / 72.0


@dataclass
class FieldCheck:
    name: str
    category: str
    err_pt: float
    ok: bool
    expected: tuple[float, float, float, float]
    actual: tuple[float, float, float, float]

    @property
    def err_mm(self) -> float:
        return round(self.err_pt * PT_TO_MM, 2)


def _center(rect: tuple[float, float, float, float]) -> tuple[float, float]:
    x, y, w, h = rect
    return x + w / 2.0, y + h / 2.0


def _center_dist(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
) -> float:
    ax, ay = _center(a)
    bx, by = _center(b)
    return float(((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5)


def _pt_rect_to_px(
    rect: tuple[float, float, float, float],
    iw: int,
    ih: int,
) -> tuple[int, int, int, int]:
    x, y, w, h = rect
    x0 = int(round(x / SAGAWA_PAGE_W * iw))
    x1 = int(round((x + w) / SAGAWA_PAGE_W * iw))
    y1 = int(round((1.0 - y / SAGAWA_PAGE_H) * ih))
    y0 = int(round((1.0 - (y + h) / SAGAWA_PAGE_H) * ih))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def _check_pair(
    name: str,
    category: str,
    expected: tuple[float, float, float, float],
    actual: tuple[float, float, float, float],
) -> FieldCheck:
    err = _center_dist(expected, actual)
    limit = THRESHOLDS_PT.get(category, 15.0)
    return FieldCheck(
        name=name,
        category=category,
        err_pt=round(err, 1),
        ok=err <= limit,
        expected=expected,
        actual=actual,
    )


def _offset_mm(
    expected: tuple[float, float, float, float],
    actual: tuple[float, float, float, float],
) -> tuple[float, float]:
    ex, ey = _center(expected)
    ax, ay = _center(actual)
    return round((ax - ex) * PT_TO_MM, 2), round((ay - ey) * PT_TO_MM, 2)


def _expected_from_scan(scan_lay: dict) -> list[tuple[str, str, tuple[float, float, float, float]]]:
    out: list[tuple[str, str, tuple[float, float, float, float]]] = []
    for i, r in enumerate(scan_lay["recv_cells"][:7]):
        out.append((f"届け先・郵便マス{i + 1}", "zip", tuple(r)))
    rt = scan_lay["recv_text"]
    for i, r in enumerate(rt["addr"]):
        out.append((f"届け先・住所{i + 1}行", "text", tuple(r)))
    out.append(("届け先・宛名", "text", tuple(rt["name"])))
    out.append(("届け先・電話", "text", tuple(rt["phone"])))
    for i, r in enumerate(scan_lay["snd_cells"][:7]):
        out.append((f"依頼主・郵便マス{i + 1}", "zip", tuple(r)))
    st = scan_lay["snd_text"]
    for i, r in enumerate(st["addr"]):
        out.append((f"依頼主・住所{i + 1}行", "text", tuple(r)))
    out.append(("依頼主・名前", "text", tuple(st["name"])))
    out.append(("依頼主・電話", "text", tuple(st["phone"])))
    out.append(("個数", "qty", tuple(scan_lay["qty"])))
    for i, r in enumerate(scan_lay["ins_rects"][:2]):
        label = "保険・チェック" if i == 0 else "保険・金額"
        out.append((label, "insurance", tuple(r)))
    return out


def _actual_from_layout() -> dict[str, tuple[float, float, float, float]]:
    from label_layout import get_sagawa_layout

    lay = get_sagawa_layout()
    return {name: (x, y, w, h) for name, x, y, w, h in lay.fields.all_preview_rects()}


def run_checks() -> tuple[list[FieldCheck], dict]:
    img, iw, ih = load_scan()
    scan_lay = _analyze_scan_layout(img, iw, ih)
    expected_list = [
        row for row in _expected_from_scan(scan_lay) if row[1] in {"zip", "text", "item"}
    ]
    actual_map = _actual_from_layout()

    checks: list[FieldCheck] = []
    missing: list[str] = []
    for name, cat, exp in expected_list:
        act = actual_map.get(name)
        if act is None:
            missing.append(name)
            continue
        checks.append(_check_pair(name, cat, exp, act))

    summary = {
        "total": len(checks),
        "ok": sum(1 for c in checks if c.ok),
        "ng": sum(1 for c in checks if not c.ok),
        "missing": missing,
        "max_err_pt": max((c.err_pt for c in checks), default=0.0),
        "worst": [
            {"name": c.name, "err_pt": c.err_pt, "limit": THRESHOLDS_PT.get(c.category, 15)}
            for c in sorted(checks, key=lambda x: -x.err_pt)[:8]
            if not c.ok
        ],
    }
    return checks, {"scan": scan_lay, "image_size": (iw, ih), "summary": summary}


def write_debug_png(
    checks: list[FieldCheck],
    scan_lay: dict,
    iw: int,
    ih: int,
    dest: Path,
) -> None:
    img, _, _ = load_scan()
    vis = img.copy()
    for c in checks:
        ex = _pt_rect_to_px(c.expected, iw, ih)
        ac = _pt_rect_to_px(c.actual, iw, ih)
        color_e = (0, 220, 0) if c.ok else (0, 200, 255)
        color_a = (0, 0, 255) if c.ok else (0, 0, 255)
        cv2.rectangle(vis, (ex[0], ex[1]), (ex[0] + ex[2], ex[1] + ex[3]), color_e, 2)
        cv2.rectangle(vis, (ac[0], ac[1]), (ac[0] + ac[2], ac[1] + ac[3]), color_a, 1)
        if not c.ok:
            cx = (ex[0] + ex[2] // 2, ex[1] + ex[3] // 2)
            ax = (ac[0] + ac[2] // 2, ac[1] + ac[3] // 2)
            cv2.line(vis, cx, ax, (0, 255, 255), 2)
            cv2.putText(
                vis,
                f"{c.err_pt:.0f}",
                (ax[0], max(12, ax[1] - 4)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.35,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), vis)


def export_preview_png(dest: Path) -> Path:
    """プレビュー PDF を高解像度 PNG に変換（実際の見え方チェック用）。"""
    import fitz

    from label_layout import get_sagawa_layout
    from pdf_print import write_sagawa_layout_preview_pdf

    tmp = dest.parent / "_layout_preview_tmp.pdf"
    pdf_path = write_sagawa_layout_preview_pdf(tmp, get_sagawa_layout())
    doc = fitz.open(pdf_path)
    try:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(dest))
    finally:
        doc.close()
        try:
            pdf_path.unlink(missing_ok=True)
        except OSError:
            pass
    return dest


def verify_preview_pdf_rects(pdf_path: Path) -> tuple[list[FieldCheck], dict]:
    """プレビュー PDF 内の赤枠（描画）とスキャン再検出の差分。"""
    import fitz

    doc = fitz.open(pdf_path)
    page = doc[0]
    ph = float(page.rect.height)
    red_rects: list[tuple[float, float, float, float]] = []
    for path in page.get_drawings():
        col = path.get("color")
        if not col or len(col) < 3:
            continue
        if col[0] < 0.9 or col[1] > 0.15 or col[2] > 0.15:
            continue
        rect = path.get("rect")
        if rect is None:
            continue
        r = rect if hasattr(rect, "x0") else fitz.Rect(rect)
        w, h = r.x1 - r.x0, r.y1 - r.y0
        if w < 0.5 or h < 0.5:
            continue
        # fitz は左上原点 → ReportLab（左下原点）へ
        red_rects.append((r.x0, ph - r.y1, w, h))
    doc.close()

    img, iw, ih = load_scan()
    scan_lay = _analyze_scan_layout(img, iw, ih)
    expected_list = [
        row for row in _expected_from_scan(scan_lay) if row[1] in {"zip", "text", "item"}
    ]

    checks: list[FieldCheck] = []
    used: set[int] = set()
    for name, cat, exp in expected_list:
        best_i = -1
        best_d = 1e9
        for i, act in enumerate(red_rects):
            if i in used:
                continue
            d = _center_dist(exp, act)
            if d < best_d:
                best_d = d
                best_i = i
        if best_i < 0:
            continue
        used.add(best_i)
        checks.append(_check_pair(name, cat, exp, red_rects[best_i]))

    summary = {
        "total": len(checks),
        "ok": sum(1 for c in checks if c.ok),
        "ng": sum(1 for c in checks if not c.ok),
        "red_rects_in_pdf": len(red_rects),
        "max_err_pt": max((c.err_pt for c in checks), default=0.0),
    }
    return checks, {"summary": summary, "scan": scan_lay, "image_size": (iw, ih)}


def _sync_position_config_from_scan() -> Path:
    """DEST/SENDER/商品欄のみスキャン検出値へ。保険・個数・時間指定は既存値を維持。"""
    from label_layout import get_sagawa_layout
    from sagawa_print_config import CONFIG_NAME, config_path, default_config

    lay = get_sagawa_layout()
    fresh = default_config(lay)
    preserve_prefixes = ("QUANTITY_", "INSURANCE_", "TIME_CHECK_", "PRICE_")
    preserve_keys = {
        "OFFSET_X",
        "OFFSET_Y",
        "DEST_OFFSET_X",
        "DEST_OFFSET_Y",
        "SENDER_OFFSET_X",
        "SENDER_OFFSET_Y",
        "ITEM_OFFSET_X",
        "ITEM_OFFSET_Y",
        "PRICE_OFFSET_X",
        "PRICE_OFFSET_Y",
        "TIME_OFFSET_X",
        "TIME_OFFSET_Y",
        "ZIP_SPACING",
        "DEBUG_GUIDES",
        "DEBUG_BORDERS",
        "DEBUG_LABELS",
        "DEBUG_UNDERLAY",
        "DEBUG_TIME_CHECK_FORCE",
    }
    written: Path | None = None
    for path in (config_path(), ROOT / "templates" / CONFIG_NAME):
        old: dict = {}
        if path.is_file():
            try:
                old = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                old = {}
        merged = dict(fresh)
        for key, val in old.items():
            if key in preserve_keys or key.startswith(preserve_prefixes):
                merged[key] = val
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        written = path
    return written or config_path()


def apply_fix() -> None:
    from tools.auto_calibrate_sagawa import calibrate

    cal = calibrate()
    out = ROOT / "templates" / "sagawa_calibration.json"
    out.write_text(
        json.dumps({**cal, "rotation": "raw"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    import importlib

    import label_layout

    importlib.reload(label_layout)
    cfg_path = _sync_position_config_from_scan()
    print(f"position config synced: {cfg_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="佐川レイアウト自動ずれ検証")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="NG 時に sagawa_calibration.json を再生成",
    )
    parser.add_argument(
        "--png",
        type=Path,
        default=ROOT / "output" / "alignment_debug.png",
        help="デバッグ画像の出力先",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "output" / "alignment_report.json",
        help="JSON レポート出力先",
    )
    parser.add_argument(
        "--preview-png",
        type=Path,
        nargs="?",
        const=str(ROOT / "output" / "layout_preview_review.png"),
        default=None,
        help="プレビュー PDF を PNG 出力（パス省略可）",
    )
    parser.add_argument(
        "--check-preview-pdf",
        action="store_true",
        help="プレビュー PDF の赤枠とスキャン検出を比較（実表示ベース）",
    )
    args = parser.parse_args(argv)

    if args.preview_png is not None:
        png_path = Path(args.preview_png)
        export_preview_png(png_path)
        print(f"preview png: {png_path}")
        if not args.check_preview_pdf:
            return 0

    checks: list[FieldCheck]
    meta: dict
    if args.check_preview_pdf:
        from pdf_print import write_sagawa_layout_preview_pdf
        from label_layout import get_sagawa_layout

        pdf_path = write_sagawa_layout_preview_pdf(
            ROOT / "output" / "_layout_preview_verify.pdf",
            get_sagawa_layout(),
        )
        checks, meta = verify_preview_pdf_rects(pdf_path)
        meta["mode"] = "preview_pdf"
    else:
        checks, meta = run_checks()
        meta["mode"] = "layout_vs_scan"
    write_debug_png(checks, meta["scan"], *meta["image_size"], args.png)

    report = {
        "summary": meta["summary"],
        "checks": [
            {
                "name": c.name,
                "category": c.category,
                "err_pt": c.err_pt,
                "err_mm": c.err_mm,
                "ok": c.ok,
                "expected": list(c.expected),
                "actual": list(c.actual),
                "delta_center_mm": list(_offset_mm(c.expected, c.actual)),
            }
            for c in checks
        ],
        "debug_png": str(args.png.resolve()),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    s = meta["summary"]
    print(f"OK {s['ok']}/{s['total']}  NG {s['ng']}  max_err={s['max_err_pt']}pt")
    print(f"max_err_mm={round(float(s['max_err_pt']) * PT_TO_MM, 2)}mm")
    print(
        "※ 数値OK = 検出ロジックと設定JSONの一致。"
        "用紙との見た目は layout_preview_review.png で確認してください。"
    )
    print(f"debug: {args.png}")
    print(f"report: {args.report}")

    if s["ng"] > 0 or s.get("missing"):
        if args.fix:
            print("再校正を実行…")
            apply_fix()
            checks2, meta2 = run_checks()
            write_debug_png(checks2, meta2["scan"], *meta2["image_size"], args.png)
            s2 = meta2["summary"]
            print(f"再検証 OK {s2['ok']}/{s2['total']}  NG {s2['ng']}")
            return 0 if s2["ng"] == 0 and not s2["missing"] else 1
        for w in s.get("worst", []):
            mm = round(float(w["err_pt"]) * PT_TO_MM, 2)
            print(f"  NG {w['name']}: {w['err_pt']}pt / {mm}mm (limit {w['limit']}pt)")
        ng_checks = sorted((c for c in checks if not c.ok), key=lambda x: -x.err_pt)[:8]
        for c in ng_checks:
            dx_mm, dy_mm = _offset_mm(c.expected, c.actual)
            print(f"  Δcenter {c.name}: dx={dx_mm}mm dy={dy_mm}mm")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
