# -*- coding: utf-8 -*-
from parser import parse_shipping_text
from item_parser import (
    extract_delivery_time,
    extract_insurance_requested,
    parse_auction_product,
)
from address_utils import split_address_company
from excel_writer import write_confirmation_text
from models import LabelPrintData


SAMPLES = [
    {
        "name": "standard_labels",
        "text": """お届け先情報
氏名：山田 太郎
郵便番号：123-4567
住所：東京都千代田区丸の内1-1-1
電話番号：090-1234-5678

商品名：テスト商品 A
オークションID：x123456789
落札数量：2
時間指定：18時-20時
保険：あり""",
    },
    {
        "name": "line_block",
        "text": """お届け先
〒530 0001
大阪府大阪市北区梅田3丁目1番1号
佐藤 花子 様
TEL 080 1111 2222

商品タイトル
中古カメラ レンズセット
管理番号：m987654321
個数 3個
お届け希望時間：午前中
運送保険：希望""",
    },
    {
        "name": "ocr_noise",
        "text": """お 届 け 先 情 報
お名前-鈴木一郎
お届け先住所
神奈川県横浜市西区高島2-16-1
〒220－0011
携帯電話: 070ー3333ー4444

タイトル: ノートPC 13インチ
オークション ID # a765432109
数量 ×2
希望時間帯 19:00〜21:00
輸送 保険 : 加入""",
    },
    {
        "name": "phone_line_not_company",
        "text": """株式会社ビッグエー　吉田豊
住所
〒2240011
神奈川県 横浜市都筑区 牛久保町1697-8
08055555555

商品名: 実データ確認商品
オークションID: x555555555
個数: 1
時間指定: 18時-20時
保険: あり""",
    },
]


def main() -> None:
    for sample in SAMPLES:
        text = sample["text"]
        ship = parse_shipping_text(text)
        aid, product, qty = parse_auction_product(text)
        delivery_time = extract_delivery_time(text)
        insurance = extract_insurance_requested(text)
        result = {
            "sample": sample["name"],
            "お届け先": bool(ship.name and ship.address),
            "商品名": product,
            "オークションID": aid,
            "保険": insurance,
            "時間指定": delivery_time,
            "個数": qty,
        }
        missing = [k for k, v in result.items() if k != "sample" and (v in ("", None, False))]
        print(result)
        if missing:
            raise AssertionError(f"{sample['name']} missing: {missing}")
        addr, company = split_address_company(ship.address)
        if sample["name"] == "phone_line_not_company":
            if "08055555555" in addr or "08055555555" in company:
                raise AssertionError("phone number leaked into address/company")
            if addr.endswith("08") or company == "08" or " 08" in addr:
                raise AssertionError("phone prefix leaked into address/company")
            if addr.endswith("0") or company in ("0", "08", "080"):
                raise AssertionError("phone fragment leaked into address/company")
            data = LabelPrintData(
                recipient=ship,
                auction_id=aid,
                product_name=product,
                quantity=qty,
                delivery_time=delivery_time,
                insurance_enabled=bool(insurance),
            )
            path = write_confirmation_text(data)
            lines = [
                line
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if ": " in line
            ]
            expected_order = [
                "宛先氏名",
                "宛先郵便番号",
                "宛先住所",
                "宛先電話番号",
                "商品名",
                "オークションID",
                "個数",
                "時間指定",
                "保険有無",
                "保険金額",
                "依頼主郵便番号",
                "依頼主住所",
                "依頼主名",
                "依頼主電話番号",
            ]
            got_order = [line.split(": ", 1)[0] for line in lines]
            if got_order != expected_order:
                raise AssertionError(f"confirmation text order mismatch: {got_order}")
            address_line = next(line for line in lines if line.startswith("宛先住所: "))
            if address_line.endswith(" 0") or address_line.endswith(" 08") or address_line.endswith(" 080"):
                raise AssertionError("phone fragment leaked into confirmation text address")


if __name__ == "__main__":
    main()
