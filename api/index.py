"""Vercel entry point: the whole FastAPI backend, served under /api.

The UI calls /api/report, /api/fields/profile, ... (the same paths the Vite dev
proxy uses locally), so the backend app is mounted at /api here.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402

app = FastAPI(title="Patato on Vercel", docs_url=None, redoc_url=None)

try:
    from app.main import app as backend  # noqa: E402
    app.mount("/api", backend)
except Exception:  # TEMPORARY: show why the backend failed to start (remove once fixed)
    _startup_error = traceback.format_exc()

    @app.get("/api/{path:path}")
    def startup_failed(path: str):
        return {"startup_error": _startup_error.splitlines()[-25:],
                "python": sys.version, "files": sorted(p.name for p in Path(__file__).resolve().parent.parent.iterdir())}
