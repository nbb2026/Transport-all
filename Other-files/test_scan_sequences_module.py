"""Regression tests for the first standalone core module (no instruments)."""

import unittest

from test_ppms_motor_debug import app
from transport.core.scan_sequences import build_round_trip_values


class SharedScanSequenceTests(unittest.TestCase):
    def test_legacy_entry_point_reexports_identical_callable(self):
        self.assertIs(app.build_round_trip_values, build_round_trip_values)

    def test_non_divisible_step_includes_endpoint_without_overshoot(self):
        self.assertEqual(
            build_round_trip_values(0, 1, 0.4, decimals=3),
            [0.0, 0.4, 0.8, 1.0, 0.8, 0.4, 0.0],
        )

    def test_descending_scan_returns_to_start(self):
        self.assertEqual(
            build_round_trip_values(1, 0, 0.4, decimals=3),
            [1.0, 0.6, 0.2, 0.0, 0.2, 0.6, 1.0],
        )

    def test_identical_endpoints(self):
        self.assertEqual(build_round_trip_values(2, 2, 0.1, decimals=3), [2.0])

    def test_invalid_step_and_nonfinite_values_are_refused(self):
        with self.assertRaises(ValueError):
            build_round_trip_values(0, 1, 0, decimals=3)
        with self.assertRaises(ValueError):
            build_round_trip_values(float("nan"), 1, 0.1, decimals=3)

    def test_point_limit_is_checked_before_expanding_list(self):
        with self.assertRaisesRegex(ValueError, "Total scan points exceed"):
            build_round_trip_values(0, 1, 0.01, decimals=4, max_total_points=10,
                                    too_many_message="Total scan points exceed")


if __name__ == "__main__":
    unittest.main()
