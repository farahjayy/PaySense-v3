"""Download the Berka (PKDD'99) `trans` and `account` tables as CSV (plan P3, task B2).

The data is public: the CTU Relational Repository exposes it on a read-only guest MariaDB account
that its dataset page publishes (https://relational.fel.cvut.cz/dataset/Financial). Research use;
the page states no licence. Berka is a real-transaction *benchmark* for Engine 1 only (ADR D-25),
never a model of the target population.

    cd backend && uv run python ../data/external/berka/download.py

Raw files go to `raw/` next to this script, which is gitignored. Needs the `ml` dependency group
(pymysql). Prints a checksum per file so a rerun can be compared.
"""

import csv
import hashlib
import sys
from pathlib import Path

import pymysql

HOST = "relational.fel.cvut.cz"
PORT = 3306
USER = "guest"
PASSWORD = "ctu-relational"  # noqa: S105 - the published read-only guest credential
DATABASE = "financial"
TABLES = {"account": "account_id", "trans": "trans_id"}  # table -> primary key
CHUNK = 50_000
TIMEOUT_SECONDS = 60
RAW = Path(__file__).resolve().parent / "raw"


def export(table: str, key: str, connection: pymysql.connections.Connection) -> Path:
    """Keyset-paginated, because the server cancels any single statement that runs too long."""
    path = RAW / f"{table}.csv"
    with connection.cursor() as cursor, path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        last = None
        while True:
            where = "" if last is None else f"WHERE `{key}` > {int(last)}"
            cursor.execute(
                f"SELECT * FROM `{table}` {where} ORDER BY `{key}` LIMIT {CHUNK}"  # noqa: S608
            )
            rows = cursor.fetchall()
            if last is None:
                writer.writerow([column[0] for column in cursor.description])
            if not rows:
                return path
            key_index = [column[0] for column in cursor.description].index(key)
            writer.writerows(rows)
            last = rows[-1][key_index]


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    try:
        connection = pymysql.connect(
            host=HOST,
            port=PORT,
            user=USER,
            password=PASSWORD,
            database=DATABASE,
            connect_timeout=TIMEOUT_SECONDS,
            read_timeout=TIMEOUT_SECONDS,
        )
    except pymysql.err.Error as error:
        print(f"could not reach {HOST}:{PORT}: {error}", file=sys.stderr)  # noqa: T201
        return 1
    with connection:
        for table, key in TABLES.items():
            path = export(table, key, connection)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"{path.name}  {path.stat().st_size} bytes  sha256 {digest}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
