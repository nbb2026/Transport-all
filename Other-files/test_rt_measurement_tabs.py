"""The measurement tabs of Transport_RT in the real window (user, 2026-11-27:
the modes PHE, AHE, NLH, SHHV, Switch in that order; test_rt_measurements.py
has the request and the page's side).  One page serves every measurement, so
the instruments stay connected: its tab is the chosen measurement's, and
choosing another measurement's tab moves the page there.

The tab "Switch" is "Switch-OOP" (user, 2026-11-27: "rename the switch to
switch-OOP").  In a wide window three things that took two rows take one
(user, same day: "shrink the two row in the figure to one row", "this also
one row"): the scan note, the stage block and the supply's live line.

Built on GitHub's machines; with no display there is no test."""
import tkinter as tk
import tkinter.font
import unittest

from test_ppms_motor_debug import app

MEASUREMENTS = {
    "PHE": ("Angle+Field", "Angle+Current"),
    "AHE": ("Field", "Field+Angle", "Field+Current"),
    "NLH": ("Current",),
    "SHHV": ("Angle+Field", "Angle+Current"),
    "Switch-OOP": ("Switch", "Switch-loop", "Switch2"),
    "Switch-IP": ("Switch", "Switch-loop", "Switch2"),
}


class TheTabs(unittest.TestCase):
    """The real window (GitHub's machines; no display, no test)."""

    @classmethod
    def setUpClass(cls):
        from lab_screen import build_lab_app
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"no display: {error}")
        cls.a = build_lab_app(app, cls.root)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.a.closing = True
        try:
            cls.a.safe_close_hardware()
        finally:
            cls.root.destroy()

    def titles(self):
        notebook = self.a.notebook
        return tuple(notebook.tab(index, "text") for index in range(notebook.index("end")))

    def choose(self, name):
        notebook = self.a.notebook
        notebook.select(self.titles().index(name))
        for _ in range(4):
            self.root.update()

    def test_1_the_tabs_are_the_measurements_then_the_log_and_it_starts_on_shhv(self):
        self.assertEqual(self.titles(), ("PHE", "AHE", "NLH", "SHHV", "Switch-OOP", "Switch-IP", "Log"))
        notebook = self.a.notebook
        self.assertEqual(notebook.select(), str(self.a.rte_panel_tab))
        self.assertEqual(notebook.tab("current", "text"), "SHHV")
        self.assertEqual(self.a.rte_panel.rte_measurement, "SHHV")

    def test_2_choosing_a_tab_brings_the_one_page_there_with_its_scans(self):
        notebook, panel = self.a.notebook, self.a.rte_panel
        for name in ("PHE", "Switch-OOP", "AHE", "Switch-IP", "NLH", "SHHV"):
            self.choose(name)
            self.assertEqual(self.titles(), ("PHE", "AHE", "NLH", "SHHV", "Switch-OOP", "Switch-IP", "Log"), name)
            self.assertEqual(notebook.select(), str(self.a.rte_panel_tab), name)
            self.assertEqual(notebook.tab("current", "text"), name)
            self.assertEqual(panel.rte_measurement, name)
            self.assertEqual(tuple(panel.rte_scan_mode_combo.cget("values")), MEASUREMENTS[name])
            self.assertEqual(panel.ppms_simple_mode.get(), panel.rte_scan_mode_combo.get())
            self.assertIn(panel.ppms_simple_mode.get(), MEASUREMENTS[name])
            self.assertTrue(panel.rte_start_button.winfo_ismapped(), name)
            self.assertEqual(len(notebook.tabs()), 7)

    def test_3_the_log_tab_shows_the_log_and_the_measurement_is_kept(self):
        self.choose("Switch-OOP")
        self.choose("Log")
        self.assertEqual(self.a.notebook.select(), str(self.a.log_tab))
        self.assertEqual(self.a.rte_panel.rte_measurement, "Switch-OOP")
        self.assertIn("Measurement: Switch-OOP (scans: Switch, Switch-loop, Switch2)", self.a.log_text.get("1.0", "end"))
        self.choose("Switch-OOP")
        self.assertEqual(self.a.notebook.select(), str(self.a.rte_panel_tab))
        self.choose("SHHV")

    def test_4_while_a_scan_runs_the_measurement_stays_and_the_page_comes_back(self):
        panel, said = self.a.rte_panel, []
        self.choose("SHHV")
        real = panel._rte_dialog
        panel._rte_dialog = lambda title, text, show=None: said.append((title, text))
        panel.ppms_field_scan_running = True
        try:
            self.choose("AHE")
            self.assertEqual(self.a.notebook.select(), str(self.a.rte_panel_tab))
            self.assertEqual(self.a.notebook.tab("current", "text"), "SHHV")
            self.assertEqual(panel.rte_measurement, "SHHV")
            self.assertEqual(tuple(panel.rte_scan_mode_combo.cget("values")), MEASUREMENTS["SHHV"])
            self.assertEqual(len(said), 1)
            self.assertIn("stays SHHV", said[0][1])
            self.assertIn("choose AHE", said[0][1])
            self.choose("Log")
            self.assertEqual(self.a.notebook.select(), str(self.a.log_tab))
            self.choose("SHHV")
        finally:
            panel.ppms_field_scan_running = False
            panel._rte_dialog = real
        self.choose("AHE")
        self.assertEqual(panel.rte_measurement, "AHE")
        self.choose("SHHV")

    def test_6_one_row_where_there_were_two_in_a_wide_window(self):
        panel = self.a.rte_panel
        self.choose("Switch-OOP")
        # The figure was of the Switch-loop scan; the tab opens on the Switch scan since 2026-11-28, whose
        # states' table stands where the note would go.
        panel.ppms_simple_mode.set("Switch-loop")
        panel._rte_mode_changed()
        self.root.geometry("2400x1300+0+0")
        for _ in range(8):
            self.root.update()
        try:
            scan = panel.rte_start_button.master.master
            controls = scan.master
            self.assertTrue(controls._pair_side_by_side)
            # The scan note is beside Round trip, in the rows of the scan settings.
            note = next(w for w in scan.winfo_children()
                        if isinstance(w, tk.ttk.Label) and str(w.cget("textvariable")) == str(panel.rte_scan_note))
            self.assertEqual(panel.rte_note_place, "beside, wide")
            self.assertEqual(str(note.grid_info()["in"]), str(panel.rte_start_button.master))
            self.assertLess(abs(note.winfo_rooty() + note.winfo_height() // 2
                                - panel.rte_start_button.winfo_rooty() - panel.rte_start_button.winfo_height() // 2), 12)
            self.assertTrue(note.winfo_ismapped())
            # The stage block is one row: Set stage 0 and the stage's line right of Go to 0.
            block = panel.rte_stage_stop_button.master
            holder = panel.rte_stage_zero_button.master
            self.assertEqual((block._rte_stage_place, block._rte_stage_one_row), ("under params", True))
            self.assertEqual(int(holder.grid_info()["row"]), 0)
            self.assertGreater(holder.winfo_rootx(), panel.rte_stage_home_button.winfo_rootx() + panel.rte_stage_home_button.winfo_width() - 2)
            self.assertLess(abs(holder.winfo_rooty() - panel.rte_stage_home_button.winfo_rooty()), 6)
            settings = block.master.master
            self.assertLessEqual(block.winfo_rootx() + block.winfo_width(), settings.winfo_rootx() + settings.winfo_width())
            # The supply's live line holds the field-setting text on one line.
            lines = [w for w in panel.ppms_plot_frame.master.winfo_children()[0].winfo_children()
                     if isinstance(w, tk.ttk.Label) and str(w.cget("textvariable")) in (str(panel.rte_drive_live), str(panel.rte_field_live))]
            self.assertEqual(len(lines), 2)
            font = tk.font.nametofont("TkDefaultFont")
            for line in lines:
                self.assertEqual(int(line.cget("width")), app.RTE_LIVE_WIDE_CHARS)
                self.assertGreaterEqual(int(float(str(line.cget("wraplength")))),
                                        font.measure("Field 1/1 +200 G, step 6: I -1.136 A, B +198.667 G"))
        finally:
            self.choose("SHHV")

    def test_7_a_narrow_window_keeps_the_two_rows(self):
        panel = self.a.rte_panel
        self.root.geometry("1101x1300+0+0")
        for _ in range(8):
            self.root.update()
        block = panel.rte_stage_stop_button.master
        self.assertFalse(getattr(block, "_rte_stage_one_row", False))
        self.assertEqual(int(panel.rte_stage_zero_button.master.grid_info()["row"]), 1)
        self.assertIn(panel.rte_note_place, ("beside", "under"))

    def test_5_the_scan_box_is_left_of_the_settings_box_in_a_wide_window(self):
        from lab_screen import LAB_WIDE
        self.root.geometry(f"{LAB_WIDE}x1300+0+0")
        for _ in range(6):
            self.root.update()
        panel = self.a.rte_panel
        scan = panel.rte_start_button.master.master
        controls = scan.master
        settings = next(w for w in controls.winfo_children()
                        if isinstance(w, tk.ttk.LabelFrame) and str(w.cget("text")) == "Settings")
        self.assertEqual(str(scan.cget("text")), "Scan")
        self.assertTrue(controls._pair_side_by_side)
        self.assertLess(scan.winfo_rootx() + scan.winfo_width(), settings.winfo_rootx() + 2)
        self.assertEqual(scan.winfo_rooty(), settings.winfo_rooty())
        self.assertLessEqual(settings.winfo_rootx() + settings.winfo_width(), controls.winfo_rootx() + controls.winfo_width())


if __name__ == "__main__":
    unittest.main()
