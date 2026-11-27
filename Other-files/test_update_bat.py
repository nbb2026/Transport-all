"""Update_Transport_<X>.bat: the lab computer's updater of this branch's
program (user, 2026-11-27: "a program that I can put it on the experimental
computer to let it automatically download the newest RT exe program to the same
file folder"; then "also make the updater for PPMS, MOKE and FMR").  The same
tests on each of the four branches: the names are read from the script.

It is a cmd.exe script, so these run on Windows only.  They serve a stand-in
release from this computer (a copy of the script with its two addresses
changed), so nothing depends on the network or on the real release; the one
test against GitHub itself runs only when UPDATE_BAT_LIVE is set."""

import functools
import hashlib
import http.server
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT, = ROOT.glob("Update_Transport_*.bat")
NAME = SCRIPT.stem[len("Update_"):]          # Transport_RT
BRANCH = NAME.replace("_", "-")              # Transport-RT
KEY = NAME[len("Transport_"):].lower()       # rt
EXE = f"{NAME}.exe"
WINDOWS = sys.platform == "win32"


def run_script(script, *args, **options):
    """As a double-click runs it: cmd.exe /c with the whole command inside
    one pair of quotes (/s), so a folder name with spaces, an ampersand or
    brackets reaches cmd.exe as one quoted path.  A plain argument list does
    not: cmd.exe drops the quotes Python puts round the path."""
    command = f'cmd.exe /d /s /c ""{script}" {" ".join(("quiet", *args))}"'
    done = subprocess.run(command, capture_output=True, text=True, stdin=subprocess.DEVNULL, **options)
    return done.returncode, done.stdout + done.stderr


class TheFile(unittest.TestCase):
    def test_it_is_ascii_with_crlf_and_names_this_programs_release(self):
        raw = SCRIPT.read_bytes()
        raw.decode("ascii")
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""), "cmd.exe needs CRLF")
        text = raw.decode("ascii")
        self.assertTrue((ROOT / f"{NAME}.py").is_file(), "the script is this branch's program's")
        self.assertIn(f'set "NAME={NAME}"', text)
        self.assertIn(f'set "VERSION_URL=https://raw.githubusercontent.com/nbb2026/Transport-all/{BRANCH}/pyproject.toml"', text)
        self.assertIn('set "RELEASE_URL=https://github.com/nbb2026/Transport-all/releases/download"', text)
        self.assertIn(f'set "TAG_PREFIX={KEY}-v"', text)
        # The tag prefix is the one the release workflow uses.
        workflow = (ROOT / ".github" / "workflows" / f"{KEY}-windows-exe.yml").read_text(encoding="utf-8")
        self.assertIn(f"RELEASE_TAG_PREFIX: {KEY}-v", workflow)
        # The folder is found before the options are read ("shift" moves %0).
        self.assertLess(text.index('pushd "%~dp0"'), text.index(":arguments"))
        # It starts nothing unless asked to.
        self.assertIn('set "START_AFTER=0"', text)

    def test_the_version_line_it_reads_is_in_pyproject(self):
        lines = [line for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines() if line.startswith("version")]
        self.assertEqual(len(lines), 1)
        self.assertRegex(lines[0], r'^version = "[0-9][0-9.]*"$')


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


@unittest.skipUnless(WINDOWS, "a cmd.exe script")
class AgainstAStandInRelease(unittest.TestCase):
    NEW = b"MZ the new program " + bytes(range(256)) * 400
    OLD = b"MZ the old program"

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rt update "))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.site = self.tmp / "site"
        self.release = self.site / "download" / f"{KEY}-v9.9"
        self.release.mkdir(parents=True)
        (self.site / "pyproject.toml").write_text('# version of the tool\n[project]\nname = "x"\nversion = "9.9"\n', encoding="utf-8")
        self.publish(self.NEW)
        (self.release / "BUILD_INFO.txt").write_text(f"{EXE}, program version 9.9\nCommit: abc ({BRANCH})\nBuilt: today\n", encoding="utf-8")
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(self.site)))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        # A folder name cmd.exe trips over when a script is careless.
        self.folder = self.tmp / "3-Transport-SHHV & Switch (lab)"
        self.folder.mkdir()
        text = SCRIPT.read_bytes().decode("ascii")
        for name, value in (("VERSION_URL", f"{self.base}/pyproject.toml"), ("RELEASE_URL", f"{self.base}/download")):
            start = text.index(f'set "{name}=')
            end = text.index('"\r\n', start)
            text = text[:start] + f'set "{name}={value}' + text[end:]
        self.script = self.folder / SCRIPT.name
        self.script.write_bytes(text.encode("ascii"))
        self.exe = self.folder / EXE
        self.previous = self.folder / f"{NAME}_previous.exe"

    def publish(self, content, sha=None):
        (self.release / EXE).write_bytes(content)
        sha = hashlib.sha256(content).hexdigest() if sha is None else sha
        (self.release / f"{EXE}.sha256").write_bytes(f"{sha}  {EXE}\n".encode("ascii"))

    def run_it(self, *args):
        return run_script(self.script, *args, cwd=str(self.tmp), timeout=300)

    def left_over(self):
        return sorted(p.name for p in self.folder.iterdir() if p.name not in (SCRIPT.name, EXE, f"{NAME}_previous.exe", f"{NAME}_BUILD_INFO.txt"))

    def test_an_empty_folder_gets_the_exe(self):
        code, said = self.run_it()
        self.assertEqual(code, 0, said)
        self.assertEqual(self.exe.read_bytes(), self.NEW)
        self.assertIn(f"UPDATED: {EXE} is now the newest (version 9.9).", said)
        self.assertIn(f"Commit: abc ({BRANCH})", said)
        self.assertIn(f"Folder: {self.folder}", said)
        self.assertNotIn("is not recognized", said)
        self.assertFalse(self.previous.exists())
        self.assertEqual(self.left_over(), [])

    def test_an_option_does_not_change_the_folder(self):
        """Found on the first Windows run, 2026-11-27: after "shift" %~dp0
        was the option's folder, so the exe landed where the script was
        started from.  cwd here is not the script's folder."""
        self.exe.write_bytes(self.OLD)
        code, said = self.run_it()
        self.assertEqual(code, 0, said)
        self.assertIn(f"Folder: {self.folder}", said)
        self.assertEqual(self.exe.read_bytes(), self.NEW)
        self.assertFalse((self.tmp / EXE).exists())
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), sorted([self.folder.name, "site"]))

    def test_an_old_exe_is_replaced_and_kept_as_previous(self):
        self.exe.write_bytes(self.OLD)
        code, said = self.run_it()
        self.assertEqual(code, 0, said)
        self.assertEqual(self.exe.read_bytes(), self.NEW)
        self.assertEqual(self.previous.read_bytes(), self.OLD)
        self.assertIn(f"kept as {NAME}_previous.exe", said)
        self.assertEqual(self.left_over(), [])

    def test_the_newest_exe_is_left_alone(self):
        self.exe.write_bytes(self.NEW)
        before = self.exe.stat().st_mtime_ns
        code, said = self.run_it()
        self.assertEqual(code, 0, said)
        self.assertIn("UP TO DATE", said)
        self.assertNotIn("Downloading", said)
        self.assertEqual(self.exe.stat().st_mtime_ns, before)
        self.assertFalse(self.previous.exists())
        self.assertEqual(self.left_over(), [])

    def test_a_download_that_does_not_match_its_sha256_changes_nothing(self):
        self.exe.write_bytes(self.OLD)
        self.publish(self.NEW, sha="0" * 64)
        code, said = self.run_it()
        self.assertEqual(code, 1, said)
        self.assertIn("NOT UPDATED: the downloaded file does not match its SHA-256", said)
        self.assertEqual(self.exe.read_bytes(), self.OLD)
        self.assertFalse(self.previous.exists())
        self.assertEqual(self.left_over(), [])

    def test_a_version_whose_files_are_not_there_yet_changes_nothing(self):
        self.exe.write_bytes(self.OLD)
        (self.site / "pyproject.toml").write_text('version = "10.0"\n', encoding="utf-8")
        code, said = self.run_it()
        self.assertEqual(code, 1, said)
        self.assertIn("NOT UPDATED: the files of version 10.0 are not on GitHub yet", said)
        self.assertEqual(self.exe.read_bytes(), self.OLD)
        self.assertEqual(self.left_over(), [])

    def test_no_connection_changes_nothing(self):
        self.exe.write_bytes(self.OLD)
        self.server.shutdown()
        self.server.server_close()
        code, said = self.run_it()
        self.assertEqual(code, 1, said)
        self.assertIn("NOT UPDATED: GitHub could not be reached", said)
        self.assertEqual(self.exe.read_bytes(), self.OLD)
        self.assertEqual(self.left_over(), [])

    def test_a_version_or_a_sha256_that_is_not_one_is_refused(self):
        self.exe.write_bytes(self.OLD)
        (self.release / f"{EXE}.sha256").write_bytes(b"not a hash & echo owned\n")
        code, said = self.run_it()
        self.assertEqual(code, 1, said)
        self.assertIn("the SHA-256 file on GitHub could not be read", said)
        self.assertNotIn("owned\n", said.replace("echo owned", ""))
        (self.site / "pyproject.toml").write_text('version = "1.0&calc"\n', encoding="utf-8")
        code, said = self.run_it()
        self.assertEqual(code, 1, said)
        self.assertIn("the version on GitHub could not be read", said)
        self.assertEqual(self.exe.read_bytes(), self.OLD)

    def test_a_running_program_is_never_replaced(self):
        """A program with the exe's name is running (a copy of ping.exe
        under that name): the exe here is left as it is."""
        elsewhere = self.tmp / "running"
        elsewhere.mkdir()
        stand_in = elsewhere / EXE
        shutil.copy(Path(os.environ["SystemRoot"]) / "System32" / "PING.EXE", stand_in)
        running = subprocess.Popen([str(stand_in), "-n", "120", "127.0.0.1"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.exe.write_bytes(self.OLD)
            code, said = self.run_it()
            self.assertEqual(code, 2, said)
            self.assertIn(f"NOT UPDATED: {EXE} is running", said)
            self.assertEqual(self.exe.read_bytes(), self.OLD)
            self.assertFalse(self.previous.exists())
            self.assertEqual(self.left_over(), [])
            # "start" does not open a second one either.
            code, said = self.run_it("start")
            self.assertEqual(code, 2, said)
            self.assertNotIn(f"Starting {EXE}", said)
        finally:
            running.kill()
            running.wait(timeout=30)
        # Closed: now it is replaced.
        code, said = self.run_it()
        self.assertEqual(code, 0, said)
        self.assertEqual(self.exe.read_bytes(), self.NEW)


@unittest.skipUnless(WINDOWS and os.environ.get("UPDATE_BAT_LIVE") == "1", "the real release on GitHub: only when UPDATE_BAT_LIVE=1")
class AgainstGitHub(unittest.TestCase):
    def test_it_downloads_the_released_exe_and_then_finds_it_newest(self):
        folder = Path(tempfile.mkdtemp(prefix="rt update live & "))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        script = folder / SCRIPT.name
        shutil.copy(SCRIPT, script)

        def run_it():
            return run_script(script, timeout=900)
        code, said = run_it()
        print(said)
        self.assertEqual(code, 0, said)
        self.assertIn(f"UPDATED: {EXE} is now the newest", said)
        exe = folder / EXE
        self.assertGreater(exe.stat().st_size, 20_000_000)
        version = next(line.split('"')[1] for line in (ROOT / "pyproject.toml").read_text(encoding="utf-8").splitlines() if line.startswith("version"))
        with urllib.request.urlopen(f"https://github.com/nbb2026/Transport-all/releases/download/{KEY}-v{version}/{EXE}.sha256", timeout=60) as reply:
            published = reply.read().decode("ascii").split()[0]
        self.assertEqual(hashlib.sha256(exe.read_bytes()).hexdigest(), published)
        self.assertIn("Commit:", said)
        code, said = run_it()
        self.assertEqual(code, 0, said)
        self.assertIn("UP TO DATE", said)


if __name__ == "__main__":
    unittest.main()
