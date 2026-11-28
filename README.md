# Transport-FMR

The FMR and STFMR pages of [Transport-all](https://github.com/nbb2026/Transport-all)
as a program of their own: ferromagnetic resonance with a PNA network analyser
(FMR) and spin-torque FMR with an R&S SMB100A source and an SR830 or Zurich
MFLI lock-in (STFMR), with a KEPCO or Lake Shore magnet supply, an LS475
gaussmeter and the Newmark rotation stage.

It runs without `Transport_all.py`. Everything it needs is in this branch:
the entry script [`Transport_FMR.py`](Transport_FMR.py) and the [`transport`](transport) package
beside it.

This is the `Transport-FMR` branch. The whole program, with its MOKE, CIDWM, Non-local, PPMS and SHHV & Switch pages,
stays on `main`.

## Running it

**Windows .exe (no Python needed).** Download from the release
[Transport_FMR v1.0](https://github.com/nbb2026/Transport-all/releases/tag/fmr-v1.0):

- `Transport_FMR.exe`: one file. Put it in a folder you keep and double-click it.
- `Transport_FMR-folder.zip`: the same program as one folder, which starts faster.
  Unzip it and double-click `Transport_FMR\Transport_FMR.exe`; keep the `_internal` folder
  beside it.

Both are rebuilt from this branch after every push that passes its checks; the
release notes give the commit and the SHA-256 of each file. The version is this
program's own (`APP_VERSION` in [`tools/fmr_host.py`](tools/fmr_host.py)), not the main
program's. Raising it starts a new release, once the owner has pushed the tag
`fmr-v<version>` (only the owner can make tags in this repository).

**From the source (64-bit Python 3.11):**

```bash
python -m pip install -r requirements.txt
```

```bash
python Transport_FMR.py
```

**As a package:** `pip install` the wheel built from `pyproject.toml`, then
start it with the `transport-fmr` command.

Still needed on the measuring PC, outside the program: NI-VISA and the GPIB driver, and LabOne for the Zurich MFLI. The Newmark
stage's `PerformaxCom.dll` and `SiUSBXp.dll`, kept beside the main program, go
beside this one.

## Keeping the lab computer's exe up to date

[`Update_Transport_FMR.bat`](Update_Transport_FMR.bat) puts the newest
`Transport_FMR.exe` into the folder the `.bat` is in (user, 2026-11-27). Copy
it once into the folder the program is kept in and double-click it:

- It reads this branch's version and the SHA-256 of that version's exe from
  GitHub. If the exe in the folder already has that SHA-256, nothing happens.
- If `Transport_FMR.exe` is running, nothing is changed (a measurement may be
  running): close the program and run it again.
- Otherwise it downloads the exe, checks its SHA-256, puts it in place and
  deletes the old one (user, 2026-11-27). A download that fails or does not
  match changes nothing: the old exe stays.

It uses only `curl`, `certutil` and `tasklist`, which are parts of Windows 10
and 11; nothing is installed. `Update_Transport_FMR.bat start` also starts the
program afterwards (or set `START_AFTER=1` in the file and use it as the
shortcut); `quiet` does not wait for a key. It is also a file of the release,
beside the exe. Tests: `test_update_bat.py`.

## What is in the window

- **FMR** and **STFMR**: the pages as in Transport-all, with the same scans,
  Set field, the stage controls and the plots. Files, columns, run logs and
  start questions are the main program's.
- **Log**: the communication log, with pause, copy and save.

Closing the window stops a running scan, zeroes the magnet supply and
switches its output off, switches the RF source off and disconnects the
instruments.

**Beside Transport_all or another Transport program:** both can be open at
once. An instrument one program has connected is refused to the others, with
the holder's name, until it is disconnected there (a named object of Windows
per instrument address; it goes when the holder disconnects, closes or dies).

## How it is put together

| Part | What it holds |
|---|---|
| [`Transport_FMR.py`](Transport_FMR.py) | The entry script: starts the application. |
| [`transport/fmr/app.py`](transport/fmr/app.py) | The application: the two pages, the instrument controllers and the window. Generated (see below). |
| [`transport/core`](transport/core) | Scan sequences, the run recorder (run folder, live CSV, JSON-lines log), and the end-of-scan zeroing and close hand-off. |
| [`transport/common`](transport/common) | Harmonic planning, lock-in settling, and the check of the 6221 / SR830 scan settings. |
| [`transport/ppms`](transport/ppms) | PPMS limits and command checks, and the MultiPyVu controller (shared package modules; used where the application's code reaches them). |

The modules in `transport/core`, `transport/common` and `transport/ppms` are
Jiaze Li's, separated from the program in November 2026. The application
imports them; it holds no second copy of that logic.

### The application module is generated

`transport/fmr/app.py` is derived from the main program by
[`tools/extract_app.py`](tools/extract_app.py):

```bash
python tools/extract_app.py tools/fmr_host.py /path/to/main/Transport_all.py
```

Starting from the two pages, it keeps every function, class, constant and
method they reach, and nothing of the other pages: about 13,700 of the
main program's 40,600 lines. It works in two passes:

1. By name: whatever the pages, the window and what they use *name* is kept
   (14,191 lines).
2. By reach (`prune_unreachable`, turned on by `PRUNE_ROOTS` in the steering
   file, since 2026-11-28): from `main`, it follows which object each method
   is called on, as Python looks a method up, and takes out what the program
   cannot get to: the Non-local page's reading, sweep and nanovoltmeter code and the PPMS page's Zurich harmonics in the instrument class these pages share, and helpers only tests called. Their tests went with
   them. A method name used on an unknown object, or in a string, still keeps
   that method in every class that is used, so it errs on the side of keeping;
   code it cannot follow stops the tool instead of being guessed at.
   `Other-files/test_unreachable_pruning.py` tests each rule and checks that
   the program has no method look-up by a name built at run time, which is the
   one thing the pass cannot see.

Two small files steer it:

- [`tools/fmr_host.py`](tools/fmr_host.py): the window of this program
  and its close, and the list of parts left out.
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
- `Other-files/ci/fmr_checks.py` builds the real window on GitHub's machines
  at the lab PC's screen sizes and saves screenshots.

GitHub runs all of it on Linux and Windows on every push
([`.github/workflows/fmr-tests.yml`](.github/workflows/fmr-tests.yml)), and
builds and checks the .exe
([`.github/workflows/fmr-windows-exe.yml`](.github/workflows/fmr-windows-exe.yml)).
The tests open windows, so run them on GitHub rather than on a desk computer.

Passing tests are not hardware acceptance: nothing here has been run on the
instruments.

License: GNU GPL v3.0 ([LICENSE](LICENSE)).
