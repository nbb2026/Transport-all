"""The built Transport_all.exe checks its own contents (Windows .exe build,
user, 2026-11-10).

PyInstaller runs this file inside the .exe just before Transport_all.py
(Transport_all.spec lists it first).  It does nothing unless the .exe is
started with --package-self-test.  Then it imports, from inside the .exe,
every library the program uses, loads the PCO camera DLLs and the .NET
runtime (pythonnet), writes the result to Transport_all_package_self_test.txt
beside the .exe, and exits with 0 when everything loaded, else 1, without
opening the program.  It opens no instrument, port or VISA session.

GitHub Actions runs it after every build; on a PC, in a terminal:
    Transport_all.exe --package-self-test
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

    def _pco_dlls():
        # As the program's own --pco-dll-self-test: the four libraries the
        # camera code loads at run time.
        from pco.loader import shared_library_loader

        shared_library_loader.increment()
        try:
            loaded = shared_library_loader.libs()
            missing = sorted({"sdk", "recorder", "convert", "xcite"} - set(loaded))
            if missing:
                raise RuntimeError("not loaded: " + ", ".join(missing))
            return "sdk, recorder, convert and xcite loaded"
        finally:
            shared_library_loader.decrement()

    def _dotnet():
        import clr  # noqa: F401  (pythonnet: starts the .NET runtime)
        import System

        return f".NET {System.Environment.Version}"

    checks = (
        ("Tcl/Tk", _tcl),
        ("numpy", lambda: _imported("numpy")),
        ("Pillow", lambda: _imported("PIL", "PIL.Image", "PIL.ImageTk", "PIL.ImageGrab",
                                     "PIL.ImageDraw", "PIL.ImageFont")),
        ("OpenCV", lambda: _imported("cv2")),
        ("pyserial", lambda: _imported("serial", "serial.tools.list_ports")),
        ("PyVISA", lambda: _imported("pyvisa", "pyvisa.ctwrapper")),
        ("pco", lambda: _imported("pco")),
        ("PCO DLLs", _pco_dlls),
        ("zhinst.core", lambda: _imported("zhinst.core")),
        ("zhinst.utils", lambda: _imported("zhinst.utils")),
        ("pythonnet", _dotnet),
        ("MultiPyVu", lambda: _imported("MultiPyVu")),
    )
    lines = [f"Transport_all package self-test: {sys.executable}"]
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
        Path(sys.executable).with_name("Transport_all_package_self_test.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")
    finally:
        # Leave at once: the program itself must not start.
        os._exit(0 if passed else 1)
