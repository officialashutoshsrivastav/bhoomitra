#!/usr/bin/env python3
"""Seed the database: roles/permissions, default organisation, super administrator,
integrations, and (optionally) the labelled Demo / Synthetic Data set.

Usage:
    python scripts/seed.py             # bootstrap + demo data (if DEMO_DATA_ENABLED)
    python scripts/seed.py --no-demo   # bootstrap only
    python scripts/seed.py --force     # re-run demo seeding even if marked done
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.seed.bootstrap import bootstrap  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-demo", action="store_true", help="skip demo data")
    parser.add_argument("--force", action="store_true", help="re-seed demo data")
    args = parser.parse_args()
    configure_logging()
    db = SessionLocal()
    try:
        bootstrap(db)
        print(json.dumps({"bootstrap": "ok", "superadmin": settings.bootstrap_superadmin_email}))
        if not args.no_demo and settings.demo_data_enabled:
            from app.seed.demo import seed_demo

            print(json.dumps(seed_demo(db, force=args.force), indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
