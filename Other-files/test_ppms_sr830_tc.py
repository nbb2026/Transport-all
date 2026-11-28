"""PPMS page, the user's two changes of 2026-10-14:

- the Zurich row's "Time constant s" reads "TC (s)", as on RT-E;
- one 'SR830 TC' dropdown for the page's three SR830s (1 ms to 10 s, the
  STFMR page's OFLT codes, default 1 s = OFLT 10, what Connect always set):
  Connect sets the choice and reads it back, a new choice is set on every
  connected SR830 on the PPMS worker, and it is locked while busy.  RT-E
  keeps OFLT 10 at Connect and has no such control.

The review of that change (2026-10-14) adds: the scan point's 180 s
autorange limit grows with the time constant; an idle poll never cuts short
the 5-time-constant wait a change sets; each scan reads OFLT? for its CSV
column; the scan-start confirmation notes a Settle s shorter than 5 long
time constants; and a mouse-wheel turn over the dropdown does nothing.
That note is superseded by the user's rule of the same day: every reading
waits at least LOCKIN_SETTLE_TAUS time constants (7 at first, then 1 x TC,
the user's later choice that day: "change all to 1*TC please"), and the
confirmation shows the wait.  For that wait RT-E's scan start reads OFLT?
too (a query, no write).

No Tk window and no instrument: the real pages are built on stand-in
widgets, and the SR830s are fakes that answer from the commands they were
sent.  Every message box is mocked, and creating a Tk root fails the test.
"""
import csv
import math
import tempfile
import threading
import time
import tkinter
import tkinter.messagebox
import types
import unittest
from concurrent.futures import Future
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

from test_ppms_motor_debug import app
from test_ppms_two_panels import ImmediateExecutor, Var


class StandIn:
    """A widget that keeps its master, options and grid cell; any other
    widget call does nothing."""

    def __init__(self, master=None, *_args, **options):
        self.master, self.options = master, dict(options)
        self.grid_options, self.children = None, []
        self.kind = type(self).__name__
        if isinstance(master, StandIn):
            master.children.append(self)

    def grid(self, **options):
        self.grid_options = dict(options)
        return self

    def bind(self, sequence, function=None, add=None):
        self.__dict__.setdefault("bindings", {})[sequence] = function

    def grid_configure(self, **options):
        self.grid_options = {**(self.grid_options or {}), **options}

    def grid_info(self):
        return dict(self.grid_options or {})

    def grid_remove(self):
        self.grid_options = None

    def winfo_children(self):
        return list(self.children)

    def configure(self, *_style, **options):
        self.options.update(options)

    config = configure

    def cget(self, name):
        return self.options.get(name, "")

    def winfo_class(self):
        return "T" + self.kind

    def winfo_reqwidth(self):
        return 70

    def winfo_reqheight(self):
        return 16

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *_args, **_options: None


class Kinds:
    """A stand-in ttk: one StandIn subclass per widget name, so isinstance
    checks in the program still work."""

    def __init__(self):
        self.made = []
        self.classes = {}

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name not in self.classes:
            made = self.made

            class Kind(StandIn):
                def __init__(self, *args, **options):
                    super().__init__(*args, **options)
                    made.append(self)

            Kind.__name__ = name
            self.classes[name] = Kind
        return self.classes[name]


def _parent():
    parent = app.CombinedControlApp.__new__(app.CombinedControlApp)
    parent.root = mock.Mock()
    parent.closing = False
    parent.ui_queue = mock.Mock()
    parent.post_ui = lambda callback: callback()
    parent.thread_log = mock.Mock()
    parent.ui_scale = parent.canvas_scale = 1.0
    return parent


def _patches(stack, ttk):
    font = types.SimpleNamespace(
        nametofont=lambda *_args, **_options: types.SimpleNamespace(measure=lambda text: 7 * len(text)),
        Font=lambda *_args, **_options: types.SimpleNamespace(measure=lambda text: 7 * len(text)))
    stack.enter_context(mock.patch.object(app, "ttk", ttk))
    stack.enter_context(mock.patch.object(app, "tkfont", font))
    stack.enter_context(mock.patch.object(app.tk, "Canvas", ttk.Canvas))
    for name in ("StringVar", "IntVar", "BooleanVar", "DoubleVar"):
        stack.enter_context(mock.patch.object(app.tk, name, Var))
    stack.enter_context(mock.patch.object(app, "ThreadPoolExecutor", ImmediateExecutor))
    stack.enter_context(mock.patch.object(app, "NonLocalACController", return_value=mock.Mock(mfli_connected=False)))
    stack.enter_context(mock.patch.object(
        app, "create_zurich_chooser",
        lambda master, *_args, **_options: types.SimpleNamespace(
            zurich_shortfall=0, grid=lambda **_o: None, configure=lambda **_o: None, master=master)))
    stack.enter_context(mock.patch.object(
        app.CombinedControlApp, "_create_connection_indicator", lambda self, master, _name: StandIn(master)))
    stack.enter_context(mock.patch.object(app.CombinedControlApp, "_set_connection_indicator", mock.Mock()))
    stack.enter_context(mock.patch.object(app.CombinedControlApp, "_redraw_ppms_transport_plot", lambda self: None))
    stack.enter_context(mock.patch.object(app.CombinedControlApp, "_draw_nonlocal_series", mock.Mock()))


def _build(cls):
    """The real panel constructor (page build and Zurich row) on stand-ins;
    afterwards its SR830 slots hold fake SR830s and Tk callbacks run at once."""
    ttk = Kinds()
    with ExitStack() as stack:
        _patches(stack, ttk)
        panel = cls(_parent(), StandIn())
    panel.post_ui = lambda callback: callback()
    panel._set_connection_indicator = mock.Mock()
    panel._redraw_ppms_transport_plot = lambda: None
    panel.thread_log = mock.Mock()
    for key in app.PPMS_SR830_KEYS:
        panel.ppms_instrument_controllers[key] = FakeController(app.PPMS_SR830_LABELS[key])
    return panel, ttk


def build_ppms_panel():
    return _build(app.PPMSPanel)


def build_rte_panel():
    return _build(app.RTEPanel)


class FakeSR830:
    """Answers the PPMS read-backs from the commands it was sent.

    keeps_time_constant: the OFLT code it reports whatever it was sent.
    answers: replies to whole commands such as "FREQ?"; hooks: a function
    run when that command is queried, before the reply."""

    def __init__(self, keeps_time_constant=None):
        self.writes, self.queries = [], []
        self.state = {"*ESR": 0, "FMOD": 0, "RSLP": 0, "HARM": 1, "ISRC": 0, "IGND": 0,
                      "ICPL": 0, "ILIN": 0, "SYNC": 0, "SENS": 13, "OFLT": 8, "OFSL": 0,
                      "RMOD": 0, "PHAS": 0}
        self.keeps_time_constant = keeps_time_constant
        self.answers, self.hooks = {"FREQ?": "317.3", "LIAS?": "0"}, {}

    def write(self, command):
        self.writes.append(command)
        name, _, value = command.partition(" ")
        if name in self.state and value and "," not in value:
            self.state[name] = float(value)

    def query(self, command):
        self.queries.append(command)
        hook = self.hooks.pop(command, None)
        if hook is not None:
            hook()
        if command in self.answers:
            return self.answers[command]
        name = command.rstrip("?")
        if name == "OFLT" and self.keeps_time_constant is not None:
            return str(self.keeps_time_constant)
        return f"{self.state[name]:g}"

    def clear(self):
        pass


class FakeController:
    """A PPMS VISA slot holding a FakeSR830 once connected."""

    def __init__(self, label, keeps_time_constant=None):
        self.label, self.lock = label, threading.RLock()
        self.instrument, self.resource_name = None, ""
        self.keeps_time_constant = keeps_time_constant
        self.disconnects = 0

    @property
    def connected(self):
        return self.instrument is not None

    def connect(self, resource):
        self.resource_name = resource
        self.instrument = FakeSR830(self.keeps_time_constant)
        return "Stanford_Research_Systems,SR830"

    def disconnect(self):
        self.disconnects += 1
        self.instrument = None


class DeferredExecutor:
    """Holds each job until run() is called, as the PPMS worker would."""

    def __init__(self):
        self.jobs = []

    def submit(self, fn, *args):
        future = Future()
        self.jobs.append((fn, args, future))
        return future

    def run(self):
        while self.jobs:
            fn, args, future = self.jobs.pop(0)
            try:
                future.set_result(fn(*args))
            except BaseException as error:
                future.set_exception(error)


def connect_setup(time_constant_code, harmonic=1):
    """Connect's SR830 writes, in the order used before 2026-10-14, with the
    chosen time constant; each is followed by a *ESR? check.  The display
    is X and Y since 2026-11-15 (user; it was R and theta)."""
    return ["*CLS", "FMOD 0", "RSLP 1", f"HARM {harmonic}", "ISRC 1", "IGND 0", "ICPL 0",
            "ILIN 0", "SYNC 0", "SENS 9", f"OFLT {time_constant_code}", "OFSL 1", "RMOD 1",
            "PHAS 0", "DDEF 1,0,0", "DDEF 2,0,0"]


class NoWindows(unittest.TestCase):
    def setUp(self):
        self.error = mock.Mock()
        unexpected = mock.Mock(side_effect=AssertionError("an unexpected dialog opened"))
        patches = [
            mock.patch("tkinter.Tk", side_effect=AssertionError("a test tried to open a Tk window")),
            mock.patch.object(tkinter.messagebox, "showerror", self.error),
            mock.patch.object(app.time, "sleep"),  # the 30 ms after each SR830 write
        ]
        for name in ("showwarning", "showinfo", "askyesno", "askokcancel", "askyesnocancel",
                     "askquestion", "askretrycancel"):
            patches.append(mock.patch.object(tkinter.messagebox, name, unexpected))
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def texts(ttk, kind=None):
        return [w.options.get("text") for w in ttk.made
                if (kind is None or w.kind == kind) and "text" in w.options]


class PageTests(NoWindows):
    pass

class ConnectTests(NoWindows):
    def connect(self, panel, key="830_a", label=None, keeps=None):
        if label is not None:
            panel.ppms_sr830_time_constant_var.set(label)
        panel.ppms_instrument_controllers[key].keeps_time_constant = keeps
        panel.connect_ppms_device(key)
        return panel.ppms_instrument_controllers[key]

class ChangeTests(NoWindows):
    def connected_panel(self, keys=("830_a", "830_c")):
        panel, ttk = build_ppms_panel()
        for key in keys:
            panel.connect_ppms_device(key)
            panel.ppms_instrument_controllers[key].instrument.writes.clear()
            panel.ppms_instrument_controllers[key].instrument.queries.clear()
        return panel

    def choose(self, panel, label):
        panel.ppms_sr830_time_constant_var.set(label)
        panel._ppms_apply_sr830_time_constant()

class CsvTests(NoWindows):
    def run_point(self, codes):
        """One point of the real PPMS scan worker, with SR830-1 and SR830-3.
        The stop event moves a clock instead of waiting: the point waits
        1 time constant of the slower SR830 first (user, 2026-10-14)."""
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.closing = False
        obj.ppms_field_scan_stop_event = self.event = ClockEvent(Clock())
        obj.ppms_scan_context = {}
        obj.ppms_last_readback = None
        obj.ppms_field_scan_rows = []
        obj.ppms_field_scan_total = 1
        obj.ppms_field_scan_started_at = time.monotonic()
        obj.ppms_environment_controller = types.SimpleNamespace(backend="MultiPyVu")
        obj.ppms_instrument_controllers = {
            "830_a": types.SimpleNamespace(resource_name="GPIB0::8::INSTR"),
            "830_c": types.SimpleNamespace(resource_name="GPIB0::10::INSTR")}
        obj.ppms_sr830_time_constant_codes = codes
        obj._read_ppms_live = lambda: dict(field_oe=0.0, field_status="Persistent",
                                           temperature_k=300.0, temperature_status="Stable")
        obj._configure_ppms_transport_scan = lambda settings: None
        sample = {}
        for address in (8, 10):
            sample.update({f"sr830_{address}_x_v": 1e-6, f"sr830_{address}_frequency_hz": 317.3,
                           f"sr830_{address}_reference_valid": True, f"sr830_{address}_sensitivity_index": 9})
        obj._acquire_ppms_first_point = lambda *args: (dict(sample), 1)
        obj._average_ppms_transport_sample = lambda *args: dict(sample)
        obj.post_ui = lambda callback: None
        obj.thread_log = lambda text: None
        settings = dict(scan_mode="Temperature", active_lockins=("830_a", "830_c"),
                        harmonic_a=1, harmonic_b=2, harmonic_c=3, acquisition_s=1.0,
                        frequency_hz=317.3, current_rms_ma=1.0, compliance_v=50.0)
        with tempfile.TemporaryDirectory() as folder:
            obj.ppms_live_csv_path = Path(folder) / "scan.csv"
            obj.ppms_live_csv_fields = None
            app.CombinedControlApp._ppms_field_scan_worker(obj, [(1, 1, 1, 300.0)], 100.0, 0.0, 1, settings)
            with obj.ppms_live_csv_path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                return next(reader), next(reader)

class Clock:
    """time.monotonic for a test: it moves only when the scan waits."""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class ClockEvent:
    """The scan's stop event: never set; each wait moves the clock on."""

    def __init__(self, clock):
        self.clock, self.waits = clock, []

    def is_set(self):
        return False

    def wait(self, seconds):
        self.waits.append(seconds)
        self.clock.now += seconds
        return False


class RangingSR830:
    """An SR830 in a scan with time-constant code ``code``.  Its 0.6 mV
    signal overloads every range below ``needs`` (SENS 17 is 1 mV)."""

    def __init__(self, code, needs=17, sens=9):
        self.code, self.needs, self.sens = code, needs, sens
        self.writes = []

    def write(self, command):
        self.writes.append(command)
        name, _, value = command.partition(" ")
        if name == "SENS":
            self.sens = int(value)

    def query(self, command):
        replies = {"SNAP? 1,2,3,4,9": "6e-4,0,6e-4,0,317.3",
                   "LIAS?": "1" if self.sens < self.needs else "0",
                   "SENS?": str(self.sens), "OFLT?": str(self.code)}
        return replies[command]

    def clear(self):
        pass


class Fake6221:
    """The 6221 as a scan reads it: output on, 1 mA RMS, no compliance."""

    def __init__(self, compliance_v=10.0, frequency_hz=317.3, peak_a=math.sqrt(2) * 1e-3):
        self.writes = []
        self.replies = {"OUTP?": "1", "STAT:MEAS:COND?": "0", "SOUR:WAVE:AMPL?": f"{peak_a:.12e}",
                        "CURR:COMP?": f"{compliance_v:g}", "SOUR:WAVE:FREQ?": f"{frequency_hz:g}"}

    def write(self, command):
        self.writes.append(command)

    def query(self, command):
        return self.replies[command]

    def clear(self):
        pass


def slot(label, instrument, resource=""):
    return types.SimpleNamespace(label=label, instrument=instrument, resource_name=resource,
                                 lock=threading.RLock(), connected=True,
                                 safe_output_off=lambda: None)


class RangeLimitTests(NoWindows):
    """A scan point's autorange limit was a fixed 180 s, set when every
    range step waited 5 x 1 s; it now grows with the step wait."""

    def averaging(self, settles):
        """The real averaging loop on scripted readings (each a range step
        with that wait, then settled ones) and a clock moved by the waits."""
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.closing = False
        clock = Clock()
        obj.ppms_field_scan_stop_event = ClockEvent(clock)
        settled = {"sr830_8_x_v": 1e-6, "sr830_8_y_v": 0.0, "sr830_8_frequency_hz": 317.3,
                   "sr830_8_reference_valid": True, "sr830_8_overload": False}
        readings = iter([{"range_settle_s": s} for s in settles])
        obj._read_ppms_transport_sample = lambda *_args: next(readings, settled)
        return obj, clock

    def run_steps(self, settle, steps):
        obj, clock = self.averaging([settle] * steps)
        with mock.patch.object(app.time, "monotonic", clock):
            obj._average_ppms_transport_sample(317.3, ("830_a",), 1.0)
        return obj

    def test_at_1_s_the_limit_is_still_180_s(self):
        """5 s per step: 36 steps fit, the 37th would end past 180 s."""
        obj = self.run_steps(5.0, 36)
        self.assertEqual(obj.ppms_field_scan_stop_event.waits.count(5.0), 36)
        with self.assertRaisesRegex(app.PPMSLockinRangeError, r"within 180 s; current point not saved"):
            self.run_steps(5.0, 37)

    def test_shorter_time_constants_keep_180_s(self):
        """100 ms: 0.5 s per step, so 360 fit in 180 s, and no more."""
        self.run_steps(0.5, 360)
        with self.assertRaisesRegex(app.PPMSLockinRangeError, r"within 180 s"):
            self.run_steps(0.5, 361)

    def test_a_long_time_constant_keeps_as_many_steps(self):
        """10 s: 50 s per step.  180 s held three; now 36 fit in 1800 s."""
        for settle, limit in ((15.0, "540"), (50.0, "1800")):
            with self.subTest(settle=settle):
                obj = self.run_steps(settle, 36)
                self.assertEqual(obj.ppms_field_scan_stop_event.waits.count(settle), 36)
                with self.assertRaisesRegex(app.PPMSLockinRangeError, rf"within {limit} s"):
                    self.run_steps(settle, 37)

class IdlePollTests(NoWindows):
    """An 'SR830 TC' change makes idle autorange wait 5 new time constants;
    a poll running beside it on another PPMS worker must not cut that short."""

    class HandOverLock:
        """An RLock whose next acquisition first runs ``pending``: another
        worker held the lock, and this one waited for it to finish."""

        def __init__(self):
            self._lock, self.pending = threading.RLock(), None

        def __enter__(self):
            pending, self.pending = self.pending, None
            if pending is not None:
                pending()
            self._lock.acquire()
            return self

        def __exit__(self, *_exc):
            self._lock.release()

    def polling_panel(self):
        panel, _ttk = build_ppms_panel()
        panel.connect_ppms_device("830_a")
        controller = panel.ppms_instrument_controllers["830_a"]
        controller.lock = self.HandOverLock()
        sr830 = controller.instrument
        # 0.5 % of the 2 uV range: a low reading (under 1 % since 2026-11-16;
        # it was 1e-07, 5 %, while the rule was 10 %).
        sr830.answers["OUTP? 3"] = "1e-08"
        sr830.writes.clear()
        sr830.queries.clear()
        panel.ppms_environment_controller = types.SimpleNamespace(backend="fake", read_environment=lambda: {})
        panel._read_ppms_current_display = lambda: "ON / sine setpoint 1 mA RMS / 317.3 Hz"
        panel._read_ppms_cryogen_display = lambda: {}
        panel.ppms_idle_autorange_enabled, panel.ppms_6221_zero_output = True, False
        panel.ppms_field_scan_running = False
        state = types.SimpleNamespace(low_range_count=2, range_cooldown=0, low_range_peak=0.0,
                                      sensitivity_index=13, clear_latch_pending=False)
        panel.ppms_sr830_range_states = {"830_a": state}
        panel.ppms_idle_range_ready_at = {}
        return panel, controller, sr830, state

    def change_to_10_s(self, panel):
        return lambda: panel._ppms_set_sr830_time_constant("830_a", 12)

class ScanStartTimeConstantTests(NoWindows):
    """Each scan start reads every active SR830's OFLT? for the CSV column,
    so a front-panel change since Connect is recorded as it is."""

    def configure(self, panel, front_panel_code=None):
        sr830 = panel.ppms_instrument_controllers["830_a"].instrument
        if front_panel_code is not None:
            sr830.state["OFLT"] = front_panel_code
        sr830.writes.clear()
        sr830.queries.clear()
        panel.thread_log.reset_mock()
        source = Fake6221()
        panel.ppms_instrument_controllers["6221"] = slot("Keithley 6221", source, "GPIB0::12::INSTR")
        panel._ppms_write_6221_checked = source.write
        panel._initialize_ppms_6221 = lambda: None
        # The page's own SR830-1 harmonic, which Connect set (SHHV's is 2
        # since the user's figure of 2026-11-16), so the start writes no HARM.
        own = str(panel._ppms_harmonic_var("830_a").get())
        panel._configure_ppms_transport_scan(dict(
            active_lockins=("830_a",), current_rms_ma=1.0, frequency_hz=317.3, compliance_v=10.0,
            harmonic_a=int(own) if own.isdigit() else 1, harmonic_b=2, harmonic_c=3))
        return sr830

    def connected(self, build=build_ppms_panel):
        panel, _ttk = build()
        panel.ppms_resource_vars["830_a"].set("GPIB0::8::INSTR")
        panel.connect_ppms_device("830_a")
        return panel

class StartSettleTests(NoWindows):
    """The scan-start confirmation used to note a Settle s shorter than 5
    time constants of a 3 s or 10 s choice, and the scan itself was not
    changed.  Since the user's rule of 2026-10-14 every reading waits at
    least 1 time constant of the slowest lock-in instead (7 at first that
    day), and the confirmation shows that wait (more in
    test_lockin_settle_rte_ppms.py)."""

    def settle(self, label, settle_s, lockins=("830_a",), build=build_ppms_panel):
        panel, _ttk = build()
        if label is not None:
            panel.ppms_sr830_time_constant_var.set(label)
        return panel._ppms_lockin_settle(settle_s, lockins, False)

class WheelTests(NoWindows):
    pass


if __name__ == "__main__":
    unittest.main()
