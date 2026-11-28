"""The pass that takes unreachable code out of the generated program (tools/extract_app.py, prune_unreachable).

User, 2026-11-28: "remove the unused code in RT to make it as shorter as possible".  The program is an
instrument program: a method taken out that the program still calls would fail in the middle of a measurement.
So the rules are tested here on small programs, one rule each, and the generated program is checked for the
two things the pass relies on: nothing more can be taken out of it (it is the pass's own result), and it has
no attribute look-up by a name built at run time that the pass could not have seen.
"""
import ast
import sys
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import extract_app  # noqa: E402

APP = ROOT / "transport" / "rt" / "app.py"


def pruned(source: str, roots=("main",)) -> str:
    return extract_app.prune_unreachable(textwrap.dedent(source), roots)[0]


def definitions(text: str) -> set[str]:
    found = set()
    for node in ast.parse(text).body:
        if isinstance(node, ast.ClassDef):
            found.add(node.name)
            found.update(f"{node.name}.{item.name}" for item in node.body if isinstance(item, ast.FunctionDef))
        elif isinstance(node, ast.FunctionDef):
            found.add(node.name)
        elif isinstance(node, ast.Assign):
            found.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return found


class RuleTests(unittest.TestCase):
    def test_what_main_does_not_reach_goes(self):
        left = definitions(pruned("""
            USED = 1
            UNUSED = 2
            def helper():
                return USED
            def never():
                return UNUSED
            def main():
                return helper()
        """))
        self.assertEqual(left, {"USED", "helper", "main"})

    def test_a_replaced_method_of_the_base_goes_but_not_one_reached_through_super(self):
        left = definitions(pruned("""
            class Window:
                def build(self):
                    return "window"
                def close(self):
                    return "window closed"
                def log(self):
                    return "log"
            class Page(Window):
                def build(self):
                    return self.log()
                def close(self):
                    return super().close()
            def main():
                page = Page()
                page.build()
                page.close()
        """))
        self.assertNotIn("Window.build", left)          # only a Page is ever made, and it has its own
        self.assertLessEqual({"Window.close", "Window.log", "Page.build", "Page.close"}, left)

    def test_the_base_method_stays_when_the_base_is_made_too(self):
        left = definitions(pruned("""
            class Window:
                def build(self):
                    return "window"
            class Page(Window):
                def build(self):
                    return "page"
            def main():
                for item in (Window(), Page()):
                    item.build()
        """))
        self.assertLessEqual({"Window.build", "Page.build"}, left)

    def test_a_method_reached_on_one_class_does_not_keep_the_other_classes_self_calls(self):
        # start() runs on both; only the window's start calls self.poll, so the page's poll is not reached.
        left = definitions(pruned("""
            class Window:
                def start(self):
                    return self.poll()
                def poll(self):
                    return 1
            class Page(Window):
                def start(self):
                    return 2
                def poll(self):
                    return 3
            def main():
                Window().start()
                Page().start()
        """))
        self.assertIn("Window.poll", left)
        self.assertNotIn("Page.poll", left)

    def test_a_name_used_on_any_object_keeps_it_in_every_made_class(self):
        left = definitions(pruned("""
            class Supply:
                def zero(self):
                    return 0
            class Stage:
                def zero(self):
                    return 0
                def home(self):
                    return 0
            def main():
                for item in (Supply(), Stage()):
                    item.zero()
        """))
        self.assertLessEqual({"Supply.zero", "Stage.zero"}, left)
        self.assertNotIn("Stage.home", left)

    def test_a_name_in_a_string_keeps_the_method(self):
        left = definitions(pruned("""
            class Supply:
                def output_on(self):
                    return True
                def output_owned(self):
                    return True
                def other(self):
                    return True
            def main(lakeshore):
                return getattr(Supply(), "output_on" if lakeshore else "output_owned")()
        """))
        self.assertLessEqual({"Supply.output_on", "Supply.output_owned"}, left)
        self.assertNotIn("Supply.other", left)

    def test_a_call_keeps_only_methods_that_can_take_its_arguments(self):
        left = definitions(pruned("""
            class Instrument:
                def configure(self, current_a, frequency_hz):
                    return current_a
                def set(self, value):
                    return value
            def main(widget, variable):
                Instrument()
                widget.configure(text="ready")
                variable.set(1)
        """))
        self.assertNotIn("Instrument.configure", left)
        self.assertIn("Instrument.set", left)

    def test_arguments_that_are_not_known_keep_the_method(self):
        for call in ("widget.configure(**options)", "widget.configure(*values)", "later = widget.configure"):
            with self.subTest(call=call):
                left = definitions(pruned(f"""
                    class Instrument:
                        def configure(self, current_a, frequency_hz):
                            return current_a
                    def main(widget, options, values):
                        Instrument()
                        {call}
                """))
                self.assertIn("Instrument.configure", left)

    def test_call_fits(self):
        def method(signature, decorator=""):
            return ast.parse(f"class C:\n    {decorator}\n    def m({signature}): pass").body[0].body[0]
        fits = extract_app.call_fits
        self.assertTrue(fits(None, method("self, a, b")))
        self.assertTrue(fits((2, frozenset()), method("self, a, b")))
        self.assertFalse(fits((1, frozenset()), method("self, a, b")))
        self.assertFalse(fits((3, frozenset()), method("self, a, b")))
        self.assertTrue(fits((3, frozenset()), method("self, a, *rest")))
        self.assertTrue(fits((1, frozenset({"b"})), method("self, a, b")))
        self.assertFalse(fits((1, frozenset({"c"})), method("self, a, b")))
        self.assertTrue(fits((1, frozenset({"c"})), method("self, a, **more")))
        self.assertTrue(fits((0, frozenset()), method("self, a=1, *, b=2")))
        self.assertFalse(fits((0, frozenset()), method("self, *, b")))
        self.assertTrue(fits((2, frozenset()), method("a, b", "@staticmethod")))
        self.assertTrue(fits((1, frozenset()), method("cls, a", "@classmethod")))
        self.assertTrue(fits((5, frozenset()), method("self", "@property")))     # the call is of what it returns

    def test_isinstance_and_a_base_class_do_not_make_objects(self):
        left = definitions(pruned("""
            class Base:
                def read(self):
                    return 0
                def only_base(self):
                    return 0
            class Meter(Base):
                def read(self):
                    return 1
            def main(item):
                if isinstance(item, Base):
                    return 0
                return Meter().read() or item.only_base()
        """))
        self.assertIn("Meter.read", left)
        self.assertIn("Base.only_base", left)           # a Meter has it
        self.assertNotIn("Base.read", left)             # no bare Base is made

    def test_a_class_method_that_builds_the_class_makes_it(self):
        left = definitions(pruned("""
            class Reading:
                def __init__(self):
                    self.value = 0
                @classmethod
                def zero(cls):
                    return cls()
                def text(self):
                    return str(self.value)
            def main():
                return Reading.zero().text()
        """))
        self.assertLessEqual({"Reading.__init__", "Reading.zero", "Reading.text"}, left)

    def test_a_class_used_only_for_one_of_its_functions_loses_the_rest(self):
        left = definitions(pruned("""
            class Source:
                def __init__(self):
                    self.on = False
                @staticmethod
                def check(value):
                    return abs(value) < 1
                def output_on(self):
                    self.on = True
            def main(item):
                item.output_on()
                return Source.check(0.5)
        """))
        self.assertIn("Source.check", left)
        self.assertNotIn("Source.output_on", left)      # no Source is made, so item is never one
        self.assertNotIn("Source.__init__", left)

    def test_a_class_with_a_base_from_outside_keeps_all_its_methods(self):
        left = definitions(pruned("""
            import threading
            class Worker(threading.Thread):
                def run(self):
                    return 0
                def helper(self):
                    return 0
            def main():
                Worker().start()
        """))
        self.assertLessEqual({"Worker.run", "Worker.helper"}, left)

    def test_special_methods_and_stream_methods_stay(self):
        left = definitions(pruned("""
            import sys
            class Log:
                def __enter__(self):
                    return self
                def __exit__(self, *error):
                    return False
                def write(self, text):
                    return len(text)
                def flush(self):
                    return None
                def rotate(self):
                    return None
            def main():
                with Log() as log:
                    print("x", file=log)
        """))
        self.assertLessEqual({"Log.__enter__", "Log.__exit__", "Log.write", "Log.flush"}, left)
        self.assertNotIn("Log.rotate", left)

    def test_a_property_and_its_setter_stay_together(self):
        left = definitions(pruned("""
            class Stage:
                @property
                def may_run(self):
                    return self._may
                @may_run.setter
                def may_run(self, value):
                    self._may = value
            def main():
                Stage().may_run = True
        """))
        self.assertIn("Stage.may_run", left)
        self.assertEqual(pruned("class A:\n    pass\ndef main():\n    return A()\n").count("def "), 1)

    def test_a_method_named_in_the_class_body_stays(self):
        left = definitions(pruned("""
            class Panel:
                def _draw(self):
                    return 0
                redraw = _draw
            def main():
                Panel().redraw()
        """))
        self.assertIn("Panel._draw", left)

    def test_a_statement_that_calls_something_stays_with_what_it_needs(self):
        left = definitions(pruned("""
            import atexit
            def tidy():
                return 0
            atexit.register(tidy)
            REGISTRY = dict()
            def main():
                return 0
        """))
        self.assertLessEqual({"tidy", "REGISTRY", "main"}, left)

    def test_unused_imports_go_and_a_class_left_empty_still_parses(self):
        text = pruned("""
            import os, sys
            from pathlib import Path, PurePath
            class Holder:
                def unused(self):
                    return os.sep
            def main():
                return Path(sys.argv[0]), isinstance(1, Holder)
        """)
        ast.parse(text)
        self.assertIn("import sys", text)
        self.assertNotIn("os", text.split("class")[0])
        self.assertIn("from pathlib import Path\n", text)
        self.assertIn("    pass", text)


class GeneratedProgramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = APP.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.text)

    def test_nothing_more_can_be_taken_out(self):
        again, report = extract_app.prune_unreachable(self.text, ("main", "run"))
        self.assertEqual(report, [])
        self.assertEqual(again, self.text)

    def test_the_other_pages_code_is_not_in_it(self):
        left = definitions(self.text)
        for name in ("CombinedControlApp.build_ppms_ui", "CombinedControlApp.start_ppms_field_scan", "CombinedControlApp._ppms_field_scan_worker",
                     "CombinedControlApp.open_ppms_macro", "PPMSMotorDebug", "parse_ppms_macro", "NonLocalACController.connect_nanovoltmeter",
                     "Keithley6221Controller.set_dc_pulse", "PPMSRemoteReadbackController.connect"):
            self.assertNotIn(name, left)
        for name in ("RTEPanel", "RTEPanel.safe_close_ppms", "CombinedControlApp.safe_close_ppms", "CombinedControlApp.ppms_sources_off",
                     "NonLocalACController.output_off", "STFMRKepco4886Controller.force_output_off", "LakeShoreMagnetSupplyController",
                     "NewmarkNSCA1Controller", "AvtechPulserController", "main", "run", "APP_VERSION"):
            self.assertIn(name, left)

    def test_no_attribute_is_looked_up_by_a_name_built_at_run_time(self):
        """getattr and setattr with a name that is not a literal: each one known, and each takes its name from
        literals in the program (which the pass counts), a DLL's exports, or hands on the name it was asked for.
        A new one must be looked at before it is added here."""
        parents = {child: node for node in ast.walk(self.tree) for child in ast.iter_child_nodes(node)}

        def where(node):
            names = []
            while node in parents:
                node = parents[node]
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    names.append(node.name)
            return ".".join(reversed(names))
        found = set()
        for node in ast.walk(self.tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if name in ("getattr", "setattr", "hasattr", "delattr") and len(node.args) >= 2:
                asked = node.args[1]              # a literal, or one of two literals ("a" if x else "b")
                choices = [asked.body, asked.orelse] if isinstance(asked, ast.IfExp) else [asked]
                if not all(isinstance(item, ast.Constant) and isinstance(item.value, str) for item in choices):
                    found.add((where(node), ast.unparse(asked)))
            if isinstance(node.func, ast.Name):          # Python's own; root.tk.eval is Tcl's
                self.assertNotIn(name, ("eval", "exec", "locals", "vars"), where(node))
            self.assertNotIn(name, ("attrgetter", "methodcaller", "__getattribute__"), where(node))
        self.assertEqual(found, {
            ("CombinedControlApp._ppms_harmonic_var", "PPMS_SR830_HARMONIC_ATTRS[key]"),     # names in that constant
            ("RTEPanel._initialize_ppms_state", "PPMS_SR830_HARMONIC_ATTRS[key]"),
            ("PPMSPanel.__getattr__", "name"),                                               # handed on to the main window
            ("newmark_declare_functions", "name"),                                           # a DLL's functions
            ("NewmarkNSCA1Controller._function", "name"),
            ("NonLocalACController.connect_mfli", "name"),                                   # NONLOCAL_MFLI_DAQ_METHODS, on LabOne's class
            ("RTEPanel.safe_close_ppms", "name"),                                            # a tuple of literals, set to None
        })
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute) and node.value.attr == "__dict__":
                self.assertIsInstance(node.slice, ast.Constant, ast.unparse(node))


if __name__ == "__main__":
    unittest.main()
