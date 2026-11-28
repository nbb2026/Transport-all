"""The host window of the standalone SHHV & Switch application, and what steers its
extraction from the main program (tools/extract_app.py reads this file;
it is not imported by the application).

* Methods of ``CombinedControlApp`` below replace the main program's methods
  of the same name: the window with the SHHV & Switch page and the log only, and a
  close that shuts down that page only.
* Top-level definitions below replace, or add to, the main program's.
"""
# What is extracted, and where to.
PAGE_CLASS = "RTEPanel"
APP_NAME = "the SHHV & Switch page"
# This program's own version (user, 2026-11-27: "name PPMS, RT, MOKE, FMR exe all as v1.0"), not the
# main program's.  It is in the .exe's properties and in every results file, and it names the release
# ("Transport_RT v1.0"): raise it here, and in pyproject.toml, and push the tag rt-v<version>, to start a new release.
APP_VERSION = "1.0"
OUTPUT = "transport/rt/app.py"
GLUE_FILES = ("ppms_package_glue.py",)
# Everything named after the page is kept, used by kept code or not.
KEEP_PATTERNS = ("(?i)(^|_)rte(_|$)", "(?i)shhv")

# Pages and parts of the main program the SHHV & Switch application does not have.
# A name here is left out even where kept code still names it.
DROP = (
    "create_motor_subsystem", "run_pco_dll_self_test",
    "TkCameraWindow", "CameraAcquisitionWorker", "CameraVideoRecorder", "AutoFocusManager",
    # The MOKE light page's LED controller and its methods of the main window
    # (kept by name only: connect, disconnect ... are also instrument methods).
    "LEDSerialController", "ChannelSettings", "LEDProtocolError", "set_connected_ui", "update_action_state",
    "set_busy", "run_task", "connect", "disconnect", "load_state", "query_channel", "query_all", "all_off",
)
# Stand-ins for dropped names that kept code tests with isinstance().
STUBS = {}
# Statements of the main window's __init__ that start other pages.
INIT_DROP = (
    "self.nonlocal_vi_mfli_device_var.trace_add(",
    "self.refresh_ports()",
    "self.set_connected_ui(",
    "self.update_stage_controls()",
    "self._update_magnet_controls()",
    "self.root.after(250, self._magnet_poll_timer)",
    "self.controller = LEDSerialController(",
    "self.port_var = ", "self.channel_vars", "self.action_widgets",
)
# Names kept whatever the reachability says (helpers only tests call).
KEEP = ("recycle_bin_available",)
# What the program is started from.  Everything it cannot reach from these is taken out of the generated module
# (user, 2026-11-28: "remove the unused code in RT to make it as shorter as possible"): the PPMS page's own
# window, scans, macro and cryostat commands, which this page replaces, the parts of the instrument classes only
# other pages use, and the helpers only tests called (KEEP and KEEP_PATTERNS above no longer hold those).
PRUNE_ROOTS = ("main", "run")
# Names the transport package already has: imported, not copied.
PACKAGE_IMPORTS = {}
# Lines after the imports.  _PROGRAM_FILE stands for the main program's
# __file__ everywhere in the generated module: the entry script's place (the
# repository root, or the unpacked folder of the .exe), where the assets,
# DLLs kept beside the program and the helium history are looked for.
EXTRA_IMPORTS = (
    '_PROGRAM_FILE = str(Path(__MODULE_FILE__).resolve().parents[2] / "Transport_RT.py")',
    '# Installed with pip, the package is in site-packages: the folder the program is started in stands in.',
    'if not getattr(sys, "frozen", False) and {"site-packages", "dist-packages"} & set(Path(_PROGRAM_FILE).parts):',
    '    _PROGRAM_FILE = str(Path.cwd() / "Transport_RT.py")',
)
# Literal text of the generated module to replace.  Its own taskbar identity,
# so it does not group under the main program's button when both are open.
REPLACE = {
    "'NH.ProfChen.MagnetoElectroOpticalMicrowaveTransport'": "'NH.ProfChen.TransportRT'",
    # Files are named after the program or the measurement that made them (see "How a run is saved" below).
    '"Transport_log_%Y%m%d_%H%M%S.txt"': '"Transport_RT_log_%Y%m%d_%H%M%S.txt"',
    "f'{self.ppms_page_name} run folder'": "f'{self._rte_run_name()}: run folder'",
    "f'{self.ppms_page_name} run log'": "f'{self._rte_run_name()}: run log'",
}

# Changes to the main program's text made before the extraction (old text, new text; each old text occurs once).
# The main program is not changed for this program's measurement tabs (user, 2026-11-27: "no need to main"), so
# what its SHHV & Switch page needs for them is put in here: the three settings below it reads
# (RTE_MEASUREMENTS, RTE_DEFAULT_MEASUREMENT, RTE_SCAN_BOX_FIRST; the values further down replace them),
# rte_set_measurement, the Scan box before the Settings box, and the measurement in the saved rows and settings.
SOURCE_REPLACE = (
    ("RTE_TAB_TITLE = 'SHHV & Switch'\n",
     (
         "RTE_TAB_TITLE = 'SHHV & Switch'\n"
         'RTE_MEASUREMENTS = {}\n'
         'RTE_MEASUREMENT_START = {}\n'
         "RTE_DEFAULT_MEASUREMENT = ''\n"
         'RTE_SCAN_BOX_FIRST = False\n'
         "RTE_PLOT_TITLE_TAIL = 'X, Y, phase vs measured field / excitation current / sample angle / pulse current'\n"
     )),
    ("        self.ppms_plot_frame.configure(text=f'{self.ppms_page_name}: X, Y, phase vs measured field / excitation current / sample angle / pulse current')\n",
     "        self.ppms_plot_frame.configure(text=f'{self.ppms_page_name}: {RTE_PLOT_TITLE_TAIL}')\n"),
    ((
        '        self.ppms_simple_mode.set(self.rte_default_scan_mode)\n'
        '        self._rte_mode_changed()\n'
    ),
     (
         '        self.ppms_simple_mode.set(self.rte_default_scan_mode)\n'
         '        self._rte_mode_changed()\n'
         '        if RTE_MEASUREMENTS:\n'
         '            self.rte_set_measurement(RTE_DEFAULT_MEASUREMENT if RTE_DEFAULT_MEASUREMENT in RTE_MEASUREMENTS else next(iter(RTE_MEASUREMENTS)))\n'
     )),
    ((
        '        controls.columnconfigure(1, weight=1)\n'
        "        settings = ttk.LabelFrame(controls, text='Settings', padding=4)\n"
        "        settings.grid(row=0, column=0, sticky='nsew')\n"
    ),
     (
         '        controls.columnconfigure(0 if RTE_SCAN_BOX_FIRST else 1, weight=1)\n'
         "        settings = ttk.LabelFrame(controls, text='Settings', padding=4)\n"
         "        settings.grid(row=0, column=1 if RTE_SCAN_BOX_FIRST else 0, sticky='nsew')\n"
     )),
    ((
        "        scan = ttk.LabelFrame(controls, text='Scan', padding=4)\n"
        "        scan.grid(row=0, column=1, sticky='nsew', padx=(6, 0))\n"
    ),
     (
         "        scan = ttk.LabelFrame(controls, text='Scan', padding=4)\n"
         "        scan.grid(row=0, column=0 if RTE_SCAN_BOX_FIRST else 1, sticky='nsew', padx=(0, 6) if RTE_SCAN_BOX_FIRST else (6, 0))\n"
     )),
    ((
        "        combo.bind('<<ComboboxSelected>>', self._rte_mode_changed)\n"
        "        self.rte_edit_widgets.append((combo, 'readonly'))\n"
    ),
     (
         "        combo.bind('<<ComboboxSelected>>', self._rte_mode_changed)\n"
         '        self.rte_scan_mode_combo = combo\n'
         "        self.rte_edit_widgets.append((combo, 'readonly'))\n"
     )),
    ('            self._arrange_pair_by_width(controls, settings, scan, gap=controls_gap, stack_gap=4, right_width=scan_stacked_width, left_width=settings_without_block)\n',
     (
         '            if RTE_SCAN_BOX_FIRST:\n'
         '                self._arrange_pair_by_width(controls, scan, settings, gap=controls_gap, stack_gap=4, left_width=scan_stacked_width, right_width=settings_without_block)\n'
         '            else:\n'
         '                self._arrange_pair_by_width(controls, settings, scan, gap=controls_gap, stack_gap=4, right_width=scan_stacked_width, left_width=settings_without_block)\n'
     )),
    ((
        '                    room = self._pair_natural_width(settings) + controls_gap\n'
        '                    room = max(room, min(room + 4, controls.winfo_width() - scan_stacked_width()))\n'
        '                controls.columnconfigure(0, minsize=room)\n'
    ),
     (
         '                    room = self._pair_natural_width(settings) + (0 if RTE_SCAN_BOX_FIRST else controls_gap)\n'
         '                    room = max(room, min(room + 4, controls.winfo_width() - scan_stacked_width() - (controls_gap if RTE_SCAN_BOX_FIRST else 0)))\n'
         '                controls.columnconfigure(1 if RTE_SCAN_BOX_FIRST else 0, minsize=room)\n'
     )),
    ('    def _rte_mode_changed(self, _event=None):\n',
     (
         '    def rte_measurement_busy(self) -> bool:\n'
         '        state = self.__dict__\n'
         "        return bool(state.get('ppms_environment_busy') or state.get('ppms_field_scan_running') or state.get('rte_closed') or state.get('rte_stage_prompt_open'))\n"
         '    def rte_set_measurement(self, name) -> bool:\n'
         '        scans = RTE_MEASUREMENTS.get(name)\n'
         '        if not scans:\n'
         '            return False\n'
         '        state = self.__dict__\n'
         "        was = state.get('rte_measurement')\n"
         '        if was == name:\n'
         '            return True\n'
         '        if was is not None and self.rte_measurement_busy():\n'
         '            return False\n'
         "        kept = state.setdefault('rte_measurement_scans', {})\n"
         '        if was is not None:\n'
         '            kept[was] = self.ppms_simple_mode.get()\n'
         '        self.rte_measurement = name\n'
         "        combo = state.get('rte_scan_mode_combo')\n"
         '        if combo is not None:\n'
         '            combo.configure(values=scans)\n'
         '        start = RTE_MEASUREMENT_START.get(name, {})\n'
         "        scan = kept.get(name) if kept.get(name) in scans else start.get('scan') if start.get('scan') in scans else scans[0]\n"
         '        if scan != self.ppms_simple_mode.get():\n'
         '            self.ppms_simple_mode.set(scan)\n'
         '            self._rte_mode_changed()\n'
         '        else:\n'
         '            if scan == SWITCH_LOOP_SCAN_MODE:\n'
         "                old, new = (tuple(RTE_MEASUREMENT_START.get(n, {}).get('ranges', {}).get(scan) or SWITCH_LOOP_DEFAULT_RANGE) for n in (was, name))\n"
         '                if old != new and tuple(str(v.get()).strip() for v in self.ppms_simple_range) == old:\n'
         '                    for variable, value in zip(self.ppms_simple_range, new):\n'
         '                        variable.set(value)\n'
         '            self._rte_follow_scan_times(scan)\n'
         "        frame = state.get('ppms_plot_frame')\n"
         '        if frame is not None:\n'
         "            frame.configure(text=f'{name}: {RTE_PLOT_TITLE_TAIL}')\n"
         '        self._rte_show_measurement_start(start)\n'
         '        return True\n'
         '    def _rte_show_measurement_start(self, start):\n'
         '        state = self.__dict__\n'
         "        shown = state.setdefault('rte_measurement_shown', {})\n"
         "        fields = (state.get('rte_outer_ranges') or {}).get('Angle+Field') or [None]\n"
         "        loop_fields = (state.get('rte_outer_ranges') or {}).get(SWITCH_LOOP_SCAN_MODE) or [None]\n"
         "        for key, variable, base in (('current_ma', state.get('ppms_transport_current_var'), f'{RTE_TRANSPORT_CURRENT_RMS_MA:g}'), ('harmonic_a', state.get('ppms_transport_harmonic_a_var'), '2'), ('pulse_width_us', state.get('rte_pulse_width_us'), f'{SWITCH_DEFAULT_PULSE_WIDTH_US:g}'), ('angle_field_g', fields[0], RTE_OUTER_ROWS['Angle+Field']['defaults'][0]), ('loop_field_g', loop_fields[0], RTE_OUTER_ROWS[SWITCH_LOOP_SCAN_MODE]['defaults'][0])):\n"
         '            new, was = str(start.get(key, base)), shown.get(key, base)\n'
         '            if variable is None or new == was or str(variable.get()).strip() != was:\n'
         '                continue\n'
         '            variable.set(new)\n'
         '            shown[key] = new\n'
         "            if key == 'harmonic_a':\n"
         "                self._ppms_apply_selected_harmonic('830_a')\n"
         '    def _rte_run_name(self) -> str:\n'
         "        return self.__dict__.get('rte_measurement') or self.ppms_page_name\n"
         '    def _append_ppms_live_csv(self, row):\n'
         "        recorder = self.__dict__.get('rte_recorder')\n"
         '        if recorder is None:\n'
         "            raise RuntimeError('No run is open; the point was not saved and the scan stopped')\n"
         '        recorder.append_row(row)\n'
         '    def _rte_scan_time_default(self, key, mode) -> str:\n'
         "        own = RTE_MEASUREMENT_START.get(self.__dict__.get('rte_measurement'), {}).get(key, {}).get(mode)\n"
         '        if own:\n'
         '            return str(own)\n'
         "        if key == 'acquire_s':\n"
         "            return f'{RTE_FIELD_ACQUISITION_S if mode in RTE_FIELD_SWEEP_MODES else SWITCH_ACQUISITION_S if mode in SWITCH_MODES else RTE_ACQUISITION_S:g}'\n"
         "        return f'{SWITCH_SETTLE_S if mode in SWITCH_6221_MODES else RTE_SETTLE_S:g}'\n"
         '    def _rte_follow_scan_times(self, mode):\n'
         "        acquire = self.__dict__.get('ppms_acquisition_time_var')\n"
         '        if acquire is not None:\n'
         "            shown = self.__dict__.get('rte_acquisition_default_shown')\n"
         "            new = self._rte_scan_time_default('acquire_s', mode)\n"
         '            if shown is None or str(acquire.get()).strip() == shown:\n'
         '                acquire.set(new)\n'
         '                self.rte_acquisition_default_shown = new\n'
         "        settle = self.__dict__.get('ppms_field_scan_stable_var')\n"
         "        if settle is not None and 'rte_settle_default_shown' in self.__dict__:\n"
         "            new = self._rte_scan_time_default('settle_s', mode)\n"
         '            if str(settle.get()).strip() == self.rte_settle_default_shown:\n'
         '                settle.set(new)\n'
         '                self.rte_settle_default_shown = new\n'
         '    def _rte_mode_changed(self, _event=None):\n'
     )),
    ('                row = dict(module=self.ppms_page_name, scan_mode=mode, loop=loop, point=point,\n',
     "                row = dict(module=self.ppms_page_name, **({'measurement': self.rte_measurement} if self.__dict__.get('rte_measurement') else {}), scan_mode=mode, loop=loop, point=point,\n"),
    ((
        '            file_name=typed_name, mode=mode,\n'
        "            plan=dict(**(dict(typed=box(state.get('rte_switch2_pulses_var'"
    ),
     (
         "            file_name=typed_name, **({'measurement': state['rte_measurement']} if state.get('rte_measurement') else {}), mode=mode,\n"
         "            plan=dict(**(dict(typed=box(state.get('rte_switch2_pulses_var'"
     )),
    ("SWITCH_DEFAULT_FIELDS_G = '-12'\n",
     "SWITCH_DEFAULT_FIELDS_G = '-12'\nSWITCH_LOOP_DEFAULT_FIELDS_G = SWITCH_DEFAULT_FIELDS_G\n"),
    ("    SWITCH_LOOP_SCAN_MODE: dict(label='Outer field G:', defaults=(SWITCH_DEFAULT_FIELDS_G,),\n",
     "    SWITCH_LOOP_SCAN_MODE: dict(label='Outer field G:', defaults=(SWITCH_LOOP_DEFAULT_FIELDS_G,),\n"),
    # One row where there were two (user, 2026-11-27: "shrink the two row in the figure to one row", "this also
    # one row"): the scan note beside Round trip wherever there is room, the stage block in one row under the
    # parameters and lock-ins where it fits, and the supply's and field's live lines wide enough for one line
    # where the connections are in two columns.  A narrow window keeps the two rows.
    ((
        '    def _rte_arrange_connection_columns(self, measurement, rack, instruments, live):\n'
        '        def rack_width() -> int:\n'
    ),
     (
         '    def _rte_arrange_connection_columns(self, measurement, rack, instruments, live):\n'
         '        def live_zero_px(widget) -> int:\n'
         "            return tkfont.nametofont('TkDefaultFont', root=widget).measure('0')\n"
         '        def rack_width() -> int:\n'
     )),
    ('            moved = max((widget.winfo_reqwidth() for widget in live), default=0)\n',
     "            moved = max((RTE_LIVE_WIDE_CHARS * live_zero_px(widget) + 16 if widget.winfo_class() == 'TLabel' else widget.winfo_reqwidth() for widget in live), default=0)\n"),
    ((
        '            measurement._rte_live_beside_rack = not side\n'
        '            try:\n'
    ),
     (
         '            measurement._rte_live_beside_rack = not side\n'
         '            try:\n'
         '                for widget in live:\n'
         "                    if widget.winfo_class() == 'TLabel':\n"
         '                        chars = RTE_LIVE_WIDE_CHARS if side else 32\n'
         '                        widget.configure(width=chars, wraplength=chars * live_zero_px(widget))\n'
     )),
    ('                    note = stacked and room > 1 and room >= rows_width + note_label.winfo_reqwidth() + 14\n',
     '                    note = room > 1 and room >= rows_width + note_label.winfo_reqwidth() + 14\n'),
    ((
        "                if self.__dict__.get('rte_note_place', 'under') != ('beside' if note else 'under'):\n"
        "                    self.rte_note_place = 'beside' if note else 'under'\n"
        '                    note_label.grid_configure(**(note_beside if note else note_under))\n'
    ),
     (
         "                note_place = ('beside' if stacked else 'beside, wide') if note else 'under'\n"
         "                if self.__dict__.get('rte_note_place', 'under') != note_place:\n"
         '                    self.rte_note_place = note_place\n'
         "                    note_label.grid_configure(**({**note_beside, 'sticky': 'e' if stacked else 'w'} if note else note_under))\n"
     )),
    ('            def arrange_stage_block(_event=None):\n',
     (
         '            zero_cell = zero.master if zero.master is not stage_box else zero\n'
         '            stage_live, stage_widths = live, {}\n'
         '            def stage_tall_width():\n'
         "                if not getattr(stage_box, '_rte_stage_one_row', False):\n"
         "                    stage_widths['tall'] = stage_box.winfo_reqwidth()\n"
         "                return stage_widths.get('tall', 0)\n"
         '            def stage_one_row(one_row):\n'
         "                if getattr(stage_box, '_rte_stage_one_row', False) is one_row:\n"
         '                    return\n'
         '                stage_box._rte_stage_one_row = one_row\n'
         '                if one_row:\n'
         "                    zero_cell.grid_configure(row=0, column=5, columnspan=1, sticky='ew', padx=(6, 0))\n"
         "                    stage_live.grid_configure(row=0, column=6, columnspan=1, sticky='w', padx=(6, 0))\n"
         '                else:\n'
         "                    zero_cell.grid_configure(row=1, column=0, columnspan=2, sticky='ew', padx=0)\n"
         "                    stage_live.grid_configure(row=1, column=2, columnspan=3, sticky='w', padx=(2, 0))\n"
         '            def arrange_stage_block(_event=None):\n'
     )),
    ('                    block = 16 + stage_box.winfo_reqwidth()\n',
     '                    block = 16 + stage_tall_width()\n'),
    ((
        "                place = 'beside lock-ins' if beside else 'under params' if side else 'under lock-ins'\n"
        "                if getattr(stage_box, '_rte_stage_place', None) == place:\n"
        '                    return\n'
        '                stage_box._rte_stage_place = place\n'
    ),
     (
         "                place = 'beside lock-ins' if beside else 'under params' if side else 'under lock-ins'\n"
         '                try:\n'
         "                    one_row = place == 'under params' and params.winfo_reqwidth() + lockins.winfo_reqwidth() >= stage_tall_width() + zero_cell.winfo_reqwidth() + stage_live.winfo_reqwidth() + 16\n"
         '                except (tk.TclError, ValueError):\n'
         '                    return\n'
         "                if getattr(stage_box, '_rte_stage_place', None) == place and getattr(stage_box, '_rte_stage_one_row', False) is one_row:\n"
         '                    return\n'
         '                stage_box._rte_stage_place = place\n'
         '                stage_one_row(one_row)\n'
     )),
    ("                    stage_box.grid_configure(in_=body, row=1, column=0, columnspan=1, sticky='nw', padx=0, pady=(4, 0))\n",
     "                    stage_box.grid_configure(in_=body, row=1, column=0, columnspan=2 if one_row else 1, sticky='nw', padx=0, pady=(4, 0))\n"),
    ("RTE_ANGLE_DEFAULT_RANGE if angle else SWITCH_LOOP_DEFAULT_RANGE if mode == SWITCH_LOOP_SCAN_MODE else () if switch else RTE_FIELD_DEFAULT_RANGE",
     "RTE_ANGLE_DEFAULT_RANGE if angle else (RTE_MEASUREMENT_START.get(self.__dict__.get('rte_measurement'), {}).get('ranges', {}).get(mode) or SWITCH_LOOP_DEFAULT_RANGE) if mode == SWITCH_LOOP_SCAN_MODE else () if switch else (RTE_MEASUREMENT_START.get(self.__dict__.get('rte_measurement'), {}).get('ranges', {}).get(mode) or RTE_FIELD_DEFAULT_RANGE)"),
    # Settle s and Acquire s of a scan may be the measurement's own (settle_s, acquire_s in RTE_MEASUREMENT_START):
    # the page's two blocks, word for word, are _rte_follow_scan_times above, which also runs when the tab changes
    # and the scan stays.
    ((
        "        acquire = self.__dict__.get('ppms_acquisition_time_var')\n"
        '        if acquire is not None:\n'
        "            shown = self.__dict__.get('rte_acquisition_default_shown')\n"
        "            new = f'{RTE_FIELD_ACQUISITION_S if mode in RTE_FIELD_SWEEP_MODES else SWITCH_ACQUISITION_S if switch else RTE_ACQUISITION_S:g}'\n"
        '            if shown is None or str(acquire.get()).strip() == shown:\n'
        '                acquire.set(new)\n'
        '                self.rte_acquisition_default_shown = new\n'
        "        settle = self.__dict__.get('ppms_field_scan_stable_var')\n"
        "        if settle is not None and 'rte_settle_default_shown' in self.__dict__:\n"
        "            new = f'{SWITCH_SETTLE_S if mode in SWITCH_6221_MODES else RTE_SETTLE_S:g}'\n"
        '            if str(settle.get()).strip() == self.rte_settle_default_shown:\n'
        '                settle.set(new)\n'
        '                self.rte_settle_default_shown = new\n'
    ),
     '        self._rte_follow_scan_times(mode)\n'),
    # How a run is saved (user, 2026-11-28: "standardize the file-saving logic across all parts of the code and ensure
    # that the file and variable naming conventions are consistent"):
    # - one name: the measurement's (the tab's), in the two questions at the start, in a blank name's
    #   <name>_<date>_<time>, in the error windows about the run's files and in Save CSV as;
    # - one writer: the run's recorder (SHHVScanRecorder below) makes the folder and writes the live CSV, the log
    #   and the Switch scans' trace CSV, each under its lock, flushed to the disk, the CSVs as UTF-8 with a BOM;
    # - one rule for file names: <folder>/<stem>/<stem>.csv, <stem>.log and <stem>_<part>.<ext> for the rest
    #   (<stem>_trace.csv, <stem>_plots_snapshot.png, Save CSV as: <stem>_copy.csv).
    # The names of the files and of the CSV's columns and the log's fields are as they were: the analysis scripts
    # read them.
    ("        folder = filedialog.askdirectory(parent=self.root, title=f'{self.ppms_page_name} live CSV folder')\n",
     "        folder = filedialog.askdirectory(parent=self.root, title=f'{self._rte_run_name()}: folder to save the run in')\n"),
    ("        typed = ask_scan_file_stem(self.root, f'{self.ppms_page_name} file name')\n",
     "        typed = ask_scan_file_stem(self.root, f'{self._rte_run_name()}: file name')\n"),
    ("        stem = typed or time.strftime(f'{self.ppms_page_name}_%Y%m%d_%H%M%S')\n",
     '        run_name = self._rte_run_name()\n'),
    ('                recorder = SHHVScanRecorder(Path(folder), stem, self.ppms_page_name)\n',
     '                recorder = SHHVScanRecorder(Path(folder), typed, run_name)\n'),
    ('            self.ppms_live_csv_path, self.ppms_live_csv_fields = path, None\n', ''),
    ((
        "        path = recorder.directory / f'{recorder.csv_path.stem}_trace.csv'\n"
    ),
     "        path = recorder.part_path('trace', 'csv')\n"),
    ((
        '        try:\n'
        '            new = not path.exists()\n'
        "            with path.open('a', newline='', encoding='utf-8') as handle:\n"
        '                writer = csv.writer(handle)\n'
        '                if new:\n'
        '                    writer.writerow(SWITCH_TRACE_COLUMNS)\n'
        '                writer.writerows(lines)\n'
        '            self.rte_switch_trace_path = path\n'
        '        except OSError as error:\n'
    ),
     (
         '        try:\n'
         "            self.rte_switch_trace_path = recorder.append_part_rows('trace', SWITCH_TRACE_COLUMNS, lines)\n"
         '        except (OSError, RuntimeError) as error:\n'
     )),
    ("title=f'Save {self.ppms_page_name} CSV as'",
     "title=f\"{self.ppms_field_scan_rows[0].get('measurement') or self.ppms_page_name}: save CSV as\""),
    ("initialfile=time.strftime(f'{self.ppms_page_name}_%Y%m%d_%H%M%S.csv'),",
     "initialfile=f'{Path(folder).name}_copy.csv' if where else time.strftime(f\"{self.ppms_field_scan_rows[0].get('measurement') or self.ppms_page_name}_%Y%m%d_%H%M%S.csv\"),"),
    ("f'{self.ppms_page_name} CSV export'",
     "f\"{self.ppms_field_scan_rows[0].get('measurement') or self.ppms_page_name}: CSV export\""),
)

MAIN_WINDOW_TITLE = "Transport_RT_NH"
# Its own icon (Other-files/assets): the main program's picture in another colour, with the name on it.
APPLICATION_ICON_BASENAME = "Transport_RT"
# The measurements of this program, in tab order, each with the scans it offers (user, 2026-11-27: "split SHHV
# and Switch to two modes. also add modes named NLH, AHE, PHE. In the order: PHE, AHE, NLH, SHHV, Switch";
# then "rename the switch to switch-OOP": the Switch tab, whose scans keep their names).
# They are tabs of one page: the instruments stay connected when the measurement changes.
RTE_MEASUREMENTS = {
    "PHE": ("Angle+Field", "Angle+Current"),
    "AHE": ("Field", "Field+Angle", "Field+Current"),
    "NLH": ("Current",),
    "SHHV": ("Angle+Field", "Angle+Current"),
    "Switch-OOP": ("Switch", "Switch-loop", "Switch2"),
    "Switch-IP": ("Switch", "Switch-loop", "Switch2"),
}
# The program starts on SHHV: the page's start-up settings (2nd harmonic, Angle+Field) are that measurement's.
RTE_DEFAULT_MEASUREMENT = "SHHV"
# The Scan box on the left and the Settings box on the right (user, same request).
RTE_SCAN_BOX_FIRST = True
# What the Switch-OOP tab starts with (user's figure, 2026-11-27: "default settings use fig in switch mode in RT"):
# Switch-loop from 22 to -22 mA in 2 mA steps and back, at 200 G, 1000 us pulses, a 0.5 mA RMS read current
# and SR830-1 on the 1st harmonic.  Loops 1, Settle s 30, Acquire s 30, Round trip, Pulses 1 and Compliance V
# 100 were the Switch-loop scan's already.  The safety tick stays the user's to make.
# Since 2026-11-28 (user's figure: "default use this settings in RT-Switch-OOP"): Switch-loop from 24 to -24 mA in
# 2 mA, Settle s 10, Acquire s 10 and an outer field of 500 G; Loops 1 and Round trip as before.  These are this
# tab's Switch-loop scan's (ranges, settle_s, acquire_s: per scan; loop_field_g: the Switch-loop Outer field G box),
# by the typed-value rule below.  The request names Switch-OOP, so Switch-IP keeps Settle s 30, Acquire s 30 and
# 200 G, and the Switch and Switch2 scans keep theirs.
# The scan a measurement opens on the first time, and the read current and SR830-1 harmonic shown while it is
# chosen: these two boxes follow the measurement only while they still hold what the program put there, so a
# typed value stays (the rule of Acquire s); the other measurements show 1.5 mA and harmonic 2 as before.
# PHE (user's figure, 2026-11-27: "default setting as the figure for PHE module"): Angle+Field 0 to -360 in 5,
# 0.5 s settle, 5 s acquire, 1.5 mA were the scan's already; its own are one outer field of 200 G (angle_field_g:
# the Angle+Field list box, by the same typed-value rule; SHHV shows the list 200 to 1000 G) and SR830-1 on the
# 1st harmonic.
# Switch-IP (user, 2026-11-27: "add a Switch-IP module which use 14mA to -14mA step 2mA as default and SR830-1
# use harmonic 2 pls. pulse width default 30us. the other settings are the same as Switch-OOP"): the tab after
# Switch-OOP, with its scans, Switch-loop, 200 G and 0.5 mA; its own are the loop 14 to -14 mA in 2 mA
# (ranges: what a scan's Start, End, Step show in this tab), 30 us pulses (pulse_width_us: the one
# Pulse us box, 1000 in the other tabs) and SR830-1 on the 2nd harmonic.  Typed values stay, as above.
# AHE (user's figure, 2026-11-27: "default setting as the figure for AHE module"): the Field scan from -3 to
# 3 A in 0.1 A and back, a 0.5 mA RMS read current, SR830-1 on the 1st harmonic; Settle s 0.5, Acquire s 2 and
# Round trip were the Field scan's already.  The figure shows the Field scan, so Field+Angle and Field+Current
# keep the -1 to 1 A in 0.02 A of 2026-11-22.
RTE_MEASUREMENT_START = {
    "PHE": dict(scan="Angle+Field", harmonic_a="1", angle_field_g="200"),
    "AHE": dict(scan="Field", current_ma="0.5", harmonic_a="1", ranges={"Field": ("-3", "3", "0.1")}),
    "Switch-OOP": dict(scan="Switch-loop", current_ma="0.5", harmonic_a="1", ranges={"Switch-loop": ("24", "-24", "2")},
                       settle_s={"Switch-loop": "10"}, acquire_s={"Switch-loop": "10"}, loop_field_g="500"),
    "Switch-IP": dict(scan="Switch-loop", current_ma="0.5", harmonic_a="2", ranges={"Switch-loop": ("14", "-14", "2")}, pulse_width_us="30"),
}
SWITCH_LOOP_DEFAULT_RANGE = ("22", "-22", "2")
SWITCH_LOOP_DEFAULT_FIELDS_G = "200"
# The live lines' width, in characters, beside the instrument rows of a wide window (32 beside the rack, where a
# long line wraps): "Field 1/1 +200 G, step 6: I -1.136 A, B +198.667 G" on one line.
RTE_LIVE_WIDE_CHARS = 48
# The Pulse us box is one box for the Switch scans and Apply pulse, on every tab.
SWITCH_DEFAULT_PULSE_WIDTH_US = 1000.0


class SHHVScanRecorder(ScanRunRecorder):
    # A run of this program: <parent>/<stem>/ with <stem>.csv and <stem>.log (the package's recorder), and every
    # other file of the run as <stem>_<part>.<extension>.  A blank name is <page>_<date>_<time>.
    def __init__(self, parent: Path, stem: str, page: str = "SHHV") -> None:
        super().__init__(parent, page, stem)

    @property
    def stem(self) -> str:
        return self.directory.name

    def part_path(self, part: str, extension: str) -> Path:
        return self.directory / f"{self.stem}_{part}.{extension}"

    def append_part_rows(self, part: str, header, rows) -> Path:
        # Rows onto <stem>_<part>.csv, as append_row writes the live CSV: under the lock, UTF-8 with a BOM, flushed
        # and synced before it returns; the header when the file is new.
        with self.lock:
            if self.closed:
                raise RuntimeError(f"The {self.label} run is closed")
            path = self.part_path(part, "csv")
            new = not path.exists()
            with path.open("a", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                if new:
                    writer.writerow(header)
                writer.writerows(rows)
                self._sync(handle)
            return path


class CombinedControlApp:
    def build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self._configure_ui_styles()
        notebook_pad = self._ui_px(3, 2)
        self.notebook = ttk.Notebook(self.root, padding=(notebook_pad, notebook_pad, notebook_pad, 0))
        self.notebook.grid(row=0, column=0, sticky="nsew")
        # One page for every measurement: its tab is the chosen measurement's, the other measurements' tabs are
        # empty frames, and choosing one of them moves the page there (_rte_measurement_tab_changed).
        self.rte_panel_tab = ttk.Frame(self.notebook)
        self.rte_measurement_spare_tabs = []
        for name in RTE_MEASUREMENTS:
            if name == RTE_DEFAULT_MEASUREMENT:
                self.notebook.add(self.rte_panel_tab, text=name)
            else:
                self.rte_measurement_spare_tabs.append(ttk.Frame(self.notebook))
                self.notebook.add(self.rte_measurement_spare_tabs[-1], text=name)
        self.log_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.log_tab, text="Log")
        self.log_tab.rowconfigure(0, weight=1)
        self.log_tab.columnconfigure(0, weight=1)
        self.rte_panel = RTEPanel(self, self.rte_panel_tab)
        self.notebook.select(self.rte_panel_tab)
        self.notebook.bind("<<NotebookTabChanged>>", self._rte_measurement_tab_changed, add="+")
        self.led_log_frame = ttk.LabelFrame(self.log_tab, text="Program communication log", padding=5)
        self.led_log_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.led_log_frame.rowconfigure(0, weight=1)
        self.led_log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(self.led_log_frame, height=5, wrap="none", state="disabled", font=(self.mono_font_family, self.ui_small_font_size), background="#fbfcfd", relief="flat", padx=5, pady=4)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.led_log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        xscrollbar = ttk.Scrollbar(self.led_log_frame, orient="horizontal", command=self.log_text.xview)
        xscrollbar.grid(row=1, column=0, sticky="ew")
        self.log_text.configure(yscrollcommand=scrollbar.set, xscrollcommand=xscrollbar.set)
        self.log_display_paused = False
        self.log_pending_lines = []
        log_tools = ttk.Frame(self.led_log_frame)
        log_tools.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.log_pause_button = ttk.Button(log_tools, text="Pause refresh", command=self.toggle_log_refresh)
        self.log_pause_button.pack(side="left")
        ttk.Button(log_tools, text="Copy shown log", command=self.copy_displayed_log).pack(side="left", padx=5)
        ttk.Button(log_tools, text="Save full log", command=self.save_communication_log).pack(side="left")
        ttk.Label(log_tools, text="Pausing only freezes the display; logging continues and catches up on resume.").pack(side="left", padx=8)

    def _rte_measurement_tab_changed(self, _event=None) -> None:
        try:
            shown = self.notebook.nametowidget(self.notebook.select())
        except (tk.TclError, KeyError):
            return
        if shown not in self.rte_measurement_spare_tabs:
            return
        names = tuple(RTE_MEASUREMENTS)
        wanted = self.notebook.index(shown)
        held = self.notebook.index(self.rte_panel_tab)
        if wanted >= len(names):
            return
        if self.rte_panel.rte_set_measurement(names[wanted]):
            # The page takes the chosen tab's place and the empty frame the page's old place.
            self.notebook.insert(wanted, self.rte_panel_tab)
            self.notebook.insert(held, shown)
            for index, name in enumerate(names):
                self.notebook.tab(index, text=name)
            self.append_log(f"Measurement: {names[wanted]} (scans: {', '.join(RTE_MEASUREMENTS[names[wanted]])})")
        else:
            self.rte_panel._rte_dialog(
                "Measurement", f"The measurement stays {names[held]} while a scan runs or the page is busy. "
                f"Stop the scan, or wait, then choose {names[wanted]}.", show=messagebox.showinfo)
        self.notebook.select(self.rte_panel_tab)

    def _redraw_active_tab(self) -> None:
        # The main program redraws other pages' plots here, never this page's.
        return

    def safe_close_hardware(self) -> None:
        try:
            self.safe_close_ppms()
        except BaseException as error:
            try:
                self.append_log(f"SHHV safe close incomplete: {error}")
            except BaseException:
                pass

    def request_close(self) -> None:
        if self.closing:
            return
        confirmed = messagebox.askyesno(
            "Close the SHHV & Switch program",
            "Exit the SHHV & Switch control program?\n\n"
            "The program will stop a running scan and the stage, switch the 6221 (and the Avtech) off, zero the "
            "magnet supply and disconnect the instruments. The stage stays where it is.\n\n"
            "After exiting, still confirm every instrument output and power supply is in a safe state.",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return
        self.closing = True
        panel = self.__dict__.get("rte_panel")
        for owner in (self, panel):
            if owner is None:
                continue
            for name in ("ppms_field_scan_stop_event", "rte_stage_stop_event"):
                event = owner.__dict__.get(name)
                if event is not None:
                    event.set()

        def finish_window_close() -> None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

        def close_everything() -> None:
            try:
                self.safe_close_hardware()
            finally:
                self.file_executor.shutdown(wait=False, cancel_futures=False)
                self.executor.shutdown(wait=False, cancel_futures=True)
                self.post_ui(finish_window_close)
        threading.Thread(target=close_everything, name="rt-safe-shutdown", daemon=True).start()


def run() -> None:
    """The installed command (pyproject.toml: transport-rt)."""
    main()


def main() -> None:
    root = tk.Tk()
    app = CombinedControlApp(root)
    root.after_idle(lambda: maximize_main_window(root))
    try:
        root.mainloop()
    finally:
        app.safe_close_hardware()
        app.executor.shutdown(wait=False, cancel_futures=True)
