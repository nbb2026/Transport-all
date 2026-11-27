# Transport-PPMS

The PPMS page of [Transport-all](https://github.com/nbb2026/Transport-all) as
a program of its own: harmonic Hall and resistance measurements in a Quantum
Design PPMS with a Keithley 6221 source, up to three SR830 lock-ins and a
Zurich MFLI.

It runs without `Transport_all.py`. Everything it needs is in this branch:
the entry script [`Transport_PPMS.py`](Transport_PPMS.py) and the
[`transport`](transport) package beside it.

This is the `Transport-PPMS` branch (it was `modular`). The whole program,
with its MOKE, CIDWM, Non-local, SHHV & Switch, FMR and ST-FMR pages, stays on
`main`.

## Running it

**Windows .exe (no Python needed).** Download from the release
[Transport_PPMS v1.0](https://github.com/nbb2026/Transport-all/releases/tag/ppms-v1.0):

- `Transport_PPMS.exe`: one file. Put it in a folder you keep and
  double-click it.
- `Transport_PPMS-folder.zip`: the same program as one folder, which starts
  faster. Unzip it and double-click `Transport_PPMS\Transport_PPMS.exe`; keep
  the `_internal` folder beside it.

Both are rebuilt from this branch after every push that passes its checks; the
release notes give the commit and the SHA-256 of each file. The version is this
program's own (`APP_VERSION` in [`tools/ppms_host.py`](tools/ppms_host.py)), not the main
program's. Raising it starts a new release, once the owner has pushed the tag
`ppms-v<version>` (only the owner can make tags in this repository).

**From the source (64-bit Python 3.11):**

```bash
python -m pip install -r requirements.txt
```

```bash
python Transport_PPMS.py
```

**As a package:** `pip install` the wheel built from `pyproject.toml`, then
start it with the `transport-ppms` command.

Still needed on the measuring PC, outside the program: NI-VISA and the GPIB
driver, LabOne for the Zurich MFLI, and MultiVu / QDInstrument for the PPMS.
`QDInstrument.dll` kept beside the main program goes beside this one. An MFLI
on LabOne 18.12 needs the Python 3.7 bridge from
[`Other-files/INSTALL_MFLI_LABONE_18_12.bat`](Other-files/INSTALL_MFLI_LABONE_18_12.bat).

## Keeping the lab computer's exe up to date

[`Update_Transport_PPMS.bat`](Update_Transport_PPMS.bat) puts the newest
`Transport_PPMS.exe` into the folder the `.bat` is in (user, 2026-11-27). Copy
it once into the folder the program is kept in and double-click it:

- It reads this branch's version and the SHA-256 of that version's exe from
  GitHub. If the exe in the folder already has that SHA-256, nothing happens.
- If `Transport_PPMS.exe` is running, nothing is changed (a measurement may be
  running): close the program and run it again.
- Otherwise it downloads the exe, checks its SHA-256, puts it in place and
  deletes the old one (user, 2026-11-27). A download that fails or does not
  match changes nothing: the old exe stays.

It uses only `curl`, `certutil` and `tasklist`, which are parts of Windows 10
and 11; nothing is installed. `Update_Transport_PPMS.bat start` also starts the
program afterwards (or set `START_AFTER=1` in the file and use it as the
shortcut); `quiet` does not wait for a key. It is also a file of the release,
beside the exe. Tests: `test_update_bat.py`.

## What is in the window

Two pages:

- **PPMS**: the page as in Transport-all, with the same scans (field, angle,
  temperature, current, frequency and their combinations), the PPMS macro,
  the motor controls, the helium history and warning, the SR830 time-constant
  control, and the Zurich with one or several harmonics. Files, columns, run
  logs and start questions are the main program's.
- **Log**: the communication log, with pause, copy and save.

Closing the window switches the 6221 output off and disconnects the
instruments. If a field scan is running, it first asks the PPMS to zero the
field.

**Beside Transport_all or another Transport program:** both can be open at
once. An instrument one program has connected is refused to the others, with
the holder's name, until it is disconnected there (a named object of Windows
per instrument address; it goes when the holder disconnects, closes or dies).

## How it is put together

| Part | What it holds |
|---|---|
| [`Transport_PPMS.py`](Transport_PPMS.py) | The entry script: starts `transport.ppms.app.main`. |
| [`transport/ppms/app.py`](transport/ppms/app.py) | The application: the PPMS page, its instrument controllers and the window. Generated (see below). |
| [`transport/ppms/protocol.py`](transport/ppms/protocol.py) | PPMS limits and the checks of field and temperature commands. |
| [`transport/ppms/controllers/multivu.py`](transport/ppms/controllers/multivu.py) | The MultiPyVu read-back controller. |
| [`transport/core`](transport/core) | Scan sequences, the run recorder (run folder, live CSV, JSON-lines log), and the end-of-scan zeroing and close hand-off. |
| [`transport/common`](transport/common) | Harmonic planning, lock-in settling, and the check of the 6221 / SR830 scan settings. |

The modules in `transport/core`, `transport/common`, `transport/ppms/protocol.py`
and `transport/ppms/controllers` are Jiaze Li's, separated from the program in
November 2026. The application imports them; it holds no second copy of that
logic. The main program's own versions of those functions had not changed
since the split, so they were reused as they are. The one addition is in the
run recorder: the extra save folders and the open-run hook the main program
gained later.

### The application module is generated

`transport/ppms/app.py` is derived from the main program by
[`tools/extract_app.py`](tools/extract_app.py):

```bash
python tools/extract_app.py tools/ppms_host.py /path/to/main/Transport_all.py
```

Starting from the PPMS panel, it keeps every function, class, constant and
method the page reaches, and nothing of the other pages. The first extraction
kept about 10,800 of the main program's 40,500 lines. Two small files steer it:

- [`tools/ppms_host.py`](tools/ppms_host.py): the window of this program (the
  PPMS and Log pages, its own close), and the list of parts left out.
- [`tools/ppms_package_glue.py`](tools/ppms_package_glue.py): which names come
  from the `transport` package, and the thin wrappers that keep the main
  program's names and signatures.

To bring a later change of the main program's PPMS page here, run the tool
again on the new `Transport_all.py`, then the tests. Do not edit `app.py` by
hand: change the two steering files.

## Tests

Offline only; no instrument, port or VISA session is opened.

```bash
cd Other-files
```

```bash
python ci/run_suite.py
```

- The main program's PPMS tests, run against this application. Tests of other
  pages in the same files were taken out with
  [`tools/prune_tests.py`](tools/prune_tests.py), which prints the reason for
  each one it removes.
- Jiaze Li's tests of the package modules.
- `Other-files/ci/ppms_checks.py` builds the real window on GitHub's machines
  at the lab PC's screen sizes and saves screenshots.

GitHub runs all of it on Linux and Windows on every push
([`.github/workflows/ppms-tests.yml`](.github/workflows/ppms-tests.yml)), and
builds and checks the .exe
([`.github/workflows/ppms-windows-exe.yml`](.github/workflows/ppms-windows-exe.yml)).
The tests open windows, so run them on GitHub rather than on a desk computer.

Passing tests are not hardware acceptance: nothing here has been run on the
PPMS.

## More

- [`Other-files/README_PPMS_SIMPLE_MODES.md`](Other-files/README_PPMS_SIMPLE_MODES.md),
  [`Other-files/README_PPMS_NESTED.md`](Other-files/README_PPMS_NESTED.md):
  the scan modes.
- [`Other-files/PPMS_Macro_README.md`](Other-files/PPMS_Macro_README.md): the
  macro.
- [`Other-files/README_PPMS_MOTOR_DEBUG.md`](Other-files/README_PPMS_MOTOR_DEBUG.md):
  the motor.

License: GNU GPL v3.0 ([LICENSE](LICENSE)).
