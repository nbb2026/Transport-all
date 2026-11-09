"""Regression tests for shared harmonic calculations and scheduling (transport.common.harmonics)."""

import inspect
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
    DEFAULT_HARMONIC_CHOICES,
    DEFAULT_HARMONIC_LABELS,
    DEFAULT_HARMONIC_MODE_ORDERS,
    DEFAULT_HARMONIC_ORDERS,
    DEFAULT_SR830_HARMONIC_SETTING_KEYS,
    active_lockins_for_pass,
    parse_harmonic_mode,
    schedule_harmonic_passes,
)


class DummyVar:
    """Minimal Tk-like variable stub for headless testing."""

    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


class ReferenceOriginalImplementation:
    """Reference implementation capturing the exact original logic prior to refactoring."""

    @staticmethod
    def original_ppms_harmonic_orders(panel, key: str) -> tuple[int, ...]:
        variable = panel._ppms_harmonic_var(key)
        value = str(variable.get()).strip() if variable is not None else "1"
        if value not in app.PPMS_HARMONIC_MODE_ORDERS:
            raise ValueError("Select harmonic 1, 2, 3, 1+2 or 1+2+3")
        return app.PPMS_HARMONIC_MODE_ORDERS[value]

    @staticmethod
    def original_ppms_harmonic_passes(panel, settings):
        schedules = {key: panel._ppms_harmonic_orders(key) for key in settings["active_lockins"]}
        passes = []
        for index in range(max((len(orders) for orders in schedules.values()), default=1)):
            config = dict(settings, harmonic_pass=index + 1)
            config["active_lockins"] = tuple(k for k, orders in schedules.items() if index < len(orders))
            for key in config["active_lockins"]:
                config[app.PPMS_SR830_HARMONIC_SETTING_KEYS[key]] = schedules[key][index]
            app.validate_ppms_transport_scan_settings(
                config["current_rms_ma"], config["frequency_hz"], config["compliance_v"],
                config["harmonic_a"], config["harmonic_b"], config["active_lockins"],
                allow_no_lockins=bool(config.get("allow_no_lockins", False)),
                harmonic_c=config["harmonic_c"])
            passes.append(config)
        return passes


class DummyPanel:
    """Mock panel instance for testing CombinedControlApp and RTEPanel harmonic methods."""

    def __init__(self, harmonic_choices=None):
        self.ppms_transport_harmonic_a_var = DummyVar("1")
        self.ppms_transport_harmonic_b_var = DummyVar("2")
        self.ppms_transport_harmonic_c_var = DummyVar("3")
        if harmonic_choices:
            for key, choice in harmonic_choices.items():
                attr = app.PPMS_SR830_HARMONIC_ATTRS[key]
                setattr(self, attr, DummyVar(choice))

    _ppms_harmonic_var = app.CombinedControlApp._ppms_harmonic_var
    _ppms_harmonic_orders = app.CombinedControlApp._ppms_harmonic_orders
    _ppms_harmonic_value = app.CombinedControlApp._ppms_harmonic_value
    _ppms_harmonic_passes = app.CombinedControlApp._ppms_harmonic_passes
    _rte_harmonic_orders = app.RTEPanel._rte_harmonic_orders
    _rte_harmonic_passes = app.RTEPanel._rte_harmonic_passes


class TestTransportCommonHarmonics(unittest.TestCase):
    def test_default_constants(self):
        self.assertEqual(DEFAULT_HARMONIC_ORDERS, (1, 2, 3))
        self.assertEqual(
            DEFAULT_HARMONIC_MODE_ORDERS,
            {"1": (1,), "2": (2,), "3": (3,), "1+2": (1, 2), "1+2+3": (1, 2, 3)},
        )
        self.assertEqual(DEFAULT_HARMONIC_CHOICES, (1, 2, 3, "1+2", "1+2+3"))
        self.assertEqual(
            DEFAULT_HARMONIC_LABELS,
            {1: "1st harmonic", 2: "2nd harmonic", 3: "3rd harmonic"},
        )
        self.assertEqual(
            DEFAULT_SR830_HARMONIC_SETTING_KEYS,
            {"830_a": "harmonic_a", "830_b": "harmonic_b", "830_c": "harmonic_c"},
        )
        self.assertEqual(app.PPMS_HARMONIC_ORDERS, (1, 2, 3))
        self.assertEqual(app.PPMS_HARMONIC_CHOICES, (1, 2, 3, "1+2", "1+2+3"))
        self.assertEqual(app.PPMS_HARMONIC_LABELS[1], "1st harmonic")
        self.assertEqual(app.PPMS_SR830_HARMONIC_SETTING_KEYS["830_a"], "harmonic_a")

    def test_independent_dictionaries_prevent_cross_mutation(self):
        """Correction 2: Module default dictionaries cannot accidentally mutate the application's configuration."""
        self.assertIsNot(app.PPMS_HARMONIC_LABELS, DEFAULT_HARMONIC_LABELS)
        self.assertIsNot(app.PPMS_ZURICH_MODE_ORDERS, DEFAULT_HARMONIC_MODE_ORDERS)
        self.assertIsNot(app.PPMS_SR830_HARMONIC_SETTING_KEYS, DEFAULT_SR830_HARMONIC_SETTING_KEYS)

        # Mutating app's dictionary does not affect default in transport.common.harmonics
        orig_labels = dict(app.PPMS_HARMONIC_LABELS)
        try:
            app.PPMS_HARMONIC_LABELS[99] = "99th harmonic"
            self.assertNotIn(99, DEFAULT_HARMONIC_LABELS)
        finally:
            app.PPMS_HARMONIC_LABELS.clear()
            app.PPMS_HARMONIC_LABELS.update(orig_labels)

        # Mutating default in transport.common.harmonics does not affect app's dictionary
        orig_default_labels = dict(DEFAULT_HARMONIC_LABELS)
        try:
            DEFAULT_HARMONIC_LABELS[99] = "99th harmonic"
            self.assertNotIn(99, app.PPMS_HARMONIC_LABELS)
        finally:
            DEFAULT_HARMONIC_LABELS.clear()
            DEFAULT_HARMONIC_LABELS.update(orig_default_labels)

        # Setting keys independence
        orig_keys = dict(app.PPMS_SR830_HARMONIC_SETTING_KEYS)
        try:
            app.PPMS_SR830_HARMONIC_SETTING_KEYS["custom"] = "harmonic_custom"
            self.assertNotIn("custom", DEFAULT_SR830_HARMONIC_SETTING_KEYS)
        finally:
            app.PPMS_SR830_HARMONIC_SETTING_KEYS.clear()
            app.PPMS_SR830_HARMONIC_SETTING_KEYS.update(orig_keys)

    def test_no_misleading_ppms_aliases_in_transport_common(self):
        import transport.common as common
        import transport.common.harmonics as harmonics

        for name in (
            "_ppms_harmonic_orders",
            "_ppms_harmonic_passes",
            "_rte_harmonic_orders",
            "_rte_harmonic_passes",
            "PPMS_HARMONIC_ORDERS",
            "PPMS_HARMONIC_MODE_ORDERS",
        ):
            self.assertFalse(hasattr(common, name), f"Misleading alias {name} found in transport.common")
            self.assertFalse(hasattr(harmonics, name), f"Misleading alias {name} found in transport.common.harmonics")

    def test_original_instance_method_signatures_preserved(self):
        sig_ppms_orders = inspect.signature(app.CombinedControlApp._ppms_harmonic_orders)
        self.assertEqual(list(sig_ppms_orders.parameters.keys()), ["self", "key"])

        sig_ppms_passes = inspect.signature(app.CombinedControlApp._ppms_harmonic_passes)
        self.assertEqual(list(sig_ppms_passes.parameters.keys()), ["self", "settings"])

        sig_rte_orders = inspect.signature(app.RTEPanel._rte_harmonic_orders)
        self.assertEqual(list(sig_rte_orders.parameters.keys()), ["self", "key"])

        sig_rte_passes = inspect.signature(app.RTEPanel._rte_harmonic_passes)
        self.assertEqual(list(sig_rte_passes.parameters.keys()), ["self", "settings"])

    def test_parse_harmonic_mode_valid(self):
        cases = [
            ("1", (1,)),
            (1, (1,)),
            ("2", (2,)),
            (2, (2,)),
            ("3", (3,)),
            (3, (3,)),
            ("1+2", (1, 2)),
            ("1+2+3", (1, 2, 3)),
            (" 1 ", (1,)),
            (" 1+2 ", (1, 2)),
            ("\t1+2+3\n", (1, 2, 3)),
        ]
        for mode_input, expected in cases:
            with self.subTest(mode_input=mode_input):
                self.assertEqual(parse_harmonic_mode(mode_input), expected)

    def test_parse_harmonic_mode_invalid(self):
        invalid_cases = [
            "0",
            0,
            "4",
            4,
            "1+3",
            "2+1",
            "3+2+1",
            "invalid",
            "",
            "   ",
            None,
            1.5,
            [1, 2],
        ]
        for bad_input in invalid_cases:
            with self.subTest(bad_input=bad_input):
                with self.assertRaises(ValueError) as ctx:
                    parse_harmonic_mode(bad_input)
                self.assertEqual(str(ctx.exception), "Select harmonic 1, 2, 3, 1+2 or 1+2+3")

    def test_dynamic_replacement_returns_custom_type_unchanged(self):
        """Correction 1: Preserve exact legacy return semantics when dynamically substituted."""
        # Non-tuple sequence (list) returned unchanged without coercion to tuple
        custom_mapping = {"custom_list": [1, 2], "custom_str": "123"}
        self.assertEqual(parse_harmonic_mode("custom_list", mode_orders=custom_mapping), [1, 2])
        self.assertIsInstance(parse_harmonic_mode("custom_list", mode_orders=custom_mapping), list)
        self.assertEqual(parse_harmonic_mode("custom_str", mode_orders=custom_mapping), "123")

        # Via panel method and app monkeypatching
        panel = DummyPanel({"830_a": "custom_mode"})
        with mock.patch.object(app, "PPMS_HARMONIC_MODE_ORDERS", {"custom_mode": [2, 3]}):
            orders = panel._ppms_harmonic_orders("830_a")
            self.assertEqual(orders, [2, 3])
            self.assertIsInstance(orders, list)

    def test_active_lockins_for_pass(self):
        schedules = {
            "830_a": (1, 2),
            "830_b": (1, 2, 3),
            "830_c": (3,),
        }
        self.assertEqual(active_lockins_for_pass(schedules, 0), ("830_a", "830_b", "830_c"))
        self.assertEqual(active_lockins_for_pass(schedules, 1), ("830_a", "830_b"))
        self.assertEqual(active_lockins_for_pass(schedules, 2), ("830_b",))
        self.assertEqual(active_lockins_for_pass(schedules, 3), ())

    def test_schedule_harmonic_passes_without_validation(self):
        settings = {
            "current_rms_ma": 1.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a", "830_b"),
        }
        schedules = {
            "830_a": (1, 2),
            "830_b": (1, 2, 3),
        }
        passes = schedule_harmonic_passes(settings, schedules)
        self.assertEqual(len(passes), 3)

        self.assertEqual(passes[0]["harmonic_pass"], 1)
        self.assertEqual(passes[0]["active_lockins"], ("830_a", "830_b"))
        self.assertEqual(passes[0]["harmonic_a"], 1)
        self.assertEqual(passes[0]["harmonic_b"], 1)

        self.assertEqual(passes[1]["harmonic_pass"], 2)
        self.assertEqual(passes[1]["active_lockins"], ("830_a", "830_b"))
        self.assertEqual(passes[1]["harmonic_a"], 2)
        self.assertEqual(passes[1]["harmonic_b"], 2)

        self.assertEqual(passes[2]["harmonic_pass"], 3)
        self.assertEqual(passes[2]["active_lockins"], ("830_b",))
        # 830_a dropped out: keeps pass 1's harmonic_a value in shallow copy
        self.assertEqual(passes[2]["harmonic_a"], 1)
        self.assertEqual(passes[2]["harmonic_b"], 3)

    def test_schedule_harmonic_passes_does_not_mutate_input_settings(self):
        settings = {
            "current_rms_ma": 1.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a", "830_b"),
        }
        original_settings = dict(settings)
        schedules = {"830_a": (1, 2), "830_b": (1,)}
        passes = schedule_harmonic_passes(settings, schedules)
        self.assertEqual(settings, original_settings)
        self.assertNotIn("harmonic_pass", settings)
        self.assertIsNot(passes[0], settings)
        self.assertIsNot(passes[1], settings)
        self.assertIsNot(passes[0], passes[1])

    def test_pass_dictionaries_remain_independent_shallow_copies(self):
        """Correction 3: Pass dictionaries remain independent shallow copies."""
        settings = {
            "current_rms_ma": 1.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a", "830_b"),
        }
        schedules = {"830_a": (1, 2), "830_b": (1, 2)}
        passes = schedule_harmonic_passes(settings, schedules)

        # Mutating a field in pass 0 does not mutate pass 1 or settings
        passes[0]["current_rms_ma"] = 999.0
        passes[0]["active_lockins"] = ("mutated",)
        self.assertEqual(passes[1]["current_rms_ma"], 1.0)
        self.assertEqual(passes[1]["active_lockins"], ("830_a", "830_b"))
        self.assertEqual(settings["current_rms_ma"], 1.0)
        self.assertEqual(settings["active_lockins"], ("830_a", "830_b"))

    def test_lockin_ordering_and_dropout_preservation(self):
        """Correction 3: Lock-in ordering, dropout and per-pass validation remain unchanged."""
        panel = DummyPanel({"830_a": "1", "830_b": "1+2", "830_c": "1+2+3"})
        # Arbitrary non-standard order in active_lockins
        settings = {
            "current_rms_ma": 0.5,
            "frequency_hz": 200.0,
            "compliance_v": 5.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_b", "830_a", "830_c"),
            "allow_no_lockins": False,
        }
        passes = panel._ppms_harmonic_passes(settings)
        self.assertEqual(len(passes), 3)

        # Pass 1: exact ordering from settings preserved
        self.assertEqual(passes[0]["active_lockins"], ("830_b", "830_a", "830_c"))
        self.assertEqual(passes[0]["harmonic_b"], 1)
        self.assertEqual(passes[0]["harmonic_a"], 1)
        self.assertEqual(passes[0]["harmonic_c"], 1)

        # Pass 2: 830_a finished, drops out; 830_b and 830_c remain in relative order
        self.assertEqual(passes[1]["active_lockins"], ("830_b", "830_c"))
        self.assertEqual(passes[1]["harmonic_b"], 2)
        self.assertEqual(passes[1]["harmonic_c"], 2)

        # Pass 3: 830_b finished, drops out; 830_c remains alone
        self.assertEqual(passes[2]["active_lockins"], ("830_c",))
        self.assertEqual(passes[2]["harmonic_c"], 3)

    def test_schedule_harmonic_passes_empty_schedules_no_lockins(self):
        settings = {
            "current_rms_ma": 1.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": (),
            "allow_no_lockins": True,
        }
        passes = schedule_harmonic_passes(settings, {})
        self.assertEqual(len(passes), 1)
        self.assertEqual(passes[0]["harmonic_pass"], 1)
        self.assertEqual(passes[0]["active_lockins"], ())

    def test_schedule_harmonic_passes_validation_callback(self):
        settings = {
            "current_rms_ma": 1.0,
            "frequency_hz": 100.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a",),
        }
        schedules = {"830_a": (1, 2)}
        validated_configs = []

        def validator(cfg):
            validated_configs.append(cfg.copy())

        passes = schedule_harmonic_passes(settings, schedules, validator=validator)
        self.assertEqual(len(passes), 2)
        self.assertEqual(len(validated_configs), 2)
        self.assertEqual(validated_configs[0]["harmonic_pass"], 1)
        self.assertEqual(validated_configs[1]["harmonic_pass"], 2)

    def test_validation_failure_prevents_scan_planning_from_completing(self):
        """Correction 3: Validation failures prevent scan planning from completing."""
        panel = DummyPanel({"830_a": "1+2+3"})
        # 40 kHz * 3rd harmonic = 120 kHz > 102 kHz ceiling
        settings = {
            "current_rms_ma": 1.0,
            "frequency_hz": 40000.0,
            "compliance_v": 10.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a",),
            "allow_no_lockins": False,
        }

        # _ppms_harmonic_passes must abort and raise ValueError
        with self.assertRaises(ValueError) as ctx:
            panel._ppms_harmonic_passes(settings)
        self.assertIn("102 kHz", str(ctx.exception))

        # _rte_harmonic_passes must abort and raise ValueError
        with self.assertRaises(ValueError) as ctx:
            panel._rte_harmonic_passes(settings)
        self.assertIn("102 kHz", str(ctx.exception))

        # Pass 1 validation failure (e.g. invalid current) also aborts immediately
        bad_settings = dict(settings, current_rms_ma=-5.0, frequency_hz=100.0)
        with self.assertRaises(ValueError) as ctx2:
            panel._ppms_harmonic_passes(bad_settings)
        self.assertIn("must be greater than 0 mA RMS", str(ctx2.exception))

    def test_equivalence_with_original_implementation(self):
        test_modes = [
            {"830_a": "1", "830_b": "2", "830_c": "3"},
            {"830_a": "1+2", "830_b": "1+2+3", "830_c": "1"},
            {"830_a": "1+2+3", "830_b": "2", "830_c": "3"},
        ]
        base_settings = {
            "current_rms_ma": 0.5,
            "frequency_hz": 133.7,
            "compliance_v": 5.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "allow_no_lockins": False,
        }

        for choices in test_modes:
            panel = DummyPanel(choices)
            # Test order extraction equivalence
            for key in app.PPMS_SR830_KEYS:
                ref_orders = ReferenceOriginalImplementation.original_ppms_harmonic_orders(panel, key)
                extracted_orders = panel._ppms_harmonic_orders(key)
                rte_orders = panel._rte_harmonic_orders(key)
                self.assertEqual(ref_orders, extracted_orders)
                self.assertEqual(ref_orders, rte_orders)

            # Test pass scheduling equivalence
            for active in (("830_a",), ("830_a", "830_b"), ("830_a", "830_b", "830_c")):
                settings = dict(base_settings, active_lockins=active)
                ref_passes = ReferenceOriginalImplementation.original_ppms_harmonic_passes(panel, settings)
                extracted_passes = panel._ppms_harmonic_passes(settings)
                rte_passes = panel._rte_harmonic_passes(settings)

                self.assertEqual(ref_passes, extracted_passes)
                self.assertEqual(ref_passes, rte_passes)

    def test_rte_delegation_behavior(self):
        panel = DummyPanel({"830_a": "1+2"})
        self.assertEqual(panel._rte_harmonic_orders("830_a"), (1, 2))
        settings = {
            "current_rms_ma": 0.5,
            "frequency_hz": 100.0,
            "compliance_v": 5.0,
            "harmonic_a": 1,
            "harmonic_b": 1,
            "harmonic_c": 1,
            "active_lockins": ("830_a",),
            "allow_no_lockins": False,
        }
        passes = panel._rte_harmonic_passes(settings)
        self.assertEqual(len(passes), 2)
        self.assertEqual(passes[0]["harmonic_a"], 1)
        self.assertEqual(passes[1]["harmonic_a"], 2)

    def test_monkeypatch_preservation(self):
        panel = DummyPanel({"830_a": "custom_mode"})
        custom_modes = dict(app.PPMS_HARMONIC_MODE_ORDERS, custom_mode=(2, 3))
        with mock.patch.object(app, "PPMS_HARMONIC_MODE_ORDERS", custom_modes):
            orders = panel._ppms_harmonic_orders("830_a")
            self.assertEqual(orders, (2, 3))

        # Test monkeypatching panel._rte_harmonic_passes as existing tests do
        mock_passes = [{"mock_key": "mock_val"}]
        with mock.patch.object(panel, "_rte_harmonic_passes", return_value=mock_passes):
            self.assertEqual(panel._rte_harmonic_passes({}), mock_passes)


if __name__ == "__main__":
    unittest.main()
