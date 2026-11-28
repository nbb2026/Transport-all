"""RT-E Angle scan, end to end (user, 2026-10-17: "now move the stage
controllers to the RT-E settings and make the angle scan function
workable"; asked what fails: "Not tried yet; make it ready").

The real RTEPanel, built on stand-in widgets, runs a whole Angle scan
through its own Start (requirements, the Yes/No, the folder and file name,
the stage check), its scan workers and its finish, on a real single-worker
executor named rte-control, as on the lab PC.  The instruments are fakes
that log every call with the thread it came from: the KEPCO 4886 and the
LS475 at their controllers' methods, the 6221 and the lock-ins at the
page's acquisition methods (their instrument paths are the PPMS page's,
shared with the Field and Current scans), and the Newmark NSC-A1 is the
program's real controller on test_rte_angle_scan's fake PerformaxCom.dll
(the standalone script's simulated NSC-A1, on a virtual clock).  The Tk
thread is the test's: the post_ui queue and root.after callbacks run when
the test pumps them.  No real DLL is ever loaded, no window opens and
every dialog is answered here."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import csv
import ctypes
import datetime
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import Mock, patch

import test_rte_panel as rte_tests
from test_ppms_motor_debug import app
from test_ppms_two_panels import ImmediateExecutor, Var
from test_rte_angle_scan import Clock, EndsShort, Recorder, RecordingDLL, Sim, script

_guards = []
# The end of every SHHV scan (user, 2026-10-18): the 6221 off and read back,
# then the KEPCO's Zero / OFF.
ZEROED = [("6221", "off"), ("6221", "OUTP?"), ("kepco", "force_off")]


def setUpModule():
    def refuse(what):
        def refused(*_args, **_kwargs):
            raise AssertionError(f"a test reached {what}")
        return refused
    for target, name, replacement in ((ctypes, "WinDLL", refuse("ctypes.WinDLL (a real DLL)")),
                                      (os, "add_dll_directory", refuse("os.add_dll_directory")),
                                      (app, "newmark_load_performax", refuse("the real Newmark DLL loader")),
                                      (app.tk, "Tk", refuse("tkinter.Tk (a window)"))):
        guard = patch.object(target, name, replacement, create=True)
        guard.start()
        _guards.append(guard)


def tearDownModule():
    while _guards:
        _guards.pop().stop()


class Root:
    """root.after for the page: callbacks wait for the test's Tk loop; the
    idle poll's 1 s timer is kept but only run when a test asks."""

    def __init__(self):
        self.pending = []

    def after(self, delay, callback):
        self.pending.append((delay, callback))
        return f"after#{len(self.pending)}"

    def after_cancel(self, _token):
        pass


class Kepco:
    connected, label = True, "KEPCO 4886"

    def __init__(self, log):
        self.log = log
        self.output_owned, self.cached_current_a = False, 0.0
        # As the real controller's (the field setting takes it, 2026-11-17).
        self.lock, self.active_mode = threading.RLock(), ""

    def set_output(self, mode, target, limit):
        self.log.append(("kepco", "set_output", mode, target, limit, threading.get_ident()))
        self.output_owned, self.cached_current_a, self.active_mode = True, target, mode

    def set_scan_current(self, value):
        self.log.append(("kepco", "set_scan_current", value, threading.get_ident()))
        self.cached_current_a = value       # as the controller's (Angle+Field rows, 2026-10-18)

    def safe_output_off(self):
        self.log.append(("kepco", "off", threading.get_ident()))
        self.output_owned = False

    def force_output_off(self):
        self.log.append(("kepco", "force_off", threading.get_ident()))
        self.output_owned, self.cached_current_a = False, 0.0
        return {}

    def disconnect(self):
        pass


class Gauss:
    connected, label = True, "Lake Shore 475"

    def __init__(self, log, field=123.0):
        self.log, self.field = log, field

    def read_field(self):
        self.log.append(("gauss", "read", threading.get_ident()))
        return {"field": self.field, "unit": "G"}

    @staticmethod
    def value_in_gauss(reading):
        return float(reading["field"])

    def disconnect(self):
        pass


class FollowingGauss(Gauss):
    """An LS475 that reads 100 G per A of the stand-in KEPCO's current
    (Angle+Field's field setting, 2026-11-17)."""

    def __init__(self, log, kepco):
        super().__init__(log)
        self.kepco = kepco

    def field_g(self):
        return 100.0 * (self.kepco.cached_current_a if self.kepco.output_owned else 0.0)

    def read_field(self):
        # The real reading's unit_code (1 = G), which the field setting's
        # STFMRGauss475Controller.value_in_gauss reads.
        self.log.append(("gauss", "read", threading.get_ident()))
        return {"field": self.field_g(), "unit": "G", "unit_code": 1}


class StuckGauss(FollowingGauss):
    """An LS475 whose field does not answer the current."""

    def field_g(self):
        return 0.0


def kepco_chosen(panel):
    """SHHV starts on the Lake Shore 643 since 2026-10-23 (user); these
    tests drive the KEPCO 4886 path, chosen as the combobox would."""
    panel.rte_magnet_choice_var.set(app.MAGNET_SUPPLY_KEPCO)
    panel._rte_magnet_choice_changed()
    return panel


def build_page(kepco=True):
    """The real RTEPanel constructor on stand-in widgets (as test_rte_angle_scan's)."""
    parent = Mock(closing=False)
    parent.root.after.return_value = "timer"
    Recorder.made = []
    with ExitStack() as stack:
        for name in ("Frame", "LabelFrame", "Label", "Entry", "Button", "Combobox", "Checkbutton", "Progressbar"):
            stack.enter_context(patch.object(app.ttk, name, Recorder))
        stack.enter_context(patch.object(app.tk, "Canvas", Recorder))
        for name in ("StringVar", "IntVar", "BooleanVar"):
            stack.enter_context(patch.object(app.tk, name, Var))
        stack.enter_context(patch.object(app, "ThreadPoolExecutor", ImmediateExecutor))
        stack.enter_context(patch.object(app.CombinedControlApp, "_create_connection_indicator",
                                         lambda _self, parent, key: Recorder(parent, indicator=key)))
        stack.enter_context(patch.object(app.CombinedControlApp, "_set_connection_indicator", Mock()))
        stack.enter_context(patch.object(app.CombinedControlApp, "_draw_nonlocal_series", Mock()))
        panel = app.RTEPanel(parent, rte_tests.Widget())
        return kepco_chosen(panel) if kepco else panel


class EndToEnd(unittest.TestCase):
    def make(self, sim=None, span=("0", "20", "10"), loops="1", round_trip=True, meter="zurich",
             tc_zurich="0.001"):
        """The page, ready for an Angle scan: the safety tick, every
        instrument connected (the stage through its real Connect, on the
        worker), Angle chosen and the range set; ``meter``: "zurich" (SHHV's
        default, the Zurich alone at 1+2 since 2026-10-18) or "sr830" (SR830-1
        alone at 1+2+3, three harmonic passes)."""
        panel = build_page()
        h = types.SimpleNamespace(panel=panel, log=[], logged=[], ui=[], in_drain=False,
                                  folder=tempfile.TemporaryDirectory())
        self.addCleanup(h.folder.cleanup)
        h.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rte-control")
        self.addCleanup(h.executor.shutdown, wait=True)
        h.worker = h.executor.submit(threading.get_ident).result(timeout=30)
        panel.ppms_executor = h.executor
        panel.root = h.root = Root()
        panel.post_ui = h.ui.append
        # The page's log lines, at once; the page's own thread_log still runs,
        # so a running scan's lines are also its run log's notes (2026-10-18).
        guard = patch.object(app.CombinedControlApp, "thread_log", lambda _self, message: h.logged.append(message))
        guard.start()
        self.addCleanup(guard.stop)
        # The plots: what each redraw would draw.
        h.draw = Mock()
        guard = patch.object(app.CombinedControlApp, "_draw_nonlocal_series", h.draw)
        guard.start()
        self.addCleanup(guard.stop)
        # Every dialog the scan can reach.
        h.askyesno = Mock(return_value=True)
        h.showerror = Mock()
        for target, name, value in ((app.messagebox, "askyesno", h.askyesno),
                                    (app.messagebox, "showerror", h.showerror),
                                    (app.filedialog, "askdirectory", Mock(return_value=h.folder.name)),
                                    (app.simpledialog, "askstring", Mock(return_value="angle"))):
            guard = patch.object(target, name, value)
            guard.start()
            self.addCleanup(guard.stop)
        # The instruments.
        panel.rte_controllers["kepco"] = h.kepco = Kepco(h.log)
        panel.rte_controllers["gauss"] = h.gauss = Gauss(h.log)
        h.clock = Clock()
        guard = patch.object(script, "_now", h.clock.now)
        guard.start()
        self.addCleanup(guard.stop)
        h.sim = Sim() if sim is None else sim
        h.dll = RecordingDLL(h.sim)
        stage = app.NewmarkNSCA1Controller(h.logged.append, owner_scope="SHHV",
                                           loader=lambda: (h.dll, "fake PerformaxCom.dll"))
        stage._now, stage._sleep = h.clock.now, h.clock.sleep
        real_move = stage.move_to_deg
        h.move_hooks = {}

        def move(target, stop_event, on_progress=None):
            h.log.append(("stage", "move", float(target), threading.get_ident()))
            hook = h.move_hooks.pop(float(target), None)
            if hook is not None:
                hook()
            state = real_move(target, stop_event, on_progress)
            h.log.append(("stage", "at", state["angle_deg"], threading.get_ident()))
            return state

        stage.move_to_deg = move
        panel.rte_controllers["newmark"] = h.stage = stage
        source = types.SimpleNamespace(connected=True, label="Keithley 6221", resource_name="GPIB0::12::INSTR",
                                       disconnect=lambda: None)
        panel.ppms_instrument_controllers["6221"] = source
        panel.zurich_controller = types.SimpleNamespace(mfli_connected=meter == "zurich", lock=threading.Lock(), mfli_has_multi_demod=lambda: True,
                                                        disconnect_mfli=lambda: None)
        panel.zurich_timeconstant.set(tc_zurich)
        if meter == "zurich":
            # The Zurich alone, chosen here: SHHV starts with SR830-1 and
            # SR830-2 measured since 2026-10-20 (user's figure).
            for key in app.PPMS_SR830_KEYS:
                panel.ppms_lockin_selection[key].set(False)
            panel.ppms_lockin_selection["zurich"].set(True)
        if meter == "sr830":
            panel.ppms_instrument_controllers["830_a"] = types.SimpleNamespace(
                connected=True, label="SR830-1", resource_name="GPIB0::8::INSTR", disconnect=lambda: None)
            for key in app.PPMS_SR830_KEYS:
                panel.ppms_lockin_selection[key].set(key == "830_a")
            panel.ppms_lockin_selection["zurich"].set(False)
            panel.ppms_transport_harmonic_a_var.set("1+2+3")
            panel.ppms_sr830_time_constant_codes = {"830_a": 0}     # 10 us: no real wait
            h.harmonic = {"830_a": 1}

            def write(key, command):
                h.log.append(("sr830", command, threading.get_ident()))
                if command.startswith("HARM "):
                    h.harmonic[key] = int(command.split()[1])

            panel._ppms_write_sr830_checked = write
        h.harmonic = h.__dict__.get("harmonic", {})

        def query(key, command, count):
            # The 6221's OUTP? after the end's off (user, 2026-10-18), and an
            # SR830's HARM? between harmonic passes.
            if command == "OUTP?":
                h.log.append(("6221", "OUTP?", threading.get_ident()))
                return (0,)
            assert command == "HARM?", command
            return (h.harmonic[key],)
        panel._ppms_query_numbers = query
        h.points = 0

        def sample(settings_lockins):
            h.points += 1
            # The Zurich's harmonics as the page has them (1+2 by default,
            # user's figure, 2026-10-18), one demodulator per order.
            orders = str(panel.zurich_harmonic.get())
            values = {"zurich_harmonic": orders}
            for demod in range(1, len(orders.split("+")) + 1):
                values.update({f"zurich_demod{demod}_x_v": demod * 1e-6 + h.points * 1e-9,
                               f"zurich_demod{demod}_y_v": -demod * 1e-6, f"zurich_demod{demod}_r_v": demod * 1.4e-6,
                               f"zurich_demod{demod}_theta_deg": -45.0, f"zurich_demod{demod}_harmonic": demod,
                               f"zurich_demod{demod}_input": 0})
            for key in settings_lockins:
                values.update({"sr830_8_x_v": 2e-6 + h.points * 1e-9, "sr830_8_y_v": 1e-6, "sr830_8_r_v": 2.2e-6,
                               "sr830_8_theta_deg": 26.0, "sr830_8_reference_valid": True})
            return values

        def configure(settings):
            h.log.append(("6221", "on", settings["current_rms_ma"], settings["frequency_hz"], threading.get_ident()))

        def first(frequency, lockins, duration):
            h.log.append(("lockins", "first", tuple(lockins), threading.get_ident()))
            return sample(lockins), 2

        def average(frequency, lockins, duration):
            h.log.append(("lockins", "read", tuple(lockins), threading.get_ident()))
            return sample(lockins)

        panel._configure_ppms_transport_scan = configure
        panel._acquire_ppms_first_point = first
        panel._average_ppms_transport_sample = average
        panel._stop_ppms_transport_source = lambda: h.log.append(("6221", "off", threading.get_ident()))
        panel._read_ppms_current_display = lambda: "ON"
        # The page as the user leaves it before Start.
        panel.ppms_control_safety_var.set(True)
        panel.rte_drive_target.set("1.5")
        panel.rte_voltage_limit.set("5")
        panel.ppms_field_scan_stable_var.set("0")
        panel.ppms_acquisition_time_var.set("0.01")
        panel.rte_connect = None
        panel._rte_connect("newmark")
        self.pump(h)
        self.assertTrue(stage.connected, h.showerror.call_args)
        # The 0.01 s typed above stays through the mode changes: a mode puts
        # its own Acquire s in the box only while the box still holds the
        # last mode's (2026-11-22; test_rte_angle_scan's mode tests).
        panel.ppms_simple_mode.set("Angle")
        panel._rte_mode_changed()
        for variable, value in zip(panel.ppms_simple_range, span):
            variable.set(value)
        panel.ppms_field_scan_loop_var.set(loops)
        panel.rte_round_trip.set(round_trip)
        h.log.clear()
        return h

    def pump(self, h, until=None, limit=5000):
        """As the program's Tk thread, until nothing is left: wait for the
        worker, run the post_ui queue (drain_ui_queue), then what
        root.after(0, ...) scheduled (the Tk event loop); the idle poll's
        1 s timer stays queued."""
        for _ in range(limit):
            h.executor.submit(lambda: None).result(timeout=120)
            moved = False
            while h.ui:
                h.in_drain = True
                try:
                    h.ui.pop(0)()
                finally:
                    h.in_drain = False
                moved = True
            ready = [item for item in h.root.pending if item[0] < 1000]
            for item in ready:
                h.root.pending.remove(item)
                item[1]()
                moved = True
            if until is not None and until():
                return
            if not moved and not h.panel.ppms_field_scan_running:
                return
        raise AssertionError("the page did not settle")

    def start(self, h):
        h.panel.start_ppms_field_scan()
        self.pump(h)

    @staticmethod
    def rows(h):
        folder = h.panel.rte_run_folder          # <folder>/<stem>/<stem>.csv
        with (folder / f"{folder.name}.csv").open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    @staticmethod
    def names(h, *kinds):
        return [entry[:2] for entry in h.log if entry[0] in kinds]


class AngleScanTests(EndToEnd):
    def test_a_whole_round_trip_angle_scan(self):
        h = self.make()
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        self.assertFalse(panel.ppms_field_scan_running)
        # The Yes/No names the angles, the held field and the wires.
        question = h.askyesno.call_args.args[1]
        self.assertIn("Angle scan from 0° to 20° (step 10°, round trip): 5 angles x 1 harmonic pass(es) = 5 points",
                      question)
        self.assertIn("the KEPCO is set once to +1.5 A (voltage limit 5 V)", question)
        self.assertIn("SAMPLE HOLDER with its wires", question)
        # The order: the stage check, the 6221 on, the KEPCO set once and the
        # field settled on the LS475, then every angle: the move, the field
        # before, the lock-ins, the field after.
        sequence = [entry[:3] if entry[0] == "stage" else entry[:2] for entry in h.log]
        self.assertEqual(sequence[:2], [("6221", "on"), ("kepco", "set_output")])
        settle = sequence[2:2 + app.STFMR_FIELD_SETTLE_REQUIRED_SAMPLES]
        self.assertEqual(settle, [("gauss", "read")] * app.STFMR_FIELD_SETTLE_REQUIRED_SAMPLES)
        points = sequence[2 + app.STFMR_FIELD_SETTLE_REQUIRED_SAMPLES:-3]
        expected = []
        for index, angle in enumerate((0.0, 10.0, 20.0, 10.0, 0.0)):
            expected += [("stage", "move", angle), ("stage", "at", angle), ("gauss", "read"),
                         ("lockins", "first" if index == 0 else "read"), ("gauss", "read")]
        self.assertEqual(points, expected)
        self.assertEqual([e[2:5] for e in h.log if e[:2] == ("kepco", "set_output")], [("CURR", 1.5, 5.0)])
        # The end: the 6221 off and read back, then the KEPCO zeroed (user,
        # 2026-10-18: "when finish scan in SHHV, automatically zero the Kepco
        # and 6221 pls"; both were held until then).
        self.assertEqual(sequence[-3:], ZEROED)
        self.assertEqual(self.names(h, "kepco", "6221"), [("6221", "on"), ("kepco", "set_output")] + ZEROED)
        # Every instrument call and every DLL call on the rte-control worker.
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})
        self.assertEqual({thread for _name, thread in h.dll.calls}, {h.worker})
        self.assertNotIn(threading.get_ident(), {thread for _name, thread in h.dll.calls})
        for command in ("X100000", "X200000"):
            self.assertIn(command, h.sim.received)
        # The live CSV: one row per angle, the angle read back, its steps.
        rows = self.rows(h)
        self.assertEqual([float(r["stage_target_deg"]) for r in rows], [0.0, 10.0, 20.0, 10.0, 0.0])
        self.assertEqual([float(r["stage_angle_deg"]) for r in rows], [0.0, 10.0, 20.0, 10.0, 0.0])
        self.assertEqual([int(r["stage_position_steps"]) for r in rows], [0, 100000, 200000, 100000, 0])
        self.assertEqual({r["stage_steps_per_degree"] for r in rows}, {"10000"})
        self.assertEqual({(r["module"], r["scan_mode"], r["loop"]) for r in rows}, {("SHHV", "Angle", "1")})
        self.assertEqual([r["point"] for r in rows], ["1", "2", "3", "4", "5"])
        self.assertEqual({r["kepco_programmed_current_a"] for r in rows}, {"1.5"})
        self.assertEqual({r["measured_field_g"] for r in rows}, {"123.0"})
        self.assertEqual({r["kepco_voltage_limit_v"] for r in rows}, {"5.0"})
        self.assertEqual(rows[0]["first_point_windows"], "2")
        # The finish and the live lines.
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; KEPCO and 6221 zeroed; stage at +0.000°")
        self.assertEqual((panel.rte_drive_live.get(), panel.ppms_current_live_var.get()),
                         ("KEPCO: zeroed and output OFF", "OFF / 0 mA"))
        self.assertEqual(panel.rte_stage_live.get(), "Stage: +0.000° (10000 steps/°)")
        self.assertEqual(panel.rte_field_live.get(), "LS475 field: +123 G")
        self.assertEqual(panel.ppms_field_scan_total, 5)
        # The plots: against the angle read back, every point.
        # The last plot drawn with data: with the Zurich at 1+2 (user's
        # figure, 2026-10-18) the hidden third-harmonic row is drawn empty.
        drawn = next(c for c in reversed(h.draw.call_args_list) if c.args[1])
        x_label, series = drawn.args[2], drawn.args[1]
        self.assertEqual(x_label, "Sample angle (°)")
        self.assertTrue(series)
        for name, points in series.items():
            with self.subTest(series=name):
                self.assertEqual([x for x, _y in points], [0.0, 10.0, 20.0, 10.0, 0.0])
        # Save CSV writes the same rows, the stage columns included.
        saved = Path(h.folder.name) / "saved.csv"
        with patch.object(app.filedialog, "asksaveasfilename", return_value=str(saved)):
            panel.save_ppms_field_scan_csv()
        with saved.open(encoding="utf-8-sig", newline="") as handle:
            copy = list(csv.DictReader(handle))
        self.assertEqual([r["stage_angle_deg"] for r in copy], [r["stage_angle_deg"] for r in rows])
        # The idle poll afterwards reads the stage again, on the worker.
        h.sim.received.clear()
        panel.ppms_poll_inflight = False
        panel._ppms_poll_timer()
        self.pump(h)
        self.assertEqual(h.sim.received, ["MST", "PX"])
        self.assertEqual(panel.rte_stage_live.get(), "Stage: +0.000° (10000 steps/°)")

    def test_loops_without_round_trip(self):
        h = self.make(span=("30", "0", "15"), loops="2", round_trip=False)
        self.start(h)
        h.showerror.assert_not_called()
        rows = self.rows(h)
        self.assertEqual([(r["loop"], r["point"], float(r["stage_angle_deg"])) for r in rows],
                         [("1", "1", 30.0), ("1", "2", 15.0), ("1", "3", 0.0),
                          ("2", "1", 30.0), ("2", "2", 15.0), ("2", "3", 0.0)])
        self.assertEqual([e[2] for e in h.log if e[:2] == ("stage", "move")], [30.0, 15.0, 0.0, 30.0, 15.0, 0.0])
        self.assertEqual(len([e for e in h.log if e[:2] == ("kepco", "set_output")]), 1)
        series = next(c.args[1] for c in reversed(h.draw.call_args_list) if c.args[1])
        self.assertEqual(sorted({name.rsplit(" ", 1)[-1] for name in series}), ["L1", "L2"], "one series per loop")

    def test_harmonic_passes_with_an_sr830(self):
        h = self.make(span=("0", "10", "10"), round_trip=False, meter="sr830")
        self.start(h)
        h.showerror.assert_not_called()
        rows = self.rows(h)
        self.assertEqual([(r["harmonic_pass"], r["sr830_8_harmonic"], float(r["stage_angle_deg"])) for r in rows],
                         [("1", "1", 0.0), ("1", "1", 10.0), ("2", "2", 0.0), ("2", "2", 10.0),
                          ("3", "3", 0.0), ("3", "3", 10.0)])
        # The field set once for every pass; the harmonic changed between
        # passes, the 6221 left on.
        self.assertEqual(len([e for e in h.log if e[:2] == ("kepco", "set_output")]), 1)
        self.assertEqual(len([e for e in h.log if e[:2] == ("6221", "on")]), 1)
        self.assertEqual([e[1] for e in h.log if e[0] == "sr830"], ["HARM 2", "HARM 3"])
        self.assertEqual(h.panel.ppms_field_scan_total, 6)
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})

    def test_the_lockins_at_start_up(self):
        # The user's figure (2026-11-16): SR830-1 at 2 measured; SR830-2 at
        # 2, SR830-3 at 3 and the Zurich at 1+2 not measured.
        panel = build_page()
        self.assertEqual({key: (str(panel._ppms_harmonic_var(key).get()), panel.ppms_lockin_selection[key].get())
                          for key in app.PPMS_SR830_KEYS},
                         {"830_a": ("2", True), "830_b": ("2", False), "830_c": ("3", False)})
        self.assertEqual((panel.zurich_harmonic.get(), panel.ppms_lockin_selection["zurich"].get()), ("1+2", False))

    def test_the_zurich_alone_runs(self):
        h = self.make(span=("0", "0", "5"), round_trip=False)
        panel = h.panel
        self.assertEqual(panel.ppms_lockin_selection["zurich"].get(), True)
        self.assertFalse(any(panel.ppms_lockin_selection[k].get() for k in app.PPMS_SR830_KEYS))
        self.start(h)
        h.showerror.assert_not_called()
        self.assertEqual([e[2] for e in h.log if e[0] == "lockins"], [()], "no SR830 read, the Zurich in the sample")
        row = self.rows(h)[0]
        self.assertEqual((row["zurich_harmonic"], row["zurich_demod2_harmonic"]), ("1+2", "2"))
        self.assertNotIn("zurich_demod3_harmonic", row, "1+2 by default (user's figure, 2026-10-18)")

    def test_the_mode_change_sets_the_angle_boxes(self):
        panel = build_page()
        # The page starts on the user's Angle+Field scan (2026-11-17; Angle
        # from 2026-11-16, Angle+Field from 2026-10-19).
        self.assertEqual(panel.ppms_simple_mode.get(), "Angle+Field")
        self.assertEqual(panel.rte_scan_note.get(), "Angle+Field: Stage °; outer: field G")
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Field")
            panel._rte_mode_changed()
        self.assertEqual(panel.rte_scan_note.get(), "Field: KEPCO A; readback: signed LS475 G")
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series") as draw:
            panel.ppms_simple_mode.set("Angle")
            panel._rte_mode_changed()
        # 0 to -360 deg in 5 deg steps (user's figures, 2026-10-18).
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["0", "-360", "5"])
        self.assertEqual(panel.rte_scan_units.get(), "Stage °")
        # The note says which box holds the field (user, 2026-10-17).
        self.assertEqual(panel.rte_scan_note.get(), "Angle: Stage °; field: KEPCO current A")
        # Round trip off for Angle (user, 2026-10-18: "default not click
        # Round trip"; it was on since 2026-10-13).
        self.assertIs(panel.rte_round_trip.get(), False, "round trip off by default")
        self.assertEqual(panel.ppms_plot_axis, "angle")
        self.assertEqual(draw.call_args.args[2], "Sample angle (°)", "an empty plot against the angle")
        for mode in ("Field", "Current"):
            with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
                panel.ppms_simple_mode.set(mode)
                panel._rte_mode_changed()
            self.assertEqual(panel.rte_scan_note.get(), "Field: KEPCO A; readback: signed LS475 G")
        self.assertLessEqual(max(map(len, app.RTE_SCAN_NOTES.values())), 40)


class AngleScanStopTests(EndToEnd):
    def test_stop_during_a_move_sends_stop_and_says_where_the_stage_is(self):
        h = self.make(span=("0", "90", "90"), round_trip=False)
        panel = h.panel
        h.move_hooks[90.0] = lambda: h.clock.hooks.append((h.clock.t + 3.0, panel.stop_ppms_field_scan))
        self.start(h)
        h.showerror.assert_not_called()
        received = h.sim.received
        self.assertIn("STOP", received[received.index("X900000"):])
        self.assertNotIn("ABORT", received)
        self.assertFalse(h.stage.motion_may_run)
        status = panel.ppms_field_scan_status_var.get()
        self.assertTrue(status.startswith("Stopped; KEPCO and 6221 zeroed; stage stopped at +"), status)
        where = float(status.rsplit(" ", 1)[1].rstrip("°"))
        self.assertTrue(0 < where < 90, where)
        self.assertEqual([float(r["stage_angle_deg"]) for r in self.rows(h)], [0.0], "the first angle's row kept")
        self.assertEqual(self.names(h, "kepco", "6221"), [("6221", "on"), ("kepco", "set_output")] + ZEROED,
                         "a Stop zeroes both, once the stage has stopped")
        moves = [entry[:3] for entry in h.log]
        self.assertLess(moves.index(("stage", "move", 90.0)), moves.index(("6221", "off", h.worker)),
                        "the stopped move (STOP confirmed) before the zeroing; the stage is not moved again")
        self.assertEqual([e[2] for e in h.log if e[:2] == ("stage", "move")], [0.0, 90.0])
        self.assertFalse(panel.ppms_field_scan_running)
        self.assertIn(f"SHHV Newmark NSC-A1 connected (Ace-Series-SDE, V231BL): {h.stage.scale_text()}", h.logged)

    def test_stop_during_a_settle(self):
        # 1 s settle a point (the Zurich's 1 s time constant): Stop from the
        # Tk thread while the worker waits.
        h = self.make(span=("0", "10", "10"), round_trip=False, tc_zurich="1")
        panel = h.panel
        panel.start_ppms_field_scan()
        self.pump(h, until=lambda: panel.ppms_field_scan_running)
        deadline = time.monotonic() + 30
        while not [e for e in h.log if e[:2] == ("stage", "at")] and time.monotonic() < deadline:
            time.sleep(0.02)
        time.sleep(0.2)                         # inside the first point's 1 s settle
        panel.stop_ppms_field_scan()
        self.pump(h)
        h.showerror.assert_not_called()
        self.assertEqual(panel.ppms_field_scan_status_var.get(),
                         "Stopped; KEPCO and 6221 zeroed; stage at +0.000°")
        self.assertEqual([e for e in h.log if e[0] == "lockins"], [], "the point was not read")
        self.assertEqual([e[2] for e in h.log if e[:2] == ("stage", "move")], [0.0], "no further move")

    def test_a_failed_move_stops_the_6221_then_zeroes_both_and_says_where(self):
        h = self.make(EndsShort(), span=("0", "10", "10"), round_trip=False)
        panel = h.panel
        self.start(h)
        h.showerror.assert_called_once()
        message = h.showerror.call_args.args[1]
        self.assertIn("not at the target", message)
        self.assertIn("Stage stopped at +9.999°", message)
        self.assertTrue(panel.ppms_field_scan_status_var.get().startswith("Failed: "))
        self.assertEqual(self.names(h, "kepco", "6221"),
                         [("6221", "on"), ("kepco", "set_output"), ("6221", "off")] + ZEROED,
                         "a stage failure: the 6221 off at once, then the end's zeroing of both")
        self.assertIn("At the end: 6221 zeroed; KEPCO zeroed", message)
        self.assertIn("SHHV Angle scan, after the stage failure: stage stopped at +9.999°", h.logged)
        self.assertEqual([float(r["stage_angle_deg"]) for r in self.rows(h)], [0.0])

    def test_closing_during_a_scan_stops_it_and_closes_the_stage_on_the_worker(self):
        h = self.make(span=("0", "10", "10"), round_trip=False, tc_zurich="1")
        panel = h.panel
        panel.zurich_executor = Mock()
        panel.start_ppms_field_scan()
        self.pump(h, until=lambda: panel.ppms_field_scan_running)
        deadline = time.monotonic() + 30
        while not [e for e in h.log if e[:2] == ("stage", "at")] and time.monotonic() < deadline:
            time.sleep(0.02)
        panel.safe_close_ppms()
        h.executor.shutdown(wait=True)
        self.assertFalse(h.stage.connected, "the queued clean-up closed it")
        self.assertEqual(h.dll.names()[-1], "fnPerformaxComClose")
        self.assertEqual({thread for _name, thread in h.dll.calls}, {h.worker})
        self.assertEqual([e[2] for e in h.log if e[:2] == ("stage", "move")], [0.0], "no further move")
        self.assertIsNone(panel._newmark_stage_ownership().owner)


def fail_next_log_write(recorder, failures=1):
    """The run log's next ``failures`` writes raise, as a full disk would."""
    real = recorder._append
    left = [failures]

    def append(text):
        if left[0]:
            left[0] -= 1
            raise OSError(28, "No space left on device")
        return real(text)
    recorder._append = append


class RunLogBase(EndToEnd):
    """The page of the scans above, with which thread wrote each log event
    and Field and Current scans on it."""

    def make(self, *args, **kwargs):
        h = super().make(*args, **kwargs)
        # Which thread wrote each event, from the recorder's own event().
        h.writes = []
        real = app.SHHVScanRecorder.event

        def event(recorder, name, **details):
            h.writes.append((name, threading.get_ident()))
            return real(recorder, name, **details)
        guard = patch.object(app.SHHVScanRecorder, "event", event)
        guard.start()
        self.addCleanup(guard.stop)
        real_close = app.SHHVScanRecorder.close

        def close(recorder, outcome, **details):
            h.writes.append(("close", threading.get_ident()))
            return real_close(recorder, outcome, **details)
        guard = patch.object(app.SHHVScanRecorder, "close", close)
        guard.start()
        self.addCleanup(guard.stop)
        return h

    def make_mode(self, mode, span, **kwargs):
        """A Field or Current scan on the same page (the KEPCO, the LS475
        and the 6221 fakes); the stage stays connected and still."""
        h = self.make(**kwargs)
        panel = h.panel
        panel.ppms_simple_mode.set(mode)
        panel._rte_mode_changed()
        for variable, value in zip(panel.ppms_simple_range, span):
            variable.set(value)
        panel._update_ppms_transport_current = lambda settings: h.log.append(
            ("6221", "current", settings["current_rms_ma"], threading.get_ident()))
        h.log.clear()
        return h

    @staticmethod
    def events(h):
        folder = h.panel.rte_run_folder
        with (folder / f"{folder.name}.log").open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle]

    @staticmethod
    def without_notes(events):
        return [event["event"] for event in events if event["event"] != "note"]

    def assert_closed(self, h):
        self.assertIsNone(h.panel.rte_recorder, "the page let the recorder go")
        self.assertEqual(self.events(h)[-1]["event"], "run_finished")


class RunLogTests(RunLogBase):
    """The SHHV run folder and its log (user, 2026-10-18: "like ST-FMR, pls
    also write a log of SHHV and save results in a folder"), on the real
    page, worker and stage controller of the scans above."""

    def test_a_whole_angle_scan_is_logged_in_order(self):
        h = self.make()
        before = dict(h.stage.last_state)
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        # The run folder <folder>/<name>/, its two files and nothing else.
        folder = Path(h.folder.name) / "angle"
        self.assertEqual(panel.rte_run_folder, folder)
        self.assertEqual(sorted(p.name for p in Path(h.folder.name).iterdir()), ["angle"])
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["angle.csv", "angle.log"])
        self.assertEqual(len(self.rows(h)), 5, "the live CSV as before, in the folder")
        events = self.events(h)
        expected = ["run_prepared", "scan_started", "harmonic_pass", "field_programmed", "field_settled"]
        for _angle in range(5):
            expected += ["stage_move", "point_saved"]
        self.assertEqual(self.without_notes(events), expected + ["outputs_zeroed", "plot_snapshots", "run_finished"])
        for event in events:
            datetime.datetime.fromisoformat(event["timestamp"])
        # run_prepared: the settings and the instruments at Start.
        prepared = events[0]
        self.assertEqual((prepared["program"], prepared["app_version"]), ("Transport_RT.py", app.APP_VERSION))
        self.assertTrue(prepared["python_version"])
        self.assertEqual((prepared["file_name"], prepared["mode"]), ("angle", "Angle"))
        self.assertEqual((prepared["run_folder"], prepared["csv_path"], prepared["log_path"]),
                         (str(folder), str(folder / "angle.csv"), str(folder / "angle.log")))
        plan = prepared["plan"]
        self.assertEqual((plan["start"], plan["end"], plan["step"], plan["loops"], plan["round_trip"]),
                         ("0", "20", "10", 1, True))
        self.assertEqual((plan["points"], plan["harmonic_passes"], plan["total_points"], plan["first_target"],
                          plan["farthest_target"]), (5, 1, 5, 0.0, 20.0))
        self.assertEqual((prepared["timing"]["settle_s"], prepared["timing"]["acquire_s"]), (0.0, 0.01))
        self.assertEqual(prepared["timing"]["effective_settle_s"], 0.001, "1 x the Zurich's 1 ms TC")
        self.assertEqual(prepared["harmonic_passes"], [{"harmonic_pass": 1, "harmonics": {}, "zurich_harmonics": "1+2"}])
        self.assertEqual(list(prepared["lockins"]), ["Zurich"])
        self.assertEqual((prepared["lockins"]["Zurich"]["harmonics"], prepared["lockins"]["Zurich"]["time_constant_s"]),
                         ("1+2", 0.001))
        self.assertEqual(prepared["source_6221"]["current_rms_ma"], float(panel.ppms_transport_current_var.get()))
        self.assertEqual(prepared["kepco"], {"current_a": 1.5, "voltage_limit_v": 5.0, "held": True})
        self.assertEqual(prepared["resources"]["newmark"]["identity"], "Ace-Series-SDE")
        self.assertTrue(prepared["resources"]["newmark"]["connected"])
        self.assertTrue(prepared["resources"]["kepco"]["connected"])
        self.assertTrue(prepared["resources"]["zurich"]["connected"])
        self.assertEqual((prepared["motor"]["identity"], prepared["motor"]["version"],
                          prepared["motor"]["steps_per_degree"]), ("Ace-Series-SDE", "V231BL", 10000))
        # Where the stage was: its last reading on the worker (at Connect)
        # and the stage check's MST; nothing was read for the log.
        at_start = prepared["stage_at_start"]
        self.assertEqual((at_start["angle_deg"], at_start["px"], at_start["read_at"]),
                         (before["angle_deg"], before["px"], before["read_at"]))
        self.assertEqual(at_start["stage_check_mst"], 0)
        self.assertIs(prepared["safety_confirmed"], True)
        # The run, in order.
        by_name = {}
        for event in events:
            by_name.setdefault(event["event"], []).append(event)
        self.assertEqual(by_name["scan_started"][0]["points"], 5)
        self.assertEqual(by_name["field_programmed"][0]["current_a"], 1.5)
        self.assertEqual(by_name["field_settled"][0]["field_g"], 123.0)
        self.assertEqual([(e["target_deg"], e["angle_deg"], e["px"]) for e in by_name["stage_move"]],
                         [(0.0, 0.0, 0), (10.0, 10.0, 100000), (20.0, 20.0, 200000), (10.0, 10.0, 100000),
                          (0.0, 0.0, 0)])
        saved = by_name["point_saved"]
        self.assertEqual([(e["index"], e["loop"], e["point"], e["x"]) for e in saved],
                         [(1, 1, 1, 0.0), (2, 1, 2, 10.0), (3, 1, 3, 20.0), (4, 1, 4, 10.0), (5, 1, 5, 0.0)])
        self.assertEqual({(e["x_column"], e["field_before_g"], e["field_after_g"], e["field_drift_g"]) for e in saved},
                         {("stage_angle_deg", 123.0, 123.0, 0.0)})
        finished = events[-1]
        self.assertEqual((finished["outcome"], finished["error"], finished["points_saved"], finished["status"],
                          finished["stage"]),
                         ("completed", "", 5, "Completed; KEPCO and 6221 zeroed; stage at +0.000°", "stage at +0.000°"))
        self.assertEqual(finished["outputs"], {"6221": "zeroed", "kepco": "zeroed"})
        (zeroed,) = [e for e in events if e["event"] == "outputs_zeroed"]
        self.assertEqual((zeroed["6221"], zeroed["kepco"]), ("zeroed", "zeroed"))
        # Every SHHV log line of the run is a note, the Start line naming the folder.
        notes = [event["text"] for event in events if event["event"] == "note"]
        self.assertTrue(notes[0].startswith(f"SHHV Angle scan; run folder: {folder} (angle.csv and angle.log)"), notes)
        self.assertTrue(set(notes) <= set(h.logged))
        self.assertIn(f"SHHV run folder {folder}: completed; angle.csv and angle.log closed", h.logged)
        self.assert_closed(h)
        # Both threads wrote: the Tk thread at Start and at the finish, the
        # worker during the scan; every DLL call stayed on the worker.
        threads = {}
        for name, thread in h.writes:
            threads.setdefault(name, set()).add(thread)
        tk_thread = threading.get_ident()
        self.assertEqual(threads["run_prepared"], {tk_thread})
        self.assertEqual(threads["close"], {tk_thread}, "run_finished and the close at the finish")
        for name in ("scan_started", "harmonic_pass", "field_programmed", "field_settled", "stage_move",
                     "point_saved"):
            self.assertEqual(threads[name], {h.worker}, name)
        self.assertEqual({thread for _name, thread in h.dll.calls}, {h.worker})
        # Save CSV as opens in the run folder.
        with patch.object(app.filedialog, "asksaveasfilename", return_value="") as ask:
            panel.save_ppms_field_scan_csv()
        self.assertEqual(ask.call_args.kwargs["initialdir"], str(folder))

    def test_a_name_in_use_gets_a_suffix_and_nothing_is_overwritten(self):
        h = self.make(span=("0", "10", "10"), round_trip=False)
        self.start(h)
        first = Path(h.folder.name) / "angle"
        kept = {p.name: p.read_bytes() for p in first.iterdir()}
        # A file of the same name, as another run might have left.
        (Path(h.folder.name) / "angle_01").write_text("not a folder", encoding="utf-8")
        for expected in ("angle_02", "angle_03"):
            self.start(h)
            h.showerror.assert_not_called()
            folder = Path(h.folder.name) / expected
            self.assertEqual(h.panel.rte_run_folder, folder)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), [f"{expected}.csv", f"{expected}.log"])
            self.assertEqual(len(self.rows(h)), 2)
        self.assertEqual({p.name: p.read_bytes() for p in first.iterdir()}, kept, "the first run untouched")
        self.assertEqual((Path(h.folder.name) / "angle_01").read_text(encoding="utf-8"), "not a folder")
        # A blank name: SHHV_<date>_<time>.
        with patch.object(app.simpledialog, "askstring", return_value=""):
            self.start(h)
        self.assertRegex(h.panel.rte_run_folder.name, r"^SHHV_\d{8}_\d{6}(_\d\d)?$")

    def test_a_folder_that_cannot_be_made_starts_nothing(self):
        h = self.make()
        missing = Path(h.folder.name) / "missing"
        with patch.object(app.filedialog, "askdirectory", return_value=str(missing)):
            self.start(h)
        h.showerror.assert_called_once()
        self.assertEqual(h.showerror.call_args.args[0], "SHHV: run folder")
        self.assertIn("the scan was not started", h.showerror.call_args.args[1])
        self.assertEqual([e for e in h.log if e[0] in ("6221", "kepco", "lockins")], [], "nothing switched on")
        self.assertEqual([e for e in h.log if e[:2] == ("stage", "move")], [])
        self.assertFalse(h.panel.ppms_field_scan_running)
        self.assertFalse(missing.exists())
        self.assertIsNone(h.panel.__dict__.get("rte_recorder"))

    def test_a_first_log_entry_that_cannot_be_written_starts_nothing(self):
        h = self.make()
        real = app.scan_log_line

        def line(name, details):
            if name == "run_prepared":
                raise OSError(28, "No space left on device")
            return real(name, details)
        with patch.object(app, "scan_log_line", line):
            self.start(h)
        self.assertEqual(h.showerror.call_args.args[0], "SHHV: run folder")
        self.assertIn("Could not write the run log", h.showerror.call_args.args[1])
        self.assertEqual([e for e in h.log if e[0] in ("6221", "kepco", "lockins", "stage")], [])
        folder = Path(h.folder.name) / "angle"
        with (folder / "angle.log").open(encoding="utf-8") as handle:
            (closing,) = [json.loads(text) for text in handle]
        self.assertEqual((closing["event"], closing["outcome"]), ("run_finished", "not_started"))
        self.assertIsNone(h.panel.__dict__.get("rte_recorder"))

    def test_a_field_scan_is_logged_in_order(self):
        h = self.make_mode("Field", ("0", "1", "1"))
        self.start(h)
        h.showerror.assert_not_called()
        events = self.events(h)
        expected = ["run_prepared", "scan_started", "harmonic_pass"]
        for _point in range(3):
            expected += ["field_programmed", "field_settled", "point_saved"]
        self.assertEqual(self.without_notes(events), expected + ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual([e["current_a"] for e in events if e["event"] == "field_programmed"], [0.0, 1.0, 0.0])
        self.assertEqual({(e["x_column"], e["x"]) for e in events if e["event"] == "point_saved"},
                         {("measured_field_g", 123.0)})
        self.assertEqual(events[0]["kepco"], {"current_a": "the plan", "voltage_limit_v": 5.0})
        self.assertNotIn("stage_at_start", events[0])
        self.assertEqual((events[-1]["outcome"], events[-1]["points_saved"], events[-1]["status"]),
                         ("completed", 3, "Completed; KEPCO and 6221 zeroed"))
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        self.assertNotIn("stage", events[-1])
        self.assert_closed(h)

    def test_a_current_scan_is_logged_in_order(self):
        h = self.make_mode("Current", ("0.5", "1.5", "0.5"))
        self.start(h)
        h.showerror.assert_not_called()
        events = self.events(h)
        self.assertEqual(self.without_notes(events),
                         ["run_prepared", "scan_started", "harmonic_pass", "point_saved", "point_saved",
                          "point_saved", "outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual([(e["target"], e["x_column"], e["x"]) for e in events if e["event"] == "point_saved"],
                         [(0.5, "6221_current_rms_ma", 0.5), (1.0, "6221_current_rms_ma", 1.0),
                          (1.5, "6221_current_rms_ma", 1.5)])
        self.assertEqual(events[0]["kepco"], {"used": False})
        self.assertEqual((events[-1]["outcome"], events[-1]["status"]),
                         ("completed", "Completed; KEPCO and 6221 zeroed"))
        # A Current scan never drives the KEPCO; it is zeroed at the end all
        # the same (user, 2026-10-18), after the 6221.
        self.assertEqual([e[:2] for e in h.log if e[0] == "kepco"], [("kepco", "force_off")])
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        self.assert_closed(h)

    def test_a_stop_during_a_move_is_logged(self):
        h = self.make(span=("0", "90", "90"), round_trip=False)
        panel = h.panel
        h.move_hooks[90.0] = lambda: h.clock.hooks.append((h.clock.t + 3.0, panel.stop_ppms_field_scan))
        self.start(h)
        h.showerror.assert_not_called()
        events = self.events(h)
        self.assertEqual(self.without_notes(events),
                         ["run_prepared", "scan_started", "harmonic_pass", "field_programmed", "field_settled",
                          "stage_move", "point_saved", "stop_requested", "outputs_zeroed", "plot_snapshots",
                          "run_finished"])
        (stop,) = [e for e in events if e["event"] == "stop_requested"]
        self.assertEqual(stop["button"], "Stop")
        finished = events[-1]
        self.assertEqual((finished["outcome"], finished["error"], finished["points_saved"]), ("stopped", "", 1))
        self.assertTrue(finished["stage"].startswith("stage stopped at +"), finished)
        self.assertEqual(finished["status"], panel.ppms_field_scan_status_var.get())
        self.assertIn("SHHV stopped at a stage move", finished["stop_reason"])
        self.assert_closed(h)

    def test_a_stage_failure_is_logged(self):
        h = self.make(EndsShort(), span=("0", "10", "10"), round_trip=False)
        self.start(h)
        events = self.events(h)
        self.assertEqual(self.without_notes(events),
                         ["run_prepared", "scan_started", "harmonic_pass", "field_programmed", "field_settled",
                          "stage_move", "point_saved", "stage_failure", "outputs_zeroed", "plot_snapshots",
                          "run_finished"])
        (failure,) = [e for e in events if e["event"] == "stage_failure"]
        self.assertIn("not at the target", failure["error"])
        self.assertEqual(failure["stage"], "stage stopped at +9.999°")
        finished = events[-1]
        self.assertEqual((finished["outcome"], finished["points_saved"], finished["stage"]),
                         ("error", 1, "stage stopped at +9.999°"))
        self.assertIn("not at the target", finished["error"])
        self.assertTrue(finished["status"].startswith("Failed: "))
        self.assertIn("SHHV Angle scan, after the stage failure: stage stopped at +9.999°",
                      [e["text"] for e in events if e["event"] == "note"])
        self.assert_closed(h)

    def test_a_log_write_failure_ends_the_scan_safely(self):
        h = self.make(span=("0", "20", "10"), round_trip=False)
        panel = h.panel
        # The write after the move to 20 deg (its stage_move) fails once.
        h.move_hooks[20.0] = lambda: fail_next_log_write(panel.rte_recorder)
        self.start(h)
        h.showerror.assert_called_once()
        self.assertEqual(h.showerror.call_args.args[0], "SHHV scan")
        self.assertIn("The SHHV log could not be written", h.showerror.call_args.args[1])
        self.assertTrue(panel.ppms_field_scan_status_var.get().startswith("Failed: The SHHV log could not be written"))
        # The normal failure path, as for a failed live-CSV row: the 6221 off,
        # the KEPCO's field held, the stage at rest where it was (no STOP).
        self.assertEqual(self.names(h, "kepco", "6221"),
                         [("6221", "on"), ("kepco", "set_output"), ("6221", "off")] + ZEROED)
        self.assertNotIn("STOP", h.sim.received)
        self.assertFalse(h.stage.motion_may_run)
        self.assertEqual([float(r["stage_angle_deg"]) for r in self.rows(h)], [0.0, 10.0], "no row after the failure")
        events = self.events(h)
        self.assertEqual(self.without_notes(events),
                         ["run_prepared", "scan_started", "harmonic_pass", "field_programmed", "field_settled",
                          "stage_move", "point_saved", "stage_move", "point_saved", "outputs_zeroed",
                          "plot_snapshots", "run_finished"])
        self.assertEqual((events[-1]["outcome"], events[-1]["points_saved"], events[-1]["stage"]),
                         ("error", 2, "stage at +20.000°"))
        self.assertIn("No space left on device", events[-1]["error"])
        self.assert_closed(h)

    def test_a_stop_button_from_the_tk_thread_is_logged(self):
        h = self.make(span=("0", "10", "10"), round_trip=False, tc_zurich="1")
        panel = h.panel
        panel.start_ppms_field_scan()
        self.pump(h, until=lambda: panel.ppms_field_scan_running)
        deadline = time.monotonic() + 30
        while not [e for e in h.log if e[:2] == ("stage", "at")] and time.monotonic() < deadline:
            time.sleep(0.02)
        panel._rte_stage_stop()
        self.pump(h)
        events = self.events(h)
        (stop,) = [e for e in events if e["event"] == "stop_requested"]
        self.assertEqual(stop["button"], "Stop stage")
        self.assertIn(("stop_requested", threading.get_ident()), h.writes, "written from the Tk thread")
        self.assertEqual(events[-1]["outcome"], "stopped")
        self.assert_closed(h)

    def test_closing_the_program_mid_scan_closes_the_log(self):
        h = self.make(span=("0", "10", "10"), round_trip=False, tc_zurich="1")
        panel = h.panel
        panel.zurich_executor = Mock()
        panel.start_ppms_field_scan()
        self.pump(h, until=lambda: panel.ppms_field_scan_running)
        deadline = time.monotonic() + 30
        while not [e for e in h.log if e[:2] == ("stage", "at")] and time.monotonic() < deadline:
            time.sleep(0.02)
        panel.safe_close_ppms()
        h.executor.shutdown(wait=True)
        events = self.events(h)
        # The stop events are set before stop_requested is written (review,
        # 2026-10-18), so the worker's outputs_zeroed may come first.
        last = self.without_notes(events)[-3:]
        self.assertEqual((sorted(last[:2]), last[2]), (["outputs_zeroed", "stop_requested"], "run_finished"))
        (stop,) = [e for e in events if e["event"] == "stop_requested"]
        self.assertEqual(stop["button"], "the program closing")
        # The close leaves neither output on: the scan's end zeroed both on
        # the worker, before the clean-up job closed the stage.
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        finished = events[-1]
        self.assertEqual((finished["outcome"], finished["status"], finished["points_saved"]),
                         ("stopped", "the program closed", 0))
        # Closed by the clean-up job on the worker, after the scan, before the stage.
        self.assertIn(("close", h.worker), h.writes)
        self.assertIn(("stop_requested", threading.get_ident()), h.writes)
        self.assertIsNone(panel.rte_recorder)
        self.assertEqual({thread for _name, thread in h.dll.calls}, {h.worker})

    def test_a_scan_the_worker_cannot_take_closes_its_log(self):
        h = self.make_mode("Field", ("0", "1", "1"))
        panel = h.panel
        refusing = Mock()
        refusing.submit.side_effect = RuntimeError("cannot schedule new futures after shutdown")
        panel.ppms_executor = refusing
        panel.start_ppms_field_scan()
        self.pump(h)        # the dialog opens from the Tk event loop (review, 2026-10-18)
        self.assertEqual(h.showerror.call_args.args[0], "SHHV scan not started")
        self.assertFalse(panel.ppms_field_scan_running)
        events = self.events(h)
        self.assertEqual(self.without_notes(events), ["run_prepared", "run_finished"])
        self.assertEqual((events[-1]["outcome"], events[-1]["points_saved"]), ("not_started", 0))
        self.assertIsNone(panel.rte_recorder)



class ScanEndZeroTests(RunLogBase):
    """User, 2026-10-18: "when finish scan in SHHV, automatically zero the
    Kepco and 6221 pls": each ending zeroes the 6221 (off, read back), then
    the KEPCO (its Zero / OFF), on the worker, each step tried whatever the
    other did; a zero that fails is said on the status line, in a dialog
    and in the log."""

    def test_a_kepco_zero_that_fails_is_reported(self):
        h = self.make(span=("0", "10", "10"), round_trip=False)

        def refused():
            h.log.append(("kepco", "force_off", threading.get_ident()))
            raise RuntimeError("KEPCO 4886 zero/OFF not confirmed: 'OUTP OFF' VI_ERROR_TMO")
        h.kepco.force_output_off = refused
        self.start(h)
        panel = h.panel
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; 6221 zeroed; KEPCO zero FAILED; stage at +10.000°")
        h.showerror.assert_called_once()
        title, message = h.showerror.call_args.args
        self.assertEqual(title, "SHHV outputs")
        self.assertIn("CHECK IT", message)
        self.assertIn("KEPCO zero FAILED: KEPCO 4886 zero/OFF not confirmed: 'OUTP OFF' VI_ERROR_TMO", message)
        self.assertNotEqual(panel.rte_drive_live.get(), "KEPCO: zeroed and output OFF")
        finished = self.events(h)[-1]
        self.assertEqual(finished["outputs"]["kepco"],
                         "zero FAILED: KEPCO 4886 zero/OFF not confirmed: 'OUTP OFF' VI_ERROR_TMO")
        self.assertEqual(finished["outcome"], "completed")
        self.assertIn("SHHV scan end: 6221 zeroed; KEPCO zero FAILED: KEPCO 4886 zero/OFF not confirmed: "
                      "'OUTP OFF' VI_ERROR_TMO", h.logged)
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})

    def test_a_6221_off_that_fails_still_zeroes_the_kepco(self):
        h = self.make_mode("Field", ("0", "1", "1"))

        def refused():
            h.log.append(("6221", "off", threading.get_ident()))
            raise RuntimeError("6221 output OFF not confirmed: VI_ERROR_TMO")
        h.panel._stop_ppms_transport_source = refused
        self.start(h)
        panel = h.panel
        self.assertEqual(self.names(h, "kepco", "6221")[-2:], [("6221", "off"), ("kepco", "force_off")],
                         "the KEPCO after the failed 6221 off (no read-back of a refused off)")
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; 6221 zero FAILED; KEPCO zeroed: check it")
        self.assertEqual(h.showerror.call_args.args[0], "SHHV outputs")
        self.assertEqual(self.events(h)[-1]["outputs"],
                         {"6221": "zero FAILED: 6221 output OFF not confirmed: VI_ERROR_TMO", "kepco": "zeroed"})
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})

    def test_a_failed_scan_zeroes_both_and_its_dialog_says_so(self):
        h = self.make_mode("Field", ("0", "1", "1"))
        h.gauss.read_field = Mock(side_effect=RuntimeError("LS475 read failed"))
        self.start(h)
        # The field failure's own clean-up (the 6221 off, the KEPCO's
        # safe off), then the end's zeroing of both.
        self.assertEqual(self.names(h, "kepco", "6221"),
                         [("6221", "on"), ("kepco", "set_output"), ("6221", "off"), ("kepco", "off")] + ZEROED)
        status = h.panel.ppms_field_scan_status_var.get()
        self.assertEqual(status, "Failed: LS475 read failed", "a failure keeps its text")
        title, message = h.showerror.call_args.args
        self.assertEqual(title, "SHHV scan")
        self.assertTrue(message.endswith("At the end: 6221 zeroed; KEPCO zeroed"), message)
        self.assertEqual(self.events(h)[-1]["outputs"], {"6221": "zeroed", "kepco": "zeroed"})

    def test_the_finish_status_lines(self):
        zeroed = {"6221": "zeroed", "kepco": "zeroed"}
        self.assertEqual(app.rte_outputs_text(zeroed), "KEPCO and 6221 zeroed")
        self.assertEqual(app.rte_outputs_text({"6221": "zeroed", "kepco": "not connected"}),
                         "6221 zeroed; KEPCO not connected")
        self.assertEqual(app.rte_outputs_text({"6221": "zeroed", "kepco": "zero FAILED: x"}),
                         "6221 zeroed; KEPCO zero FAILED: check it")
        self.assertEqual(app.rte_outputs_text({"6221": "zeroed", "kepco": "zero FAILED: x"}, check=False),
                         "6221 zeroed; KEPCO zero FAILED")
        self.assertEqual(app.rte_outputs_text({"6221": "zero FAILED: x", "kepco": "zeroed"}),
                         "6221 zero FAILED; KEPCO zeroed: check it")
        self.assertEqual(app.rte_outputs_text({"6221": "zero FAILED: x", "kepco": "zero FAILED: y"}),
                         "zero FAILED: 6221 and KEPCO: check them")
        self.assertEqual(app.rte_outputs_text({"6221": "zero FAILED: x", "kepco": "zero FAILED: y"}, check=False),
                         "zero FAILED: 6221 and KEPCO")
        self.assertEqual(app.rte_outputs_text(None), "KEPCO and 6221 not confirmed zeroed: check them")


class OuterScanTests(RunLogBase):
    """Angle+Field and Angle+Current, end to end (user, 2026-10-18: "add the
    angle + field scan mode, field is the outside loop"; "also angle+current
    mode, the current is outside loop"), on the real page, worker and stage
    controller of the scans above."""

    def make_outer(self, mode, outer, span=("0", "10", "10"), **kwargs):
        h = self.make(span=span, round_trip=False, **kwargs)
        panel = h.panel
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set(mode)
            panel._rte_mode_changed()
        self.assertIs(panel.rte_round_trip.get(), False, "round trip off by default")
        for variable, value in zip(panel.ppms_simple_range, span):
            variable.set(value)
        for variable, value in zip(panel.rte_outer_ranges[mode], outer):
            variable.set(value)
        h.configured, h.updated = [], []

        def configure(settings):
            h.configured.append(dict(settings))
            h.log.append(("6221", "on", settings["current_rms_ma"], settings["frequency_hz"], threading.get_ident()))

        def update(settings):
            h.updated.append(dict(settings))
            h.log.append(("6221", "current", settings["current_rms_ma"], threading.get_ident()))
        panel._configure_ppms_transport_scan = configure
        panel._update_ppms_transport_current = update
        h.log.clear()
        return h

    @staticmethod
    def sequence(h):
        """The calls in order, without their threads: a move's angle, a
        KEPCO step's and a 6221 change's current, the 6221 on's current, the
        mode of set_output."""
        calls = []
        for entry in h.log:
            if entry[0] in ("gauss", "lockins") or entry[1] in ("off", "OUTP?", "force_off"):
                calls.append(entry[:2])
            elif entry[1] in ("on", "set_output"):
                calls.append(entry[:3])
            else:
                calls.append(entry[:-1])
        return calls

    @staticmethod
    def point(angle, first=False):
        return [("stage", "move", angle), ("stage", "at", angle), ("gauss", "read"),
                ("lockins", "first" if first else "read"), ("gauss", "read")]

    def make_field_list(self, typed, gauss_class=None, **kwargs):
        """An Angle+Field scan whose LS475 reads 100 G per A of the KEPCO's
        current (FollowingGauss), with the field setting's waits made tiny
        (not 0: read_settled_magnet_field divides its timeout by them)."""
        h = self.make_outer("Angle+Field", (typed,), **kwargs)
        h.gauss = (gauss_class or FollowingGauss)(h.log, h.kepco)
        h.panel.rte_controllers["gauss"] = h.gauss
        for name, value in (("MAGNET_FIELD_SET_SETTLE_S", 0.0), ("MAGNET_FIELD_SET_READ_INTERVAL_S", 1e-4),
                            ("MAGNET_FIELD_SET_GROUP_GAP_S", 1e-4)):
            patcher = patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        return h

    def test_angle_field_reaches_the_typed_fields_in_order(self):
        """Angle+Field (user, 2026-11-17: "I type the field directly and it
        auto reach the current"): each typed field, a repeated one included,
        reached as Set field reaches it; the current then left for the whole
        angle sweep."""
        h = self.make_field_list("100, 20 100")
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV Angle+Field scan")
        self.assertIn("Field, the OUTER loop: 3 fields in the order typed: +100, +20, +100 G, each within ±2 G on "
                      "the LS475 (Set field's Tol. box).", question)
        self.assertIn("never beyond ±10 A", question)
        self.assertIn("3 field steps x 2 angles x 1 harmonic pass(es) = 6 points.", question)
        # The KEPCO switched on once, at 0 A with the voltage limit; then only currents.
        self.assertEqual([e[2:5] for e in h.log if e[:2] == ("kepco", "set_output")], [("CURR", 0.0, 5.0)])
        rows = self.rows(h)
        self.assertEqual([(r["outer_target_field_g"], r["outer_field_index"], float(r["stage_angle_deg"]))
                          for r in rows],
                         [("100.0", "1", 0.0), ("100.0", "1", 10.0), ("20.0", "2", 0.0), ("20.0", "2", 10.0),
                          ("100.0", "3", 0.0), ("100.0", "3", 10.0)])
        for r in rows:
            target = float(r["outer_target_field_g"])
            self.assertAlmostEqual(float(r["measured_field_g"]), target, delta=2.0, msg="within the tolerance")
            self.assertAlmostEqual(float(r["kepco_programmed_current_a"]), target / 100.0, delta=0.02)
        # The current is not touched during a field's sweep: the two points of a step have one current.
        for first, second in zip(rows[::2], rows[1::2]):
            self.assertEqual(first["kepco_programmed_current_a"], second["kepco_programmed_current_a"])
        self.assertEqual({r["scan_mode"] for r in rows}, {"Angle+Field"})
        self.assertEqual(list(rows[0])[-5:], ["field_drift_g", "outer_target_field_g", "outer_field_index",
                                              "magnet_supply", "magnet_measured_current_a"])
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; KEPCO and 6221 zeroed; stage at +10.000°")
        events = self.events(h)
        programmed = [e for e in events if e["event"] == "field_programmed"]
        self.assertEqual([(e["step_index"], e["steps"], e["target_field_g"], e["tolerance_g"]) for e in programmed],
                         [(1, 3, 100.0, 2.0), (2, 3, 20.0, 2.0), (3, 3, 100.0, 2.0)])
        for e in programmed:
            self.assertAlmostEqual(e["field_g"], e["target_field_g"], delta=2.0)
        prepared = events[0]
        self.assertEqual(prepared["mode"], "Angle+Field")
        self.assertEqual({k: prepared["outer"][k] for k in ("typed", "unit", "tolerance_g", "steps", "values")},
                         {"typed": "100, 20 100", "unit": "G (LS475 target)", "tolerance_g": 2.0, "steps": 3,
                          "values": [100.0, 20.0, 100.0]})
        self.assertEqual(prepared["kepco"], {"current_a": "found for each outer field", "voltage_limit_v": 5.0})
        self.assertEqual(events[-1]["outputs"], {"6221": "zeroed", "kepco": "zeroed"})
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker}, "all on the worker")
        self.assert_closed(h)
        drawn = next(c for c in reversed(h.draw.call_args_list) if c.args[1])
        self.assertEqual({" ".join(name.split(" ")[1:3]) for name in drawn.args[1]},
                         {"#1 +100", "#2 +20", "#3 +100"})

    def test_angle_field_refuses_a_bad_list_before_anything_moves(self):
        for typed, message in (("", "Outer field G: type the fields in G in the order to scan"),
                               ("100, 7400", "fields must stay within +/-7300 G (7300 Oe); 7400 G is outside"),
                               ("100, a", 'Outer field G: "a" is not a number')):
            with self.subTest(typed=typed):
                h = self.make_field_list(typed)
                self.start(h)
                h.askyesno.assert_not_called()
                self.assertIn(message, h.showerror.call_args.args[1])
                self.assertEqual([e for e in h.log if e[0] in ("kepco", "stage", "6221")], [], "nothing sent")
        h = self.make_field_list("100")
        h.panel.rte_field_tolerance.set("0")
        self.start(h)
        h.askyesno.assert_not_called()
        self.assertIn("The field tolerance must be above 0 G", h.showerror.call_args.args[1])

    def test_angle_field_refuses_a_kepco_already_on(self):
        """Review, 2026-11-17: an output left on (Apply, Set field, a stopped
        scan) would keep its old voltage limit; the scan asks for Zero / OFF
        first and sends nothing."""
        h = self.make_field_list("100")
        h.kepco.output_owned, h.kepco.cached_current_a, h.kepco.active_mode = True, 0.7, "CURR"
        self.start(h)
        h.askyesno.assert_not_called()
        self.assertIn("The KEPCO output is on", h.showerror.call_args.args[1])
        self.assertIn("press KEPCO Zero / OFF first", h.showerror.call_args.args[1])
        self.assertEqual([e for e in h.log if e[0] in ("kepco", "stage", "6221")], [], "nothing sent")

    def test_angle_field_a_field_that_does_not_follow_fails_and_zeroes(self):
        h = self.make_field_list("100", gauss_class=StuckGauss)
        self.start(h)
        panel = h.panel
        self.assertTrue(panel.ppms_field_scan_status_var.get().startswith("Failed:"),
                        panel.ppms_field_scan_status_var.get())
        self.assertEqual(self.rows(h), [], "no point read")
        self.assertFalse([e for e in h.log if e[:2] == ("stage", "move")], "the stage not turned")
        self.assertIn(("kepco", "force_off"), [e[:2] for e in h.log])
        self.assertEqual(self.events(h)[-1]["outputs"], {"6221": "zeroed", "kepco": "zeroed"})
        # Failed for the field, not for anything else: the gaussmeter is named.
        self.assertIn("gaussmeter", h.showerror.call_args.args[1] if h.showerror.called
                      else panel.ppms_field_scan_status_var.get())

    def test_angle_field_stop_while_the_field_is_found(self):
        h = self.make_field_list("100")
        reads = []

        class StopsGauss(FollowingGauss):
            def read_field(gauss_self):
                reads.append(1)
                if len(reads) == 6:
                    h.panel.stop_ppms_field_scan()
                return super().read_field()
        h.gauss = StopsGauss(h.log, h.kepco)
        h.panel.rte_controllers["gauss"] = h.gauss
        self.start(h)
        panel = h.panel
        self.assertTrue(panel.ppms_field_scan_status_var.get().startswith("Stopped"),
                        panel.ppms_field_scan_status_var.get())
        self.assertEqual(self.rows(h), [])
        self.assertFalse([e for e in h.log if e[:2] == ("stage", "move")])
        self.assertIn(("kepco", "force_off"), [e[:2] for e in h.log])

    def test_angle_current_steps_the_6221_outside_the_angle_sweep(self):
        h = self.make_outer("Angle+Current", ("0.5", "1.5", "0.5"))
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV Angle+Current scan")
        self.assertIn("the KEPCO is set once to +1.5 A (voltage limit 5 V)", question)
        settle = [("gauss", "read")] * app.STFMR_FIELD_SETTLE_REQUIRED_SAMPLES
        # The 6221 on at the first current, the field set once and settled,
        # then per current its amplitude (the first point read with the
        # agreeing windows) and the sweep from the first angle.
        expected = [("6221", "on", 0.5), ("kepco", "set_output", "CURR")] + settle
        expected += self.point(0.0, first=True) + self.point(10.0)
        for value in (1.0, 1.5):
            expected += [("6221", "current", value)] + self.point(0.0, first=True) + self.point(10.0)
        self.assertEqual(self.sequence(h), expected + ZEROED)
        self.assertEqual([e[2:5] for e in h.log if e[:2] == ("kepco", "set_output")], [("CURR", 1.5, 5.0)])
        # The 6221's range is fixed for the largest current, as a Current scan's.
        peak = 2 ** .5 * 1.5 * 1e-3
        self.assertEqual({round(s["continuous_sweep_peak_a"], 12) for s in h.configured + h.updated},
                         {round(peak, 12)})
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})
        rows = self.rows(h)
        self.assertEqual([(float(r["6221_current_rms_ma"]), float(r["stage_angle_deg"]), r["outer_current_index"],
                           r["first_point_windows"]) for r in rows],
                         [(.5, 0., "1", "2"), (.5, 10., "1", "1"), (1., 0., "2", "2"), (1., 10., "2", "1"),
                          (1.5, 0., "3", "2"), (1.5, 10., "3", "1")])
        # The magnet supply's two columns after them since 2026-10-21 (user).
        self.assertEqual(list(rows[0])[-4:], ["field_drift_g", "outer_current_index", "magnet_supply",
                                              "magnet_measured_current_a"])
        self.assertEqual({r["kepco_programmed_current_a"] for r in rows}, {"1.5"})
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; KEPCO and 6221 zeroed; stage at +10.000°")
        events = self.events(h)
        expected_events = ["run_prepared", "scan_started", "harmonic_pass", "current_programmed", "field_programmed",
                           "field_settled", "stage_move", "point_saved", "stage_move", "point_saved"]
        for _current in range(2):
            expected_events += ["current_programmed", "stage_move", "point_saved", "stage_move", "point_saved"]
        self.assertEqual(self.without_notes(events),
                         expected_events + ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual([(e["step_index"], e["current_rms_ma"]) for e in events if e["event"] == "current_programmed"],
                         [(1, .5), (2, 1.), (3, 1.5)])
        prepared = events[0]
        self.assertEqual((prepared["outer"]["values"], prepared["outer"]["unit"]), ([.5, 1., 1.5], "mA RMS (6221)"))
        self.assertEqual(prepared["kepco"], {"current_a": 1.5, "voltage_limit_v": 5.0, "held": True})
        self.assert_closed(h)
        drawn = next(c for c in reversed(h.draw.call_args_list) if c.args[1])
        self.assertEqual({" ".join(name.split(" ")[1:3]) for name in drawn.args[1]}, {"0.5 mA", "1 mA", "1.5 mA"})

    def test_angle_current_stop_mid_move_and_a_6221_step_failure(self):
        h = self.make_outer("Angle+Current", ("0.5", "1", "0.5"), span=("0", "90", "90"))
        panel = h.panel
        h.move_hooks[90.0] = lambda: h.clock.hooks.append((h.clock.t + 3.0, panel.stop_ppms_field_scan))
        self.start(h)
        h.showerror.assert_not_called()
        self.assertTrue(panel.ppms_field_scan_status_var.get().startswith(
            "Stopped; KEPCO and 6221 zeroed; stage stopped at +"))
        self.assertNotIn(("6221", "current"), self.names(h, "6221"), "the next current never set")
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        # A 6221 step that fails: the scan fails, both are zeroed, the stage stays.
        h = self.make_outer("Angle+Current", ("0.5", "1", "0.5"))
        h.panel._update_ppms_transport_current = Mock(side_effect=RuntimeError("6221 live amplitude readback mismatch"))
        self.start(h)
        self.assertTrue(h.panel.ppms_field_scan_status_var.get().startswith("Failed: 6221 live amplitude"))
        self.assertEqual(self.names(h, "kepco", "6221"),
                         [("6221", "on"), ("kepco", "set_output"), ("6221", "off")] + ZEROED)
        self.assertEqual([e[2] for e in h.log if e[:2] == ("stage", "move")], [0.0, 10.0])
        self.assertEqual(self.events(h)[-1]["outputs"], {"6221": "zeroed", "kepco": "zeroed"})

    def make_field_angle(self, typed, span=("-1", "1", "1"), trip=False, **kwargs):
        """A Field+Angle scan (user, 2026-11-22): the typed stage angles
        outside, the KEPCO's currents of ``span`` at each, with an LS475
        that reads 100 G per A of the KEPCO's current."""
        h = self.make(span=span, round_trip=False, **kwargs)
        panel = h.panel
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Field+Angle")
            panel._rte_mode_changed()
        self.assertIs(panel.rte_round_trip.get(), True, "a field sweep goes and comes back by default")
        panel.rte_round_trip.set(trip)
        for variable, value in zip(panel.ppms_simple_range, span):
            variable.set(value)
        panel.rte_outer_ranges["Field+Angle"][0].set(typed)
        h.gauss = FollowingGauss(h.log, h.kepco)
        panel.rte_controllers["gauss"] = h.gauss
        h.configured = []

        def configure(settings):
            h.configured.append(dict(settings))
            h.log.append(("6221", "on", settings["current_rms_ma"], settings["frequency_hz"], threading.get_ident()))
        panel._configure_ppms_transport_scan = configure
        h.log.clear()
        return h

    def test_field_angle_sweeps_the_field_at_each_typed_angle(self):
        """User, 2026-11-22: "add a Field+Angle scan mode ..., like
        Angle+Field but the Angle is the outer loop and text input": the
        stage turns to each typed angle, then the Field scan's sweep runs
        there; the rows are plotted against the measured field, a curve per
        angle."""
        h = self.make_field_angle("0, 10")
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV Field+Angle scan")
        for text in ("Stage angle, the OUTER loop: 2 angles in the order typed: +0, +10°.",
                     "KEPCO current at each angle, the INNER loop: from -1 A to +1 A (step 1 A), 3 currents a loop, "
                     "1 loop(s) (voltage limit 5 V",
                     "2 angles x 3 currents x 1 harmonic pass(es) = 6 points.",
                     "2 stage moves, 10° of turning in all after the first.",
                     "the 6221 and then the KEPCO are zeroed; the stage stays where the scan left it",
                     "SAMPLE HOLDER with its wires attached", "Can the wires follow?"):
            self.assertIn(text, question)
        # The stage first, then that angle's sweep; the output switched on
        # once, with the voltage limit, at the sweep's first current.
        calls = [e[:3] for e in h.log if e[:2] in (("stage", "move"), ("kepco", "set_output"),
                                                    ("kepco", "set_scan_current"))]
        self.assertEqual(calls, [("stage", "move", 0.0), ("kepco", "set_output", "CURR"),
                                 ("kepco", "set_scan_current", 0.0), ("kepco", "set_scan_current", 1.0),
                                 ("stage", "move", 10.0), ("kepco", "set_scan_current", -1.0),
                                 ("kepco", "set_scan_current", 0.0), ("kepco", "set_scan_current", 1.0)])
        self.assertEqual([e[2:5] for e in h.log if e[:2] == ("kepco", "set_output")], [("CURR", -1.0, 5.0)])
        self.assertEqual(len([e for e in h.log if e[:2] == ("6221", "on")]), 1)
        rows = self.rows(h)
        self.assertEqual([(r["scan_mode"], r["outer_angle_index"], float(r["stage_target_deg"]),
                           float(r["stage_angle_deg"]), float(r["kepco_programmed_current_a"])) for r in rows],
                         [("Field+Angle", index, angle, angle, current)
                          for index, angle in (("1", 0.0), ("2", 10.0)) for current in (-1.0, 0.0, 1.0)])
        for r in rows:
            self.assertAlmostEqual(float(r["measured_field_g"]), 100.0 * float(r["kepco_programmed_current_a"]))
            self.assertEqual(r["kepco_voltage_limit_v"], "5.0")
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; KEPCO and 6221 zeroed; stage at +10.000°")
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        events = self.events(h)
        self.assertEqual([(e["step_index"], e["steps"], e["target_deg"]) for e in events if e["event"] == "stage_move"],
                         [(1, 2, 0.0), (2, 2, 10.0)])
        self.assertEqual([e["x_column"] for e in events if e["event"] == "point_saved"], ["measured_field_g"] * 6)
        prepared = events[0]
        self.assertEqual((prepared["mode"], prepared["plan"]["unit"], prepared["plan"]["points"]),
                         ("Field+Angle", "A (KEPCO)", 3))
        self.assertEqual(prepared["outer"], {"typed": "0, 10", "unit": "deg (stage)", "steps": 2, "values": [0.0, 10.0],
                                             "order": "outer first, in the order typed; the field sweep inner"})
        self.assertEqual(prepared["kepco"], {"current_a": "the plan", "voltage_limit_v": 5.0})
        self.assertIn("stage_at_start", prepared)
        self.assertEqual(events[-1]["outputs"], {"6221": "zeroed", "kepco": "zeroed"})
        self.assertEqual(events[-1]["stage"], "stage at +10.000°")
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker}, "all on the worker")
        self.assert_closed(h)
        # The plots: against the measured field, a curve per typed angle.
        self.assertEqual(panel.ppms_plot_axis, "field")
        drawn = next(c for c in reversed(h.draw.call_args_list) if c.args[1])
        self.assertEqual(drawn.args[2], "Measured magnetic field (G)")
        self.assertEqual({" ".join(name.split(" ")[1:3]) for name in drawn.args[1]}, {"#1 +0°", "#2 +10°"})
        self.assertEqual({len(points) for points in drawn.args[1].values()}, {3})

    def test_field_angle_stop_stage_during_a_sweep_ends_the_scan_at_the_next_point(self):
        """Review, 2026-11-22: the stage only looks at Stop stage in a move,
        and Field+Angle moves once per angle; pressed during a sweep it
        ended nothing until the next angle, a whole sweep later."""
        h = self.make_field_angle("0, 10")
        panel = h.panel
        real_step = h.kepco.set_scan_current
        seen = []

        def step(value):
            real_step(value)
            if not seen:
                seen.append(value)
                panel.rte_stage_stop_event.set()      # Stop stage, during the first angle's sweep
        h.kepco.set_scan_current = step
        self.start(h)
        h.showerror.assert_not_called()
        self.assertEqual([e[2] for e in h.log if e[:2] == ("stage", "move")], [0.0], "no second angle")
        self.assertEqual([e[2] for e in h.log if e[:2] == ("kepco", "set_scan_current")], [0.0],
                         "the point in progress is read, no further current")
        self.assertEqual(len(self.rows(h)), 2)
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Stopped; KEPCO and 6221 zeroed; stage at +0.000°")
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        last = self.events(h)[-1]
        self.assertEqual((last["outcome"], last["stop_reason"]),
                         ("stopped", "SHHV stopped: Stop stage was pressed; stage at +0.000°"))

    def test_field_angle_refuses_a_bad_list_before_anything_moves(self):
        for typed, message in (("", "Outer stage °: type the stage angles in degrees in the order to scan"),
                               ("0, 400", "stage angles must stay within +/-360° of the stage zero (the sample wires); "
                                          "400° is outside"),
                               ("0, a", 'Outer stage °: "a" is not a number')):
            with self.subTest(typed=typed):
                h = self.make_field_angle(typed)
                self.start(h)
                h.askyesno.assert_not_called()
                self.assertEqual(h.showerror.call_args.args[0], "SHHV scan parameters")
                self.assertIn(message, h.showerror.call_args.args[1])
                self.assertEqual([e for e in h.log if e[0] in ("kepco", "stage", "6221")], [], "nothing sent")
        # A sweep current beyond the supply's limit, as a Field scan's.
        h = self.make_field_angle("0", span=("-11", "1", "1"))
        self.start(h)
        self.assertIn("KEPCO sweep current must stay within +/-10 A", h.showerror.call_args.args[1])
        self.assertEqual([e for e in h.log if e[0] in ("kepco", "stage", "6221")], [], "nothing sent")

    def make_field_current(self, typed, span=("-1", "1", "1"), trip=False, **kwargs):
        """A Field+Current scan (user, 2026-11-25): the typed 6221 read
        currents outside, the KEPCO's currents of ``span`` at each."""
        h = self.make(span=span, round_trip=False, **kwargs)
        panel = h.panel
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Field+Current")
            panel._rte_mode_changed()
        self.assertIs(panel.rte_round_trip.get(), True, "a field sweep goes and comes back by default")
        self.assertEqual(panel.rte_outer_ranges["Field+Current"][0].get(), "0.5, 1, 1.5, 2")
        panel.rte_round_trip.set(trip)
        for variable, value in zip(panel.ppms_simple_range, span):
            variable.set(value)
        panel.rte_outer_ranges["Field+Current"][0].set(typed)
        h.gauss = FollowingGauss(h.log, h.kepco)
        panel.rte_controllers["gauss"] = h.gauss
        h.configured, h.updated = [], []

        def configure(settings):
            h.configured.append(dict(settings))
            h.log.append(("6221", "on", settings["current_rms_ma"], settings["frequency_hz"], threading.get_ident()))

        def update(settings):
            h.updated.append(dict(settings))
            h.log.append(("6221", "current", settings["current_rms_ma"], threading.get_ident()))
        panel._configure_ppms_transport_scan = configure
        panel._update_ppms_transport_current = update
        h.log.clear()
        return h

    def test_field_current_sweeps_the_field_at_each_typed_6221_current(self):
        """User, 2026-11-25: "add field+current scan in the SHHV & Switch
        mode which I input current in the text and current is the larger
        cycle": the 6221 is set to each typed current, then the Field scan's
        sweep runs there; a curve per current against the measured field."""
        h = self.make_field_current("0.5, 2")
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV Field+Current scan")
        for text in ("6221 read current, the OUTER loop: 2 currents in the order typed: +0.5, +2 mA RMS.",
                     "KEPCO current at each 6221 current, the INNER loop: from -1 A to +1 A (step 1 A), 3 currents a loop",
                     "2 6221 currents x 3 KEPCO currents x 1 harmonic pass(es) = 6 points.",
                     "the 6221 and then the KEPCO are zeroed."):
            self.assertIn(text, question)
        self.assertNotIn("wires", question)
        calls = [e[:3] for e in h.log if e[0] == "6221" and e[1] in ("on", "current")
                 or e[:2] in (("kepco", "set_output"), ("kepco", "set_scan_current"))]
        self.assertEqual(calls, [("6221", "on", 0.5), ("kepco", "set_output", "CURR"),
                                 ("kepco", "set_scan_current", 0.0), ("kepco", "set_scan_current", 1.0),
                                 ("6221", "current", 2.0), ("kepco", "set_scan_current", -1.0),
                                 ("kepco", "set_scan_current", 0.0), ("kepco", "set_scan_current", 1.0)])
        self.assertEqual({s["continuous_sweep_peak_a"] for s in h.configured + h.updated}, {2 ** 0.5 * 2.0 * 1e-3})
        self.assertEqual([e for e in h.log if e[0] == "stage"], [], "the stage never moves")
        rows = self.rows(h)
        self.assertEqual([(r["scan_mode"], r["outer_current_index"], float(r["6221_current_rms_ma"]),
                           float(r["kepco_programmed_current_a"]), r["first_point_windows"]) for r in rows],
                         [("Field+Current", index, current, field, "2" if field == -1.0 else "1")
                          for index, current in (("1", 0.5), ("2", 2.0)) for field in (-1.0, 0.0, 1.0)])
        self.assertNotIn("stage_angle_deg", rows[0])
        for r in rows:
            self.assertAlmostEqual(float(r["measured_field_g"]), 100.0 * float(r["kepco_programmed_current_a"]))
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; KEPCO and 6221 zeroed")
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        events = self.events(h)
        self.assertEqual([(e["step_index"], e["current_rms_ma"]) for e in events if e["event"] == "current_programmed"],
                         [(1, 0.5), (2, 2.0)])
        self.assertEqual([e["x_column"] for e in events if e["event"] == "point_saved"], ["measured_field_g"] * 6)
        prepared = events[0]
        self.assertEqual((prepared["mode"], prepared["plan"]["unit"], prepared["plan"]["points"]),
                         ("Field+Current", "A (KEPCO)", 3))
        self.assertEqual(prepared["outer"], {"typed": "0.5, 2", "unit": "mA RMS (6221)", "steps": 2, "values": [0.5, 2.0],
                                             "order": "outer first, in the order typed; the field sweep inner"})
        self.assertEqual(prepared["source_6221"]["note"], "the outer loop gives the currents")
        self.assertEqual(prepared["kepco"], {"current_a": "the plan", "voltage_limit_v": 5.0})
        self.assertEqual(events[-1]["outputs"], {"6221": "zeroed", "kepco": "zeroed"})
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker}, "all on the worker")
        self.assert_closed(h)
        self.assertEqual(panel.ppms_plot_axis, "field")
        drawn = next(c for c in reversed(h.draw.call_args_list) if c.args[1])
        self.assertEqual(drawn.args[2], "Measured magnetic field (G)")
        self.assertEqual({" ".join(name.split(" ")[1:4]) for name in drawn.args[1]}, {"#1 0.5 mA", "#2 2 mA"})
        self.assertEqual({len(points) for points in drawn.args[1].values()}, {3})

    def test_field_current_refuses_a_bad_list_before_anything_is_sent(self):
        for typed, message in (("", "Outer 6221 mA RMS: type the 6221 read currents in mA RMS in the order to scan"),
                               ("0.5, a", 'Outer 6221 mA RMS: "a" is not a number'),
                               ("0.5, 0", "Outer 6221 mA RMS: the 6221 read currents must be greater than 0 mA RMS; 0 mA is not")):
            with self.subTest(typed=typed):
                h = self.make_field_current(typed)
                self.start(h)
                h.askyesno.assert_not_called()
                self.assertEqual(h.showerror.call_args.args[0], "SHHV scan parameters")
                self.assertIn(message, h.showerror.call_args.args[1])
                self.assertEqual([e for e in h.log if e[0] in ("kepco", "stage", "6221")], [], "nothing sent")

    def test_field_angle_stop_during_the_turn_to_the_second_angle(self):
        h = self.make_field_angle("0, 90")
        panel = h.panel
        # Stop 3 s into the move to 90°.
        h.move_hooks[90.0] = lambda: h.clock.hooks.append((h.clock.t + 3.0, panel.stop_ppms_field_scan))
        self.start(h)
        h.showerror.assert_not_called()
        status = panel.ppms_field_scan_status_var.get()
        self.assertTrue(status.startswith("Stopped; KEPCO and 6221 zeroed; stage stopped at +"), status)
        where = float(status.rsplit(" ", 1)[1].rstrip("°"))
        self.assertTrue(0 < where < 90, where)
        self.assertEqual(len(self.rows(h)), 3, "the first angle's sweep saved, nothing at the second")
        self.assertEqual([e[2] for e in h.log if e[:2] == ("kepco", "set_scan_current")], [0.0, 1.0],
                         "no current after the Stop")
        self.assertEqual(self.names(h, "kepco", "6221")[-3:], ZEROED)
        self.assertEqual(self.events(h)[-1]["outcome"], "stopped")
        self.assertFalse(h.stage.motion_may_run)

    def test_the_other_modes_are_unchanged_by_the_outer_row(self):
        # An Angle scan after an Angle+Current one: no outer column, one held field.
        h = self.make_outer("Angle+Current", ("0.5", "1", "0.5"))
        self.start(h)
        panel = h.panel
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Angle")
            panel._rte_mode_changed()
        for variable, value in zip(panel.ppms_simple_range, ("0", "10", "10")):
            variable.set(value)
        h.log.clear()
        self.start(h)
        rows = self.rows(h)
        self.assertEqual(list(rows[0])[-3:], ["field_drift_g", "magnet_supply", "magnet_measured_current_a"])
        self.assertEqual({r["scan_mode"] for r in rows}, {"Angle"})
        self.assertEqual([e[1] for e in h.log if e[0] == "kepco"], ["set_output", "force_off"])
        drawn = next(c for c in reversed(h.draw.call_args_list) if c.args[1])
        self.assertEqual(sorted(drawn.args[1]), ["Zurich P1 L1"], "one curve, named as before")
        self.assertNotIn("series_labels", drawn.kwargs)


def panel_current(panel):
    """The 6221 current the page's box holds (the Field and Angle scans' excitation)."""
    return float(panel.ppms_transport_current_var.get())


if __name__ == "__main__":
    unittest.main()
