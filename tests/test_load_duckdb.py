import contextlib
import csv
import importlib.util
import io
from pathlib import Path
import shutil
import tempfile
import unittest

import duckdb


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loader", ROOT / "etl/load_duckdb.py")
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="olap_test_")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "data/raw").mkdir(parents=True)
        shutil.copytree(ROOT / "sql", self.root / "sql")
        previous = loader.ROOT, loader.DATABASE, loader.REPORT
        self.addCleanup(self.restore_paths, previous)
        loader.ROOT = self.root
        loader.DATABASE = self.root / "data/test.duckdb"
        loader.REPORT = self.root / "data/checks.txt"
        self.row = dict.fromkeys(loader.FIELDS.values(), "0")
        self.row.update(Country="PRT", MarketSegment="Direct", DistributionChannel="Direct",
                        ReservedRoomType="A", AssignedRoomType="A", ReservationStatus="Check-Out",
                        ArrivalDateYear="2015", ArrivalDateMonth="July", ArrivalDateDayOfMonth="1",
                        ReservationStatusDate="2015-07-01", Adults="2", Children="NA", ADR="-6.38")

    @staticmethod
    def restore_paths(paths):
        loader.ROOT, loader.DATABASE, loader.REPORT = paths

    def sources(self, rows):
        for hotel, records in ((1, rows), (2, [self.row])):
            with (self.root / f"data/raw/H{hotel}.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(self.row))
                writer.writeheader()
                writer.writerows(records)

    def run_load(self):
        with contextlib.redirect_stdout(io.StringIO()):
            loader.main()

    def facts(self):
        with duckdb.connect(str(loader.DATABASE), read_only=True) as con:
            return con.execute("SELECT booking_id, children, adr FROM fact_booking ORDER BY booking_id").fetchall()

    def rejects(self):
        with (self.root / "data/rejected_duckdb.csv").open(encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    def test_valid_records_preserve_duplicates_nulls_and_negative_adr(self):
        self.sources([self.row, self.row])
        self.run_load()
        facts = self.facts()
        self.assertEqual([r[0] for r in facts], ["H1:1", "H1:2", "H2:1"])
        self.assertIsNone(facts[0][1])
        self.assertEqual(str(facts[0][2]), "-6.38")
        self.assertEqual(self.rejects(), [])
        self.run_load()
        self.assertEqual(self.facts(), facts)

    def test_bad_records_do_not_block_following_valid_record(self):
        changes = [
            {"ReservationStatusDate": "broken"}, {"ArrivalDateMonth": "Unknown"},
            {"Adults": "broken"}, {"Adults": "-1"}, {"Adults": "2147483648"},
            {"IsCanceled": "2"}, {"ReservationStatus": "invalid"}, {"LeadTime": "NULL"},
            {"ArrivalDateYear": "1999"}, {"ADR": "NaN"}, {"ADR": "1e100"},
            {"ADR": "9999999999999999.999"}, {"Children": "-1"},
        ]
        rows = [dict(self.row, **change) for change in changes]
        self.sources([self.row, *rows, self.row])
        self.run_load()
        self.assertEqual([r[0] for r in self.facts()], ["H1:1", "H1:15", "H2:1"])
        rejects = self.rejects()
        self.assertEqual(len(rejects), len(changes))
        self.assertEqual([int(r["source_row_number"]) for r in rejects], list(range(2, 15)))
        self.assertTrue(all(r["reason"] and r["raw_record"] for r in rejects))
        report = loader.REPORT.read_text()
        self.assertIn("H1.csv: 15 / 2 / 13", report)
        self.assertIn("WARNING", report)

    def test_short_extra_and_malformed_csv_records(self):
        self.sources([self.row] * 4)
        path = self.root / "data/raw/H1.csv"
        lines = path.read_text().splitlines()
        lines[1] = ",".join(lines[1].split(",")[:-1])
        lines[2] += ",extra"
        lines[3] = '"bad"trailing,' + lines[3]
        path.write_text("\n".join(lines) + "\n")
        self.run_load()
        self.assertEqual([r[0] for r in self.facts()], ["H1:4", "H2:1"])
        self.assertEqual(len(self.rejects()), 3)
        self.assertEqual([r["source_line_number"] for r in self.rejects()], ["2", "3", "4"])

    def test_all_records_rejected(self):
        self.sources([dict(self.row, Adults="bad")])
        path = self.root / "data/raw/H2.csv"
        path.write_text(path.read_text().replace("Check-Out", "invalid"))
        self.run_load()
        self.assertEqual(self.facts(), [])
        self.assertEqual(len(self.rejects()), 2)
        self.assertIn("PASS", loader.REPORT.read_text())

    def test_date_overflow_is_rejected_and_multiline_csv_is_preserved(self):
        self.sources([dict(self.row, ArrivalDateYear="999999999999999999999"),
                      dict(self.row, MarketSegment="Direct\nWeb")])
        self.run_load()
        self.assertEqual([r[0] for r in self.facts()], ["H1:2", "H2:1"])
        self.assertEqual(len(self.rejects()), 1)

    def test_fatal_error_preserves_database_and_replaces_old_pass(self):
        self.sources([self.row])
        self.run_load()
        original = self.facts()
        (self.root / "sql/ddl_duckdb.sql").write_text("INVALID SQL")
        with self.assertRaises(duckdb.Error):
            self.run_load()
        self.assertEqual(self.facts(), original)
        self.assertIn("FAIL: load aborted", loader.REPORT.read_text())
        self.assertNotIn("PASS", loader.REPORT.read_text())

    def test_missing_required_header_is_fatal(self):
        self.sources([self.row])
        (self.root / "data/raw/H1.csv").write_text("bad_header\nvalue\n")
        with self.assertRaisesRegex(ValueError, "Missing columns"):
            self.run_load()
        self.assertIn("FAIL", loader.REPORT.read_text())


if __name__ == "__main__":
    unittest.main()
