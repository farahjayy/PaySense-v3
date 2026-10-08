"""Download the Berka (PKDD'99) `trans` and `account` tables as CSV (plan P3, task B2).

The data is public: the CTU Relational Repository exposes it on a read-only guest MariaDB account
that its dataset page publishes (https://relational.fel.cvut.cz/dataset/Financial). Research use;
the page states no licence. Berka is a real-transaction *benchmark* for Engine 1 only (ADR D-25),
never a model of the target population.

    cd backend && uv run python ../data/external/berka/download.py

Raw files go to `raw/` next to this script, which is gitignored. Needs the `ml` dependency group
(pymysql). Each table is written to a `.part` file, checked against the server's row count and the
checksum recorded when the dataset was first fetched, and only then moved into place, so an
interrupted download can never leave a short file that looks complete. The connection is not
encrypted; the data is public and the credential is the published read-only guest account.
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
SHA256 = {  # recorded when the tables were first fetched; the dataset is static
    "account": "7b73fbf635edee867f48de2def090140631769e28898b822cd989504714ac95f",
    "trans": "bc71313c967339139c54259d7e4b0c3f5e902b922c27b44d2ec55968d42f3281",
}
CHUNK = 50_000
TIMEOUT_SECONDS = 60
RAW = Path(__file__).resolve().parent / "raw"


def export(table: str, key: str, connection: pymysql.connections.Connection) -> int:
    """Keyset-paginated, because the server cancels any single statement that runs too long.
    Returns the number of data rows written to `<table>.csv.part`."""
    part = RAW / f"{table}.csv.part"
    written = 0
    with connection.cursor() as cursor, part.open("w", encoding="utf-8", newline="") as handle:
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
                return written
            key_index = [column[0] for column in cursor.description].index(key)
            writer.writerows(rows)
            written += len(rows)
            last = rows[-1][key_index]


def server_count(table: str, connection: pymysql.connections.Connection) -> int:
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM `{table}`")  # noqa: S608 - constant table names
        return int(cursor.fetchone()[0])


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
            try:
                written = export(table, key, connection)
                expected = server_count(table, connection)
            except pymysql.err.Error as error:
                print(f"{table}: download interrupted: {error}", file=sys.stderr)  # noqa: T201
                return 1
            part = RAW / f"{table}.csv.part"
            digest = hashlib.sha256(part.read_bytes()).hexdigest()
            if written != expected or digest != SHA256[table]:
                print(  # noqa: T201
                    f"{table}: got {written} rows (server says {expected}), sha256 {digest}; "
                    f"expected {SHA256[table]}. Not installed.",
                    file=sys.stderr,
                )
                return 1
            part.replace(RAW / f"{table}.csv")
            print(f"{table}.csv  {written} rows  sha256 {digest}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
