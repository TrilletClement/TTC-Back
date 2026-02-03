#!/usr/bin/env python3
import argparse
import os
import sys
from pathlib import Path
from sqlalchemy.engine.url import make_url
from sqlalchemy import text

FASTAPI_DIR = Path(__file__).resolve().parents[1]  # fastapi-server/
if str(FASTAPI_DIR) not in sys.path:
    sys.path.insert(0, str(FASTAPI_DIR))

from app.orm_models.db import Base, engine


def _looks_like_local_db(url_str: str) -> bool:
    try:
        url = make_url(url_str)
    except Exception:
        return False
    host = (url.host or "").lower()
    return host in {"localhost", "127.0.0.1"} or host == ""


def main():
    parser = argparse.ArgumentParser(
        description="Drop + recreate local DB tables, then reimport GTFS (STIB/TEC)."
    )
    parser.add_argument("--yes", action="store_true", help="Confirm destructive DB reset")
    parser.add_argument("--stib", action="store_true", help="Import STIB GTFS after reset")
    parser.add_argument("--tec", action="store_true", help="Import TEC GTFS after reset")
    parser.add_argument(
        "--skip-import",
        action="store_true",
        help="Only rebuild schema; do not import GTFS",
    )
    args = parser.parse_args()

    if not (args.stib or args.tec):
        args.stib = True
        args.tec = True

    db_url = os.environ.get("DATABASE_URL", "")
    if not _looks_like_local_db(db_url):
        raise SystemExit(
            f"Refusing to drop tables on non-local DATABASE_URL: {db_url!r}. "
            "Set DATABASE_URL to a localhost DB or override this script."
        )

    if not args.yes:
        raise SystemExit(
            "This will DROP ALL TABLES and recreate them. Re-run with --yes to confirm."
        )

    print("Dropping all tables (CASCADE)...")
    # Use explicit DROP TABLE ... CASCADE to avoid SQLAlchemy drop ordering issues
    # when cycles exist (e.g., line <-> trip via best_trip foreign keys).
    with engine.begin() as conn:
        for table in list(Base.metadata.sorted_tables)[::-1]:
            if table.schema:
                full_name = f'"{table.schema}"."{table.name}"'
            else:
                full_name = f'"{table.name}"'
            conn.execute(text(f"DROP TABLE IF EXISTS {full_name} CASCADE"))

    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Schema rebuilt.")

    if args.skip_import:
        return

    # Import routines are network-backed (Opendatasoft/GTFS sources).
    from app.routines import stib_import, tec_import

    if args.stib:
        print("\nImporting STIB GTFS...")
        stib_import.import_stib_gtfs()
    if args.tec:
        print("\nImporting TEC GTFS...")
        tec_import.import_tec_gtfs(clean=False)


if __name__ == "__main__":
    main()
