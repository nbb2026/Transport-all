# Transport-MOKE

The MOKE pages of [Transport-all](https://github.com/nbb2026/Transport-all) as a
program of their own: magneto-optic Kerr imaging with the PCO camera and the
LED light source (MOKE light), the cell stage (MOKE motor), the in-plane and
out-of-plane magnets (MOKE magnet), current-induced domain-wall motion with a
Keithley 6221 or an Avtech pulser (CIDWM), and the Keithley 2410 (MOKE-24).

It runs without `Transport_all.py`. Everything it needs is in this branch:
the entry script [`Transport_MOKE.py`](Transport_MOKE.py) and the [`transport`](transport) package
beside it.

This is the `Transport-MOKE` branch. The whole program, with its Non-local, PPMS, SHHV & Switch, FMR and ST-FMR pages,
stays on `main`.

## Running it

**Windows .exe (no Python needed).** Download from the release
[Transport_MOKE v1.0](https://github.com/nbb2026/Transport-all/releases/tag/moke-v1.0):

- `Transport_MOKE.exe`: one file. Put it in a folder you keep and double-click it.
- `Transport_MOKE-folder.zip`: the same program as one folder, which starts faster.
  Unzip it and double-click `Transport_MOKE\Transport_MOKE.exe`; keep the `_internal` folder
  beside it.

Both are rebuilt from this branch after every push that passes its checks; the
release notes give the commit and the SHA-256 of each file. The version is this
program's own (`APP_VERSION` in [`tools/moke_host.py`](tools/moke_host.py)), not the main
program's. Raising it starts a new release, once the owner has pushed the tag
`moke-v<version>` (only the owner can make tags in this repository).

**From the source (64-bit Python 3.11):**

```bash
python -m pip install -r requirements.txt
```

```bash
python Transport_MOKE.py
```

**As a package:** `pip install` the wheel built from `pyproject.toml`, then
start it with the `transport-moke` command.

Still needed on the measuring PC, outside the program: the PCO camera driver, Thorlabs Kinesis, NI-VISA and the GPIB driver.

## Keeping the lab computer's exe up to date

[`Update_Transport_MOKE.bat`](Update_Transport_MOKE.bat) puts the newest
`Transport_MOKE.exe` into the folder the `.bat` is in (user, 2026-11-27). Copy
it once into the folder the program is kept in and double-click it:

- It reads this branch's version and the SHA-256 of that version's exe from
  GitHub. If the exe in the folder already has that SHA-256, nothing happens.
- If `Transport_MOKE.exe` is running, nothing is changed (a measurement may be
  running): close the program and run it again.
- Otherwise it downloads the exe, checks its SHA-256, puts it in place and
  deletes the old one (user, 2026-11-27). A download that fails or does not
  match changes nothing: the old exe stays.

It uses only `curl`, `certutil` and `tasklist`, which are parts of Windows 10
and 11; nothing is installed. `Update_Transport_MOKE.bat start` also starts the
program afterwards (or set `START_AFTER=1` in the file and use it as the
shortcut); `quiet` does not wait for a key. It is also a file of the release,
beside the exe. Tests: `test_update_bat.py`.

## What is in the window

- **MOKE light**, **MOKE motor**, **MOKE magnet**, **CIDWM** and **MOKE-24**: the
  pages as in Transport-all, with the camera window, auto-focus and drift
  tracking, and the communication log on the MOKE light page. Files, columns,
  run logs and start questions are the main program's.

Closing the window stops the camera and any running scan, zeroes the LED
currents, the magnets and the Keithley sources, and disconnects the
instruments, as the main program does for these pages.

**Beside Transport_all or another Transport program:** both can be open at
once. An instrument one program has connected is refused to the others, with
the holder's name, until it is disconnected there (a named object of Windows
per instrument address; it goes when the holder disconnects, closes or dies).

## How it is put together

| Part | What it holds |
|---|---|
| [`Transport_MOKE.py`](Transport_MOKE.py) | The entry script: starts the application. |
| [`transport/moke/app.py`](transport/moke/app.py) | The application: these pages, the instrument controllers and the window. Generated (see below). |
| [`transport/core`](transport/core) | Scan sequences, the run recorder (run folder, live CSV, JSON-lines log), and the end-of-scan zeroing and close hand-off. |
| [`transport/common`](transport/common) | Harmonic planning, lock-in settling, and the check of the 6221 / SR830 scan settings. |
| [`transport/ppms`](transport/ppms) | PPMS limits and command checks, and the MultiPyVu controller (shared package modules; used where the application's code reaches them). |

The modules in `transport/core`, `transport/common` and `transport/ppms` are
Jiaze Li's, separated from the program in November 2026. The application
imports them; it holds no second copy of that logic.

### The application module is generated

`transport/moke/app.py` is derived from the main program by
[`tools/extract_app.py`](tools/extract_app.py):

```bash
python tools/extract_app.py tools/moke_host.py /path/to/main/Transport_all.py
```

Starting from these pages, it keeps every function, class, constant and
method they reach, and nothing of the other pages: about 15,300 of the
main program's 40,600 lines. It works in two passes:

1. By name: whatever the pages, the window and what they use *name* is kept
   (17,708 lines).
2. By reach (`prune_unreachable`, turned on by `PRUNE_ROOTS` in the steering
   file, since 2026-11-28): from `main`, it follows which object each method
   is called on, as Python looks a method up, and takes out what the program
   cannot get to: the Zurich lock-in's connection, set-up and reading code and its two LabOne adapters, the Non-local page's sweeps on the 2410, and other parts of the instrument classes only other pages use, and helpers only tests called. Their tests went with
   them. A method name used on an unknown object, or in a string, still keeps
   that method in every class that is used, so it errs on the side of keeping;
   code it cannot follow stops the tool instead of being guessed at.
   `Other-files/test_unreachable_pruning.py` tests each rule and checks that
   the program has no method look-up by a name built at run time, which is the
   one thing the pass cannot see.

Two small files steer it:

- [`tools/moke_host.py`](tools/moke_host.py): the window of this program
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
- `Other-files/ci/moke_checks.py` builds the real window on GitHub's machines
  at the lab PC's screen sizes and saves screenshots.

GitHub runs all of it on Linux and Windows on every push
([`.github/workflows/moke-tests.yml`](.github/workflows/moke-tests.yml)), and
builds and checks the .exe
([`.github/workflows/moke-windows-exe.yml`](.github/workflows/moke-windows-exe.yml)).
The tests open windows, so run them on GitHub rather than on a desk computer.

Passing tests are not hardware acceptance: nothing here has been run on the
instruments.

License: GNU GPL v3.0 ([LICENSE](LICENSE)).
