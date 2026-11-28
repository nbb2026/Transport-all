"""The measurements of Transport_RT (user, 2026-11-27: "split SHHV and
Switch to two modes. also add modes named NLH, AHE, PHE. In the order: PHE,
AHE, NLH, SHHV, Switch pls. PHE-scan: angle+field, angle+current; AHE-scan:
field, field+angle, field+current; NLH-scan: current; SHHV-scan: angle+field,
angle+current; Switch-scan: switch, switch-loop, switch2. the others remain
the same. put scan on the left side and settings in the right side pls.").
Then "rename the switch to switch-OOP" (the tab; its scans keep their names)
and, with a figure of the page, "default settings use fig in switch mode in
RT": what the Switch-OOP tab starts with.

They are tabs of one page, so the instruments stay connected when the
measurement changes: the page's tab is the chosen measurement's, and choosing
another tab moves the page there and offers that measurement's scans.  Nothing
else follows the measurement: the settings, harmonics and scans are as before.
The saved rows and the run's settings name the measurement.

These tests use test_rte_angle_end_to_end's harness (stand-in widgets, no
window); test_rt_measurement_tabs.py builds the real window for the tabs."""
import json
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_rte_angle_end_to_end as ete
from test_ppms_motor_debug import app

setUpModule, tearDownModule = ete.setUpModule, ete.tearDownModule

MEASUREMENTS = {
    "PHE": ("Angle+Field", "Angle+Current"),
    "AHE": ("Field", "Field+Angle", "Field+Current"),
    "NLH": ("Current",),
    "SHHV": ("Angle+Field", "Angle+Current"),
    "Switch-OOP": ("Switch", "Switch-loop", "Switch2"),
    "Switch-IP": ("Switch", "Switch-loop", "Switch2"),
}


class TheTable(unittest.TestCase):
    def test_the_measurements_their_order_and_their_scans_are_the_users(self):
        self.assertEqual(dict(app.RTE_MEASUREMENTS), MEASUREMENTS)
        self.assertEqual(tuple(app.RTE_MEASUREMENTS), ("PHE", "AHE", "NLH", "SHHV", "Switch-OOP", "Switch-IP"))

    def test_every_scan_is_one_the_page_has(self):
        for name, scans in app.RTE_MEASUREMENTS.items():
            for scan in scans:
                self.assertIn(scan, app.RTE_SCAN_MODES, name)

    def test_the_program_starts_on_shhv_where_the_start_up_settings_belong(self):
        self.assertEqual(app.RTE_DEFAULT_MEASUREMENT, "SHHV")
        self.assertIn(app.RTE_DEFAULT_SCAN_MODE, app.RTE_MEASUREMENTS["SHHV"])


class ThePage(unittest.TestCase):
    def page(self):
        # The stand-in plots cannot be drawn on: what a scan change would redraw is left out.
        guard = patch.object(app.CombinedControlApp, "_draw_nonlocal_series")
        guard.start()
        self.addCleanup(guard.stop)
        return ete.build_page(kepco=False)

    @staticmethod
    def loop_in_oop(panel):
        """Switch-OOP with Switch-loop chosen in its list, as the user does: the tab opens on the Switch scan
        since 2026-11-28, and comes back on the scan it was left on."""
        panel.rte_set_measurement("Switch-OOP")
        panel.ppms_simple_mode.set("Switch-loop")
        panel._rte_mode_changed()

    def test_it_starts_on_shhv_with_shhvs_scans_and_the_start_up_scan(self):
        panel = self.page()
        self.assertEqual(panel.rte_measurement, "SHHV")
        self.assertEqual(tuple(panel.rte_scan_mode_combo.options["values"]), MEASUREMENTS["SHHV"])
        self.assertEqual(panel.ppms_simple_mode.get(), "Angle+Field")
        self.assertTrue(str(panel.ppms_plot_frame.options["text"]).startswith("SHHV: X, Y, phase vs"))

    def test_each_measurement_offers_its_scans_and_starts_on_its_first(self):
        """Switch-OOP opens on Switch, the scan of the user's figure of
        2026-11-28 (Switch-loop before); Switch-IP on Switch-loop."""
        panel = self.page()
        for name in ("Switch-OOP", "NLH", "AHE", "PHE", "SHHV"):
            self.assertTrue(panel.rte_set_measurement(name))
            self.assertEqual(panel.rte_measurement, name)
            self.assertEqual(tuple(panel.rte_scan_mode_combo.options["values"]), MEASUREMENTS[name])
            self.assertEqual(panel.ppms_simple_mode.get(), MEASUREMENTS[name][0])
            self.assertTrue(str(panel.ppms_plot_frame.options["text"]).startswith(f"{name}: X, Y, phase vs"))

    def test_a_new_scan_is_set_up_as_choosing_it_in_the_list_does(self):
        panel = self.page()
        panel.rte_set_measurement("AHE")
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["-3", "3", "0.1"])
        self.assertTrue(panel.rte_round_trip.get())
        self.assertEqual(panel.rte_scan_units.get(), "LS643 A")
        panel.rte_set_measurement("NLH")
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["0.01", "1", "0.01"])
        self.assertEqual(panel.rte_scan_units.get(), "6221 mA RMS")
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual([w.grid_removed for w in panel.rte_pulse_widgets], [False, True, True, False, False], "Switch: the width is each state's")
        self.assertFalse(panel.rte_states_frame.grid_removed)

    def test_a_measurement_keeps_the_scan_it_was_left_on(self):
        panel = self.page()
        panel.rte_set_measurement("Switch-OOP")
        panel.ppms_simple_mode.set("Switch2")
        panel._rte_mode_changed()
        panel.rte_set_measurement("AHE")
        panel.ppms_simple_mode.set("Field+Current")
        panel._rte_mode_changed()
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual(panel.ppms_simple_mode.get(), "Switch2")
        panel.rte_set_measurement("AHE")
        self.assertEqual(panel.ppms_simple_mode.get(), "Field+Current")

    def test_the_same_scan_in_another_measurement_keeps_what_was_typed(self):
        """SHHV and PHE both offer Angle+Field: going from one to the other
        does not put the range back to its start-up values."""
        panel = self.page()
        for variable, value in zip(panel.ppms_simple_range, ("10", "-80", "2")):
            variable.set(value)
        self.assertTrue(panel.rte_set_measurement("PHE"))
        self.assertEqual(panel.ppms_simple_mode.get(), "Angle+Field")
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["10", "-80", "2"])

    def test_a_running_scan_or_a_busy_page_keeps_the_measurement(self):
        for flag in ("ppms_field_scan_running", "ppms_environment_busy", "rte_stage_prompt_open", "rte_closed"):
            panel = self.page()
            setattr(panel, flag, True)
            self.assertFalse(panel.rte_set_measurement("Switch-OOP"), flag)
            self.assertEqual(panel.rte_measurement, "SHHV", flag)
            self.assertEqual(tuple(panel.rte_scan_mode_combo.options["values"]), MEASUREMENTS["SHHV"], flag)
            self.assertEqual(panel.ppms_simple_mode.get(), "Angle+Field", flag)
            # The measurement it is on is not a change.
            self.assertTrue(panel.rte_set_measurement("SHHV"), flag)

    def test_a_name_that_is_no_measurement_changes_nothing(self):
        panel = self.page()
        self.assertFalse(panel.rte_set_measurement("Log"))
        self.assertEqual(panel.rte_measurement, "SHHV")

    def test_nothing_else_follows_the_measurement(self):
        """ "the others remain the same": the read current, the harmonics and
        which lock-ins are measured are not the measurement's to change
        (PHE, AHE and the Switch tabs have start-up values of their own since:
        below)."""
        panel = self.page()

        def settings():
            return (panel.ppms_transport_current_var.get(), panel.ppms_transport_frequency_var.get(),
                    panel.ppms_transport_compliance_var.get(), panel.ppms_transport_harmonic_a_var.get(),
                    panel.ppms_transport_harmonic_b_var.get(), panel.ppms_transport_harmonic_c_var.get(),
                    panel.zurich_harmonic.get(), {key: v.get() for key, v in panel.ppms_lockin_selection.items()},
                    panel.ppms_page_name, {c.owner_scope for c in panel.rte_controllers.values()})
        before = settings()
        for name in ("NLH", "SHHV"):
            panel.rte_set_measurement(name)
            self.assertEqual(settings(), before, name)

    def shown(self, panel):
        return (panel.ppms_simple_mode.get(), [v.get() for v in panel.ppms_simple_range], str(panel.ppms_field_scan_loop_var.get()),
                panel.ppms_field_scan_stable_var.get(), panel.ppms_acquisition_time_var.get(), panel.rte_round_trip.get(),
                panel.rte_outer_ranges["Switch-loop"][0].get(), panel.rte_pulse_width_us.get(), panel.rte_pulse_count.get(),
                panel.ppms_transport_current_var.get(), panel.ppms_transport_frequency_var.get(),
                panel.ppms_transport_compliance_var.get(), panel.ppms_transport_harmonic_a_var.get())

    def test_the_switch_oop_tab_starts_as_the_users_figure(self):
        """User's figure, 2026-11-28 ("default use this settings in
        RT-Switch-OOP"): Switch-loop, 24 to -24 mA in 2 mA steps, 1 loop,
        Settle s 10, Acquire s 10, Round trip, 500 G.  From the figure of
        2026-11-27 (22 to -22, 30 s, 30 s, 200 G then): 1000 us pulses, 1
        pulse; read current 0.5 mA RMS at 317.3 Hz, compliance 100 V, SR830-1
        on the 1st harmonic and measured."""
        panel = self.page()
        self.loop_in_oop(panel)
        self.assertEqual(self.shown(panel), ("Switch-loop", ["24", "-24", "2"], "1", "10", "10", True, "500", "1000", "1",
                                             "0.5", "317.3", "100", "1"))
        self.assertEqual({key: v.get() for key, v in panel.ppms_lockin_selection.items()},
                         {"830_a": True, "830_b": False, "830_c": False, "zurich": False})
        self.assertEqual((panel.ppms_transport_harmonic_b_var.get(), panel.ppms_transport_harmonic_c_var.get(),
                          panel.zurich_harmonic.get()), ("2", "3", "1+2"))
        self.assertEqual(panel.rte_scan_units.get(), "6221 pulse mA")
        # The safety tick is the user's to make.
        self.assertFalse(panel.ppms_control_safety_var.get())
        # The plan: 24 down to -24 and back, 49 pulses.
        plan = [v for _l, _p, v in app.rte_scan_plan("Switch-loop", "24", "-24", "2", 1, True)]
        self.assertEqual((plan[0], plan[24], plan[-1], len(plan)), (24.0, -24.0, 24.0, 49))

    def test_the_switch_oop_tab_opens_on_the_switch_scan_with_the_figures_states(self):
        """User's figure, 2026-11-28 ("Switch-OOP default use the figure's settings"): the Switch scan, States 4,
        -360 deg / 1000 G / 0 mA, -270 / 200 / -10, -270 / 200 / 10, -360 / -1000 / 0, 50 us each; Settle s 10,
        Acquire s 10, Cycles 1, Pulses 1.  The other tabs show the table's own start-up states, a typed cell
        stays, and the tab's Switch-loop values are as they were."""
        figure = [["-360", "1000", "0", "50"], ["-270", "200", "-10", "50"], ["-270", "200", "10", "50"], ["-360", "-1000", "0", "50"]]
        own = [list(row) for row in app.SWITCH_DEFAULT_STATES]
        panel = self.page()

        def table():
            return [[v.get() for v in row] for row in panel.rte_state_vars[:4]]
        self.assertEqual(table(), own)
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual((panel.ppms_simple_mode.get(), panel.rte_states_count.get(), table()), ("Switch", "4", figure))
        self.assertEqual((panel.ppms_field_scan_stable_var.get(), panel.ppms_acquisition_time_var.get(), str(panel.ppms_field_scan_loop_var.get()),
                          panel.rte_pulse_count.get(), panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()),
                         ("10", "10", "1", "1", "0.5", "1"))
        self.assertEqual([[v.get() for v in row] for row in panel.rte_state_vars[4:6]], [[""] * 4] * 2)
        self.assertFalse(panel.ppms_control_safety_var.get(), "the safety tick is the user's to make")
        # The states are ones the scan takes: they parse, and the stage turns (every state has an angle).
        states = app.rte_switch_states(table(), "4")
        self.assertEqual([(s["angle_deg"], s["field_g"], s["pulse_ma"], round(s["width_s"] * 1e6, 6)) for s in states],
                         [(-360.0, 1000.0, 0.0, 50.0), (-270.0, 200.0, -10.0, 50.0), (-270.0, 200.0, 10.0, 50.0), (-360.0, -1000.0, 0.0, 50.0)])
        # Switch-IP and the other tabs: the table's own states (30 us on Switch-IP); back: the figure's again.
        panel.rte_set_measurement("Switch-IP")
        self.assertEqual(table(), [[*row[:3], "30"] for row in own])
        panel.rte_set_measurement("SHHV")
        self.assertEqual(table(), own)
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual((panel.ppms_simple_mode.get(), table()), ("Switch", figure))
        # A typed cell stays in every tab; the cells beside it still follow.
        panel.rte_state_vars[1][1].set("350")
        panel.rte_state_vars[2][3].set("80")
        panel.rte_set_measurement("Switch-IP")
        self.assertEqual(table(), [["0", "500", "20", "30"], ["0", "350", "-20", "30"], ["90", "500", "20", "80"], ["90", "500", "-20", "30"]])
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual(table(), [figure[0], ["-270", "350", "-10", "50"], ["-270", "200", "10", "80"], figure[3]])
        # Switch-loop in this tab keeps the figure of the morning.
        panel.ppms_simple_mode.set("Switch-loop")
        panel._rte_mode_changed()
        self.assertEqual(([v.get() for v in panel.ppms_simple_range], panel.rte_outer_ranges["Switch-loop"][0].get()), (["24", "-24", "2"], "500"))

    def test_the_phe_tab_starts_as_the_users_figure(self):
        """User's figure, 2026-11-27 ("default setting as the figure for PHE
        module"): Angle+Field 0 to -360 in 5, 1 loop, Settle s 0.5, no round
        trip; 1.5 mA RMS at 317.3 Hz, 100 V; SR830-1 on the 1st harmonic and
        the only one measured.  Figure of 2026-11-28 ("PHE default use these
        parameters pls."): Acquire s 2 (was 5), Outer field G 1000 (was 200)."""
        panel = self.page()
        panel.rte_set_measurement("PHE")
        self.assertEqual((panel.ppms_simple_mode.get(), [v.get() for v in panel.ppms_simple_range], str(panel.ppms_field_scan_loop_var.get()),
                          panel.ppms_field_scan_stable_var.get(), panel.ppms_acquisition_time_var.get(), panel.rte_round_trip.get(),
                          panel.rte_outer_ranges["Angle+Field"][0].get()),
                         ("Angle+Field", ["0", "-360", "5"], "1", "0.5", "2", False, "1000"))
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_frequency_var.get(),
                          panel.ppms_transport_compliance_var.get()), ("1.5", "317.3", "100"))
        self.assertEqual((panel.ppms_transport_harmonic_a_var.get(), panel.ppms_transport_harmonic_b_var.get(),
                          panel.ppms_transport_harmonic_c_var.get()), ("1", "2", "3"))
        self.assertEqual({key: v.get() for key, v in panel.ppms_lockin_selection.items()},
                         {"830_a": True, "830_b": False, "830_c": False, "zurich": False})
        self.assertEqual((panel.rte_pulse_current_ma.get(), panel.rte_pulse_width_us.get(), panel.rte_pulse_count.get()), ("10", "1000", "1"))
        self.assertFalse(panel.ppms_control_safety_var.get())
        # One field: one turn of 73 angles.
        self.assertEqual(list(app.rte_outer_list_plan(panel.rte_outer_ranges["Angle+Field"][0].get())), [1000.0])
        # The figure shows Angle+Field: Angle+Current keeps the page's 5 s, and a typed time stays.
        panel.ppms_simple_mode.set("Angle+Current")
        panel._rte_mode_changed()
        self.assertEqual(panel.ppms_acquisition_time_var.get(), f"{app.RTE_ACQUISITION_S:g}")
        panel.ppms_simple_mode.set("Angle+Field")
        panel._rte_mode_changed()
        self.assertEqual(panel.ppms_acquisition_time_var.get(), "2")
        panel.ppms_acquisition_time_var.set("3")
        panel.rte_set_measurement("SHHV")
        panel.rte_set_measurement("PHE")
        self.assertEqual(panel.ppms_acquisition_time_var.get(), "3")

    def test_phes_field_and_harmonic_go_back_with_shhv_and_a_typed_one_stays(self):
        fields = app.RTE_OUTER_ROWS["Angle+Field"]["defaults"][0]
        panel = self.page()
        box = panel.rte_outer_ranges["Angle+Field"][0]
        self.assertEqual((box.get(), panel.ppms_transport_harmonic_a_var.get()), (fields, "2"))
        panel.rte_set_measurement("PHE")
        self.assertEqual((box.get(), panel.ppms_transport_harmonic_a_var.get(), panel.ppms_acquisition_time_var.get()), ("1000", "1", "2"))
        panel.rte_set_measurement("SHHV")
        self.assertEqual((box.get(), panel.ppms_transport_harmonic_a_var.get(), panel.ppms_acquisition_time_var.get()), (fields, "2", f"{app.RTE_ACQUISITION_S:g}"))
        # Typed in PHE: kept in SHHV, and on the way back.
        panel.rte_set_measurement("PHE")
        box.set("350, 700")
        panel.rte_set_measurement("SHHV")
        self.assertEqual(box.get(), "350, 700")
        panel.rte_set_measurement("PHE")
        self.assertEqual(box.get(), "350, 700")
        # Typed in SHHV: PHE does not replace it.
        panel = self.page()
        box = panel.rte_outer_ranges["Angle+Field"][0]
        box.set("500")
        panel.rte_set_measurement("PHE")
        self.assertEqual((box.get(), panel.ppms_transport_harmonic_a_var.get()), ("500", "1"))

    def test_the_ahe_tab_starts_as_the_users_figure(self):
        """User's figure, 2026-11-27 ("default setting as the figure for AHE
        module"): Field -3 to 3 A in 0.1 A, 1 loop, Settle s 0.5, Acquire s 2,
        Round trip; 0.5 mA RMS at 317.3 Hz, 100 V; SR830-1 on the 1st harmonic
        and the only one measured."""
        panel = self.page()
        panel.rte_set_measurement("AHE")
        self.assertEqual((panel.ppms_simple_mode.get(), [v.get() for v in panel.ppms_simple_range], str(panel.ppms_field_scan_loop_var.get()),
                          panel.ppms_field_scan_stable_var.get(), panel.ppms_acquisition_time_var.get(), panel.rte_round_trip.get()),
                         ("Field", ["-3", "3", "0.1"], "1", "0.5", "2", True))
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_frequency_var.get(),
                          panel.ppms_transport_compliance_var.get()), ("0.5", "317.3", "100"))
        self.assertEqual((panel.ppms_transport_harmonic_a_var.get(), panel.ppms_transport_harmonic_b_var.get(),
                          panel.ppms_transport_harmonic_c_var.get(), panel.zurich_harmonic.get()), ("1", "2", "3", "1+2"))
        self.assertEqual({key: v.get() for key, v in panel.ppms_lockin_selection.items()},
                         {"830_a": True, "830_b": False, "830_c": False, "zurich": False})
        self.assertEqual((panel.rte_pulse_current_ma.get(), panel.rte_pulse_width_us.get(), panel.rte_pulse_count.get()), ("10", "1000", "1"))
        self.assertFalse(panel.ppms_control_safety_var.get())
        # -3 to 3 and back: 121 points.
        plan = [v for _l, _p, v in app.rte_scan_plan("Field", "-3", "3", "0.1", 1, True)]
        self.assertEqual((plan[0], round(plan[60], 9), plan[-1], len(plan)), (-3.0, 3.0, -3.0, 121))
        # The figure is the Field scan: the other two field sweeps keep theirs,
        # and Field shows -3 to 3 again when it is chosen again.
        for scan in ("Field+Angle", "Field+Current"):
            panel.ppms_simple_mode.set(scan)
            panel._rte_mode_changed()
            self.assertEqual([v.get() for v in panel.ppms_simple_range], list(app.RTE_FIELD_DEFAULT_RANGE), scan)
        panel.ppms_simple_mode.set("Field")
        panel._rte_mode_changed()
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["-3", "3", "0.1"])

    def test_the_read_current_and_harmonic_go_back_with_the_other_measurements(self):
        panel = self.page()
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), ("1.5", "2"))
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), ("0.5", "1"))
        for name, current, harmonic in (("SHHV", "1.5", "2"), ("AHE", "0.5", "1"), ("PHE", "1.5", "1"), ("NLH", "1.5", "2")):
            panel.rte_set_measurement(name)
            self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), (current, harmonic), name)
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), ("0.5", "1"))

    def test_a_typed_read_current_or_harmonic_stays(self):
        """As Acquire s: a box follows the measurement only while it still
        holds what the program put there."""
        panel = self.page()
        panel.ppms_transport_current_var.set("0.8")
        panel.ppms_transport_harmonic_a_var.set("3")
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), ("0.8", "3"))
        panel.rte_set_measurement("SHHV")
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), ("0.8", "3"))
        # Typed in the Switch-OOP tab: kept on the way out too.
        panel = self.page()
        panel.rte_set_measurement("Switch-OOP")
        panel.ppms_transport_current_var.set("0.2")
        panel.rte_set_measurement("SHHV")
        self.assertEqual((panel.ppms_transport_current_var.get(), panel.ppms_transport_harmonic_a_var.get()), ("0.2", "2"))

    def test_a_connected_sr830_is_set_to_the_harmonic_the_box_shows(self):
        """The harmonic box changes as choosing in it does, so a connected
        SR830-1 gets the harmonic the page shows."""
        panel = self.page()
        asked = []
        panel._ppms_apply_selected_harmonic = asked.append
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual(asked, ["830_a"])
        # PHE is on the 1st harmonic too: nothing to send.
        panel.rte_set_measurement("PHE")
        self.assertEqual(asked, ["830_a"])
        panel.rte_set_measurement("SHHV")
        self.assertEqual(asked, ["830_a", "830_a"])
        panel.rte_set_measurement("NLH")
        self.assertEqual(asked, ["830_a", "830_a"])

    def test_the_switch_ip_tab_is_switch_oop_with_14_ma_30_us_and_the_2nd_harmonic(self):
        """User, 2026-11-27: "add a Switch-IP module which use 14mA to -14mA
        step 2mA as default and SR830-1 use harmonic 2 pls. pulse width
        default 30us. the other settings are the same as Switch-OOP"."""
        self.assertEqual(app.RTE_MEASUREMENTS["Switch-IP"], app.RTE_MEASUREMENTS["Switch-OOP"])
        panel = self.page()
        self.loop_in_oop(panel)
        oop = self.shown(panel)
        panel = self.page()
        panel.rte_set_measurement("Switch-IP")
        self.assertEqual(self.shown(panel), ("Switch-loop", ["14", "-14", "2"], "1", "30", "30", True, "200", "30", "1",
                                             "0.5", "317.3", "100", "2"))
        # The loop, the pulse width and the harmonic differ, and since 2026-11-28 Settle s, Acquire s and the
        # field too: the user's figure of that day was for Switch-OOP, so this tab keeps 30 s, 30 s and 200 G.
        self.assertEqual([i for i, (a, b) in enumerate(zip(self.shown(panel), oop)) if a != b], [1, 3, 4, 6, 7, 12])
        self.assertEqual({key: v.get() for key, v in panel.ppms_lockin_selection.items()},
                         {"830_a": True, "830_b": False, "830_c": False, "zurich": False})
        self.assertFalse(panel.ppms_control_safety_var.get())
        plan = [v for _l, _p, v in app.rte_scan_plan("Switch-loop", "14", "-14", "2", 1, True)]
        self.assertEqual((plan[0], plan[14], plan[-1], len(plan)), (14.0, -14.0, 14.0, 29))
        # 30 us is a width the 6221 takes.
        self.assertLessEqual(app.K6221_MIN_PULSE_WIDTH_S, 30e-6)

    def test_the_loop_the_pulse_width_and_the_harmonic_follow_between_the_two_switch_tabs(self):
        panel = self.page()

        def three():
            return ([v.get() for v in panel.ppms_simple_range], panel.rte_pulse_width_us.get(), panel.ppms_transport_harmonic_a_var.get())
        self.loop_in_oop(panel)
        for name, expected in (("Switch-OOP", (["24", "-24", "2"], "1000", "1")), ("Switch-IP", (["14", "-14", "2"], "30", "2")),
                               ("Switch-OOP", (["24", "-24", "2"], "1000", "1")), ("Switch-IP", (["14", "-14", "2"], "30", "2"))):
            panel.rte_set_measurement(name)
            self.assertEqual(panel.ppms_simple_mode.get(), "Switch-loop", name)
            self.assertEqual(three(), expected, name)
        # Choosing Switch-loop again in the list gives this tab's loop.
        panel.ppms_simple_mode.set("Switch")
        panel._rte_mode_changed()
        panel.ppms_simple_mode.set("Switch-loop")
        panel._rte_mode_changed()
        self.assertEqual([v.get() for v in panel.ppms_simple_range], ["14", "-14", "2"])
        # The other tabs show 1000 us again.
        panel.rte_set_measurement("SHHV")
        self.assertEqual((panel.rte_pulse_width_us.get(), panel.ppms_transport_harmonic_a_var.get(), panel.ppms_transport_current_var.get()),
                         ("1000", "2", "1.5"))

    def test_a_typed_loop_or_pulse_width_stays_between_the_two_switch_tabs(self):
        panel = self.page()
        self.loop_in_oop(panel)
        for variable, value in zip(panel.ppms_simple_range, ("18", "-18", "1")):
            variable.set(value)
        panel.rte_pulse_width_us.set("500")
        panel.rte_set_measurement("Switch-IP")
        self.assertEqual(([v.get() for v in panel.ppms_simple_range], panel.rte_pulse_width_us.get()), (["18", "-18", "1"], "500"))
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual(([v.get() for v in panel.ppms_simple_range], panel.rte_pulse_width_us.get()), (["18", "-18", "1"], "500"))

    def test_the_states_pulse_widths_follow_the_tab_as_the_pulse_us_box_does(self):
        """The table's own states start with 1000 us; on Switch-IP, whose pulses are 30 us (user, 2026-11-27), a
        1000 us pulse would be 33 times the one expected, so their widths follow the tab while they still hold
        what the program put there.  A typed width, and a row not typed yet, stay."""
        panel = self.page()
        self.assertEqual({row[3] for row in app.SWITCH_DEFAULT_STATES}, {f"{app.SWITCH_DEFAULT_PULSE_WIDTH_US:g}"})

        def widths():
            return [row[3].get() for row in panel.rte_state_vars[:5]]
        self.assertEqual(widths(), ["1000"] * 4 + [""])
        panel.rte_state_vars[1][3].set("200")
        panel.rte_set_measurement("Switch-IP")
        self.assertEqual(widths(), ["30", "200", "30", "30", ""])
        panel.rte_set_measurement("SHHV")
        self.assertEqual(widths(), ["1000", "200", "1000", "1000", ""])
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual(widths(), ["50", "200", "50", "50", ""])

    def test_settle_acquire_and_the_field_follow_between_the_two_switch_tabs(self):
        """Switch-OOP's Switch-loop shows Settle s 10, Acquire s 10 and 500 G (user's figure, 2026-11-28);
        Switch-IP's shows 30, 30 and 200 G.  Both tabs stay on Switch-loop, so nothing but the tab changes."""
        panel = self.page()

        def three():
            return (panel.ppms_field_scan_stable_var.get(), panel.ppms_acquisition_time_var.get(), panel.rte_outer_ranges["Switch-loop"][0].get())
        self.loop_in_oop(panel)
        for name, expected in (("Switch-OOP", ("10", "10", "500")), ("Switch-IP", ("30", "30", "200")), ("Switch-OOP", ("10", "10", "500")),
                               ("Switch-IP", ("30", "30", "200"))):
            panel.rte_set_measurement(name)
            self.assertEqual(panel.ppms_simple_mode.get(), "Switch-loop", name)
            self.assertEqual(three(), expected, name)
        # The Switch scan shows its own 10 s on every tab (user, 2026-11-28: "settle 10s aqcuire 10s default"),
        # Switch2 keeps its times, and Switch-loop chosen again shows this tab's 10 s.
        panel.rte_set_measurement("Switch-OOP")
        for scan, times in (("Switch", ("10", "10")), ("Switch2", ("0.5", "30")), ("Switch-loop", ("10", "10"))):
            panel.ppms_simple_mode.set(scan)
            panel._rte_mode_changed()
            self.assertEqual(three()[:2], times, scan)
        # The other measurements show their scans' times as before, and the box keeps 500 G only for this tab.
        panel.rte_set_measurement("SHHV")
        self.assertEqual(three(), (f"{app.RTE_SETTLE_S:g}", f"{app.RTE_ACQUISITION_S:g}", "200"))
        panel.rte_set_measurement("AHE")
        self.assertEqual(three()[:2], ("0.5", "2"))

    def test_typed_times_and_a_typed_field_stay_between_the_two_switch_tabs(self):
        panel = self.page()
        self.loop_in_oop(panel)
        panel.ppms_field_scan_stable_var.set("15")
        panel.ppms_acquisition_time_var.set("20")
        panel.rte_outer_ranges["Switch-loop"][0].set("350")
        for name in ("Switch-IP", "Switch-OOP", "SHHV", "Switch-OOP"):
            panel.rte_set_measurement(name)
            if name.startswith("Switch"):
                self.assertEqual(panel.ppms_simple_mode.get(), "Switch-loop")
                self.assertEqual((panel.ppms_field_scan_stable_var.get(), panel.ppms_acquisition_time_var.get()), ("15", "20"), name)
            self.assertEqual(panel.rte_outer_ranges["Switch-loop"][0].get(), "350", name)

    def test_the_other_switch_scans_keep_their_own_values(self):
        panel = self.page()
        panel.rte_set_measurement("Switch-OOP")
        self.assertEqual(panel.rte_outer_ranges["Switch"][0].get(), "-12")
        self.assertEqual(panel.rte_switch_pulses_var.get(), app.SWITCH_DEFAULT_PULSES_MA)
        self.assertEqual(app.SWITCH_LOOP_DEFAULT_FIELDS_G, "200")

    def test_the_scan_box_is_left_of_the_settings_box(self):
        panel = self.page()
        boxes = {str(w.options.get("text")): w for w in ete.Recorder.made if w.options.get("text") in ("Scan", "Settings")}
        self.assertEqual(boxes["Scan"].grid_options["column"], 0)
        self.assertEqual(boxes["Settings"].grid_options["column"], 1)
        self.assertIs(boxes["Scan"].parent, boxes["Settings"].parent)
        self.assertIs(panel.rte_start_button.parent.parent, boxes["Scan"])
        self.assertTrue(app.RTE_SCAN_BOX_FIRST)


class SavedWithTheScan(ete.EndToEnd):
    def test_the_rows_and_the_run_settings_name_the_measurement(self):
        h = self.make()
        self.assertEqual(h.panel.rte_measurement, "SHHV")
        self.start(h)
        h.showerror.assert_not_called()
        rows = self.rows(h)
        self.assertTrue(rows)
        self.assertEqual({row["measurement"] for row in rows}, {"SHHV"})
        self.assertEqual(list(rows[0])[:3], ["module", "measurement", "scan_mode"])
        self.assertEqual({row["module"] for row in rows}, {"SHHV"})
        log = next(h.panel.rte_run_folder.glob("*.log"), None) or next(h.panel.rte_run_folder.glob("*.jsonl"))
        prepared = next(json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()
                        if '"run_prepared"' in line)
        self.assertIn('"measurement": "SHHV"', json.dumps(prepared))

    def in_phe(self):
        """The harness's page moved to PHE, on the harness's own short Angle
        scan again (the move puts PHE's first scan in the list)."""
        h = self.make()
        panel = h.panel
        self.assertTrue(panel.rte_set_measurement("PHE"))
        panel.ppms_simple_mode.set("Angle")
        panel._rte_mode_changed()
        for variable, value in zip(panel.ppms_simple_range, ("0", "10", "10")):
            variable.set(value)
        panel.rte_round_trip.set(False)
        return h

    def test_a_blank_file_name_is_the_measurements_name_date_and_time(self):
        """User, 2026-11-27: "change the default saved files' name
        corresponding to its children module name": PHE_<date>_<time> and so
        on, where every tab's run was SHHV_<date>_<time>."""
        h = self.in_phe()
        with patch.object(app.simpledialog, "askstring", return_value=""):
            self.start(h)
        self.assertEqual(h.showerror.call_args_list, [])
        folder = h.panel.rte_run_folder
        self.assertRegex(folder.name, r"^PHE_\d{8}_\d{6}$")
        self.assertEqual(sorted(p.name for p in folder.iterdir()), [f"{folder.name}.csv", f"{folder.name}.log"])
        self.assertEqual({row["measurement"] for row in self.rows(h)}, {"PHE"})
        # Save CSV as: the name of the measurement the rows were taken in,
        # also from another tab.
        self.assertTrue(h.panel.rte_set_measurement("SHHV"))
        with patch.object(app.filedialog, "asksaveasfilename", return_value="") as ask:
            h.panel.save_ppms_field_scan_csv()
        # ... in its title; the file suggested is the run's own name with _copy (2026-11-28).
        self.assertEqual(ask.call_args.kwargs["title"], "PHE: save CSV as")
        self.assertEqual(ask.call_args.kwargs["initialfile"], f"{folder.name}_copy.csv")
        self.assertEqual(ask.call_args.kwargs["initialdir"], str(folder))

    def test_a_typed_file_name_is_kept_in_every_measurement(self):
        h = self.in_phe()
        self.start(h)
        self.assertEqual(h.showerror.call_args_list, [])
        self.assertEqual(h.panel.rte_run_folder.name, "angle")

    def test_the_questions_at_the_start_are_named_after_the_measurement(self):
        """User, 2026-11-28: "standardize the file-saving logic ... ensure that the file and variable naming
        conventions are consistent".  The folder and the name were asked as "SHHV live CSV folder" and "SHHV
        file name" on every tab, while the files were named after the tab."""
        h = self.in_phe()
        made = []
        real = app.SHHVScanRecorder
        with patch.object(app.filedialog, "askdirectory", return_value=h.folder.name) as where, \
                patch.object(app.simpledialog, "askstring", return_value="") as name, \
                patch.object(app, "SHHVScanRecorder", side_effect=lambda *args: made.append(real(*args)) or made[-1]):
            self.start(h)
        self.assertEqual(h.showerror.call_args_list, [])
        self.assertEqual(where.call_args.kwargs["title"], "PHE: folder to save the run in")
        self.assertEqual(name.call_args.args[0], "PHE: file name")
        # One name, asked once, also names the run and the recorder's messages; the blank name's date and time
        # are the recorder's.
        (recorder,) = made
        self.assertEqual((recorder.page, recorder.label), ("PHE", "PHE"))
        self.assertRegex(recorder.stem, r"^PHE_\d{8}_\d{6}$")
        self.assertEqual(recorder.directory, h.panel.rte_run_folder)
        # Every row went through the recorder: it counted them, and the page keeps no path or header of its own.
        rows = self.rows(h)
        self.assertEqual(recorder.rows_written, len(rows))
        self.assertGreater(len(rows), 0)
        self.assertEqual(recorder.fieldnames, list(rows[0]))
        self.assertNotIn("ppms_live_csv_path", h.panel.__dict__)
        self.assertTrue(recorder.closed)

    def test_a_row_without_an_open_run_stops_the_scan(self):
        panel = self.make().panel
        panel.__dict__.pop("rte_recorder", None)
        with self.assertRaisesRegex(RuntimeError, "No run is open; the point was not saved"):
            panel._append_ppms_live_csv({"a": 1})

    def test_every_other_file_of_a_run_is_stem_part_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            first = app.SHHVScanRecorder(Path(folder), "loop", "Switch-OOP")
            second = app.SHHVScanRecorder(Path(folder), "loop", "Switch-OOP")      # the name is taken: loop_01
            self.assertEqual((first.stem, second.stem), ("loop", "loop_01"))
            self.assertEqual(second.csv_path, Path(folder) / "loop_01" / "loop_01.csv")
            self.assertEqual(second.part_path("trace", "csv"), Path(folder) / "loop_01" / "loop_01_trace.csv")
            self.assertEqual(second.part_path("plots_snapshot", "png").name, "loop_01_plots_snapshot.png")
            # The trace CSV is written as the live CSV is: header once, the byte-order mark, appended, on the disk.
            path = first.append_part_rows("trace", app.SWITCH_TRACE_COLUMNS, [("0.100", "SR830 #9 X", "1e-06", "V", "#1 +24 mA")])
            self.assertEqual(first.append_part_rows("trace", app.SWITCH_TRACE_COLUMNS, [("0.200", "SR830 #9 Y", "2e-06", "V", "#1 +24 mA")]), path)
            self.assertEqual(path, Path(folder) / "loop" / "loop_trace.csv")
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            first.append_row({"module": "SHHV", "measurement": "Switch-OOP"})
            self.assertTrue(first.csv_path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as handle:
                lines = list(csv.reader(handle))
            self.assertEqual(lines, [list(app.SWITCH_TRACE_COLUMNS), ["0.100", "SR830 #9 X", "1e-06", "V", "#1 +24 mA"],
                                     ["0.200", "SR830 #9 Y", "2e-06", "V", "#1 +24 mA"]])
            # A closed run takes nothing more, as its live CSV.
            first.close("completed")
            with self.assertRaisesRegex(RuntimeError, "The Switch-OOP run is closed"):
                first.append_part_rows("trace", app.SWITCH_TRACE_COLUMNS, [])
            second.close("completed")

    def test_the_page_has_one_writer_and_the_names_of_the_program(self):
        with open(app.__file__, encoding="utf-8") as source:
            text = source.read()
        # The recorder's part writer and Save CSV as: no other CSV is written in this module.
        self.assertEqual((text.count("csv.writer("), text.count("csv.DictWriter(")), (1, 1))
        self.assertNotIn("ppms_live_csv_path", text)
        self.assertNotIn("ppms_live_csv_fields", text)
        self.assertNotIn("live CSV folder", text)
        # The program log's suggested name is this program's.
        self.assertIn("Transport_RT_log_%Y%m%d_%H%M%S.txt", text)
        self.assertNotIn('"Transport_log_', text)

    def test_every_measurements_name_is_a_valid_file_name(self):
        for name in app.RTE_MEASUREMENTS:
            stem = f"{name}_20261127_120000"
            self.assertEqual(app.scan_file_stem(stem), stem)


if __name__ == "__main__":
    unittest.main()
