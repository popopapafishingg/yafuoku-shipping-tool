# -*- coding: utf-8 -*-
"""sagawa_form_scan.pdf から SagawaLayout 座標を推定して templates に保存。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.auto_calibrate_sagawa import calibrate


def main() -> int:
    cal = calibrate()
    out = ROOT / "templates" / "sagawa_calibration.json"
    out.write_text(
        json.dumps({**cal, "rotation": "raw"}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(cal, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
