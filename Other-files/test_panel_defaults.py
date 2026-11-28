"""Start-up defaults and status layout of the PPMS and RT-E pages.

Both are decided in the panel constructors, which the stub-based suites never
run, so they are checked here against a fully built application.
"""
import tempfile
import tkinter as tk
import tkinter.font
import unittest
from pathlib import Path

from lab_screen import LAB_WIDE, build_lab_app, lab_window
from test_ppms_motor_debug import app


class PanelDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # headless build server
            raise unittest.SkipTest(f"no display: {error}")
        cls.root.withdraw()
        cls.app = app.CombinedControlApp(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.app.closing = True
        cls.app.safe_close_hardware()
        cls.root.destroy()

    def settings(self, panel):
        """(harmonic, measured) per meter, as the settings row shows them."""
        state = {key: (str(panel._ppms_harmonic_var(key).get()),
                       bool(panel.ppms_lockin_selection[key].get()))
                 for key in app.PPMS_SR830_KEYS}
        state["zurich"] = (str(panel.zurich_harmonic.get()),
                           bool(panel.ppms_lockin_selection["zurich"].get()))
        return state

    def test_rte_selection_gives_one_plot_row_per_harmonic(self):
        panel = self.app.rte_panel
        orders = panel._ppms2_measured_orders()
        # SR830-1 alone at 2 by default (user's figure, 2026-11-16).
        self.assertEqual(sorted(orders), [2])
        self.assertEqual({order: sorted(meters) for order, meters in orders.items()},
                         {2: ["830_a"]}, f"SR830-1 alone measured by default: {orders}")

    def test_rte_scan_runs_one_pass_per_harmonic(self):
        # SR830-1 at 1+2+3, chosen as its harmonic box would: it starts at 2
        # since the user's figure of 2026-11-16 (1 from 2026-10-20, 1+2+3
        # before).
        panel = self.app.rte_panel
        variable = panel._ppms_harmonic_var("830_a")
        self.addCleanup(variable.set, variable.get())
        variable.set("1+2+3")
        passes = panel._rte_harmonic_passes(dict(
            active_lockins=("830_a",), current_rms_ma=1.0, frequency_hz=133.7,
            compliance_v=10.0, harmonic_a=1, harmonic_b=2, harmonic_c=3,
            allow_no_lockins=False))
        self.assertEqual([entry["harmonic_a"] for entry in passes], [1, 2, 3])

    def _boxes(self):
        found, pending = [], list(self.app.root.winfo_children())
        while pending:
            widget = pending.pop()
            if widget.winfo_class() == "EnglishMessageBox":
                found.append(widget)
            pending.extend(widget.winfo_children())
        return found

    @staticmethod
    def _button(box, name):
        pending = [box]
        while pending:
            widget = pending.pop()
            if widget.winfo_class() == "TButton" and widget.winfo_name() == name:
                return widget
            pending.extend(widget.winfo_children())
        return None

    def _ask(self, function, title, message, steps):
        """Run a message box with ``steps`` (ms, callback) scheduled, and a
        last resort that answers every open box, so a test never waits."""
        root = self.app.root
        jobs = [root.after(ms, callback) for ms, callback in steps]

        def answer_all():
            for box in self._boxes():
                for name in ("no", "cancel", "ok"):
                    button = self._button(box, name)
                    if button is not None:
                        button.invoke()
                        break

        jobs.append(root.after(10000, answer_all))
        try:
            return function(title, message, parent=root)
        finally:
            for job in jobs:
                root.after_cancel(job)

    def test_message_boxes_and_file_dialogs_are_in_english(self):
        """2026-10-12: Yes/No, not the Chinese Windows' buttons: our own
        message boxes, and Tk's own file dialogs, their text in English."""
        root = self.app.root
        if str(root.tk.call("tk", "windowingsystem")) != "x11":
            for command, target in (
                ("::tk_messageBox", "::tk::MessageBox"),
                ("::tk_getOpenFile", "::tk::dialog::file:: open"),
                ("::tk_getSaveFile", "::tk::dialog::file:: save"),
                ("::tk_chooseDirectory", "::tk::dialog::file::chooseDir::"),
            ):
                alias = root.tk.splitlist(root.tk.call("interp", "alias", "", command))
                self.assertEqual(" ".join(map(str, alias)), target, command)
        self.assertEqual(str(root.tk.call("::msgcat::mclocale")), "en")
        seen = []

        def read_and_answer():
            box = self._boxes()[0]
            seen.extend(str(self._button(box, name).cget("text")) for name in ("yes", "no"))
            self._button(box, "no").invoke()

        self.assertFalse(self._ask(app.messagebox.askyesno, "English dialogs",
                                   "Is this box in English?", [(300, read_and_answer)]))
        self.assertEqual(seen, ["Yes", "No"])
        self.assertEqual(self._boxes(), [], "closed")

    def test_a_box_over_an_open_box_leaves_both_answers_right(self):
        """Review, 2026-10-12: Tk's own box shares one window and one answer,
        so a second box closed the first and gave it the second's answer."""
        log = []

        def open_inner():
            log.append(("inner", app.messagebox.showinfo("Inner", "Over the open box",
                                                         parent=self.app.root)))

        def press(title, name):
            box = next(box for box in self._boxes() if box.title() == title)
            self._button(box, name).invoke()

        answer = self._ask(app.messagebox.askyesno, "Outer", "Start?", [
            (200, open_inner),
            (700, lambda: log.append(("open", sorted(box.title() for box in self._boxes())))),
            (800, lambda: press("Inner", "ok")),
            (1300, lambda: press("Outer", "yes")),
        ])
        self.assertTrue(answer, "the outer box's own answer")
        self.assertEqual(log, [("open", ["Inner", "Outer"]), ("inner", "ok")])

    def test_a_box_while_a_tcl_window_holds_the_grab(self):
        """Review, 2026-10-12: a Combobox's open list or Tk's file dialog is
        not a tkinter widget, so grab_current() raised KeyError and the box
        stayed on top for good.  It answers now and gives the grab back."""
        root = self.app.root
        root.tk.eval("toplevel .tcl_only_grab; wm geometry .tcl_only_grab 120x60+0+0")
        try:
            root.update()
            root.tk.call("grab", "set", ".tcl_only_grab")
            answer = self._ask(app.messagebox.askyesno, "Grab", "Answer?", [
                (300, lambda: self._button(self._boxes()[0], "yes").invoke()),
            ])
            self.assertTrue(answer)
            self.assertEqual(self._boxes(), [], "no box left behind")
            self.assertEqual(str(root.tk.call("grab", "current", root._w)), ".tcl_only_grab",
                             "the grab given back")
        finally:
            root.tk.call("grab", "release", ".tcl_only_grab")
            root.tk.eval("destroy .tcl_only_grab")

    def widgets(self, cls, variable=None, text=None):
        found, pending = [], [self.app.nonlocal_vi_tab]
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            if widget.winfo_class() != cls:
                continue
            if variable is not None and str(widget.cget("textvariable")) != str(variable):
                continue
            if text is not None and str(widget.cget("text")) != text:
                continue
            found.append(widget)
        return found

class NotebookTabTests(unittest.TestCase):
    """The tab strip names each page; pages sharing a rack share a prefix."""

    pass


class RTEStatusRowTests(unittest.TestCase):
    """The RT-E scan status stays on one line in the widened lab window.

    These are the messages RT-E itself shows.  Failures are cut at the first
    "; " by short_status_error, and the full text goes to the error dialog and
    the log.  (The long "Stopping the Current scan; ..." text is the PPMS
    page's; RT-E overrides the stop.)
    """

    MESSAGES = (
        "Failed: " + app.short_status_error(
            RuntimeError("6221 hit compliance; scan stopped and output turned off"), 100),
        "Failed: " + app.short_status_error(
            RuntimeError("LS475 field drifted during acquisition; point discarded"), 100),
        # The Field and Current Start line with the wait before each reading
        # and the shortest duration (2026-10-14), at its longest: 100000
        # points, Settle s 86400 s and Acquire s 86400 s (about 493 px in
        # Arial 15 px and 590 px in DejaVu Sans, under the 505 px / 598 px
        # of the Stopped line below).  The wait shows at most five digits
        # (ppms_settle_status_text): whole seconds from 100 s, 3 significant
        # digits below, so a sub-second wait is at most "0.0864" (497 px /
        # 595 px).  Only a wait under 10 ms with Acquire s of 10 h or more
        # could be wider; a wait of 100000 s or more (once 7 x a 30 ks SR830
        # time constant) cannot occur at the user's 1 x TC, as Settle s is
        # at most 86400 s (user, 2026-10-14).
        "SHHV Current: 100000 points, settle 86400 s; at least 4800024 h 00 min 00 s",
        "SHHV Current: 100000 points, settle 0.0864 s; at least 2400026 h 24 min 02 s",
        # The default Field scan at 1 x TC: 199 x (1 s + 1 s) + 1 s (user,
        # 2026-10-14; "settle 7 s; at least 26 min 33 s" at 7 x TC).
        "SHHV Field: 199 points, settle 1 s; at least 6 min 39 s",
        # A wait that differs from the one announced at Start, while it runs
        # (a time constant changed since Connect), at its widest: about 412
        # px in Arial, 485 px in DejaVu Sans (the same digits as the
        # "0.0864 s: 7 x 0.0123 s" it replaces; at 1 x TC the wait is the TC).
        "Each reading now waits 0.0864 s: 1 x 0.0864 s TC of the Zurich",
        # Every ending zeroes the 6221 and the KEPCO (user, 2026-10-18; the
        # outputs were held, and a Current scan's 6221 alone set to 0, until
        # then), so the finish lines say how that went.
        "Stopping; completed CSV points kept; KEPCO and 6221 zeroed next",
        "Completed; " + app.rte_outputs_text({"6221": "zeroed", "kepco": "zeroed"}),
        "Completed; " + app.rte_outputs_text({"6221": "zero FAILED: x", "kepco": "not connected"}),
        "Completed; " + app.rte_outputs_text({"6221": "zero FAILED: x", "kepco": "zero FAILED: y"}),
        # The Angle scan's (2026-10-13), at their longest: six significant
        # digits ({:g}) for the angles and the KEPCO current, 100000 points.
        "SHHV Angle -359.995° to 359.995°, KEPCO -9.87654 A held; 100000 points",
        "Stopped; " + app.rte_outputs_text({"6221": "zeroed", "kepco": "zeroed"}, check=False)
        + "; stage stopped at -359.999°",
        "Stopped; " + app.rte_outputs_text({"6221": "zero FAILED: x", "kepco": "zeroed"}, check=False)
        + "; stage stopped at -359.999°",
        "Stopped; " + app.rte_outputs_text(None, check=False) + "; stage stopped at -359.999°",
        "Completed; " + app.rte_outputs_text({"6221": "zeroed", "kepco": "zeroed"}, check=False)
        + "; stage at +360.000°",
        # ABORT stopped it, STOP did not (review, 2026-10-18).
        "Stopped; " + app.rte_outputs_text({"6221": "zeroed", "kepco": "zeroed"}, check=False)
        + "; stage stopped at -359.999° (ABORT)",
        # A failure that also left an output not confirmed at zero says so
        # (review, 2026-10-18), the error shortened to keep the line.
        app.rte_failed_status_text(RuntimeError("6221 hit compliance; scan stopped and output turned off"),
                                   {"6221": "zero FAILED: x", "kepco": "zeroed"}),
        app.rte_failed_status_text(RuntimeError("VI_ERROR_TMO (-1073807339): Timeout expired before "
                                                "operation completed"),
                                   {"6221": "zero FAILED: x", "kepco": "zero FAILED: y"}),
        app.rte_failed_status_text(RuntimeError("LS475 field drifted during acquisition; point discarded"), None),
        # An Angle Start that did not start (review, 2026-10-17): the longest
        # fixed reason, and the widest refusal the stage check or a fix can
        # give, cut to 44 characters (about 478 px in Arial 15 px).
        app.rte_angle_not_started_text("an OFF button was pressed"),
        app.rte_angle_not_started_text(RuntimeError(
            "The Newmark NSC-A1's last stop was not confirmed, so it may still be turning: press Stop stage "
            "first (check the stage)")),
    )

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # headless build server
            raise unittest.SkipTest(f"no display: {error}")
        cls.app = build_lab_app(app, cls.root)  # as the lab PC shows it
        cls.root.geometry(f"{LAB_WIDE}x{lab_window(cls.app)[1]}+0+0")
        notebook = next(w for w in cls.app.__dict__.values()
                        if isinstance(w, tk.ttk.Notebook))
        for index in range(notebook.index("end")):
            if notebook.tab(index, "text") == "SHHV & Switch":
                notebook.select(index)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.closing = True
        cls.app.safe_close_hardware()
        cls.root.destroy()

    def status_label(self):
        return self.app.rte_panel.rte_status_label

    def test_longest_status_fits_on_one_line(self):
        label = self.status_label()
        variable = self.app.rte_panel.ppms_field_scan_status_var
        variable.set("Ready")
        self.root.update()
        one_line = label.winfo_height()
        font = tkinter.font.Font(font=label.cget("font") or "TkDefaultFont")
        for message in self.MESSAGES:
            variable.set(message)
            self.root.update()
            self.assertEqual(str(label.cget("text")), message, "shown in full")
            self.assertLessEqual(font.measure(message), label.winfo_width(),
                                 f"status too narrow for: {message}")
            self.assertEqual(label.winfo_height(), one_line,
                             f"status wrapped onto a second line: {message}")

    def test_a_long_failure_is_cut_with_an_ellipsis(self):
        """The status shows what fits and ends in "…"; the variable keeps it all."""
        label = self.status_label()
        variable = self.app.rte_panel.ppms_field_scan_status_var
        message = "Failed: " + "VI_ERROR_TMO (-1073807339): Timeout expired before operation completed " * 3
        try:
            variable.set("Ready")
            self.root.update()
            one_line = label.winfo_height()
            variable.set(message)
            self.root.update()
            shown = str(label.cget("text"))
            font = tkinter.font.Font(font=label.cget("font") or "TkDefaultFont")
            self.assertTrue(shown.endswith("\u2026"), shown)
            self.assertTrue(message.startswith(shown[:-1].rstrip()), shown)
            self.assertLessEqual(font.measure(shown), label.winfo_width())
            self.assertEqual(variable.get(), message, "the full text is kept")
            self.assertEqual(label.winfo_height(), one_line)
        finally:
            variable.set("Ready")

    def test_status_never_wraps(self):
        self.assertEqual(int(self.status_label().cget("wraplength")), 0)

    def test_status_shares_its_row_with_the_progress_bar(self):
        """Giving the status its own row would cost the plots a row of height."""
        progress = self.app.rte_panel.ppms_field_scan_progress
        self.assertEqual(progress.master, self.status_label().master)
        self.assertLess(abs(progress.winfo_rooty() - self.status_label().winfo_rooty()), 6)


# Named to run after PanelDefaultTests' message boxes and before TCRackTests,
# as RTEStatusRowTests does: it maps and destroys a program copy too.
class SHHVConnectionColumnsTests(unittest.TestCase):
    """The SHHV & Switch page's connections (user, 2026-11-22: "also two
    columns for the instruments connection panel"; first on the Switch page
    of 2026-11-21), as the lab PC shows them: in the 2000 px window two
    columns, the rack's five rows left and the three SR830s and the Zurich
    right, with the supply's line, the LS475's reading and Set field beside
    the SR830 rows; stacked in the 1101 px window, those three beside the
    rack as before; nothing past the page's edge; whatever the resize
    history."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # headless build server
            raise unittest.SkipTest(f"no display: {error}")
        cls.app = build_lab_app(app, cls.root)  # as the lab PC shows it
        notebook = cls.app.notebook
        for index in range(notebook.index("end")):
            if notebook.tab(index, "text") == "SHHV & Switch":
                notebook.select(index)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.closing = True
        cls.app.safe_close_hardware()
        cls.root.destroy()

    def show(self, width):
        self.root.geometry(f"{width}x{lab_window(self.app)[1]}+0+0")
        for _ in range(4):
            self.root.update()
        self.assertEqual(self.root.winfo_width(), width)

    @staticmethod
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from SHHVConnectionColumnsTests.descendants(child)

    def test_two_columns_when_wide_and_stacked_when_narrow(self):
        panel = self.app.rte_panel
        motor = panel.rte_connection_widgets["newmark"][0]
        source = panel.ppms_device_resource_widgets["6221"]
        first, third = (panel.ppms_device_resource_widgets[key] for key in ("830_a", "830_c"))
        zurich = panel.zurich_connect_button
        set_field = panel.rte_set_field_button
        tab = panel.ppms_tab
        narrow = lab_window(self.app)[0]
        for history in ((LAB_WIDE,), (narrow,), (narrow, LAB_WIDE), (LAB_WIDE, narrow), (900, LAB_WIDE)):
            for width in history:
                self.show(width)
            wide = history[-1] == LAB_WIDE
            with self.subTest(history=history):
                for widget in (motor, source, first, third, zurich, set_field):
                    self.assertTrue(widget.winfo_ismapped())
                right = tab.winfo_rootx() + tab.winfo_width()
                over = [w for w in self.descendants(tab)
                        if w.winfo_ismapped() and w.winfo_rootx() + w.winfo_width() > right + 1]
                self.assertEqual(over, [], "widgets past the right edge")
                middle = lambda widget: widget.winfo_rooty() + widget.winfo_height() / 2
                if wide:
                    # SR830-1 beside the rack's first row, right of its rows.
                    self.assertGreater(first.winfo_rootx(), motor.winfo_rootx() + motor.winfo_width())
                    self.assertLess(first.winfo_rooty(), source.winfo_rooty())
                    # The field setting beside SR830-3's row, right of its
                    # connection widgets, above the Zurich's row.
                    self.assertLessEqual(abs(middle(set_field) - middle(third)), 6)
                    self.assertGreater(set_field.winfo_rootx(), third.master.winfo_rootx() + third.master.winfo_width())
                    self.assertLess(set_field.winfo_rooty() + set_field.winfo_height(), zurich.winfo_rooty() + 2)
                    # The lock-ins' four rows are no taller than the rack's
                    # five, so the box is as tall as the rack alone.
                    self.assertLessEqual(zurich.winfo_rooty() + zurich.winfo_height(),
                                         motor.winfo_rooty() + motor.winfo_height() + 2)
                else:
                    # Stacked: SR830-1 under the Motor row, in its column.
                    self.assertGreaterEqual(first.winfo_rooty(), motor.winfo_rooty() + motor.winfo_height())
                    # The field setting beside the 6221's row, as before.
                    self.assertGreater(set_field.winfo_rootx(), source.winfo_rootx() + source.winfo_width())
                    self.assertLessEqual(abs(middle(set_field) - middle(source)), 6)
        # The Zurich's harmonic row under the three SR830s'.
        self.assertEqual(int(panel.zurich_harmonic_combo.grid_info()["row"]), 3)
        self.assertFalse(hasattr(self.app, "switch_panel"))

    def test_the_pulses_box_reaches_the_scan_box_edge(self):
        """User, 2026-11-23: the Switch mode's "Pulses mA:" box "as longer
        as possible": it runs to the Scan box's right edge; when the outer
        field row sits beside the scan rows (1101 px), in Switch mode its
        label is beside its own box on the second row, under the Pulses
        box, not above it.  Since 2026-11-28 the Switch scan has its
        states' table there instead, so this is Switch2's "Pulses V:" box,
        the same two widgets."""
        panel = self.app.rte_panel
        was = panel.ppms_simple_mode.get()
        panel.ppms_simple_mode.set("Switch2")
        panel._rte_mode_changed()
        try:
            for width in (lab_window(self.app)[0], LAB_WIDE):
                self.show(width)
                with self.subTest(width=width):
                    entry = panel.rte_switch_pulse_list_widgets[1]
                    scan = entry.master.master
                    self.assertTrue(entry.winfo_ismapped())
                    right = entry.winfo_rootx() + entry.winfo_width()
                    self.assertGreaterEqual(right, scan.winfo_rootx() + scan.winfo_width() - 16)
                    label, box = (widget for widget, _options in panel.rte_outer_list_widgets)
                    self.assertTrue(label.winfo_ismapped() and box.winfo_ismapped())
                    self.assertGreaterEqual(label.winfo_rooty(), entry.winfo_rooty() + entry.winfo_height())
                    if panel.rte_outer_place == "beside":
                        self.assertEqual((int(label.grid_info()["row"]), int(box.grid_info()["row"])), (1, 1))
                        self.assertGreater(box.winfo_rootx(), label.winfo_rootx())
                    self.assertLessEqual(right, scan.winfo_rootx() + scan.winfo_width())
        finally:
            panel.ppms_simple_mode.set(was)
            panel._rte_mode_changed()
            self.root.update()


    def test_the_switch_scan_shows_its_states_table(self):
        """User, 2026-11-28: "change the switch scan mode to set the state 1,
        2, 3, 4... like MS_four state".  In the Switch scan the Scan box
        shows the table (States, and Angle, Field G, Pulse mA, Pulse us of
        each state) in place of "Pulses mA", "Outer field G" and the Pulse
        us box; it is inside the Scan box, over no other widget, at both
        window widths, beside the scan's rows where the box is wide enough."""
        panel = self.app.rte_panel
        was = panel.ppms_simple_mode.get()
        panel.ppms_simple_mode.set("Switch")
        panel._rte_mode_changed()

        def box(widget):
            return (widget.winfo_rootx(), widget.winfo_rooty(), widget.winfo_rootx() + widget.winfo_width(), widget.winfo_rooty() + widget.winfo_height())
        try:
            frame = panel.rte_states_frame
            rows, scan = frame.master, frame.master.master
            for width in (lab_window(self.app)[0], LAB_WIDE):
                for count in ("4", "8", "4"):
                    panel.rte_states_count.set(count)
                    panel._rte_show_state_rows()
                    self.show(width)
                    for _ in range(3):
                        self.root.update()
                    with self.subTest(width=width, states=count):
                        self.assertTrue(frame.winfo_ismapped())
                        shown = [row for row in panel.rte_state_rows if row[0].winfo_ismapped()]
                        self.assertEqual(len(shown), int(count))
                        self.assertTrue(all(widget.winfo_ismapped() for row in shown for widget in row))
                        hidden = (*panel.rte_switch_pulse_list_widgets, *(w for w, _options in panel.rte_outer_list_widgets), *panel.rte_pulse_widgets[1:3])
                        self.assertFalse([str(w) for w in hidden if w.winfo_ismapped()])
                        self.assertTrue(all(w.winfo_ismapped() for w in (panel.rte_pulse_widgets[0], *panel.rte_pulse_widgets[3:], *panel.rte_cycles_widgets)))
                        left, top, right, bottom = box(frame)
                        print(f"Switch states table at {self.root.winfo_width()} px, {count} states: {panel.rte_states_place}, "
                              f"{right - left}x{bottom - top} px in a Scan box of {scan.winfo_width()}x{scan.winfo_height()} px; "
                              f"pulse row {panel.__dict__.get('rte_pulse_place')}, note {panel.__dict__.get('rte_note_place')}")
                        s_left, s_top, s_right, s_bottom = box(scan)
                        self.assertTrue(s_left <= left and right <= s_right and s_top <= top and bottom <= s_bottom, (box(frame), box(scan)))
                        for other in rows.grid_slaves():
                            if other is frame or not other.winfo_ismapped() or not other.winfo_width():
                                continue
                            o_left, o_top, o_right, o_bottom = box(other)
                            self.assertFalse(left < o_right and o_left < right and top < o_bottom and o_top < bottom,
                                             f"the table {box(frame)} is over {other.winfo_class()} {other.cget('text') if 'text' in other.keys() else ''} {box(other)}")
        finally:
            panel.rte_states_count.set("4")
            panel._rte_show_state_rows()
            panel.ppms_simple_mode.set(was)
            panel._rte_mode_changed()
            self.root.update()


class ReviewFixWidgetTests(unittest.TestCase):
    """Widgets and texts changed by the review of the merged areas (review,
    2026-10-18): the MOKE magnet status says the other KEPCO was only sent
    0 A, on one line in the lab's window; a STFMR Start cancelled at its
    Yes/No or folder leaves the instrument rows and Apply output unlocked."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # headless build server
            raise unittest.SkipTest(f"no display: {error}")
        cls.app = build_lab_app(app, cls.root)  # as the lab PC shows it
        cls.root.geometry(f"{LAB_WIDE}x{lab_window(cls.app)[1]}+0+0")
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.closing = True
        cls.app.safe_close_hardware()
        cls.root.destroy()

    def select(self, text):
        notebook = self.app.notebook
        for index in range(notebook.index("end")):
            if notebook.tab(index, "text") == text:
                notebook.select(index)
        self.root.update()

    @staticmethod
    def labels_of(widget, variable):
        found = []
        for child in widget.winfo_children():
            try:
                if str(child.cget("textvariable")) == str(variable):
                    found.append(child)
            except tk.TclError:
                pass
            found.extend(ReviewFixWidgetTests.labels_of(child, variable))
        return found



# Named to sort last: unittest runs a module's classes in name order, and this
# one maps and destroys a whole program copy.  Before PanelDefaultTests'
# message boxes that is the order that crashed Tk's focus_force on the Linux
# CI (2026-10-14), so nothing in this module runs after it (user, 2026-10-14).
class TCRackTests(unittest.TestCase):
    """The PPMS rack (user, 2026-10-14): the Zurich row says "TC (s)", as on
    RT-E, and one 'SR830 TC' dropdown for the three SR830s sits beside Macro,
    under the Keithley 2400 and left of SR830-3, in the window the program
    opens with and in the 2000 px one, without widening the rack."""

    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # headless build server
            raise unittest.SkipTest(f"no display: {error}")
        cls.app = build_lab_app(app, cls.root)  # as the lab PC shows it
        notebook = next(w for w in cls.app.__dict__.values()
                        if isinstance(w, tk.ttk.Notebook))
        for index in range(notebook.index("end")):
            if notebook.tab(index, "text") == "PPMS":
                notebook.select(index)
        cls.root.update()

    @classmethod
    def tearDownClass(cls):
        cls.app.closing = True
        cls.app.safe_close_hardware()
        cls.root.destroy()

    def show(self, width):
        self.root.geometry(f"{width}x{lab_window(self.app)[1]}+0+0")
        self.root.update()

if __name__ == "__main__":
    unittest.main()
