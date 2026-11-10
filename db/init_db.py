"""Create the schema and optionally load sample data.

Usage:
    python db/init_db.py                 # schema only
    python db/init_db.py --seed          # schema plus companies and about one year of sample prices
    python db/init_db.py --roles         # also create the least-privilege roles
"""
import argparse
import pathlib
from datetime import date, timedelta

import psycopg
from psycopg import sql

from stockplatform import fakedata
from stockplatform.config import env

HERE = pathlib.Path(__file__).parent

UPSERT_COMPANY = """INSERT INTO companies (symbol, name, sector, industry) VALUES (%s, %s, %s, %s)
ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name, sector = EXCLUDED.sector, industry = EXCLUDED.industry"""

UPSERT_PRICE = """INSERT INTO prices (symbol, date, open, high, low, close, adjusted_close, volume)
VALUES (%(symbol)s, %(date)s, %(open)s, %(high)s, %(low)s, %(close)s, %(adjusted_close)s, %(volume)s)
ON CONFLICT (symbol, date) DO UPDATE SET open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low,
close = EXCLUDED.close, adjusted_close = EXCLUDED.adjusted_close, volume = EXCLUDED.volume"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true", help="load companies and sample prices")
    parser.add_argument("--roles", action="store_true", help="create least-privilege roles")
    parser.add_argument("--days", type=int, default=365, help="days of sample history")
    args = parser.parse_args()

    url = env("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is not set")
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute((HERE / "schema.sql").read_text())
        if args.roles:
            conn.execute((HERE / "roles.sql").read_text())
            # Passwords come from the deployment: ROLE_PASSWORD_SVC_READER and so on.
            for role in ("svc_reader", "svc_s6", "svc_s8", "ingestor"):
                password = env(f"ROLE_PASSWORD_{role.upper()}")
                if password:
                    conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
                    print(f"password set for {role}")
        if args.seed:
            end = date.today()
            start = end - timedelta(days=args.days)
            with conn.cursor() as cur:
                cur.executemany(UPSERT_COMPANY, fakedata.ALL_COMPANIES)
                total = 0
                for symbol in fakedata.SYMBOLS:
                    rows = fakedata.generate_prices(symbol, start, end)
                    cur.executemany(UPSERT_PRICE, rows)
                    total += len(rows)
            print(f"seeded {len(fakedata.SYMBOLS)} companies and {total} price rows")
        else:
            print("schema ready")


if __name__ == "__main__":
    main()
