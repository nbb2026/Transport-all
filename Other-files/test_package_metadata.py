"""The modular package (user, 2026-11-01): pyproject.toml installs what the
program imports, under the program's own version, with a command that starts
it as `python Transport_all.py` does."""
import tomllib
import unittest
from pathlib import Path

from test_ppms_motor_debug import app

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


class PackageTests(unittest.TestCase):
    def test_the_version_is_the_programs(self):
        self.assertEqual(PROJECT["project"]["version"], app.APP_VERSION)

    def test_every_core_module_is_packaged(self):
        setup = PROJECT["tool"]["setuptools"]
        self.assertEqual(setup["py-modules"], ["Transport_all"])
        on_disk = sorted(".".join(path.parent.relative_to(ROOT).parts)
                         for path in (ROOT / "transport").rglob("__init__.py"))
        self.assertEqual(sorted(setup["packages"]), on_disk)

    def test_the_command_runs_the_program(self):
        module, _, function = PROJECT["project"]["scripts"]["transport-all"].partition(":")
        self.assertEqual(module, "Transport_all")
        self.assertTrue(callable(getattr(app, function)))
        self.assertEqual(function, "run")


if __name__ == "__main__":
    unittest.main()
