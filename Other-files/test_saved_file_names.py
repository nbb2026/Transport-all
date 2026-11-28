"""How this program names what it saves (user, 2026-11-28: "check the RT code and standardize the file-saving logic
across all parts of the code and ensure that the file and variable naming conventions are consistent", then "do the
same for PPMS, MOKE and FMR").

The files a scan makes keep their names, and the CSV's columns theirs: the analysis scripts read them.  What is one
rule now: a run's CSV has one writer, its recorder; a copy saved by hand is suggested under the run's own name; the
program log is named after this program.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_ppms_motor_debug import app


def source() -> str:
    with open(app.__file__, encoding="utf-8") as handle:
        return handle.read()


def window(**state):
    made = app.CombinedControlApp.__new__(app.CombinedControlApp)
    made.__dict__.update(root=None, **state)
    return made


class SavedFileNames(unittest.TestCase):
    def test_the_program_log_is_named_after_this_program(self):
        self.assertIn('"Transport_PPMS_log_%Y%m%d_%H%M%S.txt"', source())
        self.assertNotIn('"Transport_log_', source())

    def test_a_runs_csv_has_one_writer(self):
        text = source()
        self.assertNotIn("ppms_live_csv_path", text)
        self.assertNotIn("def _append_ppms_live_csv", text)
        self.assertIn("recorder.append_row(row)", text)

    def test_save_csv_as_suggests_the_runs_own_name(self):
        with tempfile.TemporaryDirectory() as parent:
            folder = Path(parent) / "B24_field_01"
            folder.mkdir()
            page = window(ppms_field_scan_rows=[dict(field=1)], ppms_run_folder=folder)
            with patch.object(app.filedialog, "asksaveasfilename", return_value="") as ask:
                page.save_ppms_field_scan_csv()
            self.assertEqual((ask.call_args.kwargs["initialfile"], ask.call_args.kwargs["initialdir"]), ("B24_field_01_copy.csv", str(folder)))
        # No run folder to name it after: the dated name, as before.
        page = window(ppms_field_scan_rows=[dict(field=1)], ppms_run_folder=None)
        with patch.object(app.filedialog, "asksaveasfilename", return_value="") as ask:
            page.save_ppms_field_scan_csv()
        self.assertRegex(ask.call_args.kwargs["initialfile"], r"^PPMS_field_scan_\d{8}_\d{6}\.csv$")
        self.assertNotIn("initialdir", ask.call_args.kwargs)

if __name__ == "__main__":
    unittest.main()
