"""Inspect the booking mart and run SQL without extra dependencies.

Examples (from the project root):
    python scripts/query_duckdb.py
    python scripts/query_duckdb.py --schema fact_booking
    python scripts/query_duckdb.py --file sql/analytics.sql
    python scripts/query_duckdb.py --sql "SELECT * FROM dim_hotel"
"""

import argparse
from pathlib import Path
import sys

import duckdb


ROOT = Path(__file__).resolve().parents[1]


def show_query(connection, sql, max_rows):
    """Parse SQL properly, including semicolons inside strings and comments."""
    statements = connection.extract_statements(sql)
    if not statements:
        raise ValueError("SQL is empty or contains only comments")
    for number, statement in enumerate(statements, 1):
        if len(statements) > 1:
            print(f"\n--- Statement {number}/{len(statements)} ---", flush=True)
        result = connection.sql(statement.query)
        if result is None:
            print("OK", flush=True)
        else:
            result.show(max_rows=max_rows, max_width=160)


def main():
    # DuckDB prints Unicode table borders, including when output is redirected on Windows.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", type=Path, default=ROOT / "data/booking.duckdb",
                        help="Database path (default: project data/booking.duckdb)")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--tables", action="store_true", help="List tables")
    actions.add_argument("--schema", nargs="?", const="*", metavar="TABLE",
                         help="Describe one table, or all tables when TABLE is omitted")
    actions.add_argument("--file", type=Path, help="Run all statements in a UTF-8 SQL file")
    actions.add_argument("--sql", help="Run SQL provided as a command-line argument")
    parser.add_argument("--max-rows", type=int, default=30, help="Rows to display per result (default: 30)")
    parser.add_argument("--write", action="store_true", help="Allow database changes; default is read-only")
    args = parser.parse_args()
    if args.max_rows < 1:
        parser.error("--max-rows must be positive")
    if not args.database.is_file():
        parser.error(f"Database not found: {args.database}. Run python etl/load_duckdb.py first.")

    try:
        with duckdb.connect(str(args.database), read_only=not args.write) as connection:
            print(f"Database: {args.database.resolve()} ({'read-write' if args.write else 'read-only'})",
                  flush=True)
            if args.tables:
                show_query(connection, "SHOW TABLES", args.max_rows)
            elif args.file is not None:
                show_query(connection, args.file.read_text(encoding="utf-8-sig"), args.max_rows)
            elif args.sql is not None:
                show_query(connection, args.sql, args.max_rows)
            else:
                tables = ([args.schema] if args.schema not in (None, "*") else
                          [row[0] for row in connection.execute("SHOW TABLES").fetchall()])
                if not tables:
                    print("No tables found.")
                for table in tables:
                    print(f"\n--- {table} ---", flush=True)
                    identifier = '"' + table.replace('"', '""') + '"'
                    show_query(connection, f"DESCRIBE {identifier}", args.max_rows)
    except (duckdb.Error, OSError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
