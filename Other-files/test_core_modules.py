"""Compatibility and isolated regression tests for the extracted core code."""

import datetime
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from test_ppms_motor_debug import app
from transport.core import scan_lifecycle, scan_recording, scan_sequences


class CoreImportsTests(unittest.TestCase):
    def test_legacy_scan_helpers_are_shared(self):
        self.assertIs(app.build_round_trip_values, scan_sequences.build_round_trip_values)
        self.assertIs(app.ppms_scan_axis, scan_sequences.ppms_scan_axis)
        self.assertIs(app.lakeshore_ramp_seconds, scan_sequences.lakeshore_ramp_seconds)

    def test_scan_planning_unchanged(self):
        self.assertEqual(app.ppms_scan_axis(0, 1, 0.4), (0.0, 0.4, 0.8, 1))
        self.assertEqual(app.ppms_scan_axis(1, 1, 0.1), (1,))
        self.assertEqual(app.lakeshore_ramp_seconds([0, 2, -1], 1), 5)

    def test_legacy_json_log_uses_application_clock(self):
        # The historical app datetime module is patchable, and the recorder
        # must continue to use that same clock after moving to core.
        class FixedClock(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.datetime(2026, 10, 18, 12, 34, 56, 789012)

        fake = types.SimpleNamespace(datetime=FixedClock)
        with mock.patch.object(app, "datetime_module", fake):
            actual = json.loads(app.scan_log_line("point_saved", {"index": 1}))
        direct = json.loads(scan_recording.scan_log_line("point_saved", {"index": 1},
                                                       datetime_class=FixedClock))
        self.assertEqual(actual, direct)
        self.assertTrue(actual["timestamp"].startswith("2026-10-18T12:34:56.789"))

    def test_file_name_rule_shared(self):
        self.assertEqual(app.scan_file_stem(" B1.csv "), "B1")
        self.assertEqual(scan_recording.scan_file_stem(" B1.csv "), "B1")
        for invalid in ("CON.txt", "a/b", "x."):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                app.scan_file_stem(invalid)

    def test_scan_close_handoff_is_shared(self):
        self.assertIs(app.ScanCloseHandoff, scan_lifecycle.ScanCloseHandoff)
        done = []
        handoff = app.ScanCloseHandoff()
        handoff.begin()
        self.assertTrue(handoff.defer(lambda: done.append("closed")))
        self.assertEqual(done, [])
        handoff.end()
        self.assertEqual(done, ["closed"])
        self.assertFalse(handoff.defer(lambda: done.append("not scheduled")))

    def test_every_zero_is_attempted_after_a_failure(self):
        calls = []
        def fail():
            calls.append("first")
            raise RuntimeError("simulated readback failure")
        def safe():
            calls.append("second")
            return "not connected"
        result = app.zero_scan_outputs([("A", fail), ("B", safe)])
        self.assertEqual(calls, ["first", "second"])
        self.assertIn("zero FAILED", result["A"])
        self.assertEqual(result["B"], "not connected")
        self.assertIn("check it", app.scan_end_outputs_text(result, outputs=("A", "B")))


class RecordingCompatibilityTests(unittest.TestCase):
    def test_recorder_is_core_subclass_and_retains_application_metadata(self):
        self.assertTrue(issubclass(app.ScanRunRecorder, scan_recording.ScanRunRecorder))
        with tempfile.TemporaryDirectory() as tmp:
            recorder = app.ScanRunRecorder(Path(tmp), "PPMS", "sample", {"mode": "Field"})
            try:
                row = json.loads(recorder.log_path.read_text(encoding="utf-8").splitlines()[0])
                self.assertEqual(row["program"], "Transport_all.py")
                self.assertEqual(row["app_version"], app.APP_VERSION)
                recorder.append_row({"field": 1, "voltage": 2})
                self.assertEqual(recorder.rows_written, 1)
            finally:
                recorder.close("completed")

    def test_legacy_folder_patch_is_still_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(app, "make_scan_run_folder", wraps=app.make_scan_run_folder) as maker:
                recorder = app.ScanRunRecorder(Path(tmp), "PPMS", "sample")
            self.addCleanup(recorder.close, "completed")
            maker.assert_called_once_with(Path(tmp), "sample")

    def test_legacy_log_formatter_patch_is_still_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(app, "scan_log_line", wraps=app.scan_log_line) as formatter:
                recorder = app.ScanRunRecorder(Path(tmp), "PPMS", "sample", {"k": 1})
                self.assertTrue(recorder.note("recorded"))
                recorder.close("completed")
            self.assertGreaterEqual(formatter.call_count, 3)


if __name__ == "__main__":
    unittest.main()
