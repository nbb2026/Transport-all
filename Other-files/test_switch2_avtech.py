"""The Switch2 scan (user, 2026-11-23: "add switch2 scan in the SHHV &
Switch module which use the Avtech in stead of 6221. You can refer to CIDWM
module to learn the avtech pulse generator settings").

Switch with the Avtech giving the pulses: the outer field list, the 6221's
read current and the lock-in readings as Switch has them; at each point the
6221's output off, the Avtech's pulse(s) as the CIDWM page sends them (the
same AvtechPulserController: width and amplitude read back, output read back
off after each), then the read current on again.  The page's real controller
on test_avtech_pulser's simulated generator; no VISA session, no window."""
import threading
import unittest
from unittest.mock import patch

import test_rte_angle_end_to_end as ete
import test_switch_page as switch
from test_avtech_pulser import FakeAvtech
from test_ppms_motor_debug import app
from test_rte_angle_scan import Recorder

setUpModule, tearDownModule = ete.setUpModule, ete.tearDownModule


class Switch2Page(unittest.TestCase):
    def test_switch2_is_the_last_mode_with_the_avtechs_boxes(self):
        panel = ete.build_page(kepco=False)
        self.assertEqual(app.RTE_SCAN_MODES[-3:], ("Switch", "Switch-loop", "Switch2"))
        self.assertEqual(app.SWITCH_MODES, ("Switch", "Switch-loop", "Switch2"))
        # The Avtech's connection row: under the Zurich's, the CIDWM page's
        # address to start with, and the page's own controller.
        entry, connect, disconnect = panel.rte_connection_widgets["avtech"]
        self.assertIs(entry.options["textvariable"], panel.rte_resources["avtech"])
        self.assertEqual(panel.rte_resources["avtech"].get(), app.AVTECH_DEFAULT_RESOURCE)
        self.assertIs(entry.parent.parent, panel.ppms_instruments_frame)
        self.assertEqual(entry.parent.grid_options["row"], 4)
        self.assertEqual([w.options.get("text") for w in Recorder.made if w.parent is entry.parent][:1], ["Avtech"])
        self.assertIsInstance(panel.rte_controllers["avtech"], app.AvtechPulserController)
        self.assertEqual(panel.rte_controllers["avtech"].owner_scope, "SHHV")
        # Shown only in Switch2 or while the Avtech is connected: the other
        # modes keep their height for the plots (GitHub's 1101 px window).
        self.assertIs(entry.parent.grid_removed, True)
        pulse_list, pulse_row = panel.rte_switch_pulse_list_widgets, panel.rte_pulse_widgets
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Switch2")
            panel._rte_mode_changed()
            self.assertEqual(pulse_list[0].options["text"], "Pulses V:")
            self.assertIs(pulse_list[1].options["textvariable"], panel.rte_switch2_pulses_var)
            self.assertEqual(panel.rte_switch2_pulses_var.get(), ", ".join(str(v) for v in range(-100, 101, 10)))
            self.assertEqual({w.grid_removed for w in pulse_list + pulse_row}, {False})
            self.assertEqual({w.grid_removed for w in panel.rte_range_widgets}, {True})
            self.assertEqual([w.options.get("text") for w in pulse_row[:2] + pulse_row[3:4]], ["Avtech", "Width ns", "Pulses"])
            self.assertEqual([pulse_row[2].options["textvariable"], pulse_row[4].options["textvariable"]],
                             [panel.rte_avtech_width_ns, panel.rte_avtech_count])
            self.assertEqual((panel.rte_avtech_width_ns.get(), panel.rte_avtech_count.get()), ("50", "1"))
            self.assertEqual((panel.rte_scan_units.get(), panel.rte_scan_note.get()), ("", "Switch2: Avtech pulse V; outer: field G"))
            self.assertEqual(panel.ppms_acquisition_time_var.get(), "30")
            self.assertIs(panel.rte_round_trip.get(), True)
            self.assertIs(panel.rte_outer_list_entry.options["textvariable"], panel.rte_outer_ranges["Switch2"][0])
            self.assertEqual(panel.rte_outer_ranges["Switch2"][0].get(), "40, 20, 0, -20")
            self.assertEqual(panel.ppms_plot_axis, "avtech")
            self.assertIs(entry.parent.grid_removed, False)
            self.assertIs(panel.rte_time_row_on, True)
            # Back to Switch: the 6221's boxes again.
            panel.ppms_simple_mode.set("Switch")
            panel._rte_mode_changed()
            self.assertEqual(pulse_list[0].options["text"], "Pulses mA:")
            self.assertIs(pulse_list[1].options["textvariable"], panel.rte_switch_pulses_var)
            self.assertEqual([w.options.get("text") for w in pulse_row[:2] + pulse_row[3:4]], ["6221 write", "Pulse µs", "Pulses"])
            self.assertEqual([pulse_row[2].options["textvariable"], pulse_row[4].options["textvariable"]],
                             [panel.rte_pulse_width_us, panel.rte_pulse_count])
            # Since 2026-11-28 the Switch scan runs states: its plots are against the state's number.
            self.assertEqual(panel.ppms_plot_axis, "state")
            self.assertIs(entry.parent.grid_removed, True)
            # Connected, it stays in every mode.
            panel.rte_controllers["avtech"].instrument = object()
            panel._rte_show_avtech_row()
            self.assertIs(entry.parent.grid_removed, False)
            panel.rte_controllers["avtech"].instrument = None

    def test_the_plan_takes_volts_within_the_avtechs_100_v(self):
        typed = app.rte_pulse_list("-100, 0 50", "Pulses V", "pulse amplitudes", "V")
        plan = app.rte_scan_plan("Switch2", None, None, None, 1, True, values=typed)
        self.assertEqual([value for _loop, _point, value in plan], [-100.0, 0.0, 50.0, 0.0, -100.0])
        with self.assertRaisesRegex(ValueError, r"Avtech pulse amplitudes must stay within \+/-100 V; 120 V is outside"):
            app.rte_scan_plan("Switch2", None, None, None, 1, False, values=(0.0, 120.0))
        with self.assertRaisesRegex(ValueError, "Pulses V: type the pulse amplitudes in V"):
            app.rte_pulse_list("", "Pulses V", "pulse amplitudes", "V")
        # The 6221's messages are as before.
        with self.assertRaisesRegex(ValueError, "Pulses mA: type the pulse currents in mA in the order to scan"):
            app.rte_pulse_list("")


class Switch2Scan(switch.SwitchScan):
    def make_switch2(self, fields="100, -50", pulses="-50, 0, 50", width="30", count="1", **fake):
        h = self.make_switch(fields=fields)
        panel = h.panel
        with patch.object(app.CombinedControlApp, "_draw_nonlocal_series"):
            panel.ppms_simple_mode.set("Switch2")
            panel._rte_mode_changed()
        panel.rte_switch2_pulses_var.set(pulses)
        panel.rte_outer_ranges["Switch2"][0].set(fields)
        panel.rte_avtech_width_ns.set(width)
        panel.rte_avtech_count.set(count)
        patcher = patch.object(app, "AVTECH_PULSE_GAP_S", 0.0)
        patcher.start()
        self.addCleanup(patcher.stop)
        h.avtech = FakeAvtech(**fake)
        h.fired_with_6221 = []
        real_write = h.avtech.write

        def write(command):
            # The 6221's output at each trigger: never on while the Avtech fires.
            if command.strip().lower() == "trigger:source immediate":
                h.fired_with_6221.append(h.fake.output)
                h.log.append(("avtech", "fire", threading.get_ident()))
            return real_write(command)
        h.avtech.write = write
        controller = panel.rte_controllers["avtech"]
        controller.instrument, controller.identity, controller.resource_name = h.avtech, h.avtech.identity, "GPIB0::7::INSTR"
        return h


class Switch2ScanTests(Switch2Scan):
    def test_each_point_fires_the_avtech_with_the_6221_off_then_reads(self):
        h = self.make_switch2()
        h.draw.reset_mock()
        self.start(h)
        panel = h.panel
        h.showerror.assert_not_called()
        title, question = h.askyesno.call_args.args[:2]
        self.assertEqual(title, "SHHV scan")
        self.assertIn("Avtech pulse amplitude, the INNER loop: 5 pulses a loop in the order typed, -50, +0, +50 V and back", question)
        self.assertIn("1 Avtech pulse(s) of 30 ns", question)
        rows = self.rows(h)
        self.assertEqual([(r["outer_target_field_g"], float(r["pulse_amplitude_v"])) for r in rows],
                         [("100.0", v) for v in (-50.0, 0.0, 50.0, 0.0, -50.0)] + [("-50.0", v) for v in (-50.0, 0.0, 50.0, 0.0, -50.0)])
        self.assertEqual({(r["module"], r["scan_mode"]) for r in rows}, {("SHHV", "Switch2")})
        self.assertEqual([r["avtech_overload"] for r in rows[:3]], ["False", "no pulse", "False"])
        self.assertEqual([r["avtech_amplitude_read_v"] for r in rows[:3]], ["-50.0", "", "50.0"])
        self.assertEqual({(float(r["pulse_width_ns"]), r["pulse_count"]) for r in rows}, {(30.0, "1")})
        self.assertNotIn("pulse_current_ma", rows[0])
        # Six pulses (0 V fires none), each 30 ns, none with the 6221's output on,
        # and no 6221 pulse.
        self.assertEqual(h.avtech.pulses, [(-50.0, 3e-8), (50.0, 3e-8), (-50.0, 3e-8)] * 2)
        self.assertEqual(h.fired_with_6221, [0] * 6)
        self.assertEqual(h.fake.trains, [])
        self.assertEqual(len(h.fake.sines), 10, "the read current on again before every reading")
        self.assertEqual((h.avtech.output, h.avtech.trigger), (0, "hold"))
        self.assertEqual({entry[-1] for entry in h.log}, {h.worker})
        self.assertEqual(panel.ppms_field_scan_status_var.get(), "Completed; Avtech, KEPCO and 6221 zeroed")
        events = ete.RunLogBase.events(h)
        prepared = events[0]
        self.assertEqual((prepared["mode"], prepared["plan"]["unit"], prepared["plan"]["typed"]), ("Switch2", "V (Avtech pulse)", "-50, 0, 50"))
        self.assertEqual({k: prepared["pulse"][k] for k in ("source", "width_s", "count", "resource")},
                         {"source": "Avtech", "width_s": 3e-8, "count": 1, "resource": "GPIB0::7::INSTR"})
        zeroed = [e for e in events if e["event"] == "outputs_zeroed"][-1]
        self.assertEqual((zeroed["avtech"], zeroed["6221"]), ("zeroed", "zeroed"))
        pulse_calls = [call for call in h.draw.call_args_list if call.args[2] == "Avtech pulse amplitude (V)"]
        self.assertEqual({call.args[3] for call in pulse_calls}, {"X voltage", "Y voltage"})
        with panel.rte_switch_trace_path.open(encoding="utf-8", newline="") as handle:
            lines = list(app.csv.reader(handle))
        self.assertEqual(lines[1][4], "#1 -50 V")

    def test_two_pulses_a_point(self):
        h = self.make_switch2(fields="100", pulses="20", count="2")
        self.start(h)
        h.showerror.assert_not_called()
        self.assertEqual(h.avtech.pulses, [(20.0, 3e-8)] * 2)
        self.assertEqual(self.rows(h)[0]["avtech_pulses_sent"], "2")

    def test_start_refuses_before_anything_is_sent(self):
        positive_only = "AVTECH ELECTROSYSTEMS,AVR-E3-B-P-W3,14486,5.07"
        for pulses, width, count, identity, message in (
                ("0, 120", "30", "1", None, r"Avtech pulse amplitudes must stay within \+/-100 V"),
                ("-10, 10", "6000", "1", None, "The Avtech pulse width must be within 1 ns - 5 us"),
                ("10", "x", "1", None, "Width ns must be a number"),
                ("10", "30", "0", None, "The Avtech pulse count must be a whole number"),
                ("10, -10", "30", "1", positive_only, "This Avtech gives positive pulses only")):
            with self.subTest(message=message):
                h = self.make_switch2(pulses=pulses, width=width, count=count)
                if identity:
                    h.panel.rte_controllers["avtech"].identity = identity
                self.start(h)
                self.assertEqual(h.showerror.call_args.args[0], "SHHV scan parameters")
                self.assertRegex(h.showerror.call_args.args[1], message)
                h.askyesno.assert_not_called()
                self.assertEqual((h.avtech.pulses, h.fake.sent), ([], []))
        h = self.make_switch2()
        h.panel.rte_controllers["avtech"].instrument = None
        self.start(h)
        self.assertIn('Connect the Avtech (the "Avtech" row', h.showerror.call_args.args[1])
        self.assertEqual(h.fake.sent, [])

    def test_an_overload_stops_the_scan_with_the_output_off(self):
        h = self.make_switch2(fields="100", pulses="50, 60", trip=True)
        self.start(h)
        message = h.showerror.call_args.args[1]
        self.assertIn("The Avtech's output protection tripped at +50 V", message)
        self.assertEqual(h.avtech.pulses, [(50.0, 3e-8)])
        self.assertEqual(self.rows(h), [], "no point read")
        self.assertEqual(h.avtech.output, 0)
        events = ete.RunLogBase.events(h)
        self.assertEqual([e["event"] for e in events if e["event"].startswith("pulse")], ["pulse_overload"])
        self.assertTrue(h.panel.ppms_field_scan_status_var.get().startswith("Failed"))

    def test_a_stop_between_two_pulses_ends_it_with_the_avtech_off(self):
        h = self.make_switch2(fields="100", pulses="10", count="3")
        real = h.avtech.write
        fired = []

        def write(command):
            real(command)
            if command.strip().lower() == "trigger:source immediate":
                fired.append(command)
                h.panel.ppms_field_scan_stop_event.set()
        h.avtech.write = write
        self.start(h)
        h.showerror.assert_not_called()
        self.assertEqual(len(h.avtech.pulses), 1)
        self.assertEqual(h.avtech.output, 0)
        self.assertTrue(h.panel.ppms_field_scan_status_var.get().startswith("Stopped"))


if __name__ == "__main__":
    unittest.main()
