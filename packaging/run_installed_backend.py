"""Installed-mode wrapper around the frozen local backend entry point."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


APP_ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = APP_ROOT / ".local-run"
RUN_ROOT.mkdir(parents=True, exist_ok=True)

stdout_log = (RUN_ROOT / "backend.installed.out.log").open("a", encoding="utf-8", buffering=1)
stderr_log = (RUN_ROOT / "backend.installed.err.log").open("a", encoding="utf-8", buffering=1)
sys.stdout = stdout_log
sys.stderr = stderr_log

pid_path = RUN_ROOT / "backend.installed.pid"
pid_path.write_text(str(os.getpid()), encoding="ascii")

try:
    runpy.run_path(str(APP_ROOT / "scripts" / "run_local_backend.py"), run_name="__main__")
finally:
    try:
        if pid_path.read_text(encoding="ascii").strip() == str(os.getpid()):
            pid_path.unlink(missing_ok=True)
    except OSError:
        pass
    stdout_log.close()
    stderr_log.close()
