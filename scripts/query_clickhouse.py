"""Run read-only SQL in the project's ClickHouse container."""

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="Run all statements in a UTF-8 SQL file")
    source.add_argument("--sql", help="Run SQL provided as a command-line argument")
    args = parser.parse_args()

    try:
        sql = args.file.read_text(encoding="utf-8-sig") if args.file is not None else args.sql
        if not sql.strip():
            parser.error("SQL is empty")

        # Let ClickHouse parse statement boundaries, including semicolons in literals.
        result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "clickhouse", "clickhouse-client",
                "--database", "booking_dw", "--readonly", "1", "--multiquery",
                "--format", "TabSeparatedWithNames",
            ],
            cwd=ROOT,
            input=sql.encode("utf-8"),
        )
        return result.returncode
    except (OSError, UnicodeError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    sys.exit(main())
