"""When a lock-in's range steps down, and that it never takes turns with
the step up for ever (user, 2026-11-16: "when the measured voltage is below
1%, then decrease the range of lock-in. pls make sure the auto-range
function work well and not get stuck in an endless auto-ranging loop").

The rule was 15 % of the range on ST-FMR and Non-local and for the Zurich,
10 % on PPMS and SHHV; it is 1 % everywhere (LOCKIN_DOWNRANGE_FRACTION).
The loops it could run into, and what stops each:

- an SR830 whose finer range overloads on the input while R stays small (a
  harmonic beside the fundamental): down, overload, up, down ... ST-FMR and
  Non-local now keep the "overload floor" PPMS and SHHV had;
- the Zurich, whose firmware chooses the range: a "low" autorange that
  keeps the range was asked for again every few readings for good.

Here: the Zurich's rule against a stand-in instrument (the ST-FMR and Non-local
SR830 rules are not in this program: their tests went with that code on
2026-11-28).  The PPMS rule is in test_review_fixes and test_ppms_sr830_tc.
"""
import inspect
import unittest
from unittest import mock

from test_ppms_motor_debug import app

SCALES = app.NONLOCAL_SR830_FULL_SCALE_V


class SR830:
    """An SR830's range, as the rule sees it.  ``overloads_below``: every
    range finer than this SENS index overloads the input, whatever R is."""

    def __init__(self, index, overloads_below=0):
        self.index, self.overloads_below, self.writes = index, overloads_below, []
        self.harmonic, self.r_v, self.latched = 1, 0.0, []

    def write(self, command):
        self.writes.append(command)
        if command.startswith("SENS "):
            self.index = int(command.split()[1])
        if command.startswith("HARM "):
            self.harmonic = int(command.split()[1])

    def query(self, command):
        if command == "LIAS?":
            # What latched since the last read, then the condition now.
            return str(self.latched.pop(0) if self.latched else self.status())
        return {"SENS?": str(self.index), "*ESR?": "0", "HARM?": str(self.harmonic),
                "SNAP? 1,2,3,4,9": f"0,0,{self.r_v!r},0,17.0"}[command]

    def status(self, locked=True):
        return (1 if self.index < self.overloads_below else 0) | (0 if locked else 8)


class Firmware:
    """The Zurich's own autorange: ``ranges`` are the ranges it chooses, one
    per call (the last one for every later call)."""

    def __init__(self, *ranges):
        self.ranges, self.calls, self.range = list(ranges), 0, None

    def choose(self):
        return self.ranges[min(self.calls, len(self.ranges) - 1)]

    def request(self, command):
        assert command == "autorange", command
        old = self.range
        self.range = self.choose()
        self.calls += 1
        return {"autorange": {"old_input_range_v": old, "input_range_v": self.range}}


class PeakFirmware(Firmware):
    """A firmware that takes the smallest range of twice the input peak."""

    RANGES = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0)

    def __init__(self, start):
        super().__init__(start)
        self.range, self.peak_v = start, 0.0

    def choose(self):
        return next((r for r in self.RANGES if r >= 2 * self.peak_v), self.RANGES[-1])


class ZurichTests(unittest.TestCase):
    def make(self, start, *chosen, firmware=None):
        controller = app.NonLocalACController(lambda _text: None)
        firmware = firmware or Firmware(*chosen)
        firmware.range = start
        controller.mfli_bridge = firmware
        controller.mfli_config = {"input_range_v": start}
        return controller, firmware

    @staticmethod
    def read(controller, utilization, readings):
        return [controller._auto_range_mfli({"input_utilization": utilization}) for _ in range(readings)]

    @staticmethod
    def follow(controller, firmware, peak_v, readings):
        """``readings`` readings of an input of ``peak_v`` on whatever range
        the firmware has chosen; the actions."""
        firmware.peak_v = peak_v
        return [a for a in (controller._auto_range_mfli({"input_utilization": peak_v / firmware.range})
                            for _ in range(readings)) if a]

    def test_an_input_above_one_percent_keeps_the_range(self):
        for utilization in (0.012, 0.05, 0.14, 0.5):
            with self.subTest(utilization=utilization):
                controller, firmware = self.make(0.1, 0.01)
                self.assertEqual(self.read(controller, utilization, 40), [""] * 40)
                self.assertEqual(firmware.calls, 0)

    def test_a_low_autorange_that_keeps_the_range_is_not_asked_for_again(self):
        """The endless loop: a weak signal on the lowest range.  The firmware
        keeps 1 mV; it was asked again after every six readings, for good."""
        controller, firmware = self.make(0.001, 0.001)
        actions = self.read(controller, 0.002, 500)
        self.assertEqual([a for a in actions if a], ["RANGE 0.001->0.001 V (low)"])
        self.assertEqual(actions.index("RANGE 0.001->0.001 V (low)"), 2, "after three low readings")
        self.assertEqual(firmware.calls, 1)
        self.assertEqual(controller.mfli_low_floor_v, 0.001)

    def test_it_steps_down_while_the_firmware_lowers_the_range(self):
        controller, firmware = self.make(0.1, 0.01, 0.001, 0.001)
        actions = [a for a in self.read(controller, 0.002, 500) if a]
        self.assertEqual(actions, ["RANGE 0.1->0.01 V (low)", "RANGE 0.01->0.001 V (low)",
                                   "RANGE 0.001->0.001 V (low)"])
        self.assertEqual(firmware.calls, 3)

    def test_a_signal_that_grows_and_shrinks_is_still_followed(self):
        """Review, 2026-11-16: one step up after a step down blocked every
        later step down, so 20 uV stayed on the 30 mV range for the rest of
        the scan."""
        controller, firmware = self.make(1.0, firmware=PeakFirmware(1.0))
        self.assertEqual(self.follow(controller, firmware, 5e-3, 10), ["RANGE 1->0.01 V (low)"])
        self.assertEqual(self.follow(controller, firmware, 9e-3, 10), ["RANGE 0.01->0.03 V (overload/high)"])
        self.assertEqual(controller.mfli_low_readings_needed, 6, "twice as many low readings next time")
        actions = self.follow(controller, firmware, 20e-6, 2000)
        # After six low readings in a row, down to the lowest range (2 % of it).
        self.assertEqual(actions, ["RANGE 0.03->0.001 V (low)"])
        self.assertEqual(firmware.range, 0.001)

    def test_two_ranges_that_take_turns_do_so_ever_more_rarely(self):
        """A finer range that is too fine, a coarser one that reads low: each
        turn needs twice as many low readings as the one before."""
        controller, firmware = self.make(0.1)
        firmware.ranges = [0.01, 0.1] * 50
        changes, readings = [], 0
        while readings < 5000:
            utilization = 0.95 if firmware.range == 0.01 else 0.002
            if controller._auto_range_mfli({"input_utilization": utilization}):
                changes.append(readings)
            readings += 1
        downs = [index for index, _ in enumerate(changes) if index % 2 == 0]
        self.assertLessEqual(len(changes), 22, "about 2 x log2(5000 / 3)")
        self.assertGreater(len(downs), 3, "and it is still tried")
        gaps = [later - earlier for earlier, later in zip(changes[0::2], changes[2::2])]
        self.assertEqual(gaps, sorted(gaps), "each turn later than the one before")
        self.assertGreaterEqual(gaps[-1], 4 * gaps[0])
        # The released rule: a change every three or four readings, for good.
        self.assertLessEqual(controller.mfli_low_readings_needed, app.MFLI_DOWNRANGE_READINGS_LIMIT)

    def test_an_overload_is_still_answered_on_a_range_the_firmware_kept(self):
        controller, firmware = self.make(0.001, 0.001, 0.01, 0.01)
        self.read(controller, 0.002, 10)
        self.assertEqual(controller.mfli_low_floor_v, 0.001)
        self.assertEqual(controller._auto_range_mfli({"input_utilization": 0.9}),
                         "RANGE 0.001->0.01 V (overload/high)")
        self.assertEqual(controller._run_mfli_autorange("input overload"), "RANGE 0.01->0.01 V (input overload)")
        # Above the range it kept, a step down may be asked for again.
        self.assertEqual([a for a in self.read(controller, 0.002, 10) if a], ["RANGE 0.01->0.01 V (low)"])
        self.assertEqual(controller.mfli_low_floor_v, 0.01)

    def test_a_step_up_alone_changes_nothing(self):
        # Never stepped down: a signal that grew and shrank is followed.
        controller, firmware = self.make(0.01, 0.1, 0.01, 0.01)
        self.assertEqual(controller._auto_range_mfli({"input_utilization": 0.9}),
                         "RANGE 0.01->0.1 V (overload/high)")
        self.assertEqual(controller.mfli_low_readings_needed, 3)
        self.assertEqual([a for a in self.read(controller, 0.002, 500) if a],
                         ["RANGE 0.1->0.01 V (low)", "RANGE 0.01->0.01 V (low)"])

    def test_the_point_reads_of_stfmr_ppms_and_shv_come_through_the_same_guard(self):
        """read_stfmr_mfli, as the ST-FMR, PPMS and SHHV pages read the
        Zurich, with the real autorange behind it."""
        controller, firmware = self.make(0.1, 0.01, 0.1, 0.1)
        sample = {"input_overload": False, "input_extrema_valid": True, "input_utilization": 0.002}
        with mock.patch.object(controller, "read_mfli", side_effect=lambda _hz: dict(sample)):
            actions = [controller.read_stfmr_mfli(17.0, auto_range=True).get("auto_range", "") for _ in range(3)]
            self.assertEqual(actions, ["", "", "RANGE 0.1->0.01 V (low)"])
            sample.update(input_overload=True, input_utilization=1.0)
            self.assertEqual(controller.read_stfmr_mfli(17.0, auto_range=True)["auto_range"],
                             "RANGE 0.01->0.1 V (STFMR input overload)")
            self.assertEqual(controller.mfli_low_readings_needed, 6)
            sample.update(input_overload=False, input_utilization=0.002)
            actions = [controller.read_stfmr_mfli(17.0, auto_range=True).get("auto_range", "") for _ in range(12)]
            # The cool-down's three, then six low readings in a row.
            self.assertEqual([i for i, a in enumerate(actions) if a], [8])
            # A set-up's own autorange starts afresh.
            controller.read_stfmr_mfli(17.0, auto_range=True, initial=True)
            self.assertEqual((controller.mfli_low_readings_needed, controller.mfli_low_floor_v), (3, 0.0))

    def test_a_new_set_up_starts_afresh(self):
        for reason in app.NonLocalACController.MFLI_RANGE_FRESH_REASONS:
            with self.subTest(reason=reason):
                controller, firmware = self.make(0.001, 0.001)
                self.read(controller, 0.002, 10)
                controller.mfli_low_readings_needed, controller.mfli_stepped_down = 48, True
                controller._run_mfli_autorange(reason)
                self.assertEqual((controller.mfli_low_floor_v, controller.mfli_low_readings_needed,
                                  controller.mfli_stepped_down), (0.0, 3, False))
        self.assertEqual(app.NonLocalACController.MFLI_RANGE_FRESH_REASONS, ("initial", "STFMR frequency start"))
        import inspect
        self.assertIn("self.forget_mfli_range_guard()", inspect.getsource(app.NonLocalACController.configure_mfli))

    def test_ppms_and_shv_forget_it_where_they_forget_the_sr830_floors(self):
        """Review, 2026-11-16: a new excitation, pass or sweep forgot the
        SR830 floors and left the Zurich held back."""
        page = app.CombinedControlApp.__new__(app.CombinedControlApp)
        page.ppms_sr830_range_states = {}
        page.zurich_controller = mock.Mock()
        page._ppms_clear_sr830_range_floor()                              # a pass's or sweep's first point
        page._ppms_clear_sr830_range_floor(("830_a",), zurich=True)       # a new excitation
        self.assertEqual(page.zurich_controller.forget_mfli_range_guard.call_count, 2)
        page._ppms_clear_sr830_range_floor(("830_a",))                    # one SR830 alone
        self.assertEqual(page.zurich_controller.forget_mfli_range_guard.call_count, 2)
        del page.zurich_controller                                        # a page without a Zurich
        page._ppms_clear_sr830_range_floor()
        import inspect
        self.assertIn("_ppms_clear_sr830_range_floor(active_lockins, zurich=True)",
                      inspect.getsource(app.CombinedControlApp._configure_ppms_transport_scan))

    def test_the_tick_off_reads_only(self):
        controller, firmware = self.make(0.001, 0.001)
        controller.mfli_auto_range_enabled = False
        self.assertEqual(self.read(controller, 0.0001, 20), [""] * 20)
        self.assertEqual(firmware.calls, 0)


class FirstPointToleranceTests(unittest.TestCase):
    pass


if __name__ == "__main__":
    unittest.main()
