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
         "        own, cells = start.get('states') or (), [('states_count', state.get('rte_states_count'), str(len(SWITCH_DEFAULT_STATES)), str(len(start.get('states') or SWITCH_DEFAULT_STATES)))]\n"
         "        for index, variables in enumerate(state.get('rte_state_vars') or ()):\n"
         "            base = SWITCH_DEFAULT_STATES[index] if index < len(SWITCH_DEFAULT_STATES) else ('',) * len(variables)\n"
         "            new = own[index] if index < len(own) else (*base[:3], str(start.get('pulse_width_us', base[3]))) if base[3] and not own else base\n"
         "            cells += [(f'state_{index + 1}_{column}', variable, base[column], str(new[column])) for column, variable in enumerate(variables)]\n"
         '        for key, variable, base, new in cells:\n'
         '            was = shown.get(key, base)\n'
         '            if variable is not None and new != was and str(variable.get()).strip() == was:\n'
         '                variable.set(new)\n'
         '                shown[key] = new\n'
         '        self._rte_show_state_rows()\n'
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
         '        if mode == SWITCH_SCAN_MODE:\n'
         '            return f"{SWITCH_STATES_ACQUIRE_S if key == \'acquire_s\' else SWITCH_STATES_SETTLE_S:g}"\n'
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
    # The Switch scan runs states (user, 2026-11-28: "change the switch scan mode to set the state 1, 2, 3, 4... like
    # MS_four state? the each state can contain settings like stage angle, field, pulse mA, pulse us, the readout
    # current remains the value in the setting"; then chosen from three questions: a table with one row a state,
    # every state read at 0 G as MS-fourState reads, the states in their order times Cycles).
    # - The Scan box shows a table in place of "Pulses mA", "Outer field G" and the Pulse us box: States (how many
    #   rows), and Angle, Field G, Pulse mA, Pulse us for each state.
    # - One state: the read current off; the stage to the state's angle (at the read field, 0 G); the field to the
    #   state's; the pulse; the field back to 0 G; the read current on again, the settling and the read.  The read
    #   current, its frequency, the compliance and the number of pulses a write are the Settings boxes', as before.
    # - The pulse is logged when it is sent, before the field goes back (review, 2026-11-28: a Stop or a failure on
    #   the way back must not leave a delivered pulse out of the run log); the row's event is "state_written".  A
    #   state's field is held to the +/-7300 G of the page's typed fields, and Stop stage also holds the next pulse.
    # - The Angle boxes are filled for every state or for none: with none the stage is not moved and need not be
    #   connected, as in the Switch scan before.
    # - In the scan's own terms the read field is its one "outer" field, so the start, the end and the files of a
    #   Switch scan are the page's as they were.  Switch-loop and Switch2 are not changed.
    ("        self.rte_edit_widgets.append((pulses, 'normal'))\n",
     "        self.rte_edit_widgets.append((pulses, 'normal'))\n        self._rte_build_states_table(scan, scan_rows)\n"),
    ('        self._rte_show_avtech_row()\n        if not self.ppms_field_scan_rows:\n',
     '        self._rte_show_avtech_row()\n        self._rte_show_states(mode)\n        if not self.ppms_field_scan_rows:\n'),
    ("            note.set(RTE_SCAN_NOTES.get(mode, RTE_SCAN_NOTES['Current']).replace('KEPCO', name))\n",
     "            note.set(RTE_SCAN_NOTES.get(mode, RTE_SCAN_NOTES['Current']).replace('KEPCO', name))\n        self._rte_hide_state_parts()\n"),
    ('                    for widget, options in zip(pulse_widgets, pulse_beside if pulse else self.rte_pulse_under_options):\n                        widget.grid_configure(**options)\n',
     '                    for widget, options in zip(pulse_widgets, pulse_beside if pulse else self.rte_pulse_under_options):\n                        widget.grid_configure(**options)\n                    self._rte_hide_state_parts()\n'),
    ("    SWITCH_SCAN_MODE: 'Switch: 6221 pulse mA; outer: field G',\n",
     "    SWITCH_SCAN_MODE: 'Switch: states x Cycles; read at 0 G',\n"),
    ('            turns = mode in RTE_STAGE_MODES\n',
     "            turns = mode in RTE_STAGE_MODES or (mode == SWITCH_SCAN_MODE and self._rte_switch_states_typed()[0]['angle_deg'] is not None)\n"),
    ('else rte_pulse_list(self.rte_switch_pulses_var.get()) if mode == SWITCH_SCAN_MODE else None)\n',
     "else tuple(state['pulse_ma'] for state in self._rte_switch_states_typed()) if mode == SWITCH_SCAN_MODE else None)\n"),
    ('                                 self.ppms_field_scan_loop_var.get(), self.rte_round_trip.get(),\n',
     '                                 self.ppms_field_scan_loop_var.get(), self.rte_round_trip.get() and mode != SWITCH_SCAN_MODE,\n'),
    ("                kind = 'a Field+Angle scan' if field_angle else 'an angle scan'\n",
     "                kind = 'a Field+Angle scan' if field_angle else 'the angles of the states (or empty every Angle ° box: the stage is then not moved)' if switch else 'an angle scan'\n"),
    ('                outer = rte_outer_list_plan(self.rte_outer_ranges[mode][0].get())\n                for value in outer:\n',
     '                outer = (SWITCH_STATE_READ_FIELD_G,) if mode == SWITCH_SCAN_MODE else rte_outer_list_plan(self.rte_outer_ranges[mode][0].get())\n                for value in outer:\n'),
    ('self._rte_switch_pulse_settings(plan, settings) if switch else None\n',
     '(self._rte_states_pulse_settings(settings) if mode == SWITCH_SCAN_MODE else self._rte_switch_pulse_settings(plan, settings)) if switch else None\n'),
    ('        if outer and angle:\n            angles = [target for _loop, _point, target in plan] * (len(outer) * len(passes))\n',
     "        if switch and pulse.get('states'):\n            least_s += self._rte_states_least_extra_s(pulse, plan, passes)\n        if outer and angle:\n            angles = [target for _loop, _point, target in plan] * (len(outer) * len(passes))\n"),
    ("                    order='read current off, pulse, read current on again, settle, read',\n                    read_settle_s=switch_settle_s, read_settle_time_constants=SWITCH_READ_SETTLE_TAUS)\n",
     "                    order='read current off, pulse, read current on again, settle, read',\n                    read_settle_s=switch_settle_s, read_settle_time_constants=SWITCH_READ_SETTLE_TAUS)\n                if pulse.get('states'):\n                    self._rte_states_run_settings(run_settings, pulse)\n"),
    ("            self.ppms_plot_x_range = (min((p[2] for p in plan)), max((p[2] for p in plan))) if switch or mode == 'Current' else None\n",
     "            self.rte_plot_states = len(pulse['states']) if switch and pulse.get('states') else 0\n            self.ppms_plot_x_range = (0.5, self.rte_plot_states * plan[-1][0] + 0.5) if self.rte_plot_states else (min((p[2] for p in plan)), max((p[2] for p in plan))) if switch or mode == 'Current' else None\n"),
    ("            elif switch:\n                self.ppms_field_scan_status_var.set(f'{self.ppms_page_name} {mode}: {len(outer)} fields x {len(plan)} pulses; {self.ppms_field_scan_total} points')\n",
     "            elif switch and pulse.get('states'):\n                self.rte_stage_where = 'stage not moved'\n                self.ppms_field_scan_status_var.set(f\"{self.ppms_page_name} {mode}: {len(pulse['states'])} states x {len(plan) // len(pulse['states'])} cycle(s); {self.ppms_field_scan_total} points\")\n            elif switch:\n                self.ppms_field_scan_status_var.set(f'{self.ppms_page_name} {mode}: {len(outer)} fields x {len(plan)} pulses; {self.ppms_field_scan_total} points')\n"),
    ("                               if outer and angle else\n                               f'; fields as typed: {rte_outer_values_text(outer, 50)} (± '\n",
     "                               if outer and angle else\n                               self._rte_states_log_text(pulse, plan, settings) if switch and pulse.get('states') else\n                               f'; fields as typed: {rte_outer_values_text(outer, 50)} (± '\n"),
    ("        if pulse.get('source') == 'Avtech':\n            return self._rte_switch2_question(plan, outer, passes, limit, pulse, settings, settle_text, least_text, ramp_text)\n",
     "        if pulse.get('states'):\n            return self._rte_states_question(plan, passes, limit, pulse, settings, settle_text, least_text, ramp_text)\n        if pulse.get('source') == 'Avtech':\n            return self._rte_switch2_question(plan, outer, passes, limit, pulse, settings, settle_text, least_text, ramp_text)\n"),
    ("                    self._rte_log('pulse', index=progress, step_index=step_index, loop=loop, point=point, **pulse_columns)\n",
     "                    self._rte_log('state_written' if pulse.get('states') else 'pulse', index=progress, step_index=step_index, loop=loop, point=point, **pulse_columns)\n"),
    ('                    pulse_columns = self._rte_avtech_pulse(target, pulse) if avtech else self._rte_switch_pulse(target, pulse)\n',
     (
         "                    if pulse.get('states'):\n"
         '                        try:\n'
         '                            pulse_columns = self._rte_state_write(supply, limit, pulse, loop, point, progress)\n'
         '                        except PPMSScanCancelled:\n'
         '                            raise\n'
         '                        except Exception as state_error:\n'
         "                            stage_failure, field_failure = (getattr(state_error, 'rte_state_part', '') == part for part in ('stage', 'field'))\n"
         '                            raise\n'
         '                    else:\n'
         '                        pulse_columns = self._rte_avtech_pulse(target, pulse) if avtech else self._rte_switch_pulse(target, pulse)\n'
     )),
    ("'pulse_amplitude_v' if avtech else 'pulse_current_ma' if switch else '6221_current_rms_ma'\n",
     "'pulse_amplitude_v' if avtech else 'state' if switch and pulse.get('states') else 'pulse_current_ma' if switch else '6221_current_rms_ma'\n"),
    ("                          'pulse': ('pulse_current_ma', '6221 pulse current (mA)'),\n",
     "                          'pulse': ('pulse_current_ma', '6221 pulse current (mA)'),\n                          'state': ('state', 'State'),\n"),
    # The Switch scan's cycles side by side (user's figure of two cycles drawn over each other, 2026-11-28: "for
    # switch cycle, the first row should have 1,2,3,4,5,6,1,2,3,4,5,6... this type x-axis"): a point is drawn at
    # (cycle - 1) x states + state, all cycles are one line, and the axis is labelled with the states' numbers.
    ("            x_value = row.get(x_key)\n            if isinstance(x_value, (float, int)):\n                step = rte_outer_step_of(row)\n                tail = f\"P{row.get('harmonic_pass', 1)} L{row['loop']}\"\n",
     "            x_value = row.get(x_key)\n            if isinstance(x_value, (float, int)):\n                step = rte_outer_step_of(row)\n                x_value, tail = (x_value + (row['loop'] - 1) * cycle, f\"P{row.get('harmonic_pass', 1)}\") if cycle else (x_value, f\"P{row.get('harmonic_pass', 1)} L{row['loop']}\")\n"),
    ("        prepared = []\n        for row in self.ppms_field_scan_rows:\n            x_value = row.get(x_key)\n            if isinstance(x_value, (float, int)):\n                step = rte_outer_step_of(row)\n",
     "        prepared, cycle = [], self.__dict__.get('rte_plot_states', 0) if axis == 'state' else 0\n        for row in self.ppms_field_scan_rows:\n            x_value = row.get(x_key)\n            if isinstance(x_value, (float, int)):\n                step = rte_outer_step_of(row)\n"),
    ("                    x_range=None if axis == 'angle' else (self.__dict__.get('ppms_plot_x_range') if axis != 'field' else None) or (math.inf, -math.inf),\n",
     "                    x_range=None if axis == 'angle' else (self.__dict__.get('ppms_plot_x_range') if axis != 'field' else None) or (math.inf, -math.inf),\n                    **({'x_cycle': cycle} if cycle else {}),\n"),
    ("        angle_x_range=None,\n        x_range=None,\n    ) -> None:\n",
     "        angle_x_range=None,\n        x_range=None,\n        x_cycle=None,\n    ) -> None:\n"),
    ("        for tick_index, x_value in enumerate(x_ticks):\n            x = left + (x_value - x_min) / (x_max - x_min) * plot_width\n            canvas.create_line(x, top + plot_height, x, top + plot_height + 4)\n            if not hide_x_labels:\n",
     "        cycle_ticks = rte_state_cycle_ticks(x_cycle, x_min, x_max, plot_width) if x_cycle else None\n        for tick_index, x_value in enumerate(x_ticks if cycle_ticks is None else [tick[0] for tick in cycle_ticks]):\n            x = left + (x_value - x_min) / (x_max - x_min) * plot_width\n            canvas.create_line(x, top + plot_height, x, top + plot_height + 4)\n            if cycle_ticks is not None:\n                if cycle_ticks[tick_index][1] and not hide_x_labels:\n                    canvas.create_text(x, top + plot_height + 15, text=cycle_ticks[tick_index][1])\n                continue\n            if not hide_x_labels:\n"),
    ("        pulse_axis = axis in ('pulse', 'avtech')\n",
     "        pulse_axis = axis in ('pulse', 'avtech', 'state')\n"),
    ("        return self.__dict__.get('ppms_plot_axis') in ('pulse', 'avtech')\n",
     "        return self.__dict__.get('ppms_plot_axis') in ('pulse', 'avtech', 'state')\n"),
    # The table goes beside the scan's rows where the Scan box is wide enough (it then costs the plots little height),
    # and in the first row, beside the scan list, where it is not; beside, the pulse row and the note stay under.
    # (The scan rows' width is counted without the table, then with it in the first row: the Scan box asks for the
    # second, and the table goes beside the rows when the box is at least the first plus the table.)
    ('                    if (not outer_row and str(widget) in under) or widget is note_label:\n',
     "                    if (not outer_row and str(widget) in under) or widget is note_label or widget is self.__dict__.get('rte_states_frame'):\n"),
    ('                if outer_row:\n                    self.rte_scan_rows_columns = widths\n                return sum(widths)\n',
     '                base = sum(widths)\n                widths[6] += max(0, self._rte_states_under_px() - sum(widths[1:]))\n                if outer_row:\n                    self.rte_scan_rows_columns, self.rte_scan_rows_base = widths, base\n                return sum(widths)\n'),
    ("                    pulse = stacked and room > 1 and self.rte_outer_place == 'under' and room >= rows_width + pulse_need\n",
     "                    pulse = stacked and room > 1 and self.rte_outer_place == 'under' and room >= rows_width + pulse_need + self._rte_states_beside_px()\n"),
    ('                    note = room > 1 and room >= rows_width + note_label.winfo_reqwidth() + 14\n',
     '                    note = room > 1 and room >= rows_width + note_label.winfo_reqwidth() + 14 + self._rte_states_beside_px()\n'),
    ('    def _rte_mode_changed(self, _event=None):\n', r"""    def _rte_build_states_table(self, scan, scan_rows):
        self.rte_states_count = tk.StringVar(value=str(len(SWITCH_DEFAULT_STATES)))
        self.rte_state_vars = [tuple(tk.StringVar(value=text) for text in (SWITCH_DEFAULT_STATES[index] if index < len(SWITCH_DEFAULT_STATES) else ('',) * len(SWITCH_STATE_COLUMNS))) for index in range(SWITCH_STATES_MAX)]
        frame = ttk.Frame(scan_rows)
        head = ttk.Frame(frame)
        head.grid(row=0, column=0, sticky='w')
        ttk.Label(head, text='States').grid(row=0, column=0)
        count = ttk.Entry(head, textvariable=self.rte_states_count, width=3)
        count.grid(row=0, column=1, padx=(3, 6))
        self.rte_edit_widgets.append((count, 'normal'))
        for column, title in enumerate(SWITCH_STATE_COLUMNS, 1):
            ttk.Label(frame, text=title).grid(row=0, column=column, padx=2)
        self.rte_state_rows = []
        for number, variables in enumerate(self.rte_state_vars, 1):
            widgets = [ttk.Label(frame, text=str(number))]
            widgets[0].grid(row=number, column=0, sticky='e', padx=(0, 6))
            for column, variable in enumerate(variables, 1):
                entry = ttk.Entry(frame, textvariable=variable, width=6)
                entry.grid(row=number, column=column, padx=2, pady=1)
                self.rte_edit_widgets.append((entry, 'normal'))
                widgets.append(entry)
            self.rte_state_rows.append(widgets)
        self.rte_states_under = dict(row=0, column=1, columnspan=RTE_SCAN_ROWS_LAST_COLUMN, rowspan=1, sticky='w', padx=(4, 2))
        self.rte_states_beside = dict(row=0, column=7, columnspan=RTE_SCAN_ROWS_LAST_COLUMN - 6, rowspan=5, sticky='nw', padx=(16, 2))
        frame.grid(**self.rte_states_under)
        frame.grid_remove()
        self.rte_states_frame, self.rte_states_scan_box, self.rte_states_place = frame, scan, 'under'
        for widget in (scan, scan_rows):
            widget.bind('<Configure>', self._rte_arrange_states, add='+')
        for event in ('<KeyRelease>', '<FocusOut>'):
            count.bind(event, lambda _event: self._rte_show_state_rows(), add='+')
        self._rte_show_state_rows()
    def _rte_show_state_rows(self):
        rows = self.__dict__.get('rte_state_rows') or ()
        try:
            count = int(str(self.rte_states_count.get()).strip())
        except (ValueError, tk.TclError):
            return
        if not 1 <= count <= len(rows):
            return
        for number, widgets in enumerate(rows, 1):
            for widget in widgets:
                if number <= count:
                    widget.grid()
                else:
                    widget.grid_remove()
    def _rte_show_states(self, mode):
        frame = self.__dict__.get('rte_states_frame')
        if frame is None:
            return
        if mode == SWITCH_SCAN_MODE:
            frame.grid()
        else:
            frame.grid_remove()
        combo = self.__dict__.get('rte_scan_mode_combo')
        if combo is not None:
            combo.grid(row=0, column=0, sticky='n' if mode == SWITCH_SCAN_MODE else '')
        self._rte_hide_state_parts()
        self._rte_arrange_states()
    def _rte_states_under_px(self) -> int:
        frame = self.__dict__.get('rte_states_frame')
        try:
            return frame.winfo_reqwidth() + 6 if frame is not None and frame.winfo_manager() == 'grid' else 0
        except (tk.TclError, AttributeError):
            return 0
    def _rte_states_beside_px(self) -> int:
        return 10 ** 6 if self.__dict__.get('rte_states_place') == 'beside' and self._rte_states_under_px() else 0
    def _rte_arrange_states(self, _event=None):
        state = self.__dict__
        frame, scan = state.get('rte_states_frame'), state.get('rte_states_scan_box')
        try:
            if frame is None or scan is None or frame.winfo_manager() != 'grid':
                return
            room, rows_width = scan.winfo_width() - self._pair_inset(scan), state.get('rte_scan_rows_base') or 0
            place = 'beside' if room > 1 and rows_width > 0 and room >= rows_width + frame.winfo_reqwidth() + 22 else 'under'
            if state.get('rte_states_place') == place:
                return
            guard, window_width = state.setdefault('rte_states_guard', {}), scan.winfo_toplevel().winfo_width()
            if guard.get('window') != window_width:
                guard.update(window=window_width, flips=0)
            guard['flips'] += 1
            if guard['flips'] > PAIR_FLIP_LIMIT:
                if state.get('rte_states_place') == 'under':
                    return
                place = 'under'
            self.rte_states_place = place
            frame.grid_configure(**(self.rte_states_beside if place == 'beside' else self.rte_states_under))
            arrange = state.get('rte_arrange_beside_rows')
            if arrange is not None:
                self.root.after_idle(arrange)
        except (tk.TclError, ValueError, AttributeError, TypeError):
            return
    def _rte_hide_state_parts(self):
        mode = self.__dict__.get('ppms_simple_mode')
        if 'rte_states_frame' not in self.__dict__ or mode is None or mode.get() != SWITCH_SCAN_MODE:
            return
        for widget in (*(self.__dict__.get('rte_switch_pulse_list_widgets') or ()), *(widget for widget, _options in self.__dict__.get('rte_outer_list_widgets') or ()), *(self.__dict__.get('rte_pulse_widgets') or ())[1:3]):
            widget.grid_remove()
    def _rte_switch_states_typed(self):
        return rte_switch_states([[variable.get() for variable in row] for row in self.__dict__.get('rte_state_vars') or ()], self.rte_states_count.get())
    def _rte_states_pulse_settings(self, settings):
        states = [dict(state) for state in self._rte_switch_states_typed()]
        supply, compliance_v, checked = self._rte_supply(), float(settings['compliance_v']), None
        for state in states:
            try:
                checked = Keithley6221Controller._validate(state['pulse_ma'] * 1e-3, state['width_s'], compliance_v, self.rte_pulse_count.get())
                self._field_setting_inputs(state['field_g'], self.rte_field_tolerance.get(), supply)
            except ValueError as error:
                raise ValueError(f"State {state['state']}: {error}") from None
            state['width_s'] = checked[1]
        return dict(width_s=sum(state['width_s'] for state in states) / len(states), compliance_v=checked[2], count=checked[3], states=tuple(states))
    def _rte_states_least_extra_s(self, pulse, plan, passes):
        states = pulse['states']
        repeats = len(plan) // len(states) * len(passes)
        angles = [state['angle_deg'] for state in states if state['angle_deg'] is not None] * repeats
        fields = 2 * sum(state['field_g'] != SWITCH_STATE_READ_FIELD_G for state in states) * repeats
        return sum(abs(b - a) for a, b in zip(angles, angles[1:])) / NEWMARK_SPEED_DEG_S + fields * STFMR_FIELD_SETTLE_REQUIRED_SAMPLES * RTE_FIELD_SETTLE_POLL_S
    @staticmethod
    def _rte_state_text(state):
        return (f"{state['state']}: " + ('' if state['angle_deg'] is None else f"stage {state['angle_deg']:g}°, ")
                + f"{state['field_g']:+g} G, {state['pulse_ma']:+g} mA, {state['width_s'] * 1e6:g} µs")
    def _rte_states_log_text(self, pulse, plan, settings):
        states = pulse['states']
        return (f'; {len(states)} states x {len(plan) // len(states)} cycle(s), each write {pulse["count"]} pulse(s): '
                + '; '.join(self._rte_state_text(state) for state in states)
                + f'; each state read at {SWITCH_STATE_READ_FIELD_G:g} G (± {self.rte_scan_field_tolerance_g:g} G) with {settings["current_rms_ma"]:g} mA RMS')
    def _rte_states_run_settings(self, run_settings, pulse):
        states = [dict(state=state['state'], stage_angle_deg=state['angle_deg'], field_g=state['field_g'], pulse_current_ma=state['pulse_ma'], pulse_width_s=state['width_s']) for state in pulse['states']]
        run_settings['plan'] = dict(run_settings['plan'], typed='the states (pulse.states), in their order', unit='state')
        run_settings['outer'] = dict(unit='G (LS475 target)', tolerance_g=self.__dict__.get('rte_scan_field_tolerance_g'), steps=1, values=[SWITCH_STATE_READ_FIELD_G],
                                     order='the field every state is read at: each state leaves it for its own field and comes back to it')
        run_settings['pulse'] = dict(run_settings['pulse'], width_s='per state (pulse.states)', states=states, read_field_g=SWITCH_STATE_READ_FIELD_G,
                                     order="read current off, stage to the state's angle at the read field, field to the state's, pulse, field back to the read field, read current on again, settle, read")
    def _rte_states_question(self, plan, passes, limit, pulse, settings, settle_text, least_text, ramp_text=''):
        states, name, terms = pulse['states'], self._rte_supply_label(), self._rte_magnet_terms(limit)
        tolerance = self.__dict__.get('rte_scan_field_tolerance_g', MAGNET_FIELD_SET_DEFAULT_TOLERANCE_G)
        cycles, turns = len(plan) // len(states), states[0]['angle_deg'] is not None
        largest = max(states, key=lambda state: abs(state['pulse_ma']))
        start = "the KEPCO's output is switched on at 0 A first if it is off" if name == 'KEPCO' else f'each change is a ramp at the rate, and the {name} must be at its setpoint at Start'
        passes_text = f' Each of the {len(passes)} harmonic passes runs the whole scan, its pulses again.' if len(passes) > 1 else ''
        stage = (f'The Newmark stage turns the SAMPLE HOLDER with its wires attached, at {NEWMARK_SPEED_DEG_S:g}°/s, to each state\'s angle '
                 f'counted from the stage zero (absolute moves, all within ±{NEWMARK_CABLE_LIMIT_DEG:g}° of it), always at '
                 f'{SWITCH_STATE_READ_FIELD_G:g} G with the read current off. Can the wires follow? It stays where the scan left it.'
                 if turns else 'The stage is not moved: no state has an angle.')
        return (f'{self.ppms_simple_mode.get()} scan: {len(states)} states in their order, {cycles} cycle(s).\n\n'
                + '\n'.join(self._rte_state_text(state) for state in states) + '\n\n'
                'Each state: the read current off; ' + ("the stage to the state's angle; " if turns else '')
                + f'the field to the state\'s; one write of {pulse["count"]} pulse(s) at the state\'s current and width (compliance '
                f'{pulse["compliance_v"]:g} V; 0 mA sends no pulse); the field back to {SWITCH_STATE_READ_FIELD_G:g} G; then the read current on '
                f'again, {settings["current_rms_ma"]:g} mA RMS at {settings["frequency_hz"]:g} Hz, {settle_text} of settling, and the lock-ins read.\n\n'
                f'Each field, {SWITCH_STATE_READ_FIELD_G:g} G too, is found within ±{tolerance:g} G on the LS475 as Set field finds it ({terms}; {start}), '
                f'never beyond ±{self._rte_supply().max_current_a():g} A, and is not corrected while it is held.\n\n'
                f'{len(states)} states x {cycles} cycle(s) x {len(passes)} harmonic pass(es) = {len(plan) * len(passes)} points.{passes_text} '
                f'Largest pulse {abs(largest["pulse_ma"]):g} mA ({largest["width_s"] * 1e6:g} µs). The scan takes at least {least_text}; '
                f'finding each field takes longer than is counted.{ramp_text}\n\n'
                'The pulse has not been checked on an oscilloscope by this program: check its height and width '
                'on yours before trusting a new setting.\n\n'
                f'When the scan ends (completed, stopped or failed) the 6221 and then the {name} are zeroed. {stage}\n\nStart the scan?')
    def _rte_state_field(self, supply, target_g, limit, progress, state, count, purpose):
        try:
            self._rte_wait(0)
            reached = self._rte_scan_reach_field(supply, target_g, limit, state['state'], count)
        except PPMSScanCancelled:
            raise
        except Exception as error:
            error.rte_state_part = 'field'
            raise
        self._rte_log('field_programmed', index=progress, state=state['state'], purpose=purpose, target_field_g=target_g,
                      tolerance_g=self.rte_scan_field_tolerance_g, current_a=float(reached['current_a']), field_g=float(reached['field_g']),
                      corrections=reached.get('step'), g_per_a=reached.get('g_per_a'), voltage_limit_v=limit,
                      **self._rte_magnet_log(supply, supply.lakeshore_controller.reading if supply.lakeshore else None))
        self._rte_log_check()
        return reached
    def _rte_state_write(self, supply, limit, pulse, loop, point, progress):
        states = pulse['states']
        state = states[point - 1]
        self._rte_wait(0)
        self._rte_zero_6221_after_scan()
        columns = dict(state=state['state'], write_target_field_g=state['field_g'], write_field_g='', write_current_a='')
        if state['angle_deg'] is not None:
            if self.rte_stage_stop_event.is_set():
                raise PPMSScanCancelled(f"{self.ppms_page_name} stopped: Stop stage was pressed; {self.rte_stage_where or 'stage not moved'}")
            try:
                moved = self._rte_scan_move_stage(state['angle_deg'])
            except PPMSScanCancelled:
                raise
            except Exception as error:
                error.rte_state_part = 'stage'
                raise
            self._rte_log('stage_move', index=progress, state=state['state'], target_deg=state['angle_deg'], angle_deg=moved['angle_deg'], px=moved['px'], steps_per_degree=moved['steps_per_degree'])
            self._rte_log_check()
            columns.update(stage_target_deg=state['angle_deg'], stage_angle_deg=moved['angle_deg'], stage_position_steps=moved['px'], stage_steps_per_degree=moved['steps_per_degree'])
        away = state['field_g'] != SWITCH_STATE_READ_FIELD_G
        if away:
            reached = self._rte_state_field(supply, state['field_g'], limit, progress, state, len(states), 'write')
            columns.update(write_field_g=float(reached['field_g']), write_current_a=float(reached['current_a']))
        if state['angle_deg'] is not None and self.rte_stage_stop_event.is_set():
            raise PPMSScanCancelled(f"{self.ppms_page_name} stopped before the pulse of state {state['state']}: Stop stage was pressed; {self.rte_stage_where or 'stage not moved'}")
        sent = self._rte_switch_pulse(state['pulse_ma'], dict(pulse, width_s=state['width_s']))
        columns.update(sent)
        self._rte_log('pulse', index=progress, loop=loop, point=point, state=state['state'], write_field_g=columns['write_field_g'], **sent)
        self._rte_log_check()
        if away:
            self._rte_state_field(supply, SWITCH_STATE_READ_FIELD_G, limit, progress, state, len(states), 'read')
        return columns
    def _rte_mode_changed(self, _event=None):
"""),
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
# 1st harmonic.  Since 2026-11-28 (user's figure: "PHE default use these parameters pls."): outer field 1000 G and
# Acquire s 2 on Angle+Field (acquire_s: what a scan's Acquire s shows in this tab); Angle+Current keeps 5 s.
# Switch-IP (user, 2026-11-27: "add a Switch-IP module which use 14mA to -14mA step 2mA as default and SR830-1
# use harmonic 2 pls. pulse width default 30us. the other settings are the same as Switch-OOP"): the tab after
# Switch-OOP, with its scans, Switch-loop, 200 G and 0.5 mA; its own are the loop 14 to -14 mA in 2 mA
# (ranges: what a scan's Start, End, Step show in this tab), 30 us pulses (pulse_width_us: the one
# Pulse us box, 1000 in the other tabs) and SR830-1 on the 2nd harmonic.  Typed values stay, as above.
# AHE (user's figure, 2026-11-27: "default setting as the figure for AHE module"): the Field scan from -3 to
# 3 A in 0.1 A and back, a 0.5 mA RMS read current, SR830-1 on the 1st harmonic; Settle s 0.5, Acquire s 2 and
# Round trip were the Field scan's already.  The figure shows the Field scan, so Field+Angle and Field+Current
# keep the -1 to 1 A in 0.02 A of 2026-11-22.
# Switch-OOP since 2026-11-28 (user's figure of the Switch scan: "Switch-OOP default use the figure's settings"): the
# tab opens on the Switch scan, whose states are -360 deg / 1000 G / 0 mA, -270 deg / 200 G / -10 mA, -270 deg /
# 200 G / 10 mA and -360 deg / -1000 G / 0 mA, 50 us each (states: what the table shows in this tab; a cell follows
# the tab only while it holds what the program put there, and the other tabs show SWITCH_DEFAULT_STATES).  Settle s
# 10, Acquire s 10, Cycles 1 and Pulses 1 were the scan's already.  The tab's Switch-loop values stay as they were.
# Later on 2026-11-28 (user's figure of the table: "switching default use this settings."): the same angles with
# 600 G / 0 mA, 100 G / -17 mA, 100 G / 17 mA and -600 G / 0 mA, 1000 us each.  The angles are Switch-OOP's and the
# 1000 us is not Switch-IP's 30 us, so the figure is read as Switch-OOP's; Switch-IP keeps SWITCH_DEFAULT_STATES.
RTE_MEASUREMENT_START = {
    "PHE": dict(scan="Angle+Field", harmonic_a="1", angle_field_g="1000", acquire_s={"Angle+Field": "2"}),
    "AHE": dict(scan="Field", current_ma="0.5", harmonic_a="1", ranges={"Field": ("-3", "3", "0.1")}),
    "Switch-OOP": dict(scan="Switch", current_ma="0.5", harmonic_a="1", ranges={"Switch-loop": ("24", "-24", "2")},
                       settle_s={"Switch-loop": "10"}, acquire_s={"Switch-loop": "10"}, loop_field_g="500",
                       states=(("-360", "600", "0", "1000"), ("-270", "100", "-17", "1000"), ("-270", "100", "17", "1000"), ("-360", "-600", "0", "1000"))),
    "Switch-IP": dict(scan="Switch-loop", current_ma="0.5", harmonic_a="2", ranges={"Switch-loop": ("14", "-14", "2")}, pulse_width_us="30"),
}
SWITCH_LOOP_DEFAULT_RANGE = ("22", "-22", "2")
SWITCH_LOOP_DEFAULT_FIELDS_G = "200"
# The live lines' width, in characters, beside the instrument rows of a wide window (32 beside the rack, where a
# long line wraps): "Field 1/1 +200 G, step 6: I -1.136 A, B +198.667 G" on one line.
RTE_LIVE_WIDE_CHARS = 48
# The Pulse us box is one box for the Switch scans and Apply pulse, on every tab.
SWITCH_DEFAULT_PULSE_WIDTH_US = 1000.0
# The states of the Switch scan (see "The Switch scan runs states" above).  The table opens with four; a row past
# them is empty until it is typed.  The numbers are those of the question's picture the user chose (0 and 90 degrees,
# 500 G, +/-20 mA, 1000 us: the field, pulse and width of the Switch scan in their figure of the same day), and the
# width follows the tab's Pulse us start value (30 us on Switch-IP) while it still holds what the program put there.
SWITCH_STATES_MAX = 12
SWITCH_STATE_COLUMNS = ("Angle \u00b0", "Field G", "Pulse mA", "Pulse \u00b5s")
SWITCH_DEFAULT_STATES = (("0", "500", "20", "1000"), ("0", "500", "-20", "1000"), ("90", "500", "20", "1000"), ("90", "500", "-20", "1000"))
# The field every state is read at, and the stage turns at (user's choice: "At 0 G, as MS-fourState").
SWITCH_STATE_READ_FIELD_G = 0.0
# Settle s and Acquire s of the Switch scan, on every tab (user, 2026-11-28: "settle 10s aqcuire 10s default"); the
# Switch-loop and Switch2 scans keep theirs.  A typed value stays, as for the other scans.
SWITCH_STATES_SETTLE_S = 10.0
SWITCH_STATES_ACQUIRE_S = 10.0


def rte_pulse_axis(mode):
    return 'avtech' if mode == SWITCH2_SCAN_MODE else 'state' if mode == SWITCH_SCAN_MODE else 'pulse'


# The State axis of the Switch scan with its cycles side by side: a mark at every state of every cycle, labelled
# with the state's number (1 2 3 4 1 2 3 4 ...).  Where the numbers would run into each other every second, third
# ... state of a cycle is labelled, counted from state 1 again in each cycle; past that, state 1 of every n-th
# cycle; marks closer than 4 px are left out with their numbers.
def rte_state_cycle_ticks(states, x_min, x_max, plot_width):
    spacing = plot_width / max(x_max - x_min, 1e-9)
    every, ticks = max(1, math.ceil((22 if states >= 10 else 15) / spacing)), []
    for position in range(max(1, math.ceil(x_min)), math.floor(x_max) + 1):
        cycle, state = divmod(position - 1, states)
        shown = state % every == 0 and (state == 0 or states - state >= every) if every <= states else state == 0 and cycle % math.ceil(every / states) == 0
        if shown or spacing >= 4:
            ticks.append((position, str(state + 1) if shown else ''))
    return ticks


def rte_switch_states(rows, count):
    # The first `count` rows of the table as states: number, stage angle (None: an empty box), field, pulse
    # current and pulse width.  The angles are typed for every state or for none.
    try:
        shown = int(str(count).strip())
    except ValueError:
        shown = 0
    if not 1 <= shown <= min(SWITCH_STATES_MAX, len(rows)):
        raise ValueError(f'States: type how many states the scan has, a whole number from 1 to {SWITCH_STATES_MAX}')
    states = []
    for number, texts in enumerate(rows[:shown], 1):
        values = []
        for title, text in zip(SWITCH_STATE_COLUMNS, texts):
            text = str(text).strip()
            if not text and title == SWITCH_STATE_COLUMNS[0]:
                values.append(None)
                continue
            try:
                value = float(text)
            except ValueError:
                raise ValueError(f'State {number}, {title}: ' + (f'"{text}" is not a number' if text else 'type a number')) from None
            if not math.isfinite(value):
                raise ValueError(f'State {number}, {title}: "{text}" is not a finite number')
            values.append(value + 0.0)
        angle, field, pulse_ma, width_us = values
        if abs(field) > RTE_OUTER_FIELD_MAX_G:
            raise ValueError(f'State {number}: fields must stay within +/-{RTE_OUTER_FIELD_MAX_G:g} G ({RTE_OUTER_FIELD_MAX_G:g} Oe); {field:g} G is outside')
        if angle is not None and abs(angle) > NEWMARK_CABLE_LIMIT_DEG:
            raise ValueError(f'State {number}: stage angles must stay within +/-{NEWMARK_CABLE_LIMIT_DEG:g}\u00b0 of the stage zero (the sample wires); {angle:g}\u00b0 is outside')
        states.append(dict(state=number, angle_deg=angle, field_g=field, pulse_ma=pulse_ma, width_s=width_us / 1e6))
    without = [state['state'] for state in states if state['angle_deg'] is None]
    if without and len(without) != len(states):
        raise ValueError(f'Angle \u00b0: state {without[0]} has no angle. Type the stage angle of every state, or empty every Angle \u00b0 box so that the stage is not moved')
    return tuple(states)


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
