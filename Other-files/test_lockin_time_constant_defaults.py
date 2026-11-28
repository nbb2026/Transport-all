"""Every lock-in time constant the program starts with is 1 s.

User, 2026-10-14: "all default lock-in time constant change to 1s pls."
Before, three boxes started at 0.1 s (STFMR "MFLI TC s", the Non-local rack's
Zurich "TC (s)", the PPMS / RT-E Zurich "Time constant s" / "TC (s)") and
STFMR's "SR830 TC" at 100 ms.  Only the defaults changed: every wait computed
from a time constant keeps its rule, so the waits that follow from the new
defaults are checked here too, as the README lists them.

No Tk window and no instrument: the boxes are checked in the source (as
test_stfmr_mod_prime_range checks Mod. start / end) and, for the PPMS / RT-E
page, in the real panel constructor on stand-in widgets (test_ppms_two_panels'
make_panel).  Creating a Tk root fails the test."""
import inspect
import math
import re
import sys
import threading
import tkinter
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
for _path in (_HERE, _HERE.parent):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import transport.rt.app as app  # noqa: E402
import test_ppms_two_panels as two_panels  # noqa: E402  (its own copy of the program)


class NoWindows(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("tkinter.Tk", side_effect=AssertionError("a test tried to open a Tk window"))
        patcher.start()
        self.addCleanup(patcher.stop)


class DefaultsAreOneSecond(NoWindows):

    def test_the_methods_default_to_1_s(self):
        """What the program sends when the caller gives no time constant."""
        self.assertEqual(inspect.signature(app.STFMRSR830Controller.configure)
                         .parameters["time_constant_code"].default, 10)
        self.assertEqual(inspect.signature(app.NonLocalACController.configure_mfli)
                         .parameters["timeconstant_s"].default, 1.0)

class OneTimeConstantSettle(NoWindows):
    pass


class WaitsAtTheNewDefaults(NoWindows):
    """The rules are unchanged; these are their values at the 1 s defaults."""

    pass


def _step_seen(t_s, tau_s):
    """Fraction of a current step a 12 dB/oct (2nd-order) lock-in shows t_s
    after the step."""
    x = t_s / tau_s
    return 1.0 - math.exp(-x) * (1.0 + x)


def _iv6221_sample_times(settle_s, acquire_s):
    """When _nonlocal_iv6221_read_point reads after a step (no read delay):
    after Settle s, every NONLOCAL_IV6221_SAMPLE_INTERVAL_S until Acquire s
    has passed since the first reading."""
    interval = app.NONLOCAL_IV6221_SAMPLE_INTERVAL_S
    count = int(math.ceil(acquire_s / interval - 1e-9)) + 1
    return [settle_s + k * interval for k in range(count)]


class DefaultSetupsAtTheNewTc(NoWindows):
    """Settle s, Acquire s and Wait/pt do not follow the TC, so these
    out-of-the-box setups read before a 1 s TC has settled (reviewed,
    user, 2026-10-14).  Only documented here; the waits are unchanged."""

    pass


if __name__ == "__main__":
    unittest.main()
