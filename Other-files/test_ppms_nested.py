"""Offline range and nested-worker acceptance; no hardware or Tk window."""
import threading
import types
import unittest
from unittest.mock import patch
from test_ppms_motor_debug import app


class NestedTests(unittest.TestCase):

    def test_range_direction_endpoint(self):
        self.assertEqual(app.ppms_scan_axis(0, 2.5, 1), (0., 1., 2., 2.5))
        self.assertEqual(app.ppms_scan_axis(2, 0, 1), (2., 1., 0.))
        self.assertEqual(app.ppms_scan_axis(2, 2, 1), (2.,))
        for args in ((0, 1, 0), (0, float('nan'), 1), (0, 1e9, 1)):
            with self.assertRaises(ValueError):
                app.ppms_scan_axis(*args)

    def harness(self):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.closing = False
        obj.ppms_field_scan_stop_event = threading.Event()
        obj.ppms_scan_context = {}
        obj.ppms_angle_live_var = types.SimpleNamespace(set=lambda value: None)
        state = dict(angle=26., field=0., temp=300.)
        events = []
        remote = types.SimpleNamespace(active=state)
        remote.set_field = lambda target, *args: (state.update(field=target), events.append(('field', target)))
        remote.set_temperature = lambda target, *args: state.update(temp=target)
        obj.ppms_environment_controller = remote
        obj._read_ppms_live = lambda: dict(field_oe=state['field'], temperature_k=state['temp'], field_status='StableDriven', temperature_status='Stable')
        obj._apply_ppms_environment_readback = lambda data: None
        obj.post_ui = lambda callback: callback()
        obj.thread_log = lambda text: None
        # read_back: the PPMS scans read OUTP? back after the off (2026-10-18).
        obj._stop_ppms_transport_source = lambda **_options: events.append(('off',))
        obj._configure_ppms_transport_scan = lambda config: events.append(('configure', config['current_rms_ma']))
        obj._update_ppms_transport_current = lambda config: events.append(('amplitude', config['current_rms_ma']))
        obj._ppms_zero_field_after_interrupted_scan = lambda *args: events.append(('zero',))
        obj._ppms_field_scan_worker = lambda *args: events.append(('plane', state['angle'], state['temp']))
        class Motor:
            def __init__(self, _): pass
            def read(self): return {'angle_deg': state['angle'], 'status': 'AtTarget'}
            def move_and_verify(self, target, slowdown, cancelled, index_target=None):
                if cancelled(): raise RuntimeError('cancelled')
                self_read = state['angle']
                assert abs(target-self_read) <= 1
                state['angle'] = target
                events.append(('move', target))
        settings = dict(nested=dict(angle=(26., 27.), temperature=(300., 301.)), slowdown=14,
                        temperature_rate=1., temperature_approach=1, current_rms_ma=.001)
        return obj, Motor, settings, events

    def run_worker(self, obj, motor, settings):
        clock = iter(range(10000))
        with patch.object(app, 'PPMSMotorDebug', motor), patch.object(app.time, 'monotonic', lambda: next(clock)):
            obj._ppms_nested_scan_worker([(1,1,1,0.)], 100., 0., 1, settings)

    def recording_stop(self, obj, events, stop_on_delay=False):
        """The scan's stop event, recording each wait of a second or more
        (the Wait s delay; the readback polls wait 0.5 s)."""
        class Stop(threading.Event):
            def wait(inner, timeout=None):
                if timeout is not None and timeout >= 1:
                    events.append(('delay', timeout))
                    if stop_on_delay:
                        inner.set()
                        return True
                return False
        obj.ppms_field_scan_stop_event = Stop()

    def test_the_zurich_channels_have_a_noise_floor(self):
        settled = app.CombinedControlApp._ppms_first_point_settled
        # A weak 3rd harmonic (nV) wandering by 100 % between windows, on a
        # 10 mV input range: within 0.2 % of the range, so settled.
        previous = {"zurich_demod3_x_v": 2e-9, "zurich_demod3_y_v": 1e-9, "zurich_input_range_v": 0.01}
        current = {"zurich_demod3_x_v": 4e-9, "zurich_demod3_y_v": -1e-9, "zurich_input_range_v": 0.01}
        self.assertTrue(settled(previous, current))
        # Without a range (none read) it is still judged on 2 % of R.
        self.assertFalse(settled({k: v for k, v in previous.items() if "range" not in k},
                                 {k: v for k, v in current.items() if "range" not in k}))

    def test_first_point_repeats_windows_until_two_agree(self):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.post_ui = lambda callback: None
        obj.thread_log = lambda message: None
        def sample(x):
            return dict(sr830_8_x_v=x, sr830_8_y_v=0., sr830_8_sensitivity_index=17)
        obj._average_ppms_transport_sample = lambda f, l, d: sample(next(values))
        values = iter([1.6e-3, 2.4e-3, 2.62e-3, 2.63e-3, 2.63e-3])
        result, windows = obj._acquire_ppms_first_point(317.3, ("830_a",), 1.)
        self.assertEqual(windows, 4)                      # 2.62 -> 2.63 mV agrees within 2 %
        self.assertEqual(result["sr830_8_x_v"], 2.63e-3)  # the last window is kept
        # A channel sitting at zero settles on the full-scale floor, not on 2 % of ~0.
        values = iter([1e-9, 2e-9, 1e-9])
        result, windows = obj._acquire_ppms_first_point(317.3, ("830_a",), 1.)
        self.assertEqual(windows, 2)
        # Never settling keeps the last window after the cap.
        values = iter([i * 1e-3 for i in range(1, 20)])
        result, windows = obj._acquire_ppms_first_point(317.3, ("830_a",), 1.)
        self.assertEqual(windows, app.PPMS_FIRST_POINT_MAX_WINDOWS)
        self.assertEqual(result["sr830_8_x_v"], app.PPMS_FIRST_POINT_MAX_WINDOWS * 1e-3)


if __name__ == '__main__': unittest.main()
