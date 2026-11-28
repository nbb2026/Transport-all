"""Fixes from the whole-program review (2026-10-09), one check each.

No Tk and no instrument: stand-ins record what the code asks of them."""
import threading
import types
import unittest
from unittest import mock

import numpy as np

from test_nonlocal_keithley import Var, bare_app
from test_ppms_motor_debug import app


class Recorder:
    """An instrument that records writes and answers queries from a table."""

    def __init__(self, replies=None):
        self.log, self.replies = [], dict(replies or {})

    def write(self, command):
        self.log.append(command)

    def query(self, command):
        self.log.append(command)
        reply = self.replies[command]
        return reply.pop(0) if isinstance(reply, list) else reply


class SharedHelperTests(unittest.TestCase):
    def test_a_2_5_step_keeps_its_half_steps_in_the_labels(self):
        self.assertEqual(app.format_nice_tick(3002.5, 2.5), "3002.5")
        self.assertEqual(app.format_nice_tick(10005.0, 2.5), "10005.0")
        self.assertEqual(app.format_nice_tick(3000.0, 5.0), "3000")

    def test_a_scan_axis_does_not_repeat_its_end(self):
        self.assertEqual(app.ppms_scan_axis(0.1, 0.4, 0.1)[-2:], (0.30000000000000004, 0.4))
        self.assertEqual(len(app.ppms_scan_axis(0.1, 0.4, 0.1)), 4)

    def test_the_short_gpib_spelling_shares_the_lease(self):
        self.assertEqual(app.instrument_lease_key("GPIB0::30"), app.instrument_lease_key("GPIB0::30::INSTR"))


class MokeTests(unittest.TestCase):
    pass

class StfmrTests(unittest.TestCase):
    pass

class PpmsTests(unittest.TestCase):
    def test_rte_zero_off_acts_on_an_output_switched_on_elsewhere(self):
        panel = app.RTEPanel.__new__(app.RTEPanel)
        panel.ppms_field_scan_stop_event = threading.Event()
        panel.rte_closed = False
        kepco = mock.Mock()
        panel.rte_controllers = {"kepco": kepco}

        class Now:
            def submit(self, function):
                future = mock.Mock()
                future.result.return_value = function()
                future.add_done_callback.side_effect = lambda callback: callback(future)
                return future

        panel.ppms_executor = Now()
        panel.post_ui = lambda callback: callback()
        panel.rte_drive_live = Var()
        panel._rte_zero()
        kepco.force_output_off.assert_called_once()
        kepco.zero_output.assert_not_called()
        self.assertEqual(panel.rte_drive_live.get(), "KEPCO: zeroed and output OFF")

if __name__ == "__main__":
    unittest.main()
