# -*- coding: utf-8 -*-
"""佐川レイアウト確認（自動校正済み・手動調整不要）。"""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import ttk

from label_layout import get_sagawa_layout
from pdf_print import write_sagawa_layout_preview_pdf
from preview_http import PORT, start_layout_preview_server, stop_layout_preview_server
from settings_store import layout_preview_pdf_path

APP_TITLE = "ヤフオク送付状メーカー"


def open_layout_adjust_dialog(parent: tk.Misc) -> None:
    print("[REAL_PREVIEW] opened")
    print(f"[REAL_PREVIEW] file = {__file__}")
    preview_path = layout_preview_pdf_path()
    print("PRINT_MODE = PREVIEW_LAYOUT")
    print(f"OUTPUT_PDF = {preview_path.resolve()}")
    print("PRINTER = (none)")
    print("AUTO_PRINT = false")
    print("RESULT = preview open: PDF生成/保存のみ・印刷禁止")
    try:
        from app import APP_VERSION

        ver = APP_VERSION
    except Exception:
        ver = ""

    win = tk.Toplevel(parent)
    win.title("送り状の印刷位置（佐川・自動校正）" + (f"  {ver}" if ver else ""))
    win.minsize(520, 420)
    win.transient(parent)

    def _fit() -> None:
        win.update_idletasks()
        sh = max(win.winfo_screenheight(), 600)
        h = min(max(win.winfo_reqheight() + 16, 420), sh - 48)
        w = 560
        x = max(0, parent.winfo_rootx() + 24)
        y = max(0, parent.winfo_rooty() + 12)
        win.geometry(f"{w}x{h}+{x}+{y}")

    win.after(80, _fit)

    preview_httpd: list = [None]
    preview_http_url: str | None = None
    try:
        try:
            result = start_layout_preview_server(preview_path.parent)
        except TypeError:
            result = start_layout_preview_server()
        if isinstance(result, tuple) and len(result) >= 2:
            preview_httpd[0], pr_port = result[0], result[1]
        else:
            preview_httpd[0] = result
            pr_port = PORT
        preview_http_url = f"http://127.0.0.1:{pr_port}/preview.html"
    except Exception:
        pass

    closing = {"done": False}

    def _cleanup_after_destroy() -> None:
        try:
            try:
                stop_layout_preview_server(preview_httpd[0])
            except TypeError:
                stop_layout_preview_server()
            preview_httpd[0] = None
            print("[PREVIEW_CLOSE] preview server stopped")
        except Exception as e:
            print(f"[PREVIEW_CLOSE] preview server stop skipped: {e}")
        try:
            parent.focus_force()
            print("[PREVIEW_CLOSE] parent focus_force ok")
        except tk.TclError:
            try:
                parent.focus_set()
                print("[PREVIEW_CLOSE] parent focus_set ok")
            except tk.TclError as e:
                print(f"[PREVIEW_CLOSE] parent focus failed: {e}")

    def _close(source: str) -> None:
        print("[REAL_PREVIEW] close")
        if source == "button":
            print("[PREVIEW_CLOSE] close button clicked")
        elif source == "wm":
            print("[PREVIEW_CLOSE] wm delete called")
        else:
            print(f"[PREVIEW_CLOSE] close called: {source}")
        if closing["done"]:
            print("[PREVIEW_CLOSE] already closing")
            return
        closing["done"] = True
        try:
            if win.grab_current() is win:
                win.grab_release()
                print("[PREVIEW_CLOSE] grab_release ok")
            else:
                print("[PREVIEW_CLOSE] grab_release skipped")
        except tk.TclError:
            print("[PREVIEW_CLOSE] grab_release failed")
        try:
            print("[PREVIEW_CLOSE] destroy called")
            win.destroy()
        except tk.TclError as e:
            print(f"[PREVIEW_CLOSE] destroy failed: {e}")
        try:
            parent.after(10, _cleanup_after_destroy)
        except tk.TclError:
            _cleanup_after_destroy()

    win.protocol("WM_DELETE_WINDOW", lambda: _close("wm"))

    preview_path_str = str(preview_path.resolve())

    ttk.Label(
        win,
        text=(
            "PRINT_MODE = PREVIEW_LAYOUT\n"
            "この画面はPDF生成/保存のみです。印刷は絶対に実行しません。\n\n"
            "印刷位置は sagawa_form_scan.pdf（CCF20260521）から自動校正済みです。\n"
            "手動での数値調整は不要です。\n\n"
            "（起動時に sagawa_form_scan.pdf から再校正）\n\n"
            + (f"ブラウザプレビュー:\n{preview_http_url}\n\n" if preview_http_url else "")
            + f"PDF:\n{preview_path_str}"
        ),
        wraplength=500,
        justify="left",
    ).pack(anchor="w", padx=14, pady=(12, 8))

    status = tk.StringVar(value="プレビューを更新しています…")

    def _refresh_preview() -> None:
        try:
            try:
                import importlib
                import json
                from pathlib import Path

                from tools.auto_calibrate_sagawa import calibrate

                cal = calibrate()
                cal_path = Path(__file__).resolve().parent / "templates" / "sagawa_calibration.json"
                cal_path.write_text(
                    json.dumps({**cal, "rotation": "raw"}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                import label_layout

                importlib.reload(label_layout)
            except Exception:
                pass
            lay = get_sagawa_layout()
            write_sagawa_layout_preview_pdf(preview_path, lay)
            verify_msg = ""
            try:
                from tools.verify_sagawa_alignment import main as verify_alignment

                out_dir = Path(__file__).resolve().parent / "output"
                code = verify_alignment(
                    [
                        "--png",
                        str(out_dir / "alignment_debug.png"),
                        "--preview-png",
                        str(out_dir / "layout_preview_review.png"),
                        "--check-preview-pdf",
                    ]
                )
                if code == 0:
                    verify_msg = "\n自動検証: OK（スキャンと枠が一致）"
                else:
                    verify_msg = (
                        "\n自動検証: ずれあり → output\\alignment_debug.png（緑=正・赤=現在）"
                    )
            except Exception:
                pass
            status.set(
                "プレビューを更新しました。"
                "\n印刷は実行していません。"
                + verify_msg
                + (f"\n{preview_http_url}" if preview_http_url else f"\n{preview_path_str}")
            )
        except Exception as e:
            status.set(f"プレビュー失敗: {e}")

    ttk.Label(win, textvariable=status, foreground="gray", wraplength=500).pack(
        anchor="w", padx=14, pady=4
    )

    btnf = ttk.Frame(win)
    btnf.pack(side="bottom", fill="x", padx=12, pady=12)

    def _open_preview() -> None:
        _refresh_preview()
        if preview_http_url:
            webbrowser.open(preview_http_url)
        else:
            os.startfile(str(preview_path.resolve()))  # type: ignore[attr-defined]

    ttk.Button(btnf, text="プレビューを開く", command=_open_preview).pack(side="left", padx=4)
    ttk.Button(btnf, text="閉じる", command=lambda: _close("button")).pack(side="right", padx=4)

    win.after(120, _refresh_preview)
