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
        self.assertIn('start_db_local.cmd" --no-pause', source)
        self.assertIn('start_backend_local.cmd" --no-pause', source)
        self.assertIn('start_frontend_local.cmd" --no-pause', source)

    def test_background_workers_do_not_inherit_console_input(self):
        backend = self.script("start_backend_local.cmd")
        frontend = self.script("start_frontend_local.cmd")

        self.assertIn('backend.main 0<nul', backend)
        self.assertIn('--host 127.0.0.1 0<nul', frontend)


if __name__ == "__main__":
    unittest.main()
