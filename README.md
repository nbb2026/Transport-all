# Transport-all

## Download the Windows programs

No Python needed (Windows 10/11, 64-bit). Version 1.0 of each program:

| | Program | One file | One folder (starts faster) | Updater | Source |
|---|---|---|---|---|---|
| <img src="https://raw.githubusercontent.com/nbb2026/Transport-all/Transport-PPMS/Other-files/assets/Transport_PPMS_icon_64.png" width="32" alt=""> | **Transport_PPMS v1.0**: the PPMS page | [Transport_PPMS.exe](https://github.com/nbb2026/Transport-all/releases/download/ppms-v1.0/Transport_PPMS.exe) | [Transport_PPMS-folder.zip](https://github.com/nbb2026/Transport-all/releases/download/ppms-v1.0/Transport_PPMS-folder.zip) | [Update_Transport_PPMS.bat](https://github.com/nbb2026/Transport-all/releases/download/ppms-v1.0/Update_Transport_PPMS.bat) | [`Transport-PPMS`](https://github.com/nbb2026/Transport-all/tree/Transport-PPMS) |
| <img src="https://raw.githubusercontent.com/nbb2026/Transport-all/Transport-RT/Other-files/assets/Transport_RT_icon_64.png" width="32" alt=""> | **Transport_RT v1.0**: the SHHV & Switch page | [Transport_RT.exe](https://github.com/nbb2026/Transport-all/releases/download/rt-v1.0/Transport_RT.exe) | [Transport_RT-folder.zip](https://github.com/nbb2026/Transport-all/releases/download/rt-v1.0/Transport_RT-folder.zip) | [Update_Transport_RT.bat](https://github.com/nbb2026/Transport-all/releases/download/rt-v1.0/Update_Transport_RT.bat) | [`Transport-RT`](https://github.com/nbb2026/Transport-all/tree/Transport-RT) |
| <img src="https://raw.githubusercontent.com/nbb2026/Transport-all/Transport-MOKE/Other-files/assets/Transport_MOKE_icon_64.png" width="32" alt=""> | **Transport_MOKE v1.0**: MOKE light, MOKE motor, MOKE magnet, CIDWM, MOKE-24 | [Transport_MOKE.exe](https://github.com/nbb2026/Transport-all/releases/download/moke-v1.0/Transport_MOKE.exe) | [Transport_MOKE-folder.zip](https://github.com/nbb2026/Transport-all/releases/download/moke-v1.0/Transport_MOKE-folder.zip) | [Update_Transport_MOKE.bat](https://github.com/nbb2026/Transport-all/releases/download/moke-v1.0/Update_Transport_MOKE.bat) | [`Transport-MOKE`](https://github.com/nbb2026/Transport-all/tree/Transport-MOKE) |
| <img src="https://raw.githubusercontent.com/nbb2026/Transport-all/Transport-FMR/Other-files/assets/Transport_FMR_icon_64.png" width="32" alt=""> | **Transport_FMR v1.0**: the FMR and STFMR pages | [Transport_FMR.exe](https://github.com/nbb2026/Transport-all/releases/download/fmr-v1.0/Transport_FMR.exe) | [Transport_FMR-folder.zip](https://github.com/nbb2026/Transport-all/releases/download/fmr-v1.0/Transport_FMR-folder.zip) | [Update_Transport_FMR.bat](https://github.com/nbb2026/Transport-all/releases/download/fmr-v1.0/Update_Transport_FMR.bat) | [`Transport-FMR`](https://github.com/nbb2026/Transport-all/tree/Transport-FMR) |

**Updater** (user, 2026-11-27): for the computer a program is used on. Put the `.bat` in the folder the
`.exe` is kept in and double-click it: it downloads the newest `.exe` into that folder when the one there
is not the newest. It checks the download against its SHA-256, never replaces a program that is running,
and deletes the old one once the new one is in place. Nothing is installed (it uses `curl`, `certutil`
and `tasklist` of Windows 10/11). Windows may ask once whether to run a file from the internet: More
info, Run anyway.

Each is one page, or one rack's pages, of the whole program as a program of its own. Each release page
gives the commit and the SHA-256 of its files: [PPMS](https://github.com/nbb2026/Transport-all/releases/tag/ppms-v1.0), [RT](https://github.com/nbb2026/Transport-all/releases/tag/rt-v1.0), [MOKE](https://github.com/nbb2026/Transport-all/releases/tag/moke-v1.0), [FMR](https://github.com/nbb2026/Transport-all/releases/tag/fmr-v1.0).

The whole program, every page in one window, is the Python script [`Transport_all.py`](Transport_all.py)
on `main`. It is kept as the backup and is no longer built as an .exe (user, 2026-11-27); see
[Windows .exe](#windows-exe) to build one by hand.

Two of these programs can be open at once: an instrument one of them has connected is refused to the
others until it is disconnected there.

## What it is

Instrument control and acquisition for magneto-electro-optical transport
experiments: magneto-optic Kerr imaging, harmonic Hall transport in a PPMS,
room-temperature electrical measurement, and ferromagnetic and spin-torque
ferromagnetic resonance.

Everything runs from one Tkinter application,
[`Transport_all.py`](Transport_all.py). A single process owns the
whole shared rack, so one page cannot take an instrument another page is
already driving, and every source is brought to a safe state on shutdown.

## Running it

```bash
python3 Transport_all.py
```

Python 3.11 is what the program is developed and tested against. Every
hardware backend is imported lazily, so the application opens with none of
them installed and a page whose driver is missing reports that rather than
stopping the rest from working.

| Backend | Needed for |
| --- | --- |
| `pyvisa` | Every GPIB instrument |
| `numpy`, `opencv-python`, `Pillow` | Camera frames, region statistics, drift correction |
| `pco` | PCO camera acquisition |
| `zhinst` | Zurich Instruments MFLI lock-in |
| `pyserial` | LED controller, Cell-VSDM sample stage, KEPCO serial paths |
| `pythonnet` | PPMS through QDInstrument, Thorlabs rotation |

[`requirements.txt`](requirements.txt) pins the versions of the last build
verified on the lab PC; `python3 -m pip install -r requirements.txt` installs
them (on a Mac only the first five; the vendor packages are Windows-only).

## Windows .exe

`Transport_all.py` is no longer built or published as an .exe (user,
2026-11-27: "delete the main exe version and only save the py script for
backup"). The Windows programs are the four standalone ones at the top of this
page, each built on its own branch. The pre-release "Windows exe (newest
main)" and the workflow that filled it are gone; the recipe is kept, so the
whole program can still be built by hand (below).

A hand-built `Transport_all.exe` runs on Windows 10/11 (64-bit) without Python.
Put it in a folder you keep, such as `C:\Transport_all\`: the results folders
(`Transport_all_<page>_Results`) are made beside it, as they are beside the
.py. It holds every Python package but not the instrument drivers, which are
installed as for the .py: NI-VISA and the GPIB driver, the PCO camera driver,
Thorlabs Kinesis, LabOne and MultiVu/QDInstrument. DLLs kept beside the .py
(`PerformaxCom.dll` and `SiUSBXp.dll` for the Newmark stage) go beside the
.exe. An MFLI on LabOne 18.12 still needs the Python 3.7 bridge from
`Other-files/INSTALL_MFLI_LABONE_18_12.bat`. The .exe is not code-signed, so
Windows SmartScreen may say "Windows protected your PC" (More info, then Run
anyway). `Transport_all.exe --package-self-test` loads every library inside it
without opening the program and writes the result to
`Transport_all_package_self_test.txt` beside it.

**Build it yourself** on Windows, from the repository root:

```bat
py -3.11 -m pip install -r requirements.txt pyinstaller==6.22.3
py -3.11 -m PyInstaller --noconfirm --clean Other-files/packaging/Transport_all.spec
```

The .exe is `dist\Transport_all.exe`. The recipe is
[`Other-files/packaging/Transport_all.spec`](Other-files/packaging/Transport_all.spec).
With `set TRANSPORT_ONE_FOLDER=1` first, the same recipe makes the one-folder
build (`dist\Transport_all\Transport_all.exe` with `_internal` beside it),
which starts faster.

## Pages

The notebook has ten pages, grouped by rack.

**MOKE.** `MOKE light` drives the four-channel LED illumination and holds the
camera connection and live view. `MOKE motor` moves the Cell-VSDM sample
stage. `MOKE magnet` runs the KEPCO bipolar supply against a gaussmeter and
shows the difference image and its region of interest. `MOKE-24` and
`MOKE-6221` are the Keithley source-measure and current-source pages; the
MOKE-24 page drives a 2410 or a 2400, chosen on the page, for its voltage
scan against the region of interest, and the 6221
page does both one-pulse-per-current round trips and fixed-current multi-pulse
acquisition, averaging the region of interest over the post-pulse interval.

**Non-local** has one connection box in two columns (Keithley 2410 or 2400,
6221 and 2182A; two SR830s and the MFLI). As on RT-E, the Zurich row also
holds its reference input (**Ref.**) and time constant (**TC (s)**, default
1 s since 2026-10-14), used by 6221-IV and Gate-VI. The Ref. follows the chosen Zurich:
DEV4414 on Trigger In 1 (the default, as RT-E), DEV4435 on Aux Input 1. Once
connected, the row shows "Locked" or "Warning", read once a second. Four sub-tabs use the rack. Each scan
has a settings box and a scan box, side by side when they fit, as on RT-E,
and each run writes its own folder, as on PPMS and STFMR:
- **|R| vs time** measures the sample resistance continuously with the
  Keithley as an autoranged current source (1 nA to 1 mA, 5 V protection),
  plotted over the last 20 s. It was on the MOKE-24 page until 2026-10-08.
- **2400-IV** steps the Keithley voltage once from Start to End (default
  −6 to 6 V in 0.25 V steps, ±20 V at most, 20 V OVP) and plots the current
  read at each step.
  - **Boxes:** "2400-IV settings" holds the safety tick, sample and current
    limit; "2400-IV scan" holds Start/End/Step/Settle and the buttons.
  - **Files:** the folder is chosen at Start. The run folder
    `2400-IV_<sample>_<time>/` holds the live CSV and the parameter log. The
    sweep's end saves the plot there, and "Save plot PNG" saves it again.
- **6221-IV** is the RT-E Current scan on this page's 6221 and lock-ins,
  with RT-E's settings and start-up values:
  - **"6221-IV settings":** the 6221 (mA RMS, Frequency, Compliance, Set
    6221, Trigger line, "6221 / 2400 OFF"). Each lock-in has a harmonic
    (1, 2, 3, 1+2 or 1+2+3) and a Measure tick. The defaults are the
    Zurich alone at 1+2+3, 0.1 mA RMS, 17.3 Hz and 50 V.
  - **"6221-IV scan":** Start/End/Step (default 0.01 to 1 mA RMS in 0.01 mA
    steps), Loops, Settle 0.5 s, Acquire 1 s and Round trip.
  - **Harmonics:** an SR830 set to 1+2 or 1+2+3 runs the sweep once per
    order. The Zurich reads all its orders at once on separate demodulators.
  - **The 6221:** as on RT-E, the sine starts once on one fixed range, and
    after that only its amplitude changes, so the lock-ins stay locked.
  - **Plots:** one X / Y / θ row per measured order, with the meters
    overlaid.
  - **Files:** the run folder is `6221-IV_<time>/`, with the live CSV and
    the parameter log.
- **Gate-VI scan** measures non-local voltage against a gate, with the
  Keithley as the gate source and lock-in or nanovoltmeter detection.
  - **"Gate-VI settings":** the 6221 read current and each meter's read
    settings.
  - **"Gate-VI scan":** the pulse sweep, Start/Stop and the readouts.
  - **Files:** each scan writes a `NonLocal_VI_<time>/` folder.

Only one of the four runs at a time. If the 6221 is connected
on this page, it is switched off before |R| or I–V starts. The Keithley is
zeroed and switched off when they end.

**PPMS** controls temperature, field and rotation, and runs harmonic Hall
transport with up to three SR830 lock-ins and the MFLI. Meters measuring the
same harmonic share one plot. Selecting `1+2` or `1+2+3` on a meter runs the
scan once per harmonic order.

**RT-E** is the same transport measurement at room temperature, with the field
from a KEPCO supply read back by a Lake Shore gaussmeter.

**FMR** sweeps field against a Keysight PNA network analyser. It starts with
the Lake Shore 648 as its magnet supply at `GPIB0::15::INSTR`, the Lake Shore
475 at `GPIB0::12::INSTR` and the PNA at `GPIB0::16::INSTR` (since
2026-11-13); the KEPCO 4886 is the other choice in the supply list.
**STFMR** sweeps field with a
microwave source and lock-in detection, with MFLI, SR830 or both together.

**Setting a field.** FMR, SHHV and STFMR each have a "Set field" control
(since 2026-11-14): type the target in G and its tolerance, tick the page's
safety confirmation, and press Set field. The program steps the page's chosen
magnet supply (the KEPCO 4886 or its Lake Shore) until the Lake Shore 475
reads the target within the tolerance, and then keeps the field there: it
reads the LS475 again about every two seconds and corrects the current
whenever the field has left the tolerance.
- **Where:** in the field-output box on FMR (a row of its own) and STFMR
  (right of the safety tick); in the instrument rack under the LS475's
  reading on SHHV.
- **How:** it first makes a small probe step (0.02 A, then 0.1 and 0.5 A if
  the field did not move) to measure how many G the magnet gives per A and in
  which direction. Then each correction is a PID step on the field error.
  The first corrections are at most 0.5 A; while the field follows as
  predicted the limit doubles, up to a tenth of the supply's maximum current.
- **Reading the field:** after every step it waits 0.5 s, then reads the
  LS475 in groups of three until two groups in a row agree within the
  tolerance. A field that is still moving is waited for, up to 15 s.
- **Stopping:** while a field is being set or held the button reads
  **Stop hold**: it ends the regulation and leaves the current where it is.
  The page's red Zero / OFF ends it and zeroes the supply. For two seconds
  after it ends the button starts nothing, so a double-click cannot restart
  it. The page is busy until one of them is pressed: a scan cannot start
  while a field is held, and on STFMR the live lock-in readings pause.
- **When it gives up** it leaves the current where the last step put it and
  says why:
  - the gaussmeter did not respond to the probe steps, or sees under 20 G per
    A, as a probe outside the magnet's gap does (the current has then moved
    0.62 A at most);
  - the current was changed and the field did not respond (under a quarter
    of the expected change, judged once the change is worth 5 % of the
    field): the current is not changed again, and the message says the
    gaussmeter may not be working;
  - while a field is held, the reading jumped with the current unchanged (by
    more than five tolerances, or 0.6 % of the field if that is more): the
    probe moved, the range changed or the meter failed, and the current is
    not changed at all;
  - while a field is held, the current would have to move more than 5 % (or
    0.2 A) from where the target was first reached: a magnet's field does
    not drift that far, so the gaussmeter is drifting or fading;
  - the field did not settle within 15 s, or the readings are noisier than
    the tolerance;
  - the target needs more than the supply's maximum current;
  - the tolerance is finer than one 1 mA setpoint step;
  - a Lake Shore supply is not at its setpoint (stopped mid-ramp): Apply
    output or Zero / OFF it first.
- **It trusts the gaussmeter.** A probe that keeps reading consistently but
  wrongly (slipped partly out of the gap, on the wrong range) is followed, up
  to the supply's maximum current. Check the probe before a large field, and
  keep the supply's own current limit set for your magnet.
- The scans are unchanged: they still set currents, not fields, and start
  only once the regulation has been stopped.

**Plot pictures.** Every scan saves a screenshot of its plots in its run
folder when it ends, whether it completed, was stopped or failed, as long as
it saved at least one point (since 2026-11-13; Gate-VI did already, and MOKE
magnet and MOKE-24 only with "Save CSV + PNG"). A page with one plot saves
`<run name>_plot_snapshot.png`; a page with a grid of plots (PPMS, SHHV,
6221-IV, STFMR) saves one picture of the whole plot box,
`<run name>_plots_snapshot.png`. It is a screenshot, so it holds what is on
the screen at that moment: keep the scan's page shown and the program's
window uncovered, and the PC unlocked. If the page is not the one shown, no
picture is saved and the run log's `plot_snapshots` entry says why; the CSV
and the log are not affected. The CIDWM pulse scan has no axis plot and
saves camera images instead.

**Lock-in range.** With its autorange on, a lock-in's range steps down when
the reading has been under 1 % of the range for three readings in a row with
the reference locked (since 2026-11-16; it was 15 % on ST-FMR and Non-local
and for the Zurich, 10 % on PPMS and SHHV). For an SR830 the reading is R
against its full scale; for the Zurich it is the input's peak, every
harmonic and the noise included, against its input range. The range still
steps up at once on an overload, and on ST-FMR, Non-local and the Zurich
also at 85 % of the range. Two things keep those rules from taking turns
for ever:

- An SR830 range that had to be left because it overloaded while R was small
  on it (a weak harmonic beside a strong fundamental) is not returned to
  until the next set-up: a scan's Start, each pass of an ST-FMR sweep, the
  next order of a 6221-IV pass, and on PPMS and SHHV a new excitation, pass
  or sweep.
- The Zurich chooses its own range. A step down that did not lower the
  range is not asked for again on that range, and each time a range that
  was stepped down has to go up again, the next step down needs twice as
  many low readings in a row.

A reading can now stay at 1-2.5 % of an SR830's full scale without the range
stepping down, where it used to be brought to 15-40 %. That is what the 1 %
rule means; for the finest resolution on a small signal, set the range by
hand and untick the autorange.

**Angle scans.** The plots of an angle scan (SHHV: Angle, Angle+Field,
Angle+Current; PPMS: Angle, Angle+Temperature, Angle+Field) span exactly the
scan's own angles from the first point on, with ticks at round angles: a
scan from 0° to 360° is drawn on 0 to 360 with a tick every 90°, one from 0°
to −360° on −360 to 0 (since 2026-11-15; the limits were rounded out to the
tick step, so −360 to 0 was drawn on −400 to 0, and they grew with the
points). The angles are shown as the stage or rotator reports them, and a
point read back a little outside the range widens the axis rather than
being left off.

**Choosing a folder.** Every folder choice (a run's folder, an image folder)
opens the program's own folder window (since 2026-11-15; it was Tk's, which
could only choose). It lists the folders of the Directory shown; a
double-click or Return opens one, "Up" or Backspace goes back, and OK gives
the folder picked in the list, or the one shown when none is picked. Three
buttons work on the folder picked in the list:

- **New folder** asks for a name and makes it in the Directory shown.
- **Rename** (F2) asks for the new name; what the folder holds is kept.
- **Delete** (Del) asks first, with No as the default, and says how many
  files and folders it holds. An empty folder is removed. One with anything
  in it goes to the Windows Recycle Bin, where it can be restored.

The rules, for the data's sake:

- A name must be a valid Windows folder name, and never one already there.
- The program never deletes data for good. A folder with data is refused
  where Windows would not recycle it: a network or removable drive, the
  Recycle Bin switched off or smaller than the folder, more than 20000 files
  and folders in it, or a part of it that cannot be read or is a link to
  another folder. Delete such a folder in the Windows Explorer.
- A folder that a running scan is saving into (its run folder, a MOKE
  scan's image folder, or any folder above them) cannot be renamed or
  deleted until the scan has ended, and while any scan runs no folder with
  data is deleted at all. Empty folders, New folder and Rename elsewhere
  still work during a scan.
- A link to another folder is not deleted here.

Save-as and open-file windows are Tk's own, as before.

## Instruments

Keithley 2410, 2400, 6221 and 2182A; Stanford Research SR830 lock-ins;
Zurich Instruments MFLI; KEPCO BOP bipolar supplies; Lake Shore gaussmeters;
Rohde & Schwarz SMB100A; a Keysight PNA network analyser; Quantum Design PPMS
through either QDInstrument or MultiPyVu; PCO cameras; Thorlabs K10CR1
rotation; and serial LED and sample-stage controllers.

Default VISA addresses are set in the code and editable in the interface.

An SR830 shows X on CH1 and Y on CH2 once the program has connected it
(since 2026-11-15; every page had set R and θ). This is the front-panel
display only: the saved X, Y, R and θ are read from the instrument
whatever it shows. The CH1 and CH2 OUTPUT sockets follow the display when
they are set to "Display" on the instrument.

## Layout

| Path | Contents |
| --- | --- |
| `Transport_all.py` | The application |
| `requirements.txt` | Its Python packages, with the lab PC's versions |
| `Other-files/packaging/` | PyInstaller recipe for `Transport_all.exe` and its self-test |
| `Other-files/test*.py`, `Other-files/test/` | Offline regression tests |
| `Other-files/README.md` | Dated change log, newest first |
| `Other-files/docs/` | Generated user manual |
| `Other-files/MEO_Transport_V3_Windows_Build_Package/` | Frozen Windows release |
| `Test_Microwave_NH_dev.py` | Standalone fixed-current microwave x modulation grid test (`Other-files/Test_Microwave_NH_dev_README.md`) |
| `MS-fourState.py` | PPMS state writing and zero-field SR830 read: a cycle such as D-A-B-E-B-A repeated, or a typed sequence, plus manual angle, field and current settings as on the PPMS page; runs on its own, with the main program's instrument code copied in (`Other-files/MS-fourState_README.md`) |

## Tests

The tests run with no hardware attached. Instrument access is stubbed, so they
cover acquisition logic, safety interlocks, scan scheduling and plotting rather
than real measurement.

```bash
cd Other-files && python3 -m unittest discover -s . -p "test_*.py"
```

```bash
cd Other-files/test && PYTHONPATH=../.. python3 -m unittest \
  test_instrument_safety_logic test_mfli_autorange test_mfli_overload \
  test_stfmr_realtime_recording
```

That is 381 and 104 tests respectively, all passing as of 2026-10-04.
On macOS they hang while the display is asleep, because Tk waits for the
window server; wake it first, or run them under `caffeinate -u`.

The same tests, plus layout checks with a screenshot of each page, run on
GitHub's Linux and Windows machines on every push to `main`
([`.github/workflows/gui-tests.yml`](.github/workflows/gui-tests.yml),
[`Other-files/ci/gui_checks.py`](Other-files/ci/gui_checks.py)). Results and
screenshots are on the repository's Actions tab. Running them there keeps
test windows off the desk computer's screen. The .exe files of the standalone
programs are built and checked by workflows on their own branches.

Passing tests are not hardware acceptance. They build panels from stubs and
never run the real constructor, so a change should also be checked by starting
the application and opening every page.

## Notes

If Connect PPMS fails with a message about loading `QDInstrument.dll`, look in
it for `EndpointNotFoundException` or TCP error 10060/10061: that is a network
fault, not the DLL. Check the PPMS computer's address with `ipconfig` and the
port from the measuring PC with `Test-NetConnection <PPMS IP> -Port 11000`.
`Other-files/README.md` (2026-10-06) has the PPMS1 case and its fix.

Older LabOne releases expose the MFLI only through a Python 3.7 API. When the
installed `zhinst` cannot be imported directly, the program looks for a Python
3.7 interpreter with `zhinst` 18.12 and talks to the instrument through it as a
subprocess.

The development machine keeps a project-local CPython under `.pyenv` with a
`.venv311` environment. Both are ignored here and excluded from release
packages. That environment was created at an earlier path, so its activation
script no longer works; `Other-files/README.md` records the invocation that
does.

## License

GPL-3.0. See [LICENSE](LICENSE).
