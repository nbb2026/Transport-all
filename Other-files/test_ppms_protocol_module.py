"""Regression tests for the extracted transport.ppms.protocol module.

Verifies that validate_ppms_temperature_command, validate_ppms_field_command,
and ppms_scan_temperature_segments maintain their mathematical specifications,
safety guardrails, exception types, and exact backward compatibility with
Transport_all.
"""

import math
import sys
import unittest
from pathlib import Path

# Ensure repository root is on sys.path for direct test runs
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from transport.ppms import (
    PPMS_FIELD_LIMIT_OE,
    PPMS_FIELD_RATE_LIMIT_OE_S,
    PPMS_TEMPERATURE_LOW_BOUNDARY_K,
    PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN,
    PPMS_TEMPERATURE_MAX_K,
    PPMS_TEMPERATURE_MAX_RATE_K_MIN,
    PPMS_TEMPERATURE_MIN_K,
    ppms_scan_temperature_segments,
    validate_ppms_field_command,
    validate_ppms_temperature_command,
)
import transport.ppms.protocol as protocol_module


class TestPPMSProtocolModule(unittest.TestCase):
    """Test suite for the pure PPMS protocol and safety guardrail functions."""

    def test_module_exports(self):
        """Verify __all__ exports of transport.ppms and protocol module."""
        for symbol in (
            "PPMS_FIELD_LIMIT_OE",
            "PPMS_FIELD_RATE_LIMIT_OE_S",
            "PPMS_TEMPERATURE_LOW_BOUNDARY_K",
            "PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN",
            "PPMS_TEMPERATURE_MAX_K",
            "PPMS_TEMPERATURE_MAX_RATE_K_MIN",
            "PPMS_TEMPERATURE_MIN_K",
            "ppms_scan_temperature_segments",
            "validate_ppms_field_command",
            "validate_ppms_temperature_command",
        ):
            self.assertTrue(hasattr(protocol_module, symbol), f"Missing {symbol} in protocol")

    def test_temperature_guardrails_valid_ranges(self):
        """Verify normal and low-temperature valid command acceptance."""
        # Wholly above 9 K allows up to 10 K/min
        target, rate = validate_ppms_temperature_command(300.0, 10.0, 20.0)
        self.assertEqual(target, 300.0)
        self.assertTrue(math.isclose(rate, 10.0))

        # Boundary target at 5 K (min temperature) with 1 K/min (max low-temp rate)
        target, rate = validate_ppms_temperature_command(5.0, 1.0, 10.0)
        self.assertEqual(target, 5.0)
        self.assertTrue(math.isclose(rate, 1.0))

        # Max temperature at 380 K
        target, rate = validate_ppms_temperature_command(380.0, 5.0, 300.0)
        self.assertEqual(target, 380.0)
        self.assertTrue(math.isclose(rate, 5.0))

    def test_temperature_guardrails_rate_limits(self):
        """Verify rate limits in 5-9 K range vs above 9 K range."""
        # > 1.0 K/min when entering <= 9 K must fail
        with self.assertRaisesRegex(ValueError, "within the 5–9 K range must not exceed 1 K/min"):
            validate_ppms_temperature_command(5.0, 1.01, 10.0)

        # > 1.0 K/min when current <= 9 K must also fail
        with self.assertRaisesRegex(ValueError, "within the 5–9 K range must not exceed 1 K/min"):
            validate_ppms_temperature_command(50.0, 1.5, 8.0)

        # > 10.0 K/min wholly above 9 K must fail
        with self.assertRaisesRegex(ValueError, "above 9 K must not exceed 10 K/min"):
            validate_ppms_temperature_command(300.0, 10.01, 100.0)

        # Non-positive rate
        with self.assertRaisesRegex(ValueError, "rate must be greater than 0"):
            validate_ppms_temperature_command(100.0, 0.0)
        with self.assertRaisesRegex(ValueError, "rate must be greater than 0"):
            validate_ppms_temperature_command(100.0, -1.0)

    def test_temperature_guardrails_out_of_bounds_and_non_finite(self):
        """Verify temperature boundary violations and NaN/Inf rejection."""
        with self.assertRaisesRegex(ValueError, "PPMS target temperature must be within 5–380 K"):
            validate_ppms_temperature_command(4.99, 1.0)
        with self.assertRaisesRegex(ValueError, "PPMS target temperature must be within 5–380 K"):
            validate_ppms_temperature_command(380.01, 1.0)

        with self.assertRaisesRegex(ValueError, "finite"):
            validate_ppms_temperature_command(float("nan"), 1.0)
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_ppms_temperature_command(100.0, float("inf"))

    def test_field_guardrails_valid_and_bounds(self):
        """Verify field command validation and ±89,900 Oe limits."""
        # Max boundary field and near-max rate
        field, rate = validate_ppms_field_command(89900.0, 149.999)
        self.assertEqual(field, 89900.0)
        self.assertEqual(rate, 149.999)

        # Negative max boundary
        field, rate = validate_ppms_field_command(-89900.0, 50.0)
        self.assertEqual(field, -89900.0)
        self.assertEqual(rate, 50.0)

        # Exceeding 89900 Oe
        with self.assertRaisesRegex(ValueError, "within ±89900 Oe"):
            validate_ppms_field_command(89900.1, 100.0)
        with self.assertRaisesRegex(ValueError, "within ±89900 Oe"):
            validate_ppms_field_command(-89900.1, 100.0)

    def test_field_guardrails_rate_limits_and_non_finite(self):
        """Verify field ramp rate strict inequality (< 150 Oe/s) and non-finite values."""
        # Exactly 150 Oe/s is rejected (requirement: strictly below 150)
        with self.assertRaisesRegex(ValueError, "greater than 0 and below 150 Oe/s"):
            validate_ppms_field_command(1000.0, 150.0)
        with self.assertRaisesRegex(ValueError, "greater than 0 and below 150 Oe/s"):
            validate_ppms_field_command(1000.0, 150.1)
        with self.assertRaisesRegex(ValueError, "greater than 0 and below 150 Oe/s"):
            validate_ppms_field_command(1000.0, 0.0)
        with self.assertRaisesRegex(ValueError, "greater than 0 and below 150 Oe/s"):
            validate_ppms_field_command(1000.0, -10.0)

        with self.assertRaisesRegex(ValueError, "finite"):
            validate_ppms_field_command(float("nan"), 100.0)
        with self.assertRaisesRegex(ValueError, "finite"):
            validate_ppms_field_command(1000.0, float("inf"))

    def test_temperature_segments_planning(self):
        """Verify multi-segment staging when transitioning from warm down to <= 9 K."""
        # Cooldown crossing 9 K boundary from above 9.1 K: splits into staged approach
        # Target 5 K with requested 5 K/min: stage to (9.1 K, 5.0 K/min) then (5.0 K, 1.0 K/min)
        segments = ppms_scan_temperature_segments(current_k=50.0, target_k=5.0, rate_k_min=5.0)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], (9.1, 5.0))
        self.assertEqual(segments[1], (5.0, 1.0))

        # Cooldown crossing 9 K boundary with requested rate slower than 1 K/min (e.g. 0.5):
        # typed rate is preserved: min(rate, 1.0) -> 0.5
        segments = ppms_scan_temperature_segments(current_k=20.0, target_k=5.0, rate_k_min=0.5)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], (9.1, 0.5))
        self.assertEqual(segments[1], (5.0, 0.5))

        # Cooldown within high-temperature range only (no boundary crossing): single segment
        segments = ppms_scan_temperature_segments(current_k=300.0, target_k=50.0, rate_k_min=8.0)
        self.assertEqual(segments, [(50.0, 8.0)])

        # Starting already at or below 9.1 K (e.g. 9.05 K to 5 K): single segment directly at low rate
        segments = ppms_scan_temperature_segments(current_k=9.0, target_k=5.0, rate_k_min=5.0)
        self.assertEqual(segments, [(5.0, 1.0)])

        # Non-finite current readback rejection
        with self.assertRaisesRegex(ValueError, "Current temperature readback is invalid"):
            ppms_scan_temperature_segments(float("nan"), 100.0, 5.0)

    def test_backward_compatibility_with_transport_all(self):
        """Verify that Transport_all exposes identical objects and backward-compatible signatures."""
        import Transport_all as app

        self.assertIs(app.validate_ppms_temperature_command, validate_ppms_temperature_command)
        self.assertIs(app.validate_ppms_field_command, validate_ppms_field_command)
        self.assertIs(app.ppms_scan_temperature_segments, ppms_scan_temperature_segments)

        self.assertEqual(app.PPMS_TEMPERATURE_MIN_K, PPMS_TEMPERATURE_MIN_K)
        self.assertEqual(app.PPMS_TEMPERATURE_MAX_K, PPMS_TEMPERATURE_MAX_K)
        self.assertEqual(app.PPMS_TEMPERATURE_LOW_BOUNDARY_K, PPMS_TEMPERATURE_LOW_BOUNDARY_K)
        self.assertEqual(app.PPMS_TEMPERATURE_MAX_RATE_K_MIN, PPMS_TEMPERATURE_MAX_RATE_K_MIN)
        self.assertEqual(app.PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN, PPMS_TEMPERATURE_LOW_MAX_RATE_K_MIN)
        self.assertEqual(app.PPMS_FIELD_LIMIT_OE, PPMS_FIELD_LIMIT_OE)
        self.assertEqual(app.PPMS_FIELD_RATE_LIMIT_OE_S, PPMS_FIELD_RATE_LIMIT_OE_S)


if __name__ == "__main__":
    unittest.main()
