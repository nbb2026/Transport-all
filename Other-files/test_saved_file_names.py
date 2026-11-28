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
        self.assertIn('"Transport_FMR_log_%Y%m%d_%H%M%S.txt"', source())
        self.assertNotIn('"Transport_log_', source())

    def test_the_runs_keep_the_names_the_analysis_reads(self):
        text = source()
        for name in ('"STFMR_field_scan_"', '"FMR_field"', '"FMR_frequency"', 'STFMR_SAVED_CSV_PREFIX = "STFMR_saved_"'):
            self.assertIn(name, text)

    def test_a_copy_saved_by_hand_is_suggested_under_the_runs_own_name(self):
        for save, rows, where, dated in (("save_stfmr_fmr_results", "stfmr_fmr_rows", "stfmr_fmr_run_directory", r"^STFMR_FMR_\d{8}_\d{6}\.csv$"),
                                         ("save_stfmr_frequency_results", "stfmr_frequency_rows", "stfmr_frequency_run_directory",
                                          r"^STFMR_frequency_sweep_\d{8}_\d{6}\.csv$")):
            with self.subTest(save=save), tempfile.TemporaryDirectory() as parent:
                folder = Path(parent) / "FMR_field_20261128_101500"
                folder.mkdir()
                page = window(**{rows: [dict(index=1)], where: folder})
                with patch.object(app.filedialog, "asksaveasfilename", return_value="") as ask:
                    getattr(page, save)()
                self.assertEqual((ask.call_args.kwargs["initialfile"], ask.call_args.kwargs["initialdir"]),
                                 ("FMR_field_20261128_101500_copy.csv", str(folder)))
                # No run folder to name it after: the dated name, as before.
                page = window(**{rows: [dict(index=1)], where: None})
                with patch.object(app.filedialog, "asksaveasfilename", return_value="") as ask:
                    getattr(page, save)()
                self.assertRegex(ask.call_args.kwargs["initialfile"], dated)
                self.assertNotIn("initialdir", ask.call_args.kwargs)

if __name__ == "__main__":
    unittest.main()
