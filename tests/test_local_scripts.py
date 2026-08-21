"""Regression checks for the Windows local service launchers."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


class LocalLauncherTests(unittest.TestCase):
    def script(self, name: str) -> str:
        return (SCRIPTS / name).read_text(encoding="utf-8")

    def test_all_in_one_launcher_is_non_interactive_by_default(self):
        source = self.script("start_local.cmd")

        self.assertIn('set "NO_PAUSE=1"', source)
        self.assertIn('if /I "%~1"=="--pause" set "NO_PAUSE=0"', source)
        self.assertNotIn('start_db_local.cmd', source)
        self.assertNotIn(':3306', source)
        self.assertIn('start_backend_local.cmd" --no-pause', source)
        self.assertIn('start_frontend.cmd" --no-pause', source)

        shared_frontend = self.script("start_frontend.cmd")
        self.assertIn("npm.cmd run dev -- --host 127.0.0.1", shared_frontend)

    def test_backend_launcher_forces_safe_local_sqlite_profile(self):
        backend = self.script("start_backend_local.cmd")
        runner = (SCRIPTS / "run_local_backend.py").read_text(encoding="utf-8")

        self.assertIn('scripts\\run_local_backend.py', backend)
        self.assertIn('os.environ["APP_MODE"] = "local"', runner)
        self.assertIn('os.environ["DATABASE_URL"] = "sqlite:///./data/resumebranch.db"', runner)
        self.assertIn('os.environ["HOST"] = "127.0.0.1"', runner)

    def test_stop_launcher_does_not_manage_mysql(self):
        source = self.script("stop_app.cmd")

        self.assertNotIn('sc.exe', source)
        self.assertNotIn('net.exe stop', source)
        self.assertIn('database data was not removed', source)

    def test_superseded_launcher_names_are_removed(self):
        for name in (
            "start_frontend_local.cmd",
            "start_db_local.cmd",
            "stop_local.cmd",
        ):
            self.assertFalse((SCRIPTS / name).exists(), name)

    def test_mysql_has_an_explicit_safe_stop_launcher(self):
        source = self.script("stop_mysql.cmd")

        self.assertIn('set "DB_SERVICE=MySQL84"', source)
        self.assertIn('net.exe stop "%DB_SERVICE%"', source)
        self.assertIn('-Verb RunAs', source)
        self.assertIn('No database files or application data were deleted', source)
        self.assertNotIn('taskkill.exe', source)
        self.assertNotIn('del /q', source)

    def test_background_workers_do_not_inherit_console_input(self):
        backend = self.script("start_backend_local.cmd")
        frontend = self.script("start_frontend.cmd")

        self.assertIn('"%BACKEND_RUNNER%" 0<nul', backend)
        self.assertIn('scripts\\run_local_backend.py', backend)
        self.assertIn('scripts\\run_multi_user_backend.py', backend)
        self.assertIn('--host 127.0.0.1 0<nul', frontend)


if __name__ == "__main__":
    unittest.main()
