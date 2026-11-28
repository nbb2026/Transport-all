"""An SR830's front panel shows X and Y once the program has connected it
(user, 2026-11-15: "when the SR830 connect, it should display X and Y in its
font panel instead of R and theta").  Every page had set R and theta
("DDEF 1,1,0" / "DDEF 2,1,0"): PPMS and SHHV at Connect, ST-FMR and Non-local
with a scan's Start, which connected and showed whatever was on the panel
until then.

Here: the commands, and the Connect of the ST-FMR and Non-local pages.  The
set-up lists of the pages are in test_stfmr_sr830_tc_fixed_current (ST-FMR's
Start), test_ppms_sr830_tc (the PPMS / SHHV Connect) and test_ms_four_state.
"""
import inspect
import unittest
from unittest import mock

from test_ppms_motor_debug import app

SR830 = "Stanford_Research_Systems,SR830,s/n12345,ver1.07"
SHOW_XY = [("write", "DDEF 1,0,0"), ("write", "DDEF 2,0,0")]


class Session:
    """A VISA session that keeps what it is sent, in order."""

    def __init__(self, identity=SR830, refuse=""):
        self.identity, self.refuse, self.log, self.closed = identity, refuse, [], False

    def query(self, command):
        self.log.append(("query", command))
        return self.identity

    def write(self, command):
        self.log.append(("write", command))
        if self.refuse and command.startswith(self.refuse):
            raise RuntimeError("VI_ERROR_TMO")

    def clear(self):
        pass

    def close(self):
        self.closed = True


class DisplayTests(unittest.TestCase):
    def setUp(self):
        self.logged = []

    def visa(self, session):
        manager = mock.Mock()
        manager.open_resource.return_value = session
        for patcher in (mock.patch.object(app, "pyvisa", object()),
                        mock.patch.object(app, "acquire_shared_visa_manager", return_value=manager),
                        mock.patch.object(app, "release_shared_visa_manager"),
                        mock.patch.object(app, "acquire_instrument_lease"),
                        mock.patch.object(app, "release_instrument_lease"),
                        mock.patch.object(app.time, "sleep")):
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_commands_are_x_on_ch1_and_y_on_ch2_without_a_ratio(self):
        # DDEF i, j, k: CH1 j = 0 X (1 R); CH2 j = 0 Y (1 theta); k = 0 no ratio.
        self.assertEqual(app.SR830_DISPLAY_XY_COMMANDS, ("DDEF 1,0,0", "DDEF 2,0,0"))

    def test_no_page_sets_r_and_theta_any_more(self):
        source = inspect.getsource(app)
        code = [line.split("#")[0] for line in source.splitlines()]
        self.assertEqual([line.strip() for line in code if "DDEF 1,1" in line or "DDEF 2,1" in line], [])
        # The commands and the Connect's helper, then ST-FMR's Start,
        # Non-local's Start and the PPMS / SHHV Connect.
        self.assertEqual(sum("SR830_DISPLAY_XY_COMMANDS" in line for line in code), 5)

    def test_stfmr_connect_shows_x_and_y(self):
        session = Session()
        self.visa(session)
        controller = app.STFMRSR830Controller(self.logged.append)
        self.assertEqual(controller.connect("GPIB0::8::INSTR"), SR830)
        # Nothing before the identity is known, then the display alone: the
        # rest of the set-up (range, time constant ...) still comes with Start.
        self.assertEqual(session.log, [("query", "*IDN?"), *SHOW_XY])
        self.assertTrue(controller.connected)

    def test_a_device_that_is_not_an_sr830_is_sent_nothing(self):
        session = Session("KEITHLEY INSTRUMENTS INC.,MODEL 2400")
        self.visa(session)
        controller = app.STFMRSR830Controller(self.logged.append)
        with self.assertRaisesRegex(RuntimeError, "is not Stanford SR830"):
            controller.connect("GPIB0::8::INSTR")
        self.assertEqual(session.log, [("query", "*IDN?")])
        self.assertTrue(session.closed)

    def test_a_display_write_that_fails_does_not_undo_the_connection(self):
        session = Session(refuse="DDEF")
        self.visa(session)
        controller = app.STFMRSR830Controller(self.logged.append)
        self.assertEqual(controller.connect("GPIB0::8::INSTR"), SR830)
        self.assertTrue(controller.connected)
        self.assertFalse(session.closed)
        self.assertEqual(self.logged[-1],
                         "STFMR SR830: the display was not set to X and Y: VI_ERROR_TMO")

    def test_the_ppms_and_shv_controller_writes_nothing_itself(self):
        """Their Connect's own set-up follows at once and holds the display
        commands, each checked (test_ppms_sr830_tc)."""
        session = Session()
        self.visa(session)
        controller = app.SafeVisaIdentityController(self.logged.append, "SR830-1", "SR830")
        controller.connect("GPIB0::8::INSTR")
        self.assertEqual(session.log, [("query", "*IDN?")])

if __name__ == "__main__":
    unittest.main()
