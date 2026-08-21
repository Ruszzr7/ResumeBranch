"""Launch the backend with an explicit, non-networked local data profile."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# Set these before importing any backend module. This is more reliable than
# relying on a child shell to override values left in an older .env file.
os.environ["APP_MODE"] = "local"
os.environ["DATABASE_URL"] = "sqlite:///./data/resumebranch.db"
os.environ["HOST"] = "127.0.0.1"

runpy.run_module("backend.main", run_name="__main__")
