"""PPMS page, Frequency and Frequency+Current scans (user, 2026-10-18: "add
frequency and frequency+current scan in the PPMS module").

The frequencies are the whole-number primes from Start to End Hz (no step), as
Non-local's frequency scan.  Frequency+Current runs the whole current sweep at
each frequency.  No Tk window and no instrument: fake SCPI instruments answer,
and a fake clock moves only when the scan waits.
"""
import csv
import math
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from test_nonlocal_keithley import Var
from test_ppms_motor_debug import app
from test_ppms_sr830_tc import build_ppms_panel


class Log(list):
    """The instruments' shared log; ``hook`` sees each entry as it is
    added (a Stop pressed at that step)."""

    def __init__(self):
        super().__init__()
        self.hook = None

    def append(self, entry):
        super().append(entry)
        if self.hook is not None:
            self.hook(entry)


class Clock:
    """time.monotonic for a test: it moves only when the scan waits."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ClockEvent:
    """The scan's stop event.  Each wait is logged and moves the clock on;
    ``on_wait`` may set the event (a Stop pressed during that wait)."""

    def __init__(self, clock, log):
        self.clock, self.log, self.flag, self.on_wait = clock, log, False, None

    def is_set(self):
        return self.flag

    def set(self):
        self.flag = True

    def clear(self):
        self.flag = False

    def wait(self, seconds):
        self.log.append(("wait", round(float(seconds), 9)))
        if self.on_wait is not None:
            self.on_wait(float(seconds))
        self.clock.now += float(seconds)
        return self.flag


class Fake6221:
    """The 6221's sine as the PPMS page drives it: *RST and ABOR stop it,
    INIT starts it, and every command and query goes to the log."""

    def __init__(self, log):
        self.log = log
        self.output, self.frequency, self.amplitude = 1, 317.3, math.sqrt(2) * 1e-3
        self.compliance, self.range = 50.0, 0.1
        self.on_write = None

    def write(self, command):
        self.log.append(("6221", command))
        name, _, value = command.partition(" ")
        if command in ("*RST", "SOUR:WAVE:ABOR", "OUTP OFF"):
            self.output = 0
        if command == "*RST":
            self.frequency, self.amplitude = 1000.0, 0.0
        elif name == "SOUR:WAVE:FREQ":
            self.frequency = float(value)
        elif name == "SOUR:WAVE:AMPL":
            self.amplitude = float(value)
        elif name == "CURR:COMP":
            self.compliance = float(value)
        elif name == "SOUR:CURR:RANG":
            self.range = float(value)
        elif command == "SOUR:WAVE:INIT":
            self.output = 1
        if self.on_write is not None:
            self.on_write(command)

    def query(self, command):
        if command != "SYST:ERR?":
            self.log.append(("6221?", command))
        return {
            "SYST:ERR?": '0,"No error"', "OUTP:LTE?": "0", "OUTP?": str(self.output),
            "SOUR:WAVE:FREQ?": f"{self.frequency:.12g}", "SOUR:WAVE:AMPL?": f"{self.amplitude:.12e}",
            "CURR:COMP?": f"{self.compliance:g}", "SOUR:CURR:RANG?": f"{self.range:.12e}",
            "STAT:MEAS:COND?": "0",
        }[command]

    def safe_output_off(self):
        self.write("SOUR:WAVE:ABOR")
        self.write("OUTP OFF")


class FakeSR830:
    """An SR830 locked to the 6221's marker.  Its UNLK bit latches: the
    first LIAS? after the sine stopped or changed reads 8, as the real
    lock-in reports a lost reference.  ``never_locks_at`` makes it read a
    wrong reference frequency there."""

    def __init__(self, log, source, address, harmonic):
        self.log, self.source, self.address, self.harmonic = log, source, address, harmonic
        self.seen = (source.output, source.frequency)
        self.never_locks_at = None

    def reference(self):
        if not self.source.output:
            return 0.0
        if self.never_locks_at is not None and math.isclose(self.source.frequency, self.never_locks_at):
            return self.source.frequency * 1.5
        return self.source.frequency

    def write(self, command):
        self.log.append((f"sr830_{self.address}", command))
        name, _, value = command.partition(" ")
        if name == "HARM":
            self.harmonic = int(value)

    def query(self, command):
        if command != "*ESR?":
            self.log.append((f"sr830_{self.address}?", command))
        if command == "LIAS?":
            now = (self.source.output, self.source.frequency)
            changed, self.seen = now != self.seen or not self.source.output, now
            return "8" if changed else "0"
        frequency = self.reference()
        return {
            "*ESR?": "0", "HARM?": str(self.harmonic), "FMOD?": "0",
            "RSLP?": str(app.PPMS_SR830_REFERENCE_SLOPE), "OFLT?": "10",
            "FREQ?": f"{frequency:.12g}",
            "SNAP? 1,2,3,4,9": f"{1e-6 * self.address},0,{1e-6 * self.address},0,{frequency:.12g}",
        }[command]


class FakeZurich:
    """The Zurich on the PPMS page: its ExtRef PLL needs one read to follow
    a new frequency (``instant`` locks it at once, for a scan that does not
    wait for it).  ``never_locks`` keeps it unlocked.

    ``stale_reads`` is LabOne 18.12's case: no lock flag, and after a change
    that many reads still report the frequency it followed before, valid
    whenever that is within 0.5 % of the one expected."""

    def mfli_has_multi_demod(self):
        return True

    def __init__(self, log, source):
        self.log, self.source = log, source
        self.lock = threading.RLock()
        self.mfli_connected, self.mfli_config = True, {"timeconstant_s": 1.0}
        self.following = None
        self.never_locks = self.instant = False
        self.stale_reads, self.held, self.pll_hz = 0, 0, source.frequency

    def configure_mfli(self, *args, **options):
        self.log.append(("zurich", "configure_mfli"))

    def configure_second_harmonic(self, *args, **options):
        self.log.append(("zurich", "configure_second_harmonic"))

    def configure_third_harmonic(self, *args, **options):
        self.log.append(("zurich", "configure_third_harmonic"))

    def disable_unused_ppms_demods(self, *args):
        self.log.append(("zurich", "disable_unused_ppms_demods"))

    def read_mfli(self, expected):
        self.log.append(("zurich?", "read_mfli", float(expected)))
        state = (self.source.output, self.source.frequency)
        if self.stale_reads:
            if state != self.following:
                self.following, self.held = state, self.stale_reads
            if self.held:
                self.held -= 1
            else:
                self.pll_hz = self.source.frequency if self.source.output else 0.0
            valid = math.isclose(self.pll_hz, expected, rel_tol=5e-3, abs_tol=0.1)
            return {"X": 2e-6, "Y": 0.0, "R": 2e-6, "phase_deg": 0.0, "reference_frequency_hz": self.pll_hz,
                    "reference_valid": valid, "extref_locked": None,
                    "status_text": "LabOne 18.12 judges LOCK by reference-frequency convergence",
                    "input_overload": False, "input_range_v": 0.01, "auto_range": ""}
        locked = (not self.never_locks and self.source.output and (self.following == state or self.instant)
                  and math.isclose(self.source.frequency, expected, rel_tol=5e-3, abs_tol=0.1))
        self.following = state
        return {"X": 2e-6, "Y": 0.0, "R": 2e-6, "phase_deg": 0.0,
                "reference_frequency_hz": self.source.frequency if self.source.output else 0.0,
                "reference_valid": bool(locked), "extref_locked": bool(locked),
                "status_text": "OK" if locked else "Trigger In 1 not locked",
                "input_overload": False, "input_range_v": 0.01, "auto_range": ""}

    def read_stfmr_mfli(self, expected, auto_range=False, initial=False, attempts=0):
        return self.read_mfli(expected)

    def read_mfli_four_demods(self):
        self.log.append(("zurich?", "four_demods"))
        sample = {"zurich_demod1_enabled": True}
        for index in range(1, 5):
            sample.update({f"zurich_demod{index}_x_v": 2e-6 / index, f"zurich_demod{index}_y_v": 0.0,
                           f"zurich_demod{index}_r_v": 2e-6 / index, f"zurich_demod{index}_theta_deg": 0.0,
                           f"zurich_demod{index}_harmonic": index, f"zurich_demod{index}_input": 0})
        return sample


def controller(label, instrument, resource):
    return types.SimpleNamespace(label=label, instrument=instrument, resource_name=resource,
                                 lock=threading.RLock(), connected=True,
                                 safe_output_off=getattr(instrument, "safe_output_off", lambda: None))


class Motor:
    """The PPMS rotator, at rest at the fixed angle: no move is needed."""

    def __init__(self, _active):
        self.on_read = None

    def read(self):
        return {"angle_deg": 26.0, "status": "AtTarget"}

    def move_and_verify(self, *args, **options):
        raise AssertionError("a frequency scan at the fixed angle needs no move")


class Rig:
    """A PPMS page (the real PPMSPanel methods) on fake instruments, the
    6221 already running from a Set I at 317.3 Hz."""

    def __init__(self, test, mode, frequencies, currents, zurich=True, preserve_on_stop=True):
        self.test = test
        self.log = Log()
        self.clock = Clock()
        page = app.PPMSPanel.__new__(app.PPMSPanel)
        page.parent_app = types.SimpleNamespace()   # nothing borrowed from a main page
        page.closing = False
        page.root = None
        page.ppms_field_scan_stop_event = self.stop = ClockEvent(self.clock, self.log)
        page.ppms_scan_preserve_on_stop = preserve_on_stop
        self.source = Fake6221(self.log)
        self.sr830 = {"830_a": FakeSR830(self.log, self.source, 8, 1), "830_c": FakeSR830(self.log, self.source, 10, 3)}
        page.ppms_instrument_controllers = {
            "6221": controller("Keithley 6221", self.source, "GPIB0::30::INSTR"),
            "830_a": controller("SR830-1", self.sr830["830_a"], "GPIB0::8::INSTR"),
            "830_c": controller("SR830-3", self.sr830["830_c"], "GPIB0::10::INSTR"),
        }
        page.ppms_sr830_range_states = {key: types.SimpleNamespace(sensitivity_index=17, clear_latch_pending=False)
                                        for key in self.sr830}
        page._ppms_autorange_sr830 = lambda *args, **options: 0.0
        self.zurich = FakeZurich(self.log, self.source)
        page.zurich_controller = self.zurich
        page.zurich_closed = False
        page.zurich_scan_enabled = zurich
        page.zurich_scan_configured = False
        page.zurich_scan_harmonic, page.zurich_scan_reference, page.zurich_scan_tau = "1", "Trigger In 1", 1.0
        page._display_zurich_sample = lambda sample: self.log.append(("display", "zurich"))
        remote = types.SimpleNamespace(backend="MultiPyVu", active=object())
        remote.set_temperature = lambda target, rate, approach: self.log.append(("ppms", "set_temperature", target))
        remote.set_field = lambda *args: test.fail("a frequency scan never commands the field")
        page.ppms_environment_controller = remote
        page._read_ppms_live = lambda: dict(field_oe=1234.0, field_status="Persistent",
                                            temperature_k=300.0, temperature_status="Stable")
        page._apply_ppms_environment_readback = lambda data: None
        page.ppms_last_readback = None
        page.post_ui = lambda callback: callback()
        page.thread_log = lambda text: self.log.append(("log", text))
        for name in ("ppms_field_scan_status_var", "ppms_transport_status_var", "ppms_field_scan_eta_var",
                     "ppms_current_live_var"):
            setattr(page, name, Var(""))
        page.ppms_field_scan_progress = mock.Mock()
        page._redraw_ppms_transport_plot = lambda: None
        page.ppms_scan_context = {}
        page.ppms_field_scan_rows = []
        page.ppms_field_scan_started_at = self.clock.now
        self.folder = tempfile.TemporaryDirectory()
        test.addCleanup(self.folder.cleanup)
        page.ppms_live_csv_path = Path(self.folder.name) / "scan.csv"
        page.ppms_live_csv_fields = None
        active = tuple(self.sr830)
        settings = app.validate_ppms_transport_scan_settings(
            currents[0], (frequencies or (317.3,))[0], 50.0, 1, 2, active, allow_no_lockins=zurich, harmonic_c=3)
        settings.update(nested={"angle": (26.0,), "temperature": (300.0,)}, currents=tuple(currents),
                        scan_mode=mode, acquisition_s=1.0, temperature_rate=10.0, temperature_approach=1,
                        slowdown=14, harmonic_pass=1)
        if frequencies is not None:
            settings["frequencies"] = tuple(frequencies)
        page.ppms_field_scan_total = len(currents) * len(frequencies or (1,))
        self.page, self.settings = page, settings

    def run(self):
        """The scan as Start runs it: its one harmonic pass through
        _ppms_scan_with_final_field, which zeroes the 6221 at every end
        (user, 2026-10-18)."""
        settings = dict(self.settings)
        settings["harmonic_passes"] = (dict(self.settings),)
        with mock.patch.object(app.time, "monotonic", self.clock), \
                mock.patch.object(app.time, "sleep", lambda _s: None), \
                mock.patch.object(app, "PPMSMotorDebug", Motor):
            self.page._ppms_scan_with_final_field([(1, 1, 1, 1234.0)], 100.0, 0.0, 1, settings)

    def rows(self):
        with self.page.ppms_live_csv_path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def header(self):
        with self.page.ppms_live_csv_path.open(encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle))

    def index(self, entry, start=0):
        return self.log.index(entry, start)

    def stop_at(self, entry, occurrence=1):
        """Press Stop (or "I off", with preserve_on_stop False) when the
        log gets ``entry`` for the ``occurrence``-th time."""
        seen = []

        def hook(added):
            if added == entry:
                seen.append(added)
                if len(seen) == occurrence:
                    self.stopped_at = len(self.log)
                    self.stop.set()
        self.log.hook = hook

    def assert_switched_off(self):
        """Switched off at the end, and read back as off (review, 2026-10-18),
        by the zeroing every ending has (user, 2026-10-18)."""
        sent = [entry for entry in self.log if entry[0] in ("6221", "6221?")]
        self.test.assertEqual(sent[-3:], [("6221", "SOUR:WAVE:ABOR"), ("6221", "OUTP OFF"), ("6221?", "OUTP?")])
        self.test.assertEqual(self.source.output, 0)
        self.test.assertEqual(self.page.ppms_transport_status_var.get(),
                              "Transport acquisition: 6221 output OFF (read back)")
        self.test.assertEqual(self.page.ppms_scan_outputs, {"6221": "zeroed"})
        self.test.assertIn(("log", "PPMS scan end: 6221 zeroed"), self.log)


class PrimeListTests(unittest.TestCase):
    pass

class ModeTableTests(unittest.TestCase):
    """Every mode-keyed table and branch knows both new modes."""

    pass

def launcher(test, mode, main_row, outer=("7", "97"), harmonics=("1", "2", "3"), frequency_box="317.3",
             current_box="1"):
    """The PPMS Start (no window): returns (page, Yes/No text, settings, estimate s), or the error text."""
    page = app.CombinedControlApp.__new__(app.CombinedControlApp)
    page.ppms_field_scan_running = page.ppms_environment_busy = False
    page.closing = False
    page._require_ppms_control_ready = mock.Mock()
    page.ppms_simple_mode = Var(mode)
    page.ppms_simple_range = [Var(value) for value in main_row]
    page.ppms_temperature_scan_range = [Var(value) for value in ("300", "290", "5")]
    page.ppms_frequency_scan_range = [Var(value) for value in outer]
    boxes = dict(ppms_acquisition_time_var="1", ppms_field_target_var="1234", ppms_temperature_target_var="300",
                 ppms_motor_target_var="26", ppms_field_scan_stable_var="0", ppms_field_rate_var="100",
                 ppms_field_approach_var="No overshoot", ppms_transport_current_var=current_box,
                 ppms_transport_frequency_var=frequency_box, ppms_transport_compliance_var="50",
                 ppms_motor_confirm_var=True, ppms_temperature_rate_var="10",
                 ppms_temperature_approach_var="No overshoot", ppms_motor_speed_var="14")
    for name, value in boxes.items():
        setattr(page, name, Var(value))
    for key, value in zip(app.PPMS_SR830_KEYS, harmonics):
        setattr(page, app.PPMS_SR830_HARMONIC_ATTRS[key], Var(value))
    page.ppms_environment_controller = types.SimpleNamespace(backend=app.PPMS_QDINSTRUMENT_BACKEND)
    page.ppms_instrument_controllers = {
        key: types.SimpleNamespace(connected=True, resource_name=f"GPIB0::{address}::INSTR")
        for key, address in (("6221", 30), ("830_a", 8), ("830_b", 9), ("830_c", 10))}
    page.ppms_last_readback = dict(temperature_k=300.0, field_oe=1234.0, angle_deg=26.0)
    page.ppms_field_scan_stop_event = threading.Event()
    for name in ("_redraw_ppms_transport_plot", "_update_ppms_control_ui", "ppms_executor",
                 "ppms_field_scan_progress", "ppms_field_scan_eta_var", "ppms_transport_status_var"):
        setattr(page, name, mock.Mock())
    page.ppms_field_scan_status_var = Var("")
    page.root = None
    page.thread_log = mock.Mock()
    estimates = []
    format_duration = page._format_scan_duration
    page._format_scan_duration = lambda seconds: estimates.append(seconds) or format_duration(seconds)
    with tempfile.TemporaryDirectory() as folder, \
            mock.patch.object(app.simpledialog, "askstring", return_value=""), \
            mock.patch.object(app.messagebox, "askyesno", return_value=True) as ask, \
            mock.patch.object(app.filedialog, "askdirectory", return_value=folder), \
            mock.patch.object(app.messagebox, "showerror") as error:
        page.start_ppms_field_scan()
        if error.called:
            page.ppms_executor.submit.assert_not_called()
            return error.call_args.args[1]
    test.assertTrue(page.ppms_field_scan_running)
    args = page.ppms_executor.submit.call_args.args
    return page, ask.call_args.args[1], args[-1], estimates[0]


class StartTests(unittest.TestCase):
    pass

class SequenceTests(unittest.TestCase):
    """The per-frequency hardware sequence, on the real worker methods."""

    pass

class PlotTests(unittest.TestCase):
    @staticmethod
    def base_page(rows, mode):
        page = app.CombinedControlApp.__new__(app.CombinedControlApp)
        page.calls = []
        page._draw_nonlocal_series = lambda *args, **options: page.calls.append((args, options))
        page.ppms_transport_canvas = object()
        page.ppms_transport_canvases = {("830_a", channel): object() for channel in ("x", "y", "theta")}
        page.ppms_transport_plot_frames = {}
        page.ppms_plot_addresses = {"830_a": 8}
        page.ppms_instrument_controllers = {"830_a": types.SimpleNamespace(connected=True,
                                                                           resource_name="GPIB0::8::INSTR")}
        page.ppms_transport_harmonic_a_var = Var("1")
        page.ppms_field_scan_rows = rows
        page.ppms_active_scan_mode = mode
        page.ppms_plot_axis = app.PPMS_SCAN_PLOT_AXES[mode]
        return page

    @staticmethod
    def panel_page(rows, mode):
        page = app.PPMSPanel.__new__(app.PPMSPanel)
        page.parent_app = types.SimpleNamespace()
        page.calls = []
        page._draw_nonlocal_series = lambda *args, **options: page.calls.append((args, options))
        page.ppms_transport_canvas = None
        page.ppms_harmonic_canvases = {(1, channel): object() for channel in ("x", "y", "theta")}
        page.ppms_lockin_selection = {"830_a": Var(True), "zurich": Var(False)}
        page.ppms_instrument_controllers = {"830_a": types.SimpleNamespace(connected=True,
                                                                           resource_name="GPIB0::8::INSTR")}
        page.ppms_plot_addresses = {"830_a": 8}
        page.ppms_transport_harmonic_a_var = Var("1")
        page.ppms_field_scan_rows = rows
        page.ppms_active_scan_mode = mode
        page.ppms_plot_axis = app.PPMS_SCAN_PLOT_AXES[mode]
        return page

    @staticmethod
    def rows(frequencies, currents):
        return [{"6221_frequency_hz": f, "6221_current_rms_ma": i, "loop": 1, "temperature_index": 1,
                 "target_temperature_k": 300.0, "sr830_8_x_v": f * i * 1e-6, "sr830_8_y_v": 0.0,
                 "sr830_8_r_v": f * i * 1e-6, "sr830_8_theta_deg": 0.0, "sr830_8_harmonic": 1}
                for f in frequencies for i in currents]

class SHVUnchangedTests(unittest.TestCase):
    """The SHHV page (RTEPanel) inherits this code; it must not change."""

    def test_the_shv_page_keeps_its_own_modes_and_methods(self):
        import inspect
        source = inspect.getsource(app.RTEPanel)
        # Its own modes, Angle+Field and Angle+Current since 2026-10-18 (user).
        # The page's own list, RTE_SCAN_MODES.
        self.assertIn("values=self.rte_scan_modes", source)
        self.assertIs(app.RTEPanel.rte_scan_modes, app.RTE_SCAN_MODES)
        # Angle+Field is SHHV's own (user, 2026-11-17); Switch (user,
        # 2026-11-22) and Switch2 (user, 2026-11-23) are the last choices; no
        # frequency mode.
        self.assertEqual(app.RTE_SCAN_MODES,
                         ("Field", "Current", "Angle+Field", "Angle+Current", "Field+Angle", "Field+Current", "Switch", "Switch-loop", "Switch2"))
        for name in ("Frequency", "PPMS_SCAN_MODES", "_ppms_frequency_scan_block", "_ppms_set_up_frequency",
                     "_ppms_wait_zurich_reference", "reference_timeout_s", "frequency_settle_s"):
            self.assertNotIn(name, source.replace("RTE_TRANSPORT_FREQUENCY_HZ", "").replace("Frequency Hz", ""))
        for name in ("build_ppms_ui", "start_ppms_field_scan", "_redraw_ppms_transport_plot",
                     "_update_ppms_control_ui", "_rte_mode_changed"):
            self.assertIn(name, app.RTEPanel.__dict__, f"SHHV has its own {name}")

if __name__ == "__main__":
    unittest.main()
