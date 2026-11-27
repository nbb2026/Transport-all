# Transport-RT

The SHHV & Switch page of [Transport-all](https://github.com/nbb2026/Transport-all) as
a program of its own: room-temperature harmonic Hall measurements (SHHV) and
current-pulse switching, with a Keithley 6221, an Avtech pulser, SR830 lock-ins
or a Zurich MFLI, a KEPCO or Lake Shore 643 magnet supply, an LS475 gaussmeter
and the Newmark rotation stage.

It runs without `Transport_all.py`. Everything it needs is in this branch:
the entry script [`Transport_RT.py`](Transport_RT.py) and the [`transport`](transport) package
beside it.

This is the `Transport-RT` branch. The whole program, with its MOKE, CIDWM, Non-local, PPMS, FMR and ST-FMR pages,
stays on `main`.

## Running it

**Windows .exe (no Python needed).** Download from the release
[Transport_RT v1.0](https://github.com/nbb2026/Transport-all/releases/tag/rt-v1.0):

- `Transport_RT.exe`: one file. Put it in a folder you keep and double-click it.
- `Transport_RT-folder.zip`: the same program as one folder, which starts faster.
  Unzip it and double-click `Transport_RT\Transport_RT.exe`; keep the `_internal` folder
  beside it.

Both are rebuilt from this branch after every push that passes its checks; the
release notes give the commit and the SHA-256 of each file. The version is this
program's own (`APP_VERSION` in [`tools/rt_host.py`](tools/rt_host.py)), not the main
program's. Raising it starts a new release, once the owner has pushed the tag
`rt-v<version>` (only the owner can make tags in this repository).

**From the source (64-bit Python 3.11):**

```bash
python -m pip install -r requirements.txt
```

```bash
python Transport_RT.py
```

**As a package:** `pip install` the wheel built from `pyproject.toml`, then
start it with the `transport-rt` command.

Still needed on the measuring PC, outside the program: NI-VISA and the GPIB driver, and LabOne for the Zurich MFLI. The Newmark
stage's `PerformaxCom.dll` and `SiUSBXp.dll`, kept beside the main program, go
beside this one.

## What is in the window

The first five tabs are the measurements; each offers its own scans in the
Scan box (user, 2026-11-27):

| Tab | Scans |
|---|---|
| **PHE** | Angle+Field, Angle+Current |
| **AHE** | Field, Field+Angle, Field+Current |
| **NLH** | Current |
| **SHHV** | Angle+Field, Angle+Current |
| **Switch-OOP** | Switch, Switch-loop, Switch2 |

- They are one page: the instruments stay connected, and the settings stay as
  they are, when another measurement's tab is chosen. Only the list of scans
  and the plots' title follow the measurement. The program starts on SHHV.
- **Switch-OOP** opens as the user's figure of 2026-11-27: Switch-loop from 22
  to -22 mA in 2 mA steps and back, 1 loop, Settle s 30, Acquire s 30, outer
  field 200 G, 1000 µs pulses, read current 0.5 mA RMS, SR830-1 on the 1st
  harmonic. The read current and the SR830-1 harmonic go back to 1.5 mA and
  2 in the other tabs; either box keeps a value that was typed into it. The
  safety tick is never set by the program.
- A measurement comes back on the scan it was left on. A scan that is also in
  the new measurement (Angle+Field in PHE and SHHV) keeps what was typed.
- While a scan runs, or the page is busy, the measurement cannot be changed:
  the page stays where it is and says so. The Log tab can always be opened.
- The Scan box is on the left and the Settings box on the right (stacked, Scan
  first, in a narrow window).
- Everything else is the SHHV & Switch page of Transport-all: Set field, the
  stage controls, the pulse row, the files, run logs and start questions. The
  saved rows and the run's settings have one more entry, `measurement` (PHE,
  AHE, NLH, SHHV or Switch-OOP); the `module` column and the results folder
  still say SHHV.
- In a wide window three things take one row instead of two: the scan note
  sits beside Round trip, the stage block (Stage °, Move, Stop, Go to 0°, Set
  stage 0°, the stage's line) is one row under the settings, and the supply's
  live line ("Field 1/1 +200 G, step 6: …") is wide enough for one line. A
  narrow window keeps the two rows.
- **Log**: the communication log, with pause, copy and save.

Closing the window stops a running scan and the stage, switches the 6221 (and
the Avtech) off and zeroes the magnet supply. The stage stays where it is.

**Beside Transport_all or another Transport program:** both can be open at
once. An instrument one program has connected is refused to the others, with
the holder's name, until it is disconnected there (a named object of Windows
per instrument address; it goes when the holder disconnects, closes or dies).

## How it is put together

| Part | What it holds |
|---|---|
| [`Transport_RT.py`](Transport_RT.py) | The entry script: starts the application. |
| [`transport/rt/app.py`](transport/rt/app.py) | The application: the SHHV & Switch panel, the instrument controllers and the window. Generated (see below). |
| [`transport/core`](transport/core) | Scan sequences, the run recorder (run folder, live CSV, JSON-lines log), and the end-of-scan zeroing and close hand-off. |
| [`transport/common`](transport/common) | Harmonic planning, lock-in settling, and the check of the 6221 / SR830 scan settings. |
| [`transport/ppms`](transport/ppms) | PPMS limits and command checks, and the MultiPyVu controller (shared package modules; used where the application's code reaches them). |

The modules in `transport/core`, `transport/common` and `transport/ppms` are
Jiaze Li's, separated from the program in November 2026. The application
imports them; it holds no second copy of that logic.

### The application module is generated

`transport/rt/app.py` is derived from the main program by
[`tools/extract_app.py`](tools/extract_app.py):

```bash
python tools/extract_app.py tools/rt_host.py /path/to/main/Transport_all.py
```

Starting from the SHHV & Switch panel, it keeps every function, class, constant and
method they reach, and nothing of the other pages: about 16,700 of the
main program's 40,500 lines. Two small files steer it:

- [`tools/rt_host.py`](tools/rt_host.py): the window of this program
  with its measurement tabs (`RTE_MEASUREMENTS`: which scans each offers) and
  its close, the list of parts left out, and `SOURCE_REPLACE`: what this
  program's page has and the main program's does not (the measurements, the
  Scan box on the left), as changes to the main program's text made before
  the extraction. The main program itself is not changed for them.
- [`tools/ppms_package_glue.py`](tools/ppms_package_glue.py): which names come
  from the `transport` package, and the thin wrappers that keep the main
  program's names and signatures.

To bring a later change of the main program here, run the tool again on the
new `Transport_all.py`, then the tests. Do not edit `app.py` by hand: change
the two steering files.

## Tests

Offline only; no instrument, port or VISA session is opened.

```bash
cd Other-files
```

```bash
python ci/run_suite.py
```

- The main program's tests of these pages, run against this application. Tests
  of other pages in the same files were taken out with
  [`tools/prune_tests.py`](tools/prune_tests.py), which prints the reason for
  each one it removes.
- Jiaze Li's tests of the package modules.
- `Newmark_motor_test.py`, the stage's own test script with its simulator,
  which the stage tests use.
- `Other-files/ci/rt_checks.py` builds the real window on GitHub's machines
  at the lab PC's screen sizes and saves screenshots.

GitHub runs all of it on Linux and Windows on every push
([`.github/workflows/rt-tests.yml`](.github/workflows/rt-tests.yml)), and
builds and checks the .exe
([`.github/workflows/rt-windows-exe.yml`](.github/workflows/rt-windows-exe.yml)).
The tests open windows, so run them on GitHub rather than on a desk computer.

Passing tests are not hardware acceptance: nothing here has been run on the
instruments.

License: GNU GPL v3.0 ([LICENSE](LICENSE)).
