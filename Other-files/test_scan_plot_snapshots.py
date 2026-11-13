"""Every scan saves a picture of its plots when it ends (user, 2026-11-13:
"all program when finish scanning, auto save the screenshot of axis plot").

Gate-VI did already; MOKE magnet and MOKE-24 saved one only with their
"Save CSV + PNG" button.  Now also MOKE magnet, MOKE-24, PPMS, SHV, FMR's
field scan and frequency sweep, ST-FMR, and Non-local's 2400-IV, 6221-IV
and |R| vs time, all through save_scan_plot_snapshots:

- the file is <run folder>/<run name>_plot_snapshot.png for a page with one
  plot, <run name>_plots_snapshot.png (one picture of the plot box) for a
  page with a grid of plots; never over another file;
- it is taken in the finish before the run log is closed, so the log's
  plot_snapshots entry comes just before run_finished;
- nothing is taken without a saved point, without a run folder, while the
  program closes, or on a page whose plots are not built;
- a failure (the page is not the one shown) never stops the finish: the log
  says why, and so does Non-local's status line.

And the FMR page's start-up connections (user, the same day, from a picture
of the page): LS648 at GPIB0::15, LS475 at GPIB0::12, PNA at GPIB0::16.

Window-free: tkinter.Tk raises, and the screen grab is replaced by one that
records what it was asked to save and writes a small file."""
import threading
import unittest
from pathlib import Path
from unittest import mock

import test_fmr_scan_run as fmr_runs
import test_moke_cidwm_runs as moke_runs
import test_nonlocal_scan_runs as nonlocal_runs
import test_ppms_run_save_zero as ppms_runs
import test_rte_angle_end_to_end as shv_runs
import test_stfmr_scan_convention as stfmr_runs
from test_nonlocal_keithley import bare_app
from test_ppms_motor_debug import app

NOT_SHOWN = "The plot is not visible; cannot capture a snapshot"


def setUpModule():
    # The SHV page's guards: no real DLL, no window.
    shv_runs.setUpModule()


def tearDownModule():
    shv_runs.tearDownModule()


class Grabs:
    """In place of save_plot_canvas_snapshot (the screen grab): what it was
    asked to save, in order, each written as a small file; a widget in
    ``hidden`` fails as a plot that is not on the screen does."""

    def __init__(self, test, hidden=()):
        self.calls, self.hidden = [], list(hidden)
        # The ST-FMR harness loads the program a second time (its own module).
        for program in {id(module): module for module in (app, stfmr_runs.app)}.values():
            patcher = mock.patch.object(program.CombinedControlApp, "save_plot_canvas_snapshot",
                                        lambda page, widget, path: self.grab(widget, path))
            patcher.start()
            test.addCleanup(patcher.stop)

    def grab(self, widget, path):
        self.calls.append((widget, Path(path)))
        if any(widget is item for item in self.hidden):
            raise RuntimeError(NOT_SHOWN)
        Path(path).write_bytes(b"PNG")

    def names(self):
        return [path.name for _widget, path in self.calls]


def last_events(recorder_or_events, count=3):
    events = (recorder_or_events if isinstance(recorder_or_events, list)
              else nonlocal_runs.events(recorder_or_events))
    return [event["event"] for event in events if event["event"] != "note"][-count:]


def snapshot_event(events):
    (event,) = [event for event in events if event["event"] == "plot_snapshots"]
    return event


# --------------------------------------------------------------- the routine
class RoutineTests(nonlocal_runs.NoWindows):
    def setUp(self):
        super().setUp()
        self.a = bare_app()
        self.a.closing = False
        self.a.root = mock.Mock()
        self.log = []
        self.a.thread_log = self.log.append
        self.recorder = app.ScanRunRecorder(self.folder, "PAGE", "run", {}, label="Page")
        self.addCleanup(lambda: self.recorder.close("completed"))
        self.grabs = Grabs(self)

    def test_each_plot_is_saved_under_the_runs_name_after_a_redraw(self):
        canvas, box = object(), object()
        order = []
        self.grabs.grab = lambda widget, path, real=self.grabs.grab: (order.append("grab"), real(widget, path))
        note = self.a.save_scan_plot_snapshots(
            self.recorder, (("plot", canvas), ("plots", box)), points=4, redraw=lambda: order.append("redraw"))
        self.assertEqual(note, "")
        self.assertEqual(order, ["redraw", "grab", "grab"], "the last point is drawn before the pictures")
        folder = self.folder / "run"
        self.assertEqual(self.grabs.calls, [(canvas, folder / "run_plot_snapshot.png"),
                                            (box, folder / "run_plots_snapshot.png")])
        self.assertEqual(sorted(path.name for path in folder.iterdir()),
                         ["run.csv", "run.log", "run_plot_snapshot.png", "run_plots_snapshot.png"])
        event = snapshot_event(nonlocal_runs.events(self.recorder))
        self.assertEqual((event["saved"], event["files"], event["error"]),
                         (True, ["run_plot_snapshot.png", "run_plots_snapshot.png"], ""))
        self.assertEqual(self.log, ["Page plot snapshot: run_plot_snapshot.png, run_plots_snapshot.png saved"])

    def test_a_name_in_use_is_never_overwritten(self):
        taken = self.folder / "run" / "run_plot_snapshot.png"
        taken.write_bytes(b"an earlier picture")
        self.a.save_scan_plot_snapshots(self.recorder, (("plot", object()),))
        self.assertEqual(self.grabs.names(), ["run_plot_snapshot_01.png"])
        self.assertEqual(taken.read_bytes(), b"an earlier picture")

    def test_a_plot_that_is_not_shown_is_reported_and_the_others_still_saved(self):
        hidden, shown = object(), object()
        self.grabs.hidden.append(hidden)
        note = self.a.save_scan_plot_snapshots(self.recorder, (("plot", hidden), ("plots", shown)))
        self.assertEqual(note, f"; plot snapshot save failed: plot: {NOT_SHOWN}")
        self.assertEqual(self.grabs.names(), ["run_plot_snapshot.png", "run_plots_snapshot.png"])
        self.assertFalse((self.folder / "run" / "run_plot_snapshot.png").exists())
        event = snapshot_event(nonlocal_runs.events(self.recorder))
        self.assertEqual((event["saved"], event["files"], event["error"]),
                         (False, ["run_plots_snapshot.png"], f"plot: {NOT_SHOWN}"))
        self.assertEqual(self.log, [f"Page plot snapshot: run_plots_snapshot.png saved; save failed: plot: {NOT_SHOWN}"])

    def test_nothing_without_a_point_a_run_folder_a_plot_or_while_closing(self):
        plots = (("plot", object()),)
        closed = app.ScanRunRecorder(self.folder, "PAGE", "closed", {}, label="Page")
        closed.close("completed")
        cases = (
            ("no run folder", dict(recorder=None, plots=plots)),
            ("the run log already closed", dict(recorder=closed, plots=plots)),
            ("no saved point", dict(recorder=self.recorder, plots=plots, points=0)),
            ("the plots not built", dict(recorder=self.recorder, plots=(("plot", None), ("plots", None)))),
        )
        for label, case in cases:
            with self.subTest(label):
                self.assertEqual(self.a.save_scan_plot_snapshots(case.pop("recorder"), case.pop("plots"), **case), "")
        self.a.closing = True
        self.assertEqual(self.a.save_scan_plot_snapshots(self.recorder, plots), "", "the program is closing")
        self.assertEqual(self.grabs.calls, [])
        self.assertNotIn("plot_snapshots", last_events(self.recorder, 10))
        self.assertEqual(self.log, [])

    def test_it_never_raises(self):
        """A finish goes on to its status and its buttons whatever the
        picture does: a redraw, a page log or a page that fail are passed."""
        def failing():
            raise RuntimeError("redraw failed")
        self.a.thread_log = mock.Mock(side_effect=RuntimeError("log failed"))
        self.assertEqual(self.a.save_scan_plot_snapshots(self.recorder, (("plot", object()),), redraw=failing), "")
        self.assertEqual(self.grabs.names(), ["run_plot_snapshot.png"], "saved as shown")
        # A page made without __init__ (no closing flag), as the unit tests make it.
        bare = bare_app()
        self.assertEqual(bare.save_scan_plot_snapshots(self.recorder, (("plot", object()),)), "")
        self.assertEqual(self.a.save_scan_plot_snapshots(self.recorder, None), "")


# ----------------------------------------------------------------- Non-local
class NonLocalTests(nonlocal_runs.NoWindows):
    def test_2400_iv_saves_its_plot_before_the_log_is_closed(self):
        grabs = Grabs(self)
        nonlocal_runs.SweepRunTests.make(self)
        canvas = self.a.nonlocal_iv_canvas = object()
        nonlocal_runs.SweepRunTests.sweep(self)
        self.a._redraw_nonlocal_iv_plot.assert_called()
        name = self.recorder.directory.name
        self.assertEqual(grabs.calls, [(canvas, self.recorder.directory / f"{name}_plot_snapshot.png")])
        self.assertEqual(last_events(self.recorder), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual(snapshot_event(nonlocal_runs.events(self.recorder))["files"], [f"{name}_plot_snapshot.png"])
        self.assertEqual(self.a.nonlocal_vi_status_var.get(),
                         f"2400-IV: Completed; Keithley 2400 and 6221 zeroed; 3 points saved in {name}")
        self.assertTrue(self.recorder.closed)

    def test_a_2400_iv_plot_that_is_not_shown_is_on_the_status_line_and_the_finish_goes_on(self):
        nonlocal_runs.SweepRunTests.make(self)
        canvas = self.a.nonlocal_iv_canvas = object()
        Grabs(self, hidden=[canvas])
        nonlocal_runs.SweepRunTests.sweep(self)
        self.assertEqual(self.a.nonlocal_vi_status_var.get(),
                         "2400-IV: Completed; Keithley 2400 and 6221 zeroed; 3 points saved in "
                         f"{self.recorder.directory.name}; plot snapshot save failed: plot: {NOT_SHOWN}")
        self.assertEqual(last_events(self.recorder), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual(nonlocal_runs.events(self.recorder)[-1]["outcome"], "completed")
        self.a._update_nonlocal_vi_controls.assert_called()
        self.assertIsNone(self.a.nonlocal_recorder)

    def test_a_2400_iv_sweep_without_a_point_saves_no_plot(self):
        grabs = Grabs(self)
        nonlocal_runs.SweepRunTests.make(self)
        self.a.nonlocal_iv_canvas = object()
        nonlocal_runs.SweepRunTests.sweep(self, read_error=RuntimeError("VI_ERROR_TMO"))
        self.assertEqual(grabs.calls, [])
        self.assertEqual(last_events(self.recorder, 2), ["outputs_zeroed", "run_finished"])

    def test_r_vs_time_saves_its_plot_at_the_stop(self):
        grabs = Grabs(self)
        log = []
        a = nonlocal_runs.keithley_page(nonlocal_runs.Meter(resistance_ohm=1e6), log)
        canvas = a.nonlocal_resistance_canvas = object()
        recorder = app.ScanRunRecorder(self.folder, "NL_RvsT", "", {}, label="|R| vs time")
        stop = a.nonlocal_keithley_stop_event
        post = a.post_ui

        def counting(callback):
            post(callback)
            if len(a.posted) > 8:
                stop.set()
                a.nonlocal_keithley_task = "resistance"
                a.stop_nonlocal_keithley_task("Stop measurement")

        a.post_ui = counting
        with mock.patch.object(stop, "wait", side_effect=lambda timeout=None: stop.is_set()):
            future = nonlocal_runs.run_job(a, recorder, "resistance", lambda: a._nonlocal_resistance_worker(recorder))
        a.nonlocal_keithley_task = "resistance"
        a._finish_nonlocal_resistance(future)
        name = recorder.directory.name
        self.assertEqual(grabs.calls, [(canvas, recorder.directory / f"{name}_plot_snapshot.png")])
        self.assertEqual(last_events(recorder), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertNotIn("plot snapshot", a.nonlocal_vi_status_var.get())

    def test_6221_iv_saves_one_picture_of_its_plot_box(self):
        grabs = Grabs(self)
        # As IV6221RunTests' setUp: no waiting.
        for name in ("NONLOCAL_IV6221_FIRST_SETTLE_TAUS", "LOCKIN_SETTLE_TAUS", "NONLOCAL_IV6221_REFERENCE_WAIT_S"):
            patcher = mock.patch.object(app, name, 0.0)
            patcher.start()
            self.addCleanup(patcher.stop)
        box, make = object(), nonlocal_runs.iv6221_page

        def page(*args, **kwargs):
            a = make(*args, **kwargs)
            a.nonlocal_iv6221_plot_container = box
            return a

        with mock.patch.object(nonlocal_runs, "iv6221_page", page):
            a, recorder, _keithley = nonlocal_runs.IV6221RunTests.run_scan(self, nonlocal_runs.FakeSource())
        name = recorder.directory.name
        self.assertEqual(grabs.calls, [(box, recorder.directory / f"{name}_plots_snapshot.png")])
        self.assertEqual(last_events(recorder), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertTrue(a.nonlocal_vi_status_var.get().endswith(f"saved in {name}"), a.nonlocal_vi_status_var.get())


# ----------------------------------------------------------------------- MOKE
class MokeTests(moke_runs.Folder):
    def test_the_current_scan_draws_the_scan_for_its_picture_then_the_pages_plot_again(self):
        grabs = Grabs(self)
        recorder = self.recorder("MOKE")
        a = moke_runs.MagnetScanRunTests.page(self, recorder)
        # The stand-in page takes its methods by name (after Grabs, so the grab is the stand-in).
        moke_runs.bind(a, "save_plot_canvas_snapshot")
        canvas = a.moke_plot_canvas = object()
        a.magnet_scan_settings = {"scan.channel_key": "OUT"}
        a.moke_plot_override = None
        drawn = []
        a._redraw_moke_plot = lambda: drawn.append(a.moke_plot_override)
        shown = moke_runs.MagnetScanRunTests.run_scan(self, a)
        shown.assert_not_called()
        self.assertEqual(grabs.calls, [(canvas, self.folder / "B1" / "B1_plot_snapshot.png")])
        # Drawn for the picture: the scan's channel and its two points
        # (elapsed, set current, read current, field, ROI); then what the page shows.
        self.assertEqual(len(drawn), 2)
        key, rows = drawn[0]
        self.assertEqual((key, len(rows), {len(row) for row in rows}), ("OUT", 2, {5}))
        self.assertIsNone(drawn[1])
        self.assertIsNone(a.moke_plot_override)
        events = moke_runs.log_events(recorder)
        self.assertEqual(last_events(events), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual(snapshot_event(events)["files"], ["B1_plot_snapshot.png"])
        self.assertEqual(a.magnet_status_var.get(),
                         "Completed; Out-of-plane KEPCO zeroed; In-plane KEPCO 0 A sent, not read back")

    def test_a_current_scan_whose_plot_is_not_shown_ends_as_before_with_the_pages_plot_back(self):
        recorder = self.recorder("MOKE")
        a = moke_runs.MagnetScanRunTests.page(self, recorder)
        canvas = a.moke_plot_canvas = object()
        Grabs(self, hidden=[canvas])
        moke_runs.bind(a, "save_plot_canvas_snapshot")
        a.magnet_scan_settings = {"scan.channel_key": "OUT"}
        a.moke_plot_override = None
        a._redraw_moke_plot = mock.Mock()
        moke_runs.MagnetScanRunTests.run_scan(self, a).assert_not_called()
        self.assertIsNone(a.moke_plot_override)
        self.assertEqual(a._redraw_moke_plot.call_count, 2)
        events = moke_runs.log_events(recorder)
        self.assertEqual(snapshot_event(events)["error"], f"plot: {NOT_SHOWN}")
        self.assertEqual((events[-1]["outcome"], events[-1]["points_saved"]), ("completed", 2))
        self.assertTrue(recorder.closed)

    def test_the_moke_24_scan_saves_its_plot(self):
        grabs = Grabs(self)
        recorder = self.recorder("MOKE24")
        a = moke_runs.Moke24RunTests.page(self, recorder)
        canvas = a.keithley_plot_canvas = object()
        a._redraw_keithley_plot = mock.Mock()
        a._keithley_scan_worker([1.0, 2.0, 1.0], 0.0, 0.0, None)
        moke_runs.Moke24RunTests.finish(self, a).assert_not_called()
        a._redraw_keithley_plot.assert_called()
        self.assertEqual(grabs.calls, [(canvas, self.folder / "B1" / "B1_plot_snapshot.png")])
        self.assertEqual(last_events(moke_runs.log_events(recorder)),
                         ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual(a.keithley_status_var.get(), "Completed; 2410 zeroed")


# ------------------------------------------------------------------------ FMR
class FmrTests(fmr_runs.FmrRun):
    def test_the_field_scan_saves_its_plot(self):
        grabs = Grabs(self)
        a = self.make()
        canvas = a.stfmr_fmr_canvas = object()
        a.stfmr_frequency_canvas = object()
        self.drive(a, a.start_stfmr_fmr_scan)
        run = self.folder / "run A"
        self.assertEqual(grabs.calls, [(canvas, run / "run A_plot_snapshot.png")])
        events = self.events(self.folder)
        self.assertEqual(last_events(events), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual(snapshot_event(events)["files"], ["run A_plot_snapshot.png"])
        self.assertEqual(a.stfmr_fmr_status_var.get(), "Completed; 4886 and RF zeroed; 6 points saved")
        self.assertEqual(sorted(p.name for p in run.iterdir()), ["run A.csv", "run A.log", "run A_plot_snapshot.png"])

    def test_the_frequency_sweep_saves_its_own_plot(self):
        grabs = Grabs(self)
        a = self.make()
        a.stfmr_fmr_canvas = object()
        canvas = a.stfmr_frequency_canvas = object()
        self.drive(a, a.start_stfmr_frequency_scan)
        self.assertEqual(grabs.calls, [(canvas, self.folder / "run A" / "run A_plot_snapshot.png")])
        self.assertEqual(last_events(self.events(self.folder)), ["outputs_zeroed", "plot_snapshots", "run_finished"])

    def test_a_plot_that_is_not_shown_leaves_the_scans_end_as_it_was(self):
        a = self.make()
        canvas = a.stfmr_fmr_canvas = object()
        Grabs(self, hidden=[canvas])
        self.drive(a, a.start_stfmr_fmr_scan)
        self.error.assert_not_called()
        events = self.events(self.folder)
        self.assertEqual((events[-1]["outcome"], events[-1]["status"]),
                         ("completed", "Completed; 4886 and RF zeroed; 6 points saved"))
        self.assertEqual(snapshot_event(events)["error"], f"plot: {NOT_SHOWN}")
        self.assertIn(("log", f"FMR plot snapshot: none saved; save failed: plot: {NOT_SHOWN}"), a.log)


# --------------------------------------------------------------------- ST-FMR
class StfmrTests(stfmr_runs.Sweep):
    def test_a_sweep_saves_one_picture_of_its_four_plots(self):
        grabs = Grabs(self)
        box, make = object(), stfmr_runs.harness

        def page(*args, **kwargs):
            h = make(*args, **kwargs)
            h.stfmr_lockin_plots_frame = box
            return h

        with mock.patch.object(stfmr_runs, "harness", page):
            h, recorder = self.start()
        h.root.drain()
        self.error.assert_not_called()
        self.assertEqual(grabs.calls, [(box, Path(self.tmp.name) / "run A" / "run A_plots_snapshot.png")])
        history = stfmr_runs.events(recorder)
        self.assertEqual([e["event"] for e in history][-4:],
                         ["outputs_zeroed", "note", "plot_snapshots", "run_finished"])
        self.assertEqual(history[-1]["status"], "Completed; 4886 and RF zeroed; 6 points saved; 2 frequencies")
        self.assertFalse(h.stfmr_lockin_running)


# ----------------------------------------------------------------------- PPMS
class PpmsTests(unittest.TestCase):
    def test_a_scan_saves_one_picture_of_its_plot_box(self):
        grabs = Grabs(self)
        page = ppms_runs.Page(self)
        box = page.panel.__dict__["ppms_plot_frame"]
        page.start()
        folder = page.panel.ppms_run_folder
        self.assertEqual(grabs.calls, [(box, folder / "run1_plots_snapshot.png")])
        events = page.events()
        self.assertEqual(last_events(events), ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertEqual((snapshot_event(events)["saved"], snapshot_event(events)["files"]),
                         (True, ["run1_plots_snapshot.png"]))
        self.assertEqual(page.panel.ppms_field_scan_status_var.get(), "Completed; 6221 zeroed")
        self.assertEqual(page.dialogs, [])
        self.assertTrue(page.panel.ppms_macro_scan_result, "a Macro goes on as before")


# ------------------------------------------------------------------------ SHV
class ShvTests(shv_runs.RunLogBase):
    def test_a_scan_saves_one_picture_of_its_plot_box(self):
        grabs = Grabs(self)
        h = self.make_mode("Current", ("0.5", "1.5", "0.5"))
        box = h.panel.__dict__["ppms_plot_frame"]
        self.start(h)
        h.showerror.assert_not_called()
        folder = h.panel.rte_run_folder
        self.assertEqual(grabs.calls, [(box, folder / f"{folder.name}_plots_snapshot.png")])
        events = self.events(h)
        self.assertEqual(self.without_notes(events)[-3:], ["outputs_zeroed", "plot_snapshots", "run_finished"])
        self.assertTrue(snapshot_event(events)["saved"])
        # From the Tk thread, as every finish.
        (writer,) = [thread for name, thread in h.writes if name == "plot_snapshots"]
        self.assertEqual(writer, threading.get_ident())
        self.assert_closed(h)


# ------------------------------------------------------- the FMR connections
class FmrDefaultTests(unittest.TestCase):
    def test_the_start_up_addresses_are_those_of_the_users_picture(self):
        self.assertEqual(app.LAKESHORE_MAGNET_MODELS["648"]["resource"], "GPIB0::15::INSTR")
        self.assertEqual(app.STFMR_DEFAULT_RESOURCES["gauss"], "GPIB0::12::INSTR")
        self.assertEqual(app.STFMR_DEFAULT_RESOURCES["vna"], "GPIB0::16::INSTR")
        self.assertEqual(app.STFMR_FMR_MAGNET_CHOICES[1], "LS648")
        # The LS643 of SHV and ST-FMR keeps its address.
        self.assertEqual(app.LAKESHORE_MAGNET_MODELS["643"]["resource"], "GPIB0::12::INSTR")


if __name__ == "__main__":
    unittest.main()
