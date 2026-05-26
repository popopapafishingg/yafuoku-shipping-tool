# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import os
import tkinter as tk
import unicodedata
from pathlib import Path
from tkinter import messagebox, ttk

from address_utils import (
    is_phone_digit_fragment,
    sanitize_company_name,
    split_address_company,
    split_person_company_line,
)
from excel_writer import CONFIRMATION_NOTICE, fill_labels, open_output_folder, write_confirmation_text
from models import LabelPrintData, SenderInfo
from pdf_print import (
    PRINT_MODE_REAL_SAGAWA_OVERLAY,
    export_shipping_label_pdfs,
    print_shipping_labels,
    write_sagawa_layout_preview_pdf,
)
from print_support import get_default_printer_name, printer_status_message
from item_parser import (
    extract_delivery_time,
    extract_insurance_requested,
    parse_auction_product,
)
from parser import ShippingInfo, parse_shipping_text, extract_phone_any
from settings_store import (
    layout_preview_pdf_path,
    load_carrier,
    load_insurance_amount,
    load_insurance_enabled,
    load_print_sender_default,
    load_sender,
    save_carrier,
    save_insurance,
    save_sender,
)
from label_layout import get_sagawa_layout
from sagawa_print_config import config_path, load_print_config, save_print_config
from sagawa_print_config import (
    ensure_seino_placeholder_files,
    load_position_config,
    load_margin_config,
    margin_config_path,
    save_margin_config,
    seino_config_path,
    seino_margin_config_path,
)

APP_TITLE = "ヤフオク送付状メーカー"
APP_VERSION = "2026-05-26 preview-real build-1325"
SAMPLE = """お届け先
889-1403
宮崎県
児湯郡新富町上富田7478-3
切通宿舎D棟108号
高見 亮輔
購入者に連絡:
電話: 08039431932"""


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE}  {APP_VERSION}")
        self.minsize(860, 800)

        # 届け先
        self.var_name = tk.StringVar()
        self.var_zip = tk.StringVar()
        self.var_addr = tk.StringVar()
        self.var_company = tk.StringVar()
        self.var_recipient_phone = tk.StringVar()
        # 商品・オークション
        self.var_auction_id = tk.StringVar()
        self.var_product = tk.StringVar()
        self.var_quantity = tk.StringVar(value="1")
        self.var_delivery_time = tk.StringVar()
        # 発送元
        self.var_sender_zip = tk.StringVar()
        self.var_sender_addr = tk.StringVar()
        self.var_sender_name = tk.StringVar()
        self.var_sender_phone = tk.StringVar()
        self.var_print_sender = tk.BooleanVar(value=load_print_sender_default())
        self.var_insurance_mode = tk.StringVar(
            value="yes" if load_insurance_enabled() else "no"
        )
        self.var_insurance_amount = tk.StringVar(value=str(load_insurance_amount()))
        # その他
        self.var_carrier = tk.StringVar(value=load_carrier())
        self.var_carrier.trace_add("write", self._on_carrier_changed)
        self.custom_sagawa: str | None = None
        self.custom_seino: str | None = None

        self._load_sender_fields()
        self._build_ui()
        self.after(80, self._apply_startup_geometry)
        self.after(200, self._ensure_layout_calibrated)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _ensure_layout_calibrated(self) -> None:
        try:
            from settings_store import clear_sagawa_layout_overrides

            clear_sagawa_layout_overrides()
            try:
                import importlib
                import json

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
        except Exception:
            pass

    def _apply_startup_geometry(self) -> None:
        """最大化しない。印刷ボタン行が必ず入る高さに固定。"""
        self.update_idletasks()
        sw = max(self.winfo_screenwidth(), 800)
        sh = max(self.winfo_screenheight(), 600)
        need_h = max(self.winfo_reqheight() + 16, 820)
        h = min(need_h, sh - 40)
        w = min(940, sw - 32)
        x = max(0, (sw - w) // 2)
        y = max(0, (sh - h) // 2 - 12)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.update_idletasks()

    def _load_sender_fields(self) -> None:
        s = load_sender()
        self.var_sender_zip.set(s.zip_code)
        self.var_sender_addr.set(s.address)
        self.var_sender_name.set(s.name)
        self.var_sender_phone.set(s.phone)

    def _build_ui(self) -> None:
        pad = {"padx": 10, "pady": 3}
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True)

        act = ttk.Frame(container)
        act.pack(side="bottom", fill="x", padx=10, pady=(6, 12))
        ttk.Button(act, text="佐川で印刷", command=lambda: self._print_for_carrier("sagawa"), style="Print.TButton").pack(
            side="left", padx=4
        )
        ttk.Button(act, text="西濃で印刷", command=lambda: self._print_for_carrier("seino")).pack(side="left", padx=4)
        ttk.Button(act, text="佐川＋西濃 両方印刷", command=lambda: self._print_for_carrier("both")).pack(side="left", padx=4)
        ttk.Button(act, text="確認用Excelを開く", command=self._on_create).pack(side="left", padx=4)
        ttk.Button(act, text="確認用テキストを開く", command=self._on_create_text).pack(side="left", padx=4)
        ttk.Button(act, text="佐川 座標調整", command=lambda: self._open_position_adjuster("sagawa")).pack(side="left", padx=4)
        ttk.Button(act, text="西濃 座標調整", command=lambda: self._open_position_adjuster("seino")).pack(side="left", padx=4)
        ttk.Button(act, text="出力フォルダ", command=open_output_folder).pack(side="left", padx=4)
        try:
            ttk.Style().configure("Print.TButton", font=("", 12, "bold"))
        except tk.TclError:
            pass

        outer = ttk.Frame(container)
        outer.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(outer, highlightthickness=0)
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        body = ttk.Frame(canvas)

        def _on_body_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(body_win, width=canvas.winfo_width())

        body.bind("<Configure>", _on_body_configure)
        body_win = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(body_win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        def _on_mousewheel(event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        ttk.Label(
            body,
            text="お届け情報を貼り付け → 各欄を確認 →「佐川伝票へ印刷（PDF）」",
            font=("", 11, "bold"),
        ).pack(anchor="w", **pad)
        ttk.Label(
            body,
            text=CONFIRMATION_NOTICE,
            foreground="red",
            font=("", 10, "bold"),
        ).pack(anchor="w", **pad)
        ttk.Label(
            body,
            text="印刷設定: ✔ 実際のサイズ / ✔ 100% / ✘ ページに合わせる / ✘ 用紙に合わせる / ✘ 余白付き印刷",
            foreground="red",
            font=("", 10, "bold"),
        ).pack(anchor="w", **pad)

        frm = ttk.LabelFrame(body, text="① お届け情報（ヤフオクからコピー）")
        frm.pack(fill="x", padx=10, pady=4)
        self.txt = tk.Text(frm, height=7, wrap="word", font=("Yu Gothic UI", 10))
        self.txt.pack(fill="x", padx=6, pady=6)
        self.txt.bind("<<Paste>>", lambda e: self.after(80, self._on_parse))
        self.txt.bind("<Control-v>", self._on_paste_shortcut_main)
        self.txt.bind("<Control-V>", self._on_paste_shortcut_main)
        self.txt.bind("<KeyRelease>", lambda e: self.after(300, self._on_parse))
        self._paste_menu = tk.Menu(self.txt, tearoff=0)
        self._paste_menu.add_command(label="貼り付け", command=self._paste_from_clipboard)
        self.txt.bind("<Button-3>", self._show_paste_menu)
        br = ttk.Frame(frm)
        br.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(br, text="貼り付け", command=self._paste_from_clipboard).pack(side="left", padx=2)
        ttk.Button(br, text="読み取り", command=self._on_parse).pack(side="left", padx=2)
        ttk.Button(br, text="サンプル", command=self._load_sample).pack(side="left", padx=2)
        ttk.Button(br, text="クリア", command=self._clear).pack(side="left", padx=2)

        row2 = ttk.Frame(body)
        row2.pack(fill="x", padx=10, pady=4)
        row2.columnconfigure(0, weight=1)
        row2.columnconfigure(1, weight=1)

        dest = ttk.LabelFrame(row2, text="② 届け先")
        dest.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self._grid_entries(
            dest,
            [
                ("氏名", self.var_name),
                ("郵便番号", self.var_zip),
                ("住所", self.var_addr),
                ("会社名", self.var_company),
                ("電話番号", self.var_recipient_phone),
            ],
        )

        item = ttk.LabelFrame(row2, text="② 商品情報（右側に印刷）")
        item.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        ttk.Label(
            item,
            text="IDと商品名をまとめて貼り付け → 自動で分かれます",
            foreground="gray",
        ).pack(anchor="w", padx=8, pady=(6, 2))
        ib = ttk.Frame(item)
        ib.pack(fill="x", padx=8, pady=2)
        self.txt_item = tk.Text(item, height=3, wrap="word", font=("Yu Gothic UI", 9))
        self.txt_item.pack(fill="x", padx=8, pady=2)
        self.txt_item.bind("<<Paste>>", lambda e: self.after(80, self._parse_item_box))
        self.txt_item.bind("<KeyRelease>", lambda e: self.after(300, self._parse_item_box))
        ttk.Button(ib, text="貼り付け", command=self._paste_item_box).pack(side="left", padx=2)
        ttk.Button(ib, text="読み取り", command=self._parse_item_box).pack(side="left", padx=2)
        self._grid_entries(
            item,
            [
                ("オークションID", self.var_auction_id),
                ("商品名", self.var_product),
                ("数量", self.var_quantity),
                ("時間指定", self.var_delivery_time),
            ],
        )
        ttk.Label(
            item,
            text="例: k123456789 の次の行に商品名 / または1行でスペース区切り",
            foreground="gray",
        ).pack(anchor="w", padx=8, pady=(0, 6))

        sender = ttk.LabelFrame(body, text="③ 発送元（ご依頼主・任意）")
        sender.pack(fill="x", padx=10, pady=4)
        ttk.Label(
            sender,
            text="※ 空のままでOK。「印刷しない」を選べば届け先だけ印刷されます",
            foreground="gray",
        ).pack(anchor="w", padx=8, pady=(6, 0))
        self._grid_entries(
            sender,
            [
                ("郵便番号", self.var_sender_zip),
                ("住所", self.var_sender_addr),
                ("名前", self.var_sender_name),
                ("電話番号", self.var_sender_phone),
            ],
        )
        sf = ttk.Frame(sender)
        sf.pack(fill="x", padx=8, pady=(4, 8))
        ttk.Label(sf, text="発送元の印刷：").pack(side="left")
        ttk.Radiobutton(
            sf,
            text="印刷する",
            variable=self.var_print_sender,
            value=True,
            command=self._on_sender_toggle,
        ).pack(side="left", padx=6)
        ttk.Radiobutton(
            sf,
            text="印刷しない",
            variable=self.var_print_sender,
            value=False,
            command=self._on_sender_toggle,
        ).pack(side="left", padx=6)
        ttk.Button(sf, text="発送元を保存", command=self._save_sender).pack(side="left", padx=12)

        insf = ttk.LabelFrame(body, text="④ 保険（佐川）")
        insf.pack(fill="x", padx=10, pady=4)
        ir = ttk.Frame(insf)
        ir.pack(anchor="w", padx=8, pady=6)
        ttk.Label(ir, text="保険：").pack(side="left")
        ttk.Radiobutton(
            ir,
            text="要る",
            variable=self.var_insurance_mode,
            value="yes",
            command=self._on_insurance_mode,
        ).pack(side="left", padx=(4, 10))
        ttk.Radiobutton(
            ir,
            text="不要",
            variable=self.var_insurance_mode,
            value="no",
            command=self._on_insurance_mode,
        ).pack(side="left", padx=(0, 16))
        self.lbl_ins_amount = ttk.Label(ir, text="金額（円）")
        self.lbl_ins_amount.pack(side="left")
        self.ent_insurance_amount = ttk.Entry(
            ir, textvariable=self.var_insurance_amount, width=10
        )
        self.ent_insurance_amount.pack(side="left", padx=4)
        ttk.Label(ir, text="※ PDFにのみ印刷。Excelは確認用一覧", foreground="gray").pack(
            side="left", padx=8
        )
        self._on_insurance_mode()

        crf = ttk.LabelFrame(body, text="⑤ 送付状の種類")
        crf.pack(fill="x", padx=10, pady=4)
        cr = ttk.Frame(crf)
        cr.pack(anchor="w", padx=8, pady=6)
        for val, text in [("both", "佐川・西濃"), ("sagawa", "佐川のみ"), ("seino", "西濃のみ")]:
            ttk.Radiobutton(cr, text=text, variable=self.var_carrier, value=val).pack(
                side="left", padx=8
            )

    def _grid_entries(self, parent: ttk.Frame, rows: list[tuple[str, tk.StringVar]]) -> None:
        if not hasattr(self, "_entry_widgets"):
            self._entry_widgets: list[ttk.Entry] = []
        g = ttk.Frame(parent)
        g.pack(fill="x", padx=8, pady=6)
        for i, (lb, var) in enumerate(rows):
            ttk.Label(g, text=lb, width=12).grid(row=i, column=0, sticky="nw", pady=3)
            ent = ttk.Entry(g, textvariable=var, width=36)
            ent.grid(row=i, column=1, sticky="ew", pady=3)
            ent.bind("<Control-v>", lambda e, w=ent: self._paste_into_entry(w))
            ent.bind("<Control-V>", lambda e, w=ent: self._paste_into_entry(w))
            self._entry_widgets.append(ent)
        g.columnconfigure(1, weight=1)

    def _on_paste_shortcut_main(self, event=None) -> None:
        self.after(120, self._sync_all_from_paste)

    def _paste_into_entry(self, entry: ttk.Entry) -> str:
        try:
            text = self.clipboard_get()
            entry.delete(0, "end")
            entry.insert(0, text)
            self.after(80, self._parse_item_box)
        except tk.TclError:
            pass
        return "break"

    def _paste_item_box(self) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning(APP_TITLE, "クリップボードに文字がありません。")
            return
        self.txt_item.delete("1.0", "end")
        self.txt_item.insert("1.0", text)
        self._parse_item_box()

    def _parse_item_box(self) -> None:
        raw = self.txt_item.get("1.0", "end").strip()
        if not raw:
            return
        aid, prod, qty = parse_auction_product(raw)
        if aid:
            self.var_auction_id.set(aid)
        if prod:
            self.var_product.set(prod)
        if qty:
            self.var_quantity.set(str(qty))
        dt = extract_delivery_time(raw)
        if dt:
            self.var_delivery_time.set(dt)

    def _show_paste_menu(self, event) -> None:
        try:
            self._paste_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._paste_menu.grab_release()

    def _paste_from_clipboard(self, replace_all: bool = True) -> None:
        try:
            text = self.clipboard_get()
        except tk.TclError:
            messagebox.showwarning(APP_TITLE, "クリップボードに文字がありません。")
            return
        if replace_all:
            self.txt.delete("1.0", "end")
            self.txt.insert("1.0", text)
        else:
            self.txt.insert("insert", text)
        self.txt.focus_set()
        self.after(80, self._sync_all_from_paste)

    def _apply_shipping_info(self, info: ShippingInfo) -> None:
        phone = (info.phone or "").strip()
        company = sanitize_company_name((info.company or "").strip(), phone)
        name = (info.name or "").strip()
        if name and not is_phone_digit_fragment(name, phone):
            person, corp_from_name = split_person_company_line(name, phone)
            if corp_from_name:
                name = person or name
        else:
            corp_from_name = ""
            if is_phone_digit_fragment(name, phone):
                name = ""

        addr, company_from_addr = split_address_company(info.address, phone)
        if not company and company_from_addr:
            company = company_from_addr
        if corp_from_name and not company:
            company = corp_from_name
        addr = self._drop_phone_fragment(addr, phone)
        company = sanitize_company_name(self._drop_phone_fragment(company, phone), phone)
        if self._looks_like_phone(addr) or is_phone_digit_fragment(addr, phone):
            addr = ""
        if company and name and name == company:
            company = ""
        if info.zip_code:
            self.var_zip.set(info.zip_code)
        self.var_addr.set(addr or "")
        self.var_company.set(company or "")
        if name:
            self.var_name.set(name)
        self.var_recipient_phone.set((info.phone or "").strip())

    def _looks_like_phone(self, text: str) -> bool:
        s = unicodedata.normalize("NFKC", text or "").strip()
        digits = re.sub(r"\D", "", s)
        if len(digits) not in (10, 11) or not digits.startswith("0"):
            return False
        return bool(re.fullmatch(r"[\d\s\-()（）ー－]+", s))

    def _is_phone_fragment(self, text: str, phone: str) -> bool:
        digits = re.sub(r"\D", "", unicodedata.normalize("NFKC", text or ""))
        phone_digits = re.sub(r"\D", "", phone or "")
        return bool(digits and phone_digits and phone_digits.startswith(digits))

    def _drop_phone_fragment(self, text: str, phone: str) -> str:
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

    def _try_loose_parse(self, raw: str) -> None:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        phone = extract_phone_any(raw)
        for i, line in enumerate(lines):
            if line in ("氏名", "お名前") and i + 1 < len(lines):
                person, company = split_person_company_line(lines[i + 1].strip(), phone)
                self.var_name.set(person)
                self.var_company.set(company or "")
            if line == "住所" and i + 1 < len(lines):
                zip_code = ""
                addr_parts: list[str] = []
                for ln in lines[i + 1 :]:
                    if self._looks_like_phone(ln) or is_phone_digit_fragment(ln, phone):
                        break
                    clean = ln.replace("〒", "").strip()
                    if not zip_code and re.fullmatch(r"\d{7}", re.sub(r"\D", "", clean)):
                        zip_code = re.sub(r"\D", "", clean)
                        continue
                    if re.search(r"[都道府県市区町村郡]", ln) or re.search(r"\d", ln):
                        addr_parts.append(ln)
                if zip_code:
                    self.var_zip.set(zip_code)
                if addr_parts:
                    self.var_addr.set(addr_parts[0])
            if "氏名" in line and ("：" in line or ":" in line):
                person, company = split_person_company_line(
                    re.split(r"[:：]", line, 1)[1].strip(), phone
                )
                self.var_name.set(person)
                self.var_company.set(company or "")
        self.var_recipient_phone.set(phone)

    def _sync_all_from_paste(self) -> None:
        raw = self.txt.get("1.0", "end").strip()
        if raw:
            try:
                info = parse_shipping_text(raw)
                self._apply_shipping_info(info)
                if not self.var_recipient_phone.get().strip():
                    self.var_recipient_phone.set(extract_phone_any(raw))
            except ValueError:
                self._try_loose_parse(raw)
            aid, prod, qty = parse_auction_product(raw)
            if aid and not self.var_auction_id.get().strip():
                self.var_auction_id.set(aid)
            if prod and not self.var_product.get().strip():
                self.var_product.set(prod)
            if qty and (not self.var_quantity.get().strip() or self.var_quantity.get().strip() == "1"):
                self.var_quantity.set(str(qty))
            dt = extract_delivery_time(raw)
            if dt and not self.var_delivery_time.get().strip():
                self.var_delivery_time.set(dt)
            ins = extract_insurance_requested(raw)
            if ins is not None:
                self.var_insurance_mode.set("yes" if ins else "no")
                self._on_insurance_mode()
        self._parse_item_box()

    def _on_close(self) -> None:
        save_carrier(self.var_carrier.get())
        self._save_sender_quiet()
        self._save_insurance_quiet()
        self.destroy()

    def _insurance_enabled(self) -> bool:
        return self.var_insurance_mode.get() == "yes"

    def _on_insurance_mode(self) -> None:
        on = self._insurance_enabled()
        state = "normal" if on else "disabled"
        self.ent_insurance_amount.configure(state=state)

    def _save_insurance_quiet(self) -> None:
        try:
            amt = int(re.sub(r"[^\d]", "", self.var_insurance_amount.get() or "0"))
        except ValueError:
            amt = 50000
        save_insurance(self._insurance_enabled(), amt)

    def _save_sender_quiet(self) -> None:
        save_sender(self._get_sender(), self.var_print_sender.get())

    def _on_carrier_changed(self, *_args) -> None:
        save_carrier(self.var_carrier.get())

    def _on_sender_toggle(self) -> None:
        pass

    def _save_sender(self) -> None:
        self._save_sender_quiet()
        messagebox.showinfo(APP_TITLE, "発送元を保存しました。")

    def _get_sender(self) -> SenderInfo:
        return SenderInfo(
            zip_code=self.var_sender_zip.get().strip().replace("-", ""),
            address=self.var_sender_addr.get().strip(),
            name=self.var_sender_name.get().strip(),
            phone=self.var_sender_phone.get().strip(),
        )

    def _load_sample(self) -> None:
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", SAMPLE)
        self._on_parse()

    def _clear(self) -> None:
        self.txt.delete("1.0", "end")
        if hasattr(self, "txt_item"):
            self.txt_item.delete("1.0", "end")
        for v in (
            self.var_name,
            self.var_zip,
            self.var_addr,
            self.var_company,
            self.var_recipient_phone,
            self.var_auction_id,
            self.var_product,
            self.var_delivery_time,
        ):
            v.set("")

    def _on_parse(self) -> None:
        self._sync_all_from_paste()

    def _get_recipient(self) -> ShippingInfo:
        self._sync_all_from_paste()

        name = self.var_name.get().strip()
        zip_code = self.var_zip.get().strip().replace("-", "")
        addr = self.var_addr.get().strip()
        company = sanitize_company_name(
            self.var_company.get().strip(),
            self.var_recipient_phone.get().strip(),
        )

        if company and name and name == company:
            company = ""

        address = self._drop_phone_fragment(addr, self.var_recipient_phone.get().strip())
        company = sanitize_company_name(company, self.var_recipient_phone.get().strip())

        if not name and not address and not zip_code:
            raise ValueError(
                "お届け情報を貼り付けるか、②届け先（氏名・住所）を入力してください。"
            )

        if not name:
            if company:
                name = company
                company = ""
            elif addr:
                name = "ご担当者"
            else:
                raise ValueError(
                    "氏名が読み取れませんでした。\n"
                    "①で貼り付け後「読み取り」を押すか、②の氏名欄に直接入力してください。"
                )

        return ShippingInfo(
            name=name,
            zip_code=zip_code,
            address=address,
            phone=self.var_recipient_phone.get().strip(),
            company=company,
        )

    def _get_label_data(self) -> LabelPrintData:
        print_sender = self.var_print_sender.get()
        sender = self._get_sender()
        if print_sender:
            has_sender = bool(
                sender.name or sender.zip_code or sender.address or sender.phone
            )
            if not has_sender:
                print_sender = False

        self._parse_item_box()
        aid = self.var_auction_id.get().strip()
        prod = self.var_product.get().strip()

        try:
            ins_amount = int(re.sub(r"[^\d]", "", self.var_insurance_amount.get() or "0"))
        except ValueError:
            ins_amount = 50000
        try:
            qty = max(1, int(re.sub(r"[^\d]", "", self.var_quantity.get() or "1")))
        except ValueError:
            qty = 1

        return LabelPrintData(
            recipient=self._get_recipient(),
            auction_id=aid,
            product_name=prod,
            quantity=qty,
            delivery_time=self.var_delivery_time.get().strip(),
            sender=sender,
            print_sender=print_sender,
            insurance_enabled=self._insurance_enabled(),
            insurance_amount=ins_amount,
        )

    def _carriers(self) -> list[str]:
        c = self.var_carrier.get()
        o: list[str] = []
        if c in ("sagawa", "both"):
            o.append("sagawa")
        if c in ("seino", "both"):
            o.append("seino")
        return o

    def _print_for_carrier(self, carrier: str) -> None:
        self.var_carrier.set(carrier)
        self._on_print()

    def _on_print(self) -> None:
        try:
            save_carrier(self.var_carrier.get())
            self._save_insurance_quiet()
            self._sync_all_from_paste()
            data = self._get_label_data()
            printer = get_default_printer_name()
            if not printer:
                raise RuntimeError("既定プリンターが見つかりません。Windowsの既定プリンターを設定してください。")
            print(CONFIRMATION_NOTICE)
            print(f"PRINT_MODE = {PRINT_MODE_REAL_SAGAWA_OVERLAY}")
            print(f"PRINTER = {printer}")
            print("AUTO_PRINT = false")
            print("本番印刷PDFだけを印刷します。Excelは印刷に使いません。")
            print("印刷設定: 実際のサイズ / 100%")
            print("禁止: ページに合わせる / 用紙に合わせる / 余白付き印刷")
            print("RESULT = confirm_before_print待ち")
            if not messagebox.askyesno(
                APP_TITLE,
                "印刷はPDFを使用します。Excelは確認用です。\n\n"
                f"PRINT_MODE = {PRINT_MODE_REAL_SAGAWA_OVERLAY}\n"
                f"PRINTER = {printer}\n"
                "AUTO_PRINT = false\n\n"
                "印刷ダイアログを開きますか？",
            ):
                print("RESULT = ユーザー取消")
                return
            print("RESULT = confirm_before_print OK")
            fix_msg = print_shipping_labels(data, self._carriers())
            if fix_msg:
                messagebox.showinfo(APP_TITLE, fix_msg)
            else:
                warn = printer_status_message()
                if warn:
                    messagebox.showwarning(APP_TITLE, warn)
        except ValueError as e:
            messagebox.showwarning(APP_TITLE, str(e))
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _on_create(self) -> None:
        try:
            d = self._get_label_data()
            pdf_paths = export_shipping_label_pdfs(d, self._carriers())
            paths = fill_labels(
                d,
                self.var_carrier.get(),
                self.custom_sagawa,
                self.custom_seino,
                pdf_paths,
            )
            for p in paths.values():
                if not Path(p).is_file():
                    raise FileNotFoundError(f"出力ファイルが見つかりません: {p}")
                os.startfile(str(Path(p).resolve()))  # type: ignore[attr-defined]
            msg = (
                f"{CONFIRMATION_NOTICE}\n\n"
                "印刷設定: 実際のサイズ / 100%\n"
                "禁止: ページに合わせる / 用紙に合わせる / 余白付き印刷\n\n"
                "本番印刷用PDF:\n"
                + "\n".join(pdf_paths.values())
                + "\n\n確認用Excel:\n"
                + "\n".join(paths.values())
            )
            print(msg)
            messagebox.showinfo(APP_TITLE, msg)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _on_create_text(self) -> None:
        try:
            d = self._get_label_data()
            path = write_confirmation_text(d)
            os.startfile(str(Path(path).resolve()))  # type: ignore[attr-defined]
            print(f"確認用テキストを開きました: {path}")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _position_targets(self) -> list[tuple[str, tuple]]:
        return [
            ("宛先郵便番号", ("cells", "DEST_ZIP_CELLS")),
            ("宛先住所", ("lines", "DEST_ADDRESS_LINES")),
            ("宛先会社名", ("box", "DEST_COMPANY")),
            ("宛先氏名", ("box", "DEST_NAME")),
            ("宛先電話番号", ("box", "DEST_PHONE")),
            ("商品名", ("lines", "ITEM_NAME_LINES")),
            ("オークションID", ("box", "ITEM_ID")),
            ("個数", ("box", "QUANTITY")),
            ("時間指定", ("time",)),
            ("保険", ("boxes", ("INSURANCE_CHECK", "INSURANCE_AMOUNT"))),
            ("送り主郵便番号", ("cells", "SENDER_ZIP_CELLS")),
            ("送り主住所", ("lines", "SENDER_ADDRESS_LINES")),
            ("送り主名", ("box", "SENDER_NAME")),
            ("送り主電話番号", ("box", "SENDER_PHONE")),
        ]

    def _shift_position_target(self, spec: tuple, direction: str, amount: float) -> Path:
        layout = get_sagawa_layout()
        cfg = load_position_config(layout)
        key = "x" if direction == "horizontal" else "y"
        suffix = "_X" if direction == "horizontal" else "_Y"

        def shift_list(name: str) -> None:
            items = cfg.get(name, [])
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item[key] = float(item.get(key, 0.0)) + amount

        def shift_box(prefix: str) -> None:
            cfg[f"{prefix}{suffix}"] = float(cfg.get(f"{prefix}{suffix}", 0.0)) + amount

        mode = spec[0]
        if mode in ("cells", "lines"):
            shift_list(str(spec[1]))
        elif mode == "box":
            shift_box(str(spec[1]))
        elif mode == "boxes":
            for prefix in spec[1]:
                shift_box(str(prefix))
        elif mode == "time":
            for slot in ("MORNING", "12_14", "14_16", "16_18", "18_20", "19_21"):
                shift_box(f"TIME_CHECK_{slot}")
        else:
            raise ValueError(f"不明な調整項目です: {mode}")
        return save_print_config(cfg)

    def _regenerate_position_preview(self, status_var: tk.StringVar | None = None) -> Path:
        data = self._get_label_data()
        layout = get_sagawa_layout()
        path = write_sagawa_layout_preview_pdf(layout_preview_pdf_path(), layout, data)
        try:
            os.startfile(str(Path(path).resolve()))  # type: ignore[attr-defined]
            msg = f"PDFを開きました。保存先: {path}"
        except Exception:
            msg = f"PDFを開けませんでした。保存先: {path}"
        print(msg)
        if status_var is not None:
            status_var.set(msg)
        return path

    def _shift_margin(self, direction: str, amount: float) -> Path:
        cfg = load_margin_config()
        if direction == "horizontal":
            cfg["horizontal_offset_pt"] = float(cfg.get("horizontal_offset_pt", 0.0)) + amount
        else:
            cfg["vertical_offset_pt"] = float(cfg.get("vertical_offset_pt", 0.0)) + amount
        return save_margin_config(cfg)

    def _open_position_adjuster(self, carrier: str = "sagawa") -> None:
        if carrier == "seino":
            ensure_seino_placeholder_files()
            win = tk.Toplevel(self)
            win.title("西濃 座標調整")
            win.transient(self)
            win.geometry("520x180")
            ttk.Label(win, text="西濃の座標調整枠を作成しました。").pack(anchor="w", padx=12, pady=(12, 4))
            ttk.Label(win, text=f"個別座標JSON: {seino_config_path()}").pack(anchor="w", padx=12, pady=2)
            ttk.Label(win, text=f"全体余白JSON: {seino_margin_config_path()}").pack(anchor="w", padx=12, pady=2)
            ttk.Label(win, text="背景つきプレビュー描画は佐川実装後に追加します。").pack(anchor="w", padx=12, pady=8)
            return

        win = tk.Toplevel(self)
        win.title("佐川 座標調整")
        win.transient(self)
        win.geometry("790x620")
        status = tk.StringVar(value=f"個別座標: {config_path()} / 全体余白: {margin_config_path()}")

        header = ttk.Frame(win)
        header.pack(fill="x", padx=10, pady=8)
        ttk.Label(header, text="ユーザー用の全体余白調整", font=("", 10, "bold")).pack(anchor="w")
        ttk.Label(header, text="横全体: 右へ + / 左へ -    縦全体: 下へ + / 上へ -").pack(anchor="w")
        margin_row = ttk.Frame(header)
        margin_row.pack(anchor="w", pady=(4, 8))

        def margin_cmd(direction: str, amount: float):
            def _cmd() -> None:
                try:
                    self._shift_margin(direction, amount)
                    self._regenerate_position_preview(status)
                except Exception as e:
                    messagebox.showerror(APP_TITLE, str(e))

            return _cmd

        for caption, direction, amount in (
            ("左へ -5", "horizontal", -5.0),
            ("左へ -1", "horizontal", -1.0),
            ("右へ +1", "horizontal", 1.0),
            ("右へ +5", "horizontal", 5.0),
            ("上へ -5", "vertical", -5.0),
            ("上へ -1", "vertical", -1.0),
            ("下へ +1", "vertical", 1.0),
            ("下へ +5", "vertical", 5.0),
        ):
            ttk.Button(margin_row, text=caption, width=8, command=margin_cmd(direction, amount)).pack(side="left", padx=2)

        ttk.Label(header, text="開発者用の詳細座標", font=("", 10, "bold")).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            header,
            text="横位置: 右へ + / 左へ -    縦位置: 下へ + / 上へ -",
        ).pack(anchor="w")
        ttk.Label(header, text="調整後はプレビューPDF再生成だけを行います。印刷はしません。").pack(anchor="w")

        body = ttk.Frame(win)
        body.pack(fill="both", expand=True, padx=10, pady=4)

        def make_cmd(spec: tuple, direction: str, amount: float):
            def _cmd() -> None:
                try:
                    self._shift_position_target(spec, direction, amount)
                    self._regenerate_position_preview(status)
                except Exception as e:
                    messagebox.showerror(APP_TITLE, str(e))

            return _cmd

        for row, (label, spec) in enumerate(self._position_targets()):
            ttk.Label(body, text=label, width=16).grid(row=row, column=0, sticky="w", pady=2)
            for col, (caption, direction, amount) in enumerate(
                (
                    ("左へ -5", "horizontal", -5.0),
                    ("左へ -1", "horizontal", -1.0),
                    ("右へ +1", "horizontal", 1.0),
                    ("右へ +5", "horizontal", 5.0),
                    ("上へ -5", "vertical", 5.0),
                    ("上へ -1", "vertical", 1.0),
                    ("下へ +1", "vertical", -1.0),
                    ("下へ +5", "vertical", -5.0),
                ),
                start=1,
            ):
                ttk.Button(
                    body,
                    text=caption,
                    width=8,
                    command=make_cmd(spec, direction, amount),
                ).grid(row=row, column=col, padx=2, pady=2)

        footer = ttk.Frame(win)
        footer.pack(fill="x", padx=10, pady=8)
        ttk.Button(
            footer,
            text="背景つきプレビューPDFを開く",
            command=lambda: self._regenerate_position_preview(status),
        ).pack(side="left")
        ttk.Label(footer, textvariable=status).pack(side="left", padx=10)


def main() -> None:
    App().mainloop()


if __name__ == "__main__":
    main()
