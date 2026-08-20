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
        self.assertIn('start_frontend_local.cmd" --no-pause', source)

    def test_backend_launcher_forces_safe_local_sqlite_profile(self):
        backend = self.script("start_backend_local.cmd")
        runner = (SCRIPTS / "run_local_backend.py").read_text(encoding="utf-8")

        self.assertIn('scripts\\run_local_backend.py', backend)
        self.assertIn('os.environ["APP_MODE"] = "local"', runner)
        self.assertIn('os.environ["DATABASE_URL"] = "sqlite:///./data/deepagents.db"', runner)
        self.assertIn('os.environ["HOST"] = "127.0.0.1"', runner)

    def test_stop_launcher_does_not_manage_mysql(self):
        source = self.script("stop_local.cmd")

        self.assertNotIn('sc.exe', source)
        self.assertNotIn('net.exe stop', source)
        self.assertIn('SQLite data remains in data\\deepagents.db', source)

    def test_background_workers_do_not_inherit_console_input(self):
        backend = self.script("start_backend_local.cmd")
        frontend = self.script("start_frontend_local.cmd")

        self.assertIn('run_local_backend.py" 0<nul', backend)
        self.assertIn('--host 127.0.0.1 0<nul', frontend)


if __name__ == "__main__":
    unittest.main()
