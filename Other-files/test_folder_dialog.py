"""The program's own folder dialog (user, 2026-11-15: "make the file folder
in our program editable? e.g. delete folder, rename folder and create
folder"): every filedialog.askdirectory opens it, and it can make, rename
and delete folders.

FolderRuleTests need no window (the rules and the file operations);
RecycleBinTests run on Windows only (a real folder into the real Recycle
Bin); FolderDialogWindowTests drive the real dialog and are skipped where
no window can open.
"""
import os
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from test_ppms_motor_debug import app


def posix(path) -> str:
    """A path as the dialog returns it."""
    return Path(os.path.abspath(str(path))).as_posix()


class Folders(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.tmp = Path(holder.name)

    def make(self, *names, files=()):
        for name in names:
            (self.tmp / name).mkdir(parents=True)
        for name in files:
            (self.tmp / name).write_text("data", encoding="utf-8")

    def open_run(self, sample="sample"):
        """A scan's open run folder <tmp>/<sample>/run."""
        (self.tmp / sample).mkdir(exist_ok=True)
        recorder = app.ScanRunRecorder(self.tmp / sample, "SHHV", "run", {})
        self.addCleanup(recorder.close, "test_end")
        return recorder


class FolderRuleTests(Folders):
    def test_a_folder_name_is_a_valid_windows_name(self):
        for name in ("SRO16", "A0-10Kohm", "2026.11 Py series", "run_01", "a.b"):
            self.assertEqual(app.folder_name_problem(name), "", name)
        for name in ("a/b", "a\\b", "a:b", "what?", "star*", "<x>", 'q"q', "pipe|", "dot.", " lead", ".git",
                     "trail ", ".", "..", "CON", "nul", "COM1.txt", "LPT9", "tab\tname", "x" * 256):
            self.assertEqual(app.folder_name_problem(name), app.FOLDER_DIALOG_NAME_RULE, name)
        for name in ("", "   "):
            self.assertEqual(app.folder_name_problem(name), "Type a name.")

    def test_the_list_is_in_the_order_of_tks_dialog(self):
        """The user's folders, as Tk's dialog showed them (figure, 2026-11-15)."""
        shown = ["A0-10Kohm", "A0-10ohm", "A2-PtPy", "A3", "B15", "B16",
                 "SF01", "SF04", "SRO2", "SRO14", "SRO16", "SRO20"]
        self.make(*reversed(shown), ".hidden", files=("notes.txt",))
        self.assertEqual(app.list_subfolders(self.tmp), shown)
        self.assertEqual(sorted(["b", "A", "a10", "a9", "B"], key=app.folder_name_sort_key)[:1], ["A"])
        with self.assertRaises(OSError):
            app.list_subfolders(self.tmp / "missing")

    def test_new_folder(self):
        made = app.make_subfolder(self.tmp, "SRO21")
        self.assertEqual(made, self.tmp / "SRO21")
        self.assertTrue(made.is_dir())
        with self.assertRaisesRegex(ValueError, "SRO21 is already there"):
            app.make_subfolder(self.tmp, "SRO21")
        (self.tmp / "file.txt").write_text("x", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "file.txt is already there"):
            app.make_subfolder(self.tmp, "file.txt")
        with self.assertRaisesRegex(ValueError, "valid Windows folder name"):
            app.make_subfolder(self.tmp, "a/b")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["SRO21", "file.txt"])

    def test_rename_keeps_what_the_folder_holds(self):
        self.make("old/run", "taken", files=("old/run/data.csv",))
        renamed = app.rename_subfolder(self.tmp / "old", "new")
        self.assertEqual(renamed, self.tmp / "new")
        self.assertEqual((self.tmp / "new/run/data.csv").read_text(encoding="utf-8"), "data")
        self.assertFalse((self.tmp / "old").exists())
        # Never onto a name that is taken (os.rename would replace an empty
        # folder without a word), never a bad name; the same name is no change.
        with self.assertRaisesRegex(ValueError, "taken is already there"):
            app.rename_subfolder(self.tmp / "new", "taken")
        with self.assertRaisesRegex(ValueError, "valid Windows folder name"):
            app.rename_subfolder(self.tmp / "new", "new?")
        self.assertEqual(app.rename_subfolder(self.tmp / "new", "new"), self.tmp / "new")
        with self.assertRaisesRegex(ValueError, "gone is not a folder any more"):
            app.rename_subfolder(self.tmp / "gone", "x")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["new", "taken"])

    def test_rename_may_change_the_capitals_only(self):
        self.make("sro2")
        app.rename_subfolder(self.tmp / "sro2", "SRO2")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["SRO2"])

    def test_what_a_folder_holds_is_counted_to_a_limit(self):
        self.make("s/a/b", "s/c", files=("s/1.csv", "s/a/2.csv", "s/a/b/3.csv"))
        self.assertEqual(app.folder_contents(self.tmp / "s"), (3, 3, 12, True))
        self.assertEqual(app.folder_contents(self.tmp / "s" / "c"), (0, 0, 0, True))
        files, folders, _size, complete = app.folder_contents(self.tmp / "s", limit=1)
        self.assertFalse(complete)
        self.assertGreater(files + folders, 1)

    @unittest.skipIf(sys.platform == "win32", "links and permissions as on the Mac and Linux")
    def test_a_folder_that_is_not_all_counted_is_not_deleted_here(self):
        """Review, 2026-11-15: a folder that could not be read was called
        empty, and a link in it was followed."""
        self.make("locked/in", "linked", "target", files=("locked/in/data.csv", "target/data.csv"))
        os.symlink(self.tmp / "target", self.tmp / "linked" / "link", target_is_directory=True)
        os.chmod(self.tmp / "locked" / "in", 0)
        self.addCleanup(os.chmod, self.tmp / "locked" / "in", 0o700)
        self.assertEqual(app.folder_contents(self.tmp / "linked"), (0, 1, 0, False))
        self.assertEqual(app.folder_contents(self.tmp / "locked"), (0, 1, 0, False))
        for name in ("linked", "locked"):
            with self.assertRaisesRegex(ValueError, f"{name} holds more than is counted here .*"
                                                    "Delete it in the Windows Explorer"):
                app.folder_delete_question(self.tmp / name)
        with mock.patch.object(app, "FOLDER_DIALOG_COUNT_LIMIT", 0), \
                self.assertRaisesRegex(ValueError, r"more than is counted here \(0 files and folders\)"):
            app.folder_delete_question(self.tmp / "target")
        self.assertTrue((self.tmp / "target/data.csv").exists())

    def test_an_empty_folder_is_removed(self):
        self.make("empty")
        how, question = app.folder_delete_question(self.tmp / "empty")
        self.assertEqual((how, question), ("empty", "Delete the empty folder empty?"))
        app.delete_subfolder(self.tmp / "empty", how)
        self.assertFalse((self.tmp / "empty").exists())

    def test_a_folder_with_data_only_goes_to_the_recycle_bin(self):
        self.make("SRO16/run", files=("SRO16/run/run.csv", "SRO16/notes.txt"))
        folder = self.tmp / "SRO16"
        # Windows would not recycle it (no bin, the bin off, too large): refused.
        for reason in ("There is no Recycle Bin for it here", "The Recycle Bin is switched off for its drive"):
            with mock.patch.object(app, "recycle_bin_refusal", return_value=reason) as check, \
                    mock.patch.object(app, "move_folder_to_recycle_bin") as move:
                with self.assertRaisesRegex(
                        ValueError, rf"SRO16 holds 2 files and 1 folder \(8 bytes\)\. {reason}, so only "
                                    r"an empty folder can be deleted in this window"):
                    app.folder_delete_question(folder)
                check.assert_called_once_with(folder, 8)
                # Asked for all the same (the bin switched off meanwhile).
                with self.assertRaisesRegex(ValueError, f"{reason}, so only an empty folder"):
                    app.delete_subfolder(folder, "recycle")
                move.assert_not_called()
        self.assertTrue((folder / "run/run.csv").exists())
        # Otherwise: asked, saying what it holds, then moved there.
        with mock.patch.object(app, "recycle_bin_refusal", return_value=""), \
                mock.patch.object(app, "recycle_bin_item_count", side_effect=[3, 4, 4, 4]), \
                mock.patch.object(app, "move_folder_to_recycle_bin") as move:
            how, question = app.folder_delete_question(folder)
            self.assertEqual(how, "recycle")
            self.assertEqual(question, "Delete the folder SRO16?\n\nIt holds 2 files and 1 folder (8 bytes). "
                                       "Windows moves it to the Recycle Bin, where it can be restored.")
            self.assertEqual(app.delete_subfolder(folder, how, 77), "")
            move.assert_called_once_with(folder, 77)
            # The bin did not gain an item: said, not hidden.
            self.assertEqual(app.delete_subfolder(folder, how),
                             "SRO16 is gone. The Recycle Bin did not gain an item, so check that it is "
                             "in there: Windows may have deleted it for good.")
        # An "empty" delete of a folder that holds something by now: not removed.
        with self.assertRaises(OSError):
            app.delete_subfolder(folder, "empty")
        with self.assertRaisesRegex(ValueError, "Unknown way"):
            app.delete_subfolder(folder, "for good")
        self.assertTrue((folder / "run/run.csv").exists())

    def test_while_a_scan_runs_no_folder_with_data_is_deleted(self):
        """Review, 2026-11-15: Windows moves the folder on the Tk thread,
        which a running scan's steps need."""
        self.make("old/run", "empty", files=("old/run/run.csv",))
        recorder = self.open_run("sample")
        with mock.patch.object(app, "recycle_bin_refusal", return_value=""), \
                mock.patch.object(app, "folder_contents") as count, \
                mock.patch.object(app, "move_folder_to_recycle_bin") as move:
            for call in (lambda: app.folder_delete_question(self.tmp / "old"),
                         lambda: app.delete_subfolder(self.tmp / "old", "recycle")):
                with self.assertRaisesRegex(ValueError, "A scan is running. A folder with data can be "
                                                        "deleted here once it has ended"):
                    call()
            count.assert_not_called()
            move.assert_not_called()
            # An empty one, a new one and a rename take no time: allowed.
            self.assertEqual(app.folder_delete_question(self.tmp / "empty")[0], "empty")
            app.delete_subfolder(self.tmp / "empty", "empty")
            app.rename_subfolder(self.tmp / "old", "older")
            app.make_subfolder(self.tmp, "new")
            recorder.close("completed")
            count.return_value = (1, 1, 4, True)
            self.assertEqual(app.folder_delete_question(self.tmp / "older")[0], "recycle")
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["new", "older", "sample"])

    def test_a_scans_image_folder_is_held_as_its_run_folder_is(self):
        """Review, 2026-11-15: a MOKE scan's images go into a folder of
        their own, made again by the next image if it is renamed."""
        self.make("images/MOKE_field_scan_1", "images/other")
        recorder = self.open_run("sample")
        recorder.also_saves_into(self.tmp / "images" / "MOKE_field_scan_1")
        for folder in (self.tmp / "images", self.tmp / "images" / "MOKE_field_scan_1"):
            self.assertEqual(app.scan_run_using_folder(folder), self.tmp / "images" / "MOKE_field_scan_1")
            with self.assertRaisesRegex(ValueError, "A running scan is saving into"):
                app.rename_subfolder(folder, "renamed")
        self.assertIsNone(app.scan_run_using_folder(self.tmp / "images" / "other"))
        recorder.close("completed")
        self.assertIsNone(app.scan_run_using_folder(self.tmp / "images"))

    @unittest.skipIf(sys.platform == "win32", "making a link needs a privilege on Windows")
    def test_a_run_folder_reached_another_way_is_the_same_folder(self):
        self.make("real")
        os.symlink(self.tmp / "real", self.tmp / "alias", target_is_directory=True)
        recorder = app.ScanRunRecorder(self.tmp / "alias", "SHHV", "run", {})
        self.addCleanup(recorder.close, "test_end")
        self.assertEqual(app.scan_run_using_folder(self.tmp / "real"), recorder.directory)
        with self.assertRaisesRegex(ValueError, "A running scan is saving into"):
            app.rename_subfolder(self.tmp / "real", "renamed")

    def test_the_folder_of_a_running_scan_is_not_renamed_or_deleted(self):
        self.make("sample2")
        recorder = self.open_run("sample")
        run = recorder.directory
        self.assertEqual(run, self.tmp / "sample" / "run")
        for folder in (self.tmp / "sample", run):
            self.assertEqual(app.scan_run_using_folder(folder), run)
            with self.assertRaisesRegex(ValueError, "A running scan is saving into .*sample/run; "
                                                    f"{folder.name} cannot be renamed until"):
                app.rename_subfolder(folder, "other")
            for call in (lambda: app.folder_delete_question(folder),
                         lambda: app.delete_subfolder(folder, "recycle")):
                with self.assertRaisesRegex(ValueError, f"{folder.name} cannot be deleted until that scan"):
                    call()
        # A folder beside it, even one whose name starts the same, is free.
        self.assertIsNone(app.scan_run_using_folder(self.tmp / "sample2"))
        self.assertEqual(app.rename_subfolder(self.tmp / "sample2", "sample3"), self.tmp / "sample3")
        self.assertTrue(run.is_dir())
        # Once the scan has ended, so is its folder.
        recorder.close("completed")
        self.assertIsNone(app.scan_run_using_folder(self.tmp / "sample"))
        self.assertEqual(app.rename_subfolder(self.tmp / "sample", "sample1"), self.tmp / "sample1")

    def test_a_run_that_did_not_start_does_not_hold_its_folder(self):
        self.make("sample")
        with mock.patch.object(app.ScanRunRecorder, "event", side_effect=RuntimeError("disk")), \
                self.assertRaises(RuntimeError):
            app.ScanRunRecorder(self.tmp / "sample", "SHHV", "run", {})
        self.assertIsNone(app.scan_run_using_folder(self.tmp / "sample"))

    @unittest.skipIf(sys.platform == "win32", "making a link needs a privilege on Windows")
    def test_a_link_to_another_folder_is_not_deleted(self):
        self.make("real", files=("real/data.csv",))
        os.symlink(self.tmp / "real", self.tmp / "link", target_is_directory=True)
        self.assertTrue(app.folder_is_link(self.tmp / "link"))
        self.assertFalse(app.folder_is_link(self.tmp / "real"))
        for call in (lambda: app.folder_delete_question(self.tmp / "link"),
                     lambda: app.delete_subfolder(self.tmp / "link", "recycle")):
            with self.assertRaisesRegex(ValueError, "link is a link to another folder"):
                call()
        self.assertTrue((self.tmp / "real/data.csv").exists())

    @unittest.skipIf(sys.platform == "win32", "Windows has a Recycle Bin")
    def test_there_is_no_recycle_bin_off_windows(self):
        self.make("s", files=("s/data.csv",))
        self.assertTrue(app.recycle_bin_refusal(self.tmp))
        self.assertIsNone(app.recycle_bin_item_count(self.tmp))
        with self.assertRaisesRegex(OSError, "no Recycle Bin"):
            app.move_folder_to_recycle_bin(self.tmp / "s")
        with self.assertRaisesRegex(ValueError, "only an empty folder can be deleted"):
            app.folder_delete_question(self.tmp / "s")
        self.assertTrue((self.tmp / "s/data.csv").exists())

    def test_where_the_dialog_opens(self):
        self.make("raw/SRO16")
        with mock.patch.object(app, "_FOLDER_DIALOG_LAST_DIRECTORY", ""):
            start = app.folder_dialog_start_directory
            self.assertEqual(start(self.tmp / "raw"), Path(os.path.abspath(self.tmp / "raw")))
            # A folder that is gone (renamed or deleted): the nearest above it.
            self.assertEqual(start(self.tmp / "raw/gone/run"), Path(os.path.abspath(self.tmp / "raw")))
            self.assertEqual(start(""), Path(os.path.abspath(os.getcwd())))
            # No folder named: where the last dialog was.
            with mock.patch.object(app, "_FOLDER_DIALOG_LAST_DIRECTORY", str(self.tmp / "raw/SRO16")):
                self.assertEqual(start(""), Path(os.path.abspath(self.tmp / "raw/SRO16")))
                self.assertEqual(start(self.tmp), Path(os.path.abspath(self.tmp)))

    def test_every_folder_choice_opens_the_programs_dialog(self):
        import tkinter.filedialog as tk_filedialog
        import tkinter.messagebox as tk_messagebox
        for module, name in ((tk_filedialog, "askdirectory"), (tk_messagebox, "_show")):
            self.addCleanup(setattr, module, name, getattr(module, name))
        self.addCleanup(setattr, app, "_NATIVE_ASK_DIRECTORY", app._NATIVE_ASK_DIRECTORY)
        self.addCleanup(setattr, app, "_NATIVE_MESSAGE_SHOW", app._NATIVE_MESSAGE_SHOW)
        native = tk_filedialog.__dict__.get("_english_native_askdirectory") or tk_filedialog.askdirectory
        self.assertTrue(app.use_english_tk_dialogs(mock.Mock()))
        self.assertIs(app.filedialog.askdirectory, app.editable_folder_dialog)
        self.assertIs(app._NATIVE_ASK_DIRECTORY, native)
        self.assertIsNot(native, app.editable_folder_dialog)
        # A second time (another copy of the program in one process): Tk's
        # own is still the one kept.
        self.assertTrue(app.use_english_tk_dialogs(mock.Mock()))
        self.assertIs(app._NATIVE_ASK_DIRECTORY, native)
        # A parent that is not a Tk window (the tests' stand-ins): Tk's own.
        with mock.patch.object(app, "_NATIVE_ASK_DIRECTORY", return_value="C:/x") as tk_dialog:
            self.assertEqual(app.filedialog.askdirectory(parent=object(), title="T"), "C:/x")
            tk_dialog.assert_called_once()
            self.assertEqual(tk_dialog.call_args.kwargs["title"], "T")


@unittest.skipUnless(sys.platform == "win32", "the Windows Recycle Bin")
class RecycleBinTests(Folders):
    NAME = "transport_test_delete_me"

    def test_a_folder_with_data_goes_to_the_real_recycle_bin(self):
        self.make(f"{self.NAME}/run", files=(f"{self.NAME}/run/run.csv",))
        folder = self.tmp / self.NAME
        # The checks first: a refusal here fails the test at once, and no
        # question of Windows can wait for an answer.
        self.assertEqual(app.recycle_bin_refusal(folder, 4), "")
        self.assertFalse(app.recycle_bin_refusal(folder))
        root = app._windows_drive_root(folder)
        self.assertRegex(root, r"^[A-Za-z]:\\$")
        switched_off, largest = app._recycle_bin_settings(root)
        self.assertFalse(switched_off)
        self.assertTrue(largest is None or largest > 4)
        self.assertGreater(app._windows_drive_size(root), 10 ** 9)
        before = app.recycle_bin_item_count(folder)
        self.assertIsNotNone(before)
        how, question = app.folder_delete_question(folder)
        self.assertEqual(how, "recycle")
        self.assertIn("Windows moves it to the Recycle Bin", question)
        self.assertEqual(app.delete_subfolder(folder, how), "", "the bin gained an item")
        self.assertFalse(folder.exists())
        # In the bin, not deleted for good.
        self.assertGreater(app.recycle_bin_item_count(folder), before)

    def test_what_windows_would_not_recycle_is_refused(self):
        self.make(f"{self.NAME}/run", files=(f"{self.NAME}/run/run.csv",))
        folder = self.tmp / self.NAME
        megabyte = 1024 * 1024
        for settings, size, reason in (
                ((True, None), 4, "The Recycle Bin is switched off for its drive"),
                ((False, 10 * megabyte), 20 * megabyte,
                 "It is larger than the Recycle Bin of its drive (10.0 MB)"),
                ((False, 10 * megabyte), megabyte, ""),
        ):
            with mock.patch.object(app, "_recycle_bin_settings", return_value=settings):
                self.assertEqual(app.recycle_bin_refusal(folder, size), reason)
        with mock.patch.object(app, "_recycle_bin_settings", side_effect=OSError("no registry")):
            self.assertEqual(app.recycle_bin_refusal(folder, 4),
                             "The Recycle Bin of its drive could not be checked (no registry)")
        # A network share has no bin.
        self.assertEqual(app._windows_drive_root(r"\\server\share\raw"), "")
        with mock.patch.object(app, "_recycle_bin_settings", return_value=(True, None)), \
                self.assertRaisesRegex(ValueError, "switched off for its drive, so only an empty folder"):
            app.folder_delete_question(folder)
        self.assertTrue((folder / "run" / "run.csv").exists())

    def test_a_folder_that_is_gone_is_an_error(self):
        with self.assertRaises(OSError):
            app.move_folder_to_recycle_bin(self.tmp / "missing")


class FolderDialogWindowTests(Folders):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as error:  # headless build server
            raise unittest.SkipTest(f"no display: {error}")
        cls.root.withdraw()
        import tkinter.filedialog as tk_filedialog
        import tkinter.messagebox as tk_messagebox
        cls.saved = [(tk_filedialog, "askdirectory", tk_filedialog.askdirectory),
                     (tk_messagebox, "_show", tk_messagebox._show),
                     (app, "_NATIVE_ASK_DIRECTORY", app._NATIVE_ASK_DIRECTORY),
                     (app, "_NATIVE_MESSAGE_SHOW", app._NATIVE_MESSAGE_SHOW)]
        app.use_english_tk_dialogs(cls.root)

    @classmethod
    def tearDownClass(cls):
        for target, name, value in cls.saved:
            setattr(target, name, value)
        cls.root.destroy()

    def setUp(self):
        super().setUp()
        # No box or prompt may wait for a person: each is a stand-in, unless
        # a test asks for the real ones (real_boxes) and answers them itself.
        self.errors, self.asked, self.warnings = [], [], []
        self.answer, self.typed, self.real_boxes = True, None, False
        for target, name, stand_in in (
                (app.messagebox, "showerror", lambda title, text, **_k: self.errors.append((title, text))),
                (app.messagebox, "showwarning", lambda title, text, **_k: self.warnings.append(text)),
                (app.messagebox, "askyesno", self._ask),
                (app.simpledialog, "askstring", lambda title, prompt, **k: self.typed)):
            patcher = mock.patch.object(target, name, self._or_real(getattr(target, name), stand_in))
            patcher.start()
            self.addCleanup(patcher.stop)
        # A dialog that could not be built must fail the test, not open Tk's
        # own dialog, which nothing here would close.
        patcher = mock.patch.object(app, "_NATIVE_ASK_DIRECTORY",
                                    side_effect=AssertionError("the program's dialog was not built"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _or_real(self, real, stand_in):
        return lambda *args, **options: (real if self.real_boxes else stand_in)(*args, **options)

    def _ask(self, title, text, **options):
        self.asked.append((title, text, options.get("default")))
        return self.answer

    def choose(self, *steps, **options):
        """Open the dialog as the program does and run steps(dialog) in it;
        the dialog is cancelled after the last step if it is still open."""
        root, failures, tries = self.root, [], [0]

        def run():
            tops = [w for w in root.winfo_children() if w.winfo_class() == "EditableFolderDialog"]
            if not tops:
                tries[0] += 1
                if tries[0] < 100:
                    root.after(50, run)
                return
            dialog = tops[-1].folder_dialog
            try:
                for step in steps:
                    step(dialog)
            except BaseException as error:  # shown by the test, after the dialog
                failures.append(error)
            finally:
                if not dialog.done.get():
                    dialog.cancel()

        root.after(100, run)
        options.setdefault("initialdir", str(self.tmp))
        result = app.filedialog.askdirectory(parent=root, **options)
        if failures:
            raise failures[0]
        self.assertEqual([w for w in root.winfo_children() if w.winfo_class() == "EditableFolderDialog"],
                         [], "closed")
        return result

    @staticmethod
    def pick(dialog, name):
        index = dialog.names.index(name)
        dialog.listbox.selection_clear(0, "end")
        dialog.listbox.selection_set(index)
        dialog._selection_changed()

    def test_the_dialog_lists_the_folders_and_is_in_english(self):
        self.make("SRO14", "SRO2", ".git", files=("readme.txt",))
        seen = {}

        def look(dialog):
            seen["title"] = dialog.top.title()
            seen["names"] = list(dialog.listbox.get(0, "end"))
            seen["texts"] = [str(b.cget("text")) for b in (
                dialog.up_button, dialog.new_button, dialog.rename_button, dialog.delete_button,
                dialog.ok_button, dialog.cancel_button)]
            seen["directory"] = dialog.directory_var.get()
            seen["selection"] = dialog.selection_var.get()
            seen["edit"] = [b.instate(["disabled"]) for b in (dialog.rename_button, dialog.delete_button)]
            seen["new"] = dialog.new_button.instate(["disabled"])
            self.pick(dialog, "SRO2")
            seen["picked"] = dialog.selection_var.get()
            seen["edit picked"] = [b.instate(["disabled"])
                                   for b in (dialog.rename_button, dialog.delete_button)]
            seen["keys"] = [bool(dialog.listbox.bind(key)) for key in (
                "<Double-Button-1>", "<Return>", "<F2>", "<Delete>", "<BackSpace>")]

        self.assertEqual(self.choose(look, title="SHHV live CSV folder"), "", "cancelled")
        self.assertEqual(seen, {
            "title": "SHHV live CSV folder", "names": ["SRO2", "SRO14"],
            "texts": ["Up", "New folder", "Rename", "Delete", "OK", "Cancel"],
            "directory": posix(self.tmp), "selection": posix(self.tmp),
            "edit": [True, True], "new": False, "picked": posix(self.tmp / "SRO2"),
            "edit picked": [False, False], "keys": [True] * 5,
        })

    def test_ok_gives_the_picked_folder_or_the_one_shown(self):
        self.make("A3/run1")

        def pick_a3(dialog):
            self.pick(dialog, "A3")
            dialog.ok_button.invoke()

        self.assertEqual(self.choose(pick_a3), posix(self.tmp / "A3"))
        self.assertEqual(self.choose(lambda dialog: dialog.ok_button.invoke()), posix(self.tmp))

        def into_a3_and_back(dialog):
            self.pick(dialog, "A3")
            dialog.open_selected()
            self.assertEqual((dialog.directory_var.get(), list(dialog.listbox.get(0, "end"))),
                             (posix(self.tmp / "A3"), ["run1"]))
            dialog.up_button.invoke()
            # Back above, with the folder it came from picked.
            self.assertEqual(dialog.selection_var.get(), posix(self.tmp / "A3"))
            self.assertTrue(dialog.go_to(str(self.tmp / "A3" / "run1")))
            dialog.ok_button.invoke()

        self.assertEqual(self.choose(into_a3_and_back), posix(self.tmp / "A3" / "run1"))
        self.assertEqual(self.errors, [])

    def test_without_a_folder_named_it_opens_where_the_last_one_was(self):
        self.make("raw/SRO16")
        self.choose(lambda dialog: dialog.go_to(str(self.tmp / "raw")))
        seen = []

        def look(dialog):
            seen.append(dialog.directory_var.get())

        self.assertEqual(self.choose(look, initialdir=""), "")
        self.assertEqual(seen, [posix(self.tmp / "raw")])
        self.assertIs(app.filedialog.askdirectory, app.editable_folder_dialog)

    def test_new_folder(self):
        self.make("SRO2")

        def new(dialog):
            self.typed = " SRO21 "
            dialog.new_button.invoke()
            self.assertEqual(list(dialog.listbox.get(0, "end")), ["SRO2", "SRO21"])
            self.assertEqual(dialog.selection_var.get(), posix(self.tmp / "SRO21"), "picked")
            for bad in ("SRO2", "a/b", ""):
                self.typed = bad
                dialog.new_button.invoke()
            self.typed = None  # the prompt cancelled
            dialog.new_button.invoke()
            dialog.ok_button.invoke()

        self.assertEqual(self.choose(new), posix(self.tmp / "SRO21"))
        self.assertEqual(self.errors, [
            ("New folder", "The folder was not made: SRO2 is already there."),
            ("New folder", f"The folder was not made: {app.FOLDER_DIALOG_NAME_RULE}"),
            ("New folder", "The folder was not made: Type a name."),
        ])
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["SRO2", "SRO21"])

    def test_rename(self):
        self.make("old/run", "taken", files=("old/run/run.csv",))

        def rename(dialog):
            self.pick(dialog, "old")
            self.typed = "taken"
            dialog.rename_button.invoke()
            self.assertEqual(dialog.selection_var.get(), posix(self.tmp / "old"), "still picked")
            self.typed = "SRO16"
            dialog.rename_button.invoke()
            self.assertEqual(list(dialog.listbox.get(0, "end")), ["SRO16", "taken"])
            dialog.ok_button.invoke()

        self.assertEqual(self.choose(rename), posix(self.tmp / "SRO16"))
        self.assertEqual(self.errors, [("Rename folder", "old was not renamed: taken is already there.")])
        self.assertEqual((self.tmp / "SRO16/run/run.csv").read_text(encoding="utf-8"), "data")

    def test_delete_asks_first_and_no_is_the_default(self):
        self.make("empty", "keep")

        def delete(dialog):
            self.pick(dialog, "empty")
            self.answer = False
            dialog.delete_button.invoke()
            self.assertTrue((self.tmp / "empty").is_dir(), "No: nothing deleted")
            self.answer = True
            dialog.delete_button.invoke()
            self.assertEqual(list(dialog.listbox.get(0, "end")), ["keep"])
            self.assertEqual(dialog.selection_var.get(), posix(self.tmp), "nothing picked")
            dialog.delete_button.invoke()  # nothing picked: nothing happens

        self.assertEqual(self.choose(delete), "")
        self.assertEqual(self.asked, [("Delete folder", "Delete the empty folder empty?", "no")] * 2)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["keep"])
        self.assertEqual(self.errors, [])

    def test_delete_of_a_folder_with_data(self):
        name = "transport_test_delete_me"
        self.make(f"{name}/run", files=(f"{name}/run/run.csv",))

        def delete(dialog):
            self.pick(dialog, name)
            dialog.delete_button.invoke()

        self.assertEqual(self.choose(delete), "")
        if sys.platform == "win32":
            # Asked, then into the Recycle Bin.
            self.assertEqual(self.errors, [])
            self.assertEqual([(title, default) for title, _text, default in self.asked],
                             [("Delete folder", "no")])
            self.assertIn("It holds 1 file and 1 folder (4 bytes). Windows moves it to the Recycle Bin",
                          self.asked[0][1])
            self.assertFalse((self.tmp / name).exists())
            self.assertEqual(self.warnings, [], "the bin gained an item")
        else:
            # No Recycle Bin: not even asked, and the data is still there.
            self.assertEqual(self.asked, [])
            self.assertEqual(len(self.errors), 1)
            self.assertIn("There is no Recycle Bin for it here, so only an empty folder can be deleted",
                          self.errors[0][1])
            self.assertTrue((self.tmp / name / "run" / "run.csv").exists())

    def test_a_warning_after_the_delete_is_shown(self):
        self.make("old/run")

        def delete(dialog):
            self.pick(dialog, "old")
            with mock.patch.object(app, "folder_delete_question", return_value=("recycle", "Delete?")), \
                    mock.patch.object(app, "delete_subfolder", return_value="old is gone. Check the bin."):
                dialog.delete_button.invoke()

        self.assertEqual(self.choose(delete), "")
        self.assertEqual(self.warnings, ["old is gone. Check the bin."])

    def test_the_real_prompt_and_box_give_the_dialog_back(self):
        """Review, 2026-11-15: the hand-over of the input (grab) between the
        dialog, the name prompt and the Yes/No box, with the real windows."""
        problems = []

        def later(dialog, action):
            def run():
                try:
                    action()
                except BaseException as error:  # close what is open, so nothing waits
                    problems.append(error)
                    for window in dialog.top.winfo_children():
                        if isinstance(window, app.simpledialog.Dialog):
                            window.cancel()
                        elif window.winfo_class() == "EnglishMessageBox":
                            self._press(window, "no")
            self.root.after(400, run)

        def type_name(dialog):
            prompt = next(w for w in dialog.top.winfo_children() if isinstance(w, app.simpledialog.Dialog))
            prompt.entry.insert(0, "made here")
            prompt.ok()

        def press_yes(dialog):
            box = next(w for w in dialog.top.winfo_children() if w.winfo_class() == "EnglishMessageBox")
            self.assertTrue(self._press(box, "yes"))

        def grab(dialog):
            return str(self.root.tk.call("grab", "current", dialog.top._w))

        def chain(dialog):
            self.real_boxes = True
            later(dialog, lambda: type_name(dialog))
            dialog.new_button.invoke()
            self.assertEqual(list(dialog.listbox.get(0, "end")), ["made here"])
            self.assertEqual(grab(dialog), str(dialog.top), "the dialog has the input again")
            later(dialog, lambda: press_yes(dialog))
            dialog.delete_button.invoke()
            self.assertEqual(list(dialog.listbox.get(0, "end")), [])
            self.assertEqual(grab(dialog), str(dialog.top), "and again after the Yes/No box")
            dialog.ok_button.invoke()

        self.assertEqual(self.choose(chain), posix(self.tmp))
        self.assertEqual(problems, [])
        self.assertEqual(list(self.tmp.iterdir()), [])

    @staticmethod
    def _press(box, name) -> bool:
        pending = [box]
        while pending:
            widget = pending.pop()
            if widget.winfo_class() == "TButton" and widget.winfo_name() == name:
                widget.invoke()
                return True
            pending.extend(widget.winfo_children())
        return False

    def test_the_program_closing_ends_the_dialog(self):
        """Review, 2026-11-15: the window destroyed from outside left show()
        waiting for ever."""
        self.assertEqual(self.choose(lambda dialog: dialog.top.destroy()), "")

    def test_the_folder_of_a_running_scan_is_refused_in_the_dialog(self):
        recorder = self.open_run("sample")

        def try_both(dialog):
            self.pick(dialog, "sample")
            self.typed = "renamed"
            dialog.rename_button.invoke()
            dialog.delete_button.invoke()

        self.assertEqual(self.choose(try_both), "")
        self.assertEqual([title for title, _text in self.errors], ["Rename folder", "Delete folder"])
        for _title, text in self.errors:
            self.assertIn("A running scan is saving into", text)
        self.assertEqual(self.asked, [])
        self.assertTrue(recorder.csv_path.exists())
        recorder.close("completed")

    def test_a_typed_folder_that_does_not_exist(self):
        target = self.tmp / "new" / "deeper"

        def type_it(dialog):
            dialog.selection_var.set(str(target))
            dialog.ok_button.invoke()

        # mustexist: refused, the dialog stays open (the test cancels it).
        self.assertEqual(self.choose(type_it, mustexist=True), "")
        self.assertEqual(self.errors, [("Choose a folder", f"{posix(target)} does not exist.")])
        self.assertFalse(target.exists())
        # Otherwise asked; No leaves it, Yes makes it and gives it.
        self.answer = False
        self.assertEqual(self.choose(type_it), "")
        self.assertFalse(target.exists())
        self.answer = True
        self.assertEqual(self.choose(type_it), posix(target))
        self.assertTrue(target.is_dir())
        self.assertEqual([text for _title, text, _default in self.asked],
                         [f"{posix(target)} does not exist. Make it?"] * 2)

    def test_a_file_is_not_a_folder(self):
        self.make(files=("data.csv",))

        def type_it(dialog):
            dialog.selection_var.set(str(self.tmp / "data.csv"))
            dialog.ok_button.invoke()
            self.assertFalse(dialog.go_to(str(self.tmp / "data.csv")))
            self.assertEqual(dialog.directory_var.get(), posix(self.tmp))

        self.assertEqual(self.choose(type_it), "")
        self.assertEqual(self.errors, [
            ("Choose a folder", f"{posix(self.tmp / 'data.csv')} is not a folder."),
            ("Choose a folder", f"{self.tmp / 'data.csv'} is not a folder."),
        ])


if __name__ == "__main__":
    unittest.main()
