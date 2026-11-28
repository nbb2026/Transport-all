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
        self.assertIn('"Transport_MOKE_log_%Y%m%d_%H%M%S.txt"', source())
        self.assertNotIn('"Transport_log_', source())

    def test_every_suggested_or_made_name_carries_date_time_and_microseconds(self):
        """The recording's suggested name had date and time only; the images, the scan files and the image
        folders had the microseconds too.  The program log's name and the clock in the log lines are the two
        other formats, on purpose."""
        import re
        stamps = re.findall(r"strftime\(([\"'])(.*?)\1\)", source())
        formats = sorted({text for _quote, text in stamps})
        self.assertEqual(formats, ["%H:%M:%S", "%H:%M:%S.%f", "%Y%m%d_%H%M%S_%f", "Transport_MOKE_log_%Y%m%d_%H%M%S.txt"])

    def test_the_scans_keep_the_names_the_analysis_reads(self):
        text = source()
        for name in ("Current_Field_ROI_{timestamp}.csv", "Voltage_vs_ROI_mean_{timestamp}.csv", "MOKE_scan_parameters_{timestamp}.log",
                     "_CameraLive_8bit_{timestamp}.avi", "CIDWM_{stamp}_raw16.tiff"):
            self.assertIn(name, text)

if __name__ == "__main__":
    unittest.main()
