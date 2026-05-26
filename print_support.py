# -*- coding: utf-8 -*-
"""Windows で PDF の印刷ダイアログを安定して開く。"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

def _sumatra_paths() -> list[str]:
    import shutil as sh

    found = sh.which("SumatraPDF") or sh.which("SumatraPDF.exe")
    paths = [
        found,
        r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
        r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
        str(Path(__file__).resolve().parent / "tools" / "SumatraPDF.exe"),
    ]
    return [p for p in paths if p and Path(p).is_file()]


def _adobe_paths() -> list[str]:
    return [
        p
        for p in (
            r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
        )
        if Path(p).is_file()
    ]


def fix_fujitsu_printer_if_needed() -> str | None:
    """
    FMPR 系が LPT1 など誤ポートのとき USB へ直し、止まったジョブを削除する。
    戻り値: ユーザー向けメッセージ（修正した場合）。問題なければ None。
    """
    return None


def get_default_printer_name() -> str:
    try:
        import win32print  # type: ignore

        return str(win32print.GetDefaultPrinter() or "").strip()
    except Exception:
        pass
    script = r"""
$p = Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue |
    Where-Object { $_.Default -eq $true } |
    Select-Object -First 1 -ExpandProperty Name
if ($p) { Write-Output $p }
"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def printer_status_message() -> str | None:
    """プリンター異常時に表示する短文。正常なら None。"""
    script = r"""
$name = (Get-CimInstance Win32_Printer -ErrorAction SilentlyContinue |
    Where-Object { $_.Default -eq $true } |
    Select-Object -First 1 -ExpandProperty Name)
if (-not $name) { exit 0 }
$p = Get-Printer -Name $name -ErrorAction SilentlyContinue
if (-not $p) { exit 0 }
if ($p.PrinterStatus -eq 'Normal' -and $p.JobCount -eq 0) { exit 0 }
Write-Output ("STATUS:" + $p.PrinterStatus + ":JOBS:" + $p.JobCount + ":PORT:" + $p.PortName + ":NAME:" + $p.Name)
"""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        line = (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return None
    if not line.startswith("STATUS:"):
        return None
    parts = line.split(":")
    status = parts[1] if len(parts) > 1 else ""
    jobs = parts[3] if len(parts) > 3 else "0"
    port = parts[5] if len(parts) > 5 else ""
    name = parts[7] if len(parts) > 7 else get_default_printer_name()
    if status == "Normal" and jobs == "0":
        return None
    msg = f"既定プリンター「{name or '不明'}」の状態: {status}"
    if port:
        msg += f"（ポート: {port}）"
    if jobs != "0":
        msg += f"\n印刷待ち {jobs} 件があります。"
    msg += "\nケーブル・電源を確認し、再度印刷してください。"
    return msg


def save_print_copy(src: Path, carrier_key: str) -> Path:
    """英数字ファイル名で output に保存（印刷エラー回避）。"""
    from excel_writer import _output_dir

    name = f"label_{carrier_key}.pdf"
    dest = _output_dir() / name
    shutil.copy2(src, dest)
    return dest.resolve()


def print_xls_via_excel(xls_path: Path) -> tuple[bool, str | None]:
    """互換用。Excelは確認用一覧であり、本番印刷には使わない。"""
    return False, "Excelは確認用です。印刷はPDFを使用してください。"


def is_excel_available() -> bool:
    """Excel COM が使えるかをチェック（インストール確認）。"""
    import sys as _sys

    if _sys.platform != "win32":
        return False
    try:
        import pythoncom  # type: ignore # noqa: F401
        import win32com.client  # type: ignore
    except ImportError:
        return False
    try:
        pythoncom.CoInitialize()
        try:
            obj = win32com.client.DispatchEx("Excel.Application")
            try:
                obj.Quit()
            except Exception:
                pass
            return True
        except Exception:
            return False
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def open_print_dialog(pdf_path: Path) -> str | None:
    """
    印刷ダイアログを開く。
    ※ Edge の「print」コマンドはエラーになりやすいので使わない。
    戻り値: プリンター設定を直したときの案内文（あれば）。
    """
    resolved = Path(pdf_path).resolve()
    lower_name = resolved.name.lower()
    if any(
        part in lower_name
        for part in ("preview_layout", "sagawa_preview_layout_latest", "print_scale_test")
    ):
        raise RuntimeError(f"確認用PDFは印刷できません: {resolved.name}")
    path = str(resolved)

    for exe in _sumatra_paths():
        try:
            subprocess.Popen(
                [exe, "-print-dialog", path],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            return None
        except OSError:
            continue

    for exe in _adobe_paths():
        try:
            subprocess.Popen([exe, path], close_fds=True)
            return None
        except OSError:
            continue

    # 既定のアプリで開く（印刷は Ctrl+P。自動 print は呼ばない）
    os.startfile(path)  # type: ignore[attr-defined]
    return None
