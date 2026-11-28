"""Non-local page: the fixes from the whole-module review (2026-10-08).

No Tk and no instrument: stand-in controllers and variables record what the
page asks of them.
"""
import queue
import threading
import time
import unittest
from concurrent.futures import Future
from unittest import mock

from test_nonlocal_keithley import FakeSourceMeter, Var, bare_app, connected_controller
from test_ppms_motor_debug import app


class Executor:
    """Runs each job at once, in order, as the page's single worker would."""

    def __init__(self):
        self.jobs = []

    def submit(self, function, *args):
        self.jobs.append(function)
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as error:
            future.set_exception(error)
        return future


def page():
    a = bare_app()
    a.root, a.closing, a.nonlocal_vi_closed = None, True, False
    a.nonlocal_vi_running = a.nonlocal_vi_busy = False
    a.nonlocal_keithley_task = None
    a.nonlocal_vi_executor = Executor()
    a.post_ui = lambda callback: callback()
    a.nonlocal_vi_stop_event = threading.Event()
    a.nonlocal_vi_interlock = app.NonLocalVIInterlock()
    a.nonlocal_vi_status_var, a.nonlocal_vi_output_var = Var(), Var()
    a.nonlocal_iv6221_source_var = Var("6221 ON: 0.1 mA RMS / 17.3 Hz")
    a._update_nonlocal_vi_controls = mock.Mock()
    return a


class StopAndOffTests(unittest.TestCase):
    def setUp(self):
        self.a = a = page()
        a.nonlocal_vi_ac_controller = mock.Mock(source_connected=True, any_connected=True)
        a.nonlocal_vi_2410_controller = mock.Mock(connected=True, model="2400")

class GateVIFinishTests(unittest.TestCase):
    """Since 2026-10-18 (user) the scan's end zeroes both outputs on the
    worker; the finish reports each beside the scan's own error."""

    def finish(self, error, results):
        a = page()
        a.nonlocal_vi_2410_controller = mock.Mock(model="2400", connected=True)
        a.nonlocal_vi_eta_var = Var()
        a.nonlocal_vi_run_directory = None
        a.nonlocal_scan_outputs = results
        a._set_mfli_lock_state = mock.Mock()
        for name in ("_redraw_nonlocal_vi_plots", "_update_k6221_controls", "_update_keithley_controls"):
            setattr(a, name, mock.Mock())
        a._finish_nonlocal_vi_scan(error)
        return a

class KeithleyTaskTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(app.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.a = a = page()
        self.meter = FakeSourceMeter()
        a.nonlocal_vi_2410_controller = connected_controller(self.meter)
        a.nonlocal_vi_ac_controller = mock.Mock(source_connected=False)
        a.nonlocal_keithley_stop_event = threading.Event()
        a.nonlocal_keithley_output_off = False
        a.nonlocal_keithley_untouched = True

class ManualKeithleyTests(unittest.TestCase):
    """User, 2026-10-09: Set (a voltage left on) and Apply pulse in
    "2400-IV settings"."""

    def setUp(self):
        patcher = mock.patch.object(app.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.a = a = page()
        self.meter = FakeSourceMeter()
        a.nonlocal_vi_2410_controller = connected_controller(self.meter)
        a.nonlocal_vi_2410_controller.model = "2400"
        a.nonlocal_vi_ac_controller = mock.Mock(source_connected=True)
        a.nonlocal_keithley_stop_event = threading.Event()
        a.nonlocal_iv_safety_var = Var(True)
        a.nonlocal_iv_limit_var = Var("0.001")
        a.nonlocal_iv_set_voltage_var = Var("50")
        a.nonlocal_iv_pulse_voltage_var, a.nonlocal_iv_pulse_width_var = Var("-30"), Var("0.01")
        a.nonlocal_iv_keithley_var = Var("Keithley 2400: OFF")
        a.nonlocal_iv6221_source_var = Var("6221 ON")
        a._nonlocal_keithley_free = lambda what: True
        self.questions = []

    def run_action(self, action, answer=True):
        def ask(title, text, **options):
            self.questions.append(text)
            return answer
        with mock.patch.object(app.messagebox, "askyesno", ask), \
                mock.patch.object(app.messagebox, "showerror"), \
                mock.patch.object(app.messagebox, "showwarning") as warning:
            action()
        return warning

class PulseTests(unittest.TestCase):
    pass

class ZurichControllerTests(unittest.TestCase):
    def controller(self):
        controller = app.NonLocalACController(lambda _m: None)
        return controller

class SR830Tests(unittest.TestCase):
    class Lockin:
        def __init__(self, esr=("0",)):
            self.commands, self.esr, self.lias = [], list(esr), []

        def write(self, command):
            self.commands.append(command)

        def query(self, command):
            if command == "*ESR?":
                return self.esr.pop(0) if self.esr else "0"
            if command == "SENS?":
                return "10"
            if command == "LIAS?":
                self.lias.append(command)
                return "1" if len(self.lias) == 1 else "0"
            if command.startswith("SNAP?"):
                return "1e-6,0,1e-6,0,17.3"
            raise AssertionError(command)

        def clear(self):
            self.commands.append("<clear>")

    def controller(self, lockin):
        controller = app.NonLocalACController(lambda _m: None)
        controller.lockins = {"8": lockin}
        controller.sensitivity_indices = {"8": 9}
        controller.low_range_counts = {"8": 0}
        controller.range_cooldowns = {"8": 0}
        return controller

class BridgeTests(unittest.TestCase):
    def test_a_late_reply_is_not_taken_for_the_next_request(self):
        bridge = app.LegacyMFLIBridge.__new__(app.LegacyMFLIBridge)
        bridge.responses = queue.Queue()
        bridge.diagnostics = []
        bridge.process = None
        bridge.responses.put({"ok": True, "id": 4, "autorange": {}})   # late, timed out earlier
        bridge.responses.put({"ok": True, "id": 5, "sample": {"x": 1}})
        reply = bridge._receive(1.0, 5)
        self.assertEqual(reply["sample"], {"x": 1})
        self.assertTrue(any("request 4" in line for line in bridge.diagnostics))


class GateVIPlotTests(unittest.TestCase):
    """User, 2026-10-09: X, Y and θ against time first, a row per harmonic
    order, then the Keithley's resistance and the lock-in voltage against
    the pulse voltage, a plot per order."""

    def redraw(self, harmonics, time_rows, summary_rows):
        a = bare_app()
        a.nonlocal_vi_data_lock = threading.Lock()
        a.nonlocal_vi_time_rows = time_rows
        a.nonlocal_vi_summary_rows = summary_rows
        a.nonlocal_vi_pulse_rows = [(0.5, 4.0)]
        # (pulse V, |R|, elapsed, stage): the check before the first pulse first.
        a.nonlocal_vi_resistance_rows = [(4.0, 4e8, 0.1, "initial_gate"), (4.0, 1e9, 2.0, "post_point")]
        a.nonlocal_vi_current_rows = [(1.0, 1.0)]
        a.nonlocal_vi_ac_controller = mock.Mock(connected_lockin_keys=("9",), mfli_connected=True,
                                                nanovoltmeter_connected=True)
        a.nonlocal_vi_2410_controller = mock.Mock(model="2400")
        a._selected_nonlocal_vi_lockin_keys = lambda: ("9",)
        a.nonlocal_vi_use_mfli_var, a.nonlocal_vi_use_2182_var = Var(True), Var(True)
        a.nonlocal_vi_lockin_harmonic_vars = {"8": Var("1"), "9": Var(harmonics["9"])}
        a.nonlocal_vi_mfli_harmonic_var = Var(harmonics["mfli"])
        keys = ["resistance"] + [(order, channel) for order in (1, 2, 3)
                                          for channel in ("x", "y", "theta")]
        keys += [("summary", order) for order in (1, 2, 3)]
        a.nonlocal_vi_plot_canvases = {key: key for key in keys}
        a.nonlocal_vi_plot_frames = {key: mock.Mock() for key in keys}
        a._layout_nonlocal_vi_plots = mock.Mock()
        a._draw_nonlocal_series = mock.Mock()
        a._redraw_nonlocal_vi_plots()
        drawn = {call.args[0]: call.args[1] for call in a._draw_nonlocal_series.call_args_list}
        return a, drawn

class ZurichRowTests(unittest.TestCase):
    pass

if __name__ == "__main__":
    unittest.main()
