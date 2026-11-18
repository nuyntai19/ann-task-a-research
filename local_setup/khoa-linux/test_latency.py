"""Checks for measured latency aggregation and native-source preservation."""
import csv
from pathlib import Path
import tempfile
import unittest

from instrument_latency import instrument
from run import read_latency

HERE = Path(__file__).resolve().parent


class LatencyTests(unittest.TestCase):
    def parse(self, rows, count=4, beams=(10,), header=("beam", "query_id", "latency_us")):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latency.csv"
            with path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(header)
                writer.writerows(rows)
            return read_latency(path, count, beams)

    def test_known_percentiles_and_beam_grouping(self):
        rows = [(beam, query, value * scale) for query, value in enumerate((10, 20, 30, 40))
                for beam, scale in ((10, 1), (20, 2))]
        result = self.parse(rows, beams=(10, 20))
        for beam, scale in ((10, 1), (20, 2)):
            self.assertEqual(result[beam]["query_count"], 4)
            for name, expected in {"mean": 25, "min": 10, "max": 40,
                                   "p50": 25, "p95": 38.5, "p99": 39.7}.items():
                self.assertAlmostEqual(result[beam][name], expected * scale)

    def test_invalid_or_incomplete_samples_rejected(self):
        valid = [(10, i, 10 + i) for i in range(4)]
        cases = {
            "missing": valid[:-1], "duplicate": valid + [valid[0]],
            "wrong_beam": [(20, 0, 10)] + valid[1:],
            "bad_query": [(10, -1, 10)] + valid[1:],
            "zero": [(10, 0, 0)] + valid[1:],
            "negative": [(10, 0, -10)] + valid[1:],
            "nan": [(10, 0, "nan")] + valid[1:],
            "infinity": [(10, 0, "inf")] + valid[1:],
        }
        for label, rows in cases.items():
            with self.subTest(case=label), self.assertRaises(ValueError):
                self.parse(rows)
        with self.assertRaises(ValueError):
            self.parse(valid, header=("query_id", "latency_us"))

    def test_timers_are_only_changes_to_native_query_code(self):
        native = (HERE.parent.parent / "experiments/R86/r86_v1_2_source/algorithms/utils/beamSearch.h").read_text()
        patched = instrument(native)
        timer_line = "      local_latency::QueryTimer query_timer(i);\n"
        self.assertEqual(patched.count(timer_line), 2)
        restored = patched.removeprefix('#include "latency_probe.h"\n').replace(timer_line, "")
        self.assertEqual(restored, native)

    def test_unexpected_upstream_query_layout_rejected(self):
        native = (HERE.parent.parent / "experiments/R86/r86_v1_2_source/algorithms/utils/beamSearch.h").read_text()
        start = native.index("\nqsearchAll(const PointRange &Query_Points,")
        changed = native[:start] + native[start:].replace(
            "    parlay::parallel_for(0, Query_Points.size(), [&](size_t i) {\n",
            "    parlay::parallel_for(0, Query_Points.size(), [&](size_t query_id) {\n", 1)
        with self.assertRaises(ValueError):
            instrument(changed)


if __name__ == "__main__":
    unittest.main()
