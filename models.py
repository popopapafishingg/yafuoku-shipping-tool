# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field

from parser import ShippingInfo


@dataclass
class SenderInfo:
    zip_code: str = ""
    address: str = ""
    name: str = ""
    phone: str = ""


@dataclass
class LabelPrintData:
    """印刷・Excel出力に使うデータ一式。"""

    recipient: ShippingInfo
    auction_id: str = ""
    product_name: str = ""
    quantity: int = 1
    delivery_time: str = ""
    sender: SenderInfo = field(default_factory=SenderInfo)
    print_sender: bool = False
    insurance_enabled: bool = True
    insurance_amount: int = 50000
