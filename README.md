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

## Keeping the lab computer's exe up to date

[`Update_Transport_RT.bat`](Update_Transport_RT.bat) puts the newest
`Transport_RT.exe` into the folder the `.bat` is in (user, 2026-11-27). Copy
it once into the folder the program is kept in and double-click it:

- It reads this branch's version and the SHA-256 of that version's exe from
  GitHub. If the exe in the folder already has that SHA-256, nothing happens.
- If `Transport_RT.exe` is running, nothing is changed (a measurement may be
  running): close the program and run it again.
- Otherwise it downloads the exe, checks its SHA-256, puts it in place and
  deletes the old one (user, 2026-11-27). A download that fails or does not
  match changes nothing: the old exe stays.

It uses only `curl`, `certutil` and `tasklist`, which are parts of Windows 10
and 11; nothing is installed. `Update_Transport_RT.bat start` also starts the
program afterwards (or set `START_AFTER=1` in the file and use it as the
shortcut); `quiet` does not wait for a key. It is also a file of the release,
beside the exe. Tests: `test_update_bat.py`.

## What is in the window

The first six tabs are the measurements; each offers its own scans in the
Scan box (user, 2026-11-27):

| Tab | Scans |
|---|---|
| **PHE** | Angle+Field, Angle+Current |
| **AHE** | Field, Field+Angle, Field+Current |
| **NLH** | Current |
| **SHHV** | Angle+Field, Angle+Current |
| **Switch-OOP** | Switch, Switch-loop, Switch2 |
| **Switch-IP** | Switch, Switch-loop, Switch2 |

- They are one page: the instruments stay connected, and the settings stay as
  they are, when another measurement's tab is chosen. Only the list of scans
  and the plots' title follow the measurement. The program starts on SHHV.
- **How a run is saved** (one rule since 2026-11-28). The folder and the file
  name are asked under the measurement's name ("AHE: folder to save the run
  in", "AHE: file name"). The run is `<folder>/<name>/` (`<name>_01`, ... when
  taken) with `<name>.csv` (one row per point), `<name>.log` (JSON lines) and,
  for the rest, `<name>_<part>.<ext>`: `<name>_trace.csv` (Switch scans: every
  lock-in reading), `<name>_plots_snapshot.png`. A blank name is
  `<measurement>_<date>_<time>`. One object, the run's recorder, makes the
  folder and writes the CSV, the log and the trace CSV: under one lock, each
  write on the disk before it returns, the CSVs as UTF-8 with a byte-order
  mark (the trace CSV had none before). Save CSV as suggests
  `<name>_copy.csv` in the run folder; the program log `Transport_RT_log_<date>_<time>.txt`.
  The names of the CSV's columns and of the log's fields are unchanged.
- **Switch-OOP** opens on the Switch scan with the states of the user's second
  figure of 2026-11-28 (below). Its Switch-loop scan is as the first figure of
  that day: from 24
  to -24 mA in 2 mA steps and back, 1 loop, Settle s 10, Acquire s 10, outer
  field 500 G; and, from the figure of 2026-11-27, 1000 µs pulses, read
  current 0.5 mA RMS, SR830-1 on the 1st harmonic. The read current and the
  SR830-1 harmonic go back to 1.5 mA and 2 in the other tabs; a box keeps a
  value that was typed into it. The 10 s, 10 s and 500 G are this tab's
  Switch-loop scan's: its Switch2 scan keeps 30 s, and the Switch scan has its
  own 10 s (below). The safety tick is never set by the program.
- **AHE** opens as the user's third figure of 2026-11-27: the Field scan from
  -3 to 3 A in 0.1 A steps and back, 1 loop, Settle s 0.5, Acquire s 2, read
  current 0.5 mA RMS, SR830-1 on the 1st harmonic and the only lock-in
  measured. The figure is the Field scan: Field+Angle and Field+Current keep
  -1 to 1 A in 0.02 A.
- **Switch-IP** is Switch-OOP with three values of its own: Switch-loop from
  14 to -14 mA in 2 mA steps and back, 30 µs pulses, SR830-1 on the 2nd
  harmonic. It keeps what Switch-OOP had on 2026-11-27 for the rest (200 G,
  Settle s 30, Acquire s 30, 0.5 mA RMS read current): the figure of
  2026-11-28 was for Switch-OOP. Between the two tabs the loop, Settle s,
  Acquire s, the field, the pulse width and the harmonic follow the tab; a
  typed value stays. Pulse µs shows 1000 in the other tabs.
- **The Switch scan runs states** (since 2026-11-28; Switch-loop and Switch2
  are as before). The Scan box shows a table in place of "Pulses mA", "Outer
  field G" and the Pulse µs box:

  | | Angle ° | Field G | Pulse mA | Pulse µs |
  | --- | --- | --- | --- | --- |
  | 1 | -360 | 1000 | 0 | 50 |
  | 2 | -270 | 200 | -10 | 50 |
  | 3 | -270 | 200 | 10 | 50 |
  | 4 | -360 | -1000 | 0 | 50 |

  These are the Switch-OOP tab's states (the user's figure, 2026-11-28). In
  the other tabs the table shows 0°, 0°, 90°, 90°; 500 G; ±20 mA; 1000 µs
  (30 µs on Switch-IP). A cell follows the tab only while it still holds what
  the program put there, so a typed value stays.

  - **Settle s and Acquire s** start at 10 s in the Switch scan, on both
    Switch tabs (user, 2026-11-28); a typed value stays.
  - **States** sets how many rows the scan has (1 to 12; a row past the first
    four is empty until it is typed). The states run in their order, and
    **Cycles** repeats the whole list.
  - **One state:** the read current off; the stage to the state's angle; the
    field to the state's; one write of **Pulses** pulses at the state's
    current and width (0 mA sends none); the field back to 0 G; the read
    current on again, the settling (5 time constants and Settle s) and the
    read for Acquire s. So every state is read at 0 G, as MS-fourState reads,
    and the stage only turns at 0 G with the read current off.
  - **The read current**, its frequency, the compliance and the lock-ins are
    the Settings boxes', unchanged by a state.
  - **Angle °:** typed for every state, or left empty in every state. Empty
    means the stage is not moved and need not be connected.
  - **Each field**, 0 G too, is found on the LS475 as Set field finds it,
    within the Tol. box, so a state with a field takes two field settings. A
    state written at 0 G leaves the field alone.
  - **Plots:** X and Y against the state's number, one line a cycle; X and Y
    against time as before.
  - **Saved:** besides the Switch scan's columns, `state`,
    `write_target_field_g`, `write_field_g` and `write_current_a` (the LS475
    field and the supply current the state was written at), and the stage's
    columns when the states have angles. `measured_field_g` is the field at the
    read, and `outer_target_field_g` is the 0 G every state is read at. The
    run's settings list the states under `pulse.states`.
  - In a wide Scan box the table stands beside the scan's rows; in a narrow
    one it is in the first row, beside the scan list.
- **PHE** opens as the user's figure of 2026-11-28: Angle+Field from 0
  to -360° in 5° steps, 1 loop, Settle s 0.5, Acquire s 2, no round trip,
  outer field 1000 G (one field), read current 1.5 mA RMS, SR830-1 on the 1st
  harmonic and the only lock-in measured (until 2026-11-28: Acquire s 5 and
  200 G). The outer field, Acquire s and the harmonic differ from SHHV, which
  shows the field list 200 to 1000 G, 5 s and harmonic 2; a typed value stays
  here too. Angle+Current on this tab keeps Acquire s 5.
- A measurement comes back on the scan it was left on. A scan that is also in
  the new measurement (Angle+Field in PHE and SHHV) keeps what was typed.
- While a scan runs, or the page is busy, the measurement cannot be changed:
  the page stays where it is and says so. The Log tab can always be opened.
- The Scan box is on the left and the Settings box on the right (stacked, Scan
  first, in a narrow window).
- Everything else is the SHHV & Switch page of Transport-all: Set field, the
  stage controls, the pulse row, the files, run logs and start questions. The
  saved rows and the run's settings have one more entry, `measurement` (PHE,
  AHE, NLH, SHHV, Switch-OOP or Switch-IP); the `module` column still says SHHV.
- A run whose file name is left blank is named after its measurement:
  `PHE_<date>_<time>`, `AHE_…`, `NLH_…`, `SHHV_…`, `Switch-OOP_…`, `Switch-IP_…` (the run
  folder, its `.csv` and its `.log`). Save CSV as suggests the same name. A
  typed name is used as typed.
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
| [`transport/ppms`](transport/ppms) | PPMS limits and command checks (a shared package module; the application uses its field-command check). The MultiPyVu controller is not here: this program reaches no PPMS. |

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
method they reach, and nothing of the other pages: about 11,900 of the
main program's 40,600 lines. It works in two passes:

1. By name: whatever the panel, the window and what they use *name* is kept.
   This alone left about 16,900 lines, because the panel is built on the PPMS
   page and shares names with it.
2. By reach (`prune_unreachable`, turned on by `PRUNE_ROOTS` in the steering
   file): from `main`, it follows which object each method is called on, as
   Python looks a method up, and takes out what the program cannot get to:
   the PPMS page's own window, scans, macro, cryostat and rotator code that
   this page replaces, the parts of the instrument classes only other pages
   use, and helpers only tests called. Their tests went with them. A method
   name used on an unknown object, or in a string, still keeps that method in
   every class that is used, so it errs on the side of keeping.
   `Other-files/test_unreachable_pruning.py` tests each rule and checks that
   the program has no attribute look-up by a name built at run time, which is
   the one thing the pass cannot see.

Two small files steer it:

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
  each one it removes, and the tests of the PPMS page's own code went when
  that code did (2026-11-28).
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
