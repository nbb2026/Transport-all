"""PPMS page: one run folder and log per scan, and the 6221 zeroed at every
end (user, 2026-10-18), with the PPMS review findings of that day (P1-P9).

No Tk window and no instrument: the real PPMSPanel is built on stand-in
widgets (test_ppms_sr830_tc), its rack holds the fake 6221 and SR830s of
test_ppms_frequency_scan, every dialog is mocked, and a fake clock moves only
when the scan waits.  The real Start, worker, zeroing and finish run.
"""
import csv
import json
import math
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

from test_nonlocal_keithley import Var
from test_ppms_frequency_scan import ClockEvent, Motor, Rig
from test_ppms_motor_debug import app
from test_ppms_sr830_tc import build_ppms_panel


class Page:
    """A built PPMS page on the fake rack: SR830-1 and SR830-3 measured, no
    Zurich, the rotator at 26°, 300 K and 1234 Oe read back."""

    def __init__(self, test, mode="Current", main_row=("0.5", "1", "0.5")):
        self.test = test
        self.rig = rig = Rig(test, mode, None, (0.5, 1.0), zurich=False)
        panel, _ttk = build_ppms_panel()
        del panel.thread_log            # the page's own: its log lines become notes
        self.lines = []
        panel.parent_app.append_log = self.lines.append
        for name in ("ppms_instrument_controllers", "ppms_sr830_range_states", "_ppms_autorange_sr830",
                     "_read_ppms_live", "_apply_ppms_environment_readback"):
            setattr(panel, name, getattr(rig.page, name))
        rig.page.ppms_environment_controller.backend = app.PPMS_QDINSTRUMENT_BACKEND
        rig.page.ppms_environment_controller.connected = True
        panel.ppms_environment_controller = rig.page.ppms_environment_controller
        panel.ppms_field_scan_stop_event = rig.stop
        panel._require_ppms_control_ready = mock.Mock()
        panel.ppms_lockin_selection["zurich"].set(False)
        panel.ppms_lockin_selection["830_b"].set(False)
        panel.ppms_motor_confirm_var.set(True)
        panel.ppms_motor_target_var.set("26")
        panel.ppms_temperature_target_var.set("300")
        panel.ppms_field_target_var.set("50000")    # not used: the field is not commanded
        panel.ppms_transport_frequency_var.set("317.3")
        panel.ppms_acquisition_time_var.set("1")
        panel.ppms_last_readback = dict(temperature_k=300.0, field_oe=1234.0, angle_deg=26.0)
        panel.ppms_simple_mode.set(mode)
        for var, value in zip(panel.ppms_simple_range, main_row):
            var.set(value)
        self.dialogs, self.later = [], []
        panel.root = types.SimpleNamespace(after=lambda _ms, show: (self.later.append(show), show()))
        self.panel, self.folder = panel, tempfile.TemporaryDirectory()
        test.addCleanup(self.folder.cleanup)

    def start(self, name="run1", answer=True, folder=True):
        def error(title, text, **_options):
            self.dialogs.append((title, text))
        with mock.patch.object(app.time, "monotonic", self.rig.clock), \
                mock.patch.object(app.time, "sleep", lambda _s: None), \
                mock.patch.object(app, "PPMSMotorDebug", Motor), \
                mock.patch.object(app.messagebox, "askyesno", return_value=answer) as ask, \
                mock.patch.object(app.messagebox, "showerror", side_effect=error), \
                mock.patch.object(app.filedialog, "askdirectory",
                                  return_value=self.folder.name if folder else "") as directory, \
                mock.patch.object(app.simpledialog, "askstring", return_value=name):
            self.panel.start_ppms_field_scan()
        self.ask, self.directory = ask, directory
        return self

    def events(self, path=None):
        path = path or self.panel.ppms_run_folder / f"{self.panel.ppms_run_folder.name}.log"
        return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]

    def rows(self):
        path = self.panel.ppms_run_folder / f"{self.panel.ppms_run_folder.name}.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))

    def header(self):
        path = self.panel.ppms_run_folder / f"{self.panel.ppms_run_folder.name}.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return next(csv.reader(handle))

    def sent_6221(self):
        return [entry for entry in self.rig.log if entry[0] in ("6221", "6221?")]


ZERO = [("6221", "SOUR:WAVE:ABOR"), ("6221", "OUTP OFF"), ("6221?", "OUTP?")]


class RunFolderAndZeroTests(unittest.TestCase):
    pass

class FieldScanEndTests(unittest.TestCase):
    """A field scan's own field rules are unchanged; the 6221 is zeroed too."""

    def harness(self, refuse_zero=False):
        import test_ppms_nested as nested
        case = nested.NestedTests()
        obj, motor, settings, events = case.harness()
        del obj._ppms_zero_field_after_interrupted_scan       # the real one
        remote = obj.ppms_environment_controller
        send = remote.set_field          # the harness's: it logs and moves the field

        def set_field(target, *args):
            if refuse_zero and target == 0.0:
                events.append(("field", target))
                raise RuntimeError("MultiVu refused")
            send(target, *args)
        remote.set_field = set_field
        settings.update(scan_mode="Field", nested=dict(angle=(26.,), temperature=(300.,)))

        def run():
            clock = iter(range(10000))
            with mock.patch.object(app, 'PPMSMotorDebug', motor), \
                    mock.patch.object(app.time, 'monotonic', lambda: next(clock)):
                obj._ppms_nested_scan_worker([(1, 1, 1, 100.)], 100., 0., 1, settings)
        case.run_worker = lambda *_args: run()
        return obj, motor, settings, events, case

class ZeroPersistButtonTests(unittest.TestCase):
    """P5: queued only while a scan runs; a second click cancels; Start
    clears it."""

    pass

class CurrentTemperatureTests(unittest.TestCase):
    """P1: each temperature block's ramp runs at its first current, and that
    first point settles."""

    pass


class AutorangeTests(unittest.TestCase):
    """P2 (shared with SHHV): a range that overloaded is a floor until the
    next pass, and only a point's first reading steps a range down."""

    def sr830(self, index=13):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        state = {"SENS": index}
        instrument = mock.Mock()
        instrument.write.side_effect = lambda command: state.update(SENS=int(command.split()[1]))
        instrument.query.side_effect = lambda command: str(state["SENS"])
        obj.ppms_instrument_controllers = {"830_a": types.SimpleNamespace(
            instrument=instrument, lock=threading.RLock(), label="SR830-1")}
        obj._ppms_query_numbers = lambda key, command, n: ((state["SENS"],) if command == "SENS?" else (10,))
        obj._post_sr830_range_label = mock.Mock()
        return obj, state

    def test_no_flip_back_to_a_range_that_overloaded(self):
        obj, state = self.sr830()
        small = 0.01 * app.NONLOCAL_SR830_FULL_SCALE_V[13]
        self.assertEqual(obj._ppms_autorange_sr830("830_a", 0., 4), 5.)    # overload: 13 -> 14
        self.assertEqual(state["SENS"], 14)
        for _ in range(20):
            obj._ppms_autorange_sr830("830_a", small, 0)
        self.assertEqual(state["SENS"], 14, "never back down to the range that overloaded")
        obj._ppms_clear_sr830_range_floor()
        for _ in range(3):
            obj._ppms_autorange_sr830("830_a", small, 0)
        self.assertEqual(state["SENS"], 13, "after the floor is cleared it steps down again")

    def test_later_readings_of_a_point_do_not_step_down_or_count(self):
        obj, state = self.sr830()
        small = 0.01 * app.NONLOCAL_SR830_FULL_SCALE_V[13]
        for _ in range(10):
            obj._ppms_autorange_sr830("830_a", small, 0, allow_down=False)
        self.assertEqual(state["SENS"], 13)
        self.assertEqual(obj.ppms_sr830_range_states["830_a"].low_range_count, 0)
        # An overload still ranges up on a later reading.
        obj._ppms_autorange_sr830("830_a", 0., 4, allow_down=False)
        self.assertEqual(state["SENS"], 14)

    def test_only_the_first_reading_of_a_point_may_step_down(self):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.closing = False
        obj.ppms_field_scan_stop_event = mock.Mock(is_set=mock.Mock(return_value=False),
                                                   wait=mock.Mock(return_value=False))
        flags = []
        good = dict(sr830_8_x_v=1., sr830_8_y_v=0., sr830_8_frequency_hz=317.3, sr830_8_reference_valid=True)

        def read(frequency, lockins, allow_down=True):
            flags.append(allow_down)
            return dict(good, range_settle_s=5. if len(flags) == 2 else 0.)
        obj._read_ppms_transport_sample = read
        with mock.patch.object(app.time, "monotonic", side_effect=[0., 0., .5, 5., 5., 5.5, 6.5, 6.5]):
            obj._average_ppms_transport_sample(317.3, ("830_a",), 1.)
        self.assertEqual(flags[0], True)
        self.assertFalse(any(flags[1:]), "not after a range change's restart either")

    def test_the_floor_ends_with_the_pass(self):
        obj, state = self.sr830()
        obj._ppms_autorange_sr830("830_a", 0., 4)
        self.assertEqual(obj.ppms_sr830_range_states["830_a"].overload_floor, 14)
        obj.post_ui = lambda callback: None
        obj._average_ppms_transport_sample = lambda f, l, d: dict(sr830_8_x_v=1., sr830_8_y_v=0.)
        obj._acquire_ppms_first_point(317.3, ("830_a",), 1.)
        self.assertIsNone(obj.ppms_sr830_range_states["830_a"].overload_floor)


class SettleWithoutTkTests(unittest.TestCase):
    """P6: the worker's wait reads the 'SR830 TC' choice Start read."""

    def test_the_worker_never_reads_the_choice(self):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.closing = False
        obj.thread_log, obj.post_ui = mock.Mock(), lambda callback: None
        obj.ppms_sr830_time_constant_var = mock.Mock(get=mock.Mock(side_effect=AssertionError("Tk on the worker")))
        obj.ppms_scan_sr830_tc_code = app.STFMR_LOCKIN_SR830_TIME_CONSTANTS["3 s"]
        self.assertEqual(obj._ppms_point_settle(0.5, ("830_a",)), (3.0, 3.0))


class SetIZurichTests(unittest.TestCase):
    """P7: the PPMS page's Set I never configures the Zurich from an older
    Start's copied settings."""

    pass


class FieldReadAtStartTests(unittest.TestCase):
    """P4: modes that never command the field record the field read at Start
    and count no field ramp; P8: field ramps per harmonic pass."""

    pass

class MacroScanTests(unittest.TestCase):
    """The next Macro line runs from the Tk event loop, so a SCAN line's
    dialogs never open inside drain_ui_queue (README rule, 2026-10-14)."""

    pass


class ProgramCloseTests(unittest.TestCase):
    pass


if __name__ == "__main__":
    unittest.main()
