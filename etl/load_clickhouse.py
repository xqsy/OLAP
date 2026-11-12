"""Fully refresh six ClickHouse tables from DuckDB and reconcile the mart."""

import argparse
import csv
import io
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

import duckdb


ROOT = Path(__file__).resolve().parents[1]
TABLES = (
    "dim_date", "dim_hotel", "dim_country", "dim_channel", "dim_room_type",
    "fact_booking",
)
BATCH_SIZE = 20000


class ClickHouse:
    def __init__(self, url, database):
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
            raise ValueError("--url must be an HTTP(S) endpoint without query or fragment")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database):
            raise ValueError("--database must be a simple SQL identifier")
        self.url = url.rstrip("/")
        self.database = database

    def execute(self, sql, payload=None, use_database=True):
        params = {"wait_end_of_query": "1"}
        if use_database:
            params["database"] = self.database
        if payload is not None:
            params["query"] = sql
        request = Request(
            self.url + "/?" + urlencode(params),
            data=sql.encode("utf-8") if payload is None else payload,
            headers={
                "X-ClickHouse-User": os.environ.get("CLICKHOUSE_USER", "default"),
                "X-ClickHouse-Key": os.environ.get("CLICKHOUSE_PASSWORD", ""),
                "Content-Type": "application/octet-stream",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                return response.read().decode("utf-8").strip()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ClickHouse HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"ClickHouse connection failed: {exc.reason}") from exc

    def scalar(self, sql):
        return self.execute(sql.rstrip().rstrip(";") + " FORMAT TabSeparated")


def copy_table(source, target, table):
    cursor = source.execute(f"SELECT * FROM {table}")
    columns = [column[0] for column in cursor.description]
    column_sql = ", ".join(f"`{column}`" for column in columns)
    inserted = 0
    while rows := cursor.fetchmany(BATCH_SIZE):
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(columns)
        # Decimal is serialized directly as text, never through float.
        # ClickHouse CSV uses \N for SQL NULL, including the unknown date row.
        writer.writerows([
            [r"\N" if value is None else str(value) for value in row]
            for row in rows
        ])
        target.execute(
            f"INSERT INTO {table} ({column_sql}) FORMAT CSVWithNames",
            payload=output.getvalue().encode("utf-8"),
        )
        inserted += len(rows)
    return inserted


def reconcile(source, target, log):
    canonical = (ROOT / "sql" / "canonical_metric.sql").read_text(encoding="utf-8")
    checks = [(f"{table} rows", f"SELECT COUNT(*) FROM {table}") for table in TABLES]
    checks += [
        ("canonical completed bookings", canonical),
        ("sum of completed booking indicators", """
            SELECT COALESCE(SUM(CASE WHEN reservation_status = 'Check-Out' THEN 1 ELSE 0 END), 0)
            FROM fact_booking
        """),
        ("duplicate booking IDs", "SELECT COUNT(*) - COUNT(DISTINCT booking_id) FROM fact_booking"),
        ("NULL children", "SELECT COUNT(*) FROM fact_booking WHERE children IS NULL"),
        ("NULL adr", "SELECT COUNT(*) FROM fact_booking WHERE adr IS NULL"),
        ("unknown calendar rows", "SELECT COUNT(*) FROM dim_date WHERE date_id = 0 AND full_date IS NULL"),
    ]
    log("")
    log(f"{'Check':<38} {'DuckDB':>12} {'ClickHouse':>12}  Result")
    passed = True
    for name, sql in checks:
        expected = str(source.execute(sql).fetchone()[0])
        actual = target.scalar(sql)
        ok = actual == expected and (name != "duplicate booking IDs" or actual == "0")
        passed = passed and ok
        log(f"{name:<38} {expected:>12} {actual:>12}  {'OK' if ok else 'FAIL'}")
    adr_type = target.scalar("""
        SELECT type FROM system.columns
        WHERE database = currentDatabase() AND table = 'fact_booking' AND name = 'adr'
    """)
    decimal_ok = adr_type == "Nullable(Decimal(18, 2))"
    log(f"ClickHouse adr type: {adr_type}  {'OK' if decimal_ok else 'FAIL'}")
    return passed and decimal_ok


def refresh_summary(target, log):
    sql = (ROOT / "sql/aggregate_booking_daily.sql").read_text(encoding="utf-8")
    for statement in sql.split(";"):
        if statement.strip():
            target.execute(statement)
    mismatches = target.scalar((ROOT / "sql/check_aggregate.sql").read_text(encoding="utf-8"))
    log(f"Daily summary mismatched day/hotel groups: {mismatches}")
    passed = mismatches == "0"
    for name, condition in (("all dates", "1"),
                            ("September 2016", "arrival_date_id >= 20160901 AND arrival_date_id < 20161001")):
        detail = target.scalar(
            "SELECT count() FROM fact_booking WHERE reservation_status = 'Check-Out' AND " + condition
        )
        summary = target.scalar(
            "SELECT coalesce(sum(completed_booking_count), 0) FROM agg_booking_daily WHERE " + condition
        )
        ok = detail == summary
        passed = passed and ok
        log(f"Summary {name}: detail={detail}; summary={summary}; {'OK' if ok else 'FAIL'}")
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duckdb", type=Path, default=ROOT / "data" / "booking.duckdb")
    parser.add_argument("--url", default=os.environ.get("CLICKHOUSE_URL", "http://localhost:8123"))
    parser.add_argument("--database", default="booking_dw", help="Target database; its six mart tables are fully refreshed")
    parser.add_argument("--report", type=Path, default=ROOT / "data" / "checks_clickhouse.txt")
    args = parser.parse_args()
    lines = []

    def log(message):
        lines.append(message)
        print(message, flush=True)

    result = 1
    try:
        log("DuckDB -> ClickHouse booking mart full refresh")
        log(f"Run (UTC): {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
        log(f"Source: {args.duckdb.resolve()}")
        log(f"Target database: {args.database}")
        if not args.duckdb.is_file():
            raise FileNotFoundError(f"DuckDB database not found: {args.duckdb}")
        target = ClickHouse(args.url, args.database)
        with duckdb.connect(str(args.duckdb), read_only=True) as source:
            # Check all source tables before clearing anything in ClickHouse.
            for table in TABLES:
                source.execute(f"SELECT * FROM {table} LIMIT 0")
            log(f"ClickHouse version: {target.execute('SELECT version()', use_database=False)}")
            target.execute(f"CREATE DATABASE IF NOT EXISTS `{args.database}`", use_database=False)
            ddl = (ROOT / "sql" / "ddl_clickhouse.sql").read_text(encoding="utf-8")
            for statement in ddl.split(";"):
                if statement.strip():
                    target.execute(statement)
            log("Mode: TRUNCATE all six mart tables, then INSERT from DuckDB")
            for table in TABLES:
                target.execute(f"TRUNCATE TABLE {table}")
            for table in TABLES:
                log(f"Loaded {table}: {copy_table(source, target, table)} rows")
            if reconcile(source, target, log) and refresh_summary(target, log):
                log("PASS: all reconciliation checks passed")
                result = 0
            else:
                log("FAIL: reconciliation mismatch")
    except (OSError, RuntimeError, ValueError, duckdb.Error) as exc:
        log(f"FAIL: {exc}")
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    sys.exit(main())
