"""The magnetic-field setting's controller (user, 2026-11-14: "Add a magnetic
field setting in FMR, SHV, STFMR modules. You can try to use PID to control
the magnetic field value"), offline against simulated magnets.

- MagnetFieldPID: G per A measured with a probe step, then a PID step per
  settled reading; within the tolerance it stops.  It never steps further
  than its limit, never beyond the supply's maximum, and gives up, the
  current left where it is, when the gaussmeter does not answer, the field
  does not follow, or the target cannot be reached.
- read_settled_magnet_field: after a step, groups of three readings until two
  in a row agree; a field still moving, or noisier than the tolerance, is
  never taken for the field.
- set_magnet_field: the loop on a page's worker (the settled field, the next
  current), ended by the page's stop.
- run_magnet_field_set: that loop on a KEPCO 4886 (switched on at 0 A, or
  taken from where it is; never written after a Zero / OFF) or a Lake Shore
  643 / 648 (each step a ramp).

No window, no instrument, no real waiting."""
import math
import random
import threading
import unittest
from unittest.mock import patch

import test_fmr_stfmr_review as review
from test_lakeshore_magnet_supply import connected_supply, release
from test_ppms_motor_debug import app

PID = app.MagnetFieldPID
PROBES = app.MAGNET_FIELD_SET_PROBES_A


class Magnet:
    """An electromagnet and its gaussmeter: B = polarity * f(I) + remanence,
    read with noise and a display resolution."""

    def __init__(self, g_per_a=300.0, remanence=5.0, polarity=1.0, saturation_g=None, noise_g=0.0,
                 resolution_g=0.0, dead=False, seed=1):
        self.g_per_a, self.remanence, self.polarity = g_per_a, remanence, polarity
        self.saturation_g, self.noise_g, self.resolution_g, self.dead = saturation_g, noise_g, resolution_g, dead
        self.random = random.Random(seed)
        self.current = 0.0
        self.history = [0.0]

    def set(self, current):
        self.current = float(current)
        self.history.append(self.current)

    def true_field(self):
        if self.dead:
            return self.remanence
        linear = self.g_per_a * self.current
        if self.saturation_g:
            linear = self.saturation_g * math.tanh(linear / self.saturation_g)
        return self.polarity * linear + self.remanence

    def read(self):
        value = self.true_field() + self.random.uniform(-self.noise_g, self.noise_g)
        if self.resolution_g:
            value = round(value / self.resolution_g) * self.resolution_g
        return value


def drive(pid, magnet, readings=3):
    """The loop without its waits: returns the number of readings taken."""
    count = 0
    while True:
        values = [magnet.read() for _ in range(readings)]
        count += 1
        target = pid.update(magnet.current, sum(values) / len(values), max(values) - min(values))
        if target is None:
            return count
        magnet.set(target)
        if count > 2000:
            raise AssertionError("the loop did not end")


def steps_of(magnet):
    return [round(b - a, 6) for a, b in zip(magnet.history, magnet.history[1:])]


class ReachTests(unittest.TestCase):
    def test_a_linear_magnet_is_brought_within_the_tolerance_in_a_few_steps(self):
        magnet = Magnet()
        pid = PID(500.0, 1.0, 10.0)
        readings = drive(pid, magnet)
        self.assertLessEqual(abs(magnet.true_field() - 500.0), 1.0)
        self.assertLess(readings, 12)
        self.assertAlmostEqual(pid.slope_g_per_a, 300.0, delta=3.0)
        self.assertEqual(magnet.history[1], PROBES[0], "the first step is the small probe")
        self.assertTrue(all(abs(c) <= 10.0 for c in magnet.history))

    def test_a_field_already_within_the_tolerance_changes_nothing(self):
        magnet = Magnet(remanence=4.0)
        self.assertEqual(drive(PID(5.0, 2.0, 10.0), magnet), 1)
        self.assertEqual(magnet.history, [0.0])

    def test_reversed_wiring_a_negative_target_and_a_start_away_from_zero(self):
        for label, magnet, target in (
                ("the field falls as the current rises", Magnet(polarity=-1.0), 400.0),
                ("a negative target", Magnet(), -750.0),
                ("a weak magnet", Magnet(g_per_a=40.0), 120.0),
                ("a strong magnet", Magnet(g_per_a=2500.0), 9000.0)):
            with self.subTest(label):
                drive(PID(target, 1.0, 10.0), magnet)
                self.assertLessEqual(abs(magnet.true_field() - target), 1.0)
        magnet = Magnet()
        magnet.current, magnet.history = 2.0, [2.0]       # an output already on at 2 A
        drive(PID(900.0, 1.0, 10.0), magnet)
        self.assertLessEqual(abs(magnet.true_field() - 900.0), 1.0)

    def test_a_saturating_magnet_and_noisy_readings_still_arrive(self):
        saturating = Magnet(g_per_a=800.0, saturation_g=6000.0)
        drive(PID(5000.0, 2.0, 40.0), saturating)
        self.assertLessEqual(abs(saturating.true_field() - 5000.0), 2.0)
        for seed in range(20):
            noisy = Magnet(noise_g=0.4, seed=seed)
            drive(PID(650.0, 2.0, 10.0), noisy)
            self.assertLessEqual(abs(noisy.true_field() - 650.0), 2.0 + 0.4, seed)

    def test_a_coarse_gaussmeter_reading_is_enough_for_a_coarse_tolerance(self):
        magnet = Magnet(resolution_g=10.0)
        drive(PID(1000.0, 10.0, 10.0), magnet)
        self.assertLessEqual(abs(magnet.true_field() - 1000.0), 15.0)


class StepTests(unittest.TestCase):
    def test_the_first_corrections_are_small_and_grow_only_while_the_field_follows(self):
        magnet = Magnet(g_per_a=100.0)
        pid = PID(8000.0, 1.0, 100.0)             # an LS648: up to 100 A
        drive(pid, magnet)
        steps = steps_of(magnet)
        self.assertEqual(steps[0], PROBES[0])
        self.assertLessEqual(abs(steps[1]), 0.5 + 1e-9, "the first correction")
        self.assertLessEqual(max(abs(step) for step in steps), 10.0 + 1e-9, "never above 10 % of the maximum")
        # Each step at most twice the one before it (the limit doubles).
        for before, after in zip(steps[1:], steps[2:]):
            self.assertLessEqual(abs(after), 2.0 * abs(before) + 1e-6)
        self.assertLessEqual(abs(magnet.true_field() - 8000.0), 1.0)
        self.assertLess(len(steps), 40, "not 160 steps of 0.5 A")

    def test_a_kepco_never_steps_more_than_1_a(self):
        magnet = Magnet(g_per_a=100.0)
        drive(PID(900.0, 1.0, 10.0), magnet)
        self.assertLessEqual(max(abs(step) for step in steps_of(magnet)), 1.0 + 1e-9)

    def test_setpoints_are_whole_milliamps(self):
        magnet = Magnet(g_per_a=317.3)
        drive(PID(431.7, 0.5, 10.0), magnet)
        self.assertTrue(all(abs(c * 1000 - round(c * 1000)) < 1e-6 for c in magnet.history))

    def test_the_pid_terms(self):
        pid = PID(100.0, 1.0, 10.0, kp=0.5, ki=0.25, kd=2.0)
        pid.slope_g_per_a, pid.errors = 10.0, [40.0, 30.0, 24.0]
        # kp (24 - 30) + ki 24 + kd (24 - 60 + 40) = -3 + 6 + 8 = 11 G -> 1.1 A, held to the 0.5 A limit.
        self.assertEqual(pid._correct(1.0, 76.0, 24.0), 1.5)
        pid.step_limit_a = 5.0
        self.assertEqual(pid._correct(1.0, 76.0, 24.0), 2.1)
        # The integral term alone by default: 0.8 of the whole error.
        plain = PID(100.0, 1.0, 10.0)
        plain.slope_g_per_a, plain.errors, plain.step_limit_a = 10.0, [24.0], 5.0
        self.assertEqual(plain._correct(1.0, 76.0, 24.0), round(1.0 + 0.8 * 2.4, 3))


class GiveUpTests(unittest.TestCase):
    def test_a_gaussmeter_that_does_not_see_the_magnet_moves_the_current_by_0_62_a_at_most(self):
        for noise in (0.0, 0.3, 3.0):
            with self.subTest(noise=noise):
                magnet = Magnet(dead=True, noise_g=noise)
                with self.assertRaises(app.MagnetFieldError) as raised:
                    drive(PID(500.0, 1.0, 100.0), magnet)
                self.assertIn("did not change measurably", str(raised.exception))
                self.assertEqual(steps_of(magnet), list(PROBES))
                self.assertAlmostEqual(max(abs(c) for c in magnet.history), sum(PROBES))

    def test_a_field_that_stops_following_ends_it_after_two_steps(self):
        magnet = Magnet()
        pid = PID(2000.0, 1.0, 100.0)
        original = magnet.true_field
        magnet.true_field = lambda: original() if magnet.current <= 1.0 else 300.0 * 1.0 + 5.0   # stuck above 1 A
        with self.assertRaises(app.MagnetFieldError) as raised:
            drive(pid, magnet)
        self.assertIn("does not follow", str(raised.exception))
        after = [c for c in magnet.history if c > 1.0]
        self.assertLessEqual(len(after), 3)
        self.assertLess(max(magnet.history), 4.0, "not on to the 100 A maximum")

    def test_a_target_far_beyond_the_supply_is_refused_before_the_maximum(self):
        magnet = Magnet(g_per_a=100.0)
        with self.assertRaises(app.MagnetFieldError) as raised:
            drive(PID(5000.0, 1.0, 10.0), magnet)          # needs 50 A of a ±10 A supply
        self.assertIn("more than the magnet supply's ±10 A", str(raised.exception))
        self.assertIn("needs about +50 A", str(raised.exception))
        self.assertLess(max(abs(c) for c in magnet.history), 2.0)

    def test_a_target_just_beyond_a_saturating_magnet_stops_at_the_maximum_and_says_so(self):
        magnet = Magnet(g_per_a=800.0, saturation_g=6000.0)
        with self.assertRaises(app.MagnetFieldError) as raised:
            drive(PID(5900.0, 1.0, 10.0), magnet)
        # Said at the maximum, or just before it from the measured G per A.
        self.assertIn("more than the magnet supply's ±10 A", str(raised.exception))
        self.assertLessEqual(max(abs(c) for c in magnet.history), 10.0)

    def test_a_tolerance_finer_than_a_setpoint_step_says_so(self):
        magnet = Magnet(g_per_a=3000.0)                     # 3 G per mA
        with self.assertRaises(app.MagnetFieldError) as raised:
            drive(PID(1000.0, 0.05, 10.0), magnet)
        message = str(raised.exception)
        self.assertTrue("finer than one setpoint step" in message or "not reached after" in message, message)

    def test_a_probe_that_only_weakly_sees_the_magnet_is_refused_within_the_probe_steps(self):
        """A probe beside the gap, or on another magnet: a few G per A.
        Following it would take the current to the supply's maximum
        (review, 2026-11-14)."""
        for g_per_a in (1.5, 5.0, 15.0):
            with self.subTest(g_per_a=g_per_a):
                magnet = Magnet(g_per_a=g_per_a)
                with self.assertRaises(app.MagnetFieldError) as raised:
                    drive(PID(300.0, 1.0, 100.0), magnet)
                message = str(raised.exception)
                self.assertTrue("G per A" in message or "did not change measurably" in message, message)
                self.assertLessEqual(max(abs(c) for c in magnet.history), sum(PROBES) + 1e-9)

    def test_one_scattered_reading_does_not_switch_the_check_off(self):
        """The scatter that counts is that of the two readings a step lies
        between: one noisy reading early used to blind the check for the
        whole run, and a probe that then stopped following was followed to
        the maximum (review, 2026-11-14)."""
        magnet = Magnet()
        pid = PID(20000.0, 1.0, 100.0)
        stuck = [None]
        readings = 0
        with self.assertRaises(app.MagnetFieldError) as raised:
            while True:
                field = magnet.true_field() if stuck[0] is None else stuck[0]
                readings += 1
                target = pid.update(magnet.current, field, 20.0 if readings == 3 else 0.0)
                if magnet.current >= 2.0 and stuck[0] is None:
                    stuck[0] = field                # the probe stops following here
                magnet.set(target)
                self.assertLess(readings, 100)
        self.assertIn("does not follow", str(raised.exception))
        self.assertLess(max(magnet.history), 6.0, "not on to the 100 A maximum")

    def test_small_steps_against_a_stuck_reading_add_up_and_end_it(self):
        magnet = Magnet()
        pid = PID(520.0, 2.0, 100.0)
        original = magnet.true_field
        magnet.true_field = lambda: min(original(), 500.0)          # the reading sticks 20 G short
        with self.assertRaises(app.MagnetFieldError) as raised:
            while True:
                target = pid.update(magnet.current, magnet.true_field(), 2.0)   # readings as noisy as allowed
                magnet.set(target)
                self.assertLess(len(magnet.history), 60)
        self.assertIn("does not follow", str(raised.exception))
        self.assertLess(max(magnet.history), 500.0 / 300.0 + 0.5)

    def test_a_supply_too_small_for_the_probes_is_refused(self):
        pid = PID(500.0, 1.0, 0.05)
        self.assertEqual(pid.update(0.04, 0.0), 0.02, "down, when up is beyond the maximum")
        with self.assertRaises(app.MagnetFieldError) as raised:
            pid.update(0.02, 0.0)               # neither +0.1 A nor -0.1 A fits in ±0.05 A
        self.assertIn("leaves no room for a 0.1 A probe step", str(raised.exception))

    def test_a_first_probe_that_over_read_does_not_let_a_weak_coupling_through(self):
        """A display step or noise on the 0.02 A probe can make 15 G per A
        look like 50: the larger change that follows shows what it is, and
        the minimum holds there too (review, 2026-11-14)."""
        for g_per_a in (12.0, 15.0, 17.0, 19.0):
            with self.subTest(g_per_a=g_per_a):
                magnet = Magnet(g_per_a=g_per_a, resolution_g=1.0, remanence=0.4)
                with self.assertRaises(app.MagnetFieldError) as raised:
                    drive(PID(500.0, 2.0, 100.0), magnet)
                message = str(raised.exception)         # too weak, or not following: stopped either way
                self.assertTrue("G per A" in message or "does not follow" in message, message)
                self.assertLess(max(abs(c) for c in magnet.history), 2.0)
        for seed in range(300):
            magnet = Magnet(g_per_a=19.0, noise_g=0.15, seed=seed)
            with self.assertRaises(app.MagnetFieldError):
                drive(PID(500.0, 2.0, 100.0), magnet)
            self.assertLess(max(abs(c) for c in magnet.history), 2.0, seed)

    def test_bad_numbers_are_refused_before_anything(self):
        for arguments in ((math.nan, 1.0, 10.0), (100.0, 0.0, 10.0), (100.0, math.inf, 10.0), (100.0, 1.0, 0.0)):
            with self.subTest(arguments):
                with self.assertRaises(ValueError):
                    PID(*arguments)
        with self.assertRaises(app.MagnetFieldError):
            PID(100.0, 1.0, 10.0).update(0.0, math.nan)


class LoopTests(unittest.TestCase):
    def test_it_waits_reads_three_times_and_reports_every_reading(self):
        magnet = Magnet()
        waits, progress = [], []
        reading = app.set_magnet_field(PID(500.0, 1.0, 10.0), 0.0, magnet.set, magnet.read, waits.append,
                                       progress.append)
        self.assertTrue(reading["reached"])
        self.assertLessEqual(abs(reading["field_g"] - 500.0), 1.0)
        self.assertEqual(reading["current_a"], magnet.current)
        self.assertEqual(len(progress), len(magnet.history))
        settle, between = app.MAGNET_FIELD_SET_SETTLE_S, app.MAGNET_FIELD_SET_READ_INTERVAL_S
        gap = app.MAGNET_FIELD_SET_GROUP_GAP_S
        # The settle, a group of three readings, a gap and a second group that agrees.
        self.assertEqual(waits[:6], [settle, between, between, gap, between, between])
        self.assertEqual(len(waits), 6 * len(progress))
        self.assertEqual([entry["next_current_a"] for entry in progress[:-1]], magnet.history[1:])
        self.assertIsNone(progress[-1]["next_current_a"])

    def test_the_pages_stop_ends_it_where_it_is(self):
        magnet = Magnet()

        def wait(_seconds):
            if len(magnet.history) >= 3:
                raise app.MagnetFieldStopped("stopped")

        with self.assertRaises(app.MagnetFieldStopped):
            app.set_magnet_field(PID(2000.0, 1.0, 10.0), 0.0, magnet.set, magnet.read, wait)
        self.assertEqual(len(magnet.history), 3, "no step after the stop")


class Instant(threading.Event):
    """The page's stop event with no real waiting."""

    def wait(self, timeout=None):
        return self.is_set()


class Lagging:
    """A magnet whose field follows the current with a time constant, on a
    clock that only the loop's waits move."""

    def __init__(self, tau_s, g_per_a=300.0):
        self.tau_s, self.g_per_a = tau_s, g_per_a
        self.current, self.field, self.history = 0.0, 0.0, [0.0]

    def wait(self, seconds):
        self.field += (self.g_per_a * self.current - self.field) * (1.0 - math.exp(-seconds / self.tau_s))

    def set(self, current):
        self.current = float(current)
        self.history.append(self.current)

    def read(self):
        return self.field


class SettledReadingTests(unittest.TestCase):
    def test_a_steady_field_is_two_groups_of_three_readings(self):
        reads = []
        field, scatter = app.read_settled_magnet_field(lambda: reads.append(1) or 512.0, lambda _s: None, 1.0)
        self.assertEqual((field, scatter, len(reads)), (512.0, 0.0, 6))

    def test_a_field_still_moving_is_read_again_until_it_stops(self):
        values = iter([100.0, 140.0, 170.0, 190.0, 200.0, 205.0, 207.0, 207.5, 207.8] + [208.0] * 12)
        field, scatter = app.read_settled_magnet_field(lambda: next(values), lambda _s: None, 1.0)
        self.assertEqual(field, 208.0)
        self.assertLessEqual(scatter, 1.0)

    def test_readings_noisier_than_the_tolerance_never_count_as_the_field(self):
        noisy = random.Random(3)
        with self.assertRaises(app.MagnetFieldError) as raised:
            app.read_settled_magnet_field(lambda: 500.0 + noisy.uniform(-30.0, 30.0), lambda _s: None, 0.2)
        self.assertIn("did not settle within 15 s", str(raised.exception))
        # ... and so no step is taken on them.
        magnet = Magnet(noise_g=30.0)
        with self.assertRaises(app.MagnetFieldError):
            app.set_magnet_field(PID(500.0, 0.2, 10.0), 0.0, magnet.set, magnet.read, lambda _s: None)
        self.assertEqual(magnet.history, [0.0])

    def test_a_reading_that_is_not_a_number_and_the_pages_stop(self):
        with self.assertRaises(app.MagnetFieldError):
            app.read_settled_magnet_field(lambda: math.nan, lambda _s: None, 1.0)

        def stopped(_seconds):
            raise app.MagnetFieldStopped("stopped")
        with self.assertRaises(app.MagnetFieldStopped):
            app.read_settled_magnet_field(lambda: 1.0, stopped, 1.0)

    def test_a_field_that_lags_the_current_is_waited_for_not_overshot(self):
        magnet = Lagging(tau_s=1.5)
        reading = app.set_magnet_field(PID(900.0, 1.0, 10.0), 0.0, magnet.set, magnet.read, magnet.wait)
        self.assertTrue(reading["reached"])
        # Two groups that agree within 1 G, 0.5 s apart, leave at most a few G of lag.
        self.assertLessEqual(abs(300.0 * magnet.current - 900.0), 5.0, "the current the field needs, once settled")
        self.assertLessEqual(max(magnet.history), 900.0 / 300.0 + 0.05, "no overshoot")
        slow = Lagging(tau_s=60.0)
        with self.assertRaises(app.MagnetFieldError) as raised:
            app.set_magnet_field(PID(900.0, 1.0, 10.0), 0.0, slow.set, slow.read, slow.wait)
        self.assertIn("did not settle", str(raised.exception))
        self.assertLessEqual(max(slow.history), sum(PROBES) + 1e-9)

    def test_either_of_two_stop_events_ends_a_wait(self):
        first, second = Instant(), Instant()
        both = app._AnyEvent(first, second)
        self.assertFalse(both.is_set() or both.wait(5))
        second.set()
        self.assertTrue(both.is_set() and both.wait(5))
        first.set()
        second.clear()
        self.assertTrue(both.is_set())


class Gauss:
    """An LS475 that reads a field in its front-panel unit."""

    def __init__(self, field_g, unit_code=1):
        self.field_g, self.unit_code, self.reads = field_g, unit_code, 0

    def read_field(self):
        self.reads += 1
        value = self.field_g()
        return {"field": value / (1.0e4 if self.unit_code == 2 else 1.0), "unit_code": self.unit_code,
                "unit": "T" if self.unit_code == 2 else "G"}

    value_in_gauss = staticmethod(app.STFMRGauss475Controller.value_in_gauss)


class KepcoRunTests(unittest.TestCase):
    def rig(self, g_per_a=300.0):
        card = review.Card4886()
        kepco = review.connected_4886(card)
        supply = app.MagnetSupply(kepco)
        gauss = Gauss(lambda: g_per_a * card.current + 5.0)
        return card, kepco, supply, gauss

    def test_an_output_that_is_off_is_switched_on_at_0_a_then_stepped(self):
        card, kepco, supply, gauss = self.rig()
        progress = []
        reading = app.run_magnet_field_set(supply, gauss, 500.0, 1.0, 5.0, Instant(), progress=progress.append)
        self.assertEqual(card.writes[:5], ["FUNC:MODE CURR", "CURR 0;VOLT 5", "VOLT:RANG:AUTO 1;CURR:RANG:AUTO 1",
                                           "OUTP ON", "CURR 0.000000"])
        self.assertEqual(card.writes[5], f"CURR {PROBES[0]:.6f}", "then the probe, a current alone")
        self.assertTrue(all(write.startswith("CURR ") for write in card.writes[5:]))
        self.assertEqual(card.writes.count("OUTP ON"), 1)
        self.assertLessEqual(abs(300.0 * card.current + 5.0 - 500.0), 1.0)
        self.assertTrue(reading["reached"])
        self.assertTrue(kepco.output_owned)
        self.assertEqual(kepco.cached_current_a, card.current)
        self.assertEqual(progress[-1], reading)

    def test_an_output_already_on_is_taken_from_where_it_is(self):
        card, kepco, supply, gauss = self.rig()
        kepco.set_output("CURR", 1.0, 5.0)
        before = len(card.writes)
        app.run_magnet_field_set(supply, gauss, 900.0, 1.0, 5.0, Instant())
        self.assertNotIn("OUTP ON", card.writes[before:])
        self.assertEqual(card.writes[before], f"CURR {1.0 + PROBES[0]:.6f}")

    def test_an_output_on_in_voltage_mode_is_refused_and_nothing_sent(self):
        card, kepco, supply, gauss = self.rig()
        kepco.set_output("VOLT", 2.0, 1.0)
        before = list(card.writes)
        with self.assertRaises(app.MagnetFieldError) as raised:
            app.run_magnet_field_set(supply, gauss, 500.0, 1.0, 5.0, Instant())
        self.assertIn("voltage mode", str(raised.exception))
        self.assertEqual(card.writes, before)
        self.assertEqual(gauss.reads, 0)

    def test_a_stop_set_before_it_starts_sends_nothing(self):
        card, _kepco, supply, gauss = self.rig()
        stop = Instant()
        stop.set()
        with self.assertRaises(app.MagnetFieldStopped):
            app.run_magnet_field_set(supply, gauss, 500.0, 1.0, 5.0, stop)
        self.assertEqual(card.writes, [])

    def test_no_write_follows_a_zero_off(self):
        """The red button sets the stop, then zeroes under the 4886's lock;
        the loop checks the stop under the same lock before each write."""
        card, kepco, supply, _gauss = self.rig()
        stop = Instant()

        def field():
            if len(card.writes) >= 8 and not stop.is_set():
                stop.set()                      # Zero / OFF, from the Tk thread
                kepco.force_output_off()
            return 300.0 * card.current + 5.0

        with self.assertRaises(app.MagnetFieldStopped):
            app.run_magnet_field_set(supply, Gauss(field), 2500.0, 1.0, 5.0, stop)
        self.assertEqual(card.writes[-2:], ["CURR 0.000000", "OUTP OFF"])
        self.assertFalse(kepco.output_owned)

    def test_a_zero_off_that_forgot_the_stop_still_cannot_switch_the_output_back_on(self):
        card, kepco, supply, _gauss = self.rig()

        def field():
            if len(card.writes) >= 8 and kepco.output_owned:
                kepco.force_output_off()
            return 300.0 * card.current + 5.0

        with self.assertRaises(RuntimeError) as raised:
            app.run_magnet_field_set(supply, Gauss(field), 2500.0, 1.0, 5.0, Instant())
        self.assertIn("not in the current-output mode", str(raised.exception))
        self.assertEqual(card.writes[-1], "OUTP OFF")

    def test_a_closing_page_ends_it_and_a_tesla_reading_is_converted(self):
        card, _kepco, supply, _gauss = self.rig()
        closing = []
        with self.assertRaises(app.MagnetFieldStopped):
            app.run_magnet_field_set(supply, Gauss(lambda: closing.append(1) or 5.0), 500.0, 1.0, 5.0, Instant(),
                                     closing=lambda: bool(closing))
        self.assertEqual(card.writes[-1], "CURR 0.000000", "only the switch-on at 0 A")
        card, _kepco, supply, _gauss = self.rig()
        tesla = Gauss(lambda: 300.0 * card.current + 5.0, unit_code=2)
        reading = app.run_magnet_field_set(supply, tesla, 500.0, 1.0, 5.0, Instant())
        self.assertLessEqual(abs(reading["field_g"] - 500.0), 1.0)


class LakeShoreRunTests(unittest.TestCase):
    def tearDown(self):
        app._INSTRUMENT_LEASES.clear()

    def rig(self, model="648", **options):
        controller, fake, _clock = connected_supply(model, owner="FMR", **options)
        self.addCleanup(release, controller)
        stop = Instant()
        supply = app.MagnetSupply(None, controller, use_lakeshore=True, rate_a_s=5.0, stop_event=stop)
        return controller, fake, supply, stop

    def test_each_step_is_a_ramp_and_the_field_arrives(self):
        controller, fake, supply, stop = self.rig()
        gauss = Gauss(lambda: 120.0 * fake.current + 3.0)
        reading = app.run_magnet_field_set(supply, gauss, 2400.0, 1.0, None, stop)
        self.assertTrue(reading["reached"])
        self.assertLessEqual(abs(120.0 * fake.current + 3.0 - 2400.0), 1.0)
        setpoints = [float(c.split()[1]) for c in fake.commands[fake.connect_commands:] if c.startswith("SETI ")]
        self.assertEqual(setpoints[0], PROBES[0])
        self.assertLessEqual(max(abs(b - a) for a, b in zip([0.0] + setpoints, setpoints)), 10.0 + 1e-9)
        self.assertAlmostEqual(setpoints[-1], fake.current, places=3)
        self.assertTrue(controller.output_on)

    def test_it_starts_from_the_supplys_setpoint(self):
        _controller, fake, supply, stop = self.rig(current=4.0)
        gauss = Gauss(lambda: 120.0 * fake.current + 3.0)
        app.run_magnet_field_set(supply, gauss, 600.0, 1.0, None, stop)
        setpoints = [float(c.split()[1]) for c in fake.commands[fake.connect_commands:] if c.startswith("SETI ")]
        self.assertEqual(setpoints[0], round(4.0 + PROBES[0], 3))

    def test_a_zero_offs_stop_request_ends_it_as_a_stop_and_sends_no_new_setpoint(self):
        controller, fake, supply, stop = self.rig()

        def field():
            if fake.current > 1.0:
                controller.request_stop()       # Zero / OFF, from the Tk thread
            return 120.0 * fake.current + 3.0

        with self.assertRaises(app.MagnetFieldStopped):
            app.run_magnet_field_set(supply, Gauss(field), 2400.0, 1.0, None, stop)
        setpoints = [c for c in fake.commands[fake.connect_commands:] if c.startswith("SETI ")]
        self.assertLess(float(setpoints[-1].split()[1]), 3.0)

    def test_a_supply_stopped_away_from_its_setpoint_is_refused_and_nothing_sent(self):
        """Its first small step would be a ramp across the whole difference."""
        _controller, fake, supply, stop = self.rig(setpoint=10.0)
        fake.halted, fake.current = True, 3.0       # as after a STOP mid-ramp
        gauss = Gauss(lambda: 120.0 * fake.current + 3.0)
        with self.assertRaises(app.MagnetFieldError) as raised:
            app.run_magnet_field_set(supply, gauss, 2400.0, 1.0, None, stop)
        self.assertIn("is not at its setpoint (SETI? +10.000 A, output +3.000 A)", str(raised.exception))
        self.assertEqual([c for c in fake.commands[fake.connect_commands:] if c.startswith("SETI ")], [])
        self.assertEqual(gauss.reads, 0)

    def test_the_supplys_own_limit_is_the_maximum(self):
        _controller, fake, supply, stop = self.rig(model="643")
        self.assertEqual(supply.max_current_a(), 40.0)
        gauss = Gauss(lambda: 120.0 * fake.current + 3.0)
        with self.assertRaises(app.MagnetFieldError) as raised:
            app.run_magnet_field_set(supply, gauss, 20000.0, 1.0, None, stop)
        self.assertIn("more than the LS643's ±40 A", str(raised.exception))
        self.assertLess(abs(fake.current), 5.0)


if __name__ == "__main__":
    unittest.main()
