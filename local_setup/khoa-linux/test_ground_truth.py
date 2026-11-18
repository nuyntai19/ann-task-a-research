"""Validate provided GT parsing, native conversion, and mismatch detection."""
from pathlib import Path
import struct
import tempfile
import unittest

import numpy as np

from ground_truth import load_gt_ids, reuse_gt


class GroundTruthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.base = np.arange(32, dtype=np.float32).reshape(-1, 1)
        self.queries = np.array([[3.25], [10.25], [25.25]], dtype=np.float32)
        dists = (self.base[None, :, 0] - self.queries[:, 0, None]) ** 2
        self.ids = np.argsort(dists, axis=1, kind="stable")[:, :10].astype("<u4")

    def ivecs(self):
        path = self.path / "gt.ivecs"
        rows = np.column_stack((np.full(3, 10), self.ids)).astype("<i4")
        rows.tofile(path)
        return path

    def test_ivecs_reuse_and_query_prefix(self):
        loaded = load_gt_ids(self.ivecs(), 3, 32)
        ids, dists, validation = reuse_gt(self.base, self.queries[:2], loaded)
        np.testing.assert_array_equal(ids, self.ids[:2])
        np.testing.assert_array_equal(dists, (self.base[ids, 0] - self.queries[:2]) ** 2)
        self.assertEqual(validation["exact_sample_queries"], [0, 1])

    def test_ibin_with_and_without_distance_payload(self):
        for include_distances in (False, True):
            with self.subTest(include_distances=include_distances):
                path = self.path / "gt.ibin"
                with path.open("wb") as stream:
                    stream.write(struct.pack("<II", 3, 10))
                    self.ids.tofile(stream)
                    if include_distances:
                        np.zeros((3, 10), dtype="<f4").tofile(stream)
                np.testing.assert_array_equal(load_gt_ids(path, 3, 32), self.ids)

    def test_bad_shape_ids_and_truncated_files_rejected(self):
        path = self.ivecs()
        with self.assertRaises(ValueError):
            load_gt_ids(path, 4, 32)
        rows = np.fromfile(path, dtype="<i4").reshape(3, 11)
        for bad in (-1, 32):
            with self.subTest(bad_id=bad):
                changed = rows.copy()
                changed[0, 1] = bad
                changed.tofile(path)
                with self.assertRaises(ValueError):
                    load_gt_ids(path, 3, 32)
        path.write_bytes(b"abc")
        with self.assertRaises(ValueError):
            load_gt_ids(path, 3, 32)

    def test_wrong_query_order_duplicate_and_wrong_nearest_ids_rejected(self):
        with self.assertRaises(ValueError):
            reuse_gt(self.base, self.queries[::-1], self.ids)
        duplicate = self.ids.copy()
        duplicate[0, 1] = duplicate[0, 0]
        with self.assertRaises(ValueError):
            reuse_gt(self.base, self.queries, duplicate)
        # Distance-sorted but incorrect neighbors: exact sample check must fail.
        with self.assertRaises(ValueError):
            reuse_gt(self.base, np.array([[0.0]], dtype=np.float32),
                     np.arange(10, 20, dtype="<u4").reshape(1, 10))

    def test_equivalent_boundary_ties_accepted(self):
        base = np.arange(-15, 17, dtype=np.float32).reshape(-1, 1)
        query = np.array([[0.0]], dtype=np.float32)
        ids = np.argsort(base[:, 0] ** 2, kind="stable")[:10].astype("<u4")
        self.assertEqual(base[ids[-1], 0], -5)
        ids[-1] = np.flatnonzero(base[:, 0] == 5)[0]
        reused, _, _ = reuse_gt(base, query, ids.reshape(1, 10))
        np.testing.assert_array_equal(reused[0], ids)


if __name__ == "__main__":
    unittest.main()
