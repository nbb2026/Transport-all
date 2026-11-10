"""Unit and regression tests for shared transport measurement validation.

Covers transport.common.validation and its backward-compatibility wrapper
in Transport_all.py.
"""

from __future__ import annotations

import inspect
import math
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

# Ensure repository root is on sys.path for direct test execution
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from transport.common import (
    DEFAULT_K6221_MAX_ABS_CURRENT_A,
    DEFAULT_K6221_MAX_COMPLIANCE_V,
    DEFAULT_K6221_MAX_FREQUENCY_HZ,
    DEFAULT_K6221_MIN_COMPLIANCE_V,
    DEFAULT_K6221_MIN_FREQUENCY_HZ,
    DEFAULT_SR830_KEYS,
    DEFAULT_SR830_LABELS,
    DEFAULT_SR830_MAX_DEMOD_FREQ_HZ,
    DEFAULT_SR830_MAX_HARMONIC,
    DEFAULT_SR830_MIN_HARMONIC,
    validate_transport_scan_settings,
)
import Transport_all as app


class ReferenceOriginalValidation:
    """Exact copy of original validate_ppms_transport_scan_settings logic before extraction."""

    @staticmethod
    def validate(
        current_rms_ma,
        frequency_hz,
        compliance_v,
        harmonic_a,
        harmonic_b,
        active_lockins=("830_a", "830_b"),
        allow_no_lockins=False,
        harmonic_c=1,
        max_abs_current_a=0.105,
        min_compliance_v=0.1,
        max_compliance_v=105.0,
        valid_sr830_keys=("830_a", "830_b", "830_c"),
    ):
        current_rms_ma = float(current_rms_ma)
        frequency_hz = float(frequency_hz)
        compliance_v = float(compliance_v)
        harmonic_a = int(harmonic_a)
        harmonic_b = int(harmonic_b)
        harmonic_c = int(harmonic_c)
        active_lockins = tuple(str(key) for key in active_lockins)
        if not active_lockins and not allow_no_lockins:
            raise ValueError("PPMS field sweep requires at least one connected SR830")
        if any(key not in valid_sr830_keys for key in active_lockins):
            raise ValueError("PPMS SR830 slot is invalid")
        if not all(
            math.isfinite(value)
            for value in (current_rms_ma, frequency_hz, compliance_v)
        ):
            raise ValueError("6221 parameters for the PPMS transport scan must be finite values")
        if current_rms_ma <= 0:
            raise ValueError("6221 AC current for the PPMS transport scan must be greater than 0 mA RMS")
        peak_a = math.sqrt(2.0) * current_rms_ma * 1e-3
        if peak_a > max_abs_current_a:
            maximum_rms_ma = max_abs_current_a / math.sqrt(2.0) * 1000.0
            raise ValueError(
                f"6221 sine-wave peak must not exceed {max_abs_current_a * 1000:g} mA; "
                f"the GUI RMS current limit is about {maximum_rms_ma:.6g} mA"
            )
        if not 1e-3 <= frequency_hz <= 1e5:
            raise ValueError("6221 waveform frequency must be within 0.001–100000 Hz")
        if not min_compliance_v <= compliance_v <= max_compliance_v:
            raise ValueError(
                f"6221 compliance voltage must be within {min_compliance_v:g}–"
                f"{max_compliance_v:g} V"
            )
        harmonics = {"830_a": harmonic_a, "830_b": harmonic_b, "830_c": harmonic_c}
        for key in active_lockins:
            label = {"830_a": "A", "830_b": "B", "830_c": "C"}[key]
            harmonic = harmonics[key]
            if not 1 <= harmonic <= 19999:
                raise ValueError(f"SR830 slot {label} harmonic must be within 1–19999")
            if frequency_hz * harmonic > 102000.0:
                raise ValueError(f"SR830 slot {label} demodulation frequency must not exceed 102 kHz")
        return {
            "current_rms_ma": current_rms_ma,
            "frequency_hz": frequency_hz,
            "compliance_v": compliance_v,
            "harmonic_a": harmonic_a,
            "harmonic_b": harmonic_b,
            "harmonic_c": harmonic_c,
            "active_lockins": active_lockins,
            "allow_no_lockins": allow_no_lockins,
            "peak_a": peak_a,
        }


class TestTransportValidationPurityAndContract(unittest.TestCase):
    """AC1 and AC2: Pure module import, signature preservation, and exact contract."""

    def test_fresh_process_import_independence(self):
        """Importing transport.common.validation in a clean Python process must not import Transport_all, Tkinter, or drivers."""
        code = (
            "import sys\n"
            "import transport.common.validation as v\n"
            "assert callable(v.validate_transport_scan_settings)\n"
            "assert not hasattr(v, 'validate_ppms_transport_scan_settings'), 'Legacy alias must not be exported'\n"
            "forbidden = ['Transport_all', 'tkinter', 'tkinter.ttk', 'pyvisa', 'serial']\n"
            "loaded_forbidden = [mod for mod in forbidden if mod in sys.modules]\n"
            "if loaded_forbidden:\n"
            "    raise AssertionError(f'Forbidden modules loaded: {loaded_forbidden}')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, f"Subprocess failed:\n{result.stderr}")

    def test_shared_module_does_not_export_misleading_ppms_alias(self):
        """transport.common and transport.common.validation must not export validate_ppms_transport_scan_settings."""
        import transport.common as tc
        import transport.common.validation as tcv
        self.assertFalse(hasattr(tc, "validate_ppms_transport_scan_settings"))
        self.assertFalse(hasattr(tcv, "validate_ppms_transport_scan_settings"))
        self.assertNotIn("validate_ppms_transport_scan_settings", tc.__all__)

    def test_legacy_wrapper_signature_and_defaults(self):
        """Transport_all.validate_ppms_transport_scan_settings must retain exact signature."""
        sig = inspect.signature(app.validate_ppms_transport_scan_settings)
        params = list(sig.parameters.values())

        expected_names = [
            "current_rms_ma",
            "frequency_hz",
            "compliance_v",
            "harmonic_a",
            "harmonic_b",
            "active_lockins",
            "allow_no_lockins",
            "harmonic_c",
        ]
        self.assertEqual([p.name for p in params], expected_names)

        # Check default values
        self.assertEqual(sig.parameters["active_lockins"].default, ("830_a", "830_b"))
        self.assertEqual(sig.parameters["allow_no_lockins"].default, False)
        self.assertEqual(sig.parameters["harmonic_c"].default, 1)

    def test_default_constants(self):
        """Verify default electrical and slot constants."""
        self.assertEqual(DEFAULT_K6221_MAX_ABS_CURRENT_A, 0.105)
        self.assertEqual(DEFAULT_K6221_MIN_COMPLIANCE_V, 0.1)
        self.assertEqual(DEFAULT_K6221_MAX_COMPLIANCE_V, 105.0)
        self.assertEqual(DEFAULT_K6221_MIN_FREQUENCY_HZ, 1e-3)
        self.assertEqual(DEFAULT_K6221_MAX_FREQUENCY_HZ, 1e5)
        self.assertEqual(DEFAULT_SR830_KEYS, ("830_a", "830_b", "830_c"))
        self.assertEqual(DEFAULT_SR830_LABELS, {"830_a": "A", "830_b": "B", "830_c": "C"})
        self.assertEqual(DEFAULT_SR830_MIN_HARMONIC, 1)
        self.assertEqual(DEFAULT_SR830_MAX_HARMONIC, 19999)
        self.assertEqual(DEFAULT_SR830_MAX_DEMOD_FREQ_HZ, 102000.0)

    def test_successful_validation_and_return_structure(self):
        """Valid inputs return expected dictionary with derived peak_a."""
        result = app.validate_ppms_transport_scan_settings(1.0, 317.3, 50.0, 1, 2)
        expected_peak = math.sqrt(2.0) * 1.0 * 1e-3
        self.assertEqual(result["current_rms_ma"], 1.0)
        self.assertEqual(result["frequency_hz"], 317.3)
        self.assertEqual(result["compliance_v"], 50.0)
        self.assertEqual(result["harmonic_a"], 1)
        self.assertEqual(result["harmonic_b"], 2)
        self.assertEqual(result["harmonic_c"], 1)
        self.assertEqual(result["active_lockins"], ("830_a", "830_b"))
        self.assertFalse(result["allow_no_lockins"])
        self.assertAlmostEqual(result["peak_a"], expected_peak, places=12)

    def test_input_type_coercion(self):
        """Strings and floats coerce to appropriate numeric types."""
        result = app.validate_ppms_transport_scan_settings("0.5", "1000", "20", "1", "3", ["830_a"], harmonic_c="2")
        self.assertIsInstance(result["current_rms_ma"], float)
        self.assertEqual(result["current_rms_ma"], 0.5)
        self.assertIsInstance(result["frequency_hz"], float)
        self.assertEqual(result["frequency_hz"], 1000.0)
        self.assertIsInstance(result["compliance_v"], float)
        self.assertEqual(result["compliance_v"], 20.0)
        self.assertIsInstance(result["harmonic_a"], int)
        self.assertEqual(result["harmonic_a"], 1)
        self.assertIsInstance(result["harmonic_b"], int)
        self.assertEqual(result["harmonic_b"], 3)
        self.assertIsInstance(result["harmonic_c"], int)
        self.assertEqual(result["harmonic_c"], 2)
        self.assertIsInstance(result["active_lockins"], tuple)
        self.assertEqual(result["active_lockins"], ("830_a",))


class TestNumericLimitsAndPrecedence(unittest.TestCase):
    """Detailed boundary checks, exact error messages, and exception precedence."""

    def test_empty_lockins_requires_allow_no_lockins(self):
        with self.assertRaisesRegex(ValueError, "PPMS field sweep requires at least one connected SR830"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 1, ())

        # With allow_no_lockins=True, empty active_lockins is permitted (Zurich lock-in mode)
        res = app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 1, (), allow_no_lockins=True)
        self.assertEqual(res["active_lockins"], ())
        self.assertTrue(res["allow_no_lockins"])

    def test_invalid_sr830_slot_keys(self):
        with self.assertRaisesRegex(ValueError, "PPMS SR830 slot is invalid"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 1, ("830_a", "830_unknown"))

    def test_non_finite_parameters(self):
        for bad_val in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaisesRegex(ValueError, "6221 parameters for the PPMS transport scan must be finite values"):
                app.validate_ppms_transport_scan_settings(bad_val, 100.0, 10.0, 1, 1)
            with self.assertRaisesRegex(ValueError, "6221 parameters for the PPMS transport scan must be finite values"):
                app.validate_ppms_transport_scan_settings(1.0, bad_val, 10.0, 1, 1)
            with self.assertRaisesRegex(ValueError, "6221 parameters for the PPMS transport scan must be finite values"):
                app.validate_ppms_transport_scan_settings(1.0, 100.0, bad_val, 1, 1)

    def test_non_positive_current(self):
        with self.assertRaisesRegex(ValueError, "6221 AC current for the PPMS transport scan must be greater than 0 mA RMS"):
            app.validate_ppms_transport_scan_settings(0.0, 100.0, 10.0, 1, 1)
        with self.assertRaisesRegex(ValueError, "6221 AC current for the PPMS transport scan must be greater than 0 mA RMS"):
            app.validate_ppms_transport_scan_settings(-1.0, 100.0, 10.0, 1, 1)

    def test_peak_current_boundary(self):
        # 105 mA peak limit -> RMS limit is 0.105 / sqrt(2) * 1000 ≈ 74.246212 mA
        max_safe_rms = 0.105 / math.sqrt(2.0) * 1000.0
        # Exactly at or slightly below limit passes
        res = app.validate_ppms_transport_scan_settings(max_safe_rms - 1e-6, 100.0, 10.0, 1, 1)
        self.assertLessEqual(res["peak_a"], 0.105)

        # Slightly above limit fails with exact expected message
        above_rms = max_safe_rms + 0.001
        with self.assertRaisesRegex(ValueError, r"6221 sine-wave peak must not exceed 105 mA; the GUI RMS current limit is about 74\.2462 mA"):
            app.validate_ppms_transport_scan_settings(above_rms, 100.0, 10.0, 1, 1)

    def test_frequency_limits(self):
        with self.assertRaisesRegex(ValueError, "6221 waveform frequency must be within 0.001–100000 Hz"):
            app.validate_ppms_transport_scan_settings(1.0, 0.0009, 10.0, 1, 1)
        with self.assertRaisesRegex(ValueError, "6221 waveform frequency must be within 0.001–100000 Hz"):
            app.validate_ppms_transport_scan_settings(1.0, 100000.1, 10.0, 1, 1)

        # Boundaries pass
        self.assertEqual(app.validate_ppms_transport_scan_settings(1.0, 0.001, 10.0, 1, 1)["frequency_hz"], 0.001)
        self.assertEqual(app.validate_ppms_transport_scan_settings(1.0, 100000.0, 10.0, 1, 1)["frequency_hz"], 100000.0)

    def test_compliance_voltage_limits(self):
        with self.assertRaisesRegex(ValueError, "6221 compliance voltage must be within 0.1–105 V"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 0.09, 1, 1)
        with self.assertRaisesRegex(ValueError, "6221 compliance voltage must be within 0.1–105 V"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 105.01, 1, 1)

        # Boundaries pass
        self.assertEqual(app.validate_ppms_transport_scan_settings(1.0, 100.0, 0.1, 1, 1)["compliance_v"], 0.1)
        self.assertEqual(app.validate_ppms_transport_scan_settings(1.0, 100.0, 105.0, 1, 1)["compliance_v"], 105.0)

    def test_harmonic_range_and_inactive_slots(self):
        # Active slot harmonic out of range 1..19999
        with self.assertRaisesRegex(ValueError, "SR830 slot A harmonic must be within 1–19999"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 0, 1, ("830_a",))
        with self.assertRaisesRegex(ValueError, "SR830 slot B harmonic must be within 1–19999"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 20000, ("830_b",))
        with self.assertRaisesRegex(ValueError, "SR830 slot C harmonic must be within 1–19999"):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 1, ("830_c",), harmonic_c=0)

        # Inactive slot harmonic is NOT validated for range 1..19999, but still undergoes int() conversion
        res = app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 99999, ("830_a",), harmonic_c=-5)
        self.assertEqual(res["harmonic_b"], 99999)
        self.assertEqual(res["harmonic_c"], -5)

        # Inactive slot harmonic non-integer conversion error still raises ValueError
        with self.assertRaises(ValueError):
            app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, "not-an-int", ("830_a",))

    def test_direct_dictionary_lookup_raises_keyerror_on_unmapped_slot(self):
        """Custom valid_sr830_keys that lacks slot mapping raises KeyError matching original behavior."""
        with self.assertRaises(KeyError):
            validate_transport_scan_settings(
                1.0, 100.0, 10.0, 1, 1, ("830_custom",), valid_sr830_keys=("830_custom",)
            )
        with self.assertRaises(KeyError):
            ReferenceOriginalValidation.validate(
                1.0, 100.0, 10.0, 1, 1, ("830_custom",), valid_sr830_keys=("830_custom",)
            )

    def test_demodulation_frequency_limits(self):
        # 102 kHz limit: frequency * harmonic <= 102000.0
        # Slot A: 52000 * 2 = 104000 > 102000 -> fails
        with self.assertRaisesRegex(ValueError, "SR830 slot A demodulation frequency must not exceed 102 kHz"):
            app.validate_ppms_transport_scan_settings(1.0, 52000.0, 10.0, 2, 1, ("830_a",))

        # Slot B: 52000 * 2 = 104000 > 102000 -> fails
        with self.assertRaisesRegex(ValueError, "SR830 slot B demodulation frequency must not exceed 102 kHz"):
            app.validate_ppms_transport_scan_settings(1.0, 52000.0, 10.0, 1, 2, ("830_b",))

        # Slot C: 35000 * 3 = 105000 > 102000 -> fails
        with self.assertRaisesRegex(ValueError, "SR830 slot C demodulation frequency must not exceed 102 kHz"):
            app.validate_ppms_transport_scan_settings(1.0, 35000.0, 10.0, 1, 1, ("830_c",), harmonic_c=3)

        # Boundary 51000 * 2 = 102000.0 -> passes
        res = app.validate_ppms_transport_scan_settings(1.0, 51000.0, 10.0, 2, 2, ("830_a", "830_b"))
        self.assertEqual(res["frequency_hz"], 51000.0)


class TestDynamicMonkeypatchCompatibility(unittest.TestCase):
    """AC3: Monkeypatching Transport_all constants dynamically affects wrapper at call time."""

    def test_patch_max_current(self):
        with mock.patch.object(app, "K6221_MAX_ABS_CURRENT_A", 0.05):
            # 0.05 A peak limit corresponds to RMS limit ~35.3553 mA
            with self.assertRaisesRegex(ValueError, r"6221 sine-wave peak must not exceed 50 mA; the GUI RMS current limit is about 35\.3553 mA"):
                app.validate_ppms_transport_scan_settings(40.0, 100.0, 10.0, 1, 1)

            # 30 mA peak is ~0.0424 A <= 0.05 A -> passes
            res = app.validate_ppms_transport_scan_settings(30.0, 100.0, 10.0, 1, 1)
            self.assertEqual(res["current_rms_ma"], 30.0)

    def test_patch_compliance_limits(self):
        with mock.patch.object(app, "K6221_MIN_COMPLIANCE_V", 1.0), \
             mock.patch.object(app, "K6221_MAX_COMPLIANCE_V", 50.0):
            with self.assertRaisesRegex(ValueError, "6221 compliance voltage must be within 1–50 V"):
                app.validate_ppms_transport_scan_settings(1.0, 100.0, 0.5, 1, 1)
            with self.assertRaisesRegex(ValueError, "6221 compliance voltage must be within 1–50 V"):
                app.validate_ppms_transport_scan_settings(1.0, 100.0, 55.0, 1, 1)
            res = app.validate_ppms_transport_scan_settings(1.0, 100.0, 25.0, 1, 1)
            self.assertEqual(res["compliance_v"], 25.0)

    def test_patch_sr830_keys(self):
        with mock.patch.object(app, "PPMS_SR830_KEYS", ("830_a",)):
            # 830_b is now considered invalid
            with self.assertRaisesRegex(ValueError, "PPMS SR830 slot is invalid"):
                app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 1, ("830_a", "830_b"))
            # 830_a alone passes
            res = app.validate_ppms_transport_scan_settings(1.0, 100.0, 10.0, 1, 1, ("830_a",))
            self.assertEqual(res["active_lockins"], ("830_a",))


class TestBehavioralEquivalence(unittest.TestCase):
    """Direct comparison between ReferenceOriginalValidation and new extracted function."""

    def test_equivalence_matrix(self):
        cases = [
            (0.001, 13.7, 50.0, 1, 2, ("830_a",), False, 1),
            (1.0, 317.3, 105.0, 1, 1, ("830_a", "830_b"), False, 1),
            (10.0, 1000.0, 0.1, 2, 3, ("830_b", "830_c"), False, 2),
            (0.1, 17.3, 10.0, 1, 1, (), True, 1),
        ]
        for current, freq, comp, ha, hb, active, no_lock, hc in cases:
            ref = ReferenceOriginalValidation.validate(current, freq, comp, ha, hb, active, no_lock, hc)
            ext = validate_transport_scan_settings(current, freq, comp, ha, hb, active, no_lock, hc)
            leg = app.validate_ppms_transport_scan_settings(current, freq, comp, ha, hb, active, no_lock, hc)
            self.assertEqual(ref, ext)
            self.assertEqual(ref, leg)

    def test_equivalence_exceptions(self):
        error_cases = [
            (0.0, 100.0, 10.0, 1, 1, ("830_a",), False, 1),
            (80.0, 100.0, 10.0, 1, 1, ("830_a",), False, 1),
            (1.0, 0.0001, 10.0, 1, 1, ("830_a",), False, 1),
            (1.0, 100.0, 0.05, 1, 1, ("830_a",), False, 1),
            (1.0, 100.0, 10.0, 0, 1, ("830_a",), False, 1),
            (1.0, 60000.0, 10.0, 2, 1, ("830_a",), False, 1),
            (1.0, 100.0, 10.0, 1, 1, (), False, 1),
            (1.0, 100.0, 10.0, 1, 1, ("bad_slot",), False, 1),
        ]
        for current, freq, comp, ha, hb, active, no_lock, hc in error_cases:
            with self.assertRaises(ValueError) as ref_err:
                ReferenceOriginalValidation.validate(current, freq, comp, ha, hb, active, no_lock, hc)
            with self.assertRaises(ValueError) as ext_err:
                validate_transport_scan_settings(current, freq, comp, ha, hb, active, no_lock, hc)
            with self.assertRaises(ValueError) as leg_err:
                app.validate_ppms_transport_scan_settings(current, freq, comp, ha, hb, active, no_lock, hc)
            self.assertEqual(str(ref_err.exception), str(ext_err.exception))
            self.assertEqual(str(ref_err.exception), str(leg_err.exception))

    def test_peak_current_boundary_equivalence_grid(self):
        """Compare behavior against original implementation for representable floats at and around 0.105 A peak limit."""
        # Theoretical threshold where peak == 0.105 A:
        # peak = math.sqrt(2.0) * current_rms_ma * 1e-3
        v_exact = 105.0 / math.sqrt(2.0)

        # Dense grid of representable floating-point values at and around the threshold
        test_points = [
            v_exact - 1.0,
            v_exact - 0.01,
            v_exact - 1e-4,
            v_exact - 1e-6,
            v_exact - 1e-9,
            v_exact - 1e-12,
            math.nextafter(v_exact, 0.0),
            v_exact,
            math.nextafter(v_exact, 100.0),
            v_exact + 1e-12,
            v_exact + 1e-9,
            v_exact + 1e-6,
            v_exact + 1e-4,
            v_exact + 0.01,
            v_exact + 1.0,
        ]

        for current in test_points:
            peak = math.sqrt(2.0) * current * 1e-3
            should_pass = (peak <= 0.105)

            if should_pass:
                ref = ReferenceOriginalValidation.validate(current, 100.0, 10.0, 1, 1)
                ext = validate_transport_scan_settings(current, 100.0, 10.0, 1, 1)
                leg = app.validate_ppms_transport_scan_settings(current, 100.0, 10.0, 1, 1)
                self.assertEqual(ref, ext)
                self.assertEqual(ref, leg)
                self.assertLessEqual(ext["peak_a"], 0.105)
            else:
                with self.assertRaises(ValueError) as ref_err:
                    ReferenceOriginalValidation.validate(current, 100.0, 10.0, 1, 1)
                with self.assertRaises(ValueError) as ext_err:
                    validate_transport_scan_settings(current, 100.0, 10.0, 1, 1)
                with self.assertRaises(ValueError) as leg_err:
                    app.validate_ppms_transport_scan_settings(current, 100.0, 10.0, 1, 1)
                self.assertEqual(str(ref_err.exception), str(ext_err.exception))
                self.assertEqual(str(ref_err.exception), str(leg_err.exception))
                self.assertIn("6221 sine-wave peak must not exceed 105 mA", str(ext_err.exception))


class TestHardwareSafetyGuards(unittest.TestCase):
    """AC5: Ensure invalid settings reject before prohibited hardware operations."""

    def test_worker_configure_transport_scan_aborts_before_hardware_commands(self):
        """_configure_ppms_transport_scan must fail at validation before calling *RST or safe_output_off."""
        harness = object.__new__(app.CombinedControlApp)
        harness.ppms_field_scan_stop_event = mock.Mock()
        harness.ppms_field_scan_stop_event.is_set.return_value = False
        harness.ppms_last_current_trip = False
        harness._ppms_clear_sr830_range_floor = mock.Mock()

        mock_6221 = mock.Mock()
        mock_6221.connected = True
        mock_lockin = mock.Mock()
        mock_lockin.connected = True

        harness.ppms_instrument_controllers = {
            "6221": mock_6221,
            "830_a": mock_lockin,
        }

        # Invalid settings: 80 mA RMS exceeds 105 mA peak
        invalid_settings = {
            "current_rms_ma": 80.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a",),
        }

        with self.assertRaises(ValueError):
            harness._configure_ppms_transport_scan(invalid_settings)

        # Prohibited hardware operations must NOT have occurred
        mock_6221.safe_output_off.assert_not_called()
        mock_6221.instrument.write.assert_not_called()

    def test_worker_update_transport_current_aborts_before_scpi(self):
        """_update_ppms_transport_current must fail at validation before SOUR:WAVE:AMPL."""
        harness = object.__new__(app.CombinedControlApp)
        harness.ppms_field_scan_stop_event = mock.Mock()
        harness.ppms_field_scan_stop_event.is_set.return_value = False
        harness.closing = False
        harness._ppms_write_6221_checked = mock.Mock()

        # Invalid settings: current <= 0
        invalid_settings = {
            "current_rms_ma": -5.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a",),
            "continuous_sweep_peak_a": 0.05,
        }

        with self.assertRaises(ValueError):
            harness._update_ppms_transport_current(invalid_settings)

        harness._ppms_write_6221_checked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
