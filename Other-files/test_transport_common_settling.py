"""Regression tests for shared lock-in settling calculations (transport.common.settling)."""

import inspect
import math
import sys
import unittest
from pathlib import Path
from unittest import mock

# Ensure repository root is on sys.path for direct test execution
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import Transport_all as app
from transport.common import (
    DEFAULT_LOCKIN_SETTLE_TAUS,
    calculate_lockin_settle_s,
    format_lockin_settle_text,
    format_settle_status_text,
)


class TestTransportCommonSettling(unittest.TestCase):
    def test_default_constant(self):
        self.assertEqual(DEFAULT_LOCKIN_SETTLE_TAUS, 1.0)
        self.assertEqual(app.LOCKIN_SETTLE_TAUS, 1.0)

    def test_original_public_signatures_preserved(self):
        """Requirement 3: Keep original public function signatures in Transport_all.py exactly unchanged."""
        sig_settle = inspect.signature(app.ppms_lockin_settle_s)
        self.assertEqual(list(sig_settle.parameters.keys()), ["settle_s", "time_constants_s"])

        sig_status = inspect.signature(app.ppms_settle_status_text)
        self.assertEqual(list(sig_status.parameters.keys()), ["seconds"])

        sig_text = inspect.signature(app.ppms_lockin_settle_text)
        self.assertEqual(
            list(sig_text.parameters.keys()),
            ["settle_s", "effective_s", "slowest_tc_s", "meter"],
        )

    def test_pure_function_signatures(self):
        """Requirement 3: The new pure calculation functions accept an explicit settle_taus argument."""
        sig_settle = inspect.signature(calculate_lockin_settle_s)
        self.assertEqual(
            list(sig_settle.parameters.keys()),
            ["settle_s", "time_constants_s", "settle_taus"],
        )
        self.assertEqual(sig_settle.parameters["settle_taus"].default, DEFAULT_LOCKIN_SETTLE_TAUS)

        sig_text = inspect.signature(format_lockin_settle_text)
        self.assertEqual(
            list(sig_text.parameters.keys()),
            ["settle_s", "effective_s", "slowest_tc_s", "meter", "settle_taus"],
        )
        self.assertEqual(sig_text.parameters["settle_taus"].default, DEFAULT_LOCKIN_SETTLE_TAUS)

    def test_no_misleading_ppms_aliases_in_transport_common(self):
        """Requirement 6: transport.common should not export misleading ppms_* compatibility aliases."""
        import transport.common as common
        import transport.common.settling as settling

        for name in ("ppms_lockin_settle_s", "ppms_settle_status_text", "ppms_lockin_settle_text"):
            self.assertFalse(hasattr(common, name), f"Misleading alias {name} found in transport.common")
            self.assertFalse(hasattr(settling, name), f"Misleading alias {name} found in transport.common.settling")

    def test_calculate_lockin_settle_default_rule(self):
        self.assertEqual(calculate_lockin_settle_s(0.5, [1.0]), 1.0)
        self.assertEqual(calculate_lockin_settle_s(0.2, [0.3]), 0.3)
        self.assertEqual(calculate_lockin_settle_s(0.5, [2.0]), 2.0)
        self.assertEqual(calculate_lockin_settle_s(0.5, [1.0, 3.0]), 3.0)
        self.assertEqual(calculate_lockin_settle_s(0.5, [0.3]), 0.5)
        self.assertEqual(calculate_lockin_settle_s(30.0, [1.0, 3.0]), 30.0)
        self.assertEqual(calculate_lockin_settle_s(0.5, []), 0.5)
        self.assertEqual(calculate_lockin_settle_s(0.5, [0.0]), 0.5)

    def test_calculate_lockin_settle_custom_taus(self):
        self.assertEqual(calculate_lockin_settle_s(0.5, [1.0], 7.0), 7.0)
        self.assertEqual(calculate_lockin_settle_s(0.5, [0.1], 7.0), 0.7)
        self.assertEqual(calculate_lockin_settle_s(10.0, [1.0], 7.0), 10.0)
        self.assertEqual(calculate_lockin_settle_s(0.5, [1.0], settle_taus=7.0), 7.0)
        self.assertEqual(calculate_lockin_settle_s(0.5, [0.1], settle_taus=7.0), 0.7)
        self.assertEqual(calculate_lockin_settle_s(0.5, [1.0], settle_taus=0.0), 0.5)

    def test_calculate_lockin_settle_numerical_rounding(self):
        self.assertEqual(str(calculate_lockin_settle_s(0.5, [0.1], settle_taus=7.0)), "0.7")
        self.assertEqual(str(calculate_lockin_settle_s(0.5, [0.3], settle_taus=7.0)), "2.1")
        self.assertEqual(str(calculate_lockin_settle_s(0.0, [1e-5], settle_taus=7.0)), "7e-05")
        self.assertEqual(str(calculate_lockin_settle_s(0.1, [0.03], settle_taus=7.0)), "0.21")
        self.assertEqual(str(calculate_lockin_settle_s(0.0, [3e-5], settle_taus=7.0)), "0.00021")
        self.assertEqual(str(calculate_lockin_settle_s(0.0, [1e-5])), "1e-05")

    def test_calculate_lockin_settle_exception_preservation(self):
        """Requirement 1: Preserve original exception behavior. Do not silently ignore None or invalid strings."""
        for fn in (calculate_lockin_settle_s, app.ppms_lockin_settle_s):
            with self.subTest(fn=fn.__name__):
                # None in time constants raises TypeError
                with self.assertRaises(TypeError):
                    fn(0.5, [None])
                with self.assertRaises(TypeError):
                    fn(0.5, [1.0, None])

                # Invalid string raises ValueError
                with self.assertRaises(ValueError):
                    fn(0.5, ["not_a_number"])
                with self.assertRaises(ValueError):
                    fn(0.5, [1.0, "bad"])

                # Invalid settle_s raises TypeError or ValueError
                with self.assertRaises(TypeError):
                    fn(None, [1.0])
                with self.assertRaises(ValueError):
                    fn("bad_settle", [1.0])

                # Non-finite numbers are ignored without exception
                self.assertAlmostEqual(fn(0.0, [float("nan"), 1e-3]), 1e-3)
                self.assertAlmostEqual(fn(0.0, [float("inf"), 1e-3]), 1e-3)
                self.assertAlmostEqual(fn(0.0, [-float("inf"), 1e-3]), 1e-3)

    def test_format_settle_status_text(self):
        self.assertEqual(format_settle_status_text(7.0), "7")
        self.assertEqual(format_settle_status_text(0.7), "0.7")
        self.assertEqual(format_settle_status_text(2.1), "2.1")
        self.assertEqual(format_settle_status_text(21.0), "21")
        self.assertEqual(format_settle_status_text(70.0), "70")
        self.assertEqual(format_settle_status_text(12.34), "12.3")
        self.assertEqual(format_settle_status_text(99.94), "99.9")
        self.assertEqual(format_settle_status_text(0.0864199), "0.0864")
        self.assertEqual(format_settle_status_text(7e-05), "7e-05")
        self.assertEqual(format_settle_status_text(0.0), "0")
        self.assertEqual(format_settle_status_text(123.4), "123")
        self.assertEqual(format_settle_status_text(12345.7), "12346")
        self.assertEqual(format_settle_status_text(86400.0), "86400")

    def test_format_lockin_settle_text_equivalence(self):
        """Requirement 2: Preserve original numerical, formatting, and exception behavior of ppms_lockin_settle_text."""
        for fn in (
            lambda s, e, tc, m: format_lockin_settle_text(s, e, tc, m),
            app.ppms_lockin_settle_text,
        ):
            # Settle s longer
            self.assertEqual(
                fn(12.0, 12.0, 1.0, "the Zurich"),
                "12 s (Settle s; 1 x the slowest lock-in time constant, 1 s on the Zurich, is 1 s)",
            )
            # Lock-in TC longer
            self.assertEqual(
                fn(0.5, 1.0, 1.0, "SR830-1"),
                "1 s (1 x 1 s, the time constant of SR830-1, the slowest lock-in measured; Settle s is 0.5 s)",
            )
            # Falsy slowest_tc_s
            self.assertEqual(fn(0.5, 0.5, 0.0, ""), "0.5 s (Settle s)")
            self.assertEqual(fn(0.5, 0.5, 0, ""), "0.5 s (Settle s)")
            self.assertEqual(fn(0.5, 0.5, None, ""), "0.5 s (Settle s)")

        # Custom settle_taus in format_lockin_settle_text
        self.assertEqual(
            format_lockin_settle_text(0.5, 0.7, 0.1, "SR830-1", settle_taus=7.0),
            "0.7 s (7 x 0.1 s, the time constant of SR830-1, the slowest lock-in measured; Settle s is 0.5 s)",
        )

    def test_patching_app_lockin_settle_taus_affects_wrappers(self):
        """Requirement 4: Preserve runtime behavior of monkeypatching Transport_all.LOCKIN_SETTLE_TAUS."""
        with mock.patch.object(app, "LOCKIN_SETTLE_TAUS", 7.0):
            self.assertEqual(app.ppms_lockin_settle_s(0.5, [0.1]), 0.7)
            self.assertEqual(str(app.ppms_lockin_settle_s(0.5, [0.1])), "0.7")
            text = app.ppms_lockin_settle_text(0.5, 0.7, 0.1, "SR830-1")
            self.assertIn("7 x 0.1 s", text)

        self.assertEqual(app.LOCKIN_SETTLE_TAUS, 1.0)
        self.assertEqual(app.ppms_lockin_settle_s(0.5, [0.1]), 0.5)


if __name__ == "__main__":
    unittest.main()
