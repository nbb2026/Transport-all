"""Offline only: fake .NET methods; never load a vendor DLL or open a device."""
import importlib.util
import math
from pathlib import Path
import sys
import threading
import types
import unittest
from unittest.mock import patch

# The standalone SHHV & Switch application's module, in the transport package.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
source = ROOT / "transport" / "rt" / "app.py"
spec = importlib.util.spec_from_file_location("transport_motor_test", source)
app = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = app
spec.loader.exec_module(app)

# The scan-start window (user, 2026-11-23: only the expected time, bold red)
# is a modal Toplevel; the tests answer it through messagebox.askyesno, as
# before, and so still see the whole question that goes to the log.
app.ask_scan_start_window = app.ask_scan_start
app.ask_scan_start = lambda parent, title, question, expected, warning="", **options: app.messagebox.askyesno(title, question, parent=parent, **options)


class Type:
    def __init__(self, name, enum=False, ref=False):
        self.FullName, self.IsEnum, self.IsByRef = name, enum, ref
    def GetElementType(self):
        return Type(self.FullName, self.IsEnum)


class Method:
    def __init__(self, name, types_, invoke):
        self.Name, self.types, self.invoke = name, types_, invoke
        self.ReturnType = Type("System.Int32")
    def GetParameters(self):
        return [types.SimpleNamespace(ParameterType=t) for t in self.types]
    def Invoke(self, instrument, arguments):
        return self.invoke(arguments)
    def __str__(self):
        return self.Name


class Array:
    @classmethod
    def __class_getitem__(cls, _type):
        return lambda n: [None] * n


class MotorTests(unittest.TestCase):
    def setUp(self):
        self.writes = []
        self.logs = []
        self.angle, self.status, self.result = 25.004, "Stopped", 0
        self.modes = ["Move", "Index", "Define"]
        self.get = Method("GetPPMSItem", [Type("System.Int32"), Type("System.Double", ref=True), Type("System.Boolean")], self.read_fake)
        self.set = Method("SendPPMSCommand", [Type("System.String"), Type("System.String", ref=True), Type("System.String", ref=True), Type("System.Int32"), Type("System.Double")], self.write_fake)
        self.methods = [self.get, self.set]
        instrument = types.SimpleNamespace(GetType=lambda: types.SimpleNamespace(GetMethods=lambda: self.methods))
        self.controller = types.SimpleNamespace(instrument=instrument, lock=threading.RLock(), logger=self.logs.append)
        self.motor = app.PPMSMotorDebug(self.controller)
        self.system = types.SimpleNamespace(
            Array=Array, Object=object, Double=float, Int32=int, Boolean=bool,
            Activator=types.SimpleNamespace(CreateInstance=lambda t: 0),
            Enum=types.SimpleNamespace(GetNames=lambda t: self.modes, Parse=lambda t, n: n),
        )
        self.patch = patch.dict(sys.modules, System=self.system)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def read_fake(self, arguments):
        self.assertIn(arguments[0], (0, 3))
        self.assertIs(arguments[2], True)
        arguments[1] = self.angle if arguments[0] == 3 else {"Stopped": 4096, "Moving": 20480}.get(self.status, 0)
        return 0

    def write_fake(self, arguments):
        self.writes.append(list(arguments))
        return self.result

if __name__ == "__main__":
    unittest.main()
