"""The built Transport_RT.exe checks its own contents.

PyInstaller runs this file inside the .exe just before Transport_RT.py
(Transport_RT.spec lists it first).  It does nothing unless the .exe is
started with --package-self-test.  Then it imports, from inside the .exe,
every library the program uses and the transport package, loads the .NET
runtime (pythonnet), writes the result to
Transport_RT_package_self_test.txt beside the .exe, and exits with 0 when
everything loaded, else 1, without opening the program.  It opens no
instrument, port or VISA session.

GitHub Actions runs it after every build; on a PC, in a terminal:
    Transport_RT.exe --package-self-test
"""

import sys

if "--package-self-test" in sys.argv:
    import importlib
    import os
    import traceback
    from pathlib import Path

    def _imported(*names):
        modules = [importlib.import_module(name) for name in names]
        return getattr(modules[0], "__version__", "imported")

    def _tcl():
        import tkinter

        return "Tcl " + tkinter.Tcl().eval("info patchlevel")

    def _dotnet():
        import clr  # noqa: F401  (pythonnet: starts the .NET runtime)
        import System

        return f".NET {System.Environment.Version}"

    def _application():
        module = importlib.import_module("transport.rt.app")
        return f"version {module.APP_VERSION}, window class {module.CombinedControlApp.__name__}"

    checks = (
        ("Tcl/Tk", _tcl),
        ("numpy", lambda: _imported("numpy")),
        ("Pillow", lambda: _imported("PIL", "PIL.Image", "PIL.ImageGrab")),
        ("PyVISA", lambda: _imported("pyvisa", "pyvisa.ctwrapper")),
        ("pyserial", lambda: _imported("serial")),
        ("zhinst.core", lambda: _imported("zhinst.core")),
        ("zhinst.utils", lambda: _imported("zhinst.utils")),
        ("pythonnet", _dotnet),
        ("transport package", lambda: _imported(
            "transport.core.scan_sequences", "transport.core.scan_recording", "transport.core.scan_lifecycle",
            "transport.common.harmonics", "transport.common.settling", "transport.common.validation",
            "transport.ppms.protocol")),
        ("SHHV & Switch application", _application),
    )
    lines = [f"Transport_RT package self-test: {sys.executable}"]
    passed = True
    for name, check in checks:
        try:
            lines.append(f"OK    {name}: {check()}")
        except BaseException as error:
            passed = False
            lines.append(f"FAIL  {name}: {type(error).__name__}: {error}")
            lines.append(traceback.format_exc())
    lines.append("RESULT: PASS" if passed else "RESULT: FAIL")
    try:
        Path(sys.executable).with_name("Transport_RT_package_self_test.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
    finally:
        # Leave at once: the program itself must not start.
        os._exit(0 if passed else 1)
