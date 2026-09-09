#!/usr/bin/env python3
"""Load real administrative boundaries from geoBoundaries (CC BY 4.0).

Requires network access. ADM1 = states/UTs, ADM2 = districts.
Usage: python scripts/load_boundaries.py --adm ADM1 [--adm ADM2] [--iso3 IND] [--replace]
Attribution: geoBoundaries — Runfola D, et al. (2020) PLoS ONE 15(4): e0231866.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.database import SessionLocal  # noqa: E402
from app.integrations.service import load_geoboundaries  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--iso3", default="IND")
    p.add_argument("--adm", action="append", default=None, help="ADM0/ADM1/ADM2 (repeatable)")
    p.add_argument("--replace", action="store_true")
    a = p.parse_args()
    db = SessionLocal()
    try:
        for adm in a.adm or ["ADM1"]:
            print(json.dumps(load_geoboundaries(db, a.iso3, adm, a.replace)))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
