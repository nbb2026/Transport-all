"""The Switch scan (user, 2026-11-21: "add a Switch module containing 6221,
830, magnet like SHHV has LS643, Kepco4886, LS475, the motor. 6221 pulse
write function. to get a switching results like this fig", R_H against the
pulse current at several fields).  Since 2026-11-22 it is the last mode of
the "SHHV & Switch" page (user: "add the switch scan to the selection like
angle + field2 scan"; "change the name of SHHV to SHHV & Switch. delete the
before Switch module"), and the Switch page is gone.

The real RTEPanel on test_rte_angle_end_to_end's harness: stand-in widgets,
a real one-thread worker, a KEPCO and an LS475 whose field follows its
current, and here a 6221 that records every command of the write pulse.  No
VISA session, no window."""
import threading
import types
import unittest
from unittest.mock import patch

import test_rte_angle_end_to_end as ete
from test_ppms_motor_debug import app
from test_rte_angle_scan import Recorder

setUpModule, tearDownModule = ete.setUpModule, ete.tearDownModule


class Fake6221:
    """The 6221 as the write pulse uses it: every write kept, the waveform
    settings read back as written, a finite train ending by itself."""

    SETTINGS = ("SOUR:WAVE:AMPL", "SOUR:WAVE:OFFS", "SOUR:WAVE:FREQ", "CURR:COMP", "SOUR:WAVE:DUR:CYCL")

    def __init__(self):
        self.sent, self.values, self.output, self.event, self.trains = [], {}, 0, 0, []
        self.sine, self.sines = False, []
        self.readback = {}          # a setting's wrong read-back, for a test
        self.compliance_after_train = False
        self.read_in_compliance = False     # STAT:MEAS:COND? bit 3 with the read current on

    def write(self, command):
        self.sent.append(command)
        name, _, value = command.partition(" ")
        if name in self.SETTINGS:
            self.values[name] = float(value)
        elif command in ("OUTP ON", "OUTP OFF"):
            self.output = int(command == "OUTP ON")
        elif command == "SOUR:WAVE:FUNC SQU":
            self.sine = False
        elif command == "SOUR:WAVE:FUNC SIN":
            self.sine = True
        elif command == "SOUR:WAVE:INIT":
            if self.sine:
                self.output = 1         # the continuous read current
                self.sines.append(dict(self.values))
                return
            self.trains.append(dict(self.values))
            self.output = 0
            if self.compliance_after_train:
                self.event = 8

    def query(self, command):
        if command == "SYST:ERR?":
            return '0,"No error"'
        if command == "STAT:MEAS:EVEN?":
            value, self.event = self.event, 0
            return str(value)
        if command == "STAT:MEAS:COND?":
            return "8" if self.read_in_compliance and self.output else "0"
        if command == "OUTP?":
            return str(self.output)
        name = command.rstrip("?")
        return repr(self.readback.get(name, self.values[name]))


class SwitchScan(ete.EndToEnd):
    def make_switch(self, states=None, fields="100", span=None, width="30", pulses="1", cycles="1"):
        """The page ready for a Switch scan: SR830-1 alone at the first
        harmonic, 0.5 mA RMS read current, the KEPCO and an LS475 that reads
        100 G per A of it, the fake 6221, and the field setting's waits made
        tiny.  ``states``: the table's rows (Angle, Field G, Pulse mA, Pulse
        us) as typed; ``span``: one state a pulse current instead, all at
        ``fields`` G with no angle."""
        h = self.make(meter="sr830")
        panel = h.panel
        self.assertIs(type(panel), app.RTEPanel)
        panel.ppms_transport_current_var.set("0.5")
        panel.ppms_transport_harmonic_a_var.set("1")
        h.harmonic["830_a"] = 1
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Switch")
            panel._rte_mode_changed()
        # The states as typed in the table (user, 2026-11-28: "change the
        # switch scan mode to set the state 1, 2, 3, 4...").
        if states is None:
            states = ([("", fields, f"{value:g}", width) for value in app.ppms_scan_axis(*map(float, span))] if span
                      else [("", "100", "-2", width), ("", "-50", "2", width), ("", "0", "0", width)])
        type_states(panel, states)
        panel.ppms_field_scan_loop_var.set(cycles)
        panel.rte_pulse_count.set(pulses)
        h.gauss = ete.FollowingGauss(h.log, h.kepco)
        panel.rte_controllers["gauss"] = h.gauss
        for name, value in (("MAGNET_FIELD_SET_SETTLE_S", 0.0), ("MAGNET_FIELD_SET_READ_INTERVAL_S", 1e-4),
                            ("MAGNET_FIELD_SET_GROUP_GAP_S", 1e-4), ("SWITCH_PULSE_DONE_MARGIN_S", 0.0)):
            patcher = patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(app.time, "sleep", lambda _seconds: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        h.fake = Fake6221()
        real_first, real_average = panel._acquire_ppms_first_point, panel._average_ppms_transport_sample

        def traced(result):
            trace = panel.__dict__.get("ppms_sample_trace")
            if trace is not None:
                trace.clear()
                now = app.time.monotonic()
                for offset, x in ((0.0, 1e-6), (1.0, 2e-6), (2.0, 3e-6)):
                    trace.append((now + offset, {"sr830_8_x_v": x, "sr830_8_y_v": -x}))
            return result
        panel._acquire_ppms_first_point = lambda *args: traced(real_first(*args))
        panel._average_ppms_transport_sample = lambda *args: traced(real_average(*args))
        source = panel.ppms_instrument_controllers["6221"]
        source.lock, source.instrument = threading.RLock(), h.fake

        def query(key, command, count):
            if key == "6221":
                if command == "OUTP?":
                    h.log.append(("6221", "OUTP?", threading.get_ident()))
                return (float(h.fake.query(command)),)
            if command == "FREQ?":      # the SR830's reference, locked to the read current
                return (float(panel.ppms_transport_frequency_var.get()),)
            if command == "LIAS?":
                return (0.0,)
            assert command == "HARM?", command
            return (h.harmonic[key],)
        panel._ppms_query_numbers = query
        h.configured = []

        def configure(settings):
            h.configured.append(dict(settings))
            h.fake.sent.append("FULL SET-UP")
            h.fake.output = 1
            h.log.append(("6221", "on", settings["current_rms_ma"], settings["frequency_hz"], threading.get_ident()))
        panel._configure_ppms_transport_scan = configure

        def off():
            # The page's output off (SOUR:WAVE:ABOR, CURR 0, OUTP OFF), on the fake.
            h.log.append(("6221", "off", threading.get_ident()))
            for command in ("SOUR:WAVE:ABOR", "OUTP OFF"):
                h.fake.write(command)
            panel.post_ui(lambda: panel.ppms_transport_status_var.set("Transport acquisition: 6221 output OFF"))
        panel._stop_ppms_transport_source = off
        lines = panel.test_transport_lines = []
        line, real_set = panel.ppms_transport_status_var, panel.ppms_transport_status_var.set

        def record(value):
            lines.append(value)
            return real_set(value)
        line.set = record
        h.log.clear()
        return h


def type_states(panel, states):
    """The table as typed: the States box and each state's four boxes."""
    panel.rte_states_count.set(str(len(states)))
    for variables, texts in zip(panel.rte_state_vars, states):
        for variable, text in zip(variables, texts):
            variable.set(text)
    panel._rte_show_state_rows()


def status_lines(h):
    """Every text the page set on its acquisition line, in order (the
    harness keeps the UI callbacks it ran)."""
    return h.panel.__dict__.get("test_transport_lines", [])


class SwitchPageTests(unittest.TestCase):
    def switch_page(self):
        """The page with its Switch mode chosen."""
        panel = ete.build_page(kepco=False)
        panel.test_widgets = list(Recorder.made)
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Switch")
            panel._rte_mode_changed()
        return panel

    def test_the_tab_is_shhv_and_switch_and_the_switch_page_is_gone(self):
        """User, 2026-11-22: "change the name of SHHV to SHHV & Switch.
        delete the before Switch module".  The tab's title only: the page's
        texts, files, columns and controllers still say SHHV."""
        self.assertFalse(hasattr(app, "SwitchPanel"))
        self.assertEqual(app.RTEPanel.ppms_page_name, "SHHV")
        with open(app.__file__, encoding="utf-8") as source:
            text = source.read()
        # In this program the page's tab is the chosen measurement's (user, 2026-11-27; test_rt_measurements.py).
        self.assertIn("self.notebook.add(self.rte_panel_tab, text=name)", text)
        self.assertNotIn("switch_panel", text)
        panel = self.switch_page()
        self.assertEqual({c.owner_scope for c in panel.rte_controllers.values()}, {"SHHV"})
        texts = {str(w.options.get("text", "")) for w in panel.test_widgets}
        self.assertTrue({"Settings", "Scan", "6221 write", "Pulse µs", "Pulses"} <= texts, texts)
        # All three SR830s and the Zurich keep their rows, the Zurich's
        # harmonic row under the three.
        self.assertEqual(panel.zurich_harmonic_combo.grid_options["row"], 3)
        for key in app.PPMS_SR830_KEYS:
            self.assertFalse(panel.ppms_device_resource_widgets[key].parent.grid_removed, key)

    def test_the_settings_have_a_pulse_row_and_100_v_compliance(self):
        """User, 2026-11-22: "add another pulse apply below here RMS
        continuous settings. Change default compliance to 100V"."""
        panel = ete.build_page(kepco=False)
        self.assertEqual(panel.ppms_transport_compliance_var.get(), "100")
        self.assertEqual(app.RTE_TRANSPORT_COMPLIANCE_V, 100.0)
        # Pulse µs starts at 1000 in this program (user's figure, 2026-11-27: "default settings use fig in
        # switch mode in RT"; 10 in the main program since 2026-11-24), one pulse per write.
        self.assertEqual((panel.rte_pulse_width_us.get(), panel.rte_pulse_count.get()), ("1000", "1"))
        parts = panel.rte_apply_pulse_parts
        self.assertEqual([w.options.get("text") for w, _options in parts if "text" in w.options],
                         ["Pulse mA", "Pulse µs", "Pulses", "Apply pulse"])
        entries = [w for w, _options in parts if "textvariable" in w.options]
        self.assertEqual([w.options["textvariable"] for w in entries],
                         [panel.rte_pulse_current_ma, panel.rte_pulse_width_us, panel.rte_pulse_count])
        # Under the 6221's row, in its columns; the 6221's line and its OFF button one line down.
        rms = next(w for w in Recorder.made if w.options.get("textvariable") is panel.ppms_transport_current_var)
        params = rms.parent
        self.assertEqual(rms.grid_options["row"], 2)
        self.assertEqual({w.grid_options["in_"] for w, _options in parts}, {params})
        self.assertEqual([(w.grid_options["row"], w.grid_options["column"]) for w, _options in parts],
                         [(3, column) for column in range(7)])
        live = next(w for w in Recorder.made if w.options.get("textvariable") is panel.ppms_current_live_var)
        self.assertEqual((live.grid_options["row"], live.grid_options["column"]), (4, 0))
        # The scan's own Pulse µs / Pulses boxes are the same two variables.
        scan_entries = [w for w in panel.rte_pulse_widgets if "textvariable" in w.options]
        self.assertEqual([w.options["textvariable"] for w in scan_entries],
                         [panel.rte_pulse_width_us, panel.rte_pulse_count])
        self.assertIs(parts[-1][0], panel.rte_apply_pulse_button)
        self.assertEqual(parts[-1][0].options["command"], panel._rte_apply_pulse)

    def test_the_connections_can_go_in_two_columns(self):
        """User, 2026-11-22: "also two columns for the instruments connection
        panel".  The supply's line, the LS475's reading and the field setting
        are the box's children, shown in the rack until the window has the
        width for two columns (GitHub's window tests check both layouts)."""
        panel = ete.build_page(kepco=False)
        rack = panel.rte_connection_widgets["newmark"][0].parent
        field_set = panel.rte_set_field_button.parent
        self.assertIs(field_set.parent, rack.parent)
        self.assertIs(field_set.grid_options["in_"], rack)
        self.assertEqual((field_set.grid_options["row"], field_set.grid_options["column"]), (2, 6))
        lines = [w for w in Recorder.made if w.options.get("textvariable") in (panel.rte_field_live,
                                                                                panel.rte_drive_live)]
        self.assertEqual(sorted((w.grid_options["row"], w.grid_options["column"]) for w in lines), [(0, 6), (1, 6)])
        self.assertEqual({w.grid_options["in_"] for w in lines}, {rack})
        self.assertEqual({w.parent for w in lines}, {rack.parent})

    def test_the_plots_have_a_row_of_x_and_y_against_time(self):
        """User, 2026-11-21: "add a row to show the SR830 x signal vs time
        pls"; 2026-11-22: "also add Y vs time": X and Y side by side, in the
        row under the X and Y plots, with an equal share of the height; it
        moves down when a second harmonic is measured.  No third pulse plot
        (user, 2026-11-22: "delete R voltage against the pulse current"): X
        and Y take the row's width; another mode has its phase plot again."""
        panel = self.switch_page()
        frame, canvases = panel.rte_time_frame, panel.rte_time_canvases
        self.assertEqual(sorted(canvases), ["x", "y"])
        self.assertIs(frame.parent, panel.ppms_plot_frame)
        self.assertEqual({canvas.parent for canvas in canvases.values()}, {frame})
        self.assertEqual([canvases[c].grid_options["column"] for c in ("x", "y")], [0, 1])
        self.assertEqual(frame.grid_options, dict(row=1, column=0, columnspan=3, sticky="nsew"))
        self.assertFalse(frame.grid_removed)
        # SR830-1 is at the second harmonic at the page's start-up.
        self.assertEqual(frame.options["text"], "X and Y vs time — 2nd harmonic, SR830-1")
        self.assertIs(panel.ppms_harmonic_plot_frames[(2, "theta")].grid_removed, True)
        self.assertIs(panel.ppms_harmonic_plot_frames[(2, "x")].grid_removed, False)
        self.assertIs(canvases["x"].ppms_compact_plot, True)
        self.assertFalse(panel.ppms_harmonic_canvases[(2, "x")].ppms_hide_x_labels)
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series") as draw:
            panel.ppms_transport_harmonic_a_var.set("1")
            panel.ppms_lockin_selection["zurich"].set(True)
            panel.zurich_harmonic.set("2")
            panel._refresh_ppms2_plot_layout()
            self.assertEqual(frame.grid_options["row"], 2)
            self.assertEqual(frame.options["text"], "X and Y vs time — 1st harmonic, SR830-1")
            self.assertEqual([call.args[2:5] for call in draw.call_args_list[-2:]],
                             [("Time (s)", "X voltage", "Waiting for scan data"),
                              ("Time (s)", "Y voltage", "Waiting for scan data")])
        # Another mode: the third plot is the phase again.
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Angle+Field")
            panel._rte_mode_changed()
        self.assertEqual(panel.ppms_harmonic_plot_frames[(1, "theta")].options["text"], "1st harmonic θ — SR830-1")
        self.assertIs(panel.ppms_harmonic_plot_frames[(1, "theta")].grid_removed, False)

    def test_the_shhv_page_has_switch_as_its_last_mode(self):
        """User, 2026-11-22: "change the name of SHHV scan to Scan, and add
        the switch scan to the selection like angle + field2 scan".  The box
        is "Scan"; Switch is the last choice; the page still starts on
        Angle+Field, where the pulse row and the time row are off screen."""
        panel = ete.build_page(kepco=False)
        self.assertEqual((panel.ppms_page_name, panel.rte_scan_modes), ("SHHV", app.RTE_SCAN_MODES))
        self.assertEqual(app.RTE_SCAN_MODES[-5:], ("Field+Angle", "Field+Current", "Switch", "Switch-loop", "Switch2"))
        self.assertEqual(panel.rte_start_button.parent.parent.options["text"], "Scan")
        self.assertEqual(panel.ppms_simple_mode.get(), "Angle+Field")
        self.assertIs(panel.rte_outer_list_entry.options["textvariable"], panel.rte_outer_ranges["Angle+Field"][0])
        pulse_row = panel.rte_pulse_widgets
        self.assertEqual([w.options.get("text") for w in pulse_row[:2] + pulse_row[3:4]],
                         ["6221 write", "Pulse µs", "Pulses"])
        self.assertEqual({w.grid_removed for w in pulse_row}, {True})
        self.assertTrue(panel.rte_time_frame.grid_removed or not panel.rte_time_frame.grid_options)
        self.assertIs(panel.rte_time_row_on, False)
        before = (panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get())
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series") as draw:
            # Switch chosen: its range, round trip, fields, the pulse row and
            # the time row; the 6221 and lock-in boxes are not touched.
            panel.ppms_simple_mode.set("Switch")
            panel._rte_mode_changed()
            # The user's settings (2026-11-25: "default use this setting in
            # switch"): the loop 14 to -14 to 14 mA in 2 mA steps, field -12
            # G, Settle s 30, Round trip off.
            # Since 2026-11-28 the states' table (user: "change the switch scan mode to set the state 1, 2, 3,
            # 4... like MS_four state"), in place of "Pulses mA", "Outer field G" and the Pulse us box.
            self.assertEqual({w.grid_removed for w in panel.rte_range_widgets}, {True})
            self.assertEqual({w.grid_removed for w in panel.rte_switch_pulse_list_widgets}, {True})
            self.assertEqual({w.grid_removed for w, _options in panel.rte_outer_list_widgets}, {True})
            frame = panel.rte_states_frame
            self.assertFalse(frame.grid_removed)
            self.assertEqual((frame.grid_options["row"], frame.grid_options["column"]), (0, 1))
            self.assertEqual([w.options["text"] for w in Recorder.made if w.parent is frame and w.options.get("text")][:4], ["Angle °", "Field G", "Pulse mA", "Pulse µs"])
            self.assertEqual((panel.rte_states_count.get(), len(panel.rte_state_rows)), ("4", 12))
            self.assertEqual([[v.get() for v in row] for row in panel.rte_state_vars[:5]],
                             [["0", "500", "20", "1000"], ["0", "500", "-20", "1000"], ["90", "500", "20", "1000"], ["90", "500", "-20", "1000"], ["", "", "", ""]])
            self.assertEqual([{w.grid_removed for w in row} for row in panel.rte_state_rows], [{False}] * 4 + [{True}] * 8)
            self.assertEqual([row[0].options["text"] for row in panel.rte_state_rows[:4]], ["1", "2", "3", "4"])
            for row in panel.rte_state_rows:
                for entry in row[1:]:
                    self.assertIn((entry, "normal"), panel.rte_edit_widgets, "locked with the other boxes while a scan runs")
            # The States box shows that many rows; a count that is no number leaves them.
            for typed, shown in (("2", 2), ("", 2), ("x", 2), ("0", 2), ("13", 2), ("12", 12), ("4", 4)):
                panel.rte_states_count.set(typed)
                panel._rte_show_state_rows()
                self.assertEqual([{w.grid_removed for w in row} for row in panel.rte_state_rows], [{False}] * shown + [{True}] * (12 - shown), typed)
            # Settle s and Acquire s start at 10 s in Switch (user, 2026-11-28:
            # "settle 10s aqcuire 10s default"; 30 s each before).
            self.assertEqual(panel.ppms_acquisition_time_var.get(), "10")
            self.assertIs(panel.rte_round_trip.get(), False)
            self.assertEqual((str(panel.ppms_field_scan_loop_var.get()), panel.ppms_field_scan_stable_var.get()), ("1", "10"))
            # Cycles in Round trip's place (user, 2026-11-24: "change the
            # round trip setting to cycle times and text input in the switch
            # scan mode"): the Loops count, so the Loops box is off screen.
            label, cycles = panel.rte_cycles_widgets
            self.assertEqual((label.options["text"], cycles.options["textvariable"]), ("Cycles", panel.ppms_field_scan_loop_var))
            self.assertEqual({w.grid_removed for w in panel.rte_cycles_widgets}, {False})
            self.assertEqual([(w.grid_options["row"], w.grid_options["column"]) for w in panel.rte_cycles_widgets], [(2, 5), (2, 6)])
            self.assertEqual({w.grid_removed for w in (*panel.rte_loops_widgets, panel.rte_round_trip_check)}, {True})
            self.assertEqual((panel.rte_scan_units.get(), panel.rte_scan_note.get()),
                             ("", "Switch: states x Cycles; read at 0 G"))
            # "6221 write" and Pulses stay (the pulses of a write are every state's); the width is the state's.
            self.assertEqual([w.grid_removed for w in pulse_row], [False, True, True, False, False])
            self.assertEqual({w.grid_options["row"] for w in pulse_row}, {4})
            self.assertEqual(panel.ppms_plot_axis, "state")
            self.assertIs(panel.rte_time_row_on, True)
            self.assertFalse(panel.rte_time_frame.grid_removed)
            self.assertEqual(panel.rte_time_frame.grid_options, dict(row=1, column=0, columnspan=3, sticky="nsew"))
            self.assertIn("Time (s)", {call.args[2] for call in draw.call_args_list})
            self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()),
                             before)
            # Another mode: both rows go again.
            draw.reset_mock()
            panel.ppms_simple_mode.set("Angle+Field")
            panel._rte_mode_changed()
            self.assertEqual({w.grid_removed for w in pulse_row}, {True})
            self.assertTrue(panel.rte_states_frame.grid_removed)
            self.assertEqual(panel.ppms_field_scan_stable_var.get(), "0.5", "Settle s back to 0.5 in the other modes")
            self.assertEqual({w.grid_removed for w in panel.rte_cycles_widgets}, {True})
            self.assertEqual({w.grid_removed for w in (*panel.rte_loops_widgets, panel.rte_round_trip_check)}, {False})
            self.assertEqual({w.grid_removed for w in panel.rte_switch_pulse_list_widgets}, {True})
            self.assertEqual({w.grid_removed for w in panel.rte_range_widgets}, {False})
            self.assertTrue(panel.rte_time_frame.grid_removed)
            self.assertIs(panel.rte_time_row_on, False)
            self.assertNotIn("Time (s)", {call.args[2] for call in draw.call_args_list})

    def test_the_x_axis_ends_at_the_settings_not_at_a_rounded_tick(self):
        """User, 2026-11-24: "the xlim should be the maxium of the settings
        not the readings" (a field sweep to 205 G drawn to 300 G).  The SHHV
        plots end at the scan's own range: the typed pulses or currents, or,
        for a measured field (the settings are supply amps), the last field
        read, not the next round tick."""
        from test_nonlocal_keithley import Canvas
        panel = ete.build_page(kepco=False)
        field = {"a": [(-200.0, 1e-6), (0.0, 2e-6), (205.0, 3e-6)]}
        canvas = Canvas(900, 300)
        panel._draw_nonlocal_series(canvas, field, "Measured magnetic field (G)", "X voltage", "wait", x_range=(app.math.inf, -app.math.inf))
        self.assertIn("200", canvas.texts())
        self.assertNotIn("300", canvas.texts())
        panel._draw_nonlocal_series(canvas, field, "Measured magnetic field (G)", "X voltage", "wait")
        self.assertIn("300", canvas.texts(), "the other pages' plots round out as before")
        pulses = {"b": [(6.0, 1e-6)]}
        panel._draw_nonlocal_series(canvas, pulses, "6221 pulse current (mA)", "X voltage", "wait", x_range=(-10.0, 10.0))
        self.assertTrue({"-10", "10"} <= set(canvas.texts()), canvas.texts())

    def test_the_state_axis_counts_the_states_again_in_every_cycle(self):
        """User's figure of two cycles of six states drawn over each other, 2026-11-28: "for switch cycle, the
        first row should have 1,2,3,4,5,6,1,2,3,4,5,6... this type x-axis"."""
        from test_nonlocal_keithley import Canvas
        panel = ete.build_page(kepco=False)
        points = {"SR830-1 P1": [(position, 1e-6 * (position % 6 >= 4)) for position in range(1, 13)]}
        canvas = Canvas(1000, 300)
        panel._draw_nonlocal_series(canvas, points, "State", "X voltage", "wait", x_range=(0.5, 12.5), x_cycle=6)
        numbers = [text for text in canvas.texts() if text.isdigit()]
        self.assertEqual(numbers[:12], ["1", "2", "3", "4", "5", "6"] * 2, canvas.texts())
        self.assertNotIn("12", canvas.texts())
        # The other axes are drawn as before.
        panel._draw_nonlocal_series(canvas, points, "State", "X voltage", "wait", x_range=(0.5, 12.5))
        self.assertTrue({"2.5", "12.5"} <= set(canvas.texts()), canvas.texts())
        # Every state of every cycle has a mark; the numbers thin out before they touch, counted from 1 in each cycle.
        ticks = app.rte_state_cycle_ticks
        self.assertEqual(ticks(4, 0.5, 4.5, 800), [(1, "1"), (2, "2"), (3, "3"), (4, "4")])
        self.assertEqual([label for _x, label in ticks(6, 0.5, 60.5, 800)], ["1", "", "3", "", "5", ""] * 10)
        self.assertEqual([label for _x, label in ticks(5, 0.5, 50.5, 700)], ["1", "", "3", "", ""] * 10, "no 5 beside the next cycle's 1")
        many = ticks(4, 0.5, 400.5, 800)
        self.assertEqual([x for x, _label in many], list(range(1, 400, 8)), "marks closer than 4 px go with their numbers")
        self.assertEqual({label for _x, label in many}, {"1"})
        self.assertEqual([label for _x, label in ticks(12, 0.5, 24.5, 800)][:13], [str(n) for n in range(1, 13)] + ["1"])

    def test_the_lockins_start_at_gpib_9_10_and_11(self):
        """User, 2026-11-25: "default settings as the fig in SHHV & Switch"
        (SR830-1 GPIB0::9, SR830-2 GPIB0::10, SR830-3 GPIB0::11).  The page
        takes any GPIB address 1 to 30 for its SR830s; the PPMS page keeps
        8, 9 and 10."""
        panel = ete.build_page(kepco=False)
        self.assertEqual([panel.ppms_resource_vars[key].get() for key in app.PPMS_SR830_KEYS],
                         ["GPIB0::9::INSTR", "GPIB0::10::INSTR", "GPIB0::11::INSTR"])
        self.assertEqual([panel._ppms_sr830_address(f"GPIB0::{a}::INSTR") for a in (1, 9, 11, 30)], [1, 9, 11, 30])
        for bad in ("GPIB0::0::INSTR", "GPIB0::31::INSTR", "ASRL3::INSTR"):
            with self.assertRaisesRegex(ValueError, "SR830 address must be GPIB0::<1 to 30>::INSTR"):
                panel._ppms_sr830_address(bad)
        self.assertEqual([app.PPMS_DEFAULT_RESOURCES[key] for key in app.PPMS_SR830_KEYS],
                         ["GPIB0::8::INSTR", "GPIB0::9::INSTR", "GPIB0::10::INSTR"])

    def test_the_plan_is_the_pulse_loop(self):
        plan = app.rte_scan_plan("Switch", "-2", "2", "2", 1, True)
        self.assertEqual([value for _loop, _point, value in plan], [-2.0, 0.0, 2.0, 0.0, -2.0])
        # Typed pulses, in the order typed, and back with Round trip.
        typed = app.rte_pulse_list("10, -5;  0 7.5")
        self.assertEqual(typed, (10.0, -5.0, 0.0, 7.5))
        plan = app.rte_scan_plan("Switch", None, None, None, 2, True, values=typed)
        self.assertEqual([value for _loop, _point, value in plan], [10.0, -5.0, 0.0, 7.5, 0.0, -5.0, 10.0] * 2)
        self.assertEqual([value for _loop, _point, value in app.rte_scan_plan("Switch", None, None, None, 1, False, values=typed)], list(typed))
        for text, message in (("", "type the pulse currents"), ("1, x", '"x" is not a number'), ("nan", "not a finite number")):
            with self.assertRaisesRegex(ValueError, message):
                app.rte_pulse_list(text)
        with self.assertRaisesRegex(ValueError, r"within \+/-105 mA; 106 mA is outside"):
            app.rte_scan_plan("Switch", None, None, None, 1, False, values=(0.0, 106.0))
        with self.assertRaisesRegex(ValueError, r"6221 pulse currents must stay within \+/-105 mA; 106 mA is outside"):
            app.rte_scan_plan("Switch", "0", "106", "106", 1, False)


class AveragingTraceTests(unittest.TestCase):
    """The real averaging loop keeps each counted reading when the page asks
    (ppms_sample_trace, the Switch scan's X and Y vs time, user,
    2026-11-22), the mean is the mean of those readings, an overloaded one
    is neither kept nor averaged, and a range change starts the window and
    its trace again.  Without the request nothing is kept."""

    def page(self, readings):
        page = types.SimpleNamespace()
        page.ppms_field_scan_stop_event = threading.Event()
        page.closing = False
        values = iter(readings)
        page._read_ppms_transport_sample = lambda frequency, lockins, allow: dict(next(values))
        return page

    @staticmethod
    def reading(x, **extra):
        return dict({"sr830_8_x_v": x, "sr830_8_y_v": -x, "sr830_8_frequency_hz": 317.3,
                     "sr830_8_reference_valid": True, "sr830_8_overload": False}, **extra)

    def average(self, page, duration=0.12):
        return app.CombinedControlApp._average_ppms_transport_sample(page, 317.3, ("830_a",), duration)

    def test_the_trace_holds_the_counted_readings_of_the_window(self):
        page = self.page([self.reading(1e-6, range_settle_s=0.01), self.reading(2e-6),
                          self.reading(9e-6, sr830_8_overload=True)] + [self.reading(4e-6)] * 50)
        page.ppms_sample_trace = [("stale", {})]
        result = self.average(page)
        trace = page.ppms_sample_trace
        self.assertNotIn(("stale", {}), trace)
        xs = [values["sr830_8_x_v"] for _at, values in trace]
        self.assertEqual(xs[0], 2e-6, "the reading before the range change is not kept")
        self.assertNotIn(9e-6, xs, "the overloaded reading is not kept")
        self.assertEqual(result["sample_count"], len(trace))
        self.assertAlmostEqual(result["sr830_8_x_v"], sum(xs) / len(xs))
        self.assertEqual(sorted(trace[0][1]), ["sr830_8_x_v", "sr830_8_y_v"])
        times = [at for at, _values in trace]
        self.assertEqual(times, sorted(times))

    def test_without_the_request_nothing_is_kept(self):
        page = self.page([self.reading(1e-6)] * 50)
        self.average(page, 0.05)
        self.assertNotIn("ppms_sample_trace", page.__dict__)


class SwitchScanTests(SwitchScan):
    def make_states(self, states, **kwargs):
        """make_switch with the scan's steps kept in h.log in the order they ran: each field found, each
        pulse and each restart of the read current, beside the stage's moves and the lock-in reads."""
        h = self.make_switch(states=states, **kwargs)
        panel = h.panel
        for name, entry in (("_rte_scan_reach_field", lambda supply, target, *rest: ("field", target)),
                            ("_rte_switch_pulse", lambda pulse_ma, pulse: ("pulse", pulse_ma, round(pulse["width_s"] * 1e6, 6))),
                            ("_rte_switch_read_on", lambda settings: ("read on",))):
            def traced(*args, real=getattr(panel, name), entry=entry):
                h.log.append((*entry(*args), threading.get_ident()))
                return real(*args)
            setattr(panel, name, traced)
        return h

    @staticmethod
    def steps(h):
        return [entry[:-1] if entry[0] in ("field", "pulse", "read on") else entry[:3] if entry[0] == "stage" else entry[:2]
                for entry in h.log if entry[0] in ("field", "pulse", "read on", "lockins") or entry[:2] == ("stage", "move")]

    def test_each_state_is_written_then_read_at_zero_field(self):
        """User, 2026-11-28: "can you change the switch scan mode to set the state 1, 2, 3, 4... like MS_four
        state? the each state can contain settings like stage angle, field, pulse mA, pulse us, the readout
        current remains the value in the setting."  Chosen from the questions: every state is read at 0 G as
        MS-fourState reads, and the states run in their order, times Cycles."""
        h = self.make_states([("0", "100", "-2", "30"), ("90", "-50", "2", "50"), ("90", "0", "0", "30")], cycles="2")
        h.draw.reset_mock()         # the harness drew SHHV's Angle axes while it set the page up
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV scan")
        self.assertIn("Switch scan: 3 states in their order, 2 cycle(s).\n\n"
                      "1: stage 0°, +100 G, -2 mA, 30 µs\n2: stage 90°, -50 G, +2 mA, 50 µs\n3: stage 90°, +0 G, +0 mA, 30 µs\n\n", question)
        self.assertIn("Each state: the read current off; the stage to the state's angle; the field to the state's; one write of "
                      "1 pulse(s) at the state's current and width", question)
        self.assertIn("the field back to 0 G; then the read current on again, 0.5 mA RMS at 317.3 Hz", question)
        self.assertIn("3 states x 2 cycle(s) x 1 harmonic pass(es) = 6 points.", question)
        self.assertIn("Largest pulse 2 mA (30 µs).", question)
        self.assertIn("always at 0 G with the read current off. Can the wires follow?", question)
        # One state: the stage at 0 G, the field, the pulse, 0 G again, the read current, the read.  A state
        # written at 0 G leaves the field where it is, and 0 mA sends no pulse.
        cycle = [("stage", "move", 0.0), ("field", 100.0), ("pulse", -2.0, 30.0), ("field", 0.0), ("read on",), ("lockins", "read"),
                 ("stage", "move", 90.0), ("field", -50.0), ("pulse", 2.0, 50.0), ("field", 0.0), ("read on",), ("lockins", "read"),
                 ("stage", "move", 90.0), ("pulse", 0.0, 30.0), ("read on",), ("lockins", "read")]
        first = [("lockins", "first") if index == 5 else step for index, step in enumerate(cycle)]
        self.assertEqual(self.steps(h), [("field", 0.0)] + first + cycle)
        # The read current is off before the stage turns, a field changes or a pulse goes out.
        on = False
        for entry in h.log:
            if entry[:2] in (("6221", "on"), ("read on",)) or entry[0] == "read on":
                on = True
            elif entry[:2] == ("6221", "off"):
                on = False
            elif entry[0] in ("field", "pulse") or entry[:2] == ("stage", "move"):
                self.assertFalse(on, entry)
        rows = self.rows(h)
        self.assertEqual([(r["loop"], r["point"], r["state"]) for r in rows],
                         [(str(loop), str(state), str(state)) for loop in (1, 2) for state in (1, 2, 3)])
        self.assertEqual([(r["write_target_field_g"], float(r["pulse_current_ma"]), float(r["pulse_width_s"]), r["stage_target_deg"])
                          for r in rows[:3]],
                         [("100.0", -2.0, 3e-5, "0.0"), ("-50.0", 2.0, 5e-5, "90.0"), ("0.0", 0.0, 3e-5, "90.0")])
        self.assertEqual({(r["module"], r["scan_mode"], r["outer_target_field_g"], r["outer_field_index"], r["pulse_count"]) for r in rows},
                         {("SHHV", "Switch", "0.0", "1", "1")})
        self.assertEqual([r["pulse_in_compliance"] for r in rows[:3]], ["False", "False", "no pulse"])
        for r in rows:
            # Read at 0 G; written at the state's field, which the row keeps as the LS475 read it.
            self.assertAlmostEqual(float(r["measured_field_g"]), 0.0, delta=2.0)
            if r["state"] == "3":
                self.assertEqual((r["write_field_g"], r["write_current_a"]), ("", ""))
            else:
                self.assertAlmostEqual(float(r["write_field_g"]), float(r["write_target_field_g"]), delta=2.0)
                self.assertAlmostEqual(float(r["write_current_a"]), float(r["write_target_field_g"]) / 100.0, delta=0.021)
            self.assertAlmostEqual(float(r["stage_angle_deg"]), float(r["stage_target_deg"]), delta=0.01)
            self.assertAlmostEqual(float(r["sr830_8_x_over_i_ohm"]), float(r["sr830_8_x_v"]) / 0.5e-3)
            self.assertEqual(r["6221_current_rms_ma"], "0.5")
            # Each reading follows the read current's restart: 5 x the
            # slowest lock-in's time constant, then Settle s (0 here).
            self.assertGreater(float(r["slowest_lockin_tc_s"]), 0)
            self.assertAlmostEqual(float(r["effective_settle_s"]), 5.0 * float(r["slowest_lockin_tc_s"]))
        self.assertEqual(app.SWITCH_READ_SETTLE_TAUS, 5.0)
        self.assertIn("(5 x ", question)
        self.assertIn("then Settle s 0 s) of settling", question)
        # Four trains (0 mA sends none), each the CIDWM pulse at its state's width: a 50 % square of period
        # 2 x width, amplitude |I|/2, offset I/2, one cycle.
        self.assertEqual(len(h.fake.trains), 4)
        for train, (current_ma, width_s) in zip(h.fake.trains, ((-2.0, 30e-6), (2.0, 50e-6)) * 2):
            frequency = 1.0 / (2.0 * width_s)
            self.assertAlmostEqual(train["SOUR:WAVE:AMPL"], abs(current_ma) * 1e-3 / 2.0)
            self.assertAlmostEqual(train["SOUR:WAVE:OFFS"], current_ma * 1e-3 / 2.0)
            self.assertAlmostEqual(train["SOUR:WAVE:FREQ"], frequency, delta=frequency * 1e-9)
            self.assertEqual((train["SOUR:WAVE:DUR:CYCL"], train["CURR:COMP"]),
                             (1.0, float(h.configured[0]["compliance_v"])))
        # The scan's one full set-up (the 6221's reset) comes before any
        # pulse; after each pulse the read current comes back without it.
        sent = h.fake.sent
        self.assertEqual(sent.count("FULL SET-UP"), 1)
        self.assertEqual(sent[0], "FULL SET-UP")
        self.assertNotIn("*RST", sent)
        # One pulse's commands, in order, and nothing armed before every
        # setting is written.
        first = sent.index("SOUR:WAVE:ARM")
        self.assertEqual(sent[first - 1], "SOUR:WAVE:DUR:CYCL 1")
        self.assertEqual(sent[first:first + 3], ["SOUR:WAVE:ARM", "OUTP ON", "SOUR:WAVE:INIT"])
        self.assertEqual(sent[sent.index("SOUR:WAVE:FUNC SQU") - 2:sent.index("SOUR:WAVE:FUNC SQU") + 2],
                         ["SOUR:WAVE:ABOR", f"CURR:COMP {float(h.configured[0]['compliance_v']):.12g}",
                          "SOUR:WAVE:FUNC SQU", "SOUR:WAVE:DCYC 50"])
        # The read current after it: MS-fourState's sine, armed with the
        # output off, on at INIT; six times, once before every reading.
        sine = sent.index("SOUR:WAVE:FUNC SIN")
        self.assertEqual(sent[sine - 2:sine + 14], [
            "SOUR:WAVE:ABOR", f"CURR:COMP {float(h.configured[0]['compliance_v']):.12g}", "SOUR:WAVE:FUNC SIN",
            "SOUR:WAVE:FREQ 317.3", f"SOUR:WAVE:AMPL {2 ** 0.5 * 0.5e-3:.12e}", "SOUR:WAVE:OFFS 0",
            "SOUR:WAVE:RANG BEST", "SOUR:WAVE:EXTR OFF", "SOUR:WAVE:DUR:CYCL INF",
            f"SOUR:WAVE:PMAR {app.NONLOCAL_MARKER_PHASE_DEG:g}", f"SOUR:WAVE:PMAR:OLIN {app.NONLOCAL_MARKER_LINE}",
            "SOUR:WAVE:PMAR:STAT ON", "OUTP OFF", "SOUR:WAVE:ABOR", "SOUR:WAVE:ARM", "SOUR:WAVE:INIT"])
        self.assertEqual(len(h.fake.sines), 6, "the read current on again before every reading")
        self.assertEqual(h.fake.output, 0, "off at the end")
        # The acquisition line follows the read current (user, 2026-11-24:
        # "fix the 6221 output OFF line too"): ON before each reading, OFF
        # for each pulse and at the end.
        shown = [text for text in status_lines(h) if text.startswith("Transport acquisition: 6221")]
        self.assertEqual(shown.count("Transport acquisition: 6221 ON, 0.5 mA RMS at 317.3 Hz (read current)"), 6)
        self.assertIn("OFF", shown[-1])
        # A pulse is never sent with the read current on: each train's
        # commands start after an output read back off.
        for index, command in enumerate(sent):
            if command == "SOUR:WAVE:FUNC SQU":
                before = sent[:index]
                last_sine = max((i for i, c in enumerate(before) if c in ("SOUR:WAVE:INIT", "FULL SET-UP")), default=-1)
                self.assertIn("SOUR:WAVE:ABOR", before[last_sine + 1:])
        # Everything on the page's worker.
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})
        status = panel.ppms_field_scan_status_var.get()
        self.assertTrue(status.startswith("Completed; ") and status.endswith("; stage at +90.000°"), status)
        self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED)
        events = ete.RunLogBase.events(h)
        prepared = events[0]
        self.assertEqual((prepared["mode"], prepared["plan"]["unit"], prepared["plan"]["points"], prepared["plan"]["loops"]),
                         ("Switch", "state", 6, 2))
        self.assertEqual(prepared["pulse"]["states"], [
            dict(state=1, stage_angle_deg=0.0, field_g=100.0, pulse_current_ma=-2.0, pulse_width_s=3e-5),
            dict(state=2, stage_angle_deg=90.0, field_g=-50.0, pulse_current_ma=2.0, pulse_width_s=5e-5),
            dict(state=3, stage_angle_deg=90.0, field_g=0.0, pulse_current_ma=0.0, pulse_width_s=3e-5)])
        self.assertEqual((prepared["pulse"]["count"], prepared["pulse"]["read_field_g"], prepared["outer"]["values"]), (1, 0.0, [0.0]))
        self.assertIn("field back to the read field, read current on again, settle, read", prepared["pulse"]["order"])
        pulses = [e for e in events if e["event"] == "pulse"]
        self.assertEqual([(e["loop"], e["state"], e["pulse_current_ma"]) for e in pulses],
                         [(loop, state, value) for loop in (1, 2) for state, value in ((1, -2.0), (2, 2.0), (3, 0.0))])
        # The pulse is in the log when it is sent, before the field goes back (review, 2026-11-28).
        kinds = [(e["event"], e.get("purpose", "")) for e in events if e["event"] in ("pulse", "field_programmed", "state_written", "point_saved")]
        self.assertEqual(kinds[1:6], [("field_programmed", "write"), ("pulse", ""), ("field_programmed", "read"), ("state_written", ""), ("point_saved", "")])
        fields = [e for e in events if e["event"] == "field_programmed"]
        self.assertEqual([(e.get("purpose", "start"), e["target_field_g"]) for e in fields],
                         [("start", 0.0)] + [("write", 100.0), ("read", 0.0), ("write", -50.0), ("read", 0.0)] * 2)
        self.assertEqual([e["target_deg"] for e in events if e["event"] == "stage_move"], [0.0, 90.0, 90.0] * 2)
        self.assertEqual(events[-1]["event"], "run_finished")
        # The plots: X and Y in volts against the state's number, the cycles side by side (user, 2026-11-28:
        # "for switch cycle, the first row should have 1,2,3,4,5,6,1,2,3,4,5,6... this type x-axis").
        state_calls = [call for call in h.draw.call_args_list if call.args[2] == "State"]
        self.assertEqual({call.args[3] for call in state_calls}, {"X voltage", "Y voltage"})
        self.assertEqual({(call.kwargs["x_range"], call.kwargs["x_cycle"]) for call in state_calls}, {((0.5, 6.5), 3)})
        canvases = h.panel.ppms_harmonic_canvases
        last_x = [call for call in state_calls if call.args[0] is canvases[(1, "x")]][-1]
        saved = h.panel.ppms_field_scan_rows
        self.assertEqual(len(saved), 6)
        self.assertEqual([[x for x, _v in points] for points in last_x.args[1].values()], [[1, 2, 3, 4, 5, 6]], "the cycles, one after the other on one line")
        self.assertFalse([call for call in state_calls if call.args[0] is canvases[(1, "theta")]])
        # X and Y against time: every sample of each reading, a segment per
        # reading (user, 2026-11-22: "it should show the voltage in the
        # period not a single point"), on the time of the scan.
        for channel, sign in (("x", 1), ("y", -1)):
            timed = [call for call in h.draw.call_args_list if call.args[0] is h.panel.rte_time_canvases[channel]][-1]
            self.assertEqual(timed.args[2:4], ("Time (s)", f"{channel.upper()} voltage"))
            series = timed.args[1]
            self.assertEqual(sorted(series), sorted(f"SR830-1 #{index}" for index in range(1, 7)))
            for points in series.values():
                self.assertEqual([v for _t, v in points], [sign * 1e-6, sign * 2e-6, sign * 3e-6])
        # And in the run folder's trace CSV, with each reading's means.
        trace = h.panel.rte_switch_trace_path
        self.assertEqual(trace.name, h.panel.rte_recorder.csv_path.stem + "_trace.csv") if h.panel.__dict__.get(
            "rte_recorder") else self.assertTrue(trace.name.endswith("_trace.csv"))
        # Since 2026-11-28 with the byte-order mark the live CSV has: the recorder writes both.
        self.assertTrue(trace.read_bytes().startswith(b"\xef\xbb\xbf"))
        with trace.open(encoding="utf-8-sig", newline="") as handle:
            lines = list(app.csv.reader(handle))
        self.assertEqual(lines[0], ["time_s", "quantity", "value", "unit", "point"])
        self.assertEqual(sum(1 for line in lines if line[1] == "SR830 #8 X"), 18)
        self.assertEqual(sum(1 for line in lines if line[1] == "SR830 #8 mean X"), 6)
        self.assertEqual(lines[1][4], "#1 -2 mA")

    def test_states_without_angles_leave_the_stage_alone(self):
        """With every Angle box empty the scan is the Switch scan as it was for the stage: not moved, and
        not needed (it may be disconnected)."""
        h = self.make_states([("", "100", "-2", "30"), ("", "100", "2", "30")])
        h.panel.rte_controllers["newmark"] = types.SimpleNamespace(connected=False, motion_may_run=False, label="Newmark stage")
        self.start(h)
        h.showerror.assert_not_called()
        question = h.askyesno.call_args.args[1]
        self.assertIn("1: +100 G, -2 mA, 30 µs\n2: +100 G, +2 mA, 30 µs", question)
        self.assertIn("The stage is not moved: no state has an angle.", question)
        self.assertNotIn("the stage to the state's angle", question)
        self.assertEqual(self.steps(h), [("field", 0.0), ("field", 100.0), ("pulse", -2.0, 30.0), ("field", 0.0), ("read on",), ("lockins", "first"),
                                         ("field", 100.0), ("pulse", 2.0, 30.0), ("field", 0.0), ("read on",), ("lockins", "read")])
        rows = self.rows(h)
        self.assertEqual([r["state"] for r in rows], ["1", "2"])
        self.assertNotIn("stage_angle_deg", rows[0])
        self.assertEqual(h.panel.ppms_field_scan_status_var.get(), "Completed; KEPCO and 6221 zeroed")

    def test_the_table_is_checked_before_anything_is_sent(self):
        for states, count, message in (
                ([("", "100", "2", "30")], "0", "States: type how many states the scan has, a whole number from 1 to 12"),
                ([("", "100", "2", "30")], "13", "States: type how many states the scan has"),
                ([("", "", "2", "30")], "1", "State 1, Field G: type a number"),
                ([("", "100", "2", "30"), ("", "100", "x", "30")], "2", 'State 2, Pulse mA: "x" is not a number'),
                ([("0", "100", "2", "30"), ("", "100", "2", "30")], "2", "Angle °: state 2 has no angle. Type the stage angle of every state, or empty every Angle ° box"),
                ([("361", "100", "2", "30")], "1", "State 1: stage angles must stay within +/-360° of the stage zero (the sample wires); 361° is outside"),
                ([("", "100", "2", "1")], "1", "State 1: 6221 pulse width must be between"),
                # The page's cap on a typed field (review, 2026-11-28: 50000 typed for 500 must not start).
                ([("", "50000", "2", "30")], "1", "State 1: fields must stay within +/-7300 G (7300 Oe); 50000 G is outside"),
                ([("", "100", "200", "30")], "1", "6221 pulse currents must stay within +/-105 mA")):
            with self.subTest(message=message):
                h = self.make_states(states)
                h.panel.rte_states_count.set(count)
                self.start(h)
                self.assertEqual(h.showerror.call_args.args[0], "SHHV scan parameters")
                self.assertIn(message, h.showerror.call_args.args[1])
                h.askyesno.assert_not_called()
                self.assertEqual((h.fake.sent, h.log), ([], []))
        # A state with an angle needs the motor.
        h = self.make_states([("10", "100", "2", "30")])
        h.panel.rte_controllers["newmark"] = types.SimpleNamespace(connected=False, motion_may_run=False, label="Newmark stage")
        self.start(h)
        self.assertIn("for the angles of the states (or empty every Angle ° box: the stage is then not moved)", h.showerror.call_args.args[1])
        self.assertEqual((h.fake.sent, h.log), ([], []))

    def test_a_pulse_that_went_out_is_in_the_log_whatever_happens_on_the_way_back(self):
        """Review, 2026-11-28: a Stop, or a field that fails, between the pulse and the return to 0 G left a
        delivered pulse out of the run log.  It is logged the moment it is sent."""
        for ending in ("stop", "field"):
            with self.subTest(ending=ending):
                h = self.make_states([("", "100", "2", "30"), ("", "100", "-2", "30")])
                panel = h.panel
                reach, sent = panel._rte_scan_reach_field, []

                def back(supply, target, *rest, reach=reach, sent=sent, ending=ending, panel=panel, h=h):
                    if target == 0.0 and len(h.fake.trains) == 1 and not sent:
                        sent.append(True)
                        if ending == "stop":
                            panel.ppms_field_scan_stop_event.set()
                        else:
                            raise app.MagnetFieldError("the field did not answer")
                    return reach(supply, target, *rest)
                panel._rte_scan_reach_field = back
                self.start(h)
                self.assertEqual(self.rows(h), [], "no state was read")
                self.assertEqual(len(h.fake.trains), 1)
                pulses = [e for e in ete.RunLogBase.events(h) if e["event"] == "pulse"]
                self.assertEqual([(e["state"], e["pulse_current_ma"], e["pulse_in_compliance"]) for e in pulses], [(1, 2.0, False)])
                status = panel.ppms_field_scan_status_var.get()
                self.assertTrue(status.startswith("Stopped; " if ending == "stop" else "Failed: the field did not answer"), status)
                self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED if ending == "stop" else self.names(h, "6221", "kepco")[-3:])
                self.assertIn(("kepco", "force_off"), self.names(h, "kepco"))
                self.assertEqual(h.fake.output, 0)

    def test_stop_stage_holds_the_next_pulse(self):
        """Review, 2026-11-28: Stop stage pressed while a state's field is being set ended the scan only at the
        next state's move, after that state's pulse.  With angles, the pulse is not sent either."""
        h = self.make_states([("0", "100", "2", "30"), ("90", "100", "-2", "30")])
        panel = h.panel
        reach = panel._rte_scan_reach_field

        def during(supply, target, *rest):
            if target == 100.0:
                panel.rte_stage_stop_event.set()
            return reach(supply, target, *rest)
        panel._rte_scan_reach_field = during
        self.start(h)
        self.assertEqual((h.fake.trains, self.rows(h)), ([], []))
        self.assertIn("stopped before the pulse of state 1: Stop stage was pressed", " ".join(str(e) for e in ete.RunLogBase.events(h)))
        self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED)

    def test_a_stage_or_field_that_fails_in_a_state_ends_the_scan_as_in_the_other_scans(self):
        h = self.make_states([("0", "100", "2", "30"), ("90", "100", "-2", "30")])
        h.move_hooks[90.0] = lambda: (_ for _ in ()).throw(app.NewmarkStageError("the stage did not answer"))
        self.start(h)
        self.assertIn("the stage did not answer", h.showerror.call_args.args[1])
        self.assertEqual([r["state"] for r in self.rows(h)], ["1"])
        self.assertEqual(len(h.fake.trains), 1, "state 2's pulse was not sent")
        self.assertTrue([e for e in ete.RunLogBase.events(h) if e["event"] == "stage_failure"])
        self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED)

    def test_switch_loop_takes_start_end_step_and_loops_like_field(self):
        """User, 2026-11-26: "add a switch-loop in the scan mode below switch
        which input start, end, step, loops like field": the Switch scan
        with its pulse currents from Start / End / Step mA, Loops and Round
        trip instead of the typed list."""
        h = self.make_switch(fields="100")
        panel = h.panel
        modes = list(app.RTE_SCAN_MODES)
        self.assertEqual(modes[modes.index("Switch") + 1], "Switch-loop")
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Switch-loop")
            panel._rte_mode_changed()
        # 22 to -22 mA in 2 mA steps at 200 G in this program (user's figure, 2026-11-27); 14, -14, 2 at -12 G
        # in the main program.
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["22", "-22", "2"])
        self.assertIs(panel.rte_round_trip.get(), True)
        self.assertEqual(panel.rte_scan_units.get(), "6221 pulse mA")
        self.assertEqual(panel.rte_scan_note.get(), "Switch-loop: pulse mA; outer: field G")
        self.assertEqual(panel.rte_outer_label.get(), "Outer field G:")
        self.assertEqual(panel.rte_outer_ranges["Switch-loop"][0].get(), "200")
        self.assertEqual(panel.ppms_plot_axis, "pulse")
        self.assertEqual([v for _l, _p, v in app.rte_scan_plan("Switch-loop", "14", "-14", "2", 1, True)],
                         [14.0 - 2 * i for i in range(15)] + [-12.0 + 2 * i for i in range(14)])
        panel.ppms_simple_range[0].set("-2")
        panel.ppms_simple_range[1].set("2")
        panel.ppms_simple_range[2].set("2")
        panel.ppms_field_scan_loop_var.set("2")
        panel.ppms_field_scan_stable_var.set("0")
        panel.rte_outer_ranges["Switch-loop"][0].set("100")
        self.start(h)
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertTrue(question.startswith("Switch-loop scan."))
        self.assertIn("6221 pulse current, the INNER loop: 5 pulses a loop from -2 mA to +2 mA (step 2 mA and back), "
                      "2 loop(s). Largest pulse 2 mA.", question)
        self.assertIn("1 fields x 10 pulses x 1 harmonic pass(es) = 10 points.", question)
        rows = self.rows(h)
        self.assertEqual([(r["scan_mode"], r["loop"], float(r["pulse_current_ma"])) for r in rows],
                         [("Switch-loop", loop, v) for loop in ("1", "2") for v in (-2.0, 0.0, 2.0, 0.0, -2.0)])
        self.assertEqual(len(h.fake.trains), 6, "0 mA sends no pulse")
        prepared = ete.RunLogBase.events(h)[0]
        self.assertEqual({k: prepared["plan"][k] for k in ("start", "end", "step", "unit", "loops", "round_trip")},
                         {"start": "-2", "end": "2", "step": "2", "unit": "mA (6221 pulse)", "loops": 2, "round_trip": True})
        self.assertEqual(prepared["outer"]["values"], [100.0])
        self.assertTrue(panel.ppms_field_scan_status_var.get().startswith("Completed"))
        # A pulse beyond the 6221's limit is refused before anything is sent.
        with self.assertRaisesRegex(ValueError, r"6221 pulse currents must stay within \+/-105 mA; 106 mA is outside"):
            app.rte_scan_plan("Switch-loop", "0", "106", "106", 1, False)

    def test_x_and_y_vs_time_follow_the_window_as_it_is_read(self):
        """User, 2026-11-24: "The X and Y signals versus time should be
        displayed and updated in real time here."  While a Switch scan runs,
        a 1 s timer draws the readings of the Acquire window being read
        beside the saved ones; nothing new, nothing redrawn; the scan over,
        the timer stops."""
        h = self.make_switch()
        panel = h.panel
        started = app.time.monotonic() - 300.0
        panel.ppms_field_scan_running, panel.ppms_active_scan_mode = True, "Switch"
        panel.ppms_field_scan_started_at = started
        panel.rte_switch_traces = [dict(index=1, pulse_ma=-2.0, harmonics={"8": 1}, times=[0.0, 1.0],
                                        values=[{"sr830_8_x_v": 1e-6, "sr830_8_y_v": -1e-6}] * 2)]
        panel.rte_switch_live = dict(index=2, harmonics={"8": 1})
        panel.ppms_sample_trace = [(started + 305.0, {"sr830_8_x_v": 5e-6, "sr830_8_y_v": -5e-6})]
        h.root.pending.clear()

        def drawn(channel):
            calls = [c for c in h.draw.call_args_list if c.args[0] is panel.rte_time_canvases[channel]]
            return calls[-1].args[1] if calls else None
        h.draw.reset_mock()
        panel._rte_live_time_tick()
        for channel, sign in (("x", 1), ("y", -1)):
            series = drawn(channel)
            self.assertEqual(sorted(series), ["SR830-1 #1", "SR830-1 #2"])
            (at, value), = series["SR830-1 #2"]
            self.assertAlmostEqual(at, 305.0, places=6)
            self.assertEqual(value, sign * 5e-6)
        self.assertEqual([delay for delay, _callback in h.root.pending], [1000])
        panel.ppms_sample_trace.append((started + 305.4, {"sr830_8_x_v": 6e-6, "sr830_8_y_v": -6e-6}))
        h.draw.reset_mock()
        panel._rte_live_time_tick()
        self.assertEqual([v for _at, v in drawn("x")["SR830-1 #2"]], [5e-6, 6e-6])
        h.draw.reset_mock()
        panel._rte_live_time_tick()
        self.assertIsNone(drawn("x"), "no new reading, no redraw")
        panel.ppms_field_scan_running = False
        h.root.pending.clear()
        panel._rte_live_time_tick()
        self.assertEqual(h.root.pending, [])
        # A scan's start sets the timer going.
        h = self.make_switch(fields="100", span=("2", "2", "1"))
        self.start(h)
        self.assertIn(h.panel._rte_live_time_tick, [callback for _delay, callback in h.root.pending])

    def test_the_time_plot_never_keeps_a_live_trace_that_finishes_mid_redraw(self):
        """Speed pass, 2026-11-25: finished traces' points are kept between
        redraws; review: the worker may append the live trace while the x
        plot is drawn, and its partial points must not be kept for the y
        plot or later redraws."""
        h = self.make_switch()
        panel = h.panel
        started = app.time.monotonic() - 300.0
        panel.ppms_field_scan_running, panel.ppms_active_scan_mode = True, "Switch"
        panel.ppms_field_scan_started_at = started
        first = dict(index=1, pulse_ma=-2.0, harmonics={"8": 1}, times=[0.0, 1.0],
                     values=[{"sr830_8_x_v": 1e-6, "sr830_8_y_v": -1e-6}] * 2)
        panel.rte_switch_traces = [first]
        panel.rte_switch_live = dict(index=2, harmonics={"8": 1})
        panel.ppms_sample_trace = [(started + 305.0, {"sr830_8_x_v": 5e-6, "sr830_8_y_v": -5e-6})]
        whole = dict(index=2, pulse_ma=-4.0, harmonics={"8": 1}, times=[5.0, 6.0],
                     values=[{"sr830_8_x_v": 5e-6, "sr830_8_y_v": -5e-6}, {"sr830_8_x_v": 7e-6, "sr830_8_y_v": -7e-6}])
        def finish(canvas, *args, **kwargs):
            if canvas is panel.rte_time_canvases["x"] and len(panel.rte_switch_traces) == 1:
                panel.rte_switch_traces.append(whole)      # the worker, during the x plot
        h.draw.side_effect = finish
        panel._redraw_switch_time_plot()
        panel.ppms_field_scan_running, panel.ppms_sample_trace = False, None
        h.draw.reset_mock()
        panel._redraw_switch_time_plot()
        for call in h.draw.call_args_list:
            self.assertEqual(len(call.args[1]["SR830-1 #2"]), 2, "the whole trace, not the live part")
        self.assertEqual(len(h.draw.call_args_list), 2)

    def test_apply_pulse_sends_one_pulse_by_hand(self):
        """User, 2026-11-22: "add another pulse apply below here RMS
        continuous settings": the settings' Apply pulse sends the "6221
        Pulse mA" current once, with the Pulse µs / Pulses boxes and the
        Compliance V box, as the Switch scan sends each pulse; the 6221 is
        off after it."""
        h = self.make_switch()
        panel = h.panel
        # 10 mA at start-up (user, 2026-11-22: "default pulse 10 mA pls.").
        self.assertEqual(panel.rte_pulse_current_ma.get(), "10")
        self.assertEqual(panel.ppms_transport_compliance_var.get(), "100")
        # 0 mA sends nothing, and says so.
        panel.rte_pulse_current_ma.set("0")
        panel._rte_apply_pulse()
        self.pump(h)
        self.assertEqual(h.showerror.call_args.args[0], "SHHV pulse")
        self.assertIn('Type the pulse current in the "Pulse mA" box beside Apply pulse', h.showerror.call_args.args[1])
        h.askyesno.assert_not_called()
        self.assertEqual(h.fake.sent, [])
        # +5 mA, 50 µs, once.
        h.showerror.reset_mock()
        panel.rte_pulse_current_ma.set("5")
        panel.rte_pulse_width_us.set("50")
        panel._rte_apply_pulse()
        self.pump(h)
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV pulse")
        self.assertIn("Send 1 pulse(s) of +5 mA, 50 µs each, from the 6221 now (compliance 100 V)?", question)
        self.assertIn("a current set with Set 6221 ends", question)
        self.assertEqual(len(h.fake.trains), 1)
        train = h.fake.trains[0]
        self.assertEqual((train["SOUR:WAVE:AMPL"], train["SOUR:WAVE:OFFS"], train["SOUR:WAVE:FREQ"],
                          train["CURR:COMP"], train["SOUR:WAVE:DUR:CYCL"]), (2.5e-3, 2.5e-3, 1e4, 100.0, 1.0))
        arm = h.fake.sent.index("SOUR:WAVE:ARM")
        self.assertEqual(h.fake.sent[arm:arm + 3], ["SOUR:WAVE:ARM", "OUTP ON", "SOUR:WAVE:INIT"])
        self.assertNotIn("SOUR:WAVE:FUNC SIN", h.fake.sent, "no read current after it")
        self.assertNotIn("*RST", h.fake.sent)
        self.assertEqual(h.fake.output, 0)
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Pulse +5 mA x 1 (50 µs) sent; 6221 off")
        self.assertIn("SHHV: Pulse +5 mA x 1 (50 µs) sent; 6221 off", h.logged)
        self.assertIs(panel.ppms_environment_busy, False)
        self.assertEqual(self.names(h, "6221")[-2:], [("6221", "off"), ("6221", "OUTP?")], "off, read back")
        # A pulse that reaches the compliance says so.
        h.fake.compliance_after_train = True
        panel.rte_pulse_current_ma.set("-5")
        panel._rte_apply_pulse()
        self.pump(h)
        self.assertEqual(panel.ppms_field_scan_status_var.get(),
                         "Pulse -5 mA x 1 (50 µs) sent; the 6221 REACHED COMPLIANCE (100 V); 6221 off")
        self.assertEqual(h.fake.trains[-1]["SOUR:WAVE:OFFS"], -2.5e-3)

    def test_apply_pulse_that_fails_after_the_start_says_the_pulse_went_out(self):
        """Review, 2026-11-22: an error after SOUR:WAVE:INIT was shown as a
        plain failure, though the pulse had been delivered."""
        h = self.make_switch()
        panel = h.panel
        panel.rte_pulse_current_ma.set("5")
        real_query = panel._ppms_query_numbers

        def query(key, command, count):
            if key == "6221" and command == "OUTP?" and h.fake.trains and not h.fake.sent[-1].startswith("OUTP OFF"):
                raise RuntimeError("VI_ERROR_TMO")
            return real_query(key, command, count)
        panel._ppms_query_numbers = query
        panel._rte_apply_pulse()
        self.pump(h)
        message = h.showerror.call_args.args[1]
        self.assertIn("The +5 mA pulse was started and has most likely been delivered, but its end was not "
                      "confirmed: VI_ERROR_TMO. The 6221 has been switched off.", message)
        self.assertEqual(len(h.fake.trains), 1)
        self.assertEqual(h.fake.output, 0)
        self.assertIs(panel.ppms_environment_busy, False)
        # A failure before the start is the plain one.
        h2 = self.make_switch()
        h2.panel.rte_pulse_current_ma.set("5")
        h2.fake.readback["SOUR:WAVE:AMPL"] = 9e-3
        h2.panel._rte_apply_pulse()
        self.pump(h2)
        self.assertIn("6221 pulse amplitude readback mismatch", h2.showerror.call_args.args[1])
        self.assertNotIn("most likely been delivered", h2.showerror.call_args.args[1])
        self.assertEqual(h2.fake.trains, [])

    def test_apply_pulse_is_refused_as_a_scan_pulse_is(self):
        h = self.make_switch()
        panel = h.panel
        for current, width, pulses, message in (("200", "30", "1", "6221 current exceeds the software limit ±105 mA"),
                                                ("5", "x", "1", "Pulse mA, Pulse µs and Compliance V must be numbers"),
                                                ("5", "30", "0", "6221 pulse count must be between 1 and")):
            with self.subTest(message=message):
                panel.rte_pulse_current_ma.set(current)
                panel.rte_pulse_width_us.set(width)
                panel.rte_pulse_count.set(pulses)
                panel._rte_apply_pulse()
                self.pump(h)
                self.assertIn(message, h.showerror.call_args.args[1])
        # No to the question, the safety tick off, the 6221 not connected: nothing sent.
        panel.rte_pulse_current_ma.set("5")
        panel.rte_pulse_width_us.set("30")
        panel.rte_pulse_count.set("1")
        h.askyesno.return_value = False
        panel._rte_apply_pulse()
        self.pump(h)
        h.askyesno.return_value = True
        panel.ppms_control_safety_var.set(False)
        panel._rte_apply_pulse()
        self.pump(h)
        self.assertIn("Tick the SHHV rack safety confirmation first", h.showerror.call_args.args[1])
        panel.ppms_control_safety_var.set(True)
        panel.ppms_instrument_controllers["6221"].connected = False
        panel._rte_apply_pulse()
        self.pump(h)
        self.assertIn("Connect the Keithley 6221 first", h.showerror.call_args.args[1])
        self.assertEqual(h.fake.sent, [])
        self.assertEqual(h.fake.trains, [])

    def test_a_setting_that_does_not_read_back_arms_nothing(self):
        h = self.make_switch(fields="100", span=("2", "2", "1"))
        h.fake.readback["SOUR:WAVE:AMPL"] = 5e-3
        self.start(h)
        self.assertIn("6221 pulse amplitude readback mismatch: requested 0.001, read 0.005",
                      h.showerror.call_args.args[1])
        self.assertNotIn("SOUR:WAVE:ARM", h.fake.sent)
        self.assertNotIn("OUTP ON", h.fake.sent)
        self.assertEqual(h.fake.trains, [])
        self.assertTrue(h.panel.ppms_field_scan_status_var.get().startswith("Failed: 6221 pulse amplitude"),
                        h.panel.ppms_field_scan_status_var.get())
        # The end still zeroes the 6221 and the KEPCO.
        self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED)

    def test_compliance_during_a_pulse_is_saved_and_logged(self):
        h = self.make_switch(fields="100", span=("2", "2", "1"))
        h.fake.compliance_after_train = True
        self.start(h)
        h.showerror.assert_not_called()
        self.assertEqual([r["pulse_in_compliance"] for r in self.rows(h)], ["True", "True", "True"][:1])
        self.assertTrue([line for line in h.logged if "SHHV: the 6221 reached compliance" in line
                         and "+2 mA pulse" in line], h.logged)

    def test_a_read_current_in_compliance_stops_the_scan_naming_it(self):
        """Review, 2026-11-22: a real Switch scan ended "6221 hit compliance"
        at a reading; the read current's own compliance is now named, with
        the resistance it means, right after the read current is on again."""
        h = self.make_switch(fields="100", span=("2", "2", "1"))
        h.fake.read_in_compliance = True
        self.start(h)
        message = h.showerror.call_args.args[1]
        self.assertIn("The 6221 is in compliance with the read current on (0.5 mA RMS, 0.707 mA peak, "
                      "Compliance V 100 V): the sample and leads are above about 1.41e+05 Ω.", message)
        self.assertEqual(self.rows(h), [], "no point read")
        self.assertEqual(len(h.fake.trains), 1, "the pulse went out first")
        self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED)

    def test_start_refuses_a_pulse_beyond_the_limits_before_anything_is_sent(self):
        for span, width, pulses, message in (
                (("0", "200", "100"), "30", "1", "6221 pulse currents must stay within +/-105 mA"),
                (("-2", "2", "2"), "x", "1", 'State 1, Pulse µs: "x" is not a number'),
                (("-2", "2", "2"), "30", "0", "State 1: 6221 pulse count must be between 1 and"),
                (("-2", "2", "2"), "30", "1.5", "State 1: 6221 pulse count must be an integer")):
            with self.subTest(message=message):
                h = self.make_switch(span=span, width=width, pulses=pulses)
                self.start(h)
                self.assertEqual(h.showerror.call_args.args[0], "SHHV scan parameters")
                self.assertIn(message, h.showerror.call_args.args[1])
                h.askyesno.assert_not_called()
                self.assertEqual(h.fake.sent, [])
                self.assertEqual(h.log, [])

    def test_a_stop_during_the_loop_ends_it_zeroed(self):
        h = self.make_switch(fields="100", span=("-2", "2", "1"))
        panel = h.panel
        real = panel._rte_switch_pulse

        def pulse(pulse_ma, settings):
            if pulse_ma == 0:
                panel.ppms_field_scan_stop_event.set()
            return real(pulse_ma, settings)
        panel._rte_switch_pulse = pulse
        self.start(h)
        h.showerror.assert_not_called()
        self.assertEqual([float(r["pulse_current_ma"]) for r in self.rows(h)], [-2.0, -1.0])
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Stopped; KEPCO and 6221 zeroed")
        self.assertEqual(self.names(h, "6221", "kepco")[-3:], ete.ZEROED)


if __name__ == "__main__":
    unittest.main()
