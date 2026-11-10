"""Default save folders in a built Transport_all.exe (Windows .exe build,
user, 2026-11-10).  In a one-file build (PyInstaller or Nuitka) __file__ is
inside a temporary folder that is deleted when the program exits, so the
default results folders, and the folder dialogs' fallback start folder, are
beside the .exe there; for the .py they stay beside the .py, as before."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_ppms_motor_debug import app

ROOT = Path(__file__).resolve().parents[1]
RESULTS_FOLDERS = (
    "MAGNET_SCAN_RESULTS_DIRECTORY", "KEITHLEY_RESULTS_DIRECTORY", "CIDWM_SCAN_DIRECTORY",
    "NONLOCAL_RESULTS_DIRECTORY", "NONLOCAL_VI_RESULTS_DIRECTORY",
    "NONLOCAL_IV_SWEEP_RESULTS_DIRECTORY", "NONLOCAL_IV6221_RESULTS_DIRECTORY",
)


class ProgramDirectoryTests(unittest.TestCase):
    def test_the_py_program_saves_beside_itself(self):
        self.assertEqual(app.PROGRAM_DIRECTORY, ROOT)
        self.assertEqual(app.program_directory(), ROOT)

    def test_a_built_exe_saves_beside_the_exe(self):
        exe = Path(tempfile.gettempdir()) / "Lab PC" / "Transport_all.exe"
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "argv", [str(exe)]):
            self.assertEqual(app.program_directory(), exe.resolve().parent)

    def test_the_results_folders_are_beside_the_program(self):
        for name in RESULTS_FOLDERS:
            with self.subTest(name):
                folder = getattr(app, name)
                self.assertEqual(folder.parent, app.PROGRAM_DIRECTORY)
                self.assertTrue(folder.name.startswith("Transport_all_"), folder.name)

    def test_no_save_folder_comes_from_the_script_location(self):
        # __file__'s folder is still searched for bundled files (DLLs, icons).
        source = (ROOT / "Transport_all.py").read_text(encoding="utf-8")
        self.assertNotIn('Path(__file__).resolve().parent / f"{Path(__file__).stem}_', source)
        for line in ("self.camera_video_directory = PROGRAM_DIRECTORY",
                     "self.stfmr_lockin_save_directory = PROGRAM_DIRECTORY",
                     "initial_directory = PROGRAM_DIRECTORY"):
            self.assertIn(line, source)


if __name__ == "__main__":
    unittest.main()
