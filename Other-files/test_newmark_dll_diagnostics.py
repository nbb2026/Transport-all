"""Newmark DLL loading messages (user, 2026-10-17: the first run on the lab
PC stopped with "Windows error 126" because PerformaxCom.dll and SiUSBXp.dll
had not been copied beside the script yet).  The program says which DLL is
missing or 32-bit, and where to put the pair and get it; the standalone
script's own tests are on main.  Fake DLL files with a PE header only; no
real DLL is loaded on any OS (ctypes.WinDLL is a stand-in)."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_ppms_motor_debug import app

def fake_dll(path, bits):
    """A file with just the PE header fields the check reads."""
    header = bytearray(512)
    header[:2] = b"MZ"
    header[0x3C:0x40] = (0x80).to_bytes(4, "little")
    header[0x80:0x84] = b"PE\0\0"
    header[0x84:0x86] = (0x8664 if bits == 64 else 0x14C).to_bytes(2, "little")
    Path(path).write_bytes(bytes(header))


class FakeWinDLL:
    def __init__(self, missing=False, wrong_bits=False):
        self.loaded, self.missing, self.wrong_bits = [], missing, wrong_bits

    def __call__(self, path):
        self.loaded.append(str(path))
        if self.missing:
            raise FileNotFoundError(f"Could not find module '{path}' (or one of its dependencies)")
        if self.wrong_bits:
            error = OSError("[WinError 193] %1 is not a valid Win32 application")
            error.winerror = 193
            raise error
        return object()


class BitsTests(unittest.TestCase):
    def test_bits_from_the_pe_header(self):
        with tempfile.TemporaryDirectory() as folder:
            for bits in (32, 64):
                fake_dll(Path(folder) / f"d{bits}.dll", bits)
                self.assertEqual(app.newmark_dll_bits(Path(folder) / f"d{bits}.dll"), bits)
            (Path(folder) / "text.dll").write_text("not a dll")
            self.assertIsNone(app.newmark_dll_bits(Path(folder) / "text.dll"))
            self.assertIsNone(app.newmark_dll_bits(Path(folder) / "missing.dll"))


class ProgramLoaderTests(unittest.TestCase):
    def load(self, folder, win_dll):
        with mock.patch.object(app, "newmark_dll_folder", return_value=folder), \
                mock.patch.object(app.ctypes, "WinDLL", win_dll, create=True), \
                mock.patch.object(app.os, "add_dll_directory", lambda path: path, create=True), \
                mock.patch.object(app, "newmark_declare_functions", lambda dll: dll), \
                mock.patch.object(app, "_NEWMARK_DLL_DIRECTORIES", []):
            return app.newmark_load_performax()

    def test_nothing_beside_the_program(self):
        win_dll = FakeWinDLL(missing=True)
        with self.assertRaises(app.NewmarkStageError) as raised:
            self.load(None, win_dll)
        text = str(raised.exception)
        self.assertIn("it is not in the program's folder", text)
        self.assertIn("USB 64-bit DLL v2.06", text)

    def test_a_32_bit_dll_found_elsewhere_is_not_called_missing(self):
        with self.assertRaises(app.NewmarkStageError) as raised:
            self.load(None, FakeWinDLL(wrong_bits=True))
        self.assertIn("not a 64-bit DLL", str(raised.exception))
        self.assertNotIn("was not found", str(raised.exception))

    def test_siusbxp_missing_and_32_bit(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            fake_dll(folder / "PerformaxCom.dll", 64)
            with self.assertRaises(app.NewmarkStageError) as raised:
                self.load(folder, FakeWinDLL())
            self.assertIn("but SiUSBXp.dll is not", str(raised.exception))
            fake_dll(folder / "SiUSBXp.dll", 32)
            with self.assertRaises(app.NewmarkStageError) as raised:
                self.load(folder, FakeWinDLL())
            self.assertIn("SiUSBXp.dll is a 32-bit DLL", str(raised.exception))

    def test_the_64_bit_pair_loads(self):
        with tempfile.TemporaryDirectory() as name:
            folder = Path(name)
            fake_dll(folder / "PerformaxCom.dll", 64)
            fake_dll(folder / "SiUSBXp.dll", 64)
            win_dll = FakeWinDLL()
            _dll, path = self.load(folder, win_dll)
            self.assertEqual(path, str(folder / "PerformaxCom.dll"))
            self.assertEqual(win_dll.loaded, [str(folder / "SiUSBXp.dll"), str(folder / "PerformaxCom.dll")])


if __name__ == "__main__":
    unittest.main()
