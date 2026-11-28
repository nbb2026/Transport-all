"""Non-local page: |R| vs time (moved from MOKE-24) and the I-V sweep.

Both run on the Gate-VI Keithley (NonLocalVI2410Controller).  No Tk and no
instrument: a stand-in canvas records the drawing, and a fake SourceMeter
answers the SCPI commands.
"""
import csv
import threading
from pathlib import Path
import unittest
from concurrent.futures import Future
from unittest import mock

from test_ppms_motor_debug import app


class Canvas:
    def __init__(self, width=1900, height=260):
        self.items = []
        self.size = (width, height)

    def delete(self, *args):
        self.items.clear()

    def winfo_width(self):
        return self.size[0]

    def winfo_height(self):
        return self.size[1]

    def create_line(self, *args, **kwargs):
        self.items.append(("line", len(args), kwargs.get("fill")))

    def create_text(self, *args, **kwargs):
        self.items.append(("text", 0, kwargs.get("text")))

    def create_rectangle(self, *args, **kwargs):
        self.items.append(("rectangle", 0, kwargs.get("fill")))

    def create_oval(self, *args, **kwargs):
        self.items.append(("oval", 0, None))

    def texts(self):
        return [text for kind, _, text in self.items if kind == "text"]


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def bare_app():
    app_ = app.CombinedControlApp.__new__(app.CombinedControlApp)
    app_._canvas_is_visible = lambda canvas: True
    app_._draw_plot_grid = lambda *args: None
    app_.ui_font_family, app_.ui_font_size, app_.ui_small_font_size = "Segoe UI", 10, 9
    return app_


class FakeSourceMeter:
    """A 2410/2400 on the pulse page: a 1 GΩ sample in voltage mode, so the
    current is V / 1 GΩ (nA), clamped at the current limit."""

    def __init__(self, resistance_ohm=1e9):
        self.commands = []
        self.resistance_ohm = resistance_ohm
        self.voltage = 0.0
        self.current_source = 0.0
        self.limit = 1e-3
        self.ovp = 210.0
        self.range = 21.0
        self.output = 0
        self.mode = "VOLT"

    def write(self, command):
        self.commands.append(command)
        upper = command.upper()
        value = command.rsplit(" ", 1)[-1]
        if upper == "*RST":
            self.output, self.voltage, self.ovp, self.mode, self.range = 0, 0.0, 210.0, "VOLT", 21.0
        elif upper.startswith(":SOUR:FUNC "):
            self.mode = value.upper()
        elif upper.startswith(":SOUR:VOLT:PROT "):
            self.ovp = float(value)
        elif upper.startswith(":SOUR:VOLT:RANG "):
            # The range's full scale, as a 2400 reads it back (21, 210, 1100 V).
            self.range = float(value) * 1.05 if float(value) < 1000 else 1100.0
        elif upper.startswith(":SOUR:VOLT "):
            self.voltage = float(value)
        elif upper.startswith(":SOUR:CURR "):
            self.current_source = float(value)
        elif upper.startswith(":SENS:CURR:PROT "):
            self.limit = float(value)
        elif upper == ":OUTP ON":
            self.output = 1
        elif upper == ":OUTP OFF":
            self.output = 0

    def query(self, command):
        upper = command.upper()
        if upper == "SYST:ERR?":
            return '0,"No error"'
        if upper == ":OUTP?":
            return str(self.output)
        if upper == ":SOUR:VOLT:PROT?":
            return str(self.ovp)
        if upper == ":SOUR:VOLT:RANG?":
            return str(self.range)
        if upper == ":SENS:CURR:PROT?":
            return str(self.limit)
        if upper == ":READ?":
            if self.output == 0:
                # A 2400/2410 refuses a reading with the output off.
                raise RuntimeError('-803,"Not permitted with OUTPUT off"')
            if self.mode == "CURR":
                if self.resistance_ohm == float("inf"):  # open: at the 5 V limit, no current
                    return "5.000000e+00,0.000000e+00"
                return f"{self.current_source * self.resistance_ohm:.6e},{self.current_source:.6e}"
            current = self.voltage / self.resistance_ohm
            current = max(-self.limit, min(self.limit, current))
            return f"{self.voltage:.6e},{current:.6e}"
        raise AssertionError(f"unexpected query: {command}")

    def close(self):
        pass


def connected_controller(meter):
    controller = app.NonLocalVI2410Controller(lambda _message: None)
    controller.instrument = meter
    controller.resource_name = "GPIB0::24::INSTR"
    controller.identity = "KEITHLEY INSTRUMENTS INC.,MODEL 2400,1,C30"
    controller.source_mode = "VOLT"
    return controller


# ------------------------------------------------------------- |R| vs time
class ResistancePlotTests(unittest.TestCase):
    def draw(self, rows):
        app_ = bare_app()
        app_.nonlocal_resistance_canvas = Canvas()
        app_.nonlocal_resistance_rows = rows
        with mock.patch.object(app, "np", None):
            app_._redraw_nonlocal_resistance_plot()
        return app_.nonlocal_resistance_canvas.items

class FinishTests(unittest.TestCase):
    """The finish reports the end's zeroing, done on the worker (user,
    2026-10-18: every scan ends with both outputs zeroed)."""

    def finished(self, kind, error, *, results=None, redraw_error=None):
        app_ = bare_app()
        app_.closing = True  # no dialogs
        app_.nonlocal_keithley_task = kind
        app_.nonlocal_vi_2410_controller = app.NonLocalVI2410Controller(lambda _m: None)
        app_.nonlocal_vi_output_var, app_.nonlocal_vi_status_var = Var(), Var()
        app_.nonlocal_iv_eta_var, app_.nonlocal_iv6221_source_var = Var(), Var()
        app_.nonlocal_iv_rows, app_.nonlocal_iv_total_points = [(1, 0, 0, 0, 0, False)], 49
        app_.nonlocal_run_points = 1
        app_.nonlocal_scan_outputs = (results if results is not None
                                      else {"6221": "zeroed", "Keithley 2410": "zeroed"})
        redraw = mock.Mock(side_effect=redraw_error)
        app_._redraw_nonlocal_resistance_plot = app_._redraw_nonlocal_iv_plot = redraw
        app_._update_nonlocal_vi_controls = mock.Mock()
        future = Future()
        future.set_exception(error)
        finish = (app_._finish_nonlocal_resistance if kind == "resistance"
                  else app_._finish_nonlocal_iv_sweep)
        if redraw_error is None:
            finish(future)
        else:
            with self.assertRaises(type(redraw_error)):
                finish(future)
        return app_

# ----------------------------------------------------------------- I-V sweep
class SweepValuesTests(unittest.TestCase):
    pass

class SweepPlotTests(unittest.TestCase):
    def draw(self, rows, sample="1µm Pt-Pt", size=(900, 600)):
        app_ = bare_app()
        app_.nonlocal_iv_canvas = Canvas(*size)
        app_.nonlocal_iv_rows = rows
        app_.nonlocal_iv_settings = {"start_v": -6.0, "end_v": 6.0, "sample": sample}
        with mock.patch.object(app, "np", None):
            app_._redraw_nonlocal_iv_plot()
        return app_.nonlocal_iv_canvas

class SweepControllerTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(app.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.meter = FakeSourceMeter()
        self.controller = connected_controller(self.meter)

    def start(self, model, limit_a, max_abs_v):
        meter = FakeSourceMeter()
        controller = connected_controller(meter)
        controller.model = model
        controller.start_iv_sweep(limit_a, max_abs_v)
        return meter, controller

    def test_an_output_found_on_is_drained_before_the_reset(self):
        meter = FakeSourceMeter()
        controller = connected_controller(meter)
        meter.output, meter.voltage = 1, 150.0   # e.g. left on before a reconnect
        with mock.patch.object(app.time, "sleep", lambda s: meter.commands.append(f"sleep {s:g}")):
            controller.setup_voltage_mode(1e-3)
        self.assertEqual(meter.commands[:3], [":SOUR:VOLT 0", "sleep 1", "sleep 0.2"])
        self.assertLess(meter.commands.index(":OUTP OFF"), meter.commands.index("*RST"))

class Source:
    """The Gate-VI 6221: its output is switched off before the Keithley sources."""

    def __init__(self, log):
        self.log = log
        self.source_connected = True

    def output_off(self):
        self.log.append("6221 off")

    def confirm_output_off(self, context):
        self.log.append("6221 confirmed off")


class WorkerTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(app.time, "sleep")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.meter = FakeSourceMeter()
        self.app = bare_app()
        self.log = []
        self.app.nonlocal_vi_2410_controller = connected_controller(self.meter)
        self.app.nonlocal_vi_ac_controller = Source(self.log)
        self.app.nonlocal_vi_interlock = app.NonLocalVIInterlock()
        self.app.nonlocal_keithley_stop_event = threading.Event()
        self.app.nonlocal_keithley_output_off = False
        self.posted = []
        self.app.post_ui = self.posted.append
        self.app.nonlocal_vi_status_var = Var()
        self.app.nonlocal_iv6221_source_var = Var()

    def settings(self, voltages=(-1.0, 0.0, 1.0)):
        return {"voltages": list(voltages), "current_limit_a": 1e-3, "settle_s": 0.0}

    def recorder(self, page="NL_2400IV"):
        # The run folder's recorder, as begin_scan_run makes it (2026-10-18).
        import tempfile
        return app.ScanRunRecorder(Path(tempfile.mkdtemp()), page, "run", {})

class SixTwoTwoOneOffTests(WorkerTests):
    """|R| and 2400-IV switch the 6221 off first (review of 2026-10-08)."""

    pass

class OpenCircuitTests(unittest.TestCase):
    pass


class StartQuestionTests(unittest.TestCase):
    def setUp(self):
        self.app = a = bare_app()
        a.root = None
        a.nonlocal_keithley_task = None
        a._nonlocal_keithley_free = lambda what: True
        a.nonlocal_iv_safety_var = Var(True)
        a.active_file_exports = set()
        a.nonlocal_vi_2410_controller = app.NonLocalVI2410Controller(lambda _m: None)
        a.nonlocal_iv_start_var, a.nonlocal_iv_end_var = Var("-6"), Var("6")
        a.nonlocal_iv_step_var, a.nonlocal_iv_settle_var = Var("0.25"), Var("0.5")
        a.nonlocal_iv_limit_var = Var("1e-6")
        a._begin_nonlocal_keithley_task = mock.Mock()

    def ask(self, answer, folder="", name=""):
        # The Yes/No, then begin_scan_run's folder and optional file name
        # (user, 2026-10-18).
        with mock.patch.object(app.messagebox, "askyesno", return_value=answer) as question, \
                mock.patch.object(app.filedialog, "askdirectory", return_value=folder) as folders, \
                mock.patch.object(app.simpledialog, "askstring", return_value=name):
            self.app.start_nonlocal_iv_sweep()
        self.folders = folders
        return question.call_args[0][1] if question.called else None

if __name__ == "__main__":
    unittest.main()
