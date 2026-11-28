"""Offline RT-E regression tests. Never open a VISA or LabOne session."""
from concurrent.futures import Future
from contextlib import ExitStack
import csv
from pathlib import Path
import tempfile
import threading
import types
import time
import unittest
from unittest.mock import Mock, patch

from test_ppms_motor_debug import app
from test_ppms_two_panels import Var, ImmediateExecutor


class StartExecutor:
    """The RT-E worker at Start (user, 2026-10-17).  Short jobs, such as an
    Angle scan's stage check before any instrument is set up, run at once,
    as ImmediateExecutor runs them; the scan's own job is only recorded and
    gets ``scan_future`` (a Future the test settles, else a Mock that never
    calls back), so the scan never runs here.  ``submit`` is a Mock, so its
    calls can be asserted as before."""

    SCAN = '_rte_harmonic_scan_worker'

    def __init__(self, scan_future=None):
        self.scan_future = Mock() if scan_future is None else scan_future
        self.submit = Mock(side_effect=self._submit)

    def _submit(self, fn, *args):
        if getattr(fn, '__name__', '') == self.SCAN:
            return self.scan_future
        future = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as error:
            future.set_exception(error)
        return future

    def scans(self):
        """The scan submits: (fn, mode, plan, passes, limit, stable, duration[, field current])."""
        return [call.args for call in self.submit.call_args_list
                if getattr(call.args[0], '__name__', '') == self.SCAN]

    def shutdown(self, **kwargs):
        pass


class Widget:
    def __init__(self, *args, **kwargs):
        self.options = dict(kwargs)
        self.parent = args[0] if args else None
    def grid(self, **kwargs): pass
    def grid_remove(self): pass
    def rowconfigure(self, *args, **kwargs): pass
    def columnconfigure(self, *args, **kwargs): pass
    def bind(self, *args, **kwargs): pass
    def configure(self, **kwargs): self.options.update(kwargs)
    def grid_size(self): return (18, 9)


class RTE(unittest.TestCase):
    def harmonic_panel(self, choices=('1+2', '1+2+3', '3')):
        panel = self.make_worker()
        panel.zurich_scan_enabled = False
        for key, choice in zip(app.PPMS_SR830_KEYS, choices):
            setattr(panel, app.PPMS_SR830_HARMONIC_ATTRS[key], Var(choice))
        return panel

    def ordered(self, panel):
        """The scan's acquisitions and its end's zeroing, in one call list."""
        order = Mock()
        order.attach_mock(panel._average_ppms_transport_sample, 'acquire')
        order.attach_mock(panel._acquire_ppms_first_point, 'acquire_first')
        order.attach_mock(panel._stop_ppms_transport_source, 'off')
        order.attach_mock(panel._ppms_query_numbers, 'query')
        order.attach_mock(panel.rte_controllers['kepco'].force_output_off, 'kepco_zero')
        return order

    def make_worker(self):
        panel = app.RTEPanel.__new__(app.RTEPanel)
        panel.parent_app = Mock(closing=False)
        panel.closing = panel.rte_closed = False
        panel.ppms_field_scan_stop_event = threading.Event()
        panel.ppms_field_scan_rows = []
        panel.ppms_field_scan_started_at = time.monotonic()
        panel.ppms_field_scan_total = 2
        panel.ppms_live_csv_fields = None
        panel.ppms_instrument_controllers = {'830_a': Mock(resource_name='GPIB0::8::INSTR')}
        panel.rte_controllers = {'kepco': Mock(output_owned=True, cached_current_a=0.), 'gauss': Mock()}
        panel._configure_ppms_transport_scan = Mock()
        panel._rte_update_current = Mock()
        panel._stop_ppms_transport_source = Mock()
        panel._ppms_query_numbers = Mock(return_value=(0.,))  # 6221 OUTP? after the off command
        panel._rte_settle_field = Mock(return_value=-2.)
        panel._rte_read_field = Mock(return_value=-2.)
        sample = {'sr830_8_x_v': 1e-6, 'sr830_8_y_v': -1e-6, 'sr830_8_r_v': 1.414e-6,
                  'sr830_8_theta_deg': -45., 'sr830_8_reference_valid': True}
        panel._acquire_ppms_first_point = Mock(return_value=(dict(sample), 2))
        panel._average_ppms_transport_sample = Mock(return_value=dict(sample))
        panel.post_ui = Mock()
        panel._ppms_append_row = Mock()
        panel._rte_wait = lambda seconds: (
            (_ for _ in ()).throw(app.PPMSScanCancelled('stop'))
            if panel.ppms_field_scan_stop_event.is_set() else None)
        return panel

    def settings(self):
        return app.validate_ppms_transport_scan_settings(1., 317.3, 50., 1, 2, ('830_a',))

    def test_rte_server_override_and_shared_default_are_isolated(self):
        with patch.object(app.socket, 'create_connection') as connect:
            connect.return_value.__enter__.return_value = Mock()
            servers, _ = app.NonLocalACController._mfli_reachable_servers(candidates=(('192.168.68.250', 8004),))
            self.assertEqual(servers, [('192.168.68.250', 8004)])
            connect.assert_called_once_with(('192.168.68.250', 8004), 1.2)
            connect.reset_mock()
            servers, _ = app.NonLocalACController._mfli_reachable_servers()
            self.assertEqual(servers, list(app.NONLOCAL_MFLI_SERVER_CANDIDATES))

    def test_rte_unreachable_message_uses_correct_address(self):
        controller = app.NonLocalACController(lambda _: None)
        controller.mfli_server_candidates = (('192.168.68.250', 8004),)
        with patch.object(app.socket, 'create_connection', side_effect=TimeoutError('timed out')):
            with self.assertRaises(RuntimeError) as caught:
                controller.connect_mfli('MF-DEV4414')
        message = str(caught.exception)
        self.assertIn('dev4414', message)
        self.assertIn('192.168.68.250', message)
        self.assertNotIn('192.168.69.77', message)
        self.assertNotIn('192.168.69.78', message)

if __name__ == '__main__':
    unittest.main()
