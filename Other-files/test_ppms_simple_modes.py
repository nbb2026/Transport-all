"""Four-mode launch validation without Tk or instrument writes."""
import threading
import tempfile
import csv
from pathlib import Path
import ast
import inspect
import textwrap
import types
import unittest
from unittest.mock import Mock, patch
from test_ppms_motor_debug import app


class ModeTests(unittest.TestCase):

    def launch(self, mode, values, confirm=True, cancel_folder=False, filename="", existing=None, selected=None, speed=14,
               expect_error=None):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        obj.ppms_field_scan_running = obj.ppms_environment_busy = False
        obj._require_ppms_control_ready = Mock()
        obj.ppms_simple_mode = Mock(get=lambda: mode)
        obj.ppms_simple_range = [Mock(get=lambda v=v: v) for v in values]
        obj.ppms_temperature_scan_range = [Mock(get=lambda v=v: v) for v in (300, 290, 5)]
        obj.ppms_temperature_delay_var = Mock(get=lambda: getattr(self, "temperature_delay", "0"))
        defaults = dict(ppms_acquisition_time_var=1, ppms_field_target_var=100, ppms_temperature_target_var=300,
            ppms_motor_target_var=26, ppms_field_scan_stable_var=0,
            ppms_field_rate_var=100, ppms_field_approach_var="No overshoot",
            ppms_transport_current_var=.001, ppms_transport_frequency_var=13.7,
            ppms_transport_compliance_var=50, ppms_transport_harmonic_a_var=1,
            ppms_transport_harmonic_b_var=2, ppms_motor_confirm_var=True,
            ppms_temperature_rate_var=1, ppms_temperature_approach_var="No overshoot",
            ppms_motor_speed_var=speed)
        for name, value in defaults.items():
            setattr(obj, name, Mock(get=lambda v=value: v))
        obj.ppms_environment_controller = types.SimpleNamespace(backend=app.PPMS_QDINSTRUMENT_BACKEND)
        obj.ppms_instrument_controllers = {k: types.SimpleNamespace(connected=True, resource_name=f"GPIB0::{address}::INSTR")
            for k, address in (("6221", 30), ("830_a", 8), ("830_b", 9))}
        if selected is not None:
            obj.ppms_lockin_selection = {key: Mock(get=lambda key=key: key in selected)
                                        for key in ('830_a', '830_b', 'zurich')}
            obj.zurich_controller = types.SimpleNamespace(mfli_connected='zurich' in selected, mfli_has_multi_demod=lambda: True)
            for key in ('830_a', '830_b'):
                obj.ppms_instrument_controllers[key].connected = key in selected
        obj.ppms_last_readback = dict(temperature_k=300, field_oe=100)
        obj.ppms_field_scan_stop_event = threading.Event()
        for name in ("_redraw_ppms_transport_plot", "_update_ppms_control_ui", "ppms_executor",
                     "ppms_field_scan_progress", "ppms_field_scan_eta_var", "ppms_field_scan_status_var", "ppms_transport_status_var"):
            setattr(obj, name, Mock())
        obj.root = None
        obj.thread_log = Mock()
        self.durations = []
        obj._format_scan_duration = lambda seconds: (self.durations.append(seconds), f"{seconds:g} s")[1]
        order = []
        def answer(*args, **kwargs):
            order.append("confirm")
            self.last_question = args[1] if len(args) > 1 else kwargs.get("message", "")
            return confirm
        with tempfile.TemporaryDirectory() as folder, patch.object(app.simpledialog, "askstring", return_value=filename), patch.object(app.messagebox, "askyesno", side_effect=answer), patch.object(app.filedialog, "askdirectory", side_effect=lambda **kw: (order.append("folder") or ("" if cancel_folder else folder))), patch.object(app.messagebox, "showerror") as error:
            if existing:
                (Path(folder) / existing).write_text("original", encoding="utf-8")
            obj.start_ppms_field_scan()
            if expect_error is not None:
                self.assertIn(expect_error, error.call_args.args[1])
                obj.ppms_executor.submit.assert_not_called()
                return None
            self.assertFalse(error.called, error.call_args)
            self.assertEqual(order, ["confirm", "folder"] if confirm else ["confirm"])
            if not confirm or cancel_folder or filename is None:
                obj.ppms_executor.submit.assert_not_called()
                self.assertFalse(obj.ppms_field_scan_running)
                self.assertEqual(list(Path(folder).iterdir()), [])
                return
            if existing:
                self.assertEqual((Path(folder) / existing).read_text(encoding="utf-8"), "original")
        args = obj.ppms_executor.submit.call_args.args
        return obj, args[1], args[-1]

    def test_live_csv_appends_rows_with_one_header(self):
        obj = app.CombinedControlApp.__new__(app.CombinedControlApp)
        with tempfile.TemporaryDirectory() as folder:
            obj.ppms_live_csv_path = Path(folder) / "scan.csv"
            obj.ppms_live_csv_fields = None
            obj._append_ppms_live_csv(dict(field=1, x=2))
            obj._append_ppms_live_csv(dict(field=3, x=4))
            before = obj.ppms_live_csv_path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, "channels changed"):
                obj._append_ppms_live_csv(dict(field=5, y=6))
            self.assertEqual(obj.ppms_live_csv_path.read_bytes(), before)
            with obj.ppms_live_csv_path.open(encoding="utf-8-sig") as handle:
                self.assertEqual(list(csv.DictReader(handle)), [dict(field="1", x="2"), dict(field="3", x="4")])


if __name__ == "__main__":
    unittest.main()
