"""The host window of the standalone MOKE application, and what steers its
extraction from the main program (tools/extract_app.py reads this file; it is
not imported by the application).

The MOKE pages are the main window's own, so the methods below are the main
program's with the other pages (Non-local, PPMS, SHHV & Switch, FMR, STFMR)
taken out: the window, the redraw on a tab change, and the close.
"""
APP_NAME = "the MOKE light, MOKE motor, MOKE magnet, CIDWM and MOKE-24 pages"
# This program's own version (user, 2026-11-27: "name PPMS, RT, MOKE, FMR exe all as v1.0"), not the
# main program's.  It is in the .exe's properties and in every results file, and it names the release
# ("Transport_MOKE v1.0"): raise it here, and in pyproject.toml, and push the tag moke-v<version>, to start a new release.
APP_VERSION = "1.0"
OUTPUT = "transport/moke/app.py"
GLUE_FILES = ("ppms_package_glue.py",)
KEEP_PATTERNS = ("(?i)moke", "(?i)cidwm")
DROP = ("RTEPanel", "PPMSPanel")
STUBS = {}
INIT_DROP = (
    "self.nonlocal_vi_mfli_device_var.trace_add(",
    "self._initialize_ppms_state()",
)
KEEP = ("recycle_bin_available",)
# What the program is started from.  Everything it cannot reach from these is taken out of the generated module
# by the tool's second pass, prune_unreachable (user, 2026-11-28: "remove the unused code in RT to make it as
# shorter as possible", then "do the same for PPMS, MOKE and FMR"): code of other pages that was kept because
# this program's code uses the same names, and helpers only tests called (KEEP and KEEP_PATTERNS above no
# longer hold those).
PRUNE_ROOTS = ("main", "run")
EXTRA_IMPORTS = (
    '_PROGRAM_FILE = str(Path(__MODULE_FILE__).resolve().parents[2] / "Transport_MOKE.py")',
    '# Installed with pip, the package is in site-packages: the folder the program is started in stands in.',
    'if not getattr(sys, "frozen", False) and {"site-packages", "dist-packages"} & set(Path(_PROGRAM_FILE).parts):',
    '    _PROGRAM_FILE = str(Path.cwd() / "Transport_MOKE.py")',
)
# How runs are saved in this program (user, 2026-11-28: "standardize the file-saving logic across all parts of the
# code and ensure that the file and variable naming conventions are consistent", for RT, then "do the same for PPMS,
# MOKE and FMR"): a run's folder, live CSV and log are the recorder's alone; a copy saved by hand is suggested under
# the run's own name, <stem>_copy.csv, in the run folder; the program log is named after this program.  The names of
# the files a scan makes, of the CSV's columns and of the log's fields are as they were: the analysis scripts read them.
SOURCE_REPLACE = (
    ('        timestamp = datetime_module.datetime.now().strftime("%Y%m%d_%H%M%S")\n',
     '        timestamp = datetime_module.datetime.now().strftime("%Y%m%d_%H%M%S_%f")\n'),
)
REPLACE = {
    "'NH.ProfChen.MagnetoElectroOpticalMicrowaveTransport'": "'NH.ProfChen.TransportMOKE'",
    '"Transport_log_%Y%m%d_%H%M%S.txt"': '"Transport_MOKE_log_%Y%m%d_%H%M%S.txt"',
}

MAIN_WINDOW_TITLE = "Transport_MOKE_NH"
# Its own icon (Other-files/assets): the main program's picture in another colour, with the name on it.
APPLICATION_ICON_BASENAME = "Transport_MOKE"


class CombinedControlApp:
    # The MOKE-24 Keithley and the CIDWM 6221 are also the Non-local page's in
    # the main program, which refreshes that page's buttons when they connect
    # or disconnect.  There is no Non-local page here.
    def _update_nonlocal_vi_controls(self) -> None:
        return

    def _update_nonlocal_keithley_controls(self) -> None:
        return

    def build_ui(self) -> None:
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self._configure_ui_styles()
        notebook_pad = self._ui_px(3, 2)
        self.notebook = ttk.Notebook(self.root, padding=(notebook_pad, notebook_pad, notebook_pad, 0))
        self.notebook.grid(row=0, column=0, sticky="nsew")
        self.led_tab = ttk.Frame(self.notebook)
        self.motor_tab = ttk.Frame(self.notebook)
        self.difference_tab = ttk.Frame(self.notebook)
        self.keithley_tab = ttk.Frame(self.notebook)
        self.k6221_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.led_tab, text="MOKE light")
        self.notebook.add(self.motor_tab, text="MOKE motor")
        self.notebook.add(self.difference_tab, text="MOKE magnet")
        self.notebook.add(self.k6221_tab, text="CIDWM")
        self.notebook.add(self.keithley_tab, text="MOKE-24")
        self.led_tab.rowconfigure(0, weight=1)
        self.led_tab.columnconfigure(0, weight=1)
        self.motor_tab.rowconfigure(0, weight=1)
        self.motor_tab.columnconfigure(0, weight=1)
        self.difference_tab.rowconfigure(0, weight=1)
        self.difference_tab.columnconfigure(0, weight=1)
        self.keithley_tab.rowconfigure(0, weight=1)
        self.keithley_tab.columnconfigure(0, weight=1)
        self.k6221_tab.rowconfigure(0, weight=1)
        self.k6221_tab.columnconfigure(0, weight=1)
        self.build_difference_ui()
        self.build_keithley_ui()
        self.build_k6221_ui()
        outer = ttk.Frame(self.led_tab, padding=8)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=0)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(4, weight=0)
        outer.rowconfigure(6, weight=0)
        outer.rowconfigure(7, weight=1)
        self.led_outer = outer
        self.build_camera_launcher_ui(outer, row=0)
        connection = ttk.LabelFrame(outer, text="Serial connection", padding=8)
        connection.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        connection.columnconfigure(7, weight=1)
        ttk.Label(connection, text="LED port:").grid(row=0, column=0)
        self.port_combo = ttk.Combobox(connection, textvariable=self.port_var, width=11, state='normal')
        self.port_combo.grid(row=0, column=1, padx=4)
        ttk.Button(connection, text='Refresh', command=self.refresh_ports).grid(row=0, column=2, padx=3)
        self.connect_button = ttk.Button(connection, text="Connect", command=self.connect)
        self.connect_button.grid(row=0, column=3, padx=3)
        self.disconnect_button = ttk.Button(connection, text='Disconnect', command=self.disconnect)
        self.disconnect_button.grid(row=0, column=4, padx=3)
        self._create_connection_indicator(connection, 'led').grid(row=0, column=5, padx=(8, 1))
        ttk.Label(connection, textvariable=self.connection_var).grid(row=0, column=6, padx=(1, 10))
        ttk.Label(connection, textvariable=self.operation_var).grid(row=0, column=7, sticky='e')
        self.led_log_toggle_button = ttk.Button(connection, text='Show log', command=self.toggle_led_log, style='Compact.TButton', width=8)
        self.led_log_toggle_button.grid(row=0, column=8, padx=(8, 0))
        safety = ttk.Frame(outer)
        safety.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        safety.columnconfigure(0, weight=1)
        ttk.Label(safety, text=f'Safety limit: current 0–{CURRENT_LIMIT}; start from 0 for a first test.', foreground='#9a4d00').grid(row=0, column=0, sticky='w')
        self.off_button = tk.Button(
            safety,
            text="Zero all / emergency off",
            command=self.all_off,
            bg=THEME_COLORS["danger"],
            fg="white",
            activebackground=THEME_COLORS["danger_pressed"],
            activeforeground="white",
            padx=10,
            pady=4,
        )
        self.off_button.grid(row=0, column=1)
        global_frame = ttk.LabelFrame(outer, text="Global control", padding=8)
        global_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 7))
        global_frame.columnconfigure(1, weight=1)
        ttk.Label(global_frame, text='All 4 currents:').grid(row=0, column=0, sticky='e', padx=(0, 6))
        preset_row = ttk.Frame(global_frame)
        preset_row.grid(row=0, column=1, sticky="ew")
        presets = ttk.Frame(preset_row)
        presets.grid(row=0, column=0, sticky="w")
        for index, value in enumerate((0, 10, 50, 100, 500)):
            button = ttk.Button(presets, text=str(value), width=6, command=lambda selected=value: self.apply_preset(selected))
            button.grid(row=0, column=index, padx=(0 if index == 0 else 4, 0))
            self.action_widgets.append(button)
        all_channel_buttons = ttk.Frame(preset_row)
        all_channel_buttons.grid(row=0, column=1, sticky="w")
        continuous = ttk.Button(all_channel_buttons, text='All 4 continuous on', command=self.all_continuous)
        continuous.grid(row=0, column=0)
        self.action_widgets.append(continuous)
        apply_all = ttk.Button(all_channel_buttons, text="Apply all", command=self.apply_all)
        apply_all.grid(row=0, column=1, padx=(4, 0))
        self.action_widgets.append(apply_all)
        query_all = ttk.Button(all_channel_buttons, text="Query all", command=self.query_all)
        query_all.grid(row=0, column=2, padx=(4, 0))
        self.action_widgets.append(query_all)
        self._arrange_pair_by_width(preset_row, presets, all_channel_buttons, gap=12, stack_gap=4)
        ttk.Label(global_frame, text='Continuous current, all 4:').grid(row=1, column=0, sticky='e', padx=(0, 6), pady=(6, 0))
        continuous_row = ttk.Frame(global_frame)
        continuous_row.grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Spinbox(continuous_row, from_=0, to=CURRENT_LIMIT, increment=1, textvariable=self.global_current_var, width=9).grid(row=0, column=0, sticky='w')
        set_continuous_current = ttk.Button(continuous_row, text='Set continuous current on all 4', command=self.apply_global_continuous_current)
        set_continuous_current.grid(row=0, column=1, sticky="w", padx=(6, 0))
        self.action_widgets.append(set_continuous_current)
        options_row = ttk.Frame(global_frame)
        options_row.grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Checkbutton(options_row, text='Read back after setting', variable=self.auto_readback_var).grid(row=0, column=0, sticky='w')
        ttk.Checkbutton(options_row, text='Show and edit advanced parameters p/g/d/f', variable=self.raw_edit_var, command=self.update_raw_state).grid(row=0, column=1, sticky='w', padx=(16, 0))
        channels_frame = ttk.Frame(outer)
        channels_frame.grid(row=4, column=0, sticky='new', padx=(0, 4), pady=(0, 7))
        channels_frame.columnconfigure(0, weight=1)
        for channel in CHANNELS:
            channels_frame.rowconfigure(channel - 1, weight=0)
            self.build_channel(channels_frame, channel, channel - 1, 0)
        led_plot = ttk.LabelFrame(outer, text='ROI intensity vs time (raw 16-bit, no background subtraction)', padding=6)
        led_plot.grid(row=4, column=1, sticky='new', padx=(4, 0), pady=(3, 10))
        led_plot.rowconfigure(1, weight=0)
        led_plot.columnconfigure(0, weight=1)
        plot_header = ttk.Frame(led_plot)
        plot_header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        roi_mean_label = ttk.Label(plot_header, textvariable=self.led_roi_mean_var, style='Metric.TLabel', width=37)
        roi_mean_label.grid(row=0, column=0, sticky="w")
        roi_hint_label = ttk.Label(plot_header, text='Shift + left-drag on the camera view to select an ROI', style='Muted.TLabel')
        roi_hint_label.grid(row=0, column=1, sticky="w")
        self._arrange_pair_by_width(plot_header, roi_mean_label, roi_hint_label, gap=12, stack_gap=2)
        self.led_intensity_canvas = tk.Canvas(
            led_plot,
            bg=THEME_COLORS["plot_background"],
            highlightthickness=1,
            highlightbackground=THEME_COLORS["plot_border"],
            height=self._ui_px(230, 135, canvas=True),
        )
        self.led_intensity_canvas.grid(row=1, column=0, sticky="nsew")
        self.led_intensity_canvas.bind('<Configure>', lambda _event: self._redraw_live_intensity_plots())
        self.build_stage_ui(outer, row=5, columnspan=2)
        self.led_log_frame = ttk.LabelFrame(outer, text='Program communication log', padding=5)
        self.led_log_frame.grid(row=6, column=0, columnspan=2, sticky="nsew")
        self.led_log_frame.rowconfigure(0, weight=1)
        self.led_log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(self.led_log_frame, height=5, wrap='none', state='disabled', font=(self.mono_font_family, self.ui_small_font_size), background='#fbfcfd', relief='flat', padx=5, pady=4)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(self.led_log_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        xscrollbar = ttk.Scrollbar(self.led_log_frame, orient='horizontal', command=self.log_text.xview)
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
        self.led_log_frame.grid_remove()

    def _redraw_active_tab(self) -> None:
        if self.closing or self.notebook is None:
            return
        try:
            selected = self.notebook.nametowidget(self.notebook.select())
        except (KeyError, tk.TclError):
            return
        self._redraw_live_intensity_plots()
        if selected is self.difference_tab:
            self._redraw_moke_plot()
        elif selected is self.keithley_tab:
            self._redraw_keithley_plot()

    def safe_close_hardware(self) -> None:
        shutdown_steps = (
            ("Camera", self.safe_close_camera),
            ("LED", self.safe_close_led),
            ("Analyser rotation stage", self.safe_close_stage),
            ("Magnets and gaussmeters", self.safe_close_magnets),
            ("MOKE-24 Keithley", self.safe_close_keithley),
            ("Keithley 6221", self.safe_close_k6221),
            ("Avtech pulse generator", self.safe_close_avtech),
            ("Cell-VSDM motor", self.safe_close_motor),
        )
        for label, operation in shutdown_steps:
            try:
                operation()
            except BaseException as error:
                try:
                    self.append_log(f"{label} safe close incomplete: {error}")
                except BaseException:
                    pass

    def request_close(self) -> None:
        if self.closing:
            return
        if self.busy:
            messagebox.showinfo('Please wait', 'The LED serial operation has not finished; close the program later.', parent=self.root)
            return
        confirmed = messagebox.askyesno(
            "Close all modules",
            "Exit the control program?\n\n"
            "The program will try, in order, to:\n"
            "  • stop PCO camera acquisition and any running scan\n"
            "  • finish and save any Camera Live recording in progress\n"
            "  • zero the four LED currents and switch their outputs off\n"
            "  • keep the analyser stage at its position (no zeroing), stop motion and disconnect\n"
            "  • stop and disable the translation motor\n"
            "  • write 0 A to the in-plane/out-of-plane KEPCO and disconnect the gaussmeters\n"
            "  • zero the MOKE-24 Keithley, switch its output off and disconnect\n"
            "  • stop Keithley 6221 pulses, zero, switch its output off and disconnect\n"
            "After exiting, still confirm every instrument output and power supply is in a safe state.",
            icon="warning",
            parent=self.root,
        )
        if not confirmed:
            return
        self.closing = True
        self.operation_var.set("Closing all modules…")
        focus = self.__dict__.get("auto_focus")
        if focus is not None:
            focus.cancel("the program closing")
        self.magnet_scan_stop_event.set()
        self.magnet_field_zero_stop_event.set()
        self.keithley_stop_event.set()
        self.k6221_stop_event.set()
        for owner in (self, self.__dict__.get("ppms_panel"), self.__dict__.get("rte_panel")):
            if owner is None:
                continue
            for name in (
                "nonlocal_keithley_stop_event", "stfmr_fmr_stop_event",
                "stfmr_frequency_stop_event", "stfmr_lockin_stop_event",
                "ppms_field_scan_stop_event",
                "rte_stage_stop_event",
                "stfmr_field_stop_event", "stfmr_lockin_field_stop_event",
            ):
                event = owner.__dict__.get(name)
                if event is not None:
                    event.set()
        try:
            self.magnet_auto_poll_var.set(False)
        except tk.TclError:
            pass
        detached_recorder = None
        camera = self.camera_window
        if camera is not None:
            detached_recorder = camera.detach_video_recorder()
        self.safe_close_camera()
        def finish_window_close() -> None:
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        def close_everything() -> None:
            try:
                self.safe_close_hardware()
                if detached_recorder is not None:
                    try:
                        detached_recorder.stop()
                    except BaseException as error:
                        self.append_log(f"Camera recording finalisation warning: {error}")
                video_future = self.camera_video_stop_future
                if video_future is not None:
                    try:
                        video_future.result(timeout=10.0)
                    except BaseException as error:
                        self.append_log(f"Camera recording finalisation warning: {error}")
            finally:
                self.file_executor.shutdown(wait=False, cancel_futures=False)
                self.executor.shutdown(wait=False, cancel_futures=True)
                self.post_ui(finish_window_close)
        threading.Thread(target=close_everything, name='moke-safe-shutdown', daemon=True).start()


def main() -> None:
    root = tk.Tk()
    app = CombinedControlApp(root)
    app.update_raw_state()
    MotorAppClass, motor_self_test = create_motor_subsystem()
    motor_self_test()
    app.attach_motor(MotorAppClass)
    root.after_idle(lambda: maximize_main_window(root))
    if serial is None:
        root.after(250, lambda: messagebox.showerror('pyserial missing', 'Run first:\n\npy -m pip install pyserial'))
    try:
        root.mainloop()
    finally:
        app.safe_close_hardware()
        app.executor.shutdown(wait=False, cancel_futures=True)


def run() -> None:
    """The installed command (pyproject.toml: transport-moke)."""
    if PCO_DLL_SELF_TEST_SWITCH in sys.argv:
        raise SystemExit(run_pco_dll_self_test())
    main()
