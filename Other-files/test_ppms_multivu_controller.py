"""Regression tests for the extracted PPMSMultiVuReadbackController.

Verifies:
1. Module exports and backward compatibility via Transport_all and transport.ppms.
2. Endpoint validation with normal inputs, invalid IPs, invalid ports, and socket.getaddrinfo errors.
3. MultiPyVu connection lifecycle (connect, re-connect, disconnect, idempotent disconnect).
4. Normal readbacks, non-finite responses, and malformed data handling.
5. Safety guardrail enforcement for temperature and magnetic field commands.
6. Modern vs. legacy MultiPyVu enum resolution and missing enum error handling.
7. Mocked MultiPyVu API robustness:
   - exception propagation across get_temperature, get_field, set_temperature, set_field
   - connection failure and cleanup
   - socket and SDK timeouts
   - malformed non-numeric data
   - uncertain command outcome handling (timeout without resend/retry)
"""

from __future__ import annotations

import enum
import math
import socket
import sys
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

# Ensure repository root is on sys.path for direct test execution
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import Transport_all as app
import transport.ppms as ppms_pkg
import transport.ppms.controllers as controllers_pkg
from transport.ppms.controllers.multivu import PPMSMultiVuReadbackController


class DummyStatusEnum(enum.Enum):
    Stable = 1
    Tracking = 2
    Holding = 3
    Chasing = 4


class TestMultiVuControllerBasics(unittest.TestCase):
    """Test module exports, backward compatibility, and endpoint validation."""

    def test_module_exports_and_backward_compatibility(self):
        """Verify PPMSMultiVuReadbackController is exported identically across all access paths."""
        self.assertIs(app.PPMSMultiVuReadbackController, PPMSMultiVuReadbackController)
        self.assertIs(ppms_pkg.PPMSMultiVuReadbackController, PPMSMultiVuReadbackController)
        self.assertIs(controllers_pkg.PPMSMultiVuReadbackController, PPMSMultiVuReadbackController)
        self.assertIn("PPMSMultiVuReadbackController", ppms_pkg.__all__)
        self.assertIn("PPMSMultiVuReadbackController", controllers_pkg.__all__)

    def test_validate_endpoint_valid_inputs(self):
        """Verify validate_endpoint accepts valid IP addresses, hostnames, and strips whitespace."""
        # IPv4 string
        host, port = PPMSMultiVuReadbackController.validate_endpoint("192.168.137.5", 5000)
        self.assertEqual(host, "192.168.137.5")
        self.assertEqual(port, 5000)

        # Localhost string with whitespace and string port
        host, port = PPMSMultiVuReadbackController.validate_endpoint("  127.0.0.1  ", " 11000 ")
        self.assertEqual(host, "127.0.0.1")
        self.assertEqual(port, 11000)

        # Boundary ports
        _, port1 = PPMSMultiVuReadbackController.validate_endpoint("127.0.0.1", 1)
        self.assertEqual(port1, 1)
        _, port65535 = PPMSMultiVuReadbackController.validate_endpoint("127.0.0.1", 65535)
        self.assertEqual(port65535, 65535)

    def test_validate_endpoint_invalid_inputs(self):
        """Verify validate_endpoint rejects empty host, bad port numbers, and getaddrinfo failures."""
        # Empty host
        with self.assertRaisesRegex(ValueError, "PPMS IP address cannot be empty"):
            PPMSMultiVuReadbackController.validate_endpoint("", 5000)
        with self.assertRaisesRegex(ValueError, "PPMS IP address cannot be empty"):
            PPMSMultiVuReadbackController.validate_endpoint("   ", 5000)

        # Port out of range
        with self.assertRaisesRegex(ValueError, "PPMS TCP port must be between 1 and 65535"):
            PPMSMultiVuReadbackController.validate_endpoint("127.0.0.1", 0)

        # Negative port or out of range port caught by getaddrinfo / validation
        with self.assertRaises(ValueError):
            PPMSMultiVuReadbackController.validate_endpoint("127.0.0.1", -5)
        with self.assertRaises(ValueError):
            PPMSMultiVuReadbackController.validate_endpoint("127.0.0.1", 65536)

        # Non-numeric port
        with self.assertRaisesRegex(ValueError, "PPMS IP address or port is invalid"):
            PPMSMultiVuReadbackController.validate_endpoint("127.0.0.1", "bad_port")

        # Socket getaddrinfo resolution failure
        with mock.patch("socket.getaddrinfo", side_effect=socket.gaierror(8, "nodename nor servname provided")):
            with self.assertRaisesRegex(ValueError, "PPMS IP address or port is invalid: invalid.host:5000"):
                PPMSMultiVuReadbackController.validate_endpoint("invalid.host", 5000)


class FakeMultiPyVuClient:
    """Mock MultiPyVu Client mimicking Quantum Design SDK object hierarchies."""

    def __init__(
        self,
        temperature_reading=(300.0, "Stable"),
        field_reading=(0.0, "Holding"),
        modern_enums: bool = True,
    ):
        self.temperature_reading = temperature_reading
        self.field_reading = field_reading
        self.is_open = False
        self.closed_client = False
        self.closed_server = False

        self.set_temperature_calls: list[tuple] = []
        self.set_field_calls: list[tuple] = []

        if modern_enums:
            self.temperature = types.SimpleNamespace(
                approach_mode=types.SimpleNamespace(
                    fast_settle="fast_settle_enum",
                    no_overshoot="no_overshoot_enum",
                )
            )
            self.field = types.SimpleNamespace(
                approach_mode=types.SimpleNamespace(
                    linear="linear_enum",
                    no_overshoot="no_overshoot_enum",
                    oscillate="oscillate_enum",
                ),
                driven_mode=types.SimpleNamespace(
                    persistent="persistent_enum",
                    driven="driven_enum",
                ),
            )
        else:
            # Legacy enum organization
            self.temp_approach_mode = types.SimpleNamespace(
                fast_settle="legacy_fast_settle",
                no_overshoot="legacy_no_overshoot",
            )
            self.field_approach_mode = types.SimpleNamespace(
                linear="legacy_linear",
                no_overshoot="legacy_no_overshoot",
                oscillate="legacy_oscillate",
            )
            self.field_driven_mode = types.SimpleNamespace(
                persistent="legacy_persistent",
                driven="legacy_driven",
            )

    def open(self):
        self.is_open = True

    def close_client(self):
        self.closed_client = True
        self.is_open = False

    def close_server(self):
        self.closed_server = True

    def get_temperature(self):
        return self.temperature_reading

    def get_field(self):
        return self.field_reading

    def set_temperature(self, target_k, rate_k_min, approach):
        self.set_temperature_calls.append((target_k, rate_k_min, approach))

    def set_field(self, target_oe, rate_oe_s, approach, mode):
        self.set_field_calls.append((target_oe, rate_oe_s, approach, mode))


class TestMultiVuControllerLifecycleAndOperations(unittest.TestCase):
    """Test controller connect, readback, command issuing, and disconnect behavior."""

    def setUp(self):
        self.logs: list[str] = []
        self.controller = PPMSMultiVuReadbackController(self.logs.append)

    def test_missing_multipyvu_library(self):
        """Verify informative error message when MultiPyVu cannot be imported."""
        with mock.patch("importlib.import_module", side_effect=ImportError("No module named 'MultiPyVu'")):
            with self.assertRaisesRegex(RuntimeError, "Quantum Design MultiPyVu is missing"):
                self.controller.connect("127.0.0.1", 5000)
        self.assertFalse(self.controller.connected)

    def test_successful_connect_and_readback(self):
        """Verify connection initialization, logging, and initial readback."""
        fake_client = FakeMultiPyVuClient(
            temperature_reading=(10.5, DummyStatusEnum.Stable),
            field_reading=(5000.0, DummyStatusEnum.Holding),
        )
        fake_module = types.SimpleNamespace(Client=mock.Mock(return_value=fake_client))

        with mock.patch("importlib.import_module", return_value=fake_module):
            result = self.controller.connect("127.0.0.1", 5000)

        fake_module.Client.assert_called_once_with(host="127.0.0.1", port=5000)
        self.assertTrue(fake_client.is_open)
        self.assertTrue(self.controller.connected)
        self.assertEqual(self.controller.host, "127.0.0.1")
        self.assertEqual(self.controller.port, 5000)
        self.assertIn("PPMS MultiVu connected: 127.0.0.1:5000", self.logs)

        self.assertEqual(result["temperature_k"], 10.5)
        self.assertEqual(result["temperature_status"], "Stable")
        self.assertEqual(result["field_oe"], 5000.0)
        self.assertEqual(result["field_status"], "Holding")

    def test_reconnect_returns_cached_connection(self):
        """Verify calling connect when already connected performs a readback without re-opening."""
        fake_client = FakeMultiPyVuClient(
            temperature_reading=(20.0, "Stable"),
            field_reading=(100.0, "Holding"),
        )
        self.controller.client = fake_client
        self.controller.host = "127.0.0.1"
        self.controller.port = 5000

        with mock.patch("importlib.import_module") as mock_import:
            result = self.controller.connect("127.0.0.1", 5000)
            mock_import.assert_not_called()

        self.assertEqual(result["temperature_k"], 20.0)
        self.assertEqual(result["field_oe"], 100.0)

    def test_connect_failure_cleans_up_client(self):
        """Verify client.close_client is called and state reset when client.open fails."""
        fake_client = FakeMultiPyVuClient()
        fake_client.open = mock.Mock(side_effect=ConnectionRefusedError("Connection refused"))
        fake_module = types.SimpleNamespace(Client=mock.Mock(return_value=fake_client))

        with mock.patch("importlib.import_module", return_value=fake_module):
            with self.assertRaises(ConnectionRefusedError):
                self.controller.connect("127.0.0.1", 5000)

        self.assertTrue(fake_client.closed_client)
        self.assertIsNone(self.controller.client)
        self.assertFalse(self.controller.connected)

    def test_connect_failure_during_initial_readback(self):
        """Verify cleanup occurs if read_environment fails immediately after open."""
        fake_client = FakeMultiPyVuClient(temperature_reading=(float("nan"), "Stable"))
        fake_module = types.SimpleNamespace(Client=mock.Mock(return_value=fake_client))

        with mock.patch("importlib.import_module", return_value=fake_module):
            with self.assertRaisesRegex(RuntimeError, "non-finite readings"):
                self.controller.connect("127.0.0.1", 5000)

        self.assertTrue(fake_client.closed_client)
        self.assertIsNone(self.controller.client)
        self.assertFalse(self.controller.connected)

    def test_disconnect_behavior(self):
        """Verify disconnect closes client only, never server, and is idempotent."""
        fake_client = FakeMultiPyVuClient()
        fake_client.open()
        self.controller.client = fake_client
        self.controller.host = "127.0.0.1"
        self.controller.port = 5000

        self.controller.disconnect()

        self.assertTrue(fake_client.closed_client)
        self.assertFalse(fake_client.closed_server)
        self.assertIsNone(self.controller.client)
        self.assertFalse(self.controller.connected)
        self.assertEqual(self.controller.host, "")
        self.assertEqual(self.controller.port, 0)
        self.assertIn("PPMS MultiVu client disconnected (current setpoints unchanged)", self.logs)

        # Idempotent second call should not crash or call closed client
        self.controller.disconnect()

    def test_read_environment_when_disconnected(self):
        """Verify read_environment raises RuntimeError if not connected."""
        with self.assertRaisesRegex(RuntimeError, "PPMS MultiVu is not connected"):
            self.controller.read_environment()

    def test_read_environment_non_finite_rejection(self):
        """Verify NaN and Inf temperature and field values raise RuntimeError."""
        fake_client = FakeMultiPyVuClient(temperature_reading=(float("nan"), "Stable"))
        self.controller.client = fake_client
        with self.assertRaisesRegex(RuntimeError, "PPMS returned non-finite readings"):
            self.controller.read_environment()

        fake_client.temperature_reading = (300.0, "Stable")
        fake_client.field_reading = (float("inf"), "Holding")
        with self.assertRaisesRegex(RuntimeError, "PPMS returned non-finite readings"):
            self.controller.read_environment()

    def test_set_temperature_normal_and_guardrails(self):
        """Verify set_temperature guardrails, approach resolution, and execution."""
        fake_client = FakeMultiPyVuClient(
            temperature_reading=(50.0, "Stable"),
            field_reading=(0.0, "Holding"),
            modern_enums=True,
        )
        self.controller.client = fake_client

        # Disconnected check
        unconnected_ctrl = PPMSMultiVuReadbackController(lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "PPMS MultiVu is not connected"):
            unconnected_ctrl.set_temperature(100.0, 5.0, 0)

        # Valid fast_settle (0)
        res = self.controller.set_temperature(75.0, 5.0, 0)
        self.assertEqual(fake_client.set_temperature_calls[-1], (75.0, 5.0, "fast_settle_enum"))
        self.assertEqual(res["temperature_k"], 50.0)

        # Valid no_overshoot (1)
        self.controller.set_temperature(60.0, 2.0, 1)
        self.assertEqual(fake_client.set_temperature_calls[-1], (60.0, 2.0, "no_overshoot_enum"))

        # Guardrail: target out of bounds
        with self.assertRaises(ValueError):
            self.controller.set_temperature(4.0, 1.0, 0)
        with self.assertRaises(ValueError):
            self.controller.set_temperature(400.0, 1.0, 0)

        # Guardrail: rate too high for low-temperature range
        fake_client.temperature_reading = (7.0, "Stable")
        with self.assertRaisesRegex(ValueError, "within the 5–9 K range must not exceed 1 K/min"):
            self.controller.set_temperature(7.0, 5.0, 0)

    def test_set_temperature_legacy_enums_and_missing_enums(self):
        """Verify fallback to legacy temp_approach_mode and missing enum error."""
        legacy_client = FakeMultiPyVuClient(
            temperature_reading=(100.0, "Stable"),
            field_reading=(0.0, "Holding"),
            modern_enums=False,
        )
        self.controller.client = legacy_client
        self.controller.set_temperature(150.0, 5.0, 0)
        self.assertEqual(legacy_client.set_temperature_calls[-1], (150.0, 5.0, "legacy_fast_settle"))

        # Missing enum
        broken_client = FakeMultiPyVuClient(temperature_reading=(100.0, "Stable"))
        broken_client.temperature = types.SimpleNamespace()
        self.controller.client = broken_client
        with self.assertRaisesRegex(RuntimeError, "lacks the mode enum fast_settle"):
            self.controller.set_temperature(150.0, 5.0, 0)

    def test_set_field_normal_and_guardrails(self):
        """Verify set_field parameter validation, enum resolution, and execution."""
        fake_client = FakeMultiPyVuClient(
            temperature_reading=(300.0, "Stable"),
            field_reading=(0.0, "Holding"),
            modern_enums=True,
        )
        self.controller.client = fake_client

        # Disconnected check
        unconnected_ctrl = PPMSMultiVuReadbackController(lambda _: None)
        with self.assertRaisesRegex(RuntimeError, "PPMS MultiVu is not connected"):
            unconnected_ctrl.set_field(1000.0, 50.0, 0, 0)

        # Valid linear (0) persistent (0)
        res = self.controller.set_field(1000.0, 50.0, 0, 0)
        self.assertEqual(fake_client.set_field_calls[-1], (1000.0, 50.0, "linear_enum", "persistent_enum"))
        self.assertEqual(res["field_oe"], 0.0)

        # Valid no_overshoot (1) driven (1)
        self.controller.set_field(2000.0, 60.0, 1, 1)
        self.assertEqual(fake_client.set_field_calls[-1], (2000.0, 60.0, "no_overshoot_enum", "driven_enum"))

        # Valid oscillate (2) driven (1)
        self.controller.set_field(3000.0, 70.0, 2, 1)
        self.assertEqual(fake_client.set_field_calls[-1], (3000.0, 70.0, "oscillate_enum", "driven_enum"))

        # Guardrail: field limit ±89900 Oe
        with self.assertRaises(ValueError):
            self.controller.set_field(90000.0, 50.0, 0, 0)

        # Guardrail: rate limit strictly below 150 Oe/s
        with self.assertRaises(ValueError):
            self.controller.set_field(1000.0, 150.0, 0, 0)

        # Invalid approach code
        with self.assertRaisesRegex(ValueError, "PPMS field approach/mode parameters are invalid"):
            self.controller.set_field(1000.0, 50.0, 99, 0)

        # Invalid mode code
        with self.assertRaisesRegex(ValueError, "PPMS field approach/mode parameters are invalid"):
            self.controller.set_field(1000.0, 50.0, 0, 99)

    def test_set_field_legacy_enums_and_missing_enums(self):
        """Verify set_field with legacy enum grouping and missing enum handling."""
        legacy_client = FakeMultiPyVuClient(
            temperature_reading=(300.0, "Stable"),
            field_reading=(0.0, "Holding"),
            modern_enums=False,
        )
        self.controller.client = legacy_client
        self.controller.set_field(500.0, 20.0, 0, 0)
        self.assertEqual(legacy_client.set_field_calls[-1], (500.0, 20.0, "legacy_linear", "legacy_persistent"))

        # Missing enum
        broken_client = FakeMultiPyVuClient(
            temperature_reading=(300.0, "Stable"),
            field_reading=(0.0, "Holding"),
        )
        broken_client.field = types.SimpleNamespace()
        self.controller.client = broken_client
        with self.assertRaisesRegex(RuntimeError, "lacks the mode enum linear"):
            self.controller.set_field(500.0, 20.0, 0, 0)


class TestMultiVuExceptionPropagationAndRobustness(unittest.TestCase):
    """Direct mocked MultiPyVu API tests covering exception propagation,

    connection failures, timeouts, malformed responses, cleanup, and uncertain outcomes.
    """

    def setUp(self):
        self.fake_client = FakeMultiPyVuClient()
        self.fake_client.open()
        self.logs: list[str] = []
        self.controller = PPMSMultiVuReadbackController(self.logs.append)
        self.controller.client = self.fake_client

    def test_connect_timeouts_and_network_failures_trigger_cleanup(self):
        """Verify client.open timeouts and network errors invoke close_client and propagate."""
        for error in (
            TimeoutError("Connection timed out"),
            socket.timeout("Socket timed out"),
            ConnectionRefusedError("Connection refused"),
            OSError("Network unreachable"),
        ):
            with self.subTest(error=type(error).__name__):
                client = FakeMultiPyVuClient()
                client.open = mock.Mock(side_effect=error)
                fake_module = types.SimpleNamespace(Client=mock.Mock(return_value=client))
                ctrl = PPMSMultiVuReadbackController(lambda _: None)

                with mock.patch("importlib.import_module", return_value=fake_module):
                    with self.assertRaises(type(error)):
                        ctrl.connect("192.168.137.5", 5000)

                self.assertTrue(client.closed_client)
                self.assertIsNone(ctrl.client)
                self.assertFalse(ctrl.connected)

    def test_read_environment_timeout_and_network_error_propagation(self):
        """Verify timeouts and socket errors during get_temperature/get_field propagate."""
        for error in (
            TimeoutError("Read timed out"),
            socket.timeout("Socket timed out"),
            ConnectionResetError("Connection reset by peer"),
            BrokenPipeError("Broken pipe"),
        ):
            with self.subTest(component="get_temperature", error=type(error).__name__):
                self.fake_client.get_temperature = mock.Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    self.controller.read_environment()

            with self.subTest(component="get_field", error=type(error).__name__):
                self.fake_client.get_temperature = mock.Mock(return_value=(300.0, "Stable"))
                self.fake_client.get_field = mock.Mock(side_effect=error)
                with self.assertRaises(type(error)):
                    self.controller.read_environment()

    def test_read_environment_malformed_non_numeric_responses(self):
        """Verify non-numeric string data from MultiPyVu raises ValueError."""
        self.fake_client.get_temperature = mock.Mock(return_value=("corrupted_reading", "Stable"))
        with self.assertRaises(ValueError):
            self.controller.read_environment()

        self.fake_client.get_temperature = mock.Mock(return_value=(300.0, "Stable"))
        self.fake_client.get_field = mock.Mock(return_value=("invalid_field", "Holding"))
        with self.assertRaises(ValueError):
            self.controller.read_environment()

    def test_set_temperature_timeout_and_exception_propagation(self):
        """Verify timeouts or network failures during set_temperature propagate without retry."""
        # 1. Timeout during pre-command readback (get_temperature)
        self.fake_client.get_temperature = mock.Mock(side_effect=TimeoutError("Pre-check timed out"))
        with self.assertRaises(TimeoutError):
            self.controller.set_temperature(100.0, 5.0, 0)
        self.assertEqual(len(self.fake_client.set_temperature_calls), 0)

        # 2. Timeout during actual set_temperature call
        self.fake_client.get_temperature = mock.Mock(return_value=(300.0, "Stable"))
        self.fake_client.set_temperature = mock.Mock(side_effect=socket.timeout("Command timed out"))
        with self.assertRaises(socket.timeout):
            self.controller.set_temperature(100.0, 5.0, 0)
        self.fake_client.set_temperature.assert_called_once()

    def test_set_field_timeout_uncertain_outcome_and_no_resend(self):
        """Verify command timeout leaves outcome uncertain, never retries, and keeps lock intact.

        When set_field fails with a timeout or network exception, the command was already
        issued once to the instrument SDK. The controller must not attempt to re-send the
        field target (which could disrupt a running ramp), must release its lock, and allow
        subsequent readback or disconnect without deadlock.
        """
        self.fake_client.set_field = mock.Mock(side_effect=TimeoutError("Set field timed out"))

        with self.assertRaises(TimeoutError):
            self.controller.set_field(5000.0, 50.0, 0, 1)

        # Assert invoked exactly once (no retry/resend)
        self.fake_client.set_field.assert_called_once()

        # Controller lock must be released so subsequent read_environment succeeds
        self.fake_client.get_temperature = mock.Mock(return_value=(300.0, "Stable"))
        self.fake_client.get_field = mock.Mock(return_value=(2500.0, "Chasing"))
        reading = self.controller.read_environment()
        self.assertEqual(reading["field_oe"], 2500.0)
        self.assertEqual(reading["field_status"], "Chasing")

        # Disconnect succeeds cleanly
        self.controller.disconnect()
        self.assertFalse(self.controller.connected)


if __name__ == "__main__":
    unittest.main()
