# -*- mode: python ; coding: utf-8 -*-
# PyInstaller recipe for Transport_all.exe: the whole program as one Windows
# file that runs without Python (Windows .exe build, user, 2026-11-10).
#
# GitHub Actions builds it on every push to main
# (.github/workflows/build-windows.yml).  To build it by hand on a Windows PC,
# from the repository root:
#     py -3.11 -m pip install -r requirements.txt pyinstaller==6.22.3
#     py -3.11 -m PyInstaller --noconfirm --clean Other-files/packaging/Transport_all.spec
# The program is then dist\Transport_all.exe.
#
# Still needed on the PC, outside the .exe: the vendor drivers and runtimes
# (NI-VISA and GPIB, PCO camera driver, Thorlabs Kinesis, LabOne, MultiVu /
# QDInstrument, Newmark PerformaxCom.dll), as for the .py program.

import re
import sysconfig
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

PACKAGING = Path(SPECPATH).resolve()
ROOT = PACKAGING.parents[1]
ICON = "Magneto_Electro_Optical_Microwave_Transport_NH"
ASSETS = ROOT / "Other-files" / "assets"
# The publisher, stored as the company name in the .exe's version information
# (user, 2026-11-12).  Windows shows it as "Company" (Explorer tooltip and
# column) and "Publisher" (Task Manager).  It is not a code signature:
# SmartScreen still says "Unknown publisher" for an unsigned .exe.
PUBLISHER = "HengNiu & ClaudeCode"
VERSION = re.search(
    r'^APP_VERSION = "(.+)"', (ROOT / "Transport_all.py").read_text(encoding="utf-8"), re.M
).group(1)
VERSION_NUMBERS = tuple((list(map(int, re.findall(r"\d+", VERSION))) + [0, 0, 0, 0])[:4])

# The window and taskbar icons, found by the program in "assets" beside it.
datas = [
    (str(ASSETS / f"{ICON}_icon.png"), "assets"),
    (str(ASSETS / f"{ICON}.ico"), "assets"),
]
# pco loads its SDK, recorder, converter and XCite DLLs from pco/win_x64 at run
# time (ctypes), so they are not found by import analysis: take every DLL with
# its folder (27 in pco 2.6.0, 6 of them in win_x64/genicam).  The camera did
# not start in an older one-file build that missed them (Other-files/docs).
binaries = collect_dynamic_libs("pco")
datas += collect_data_files("pco")
# PyVISA reports its version from the package metadata.
datas += copy_metadata("pyvisa")
hiddenimports = collect_submodules("pyvisa")
# The program imports these by name at run time (importlib).
hiddenimports += ["zhinst.core", "zhinst.utils"]
# MultiPyVu, the optional PPMS backend, also loaded by name.
multipyvu_datas, multipyvu_binaries, multipyvu_imports = collect_all("MultiPyVu")
datas += multipyvu_datas
binaries += multipyvu_binaries
hiddenimports += multipyvu_imports
# MultiPyVu refuses to import unless it finds pywin32.version.txt in
# site-packages (sysconfig "platlib"), which inside the .exe is Lib/site-packages.
datas.append((str(Path(sysconfig.get_path("platlib")) / "pywin32.version.txt"), "Lib/site-packages"))

a = Analysis(
    # package_self_test.py runs first and does nothing unless the .exe is
    # started with --package-self-test; then Transport_all.py runs as usual.
    [str(PACKAGING / "package_self_test.py"), str(ROOT / "Transport_all.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
pyz = PYZ(a.pure)
# File > Properties > Details shows the description, versions, product name
# and original file name; the company name (PUBLISHER) shows elsewhere (above).
version_info = VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=VERSION_NUMBERS,
        prodvers=VERSION_NUMBERS,
        mask=0x3F,
        flags=0x0,
        OS=0x40004,  # Windows NT, 32/64-bit
        fileType=0x1,  # an application
        subtype=0x0,
        date=(0, 0),
    ),
    kids=[
        StringFileInfo(
            [
                StringTable(
                    "040904B0",  # U.S. English, Unicode
                    [
                        StringStruct("CompanyName", PUBLISHER),
                        StringStruct("FileDescription", "Transport_all"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", "Transport_all"),
                        StringStruct("OriginalFilename", "Transport_all.exe"),
                        StringStruct("ProductName", "Transport_all"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]
        ),
        VarFileInfo([VarStruct("Translation", [0x0409, 0x04B0])]),
    ],
)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Transport_all",
    icon=str(ASSETS / f"{ICON}.ico"),
    version=version_info,
    console=False,  # a GUI program: no console window
    upx=False,  # compressed executables are flagged more often by antivirus
    debug=False,
    strip=False,
    runtime_tmpdir=None,
)
