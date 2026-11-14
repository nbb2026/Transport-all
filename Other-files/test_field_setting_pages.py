"""The "Set field" control of the FMR, ST-FMR and SHV pages (user,
2026-11-14: "Add a magnetic field setting in FMR, SHV, STFMR modules. You
can try to use PID to control the magnetic field value").

Each page steps its chosen magnet supply (the KEPCO 4886 or its Lake Shore)
until the LS475 reads the target within the tolerance, then keeps it there
(user, the same day: "keep regulating the field after it reaches the
target") until its button, "Stop hold" meanwhile, is pressed again (the
current stays) or Zero / OFF (test_magnet_field_set.py has the controller).
Here, per page:

- it needs the safety confirmation, the supply and the LS475 connected and
  the page idle, and refuses bad numbers before anything is sent;
- the page is busy while it runs and free again afterwards;
- Zero / OFF ends it and zeroes the supply, and no write follows the zero:
  also when it is pressed from the Tk thread while the worker is writing or
  reading, or while the job is still queued (review, 2026-11-14);
- the FMR page's 4886 is written from the Tk thread only, its session's rule;
- a target that cannot be reached leaves the current where it is and says so.

Window-free: tkinter.Tk raises, every dialog is a stand-in, no instrument,
no real waiting."""
import threading
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from unittest import mock

import test_fmr_scan_run as fmr_runs
import test_fmr_stfmr_review as review
import test_lakeshore_pages as ls_pages
import test_rte_angle_end_to_end as shv_runs
from test_lakeshore_magnet_supply import connected_supply
from test_magnet_field_set import Gauss, Instant
from test_nonlocal_keithley import Var
from test_ppms_motor_debug import app

SAFETY = "Please tick the magnet, cooling, wiring, limits and personnel safety confirmation first."
# The ST-FMR harness loads the program a second time, as its own module.
stfmr_app = ls_pages.stfmr_app
Variable = ls_pages.Variable


def stop_once_held(gauss, target, tolerance, press, readings=14):
    """Press the page's Stop hold after ``readings`` LS475 readings within
    the tolerance: the field was reached (a settled reading is two groups
    of three) and then read again while held."""
    read, inside, reads = gauss.read_field, [0], [0]

    def reading():
        reads[0] += 1
        if reads[0] > 3000:
            raise AssertionError("the hold did not end")       # a failure, never a hang
        result = read()
        if abs(app.STFMRGauss475Controller.value_in_gauss(result) - target) <= tolerance:
            inside[0] += 1
            if inside[0] == readings:
                press()
        return result
    gauss.read_field = reading
    return inside


def setUpModule():
    # The SHV page's guards: no real DLL, no window.
    shv_runs.setUpModule()
    # A second Set field right after one ended is these tests' own; the
    # wait a press needs after an end has its tests below.
    for program in {id(module): module for module in (app, stfmr_app)}.values():
        _patches.append(mock.patch.object(program, "MAGNET_FIELD_RESTART_LOCKOUT_S", 0.0))
        _patches[-1].start()


_patches = []


def tearDownModule():
    while _patches:
        _patches.pop().stop()
    shv_runs.tearDownModule()


# ------------------------------------------------------------------------ FMR
class FmrFieldTests(fmr_runs.FmrRun):
    def page(self, target="500", tolerance="1"):
        a = self.make()
        a.stfmr_closed = False
        a.stfmr_field_target_var, a.stfmr_field_tolerance_var = Var(target), Var(tolerance)
        a.stfmr_field_stop_event = Instant()
        a.stfmr_output_mode_var, a.stfmr_output_limit_var = Var("Current"), Var("5")
        a.busy_calls = []
        a._set_stfmr_scan_busy = lambda busy: a.busy_calls.append((busy, a.stfmr_magnet_job_pending))
        a.statuses = []
        show = a.stfmr_status_var.set
        a.stfmr_status_var.set = lambda text: (a.statuses.append(text), show(text))[1]
        # Held once reached: the page's button, pressed again, ends it.
        a.held = stop_once_held(a.stfmr_controllers["gauss"], float(target), float(tolerance), a.set_stfmr_field)
        return a

    def writes(self, a):
        return [entry[1] for entry in fmr_runs.sent(a) if entry[0] == "4886"]

    def test_the_kepco_is_stepped_until_the_475_reads_the_target(self):
        a = self.page()
        a.set_stfmr_field()
        self.error.assert_not_called()
        writes = self.writes(a)
        self.assertEqual(writes[:5], ["FUNC:MODE CURR", "CURR 0;VOLT 5", "VOLT:RANG:AUTO 1;CURR:RANG:AUTO 1",
                                      "OUTP ON", "CURR 0.000000"])
        self.assertTrue(all(write.startswith("CURR ") for write in writes[5:]))
        self.assertLessEqual(abs(300.0 * a.card.current - 500.0), 1.0)
        # Reached, then held (read again, nothing to correct) until Stop hold.
        holding = [text for text in a.statuses if text.startswith("Holding +500 ± 1 G: I +1.6")]
        self.assertGreaterEqual(len(holding), 2, a.statuses)
        self.assertEqual(a.statuses[-2:], ["Stopping the field regulation…",
                                           "Field regulation stopped; the 4886 is left at its last current"])
        self.assertEqual(writes[-1], f"CURR {a.card.current:.6f}", "the current stays where it held the field")
        self.assertFalse(a.stfmr_field_running)
        # The page was busy while it ran (the job counted) and is free again.
        self.assertEqual(a.busy_calls[0], (False, 1))
        self.assertEqual(a.busy_calls[-1], (False, 0))
        self.assertEqual(a.stfmr_magnet_job_pending, 0)
        # The panel shows what was sent, and the 475 box the last reading.
        self.assertEqual(review.readout(a)[1], f"I: {a.card.current:+.6g} A")
        self.assertEqual(review.readout(a)[3], "OUTP: ON")
        self.assertTrue(a.stfmr_gauss_field_var.get().endswith(" G"))
        self.assertIn(("log", "FMR field: setting +500 G ± 1 G with the 4886"), a.log)
        logged = [text for kind, text in a.log if kind == "log"]
        self.assertTrue(any(text.startswith("FMR field: +500 G reached with the 4886: I +1.6")
                            and text.endswith("held from here") for text in logged), logged)
        self.assertEqual(logged[-1], "FMR field: regulation of +500 G stopped; the 4886 left where it is")

    def test_a_field_that_drifts_while_held_is_brought_back(self):
        a = self.page(target="500", tolerance="1")
        gauss = a.stfmr_controllers["gauss"]
        a.held[0] = -10 ** 6                    # not stopped by the page's own hook
        read, state = gauss.read_field, {"reads": 0, "drift": 0.0, "worst": 0.0}

        def reading():
            result = read()
            state["reads"] += 1
            if state["drift"] or abs(result["field"] - 500.0) <= 1.0:
                state["drift"] -= 0.1           # the magnet warms: the field sags, slowly
            result["field"] += state["drift"]
            if state["drift"] < -4.0:
                state["worst"] = max(state["worst"], abs(result["field"] - 500.0))
            if state["drift"] < -20.0 and a.stfmr_field_running:
                a.set_stfmr_field()             # Stop hold
            return result
        gauss.read_field = reading
        a.set_stfmr_field()
        self.error.assert_not_called()
        self.assertEqual(a.statuses[-1], "Field regulation stopped; the 4886 is left at its last current")
        # 20 G of drift made up by the current, the field never far off, and
        # no "the field did not respond" from the drift.
        self.assertGreater(300.0 * a.card.current, 500.0 + 15.0)
        self.assertLess(state["worst"], 3.0)

    def test_a_second_click_on_stop_hold_or_a_click_after_zero_off_starts_nothing(self):
        """The button is "Set field" again a moment after the first click or
        the Zero / OFF: the next click used to start a new field setting,
        after a Zero / OFF switching the magnet back on (review, 2026-11-14)."""
        with mock.patch.object(app, "MAGNET_FIELD_RESTART_LOCKOUT_S", 2.0):
            a = self.page()
            a.set_stfmr_field()                 # held, then stopped by the page's hook
            writes = list(self.writes(a))
            a.set_stfmr_field()                 # the double-click's second click
            self.assertEqual(self.writes(a), writes)
            self.assertEqual(a.statuses[-1], app.MAGNET_FIELD_JUST_STOPPED_TEXT)
            self.assertFalse(a.stfmr_field_running)
            # Zero / OFF, then a click on what was "Stop hold".
            b = self.page(target="2500")
            gauss = b.stfmr_controllers["gauss"]
            read = gauss.read_field
            gauss.read_field = lambda: (b.zero_stfmr_kepco_output() if len(self.writes(b)) >= 8
                                        and not b.stfmr_field_stop_event.is_set() else None, read())[1]
            b.set_stfmr_field()
            self.assertEqual(self.writes(b)[-1], "OUTP OFF")
            b.set_stfmr_field()
            self.assertEqual(self.writes(b)[-1], "OUTP OFF", "the magnet stays off")
            self.assertFalse(b.stfmr_controllers["kepco"].output_owned)
            # After an error a retry is a deliberate press: not held back.
            c = self.page(target="9000")
            c.set_stfmr_field()
            self.assertTrue(c.statuses[-1].startswith("Field not set: Target +9000 G"), c.statuses[-1])
            writes = len(self.writes(c))
            c.stfmr_field_target_var.set("300")
            stop_once_held(c.stfmr_controllers["gauss"], 300.0, 1.0, c.set_stfmr_field)
            c.set_stfmr_field()
            self.assertGreater(len(self.writes(c)), writes)
            self.assertLessEqual(abs(300.0 * c.card.current - 300.0), 1.0)
            # Later it is a Set field again.
            b.stfmr_field_ended_at -= 5.0
            gauss.read_field = read
            b.stfmr_field_target_var.set("300")
            stop_once_held(gauss, 300.0, 1.0, b.set_stfmr_field)
            b.set_stfmr_field()
            self.assertLessEqual(abs(300.0 * b.card.current - 300.0), 1.0)

    def test_a_gaussmeter_that_fails_while_the_field_is_held_leaves_the_current_and_says_so(self):
        """User, 2026-11-14: "when the current increase while the field not
        respond stop increasing the current and return that the Gauss meter
        may not work"."""
        a = self.page(target="500", tolerance="1")
        gauss = a.stfmr_controllers["gauss"]
        a.held[0] = -10 ** 6
        read, inside = gauss.read_field, [0]

        def reading():
            result = read()
            inside[0] += 1 if abs(result["field"] - 500.0) <= 1.0 else 0
            if inside[0] >= 14:
                result["field"] = 0.0           # the meter dies: it reads 0 G whatever the current
            return result
        gauss.read_field = reading
        a.set_stfmr_field()
        self.assertLessEqual(abs(300.0 * a.card.current - 500.0), 1.0, "the current is where it held the field")
        self.assertTrue(a.statuses[-1].startswith("Field lost: The field reading changed by -499"), a.statuses[-1])
        a.root.run(lambda: False)
        text = self.error.call_args.args[1]
        self.assertIn("while the KEPCO current stayed at", text)
        self.assertIn("The current is not changed. The gaussmeter may not be working", text)
        self.assertTrue(text.endswith("The 4886 is left at its last current; Zero / OFF zeroes it."), text)
        self.assertEqual(a.stfmr_magnet_job_pending, 0)
        self.assertFalse(a.stfmr_field_running)

    def test_the_4886_is_written_from_the_tk_thread_and_only_the_475_read_on_the_worker(self):
        """This page's rule for its 4886 session (connect_stfmr_device): a
        first transaction from a worker thread can leave it unresponsive."""
        a = self.page()
        a.stfmr_executor = ls_pages.WorkerExecutor(self, "stfmr-control")
        threads = {"4886": set(), "475": set()}
        write, gauss = a.card.write_raw, a.stfmr_controllers["gauss"]
        read = gauss.read_field
        a.card.write_raw = lambda payload: (threads["4886"].add(threading.get_ident()), write(payload))[1]
        gauss.read_field = lambda: (threads["475"].add(threading.get_ident()), read())[1]
        a.set_stfmr_field()
        self.error.assert_not_called()
        self.assertLessEqual(abs(300.0 * a.card.current - 500.0), 1.0)
        self.assertGreaterEqual(a.held[0], 14, "also while it was held")
        self.assertEqual(threads["4886"], {threading.get_ident()})
        self.assertEqual(threads["475"], {a.stfmr_executor.ident})
        self.assertEqual(a.stfmr_magnet_job_pending, 0)

    def test_it_needs_the_safety_tick_both_instruments_and_an_idle_page(self):
        a = self.page()
        a.stfmr_safety_var.set(False)
        with mock.patch.object(app.messagebox, "showwarning") as warned:
            a.set_stfmr_field()
        self.assertEqual(warned.call_args.args[:2], ("FMR field", SAFETY))
        a.stfmr_safety_var.set(True)
        a.stfmr_controllers["gauss"].connected = False
        with mock.patch.object(app.messagebox, "showwarning") as warned:
            a.set_stfmr_field()
        self.assertEqual(warned.call_args.args[:2], ("FMR field", "Connect the 4886 and the LS475 first."))
        a.stfmr_controllers["gauss"].connected = True
        for busy in ("stfmr_fmr_running", "stfmr_frequency_running"):
            setattr(a, busy, True)
            a.set_stfmr_field()
            setattr(a, busy, False)
        a.stfmr_magnet_job_pending = 1
        a.set_stfmr_field()
        a.apply_stfmr_kepco_output()            # Apply output waits for a field setting too
        self.assertEqual(self.writes(a), [], "nothing was sent")

    def test_bad_numbers_and_voltage_mode_are_refused_before_anything_is_sent(self):
        for change, message in (
                (dict(stfmr_field_target_var="abc"), "The target field and its tolerance must be numbers, in G"),
                (dict(stfmr_field_tolerance_var="0"), "The field tolerance must be above 0 G"),
                (dict(stfmr_output_limit_var="25"), "The voltage limit must be within 0–20 V"),
                (dict(stfmr_output_mode_var="Voltage"),
                 "Choose the output mode Current to set a field: the 4886 is stepped in current")):
            with self.subTest(change):
                a = self.page()
                for name, value in change.items():
                    getattr(a, name).set(value)
                self.error.reset_mock()
                a.set_stfmr_field()
                self.assertEqual(self.error.call_args.args[:2], ("FMR field", message))
                self.assertEqual(self.writes(a), [])
                self.assertEqual(a.__dict__.get("stfmr_magnet_job_pending", 0), 0)

    def test_zero_off_ends_it_and_nothing_is_written_after_the_zero(self):
        a = self.page(target="2500")
        gauss = a.stfmr_controllers["gauss"]
        read = gauss.read_field

        def reading():
            if len(self.writes(a)) >= 8 and not a.stfmr_field_stop_event.is_set():
                a.zero_stfmr_kepco_output()         # the red button, while the loop runs
            return read()
        gauss.read_field = reading
        a.set_stfmr_field()
        self.error.assert_not_called()
        self.assertEqual(self.writes(a)[-2:], ["CURR 0.000000", "OUTP OFF"])
        self.assertEqual(a.stfmr_status_var.get(), "KEPCO zeroed and output off", "the Zero's own line stays")
        self.assertEqual(review.readout(a)[3], "OUTP: OFF")
        self.assertEqual(a.stfmr_magnet_job_pending, 0)
        # The next Set field is not ended by that old Zero.
        gauss.read_field = read
        a.stfmr_field_target_var.set("300")
        stop_once_held(gauss, 300.0, 1.0, a.set_stfmr_field)
        a.set_stfmr_field()
        self.assertLessEqual(abs(300.0 * a.card.current - 300.0), 1.0)

    def test_a_target_out_of_reach_leaves_the_current_and_says_so(self):
        a = self.page(target="9000")                # 30 A of a ±10 A supply
        a.set_stfmr_field()
        self.assertTrue(a.stfmr_status_var.get().startswith("Field not set: Target +9000 G needs about +30 A"),
                        a.stfmr_status_var.get())
        self.error.assert_not_called()              # the dialog opens from the Tk event loop
        a.root.run(lambda: False)
        title, text = self.error.call_args.args[:2]
        self.assertEqual(title, "FMR field")
        self.assertIn("more than the KEPCO's ±10 A", text)
        self.assertTrue(text.endswith("The 4886 is left at its last current; Zero / OFF zeroes it."), text)
        self.assertLess(abs(a.card.current), 2.0)
        self.assertNotIn("OUTP OFF", self.writes(a))
        self.assertEqual(a.stfmr_magnet_job_pending, 0)

    def test_a_475_that_fails_to_read_leaves_the_current_and_frees_the_page(self):
        a = self.page()
        gauss = a.stfmr_controllers["gauss"]
        read = gauss.read_field
        gauss.read_field = lambda: (_ for _ in ()).throw(RuntimeError("VI_ERROR_TMO")) \
            if len(self.writes(a)) >= 7 else read()
        a.set_stfmr_field()
        self.assertEqual(a.stfmr_status_var.get(), "Field not set: VI_ERROR_TMO")
        self.assertEqual(a.busy_calls[-1], (False, 0))
        self.assertTrue(a.stfmr_controllers["kepco"].output_owned, "left on, for the operator's Zero / OFF")

    def make_ls(self, target="2400", **fake_options):
        a = self.page(target=target)
        controller, fake, _clock = connected_supply("648", owner="FMR", **fake_options)
        self.addCleanup(app._INSTRUMENT_LEASES.clear)
        a.stfmr_controllers["lakeshore"] = controller
        a.stfmr_magnet_choice = "LS648"
        a.stfmr_magnet_rate_var = Var("5")
        a.stfmr_controllers["gauss"] = Gauss(lambda: 120.0 * fake.current + 3.0)
        a.stfmr_controllers["gauss"].connected = True
        a.held = stop_once_held(a.stfmr_controllers["gauss"], float(target), 1.0, a.set_stfmr_field)
        return a, controller, fake

    def setpoints(self, fake):
        return [float(c.split()[1]) for c in fake.commands[fake.connect_commands:] if c.startswith("SETI ")]

    def test_the_ls648_is_ramped_step_by_step_to_the_target(self):
        a, controller, fake = self.make_ls()
        a.set_stfmr_field()
        self.error.assert_not_called()
        self.assertLessEqual(abs(120.0 * fake.current + 3.0 - 2400.0), 1.0)
        self.assertEqual(self.setpoints(fake)[0], 0.02)
        self.assertEqual(self.writes(a), [], "the 4886 is not touched")
        self.assertTrue(any(text.startswith("Holding +2400 ± 1 G: I +19.9") for text in a.statuses), a.statuses)
        self.assertEqual(a.statuses[-1], "Field regulation stopped; the LS648 is left at its last current")
        self.assertEqual(self.setpoints(fake)[-1], round(fake.current, 3), "no setpoint after Stop hold")
        self.assertTrue(controller.output_on)
        self.assertEqual(a.stfmr_magnet_job_pending, 0)
        self.assertEqual(a.stfmr_magnet_rate_a_s, 5.0, "the Rate A/s box")
        self.assertIn(("log", "FMR field: setting +2400 G ± 1 G with the LS648"), a.log)

    def test_the_ls648s_zero_off_ends_it_and_zeroes_it(self):
        a, controller, fake = self.make_ls()
        gauss = a.stfmr_controllers["gauss"]
        read = gauss.read_field

        def reading():
            if fake.current > 2.0 and not a.stfmr_field_stop_event.is_set():
                a.zero_stfmr_kepco_output()
            return read()
        gauss.read_field = reading
        a.set_stfmr_field()
        self.error.assert_not_called()
        self.assertLessEqual(abs(fake.current), 0.05, "ramped to 0 A")
        self.assertEqual(self.setpoints(fake)[-1], 0.0)
        self.assertEqual(a.stfmr_status_var.get(), "LS648 at 0 A (zeroed)")
        self.assertEqual(a.stfmr_magnet_job_pending, 0)

    def test_a_bad_rate_is_refused(self):
        a, _controller, fake = self.make_ls()
        a.stfmr_magnet_rate_var.set("0")
        a.set_stfmr_field()
        self.assertEqual(self.error.call_args.args[0], "FMR field")
        self.assertEqual(self.setpoints(fake), [])


# --------------------------------------------------------------------- ST-FMR
class StfmrFieldTests(ls_pages.NoWindows):
    def page(self, target="500", tolerance="1"):
        h = ls_pages.harness(self.tmp.name)
        self.card = review.Card4886()
        kepco = stfmr_app.STFMRKepco4886Controller(lambda message: None)
        kepco.instrument = self.card
        gauss = Gauss(lambda: 300.0 * self.card.current + 5.0)
        gauss.connected = True
        h.stfmr_lockin_controllers["kepco"], h.stfmr_lockin_controllers["gauss"] = kepco, gauss
        h.stfmr_lockin_magnet_choice = stfmr_app.MAGNET_SUPPLY_KEPCO
        h.stfmr_lockin_stop_event, h.stfmr_lockin_field_stop_event = Instant(), Instant()
        h.stfmr_lockin_field_target_var, h.stfmr_lockin_field_tolerance_var = Variable(target), Variable(tolerance)
        h.stfmr_lockin_manual_mode_var, h.stfmr_lockin_manual_limit_var = Variable("Current"), Variable("5")
        h.logged = []
        h.thread_log = h.logged.append
        # Held once reached: the page's button, pressed again, ends it.
        h.held = stop_once_held(gauss, float(target), float(tolerance), h.set_stfmr_lockin_field)
        return h

    def test_the_kepco_is_stepped_until_the_475_reads_the_target(self):
        h = self.page()
        gauss = h.stfmr_lockin_controllers["gauss"]
        read, during = gauss.read_field, []

        def reading():
            during.append((h.stfmr_lockin_field_setting, h._stfmr_lockin_magnet_jobs_pending()))
            return read()
        gauss.read_field = reading
        h.set_stfmr_lockin_field()
        h.root.drain()
        self.error.assert_not_called()
        self.assertEqual(self.card.writes[:5], ["FUNC:MODE CURR", "CURR 0;VOLT 5",
                                                "VOLT:RANG:AUTO 1;CURR:RANG:AUTO 1", "OUTP ON", "CURR 0.000000"])
        self.assertLessEqual(abs(300.0 * self.card.current + 5.0 - 500.0), 1.0)
        self.assertGreaterEqual(h.held[0], 14, "read on while it was held")
        self.assertEqual(self.card.writes[-1], f"CURR {self.card.current:.6f}", "the current stays")
        status = h.stfmr_lockin_status_var.get()
        self.assertEqual(status, "Field regulation stopped; 4886 left as it is")
        self.assertLessEqual(len(status), 52, "within the page's status label")
        self.assertTrue(h.stfmr_lockin_controllers["kepco"].output_owned)
        # Apply output, Start, a hand move and the supply choice waited, and
        # the two rows were locked, while it ran; all free again.
        self.assertEqual(set(during), {(True, True)})
        self.assertFalse(h.stfmr_lockin_field_setting)
        self.assertFalse(h._stfmr_lockin_magnet_jobs_pending())
        self.assertEqual(h.logged[0], "STFMR field: setting +500 G ± 1 G with the 4886")
        self.assertEqual(h.logged[-1], "STFMR field: regulation of +500 G stopped; the 4886 left where it is")

    def test_it_waits_as_apply_output_does_and_needs_the_tick_and_both_instruments(self):
        h = self.page()
        cases = (
            (dict(stfmr_lockin_running=True), "A sweep is running and owns the magnet supply. Stop the sweep first."),
            (dict(stfmr_lockin_starting=True),
             "A stage job or a sweep start is pending: the magnet supply stays as it is until it ends."),
        )
        for state, message in cases:
            with self.subTest(state):
                for name, value in state.items():
                    setattr(h, name, value)
                with mock.patch.object(stfmr_app.messagebox, "showwarning") as warned:
                    h.set_stfmr_lockin_field()
                self.assertEqual(warned.call_args.args[:2], ("STFMR field", message))
                for name in state:
                    setattr(h, name, False)
        h.stfmr_lockin_manual_safety_var.set(False)
        with mock.patch.object(stfmr_app.messagebox, "showwarning") as warned:
            h.set_stfmr_lockin_field()
        self.assertEqual(warned.call_args.args[:2], ("STFMR field", SAFETY))
        h.stfmr_lockin_manual_safety_var.set(True)
        h.stfmr_lockin_controllers["gauss"].connected = False
        with mock.patch.object(stfmr_app.messagebox, "showwarning") as warned:
            h.set_stfmr_lockin_field()
        self.assertEqual(warned.call_args.args[:2], ("STFMR field", "Connect the 4886 and the LS475 first."))
        h.stfmr_lockin_controllers["gauss"].connected = True
        h.stfmr_lockin_magnet_job_pending = 1           # a Lake Shore job, or another field setting
        h.set_stfmr_lockin_field()
        h.apply_stfmr_lockin_kepco_output()
        h.stfmr_lockin_magnet_job_pending = 0
        h.stfmr_lockin_manual_mode_var.set("Voltage")
        h.set_stfmr_lockin_field()
        self.assertEqual(self.error.call_args.args[:2],
                         ("STFMR field", "Choose the output mode Current to set a field: the 4886 is stepped in "
                                         "current"))
        self.assertEqual(self.card.writes, [], "nothing was sent")
        self.assertFalse(h.__dict__.get("stfmr_lockin_field_setting", False))

    def test_zero_off_ends_it_and_nothing_is_written_after_the_zero(self):
        h = self.page(target="2500")
        gauss = h.stfmr_lockin_controllers["gauss"]
        read = gauss.read_field

        def reading():
            if len(self.card.writes) >= 8 and not h.stfmr_lockin_stop_event.is_set():
                h.zero_stfmr_lockin_kepco_output()      # the red button, while the loop runs
            return read()
        gauss.read_field = reading
        h.set_stfmr_lockin_field()
        h.root.drain()
        self.error.assert_not_called()
        self.assertEqual(self.card.writes[-2:], ["CURR 0.000000", "OUTP OFF"])
        self.assertEqual(h.stfmr_lockin_status_var.get(), "KEPCO zeroed and output off")
        self.assertFalse(h.stfmr_lockin_field_setting)
        self.assertFalse(h._stfmr_lockin_magnet_jobs_pending())

    def test_a_zero_off_pressed_while_the_worker_is_writing_is_not_lost(self):
        """The press finds the 4886's lock held, as during a sweep, and is
        made again 200 ms later.  That second press used to count as a
        sweep's (which zeroes the 4886 itself) and sent nothing: the magnet
        stayed on (review, 2026-11-14)."""
        h = self.page(target="2500")
        pool = ThreadPoolExecutor(max_workers=1)
        self.addCleanup(pool.shutdown, wait=True)
        futures = []
        h.stfmr_lockin_executor = mock.Mock(submit=lambda job: futures.append(pool.submit(job)) or futures[-1])
        writing, release = threading.Event(), threading.Event()
        write = self.card.write_raw

        def slow(payload):
            if len(self.card.writes) == 7:          # a step of the loop, under the 4886's lock
                writing.set()
                release.wait(30)
            write(payload)
        self.card.write_raw = slow
        h.set_stfmr_lockin_field()
        self.assertTrue(writing.wait(30))
        h.zero_stfmr_lockin_kepco_output()          # the Tk thread, while the worker holds the lock
        self.assertIn("will be zeroed when it returns", h.stfmr_lockin_status_var.get())
        self.assertNotIn("OUTP OFF", self.card.writes)
        release.set()
        with self.assertRaises(stfmr_app.MagnetFieldStopped):
            futures[0].result(timeout=30)
        pool.submit(lambda: None).result(timeout=30)    # the job's done callback has run on the worker
        h.root.drain()                              # the press made again, and the job's end
        self.error.assert_not_called()
        self.assertEqual(self.card.writes[-2:], ["CURR 0.000000", "OUTP OFF"])
        self.assertFalse(h.stfmr_lockin_controllers["kepco"].output_owned)
        self.assertEqual(h.stfmr_lockin_status_var.get(), "KEPCO zeroed and output off")
        self.assertFalse(h._stfmr_lockin_magnet_jobs_pending())

    def test_a_zero_off_of_a_queued_one_holds_whatever_clears_the_sweeps_stop(self):
        """Queued behind a slow job, zeroed, then a Move stage: the move is
        refused while the field setting is pending, and even with the sweep's
        stop event cleared, as a move clears it, the queued job sends
        nothing (review, 2026-11-14: it switched the 4886 on)."""
        h = self.page(target="1500")
        queued = []
        h.stfmr_lockin_executor = mock.Mock(submit=lambda job: queued.append((job, Future())) or queued[-1][1])
        h.set_stfmr_lockin_field()
        self.assertEqual(len(queued), 1)
        h.zero_stfmr_lockin_kepco_output()
        zeroed = list(self.card.writes)
        self.assertEqual(zeroed[-1], "OUTP OFF")
        with self.assertRaisesRegex(RuntimeError, "A field setting of the 4886 is in progress"):
            h._stfmr_lockin_require_4886_off()
        h.stfmr_lockin_stop_event.clear()           # what a Move stage or a Start does
        with self.assertRaises(stfmr_app.MagnetFieldStopped):
            queued[0][0]()
        self.assertEqual(self.card.writes, zeroed, "nothing after the Zero / OFF")
        self.assertFalse(h.stfmr_lockin_controllers["kepco"].output_owned)

    def test_a_second_click_on_stop_hold_starts_nothing(self):
        with mock.patch.object(stfmr_app, "MAGNET_FIELD_RESTART_LOCKOUT_S", 2.0):
            h = self.page()
            h.set_stfmr_lockin_field()
            h.root.drain()
            writes = list(self.card.writes)
            h.set_stfmr_lockin_field()          # the double-click's second click
            h.root.drain()
            self.assertEqual(self.card.writes, writes)
            self.assertEqual(h.stfmr_lockin_status_var.get(), "Field regulation has just stopped")
            self.assertFalse(h._stfmr_lockin_magnet_jobs_pending())

    def test_a_target_out_of_reach_leaves_the_current_and_says_so(self):
        h = self.page(target="9000")
        h.set_stfmr_lockin_field()
        h.root.drain()
        status = h.stfmr_lockin_status_var.get()
        self.assertTrue(status.startswith("Field not set: Target +9000 G needs"), status)
        self.assertLessEqual(len(status), 52)
        title, text = self.error.call_args.args[:2]
        self.assertEqual(title, "STFMR field")
        self.assertTrue(text.endswith("The 4886 is left at its last current; Zero / OFF zeroes it."), text)
        self.assertNotIn("OUTP OFF", self.card.writes)
        self.assertFalse(h._stfmr_lockin_magnet_jobs_pending())

    def test_the_ls643_is_ramped_step_by_step_and_its_zero_off_ends_it(self):
        h = self.page(target="2400")
        controller, fake, _clock = connected_supply("643", owner="STFMR", module=stfmr_app)
        self.addCleanup(stfmr_app._INSTRUMENT_LEASES.clear)
        h.stfmr_lockin_controllers["lakeshore"] = controller
        h.stfmr_lockin_magnet_choice = "LS643"
        h.stfmr_lockin_magnet_rate_var = Variable("5")
        gauss = Gauss(lambda: 120.0 * fake.current + 3.0)
        gauss.connected = True
        h.stfmr_lockin_controllers["gauss"] = gauss
        stop_once_held(gauss, 2400.0, 1.0, h.set_stfmr_lockin_field)
        h.set_stfmr_lockin_field()
        h.root.drain()
        self.error.assert_not_called()
        self.assertLessEqual(abs(120.0 * fake.current + 3.0 - 2400.0), 1.0)
        self.assertEqual(self.card.writes, [], "the 4886 is not touched")
        self.assertEqual(h.stfmr_lockin_status_var.get(), "Field regulation stopped; LS643 left as it is")
        self.assertTrue(controller.output_on, "a hand move of the stage is refused until it is zeroed")
        # Zero / OFF during the next one: no setpoint but the zero's follows.
        read = gauss.read_field

        def reading():
            if fake.current > 21.0 and not h.stfmr_lockin_stop_event.is_set():
                h.zero_stfmr_lockin_kepco_output()
            return read()
        gauss.read_field = reading
        h.stfmr_lockin_field_target_var.set("3600")
        h.set_stfmr_lockin_field()
        h.root.drain()
        self.assertLessEqual(abs(fake.current), 0.05)
        self.assertEqual(fake.sent()[-1], "SETI 0.000")
        self.assertFalse(h._stfmr_lockin_magnet_jobs_pending())


# ------------------------------------------------------------------------ SHV
class ShvFieldTests(shv_runs.EndToEnd):
    def page(self, target="500", tolerance="1"):
        h = self.make()
        panel = h.panel
        self.card = review.Card4886()
        kepco = app.STFMRKepco4886Controller(lambda message: None)
        kepco.instrument = self.card
        gauss = Gauss(lambda: 300.0 * self.card.current + 5.0)
        gauss.connected = True
        panel.rte_controllers["kepco"], panel.rte_controllers["gauss"] = kepco, gauss
        h.kepco, h.gauss = kepco, gauss
        panel.ppms_field_scan_stop_event = Instant()
        panel.rte_field_target.set(target)
        panel.rte_field_tolerance.set(tolerance)
        # Held once reached: the page's button, pressed again, ends it.
        h.held = stop_once_held(gauss, float(target), float(tolerance), panel._rte_set_field)
        return h

    def test_the_kepco_is_stepped_on_the_worker_until_the_475_reads_the_target(self):
        h = self.page()
        panel = h.panel
        read, during = h.gauss.read_field, []

        def reading():
            during.append((panel.ppms_environment_busy, threading.get_ident()))
            return read()
        h.gauss.read_field = reading
        panel._rte_set_field()
        self.pump(h)
        h.showerror.assert_not_called()
        self.assertEqual(self.card.writes[:5], ["FUNC:MODE CURR", "CURR 0;VOLT 5",
                                                "VOLT:RANG:AUTO 1;CURR:RANG:AUTO 1", "OUTP ON", "CURR 0.000000"])
        self.assertLessEqual(abs(300.0 * self.card.current + 5.0 - 500.0), 1.0)
        self.assertGreaterEqual(h.held[0], 14, "read on while it was held")
        self.assertEqual(self.card.writes[-1], f"CURR {self.card.current:.6f}", "the current stays")
        self.assertEqual(panel.rte_drive_live.get(), "KEPCO: field regulation stopped")
        self.assertFalse(panel.rte_field_setting)
        self.assertEqual(h.logged[-1], "SHV field: regulation of +500 G stopped")
        self.assertEqual(set(during), {(True, h.worker)}, "on the worker, the rack busy meanwhile")
        self.assertFalse(panel.ppms_environment_busy)
        self.assertIn("SHV field: setting +500 G ± 1 G with the KEPCO", h.logged)

    def test_it_needs_the_racks_safety_tick_and_both_instruments(self):
        h = self.page()
        panel = h.panel
        panel.ppms_control_safety_var.set(False)
        panel._rte_set_field()
        self.assertEqual(h.showerror.call_args.args[:2], ("SHV field", "Tick the SHV rack safety confirmation first"))
        panel.ppms_control_safety_var.set(True)
        h.gauss.connected = False
        panel._rte_set_field()
        self.assertEqual(h.showerror.call_args.args[:2], ("SHV field", "Connect the Lake Shore 475 first"))
        h.gauss.connected = True
        panel.rte_field_tolerance.set("0")
        panel._rte_set_field()
        self.assertEqual(h.showerror.call_args.args[:2], ("SHV field", "The field tolerance must be above 0 G"))
        panel.rte_field_tolerance.set("1")
        panel.ppms_environment_busy = True
        panel._rte_set_field()
        self.assertEqual(h.showerror.call_args.args[:2], ("SHV field", "SHV is busy; wait or stop the scan first"))
        panel.ppms_environment_busy = False
        self.pump(h)
        self.assertEqual(self.card.writes, [], "nothing was sent")

    def test_zero_off_ends_it_and_its_zero_runs_next_on_the_worker(self):
        h = self.page(target="2500")
        panel = h.panel
        read = h.gauss.read_field

        def reading():
            if len(self.card.writes) >= 8 and not panel.ppms_field_scan_stop_event.is_set():
                panel._rte_zero()               # the red button: the stop event, and the OFF queued
            return read()
        h.gauss.read_field = reading
        panel._rte_set_field()
        self.pump(h)
        h.showerror.assert_not_called()
        self.assertEqual(self.card.writes[-2:], ["CURR 0.000000", "OUTP OFF"])
        self.assertEqual(panel.rte_drive_live.get(), "KEPCO: zeroed and output OFF")
        self.assertFalse(panel.ppms_environment_busy)

    def test_set_field_waits_for_the_ls643s_zero_off_ramp(self):
        """A press during the ramp to 0 A, the button long "Set field"
        again, queued a field setting behind it and the magnet came back up
        (review, 2026-11-14)."""
        h = self.page(target="2400")
        panel = h.panel
        controller, fake, _clock = connected_supply("643", owner="SHV", current=20.0)
        self.addCleanup(app._INSTRUMENT_LEASES.clear)
        panel.rte_controllers["lakeshore"] = controller
        panel.rte_magnet_rate.set("5")
        panel.rte_magnet_choice_var.set("Lake Shore 643")
        panel._rte_magnet_choice_changed()
        gate = threading.Event()
        h.executor.submit(gate.wait, 30)        # the worker is busy: the zero stays queued behind it
        panel._rte_zero()
        self.assertEqual(panel.rte_lakeshore_zero_pending, 1)
        panel._rte_set_field()
        self.assertEqual(h.showerror.call_args.args[:2],
                         ("SHV field", "The LS643 is being ramped to 0 A (Zero / OFF): wait for it, then set the "
                                       "field"))
        gate.set()
        self.pump(h)
        self.assertEqual(panel.rte_lakeshore_zero_pending, 0)
        self.assertLessEqual(abs(fake.current), 0.05)
        self.assertEqual(fake.sent()[-1], "SETI 0.000", "the zero, and no field setting behind it")

    def test_a_second_click_on_stop_hold_starts_nothing(self):
        with mock.patch.object(app, "MAGNET_FIELD_RESTART_LOCKOUT_S", 2.0):
            h = self.page()
            panel = h.panel
            panel._rte_set_field()
            self.pump(h)
            writes = list(self.card.writes)
            self.assertEqual(panel.rte_drive_live.get(), "KEPCO: field regulation stopped")
            panel._rte_set_field()              # the double-click's second click
            self.pump(h)
            self.assertEqual(self.card.writes, writes)
            self.assertEqual(panel.rte_drive_live.get(), app.MAGNET_FIELD_JUST_STOPPED_TEXT)
            h.showerror.assert_not_called()
            self.assertFalse(panel.ppms_environment_busy)

    def test_a_zero_off_from_the_tk_thread_while_the_worker_reads(self):
        h = self.page(target="2500")
        panel = h.panel
        reading_now, release = threading.Event(), threading.Event()
        read = h.gauss.read_field

        def reading():
            if len(self.card.writes) >= 8 and not reading_now.is_set():
                reading_now.set()
                release.wait(30)
            return read()
        h.gauss.read_field = reading
        panel._rte_set_field()
        self.assertTrue(reading_now.wait(30))
        writes = len(self.card.writes)
        panel._rte_zero()                           # this (the Tk) thread
        release.set()
        self.pump(h)
        h.showerror.assert_not_called()
        self.assertEqual(self.card.writes[writes:], ["CURR 0.000000", "OUTP OFF"], "only the zero after the press")
        self.assertEqual(panel.rte_drive_live.get(), "KEPCO: zeroed and output OFF")
        self.assertFalse(panel.ppms_environment_busy)

    def test_a_target_out_of_reach_leaves_the_current_and_says_so(self):
        h = self.page(target="9000")
        panel = h.panel
        panel._rte_set_field()
        self.pump(h)
        self.assertTrue(panel.rte_drive_live.get().startswith("Field not set: Target +9000 G needs about +30 A"),
                        panel.rte_drive_live.get())
        title, text = h.showerror.call_args.args[:2]
        self.assertEqual(title, "SHV field")
        self.assertTrue(text.endswith("The KEPCO is left at its last current; its Zero / OFF zeroes it."), text)
        self.assertNotIn("OUTP OFF", self.card.writes)
        self.assertFalse(panel.ppms_environment_busy)

    def test_the_ls643_is_ramped_step_by_step_to_the_target(self):
        h = self.page(target="2400")
        panel = h.panel
        controller, fake, _clock = connected_supply("643", owner="SHV")
        self.addCleanup(app._INSTRUMENT_LEASES.clear)
        panel.rte_controllers["lakeshore"] = controller
        panel.rte_magnet_rate.set("5")
        panel.rte_magnet_choice_var.set("Lake Shore 643")
        panel._rte_magnet_choice_changed()
        self.assertTrue(panel._rte_lakeshore_chosen(), h.showerror.call_args)
        gauss = Gauss(lambda: 120.0 * fake.current + 3.0)
        gauss.connected = True
        panel.rte_controllers["gauss"] = gauss
        stop_once_held(gauss, 2400.0, 1.0, panel._rte_set_field)
        panel._rte_set_field()
        self.pump(h)
        h.showerror.assert_not_called()
        self.assertLessEqual(abs(120.0 * fake.current + 3.0 - 2400.0), 1.0)
        self.assertEqual(self.card.writes, [], "the KEPCO is not touched")
        self.assertEqual(panel.rte_drive_live.get(), "LS643: field regulation stopped")
        self.assertEqual(fake.page_threads(), {h.worker})


if __name__ == "__main__":
    unittest.main()
