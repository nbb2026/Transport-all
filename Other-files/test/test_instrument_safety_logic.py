"""Offline regression tests for instrument safety logic (no hardware needed)."""

import math
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path

import numpy as np


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import transport.fmr.app as app


class FakeVariable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeProgressbar:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class FakeSharedVisaInstrument:
    def __init__(self, identity):
        self.identity = identity
        self.closed = False
        self.commands = []
        self.timeout = None
        self.write_termination = "PYVISA_DEFAULT_WRITE"
        self.read_termination = "PYVISA_DEFAULT_READ"
        self.send_end = False
        self.query_delay = 0.0

    def _require_open(self):
        if self.closed:
            raise RuntimeError("VI_ERROR_INV_OBJECT")

    def query(self, command):
        self._require_open()
        if command == "*IDN?":
            return self.identity
        return "0"

    def write(self, command):
        self._require_open()
        self.commands.append(command)

    def close(self):
        self.closed = True


class FakeSharedVisaManager:
    def __init__(self, identities):
        self.identities = dict(identities)
        self._session = 1
        self.resources = []
        self.close_calls = 0
        self.list_resources_calls = 0

    @property
    def session(self):
        if self._session is None:
            raise RuntimeError("invalid ResourceManager session")
        return self._session

    def open_resource(self, resource):
        self.session
        instrument = FakeSharedVisaInstrument(self.identities[resource])
        self.resources.append(instrument)
        return instrument

    def list_resources(self):
        self.session
        self.list_resources_calls += 1
        return tuple(self.identities)

    def close(self):
        self.close_calls += 1
        for instrument in self.resources:
            instrument.close()
        self._session = None


class FakePyVisaModule:
    def __init__(self, manager):
        self.manager = manager

    def ResourceManager(self):
        return self.manager


class Fake2410:
    # :SOUR:VOLT:PROT levels from the 2400-series manual: a value between two
    # levels selects the lower one, and above the highest it means none.
    OVP_LEVELS = (20.0, 40.0, 100.0, 200.0, 300.0, 400.0, 500.0)
    OVP_NONE = 1100.0
    IDENTITY = "KEITHLEY INSTRUMENTS INC.,MODEL 2410,1234567,C34"

    def __init__(self):
        self.commands = []
        self.voltage = 0.0
        self.voltage_range = 20.0
        self.ovp = 200.0
        self.output = 0
        self.errors = []

    def _ovp_level(self, value):
        value = abs(value)
        if value > self.OVP_LEVELS[-1]:
            return self.OVP_NONE
        return max([level for level in self.OVP_LEVELS if level <= value] or [self.OVP_LEVELS[0]])

    def write(self, command):
        self.commands.append(command)
        upper = command.upper()
        if upper.startswith(":SOUR:VOLT:RANG "):
            self.voltage_range = float(command.rsplit(" ", 1)[1])
        elif upper.startswith(":SOUR:VOLT:PROT "):
            self.ovp = self._ovp_level(float(command.rsplit(" ", 1)[1]))
        elif upper.startswith(":SOUR:VOLT "):
            self.voltage = float(command.rsplit(" ", 1)[1])
        elif upper == ":OUTP ON":
            self.output = 1
        elif upper == ":OUTP OFF":
            self.output = 0
        elif upper == "*RST":
            # As the instrument: output off, source at 0, OVP none.
            self.output, self.voltage, self.ovp = 0, 0.0, self.OVP_NONE

    def query(self, command):
        upper = command.upper()
        if upper == "SYST:ERR?":
            if self.errors:
                return self.errors.pop(0)
            return '0,"No error"'
        if upper == ":SOUR:VOLT:RANG?":
            return str(self.voltage_range)
        if upper == ":SOUR:VOLT:PROT?":
            return str(self.ovp)
        if upper == ":SOUR:VOLT?":
            return str(self.voltage)
        if upper == ":OUTP?":
            return str(self.output)
        if upper == "*IDN?":
            return self.IDENTITY
        raise AssertionError(f"unexpected query: {command}")

    def close(self):
        pass


class Fake2400(Fake2410):
    """A 2400: its highest source range is 200 V, so the 2410's 1000 V range
    is refused with a SCPI error, as the instrument does.  It has no 200 V
    OVP level: asked for 200 V it selects none, read back as 210 V."""

    OVP_LEVELS = (20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 160.0)
    OVP_NONE = 210.0
    IDENTITY = "KEITHLEY INSTRUMENTS INC.,MODEL 2400,4105497,C30   Mar 17 2006 09:29:29/A02  /K/J"

    def write(self, command):
        upper = command.upper()
        if upper.startswith(":SOUR:VOLT:RANG ") and float(command.rsplit(" ", 1)[1]) > 210.0:
            self.commands.append(command)
            self.errors.append('-222,"Parameter data out of range"')
            return
        super().write(command)



class Fake6221:
    def __init__(self):
        self.commands = []
        self.current = 0.0
        self.compliance = 10.0
        self.auto_range = 0
        self.output = 0
        self.wave_frequency = 13.7
        self.wave_amplitude = 0.0
        self.wave_offset = 0.0
        self.wave_cycles = 1
        self.marker_enabled = 0
        self.marker_line = 4
        self.marker_phase = 0.0
        self.measurement_condition = 0
        self.auto_complete_waveform = False
        self.reported_wave_cycles = None

    def write(self, command):
        self.commands.append(command)
        upper = command.upper()
        if upper.startswith("CURR:COMP "):
            self.compliance = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:CURR:RANG:AUTO "):
            self.auto_range = int(upper.endswith("ON"))
        elif upper.startswith("SOUR:CURR:RANG "):
            self.current_range = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:CURR "):
            self.current = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:WAVE:FREQ "):
            self.wave_frequency = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:WAVE:AMPL "):
            self.wave_amplitude = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:WAVE:OFFS "):
            self.wave_offset = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:WAVE:DUR:CYCL "):
            value = command.rsplit(" ", 1)[1]
            self.wave_cycles = value if value.upper() == "INF" else int(value)
        elif upper.startswith("SOUR:WAVE:PMAR:OLIN "):
            self.marker_line = int(command.rsplit(" ", 1)[1])
        elif upper.startswith("SOUR:WAVE:PMAR:STAT "):
            self.marker_enabled = int(upper.endswith("ON"))
        elif upper.startswith("SOUR:WAVE:PMAR "):
            self.marker_phase = float(command.rsplit(" ", 1)[1])
        elif upper == "SOUR:WAVE:INIT":
            self.output = 0 if self.auto_complete_waveform else 1
        elif upper == "SOUR:WAVE:ABOR":
            self.output = 0
        elif upper == "OUTP ON":
            self.output = 1
        elif upper == "OUTP OFF":
            self.output = 0

    def query(self, command):
        upper = command.upper()
        if upper == "SYST:ERR?":
            return '0,"No error"'
        if upper == "CURR:COMP?":
            return str(self.compliance)
        if upper == "SOUR:CURR:RANG:AUTO?":
            return str(self.auto_range)
        if upper == "SOUR:CURR:RANG?":
            return str(getattr(self, "current_range", 0.1))
        if upper == "SOUR:CURR?":
            return str(self.current)
        if upper == "SOUR:WAVE:FREQ?":
            return str(self.wave_frequency)
        if upper == "SOUR:WAVE:AMPL?":
            return str(self.wave_amplitude)
        if upper == "SOUR:WAVE:OFFS?":
            return str(self.wave_offset)
        if upper == "SOUR:WAVE:DUR:CYCL?":
            if self.reported_wave_cycles is not None:
                return str(self.reported_wave_cycles)
            return str(self.wave_cycles)
        if upper == "SOUR:WAVE:PMAR:STAT?":
            return str(self.marker_enabled)
        if upper == "SOUR:WAVE:PMAR:OLIN?":
            return str(self.marker_line)
        if upper == "SOUR:WAVE:PMAR?":
            return str(self.marker_phase)
        if upper == "OUTP?":
            return str(self.output)
        if upper == "STAT:MEAS:COND?":
            return str(self.measurement_condition)
        if upper == "OUTP:LTE?":
            # Output low floating (the rack's state; checked after each *RST).
            return "0"
        raise AssertionError(f"unexpected query: {command}")


class FakeSR830:
    def __init__(self, r_value):
        self.commands = []
        self.harmonic = 1
        self.reference_mode = 0
        self.reference_slope = 1  # PPMS default: TTL rising edge
        self.frequency = 13.7
        self.r_value = float(r_value)
        self.status = 0

    def write(self, command):
        self.commands.append(command)
        upper = command.upper()
        if upper.startswith("HARM "):
            self.harmonic = int(command.rsplit(" ", 1)[1])
        elif upper.startswith("FMOD "):
            self.reference_mode = int(command.rsplit(" ", 1)[1])
        elif upper.startswith("RSLP "):
            self.reference_slope = int(command.rsplit(" ", 1)[1])
        elif upper.startswith("SENS "):
            self.sensitivity = int(command.rsplit(" ", 1)[1])

    def query(self, command):
        upper = command.upper()
        if upper == "*ESR?":
            return "0"
        if upper == "HARM?":
            return str(self.harmonic)
        if upper == "FMOD?":
            return str(self.reference_mode)
        if upper == "RSLP?":
            return str(self.reference_slope)
        if upper == "FREQ?":
            return str(self.frequency)
        if upper == "LIAS?":
            return str(self.status)
        if upper == "SNAP? 1,2,3,4,9":
            return f"1e-6,2e-6,{self.r_value},3.5,{self.frequency}"
        if upper == "SENS?":
            # Sensitivity code queried by the PPMS SR830 autorange step.
            return str(getattr(self, "sensitivity", 24))
        if upper == "OFLT?":
            # Time-constant code (9 = 100 ms) used to size the settle wait.
            return str(getattr(self, "time_constant_code", 9))
        raise AssertionError(f"unexpected query: {command}")

    def clear(self):
        pass


class Fake2182:
    def write(self, _command):
        pass

    def query(self, command):
        if command.upper() == "SYST:ERR?":
            return '0,"No error"'
        raise AssertionError(f"unexpected query: {command}")


class FakeKepco4886:
    def __init__(self):
        self.commands = []
        self.mode = "CURR"
        self.current = 0.0
        self.voltage = 0.0
        self.output = 0

    def write(self, command):
        self.commands.append(command)
        upper = command.upper()
        if upper.startswith("FUNC:MODE "):
            self.mode = upper.rsplit(" ", 1)[1]
        elif upper.startswith("CURR "):
            self.current = float(command.rsplit(" ", 1)[1])
        elif upper.startswith("VOLT "):
            self.voltage = float(command.rsplit(" ", 1)[1])
        elif upper == "OUTP ON":
            self.output = 1
        elif upper == "OUTP OFF":
            self.output = 0

    def query(self, command):
        upper = command.upper()
        if upper == "FUNC:MODE?":
            return self.mode
        if upper == "MEAS:CURR?" or upper == "CURR?":
            return str(self.current)
        if upper == "MEAS:VOLT?" or upper == "VOLT?":
            return str(self.voltage)
        if upper == "OUTP?":
            return str(self.output)
        if upper == "SYST:ERR?":
            return '0,"No error"'
        raise AssertionError(f"unexpected query: {command}")


class FakeLakeShore475:
    def __init__(self, field=123.45, unit=1):
        self.field = field
        self.unit = unit

    def query(self, command):
        if command.upper() == "RDGFIELD?":
            return str(self.field)
        if command.upper() == "UNIT?":
            return str(self.unit)
        raise AssertionError(f"unexpected query: {command}")


class FakeMultiPyVuClient:
    def get_temperature(self):
        return 7.25, "Stable"

    def get_field(self):
        return -1234.5, "Holding"


class InstrumentSafetyTests(unittest.TestCase):
    def setUp(self):
        app._INSTRUMENT_LEASES.clear()
        app._SHARED_VISA_MANAGER = None
        app._SHARED_VISA_MANAGER_USERS = 0

    def tearDown(self):
        app._INSTRUMENT_LEASES.clear()
        app._SHARED_VISA_MANAGER = None
        app._SHARED_VISA_MANAGER_USERS = 0

    def test_shared_visa_manager_survives_one_controller_disconnect(self):
        original_pyvisa = app.pyvisa
        manager = FakeSharedVisaManager({
            "GPIB0::6::INSTR": "KEPCO,4886,TEST,1",
            "GPIB0::12::INSTR": "LSCI,MODEL475,TEST,1",
        })
        app.pyvisa = FakePyVisaModule(manager)
        kepco = app.SafeVisaIdentityController(
            lambda _message: None, "KEPCO", "4886", owner_scope="STFMR"
        )
        gauss = app.SafeVisaIdentityController(
            lambda _message: None, "Gauss", "MODEL475", owner_scope="STFMR"
        )
        try:
            kepco.connect("GPIB0::6::INSTR")
            gauss.connect("GPIB0::12::INSTR")
            self.assertIs(kepco.resource_manager, gauss.resource_manager)
            self.assertEqual(app._SHARED_VISA_MANAGER_USERS, 2)

            kepco.disconnect()
            self.assertEqual(manager.close_calls, 0)
            self.assertEqual(app._SHARED_VISA_MANAGER_USERS, 1)
            self.assertIn("MODEL475", gauss.instrument.query("*IDN?"))

            gauss.disconnect()
            self.assertEqual(manager.close_calls, 1)
            self.assertEqual(app._SHARED_VISA_MANAGER_USERS, 0)
            self.assertIsNone(app._SHARED_VISA_MANAGER)
        finally:
            try:
                kepco.disconnect()
            except BaseException:
                pass
            try:
                gauss.disconnect()
            except BaseException:
                pass
            app.pyvisa = original_pyvisa

    def test_failed_visa_identity_check_does_not_close_other_session(self):
        original_pyvisa = app.pyvisa
        manager = FakeSharedVisaManager({
            "GPIB0::6::INSTR": "KEPCO,4886,TEST,1",
            "GPIB0::16::INSTR": "UNEXPECTED,DEVICE,TEST,1",
        })
        app.pyvisa = FakePyVisaModule(manager)
        kepco = app.SafeVisaIdentityController(
            lambda _message: None, "KEPCO", "4886", owner_scope="STFMR"
        )
        vna = app.SafeVisaIdentityController(
            lambda _message: None, "N5227A", "N5227A", owner_scope="STFMR"
        )
        try:
            kepco.connect("GPIB0::6::INSTR")
            with self.assertRaises(RuntimeError):
                vna.connect("GPIB0::16::INSTR")
            self.assertEqual(manager.close_calls, 0)
            self.assertEqual(app._SHARED_VISA_MANAGER_USERS, 1)
            self.assertIn("4886", kepco.instrument.query("*IDN?"))
            kepco.disconnect()
            self.assertEqual(manager.close_calls, 1)
        finally:
            try:
                kepco.disconnect()
            except BaseException:
                pass
            try:
                vna.disconnect()
            except BaseException:
                pass
            app.pyvisa = original_pyvisa

    def test_stfmr_kepco_current_mode_matches_labview_trace(self):
        controller = app.STFMRKepco4886Controller(lambda _message: None)
        fake = FakeKepco4886()
        controller.instrument = fake
        result = controller.set_output("CURR", -2.5, 8.0)
        self.assertEqual(fake.commands, [
            "FUNC:MODE CURR",
            "CURR 0;VOLT 8",
            "VOLT:RANG:AUTO 1;CURR:RANG:AUTO 1",
            "OUTP ON",
            "CURR -2.500000",
        ])
        self.assertEqual(result["mode"], "CURR")
        self.assertTrue(result["output"])
        self.assertEqual(result["current_a"], -2.5)
        self.assertEqual(result["voltage_v"], 8.0)
        fake.commands.clear()
        scan_result = controller.set_scan_current(1.25)
        self.assertEqual(fake.commands, ["CURR 1.250000"])
        self.assertEqual(scan_result["current_a"], 1.25)
        with self.assertRaises(ValueError):
            controller.set_output("CURR", 10.0001, 8.0)

    def test_stfmr_kepco_voltage_mode_and_zero(self):
        controller = app.STFMRKepco4886Controller(lambda _message: None)
        fake = FakeKepco4886()
        controller.instrument = fake
        result = controller.set_output("VOLT", 12.0, 3.0)
        self.assertEqual(fake.commands, [
            "FUNC:MODE VOLT",
            "VOLT 0;CURR 3",
            "VOLT:RANG:AUTO 1;CURR:RANG:AUTO 1",
            "OUTP ON",
            "VOLT 12.000000",
        ])
        self.assertEqual(result["mode"], "VOLT")
        zeroed = controller.zero_output()
        self.assertFalse(zeroed["output"])
        self.assertEqual(zeroed["current_a"], 0.0)
        self.assertEqual(zeroed["voltage_v"], 0.0)
        self.assertEqual(fake.commands[-2:], ["VOLT 0.000000", "OUTP OFF"])

    def test_stfmr_kepco_connect_preserves_native_gpib_eoi_profile(self):
        original_pyvisa = app.pyvisa
        manager = FakeSharedVisaManager({
            "GPIB0::6::INSTR": "KEPCO,BIT 4886 20-10,TEST,1.0",
        })
        app.pyvisa = FakePyVisaModule(manager)
        controller = app.STFMRKepco4886Controller(lambda _message: None)
        controller.connect_settle_seconds = 0.0
        try:
            identity = controller.connect("GPIB0::6::INSTR")
            self.assertIn("4886 20-10", identity)
            instrument = manager.resources[-1]
            self.assertIsNone(instrument.write_termination)
            self.assertIsNone(instrument.read_termination)
            self.assertTrue(instrument.send_end)
            self.assertEqual(instrument.query_delay, 0.0)
            self.assertEqual(instrument.commands, [])
            self.assertEqual(manager.list_resources_calls, 0)
        finally:
            try:
                controller.disconnect()
            except BaseException:
                pass
            app.pyvisa = original_pyvisa

    def test_stfmr_kepco_connect_never_queries_or_writes(self):
        class TimeoutInstrument(FakeSharedVisaInstrument):
            def query(self, command):
                self._require_open()
                raise RuntimeError("VI_ERROR_TMO")

        class TimeoutManager(FakeSharedVisaManager):
            def open_resource(self, resource):
                self.session
                instrument = TimeoutInstrument(self.identities[resource])
                self.resources.append(instrument)
                return instrument

        original_pyvisa = app.pyvisa
        manager = TimeoutManager({
            "GPIB0::6::INSTR": "KEPCO,BIT 4886 20-10,TEST,1.0",
        })
        app.pyvisa = FakePyVisaModule(manager)
        controller = app.STFMRKepco4886Controller(lambda _message: None)
        controller.connect_settle_seconds = 0.0
        try:
            identity = controller.connect("GPIB0::6::INSTR")
            instrument = manager.resources[-1]
            self.assertIn("not queried", identity)
            self.assertEqual(instrument.commands, [])
            self.assertFalse(instrument.closed)
            controller.disconnect()
            self.assertTrue(instrument.closed)
        finally:
            try:
                controller.disconnect()
            except BaseException:
                pass
            app.pyvisa = original_pyvisa

    def test_stfmr_gaussmeter_preserves_units(self):
        controller = app.STFMRGauss475Controller(lambda _message: None)
        controller.instrument = FakeLakeShore475(field=-456.75, unit=3)
        result = controller.read_field()
        self.assertEqual(result["field"], -456.75)
        self.assertEqual(result["unit"], "Oe")

    def test_stfmr_lockin_defaults_match_supplied_labview_setup(self):
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_RESOURCES, {
            "kepco": "GPIB0::6::INSTR",
            "gauss": "GPIB0::15::INSTR",
            "smb": "GPIB0::28::INSTR",
            "830": "GPIB0::9::INSTR",
            "mfli": "dev4435",
        })
        # The user's screenshot (2026-10-17): f 3 to 9 GHz, 12 dBm alone
        # (P step 3 dB), Mod. 317.3 Hz.
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_FREQUENCY_GHZ, 3.0)
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_FREQUENCY_STOP_GHZ, 9.0)
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_POWER_DBM, 12.0)
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_POWER_STOP_DBM, 12.0)
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_POWER_STEP_DB, 3.0)
        self.assertEqual(app.STFMR_LOCKIN_DEFAULT_LFO_HZ, 317.3)
        # Every lock-in time constant starts at 1 s (user, 2026-10-14; was 0.1 s).
        self.assertEqual(app.STFMR_LOCKIN_MFLI_TIME_CONSTANT_S, 1.0)
        self.assertEqual(
            app.STFMR_LOCKIN_SR830_DEFAULT_REFERENCE_INPUT, "Sine"
        )
        self.assertEqual(app.STFMR_LOCKIN_SR830_REFERENCE_INPUTS, {
            "Sine": 0,
            "TTL Rising": 1,
            "TTL Falling": 2,
        })

    def test_stfmr_lockin_xy_component_normalizes_sr830_and_mfli_samples(self):
        helper = app.CombinedControlApp._stfmr_lockin_sample_component
        self.assertAlmostEqual(helper({"x_v": 1.25e-6}, "X"), 1.25e-6)
        self.assertAlmostEqual(helper({"y_v": -2.5e-6}, "Y"), -2.5e-6)
        self.assertAlmostEqual(helper({"X": 3.0e-3}, "X"), 3.0e-3)
        self.assertAlmostEqual(helper({"Y": -4.0e-3}, "Y"), -4.0e-3)
        with self.assertRaisesRegex(RuntimeError, "valid X"):
            helper({"X": float("nan")}, "X")

    def test_stfmr_sweep_refuses_to_start_without_the_safety_tick(self):
        """The page's one confirmation, in the 4886 output panel, gates the sweep."""
        harness = object.__new__(app.CombinedControlApp)
        harness._stfmr_lockin_connected = lambda _key: True
        harness.stfmr_lockin_meter_var = FakeVariable("MFLI")
        harness.stfmr_lockin_manual_safety_var = FakeVariable(False)
        with self.assertRaisesRegex(RuntimeError, "safety confirmation"):
            harness._stfmr_lockin_inputs()

    def test_stfmr_lockin_scan_is_one_way_per_loop(self):
        harness = object.__new__(app.CombinedControlApp)
        harness._stfmr_lockin_connected = lambda _key: True
        harness.stfmr_lockin_manual_safety_var = FakeVariable(True)
        harness.stfmr_lockin_meter_var = FakeVariable("MFLI")
        harness.stfmr_lockin_frequency_start_var = FakeVariable("5")
        harness.stfmr_lockin_frequency_stop_var = FakeVariable("7")
        harness.stfmr_lockin_frequency_step_var = FakeVariable("1")
        # P start / P stop / P step replace Power dBm (user, 2026-10-14).
        harness.stfmr_lockin_power_start_var = FakeVariable("10")
        harness.stfmr_lockin_power_stop_var = FakeVariable("10")
        harness.stfmr_lockin_power_step_var = FakeVariable("1")
        harness.stfmr_lockin_mod_start_var = FakeVariable("317.3")
        harness.stfmr_lockin_mod_end_var = FakeVariable("317.3")
        # Settle s and Acquire s replace Wait/pt (user, 2026-10-14).
        harness.stfmr_lockin_settle_var = FakeVariable("1")
        harness.stfmr_lockin_acquire_var = FakeVariable("2")
        harness.stfmr_lockin_limit_var = FakeVariable("10")
        harness.stfmr_lockin_loop_var = FakeVariable(2)
        harness.stfmr_lockin_start_var = FakeVariable("-1")
        harness.stfmr_lockin_stop_var = FakeVariable("1")
        harness.stfmr_lockin_step_var = FakeVariable("1")
        points, frequencies, powers, *_rest = harness._stfmr_lockin_inputs()
        self.assertEqual(points, [-1.0, 0.0, 1.0, -1.0, 0.0, 1.0])
        self.assertEqual(frequencies, [5.0, 6.0, 7.0])
        self.assertEqual(powers, [10.0], "P start = P stop: one power")
        self.assertEqual(harness.stfmr_lockin_points_per_loop, 3)

    def test_stfmr_lockin_field_plot_does_not_join_loops(self):
        rows = [
            {"meter": "MFLI", "loop": 1, "field_g": -10, "voltage_v": 1e-3},
            {"meter": "MFLI", "loop": 1, "field_g": 10, "voltage_v": 2e-3},
            {"meter": "MFLI", "loop": 2, "field_g": -10, "voltage_v": 3e-3},
            {"meter": "MFLI", "loop": 2, "field_g": 10, "voltage_v": 4e-3},
        ]
        series = app.CombinedControlApp._stfmr_lockin_field_component_series(
            rows, "MFLI", "mfli", "voltage_v"
        )
        self.assertEqual(
            series,
            {
                "mfli_loop_1": [(-10.0, 1e-3), (10.0, 2e-3)],
                "mfli_loop_2": [(-10.0, 3e-3), (10.0, 4e-3)],
            },
        )

    def test_stfmr_lockin_field_plot_groups_frequency_and_loop(self):
        rows = [
            {
                "meter": "MFLI", "loop": 1,
                "microwave_frequency_ghz": 5.0,
                "field_g": -10, "voltage_v": 1e-3,
            },
            {
                "meter": "MFLI", "loop": 1,
                "microwave_frequency_ghz": 6.0,
                "field_g": -9, "voltage_v": 2e-3,
            },
            {
                "meter": "MFLI", "loop": 2,
                "microwave_frequency_ghz": 5.0,
                "field_g": 10, "voltage_v": 3e-3,
            },
        ]
        series = app.CombinedControlApp._stfmr_lockin_field_component_series(
            rows,
            "MFLI",
            "mfli",
            "voltage_v",
            group_frequency=True,
        )
        self.assertEqual(
            series,
            {
                "mfli_freq_5_loop_1": [(-10.0, 1e-3)],
                "mfli_freq_6_loop_1": [(-9.0, 2e-3)],
                "mfli_freq_5_loop_2": [(10.0, 3e-3)],
            },
        )
        labels, colors = (
            app.CombinedControlApp._stfmr_lockin_frequency_series_styles(
                series, "voltage_v"
            )
        )
        self.assertEqual(labels["mfli_freq_5_loop_1"], "5 GHz")
        self.assertEqual(labels["mfli_freq_5_loop_2"], "")
        self.assertEqual(labels["mfli_freq_6_loop_1"], "6 GHz")
        self.assertEqual(
            colors["mfli_freq_5_loop_1"], colors["mfli_freq_5_loop_2"]
        )
        self.assertNotEqual(
            colors["mfli_freq_5_loop_1"], colors["mfli_freq_6_loop_1"]
        )

    def test_stfmr_lockin_frequency_colors_darkens_with_frequency(self):
        series = {
            f"mfli_freq_{frequency}_loop_1": [(0.0, 0.0)]
            for frequency in (3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
        }

        def brightness(color):
            red, green, blue = (
                int(color[index:index + 2], 16) for index in (1, 3, 5)
            )
            return 0.2126 * red + 0.7152 * green + 0.0722 * blue

        for component in ("x_v", "y_v", "phase_deg", "voltage_v"):
            _labels, colors = (
                app.CombinedControlApp._stfmr_lockin_frequency_series_styles(
                    series, component
                )
            )
            ordered_brightness = [
                brightness(colors[f"mfli_freq_{frequency}_loop_1"])
                for frequency in (3.0, 4.0, 5.0, 6.0, 7.0, 8.0)
            ]
            self.assertTrue(all(
                earlier > later
                for earlier, later in zip(
                    ordered_brightness, ordered_brightness[1:]
                )
            ))

    def test_stfmr_lockin_plots_use_compact_markers(self):
        harness = object.__new__(app.CombinedControlApp)
        captured = {}
        harness._draw_nonlocal_series = (
            lambda *_args, **kwargs: captured.update(kwargs)
        )

        harness._draw_stfmr_lockin_frequency_component(
            object(), [], "MFLI", "mfli", "x_v", "MFLI X", "等待数据"
        )

        self.assertTrue(captured["markers"])
        self.assertEqual(captured["marker_radius"], 1.5)

    def test_stfmr_lower_right_plot_is_4886_current_vs_measured_field(self):
        harness = object.__new__(app.CombinedControlApp)
        harness.stfmr_lockin_canvas = object()
        harness.stfmr_lockin_rows = [{
            "meter": "MFLI", "microwave_frequency_ghz": 3.0,
            "loop": 1, "field_g": 125.0, "current_a": 0.5,
        }]
        harness.stfmr_lockin_selected_meter = "MFLI"
        captured = {}
        harness._draw_nonlocal_series = (
            lambda *args, **kwargs: captured.update(args=args, kwargs=kwargs)
        )

        harness._redraw_stfmr_lockin_plot()

        self.assertEqual(
            captured["args"][1],
            {"mfli_freq_3_loop_1": [(0.5, 125.0)]},
        )
        self.assertEqual(captured["args"][2], "4886 set current (A)")
        self.assertEqual(captured["args"][3], "LS475 measured field (G)")
        self.assertNotIn("auto_voltage_unit", captured["kwargs"])

    def test_mfli_accepts_discrete_timeconstant_readback_near_request(self):
        class FakeBridge:
            def request(self, command, **kwargs):
                self.command = command
                self.kwargs = kwargs
                return {
                    "actual_ac": 1,
                    "actual_imp50": 0,
                    "actual_scaling": 1.0,
                    "actual_harmonic": 1,
                    "actual_extref_harmonic": 1,
                    "extref_enabled": 1,
                    "extref_adcselect": kwargs["reference_adcselect"],
                    "timeconstant_s": 0.100016,
                    "filter_order": app.NONLOCAL_LOCKIN_FILTER_ORDER,
                    "sample_rate_hz": kwargs["sample_rate_hz"],
                    "input_range_v": 0.03,
                }

        controller = app.NonLocalACController(lambda _message: None)
        bridge = FakeBridge()
        controller.mfli_bridge = bridge
        controller.mfli_device = "dev4435"
        controller.mfli_props = {"options": "MD", "has_demod_2": True}
        result = controller.configure_mfli(
            "AC",
            1,
            "R",
            reference_source="Aux Input 1",
            sample_rate_hz=1.0,
            input_impedance="10 MΩ",
            input_scaling=1.0,
            timeconstant_s=0.1,
        )
        self.assertEqual(bridge.command, "configure")
        self.assertAlmostEqual(bridge.kwargs["timeconstant_s"], 0.1)
        self.assertAlmostEqual(result["timeconstant_s"], 0.100016)

    def test_mfli_readback_uses_independent_xy_for_phase_and_lock_state(self):
        class FakeBridge:
            def request(self, command, **_kwargs):
                self.command = command
                return {
                    "sample": {
                        "x": -650.0e-6,
                        "y": -750.0e-6,
                        "frequency": 244.78,
                        "extref_locked": 0,
                        "input_range_v": 0.03,
                        "input_max_normalized": 0.1,
                        "input_min_normalized": -0.1,
                    }
                }

        controller = app.NonLocalACController(lambda _message: None)
        bridge = FakeBridge()
        controller.mfli_bridge = bridge
        controller.mfli_device = "dev4435"
        controller.mfli_config = {"harmonic": 1}
        sample = controller.read_mfli(317.3)

        self.assertEqual(bridge.command, "read")
        self.assertAlmostEqual(sample["X"], -650.0e-6)
        self.assertAlmostEqual(sample["Y"], -750.0e-6)
        self.assertAlmostEqual(sample["phase_deg"], -130.91438322002512)
        self.assertFalse(sample["reference_valid"])

    def test_stfmr_reference_indicator_uses_green_red_and_neutral_states(self):
        class FakeCanvas:
            def itemconfigure(self, item, **kwargs):
                self.item = item
                self.options = kwargs

        harness = object.__new__(app.CombinedControlApp)
        canvas = FakeCanvas()
        harness.stfmr_lockin_reference_indicator = (canvas, 7)

        harness._set_stfmr_lockin_reference_state(True)
        self.assertEqual(canvas.item, 7)
        self.assertEqual(canvas.options["fill"], "#20b15a")
        harness._set_stfmr_lockin_reference_state(False)
        self.assertEqual(canvas.options["fill"], "#e53935")
        harness._set_stfmr_lockin_reference_state(None)
        self.assertEqual(canvas.options["fill"], "#9aa0a6")

    def test_stfmr_smb100a_setup_matches_supplied_trace(self):
        class FakeSMB100A(FakeSharedVisaInstrument):
            """Answers :POW? with the level last sent, and keeps every
            write and query in order."""

            def __init__(self, identity):
                super().__init__(identity)
                self.level, self.sequence = "6", []

            def write(self, command):
                super().write(command)
                self.sequence.append(command)
                if command.startswith(":POW "):
                    self.level = command.split()[1]
                elif command.startswith("LFO:FREQ "):
                    self.lfo = command.split()[1]
                elif command.startswith("FREQ "):
                    self.carrier = f"{float(command[5:-3]) * 1e9:.12g}"

            def query(self, command):
                # The level, and since 2026-10-18 the LFO and the carrier.
                answers = {":POW?": "level", "LFO:FREQ?": "lfo", "FREQ?": "carrier"}
                if command in answers:
                    self.sequence.append(command)
                    return getattr(self, answers[command])
                return super().query(command)

        controller = app.STFMRSMB100AController(lambda _message: None)
        fake = FakeSMB100A("Rohde&Schwarz,SMB100A,TEST,1.0")
        controller.instrument = fake
        self.assertEqual(controller.configure(5.0, 10.0, 317.3), 10.0)
        # The first power is read back right after it is sent, before the
        # carrier and the RF are switched on (review, 2026-10-14); the
        # writes are the trace's, in its order.
        self.assertEqual(fake.sequence[2:8], ["LFO:FREQ 317.3 Hz", "LFO:FREQ?", ":POW 10", ":POW?",
                                              "FREQ 5GHz", "FREQ?"])
        self.assertEqual(fake.commands, [
            ":AM:DEPT:LIN 1.0E+2",
            "LFO:VOLT 0.50 V",
            "LFO:FREQ 317.3 Hz",
            ":POW 10",
            "FREQ 5GHz",
            "LFO ON",
            "OUTPUT ON",
            "AM:STAT ON",
        ])
        self.assertEqual(controller.set_frequency(6.0), 6e9)
        self.assertEqual(fake.commands[-1], "FREQ 6GHz")
        self.assertEqual(fake.sequence[-1], "FREQ?", "read back (review, 2026-10-18)")
        controller.rf_off()
        self.assertEqual(
            fake.commands[-3:], ["AM:STAT OFF", "LFO OFF", "OUTPUT OFF"]
        )

    def test_stfmr_sr830_setup_and_sample_readback(self):
        class FakeSR830(FakeSharedVisaInstrument):
            def __init__(self, identity):
                super().__init__(identity)
                self.sensitivity = app.STFMR_LOCKIN_SR830_SENSITIVITY_CODE

            def write(self, command):
                super().write(command)
                if command.startswith("SENS "):
                    self.sensitivity = int(command.split()[1])
                if command.startswith("OFLT "):
                    # configure() reads the time constant back (2026-10-13).
                    self.time_constant = int(command.split()[1])

            def query(self, command):
                if command == "OFLT?":
                    return str(self.time_constant)
                if command == "SNAP? 1,2,3,4,9":
                    return "1e-6,-2e-6,2.2360679e-6,-63.4349,317.3"
                if command == "LIAS?":
                    return "0"
                if command == "FMOD?":
                    return "0"
                if command == "RSLP?":
                    return "0"
                if command == "HARM?":
                    return "1"
                if command == "SENS?":
                    return str(self.sensitivity)
                if command == "FREQ?":
                    return "317.3"
                return super().query(command)

        controller = app.STFMRSR830Controller(lambda _message: None)
        fake = FakeSR830("Stanford_Research_Systems,SR830,TEST,1.0")
        controller.instrument = fake
        controller.configure()
        lock = controller.wait_for_reference(317.3)
        sample = controller.read_sample(317.3)
        self.assertIn("FMOD 0", fake.commands)
        self.assertIn("RSLP 0", fake.commands)
        self.assertIn(
            f"SENS {app.STFMR_LOCKIN_SR830_SENSITIVITY_CODE}", fake.commands
        )
        self.assertIn(
            f"OFLT {app.STFMR_LOCKIN_SR830_TIME_CONSTANT_CODE}", fake.commands
        )
        self.assertEqual(lock["reference_input"], "Sine")
        self.assertAlmostEqual(sample["r_v"], 2.2360679e-6)
        self.assertTrue(sample["reference_valid"])
        self.assertTrue(sample["measurement_valid"])

    def test_stfmr_sr830_ttl_ref_and_auto_range_are_verified(self):
        class FakeSR830(FakeSharedVisaInstrument):
            def __init__(self):
                super().__init__("Stanford_Research_Systems,SR830,TEST,1.0")
                self.sensitivity = app.STFMR_LOCKIN_SR830_SENSITIVITY_CODE
                self.reference_slope = 0

            def write(self, command):
                super().write(command)
                if command.startswith("SENS "):
                    self.sensitivity = int(command.split()[1])
                if command.startswith("RSLP "):
                    self.reference_slope = int(command.split()[1])
                if command.startswith("OFLT "):
                    # configure() reads the time constant back (2026-10-13).
                    self.time_constant = int(command.split()[1])

            def query(self, command):
                if command == "OFLT?":
                    return str(self.time_constant)
                responses = {
                    "FMOD?": "0",
                    "HARM?": "1",
                    "LIAS?": "0",
                    "FREQ?": "317.3",
                    "SNAP? 1,2,3,4,9": "30e-6,40e-6,60e-6,53.13,317.3",
                }
                if command == "RSLP?":
                    return str(self.reference_slope)
                if command == "SENS?":
                    return str(self.sensitivity)
                if command in responses:
                    return responses[command]
                return super().query(command)

        controller = app.STFMRSR830Controller(lambda _message: None)
        fake = FakeSR830()
        controller.instrument = fake
        configured = controller.configure("TTL Falling", auto_range=True)
        first = controller.read_sample(317.3)
        second = controller.read_sample(317.3)

        self.assertEqual(configured["reference_slope"], 2)
        self.assertIn("RSLP 2", fake.commands)
        self.assertEqual(first["sensitivity_index"], 13)
        self.assertEqual(first["auto_range"], "SENS 13->14 (overload/high)")
        self.assertFalse(first["measurement_valid"])
        self.assertEqual(second["sensitivity_index"], 14)
        self.assertEqual(second["auto_range"], "")
        self.assertTrue(second["measurement_valid"])

    def test_stfmr_normal_completion_turns_off_smb100a(self):
        # Every end zeroes the 4886 as its Zero / OFF does and switches the
        # SMB100A RF off with OUTP? read back, on the page's worker (user,
        # 2026-10-18).
        class FakeKepco:
            connected = True

            def __init__(self):
                self.zero_calls = 0

            def force_output_off(self):
                self.zero_calls += 1

        class FakeSmb:
            connected = True

            def __init__(self):
                self.off_calls = 0

            def rf_off_read_back(self):
                self.off_calls += 1

        class Worker:
            def __init__(self):
                self.jobs = 0

            def submit(self, operation):
                from concurrent.futures import Future
                self.jobs += 1
                future = Future()
                future.set_result(operation())
                return future

        harness = object.__new__(app.CombinedControlApp)
        kepco = FakeKepco()
        smb = FakeSmb()
        harness.stfmr_lockin_running = True
        harness.stfmr_lockin_closed = False
        harness.stfmr_lockin_recorder = None
        harness.stfmr_lockin_after_id = None
        harness.stfmr_lockin_stop_event = __import__("threading").Event()
        harness.stfmr_lockin_executor = worker = Worker()
        harness.post_ui = lambda callback: callback()
        harness.thread_log = lambda _text: None
        harness.stfmr_lockin_controllers = {"kepco": kepco, "smb": smb}
        harness.stfmr_lockin_rows = [{"field_g": 0.0}]
        harness.stfmr_lockin_frequencies_ghz = [5.0]
        harness.stfmr_lockin_status_var = FakeVariable("")
        harness.closing = False
        harness._update_stfmr_lockin_ui = lambda: None

        harness._finish_stfmr_lockin_scan()

        self.assertEqual(worker.jobs, 1, "zeroed on the page's worker")
        self.assertEqual(kepco.zero_calls, 1)
        self.assertEqual(smb.off_calls, 1)
        self.assertFalse(harness.stfmr_lockin_running)
        self.assertEqual(harness.stfmr_lockin_status_var.get(),
                         "Completed; 4886 and RF zeroed; 1 point saved; 1 frequency")

    class FakePNA:
        """A PNA's channel 1 for STFMRPNAFMRController: the measurement
        catalog, window 1's traces, the CW frequency (limited to max_hz) and
        an error queue (``refuse`` holds commands it answers with an error)."""

        def __init__(self, catalog=(), traces=(), max_hz=26.5e9, errors=(), refuse=()):
            self.commands = []
            self.data_index = 0
            self.catalog = dict(catalog)
            self.traces = dict(traces)          # trace number -> measurement name
            self.max_hz = max_hz
            self.frequency = 1e9
            self.errors = list(errors)
            self.refuse = tuple(refuse)

        def write(self, command):
            self.commands.append(command)
            if any(command.startswith(prefix) for prefix in self.refuse):
                self.errors.append(f'-113,"Undefined header; {command}"')
                return
            if command.startswith("CALC1:PAR:DEF:EXT "):
                name, parameter = (part.strip("'") for part in command.split(" ", 1)[1].split(","))
                self.catalog[name] = parameter
            elif command == "*CLS":
                self.errors.clear()
            elif command.startswith("CALC1:PAR:DEL "):
                name = command.split(" ", 1)[1].strip("'")
                if name not in self.catalog:
                    self.errors.append('-200,"Execution error; measurement not found"')
                    return
                del self.catalog[name]
                self.traces = {n: m for n, m in self.traces.items() if m != name}
            elif command.startswith("DISP:WIND1:TRAC") and ":FEED " in command:
                number = int(command[len("DISP:WIND1:TRAC"):command.index(":FEED")])
                if number in self.traces:
                    self.errors.append('-221,"Settings conflict; trace number in use"')
                else:
                    self.traces[number] = command.split(" ", 1)[1].strip("'")
            elif command.startswith("SENS1:FREQ:CW "):
                self.frequency = min(float(command.split(" ", 1)[1]), self.max_hz)

        def query(self, command):
            self.commands.append(command)
            if command == "CALC1:PAR:CAT?":
                if not self.catalog:
                    return '"NO CATALOG"'
                return '"' + ",".join(f"{n},{p}" for n, p in self.catalog.items()) + '"'
            if command == "DISP:WIND1:CAT?":
                return '"' + (",".join(str(n) for n in sorted(self.traces)) or "EMPTY") + '"'
            if command == "SYST:ERR?":
                return self.errors.pop(0) if self.errors else '+0,"No error"'
            if command == "SENS1:FREQ:CW?":
                return f"{self.frequency:+.11E}"
            if command in {"SOUR1:POW1?", "SOUR1:POW2?"}:
                return "-10"
            if command == "*OPC?":
                return "1"
            if command == "CALC1:DATA? FDATA":
                self.data_index += 1
                return str(-10.0 - self.data_index)
            raise AssertionError(f"unexpected query: {command}")

    def pna(self, **fake_options):
        log = []
        controller = app.STFMRPNAFMRController(log.append)
        fake = self.FakePNA(**fake_options)
        controller.instrument = fake
        return controller, fake, log

    def test_stfmr_pna_displays_and_triggers_all_selected_traces_once(self):
        controller, fake, log = self.pna()
        selected = ("S11", "S12", "S21", "S22")
        actual_powers = controller.configure_cw(5.0e9, selected, -10.0)
        values = controller.trigger_and_read(selected)
        self.assertEqual(actual_powers, {1: -10.0, 2: -10.0})
        self.assertEqual(set(values), set(selected))
        self.assertEqual(fake.commands.count("SENS1:SWE:MODE SING"), 1)
        for index, parameter in enumerate(selected, start=1):
            name = f"TRANSPORT_FMR_{parameter}"
            self.assertIn(
                f"DISP:WIND1:TRAC{index}:FEED '{name}'", fake.commands
            )
        self.assertIn("SOUR1:POW1 -10", fake.commands)
        self.assertIn("SOUR1:POW2 -10", fake.commands)
        self.assertEqual(log, [])

    def test_stfmr_pna_setup_sends_only_commands_the_pna_takes(self):
        """User, 2026-11-18 ("fix 1-5"): TRIG:SEQ:SCOP CHAN (the PNA takes
        ALL, CURRent or ACTive) and INIT1:CONT OFF (undone by the next
        TRIG:SEQ:SOUR IMM) are gone; internal trigger, one sweep per read."""
        controller, fake, _log = self.pna()
        controller.configure_cw(5.0e9, ("S21", "S12"), -10.0)
        self.assertFalse([c for c in fake.commands if c.startswith(("TRIG:SEQ:SCOP", "INIT"))])
        self.assertIn("TRIG:SEQ:SOUR IMM", fake.commands)
        self.assertIn("SENS1:SWE:TRIG:MODE CHAN", fake.commands)

    def test_stfmr_pna_cw_frequency_is_read_back(self):
        controller, fake, _log = self.pna(max_hz=26.5e9)
        controller.configure_cw(26.5e9, ("S21",), -10.0)
        self.assertIn("SENS1:FREQ:CW?", fake.commands)
        controller, fake, _log = self.pna(max_hz=26.5e9)
        with self.assertRaisesRegex(RuntimeError, "target 30 GHz, readback 26.5 GHz"):
            controller.configure_cw(30e9, ("S21",), -10.0)
        self.assertNotIn("OUTP ON", fake.commands, "RF stays off")

    def test_stfmr_pna_refused_setup_command_stops_before_rf_on(self):
        controller, fake, _log = self.pna(refuse=("SENS1:SWE:POIN",))
        with self.assertRaisesRegex(RuntimeError, "refused part of the FMR set-up: -113"):
            controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertNotIn("OUTP ON", fake.commands)

    def test_stfmr_pna_errors_from_before_are_logged_not_raised(self):
        controller, fake, log = self.pna(errors=('-410,"Query INTERRUPTED"',))
        controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertIn("OUTP ON", fake.commands)
        self.assertEqual(len(log), 1)
        self.assertIn("errors queued before the FMR set-up, cleared: -410", log[0])

    def test_stfmr_pna_traces_use_free_numbers_and_unticked_ones_are_deleted(self):
        """User, 2026-11-18 ("fix 1-5"): the window's own trace 1 stays; a
        new measurement goes on a free number; one left by an earlier
        selection is deleted (not swept on), and only after the new one is
        made, so channel 1 is never empty (review)."""
        controller, fake, log = self.pna(
            catalog={"CH1_S11_1": "S11", "TRANSPORT_FMR_S12": "S12", "TRANSPORT_FMR_S22": "S22"},
            traces={1: "CH1_S11_1", 2: "TRANSPORT_FMR_S12", 3: "TRANSPORT_FMR_S22"})
        controller.configure_cw(5e9, ("S21", "S12"), -10.0)
        self.assertEqual(fake.catalog, {"CH1_S11_1": "S11", "TRANSPORT_FMR_S21": "S21",
                                        "TRANSPORT_FMR_S12": "S12"})
        self.assertEqual(fake.traces, {1: "CH1_S11_1", 2: "TRANSPORT_FMR_S12", 3: "TRANSPORT_FMR_S21"})
        self.assertEqual(controller.trace_numbers, {"S21": 3})
        self.assertNotIn("CALC1:PAR:DEL 'TRANSPORT_FMR_S12'", fake.commands, "kept, not made again")
        self.assertLess(fake.commands.index("CALC1:PAR:DEF:EXT 'TRANSPORT_FMR_S21','S21'"),
                        fake.commands.index("CALC1:PAR:DEL 'TRANSPORT_FMR_S22'"))
        self.assertEqual(log, [])
        values = controller.trigger_and_read(("S21", "S12"))
        self.assertEqual(set(values), {"S21", "S12"})

    def test_stfmr_pna_a_new_connection_keeps_matching_measurements(self):
        controller, fake, log = self.pna(catalog={"TRANSPORT_FMR_S21": "S21"},
                                         traces={1: "TRANSPORT_FMR_S21"})
        controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertFalse([c for c in fake.commands if c.startswith(("CALC1:PAR:DEF", "CALC1:PAR:DEL", "DISP:"))])
        self.assertEqual(controller.trigger_and_read(("S21",)), {"S21": -11.0})
        self.assertEqual(log, [])

    def test_stfmr_pna_refused_measurement_is_an_error(self):
        controller, fake, log = self.pna(refuse=("CALC1:PAR:DEF:EXT",))
        with self.assertRaisesRegex(RuntimeError, "refused the FMR measurements: -113"):
            controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertNotIn("OUTP ON", fake.commands)
        self.assertEqual(log, [])
        with self.assertRaisesRegex(RuntimeError, "not yet configured"):
            controller.trigger_and_read(("S21",))
        fake.refuse = ()                        # a retry makes it
        controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertEqual(fake.catalog, {"TRANSPORT_FMR_S21": "S21"})

    def test_stfmr_pna_many_old_errors_are_cleared(self):
        controller, fake, log = self.pna(errors=['-221,"Settings conflict"'] * 80)
        controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertIn("*CLS", fake.commands)
        self.assertIn("OUTP ON", fake.commands)
        self.assertEqual(len(log), 1)
        self.assertIn("more than 50 errors queued", log[0])

    def test_stfmr_pna_reading_error_fails_the_reading(self):
        """Review, 2026-11-18: a refused select would leave the last trace
        selected and its value saved under another S-parameter."""
        controller, fake, _log = self.pna()
        controller.configure_cw(5e9, ("S21", "S12"), -10.0)
        fake.refuse = ("CALC1:PAR:SEL 'TRANSPORT_FMR_S12'",)
        with self.assertRaisesRegex(RuntimeError, "error during the reading: -113"):
            controller.trigger_and_read(("S21", "S12"))

    def test_stfmr_pna_same_selection_is_not_set_up_again(self):
        controller, fake, log = self.pna()
        controller.configure_cw(5e9, ("S21",), -10.0)
        fake.commands.clear()
        controller.configure_cw(6e9, ("S21",), -10.0)
        self.assertFalse([c for c in fake.commands if c.startswith(("CALC1:PAR:DEF", "CALC1:PAR:DEL", "DISP:"))])
        # A new selection, or a catalog changed on the PNA, sets up again.
        controller.configure_cw(6e9, ("S12",), -10.0)
        self.assertEqual(fake.catalog, {"TRANSPORT_FMR_S12": "S12"})
        del fake.catalog["TRANSPORT_FMR_S12"]
        controller.configure_cw(6e9, ("S12",), -10.0)
        self.assertEqual(fake.catalog, {"TRANSPORT_FMR_S12": "S12"})
        self.assertEqual(log, [])

    def test_stfmr_pna_display_errors_are_logged_and_measuring_goes_on(self):
        controller, fake, log = self.pna(refuse=("DISP:WIND1:TRAC",))
        controller.configure_cw(5e9, ("S21",), -10.0)
        self.assertIn("OUTP ON", fake.commands)
        self.assertEqual(len(log), 1)
        self.assertIn("may not all show in window 1", log[0])
        self.assertEqual(controller.trigger_and_read(("S21",)), {"S21": -11.0})

    def test_stfmr_pna_power_limit_and_source_port_mapping(self):
        controller = app.STFMRPNAFMRController(lambda _message: None)
        self.assertEqual(controller.source_ports_for(("S11", "S21")), (1,))
        self.assertEqual(controller.source_ports_for(("S12", "S22")), (2,))
        self.assertEqual(controller.source_ports_for(("S11", "S22")), (1, 2))
        with self.assertRaises(ValueError):
            controller.configure_cw(5.0e9, ("S21",), 0.01)

    def test_stfmr_fmr_scan_points_are_inclusive_and_bounded(self):
        points = app.CombinedControlApp._build_stfmr_one_way_points(
            -1.0, 1.0, 0.3
        )
        self.assertEqual(points[0], -1.0)
        self.assertEqual(points[-1], 1.0)
        self.assertTrue(all(-1.0 <= item <= 1.0 for item in points))
        with self.assertRaises(ValueError):
            app.CombinedControlApp._build_stfmr_one_way_points(
                -1.0, 1.0, 0.0
            )
        with self.assertRaises(ValueError):
            app.CombinedControlApp._build_stfmr_one_way_points(
                -11.0, 1.0, 0.1
            )

    def test_stfmr_frequency_points_are_inclusive_in_both_directions(self):
        upward = app.CombinedControlApp._build_stfmr_frequency_points(
            5.0, 10.0, 1.0
        )
        self.assertEqual(
            upward,
            [5e9, 6e9, 7e9, 8e9, 9e9, 10e9],
        )
        downward = app.CombinedControlApp._build_stfmr_frequency_points(
            10.0, 5.0, 2.0
        )
        self.assertEqual(downward, [10e9, 8e9, 6e9, 5e9])
        with self.assertRaises(ValueError):
            app.CombinedControlApp._build_stfmr_frequency_points(
                5.0, 10.0, 0.0
            )

    def test_stfmr_field_settle_rejects_transition_and_accepts_quiet_tail(self):
        checker = app.CombinedControlApp._stfmr_field_samples_stable
        self.assertFalse(checker([0.0, 120.0, 260.0]))
        self.assertFalse(checker([400.0, 410.0]))
        self.assertTrue(checker([399.2, 400.1, 399.8]))
        self.assertTrue(checker([1998.0, 2000.0, 2001.0]))

    def test_stfmr_discards_first_two_startup_points(self):
        checker = app.CombinedControlApp._stfmr_should_discard_startup_point
        self.assertTrue(checker(0))
        self.assertTrue(checker(1))
        self.assertFalse(checker(2))
        self.assertFalse(checker(120))
        # Loop 2 onwards starts with the jump back to start: its first two too.
        self.assertTrue(checker(10, 10))
        self.assertTrue(checker(11, 10))
        self.assertFalse(checker(12, 10))
        self.assertFalse(checker(9, 10))

    def test_stfmr_progress_clamps_to_valid_scan_range(self):
        progress = FakeProgressbar()
        app.CombinedControlApp._set_stfmr_progress(progress, 3, 10)
        self.assertEqual(progress.options, {"maximum": 10, "value": 3})
        app.CombinedControlApp._set_stfmr_progress(progress, 12, 10)
        self.assertEqual(progress.options, {"maximum": 10, "value": 10})
        app.CombinedControlApp._set_stfmr_progress(None, 1, 0)

    def test_duplicate_resource_is_rejected_until_release(self):
        first = object()
        second = object()
        app.acquire_instrument_lease("GPIB0::24::INSTR", first, "first")
        with self.assertRaises(RuntimeError):
            app.acquire_instrument_lease("gpib0::24::instr", second, "second")
        # The same controller may own several roles (source/meter); reusing
        # one address inside that controller must also be rejected.
        with self.assertRaises(RuntimeError):
            app.acquire_instrument_lease("GPIB0::24::INSTR", first, "other role")
        app.release_instrument_lease("GPIB0::24::INSTR", first)
        app.acquire_instrument_lease("gpib0::24::instr", second, "second")

    def test_ui_queue_drain_is_time_sliced(self):
        class FakeRoot:
            def __init__(self):
                self.after_calls = []

            @staticmethod
            def winfo_exists():
                return True

            def after(self, delay_ms, callback):
                self.after_calls.append((delay_ms, callback))

        harness = object.__new__(app.CombinedControlApp)
        harness.root = FakeRoot()
        harness.ui_queue = app.queue.Queue()
        harness.closing = False
        completed = []
        callback_count = app.UI_QUEUE_MAX_CALLBACKS_PER_TICK + 5
        for index in range(callback_count):
            harness.ui_queue.put(lambda value=index: completed.append(value))

        app.CombinedControlApp.drain_ui_queue(harness)

        self.assertGreater(len(completed), 0)
        self.assertLessEqual(
            len(completed), app.UI_QUEUE_MAX_CALLBACKS_PER_TICK
        )
        self.assertFalse(harness.ui_queue.empty())
        self.assertEqual(
            harness.root.after_calls[-1][0], app.UI_QUEUE_ACTIVE_DELAY_MS
        )

    def test_legacy_labone_bridge_source_still_compiles(self):
        # The embedded bridge is launched by an older Python/LabOne runtime;
        # compile it separately because normal py_compile only sees a string.
        compile(app._MFLI_BRIDGE_SOURCE, "<mfli_bridge>", "exec")
        self.assertIn(
            'requested_imp50 = int(request.get("input_imp50", 0))',
            app._MFLI_BRIDGE_SOURCE,
        )
        self.assertIn(
            "daq.setInt(imp50_node, requested_imp50)",
            app._MFLI_BRIDGE_SOURCE,
        )
        self.assertIn(
            "daq.setDouble(scaling_node, requested_scaling)",
            app._MFLI_BRIDGE_SOURCE,
        )
        self.assertIn('"actual_scaling"', app._MFLI_BRIDGE_SOURCE)

    def test_nice_linear_ticks_keep_rolling_axes_readable(self):
        axis_min, axis_max, ticks, step = app.nice_linear_ticks(
            3.38,
            23.4,
            expand_limits=False,
        )
        self.assertEqual((axis_min, axis_max), (3.38, 23.4))
        self.assertEqual(step, 5.0)
        self.assertEqual(ticks, [5.0, 10.0, 15.0, 20.0])

    def test_nice_linear_ticks_expand_small_readback_axis(self):
        axis_min, axis_max, ticks, step = app.nice_linear_ticks(
            0.0,
            0.00108,
            include_zero=True,
        )
        self.assertEqual(axis_min, 0.0)
        self.assertTrue(axis_max >= 0.00108)
        self.assertEqual(step, 0.00025)
        self.assertEqual(ticks[:3], [0.0, 0.00025, 0.0005])

    def test_6221_ac_mode_converts_gui_rms_to_remote_peak(self):
        controller = app.NonLocalACController(lambda _message: None)
        controller.source = Fake6221()
        controller.nanovoltmeter = Fake2182()
        frequency, _readbacks = controller.configure(
            0.1,
            13.7,
            50.0,
            {},
            use_nanovoltmeter=True,
            output_mode="AC",
        )
        expected_peak_a = math.sqrt(2.0) * 0.1e-3
        self.assertTrue(math.isclose(frequency, 13.7))
        self.assertTrue(math.isclose(controller.source.wave_amplitude,
                                     expected_peak_a))

    def test_the_zurich_is_set_up_as_on_ppms(self):
        """User, 2026-10-09: the Non-local Zurich as the PPMS module's: on
        MF-MD the reference on Demod 4 and the unused demodulators off."""
        for has_md, expected in ((True, 3), (False, None)):
            with self.subTest(mf_md=has_md):
                controller = app.NonLocalACController(lambda _message: None)
                controller.source = Fake6221()
                controller.mfli_daq = object()
                controller.mfli_has_multi_demod = lambda: has_md
                controller.configure_mfli = mock.Mock(return_value={"sample_rate_hz": 10.0})
                controller.disable_unused_ppms_demods = mock.Mock()
                controller.configure(0.1, 17.3, 50.0, {}, mfli_config={
                    "coupling": "AC", "harmonic": 2, "channel": "R", "reference_source": "Trigger In 1",
                    "input_impedance": "10 MΩ", "input_scaling": 1.0, "timeconstant_s": 0.1})
                kwargs = controller.configure_mfli.call_args.kwargs
                self.assertEqual(kwargs["external_reference_demodulator"], expected)
                self.assertEqual((kwargs["input_impedance"], kwargs["input_scaling"]), ("10 MΩ", 1.0))
                if has_md:
                    controller.disable_unused_ppms_demods.assert_called_once_with("1")
                else:
                    controller.disable_unused_ppms_demods.assert_not_called()
        # Several orders ask for Demod 4 themselves; nothing is switched off here.
        controller = app.NonLocalACController(lambda _message: None)
        controller.source = Fake6221()
        controller.mfli_daq = object()
        controller.mfli_has_multi_demod = lambda: True
        controller.configure_mfli = mock.Mock(return_value={})
        controller.disable_unused_ppms_demods = mock.Mock()
        controller.configure(0.1, 17.3, 50.0, {}, mfli_config={
            "coupling": "AC", "harmonic": 1, "channel": "R", "reference_source": "Trigger In 1",
            "input_impedance": "10 MΩ", "input_scaling": 1.0, "external_reference_demodulator": 3})
        self.assertEqual(controller.configure_mfli.call_args.kwargs["external_reference_demodulator"], 3)
        controller.disable_unused_ppms_demods.assert_not_called()

if __name__ == "__main__":
    unittest.main()
