"""Offline tests of the actual PPMS completion and shutdown callbacks."""
from concurrent.futures import Future
import threading
import unittest
from unittest.mock import Mock, patch
from test_ppms_motor_debug import app
from test_ppms_motor_debug import Array
import types


class CurrentCallbacks(unittest.TestCase):

    def test_no_range_change_without_overload_for_either_lockin(self):
        obj = self.make_app()
        obj.ppms_instrument_controllers = {
            key: Mock(lock=threading.RLock()) for key in ('830_a', '830_b')}
        obj._ppms_query_numbers = Mock(return_value=(13,))
        obj._set_connection_indicator = Mock()
        scale = app.NONLOCAL_SR830_FULL_SCALE_V[13]
        for key in ('830_a', '830_b'):
            # Without an overload the range never widens; at/above 10 % it never narrows either.
            for magnitude in (.10 * scale, .5 * scale, .98 * scale, 1.):
                for _ in range(6):
                    self.assertEqual(obj._ppms_autorange_sr830(key, magnitude, 0), 0.)
            obj.ppms_instrument_controllers[key].instrument.write.assert_not_called()

    def test_low_signal_narrows_one_code_after_three_settled_readings(self):
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        controller.instrument.query.return_value = '12'
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._ppms_query_numbers = Mock(side_effect=[(13,), (13,), (13,), (10,), (12,), (12,), (12,), (12,)])
        obj._set_connection_indicator = Mock()
        # Under 1 % of the range (user, 2026-11-16; the rule was 10 %).
        small = .009 * app.NONLOCAL_SR830_FULL_SCALE_V[13]
        self.assertEqual(obj._ppms_autorange_sr830('830_a', small, 0), 0.)
        self.assertEqual(obj._ppms_autorange_sr830('830_a', small, 0), 0.)
        controller.instrument.write.assert_not_called()
        self.assertEqual(obj._ppms_autorange_sr830('830_a', small, 0), 5.)   # third reading: one code down
        controller.instrument.write.assert_called_once_with('SENS 12')
        # Cool-down: three more small readings do not step again.
        for _ in range(3):
            self.assertEqual(obj._ppms_autorange_sr830('830_a', small, 0), 0.)
        controller.instrument.write.assert_called_once()

    def test_down_range_skipped_when_unlocked_disabled_or_in_scan_window(self):
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._ppms_query_numbers = Mock(return_value=(13,))
        obj._set_connection_indicator = Mock()
        small = 1e-9
        for _ in range(5):
            obj._ppms_autorange_sr830('830_a', small, 8)                    # reference unlocked
            obj._ppms_autorange_sr830('830_a', small, 0, enabled=False)     # excitation off
            obj._ppms_autorange_sr830('830_a', small, 0, allow_down=False)  # inside a scan point
        controller.instrument.write.assert_not_called()

    def test_reading_above_one_percent_resets_the_count(self):
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._ppms_query_numbers = Mock(return_value=(13,))
        obj._set_connection_indicator = Mock()
        scale = app.NONLOCAL_SR830_FULL_SCALE_V[13]
        for magnitude in (.005 * scale, .005 * scale, .3 * scale, .005 * scale, .005 * scale):
            self.assertEqual(obj._ppms_autorange_sr830('830_a', magnitude, 0), 0.)
        controller.instrument.write.assert_not_called()

    def test_between_one_and_ten_percent_the_range_is_kept(self):
        """User, 2026-11-16: "when the measured voltage is below 1%, then
        decrease the range"; 9 % and 2 % stepped it down while the rule
        was 10 %."""
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._ppms_query_numbers = Mock(return_value=(13,))
        obj._set_connection_indicator = Mock()
        scale = app.NONLOCAL_SR830_FULL_SCALE_V[13]
        for fraction in (.09, .02, .011):
            for _ in range(10):
                self.assertEqual(obj._ppms_autorange_sr830('830_a', fraction * scale, 0), 0.)
        controller.instrument.write.assert_not_called()

    def test_overload_steps_up_one_code_per_settle(self):
        for key in ('830_a', '830_b'):
            with self.subTest(key=key):
                obj = self.make_app()
                controller = Mock(lock=threading.RLock())
                controller.instrument.query.side_effect = ['14', '15']
                obj.ppms_instrument_controllers = {key: controller}
                obj._ppms_query_numbers = Mock(side_effect=[
                    (13,), (10,),   # SENS?, OFLT?: overloaded -> one code up
                    (14,), (10,),   # still overloaded -> one more
                    (15,)])         # clear: no change
                obj._set_connection_indicator = Mock()
                self.assertEqual(obj._ppms_autorange_sr830(key, 0., 4), 5.)
                self.assertEqual(obj._ppms_autorange_sr830(key, 0., 4), 5.)
                self.assertEqual(obj._ppms_autorange_sr830(key, 1e-5, 0), 0.)
                self.assertEqual([c.args[0] for c in controller.instrument.write.call_args_list], ['SENS 14', 'SENS 15'])

    def test_connection_initializes_sr830_and_checks_settings(self):
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        controller.connect.return_value = 'SR830'
        obj.ppms_instrument_controllers = {'830_b': controller}
        obj._ppms_write_sr830_checked = Mock()
        values = {'FMOD': 0, 'RSLP': 1, 'HARM': 2, 'ISRC': 1, 'IGND': 0,
                  'ICPL': 0, 'ILIN': 0, 'SYNC': 0, 'SENS': 9, 'OFLT': 10, 'OFSL': 1, 'RMOD': 1, 'PHAS': 0}
        obj._ppms_query_numbers = Mock(side_effect=lambda key, query, n: (values[query[:-1]],))
        self.assertEqual(obj._connect_and_initialize_ppms_device('830_b', 'GPIB0::10::INSTR', 2), 'SR830')
        obj._ppms_write_sr830_checked.assert_any_call('830_b', 'HARM 2')
        obj._ppms_write_sr830_checked.assert_any_call('830_b', 'ISRC 1')
        obj._ppms_write_sr830_checked.assert_any_call('830_b', 'ILIN 0')
        obj._ppms_write_sr830_checked.assert_any_call('830_b', 'SYNC 0')
        self.assertEqual(obj._ppms_query_numbers.call_count, 13)
        controller.disconnect.assert_not_called()

    def test_initialization_failure_disconnects_instead_of_claiming_connected(self):
        obj = self.make_app()
        controller = Mock()
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._initialize_ppms_sr830 = Mock(side_effect=RuntimeError('readback mismatch'))
        with self.assertRaisesRegex(RuntimeError, 'readback mismatch'):
            obj._connect_and_initialize_ppms_device('830_a', 'GPIB0::8::INSTR', 1)
        controller.disconnect.assert_called_once()

    def test_indicator_overload_red_then_recovers(self):
        obj = self.make_app()
        canvas = Mock()
        obj.instrument_connection_indicators = {"ppms_ref_830_a": (canvas, 1)}
        for connected, fault, color in ((True, True, "#e53935"),
                                        (True, False, "#20b15a"),
                                        (False, False, "#9aa0a6")):
            obj._set_connection_indicator("ppms_ref_830_a", connected, fault=fault)
            self.assertEqual(canvas.itemconfigure.call_args.kwargs["fill"], color)

    def test_autorange_status_reports_the_selected_full_scale(self):
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        controller.instrument.query.return_value = '14'
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._ppms_query_numbers = Mock(side_effect=[(13,), (10,)])
        obj._set_connection_indicator = Mock()
        obj.ppms_sr830_range_vars = {'830_a': Mock()}
        obj._ppms_autorange_sr830('830_a', 0., 4)          # overload: 50 uV -> 100 uV
        self.assertEqual(obj.ppms_sr830_range_vars['830_a'].set.call_args.args[0], 'Autorange 100 uV')
        self.assertEqual(
            [app.CombinedControlApp._format_sr830_full_scale(i) for i in (0, 13, 20, 26, None)],
            ['2 nV', '50 uV', '10 mV', '1 V', '--'])

    def test_autorange_uses_verified_sens_and_time_constant(self):
        obj = self.make_app()
        instrument = Mock()
        instrument.query.return_value = "14"
        obj.ppms_instrument_controllers = {"830_a": types.SimpleNamespace(instrument=instrument, lock=threading.RLock(), label="SR830-1")}
        obj._ppms_query_numbers = Mock(side_effect=[(13,), (10,)])
        obj._set_connection_indicator = Mock()
        obj.ppms_sr830_status_vars = {"830_a": Mock()}
        self.assertEqual(obj._ppms_autorange_sr830("830_a", 1., 1), 5.)
        instrument.write.assert_called_once_with("SENS 14")
        instrument.query.assert_called_once_with("SENS?")
        self.assertIn("OVERLOAD", obj.ppms_sr830_status_vars["830_a"].set.call_args.args[0])
        obj._set_connection_indicator.assert_called_with("ppms_ref_830_a", False, fault=True)

    def test_overload_at_maximum_range_raises(self):
        obj = self.make_app()
        instrument = Mock()
        obj.ppms_instrument_controllers = {"830_a": types.SimpleNamespace(instrument=instrument, lock=threading.RLock(), label="SR830-1")}
        obj._ppms_query_numbers = Mock(side_effect=[(26,)])
        obj._set_connection_indicator = Mock()
        obj.ppms_sr830_status_vars = {"830_a": Mock()}
        with self.assertRaisesRegex(app.PPMSLockinRangeError, "maximum sensitivity"):
            obj._ppms_autorange_sr830("830_a", 1., 4)
        instrument.write.assert_not_called()

    def test_overload_ranges_up_even_without_excitation(self):
        obj = self.make_app()
        instrument = Mock()
        instrument.query.return_value = "14"
        obj.ppms_instrument_controllers = {"830_a": types.SimpleNamespace(instrument=instrument, lock=threading.RLock(), label="SR830-1")}
        obj._ppms_query_numbers = Mock(side_effect=[(13,), (10,)])
        obj._set_connection_indicator = Mock()
        obj.ppms_sr830_status_vars = {"830_a": Mock()}
        self.assertEqual(obj._ppms_autorange_sr830("830_a", 20e-6, 1, enabled=False), 5.)
        instrument.write.assert_called_once_with("SENS 14")

    def test_overloaded_samples_are_excluded_from_the_mean(self):
        obj = self.make_app()
        obj.ppms_field_scan_stop_event = Mock(is_set=Mock(return_value=False), wait=Mock(return_value=False))
        obj.closing = False
        good = dict(sr830_8_x_v=1., sr830_8_y_v=0., sr830_8_frequency_hz=317.3, sr830_8_reference_valid=True, sr830_8_overload=False)
        bad = dict(good, sr830_8_x_v=100., sr830_8_overload=True)
        obj._read_ppms_transport_sample = Mock(side_effect=[bad, good, bad, good])
        with patch.object(app.time, 'monotonic', side_effect=[0., .2, .4, .6, 1.2, 1.2]):
            result = obj._average_ppms_transport_sample(317.3, ("830_a",), 1.)
        self.assertEqual(result["sr830_8_x_v"], 1.)
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["overloaded_sample_count"], 2)

    def test_range_switch_discards_old_samples(self):
        obj = self.make_app()
        obj.ppms_field_scan_stop_event = Mock(is_set=Mock(return_value=False), wait=Mock(return_value=False))
        obj._read_ppms_transport_sample = Mock(side_effect=[
            {"range_settle_s": 5., "sr830_8_x_v": 999., "sr830_8_y_v": 999.},
            {"range_settle_s": 0., "sr830_8_x_v": 2., "sr830_8_y_v": 4.}])
        with patch.object(app.time, "monotonic", side_effect=[0., 0., 5., 7., 7.]):
            result = obj._average_ppms_transport_sample(317.3, ("830_a",), 1.)
        self.assertEqual(result["sample_count"], 1)
        self.assertEqual(result["sr830_8_x_v"], 2.)
        obj.ppms_field_scan_stop_event.wait.assert_called_once_with(5.)

    def test_window_averages_two_lockins_and_records_count(self):
        obj = self.make_app()
        obj.ppms_field_scan_stop_event = Mock(is_set=Mock(return_value=False), wait=Mock(return_value=False))
        samples = []
        for value in (1., 3.):
            sample = {"6221_output_on": True}
            for address in (8, 10):
                sample.update({f"sr830_{address}_x_v": value, f"sr830_{address}_y_v": value*2,
                               f"sr830_{address}_frequency_hz": 317.3, f"sr830_{address}_reference_valid": True})
            samples.append(sample)
        obj._read_ppms_transport_sample = Mock(side_effect=samples)
        with patch.object(app.time, "monotonic", side_effect=(0., .4, 1.2, 1.2)):
            result = obj._average_ppms_transport_sample(317.3, ("830_a", "830_b"), 1.)
        self.assertEqual(result["sample_count"], 2)
        for address in (8, 10):
            self.assertEqual(result[f"sr830_{address}_x_v"], 2.)
            self.assertEqual(result[f"sr830_{address}_y_v"], 4.)
        self.assertEqual(result["acquisition_elapsed_s"], 1.2)

    def test_window_cancel_or_bad_reference_does_not_return_partial_point(self):
        obj = self.make_app()
        obj.ppms_field_scan_stop_event.set()
        obj._read_ppms_transport_sample = Mock()
        with self.assertRaises(app.PPMSScanCancelled):
            obj._average_ppms_transport_sample(317.3, ("830_a",), 1.)
        obj._read_ppms_transport_sample.assert_not_called()
        obj.ppms_field_scan_stop_event.clear()
        obj._read_ppms_transport_sample.return_value = {"sr830_8_reference_valid": False}
        with self.assertRaisesRegex(RuntimeError, "reference unlocked"):
            obj._average_ppms_transport_sample(317.3, ("830_a",), 1.)

    def make_app(self):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.root, obj.closing = None, False
        obj.ppms_environment_busy = False
        obj.ppms_connection_var = Mock()
        obj._require_ppms_control_ready = Mock()
        obj._set_ppms_environment_ui = Mock()
        obj._apply_ppms_environment_readback = Mock()
        obj.ppms_field_scan_stop_event = threading.Event()
        obj.post_ui = lambda callback: callback()
        obj.ppms_executor = Mock()
        self.future = Future()
        obj.ppms_executor.submit.return_value = self.future
        return obj

    def shutdown(self, state):
        obj = self.make_app()
        obj.ppms_instrument_controllers = {}
        for key in ("6221", "2400"):
            controller = Mock()
            controller.lock = threading.RLock()
            controller.instrument = Mock() if key == "6221" else None
            obj.ppms_instrument_controllers[key] = controller
        obj._ppms_query_numbers = Mock(return_value=(state,))
        # The error dialog opens from root.after (review, 2026-10-18).
        obj.root = types.SimpleNamespace(after=lambda _ms, show: show())
        obj.ppms_sources_off()
        self.assertTrue(obj.ppms_field_scan_stop_event.is_set())
        worker = obj.ppms_executor.submit.call_args.args[0]
        with patch.object(app.messagebox, "showerror") as popup:
            try:
                result = worker()
            except Exception as error:
                self.future.set_exception(error)
            else:
                self.future.set_result(result)
            self.assertEqual(popup.call_count, int(state != 0))
        obj.ppms_instrument_controllers["6221"].safe_output_off.assert_called_once()
        return obj

    def test_shutdown_confirms_only_connected_source(self):
        obj = self.shutdown(0)
        obj.ppms_connection_var.set.assert_called_with("6221 output OFF confirmed by readback")

    def test_shutdown_on_readback_is_not_reported_as_success(self):
        obj = self.shutdown(1)
        self.assertIn("not confirmed", obj.ppms_connection_var.set.call_args.args[0])

    def test_cancel_prevents_further_start_command(self):
        obj = self.make_app()
        source = Mock()
        source.lock = threading.RLock()
        obj.ppms_instrument_controllers = {"6221": source}
        obj.ppms_field_scan_stop_event.set()
        with self.assertRaises(app.PPMSScanCancelled):
            obj._ppms_write_6221_checked("SOUR:WAVE:INIT")
        source.instrument.write.assert_not_called()

    def test_zero_current_skips_sr830_range_writes(self):
        obj = self.make_app()
        controller = Mock(lock=threading.RLock())
        controller.instrument.query.return_value = '11'
        obj.ppms_instrument_controllers = {'830_a': controller}
        obj._ppms_query_numbers = Mock(return_value=(10,))
        obj._set_connection_indicator = Mock()
        # Without an overload nothing is written while the excitation is off ...
        self.assertEqual(obj._ppms_autorange_sr830('830_a', 0., 0, enabled=False), 0.)
        controller.instrument.write.assert_not_called()
        # ... but an overload still ranges up one code.
        self.assertEqual(obj._ppms_autorange_sr830('830_a', 0., 7, enabled=False), 5.)
        controller.instrument.write.assert_called_once_with('SENS 11')

    def test_live_current_readback_states(self):
        obj = self.make_app()
        source = Mock()
        source.lock = threading.RLock()
        obj.ppms_instrument_controllers = {"6221": source}
        source.instrument = None
        self.assertEqual(obj._read_ppms_current_display(), "Not connected")
        source.instrument = Mock()
        obj._ppms_query_numbers = Mock(return_value=(0,))
        self.assertEqual(obj._read_ppms_current_display(), "OFF / 0 mA")
        self.assertTrue(obj.ppms_6221_zero_output)
        obj._ppms_query_numbers.assert_called_once_with("6221", "OUTP?", 1)
        obj._ppms_query_numbers.side_effect = [(1,), (0.001414213562373095,), (317.3,), (8,)]
        text = obj._read_ppms_current_display()
        self.assertIn("ON / sine setpoint 1 mA RMS / 317.3 Hz", text)
        self.assertFalse(obj.ppms_6221_zero_output)
        obj._ppms_query_numbers.side_effect = [(1,), (0.,), (317.3,), (0,)]
        obj._read_ppms_current_display()
        self.assertTrue(obj.ppms_6221_zero_output)
        self.assertIn("Compliance", text)
        self.assertTrue(text.startswith("⚠ Compliance hit"))
        obj._ppms_query_numbers.side_effect = [(1,), (0.001414213562373095,), (317.3,), (0,)]
        self.assertNotIn("Compliance hit", obj._read_ppms_current_display())
        obj.ppms_last_current_trip = True
        obj._ppms_query_numbers.side_effect = [(0,)]
        self.assertEqual(obj._read_ppms_current_display(), "OFF / 0 mA; compliance hit in the last scan")
        obj._ppms_query_numbers.side_effect = TimeoutError("timeout")
        self.assertTrue(obj._read_ppms_current_display().startswith("Unknown"))


if __name__ == "__main__":
    unittest.main()
