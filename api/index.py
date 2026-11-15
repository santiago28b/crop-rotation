"""Vercel entry point: the whole FastAPI backend, served under /api.

The UI calls /api/report, /api/fields/profile, ... (the same paths the Vite dev
proxy uses locally), so the backend app is mounted at /api here.

Note: app/climate.py imports scripts/fetch_power.py, so scripts/ must stay in
the function bundle (see excludeFiles in vercel.json).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402

from app.main import app as backend  # noqa: E402

app = FastAPI(title="Patato on Vercel", docs_url=None, redoc_url=None)
app.mount("/api", backend)
