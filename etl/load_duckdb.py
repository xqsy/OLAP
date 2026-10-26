"""Rebuild the booking mart from H1/H2 and save the SQL check results."""

import csv
import json
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data" / "booking.duckdb"
REPORT = ROOT / "data" / "checks_duckdb.txt"
MONTHS = {name: n for n, name in enumerate(
    "January February March April May June July August September October November December".split(), 1
)}
FIELDS = {
    "country_code": "Country", "market_segment": "MarketSegment",
    "distribution_channel": "DistributionChannel",
    "reserved_room_type": "ReservedRoomType", "assigned_room_type": "AssignedRoomType",
    "reservation_status": "ReservationStatus", "is_canceled": "IsCanceled",
    "lead_time": "LeadTime", "stays_in_weekend_nights": "StaysInWeekendNights",
    "stays_in_week_nights": "StaysInWeekNights", "adults": "Adults",
    "children": "Children", "babies": "Babies", "adr": "ADR",
}


def normalize(value):
    value = value.strip()
    return None if not value or value.upper() in {"NULL", "NA", "N/A"} else value


def validate_row(row):
    """Validate source values before they can abort the SQL transaction."""
    if None in row or any(value is None for value in row.values()):
        raise ValueError("CSV record has a different number of columns than the header")
    row = {key: normalize(value) for key, value in row.items()}
    try:
        arrival = date(int(row["ArrivalDateYear"]), MONTHS[row["ArrivalDateMonth"]],
                       int(row["ArrivalDateDayOfMonth"]))
        status = date.fromisoformat(row["ReservationStatusDate"])
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        raise ValueError(f"Invalid or missing booking date: {exc}") from exc
    if min(arrival, status) < date(2000, 1, 1):
        raise ValueError("Booking dates must be on or after 2000-01-01")
    if row["ReservationStatus"] not in {"Check-Out", "Canceled", "No-Show"}:
        raise ValueError("ReservationStatus must be Check-Out, Canceled or No-Show")
    for field in ("IsCanceled", "LeadTime", "StaysInWeekendNights", "StaysInWeekNights",
                  "Adults", "Children", "Babies"):
        value = row[field]
        if value is None and field == "Children":
            continue
        try:
            number = int(value)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{field}: expected an integer, got {value!r}") from exc
        maximum = 1 if field == "IsCanceled" else 2147483647
        if not 0 <= number <= maximum:
            raise ValueError(f"{field}: value outside 0..{maximum}")
        row[field] = str(number)
    if row["ADR"] is not None:
        try:
            with localcontext() as ctx:
                ctx.prec = 32
                amount = Decimal(row["ADR"])
                if not amount.is_finite() or abs(amount) >= Decimal("10000000000000000"):
                    raise InvalidOperation
                amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if abs(amount) >= Decimal("10000000000000000"):
                    raise InvalidOperation
        except InvalidOperation as exc:
            raise ValueError("ADR: value does not fit DECIMAL(18,2)") from exc
        row["ADR"] = str(amount)
    return arrival, status, row


def prepare_csv(path, rejected_path):
    """Keep source record numbers, stream rejects to disk, return per-file counts."""
    counts = []
    with path.open("w", encoding="utf-8", newline="") as output, rejected_path.open(
            "w", encoding="utf-8", newline="") as rejected:
        writer = csv.writer(output)
        rejects = csv.writer(rejected)
        rejects.writerow(["source_file", "source_row_number", "source_line_number", "reason", "raw_record"])
        writer.writerow(["hotel_id", "hotel_code", "source_file", "source_row_number",
                         "arrival_date", "status_date", *FIELDS])
        for hotel_id in (1, 2):
            source = ROOT / "data" / "raw" / f"H{hotel_id}.csv"
            with source.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle, strict=True)
                required = set(FIELDS.values()) | {
                    "ArrivalDateYear", "ArrivalDateMonth", "ArrivalDateDayOfMonth",
                    "ReservationStatusDate",
                }
                if not required.issubset(reader.fieldnames or []):
                    raise ValueError(f"Missing columns in {source}")
                total = accepted = 0
                while True:
                    line_number = reader.reader.line_num + 1
                    row = None
                    try:
                        row = next(reader)
                    except StopIteration:
                        break
                    except csv.Error as exc:
                        total += 1
                        rejects.writerow([source.name, total, line_number, str(exc), ""])
                        continue
                    total += 1
                    try:
                        arrival, status, clean = validate_row(row)
                    except ValueError as exc:
                        rejects.writerow([source.name, total, line_number, str(exc),
                                          json.dumps(row, ensure_ascii=False)])
                        continue
                    writer.writerow([hotel_id, f"H{hotel_id}", source.name, total,
                                     arrival, status, *[clean[key] for key in FIELDS.values()]])
                    accepted += 1
                counts.append((source.name, total, accepted, total - accepted))
    return counts


LOAD_SQL = """
INSERT INTO dim_date VALUES (0, NULL, NULL, NULL, NULL, NULL);
INSERT INTO dim_date
SELECT year(d) * 10000 + month(d) * 100 + day(d), d,
       year(d), quarter(d), month(d), isodow(d)
FROM generate_series(
    (SELECT min(d) FROM (SELECT arrival_date AS d FROM raw_booking
                         UNION ALL SELECT status_date FROM raw_booking)),
    (SELECT max(d) FROM (SELECT arrival_date AS d FROM raw_booking
                         UNION ALL SELECT status_date FROM raw_booking)),
    INTERVAL 1 DAY) AS calendar(d);

INSERT INTO dim_hotel VALUES (0, 0, 'UNKNOWN', 'UNKNOWN', DATE '0001-01-01', NULL, true);
-- There is no source history: initial type applies to the whole source period.
INSERT INTO dim_hotel
SELECT hotel_id, hotel_id, hotel_code,
       CASE hotel_id WHEN 1 THEN 'Resort Hotel' ELSE 'City Hotel' END,
       coalesce(min(arrival_date), DATE '0001-01-01'), NULL, true
FROM raw_booking GROUP BY hotel_id, hotel_code;

INSERT INTO dim_country VALUES (0, 'UNKNOWN');
INSERT INTO dim_country
SELECT row_number() OVER (ORDER BY country_code), country_code
FROM (SELECT DISTINCT country_code FROM raw_booking
      WHERE country_code IS NOT NULL AND country_code <> 'UNKNOWN');

INSERT INTO dim_channel
SELECT row_number() OVER (ORDER BY market_segment, distribution_channel) - 1,
       market_segment, distribution_channel
FROM (SELECT coalesce(market_segment, 'UNKNOWN') AS market_segment,
             coalesce(distribution_channel, 'UNKNOWN') AS distribution_channel FROM raw_booking
      UNION SELECT 'UNKNOWN', 'UNKNOWN');

INSERT INTO dim_room_type
SELECT row_number() OVER (ORDER BY hotel_id, room_type_code) - 1,
       hotel_id, room_type_code
FROM (SELECT hotel_id, coalesce(reserved_room_type, 'UNKNOWN') AS room_type_code FROM raw_booking
      UNION SELECT hotel_id, coalesce(assigned_room_type, 'UNKNOWN') FROM raw_booking
      UNION SELECT hotel_id, 'UNKNOWN' FROM raw_booking
      UNION SELECT 0, 'UNKNOWN');

INSERT INTO fact_booking
SELECT r.hotel_code || ':' || r.source_row_number, h.hotel_sk,
       coalesce(year(r.arrival_date)*10000 + month(r.arrival_date)*100 + day(r.arrival_date), 0),
       coalesce(year(r.status_date)*10000 + month(r.status_date)*100 + day(r.status_date), 0),
       c.country_id, ch.channel_id, rr.room_type_id, ar.room_type_id,
       r.reservation_status, r.is_canceled::SMALLINT, r.lead_time::INTEGER,
       r.stays_in_weekend_nights::INTEGER, r.stays_in_week_nights::INTEGER,
       r.adults::INTEGER, r.children::INTEGER, r.babies::INTEGER, r.adr::DECIMAL(18,2),
       r.source_file, r.source_row_number
FROM raw_booking r
JOIN dim_hotel h ON r.hotel_id = h.hotel_id
    AND ((r.arrival_date IS NULL AND h.is_current)
         OR (r.arrival_date >= h.valid_from
             AND (r.arrival_date < h.valid_to OR h.valid_to IS NULL)))
JOIN dim_country c ON c.country_code = coalesce(r.country_code, 'UNKNOWN')
JOIN dim_channel ch ON ch.market_segment = coalesce(r.market_segment, 'UNKNOWN')
    AND ch.distribution_channel = coalesce(r.distribution_channel, 'UNKNOWN')
JOIN dim_room_type rr ON rr.hotel_id = h.hotel_id
    AND rr.room_type_code = coalesce(r.reserved_room_type, 'UNKNOWN')
JOIN dim_room_type ar ON ar.hotel_id = h.hotel_id
    AND ar.room_type_code = coalesce(r.assigned_room_type, 'UNKNOWN');
"""


def load():
    with TemporaryDirectory(prefix="olap_duckdb_") as temporary:
        normalized = Path(temporary) / "normalized.csv"
        rejected_path = REPORT.with_name("rejected_duckdb.csv")
        counts = prepare_csv(normalized, rejected_path)
        with duckdb.connect(str(DATABASE)) as con:
            con.execute("""
                CREATE TEMP TABLE raw_booking AS
                SELECT * REPLACE (hotel_id::INTEGER AS hotel_id,
                    source_row_number::INTEGER AS source_row_number,
                    arrival_date::DATE AS arrival_date, status_date::DATE AS status_date)
                FROM read_csv(?, header=true, all_varchar=true, nullstr='')
            """, [str(normalized)])
            con.execute("BEGIN TRANSACTION")
            try:
                for table in ("fact_booking", "dim_room_type", "dim_channel",
                              "dim_country", "dim_hotel", "dim_date"):
                    con.execute(f"DROP TABLE IF EXISTS {table}")
                con.execute((ROOT / "sql" / "ddl_duckdb.sql").read_text(encoding="utf-8"))
                con.execute(LOAD_SQL)
                checks = con.execute((ROOT / "sql" / "check_duckdb.sql").read_text(
                    encoding="utf-8")).fetchall()
                failures = [name for name, actual, expected in checks
                            if expected is not None and actual != expected]
                run_time = datetime.now(timezone(timedelta(hours=3))).isoformat(timespec="seconds")
                lines = ["DuckDB booking mart checks", f"Run (UTC+03:00): {run_time}",
                         f"DuckDB: {duckdb.__version__}", "",
                         "Source records (read / accepted / rejected):"]
                lines.extend(f"{name}: {total} / {accepted} / {rejected}"
                             for name, total, accepted, rejected in counts)
                lines.extend([f"Rejected records: {rejected_path}", "",
                              f"{'Check':<46} {'Actual':>10} {'Expected':>10}  Result"])
                for name, actual, expected in checks:
                    result = "INFO" if expected is None else ("OK" if actual == expected else "FAIL")
                    lines.append(f"{name:<46} {actual:>10} {str(expected) if expected is not None else '-':>10}  {result}")
                lines.extend(["", "FAIL: transaction rolled back" if failures else
                              "PASS: all checks passed for accepted records"])
                if any(rejected for _, _, _, rejected in counts):
                    lines.append("WARNING: rejected source records; see rejected_duckdb.csv")
                if failures:
                    con.execute("ROLLBACK")
                else:
                    con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
            REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
            print("\n".join(lines))
            if failures:
                raise SystemExit(1)


def main():
    try:
        load()
    except Exception as exc:
        REPORT.write_text(f"FAIL: load aborted\n{type(exc).__name__}: {exc}\n", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
